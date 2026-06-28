#업데이트날짜: 2026.06.26
#작성자: j-neat
#야후 파이낸스에서 데이터 수집 모듈
#PER (주가수익비율): 낮을수록 회사가 버는 돈에 비해 주가가 싸다는 뜻 (보통 20 이하면 가점)
#PBR (주가순자산비율): 1에 가까울수록 회사가 가진 재산에 비해 주가가 싸다는 뜻 (보통 3 이하면 가점)
#RSI (상대강도지수): 0~100 사이로 움직이는데, 30 이하면 '사람들이 너무 많이 팔아서 과매도 상태(바닥)'라는 뜻
import yfinance as yf
import pandas as pd
import requests
import io

def get_stock_data(ticker, period='6mo'):
    stock_info = yf.Ticker(ticker)
    df = stock_info.history(period=period)
    return df

def get_fundamental_data(ticker):
    stock = yf.Ticker(ticker)
    info = stock.info
    return {
        'PER': info.get('trailingPE', 0),
        'PBR': info.get('priceToBook', 0),
        'ROE': info.get('returnOnEquity', 0),
        'Debt_Ratio': info.get('debtToEquity', 0)
    }

def get_supply_data(ticker, market_type):
    """네이버 금융에서 최근 외국인/기관 수급 동향을 가져오는 함수 (코스닥 전용)"""
    supply_info = {'foreign_buy_days': 0, 'inst_buy_days': 0}
    
    if market_type == 'KOSDAQ':
        clean_ticker = ticker.replace('.KQ', '').replace('.KS', '')
        try:
            url = f"https://finance.naver.com/item/frgn.naver?code={clean_ticker}"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            res = requests.get(url, headers=headers)
            res.encoding = 'euc-kr' 
            
            # io.StringIO를 사용해 안전하게 HTML 표 읽기 (경고/에러 방지)
            tables = pd.read_html(io.StringIO(res.text))
            
            df = None
            # 글자 매칭 대신, 열 개수가 7개 이상인 메인 수급표를 자동으로 찾음
            for t in tables:
                if len(t.columns) >= 7:
                    df = t
                    break
                    
            if df is None:
                return supply_info
                
            # 네이버 표 제목이 2줄(다중 인덱스)인 경우 1줄로 통합
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(0)
                
            # 결측치(빈 줄) 제거
            date_col = df.columns[0]
            df = df.dropna(subset=[date_col])
            # 표 중간에 끼어있는 '날짜' 제목 행도 제거
            df = df[df[date_col] != '날짜']
            
            recent_data = df.head(5) 
            
            # 기관 연속 매수일 계산 (6번째 열)
            inst_buy = 0
            for val in recent_data.iloc[:, 5]:
                val_str = str(val).replace(',', '').replace('+', '').strip()
                try:
                    if int(val_str) > 0: inst_buy += 1
                    else: break
                except:
                    break
                    
            # 외국인 연속 매수일 계산 (7번째 열)
            foreign_buy = 0
            for val in recent_data.iloc[:, 6]:
                val_str = str(val).replace(',', '').replace('+', '').strip()
                try:
                    if int(val_str) > 0: foreign_buy += 1
                    else: break
                except:
                    break
                    
            supply_info['inst_buy_days'] = inst_buy
            supply_info['foreign_buy_days'] = foreign_buy
            
        except Exception as e:
            # 화면 테러 방지를 위해 긴 HTML 대신 짧은 에러 이름만 출력
            print(f"  ⚠️ [{clean_ticker}] 수급 데이터 에러 ({type(e).__name__})")
            
    return supply_info