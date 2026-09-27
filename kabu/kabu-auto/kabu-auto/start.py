# -*- coding: utf-8 -*-
"""起動メニュー：最初にモードを選ぶ。

使い方:  py start.py            （メニューで選ぶ）
         py start.py --mode backtest 7203 --walk
         py start.py --mode paper evening|morning
         py start.py --mode live morning     ← 実弾。確認の入力を求める
         py start.py --mode live t 9432 --confirm 実弾
                                             ← 試し撃ち（7-1b）。寄成を1回出して、すぐ取り消す。
                                               --confirm はユーザーが「実弾」と書いたときだけ付ける

ここで選んだモードは「この1回」だけ。config.py の ORDER_MODE（既定 "paper"）は変えない。
タスクスケジューラで回す run_collect.bat／run_morning.bat は config.py の設定で動く。
"""
import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import config                                              # noqa: E402
from kabu_auto import api, backtest, calendar as cal, data, paper, sizing  # noqa: E402

BANNER = """
==============================================
  kabu-auto  移動平均クロスの自動売買（本書の完成形）
==============================================
どのモードで動かしますか？

  1) バックテスト              過去データで戦略を試す。kabuステーションは使わない
  2) 発注しないモード（ペーパー）  今日の収集と判定。注文は「出したつもり」で記録するだけ
  3) 実弾モード（実発注）        寄り付きの成行で、本当に注文を出す ★お金が動く
  s) 状態を見る
  q) やめる
"""


def ask(prompt: str, default: str = "") -> str:
    try:
        v = input(prompt).strip()
    except EOFError:
        return default
    return v or default


# ---------------------------------------------------------------- 各モード

def mode_backtest(code: str = "", grid: bool = None, walk: bool = None) -> int:
    code = code or ask("銘柄コード（例 7203）: ")
    if not code:
        print("銘柄コードが空です。")
        return 1
    dates, opens, closes = data.series(code)
    if len(closes) < config.LONG_PERIOD + 2:
        print(f"NG: {code} のデータが {len(closes)} 日分しかありません。"
              f"先に過去データを入れてください（py run_backtest.py --import {code} 取ってきた.csv）")
        return 1
    if grid is None:
        grid = ask("総当たりもやりますか？（罠の実演。y/N）: ", "n").lower() == "y"
    if walk is None:
        walk = ask("walk-forward もやりますか？（Y/n）: ", "y").lower() != "n"
    print(f"\n銘柄 {code}  {dates[0]} 〜 {dates[-1]}（{len(dates)} 日）")
    print(f"約定: シグナルの翌営業日の寄値 / コスト 片道 {config.BACKTEST_SLIPPAGE_BPS + config.BACKTEST_FEE_BPS:g}bp（税金は下に概算で別表示）")
    r = backtest.run(dates, closes, config.SHORT_PERIOD, config.LONG_PERIOD, opens)
    n, wr, avg = backtest.summary(r)
    print(f"素直 {config.SHORT_PERIOD}日/{config.LONG_PERIOD}日: 累積損益 {r['total']:+,.1f}円（1株）/ 取引 {n} 回 / "
          f"勝率 {wr:.1f}% / 1取引あたり平均 {avg:+.2f}%")
    tax, net = backtest.after_tax(r["trades"])
    print(f"  税引後（概算・確定した取引のみ）: {net:+,.1f}円 / 税 {tax:,.1f}円（税率 {config.BACKTEST_TAX_RATE * 100:.3f}%。繰越控除・損益通算は考えない）")
    if grid:
        ranked = backtest.grid_search(dates, closes, opens=opens)
        print(f"総当たり {len(ranked)} 通り。上位3:")
        for total, s, l, n, w in ranked[:3]:
            print(f"  {s:>2}日/{l:>3}日  {total:+,.1f}円  取引{n}回 勝率{w:.1f}%")
        print("※過去に合わせ込んだ数字です。信じない（第6章 6-4）")
    if walk:
        wf = backtest.walk_forward(dates, closes, opens=opens)
        if not wf["windows"]:
            print(f"walk-forward: 学習{config.TRAIN_DAYS}日＋検証{config.TEST_DAYS}日の窓が作れません（データが短い）")
        else:
            wins = sum(1 for w in wf["windows"] if w[6] > 0)
            print(f"walk-forward: 検証期間の累積 {wf['wf_equity'][-1]:+,.1f}円 / {len(wf['windows'])} 窓中 勝ち {wins}")
    return 0


def mode_paper(step: str = "") -> int:
    config.ORDER_MODE = "paper"
    step = step or ask("引け後の処理(e) / 朝の確認(m) どちら？ [e/m]: ", "e").lower()
    d = cal.today()
    if step.startswith("m"):
        try:
            print(api.check_connection())
        except api.ApiError as e:
            print(f"NG: {e}")
            return 1
        paper.morning(d)
        print("今日は動きます（発注しないモード）。")
        return 0
    if not cal.is_trading_day(d):
        print(f"{d} は休場です。")
        return 0
    fetch = ask("kabuステーションAPIから今日の分を取りますか？（Y/n）: ", "y").lower() != "n"
    if fetch:
        from run_collect import collect
        failed = collect(d)
        if failed:
            print(f"[WARN] {failed} 銘柄の取得に失敗（ログに残しています）")
    paper.evening(d)
    return 0


def mode_live(step: str = "", test_code: str = "", confirm: str = "") -> int:
    print("\n★★★ 実弾モード ★★★")
    per = f"{config.BUDGET_PER_ORDER:,} 円まで" if config.BUDGET_PER_ORDER is not None else f"{config.QTY} 株（固定）"
    print(f"  寄り付きの成行で本当に注文を出します。1回 {per}、1日 {config.DAILY_ORDER_LIMIT} 件まで。")
    print("  7-1b の準備（最小単元ぶんの入金／ソフトリミットを最小に／規約の確認）は済んでいますか？")
    if config.CONFIRM_WORD:
        word = confirm or ask(f"続けるなら「{config.CONFIRM_WORD}」と入力してください: ")
        if word != config.CONFIRM_WORD:
            print("中止しました（発注は出していません）。")
            return 1
    else:
        print("  ※ 合言葉なしで動いています（config.CONFIRM_WORD が空。おすすめしません）")
    config.ORDER_MODE = "live"
    step = step or ask("朝の発注(m) / 引け後の処理(e) / 試し撃ち→即取消(t) どれ？ [m/e/t]: ", "m").lower()
    d = cal.today()
    if step.startswith("t"):
        # 試し撃ち（7-1b）：帳簿に「今日の寄り付き・買い・1単元」を1件だけ手で積み、朝のボタンと同じ処理（paper.morning）で
        # 送る。受け付けられたら、その場で取り消し、注文約定照会で約定 0 株を確かめる。本番のシグナルが翌朝たどるのと同じ道。
        # 取引時間中は 後場の寄りで約定しうるので受け付けない。買付余力（1単元ぶん）が無いと証券会社側で拒否される。
        if cal.is_trading_day(d) and "09:00" <= f"{datetime.now():%H:%M}" < "15:30":
            print("取引時間中（9:00〜15:30）は試し撃ちしません。引け後か、朝9時前にどうぞ。")
            return 1
        code = test_code or ask("銘柄コード（1単元の買いを1回出して、すぐ取り消します）: ")
        if not code:
            print("中止しました。")
            return 1
        test_qty = sizing.lot_size(code)
        print(f"  試し撃ちの株数: {test_qty} 株（1単元。config.LOT_SIZES / LOT_SIZE）")
        print(f"  接続先: {config.API_BASE}（{'本番' if config.ENV == 'prod' else '検証環境'}）")
        st = paper.load()
        if any(o.get("for_date") == d for o in st["pending"]):
            print(f"帳簿に {d} の注文がすでにあります（本番のシグナル分）。試し撃ちは、それを朝のボタンで出す前には行いません。")
            return 1
        st["pending"].append({"code": code, "side": "買い", "qty": test_qty, "for_date": d, "reason": "試し撃ち（手で積んだ）", "test": True})
        paper.save(st)
        try:
            print(api.check_connection())
            token = api.get_token()
            results = paper.morning(d, send_func=lambda c, side, q: api.send_order(token, c, side, q))
        except api.ApiError as e:
            print(f"NG: {e}")
            results = []
        st = paper.load()
        st["pending"] = [o for o in st["pending"] if not o.get("test")]     # 手で積んだ分は帳簿に残さない
        rec = st["orders"][-1] if results else None                          # morning() が末尾に足した台帳の行
        if rec is not None:
            rec["mode"] = f"live-test({config.ENV})"                         # 1日の上限（DAILY_ORDER_LIMIT）には数えない
        if rec is not None and rec.get("status") == "uncertain":
            paper.save(st)
            print("★ 注文が受け付けられたか分かりません。kabuステーションの「注文約定照会」を見て、残っていれば手で取り消してください。")
            return 1
        if rec is None or rec.get("status") != "sent":
            paper.save(st)
            print("注文は受け付けられませんでした。上のエラーを Claude Code に見せて、docs/ の仕様書を正として直してください。")
            return 1
        order_id = rec["result"]
        try:
            api.cancel_order(token, order_id)
            rec["cancelled"] = True
            print("取消を送りました。")
        except api.ApiError as e:
            rec["cancelled"] = False
            paper.save(st)
            print(f"NG: 取消に失敗 → {e}")
            print("★ 注文が残っています。kabuステーションの「注文約定照会」から、いま手で取り消してください。")
            return 1
        time.sleep(2)   # 照会への反映を待つ
        try:
            info = api.order_status(token, order_id)
            rec["cum_qty"] = info.get("CumQty", 0)
            print("注文約定照会: " + api.describe_order(info))
        except api.ApiError as e:
            print(f"照会は失敗しました（{e}）。kabuステーションの画面で確認してください。")
        paper.save(st)
        print("試し撃ち完了。お金は動いていません。kabuステーションの「注文約定照会」にも、受付と取消の記録が残っています。")
        return 0

    if step.startswith("m"):
        try:
            print(api.check_connection())
        except api.ApiError as e:
            print(f"NG: {e}")
            return 1
        token = api.get_token()
        try:
            holdings = api.holdings(token)       # 発注の前に、証券会社の残高を見る
        except api.ApiError as e:
            print(f"NG: 証券会社の残高を取れません（{e}）。突き合わせができないので、実発注は止めます。")
            return 1
        res = paper.morning(d, send_func=lambda code, side, qty: api.send_order(token, code, side, qty), holdings=holdings)
        print(f"注文 {len(res)} 件を処理しました。kabuステーションの「注文約定照会」で確認してください。")
        return 0
    from run_collect import collect, live_tools
    if cal.is_trading_day(d):
        failed = collect(d)
        if failed:
            print(f"[WARN] {failed} 銘柄の取得に失敗")
    status_func, holdings_func = live_tools()
    paper.evening(d, status_func, holdings_func)
    return 0


# ---------------------------------------------------------------- 入口

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["backtest", "paper", "live"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--grid", action="store_true")
    ap.add_argument("--walk", action="store_true")
    ap.add_argument("--env", choices=["prod", "test"], help="この1回だけ接続先を切り替える（test=検証環境 18081）")
    ap.add_argument("--confirm", default="", help="実弾モードの合言葉（config.CONFIRM_WORD、既定「実弾」）。Claude Code に走らせるとき、ユーザーがその言葉を書いたときだけ付ける")
    a = ap.parse_args()
    if a.env:
        config.ENV = a.env
        config.API_BASE = {"prod": "http://localhost:18080/kabusapi", "test": "http://localhost:18081/kabusapi"}[a.env]

    if a.mode == "backtest":
        return mode_backtest(a.args[0] if a.args else "", a.grid, a.walk)   # 引数指定のときは何も聞かない
    if a.mode == "paper":
        return mode_paper(a.args[0] if a.args else "")
    if a.mode == "live":
        return mode_live(a.args[0] if a.args else "", a.args[1] if len(a.args) > 1 else "", a.confirm)

    while True:
        print(BANNER)
        print(f"  （config.py の既定: ORDER_MODE={config.ORDER_MODE} / 銘柄 {len(config.SYMBOLS)} / "
              f"{config.SHORT_PERIOD}日-{config.LONG_PERIOD}日）")
        c = ask("番号を入力: ").lower()
        if c == "1":
            mode_backtest()
        elif c == "2":
            mode_paper()
        elif c == "3":
            mode_live()
        elif c == "s":
            print(paper.status())
        elif c in ("q", ""):
            return 0
        else:
            print("1 / 2 / 3 / s / q のどれかを入力してください。")
        ask("\nEnter で戻る ")


if __name__ == "__main__":
    sys.exit(main())
