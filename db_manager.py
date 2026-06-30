import os
from supabase import create_client, Client

def get_supabase_client() -> Client:
    """.env 파일의 환경 변수를 읽어 Supabase 클라이언트를 초기화합니다."""
    url: str = os.environ.get("SUPABASE_URL")
    key: str = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("🚨 Supabase 환경변수(URL 또는 KEY)가 .env 파일에 설정되지 않았습니다.")
    return create_client(url, key)

def save_signal_to_db(ticker, stock_name, price, score, reasons_list, market_type):
    """
    추천 종목 정보를 Supabase PostgreSQL의 quant_signals 테이블에 저장합니다.
    """
    try:
        supabase = get_supabase_client()
        
        # DB 테이블 스키마 구조에 맞게 데이터 매핑
        data = {
            "ticker": str(ticker),
            "stock_name": str(stock_name),
            "price": float(price),
            "score": int(score),
            "reasons": ", ".join(reasons_list),
            "market_type": str(market_type)
        }
        
        # 데이터 원격 삽입 실행
        response = supabase.table("quant_signals").insert(data).execute()
        return response
    except Exception as e:
        print(f"      🚨 [DB 에러] 데이터 적재 실패 원인: {e}")
        raise e