# 업데이트날짜: 2026.07.07
# 작성자: j-neat
# 메인모듈 (다트 공시 데이터 추가 로직)

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
from dart_manager import collect_and_save_disclosures # 💡 DART 매니저 추가

load_dotenv()  

SLACK_TOKEN = os.getenv("SLACK_TOKEN")
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL")

if not SLACK_TOKEN or not SLACK_CHANNEL:
    print("🚨 오류: 슬랙 토큰이나 채널 ID 없음!")
    exit()

def clean_charts_folder():
    folder_path = "charts"
    if os.path.exists(folder_path):
        shutil.rmtree(folder_path)
    os.makedirs(folder_path)

def get_nasdaq_100():
    url = 'https://en.wikipedia.org/wiki/Nasdaq-100'
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers)
        tables = pd.read_html(response.text)
        for table in tables:
            ticker_col = 'Ticker' if 'Ticker' in table.columns else 'Symbol' if 'Symbol' in table.columns else None
            if ticker_col and 'Company' in table.columns:
                return dict(zip(table[ticker_col], table['Company']))
    except:
        pass
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

def check_market_regime(index_ticker):
    try:
        index_df = get_stock_data(index_ticker, period='1y')
        index_df['SMA_200'] = index_df['Close'].rolling(window=200).mean()
        return index_df['Close'].iloc[-1] > index_df['SMA_200'].iloc[-1]
    except:
        return True

def send_term_dictionary(token, channel_id):
    msg = "📚 *[퀀트 시그널 용어 사전]* 📚\n• RSI / OBV / POC 등 지표 안내\n------------------------------------------------------------"
    send_quant_signal(token, channel_id, msg)

def send_position_tracking_report(token, channel_id):
    recent_signals = get_recent_buy_signals()
    if not recent_signals:
        send_quant_signal(token, channel_id, "🔍 *[기존 추천 종목 A/S 리포트]*\n데이터 없음.\n------------------------------------------------------------")
        return

    tracking_msg = "🔍 *[기존 추천 종목 A/S 리포트]*\n\n"
    for signal_data in recent_signals:
        ticker = signal_data['ticker']
        stock_name = signal_data['stock_name']
        orig_price = signal_data['price']
        market_type = signal_data['market_type']
        display_name = f"{stock_name}({ticker.replace('.KS', '').replace('.KQ', '')})"
        
        try:
            df = get_stock_data(ticker, period='6mo')
            if df is None or len(df) < 20: continue
            fundamentals = get_fundamental_data(ticker)
            supply_info = get_supply_data(ticker, market_type)
            is_bull = check_market_regime('^KS11' if market_type in ['KOSPI', 'KOSDAQ'] else 'QQQ')

            # ticker 인자 추가 전달
            signal, current_score, _, _, targets = apply_multi_factor_strategy(
                df, fundamentals, market_type, supply_info, ticker, is_bull, ticker
            )
            
            current_price = df['Close'].iloc[-1]
            return_pct = ((current_price - orig_price) / orig_price) * 100
            
            if current_price <= targets['SL']:
                tracking_msg += f"🚨 `{display_name}` : *손절가 이탈* ({return_pct:.1f}%)\n"
            elif signal == 'BUY':
                tracking_msg += f"✅ `{display_name}` : HOLD ({current_score}점 / {return_pct:.1f}%)\n"
            else:
                tracking_msg += f"⚠️ `{display_name}` : 매도 준비 ({current_score}점 / {return_pct:.1f}%)\n"
        except:
            pass
            
    tracking_msg += "\n------------------------------------------------------------\n👇 *오늘의 신규 시그널* 👇"
    send_quant_signal(token, channel_id, tracking_msg)

if __name__ == "__main__":
    print("=== 🚀 멀티팩터 퀀트 스크리닝 시작 ===")
    clean_charts_folder()
    clear_slack_channel(SLACK_TOKEN, SLACK_CHANNEL)
    send_term_dictionary(SLACK_TOKEN, SLACK_CHANNEL)
    send_position_tracking_report(SLACK_TOKEN, SLACK_CHANNEL)

    us_stocks = get_nasdaq_100()
    kr_kospi_stocks = get_kospi_top_100() 
    kr_kosdaq_stocks = get_kosdaq_top_100()
    
    groups = [
        ("🇺🇸 (NASDAQ 100)", us_stocks, 'QQQ', 'NASDAQ'), 
        ("🇰🇷 (KOSPI 100)", kr_kospi_stocks, '^KS11', 'KOSPI'), 
        ("🇰🇷 (KOSDAQ 100+ETF)", kr_kosdaq_stocks, '^KS11', 'KOSDAQ') 
    ]
    
    for flag, stock_dict, index_ticker, market_type in groups:
        print(f"\n▶️ {flag} 분석 중...")
        is_bull_market = check_market_regime(index_ticker)
        
        for ticker, name in stock_dict.items():
            try:
                # 💡 [핵심] 한국 종목이면 차트 분석 전에 DART 공시부터 수집해서 DB에 갱신
                if market_type in ['KOSPI', 'KOSDAQ']:
                    collect_and_save_disclosures(ticker, name)

                raw_data = get_stock_data(ticker, period='6mo')
                if raw_data is None or len(raw_data) < 20: continue

                fundamentals = get_fundamental_data(ticker)
                supply_info = get_supply_data(ticker, market_type)
                
                # ticker 인자 추가 전달
                signal, score, reasons, processed_data, price_targets = apply_multi_factor_strategy(
                    raw_data, fundamentals, market_type, supply_info, name, is_bull_market, ticker
                )
                
                display_name = f"{name}({ticker.replace('.KS', '').replace('.KQ', '')})"
                
                if signal == 'BUY':
                    current_price = raw_data['Close'].iloc[-1]
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    plot_stock_chart(processed_data, display_name, score, reasons, fundamentals)
                    
                    msg = (f"🚨 *[매수 추천 봇]*\n⏰ `{now}`\n📌 {display_name}\n💰 `{current_price:,.0f}`\n"
                           f"🎯 익절: `{price_targets['TP']:,.0f}`\n🛑 손절: `{price_targets['SL']:,.0f}`\n"
                           f"📊 스코어: `{score}점`\n💡 사유: {', '.join(reasons)}")
                    
                    send_quant_signal(SLACK_TOKEN, SLACK_CHANNEL, msg, f"charts/{display_name}_chart.png")
                    save_signal_to_db(ticker, name, current_price, score, reasons, market_type)
                    print(f"  ✅ [추천] {display_name} ({score}점)")
            except Exception as e:
                pass