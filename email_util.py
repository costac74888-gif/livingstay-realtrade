# -*- coding: utf-8 -*-
"""Resend 이메일 발송 헬퍼 (sms_util.py와 같은 패턴).

send_email()은 절대 예외를 위로 던지지 않는다 — 이메일 발송 실패가
알림 생성 등 본 처리 자체를 막으면 안 되기 때문. (ok, message) 튜플 반환.
"""
import os

import requests

RESEND_SEND_URL = "https://api.resend.com/emails"


def send_email(to, subject, html_body):
    """Resend REST API로 이메일 발송. 반환: (ok: bool, message: str). 예외를 던지지 않음."""
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    from_email = os.environ.get("RESEND_FROM_EMAIL", "").strip()
    if not api_key or not from_email:
        return False, "이메일 설정(RESEND_API_KEY/RESEND_FROM_EMAIL)이 등록되지 않아 발송을 건너뜁니다."

    to_addr = (to or "").strip()
    if not to_addr or "@" not in to_addr:
        return False, "수신자 이메일이 없습니다."

    try:
        res = requests.post(
            RESEND_SEND_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": from_email,
                "to": [to_addr],
                "subject": subject,
                "html": html_body,
            },
            timeout=10,
        )
        if res.status_code in (200, 201):
            return True, "발송 성공"
        try:
            detail = res.json().get("message") or res.text
        except Exception:
            detail = res.text
        return False, f"Resend 발송 실패({res.status_code}): {detail}"
    except Exception as e:
        return False, f"이메일 발송 중 오류: {e}"
