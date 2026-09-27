# -*- coding: utf-8 -*-
"""口座の状態と、1日の進め方（第7章）。

  引け後 evening(d) … 1) 今朝の注文を d の寄値で「約定したことにする」（paper）。
                         実発注モードでは、実際に発注に成功した注文だけを、注文約定照会で確かめて記帳する
                      2) d の終値でシグナル判定 → 翌営業日の寄り付きの注文（pending）を作る
                      3) 記録（state/account.json と logs/）
                      終値が取れなかった銘柄があれば days[d]["skipped"] に残り、同じ日をもう一度実行すると、その銘柄だけ再判定する
  朝     morning(d)  … 接続確認。ORDER_MODE=="live" のときだけ、d 用の pending を寄成で実発注（売りを先に）。
                      送信済みの注文には order_id が付き、同じ日に何度実行しても二重に出さない

state/account.json:
  positions  {code: {qty, entry_date, entry_px}}
  pending    [{code, side, qty, for_date, reason, order_id?, uncertain?, send_error?}]
  days       {date: {"filled": [...], "signals": [...], "pnl": 円, "cumulative_pnl": 円, "skipped": [銘柄...]}}
  orders     [{date, code, side, qty, mode, status: sent|failed|uncertain, result}]   ← 出した（出したつもりの）注文の台帳
  unfilled   [{...注文, date, reason}]   ← 実発注モードで約定扱いにしなかった注文（未送信・失敗・不明・約定0株）。人が確認する
"""
import contextlib
import json
import os
import time
from datetime import datetime

import config
from kabu_auto import api
from kabu_auto import calendar as cal
from kabu_auto import data, sizing, strategy

EMPTY = {"positions": {}, "pending": [], "days": {}, "orders": [], "unfilled": [], "cumulative_pnl": 0}


def load() -> dict:
    if config.STATE_FILE.is_file():
        st = json.loads(config.STATE_FILE.read_text(encoding="utf-8"))
    else:
        st = json.loads(json.dumps(EMPTY))
    st.setdefault("unfilled", [])       # 古い state/account.json にも足す
    return st


def save(st: dict) -> None:
    config.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    st["updated_at"] = f"{datetime.now():%Y-%m-%d %H:%M:%S}"
    tmp = config.STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(config.STATE_FILE)


def log(msg: str) -> None:
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (config.LOG_DIR / "kabu-auto.log").open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}\t{msg}\n")
    print(msg)


# ---------------------------------------------------------------- 引け後

def fill_pending(st: dict, d: str, status_func=None) -> list:
    """d 用の pending を d の寄値で約定したことにする。

    paper … 全部、寄値で約定扱い。
    live  … order_id がある（発注に成功した）ものだけ。発注していない・失敗・結果不明は約定扱いにせず st["unfilled"] へ。
            status_func(order_id) が使えれば、注文約定照会の約定数量（CumQty）で確かめる（0株なら記帳しない／一部なら約定した数量だけ）。
            照会できなかったときは、寄値で約定した見積もりとして記帳し、"verified": False を付けて警告する。
    """
    live = config.ORDER_MODE == "live"
    filled, keep = [], []
    for o in st["pending"]:
        if o["for_date"] != d:
            keep.append(o)
            continue
        tag = f"{o['code']} {o['side']}"
        if live and not o.get("order_id"):
            why = "前回の送信結果が不明（要確認。kabuステーションの注文約定照会を見る）" if o.get("uncertain") \
                else "発注していない（失敗か、1日の上限超過）"
            log(f"  [ERROR] {tag}: {why}。約定扱いにしません（state の unfilled に記録）")
            st["unfilled"].append({**o, "date": d, "reason": why})
            continue
        px = data.open_of(o["code"], d)
        if not px:
            log(f"  [WARN] {o['code']} の {d} の寄値が無い（休場か、今日の分を取り込む前）。注文を持ち越します")
            keep.append(o)
            continue

        qty, verified = o["qty"], None
        if live and status_func is not None:
            try:
                info = status_func(o["order_id"])
            except Exception as e:  # noqa: BLE001
                info, verified = None, False
                log(f"  [WARN] {tag}: 注文約定照会に失敗（{e}）。寄値の見積もりで記帳します。証券会社の画面で確認してください")
            else:
                if not info:
                    verified = False
                    log(f"  [WARN] {tag}: 注文約定照会に見当たりません。寄値の見積もりで記帳します。証券会社の画面で確認してください")
                else:
                    cum = int(info.get("CumQty") or 0)
                    if cum <= 0:
                        # 約定が確認できない注文を、建玉として記帳してはいけない（帳簿に無い保有より、実在しない保有のほうが危ない）。
                        # 実際は約定していた場合は、引け後の残高の突き合わせが食い違いとして知らせる
                        log(f"  [ERROR] {tag}: 約定 0 株です（State {info.get('State')}）。約定扱いにしません。"
                            "kabuステーションの注文約定照会で確認してください")
                        st["unfilled"].append({**o, "date": d, "reason": f"約定0株（State {info.get('State')}）"})
                        continue
                    if cum < qty:
                        log(f"  [WARN] {tag}: 一部だけ約定（{cum}/{qty} 株）。約定した数量だけ記帳します")
                        qty = cum
                    verified = True

        pos = st["positions"].get(o["code"])
        if o["side"] == "買い" and pos is None:
            st["positions"][o["code"]] = {"qty": qty, "entry_date": d, "entry_px": px}
            filled.append({**o, "qty": qty, "px": px, "pnl": 0, "verified": verified})
        elif o["side"] == "売り" and pos is not None:
            qty = min(qty, pos["qty"])
            pnl = (px - pos["entry_px"]) * qty
            if qty >= pos["qty"]:
                del st["positions"][o["code"]]
            else:
                pos["qty"] -= qty
            filled.append({**o, "qty": qty, "px": px, "pnl": pnl, "verified": verified})
        else:
            log(f"  [skip] {tag}：建玉の状態と合わないので見送り")
    st["pending"] = keep
    return filled


def expire_stale(st: dict, d: str) -> None:
    """d より前の日付の注文は、もう出せない（古いシグナル）。待ち一覧に残さず、unfilled に理由つきで移す。"""
    keep = []
    for o in st["pending"]:
        if o["for_date"] < d:
            log(f"  [WARN] {o['code']} {o['side']}: {o['for_date']} 用の注文が期限切れです（その日の処理が動かなかった）。"
                "破棄して unfilled に記録します")
            st["unfilled"].append({**o, "date": d, "reason": f"期限切れ（{o['for_date']} 用）"})
        else:
            keep.append(o)
    st["pending"] = keep


def make_signals(st: dict, d: str, codes: list = None, skipped: list = None) -> list:
    """d の終値までのデータでシグナルを判定し、翌営業日の寄り付きの注文にする。

    codes … 判定する銘柄（省略なら config.SYMBOLS 全部）。skipped … 終値が無くて判定できなかった銘柄を入れる出力先。
    """
    nxt = cal.next_trading_day(d)
    out = []
    for code in (codes if codes is not None else config.SYMBOLS):
        dates, closes = data.closes(code, until=d)
        if not dates or dates[-1] != d:
            log(f"  [WARN] {code}: {d} の終値が無い（データ収集が失敗?）。判定を飛ばします")
            if skipped is not None:
                skipped.append(code)
            continue
        held = code in st["positions"]
        jump = data.recent_jump(code, d, config.LONG_PERIOD)
        if jump and not held:
            log(f"  [ERROR] {code}: {jump[0]} に前日比 {jump[1]:.2f} 倍の段差（分割・併合、または調整済み/未調整の混在の疑い）。"
                "移動平均が誤爆するので、新規の買いシグナルは出しません。データを確認して直してください（py run_backtest.py --audit）")
            continue
        if jump:
            # 保有中の銘柄の売りは止めない（本当の暴落で売れなくなるほうが危ない）。誤爆かもしれないので警告だけ出す
            log(f"  [WARN] {code}: {jump[0]} に前日比 {jump[1]:.2f} 倍の段差。保有中なので売りの判定は続けますが、データを確認してください")
        sig = strategy.latest_signal(dates, closes)
        if sig == "買い" and not held:
            qty = sizing.order_qty(code, closes[-1])
            if qty <= 0:
                log(f"  [WARN] {code}: 買いシグナルですが、{closes[-1]:,.0f}円 x 1単元（{sizing.lot_size(code)}株）が"
                    f"1回の上限 {config.BUDGET_PER_ORDER:,} 円を超えるので見送ります")
                continue
            out.append({"code": code, "side": "買い", "qty": qty, "for_date": nxt, "reason": f"{d} ゴールデンクロス"})
        elif sig == "売り" and held:
            out.append({"code": code, "side": "売り", "qty": st["positions"][code]["qty"], "for_date": nxt, "reason": f"{d} デッドクロス"})
    return out


class Busy(Exception):
    """別の実行が state を使っている。"""


LOCK_STALE_SEC = 600


@contextlib.contextmanager
def _lock():
    """state/account.lock を排他的に作る。二重起動（朝のボタンを2回押す等）で、同じ注文を2回出さないため。

    実行が異常終了してロックが残っても、LOCK_STALE_SEC（10分）たてば無効として奪う。
    """
    p = config.STATE_FILE.parent / "account.lock"
    p.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                age = time.time() - p.stat().st_mtime
            except OSError:
                continue
            if age < LOCK_STALE_SEC:
                raise Busy(f"別の実行が進行中です（{p.name}）。終わってからやり直してください。"
                           f"異常終了で残っている場合は、{int(LOCK_STALE_SEC / 60)}分たつと自動で解除されます")
            try:
                p.unlink()
            except OSError:
                pass
    else:
        raise Busy("ロックを取れませんでした")
    try:
        os.write(fd, f"{os.getpid()} {datetime.now():%Y-%m-%d %H:%M:%S}".encode("ascii"))
        os.close(fd)
        yield
    finally:
        try:
            p.unlink()
        except OSError:
            pass


def evening(d: str, status_func=None, holdings_func=None) -> dict:
    """引け後の処理（二重起動を避けるロックつき）。"""
    try:
        with _lock():
            return _evening(d, status_func, holdings_func)
    except Busy as e:
        log(f"[ERROR] {e}")
        return load()


def _evening(d: str, status_func=None, holdings_func=None) -> dict:
    """引け後の処理の本体。status_func は実発注モードで注文約定照会に使う（run_collect.status_func_for_live()）。

    取得に失敗して判定できなかった銘柄があると、その日は「未完了」として残る。データを取り直して同じ日をもう一度
    実行すると、判定できなかった銘柄だけを再判定する（約定の記帳と、済んだ銘柄の判定は二重にやらない）。
    """
    st = load()
    prev = st["days"].get(d)
    if prev is not None and not prev.get("skipped"):
        log(f"[skip] {d} は処理済みです（二重に進めません）")
        return st
    rerun = prev is not None
    log(f"--- {d} 引け後の処理" + (f"（再判定: {', '.join(prev['skipped'])}）" if rerun else "") + " ---")
    expire_stale(st, d)
    filled = fill_pending(st, d, status_func)
    for f in filled:
        log(f"  約定（{config.ORDER_MODE}）: {f['code']} {f['side']} {f['qty']}株 @ {f['px']:,.1f}"
            + (f"  損益 {f['pnl']:+,.0f}円" if f["side"] == "売り" else ""))
    pnl = sum(f["pnl"] for f in filled)
    st["cumulative_pnl"] += pnl
    skipped = []
    new = make_signals(st, d, codes=prev["skipped"] if rerun else None, skipped=skipped)
    st["pending"].extend(new)
    for o in new:
        log(f"  {'出すはずの' if config.ORDER_MODE == 'paper' else '明朝に出す'}注文: {o['for_date']} 寄り付き "
            f"{o['code']} {o['side']} {o['qty']}株（{o['reason']}）")
    if not new:
        log("  新しいシグナルはありません")
    if rerun:
        day = {"filled": prev["filled"] + filled, "signals": prev["signals"] + new, "pnl": prev["pnl"] + pnl}
    else:
        day = {"filled": filled, "signals": new, "pnl": pnl}
    day["cumulative_pnl"] = st["cumulative_pnl"]
    if skipped:
        day["skipped"] = skipped
    st["days"][d] = day
    save(st)
    log(f"  本日の損益 {pnl:+,.0f}円 / 累積 {st['cumulative_pnl']:+,.0f}円 / 建玉 {len(st['positions'])} 件 / "
        f"明日の注文 {len(new)} 件")
    if skipped:
        log(f"  [WARN] {len(skipped)} 銘柄（{', '.join(skipped)}）は終値が無く判定できていません。"
            f"データが取れたら、同じ日をもう一度実行してください（この銘柄だけ再判定します）")
    if config.ORDER_MODE == "live":
        log("  ※実発注モード。実際の約定はkabuステーションの「注文約定照会」で確認してください。ここの損益は寄値による見積もりです")
        if holdings_func is not None:
            try:
                diffs = reconcile(st, holdings_func())
            except Exception as e:  # noqa: BLE001
                log(f"  [WARN] 証券会社の残高を取れませんでした（{e}）。帳簿との突き合わせはできていません")
            else:
                if diffs:
                    log("  [ERROR] 帳簿と証券会社の残高が食い違っています。次の朝の発注の前に、原因を確かめてください:")
                    for x in diffs:
                        log(f"    {x}")
                else:
                    log("  帳簿と証券会社の残高は一致しています")
    return st


# ---------------------------------------------------------------- 朝

def _rec_status(x: dict) -> str:
    """台帳の1行の状態。status が無い古い行は result から推定する。"""
    return x.get("status") or ("failed" if str(x.get("result", "")).startswith("失敗") else "sent")


def morning(d: str, send_func=None, holdings: dict = None) -> list:
    """朝の発注（二重起動を避けるロックつき）。"""
    try:
        with _lock():
            return _morning(d, send_func, holdings)
    except Busy as e:
        log(f"[{d}] [ERROR] 実行を止めました: {e}")
        return []


def _morning(d: str, send_func=None, holdings: dict = None) -> list:
    """d 用の注文を出す。paper なら表示だけ。live なら send_func(code, side, qty) を呼ぶ。

    - 売りを先に出す（1日の上限に達したとき、手仕舞いの売りが買いに押し出されないように）
    - 送信済み（order_id あり）・結果不明（uncertain）の注文は、何度実行しても再送しない（二重注文の防止）
    - 確実に失敗した注文（エラーコード付きの拒否）だけは、原因を直して同じ日にもう一度実行すれば再送できる
    - 1日の上限に数えるのは、送信済みと結果不明。確実に失敗したものは数えない
    - holdings（証券会社の現物の保有 {銘柄コード: 株数}）を渡すと、発注の前に残高と突き合わせる：
      買い … 証券会社にすでに保有がある銘柄は出さない（帳簿と食い違ったまま重ねて買わない）
      売り … 証券会社の保有が売る株数に足りない銘柄は出さない
      出さなかった注文は待ち一覧に残り、引け後に「発注していない」として state の unfilled に記録される
    """
    st = load()
    todays = [o for o in st["pending"] if o["for_date"] == d]
    if not todays:
        log(f"[{d}] 今日出す注文はありません")
        return []
    if config.ORDER_MODE != "live":
        for o in todays:
            log(f"[{d}] 出したつもり: {o['code']} {o['side']} {o['qty']}株 寄成（{o['reason']}）")
        return []
    warn = cal.holiday_warning(d)
    if warn:
        log(f"[{d}] [ERROR] 実発注を止めました: {warn}")
        return []
    todays.sort(key=lambda o: 0 if o["side"] == "売り" else 1)      # 並べ替えは安定。売り→買いの順、それぞれ元の順序
    sent_today = sum(1 for x in st["orders"]
                     if x["date"] == d and x["mode"] == "live" and _rec_status(x) in ("sent", "uncertain"))
    results, over_limit = [], []
    for o in todays:
        tag = f"{o['code']} {o['side']} {o['qty']}株"
        if o.get("order_id"):
            log(f"[{d}] 送信済みなので再送しません: {tag} 注文ID {o['order_id']}")
            continue
        if o.get("uncertain"):
            log(f"[{d}] [WARN] {tag}: 前回の送信結果が不明です。二重注文を避けるため再送しません。"
                "kabuステーションの「注文約定照会」で確認してください")
            continue
        if sent_today >= config.DAILY_ORDER_LIMIT:
            over_limit.append(tag)
            continue
        if holdings is not None:
            have = holdings.get(o["code"], 0)
            why = ""
            if o["side"] == "買い" and have > 0:
                why = f"証券会社の残高にすでに {have} 株あります（帳簿には無い）。重ねて買わないよう出しません"
            elif o["side"] == "売り" and have < o["qty"]:
                why = f"証券会社の残高が {have} 株で、売る {o['qty']} 株に足りません。出しません"
            if why:
                o["send_error"] = "残高の突き合わせで見送り: " + why
                log(f"[{d}] [ERROR] {tag}: {why}。帳簿と証券会社の状態がずれています。kabuステーションの残高を確認してください")
                continue
        rec = {"date": d, "code": o["code"], "side": o["side"], "qty": o["qty"], "mode": "live"}
        try:
            res = send_func(o["code"], o["side"], o["qty"])
            order_id = res.get("OrderId") if isinstance(res, dict) else None
            if order_id:
                o["order_id"] = order_id
                o.pop("send_error", None)
                rec.update(status="sent", result=order_id)
                log(f"[{d}] ★実発注: {tag} 寄成 → 注文ID {order_id}")
            else:       # 注文IDが返らない = 受け付けられたか分からない
                o["uncertain"] = True
                rec.update(status="uncertain", result=f"不明: 注文IDなし（応答 {res}）")
                log(f"[{d}] [WARN] {tag}: 注文IDが返りませんでした（応答 {res}）。再送せず、注文約定照会で確認してください")
            sent_today += 1
        except api.OrderUncertain as e:
            o["uncertain"] = True
            rec.update(status="uncertain", result=f"不明: {e}")
            log(f"[{d}] [WARN] 発注結果が不明: {tag} → {e}")
            sent_today += 1
        except Exception as e:  # noqa: BLE001
            o["send_error"] = str(e)
            rec.update(status="failed", result=f"失敗: {e}")
            log(f"[{d}] 発注失敗: {tag} → {e}")
        st["orders"].append(rec)
        results.append(rec)
        save(st)            # 1件ごとに保存する。途中で止まっても、送った注文の order_id が残り、再実行で再送しない
    if over_limit:
        log(f"[{d}] [WARN] 1日の上限（{config.DAILY_ORDER_LIMIT}件）に達したので出していません: {', '.join(over_limit)}"
            "（帳簿には約定扱いにしません）")
    save(st)
    return results


def reconcile(st: dict, holdings: dict) -> list:
    """帳簿の建玉と、証券会社の現物の保有を突き合わせる。食い違いの説明を返す（何も変えない）。

    見るのは config.SYMBOLS と帳簿にある銘柄だけ（それ以外の保有は、この自動売買の対象ではないので無視する）。
    """
    out = []
    for code in sorted(set(config.SYMBOLS) | set(st["positions"])):
        ledger = st["positions"].get(code, {}).get("qty", 0)
        broker = holdings.get(code, 0)
        if ledger != broker:
            out.append(f"{code}: 帳簿 {ledger} 株 / 証券会社 {broker} 株")
    return out


def status() -> str:
    st = load()
    lines = [f"モード: {config.ORDER_MODE}　累積損益 {st['cumulative_pnl']:+,.0f}円　建玉 {len(st['positions'])} 件　"
             f"待ち注文 {len(st['pending'])} 件　処理済み {len(st['days'])} 日"]
    for code, p in st["positions"].items():
        lines.append(f"  保有 {code} {p['qty']}株 @ {p['entry_px']:,.1f}（{p['entry_date']}〜）")
    for o in st["pending"]:
        extra = "　[送信済み]" if o.get("order_id") else ("　[結果不明・要確認]" if o.get("uncertain") else "")
        lines.append(f"  注文 {o['for_date']} {o['code']} {o['side']} {o['qty']}株（{o['reason']}）{extra}")
    for d, day in sorted(st["days"].items()):
        if day.get("skipped"):
            lines.append(f"  [未完了] {d}: 判定できていない銘柄 {', '.join(day['skipped'])}（同じ日をもう一度実行）")
    if st["unfilled"]:
        lines.append(f"  [要確認] 約定扱いにしなかった注文 {len(st['unfilled'])} 件（state/account.json の unfilled）")
    return "\n".join(lines)
