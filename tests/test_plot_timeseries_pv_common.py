import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "visualization" / "plot_timeseries_pv_common.py"
SPEC = importlib.util.spec_from_file_location("plot_timeseries_pv_common", MODULE_PATH)
plot_timeseries_pv_common = importlib.util.module_from_spec(SPEC)
sys.modules["plot_timeseries_pv_common"] = plot_timeseries_pv_common
SPEC.loader.exec_module(plot_timeseries_pv_common)


def _plotter(name):
    def plot(ax, df, log_scale=False):
        return None

    plot.__name__ = name
    return plot


class FakePlotTimeseriesModule:
    def __init__(self):
        self.plt = SimpleNamespace(close=lambda fig: None)
        self.saved_stems = []
        self.data_stems = []
        self.PLOTTERS = [("01_saturation_decay", _plotter("plot_sn"))]
        self.SUPPLEMENTAL_METRIC_PLOTTERS = [("S13_a_i_2D_flow", _plotter("plot_ai_2d_flow"))]
        self.SUPPLEMENTAL_COUNT_PLOTTERS = [
            ("S10_count_fraction_droplets", _plotter("plot_count_frac_droplets"))
        ]
        self.DATA_EXPORTS = [
            ("01_saturation_decay", ["RealTime_s", "Time_min", "PV", "Sn"]),
            ("S13_a_i_2D_flow", ["RealTime_s", "Time_min", "PV", "a_i_2D_flow"]),
        ]
        self.SUPPLEMENTAL_COUNT_DATA_EXPORTS = [
            (
                "S10_count_fraction_droplets",
                ["RealTime_s", "Time_min", "PV", "countFracDroplets", "countFracDropletsValid"],
            )
        ]

    def configure_nature_style(self):
        return None

    def style_axes(self, ax):
        return None

    def _prepare_plot_df(self, df, smooth_window=101, smooth_polyorder=3, rate_lr_window=101):
        return df.copy()

    def _create_combined_figure(self, df, log_scale=False):
        return object()

    def _create_individual_figure(self, df, plotter, log_scale=False):
        return object()

    def _save_figure(self, fig, stem, figures_dir, dpi):
        self.saved_stems.append(stem)
        return [Path(figures_dir) / f"{stem}.png", Path(figures_dir) / f"{stem}.svg"]

    def _write_data_workbook(self, df, stem, columns, figures_dir):
        self.data_stems.append((stem, tuple(columns)))
        return Path(figures_dir) / f"{stem}_data.xlsx"


class PlotTimeseriesPVCommonTests(unittest.TestCase):
    def test_pv_wrapper_includes_supplemental_metric_and_count_outputs(self):
        module = FakePlotTimeseriesModule()
        df = pd.DataFrame(
            {
                "RealTime_s": [0.0, 60.0],
                "Time_min": [0.0, 1.0],
                "PV": [0.0, 2.0],
                "Sn": [1.0, 0.9],
                "a_i_2D_flow": [100.0, 90.0],
                "countFracDroplets": [0.4, 0.5],
                "countFracDropletsValid": [0.4, 0.5],
            }
        )
        args = SimpleNamespace(
            dpi=300,
            smooth_window=101,
            smooth_polyorder=3,
            rate_lr_window=101,
            min_blob_area_px=20,
        )

        with tempfile.TemporaryDirectory() as tmp:
            plot_timeseries_pv_common.create_all_figures_pv(module, df, Path(tmp), args)

        self.assertIn("S13_a_i_2D_flow", module.saved_stems)
        self.assertIn("S13_a_i_2D_flow_log", module.saved_stems)
        self.assertIn("S10_count_fraction_droplets", module.saved_stems)
        self.assertIn("S10_count_fraction_droplets_log", module.saved_stems)
        data_stems = {stem for stem, _ in module.data_stems}
        self.assertIn("S13_a_i_2D_flow", data_stems)
        self.assertIn("S10_count_fraction_droplets", data_stems)


if __name__ == "__main__":
    unittest.main()
