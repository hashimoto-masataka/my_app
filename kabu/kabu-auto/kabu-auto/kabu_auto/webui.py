# -*- coding: utf-8 -*-
"""ブラウザで操作する画面（このPCだけで開く）。標準ライブラリだけ。

できること: 建玉・注文・損益・データ・ログを見る／チャートを見る／バックテストとデータ点検を回す／
            過去データ(CSV)を取り込む／ペーパーの「収集と判定」「朝の確認」を押す。
できないこと: 実発注。この画面は発注の関数を一切呼ばない（発注できるコードは start.py と run_morning.py だけ、という
            CLAUDE.md の約束を守る）。ペーパーの操作は、config.ORDER_MODE が "paper" のときだけ動く。

安全のつくり:
  - 127.0.0.1（このPC）だけで待ち受ける。Host / Origin を確かめる（他のサイトから操作されない）
  - 操作（POST）には、起動のたびに作る合言葉のトークンが要る
  - 実際の処理は run_collect.py などを別プロセスで動かす（画面のコードは帳簿を書き換えない）
"""
import importlib
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import config
from kabu_auto import calendar as cal
from kabu_auto import data, paper, strategy

CODE_RE = re.compile(r"^[0-9A-Za-z]{4,5}$")
MAX_UPLOAD = 20 * 1024 * 1024
JOB_TIMEOUT = 20 * 60
MAX_LINES = 3000


# ---------------------------------------------------------------- 仕事（別プロセス）

class JobRunner:
    """一度に1つだけ、決まったスクリプトを別プロセスで動かし、出力を貯める。"""

    def __init__(self):
        self._lock = threading.Lock()
        self.job = None

    def running(self) -> bool:
        return self.job is not None and self.job["rc"] is None

    def start(self, label: str, argv: list):
        with self._lock:
            if self.running():
                return None
            job = {"id": int(time.time() * 1000), "label": label, "lines": [], "rc": None, "started": time.time()}
            self.job = job
        threading.Thread(target=self._run, args=(job, argv), daemon=True).start()
        return job

    def _run(self, job: dict, argv: list) -> None:
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1", KABU_GUI="1")
        try:
            p = subprocess.Popen(argv, cwd=str(config.ROOT), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, env=env)
            timer = threading.Timer(JOB_TIMEOUT, p.kill)
            timer.start()
            for raw in p.stdout:
                if len(job["lines"]) < MAX_LINES:
                    job["lines"].append(raw.decode("utf-8", "replace").rstrip("\r\n"))
            p.stdout.close()
            job["rc"] = p.wait()
            timer.cancel()
        except Exception as e:  # noqa: BLE001
            job["lines"].append(f"起動できませんでした: {e}")
            job["rc"] = -1

    def snapshot(self) -> dict:
        j = self.job
        if j is None:
            return {"running": False, "id": None, "label": "", "rc": None, "lines": []}
        return {"running": j["rc"] is None, "id": j["id"], "label": j["label"], "rc": j["rc"], "lines": list(j["lines"])}


# 画面から動かせるもの（これ以外は動かさない）。needs_paper は config が paper のときだけ。
ACTIONS = {
    "collect": ("ペーパー: 今日の収集と判定", True),
    "collect_nofetch": ("ペーパー: 手元のデータで判定だけ", True),
    "morning": ("ペーパー: 朝の確認", True),
    "audit": ("データの点検", False),
    "backtest": ("バックテスト", False),
}


def build_argv(name: str, params: dict) -> list:
    py = [sys.executable, "-X", "utf8"]
    code = str(params.get("code") or "")
    if name == "collect":
        return py + ["run_collect.py"]
    if name == "collect_nofetch":
        return py + ["run_collect.py", "--no-fetch"]
    if name == "morning":
        return py + ["run_morning.py"]
    if name == "audit":
        return py + ["run_backtest.py", "--audit"] + ([code] if code else [])
    if name == "backtest":
        argv = py + ["run_backtest.py", code]
        if params.get("grid"):
            argv.append("--grid")
        if params.get("walk"):
            argv.append("--walk")
        return argv
    raise ValueError(name)


# ---------------------------------------------------------------- 画面に出す情報

def _last_lines(path: Path, n: int = 80) -> list:
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            f.seek(max(0, size - 64 * 1024))
            text = f.read().decode("utf-8", "replace")
        return text.splitlines()[-n:]
    except OSError:
        return []


def symbol_rows() -> list:
    out = []
    for code in config.SYMBOLS:
        rows = data.load(code)
        dates = [r["Date"] for r in rows]
        closes = [r["Close"] for r in rows]
        sig, trend = "", ""
        if len(closes) > config.LONG_PERIOD:
            sig = strategy.latest_signal(dates, closes)
            s = strategy.moving_average(closes, config.SHORT_PERIOD)[-1]
            lg = strategy.moving_average(closes, config.LONG_PERIOD)[-1]
            trend = "短期が上" if s > lg else "短期が下"
        jump = data.recent_jump(code, dates[-1], config.LONG_PERIOD) if dates else None
        out.append({"code": code, "rows": len(rows), "first": dates[0] if dates else "", "last": dates[-1] if dates else "",
                    "close": closes[-1] if closes else None, "signal": sig, "trend": trend,
                    "jump": f"{jump[0]} に前日比 {jump[1]:.2f} 倍" if jump else "",
                    "enough": len(closes) >= config.LONG_PERIOD + 2})
    return out


def build_state(jobs: JobRunner) -> dict:
    st = paper.load()
    today = cal.today()
    last_close = {}
    for code in st["positions"]:
        _, closes = data.closes(code)
        last_close[code] = closes[-1] if closes else None
    positions = []
    for code, p in st["positions"].items():
        lc = last_close.get(code)
        positions.append({"code": code, **p, "last_close": lc,
                          "unrealized": (lc - p["entry_px"]) * p["qty"] if lc else None})
    days = sorted(st["days"].items())
    return {
        "today": today,
        "is_trading_day": cal.is_trading_day(today),
        "holiday_warning": cal.holiday_warning(today),
        "mode": config.ORDER_MODE,
        "env": config.ENV,
        "settings": {"short": config.SHORT_PERIOD, "long": config.LONG_PERIOD, "budget": config.BUDGET_PER_ORDER,
                     "qty": config.QTY, "daily_limit": config.DAILY_ORDER_LIMIT, "symbols": len(config.SYMBOLS),
                     "slippage_bps": config.BACKTEST_SLIPPAGE_BPS, "fee_bps": config.BACKTEST_FEE_BPS,
                     "tax_rate": config.BACKTEST_TAX_RATE},
        "ledger": {"cumulative_pnl": st["cumulative_pnl"], "positions": positions, "pending": st["pending"],
                   "unfilled": st["unfilled"][-20:], "updated_at": st.get("updated_at", ""),
                   "days": [{"date": d, "pnl": v["pnl"], "cumulative_pnl": v["cumulative_pnl"],
                             "signals": len(v["signals"]), "filled": len(v["filled"]), "skipped": v.get("skipped", [])}
                            for d, v in days[-120:]],
                   "orders": st["orders"][-20:]},
        "symbols": symbol_rows(),
        "log": _last_lines(config.LOG_DIR / "kabu-auto.log"),
        "job": jobs.snapshot(),
    }


def build_chart(code: str, n: int = 250) -> dict:
    rows = data.load(code)
    dates = [r["Date"] for r in rows]
    closes = [r["Close"] for r in rows]
    ma_s = strategy.moving_average(closes, config.SHORT_PERIOD)
    ma_l = strategy.moving_average(closes, config.LONG_PERIOD)
    sigs = strategy.find_signals(dates, ma_s, ma_l)
    start = max(0, len(dates) - n)
    index = {d: i for i, d in enumerate(dates)}
    return {"code": code, "dates": dates[start:], "close": closes[start:], "ma_s": ma_s[start:], "ma_l": ma_l[start:],
            "signals": [{"i": index[d] - start, "side": k} for d, k in sigs if index[d] >= start],
            "short": config.SHORT_PERIOD, "long": config.LONG_PERIOD}


def import_upload(code: str, body: bytes) -> dict:
    """ブラウザから送られた CSV を取り込む。文字コードは UTF-8 か Shift-JIS(cp932)。"""
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = body.decode("cp932")
    fd, tmp = tempfile.mkstemp(suffix=".csv")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        n = data.import_csv(code, Path(tmp))
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return {"rows": n, "note": data.last_import_note, "warnings": data.audit(code)}


# ---------------------------------------------------------------- サーバー

class Handler(BaseHTTPRequestHandler):
    server_version = "kabu-auto-gui"

    def log_message(self, *a):          # コンソールを汚さない
        pass

    # --- 共通
    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        if host not in ("127.0.0.1", "localhost"):
            return False
        origin = self.headers.get("Origin")
        if origin:
            o = urlparse(origin)
            if o.hostname not in ("127.0.0.1", "localhost") or (o.port or 80) != self.server.server_port:
                return False
        return True

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src 'self' data:")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _err(self, code: int, msg: str) -> None:
        self._json({"error": msg}, code)

    def _token_ok(self) -> bool:
        return secrets.compare_digest(self.headers.get("X-Token") or "", self.server.token)

    # --- GET
    def do_GET(self):
        if not self._host_ok():
            return self._err(403, "このアドレスでは開けません（127.0.0.1 か localhost で開いてください）")
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path == "/":
                html = INDEX_HTML.replace("__TOKEN__", self.server.token)
                return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            if u.path == "/api/state":
                self.server.refresh_config()
                return self._json(build_state(self.server.jobs))
            if u.path == "/api/job":
                return self._json(self.server.jobs.snapshot())
            if u.path == "/api/chart":
                code = (q.get("code") or [""])[0]
                if not CODE_RE.match(code):
                    return self._err(400, "銘柄コードが正しくありません")
                return self._json(build_chart(code))
        except Exception as e:  # noqa: BLE001
            return self._err(500, f"内部エラー: {e}")
        return self._err(404, "見つかりません")

    # --- POST
    def do_POST(self):
        if not self._host_ok():
            return self._err(403, "このアドレスでは操作できません")
        if not self._token_ok():
            return self._err(403, "画面を開き直してください（操作の合言葉が合いません）")
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_UPLOAD:
                return self._err(413, "ファイルが大きすぎます（20MBまで）")
            body = self.rfile.read(length) if length else b""
            if u.path == "/api/run":
                return self._run(json.loads(body.decode("utf-8") or "{}"))
            if u.path == "/api/import":
                code = (q.get("code") or [""])[0]
                if not CODE_RE.match(code):
                    return self._err(400, "銘柄コードが正しくありません（4〜5桁の英数字）")
                if not body:
                    return self._err(400, "ファイルが空です")
                return self._json(import_upload(code, body))
        except (ValueError, UnicodeDecodeError) as e:
            return self._err(400, str(e))
        except Exception as e:  # noqa: BLE001
            return self._err(500, f"内部エラー: {e}")
        return self._err(404, "見つかりません")

    def _run(self, req: dict):
        name = req.get("name")
        if name not in ACTIONS:
            return self._err(400, "そのような操作はありません")
        label, needs_paper = ACTIONS[name]
        self.server.refresh_config()
        if needs_paper and config.ORDER_MODE != "paper":
            return self._err(403, "config.py が実発注モード（live）です。この画面のペーパー操作は、発注しないモード（paper）のときだけ使えます。"
                                  "実弾の操作は、これまでどおり start.py から行ってください")
        code = str(req.get("code") or "")
        if name == "backtest" and not CODE_RE.match(code):
            return self._err(400, "銘柄コードを選んでください")
        if name == "audit" and code and not CODE_RE.match(code):
            return self._err(400, "銘柄コードが正しくありません")
        job = self.server.jobs.start(label, build_argv(name, {"code": code, "grid": bool(req.get("grid")), "walk": bool(req.get("walk"))}))
        if job is None:
            return self._err(409, "ほかの操作が実行中です。終わってからもう一度押してください")
        return self._json({"started": True, "id": job["id"]})


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr, reload_config: bool = True):
        super().__init__(addr, Handler)
        self.token = secrets.token_urlsafe(24)
        self.jobs = JobRunner()
        self._reload = reload_config
        self._cfg_lock = threading.Lock()

    def refresh_config(self) -> None:
        """config.py を書き換えたら、画面を開き直さなくても反映する。"""
        if self._reload:
            with self._cfg_lock:
                importlib.reload(config)


def make_server(port: int = 8765, reload_config: bool = True) -> Server:
    return Server(("127.0.0.1", port), reload_config)


INDEX_HTML = Path(__file__).with_name("webui.html").read_text(encoding="utf-8")
