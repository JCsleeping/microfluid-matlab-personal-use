import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from visualization.build_blob_structure_figure_package import build_figure_package


class BlobStructureFigurePackageTests(unittest.TestCase):
    def test_build_figure_package_writes_scope_safe_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            morph = root / "morph"
            stats = root / "stats"
            atlas = morph / "representative_blob_atlas"
            fig_src = stats / "figures_blob_structure"
            out = root / "figpkg"
            morph.mkdir()
            stats.mkdir()
            atlas.mkdir()
            fig_src.mkdir()

            pd.DataFrame(
                {
                    "ShapeClass": [
                        "branched_complex",
                        "ambiguous_valid",
                        "elongated",
                        "compact_round",
                        "small_unclassified",
                    ],
                    "CountFraction": [0.1, 0.2, 0.1, 0.1, 0.5],
                    "AreaFraction": [0.4, 0.3, 0.2, 0.05, 0.05],
                }
            ).to_csv(stats / "blob_structure_class_summary.csv", index=False)
            pd.DataFrame(
                {
                    "SnStage": ["early_depletion", "endpoint"],
                    "area_frac_branched_complex": [0.4, 0.2],
                    "area_frac_ambiguous_valid": [0.3, 0.2],
                    "area_frac_elongated": [0.2, 0.1],
                    "area_frac_compact_round": [0.05, 0.0],
                    "area_frac_small_unclassified": [0.05, 0.5],
                }
            ).to_csv(stats / "blob_structure_transition_by_sn_stage.csv", index=False)

            rows = []
            for idx, cls in enumerate(["branched_complex", "ambiguous_valid", "elongated", "compact_round"]):
                rows.append(
                    {
                        "ShapeClass": cls,
                        "ShapeValid": True,
                        "Area_px": 500 + idx * 100,
                        "ProjectedSphericity2D": 0.5 + idx * 0.1,
                        "ProjectedRoughness_boundary": 1.1 + idx * 0.2,
                    }
                )
            pd.DataFrame(rows).to_csv(morph / "blob_shape_class_by_blob.csv", index=False)

            panel_path = atlas / "panel.png"
            Image.fromarray(np.full((24, 24, 3), 240, dtype=np.uint8)).save(panel_path)
            pd.DataFrame(
                {
                    "ShapeClass": ["compact_round", "elongated", "branched_complex", "ambiguous_valid"],
                    "ExemplarType": ["class_medoid"] * 4,
                    "Status": ["RENDERED"] * 4,
                    "PanelPath": [str(panel_path)] * 4,
                }
            ).to_csv(atlas / "representative_blob_atlas_manifest.csv", index=False)

            Image.fromarray(np.full((20, 20, 3), 128, dtype=np.uint8)).save(
                fig_src / "valid_metric_distributions_by_shape_class.png"
            )

            manifest = build_figure_package(morph, stats, out)
            self.assertFalse(manifest["scope"]["roughness_3d"])
            for name in [
                "Fig_BlobShapeClassFractions.png",
                "Fig_ShapeClassBySnStage.png",
                "Fig_BlobShapeMap_Sphericity_Roughness.png",
                "Fig_RepresentativeBlobAtlas.png",
                "Fig_ValidMetricDistributionsByShapeClass.png",
                "figure_caption_bank.md",
                "figure_package_manifest.json",
            ]:
                self.assertTrue((out / name).exists(), name)

            caption = (out / "figure_caption_bank.md").read_text(encoding="utf-8")
            self.assertIn("2D exterior-boundary complexity proxy", caption)
            self.assertIn("not be described as 3D morphology or Wadell roundness", caption)

            saved = json.loads((out / "figure_package_manifest.json").read_text(encoding="utf-8"))
            self.assertIn("Fig_BlobShapeMap_Sphericity_Roughness.png", saved["figures"])


if __name__ == "__main__":
    unittest.main()
