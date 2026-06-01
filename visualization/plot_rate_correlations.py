"""Plot dissolution rate (-dSn/dt) vs microstructural metrics.

Stage-aware "rate-structure phase plots":

* Each metric (a_i_2D, projected interfacial length L_ow, MaxBlobFrac,
  NumBlobs, ReqMedian, and the three topology-fraction series fracDroplets /
  fracColumns / fracClusters) is rendered up to three ways: a stage-colored
  scatter, a binned median +/- IQR summary over the active-removal regime,
  and a time-colored trajectory.
* Units for ``a_i_2D`` are auto-inferred (median > 1e3 -> already 1/m, no
  reconversion). ``InterfaceArea`` is treated as projected interfacial length
  L_ow (multiply by pixel_size_m, *not* squared). ``ReqMedian`` is reported
  in micrometres when pixel size is known. Decisions are recorded in
  ``rate_plot_unit_inference.json``.
* Dissolution rate is computed by default with a *time-window* local linear
  regression on a monotone-smoothed Sn signal so that segmentation jitter
  cannot inflate the rate. The legacy frame-window methods (``lr`` and
  ``movmedian``) remain available as QC alternatives.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize


# --------------------------------------------------------------------------- #
# Sibling module loader (reuse plot_timeseries helpers without packaging)
# --------------------------------------------------------------------------- #
def _load_plot_timeseries():
    if "plot_timeseries" in sys.modules:
        return sys.modules["plot_timeseries"]
    module_path = Path(__file__).resolve().with_name("plot_timeseries.py")
    spec = importlib.util.spec_from_file_location("plot_timeseries", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot locate plot_timeseries.py at {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["plot_timeseries"] = module
    spec.loader.exec_module(module)
    return module


_pt = _load_plot_timeseries()
find_timeseries_csv = _pt.find_timeseries_csv
filter_min_time = _pt.filter_min_time
find_pixel_size_um = _pt.find_pixel_size_um
find_blob_detail_csv = _pt.find_blob_detail_csv
configure_nature_style = _pt.configure_nature_style
style_axes = _pt.style_axes
WONG_COLORS = _pt.WONG_COLORS
MM_PER_INCH = _pt.MM_PER_INCH
INDIVIDUAL_SIZE = _pt.INDIVIDUAL_SIZE
_save_figure = _pt._save_figure


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
CORE_REQUIRED_COLUMNS = (
    "RealTime_s",
    "Sn",
)
OPTIONAL_METRIC_COLUMNS = (
    "NumBlobs",
    "InterfaceArea",
    "MaxBlobFrac",
    "ReqMedian",
    "a_i_2D",
    "a_i_2D_flow",
    "fracDroplets",
    "fracColumns",
    "fracClusters",
    "areaFracDroplets",
    "areaFracColumns",
    "areaFracClusters",
    "areaFracDropletsValid",
    "areaFracColumnsValid",
    "areaFracClustersValid",
    "countFracDroplets",
    "countFracColumns",
    "countFracClusters",
    "countFracDropletsValid",
    "countFracColumnsValid",
    "countFracClustersValid",
    "MassDissolvedKg",
    "FrameIndex",
)
REQUIRED_COLUMNS = CORE_REQUIRED_COLUMNS

DEFAULT_LOG_X_METRICS = ("a_i_2D", "a_i_2D_flow", "InterfaceArea", "NumBlobs")
FORCE_LINEAR_METRICS = {
    "MaxBlobFrac",
    "fracDroplets",
    "fracColumns",
    "fracClusters",
    "areaFracDroplets",
    "areaFracColumns",
    "areaFracClusters",
    "areaFracDropletsValid",
    "areaFracColumnsValid",
    "areaFracClustersValid",
    "countFracDroplets",
    "countFracColumns",
    "countFracClusters",
    "countFracDropletsValid",
    "countFracColumnsValid",
    "countFracClustersValid",
}
LOG_X_ALLOWED_METRICS = frozenset(
    {
        "a_i_2D",
        "a_i_2D_flow",
        "InterfaceArea",
        "MaxBlobFrac",
        "NumBlobs",
        "ReqMedian",
        "fracDroplets",
        "fracColumns",
        "fracClusters",
        "areaFracDroplets",
        "areaFracColumns",
        "areaFracClusters",
        "areaFracDropletsValid",
        "areaFracColumnsValid",
        "areaFracClustersValid",
        "countFracDroplets",
        "countFracColumns",
        "countFracClusters",
        "countFracDropletsValid",
        "countFracColumnsValid",
        "countFracClustersValid",
    }
)

STAGE_LABELS = ["near_depleted", "tail", "active_removal", "induction_or_stable"]
STAGE_COLORS = {
    "induction_or_stable": "#7F7F7F",
    "active_removal": WONG_COLORS["blue"],
    "tail": WONG_COLORS["orange"],
    "near_depleted": "#C8C8C8",
}
# Drawing order: paint context first, foreground last.
STAGE_DRAW_ORDER = ["near_depleted", "induction_or_stable", "tail", "active_removal"]

DEFAULT_DT_SECONDS = 270.0
DEFAULT_RATE_WINDOW_MIN = 20.0
DEFAULT_RATE_MIN_POINTS = 25
DEFAULT_SN_SMOOTH_WINDOW_FRAMES = 51

BINNED_SUMMARY_COLUMNS = [
    "metric",
    "stage",
    "bin_id",
    "x_bin_min",
    "x_bin_max",
    "x_bin_p25",
    "x_bin_median",
    "x_bin_p75",
    "x_bin_iqr",
    "rate_p25",
    "rate_median",
    "rate_p75",
    "rate_iqr",
    "x_plot",
    "y_plot",
    "yerr_lower",
    "yerr_upper",
    "errorbar_definition",
    "n",
]

RATE_METHOD_TO_COLUMN = {
    "time-lr": "DissolutionRate_Sn_time_lr",
    "lr": "DissolutionRate_Sn_lr",
    "movmedian": "DissolutionRate_Sn_movmed",
}
RATE_METHOD_TO_NORM_COLUMN = {
    "time-lr": "NormalizedDissolutionRate_Sn_time_lr",
    "lr": "NormalizedDissolutionRate_Sn_lr",
    "movmedian": "NormalizedDissolutionRate_Sn_movmed",
}


X_AXIS_SPECS = [
    {
        "key": "a_i_2D",
        "stem": "a_i_2D",
        "label_template": r"Specific interfacial length density $a_i^{{2D}}$ ({unit})",
    },
    {
        "key": "a_i_2D_flow",
        "stem": "a_i_2D_flow",
        "label_template": r"Flow-normalized interfacial density $L_{{ow}}/A_{{flow}}$ ({unit})",
    },
    {
        "key": "InterfaceArea",
        "stem": "projected_interface_length",
        "label_template": r"Projected interfacial length $L_{{ow}}$ ({unit})",
    },
    {
        "key": "MaxBlobFrac",
        "stem": "max_blob_fraction",
        "label_template": "Largest blob fraction (-)",
    },
    {
        "key": "NumBlobs",
        "stem": "num_blobs",
        "label_template": "Number of blobs",
    },
    {
        "key": "ReqMedian",
        "stem": "req_median",
        "label_template": "Median equivalent radius ({unit})",
    },
]

FRACTION_SPECS = [
    {
        "key": "fracDroplets",
        "stem": "frac_droplets",
        "label_template": "{kind} fraction droplets (-)",
        "label": "Droplets",
    },
    {
        "key": "fracColumns",
        "stem": "frac_columns",
        "label_template": "{kind} fraction columns (-)",
        "label": "Columns",
    },
    {
        "key": "fracClusters",
        "stem": "frac_clusters",
        "label_template": "{kind} fraction clusters (-)",
        "label": "Clusters",
    },
]


COUNT_FRACTION_SPECS = [
    {
        "key": "countFracDroplets",
        "stem": "count_frac_droplets",
        "label_template": "{kind} fraction droplets (-)",
        "label": "Droplets",
    },
    {
        "key": "countFracColumns",
        "stem": "count_frac_columns",
        "label_template": "{kind} fraction columns (-)",
        "label": "Columns",
    },
    {
        "key": "countFracClusters",
        "stem": "count_frac_clusters",
        "label_template": "{kind} fraction clusters (-)",
        "label": "Clusters",
    },
]


def _first_existing_metric(df, candidates):
    columns = set(df.columns)
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def _resolved_fraction_specs(df, fraction_kind=None):
    kind = str(fraction_kind or "Area").lower()
    resolved = []
    for spec in FRACTION_SPECS:
        label = spec["label"]
        if kind == "count":
            candidates = [f"countFrac{label}Valid", f"countFrac{label}", spec["key"]]
        else:
            candidates = [f"areaFrac{label}Valid", f"areaFrac{label}", spec["key"]]
        selected = _first_existing_metric(df, candidates)
        if selected is None:
            selected = spec["key"]
        item = dict(spec)
        item["key"] = selected
        item["fraction_kind"] = "Count" if kind == "count" else "Area"
        resolved.append(item)
    return resolved


def _resolved_count_fraction_specs(df):
    """Return supplemental count-fraction specs when count columns are available."""
    resolved = []
    for spec in COUNT_FRACTION_SPECS:
        label = spec["label"]
        selected = _first_existing_metric(df, [f"countFrac{label}Valid", f"countFrac{label}"])
        if selected is None:
            continue
        item = dict(spec)
        item["key"] = selected
        item["fraction_kind"] = "Count"
        resolved.append(item)
    return resolved


def _rate_metric_specs(df, fraction_kind=None, include_count_fractions=True):
    """Resolve all rate-correlation X metrics for the current DataFrame."""
    specs = list(X_AXIS_SPECS) + _resolved_fraction_specs(df, fraction_kind)
    if include_count_fractions:
        existing_keys = {spec["key"] for spec in specs}
        specs.extend(
            spec for spec in _resolved_count_fraction_specs(df)
            if spec["key"] not in existing_keys
        )
    return specs


# --------------------------------------------------------------------------- #
# IO and validation
# --------------------------------------------------------------------------- #
def validate_required_columns(df):
    missing = [c for c in CORE_REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(missing)}")


def load_rate_timeseries(csv_path):
    """Load and time-correct a CSV using only the columns needed by this script."""
    csv_path = Path(csv_path)
    df = pd.read_csv(csv_path)
    if "RealTime_s" not in df.columns and "Time" in df.columns:
        # Older pipeline exports use Time as elapsed seconds. Normalize that
        # schema here so rate windows are interpreted in real minutes.
        df["RealTime_s"] = pd.to_numeric(df["Time"], errors="coerce")
    validate_required_columns(df)

    df = df.copy()
    if "FrameIndex" not in df.columns:
        df["FrameIndex"] = np.arange(1, len(df) + 1, dtype=int)
    numeric_columns = [c for c in CORE_REQUIRED_COLUMNS + OPTIONAL_METRIC_COLUMNS if c in df.columns]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    invalid = [column for column in CORE_REQUIRED_COLUMNS if df[column].isna().any()]
    if invalid:
        raise ValueError(f"Non-numeric or missing values in column(s): {', '.join(invalid)}")

    nonfinite = [column for column in CORE_REQUIRED_COLUMNS if not np.isfinite(df[column]).all()]
    if nonfinite:
        raise ValueError(f"Required numeric column(s) must be finite: {', '.join(nonfinite)}")

    if len(df) < 2 or df["RealTime_s"].count() < 2:
        raise ValueError("Time-series CSV must contain at least two finite time points")

    df = df.sort_values("RealTime_s", kind="mergesort").reset_index(drop=True)
    if df["RealTime_s"].duplicated().any():
        duplicates = df.loc[df["RealTime_s"].duplicated(), "RealTime_s"].tolist()
        raise ValueError(f"Duplicate RealTime_s values are not allowed: {duplicates}")

    if "FrameIndex" in df.columns:
        df["FrameIndex"] = pd.to_numeric(df["FrameIndex"], errors="coerce")
        if df["FrameIndex"].isna().any():
            raise ValueError("Non-numeric or missing values in column(s): FrameIndex")
    else:
        df["FrameIndex"] = np.arange(1, len(df) + 1)

    df["Time_min"] = df["RealTime_s"] / 60.0
    if "a_i_2D" in df.columns and "Sn" in df.columns:
        df["a_i_2D_flow"] = pd.to_numeric(df["a_i_2D"], errors="coerce") * pd.to_numeric(
            df["Sn"], errors="coerce"
        )
    return df


# --------------------------------------------------------------------------- #
# Stage masking
# --------------------------------------------------------------------------- #
def assign_stage(sn_norm, min_sn_norm_valid=0.05, active_min=0.10, induction_min=0.95):
    """Assign dissolution-stage labels using a dynamic near-depleted threshold."""
    sn_norm = np.asarray(sn_norm, dtype=float)
    stage = np.full(len(sn_norm), "unknown", dtype=object)
    finite = np.isfinite(sn_norm)
    min_valid = float(min_sn_norm_valid)
    active_min = float(active_min)
    induction_min = float(induction_min)

    stage[finite & (sn_norm < min_valid)] = "near_depleted"
    if min_valid < active_min:
        tail = finite & (sn_norm >= min_valid) & (sn_norm < active_min)
        stage[tail] = "tail"
    active = finite & (sn_norm >= active_min) & (sn_norm < induction_min)
    stage[active] = "active_removal"
    stage[finite & (sn_norm >= induction_min)] = "induction_or_stable"
    return stage


def valid_interpretation_mask(df):
    """Rows eligible for architecture/rate-correlation interpretation."""
    if "ValidStructure" not in df.columns:
        return np.ones(len(df), dtype=bool)
    return df["ValidStructure"].fillna(False).astype(bool).to_numpy()


def attach_stage_and_masks(df, min_sn_norm_valid=0.05, min_blobs_valid=20):
    """Attach SnNorm/NearDepleted/ValidStructure/Stage columns in-place.

    ``Stage`` follows the censoring scheme from the rate-correlation plan:

    * ``induction_or_stable``: SnNorm >= 0.95
    * ``active_removal``: 0.10 <= SnNorm < 0.95
    * ``tail``: 0.05 <= SnNorm < 0.10
    * ``near_depleted``: SnNorm < 0.05

    ``ValidStructure`` is True only outside near-depleted *and* with enough
    blobs and a positive interface length.
    """
    sn = pd.to_numeric(df["Sn"], errors="coerce").to_numpy(dtype=float)
    sn0 = next((v for v in sn if np.isfinite(v) and v > 0), float("nan"))
    df["Sn0"] = sn0
    with np.errstate(divide="ignore", invalid="ignore"):
        sn_norm = sn / sn0 if np.isfinite(sn0) and sn0 > 0 else np.full_like(sn, np.nan)
    df["SnNorm"] = sn_norm

    near_depleted = sn_norm < float(min_sn_norm_valid)
    df["NearDepleted"] = near_depleted

    if "NumBlobs" in df.columns:
        num_blobs = pd.to_numeric(df["NumBlobs"], errors="coerce").to_numpy(dtype=float)
        blob_ok = num_blobs >= int(min_blobs_valid)
    else:
        blob_ok = np.ones(len(df), dtype=bool)

    if "InterfaceArea" in df.columns:
        interface = pd.to_numeric(df["InterfaceArea"], errors="coerce").to_numpy(dtype=float)
        interface_ok = interface > 0
    else:
        interface_ok = np.ones(len(df), dtype=bool)

    df["ValidStructure"] = (
        np.isfinite(sn_norm)
        & (sn_norm >= float(min_sn_norm_valid))
        & blob_ok
        & interface_ok
    )

    df["Stage"] = assign_stage(sn_norm, min_sn_norm_valid=min_sn_norm_valid)
    return df


# --------------------------------------------------------------------------- #
# Unit inference
# --------------------------------------------------------------------------- #
def infer_metric_units(df, args, pixel_size_um):
    """Decide per-metric input/plot units and the conversion factor to apply.

    Returns a dict keyed by metric name with sub-dict
    ``{"input_unit", "plot_unit", "conversion", "median"}``.
    """
    pixel_size_m = float(pixel_size_um) * 1e-6 if pixel_size_um else None
    info = {}

    # ---- a_i_2D ---------------------------------------------------------- #
    ai2d_choice = getattr(args, "ai2d_unit", "auto") if args is not None else "auto"
    a_i_2D_values = pd.to_numeric(df.get("a_i_2D"), errors="coerce") if "a_i_2D" in df.columns else pd.Series(dtype=float)
    median_a = float(np.nanmedian(a_i_2D_values)) if a_i_2D_values.notna().any() else float("nan")

    def _ai_density_info(median_value):
        if ai2d_choice == "1/m":
            return {
                "input_unit": "1/m",
                "plot_unit": "1/m",
                "conversion": "none",
                "median": median_value,
            }
        if ai2d_choice == "1/px":
            if pixel_size_m:
                return {
                    "input_unit": "1/px",
                    "plot_unit": "1/m",
                    "conversion": "divide_by_pixel_size_m",
                    "median": median_value,
                }
            return {
                "input_unit": "1/px",
                "plot_unit": "1/px",
                "conversion": "none",
                "median": median_value,
            }
        if np.isfinite(median_value) and median_value > 1e3:
            return {
                "input_unit": "1/m",
                "plot_unit": "1/m",
                "conversion": "none",
                "median": median_value,
            }
        if pixel_size_m:
            return {
                "input_unit": "1/px",
                "plot_unit": "1/m",
                "conversion": "divide_by_pixel_size_m",
                "median": median_value,
            }
        return {
            "input_unit": "1/px",
            "plot_unit": "1/px",
            "conversion": "none",
            "median": median_value,
        }

    info["a_i_2D"] = _ai_density_info(median_a)

    if "a_i_2D_flow" in df.columns:
        flow_values = pd.to_numeric(df.get("a_i_2D_flow"), errors="coerce")
        median_flow = float(np.nanmedian(flow_values)) if flow_values.notna().any() else float("nan")
        if a_i_2D_values.notna().any():
            flow_info = dict(info["a_i_2D"])
            flow_info["median"] = median_flow
        else:
            flow_info = _ai_density_info(median_flow)
        info["a_i_2D_flow"] = flow_info

    # ---- InterfaceArea (treated as projected length L_ow) --------------- #
    iface_choice = getattr(args, "interface_unit", "auto") if args is not None else "auto"
    iface_values = (
        pd.to_numeric(df.get("InterfaceArea"), errors="coerce")
        if "InterfaceArea" in df.columns
        else pd.Series(dtype=float)
    )
    median_i = float(np.nanmedian(iface_values)) if iface_values.notna().any() else float("nan")

    if iface_choice == "px_length":
        info["InterfaceArea"] = {
            "input_unit": "px_length",
            "plot_unit": "m" if pixel_size_m else "px",
            "conversion": "multiply_by_pixel_size_m" if pixel_size_m else "none",
            "median": median_i,
        }
    elif iface_choice == "m_length":
        info["InterfaceArea"] = {
            "input_unit": "m_length",
            "plot_unit": "m",
            "conversion": "none",
            "median": median_i,
        }
    elif iface_choice == "px_area":
        info["InterfaceArea"] = {
            "input_unit": "px_area",
            "plot_unit": r"m$^2$" if pixel_size_m else r"px$^2$",
            "conversion": "multiply_by_pixel_size_m_squared" if pixel_size_m else "none",
            "median": median_i,
        }
    elif iface_choice == "m_area":
        info["InterfaceArea"] = {
            "input_unit": "m_area",
            "plot_unit": r"m$^2$",
            "conversion": "none",
            "median": median_i,
        }
    else:  # auto -> projected length
        if pixel_size_m:
            info["InterfaceArea"] = {
                "input_unit": "px_length",
                "plot_unit": "m",
                "conversion": "multiply_by_pixel_size_m",
                "median": median_i,
            }
        else:
            info["InterfaceArea"] = {
                "input_unit": "px_length",
                "plot_unit": "px",
                "conversion": "none",
                "median": median_i,
            }

    # ---- ReqMedian ------------------------------------------------------- #
    req_choice = getattr(args, "req_unit", "auto") if args is not None else "auto"
    if req_choice == "px":
        info["ReqMedian"] = {"input_unit": "px", "plot_unit": "px", "conversion": "none"}
    elif req_choice == "um":
        if pixel_size_um:
            info["ReqMedian"] = {
                "input_unit": "px",
                "plot_unit": "μm",
                "conversion": "multiply_by_pixel_size_um",
            }
        else:
            info["ReqMedian"] = {"input_unit": "px", "plot_unit": "px", "conversion": "none"}
    else:  # auto
        if pixel_size_um:
            info["ReqMedian"] = {
                "input_unit": "px",
                "plot_unit": "μm",
                "conversion": "multiply_by_pixel_size_um",
            }
        else:
            info["ReqMedian"] = {"input_unit": "px", "plot_unit": "px", "conversion": "none"}

    # ``--req-unit`` describes the input CSV unit. Override the legacy branch
    # above so explicit micrometre input is never converted a second time.
    if req_choice == "px":
        info["ReqMedian"] = {
            "input_unit": "px",
            "plot_unit": "um" if pixel_size_um else "px",
            "conversion": "multiply_by_pixel_size_um" if pixel_size_um else "none",
        }
    elif req_choice == "um":
        info["ReqMedian"] = {"input_unit": "um", "plot_unit": "um", "conversion": "none"}
    elif pixel_size_um:
        info["ReqMedian"] = {
            "input_unit": "px",
            "plot_unit": "um",
            "conversion": "multiply_by_pixel_size_um",
        }
    else:
        info["ReqMedian"] = {"input_unit": "px", "plot_unit": "px", "conversion": "none"}

    return info


def convert_metric_for_plot(values, metric_key, unit_info, pixel_size_um):
    """Apply the conversion encoded in ``unit_info`` (no-op when unknown)."""
    arr = np.asarray(values, dtype=float)
    info = (unit_info or {}).get(metric_key)
    if info is None:
        return arr
    conv = info.get("conversion", "none")
    if conv == "none":
        return arr
    if pixel_size_um is None:
        return arr
    pixel_size_m = float(pixel_size_um) * 1e-6
    if conv == "divide_by_pixel_size_m":
        return arr / pixel_size_m
    if conv == "multiply_by_pixel_size_m":
        return arr * pixel_size_m
    if conv == "multiply_by_pixel_size_m_squared":
        return arr * (pixel_size_m ** 2)
    if conv == "multiply_by_pixel_size_um":
        return arr * float(pixel_size_um)
    return arr


# --------------------------------------------------------------------------- #
# Robust derivative computation
# --------------------------------------------------------------------------- #
def _moving_median(values, window):
    """Centered rolling median with edge-aware fallback (no SciPy dependency)."""
    series = pd.Series(np.asarray(values, dtype=float))
    window = max(1, int(window))
    if window <= 1 or len(series) == 0:
        return series.to_numpy()
    smoothed = series.rolling(window=window, center=True, min_periods=1).median()
    return smoothed.to_numpy()


def prepare_sn_rate_input(df, sn_smooth_window_frames=DEFAULT_SN_SMOOTH_WINDOW_FRAMES,
                          monotone=True):
    """Add ``Sn_rate_input`` column: rolling-median smoothed Sn, optionally
    forced monotonically non-increasing (cumulative minimum).

    The original ``Sn`` column is never overwritten."""
    sn = pd.to_numeric(df["Sn"], errors="coerce").to_numpy(dtype=float)
    sn_med = _moving_median(sn, sn_smooth_window_frames)
    if monotone:
        # Replace NaNs with +inf so cummin propagates last finite value safely.
        finite = np.where(np.isfinite(sn_med), sn_med, np.inf)
        cummin = np.minimum.accumulate(finite)
        cummin = np.where(np.isfinite(cummin), cummin, np.nan)
        sn_rate_input = cummin
    else:
        sn_rate_input = sn_med
    df["Sn_rate_input"] = sn_rate_input
    return df


def compute_dissolution_rate_movmedian(df, smooth_window=5, dt_seconds=DEFAULT_DT_SECONDS):
    """Median-smooth Sn (frame-based) then centered finite difference over a
    fixed time span ``dt_seconds`` (default 270 s).
    """
    time_min = pd.to_numeric(df["Time_min"], errors="coerce").to_numpy(dtype=float)
    saturation = pd.to_numeric(df["Sn"], errors="coerce").to_numpy(dtype=float)
    if len(saturation) < 2:
        raise ValueError("Need at least two rows to compute a derivative.")
    if dt_seconds is None or dt_seconds <= 0:
        raise ValueError("dt_seconds must be positive.")

    smoothed = _moving_median(saturation, smooth_window)
    half_min = float(dt_seconds) / 60.0 / 2.0

    t_lo = np.maximum(time_min - half_min, time_min[0])
    t_hi = np.minimum(time_min + half_min, time_min[-1])
    span_min = t_hi - t_lo

    y_lo = np.interp(t_lo, time_min, smoothed)
    y_hi = np.interp(t_hi, time_min, smoothed)

    with np.errstate(divide="ignore", invalid="ignore"):
        rate = np.where(span_min > 1e-12, -(y_hi - y_lo) / span_min, np.nan)

    finite_mask = np.isfinite(rate)
    if (~finite_mask).any() and finite_mask.any():
        idx = np.arange(len(rate))
        rate = np.interp(idx, idx[finite_mask], rate[finite_mask])
    return pd.Series(rate, index=df.index, name="DissolutionRate_Sn_movmed")


def compute_dissolution_rate_lr(df, dt_seconds=DEFAULT_DT_SECONDS):
    """Rolling local linear regression on raw Sn over a fixed time span
    ``dt_seconds`` (default 270 s); ``-slope`` is the rate.

    Vectorised with cumulative sums of ``(t, Sn, t^2, t*Sn)`` so the cost is
    O(N log N) regardless of how dense the local sampling becomes.
    """
    time_min = pd.to_numeric(df["Time_min"], errors="coerce").to_numpy(dtype=float)
    saturation = pd.to_numeric(df["Sn"], errors="coerce").to_numpy(dtype=float)
    n = len(saturation)
    if n < 2:
        raise ValueError("Need at least two rows to compute a derivative.")
    if dt_seconds is None or dt_seconds <= 0:
        raise ValueError("dt_seconds must be positive.")

    half_min = float(dt_seconds) / 60.0 / 2.0
    return _time_window_slope(time_min, saturation, half_min, min_points=2,
                                name="DissolutionRate_Sn_lr",
                                index=df.index)


def compute_dissolution_rate_time_lr(df, time_col="Time_min",
                                       sn_col="Sn_rate_input",
                                       window_min=DEFAULT_RATE_WINDOW_MIN,
                                       min_points=DEFAULT_RATE_MIN_POINTS):
    """Time-window local linear regression of Sn(Time_min).

    For each row we collect rows whose ``|t - t_i| <= window_min/2`` and fit
    OLS slope by accumulated sums; ``-slope`` per minute is the rate. If a
    window contains fewer than ``min_points`` rows it is widened symmetrically
    to the nearest ``min_points`` neighbours.
    """
    if time_col not in df.columns:
        raise KeyError(f"DataFrame is missing time column '{time_col}'")
    if sn_col not in df.columns:
        raise KeyError(f"DataFrame is missing sn column '{sn_col}'")
    time_min = pd.to_numeric(df[time_col], errors="coerce").to_numpy(dtype=float)
    sn = pd.to_numeric(df[sn_col], errors="coerce").to_numpy(dtype=float)
    n = len(sn)
    if n < 2:
        raise ValueError("Need at least two rows to compute a derivative.")
    if window_min is None or window_min <= 0:
        raise ValueError("window_min must be positive.")
    if min_points < 2:
        raise ValueError("min_points must be at least 2.")

    half = float(window_min) / 2.0
    return _time_window_slope(
        time_min, sn, half, min_points=int(min_points),
        name="DissolutionRate_Sn_time_lr", index=df.index,
    )


def _time_window_slope(time_min, y, half_min, min_points, name, index):
    """Vectorised OLS slope inside a rolling time window.

    ``time_min`` must already be monotonically non-decreasing (that holds
    after ``load_rate_timeseries``).
    """
    n = len(y)
    cs_t = np.concatenate(([0.0], np.cumsum(time_min)))
    cs_y = np.concatenate(([0.0], np.cumsum(y)))
    cs_tt = np.concatenate(([0.0], np.cumsum(time_min * time_min)))
    cs_ty = np.concatenate(([0.0], np.cumsum(time_min * y)))

    lo = np.searchsorted(time_min, time_min - half_min, side="left")
    hi = np.searchsorted(time_min, time_min + half_min, side="right")

    win_n = (hi - lo).astype(int)

    if min_points > 2:
        too_few = win_n < min_points
        if too_few.any():
            for i in np.flatnonzero(too_few):
                target = min(min_points, n)
                half_count = target // 2
                lo_i = max(0, i - half_count)
                hi_i = min(n, lo_i + target)
                lo_i = max(0, hi_i - target)
                lo[i] = lo_i
                hi[i] = hi_i
            win_n = (hi - lo).astype(int)

    win_n_f = win_n.astype(float)
    sum_t = cs_t[hi] - cs_t[lo]
    sum_y = cs_y[hi] - cs_y[lo]
    sum_tt = cs_tt[hi] - cs_tt[lo]
    sum_ty = cs_ty[hi] - cs_ty[lo]

    denom = win_n_f * sum_tt - sum_t * sum_t
    numer = win_n_f * sum_ty - sum_t * sum_y

    rate = np.full(n, np.nan, dtype=float)
    valid = (win_n_f >= 2.0) & (denom > 1e-30)
    rate[valid] = -(numer[valid] / denom[valid])

    if (~valid).any() and valid.any():
        valid_idx = np.flatnonzero(valid)
        rate = np.interp(np.arange(n), valid_idx, rate[valid_idx])
    return pd.Series(rate, index=index, name=name)


def compute_normalized_rate(rate_series, df, eps=1e-12):
    """Return ``rate / max(Sn, eps)`` so rate scales out of cumulative depletion."""
    saturation = pd.to_numeric(df["Sn"], errors="coerce").to_numpy(dtype=float)
    rate = np.asarray(rate_series, dtype=float)
    denominator = np.maximum(saturation, float(eps))
    normalized = rate / denominator
    return pd.Series(normalized, index=df.index, name="NormalizedDissolutionRate_Sn")


def compute_dissolution_rates(
    df,
    rate_window_min=DEFAULT_RATE_WINDOW_MIN,
    rate_min_points=DEFAULT_RATE_MIN_POINTS,
    **_,
):
    """Compatibility wrapper returning the legacy primary rate columns.

    The production path uses :func:`attach_all_rates`, whose primary rate is a
    time-window local regression on monotone-smoothed Sn. Older tests and
    notebooks called ``compute_dissolution_rates`` directly, so this wrapper
    preserves that small API surface with the same interpretation boundary:
    raw frame-to-frame Sn differences are not used.
    """
    out = df.copy()
    if "RealTime_s" in out.columns:
        out["Time_min"] = pd.to_numeric(out["RealTime_s"], errors="coerce") / 60.0
    elif "Time_min" in out.columns:
        out["Time_min"] = pd.to_numeric(out["Time_min"], errors="coerce")
    elif "Time" in out.columns:
        out["Time_min"] = pd.to_numeric(out["Time"], errors="coerce")
    else:
        out["Time_min"] = np.arange(len(out), dtype=float)

    if "Sn" not in out.columns:
        raise KeyError("DataFrame is missing required column 'Sn'")

    sn = pd.to_numeric(out["Sn"], errors="coerce").to_numpy(dtype=float)
    finite_for_monotone = np.where(np.isfinite(sn), sn, np.inf)
    monotone = np.minimum.accumulate(finite_for_monotone)
    monotone = np.where(np.isfinite(monotone), monotone, np.nan)
    out["SnMonotone"] = monotone
    out["Sn_rate_input"] = monotone

    valid_sn = sn[np.isfinite(sn) & (sn > 0)]
    sn0 = float(valid_sn[0]) if valid_sn.size else np.nan
    out["RemovalFraction"] = (sn0 - sn) / sn0 if np.isfinite(sn0) and sn0 > 0 else np.nan

    rate = compute_dissolution_rate_time_lr(
        out,
        time_col="Time_min",
        sn_col="Sn_rate_input",
        window_min=rate_window_min,
        min_points=rate_min_points,
    )
    rate = rate.clip(lower=0.0)
    out["DissolutionRate_Sn_per_min"] = rate.to_numpy()
    out["DissolutionRate_Sn_time_lr"] = rate.to_numpy()
    out["NormalizedDissolutionRate_Sn_per_min"] = compute_normalized_rate(rate, out).to_numpy()
    return out


# --------------------------------------------------------------------------- #
# Optional physical rates
# --------------------------------------------------------------------------- #
def compute_mass_rate(df):
    if "MassDissolvedKg" not in df.columns:
        return None
    mass = pd.to_numeric(df["MassDissolvedKg"], errors="coerce").to_numpy(dtype=float)
    time_s = pd.to_numeric(df["RealTime_s"], errors="coerce").to_numpy(dtype=float)
    if len(mass) < 2 or not np.isfinite(mass).any():
        return None
    rate = np.gradient(mass, time_s)
    return pd.Series(rate, index=df.index, name="DissolutionRate_mass_kg_per_s")


def compute_projected_interface_length_rate(df, pixel_size_um, mass_rate, unit_info):
    """Return mass rate per projected interface length, using InterfaceArea as L_ow."""
    if mass_rate is None or "InterfaceArea" not in df.columns:
        return None
    interface_length = convert_metric_for_plot(
        pd.to_numeric(df["InterfaceArea"], errors="coerce").to_numpy(dtype=float),
        "InterfaceArea",
        unit_info,
        pixel_size_um,
    )
    iface_info = (unit_info or {}).get("InterfaceArea", {})
    if iface_info.get("plot_unit") != "m":
        return None
    with np.errstate(divide="ignore", invalid="ignore"):
        flux = np.asarray(mass_rate, dtype=float) / np.where(
            interface_length > 0, interface_length, np.nan
        )
    return pd.Series(
        flux,
        index=df.index,
        name="DissolutionRate_per_projected_interface_length_kg_per_s_per_m",
    )


def compute_mass_transfer_proxy(rate_series, df):
    if "InterfaceArea" not in df.columns:
        return pd.Series(np.nan, index=df.index, name="MassTransferProxy_per_pixel")
    interface = pd.to_numeric(df["InterfaceArea"], errors="coerce").to_numpy(dtype=float)
    rate = np.asarray(rate_series, dtype=float)
    denominator = np.where(interface > 0, interface, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        proxy = rate / denominator
    return pd.Series(proxy, index=df.index, name="MassTransferProxy_per_pixel")


# --------------------------------------------------------------------------- #
# Driver helpers
# --------------------------------------------------------------------------- #
def attach_all_rates(
    df,
    movmedian_smooth_window=5,
    dt_seconds=DEFAULT_DT_SECONDS,
    rate_window_min=DEFAULT_RATE_WINDOW_MIN,
    rate_min_points=DEFAULT_RATE_MIN_POINTS,
    sn_smooth_window_frames=DEFAULT_SN_SMOOTH_WINDOW_FRAMES,
    monotone_sn_for_rate=True,
    pixel_size_um=None,
    unit_info=None,
):
    """Mutate ``df`` in place to add every derived rate column, return ``df``.

    The default rate column ``DissolutionRate_Sn_time_lr`` is fit on the
    monotone-smoothed ``Sn_rate_input``; the legacy ``DissolutionRate_Sn_lr``
    and ``DissolutionRate_Sn_movmed`` are kept for QC.
    """
    prepare_sn_rate_input(
        df,
        sn_smooth_window_frames=sn_smooth_window_frames,
        monotone=bool(monotone_sn_for_rate),
    )

    df["DissolutionRate_Sn_time_lr"] = compute_dissolution_rate_time_lr(
        df,
        time_col="Time_min",
        sn_col="Sn_rate_input",
        window_min=rate_window_min,
        min_points=rate_min_points,
    ).to_numpy()
    df["DissolutionRate_Sn_movmed"] = compute_dissolution_rate_movmedian(
        df, smooth_window=movmedian_smooth_window, dt_seconds=dt_seconds
    ).to_numpy()
    df["DissolutionRate_Sn_lr"] = compute_dissolution_rate_lr(
        df, dt_seconds=dt_seconds
    ).to_numpy()

    df["NormalizedDissolutionRate_Sn_time_lr"] = compute_normalized_rate(
        df["DissolutionRate_Sn_time_lr"], df
    ).to_numpy()
    df["NormalizedDissolutionRate_Sn_movmed"] = compute_normalized_rate(
        df["DissolutionRate_Sn_movmed"], df
    ).to_numpy()
    df["NormalizedDissolutionRate_Sn_lr"] = compute_normalized_rate(
        df["DissolutionRate_Sn_lr"], df
    ).to_numpy()

    mass_rate = compute_mass_rate(df)
    if mass_rate is not None:
        df["DissolutionRate_mass_kg_per_s"] = mass_rate.to_numpy()
        if unit_info is None:
            unit_info = infer_metric_units(df, None, pixel_size_um)
        length_rate = compute_projected_interface_length_rate(
            df, pixel_size_um, mass_rate, unit_info
        )
        if length_rate is not None:
            df["DissolutionRate_per_projected_interface_length_kg_per_s_per_m"] = (
                length_rate.to_numpy()
            )

    df["MassTransferProxy_time_lr_per_pixel"] = compute_mass_transfer_proxy(
        df["DissolutionRate_Sn_time_lr"], df
    ).to_numpy()
    df["MassTransferProxy_movmed_per_pixel"] = compute_mass_transfer_proxy(
        df["DissolutionRate_Sn_movmed"], df
    ).to_numpy()
    df["MassTransferProxy_lr_per_pixel"] = compute_mass_transfer_proxy(
        df["DissolutionRate_Sn_lr"], df
    ).to_numpy()
    return df


def _simple_association_rows(df, metric_keys, rate_col):
    rows = []
    y = pd.to_numeric(df[rate_col], errors="coerce") if rate_col in df.columns else None
    for metric in metric_keys:
        available = metric in df.columns and y is not None
        if not available:
            rows.append(
                {
                    "metric": metric,
                    "available": False,
                    "n": 0,
                    "pearson_r": np.nan,
                    "spearman_r": np.nan,
                    "rate_column": rate_col,
                }
            )
            continue
        x = pd.to_numeric(df[metric], errors="coerce")
        valid = x.notna() & y.notna() & np.isfinite(x.to_numpy(dtype=float)) & np.isfinite(y.to_numpy(dtype=float))
        n = int(valid.sum())
        pearson = float(x[valid].corr(y[valid], method="pearson")) if n >= 3 else np.nan
        spearman = float(x[valid].corr(y[valid], method="spearman")) if n >= 3 else np.nan
        rows.append(
            {
                "metric": metric,
                "available": True,
                "n": n,
                "pearson_r": pearson,
                "spearman_r": spearman,
                "rate_column": rate_col,
            }
        )
    return rows


def _simple_binned_rows(df, metric_keys, rate_col, n_bins=5, min_bin_count=20):
    rows = []
    if rate_col not in df.columns:
        return rows
    y_full = pd.to_numeric(df[rate_col], errors="coerce")
    stages = list(df["Stage"].dropna().astype(str).unique()) if "Stage" in df.columns else ["all"]
    for metric in metric_keys:
        if metric not in df.columns:
            continue
        x_full = pd.to_numeric(df[metric], errors="coerce")
        for stage in stages:
            if stage == "all":
                stage_mask = pd.Series(True, index=df.index)
            else:
                stage_mask = df["Stage"].astype(str) == stage
            valid = (
                stage_mask
                & x_full.notna()
                & y_full.notna()
                & np.isfinite(x_full.to_numpy(dtype=float))
                & np.isfinite(y_full.to_numpy(dtype=float))
            )
            if int(valid.sum()) < max(n_bins, min_bin_count):
                continue
            x = x_full[valid]
            y = y_full[valid]
            try:
                bins = pd.qcut(x.rank(method="first"), q=min(n_bins, len(x)), labels=False, duplicates="drop")
            except ValueError:
                continue
            for bin_id in sorted(pd.unique(bins.dropna())):
                mask = bins == bin_id
                if int(mask.sum()) < min_bin_count:
                    continue
                xb = x[mask]
                yb = y[mask]
                rows.append(
                    {
                        "metric": metric,
                        "stage": stage,
                        "bin_id": int(bin_id),
                        "x_bin_min": float(xb.min()),
                        "x_bin_max": float(xb.max()),
                        "x_bin_median": float(xb.median()),
                        "rate_median": float(yb.median()),
                        "rate_p25": float(yb.quantile(0.25)),
                        "rate_p75": float(yb.quantile(0.75)),
                        "n": int(mask.sum()),
                    }
                )
    return rows


def write_rate_outputs(
    csv_path,
    postprocess_dir,
    dpi=300,
    no_figures=False,
    rate_window_min=DEFAULT_RATE_WINDOW_MIN,
    rate_min_points=DEFAULT_RATE_MIN_POINTS,
):
    """Write Level A rate CSVs used by the batch postprocess driver.

    The standalone plotting CLI writes these outputs under ``figures_rate``.
    The Level A driver expects top-level CSVs, so this helper keeps the same
    rate estimator but emits the compact tables consumed by downstream QC and
    interpretation scripts.
    """
    postprocess_dir = Path(postprocess_dir)
    postprocess_dir.mkdir(parents=True, exist_ok=True)

    df = load_rate_timeseries(csv_path)
    attach_stage_and_masks(df)
    pixel_size_um = find_pixel_size_um(postprocess_dir.parent)
    unit_info = infer_metric_units(df, None, pixel_size_um)
    attach_all_rates(
        df,
        rate_window_min=rate_window_min,
        rate_min_points=rate_min_points,
        pixel_size_um=pixel_size_um,
        unit_info=unit_info,
    )

    df["SnMonotone"] = df["Sn_rate_input"]
    first_sn = next((float(v) for v in df["Sn"].to_numpy(dtype=float) if np.isfinite(v) and v > 0), np.nan)
    if np.isfinite(first_sn) and first_sn > 0:
        df["RemovalFraction"] = (first_sn - df["Sn"]) / first_sn
    else:
        df["RemovalFraction"] = np.nan
    df["DissolutionRate_Sn_per_min"] = df["DissolutionRate_Sn_time_lr"]
    df["NormalizedDissolutionRate_Sn_per_min"] = df["NormalizedDissolutionRate_Sn_time_lr"]

    rate_columns = [
        "Time",
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
        "FrameIndex",
        "Time_min",
        "SnNorm",
        "RemovalFraction",
        "SnMonotone",
        "DissolutionRate_Sn_per_min",
        "NormalizedDissolutionRate_Sn_per_min",
        "Stage",
    ]
    present_rate_columns = [c for c in rate_columns if c in df.columns]
    rates = df.loc[:, present_rate_columns].copy()
    rates.to_csv(postprocess_dir / "dissolution_rates.csv", index=False)

    metric_keys = [s["key"] for s in X_AXIS_SPECS] + [s["key"] for s in FRACTION_SPECS]
    associations = pd.DataFrame(_simple_association_rows(df, metric_keys, "DissolutionRate_Sn_per_min"))
    associations.to_csv(postprocess_dir / "rate_metric_associations.csv", index=False)
    binned = pd.DataFrame(_simple_binned_rows(df, metric_keys, "DissolutionRate_Sn_per_min"))
    binned.to_csv(postprocess_dir / "rate_metric_binned_summary.csv", index=False)

    if not no_figures:
        figures_dir = postprocess_dir / "figures_rate"
        figures_dir.mkdir(parents=True, exist_ok=True)
        fig, ax = plt.subplots(figsize=(6.0, 3.0))
        ax.plot(df["Time_min"], df["DissolutionRate_Sn_per_min"], color=WONG_COLORS["blue"], linewidth=0.8)
        ax.set_xlabel("Time (min)")
        ax.set_ylabel("Dissolution rate (Sn/min)")
        style_axes(ax)
        for suffix in ("png", "svg"):
            fig.savefig(figures_dir / f"dissolution_rate_window_{rate_window_min:g}min.{suffix}", dpi=dpi if suffix == "png" else None, bbox_inches="tight", facecolor="white")
        plt.close(fig)

    return {"rates": rates, "associations": associations, "binned": binned}


# --------------------------------------------------------------------------- #
# Plot helpers
# --------------------------------------------------------------------------- #
RATE_LABELS = {
    "raw": r"$-dS_n/dt$ (1/min)",
    "norm": r"$-dS_n/dt \,/\, S_n$ (1/min)",
}


def _x_label_for(spec, df, pixel_size_um, unit_info=None, fraction_kind=None):
    """Build the x-axis label, preferring ``unit_info`` when available."""
    template = spec["label_template"]
    key = spec["key"]

    if "{kind}" in template:
        kind = fraction_kind or "Area"
        return template.format(kind=kind)

    if "{unit}" in template:
        unit = None
        if unit_info and key in unit_info:
            unit = unit_info[key].get("plot_unit")
        if unit is None:
            if key == "ReqMedian":
                unit = df.attrs.get("req_unit") or ("μm" if pixel_size_um else "px")
            elif key == "InterfaceArea":
                unit = "m" if pixel_size_um else "px"
            elif key in ("a_i_2D", "a_i_2D_flow"):
                unit = "1/m"
            else:
                unit = ""
        if key == "ReqMedian" and unit not in ("px", "um"):
            unit = "um" if pixel_size_um else unit
        return template.format(unit=unit)

    return template


def _should_log_metric(metric_key, log_x_metrics, x_values, valid_mask=None):
    """Decide whether to plot this metric on a log axis."""
    if metric_key in FORCE_LINEAR_METRICS:
        return False
    if isinstance(log_x_metrics, str):
        if log_x_metrics.lower() == "auto":
            x = np.asarray(x_values, dtype=float)
            if valid_mask is not None:
                mask = np.asarray(valid_mask, dtype=bool)
                if mask.shape == x.shape:
                    x = x[mask]
            x = x[np.isfinite(x) & (x > 0)]
            if x.size < 10:
                return False
            p5 = float(np.percentile(x, 5))
            p95 = float(np.percentile(x, 95))
            return p5 > 0 and (p95 / p5) > 20.0
        if log_x_metrics.lower() == "all":
            return True
        if log_x_metrics.lower() == "none":
            return False
    if isinstance(log_x_metrics, (set, frozenset, list, tuple)):
        return metric_key in log_x_metrics
    return False


def _decimate_indices(idx, max_points, rng):
    if len(idx) <= max_points:
        return idx
    chosen = rng.choice(idx, size=max_points, replace=False)
    return np.sort(chosen)


def add_rate_zero_line(ax):
    ax.axhline(0.0, color="#999999", linewidth=0.8, linestyle="--", zorder=0)


def _write_rate_data_workbook(stem, sheets, figures_dir):
    """Write one xlsx per plot; sheet names capped at Excel's 31-char limit."""
    figures_dir = Path(figures_dir)
    figures_dir.mkdir(parents=True, exist_ok=True)
    xlsx_path = figures_dir / f"{stem}_data.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="xlsxwriter") as writer:
        for name, data in sheets.items():
            df_out = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
            sheet_title = name[:31]
            df_out.to_excel(writer, sheet_name=sheet_title, index=False)
            worksheet = writer.sheets[sheet_title]
            if len(df_out.columns):
                worksheet.freeze_panes(1, 0)
            for idx, column in enumerate(df_out.columns):
                width = min(max(len(str(column)) + 2, 12), 28)
                worksheet.set_column(idx, idx, width)
    return xlsx_path


def _select_stage_scatter_indices(
    df,
    metric_key,
    rate_col,
    unit_info,
    pixel_size_um,
    log_x,
    max_points,
    show_excluded,
    seed=42,
):
    """Return ``stage -> iloc indices`` drawn for plotting (matches random decimation).

    Indices are positional row numbers into ``df``.
    """
    raw_x = pd.to_numeric(df[metric_key], errors="coerce").to_numpy()
    x = convert_metric_for_plot(raw_x, metric_key, unit_info, pixel_size_um)
    y = pd.to_numeric(df[rate_col], errors="coerce").to_numpy()
    stage_arr = (
        df["Stage"].astype("string").to_numpy()
        if "Stage" in df.columns
        else np.array(["active_removal"] * len(x))
    )
    valid_structure = valid_interpretation_mask(df)
    finite = np.isfinite(x) & np.isfinite(y)
    if log_x:
        finite &= x > 0
    rng = np.random.default_rng(seed)
    out = {}
    if show_excluded:
        context = finite & ~valid_structure
        if np.any(context):
            idx = _decimate_indices(np.flatnonzero(context), max_points, rng)
            out["excluded_context"] = idx.astype(int)
    for stage_label in STAGE_DRAW_ORDER:
        mask = stage_arr == stage_label
        valid = finite & valid_structure & mask
        if not np.any(valid):
            continue
        idx = np.flatnonzero(valid)
        idx = _decimate_indices(idx, max_points, rng)
        out[str(stage_label)] = idx.astype(int)
    return out


def _select_trajectory_indices(
    df,
    metric_key,
    rate_col,
    unit_info,
    pixel_size_um,
    log_x,
    max_points,
    show_excluded,
):
    """Positional indices used for trajectory markers/line (time-sorted subset)."""
    raw_x = pd.to_numeric(df[metric_key], errors="coerce").to_numpy()
    x = convert_metric_for_plot(raw_x, metric_key, unit_info, pixel_size_um)
    y = pd.to_numeric(df[rate_col], errors="coerce").to_numpy()
    t = pd.to_numeric(df["Time_min"], errors="coerce").to_numpy()
    valid_structure = valid_interpretation_mask(df)
    valid = np.isfinite(x) & np.isfinite(y) & np.isfinite(t)
    if log_x:
        valid &= x > 0
    if not show_excluded:
        valid &= valid_structure
    if not np.any(valid):
        return np.array([], dtype=int)
    idx = np.flatnonzero(valid)
    if len(idx) > max_points:
        sel = np.linspace(0, len(idx) - 1, max_points).astype(int)
        idx = idx[sel]
    order = idx[np.argsort(t[idx])]
    return order.astype(int)


def _metric_rate_plot_dataframe(
    df,
    metric_key,
    rate_col,
    unit_info,
    pixel_size_um,
    log_x,
    require_finite_time=False,
):
    """Build one aligned row-wise table including raw/plot metric and rate."""
    raw_x = pd.to_numeric(df[metric_key], errors="coerce").to_numpy()
    x_plot = convert_metric_for_plot(raw_x, metric_key, unit_info, pixel_size_um)
    y = pd.to_numeric(df[rate_col], errors="coerce").to_numpy()
    cols = {}

    def _pull(name, default=np.nan):
        if name not in df.columns:
            return np.full(len(df), default)
        v = pd.to_numeric(df[name], errors="coerce") if df[name].dtype != object else df[name]
        return v.to_numpy() if hasattr(v, "to_numpy") else np.asarray(v)

    cols[f"{metric_key}_raw"] = raw_x.astype(float)
    cols[f"{metric_key}_plot"] = x_plot.astype(float)
    cols[rate_col] = y.astype(float)
    cols["RealTime_s"] = _pull("RealTime_s")
    cols["Time_min"] = _pull("Time_min")
    cols["Sn"] = _pull("Sn")
    cols["Sn_rate_input"] = _pull("Sn_rate_input")
    cols["SnNorm"] = _pull("SnNorm")
    if "Stage" in df.columns:
        cols["Stage"] = df["Stage"].astype("string").to_numpy()
    else:
        cols["Stage"] = np.array(["active_removal"] * len(df), dtype=object)
    if "ValidStructure" in df.columns:
        cols["ValidStructure"] = df["ValidStructure"].to_numpy()
    else:
        cols["ValidStructure"] = np.full(len(df), True, dtype=bool)
    if "NearDepleted" in df.columns:
        cols["NearDepleted"] = df["NearDepleted"].to_numpy()
    else:
        cols["NearDepleted"] = np.zeros(len(df), dtype=bool)
    if "FrameIndex" in df.columns:
        cols["FrameIndex"] = _pull("FrameIndex")

    out = pd.DataFrame(cols)
    mask = np.isfinite(x_plot) & np.isfinite(y)
    if log_x:
        mask &= x_plot > 0
    if require_finite_time:
        mask &= np.isfinite(out["Time_min"].to_numpy(dtype=float))
    keep = np.flatnonzero(mask)
    return out, keep


def _build_scatter_or_trajectory_sheets(
    df,
    metric_key,
    rate_col,
    unit_info,
    pixel_size_um,
    log_x,
    plotted_ilocs,
    require_finite_time=False,
):
    """``data_all`` = all valid rows; ``data_plotted`` = plotted subsample."""
    full, ix_all = _metric_rate_plot_dataframe(
        df,
        metric_key,
        rate_col,
        unit_info,
        pixel_size_um,
        log_x,
        require_finite_time=require_finite_time,
    )
    data_all = full.iloc[ix_all].reset_index(drop=True)
    plotted_ilocs = np.asarray(plotted_ilocs, dtype=int).ravel()
    plotted_ilocs = np.unique(plotted_ilocs[np.isin(plotted_ilocs, ix_all)])
    data_plotted = (
        full.iloc[plotted_ilocs].reset_index(drop=True)
        if plotted_ilocs.size
        else full.iloc[[]].copy()
    )
    # Align empty plotted sheet columns to data_all
    if data_plotted.empty and not data_all.empty:
        data_plotted = pd.DataFrame({c: [] for c in data_all.columns})
    return {"data_all": data_all, "data_plotted": data_plotted}


def plot_stage_scatter(
    ax,
    df,
    metric_key,
    rate_col,
    spec,
    unit_info,
    pixel_size_um,
    plotted_idx_per_stage,
    log_x=False,
    fraction_kind=None,
):
    """Stage-coloured scatter; no global regression; near-depleted greyed out.

    ``plotted_idx_per_stage`` maps stage name to positional row indices into ``df``
    (same indices used for the ``data_plotted`` Excel sheet).
    """
    raw_x = pd.to_numeric(df[metric_key], errors="coerce").to_numpy()
    x = convert_metric_for_plot(raw_x, metric_key, unit_info, pixel_size_um)
    y = pd.to_numeric(df[rate_col], errors="coerce").to_numpy()

    plotted_any = False
    handles = {}

    context_idx = plotted_idx_per_stage.get("excluded_context")
    if context_idx is not None and len(context_idx):
        handle = ax.scatter(
            x[context_idx], y[context_idx],
            s=10.0, marker="o", facecolors="none",
            edgecolors="#B8B8B8", linewidths=0.55,
            alpha=0.6, zorder=1,
        )
        handles["excluded_context"] = handle
        plotted_any = True

    for stage_label in STAGE_DRAW_ORDER:
        idx = plotted_idx_per_stage.get(str(stage_label))
        if idx is None or len(idx) == 0:
            continue
        color = STAGE_COLORS.get(stage_label, "#666666")

        if stage_label == "near_depleted":
            handle = ax.scatter(
                x[idx], y[idx],
                s=8.0, facecolors="none", edgecolors=color,
                linewidths=0.5, alpha=0.55, zorder=1,
            )
        elif stage_label == "active_removal":
            handle = ax.scatter(
                x[idx], y[idx],
                s=12.0, color=color, edgecolors="white",
                linewidths=0.3, alpha=0.85, zorder=4,
            )
        else:
            handle = ax.scatter(
                x[idx], y[idx],
                s=10.0, color=color, edgecolors="white",
                linewidths=0.25, alpha=0.7,
                zorder=2 if stage_label == "induction_or_stable" else 3,
            )
        handles[stage_label] = handle
        plotted_any = True

    if not plotted_any:
        ax.text(0.5, 0.5, "No data", transform=ax.transAxes,
                ha="center", va="center", color="#888888", fontsize=8)

    ax.set_xlabel(_x_label_for(spec, df, pixel_size_um, unit_info, fraction_kind))
    add_rate_zero_line(ax)
    if log_x:
        ax.set_xscale("log")
    style_axes(ax)
    if log_x:
        ax.grid(True, which="both", color="#E4E4E4", linewidth=0.55, alpha=0.7)

    if handles:
        legend_order = [s for s in ("induction_or_stable", "active_removal", "tail", "near_depleted", "excluded_context")
                         if s in handles]
        ax.legend(
            [handles[s] for s in legend_order],
            [s.replace("_", " ") for s in legend_order],
            loc="lower center",
            bbox_to_anchor=(0.5, 1.04),
            ncol=len(legend_order),
            frameon=False,
            handlelength=1.0,
            handletextpad=0.3,
            columnspacing=1.0,
            borderaxespad=0.0,
            fontsize=7.5,
        )


def compute_binned_summary_rows(df, metric_key, rate_col, unit_info, pixel_size_um,
                                  stages, n_bins, log_x, min_bin_count=20):
    """Return a list of dict rows (one per stage*bin) ready for both the
    binned-summary plot and the binned-summary CSV."""
    rows = []
    for stage_label in stages:
        if "Stage" in df.columns:
            sub = df[df["Stage"].astype("string") == stage_label]
        else:
            sub = df
        if sub.empty:
            continue
        raw_x = pd.to_numeric(sub[metric_key], errors="coerce").to_numpy()
        x = convert_metric_for_plot(raw_x, metric_key, unit_info, pixel_size_um)
        y = pd.to_numeric(sub[rate_col], errors="coerce").to_numpy()
        valid = np.isfinite(x) & np.isfinite(y)
        valid &= valid_interpretation_mask(sub)
        if log_x:
            valid &= x > 0
        x = x[valid]
        y = y[valid]
        if x.size < max(n_bins, 4):
            continue
        quantiles = np.linspace(0.0, 1.0, n_bins + 1)
        edges = np.unique(np.quantile(x, quantiles))
        if len(edges) < 3:
            continue
        bin_idx = np.clip(np.searchsorted(edges, x, side="right") - 1, 0, len(edges) - 2)
        for b in range(len(edges) - 1):
            mask = bin_idx == b
            if not mask.any():
                continue
            xb = x[mask]
            yb = y[mask]
            if xb.size < min_bin_count:
                continue
            x_bin_median = float(np.median(xb))
            x_bin_p25 = float(np.percentile(xb, 25))
            x_bin_p75 = float(np.percentile(xb, 75))
            rate_median = float(np.median(yb))
            rate_p25 = float(np.percentile(yb, 25))
            rate_p75 = float(np.percentile(yb, 75))
            rows.append(
                {
                    "metric": metric_key,
                    "stage": stage_label,
                    "bin_id": b,
                    "x_bin_min": float(edges[b]),
                    "x_bin_max": float(edges[b + 1]),
                    "x_bin_p25": x_bin_p25,
                    "x_bin_median": x_bin_median,
                    "x_bin_p75": x_bin_p75,
                    "x_bin_iqr": x_bin_p75 - x_bin_p25,
                    "rate_p25": rate_p25,
                    "rate_median": rate_median,
                    "rate_p75": rate_p75,
                    "rate_iqr": rate_p75 - rate_p25,
                    "x_plot": x_bin_median,
                    "y_plot": rate_median,
                    "yerr_lower": rate_median - rate_p25,
                    "yerr_upper": rate_p75 - rate_median,
                    "errorbar_definition": "y_plot=rate_median; yerr_lower=rate_median-rate_p25; yerr_upper=rate_p75-rate_median",
                    "n": int(xb.size),
                }
            )
    return rows


def plot_binned_summary(ax, binned_rows, spec, df, unit_info, pixel_size_um,
                         log_x=False, fraction_kind=None):
    if not binned_rows:
        ax.text(0.5, 0.5, "No data", transform=ax.transAxes,
                ha="center", va="center", color="#888888", fontsize=8)
    else:
        by_stage = {}
        for r in binned_rows:
            by_stage.setdefault(r["stage"], []).append(r)
        for stage_label, rs in by_stage.items():
            color = STAGE_COLORS.get(stage_label, "#444444")
            xs = np.array([r["x_bin_median"] for r in rs])
            ys = np.array([r["rate_median"] for r in rs])
            err_lo = np.array([r["rate_median"] - r["rate_p25"] for r in rs])
            err_hi = np.array([r["rate_p75"] - r["rate_median"] for r in rs])
            order = np.argsort(xs)
            ax.errorbar(
                xs[order], ys[order],
                yerr=[err_lo[order], err_hi[order]],
                marker="o", markersize=4.0, color=color,
                linestyle="none", elinewidth=0.8, capsize=2.5,
                alpha=0.9, label=stage_label.replace("_", " "),
            )
            ax.plot(xs[order], ys[order], color=color, linewidth=1.2,
                     alpha=0.7, zorder=2)

    ax.set_xlabel(_x_label_for(spec, df, pixel_size_um, unit_info, fraction_kind))
    add_rate_zero_line(ax)
    if log_x:
        ax.set_xscale("log")
    style_axes(ax)
    if log_x:
        ax.grid(True, which="both", color="#E4E4E4", linewidth=0.55, alpha=0.7)


def plot_trajectory(
    ax,
    df,
    metric_key,
    rate_col,
    spec,
    unit_info,
    pixel_size_um,
    plotted_iloc_ordered,
    log_x=False,
    fraction_kind=None,
):
    """Trajectory (time-colored); ``plotted_iloc_ordered`` is row indices in plot order."""
    raw_x = pd.to_numeric(df[metric_key], errors="coerce").to_numpy()
    x = convert_metric_for_plot(raw_x, metric_key, unit_info, pixel_size_um)
    y = pd.to_numeric(df[rate_col], errors="coerce").to_numpy()
    t = pd.to_numeric(df["Time_min"], errors="coerce").to_numpy()
    valid_structure = valid_interpretation_mask(df)

    ax.set_xlabel(_x_label_for(spec, df, pixel_size_um, unit_info, fraction_kind))
    add_rate_zero_line(ax)
    if log_x:
        ax.set_xscale("log")
    style_axes(ax)
    if log_x:
        ax.grid(True, which="both", color="#E4E4E4", linewidth=0.55, alpha=0.7)

    order = np.asarray(plotted_iloc_ordered, dtype=int).ravel()
    if order.size == 0:
        ax.text(0.5, 0.5, "No data", transform=ax.transAxes,
                ha="center", va="center", color="#888888", fontsize=8)
        return

    norm = Normalize(vmin=float(t[order].min()), vmax=float(t[order].max()))
    ax.plot(x[order], y[order], color="#888888", linewidth=0.5, alpha=0.4, zorder=1)
    valid_mask = valid_structure[order]
    if np.any(valid_mask):
        ax.scatter(
            x[order][valid_mask], y[order][valid_mask],
            c=t[order][valid_mask], cmap="viridis", norm=norm,
            s=10.0, linewidths=0.0, alpha=0.85, zorder=3,
        )
    near_mask = ~valid_structure[order]
    if np.any(near_mask):
        ax.scatter(
            x[order][near_mask], y[order][near_mask],
            s=14.0, marker="o", facecolors="none",
            edgecolors="#BBBBBB", linewidths=0.6, alpha=0.7, zorder=2,
        )

    sm = ScalarMappable(norm=norm, cmap="viridis")
    sm.set_array([])
    cbar = ax.figure.colorbar(sm, ax=ax, pad=0.02, fraction=0.045)
    cbar.set_label("Time (min)", fontsize=8.0)
    cbar.ax.tick_params(labelsize=7.5)
    cbar.outline.set_linewidth(0.6)


# --------------------------------------------------------------------------- #
# Statistics helpers
# --------------------------------------------------------------------------- #
def compute_associations(df, metric_keys, rate_col, unit_info, pixel_size_um):
    """Per-(metric, stage) summary including Spearman/Pearson correlations."""
    rows = []
    stages = list(STAGE_LABELS)
    if "Stage" not in df.columns:
        return rows
    stage_arr = df["Stage"].astype("string").to_numpy()
    interpretation_mask = valid_interpretation_mask(df)
    rate_vals = pd.to_numeric(df[rate_col], errors="coerce").to_numpy()
    for metric in metric_keys:
        if metric not in df.columns:
            continue
        raw_x_full = pd.to_numeric(df[metric], errors="coerce").to_numpy()
        x_full = convert_metric_for_plot(raw_x_full, metric, unit_info, pixel_size_um)
        for stage_label in stages:
            stage_mask = stage_arr == stage_label
            finite = np.isfinite(x_full) & np.isfinite(rate_vals) & stage_mask
            valid = finite & interpretation_mask
            n_total = int(np.count_nonzero(finite))
            n_valid = int(np.count_nonzero(valid))
            n_excluded = int(n_total - n_valid)
            x = x_full[valid]
            y = rate_vals[valid]
            if x.size == 0:
                rows.append(
                    {
                        "metric": metric,
                        "stage": stage_label,
                        "n": 0,
                        "n_total": n_total,
                        "n_valid": n_valid,
                        "n_excluded": n_excluded,
                        "exclusion_rule": "ValidStructure == True",
                        "x_min": float("nan"),
                        "x_median": float("nan"),
                        "x_max": float("nan"),
                        "rate_median": float("nan"),
                        "rate_iqr": float("nan"),
                        "spearman_rho": float("nan"),
                        "pearson_r": float("nan"),
                        "used_for_interpretation": False,
                    }
                )
                continue
            spearman_val = pd.Series(x).corr(pd.Series(y), method="spearman")
            pearson_val = pd.Series(x).corr(pd.Series(y), method="pearson")
            rows.append(
                {
                    "metric": metric,
                    "stage": stage_label,
                    "n": int(x.size),
                    "n_total": n_total,
                    "n_valid": n_valid,
                    "n_excluded": n_excluded,
                    "exclusion_rule": "ValidStructure == True",
                    "x_min": float(np.min(x)),
                    "x_median": float(np.median(x)),
                    "x_max": float(np.max(x)),
                    "rate_median": float(np.median(y)),
                    "rate_iqr": float(np.percentile(y, 75) - np.percentile(y, 25)),
                    "spearman_rho": float(spearman_val) if pd.notna(spearman_val) else float("nan"),
                    "pearson_r": float(pearson_val) if pd.notna(pearson_val) else float("nan"),
                    "used_for_interpretation": stage_label == "active_removal",
                }
            )
    return rows


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def _parse_log_x(value):
    if value is None or value == "":
        return set(DEFAULT_LOG_X_METRICS)
    if value.lower() == "none":
        return set()
    if value.lower() == "all":
        return set(LOG_X_ALLOWED_METRICS)
    if value.lower() == "auto":
        return "auto"
    parsed = {item.strip() for item in value.split(",") if item.strip()}
    unknown = sorted(parsed - LOG_X_ALLOWED_METRICS)
    if unknown:
        allowed = ", ".join(sorted(LOG_X_ALLOWED_METRICS))
        raise ValueError(
            f"Unknown --log-x metric(s): {', '.join(unknown)}. "
            f"Allowed values: {allowed}, all, none, auto"
        )
    return parsed


def _rate_method_stem(rate_method):
    return str(rate_method).replace("-", "_")


def _resolve_fraction_kind(args, df):
    """Return ``"Area"`` or ``"Count"`` without reading large blob-detail CSVs."""
    choice = getattr(args, "fraction_kind", "area") if args is not None else "area"
    choice = str(choice).lower()
    if choice == "area":
        return "Area"
    if choice == "count":
        return "Count"
    if any(col in df.columns for col in ("areaFracDroplets", "areaFracColumns", "areaFracClusters")):
        return "Area"
    if any(col in df.columns for col in ("countFracDroplets", "countFracColumns", "countFracClusters")):
        return "Count"
    return "Area"


def attach_topology_fraction_qc(df, output_dir, min_blob_area_px=20):
    """Attach area/count topology fractions from blob_detail_all_frames.csv when present."""
    blob_detail_path = find_blob_detail_csv(output_dir)
    if blob_detail_path is None:
        return df, {
            "path": None,
            "status": "missing blob_detail_all_frames.csv; count-fraction rate plots skipped unless count columns are already present",
        }

    blob_detail = pd.read_csv(blob_detail_path)
    enriched, qc = _pt.apply_blob_detail_qc(
        df,
        blob_detail,
        min_blob_area_px=min_blob_area_px,
    )
    topology = qc.get("topology", {}) if isinstance(qc, dict) else {}
    return enriched, {
        "path": str(blob_detail_path),
        "status": "loaded",
        "classification": topology.get("classification", "ambiguous"),
    }


def metric_availability_rows(df, specs, rate_col):
    rows = []
    y = pd.to_numeric(df[rate_col], errors="coerce").to_numpy() if rate_col in df.columns else None
    for spec in specs:
        metric = spec["key"]
        if metric not in df.columns:
            rows.append(
                {
                    "metric": metric,
                    "available": False,
                    "n_finite": 0,
                    "n_missing": int(len(df)),
                    "plotted": False,
                    "reason_if_skipped": "missing column",
                }
            )
            continue
        x = pd.to_numeric(df[metric], errors="coerce").to_numpy()
        finite_x = np.isfinite(x)
        finite_pair = finite_x & np.isfinite(y) if y is not None else finite_x
        n_finite = int(np.count_nonzero(finite_pair))
        n_missing = int(len(df) - np.count_nonzero(finite_x))
        plotted = bool(n_finite > 0 and y is not None)
        reason = "" if plotted else ("missing rate column" if y is None else "no finite data")
        rows.append(
            {
                "metric": metric,
                "available": True,
                "n_finite": n_finite,
                "n_missing": n_missing,
                "plotted": plotted,
                "reason_if_skipped": reason,
            }
        )
    return rows


def create_all_rate_figures(
    df,
    figures_dir,
    rate_method="time-lr",
    dpi=300,
    pixel_size_um=None,
    log_x_metrics=None,
    plot_set=("stage", "binned", "trajectory"),
    plot_normalized_rate=False,
    n_bins=8,
    max_scatter_points=3000,
    max_trajectory_points=800,
    show_excluded_context=True,
    binned_stages=("active_removal",),
    min_bin_count=20,
    fraction_kind=None,
    unit_info=None,
    save_plot_data=True,
):
    """Generate the rate-vs-X figures and return ``(written_paths, binned_rows)``.

    The figure count is ``len(specs) * len(plot_set) * (1 + plot_normalized_rate)``
    where ``specs`` is the union of ``X_AXIS_SPECS`` and ``FRACTION_SPECS``.
    """
    if rate_method not in RATE_METHOD_TO_COLUMN:
        raise ValueError(f"rate_method must be one of {sorted(RATE_METHOD_TO_COLUMN)}")
    plot_set = tuple(item for item in plot_set if item)
    invalid_plots = sorted(set(plot_set) - {"stage", "binned", "trajectory"})
    if invalid_plots:
        raise ValueError(
            f"Unknown plot kinds: {invalid_plots}. Allowed: stage, binned, trajectory"
        )

    if unit_info is None:
        unit_info = infer_metric_units(df, None, pixel_size_um)

    configure_nature_style()
    figures_dir = Path(figures_dir)
    figures_dir.mkdir(parents=True, exist_ok=True)

    rate_col = RATE_METHOD_TO_COLUMN[rate_method]
    norm_col = RATE_METHOD_TO_NORM_COLUMN[rate_method]

    rate_variants = [("rate", rate_col, RATE_LABELS["raw"], False)]
    if plot_normalized_rate:
        rate_variants.append(("normalized_rate", norm_col, RATE_LABELS["norm"], True))

    written = []
    binned_rows_all = []

    fraction_kind = fraction_kind or "Area"
    all_specs = _rate_metric_specs(df, fraction_kind, include_count_fractions=True)
    method_stem = _rate_method_stem(rate_method)
    valid_for_scale = valid_interpretation_mask(df)

    for variant_prefix, column, ylabel, restrict_to_valid in rate_variants:
        df_for_plot = (
            df[df["ValidStructure"].astype(bool)] if restrict_to_valid and "ValidStructure" in df.columns else df
        )
        if df_for_plot is df:
            pass

        for spec in all_specs:
            metric = spec["key"]
            if metric not in df.columns:
                continue
            kind_for_label = spec.get("fraction_kind")

            x_raw = pd.to_numeric(df[metric], errors="coerce").to_numpy()
            x_for_log = convert_metric_for_plot(x_raw, metric, unit_info, pixel_size_um)
            log_x = _should_log_metric(
                metric, log_x_metrics, x_for_log, valid_mask=valid_for_scale
            )

            stem_prefix = (
                f"rate_{method_stem}"
                if variant_prefix == "rate"
                else f"normalized_rate_{method_stem}"
            )

            if "stage" in plot_set:
                plotted_by_stage = _select_stage_scatter_indices(
                    df_for_plot,
                    metric,
                    column,
                    unit_info,
                    pixel_size_um,
                    log_x,
                    max_scatter_points,
                    show_excluded_context,
                    seed=42,
                )
                fig, ax = plt.subplots(figsize=INDIVIDUAL_SIZE)
                plot_stage_scatter(
                    ax, df_for_plot, metric, column, spec, unit_info,
                    pixel_size_um, plotted_by_stage, log_x=log_x,
                    fraction_kind=kind_for_label,
                )
                ax.set_ylabel(ylabel)
                fig.tight_layout(pad=0.6)
                stem = f"{stem_prefix}_vs_{spec['stem']}_stage_scatter"
                written.extend(_save_figure(fig, stem, figures_dir, dpi))
                plt.close(fig)
                if save_plot_data:
                    stage_arrays = [v for v in plotted_by_stage.values() if len(v)]
                    union_idx = (
                        np.unique(np.concatenate(stage_arrays))
                        if stage_arrays
                        else np.array([], dtype=int)
                    )
                    sheets = _build_scatter_or_trajectory_sheets(
                        df_for_plot,
                        metric,
                        column,
                        unit_info,
                        pixel_size_um,
                        log_x,
                        union_idx,
                        require_finite_time=False,
                    )
                    written.append(_write_rate_data_workbook(stem, sheets, figures_dir))

            if "binned" in plot_set:
                rows = compute_binned_summary_rows(
                    df_for_plot, metric, column, unit_info, pixel_size_um,
                    stages=binned_stages, n_bins=n_bins, log_x=log_x,
                    min_bin_count=min_bin_count,
                )
                fig, ax = plt.subplots(figsize=INDIVIDUAL_SIZE)
                plot_binned_summary(
                    ax, rows, spec, df_for_plot, unit_info, pixel_size_um,
                    log_x=log_x, fraction_kind=kind_for_label,
                )
                ax.set_ylabel(f"Median {ylabel}")
                fig.tight_layout(pad=0.6)
                stem = f"{stem_prefix}_vs_{spec['stem']}_binned_active"
                written.extend(_save_figure(fig, stem, figures_dir, dpi))
                plt.close(fig)
                if save_plot_data:
                    written.append(
                        _write_rate_data_workbook(
                            stem,
                            {"data": pd.DataFrame(rows, columns=BINNED_SUMMARY_COLUMNS)},
                            figures_dir,
                        )
                    )
                if variant_prefix == "rate":
                    binned_rows_all.extend(rows)

            if "trajectory" in plot_set:
                traj_order = _select_trajectory_indices(
                    df_for_plot,
                    metric,
                    column,
                    unit_info,
                    pixel_size_um,
                    log_x,
                    max_trajectory_points,
                    show_excluded_context,
                )
                fig, ax = plt.subplots(figsize=INDIVIDUAL_SIZE)
                plot_trajectory(
                    ax, df_for_plot, metric, column, spec, unit_info, pixel_size_um,
                    traj_order, log_x=log_x, fraction_kind=kind_for_label,
                )
                ax.set_ylabel(ylabel)
                fig.tight_layout(pad=0.6)
                stem = f"{stem_prefix}_vs_{spec['stem']}_trajectory_timecolored"
                written.extend(_save_figure(fig, stem, figures_dir, dpi))
                plt.close(fig)
                if save_plot_data:
                    sheets = _build_scatter_or_trajectory_sheets(
                        df_for_plot,
                        metric,
                        column,
                        unit_info,
                        pixel_size_um,
                        log_x,
                        traj_order,
                        require_finite_time=True,
                    )
                    written.append(_write_rate_data_workbook(stem, sheets, figures_dir))

    return written, binned_rows_all


def compute_dissolution_rates(
    df,
    rate_window_min=DEFAULT_RATE_WINDOW_MIN,
    rate_min_points=DEFAULT_RATE_MIN_POINTS,
    min_sn_norm_valid=0.05,
    min_blobs_valid=20,
    sn_smooth_window_frames=1,
    monotone_sn_for_rate=True,
):
    """Compatibility helper returning a DataFrame with derived rate columns."""
    out = df.copy()
    if "Time_min" not in out.columns:
        if "RealTime_s" not in out.columns:
            raise KeyError("DataFrame must contain RealTime_s or Time_min")
        out["Time_min"] = pd.to_numeric(out["RealTime_s"], errors="coerce") / 60.0
    attach_stage_and_masks(
        out,
        min_sn_norm_valid=min_sn_norm_valid,
        min_blobs_valid=min_blobs_valid,
    )
    attach_all_rates(
        out,
        rate_window_min=rate_window_min,
        rate_min_points=rate_min_points,
        sn_smooth_window_frames=sn_smooth_window_frames,
        monotone_sn_for_rate=monotone_sn_for_rate,
    )
    out["SnMonotone"] = out["Sn_rate_input"]
    out["DissolutionRate_Sn_per_min"] = out["DissolutionRate_Sn_time_lr"]
    out["RemovalFraction"] = 1.0 - out["SnNorm"]
    return out


def _default_unit_args():
    return argparse.Namespace(
        ai2d_unit="auto",
        interface_unit="auto",
        req_unit="auto",
        fraction_kind="area",
    )


def _default_rate_columns(df):
    rate_columns = [
        "RealTime_s", "Time_min", "Sn", "Sn_rate_input",
        "SnNorm", "Stage", "ValidStructure", "NearDepleted",
        "DissolutionRate_Sn_time_lr",
        "DissolutionRate_Sn_movmed",
        "DissolutionRate_Sn_lr",
        "NormalizedDissolutionRate_Sn_time_lr",
        "NormalizedDissolutionRate_Sn_movmed",
        "NormalizedDissolutionRate_Sn_lr",
        "MassTransferProxy_time_lr_per_pixel",
        "MassTransferProxy_movmed_per_pixel",
        "MassTransferProxy_lr_per_pixel",
    ]
    for optional in (
        "DissolutionRate_mass_kg_per_s",
        "DissolutionRate_per_projected_interface_length_kg_per_s_per_m",
    ):
        if optional in df.columns:
            rate_columns.append(optional)
    return [c for c in rate_columns if c in df.columns]


def write_rate_outputs(
    timeseries_csv,
    output_dir,
    dpi=300,
    no_figures=False,
    rate_window_min=DEFAULT_RATE_WINDOW_MIN,
    rate_min_points=DEFAULT_RATE_MIN_POINTS,
    pixel_size_um=None,
):
    """Run rate/metric association outputs as a library call for the driver."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = load_rate_timeseries(timeseries_csv)
    attach_stage_and_masks(df)
    unit_args = _default_unit_args()
    unit_info = infer_metric_units(df, unit_args, pixel_size_um)
    attach_all_rates(
        df,
        rate_window_min=rate_window_min,
        rate_min_points=rate_min_points,
        pixel_size_um=pixel_size_um,
        unit_info=unit_info,
    )

    rate_method = "time-lr"
    rate_col = RATE_METHOD_TO_COLUMN[rate_method]
    fraction_kind = _resolve_fraction_kind(unit_args, df)
    all_specs = _rate_metric_specs(df, fraction_kind, include_count_fractions=True)
    all_metric_keys = [s["key"] for s in all_specs]

    figure_paths = []
    binned_rows = []
    if not no_figures:
        figure_paths, binned_rows = create_all_rate_figures(
            df,
            figures_dir=output_dir / "figures_rate",
            rate_method=rate_method,
            dpi=dpi,
            pixel_size_um=pixel_size_um,
            log_x_metrics={"auto"},
            fraction_kind=fraction_kind,
            unit_info=unit_info,
        )
    else:
        valid_mask = valid_interpretation_mask(df)
        for spec in all_specs:
            key = spec["key"]
            if key not in df.columns:
                continue
            values = pd.to_numeric(df[key], errors="coerce")
            log_x = _should_log_metric(key, {"auto"}, values, valid_mask)
            binned_rows.extend(
                compute_binned_summary_rows(
                    df,
                    key,
                    rate_col,
                    unit_info,
                    pixel_size_um,
                    stages=("active_removal",),
                    n_bins=8,
                    log_x=log_x,
                    min_bin_count=20,
                )
            )

    rates_csv = output_dir / "dissolution_rates.csv"
    associations_csv = output_dir / "rate_metric_associations.csv"
    binned_csv = output_dir / "rate_metric_binned_summary.csv"
    unit_json = output_dir / "rate_plot_unit_inference.json"

    df.loc[:, _default_rate_columns(df)].to_csv(rates_csv, index=False)
    pd.DataFrame(compute_associations(df, all_metric_keys, rate_col, unit_info, pixel_size_um)).to_csv(
        associations_csv,
        index=False,
    )
    pd.DataFrame(binned_rows, columns=BINNED_SUMMARY_COLUMNS).to_csv(
        binned_csv, index=False
    )
    with open(unit_json, "w", encoding="utf-8") as fp:
        json.dump(unit_info, fp, indent=2, ensure_ascii=False, default=_json_default)

    return {
        "rates": df,
        "associations": associations_csv,
        "binned_summary": binned_csv,
        "unit_info": unit_info,
        "outputs": {
            "rates_csv": rates_csv,
            "associations_csv": associations_csv,
            "binned_csv": binned_csv,
            "unit_json": unit_json,
            "figures": figure_paths,
        },
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Plot -dSn/dt vs microstructural metrics (companion to plot_timeseries.py)."
    )
    parser.add_argument("output_dir", help="Pipeline output directory containing the time-series CSV.")
    parser.add_argument("--csv", dest="csv_path", help="Explicit path to the time-series CSV.")
    parser.add_argument(
        "--figures-dir",
        help="Directory for generated figures. Defaults to <output_dir>/figures_rate.",
    )
    parser.add_argument("--dpi", type=int, default=300, help="PNG output DPI.")
    parser.add_argument(
        "--skip-frames",
        type=int,
        default=0,
        help="Number of initial frames to skip (e.g. 1 to remove injection transient at t=0).",
    )
    parser.add_argument(
        "--min-time-min",
        type=float,
        default=None,
        help="Drop rows with Time_min below this threshold before plotting.",
    )
    parser.add_argument(
        "--pixel-size-um",
        type=float,
        default=None,
        help="Pixel size in micrometres per pixel; auto-detected from analysis_report.txt when omitted.",
    )

    parser.add_argument(
        "--rate-method",
        choices=("time-lr", "lr", "movmedian"),
        default="time-lr",
        help="Which dissolution-rate column drives the plots (default: time-lr).",
    )
    parser.add_argument(
        "--rate-window-min",
        type=float,
        default=DEFAULT_RATE_WINDOW_MIN,
        help="Time window (minutes) used by the time-lr rate method (default: 20).",
    )
    parser.add_argument(
        "--rate-min-points",
        type=int,
        default=DEFAULT_RATE_MIN_POINTS,
        help="Minimum number of points used in each time-lr fit (default: 25).",
    )
    parser.add_argument(
        "--sn-smooth-window-frames",
        type=int,
        default=DEFAULT_SN_SMOOTH_WINDOW_FRAMES,
        help="Frame window for the rolling-median pre-smoothing of Sn (default: 51).",
    )
    parser.add_argument(
        "--monotone-sn-for-rate",
        dest="monotone_sn_for_rate",
        action="store_true",
        help="Force Sn used for rate to be monotonically non-increasing (default: on).",
    )
    parser.add_argument(
        "--no-monotone-sn-for-rate",
        dest="monotone_sn_for_rate",
        action="store_false",
        help="Disable monotonic smoothing of Sn for rate input.",
    )
    parser.set_defaults(monotone_sn_for_rate=True)

    parser.add_argument(
        "--dt-seconds",
        type=float,
        default=DEFAULT_DT_SECONDS,
        help=(
            "Time window (seconds) used by the QC rate methods (lr, movmedian). "
            "Default 270 s (= 4.5 min)."
        ),
    )
    parser.add_argument(
        "--movmedian-window",
        type=int,
        default=5,
        help="Frame count for the movmedian pre-smoothing of Sn (default: 5).",
    )

    parser.add_argument(
        "--min-sn-norm-valid",
        type=float,
        default=0.05,
        help="Minimum Sn/Sn0 to count as valid structure (default: 0.05).",
    )
    parser.add_argument(
        "--min-blobs-valid",
        type=int,
        default=20,
        help="Minimum NumBlobs to count as valid structure (default: 20).",
    )
    parser.add_argument(
        "--min-blob-area-px",
        type=float,
        default=20,
        help=(
            "Minimum blob area in pixels for topology fraction recomputation from "
            "blob_detail_all_frames.csv (default: 20)."
        ),
    )
    parser.add_argument(
        "--stage-mode",
        choices=("snnorm",),
        default="snnorm",
        help="How to assign Stage labels (currently only snnorm).",
    )

    parser.add_argument(
        "--show-excluded-context",
        dest="show_excluded_context",
        action="store_true",
        help="Show near-depleted points in greyed-out style (default: on).",
    )
    parser.add_argument(
        "--no-show-excluded-context",
        dest="show_excluded_context",
        action="store_false",
        help="Hide near-depleted points entirely.",
    )
    parser.set_defaults(show_excluded_context=True)

    parser.add_argument(
        "--ai2d-unit",
        choices=("auto", "1/m", "1/px"),
        default="auto",
        help="Force input unit for a_i_2D (default: auto, median > 1e3 -> 1/m).",
    )
    parser.add_argument(
        "--interface-unit",
        choices=("auto", "px_length", "m_length", "px_area", "m_area"),
        default="auto",
        help=(
            "Input unit for InterfaceArea/L_ow. auto assumes px_length and converts "
            "to m when pixel size is known."
        ),
    )
    parser.add_argument(
        "--req-unit",
        choices=("auto", "px", "um"),
        default="auto",
        help=(
            "Input unit for ReqMedian. px converts to um when pixel size is known; "
            "um is kept unchanged."
        ),
    )
    parser.add_argument(
        "--fraction-kind",
        choices=("auto", "area", "count"),
        default="area",
        help="Interpret fracDroplets/fracColumns/fracClusters as area or count fractions (default: area).",
    )

    parser.add_argument(
        "--plot-set",
        default="stage,binned,trajectory",
        help="Comma-separated subset of plot kinds to emit.",
    )
    parser.add_argument(
        "--plot-normalized-rate",
        dest="plot_normalized_rate",
        action="store_true",
        help="Also emit normalized-rate (-dSn/dt / Sn) figures (default: off).",
    )
    parser.add_argument(
        "--no-plot-normalized-rate",
        dest="plot_normalized_rate",
        action="store_false",
        help="Disable normalized-rate figures.",
    )
    parser.set_defaults(plot_normalized_rate=False)

    parser.add_argument(
        "--n-bins",
        type=int,
        default=8,
        help="Number of quantile bins for binned-summary plots (default: 8).",
    )
    parser.add_argument(
        "--min-bin-count",
        type=int,
        default=20,
        help="Minimum sample count required to draw a binned summary point (default: 20).",
    )
    parser.add_argument(
        "--binned-stages",
        default="active_removal",
        help="Comma-separated stages used in binned summaries; or 'all'.",
    )
    parser.add_argument(
        "--max-scatter-points",
        type=int,
        default=3000,
        help="Maximum points per stage in stage scatter plots (default: 3000).",
    )
    parser.add_argument(
        "--max-trajectory-points",
        type=int,
        default=800,
        help="Maximum points in trajectory plots (default: 800).",
    )

    parser.add_argument(
        "--log-x",
        default="auto",
        help="Log-axis decision: 'auto' (per-metric), 'all', 'none', or comma-separated metrics.",
    )

    parser.add_argument(
        "--save-rates-csv",
        dest="save_rates_csv",
        action="store_true",
        help="Write dissolution_rates.csv with all derived rate columns (default: on).",
    )
    parser.add_argument(
        "--no-save-rates-csv",
        dest="save_rates_csv",
        action="store_false",
        help="Skip dissolution_rates.csv.",
    )
    parser.set_defaults(save_rates_csv=True)
    parser.add_argument(
        "--save-stats-csv",
        dest="save_stats_csv",
        action="store_true",
        help="Write rate_metric_associations.csv and rate_metric_binned_summary.csv (default: on).",
    )
    parser.add_argument(
        "--no-save-stats-csv",
        dest="save_stats_csv",
        action="store_false",
        help="Skip the supplementary statistics CSVs.",
    )
    parser.set_defaults(save_stats_csv=True)

    parser.add_argument(
        "--save-plot-data",
        dest="save_plot_data",
        action="store_true",
        help="Write one <stem>_data.xlsx per figure (default: on).",
    )
    parser.add_argument(
        "--no-save-plot-data",
        dest="save_plot_data",
        action="store_false",
        help="Skip per-figure Excel workbooks.",
    )
    parser.set_defaults(save_plot_data=True)

    return parser


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir)
    csv_path = find_timeseries_csv(output_dir, args.csv_path)
    figures_dir = Path(args.figures_dir) if args.figures_dir else output_dir / "figures_rate"

    df = load_rate_timeseries(csv_path)

    skip = args.skip_frames
    if skip > 0:
        if skip >= len(df) - 1:
            raise ValueError(
                f"--skip-frames {skip} would leave fewer than 2 rows out of {len(df)}"
            )
        df = df.iloc[skip:].reset_index(drop=True)

    if args.min_time_min is not None:
        df = filter_min_time(df, args.min_time_min)

    pixel_size_um = args.pixel_size_um
    pixel_size_source = "user-provided"
    if pixel_size_um is None:
        pixel_size_um = find_pixel_size_um(output_dir)
        pixel_size_source = "analysis_report.txt"

    if args.dt_seconds <= 0:
        raise ValueError("--dt-seconds must be positive")
    if args.rate_window_min <= 0:
        raise ValueError("--rate-window-min must be positive")
    if args.rate_min_points < 2:
        raise ValueError("--rate-min-points must be >= 2")
    if args.sn_smooth_window_frames < 1:
        raise ValueError("--sn-smooth-window-frames must be >= 1")
    if args.n_bins < 2:
        raise ValueError("--n-bins must be >= 2")
    if args.min_bin_count < 1:
        raise ValueError("--min-bin-count must be >= 1")
    if args.min_blobs_valid < 0:
        raise ValueError("--min-blobs-valid must be non-negative")
    if args.min_blob_area_px < 0:
        raise ValueError("--min-blob-area-px must be non-negative")
    if not (0.0 <= args.min_sn_norm_valid <= 1.0):
        raise ValueError("--min-sn-norm-valid must be in [0, 1]")

    df = attach_stage_and_masks(
        df,
        min_sn_norm_valid=args.min_sn_norm_valid,
        min_blobs_valid=args.min_blobs_valid,
    )
    df, topology_qc = attach_topology_fraction_qc(
        df,
        output_dir,
        min_blob_area_px=args.min_blob_area_px,
    )

    unit_info = infer_metric_units(df, args, pixel_size_um)

    attach_all_rates(
        df,
        movmedian_smooth_window=args.movmedian_window,
        dt_seconds=args.dt_seconds,
        rate_window_min=args.rate_window_min,
        rate_min_points=args.rate_min_points,
        sn_smooth_window_frames=args.sn_smooth_window_frames,
        monotone_sn_for_rate=args.monotone_sn_for_rate,
        pixel_size_um=pixel_size_um,
        unit_info=unit_info,
    )

    log_x_metrics = _parse_log_x(args.log_x)

    plot_set = tuple(item.strip() for item in args.plot_set.split(",") if item.strip())

    binned_stages_raw = args.binned_stages.strip()
    if binned_stages_raw.lower() == "all":
        binned_stages = tuple(STAGE_LABELS)
    else:
        binned_stages = tuple(item.strip() for item in binned_stages_raw.split(",") if item.strip())
    invalid_stages = sorted(set(binned_stages) - set(STAGE_LABELS))
    if invalid_stages:
        raise ValueError(
            f"Unknown stage(s) in --binned-stages: {invalid_stages}. "
            f"Allowed: {STAGE_LABELS} or 'all'"
        )

    fraction_kind = _resolve_fraction_kind(args, df)

    written, binned_rows = create_all_rate_figures(
        df,
        figures_dir=figures_dir,
        rate_method=args.rate_method,
        dpi=args.dpi,
        pixel_size_um=pixel_size_um,
        log_x_metrics=log_x_metrics,
        plot_set=plot_set,
        plot_normalized_rate=args.plot_normalized_rate,
        n_bins=args.n_bins,
        max_scatter_points=args.max_scatter_points,
        max_trajectory_points=args.max_trajectory_points,
        show_excluded_context=args.show_excluded_context,
        binned_stages=binned_stages,
        min_bin_count=args.min_bin_count,
        fraction_kind=fraction_kind,
        unit_info=unit_info,
        save_plot_data=args.save_plot_data,
    )

    figures_dir.mkdir(parents=True, exist_ok=True)
    unit_json_path = figures_dir / "rate_plot_unit_inference.json"
    with open(unit_json_path, "w", encoding="utf-8") as fp:
        json.dump(unit_info, fp, indent=2, ensure_ascii=False, default=_json_default)

    all_specs = _rate_metric_specs(df, fraction_kind, include_count_fractions=True)
    all_metric_keys = [s["key"] for s in all_specs]
    rate_col = RATE_METHOD_TO_COLUMN[args.rate_method]
    availability_path = figures_dir / "rate_plot_metric_availability.csv"
    pd.DataFrame(metric_availability_rows(df, all_specs, rate_col)).to_csv(
        availability_path, index=False
    )

    associations_path = None
    binned_csv_path = None
    if args.save_stats_csv:
        assoc_rows = compute_associations(df, all_metric_keys, rate_col, unit_info, pixel_size_um)
        associations_path = figures_dir / "rate_metric_associations.csv"
        pd.DataFrame(assoc_rows).to_csv(associations_path, index=False)
        binned_csv_path = figures_dir / "rate_metric_binned_summary.csv"
        pd.DataFrame(binned_rows, columns=BINNED_SUMMARY_COLUMNS).to_csv(
            binned_csv_path, index=False
        )

    rates_csv_path = None
    if args.save_rates_csv:
        rates_csv_path = figures_dir / "dissolution_rates.csv"
        rate_columns = [
            "RealTime_s", "Time_min", "Sn", "Sn_rate_input",
            "SnNorm", "Stage", "ValidStructure", "NearDepleted",
            "DissolutionRate_Sn_time_lr",
            "DissolutionRate_Sn_movmed",
            "DissolutionRate_Sn_lr",
            "NormalizedDissolutionRate_Sn_time_lr",
            "NormalizedDissolutionRate_Sn_movmed",
            "NormalizedDissolutionRate_Sn_lr",
            "MassTransferProxy_time_lr_per_pixel",
            "MassTransferProxy_movmed_per_pixel",
            "MassTransferProxy_lr_per_pixel",
        ]
        for optional in (
            "DissolutionRate_mass_kg_per_s",
            "DissolutionRate_per_projected_interface_length_kg_per_s_per_m",
        ):
            if optional in df.columns:
                rate_columns.append(optional)
        present = [c for c in rate_columns if c in df.columns]
        df.loc[:, present].to_csv(rates_csv_path, index=False)

    config_path = figures_dir / "rate_plot_config.json"
    config_payload = {
        "rate_method": args.rate_method,
        "rate_window_min": args.rate_window_min,
        "rate_min_points": args.rate_min_points,
        "sn_smooth_window_frames": args.sn_smooth_window_frames,
        "monotone_sn_for_rate": bool(args.monotone_sn_for_rate),
        "min_sn_norm_valid": args.min_sn_norm_valid,
        "min_blobs_valid": args.min_blobs_valid,
        "min_blob_area_px": args.min_blob_area_px,
        "topology_fraction_qc": topology_qc,
        "stage_thresholds": {
            "near_depleted": f"SnNorm < {args.min_sn_norm_valid:g}",
            "tail": f"{args.min_sn_norm_valid:g} <= SnNorm < 0.10",
            "active_removal": "0.10 <= SnNorm < 0.95",
            "induction_or_stable": "SnNorm >= 0.95",
        },
        "plot_set": list(plot_set),
        "log_x": args.log_x,
        "min_bin_count": args.min_bin_count,
        "fraction_kind": fraction_kind,
        "stage_counts": df["Stage"].value_counts(dropna=False).to_dict() if "Stage" in df.columns else {},
        "n_rows": int(len(df)),
        "n_valid_structure": int(np.count_nonzero(valid_interpretation_mask(df))),
        "unit_info": unit_info,
        "outputs": [str(path) for path in written],
    }
    with open(config_path, "w", encoding="utf-8") as fp:
        json.dump(config_payload, fp, indent=2, ensure_ascii=False, default=_json_default)

    print(f"Read: {csv_path}")
    print(f"Rows: {len(df)}")
    if pixel_size_um is not None:
        print(f"Pixel size: {pixel_size_um} μm/px (source: {pixel_size_source}).")
    else:
        print("Pixel size: not provided/auto-detected; areas/lengths kept in pixel units.")
    print(
        f"Rate method: {args.rate_method} "
        f"(window_min={args.rate_window_min:g}, min_points={args.rate_min_points}, "
        f"sn_smooth_frames={args.sn_smooth_window_frames}, "
        f"monotone={args.monotone_sn_for_rate})"
    )
    print(f"Stage thresholds: SnNorm>=0.95 induction, [0.10,0.95) active, "
          f"[{args.min_sn_norm_valid:g},0.10) tail, <{args.min_sn_norm_valid:g} near-depleted")
    print("Unit inference:")
    for key, info in unit_info.items():
        msg = (
            f"  {key}: input={info['input_unit']}, plot={info['plot_unit']}, "
            f"conversion={info['conversion']}"
        )
        if "median" in info and np.isfinite(info["median"]):
            msg += f", median={info['median']:g}"
        print(msg)
    print(f"Topology fraction kind: {fraction_kind}")
    print(f"Figures directory: {figures_dir}")
    print(f"Saved: {unit_json_path}")
    print(f"Saved: {availability_path}")
    print(f"Saved: {config_path}")
    if rates_csv_path is not None:
        print(f"Saved: {rates_csv_path}")
    if associations_path is not None:
        print(f"Saved: {associations_path}")
    if binned_csv_path is not None:
        print(f"Saved: {binned_csv_path}")
    for path in written:
        print(f"Saved: {path}")
    return 0


def _json_default(obj):
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serialisable")


if __name__ == "__main__":
    raise SystemExit(main())
