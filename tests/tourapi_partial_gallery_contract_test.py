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


if __name__ == "__main__":
    unittest.main()