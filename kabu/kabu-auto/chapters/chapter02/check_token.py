# -*- coding: utf-8 -*-
"""kabuステーションAPI 接続確認スクリプト

本番環境(ポート18080)のトークン発行エンドポイントを呼び、
接続できるか・APIパスワードが正しいかを確認する。
標準ライブラリのみ使用(追加インストール不要)。
"""
import json
import os
import sys
import urllib.error
import urllib.request

URL = "http://localhost:18080/kabusapi/token"


def main() -> int:
    password = os.environ.get("KABU_API_PASSWORD")
    if not password:
        print("NG: 環境変数 KABU_API_PASSWORD が設定されていません。")
        print("    設定後、ターミナルを開き直してから再実行してください。")
        return 1

    body = json.dumps({"APIPassword": password}).encode("utf-8")
    req = urllib.request.Request(
        URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            data = json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        print(f"NG: APIがエラーを返しました (HTTP {e.code})")
        print(f"    応答: {detail}")
        if e.code == 401:
            print("    → APIパスワードが違う可能性があります。")
        return 1
    except urllib.error.URLError as e:
        print(f"NG: kabuステーションに接続できませんでした ({e.reason})")
        print("    → kabuステーションが起動しているか、ログイン済みかを確認してください。")
        print("    → 設定画面でAPIの利用が有効になっているかも確認してください。")
        return 1

    token = data.get("Token", "")
    if not token:
        print(f"NG: 応答にトークンが含まれていません: {data}")
        return 1

    # トークンは秘密情報なので先頭4文字だけ表示する
    print("OK: トークンを取得できました。接続は正常です。")
    print(f"    Token(先頭のみ): {token[:4]}... (全{len(token)}文字)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
