# 업데이트날짜: 2026.06.28
# 작성자: j-neat
# 투자 전략 및 시그널 전담 모듈 (ETF 논리 모순 완벽 해결 버전)

import pandas as pd

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    avg_gain = gain.rolling(window=period, min_periods=1).mean()
    avg_loss = loss.rolling(window=period, min_periods=1).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def apply_multi_factor_strategy(df, fundamentals, market_type='NASDAQ', supply_info=None, stock_name=""):
    df['RSI'] = calculate_rsi(df['Close'])
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['Volume_SMA_20'] = df['Volume'].rolling(window=20).mean()
    
    today_rsi = df['RSI'].iloc[-1]
    today_close = df['Close'].iloc[-1]
    today_sma_20 = df['SMA_20'].iloc[-1]
    today_volume = df['Volume'].iloc[-1]
    today_vol_sma_20 = df['Volume_SMA_20'].iloc[-1]
    
    score = 0
    reasons = []
    
    is_etf = '레버리지' in stock_name or '인버스' in stock_name or 'KODEX' in stock_name or 'TIGER' in stock_name

    if is_etf:
        # 💡 [해결] ETF 전용 전략: 20일선 돌파(50점)를 못 하면 무조건 탈락하도록 배점 조정!
        p_sma, p_rsi, p_vol = 50, 25, 25
        
        if today_close > today_sma_20: 
            score += p_sma; reasons.append("확실한 추세(20일선 위)")
        if not pd.isna(today_rsi) and today_rsi < 65: 
            score += p_rsi; reasons.append(f"추세 상승여력(RSI {today_rsi:.1f})")
        if today_volume > today_vol_sma_20 * 1.2: 
            score += p_vol; reasons.append("거래량 유입")
            
    elif market_type == 'NASDAQ':
        p_per, p_pbr, p_roe, p_debt = 20, 15, 20, 15
        p_rsi, p_sma, p_vol = 10, 10, 10
        
        per = fundamentals.get('PER')
        if per and 0 < per < 20: 
            score += p_per; reasons.append(f"PER 저평가({per:.1f})")
        pbr = fundamentals.get('PBR')
        if pbr and 0 < pbr < 2.0: 
            score += p_pbr; reasons.append(f"PBR 우수({pbr:.1f})")
        roe = fundamentals.get('ROE')
        if roe and roe > 0.12: 
            score += p_roe; reasons.append(f"고수익성(ROE {roe*100:.1f}%)")
        debt = fundamentals.get('Debt_Ratio')
        if debt and debt < 100: 
            score += p_debt; reasons.append(f"재무건전(부채 {debt:.1f}%)")
            
        if not pd.isna(today_rsi) and today_rsi < 40: 
            score += p_rsi; reasons.append(f"과매도(RSI {today_rsi:.1f})")
        if today_close > today_sma_20: 
            score += p_sma; reasons.append("상승 추세")
        if today_volume > today_vol_sma_20 * 1.5: 
            score += p_vol; reasons.append("거래량 터짐")
            
    else:
        p_rsi, p_sma, p_vol = 20, 20, 20
        p_foreign, p_inst = 20, 20 

        if not pd.isna(today_rsi) and today_rsi < 65: 
            score += p_rsi; reasons.append(f"상승여력(RSI {today_rsi:.1f})")
        if today_close > today_sma_20: 
            score += p_sma; reasons.append("상승 추세")
        if today_volume > today_vol_sma_20 * 1.2: 
            score += p_vol; reasons.append("거래량 증가")

        if supply_info:
            foreign_days = supply_info.get('foreign_buy_days', 0)
            inst_days = supply_info.get('inst_buy_days', 0)
            
            if foreign_days >= 2: 
                score += p_foreign; reasons.append(f"외국인 {foreign_days}일 연속 픽")
            elif foreign_days == 1:
                score += (p_foreign // 2); reasons.append("외국인 오늘 매수")
                
            if inst_days >= 2:
                score += p_inst; reasons.append(f"기관 {inst_days}일 연속 픽")
            elif inst_days == 1:
                score += (p_inst // 2); reasons.append("기관 오늘 매수")
        
    BUY_THRESHOLD = 55
    signal = 'BUY' if score >= BUY_THRESHOLD else 'HOLD'
    
    tag = "[ETF]" if is_etf else f"[{market_type}]"
    if score >= BUY_THRESHOLD:
        reasons.append(f"종합 점수: {int(score)}점 {tag}")
    
    return signal, int(score), reasons