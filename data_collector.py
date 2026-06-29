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
    
    # 1. PER (주가수익비율) 추정
    # 우선적으로 과거 실적(trailingPE)을 찾고, 없으면 향후 12개월 예상치(forwardPE)를 사용
    per = info.get('trailingPE')
    if not per:
        per = info.get('forwardPE', 0)
        
    # 2. PBR (주가순자산비율) 추정
    # priceToBook이 없으면, 현재가(currentPrice) / 주당순자산(bookValue)로 직접 계산
    pbr = info.get('priceToBook')
    if not pbr:
        price = info.get('currentPrice', info.get('previousClose', 0))
        book_value = info.get('bookValue', 0)
        if price > 0 and book_value > 0:
            pbr = price / book_value
        else:
            pbr = 0
            
    # 3. ROE (자기자본이익률) 추정
    # returnOnEquity가 없으면, 주당순이익(EPS) / 주당순자산(bookValue)로 근사치 계산
    roe = info.get('returnOnEquity')
    if not roe:
        eps = info.get('trailingEps', info.get('forwardEps', 0))
        book_value = info.get('bookValue', 0)
        if eps and book_value and book_value > 0:
            roe = eps / book_value
        else:
            roe = 0
            
    # 4. 부채비율(Debt Ratio) 추정
    # debtToEquity가 없으면 총부채(totalDebt)와 시가총액(marketCap)을 이용해 보수적인 추정치 적용
    debt = info.get('debtToEquity')
    if not debt:
        total_debt = info.get('totalDebt', 0)
        market_cap = info.get('marketCap', 0)
        # 시총 대비 부채가 100%를 넘어가면 위험하다고 판단 (자본 대비 부채비율의 대체재)
        if total_debt > 0 and market_cap > 0:
            debt = (total_debt / market_cap) * 100 
        else:
            debt = 0 
            
    return {
        'PER': per,
        'PBR': pbr,
        'ROE': roe,
        'Debt_Ratio': debt
    }

def get_supply_data(ticker, market_type):
    supply_info = {'foreign_buy_days': 0, 'inst_buy_days': 0}
    
    # 💡 [수정] KOSDAQ뿐만 아니라 KOSPI 시장도 네이버 금융 수급 데이터를 가져오도록 추가
    if market_type in ['KOSDAQ', 'KOSPI']:
        clean_ticker = ticker.replace('.KQ', '').replace('.KS', '')
        try:
            url = f"https://finance.naver.com/item/frgn.naver?code={clean_ticker}"
            headers = {'User-Agent': 'Mozilla/5.0'}
            res = requests.get(url, headers=headers)
            res.encoding = 'euc-kr' 
            
            tables = pd.read_html(io.StringIO(res.text))
            
            df = None
            for t in tables:
                if len(t.columns) >= 7:
                    df = t
                    break
                    
            if df is None: return supply_info
                
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(0)
                
            date_col = df.columns[0]
            df = df.dropna(subset=[date_col])
            df = df[df[date_col] != '날짜']
            recent_data = df.head(5) 
            
            inst_col_idx, foreign_col_idx = 5, 6
            for i, col_name in enumerate(df.columns):
                if '기관' in str(col_name): 
                    inst_col_idx = i
                elif '외국인' in str(col_name) and '비율' not in str(col_name) and '보유' not in str(col_name): 
                    foreign_col_idx = i

            def count_continuous_buy(series):
                days = 0
                for val in series:
                    val_str = str(val).replace(',', '').replace('+', '').strip()
                    try:
                        if int(val_str) > 0: days += 1
                        else: break
                    except: break
                return days

            supply_info['inst_buy_days'] = count_continuous_buy(recent_data.iloc[:, inst_col_idx])
            supply_info['foreign_buy_days'] = count_continuous_buy(recent_data.iloc[:, foreign_col_idx])
            
        except Exception as e:
            print(f"  ⚠️ [{clean_ticker}] 수급 데이터 에러 ({type(e).__name__})")
            
    return supply_info