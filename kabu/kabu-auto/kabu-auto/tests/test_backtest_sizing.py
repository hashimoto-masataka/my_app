# -*- coding: utf-8 -*-
"""バックテストが実運用と同じルール（翌営業日の寄値で約定・コスト込み）になっていることと、株数の決め方のテスト。

実行:  py -m unittest discover -s tests -v
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config                                              # noqa: E402
from kabu_auto import backtest, data, paper, sizing, strategy  # noqa: E402
from test_safety import CROSS, Base, write_csv, weekdays   # noqa: E402


def cross_series(n_tail: int = 0):
    """買い→売りが1回ずつ出る終値の並び。

    100 x25 → 90 x3 → 140（買い）→ 140 x4 → 60 x6 → …（デッドクロス）
    """
    c = [100.0] * 25 + [90.0] * 3 + [140.0] + [140.0] * 4 + [60.0] * 8 + [60.0] * n_tail
    return c


class TestBacktestAlignment(unittest.TestCase):
    def setUp(self):
        self.closes = cross_series()
        self.dates = weekdays(len(self.closes))
        sig = strategy.signals_for(self.dates, self.closes)
        self.buy_i = self.dates.index([d for d, k in sig if k == "買い"][0])
        self.sell_i = self.dates.index([d for d, k in sig if k == "売り" and d > self.dates[self.buy_i]][0])   # 買いの後の最初の売り

    def test_シグナルの翌営業日の寄値で約定する(self):
        opens = [c + 1 for c in self.closes]           # 寄値は終値より1円高い、と仮定
        r = backtest.run(self.dates, self.closes, 5, 25, opens, slippage_bps=0, fee_bps=0)
        buy_d, buy_px, sell_d, sell_px, pnl = r["trades"][0]
        self.assertEqual(buy_d, self.dates[self.buy_i + 1])          # 翌日
        self.assertEqual(buy_px, opens[self.buy_i + 1])              # 当日終値ではなく翌日の寄値
        self.assertEqual(sell_d, self.dates[self.sell_i + 1])
        self.assertEqual(sell_px, opens[self.sell_i + 1])
        self.assertAlmostEqual(pnl, sell_px - buy_px)

    def test_コストは不利な向きに乗る(self):
        opens = list(self.closes)
        free = backtest.run(self.dates, self.closes, 5, 25, opens, slippage_bps=0, fee_bps=0)
        paid = backtest.run(self.dates, self.closes, 5, 25, opens, slippage_bps=10, fee_bps=5)   # 片道 15bp
        _, buy_px, _, sell_px, _ = paid["trades"][0]
        _, fbuy, _, fsell, _ = free["trades"][0]
        self.assertAlmostEqual(buy_px, fbuy * 1.0015)
        self.assertAlmostEqual(sell_px, fsell * 0.9985)
        self.assertLess(paid["total"], free["total"])

    def test_最終日のシグナルは約定しない(self):
        n = self.buy_i + 1                                # 買いシグナルが最終日になるところで切る
        r = backtest.run(self.dates[:n], self.closes[:n], 5, 25, None, slippage_bps=0, fee_bps=0)
        self.assertEqual(r["trades"], [])
        self.assertEqual(r["total"], 0.0)                 # 建玉も無い

    def test_約定した日から含み損益がつく(self):
        opens = list(self.closes)
        r = backtest.run(self.dates, self.closes, 5, 25, opens, slippage_bps=0, fee_bps=0)
        j = self.buy_i + 1
        self.assertEqual(r["equity"][j - 1], 0.0)
        self.assertAlmostEqual(r["equity"][j], self.closes[j] - opens[j])

    def test_returnsは取引ごとのコスト込みリターン(self):
        opens = list(self.closes)
        r = backtest.run(self.dates, self.closes, 5, 25, opens, slippage_bps=10, fee_bps=0)
        _, buy_px, _, _, pnl = r["trades"][0]
        self.assertAlmostEqual(r["returns"][0], pnl / buy_px)
        n, wr, avg = backtest.summary(r)
        self.assertEqual(n, 1)

    def test_walk_forwardが寄値つきで動く(self):
        closes = (cross_series() * 8)[:400]
        dates = weekdays(len(closes))
        wf = backtest.walk_forward(dates, closes, train_days=150, test_days=50, opens=list(closes))
        self.assertGreater(len(wf["windows"]), 0)


class TestAfterTax(unittest.TestCase):
    def trade(self, sell_date, pnl):
        return ("2026-01-05", 100.0, sell_date, 100.0 + pnl, pnl)

    def test_利益にだけ税がかかる(self):
        tax, net = backtest.after_tax([self.trade("2026-03-02", 100.0)], 0.2)
        self.assertAlmostEqual(tax, 20.0)
        self.assertAlmostEqual(net, 80.0)

    def test_同じ年の損失は相殺する(self):
        tax, net = backtest.after_tax([self.trade("2026-03-02", 100.0), self.trade("2026-05-01", -60.0)], 0.2)
        self.assertAlmostEqual(tax, 8.0)            # (100-60) * 0.2
        self.assertAlmostEqual(net, 32.0)

    def test_損失の年は税がゼロ_年をまたいだ相殺は考えない(self):
        tax, net = backtest.after_tax([self.trade("2025-12-01", -50.0), self.trade("2026-03-02", 100.0)], 0.2)
        self.assertAlmostEqual(tax, 20.0)            # 2025年の損失は繰り越さない（保守的な概算）
        self.assertAlmostEqual(net, 30.0)

    def test_非課税なら税ゼロ(self):
        tax, net = backtest.after_tax([self.trade("2026-03-02", 100.0)], 0.0)
        self.assertEqual((tax, net), (0.0, 100.0))

    def test_取引なし(self):
        self.assertEqual(backtest.after_tax([], 0.2), (0.0, 0.0))

    def test_既定の税率はconfigから(self):
        with mock.patch.object(config, "BACKTEST_TAX_RATE", 0.5):
            tax, _ = backtest.after_tax([self.trade("2026-03-02", 10.0)])
        self.assertAlmostEqual(tax, 5.0)


class TestSizing(unittest.TestCase):
    def test_予算に収まる最大の単元数(self):
        with mock.patch.object(config, "BUDGET_PER_ORDER", 500_000), mock.patch.object(config, "LOT_SIZE", 100), \
                mock.patch.object(config, "LOT_SIZES", {}):
            self.assertEqual(sizing.order_qty("1111", 1000.0), 500)      # 1単元 10万円 → 5単元
            self.assertEqual(sizing.order_qty("1111", 1234.0), 400)      # 1単元 123,400円 → 4単元
            self.assertEqual(sizing.order_qty("1111", 5000.0), 100)      # ちょうど1単元 50万円
            self.assertEqual(sizing.order_qty("1111", 5001.0), 0)        # 1単元が予算超え → 買わない

    def test_単元が違う銘柄(self):
        with mock.patch.object(config, "BUDGET_PER_ORDER", 100_000), mock.patch.object(config, "LOT_SIZES", {"9999": 1}):
            self.assertEqual(sizing.order_qty("9999", 1234.0), 81)
            self.assertEqual(sizing.lot_size("1111"), config.LOT_SIZE)

    def test_予算なしなら固定株数に戻る(self):
        with mock.patch.object(config, "BUDGET_PER_ORDER", None), mock.patch.object(config, "QTY", 200):
            self.assertEqual(sizing.order_qty("1111", 99999999.0), 200)

    def test_不正な価格は0株(self):
        self.assertEqual(sizing.order_qty("1111", 0), 0)
        self.assertEqual(sizing.order_qty("1111", None), 0)


class TestSignalSizing(Base):
    """引け後のシグナル → 注文の株数が予算基準になる。買えない銘柄は見送る。"""

    def test_予算基準の株数で注文が積まれる(self):
        dates = write_csv("1111", CROSS)                 # 最終日の終値 140円で買いシグナル
        d = dates[-1]
        with mock.patch.object(config, "ORDER_MODE", "paper"), mock.patch.object(config, "BUDGET_PER_ORDER", 100_000), \
                mock.patch.object(config, "SYMBOLS", ["1111"]):
            st = paper.evening(d)
        self.assertEqual(st["pending"][0]["qty"], 700)  # 100,000 / 140 = 714 → 7単元

    def test_1単元が予算超えなら見送る(self):
        dates = write_csv("1111", CROSS)
        d = dates[-1]
        with mock.patch.object(config, "ORDER_MODE", "paper"), mock.patch.object(config, "BUDGET_PER_ORDER", 10_000), \
                mock.patch.object(config, "SYMBOLS", ["1111"]):
            st = paper.evening(d)                       # 140円 x 100株 = 14,000円 > 10,000円
        self.assertEqual(st["pending"], [])

    def test_売りは建玉の株数のまま(self):
        closes = cross_series()
        dates = write_csv("1111", closes)
        sig = strategy.signals_for(dates, closes)
        buy_d = [d for d, k in sig if k == "買い"][0]
        sell_d = [d for d, k in sig if k == "売り" and d > buy_d][0]
        st = paper.load()
        st["positions"]["1111"] = {"qty": 300, "entry_date": dates[0], "entry_px": 100.0}
        paper.save(st)
        with mock.patch.object(config, "ORDER_MODE", "paper"), mock.patch.object(config, "BUDGET_PER_ORDER", 1), \
                mock.patch.object(config, "SYMBOLS", ["1111"]):
            st = paper.evening(sell_d)
        self.assertEqual([(o["side"], o["qty"]) for o in st["pending"]], [("売り", 300)])


class TestSeries(Base):
    def test_寄値が0なら終値で代用(self):
        dates = weekdays(3)
        data.save("1111", [{"Date": dates[0], "Open": 0, "High": 0, "Low": 0, "Close": 10, "Volume": 0},
                           {"Date": dates[1], "Open": 11, "High": 0, "Low": 0, "Close": 12, "Volume": 0}])
        d, o, c = data.series("1111")
        self.assertEqual(o, [10, 11])
        self.assertEqual(c, [10, 12])


if __name__ == "__main__":
    unittest.main()
