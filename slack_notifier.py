# 업데이트날짜: 2026.08.13
# 작성자: j-neat
# 슬랙 알림 전송 전담 모듈 (신규 메시지 보호 적용)

import os
import requests
import time
import threading
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

def _clear_channel_worker(token, channel_id, latest_ts):
    """백그라운드에서 실행될 실제 메시지 삭제 로직 (최신 메시지 보호)"""
    print("🧹 [백그라운드] 슬랙 채널 청소 시작... (새 메시지 보호)")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    history_url = "https://slack.com/api/conversations.history"
    
    try:
        total_deleted = 0
        while True:
            # 💡 [핵심] latest 파라미터를 추가하여 청소 시작 시간 이전의 메시지만 불러옴
            params = {
                "channel": channel_id, 
                "limit": 100,
                "latest": latest_ts 
            }
            res = requests.get(history_url, headers=headers, params=params).json()
            
            if not res.get("ok"):
                print(f"🚨 [백그라운드 에러] 메시지 목록을 불러오지 못했습니다: {res.get('error')}")
                break
                
            messages = res.get("messages", [])
            if not messages:
                if total_deleted == 0:
                    print("✨ [백그라운드] 삭제할 메시지가 없습니다. (이미 깨끗함)")
                break
                
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
                            time.sleep(3)
                            continue 
                        else:
                            break
                    break 
                    
                time.sleep(1.2)
                total_deleted += 1
            
            if not res.get("has_more"):
                break
                
        if total_deleted > 0:
            print(f"✨ [백그라운드] 슬랙 채널 청소 완료! (총 {total_deleted}개 삭제)")
        
    except Exception as e:
        print(f"🚨 [백그라운드] 슬랙 청소 중 시스템 에러 발생: {e}")

def clear_slack_channel(token, channel_id):
    """채널 청소 스레드를 실행하는 함수 (실행 시점의 타임스탬프 기록)"""
    # 💡 [핵심] 함수가 호출된 현재 시간(Unix Timestamp)을 문자열로 기록
    current_ts = str(time.time())
    
    # 기록된 시간을 스레드의 인자로 전달
    t = threading.Thread(target=_clear_channel_worker, args=(token, channel_id, current_ts))
    t.start()
    print("🚀 슬랙 청소 작업을 백그라운드로 보냈어. (새로 보내는 메시지는 지워지지 않아!)")

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