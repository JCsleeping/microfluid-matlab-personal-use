import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from visualization.build_blob_structure_results_section import build_results_section_package


class BlobStructureResultsSectionTests(unittest.TestCase):
    def test_build_results_section_package_uses_allowed_claims(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stats = root / "stats"
            desc = root / "desc"
            figs = root / "figs"
            out = root / "results"
            stats.mkdir()
            desc.mkdir()
            figs.mkdir()

            (stats / "blob_structure_statistics_manifest.json").write_text(
                json.dumps({"row_counts": {"frames": 4, "blob_rows": 6, "shape_valid_rows": 4}}),
                encoding="utf-8",
            )
            (desc / "g21_blob_structure_description_manifest.json").write_text(
                json.dumps({"source_rows": {"frames": 4}}),
                encoding="utf-8",
            )
            (figs / "figure_package_manifest.json").write_text(
                json.dumps(
                    {
                        "figures": {
                            "Fig_BlobShapeClassFractions.png": {},
                            "Fig_BlobShapeMap_Sphericity_Roughness.png": {
                                "plotted_points": 100,
                                "available_valid_points": 400,
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            pd.DataFrame(
                {
                    "ShapeClass": [
                        "branched_complex",
                        "ambiguous_valid",
                        "elongated",
                        "compact_round",
                        "small_unclassified",
                    ],
                    "AreaFraction": [0.4, 0.3, 0.2, 0.05, 0.05],
                    "CountFraction": [0.1, 0.2, 0.1, 0.1, 0.5],
                }
            ).to_csv(stats / "blob_structure_class_summary.csv", index=False)
            pd.DataFrame(
                {
                    "SnStage": ["early_depletion", "active_dissolution", "late_depletion", "endpoint"],
                    "area_frac_branched_complex": [0.4, 0.3, 0.2, 0.1],
                    "area_frac_ambiguous_valid": [0.3, 0.4, 0.3, 0.2],
                    "area_frac_elongated": [0.1, 0.1, 0.2, 0.1],
                    "count_frac_small_unclassified": [0.1, 0.2, 0.4, 0.8],
                    "area_frac_small_unclassified": [0.05, 0.1, 0.2, 0.6],
                }
            ).to_csv(stats / "blob_structure_transition_by_sn_stage.csv", index=False)

            manifest = build_results_section_package(stats, desc, figs, out)
            self.assertFalse(manifest["scope"]["tracking"])
            self.assertTrue((out / "g21_blob_structure_results_section.md").exists())
            self.assertTrue((out / "g21_blob_structure_results_claims_to_figures.csv").exists())

            text = (out / "g21_blob_structure_results_section.md").read_text(encoding="utf-8")
            self.assertIn("full-duration projected 2D blob-structure data product", text)
            self.assertIn("Endpoint morphology", text)
            self.assertIn("not as single-blob dynamics or causal mechanisms", text)
            self.assertNotIn("caused by", text.lower())

            claims = pd.read_csv(out / "g21_blob_structure_results_claims_to_figures.csv")
            self.assertIn("Boundary", claims.columns)
            self.assertTrue(claims["Boundary"].astype(str).str.contains("not true roughness").any())


if __name__ == "__main__":
    unittest.main()
