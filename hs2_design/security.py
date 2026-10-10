"""Shared additive response hardening; no identity/DB/provider configuration."""


def harden(response):
    response.headers["Content-Security-Policy"]=response.headers.get("Content-Security-Policy") or (
        "default-src 'self'; script-src 'self' https://dapi.kakao.com https://t1.daumcdn.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; img-src 'self' https: data: blob:; "
        "connect-src 'self' https://dapi.kakao.com https://*.daumcdn.net; "
        "frame-src 'self' https://map.kakao.com https://*.daum.net; "
        "frame-ancestors 'self'; object-src 'none'; base-uri 'self'; form-action 'self'")
    response.headers["Permissions-Policy"]="camera=(), microphone=(), geolocation=(), payment=()"
    response.headers["Strict-Transport-Security"]="max-age=31536000"
    response.headers["X-Frame-Options"]="SAMEORIGIN"
    response.headers["X-Permitted-Cross-Domain-Policies"]="none"
    response.headers["Referrer-Policy"]="same-origin"
    response.headers["X-Content-Type-Options"]="nosniff"
    return response
