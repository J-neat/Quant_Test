# 업데이트날짜: 2026.07.07
# 작성자: j-neat
# 공시정보 매니저(DART 공시 + 네이버 뉴스 통합 이벤트 수집기)
import os
import requests
import OpenDartReader
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from db_manager import save_disclosure
from dotenv import load_dotenv
import contextlib
import io

load_dotenv()

_dart_client = None

def get_dart_client():
    """DART 클라이언트는 생성 시 기업코드 파일(수 MB)을 읽으므로 한 번만 만들어 재사용"""
    global _dart_client
    if _dart_client is None:
        api_key = os.environ.get("DART_API_KEY")
        if not api_key:
            raise ValueError("🚨 DART_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
        _dart_client = OpenDartReader(api_key)
    return _dart_client

def fetch_naver_news(clean_ticker):
    """네이버 금융에서 해당 종목의 최신 뉴스 제목들을 크롤링합니다."""
    titles = []
    try:
        url = f"https://finance.naver.com/item/news_news.naver?code={clean_ticker}&page=1"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        news_links = soup.select('.title a')
        for link in news_links:
            titles.append(link.text.strip())
    except Exception as e:
        print(f"  ❌ [{clean_ticker}] 네이버 뉴스 크롤링 자체 실패: {e}")
    return titles

def collect_and_save_disclosures(ticker, stock_name):
    """최근 1주일간의 DART 공시와 오늘의 뉴스를 수집하여 호재/악재를 DB에 저장합니다."""
    try:
        dart = get_dart_client()

        clean_ticker = ticker.replace('.KS', '').replace('.KQ', '')
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y%m%d')
        today_date = datetime.now().strftime('%Y%m%d')
        
        events_to_evaluate = []

        # 1. DART 공시 수집
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                reports = dart.list(clean_ticker, start=start_date)
                
            if reports is not None and not reports.empty:
                for _, row in reports.iterrows():
                    events_to_evaluate.append({
                        'title': f"[공시] {row['report_nm']}",
                        'date': row['rcept_dt']
                    })
        except Exception as dart_err:
            # 공시가 없는 경우 응답 코드가 에러로 올 수 있으므로 상세 출력하지 않고 패스
            pass
                
        # 2. 네이버 최신 뉴스 수집
        news_titles = fetch_naver_news(clean_ticker)
        for title in news_titles:
            events_to_evaluate.append({
                'title': f"[뉴스] {title}",
                'date': today_date
            })

        # 💡 현실적인 대형주용 호재/악재 키워드 세팅
        good_keywords = [
            '수주', '공급계약', '흑자전환', '사상최대', '목표가 상향', '자사주 취득', 
            '소각', 'M&A', '어닝 서프라이즈', '배당 확대', '독점', '승인', '개발 성공'
        ]
        bad_keywords = [
            '유상증자', '횡령', '배임', '감자', '적자전환', '목표가 하향', 
            '어닝 쇼크', '하회', '검찰', '압수수색', '소송', '실적 부진', '디폴트'
        ]
        
        # 3. 평가 및 DB 적재
        for event in events_to_evaluate:
            event_title = event['title']
            event_date = event['date']
            
            event_type = None
            if any(kw in event_title for kw in good_keywords):
                event_type = 'GOOD'
            elif any(kw in event_title for kw in bad_keywords):
                event_type = 'BAD'
                
            if event_type:
                try:
                    # 같은 종목·같은 제목이 이미 있으면 DB가 알아서 무시 (UNIQUE 제약)
                    if save_disclosure(ticker, stock_name, event_title, event_type, event_date):
                        if event_type == 'GOOD':
                            print(f"  🎉 [DB 적재 성공] {stock_name}: {event_title[:25]}... (GOOD)")
                        else:
                            print(f"  🚨 [DB 적재 성공] {stock_name}: {event_title[:25]}... (BAD)")
                
                except Exception as db_insert_err:
                    print(f"  ❌ [DB 적재 에러] {stock_name}({ticker}) 저장 실패: {db_insert_err}")
                    
    except Exception as global_err:
        print(f"  ❌ [DART 매니저 시스템 치명적 에러]: {global_err}")
