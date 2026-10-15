# 업데이트날짜: 2026.10.15
# 작성자: j-neat
# 아이폰용 앱(PWA) 서버 — 슬랙과 별도로 휴대폰에서 시그널 확인 / 푸시 알림 / 봇 실행
#
# 실행: python web_app.py  또는 start_app.bat 더블클릭 (스케줄러 포함 — scheduler.py 를 같이 켜면 중복 실행되니 하나만)
#   - 아이폰 접속: Tailscale 로 연결 후 `tailscale serve --bg 8000` → https://<PC이름>.<tailnet>.ts.net
#     (기본은 이 PC 안(127.0.0.1)에서만 열림 — Tailscale 이 HTTPS 로 중계하므로 외부에 포트를 열 필요 없음)
#   - 같은 와이파이에서 테스트만 할 때: .env 에 APP_HOST=0.0.0.0 → http://<PC의 IP>:8000 (푸시 알림은 HTTPS 에서만 동작)
# .env 옵션:
#   APP_TOKEN=비밀번호      → 앱 첫 화면에서 입력해야 사용 가능 (없으면 잠금 없음, Tailscale 안에서만 쓰면 생략 가능)
#   APP_PORT=8000           → 포트 변경
#   APP_HOST=127.0.0.1      → 0.0.0.0 이면 같은 와이파이의 다른 기기에서도 접속 가능
#   APP_SCHEDULER=0         → 서버 안의 자동 실행 끄기 (scheduler.py 를 따로 돌리는 경우)

import os
import sys
import time
import glob
import threading
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pandas as pd
import yfinance as yf
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()

import db_manager as db
from push_notifier import get_public_key, send_push_all
from scheduler import KR_RUN_TIMES, US_RUN_TIMES, KST, NY, due_jobs
from data_collector import INDEX_BY_MARKET

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "app_static")
LOG_DIR = os.path.join(os.path.dirname(db.DB_PATH), "logs")
LOG_RETENTION_DAYS = 30
APP_TOKEN = os.environ.get("APP_TOKEN", "").strip()
APP_PORT = int(os.environ.get("APP_PORT", "8000"))
APP_HOST = os.environ.get("APP_HOST", "127.0.0.1")
SCHEDULER_ENABLED = os.environ.get("APP_SCHEDULER", "1") != "0"
MARKET_LABEL = {"KR": "한국장", "US": "미국장"}

@asynccontextmanager
async def lifespan(_app):
    """서버 시작 시: 멈춘 실행 기록 정리, 오래된 로그 삭제, 자동 실행 스레드 시작"""
    db.mark_stale_runs_failed()
    cleanup_logs()
    if SCHEDULER_ENABLED:
        threading.Thread(target=scheduler_loop, daemon=True).start()
        print(f"⏰ 자동 실행 켜짐 — 한국장(KST): {', '.join(KR_RUN_TIMES)} / 미국장(뉴욕): {', '.join(US_RUN_TIMES)}")
    print(f"📱 앱 서버 시작: http://localhost:{APP_PORT}  (잠금: {'켜짐' if APP_TOKEN else '꺼짐'})")
    yield

app = FastAPI(title="Quant Signal", docs_url=None, redoc_url=None, lifespan=lifespan)


# ---------------------------------------------------------
# 잠금 (APP_TOKEN 이 설정된 경우만)
# ---------------------------------------------------------
PUBLIC_PATHS = ("/", "/index.html", "/manifest.webmanifest", "/sw.js", "/api/auth", "/api/login")

@app.middleware("http")
async def token_guard(request: Request, call_next):
    path = request.url.path
    if APP_TOKEN and not (path in PUBLIC_PATHS or path.startswith("/static/")):
        if request.cookies.get("qt") != APP_TOKEN:
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
    return await call_next(request)

@app.get("/api/auth")
def auth_status(request: Request):
    return {"required": bool(APP_TOKEN), "ok": (not APP_TOKEN) or request.cookies.get("qt") == APP_TOKEN}

@app.post("/api/login")
async def login(request: Request):
    body = await request.json()
    if not APP_TOKEN or body.get("token") == APP_TOKEN:
        resp = JSONResponse({"ok": True})
        if APP_TOKEN:
            resp.set_cookie("qt", APP_TOKEN, max_age=60 * 60 * 24 * 365, httponly=True, samesite="lax")
        return resp
    time.sleep(1)  # 무작위 대입 지연
    raise HTTPException(401, "비밀번호가 틀렸어요")

# ---------------------------------------------------------
# 봇 실행 관리 (스케줄 + 수동)
# ---------------------------------------------------------
class BotRunner:
    def __init__(self):
        self.lock = threading.Lock()
        self.current = None  # {"id", "market", "trigger", "started", "log_path"}

    def start(self, market, trigger):
        """실행 시작. 이미 실행 중이면 None"""
        with self.lock:
            if self.current:
                return None
            os.makedirs(LOG_DIR, exist_ok=True)
            log_path = os.path.join(LOG_DIR, f"{datetime.now(KST).strftime('%Y%m%d_%H%M%S')}_{market}.log")
            run_id = db.start_bot_run(market, trigger, log_path)
            self.current = {"id": run_id, "market": market, "trigger": trigger,
                            "started": time.time(), "log_path": log_path}
        threading.Thread(target=self._run, args=(run_id, market, log_path), daemon=True).start()
        return run_id

    def _run(self, run_id, market, log_path):
        status = "failed"
        try:
            env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
            with open(log_path, "w", encoding="utf-8") as log:
                proc = subprocess.run([sys.executable, "main.py", market], cwd=BASE_DIR,
                                      stdout=log, stderr=subprocess.STDOUT, env=env)
            status = "success" if proc.returncode == 0 else "failed"
        except Exception as e:
            print(f"🚨 봇 실행 실패: {e}")
        finally:
            db.finish_bot_run(run_id, status)
            with self.lock:
                self.current = None
            _cache.clear()

runner = BotRunner()

def scheduler_loop():
    """scheduler.py 와 같은 시간표로 자동 실행 (실행 중이면 그 회차는 건너뜀)"""
    done_keys = set()
    while True:
        try:
            for market, key in due_jobs(done_keys):
                done_keys.add(key)
                if runner.start(market, "schedule") is None:
                    print(f"⏭️ [{key}] 다른 실행이 진행 중이라 건너뜀")
            if len(done_keys) > 200:
                done_keys = set(sorted(done_keys)[-50:])
        except Exception as e:
            print(f"🚨 스케줄러 오류: {e}")
        time.sleep(20)

def next_runs():
    """시장별 다음 자동 실행 시각 (KST)"""
    result = {}
    for market, tz, times in (("KR", KST, KR_RUN_TIMES), ("US", NY, US_RUN_TIMES)):
        now = datetime.now(tz)
        for day in range(0, 8):
            d = now + timedelta(days=day)
            if d.weekday() >= 5:
                continue
            slots = [d.replace(hour=int(t[:2]), minute=int(t[3:]), second=0, microsecond=0) for t in times]
            upcoming = [s for s in slots if s > now]
            if upcoming:
                result[market] = upcoming[0].astimezone(KST).isoformat()
                break
    return result

def cleanup_logs():
    limit = time.time() - LOG_RETENTION_DAYS * 86400
    for path in glob.glob(os.path.join(LOG_DIR, "*.log")):
        if os.path.getmtime(path) < limit:
            os.remove(path)

# ---------------------------------------------------------
# 시세 캐시 (야후 파이낸스 호출 최소화)
# ---------------------------------------------------------
_cache = {}

def cached(key, ttl, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    value = fn()
    _cache[key] = (time.time(), value)
    return value

def fetch_last_prices(tickers):
    if not tickers:
        return {}
    data = yf.download(sorted(tickers), period="5d", interval="1d", auto_adjust=False, progress=False, group_by="ticker")
    prices = {}
    for t in tickers:
        try:
            close = (data[t] if len(tickers) > 1 else data)["Close"].dropna()
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            prices[t] = float(close.iloc[-1])
        except Exception:
            pass
    return prices

def fetch_regimes():
    """시장별 국면: 지수가 200일선 위면 상승장 (봇의 매수 허용 조건과 동일)"""
    result = {}
    for market, index in INDEX_BY_MARKET.items():
        try:
            df = yf.download(index, period="2y", progress=False, auto_adjust=True)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            close = df["Close"].dropna()
            sma = close.rolling(200).mean().iloc[-1]
            result[market] = {"bull": bool(close.iloc[-1] > sma), "close": float(close.iloc[-1]),
                              "sma200": float(sma), "gap": float(close.iloc[-1] / sma - 1)}
        except Exception as e:
            result[market] = {"bull": None, "error": str(e)}
    return result

def signal_view(row):
    row = dict(row)
    row["chart_url"] = f"/charts/{row['chart_path']}" if row.get("chart_path") else None
    row["reasons"] = [r.strip() for r in (row.get("reasons") or "").split(", ") if r.strip() and not r.strip().startswith("⚠️ [주의]")]
    return row

# ---------------------------------------------------------
# API
# ---------------------------------------------------------
@app.get("/api/overview")
def overview():
    today_start = db.to_utc_iso(datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0))
    signals = [signal_view(s) for s in db.get_signals_since(days=2) if s["created_at"] >= today_start]
    runs = db.get_recent_bot_runs(1)
    return {
        "now": datetime.now(KST).isoformat(),
        "signals": signals,
        "next_runs": next_runs() if SCHEDULER_ENABLED else {},
        "scheduler": SCHEDULER_ENABLED,
        "running": runner_state(),
        "last_run": runs[0] if runs else None,
    }

@app.get("/api/regimes")
def regimes():
    """시장 국면은 지수 데이터를 받아야 해서 느릴 수 있어 별도 API (1시간 캐시)"""
    return cached("regimes", 3600, fetch_regimes)

@app.get("/api/signals")
def signals(days: int = 7):
    return [signal_view(s) for s in db.get_signals_since(days=min(max(days, 1), 365))]

@app.get("/api/positions")
def positions(days: int = 7):
    """최근 추천 종목의 최초 추천가 대비 현재 수익률"""
    recent = db.get_recent_buy_signals(days=min(max(days, 1), 60))
    # 최신순 목록을 dict로 덮어쓰면 종목별 '가장 오래된(최초 추천)' 행이 남음 → 수익률 기준과 같은 회차의 TP/SL
    full = {s["ticker"]: s for s in db.get_signals_since(days=min(max(days, 1), 60))}
    tickers = tuple(sorted(s["ticker"] for s in recent))
    prices = cached(("prices", tickers), 180, lambda: fetch_last_prices(list(tickers)))
    items = []
    for s in recent:
        latest = full.get(s["ticker"], {})
        price = prices.get(s["ticker"])
        ret = (price / s["price"] - 1) if price and s["price"] else None
        tp, sl = latest.get("tp"), latest.get("sl")
        status = "hold"
        if price and sl and price <= sl:
            status = "stop"
        elif price and tp and price >= tp:
            status = "target"
        items.append({**s, "current": price, "return": ret, "tp": tp, "sl": sl, "status": status,
                      "chart_url": f"/charts/{latest['chart_path']}" if latest.get("chart_path") else None})
    order = {"stop": 0, "target": 1, "hold": 2}
    items.sort(key=lambda x: (order[x["status"]], -(x["return"] or 0)))
    return {"items": items, "updated": datetime.now(KST).isoformat()}

@app.get("/api/disclosures")
def disclosures(limit: int = 100):
    return db.get_recent_disclosures(min(max(limit, 1), 500))

def runner_state():
    cur = runner.current
    if not cur:
        return None
    return {"id": cur["id"], "market": cur["market"], "trigger": cur["trigger"],
            "elapsed": int(time.time() - cur["started"])}

@app.get("/api/runs")
def runs():
    return {"running": runner_state(), "history": db.get_recent_bot_runs(20),
            "schedule": {"KR": KR_RUN_TIMES, "US": US_RUN_TIMES}, "next_runs": next_runs() if SCHEDULER_ENABLED else {},
            "scheduler": SCHEDULER_ENABLED}

@app.post("/api/runs/{market}")
def run_now(market: str):
    market = market.upper()
    if market not in ("KR", "US"):
        raise HTTPException(400, "KR 또는 US 만 가능해요")
    run_id = runner.start(market, "manual")
    if run_id is None:
        raise HTTPException(409, "이미 실행 중이에요")
    return {"id": run_id}

@app.get("/api/runs/{run_id}/log")
def run_log(run_id: int, lines: int = 40):
    row = next((r for r in db.get_recent_bot_runs(200) if r["id"] == run_id), None)
    if not row or not row.get("log_path") or not os.path.exists(row["log_path"]):
        return {"lines": []}
    with open(row["log_path"], encoding="utf-8", errors="replace") as f:
        text = f.read().splitlines()
    keep = [l for l in text if l.strip() and "수급 데이터 에러" not in l]
    return {"lines": keep[-min(max(lines, 1), 200):]}

@app.get("/api/push/public-key")
def push_public_key():
    return {"key": get_public_key()}

@app.post("/api/push/subscribe")
async def push_subscribe(request: Request):
    sub = await request.json()
    try:
        db.add_push_subscription(sub["endpoint"], sub["keys"]["p256dh"], sub["keys"]["auth"])
    except (KeyError, TypeError):
        raise HTTPException(400, "잘못된 구독 정보")
    return {"ok": True}

@app.post("/api/push/unsubscribe")
async def push_unsubscribe(request: Request):
    sub = await request.json()
    db.remove_push_subscription(sub.get("endpoint", ""))
    return {"ok": True}

@app.post("/api/push/test")
def push_test():
    sent = send_push_all("✅ 알림 테스트", "퀀트 시그널 알림이 잘 도착했어요.", url="/?tab=bot", tag="test")
    return {"sent": sent}

@app.get("/charts/{name}")
def chart(name: str):
    path = os.path.join(db.CHART_DIR, os.path.basename(name))
    if not os.path.exists(path):
        raise HTTPException(404)
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})

# ---------------------------------------------------------
# 앱 화면 (PWA)
# ---------------------------------------------------------
@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"), headers={"Cache-Control": "no-cache"})

@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(os.path.join(STATIC_DIR, "manifest.webmanifest"), media_type="application/manifest+json")

@app.get("/sw.js")
def service_worker():
    # 서비스 워커는 루트 경로에서 제공해야 앱 전체를 담당할 수 있음
    return FileResponse(os.path.join(STATIC_DIR, "sw.js"), media_type="text/javascript",
                        headers={"Cache-Control": "no-cache"})

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host=APP_HOST, port=APP_PORT, log_level="warning")
