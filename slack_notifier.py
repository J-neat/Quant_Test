#업데이트날짜: 2026.06.26
#작성자: j-neat
#슬랙 알림 전송 전담 모듈
import requests  
import time      
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import os

def clear_slack_channel(token, channel_id):
    print("🧹 슬랙 채널의 이전 메시지들을 싹 지우는 중...")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    history_url = "https://slack.com/api/conversations.history"
    params = {"channel": channel_id, "limit": 100}
    
    try:
        res = requests.get(history_url, headers=headers, params=params).json()
        
        if not res.get("ok"):
            print(f"🚨 [슬랙 에러] 메시지 목록을 불러오지 못했습니다: {res.get('error')}")
            return
            
        messages = res.get("messages", [])
        if not messages:
            print("✨ 삭제할 메시지가 없습니다. (이미 깨끗함)")
            return
            
        for msg in messages:
            delete_url = "https://slack.com/api/chat.delete"
            del_data = {
                "channel": channel_id,
                "ts": msg["ts"]
            }
            
            # 💡 [핵심] 삭제 성공할 때까지 무한 재시도하는 while 루프 추가
            while True:
                del_res = requests.post(delete_url, headers=headers, json=del_data).json()
                
                if not del_res.get("ok"):
                    if del_res.get("error") == "ratelimited":
                        print("⏳ 슬랙 속도 제한 감지! 3초 대기 후 해당 메시지부터 재시도...")
                        time.sleep(3)
                        continue  # 다시 시도!
                    else:
                        print(f"⚠️ 삭제 실패 (건너뜀): {del_res.get('error')}")
                        break
                break  # 정상 삭제 시 루프 탈출
                
            # 슬랙 API 삭제 권장 간격 (1분에 50개 제한 고려)
            time.sleep(1.2)
            
        print("✨ 슬랙 채널 청소 완료!")
        
    except Exception as e:
        print(f"🚨 슬랙 청소 중 시스템 에러 발생: {e}")

def send_quant_signal(token, channel_id, message, image_path=None):
    """슬랙 채널로 텍스트 메시지와 차트 이미지를 전송하는 함수"""
    client = WebClient(token=token)
    
    try:
        client.chat_postMessage(
            channel=channel_id,
            text=message
        )
        print(f"  📢 슬랙 메시지 전송 성공!")
        
        if image_path and os.path.exists(image_path):
            client.files_upload_v2(
                channel=channel_id,
                file=image_path,
                title=os.path.basename(image_path),
                initial_comment="📊 해당 종목의 실시간 멀티팩터 분석 차트입니다."
            )
            print(f"  🚀 슬랙 차트 이미지 업로드 완료!")
            
    except SlackApiError as e:
        print(f"  ❌ 슬랙 알림 전송 에러: {e.response['error']}")