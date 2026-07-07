#업데이트날짜: 2026.07.02
#작성자: j-neat
#시각화 모듈 (거래량 + 펀더멘털 상세 텍스트 + 이모지 깨짐 방지 버전)

import matplotlib.pyplot as plt
import matplotlib
import numpy as np
import os
import re

plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False

def plot_stock_chart(df, ticker, score, reasons, fundamentals=None):
    if not os.path.exists("charts"):
        os.makedirs("charts")
        
    print(f"  📊 [{ticker}] 차트 및 매물대 정보 시각화 중...")
    
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 10), gridspec_kw={'height_ratios': [3, 1, 1]})
    
    # --- 1. 주가 차트 ---
    ax1.plot(df.index, df['Close'], label='종가', color='black', linewidth=1.5)
    if 'SMA_20' in df.columns:
        ax1.plot(df.index, df['SMA_20'], label='20일선', color='blue', linestyle='--', alpha=0.7)
    
    # 💡 차트 배경에 매물대(Volume Profile) 가로로 그리기
    try:
        ax_vp = ax1.twiny() 
        hist, bins = np.histogram(df['Close'], bins=30, weights=df['Volume'])
        center = (bins[:-1] + bins[1:]) / 2
        ax_vp.barh(center, hist, height=(bins[1]-bins[0])*0.9, color='gray', alpha=0.2, edgecolor='none')
        ax_vp.set_xlim(0, hist.max() * 4) 
        ax_vp.axis('off') 
        
        # 최대 매물대(POC) 가격 계산하여 빨간 점선 표시
        poc_idx = np.argmax(hist)
        poc_price = center[poc_idx]
        ax1.axhline(poc_price, color='red', linestyle=':', alpha=0.5, label='최대 매물대(POC)')
    except:
        poc_price = df['Close'].mean()
    
    ax1.set_title(f'{ticker} 종합 퀀트 점수: {score}/100', fontsize=16, fontweight='bold')
    ax1.legend(loc='upper left')
    ax1.grid(True, linestyle='--', alpha=0.5)
    ax1.set_ylabel('주가 (Price)')
    
    # --- 2. 거래량 차트 ---
    colors = np.where(df['Close'] >= df['Open'], 'red', 'blue')
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
    
    # --- 4. 상세 텍스트 ---
    last_close = df['Close'].iloc[-1]
    last_sma = df['SMA_20'].iloc[-1]
    last_rsi = df['RSI'].iloc[-1]
    
    if 'OBV' in df.columns and 'OBV_SMA_20' in df.columns:
        obv_status = "상승(매집)" if df['OBV'].iloc[-1] > df['OBV_SMA_20'].iloc[-1] else "하락(이탈)"
    else:
        obv_status = "정보 없음"
    
    fund_text = ""
    if fundamentals:
        per = fundamentals.get('PER', 0)
        pbr = fundamentals.get('PBR', 0)
        roe = (fundamentals.get('ROE') or 0) * 100
        debt = fundamentals.get('Debt_Ratio') or 0
        fund_text = f" | PER: {per:.1f}배 | PBR: {pbr:.1f}배 | ROE: {roe:.1f}% | 부채비율: {debt:.1f}%"
    
    # 💡 [핵심] 폰트 깨짐을 유발하는 주요 이모지들을 정규식으로 제거
    clean_reasons = [re.sub(r'[🌟⚠️🔥🚫✅❌🎯🛑🎉🚨]', '', r).strip() for r in reasons]
    
    detail_text = (
        f"[현재 지표 요약]\n"
        f"• 가격/추세: 현재가 {last_close:,.0f}원 | 20일선 {last_sma:,.0f}원 | RSI {last_rsi:.1f}\n"
        f"• 거래량/매물: 최대 매물대 {poc_price:,.0f}원 | OBV 추세: {obv_status}\n"
        f"• 재무 지표: {fund_text.strip(' |') if fund_text else '재무 정보 없음'}\n"
        f"• 추천 사유: {', '.join(clean_reasons)}" # 원본 reasons 대신 clean_reasons 사용
    )
    
    fig.text(0.5, 0.02, detail_text, ha='center', fontsize=11, 
             bbox=dict(facecolor='#F5F5F5', edgecolor='#CCCCCC', alpha=0.9, boxstyle='round,pad=0.8'))
    
    plt.subplots_adjust(bottom=0.18)
    plt.savefig(f"charts/{ticker}_chart.png", dpi=120, bbox_inches='tight')
    plt.close()