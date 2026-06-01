import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from visualization.build_shape_class_v1_representative_atlas import build_v1_representative_atlas


class ShapeClassV1RepresentativeAtlasTests(unittest.TestCase):
    def test_builds_candidates_from_v1_labels_and_existing_label_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            morph = root / "morphology"
            v1 = morph / "shape_v1"
            morph.mkdir()
            v1.mkdir()

            rows = []
            morph_rows = []
            classes = ["compact_regular", "moderately_elongated"]
            for class_index, shape_class in enumerate(classes):
                for offset in range(3):
                    frame = class_index + 1
                    blob_id = offset + 1
                    area = 300 + 100 * offset + 50 * class_index
                    rows.append(
                        {
                            "FrameIndex": frame,
                            "BlobID": blob_id,
                            "ShapeClassV1": shape_class,
                            "ShapeClassV1Reason": "unit_test",
                            "ShapeClassVersion": "v1",
                            "ShapeV1InterpretationTier": "geometry_valid",
                            "MetricSource": "full_duration_sidecar",
                            "BoundaryMetricSource": "corrected_sidecar_boundary",
                            "DatasetSubset": "full_duration_sidecar",
                            "FullSidecarDerived": True,
                            "Area_px": area,
                            "AreaTier": "area_ge_250",
                            "ProjectedSphericity2D": 0.9 - 0.05 * offset,
                            "Circularity2D_boundary": 0.81 - 0.05 * offset,
                            "AspectRatio01": 0.8 - 0.1 * offset,
                            "AxisAspectRatio": 1.25 + offset,
                            "Solidity2D": 0.95 - 0.1 * offset,
                            "ProjectedRoughness_boundary": 1.05 + 0.1 * offset,
                            "PtotalOverPouter": 1.0,
                            "ProjectedRegularity2D": 0.88 - 0.05 * offset,
                        }
                    )
                    morph_rows.append(
                        {
                            "FrameIndex": frame,
                            "BlobID": blob_id,
                            "MaskPath": str(root / f"frame_{frame:06d}_mask.tif"),
                            "LabelPath": str(root / f"frame_{frame:06d}_labels.tif"),
                        }
                    )

            pd.DataFrame(rows).to_csv(v1 / "blob_shape_class_v1_by_blob.csv", index=False)
            pd.DataFrame(morph_rows).to_csv(morph / "blob_morphology_by_blob.csv", index=False)

            result = build_v1_representative_atlas(morph, v1, render=False)

            candidates = pd.read_csv(v1 / "representative_blob_candidates.csv")
            self.assertEqual(result["candidate_count"], 6)
            self.assertEqual(set(candidates["ShapeClass"]), set(classes))
            self.assertTrue(candidates["LabelPath"].astype(str).str.endswith("_labels.tif").all())
            self.assertTrue(candidates["ShapeClassVersion"].eq("v1").all())
            self.assertIn("class_medoid", set(candidates["ExemplarType"]))
            self.assertIn("large_area_exemplar", set(candidates["ExemplarType"]))
            self.assertIn("shape_extreme", set(candidates["ExemplarType"]))

            manifest = json.loads((v1 / "representative_blob_candidates_manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["scope"]["roughness_3d"])
            self.assertEqual(manifest["shape_class_count"], 2)


if __name__ == "__main__":
    unittest.main()
