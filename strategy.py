# 업데이트날짜: 2026.07.07
# 작성자: j-neat
# 투자 전략 및 시그널 전담 모듈 (RSI 모멘텀 보정 및 매물대 기간 고정, 낙폭과대 예외 추가)

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

# 💡 [수정 2] 매물대 계산 시 최근 120일(약 6개월) 고정 윈도우 적용
def get_poc_price(df, bins=20, window=120):
    try:
        recent_df = df.tail(window)
        hist, bin_edges = np.histogram(recent_df['Close'], bins=bins, weights=recent_df['Volume'])
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

    df['Turnover'] = df['Close'] * df['Volume']
    avg_turnover_5d = df['Turnover'].rolling(window=5).mean().iloc[-1]

    if not is_bull_market:
        return 'HOLD', 0, ["🚫 거시경제 하락장 (지수 200일선 하회)으로 인한 매수 차단"], df, {}

    if market_type == 'NASDAQ':
        min_turnover = 10_000_000 
    else:
        min_turnover = 10_000_000_000 
        
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
    
    high_52w = df['High'].rolling(window=min(252, len(df))).max().iloc[-1]
    
    gap_percent = ((today_close - today_sma_20) / today_sma_20 * 100) if today_sma_20 > 0 else 0.0
    
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
        # 💡 [수정 3] 20일선 아래라도, -5% 이상 벌어진 과대낙폭 상태면 예외적으로 통과 허용
        if today_close <= today_sma_20 and gap_percent > -5.0:
            return 'HOLD', 0, ["추세 이탈(20일선 하회 및 애매한 위치)"], df, {}
            
        # 💡 [수정 1] RSI 모멘텀 타겟 상향 (60 이상 시 만점)
        rsi_score = min(20.0, (today_rsi / 60.0) * 20.0) if not pd.isna(today_rsi) else 0.0
        score += rsi_score
        reasons.append(f"RSI({rsi_score:.1f}점)")

        vol_ratio = today_volume / today_vol_sma_20 if today_vol_sma_20 > 0 else 1.0
        vol_score = min(20.0, (vol_ratio / 2.0) * 20.0)
        score += vol_score
        reasons.append(f"거래량({vol_score:.1f}점)")

        # 💡 [수정 3 연계] 낙폭 과대 시 20일선 이격도에 프리미엄 만점 부여
        if 0 < gap_percent <= 3:
            sma_score = min(20.0, (gap_percent / 3.0) * 20.0)
        elif gap_percent <= -5.0:
            sma_score = 20.0 # 낙폭과대 프리미엄
        else:
            sma_score = 0.0
            
        score += sma_score
        reasons.append(f"20일선 이격({sma_score:.1f}점)")

        obv_ratio = today_obv / today_obv_sma if today_obv_sma > 0 else 1.0
        obv_score = min(20.0, (obv_ratio / 1.1) * 20.0) if obv_ratio > 1.0 else 0.0
        score += obv_score
        reasons.append(f"OBV({obv_score:.1f}점)")

        poc_gap = ((today_close - poc_price) / poc_price * 100) if poc_price > 0 else 0.0
        poc_score = min(20.0, (poc_gap / 3.0) * 20.0) if poc_gap > 0 else 0.0
        score += poc_score
        reasons.append(f"매물대 돌파({poc_score:.1f}점)")

    elif market_type == 'NASDAQ':
        per = fundamentals.get('PER', 0)
        per_score = 10.0 if 0 < per < 20 else 0.0
        score += per_score
        
        roe = fundamentals.get('ROE', 0)
        roe_score = 10.0 if roe >= 0.12 else 0.0
        score += roe_score
        
        reasons.append(f"재무({per_score+roe_score:.1f}점)")
            
        high_gap = today_close / high_52w if high_52w > 0 else 0.0
        high_score = min(20.0, (high_gap / 0.95) * 20.0)
        score += high_score
        
        # 💡 [수정 1] 미장 RSI 모멘텀 타겟 (60 이상 시 만점)
        rsi_score = min(15.0, (today_rsi / 60.0) * 15.0) if not pd.isna(today_rsi) else 0.0
        score += rsi_score
        
        vol_ratio = today_volume / today_vol_sma_20 if today_vol_sma_20 > 0 else 1.0
        vol_score = min(15.0, (vol_ratio / 2.0) * 15.0)
        score += vol_score
        
        sma_score = min(15.0, (gap_percent / 3.0) * 15.0) if gap_percent > 0 else 0.0
        score += sma_score
        
        poc_gap = ((today_close - poc_price) / poc_price * 100) if poc_price > 0 else 0.0
        poc_score = min(15.0, (poc_gap / 3.0) * 15.0) if poc_gap > 0 else 0.0
        score += poc_score
        
        reasons.append(f"모멘텀({high_score+rsi_score+vol_score+sma_score+poc_score:.1f}점)")
            
    else: 
        # 💡 [수정 1] 국장 RSI 모멘텀 타겟 (60 이상 시 만점)
        rsi_score = min(15.0, (today_rsi / 60.0) * 15.0) if not pd.isna(today_rsi) else 0.0
        
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
            reasons.insert(0, f"\n🌟 [주말 돌파 VIP] 하락 압력을 이겨낸 찐텐 종목! (총 {score:.1f}점)\n")
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