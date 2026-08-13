# strategy.py
# 업데이트날짜: 2026.08.13
# 작성자: j-neat
# 투자 전략 및 시그널 전담 모듈 (연속형 스코어링 및 RSI 과열 방지 적용 버전)

import pandas as pd
import numpy as np
import os
import yfinance as yf
from supabase import create_client

def check_recent_events(ticker, df, today_close):
    try:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        supabase = create_client(url, key)
        
        response = supabase.table("dart_disclosures").select("event_type, report_title, rcept_dt").eq("ticker", ticker).execute()
        
        event_score = 0
        event_msgs = []
        
        for item in response.data:
            event_type = item['event_type']
            title = item['report_title']
            rcept_dt = f"{item['rcept_dt'][:4]}-{item['rcept_dt'][4:6]}-{item['rcept_dt'][6:]}"
            
            try:
                base_price = df.loc[:rcept_dt]['Close'].iloc[-1]
                price_change_pct = ((today_close - base_price) / base_price) * 100
            except:
                base_price = today_close
                price_change_pct = 0.0

            # 💡 [수정] 선반영률에 따른 선형 점수 부여
            if event_type == 'GOOD':
                if price_change_pct >= 5.0:
                    event_msgs.append(f"⚠️ 호재 선반영 차단: {title[:15]}... (이미 {price_change_pct:.1f}% 상승)")
                else:
                    bonus = max(0.0, 10.0 * (5.0 - price_change_pct) / 5.0)
                    event_score += bonus
                    event_msgs.append(f"🎉 호재공시(+{bonus:.1f}): {title[:15]}... (반영률 {price_change_pct:.1f}%)")
                    
            elif event_type == 'BAD':
                if price_change_pct <= -10.0:
                    event_score -= 15.0
                    event_msgs.append(f"⚠️ 악재 과매도: {title[:15]}... (이미 {price_change_pct:.1f}% 하락, -15점)")
                else:
                    penalty = -30.0 * (10.0 - abs(price_change_pct)) / 10.0
                    event_score += penalty
                    event_msgs.append(f"🚨 악재공시({penalty:.1f}): {title[:15]}... (반영률 {price_change_pct:.1f}%)")
                
        return event_score, event_msgs
    except:
        return 0, []

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# 💡 [신규] RSI 정규분포형 스코어링 함수 (과열 진입 시 점수 차감)
def get_rsi_score(rsi, max_score):
    if pd.isna(rsi): 
        return 0.0
    if rsi < 40: 
        # 침체구간: 오를수록 점수 증가
        return max_score * (rsi / 40.0)
    elif 40 <= rsi <= 65: 
        # 골디락스(안정적 상승): 만점
        return max_score
    elif 65 < rsi <= 85: 
        # 과열구간: 85에 가까워질수록 점수 깎임
        return max_score * ((85.0 - rsi) / 20.0)
    else: 
        # 85 초과 극단적 과매수: 강한 페널티
        return -max_score * 0.5 

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

def calculate_heikin_ashi(df):
    ha_df = df.copy()
    ha_df['HA_Close'] = (ha_df['Open'] + ha_df['High'] + ha_df['Low'] + ha_df['Close']) / 4
    ha_df['HA_Open'] = 0.0
    
    col_idx = ha_df.columns.get_loc('HA_Open')
    ha_df.iloc[0, col_idx] = (ha_df['Open'].iloc[0] + ha_df['Close'].iloc[0]) / 2

    for i in range(1, len(ha_df)):
        ha_df.iloc[i, col_idx] = (ha_df.iloc[i-1, col_idx] + ha_df['HA_Close'].iloc[i-1]) / 2

    ha_df['HA_High'] = ha_df[['High', 'HA_Open', 'HA_Close']].max(axis=1)
    ha_df['HA_Low'] = ha_df[['Low', 'HA_Open', 'HA_Close']].min(axis=1)
    
    return ha_df

def check_30min_rule(ticker):
    try:
        intra_df = yf.download(ticker, period='1d', interval='5m', progress=False)
        
        if intra_df.empty or len(intra_df) < 6:
            return 'PASS', 0, "장 초반 30분 데이터 부족(관망)"

        if isinstance(intra_df.columns, pd.MultiIndex):
            intra_df.columns = intra_df.columns.get_level_values(0)

        first_30m = intra_df.iloc[:6]
        open_price = first_30m['Open'].iloc[0]
        close_30m = first_30m['Close'].iloc[-1]
        high_30m = first_30m['High'].max()
        low_30m = first_30m['Low'].min()

        volatility = (high_30m - low_30m) / open_price * 100
        
        # 💡 [수정] 돌파/방어 강도(변동률)에 따른 비례 점수
        gap_pct = abs((close_30m - open_price) / open_price * 100)
        bonus_score = min(15.0, (gap_pct / 1.5) * 15.0)

        if volatility < 0.5:
            return 'BLOCK', -100, "🚫 [30분 법칙] 변동성 실종 (당일 큰 시세 기대 어려움)"

        if high_30m > open_price:
            if close_30m < open_price:
                return 'BLOCK', -100, "🚫 [30분 법칙] 상승 후 하락하여 시가 이탈 (매수 금지)"
            elif low_30m < high_30m and close_30m >= open_price:
                return 'BONUS', round(bonus_score, 1), f"🔥 [30분 법칙] 시가 방어 성공 (+{bonus_score:.1f}점)"

        if low_30m < open_price:
            if close_30m > open_price:
                return 'BONUS', round(bonus_score, 1), f"🔥 [30분 법칙] 하락 후 시가 돌파 (+{bonus_score:.1f}점)"
            elif close_30m > low_30m and close_30m <= open_price:
                return 'BLOCK', -100, "🚫 [30분 법칙] 하락 후 반등했으나 시가 돌파 실패 (매수 금지)"

        return 'PASS', 0, ""
    except Exception as e:
        return 'PASS', 0, ""

def apply_multi_factor_strategy(df, fundamentals, market_type='US', supply_info=None, stock_name="", is_bull_market=True, ticker=""):
    if df is None or len(df) < 20:
        return 'HOLD', 0, ["데이터 부족"], df, {}
        
    df = df.copy() 
    
    ha_df = calculate_heikin_ashi(df)
    today_ha_open = ha_df['HA_Open'].iloc[-1]
    today_ha_close = ha_df['HA_Close'].iloc[-1]
    today_ha_low = ha_df['HA_Low'].iloc[-1]
    
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
        return 'HOLD', 0, ["🚫 유동성 부족"], df, {}

    today_rsi = df['RSI'].iloc[-1]
    today_close = df['Close'].iloc[-1]
    today_open = df['Open'].iloc[-1] 
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

    rule_status, rule_score, rule_msg = check_30min_rule(ticker)
    if rule_status == 'BLOCK':
        return 'HOLD', 0, [rule_msg], df, {}
    elif rule_status == 'BONUS':
        score += rule_score
        reasons.append(rule_msg)

    # 💡 [수정] 하이킨아시 몸통 비율(추세 강도)에 따른 선형 점수
    ha_body_pct = (today_ha_close - today_ha_open) / today_ha_open * 100
    if today_ha_close < today_ha_open:
        penalty = max(-20.0, (ha_body_pct / 3.0) * 20.0) 
        score += penalty
        reasons.append(f"⚠️ 하이킨아시 음봉 (추세 하락중, {penalty:.1f}점)")
    elif today_ha_close > today_ha_open and today_ha_low == today_ha_open:
        bonus = min(15.0, (ha_body_pct / 3.0) * 15.0)
        score += bonus
        reasons.append(f"🔥 하이킨아시 찐양봉 (강력한 상승 추세 +{bonus:.1f}점)")

    # -----------------------------------------------------
    # 스코어링 로직 
    # -----------------------------------------------------
    if is_etf:
        if today_close <= today_sma_20 and gap_percent > -5.0:
            return 'HOLD', 0, ["추세 이탈"], df, {}
            
        score += get_rsi_score(today_rsi, 20.0)
        
        vol_ratio = today_volume / today_vol_sma_20 if today_vol_sma_20 > 0 else 1.0
        score += min(20.0, (vol_ratio / 2.0) * 20.0)
        
        if 0 < gap_percent <= 3:
            score += min(20.0, (gap_percent / 3.0) * 20.0)
        elif gap_percent <= -5.0:
            score += 20.0 
            
        obv_ratio = today_obv / today_obv_sma if today_obv_sma > 0 else 1.0
        score += min(20.0, (obv_ratio / 1.1) * 20.0) if obv_ratio > 1.0 else 0.0
        
        poc_gap = ((today_close - poc_price) / poc_price * 100) if poc_price > 0 else 0.0
        score += min(20.0, (poc_gap / 3.0) * 20.0) if poc_gap > 0 else 0.0
        
        reasons.append(f"기술점수반영")

    elif market_type == 'NASDAQ':
        # 💡 [수정] PER, ROE 선형 비율 점수 적용
        per = fundamentals.get('PER', 0)
        if 0 < per < 20:
            score += 10.0 * ((20.0 - per) / 20.0)
            
        roe = fundamentals.get('ROE', 0)
        if roe > 0:
            score += min(10.0, (roe / 0.12) * 5.0) 
            
        high_gap = today_close / high_52w if high_52w > 0 else 0.0
        score += min(20.0, (high_gap / 0.95) * 20.0)
        
        score += get_rsi_score(today_rsi, 15.0)
        
        vol_ratio = today_volume / today_vol_sma_20 if today_vol_sma_20 > 0 else 1.0
        score += min(15.0, (vol_ratio / 2.0) * 15.0)
        score += min(15.0, (gap_percent / 3.0) * 15.0) if gap_percent > 0 else 0.0
        
        poc_gap = ((today_close - poc_price) / poc_price * 100) if poc_price > 0 else 0.0
        score += min(15.0, (poc_gap / 3.0) * 15.0) if poc_gap > 0 else 0.0
        
    else: 
        score += get_rsi_score(today_rsi, 15.0)
        score += min(15.0, (gap_percent / 3.0) * 15.0) if gap_percent > 0 else 0.0
        
        vol_ratio = today_volume / today_vol_sma_20 if today_vol_sma_20 > 0 else 1.0
        score += min(15.0, (vol_ratio / 2.0) * 15.0)
        
        poc_gap = ((today_close - poc_price) / poc_price * 100) if poc_price > 0 else 0.0
        score += min(15.0, (poc_gap / 3.0) * 15.0) if poc_gap > 0 else 0.0
        
        supply_info = supply_info or {}
        foreign_days = supply_info.get('foreign_buy_days', 0)
        inst_days = supply_info.get('inst_buy_days', 0)
        score += min(20.0, (foreign_days / 3.0) * 20.0)
        score += min(20.0, (inst_days / 3.0) * 20.0)

    if market_type in ['KR', 'KOSPI', 'KOSDAQ'] and not is_etf:
        event_bonus, event_msgs = check_recent_events(ticker, df, today_close)
        if event_bonus != 0 or event_msgs:
            score += event_bonus
            reasons.extend(event_msgs)

    signal = 'BUY' if score >= BUY_THRESHOLD else 'HOLD'
    
    if score >= BUY_THRESHOLD: 
        if today_weekday in [3, 4]:
            reasons.insert(0, f"\n🌟 [주말 돌파 VIP] (최종 {score:.1f}점)\n")
        else:
            reasons.append(f"최종: {score:.1f}점")
            
        reasons.append("\n⚠️ [주의] 매수 직후 당일 시가 기준으로 예약 매도를 세팅하세요!")

    target_price = 0
    stop_loss = 0
    
    resistance_price = min(bb_upper, poc_price)
    kr_atr_target = today_open + (today_atr * 2.0) 
    us_atr_target = today_open + (today_atr * 3.0) 
    
    if market_type in ['KR', 'KOSPI', 'KOSDAQ']:
        if resistance_price <= today_open + (today_atr * 1.0):
            target_price = kr_atr_target 
        else:
            target_price = resistance_price 
            
        stop_loss = today_open - (today_atr * 2.0)
        
    else: 
        if bb_upper <= today_open + (today_atr * 1.5):
            target_price = us_atr_target
        else:
            target_price = bb_upper
            
        stop_loss = today_open - (today_atr * 2.0)
        
    price_targets = {'TP': int(target_price), 'SL': int(stop_loss)}
    
    return signal, round(score, 1), reasons, df, price_targets