# 업데이트날짜: 2026.08.13
# 작성자: j-neat
# 메인모듈 (DB 자동 청소 및 슬랙 백그라운드 초기화 적용 버전)

import os
import sys
import shutil
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

from data_collector import (get_stock_data, get_fundamental_data, get_supply_data,
                            get_nasdaq_100, get_kospi_top_100, get_kosdaq_top_100, INDEX_BY_MARKET)
from strategy import apply_multi_factor_strategy
from visualizer import plot_stock_chart
from slack_notifier import send_quant_signal, clear_slack_channel, was_posted_today
from db_manager import (save_signal_to_db, get_recent_buy_signals, cleanup_old_db_data, is_signal_saved_today,
                        CHART_DIR as APP_CHART_DIR)
from push_notifier import send_push_all
from dart_manager import collect_and_save_disclosures

load_dotenv()

SLACK_TOKEN = os.getenv("SLACK_TOKEN")
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL")

if not SLACK_TOKEN or not SLACK_CHANNEL:
    print("🚨 오류: 슬랙 토큰이나 채널 ID 없음!")
    sys.exit(1)

KR_MARKETS = ('KOSPI', 'KOSDAQ')
KST = ZoneInfo("Asia/Seoul")
NY = ZoneInfo("America/New_York")

def is_kr_market(market_type):
    return market_type in KR_MARKETS

def fmt_price(value, market_type):
    """한국 주식은 원 단위, 미국 주식은 소수점 2자리로 표시"""
    return f"{value:,.0f}" if is_kr_market(market_type) else f"{value:,.2f}"

def keep_chart_for_app(chart_path, ticker):
    """슬랙용 차트를 앱용 보관 폴더(data/charts/)에 복사하고 파일명 반환 (실패 시 None)"""
    try:
        if not chart_path or not os.path.exists(chart_path):
            return None
        os.makedirs(APP_CHART_DIR, exist_ok=True)
        safe = ticker.replace('.', '_').replace('/', '_')
        file_name = f"{datetime.now().strftime('%Y%m%d_%H%M')}_{safe}.png"
        shutil.copyfile(chart_path, os.path.join(APP_CHART_DIR, file_name))
        return file_name
    except Exception as e:
        print(f"  ⚠️ [앱 차트 보관 실패] {e}")
        return None

def clean_charts_folder():
    folder_path = "charts"
    if os.path.exists(folder_path):
        shutil.rmtree(folder_path)
    os.makedirs(folder_path)

_regime_cache = {}

def check_market_regime(index_ticker):
    """지수가 200일선 위인지 확인 (같은 실행 안에서는 결과를 캐시해서 재사용)"""
    if index_ticker in _regime_cache:
        return _regime_cache[index_ticker]
    try:
        # 1y(약 250거래일)는 200일선 계산에 여유가 적어서 2y로 넉넉하게 조회
        index_df = get_stock_data(index_ticker, period='2y')
        sma_200 = index_df['Close'].rolling(window=200).mean().iloc[-1]
        result = bool(pd.isna(sma_200) or index_df['Close'].iloc[-1] > sma_200)
    except Exception as e:
        print(f"⚠️ 시장 국면 확인 실패({index_ticker}): {e} → 상승장으로 간주")
        result = True
    _regime_cache[index_ticker] = result
    return result

TERM_DICT_HEADER = "📚 *[퀀트 시그널 용어 사전]* 📚"

def send_term_dictionary(token, channel_id):
    # 💡 [수정] 채널을 매번 비우지 않으므로 용어 사전은 하루 1번만 발송
    if was_posted_today(token, channel_id, TERM_DICT_HEADER):
        print("📚 용어 사전은 오늘 이미 발송됨 → 생략")
        return
    msg = (
        f"{TERM_DICT_HEADER}\n\n"
        "• *RSI (상대강도지수):* 주가의 과열/침체를 나타냅니다. 30 이하면 과매도(바닥권), 70 이상이면 과매수(고점권)로 해석합니다.\n"
        "• *OBV:* 거래량 누적 지표입니다. 주가가 하락하는데 OBV가 버틴다면 '스마트 머니'의 매집을 의심할 수 있습니다.\n"
        "• *POC (Point of Control):* 최근 6개월간 가장 많은 거래가 이루어진 '최대 매물대' 가격입니다. 강력한 지지선/저항선 역할을 합니다.\n"
        "• *PER / PBR:* 기업의 수익성과 자산 대비 현재 주가의 고평가/저평가를 나타내는 기본적 분석 지표입니다.\n"
        "------------------------------------------------------------"
    )
    send_quant_signal(token, channel_id, msg)

def signal_label_date(created_at, market_type):
    """DB created_at(UTC)을 시장 현지 날짜 'MM/DD'로 변환 (실패 시 '?')"""
    try:
        tz = KST if is_kr_market(market_type) else NY
        return datetime.fromisoformat(created_at).astimezone(tz).strftime("%m/%d")
    except (TypeError, ValueError):
        return "?"

def send_position_tracking_report(token, channel_id, markets=None):
    recent_signals = get_recent_buy_signals()
    if markets:
        recent_signals = [s for s in recent_signals if s.get('market_type') in markets]
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
        # 💡 수익률은 기간 내 '최초 추천가' 기준 → 언제 추천가인지 함께 표시
        since = f"{signal_label_date(signal_data.get('created_at'), market_type)} 추천가 기준"
        if signal_data.get('signal_count', 1) > 1:
            since += f", {signal_data['signal_count']}일 추천됨"
        
        try:
            df = get_stock_data(ticker, period='1y')
            if df is None or len(df) < 20: continue
            fundamentals = get_fundamental_data(ticker)
            supply_info = get_supply_data(ticker, market_type)
            is_bull = check_market_regime(INDEX_BY_MARKET.get(market_type, 'QQQ'))

            # 💡 [수정] 종목명 자리에 티커를 넘기던 버그 수정 (ETF 판별이 안 되던 문제)
            signal, current_score, reasons, _, targets = apply_multi_factor_strategy(
                df, fundamentals, market_type, supply_info, stock_name, is_bull, ticker
            )
            
            current_price = df['Close'].iloc[-1]
            return_pct = ((current_price - orig_price) / orig_price) * 100
            
            # 💡 [수정] 하락장/유동성 부족 등으로 전략이 조기 종료되면 targets가 빈 dict라서
            #    기존 코드는 KeyError → 해당 종목이 리포트에서 조용히 사라졌음
            stop_loss = targets.get('SL') if targets else None
            if stop_loss and current_price <= stop_loss:
                tracking_msg += f"🚨 `{display_name}` : *손절가 이탈* ({return_pct:+.1f}% / {since})\n"
            elif signal == 'BUY':
                tracking_msg += f"✅ `{display_name}` : HOLD ({current_score}점 / {return_pct:+.1f}% / {since})\n"
            else:
                why = f" - {reasons[0].strip()}" if (not targets and reasons) else ""
                tracking_msg += f"⚠️ `{display_name}` : 매도 준비 ({current_score}점 / {return_pct:+.1f}% / {since}){why}\n"
        except Exception as e:
            print(f"  ⚠️ [A/S 리포트] {display_name} 평가 실패: {type(e).__name__}: {e}")
            
    tracking_msg += "\n------------------------------------------------------------\n👇 *오늘의 신규 시그널* 👇"
    send_quant_signal(token, channel_id, tracking_msg)


def parse_target_markets(argv):
    """실행 인자로 분석할 시장 선택: python main.py KR | US | ALL (기본값 ALL)"""
    arg = argv[1].upper() if len(argv) > 1 else 'ALL'
    if arg == 'KR':
        return ['KOSPI', 'KOSDAQ']
    if arg == 'US':
        return ['NASDAQ']
    return ['NASDAQ', 'KOSPI', 'KOSDAQ']


if __name__ == "__main__":
    target_markets = parse_target_markets(sys.argv)
    print(f"=== 🚀 멀티팩터 퀀트 시스템 시작 (대상: {', '.join(target_markets)}) ===")
    clean_charts_folder()
    
    # 💡 [핵심] 프로그램 시작 직후 가장 먼저 30일 지난 DB 데이터 청소
    cleanup_old_db_data()
    
    # 프로그램 시작 직후 오래된 슬랙 메시지 청소(백그라운드) 및 용어 사전 발송(하루 1번)
    clear_slack_channel(SLACK_TOKEN, SLACK_CHANNEL)
    send_term_dictionary(SLACK_TOKEN, SLACK_CHANNEL)
    
    # 1. 대상 유니버스 셋업 (필요한 시장만)
    us_stocks = get_nasdaq_100() if 'NASDAQ' in target_markets else {}
    kr_kospi_stocks = get_kospi_top_100() if 'KOSPI' in target_markets else {}
    kr_kosdaq_stocks = get_kosdaq_top_100() if 'KOSDAQ' in target_markets else {}

    # ==========================================================
    # 💡 [Phase 1] DART 공시 데이터 선제 수집 및 DB 적재 (한국 시장 대상일 때만)
    # ==========================================================
    if kr_kospi_stocks or kr_kosdaq_stocks:
        print("\n📡 [Phase 1] 한국 시장(KOSPI/KOSDAQ) 공시 데이터 수집 중...")
        
        for ticker, name in kr_kospi_stocks.items():
            collect_and_save_disclosures(ticker, name)
            
        for ticker, name in kr_kosdaq_stocks.items():
            # ETF(레버리지/인버스)는 DART 공시 대상이 아니므로 건너뜀
            if ticker.endswith('.KQ'):
                collect_and_save_disclosures(ticker, name)
            
        print("✅ 공시 데이터 DB 적재 완료!\n")
    # ==========================================================

    # A/S 리포트는 공시 수집 및 분석을 위해 Phase 1 이후에 발송
    send_position_tracking_report(SLACK_TOKEN, SLACK_CHANNEL, target_markets)

    # ==========================================================
    # 💡 [Phase 2] 본격적인 전략 분석 및 스크리닝
    # ==========================================================
    groups = [
        ("🇺🇸 (NASDAQ 100)", us_stocks, 'NASDAQ'), 
        ("🇰🇷 (KOSPI 100)", kr_kospi_stocks, 'KOSPI'), 
        ("🇰🇷 (KOSDAQ 100+ETF)", kr_kosdaq_stocks, 'KOSDAQ') 
    ]
    
    for flag, stock_dict, market_type in groups:
        if not stock_dict:
            continue
        print(f"\n▶️ [Phase 2] {flag} 차트 분석 중...")
        is_bull_market = check_market_regime(INDEX_BY_MARKET[market_type])
        error_count = 0
        
        for ticker, name in stock_dict.items():
            try:
                raw_data = get_stock_data(ticker, period='1y')
                if raw_data is None or len(raw_data) < 20: continue

                fundamentals = get_fundamental_data(ticker)
                supply_info = get_supply_data(ticker, market_type)
                
                signal, score, reasons, processed_data, price_targets = apply_multi_factor_strategy(
                    raw_data, fundamentals, market_type, supply_info, name, is_bull_market, ticker
                )
                
                display_name = f"{name}({ticker.replace('.KS', '').replace('.KQ', '')})"
                
                if signal == 'BUY' and is_signal_saved_today(ticker, market_type):
                    # 💡 [중복 방지] 오늘 이미 추천·알림한 종목은 슬랙 재전송/DB 저장 생략
                    print(f"  ⏭️ [추천 유지] {display_name} ({score}점) - 오늘 이미 알림 보냄")
                elif signal == 'BUY':
                    current_price = raw_data['Close'].iloc[-1]
                    open_price = raw_data['Open'].iloc[-1] 
                    
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    chart_path = plot_stock_chart(processed_data.tail(125), display_name, score, reasons, fundamentals)
                    
                    msg = (f"🚨 *[매수 추천 봇]*\n"
                           f"⏰ `{now}`\n📌 {display_name}\n"
                           f"📈 *당일 시가:* `{fmt_price(open_price, market_type)}`\n"
                           f"💰 *현재가:* `{fmt_price(current_price, market_type)}`\n"
                           f"🎯 익절(시가기준): `{fmt_price(price_targets['TP'], market_type)}`\n"
                           f"🛑 손절(시가기준): `{fmt_price(price_targets['SL'], market_type)}`\n"
                           f"📊 스코어: `{score}점`\n💡 사유: {', '.join(reasons)}")
                    
                    send_quant_signal(SLACK_TOKEN, SLACK_CHANNEL, msg, chart_path)
                    # 📱 앱용: 차트는 charts/가 실행마다 비워지므로 data/charts/에 따로 보관
                    app_chart = keep_chart_for_app(chart_path, ticker)
                    saved = save_signal_to_db(ticker, name, current_price, score, reasons, market_type,
                                              open_price=open_price, tp=price_targets['TP'], sl=price_targets['SL'],
                                              chart_path=app_chart)
                    if saved:
                        send_push_all(
                            f"🚨 매수 추천 · {name}",
                            f"{score}점 | 현재가 {fmt_price(current_price, market_type)} | "
                            f"익절 {fmt_price(price_targets['TP'], market_type)} / 손절 {fmt_price(price_targets['SL'], market_type)}",
                            url=f"/?tab=today&ticker={ticker}", tag=ticker)
                    print(f"  ✅ [추천] {display_name} ({score}점)")
            except Exception as e:
                # 💡 [수정] 에러를 조용히 삼키지 않고 원인을 출력 (어떤 종목이 왜 빠졌는지 확인 가능)
                error_count += 1
                print(f"  ❌ [{ticker}] 분석 실패: {type(e).__name__}: {e}")

        if error_count:
            print(f"  ⚠️ {flag}: {error_count}개 종목 분석 실패")
