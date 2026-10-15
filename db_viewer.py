# 업데이트날짜: 2026.10.15
# 작성자: j-neat
# 로컬 DB(data/quant.db) 간단 조회 도구
#
# 사용법:
#   python db_viewer.py                 # 요약 (테이블별 건수 + 최근 추천 10건)
#   python db_viewer.py signals [N]     # 최근 추천 기록 N건 (기본 30)
#   python db_viewer.py disclosures [N] # 최근 공시/뉴스 이벤트 N건 (기본 30)
#   python db_viewer.py today           # 오늘(KST) 추천 종목
#   python db_viewer.py sql "SELECT ..." # 직접 SQL 실행 (조회용)

import sys
from contextlib import closing
from datetime import datetime
import pandas as pd
from db_manager import get_connection, DB_PATH, KST, to_utc_iso

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)
pd.set_option("display.max_colwidth", 40)
pd.set_option("display.unicode.east_asian_width", True)  # 한글 컬럼 줄맞춤

def query(sql, params=()):
    with closing(get_connection()) as conn:
        return pd.read_sql_query(sql, conn, params=params)

def to_kst(df, col="created_at"):
    """DB의 UTC 시간을 한국 시간으로 보기 좋게 변환"""
    if not df.empty and col in df:
        df[col] = pd.to_datetime(df[col], utc=True).dt.tz_convert(KST).dt.strftime("%m-%d %H:%M")
    return df

def show_signals(limit=30):
    df = query("SELECT created_at AS 추천시각, ticker, stock_name, market_type, price, score, reasons "
               "FROM quant_signals ORDER BY created_at DESC, id DESC LIMIT ?", (limit,))
    print(to_kst(df, "추천시각").to_string(index=False) if not df.empty else "(추천 기록 없음)")

def show_disclosures(limit=30):
    df = query("SELECT rcept_dt, ticker, stock_name, event_type, report_title "
               "FROM dart_disclosures ORDER BY rcept_dt DESC, id DESC LIMIT ?", (limit,))
    print(df.to_string(index=False) if not df.empty else "(공시 이벤트 없음)")

def show_today():
    since = to_utc_iso(datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0))
    df = query("SELECT created_at AS 추천시각, ticker, stock_name, market_type, price, score "
               "FROM quant_signals WHERE created_at >= ? ORDER BY score DESC", (since,))
    print(to_kst(df, "추천시각").to_string(index=False) if not df.empty else "(오늘 추천 없음)")

def show_summary():
    print(f"📂 DB 파일: {DB_PATH}\n")
    counts = query("SELECT 'quant_signals' AS 테이블, COUNT(*) AS 건수, MIN(created_at) AS 처음, MAX(created_at) AS 마지막 FROM quant_signals "
                   "UNION ALL SELECT 'dart_disclosures', COUNT(*), MIN(created_at), MAX(created_at) FROM dart_disclosures")
    print(counts.to_string(index=False))
    print("\n📈 최근 추천 10건")
    show_signals(10)

if __name__ == "__main__":
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else "summary"
    n = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 30
    if cmd == "signals":
        show_signals(n)
    elif cmd == "disclosures":
        show_disclosures(n)
    elif cmd == "today":
        show_today()
    elif cmd == "sql" and len(sys.argv) > 2:
        print(query(sys.argv[2]).to_string(index=False))
    else:
        show_summary()
