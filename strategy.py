# 업데이트날짜: 2026.07.02
# 작성자: j-neat
# 투자 전략 및 시그널 전담 모듈 (유동성 필터 + 미장 모멘텀 + 직관적 비례 스코어링 적용)

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

def calculate_atr(df, period=14):
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    return true_range.rolling(window=period).mean()

def apply_multi_factor_strategy(df, fundamentals, market_type='US', supply_info=None, stock_name="", is_bull_market=True):
    if df is None or len(df) < 20:
        return 'HOLD', 0, ["데이터 부족"], df, {}
        
    df = df.copy() 
    df['RSI'] = calculate_rsi(df['Close'])
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['Volume_SMA_20'] = df['Volume'].rolling(window=20).mean()
    df['OBV'] = (np.sign(df['Close'].diff()) * df['Volume']).fillna(0).cumsum()
    df['OBV_SMA_20'] = df['OBV'].rolling(window=20).mean()
    
    df['BB_Upper'] = df['SMA_20'] + (2 * df['Close'].rolling(window=20).std())
    df['ATR'] = calculate_atr(df)

    # 💡 1. 거래대금 계산 (잡주 필터링용)
    df['Turnover'] = df['Close'] * df['Volume']
    avg_turnover_5d = df['Turnover'].rolling(window=5).mean().iloc[-1]

    # 거시경제 하락장 차단
    if not is_bull_market:
        return 'HOLD', 0, ["🚫 거시경제 하락장 (지수 200일선 하회)으로 인한 매수 차단"], df, {}

    # 💡 2. 유동성 하드 필터 (잡주/소외주 원천 차단)
    if market_type == 'NASDAQ':
        min_turnover = 10_000_000 # 미장: 5일 평균 거래대금 1천만 달러 이상
    else:
        min_turnover = 10_000_000_000 # 국장: 5일 평균 거래대금 100억 원 이상
        
    if avg_turnover_5d < min_turnover:
        return 'HOLD', 0, ["🚫 유동성 부족 (소외주/잡주 리스크 필터링)"], df, {}

    today_rsi = df['RSI'].iloc[-1]
    today_close = df['Close'].iloc[-1]
    today_sma_20 = df['SMA_20'].iloc[-1]
    today_volume = df['Volume'].iloc[-1]
    today_vol_sma_20 = df['Volume_SMA_20'].iloc[-1]
    today_obv = df['OBV'].iloc[-1]
    today_obv_sma = df['OBV_SMA_20'].iloc[-1]
    poc_price = get_poc_price(df) 
    
    today_atr = df['ATR'].fillna(today_close * 0.03).iloc[-1]
    bb_upper = df['BB_Upper'].fillna(today_close).iloc[-1]
    
    # 52주 고가 (미장 모멘텀 팩터용)
    high_52w = df['High'].rolling(window=min(252, len(df))).max().iloc[-1]
    
    today_weekday = df.index[-1].weekday()
    BUY_THRESHOLD = 60.0 if today_weekday in [3, 4] else 50.0
    
    score = 0.0
    reasons = []
    
    etf_keywords = ['레버리지', '인버스', 'KODEX', 'TIGER', 'ETF', 'TRUST', 'FUND', 'PROSHARES', 'DIREXION', 'ACE']
    is_etf = any(keyword in str(stock_name).upper() for keyword in etf_keywords)

    # ==========================================
    # 직관적 비례 스코어링 (현재값 / 목표값 * 만점)
    # ==========================================
    
    if is_etf:
        if today_close <= today_sma_20:
            return 'HOLD', 0, ["추세 이탈(20일선 하회)"], df, {}
            
        # 1. RSI (목표: 30 이상 돌파 시 만점 20점)
        rsi_score = min(20.0, (today_rsi / 30.0) * 20.0) if not pd.isna(today_rsi) else 0.0
        score += rsi_score
        reasons.append(f"RSI({rsi_score:.1f}점)")

        # 2. 거래량 (목표: 평균대비 2배 터지면 만점 20점)
        vol_ratio = today_volume / today_vol_sma_20 if today_vol_sma_20 > 0 else 1.0
        vol_score = min(20.0, (vol_ratio / 2.0) * 20.0)
        score += vol_score
        reasons.append(f"거래량({vol_score:.1f}점)")

        # 3. 20일선 이격도 (목표: 20일선 대비 3% 이상 상승 시 만점 20점)
        gap_percent = ((today_close - today_sma_20) / today_sma_20 * 100) if today_sma_20 > 0 else 0.0
        sma_score = min(20.0, (gap_percent / 3.0) * 20.0) if gap_percent > 0 else 0.0
        score += sma_score
        reasons.append(f"20일선 이격({sma_score:.1f}점)")

        # 4. OBV 상승 (목표: OBV가 평균을 상회하는 비율에 따라 최대 20점)
        obv_ratio = today_obv / today_obv_sma if today_obv_sma > 0 else 1.0
        obv_score = min(20.0, (obv_ratio / 1.1) * 20.0) if obv_ratio > 1.0 else 0.0
        score += obv_score
        reasons.append(f"OBV({obv_score:.1f}점)")

        # 5. 매물대 돌파 (목표: 매물대 대비 3% 이상 돌파 시 만점 20점)
        poc_gap = ((today_close - poc_price) / poc_price * 100) if poc_price > 0 else 0.0
        poc_score = min(20.0, (poc_gap / 3.0) * 20.0) if poc_gap > 0 else 0.0
        score += poc_score
        reasons.append(f"매물대 돌파({poc_score:.1f}점)")

    elif market_type == 'NASDAQ':
        # 💡 미장 펀더멘털 비중 축소 (총 20점)
        per = fundamentals.get('PER', 0)
        per_score = 10.0 if 0 < per < 20 else 0.0
        score += per_score
        
        roe = fundamentals.get('ROE', 0)
        roe_score = 10.0 if roe >= 0.12 else 0.0
        score += roe_score
        
        reasons.append(f"재무({per_score+roe_score:.1f}점)")
            
        # 💡 미장 기술적 모멘텀 강화 (총 80점)
        # 1. 52주 신고가 근접도 (목표: 52주 고가 대비 95% 이상 도달 시 만점 20점)
        high_gap = today_close / high_52w if high_52w > 0 else 0.0
        high_score = min(20.0, (high_gap / 0.95) * 20.0)
        score += high_score
        
        # 2. RSI (목표 50 이상 도달 시 만점 15점 - 추세장)
        rsi_score = min(15.0, (today_rsi / 50.0) * 15.0) if not pd.isna(today_rsi) else 0.0
        score += rsi_score
        
        # 3. 거래량 폭발 (목표 2배 달성 시 15점)
        vol_ratio = today_volume / today_vol_sma_20 if today_vol_sma_20 > 0 else 1.0
        vol_score = min(15.0, (vol_ratio / 2.0) * 15.0)
        score += vol_score
        
        # 4. 20일선 추세 (목표 3% 달성 시 15점)
        gap_percent = ((today_close - today_sma_20) / today_sma_20 * 100) if today_sma_20 > 0 else 0.0
        sma_score = min(15.0, (gap_percent / 3.0) * 15.0) if gap_percent > 0 else 0.0
        score += sma_score
        
        # 5. 매물대 돌파 (목표 3% 달성 시 15점)
        poc_gap = ((today_close - poc_price) / poc_price * 100) if poc_price > 0 else 0.0
        poc_score = min(15.0, (poc_gap / 3.0) * 15.0) if poc_gap > 0 else 0.0
        score += poc_score
        
        reasons.append(f"모멘텀({high_score+rsi_score+vol_score+sma_score+poc_score:.1f}점)")
            
    else: 
        # 국장 로직 (총 100점 비례식 분배)
        rsi_score = min(15.0, (today_rsi / 30.0) * 15.0) if not pd.isna(today_rsi) else 0.0
        
        gap_percent = ((today_close - today_sma_20) / today_sma_20 * 100) if today_sma_20 > 0 else 0.0
        sma_score = min(15.0, (gap_percent / 3.0) * 15.0) if gap_percent > 0 else 0.0
        
        vol_ratio = today_volume / today_vol_sma_20 if today_vol_sma_20 > 0 else 1.0
        vol_score = min(15.0, (vol_ratio / 2.0) * 15.0)
        
        poc_gap = ((today_close - poc_price) / poc_price * 100) if poc_price > 0 else 0.0
        poc_score = min(15.0, (poc_gap / 3.0) * 15.0) if poc_gap > 0 else 0.0
        
        score += (rsi_score + sma_score + vol_score + poc_score)
        reasons.append(f"기술({rsi_score+sma_score+vol_score+poc_score:.1f}점)")

        supply_info = supply_info or {}
        foreign_days = supply_info.get('foreign_buy_days', 0)
        inst_days = supply_info.get('inst_buy_days', 0)
        
        # 수급 점수 (목표: 3일 연속 매수 시 만점 20점)
        foreign_score = min(20.0, (foreign_days / 3.0) * 20.0)
        inst_score = min(20.0, (inst_days / 3.0) * 20.0)
        score += (foreign_score + inst_score)
        
        if foreign_days > 0 or inst_days > 0:
            reasons.append(f"메이저수급({foreign_score+inst_score:.1f}점)")

    # ==========================================
    # 시그널 판정 및 타겟 가격 도출
    # ==========================================
    signal = 'BUY' if score >= BUY_THRESHOLD else 'HOLD'
    
    if score >= BUY_THRESHOLD: 
        if today_weekday in [3, 4]:
            reasons.insert(0, f"\n🌟 [목/금 리스크 돌파 VIP] 하락 압력을 이겨낸 찐텐 종목! (총 {score:.1f}점)\n")
        else:
            reasons.append(f"종합: {score:.1f}점 [{market_type}]")
            
        reasons.append("\n⚠️ [주의] 매수 직후 증권사 앱에서 '자동 감시 주문(예약 매도)'으로 아래 익절/손절가를 반드시 세팅하세요!")

    target_price = 0
    stop_loss = 0
    
    if market_type in ['KR', 'KOSPI', 'KOSDAQ']:
        target_price = max(bb_upper, poc_price)
        if target_price <= today_close: 
            target_price = today_close + (today_atr * 1.5)
        stop_loss = today_close - (today_atr * 2)
    else: 
        target_price = today_close + (today_atr * 3)
        stop_loss = max(today_sma_20, today_close - (today_atr * 1.5))
        
    price_targets = {
        'TP': int(target_price),
        'SL': int(stop_loss)
    }
    
    return signal, round(score, 1), reasons, df, price_targets