# -*- coding: utf-8 -*-
"""7203で総当たりして選んだパラメータは、他の銘柄にも通用するのか?

使い方:  py transfer_test.py [期間]
例:      py transfer_test.py 5y

第4章で作った100銘柄リスト(scan_signals.py の SYMBOLS)に対して、
  A) 第4章のまま          5日 / 25日
  B) 7203で総当たりの最良  28日 / 90日
  C) 単に買って持ち続ける (buy & hold)
の3つを当てはめて比べる。

株価の水準が銘柄ごとに違うので、損益は「初日の株価に対する%」に直して比べる。
"""
import json
import os
import sys
import time
import urllib.error

from ma_signal import fetch_daily_closes
from backtest import backtest
from scan_signals import SYMBOLS

CACHE = "_price_cache"
NAIVE = (5, 25)     # 第4章のまま
FITTED = (28, 90)   # 7203の5年を総当たりして出た最良


def load(symbol: str, period: str) -> list:
    """取得したデータをファイルに残しておき、2回目からはそれを読む。"""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"{symbol}_{period}.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    data = fetch_daily_closes(symbol, period)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    time.sleep(0.15)  # 取得先への配慮(第3章で教えた作法)
    return data


def main() -> int:
    period = sys.argv[1] if len(sys.argv) > 1 else "5y"
    rows, errors = [], []

    for i, (code, name) in enumerate(SYMBOLS, 1):
        try:
            data = load(code, period)
        except (urllib.error.URLError, RuntimeError) as e:
            errors.append((code, name, str(e)))
            continue
        if len(data) < 200:
            errors.append((code, name, f"{len(data)}日分しかない"))
            continue
        dates = [d for d, _ in data]
        closes = [c for _, c in data]
        base = closes[0]
        naive = backtest(dates, closes, *NAIVE)["total"] / base * 100
        fitted = backtest(dates, closes, *FITTED)["total"] / base * 100
        hold = (closes[-1] - base) / base * 100
        rows.append((code, name, naive, fitted, hold))
        if i % 20 == 0:
            print(f"  … {i}/{len(SYMBOLS)} 銘柄", file=sys.stderr)

    if not rows:
        print("NG: 1銘柄も取得できませんでした。")
        return 1

    n = len(rows)
    naive_v = sorted(r[2] for r in rows)
    fitted_v = sorted(r[3] for r in rows)
    hold_v = sorted(r[4] for r in rows)

    def med(v):
        return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2

    print(f"■ {n}銘柄 / 期間 {period}  (初日の株価に対する%で比較)")
    print()
    print(f"  {'':<26}{'平均':>9}{'中央値':>9}{'プラスの銘柄':>13}")
    for label, v in [(f"A 第4章のまま {NAIVE[0]}日/{NAIVE[1]}日", naive_v),
                     (f"B 7203の最良 {FITTED[0]}日/{FITTED[1]}日", fitted_v),
                     ("C 買って持ち続ける", hold_v)]:
        pos = sum(1 for x in v if x > 0)
        print(f"  {label:<26}{sum(v)/n:>+8.1f}%{med(v):>+8.1f}%{pos:>9}/{n}")

    beat_naive = sum(1 for r in rows if r[3] > r[2])
    beat_hold = sum(1 for r in rows if r[3] > r[4])
    print()
    print(f"  BがAに勝った銘柄     : {beat_naive}/{n}")
    print(f"  BがC(持ち続け)に勝った: {beat_hold}/{n}")

    # Bの成績と「その5年で上がったか」の関係
    mx = sum(r[3] for r in rows) / n
    my = sum(r[4] for r in rows) / n
    cov = sum((r[3] - mx) * (r[4] - my) for r in rows)
    vx = sum((r[3] - mx) ** 2 for r in rows) ** 0.5
    vy = sum((r[4] - my) ** 2 for r in rows) ** 0.5
    print(f"  Bの成績と買って持ち続けた成績の相関: {cov / (vx * vy):+.2f}")

    print()
    print("  Bが良かった上位5銘柄:")
    for code, name, a, b, c in sorted(rows, key=lambda r: -r[3])[:5]:
        print(f"    {code} {name:<12}  B{b:>+8.1f}%   A{a:>+8.1f}%   持ち続け{c:>+8.1f}%")
    print("  Bが悪かった下位5銘柄:")
    for code, name, a, b, c in sorted(rows, key=lambda r: r[3])[:5]:
        print(f"    {code} {name:<12}  B{b:>+8.1f}%   A{a:>+8.1f}%   持ち続け{c:>+8.1f}%")

    if errors:
        print()
        print(f"  取得できなかった銘柄: {len(errors)}件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
