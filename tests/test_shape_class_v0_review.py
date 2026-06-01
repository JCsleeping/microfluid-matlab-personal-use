import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from visualization.build_shape_class_v0_review import build_shape_class_v0_review


class ShapeClassV0ReviewTests(unittest.TestCase):
    def test_review_outputs_are_diagnostic_not_official_reclassification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            morph = root / "morph"
            out = root / "review"
            morph.mkdir()
            thresholds = {
                "thresholds": {
                    "ProjectedSphericity2D": {"q50": 0.7, "q75": 0.85},
                    "AxisAspectRatio": {"q75": 2.0, "q90": 3.0},
                    "Solidity2D": {"q25": 0.7, "q50": 0.85},
                    "ProjectedRoughness_boundary": {"q75": 1.2, "q90": 1.5},
                }
            }
            (morph / "blob_morphology_thresholds.json").write_text(json.dumps(thresholds), encoding="utf-8")
            rows = [
                {
                    "FrameIndex": 1,
                    "BlobID": 1,
                    "ShapeClass": "ambiguous_valid",
                    "Area_px": 500,
                    "ProjectedSphericity2D": 0.82,
                    "AxisAspectRatio": 1.5,
                    "Solidity2D": 0.9,
                    "ProjectedRoughness_boundary": 1.1,
                    "PtotalOverPouter": 1.0,
                    "ProjectedRegularity2D": 0.8,
                    "MaskPath": "mask.tif",
                    "LabelPath": "label.tif",
                },
                {
                    "FrameIndex": 1,
                    "BlobID": 2,
                    "ShapeClass": "ambiguous_valid",
                    "Area_px": 700,
                    "ProjectedSphericity2D": 0.65,
                    "AxisAspectRatio": 2.4,
                    "Solidity2D": 0.8,
                    "ProjectedRoughness_boundary": 1.15,
                    "PtotalOverPouter": 1.0,
                    "ProjectedRegularity2D": 0.65,
                    "MaskPath": "mask.tif",
                    "LabelPath": "label.tif",
                },
                {
                    "FrameIndex": 1,
                    "BlobID": 3,
                    "ShapeClass": "compact_round",
                    "Area_px": 800,
                    "ProjectedSphericity2D": 0.9,
                    "AxisAspectRatio": 1.1,
                    "Solidity2D": 0.95,
                    "ProjectedRoughness_boundary": 1.05,
                    "PtotalOverPouter": 1.0,
                    "ProjectedRegularity2D": 0.9,
                    "MaskPath": "mask.tif",
                    "LabelPath": "label.tif",
                },
            ]
            pd.DataFrame(rows).to_csv(morph / "blob_shape_class_by_blob.csv", index=False)

            manifest = build_shape_class_v0_review(morph, out)
            self.assertFalse(manifest["scope"]["changes_official_shape_classes"])
            self.assertEqual(manifest["row_counts"]["ambiguous_valid_rows"], 2)

            for name in [
                "ambiguous_valid_diagnostic.csv",
                "ambiguous_valid_candidate_subclasses.csv",
                "ambiguous_valid_representatives.csv",
                "shape_class_v0_review.md",
                "shape_class_v0_review_manifest.json",
            ]:
                self.assertTrue((out / name).exists(), name)

            subclasses = pd.read_csv(out / "ambiguous_valid_candidate_subclasses.csv")
            self.assertIn("CandidateSubclass", subclasses.columns)
            self.assertTrue(set(subclasses["CandidateSubclass"]).intersection({"near_compact_round", "moderately_elongated"}))

            review = (out / "shape_class_v0_review.md").read_text(encoding="utf-8")
            self.assertIn("diagnostic only", review)
            self.assertIn("Do not infer split/merge", review)


if __name__ == "__main__":
    unittest.main()
