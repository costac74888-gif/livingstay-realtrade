import io
import unittest

import piexif
from PIL import Image

from utils.photo_validate import validate_photo


BUILDING_LAT = 37.5
BUILDING_LNG = 127.0


def _gps_dms(value):
    value = abs(value)
    degrees = int(value)
    minutes = int((value - degrees) * 60)
    seconds = (value - degrees - minutes / 60) * 3600
    return ((degrees, 1), (minutes, 1), (int(round(seconds * 10000)), 10000))


def make_image(*, fmt="JPEG", size=(1280, 960), gps=None, solid=False):
    image = (
        Image.new("RGB", size, "#888888")
        if solid
        else Image.effect_noise(size, 80).convert("RGB")
    )
    output = io.BytesIO()
    options = {}
    if gps is not None:
        lat, lng = gps
        options["exif"] = piexif.dump({
            "GPS": {
                piexif.GPSIFD.GPSLatitudeRef: b"N" if lat >= 0 else b"S",
                piexif.GPSIFD.GPSLatitude: _gps_dms(lat),
                piexif.GPSIFD.GPSLongitudeRef: b"E" if lng >= 0 else b"W",
                piexif.GPSIFD.GPSLongitude: _gps_dms(lng),
            },
            "Exif": {
                piexif.ExifIFD.DateTimeOriginal: b"2026:09:02 12:34:56",
            },
        })
    image.save(output, format=fmt, quality=88, **options)
    return output.getvalue()


class PhotoValidationTest(unittest.TestCase):
    def test_nearby_gps_jpeg_is_verified(self):
        result = validate_photo(
            make_image(gps=(37.5001, 127.0001)),
            "image/jpeg", BUILDING_LAT, BUILDING_LNG, "building_owner", False,
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["gps_verified"])
        self.assertEqual(64, len(result["hash"]))
        self.assertEqual("2026:09:02 12:34:56", result["exif_taken_at"])

    def test_distant_gps_is_allowed(self):
        result = validate_photo(
            make_image(gps=(37.502, 127.0)),
            "image/jpeg", BUILDING_LAT, BUILDING_LNG, "owner", False,
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["gps_verified"])

    def test_owner_requires_gps_but_certified_agent_does_not(self):
        photo = make_image()
        owner = validate_photo(
            photo, "image/jpeg", BUILDING_LAT, BUILDING_LNG, "business", False,
        )
        agent = validate_photo(
            photo, "image/jpeg", BUILDING_LAT, BUILDING_LNG, "business", True,
        )
        self.assertFalse(owner["ok"])
        self.assertIn("위치정보", owner["error"])
        self.assertTrue(agent["ok"])
        self.assertFalse(agent["gps_verified"])

    def test_png_is_allowed_for_agent(self):
        result = validate_photo(
            make_image(fmt="PNG"),
            "image/png", BUILDING_LAT, BUILDING_LNG, "agent", True,
        )
        self.assertTrue(result["ok"])

    def test_webp_mime_is_rejected(self):
        result = validate_photo(
            make_image(),
            "image/webp", BUILDING_LAT, BUILDING_LNG, "agent", True,
        )
        self.assertFalse(result["ok"])
        self.assertIn("jpg/png", result["error"])

    def test_low_resolution_and_solid_images_are_rejected(self):
        low_resolution = validate_photo(
            make_image(size=(800, 600)),
            "image/jpeg", BUILDING_LAT, BUILDING_LNG, "agent", True,
        )
        solid = validate_photo(
            make_image(solid=True),
            "image/jpeg", BUILDING_LAT, BUILDING_LNG, "agent", True,
        )
        self.assertFalse(low_resolution["ok"])
        self.assertIn("해상도", low_resolution["error"])
        self.assertFalse(solid["ok"])
        self.assertIn("단색", solid["error"])

    def test_hash_is_stable_for_duplicate_detection(self):
        photo = make_image(gps=(37.5001, 127.0001))
        first = validate_photo(
            photo, "image/jpeg", BUILDING_LAT, BUILDING_LNG, "owner", False,
        )
        second = validate_photo(
            photo, "image/jpeg", BUILDING_LAT, BUILDING_LNG, "owner", False,
        )
        self.assertEqual(first["hash"], second["hash"])


if __name__ == "__main__":
    unittest.main()