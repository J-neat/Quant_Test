# 업데이트날짜: 2026.10.15
# 작성자: j-neat
# 아이폰 앱(PWA) 웹 푸시 알림 전송 모듈
#
# - 아이폰은 iOS 16.4+ 에서 '홈 화면에 추가'한 웹 앱만 푸시를 받을 수 있고, HTTPS 주소여야 함 (Tailscale serve 사용)
# - VAPID 키(푸시 서명용)는 처음 호출 시 data/vapid_private.pem 으로 자동 생성 (data/는 gitignore)
# - 구독 정보는 DB push_subscriptions 테이블, 만료된 구독(404/410)은 자동 삭제

import os
import json
from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid01, b64urlencode
from pywebpush import webpush, WebPushException
from db_manager import DB_PATH, get_push_subscriptions, remove_push_subscription

VAPID_PRIVATE_PATH = os.path.join(os.path.dirname(DB_PATH), "vapid_private.pem")
# 푸시 서비스(애플)가 문제 발생 시 연락할 주소. .env 의 PUSH_CONTACT 로 바꿀 수 있음 (mailto: 또는 https:)
PUSH_CONTACT = os.environ.get("PUSH_CONTACT", "mailto:quant-bot@example.com")

_vapid = None

def _get_vapid():
    global _vapid
    if _vapid is None:
        if os.path.exists(VAPID_PRIVATE_PATH):
            _vapid = Vapid01.from_file(VAPID_PRIVATE_PATH)
        else:
            os.makedirs(os.path.dirname(VAPID_PRIVATE_PATH), exist_ok=True)
            _vapid = Vapid01()
            _vapid.generate_keys()
            _vapid.save_key(VAPID_PRIVATE_PATH)
            print(f"🔑 푸시 알림용 VAPID 키 생성: {VAPID_PRIVATE_PATH}")
    return _vapid

def get_public_key():
    """브라우저 구독 시 필요한 공개키 (base64url)"""
    raw = _get_vapid().public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return b64urlencode(raw)

def send_push_all(title, body, url="/", tag=None):
    """구독한 모든 기기로 푸시 전송. 보낸 개수 반환 (구독이 없거나 실패해도 예외를 던지지 않음)"""
    try:
        subs = get_push_subscriptions()
    except Exception as e:
        print(f"  ⚠️ [푸시] 구독 조회 실패: {e}")
        return 0
    if not subs:
        return 0

    payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag}, ensure_ascii=False)
    _get_vapid()  # 키가 없으면 생성
    sent = 0
    for sub in subs:
        try:
            webpush(
                subscription_info={"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
                data=payload,
                vapid_private_key=VAPID_PRIVATE_PATH,
                vapid_claims={"sub": PUSH_CONTACT},
                ttl=3600,
                timeout=10,
            )
            sent += 1
        except WebPushException as e:
            status = getattr(e.response, "status_code", None)
            if status in (404, 410):
                remove_push_subscription(sub["endpoint"])  # 앱 삭제 등으로 만료된 구독
                print("  🧹 [푸시] 만료된 구독 삭제")
            else:
                print(f"  ⚠️ [푸시] 전송 실패 ({status}): {e}")
        except Exception as e:
            print(f"  ⚠️ [푸시] 전송 실패: {type(e).__name__}: {e}")
    if sent:
        print(f"  📱 [푸시] {sent}개 기기로 알림 전송")
    return sent
