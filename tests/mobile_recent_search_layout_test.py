from pathlib import Path


JS = Path("static/js/main.js").read_text(encoding="utf-8")
CSS = Path("static/css/main.css").read_text(encoding="utf-8")


def test_recent_search_keeps_ten_buildings():
    assert 'const HS_RECENT_MAX = 10;' in JS


def test_mobile_recent_search_wraps_inside_scrollable_search_card():
    assert ".map-searchbar .recent-search-chips" in CSS
    assert "flex-wrap:wrap; overflow:visible;" in CSS
    assert "overflow-y:auto;" in CSS


def test_building_photo_keeps_its_top_edge_visible():
    photo_rule = CSS.split(".bld-photo-slide > img{", 1)[1].split("}", 1)[0]
    assert "object-fit:cover;" in photo_rule
    assert "object-position:center top;" in photo_rule