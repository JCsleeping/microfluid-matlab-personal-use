import json
import tempfile
import unittest
from pathlib import Path
from typing import Callable

import pandas as pd

from visualization.build_blob_pipeline_acceptance_review import Inputs, build_pipeline_acceptance_review


class BlobPipelineAcceptanceReviewTests(unittest.TestCase):
    def _write_fixture(
        self,
        root: Path,
        *,
        level_a_extra_rows: int = 1,
        drop_morphology_frame: int | None = None,
        add_unexpected_morphology_frame: bool = False,
        mutate_morphology: Callable[[pd.DataFrame], None] | None = None,
    ) -> Inputs:
        output_root = root / "output"
        post = output_root / "postprocess"
        morph = post / "morphology"
        v1 = morph / "shape_v1"
        stats = morph / "stats"
        out = morph / "acceptance"
        output_root.mkdir()
        post.mkdir()
        morph.mkdir()
        v1.mkdir()
        stats.mkdir()

        level_a = pd.DataFrame(
            {
                "FrameIndex": [1, 1, 2, 2],
                "BlobID": [1, 2, 1, 2],
                "Area": [300, 120, 500, 80],
            }
        )
        if level_a_extra_rows:
            extras = pd.DataFrame(
                {
                    "FrameIndex": [2] * level_a_extra_rows,
                    "BlobID": list(range(10, 10 + level_a_extra_rows)),
                    "Area": [700] * level_a_extra_rows,
                }
            )
            level_a = pd.concat([level_a, extras], ignore_index=True)
        level_a.to_csv(output_root / "blob_detail_all_frames.csv", index=False)

        morph_rows = pd.DataFrame(
            {
                "FrameIndex": [1, 1, 2, 2],
                "BlobID": [1, 2, 1, 2],
                "Area_px": [300, 120, 500, 80],
                "MajorAxisLength_px": [30, 20, 40, 15],
                "MinorAxisLength_px": [20, 10, 20, 10],
                "AxisAspectRatio": [1.5, 2.0, 2.0, 1.5],
                "AspectRatio01": [2 / 3, 0.5, 0.5, 2 / 3],
                "Solidity2D": [0.95, 0.9, 0.8, 0.92],
                "ProjectedSphericity2D": [0.9, 0.88, 0.7, 0.93],
                "Circularity2D_boundary": [0.81, 0.77, 0.49, 0.86],
                "ProjectedRoughness_boundary": [1.05, 1.03, 1.2, 1.02],
                "PtotalOverPouter": [1.0, 1.0, 1.1, 1.0],
                "P_outer_boundary": [65, 45, 90, 35],
                "Pc_outer_boundary": [62, 44, 75, 34],
                "P_total_boundary": [65, 45, 99, 35],
                "BoundaryMetricValid": [True, False, True, False],
                "AreaTier": ["large", "small", "high_confidence", "tiny"],
            }
        )
        if drop_morphology_frame is not None:
            morph_rows = morph_rows[morph_rows["FrameIndex"].ne(drop_morphology_frame)].copy()
        if add_unexpected_morphology_frame:
            extra = morph_rows.iloc[[0]].copy()
            extra["FrameIndex"] = 3
            extra["BlobID"] = 99
            morph_rows = pd.concat([morph_rows, extra], ignore_index=True)
        if mutate_morphology is not None:
            mutate_morphology(morph_rows)
        morph_rows.to_csv(morph / "blob_morphology_by_blob.csv", index=False)
        morph_rows.to_csv(morph / "blob_shape_class_by_blob.csv", index=False)
        (morph / "blob_morphology_manifest.json").write_text(
            json.dumps({"row_counts": {"blob_rows": len(morph_rows)}, "frame_counts": {"frames": 2}}),
            encoding="utf-8",
        )

        v1_rows = pd.DataFrame(
            {
                "FrameIndex": morph_rows["FrameIndex"].tolist(),
                "BlobID": morph_rows["BlobID"].tolist(),
                "ShapeClassV1": [
                    "compact_regular" if area >= 250 else ("low_area_compact_candidate_100_249" if area >= 100 else "count_only_lt100")
                    for area in morph_rows["Area_px"]
                ],
                "ShapeClassVersion": ["v1"] * len(morph_rows),
                "ShapeV1InterpretationTier": [
                    "geometry_interpretable" if area >= 250 else ("low_area_shape_caution" if area >= 100 else "count_only")
                    for area in morph_rows["Area_px"]
                ],
                "Area_px": morph_rows["Area_px"].tolist(),
                "MetricSource": ["full_duration_sidecar"] * len(morph_rows),
                "BoundaryMetricSource": ["corrected_sidecar_boundary"] * len(morph_rows),
                "DatasetSubset": ["full_duration_sidecar"] * len(morph_rows),
                "FullSidecarDerived": [True] * len(morph_rows),
            }
        )
        v1_rows.to_csv(v1 / "blob_shape_class_v1_by_blob.csv", index=False)
        (v1 / "shape_class_v1_formal_manifest.json").write_text(
            json.dumps({"decision_label": "ACCEPT", "row_counts": {"rows": len(v1_rows), "frames": 2}}),
            encoding="utf-8",
        )
        (stats / "blob_structure_statistics_manifest.json").write_text(
            json.dumps({"row_counts": {"blob_rows": len(v1_rows), "frames": 2}}),
            encoding="utf-8",
        )
        return Inputs(
            output_root=output_root,
            postprocess_dir=post,
            morphology_dir=morph,
            shape_class_v1_dir=v1,
            structure_statistics_dir=stats,
            output_dir=out,
        )

    def test_acceptance_review_writes_qc_tables_and_documents_row_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            inputs = self._write_fixture(Path(tmp), level_a_extra_rows=1)

            manifest = build_pipeline_acceptance_review(inputs)

            self.assertEqual(manifest["decision_label"], "ACCEPT_BLOB_PIPELINE_WITH_DOCUMENTED_WARNINGS")
            for name in [
                "g21_blob_pipeline_acceptance_review.md",
                "g21_blob_pipeline_run_status.md",
                "g21_blob_pipeline_acceptance_matrix.csv",
                "g21_blob_frame_coverage_summary.csv",
                "g21_blob_computation_warning_inventory.csv",
                "g21_blob_computation_qc_summary.csv",
                "g21_blob_computation_by_frame_qc.csv",
                "g21_blob_metric_range_audit.csv",
                "g21_blob_row_reconciliation.csv",
                "g21_blob_pipeline_release_manifest.json",
            ]:
                self.assertTrue((inputs.output_dir / name).exists(), name)

            qc = pd.read_csv(inputs.output_dir / "g21_blob_computation_qc_summary.csv")
            self.assertFalse(qc["Status"].eq("FAIL").any())
            recon = pd.read_csv(inputs.output_dir / "g21_blob_row_reconciliation.csv")
            level_a = recon[recon["Check"].eq("level_a_vs_morphology_rows")].iloc[0]
            self.assertEqual(level_a["Status"], "WARN")
            self.assertEqual(level_a["DifferenceRows"], 1)
            review_text = (inputs.output_dir / "g21_blob_pipeline_acceptance_review.md").read_text(encoding="utf-8")
            self.assertIn("Warning Interpretation", review_text)
            self.assertIn("downstream morphology, ShapeClassV0, ShapeClassV1", review_text)
            self.assertEqual(manifest["thresholds"]["row_diff_warn_max_rows"], 20)
            self.assertEqual(manifest["coverage"]["expected_frames"], 2)
            self.assertEqual(manifest["blocking_issues"], [])
            run_status = (inputs.output_dir / "g21_blob_pipeline_run_status.md").read_text(encoding="utf-8")
            self.assertIn("Blob Pipeline Run Status", run_status)
            self.assertIn("Expected frames", run_status)
            self.assertIn("`2`", run_status)
            self.assertIn("tracking", run_status)
            matrix = pd.read_csv(inputs.output_dir / "g21_blob_pipeline_acceptance_matrix.csv")
            self.assertTrue({"Category", "Check", "Status", "Value", "Expected", "Notes"}.issubset(matrix.columns))
            frame_summary = pd.read_csv(inputs.output_dir / "g21_blob_frame_coverage_summary.csv")
            self.assertIn("missing_frames", set(frame_summary["Metric"]))
            warnings = pd.read_csv(inputs.output_dir / "g21_blob_computation_warning_inventory.csv")
            self.assertIn("level_a_vs_morphology_rows", set(warnings["Check"]))

    def test_large_level_a_morphology_row_difference_blocks_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            inputs = self._write_fixture(Path(tmp), level_a_extra_rows=100)

            manifest = build_pipeline_acceptance_review(inputs)

            self.assertEqual(manifest["decision_label"], "BLOCKED_BLOB_PIPELINE_QC")
            self.assertIn("level_a_vs_morphology_rows", manifest["blocking_issues"])

    def test_missing_expected_final_frame_blocks_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            inputs = self._write_fixture(Path(tmp), level_a_extra_rows=0, drop_morphology_frame=2)

            manifest = build_pipeline_acceptance_review(inputs)

            self.assertEqual(manifest["decision_label"], "BLOCKED_BLOB_PIPELINE_QC")
            self.assertIn("frame_coverage_complete", manifest["blocking_issues"])
            frame_qc = pd.read_csv(inputs.output_dir / "g21_blob_computation_by_frame_qc.csv")
            self.assertIn("MISSING_FRAME", set(frame_qc["FrameStatus"]))

    def test_unexpected_frame_beyond_expected_range_blocks_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            inputs = self._write_fixture(Path(tmp), level_a_extra_rows=0, add_unexpected_morphology_frame=True)

            manifest = build_pipeline_acceptance_review(inputs)

            self.assertEqual(manifest["decision_label"], "BLOCKED_BLOB_PIPELINE_QC")
            self.assertIn("frame_coverage_complete", manifest["blocking_issues"])
            frame_qc = pd.read_csv(inputs.output_dir / "g21_blob_computation_by_frame_qc.csv")
            self.assertIn("UNEXPECTED_FRAME", set(frame_qc["FrameStatus"]))

    def test_missing_required_all_row_numeric_metric_blocks_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            def mutate(df: pd.DataFrame) -> None:
                df.loc[df.index[0], "Area_px"] = None

            inputs = self._write_fixture(Path(tmp), level_a_extra_rows=0, mutate_morphology=mutate)

            manifest = build_pipeline_acceptance_review(inputs)

            self.assertEqual(manifest["decision_label"], "BLOCKED_BLOB_PIPELINE_QC")
            self.assertIn("metric_invariant_failures", manifest["blocking_issues"])
            metric_qc = pd.read_csv(inputs.output_dir / "g21_blob_metric_range_audit.csv")
            row = metric_qc[metric_qc["Metric"].eq("Area_px_non_missing_numeric")].iloc[0]
            self.assertEqual(row["Status"], "FAIL")

    def test_missing_required_boundary_numeric_metric_blocks_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            def mutate(df: pd.DataFrame) -> None:
                df.loc[df["BoundaryMetricValid"].eq(True).idxmax(), "P_outer_boundary"] = None

            inputs = self._write_fixture(Path(tmp), level_a_extra_rows=0, mutate_morphology=mutate)

            manifest = build_pipeline_acceptance_review(inputs)

            self.assertEqual(manifest["decision_label"], "BLOCKED_BLOB_PIPELINE_QC")
            metric_qc = pd.read_csv(inputs.output_dir / "g21_blob_metric_range_audit.csv")
            row = metric_qc[metric_qc["Metric"].eq("P_outer_boundary_non_missing_numeric")].iloc[0]
            self.assertEqual(row["Status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
