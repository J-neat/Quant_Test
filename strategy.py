# strategy.py
# 업데이트날짜: 2026.08.10
# 작성자: j-neat
# 투자 전략 및 시그널 전담 모듈 (하이킨아시, 30분 법칙, 시가 고정 익절/손절 적용 버전)

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

# 💡 [신규] 하이킨아시 계산 함수
# 💡 [수정] 체인 할당 에러(ChainedAssignmentError) 완벽 해결 버전
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

# 💡 [신규] 장 시작 30분 법칙 검증 함수 (5분봉 활용)
def check_30min_rule(ticker):
    try:
        # 야후 파이낸스에서 오늘 하루 5분봉 데이터 로드
        intra_df = yf.download(ticker, period='1d', interval='5m', progress=False)
        
        if intra_df.empty or len(intra_df) < 6:
            return 'PASS', 0, "장 초반 30분 데이터 부족(관망)"

        if isinstance(intra_df.columns, pd.MultiIndex):
            intra_df.columns = intra_df.columns.get_level_values(0)

        # 첫 30분 (6개 캔들) 추출
        first_30m = intra_df.iloc[:6]
        open_price = first_30m['Open'].iloc[0]
        close_30m = first_30m['Close'].iloc[-1]
        high_30m = first_30m['High'].max()
        low_30m = first_30m['Low'].min()

        volatility = (high_30m - low_30m) / open_price * 100

        # 1. 움직임 없음 (0.5% 미만 변동)
        if volatility < 0.5:
            return 'BLOCK', -100, "🚫 [30분 법칙] 변동성 실종 (당일 큰 시세 기대 어려움)"

        # 2. 상승 후 하락 패턴
        if high_30m > open_price:
            if close_30m < open_price:
                return 'BLOCK', -100, "🚫 [30분 법칙] 상승 후 하락하여 시가 이탈 (매수 금지)"
            elif low_30m < high_30m and close_30m >= open_price:
                return 'BONUS', 15, "🔥 [30분 법칙] 상승 후 하락했으나 시가 방어 성공 (강한 지지)"

        # 3. 하락 후 반등 패턴
        if low_30m < open_price:
            if close_30m > open_price:
                return 'BONUS', 15, "🔥 [30분 법칙] 하락 후 반등하여 시가 돌파 (본격 상승 랠리 기대)"
            elif close_30m > low_30m and close_30m <= open_price:
                return 'BLOCK', -100, "🚫 [30분 법칙] 하락 후 반등했으나 시가 돌파 실패 (매수 금지)"

        return 'PASS', 0, ""
    except Exception as e:
        return 'PASS', 0, ""

def apply_multi_factor_strategy(df, fundamentals, market_type='US', supply_info=None, stock_name="", is_bull_market=True, ticker=""):
    if df is None or len(df) < 20:
        return 'HOLD', 0, ["데이터 부족"], df, {}
        
    df = df.copy() 
    
    # 💡 [적용] 하이킨아시 지표 계산
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
    today_open = df['Open'].iloc[-1]  # 💡 시가(Open) 고정 데이터 확보
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

    # 💡 [적용] 장 시작 30분 법칙 검증 (ETF 및 일반 주식 공통 적용)
    rule_status, rule_score, rule_msg = check_30min_rule(ticker)
    if rule_status == 'BLOCK':
        return 'HOLD', 0, [rule_msg], df, {}
    elif rule_status == 'BONUS':
        score += rule_score
        reasons.append(rule_msg)

    # 💡 [적용] 하이킨아시 추세 판별
    if today_ha_close < today_ha_open:
        score -= 20.0
        reasons.append("⚠️ 하이킨아시 음봉 (추세 하락중, -20점)")
    elif today_ha_close > today_ha_open and today_ha_low == today_ha_open:
        score += 15.0
        reasons.append("🔥 하이킨아시 찐양봉 (아래꼬리 없음, 강력한 상승 추세 +15점)")

    # -----------------------------------------------------
    # 기존 스코어링 로직 (ETF, NASDAQ, KOSPI/KOSDAQ)
    # -----------------------------------------------------
    if is_etf:
        if today_close <= today_sma_20 and gap_percent > -5.0:
            return 'HOLD', 0, ["추세 이탈"], df, {}
            
        score += min(20.0, (today_rsi / 60.0) * 20.0) if not pd.isna(today_rsi) else 0.0
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

    # 이벤트 공시 점수 합산
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

    # 💡 [핵심] 시가(Open) 고정 기반 '동적 적정 매도가' 계산 로직
    target_price = 0
    stop_loss = 0
    
    # 1. 1차 저항선 확인: 볼린저 밴드 상단과 최대 매물대(POC) 중 보수적인(낮은) 가격
    resistance_price = min(bb_upper, poc_price)
    
    # 2. 종목별 변동성(ATR) 기반 수익 목표치
    kr_atr_target = today_open + (today_atr * 2.0) # 국장은 시가 대비 ATR 2배수 수익
    us_atr_target = today_open + (today_atr * 3.0) # 미장은 시가 대비 ATR 3배수 수익
    
    if market_type in ['KR', 'KOSPI', 'KOSDAQ']:
        # 저항선이 시가보다 너무 가깝거나 낮다면 (먹을 폭이 ATR 1배수도 안 나온다면)
        if resistance_price <= today_open + (today_atr * 1.0):
            target_price = kr_atr_target # 변동성 기반 타겟으로 상향
        else:
            target_price = resistance_price # 의미 있는 저항선에서 익절
            
        # 손절가는 흔들기(휩쏘)를 견디기 위해 시가 대비 ATR 2배수 하락으로 고정
        stop_loss = today_open - (today_atr * 2.0)
        
    else: 
        # 미장(NASDAQ)은 매물대보다 볼린저 상단 추세 돌파를 더 신뢰
        if bb_upper <= today_open + (today_atr * 1.5):
            target_price = us_atr_target
        else:
            target_price = bb_upper
            
        stop_loss = today_open - (today_atr * 2.0)
        
    price_targets = {'TP': int(target_price), 'SL': int(stop_loss)}
    
    return signal, round(score, 1), reasons, df, price_targets