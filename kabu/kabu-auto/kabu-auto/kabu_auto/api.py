# -*- coding: utf-8 -*-
"""kabuステーションAPI の窓口（第2・3章の作法をまとめたもの）。

- APIパスワードは環境変数から。値はログに出さない
- 情報系は 10件/秒 まで → 呼ぶたびに REQUEST_INTERVAL 空ける
- 429 / 5xx / 接続エラーだけリトライ（1→2→4秒）。400 / 401 は即エラー
- 注文の送信（send_order）だけはリトライしない。応答が届かなかっただけで注文は受理済み、ということがありうる
  （再送すると二重注文になる）。その場合は OrderUncertain を投げる
- トークンは毎回取り直す（新規発行で旧トークンは無効になる。同時に2つ動かさない）
- 取得した銘柄は自動で「登録銘柄リスト」に入る（上限50）。使い終わったら unregister_all()
"""
import json
import os
import time
import urllib.error
import urllib.request

import config

_last_call = 0.0


class ApiError(Exception):
    """人が読める日本語の説明つきエラー。"""


class OrderUncertain(ApiError):
    """注文を送ったが、受け付けられたか分からない（応答が届かない等）。

    再送してはいけない。kabuステーションの「注文約定照会」で確認する。
    """


def _throttle() -> None:
    global _last_call
    wait = config.REQUEST_INTERVAL - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()


def _call(path: str, method: str = "GET", body: dict = None, token: str = None, once: bool = False) -> dict:
    """once=True は「1回だけ送る」（注文用）。リトライしない。結果が分からないときは OrderUncertain。"""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-API-KEY"] = token
    req = urllib.request.Request(config.API_BASE + path, data=data, headers=headers, method=method)
    last, last_detail = None, ""
    for attempt in range(1 if once else 1 + config.MAX_RETRIES):
        if attempt:
            time.sleep(1.0 * 2 ** (attempt - 1))
        _throttle()
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                return json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            if once:
                # 注文は再送しない。kabu API がエラーコード付きで返した／429（受け付けていない）は「確実に失敗」。
                # コード無しの 5xx は、受け付けたか分からない
                if e.code == 429 or e.code < 500 or _is_api_error(detail):
                    raise ApiError(_explain(e.code, detail)) from None
                raise OrderUncertain(f"HTTP {e.code} が返りました（応答: {detail[:200]}）。注文が受け付けられたか分かりません。"
                                     "再送せず、kabuステーションの「注文約定照会」で確認してください") from None
            if e.code == 429 or (e.code >= 500 and not _is_api_error(detail)):
                last = e          # 頻度制限・本当に一時的なサーバーエラー → リトライ
                last_detail = detail
                continue
            # 4xx、または kabu API がエラーコード付きで返した 5xx は、待っても直らない → 中身を見せて止める
            raise ApiError(_explain(e.code, detail)) from None
        except OSError as e:      # 接続エラー・タイムアウト（URLError も TimeoutError も OSError の仲間）
            if once:
                if isinstance(e, urllib.error.URLError) and _refused(e):
                    raise ApiError("kabuステーションに接続できません（注文は送られていません）。アプリが起動してログインしているか確認してください") from None
                raise OrderUncertain(f"応答が届きませんでした（{e}）。注文が受け付けられたか分かりません。"
                                     "再送せず、kabuステーションの「注文約定照会」で確認してください") from None
            last = e
            continue
    if not isinstance(last, urllib.error.HTTPError):
        raise ApiError("kabuステーションに接続できません。アプリが起動してログインしているか、"
                       "右上の「</>」が緑かを確認してください（毎朝6:15にトークンが失効します。窓は開いたままです）")
    raise ApiError(f"一時的なエラーが続いています（{last}）。応答: {last_detail[:300]}。しばらく待って再実行してください")


def _refused(e: "urllib.error.URLError") -> bool:
    """接続そのものが拒否された（＝相手に届いていない）か。タイムアウトは届いたか分からないので False。"""
    return isinstance(getattr(e, "reason", None), ConnectionRefusedError)


def _is_api_error(detail: str) -> bool:
    """応答本文が kabu API のエラー形式（{"Code":..., "Message":...}）か。"""
    try:
        return "Code" in json.loads(detail)
    except ValueError:
        return False


def _explain(code: int, detail: str) -> str:
    try:
        j = json.loads(detail)
        api_code, msg = j.get("Code"), j.get("Message", "")
    except ValueError:
        api_code, msg = None, detail[:200]
    hints = {
        4001007: "kabuステーションにログインしていません",
        4001013: "APIパスワードが違います（ログインパスワードとは別物。1-4で設定したもの）",
        4001017: "kabuステーションが未ログインです",
        4001018: "銘柄登録の上限（50）に達しています。unregister_all() で解除してください",
        4001019: "銘柄登録の上限（50）に達しています。unregister_all() で解除してください",
        4002001: "銘柄が見つかりません。銘柄コードを確認してください",
        100378: "市場に「1（東証）」を指定した現物の新規注文は受け付けられません。config.ORDER_EXCHANGE を 9（SOR）に",
    }
    hint = hints.get(api_code, "docs/エラーコード一覧.md で意味を確認してください")
    return f"HTTP {code} / API {api_code}: {msg} → {hint}"


def _read_env_file(path, key: str) -> str:
    """KEY=VALUE 形式の .env から key の値だけ返す。無ければ ""。値はログに出さない。"""
    try:
        for line in open(path, encoding="utf-8-sig"):
            line = line.strip()
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def api_password() -> str:
    """三点セット（図1-5）: 本番(18080)は本番用、検証(18081)は検証用のパスワードを使う。"""
    key = config.API_PASSWORD_ENV if config.ENV == "prod" else config.API_PASSWORD_ENV_TEST
    pw = os.environ.get(key)
    if not pw and getattr(config, "ENV_FILE", None):
        pw = _read_env_file(config.ENV_FILE, key)
    if not pw and config.ENV != "prod":
        raise ApiError(f"検証環境には検証用のAPIパスワードが必要です（1-4 の「検証用」欄で設定し、環境変数 {key} に入れる）。"
                       "本番用のパスワードでは 401 になります（三点セット・図1-5）")
    if not pw:
        raise ApiError(f"環境変数 {config.API_PASSWORD_ENV} が設定されていません。"
                       "password_setup.bat で設定し、アプリを開き直してください"
                       + ("（config_local.py の ENV_FILE にも見つかりません）" if getattr(config, "ENV_FILE", None) else ""))
    return pw


def get_token() -> str:
    return _call("/token", "POST", {"APIPassword": api_password()})["Token"]


def board(token: str, symbol: str) -> dict:
    return _call(f"/board/{symbol}@{config.EXCHANGE}", token=token)


def unregister_all(token: str) -> None:
    _call("/unregister/all", "PUT", token=token)


def send_order(token: str, symbol: str, side: str, qty: int) -> dict:
    """翌営業日の寄り付きの成行（寄成・前場）で現物の注文を出す。side は "買い" / "売り"。

    ★実発注。呼び出し側（paper.py）が ORDER_MODE == "live" のときだけ呼ぶ。
    """
    # 仕様書 v1.5（docs/kabu_STATION_API.yaml の RequestSendOrder）に注文パスワードの項目は無い。
    # もし発注時に「Password が必要」というエラーが返ったら、docs/ の仕様書を取り直して確認する。
    body = {
        "Symbol": symbol,
        "Exchange": config.ORDER_EXCHANGE,          # 9=SOR（東証=1 を指定すると 100378 で拒否される。2026-09-03 実測）
        "SecurityType": 1,                          # 株式
        "Side": "2" if side == "買い" else "1",      # 2=買 / 1=売
        "CashMargin": 1,                            # 現物
        "DelivType": 2 if side == "買い" else 0,     # 現物買=お預り金 / 現物売=指定なし
        "FundType": "AA" if side == "買い" else "  ",  # 現物買=信用代用 / 現物売=半角スペース2つ（仕様書どおり）
        "AccountType": config.ACCOUNT_TYPE,
        "Qty": int(qty),
        "FrontOrderType": 13,                       # 寄成（前場）
        "Price": 0,                                 # 成行は 0
        "ExpireDay": 0,                             # 「本日」＝引け後なら翌取引所営業日
    }
    return _call("/sendorder", "POST", body, token=token, once=True)   # 再送しない（二重注文の防止）


def cancel_order(token: str, order_id: str) -> dict:
    """注文を取り消す（仕様書 RequestCancelOrder。必要なのは OrderId だけ）。"""
    return _call("/cancelorder", "PUT", {"OrderId": order_id}, token=token)


def positions(token: str, product: int = 1) -> list:
    """残高照会（/positions）。product: 1=現物。読み取りだけで、注文は出さない。"""
    rows = _call(f"/positions?product={product}", token=token)
    return rows if isinstance(rows, list) else []


def holdings(token: str) -> dict:
    """現物の保有数量 {銘柄コード: 株数}。config.ACCOUNT_TYPE の口座の、買い建玉（Side "2"）の残数量（LeavesQty）の合計。"""
    out = {}
    for r in positions(token, 1):
        if r.get("AccountType") not in (None, config.ACCOUNT_TYPE) or str(r.get("Side")) != "2":
            continue
        code = str(r.get("Symbol") or "")
        if code:
            out[code] = out.get(code, 0) + int(r.get("LeavesQty") or 0)
    return out


STATE_NAMES = {1: "待機", 2: "処理中", 3: "処理済（発注済）", 4: "訂正取消送信中",
               5: "終了（取消済・全約定・失効・エラーのどれか）"}


def order_status(token: str, order_id: str) -> dict:
    """注文約定照会（/orders?id=）で1件だけ引く。見つからなければ {}。

    返り値の見方: State（STATE_NAMES）／OrderQty 注文数量／CumQty 約定数量。
    """
    rows = _call(f"/orders?id={order_id}", token=token)
    for r in rows if isinstance(rows, list) else []:
        if str(r.get("ID", "")).lower() == order_id.lower():
            return r
    return {}


def describe_order(r: dict) -> str:
    if not r:
        return "注文約定照会に見当たりません（反映まで数秒かかることがあります）"
    st = r.get("State")
    return (f"状態: {st} {STATE_NAMES.get(st, '')} / 注文 {r.get('OrderQty', '?')} 株 / 約定 {r.get('CumQty', 0)} 株"
            f"（{r.get('SymbolName', '')} {r.get('ExchangeName', '')}）")


def check_connection() -> str:
    """接続確認。成功なら説明文を返し、失敗なら ApiError。"""
    get_token()
    return "接続OK（トークンを取得できました）。APIは待ち受け中です"
