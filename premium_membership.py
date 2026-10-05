"""유료 상세정보의 공개 경계. 결제·권한 정책 승인 전에는 모두 잠근다.

계정의 사업장/파트너 역할은 유료 구독이 아니다. 기존 역할 연결을
구독 권한으로 해석하거나 로그인만으로 상세정보를 풀지 않는다.
"""
from flask import jsonify


def membership_access(feature):
    return {
        "required": True,
        "available": False,
        "status": "preparing",
        "feature": feature,
        "info_url": "/membership",
    }


def locked_response(feature):
    response = jsonify(
        ok=False,
        code="MEMBERSHIP_PREPARING",
        message="유료 멤버십 준비 중입니다. 상세정보 열람과 신규 현황조사 신청은 아직 제공되지 않습니다.",
        membership_access=membership_access(feature),
    )
    response.headers["Cache-Control"] = "no-store"
    return response, 403