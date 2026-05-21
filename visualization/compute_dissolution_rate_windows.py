"""Compute dissolution-rate curves using fixed time or PV windows.

This standalone helper reads the pipeline time-series CSV, recomputes
dissolution rate from Sn vs Time_min or Sn vs PV for several physical windows,
and writes an Excel workbook plus linear/log comparison figures.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from plot_timeseries import (
    INDIVIDUAL_SIZE,
    LINEWIDTH,
    MARKER,
    MARKER_SIZE,
    WONG_COLORS,
    configure_nature_style,
    filter_min_time,
    find_timeseries_csv,
    load_timeseries,
    style_axes,
)


DEFAULT_WINDOWS_MIN = (0.5, 1.0, 3.0, 5.0)
PV_CANDIDATE_COLUMNS = (
    "PV",
    "X",
    "PV_since_onset",
    "PV_original",
    "PV_from_RealTime_s",
    "PV_from_Time_min",
    "PoreVolume",
    "PoreVolumes",
    "InjectedPV",
    "PV_injected",
    "PoreVolumeInjected",
    "PoreVolume_Injected",
)
NUMBER_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")


def parse_windows(text):
    if text is None:
        return list(DEFAULT_WINDOWS_MIN)
    windows = []
    for item in str(text).split(","):
        item = item.strip()
        if not item:
            continue
        value = float(item)
        if value <= 0:
            raise ValueError("Rate windows must be positive minutes")
        windows.append(value)
    if not windows:
        raise ValueError("At least one rate window is required")
    return windows


def window_label(window_value, unit_label):
    return f"{window_value:g}".replace(".", "p") + unit_label


def centered_rolling_median(x_values, values, window_value):
    x_values = np.asarray(x_values, dtype=float)
    values = np.asarray(values, dtype=float)
    out = np.full(len(values), np.nan, dtype=float)
    if len(values) == 0:
        return out
    half = float(window_value) / 2.0
    for i, x_value in enumerate(x_values):
        start = np.searchsorted(x_values, x_value - half, side="left")
        end = np.searchsorted(x_values, x_value + half, side="right")
        if end - start < 1:
            start, end = i, i + 1
        window_values = values[start:end]
        window_values = window_values[np.isfinite(window_values)]
        if len(window_values):
            out[i] = np.median(window_values)
    return out


def local_linear_rate(x_values, values, window_value):
    """Return max(-dSn/dx, 0) from local linear fits over an x-window."""
    x_values = np.asarray(x_values, dtype=float)
    values = np.asarray(values, dtype=float)
    rate = np.full(len(values), np.nan, dtype=float)
    if len(values) < 2:
        return rate

    half = float(window_value) / 2.0
    for i, x_value in enumerate(x_values):
        start = np.searchsorted(x_values, x_value - half, side="left")
        end = np.searchsorted(x_values, x_value + half, side="right")

        if end - start < 2:
            if i == 0:
                end = np.searchsorted(x_values, x_values[0] + window_value, side="right")
            elif i == len(x_values) - 1:
                start = np.searchsorted(x_values, x_values[-1] - window_value, side="left")
            else:
                start = max(0, i - 1)
                end = min(len(x_values), i + 2)

        x = x_values[start:end]
        y = values[start:end]
        finite = np.isfinite(x) & np.isfinite(y)
        x = x[finite]
        y = y[finite]
        if len(np.unique(x)) < 2:
            continue
        slope, _intercept = np.polyfit(x, y, deg=1)
        rate[i] = max(-float(slope), 0.0)
    return rate


def raw_centered_difference_rate(x_values, saturation, window_value):
    """Return -dSn/dx over a centered x interval using interpolation."""
    x_values = np.asarray(x_values, dtype=float)
    saturation = np.asarray(saturation, dtype=float)
    rate = np.full(len(saturation), np.nan, dtype=float)
    if len(saturation) < 2:
        return rate
    half = float(window_value) / 2.0
    finite = np.isfinite(x_values) & np.isfinite(saturation)
    x = x_values[finite]
    y = saturation[finite]
    if len(np.unique(x)) < 2:
        return rate
    for i, x_value in enumerate(x_values):
        left = x_value - half
        right = x_value + half
        if left < x[0] or right > x[-1]:
            continue
        y_left = np.interp(left, x, y)
        y_right = np.interp(right, x, y)
        rate[i] = -((y_right - y_left) / float(window_value))
    return rate


def _first_number(text):
    match = NUMBER_RE.search(str(text))
    if not match:
        return None
    return float(match.group(0))


def _pore_volume_to_ul(value, line):
    lower = str(line).lower()
    if "m^3" in lower or "m3" in lower:
        return float(value) * 1e9
    if "mm^3" in lower or "mm3" in lower or "µl" in lower or "μl" in lower or "ul" in lower:
        return float(value)
    if "ml" in lower:
        return float(value) * 1000.0
    return float(value)


def find_pore_volume_ul(output_dir, pore_volume_ul=None):
    if pore_volume_ul is not None:
        if pore_volume_ul <= 0:
            raise ValueError("--pore-volume-ul must be positive")
        return float(pore_volume_ul), "user-provided"

    report = Path(output_dir) / "analysis_report.txt" if output_dir is not None else None
    if report is None or not report.exists():
        return None, "missing"
    for line in report.read_text(encoding="utf-8", errors="replace").splitlines():
        label = line.lower()
        if "flow domain pore volume" in label or "pore volume" in label:
            value = _first_number(line)
            if value is not None:
                return _pore_volume_to_ul(value, line), str(report)
    return None, "not-found"


def compute_pv_from_flow(df, output_dir, flow_rate_ul_min, pore_volume_ul=None):
    if flow_rate_ul_min is None:
        raise ValueError(
            "No PV column found. Provide --flow-rate-ul-min so PV can be computed as "
            "Q(µL/min) * RealTime_s / 60 / Vpore(µL), or provide --pv-column."
        )
    if flow_rate_ul_min <= 0:
        raise ValueError("--flow-rate-ul-min must be positive")
    if "RealTime_s" not in df.columns:
        raise ValueError("Cannot compute PV without RealTime_s")

    vpore_ul, source = find_pore_volume_ul(output_dir, pore_volume_ul=pore_volume_ul)
    if vpore_ul is None or vpore_ul <= 0:
        raise ValueError(
            "Could not determine Flow Domain Pore Volume. Provide --pore-volume-ul "
            "or ensure analysis_report.txt contains 'Flow Domain Pore Volume'."
        )
    time_s = pd.to_numeric(df["RealTime_s"], errors="coerce").to_numpy(dtype=float)
    pv = float(flow_rate_ul_min) * time_s / 60.0 / float(vpore_ul)
    metadata = {
        "source": "computed_from_flow_rate_and_realtime",
        "formula": "PV = flow_rate_ul_min * RealTime_s / 60 / pore_volume_ul",
        "flow_rate_ul_min": float(flow_rate_ul_min),
        "pore_volume_ul": float(vpore_ul),
        "pore_volume_source": source,
        "pv_min": float(np.nanmin(pv)) if np.any(np.isfinite(pv)) else None,
        "pv_max": float(np.nanmax(pv)) if np.any(np.isfinite(pv)) else None,
    }
    return "PV_from_RealTime_s", pv, metadata


def resolve_x_axis(
    df,
    x_axis="time",
    pv_column="auto",
    pv_per_min=None,
    output_dir=None,
    flow_rate_ul_min=None,
    pore_volume_ul=None,
):
    if x_axis == "time":
        return "Time_min", "min", "per_min", "Time (min)", pd.to_numeric(
            df["Time_min"], errors="coerce"
        ).to_numpy(dtype=float), {"source": "Time_min"}

    columns = set(df.columns)
    selected = None
    if pv_column and pv_column != "auto":
        if pv_column not in columns:
            raise ValueError(f"Requested PV column not found: {pv_column}")
        selected = pv_column
    else:
        selected = next((col for col in PV_CANDIDATE_COLUMNS if col in columns), None)

    if selected is not None:
        pv = pd.to_numeric(df[selected], errors="coerce").to_numpy(dtype=float)
        return selected, "PV", "per_PV", "PV", pv, {"source": "csv_column", "column": selected}

    if flow_rate_ul_min is not None:
        x_col, pv, metadata = compute_pv_from_flow(
            df,
            output_dir=output_dir,
            flow_rate_ul_min=flow_rate_ul_min,
            pore_volume_ul=pore_volume_ul,
        )
        return x_col, "PV", "per_PV", "PV", pv, metadata

    if pv_per_min is None:
        raise ValueError(
            "No PV column found. Provide --flow-rate-ul-min, --pv-column, or --pv-per-min "
            "to use --x-axis pv."
        )
    pv = pd.to_numeric(df["Time_min"], errors="coerce").to_numpy(dtype=float) * float(pv_per_min)
    return "PV_from_Time_min", "PV", "per_PV", "PV", pv, {
        "source": "computed_from_pv_per_min",
        "formula": "PV = Time_min * pv_per_min",
        "pv_per_min": float(pv_per_min),
    }


def compute_window_rates(
    df,
    windows,
    x_axis="time",
    pv_column="auto",
    pv_per_min=None,
    output_dir=None,
    flow_rate_ul_min=None,
    pore_volume_ul=None,
):
    x_col, window_unit, rate_unit, _xlabel, x_values, metadata = resolve_x_axis(
        df,
        x_axis=x_axis,
        pv_column=pv_column,
        pv_per_min=pv_per_min,
        output_dir=output_dir,
        flow_rate_ul_min=flow_rate_ul_min,
        pore_volume_ul=pore_volume_ul,
    )
    keep_cols = [col for col in ("RealTime_s", "Time_min", "Sn") if col in df.columns]
    out = df[keep_cols].copy()
    out[x_col] = x_values
    saturation = pd.to_numeric(df["Sn"], errors="coerce").to_numpy(dtype=float)

    for window_value in windows:
        label = window_label(window_value, window_unit)
        sn_smooth = centered_rolling_median(x_values, saturation, window_value)
        sn_mono = np.minimum.accumulate(sn_smooth)
        out[f"SnSmooth_{label}"] = sn_smooth
        out[f"SnMono_{label}"] = sn_mono
        out[f"RateLR_{label}_{rate_unit}"] = local_linear_rate(x_values, sn_mono, window_value)
        out[f"RateRawCentral_{label}_{rate_unit}"] = raw_centered_difference_rate(
            x_values, saturation, window_value
        )
    return out, metadata


def plot_rate_windows(
    rate_df,
    windows,
    out_dir,
    x_axis="time",
    pv_column="auto",
    pv_per_min=None,
    output_dir=None,
    flow_rate_ul_min=None,
    pore_volume_ul=None,
    dpi=300,
):
    configure_nature_style()
    x_col, window_unit, rate_unit, xlabel, _x_values, _metadata = resolve_x_axis(
        rate_df,
        x_axis=x_axis,
        pv_column=pv_column,
        pv_per_min=pv_per_min,
        output_dir=output_dir,
        flow_rate_ul_min=flow_rate_ul_min,
        pore_volume_ul=pore_volume_ul,
    )
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    colors = [
        WONG_COLORS["blue"],
        WONG_COLORS["vermillion"],
        WONG_COLORS["bluish_green"],
        WONG_COLORS["reddish_purple"],
        WONG_COLORS["orange"],
        WONG_COLORS["sky_blue"],
    ]
    written = []
    for log_scale in (False, True):
        fig, ax = plt.subplots(figsize=INDIVIDUAL_SIZE)
        x_values = rate_df[x_col].to_numpy(dtype=float)
        for idx, window_value in enumerate(windows):
            label = window_label(window_value, window_unit)
            column = f"RateLR_{label}_{rate_unit}"
            y = rate_df[column].to_numpy(dtype=float)
            mask = np.isfinite(x_values) & np.isfinite(y)
            if log_scale:
                mask &= x_values > 0
            if not np.any(mask):
                continue
            x_plot = x_values[mask]
            y_plot = y[mask]
            ax.plot(
                x_plot,
                y_plot,
                color=colors[idx % len(colors)],
                linewidth=LINEWIDTH,
                marker=MARKER,
                markersize=MARKER_SIZE,
                markerfacecolor="white",
                markeredgecolor=colors[idx % len(colors)],
                markeredgewidth=1.0,
                markevery=max(1, len(x_plot) // 20),
                label=f"{window_value:g} {window_unit}",
            )
        ax.set_xlabel(f"{xlabel} (log scale)" if log_scale else xlabel)
        ax.set_ylabel("Dissolution rate (min$^{-1}$)" if rate_unit == "per_min" else "Dissolution rate (PV$^{-1}$)")
        if log_scale:
            ax.set_xscale("log")
        style_axes(ax)
        if log_scale:
            ax.grid(True, which="both", color="#E4E4E4", linewidth=0.55, alpha=0.7)
        ax.legend(
            loc="lower center",
            bbox_to_anchor=(0.5, 1.04),
            ncol=min(len(windows), 4),
            frameon=False,
            handlelength=1.6,
            handletextpad=0.4,
            columnspacing=1.2,
            borderaxespad=0.0,
        )
        fig.tight_layout(pad=0.6)
        axis_suffix = "" if x_axis == "time" else "_pv"
        suffix = "_log" if log_scale else ""
        png = out_dir / f"02_dissolution_rate_windows{axis_suffix}{suffix}.png"
        svg = out_dir / f"02_dissolution_rate_windows{axis_suffix}{suffix}.svg"
        fig.savefig(png, dpi=dpi, facecolor="white")
        fig.savefig(svg, facecolor="white")
        plt.close(fig)
        written.extend([png, svg])
    return written


def write_rate_workbook(rate_df, out_dir, x_axis="time"):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    axis_suffix = "" if x_axis == "time" else "_pv"
    path = out_dir / f"02_dissolution_rate_windows{axis_suffix}_data.xlsx"
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        rate_df.to_excel(writer, sheet_name="data", index=False)
        worksheet = writer.sheets["data"]
        worksheet.freeze_panes(1, 0)
        for idx, column in enumerate(rate_df.columns):
            width = min(max(len(str(column)) + 2, 12), 34)
            worksheet.set_column(idx, idx, width)
    return path


def write_pv_metadata(metadata, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "pv_conversion_metadata.json"
    path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Compute dissolution-rate curves using fixed time windows."
    )
    parser.add_argument("output_dir", help="Pipeline output directory containing time-series CSV.")
    parser.add_argument("--csv", dest="csv_path", help="Explicit time-series CSV path.")
    parser.add_argument(
        "--figures-dir",
        help="Output directory. Defaults to <output_dir>/figures.",
    )
    parser.add_argument(
        "--windows-min",
        default="0.5,1,3,5",
        help="Comma-separated rate windows in minutes. Default: 0.5,1,3,5.",
    )
    parser.add_argument(
        "--windows-pv",
        default=None,
        help="Comma-separated rate windows in PV units when --x-axis pv. Defaults to --windows-min values interpreted as PV.",
    )
    parser.add_argument(
        "--x-axis",
        choices=["time", "pv"],
        default="time",
        help="Coordinate used for derivatives and plots. Run once for time and once for PV.",
    )
    parser.add_argument(
        "--pv-column",
        default="auto",
        help="PV column name, or auto to try common names. Used only with --x-axis pv.",
    )
    parser.add_argument(
        "--pv-per-min",
        type=float,
        default=None,
        help="Direct PV/min conversion fallback when no PV column exists.",
    )
    parser.add_argument(
        "--flow-rate-ul-min",
        type=float,
        default=None,
        help="Water-displacement flow rate in µL/min for PV = Q * RealTime_s / 60 / Vpore.",
    )
    parser.add_argument(
        "--pore-volume-ul",
        type=float,
        default=None,
        help="Flow-domain pore volume in µL. If omitted, read from analysis_report.txt.",
    )
    parser.add_argument(
        "--skip-frames",
        type=int,
        default=0,
        help="Number of initial rows to skip before computing rates.",
    )
    parser.add_argument(
        "--min-time-min",
        type=float,
        default=None,
        help="Minimum Time_min to include after skipped frames.",
    )
    parser.add_argument("--dpi", type=int, default=300, help="PNG output DPI.")
    return parser


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir)
    csv_path = find_timeseries_csv(output_dir, args.csv_path)
    figures_dir = Path(args.figures_dir) if args.figures_dir else output_dir / "figures"

    df = load_timeseries(csv_path)
    if args.skip_frames > 0:
        if args.skip_frames >= len(df) - 1:
            raise ValueError(
                f"--skip-frames {args.skip_frames} would leave fewer than 2 rows"
            )
        df = df.iloc[args.skip_frames :].reset_index(drop=True)
    df = filter_min_time(df, args.min_time_min)

    print(f"Read: {csv_path}")
    print(f"Rows: {len(df)}")
    axis = args.x_axis
    windows = parse_windows(args.windows_pv if axis == "pv" and args.windows_pv else args.windows_min)
    rate_df, pv_metadata = compute_window_rates(
        df,
        windows,
        x_axis=axis,
        pv_column=args.pv_column,
        pv_per_min=args.pv_per_min,
        output_dir=output_dir,
        flow_rate_ul_min=args.flow_rate_ul_min,
        pore_volume_ul=args.pore_volume_ul,
    )
    written = [write_rate_workbook(rate_df, figures_dir, x_axis=axis)]
    if axis == "pv":
        written.append(write_pv_metadata(pv_metadata, figures_dir))
    written.extend(
        plot_rate_windows(
            rate_df,
            windows,
            figures_dir,
            x_axis=axis,
            pv_column=args.pv_column,
            pv_per_min=args.pv_per_min,
            output_dir=output_dir,
            flow_rate_ul_min=args.flow_rate_ul_min,
            pore_volume_ul=args.pore_volume_ul,
            dpi=args.dpi,
        )
    )
    print(f"X axis: {axis}")
    if axis == "pv":
        print(f"PV source: {pv_metadata.get('source')}")
        if pv_metadata.get("source") == "computed_from_flow_rate_and_realtime":
            print(
                "PV formula: PV = "
                f"{pv_metadata['flow_rate_ul_min']} * RealTime_s / 60 / "
                f"{pv_metadata['pore_volume_ul']}"
            )
    print("Rate windows: " + ", ".join(f"{w:g}" for w in windows))
    print(f"Output directory: {figures_dir}")
    for path in written:
        print(f"Saved: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
