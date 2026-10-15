# Quant_Test (2026_quant) — Claude 작업 메모

나스닥100 / 코스피100 / 코스닥100+ETF 종목을 기술적·재무적 지표로 점수화해서
매수 시그널을 Slack으로 보내고 로컬 SQLite(`data/quant.db`)에 기록하는 개인 퀀트 봇.
답변은 한국어로 해줘.

## 실행 환경
- Windows, PowerShell, 가상환경 `venv` (`.\venv\Scripts\activate`)
- Python 패키지: `requirements.txt` (pandas 3.x, yfinance, supabase, slack_sdk, OpenDartReader 등)
- 비밀값은 `.env` (SLACK_TOKEN, SLACK_CHANNEL, DART_API_KEY / SUPABASE_*는 이전 스크립트용, QUANT_DB_PATH 선택) — 절대 커밋/출력 금지
- 실행: `python main.py [KR|US|ALL]`, 자동 실행: `python scheduler.py`

## 파일 구조
- `main.py` — 유니버스 수집 → DART 공시 수집(Phase 1) → A/S 리포트 → 종목 스크리닝(Phase 2) → Slack/DB
- `strategy.py` — `apply_multi_factor_strategy()` 점수 계산, 30분 법칙, 하이킨아시, 공시 이벤트 점수, TP/SL
- `data_collector.py` — yfinance 시세/재무, 네이버 금융 외국인·기관 수급
- `dart_manager.py` — DART 공시 + 네이버 뉴스 키워드로 호재/악재 판별 → `dart_disclosures` 테이블
- `db_manager.py` — **유일한 DB 접근 계층** (SQLite). `quant_signals`(보관 365일), `dart_disclosures`(30일, ticker+report_title UNIQUE)
- `web_app.py` — 아이폰 앱(PWA) 서버 (FastAPI, `app_static/`). 스케줄러 내장(`scheduler.due_jobs` 재사용) → scheduler.py와 동시 실행 금지. 기본 127.0.0.1:8000, Tailscale serve로 HTTPS
- `push_notifier.py` — 웹 푸시 (VAPID 키 `data/vapid_private.pem` 자동 생성), main.py가 BUY 저장 시 슬랙과 별도로 전송
- `db_viewer.py` — 로컬 DB 조회 (`python db_viewer.py [summary|signals|disclosures|today|sql "..."]`)
- `migrate_supabase_to_sqlite.py` — 일시정지된 Supabase 프로젝트 Resume 후 1회 실행해 예전 데이터 이전 (중복 실행 안전)
- `visualizer.py` — 차트 PNG 생성 (`charts/`), 저장 경로 반환
- `slack_notifier.py` — 메시지/차트 전송, 채널 백그라운드 청소
- `scheduler.py` — 한국장(KST)·미국장(뉴욕 현지시간) 평일 시간표로 `main.py KR/US` 실행
- `backtester.py` — `python backtester.py [ALL|KR|US|DB] [시작일]` 실전과 같은 유니버스 백테스트 (DB=봇 추천 종목만, 비교용)
- `performance_reporter.py` — DB 추천 종목 실전 수익률 평가
- 유니버스(`get_nasdaq_100` 등)와 `INDEX_BY_MARKET`은 `data_collector.py`에 있음 (main.py는 Slack 토큰 없으면 import 시 종료되므로)

## 2026-10-15 수정 내역 (Claude 앱에서 작업)
- pandas 3에서 `pd.read_html(문자열)` 에러로 나스닥100이 AAPL·MSFT 2종목만 분석되던 버그 → `io.StringIO`로 수정
- 공시 점수: 악재 후 주가 상승 시 페널티가 가점으로 바뀌던 버그 수정, 호재 건당 최대 10점, 이벤트 합계 -30~+20 제한
- A/S 리포트: 전략 조기 종료 시 `targets`가 비어 KeyError로 종목이 사라지던 문제 수정, 종목명 대신 티커 넘기던 버그 수정
- 미국 주식 TP/SL을 소수점 2자리 유지 (`int()` 절삭 제거), Slack 메시지 가격 포맷 시장별 분리
- 재무 데이터 `None`/`'Infinity'` 처리, 조회 실패해도 0으로 대체하고 분석 계속
- 30분 법칙: 전 거래일 분봉이면 판단 보류, ticker 없으면(백테스트) 건너뜀
- 시장 국면: 실행 1회당 캐시, KOSDAQ은 `^KQ11` 기준 (원래 `^KS11` — 되돌리려면 `data_collector.INDEX_BY_MARKET` 수정)
- 백테스트: 손절/익절을 종가가 아닌 실제 체결가(갭이면 시가)로 청산, 종료일 오늘로, ETF 판별용 종목명 전달
- 스케줄러: 미장을 뉴욕 현지 요일·시간 기준으로 (서머타임 자동 반영), `main.py KR/US` 분리 실행
- DART/Supabase 클라이언트 재사용, 요청 timeout 추가, 에러를 삼키지 않고 로그 출력, 차트 파일명 금지문자 치환
- `.gitignore`에 `docs_cache/`, `backtest_charts/` 추가 / `requirements.txt` UTF-16 → UTF-8 / README 갱신
- 실 API(yfinance, Supabase, DART, Slack)로는 아직 미검증 — 가짜 데이터로만 테스트함

## 과제 현황 (2026-10-15 이어서 처리)
- ~~매수 시그널 중복 저장~~ → 해결: `save_signal_to_db`가 같은 거래일(한국장 KST, 미장 뉴욕 날짜)에 이미 저장된 티커면 건너뜀 (그날 최초 추천가 유지)
- ~~실행마다 Slack 채널 전체 삭제~~ → 해결: `SLACK_RETENTION_DAYS`(7일) 지난 메시지만 삭제, 오늘 이미 추천한 종목은 Slack 재전송 생략, 용어 사전은 하루 1번 (A/S 리포트는 실행마다 계속 발송)
- ~~A/S 리포트 기준가~~ → 해결: 최근 3일 내 **최초 추천가** 기준으로 수익률 계산, 리포트에 `MM/DD 추천가 기준, N일 추천됨` 표시
- ~~악재 점수 불연속~~ → 해결: 하락 0% 이하 -30점 → 10% 하락 -15점까지 선형, 그 이상은 -15점 유지 (`BAD_PENALTY_*` 상수)
- ~~인버스 ETF 하락장 매수 불가~~ → 해결: 일반 종목은 하락장, 인버스 ETF(`INVERSE_KEYWORDS`)는 상승장에서 차단. `is_bull_market=None`이면 국면 필터 생략
- ~~백테스트 낙관 편향~~ → 해결: 전체 유니버스 테스트, 날짜별 지수 200일선 국면 적용, 다음 날 시가 진입(갭이면 포기), 실제 재무 데이터, 실전과 같은 6개월 판단 창, 단순 보유 대비 비교 리포트, 차트는 `backtest_charts/`에 저장(창 안 띄움)
  - 남은 한계: 현재 구성 종목 기준(생존 편향), 재무는 현재 값, 수급 데이터 없음
  - 2025-01~2026-10 실데이터 4종목 스모크 테스트: 승률 59%지만 단순 보유 대비 크게 뒤처짐 (AAPL·NVDA·삼성전자·코스닥 인버스)
- ~~`docs_cache` git 추적 여부~~ → 확인 결과 추적 안 됨, 조치 불필요

## 2026-10-15 실제 실행에서 발견·수정
- Supabase 프로젝트 `neat-quant`가 무료 플랜 비활성으로 일시정지(DNS 조회 실패) → 로컬 SQLite로 전환. Supabase 데이터는 2027-10-13까지 Resume 가능
- 위키피디아 나스닥100 구성종목 표가 `List_of_NASDAQ-100_companies` 문서로 이동 → 새 문서 우선 조회
- 네이버 금융 수급 페이지(frgn.naver) 개편으로 HTML 표 사라짐 → `m.stock.naver.com/api/stock/{code}/trend` JSON 사용 (이전엔 수급 점수가 사실상 항상 0)
- Git Bash 등 파이프로 실행하면 cp949 콘솔에서 이모지 print가 UnicodeEncodeError → `PYTHONIOENCODING=utf-8` 필요 (PowerShell 콘솔 직접 실행은 문제없음)
- 나스닥 추천 과다(하루 50건): 52주 고가 근접도(고가 70%만 돼도 14.7점)·거래량(평소 1배에 7.5점) 공짜 점수 제거 + 시장별 기준 `BUY_THRESHOLD_BY_MARKET`(NASDAQ 80, 목·금 +10)
  - 근거: 2025-10~2026-10 나스닥100 일별 점수 분포 → 기준 80이면 하루 평균 5.8건(중앙값 4)
  - ⚠️ 같은 분석에서 점수의 5일 후 수익률 예측력은 거의 없었음 (추천 평균 ~0.6% vs 전체 평균 0.67%, 승률 ~51%) — 전략 자체 개선은 별도 과제

## 2026-10-15 전략 예측력 연구 (`research/`)
- 2021-01~2026-10 나스닥100·코스피100·코스닥100, 상승장 날짜만, 다음 날 시가 진입 → 10일 후 초과수익으로 팩터 검증 (학습 2021-23 / 검증 2024-26)
- 한국장 점수 교체: RSI·20일선 이격·거래량·매물대 제거(무효/역방향, 기존 점수 상위 5종목이 무작위보다 못함) → 52주 고가 근접(60점) + 하이킨아시 + 수급(검증 불가라 각 5점) + 공시. 기준 70점, 목·금 가산 없음
- 실전 일봉 6개월 → 1년 (예전 '52주 고가'가 실제론 6개월 고가였음). OBV는 예전과 같게 최근 125일부터 누적, 차트는 최근 125일만
- 나스닥: 유효한 팩터 없음 → 구조 유지, 기준 80(목·금 90). 1년 데이터 기준으로 추천 건수 재확인함
- 백테스터 LOOKBACK 250

## 2026-10-15 아이폰 앱 (PWA)
- 슬랙은 그대로 유지, 앱은 별도 채널. 탭: 오늘(시장 국면·오늘 추천) / 추적(최초 추천가 대비 수익률·익절/손절 상태) / 공시 / 봇(수동 실행·로그·알림 설정·시간표)
- DB 추가: quant_signals에 open_price/tp/sl/chart_path 컬럼(자동 ALTER), push_subscriptions, bot_runs 테이블. 앱 차트는 data/charts/ (90일 보관)
- 한국식 색상(상승 빨강/하락 파랑). 정적 파일 바꾸면 index.html·sw.js의 `?v=` 와 캐시 이름 올릴 것
- Tailscale 설치·serve 완료: https://laptop-9i91gfr9.taila87c3d.ts.net → 127.0.0.1:8000 (노트북이라 절전 시 서버 멈춤 주의)
- 자동 실행 시간표는 앱에서 편집 → DB app_settings['schedule'] (`scheduler.load_schedule()`), 코드의 KR/US_RUN_TIMES는 기본값
