# -*- coding: utf-8 -*-
"""移動平均クロス（第4章）。

  買い = 短期移動平均が長期移動平均を下から上に抜けた日（ゴールデンクロス）
  売り = 短期移動平均が長期移動平均を上から下に抜けた日（デッドクロス）

期間は config.SHORT_PERIOD / LONG_PERIOD。第6章のとおり、ここを「最適化」しない。
"""
import config


def moving_average(closes: list, period: int) -> list:
    """単純移動平均。period 日に満たない位置は None。"""
    out = []
    for i in range(len(closes)):
        if i + 1 < period:
            out.append(None)
        else:
            out.append(sum(closes[i + 1 - period:i + 1]) / period)
    return out


def find_signals(dates: list, short_ma: list, long_ma: list) -> list:
    """クロスした日を [(日付, "買い" or "売り"), ...] で返す。"""
    signals = []
    for i in range(1, len(dates)):
        if None in (short_ma[i - 1], long_ma[i - 1], short_ma[i], long_ma[i]):
            continue
        prev = short_ma[i - 1] - long_ma[i - 1]
        cur = short_ma[i] - long_ma[i]
        if prev <= 0 < cur:
            signals.append((dates[i], "買い"))
        elif prev >= 0 > cur:
            signals.append((dates[i], "売り"))
    return signals


def signals_for(dates: list, closes: list, short: int = None, long_: int = None) -> list:
    short = short or config.SHORT_PERIOD
    long_ = long_ or config.LONG_PERIOD
    return find_signals(dates, moving_average(closes, short), moving_average(closes, long_))


def latest_signal(dates: list, closes: list) -> str:
    """最終日にシグナルが出ていれば "買い"/"売り"、無ければ ""。"""
    if len(closes) < config.LONG_PERIOD + 1:
        return ""
    sig = signals_for(dates, closes)
    if sig and sig[-1][0] == dates[-1]:
        return sig[-1][1]
    return ""
