# -*- coding: utf-8 -*-
"""Resend 이메일 발송 헬퍼 (sms_util.py와 같은 패턴).

send_email()은 절대 예외를 위로 던지지 않는다 — 이메일 발송 실패가
알림 생성 등 본 처리 자체를 막으면 안 되기 때문. (ok, message) 튜플 반환.
"""
import os

import requests

RESEND_SEND_URL = "https://api.resend.com/emails"

# 뉴스레터 헤더 로고 — 브랜드가이드 04번 "Black & White On White Background" 버전 고정.
# 이메일 본문에서는 상대경로를 못 쓰므로 운영 서버 절대경로 URL이어야 함.
NEWSLETTER_LOGO_URL = "https://homenstay.com/static/img/logo-black-on-white.png"


def _esc(v, default="-"):
    """HTML 이스케이프 (None이면 default)."""
    if v is None or v == "":
        return default
    return (str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _tx_card_html(tx):
    """실거래 카드 1건. tx는 dict: building_name, deal_type, area_pyeong(또는 area_text),
    price_text, floor, deal_date, avg_price_text(없으면 해당 문구 생략)."""
    name = _esc(tx.get("building_name"))
    deal_type = _esc(tx.get("deal_type"))
    area_text = _esc(tx.get("area_text") or tx.get("area_pyeong"))
    price_text = _esc(tx.get("price_text"))
    floor = _esc(tx.get("floor"))
    deal_date = _esc(tx.get("deal_date"))
    meta = f"{floor}층 · {deal_date}"
    avg = tx.get("avg_price_text")
    if avg:
        meta += f" · 이번달 평균 {_esc(avg)}"
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="border:1px solid #eeeeee;border-radius:8px;margin-bottom:8px;">'
        '<tr><td style="padding:14px 16px;">'
        f'<p style="font-size:14px;font-weight:bold;color:#111111;margin:0 0 6px;">{name}</p>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
        f'<td style="font-size:13px;color:#333333;">{deal_type} {area_text}</td>'
        f'<td style="font-size:13px;color:#333333;font-weight:bold;text-align:right;">{price_text}</td>'
        '</tr></table>'
        f'<p style="font-size:12px;color:#999999;margin:4px 0 0;">{meta}</p>'
        '</td></tr></table>'
    )


def _news_item_html(item):
    """뉴스 아이템 1건. item은 dict: title, url."""
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="border-top:1px solid #f2f2f2;">'
        '<tr><td style="padding:10px 0;">'
        f'<a href="{_esc(item.get("url"), "#")}" '
        f'style="font-size:13px;color:#333333;text-decoration:none;">{_esc(item.get("title"))}</a>'
        '</td></tr></table>'
    )


def _role_cell_html(role_label, info, width_pct):
    """중개/운영 셀 1개. info는 dict: name(상호/이름), detail(연락처 등, 선택)."""
    detail = _esc(info.get("detail"), "")
    detail_html = (f'<p style="font-size:12px;color:#666666;margin:4px 0 0;">{detail}</p>'
                   if detail else "")
    return (
        f'<td width="{width_pct}%" style="padding:4px;" valign="top">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="border:1px solid #eeeeee;border-radius:8px;">'
        '<tr><td style="padding:12px;">'
        f'<p style="font-size:12px;color:#999999;margin:0 0 4px;">{_esc(role_label)}</p>'
        f'<p style="font-size:13px;color:#333333;margin:0;">{_esc(info.get("name"))}</p>'
        f'{detail_html}'
        '</td></tr></table></td>'
    )


def render_newsletter_email(unsubscribe_link, greeting_line,
                            transactions=None, news_items=None,
                            agent_info=None, operator_info=None):
    """뉴스레터형 이메일 HTML 생성 (newsletter_template.html 구조).

    - 섹션(실거래내역/숙박 뉴스레터/중개·운영 정보)은 데이터 없으면 통째로 생략.
    - 전부 없으면 (False, "no content") 반환 → 호출부는 발송을 건너뜀.
    - 있으면 (True, html) 반환.
    - 아웃룩 호환: table 레이아웃 + 인라인 스타일만 사용 (flex/CSS 변수 금지).
    """
    sections = []

    if transactions:
        cards = "".join(_tx_card_html(t) for t in transactions)
        sections.append(
            '<tr><td style="padding:20px 28px 4px;">'
            '<p style="font-size:12px;font-weight:bold;color:#999999;'
            'letter-spacing:.04em;margin:0 0 10px;">실거래내역</p>'
            f'{cards}</td></tr>'
        )

    if news_items:
        items = "".join(_news_item_html(n) for n in news_items)
        sections.append(
            '<tr><td style="padding:12px 28px 4px;">'
            '<p style="font-size:12px;font-weight:bold;color:#999999;'
            'letter-spacing:.04em;margin:0 0 10px;">숙박 뉴스레터</p>'
            f'{items}</td></tr>'
        )

    if agent_info or operator_info:
        width = 50 if (agent_info and operator_info) else 100
        cells = ""
        if agent_info:
            cells += _role_cell_html("중개", agent_info, width)
        if operator_info:
            cells += _role_cell_html("운영", operator_info, width)
        sections.append(
            '<tr><td style="padding:12px 28px 24px;">'
            '<p style="font-size:12px;font-weight:bold;color:#999999;'
            'letter-spacing:.04em;margin:0 0 10px;">중개 · 운영 정보</p>'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
            f'<tr>{cells}</tr></table></td></tr>'
        )

    if not sections:
        return False, "no content"

    html = (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#f4f4f4;padding:24px 0;">'
        '<tr><td align="center">'
        '<table role="presentation" width="520" cellpadding="0" cellspacing="0" '
        'style="background:#ffffff;border-radius:12px;overflow:hidden;'
        "font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif;\">"
        # 헤더 (흰 바탕 + 검정 로고, 세로 28px 기준 비율 유지: 원본 365x56 → 183x28)
        '<tr><td style="padding:24px 28px 16px;border-bottom:1px solid #eeeeee;background:#ffffff;">'
        f'<img src="{NEWSLETTER_LOGO_URL}" alt="HOME &amp; STAY 홈앤스테이" '
        'width="183" height="28" style="display:block;border:0;outline:none;" />'
        f'<p style="margin:12px 0 0;font-size:13px;color:#666666;">{_esc(greeting_line, "")}</p>'
        '</td></tr>'
        + "".join(sections) +
        # 푸터
        '<tr><td style="background:#fafafa;padding:20px 28px;text-align:center;'
        'border-top:1px solid #eeeeee;">'
        '<p style="font-size:12px;color:#999999;margin:0 0 4px;">'
        '<a href="https://homenstay.com" style="color:#999999;text-decoration:underline;">'
        'homenstay.com</a>에서 더 많은 정보를 확인하세요</p>'
        '<p style="font-size:11px;color:#cccccc;margin:0;">© 2026 빌드리머스. 이 메일은 발신 전용입니다.</p>'
        '<p style="font-size:11px;color:#cccccc;margin:6px 0 0;">'
        f'<a href="{_esc(unsubscribe_link, "#")}" style="color:#cccccc;text-decoration:underline;">'
        '이메일 수신 끄기</a></p>'
        '</td></tr>'
        '</table></td></tr></table>'
    )
    return True, html


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
                "from": f"홈앤스테이 <{from_email}>",
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
