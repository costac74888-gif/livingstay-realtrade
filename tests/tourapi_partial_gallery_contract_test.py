import unittest
from pathlib import Path


class TourApiPartialGalleryContractTests(unittest.TestCase):
    def test_single_legacy_photo_is_enriched_without_hiding_it(self):
        app = Path("app.py").read_text(encoding="utf-8")
        main = Path("static/js/main.js").read_text(encoding="utf-8")

        self.assertIn('fetch["status"] == "gallery_checked"', app)
        self.assertIn("tourapi_photo_count >= 2", app)
        self.assertIn('"images_backfilled",', app)
        self.assertIn('"gallery_checked" if (photos or existing_urls)', app)

        self.assertIn("if (data.status === \"cached\") return;", main)
        self.assertIn("const mergePhotos = (...groups)", main)
        self.assertIn(
            "renderPhotoSlider(mergePhotos(photos, local.photos))",
            main,
        )
        self.assertIn(
            "const mergedPhotos = mergePhotos("
            "photos, gocampingInitial, clientPhotos)",
            main,
        )
        self.assertIn(
            "if (mergedPhotos.length) {\n"
            "            renderPhotoSlider(mergedPhotos);",
            main,
        )
        self.assertIn("BUILDING_PHOTO_LOCAL_CACHE_VERSION = 2", main)

    def test_partial_gallery_has_a_real_browser_regression_check(self):
        browser_test = Path(
            "tests/tourapi_partial_gallery_browser_test.js"
        ).read_text(encoding="utf-8")
        package = Path("package.json").read_text(encoding="utf-8")

        self.assertIn('scenario = "empty"', browser_test)
        self.assertIn('openScenario("success")', browser_test)
        self.assertIn('openScenario("error")', browser_test)
        self.assertIn('"test:tourapi-gallery"', package)


if __name__ == "__main__":
    unittest.main()