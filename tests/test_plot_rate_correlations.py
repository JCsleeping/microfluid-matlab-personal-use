import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

# Load plot_timeseries first so plot_rate_correlations finds it via sys.modules.
_PT_PATH = ROOT / "visualization" / "plot_timeseries.py"
_PT_SPEC = importlib.util.spec_from_file_location("plot_timeseries", _PT_PATH)
plot_timeseries = importlib.util.module_from_spec(_PT_SPEC)
sys.modules["plot_timeseries"] = plot_timeseries
_PT_SPEC.loader.exec_module(plot_timeseries)

_PRC_PATH = ROOT / "visualization" / "plot_rate_correlations.py"
_PRC_SPEC = importlib.util.spec_from_file_location("plot_rate_correlations", _PRC_PATH)
plot_rate_correlations = importlib.util.module_from_spec(_PRC_SPEC)
sys.modules["plot_rate_correlations"] = plot_rate_correlations
_PRC_SPEC.loader.exec_module(plot_rate_correlations)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def make_synthetic_df(n=20, with_mass=True, seed=0, sn0=1.0, sn_min=0.05):
    """Build a regularly-sampled DataFrame with all required columns plus mass.

    Sn linearly decreases from ``sn0`` to ``sn_min`` so SnNorm spans every
    stage (induction -> active -> tail -> near_depleted) when ``sn_min``
    falls below the censoring threshold.
    """
    rng = np.random.default_rng(seed)
    real_time_s = np.arange(n) * 30.0
    sn = np.linspace(sn0, sn_min, n)
    df = pd.DataFrame(
        {
            "RealTime_s": real_time_s,
            "Sn": sn,
            "NumBlobs": np.clip(400 - 4 * np.arange(n), 1, None),
            "InterfaceArea": 80000 - 200 * np.arange(n),
            "MaxBlobFrac": np.clip(0.1 + 0.005 * np.arange(n), 0, 1),
            "ReqMedian": np.clip(8.0 - 0.05 * np.arange(n), 0.5, None),
            "ReqMean": np.clip(13.0 - 0.05 * np.arange(n), 1.0, None),
            "ReqStd": np.clip(14.0 - 0.05 * np.arange(n), 1.0, None),
            "a_i_2D": 40000 - 100 * np.arange(n),
            "fracDroplets": np.clip(0.15 + 0.01 * np.arange(n), 0, 1),
            "fracColumns": np.clip(0.25 - 0.005 * np.arange(n), 0, 1),
            "fracClusters": np.clip(0.60 - 0.005 * np.arange(n), 0, 1),
        }
    )
    # Re-normalise the three fractions so they sum to 1.
    frac_sum = (
        df["fracDroplets"] + df["fracColumns"] + df["fracClusters"]
    ).replace(0, np.nan)
    df["fracDroplets"] = df["fracDroplets"] / frac_sum
    df["fracColumns"] = df["fracColumns"] / frac_sum
    df["fracClusters"] = df["fracClusters"] / frac_sum
    if with_mass:
        df["MassDissolvedKg"] = 1e-9 * np.arange(n)
    df["Time_min"] = df["RealTime_s"] / 60.0
    _ = rng  # rng kept for future stochastic extensions; silence linters.
    return df


def write_full_csv(output_dir: Path, n=20) -> Path:
    df = make_synthetic_df(n=n, with_mass=True)
    csv_path = output_dir / "timeseries_realtime_test.csv"
    columns = [
        "RealTime_s",
        "Sn",
        "NumBlobs",
        "MeanBlobSize",
        "InterfaceArea",
        "MaxBlobFrac",
        "ReqMedian",
        "ReqMean",
        "ReqStd",
        "MeanCircularity",
        "a_i_2D",
        "nDroplets",
        "nColumns",
        "nClusters",
        "fracDroplets",
        "fracColumns",
        "fracClusters",
        "MassDissolvedKg",
    ]
    df = df.assign(
        MeanBlobSize=200.0,
        MeanCircularity=0.6,
        nDroplets=10,
        nColumns=20,
        nClusters=370,
    )
    df.loc[:, columns].to_csv(csv_path, index=False)
    full = pd.read_csv(csv_path)
    full["RealTime_s"] = df["RealTime_s"].values
    full["Interval_s"] = 30.0
    full.to_csv(csv_path, index=False)
    return csv_path


def write_minimal_rate_csv(output_dir: Path, n=12) -> Path:
    df = make_synthetic_df(n=n, with_mass=False)
    csv_path = output_dir / "timeseries_realtime_minimal_rate.csv"
    df.loc[:, ["RealTime_s", "Sn", "a_i_2D"]].to_csv(csv_path, index=False)
    return csv_path


# --------------------------------------------------------------------------- #
# Rate-computation tests (legacy path)
# --------------------------------------------------------------------------- #
class RateCorrelationsTests(unittest.TestCase):
    def test_movmedian_recovers_known_slope_on_clean_line(self):
        n = 60
        time_min = np.arange(n) * 0.5
        sn = 1.0 - 0.04 * time_min
        df = pd.DataFrame({"Time_min": time_min, "Sn": sn})
        rate = plot_rate_correlations.compute_dissolution_rate_movmedian(
            df, smooth_window=5, dt_seconds=270.0
        )
        np.testing.assert_allclose(rate.values[10:-10], 0.04, atol=1e-6)
        self.assertEqual(rate.name, "DissolutionRate_Sn_movmed")

    def test_lr_recovers_slope_with_noise(self):
        rng = np.random.default_rng(42)
        n = 60
        time_min = np.linspace(0, 30, n)
        true_slope = -0.02
        sn = 1.0 + true_slope * time_min + rng.normal(scale=0.01, size=n)
        df = pd.DataFrame({"Time_min": time_min, "Sn": sn})
        rate = plot_rate_correlations.compute_dissolution_rate_lr(df, dt_seconds=270.0)
        self.assertAlmostEqual(float(np.mean(rate.values[10:-10])), -true_slope, places=2)
        self.assertEqual(rate.name, "DissolutionRate_Sn_lr")

    def test_lr_handles_irregular_time_steps(self):
        time_min = np.array([0.0, 0.05, 0.2, 0.5, 1.5, 5.0, 10.0, 20.0])
        sn = 1.0 - 0.03 * time_min
        df = pd.DataFrame({"Time_min": time_min, "Sn": sn})
        rate = plot_rate_correlations.compute_dissolution_rate_lr(df, dt_seconds=270.0)
        np.testing.assert_allclose(rate.values, 0.03, atol=1e-8)

    def test_lr_uses_time_window_not_frame_count_on_dense_segments(self):
        rng = np.random.default_rng(0)
        time_min = np.concatenate(
            [np.linspace(0, 1, 200), np.linspace(1.05, 6, 50)]
        )
        true_slope = -0.05
        sn = 1.0 + true_slope * time_min + rng.normal(scale=0.005, size=len(time_min))
        df = pd.DataFrame({"Time_min": time_min, "Sn": sn})
        rate = plot_rate_correlations.compute_dissolution_rate_lr(df, dt_seconds=270.0)
        rate_dense = float(np.mean(rate.values[20:180]))
        rate_sparse = float(np.mean(rate.values[210:240]))
        self.assertAlmostEqual(rate_dense, -true_slope, places=2)
        self.assertAlmostEqual(rate_sparse, -true_slope, places=2)

    def test_movmedian_rejects_nonpositive_dt_seconds(self):
        df = pd.DataFrame({"Time_min": [0.0, 1.0], "Sn": [1.0, 0.5]})
        with self.assertRaisesRegex(ValueError, "dt_seconds must be positive"):
            plot_rate_correlations.compute_dissolution_rate_movmedian(df, dt_seconds=0)
        with self.assertRaisesRegex(ValueError, "dt_seconds must be positive"):
            plot_rate_correlations.compute_dissolution_rate_lr(df, dt_seconds=-1.0)

    def test_normalized_rate_divides_by_sn(self):
        df = pd.DataFrame({"Sn": [0.5, 0.25, 0.0]})
        rate = pd.Series([0.1, 0.2, 0.3])
        normalized = plot_rate_correlations.compute_normalized_rate(rate, df)
        self.assertAlmostEqual(normalized.iloc[0], 0.2)
        self.assertAlmostEqual(normalized.iloc[1], 0.8)
        self.assertGreater(normalized.iloc[2], 1e10)

    def test_mass_rate_uses_realtime_seconds(self):
        df = pd.DataFrame(
            {"RealTime_s": np.arange(0, 50, 10), "MassDissolvedKg": np.arange(0, 50, 10) * 2e-9}
        )
        rate = plot_rate_correlations.compute_mass_rate(df)
        self.assertIsNotNone(rate)
        np.testing.assert_allclose(rate.values, 2e-9, atol=1e-15)

    def test_mass_rate_returns_none_when_column_missing(self):
        df = pd.DataFrame({"RealTime_s": [0, 30], "Sn": [1.0, 0.5]})
        self.assertIsNone(plot_rate_correlations.compute_mass_rate(df))

    def test_projected_interface_length_rate_skipped_when_pixel_size_missing(self):
        df = pd.DataFrame({"InterfaceArea": [100, 200]})
        mass_rate = pd.Series([1e-9, 1e-9])
        unit_info = {"InterfaceArea": {"plot_unit": "px", "conversion": "none"}}
        self.assertIsNone(
            plot_rate_correlations.compute_projected_interface_length_rate(
                df, None, mass_rate, unit_info
            )
        )
        self.assertIsNone(
            plot_rate_correlations.compute_projected_interface_length_rate(
                df, 4.17, None, unit_info
            )
        )

    def test_mass_rate_per_projected_interface_length_uses_length_conversion(self):
        df = pd.DataFrame({"InterfaceArea": [1000.0, 2000.0]})
        mass_rate = pd.Series([1e-9, 2e-9])
        unit_info = {
            "InterfaceArea": {
                "conversion": "multiply_by_pixel_size_m",
                "plot_unit": "m",
                "input_unit": "px_length",
            }
        }
        out = plot_rate_correlations.compute_projected_interface_length_rate(
            df, pixel_size_um=5.0, mass_rate=mass_rate, unit_info=unit_info
        )
        np.testing.assert_allclose(
            out.to_numpy(), [1e-9 / (1000 * 5e-6), 2e-9 / (2000 * 5e-6)]
        )

    def test_mass_transfer_proxy_handles_zero_area(self):
        df = pd.DataFrame({"InterfaceArea": [0.0, 100.0]})
        rate = pd.Series([0.5, 1.0])
        proxy = plot_rate_correlations.compute_mass_transfer_proxy(rate, df)
        self.assertTrue(np.isnan(proxy.iloc[0]))
        self.assertAlmostEqual(proxy.iloc[1], 0.01)

    def test_attach_all_rates_adds_expected_columns(self):
        df = make_synthetic_df(n=15, with_mass=True)
        plot_rate_correlations.attach_all_rates(df, pixel_size_um=4.17)
        for col in (
            "Sn_rate_input",
            "DissolutionRate_Sn_time_lr",
            "DissolutionRate_Sn_movmed",
            "DissolutionRate_Sn_lr",
            "NormalizedDissolutionRate_Sn_time_lr",
            "NormalizedDissolutionRate_Sn_movmed",
            "NormalizedDissolutionRate_Sn_lr",
            "DissolutionRate_mass_kg_per_s",
            "DissolutionRate_per_projected_interface_length_kg_per_s_per_m",
            "MassTransferProxy_time_lr_per_pixel",
            "MassTransferProxy_movmed_per_pixel",
            "MassTransferProxy_lr_per_pixel",
        ):
            self.assertIn(col, df.columns)

    def test_validate_required_columns_lists_missing_core(self):
        df = make_synthetic_df().drop(columns=["Sn"])
        with self.assertRaisesRegex(ValueError, "Sn"):
            plot_rate_correlations.validate_required_columns(df)

    def test_parse_log_x_handles_special_values(self):
        self.assertEqual(plot_rate_correlations._parse_log_x(""), set(plot_rate_correlations.DEFAULT_LOG_X_METRICS))
        self.assertEqual(plot_rate_correlations._parse_log_x("none"), set())
        self.assertIn("a_i_2D", plot_rate_correlations._parse_log_x("a_i_2D, NumBlobs"))
        self.assertIn("a_i_2D", plot_rate_correlations._parse_log_x("all"))
        self.assertEqual(plot_rate_correlations._parse_log_x("auto"), "auto")

    def test_parse_log_x_rejects_unknown_metrics(self):
        with self.assertRaisesRegex(ValueError, "Unknown --log-x metric.*interface_area"):
            plot_rate_correlations._parse_log_x("a_i_2D, interface_area")


# --------------------------------------------------------------------------- #
# New rate path: time-LR + monotone Sn smoothing
# --------------------------------------------------------------------------- #
class TimeWindowRateTests(unittest.TestCase):
    def test_time_lr_recovers_known_slope(self):
        n = 100
        time_min = np.linspace(0, 50, n)
        sn = 1.0 - 0.02 * time_min
        df = pd.DataFrame({"Time_min": time_min, "Sn_rate_input": sn})
        rate = plot_rate_correlations.compute_dissolution_rate_time_lr(
            df, time_col="Time_min", sn_col="Sn_rate_input",
            window_min=20.0, min_points=10,
        )
        # Centre region should be very close to the analytic slope of 0.02.
        np.testing.assert_allclose(rate.values[20:-20], 0.02, atol=1e-6)
        self.assertEqual(rate.name, "DissolutionRate_Sn_time_lr")

    def test_time_lr_uses_window_min_not_frame_count(self):
        """Two segments with different sampling density share the same slope."""
        rng = np.random.default_rng(11)
        time_min = np.concatenate(
            [np.linspace(0, 10, 400), np.linspace(10.05, 60, 80)]
        )
        true_slope = -0.04
        sn = 1.0 + true_slope * time_min + rng.normal(scale=0.005, size=len(time_min))
        df = pd.DataFrame({"Time_min": time_min, "Sn_rate_input": sn})
        rate = plot_rate_correlations.compute_dissolution_rate_time_lr(
            df, window_min=20.0, min_points=10,
        )
        # Drop edge effects.
        rate_dense = float(np.mean(rate.values[40:360]))
        rate_sparse = float(np.mean(rate.values[420:460]))
        self.assertAlmostEqual(rate_dense, -true_slope, places=2)
        self.assertAlmostEqual(rate_sparse, -true_slope, places=2)

    def test_time_lr_rejects_nonpositive_window(self):
        df = pd.DataFrame({"Time_min": [0.0, 1.0], "Sn_rate_input": [1.0, 0.5]})
        with self.assertRaisesRegex(ValueError, "window_min must be positive"):
            plot_rate_correlations.compute_dissolution_rate_time_lr(df, window_min=0)

    def test_prepare_sn_rate_input_monotone(self):
        df = pd.DataFrame(
            {
                "Time_min": np.arange(8) * 0.5,
                "Sn": [1.0, 0.95, 0.97, 0.92, 0.96, 0.85, 0.83, 0.90],
            }
        )
        plot_rate_correlations.prepare_sn_rate_input(
            df, sn_smooth_window_frames=1, monotone=True,
        )
        sri = df["Sn_rate_input"].to_numpy()
        # Cumulative minimum -> never increases from previous value.
        self.assertTrue(np.all(np.diff(sri) <= 1e-12))


# --------------------------------------------------------------------------- #
# Stage masks and validity censoring
# --------------------------------------------------------------------------- #
class StageMaskTests(unittest.TestCase):
    def test_near_depleted_excluded_from_valid_structure(self):
        df = pd.DataFrame(
            {
                "Sn": [1.0, 0.5, 0.04],
                "NumBlobs": [100, 80, 2],
                "InterfaceArea": [50000, 40000, 200],
            }
        )
        plot_rate_correlations.attach_stage_and_masks(df)
        np.testing.assert_array_equal(
            df["ValidStructure"].to_numpy(), np.array([True, True, False])
        )
        self.assertEqual(df["Stage"].iloc[2], "near_depleted")
        self.assertEqual(df["NearDepleted"].iloc[2], True)

    def test_stage_thresholds_match_plan(self):
        df = pd.DataFrame(
            {
                "Sn": [1.0, 0.95, 0.85, 0.10, 0.07, 0.03],
                "NumBlobs": [200] * 6,
                "InterfaceArea": [10000] * 6,
            }
        )
        plot_rate_correlations.attach_stage_and_masks(df)
        stages = df["Stage"].tolist()
        # SnNorm = Sn/Sn0 with Sn0=1.0
        self.assertEqual(stages[0], "induction_or_stable")
        self.assertEqual(stages[1], "induction_or_stable")
        self.assertEqual(stages[2], "active_removal")
        self.assertEqual(stages[3], "active_removal")
        self.assertEqual(stages[4], "tail")
        self.assertEqual(stages[5], "near_depleted")

    def test_low_blob_count_invalidates_structure(self):
        df = pd.DataFrame(
            {"Sn": [0.6, 0.6], "NumBlobs": [100, 5], "InterfaceArea": [4000, 4000]}
        )
        plot_rate_correlations.attach_stage_and_masks(df, min_blobs_valid=20)
        np.testing.assert_array_equal(
            df["ValidStructure"].to_numpy(), np.array([True, False])
        )

    def test_min_sn_norm_valid_010_marks_007_near_depleted(self):
        df = pd.DataFrame({
            "Sn": [1.0, 0.2, 0.07],
            "RealTime_s": [0.0, 60.0, 120.0],
            "NumBlobs": [30, 30, 30],
            "InterfaceArea": [10, 10, 10],
        })
        plot_rate_correlations.attach_stage_and_masks(
            df, min_sn_norm_valid=0.10, min_blobs_valid=20
        )
        self.assertEqual(df.loc[2, "Stage"], "near_depleted")


# --------------------------------------------------------------------------- #
# Unit inference (acceptance tests)
# --------------------------------------------------------------------------- #
class UnitInferenceTests(unittest.TestCase):
    def test_a_i_2D_already_in_per_meter_not_reconverted(self):
        """median(a_i_2D) > 1e3 -> input already 1/m, never multiplied by 1/pixel_size_m."""
        df = pd.DataFrame({"a_i_2D": [4.5e4, 5.0e4], "InterfaceArea": [1.0, 2.0]})
        info = plot_rate_correlations.infer_metric_units(df, args=None, pixel_size_um=5.0)
        self.assertEqual(info["a_i_2D"]["input_unit"], "1/m")
        self.assertEqual(info["a_i_2D"]["plot_unit"], "1/m")
        self.assertEqual(info["a_i_2D"]["conversion"], "none")

        x = plot_rate_correlations.convert_metric_for_plot(
            df["a_i_2D"].to_numpy(), "a_i_2D", info, pixel_size_um=5.0
        )
        np.testing.assert_array_equal(x, np.array([4.5e4, 5.0e4]))
        # Definitely NOT inflated to ~1e10
        self.assertLess(float(np.max(x)), 1e6)

    def test_a_i_2D_in_per_pixel_converts_to_per_meter(self):
        """median(a_i_2D) <= 1e3 -> assume 1/px, convert by dividing by pixel_size_m."""
        df = pd.DataFrame({"a_i_2D": [0.5, 0.7], "InterfaceArea": [10.0, 20.0]})
        info = plot_rate_correlations.infer_metric_units(df, args=None, pixel_size_um=5.0)
        self.assertEqual(info["a_i_2D"]["input_unit"], "1/px")
        self.assertEqual(info["a_i_2D"]["plot_unit"], "1/m")
        self.assertEqual(info["a_i_2D"]["conversion"], "divide_by_pixel_size_m")
        x = plot_rate_correlations.convert_metric_for_plot(
            df["a_i_2D"].to_numpy(), "a_i_2D", info, pixel_size_um=5.0
        )
        # 0.5 / 5e-6 = 1e5
        np.testing.assert_allclose(x, np.array([1e5, 1.4e5]))

    def test_interface_area_px_length_converts_by_pixel_size_not_squared(self):
        """InterfaceArea is L_ow in pixels: convert to metres via *pixel_size_m, NOT squared."""
        df = pd.DataFrame({"a_i_2D": [4e4], "InterfaceArea": [1000.0]})
        info = plot_rate_correlations.infer_metric_units(df, args=None, pixel_size_um=5.0)
        self.assertEqual(info["InterfaceArea"]["input_unit"], "px_length")
        self.assertEqual(info["InterfaceArea"]["plot_unit"], "m")
        self.assertEqual(info["InterfaceArea"]["conversion"], "multiply_by_pixel_size_m")
        x = plot_rate_correlations.convert_metric_for_plot(
            df["InterfaceArea"].to_numpy(), "InterfaceArea", info, pixel_size_um=5.0
        )
        # 1000 px * (5 um -> 5e-6 m) = 0.005 m  (NOT 1000 * (5e-6)^2 = 2.5e-8)
        np.testing.assert_allclose(x, np.array([0.005]))
        self.assertGreater(float(x[0]), 1e-4)

    def test_interface_unit_override_to_area_squares_pixel_size(self):
        df = pd.DataFrame({"a_i_2D": [4e4], "InterfaceArea": [1000.0]})

        class _Args:
            ai2d_unit = "auto"
            interface_unit = "px_area"
            req_unit = "auto"

        info = plot_rate_correlations.infer_metric_units(df, args=_Args(), pixel_size_um=5.0)
        self.assertEqual(info["InterfaceArea"]["plot_unit"], r"m$^2$")
        x = plot_rate_correlations.convert_metric_for_plot(
            df["InterfaceArea"].to_numpy(), "InterfaceArea", info, pixel_size_um=5.0
        )
        np.testing.assert_allclose(x, np.array([1000.0 * (5e-6) ** 2]))

    def test_interface_unit_m_length_is_not_converted(self):
        args = SimpleNamespace(ai2d_unit="auto", interface_unit="m_length", req_unit="auto")
        df = pd.DataFrame({"a_i_2D": [4e4], "InterfaceArea": [0.012], "ReqMedian": [5.0]})
        info = plot_rate_correlations.infer_metric_units(df, args, pixel_size_um=4.17)
        self.assertEqual(info["InterfaceArea"]["input_unit"], "m_length")
        self.assertEqual(info["InterfaceArea"]["plot_unit"], "m")
        self.assertEqual(info["InterfaceArea"]["conversion"], "none")
        np.testing.assert_allclose(
            plot_rate_correlations.convert_metric_for_plot(df["InterfaceArea"], "InterfaceArea", info, 4.17),
            [0.012],
        )

    def test_interface_unit_px_length_converts_to_m(self):
        args = SimpleNamespace(ai2d_unit="auto", interface_unit="px_length", req_unit="auto")
        df = pd.DataFrame({"a_i_2D": [4e4], "InterfaceArea": [1000.0], "ReqMedian": [5.0]})
        info = plot_rate_correlations.infer_metric_units(df, args, pixel_size_um=4.17)
        self.assertEqual(info["InterfaceArea"]["conversion"], "multiply_by_pixel_size_m")
        np.testing.assert_allclose(
            plot_rate_correlations.convert_metric_for_plot(df["InterfaceArea"], "InterfaceArea", info, 4.17),
            [1000.0 * 4.17e-6],
        )

    def test_req_unit_um_is_not_converted(self):
        args = SimpleNamespace(ai2d_unit="auto", interface_unit="auto", req_unit="um")
        df = pd.DataFrame({"a_i_2D": [4e4], "InterfaceArea": [1000.0], "ReqMedian": [25.0]})
        info = plot_rate_correlations.infer_metric_units(df, args, pixel_size_um=4.17)
        self.assertEqual(info["ReqMedian"]["input_unit"], "um")
        self.assertEqual(info["ReqMedian"]["plot_unit"], "um")
        self.assertEqual(info["ReqMedian"]["conversion"], "none")
        np.testing.assert_allclose(
            plot_rate_correlations.convert_metric_for_plot(df["ReqMedian"], "ReqMedian", info, 4.17),
            [25.0],
        )

    def test_req_unit_auto_uses_micrometres_when_pixel_size_known(self):
        df = pd.DataFrame({"a_i_2D": [1.0], "InterfaceArea": [1.0], "ReqMedian": [10.0]})
        info = plot_rate_correlations.infer_metric_units(df, args=None, pixel_size_um=4.17)
        self.assertEqual(info["ReqMedian"]["plot_unit"], "um")
        self.assertEqual(info["ReqMedian"]["conversion"], "multiply_by_pixel_size_um")
        x = plot_rate_correlations.convert_metric_for_plot(
            df["ReqMedian"].to_numpy(), "ReqMedian", info, pixel_size_um=4.17
        )
        np.testing.assert_allclose(x, np.array([41.7]))

    def test_x_label_uses_unit_info_for_interface_area(self):
        df = pd.DataFrame({"a_i_2D": [4e4], "InterfaceArea": [1000.0]})
        info = plot_rate_correlations.infer_metric_units(df, args=None, pixel_size_um=5.0)
        spec = plot_rate_correlations.X_AXIS_SPECS[1]  # InterfaceArea
        label = plot_rate_correlations._x_label_for(spec, df, pixel_size_um=5.0, unit_info=info)
        self.assertIn("L_{ow}", label)
        self.assertIn("(m)", label)
        self.assertNotIn(r"m$^2$", label)


# --------------------------------------------------------------------------- #
# Plotting / driver tests
# --------------------------------------------------------------------------- #
class PlotDriverTests(unittest.TestCase):
    def _attach_pipeline(self, df, pixel_size_um=None):
        plot_rate_correlations.attach_stage_and_masks(df)
        unit_info = plot_rate_correlations.infer_metric_units(
            df, args=None, pixel_size_um=pixel_size_um
        )
        plot_rate_correlations.attach_all_rates(
            df, pixel_size_um=pixel_size_um, unit_info=unit_info
        )
        return unit_info

    def test_create_all_rate_figures_writes_default_plot_set(self):
        df = make_synthetic_df(n=40, with_mass=True)
        df.attrs["req_unit"] = "px"
        unit_info = self._attach_pipeline(df, pixel_size_um=None)
        with tempfile.TemporaryDirectory() as tmp:
            figures_dir = Path(tmp)
            written, _ = plot_rate_correlations.create_all_rate_figures(
                df,
                figures_dir=figures_dir,
                rate_method="time-lr",
                dpi=80,
                pixel_size_um=None,
                log_x_metrics=set(),
                unit_info=unit_info,
            )
            stems_png = sorted({path.stem for path in written if path.suffix == ".png"})
            self.assertEqual(len(stems_png), 24)
            self.assertEqual(len([p for p in written if p.suffix == ".png"]), 24)
            self.assertEqual(len([p for p in written if p.suffix == ".svg"]), 24)
            self.assertEqual(len([p for p in written if p.suffix == ".xlsx"]), 24)
            for path in written:
                self.assertTrue(path.exists())
                self.assertGreater(path.stat().st_size, 200, path)

    def test_create_all_rate_figures_supports_normalized_rate(self):
        df = make_synthetic_df(n=40, with_mass=True)
        df.attrs["req_unit"] = "px"
        unit_info = self._attach_pipeline(df, pixel_size_um=None)
        with tempfile.TemporaryDirectory() as tmp:
            figures_dir = Path(tmp)
            written, _ = plot_rate_correlations.create_all_rate_figures(
                df,
                figures_dir=figures_dir,
                rate_method="time-lr",
                dpi=80,
                pixel_size_um=None,
                log_x_metrics=set(),
                plot_set=("stage",),
                plot_normalized_rate=True,
                unit_info=unit_info,
            )
            stems_png = sorted({path.stem for path in written if path.suffix == ".png"})
            self.assertEqual(len(stems_png), 16)
            self.assertEqual(len([p for p in written if p.suffix == ".xlsx"]), 16)
            self.assertTrue(any("normalized_rate_time_lr_vs_" in s for s in stems_png))
            self.assertTrue(any(s.startswith("rate_time_lr_vs_") for s in stems_png))

    def test_topology_fraction_plots_emitted_separately(self):
        """Three independent fraction figures and no combined ganglia figure."""
        df = make_synthetic_df(n=40, with_mass=True)
        df.attrs["req_unit"] = "px"
        unit_info = self._attach_pipeline(df, pixel_size_um=None)
        with tempfile.TemporaryDirectory() as tmp:
            figures_dir = Path(tmp)
            written, _ = plot_rate_correlations.create_all_rate_figures(
                df,
                figures_dir=figures_dir,
                rate_method="time-lr",
                dpi=80,
                pixel_size_um=None,
                log_x_metrics=set(),
                plot_set=("stage",),
                unit_info=unit_info,
            )
            stems_png = {path.stem for path in written if path.suffix == ".png"}
            self.assertIn("rate_time_lr_vs_frac_droplets_stage_scatter", stems_png)
            self.assertIn("rate_time_lr_vs_frac_columns_stage_scatter", stems_png)
            self.assertIn("rate_time_lr_vs_frac_clusters_stage_scatter", stems_png)
            for stem in stems_png:
                self.assertNotIn("ganglia", stem.lower())
                self.assertNotIn("06_", stem)

    def test_fraction_kind_count_uses_count_fraction_columns(self):
        df = make_synthetic_df(n=40, with_mass=True)
        df["areaFracDropletsValid"] = np.linspace(0.1, 0.2, len(df))
        df["countFracDropletsValid"] = np.linspace(0.7, 0.8, len(df))
        df["areaFracColumnsValid"] = np.linspace(0.2, 0.3, len(df))
        df["countFracColumnsValid"] = np.linspace(0.2, 0.1, len(df))
        df["areaFracClustersValid"] = 1.0 - df["areaFracDropletsValid"] - df["areaFracColumnsValid"]
        df["countFracClustersValid"] = 1.0 - df["countFracDropletsValid"] - df["countFracColumnsValid"]
        unit_info = self._attach_pipeline(df, pixel_size_um=None)
        with tempfile.TemporaryDirectory() as tmp:
            figures_dir = Path(tmp)
            plot_rate_correlations.create_all_rate_figures(
                df,
                figures_dir=figures_dir,
                rate_method="time-lr",
                dpi=80,
                pixel_size_um=None,
                log_x_metrics=set(),
                plot_set=("stage",),
                fraction_kind="Count",
                unit_info=unit_info,
            )

            data = pd.read_excel(
                figures_dir / "rate_time_lr_vs_frac_droplets_stage_scatter_data.xlsx",
                sheet_name="data_all",
            )
            self.assertIn("countFracDropletsValid_raw", data.columns)
            self.assertNotIn("fracDroplets_raw", data.columns)
            self.assertAlmostEqual(data["countFracDropletsValid_raw"].iloc[0], 0.7)

    def test_binned_summary_defaults_to_active_removal_only(self):
        """rate_metric_binned_summary.csv should not contain non-active stages by default."""
        df = make_synthetic_df(n=80, with_mass=True)
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path = write_full_csv(output_dir, n=80)
            (output_dir / "analysis_report.txt").write_text(
                "Pixel Size: 4.17 μm/px\n", encoding="utf-8"
            )
            figures_dir = output_dir / "figures_rate"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = plot_rate_correlations.main(
                    [
                        str(output_dir),
                        "--csv",
                        str(csv_path),
                        "--figures-dir",
                        str(figures_dir),
                        "--dpi",
                        "80",
                        "--plot-set",
                        "binned",
                        "--n-bins",
                        "4",
                    ]
                )
            self.assertEqual(exit_code, 0)
            binned_csv = figures_dir / "rate_metric_binned_summary.csv"
            self.assertTrue(binned_csv.exists())
            binned = pd.read_csv(binned_csv)
            if not binned.empty:
                stages_present = set(binned["stage"].astype(str).unique())
                self.assertEqual(stages_present, {"active_removal"})
            self.assertEqual(len(list(figures_dir.glob("*_data.xlsx"))), 8)

        _ = df  # silence unused

    def test_unit_inference_json_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path = write_full_csv(output_dir, n=30)
            (output_dir / "analysis_report.txt").write_text(
                "Pixel Size: 4.17 μm/px\n", encoding="utf-8"
            )
            figures_dir = output_dir / "figures_rate"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = plot_rate_correlations.main(
                    [
                        str(output_dir),
                        "--csv",
                        str(csv_path),
                        "--figures-dir",
                        str(figures_dir),
                        "--dpi",
                        "80",
                        "--plot-set",
                        "stage",
                    ]
                )
            self.assertEqual(exit_code, 0)
            unit_json = figures_dir / "rate_plot_unit_inference.json"
            self.assertTrue(unit_json.exists())
            self.assertEqual(len(list(figures_dir.glob("*_data.xlsx"))), 8)
            payload = json.loads(unit_json.read_text(encoding="utf-8"))
            self.assertIn("a_i_2D", payload)
            self.assertIn("InterfaceArea", payload)
            self.assertIn("ReqMedian", payload)
            self.assertEqual(payload["InterfaceArea"]["plot_unit"], "m")
            self.assertEqual(payload["a_i_2D"]["plot_unit"], "1/m")
            self.assertEqual(payload["ReqMedian"]["plot_unit"], "um")

    def test_main_smoke_test_runs_and_writes_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path = write_full_csv(output_dir, n=40)
            (output_dir / "analysis_report.txt").write_text(
                "Pixel Size: 4.17 μm/px\n", encoding="utf-8"
            )
            figures_dir = output_dir / "figures_rate"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = plot_rate_correlations.main(
                    [
                        str(output_dir),
                        "--csv",
                        str(csv_path),
                        "--figures-dir",
                        str(figures_dir),
                        "--dpi",
                        "80",
                        "--rate-method",
                        "time-lr",
                    ]
                )
            self.assertEqual(exit_code, 0)
            output = stdout.getvalue()
            self.assertIn("Pixel size: 4.17", output)
            self.assertIn("Rate method: time-lr", output)
            rates_csv = figures_dir / "dissolution_rates.csv"
            self.assertTrue(rates_csv.exists())
            rates_df = pd.read_csv(rates_csv)
            for col in (
                "Sn_rate_input",
                "DissolutionRate_Sn_time_lr",
                "DissolutionRate_Sn_movmed",
                "DissolutionRate_Sn_lr",
                "Stage",
                "ValidStructure",
                "DissolutionRate_mass_kg_per_s",
            ):
                self.assertIn(col, rates_df.columns)
            png_files = sorted(figures_dir.glob("*.png"))
            self.assertEqual(len(png_files), 24)
            self.assertEqual(len(list(figures_dir.glob("*_data.xlsx"))), 24)
            self.assertTrue((figures_dir / "rate_plot_config.json").exists())
            self.assertTrue((figures_dir / "rate_plot_metric_availability.csv").exists())

    def test_main_accepts_rate_plan_required_columns_without_timeseries_plot_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path = write_minimal_rate_csv(output_dir, n=40)
            (output_dir / "analysis_report.txt").write_text(
                "Pixel Size: 4.17 μm/px\n", encoding="utf-8"
            )
            figures_dir = output_dir / "figures_rate_minimal"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = plot_rate_correlations.main(
                    [
                        str(output_dir),
                        "--csv",
                        str(csv_path),
                        "--figures-dir",
                        str(figures_dir),
                        "--dpi",
                        "80",
                    ]
            )
            self.assertEqual(exit_code, 0)
            self.assertIn("Rows: 40", stdout.getvalue())
            availability = pd.read_csv(figures_dir / "rate_plot_metric_availability.csv")
            self.assertIn("missing column", set(availability["reason_if_skipped"].astype(str)))
            self.assertLess(len(sorted(figures_dir.glob("*.png"))), 24)

    def test_pixel_size_propagates_to_metric_axis_labels(self):
        df = make_synthetic_df(n=15, with_mass=True)
        df.attrs["req_unit"] = "um"
        unit_info = self._attach_pipeline(df, pixel_size_um=4.17)
        # ReqMedian -> um
        label_for_req = plot_rate_correlations._x_label_for(
            plot_rate_correlations.X_AXIS_SPECS[4], df,
            pixel_size_um=4.17, unit_info=unit_info,
        )
        self.assertIn("um", label_for_req)
        # InterfaceArea -> projected length L_ow in metres (NOT m^2)
        label_for_iface = plot_rate_correlations._x_label_for(
            plot_rate_correlations.X_AXIS_SPECS[1], df,
            pixel_size_um=4.17, unit_info=unit_info,
        )
        self.assertIn("L_{ow}", label_for_iface)
        self.assertIn("(m)", label_for_iface)
        self.assertNotIn(r"m$^2$", label_for_iface)

    def test_png_paths_have_matching_workbook_paths(self):
        df = make_synthetic_df(n=35, with_mass=True)
        df.attrs["req_unit"] = "px"
        unit_info = self._attach_pipeline(df, pixel_size_um=None)
        with tempfile.TemporaryDirectory() as tmp:
            figures_dir = Path(tmp)
            plot_rate_correlations.create_all_rate_figures(
                df,
                figures_dir=figures_dir,
                rate_method="time-lr",
                dpi=72,
                pixel_size_um=None,
                log_x_metrics=set(),
                plot_set=("stage", "binned"),
                unit_info=unit_info,
                save_plot_data=True,
            )
            for png in sorted(figures_dir.glob("*.png")):
                xlsx = figures_dir / f"{png.stem}_data.xlsx"
                self.assertTrue(xlsx.is_file(), msg=str(xlsx))

    def test_stage_scatter_xlsx_has_data_all_and_plotted_sheets(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path = write_full_csv(output_dir, n=50)
            (output_dir / "analysis_report.txt").write_text(
                "Pixel Size: 4.17 μm/px\n", encoding="utf-8"
            )
            figures_dir = output_dir / "figures_rate"
            exit_code = plot_rate_correlations.main(
                [
                    str(output_dir),
                    "--csv",
                    str(csv_path),
                    "--figures-dir",
                    str(figures_dir),
                    "--dpi",
                    "72",
                    "--plot-set",
                    "stage",
                    "--no-save-stats-csv",
                ]
            )
            self.assertEqual(exit_code, 0)
            xlsx_path = figures_dir / "rate_time_lr_vs_a_i_2D_stage_scatter_data.xlsx"
            self.assertTrue(xlsx_path.exists())
            with pd.ExcelFile(xlsx_path) as xl_file:
                self.assertEqual(set(xl_file.sheet_names), {"data_all", "data_plotted"})
                d_all = pd.read_excel(xl_file, sheet_name="data_all")
                d_plot = pd.read_excel(xl_file, sheet_name="data_plotted")
            self.assertLessEqual(len(d_plot), len(d_all))
            self.assertIn("Stage", d_all.columns)
            self.assertIn("a_i_2D_plot", d_all.columns)

    def test_binned_xlsx_uses_active_removal_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path = write_full_csv(output_dir, n=70)
            (output_dir / "analysis_report.txt").write_text(
                "Pixel Size: 4.17 μm/px\n", encoding="utf-8"
            )
            figures_dir = output_dir / "figures_rate_bin"
            exit_code = plot_rate_correlations.main(
                [
                    str(output_dir),
                    "--csv",
                    str(csv_path),
                    "--figures-dir",
                    str(figures_dir),
                    "--dpi",
                    "72",
                    "--plot-set",
                    "binned",
                    "--n-bins",
                    "4",
                    "--no-save-stats-csv",
                ]
            )
            self.assertEqual(exit_code, 0)
            xlsx_path = figures_dir / "rate_time_lr_vs_a_i_2D_binned_active_data.xlsx"
            self.assertTrue(xlsx_path.exists())
            d = pd.read_excel(xlsx_path, sheet_name="data")
            if not d.empty:
                self.assertEqual(set(d["stage"].astype(str)), {"active_removal"})

    def test_trajectory_xlsx_plotted_capped_by_max_trajectory_points(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path = write_full_csv(output_dir, n=160)
            (output_dir / "analysis_report.txt").write_text(
                "Pixel Size: 4.17 μm/px\n", encoding="utf-8"
            )
            figures_dir = output_dir / "figures_rate_traj"
            exit_code = plot_rate_correlations.main(
                [
                    str(output_dir),
                    "--csv",
                    str(csv_path),
                    "--figures-dir",
                    str(figures_dir),
                    "--dpi",
                    "72",
                    "--plot-set",
                    "trajectory",
                    "--max-trajectory-points",
                    "42",
                    "--no-save-stats-csv",
                ]
            )
            self.assertEqual(exit_code, 0)
            d_plot = pd.read_excel(
                figures_dir / "rate_time_lr_vs_a_i_2D_trajectory_timecolored_data.xlsx",
                sheet_name="data_plotted",
            )
            self.assertLessEqual(len(d_plot), 42)

    def test_no_save_plot_data_skips_workbooks(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path = write_full_csv(output_dir, n=30)
            (output_dir / "analysis_report.txt").write_text(
                "Pixel Size: 4.17 μm/px\n", encoding="utf-8"
            )
            figures_dir = output_dir / "figures_rate_noplotdata"
            exit_code = plot_rate_correlations.main(
                [
                    str(output_dir),
                    "--csv",
                    str(csv_path),
                    "--figures-dir",
                    str(figures_dir),
                    "--dpi",
                    "72",
                    "--plot-set",
                    "stage",
                    "--no-save-plot-data",
                    "--no-save-stats-csv",
                ]
            )
            self.assertEqual(exit_code, 0)
            self.assertEqual(len(list(figures_dir.glob("*_data.xlsx"))), 0)

    def test_create_all_rate_figures_save_plot_data_false(self):
        df = make_synthetic_df(n=30, with_mass=True)
        unit_info = self._attach_pipeline(df, pixel_size_um=None)
        with tempfile.TemporaryDirectory() as tmp:
            figures_dir = Path(tmp)
            plot_rate_correlations.create_all_rate_figures(
                df,
                figures_dir=figures_dir,
                rate_method="time-lr",
                dpi=72,
                pixel_size_um=None,
                log_x_metrics=set(),
                plot_set=("stage",),
                unit_info=unit_info,
                save_plot_data=False,
            )
            self.assertEqual(len(list(figures_dir.glob("*_data.xlsx"))), 0)

    def test_missing_optional_metric_column_skips_plot_instead_of_raising(self):
        df = pd.DataFrame({
            "RealTime_s": [0.0, 60.0, 120.0, 180.0],
            "Sn": [1.0, 0.9, 0.8, 0.7],
            "a_i_2D": [4e4, 4.1e4, 4.2e4, 4.3e4],
        })
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "timeseries_realtime_test.csv"
            df.to_csv(csv_path, index=False)
            loaded = plot_rate_correlations.load_rate_timeseries(csv_path)
            self.assertIn("a_i_2D", loaded.columns)

    def test_metric_availability_csv_records_skipped_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path = write_minimal_rate_csv(output_dir, n=40)
            figures_dir = output_dir / "figures_rate"
            exit_code = plot_rate_correlations.main(
                [
                    str(output_dir),
                    "--csv",
                    str(csv_path),
                    "--figures-dir",
                    str(figures_dir),
                    "--dpi",
                    "72",
                    "--plot-set",
                    "stage",
                    "--no-save-plot-data",
                    "--no-save-stats-csv",
                ]
            )
            self.assertEqual(exit_code, 0)
            availability = pd.read_csv(figures_dir / "rate_plot_metric_availability.csv")
            row = availability.loc[availability["metric"] == "InterfaceArea"].iloc[0]
            self.assertFalse(bool(row["available"]))
            self.assertEqual(row["reason_if_skipped"], "missing column")

    def test_valid_structure_false_rows_do_not_enter_binned_or_associations(self):
        df = make_synthetic_df(n=40, with_mass=True)
        unit_info = self._attach_pipeline(df, pixel_size_um=4.17)
        df.loc[10:15, "ValidStructure"] = False
        rows = plot_rate_correlations.compute_binned_summary_rows(
            df, "a_i_2D", "DissolutionRate_Sn_time_lr", unit_info, 4.17,
            stages=("active_removal",), n_bins=4, log_x=False, min_bin_count=1,
        )
        assoc = plot_rate_correlations.compute_associations(
            df, ["a_i_2D"], "DissolutionRate_Sn_time_lr", unit_info, 4.17
        )
        self.assertTrue(all(r["n"] >= 1 for r in rows))
        self.assertTrue(all(r["n_valid"] <= r["n_total"] for r in assoc))
        self.assertTrue(any(r["n_excluded"] > 0 for r in assoc))

    def test_log_x_auto_ignores_near_depleted_ai2d_spike(self):
        df = make_synthetic_df(n=30, with_mass=True)
        df["a_i_2D"] = 40000.0
        df.loc[df.index[-1], "a_i_2D"] = 2e6
        df["ValidStructure"] = True
        df.loc[df.index[-1], "ValidStructure"] = False
        x = df["a_i_2D"].to_numpy()
        self.assertFalse(
            plot_rate_correlations._should_log_metric(
                "a_i_2D", "auto", x, valid_mask=df["ValidStructure"]
            )
        )

    def test_fraction_metrics_force_linear_log_auto(self):
        x = np.geomspace(1e-4, 1, 100)
        self.assertFalse(plot_rate_correlations._should_log_metric("fracDroplets", "auto", x))
        self.assertFalse(plot_rate_correlations._should_log_metric("MaxBlobFrac", "auto", x))

    def test_fraction_kind_default_area_without_reading_blob_detail(self):
        parser = plot_rate_correlations.build_arg_parser()
        args = parser.parse_args(["dummy_output"])
        self.assertEqual(args.fraction_kind, "area")

    def test_no_save_rates_csv_suppresses_default_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path = write_full_csv(output_dir, n=40)
            figures_dir = output_dir / "figures_rate"
            exit_code = plot_rate_correlations.main(
                [
                    str(output_dir),
                    "--csv",
                    str(csv_path),
                    "--figures-dir",
                    str(figures_dir),
                    "--dpi",
                    "72",
                    "--plot-set",
                    "stage",
                    "--no-save-rates-csv",
                    "--no-save-stats-csv",
                    "--no-save-plot-data",
                ]
            )
            self.assertEqual(exit_code, 0)
            self.assertFalse((figures_dir / "dissolution_rates.csv").exists())

    def test_binned_summary_skips_bins_below_min_bin_count(self):
        df = make_synthetic_df(n=40, with_mass=True)
        unit_info = self._attach_pipeline(df, pixel_size_um=4.17)
        rows = plot_rate_correlations.compute_binned_summary_rows(
            df, "a_i_2D", "DissolutionRate_Sn_time_lr", unit_info, 4.17,
            stages=("active_removal",), n_bins=8, log_x=False, min_bin_count=20,
        )
        self.assertTrue(all(r["n"] >= 20 for r in rows))


# --------------------------------------------------------------------------- #
# Statistics CSVs
# --------------------------------------------------------------------------- #
class StatsCsvTests(unittest.TestCase):
    def test_associations_and_binned_csv_emitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path = write_full_csv(output_dir, n=80)
            (output_dir / "analysis_report.txt").write_text(
                "Pixel Size: 4.17 μm/px\n", encoding="utf-8"
            )
            figures_dir = output_dir / "figures_rate"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = plot_rate_correlations.main(
                    [
                        str(output_dir),
                        "--csv",
                        str(csv_path),
                        "--figures-dir",
                        str(figures_dir),
                        "--dpi",
                        "80",
                        "--plot-set",
                        "stage",
                    ]
                )
            self.assertEqual(exit_code, 0)
            assoc_csv = figures_dir / "rate_metric_associations.csv"
            binned_csv = figures_dir / "rate_metric_binned_summary.csv"
            self.assertTrue(assoc_csv.exists())
            self.assertTrue(binned_csv.exists())
            assoc = pd.read_csv(assoc_csv)
            for col in ("metric", "stage", "n", "spearman_rho", "pearson_r",
                         "used_for_interpretation"):
                self.assertIn(col, assoc.columns)
            self.assertEqual(len(list(figures_dir.glob("*_data.xlsx"))), 8)


if __name__ == "__main__":
    unittest.main(verbosity=2)
