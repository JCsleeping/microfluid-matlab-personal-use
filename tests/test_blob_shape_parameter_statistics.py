import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from visualization.build_blob_shape_parameter_statistics import build_shape_parameter_statistics


class BlobShapeParameterStatisticsTests(unittest.TestCase):
    def test_statistics_package_writes_formulas_and_grouped_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            morph_dir = root / "morphology"
            level_a_dir = root / "level_a"
            morph_dir.mkdir()
            level_a_dir.mkdir()

            pd.DataFrame(
                [
                    {
                        "FrameIndex": 1,
                        "RealTime_s": 0.0,
                        "BlobID": 1,
                        "ShapeClass": "compact_round",
                        "ShapeValid": True,
                        "ReliabilityClass": "high_confidence",
                        "Area_px": 1000.0,
                        "AreaTier": "large",
                        "MajorAxisLength_px": 50.0,
                        "MinorAxisLength_px": 40.0,
                        "Eccentricity": 0.6,
                        "Extent": 0.75,
                        "ConvexArea_px": 1100.0,
                        "Solidity2D": 1000.0 / 1100.0,
                        "ProjectedSphericity2D": 0.82,
                        "Circularity2D_boundary": 0.67,
                        "AspectRatio01": 0.8,
                        "AxisAspectRatio": 1.25,
                        "ProjectedRoughness_boundary": 1.08,
                        "PtotalOverPouter": 1.0,
                        "ProjectedRegularity2D": (0.82 + 0.8 + 1000.0 / 1100.0) / 3.0,
                        "P_outer_boundary": 130.0,
                        "Pc_outer_boundary": 120.0,
                        "P_total_boundary": 130.0,
                    },
                    {
                        "FrameIndex": 2,
                        "RealTime_s": 1.0,
                        "BlobID": 2,
                        "ShapeClass": "elongated",
                        "ShapeValid": True,
                        "ReliabilityClass": "geometry_valid",
                        "Area_px": 500.0,
                        "AreaTier": "medium",
                        "MajorAxisLength_px": 80.0,
                        "MinorAxisLength_px": 20.0,
                        "Eccentricity": 0.9,
                        "Extent": 0.5,
                        "ConvexArea_px": 625.0,
                        "Solidity2D": 0.8,
                        "ProjectedSphericity2D": 0.55,
                        "Circularity2D_boundary": 0.3,
                        "AspectRatio01": 0.25,
                        "AxisAspectRatio": 4.0,
                        "ProjectedRoughness_boundary": 1.2,
                        "PtotalOverPouter": 1.1,
                        "ProjectedRegularity2D": (0.55 + 0.25 + 0.8) / 3.0,
                        "P_outer_boundary": 150.0,
                        "Pc_outer_boundary": 125.0,
                        "P_total_boundary": 165.0,
                    },
                    {
                        "FrameIndex": 2,
                        "RealTime_s": 1.0,
                        "BlobID": 3,
                        "ShapeClass": "small_unclassified",
                        "ShapeValid": False,
                        "ReliabilityClass": "count_only_small",
                        "Area_px": 100.0,
                        "AreaTier": "tiny",
                        "MajorAxisLength_px": 15.0,
                        "MinorAxisLength_px": 10.0,
                        "Eccentricity": 0.4,
                        "Extent": 0.6,
                        "ConvexArea_px": 120.0,
                        "Solidity2D": 100.0 / 120.0,
                        "ProjectedSphericity2D": 0.7,
                        "Circularity2D_boundary": 1.2,
                        "AspectRatio01": 10.0 / 15.0,
                        "AxisAspectRatio": 1.5,
                        "ProjectedRoughness_boundary": 0.95,
                        "PtotalOverPouter": 1.0,
                        "ProjectedRegularity2D": (0.7 + 10.0 / 15.0 + 100.0 / 120.0) / 3.0,
                        "P_outer_boundary": 45.0,
                        "Pc_outer_boundary": 47.0,
                        "P_total_boundary": 45.0,
                    },
                ]
            ).to_csv(morph_dir / "blob_morphology_by_blob.csv", index=False)

            pd.DataFrame(
                {
                    "FrameIndex": [1, 2],
                    "SnMonotone": [0.25, 0.001],
                    "DissolutionRate_Sn_per_min": [0.01, 0.001],
                }
            ).to_csv(level_a_dir / "dissolution_rates.csv", index=False)

            (morph_dir / "blob_morphology_thresholds.json").write_text(
                json.dumps(
                    {
                        "reference_filter": {"BoundaryMetricValid": True, "min_area_px": 250},
                        "thresholds": {
                            "ProjectedSphericity2D": {"q75": 0.8},
                            "AxisAspectRatio": {"q75": 2.0, "q90": 3.0},
                            "AspectRatio01": {"q75": 0.7},
                            "Solidity2D": {"q25": 0.75, "q75": 0.9},
                            "ProjectedRoughness_boundary": {"q75": 1.15, "q90": 1.3},
                            "PtotalOverPouter": {"q75": 1.05},
                        },
                    }
                ),
                encoding="utf-8",
            )

            output_dir = root / "stats_out"
            result = build_shape_parameter_statistics(morph_dir, level_a_dir, output_dir=output_dir)

            self.assertEqual(result["row_counts"]["blob_rows"], 3)
            expected = {
                "g21_blob_shape_parameter_formula_notes.md",
                "blob_shape_parameter_metric_dictionary.csv",
                "blob_shape_parameter_overall_statistics.csv",
                "blob_shape_parameter_shape_valid_statistics.csv",
                "blob_shape_parameter_by_reliability_class.csv",
                "blob_shape_parameter_by_area_tier.csv",
                "blob_shape_parameter_by_class.csv",
                "blob_shape_parameter_by_sn_stage.csv",
                "blob_shape_parameter_by_class_stage.csv",
                "blob_shape_parameter_statistics_manifest.json",
            }
            self.assertTrue(expected.issubset({path.name for path in output_dir.iterdir()}))

            notes = (output_dir / "g21_blob_shape_parameter_formula_notes.md").read_text(encoding="utf-8")
            self.assertIn("ProjectedSphericity2D = 2 * sqrt(pi * Area_px) / P_outer_boundary", notes)
            self.assertIn("Circularity2D_boundary is not Wadell roundness", notes)
            self.assertIn("ProjectedRoughness_boundary is a 2D exterior-boundary proxy", notes)
            self.assertNotIn("3D roughness result", notes)

            dictionary = pd.read_csv(output_dir / "blob_shape_parameter_metric_dictionary.csv")
            self.assertIn("AR_axis_aspect_ratio", set(dictionary["MetricAlias"]))
            self.assertIn("R_projected_roughness_proxy", set(dictionary["MetricAlias"]))

            overall = pd.read_csv(output_dir / "blob_shape_parameter_overall_statistics.csv")
            ar = overall[overall["Metric"].eq("AxisAspectRatio")].iloc[0]
            self.assertAlmostEqual(ar["AreaWeightedMean"], (1.25 * 1000.0 + 4.0 * 500.0 + 1.5 * 100.0) / 1600.0)

            valid_only = pd.read_csv(output_dir / "blob_shape_parameter_shape_valid_statistics.csv")
            valid_area = valid_only[valid_only["Metric"].eq("Area_px")].iloc[0]
            self.assertEqual(valid_area["NRows"], 2)

            by_reliability = pd.read_csv(output_dir / "blob_shape_parameter_by_reliability_class.csv")
            self.assertIn("count_only_small", set(by_reliability["ReliabilityClass"]))

            by_stage = pd.read_csv(output_dir / "blob_shape_parameter_by_sn_stage.csv")
            self.assertEqual(set(by_stage["SnStage"]), {"early_depletion", "endpoint"})


if __name__ == "__main__":
    unittest.main()
