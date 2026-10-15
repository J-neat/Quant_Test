# 업데이트날짜: 2026.10.15
# 작성자: j-neat
# 백테스트 모듈
#
# 실행: python backtester.py [ALL|KR|US|DB] [시작일 YYYY-MM-DD]
#   ALL/KR/US : 실전 봇과 같은 유니버스(나스닥100 / 코스피100 / 코스닥100+ETF) 전체를 테스트 (기본값)
#   DB        : 봇이 이미 추천했던 종목만 테스트 (예전 방식 — 결과가 낙관적으로 치우침)
#
# 💡 [수정] 결과가 낙관적으로 치우치던 원인들 정리
#   1. 봇이 이미 추천한 종목만 테스트 → 전체 유니버스로 테스트 (선택 편향 제거)
#   2. 시장 국면을 항상 무시 → 그날 기준 지수 200일선으로 국면 필터 적용 (인버스 ETF 포함)
#   3. 시그널 당일 종가로 매수(그날 종가를 보고 그 가격에 사는 셈) → 다음 날 시가로 매수
#   4. 재무 데이터를 PER 12 / ROE 15% 등 유리한 값으로 고정 → 실제 현재 재무 데이터 사용
#   5. 판단에 쓰는 일봉 길이를 실전과 같은 6개월(LOOKBACK)로 맞춤 (OBV 등이 데이터 시작점에 따라 달라짐)
#   6. 같은 기간 단순 보유(Buy & Hold) 수익률과 비교
# ⚠️ 남은 한계: 유니버스가 '현재' 구성 종목이라 생존 편향이 남아 있고, 재무 데이터도 현재 값(미래 정보)임

import sys
import os
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from datetime import datetime, timedelta
from dotenv import load_dotenv
from db_manager import get_all_signals
from strategy import apply_multi_factor_strategy
from data_collector import (get_fundamental_data, get_nasdaq_100, get_kospi_top_100,
                            get_kosdaq_top_100, INDEX_BY_MARKET)

load_dotenv()

LOOKBACK = 125              # 실전(main.py)은 6개월(약 125거래일) 일봉으로 판단
FEE = 0.002                 # 매수·매도 각각 적용
INITIAL_CAPITAL = 1_000_000
CHART_DIR = "backtest_charts"

# 1. 폰트 깨짐 방지 설정
font_path = "C:/Windows/Fonts/malgun.ttf"
if os.path.exists(font_path):
    font_name = fm.FontProperties(fname=font_path).get_name()
    plt.rcParams['font.family'] = font_name
else:
    plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['axes.unicode_minus'] = False

# 2. 테스트 유니버스 {티커: (종목명, 시장)}
def get_tickers_from_db():
    """봇이 추천했던 종목 (예전 방식, 비교용)"""
    print("🗄️ DB에서 추천 종목 유니버스를 가져오는 중...")
    try:
        # 중복 제거 (종목명은 ETF 판별에 필요)
        tickers = {item['ticker']: (item.get('stock_name') or item['ticker'], item.get('market_type') or guess_market(item['ticker']))
                   for item in get_all_signals()}
        print(f"✅ 총 {len(tickers)}개의 고유 추천 종목을 DB에서 확보했습니다!\n")
        return tickers
    except Exception as e:
        print(f"🚨 DB 조회 실패: {e}")
        return {}

def guess_market(ticker):
    if ticker.endswith('.KS'): return 'KOSPI'
    if ticker.endswith('.KQ'): return 'KOSDAQ'
    return 'NASDAQ'

def get_universe(source):
    """실전 봇과 같은 유니버스. 코스닥 그룹의 인버스/레버리지 ETF는 .KS 티커지만 KOSDAQ 시장으로 취급"""
    if source == 'DB':
        return get_tickers_from_db()
    loaders = {'NASDAQ': get_nasdaq_100, 'KOSPI': get_kospi_top_100, 'KOSDAQ': get_kosdaq_top_100}
    markets = {'KR': ['KOSPI', 'KOSDAQ'], 'US': ['NASDAQ']}.get(source, ['NASDAQ', 'KOSPI', 'KOSDAQ'])
    universe = {}
    for market in markets:
        try:
            for ticker, name in loaders[market]().items():
                universe.setdefault(ticker, (name, market))
        except Exception as e:
            print(f"⚠️ {market} 종목 목록 수집 실패: {e}")
    print(f"✅ 테스트 유니버스: {len(universe)}개 종목 ({', '.join(markets)})\n")
    return universe

def download(ticker, start, end):
    df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

def get_regime_series(index_ticker, start_date, end_date):
    """날짜별 시장 국면 (True=상승장: 지수가 200일선 위). 실전 check_market_regime과 같은 기준, 데이터 부족 시 상승장"""
    try:
        data_start = (pd.Timestamp(start_date) - timedelta(days=400)).strftime("%Y-%m-%d")
        idx = download(index_ticker, data_start, end_date)
        sma_200 = idx['Close'].rolling(window=200).mean()
        return (idx['Close'] > sma_200) | sma_200.isna()
    except Exception as e:
        print(f"⚠️ 시장 국면 데이터 실패({index_ticker}): {e} → 국면 필터 생략")
        return None

# 3. 종목 1개 시뮬레이션
def backtest_one(df, stock_name, market_type, fundamentals, regime, start_date):
    """시그널 다음 날 시가 매수, 손절/익절은 실제 체결 가능 가격으로 청산. 결과 dict 반환"""
    first = max(LOOKBACK - 1, int(df.index.searchsorted(pd.Timestamp(start_date))))
    if first >= len(df) - 1:
        return None

    # 그날의 시장 국면 (지수와 거래일이 다르면 직전 값 사용, 없으면 None=필터 생략)
    if regime is not None:
        bull_by_day = regime.reindex(df.index, method='ffill')
    else:
        bull_by_day = pd.Series([None] * len(df), index=df.index, dtype=object)

    capital = INITIAL_CAPITAL
    position = 0
    entry_price = 0.0
    tp_price = sl_price = 0.0
    pending = None          # 어제 시그널의 (TP, SL) → 오늘 시가에 매수
    trades = []             # 청산된 거래별 수익률(%)
    gap_skips = 0

    for i in range(first, len(df)):
        today = df.iloc[i]

        if pending is not None:
            tp, sl = pending
            pending = None
            # 시가가 이미 손절가 이하 / 익절가 이상으로 갭이 뜨면 진입하지 않음
            if sl < today['Open'] < tp:
                entry_price = float(today['Open'])
                position = int(capital // (entry_price * (1 + FEE)))
                if position > 0:
                    capital -= position * entry_price * (1 + FEE)
                    tp_price, sl_price = tp, sl
            else:
                gap_skips += 1

        if position > 0:
            # 손절/익절을 종가가 아닌 실제 체결 가능한 가격으로 청산 (갭이면 시가)
            # 하루에 둘 다 터치하면 보수적으로 손절 먼저 처리
            exit_price = None
            if today['Open'] <= sl_price:
                exit_price = today['Open']
            elif today['Low'] <= sl_price:
                exit_price = sl_price
            elif today['Open'] >= tp_price:
                exit_price = today['Open']
            elif today['High'] >= tp_price:
                exit_price = tp_price
            if exit_price is not None:
                capital += position * exit_price * (1 - FEE)
                trades.append(((exit_price * (1 - FEE)) / (entry_price * (1 + FEE)) - 1) * 100)
                position = 0
            continue

        if i == len(df) - 1:
            break  # 마지막 날 시그널은 다음 날 매수가 불가능

        # ticker 인자는 일부러 비워둠 → 오늘자 30분 법칙/현재 DB 공시가 과거 날짜에 섞이는 것(미래 정보 누수) 방지
        window = df.iloc[i - LOOKBACK + 1:i + 1]
        is_bull = bull_by_day.iloc[i]
        is_bull = None if pd.isna(is_bull) else bool(is_bull)
        signal, _, _, _, targets = apply_multi_factor_strategy(
            window, fundamentals, market_type, {}, stock_name, is_bull, ""
        )
        if signal == 'BUY' and targets:
            pending = (targets['TP'], targets['SL'])

    last_close = float(df['Close'].iloc[-1])
    open_trade = position > 0
    if open_trade:
        trades.append(((last_close * (1 - FEE)) / (entry_price * (1 + FEE)) - 1) * 100)
    final_value = capital + position * last_close
    return {
        'Return': (final_value / INITIAL_CAPITAL - 1) * 100,
        'BuyHold': (last_close / float(df['Close'].iloc[first]) - 1) * 100,
        'Trades': len(trades),
        'TradeReturns': trades,
        'OpenAtEnd': open_trade,
        'GapSkips': gap_skips,
    }

# 4. 백테스트 메인 엔진
def run_portfolio_backtest(ticker_list, start_date, end_date, label="전체 유니버스"):
    if not ticker_list:
        print("백테스트를 진행할 종목이 없습니다.")
        return None

    # 리스트/{티커: 종목명}으로 넘겨도 동작하도록 {티커: (종목명, 시장)} 형태로 통일
    if not isinstance(ticker_list, dict):
        ticker_list = {t: t for t in ticker_list}
    ticker_list = {t: v if isinstance(v, tuple) else (v, guess_market(t)) for t, v in ticker_list.items()}

    print(f"🚀 [{label}] 백테스트 시작! ({start_date} ~ {end_date}, {len(ticker_list)}종목)")
    # 첫 테스트일부터 6개월치 일봉이 확보되도록 데이터를 앞당겨 받음
    data_start = (pd.Timestamp(start_date) - timedelta(days=LOOKBACK * 2)).strftime("%Y-%m-%d")

    regimes = {}
    all_results = []
    for n, (ticker, (stock_name, market_type)) in enumerate(ticker_list.items(), 1):
        try:
            if market_type not in regimes:
                index_ticker = INDEX_BY_MARKET.get(market_type, 'QQQ')
                regimes[market_type] = get_regime_series(index_ticker, start_date, end_date)

            df = download(ticker, data_start, end_date)
            if df.empty or len(df) < LOOKBACK + 20:
                print(f"⏭️ [{n}/{len(ticker_list)}] {ticker}: 데이터 부족")
                continue

            fundamentals = get_fundamental_data(ticker)
            result = backtest_one(df, stock_name, market_type, fundamentals, regimes[market_type], start_date)
            if result is None:
                continue
            result.update({'Ticker': ticker, 'Name': stock_name, 'Market': market_type})
            all_results.append(result)
            print(f"✅ [{n}/{len(ticker_list)}] {ticker}: 전략 {result['Return']:.2f}% / 보유 {result['BuyHold']:.2f}% ({result['Trades']}회 거래)")

        except Exception as e:
            print(f"❌ {ticker} 에러: {type(e).__name__}: {e}")
            continue

    if not all_results:
        print("백테스트 결과 데이터가 없습니다.")
        return None

    # 5. 결과 정제 및 리포트
    res = pd.DataFrame(all_results)
    res = res.replace([np.inf, -np.inf], np.nan).dropna(subset=['Return', 'BuyHold'])
    res.sort_values('Return', ascending=False, inplace=True)
    print_report(res, label)
    save_chart(res, label)
    return res

def print_report(res, label):
    traded = res[res['Trades'] > 0]
    trade_returns = [r for rs in res['TradeReturns'] for r in rs]

    print("\n" + "=" * 55)
    print(f"📊 [{label}] 백테스트 최종 리포트")
    print("=" * 55)
    print(f"• 테스트 종목 수: {len(res)}개 (거래 발생 {len(traded)}개)")
    print(f"• 전략 평균 수익률 (전 종목 동일 비중): {res['Return'].mean():.2f}%")
    print(f"• 단순 보유 평균 수익률:               {res['BuyHold'].mean():.2f}%")
    print(f"• 초과 수익 (전략 - 보유):             {res['Return'].mean() - res['BuyHold'].mean():+.2f}%p")
    if len(traded):
        print(f"• 거래 발생 종목만: 전략 {traded['Return'].mean():.2f}% / 보유 {traded['BuyHold'].mean():.2f}%")
    if trade_returns:
        tr = np.array(trade_returns)
        print(f"• 총 거래 {len(tr)}회 | 승률 {(tr > 0).mean() * 100:.1f}% | 거래당 평균 {tr.mean():.2f}% "
              f"(평균 이익 {tr[tr > 0].mean() if (tr > 0).any() else 0:.2f}% / 평균 손실 {tr[tr <= 0].mean() if (tr <= 0).any() else 0:.2f}%)")
        print(f"• 갭으로 진입 포기: {int(res['GapSkips'].sum())}회 | 종료 시점 보유 중: {int(res['OpenAtEnd'].sum())}종목 (종가로 평가)")
    if res['Market'].nunique() > 1:
        print("• 시장별:")
        for market, g in res.groupby('Market'):
            print(f"    {market:7s} 전략 {g['Return'].mean():7.2f}% / 보유 {g['BuyHold'].mean():7.2f}% / 거래 {int(g['Trades'].sum())}회")
    print("=" * 55)
    print("⚠️ 현재 구성 종목·현재 재무 데이터 기준이라 생존 편향이 일부 남아 있음")

def save_chart(res, label):
    os.makedirs(CHART_DIR, exist_ok=True)
    plot = res.head(60)  # 종목이 많으면 막대가 안 보여서 상위 60개만
    x = np.arange(len(plot))
    plt.figure(figsize=(16, 6))
    plt.bar(x - 0.2, plot['Return'], width=0.4, color='skyblue', label='전략')
    plt.bar(x + 0.2, plot['BuyHold'], width=0.4, color='lightgray', label='단순 보유')
    plt.xticks(x, plot['Ticker'], rotation=90, fontsize=8)
    plt.title(f'{label} 백테스트 결과 (전략 수익률 상위 {len(plot)}개)', fontsize=15)
    plt.ylabel('수익률 (%)')
    plt.axhline(0, color='red', linestyle='--')
    plt.legend()
    plt.tight_layout()
    path = os.path.join(CHART_DIR, f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
    plt.savefig(path)
    plt.close()
    print(f"🖼️ 차트 저장: {path}")

if __name__ == "__main__":
    source = sys.argv[1].upper() if len(sys.argv) > 1 else 'ALL'
    start = sys.argv[2] if len(sys.argv) > 2 else "2024-01-01"
    universe = get_universe(source)
    label = "DB 추천 종목" if source == 'DB' else f"{source} 유니버스"
    run_portfolio_backtest(universe, start, datetime.now().strftime("%Y-%m-%d"), label)
