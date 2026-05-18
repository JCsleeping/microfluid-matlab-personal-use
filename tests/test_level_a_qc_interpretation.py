import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "visualization" / "qc_level_a_interpretation.py"
SPEC = importlib.util.spec_from_file_location("qc_level_a_interpretation", MODULE_PATH)
qc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qc)


def make_postprocess_dir(root):
    post = root / "postprocess_residual_structure_mock"
    post.mkdir()
    frame = np.arange(1, 31)
    time_min = frame.astype(float)
    rate = np.linspace(0.03, 0.90, len(frame))
    sn = 1.0 - np.linspace(0.0, 0.8, len(frame))
    stage = np.where(frame <= 10, "early", np.where(frame <= 20, "middle", "late"))

    rates = pd.DataFrame(
        {
            "FrameIndex": frame,
            "Time_min": time_min,
            "Sn": sn,
            "SnNorm": sn / sn[0],
            "DissolutionRate_Sn_per_min": rate,
            "Stage": stage,
            "NumBlobs": rate * 100 + 5,
            "ReqMedian": rate * 10 + 1,
            "MaxBlobFrac": 1.0 - rate,
            "fracDroplets": 1.0 - rate / rate.max(),
            "fracColumns": rate / rate.max(),
            "a_i_2D": rate * 1000 + 50,
            "InterfaceArea": rate * 500 + 10,
        }
    )
    rates.to_csv(post / "dissolution_rates.csv", index=False)

    pd.DataFrame(
        {
            "FrameIndex": frame,
            "Circularity2D_area_weighted_mean": 1.0 - rate / 2,
            "Solidity_area_weighted_mean": 0.8 - rate / 5,
            "AspectRatio_area_weighted_mean": np.sin(frame),
        }
    ).to_csv(post / "blob_population_morphology_by_frame.csv", index=False)

    pd.DataFrame(
        {
            "FrameIndex": frame,
            "areaFracDroplets": 1.0 - rate / rate.max(),
            "areaFracColumns": rate / rate.max(),
            "areaFracClusters": 0.2,
        }
    ).to_csv(post / "topology_population_by_frame.csv", index=False)

    pd.DataFrame(
        {
            "FrameIndex": frame,
            "Slope_logN_gt_Req_vs_logReq": -rate,
        }
    ).to_csv(post / "size_distribution_slope_vs_time.csv", index=False)

    pd.DataFrame(
        {
            "FrameIndex": frame,
            "ArchitectureType": ["ganglia-rich"] * len(frame),
            "Stage": stage,
        }
    ).to_csv(post / "architecture_vs_time.csv", index=False)
    pd.DataFrame(columns=["From", "To", "FrameIndex"]).to_csv(post / "architecture_transitions.csv", index=False)
    return post


class LevelAQCTests(unittest.TestCase):
    def test_stable_score_uses_minimum_absolute_pearson_spearman(self):
        self.assertAlmostEqual(qc.stable_score(0.9, -0.4), 0.4)
        self.assertAlmostEqual(qc.stable_score(np.nan, 0.4), 0.0)

    def test_qc_run_writes_expected_outputs_and_flags_single_architecture(self):
        with tempfile.TemporaryDirectory() as tmp:
            post = make_postprocess_dir(Path(tmp))
            out = post / "level_a_qc_test"
            exit_code = qc.main(
                [
                    "--postprocess-dir",
                    str(post),
                    "--output-dir",
                    str(out),
                    "--stable-threshold",
                    "0.4",
                    "--min-n",
                    "5",
                    "--no-figures",
                ]
            )
            self.assertEqual(exit_code, 0)
            for name in [
                "level_a_qc_report.md",
                "global_stable_associations.csv",
                "stage_stable_associations.csv",
                "stage_time_detrended_associations.csv",
                "stage_rate_summary.csv",
                "architecture_qc_summary.csv",
                "interpretation_candidates.csv",
            ]:
                self.assertTrue((out / name).exists(), name)

            arch = pd.read_csv(out / "architecture_qc_summary.csv")
            self.assertEqual(arch.loc[0, "transition_signal"], "no_architecture_transition_signal")
            candidates = pd.read_csv(out / "interpretation_candidates.csv")
            self.assertIn("HIGH_CONFIDENCE_LEVEL_A_CANDIDATE", set(candidates["candidate_status"]))
            report = (out / "level_a_qc_report.md").read_text(encoding="utf-8")
            self.assertIn("Architecture transition is not a useful primary interpretation axis", report)
            self.assertIn("metadata", report.lower())

    def test_missing_optional_metric_is_recorded_unavailable_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            post = make_postprocess_dir(Path(tmp))
            (post / "blob_population_morphology_by_frame.csv").unlink()
            out = post / "level_a_qc_missing_optional"
            qc.main(["--postprocess-dir", str(post), "--output-dir", str(out), "--no-figures", "--min-n", "5"])
            global_assoc = pd.read_csv(out / "global_stable_associations.csv")
            row = global_assoc.loc[global_assoc["metric"] == "Circularity2D_area_weighted_mean"].iloc[0]
            self.assertEqual(bool(row["available"]), False)

    def test_nonempty_explicit_output_dir_requires_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            post = make_postprocess_dir(Path(tmp))
            out = post / "level_a_qc_existing"
            out.mkdir()
            (out / "old.txt").write_text("old", encoding="utf-8")
            with self.assertRaisesRegex(FileExistsError, "already exists and is not empty"):
                qc.main(["--postprocess-dir", str(post), "--output-dir", str(out), "--no-figures"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
