# -*- coding: utf-8 -*-
"""ブラウザで操作する画面を開く。このPCだけで開ける（127.0.0.1）。

使い方:  py run_gui.py          → ブラウザが開く。閉じるときはこの窓で Ctrl+C
         py run_gui.py --port 9000 --no-browser
実発注はこの画面からはできない（見る・検証する・ペーパーまで）。詳しくは kabu_auto/webui.py。
"""
import argparse
import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from kabu_auto import webui  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    srv = None
    for port in range(a.port, a.port + 10):
        try:
            srv = webui.make_server(port)
            break
        except OSError:
            continue
    if srv is None:
        print(f"NG: ポート {a.port}〜{a.port + 9} がすべて使われています。--port で別の番号を指定してください。")
        return 1
    url = f"http://127.0.0.1:{srv.server_port}/"
    print(f"kabu-auto の画面: {url}")
    print("このPCのブラウザでだけ開けます。終わるときは、この窓で Ctrl+C を押してください。")
    if not a.no_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n終了します。")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
