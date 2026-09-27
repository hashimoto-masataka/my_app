# -*- coding: utf-8 -*-
"""株価チャート(価格・短期線・長期線+売買シグナルの矢印)を画像に保存するスクリプト

使い方:  py ma_chart.py 銘柄コード
例:      py ma_chart.py 7203   →  chart_7203.png ができる

データ取得・移動平均・シグナル判定は ma_signal.py の関数をそのまま使う。
期間を変えたいときは ma_signal.py の SHORT_PERIOD / LONG_PERIOD を変更する。
"""
import datetime
import sys
import urllib.error

import matplotlib
matplotlib.use("Agg")  # 画面表示なしで画像ファイルだけ作る
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from ma_signal import (
    SHORT_PERIOD, LONG_PERIOD,
    fetch_daily_closes, moving_average, find_signals,
)

# 日本語ラベルが文字化けしないようWindows標準フォントを指定
plt.rcParams["font.family"] = ["Meiryo", "MS Gothic", "sans-serif"]


def main() -> int:
    if len(sys.argv) < 2:
        print("使い方:  py ma_chart.py 銘柄コード")
        print("例:      py ma_chart.py 7203")
        return 1
    symbol = sys.argv[1]

    try:
        data = fetch_daily_closes(symbol)
    except (urllib.error.URLError, RuntimeError) as e:
        print(f"NG: 終値データを取得できませんでした ({e})")
        return 1

    dates_s = [d for d, _ in data]
    closes = [c for _, c in data]
    dates = [datetime.datetime.strptime(d, "%Y-%m-%d") for d in dates_s]
    short_ma = moving_average(closes, SHORT_PERIOD)
    long_ma = moving_average(closes, LONG_PERIOD)
    signals = find_signals(dates_s, short_ma, long_ma)

    # シグナルの日付 → その日の終値(矢印を置く位置に使う)
    close_by_date = dict(zip(dates_s, closes))
    buy_x = [datetime.datetime.strptime(d, "%Y-%m-%d") for d, k in signals if k == "買い"]
    buy_y = [close_by_date[d] for d, k in signals if k == "買い"]
    sell_x = [datetime.datetime.strptime(d, "%Y-%m-%d") for d, k in signals if k == "売り"]
    sell_y = [close_by_date[d] for d, k in signals if k == "売り"]

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(dates, closes, color="#444444", linewidth=1.2, label="終値")
    ax.plot(dates, short_ma, color="#1f77b4", linewidth=1.5,
            label=f"短期 {SHORT_PERIOD}日移動平均")
    ax.plot(dates, long_ma, color="#ff7f0e", linewidth=1.5,
            label=f"長期 {LONG_PERIOD}日移動平均")

    # 矢印: 買い=価格の少し下に上向き▲、売り=価格の少し上に下向き▼
    offset = (max(closes) - min(closes)) * 0.04
    ax.scatter(buy_x, [y - offset for y in buy_y], marker="^", s=130,
               color="#d62728", zorder=5, label="買いシグナル")
    ax.scatter(sell_x, [y + offset for y in sell_y], marker="v", s=130,
               color="#2ca02c", zorder=5, label="売りシグナル")

    ax.set_title(f"{symbol}  移動平均クロス ({SHORT_PERIOD}日/{LONG_PERIOD}日)")
    ax.set_ylabel("株価(円)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()

    out = f"chart_{symbol}.png"
    fig.savefig(out, dpi=110)
    print(f"チャートを保存しました: {out}")
    print(f"(買い {len(buy_x)}回 / 売り {len(sell_x)}回 のシグナルを表示)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
