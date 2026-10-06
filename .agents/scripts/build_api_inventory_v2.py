"""Source-reviewed API inventory; never import the app or call a provider."""
from collections import Counter
from pathlib import Path
from math import ceil
import re
from zipfile import ZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "exports/homenstay_api_inventory_priority_v2_2026-10-06.xlsx"
ROWS = []
P = {0: "P0 우선 확인", 1: "P1 우선 개선", 2: "P2 조건부 개선",
     3: "P3 후순위", 4: "보류·범위 외", 5: "유지"}


def add(id, old, level, name, kind, agency, url, key, code, menu, schedule,
        reason, action, relay="미구현", app="연동 구현", history="운영 미확인", rule="조건부 검토"):
    ROWS.append(dict(id=id, old=str(old), level=level, name=name, kind=kind,
                     agency=agency, url=url, key=key, code=code, menu=menu,
                     schedule=schedule, reason=reason, action=action, relay=relay,
                     app=app, history=history, rule=rule))


def inventory():
    for i, (operation, label, old, schedule) in enumerate([
        ("getBrTitleInfo", "건축HUB 표제부", 1, "정기 건축물대장 월·수·금 / 건축정보 매일 + 수동"),
        ("getBrFlrOulnInfo", "건축HUB 층별개요", 2, "직접 조회 + 건물 분류 배치에서 조건부"),
        ("getBrExposPubuseAreaInfo", "건축HUB 전유공용면적", 3, "직접 조회 / 면적 프리워밍 등 별도 배치"),
        ("getBrJijiguInfo", "건축HUB 지역지구구역", 4, "상세·건축정보 조회 시 조건부"),
    ], 1):
        add(f"HUB-{i}", old, 0, f"{label} · {operation}", "REST API", "국토교통부",
            f"https://apis.data.go.kr/1613000/BldRgstHubService/{operation}",
            "BLD_SERVICE_KEY" + (" / 전국 수집은 DATA_GO_KR_BROKER_API_KEY" if i == 1 else ""),
            "building_registry.py:_get_with_retry; public_api_client.py:SERVICE_PATHS" +
            ("; sync_brhub.py:_fetch_page" if i == 1 else ""),
            "① 건물수집·보완, ③ 건축정보, ⑪ 재분류 / 일부는 상세·별도 면적배치",
            schedule, "기존 핵심 연동을 운영 완료로 단정한 오류부터 정정. 같은 접두어라도 작업별 실검증은 별개.",
            "첫 OFF 게시 확인 → 건축HUB ON 재게시 → 승인된 실요청·공급자 본문 확인 → batch 환경 별도 확인",
            relay="구현(스위치 조건)",
            history="과거 realtime HTTP 200·코드 00 기록 / 현재 운영 미확인" if i == 1 else "개별 실검증·현재 운영 미확인",
            rule="기존 중계 활성화·검증 필요")
    for i, (svc, label, old) in enumerate([
        ("NrgTrade", "상업·업무용 매매", 5), ("RHTrade", "연립·다세대 매매", 6),
        ("SHTrade", "단독·다가구 매매", 7), ("LandTrade", "토지 매매", 8)
    ], 1):
        add(f"RTMS-{i}", old, 0, f"실거래 {label} · {svc}", "REST API", "국토교통부",
            f"https://apis.data.go.kr/1613000/RTMSDataSvc{svc}/getRTMSDataSvc{svc}",
            "RTMS_SERVICE_KEY / DATA_GO_KR_BROKER_API_KEY(대체)",
            "sync_rural_hanok_trades.py; public_api_client.py:SERVICE_PATHS" +
            ("; sync_batch.py; discover_new_buildings.py" if i == 1 else ""),
            "④ 최근 거래·⑤ 과거 백필·신규발굴" if i == 1 else "정기 농어촌민박·한옥 실거래 단계",
            "정기 매일(단계 정의) + Nrg 수동·과거 백필",
            "중계 호출 경로는 4종 구현. 허용 경로·서버 과거 통계만으로 현재 운영 완료 판정 불가.",
            "건축HUB 안정화 후 RTMS ON 재게시 → 서비스별 응답·적재 확인 → 예약 배포 batch 검증",
            relay="구현(스위치 조건)",
            history="과거 batch HTTP 200·코드 000 기록 / 현재 운영 미확인" if i == 1 else "개별 실검증·현재 운영 미확인",
            rule="기존 중계 활성화·검증 필요")
    for i, endpoint in enumerate(["storeListInPnu", "storeListInBuilding"], 1):
        add(f"STORE-{i}", 9, 1 if i == 1 else 2, f"상가정보 · {endpoint}", "REST API",
            "소상공인시장진흥공단", f"https://apis.data.go.kr/B553077/api/open/sdsc2/{endpoint}",
            "STORE_INFO_SERVICE_KEY", "store_info_util.py:_get_with_retry; sync_realty_stores.py; sync_stores.py",
            "⑧ 단지부동산 / ⑫ 상가정보 사전수집 / 상세 상가",
            "PNU: 정기 매일·수동 / Building: 호환 경로·실제 사용량 확인",
            "단지부동산·상가정보의 기존 직접 연동. 같은 정부 호스트라는 이유만으로 장애 확정은 불가.",
            "운영 실패·호출량 확인 → 필요 시 서버·클라이언트 양쪽 경로 추가 → XML·정상 빈 결과 검증",
            rule="우선 중계 후보" if i == 1 else "호환 경로 사용 시 검토")
    add("PERMIT-1", 10, 1, "건축인허가 · getApBasisOulnInfo", "REST API", "국토교통부",
        "https://apis.data.go.kr/1613000/ArchPmsHubService/getApBasisOulnInfo",
        "DATA_GO_KR_BROKER_API_KEY", "sync_permits.py:_fetch_page; scheduled_sync.py:building_permits",
        "⑩ 준공전 건물수집", "정기 화·목·토(매일 아님) + 수동",
        "준공 전 숙박시설 발굴. 코드·화면에 불안정 설명이 있으나 현재 운영 실패는 미점검.",
        "실제 오류·공급자 권한 확인 → 중계 후보 검토 → 서버·클라이언트 개별 서비스 추가",
        rule="우선 중계 후보")
    for i, (svc, endpoint, label) in enumerate([
        ("list", "OnbidRlstListSrvc2/getRlstCltrList2", "물건목록"),
        ("detail", "OnbidRlstDtlSrvc2/getRlstDtlInf2", "물건상세"),
        ("bid", "OnbidCltrBidDtlSrvc2/getCltrBidInf2", "입찰정보"),
        ("notice", "OnbidPbancDtlnfSrvc2/getPbancDtlInf2", "공고상세"),
    ], 1):
        add(f"ONBID-{i}", 15, 1, f"온비드 공매 · {label}", "REST API", "한국자산관리공사",
            "https://apis.data.go.kr/B010003/" + endpoint, "DATA_GO_KR_BROKER_API_KEY",
            f"auction_domain.py:ENDPOINTS[{svc}]; sync_onbid.py:call",
            "온비드 공매 동기화 / 공매 상세", "수동 버튼 있음 / 통합 STAGES에는 없음; 별도 배포·자동 실행 미확인",
            "공매 기능 핵심. 코드상 직접 연동 구현. 과거 승인 대기·옛 서버 호스트 기록을 현재 상태로 단정 금지.",
            "현 승인·권한·운영 수집 결과 확인(승인됐으면 재신청 불필요) → 실패 시 중계 검토 → 4종 별도 검증",
            rule="우선 권한·운영 확인 후 중계 검토")
    add("BROKER-1", 16, 2, "전국 공인중개사사무소 표준데이터", "REST API", "공공데이터포털",
        "https://api.data.go.kr/openapi/tn_pubr_public_med_office_api", "DATA_GO_KR_BROKER_API_KEY",
        "sync_brokers.py; scheduled_sync.py:brokers", "⑥ 인근 중개업소 후보", "정기 매일 + 수동",
        "상가정보 API와 다른 API·호스트. 후보 공급자와 직접 연결 상태를 분리.",
        "운영 오류·한도·권한 확인 후 필요할 때만 별도 호스트 허용·중계 구현", rule="조건부 중계 후보")
    for i, (endpoint, label) in enumerate([
        ("areaBasedList2", "숙박 목록·사진 유무"), ("detailImage2", "다중사진"),
        ("searchKeyword2", "키워드 사진 후보")
    ], 1):
        add(f"TOUR-{i}", 19, 2 if i < 3 else 3, f"TourAPI · {label} · {endpoint}", "REST API",
            "한국관광공사", f"https://apis.data.go.kr/B551011/KorService2/{endpoint}",
            "TOUR_API_SERVICE_KEY",
            ("prewarm_tourapi_metadata.py; backfill_tourapi_images.py" if i == 1 else
             "sync_building_photos.py; backfill_tourapi_images.py" if i == 2 else "sync_building_photos.py"),
            "③ 건물 사진 수집 / 상세 사진",
            "수동·별도 백필 / 통합 STAGES에 TourAPI 단계 없음",
            "사진 품질에 직접 영향. 활용승인 부족과 네트워크 문제를 분리해야 함.",
            "KorService2 권한·실패·호출 예산 확인 → 연결 장애일 때 중계 검토; 정상 코드·사진 보존 검사",
            rule="조건부 중계 후보")
    add("MAINT-1", "추가", 2, "건축물 유지관리 · getMaintenanceHistory", "REST API", "국토교통부",
        "https://apis.data.go.kr/1613000/MtnChkHubService/getMaintenanceHistory",
        "BLD_INSPECTION_SERVICE_KEY", "building_registry.py:fetch_maintenance_history",
        "건물 상세 건축정보 확인(관련 기능)", "직접 조회 시 조건부 / 통합 전용 단계 없음",
        "원본 누락. 별도 점검키는 지역지구가 아니라 이 API에서 사용.",
        "공급자 활용권한·실패 확인 후 필요 시 별도 서비스로 중계; 건축HUB ON만으로 경유되지 않음",
        rule="조건부 중계 후보")
    add("RONE-1", 17, 2, "R-ONE 임대수익 기준 · SttsApiTblData", "REST API", "한국부동산원",
        "https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do", "RONE_API_KEY",
        "sync_rone_rental_benchmarks.py; scheduled_sync.py:rone_rental",
        "정기 R-ONE 임대수익 기준 / 분석 벤치마크", "정기 매주 월(수동 전용 아님)",
        "숙박자산 분석 기준. 중계 부재와 앱 미연동은 다름.",
        "주간 운영 결과·공급자 오류 확인; 반복 연결 장애가 있을 때만 별도 중계 검토")
    add("JUSO-1", 18, 2, "도로명주소·우편번호 검색", "REST API", "행정안전부",
        "https://business.juso.go.kr/addrlink/addrLinkApi.do\n대체: https://www.juso.go.kr/addrlink/addrLinkApi.do",
        "JUSO_API_KEY", "address_utils.py; app.py:_zip_backfill_auto_loop",
        "③-① 우편번호 자동채움 / 주소 정규화", "앱 내부 자동 루프 / 예약 배포 동작과 구분",
        "주소 매칭·우편번호 기존 연동. 기본 호스트 누락 수정.",
        "자동 채움 실행 결과 확인; 오류가 반복될 때만 공급자·대체 경로 및 중계 검토")
    for i, endpoint in enumerate(["basedList", "imageList"], 1):
        add(f"CAMP-{i}", 21, 2, f"고캠핑 API · {endpoint}", "REST API", "한국관광공사",
            f"https://apis.data.go.kr/B551011/GoCamping/{endpoint}", "LODGING_SERVICE_KEY",
            "sync_lodgings.py:main, fetch_camping_list/fetch_camping_images; scheduled_sync.py:camping",
            "캠핑 다중사진 이어서 수집 / 정기 캠핑",
            "basedList: 정기 매일; imageList: 수동·캠핑 수집 조건부",
            "고캠핑 전용 실행은 legacy 숙박 종료 후에도 허용. 캠핑을 숙박 종료와 같이 차단한다고 해석하지 않음.",
            "운영 성공·사진 누락·공유 한도 확인 → 필요 시 별도 중계 추가; 데이터랩과 숙박 통계 분리",
            rule="조건부 중계 후보")
    add("CAMP-WEB", 22, 3, "고캠핑 공개 웹 목록·상세", "웹 수집", "한국관광공사",
        "https://gocamping.or.kr/bsite/camp/info/", "없음",
        "backfill_gocamping_web.py; scheduled_sync.py:gocamping_web", "고캠핑 데이터 동기화",
        "정기 매주 일 + 수동(수동 전용 아님)",
        "이미 웹 수집 구현. 공식 GoCamping REST와 다른 경로.",
        "원본 총계·파싱 건수·이름+주소 유일성 확인; REST 허용목록 일괄 확장 금지",
        rule="웹 수집 별도 검토")
    for i, (path, name, code, menu) in enumerate([
        ("search/address.json", "주소검색", "geocode_buildings.py; geocode_brokers.py; app.py",
         "② 건물 좌표 / ⑦ 중개업소 좌표"),
        ("search/keyword.json", "키워드검색", "import_tourism_stats.py; app.py",
         "관광통계 장소 보정 / 관련 건물 검색"),
        ("search/category.json", "카테고리검색", "app.py:_KAKAO_LOCAL_CATEGORY_URL", "인근 상가 등 관련 기능"),
        ("geo/coord2regioncode.json", "좌표→행정구역", "import_tourism_stats.py", "관광통계 장소·지역 보정"),
    ], 1):
        add(f"KAKAO-{i}", 25, 5, f"카카오 로컬 · {name}", "REST API", "카카오",
            "https://dapi.kakao.com/v2/local/" + path, "KAKAO_REST_API_KEY", code, menu,
            "주소: 정기 매일·수동 / 나머지 해당 기능·수입 작업 조건부",
            "정부 API 중계 전환 범위 밖의 기존 직접 연동.",
            "기존 직접 연결 유지; 실제 반복 장애·한도 초과가 있을 때 별도 검토",
            relay="전환 범위 밖", rule="현재 중계 추가 불필요")
    for i, endpoint in enumerate(["streetview", "streetview/metadata"], 1):
        add(f"GOOGLE-{i}", 26, 5, f"Google Street View · {'이미지' if i == 1 else '메타데이터'}",
            "REST API", "Google", "https://maps.googleapis.com/maps/api/" + endpoint,
            "GOOGLE_MAPS_API_KEY", "sync_building_photos.py; app.py:_google_streetview_metadata",
            "관련 건물 사진·상세 보조", "직접 조회·사진 수집 조건부",
            "TourAPI 사진 부재 등 조건이 있는 보조 서비스; 관리자 TourAPI 버튼이 항상 호출하는 것은 아님.",
            "기존 직접 조회 유지; 도메인·결제·쿼터는 별도 확인", relay="전환 범위 밖",
            rule="현재 중계 추가 불필요")
    add("VWORLD-1", 24, 3, "브이월드 WMS 건물 지도 이미지", "지도 API", "브이월드",
        "https://api.vworld.kr/req/wms", "VWORLD_API_KEY", "sync_building_photos.py",
        "관련 건물 사진 보조", "사진 수집·관련 요청 조건부",
        "정부 도메인이나 독립 서비스. 기존 문서의 Replit발 접속 제약 이력은 현재 검사 결과 아님.",
        "공급자 접속 정책·허용 출처 확인 후 필요 시 별도 중계 검토")
    add("VWORLD-PC", 24, 4, "브이월드 공인중개사사무소 · getEBOfficeInfo", "수동 PC API", "브이월드",
        "https://api.vworld.kr/ned/data/getEBOfficeInfo", "VWORLD_API_KEY",
        "vworld_broker_fetch.py", "PC 수동 수집 스크립트(관리자 버튼 아님)", "수동 PC 전용",
        "운영 관리자 자동 연결과 구분해야 함.", "운영 API 연결 완료로 세지 않음",
        app="수동 스크립트", relay="전환 범위 밖", rule="운영 전환 보류")
    for i, (name, url) in enumerate([
        ("문체부 RSS", "https://www.mcst.go.kr/common/rss/rssGenXml.jsp?pMenuCD=0302000000"),
        ("관광공사 보도자료", "https://knto.or.kr/pressRelease?srchText=%EC%88%99%EB%B0%95"),
        ("숙박매거진 RSS", "https://www.sukbakmagazine.com/rss/allArticle.xml"),
        ("호텔앤레스토랑 RSS", "https://www.hotelrestaurant.co.kr/rss/allArticle.xml")
    ], 1):
        add(f"NEWS-{i}", 20, 3, name, "웹/RSS", "공개 뉴스 공급자", url, "없음",
            "weekly_digest_news.py", "주간 이메일 콘텐츠", "주간 콘텐츠 구성 시(캐시·원본 상황에 따라 호출)",
            "정부 업무 데이터 REST API가 아닌 콘텐츠 수집.",
            "실패 소스·빈 상태 확인; 발송과 뉴스 수집을 분리, 별도 웹 정책 검토", rule="웹 수집 별도 검토")
    add("DATALAB-LINK", 23, 4, "관광데이터랩 공식 자료 안내", "안내 링크", "한국관광공사",
        "https://datalab.visitkorea.or.kr/datalab/portal/getMetaInfoList.do", "없음",
        "tourism_datalab_admin.py:OFFICIAL_UPDATE_GUIDE_URL", "관광통계 관리",
        "외부 API 자동 수집 아님", "코드에서는 공식 안내 URL이며 이 상수만으로 웹/API 수집 구현 판정 불가.",
        "안내 링크와 업로드·정기 자료 반영을 분리", app="안내 링크만", relay="해당 없음",
        history="API 검증 해당 없음", rule="API 중계 대상 아님")
    add("DATALAB-FILE", "추가", 2, "월간 관광 방문자 승인 원본", "승인 파일/저장소", "한국관광공사 원본·승인 저장소",
        "TOURISM_DATALAB_MONTHLY_MANIFEST_URL(설정 시 같은 HTTPS origin)\n기본: Object Storage 승인 manifest·ZIP",
        "공공 API 인증키 없음 / 저장소 인증은 기존 storage_util", "sync_tourism_monthly.py:fetch_approved_source",
        "정기 월간 관광 시군구 방문자 / 관광통계 관리", "정기 매주 월",
        "원본 누락. DataLab API 자동 조회가 아니라 승인 파일 다운로드·해시 검증·DB 반영.",
        "승인 manifest·자료기간·해시·실제 정기 실행 확인; 불명확한 호스트를 정부 API로 추가 금지",
        relay="해당 없음", rule="파일 경로 점검(중계 아님)")
    add("GOV-CSV8", 11, 1, "정부 숙박 8종 CSV staging·승인·promotion", "CSV/DB(8종)",
        "정부 허가원장", "업로드 CSV → 개발 staging·승인 → 운영 promotion",
        "외부 API 키 없음", "lodging_data_contract.py; lodging_staging.py; lodging_promotion.py; apply_lodging_promotion.py",
        "⑨-A 정부 숙박 8종 staging·승인 / 정기 숙박 승인 원장 반영",
        "업로드·승인 수동 / 승인 원장 promotion 정기 매일",
        "사업자 현황의 현재 정규 경로는 API가 아닌 승인 원장. 직접수집과 병행 전환은 원장 경합 위험.",
        "개발 승인·dry-run·운영 반영 상태 확인; 중계 구현 대신 원본 최신성·promotion 점검",
        relay="해당 없음", rule="승인 파일 경로 점검")
    for i, (name, endpoint, old, key, code) in enumerate([
        ("일반·생활 숙박업", "lodgings", 11, "DATA_GO_KR_BROKER_API_KEY", "sync_lodgings.py:main"),
        ("농어촌민박업", "rural_homestays", 12, "LODGING_SERVICE_KEY / DATA_GO_KR_BROKER_API_KEY", "sync_rural_hanok.py:main"),
        ("한옥체험업", "hanok_experience", 13, "LODGING_SERVICE_KEY / DATA_GO_KR_BROKER_API_KEY", "sync_rural_hanok.py:main"),
        ("관광펜션업", "tourist_pensions", 14, "LODGING_SERVICE_KEY / DATA_GO_KR_BROKER_API_KEY", "sync_rural_hanok.py:main"),
    ], 1):
        add(f"LEGACY-{i}", old, 4, f"기존 직접수집 · {name}", "REST API(legacy)",
            "행정안전부", f"https://apis.data.go.kr/1741000/{endpoint}/info", key,
            code + "; legacy_lodging_gate.py; scheduled_sync.py",
            "⑨-B 기존 직접 동기화(종료) / legacy 정기 단계",
            "정기 정의 매일이나 종료 게이트로 skip 가능; 현재 DB 플래그 미조회",
            "경로 존재 ≠ 현재 실제 실행. 기본 fail-open 게이트이므로 DB enabled=False 여부도 중요.",
            "종료 승인·DB 제어값·실제 skip 확인부터. 비상복구 승인 전 재활성화·일괄 중계 금지",
            app="구현(종료 게이트)", history="UI 종료 표시 / 현재 DB 플래그·실행 미확인",
            rule="정상 운영 전환 보류")
    for id, name, agency, url, key, code in [
        ("MAIL-1", "Resend 이메일 발송", "Resend", "https://api.resend.com/emails",
         "RESEND_API_KEY / RESEND_FROM_EMAIL", "email_util.py; weekly_digest.py"),
        ("SMS-1", "Solapi 문자 발송", "Solapi", "https://api.solapi.com/messages/v4/send",
         "SOLAPI_API_KEY / SOLAPI_API_SECRET / SOLAPI_SENDER", "sms_util.py"),
        ("AUTH-1", "카카오 로그인 인증 시작", "카카오", "https://kauth.kakao.com/oauth/authorize",
         "KAKAO_REST_API_KEY", "app.py:_KAKAO_AUTHORIZE_URL"),
        ("AUTH-2", "카카오 로그인 토큰 발급", "카카오", "https://kauth.kakao.com/oauth/token",
         "KAKAO_REST_API_KEY / KAKAO_CLIENT_SECRET", "app.py:_KAKAO_TOKEN_URL"),
        ("AUTH-3", "카카오 로그인 사용자 정보", "카카오", "https://kapi.kakao.com/v2/user/me",
         "OAuth access token(실제 값 미기재)", "app.py:_KAKAO_USERME_URL"),
    ]:
        add(id, 27, 4, name, "발송/인증 API", agency, url, key, code,
            "주간 이메일·회원 알림·로그인(관련 서비스)", "발송·로그인 이벤트별 / 이메일 주간",
            "데이터 수집 API와 구분. 이메일은 실제 외부 API를 쓰므로 'API 아님'이라고 하지 않음.",
            "기존 발송·인증 경로 유지; 공공 API 중계 목록에 넣지 않음",
            relay="전환 범위 밖", rule="데이터 동기화 전환 대상 아님")


def menu_map():
    # All 24 identified section IDs in the actual showDataSync template.
    return [
        ("dsSecOnbid", "온비드 공매 동기화", "ONBID-1~4", "공급자 REST API", "운영 작업", "sync_onbid.py / 직접 호출", "4종 코드 구현; 현 권한·운영 성공 미확인"),
        ("(ID 없음)", "공매 현황조사 운영", "없음", "내부 설정·신청 관리", "관리 링크", "관리 화면으로 이동", "데이터 수집 API 아님"),
        ("dsSecWeeklyDigest", "주간 이메일 전체 발송", "NEWS-1~4, MAIL-1", "웹/RSS + 발송 API + 내부 DB", "실제 발송", "weekly_digest.py / weekly_digest_news.py", "뉴스 수집과 이메일 API 분리; 회원 데이터는 DB"),
        ("dsSecBrhub", "① 건물수집 / 과거 구간 재수집", "HUB-1", "건축HUB 표제부", "운영", "sync_brhub.py", "버튼 자체는 NrgTrade가 아니라 표제부 전수 수집"),
        ("(별도 코드)", "신규 건물 발굴", "RTMS-1, HUB-1~2", "실거래 + 건축 분류", "관련 별도 배치", "discover_new_buildings.py", "① 건물수집 버튼과 혼동 금지"),
        ("dsSecBackfillLodging", "① 보완 영업신고 누락건물 등록", "HUB-1~2, KAKAO-1(주소 처리 시)", "저장 신고 + 건축HUB 등", "운영", "backfill_from_lodging_registry.py", "원장 파일 검증·promotion과 다른 건물 보완 작업"),
        ("dsSecBackfillLodging", "기타→키워드 / 영업신고 소급 재분류", "없음", "내부 DB·키워드", "운영", "app.py:admin_reclassify_lodging_keywords/admin_reclassify_by_hygiene", "⑪ 미분류 재분류와 구분"),
        ("dsSecGeo", "② 지도 좌표 채우기", "KAKAO-1", "REST API", "운영", "geocode_buildings.py", "기존 직접 연동"),
        ("dsSecPhotos", "③ 건물 사진 유무 / 숙박사진 이어서", "TOUR-1~2", "REST API", "운영", "prewarm_tourapi_metadata.py / backfill_tourapi_images.py", "이 두 버튼이 Google·Vworld를 항상 호출하는 것은 아님"),
        ("(관련 상세)", "건물 사진 보조 경로", "TOUR-3, GOOGLE-1~2, VWORLD-1", "보조 API", "관련 상세·별도 코드", "sync_building_photos.py / app.py", "관리자 사진 버튼의 직접 호출과 분리"),
        ("dsSecTitle", "③ 건축정보 채우기", "HUB-1~2(대표), HUB-3~4·MAINT-1(관련 조회)", "건축HUB API", "운영", "backfill_title_info.py / building_registry.py", "표제부 배치와 상세·면적·점검 API 용도를 구분"),
        ("dsSecZip", "③-① 우편번호 자동채움", "JUSO-1", "REST API", "자동·수동 버튼 없음", "app.py:_zip_backfill_auto_loop / address_utils.py", "자동 루프 기동·처리 현황은 운영 별도 확인"),
        ("dsSecTx", "④ 실거래 동기화", "RTMS-1, HUB-1~2(분류 조건부)", "실거래 API", "운영", "sync_batch.py", "최근 거래·확실한 건물 연결"),
        ("dsSecTxBackfill", "⑤ 과거 데이터 백필", "RTMS-1, HUB-1~2(분류 조건부)", "실거래 API", "운영·대량", "sync_batch.py(장기 범위)", "일상 갱신과 별개; 자동 실행 지시 아님"),
        ("dsSecBroker", "⑥ 인근 중개업소 후보", "BROKER-1", "REST API", "운영", "sync_brokers.py", "api.data.go.kr 단수 호스트"),
        ("dsSecBrokerGeo", "⑦ 중개업소 좌표", "KAKAO-1", "REST API", "운영", "geocode_brokers.py", "기존 직접 연동"),
        ("dsSecRealty", "⑧ 단지부동산(상가정보)", "STORE-1", "REST API", "운영", "sync_realty_stores.py / store_info_util.py", "상가 사전수집과 같은 키·예산 공유"),
        ("dsSecLodgingStaging", "⑨-A 정부 숙박 8종 staging·승인", "GOV-CSV8", "CSV·DB", "개발 전용", "lodging_staging.py / lodging_promotion.py", "이 화면에 운영 반영 버튼·공급자 실호출 없음"),
        ("dsSecCampingImages", "캠핑 다중사진 이어서", "CAMP-2", "REST API", "운영", "sync_lodgings.py --update-images-only", "legacy 종료 게이트 예외; 고캠핑 예산 공유"),
        ("dsSecGocampingWeb", "고캠핑 데이터 동기화", "CAMP-WEB", "공개 웹 수집", "운영", "backfill_gocamping_web.py", "정기 일요일 + 수동, REST API와 별개"),
        ("dsSecLodging", "⑨-B 기존 직접 동기화·파일 가져오기", "LEGACY-1~4", "legacy API·구 파일", "사용 중지·비상복구", "sync_lodgings.py / sync_rural_hanok.py / legacy_lodging_gate.py", "현재 DB enabled 값 미확인; 버튼 잠김과 스케줄 skip 구분"),
        ("dsSecPermits", "⑩ 준공전 건물수집", "PERMIT-1", "REST API", "운영", "sync_permits.py", "정기 화·목·토; 매일 아님"),
        ("dsSecReclassify", "⑪ 미분류 건물 재분류", "HUB-1~2", "외부 건축HUB API", "운영", "reclassify_unclassified.py:classify_lodging_building", "원본의 외부 API 없음은 오류"),
        ("dsSecClassificationProvenance", "⑫ 법정분류 근거 점검", "없음", "저장 근거·신고 DB", "운영", "app.py:admin_lodging_classification_provenance", "새 공급자 실호출 없이 근거 복원"),
        ("dsSecStores", "⑫ 상가정보 사전수집", "STORE-1", "REST API", "운영", "sync_stores.py / store_info_util.py", "PNU 기반; 단지부동산과 공유 예산"),
        ("dsSecPendingCompletion", "완공 대기 / 오염 건물 정리", "없음(직접 목록·전환·정리)", "내부 DB", "운영·삭제 주의", "app.py:admin_pending_completion / 건물 PUT / 정리 라우트", "별도 건축정보 검증과 목록·상태변경을 분리"),
        ("dsSecBackup", "데이터 백업", "없음(공공 API)", "DB·파일", "접속 환경 DB", "app.py:관리자 backup 라우트", "API 수집 작업 아님"),
        ("(정기)", "농어촌민박·한옥 실거래", "RTMS-1~4", "REST API", "정기 매일", "scheduled_sync.py:rural_hanok_trades", "legacy 신고 수집 종료와 실거래 단계를 혼동 금지"),
        ("(정기)", "숙박 승인 원장 자동 반영 / 병행 비교", "GOV-CSV8", "DB 승격·비교", "정기 매일", "apply_lodging_promotion.py / compare_lodging_parallel.py", "공급자 실호출 대신 승인 staging·운영 DB 처리"),
        ("(정기)", "월간 관광 / R-ONE 임대수익", "DATALAB-FILE, RONE-1", "승인 파일 + REST API", "정기 매주 월", "sync_tourism_monthly.py / sync_rone_rental_benchmarks.py", "파일 수집과 기관 API 구분"),
        ("(관련 메뉴)", "관광통계 관리·장소 보정", "DATALAB-LINK, KAKAO-2~4", "안내링크·업로드·카카오 API", "수동 관리", "tourism_datalab_admin.py / import_tourism_stats.py", "관광데이터랩 링크를 수집 API로 세지 않음"),
    ]


CORRECTIONS = [
    ("원본 API 1~3·5~8 / 요약", "중계 연결됨·완료", "코드 구현(조건부), 현재 운영 검증 미확인",
     "public_api_client.py / docs/public_api_relay_verification.md", "허용 목록·과거 호출·스위치·실제 게시 검증을 분리"),
    ("원본 API 4", "지역지구는 BLD_INSPECTION_SERVICE_KEY, 중계 확인필요", "BLD_SERVICE_KEY; _get_with_retry→public_api_get 경로 구현",
     "building_registry.py:fetch_jijigu_rows", "별도 점검키는 유지관리 이력 API에서 사용"),
    ("원본 API 1·5", "오늘 batch 487·844 등 서버 통계로 완료", "첨부의 과거 통계 주장(이번에 원장 미검증); 현재 운영 완료 근거로 사용 안 함",
     "첨부 원본 / docs/public_api_relay_verification.md", "통계 날짜·서비스·용도·환경별 범위 확인 필요"),
    ("원본 메뉴 ①", "전국 건물수집 버튼 = Nrg+HUB", "실제 버튼은 sync_brhub의 건축HUB 표제부; 별도 신규발굴만 Nrg 사용",
     "static/admin.html:showDataSync / sync_brhub.py / discover_new_buildings.py", "화면 버튼과 별도 배치 분리"),
    ("원본 메뉴 ⑪·⑫", "미분류 재분류·근거 점검 모두 내부 DB", "⑪ 건축HUB 호출 / ⑫ 법정분류 근거 복원은 저장 DB",
     "reclassify_unclassified.py / app.py:admin_lodging_classification_provenance", "작업을 합쳐 외부호출 없음으로 표시하지 않음"),
    ("원본 API 11~14·메뉴 ⑨", "staging 외부경로 확인필요; 1741000 일괄 중계", "8종 CSV·DB 승인 경로와 종료 게이트 legacy API 분리",
     "lodging_staging.py / lodging_data_contract.py / legacy_lodging_gate.py", "정상 승인 원장을 우선; 비상 경로 무승인 재활성화 금지"),
    ("원본 API 10 / 작업 순서", "인허가 매일 호출·긴급 확정", "정기 정의 화·목·토; 실제 장애 확인 후 우선 중계 후보",
     "scheduled_sync.py:building_permits", "도메인 같음만으로 같은 장애 확정 불가"),
    ("원본 API 15·온비드 매핑", "활용신청 4종 승인 대기 / 서버 옛 호스트", "4종 직접 호출 코드 있음; 현 승인·서버 설정·운영 성공 미확인",
     "auction_domain.py:ENDPOINTS / sync_onbid.py:call", "과거 기록을 현재 미승인 판정으로 사용 금지"),
    ("원본 API 17", "R-ONE 수동·월간, 자동 여부 확인필요", "정기 매주 월 단계 구현", "scheduled_sync.py:rone_rental", "게시·실제 실행 성공은 별도 확인"),
    ("원본 API 22", "고캠핑 웹 수동만", "정기 매주 일 + 수동", "scheduled_sync.py:gocamping_web", "공공 API가 아닌 웹 수집"),
    ("원본 API 21·legacy", "기존 숙박 종료와 캠핑 수집 혼동 가능", "--camping / --update-images-only는 legacy 게이트 예외",
     "sync_lodgings.py:main", "GoCamping 지속 수집은 승인 숙박 원장과 다른 공급원"),
    ("원본 API 18", "JUSO www 호스트만", "business.juso.go.kr 기본 + www.juso.go.kr 대체", "address_utils.py", "주소·우편번호 자동 루프와 공급자 호출 분리"),
    ("원본 API 23", "관광데이터랩 메타정보 웹 수집", "해당 URL은 공식 안내 상수; 월간 자동 반영은 승인 manifest·ZIP",
     "tourism_datalab_admin.py / sync_tourism_monthly.py", "안내 링크·파일 경로를 API로 집계하지 않음"),
    ("원본 API 19·사진 매핑", "TourAPI·Google·Vworld를 사진 버튼 한 항목", "목록·이미지 관리자 버튼과 상세·별도 보조 경로 분리",
     "static/admin.html / prewarm_tourapi_metadata.py / backfill_tourapi_images.py", "실제 함수·명령별 사용 경로 확인"),
    ("원본 전체 목록", "유지관리 이력·월간 승인 원본 누락", "유지관리 API·월간 파일 경로 추가; 복수 API는 경로별 분리",
     "building_registry.py / sync_tourism_monthly.py", "정부 CSV8종은 별도 시트에 모두 명시"),
    ("원본 메뉴 주간 이메일", "API 아님", "뉴스는 웹/RSS, 발송은 Resend API, 개인별 정보는 DB",
     "weekly_digest_news.py / email_util.py / weekly_digest.py", "발송/인증은 공공 데이터 중계 범위 밖"),
    ("원본 작업 순서", "서버 지시문 번호·권한 수정 필수·일괄 전환", "독립 실행 가능한 확인 단계·백업·최소권한·개별 검증 순서",
     "docs/public_api_relay_operations.md / 검토 원칙", "서버 원본 미검증; 도메인 전체 허용·무조건 재설치 금지"),
    ("원본 우선순위", "미중계=미연결, 완료·제외를 긴급도와 혼합", "앱 코드·중계 코드·운영 검증·조치 우선순위를 별도 열로 분리",
     "이번 v2 분류 기준", "우선순위는 운영 영향·기존 구현·관찰된 근거 중심의 검토 권고"),
]


def weighted(s):
    return sum(2 if ord(c) > 127 else 1 for c in str(s or ""))


def sheet(wb, title, headers, data, widths, table=True):
    ws = wb.create_sheet(title)
    ws.append(headers)
    for row in data:
        ws.append(row)
    ws.freeze_panes = "E2" if title in ("API 전체 목록", "상세·근거") else "B2"
    ws.sheet_view.showGridLines = False
    for i, width in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = width
    border = Border(bottom=Side(style="hair", color="DCE4EA"))
    for row in ws:
        for c in row:
            c.font = Font(name="맑은 고딕", size=10, color="243746")
            c.alignment = Alignment(vertical="top", wrap_text=True)
            c.border = border
        ws.row_dimensions[row[0].row].height = max(30, min(190, 15 * max(
            ceil(weighted(c.value) / max(widths[c.column - 1] - 2, 1))
            + str(c.value or "").count("\n") for c in row
        ) + 10))
    for c in ws[1]:
        c.font = Font(name="맑은 고딕", size=10, bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="244A5B")
    ws.row_dimensions[1].height = 36
    if table and data:
        tab = Table(displayName=f"T{len(wb.worksheets)}", ref=ws.dimensions)
        tab.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
        ws.add_table(tab)
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A3
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_title_rows = "1:1"
    ws.print_options.horizontalCentered = True
    ws.oddFooter.center.text = "홈앤스테이 API 현황 v2 · 2026-10-06 | &P / &N"
    ws.print_area = ws.dimensions
    return ws


def main():
    inventory()
    family_order = ["HUB", "RTMS", "STORE", "PERMIT", "ONBID", "GOV", "TOUR",
                    "BROKER", "MAINT", "RONE", "JUSO", "CAMP", "DATALAB",
                    "VWORLD", "NEWS", "LEGACY", "MAIL", "SMS", "AUTH", "KAKAO", "GOOGLE"]
    ROWS.sort(key=lambda r: (
        r["level"], family_order.index(r["id"].split("-")[0]), r["id"]
    ))
    for n, row in enumerate(ROWS, 1):
        row["order"] = n
    wb = Workbook()
    wb.remove(wb.active)
    priority = Counter(P[r["level"]] for r in ROWS)
    kinds = Counter(r["kind"] for r in ROWS)
    relay_count = sum(r["relay"] == "구현(스위치 조건)" for r in ROWS)
    summary = [
        ("문서", "홈앤스테이 API 연결현황·우선순위 v2", ""),
        ("검토 기준", "2026-10-06 / 첨부 4개 시트의 27개 분류 및 현재 코드 대조", ""),
        ("대상 범위", "관리자 데이터 동기화 메뉴 + 관련 정기 단계 + 원본의 상세·발송·인증·PC 보조 경로", ""),
        ("검증 한계", "운영 앱 로그인 화면·실행 중 스위치·운영 DB·중계서버 통계·공급자 실호출은 이번에 점검하지 않음", ""),
        ("앱 연결의 의미", "연동 구현 = 코드상 호출부 존재. 현재 운영 성공·활용승인·토큰 유효성 보장 아님", ""),
        ("중계 연결의 의미", "구현(스위치 조건) = 클라이언트 경유 구현. 서버 허용·게시·실행·공급자 정상 응답 확인은 별도", ""),
        ("핵심 결론 1", "건축HUB 4개 + 실거래 4개는 중계 코드 구현됨. 완료가 아니라 P0 운영 검증 대상으로 수정", ""),
        ("핵심 결론 2", "상가정보 PNU·건축인허가 우선 중계 후보. 온비드는 현 권한·운영 결과 확인 후 전환 검토", ""),
        ("핵심 결론 3", "정부 숙박 8종은 CSV→개발 승인→운영 promotion. 종료 legacy API를 긴급 일괄 연결하지 않음", ""),
        ("핵심 결론 4", "모든 동기화가 공급자 API 호출은 아님. 웹/RSS·파일·DB·안내링크·발송 API를 구분", ""),
        ("운영 검증 원칙", "관리자 중계 상태는 해당 실행 환경 임시 기록. 2xx만으로 파싱·DB 적재·배치 완료 판정 불가", ""),
        ("이 파일에서 한 작업", "파일·코드 읽기 및 엑셀 생성만 수행. API 호출·DB 변경·토큰 조회·게시·스케줄 변경 없음", ""),
        ("목록 총계", len(ROWS), "공급자 수가 아닌 관리 경로 수; 비API·보조 경로 포함"),
        ("중계 코드 구현", relay_count, "건축HUB 4 + 실거래 4; 현재 운영 완료 건수 아님"),
        ("새 API 구현 필요", 0, "원본의 업무 API는 이미 직접 호출 코드 있음. 중계 추가 필요성과 앱 미연동을 구분"),
        ("현재 운영 성공 확정", "미판정", "미확인 ≠ 실패. 이번 검토에 실호출·운영 원장 확인 없음"),
    ] + [(name, count, "검토 시점 스냅샷") for name, count in priority.items()] + [
        ("분류 · " + name, count, "경로 단위") for name, count in kinds.items()
    ] + [
        ("P0", "기존 중계 경로의 운영 검증부터", "도메인/과거 통계만으로 완료 판정 금지"),
        ("P1", "핵심 데이터 수집의 권한·장애·원본 경로 우선 개선", "우선순위는 권고이며 장애 확정·실행 승인이 아님"),
        ("P2", "반복 장애·데이터 공란 등 근거가 있을 때 전환 검토", "정상 직접 연동이면 유지"),
        ("P3", "보조 웹·사진 등 후순위 검토", "중계 방식도 REST와 분리"),
        ("보류·범위 외", "종료 legacy·안내·수동 PC·발송·인증", "복구·신규 전환은 별도 승인"),
        ("유지", "현재 공공 API 중계 확대 범위 밖의 기존 직접 연동", "상용·해외라는 이유만으로 장애 가능성까지 부정하지 않음"),
        ("사용법", "API 전체 목록에서 우선순위·중계코드·운영검증 필터. ID로 상세·메뉴 연결", "요약 건수는 검토 시점 고정값; 목록 수정 후 자동 갱신 아님"),
    ]
    sheet(wb, "요약", ["구분", "검토 결과", "설명"], summary, [26, 100, 63])
    main_rows = [
        (r["id"], r["order"], P[r["level"]], r["name"], r["kind"], r["app"],
         r["relay"], r["history"], r["rule"], r["action"], r["reason"])
        for r in ROWS
    ]
    ws = sheet(wb, "API 전체 목록",
               ["ID", "검토순서", "우선순위", "API / 데이터 경로", "종류", "앱 연결(코드)",
                "중계 연결(코드)", "현재 운영 검증", "연결 필요 판정", "다음 조치", "우선순위·판정 이유"],
               main_rows, [18, 11, 20, 45, 22, 24, 25, 47, 32, 62, 62])
    colors = {0: "FCE4D6", 1: "FFF2CC", 2: "E2EFF9", 3: "F2F4F7", 4: "E8E8E8", 5: "E2F0D9"}
    for n, r in enumerate(ROWS, 2):
        for col in (2, 3):
            ws.cell(n, col).fill = PatternFill("solid", fgColor=colors[r["level"]])
        ws.cell(n, 8).fill = PatternFill("solid", fgColor="FFF8DD")
    sheet(wb, "상세·근거",
          ["ID", "원본 번호", "API / 경로", "제공기관", "호스트·엔드포인트", "인증 설정 이름(값 미기재)",
           "사용 코드·함수", "관리자 메뉴·관련 기능", "자동 호출(코드 정의)", "중계 구현 근거", "운영 검증 범위"],
          [(r["id"], r["old"], r["name"], r["agency"], r["url"], r["key"], r["code"],
            r["menu"], r["schedule"], r["relay"], r["history"]) for r in ROWS],
          [18, 12, 44, 23, 85, 58, 68, 60, 65, 25, 49])
    menus = menu_map()
    sheet(wb, "관리자 메뉴별 매핑",
          ["화면 ID", "관리자 메뉴·작업", "관련 목록 ID", "외부/내부 처리", "실행 범위",
           "실제 코드·작업", "수정·주의"], menus, [37, 52, 36, 37, 30, 75, 82])
    steps = [
        (1, "운영 현황 확인", "전체", "웹 배포·예약 배포를 분리", "스위치·권한·오류·현재 성공 시각·본문·적재 결과 확인", "이번 파일에서 실행하지 않음"),
        (2, "첫 OFF 게시 확인", "HUB/RTMS", "설정 준비·게시 승인", "세 스위치 OFF 게시 성공 확인 후 다음 단계", "처음부터 모두 ON 설정 금지"),
        (3, "건축HUB 활성화·실검증", "HUB-1~4", "2 완료", "ON 재게시 후 승인된 조회·공급자 정상 응답·기존 기능 확인", "층별·면적·지역지구도 각각 사용 경로 확인"),
        (4, "실거래 활성화·실검증", "RTMS-1~4", "건축HUB 안정화", "ON 재게시 후 지정 4종 검증", "Nrg 1회 성공을 전체 성공으로 확대 금지"),
        (5, "기존 예약 배포 점검", "HUB/RTMS batch", "웹 안정화·예약 변경 승인", "해당 게시 설정·batch 토큰·새 실행 확인", "개발/웹 Secrets 수정만으로 반영 단정 금지"),
        (6, "정규 숙박 원장·종료 경로 확인", "GOV-CSV8 / LEGACY-1~4", "개발 승인·운영 반영 상태 확인", "승인 원장 최신성·promotion·legacy skip 점검", "1741000 계열 일괄 ON 금지"),
        (7, "상가·인허가 중계 필요 확정", "STORE-1 / PERMIT-1", "실제 오류·호출량·권한 확인", "직접 연동이 정상이면 유지; 반복 연결 장애면 우선 전환", "도메인 같음은 장애 증거 아님"),
        (8, "온비드 현 권한·직접 동기화 확인", "ONBID-1~4", "현 활용승인·기존 실패 확인", "이미 승인됐으면 재신청하지 않고 기능 결과 점검", "서버 상태·승인 대기는 현재 미확인"),
        (9, "선택한 API만 중계 구현", "필요 확정 API", "서버/앱 변경 승인·안전 백업", "서버 호스트·경로·토큰용도와 앱 경유 둘 다 구현; 정상/빈/오류 응답 검사", "무조건 재설치·전체 도메인 허용·권한 일괄 공개 금지"),
        (10, "선택 서비스 OFF 게시→개별 ON", "새 경유 API", "구현·검사 통과", "개별 서비스·용도별 소량 검증 후 기존 일정에 적용", "자동 직접 폴백·대량 수집은 별도 승인"),
        (11, "후속 조건부 검토", "TourAPI·중개·R-ONE·JUSO·캠핑·유지관리", "핵심 경로 안정화", "공란·실패·권한·호출 예산 근거에 따라 순서 조정", "정상 직접 연결은 유지"),
    ]
    sheet(wb, "작업 순서", ["순서", "작업", "대상", "선행 조건", "완료 기준", "주의"], steps,
          [10, 42, 42, 52, 92, 69])
    government = [
        ("관광숙박업", "tourism_lodging"), ("관광펜션업", "tourism_pension"),
        ("농어촌민박업", "rural_homestay"), ("숙박업", "lodging"),
        ("외국인관광도시민박업", "foreign_city_homestay"), ("일반야영장업", "general_camping"),
        ("자동차야영장업", "auto_camping"), ("한옥체험업", "hanok"),
    ]
    nonapi = [
        ("정부 CSV · " + label, key, "GOV-CSV8", "CSV 원본·개발 staging·승인·DB promotion",
         "공급자 API 실호출 아님", "원본 상태·주소·관리번호 보존; 승인된 원장만 반영")
        for label, key in government
    ] + [
        ("외국인관광도시민박업 분류", "foreign_city_homestay", "GOV-CSV8", "법정 업종 원장",
         "Airbnb API 아님", "에어비앤비는 예약 플랫폼; 법적 업종과 구분"),
        ("월간 관광 방문자", "approved manifest + ZIP", "DATALAB-FILE", "저장소/승인 HTTPS 자료",
         "DataLab API 자동 조회 아님", "해시·자료기간·origin 확인"),
        ("법정분류 근거 복원", "저장 건축근거·활성 신고", "없음", "DB 처리",
         "현재 작업에서 실호출 없음", "⑪ 미분류 재분류의 HUB 호출과 분리"),
        ("백업·완공 상태변경·오염 정리", "현재 연결된 DB", "없음", "DB·파일 처리",
         "공공 API 수집 아님", "삭제·상태변경은 영향 확인"),
        ("기존 직접 신고 수집", "LEGACY-1~4", "LEGACY-1~4", "종료 승인·DB 제어 게이트",
         "비상복구 전용", "플래그·실제 skip 확인; 게이트 기본 fail-open 주의"),
        ("고캠핑 전용 수집", "--camping / --update-images-only", "CAMP-1~2", "공급자 API",
         "legacy 종료 게이트 예외", "숙박 승인 8종과 공급원·한도를 구분"),
        ("공매 현황조사 운영", "관리 화면 링크", "없음", "설정·신청·입금·진행 관리",
         "공급자 동기화 아님", "온비드 수집 버튼과 구분"),
        ("관광데이터랩 안내", "공식 자료 안내 URL", "DATALAB-LINK", "안내 링크",
         "이 링크만으로 자동 수집 구현 판정 불가", "원본 업로드·정기 반영은 별도"),
    ]
    sheet(wb, "비API·종료 경로",
          ["자료·작업", "원본 키·경로", "관련 ID", "처리 방식", "API와의 차이", "운영 주의"],
          nonapi, [48, 46, 30, 69, 62, 83])
    sheet(wb, "v2 수정 내역", ["원본 위치", "원본 표현", "v2 수정", "검토 근거", "이유·영향"],
          CORRECTIONS, [35, 71, 92, 85, 70])
    wb.active = 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    validate(menus)


def validate(menus):
    w = load_workbook(OUT, read_only=False, data_only=False)
    with ZipFile(OUT) as z:
        assert z.testzip() is None
    assert len(ROWS) == len({r["id"] for r in ROWS})
    assert w["API 전체 목록"].max_row == len(ROWS) + 1
    assert {str(n) for n in range(1, 28)} <= {r["old"] for r in ROWS}
    assert sum(r["relay"] == "구현(스위치 조건)" for r in ROWS) == 8
    for r in ROWS:
        for ref in r["code"].split(";"):
            filename = ref.strip().split(":")[0]
            if filename.endswith(".py"):
                assert (ROOT / filename).is_file(), filename
    source = (ROOT / "static/admin.html").read_text()
    body = source[source.index("function showDataSync()"):source.index('id="dsSecBackup"') + 100]
    actual_sections = set(re.findall(r'id="(dsSec[^"]+)"', body))
    assert actual_sections <= {m[0] for m in menus}, actual_sections
    assert not any(c.data_type == "f" for s in w for row in s for c in row)
    for s in w:
        assert s.freeze_panes
        assert len(s.tables) == 1
    print(f"PASS: {len(ROWS)} inventory paths, all 27 original categories covered, "
          f"{len(actual_sections)} actual sync section IDs mapped, "
          f"{len(w.sheetnames)} sheets, valid XLSX ZIP, no uncalculated formulas.")
    print("Priorities:", dict(Counter(P[r['level']] for r in ROWS)))
    print("File:", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
