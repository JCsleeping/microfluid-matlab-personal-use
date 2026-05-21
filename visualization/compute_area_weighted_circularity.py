"""Compute area-weighted valid mean circularity vs time or PV."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from compute_dissolution_rate_windows import resolve_x_axis, write_pv_metadata
from plot_timeseries import (
    INDIVIDUAL_SIZE,
    LINEWIDTH,
    MARKER,
    MARKER_SIZE,
    VALID_SN_THRESHOLD,
    WONG_COLORS,
    configure_nature_style,
    filter_min_time,
    find_timeseries_csv,
    load_timeseries,
    style_axes,
)


def find_blob_detail_csv(output_dir, blob_detail_path=None):
    if blob_detail_path is not None:
        path = Path(blob_detail_path)
        if not path.exists():
            raise FileNotFoundError(f"Blob-detail CSV not found: {path}")
        return path
    path = Path(output_dir) / "blob_detail_all_frames.csv"
    if not path.exists():
        raise FileNotFoundError(f"blob_detail_all_frames.csv not found in {output_dir}")
    return path


def load_timeseries_with_frame_index(csv_path):
    df = load_timeseries(csv_path)
    if "FrameIndex" not in df.columns:
        df["FrameIndex"] = np.arange(1, len(df) + 1)
    return df


def _first_finite(series):
    values = pd.to_numeric(series, errors="coerce")
    finite = values[np.isfinite(values)]
    if finite.empty:
        raise ValueError("No finite Sn values found")
    return float(finite.iloc[0])


def prepare_timeseries(
    df,
    x_axis="time",
    pv_column="auto",
    pv_per_min=None,
    output_dir=None,
    flow_rate_ul_min=None,
    pore_volume_ul=None,
):
    out = df.copy()
    sn0 = _first_finite(out["Sn"])
    out["SnNorm"] = pd.to_numeric(out["Sn"], errors="coerce") / sn0
    x_col, _window_unit, _rate_unit, xlabel, x_values, metadata = resolve_x_axis(
        out,
        x_axis=x_axis,
        pv_column=pv_column,
        pv_per_min=pv_per_min,
        output_dir=output_dir,
        flow_rate_ul_min=flow_rate_ul_min,
        pore_volume_ul=pore_volume_ul,
    )
    out[x_col] = x_values
    return out, x_col, xlabel, metadata


def _area_weighted_mean(group):
    area = pd.to_numeric(group["Area"], errors="coerce").to_numpy(dtype=float)
    circ = pd.to_numeric(group["Circularity"], errors="coerce").to_numpy(dtype=float)
    finite = np.isfinite(area) & np.isfinite(circ) & (area > 0)
    if not np.any(finite):
        return np.nan
    return float(np.sum(area[finite] * circ[finite]) / np.sum(area[finite]))


def compute_area_weighted_circularity(
    timeseries,
    blob_detail,
    x_col,
    min_blob_area_px=20,
    valid_sn_threshold=VALID_SN_THRESHOLD,
):
    required = {"FrameIndex", "Area", "Perimeter"}
    missing = required - set(blob_detail.columns)
    if missing:
        raise ValueError(f"blob_detail_all_frames.csv missing column(s): {', '.join(sorted(missing))}")

    blobs = blob_detail.copy()
    for column in ("FrameIndex", "Area", "Perimeter", "Circularity"):
        if column in blobs.columns:
            blobs[column] = pd.to_numeric(blobs[column], errors="coerce")

    if "Circularity" not in blobs.columns:
        with np.errstate(divide="ignore", invalid="ignore"):
            blobs["Circularity"] = 4.0 * np.pi * blobs["Area"] / (blobs["Perimeter"] ** 2)

    frame_cols = []
    for col in ("FrameIndex", "RealTime_s", "Time_min", "Sn", "SnNorm", x_col):
        if col in timeseries.columns and col not in frame_cols:
            frame_cols.append(col)
    frames = timeseries[frame_cols].drop_duplicates("FrameIndex")
    blobs = blobs.merge(frames[["FrameIndex", "SnNorm"]], on="FrameIndex", how="left")

    valid_blob = (
        (blobs["SnNorm"] > float(valid_sn_threshold))
        & (blobs["Perimeter"] > 0)
        & (blobs["Area"] >= float(min_blob_area_px))
        & np.isfinite(blobs["Circularity"])
    )

    raw = (
        blobs.groupby("FrameIndex")
        .agg(
            NumBlobs_detail=("BlobID", "size") if "BlobID" in blobs.columns else ("Area", "size"),
            MeanCircularity_raw_unweighted=("Circularity", "mean"),
        )
        .reset_index()
    )

    valid_blobs = blobs.loc[valid_blob].copy()
    if valid_blobs.empty:
        valid = pd.DataFrame(
            columns=[
                "FrameIndex",
                "NumBlobs_valid_shape",
                "ValidBlobAreaSum_px2",
                "MeanCircularity_valid_unweighted",
                "MedianCircularity_valid",
                "MeanCircularity_valid_areaweighted",
            ]
        )
    else:
        valid_basic = (
            valid_blobs.groupby("FrameIndex")
            .agg(
                NumBlobs_valid_shape=("Circularity", "size"),
                ValidBlobAreaSum_px2=("Area", "sum"),
                MeanCircularity_valid_unweighted=("Circularity", "mean"),
                MedianCircularity_valid=("Circularity", "median"),
            )
            .reset_index()
        )
        weighted = (
            valid_blobs.groupby("FrameIndex")[["Area", "Circularity"]]
            .apply(_area_weighted_mean)
            .rename("MeanCircularity_valid_areaweighted")
            .reset_index()
        )
        valid = valid_basic.merge(weighted, on="FrameIndex", how="left")

    out = frames.merge(raw, on="FrameIndex", how="left").merge(valid, on="FrameIndex", how="left")
    out["ValidSnThreshold"] = float(valid_sn_threshold)
    out["MinBlobArea_px2"] = float(min_blob_area_px)
    out["ValidBlobRule"] = (
        f"SnNorm>{valid_sn_threshold:g}; Perimeter>0; Area>={min_blob_area_px:g} px^2"
    )
    return out


def plot_circularity(summary, x_col, xlabel, out_dir, x_axis="time", dpi=300):
    configure_nature_style()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    axis_suffix = "" if x_axis == "time" else "_pv"
    written = []
    for log_scale in (False, True):
        fig, ax = plt.subplots(figsize=INDIVIDUAL_SIZE)
        x = pd.to_numeric(summary[x_col], errors="coerce").to_numpy(dtype=float)
        series = [
            (
                "MeanCircularity_raw_unweighted",
                "Raw unweighted",
                "#A0A0A0",
                0.9,
                None,
            ),
            (
                "MeanCircularity_valid_areaweighted",
                "Valid area-weighted",
                WONG_COLORS["reddish_purple"],
                LINEWIDTH,
                MARKER,
            ),
        ]
        for column, label, color, linewidth, marker in series:
            if column not in summary.columns:
                continue
            y = pd.to_numeric(summary[column], errors="coerce").to_numpy(dtype=float)
            mask = np.isfinite(x) & np.isfinite(y)
            if log_scale:
                mask &= x > 0
            if not np.any(mask):
                continue
            ax.plot(
                x[mask],
                y[mask],
                color=color,
                linewidth=linewidth,
                marker=marker,
                markersize=MARKER_SIZE if marker else 0,
                markerfacecolor="white",
                markeredgecolor=color,
                markeredgewidth=1.0,
                markevery=max(1, int(np.count_nonzero(mask)) // 20),
                label=label,
            )

        ax.set_xlabel(f"{xlabel} (log scale)" if log_scale else xlabel)
        ax.set_ylabel("Mean circularity (-)")
        if log_scale:
            ax.set_xscale("log")
        style_axes(ax)
        if log_scale:
            ax.grid(True, which="both", color="#E4E4E4", linewidth=0.55, alpha=0.7)
        ax.legend(
            loc="lower center",
            bbox_to_anchor=(0.5, 1.04),
            ncol=2,
            frameon=False,
            handlelength=1.6,
            handletextpad=0.4,
            columnspacing=1.2,
            borderaxespad=0.0,
        )
        fig.tight_layout(pad=0.6)
        suffix = "_log" if log_scale else ""
        png = out_dir / f"09_mean_circularity_area_weighted{axis_suffix}{suffix}.png"
        svg = out_dir / f"09_mean_circularity_area_weighted{axis_suffix}{suffix}.svg"
        fig.savefig(png, dpi=dpi, facecolor="white")
        fig.savefig(svg, facecolor="white")
        plt.close(fig)
        written.extend([png, svg])
    return written


def write_summary_workbook(summary, out_dir, x_axis="time"):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    axis_suffix = "" if x_axis == "time" else "_pv"
    path = out_dir / f"09_mean_circularity_area_weighted{axis_suffix}_data.xlsx"
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        summary.to_excel(writer, sheet_name="data", index=False)
        worksheet = writer.sheets["data"]
        worksheet.freeze_panes(1, 0)
        for idx, column in enumerate(summary.columns):
            width = min(max(len(str(column)) + 2, 12), 42)
            worksheet.set_column(idx, idx, width)
    return path


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Compute area-weighted valid mean circularity from blob_detail_all_frames.csv."
    )
    parser.add_argument("output_dir", help="Pipeline output directory.")
    parser.add_argument("--csv", dest="csv_path", help="Explicit time-series CSV path.")
    parser.add_argument("--blob-detail", help="Explicit blob_detail_all_frames.csv path.")
    parser.add_argument("--figures-dir", help="Output directory. Defaults to <output_dir>/figures.")
    parser.add_argument(
        "--x-axis",
        choices=["time", "pv"],
        default="time",
        help="Plot x-axis. Run once with time and once with pv to generate separate figures.",
    )
    parser.add_argument("--pv-column", default="auto", help="PV column name, or auto.")
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
    parser.add_argument("--skip-frames", type=int, default=0, help="Initial rows to skip.")
    parser.add_argument("--min-time-min", type=float, default=None, help="Minimum Time_min to include.")
    parser.add_argument(
        "--min-blob-area-px",
        type=float,
        default=20,
        help="Minimum blob area in px^2 for valid area-weighted circularity.",
    )
    parser.add_argument(
        "--valid-sn-threshold",
        type=float,
        default=VALID_SN_THRESHOLD,
        help="Valid structure threshold in Sn/Sn0. Default: 0.05.",
    )
    parser.add_argument("--dpi", type=int, default=300, help="PNG output DPI.")
    return parser


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir)
    csv_path = find_timeseries_csv(output_dir, args.csv_path)
    blob_detail_path = find_blob_detail_csv(output_dir, args.blob_detail)
    figures_dir = Path(args.figures_dir) if args.figures_dir else output_dir / "figures"

    df = load_timeseries_with_frame_index(csv_path)
    if args.skip_frames > 0:
        if args.skip_frames >= len(df) - 1:
            raise ValueError(f"--skip-frames {args.skip_frames} would leave fewer than 2 rows")
        df = df.iloc[args.skip_frames :].reset_index(drop=True)
    blob_detail = pd.read_csv(blob_detail_path)
    df = filter_min_time(df, args.min_time_min)
    print(f"Read time-series: {csv_path}")
    print(f"Read blob detail: {blob_detail_path}")
    print(f"Rows: {len(df)}")
    axis = args.x_axis
    axis_df, x_col, xlabel, pv_metadata = prepare_timeseries(
        df,
        x_axis=axis,
        pv_column=args.pv_column,
        pv_per_min=args.pv_per_min,
        output_dir=output_dir,
        flow_rate_ul_min=args.flow_rate_ul_min,
        pore_volume_ul=args.pore_volume_ul,
    )
    summary = compute_area_weighted_circularity(
        axis_df,
        blob_detail,
        x_col,
        min_blob_area_px=args.min_blob_area_px,
        valid_sn_threshold=args.valid_sn_threshold,
    )
    written = [write_summary_workbook(summary, figures_dir, x_axis=axis)]
    if axis == "pv":
        written.append(write_pv_metadata(pv_metadata, figures_dir))
    written.extend(plot_circularity(summary, x_col, xlabel, figures_dir, x_axis=axis, dpi=args.dpi))
    print(f"X axis: {axis}")
    if axis == "pv":
        print(f"PV source: {pv_metadata.get('source')}")
        if pv_metadata.get("source") == "computed_from_flow_rate_and_realtime":
            print(
                "PV formula: PV = "
                f"{pv_metadata['flow_rate_ul_min']} * RealTime_s / 60 / "
                f"{pv_metadata['pore_volume_ul']}"
            )
    print(
        "Valid blob rule: "
        f"Sn/Sn0>{args.valid_sn_threshold:g}, Perimeter>0, Area>={args.min_blob_area_px:g} px^2"
    )
    print(f"Output directory: {figures_dir}")
    for path in written:
        print(f"Saved: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
