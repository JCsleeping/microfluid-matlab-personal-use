import importlib.util
import inspect
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

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
            "MeanCircularity": [0.62, 0.61, 0.59, 0.57, 0.55, 0.54, 0.52],
            "a_i_2D": [40000, 39000, 37500, 36000, 34200, 32500, 31000],
            "fracDroplets": [0.14, 0.15, 0.17, 0.19, 0.21, 0.22, 0.24],
            "fracColumns": [0.28, 0.27, 0.26, 0.25, 0.23, 0.22, 0.20],
            "fracClusters": [0.58, 0.58, 0.57, 0.56, 0.56, 0.56, 0.56],
            "Interval_s": [0, 60, 120, 180, 240, 300, 360],
        }
    )
    csv_path = output_dir / filename
    df.to_csv(csv_path, index=False)
    return csv_path


def write_blob_detail_csv(output_dir: Path) -> Path:
    df = pd.DataFrame(
        {
            "FrameIndex": [1, 1, 3, 3, 5, 5, 7, 7],
            "FrameTime": [0, 0, 180, 180, 600, 600, 1260, 1260],
            "BlobID": [1, 2, 1, 2, 1, 2, 1, 2],
            "Area": [100.0, 10.0, 80.0, 30.0, 70.0, 50.0, 40.0, 25.0],
            "Perimeter": [40.0, 10.0, 0.0, 20.0, 15.0, 28.0, 22.0, 18.0],
            "Circularity": [0.78, 0.95, 0.8, 1.2, 1.1, 0.7, 0.9, 0.6],
            "EquivRadius": [5.6, 1.8, 5.0, 3.1, 4.7, 4.0, 3.6, 2.8],
            "TopologyType": [
                "droplet",
                "droplet",
                "column",
                "cluster",
                "cluster",
                "cluster",
                "column",
                "droplet",
            ],
        }
    )
    path = output_dir / "blob_detail_all_frames.csv"
    df.to_csv(path, index=False)
    return path


class PlotTimeseriesTests(unittest.TestCase):
    def test_find_timeseries_csv_requires_corrected_realtime_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            write_sample_csv(output_dir, filename="some_timeseries.csv")

            with self.assertRaises(FileNotFoundError):
                plot_timeseries.find_timeseries_csv(output_dir)

    def test_find_timeseries_csv_selects_newest_corrected_realtime_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            older = write_sample_csv(output_dir, filename="timeseries_realtime_20260508_105232.csv")
            newer = write_sample_csv(output_dir, filename="timeseries_realtime_20260508_110000.csv")
            older.touch()
            newer.touch()

            selected = plot_timeseries.find_timeseries_csv(output_dir)

            self.assertEqual(selected, newer)

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

            missing_microstructure_path = output_dir / "timeseries_realtime_missing_microstructure.csv"
            pd.read_csv(csv_path).drop(columns=["a_i_2D", "MeanCircularity"]).to_csv(
                missing_microstructure_path, index=False
            )

            with self.assertRaisesRegex(ValueError, "a_i_2D.*MeanCircularity|MeanCircularity.*a_i_2D"):
                plot_timeseries.load_timeseries(missing_microstructure_path)

    def test_load_timeseries_preserves_corrected_realtime_origin(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path = write_sample_csv(output_dir)
            df = pd.read_csv(csv_path)
            df["RealTime_s"] = df["RealTime_s"] + 120
            df.to_csv(csv_path, index=False)

            loaded = plot_timeseries.load_timeseries(csv_path)

            self.assertEqual(loaded.loc[0, "RealTime_s"], 120)
            self.assertEqual(loaded.loc[0, "Time_min"], 2)
            self.assertEqual(loaded.loc[2, "Time_min"], 5)

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

    def test_publication_rate_is_monotone_nonnegative_and_uses_linear_time(self):
        time_min = np.array([0.0, 1.0, 2.0, 4.0, 7.0, 11.0, 16.0])
        sn = np.array([1.0, 0.94, 0.955, 0.88, 0.81, 0.75, 0.68])
        df = pd.DataFrame({"Time_min": time_min, "Sn": sn})

        raw = plot_timeseries.compute_raw_dissolution_rate(df)
        rate = plot_timeseries.compute_dissolution_rate(df, smooth_window=1, rate_lr_window=3)

        self.assertLess(raw.iloc[1], 0)
        self.assertTrue((rate >= -1e-12).all())

        linear_df = pd.DataFrame(
            {
                "Time_min": [1.0, 10.0, 100.0, 1000.0],
                "Sn": [1.0, 0.91, 0.01, 0.0],
            }
        )
        linear_rate = plot_timeseries.compute_dissolution_rate(
            linear_df,
            smooth_window=1,
            rate_lr_window=3,
        )
        self.assertAlmostEqual(linear_rate.iloc[1], 0.01, places=6)

    def test_log_synthetic_start_uses_adjacent_interval_from_zero(self):
        df = pd.DataFrame({"Time_min": [0.0, 10.0, 100.0], "Sn": [1.0, 0.9, 0.5]})

        x, y = plot_timeseries._x_and_y(df, "Sn", log_scale=True)

        self.assertEqual(x[0], 0.5)
        self.assertEqual(y[0], 1.0)

    def test_log_synthetic_start_uses_earliest_time_value_even_if_unsorted(self):
        df = pd.DataFrame({"Time_min": [10.0, 0.0, 100.0], "Sn": [0.9, 1.0, 0.5]})

        x, y = plot_timeseries._x_and_y(df, "Sn", log_scale=True)

        self.assertEqual(x[0], 0.5)
        self.assertEqual(y[0], 1.0)

    def test_log_dissolution_rate_uses_first_positive_rate_for_synthetic_start(self):
        df = pd.DataFrame(
            {
                "Time_min": [0.0, 1.0, 2.0],
                "DissolutionRate_per_min": [99.0, 0.2, 0.3],
            }
        )
        fig, ax = plot_timeseries.plt.subplots()
        try:
            plot_timeseries.plot_dissolution_rate(ax, df, log_scale=True)

            ydata = ax.lines[0].get_ydata()
            self.assertEqual(ydata[0], 0.2)
        finally:
            plot_timeseries.plt.close(fig)

    def test_prepare_plot_df_adds_largest_blob_flow_fraction(self):
        df = pd.DataFrame(
            {
                "Time_min": [0.0, 1.0, 2.0],
                "Sn": [0.30, 0.20, 0.10],
                "MaxBlobFrac": [0.10, 0.50, 0.25],
            }
        )

        plot_df = plot_timeseries._prepare_plot_df(df, smooth_window=0, smooth_polyorder=2)

        self.assertIn("MaxBlobFlowFrac", plot_df.columns)
        np.testing.assert_allclose(plot_df["MaxBlobFlowFrac"], [0.03, 0.10, 0.025])

    def test_prepare_plot_df_adds_sn_norm_valid_structure_and_stage(self):
        df = pd.DataFrame(
            {
                "Time_min": [0.0, 1.0, 2.0, 3.0],
                "Sn": [1.0, 0.80, 0.40, 0.03],
                "NumBlobs": [25, 19, 30, 30],
                "MaxBlobFrac": [0.1, 0.2, 0.3, 0.4],
                "a_i_2D": [10.0, 20.0, 30.0, 40.0],
            }
        )

        plot_df = plot_timeseries._prepare_plot_df(
            df,
            smooth_window=1,
            smooth_polyorder=2,
            rate_lr_window=3,
        )

        np.testing.assert_allclose(plot_df["SnNorm"], [1.0, 0.80, 0.40, 0.03])
        self.assertEqual(plot_df["ValidStructure"].tolist(), [True, False, True, False])
        self.assertEqual(
            plot_df["DissolutionStage"].tolist(),
            ["early", "early", "middle", "near-depleted"],
        )
        self.assertIn("DissolutionRate_raw_per_min", plot_df.columns)
        self.assertIn("Sn_mono_rate", plot_df.columns)

    def test_plot_largest_blob_flow_fraction_uses_derived_column(self):
        df = pd.DataFrame({"Time_min": [0.0, 1.0, 2.0], "MaxBlobFlowFrac": [0.03, 0.10, 0.025]})
        fig, ax = plot_timeseries.plt.subplots()
        try:
            plot_timeseries.plot_max_blob_flow_frac(ax, df)

            np.testing.assert_allclose(ax.lines[0].get_ydata(), [0.03, 0.10, 0.025])
            self.assertEqual(ax.get_ylabel(), "Amax / Aflow")
        finally:
            plot_timeseries.plt.close(fig)

    def test_new_microstructure_time_plotters_use_requested_columns(self):
        df = pd.DataFrame(
            {
                "Time_min": [0.0, 1.0, 2.0],
                "a_i_2D": [10.0, 9.0, 8.0],
                "MeanCircularity": [0.8, 0.7, 0.6],
                "fracDroplets": [0.1, 0.2, 0.3],
                "fracColumns": [0.4, 0.3, 0.2],
                "fracClusters": [0.5, 0.5, 0.5],
            }
        )
        plotter_specs = [
            (plot_timeseries.plot_ai_2d, "a_i_2D", [10.0, 9.0, 8.0], "Specific interfacial area"),
            (plot_timeseries.plot_mean_circularity, "MeanCircularity", [0.8, 0.7, 0.6], "Mean circularity"),
            (plot_timeseries.plot_frac_droplets, "fracDroplets", [0.1, 0.2, 0.3], "Droplet fraction"),
            (plot_timeseries.plot_frac_columns, "fracColumns", [0.4, 0.3, 0.2], "Column fraction"),
            (plot_timeseries.plot_frac_clusters, "fracClusters", [0.5, 0.5, 0.5], "Cluster fraction"),
        ]

        for plotter, _column, expected_y, ylabel in plotter_specs:
            fig, ax = plot_timeseries.plt.subplots()
            try:
                plotter(ax, df)
                np.testing.assert_allclose(ax.lines[0].get_ydata(), expected_y)
                self.assertIn(ylabel, ax.get_ylabel())
            finally:
                plot_timeseries.plt.close(fig)

    def test_stage_rate_plot_colours_near_depleted_grey(self):
        df = pd.DataFrame(
            {
                "Time_min": [0.0, 1.0, 2.0, 3.0],
                "a_i_2D": [10.0, 20.0, 30.0, 40.0],
                "DissolutionRate_per_min": [0.1, 0.2, 0.05, 0.01],
                "DissolutionStage": ["early", "middle", "late", "near-depleted"],
            }
        )
        fig, ax = plot_timeseries.plt.subplots()
        try:
            plot_timeseries.plot_rate_vs_ai_2d_stage(ax, df)

            labels = {collection.get_label() for collection in ax.collections}
            self.assertTrue({"early", "middle", "late", "near-depleted"}.issubset(labels))
            near_collection = [
                collection for collection in ax.collections if collection.get_label() == "near-depleted"
            ][0]
            np.testing.assert_allclose(near_collection.get_facecolor()[0, :3], [0.6, 0.6, 0.6], atol=0.05)
        finally:
            plot_timeseries.plt.close(fig)

    def test_blob_detail_qc_filters_circularity_and_recomputes_topology_fractions(self):
        timeseries = pd.DataFrame(
            {
                "FrameIndex": [1, 3, 5],
                "Time_min": [0.0, 3.0, 10.0],
                "SnNorm": [1.0, 0.4, 0.03],
                "NumBlobs": [25, 30, 30],
                "fracDroplets": [0.5, 0.1, 0.2],
                "fracColumns": [0.2, 0.4, 0.3],
                "fracClusters": [0.3, 0.5, 0.5],
            }
        )
        blob_detail = pd.DataFrame(
            {
                "FrameIndex": [1, 1, 3, 3, 5],
                "Area": [100.0, 10.0, 80.0, 30.0, 70.0],
                "Perimeter": [40.0, 10.0, 0.0, 20.0, 15.0],
                "Circularity": [0.8, 0.9, 0.8, 1.2, 0.7],
                "EquivRadius": [5.0, 2.0, 4.0, 3.0, 4.5],
                "TopologyType": ["droplet", "droplet", "column", "cluster", "cluster"],
            }
        )

        enriched, qc = plot_timeseries.apply_blob_detail_qc(
            timeseries,
            blob_detail,
            min_blob_area_px=20,
        )

        self.assertAlmostEqual(enriched.loc[enriched["FrameIndex"] == 1, "MeanCircularity_valid"].iloc[0], 0.8)
        self.assertTrue(np.isnan(enriched.loc[enriched["FrameIndex"] == 3, "MeanCircularity_valid"].iloc[0]))
        self.assertIn("gt1_blobs", qc["circularity"])
        self.assertEqual(len(qc["circularity"]["gt1_blobs"]), 1)
        topology = qc["topology"]["by_frame"]
        row1 = topology.loc[topology["FrameIndex"] == 1].iloc[0]
        self.assertAlmostEqual(row1["areaFracDroplets"], 1.0)
        self.assertAlmostEqual(row1["countFracDroplets"], 1.0)
        row3 = topology.loc[topology["FrameIndex"] == 3].iloc[0]
        self.assertAlmostEqual(row3["areaFracColumns"], 80.0 / 110.0)
        self.assertAlmostEqual(row3["areaFracClusters"], 30.0 / 110.0)
        self.assertAlmostEqual(row3["countFracColumns"], 0.5)
        self.assertAlmostEqual(row3["countFracClusters"], 0.5)
        self.assertEqual(qc["topology"]["classification"], "ambiguous")

    def test_selected_frame_blob_detail_uses_nearest_times(self):
        timeseries = pd.DataFrame(
            {
                "FrameIndex": [1, 2, 3],
                "Time_min": [0.0, 29.0, 71.0],
                "SnNorm": [1.0, 0.8, 0.6],
            }
        )
        blob_detail = pd.DataFrame(
            {
                "FrameIndex": [2, 3],
                "Area": [100.0, 120.0],
                "Perimeter": [30.0, 40.0],
                "Circularity": [0.8, 0.7],
                "EquivRadius": [5.0, 6.0],
            }
        )

        selected = plot_timeseries.selected_req_distribution_data(
            timeseries,
            blob_detail,
            target_times=(30, 70),
            min_blob_area_px=20,
        )

        self.assertEqual(selected["FrameIndex"].tolist(), [2, 3])
        self.assertEqual(selected["TargetTime_min"].tolist(), [30, 70])

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

    def test_req_stats_uses_plan_colors_and_legend_position(self):
        df = pd.DataFrame(
            {
                "Time_min": [0.0, 1.0, 2.0],
                "ReqMedian": [1.0, 2.0, 3.0],
                "ReqMean": [1.5, 2.5, 3.5],
                "ReqStd": [0.2, 0.3, 0.4],
            }
        )
        fig, ax = plot_timeseries.plt.subplots()
        try:
            plot_timeseries.plot_req_stats(ax, df)

            self.assertEqual([line.get_color() for line in ax.lines], ["#0072B2", "#D55E00", "#009E73"])
            legend = ax.get_legend()
            self.assertIsNotNone(legend)
            self.assertFalse(legend.get_frame().get_visible())
            self.assertEqual(legend._loc, 8)
            self.assertAlmostEqual(legend.get_bbox_to_anchor()._bbox.x0, 0.5)
            self.assertAlmostEqual(legend.get_bbox_to_anchor()._bbox.y0, 1.04)
        finally:
            plot_timeseries.plt.close(fig)

    def test_save_figure_uses_white_facecolor_for_png_and_svg(self):
        with tempfile.TemporaryDirectory() as tmp:
            fig = plot_timeseries.plt.figure()
            try:
                with mock.patch.object(fig, "savefig") as savefig:
                    written = plot_timeseries._save_figure(fig, "example", Path(tmp), dpi=300)

                self.assertEqual([path.name for path in written], ["example.png", "example.svg"])
                self.assertEqual(savefig.call_count, 2)
                for call in savefig.call_args_list:
                    self.assertEqual(call.kwargs["facecolor"], "white")
            finally:
                plot_timeseries.plt.close(fig)

    def test_default_png_dpi_is_300(self):
        create_params = inspect.signature(plot_timeseries.create_all_figures).parameters
        self.assertEqual(create_params["dpi"].default, 300)

        args = plot_timeseries.build_arg_parser().parse_args(["output_dir"])
        self.assertEqual(args.dpi, 300)

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
            self.assertIn(f"Figures directory: {figures_dir}", lines)
            saved_lines = [line for line in lines if line.startswith("Saved: ")]
            self.assertEqual(len(saved_lines), 79)
            self.assertEqual(len(lines), 83)

    def test_skip_frames_removes_initial_rows_via_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path = write_sample_csv(output_dir)
            figures_dir = output_dir / "figures_skip"
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = plot_timeseries.main(
                    [
                        str(output_dir),
                        "--csv", str(csv_path),
                        "--figures-dir", str(figures_dir),
                        "--dpi", "80",
                        "--smooth-window", "0",
                        "--skip-frames", "2",
                    ]
                )

            self.assertEqual(exit_code, 0)
            lines = stdout.getvalue().splitlines()
            self.assertEqual(lines[1], "Rows: 5")

    def test_min_time_min_filters_rows_after_skip_frames_via_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path = write_sample_csv(output_dir)
            figures_dir = output_dir / "figures_min_time"
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = plot_timeseries.main(
                    [
                        str(output_dir),
                        "--csv", str(csv_path),
                        "--figures-dir", str(figures_dir),
                        "--dpi", "80",
                        "--smooth-window", "0",
                        "--skip-frames", "1",
                        "--min-time-min", "3",
                    ]
                )

            self.assertEqual(exit_code, 0)
            lines = stdout.getvalue().splitlines()
            self.assertEqual(lines[1], "Rows: 5")

    def test_min_time_min_rejects_when_too_few_rows_remain(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path = write_sample_csv(output_dir)

            with self.assertRaisesRegex(ValueError, "--min-time-min.*fewer than 2 rows"):
                plot_timeseries.main(
                    [
                        str(output_dir),
                        "--csv", str(csv_path),
                        "--dpi", "80",
                        "--min-time-min", "21",
                    ]
                )

    def test_find_pixel_size_um_parses_analysis_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            (output_dir / "analysis_report.txt").write_text(
                "Header line\n"
                "  Pixel Size:                              4.17 μm/px  (4.17e-06 m/px)\n"
                "Some other line\n",
                encoding="utf-8",
            )
            self.assertAlmostEqual(plot_timeseries.find_pixel_size_um(output_dir), 4.17)

    def test_find_pixel_size_um_returns_none_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(plot_timeseries.find_pixel_size_um(Path(tmp)))

    def test_apply_pixel_size_to_req_converts_columns_and_tags_unit(self):
        df = pd.DataFrame(
            {"ReqMedian": [2.0, 3.0], "ReqMean": [4.0, 5.0], "ReqStd": [0.5, 0.6]}
        )
        out = plot_timeseries.apply_pixel_size_to_req(df, 4.17)
        np.testing.assert_allclose(out["ReqMedian"].values, [2.0 * 4.17, 3.0 * 4.17])
        np.testing.assert_allclose(out["ReqMean"].values, [4.0 * 4.17, 5.0 * 4.17])
        np.testing.assert_allclose(out["ReqStd"].values, [0.5 * 4.17, 0.6 * 4.17])
        self.assertEqual(out.attrs["req_unit"], "μm")

    def test_apply_pixel_size_to_req_keeps_pixels_when_unset(self):
        df = pd.DataFrame({"ReqMedian": [2.0], "ReqMean": [3.0], "ReqStd": [0.1]})
        out = plot_timeseries.apply_pixel_size_to_req(df, None)
        np.testing.assert_allclose(out["ReqMedian"].values, [2.0])
        self.assertEqual(out.attrs["req_unit"], "px")

    def test_plot_req_stats_uses_unit_from_df_attrs_in_ylabel(self):
        df = pd.DataFrame(
            {
                "Time_min": [0.0, 1.0, 2.0],
                "ReqMedian": [1.0, 2.0, 3.0],
                "ReqMean": [1.5, 2.5, 3.5],
                "ReqStd": [0.2, 0.3, 0.4],
            }
        )
        df.attrs["req_unit"] = "μm"
        fig, ax = plot_timeseries.plt.subplots()
        try:
            plot_timeseries.plot_req_stats(ax, df)
            self.assertEqual(ax.get_ylabel(), "Equivalent radius (μm)")
        finally:
            plot_timeseries.plt.close(fig)

    def test_main_auto_reads_pixel_size_from_analysis_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path = write_sample_csv(output_dir)
            (output_dir / "analysis_report.txt").write_text(
                "Pixel Size: 4.17 μm/px\n", encoding="utf-8"
            )
            figures_dir = output_dir / "figures_pixel"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = plot_timeseries.main(
                    [
                        str(output_dir),
                        "--csv", str(csv_path),
                        "--figures-dir", str(figures_dir),
                        "--dpi", "80",
                        "--smooth-window", "0",
                    ]
                )
            self.assertEqual(exit_code, 0)
            self.assertIn("Pixel size: 4.17 μm/px", stdout.getvalue())

    def test_skip_frames_rejects_removing_all_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path = write_sample_csv(output_dir)

            with self.assertRaisesRegex(ValueError, "fewer than 2 rows"):
                plot_timeseries.main(
                    [
                        str(output_dir),
                        "--csv", str(csv_path),
                        "--dpi", "80",
                        "--skip-frames", "6",
                    ]
                )

    def test_create_all_figures_writes_plot_data_workbooks_once_per_linear_plot(self):
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

            data_names = {path.name for path in written if path.suffix == ".xlsx"}
            self.assertEqual(
                data_names,
                {
                    "timeseries_6panel_data.xlsx",
                    "01_saturation_decay_data.xlsx",
                    "02_dissolution_rate_data.xlsx",
                    "03_blob_count_data.xlsx",
                    "04_largest_blob_fraction_data.xlsx",
                    "05_equivalent_radius_stats_data.xlsx",
                    "06_interface_area_data.xlsx",
                    "07_largest_blob_flow_fraction_data.xlsx",
                    "08_a_i_2D_data.xlsx",
                    "09_mean_circularity_data.xlsx",
                    "10_fraction_droplets_data.xlsx",
                    "11_fraction_columns_data.xlsx",
                    "12_fraction_clusters_data.xlsx",
                    "13_sn_norm_ai_2D_overlay_data.xlsx",
                    "14_rate_vs_ai_2D_stage_data.xlsx",
                    "structure_validity_qc.xlsx",
                    "circularity_gt1_audit.xlsx",
                    "topology_fraction_audit.xlsx",
                    "summary_metrics.xlsx",
                },
            )
            self.assertFalse(any("_log_data" in name for name in data_names))

            flow_data = pd.read_excel(figures_dir / "07_largest_blob_flow_fraction_data.xlsx")
            self.assertEqual(
                list(flow_data.columns),
                ["RealTime_s", "Time_min", "Sn", "MaxBlobFrac", "MaxBlobFlowFrac"],
            )
            np.testing.assert_allclose(
                flow_data["MaxBlobFlowFrac"],
                flow_data["Sn"] * flow_data["MaxBlobFrac"],
            )

            rate_data = pd.read_excel(figures_dir / "02_dissolution_rate_data.xlsx")
            self.assertEqual(
                list(rate_data.columns),
                ["RealTime_s", "Time_min", "DissolutionRate_per_min"],
            )

            ai_data = pd.read_excel(figures_dir / "08_a_i_2D_data.xlsx")
            self.assertEqual(list(ai_data.columns), ["RealTime_s", "Time_min", "a_i_2D"])

            circularity_data = pd.read_excel(figures_dir / "09_mean_circularity_data.xlsx")
            self.assertEqual(
                list(circularity_data.columns),
                ["RealTime_s", "Time_min", "MeanCircularity", "MeanCircularity_raw", "MeanCircularity_valid"],
            )

            droplets_data = pd.read_excel(figures_dir / "10_fraction_droplets_data.xlsx")
            self.assertEqual(
                list(droplets_data.columns),
                ["RealTime_s", "Time_min", "fracDroplets"],
            )

            saturation_data = pd.read_excel(figures_dir / "01_saturation_decay_data.xlsx")
            self.assertIn("SnNorm", saturation_data.columns)

            rate_data = pd.read_excel(figures_dir / "14_rate_vs_ai_2D_stage_data.xlsx")
            self.assertEqual(
                list(rate_data.columns),
                ["RealTime_s", "Time_min", "a_i_2D", "DissolutionRate_per_min", "DissolutionStage", "ValidStructure"],
            )

    def test_create_all_figures_uses_blob_detail_for_req_distribution_and_audits(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path = write_sample_csv(output_dir)
            write_blob_detail_csv(output_dir)
            df = plot_timeseries.load_timeseries(csv_path)
            figures_dir = output_dir / "figures"

            written = plot_timeseries.create_all_figures(
                df,
                figures_dir=figures_dir,
                dpi=80,
                smooth_window=1,
                smooth_polyorder=2,
                rate_lr_window=3,
                output_dir=output_dir,
                min_blob_area_px=20,
            )

            names = {path.name for path in written}
            self.assertIn("15_req_distribution.png", names)
            self.assertIn("15_req_distribution.svg", names)
            for stem in (
                "S10_count_fraction_droplets",
                "S11_count_fraction_columns",
                "S12_count_fraction_clusters",
            ):
                self.assertIn(f"{stem}.png", names)
                self.assertIn(f"{stem}.svg", names)
                self.assertIn(f"{stem}_log.png", names)
                self.assertIn(f"{stem}_log.svg", names)
                self.assertIn(f"{stem}_data.xlsx", names)
            circularity = pd.read_excel(figures_dir / "circularity_gt1_audit.xlsx", sheet_name="gt1_blobs")
            self.assertIn("Circularity", circularity.columns)
            topology = pd.read_excel(figures_dir / "topology_fraction_audit.xlsx", sheet_name="by_frame")
            self.assertIn("areaFracDroplets", topology.columns)
            self.assertIn("countFracDroplets", topology.columns)
            droplets_data = pd.read_excel(figures_dir / "10_fraction_droplets_data.xlsx")
            for column in (
                "fracDroplets",
                "areaFracDroplets",
                "areaFracDropletsValid",
                "countFracDroplets",
                "countFracDropletsValid",
            ):
                self.assertIn(column, droplets_data.columns)
            invalid_row = droplets_data.loc[droplets_data["Time_min"] == 21.0].iloc[0]
            self.assertTrue(np.isnan(invalid_row["areaFracDropletsValid"]))
            self.assertTrue(np.isnan(invalid_row["countFracDropletsValid"]))
            count_data = pd.read_excel(figures_dir / "S10_count_fraction_droplets_data.xlsx")
            self.assertEqual(
                list(count_data.columns),
                ["RealTime_s", "Time_min", "countFracDroplets", "countFracDropletsValid"],
            )
            summary = pd.read_excel(figures_dir / "summary_metrics.xlsx")
            self.assertIn("ReliablePeak_a_i_2D", summary["Metric"].tolist())

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
                "07_largest_blob_flow_fraction",
                "08_a_i_2D",
                "09_mean_circularity",
                "10_fraction_droplets",
                "11_fraction_columns",
                "12_fraction_clusters",
                "13_sn_norm_ai_2D_overlay",
                "14_rate_vs_ai_2D_stage",
            ]
            expected_names = set()
            for base in linear_basenames:
                expected_names.add(f"{base}.png")
                expected_names.add(f"{base}.svg")
                expected_names.add(f"{base}_log.png")
                expected_names.add(f"{base}_log.svg")
                expected_names.add(f"{base}_data.xlsx")
            expected_names.update(
                {
                    "structure_validity_qc.xlsx",
                    "circularity_gt1_audit.xlsx",
                    "topology_fraction_audit.xlsx",
                    "summary_metrics.xlsx",
                }
            )

            self.assertEqual({path.name for path in written}, expected_names)
            for path in written:
                self.assertTrue(path.exists(), path)
                self.assertGreater(path.stat().st_size, 500, path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
