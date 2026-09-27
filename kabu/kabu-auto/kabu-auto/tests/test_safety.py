# -*- coding: utf-8 -*-
"""発注まわりの安全策のテスト（kabuステーションには一切つながない）。

実行:  py -m unittest discover -s tests -v      （このフォルダ = kabu-auto で）
"""
import datetime as dt
import shutil
import socket
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config                                   # noqa: E402
from kabu_auto import api, data, paper, strategy  # noqa: E402

# 5日/25日クロスで、最終日に「買い」が出る終値の並び（下の test_fixture で確かめる）
CROSS = [100.0] * 25 + [90.0] * 3 + [140.0]


def weekdays(n: int, start: str = "2026-06-01") -> list:
    d, out = dt.date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(f"{d:%Y-%m-%d}")
        d += dt.timedelta(days=1)
    return out


def write_csv(code: str, closes: list) -> list:
    dates = weekdays(len(closes))
    data.save(code, [{"Date": d, "Open": c, "High": c, "Low": c, "Close": c, "Volume": 1000} for d, c in zip(dates, closes)])
    return dates


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patches = [
            mock.patch.object(config, "STATE_FILE", self.tmp / "state" / "account.json"),
            mock.patch.object(config, "LOG_DIR", self.tmp / "logs"),
            mock.patch.object(config, "DATA_DIR", self.tmp / "daily"),
            mock.patch.object(config, "HOLIDAYS_FILE", self.tmp / "holidays.txt"),
            mock.patch.object(config, "ORDER_MODE", "live"),
            mock.patch.object(config, "DAILY_ORDER_LIMIT", 3),
            mock.patch.object(config, "SYMBOLS", ["1111", "2222"]),
            mock.patch("builtins.print"),
        ]
        for p in self.patches:
            p.start()
        (self.tmp / "holidays.txt").write_text("# テスト用\n2025-01-13\n2026-01-12\n2027-01-11\n", encoding="utf-8")
        self.addCleanup(lambda: [p.stop() for p in self.patches])
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def pending(self, orders: list, d: str):
        st = paper.load()
        st["pending"] = [{"reason": "test", "for_date": d, **o} for o in orders]
        paper.save(st)


class TestFixture(Base):
    def test_fixture(self):
        dates = weekdays(len(CROSS))
        self.assertEqual(strategy.latest_signal(dates, CROSS), "買い")


class TestMorning(Base):
    def setUp(self):
        super().setUp()
        self.d = "2026-07-01"

    def test_二重に出さない(self):
        self.pending([{"code": "1111", "side": "買い", "qty": 100}], self.d)
        send = mock.Mock(return_value={"OrderId": "A1"})
        paper.morning(self.d, send)
        paper.morning(self.d, send)          # 朝のボタンをもう一度押した
        self.assertEqual(send.call_count, 1)
        self.assertEqual(paper.load()["pending"][0]["order_id"], "A1")

    def test_売りを先に出す_上限で買いが押し出される(self):
        self.pending([{"code": "1", "side": "買い", "qty": 100}, {"code": "2", "side": "買い", "qty": 100},
                      {"code": "3", "side": "買い", "qty": 100}, {"code": "4", "side": "売り", "qty": 100}], self.d)
        sent = []
        paper.morning(self.d, lambda c, s, q: sent.append((c, s)) or {"OrderId": "X" + c})
        self.assertEqual(sent[0], ("4", "売り"))
        self.assertEqual(len(sent), 3)
        self.assertNotIn(("3", "買い"), sent)

    def test_確実な失敗は再送できて_上限に数えない(self):
        self.pending([{"code": "1111", "side": "買い", "qty": 100}], self.d)
        paper.morning(self.d, mock.Mock(side_effect=api.ApiError("HTTP 400 / API 100378")))
        o = paper.load()["pending"][0]
        self.assertIn("send_error", o)
        self.assertNotIn("order_id", o)
        send = mock.Mock(return_value={"OrderId": "A2"})
        paper.morning(self.d, send)          # 原因を直して、もう一度
        self.assertEqual(send.call_count, 1)

    def test_結果不明は再送しない(self):
        self.pending([{"code": "1111", "side": "買い", "qty": 100}], self.d)
        paper.morning(self.d, mock.Mock(side_effect=api.OrderUncertain("応答が届きません")))
        send = mock.Mock(return_value={"OrderId": "A3"})
        paper.morning(self.d, send)
        self.assertEqual(send.call_count, 0)
        self.assertEqual(paper.load()["orders"][0]["status"], "uncertain")

    def test_注文IDが無い応答は結果不明として扱う(self):
        self.pending([{"code": "1111", "side": "買い", "qty": 100}], self.d)
        paper.morning(self.d, mock.Mock(return_value={"Result": 0}))
        self.assertTrue(paper.load()["pending"][0]["uncertain"])

    def test_ペーパーは送らない(self):
        self.pending([{"code": "1111", "side": "買い", "qty": 100}], self.d)
        send = mock.Mock()
        with mock.patch.object(config, "ORDER_MODE", "paper"):
            paper.morning(self.d, send)
        send.assert_not_called()


class TestFill(Base):
    """引け後の記帳。実発注モードでは、実際に出せた注文だけを約定扱いにする。"""

    def setUp(self):
        super().setUp()
        self.dates = write_csv("1111", CROSS)
        self.d = self.dates[-1]

    def fill(self, status_func=None):
        st = paper.load()
        filled = paper.fill_pending(st, self.d, status_func)
        paper.save(st)
        return filled, paper.load()

    def test_発注していない注文は約定扱いにしない(self):
        self.pending([{"code": "1111", "side": "買い", "qty": 100}], self.d)      # order_id なし = 失敗か上限超過
        filled, st = self.fill()
        self.assertEqual(filled, [])
        self.assertEqual(st["positions"], {})
        self.assertEqual(len(st["unfilled"]), 1)
        self.assertEqual(st["pending"], [])

    def test_結果不明も約定扱いにしない(self):
        self.pending([{"code": "1111", "side": "買い", "qty": 100, "uncertain": True}], self.d)
        filled, st = self.fill()
        self.assertEqual((filled, st["positions"]), ([], {}))
        self.assertIn("不明", st["unfilled"][0]["reason"])

    def test_約定0株で終了なら記帳しない(self):
        self.pending([{"code": "1111", "side": "買い", "qty": 100, "order_id": "A1"}], self.d)
        filled, st = self.fill(lambda oid: {"State": 5, "OrderQty": 100, "CumQty": 0})
        self.assertEqual((filled, st["positions"]), ([], {}))
        self.assertEqual(len(st["unfilled"]), 1)

    def test_一部約定は約定した数量だけ記帳する(self):
        self.pending([{"code": "1111", "side": "買い", "qty": 100, "order_id": "A1"}], self.d)
        filled, st = self.fill(lambda oid: {"State": 5, "OrderQty": 100, "CumQty": 40})
        self.assertEqual(st["positions"]["1111"]["qty"], 40)
        self.assertTrue(filled[0]["verified"])

    def test_全部約定(self):
        self.pending([{"code": "1111", "side": "買い", "qty": 100, "order_id": "A1"}], self.d)
        filled, st = self.fill(lambda oid: {"State": 5, "OrderQty": 100, "CumQty": 100})
        self.assertEqual(st["positions"]["1111"]["qty"], 100)

    def test_照会できないときは見積もりで記帳して_未確認と印を付ける(self):
        self.pending([{"code": "1111", "side": "買い", "qty": 100, "order_id": "A1"}], self.d)

        def boom(oid):
            raise api.ApiError("接続できません")
        filled, st = self.fill(boom)
        self.assertEqual(st["positions"]["1111"]["qty"], 100)
        self.assertIs(filled[0]["verified"], False)

    def test_売りの一部約定は建玉を減らすだけ(self):
        st = paper.load()
        st["positions"]["1111"] = {"qty": 100, "entry_date": "2026-06-01", "entry_px": 100.0}
        paper.save(st)
        self.pending([{"code": "1111", "side": "売り", "qty": 100, "order_id": "A1"}], self.d)
        filled, st = self.fill(lambda oid: {"State": 5, "OrderQty": 100, "CumQty": 30})
        self.assertEqual(st["positions"]["1111"]["qty"], 70)

    def test_ペーパーは今まで通り全部約定扱い(self):
        self.pending([{"code": "1111", "side": "買い", "qty": 100}], self.d)
        with mock.patch.object(config, "ORDER_MODE", "paper"):
            filled, st = self.fill()
        self.assertEqual(st["positions"]["1111"]["qty"], 100)
        self.assertEqual(st["unfilled"], [])


class TestEveningRerun(Base):
    def test_取れなかった銘柄だけ再判定できる(self):
        with mock.patch.object(config, "ORDER_MODE", "paper"):
            dates = write_csv("1111", CROSS)
            write_csv("2222", CROSS[:-1])                 # 2222 は最終日の終値が取れなかった
            d = dates[-1]
            st = paper.evening(d)
            self.assertEqual(st["days"][d]["skipped"], ["2222"])
            self.assertEqual([o["code"] for o in st["pending"]], ["1111"])

            paper.evening(d)                              # データが取れないまま再実行 → 増えない・壊れない
            self.assertEqual([o["code"] for o in paper.load()["pending"]], ["1111"])

            write_csv("2222", CROSS)                      # 取り直せた
            st = paper.evening(d)
            self.assertNotIn("skipped", st["days"][d])
            self.assertEqual(sorted(o["code"] for o in st["pending"]), ["1111", "2222"])   # 1111 は二重にならない

            st = paper.evening(d)                         # 完了後は今まで通り「処理済み」
            self.assertEqual(len(st["pending"]), 2)


class TestApiOnce(unittest.TestCase):
    """注文は再送しない（応答が届かなかっただけで受理済み、ということがあるため）。"""

    def setUp(self):
        for p in (mock.patch.object(api.time, "sleep"), mock.patch.object(api, "_throttle"),
                  mock.patch.object(config, "MAX_RETRIES", 3)):
            p.start()
            self.addCleanup(p.stop)

    def test_タイムアウトは1回だけ送り_結果不明(self):
        with mock.patch.object(api.urllib.request, "urlopen", side_effect=socket.timeout("timed out")) as m:
            with self.assertRaises(api.OrderUncertain):
                api.send_order("tok", "7203", "買い", 100)
        self.assertEqual(m.call_count, 1)

    def test_URLErrorのタイムアウトも結果不明(self):
        with mock.patch.object(api.urllib.request, "urlopen", side_effect=urllib.error.URLError(socket.timeout("t"))) as m:
            with self.assertRaises(api.OrderUncertain):
                api.send_order("tok", "7203", "買い", 100)
        self.assertEqual(m.call_count, 1)

    def test_接続拒否は届いていないので確実な失敗(self):
        with mock.patch.object(api.urllib.request, "urlopen", side_effect=urllib.error.URLError(ConnectionRefusedError())):
            with self.assertRaises(api.ApiError) as cm:
                api.send_order("tok", "7203", "買い", 100)
        self.assertNotIsInstance(cm.exception, api.OrderUncertain)

    def _http_error(self, code, body):
        import io
        return urllib.error.HTTPError("http://x", code, "err", {}, io.BytesIO(body))

    def test_コード付きの拒否は確実な失敗_5xxコード無しは結果不明(self):
        e1 = self._http_error(500, b'{"Code": 100378, "Message": "x"}')
        with mock.patch.object(api.urllib.request, "urlopen", side_effect=e1) as m:
            with self.assertRaises(api.ApiError) as cm:
                api.send_order("tok", "7203", "買い", 100)
        self.assertNotIsInstance(cm.exception, api.OrderUncertain)
        self.assertEqual(m.call_count, 1)
        e2 = self._http_error(502, b"Bad Gateway")
        with mock.patch.object(api.urllib.request, "urlopen", side_effect=e2) as m:
            with self.assertRaises(api.OrderUncertain):
                api.send_order("tok", "7203", "買い", 100)
        self.assertEqual(m.call_count, 1)

    def test_情報系は今まで通りリトライする(self):
        with mock.patch.object(api.urllib.request, "urlopen", side_effect=socket.timeout("t")) as m:
            with self.assertRaises(api.ApiError):
                api.board("tok", "7203")
        self.assertEqual(m.call_count, 4)      # 1回 + MAX_RETRIES(3)


if __name__ == "__main__":
    unittest.main()
