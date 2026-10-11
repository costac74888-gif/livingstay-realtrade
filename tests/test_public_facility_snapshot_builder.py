import csv
import json
import tempfile
import unittest
from pathlib import Path
from scripts.build_public_facility_snapshot import build


class PublicSnapshotBuilderTests(unittest.TestCase):
    def inputs(self, root):
        before=dict(total="2",located="1",fingerprint="unit-only-fence")
        for name, data in (
            ("before.csv",before),("after.csv",before),
            ("counts.csv",dict(**before,master_total="3"))):
            with (root/name).open("w",newline="") as stream:
                writer=csv.DictWriter(stream,fieldnames=list(data))
                writer.writeheader();writer.writerow(data)
        rows=[["a"*32,"unit-only A","일반","서울","동",37,127],
              ["b"*32,"unit-only B","일반","서울","동",None,None]]
        with (root/"page-000.csv").open("w",newline="") as stream:
            writer=csv.writer(stream);writer.writerow(["rows"])
            writer.writerow([json.dumps(rows)])

    def test_complete_audited_export_and_missing_points(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.inputs(root)
            result=build(root,root/"output")
            self.assertEqual(result["total"],2)
            self.assertEqual(result["without_coordinates"],1)

    def test_changed_source_retains_previous_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.inputs(root)
            output=root/"output";output.mkdir()
            (output/"snapshot.json").write_text("previous-unit-only")
            (root/"after.csv").write_text("total,located,fingerprint\n3,1,changed\n")
            with self.assertRaises(ValueError):build(root,output)
            self.assertEqual((output/"snapshot.json").read_text(),"previous-unit-only")

    def test_truncated_query_output_is_not_silently_completed(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.inputs(root)
            (root/"page-000.csv").write_text('rows\n"[[truncated')
            with self.assertRaises(ValueError):build(root,root/"output")


if __name__=="__main__":
    unittest.main()
