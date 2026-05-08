"""Create Nature-style time-series figures from microfluidics CSV output."""

from __future__ import annotations

import argparse
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
        candidates = sorted(output_dir.glob("*timeseries*.csv"))
    if not candidates:
        raise FileNotFoundError(f"No time-series CSV found in {output_dir}")
    if len(candidates) > 1:
        names = ", ".join(path.name for path in candidates)
        raise ValueError(f"Multiple time-series CSV files found; pass --csv explicitly: {names}")
    return candidates[0]


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

    df = df.sort_values("RealTime_s", kind="mergesort").reset_index(drop=True)
    if df["RealTime_s"].duplicated().any():
        duplicates = df.loc[df["RealTime_s"].duplicated(), "RealTime_s"].tolist()
        raise ValueError(f"Duplicate RealTime_s values are not allowed: {duplicates}")

    df["RealTime_s"] = df["RealTime_s"] - df["RealTime_s"].iloc[0]
    df["Time_min"] = df["RealTime_s"] / 60.0
    return df


def compute_dissolution_rate(df, smooth_window=101, smooth_polyorder=3):
    """Compute -dSn/dt in minutes, optionally smoothed with Savitzky-Golay."""
    time_min = pd.to_numeric(df["Time_min"], errors="coerce").to_numpy(dtype=float)
    saturation = pd.to_numeric(df["Sn"], errors="coerce").to_numpy(dtype=float)
    rate = -np.gradient(saturation, time_min)

    window = int(smooth_window or 0)
    polyorder = int(smooth_polyorder)
    if window > 1 and len(rate) >= 3:
        if window % 2 == 0:
            window += 1
        max_odd_window = len(rate) if len(rate) % 2 == 1 else len(rate) - 1
        window = min(window, max_odd_window)
        if window > polyorder and window >= 3:
            try:
                from scipy.signal import savgol_filter

                rate = savgol_filter(rate, window_length=window, polyorder=polyorder, mode="interp")
            except ImportError:
                pass

    return pd.Series(rate, index=df.index, name="DissolutionRate_per_min")


def configure_nature_style():
    """Apply compact Nature-style Matplotlib rcParams."""
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "font.size": 8.5,
            "axes.labelsize": 8.5,
            "axes.titlesize": 8.5,
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "legend.fontsize": 7.5,
            "axes.linewidth": 0.8,
            "axes.edgecolor": "#333333",
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
        ax.spines[side].set_linewidth(0.8)
        ax.spines[side].set_color("#333333")
    ax.tick_params(axis="both", which="both", direction="out", colors="#333333")
    ax.minorticks_on()
    ax.grid(True, which="major", color="#D9D9D9", linewidth=0.45, alpha=0.7)
    ax.set_axisbelow(True)
    return ax


def _markevery(df):
    return max(1, len(df) // 20)


def _x_and_y(df, column, log_scale=False):
    x = df["Time_min"].to_numpy(dtype=float)
    y = df[column].to_numpy(dtype=float)
    if log_scale and len(x) and np.any(x <= 0):
        finite_x = np.sort(np.unique(x[np.isfinite(x)]))
        adjacent_intervals = np.diff(finite_x)
        positive_intervals = adjacent_intervals[adjacent_intervals > 0]
        interval = np.min(positive_intervals) if len(positive_intervals) else 1.0
        synthetic_start = max(0.05 * interval, np.finfo(float).tiny)
        keep = x > 0
        x = np.concatenate(([synthetic_start], x[keep]))
        y = np.concatenate(([y[0]], y[keep]))
    return x, y


def _plot_line(ax, df, column, label, color, log_scale=False):
    x, y = _x_and_y(df, column, log_scale=log_scale)
    ax.plot(
        x,
        y,
        color=color,
        linewidth=LINEWIDTH,
        marker=MARKER,
        markersize=MARKER_SIZE,
        markerfacecolor="white",
        markeredgecolor=color,
        markeredgewidth=0.8,
        markevery=_markevery(df),
        label=label,
    )


def _finalize_time_axis(ax, ylabel, log_scale=False):
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Time (min, log scale)" if log_scale else "Time (min)")
    if log_scale:
        ax.set_xscale("log")
    style_axes(ax)
    if log_scale:
        ax.grid(True, which="both", color="#D9D9D9", linewidth=0.45, alpha=0.7)


def plot_sn(ax, df, log_scale=False):
    _plot_line(ax, df, "Sn", "Sn", WONG_COLORS["blue"], log_scale)
    _finalize_time_axis(ax, "Saturation, Sn", log_scale)


def plot_dissolution_rate(ax, df, log_scale=False):
    _plot_line(
        ax,
        df,
        "DissolutionRate_per_min",
        "Dissolution rate",
        WONG_COLORS["vermillion"],
        log_scale,
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
    _finalize_time_axis(ax, "Largest blob fraction", log_scale)


def plot_req_stats(ax, df, log_scale=False):
    series = [
        ("ReqMedian", "Median", WONG_COLORS["black"]),
        ("ReqMean", "Mean", WONG_COLORS["orange"]),
        ("ReqStd", "Std", WONG_COLORS["sky_blue"]),
    ]
    for column, label, color in series:
        _plot_line(ax, df, column, label, color, log_scale)
    _finalize_time_axis(ax, "Equivalent radius", log_scale)
    ax.legend(loc="best")


def plot_interface_area(ax, df, log_scale=False):
    _plot_line(
        ax,
        df,
        "InterfaceArea",
        "Interface area",
        WONG_COLORS["yellow"],
        log_scale,
    )
    _finalize_time_axis(ax, "Interface area", log_scale)


PLOTTERS = [
    ("01_saturation_decay", plot_sn),
    ("02_dissolution_rate", plot_dissolution_rate),
    ("03_blob_count", plot_num_blobs),
    ("04_largest_blob_fraction", plot_max_blob_frac),
    ("05_equivalent_radius_stats", plot_req_stats),
    ("06_interface_area", plot_interface_area),
]


def _save_figure(fig, stem, figures_dir, dpi):
    """Save one figure as PNG and SVG and return both paths."""
    figures_dir = Path(figures_dir)
    figures_dir.mkdir(parents=True, exist_ok=True)
    png_path = figures_dir / f"{stem}.png"
    svg_path = figures_dir / f"{stem}.svg"
    fig.savefig(png_path, dpi=dpi)
    fig.savefig(svg_path)
    return [png_path, svg_path]


def _prepare_plot_df(df, smooth_window, smooth_polyorder):
    plot_df = df.copy()
    if "DissolutionRate_per_min" not in plot_df.columns:
        plot_df["DissolutionRate_per_min"] = compute_dissolution_rate(
            plot_df,
            smooth_window=smooth_window,
            smooth_polyorder=smooth_polyorder,
        )
    return plot_df


def _create_combined_figure(df, log_scale=False):
    fig, axes = plt.subplots(3, 2, figsize=COMBINED_SIZE)
    for ax, (_, plotter) in zip(axes.ravel(), PLOTTERS):
        plotter(ax, df, log_scale=log_scale)
    fig.tight_layout(pad=0.8, w_pad=1.0, h_pad=1.0)
    return fig


def _create_individual_figure(df, plotter, log_scale=False):
    fig, ax = plt.subplots(figsize=INDIVIDUAL_SIZE)
    plotter(ax, df, log_scale=log_scale)
    fig.tight_layout(pad=0.6)
    return fig


def create_all_figures(
    df,
    figures_dir,
    dpi=600,
    smooth_window=101,
    smooth_polyorder=3,
):
    """Create 6-panel and individual figures in linear and log x-axis variants."""
    configure_nature_style()
    plot_df = _prepare_plot_df(df, smooth_window, smooth_polyorder)
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
    parser.add_argument("--dpi", type=int, default=600, help="PNG output DPI.")
    parser.add_argument(
        "--smooth-window",
        type=int,
        default=101,
        help="Savitzky-Golay smoothing window for dissolution rate; use 0 to disable.",
    )
    parser.add_argument(
        "--smooth-polyorder",
        type=int,
        default=3,
        help="Savitzky-Golay smoothing polynomial order.",
    )
    return parser


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir)
    csv_path = find_timeseries_csv(output_dir, args.csv_path)
    figures_dir = Path(args.figures_dir) if args.figures_dir else output_dir / "figures"
    df = load_timeseries(csv_path)
    written = create_all_figures(
        df,
        figures_dir=figures_dir,
        dpi=args.dpi,
        smooth_window=args.smooth_window,
        smooth_polyorder=args.smooth_polyorder,
    )
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
