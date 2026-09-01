"""매물 사진의 이미지 품질·EXIF GPS 검증 유틸리티."""

import hashlib
import io
import math
from datetime import datetime

from PIL import Image, ImageStat
import piexif


ALLOWED_MIME = {"image/jpeg", "image/png"}
MAX_BYTES = 10 * 1024 * 1024
MIN_WIDTH = 1280
MIN_HEIGHT = 960
GPS_RADIUS_M = 50
GPS_RADIUS_LOOSE_M = 100
STDDEV_MIN = 15


def _rational(value):
    try:
        numerator, denominator = value
        if not denominator:
            return None
        return float(numerator) / float(denominator)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _dms_to_dd(dms):
    if not dms or len(dms) < 3:
        return None
    values = [_rational(part) for part in dms[:3]]
    if any(value is None for value in values):
        return None
    return values[0] + values[1] / 60 + values[2] / 3600


def _exif_text(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore").strip()
    return str(value).strip() if value is not None else ""


def _parse_exif(file_bytes):
    gps_lat = gps_lng = exif_taken_at = None
    gps_hdop = None
    try:
        exif = piexif.load(file_bytes)
        gps = exif.get("GPS", {})
        gps_lat = _dms_to_dd(gps.get(piexif.GPSIFD.GPSLatitude))
        gps_lng = _dms_to_dd(gps.get(piexif.GPSIFD.GPSLongitude))
        lat_ref = _exif_text(gps.get(piexif.GPSIFD.GPSLatitudeRef, "N")).upper()
        lng_ref = _exif_text(gps.get(piexif.GPSIFD.GPSLongitudeRef, "E")).upper()
        if gps_lat is not None and lat_ref == "S":
            gps_lat = -gps_lat
        if gps_lng is not None and lng_ref == "W":
            gps_lng = -gps_lng
        hdop = _rational(gps.get(piexif.GPSIFD.GPSDOP))
        if hdop is not None:
            gps_hdop = hdop

        raw_taken_at = exif.get("Exif", {}).get(piexif.ExifIFD.DateTimeOriginal)
        exif_taken_at = _exif_text(raw_taken_at) or None
    except Exception:
        # EXIF가 없는 PNG·편집본도 이미지 자체가 정상이라면 다음 검증으로 진행한다.
        pass
    return gps_lat, gps_lng, gps_hdop, exif_taken_at


def _haversine(lat1, lng1, lat2, lng2):
    """두 좌표 간 거리를 미터 단위로 반환한다."""
    earth_radius_m = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return earth_radius_m * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def validate_photo(
    file_bytes,
    mime_type,
    building_lat,
    building_lng,
    registrant_type,
    is_certified_agent,
):
    """업로드 사진을 검증하고 DB에 기록할 메타데이터를 반환한다."""
    if mime_type not in ALLOWED_MIME:
        return {"ok": False, "error": "jpg/png 파일만 등록 가능합니다."}
    if len(file_bytes) > MAX_BYTES:
        return {"ok": False, "error": "파일 크기는 10MB 이하만 가능합니다."}

    try:
        with Image.open(io.BytesIO(file_bytes)) as image:
            width, height = image.size
            if width < MIN_WIDTH or height < MIN_HEIGHT:
                return {
                    "ok": False,
                    "error": f"해상도가 너무 낮습니다 (최소 {MIN_WIDTH}x{MIN_HEIGHT}px).",
                }
            stddev = sum(ImageStat.Stat(image.convert("RGB")).stddev) / 3
    except Exception:
        return {"ok": False, "error": "이미지를 읽을 수 없습니다."}

    if stddev < STDDEV_MIN:
        return {"ok": False, "error": "단색 또는 빈 이미지는 등록할 수 없습니다."}

    photo_hash = hashlib.sha256(file_bytes).hexdigest()
    gps_lat, gps_lng, gps_hdop, exif_taken_at = _parse_exif(file_bytes)
    gps_verified = False
    radius = GPS_RADIUS_LOOSE_M if is_certified_agent or (gps_hdop and gps_hdop > 5) else GPS_RADIUS_M
    requires_gps = (
        registrant_type in {"owner", "building_owner", "landlord", "business"}
        and not is_certified_agent
    )

    has_gps = (
        gps_lat is not None
        and gps_lng is not None
        and math.isfinite(gps_lat)
        and math.isfinite(gps_lng)
    )
    has_building_coords = (
        building_lat is not None
        and building_lng is not None
        and math.isfinite(float(building_lat))
        and math.isfinite(float(building_lng))
    )
    if has_gps and has_building_coords:
        distance = _haversine(gps_lat, gps_lng, float(building_lat), float(building_lng))
        if distance > radius:
            return {
                "ok": False,
                "error": (
                    f"촬영 위치가 건물에서 {int(distance)}m 떨어져 있습니다. "
                    f"건물 현장({radius}m 이내)에서 촬영한 사진만 등록 가능합니다."
                ),
            }
        gps_verified = True
    elif requires_gps:
        if not has_building_coords:
            return {
                "ok": False,
                "error": "건물 좌표를 확인할 수 없어 사진 위치를 검증할 수 없습니다.",
            }
        return {
            "ok": False,
            "error": (
                "위치정보(GPS)가 없는 사진입니다. "
                "스마트폰으로 건물 현장에서 직접 촬영한 사진을 올려주세요."
            ),
        }

    return {
        "ok": True,
        "hash": photo_hash,
        "gps_lat": gps_lat,
        "gps_lng": gps_lng,
        "gps_verified": gps_verified,
        "exif_taken_at": exif_taken_at,
    }