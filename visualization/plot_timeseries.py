"""Create Nature-style time-series figures from microfluidics CSV output."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


REQUIRED_COLUMNS = [
    "RealTime_s",
    "Sn",
    "NumBlobs",
    "MaxBlobFrac",
    "ReqMedian",
    "ReqMean",
    "ReqStd",
    "InterfaceArea",
    "MeanCircularity",
    "a_i_2D",
    "fracDroplets",
    "fracColumns",
    "fracClusters",
]

WONG_COLORS = {
    "black": "#000000",
    "orange": "#E69F00",
    "sky_blue": "#56B4E9",
    "bluish_green": "#009E73",
    "yellow": "#F0E442",
    "blue": "#0072B2",
    "vermillion": "#D55E00",
    "reddish_purple": "#CC79A7",
}

MM_PER_INCH = 25.4
COMBINED_SIZE = (180 / MM_PER_INCH, 160 / MM_PER_INCH)
INDIVIDUAL_SIZE = (89 / MM_PER_INCH, 68 / MM_PER_INCH)
LINEWIDTH = 1.8
MARKER = "o"
MARKER_SIZE = 4.0
VALID_SN_THRESHOLD = 0.05
VALID_MIN_BLOB_COUNT = 20
VALID_AREA_THRESHOLD = 0.0
STAGE_COLORS = {
    "early": WONG_COLORS["blue"],
    "middle": WONG_COLORS["orange"],
    "late": WONG_COLORS["reddish_purple"],
    "near-depleted": "#999999",
}
STAGE_ORDER = ["early", "middle", "late", "near-depleted"]
REQ_TARGET_TIMES_MIN = (30, 70, 150, 300, 1000)


def find_timeseries_csv(output_dir, csv_path=None):
    """Find a time-series CSV in an output directory unless one is supplied."""
    if csv_path is not None:
        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {path}")
        return path

    output_dir = Path(output_dir)
    candidates = sorted(output_dir.glob("timeseries_realtime*.csv"))
    if not candidates:
        raise FileNotFoundError(f"No time-series CSV found in {output_dir}")
    return max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name))


_PIXEL_SIZE_UM_PATTERN = re.compile(
    r"Pixel\s*Size\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*(?:μm|um|µm)\s*/\s*px",
    flags=re.IGNORECASE,
)


def find_pixel_size_um(output_dir):
    """Auto-detect pixel size (μm/px) from analysis_report.txt; return None if absent."""
    report = Path(output_dir) / "analysis_report.txt"
    if not report.exists():
        return None
    text = report.read_text(encoding="utf-8", errors="replace")
    match = _PIXEL_SIZE_UM_PATTERN.search(text)
    if match is None:
        return None
    return float(match.group(1))


def load_timeseries(csv_path):
    """Load, validate, sort, and time-correct a time-series CSV."""
    csv_path = Path(csv_path)
    df = pd.read_csv(csv_path)

    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(missing)}")

    df = df.copy()
    for column in REQUIRED_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    invalid = [column for column in REQUIRED_COLUMNS if df[column].isna().any()]
    if invalid:
        raise ValueError(f"Non-numeric or missing values in column(s): {', '.join(invalid)}")

    nonfinite = [column for column in REQUIRED_COLUMNS if not np.isfinite(df[column]).all()]
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
    return df


def filter_min_time(df, min_time_min):
    """Keep rows at or after a minimum Time_min threshold."""
    if min_time_min is None:
        return df

    threshold = float(min_time_min)
    filtered = df.loc[df["Time_min"] >= threshold].reset_index(drop=True)
    if len(filtered) < 2:
        raise ValueError(
            f"--min-time-min {threshold:g} would leave fewer than 2 rows out of {len(df)}"
        )
    return filtered


def compute_raw_dissolution_rate(df):
    """Compute raw finite-difference -dSn/dt in minutes for QC exports."""
    time_min = pd.to_numeric(df["Time_min"], errors="coerce").to_numpy(dtype=float)
    saturation = pd.to_numeric(df["Sn"], errors="coerce").to_numpy(dtype=float)
    rate = np.zeros(len(saturation), dtype=float)
    if len(saturation) > 1:
        dt = np.diff(time_min)
        dsn = np.diff(saturation)
        with np.errstate(divide="ignore", invalid="ignore"):
            forward_rate = -(dsn / dt)
        rate[:-1] = forward_rate
        rate[-1] = forward_rate[-1]
    return pd.Series(rate, index=df.index, name="DissolutionRate_raw_per_min")


def _centered_rolling_median(values, window):
    values = pd.Series(values, dtype=float)
    window = int(window or 1)
    if window <= 1:
        return values.to_numpy(dtype=float)
    if window % 2 == 0:
        window += 1
    return (
        values.rolling(window=window, center=True, min_periods=1)
        .median()
        .to_numpy(dtype=float)
    )


def _rolling_local_linear_slope(time_min, values, window):
    """Return centered rolling OLS slopes dy/dt with asymmetric edge windows."""
    time_min = np.asarray(time_min, dtype=float)
    values = np.asarray(values, dtype=float)
    n = len(values)
    if n == 0:
        return np.array([], dtype=float)
    if n == 1:
        return np.array([0.0], dtype=float)

    window = int(window or 1)
    window = max(2, min(window, n))
    half = window // 2
    slopes = np.zeros(n, dtype=float)
    for i in range(n):
        start = max(0, i - half)
        end = min(n, start + window)
        start = max(0, end - window)
        x = time_min[start:end]
        y = values[start:end]
        finite = np.isfinite(x) & np.isfinite(y)
        x = x[finite]
        y = y[finite]
        if len(np.unique(x)) < 2:
            slopes[i] = 0.0
            continue
        slope, _intercept = np.polyfit(x, y, deg=1)
        slopes[i] = slope
    return slopes


def compute_rate_series(df, smooth_window=101, rate_lr_window=101):
    """Compute smooth, monotone Sn and publication-ready nonnegative rate."""
    time_min = pd.to_numeric(df["Time_min"], errors="coerce").to_numpy(dtype=float)
    saturation = pd.to_numeric(df["Sn"], errors="coerce").to_numpy(dtype=float)
    sn_smooth = _centered_rolling_median(saturation, smooth_window)
    sn_mono = np.minimum.accumulate(sn_smooth)
    slopes = _rolling_local_linear_slope(time_min, sn_mono, rate_lr_window)
    rate = np.maximum(-slopes, 0.0)
    return (
        pd.Series(sn_smooth, index=df.index, name="Sn_smooth_rate"),
        pd.Series(sn_mono, index=df.index, name="Sn_mono_rate"),
        pd.Series(rate, index=df.index, name="DissolutionRate_per_min"),
    )


def compute_dissolution_rate(df, smooth_window=101, smooth_polyorder=3, rate_lr_window=101):
    """Compute publication -dSn/dt using movmedian Sn, cummin, and local linear time."""
    _ = smooth_polyorder
    _sn_smooth, _sn_mono, rate = compute_rate_series(
        df,
        smooth_window=smooth_window,
        rate_lr_window=rate_lr_window,
    )
    return rate


def configure_nature_style():
    """Apply compact Nature-style Matplotlib rcParams."""
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "font.size": 8.5,
            "axes.labelsize": 9.5,
            "axes.titlesize": 8.5,
            "xtick.labelsize": 8.5,
            "ytick.labelsize": 8.5,
            "legend.fontsize": 8.0,
            "axes.linewidth": 0.8,
            "axes.edgecolor": "#333333",
            "lines.solid_capstyle": "round",
            "xtick.direction": "out",
            "ytick.direction": "out",
            "xtick.major.size": 3.0,
            "ytick.major.size": 3.0,
            "xtick.minor.size": 1.8,
            "ytick.minor.size": 1.8,
            "xtick.major.width": 0.8,
            "ytick.major.width": 0.8,
            "xtick.minor.width": 0.6,
            "ytick.minor.width": 0.6,
            "legend.frameon": False,
            "figure.dpi": 150,
            "savefig.dpi": 600,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.03,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
        }
    )


def style_axes(ax):
    """Apply common axis styling."""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for side in ("bottom", "left"):
        ax.spines[side].set_linewidth(0.9)
        ax.spines[side].set_color("#2B2B2B")
    ax.tick_params(
        axis="both",
        which="major",
        direction="out",
        colors="#2B2B2B",
        length=4.0,
        width=0.9,
    )
    ax.tick_params(
        axis="both",
        which="minor",
        direction="out",
        colors="#2B2B2B",
        length=2.2,
        width=0.6,
    )
    ax.minorticks_on()
    ax.grid(True, which="major", color="#E4E4E4", linewidth=0.55, alpha=0.7)
    ax.set_axisbelow(True)
    return ax


def _markevery(df):
    return max(1, len(df) // 20)


def _x_and_y(df, column, log_scale=False, synthetic_y="earliest"):
    x = df["Time_min"].to_numpy(dtype=float)
    y = df[column].to_numpy(dtype=float)
    if log_scale and len(x) and np.any(x <= 0):
        finite_mask = np.isfinite(x)
        finite_x = np.sort(np.unique(x[finite_mask]))
        adjacent_intervals = np.diff(finite_x)
        positive_intervals = adjacent_intervals[adjacent_intervals > 0]
        interval = np.min(positive_intervals) if len(positive_intervals) else 1.0
        synthetic_start = max(0.05 * interval, np.finfo(float).tiny)
        keep = x > 0
        if synthetic_y == "first_positive" and np.any(keep):
            positive_indices = np.flatnonzero(keep)
            synthetic_value = y[positive_indices[np.argmin(x[positive_indices])]]
        else:
            finite_indices = np.flatnonzero(finite_mask)
            synthetic_value = y[finite_indices[np.argmin(x[finite_indices])]]
        x = np.concatenate(([synthetic_start], x[keep]))
        y = np.concatenate(([synthetic_value], y[keep]))
    return x, y


def _plot_line(ax, df, column, label, color, log_scale=False, synthetic_y="earliest"):
    x, y = _x_and_y(df, column, log_scale=log_scale, synthetic_y=synthetic_y)
    ax.plot(
        x,
        y,
        color=color,
        linewidth=LINEWIDTH,
        marker=MARKER,
        markersize=MARKER_SIZE,
        markerfacecolor="white",
        markeredgecolor=color,
        markeredgewidth=1.0,
        markevery=_markevery(df),
        label=label,
    )


def _plot_invalid_points(ax, df, column, log_scale=False):
    if "ValidStructure" not in df.columns or column not in df.columns:
        return
    invalid = ~df["ValidStructure"].astype(bool)
    invalid = invalid & df[column].notna()
    if log_scale:
        invalid = invalid & (df["Time_min"] > 0)
    if not invalid.any():
        return
    ax.scatter(
        df.loc[invalid, "Time_min"],
        df.loc[invalid, column],
        s=18,
        color="#B0B0B0",
        edgecolors="white",
        linewidths=0.5,
        zorder=4,
        label="not used for architecture interpretation",
    )
    ax.legend(loc="best", frameon=False)


def _finalize_time_axis(ax, ylabel, log_scale=False):
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Time (min, log scale)" if log_scale else "Time (min)")
    if log_scale:
        ax.set_xscale("log")
    style_axes(ax)
    if log_scale:
        ax.grid(True, which="both", color="#E4E4E4", linewidth=0.55, alpha=0.7)


def plot_sn(ax, df, log_scale=False):
    column = "SnNorm" if "SnNorm" in df.columns else "Sn"
    _plot_line(ax, df, column, "Sn/Sn0" if column == "SnNorm" else "Sn", WONG_COLORS["blue"], log_scale)
    _finalize_time_axis(ax, "Sn/Sn0" if column == "SnNorm" else "Saturation, Sn", log_scale)


def plot_dissolution_rate(ax, df, log_scale=False):
    _plot_line(
        ax,
        df,
        "DissolutionRate_per_min",
        "Dissolution rate",
        WONG_COLORS["vermillion"],
        log_scale,
        synthetic_y="first_positive",
    )
    _finalize_time_axis(ax, "Dissolution rate (min$^{-1}$)", log_scale)


def plot_num_blobs(ax, df, log_scale=False):
    _plot_line(ax, df, "NumBlobs", "Blobs", WONG_COLORS["bluish_green"], log_scale)
    _finalize_time_axis(ax, "Number of blobs", log_scale)


def plot_max_blob_frac(ax, df, log_scale=False):
    _plot_line(
        ax,
        df,
        "MaxBlobFrac",
        "Largest blob fraction",
        WONG_COLORS["reddish_purple"],
        log_scale,
    )
    _plot_invalid_points(ax, df, "MaxBlobFrac", log_scale)
    _finalize_time_axis(ax, "Largest blob fraction", log_scale)


def plot_max_blob_flow_frac(ax, df, log_scale=False):
    _plot_line(
        ax,
        df,
        "MaxBlobFlowFrac",
        "Largest blob / flow-domain area",
        WONG_COLORS["sky_blue"],
        log_scale,
    )
    _plot_invalid_points(ax, df, "MaxBlobFlowFrac", log_scale)
    _finalize_time_axis(ax, "Amax / Aflow", log_scale)


def plot_ai_2d(ax, df, log_scale=False):
    _plot_line(
        ax,
        df,
        "a_i_2D",
        r"$a_i^{2D}$",
        WONG_COLORS["black"],
        log_scale,
    )
    _plot_invalid_points(ax, df, "a_i_2D", log_scale)
    _finalize_time_axis(ax, r"Specific interfacial area, $a_i^{2D}$", log_scale)


def plot_mean_circularity(ax, df, log_scale=False):
    if "MeanCircularity_valid" in df.columns and df["MeanCircularity_valid"].notna().any():
        _plot_line(
            ax,
            df,
            "MeanCircularity_raw",
            "Raw",
            "#A0A0A0",
            log_scale,
        )
        _plot_line(
            ax,
            df,
            "MeanCircularity_valid",
            "Valid",
            WONG_COLORS["orange"],
            log_scale,
        )
        ax.legend(loc="best", frameon=False)
    else:
        _plot_line(
            ax,
            df,
            "MeanCircularity",
            "Mean circularity",
            WONG_COLORS["orange"],
            log_scale,
        )
    _plot_invalid_points(ax, df, "MeanCircularity", log_scale)
    _finalize_time_axis(ax, "Mean circularity", log_scale)


def plot_frac_droplets(ax, df, log_scale=False):
    _plot_line(
        ax,
        df,
        "fracDroplets",
        "Droplets",
        WONG_COLORS["blue"],
        log_scale,
    )
    _plot_invalid_points(ax, df, "fracDroplets", log_scale)
    _finalize_time_axis(ax, "Droplet fraction", log_scale)


def plot_frac_columns(ax, df, log_scale=False):
    _plot_line(
        ax,
        df,
        "fracColumns",
        "Columns",
        WONG_COLORS["vermillion"],
        log_scale,
    )
    _plot_invalid_points(ax, df, "fracColumns", log_scale)
    _finalize_time_axis(ax, "Column fraction", log_scale)


def plot_frac_clusters(ax, df, log_scale=False):
    _plot_line(
        ax,
        df,
        "fracClusters",
        "Clusters",
        WONG_COLORS["bluish_green"],
        log_scale,
    )
    _plot_invalid_points(ax, df, "fracClusters", log_scale)
    _finalize_time_axis(ax, "Cluster fraction", log_scale)


def plot_req_stats(ax, df, log_scale=False):
    series = [
        ("ReqMedian", "Median", WONG_COLORS["blue"]),
        ("ReqMean", "Mean", WONG_COLORS["vermillion"]),
        ("ReqStd", "Std", WONG_COLORS["bluish_green"]),
    ]
    for column, label, color in series:
        _plot_line(ax, df, column, label, color, log_scale)
        _plot_invalid_points(ax, df, column, log_scale)
    unit = df.attrs.get("req_unit", "px")
    _finalize_time_axis(ax, f"Equivalent radius ({unit})", log_scale)
    ax.legend(
        loc="lower center",
        bbox_to_anchor=(0.5, 1.04),
        ncol=3,
        frameon=False,
        handlelength=1.6,
        handletextpad=0.4,
        columnspacing=1.2,
        borderaxespad=0.0,
    )


def apply_pixel_size_to_req(df, pixel_size_um):
    """Convert ReqMedian/Mean/Std from pixels to μm and tag the unit on df.attrs."""
    if pixel_size_um is None or pixel_size_um <= 0:
        df.attrs.setdefault("req_unit", "px")
        return df
    for col in ("ReqMedian", "ReqMean", "ReqStd"):
        df[col] = df[col] * float(pixel_size_um)
    df.attrs["req_unit"] = "μm"
    return df


def plot_interface_area(ax, df, log_scale=False):
    _plot_line(
        ax,
        df,
        "InterfaceArea",
        "Interface area",
        WONG_COLORS["orange"],
        log_scale,
    )
    _plot_invalid_points(ax, df, "InterfaceArea", log_scale)
    _finalize_time_axis(ax, "Interface area", log_scale)


def plot_sn_norm_ai_2d_overlay(ax, df, log_scale=False):
    _plot_line(ax, df, "SnNorm", "Sn/Sn0", WONG_COLORS["blue"], log_scale)
    _finalize_time_axis(ax, "Sn/Sn0", log_scale)

    ax2 = ax.twinx()
    x, y = _x_and_y(df, "a_i_2D", log_scale=log_scale)
    ax2.plot(
        x,
        y,
        color=WONG_COLORS["orange"],
        linewidth=LINEWIDTH,
        marker=MARKER,
        markersize=MARKER_SIZE,
        markerfacecolor="white",
        markeredgecolor=WONG_COLORS["orange"],
        markeredgewidth=1.0,
        markevery=_markevery(df),
        label=r"$a_i^{2D}$",
    )
    if log_scale:
        ax2.set_xscale("log")
    ax2.set_ylabel(r"$a_i^{2D}$")
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_linewidth(0.9)
    ax2.spines["right"].set_color("#2B2B2B")
    ax2.tick_params(axis="y", which="major", direction="out", colors="#2B2B2B", length=4.0, width=0.9)
    ax2.tick_params(axis="y", which="minor", direction="out", colors="#2B2B2B", length=2.2, width=0.6)
    ax2.minorticks_on()

    lines = ax.lines + ax2.lines
    ax.legend(lines, [line.get_label() for line in lines], loc="best", frameon=False)


def plot_rate_vs_ai_2d_stage(ax, df, log_scale=False):
    for stage in STAGE_ORDER:
        subset = df[df["DissolutionStage"] == stage]
        if subset.empty:
            continue
        x = subset["a_i_2D"].to_numpy(dtype=float)
        y = subset["DissolutionRate_per_min"].to_numpy(dtype=float)
        finite = np.isfinite(x) & np.isfinite(y)
        if log_scale:
            finite = finite & (x > 0)
        if not finite.any():
            continue
        ax.scatter(
            x[finite],
            y[finite],
            s=22,
            color=STAGE_COLORS[stage],
            edgecolors="white",
            linewidths=0.5,
            alpha=0.9,
            label=stage,
        )
    ax.set_xlabel(r"$a_i^{2D}$" + (" (log scale)" if log_scale else ""))
    ax.set_ylabel("Dissolution rate (min$^{-1}$)")
    if log_scale:
        ax.set_xscale("log")
    style_axes(ax)
    ax.legend(
        loc="lower center",
        bbox_to_anchor=(0.5, 1.04),
        ncol=2,
        frameon=False,
        handlelength=1.2,
        handletextpad=0.4,
        columnspacing=1.0,
        borderaxespad=0.0,
    )


PLOTTERS = [
    ("01_saturation_decay", plot_sn),
    ("02_dissolution_rate", plot_dissolution_rate),
    ("03_blob_count", plot_num_blobs),
    ("04_largest_blob_fraction", plot_max_blob_frac),
    ("05_equivalent_radius_stats", plot_req_stats),
    ("06_interface_area", plot_interface_area),
    ("07_largest_blob_flow_fraction", plot_max_blob_flow_frac),
    ("08_a_i_2D", plot_ai_2d),
    ("09_mean_circularity", plot_mean_circularity),
    ("10_fraction_droplets", plot_frac_droplets),
    ("11_fraction_columns", plot_frac_columns),
    ("12_fraction_clusters", plot_frac_clusters),
    ("13_sn_norm_ai_2D_overlay", plot_sn_norm_ai_2d_overlay),
    ("14_rate_vs_ai_2D_stage", plot_rate_vs_ai_2d_stage),
]

DATA_EXPORTS = [
    (
        "timeseries_6panel",
        [
            "FrameIndex",
            "RealTime_s",
            "Time_min",
            "Sn",
            "SnNorm",
            "DissolutionRate_raw_per_min",
            "Sn_smooth_rate",
            "Sn_mono_rate",
            "DissolutionRate_per_min",
            "NumBlobs",
            "MaxBlobFrac",
            "ReqMedian",
            "ReqMean",
            "ReqStd",
            "InterfaceArea",
            "MaxBlobFlowFrac",
            "a_i_2D",
            "MeanCircularity",
            "MeanCircularity_raw",
            "MeanCircularity_valid",
            "fracDroplets",
            "fracColumns",
            "fracClusters",
            "ValidStructure",
            "DissolutionStage",
        ],
    ),
    ("01_saturation_decay", ["RealTime_s", "Time_min", "Sn", "SnNorm"]),
    (
        "02_dissolution_rate",
        ["RealTime_s", "Time_min", "DissolutionRate_per_min"],
    ),
    ("03_blob_count", ["RealTime_s", "Time_min", "NumBlobs"]),
    ("04_largest_blob_fraction", ["RealTime_s", "Time_min", "MaxBlobFrac"]),
    (
        "05_equivalent_radius_stats",
        ["RealTime_s", "Time_min", "ReqMedian", "ReqMean", "ReqStd"],
    ),
    ("06_interface_area", ["RealTime_s", "Time_min", "InterfaceArea"]),
    (
        "07_largest_blob_flow_fraction",
        ["RealTime_s", "Time_min", "Sn", "MaxBlobFrac", "MaxBlobFlowFrac"],
    ),
    ("08_a_i_2D", ["RealTime_s", "Time_min", "a_i_2D"]),
    (
        "09_mean_circularity",
        ["RealTime_s", "Time_min", "MeanCircularity", "MeanCircularity_raw", "MeanCircularity_valid"],
    ),
    ("10_fraction_droplets", ["RealTime_s", "Time_min", "fracDroplets"]),
    ("11_fraction_columns", ["RealTime_s", "Time_min", "fracColumns"]),
    ("12_fraction_clusters", ["RealTime_s", "Time_min", "fracClusters"]),
    ("13_sn_norm_ai_2D_overlay", ["RealTime_s", "Time_min", "Sn", "SnNorm", "a_i_2D"]),
    (
        "14_rate_vs_ai_2D_stage",
        ["RealTime_s", "Time_min", "a_i_2D", "DissolutionRate_per_min", "DissolutionStage", "ValidStructure"],
    ),
]


def _save_figure(fig, stem, figures_dir, dpi):
    """Save one figure as PNG and SVG and return both paths."""
    figures_dir = Path(figures_dir)
    figures_dir.mkdir(parents=True, exist_ok=True)
    png_path = figures_dir / f"{stem}.png"
    svg_path = figures_dir / f"{stem}.svg"
    fig.savefig(png_path, dpi=dpi, facecolor="white")
    fig.savefig(svg_path, facecolor="white")
    return [png_path, svg_path]


def _write_data_workbook(df, stem, columns, figures_dir):
    """Write the data used by one linear plot to an Excel workbook."""
    figures_dir = Path(figures_dir)
    figures_dir.mkdir(parents=True, exist_ok=True)
    xlsx_path = figures_dir / f"{stem}_data.xlsx"
    data = df.loc[:, columns].copy()
    with pd.ExcelWriter(xlsx_path, engine="xlsxwriter") as writer:
        data.to_excel(writer, sheet_name="data", index=False)
        worksheet = writer.sheets["data"]
        worksheet.freeze_panes(1, 0)
        if len(columns):
            worksheet.autofilter(0, 0, len(data), len(columns) - 1)
        for index, column in enumerate(columns):
            width = min(max(len(column) + 2, 12), 28)
            worksheet.set_column(index, index, width)
    return xlsx_path


def write_plot_data_workbooks(df, figures_dir):
    """Write one data workbook per linear plot; log variants reuse the same data."""
    return [
        _write_data_workbook(df, stem, columns, figures_dir)
        for stem, columns in DATA_EXPORTS
    ]


def _sn0_from_series(sn):
    finite = pd.to_numeric(sn, errors="coerce")
    finite = finite[np.isfinite(finite)]
    if finite.empty:
        return 1.0
    positive = finite[finite > 0]
    if positive.empty:
        return max(float(finite.iloc[0]), np.finfo(float).eps)
    return float(positive.iloc[0])


def _stage_from_sn_norm(sn_norm):
    if not np.isfinite(sn_norm) or sn_norm < 0.05:
        return "near-depleted"
    if sn_norm < 0.25:
        return "late"
    if sn_norm < 0.75:
        return "middle"
    return "early"


def _prepare_plot_df(
    df,
    smooth_window,
    smooth_polyorder,
    rate_lr_window=101,
    valid_sn_threshold=VALID_SN_THRESHOLD,
    min_blob_count=VALID_MIN_BLOB_COUNT,
    area_threshold=VALID_AREA_THRESHOLD,
):
    plot_df = df.copy()
    if "FrameIndex" not in plot_df.columns:
        plot_df["FrameIndex"] = np.arange(1, len(plot_df) + 1)

    sn0 = _sn0_from_series(plot_df["Sn"])
    plot_df["SnNorm"] = plot_df["Sn"] / sn0
    plot_df["DissolutionRate_raw_per_min"] = compute_raw_dissolution_rate(plot_df)
    sn_smooth, sn_mono, rate = compute_rate_series(
        plot_df,
        smooth_window=smooth_window,
        rate_lr_window=rate_lr_window,
    )
    plot_df["Sn_smooth_rate"] = sn_smooth
    plot_df["Sn_mono_rate"] = sn_mono
    plot_df["DissolutionRate_per_min"] = rate
    if "MaxBlobFlowFrac" not in plot_df.columns:
        plot_df["MaxBlobFlowFrac"] = plot_df["Sn"] * plot_df["MaxBlobFrac"]
    if "MeanCircularity" in plot_df.columns:
        plot_df["MeanCircularity_raw"] = plot_df["MeanCircularity"]
    else:
        plot_df["MeanCircularity_raw"] = np.nan
        plot_df["MeanCircularity"] = np.nan
    if "MeanCircularity_valid" not in plot_df.columns:
        plot_df["MeanCircularity_valid"] = np.nan

    sn_ok = plot_df["SnNorm"] >= float(valid_sn_threshold)
    if "NumBlobs" in plot_df.columns:
        blob_ok = plot_df["NumBlobs"] >= int(min_blob_count)
    else:
        blob_ok = pd.Series(True, index=plot_df.index)
    if "TotalArea" in plot_df.columns:
        area_ok = plot_df["TotalArea"] >= float(area_threshold)
    else:
        area_ok = pd.Series(True, index=plot_df.index)
    plot_df["ValidStructure"] = (sn_ok & blob_ok & area_ok).astype(bool)
    plot_df["DissolutionStage"] = plot_df["SnNorm"].map(_stage_from_sn_norm)
    return plot_df


def find_blob_detail_csv(output_dir):
    if output_dir is None:
        return None
    path = Path(output_dir) / "blob_detail_all_frames.csv"
    return path if path.exists() else None


def _topology_label(value):
    text = str(value).strip().lower()
    if text.startswith("drop"):
        return "Droplets"
    if text.startswith("col"):
        return "Columns"
    if text.startswith("clust"):
        return "Clusters"
    return None


def _empty_topology_by_frame():
    return pd.DataFrame(
        columns=[
            "FrameIndex",
            "areaFracDroplets",
            "areaFracColumns",
            "areaFracClusters",
            "countFracDroplets",
            "countFracColumns",
            "countFracClusters",
        ]
    )


def _compute_topology_fractions(blob_detail, min_blob_area_px=20):
    required = {"FrameIndex", "Area", "TopologyType"}
    if not required.issubset(blob_detail.columns):
        return _empty_topology_by_frame()

    blobs = blob_detail.copy()
    blobs["Area"] = pd.to_numeric(blobs["Area"], errors="coerce")
    blobs["TopologyClass"] = blobs["TopologyType"].map(_topology_label)
    blobs = blobs[
        blobs["Area"].notna()
        & (blobs["Area"] >= float(min_blob_area_px))
        & blobs["TopologyClass"].notna()
    ]
    rows = []
    for frame_index, group in blobs.groupby("FrameIndex"):
        total_area = group["Area"].sum()
        total_count = len(group)
        row = {"FrameIndex": frame_index}
        for label in ("Droplets", "Columns", "Clusters"):
            subset = group[group["TopologyClass"] == label]
            row[f"areaFrac{label}"] = subset["Area"].sum() / total_area if total_area > 0 else np.nan
            row[f"countFrac{label}"] = len(subset) / total_count if total_count > 0 else np.nan
        rows.append(row)
    if not rows:
        return _empty_topology_by_frame()
    return pd.DataFrame(rows).sort_values("FrameIndex").reset_index(drop=True)


def _classify_existing_topology_fractions(timeseries, topology_by_frame):
    existing = ["fracDroplets", "fracColumns", "fracClusters"]
    if topology_by_frame.empty or not set(existing).issubset(timeseries.columns):
        return "ambiguous"
    merged = timeseries[["FrameIndex", *existing]].merge(
        topology_by_frame,
        on="FrameIndex",
        how="inner",
    )
    if merged.empty:
        return "ambiguous"

    area_cols = ["areaFracDroplets", "areaFracColumns", "areaFracClusters"]
    count_cols = ["countFracDroplets", "countFracColumns", "countFracClusters"]
    area_error = np.nanmean(np.abs(merged[existing].to_numpy() - merged[area_cols].to_numpy()))
    count_error = np.nanmean(np.abs(merged[existing].to_numpy() - merged[count_cols].to_numpy()))
    tolerance = 0.02
    if np.isfinite(area_error) and area_error <= tolerance and area_error < count_error:
        return "area-like"
    if np.isfinite(count_error) and count_error <= tolerance and count_error < area_error:
        return "count-like"
    return "ambiguous"


def apply_blob_detail_qc(timeseries, blob_detail, min_blob_area_px=20):
    """Attach valid circularity means and compute circularity/topology audit tables."""
    enriched = timeseries.copy()
    if "MeanCircularity" in enriched.columns:
        enriched["MeanCircularity_raw"] = enriched["MeanCircularity"]
    elif "MeanCircularity_raw" not in enriched.columns:
        enriched["MeanCircularity_raw"] = np.nan
    enriched["MeanCircularity_valid"] = np.nan

    blobs = blob_detail.copy()
    if "FrameIndex" not in blobs.columns:
        return enriched, {
            "circularity": {
                "status": pd.DataFrame({"Status": ["blob_detail_all_frames.csv lacks FrameIndex"]}),
                "gt1_blobs": pd.DataFrame(),
                "by_frame": pd.DataFrame(),
            },
            "topology": {
                "status": pd.DataFrame({"Status": ["blob_detail_all_frames.csv lacks FrameIndex"]}),
                "by_frame": _empty_topology_by_frame(),
                "classification": "ambiguous",
            },
        }

    for column in ("Area", "Perimeter", "Circularity", "EquivRadius", "EquivDiameter"):
        if column in blobs.columns:
            blobs[column] = pd.to_numeric(blobs[column], errors="coerce")

    frame_sn = enriched[["FrameIndex", "SnNorm"]].drop_duplicates("FrameIndex")
    blobs = blobs.merge(frame_sn, on="FrameIndex", how="left")

    valid_circularity = (
        blobs.get("Area", pd.Series(np.nan, index=blobs.index)) >= float(min_blob_area_px)
    )
    valid_circularity &= blobs.get("Perimeter", pd.Series(np.nan, index=blobs.index)) > 0
    valid_circularity &= blobs.get("Circularity", pd.Series(np.nan, index=blobs.index)) <= 1.05
    valid_circularity &= blobs["SnNorm"] > VALID_SN_THRESHOLD
    valid_means = blobs.loc[valid_circularity].groupby("FrameIndex")["Circularity"].mean()
    enriched["MeanCircularity_valid"] = enriched["FrameIndex"].map(valid_means)

    gt1_mask = blobs.get("Circularity", pd.Series(np.nan, index=blobs.index)) > 1.0
    if "Area" in blobs.columns:
        gt1_mask &= blobs["Area"] >= float(min_blob_area_px)
    gt1_blobs = blobs.loc[gt1_mask].copy()
    if not gt1_blobs.empty and "Area" in gt1_blobs.columns:
        gt1_blobs["AreaBin"] = pd.cut(
            gt1_blobs["Area"],
            bins=[0, 20, 50, 100, 250, 500, np.inf],
            labels=["0-20", "20-50", "50-100", "100-250", "250-500", ">500"],
            include_lowest=True,
        )
    if not gt1_blobs.empty:
        circularity_by_frame = (
            gt1_blobs.groupby("FrameIndex")
            .agg(
                NumCircularityGt1=("Circularity", "size"),
                MedianArea=("Area", "median"),
                MedianPerimeter=("Perimeter", "median"),
                MaxCircularity=("Circularity", "max"),
            )
            .reset_index()
        )
    else:
        circularity_by_frame = pd.DataFrame(
            columns=["FrameIndex", "NumCircularityGt1", "MedianArea", "MedianPerimeter", "MaxCircularity"]
        )

    topology_by_frame = _compute_topology_fractions(blobs, min_blob_area_px=min_blob_area_px)
    classification = _classify_existing_topology_fractions(enriched, topology_by_frame)
    topology_status = pd.DataFrame(
        {
            "Metric": ["Existing fracDroplets/fracColumns/fracClusters classification"],
            "Value": [classification],
        }
    )

    return enriched, {
        "circularity": {
            "gt1_blobs": gt1_blobs,
            "by_frame": circularity_by_frame,
        },
        "topology": {
            "by_frame": topology_by_frame,
            "classification": classification,
            "status": topology_status,
        },
    }


def selected_req_distribution_data(
    timeseries,
    blob_detail,
    target_times=REQ_TARGET_TIMES_MIN,
    min_blob_area_px=20,
):
    if blob_detail is None or blob_detail.empty:
        return pd.DataFrame()
    required = {"FrameIndex", "Area"}
    if not required.issubset(blob_detail.columns):
        return pd.DataFrame()

    times = timeseries[["FrameIndex", "Time_min"]].copy()
    blobs = blob_detail.copy()
    blobs["Area"] = pd.to_numeric(blobs["Area"], errors="coerce")
    for column in ("Perimeter", "Circularity", "EquivRadius", "EquivDiameter"):
        if column in blobs.columns:
            blobs[column] = pd.to_numeric(blobs[column], errors="coerce")

    rows = []
    for target in target_times:
        nearest_idx = (times["Time_min"] - float(target)).abs().idxmin()
        frame_index = times.loc[nearest_idx, "FrameIndex"]
        selected_time = times.loc[nearest_idx, "Time_min"]
        frame_blobs = blobs[(blobs["FrameIndex"] == frame_index) & (blobs["Area"] >= float(min_blob_area_px))].copy()
        if frame_blobs.empty:
            continue
        if "EquivRadius" in frame_blobs.columns:
            req = frame_blobs["EquivRadius"]
        elif "EquivDiameter" in frame_blobs.columns:
            req = frame_blobs["EquivDiameter"] / 2.0
        else:
            req = np.sqrt(frame_blobs["Area"] / np.pi)
        frame_blobs["Req"] = req
        frame_blobs["TargetTime_min"] = target
        frame_blobs["SelectedTime_min"] = selected_time
        rows.append(frame_blobs)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def _plot_req_distribution(req_data):
    fig, ax = plt.subplots(figsize=INDIVIDUAL_SIZE)
    target_order = list(dict.fromkeys(req_data["TargetTime_min"].tolist()))
    values = [
        req_data.loc[req_data["TargetTime_min"] == target, "Req"].dropna().to_numpy(dtype=float)
        for target in target_order
    ]
    positions = np.arange(1, len(values) + 1)
    usable = [value for value in values if len(value)]
    if usable:
        ax.violinplot(values, positions=positions, showmeans=False, showmedians=True)
        rng = np.random.default_rng(0)
        for pos, value in zip(positions, values):
            if len(value) == 0:
                continue
            jitter = rng.uniform(-0.06, 0.06, size=len(value))
            ax.scatter(
                np.full(len(value), pos) + jitter,
                value,
                s=12,
                color=WONG_COLORS["blue"],
                alpha=0.75,
                edgecolors="white",
                linewidths=0.3,
            )
    ax.set_xticks(positions)
    ax.set_xticklabels([f"{target:g}" for target in target_order])
    ax.set_xlabel("Target time (min)")
    ax.set_ylabel("Equivalent radius")
    style_axes(ax)
    fig.tight_layout(pad=0.6)
    return fig


def _architecture_from_row(row, prefix="frac"):
    candidates = {
        "droplets": row.get(f"{prefix}Droplets", np.nan),
        "columns": row.get(f"{prefix}Columns", np.nan),
        "clusters": row.get(f"{prefix}Clusters", np.nan),
    }
    finite = {key: value for key, value in candidates.items() if pd.notna(value)}
    if not finite:
        return "unknown"
    return max(finite, key=finite.get)


def _first_time_at_or_below(df, threshold):
    subset = df[df["SnNorm"] <= threshold]
    if subset.empty:
        return np.nan
    return float(subset.iloc[0]["Time_min"])


def create_summary_metrics(plot_df):
    metrics = []

    def add(metric, value):
        metrics.append({"Metric": metric, "Value": value})

    valid = plot_df[plot_df["ValidStructure"]]
    peak_rate_idx = plot_df["DissolutionRate_per_min"].idxmax()
    initial = plot_df.iloc[0]
    peak_rate = plot_df.loc[peak_rate_idx]
    tail = plot_df.iloc[-1]
    peak_blob_idx = plot_df["NumBlobs"].idxmax() if "NumBlobs" in plot_df.columns else plot_df.index[0]

    max_rate = plot_df["DissolutionRate_per_min"].max()
    onset_candidates = plot_df[plot_df["DissolutionRate_per_min"] >= max_rate * 0.05] if max_rate > 0 else pd.DataFrame()
    add("t_onset", float(onset_candidates.iloc[0]["Time_min"]) if not onset_candidates.empty else np.nan)
    add("t_peak_blob_count", float(plot_df.loc[peak_blob_idx, "Time_min"]))
    add("t_peak_rate", float(peak_rate["Time_min"]))
    add("t50", _first_time_at_or_below(plot_df, 0.50))
    add("t90", _first_time_at_or_below(plot_df, 0.10))
    add("t95", _first_time_at_or_below(plot_df, 0.05))
    add("Sn0", float(initial["Sn"]))
    add("FinalSn", float(tail["Sn"]))
    add("RemovalFraction", float(1.0 - tail["SnNorm"]))
    add("InitialNumBlobs", float(initial.get("NumBlobs", np.nan)))
    add("PeakNumBlobs", float(plot_df["NumBlobs"].max()) if "NumBlobs" in plot_df.columns else np.nan)
    add("InitialMaxBlobFrac", float(initial.get("MaxBlobFrac", np.nan)))
    add("InitialAmaxAflow", float(initial.get("MaxBlobFlowFrac", np.nan)))
    add("PeakAmaxAflow", float(plot_df["MaxBlobFlowFrac"].max()) if "MaxBlobFlowFrac" in plot_df.columns else np.nan)
    add("InitialInterfaceLength", float(initial.get("InterfaceArea", np.nan)))
    add("PeakInterfaceLength", float(plot_df["InterfaceArea"].max()) if "InterfaceArea" in plot_df.columns else np.nan)
    add("Initial_a_i_2D", float(initial.get("a_i_2D", np.nan)))
    add("Peak_a_i_2D", float(plot_df["a_i_2D"].max()) if "a_i_2D" in plot_df.columns else np.nan)
    add("ReliablePeak_a_i_2D", float(valid["a_i_2D"].max()) if not valid.empty and "a_i_2D" in valid else np.nan)
    add("InitialReqMedian", float(initial.get("ReqMedian", np.nan)))
    add("PeakReqMedian", float(plot_df["ReqMedian"].max()) if "ReqMedian" in plot_df.columns else np.nan)
    add("MinimumReqMedian_valid", float(valid["ReqMedian"].min()) if not valid.empty and "ReqMedian" in valid else np.nan)
    add("InitialMeanCircularity_raw", float(initial.get("MeanCircularity_raw", np.nan)))
    add(
        "PeakMeanCircularity_raw",
        float(plot_df["MeanCircularity_raw"].max()) if "MeanCircularity_raw" in plot_df.columns else np.nan,
    )
    add("InitialMeanCircularity_valid", float(initial.get("MeanCircularity_valid", np.nan)))
    add(
        "PeakMeanCircularity_valid",
        float(valid["MeanCircularity_valid"].max())
        if not valid.empty and valid["MeanCircularity_valid"].notna().any()
        else np.nan,
    )
    add("InitialAreaFracDroplets", float(initial.get("fracDroplets", np.nan)))
    add("InitialAreaFracColumns", float(initial.get("fracColumns", np.nan)))
    add("InitialAreaFracClusters", float(initial.get("fracClusters", np.nan)))
    add("PeakRateAreaFracDroplets", float(peak_rate.get("fracDroplets", np.nan)))
    add("PeakRateAreaFracColumns", float(peak_rate.get("fracColumns", np.nan)))
    add("PeakRateAreaFracClusters", float(peak_rate.get("fracClusters", np.nan)))
    add("StageAtPeakRate", peak_rate.get("DissolutionStage", "unknown"))
    add("ArchitectureInitial", _architecture_from_row(initial))
    add("ArchitectureMainStage", _architecture_from_row(peak_rate))
    add("ArchitectureTailLabel", _architecture_from_row(tail))
    return pd.DataFrame(metrics)


def _write_excel_sheets(path, sheets):
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        for sheet_name, data in sheets.items():
            data = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
            data.to_excel(writer, sheet_name=sheet_name[:31], index=False)
            worksheet = writer.sheets[sheet_name[:31]]
            if len(data.columns):
                worksheet.autofilter(0, 0, len(data), len(data.columns) - 1)
            for index, column in enumerate(data.columns):
                width = min(max(len(str(column)) + 2, 12), 32)
                worksheet.set_column(index, index, width)


def write_qc_workbooks(plot_df, qc, figures_dir):
    figures_dir = Path(figures_dir)
    figures_dir.mkdir(parents=True, exist_ok=True)
    written = []

    structure_cols = [
        column
        for column in [
            "FrameIndex",
            "RealTime_s",
            "Time_min",
            "Sn",
            "SnNorm",
            "NumBlobs",
            "ValidStructure",
            "DissolutionStage",
            "DissolutionRate_raw_per_min",
            "DissolutionRate_per_min",
            "a_i_2D",
            "MaxBlobFrac",
            "MaxBlobFlowFrac",
            "MeanCircularity_raw",
            "MeanCircularity_valid",
        ]
        if column in plot_df.columns
    ]
    structure_path = figures_dir / "structure_validity_qc.xlsx"
    _write_excel_sheets(structure_path, {"frame_qc": plot_df.loc[:, structure_cols].copy()})
    written.append(structure_path)

    circularity = qc.get("circularity", {})
    circularity_path = figures_dir / "circularity_gt1_audit.xlsx"
    circularity_sheets = {
        "gt1_blobs": circularity.get("gt1_blobs", pd.DataFrame()),
        "by_frame": circularity.get("by_frame", pd.DataFrame()),
    }
    if "status" in circularity:
        circularity_sheets["status"] = circularity["status"]
    _write_excel_sheets(circularity_path, circularity_sheets)
    written.append(circularity_path)

    topology = qc.get("topology", {})
    topology_path = figures_dir / "topology_fraction_audit.xlsx"
    topology_sheets = {
        "by_frame": topology.get("by_frame", _empty_topology_by_frame()),
        "status": topology.get(
            "status",
            pd.DataFrame({"Metric": ["classification"], "Value": [topology.get("classification", "ambiguous")]}),
        ),
    }
    _write_excel_sheets(topology_path, topology_sheets)
    written.append(topology_path)

    summary_path = figures_dir / "summary_metrics.xlsx"
    _write_excel_sheets(summary_path, {"summary": create_summary_metrics(plot_df)})
    written.append(summary_path)
    return written


def _create_combined_figure(df, log_scale=False):
    n_cols = 2
    n_rows = int(np.ceil(len(PLOTTERS) / n_cols))
    width, height = COMBINED_SIZE
    fig_height = max(height, n_rows * 45 / MM_PER_INCH)
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(width, fig_height))
    axes = np.asarray(axes).ravel()
    for ax, (_, plotter) in zip(axes, PLOTTERS):
        plotter(ax, df, log_scale=log_scale)
    for ax in axes[len(PLOTTERS):]:
        ax.set_visible(False)
    fig.tight_layout(pad=0.8, w_pad=1.0, h_pad=1.8)
    return fig


def _create_individual_figure(df, plotter, log_scale=False):
    fig, ax = plt.subplots(figsize=INDIVIDUAL_SIZE)
    plotter(ax, df, log_scale=log_scale)
    fig.tight_layout(pad=0.6)
    return fig


def create_all_figures(
    df,
    figures_dir,
    dpi=300,
    smooth_window=101,
    smooth_polyorder=3,
    rate_lr_window=101,
    output_dir=None,
    min_blob_area_px=20,
    valid_sn_threshold=VALID_SN_THRESHOLD,
    min_blob_count=VALID_MIN_BLOB_COUNT,
    area_threshold=VALID_AREA_THRESHOLD,
):
    """Create combined and individual figures in linear and log x-axis variants."""
    configure_nature_style()
    plot_df = _prepare_plot_df(
        df,
        smooth_window,
        smooth_polyorder,
        rate_lr_window=rate_lr_window,
        valid_sn_threshold=valid_sn_threshold,
        min_blob_count=min_blob_count,
        area_threshold=area_threshold,
    )
    blob_detail = None
    blob_detail_path = find_blob_detail_csv(output_dir)
    if blob_detail_path is not None:
        blob_detail = pd.read_csv(blob_detail_path)
        plot_df, qc = apply_blob_detail_qc(
            plot_df,
            blob_detail,
            min_blob_area_px=min_blob_area_px,
        )
    else:
        message = "blob_detail_all_frames.csv not found; skipped Req distribution and blob-detail audits"
        qc = {
            "circularity": {
                "status": pd.DataFrame({"Status": [message]}),
                "gt1_blobs": pd.DataFrame(),
                "by_frame": pd.DataFrame(),
            },
            "topology": {
                "status": pd.DataFrame({"Status": [message], "classification": ["ambiguous"]}),
                "by_frame": _empty_topology_by_frame(),
                "classification": "ambiguous",
            },
        }
    written = []

    for log_scale in (False, True):
        suffix = "_log" if log_scale else ""
        fig = _create_combined_figure(plot_df, log_scale=log_scale)
        written.extend(_save_figure(fig, f"timeseries_6panel{suffix}", figures_dir, dpi))
        plt.close(fig)

        for stem, plotter in PLOTTERS:
            fig = _create_individual_figure(plot_df, plotter, log_scale=log_scale)
            written.extend(_save_figure(fig, f"{stem}{suffix}", figures_dir, dpi))
            plt.close(fig)

    if blob_detail is not None:
        req_data = selected_req_distribution_data(
            plot_df,
            blob_detail,
            target_times=REQ_TARGET_TIMES_MIN,
            min_blob_area_px=min_blob_area_px,
        )
        if not req_data.empty:
            fig = _plot_req_distribution(req_data)
            written.extend(_save_figure(fig, "15_req_distribution", figures_dir, dpi))
            plt.close(fig)

    written.extend(write_plot_data_workbooks(plot_df, figures_dir))
    written.extend(write_qc_workbooks(plot_df, qc, figures_dir))
    return written


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Create Nature-style time-series figures from pipeline CSV output."
    )
    parser.add_argument("output_dir", help="Pipeline output directory containing the time-series CSV.")
    parser.add_argument("--csv", dest="csv_path", help="Explicit path to the time-series CSV.")
    parser.add_argument(
        "--figures-dir",
        help="Directory for generated figures. Defaults to <output_dir>/figures.",
    )
    parser.add_argument("--dpi", type=int, default=300, help="PNG output DPI.")
    parser.add_argument(
        "--smooth-window",
        type=int,
        default=101,
        help="Centered moving-median window for publication dissolution rate; use 1 to disable.",
    )
    parser.add_argument(
        "--smooth-polyorder",
        type=int,
        default=3,
        help="Compatibility argument retained from the old Savitzky-Golay rate; no longer drives publication rate.",
    )
    parser.add_argument(
        "--rate-lr-window",
        type=int,
        default=101,
        help="Centered local-linear window for monotone publication dissolution rate.",
    )
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
        help="Minimum Time_min to include after skipped frames (e.g. 1 to start plots at 1 min).",
    )
    parser.add_argument(
        "--pixel-size-um",
        type=float,
        default=None,
        help=(
            "Pixel size in micrometres per pixel. Used to convert ReqMedian/Mean/Std "
            "to μm. If omitted, auto-detected from analysis_report.txt; if neither is "
            "available, equivalent radius stays in pixels."
        ),
    )
    parser.add_argument(
        "--min-blob-area-px",
        type=float,
        default=20,
        help="Minimum blob area in pixels for valid circularity and selected Req distribution QC.",
    )
    return parser


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir)
    csv_path = find_timeseries_csv(output_dir, args.csv_path)
    figures_dir = Path(args.figures_dir) if args.figures_dir else output_dir / "figures"
    df = load_timeseries(csv_path)
    skip = args.skip_frames
    if skip > 0:
        if skip >= len(df) - 1:
            raise ValueError(
                f"--skip-frames {skip} would leave fewer than 2 rows out of {len(df)}"
            )
        df = df.iloc[skip:].reset_index(drop=True)
    df = filter_min_time(df, args.min_time_min)

    pixel_size_um = args.pixel_size_um
    pixel_size_source = "user-provided"
    if pixel_size_um is None:
        pixel_size_um = find_pixel_size_um(output_dir)
        pixel_size_source = "analysis_report.txt"
    df = apply_pixel_size_to_req(df, pixel_size_um)

    written = create_all_figures(
        df,
        figures_dir=figures_dir,
        dpi=args.dpi,
        smooth_window=args.smooth_window,
        smooth_polyorder=args.smooth_polyorder,
        rate_lr_window=args.rate_lr_window,
        output_dir=output_dir,
        min_blob_area_px=args.min_blob_area_px,
    )
    print(f"Read: {csv_path}")
    print(f"Rows: {len(df)}")
    if pixel_size_um is not None:
        print(f"Pixel size: {pixel_size_um} μm/px (source: {pixel_size_source}); Req* converted to μm.")
    else:
        print("Pixel size: not provided/auto-detected; Req* kept in pixels.")
    print(f"Figures directory: {figures_dir}")
    for path in written:
        print(f"Saved: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
