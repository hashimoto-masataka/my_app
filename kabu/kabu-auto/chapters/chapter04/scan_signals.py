# -*- coding: utf-8 -*-
"""主要100銘柄の移動平均クロスをまとめて判定し、サインが出た銘柄だけ表示する

使い方:  py scan_signals.py

- 移動平均の期間は ma_signal.py の SHORT_PERIOD / LONG_PERIOD に従う
- 「サインが出た」= 直近 RECENT_DAYS 営業日以内にクロスが発生したこと
- 最新営業日に出たサインには ★ を付ける
- 銘柄リストは下の SYMBOLS を編集すれば自由に変えられる
"""
import sys
import time
import unicodedata
import urllib.error

from ma_signal import (
    SHORT_PERIOD, LONG_PERIOD,
    fetch_daily_closes, moving_average, find_signals,
)

# ============ 設定 ============
RECENT_DAYS = 5        # 直近何営業日以内のサインを拾うか
FETCH_INTERVAL = 0.3   # データ取得の間隔(秒)。取得先に負荷をかけないため
# ==============================

# 主要100銘柄(コード, 名前)。編集して入れ替えてよい
SYMBOLS = [
    ("7203", "トヨタ自動車"), ("7267", "ホンダ"), ("7201", "日産自動車"),
    ("7269", "スズキ"), ("7270", "SUBARU"), ("6902", "デンソー"),
    ("7011", "三菱重工業"), ("7012", "川崎重工業"), ("7013", "IHI"),
    ("6301", "コマツ"), ("6326", "クボタ"), ("6367", "ダイキン工業"),
    ("6273", "SMC"), ("6954", "ファナック"), ("6501", "日立製作所"),
    ("6503", "三菱電機"), ("6752", "パナソニックHD"), ("6702", "富士通"),
    ("6701", "NEC"), ("6758", "ソニーグループ"), ("6971", "京セラ"),
    ("6981", "村田製作所"), ("6857", "アドバンテスト"), ("8035", "東京エレクトロン"),
    ("6146", "ディスコ"), ("6920", "レーザーテック"), ("6861", "キーエンス"),
    ("6594", "ニデック"), ("3436", "SUMCO"), ("7751", "キヤノン"),
    ("7731", "ニコン"), ("7733", "オリンパス"), ("4543", "テルモ"),
    ("4502", "武田薬品工業"), ("4503", "アステラス製薬"), ("4568", "第一三共"),
    ("4519", "中外製薬"), ("4523", "エーザイ"), ("4507", "塩野義製薬"),
    ("4578", "大塚HD"), ("4901", "富士フイルムHD"), ("4911", "資生堂"),
    ("4452", "花王"), ("4063", "信越化学工業"), ("4188", "三菱ケミカルG"),
    ("4183", "三井化学"), ("4005", "住友化学"), ("3407", "旭化成"),
    ("5401", "日本製鉄"), ("5411", "JFEHD"), ("5713", "住友金属鉱山"),
    ("5802", "住友電気工業"), ("5108", "ブリヂストン"), ("5201", "AGC"),
    ("5332", "TOTO"), ("2914", "JT"), ("2502", "アサヒGHD"),
    ("2503", "キリンHD"), ("2802", "味の素"), ("2801", "キッコーマン"),
    ("2269", "明治HD"), ("2897", "日清食品HD"), ("2002", "日清製粉G"),
    ("1332", "ニッスイ"), ("3382", "セブン&アイHD"), ("8267", "イオン"),
    ("9983", "ファーストリテイリング"), ("6098", "リクルートHD"),
    ("4755", "楽天グループ"), ("9433", "KDDI"), ("9432", "NTT"),
    ("9434", "ソフトバンク"), ("9984", "ソフトバンクG"), ("2413", "エムスリー"),
    ("4661", "オリエンタルランド"), ("9202", "ANAHD"), ("9201", "日本航空"),
    ("9020", "JR東日本"), ("9022", "JR東海"), ("9021", "JR西日本"),
    ("9101", "日本郵船"), ("9104", "商船三井"), ("9107", "川崎汽船"),
    ("9501", "東京電力HD"), ("9503", "関西電力"), ("9531", "東京ガス"),
    ("8058", "三菱商事"), ("8031", "三井物産"), ("8001", "伊藤忠商事"),
    ("8002", "丸紅"), ("8053", "住友商事"), ("8306", "三菱UFJFG"),
    ("8316", "三井住友FG"), ("8411", "みずほFG"), ("8604", "野村HD"),
    ("8766", "東京海上HD"), ("8591", "オリックス"), ("8801", "三井不動産"),
    ("8802", "三菱地所"), ("7974", "任天堂"),
]


def pad(text: str, width: int) -> str:
    """全角文字を2文字ぶんとして数え、指定幅まで空白を足す。"""
    visual = sum(2 if unicodedata.east_asian_width(c) in "FWA" else 1 for c in text)
    return text + " " * max(0, width - visual)


def main() -> int:
    print(f"{len(SYMBOLS)}銘柄を判定します "
          f"(短期{SHORT_PERIOD}日/長期{LONG_PERIOD}日、直近{RECENT_DAYS}営業日以内のサイン)")
    print()

    hits = []    # (コード, 名前, 日付, 種別, 最新営業日か)
    errors = []  # (コード, 名前, 理由)

    for i, (code, name) in enumerate(SYMBOLS):
        if i > 0:
            time.sleep(FETCH_INTERVAL)
        try:
            data = fetch_daily_closes(code)
        except (urllib.error.URLError, RuntimeError) as e:
            errors.append((code, name, str(e)))
            continue

        if len(data) < LONG_PERIOD + 1:
            errors.append((code, name, f"データ不足({len(data)}日分)"))
            continue

        dates = [d for d, _ in data]
        closes = [c for _, c in data]
        short_ma = moving_average(closes, SHORT_PERIOD)
        long_ma = moving_average(closes, LONG_PERIOD)
        signals = find_signals(dates, short_ma, long_ma)

        recent_dates = set(dates[-RECENT_DAYS:])
        for date, kind in signals:
            if date in recent_dates:
                hits.append((code, name, date, kind, date == dates[-1]))

        done = i + 1
        if done % 20 == 0:
            print(f"  … {done}/{len(SYMBOLS)} 銘柄まで判定済み")

    print()
    if not hits:
        print(f"直近{RECENT_DAYS}営業日以内にサインが出た銘柄はありませんでした。")
    else:
        print(f"■ サインが出た銘柄: {len(hits)}件 (★=最新営業日)")
        print()
        print(f"{'コード':<6} {pad('銘柄名', 22)} {'日付':<12} {'サイン'}")
        print("-" * 50)
        for code, name, date, kind, is_latest in sorted(hits, key=lambda h: (h[2], h[0])):
            star = " ★" if is_latest else ""
            print(f"{code:<6} {pad(name, 22)} {date:<12} {kind}{star}")

    if errors:
        print()
        print(f"■ 判定できなかった銘柄: {len(errors)}件")
        for code, name, reason in errors:
            print(f"  {code} {name}: {reason}")

    print()
    print(f"判定完了: {len(SYMBOLS) - len(errors)}/{len(SYMBOLS)} 銘柄")
    return 0


if __name__ == "__main__":
    sys.exit(main())
