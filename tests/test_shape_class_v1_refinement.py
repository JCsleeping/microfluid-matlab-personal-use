import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from visualization.build_shape_class_v1_refinement import build_shape_class_v1_refinement


class ShapeClassV1RefinementTests(unittest.TestCase):
    def test_v1_refines_low_area_and_ambiguous_rows_without_promoting_small_boundary_classes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            morph_dir = root / "morphology"
            morph_dir.mkdir()

            pd.DataFrame(
                [
                    {
                        "FrameIndex": 1,
                        "RealTime_s": 0.0,
                        "BlobID": 1,
                        "ShapeClass": "small_unclassified",
                        "ShapeClassReason": "area_lt_250",
                        "Area_px": 80.0,
                        "BoundaryMetricValid": False,
                        "AreaTier": "tiny",
                        "AxisAspectRatio": 1.2,
                        "AspectRatio01": 0.83,
                        "Solidity2D": 0.95,
                        "ProjectedSphericity2D": 0.9,
                        "ProjectedRoughness_boundary": 1.05,
                        "PtotalOverPouter": 1.0,
                        "CircularityGreaterThan1p05": True,
                        "RoughnessLessThanOne": False,
                        "TouchesImageBorder": False,
                    },
                    {
                        "FrameIndex": 1,
                        "RealTime_s": 0.0,
                        "BlobID": 2,
                        "ShapeClass": "small_unclassified",
                        "ShapeClassReason": "area_lt_250",
                        "Area_px": 150.0,
                        "BoundaryMetricValid": False,
                        "AreaTier": "small",
                        "AxisAspectRatio": 1.3,
                        "AspectRatio01": 0.77,
                        "Solidity2D": 0.94,
                        "ProjectedSphericity2D": 0.86,
                        "ProjectedRoughness_boundary": 1.04,
                        "PtotalOverPouter": 1.0,
                        "CircularityGreaterThan1p05": False,
                        "RoughnessLessThanOne": False,
                        "TouchesImageBorder": False,
                    },
                    {
                        "FrameIndex": 1,
                        "RealTime_s": 0.0,
                        "BlobID": 3,
                        "ShapeClass": "small_unclassified",
                        "ShapeClassReason": "area_lt_250",
                        "Area_px": 180.0,
                        "BoundaryMetricValid": False,
                        "AreaTier": "small",
                        "AxisAspectRatio": 2.5,
                        "AspectRatio01": 0.4,
                        "Solidity2D": 0.85,
                        "ProjectedSphericity2D": 0.7,
                        "ProjectedRoughness_boundary": 1.1,
                        "PtotalOverPouter": 1.0,
                        "CircularityGreaterThan1p05": False,
                        "RoughnessLessThanOne": False,
                        "TouchesImageBorder": False,
                    },
                    {
                        "FrameIndex": 2,
                        "RealTime_s": 1.0,
                        "BlobID": 4,
                        "ShapeClass": "ambiguous_valid",
                        "ShapeClassReason": "valid_geometry_fallback",
                        "Area_px": 600.0,
                        "BoundaryMetricValid": True,
                        "AreaTier": "large",
                        "AxisAspectRatio": 1.5,
                        "AspectRatio01": 0.67,
                        "Solidity2D": 0.93,
                        "ProjectedSphericity2D": 0.86,
                        "ProjectedRoughness_boundary": 1.08,
                        "PtotalOverPouter": 1.0,
                        "CircularityGreaterThan1p05": False,
                        "RoughnessLessThanOne": False,
                        "TouchesImageBorder": False,
                    },
                    {
                        "FrameIndex": 2,
                        "RealTime_s": 1.0,
                        "BlobID": 5,
                        "ShapeClass": "ambiguous_valid",
                        "ShapeClassReason": "valid_geometry_fallback",
                        "Area_px": 700.0,
                        "BoundaryMetricValid": True,
                        "AreaTier": "large",
                        "AxisAspectRatio": 2.5,
                        "AspectRatio01": 0.4,
                        "Solidity2D": 0.84,
                        "ProjectedSphericity2D": 0.75,
                        "ProjectedRoughness_boundary": 1.1,
                        "PtotalOverPouter": 1.0,
                        "CircularityGreaterThan1p05": False,
                        "RoughnessLessThanOne": False,
                        "TouchesImageBorder": False,
                    },
                    {
                        "FrameIndex": 2,
                        "RealTime_s": 1.0,
                        "BlobID": 6,
                        "ShapeClass": "compact_round",
                        "ShapeClassReason": "high_sphericity_high_solidity_low_elongation",
                        "Area_px": 800.0,
                        "BoundaryMetricValid": True,
                        "AreaTier": "large",
                        "AxisAspectRatio": 1.1,
                        "AspectRatio01": 0.91,
                        "Solidity2D": 0.96,
                        "ProjectedSphericity2D": 0.91,
                        "ProjectedRoughness_boundary": 1.04,
                        "PtotalOverPouter": 1.0,
                        "CircularityGreaterThan1p05": False,
                        "RoughnessLessThanOne": False,
                        "TouchesImageBorder": False,
                    },
                ]
            ).to_csv(morph_dir / "blob_morphology_by_blob.csv", index=False)

            (morph_dir / "blob_morphology_thresholds.json").write_text(
                json.dumps(
                    {
                        "thresholds": {
                            "ProjectedSphericity2D": {"q50": 0.76, "q75": 0.85, "q90": 0.92},
                            "AspectRatio01": {"q50": 0.55, "q75": 0.68, "q90": 0.80},
                            "AxisAspectRatio": {"q50": 1.82, "q75": 2.34, "q90": 2.99},
                            "Solidity2D": {"q25": 0.74, "q50": 0.86, "q75": 0.92, "q90": 0.95},
                            "ProjectedRoughness_boundary": {"q75": 1.22, "q90": 1.37},
                            "PtotalOverPouter": {"q75": 1.0, "q90": 1.06},
                        }
                    }
                ),
                encoding="utf-8",
            )

            output_dir = root / "v1"
            manifest = build_shape_class_v1_refinement(morph_dir, output_dir=output_dir)

            by_blob = pd.read_csv(output_dir / "blob_shape_class_v1_by_blob.csv")
            classes = dict(zip(by_blob["BlobID"], by_blob["ShapeClassV1"]))
            self.assertEqual(classes[1], "count_only_lt100")
            self.assertEqual(classes[2], "low_area_compact_candidate_100_249")
            self.assertEqual(classes[3], "low_area_elongated_candidate_100_249")
            self.assertEqual(classes[4], "near_compact_regular")
            self.assertEqual(classes[5], "moderately_elongated")
            self.assertEqual(classes[6], "compact_regular")

            low_area = by_blob[by_blob["Area_px"] < 250]
            self.assertTrue(low_area["ShapeClassV1"].str.startswith(("count_only", "low_area")).all())
            self.assertTrue((by_blob["ShapeClassVersion"] == "v1").all())
            self.assertTrue((by_blob["MetricSource"] == "full_duration_sidecar").all())
            self.assertTrue((by_blob["BoundaryMetricSource"] == "corrected_sidecar_boundary").all())
            self.assertTrue(by_blob["FullSidecarDerived"].astype(bool).all())

            summary = pd.read_csv(output_dir / "shape_class_v1_summary_by_class.csv")
            self.assertIn("near_compact_regular", set(summary["ShapeClassV1"]))
            transition = pd.read_csv(output_dir / "shape_class_v0_to_v1_transition_count.csv")
            self.assertIn("ShapeClassV0", transition.columns)
            self.assertIn("near_compact_regular", transition.columns)

            qc = (output_dir / "shape_class_v1_qc.md").read_text(encoding="utf-8")
            self.assertIn("Area < 100 px remains count-only", qc)
            self.assertIn("100 <= Area < 250 px is low-area projected-shape caution", qc)
            self.assertIn("Decision:", qc)

            self.assertEqual(manifest["row_counts"]["rows"], 6)
            self.assertIn("decision_label", manifest["qc"])


if __name__ == "__main__":
    unittest.main()
