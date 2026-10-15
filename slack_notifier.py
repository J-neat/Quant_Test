# 업데이트날짜: 2026.10.15
# 작성자: j-neat
# 슬랙 알림 전송 전담 모듈 (보관 기간 지난 메시지만 청소)

import os
import requests
import time
import threading
from datetime import datetime
from zoneinfo import ZoneInfo
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

KST = ZoneInfo("Asia/Seoul")
HISTORY_URL = "https://slack.com/api/conversations.history"
DELETE_URL = "https://slack.com/api/chat.delete"

# 💡 슬랙 메시지 보관 기간 (이 기간보다 오래된 봇 메시지만 삭제)
SLACK_RETENTION_DAYS = 7

def _clear_channel_worker(token, channel_id, latest_ts):
    """백그라운드에서 실행될 실제 메시지 삭제 로직 (latest_ts 이전 메시지만 삭제)"""
    print("🧹 [백그라운드] 슬랙 채널 청소 시작... (보관 기간 지난 메시지만)")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        total_deleted = 0
        while True:
            # 💡 latest 파라미터로 보관 기간 이전의 메시지만 불러옴
            params = {
                "channel": channel_id,
                "limit": 100,
                "latest": latest_ts
            }
            res = requests.get(HISTORY_URL, headers=headers, params=params, timeout=10).json()

            if not res.get("ok"):
                print(f"🚨 [백그라운드 에러] 메시지 목록을 불러오지 못했습니다: {res.get('error')}")
                break

            messages = res.get("messages", [])
            if not messages:
                break

            for msg in messages:
                del_data = {
                    "channel": channel_id,
                    "ts": msg["ts"]
                }

                while True:
                    del_res = requests.post(DELETE_URL, headers=headers, json=del_data, timeout=10).json()
                    if del_res.get("error") == "ratelimited":
                        time.sleep(3)
                        continue
                    break

                if del_res.get("ok"):
                    total_deleted += 1
                time.sleep(1.2)

            # 💡 [수정] 삭제 못 하는 메시지(다른 사람 글 등)가 있으면 같은 페이지만 무한 반복하던 문제
            #    → 이번 페이지의 가장 오래된 메시지 이전부터 다시 조회 (latest는 해당 ts 미포함)
            if not res.get("has_more"):
                break
            latest_ts = min(messages, key=lambda m: float(m["ts"]))["ts"]

        print(f"✨ [백그라운드] 슬랙 채널 청소 완료! (총 {total_deleted}개 삭제)")

    except Exception as e:
        print(f"🚨 [백그라운드] 슬랙 청소 중 시스템 에러 발생: {e}")

def clear_slack_channel(token, channel_id, keep_days=SLACK_RETENTION_DAYS):
    """보관 기간(keep_days)보다 오래된 메시지만 삭제하는 청소 스레드 실행"""
    # 💡 [수정] 실행마다 채널 전체를 지우던 방식 → 최근 keep_days일 메시지는 남겨둠
    latest_ts = str(time.time() - keep_days * 86400)

    t = threading.Thread(target=_clear_channel_worker, args=(token, channel_id, latest_ts))
    t.start()
    print(f"🚀 슬랙 청소 작업을 백그라운드로 보냈어. ({keep_days}일 지난 메시지만 삭제)")

def was_posted_today(token, channel_id, text_prefix):
    """오늘(KST 0시 이후) 채널에 text_prefix로 시작하는 메시지가 이미 있는지 확인. 조회 실패 시 False"""
    today_start = datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0)
    headers = {"Authorization": f"Bearer {token}"}
    params = {"channel": channel_id, "oldest": str(today_start.timestamp()), "limit": 200}
    try:
        res = requests.get(HISTORY_URL, headers=headers, params=params, timeout=10).json()
        if not res.get("ok"):
            print(f"⚠️ 슬랙 메시지 조회 실패: {res.get('error')}")
            return False
        return any(m.get("text", "").startswith(text_prefix) for m in res.get("messages", []))
    except Exception as e:
        print(f"⚠️ 슬랙 메시지 조회 실패: {e}")
        return False

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
