import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from visualization.build_blob_pipeline_acceptance_review import Inputs, build_pipeline_acceptance_review


class BlobPipelineAcceptanceReviewTests(unittest.TestCase):
    def test_acceptance_review_writes_qc_tables_and_documents_row_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
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

            pd.DataFrame(
                {
                    "FrameIndex": [1, 1, 2, 2, 2],
                    "BlobID": [1, 2, 1, 2, 3],
                    "Area": [300, 120, 500, 80, 700],
                }
            ).to_csv(output_root / "blob_detail_all_frames.csv", index=False)

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
            morph_rows.to_csv(morph / "blob_morphology_by_blob.csv", index=False)
            morph_rows.to_csv(morph / "blob_shape_class_by_blob.csv", index=False)
            (morph / "blob_morphology_manifest.json").write_text(
                json.dumps({"row_counts": {"blob_rows": 4}, "frame_counts": {"frames": 2}}),
                encoding="utf-8",
            )

            v1_rows = pd.DataFrame(
                {
                    "FrameIndex": [1, 1, 2, 2],
                    "BlobID": [1, 2, 1, 2],
                    "ShapeClassV1": [
                        "compact_regular",
                        "low_area_compact_candidate_100_249",
                        "moderately_concave",
                        "count_only_lt100",
                    ],
                    "ShapeClassVersion": ["v1"] * 4,
                    "ShapeV1InterpretationTier": [
                        "geometry_interpretable",
                        "low_area_shape_caution",
                        "geometry_interpretable",
                        "count_only",
                    ],
                    "Area_px": [300, 120, 500, 80],
                    "MetricSource": ["full_duration_sidecar"] * 4,
                    "BoundaryMetricSource": ["corrected_sidecar_boundary"] * 4,
                    "DatasetSubset": ["full_duration_sidecar"] * 4,
                    "FullSidecarDerived": [True] * 4,
                }
            )
            v1_rows.to_csv(v1 / "blob_shape_class_v1_by_blob.csv", index=False)
            (v1 / "shape_class_v1_formal_manifest.json").write_text(
                json.dumps({"decision_label": "ACCEPT", "row_counts": {"rows": 4, "frames": 2}}),
                encoding="utf-8",
            )
            (stats / "blob_structure_statistics_manifest.json").write_text(
                json.dumps({"row_counts": {"blob_rows": 4, "frames": 2}}),
                encoding="utf-8",
            )

            manifest = build_pipeline_acceptance_review(
                Inputs(
                    output_root=output_root,
                    postprocess_dir=post,
                    morphology_dir=morph,
                    shape_class_v1_dir=v1,
                    structure_statistics_dir=stats,
                    output_dir=out,
                )
            )

            self.assertEqual(manifest["decision_label"], "ACCEPT_BLOB_PIPELINE_WITH_DOCUMENTED_WARNINGS")
            for name in [
                "g21_blob_pipeline_acceptance_review.md",
                "g21_blob_computation_qc_summary.csv",
                "g21_blob_computation_by_frame_qc.csv",
                "g21_blob_metric_range_audit.csv",
                "g21_blob_row_reconciliation.csv",
                "g21_blob_pipeline_release_manifest.json",
            ]:
                self.assertTrue((out / name).exists(), name)

            qc = pd.read_csv(out / "g21_blob_computation_qc_summary.csv")
            self.assertFalse(qc["Status"].eq("FAIL").any())
            recon = pd.read_csv(out / "g21_blob_row_reconciliation.csv")
            level_a = recon[recon["Check"].eq("level_a_vs_morphology_rows")].iloc[0]
            self.assertEqual(level_a["Status"], "WARN")
            self.assertEqual(level_a["DifferenceRows"], 1)
            review_text = (out / "g21_blob_pipeline_acceptance_review.md").read_text(encoding="utf-8")
            self.assertIn("Warning Interpretation", review_text)
            self.assertIn("downstream morphology, ShapeClassV0, ShapeClassV1", review_text)


if __name__ == "__main__":
    unittest.main()
