import importlib.util
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "visualization" / "plot_multi_experiment_comparison.py"


def load_module():
    spec = importlib.util.spec_from_file_location("plot_multi_experiment_comparison", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


comparison = load_module()


def write_workbook(path, sheets):
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        for sheet_name, df in sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)


class MultiExperimentComparisonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def figures_dir(self, name):
        path = self.root / name / "figures"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_manifest(self, rows):
        path = self.root / "compare_manifest.csv"
        pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")
        return path

    def write_saturation(self, figures_dir, sn0=0.30, delta=0.02):
        time = np.array([0.0, 3.0, 10.0, 30.0, 100.0])
        sn = sn0 - delta * np.arange(len(time))
        df = pd.DataFrame(
            {
                "RealTime_s": time * 60,
                "Time_min": time,
                "Sn": sn,
                "SnNorm": sn / sn[0],
            }
        )
        write_workbook(figures_dir / "01_saturation_decay_data.xlsx", {"data": df})

    def write_custom_saturation_workbook(self, path, sn0=0.30):
        time = np.array([0.0, 10.0, 20.0])
        sn = sn0 - 0.03 * np.arange(len(time))
        df = pd.DataFrame({"Time_min": time, "SnNorm": sn / sn[0]})
        write_workbook(path, {"data": df})

    def write_rate_scatter(self, figures_dir):
        data_all = pd.DataFrame(
            {
                "a_i_2D_raw": [10.0, 11.0, 12.0, 13.0],
                "a_i_2D_plot": [10.0, 11.0, 12.0, 13.0],
                "DissolutionRate_Sn_time_lr": [0.001, 0.002, 0.003, 0.004],
                "Time_min": [1.0, 2.0, 3.0, 4.0],
                "SnNorm": [0.9, 0.6, 0.2, 0.03],
                "Stage": ["early", "middle", "late", "near-depleted"],
                "ValidStructure": [True, True, True, False],
            }
        )
        data_plotted = data_all.iloc[:2].copy()
        write_workbook(
            figures_dir / "rate_time_lr_vs_a_i_2D_stage_scatter_data.xlsx",
            {"data_all": data_all, "data_plotted": data_plotted},
        )

    def write_binned(self, figures_dir):
        df = pd.DataFrame(
            {
                "metric": ["a_i_2D", "a_i_2D"],
                "stage": ["early", "middle"],
                "bin_id": [0, 1],
                "x_bin_min": [10.0, 20.0],
                "x_bin_max": [20.0, 30.0],
                "x_bin_median": [15.0, 25.0],
                "rate_median": [0.001, 0.003],
                "rate_p25": [0.0005, 0.0025],
                "rate_p75": [0.0015, 0.0035],
                "n": [5, 6],
            }
        )
        write_workbook(figures_dir / "rate_time_lr_vs_a_i_2D_binned_active_data.xlsx", {"data": df})

    def test_load_manifest_handles_unicode_paths_and_optional_styles(self):
        first = self.figures_dir("实验 数据 A")
        second = self.figures_dir("experiment with spaces")
        manifest = self.write_manifest(
            [
                {
                    "label": "4 uL",
                    "figures_dir": str(first),
                    "color": "#111111",
                    "marker": "D",
                    "linestyle": "--",
                    "order": 2,
                },
                {
                    "label": "6 uL",
                    "figures_dir": str(second),
                    "color": "#222222",
                    "marker": "s",
                    "linestyle": "-.",
                    "order": 1,
                },
            ]
        )

        experiments = comparison.load_manifest(manifest)

        self.assertEqual([exp.label for exp in experiments], ["6 uL", "4 uL"])
        self.assertEqual(experiments[0].figures_dir, second)
        self.assertEqual(experiments[1].color, "#111111")
        self.assertEqual(experiments[1].marker, "D")
        self.assertEqual(experiments[1].linestyle, "--")

    def test_primary_metric_selection_for_known_stems(self):
        cases = [
            ("01_saturation_decay", pd.DataFrame({"Sn": [1.0], "SnNorm": [1.0]}), ["SnNorm"]),
            (
                "04_largest_blob_fraction",
                pd.DataFrame({"MaxBlobFrac": [0.2], "MaxBlobFrac_valid": [0.2]}),
                ["MaxBlobFrac_valid"],
            ),
            ("08_a_i_2D", pd.DataFrame({"a_i_2D": [1.0], "a_i_2D_valid": [1.0]}), ["a_i_2D_valid"]),
            (
                "09_mean_circularity",
                pd.DataFrame({"MeanCircularity": [0.8], "MeanCircularity_valid": [0.7]}),
                ["MeanCircularity_valid"],
            ),
            (
                "10_fraction_droplets",
                pd.DataFrame({"fracDroplets": [0.5], "areaFracDropletsValid": [0.6]}),
                ["areaFracDropletsValid"],
            ),
            (
                "S10_count_fraction_droplets",
                pd.DataFrame({"countFracDroplets": [0.4], "countFracDropletsValid": [0.7]}),
                ["countFracDropletsValid"],
            ),
        ]
        for stem, df, expected in cases:
            with self.subTest(stem=stem):
                self.assertEqual(comparison.select_y_columns(stem, df), expected)

    def test_create_comparison_outputs_saturation_png_svg_and_data(self):
        rows = []
        for idx, label in enumerate(["4 uL", "6 uL", "8 uL"]):
            figures_dir = self.figures_dir(f"exp_{idx}")
            self.write_saturation(figures_dir, sn0=0.30 + idx * 0.01)
            rows.append({"label": label, "figures_dir": str(figures_dir)})
        manifest = self.write_manifest(rows)
        out_dir = self.root / "comparison"

        experiments = comparison.load_manifest(manifest)
        written = comparison.create_comparison(
            experiments,
            "01_saturation_decay",
            out_dir,
            dpi=80,
        )

        written_names = {path.name for path in written}
        self.assertIn("comparison_01_saturation_decay.png", written_names)
        self.assertIn("comparison_01_saturation_decay.svg", written_names)
        self.assertIn("comparison_01_saturation_decay_log.png", written_names)
        self.assertIn("comparison_01_saturation_decay_log.svg", written_names)
        self.assertIn("comparison_01_saturation_decay_data.xlsx", written_names)
        combined = pd.read_excel(out_dir / "comparison_01_saturation_decay_data.xlsx", sheet_name="data")
        self.assertEqual(set(combined["ExperimentLabel"]), {"4 uL", "6 uL", "8 uL"})
        self.assertEqual(set(combined["SeriesName"]), {"SnNorm"})
        self.assertEqual(len(combined), 15)
        self.assertIn("Time_min", combined.columns)

    def test_custom_workbook_manifest_and_out_stem(self):
        workbook_a = self.root / "custom inputs" / "sn_curve_a.xlsx"
        workbook_b = self.root / "custom inputs" / "sn_curve_b.xlsx"
        self.write_custom_saturation_workbook(workbook_a, sn0=0.30)
        self.write_custom_saturation_workbook(workbook_b, sn0=0.36)
        manifest = self.write_manifest(
            [
                {"label": "A", "workbook": str(workbook_a), "color": "#0072B2"},
                {"label": "B", "workbook": str(workbook_b), "color": "#D55E00"},
            ]
        )
        out_dir = self.root / "custom_out"
        experiments = comparison.load_manifest(manifest)

        written = comparison.create_comparison(
            experiments,
            "not_used_for_workbook_lookup",
            out_dir,
            out_stem="custom_saturation_name",
            x="Time_min",
            y="SnNorm",
            dpi=80,
        )

        written_names = {path.name for path in written}
        self.assertIn("custom_saturation_name.png", written_names)
        self.assertIn("custom_saturation_name.svg", written_names)
        self.assertIn("custom_saturation_name_log.png", written_names)
        self.assertIn("custom_saturation_name_data.xlsx", written_names)
        self.assertNotIn("comparison_not_used_for_workbook_lookup.png", written_names)
        combined = pd.read_excel(out_dir / "custom_saturation_name_data.xlsx", sheet_name="data")
        self.assertEqual(set(combined["ExperimentLabel"]), {"A", "B"})
        self.assertEqual(set(combined["SourceWorkbook"]), {str(workbook_a), str(workbook_b)})

    def test_rate_scatter_uses_data_plotted_sheet_by_default(self):
        rows = []
        for idx, label in enumerate(["4 uL", "8 uL"]):
            figures_dir = self.figures_dir(f"rate_{idx}")
            self.write_rate_scatter(figures_dir)
            rows.append({"label": label, "figures_dir": str(figures_dir)})
        out_dir = self.root / "scatter_out"
        experiments = comparison.load_manifest(self.write_manifest(rows))

        written = comparison.create_comparison(
            experiments,
            "rate_time_lr_vs_a_i_2D_stage_scatter",
            out_dir,
            dpi=80,
        )

        written_names = {path.name for path in written}
        self.assertIn("comparison_rate_time_lr_vs_a_i_2D_stage_scatter.png", written_names)
        self.assertNotIn("comparison_rate_time_lr_vs_a_i_2D_stage_scatter_log.png", written_names)
        combined = pd.read_excel(
            out_dir / "comparison_rate_time_lr_vs_a_i_2D_stage_scatter_data.xlsx",
            sheet_name="data",
        )
        self.assertEqual(set(combined["SourceSheet"]), {"data_plotted"})
        self.assertEqual(set(combined["SeriesName"]), {"DissolutionRate_Sn_time_lr"})
        self.assertEqual(len(combined), 4)

    def test_binned_summary_outputs_errorbar_data(self):
        rows = []
        for idx, label in enumerate(["4 uL", "6 uL"]):
            figures_dir = self.figures_dir(f"binned_{idx}")
            self.write_binned(figures_dir)
            rows.append({"label": label, "figures_dir": str(figures_dir)})
        out_dir = self.root / "binned_out"
        experiments = comparison.load_manifest(self.write_manifest(rows))

        written = comparison.create_comparison(
            experiments,
            "rate_time_lr_vs_a_i_2D_binned_active",
            out_dir,
            dpi=80,
        )

        written_names = {path.name for path in written}
        self.assertIn("comparison_rate_time_lr_vs_a_i_2D_binned_active.png", written_names)
        self.assertNotIn("comparison_rate_time_lr_vs_a_i_2D_binned_active_log.png", written_names)
        combined = pd.read_excel(
            out_dir / "comparison_rate_time_lr_vs_a_i_2D_binned_active_data.xlsx",
            sheet_name="data",
        )
        self.assertEqual(set(combined["SeriesName"]), {"rate_median"})
        self.assertEqual(combined["X"].dropna().tolist(), [15.0, 25.0, 15.0, 25.0])
        self.assertEqual(combined["Y"].dropna().tolist(), [0.001, 0.003, 0.001, 0.003])

    def test_missing_workbook_behavior(self):
        present = self.figures_dir("present")
        missing = self.figures_dir("missing")
        self.write_saturation(present)
        manifest = self.write_manifest(
            [
                {"label": "present", "figures_dir": str(present)},
                {"label": "missing", "figures_dir": str(missing)},
            ]
        )
        experiments = comparison.load_manifest(manifest)

        with self.assertRaises(FileNotFoundError):
            comparison.create_comparison(
                experiments,
                "01_saturation_decay",
                self.root / "fail_out",
                dpi=80,
            )

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            comparison.create_comparison(
                experiments,
                "01_saturation_decay",
                self.root / "allow_out",
                allow_missing=True,
                dpi=80,
            )
        self.assertTrue(any("Skipping missing workbook" in str(item.message) for item in caught))
        combined = pd.read_excel(self.root / "allow_out" / "comparison_01_saturation_decay_data.xlsx")
        self.assertEqual(set(combined["ExperimentLabel"]), {"present"})


if __name__ == "__main__":
    unittest.main()
