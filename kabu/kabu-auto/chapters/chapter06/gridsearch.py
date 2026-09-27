# -*- coding: utf-8 -*-
"""移動平均の期間を総当たりして、いちばん累積損益が良くなる組み合わせを探すスクリプト

使い方:  py gridsearch.py 銘柄コード [期間]
例:      py gridsearch.py 7203 5y

※これは「やってはいけないこと」の実演。過去に都合のいい数字を選んでいるだけで、
  未来に通用する保証はまったくない(第6章 カーブフィッティング)。
"""
import sys
import urllib.error

from ma_signal import fetch_daily_closes
from backtest import backtest

SHORT_RANGE = range(3, 31)    # 短期: 3〜30日
LONG_RANGE = range(10, 121, 5)  # 長期: 10〜120日を5日刻み


def search(dates: list, closes: list, verbose: bool = False) -> list:
    """全組み合わせを試して [(累積損益, 短期, 長期, 取引回数, 勝率), ...] を良い順に返す。"""
    results = []
    for short in SHORT_RANGE:
        for long in LONG_RANGE:
            if short >= long:
                continue
            if len(closes) < long + 2:
                continue
            r = backtest(dates, closes, short, long)
            t = r["trades"]
            wr = (sum(1 for x in t if x[4] > 0) / len(t) * 100) if t else 0.0
            results.append((r["total"], short, long, len(t), wr))
    results.sort(reverse=True)
    return results


def main() -> int:
    if len(sys.argv) < 2:
        print("使い方:  py gridsearch.py 銘柄コード [期間]")
        return 1
    symbol = sys.argv[1]
    period = sys.argv[2] if len(sys.argv) > 2 else "1y"

    try:
        data = fetch_daily_closes(symbol, period)
    except (urllib.error.URLError, RuntimeError) as e:
        print(f"NG: 終値データを取得できませんでした ({e})")
        return 1

    dates = [d for d, _ in data]
    closes = [c for _, c in data]
    results = search(dates, closes)

    print(f"銘柄: {symbol}  期間: {dates[0]} 〜 {dates[-1]} ({len(data)}日分)")
    print(f"試した組み合わせ: {len(results)}通り")
    print()
    print("成績が良かった上位10通り:")
    print(f"  {'短期':>4} {'長期':>4} {'取引':>4} {'勝率':>7} {'累積損益':>12}")
    for total, short, long, n, wr in results[:10]:
        print(f"  {short:>4} {long:>4} {n:>4} {wr:>6.1f}% {total:>+11,.1f}円")
    print()
    print("成績が悪かった下位3通り(参考):")
    for total, short, long, n, wr in results[-3:]:
        print(f"  {short:>4} {long:>4} {n:>4} {wr:>6.1f}% {total:>+11,.1f}円")
    print()
    best = results[0]
    print(f"★ 最良: 短期{best[1]}日 / 長期{best[2]}日 → {best[0]:+,.1f}円")
    print(f"   (第4章の既定 5日/25日 と比べてどれだけ「良く」なったかを見てください)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
