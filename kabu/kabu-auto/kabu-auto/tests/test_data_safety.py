# -*- coding: utf-8 -*-
"""データと休場日の安全策のテスト（板の時刻・休場日ファイル・段差）。

実行:  py -m unittest discover -s tests -v
"""
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config                                            # noqa: E402
from kabu_auto import calendar as cal, data, paper      # noqa: E402
from test_safety import CROSS, Base, weekdays, write_csv  # noqa: E402


def board(price=1000.0, t="2026-07-01T15:00:00+09:00"):
    return {"CurrentPrice": price, "CurrentPriceTime": t, "OpeningPrice": price, "HighPrice": price,
            "LowPrice": price, "TradingVolume": 1000}


class TestBoardTime(Base):
    def test_今日の時刻なら書く(self):
        msg = data.append_today("1111", "2026-07-01", board())
        self.assertIn("追記", msg)
        self.assertEqual(data.load("1111")[-1]["Date"], "2026-07-01")

    def test_前の営業日の値は書かない(self):
        msg = data.append_today("1111", "2026-07-01", board(t="2026-06-30T15:00:00+09:00"))
        self.assertIn("今日", msg)
        self.assertEqual(data.load("1111"), [])

    def test_時刻が読めない値は書かない(self):
        for t in (None, "", "15:00", "abcd"):
            self.assertIn("読めない", data.append_today("1111", "2026-07-01", board(t=t)))
        self.assertEqual(data.load("1111"), [])

    def test_休場日ファイルが無くても休場日に古い値を貯めない(self):
        # 2026-07-20 は海の日（休場）。カレンダーが知らなくても、板の時刻が 7/17 なので書かない
        self.assertFalse((self.tmp / "nope.txt").exists())
        msg = data.append_today("1111", "2026-07-20", board(t="2026-07-17T15:00:00+09:00"))
        self.assertIn("今日", msg)


class TestHolidayFile(Base):
    def test_ファイルが無いと警告(self):
        with mock.patch.object(config, "HOLIDAYS_FILE", self.tmp / "nothing.txt"):
            self.assertIn("ありません", cal.holiday_warning("2026-07-01"))

    def test_その年の分が無いと警告(self):
        self.assertEqual(cal.holiday_warning("2026-07-01"), "")
        self.assertIn("2028 年", cal.holiday_warning("2028-07-03"))

    def test_書き換えたら読み直す(self):
        f = self.tmp / "holidays.txt"
        self.assertTrue(cal.is_trading_day("2026-07-20"))
        time.sleep(0.01)
        f.write_text("2026-07-20\n", encoding="utf-8")
        import os
        os.utime(f, (time.time() + 5, time.time() + 5))
        self.assertFalse(cal.is_trading_day("2026-07-20"))

    def test_実発注は休場日ファイルが整うまで止まる(self):
        with mock.patch.object(config, "HOLIDAYS_FILE", self.tmp / "nothing.txt"):
            st = paper.load()
            st["pending"] = [{"code": "1111", "side": "買い", "qty": 100, "for_date": "2026-07-01", "reason": "t"}]
            paper.save(st)
            send = mock.Mock(return_value={"OrderId": "A1"})
            self.assertEqual(paper.morning("2026-07-01", send), [])
            send.assert_not_called()

    def test_ペーパーは止めない(self):
        with mock.patch.object(config, "HOLIDAYS_FILE", self.tmp / "nothing.txt"), \
                mock.patch.object(config, "ORDER_MODE", "paper"):
            st = paper.load()
            st["pending"] = [{"code": "1111", "side": "買い", "qty": 100, "for_date": "2026-07-01", "reason": "t"}]
            paper.save(st)
            paper.morning("2026-07-01")          # 例外なく「出したつもり」を表示するだけ


class TestJumps(Base):
    def rows(self, closes):
        return [{"Date": d, "Close": c} for d, c in zip(weekdays(len(closes)), closes)]

    def test_段差の検出(self):
        j = data.jumps(self.rows([100, 101, 50, 51, 160]))
        self.assertEqual([round(r, 2) for _, r in j], [0.5, 3.14])

    def test_通常の値動きは段差ではない(self):
        self.assertEqual(data.jumps(self.rows([100, 130, 90, 120])), [])       # +30%・-30% までは正常

    def test_直近だけ見る(self):
        closes = [100.0] * 5 + [50.0] + [50.0] * 40
        dates = write_csv("1111", closes)
        self.assertIsNone(data.recent_jump("1111", dates[-1], 25))             # 25日より前の段差は影響しない
        self.assertIsNotNone(data.recent_jump("1111", dates[-1], 45))

    def test_audit_欠けと段差(self):
        closes = [100.0] * 10 + [45.0] * 10
        dates = weekdays(len(closes))
        data.save("1111", [{"Date": d, "Open": c, "High": c, "Low": c, "Close": c, "Volume": 1}
                           for i, (d, c) in enumerate(zip(dates, closes)) if i != 5])
        w = data.audit("1111")
        self.assertTrue(any("段差" in x for x in w))
        self.assertTrue(any("行が無い" in x and dates[5] in x for x in w))

    def test_audit_問題なし(self):
        write_csv("1111", [100.0 + i for i in range(30)])
        self.assertEqual(data.audit("1111"), [])


class TestSignalGuard(Base):
    def setUp(self):
        super().setUp()
        # 買いシグナルは出るが、直近に -50% の段差（分割の疑い）がある並び
        self.closes = [200.0] * 25 + [90.0] * 3 + [140.0]
        self.dates = write_csv("1111", self.closes)

    def test_段差のある銘柄は買わない(self):
        with mock.patch.object(config, "ORDER_MODE", "paper"), mock.patch.object(config, "SYMBOLS", ["1111"]):
            st = paper.evening(self.dates[-1])
        self.assertEqual(st["pending"], [])

    def test_段差が無ければ買う(self):
        write_csv("1111", CROSS)
        with mock.patch.object(config, "ORDER_MODE", "paper"), mock.patch.object(config, "SYMBOLS", ["1111"]):
            st = paper.evening(weekdays(len(CROSS))[-1])
        self.assertEqual([o["side"] for o in st["pending"]], ["買い"])

    def test_保有中の売りは止めない(self):
        closes = [100.0] * 25 + [140.0] * 5 + [60.0] * 8          # 140 -> 60 は段差だが、売りは出す
        dates = write_csv("1111", closes)
        from kabu_auto import strategy
        sell_d = [d for d, k in strategy.signals_for(dates, closes) if k == "売り"][0]
        st = paper.load()
        st["positions"]["1111"] = {"qty": 100, "entry_date": dates[0], "entry_px": 100.0}
        paper.save(st)
        with mock.patch.object(config, "ORDER_MODE", "paper"), mock.patch.object(config, "SYMBOLS", ["1111"]):
            st = paper.evening(sell_d)
        self.assertEqual([o["side"] for o in st["pending"]], ["売り"])


class TestImportNote(Base):
    def test_調整後の列を使うと注意が出る(self):
        src = self.tmp / "jq.csv"
        src.write_text("Date,AdjustmentOpen,AdjustmentHigh,AdjustmentLow,AdjustmentClose,AdjustmentVolume\n"
                       "2026-06-01,10,11,9,10,100\n2026-06-02,10,11,9,10.5,100\n", encoding="utf-8")
        self.assertEqual(data.import_csv("1111", src), 2)
        self.assertIn("調整後", data.last_import_note)

    def test_通常の列なら注意なし(self):
        src = self.tmp / "y.csv"
        src.write_text("Date,Open,High,Low,Close,Volume\n2026-06-01,10,11,9,10,100\n", encoding="utf-8")
        data.import_csv("1111", src)
        self.assertEqual(data.last_import_note, "")


class TestShippedHolidays(unittest.TestCase):
    """配布している data/holidays.txt の形式チェック（内容の正しさは JPX の公式ページで確認する）。"""

    def setUp(self):
        self.path = Path(__file__).resolve().parent.parent / "data" / "holidays.txt"

    def days(self):
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if len(s) >= 10 and s[0] != "#":
                out.append(s[:10])
        return out

    def test_日付として読めて_土日でなく_重複せず_並んでいる(self):
        import datetime as dt
        days = self.days()
        self.assertGreater(len(days), 30)
        parsed = [dt.date.fromisoformat(d) for d in days]           # 読めない行があればここで落ちる
        self.assertEqual(days, sorted(set(days)))
        for d in parsed:
            self.assertLess(d.weekday(), 5, f"{d} は土日（書かなくてよい）")

    def test_今年と来年の分がある(self):
        years = {d[:4] for d in self.days()}
        self.assertLessEqual({"2026", "2027"}, years)

    def test_カレンダーが休場と判定する(self):
        with mock.patch.object(config, "HOLIDAYS_FILE", self.path):
            self.assertEqual(cal.holiday_warning("2026-09-19"), "")
            self.assertFalse(cal.is_trading_day("2026-09-22"))        # 国民の休日
            self.assertFalse(cal.is_trading_day("2027-03-22"))        # 振替休日
            self.assertTrue(cal.is_trading_day("2026-09-24"))
            self.assertEqual(cal.next_trading_day("2026-09-18"), "2026-09-24")   # 9/21-23 が連休
            self.assertEqual(cal.next_trading_day("2026-12-30"), "2027-01-04")   # 大納会の次は大発会


if __name__ == "__main__":
    unittest.main()
