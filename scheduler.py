# 업데이트날짜: 2026.10.15
# 작성자: j-neat
# 스케줄러 모듈 (30분 법칙 및 미장 시간대 최적화 버전)
# - 한국장: 한국 시간(KST) 평일 기준으로 실행 → python main.py KR
# - 미국장: 뉴욕 현지 시간 평일 기준으로 실행 → python main.py US
#   (서머타임 시작/종료를 자동 반영. 기존처럼 KST 23:10 고정이면 11월~3월엔 개장 전에 돌아감)

import sys
import time
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
NY = ZoneInfo("America/New_York")

# 한국장(09:00 개장) 타점 - 한국 시간
KR_RUN_TIMES = [
    "08:40",
    "09:00",
    "09:35",  # 30분 법칙 완성 직후 (핵심)
    "10:00",
    "10:30",
    "11:00",
    "13:30",
    "15:10",  # 종가 베팅
]

# 미국장(09:30 개장) 타점 - 뉴욕 현지 시간
# (서머타임 기준 KST 23:10 / 01:00 / 04:00 / 04:30 과 같은 시점)
US_RUN_TIMES = [
    "10:10",  # 미장 30분 법칙 완성 직후
    "12:00",
    "15:00",
    "15:30",
]


def run_quant_bot(market):
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{now}] 🤖 퀀트 스크리닝 배치를 시작합니다... (시장: {market})")

    try:
        subprocess.run([sys.executable, "main.py", market], check=True)
        print(f"[{datetime.now(KST).strftime('%H:%M:%S')}] ✅ 스크리닝 작업 완료!")
    except subprocess.CalledProcessError as e:
        print(f"[{datetime.now(KST).strftime('%H:%M:%S')}] 🚨 봇 실행 중 오류 발생: {e}")


def due_jobs(last_run_keys):
    """지금 실행해야 할 (시장, 키) 목록. 같은 분에 중복 실행되지 않도록 키로 관리"""
    jobs = []
    for market, tz, run_times in (("KR", KST, KR_RUN_TIMES), ("US", NY, US_RUN_TIMES)):
        local_now = datetime.now(tz)
        # 💡 [수정] 기존에는 미장 새벽 실행(01:00/04:00)도 한국 기준 월~금이라
        #    월요일 새벽(미국 일요일)엔 헛돌고, 토요일 새벽(미국 금요일 장)은 빠졌음
        #    → 각 시장의 현지 요일 기준으로 평일만 실행
        if local_now.weekday() >= 5:
            continue
        for hhmm in run_times:
            hour, minute = map(int, hhmm.split(":"))
            slot = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            key = f"{local_now.strftime('%Y-%m-%d')}-{market}-{hhmm}"
            # 이전 실행이 길어져 정각을 놓쳐도 30분 안이면 늦게라도 실행 (프로그램 시작 시 지난 슬롯 몰아서 실행 방지)
            late_sec = (local_now - slot).total_seconds()
            if 0 <= late_sec < 30 * 60 and key not in last_run_keys:
                jobs.append((market, key))
                break  # 같은 시장은 한 번에 하나만
    return jobs


if __name__ == "__main__":
    print("⏰ 로컬 스케줄러 가동 시작... (종료하려면 Ctrl+C)")
    print(f"📌 한국장(KST, 평일): {', '.join(KR_RUN_TIMES)}")
    print(f"📌 미국장(뉴욕 현지시간, 평일): {', '.join(US_RUN_TIMES)}")

    done_keys = set()
    try:
        while True:
            for market, key in due_jobs(done_keys):
                done_keys.add(key)
                run_quant_bot(market)
            # 오래된 키 정리 (메모리 누수 방지)
            if len(done_keys) > 200:
                done_keys = set(sorted(done_keys)[-50:])  # 키가 날짜로 시작하므로 최근 것만 남음
            time.sleep(20)
    except KeyboardInterrupt:
        print("\n🛑 사용자의 요청으로 퀀트 스케줄러를 안전하게 중지합니다.")
        print("✨ 시스템 OFF 완료!")
