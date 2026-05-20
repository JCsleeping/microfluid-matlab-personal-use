import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import tifffile


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "visualization" / "render_blob_atlas_panels.py"
SPEC = importlib.util.spec_from_file_location("render_blob_atlas_panels", MODULE_PATH)
blob_atlas = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(blob_atlas)


def write_candidates(path: Path, rows: list[dict]) -> None:
    base = {
        "FrameIndex": 263,
        "BlobID": 131,
        "ShapeClass": "ambiguous_valid",
        "Area_px": 24.0,
        "AreaTier": "medium",
        "ProjectedSphericity2D": 0.82,
        "Circularity2D_boundary": 0.75,
        "AspectRatio01": 0.61,
        "AxisAspectRatio": 1.64,
        "Solidity2D": 0.91,
        "ProjectedRoughness_boundary": 1.18,
        "PtotalOverPouter": 1.07,
        "ProjectedRegularity2D": 0.78,
        "MaskPath": "",
        "LabelPath": "",
        "ExemplarType": "class_medoid",
        "SelectionReason": "synthetic",
    }
    full_rows = []
    for row in rows:
        item = base.copy()
        item.update(row)
        full_rows.append(item)
    pd.DataFrame(full_rows, columns=list(base)).to_csv(path, index=False)


class BlobAtlasRendererTests(unittest.TestCase):
    def test_successful_render_writes_png_and_manifest_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            labels = np.zeros((40, 50), dtype=np.uint16)
            labels[12:18, 20:28] = 131
            label_path = root / "frame_000263_labels.tif"
            tifffile.imwrite(label_path, labels)

            candidates_csv = root / "representative_blob_candidates.csv"
            write_candidates(candidates_csv, [{"LabelPath": str(label_path)}])
            output_dir = root / "representative_blob_atlas"

            result = blob_atlas.render_blob_atlas(candidates_csv, output_dir=output_dir)

            self.assertEqual(result["rendered_count"], 1)
            panel_path = output_dir / "frame_000263_blob_000131_ambiguous_valid_class_medoid.png"
            self.assertTrue(panel_path.exists())
            self.assertGreater(panel_path.stat().st_size, 0)

            manifest = pd.read_csv(output_dir / "representative_blob_atlas_manifest.csv")
            self.assertEqual(len(manifest), 1)
            self.assertEqual(manifest.loc[0, "Status"], "RENDERED")
            self.assertEqual(Path(manifest.loc[0, "PanelPath"]), panel_path)
            self.assertEqual(int(manifest.loc[0, "BBoxY0"]), 12)
            self.assertEqual(int(manifest.loc[0, "BBoxX0"]), 20)
            self.assertEqual(int(manifest.loc[0, "BBoxY1"]), 18)
            self.assertEqual(int(manifest.loc[0, "BBoxX1"]), 28)

            summary = (output_dir / "representative_blob_atlas_summary.md").read_text(encoding="utf-8")
            self.assertIn("2D projected representative blobs", summary)
            self.assertIn("not tracking, fractal analysis, 3D roughness", summary)
            self.assertIn("Rendered candidates: 1", summary)

    def test_missing_label_path_or_absent_blob_id_writes_failure_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            labels = np.zeros((20, 20), dtype=np.uint16)
            labels[3:8, 4:10] = 999
            label_path = root / "frame_000264_labels.tif"
            tifffile.imwrite(label_path, labels)

            candidates_csv = root / "representative_blob_candidates.csv"
            write_candidates(
                candidates_csv,
                [
                    {"FrameIndex": 264, "BlobID": 131, "LabelPath": str(root / "missing_labels.tif")},
                    {"FrameIndex": 264, "BlobID": 131, "LabelPath": str(label_path)},
                ],
            )

            result = blob_atlas.render_blob_atlas(candidates_csv)

            self.assertEqual(result["rendered_count"], 0)
            self.assertEqual(result["missing_count"], 2)
            manifest = pd.read_csv(root / "representative_blob_atlas" / "representative_blob_atlas_manifest.csv")
            self.assertEqual(list(manifest["Status"]), ["MISSING_LABEL_PATH", "MISSING_BLOB_LABEL"])
            self.assertTrue(manifest["PanelPath"].fillna("").eq("").all())

    def test_output_overwrite_guard_prevents_deleting_non_atlas_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidates_csv = root / "representative_blob_candidates.csv"
            write_candidates(candidates_csv, [])
            output_dir = root / "custom_panels"
            output_dir.mkdir()
            sentinel = output_dir / "keep.txt"
            sentinel.write_text("do not delete", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Refusing to overwrite non-atlas output directory"):
                blob_atlas.render_blob_atlas(candidates_csv, output_dir=output_dir, overwrite=True)

            self.assertTrue(sentinel.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
