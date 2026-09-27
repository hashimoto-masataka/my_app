# -*- coding: utf-8 -*-
"""移動平均クロスのシグナルで売買したら損益がどうなったかを調べるスクリプト

使い方:  py backtest.py 銘柄コード [期間]
例:      py backtest.py 7203 5y

売買のルール(第4章のシグナルをそのまま使う):
  買いシグナルの日の終値で1株買う(持っていないときだけ)
  売りシグナルの日の終値で売る(持っているときだけ)
  最終日に持ち越していたら、最終日の終値で評価する(含み損益)

※手数料・スリッページ・税金は入れていない。ここは第7章で扱う。
"""
import sys
import urllib.error

from ma_signal import (
    SHORT_PERIOD, LONG_PERIOD,
    fetch_daily_closes, moving_average, find_signals,
)


def backtest(dates: list, closes: list, short_period: int, long_period: int) -> dict:
    """売買を再現して、日々の累積損益と取引明細を返す。

    戻り値:
      equity  … 日ごとの累積損益(確定 + 含み)。dates と同じ長さ
      trades  … [(買った日, 買値, 売った日, 売値, 損益), ...]
      total   … 最終の累積損益
    """
    short_ma = moving_average(closes, short_period)
    long_ma = moving_average(closes, long_period)
    signals = dict(find_signals(dates, short_ma, long_ma))

    realized = 0.0      # 決済して確定した損益
    entry_price = None  # 保有中の建値(持っていなければ None)
    entry_date = None
    equity = []
    trades = []

    for i, date in enumerate(dates):
        kind = signals.get(date)
        if kind == "買い" and entry_price is None:
            entry_price = closes[i]
            entry_date = date
        elif kind == "売り" and entry_price is not None:
            profit = closes[i] - entry_price
            realized += profit
            trades.append((entry_date, entry_price, date, closes[i], profit))
            entry_price = None
            entry_date = None
        # その日の時点での累積損益 = 確定分 + いま持っている分の含み
        unrealized = (closes[i] - entry_price) if entry_price is not None else 0.0
        equity.append(realized + unrealized)

    return {"equity": equity, "trades": trades, "total": equity[-1] if equity else 0.0}


def main() -> int:
    if len(sys.argv) < 2:
        print("使い方:  py backtest.py 銘柄コード [期間]")
        print("例:      py backtest.py 7203 5y")
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
    if len(data) < LONG_PERIOD + 2:
        print(f"NG: データが{len(data)}日分しかなく、長期{LONG_PERIOD}日の計算に足りません。")
        return 1

    result = backtest(dates, closes, SHORT_PERIOD, LONG_PERIOD)
    trades = result["trades"]

    print(f"銘柄: {symbol}  期間: {dates[0]} 〜 {dates[-1]} ({len(data)}日分)")
    print(f"ルール: 短期{SHORT_PERIOD}日 / 長期{LONG_PERIOD}日 の移動平均クロス、1株ずつ売買")
    print()
    if not trades:
        print("売買は一度も成立しませんでした。")
    else:
        print("取引の明細(1株あたり):")
        for buy_d, buy_p, sell_d, sell_p, profit in trades:
            mark = "＋" if profit >= 0 else "−"
            print(f"  {buy_d} {buy_p:>8,.1f}円 買い → "
                  f"{sell_d} {sell_p:>8,.1f}円 売り   {mark}{abs(profit):>7,.1f}円")
        wins = [t for t in trades if t[4] > 0]
        print()
        print(f"取引回数: {len(trades)}回   勝ち: {len(wins)}回   "
              f"勝率: {len(wins) / len(trades) * 100:.1f}%")
    print(f"累積損益(1株あたり): {result['total']:+,.1f}円")
    print(f"※手数料・スリッページ・税金は含めていません。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
