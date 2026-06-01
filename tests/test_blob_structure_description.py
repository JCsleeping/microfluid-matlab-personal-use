import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from visualization.build_blob_structure_description import build_description_package


class BlobStructureDescriptionTests(unittest.TestCase):
    def test_description_package_uses_scope_safe_language_and_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stats = root / "stats"
            out = root / "desc"
            stats.mkdir()
            (stats / "figures_blob_structure").mkdir()
            (stats / "blob_structure_statistics_manifest.json").write_text(
                json.dumps(
                    {
                        "row_counts": {"frames": 4, "blob_rows": 6, "shape_valid_rows": 4},
                    }
                ),
                encoding="utf-8",
            )
            pd.DataFrame(
                {
                    "ShapeClass": ["branched_complex", "ambiguous_valid", "small_unclassified", "compact_round"],
                    "NBlobs": [2, 2, 1, 1],
                    "CountFraction": [0.33, 0.33, 0.17, 0.17],
                    "AreaFraction": [0.50, 0.30, 0.05, 0.15],
                }
            ).to_csv(stats / "blob_structure_class_summary.csv", index=False)
            pd.DataFrame(
                {
                    "SnStage": ["early_depletion", "endpoint"],
                    "NFrames": [2, 2],
                    "NBlobs": [4, 2],
                    "AreaSum_px": [1000, 100],
                    "count_frac_branched_complex": [0.4, 0.1],
                    "area_frac_branched_complex": [0.5, 0.2],
                    "count_frac_ambiguous_valid": [0.4, 0.1],
                    "area_frac_ambiguous_valid": [0.3, 0.2],
                    "count_frac_elongated": [0.0, 0.0],
                    "area_frac_elongated": [0.0, 0.0],
                    "count_frac_compact_round": [0.1, 0.0],
                    "area_frac_compact_round": [0.15, 0.0],
                    "count_frac_small_unclassified": [0.1, 0.8],
                    "area_frac_small_unclassified": [0.05, 0.6],
                }
            ).to_csv(stats / "blob_structure_transition_by_sn_stage.csv", index=False)

            manifest = build_description_package(stats, out)
            self.assertEqual(manifest["source_rows"]["frames"], 4)

            for name in [
                "g21_blob_structure_description.md",
                "g21_blob_structure_claims_table.csv",
                "g21_blob_structure_figure_notes.md",
                "g21_blob_structure_description_manifest.json",
            ]:
                self.assertTrue((out / name).exists(), name)

            text = (out / "g21_blob_structure_description.md").read_text(encoding="utf-8")
            self.assertIn("does not describe tracking trajectories", text)
            self.assertIn("not Wadell roundness", text)
            self.assertIn("2D exterior-boundary complexity proxy", text)
            self.assertIn("Endpoint morphology should therefore be interpreted", text)

            claims = pd.read_csv(out / "g21_blob_structure_claims_table.csv")
            self.assertIn("ForbiddenWording", claims.columns)
            self.assertTrue(claims["ForbiddenWording"].astype(str).str.contains("3D roughness").any())


if __name__ == "__main__":
    unittest.main()
