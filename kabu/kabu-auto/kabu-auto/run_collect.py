# -*- coding: utf-8 -*-
"""引け後（平日16時）に回す：今日の終値を貯めて、シグナルを判定し、明日の注文を用意する。

使い方:  py run_collect.py                 今日ぶん（kabuステーションAPIから取得 → 判定）
         py run_collect.py --date 2026-09-02 --no-fetch   取得は飛ばして判定だけ（データがある日の再実行）
         py run_collect.py --status

タスクスケジューラ（第5章 5-5）から run_collect.bat 経由で呼ぶ。
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import config                                   # noqa: E402
from kabu_auto import api, calendar as cal, data, paper  # noqa: E402


def collect(d: str) -> int:
    """対象銘柄の今日の四本値を kabuステーションAPI から取って CSV に足す。失敗した銘柄数を返す。"""
    try:
        token = api.get_token()
    except api.ApiError as e:
        paper.log(f"[ERROR] {e}")
        return len(config.SYMBOLS)
    failed = 0
    for code in config.SYMBOLS:
        try:
            b = api.board(token, code)
            paper.log(f"  {code} {b.get('SymbolName', '')}: {data.append_today(code, d, b)}")
        except api.ApiError as e:
            failed += 1
            paper.log(f"  {code}: 取得失敗 → {e}")
    try:
        api.unregister_all(token)   # 登録上限50の枠を空けておく（CLAUDE.md）
    except api.ApiError as e:
        paper.log(f"  [WARN] 登録解除に失敗: {e}")
    return failed


def live_tools():
    """実発注モードのとき、(注文約定照会, 残高照会) の関数を返す。paper なら (None, None)。

    トークンは1つだけ取って両方で使う（新しく取ると、前のトークンが無効になるため）。
    """
    if config.ORDER_MODE != "live":
        return None, None
    try:
        token = api.get_token()
    except api.ApiError as e:
        paper.log(f"  [WARN] 注文約定照会・残高照会の準備に失敗: {e}（約定は寄値の見積もりで記帳し、残高の突き合わせはしません）")
        return None, None
    return (lambda order_id: api.order_status(token, order_id)), (lambda: api.holdings(token))


def status_func_for_live():
    """（互換用）注文約定照会の関数だけ。"""
    return live_tools()[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=cal.today())
    ap.add_argument("--no-fetch", action="store_true", help="APIから取らず、手元のデータで判定だけ")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    if os.environ.get("KABU_GUI") and config.ORDER_MODE != "paper":
        # 画面（run_gui.py）から呼ばれたときは、発注しないモードでしか動かない（二重の安全策）
        print("NG: 画面からの操作は、config.py が発注しないモード（paper）のときだけ動きます。実弾の操作は start.py から行ってください。")
        return 1
    if a.status:
        print(paper.status())
        return 0
    d = a.date
    warn = cal.holiday_warning(d)
    if warn:
        paper.log(f"[WARN] {warn}")
    if not cal.is_trading_day(d):
        paper.log(f"[skip] {d} は休場です")
        return 0
    if not a.no_fetch:
        failed = collect(d)
        if failed:
            paper.log(f"[WARN] {failed} 銘柄の取得に失敗。黙って止まらないよう、ここに残します（第5章 5-5）")
    status_func, holdings_func = live_tools()
    paper.evening(d, status_func, holdings_func)
    return 0


if __name__ == "__main__":
    sys.exit(main())
