# -*- coding: utf-8 -*-
"""朝いちばんに押す：接続を確かめて、今日の注文を出す（実発注モードのときだけ）。

使い方:  py run_morning.py            今日
         py run_morning.py --date 2026-09-03

毎朝の手順（第7章 7-3）: ①kabuステーションにログイン → ②このボタン → 「今日は動きます」を見る
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import config                                   # noqa: E402
from kabu_auto import api, calendar as cal, paper  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=cal.today())
    a = ap.parse_args()
    if os.environ.get("KABU_GUI") and config.ORDER_MODE != "paper":
        # 画面（run_gui.py）から呼ばれたときは、発注しないモードでしか動かない（二重の安全策）
        print("NG: 画面からの操作は、config.py が発注しないモード（paper）のときだけ動きます。実弾の操作は start.py から行ってください。")
        return 1
    d = a.date
    if config.ORDER_MODE == "live":
        print("★★★ 実発注モードです。この先の注文は本物のお金が動きます ★★★")
        per = f"{config.BUDGET_PER_ORDER:,} 円まで" if config.BUDGET_PER_ORDER is not None else f"{config.QTY} 株（固定）"
        print(f"    1日の上限 {config.DAILY_ORDER_LIMIT} 件 / 1回 {per} / 口座区分 {config.ACCOUNT_TYPE}")
    try:
        print(api.check_connection())
    except api.ApiError as e:
        print(f"NG: {e}")
        print("今日は動きません。上の原因を直してから、もう一度押してください。")
        return 1
    warn = cal.holiday_warning(d)
    if warn:
        print(f"[{'NG' if config.ORDER_MODE == 'live' else 'WARN'}] {warn}")
        if config.ORDER_MODE == "live":
            print("実発注は止めます。休場日ファイルを整えてから、もう一度押してください。")
            return 1
    if not cal.is_trading_day(d):
        print(f"{d} は休場です。今日は注文はありません。")
        return 0
    if config.ORDER_MODE == "live":
        token = api.get_token()
        try:
            holdings = api.holdings(token)       # 発注の前に、証券会社の残高を見る（帳簿とずれたまま出さないため）
        except api.ApiError as e:
            print(f"NG: 証券会社の残高を取れません（{e}）")
            print("残高の突き合わせができないので、実発注は止めます。原因を直してから、もう一度押してください。")
            return 1
        paper.morning(d, send_func=lambda code, side, qty: api.send_order(token, code, side, qty), holdings=holdings)
    else:
        paper.morning(d)
    print("今日は動きます。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
