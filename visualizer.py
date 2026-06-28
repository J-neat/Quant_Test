#업데이트날짜: 2026.06.28
#작성자: j-neat
#시각화 모듈 (거래량 + 펀더멘털 상세 텍스트 추가 버전)

import matplotlib.pyplot as plt
import os
import matplotlib

# 한글 폰트 설정 (윈도우 환경)
plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False

# 💡 매개변수에 fundamentals=None 추가
def plot_stock_chart(df, ticker, score, reasons, fundamentals=None):
    if not os.path.exists("charts"):
        os.makedirs("charts")
        
    print(f"  📊 [{ticker}] 차트 및 재무 정보 시각화 중...")
    
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 10), gridspec_kw={'height_ratios': [3, 1, 1]})
    
    # --- 1. 주가 차트 ---
    ax1.plot(df.index, df['Close'], label='종가', color='black', linewidth=1.5)
    if 'SMA_20' in df.columns:
        ax1.plot(df.index, df['SMA_20'], label='20일 이동평균선', color='blue', linestyle='--', alpha=0.7)
    
    ax1.set_title(f'{ticker} 종합 퀀트 점수: {score}/100', fontsize=16, fontweight='bold')
    ax1.legend(loc='upper left')
    ax1.grid(True, linestyle='--', alpha=0.5)
    ax1.set_ylabel('주가 (Price)')
    
    # --- 2. 거래량 차트 ---
    colors = ['red' if df['Close'].iloc[i] >= df['Open'].iloc[i] else 'blue' for i in range(len(df))]
    ax2.bar(df.index, df['Volume'], color=colors, alpha=0.5, label='거래량')
    
    if 'Volume_SMA_20' in df.columns:
        ax2.plot(df.index, df['Volume_SMA_20'], color='orange', linestyle='-', label='20일 평균 거래량')
        
    ax2.legend(loc='upper left')
    ax2.grid(True, linestyle='--', alpha=0.5)
    ax2.set_ylabel('거래량 (Volume)')
    
    # --- 3. RSI 차트 ---
    if 'RSI' in df.columns:
        ax3.plot(df.index, df['RSI'], color='purple', label='RSI (투자심리)')
        ax3.axhline(70, color='red', linestyle='--', alpha=0.5) 
        ax3.axhline(30, color='green', linestyle='--', alpha=0.5) 
        
        ax3.fill_between(df.index, y1=70, y2=100, color='red', alpha=0.1)
        ax3.fill_between(df.index, y1=0, y2=30, color='green', alpha=0.1)
        
    ax3.set_ylim(0, 100)
    ax3.legend(loc='upper left')
    ax3.grid(True, linestyle='--', alpha=0.5)
    ax3.set_ylabel('RSI 지수')
    
    # --- 4. 상세 설명 텍스트 박스 ---
    last_close = df['Close'].iloc[-1]
    last_sma = df['SMA_20'].iloc[-1]
    last_rsi = df['RSI'].iloc[-1]
    
    # 💡 펀더멘털 텍스트 만들기
    fund_text = ""
    if fundamentals:
        per = fundamentals.get('PER', 0)
        pbr = fundamentals.get('PBR', 0)
        roe = fundamentals.get('ROE', 0) * 100
        debt = fundamentals.get('Debt_Ratio', 0)
        fund_text = f" | PER: {per:.1f}배 | PBR: {pbr:.1f}배 | ROE: {roe:.1f}% | 부채비율: {debt:.1f}%"
    
    # 기존 detail_text 부분을 아래 코드로 교체 (💡 이모지 삭제)
    detail_text = (
        f"[현재 지표 요약]\n"
        f"• 기술적 지표: 현재가 {last_close:,.0f}원 | 20일선 {last_sma:,.0f}원 | RSI {last_rsi:.1f}\n"
        f"• 재무 지표: {fund_text.strip(' |') if fund_text else '재무 정보 없음'}\n"
        f"• 추천 사유: {', '.join(reasons)}"
    )
    
    fig.text(0.5, 0.02, detail_text, ha='center', fontsize=12, 
             bbox=dict(facecolor='#F5F5F5', edgecolor='#CCCCCC', alpha=0.9, boxstyle='round,pad=0.8'))
    
    plt.tight_layout(rect=[0, 0.1, 1, 1]) # 텍스트 박스가 3줄로 늘어나서 여백(0.1)을 조금 더 확보함
    
    plt.savefig(f"charts/{ticker}_chart.png", dpi=120)
    plt.close()