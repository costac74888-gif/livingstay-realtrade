"""Administrator-only route classification; no provider probes or DB access.

The mapping describes the calls a synchronization action can make, not its
health. Relay configuration and transport telemetry apply to this runtime only.
"""

from datetime import datetime, timezone

from public_api_client import relay_status


# Mixed routes are intentional: classification/geocoding can be conditional.
SECTION_ROUTES = {
    "dsSecOnbid": (("onbid", "온비드", "relay"),),
    "dsSecWeeklyDigest": (
        ("news", "뉴스", "web"), ("email", "이메일", "direct"),
    ),
    "dsSecBrhub": (("bldg_hub", "건축HUB", "relay"),),
    "dsSecBackfillLodging": (
        ("bldg_hub", "건축HUB", "relay"),
        ("kakao", "카카오 주소(필요 시)", "direct"),
    ),
    "dsSecGeo": (("kakao", "카카오 주소", "direct"),),
    "dsSecPhotos": (("tourapi", "TourAPI", "direct"),),
    "dsSecTitle": (("bldg_hub", "건축HUB", "relay"),),
    "dsSecZip": (("juso", "주소·우편번호", "relay"),),
    "dsSecTx": (
        ("rtms", "실거래", "relay"),
        ("bldg_hub", "건축HUB(분류 시)", "relay"),
    ),
    "dsSecTxBackfill": (
        ("rtms", "실거래", "relay"),
        ("bldg_hub", "건축HUB(분류 시)", "relay"),
    ),
    "dsSecBroker": (("brokers", "중개사 표준데이터", "direct"),),
    "dsSecBrokerGeo": (("kakao", "카카오 주소", "direct"),),
    "dsSecRealty": (("stores", "상가정보", "direct"),),
    "dsSecLodgingStaging": (("lodging_csv", "숙박 8종 승인 원장", "file"),),
    "dsSecCampingImages": (("gocamping", "고캠핑", "direct"),),
    "dsSecGocampingWeb": (("gocamping_web", "고캠핑 웹", "web"),),
    "dsSecLodging": (("legacy_lodging", "기존 직접 수집", "disabled"),),
    "dsSecPermits": (("permits", "건축인허가", "direct"),),
    "dsSecReclassify": (("bldg_hub", "건축HUB", "relay"),),
    "dsSecClassificationProvenance": (("database", "저장 근거 점검", "internal"),),
    "dsSecStores": (("stores", "상가정보", "direct"),),
    "dsSecPendingCompletion": (("database", "건물 상태 관리", "internal"),),
    "dsSecBackup": (("database", "데이터 백업", "internal"),),
}


def data_sync_transport_status():
    """One bounded local snapshot shared by the summary and section badges."""
    services = relay_status()
    sections = {}
    for section_id, routes in SECTION_ROUTES.items():
        items = []
        for service, label, mode in routes:
            item = {"service": service, "label": label, "mode": mode}
            if mode == "relay":
                item.update(services[service])
            items.append(item)
        sections[section_id] = {"routes": items}
    return {
        "services": services,
        "sections": sections,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "observation_scope": "current_runtime",
    }
