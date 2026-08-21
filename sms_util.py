# -*- coding: utf-8 -*-
"""솔라피(SOLAPI) SMS 발송 헬퍼.

send_sms()는 절대 예외를 위로 던지지 않는다 — 문자 발송 실패가
회원 승인 등 본 처리 자체를 막으면 안 되기 때문. (ok, message) 튜플 반환.
"""
import datetime as _datetime
import hashlib
import hmac
import os
import re
import secrets

import requests

SOLAPI_SEND_URL = "https://api.solapi.com/messages/v4/send"


def _solapi_authorization(api_key, api_secret):
    """솔라피 HMAC-SHA256 Authorization 헤더를 만든다."""
    date = _datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    salt = secrets.token_hex(16)
    signature = hmac.new(
        api_secret.encode("utf-8"),
        (date + salt).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return (
        f"HMAC-SHA256 apiKey={api_key}, date={date}, "
        f"salt={salt}, signature={signature}"
    )


def _response_message(data):
    if isinstance(data, dict):
        message = data.get("message") or data.get("statusMessage")
        if message:
            return str(message)
        return str(data)
    return str(data)


def send_sms(phone, message):
    """솔라피 API로 SMS 발송. 반환: (ok: bool, message: str). 예외를 던지지 않음."""
    api_key = os.environ.get("SOLAPI_API_KEY", "").strip()
    api_secret = os.environ.get("SOLAPI_API_SECRET", "").strip()
    sender = re.sub(r"\D", "", os.environ.get("SOLAPI_SENDER", ""))
    if not api_key or not api_secret or not sender:
        return False, "SMS 설정(SOLAPI_API_KEY/SOLAPI_API_SECRET/SOLAPI_SENDER)이 등록되지 않아 발송을 건너뜁니다."

    receiver = re.sub(r"\D", "", phone or "")
    if not receiver:
        return False, "수신자 전화번호가 없습니다."

    try:
        response = requests.post(
            SOLAPI_SEND_URL,
            headers={
                "Authorization": _solapi_authorization(api_key, api_secret),
                "Content-Type": "application/json",
            },
            json={
                "message": {
                    "to": receiver,
                    "from": sender,
                    "text": str(message or ""),
                }
            },
            timeout=10,
        )
        data = response.json()
        message_list = data.get("messageList", {}) if isinstance(data, dict) else {}
        status_codes = {
            str(item.get("statusCode"))
            for item in message_list.values()
            if isinstance(item, dict) and item.get("statusCode") is not None
        }
        if response.ok and (data.get("groupId") or "2000" in status_codes):
            return True, "발송 성공"
        return False, f"솔라피 발송 실패: {_response_message(data)}"
    except Exception as exc:
        return False, f"SMS 발송 중 오류: {exc}"