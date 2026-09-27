# -*- coding: utf-8 -*-
"""日足データの置き場（第5章）。

形式: data/daily/{code}.csv   Date,Open,High,Low,Close,Volume（古い順・1日1行）
  過去 … J-Quants や yfinance で取った CSV を import_csv() でこの形に揃えて入れる
  今日 … 引け後に kabuステーションAPI の板情報（OpeningPrice/HighPrice/LowPrice/CurrentPrice/
         TradingVolume）を append_today() で1行足す

CLAUDE.md のとおり、実データのみ。ダミーは作らない。
"""
import csv
from pathlib import Path

import config

COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume"]
ADJUSTED_COLUMNS = {"AdjustmentClose", "AdjC", "Adj Close"}
last_import_note = ""       # import_csv の直後に、取り込みの注意（あれば）が入る

# 入手先ごとの列名の違いを吸収する（左が本書の列名、右が候補）
ALIASES = {
    "Date": ["Date", "date", "日付"],
    "Open": ["Open", "AdjustmentOpen", "AdjO", "O", "open"],
    "High": ["High", "AdjustmentHigh", "AdjH", "H", "high"],
    "Low": ["Low", "AdjustmentLow", "AdjL", "L", "low"],
    "Close": ["Close", "AdjustmentClose", "AdjC", "C", "close", "Adj Close"],
    "Volume": ["Volume", "AdjustmentVolume", "AdjV", "V", "volume"],
}


def path_of(code: str) -> Path:
    return config.DATA_DIR / f"{code}.csv"


def load(code: str) -> list:
    """[{Date, Open, High, Low, Close, Volume}, ...] を古い順で。無ければ []。"""
    p = path_of(code)
    if not p.is_file():
        return []
    rows = []
    with p.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            try:
                rows.append({"Date": r["Date"][:10], "Open": float(r["Open"] or 0), "High": float(r["High"] or 0),
                             "Low": float(r["Low"] or 0), "Close": float(r["Close"]), "Volume": float(r["Volume"] or 0)})
            except (KeyError, ValueError):
                continue
    rows.sort(key=lambda x: x["Date"])
    return rows


def save(code: str, rows: list) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    seen, out = set(), []
    for r in sorted(rows, key=lambda x: x["Date"]):
        if r["Date"] in seen:
            continue
        seen.add(r["Date"])
        out.append(r)
    tmp = path_of(code).with_suffix(".csv.tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in out:
            w.writerow({k: r.get(k, "") for k in COLUMNS})
    tmp.replace(path_of(code))


def closes(code: str, until: str = None) -> tuple:
    """(dates, closes)。until を指定するとその日まで。"""
    rows = [r for r in load(code) if until is None or r["Date"] <= until]
    return [r["Date"] for r in rows], [r["Close"] for r in rows]


def series(code: str, until: str = None) -> tuple:
    """(dates, opens, closes)。寄値の列が無い（0）日は終値で代用する（open_of と同じ扱い）。"""
    rows = [r for r in load(code) if until is None or r["Date"] <= until]
    return [r["Date"] for r in rows], [(r["Open"] or r["Close"]) for r in rows], [r["Close"] for r in rows]


def open_of(code: str, date: str):
    """date の寄値。寄値の列が無いデータ（終値だけの CSV）なら終値で代用する。"""
    for r in load(code):
        if r["Date"] == date:
            return r["Open"] or r["Close"] or None
    return None


def price_date(board: dict) -> str:
    """板情報の現値時刻（CurrentPriceTime、例 2026-09-18T15:00:00+09:00）の日付。読めなければ ""。"""
    t = str(board.get("CurrentPriceTime") or "")[:10]
    try:
        y, m, d = int(t[0:4]), int(t[5:7]), int(t[8:10])
        return f"{y:04d}-{m:02d}-{d:02d}" if t[4] == "-" and t[7] == "-" and 1 <= m <= 12 and 1 <= d <= 31 else ""
    except (ValueError, IndexError):
        return ""


def append_today(code: str, date: str, board: dict) -> str:
    """板情報（/board の応答）から今日の1行を足す。戻り値は結果の説明（ログ用）。

    板の値は「最後に付いた値」。休場日や、値が付かなかった日は、前の営業日の終値が返る。
    現値時刻の日付が date と違えば、それを今日の終値として貯めてはいけないので書かない（休場日ファイルの抜けの保険にもなる）。
    """
    close = board.get("CurrentPrice")
    if close is None:
        return "値が付いていない（休場・取得時刻が早い?）ので書きません"
    pd = price_date(board)
    if not pd:
        return (f"現値時刻（CurrentPriceTime={board.get('CurrentPriceTime')!r}）が読めないので書きません。"
                "今日の値か確認できない値は貯めません")
    if pd != date:
        return (f"現値時刻が {pd} で、今日（{date}）の値ではないので書きません"
                "（休場日か、今日は値が付かなかった。休場日なら休場日ファイルに足す）")
    rows = load(code)
    if rows and rows[-1]["Date"] == date:
        return "今日の分はすでにあります（上書きしません）"
    row = {"Date": date, "Open": board.get("OpeningPrice") or 0, "High": board.get("HighPrice") or 0,
           "Low": board.get("LowPrice") or 0, "Close": close, "Volume": board.get("TradingVolume") or 0}
    warn = split_warning(rows, row)
    rows.append(row)
    save(code, rows)
    return f"追記 {date} 終値 {close:,.1f}" + (f"　★{warn}" if warn else "")


def split_warning(rows: list, new_row: dict) -> str:
    """前日比で ±40% を超えたら、暴落ではなく株式分割・併合を疑う（第5章 5-6）。"""
    if not rows:
        return ""
    prev = rows[-1]["Close"]
    if prev and (new_row["Close"] / prev < 0.6 or new_row["Close"] / prev > 1.6):
        return f"前日比 {new_row['Close'] / prev:.2f} 倍。株式分割・併合の可能性。移動平均が誤爆するので確認すること"
    return ""


def jumps(rows: list) -> list:
    """前日比が config.JUMP_LIMIT を外れた日 [(日付, 倍率), ...]。分割・併合、調整済み/未調整の混在の疑い。"""
    lo, hi = config.JUMP_LIMIT
    out = []
    for prev, cur in zip(rows, rows[1:]):
        if prev["Close"] and cur["Close"]:
            r = cur["Close"] / prev["Close"]
            if r < lo or r > hi:
                out.append((cur["Date"], r))
    return out


def recent_jump(code: str, until: str, days: int) -> tuple:
    """until までの直近 days 本の終値の中に段差があれば (日付, 倍率)。なければ None。移動平均が誤爆する。"""
    rows = [r for r in load(code) if r["Date"] <= until][-(days + 1):]
    j = jumps(rows)
    return j[-1] if j else None


def audit(code: str) -> list:
    """データの点検。人が読む警告のリストを返す（空なら問題なし）。

    - 段差（前日比が JUMP_LIMIT の外）
    - 欠け（営業日なのに行が無い。取得失敗の日など）
    - 値が0や欠けの行
    """
    from kabu_auto import calendar as cal
    rows = load(code)
    out = []
    if not rows:
        return [f"{code}: データがありません"]
    for d, r in jumps(rows):
        out.append(f"{code}: {d} に前日比 {r:.2f} 倍の段差。分割・併合か、調整済み/未調整の株価の混在の疑い。直近 {config.LONG_PERIOD} 日以内なら、この銘柄のシグナルは出しません")
    have = {r["Date"] for r in rows}
    missing, d = [], cal.to_date(rows[0]["Date"])
    end = cal.to_date(rows[-1]["Date"])
    while d < end:
        s = f"{d:%Y-%m-%d}"
        if cal.is_trading_day(s) and s not in have:
            missing.append(s)
        d += __import__("datetime").timedelta(days=1)
    if missing:
        head = ", ".join(missing[:5]) + (f" ほか{len(missing) - 5}日" if len(missing) > 5 else "")
        out.append(f"{code}: 営業日なのに行が無い日が {len(missing)} 日あります（{head}）。取得失敗か、休場日ファイルの抜け")
    bad = [r["Date"] for r in rows if not r["Close"] or r["Close"] <= 0]
    if bad:
        out.append(f"{code}: 終値が0以下の行があります（{bad[0]} ほか）")
    return out


def import_csv(code: str, src: Path) -> int:
    """J-Quants / yfinance / KABU+ などの CSV を本書の形に揃えて取り込む。戻り値は取り込んだ行数。

    調整後の列（AdjustmentClose / AdjC / Adj Close）を使ったときは、引け後に kabuステーションAPI から足す「今日の値」
    （調整されていない実際の値）と段差ができうる。取り込み結果の説明は last_import_note に入れる。
    """
    with Path(src).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        colmap = {}
        for key, cands in ALIASES.items():
            for c in cands:
                if c in header:
                    colmap[key] = c
                    break
        if "Date" not in colmap or "Close" not in colmap:
            raise ValueError(f"日付と終値の列が見つかりません: {header}")
        global last_import_note
        last_import_note = ""
        if colmap["Close"] in ADJUSTED_COLUMNS:
            last_import_note = (f"終値に調整後の列（{colmap['Close']}）を使いました。今日から貯める値（kabuステーションAPI）は調整されていない実際の値です。"
                                "株式分割があった銘柄は、境目で段差ができるので、取り込み後に audit で点検してください")
        rows = load(code)
        have = {r["Date"] for r in rows}
        n = 0
        for r in reader:
            d = (r[colmap["Date"]] or "")[:10].replace("/", "-")
            if len(d) != 10 or d in have:
                continue
            try:
                rows.append({"Date": d,
                             "Open": float(r.get(colmap.get("Open", ""), "") or 0),
                             "High": float(r.get(colmap.get("High", ""), "") or 0),
                             "Low": float(r.get(colmap.get("Low", ""), "") or 0),
                             "Close": float(r[colmap["Close"]]),
                             "Volume": float(r.get(colmap.get("Volume", ""), "") or 0)})
                n += 1
            except ValueError:
                continue
    save(code, rows)
    return n
