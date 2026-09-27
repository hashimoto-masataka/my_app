# -*- coding: utf-8 -*-
"""バックテスト（第6章）: 素直に当てる／総当たり（罠の実演）／walk-forward。

売買のルールは実運用（paper.py）と同じ：
  シグナルが出た日の終値で判定 → 「翌営業日の寄値」で約定する（当日の終値では約定しない）。
  最終日に出たシグナルは、約定する日が無いので何もしない。
  コスト：約定価格に、片道ぶんの スリッページ + 手数料（config.BACKTEST_SLIPPAGE_BPS / BACKTEST_FEE_BPS）を不利な向きに乗せる。
  損益は 1株あたりの円。税金は run() の損益には入れず、after_tax() で税引後の概算を別に出す。returns は1回の取引ごとのコスト込みリターン（%ではなく比率）。
opens を渡さなかったときは、約定価格に「翌日の終値」を使う（寄値の列が無いデータ用の近似）。
"""
import config
from kabu_auto.strategy import moving_average, find_signals


def _cost_rate(slippage_bps, fee_bps) -> float:
    s = config.BACKTEST_SLIPPAGE_BPS if slippage_bps is None else slippage_bps
    f = config.BACKTEST_FEE_BPS if fee_bps is None else fee_bps
    return (s + f) / 10000.0


def run(dates: list, closes: list, short: int, long_: int, opens: list = None,
        slippage_bps: float = None, fee_bps: float = None) -> dict:
    """戻り値: equity（日ごとの累積損益・1株あたり円。含み損益つき）/ trades / returns / total。

    trades は [(買い約定日, 買い約定値, 売り約定日, 売り約定値, 損益), ...]。約定値はコスト込み。
    """
    fills = opens if opens is not None else closes
    cost = _cost_rate(slippage_bps, fee_bps)
    sig = dict(find_signals(dates, moving_average(closes, short), moving_average(closes, long_)))
    realized, entry, entry_d = 0.0, None, None
    equity, trades, returns = [], [], []
    order = None                                   # 前日のシグナルで積まれた「今日の寄りで出す注文」
    for i, d in enumerate(dates):
        if order == "買い" and entry is None:
            entry, entry_d = fills[i] * (1 + cost), d
        elif order == "売り" and entry is not None:
            px = fills[i] * (1 - cost)
            pnl = px - entry
            realized += pnl
            trades.append((entry_d, entry, d, px, pnl))
            returns.append(pnl / entry)
            entry = None
        order = None
        equity.append(realized + ((closes[i] - entry) if entry is not None else 0.0))
        k = sig.get(d)
        if k == "買い" and entry is None:
            order = "買い"
        elif k == "売り" and entry is not None:
            order = "売り"
    return {"equity": equity, "trades": trades, "returns": returns, "total": equity[-1] if equity else 0.0}


def summary(r: dict) -> tuple:
    """(取引回数, 勝率%, 1取引あたり平均リターン%)"""
    t = r["trades"]
    n = len(t)
    wr = (sum(1 for x in t if x[4] > 0) / n * 100) if n else 0.0
    avg = (sum(r["returns"]) / n * 100) if n else 0.0
    return n, wr, avg


def after_tax(trades: list, rate: float = None) -> tuple:
    """(税額, 税引後の累積損益)。trades は run() の trades（実現損益だけ。含み益は入れない）。

    概算のしかた：売った年ごとに、その年の損益の合計がプラスなら rate をかける（年内の損失は同じ年の利益と相殺）。
    次のことは考えていない：損失の繰越控除（3年）、他の銘柄・他の口座との損益通算、住民税の申告方法による違い、
    配当、NISA の非課税枠。なので実際の税額とは違う。損失の年が続く場合は、この概算は実際より税が重く出る（保守的）。
    """
    rate = config.BACKTEST_TAX_RATE if rate is None else rate
    by_year = {}
    for t in trades:
        by_year[t[2][:4]] = by_year.get(t[2][:4], 0.0) + t[4]
    tax = sum(max(0.0, v) * rate for v in by_year.values())
    return tax, sum(t[4] for t in trades) - tax


def grid_search(dates: list, closes: list, shorts=range(3, 31), longs=range(10, 121, 5), opens: list = None) -> list:
    """[(累積損益, 短期, 長期, 取引回数, 勝率), ...] を良い順に。※やってはいけないことの実演。"""
    out = []
    for s in shorts:
        for l in longs:
            if s >= l or len(closes) < l + 2:
                continue
            r = run(dates, closes, s, l, opens)
            t = r["trades"]
            wr = (sum(1 for x in t if x[4] > 0) / len(t) * 100) if t else 0.0
            out.append((r["total"], s, l, len(t), wr))
    out.sort(reverse=True)
    return out


def walk_forward(dates: list, closes: list, train_days: int = None, test_days: int = None, opens: list = None) -> dict:
    """学習期間で総当たり → 決めた期間を、まだ見ていない検証期間で試す → ずらして繰り返す。"""
    train_days = train_days or config.TRAIN_DAYS
    test_days = test_days or config.TEST_DAYS
    wf_dates, wf_equity, windows = [], [], []
    carried, start = 0.0, 0
    while start + train_days + test_days <= len(closes):
        ranked = grid_search(dates[start:start + train_days], closes[start:start + train_days],
                             opens=opens[start:start + train_days] if opens else None)
        if not ranked:
            break
        _, bs, bl, _, _ = ranked[0]
        warm = max(0, start + train_days - bl - 1)
        end = start + train_days + test_days
        r = run(dates[warm:end], closes[warm:end], bs, bl, opens[warm:end] if opens else None)
        cut = (start + train_days) - warm
        base = r["equity"][cut - 1] if cut > 0 else 0.0
        eq = [e - base for e in r["equity"][cut:]]
        wf_dates.extend(dates[start + train_days:end])
        wf_equity.extend([carried + e for e in eq])
        carried = wf_equity[-1]
        windows.append((dates[start], dates[start + train_days - 1], dates[start + train_days],
                        dates[end - 1], bs, bl, eq[-1]))
        start += test_days
    return {"wf_dates": wf_dates, "wf_equity": wf_equity, "windows": windows}
