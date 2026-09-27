# -*- coding: utf-8 -*-
"""kabu-auto の設定（単一の正本）。いじるのは基本ここだけ。

「実発注モードに切り替えて」と頼まれたら、Claude Code は ORDER_MODE を "live" に変える。
それ以外の理由で "live" にしてはいけない（付録A「安全（変更禁止）」）。
"""
from pathlib import Path

# ---- 対象銘柄（第4章のリストから。kabuステーションAPIの登録上限は50なので 20〜30 まで）
SYMBOLS = [
    "7203",  # トヨタ自動車
    "6758",  # ソニーグループ
    "9984",  # ソフトバンクグループ
    "8306",  # 三菱UFJフィナンシャル・グループ
    "9432",  # NTT
    "6861",  # キーエンス
    "8035",  # 東京エレクトロン
    "9983",  # ファーストリテイリング
    "4063",  # 信越化学工業
    "7974",  # 任天堂
]

# ---- 戦略（第4章の移動平均クロス。第6章の教訓：この数字を「最適化」しない）
SHORT_PERIOD = 5
LONG_PERIOD = 25

# ---- 発注
ORDER_MODE = "paper"        # "paper" = 発注しないモード（既定） / "live" = 実発注
DAILY_ORDER_LIMIT = 3       # 1日に出してよい注文の上限（暴走の被害を抑える）
BUDGET_PER_ORDER = 500_000  # 1回の買いに使う上限金額（円）。株数は「この金額に収まる最大の単元数」で決める（sizing.py）。
                            # 1単元がこの金額を超える銘柄（高額銘柄）は、買わずに見送る（ログに残る）。None にすると下の QTY 固定に戻る
QTY = 100                   # BUDGET_PER_ORDER が None のときの固定株数。試し撃ち（start.py の t）は、この設定に関係なく「1単元」だけ
LOT_SIZE = 100              # 既定の単元株数
LOT_SIZES = {}              # 単元が違う銘柄だけ書く。例: {"1234": 1}（対象に加える前に、証券会社の画面で単元株数を確認する）
ACCOUNT_TYPE = 4            # 口座区分: 2=一般 / 4=特定 / 12=法人
ENV = "prod"                # "prod" = 本番(18080) / "test" = 検証(18081)。三点セット（1-5）を揃えること
CONFIRM_WORD = "実弾"        # 実弾モードの合言葉。start.py がこの言葉を打つまで先に進まない。
                            # 変えてよい。"" にすると合言葉なし（おすすめしない。うっかりで本物の注文が飛ぶ）

# ---- 接続
API_BASE = {"prod": "http://localhost:18080/kabusapi", "test": "http://localhost:18081/kabusapi"}[ENV]
EXCHANGE = 1                # 板情報（/board）は東証
ORDER_EXCHANGE = 9          # 注文の市場: 9=SOR。通常時は「1=東証」を指定した現物の新規注文は拒否される（エラー100378）。
                            # 手数料無料化の条件も「SOR選択」（第7章 7-2 ②）。SOR がメンテナンス中のときだけ 1 が使える
REQUEST_INTERVAL = 0.15     # 情報系は 10件/秒 まで → 約 6.7件/秒 に抑える（第3章）
MAX_RETRIES = 3
API_PASSWORD_ENV = "KABU_API_PASSWORD"          # 本番用 APIパスワード（1-4）
API_PASSWORD_ENV_TEST = "KABU_API_PASSWORD_TEST"  # 検証用 APIパスワード（1-4 の「検証用」欄。三点セット・図1-5）

# ---- 置き場所（このフォルダの中で完結する）
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "daily"      # {code}.csv  Date,Open,High,Low,Close,Volume
STATE_FILE = ROOT / "state" / "account.json"
LOG_DIR = ROOT / "logs"
HOLIDAYS_FILE = ROOT / "data" / "holidays.txt"   # 1行1日 YYYY-MM-DD（土日以外の休場日）。その年の分が無いと実発注は止まる（calendar.py）

# ---- データの安全策（第5章 5-6）
JUMP_LIMIT = (0.6, 1.6)     # 前日比がこの範囲を外れたら「分割・併合や、調整済み/未調整の混在」を疑う（data.py）。
                            # 直近 LONG_PERIOD 日にそういう段差がある銘柄は、シグナルを出さない（移動平均が誤爆するため）

# ---- バックテスト（第6章。窓の長さは結果を見る前に決める）
TRAIN_DAYS = 500
TEST_DAYS = 125
# 約定の想定は実運用と同じ：シグナルが出た日の「翌営業日の寄値」で約定する。片道ぶんのコストを不利な向きに乗せる（1bp = 0.01%）
BACKTEST_SLIPPAGE_BPS = 10  # 寄成のずれの見積もり（片道）。実測（第7章 7-2）で置き換える。仮の値
BACKTEST_FEE_BPS = 0        # 手数料（片道）。SOR 選択で無料の想定（第7章 7-2 ②）。条件が変わったらここを直す
BACKTEST_TAX_RATE = 0.20315 # 税引後（概算）の表示に使う税率。特定口座・源泉徴収ありの譲渡益課税（所得税15.315% + 住民税5%）の想定。
                            # NISA など非課税の口座なら 0 に。あくまで概算（下の backtest.after_tax の注意を参照）。税務の判断は専門家か税務署へ

# ---- 手元だけの上書き（config_local.py。.gitignore 済みで配布しない）
#   例: ENV_FILE = r"C:\path\to\.env"  … 環境変数が無いとき、この .env から KABU_API_PASSWORD を読む
ENV_FILE = None
try:
    from config_local import *  # noqa: F401,F403
except ImportError:
    pass
