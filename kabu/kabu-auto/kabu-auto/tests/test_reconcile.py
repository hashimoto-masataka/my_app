# -*- coding: utf-8 -*-
"""証券会社の残高との突き合わせ（読み取りだけ。注文は出さない）のテスト。

実行:  py -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config                                   # noqa: E402
from kabu_auto import api, paper                # noqa: E402
from test_safety import CROSS, Base, write_csv  # noqa: E402


class TestHoldings(unittest.TestCase):
    def rows(self):
        return [
            {"Symbol": "7203", "AccountType": 4, "Side": "2", "LeavesQty": 100},
            {"Symbol": "7203", "AccountType": 4, "Side": "2", "LeavesQty": 200.0},   # 同じ銘柄の別ロット → 合計
            {"Symbol": "6758", "AccountType": 2, "Side": "2", "LeavesQty": 100},     # 別の口座区分 → 無視
            {"Symbol": "9984", "AccountType": 4, "Side": "1", "LeavesQty": 100},     # 売建（信用など）→ 無視
            {"Symbol": "9432", "AccountType": 4, "Side": "2", "LeavesQty": None},
        ]

    def test_口座区分と売買区分で絞って合計する(self):
        with mock.patch.object(config, "ACCOUNT_TYPE", 4), mock.patch.object(api, "_call", return_value=self.rows()) as m:
            self.assertEqual(api.holdings("tok"), {"7203": 300, "9432": 0})
        self.assertEqual(m.call_args[0][0], "/positions?product=1")          # 現物だけ・GET（読み取り）
        self.assertEqual(m.call_args[1].get("method", "GET"), "GET")

    def test_保有なしは空(self):
        with mock.patch.object(api, "_call", return_value=[]):
            self.assertEqual(api.holdings("tok"), {})
        with mock.patch.object(api, "_call", return_value={"unexpected": 1}):
            self.assertEqual(api.holdings("tok"), {})


class TestMorningHoldings(Base):
    def setUp(self):
        super().setUp()
        self.d = "2026-07-01"

    def pend(self, *orders):
        st = paper.load()
        st["pending"] = [{"reason": "t", "for_date": self.d, **o} for o in orders]
        paper.save(st)

    def test_すでに保有している銘柄は買わない(self):
        self.pend({"code": "1111", "side": "買い", "qty": 100})
        send = mock.Mock(return_value={"OrderId": "A1"})
        self.assertEqual(paper.morning(self.d, send, holdings={"1111": 100}), [])
        send.assert_not_called()
        self.assertIn("見送り", paper.load()["pending"][0]["send_error"])

    def test_保有がなければ買う(self):
        self.pend({"code": "1111", "side": "買い", "qty": 100})
        send = mock.Mock(return_value={"OrderId": "A1"})
        paper.morning(self.d, send, holdings={"2222": 500})                  # 別の銘柄の保有は関係ない
        self.assertEqual(send.call_count, 1)

    def test_保有が足りない売りは出さない(self):
        self.pend({"code": "1111", "side": "売り", "qty": 300})
        send = mock.Mock(return_value={"OrderId": "A1"})
        paper.morning(self.d, send, holdings={"1111": 100})
        send.assert_not_called()

    def test_足りている売りは出す(self):
        self.pend({"code": "1111", "side": "売り", "qty": 300})
        send = mock.Mock(return_value={"OrderId": "A1"})
        paper.morning(self.d, send, holdings={"1111": 300})
        self.assertEqual(send.call_count, 1)

    def test_見送った分は上限に数えない(self):
        with mock.patch.object(config, "DAILY_ORDER_LIMIT", 1):
            self.pend({"code": "1111", "side": "買い", "qty": 100}, {"code": "2222", "side": "買い", "qty": 100})
            send = mock.Mock(return_value={"OrderId": "A1"})
            paper.morning(self.d, send, holdings={"1111": 100})
        self.assertEqual([c.args[0] for c in send.call_args_list], ["2222"])   # 1111 は見送り、2222 が上限の1件目

    def test_突き合わせなし_holdingsを渡さなければ従来どおり(self):
        self.pend({"code": "1111", "side": "買い", "qty": 100})
        send = mock.Mock(return_value={"OrderId": "A1"})
        paper.morning(self.d, send)
        self.assertEqual(send.call_count, 1)

    def test_見送った買いは引け後に約定扱いにならない(self):
        dates = write_csv("1111", CROSS)
        d = dates[-1]
        st = paper.load()
        st["pending"] = [{"code": "1111", "side": "買い", "qty": 100, "for_date": d, "reason": "t"}]
        paper.save(st)
        paper.morning(d, mock.Mock(return_value={"OrderId": "X"}), holdings={"1111": 100})
        st = paper.load()
        paper.fill_pending(st, d)
        self.assertEqual(st["positions"], {})
        self.assertEqual(len(st["unfilled"]), 1)


class TestReconcile(Base):
    def test_食い違いだけを返す(self):
        st = paper.load()
        st["positions"] = {"1111": {"qty": 100, "entry_date": "x", "entry_px": 1.0},
                           "2222": {"qty": 100, "entry_date": "x", "entry_px": 1.0}}
        with mock.patch.object(config, "SYMBOLS", ["1111", "2222", "3333"]):
            diffs = paper.reconcile(st, {"1111": 100, "2222": 200, "3333": 100, "9999": 500})
        self.assertEqual(len(diffs), 2)
        self.assertTrue(any("2222" in x and "帳簿 100" in x and "証券会社 200" in x for x in diffs))
        self.assertTrue(any("3333" in x and "帳簿 0" in x for x in diffs))
        self.assertFalse(any("9999" in x for x in diffs))                    # 対象外の銘柄の保有は無視

    def test_一致なら空(self):
        st = paper.load()
        st["positions"] = {"1111": {"qty": 100, "entry_date": "x", "entry_px": 1.0}}
        with mock.patch.object(config, "SYMBOLS", ["1111"]):
            self.assertEqual(paper.reconcile(st, {"1111": 100}), [])

    def test_引け後の突き合わせは何も変えず_失敗しても止まらない(self):
        dates = write_csv("1111", CROSS)
        d = dates[-1]
        with mock.patch.object(config, "SYMBOLS", ["1111"]):
            def boom():
                raise api.ApiError("接続できません")
            st = paper.evening(d, None, boom)                                # 例外を出さずに最後まで進む
        self.assertIn(d, st["days"])

    def test_引け後の突き合わせの結果がログに出る(self):
        dates = write_csv("1111", CROSS)
        d = dates[-1]
        logs = []
        with mock.patch.object(config, "SYMBOLS", ["1111"]), mock.patch.object(paper, "log", side_effect=logs.append):
            paper.evening(d, None, lambda: {"1111": 300})
        self.assertTrue(any("食い違" in x for x in logs))


if __name__ == "__main__":
    unittest.main()
