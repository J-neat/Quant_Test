# Quant_Test

주식 시장 분석 연습 프로그램입니다.

---

# 1. 프로젝트 개요

이 프로젝트는 **나스닥 및 코스피,코스닥 종목의 기술적/재무적 지표를 분석**하고, **Slack으로 매일 분석 리포트와 차트를 자동 전송**하는 퀀트 투자 도구입니다.

---

# 2. 주요 구성 요소

```text
Quant_Test/
├── main.py               # 봇 실행 메인 코드 (python main.py [KR|US|ALL])
├── scheduler.py          # 장 시간대별 자동 실행
├── data_collector.py     # 데이터 수집 (yfinance, 네이버 수급)
├── strategy.py           # 멀티팩터 스코어링 및 매수 시그널
├── dart_manager.py       # DART 공시 + 네이버 뉴스 호재/악재 수집
├── db_manager.py         # 로컬 SQLite DB(data/quant.db) 저장/조회/청소
├── db_viewer.py          # 로컬 DB 조회 (python db_viewer.py [summary|signals|disclosures|today])
├── migrate_supabase_to_sqlite.py # 예전 Supabase 데이터 → 로컬 DB 1회 이전
├── visualizer.py         # 차트 생성
├── slack_notifier.py     # Slack 알림 및 차트 전송
├── backtester.py         # 유니버스 백테스트 (python backtester.py [ALL|KR|US|DB] [시작일])
├── performance_reporter.py # 실전 추천 성과 평가
├── requirements.txt      # 필수 라이브러리 목록
└── .gitignore            # 보안을 위한 설정
```

---

# 3. 설치 및 설정 가이드

## 3.1 프로젝트 복제

```bash
git clone https://github.com/J-neat/Quant_Test.git
cd Quant_Test
```

---

## 3.2 환경 설정 및 라이브러리 설치

```bash
# 가상환경 생성
python -m venv venv

# 가상환경 활성화 (Windows)
.\venv\Scripts\activate

# 의존성 라이브러리 설치
pip install -r requirements.txt
```

---

## 3.3 환경 변수 설정

프로젝트 루트 폴더에 `.env` 파일을 생성한 후 아래 내용을 입력합니다.

```env
SLACK_TOKEN=xoxb-발급받은-토큰-입력
SLACK_CHANNEL=채널ID-입력
DART_API_KEY=발급받은-DART-API-키

# (선택) 예전 Supabase 데이터를 옮길 때만 필요
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=eyJhb...
```

DB는 로컬 SQLite 파일(`data/quant.db`)이라 따로 가입·설정할 필요가 없습니다. 첫 실행 때 자동으로 만들어집니다.
다른 위치에 두려면 `.env`에 `QUANT_DB_PATH=경로`를 추가하세요. 이 파일만 백업하면 모든 기록이 보존됩니다.

## 3.5 실행 방법

```bash
# 전체 시장 1회 분석
python main.py

# 시장별 분석 (KR: 코스피/코스닥, US: 나스닥)
python main.py KR
python main.py US

# 정해진 시간에 자동 실행 (한국장은 KST, 미국장은 뉴욕 현지시간 기준 평일)
python scheduler.py

# 백테스트 (ALL/KR/US: 실전 유니버스 전체, DB: 봇이 추천했던 종목만) — 차트는 backtest_charts/
python backtester.py ALL 2024-01-01

# 실전 추천 성과 평가 (DB에 쌓인 추천 기록 기준)
python performance_reporter.py

# 로컬 DB 조회 (요약 / 최근 추천 / 공시 이벤트 / 오늘 추천)
python db_viewer.py
python db_viewer.py signals 50
python db_viewer.py disclosures
python db_viewer.py today

# 예전 Supabase 데이터를 로컬 DB로 이전 (Supabase 프로젝트 Resume 후 1회)
python migrate_supabase_to_sqlite.py
```

---

## 3.4 Slack API 설정

Slack API의 **OAuth & Permissions** 메뉴에서 **Bot Token Scopes**에 아래 권한을 추가합니다.

```text
chat:write
channels:history
channels:join
files:write
```

---

# 4. 팀원을 위한 팁

### 채널 ID 확인 방법

1. Slack에서 원하는 채널 우클릭
2. **채널 세부 정보 보기**
3. 하단의 **채널 ID** 복사

### 라이브러리 추가 시

새 패키지를 설치한 후 반드시 `requirements.txt`를 최신 상태로 갱신하세요.

```bash
pip install 패키지명
pip freeze > requirements.txt
```

---

# 사용 기술

* Python
* yfinance
* FinanceDataReader
* Slack API
* dotenv

---

# 참고 사항

* `.env` 파일은 Git에 업로드하지 않습니다.
* Slack Bot Token은 외부에 노출되지 않도록 주의하세요.
* `requirements.txt`는 라이브러리 변경 시마다 업데이트하는 것을 권장합니다.
