# -*- coding: utf-8 -*-
"""複数銘柄の株価をまとめて取得して一覧表示するスクリプト

使い方:  py get_prices.py                    (主要10銘柄)
         py get_prices.py 7203 9984 6758     (銘柄コードを好きなだけ指定)

kabuステーションAPI(本番環境)を使用。取得のみで、発注は一切しない。

APIの制限「情報系リクエストは1秒あたり10件程度まで」に合わせて、
リクエストの間に待ち時間を入れている。一時的なエラーは自動でリトライする。
"""
import json
import os
import sys
import time
import unicodedata
import urllib.error
import urllib.request

BASE_URL = "http://localhost:18080/kabusapi"
EXCHANGE = 1  # 東証

# 1秒あたり10件までの制限に対し、余裕を見て1件あたり0.15秒空ける(約6.7件/秒)
REQUEST_INTERVAL = 0.15

# リトライ設定: 一時的なエラーのとき、1秒→2秒→4秒と待ちを伸ばして最大3回やり直す
MAX_RETRIES = 3
RETRY_WAIT = 1.0

# 引数なしのときに使う主要10銘柄
DEFAULT_SYMBOLS = [
    "7203",  # トヨタ自動車
    "6758",  # ソニーグループ
    "9984",  # ソフトバンクグループ
    "8306",  # 三菱UFJフィナンシャル・グループ
    "9432",  # NTT
    "6861",  # キーエンス
    "8035",  # 東京エレクトロン
    "9983",  # ファーストリテイリング
    "4063",  # 信越化学工業
    "7974",  # 任天堂
]


def request_with_retry(req: urllib.request.Request) -> dict:
    """APIを呼ぶ。一時的なエラー(429/5xx/接続断)なら待ってやり直す。

    待っても直らないエラー(400/401など)はそのまま例外を投げる。
    """
    last_error = None
    for attempt in range(1 + MAX_RETRIES):
        if attempt > 0:
            wait = RETRY_WAIT * (2 ** (attempt - 1))  # 1秒 → 2秒 → 4秒
            print(f"    (一時エラーのため {wait:.0f}秒待ってリトライします "
                  f"{attempt}/{MAX_RETRIES})")
            time.sleep(wait)
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                return json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                last_error = e  # 頻度制限・サーバー側の一時エラー → リトライ
                continue
            raise  # 400/401 などは待っても直らないので即エラー
        except urllib.error.URLError as e:
            last_error = e  # 接続エラー・タイムアウト → リトライ
            continue
    raise last_error


def get_token(password: str) -> str:
    body = json.dumps({"APIPassword": password}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/token",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return request_with_retry(req)["Token"]


def get_board(token: str, symbol: str) -> dict:
    req = urllib.request.Request(
        f"{BASE_URL}/board/{symbol}@{EXCHANGE}",
        headers={"X-API-KEY": token},
        method="GET",
    )
    return request_with_retry(req)


def fmt(value: float) -> str:
    """価格を読みやすく整形する(3243.0 → 3,243 / 3243.5 → 3,243.5)。"""
    if value == int(value):
        return f"{int(value):,}"
    return f"{value:,}"


def pad(text: str, width: int) -> str:
    """全角文字を2文字ぶんとして数え、指定幅まで空白を足す。"""
    visual = sum(2 if unicodedata.east_asian_width(c) in "FWA" else 1 for c in text)
    return text + " " * max(0, width - visual)


def main() -> int:
    symbols = sys.argv[1:] or DEFAULT_SYMBOLS

    password = os.environ.get("KABU_API_PASSWORD")
    if not password:
        print("NG: 環境変数 KABU_API_PASSWORD が設定されていません。")
        return 1

    try:
        token = get_token(password)
    except urllib.error.HTTPError as e:
        print(f"NG: トークンを取得できませんでした (HTTP {e.code})")
        print(f"    応答: {e.read().decode('utf-8', errors='replace')}")
        return 1
    except urllib.error.URLError as e:
        print(f"NG: kabuステーションに接続できませんでした ({e.reason})")
        print("    → kabuステーションが起動しているか確認してください。")
        return 1

    print(f"{'コード':<6} {pad('銘柄名', 24)} {'現在値':>10} {'前日比':>8}")
    print("-" * 54)

    ok = 0
    for i, symbol in enumerate(symbols):
        if i > 0:
            time.sleep(REQUEST_INTERVAL)  # 頻度制限(10件/秒)を超えないための待ち
        try:
            board = get_board(token, symbol)
        except urllib.error.HTTPError as e:
            print(f"{symbol:<6} {pad('(取得失敗 HTTP ' + str(e.code) + ')', 24)}")
            continue
        except urllib.error.URLError:
            print(f"{symbol:<6} {pad('(接続エラー)', 24)}")
            continue

        name = board.get("SymbolName", "(名称不明)")
        price = board.get("CurrentPrice")
        change = board.get("ChangePreviousClose")

        if price is None:
            print(f"{symbol:<6} {pad(name, 24)} {'値なし':>10}")
        else:
            sign = "+" if (change or 0) >= 0 else ""
            change_s = f"{sign}{fmt(change)}" if change is not None else ""
            print(f"{symbol:<6} {pad(name, 24)} {fmt(price):>10} {change_s:>8}")
        ok += 1

    print("-" * 54)
    print(f"{ok}/{len(symbols)} 銘柄を取得しました")
    return 0 if ok == len(symbols) else 1


if __name__ == "__main__":
    sys.exit(main())
