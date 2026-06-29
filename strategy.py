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
    """매물대(Volume Profile) 중 가장 두터운 가격대(Point of Control) 계산"""
    try:
        hist, bin_edges = np.histogram(df['Close'], bins=bins, weights=df['Volume'])
        max_bin_idx = np.argmax(hist)
        poc_price = (bin_edges[max_bin_idx] + bin_edges[max_bin_idx + 1]) / 2
        return poc_price
    except:
        return df['Close'].mean()

def apply_multi_factor_strategy(df, fundamentals, market_type='NASDAQ', supply_info=None, stock_name=""):
    if df is None or len(df) < 20:
        return 'HOLD', 0, ["데이터 부족"], df 
        
    df = df.copy() 
    df['RSI'] = calculate_rsi(df['Close'])
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['Volume_SMA_20'] = df['Volume'].rolling(window=20).mean()
    
    # 💡 [추가] OBV 계산
    df['OBV'] = (np.sign(df['Close'].diff()) * df['Volume']).fillna(0).cumsum()
    df['OBV_SMA_20'] = df['OBV'].rolling(window=20).mean()
    
    today_rsi = df['RSI'].iloc[-1]
    today_close = df['Close'].iloc[-1]
    today_sma_20 = df['SMA_20'].iloc[-1]
    today_volume = df['Volume'].iloc[-1]
    today_vol_sma_20 = df['Volume_SMA_20'].iloc[-1]
    
    today_obv = df['OBV'].iloc[-1]
    today_obv_sma = df['OBV_SMA_20'].iloc[-1]
    poc_price = get_poc_price(df) # 가장 두터운 매물대 가격
    
    score = 0
    reasons = []
    BUY_THRESHOLD = 55
    
    etf_keywords = ['레버리지', '인버스', 'KODEX', 'TIGER', 'ETF', 'TRUST', 'FUND', 'PROSHARES', 'DIREXION']
    is_etf = any(keyword in str(stock_name).upper() for keyword in etf_keywords)

    if is_etf:
        if today_close <= today_sma_20:
            reasons.append("추세 이탈(20일선 하회)")
            return 'HOLD', 0, reasons, df
            
        p_sma, p_rsi, p_vol, p_obv, p_poc = 20, 20, 20, 20, 20
        score += p_sma; reasons.append("확실한 추세(20일선 위)")
        
        if not pd.isna(today_rsi) and today_rsi < 65: score += p_rsi; reasons.append(f"상승여력(RSI {today_rsi:.1f})")
        if today_volume > today_vol_sma_20 * 1.2: score += p_vol; reasons.append("거래량 유입")
        if today_obv > today_obv_sma: score += p_obv; reasons.append("OBV 매집 포착")
        if today_close > poc_price: score += p_poc; reasons.append("주요 매물대 돌파")
            
    elif market_type == 'NASDAQ':
        # 펀더멘털(40) + 기술적/수급(60)
        p_per, p_pbr, p_roe, p_debt = 10, 10, 10, 10
        p_rsi, p_sma, p_vol, p_obv, p_poc = 10, 10, 10, 15, 15
        
        per = fundamentals.get('PER', 0)
        if per and 0 < per < 20: score += p_per; reasons.append(f"PER 저평가({per:.1f})")
            
        pbr = fundamentals.get('PBR', 0)
        if pbr and 0 < pbr < 2.0: score += p_pbr; reasons.append(f"PBR 우수({pbr:.1f})")
            
        roe = fundamentals.get('ROE', 0)
        if roe and roe > 0.12: score += p_roe; reasons.append(f"고수익성(ROE {roe*100:.1f}%)")
            
        debt = fundamentals.get('Debt_Ratio', 999) 
        if debt and debt < 100: score += p_debt; reasons.append(f"재무건전(부채 {debt:.1f}%)")
            
        if not pd.isna(today_rsi) and today_rsi < 40: score += p_rsi; reasons.append(f"과매도(RSI {today_rsi:.1f})")
        if today_close > today_sma_20: score += p_sma; reasons.append("상승 추세")
        if today_volume > today_vol_sma_20 * 1.5: score += p_vol; reasons.append("거래량 터짐")
        if today_obv > today_obv_sma: score += p_obv; reasons.append("OBV 매집 포착")
        if today_close > poc_price: score += p_poc; reasons.append("주요 매물대 돌파")
            
    else: # KOSDAQ / KOSPI
        p_rsi, p_sma, p_vol = 10, 10, 10
        p_obv, p_poc = 15, 15
        p_foreign, p_inst = 15, 15
        p_synergy = 10 

        if not pd.isna(today_rsi) and today_rsi < 65: score += p_rsi; reasons.append(f"상승여력(RSI {today_rsi:.1f})")
        if today_close > today_sma_20: score += p_sma; reasons.append("상승 추세")
        if today_volume > today_vol_sma_20 * 1.2: score += p_vol; reasons.append("거래량 증가")
        if today_obv > today_obv_sma: score += p_obv; reasons.append("OBV 상승(매집)")
        if today_close > poc_price: score += p_poc; reasons.append("최대 매물대 돌파")

        supply_info = supply_info or {}
        foreign_days = supply_info.get('foreign_buy_days', 0)
        inst_days = supply_info.get('inst_buy_days', 0)
        
        if foreign_days >= 2: score += p_foreign; reasons.append(f"외국인 {foreign_days}일 연속 픽")
        elif foreign_days == 1: score += (p_foreign // 2); reasons.append("외국인 오늘 매수")
            
        if inst_days >= 2: score += p_inst; reasons.append(f"기관 {inst_days}일 연속 픽")
        elif inst_days == 1: score += (p_inst // 2); reasons.append("기관 오늘 매수")
        
        # 💡 [추가] 수급-지표 시너지 가점
        if today_close > today_sma_20 and (foreign_days > 0 or inst_days > 0):
            score += p_synergy; reasons.append("🔥 추세+수급 동반 시너지")
        
    signal = 'BUY' if score >= BUY_THRESHOLD else 'HOLD'
    
    tag = "[ETF]" if is_etf else f"[{market_type}]"
    if score >= BUY_THRESHOLD:
        reasons.append(f"종합 점수: {int(score)}점 {tag}")
    
    return signal, int(score), reasons, df