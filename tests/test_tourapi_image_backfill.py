import unittest
from pathlib import Path
from unittest import mock

import requests

import backfill_tourapi_images as images


class TourApiImageBackfillTests(unittest.TestCase):
    def test_representative_and_detail_images_are_deduplicated_and_limited(self):
        rows = [
            {"originimgurl": "https://tong.visitkorea.or.kr/a.jpg", "imgname": "외관"},
            {"originimgurl": "https://tong.visitkorea.or.kr/b.jpg", "imgname": "객실"},
            {"originimgurl": "https://tong.visitkorea.or.kr/b.jpg", "imgname": "객실"},
        ]
        result = images._photo_rows(
            "https://tong.visitkorea.or.kr/a.jpg", rows
        )
        self.assertEqual(
            [row["url"] for row in result],
            [
                "https://tong.visitkorea.or.kr/a.jpg",
                "https://tong.visitkorea.or.kr/b.jpg",
            ],
        )
        self.assertEqual(result[1]["photo_type"], "room")
        many = images._photo_rows(
            "",
            [
                {
                    "originimgurl":
                        f"https://tong.visitkorea.or.kr/{index}.jpg"
                }
                for index in range(40)
            ],
        )
        self.assertEqual(len(many), 20)

    def test_untrusted_or_insecure_image_hosts_are_rejected(self):
        result = images._photo_rows(
            "http://tong.visitkorea.or.kr/insecure.jpg",
            [{"originimgurl": "https://evil.example/photo.jpg"}],
        )
        self.assertEqual(result, [])

    def test_existing_photo_is_merged_without_exceeding_building_cap(self):
        existing = ["https://tong.visitkorea.or.kr/existing.jpg"]
        result = images._photo_rows(
            "https://tong.visitkorea.or.kr/existing.jpg",
            [
                {
                    "originimgurl":
                        f"https://tong.visitkorea.or.kr/new-{index}.jpg"
                }
                for index in range(40)
            ],
            existing_urls=existing,
            max_new=images.MAX_PHOTOS - len(existing),
        )
        self.assertEqual(len(result), 19)
        self.assertNotIn(existing[0], [row["url"] for row in result])

    def test_each_http_attempt_claims_one_shared_quota_slot(self):
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "response": {
                "header": {"resultCode": "0000"},
                "body": {"items": {"item": []}},
            }
        }
        session = mock.Mock()
        session.get.return_value = response
        with mock.patch.object(
            images, "_claim_daily_slot", return_value=1
        ) as claim:
            images._tour_request(
                session, "detailImage2", {"contentId": "1"}, "key"
            )
        claim.assert_called_once_with(
            images.CALLS_KEY, images.TOURAPI_DAILY_CAP
        )
        session.get.assert_called_once()
        self.assertEqual(
            session.get.call_args.kwargs["params"]["serviceKey"], "key"
        )

    @mock.patch.object(images.time, "sleep")
    def test_transient_timeout_retries_and_claims_each_attempt(self, sleep):
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "response": {
                "header": {"resultCode": "0000"},
                "body": {"items": {"item": []}},
            }
        }
        session = mock.Mock()
        session.get.side_effect = [
            requests.Timeout("temporary timeout"),
            response,
        ]
        with mock.patch.object(
            images, "_claim_daily_slot", side_effect=[1, 2]
        ) as claim:
            result = images._tour_request(
                session, "detailImage2", {"contentId": "1"}, "a%2Bb"
            )
        self.assertEqual(
            result["response"]["header"]["resultCode"], "0000"
        )
        self.assertEqual(claim.call_count, 2)
        self.assertEqual(session.get.call_count, 2)
        self.assertEqual(
            session.get.call_args.kwargs["params"]["serviceKey"], "a+b"
        )
        sleep.assert_called_once_with(images.REQUEST_RETRY_DELAYS[0])

    def test_admin_runner_is_detached_resumable_and_visible(self):
        app = Path("app.py").read_text(encoding="utf-8")
        admin = Path("static/admin.html").read_text(encoding="utf-8")
        self.assertIn(
            '@app.route("/api/admin/tourapi-image-backfill", methods=["POST"])',
            app,
        )
        self.assertIn(
            '@app.route("/api/admin/tourapi-image-backfill-status")', app
        )
        self.assertIn(
            '_TOURAPI_IMAGE_BACKFILL_META_KEY = '
            '"admin:tourapi_image_backfill:status"',
            app,
        )
        self.assertIn('"backfill_tourapi_images.py"', app)
        self.assertIn('"--run-id", "__RUN_ID__"', app)
        self.assertIn('id="tourapiImageBackfillRunBtn"', admin)
        self.assertIn("TourAPI 숙박사진 이어서 수집", admin)
        self.assertIn("detailImage2 다중사진", admin)
        self.assertIn("f.status IS DISTINCT FROM 'gallery_checked'", Path(
            "backfill_tourapi_images.py"
        ).read_text(encoding="utf-8"))
        self.assertIn(
            "AND p.source='tourapi'",
            Path("backfill_tourapi_images.py").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "SELECT pg_advisory_xact_lock(%s, %s)",
            Path("app.py").read_text(encoding="utf-8"),
        )
        backfill = Path("backfill_tourapi_images.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("FOR UPDATE", backfill)
        self.assertIn("ProviderReferenceChanged", backfill)
        self.assertNotIn(
            "_insert_photos(\n"
            "                        cur, row[\"building_id\"], photos, \"tourapi\"\n"
            "                    )\n"
            "                    conn.commit()",
            backfill,
        )


if __name__ == "__main__":
    unittest.main()