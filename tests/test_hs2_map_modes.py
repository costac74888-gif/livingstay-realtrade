import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from scripts.hs2_map_modes import FacilitySnapshot


class SnapshotTests(unittest.TestCase):
    def snapshot(self, path, rows):
        data=json.dumps(rows).encode()
        (path/"facilities-000.json").write_bytes(data)
        (path/"snapshot.json").write_text(json.dumps(dict(total=len(rows),captured_at="unit-only",
            parts=[dict(name="facilities-000.json",sha256=hashlib.sha256(data).hexdigest())])))
        return FacilitySnapshot(path)

    def test_missing_is_explicit_not_fake(self):
        with tempfile.TemporaryDirectory() as directory:
            s=FacilitySnapshot(Path(directory))
            self.assertFalse(s.status()["connected"]);self.assertEqual(s.rows,[])

    def test_all_records_directory_and_only_real_coordinates(self):
        with tempfile.TemporaryDirectory() as directory:
            s=self.snapshot(Path(directory),[
                ["a"*32,"unit-only A","일반","서울","성수",37.5,127],
                ["b"*32,"unit-only B","농어촌민박","제주","읍",None,None],
                ["c"*32,"unit-only C","관광","부산","동",999,999]])
            self.assertEqual(s.status()["total"],3);self.assertEqual(s.located,1)
            self.assertEqual(len(s.matching("농어촌")),1)
            self.assertTrue(all("public_id" not in r and "application_id" not in r for r in s.rows))
            items,count=s.viewport((32,124,39.5,132),4)
            self.assertEqual(count,1);self.assertEqual(len(items),1)
            self.assertEqual(items[0]["point"],dict(lat=37.5,lng=127))

    def test_clusters_exact_count_bounded_and_query(self):
        with tempfile.TemporaryDirectory() as directory:
            rows=[[f"{i:032x}","unit-only fixture","일반","서울","동",37+i/100000,127+i/100000] for i in range(1000)]
            s=self.snapshot(Path(directory),rows)
            items,count=s.viewport((32,124,39.5,132),13)
            self.assertEqual(count,1000);self.assertEqual(sum(r["count"] for r in items),1000)
            self.assertLessEqual(len(items),160)
            self.assertTrue(all(r["cluster"] for r in items))
            self.assertEqual(s.viewport((32,124,39.5,132),13,"없는시설"),([],0))

    def test_tampered_snapshot_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);self.snapshot(p,[["a"*32,"unit only","일반","서울","동",37,127]])
            (p/"facilities-000.json").write_text("[]")
            s=FacilitySnapshot(p)
            self.assertFalse(s.status()["connected"]);self.assertEqual(s.located,0)

    def test_duplicate_record_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            row=["a"*32,"unit only","일반","서울","동",37,127]
            self.assertFalse(self.snapshot(Path(directory),[row,row]).status()["connected"])

    def test_coordinate_filters_keep_missing_records_without_filling_gaps(self):
        with tempfile.TemporaryDirectory() as directory:
            s=self.snapshot(Path(directory),[
                ["a"*32,"unit-only A","일반","서울","동",37,127],
                ["b"*32,"unit-only B","일반","서울","동",None,None]])
            self.assertEqual(len(s.matching("")),2)
            self.assertEqual(len(s.matching("", "located")),1)
            self.assertEqual(len(s.matching("", "missing")),1)
            self.assertIsNone(s.matching("", "missing")[0]["point"])

    def test_public_replica_audit_must_match_actual_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            self.snapshot(p,[["a"*32,"unit-only","일반","서울","동",37,127]])
            manifest=json.loads((p/"snapshot.json").read_text())
            before=dict(total="1",located="1",fingerprint="unit-only-not-live-evidence")
            manifest.update(source="production_readonly_public_field_snapshot",
                reference_count=2, production_writes=False, contains_customer_or_owner_fields=False,
                public_source_fence=dict(before=before,after=before.copy(),
                    counts=dict(**before,master_total="2")))
            (p/"snapshot.json").write_text(json.dumps(manifest))
            s=FacilitySnapshot(p)
            self.assertTrue(s.status()["reference_count_verified"])
            self.assertFalse(s.status()["live_connection"])
            manifest["public_source_fence"]["after"]["total"]="2"
            (p/"snapshot.json").write_text(json.dumps(manifest))
            s=FacilitySnapshot(p)
            self.assertFalse(s.status()["connected"])
            self.assertFalse(s.status()["reference_count_verified"])


if __name__=="__main__":
    unittest.main()
