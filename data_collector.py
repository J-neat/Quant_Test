#업데이트날짜: 2026.06.26
#작성자: j-neat
#야후 파이낸스에서 데이터 수집 모듈
#PER (주가수익비율): 낮을수록 회사가 버는 돈에 비해 주가가 싸다는 뜻 (보통 20 이하면 가점)
#PBR (주가순자산비율): 1에 가까울수록 회사가 가진 재산에 비해 주가가 싸다는 뜻 (보통 3 이하면 가점)
#RSI (상대강도지수): 0~100 사이로 움직이는데, 30 이하면 '사람들이 너무 많이 팔아서 과매도 상태(바닥)'라는 뜻
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import io
import FinanceDataReader as fdr

_NUMERIC_KEYS = {
    'trailingPE', 'forwardPE', 'priceToBook', 'currentPrice', 'previousClose', 'bookValue',
    'returnOnEquity', 'trailingEps', 'forwardEps', 'debtToEquity', 'totalDebt', 'marketCap',
}

def get_stock_data(ticker, period='6mo'):
    stock_info = yf.Ticker(ticker)
    df = stock_info.history(period=period)
    return df

def _to_number(value):
    """yfinance가 None, 'Infinity' 같은 값을 줄 때가 있어서 안전하게 float로 변환 (실패 시 0)"""
    try:
        num = float(value)
        return num if np.isfinite(num) else 0.0
    except (TypeError, ValueError):
        return 0.0

def get_fundamental_data(ticker):
    """재무 지표 조회. 실패해도 예외를 던지지 않고 0으로 채운 값을 반환
    (기존에는 info 조회 실패 / None 비교 에러로 종목 분석 전체가 건너뛰어졌음)"""
    try:
        info = yf.Ticker(ticker).info or {}
        return _calc_fundamentals(info)
    except Exception as e:
        print(f"  ⚠️ [{ticker}] 재무 데이터 조회 실패 ({type(e).__name__}) → 0으로 대체")
        return {'PER': 0.0, 'PBR': 0.0, 'ROE': 0.0, 'Debt_Ratio': 0.0}

def _calc_fundamentals(info):
    info = {k: (_to_number(v) if k in _NUMERIC_KEYS else v) for k, v in info.items()}
    
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
            # 💡 [수정] 2026-10 네이버 금융 PC 페이지(frgn.naver)가 개편되어 HTML 표가 사라짐
            #    (pd.read_html이 표를 못 찾아 전 종목 수급 0일로 처리되던 문제) → 네이버 모바일 JSON API 사용
            url = f"https://m.stock.naver.com/api/stock/{clean_ticker}/trend?pageSize=5"
            headers = {'User-Agent': 'Mozilla/5.0'}
            res = requests.get(url, headers=headers, timeout=10)
            res.raise_for_status()
            recent_data = res.json()  # 최신 날짜가 먼저 옴

            def count_continuous_buy(key):
                days = 0
                for row in recent_data:
                    val_str = str(row.get(key, '')).replace(',', '').replace('+', '').strip()
                    try:
                        if int(val_str) > 0: days += 1
                        else: break
                    except ValueError: break
                return days

            supply_info['inst_buy_days'] = count_continuous_buy('organPureBuyQuant')
            supply_info['foreign_buy_days'] = count_continuous_buy('foreignerPureBuyQuant')
            
        except Exception as e:
            print(f"  ⚠️ [{clean_ticker}] 수급 데이터 에러 ({type(e).__name__})")
            
    return supply_info


# ---------------------------------------------------------
# 분석 대상 유니버스 (main.py, backtester.py 공용)
# ---------------------------------------------------------
# 시장 국면(200일선) 판단용 지수 — KOSDAQ은 ^KQ11 (원래 ^KS11)
INDEX_BY_MARKET = {'NASDAQ': 'QQQ', 'KOSPI': '^KS11', 'KOSDAQ': '^KQ11'}

# 💡 [수정] 2026-10 위키피디아 'Nasdaq-100' 문서에서 구성종목 표가 별도 문서로 분리됨 → 새 문서 먼저, 옛 문서는 예비
NASDAQ_100_URLS = [
    'https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies',
    'https://en.wikipedia.org/wiki/Nasdaq-100',
]

def get_nasdaq_100():
    headers = {'User-Agent': 'Mozilla/5.0'}
    for url in NASDAQ_100_URLS:
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            # pandas 3.x 부터는 HTML 문자열을 그대로 넘기면 '파일 경로'로 해석해서 에러가 남 → StringIO로 감싸야 함
            tables = pd.read_html(io.StringIO(response.text))
            for table in tables:
                ticker_col = 'Ticker' if 'Ticker' in table.columns else 'Symbol' if 'Symbol' in table.columns else None
                if ticker_col and 'Company' in table.columns and len(table) >= 90:
                    # 야후 파이낸스는 BRK.B 같은 티커를 BRK-B 로 씀
                    return {str(t).replace('.', '-'): c for t, c in zip(table[ticker_col], table['Company'])}
        except Exception as e:
            print(f"⚠️ 나스닥 100 목록 수집 실패 ({url}: {type(e).__name__}: {e})")
    print("⚠️ 위키피디아에서 나스닥 100 표를 찾지 못했습니다. (기본 2종목으로 대체)")
    return {'AAPL': 'Apple Inc.', 'MSFT': 'Microsoft Corp.'}

def get_kospi_top_100():
    df = fdr.StockListing('KOSPI')
    return {f"{row['Code']}.KS": row['Name'] for _, row in df.head(100).iterrows()}

def get_kosdaq_top_100():
    df = fdr.StockListing('KOSDAQ')
    kosdaq_dict = {f"{row['Code']}.KQ": row['Name'] for _, row in df.head(100).iterrows()}
    etfs = {"233740.KS": "KODEX 코스닥150레버리지", "251340.KS": "KODEX 코스닥150선물인버스", "252710.KS": "TIGER 코스닥150선물인버스"}
    kosdaq_dict.update(etfs)
    return kosdaq_dict
