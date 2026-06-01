import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from visualization.build_blob_structure_statistics import (
    Inputs,
    assign_sn_stage,
    build_blob_structure_statistics,
)


class BlobStructureStatisticsTests(unittest.TestCase):
    def test_assign_sn_stage_endpoint_takes_precedence(self):
        level_a = pd.DataFrame(
            {
                "FrameIndex": [1, 2, 3, 4, 5, 6],
                "SnMonotone": [0.25, 0.15, 0.07, 0.02, 0.004, 0.22],
                "DissolutionRate_Sn_per_min": [0.1] * 6,
            }
        )
        staged = assign_sn_stage(level_a)
        self.assertEqual(staged.loc[0, "SnStage"], "early_depletion")
        self.assertEqual(staged.loc[1, "SnStage"], "active_dissolution")
        self.assertEqual(staged.loc[3, "SnStage"], "late_depletion")
        self.assertEqual(staged.loc[4, "SnStage"], "endpoint")
        self.assertEqual(staged.loc[5, "SnStage"], "endpoint")

    def test_build_statistics_outputs_scope_and_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            morph = root / "morph"
            level_a = root / "level_a"
            out = root / "stats"
            atlas = morph / "representative_blob_atlas"
            morph.mkdir()
            level_a.mkdir()
            atlas.mkdir()

            pd.DataFrame(
                {
                    "FrameIndex": [1, 1, 2, 3, 4, 4],
                    "RealTime_s": [0, 0, 1, 2, 3, 3],
                    "BlobID": [1, 2, 1, 1, 1, 2],
                    "ShapeClass": [
                        "compact_round",
                        "small_unclassified",
                        "elongated",
                        "boundary_invalid",
                        "branched_complex",
                        "ambiguous_valid",
                    ],
                    "ShapeClassReason": ["x"] * 6,
                    "ShapeValid": [True, False, True, False, True, True],
                    "ShapeInvalidReason": ["", "area_lt_250", "", "boundary_metric_invalid", "", ""],
                    "ReliabilityClass": [
                        "high_confidence",
                        "count_only",
                        "geometry_valid",
                        "boundary_invalid",
                        "high_confidence",
                        "geometry_valid",
                    ],
                    "Area_px": [1000, 20, 300, 600, 1500, 450],
                    "AreaTier": ["high_confidence", "tiny", "medium", "large", "high_confidence", "medium"],
                    "ProjectedSphericity2D": [0.8, 0.5, 0.55, 0.4, 0.45, 0.65],
                    "Circularity2D_boundary": [0.7, 1.2, 0.5, 1.1, 0.4, 0.6],
                    "AspectRatio01": [0.9, 0.5, 0.2, 0.4, 0.25, 0.7],
                    "AxisAspectRatio": [1.1, 2.0, 5.0, 2.5, 4.5, 1.6],
                    "Solidity2D": [0.95, 0.8, 0.7, 0.6, 0.4, 0.85],
                    "ProjectedRoughness_boundary": [1.1, 0.9, 1.4, 1.2, 2.0, 1.2],
                    "PtotalOverPouter": [1.0, 1.0, 1.1, 1.2, 2.5, 1.0],
                    "ProjectedRegularity2D": [0.88, 0.6, 0.48, 0.47, 0.37, 0.73],
                    "A_blob_Atotal": [0.4, 0.01, 0.2, 0.3, 0.5, 0.2],
                }
            ).to_csv(morph / "blob_shape_class_by_blob.csv", index=False)

            pd.DataFrame(
                {
                    "FrameIndex": [1, 2, 3, 4],
                    "SnMonotone": [0.25, 0.10, 0.02, 0.001],
                    "DissolutionRate_Sn_per_min": [0.1, 0.2, 0.3, 0.4],
                }
            ).to_csv(level_a / "dissolution_rates.csv", index=False)

            pd.DataFrame(
                {
                    "FrameIndex": [1],
                    "BlobID": [1],
                    "ShapeClass": ["compact_round"],
                    "Status": ["RENDERED"],
                }
            ).to_csv(atlas / "representative_blob_atlas_manifest.csv", index=False)

            manifest = build_blob_structure_statistics(Inputs(morphology_dir=morph, level_a_dir=level_a, output_dir=out))

            self.assertEqual(manifest["row_counts"]["blob_rows"], 6)
            self.assertFalse(manifest["scope"]["true_wadell_roundness"])
            self.assertFalse(manifest["scope"]["roughness_3d"])

            for name in [
                "blob_structure_metric_dictionary.md",
                "blob_structure_class_summary.csv",
                "blob_structure_by_stage.csv",
                "blob_structure_transition_by_sn_stage.csv",
                "blob_structure_representative_atlas_review.md",
                "blob_structure_statistics_manifest.json",
            ]:
                self.assertTrue((out / name).exists(), name)

            dictionary = (out / "blob_structure_metric_dictionary.md").read_text(encoding="utf-8")
            self.assertIn("not Wadell roundness", dictionary)
            self.assertIn("not 3D sphericity", dictionary)
            self.assertIn("2D exterior-boundary proxy", dictionary)

            class_summary = pd.read_csv(out / "blob_structure_class_summary.csv")
            small = class_summary[class_summary["ShapeClass"] == "small_unclassified"].iloc[0]
            self.assertFalse(bool(small["InterpretationAllowed"]))

            by_stage = pd.read_csv(out / "blob_structure_by_stage.csv")
            self.assertIn("endpoint", set(by_stage["SnStage"]))
            for _, group in by_stage.groupby("SnStage"):
                self.assertAlmostEqual(group["StageCountFraction"].sum(), 1.0)
                self.assertAlmostEqual(group["StageAreaFraction"].sum(), 1.0)

            saved_manifest = json.loads((out / "blob_structure_statistics_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(saved_manifest["row_counts"]["frames"], 4)

    def test_build_statistics_supports_shape_class_v1_formal_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            morph = root / "morph"
            level_a = root / "level_a"
            v1 = root / "v1_formal"
            out = root / "stats_v1"
            morph.mkdir()
            level_a.mkdir()
            v1.mkdir()

            pd.DataFrame(
                {
                    "FrameIndex": [1, 1, 2, 2],
                    "RealTime_s": [0, 0, 1, 1],
                    "BlobID": [1, 2, 3, 4],
                    "ShapeClassV0": ["small_unclassified", "small_unclassified", "compact_round", "ambiguous_valid"],
                    "ShapeClassV1": [
                        "count_only_lt100",
                        "low_area_compact_candidate_100_249",
                        "compact_regular",
                        "near_compact_regular",
                    ],
                    "ShapeClassV1Reason": [
                        "area_lt_100_count_only",
                        "area_100_249_compact_projected_shape_caution",
                        "renamed_v0_compact_round",
                        "intermediate_compact_regular_v1",
                    ],
                    "ShapeClassVersion": ["v1"] * 4,
                    "ShapeV1InterpretationTier": [
                        "count_only",
                        "low_area_shape_caution",
                        "geometry_interpretable",
                        "geometry_interpretable",
                    ],
                    "MetricSource": ["full_duration_sidecar"] * 4,
                    "BoundaryMetricSource": ["corrected_sidecar_boundary"] * 4,
                    "DatasetSubset": ["full_duration_sidecar"] * 4,
                    "FullSidecarDerived": [True] * 4,
                    "ShapeClassSource": ["shape_class_v1_formal_package"] * 4,
                    "AreaThresholdVersion": ["area_gate_v1_lt100_100_249_ge250_ge500"] * 4,
                    "Area_px": [80, 150, 500, 700],
                    "AreaTier": ["tiny", "small", "large", "large"],
                    "ProjectedSphericity2D": [0.9, 0.86, 0.91, 0.86],
                    "Circularity2D_boundary": [1.1, 0.9, 0.8, 0.7],
                    "AspectRatio01": [0.8, 0.75, 0.9, 0.7],
                    "AxisAspectRatio": [1.25, 1.33, 1.1, 1.5],
                    "Solidity2D": [0.9, 0.92, 0.96, 0.93],
                    "ProjectedRoughness_boundary": [1.0, 1.1, 1.05, 1.08],
                    "PtotalOverPouter": [1.0, 1.0, 1.0, 1.0],
                    "ProjectedRegularity2D": [0.85, 0.84, 0.92, 0.83],
                }
            ).to_csv(v1 / "blob_shape_class_v1_by_blob.csv", index=False)

            (v1 / "shape_class_v1_formal_manifest.json").write_text(
                json.dumps(
                    {
                        "decision_label": "ACCEPT_SHAPE_CLASS_V1_FORMAL_WITH_SCOPE_LIMITS",
                        "row_counts": {"rows": 4, "frames": 2},
                    }
                ),
                encoding="utf-8",
            )

            pd.DataFrame(
                {
                    "FrameIndex": [1, 2],
                    "SnMonotone": [0.25, 0.001],
                    "DissolutionRate_Sn_per_min": [0.1, 0.2],
                }
            ).to_csv(level_a / "dissolution_rates.csv", index=False)

            manifest = build_blob_structure_statistics(
                Inputs(
                    morphology_dir=morph,
                    level_a_dir=level_a,
                    output_dir=out,
                    shape_class_version="v1",
                    shape_class_v1_dir=v1,
                )
            )

            self.assertEqual(manifest["shape_class"]["version"], "v1")
            self.assertEqual(manifest["shape_class"]["active_shape_class_column"], "ShapeClassActive")
            self.assertEqual(manifest["row_counts"]["blob_rows"], 4)
            self.assertEqual(manifest["row_counts"]["boundary_interpretable_rows"], 2)

            class_summary = pd.read_csv(out / "blob_structure_class_summary.csv")
            self.assertIn("compact_regular", set(class_summary["ShapeClass"]))
            count_only = class_summary[class_summary["ShapeClass"] == "count_only_lt100"].iloc[0]
            self.assertFalse(bool(count_only["InterpretationAllowed"]))

            by_stage = pd.read_csv(out / "blob_structure_by_stage.csv")
            self.assertIn("near_compact_regular", set(by_stage["ShapeClass"]))
            for _, group in by_stage.groupby("SnStage"):
                self.assertAlmostEqual(group["StageCountFraction"].sum(), 1.0)
                self.assertAlmostEqual(group["StageAreaFraction"].sum(), 1.0)

            saved_manifest = json.loads((out / "blob_structure_statistics_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(saved_manifest["shape_class"]["source_file"], str(v1 / "blob_shape_class_v1_by_blob.csv"))

    def test_build_statistics_rejects_blocked_shape_class_v1_formal_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            morph = root / "morph"
            level_a = root / "level_a"
            v1 = root / "v1_formal"
            out = root / "stats_v1"
            morph.mkdir()
            level_a.mkdir()
            v1.mkdir()

            pd.DataFrame(
                {
                    "FrameIndex": [1],
                    "BlobID": [1],
                    "ShapeClassV1": ["compact_regular"],
                    "ShapeClassV1Reason": ["renamed_v0_compact_round"],
                    "ShapeClassVersion": ["v1"],
                    "ShapeV1InterpretationTier": ["geometry_interpretable"],
                    "Area_px": [500],
                }
            ).to_csv(v1 / "blob_shape_class_v1_by_blob.csv", index=False)
            (v1 / "shape_class_v1_formal_manifest.json").write_text(
                json.dumps({"decision_label": "BLOCKED_SHAPE_CLASS_V1_FORMAL", "row_counts": {"rows": 1}}),
                encoding="utf-8",
            )
            pd.DataFrame({"FrameIndex": [1], "SnMonotone": [0.25], "DissolutionRate_Sn_per_min": [0.1]}).to_csv(
                level_a / "dissolution_rates.csv", index=False
            )

            with self.assertRaisesRegex(ValueError, "blocked"):
                build_blob_structure_statistics(
                    Inputs(
                        morphology_dir=morph,
                        level_a_dir=level_a,
                        output_dir=out,
                        shape_class_version="v1",
                        shape_class_v1_dir=v1,
                    )
                )


if __name__ == "__main__":
    unittest.main()
