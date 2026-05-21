import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from visualization.build_blob_structure_data_figure_bundle import Inputs, build_data_figure_bundle


class BlobStructureDataFigureBundleTests(unittest.TestCase):
    def _make_fixture(self, root: Path) -> Inputs:
        post = root / "postprocess"
        morph = root / "morphology"
        v1 = morph / "shape_v1"
        stats = morph / "stats"
        acceptance = morph / "acceptance"
        atlas = v1 / "representative_blob_atlas"
        out = root / "bundle"
        for path in [post, morph, v1, stats, acceptance, atlas]:
            path.mkdir(parents=True)

        pd.DataFrame(
            {
                "FrameIndex": [1, 2, 3],
                "RealTime_s": [0.0, 1.0, 2.0],
                "SnMonotone": [0.25, 0.08, 0.001],
                "DissolutionRate_Sn_per_min": [0.1, 0.2, 0.05],
            }
        ).to_csv(post / "dissolution_rates.csv", index=False)

        by_blob = pd.DataFrame(
            {
                "FrameIndex": [1, 1, 2, 2, 3],
                "RealTime_s": [0, 0, 1, 1, 2],
                "BlobID": [1, 2, 1, 2, 1],
                "ShapeClassV1": [
                    "compact_regular",
                    "count_only_lt100",
                    "moderately_elongated",
                    "low_area_compact_candidate_100_249",
                    "branched_complex",
                ],
                "ShapeClassV1Reason": ["rule"] * 5,
                "ShapeClassVersion": ["v1"] * 5,
                "ShapeV1InterpretationTier": [
                    "geometry_interpretable",
                    "count_only",
                    "geometry_interpretable",
                    "low_area_shape_caution",
                    "geometry_interpretable",
                ],
                "MetricSource": ["full_duration_projected_shape"] * 5,
                "BoundaryMetricSource": ["level_a_projected_boundary_proxy"] * 5,
                "CorrectedBoundaryAvailable": [True, False, True, False, True],
                "DatasetSubset": ["full_duration_projected_shape"] * 5,
                "FullSidecarDerived": [False] * 5,
                "Area_px": [500, 50, 800, 150, 1200],
                "AreaTier": ["large", "tiny", "high_confidence", "small", "high_confidence"],
                "BoundaryMetricValid": [True, False, True, False, True],
                "ProjectedSphericity2D": [0.9, 0.75, 0.55, 0.86, 0.45],
                "Circularity2D_boundary": [0.81, 0.56, 0.30, 0.74, 0.20],
                "AspectRatio01": [0.85, 0.8, 0.35, 0.75, 0.25],
                "AxisAspectRatio": [1.18, 1.25, 2.85, 1.33, 4.0],
                "Solidity2D": [0.95, 0.9, 0.8, 0.92, 0.45],
                "ProjectedRoughness_boundary": [1.05, 1.0, 1.25, 1.1, 2.0],
                "PtotalOverPouter": [1.0, 1.0, 1.0, 1.0, 1.4],
                "ProjectedRegularity2D": [0.90, 0.82, 0.57, 0.84, 0.38],
            }
        )
        by_blob.to_csv(v1 / "blob_shape_class_v1_by_blob.csv", index=False)

        (v1 / "shape_class_v1_formal_manifest.json").write_text(
            json.dumps(
                {
                    "decision_label": "ACCEPT_SHAPE_CLASS_V1_FORMAL_WITH_SCOPE_LIMITS",
                    "row_counts": {"rows": 5, "frames": 3},
                }
            ),
            encoding="utf-8",
        )

        by_blob.groupby("ShapeClassV1", as_index=False).agg(
            NRows=("BlobID", "count"),
            AreaSum_px=("Area_px", "sum"),
        ).assign(
            CountFraction=lambda df: df["NRows"] / df["NRows"].sum(),
            AreaFraction=lambda df: df["AreaSum_px"] / df["AreaSum_px"].sum(),
        ).to_csv(v1 / "shape_class_v1_summary_by_class.csv", index=False)

        stage_map = {1: "early_depletion", 2: "active_dissolution", 3: "endpoint"}
        by_stage = by_blob.assign(SnStage=by_blob["FrameIndex"].map(stage_map))
        by_stage.groupby(["SnStage", "ShapeClassV1"], as_index=False).agg(
            NRows=("BlobID", "count"),
            AreaSum_px=("Area_px", "sum"),
        ).assign(
            CountFraction=1.0,
            AreaFraction=1.0,
        ).to_csv(v1 / "shape_class_v1_summary_by_stage.csv", index=False)

        pd.DataFrame(
            {
                "ShapeClass": ["compact_regular", "moderately_elongated"],
                "NBlobs": [1, 1],
                "CountFraction": [0.2, 0.2],
                "AreaSum_px": [500, 800],
                "AreaFraction": [0.185, 0.296],
            }
        ).to_csv(stats / "blob_structure_class_summary.csv", index=False)
        pd.DataFrame(
            {
                "SnStage": ["early_depletion", "active_dissolution", "endpoint"],
                "ShapeClass": ["compact_regular", "moderately_elongated", "branched_complex"],
                "NBlobs": [1, 1, 1],
                "CountFraction": [0.5, 0.5, 1.0],
                "AreaSum_px": [500, 800, 1200],
                "AreaFraction": [0.91, 0.84, 1.0],
            }
        ).to_csv(stats / "blob_structure_by_stage.csv", index=False)
        pd.DataFrame(
            {
                "SnStage": ["early_depletion", "active_dissolution", "endpoint"],
                "NFrames": [1, 1, 1],
                "NBlobs": [2, 2, 1],
                "AreaSum_px": [550, 950, 1200],
            }
        ).to_csv(stats / "blob_structure_transition_by_sn_stage.csv", index=False)
        (stats / "blob_structure_statistics_manifest.json").write_text(
            json.dumps({"row_counts": {"blob_rows": 5, "frames": 3}}),
            encoding="utf-8",
        )

        panel_path = atlas / "panel.png"
        Image.fromarray(np.full((24, 24, 3), 220, dtype=np.uint8)).save(panel_path)
        pd.DataFrame(
            {
                "FrameIndex": [1],
                "BlobID": [1],
                "ShapeClass": ["compact_regular"],
                "ExemplarType": ["class_medoid"],
                "Status": ["RENDERED"],
                "PanelPath": [str(panel_path)],
            }
        ).to_csv(atlas / "representative_blob_atlas_manifest.csv", index=False)
        pd.DataFrame(
            {
                "FrameIndex": [1],
                "BlobID": [1],
                "ShapeClass": ["compact_regular"],
                "ExemplarType": ["class_medoid"],
                "Status": ["RENDERED"],
                "PanelPath": [str(panel_path)],
                "Area_px": [500],
            }
        ).to_csv(v1 / "representative_blob_candidates.csv", index=False)

        pd.DataFrame(
            {
                "Metric": ["expected_frames", "frame_rows_in_qc", "missing_frames", "row_mismatch_frames"],
                "Value": [3, 3, 0, 0],
            }
        ).to_csv(acceptance / "g21_blob_frame_coverage_summary.csv", index=False)
        pd.DataFrame(
            {
                "Gate": ["frame_coverage", "row_mismatch_frames"],
                "Status": ["PASS", "PASS"],
                "Value": [3, 0],
                "Expected": ["3", "0"],
                "Notes": ["", ""],
            }
        ).to_csv(acceptance / "g21_blob_computation_qc_summary.csv", index=False)
        pd.DataFrame(
            {
                "Category": ["metric_audit"],
                "Check": ["ProjectedSphericity2D_all_rows"],
                "Status": ["WARN"],
                "Value": [0],
                "Expected": ["documented"],
                "Notes": ["fixture warning"],
            }
        ).to_csv(acceptance / "g21_blob_computation_warning_inventory.csv", index=False)
        (acceptance / "g21_blob_pipeline_release_manifest.json").write_text(
            json.dumps(
                {
                    "decision_label": "ACCEPT_BLOB_PIPELINE_WITH_DOCUMENTED_WARNINGS",
                    "git_commit": "abc123",
                    "row_counts": {"morphology_rows": 5, "shape_class_v1_rows": 5, "frames": 3},
                    "warning_issues": ["metric_invariant_warnings"],
                    "blocking_issues": [],
                }
            ),
            encoding="utf-8",
        )

        return Inputs(
            postprocess_dir=post,
            morphology_dir=morph,
            shape_class_v1_dir=v1,
            structure_statistics_dir=stats,
            acceptance_dir=acceptance,
            output_dir=out,
            repo_root=root,
        )

    def test_bundle_writes_inventories_tables_figures_and_scope_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            inputs = self._make_fixture(Path(tmp))
            manifest = build_data_figure_bundle(inputs)

            required_top = [
                "README_data_figure_bundle.md",
                "data_inventory.csv",
                "figure_inventory.csv",
                "field_dictionary.csv",
                "formula_notes.md",
                "qc_and_scope_notes.md",
                "bundle_manifest.json",
            ]
            for name in required_top:
                self.assertTrue((inputs.output_dir / name).exists(), name)

            for name in [
                "shape_class_v1_count_area_summary.csv",
                "shape_class_v1_by_stage_summary.csv",
                "area_tier_summary.csv",
                "geometry_interpretable_fraction_by_stage.csv",
                "frame_level_blob_structure_summary.csv",
                "representative_blob_table.csv",
            ]:
                self.assertTrue((inputs.output_dir / "tables" / name).exists(), name)

            data_inventory = pd.read_csv(inputs.output_dir / "data_inventory.csv")
            for path in data_inventory["Path"]:
                self.assertTrue(Path(path).exists(), path)

            figure_inventory = pd.read_csv(inputs.output_dir / "figure_inventory.csv")
            self.assertGreaterEqual(len(figure_inventory), 12)
            for path in figure_inventory["Path"]:
                self.assertTrue(Path(path).exists(), path)

            fields = pd.read_csv(inputs.output_dir / "field_dictionary.csv")
            for field in [
                "ProjectedSphericity2D",
                "Circularity2D_boundary",
                "AxisAspectRatio",
                "AspectRatio01",
                "Solidity2D",
                "ProjectedRegularity2D",
                "ProjectedRoughness_boundary",
                "PtotalOverPouter",
                "ShapeClassV1",
                "AreaTier",
                "BoundaryMetricValid",
            ]:
                self.assertIn(field, set(fields["Field"]))

            formula = (inputs.output_dir / "formula_notes.md").read_text(encoding="utf-8")
            self.assertIn("ProjectedSphericity2D", formula)
            self.assertIn("Circularity2D_boundary", formula)
            self.assertIn("not Wadell roundness", formula)
            self.assertIn("not 3D roughness", formula)
            self.assertIn("not true fluid-fluid interfacial area", formula)

            notes = (inputs.output_dir / "qc_and_scope_notes.md").read_text(encoding="utf-8")
            self.assertIn("ACCEPT_BLOB_PIPELINE_WITH_DOCUMENTED_WARNINGS", notes)
            self.assertIn("No tracking", notes)
            self.assertIn("No 3D roughness", notes)

            forbidden = ["proves", "suggests a mechanism", "caused by", "drives the"]
            text = "\n".join(
                [
                    (inputs.output_dir / "README_data_figure_bundle.md").read_text(encoding="utf-8"),
                    notes,
                    (inputs.output_dir / "figure_inventory.csv").read_text(encoding="utf-8"),
                ]
            ).lower()
            for phrase in forbidden:
                self.assertNotIn(phrase, text)

            class_summary = pd.read_csv(inputs.output_dir / "tables" / "shape_class_v1_count_area_summary.csv")
            self.assertEqual(int(class_summary["N"].sum()), 5)
            self.assertAlmostEqual(float(class_summary["CountFraction"].sum()), 1.0)
            self.assertAlmostEqual(float(class_summary["AreaFraction"].sum()), 1.0)

            saved_manifest = json.loads((inputs.output_dir / "bundle_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(saved_manifest["row_counts"]["shape_class_v1_rows"], 5)
            self.assertFalse(saved_manifest["scope"]["writes_scientific_interpretation"])
            self.assertEqual(manifest["output_dir"], str(inputs.output_dir))


if __name__ == "__main__":
    unittest.main()
