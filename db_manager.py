# 업데이트날짜: 2026.10.15
# 작성자: j-neat
# DB 관리 모듈 — 로컬 SQLite (data/quant.db)
#
# 💡 [변경] Supabase 무료 플랜은 7일간 활동이 없으면 프로젝트가 일시정지돼서
#    봇이 돌고 있는 PC에 파일 하나로 저장하는 SQLite로 교체 (무료·무제한·일시정지 없음, 설치 불필요)
#    - 모든 DB 접근은 이 모듈을 통해서만 함 (main / dart_manager / strategy / backtester / performance_reporter)
#    - 시간(created_at)은 UTC ISO 문자열 'YYYY-MM-DDTHH:MM:SS+00:00' 로 저장 → 문자열 비교로 기간 조회
#    - 예전 Supabase 데이터 이전: python migrate_supabase_to_sqlite.py

import os
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
NY = ZoneInfo("America/New_York")

DB_PATH = os.environ.get("QUANT_DB_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "quant.db")

DISCLOSURE_RETENTION_DAYS = 30   # 공시/뉴스 이벤트는 최근 것만 의미 있음
SIGNAL_RETENTION_DAYS = 365      # 추천 기록은 실전 성과 평가용으로 오래 보관 (Supabase 시절엔 30일)

SCHEMA = """
CREATE TABLE IF NOT EXISTS quant_signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT    NOT NULL,
    ticker      TEXT    NOT NULL,
    stock_name  TEXT,
    price       REAL,
    score       INTEGER,
    reasons     TEXT,
    market_type TEXT
);
CREATE INDEX IF NOT EXISTS idx_signals_ticker_created ON quant_signals (ticker, created_at);
CREATE INDEX IF NOT EXISTS idx_signals_created ON quant_signals (created_at);

CREATE TABLE IF NOT EXISTS dart_disclosures (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT    NOT NULL,
    ticker       TEXT    NOT NULL,
    stock_name   TEXT,
    report_title TEXT    NOT NULL,
    event_type   TEXT    NOT NULL,   -- 'GOOD' / 'BAD'
    rcept_dt     TEXT    NOT NULL,   -- 'YYYYMMDD'
    UNIQUE (ticker, report_title)
);
CREATE INDEX IF NOT EXISTS idx_disclosures_ticker ON dart_disclosures (ticker);
"""

_initialized = False

def get_connection():
    """SQLite 연결 (첫 호출 시 폴더/테이블 자동 생성). with closing(get_connection()) as conn: 형태로 사용"""
    global _initialized
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    if not _initialized:
        conn.execute("PRAGMA journal_mode=WAL")  # 백테스트/리포트가 읽는 중에도 봇이 쓸 수 있게
        conn.executescript(SCHEMA)
        _initialized = True
    return conn

def utc_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def to_utc_iso(dt):
    """datetime → DB 저장 형식 (naive면 UTC로 간주)"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec='seconds')

def cleanup_old_db_data():
    """보관 기간이 지난 데이터 삭제 (공시 30일, 추천 기록 365일)"""
    try:
        disclosure_cutoff = (datetime.now(KST) - timedelta(days=DISCLOSURE_RETENTION_DAYS)).strftime("%Y%m%d")
        signal_cutoff = to_utc_iso(datetime.now(timezone.utc) - timedelta(days=SIGNAL_RETENTION_DAYS))
        with closing(get_connection()) as conn, conn:
            d = conn.execute("DELETE FROM dart_disclosures WHERE rcept_dt < ?", (disclosure_cutoff,)).rowcount
            s = conn.execute("DELETE FROM quant_signals WHERE created_at < ?", (signal_cutoff,)).rowcount
        print(f"🧹 [DB 청소 완료] 공시 {d}건({DISCLOSURE_RETENTION_DAYS}일 경과), 추천 기록 {s}건({SIGNAL_RETENTION_DAYS}일 경과) 삭제")
    except Exception as e:
        print(f"🚨 [DB 청소 에러] 오래된 데이터를 삭제하는 중 문제가 발생했어: {e}")

# ---------------------------------------------------------
# quant_signals (매수 추천 기록)
# ---------------------------------------------------------
def _market_day_start_utc(market_type):
    """해당 시장 현지 기준 '오늘 0시'를 UTC ISO 문자열로 반환 (미장은 KST 자정을 넘어가므로 뉴욕 날짜 기준)"""
    tz = KST if market_type in ('KOSPI', 'KOSDAQ') else NY
    day_start = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    return to_utc_iso(day_start)

def is_signal_saved_today(ticker, market_type):
    """같은 거래일에 이미 추천(저장)된 종목인지 확인. 조회 실패 시 False (알림 누락보다 중복이 낫다)"""
    try:
        with closing(get_connection()) as conn:
            row = conn.execute(
                "SELECT 1 FROM quant_signals WHERE ticker = ? AND created_at >= ? LIMIT 1",
                (str(ticker), _market_day_start_utc(market_type)),
            ).fetchone()
        return row is not None
    except Exception as e:
        print(f"      🚨 [DB 에러] 오늘 추천 여부 조회 실패: {e}")
        return False

def save_signal_to_db(ticker, stock_name, price, score, reasons_list, market_type):
    """
    추천 종목 정보를 quant_signals 테이블에 저장합니다.
    같은 거래일에 이미 저장된 종목이면 중복 저장하지 않습니다 (그날 최초 추천가 유지).
    저장했으면 True, 중복/실패면 False
    """
    try:
        # 💡 [중복 방지] 스케줄러가 하루 여러 번 돌아도 종목당 하루 1건만 저장
        if is_signal_saved_today(ticker, market_type):
            print(f"      ⏭️ [DB] {ticker} 오늘 이미 저장됨 → 중복 저장 생략")
            return False

        with closing(get_connection()) as conn, conn:
            conn.execute(
                "INSERT INTO quant_signals (created_at, ticker, stock_name, price, score, reasons, market_type) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    utc_now_iso(),
                    str(ticker),
                    str(stock_name),
                    float(price),
                    # 소수점 점수(65.8)를 반올림하여 정수(66)로 저장
                    int(round(float(score))),
                    ", ".join(reasons_list),
                    str(market_type),
                ),
            )
        return True
    except Exception as e:
        print(f"      🚨 [DB 에러] 데이터 적재 실패 원인: {e}")
        return False

def get_recent_buy_signals(days=3):
    """
    최근 days일 이내에 저장된 추천 종목의 상세 정보(티커, 종목명, 매수가 등)를 불러옵니다.
    """
    try:
        since = to_utc_iso(datetime.now(timezone.utc) - timedelta(days=days))
        with closing(get_connection()) as conn:
            rows = conn.execute(
                "SELECT ticker, stock_name, price, score, market_type, created_at FROM quant_signals "
                "WHERE created_at >= ? ORDER BY created_at, id",
                (since,),
            ).fetchall()

        # 💡 중복 티커는 '최초 추천' 기준으로 유지 (예전엔 최신 추천가로 덮어써서 재추천마다 기준가가 바뀌었음)
        #    signal_count: 기간 내 추천된 날 수 (하루 1건만 저장되므로)
        unique_signals = {}
        for row in rows:
            item = dict(row)
            if item['ticker'] in unique_signals:
                unique_signals[item['ticker']]['signal_count'] += 1
            else:
                unique_signals[item['ticker']] = {**item, 'signal_count': 1}

        return list(unique_signals.values())
    except Exception as e:
        print(f"🚨 DB 조회 중 에러 발생: {e}")
        return []

def get_all_signals():
    """전체 추천 기록 (오래된 순) — 실전 성과 평가 / 백테스트 DB 유니버스용"""
    with closing(get_connection()) as conn:
        rows = conn.execute("SELECT * FROM quant_signals ORDER BY created_at, id").fetchall()
    return [dict(r) for r in rows]

# ---------------------------------------------------------
# dart_disclosures (공시/뉴스 호재·악재 이벤트)
# ---------------------------------------------------------
def save_disclosure(ticker, stock_name, report_title, event_type, rcept_dt):
    """공시/뉴스 이벤트 저장. 같은 종목·같은 제목이 이미 있으면 무시. 새로 저장했으면 True"""
    with closing(get_connection()) as conn, conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO dart_disclosures (created_at, ticker, stock_name, report_title, event_type, rcept_dt) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (utc_now_iso(), ticker, stock_name, report_title, event_type, str(rcept_dt)),
        )
        return cur.rowcount > 0

def get_disclosures(ticker):
    """종목의 공시/뉴스 이벤트 목록 (event_type, report_title, rcept_dt)"""
    with closing(get_connection()) as conn:
        rows = conn.execute(
            "SELECT event_type, report_title, rcept_dt FROM dart_disclosures WHERE ticker = ? ORDER BY rcept_dt",
            (ticker,),
        ).fetchall()
    return [dict(r) for r in rows]
