# -*- coding: utf-8 -*-
"""ブラウザ画面（webui）のテスト。127.0.0.1 の一時サーバーに本当につないで確かめる（kabuステーションにはつながない）。

実行:  py -m unittest discover -s tests -v
"""
import json
import subprocess
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config                                   # noqa: E402
from kabu_auto import data, paper, webui        # noqa: E402
from test_safety import CROSS, Base, write_csv  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class WebBase(Base):
    def setUp(self):
        super().setUp()
        patches = [mock.patch.object(config, "ORDER_MODE", "paper"), mock.patch.object(config, "SYMBOLS", ["1111", "2222"])]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.srv = webui.make_server(0, reload_config=False)        # 0 = 空いているポート
        self.port = self.srv.server_port
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def req(self, path, method="GET", body=None, headers=None, token=True, host=None):
        h = dict(headers or {})
        if token:
            h["X-Token"] = self.srv.token
        if host:
            h["Host"] = host
        r = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=body, method=method, headers=h)
        try:
            with urllib.request.urlopen(r, timeout=10) as res:
                return res.status, res.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def jreq(self, *a, **k):
        code, body = self.req(*a, **k)
        return code, json.loads(body.decode("utf-8"))

    def wait_job(self, timeout=30):
        t = time.time()
        while time.time() - t < timeout:
            j = self.srv.jobs.snapshot()
            if not j["running"]:
                return j
            time.sleep(0.05)
        self.fail("仕事が終わらない")


class TestPage(WebBase):
    def test_トップページにトークンが入る(self):
        code, body = self.req("/")
        html = body.decode("utf-8")
        self.assertEqual(code, 200)
        self.assertIn(self.srv.token, html)
        self.assertNotIn("__TOKEN__", html)

    def test_他のホスト名では開けない(self):
        code, _ = self.req("/api/state", host="evil.example.com")
        self.assertEqual(code, 403)
        code, _ = self.req("/api/state", host=f"127.0.0.1:{self.port}")
        self.assertEqual(code, 200)

    def test_別のサイトからの操作は受けない(self):
        code, _ = self.req("/api/run", "POST", b"{}", {"Origin": "http://evil.example.com"})
        self.assertEqual(code, 403)

    def test_操作にはトークンが要る(self):
        code, _ = self.req("/api/run", "POST", b'{"name":"audit"}', token=False)
        self.assertEqual(code, 403)
        code, _ = self.req("/api/run", "POST", b'{"name":"audit"}', {"X-Token": "wrong"}, token=False)
        self.assertEqual(code, 403)


class TestState(WebBase):
    def test_状態の形(self):
        write_csv("1111", CROSS)
        code, s = self.jreq("/api/state")
        self.assertEqual(code, 200)
        self.assertEqual(s["mode"], "paper")
        self.assertEqual([y["code"] for y in s["symbols"]], ["1111", "2222"])
        self.assertEqual(s["symbols"][0]["signal"], "買い")
        self.assertEqual(s["symbols"][1]["rows"], 0)
        self.assertEqual(s["ledger"]["positions"], [])
        self.assertIn("settings", s)

    def test_建玉に含み損益が出る(self):
        dates = write_csv("1111", CROSS)
        st = paper.load()
        st["positions"]["1111"] = {"qty": 100, "entry_date": dates[0], "entry_px": 100.0}
        paper.save(st)
        _, s = self.jreq("/api/state")
        p = s["ledger"]["positions"][0]
        self.assertEqual(p["last_close"], 140.0)
        self.assertEqual(p["unrealized"], 4000.0)

    def test_ログの末尾が出る(self):
        paper.log("テストのログ")
        _, s = self.jreq("/api/state")
        self.assertTrue(any("テストのログ" in x for x in s["log"]))


class TestChart(WebBase):
    def test_チャートのデータ(self):
        write_csv("1111", CROSS)
        code, c = self.jreq("/api/chart?code=1111")
        self.assertEqual(code, 200)
        self.assertEqual(len(c["dates"]), len(CROSS))
        self.assertEqual(c["signals"][-1]["side"], "買い")
        self.assertIsNone(c["ma_l"][0])                     # 長期平均が出ない最初の期間は null

    def test_不正な銘柄コード(self):
        code, _ = self.jreq("/api/chart?code=../etc")
        self.assertEqual(code, 400)


class TestRun(WebBase):
    def test_未知の操作は動かさない(self):
        code, r = self.jreq("/api/run", "POST", json.dumps({"name": "send_order"}).encode())
        self.assertEqual(code, 400)
        self.assertFalse(self.srv.jobs.running())

    def test_実発注モードではペーパー操作を断る(self):
        with mock.patch.object(config, "ORDER_MODE", "live"):
            for name in ("collect", "collect_nofetch", "morning"):
                code, r = self.jreq("/api/run", "POST", json.dumps({"name": name}).encode())
                self.assertEqual(code, 403, name)
                self.assertIn("実発注モード", r["error"])
        self.assertIsNone(self.srv.jobs.job)

    def test_実発注モードでも検証は使える(self):
        write_csv("1111", CROSS)
        with mock.patch.object(config, "ORDER_MODE", "live"), mock.patch.object(webui, "build_argv", return_value=[sys.executable, "-c", "print('ok')"]):
            code, _ = self.jreq("/api/run", "POST", json.dumps({"name": "audit"}).encode())
        self.assertEqual(code, 200)
        self.wait_job()

    def test_バックテストは銘柄コードが要る(self):
        code, _ = self.jreq("/api/run", "POST", json.dumps({"name": "backtest", "code": "x y"}).encode())
        self.assertEqual(code, 400)

    def test_仕事の出力を貯める_1つずつしか動かない(self):
        argv = [sys.executable, "-c", "import time;print('はじまり');time.sleep(0.6);print('おわり')"]
        with mock.patch.object(webui, "build_argv", return_value=argv):
            code, _ = self.jreq("/api/run", "POST", json.dumps({"name": "audit"}).encode())
            self.assertEqual(code, 200)
            code2, r2 = self.jreq("/api/run", "POST", json.dumps({"name": "audit"}).encode())
            self.assertEqual(code2, 409)                                     # 実行中は2つ目を断る
        j = self.wait_job()
        self.assertEqual(j["rc"], 0)
        self.assertEqual(j["lines"], ["はじまり", "おわり"])

    def test_引数の組み立て_ペーパー操作は_liveを指定しない(self):
        for name in ("collect", "collect_nofetch", "morning", "audit"):
            argv = webui.build_argv(name, {"code": "7203"})
            self.assertNotIn("live", argv)
            self.assertNotIn("start.py", " ".join(argv))
        argv = webui.build_argv("backtest", {"code": "7203", "walk": True, "grid": True})
        self.assertEqual(argv[-4:], ["run_backtest.py", "7203", "--grid", "--walk"][-4:])

    def test_実際にデータ点検を別プロセスで動かせる(self):
        # 一時フォルダの config は別プロセスに渡らないので、点検スクリプトを直接（本物のconfig）で --help だけ動かして起動確認する
        with mock.patch.object(webui, "build_argv", return_value=[sys.executable, "-X", "utf8", str(ROOT / "run_backtest.py"), "--help"]):
            code, _ = self.jreq("/api/run", "POST", json.dumps({"name": "audit"}).encode())
        self.assertEqual(code, 200)
        j = self.wait_job()
        self.assertEqual(j["rc"], 0)
        self.assertTrue(any("usage" in x for x in j["lines"]))


class TestImport(WebBase):
    def test_UTF8のCSVを取り込む(self):
        csv = "Date,Open,High,Low,Close,Volume\n2026-06-01,10,11,9,10,100\n2026-06-02,10,11,9,10.5,100\n"
        code, r = self.jreq("/api/import?code=1111", "POST", csv.encode("utf-8"))
        self.assertEqual(code, 200)
        self.assertEqual(r["rows"], 2)
        self.assertEqual(len(data.load("1111")), 2)

    def test_ShiftJISのCSVも取り込む(self):
        csv = "日付,始値,高値,安値,終値,出来高\n2026-06-01,10,11,9,10,100\n"
        # 列名が日本語で対応外のときは、分かる説明つきで断る（例外で落ちない）
        code, r = self.jreq("/api/import?code=1111", "POST", csv.encode("cp932"))
        self.assertEqual(code, 400)
        self.assertIn("終値", r["error"])

    def test_調整後の列には注意が出る(self):
        csv = "Date,AdjustmentOpen,AdjustmentHigh,AdjustmentLow,AdjustmentClose,AdjustmentVolume\n2026-06-01,10,11,9,10,100\n"
        _, r = self.jreq("/api/import?code=1111", "POST", csv.encode("utf-8"))
        self.assertIn("調整後", r["note"])

    def test_銘柄コードと空ファイルの検査(self):
        self.assertEqual(self.req("/api/import?code=../x", "POST", b"a")[0], 400)
        self.assertEqual(self.req("/api/import?code=1111", "POST", b"")[0], 400)


class TestNoOrderPath(unittest.TestCase):
    """画面のコードから、発注に行ける道が無いこと。"""

    def test_webuiは発注関数を呼ばない(self):
        for f in ("kabu_auto/webui.py", "kabu_auto/webui.html", "run_gui.py"):
            text = (ROOT / f).read_text(encoding="utf-8")
            for bad in ("send_order", "cancel_order", "sendorder", "cancelorder", "--mode live", "mode_live"):
                self.assertNotIn(bad, text, f"{f} に {bad}")

    def test_画面からの呼び出しは_liveなら断る(self):
        for script in ("run_collect.py", "run_morning.py"):
            r = subprocess.run([sys.executable, "-c",
                                "import sys,config;config.ORDER_MODE='live';sys.argv=['x'];"
                                f"import runpy;runpy.run_path('{script}', run_name='__main__')"],
                               cwd=str(ROOT), env={**__import__('os').environ, "KABU_GUI": "1", "PYTHONIOENCODING": "utf-8"},
                               capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertNotEqual(r.returncode, 0, script)
            self.assertIn("paper", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
