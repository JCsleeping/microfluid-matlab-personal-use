import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "visualization" / "trim_comparison_onset.py"


def load_module():
    spec = importlib.util.spec_from_file_location("trim_comparison_onset", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_workbook(path, df):
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="data", index=False)


class TrimComparisonOnsetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_detects_onset_independently_per_experiment(self):
        trim = load_module()
        df = pd.DataFrame(
            {
                "ExperimentLabel": ["2 uL"] * 8 + ["4 uL"] * 8,
                "SeriesName": ["SnNorm"] * 16,
                "PV": list(range(8)) + list(range(20, 28)),
                "Y": [1.0, 1.0, 0.99, 0.981, 0.979, 0.978, 0.977, 0.976]
                + [1.0, 0.995, 0.979, 0.978, 0.977, 0.976, 0.975, 0.974],
                "SnNorm": [1.0, 1.0, 0.99, 0.981, 0.979, 0.978, 0.977, 0.976]
                + [1.0, 0.995, 0.979, 0.978, 0.977, 0.976, 0.975, 0.974],
            }
        )

        trimmed, metadata = trim.trim_to_onset(df, threshold=0.98, min_consecutive=3)

        starts = trimmed.groupby("ExperimentLabel")["PV_original"].first().to_dict()
        self.assertEqual(starts["2 uL"], 4)
        self.assertEqual(starts["4 uL"], 22)
        self.assertTrue(np.allclose(trimmed.groupby("ExperimentLabel")["PV_since_onset"].first(), 0.0))
        self.assertEqual(metadata.set_index("ExperimentLabel").loc["2 uL", "TrimmedRows"], 4)
        self.assertEqual(metadata.set_index("ExperimentLabel").loc["4 uL", "TrimmedRows"], 2)

    def test_sn_plot_uses_snnorm_for_onset_and_preserves_original_pv(self):
        trim = load_module()
        df = pd.DataFrame(
            {
                "ExperimentLabel": ["6 uL"] * 6,
                "SeriesName": ["Sn"] * 6,
                "PV": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0],
                "Y": [0.31, 0.31, 0.30, 0.29, 0.28, 0.27],
                "Sn": [0.31, 0.31, 0.30, 0.29, 0.28, 0.27],
                "SnNorm": [1.0, 0.99, 0.979, 0.978, 0.977, 0.976],
            }
        )

        trimmed, metadata = trim.trim_to_onset(df, threshold=0.98, min_consecutive=2)

        self.assertEqual(trimmed["PV_original"].iloc[0], 12.0)
        self.assertEqual(trimmed["PV_since_onset"].iloc[0], 0.0)
        self.assertEqual(trimmed["PV_onset"].iloc[0], 12.0)
        self.assertEqual(trimmed["Y"].iloc[0], 0.30)
        self.assertTrue(metadata["OnsetFound"].iloc[0])

    def test_sn_plot_derives_snnorm_from_sn_when_snnorm_is_missing(self):
        trim = load_module()
        df = pd.DataFrame(
            {
                "ExperimentLabel": ["2 uL"] * 6,
                "SeriesName": ["Sn"] * 6,
                "PV": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0],
                "Y": [0.31, 0.31, 0.30, 0.29, 0.28, 0.27],
                "Sn": [0.31, 0.31, 0.30, 0.29, 0.28, 0.27],
                "SnNorm": [np.nan] * 6,
            }
        )

        trimmed, metadata = trim.trim_to_onset(df, threshold=0.98, min_consecutive=2)

        self.assertEqual(trimmed["PV_original"].iloc[0], 12.0)
        self.assertEqual(trimmed["PV_since_onset"].iloc[0], 0.0)
        self.assertTrue(metadata["OnsetFound"].iloc[0])
        self.assertEqual(metadata["OnsetSignal"].iloc[0], "Sn_normalized")

    def test_log_plot_filters_zero_pv_since_onset(self):
        trim = load_module()
        df = pd.DataFrame(
            {
                "ExperimentLabel": ["2 uL", "2 uL", "2 uL"],
                "SeriesName": ["SnNorm", "SnNorm", "SnNorm"],
                "PV_since_onset": [0.0, 1.0, 2.0],
                "Y": [1.0, 0.9, 0.8],
            }
        )

        x, y = trim.xy_for_plot(df, scale="log")

        self.assertTrue(np.all(x > 0))
        self.assertEqual(x.tolist(), [1.0, 2.0])
        self.assertEqual(y.tolist(), [0.9, 0.8])

    def test_cli_smoke_writes_figures_and_workbook(self):
        trim = load_module()
        in_path = self.root / "custom_SnNorm_2_4_6ul_data.xlsx"
        df = pd.DataFrame(
            {
                "ExperimentLabel": ["2 uL"] * 7 + ["4 uL"] * 7,
                "SeriesName": ["SnNorm"] * 14,
                "PV": list(range(7)) + list(range(10, 17)),
                "Y": [1.0, 1.0, 0.99, 0.979, 0.978, 0.977, 0.976]
                + [1.0, 0.99, 0.979, 0.978, 0.977, 0.976, 0.975],
                "SnNorm": [1.0, 1.0, 0.99, 0.979, 0.978, 0.977, 0.976]
                + [1.0, 0.99, 0.979, 0.978, 0.977, 0.976, 0.975],
            }
        )
        write_workbook(in_path, df)

        rc = trim.main([str(in_path), "--out-stem", "custom_SnNorm_2_4_6ul_onset_pv0"])

        self.assertEqual(rc, 0)
        for suffix in [".png", ".svg", "_log.png", "_log.svg", "_data.xlsx"]:
            self.assertTrue((self.root / f"custom_SnNorm_2_4_6ul_onset_pv0{suffix}").exists())
        out = pd.read_excel(self.root / "custom_SnNorm_2_4_6ul_onset_pv0_data.xlsx", sheet_name="data")
        self.assertIn("PV_original", out.columns)
        self.assertIn("PV_since_onset", out.columns)
        self.assertEqual(out.groupby("ExperimentLabel")["PV_since_onset"].first().tolist(), [0, 0])


if __name__ == "__main__":
    unittest.main()
