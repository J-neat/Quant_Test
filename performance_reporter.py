# 업데이트날짜: 2026.07.07
# 작성자: j-neat
# 실전 봇 성과 평가 모듈 (로컬 SQLite DB 기록 기반 실제 수익률 추적)

import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import yfinance as yf
from dotenv import load_dotenv
from db_manager import get_all_signals

load_dotenv()

# 폰트 깨짐 방지 설정
font_path = "C:/Windows/Fonts/malgun.ttf"
if os.path.exists(font_path):
    font_name = fm.FontProperties(fname=font_path).get_name()
    plt.rcParams['font.family'] = font_name
else:
    plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['axes.unicode_minus'] = False

def generate_real_performance_report():
    print("🗄️ DB에서 봇의 과거 추천 기록을 모두 불러오는 중...")
    
    # DB에서 모든 시그널 기록 가져오기 (오래된 순서대로 정렬)
    signals = get_all_signals()
    
    if not signals:
        print("DB에 저장된 추천 기록이 없습니다.")
        return

    df_signals = pd.DataFrame(signals)
    print(f"✅ 총 {len(df_signals)}건의 실전 매수 시그널을 평가합니다.\n")
    
    # 티커별 최신 주가 한 번에 조회 (속도 최적화)
    tickers = list(df_signals['ticker'].unique())
    print("🌐 야후 파이낸스에서 현재 주가 실시간 갱신 중...")
    
    current_prices = {}
    for ticker in tickers:
        try:
            # 1일 치 최신 데이터만 빠르게 호출
            curr_data = yf.download(ticker, period="1d", progress=False)
            if isinstance(curr_data.columns, pd.MultiIndex):
                curr_data.columns = curr_data.columns.get_level_values(0)
                
            if not curr_data.empty:
                current_prices[ticker] = float(curr_data['Close'].iloc[-1])
        except Exception as e:
            print(f"❌ {ticker} 주가 갱신 실패: {e}")
    
    results = []
    
    # 봇의 매수가 vs 현재가 대결 연산
    for _, row in df_signals.iterrows():
        ticker = row['ticker']
        stock_name = row['stock_name']
        entry_price = float(row['price'])
        created_at = row['created_at'][:10] # YYYY-MM-DD 형태만 추출
        
        if ticker in current_prices:
            curr_price = current_prices[ticker]
            # 💡 [핵심] 실제 수익률 계산
            ret_pct = ((curr_price - entry_price) / entry_price) * 100
            
            results.append({
                '추천일자': created_at,
                '티커': ticker,
                '종목명': stock_name,
                '추천가(진입)': entry_price,
                '현재가': curr_price,
                '실제수익률(%)': round(ret_pct, 2)
            })
    
    res_df = pd.DataFrame(results)
    if res_df.empty:
        print("평가할 수 있는 유효한 데이터가 없습니다.")
        return

    # --- 텍스트 리포트 출력 ---
    print("\n" + "="*60)
    print("🏆 [실전 봇 성과 평가 리포트] 🏆")
    print("="*60)
    print(f"• 누적 추천 횟수: {len(res_df)}회")
    print(f"• 실전 평균 수익률: {res_df['실제수익률(%)'].mean():.2f}%")
    print(f"• 승률 (수익 중인 종목 비율): {(res_df['실제수익률(%)'] > 0).mean()*100:.1f}%")
    print("="*60)
    
    print("\n🔍 [최근 10건 추천 내역 상세]")
    print(res_df.tail(10).to_string(index=False))
    print("\n")

    # --- 그래프 시각화 ---
    res_df_sorted = res_df.sort_values('실제수익률(%)', ascending=False)
    
    plt.figure(figsize=(14, 6))
    
    # 수익은 빨간색, 손실은 파란색으로 직관적 표시
    colors = ['#FF4B4B' if x > 0 else '#4B7BFF' for x in res_df_sorted['실제수익률(%)']]
    
    # 라벨에 종목명과 추천 월/일을 같이 표기 (예: 삼성전자\n07-01)
    labels = res_df_sorted['종목명'] + "\n(" + res_df_sorted['추천일자'].str[5:] + ")"
    
    plt.bar(labels, res_df_sorted['실제수익률(%)'], color=colors)
    plt.xticks(rotation=90, fontsize=8)
    
    title_font = fm.FontProperties(fname=font_path) if os.path.exists(font_path) else None
    plt.title('봇 실전 추천 내역 누적 수익률 평가 (과거 매수가 vs 현재가)', fontproperties=title_font, fontsize=15, fontweight='bold')
    plt.ylabel('수익률 (%)', fontproperties=title_font)
    plt.axhline(0, color='black', linestyle='-', linewidth=1.2)
    plt.grid(axis='y', linestyle='--', alpha=0.3)
    
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    generate_real_performance_report()