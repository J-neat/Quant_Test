# 업데이트날짜: 2026.06.28
# 작성자: j-neat
# 투자 전략 및 시그널 전담 모듈 (ETF 논리 모순 완벽 해결 버전)

import pandas as pd
import numpy as np

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def get_poc_price(df, bins=20):
    try:
        hist, bin_edges = np.histogram(df['Close'], bins=bins, weights=df['Volume'])
        max_bin_idx = np.argmax(hist)
        return (bin_edges[max_bin_idx] + bin_edges[max_bin_idx + 1]) / 2
    except:
        return df['Close'].mean()

# 💡 [매개변수 추가] is_bull_market (현재 시장이 200일선 위에 있는지 여부)
def apply_multi_factor_strategy(df, fundamentals, market_type='NASDAQ', supply_info=None, stock_name="", is_bull_market=True):
    if df is None or len(df) < 20:
        return 'HOLD', 0, ["데이터 부족"], df 
        
    df = df.copy() 
    df['RSI'] = calculate_rsi(df['Close'])
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['Volume_SMA_20'] = df['Volume'].rolling(window=20).mean()
    df['OBV'] = (np.sign(df['Close'].diff()) * df['Volume']).fillna(0).cumsum()
    df['OBV_SMA_20'] = df['OBV'].rolling(window=20).mean()
    
    # 💡 [핵심] 하드 필터: 거시경제 하락장일 경우 모든 신규 진입 차단
    if not is_bull_market:
        return 'HOLD', 0, ["🚫 거시경제 하락장 (지수 200일선 하회)으로 인한 매수 차단"], df

    today_rsi = df['RSI'].iloc[-1]
    today_close = df['Close'].iloc[-1]
    today_sma_20 = df['SMA_20'].iloc[-1]
    today_volume = df['Volume'].iloc[-1]
    today_vol_sma_20 = df['Volume_SMA_20'].iloc[-1]
    today_obv = df['OBV'].iloc[-1]
    today_obv_sma = df['OBV_SMA_20'].iloc[-1]
    poc_price = get_poc_price(df) 
    
    score = 0
    reasons = []
    BUY_THRESHOLD = 55
    
    etf_keywords = ['레버리지', '인버스', 'KODEX', 'TIGER', 'ETF', 'TRUST', 'FUND', 'PROSHARES', 'DIREXION', 'ACE']
    is_etf = any(keyword in str(stock_name).upper() for keyword in etf_keywords)

    if is_etf:
        if today_close <= today_sma_20:
            return 'HOLD', 0, ["추세 이탈(20일선 하회)"], df
        score += 20; reasons.append("확실한 추세(20일선 위)")
        if not pd.isna(today_rsi) and today_rsi < 75: score += 20; reasons.append(f"추세 상승여력(RSI {today_rsi:.1f})")
        if today_volume > today_vol_sma_20 * 1.2: score += 20; reasons.append("거래량 유입")
        if today_obv > today_obv_sma: score += 20; reasons.append("OBV 매집 포착")
        if today_close > poc_price: score += 20; reasons.append("주요 매물대 돌파")
            
    elif market_type == 'NASDAQ':
        if fundamentals.get('PER', 0) and 0 < fundamentals.get('PER') < 20: score += 10; reasons.append("PER 저평가")
        if fundamentals.get('PBR', 0) and 0 < fundamentals.get('PBR') < 2.0: score += 10; reasons.append("PBR 우수")
        if fundamentals.get('ROE', 0) and fundamentals.get('ROE') > 0.12: score += 10; reasons.append("고수익성")
        if fundamentals.get('Debt_Ratio', 999) < 100: score += 10; reasons.append("재무건전")
            
        if not pd.isna(today_rsi) and today_rsi < 75: score += 10; reasons.append(f"모멘텀(RSI {today_rsi:.1f})")
        if today_close > today_sma_20: score += 10; reasons.append("상승 추세")
        if today_volume > today_vol_sma_20 * 1.5: score += 10; reasons.append("거래량 터짐")
        if today_obv > today_obv_sma: score += 15; reasons.append("OBV 매집 포착")
        if today_close > poc_price: score += 15; reasons.append("주요 매물대 돌파")
            
    else: 
        if not pd.isna(today_rsi) and today_rsi < 75: score += 10; reasons.append(f"모멘텀(RSI {today_rsi:.1f})")
        if today_close > today_sma_20: score += 10; reasons.append("상승 추세")
        if today_volume > today_vol_sma_20 * 1.2: score += 10; reasons.append("거래량 증가")
        if today_obv > today_obv_sma: score += 15; reasons.append("OBV 상승(매집)")
        if today_close > poc_price: score += 15; reasons.append("최대 매물대 돌파")

        supply_info = supply_info or {}
        foreign_days = supply_info.get('foreign_buy_days', 0)
        inst_days = supply_info.get('inst_buy_days', 0)
        
        if foreign_days >= 2: score += 15; reasons.append(f"외국인 {foreign_days}일 연속 픽")
        elif foreign_days == 1: score += 7; reasons.append("외국인 오늘 매수")
        if inst_days >= 2: score += 15; reasons.append(f"기관 {inst_days}일 연속 픽")
        elif inst_days == 1: score += 7; reasons.append("기관 오늘 매수")
        
        if today_close > today_sma_20 and (foreign_days > 0 or inst_days > 0):
            score += 10; reasons.append("🔥 추세+수급 동반 시너지")
        
    signal = 'BUY' if score >= BUY_THRESHOLD else 'HOLD'
    if score >= BUY_THRESHOLD: reasons.append(f"종합: {int(score)}점 [{market_type}]")
    
    return signal, int(score), reasons, df