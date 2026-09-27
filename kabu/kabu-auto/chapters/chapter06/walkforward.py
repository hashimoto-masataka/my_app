# -*- coding: utf-8 -*-
"""walk-forward検証: 学習期間で決めたパラメータを、見ていない検証期間で試す

使い方:  py walkforward.py 銘柄コード [期間]
例:      py walkforward.py 7203 5y

やっていること:
  1) 学習期間(既定500営業日 ≒ 2年)だけを見て、総当たりで最良のパラメータを決める
  2) そのパラメータを、次の検証期間(既定125営業日 ≒ 半年)で試す
     —— 検証期間は、パラメータを決めたときには"未来"だった部分
  3) 区切りを検証期間ぶんだけ後ろにずらして、1)〜2)を繰り返す
  4) 検証期間の成績だけをつないで評価する
"""
import sys
import urllib.error

from ma_signal import fetch_daily_closes
from backtest import backtest
from gridsearch import search

TRAIN_DAYS = 500  # 学習期間(営業日)
TEST_DAYS = 125   # 検証期間(営業日)


def walk_forward(dates: list, closes: list,
                 train_days: int = TRAIN_DAYS, test_days: int = TEST_DAYS) -> dict:
    """検証期間の損益だけをつないだ累積曲線を返す。

    戻り値:
      wf_dates  … 検証期間の日付を順につないだもの
      wf_equity … その日付に対応する累積損益(検証期間のみ)
      windows   … [(学習開始, 学習終了, 検証開始, 検証終了, 短期, 長期, その窓の損益), ...]
    """
    wf_dates, wf_equity, windows = [], [], []
    carried = 0.0  # 前の窓までの累積
    start = 0
    while start + train_days + test_days <= len(closes):
        tr_d = dates[start:start + train_days]
        tr_c = closes[start:start + train_days]
        # ★学習期間だけを見て決める(検証期間は絶対に覗かない)
        ranked = search(tr_d, tr_c)
        if not ranked:
            break
        _, best_short, best_long, _, _ = ranked[0]

        # 検証期間。移動平均の計算に長期ぶんの助走が要るので、直前のデータを足して渡す
        warm = start + train_days - best_long - 1
        seg_d = dates[warm:start + train_days + test_days]
        seg_c = closes[warm:start + train_days + test_days]
        r = backtest(seg_d, seg_c, best_short, best_long)
        # 助走部分を落として、検証期間ぶんだけを取り出す
        cut = (start + train_days) - warm
        eq = r["equity"][cut:]
        base = r["equity"][cut - 1] if cut > 0 else 0.0
        eq = [e - base for e in eq]

        wf_dates.extend(dates[start + train_days:start + train_days + test_days])
        wf_equity.extend([carried + e for e in eq])
        carried = wf_equity[-1]
        windows.append((dates[start], dates[start + train_days - 1],
                        dates[start + train_days], dates[start + train_days + test_days - 1],
                        best_short, best_long, eq[-1]))
        start += test_days

    return {"wf_dates": wf_dates, "wf_equity": wf_equity, "windows": windows}


def main() -> int:
    if len(sys.argv) < 2:
        print("使い方:  py walkforward.py 銘柄コード [期間]")
        return 1
    symbol = sys.argv[1]
    period = sys.argv[2] if len(sys.argv) > 2 else "5y"

    try:
        data = fetch_daily_closes(symbol, period)
    except (urllib.error.URLError, RuntimeError) as e:
        print(f"NG: 終値データを取得できませんでした ({e})")
        return 1

    dates = [d for d, _ in data]
    closes = [c for _, c in data]
    res = walk_forward(dates, closes)
    if not res["windows"]:
        print(f"NG: データが{len(data)}日分では、学習{TRAIN_DAYS}日＋検証{TEST_DAYS}日の窓が1つも作れません。")
        return 1

    print(f"銘柄: {symbol}  期間: {dates[0]} 〜 {dates[-1]} ({len(data)}日分)")
    print(f"学習{TRAIN_DAYS}営業日 → 検証{TEST_DAYS}営業日 を{TEST_DAYS}営業日ずつずらす")
    print()
    print(f"  {'学習期間':<24}{'検証期間':<24}{'選ばれた':>10}{'検証の損益':>12}")
    for tr_s, tr_e, te_s, te_e, sh, lo, pnl in res["windows"]:
        print(f"  {tr_s}〜{tr_e}  {te_s}〜{te_e}  {sh:>3}日/{lo:>3}日 {pnl:>+11,.1f}円")
    print()
    print(f"窓の数: {len(res['windows'])}   検証期間の累積損益: {res['wf_equity'][-1]:+,.1f}円")
    wins = sum(1 for w in res["windows"] if w[6] > 0)
    print(f"検証期間で勝った窓: {wins}/{len(res['windows'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
