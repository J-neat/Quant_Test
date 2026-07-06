# 업데이트날짜: 2026.07.06
# 작성자: j-neat
# 메인모듈 (기존 보유 종목 A/S 추적 리포트 통합 버전)

import os
import shutil
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
import FinanceDataReader as fdr

from data_collector import get_stock_data, get_fundamental_data, get_supply_data
from strategy import apply_multi_factor_strategy
from visualizer import plot_stock_chart
from slack_notifier import send_quant_signal, clear_slack_channel  
from db_manager import save_signal_to_db, get_recent_buy_signals 

load_dotenv()  

SLACK_TOKEN = os.getenv("SLACK_TOKEN")
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL")

if not SLACK_TOKEN or not SLACK_CHANNEL:
    print("🚨 오류: .env 파일에서 슬랙 토큰이나 채널 ID를 찾을 수 없습니다!")
    exit()

def clean_charts_folder():
    print("🧹 기존 차트 파일들을 깨끗하게 청소하는 중...")
    folder_path = "charts"
    if os.path.exists(folder_path):
        shutil.rmtree(folder_path)
    os.makedirs(folder_path)

def get_nasdaq_100():
    print("🌐 미국 NASDAQ 100 종목명과 티커를 가져오는 중...")
    url = 'https://en.wikipedia.org/wiki/Nasdaq-100'
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers)
        tables = pd.read_html(response.text)
        for table in tables:
            ticker_col = 'Ticker' if 'Ticker' in table.columns else 'Symbol' if 'Symbol' in table.columns else None
            if ticker_col and 'Company' in table.columns:
                return dict(zip(table[ticker_col], table['Company']))
    except Exception as e:
        print(f"  ❌ 나스닥 데이터 수집 에러: {e}")
    return {'AAPL': 'Apple Inc.', 'MSFT': 'Microsoft Corp.'}

def get_kospi_top_100():
    print("🌐 한국 KOSPI 시가총액 100 종목을 가져오는 중...")
    df = fdr.StockListing('KOSPI')
    top_100 = df.head(100)
    kospi_dict = {f"{row['Code']}.KS": row['Name'] for _, row in top_100.iterrows()}
    return kospi_dict

def get_kosdaq_top_100():
    print("🌐 한국 KOSDAQ 시가총액 100 및 주요 ETF를 가져오는 중...")
    df = fdr.StockListing('KOSDAQ')
    top_100 = df.head(100)
    kosdaq_dict = {f"{row['Code']}.KQ": row['Name'] for _, row in top_100.iterrows()}
    
    etfs = {
        "233740.KS": "KODEX 코스닥150레버리지",
        "251340.KS": "KODEX 코스닥150선물인버스",
        "252710.KS": "TIGER 코스닥150선물인버스"
    }
    kosdaq_dict.update(etfs)
    return kosdaq_dict

def check_market_regime(index_ticker):
    try:
        index_df = get_stock_data(index_ticker, period='1y')
        index_df['SMA_200'] = index_df['Close'].rolling(window=200).mean()
        last_close = index_df['Close'].iloc[-1]
        last_sma_200 = index_df['SMA_200'].iloc[-1]
        return last_close > last_sma_200
    except:
        return True

def send_term_dictionary(token, channel_id):
    dictionary_msg = (
        "📚 *[퀀트 시그널 용어 사전]* 📚\n\n"
        "• *RSI (상대강도지수):* 주가의 과열/침체를 나타냅니다. 30 이하면 과매도(바닥권), 70 이상이면 과매수(고점권)로 해석합니다.\n"
        "• *OBV:* 거래량 누적 지표입니다. 주가가 하락하는데 OBV가 버틴다면 '스마트 머니'의 매집을 의심할 수 있습니다.\n"
        "• *POC (Point of Control):* 최근 6개월간 가장 많은 거래가 이루어진 '최대 매물대' 가격입니다. 강력한 지지선/저항선 역할을 합니다.\n"
        "• *PER / PBR:* 기업의 수익성과 자산 대비 현재 주가의 고평가/저평가를 나타내는 기본적 분석 지표입니다.\n"
        "------------------------------------------------------------"
    )
    send_quant_signal(token, channel_id, dictionary_msg)

# 💡 [핵심] 기존 추천 종목 A/S 리포트 생성 함수
def send_position_tracking_report(token, channel_id):
    print("🔍 과거 추천 종목 A/S 리포트 생성 중...")
    recent_signals = get_recent_buy_signals() 
    if not recent_signals:
        send_quant_signal(token, channel_id, "🔍 *[기존 추천 종목 A/S 리포트]*\n최근 3일 내 추천된 종목이 없습니다.\n------------------------------------------------------------")
        return
    tracking_msg = "🔍 *[기존 추천 종목 A/S 리포트]*\n\n"
    
    for signal_data in recent_signals:
        ticker = signal_data['ticker']
        stock_name = signal_data['stock_name']
        orig_price = signal_data['price'] # 과거 DB에 저장했던 매수가
        market_type = signal_data['market_type']
        
        clean_ticker = ticker.replace('.KS', '').replace('.KQ', '')
        display_name = f"{stock_name}({clean_ticker})"
        
        try:
            df = get_stock_data(ticker, period='6mo')
            if df is None or len(df) < 20: continue
            
            fundamentals = get_fundamental_data(ticker)
            supply_info = get_supply_data(ticker, market_type)
            
            index_ticker = '^KS11' if market_type in ['KOSPI', 'KOSDAQ'] else 'QQQ'
            is_bull = check_market_regime(index_ticker)

            signal, current_score, _, _, targets = apply_multi_factor_strategy(
                df, fundamentals, market_type, supply_info, ticker, is_bull
            )
            
            current_price = df['Close'].iloc[-1]
            sl_price = targets['SL']
            
            # 💡 [추가] 과거 추천가 대비 현재 수익률 계산
            return_pct = ((current_price - orig_price) / orig_price) * 100
            
            if current_price <= sl_price:
                tracking_msg += f"🚨 `{display_name}` : *손절가 이탈* (현재 수익률 {return_pct:.1f}%) - 즉시 매도 권고!\n"
            elif signal == 'BUY':
                tracking_msg += f"✅ `{display_name}` : 상승 추세 유지 (현재 {current_score}점 / 수익률 {return_pct:.1f}%) - HOLD\n"
            else:
                tracking_msg += f"⚠️ `{display_name}` : 상승 모멘텀 둔화 (현재 {current_score}점 / 수익률 {return_pct:.1f}%) - 매도 준비\n"
                
        except Exception as e:
            tracking_msg += f"❓ `{display_name}` : 상태 확인 불가\n"
            
    tracking_msg += "\n------------------------------------------------------------\n👇 *오늘의 신규 추천 종목 시그널이 곧 도착합니다.* 👇"
    send_quant_signal(token, channel_id, tracking_msg)


if __name__ == "__main__":
    print("=== 🚀 멀티팩터 퀀트 스크리닝 & 슬랙 알림 시작 ===\n")
    
    clean_charts_folder()
    clear_slack_channel(SLACK_TOKEN, SLACK_CHANNEL)

    # 💡 1. 용어 설명 먼저 쏘기
    send_term_dictionary(SLACK_TOKEN, SLACK_CHANNEL)
    
    # 💡 2. 용어 설명 바로 다음 메시지로 기존 종목 A/S 리포트 쏘기
    send_position_tracking_report(SLACK_TOKEN, SLACK_CHANNEL)

    # 💡 3. 오늘의 신규 종목 스크리닝 시작
    us_stocks = get_nasdaq_100()
    kr_kospi_stocks = get_kospi_top_100() 
    kr_kosdaq_stocks = get_kosdaq_top_100()
    
    screening_groups = [
        ("🇺🇸 (NASDAQ 100)", us_stocks, 'QQQ', 'NASDAQ'), 
        ("🇰🇷 (KOSPI 100)", kr_kospi_stocks, '^KS11', 'KOSPI'), 
        ("🇰🇷 (KOSDAQ 100+ETF)", kr_kosdaq_stocks, '^KS11', 'KOSDAQ') 
    ]
    
    for flag, stock_dict, index_ticker, market_type in screening_groups:
        print(f"\n======================================")
        print(f"▶️ {flag} 분석 중...")
        
        is_bull_market = check_market_regime(index_ticker)
        if not is_bull_market:
            print(f"⚠️ [마켓 경고] {index_ticker} 지수가 200일선 아래에 있습니다. (보수적 접근 필요)")
            
        print(f"======================================")
        
        for ticker, name in stock_dict.items():
            try:
                raw_data = get_stock_data(ticker, period='6mo')
                if raw_data is None or len(raw_data) < 20: continue

                fundamentals = get_fundamental_data(ticker)
                supply_info = get_supply_data(ticker, market_type)
                
                signal, score, reasons, processed_data, price_targets = apply_multi_factor_strategy(
                    raw_data, fundamentals, market_type=market_type, 
                    supply_info=supply_info, stock_name=name, is_bull_market=is_bull_market
                )
                
                clean_ticker = ticker.replace('.KS', '').replace('.KQ', '')
                display_name = f"{name}({clean_ticker})".replace('/', '-')
                
                if signal == 'BUY':
                    current_price = raw_data['Close'].iloc[-1]
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    print(f"  ✅ [추천] {display_name} (점수: {score}/100)")
                    
                    plot_stock_chart(processed_data, display_name, score, reasons, fundamentals)
                    
                    tp_price = price_targets['TP']
                    sl_price = price_targets['SL']

                    slack_message = (
                        f"🚨 *[신규 매수 추천 봇]*\n"
                        f"⏰ *시간:* `{now}`\n\n"
                        f"📌 *종목:* {display_name}\n"
                        f"💰 *현재가:* `{current_price:,.2f}`\n"
                        f"🎯 *목표 익절가:* `{tp_price:,.0f}원`\n"
                        f"🛑 *절대 손절가:* `{sl_price:,.0f}원`\n"
                        f"📊 *스코어:* `{score} / 100 점`\n"
                        f"💡 *사유:* {', '.join(reasons)}"
                    )
                    
                    chart_file_path = f"charts/{display_name}_chart.png"
                    send_quant_signal(SLACK_TOKEN, SLACK_CHANNEL, slack_message, chart_file_path)
                    
                    try:
                        save_signal_to_db(
                            ticker=ticker, 
                            stock_name=name, 
                            price=current_price, 
                            score=score, 
                            reasons_list=reasons,
                            market_type=market_type
                        )
                        print(f"      🗄️ 클라우드 DB 적재 성공: {display_name}")
                    except Exception as db_err:
                        print(f"      ❌ 클라우드 DB 적재 실패 로그: {db_err}")

                else:
                    if score > 0:
                        print(f"  ⏳ [관망] {display_name} (점수: {score}/100)")
                    elif "데이터 부족" in reasons:
                        print(f"  ⚠️ [데이터 부족 패스] {display_name}")
            except Exception as e:
                print(f"  ⚠️ [{ticker}] 처리 중 에러 발생: {e}")
                
    print("\n🎯 스크리닝 및 알림 전송 완료! 🎯")