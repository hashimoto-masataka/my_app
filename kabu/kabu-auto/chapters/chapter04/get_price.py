# -*- coding: utf-8 -*-
"""指定した銘柄の現在の株価を表示するスクリプト

使い方:  py get_price.py 銘柄コード
例:      py get_price.py 7203    (トヨタ自動車)

kabuステーションAPI(本番環境)を使用。取得のみで、発注は一切しない。
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = "http://localhost:18080/kabusapi"
EXCHANGE = 1  # 東証


def api_error_exit(prefix: str, e: urllib.error.HTTPError) -> None:
    detail = e.read().decode("utf-8", errors="replace")
    print(f"NG: {prefix} (HTTP {e.code})")
    print(f"    応答: {detail}")
    sys.exit(1)


def get_token(password: str) -> str:
    """APIパスワードを渡してトークンを取得する。"""
    body = json.dumps({"APIPassword": password}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/token",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return json.loads(res.read().decode("utf-8"))["Token"]
    except urllib.error.HTTPError as e:
        api_error_exit("トークンを取得できませんでした", e)


def get_board(token: str, symbol: str) -> dict:
    """時価情報(現在値など)を取得する。"""
    req = urllib.request.Request(
        f"{BASE_URL}/board/{symbol}@{EXCHANGE}",
        headers={"X-API-KEY": token},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        api_error_exit(f"銘柄 {symbol} の株価を取得できませんでした", e)


def fmt(value: float) -> str:
    """価格を読みやすく整形する(3243.0 → 3,243 / 3243.5 → 3,243.5)。"""
    if value == int(value):
        return f"{int(value):,}"
    return f"{value:,}"


def main() -> int:
    if len(sys.argv) < 2:
        print("使い方:  py get_price.py 銘柄コード")
        print("例:      py get_price.py 7203")
        return 1
    symbol = sys.argv[1]

    password = os.environ.get("KABU_API_PASSWORD")
    if not password:
        print("NG: 環境変数 KABU_API_PASSWORD が設定されていません。")
        print("    新しいウィンドウで実行し直すか、password_setup.bat で設定してください。")
        return 1

    try:
        token = get_token(password)
        board = get_board(token, symbol)
    except urllib.error.URLError as e:
        print(f"NG: kabuステーションに接続できませんでした ({e.reason})")
        print("    → kabuステーションが起動しているか確認してください。")
        return 1

    name = board.get("SymbolName", "(名称不明)")
    price = board.get("CurrentPrice")
    time_ = board.get("CurrentPriceTime", "")
    change = board.get("ChangePreviousClose")

    print(f"銘柄: {name} ({symbol})")
    if price is None:
        print("現在値: まだ値が付いていません(取引時間外などの可能性)")
    else:
        print(f"現在値: {fmt(price)} 円")
        if change is not None:
            sign = "+" if change >= 0 else ""
            print(f"前日比: {sign}{fmt(change)} 円")
        if time_:
            print(f"時刻:   {time_.replace('T', ' ').split('+')[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
