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


def _finalize_time_axis(ax, ylabel, log_scale=False):
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Time (min, log scale)" if log_scale else "Time (min)")
    if log_scale:
        ax.set_xscale("log")
    style_axes(ax)
    if log_scale:
        ax.grid(True, which="both", color="#E4E4E4", linewidth=0.55, alpha=0.7)


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
    _finalize_time_axis(ax, r"Specific interfacial area, $a_i^{2D}$", log_scale)


def plot_mean_circularity(ax, df, log_scale=False):
    _plot_line(
        ax,
        df,
        "MeanCircularity",
        "Mean circularity",
        WONG_COLORS["orange"],
        log_scale,
    )
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
    _finalize_time_axis(ax, "Cluster fraction", log_scale)


def plot_req_stats(ax, df, log_scale=False):
    series = [
        ("ReqMedian", "Median", WONG_COLORS["blue"]),
        ("ReqMean", "Mean", WONG_COLORS["vermillion"]),
        ("ReqStd", "Std", WONG_COLORS["bluish_green"]),
    ]
    for column, label, color in series:
        _plot_line(ax, df, column, label, color, log_scale)
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
    _finalize_time_axis(ax, "Interface area", log_scale)


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
]

DATA_EXPORTS = [
    (
        "timeseries_6panel",
        [
            "RealTime_s",
            "Time_min",
            "Sn",
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
            "fracDroplets",
            "fracColumns",
            "fracClusters",
        ],
    ),
    ("01_saturation_decay", ["RealTime_s", "Time_min", "Sn"]),
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
    ("09_mean_circularity", ["RealTime_s", "Time_min", "MeanCircularity"]),
    ("10_fraction_droplets", ["RealTime_s", "Time_min", "fracDroplets"]),
    ("11_fraction_columns", ["RealTime_s", "Time_min", "fracColumns"]),
    ("12_fraction_clusters", ["RealTime_s", "Time_min", "fracClusters"]),
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


def _prepare_plot_df(df, smooth_window, smooth_polyorder):
    plot_df = df.copy()
    if "DissolutionRate_per_min" not in plot_df.columns:
        plot_df["DissolutionRate_per_min"] = compute_dissolution_rate(
            plot_df,
            smooth_window=smooth_window,
            smooth_polyorder=smooth_polyorder,
        )
    if "MaxBlobFlowFrac" not in plot_df.columns:
        plot_df["MaxBlobFlowFrac"] = plot_df["Sn"] * plot_df["MaxBlobFrac"]
    return plot_df


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
):
    """Create combined and individual figures in linear and log x-axis variants."""
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

    written.extend(write_plot_data_workbooks(plot_df, figures_dir))
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
        help="Savitzky-Golay smoothing window for dissolution rate; use 0 to disable.",
    )
    parser.add_argument(
        "--smooth-polyorder",
        type=int,
        default=3,
        help="Savitzky-Golay smoothing polynomial order.",
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
