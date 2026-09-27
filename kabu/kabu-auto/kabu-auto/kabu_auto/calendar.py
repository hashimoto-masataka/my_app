# -*- coding: utf-8 -*-
"""営業日の判定。土日と、data/holidays.txt に書いた休場日を除く。

休場日の一覧は kabuステーションAPIからは取れない。JPX の公式カレンダー（J-Quants の
取引カレンダーAPI・無料プランで可）から作るか、Claude Code に「今年の東証の休場日を
holidays.txt に書いて」と頼む。年末年始（12/31〜1/3）は書かなくても休みとして扱う。
"""
import datetime as _dt
from functools import lru_cache
from pathlib import Path

import config


@lru_cache(maxsize=4)
def _read(path: str, mtime: float) -> frozenset:
    days = set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if len(s) >= 10 and s[0] != "#":
            days.add(s[:10])
    return frozenset(days)


def holidays() -> set:
    """休場日の集合。ファイルを書き換えたら（更新時刻が変われば）読み直す。"""
    p = config.HOLIDAYS_FILE
    if not p.is_file():
        return set()
    return set(_read(str(p), p.stat().st_mtime))


def holiday_warning(d: str) -> str:
    """d の年の休場日が holidays.txt に書かれていなければ、その説明。大丈夫なら ""。

    休場日ファイルが無い／その年の分が無いと、祝日を営業日と見なして動いてしまう
    （実発注では、休場日に注文を出したり、前日の終値を「今日の分」として貯めたりする）。
    """
    if not config.HOLIDAYS_FILE.is_file():
        return (f"休場日ファイル（{config.HOLIDAYS_FILE.name}）がありません。祝日を営業日と見なしてしまいます。"
                "東証の休場日を1行1日（YYYY-MM-DD）で書いてください（README「最初にやること」4）")
    if not any(h.startswith(d[:4]) for h in holidays()):
        return (f"休場日ファイルに {d[:4]} 年の休場日がありません。祝日を営業日と見なしてしまいます。"
                f"{d[:4]} 年の東証の休場日を書き足してください")
    return ""


def to_date(s: str) -> _dt.date:
    return _dt.date(int(s[0:4]), int(s[5:7]), int(s[8:10]))


def is_trading_day(s: str) -> bool:
    d = to_date(s)
    if d.weekday() >= 5:
        return False
    if (d.month == 12 and d.day == 31) or (d.month == 1 and d.day <= 3):
        return False
    return s not in holidays()


def next_trading_day(s: str) -> str:
    d = to_date(s) + _dt.timedelta(days=1)
    while not is_trading_day(f"{d:%Y-%m-%d}"):
        d += _dt.timedelta(days=1)
    return f"{d:%Y-%m-%d}"


def today() -> str:
    return f"{_dt.date.today():%Y-%m-%d}"
