import hashlib
import io
import json
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest.mock import patch

import sync_tourism_monthly as sync
import tourism_datalab_admin as admin


def monthly_csv(missing_region=False):
    rows = [
        "기준년월,광역지자체명,기초지자체명,기초지자체 방문자 수,기초지자체 방문자 비율",
        "202601,서울특별시,중구,100,10",
        "202601,서울특별시,종로구,200,20",
        "202602,서울특별시,중구,110,11",
    ]
    if not missing_region:
        rows.append("202602,서울특별시,종로구,210,21")
    return ("\n".join(rows) + "\n").encode()


def archive(raw):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("지역별 방문자 수(기초지자체별).csv", raw)
    return out.getvalue()


class TourismMonthlySyncTests(unittest.TestCase):
    def test_uses_existing_missing_region_validation(self):
        raw = archive(monthly_csv(missing_region=True))
        with self.assertRaisesRegex(ValueError, "누락 지역"):
            admin.validated_monthly_visitor_manifest(
                "관광_202601-202602_원본.zip", raw
            )

    def test_declared_period_is_required_to_detect_edge_months(self):
        with self.assertRaisesRegex(ValueError, "YYYYMM-YYYYMM"):
            admin.validated_monthly_visitor_manifest(
                "관광_월간_원본.zip", archive(monthly_csv())
            )

    def test_hash_mismatch_stops_before_validation_or_database(self):
        manifest = json.dumps({
            "filename": "관광_202601-202602_원본.zip",
            "url": "https://approved.example/monthly.zip",
            "sha256": "0" * 64,
        }).encode()
        with patch.object(sync, "_download", side_effect=[manifest, b"wrong"]):
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                sync.fetch_approved_source("https://approved.example/manifest.json")

    def test_default_approved_path_uses_content_addressed_object_storage(self):
        raw = archive(monthly_csv())
        digest = hashlib.sha256(raw).hexdigest()
        manifest = json.dumps({
            "filename": "관광_202601-202602_원본.zip",
            "object_key": f"{sync.OBJECT_ARCHIVE_PREFIX}{digest}.zip",
            "sha256": digest,
        }).encode()
        with patch.object(
            sync.storage_util, "download_bytes", side_effect=[manifest, raw]
        ) as download:
            filename, actual, actual_hash = sync.fetch_approved_source()
        self.assertEqual(filename, "관광_202601-202602_원본.zip")
        self.assertEqual(actual, raw)
        self.assertEqual(actual_hash, digest)
        self.assertEqual(
            download.call_args_list[0].args[0], sync.OBJECT_MANIFEST_KEY
        )

    def test_object_manifest_cannot_select_arbitrary_key(self):
        raw = archive(monthly_csv())
        digest = hashlib.sha256(raw).hexdigest()
        manifest = json.dumps({
            "filename": "관광_202601-202602_원본.zip",
            "object_key": "other/private-object.zip",
            "sha256": digest,
        }).encode()
        with patch.object(sync.storage_util, "download_bytes", return_value=manifest):
            with self.assertRaisesRegex(ValueError, "content-addressed"):
                sync.fetch_approved_source()

    def test_manifest_and_source_must_share_approved_origin(self):
        manifest = json.dumps({
            "filename": "관광_202601-202602_원본.zip",
            "url": "https://other.example/monthly.zip",
            "sha256": hashlib.sha256(b"x").hexdigest(),
        }).encode()
        with patch.object(sync, "_download", return_value=manifest):
            with self.assertRaisesRegex(ValueError, "같은 HTTPS origin"):
                sync.fetch_approved_source("https://approved.example/manifest.json")

    def test_scheduled_stage_runs_weekly(self):
        import scheduled_sync
        stage = scheduled_sync.STAGE_MAP["tourism_monthly"]
        self.assertEqual(stage.command, ("sync_tourism_monthly.py",))
        self.assertTrue(stage.is_due(0))
        self.assertFalse(stage.is_due(1))

    def test_admin_registry_exposes_scheduled_stage(self):
        source = Path("app.py").read_text(encoding="utf-8")
        self.assertIn(
            '("tourism_monthly", "월간 관광 시군구 방문자 원본", "관광", "매주 월")',
            source,
        )

    def test_download_does_not_follow_redirects(self):
        class RedirectingOpener:
            def open(self, request, timeout):
                raise urllib.error.HTTPError(
                    request.full_url, 302, "Found",
                    {"Location": "https://other.example/file.zip"}, None
                )
        with patch.object(sync.urllib.request, "build_opener", return_value=RedirectingOpener()):
            with self.assertRaises(urllib.error.HTTPError):
                sync._download("https://approved.example/file.zip", 100)
