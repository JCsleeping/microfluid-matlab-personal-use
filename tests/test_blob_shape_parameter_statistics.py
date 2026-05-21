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
            self.assertIn("AxisAspectRatio and AspectRatio01 are reciprocal forms", notes)
            self.assertIn("ProjectedSphericity2D and Circularity2D_boundary are mathematically related", notes)
            self.assertIn("ShapeClassV0 and ShapeClassV1 must not be mixed", notes)
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

    def test_statistics_package_supports_shape_class_v1_formal_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            morph_dir = root / "morphology"
            v1_dir = root / "v1_formal"
            level_a_dir = root / "level_a"
            output_dir = root / "stats_v1"
            morph_dir.mkdir()
            v1_dir.mkdir()
            level_a_dir.mkdir()

            pd.DataFrame(
                [
                    {
                        "FrameIndex": 1,
                        "RealTime_s": 0.0,
                        "BlobID": 1,
                        "ShapeClassV0": "small_unclassified",
                        "ShapeClassV1": "count_only_lt100",
                        "ShapeClassV1Reason": "area_lt_100_count_only",
                        "ShapeClassVersion": "v1",
                        "ShapeV1InterpretationTier": "count_only",
                        "MetricSource": "full_duration_sidecar",
                        "BoundaryMetricSource": "corrected_sidecar_boundary",
                        "DatasetSubset": "full_duration_sidecar",
                        "FullSidecarDerived": True,
                        "Area_px": 80.0,
                        "AreaTier": "tiny",
                        "MajorAxisLength_px": 15.0,
                        "MinorAxisLength_px": 10.0,
                        "Solidity2D": 0.9,
                        "ProjectedSphericity2D": 0.8,
                        "Circularity2D_boundary": 0.64,
                        "AspectRatio01": 2.0 / 3.0,
                        "AxisAspectRatio": 1.5,
                        "ProjectedRoughness_boundary": 1.05,
                        "PtotalOverPouter": 1.0,
                    },
                    {
                        "FrameIndex": 2,
                        "RealTime_s": 1.0,
                        "BlobID": 2,
                        "ShapeClassV0": "compact_round",
                        "ShapeClassV1": "compact_regular",
                        "ShapeClassV1Reason": "renamed_v0_compact_round",
                        "ShapeClassVersion": "v1",
                        "ShapeV1InterpretationTier": "geometry_interpretable",
                        "MetricSource": "full_duration_sidecar",
                        "BoundaryMetricSource": "corrected_sidecar_boundary",
                        "DatasetSubset": "full_duration_sidecar",
                        "FullSidecarDerived": True,
                        "Area_px": 500.0,
                        "AreaTier": "large",
                        "MajorAxisLength_px": 40.0,
                        "MinorAxisLength_px": 35.0,
                        "Solidity2D": 0.95,
                        "ProjectedSphericity2D": 0.9,
                        "Circularity2D_boundary": 0.81,
                        "AspectRatio01": 0.875,
                        "AxisAspectRatio": 40.0 / 35.0,
                        "ProjectedRoughness_boundary": 1.04,
                        "PtotalOverPouter": 1.0,
                    },
                    {
                        "FrameIndex": 2,
                        "RealTime_s": 1.0,
                        "BlobID": 3,
                        "ShapeClassV0": "ambiguous_valid",
                        "ShapeClassV1": "near_compact_regular",
                        "ShapeClassV1Reason": "intermediate_compact_regular_v1",
                        "ShapeClassVersion": "v1",
                        "ShapeV1InterpretationTier": "geometry_interpretable",
                        "MetricSource": "full_duration_sidecar",
                        "BoundaryMetricSource": "corrected_sidecar_boundary",
                        "DatasetSubset": "full_duration_sidecar",
                        "FullSidecarDerived": True,
                        "Area_px": 700.0,
                        "AreaTier": "large",
                        "MajorAxisLength_px": 55.0,
                        "MinorAxisLength_px": 40.0,
                        "Solidity2D": 0.93,
                        "ProjectedSphericity2D": 0.86,
                        "Circularity2D_boundary": 0.74,
                        "AspectRatio01": 40.0 / 55.0,
                        "AxisAspectRatio": 55.0 / 40.0,
                        "ProjectedRoughness_boundary": 1.08,
                        "PtotalOverPouter": 1.0,
                    },
                ]
            ).to_csv(v1_dir / "blob_shape_class_v1_by_blob.csv", index=False)
            (v1_dir / "shape_class_v1_formal_manifest.json").write_text(
                json.dumps(
                    {
                        "decision_label": "ACCEPT_SHAPE_CLASS_V1_FORMAL_WITH_SCOPE_LIMITS",
                        "row_counts": {"rows": 3, "frames": 2},
                    }
                ),
                encoding="utf-8",
            )
            pd.DataFrame({"FrameIndex": [1, 2], "SnMonotone": [0.25, 0.001]}).to_csv(
                level_a_dir / "dissolution_rates.csv", index=False
            )
            (morph_dir / "blob_morphology_thresholds.json").write_text(
                json.dumps({"thresholds": {"AxisAspectRatio": {"q75": 1.2, "q90": 2.0}}}),
                encoding="utf-8",
            )

            manifest = build_shape_parameter_statistics(
                morph_dir,
                level_a_dir,
                output_dir=output_dir,
                shape_class_version="v1",
                shape_class_v1_dir=v1_dir,
            )

            self.assertEqual(manifest["shape_class"]["version"], "v1")
            self.assertEqual(manifest["row_counts"]["shape_valid_rows"], 2)
            expected = {
                "g21_blob_shape_parameter_formula_notes_v1.md",
                "g21_shape_class_v1_decision_rules.md",
                "g21_shape_class_v1_field_dictionary.md",
            }
            self.assertTrue(expected.issubset({path.name for path in output_dir.iterdir()}))

            by_class = pd.read_csv(output_dir / "blob_shape_parameter_by_class.csv")
            self.assertIn("compact_regular", set(by_class["ShapeClass"]))
            self.assertIn("count_only_lt100", set(by_class["ShapeClass"]))
            self.assertNotIn("compact_round", set(by_class["ShapeClass"]))

            notes = (output_dir / "g21_blob_shape_parameter_formula_notes_v1.md").read_text(encoding="utf-8")
            self.assertIn("Area_px < 100 -> count_only_lt100", notes)
            self.assertIn("not 3D roughness", notes)
            decision_rules = (output_dir / "g21_shape_class_v1_decision_rules.md").read_text(encoding="utf-8")
            self.assertIn("low_area_*_100_249", decision_rules)


if __name__ == "__main__":
    unittest.main()
