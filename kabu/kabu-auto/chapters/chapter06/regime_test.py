# -*- coding: utf-8 -*-
"""総当たりで選んだパラメータは、他の銘柄・他の期間に持ち越せるのか?

使い方:  py regime_test.py

第4章で作った100銘柄リストに対して、10年ぶんの日足を前半5年・後半5年に割り、
それぞれで下の組み合わせを比べる。★は7203の後半5年を総当たりして出た「最良」。
比較対象として、7203とは何の関係もない適当な遅い組み合わせと、
「買って持ち続ける」(取引ゼロ)も並べる。

損益は銘柄ごとの株価水準の違いを消すため、初日の株価に対する%で表す。
データは transfer_test.py が作る _price_cache/ を使う(無ければ取得する)。
"""
import json
import os
import sys
import time

from ma_signal import fetch_daily_closes
from backtest import backtest
from scan_signals import SYMBOLS

CACHE = "_price_cache"
HALF = 1230  # 5年ぶんの営業日の目安
PAIRS = [
    (5, 25, "5日/25日(第4章のまま)"),
    (28, 90, "★28日/90日(総当たりの最良)"),
    (10, 50, "10日/50日(適当)"),
    (30, 80, "30日/80日(適当)"),
    (40, 120, "40日/120日(適当)"),
]


def load_all(period: str = "10y") -> list:
    os.makedirs(CACHE, exist_ok=True)
    out = []
    for code, name in SYMBOLS:
        path = os.path.join(CACHE, f"{code}_{period}.json")
        if os.path.exists(path):
            data = json.load(open(path, encoding="utf-8"))
        else:
            try:
                data = fetch_daily_closes(code, period)
            except Exception as e:
                print(f"  取得失敗 {code} {name}: {e}", file=sys.stderr)
                continue
            json.dump(data, open(path, "w", encoding="utf-8"))
            time.sleep(0.15)  # 取得先への配慮(第3章の作法)
        if len(data) >= HALF * 2 - 60:
            out.append((code, name, [x[0] for x in data], [x[1] for x in data]))
    return out


def report(rows: list, title: str) -> None:
    m = len(rows)

    def med(v):
        v = sorted(v)
        return v[m // 2] if m % 2 else (v[m // 2 - 1] + v[m // 2]) / 2

    hold = [(cl[-1] - cl[0]) / cl[0] * 100 for _, _, _, cl in rows]
    print(f"\n■ {title}  {rows[0][2][0]}〜{rows[0][2][-1]}  {m}銘柄")
    print(f"  {'':<26}{'平均':>9}{'中央値':>9}{'取引':>8}{'持ち続けに勝ち':>14}")
    for s, l, label in PAIRS:
        vals, tr = [], []
        for _, _, dt, cl in rows:
            r = backtest(dt, cl, s, l)
            vals.append(r["total"] / cl[0] * 100)
            tr.append(len(r["trades"]))
        bh = sum(1 for x, h in zip(vals, hold) if x > h)
        print(f"  {label:<26}{sum(vals)/m:>+8.1f}%{med(vals):>+8.1f}%"
              f"{sum(tr)/m:>7.1f}回{bh:>11}/{m}")
    print(f"  {'買って持ち続ける(取引ゼロ)':<26}{sum(hold)/m:>+8.1f}%{med(hold):>+8.1f}%"
          f"{0:>7.1f}回{'-':>14}")


def main() -> int:
    series = load_all()
    if not series:
        print("NG: データを1銘柄も用意できませんでした。")
        return 1
    report([(c, n, dt[:HALF], cl[:HALF]) for c, n, dt, cl in series], "前半5年")
    report([(c, n, dt[-HALF:], cl[-HALF:]) for c, n, dt, cl in series], "後半5年")
    print()
    print("  読み方: 前半と後半で順位が入れ替わるなら、その組み合わせの良さは")
    print("          戦略の性質ではなく、その5年の性質にすぎない。")
    print("  ※このスクリプトの表示に長音記号を使っていないのは、Windowsのコンソール")
    print("    (cp932)が一部の記号を出せず、そこだけで異常終了するためです。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
