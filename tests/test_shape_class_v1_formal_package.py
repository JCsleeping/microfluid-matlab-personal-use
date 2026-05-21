import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from visualization.build_shape_class_v1_formal_package import build_shape_class_v1_formal_package


class ShapeClassV1FormalPackageTests(unittest.TestCase):
    def test_formal_package_writes_acceptance_artifacts_and_conserves_transition_totals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            morphology_dir = root / "morphology"
            refinement_dir = root / "v1_refinement"
            level_a_dir = root / "level_a"
            morphology_dir.mkdir()
            refinement_dir.mkdir()
            level_a_dir.mkdir()

            rows = pd.DataFrame(
                [
                    {
                        "FrameIndex": 1,
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
                    },
                    {
                        "FrameIndex": 1,
                        "BlobID": 2,
                        "ShapeClassV0": "small_unclassified",
                        "ShapeClassV1": "low_area_compact_candidate_100_249",
                        "ShapeClassV1Reason": "area_100_249_compact_projected_shape_caution",
                        "ShapeClassVersion": "v1",
                        "ShapeV1InterpretationTier": "low_area_shape_caution",
                        "MetricSource": "full_duration_sidecar",
                        "BoundaryMetricSource": "corrected_sidecar_boundary",
                        "DatasetSubset": "full_duration_sidecar",
                        "FullSidecarDerived": True,
                        "Area_px": 150.0,
                    },
                    {
                        "FrameIndex": 2,
                        "BlobID": 3,
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
                    },
                    {
                        "FrameIndex": 2,
                        "BlobID": 4,
                        "ShapeClassV0": "elongated",
                        "ShapeClassV1": "elongated",
                        "ShapeClassV1Reason": "axis_aspect_ratio_ge_q90",
                        "ShapeClassVersion": "v1",
                        "ShapeV1InterpretationTier": "geometry_interpretable",
                        "MetricSource": "full_duration_sidecar",
                        "BoundaryMetricSource": "corrected_sidecar_boundary",
                        "DatasetSubset": "full_duration_sidecar",
                        "FullSidecarDerived": True,
                        "Area_px": 700.0,
                    },
                    {
                        "FrameIndex": 2,
                        "BlobID": 5,
                        "ShapeClassV0": "branched_complex",
                        "ShapeClassV1": "branched_complex",
                        "ShapeClassV1Reason": "preserved_v0_branched_complex",
                        "ShapeClassVersion": "v1",
                        "ShapeV1InterpretationTier": "geometry_interpretable",
                        "MetricSource": "full_duration_sidecar",
                        "BoundaryMetricSource": "corrected_sidecar_boundary",
                        "DatasetSubset": "full_duration_sidecar",
                        "FullSidecarDerived": True,
                        "Area_px": 900.0,
                    },
                    {
                        "FrameIndex": 2,
                        "BlobID": 6,
                        "ShapeClassV0": "ambiguous_valid",
                        "ShapeClassV1": "ambiguous_valid",
                        "ShapeClassV1Reason": "valid_geometry_fallback_v1",
                        "ShapeClassVersion": "v1",
                        "ShapeV1InterpretationTier": "geometry_interpretable",
                        "MetricSource": "full_duration_sidecar",
                        "BoundaryMetricSource": "corrected_sidecar_boundary",
                        "DatasetSubset": "full_duration_sidecar",
                        "FullSidecarDerived": True,
                        "Area_px": 600.0,
                    },
                ]
            )
            rows.to_csv(refinement_dir / "blob_shape_class_v1_by_blob.csv", index=False)
            (refinement_dir / "shape_class_v1_manifest.json").write_text(
                json.dumps({"qc": {"decision_label": "PASS"}, "row_counts": {"rows": 6, "frames": 2}}),
                encoding="utf-8",
            )
            pd.DataFrame({"FrameIndex": [1, 2], "SnMonotone": [0.25, 0.001]}).to_csv(
                level_a_dir / "dissolution_rates.csv", index=False
            )
            (morphology_dir / "blob_morphology_manifest.json").write_text(
                json.dumps({"git_commit": "abc123", "row_counts": {"blob_rows": 6}}),
                encoding="utf-8",
            )

            out_dir = root / "formal"
            manifest = build_shape_class_v1_formal_package(
                morphology_dir=morphology_dir,
                shape_class_v1_dir=refinement_dir,
                level_a_dir=level_a_dir,
                output_dir=out_dir,
            )

            expected = {
                "blob_shape_class_v1_by_blob.csv",
                "shape_class_v1_summary_by_class.csv",
                "shape_class_v1_summary_by_stage.csv",
                "shape_class_v0_to_v1_transition_count.csv",
                "shape_class_v0_to_v1_transition_area.csv",
                "shape_class_v0_to_v1_transition_by_sn_stage_count.csv",
                "shape_class_v0_to_v1_transition_by_sn_stage_area.csv",
                "shape_class_v1_gate_audit.csv",
                "shape_class_v1_acceptance_gate_audit.csv",
                "shape_class_v1_schema.md",
                "g21_shape_class_v1_acceptance_review.md",
                "g21_shape_class_v1_data_product_acceptance_review.md",
                "g21_blob_shape_parameter_formula_notes_v1.md",
                "g21_shape_class_v1_decision_rules.md",
                "g21_shape_class_v1_field_dictionary.md",
                "shape_class_v1_formal_manifest.json",
            }
            self.assertTrue(expected.issubset({path.name for path in out_dir.iterdir()}))

            formal = pd.read_csv(out_dir / "blob_shape_class_v1_by_blob.csv")
            for column in [
                "ShapeClassVersion",
                "ShapeClassSource",
                "MetricSource",
                "BoundaryMetricSource",
                "DatasetSubset",
                "FullSidecarDerived",
                "AreaThresholdVersion",
                "InputMorphologyProduct",
                "InputShapeClassV1Dir",
                "GitCommit",
                "SnStage",
            ]:
                self.assertIn(column, formal.columns)

            gate = pd.read_csv(out_dir / "shape_class_v1_gate_audit.csv")
            self.assertTrue((gate["Status"] == "PASS").all())

            count_transition = pd.read_csv(out_dir / "shape_class_v0_to_v1_transition_count.csv")
            count_sum = count_transition.drop(columns=["ShapeClassV0"]).to_numpy().sum()
            self.assertEqual(count_sum, 6)

            area_transition = pd.read_csv(out_dir / "shape_class_v0_to_v1_transition_area.csv")
            area_sum = area_transition.drop(columns=["ShapeClassV0"]).to_numpy().sum()
            self.assertAlmostEqual(area_sum, rows["Area_px"].sum())

            stage_count = pd.read_csv(out_dir / "shape_class_v0_to_v1_transition_by_sn_stage_count.csv")
            self.assertEqual(stage_count["Count"].sum(), 6)
            stage_area = pd.read_csv(out_dir / "shape_class_v0_to_v1_transition_by_sn_stage_area.csv")
            self.assertAlmostEqual(stage_area["AreaSum_px"].sum(), rows["Area_px"].sum())

            review = (out_dir / "g21_shape_class_v1_acceptance_review.md").read_text(encoding="utf-8")
            self.assertIn("Decision: `ACCEPT_SHAPE_CLASS_V1_FORMAL_WITH_SCOPE_LIMITS`", review)
            self.assertIn("100 <= Area < 250 px remains low-area projected-shape caution", review)
            product_review = (out_dir / "g21_shape_class_v1_data_product_acceptance_review.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("Decision: `ACCEPT_WITH_SCOPE_LIMITS`", product_review)
            self.assertIn("Diagnostic flags AF-AL", product_review)
            formula_notes = (out_dir / "g21_blob_shape_parameter_formula_notes_v1.md").read_text(encoding="utf-8")
            self.assertIn("not Wadell roundness", formula_notes)
            self.assertIn("not 3D roughness", formula_notes)
            rules = (out_dir / "g21_shape_class_v1_decision_rules.md").read_text(encoding="utf-8")
            self.assertIn("Area_px < 100 -> count_only_lt100", rules)
            dictionary = (out_dir / "g21_shape_class_v1_field_dictionary.md").read_text(encoding="utf-8")
            self.assertIn("CircularityArtifactFlag", dictionary)

            self.assertEqual(manifest["decision_label"], "ACCEPT_SHAPE_CLASS_V1_FORMAL_WITH_SCOPE_LIMITS")
            self.assertEqual(manifest["conservation"]["transition_count_sum"], 6)


if __name__ == "__main__":
    unittest.main()
