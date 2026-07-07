# 업데이트날짜: 2026.07.07
# 작성자: j-neat
# 공시정보 매니저
import os
import OpenDartReader
from datetime import datetime, timedelta
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

def get_dart_client():
    api_key = os.environ.get("DART_API_KEY")
    if not api_key:
        raise ValueError("🚨 DART_API_KEY가 설정되지 않았습니다.")
    return OpenDartReader(api_key)

def collect_and_save_disclosures(ticker, stock_name):
    """최근 1주일간의 주요 공시를 확인하여 호재/악재 여부를 DB에 저장합니다."""
    try:
        dart = get_dart_client()
        
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        supabase = create_client(url, key)

        # 야후 파이낸스 티커(005930.KS)에서 순수 숫자(005930)만 추출
        clean_ticker = ticker.replace('.KS', '').replace('.KQ', '')
        
        # 7일 전 날짜 세팅
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y%m%d')
        
        # DART에서 해당 종목 공시 리스트업
        reports = dart.list(clean_ticker, start=start_date)
        
        if reports is None or reports.empty:
            return
            
        # 주가에 즉각적인 영향을 주는 핵심 공시 키워드
        good_keywords = ['단일판매ㆍ공급계약체결', '무상증자결정', '자기주식취득', '영업(잠정)실적(공정공시)', '주식소각']
        bad_keywords = ['유상증자결정', '횡령', '배임', '감자결정', '주주총회소집결의(감자)']
        
        for _, row in reports.iterrows():
            title = row['report_nm']
            receipt_date = row['rcept_dt']
            
            event_type = None
            if any(kw in title for kw in good_keywords):
                event_type = 'GOOD'
            elif any(kw in title for kw in bad_keywords):
                event_type = 'BAD'
                
            if event_type:
                # DB 중복 체크
                check_exist = supabase.table('dart_disclosures').select('id').eq('ticker', ticker).eq('report_title', title).execute()
                
                if not check_exist.data:
                    data = {
                        "ticker": ticker,
                        "stock_name": stock_name,
                        "report_title": title,
                        "event_type": event_type,
                        "rcept_dt": receipt_date
                    }
                    supabase.table("dart_disclosures").insert(data).execute()
                    print(f"  📡 [공시 업데이트] {stock_name} : {title} ({event_type})")
                    
    except Exception as e:
        # 공시가 아예 없는 종목은 패스
        pass