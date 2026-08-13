# 업데이트날짜: 2026.08.13
# 작성자: j-neat
# 슬랙 알림 전송 전담 모듈 (백그라운드 채널 청소 적용)

import os
import requests
import time
import threading
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

def _clear_channel_worker(token, channel_id):
    """백그라운드에서 실행될 실제 메시지 삭제 로직 (100개 이상 모두 삭제 지원)"""
    print("🧹 [백그라운드] 슬랙 채널 청소 시작...")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    history_url = "https://slack.com/api/conversations.history"
    
    try:
        total_deleted = 0
        while True:
            params = {"channel": channel_id, "limit": 100}
            res = requests.get(history_url, headers=headers, params=params).json()
            
            if not res.get("ok"):
                print(f"🚨 [백그라운드 에러] 메시지 목록을 불러오지 못했습니다: {res.get('error')}")
                break
                
            messages = res.get("messages", [])
            if not messages:
                if total_deleted == 0:
                    print("✨ [백그라운드] 삭제할 메시지가 없습니다. (이미 깨끗함)")
                break
                
            # 100개씩 순회하며 삭제
            for msg in messages:
                delete_url = "https://slack.com/api/chat.delete"
                del_data = {
                    "channel": channel_id,
                    "ts": msg["ts"]
                }
                
                while True:
                    del_res = requests.post(delete_url, headers=headers, json=del_data).json()
                    
                    if not del_res.get("ok"):
                        if del_res.get("error") == "ratelimited":
                            # 속도 제한 걸리면 3초 쉬고 다시 시도
                            time.sleep(3)
                            continue 
                        else:
                            break
                    break 
                    
                # 슬랙 API 삭제 권장 간격 (1분에 50개 제한 고려)
                time.sleep(1.2)
                total_deleted += 1
            
            # 💡 [핵심] 메시지가 더 남아있는지 슬랙 API 응답(has_more) 확인
            if not res.get("has_more"):
                break
                
        if total_deleted > 0:
            print(f"✨ [백그라운드] 슬랙 채널 청소 완료! (총 {total_deleted}개 삭제)")
        
    except Exception as e:
        print(f"🚨 [백그라운드] 슬랙 청소 중 시스템 에러 발생: {e}")

def clear_slack_channel(token, channel_id):
    """채널 청소 스레드를 실행하고 즉시 제어권을 반환하는 함수"""
    t = threading.Thread(target=_clear_channel_worker, args=(token, channel_id))
    t.start()
    print("🚀 슬랙 청소 작업을 백그라운드로 보냈어. (메인 작업은 기다림 없이 계속 진행됨)")

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