# strategy.py
# 업데이트날짜: 2026.07.07
# 작성자: j-neat
# 투자 전략 및 시그널 전담 모듈 (이벤트 드리븐 & 선반영 차단 버전)

import pandas as pd
import numpy as np
import os
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

            if event_type == 'GOOD':
                if price_change_pct >= 5.0:
                    event_msgs.append(f"⚠️ 호재 선반영 차단: {title[:15]}... (이미 {price_change_pct:.1f}% 상승)")
                else:
                    event_score += 10.0
                    event_msgs.append(f"🎉 호재공시(+10): {title[:15]}... (반영률 {price_change_pct:.1f}%)")
                    
            elif event_type == 'BAD':
                if price_change_pct <= -10.0:
                    event_score -= 15.0
                    event_msgs.append(f"⚠️ 악재 과매도: {title[:15]}... (이미 {price_change_pct:.1f}% 하락, -15점)")
                else:
                    event_score -= 30.0
                    event_msgs.append(f"🚨 악재공시(-30): {title[:15]}... (반영률 {price_change_pct:.1f}%)")
                
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

def apply_multi_factor_strategy(df, fundamentals, market_type='US', supply_info=None, stock_name="", is_bull_market=True, ticker=""):
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
        return 'HOLD', 0, ["🚫 유동성 부족"], df, {}

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

    if is_etf:
        if today_close <= today_sma_20 and gap_percent > -5.0:
            return 'HOLD', 0, ["추세 이탈"], df, {}
            
        rsi_score = min(20.0, (today_rsi / 60.0) * 20.0) if not pd.isna(today_rsi) else 0.0
        score += rsi_score
        
        vol_ratio = today_volume / today_vol_sma_20 if today_vol_sma_20 > 0 else 1.0
        vol_score = min(20.0, (vol_ratio / 2.0) * 20.0)
        score += vol_score
        
        if 0 < gap_percent <= 3:
            sma_score = min(20.0, (gap_percent / 3.0) * 20.0)
        elif gap_percent <= -5.0:
            sma_score = 20.0 
        else:
            sma_score = 0.0
        score += sma_score
        
        obv_ratio = today_obv / today_obv_sma if today_obv_sma > 0 else 1.0
        obv_score = min(20.0, (obv_ratio / 1.1) * 20.0) if obv_ratio > 1.0 else 0.0
        score += obv_score
        
        poc_gap = ((today_close - poc_price) / poc_price * 100) if poc_price > 0 else 0.0
        poc_score = min(20.0, (poc_gap / 3.0) * 20.0) if poc_gap > 0 else 0.0
        score += poc_score
        
        reasons.append(f"기술점수({score:.1f})")

    elif market_type == 'NASDAQ':
        per = fundamentals.get('PER', 0)
        score += 10.0 if 0 < per < 20 else 0.0
        roe = fundamentals.get('ROE', 0)
        score += 10.0 if roe >= 0.12 else 0.0
        
        high_gap = today_close / high_52w if high_52w > 0 else 0.0
        score += min(20.0, (high_gap / 0.95) * 20.0)
        score += min(15.0, (today_rsi / 60.0) * 15.0) if not pd.isna(today_rsi) else 0.0
        vol_ratio = today_volume / today_vol_sma_20 if today_vol_sma_20 > 0 else 1.0
        score += min(15.0, (vol_ratio / 2.0) * 15.0)
        score += min(15.0, (gap_percent / 3.0) * 15.0) if gap_percent > 0 else 0.0
        poc_gap = ((today_close - poc_price) / poc_price * 100) if poc_price > 0 else 0.0
        score += min(15.0, (poc_gap / 3.0) * 15.0) if poc_gap > 0 else 0.0
        
        reasons.append(f"총점({score:.1f}점)")
            
    else: 
        score += min(15.0, (today_rsi / 60.0) * 15.0) if not pd.isna(today_rsi) else 0.0
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
        
        reasons.append(f"차트/수급({score:.1f}점)")

    # 💡 [핵심] 공시 이벤트(선반영 필터 적용) 점수 합산
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
            
        reasons.append("\n⚠️ [주의] 매수 직후 증권사 앱에서 예약 매도를 세팅하세요!")

    target_price = 0
    stop_loss = 0
    
    if market_type in ['KR', 'KOSPI', 'KOSDAQ']:
        target_price = min(bb_upper, poc_price)
        if target_price <= today_close: 
            target_price = today_close + (today_atr * 1.5)
        stop_loss = today_close - (today_atr * 2)
    else: 
        target_price = today_close + (today_atr * 1.5)
        stop_loss = max(today_sma_20, today_close - (today_atr * 1.5))
        
    price_targets = {'TP': int(target_price), 'SL': int(stop_loss)}
    
    return signal, round(score, 1), reasons, df, price_targets