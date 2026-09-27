# -*- coding: utf-8 -*-
"""バックテスト（第6章）を手元のデータで回す。

使い方:  py run_backtest.py 7203              素直（config の期間）
         py run_backtest.py 7203 --grid       総当たり（罠の実演）
         py run_backtest.py 7203 --walk       walk-forward
         py run_backtest.py --import 7203 path/to/jquants.csv   過去データの取り込み（J-Quants / yfinance 等）
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import config                              # noqa: E402
from kabu_auto import backtest, data       # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("code", nargs="?")
    ap.add_argument("--grid", action="store_true")
    ap.add_argument("--walk", action="store_true")
    ap.add_argument("--import", dest="imp", nargs=2, metavar=("CODE", "CSV"))
    ap.add_argument("--audit", action="store_true", help="データの点検（段差・欠け）。銘柄を指定しなければ config.SYMBOLS 全部")
    a = ap.parse_args()

    if a.audit:
        codes = [a.code] if a.code else config.SYMBOLS
        n = 0
        for c in codes:
            for w in data.audit(c):
                print("  [WARN] " + w)
                n += 1
        print(f"点検 {len(codes)} 銘柄: " + ("問題は見つかりませんでした" if not n else f"{n} 件の警告"))
        return 1 if n else 0

    if a.imp:
        n = data.import_csv(a.imp[0], Path(a.imp[1]))
        print(f"{a.imp[0]}: {n} 行を取り込みました → {data.path_of(a.imp[0])}")
        if data.last_import_note:
            print("  [注意] " + data.last_import_note)
        for w in data.audit(a.imp[0]):
            print("  [WARN] " + w)
        return 0
    if not a.code:
        ap.print_help()
        return 1

    dates, opens, closes = data.series(a.code)
    if len(closes) < config.LONG_PERIOD + 2:
        print(f"NG: {a.code} のデータが {len(closes)} 日分しかありません（--import で過去分を入れてください）")
        return 1
    print(f"銘柄 {a.code}  {dates[0]} 〜 {dates[-1]}（{len(dates)} 日）")
    for w in data.audit(a.code):
        print("  [WARN] " + w)

    print(f"約定: シグナルの翌営業日の寄値 / コスト 片道 {config.BACKTEST_SLIPPAGE_BPS + config.BACKTEST_FEE_BPS:g}bp（税金は下に概算で別表示）")
    r = backtest.run(dates, closes, config.SHORT_PERIOD, config.LONG_PERIOD, opens)
    n, wr, avg = backtest.summary(r)
    print(f"素直 {config.SHORT_PERIOD}日/{config.LONG_PERIOD}日: 累積損益 {r['total']:+,.1f}円（1株）/ 取引 {n} 回 / "
          f"勝率 {wr:.1f}% / 1取引あたり平均 {avg:+.2f}%")
    tax, net = backtest.after_tax(r["trades"])
    print(f"  税引後（概算・確定した取引のみ）: {net:+,.1f}円 / 税 {tax:,.1f}円（税率 {config.BACKTEST_TAX_RATE * 100:.3f}%。繰越控除・損益通算は考えない）")

    if a.grid:
        ranked = backtest.grid_search(dates, closes, opens=opens)
        print(f"総当たり {len(ranked)} 通り。上位5:")
        for total, s, l, n, w in ranked[:5]:
            print(f"  {s:>2}日/{l:>3}日  {total:+,.1f}円  取引{n}回 勝率{w:.1f}%")
        print("※これは「過去に合わせ込んだ数字」です。信じない（第6章 6-4）")
    if a.walk:
        wf = backtest.walk_forward(dates, closes, opens=opens)
        if not wf["windows"]:
            print(f"NG: 学習{config.TRAIN_DAYS}日＋検証{config.TEST_DAYS}日の窓が作れません。config の TRAIN_DAYS/TEST_DAYS を小さく")
            return 1
        for tr_s, tr_e, te_s, te_e, s, l, pnl in wf["windows"]:
            print(f"  学習 {tr_s}〜{tr_e} → 検証 {te_s}〜{te_e}  選ばれた {s}日/{l}日  {pnl:+,.1f}円")
        wins = sum(1 for w in wf["windows"] if w[6] > 0)
        print(f"walk-forward: 検証期間の累積 {wf['wf_equity'][-1]:+,.1f}円 / {len(wf['windows'])} 窓中 勝ち {wins}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
