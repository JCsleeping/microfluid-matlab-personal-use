import importlib.util
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "visualization" / "plot_circularity_iqr.py"
SPEC = importlib.util.spec_from_file_location("plot_circularity_iqr", MODULE_PATH)
plot_circularity_iqr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plot_circularity_iqr)


class PlotCircularityIqrTests(unittest.TestCase):
    def test_summary_computes_median_iqr_area_weighted_and_valid_n(self):
        timeseries = pd.DataFrame(
            {
                "FrameIndex": [1, 2],
                "Time_min": [0.0, 20.0],
                "Sn": [1.0, 0.04],
                "SnNorm": [1.0, 0.04],
                "DissolutionStage": ["early", "near-depleted"],
            }
        )
        blob_detail = pd.DataFrame(
            {
                "FrameIndex": [1, 1, 1, 2],
                "Area": [100.0, 300.0, 5.0, 200.0],
                "Perimeter": [40.0, 60.0, 8.0, 50.0],
                "Circularity": [0.8, 0.6, 0.95, 0.7],
            }
        )

        summary, valid_blobs = plot_circularity_iqr.compute_circularity_summary(
            timeseries,
            blob_detail,
            min_blob_area_px=20,
            min_sn_norm=0.05,
            max_circularity=1.05,
        )

        row1 = summary.loc[summary["FrameIndex"] == 1].iloc[0]
        self.assertEqual(row1["ValidCircularityN"], 2)
        self.assertAlmostEqual(row1["CircularityQ25_valid"], 0.65)
        self.assertAlmostEqual(row1["MedianCircularity_valid"], 0.7)
        self.assertAlmostEqual(row1["CircularityQ75_valid"], 0.75)
        self.assertAlmostEqual(row1["AreaWeightedCircularity_valid"], 0.65)

        row2 = summary.loc[summary["FrameIndex"] == 2].iloc[0]
        self.assertEqual(row2["ValidCircularityN"], 0)
        self.assertTrue(np.isnan(row2["MedianCircularity_valid"]))
        self.assertEqual(len(valid_blobs), 2)

    def test_binned_summary_aggregates_blob_level_circularity(self):
        valid_blobs = pd.DataFrame(
            {
                "Time_min": [1.0, 2.0, 21.0],
                "Area": [100.0, 300.0, 100.0],
                "Circularity": [0.8, 0.6, 0.4],
                "DissolutionStage": ["early", "early", "middle"],
            }
        )

        binned = plot_circularity_iqr.compute_binned_summary(valid_blobs, bin_width_min=20)

        first = binned.loc[binned["TimeBinStart_min"] == 0.0].iloc[0]
        self.assertEqual(first["ValidCircularityN"], 2)
        self.assertAlmostEqual(first["MedianCircularity_valid"], 0.7)
        self.assertAlmostEqual(first["AreaWeightedCircularity_valid"], 0.65)

    def test_parse_multiple_bin_widths_and_file_stems(self):
        self.assertEqual(plot_circularity_iqr._parse_bin_widths("5,10,25"), [5.0, 10.0, 25.0])
        self.assertEqual(plot_circularity_iqr._bin_width_stem(2.5), "2p5min")


if __name__ == "__main__":
    unittest.main()
