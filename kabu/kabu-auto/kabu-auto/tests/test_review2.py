# -*- coding: utf-8 -*-
"""再レビューで見つけた穴（途中停止・二重起動・期限切れ・約定0株）のテスト。

実行:  py -m unittest discover -s tests -v
"""
import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config                                   # noqa: E402
from kabu_auto import api, paper                # noqa: E402
from test_safety import CROSS, Base, write_csv  # noqa: E402


class Crash(BaseException):
    """途中で止まった（Ctrl+C・強制終了など）ことの再現。Exception ではないので、普通の except では捕まらない。"""


class TestMorningCrash(Base):
    d = "2026-07-01"

    def test_途中で止まっても送った注文は記録され_再実行で再送しない(self):
        st = paper.load()
        st["pending"] = [{"code": "1", "side": "買い", "qty": 100, "for_date": self.d, "reason": "t"},
                         {"code": "2", "side": "買い", "qty": 100, "for_date": self.d, "reason": "t"}]
        paper.save(st)
        calls = []

        def send(code, side, qty):
            calls.append(code)
            if code == "2":
                raise Crash()
            return {"OrderId": "ID" + code}
        with self.assertRaises(Crash):
            paper.morning(self.d, send)
        saved = {o["code"]: o for o in paper.load()["pending"]}
        self.assertEqual(saved["1"]["order_id"], "ID1")          # 1件目は送信済みとして残っている

        calls.clear()
        paper.morning(self.d, lambda c, s, q: calls.append(c) or {"OrderId": "ID" + c})
        self.assertNotIn("1", calls)                              # 再実行で1件目は再送しない


class TestLock(Base):
    d = "2026-07-01"

    def lock_path(self):
        return config.STATE_FILE.parent / "account.lock"

    def test_実行中は別の実行が止まる(self):
        st = paper.load()
        st["pending"] = [{"code": "1", "side": "買い", "qty": 100, "for_date": self.d, "reason": "t"}]
        paper.save(st)
        send = mock.Mock(return_value={"OrderId": "A"})
        with paper._lock():                                       # 1つ目の実行が動いている
            self.assertEqual(paper.morning(self.d, send), [])     # 2つ目（朝のボタンの2度押し）は止まる
        send.assert_not_called()
        self.assertFalse(self.lock_path().exists())               # 終わればロックは消える

    def test_ロックは正常終了でも例外でも消える(self):
        with paper._lock():
            self.assertTrue(self.lock_path().exists())
        self.assertFalse(self.lock_path().exists())
        with self.assertRaises(RuntimeError):
            with paper._lock():
                raise RuntimeError("x")
        self.assertFalse(self.lock_path().exists())

    def test_古いロックは奪える(self):
        self.lock_path().parent.mkdir(parents=True, exist_ok=True)
        self.lock_path().write_text("old", encoding="utf-8")
        old = time.time() - paper.LOCK_STALE_SEC - 5
        os.utime(self.lock_path(), (old, old))
        with paper._lock():
            pass                                                  # 例外なく取れる

    def test_新しいロックは奪えない(self):
        self.lock_path().parent.mkdir(parents=True, exist_ok=True)
        self.lock_path().write_text("now", encoding="utf-8")
        with self.assertRaises(paper.Busy):
            with paper._lock():
                pass

    def test_引け後も二重に走らない(self):
        dates = write_csv("1111", CROSS)
        with mock.patch.object(config, "SYMBOLS", ["1111"]), mock.patch.object(config, "ORDER_MODE", "paper"):
            with paper._lock():
                st = paper.evening(dates[-1])
            self.assertNotIn(dates[-1], st["days"])               # 止まって、何も進めていない
            st = paper.evening(dates[-1])
            self.assertIn(dates[-1], st["days"])


class TestFillZero(Base):
    def setUp(self):
        super().setUp()
        self.dates = write_csv("1111", CROSS)
        self.d = self.dates[-1]

    def test_約定0株は_終了していなくても記帳しない(self):
        st = paper.load()
        st["pending"] = [{"code": "1111", "side": "買い", "qty": 100, "for_date": self.d, "reason": "t", "order_id": "A1"}]
        paper.save(st)
        st = paper.load()
        filled = paper.fill_pending(st, self.d, lambda oid: {"State": 3, "OrderQty": 100, "CumQty": 0})   # 処理済み・未約定
        self.assertEqual((filled, st["positions"]), ([], {}))
        self.assertIn("約定0株", st["unfilled"][0]["reason"])


class TestExpire(Base):
    def test_期限切れの注文は待ち一覧に残さない(self):
        dates = write_csv("1111", CROSS)
        d = dates[-1]
        st = paper.load()
        st["pending"] = [{"code": "1111", "side": "買い", "qty": 100, "for_date": dates[-5], "reason": "old"},
                         {"code": "2222", "side": "買い", "qty": 100, "for_date": "2099-01-01", "reason": "future"}]
        paper.save(st)
        with mock.patch.object(config, "SYMBOLS", ["1111"]), mock.patch.object(config, "ORDER_MODE", "paper"):
            st = paper.evening(d)
        self.assertEqual([o["reason"] for o in st["pending"] if o["reason"] in ("old", "future")], ["future"])
        self.assertEqual(st["unfilled"][0]["reason"], f"期限切れ（{dates[-5]} 用）")


class TestNoTokenLeak(unittest.TestCase):
    def test_接続確認は_トークンの文字を出さない(self):
        with mock.patch.object(api, "get_token", return_value="SECRETTOKEN123"):
            self.assertNotIn("SECR", api.check_connection())


if __name__ == "__main__":
    unittest.main()
