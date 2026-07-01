# 업데이트날짜: 2026.07.01
# 작성자: j-neat
# 스케줄러 모듈

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

# 하루 4번 스크리닝을 위한 실행 시간대 배열
run_times = ["08:50", "09:20", "12:00", "15:20", "16:00"]

days = ["monday", "tuesday", "wednesday", "thursday", "friday"]



# 반복문을 통해 평일 x 4개 시간대 스케줄을 한 번에 등록
for day in days:
    for t in run_times:
        getattr(schedule.every(), day).at(t).do(run_quant_bot)

print("⏰ 로컬 스케줄러 가동 시작... (종료하려면 Ctrl+C)")
print(f"📌 세팅된 실행 시간(평일): {', '.join(run_times)}")

# 메인 루프 (1분마다 조건 체크 후 대기)
try:
    # 메인 루프 (1분마다 조건 체크 후 대기)
    while True:
        schedule.run_pending()
        time.sleep(60)
except KeyboardInterrupt:
    # Ctrl + C 를 누르면 에러를 뿜지 않고 아래 코드를 실행하며 깔끔하게 종료됨
    print("\n🛑 사용자의 요청으로 퀀트 스케줄러를 안전하게 중지합니다.")
    print("✨ 시스템 OFF 완료!")