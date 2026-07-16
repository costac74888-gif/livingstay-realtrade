# -*- coding: utf-8 -*-
"""알리고(aligo.in) SMS 발송 헬퍼.

send_sms()는 절대 예외를 위로 던지지 않는다 — 문자 발송 실패가
회원 승인 등 본 처리 자체를 막으면 안 되기 때문. (ok, message) 튜플 반환.
"""
import os
import re

import requests

ALIGO_SEND_URL = "https://apis.aligo.in/send/"


def send_sms(phone, message):
    """알리고 API로 SMS 발송. 반환: (ok: bool, message: str). 예외를 던지지 않음."""
    api_key = os.environ.get("ALIGO_API_KEY", "").strip()
    user_id = os.environ.get("ALIGO_USER_ID", "").strip()
    sender = re.sub(r"\D", "", os.environ.get("ALIGO_SENDER", ""))
    if not api_key or not user_id or not sender:
        return False, "SMS 설정(ALIGO_API_KEY/ALIGO_USER_ID/ALIGO_SENDER)이 등록되지 않아 발송을 건너뜁니다."

    receiver = re.sub(r"\D", "", phone or "")
    if not receiver:
        return False, "수신자 전화번호가 없습니다."

    try:
        res = requests.post(ALIGO_SEND_URL, data={
            "key": api_key,
            "user_id": user_id,
            "sender": sender,
            "receiver": receiver,
            "msg": message,
        }, timeout=10)
        data = res.json()
        # 알리고 응답: result_code == "1" 이면 성공
        if str(data.get("result_code")) == "1":
            return True, "발송 성공"
        return False, f"알리고 발송 실패: {data.get('message') or data}"
    except Exception as e:
        return False, f"SMS 발송 중 오류: {e}"
