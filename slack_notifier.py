#업데이트날짜: 2026.06.26
#작성자: j-neat
#슬랙 알림 전송 전담 모듈

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import os

#업데이트날짜: 2026.06.26
#작성자: j-neat
#슬랙 알림 전송 전담 모듈

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import os

def clear_slack_channel(token, channel_id):
    """슬랙 채널의 이전 메시지들을 모두 삭제하는 함수"""
    client = WebClient(token=token)
    try:
        print("🧹 슬랙 채널의 이전 메시지들을 싹 지우는 중...")
        # 채널의 최근 메시지 100개 가져오기
        result = client.conversations_history(channel=channel_id, limit=100)
        messages = result["messages"]
        
        for msg in messages:
            try:
                # 메시지 하나씩 삭제
                client.chat_delete(channel=channel_id, ts=msg["ts"])
            except SlackApiError:
                # 봇이 쓴 글이 아니거나 권한이 없는 경우(ex: 시스템 메시지) 패스
                pass
        print("✨ 슬랙 채널 청소 완료!")
    except SlackApiError as e:
        print(f"  ❌ 슬랙 메시지 읽기 에러 (권한을 확인하세요): {e.response['error']}")

def send_quant_signal(token, channel_id, message, image_path=None):
    """슬랙 채널로 텍스트 메시지와 차트 이미지를 전송하는 함수"""
    client = WebClient(token=token)
    
    try:
        # 1. 먼저 추천 종목 정보 텍스트 전송
        client.chat_postMessage(
            channel=channel_id,
            text=message
        )
        print(f"  📢 슬랙 메시지 전송 성공!")
        
        # 2. 저장된 차트 이미지 파일이 있다면 슬랙으로 업로드
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

def send_quant_signal(token, channel_id, message, image_path=None):
    """슬랙 채널로 텍스트 메시지와 차트 이미지를 전송하는 함수"""
    client = WebClient(token=token)
    
    try:
        # 1. 먼저 추천 종목 정보 텍스트 전송
        client.chat_postMessage(
            channel=channel_id,
            text=message
        )
        print(f"  📢 슬랙 메시지 전송 성공!")
        
        # 2. 저장된 차트 이미지 파일이 있다면 슬랙으로 업로드
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