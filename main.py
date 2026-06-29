# 업데이트날짜: 2026.06.28
# 작성자: j-neat
# 메인모듈 (KOSDAQ 100 + 레버리지/인버스 ETF 추가 버전)

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

# 💡 [핵심 추가] 코스피 100종목을 가져오는 함수 추가
def get_kospi_top_100():
    print("🌐 한국 KOSPI 시가총액 100 종목을 가져오는 중...")
    df = fdr.StockListing('KOSPI')
    top_100 = df.head(100)
    # 코스피는 야후 파이낸스 티커 식별을 위해 .KS를 붙여줍니다.
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

if __name__ == "__main__":
    print("=== 🚀 멀티팩터 퀀트 스크리닝 & 슬랙 알림 시작 ===\n")
    
    clean_charts_folder()
    clear_slack_channel(SLACK_TOKEN, SLACK_CHANNEL)

    us_stocks = get_nasdaq_100()
    kr_kospi_stocks = get_kospi_top_100() # 코스피 데이터 로드
    kr_kosdaq_stocks = get_kosdaq_top_100()
    
    # 💡 [수정] 스크리닝 루프에 KOSPI 100 그룹을 추가
    screening_groups = [
        ("🇺🇸 (NASDAQ 100)", us_stocks), 
        ("🇰🇷 (KOSPI 100)", kr_kospi_stocks), 
        ("🇰🇷 (KOSDAQ 100+ETF)", kr_kosdaq_stocks)
    ]
    
    for flag, stock_dict in screening_groups:
        print(f"\n======================================")
        print(f"▶️ {flag} 분석 중...")
        print(f"======================================")
        
        # 💡 [수정] market_type을 문자열(flag)에 맞게 3가지로 분기
        if "NASDAQ" in flag:
            market_type = 'NASDAQ'
        elif "KOSPI" in flag:
            market_type = 'KOSPI'
        else:
            market_type = 'KOSDAQ'
        
        for ticker, name in stock_dict.items():
            try:
                raw_data = get_stock_data(ticker, period='6mo')
                if raw_data is None or len(raw_data) < 20: 
                    continue

                fundamentals = get_fundamental_data(ticker)
                supply_info = get_supply_data(ticker, market_type)
                
                # 💡 [수정] processed_data 변수를 추가로 받아옵니다.
                signal, score, reasons, processed_data = apply_multi_factor_strategy(
                    raw_data, fundamentals, market_type=market_type, supply_info=supply_info, stock_name=name
                )
                
                clean_ticker = ticker.replace('.KS', '').replace('.KQ', '')
                display_name = f"{name}({clean_ticker})".replace('/', '-')
                
                if signal == 'BUY':
                    current_price = raw_data['Close'].iloc[-1]
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    print(f"  ✅ [추천] {display_name} (점수: {score}/100)")
                    
                    # 💡 [수정] raw_data 대신 지표가 포함된 processed_data를 넘겨줍니다.
                    plot_stock_chart(processed_data, display_name, score, reasons, fundamentals)
                    
                    slack_message = (
                        f"🚨 *[매수 추천 봇]*\n"
                        f"⏰ *시간:* `{now}`\n\n"
                        f"📌 *종목:* {display_name}\n"
                        f"💰 *현재가:* `{current_price:,.2f}`\n"
                        f"📊 *스코어:* `{score} / 100 점`\n"
                        f"💡 *사유:* {', '.join(reasons)}"
                    )
                    
                    chart_file_path = f"charts/{display_name}_chart.png"
                    send_quant_signal(SLACK_TOKEN, SLACK_CHANNEL, slack_message, chart_file_path)
                else:
                    if score > 0:
                        print(f"  ⏳ [관망] {display_name} (점수: {score}/100)")
                        
            except Exception as e:
                print(f"  ⚠️ [{ticker}] 처리 중 에러 발생: {e}")
                
    print("\n🎯 스크리닝 완료! 🎯")