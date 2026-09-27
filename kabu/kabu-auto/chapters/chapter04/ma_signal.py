# -*- coding: utf-8 -*-
"""移動平均クロスで売買シグナルを出すスクリプト

使い方:  py ma_signal.py 銘柄コード
例:      py ma_signal.py 7203

終値データは Yahoo Finance の公開データから日足を自動取得する(追加インストール不要)。
kabuステーションAPIには日足履歴の取得機能がないため、データ源のみ外部を使う。
※Stooqも試したが、ブラウザ確認が必須になっておりスクリプトからは取得できなかった(2026-09-02)。

シグナルの定義:
  買い = 短期移動平均が長期移動平均を下から上に抜けた日(ゴールデンクロス)
  売り = 短期移動平均が長期移動平均を上から下に抜けた日(デッドクロス)
"""
import datetime
import json
import sys
import urllib.error
import urllib.request

# ============ 設定(ここを変えれば期間を調整できる) ============
SHORT_PERIOD = 5    # 短期移動平均の日数
LONG_PERIOD = 25    # 長期移動平均の日数
SHOW_SIGNALS = 10   # 直近何回分のシグナルを表示するか
# ==============================================================


def fetch_daily_closes(symbol: str, period: str = "1y") -> list:
    """Yahoo Financeから日足を取得し、[(日付, 終値), ...] を古い順で返す。

    period は "1y" "2y" "5y" "10y" など。既定は1年分(第4章と同じ)。
    第6章のバックテストのように長い期間が要るときだけ指定する。
    """
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.T"
           f"?range={period}&interval=1d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            data = json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise RuntimeError(f"銘柄コード {symbol} が見つかりませんでした")
        raise RuntimeError(f"データ取得に失敗しました (HTTP {e.code})")

    result = data.get("chart", {}).get("result")
    if not result:
        raise RuntimeError(f"データを取得できませんでした(銘柄コード {symbol} が正しいか確認してください)")

    timestamps = result[0]["timestamp"]
    closes = result[0]["indicators"]["quote"][0]["close"]
    pairs = []
    for ts, close in zip(timestamps, closes):
        if close is None:  # 休場などで値が無い日は飛ばす
            continue
        date = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        pairs.append((date, close))
    return pairs


def moving_average(closes: list, period: int) -> list:
    """単純移動平均。データが period 日に満たない位置は None。"""
    result = []
    for i in range(len(closes)):
        if i + 1 < period:
            result.append(None)
        else:
            result.append(sum(closes[i + 1 - period:i + 1]) / period)
    return result


def find_signals(dates: list, short_ma: list, long_ma: list) -> list:
    """クロスした日を [(日付, "買い" or "売り"), ...] で返す。"""
    signals = []
    for i in range(1, len(dates)):
        if None in (short_ma[i - 1], long_ma[i - 1], short_ma[i], long_ma[i]):
            continue
        prev_diff = short_ma[i - 1] - long_ma[i - 1]
        diff = short_ma[i] - long_ma[i]
        if prev_diff <= 0 < diff:
            signals.append((dates[i], "買い"))
        elif prev_diff >= 0 > diff:
            signals.append((dates[i], "売り"))
    return signals


def main() -> int:
    if len(sys.argv) < 2:
        print("使い方:  py ma_signal.py 銘柄コード")
        print("例:      py ma_signal.py 7203")
        return 1
    symbol = sys.argv[1]

    if SHORT_PERIOD >= LONG_PERIOD:
        print(f"NG: 短期({SHORT_PERIOD}日)は長期({LONG_PERIOD}日)より短くしてください。")
        return 1

    try:
        data = fetch_daily_closes(symbol)
    except (urllib.error.URLError, RuntimeError) as e:
        print(f"NG: 終値データを取得できませんでした ({e})")
        return 1

    if len(data) < LONG_PERIOD + 1:
        print(f"NG: データが{len(data)}日分しかなく、長期{LONG_PERIOD}日の計算に足りません。")
        return 1

    dates = [d for d, _ in data]
    closes = [c for _, c in data]
    short_ma = moving_average(closes, SHORT_PERIOD)
    long_ma = moving_average(closes, LONG_PERIOD)
    signals = find_signals(dates, short_ma, long_ma)

    print(f"銘柄: {symbol}  (終値データ: {dates[0]} 〜 {dates[-1]}, {len(data)}日分)")
    print(f"短期: {SHORT_PERIOD}日移動平均 / 長期: {LONG_PERIOD}日移動平均")
    print()
    print(f"直近の終値:     {closes[-1]:,.1f} 円 ({dates[-1]})")
    print(f"短期移動平均:   {short_ma[-1]:,.1f} 円")
    print(f"長期移動平均:   {long_ma[-1]:,.1f} 円")
    trend = "短期 > 長期 (上昇基調)" if short_ma[-1] > long_ma[-1] else "短期 < 長期 (下落基調)"
    print(f"現在の位置関係: {trend}")
    print()

    if not signals:
        print("シグナルは一度も発生していません。")
    else:
        print(f"直近のシグナル(最大{SHOW_SIGNALS}回分):")
        for date, kind in signals[-SHOW_SIGNALS:]:
            print(f"  {date}  {kind}")
        last_date, last_kind = signals[-1]
        if last_date == dates[-1]:
            print()
            print(f"★ 最新の営業日({last_date})にシグナルが出ています: {last_kind}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
