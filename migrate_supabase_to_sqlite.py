# 업데이트날짜: 2026.10.15
# 작성자: j-neat
# 예전 Supabase 데이터(quant_signals, dart_disclosures)를 로컬 SQLite(data/quant.db)로 옮기는 1회용 스크립트
#
# 사용법:
#   1. Supabase 대시보드에서 일시정지된 프로젝트를 Resume (2027-10-13까지 무료로 가능)
#   2. .env 에 SUPABASE_URL, SUPABASE_KEY 가 있는 상태에서 실행: python migrate_supabase_to_sqlite.py
#   3. 여러 번 실행해도 이미 옮긴 데이터는 다시 넣지 않음
#   (이 스크립트에만 supabase 패키지가 필요)

import os
from contextlib import closing
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client
from db_manager import get_connection, to_utc_iso, DB_PATH

load_dotenv()
PAGE_SIZE = 1000

def fetch_all(supabase, table):
    """Supabase는 한 번에 최대 1000행만 주므로 페이지 단위로 전부 가져옴"""
    rows, start = [], 0
    while True:
        page = supabase.table(table).select("*").order("id").range(start, start + PAGE_SIZE - 1).execute().data
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            return rows
        start += PAGE_SIZE

def normalize_time(value):
    """Supabase 시간 문자열 → 로컬 DB 형식 (UTC, 초 단위). 시간대가 없으면 UTC로 간주"""
    if not value:
        return to_utc_iso(datetime.now())
    return to_utc_iso(datetime.fromisoformat(str(value).replace("Z", "+00:00")))

def main():
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("🚨 .env 에 SUPABASE_URL / SUPABASE_KEY 가 없습니다.")
        return
    supabase = create_client(url, key)

    signals = fetch_all(supabase, "quant_signals")
    disclosures = fetch_all(supabase, "dart_disclosures")
    print(f"📥 Supabase: 추천 기록 {len(signals)}건, 공시 이벤트 {len(disclosures)}건")

    added_signals = added_disclosures = 0
    with closing(get_connection()) as conn, conn:
        for r in signals:
            created_at = normalize_time(r.get("created_at"))
            exists = conn.execute("SELECT 1 FROM quant_signals WHERE ticker = ? AND created_at = ?",
                                  (r["ticker"], created_at)).fetchone()
            if exists:
                continue
            conn.execute(
                "INSERT INTO quant_signals (created_at, ticker, stock_name, price, score, reasons, market_type) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (created_at, r["ticker"], r.get("stock_name"), r.get("price"), r.get("score"),
                 r.get("reasons"), r.get("market_type")),
            )
            added_signals += 1

        for r in disclosures:
            cur = conn.execute(
                "INSERT OR IGNORE INTO dart_disclosures (created_at, ticker, stock_name, report_title, event_type, rcept_dt) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (normalize_time(r.get("created_at")), r["ticker"], r.get("stock_name"),
                 r["report_title"], r["event_type"], str(r["rcept_dt"])),
            )
            added_disclosures += cur.rowcount

    print(f"✅ 로컬 DB({DB_PATH})로 이전 완료: 추천 기록 {added_signals}건, 공시 이벤트 {added_disclosures}건 추가")

if __name__ == "__main__":
    main()
