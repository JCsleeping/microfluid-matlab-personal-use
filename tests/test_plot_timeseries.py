import importlib.util
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "visualization" / "plot_timeseries.py"
SPEC = importlib.util.spec_from_file_location("plot_timeseries", MODULE_PATH)
plot_timeseries = importlib.util.module_from_spec(SPEC)
sys.modules["plot_timeseries"] = plot_timeseries
SPEC.loader.exec_module(plot_timeseries)


def write_sample_csv(output_dir: Path, filename: str = "timeseries_realtime_sample.csv") -> Path:
    df = pd.DataFrame(
        {
            "RealTime_s": [0, 60, 180, 360, 600, 900, 1260],
            "Sn": [1.00, 0.99, 0.97, 0.94, 0.90, 0.85, 0.79],
            "NumBlobs": [12, 13, 15, 14, 11, 9, 8],
            "MaxBlobFrac": [0.31, 0.32, 0.35, 0.37, 0.41, 0.44, 0.46],
            "ReqMedian": [21.0, 20.4, 19.6, 18.9, 18.2, 17.5, 16.8],
            "ReqMean": [25.0, 24.1, 23.4, 22.9, 21.8, 20.6, 19.9],
            "ReqStd": [4.3, 4.1, 3.9, 3.8, 3.5, 3.4, 3.2],
            "InterfaceArea": [820, 835, 850, 842, 810, 770, 730],
            "Interval_s": [0, 60, 120, 180, 240, 300, 360],
        }
    )
    csv_path = output_dir / filename
    df.to_csv(csv_path, index=False)
    return csv_path


class PlotTimeseriesTests(unittest.TestCase):
    def test_load_timeseries_adds_minutes_and_checks_required_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path = write_sample_csv(output_dir)

            df = plot_timeseries.load_timeseries(csv_path)

            self.assertIn("Time_min", df.columns)
            self.assertEqual(df.loc[0, "Time_min"], 0)
            self.assertEqual(df.loc[2, "Time_min"], 3)
            self.assertEqual(df.loc[6, "Time_min"], 21)

            broken_path = output_dir / "timeseries_realtime_broken.csv"
            pd.read_csv(csv_path).drop(columns=["InterfaceArea"]).to_csv(broken_path, index=False)

            with self.assertRaisesRegex(ValueError, "InterfaceArea"):
                plot_timeseries.load_timeseries(broken_path)

    def test_load_timeseries_rejects_nonfinite_required_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path = write_sample_csv(output_dir)
            bad_df = pd.read_csv(csv_path)
            bad_df.loc[1, "Sn"] = np.inf
            bad_df["InterfaceArea"] = bad_df["InterfaceArea"].astype(float)
            bad_df.loc[2, "InterfaceArea"] = -np.inf
            bad_path = output_dir / "timeseries_realtime_nonfinite.csv"
            bad_df.to_csv(bad_path, index=False)

            with self.assertRaisesRegex(ValueError, "finite.*Sn.*InterfaceArea"):
                plot_timeseries.load_timeseries(bad_path)

    def test_load_timeseries_requires_at_least_two_finite_time_points(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            header_only_path = output_dir / "timeseries_realtime_empty.csv"
            pd.DataFrame(columns=plot_timeseries.REQUIRED_COLUMNS).to_csv(header_only_path, index=False)

            with self.assertRaisesRegex(ValueError, "at least two finite time points"):
                plot_timeseries.load_timeseries(header_only_path)

            single_row_path = output_dir / "timeseries_realtime_single.csv"
            pd.read_csv(write_sample_csv(output_dir)).iloc[:1].to_csv(single_row_path, index=False)

            with self.assertRaisesRegex(ValueError, "at least two finite time points"):
                plot_timeseries.load_timeseries(single_row_path)

    def test_compute_dissolution_rate_respects_irregular_realtime(self):
        df = pd.DataFrame(
            {
                "RealTime_s": [0, 60, 180, 360, 600, 900],
                "Sn": [1.00, 0.99, 0.97, 0.94, 0.90, 0.85],
                "NumBlobs": [1, 1, 1, 1, 1, 1],
                "MaxBlobFrac": [0.1, 0.1, 0.1, 0.1, 0.1, 0.1],
                "ReqMedian": [1, 1, 1, 1, 1, 1],
                "ReqMean": [1, 1, 1, 1, 1, 1],
                "ReqStd": [0, 0, 0, 0, 0, 0],
                "InterfaceArea": [10, 10, 10, 10, 10, 10],
            }
        )
        df["Time_min"] = df["RealTime_s"] / 60.0

        rate = plot_timeseries.compute_dissolution_rate(df, smooth_window=0)

        np.testing.assert_allclose(rate.to_numpy(), np.full(6, 0.01), atol=1e-12)
        self.assertEqual(rate.name, "DissolutionRate_per_min")

    def test_log_synthetic_start_uses_adjacent_interval_from_zero(self):
        df = pd.DataFrame({"Time_min": [0.0, 10.0, 100.0], "Sn": [1.0, 0.9, 0.5]})

        x, y = plot_timeseries._x_and_y(df, "Sn", log_scale=True)

        self.assertEqual(x[0], 0.5)
        self.assertEqual(y[0], 1.0)

    def test_log_axis_enables_major_and_minor_gridlines(self):
        df = pd.DataFrame({"Time_min": [0.0, 1.0, 10.0, 100.0], "Sn": [1.0, 0.9, 0.7, 0.4]})
        fig, ax = plot_timeseries.plt.subplots()
        try:
            plot_timeseries.plot_sn(ax, df, log_scale=True)
            fig.canvas.draw()

            self.assertTrue(any(tick.gridline.get_visible() for tick in ax.xaxis.get_major_ticks()))
            self.assertTrue(any(tick.gridline.get_visible() for tick in ax.xaxis.get_minor_ticks()))
        finally:
            plot_timeseries.plt.close(fig)

    def test_nature_style_rcparams_match_plan(self):
        plot_timeseries.configure_nature_style()

        self.assertEqual(plot_timeseries.plt.rcParams["font.sans-serif"][:3], ["Arial", "Helvetica", "DejaVu Sans"])
        self.assertEqual(plot_timeseries.plt.rcParams["font.size"], 8.5)
        self.assertEqual(plot_timeseries.plt.rcParams["axes.labelsize"], 9.5)
        self.assertEqual(plot_timeseries.plt.rcParams["xtick.labelsize"], 8.5)
        self.assertEqual(plot_timeseries.plt.rcParams["ytick.labelsize"], 8.5)
        self.assertEqual(plot_timeseries.plt.rcParams["legend.fontsize"], 8.0)
        self.assertEqual(plot_timeseries.plt.rcParams["lines.solid_capstyle"], "round")
        self.assertEqual(plot_timeseries.plt.rcParams["figure.dpi"], 150)
        self.assertEqual(plot_timeseries.plt.rcParams["savefig.dpi"], 600)
        self.assertEqual(plot_timeseries.plt.rcParams["pdf.fonttype"], 42)
        self.assertEqual(plot_timeseries.plt.rcParams["ps.fonttype"], 42)
        self.assertEqual(plot_timeseries.plt.rcParams["svg.fonttype"], "none")

    def test_axis_line_and_interface_styles_match_plan(self):
        df = pd.DataFrame({"Time_min": [0.0, 1.0, 2.0], "InterfaceArea": [10.0, 11.0, 12.0]})
        fig, ax = plot_timeseries.plt.subplots()
        try:
            plot_timeseries.plot_interface_area(ax, df)
            fig.canvas.draw()

            self.assertEqual(ax.spines["bottom"].get_linewidth(), 0.9)
            self.assertEqual(ax.spines["left"].get_linewidth(), 0.9)
            self.assertEqual(ax.spines["bottom"].get_edgecolor(), (0.16862745098039217, 0.16862745098039217, 0.16862745098039217, 1.0))
            self.assertEqual(ax.xaxis.get_tick_params(which="major")["length"], 4.0)
            self.assertEqual(ax.xaxis.get_tick_params(which="major")["width"], 0.9)
            self.assertEqual(ax.xaxis.get_tick_params(which="minor")["length"], 2.2)
            self.assertEqual(ax.xaxis.get_tick_params(which="minor")["width"], 0.6)
            self.assertEqual(ax.lines[0].get_markeredgewidth(), 1.0)
            self.assertEqual(ax.lines[0].get_color(), "#E69F00")
            self.assertEqual(ax.xaxis.get_major_ticks()[0].gridline.get_color(), "#E4E4E4")
            self.assertEqual(ax.xaxis.get_major_ticks()[0].gridline.get_linewidth(), 0.55)
        finally:
            plot_timeseries.plt.close(fig)

    def test_cli_prints_smoke_test_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path = write_sample_csv(output_dir)
            figures_dir = output_dir / "custom_figures"
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = plot_timeseries.main(
                    [
                        str(output_dir),
                        "--csv",
                        str(csv_path),
                        "--figures-dir",
                        str(figures_dir),
                        "--dpi",
                        "80",
                        "--smooth-window",
                        "0",
                    ]
                )

            lines = stdout.getvalue().splitlines()
            self.assertEqual(exit_code, 0)
            self.assertEqual(lines[0], f"Read: {csv_path}")
            self.assertEqual(lines[1], "Rows: 7")
            self.assertEqual(lines[2], f"Figures directory: {figures_dir}")
            self.assertTrue(all(line.startswith("Saved: ") for line in lines[3:]))
            self.assertEqual(len(lines), 31)

    def test_create_all_figures_writes_linear_and_log_png_and_svg(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path = write_sample_csv(output_dir)
            df = plot_timeseries.load_timeseries(csv_path)
            figures_dir = output_dir / "figures"

            written = plot_timeseries.create_all_figures(
                df,
                figures_dir=figures_dir,
                dpi=80,
                smooth_window=0,
                smooth_polyorder=2,
            )

            linear_basenames = [
                "timeseries_6panel",
                "01_saturation_decay",
                "02_dissolution_rate",
                "03_blob_count",
                "04_largest_blob_fraction",
                "05_equivalent_radius_stats",
                "06_interface_area",
            ]
            expected_names = set()
            for base in linear_basenames:
                expected_names.add(f"{base}.png")
                expected_names.add(f"{base}.svg")
                expected_names.add(f"{base}_log.png")
                expected_names.add(f"{base}_log.svg")

            self.assertEqual({path.name for path in written}, expected_names)
            for path in written:
                self.assertTrue(path.exists(), path)
                self.assertGreater(path.stat().st_size, 500, path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
