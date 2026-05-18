import importlib.util
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "visualization" / "analyze_architecture_vs_time.py"
SPEC = importlib.util.spec_from_file_location("analyze_architecture_vs_time", MODULE_PATH)
architecture_time = importlib.util.module_from_spec(SPEC)
sys.modules["analyze_architecture_vs_time"] = architecture_time
SPEC.loader.exec_module(architecture_time)


def write_timeseries(output_dir, labels=None):
    if labels is None:
        labels = [
            "pool-like", "pool-like", "pool-like", "pool-like", "pool-like",
            "ganglia-rich", "ganglia-rich", "mixed", "ganglia-rich", "ganglia-rich",
            "ganglia-rich", "ganglia-rich", "ganglia-rich", "mixed", "mixed",
            "mixed", "mixed", "mixed",
        ]
    rows = []
    for i, label in enumerate(labels):
        if label == "pool-like":
            max_blob, num_blobs, ai2d = 0.70, 5, 2.5e4
        elif label == "ganglia-rich":
            max_blob, num_blobs, ai2d = 0.20, 80, 8.0e4
        else:
            max_blob, num_blobs, ai2d = 0.45, 40, 4.0e4
        rows.append(
            {
                "Time": i,
                "RealTime_s": float(i * 60),
                "Sn": 1.0 - 0.02 * i,
                "NumBlobs": num_blobs,
                "InterfaceArea": 1000 + i,
                "MaxBlobFrac": max_blob,
                "ReqMedian": 8.0 - 0.1 * i,
                "a_i_2D": ai2d,
                "fracDroplets": 0.2,
                "fracColumns": 0.3,
                "fracClusters": 0.5,
            }
        )
    df = pd.DataFrame(rows)
    csv_path = output_dir / "timeseries_realtime_test.csv"
    df.to_csv(csv_path, index=False)
    return csv_path, df


class ArchitectureClassificationTests(unittest.TestCase):
    def test_matlab_threshold_scoring_and_labels_are_reproduced(self):
        thresholds = architecture_time.ArchitectureThresholds()
        row = pd.Series({"MaxBlobFrac": 0.20, "NumBlobs": 80, "a_i_2D": 8.0e4})
        result = architecture_time.classify_architecture_row(row, thresholds)
        self.assertEqual(result["ArchitectureType"], "ganglia-rich")
        self.assertEqual(result["PoolScore"], 0)
        self.assertEqual(result["GangliaScore"], 3)
        self.assertIn("ganglia_score >= 2", result["Reason"])

        row = pd.Series({"MaxBlobFrac": 0.70, "NumBlobs": 5, "a_i_2D": 2.0e4})
        result = architecture_time.classify_architecture_row(row, thresholds)
        self.assertEqual(result["ArchitectureType"], "pool-like")
        self.assertEqual(result["PoolScore"], 3)
        self.assertEqual(result["GangliaScore"], 0)

    def test_missing_ai2d_uses_matlab_nan_branch(self):
        thresholds = architecture_time.ArchitectureThresholds()
        row = pd.Series({"MaxBlobFrac": 0.70, "NumBlobs": 5, "a_i_2D": np.nan})
        result = architecture_time.classify_architecture_row(row, thresholds)
        self.assertEqual(result["ArchitectureType"], "pool-like")
        self.assertEqual(result["PoolScore"], 2)
        self.assertEqual(result["GangliaScore"], 0)
        self.assertIn("a_i_2D is non-finite", result["Reason"])


class ArchitecturePipelineTests(unittest.TestCase):
    def test_style_helpers_match_timeseries_v1_legend_and_axes(self):
        fig, ax = plt.subplots()
        ax.plot([0, 1], [0, 1], label="pool-like")
        ax.plot([0, 1], [1, 0], label="mixed")

        architecture_time.style_axes(ax)
        legend = architecture_time.legend_above(ax, ncol=2)

        self.assertFalse(ax.spines["top"].get_visible())
        self.assertFalse(ax.spines["right"].get_visible())
        self.assertAlmostEqual(ax.spines["left"].get_linewidth(), 0.9)
        self.assertIsNotNone(legend)
        self.assertFalse(legend.get_frame_on())
        self.assertEqual(legend._ncols, 2)
        plt.close(fig)

    def test_frame_index_from_time_and_time_output_is_minutes(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path, _ = write_timeseries(output_dir)
            loaded = architecture_time.load_timeseries(csv_path)
            self.assertIn("FrameIndex", loaded.columns)
            self.assertIn("Time_min", loaded.columns)
            self.assertEqual(loaded.loc[3, "FrameIndex"], 3)
            self.assertEqual(loaded.loc[3, "Time_min"], 3.0)

    def test_architecture_vs_time_contains_required_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path, _ = write_timeseries(output_dir)
            loaded = architecture_time.load_timeseries(csv_path)
            enriched = architecture_time.prepare_architecture_dataframe(
                loaded,
                output_dir=output_dir,
                rates_csv_path=None,
                thresholds=architecture_time.ArchitectureThresholds(),
                min_sn_norm_valid=0.05,
                min_blobs_valid=1,
            )
            required = {
                "FrameIndex", "Time", "Sn", "ArchitectureType", "PoolScore",
                "GangliaScore", "MaxBlobFrac", "NumBlobs", "a_i_2D", "ReqMedian",
                "fracDroplets", "fracColumns", "fracClusters", "Reason",
                "RealTime_s", "Time_min", "SnNorm", "ValidArchitecture",
                "DissolutionRate_per_min",
            }
            self.assertTrue(required.issubset(enriched.columns))

    def test_transition_summary_ignores_short_label_flicker(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path, _ = write_timeseries(output_dir)
            df = architecture_time.prepare_architecture_dataframe(
                architecture_time.load_timeseries(csv_path),
                output_dir=output_dir,
                rates_csv_path=None,
                thresholds=architecture_time.ArchitectureThresholds(),
                min_sn_norm_valid=0.05,
                min_blobs_valid=1,
            )
            transitions = architecture_time.detect_transitions(
                df, min_run_frames=3, window_min=2.0
            )
            pairs = list(zip(transitions["From"], transitions["To"]))
            self.assertIn(("pool-like", "ganglia-rich"), pairs)
            self.assertIn(("ganglia-rich", "mixed"), pairs)
            self.assertNotIn(("ganglia-rich", "mixed"), pairs[:1])
            self.assertEqual(len(transitions), 2)

    def test_invalid_architecture_rows_do_not_enter_transitions(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path, _ = write_timeseries(output_dir, labels=["pool-like"] * 5 + ["mixed"] * 5)
            df = architecture_time.prepare_architecture_dataframe(
                architecture_time.load_timeseries(csv_path),
                output_dir=output_dir,
                rates_csv_path=None,
                thresholds=architecture_time.ArchitectureThresholds(),
                min_sn_norm_valid=0.05,
                min_blobs_valid=20,
            )
            df.loc[df["ArchitectureType"] == "mixed", "ValidArchitecture"] = False
            transitions = architecture_time.detect_transitions(
                df, min_run_frames=3, window_min=2.0
            )
            self.assertTrue(transitions.empty)

    def test_existing_rates_csv_is_preferred_when_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path, ts = write_timeseries(output_dir)
            rates_dir = output_dir / "figures_rate"
            rates_dir.mkdir()
            pd.DataFrame(
                {
                    "RealTime_s": ts["RealTime_s"],
                    "SnNorm": np.linspace(1.0, 0.7, len(ts)),
                    "ValidStructure": [True] * len(ts),
                    "DissolutionRate_Sn_time_lr": [0.123] * len(ts),
                }
            ).to_csv(rates_dir / "dissolution_rates.csv", index=False)
            df = architecture_time.prepare_architecture_dataframe(
                architecture_time.load_timeseries(csv_path),
                output_dir=output_dir,
                rates_csv_path=None,
                thresholds=architecture_time.ArchitectureThresholds(),
                min_sn_norm_valid=0.05,
                min_blobs_valid=20,
            )
            self.assertTrue(np.allclose(df["DissolutionRate_per_min"], 0.123))
            self.assertTrue(np.allclose(df["SnNorm"], np.linspace(1.0, 0.7, len(ts))))

    def test_main_writes_csv_json_and_figures(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path, _ = write_timeseries(output_dir)
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = architecture_time.main(
                    [
                        str(output_dir),
                        "--csv", str(csv_path),
                        "--transition-min-run-frames", "3",
                        "--transition-window-min", "2",
                        "--dpi", "80",
                    ]
                )
            self.assertEqual(exit_code, 0)
            self.assertTrue((output_dir / "architecture_vs_time.csv").exists())
            self.assertTrue((output_dir / "architecture_transitions.csv").exists())
            self.assertTrue((output_dir / "architecture_rate_summary.csv").exists())
            payload = json.loads((output_dir / "architecture_summary.json").read_text())
            self.assertIn("peak_rate", payload)
            figures = output_dir / "figures_architecture_time"
            self.assertTrue((figures / "01_architecture_timeline.png").exists())
            self.assertTrue((figures / "04_rate_vs_ai2d_by_architecture.svg").exists())

    def test_rate_distribution_groups_skip_empty_and_label_sample_size(self):
        df = pd.DataFrame(
            {
                "ArchitectureType": ["pool-like", "mixed", "mixed", "ganglia-rich", "ganglia-rich"],
                "ValidArchitecture": [False, True, True, True, True],
                "DissolutionRate_per_min": [0.2, 1e-4, 2e-4, 1e-3, 2e-3],
            }
        )
        groups = architecture_time.rate_distribution_groups(df)
        self.assertEqual([group["architecture"] for group in groups], ["mixed", "ganglia-rich"])
        self.assertEqual([group["label"] for group in groups], ["mixed\nn=2", "ganglia-rich\nn=2"])
        self.assertTrue(all(np.all(group["values"] > 0) for group in groups))


if __name__ == "__main__":
    unittest.main(verbosity=2)
