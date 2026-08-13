# 업데이트날짜: 2026.08.10
# 작성자: j-neat
# 스케줄러 모듈 (30분 법칙 및 미장 시간대 최적화 버전)

import schedule
import time
import subprocess
from datetime import datetime

def run_quant_bot():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{now}] 🤖 퀀트 스크리닝 배치를 시작합니다...")
    
    try:
        import sys
        venv_python = sys.executable
        
        subprocess.run([venv_python, "main.py"], check=True)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ 스크리닝 작업 완료!")
    except subprocess.CalledProcessError as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚨 봇 실행 중 오류 발생: {e}")

# 💡 [핵심] 30분 법칙 캔들 완성 이후 및 미장(NASDAQ) 시간대 포함
run_times = [
    # 한국장(09:00 개장) 타점
    "08:40",
    "09:00",
    "09:35", # 30분 법칙 완성 직후 (핵심)
    "10:00",
    "10:30",
    "11:00", 
    "13:30", 
    "15:10", # 종가 베팅
    
    # 미국장(22:30 서머타임 개장) 타점
    "23:10", # 미장 30분 법칙 완성 직후
    "01:00",
    "04:00",
    "04:30"
]

days = ["monday", "tuesday", "wednesday", "thursday", "friday"]

for day in days:
    for t in run_times:
        getattr(schedule.every(), day).at(t).do(run_quant_bot)

print("⏰ 로컬 스케줄러 가동 시작... (종료하려면 Ctrl+C)")
print(f"📌 세팅된 실행 시간(평일): {', '.join(run_times)}")

try:
    while True:
        schedule.run_pending()
        time.sleep(60)
except KeyboardInterrupt:
    print("\n🛑 사용자의 요청으로 퀀트 스케줄러를 안전하게 중지합니다.")
    print("✨ 시스템 OFF 완료!")