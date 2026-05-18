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
MODULE_PATH = ROOT / "visualization" / "analyze_blob_population_morphology.py"
SPEC = importlib.util.spec_from_file_location("analyze_blob_population_morphology", MODULE_PATH)
blob_population = importlib.util.module_from_spec(SPEC)
sys.modules["analyze_blob_population_morphology"] = blob_population
SPEC.loader.exec_module(blob_population)


def make_blob_detail():
    return pd.DataFrame(
        {
            "FrameIndex": [1, 1, 1, 2, 2, 2, 2],
            "FrameTime": [0, 0, 0, 1, 1, 1, 1],
            "BlobID": [1, 2, 3, 1, 2, 3, 4],
            "Area": [10, 30, 60, 5, 15, 80, 100],
            "Perimeter": [10, 20, 30, 6, 7, 20, 25],
            "Circularity": [0.8, 0.9, 1.1, 0.7, 0.6, 0.5, np.nan],
            "AspectRatio": [1.0, 2.0, 4.0, 1.2, 1.5, 3.0, 6.0],
            "Solidity": [0.5, 0.8, 1.0, 0.7, 0.8, 0.9, 0.95],
            "EquivRadius": [1.0, 2.0, 4.0, 0.5, 1.5, 4.0, 5.0],
            "EulerNumber": [1, 1, 0, 1, 0, 0, -1],
            "TopologyType": ["droplet", "column", "cluster", "droplet", "column", "cluster", "cluster"],
        }
    )


def write_blob_csv(output_dir):
    path = output_dir / "blob_detail_all_frames.csv"
    make_blob_detail().to_csv(path, index=False)
    return path


def write_timeseries_csv(output_dir):
    df = pd.DataFrame(
        {
            "Time": [0, 1],
            "RealTime_s": [0.0, 60.0],
            "Sn": [0.5, 0.25],
        }
    )
    path = output_dir / "timeseries_realtime_test.csv"
    df.to_csv(path, index=False)
    return path


class BlobPopulationMorphologyTests(unittest.TestCase):
    def test_style_helpers_match_timeseries_v1_legend_and_axes(self):
        fig, ax = plt.subplots()
        ax.plot([0, 1], [0, 1], label="A")
        ax.plot([0, 1], [1, 0], label="B")

        blob_population.style_axes(ax)
        legend = blob_population.legend_above(ax, ncol=2)

        self.assertFalse(ax.spines["top"].get_visible())
        self.assertFalse(ax.spines["right"].get_visible())
        self.assertAlmostEqual(ax.spines["left"].get_linewidth(), 0.9)
        self.assertIsNotNone(legend)
        self.assertFalse(legend.get_frame_on())
        self.assertEqual(legend._ncols, 2)
        plt.close(fig)

    def test_per_frame_area_and_req_distribution_summary(self):
        summary = blob_population.compute_frame_morphology(make_blob_detail(), pixel_size_um=2.0)
        row = summary.loc[summary["FrameIndex"] == 1].iloc[0]
        self.assertEqual(row["BlobCount"], 3)
        self.assertAlmostEqual(row["TotalArea_px"], 100.0)
        self.assertAlmostEqual(row["Area_median_px"], 30.0)
        self.assertAlmostEqual(row["Area_mean_px"], 100.0 / 3.0)
        self.assertAlmostEqual(row["Area_p10_px"], 14.0)
        self.assertAlmostEqual(row["Area_p90_px"], 54.0)
        self.assertAlmostEqual(row["EquivRadius_median_px"], 2.0)
        self.assertAlmostEqual(row["EquivRadius_p90_px"], 3.6)
        self.assertAlmostEqual(row["Area_median_um2"], 120.0)
        self.assertAlmostEqual(row["EquivRadius_median_um"], 4.0)

    def test_area_weighted_shape_metrics_and_shape_filter(self):
        summary = blob_population.compute_frame_morphology(
            make_blob_detail(),
            pixel_size_um=None,
            min_shape_area_px=9,
            min_shape_perimeter_px=8,
        )
        row1 = summary.loc[summary["FrameIndex"] == 1].iloc[0]
        self.assertAlmostEqual(row1["Circularity_area_weighted_mean"], 1.01)
        self.assertAlmostEqual(row1["AspectRatio_area_weighted_mean"], 3.1)
        self.assertAlmostEqual(row1["Solidity_area_weighted_mean"], 0.89)

        row2 = summary.loc[summary["FrameIndex"] == 2].iloc[0]
        self.assertAlmostEqual(row2["Circularity_mean"], 0.5)
        self.assertAlmostEqual(row2["AspectRatio_area_weighted_mean"], (80 * 3.0 + 100 * 6.0) / 180.0)
        self.assertAlmostEqual(row2["Solidity_area_weighted_mean"], (80 * 0.9 + 100 * 0.95) / 180.0)

    def test_area_concentration_metrics(self):
        summary = blob_population.compute_frame_morphology(make_blob_detail())
        row = summary.loc[summary["FrameIndex"] == 1].iloc[0]
        self.assertAlmostEqual(row["Amax_Atotal"], 0.6)
        self.assertAlmostEqual(row["A_top3_Atotal"], 1.0)
        self.assertAlmostEqual(row["AreaGini"], 1.0 / 3.0)

    def test_topology_count_and_area_fractions_are_separate(self):
        topology = blob_population.compute_topology_population(make_blob_detail())
        row = topology.loc[topology["FrameIndex"] == 2].iloc[0]
        self.assertEqual(row["countDroplets"], 1)
        self.assertEqual(row["countColumns"], 1)
        self.assertEqual(row["countClusters"], 2)
        self.assertAlmostEqual(row["countFracClusters"], 0.5)
        self.assertAlmostEqual(row["areaFracDroplets"], 5.0 / 200.0)
        self.assertAlmostEqual(row["areaFracColumns"], 15.0 / 200.0)
        self.assertAlmostEqual(row["areaFracClusters"], 180.0 / 200.0)

    def test_size_distribution_slope_uses_log_survival_distribution(self):
        df = pd.DataFrame(
            {
                "FrameIndex": [1] * 6,
                "EquivRadius": [1, 2, 4, 8, 16, 32],
                "Area": [1, 1, 1, 1, 1, 1],
            }
        )
        slopes = blob_population.compute_size_distribution_slopes(
            df, q_low=0.0, q_high=1.0, min_slope_points=3
        )
        row = slopes.iloc[0]
        self.assertEqual(row["FitN"], 6)
        self.assertLess(row["Slope_logN_gt_Req_vs_logReq"], 0)
        self.assertGreaterEqual(row["R2"], 0.8)
        self.assertEqual(row["FitReqMin"], 1.0)
        self.assertEqual(row["FitReqMax"], 32.0)

    def test_timeseries_alignment_uses_time_plus_one(self):
        blob = make_blob_detail()
        ts = pd.DataFrame({"Time": [0, 1], "RealTime_s": [0.0, 60.0], "Sn": [0.5, 0.25]})
        aligned = blob_population.align_timeseries(
            pd.DataFrame({"FrameIndex": [1, 2]}), ts
        )
        self.assertAlmostEqual(aligned.loc[aligned["FrameIndex"] == 1, "Time_min"].iloc[0], 0.0)
        self.assertAlmostEqual(aligned.loc[aligned["FrameIndex"] == 2, "Time_min"].iloc[0], 1.0)
        self.assertAlmostEqual(aligned.loc[aligned["FrameIndex"] == 2, "SnNorm"].iloc[0], 0.5)
        _ = blob

    def test_cli_smoke_writes_outputs_and_figures(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            blob_csv = write_blob_csv(output_dir)
            ts_csv = write_timeseries_csv(output_dir)
            (output_dir / "analysis_report.txt").write_text("Pixel Size: 2.0 um/px\n", encoding="utf-8")
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = blob_population.main(
                    [
                        str(output_dir),
                        "--blob-csv",
                        str(blob_csv),
                        "--timeseries-csv",
                        str(ts_csv),
                        "--dpi",
                        "80",
                        "--min-slope-points",
                        "3",
                    ]
                )
            self.assertEqual(exit_code, 0)
            self.assertTrue((output_dir / "blob_population_morphology_by_frame.csv").exists())
            self.assertTrue((output_dir / "size_distribution_slope_vs_time.csv").exists())
            self.assertTrue((output_dir / "topology_population_by_frame.csv").exists())
            payload = json.loads((output_dir / "blob_population_morphology_summary.json").read_text())
            self.assertEqual(payload["n_frames"], 2)
            figures = output_dir / "figures_blob_population"
            self.assertTrue((figures / "01_area_req_distribution_summary.png").exists())
            self.assertTrue((figures / "05_area_concentration_metrics.svg").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
