import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "visualization" / "analyze_blob_shape_classes.py"
SPEC = importlib.util.spec_from_file_location("analyze_blob_shape_classes", MODULE_PATH)
shape_classes = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(shape_classes)


def write_blob_csv(path):
    df = pd.DataFrame(
        {
            "FrameIndex": [1, 1, 1, 1, 1, 1, 2, 2],
            "FrameTime": [0, 0, 0, 0, 0, 0, 1, 1],
            "BlobID": [101, 102, 103, 104, 105, 106, 201, 202],
            "Area": [40.0, 5.0, 10.0, 10.0, 8.0, 7.0, 0.5, 99.5],
            "Circularity": [0.95, 0.90, 0.70, 0.40, 0.82, 1.10, 0.80, 0.76],
            "AspectRatio": [3.0, 1.1, 1.2, 3.2, 1.1, 1.1, 1.0, 1.0],
            "Solidity": [0.95, 0.95, 0.70, 0.95, 0.95, 0.95, 0.95, 0.95],
            "EquivRadius": [2.0, 1.0, 5.0, 6.0, 7.0, 8.0, 0.4, 7.0],
        }
    )
    df.to_csv(path, index=False)
    return df


class BlobShapeClassTests(unittest.TestCase):
    def test_deterministic_priority_assignment(self):
        with tempfile.TemporaryDirectory() as tmp:
            blob_csv = Path(tmp) / "blob.csv"
            write_blob_csv(blob_csv)

            by_blob, _, _, _ = shape_classes.analyze_blob_shape_classes(blob_csv, chunksize=3)
            classes = dict(zip(by_blob["BlobID"], by_blob["ShapeClass"]))

            self.assertEqual(classes[101], "large_dominant")
            self.assertEqual(classes[102], "small_fragment")
            self.assertEqual(classes[103], "concave_irregular")
            self.assertEqual(classes[104], "elongated")
            self.assertEqual(classes[105], "compact_round")
            self.assertEqual(classes[106], "ambiguous")

    def test_circularity_column_renamed_to_circularity2d_without_roundness(self):
        with tempfile.TemporaryDirectory() as tmp:
            blob_csv = Path(tmp) / "blob.csv"
            write_blob_csv(blob_csv)

            by_blob, _, _, _ = shape_classes.analyze_blob_shape_classes(blob_csv, chunksize=4)

            self.assertIn("Circularity2D", by_blob.columns)
            self.assertNotIn("Circularity", by_blob.columns)
            self.assertNotIn("Roundness", by_blob.columns)
            valid = by_blob.loc[by_blob["BlobID"] == 105].iloc[0]
            self.assertAlmostEqual(valid["ProjectedSphericity2D"], np.sqrt(0.82))

    def test_area_and_count_fractions_are_separated(self):
        with tempfile.TemporaryDirectory() as tmp:
            blob_csv = Path(tmp) / "blob.csv"
            write_blob_csv(blob_csv)

            _, summary, _, _ = shape_classes.analyze_blob_shape_classes(blob_csv, chunksize=3)
            row = summary.loc[summary["FrameIndex"] == 1].iloc[0]

            self.assertAlmostEqual(row["countFrac_large_dominant"], 1.0 / 6.0)
            self.assertAlmostEqual(row["areaFrac_large_dominant"], 40.0 / 80.0)
            self.assertIn("ShapeEntropy_count", row.index)
            self.assertIn("ShapeEntropy_area", row.index)

    def test_invalid_circularity_gt_1p05_is_flagged_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            blob_csv = Path(tmp) / "blob.csv"
            write_blob_csv(blob_csv)

            by_blob, _, _, qc = shape_classes.analyze_blob_shape_classes(blob_csv, chunksize=3)
            row = by_blob.loc[by_blob["BlobID"] == 106].iloc[0]

            self.assertEqual(bool(row["ShapeValid"]), False)
            self.assertIn("circularity_gt_1p05", row["ShapeInvalidReason"])
            self.assertTrue(np.isnan(row["ProjectedSphericity2D"]))
            self.assertGreater(qc.loc[0, "invalid_circularity_gt_1p05_count"], 0)

    def test_tiny_blobs_are_flagged_invalid_and_in_qc(self):
        with tempfile.TemporaryDirectory() as tmp:
            blob_csv = Path(tmp) / "blob.csv"
            write_blob_csv(blob_csv)

            by_blob, _, _, qc = shape_classes.analyze_blob_shape_classes(blob_csv, chunksize=4)
            row = by_blob.loc[by_blob["BlobID"] == 201].iloc[0]

            self.assertEqual(bool(row["ShapeValid"]), False)
            self.assertIn("tiny_blob", row["ShapeInvalidReason"])
            self.assertEqual(int(qc.loc[0, "tiny_blob_count"]), 1)

    def test_rate_associations_use_dissolution_rates_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            blob_csv = root / "blob.csv"
            rates_csv = root / "dissolution_rates.csv"
            post = root / "post"
            write_blob_csv(blob_csv)
            pd.DataFrame(
                {
                    "FrameIndex": [1, 2],
                    "DissolutionRate_Sn_per_min": [0.2, 0.8],
                    "OtherRate": [3.0, 4.0],
                }
            ).to_csv(rates_csv, index=False)

            out = shape_classes.run_analysis(
                shape_classes.build_parser().parse_args(
                    [
                        "--output-root",
                        str(root),
                        "--postprocess-dir",
                        str(post),
                        "--blob-csv",
                        str(blob_csv),
                        "--dissolution-rates-csv",
                        str(rates_csv),
                        "--output-dir",
                        "shape_out",
                        "--no-figures",
                    ]
                )
            )
            assoc = pd.read_csv(out / "blob_shape_rate_associations.csv")

            self.assertIn("DissolutionRate_Sn_per_min", set(assoc["rate_column"]))
            self.assertIn("areaFrac_large_dominant", set(assoc["metric"]))
            self.assertTrue((assoc["n"] >= 2).any())

    def test_explicit_nonempty_output_dir_refuses_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            blob_csv = root / "blob.csv"
            post = root / "post"
            out = post / "shape_existing"
            write_blob_csv(blob_csv)
            out.mkdir(parents=True)
            (out / "old.csv").write_text("old", encoding="utf-8")

            with self.assertRaisesRegex(FileExistsError, "already exists and is not empty"):
                shape_classes.main(
                    [
                        "--output-root",
                        str(root),
                        "--postprocess-dir",
                        str(post),
                        "--blob-csv",
                        str(blob_csv),
                        "--output-dir",
                        "shape_existing",
                        "--no-figures",
                    ]
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
