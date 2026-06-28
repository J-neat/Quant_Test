# Quant_Test

주식 시장 분석 연습 프로그램입니다.

---

# 1. 프로젝트 개요

이 프로젝트는 **나스닥 및 코스닥 종목의 기술적/재무적 지표를 분석**하고, **Slack으로 매일 분석 리포트와 차트를 자동 전송**하는 퀀트 투자 도구입니다.

---

# 2. 주요 구성 요소

```text
Quant_Test/
├── main.py               # 봇 실행 메인 코드
├── data_collector.py     # 데이터 수집 (yfinance, FinanceDataReader)
├── slack_notifier.py     # Slack 알림 및 차트 전송
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
