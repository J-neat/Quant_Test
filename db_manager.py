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
    
def get_recent_buy_tickers():
    """
    최근 3일 이내에 'BUY' 시그널이 발생했던 종목 티커(Ticker) 리스트를 Supabase에서 불러옵니다.
    """
    try:
        from supabase import create_client
        import os
        from datetime import datetime, timedelta
        
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        supabase = create_client(url, key)
        
        three_days_ago = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        
        response = supabase.table("quant_signals") \
            .select("ticker") \
            .eq("signal", "BUY") \
            .gte("created_at", three_days_ago) \
            .execute()
            
        tickers = list(set([item['ticker'] for item in response.data]))
        return tickers
    except Exception as e:
        print(f"DB 조회 중 에러 발생: {e}")
        return []