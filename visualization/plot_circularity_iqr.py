"""Plot valid circularity median, IQR, and area-weighted circularity diagnostics."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from plot_timeseries import (
    INDIVIDUAL_SIZE,
    LINEWIDTH,
    MARKER_SIZE,
    VALID_SN_THRESHOLD,
    WONG_COLORS,
    _stage_from_sn_norm,
    configure_nature_style,
    find_timeseries_csv,
    load_timeseries,
    style_axes,
)


STAGE_ORDER = ["early", "middle", "late", "near-depleted"]


def find_blob_detail_csv(output_dir, blob_detail_path=None):
    if blob_detail_path:
        path = Path(blob_detail_path)
        if not path.exists():
            raise FileNotFoundError(f"Blob-detail CSV not found: {path}")
        return path
    path = Path(output_dir) / "blob_detail_all_frames.csv"
    if not path.exists():
        raise FileNotFoundError(f"blob_detail_all_frames.csv not found in {output_dir}")
    return path


def _sn0_from_series(sn):
    values = pd.to_numeric(sn, errors="coerce")
    finite = values[np.isfinite(values)]
    if finite.empty:
        raise ValueError("No finite Sn values found.")
    positive = finite[finite > 0]
    return float(positive.iloc[0] if not positive.empty else finite.iloc[0])


def prepare_timeseries(df, skip_frames=0, min_time_min=None):
    out = df.copy()
    if "Time_min" not in out.columns:
        if "RealTime_s" not in out.columns:
            raise ValueError("Timeseries data must contain Time_min or RealTime_s.")
        out["Time_min"] = pd.to_numeric(out["RealTime_s"], errors="coerce") / 60.0
    if "FrameIndex" not in out.columns:
        out["FrameIndex"] = np.arange(1, len(out) + 1)
    if skip_frames:
        if skip_frames >= len(out):
            raise ValueError(f"--skip-frames {skip_frames} removes all rows.")
        out = out.iloc[int(skip_frames):].reset_index(drop=True)
    if min_time_min is not None:
        out = out[pd.to_numeric(out["Time_min"], errors="coerce") >= float(min_time_min)].reset_index(drop=True)
    sn0 = _sn0_from_series(out["Sn"])
    out["SnNorm"] = pd.to_numeric(out["Sn"], errors="coerce") / sn0
    out["DissolutionStage"] = out["SnNorm"].map(_stage_from_sn_norm)
    return out


def _area_weighted_mean(area, values):
    area = np.asarray(area, dtype=float)
    values = np.asarray(values, dtype=float)
    finite = np.isfinite(area) & np.isfinite(values) & (area > 0)
    if not np.any(finite):
        return np.nan
    return float(np.sum(area[finite] * values[finite]) / np.sum(area[finite]))


def compute_circularity_summary(
    timeseries,
    blob_detail,
    min_blob_area_px=20,
    min_sn_norm=VALID_SN_THRESHOLD,
    max_circularity=1.05,
):
    required = {"FrameIndex", "Area", "Perimeter"}
    missing = required - set(blob_detail.columns)
    if missing:
        raise ValueError(f"blob_detail_all_frames.csv missing column(s): {', '.join(sorted(missing))}")

    frames = timeseries.copy()
    frame_cols = [
        column
        for column in ("FrameIndex", "RealTime_s", "Time_min", "Sn", "SnNorm", "DissolutionStage")
        if column in frames.columns
    ]
    frames = frames.loc[:, frame_cols].drop_duplicates("FrameIndex").copy()

    blobs = blob_detail.copy()
    for column in ("FrameIndex", "Area", "Perimeter", "Circularity"):
        if column in blobs.columns:
            blobs[column] = pd.to_numeric(blobs[column], errors="coerce")
    if "Circularity" not in blobs.columns:
        with np.errstate(divide="ignore", invalid="ignore"):
            blobs["Circularity"] = 4.0 * np.pi * blobs["Area"] / (blobs["Perimeter"] ** 2)

    blobs = blobs.merge(
        frames[["FrameIndex", "Time_min", "SnNorm", "DissolutionStage"]],
        on="FrameIndex",
        how="left",
    )

    valid = (
        (blobs["SnNorm"] > float(min_sn_norm))
        & (blobs["Area"] >= float(min_blob_area_px))
        & (blobs["Perimeter"] > 0)
        & np.isfinite(blobs["Circularity"])
        & (blobs["Circularity"] > 0)
    )
    if max_circularity is not None:
        valid &= blobs["Circularity"] <= float(max_circularity)

    valid_blobs = blobs.loc[valid].copy()
    raw = (
        blobs.groupby("FrameIndex")
        .agg(
            RawCircularityN=("Circularity", "size"),
            MeanCircularity_raw=("Circularity", "mean"),
        )
        .reset_index()
    )

    if valid_blobs.empty:
        valid_summary = pd.DataFrame(
            columns=[
                "FrameIndex",
                "ValidCircularityN",
                "ValidBlobAreaSum_px2",
                "MeanCircularity_valid",
                "CircularityQ25_valid",
                "MedianCircularity_valid",
                "CircularityQ75_valid",
                "AreaWeightedCircularity_valid",
            ]
        )
    else:
        grouped = valid_blobs.groupby("FrameIndex")
        valid_summary = (
            grouped["Circularity"]
            .agg(
                ValidCircularityN="size",
                MeanCircularity_valid="mean",
                CircularityQ25_valid=lambda s: s.quantile(0.25),
                MedianCircularity_valid="median",
                CircularityQ75_valid=lambda s: s.quantile(0.75),
            )
            .reset_index()
        )
        area_sum = grouped["Area"].sum().rename("ValidBlobAreaSum_px2").reset_index()
        valid_blobs["_CircularityAreaProduct"] = valid_blobs["Area"] * valid_blobs["Circularity"]
        weighted_sum = grouped["_CircularityAreaProduct"].sum()
        area_sum_for_weight = grouped["Area"].sum()
        weighted = (weighted_sum / area_sum_for_weight).where(area_sum_for_weight > 0, np.nan)
        weighted = weighted.rename("AreaWeightedCircularity_valid").reset_index()
        valid_summary = valid_summary.merge(area_sum, on="FrameIndex", how="left").merge(
            weighted, on="FrameIndex", how="left"
        )

    summary = frames.merge(raw, on="FrameIndex", how="left").merge(valid_summary, on="FrameIndex", how="left")
    summary["ValidCircularityN"] = summary["ValidCircularityN"].fillna(0).astype(int)
    summary["ValidBlobAreaSum_px2"] = summary["ValidBlobAreaSum_px2"].fillna(0.0)
    summary["ValidSnThreshold"] = float(min_sn_norm)
    summary["MinBlobArea_px2"] = float(min_blob_area_px)
    summary["MaxCircularity"] = np.nan if max_circularity is None else float(max_circularity)
    return summary, valid_blobs


def compute_binned_summary(valid_blobs, bin_width_min=20):
    if valid_blobs.empty:
        return pd.DataFrame(
            columns=[
                "TimeBinStart_min",
                "TimeBinCenter_min",
                "ValidCircularityN",
                "CircularityQ25_valid",
                "MedianCircularity_valid",
                "CircularityQ75_valid",
                "AreaWeightedCircularity_valid",
            ]
        )
    data = valid_blobs.copy()
    data = data[np.isfinite(data["Time_min"]) & np.isfinite(data["Circularity"])]
    if data.empty:
        return pd.DataFrame()
    width = float(bin_width_min)
    data["TimeBinStart_min"] = np.floor(data["Time_min"] / width) * width
    grouped = data.groupby("TimeBinStart_min")
    out = (
        grouped["Circularity"]
        .agg(
            ValidCircularityN="size",
            CircularityQ25_valid=lambda s: s.quantile(0.25),
            MedianCircularity_valid="median",
            CircularityQ75_valid=lambda s: s.quantile(0.75),
        )
        .reset_index()
    )
    data["_CircularityAreaProduct"] = data["Area"] * data["Circularity"]
    weighted_sum = grouped["_CircularityAreaProduct"].sum()
    area_sum = grouped["Area"].sum()
    weighted = (weighted_sum / area_sum).where(area_sum > 0, np.nan)
    weighted = weighted.rename("AreaWeightedCircularity_valid").reset_index()
    out = out.merge(weighted, on="TimeBinStart_min", how="left")
    out["TimeBinCenter_min"] = out["TimeBinStart_min"] + width / 2.0
    return out


def compute_stage_summary(valid_blobs):
    if valid_blobs.empty:
        return pd.DataFrame(columns=["DissolutionStage", "ValidCircularityN"])
    rows = []
    for stage in STAGE_ORDER:
        group = valid_blobs[valid_blobs["DissolutionStage"] == stage]
        if group.empty:
            continue
        rows.append(
            {
                "DissolutionStage": stage,
                "ValidCircularityN": int(len(group)),
                "CircularityQ25_valid": float(group["Circularity"].quantile(0.25)),
                "MedianCircularity_valid": float(group["Circularity"].median()),
                "CircularityQ75_valid": float(group["Circularity"].quantile(0.75)),
                "AreaWeightedCircularity_valid": _area_weighted_mean(group["Area"], group["Circularity"]),
            }
        )
    return pd.DataFrame(rows)


def _legend_above(ax, ncol=3):
    ax.legend(
        loc="lower center",
        bbox_to_anchor=(0.5, 1.04),
        ncol=ncol,
        frameon=False,
        handlelength=1.6,
        handletextpad=0.4,
        columnspacing=1.2,
        borderaxespad=0.0,
    )


def _save_figure(fig, out_dir, stem, dpi):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / f"{stem}.png"
    svg = out_dir / f"{stem}.svg"
    fig.savefig(png, dpi=dpi, facecolor="white")
    fig.savefig(svg, facecolor="white")
    plt.close(fig)
    return [png, svg]


def plot_frame_iqr(summary, out_dir, dpi=300):
    configure_nature_style()
    fig, (ax, ax_n) = plt.subplots(
        2,
        1,
        figsize=(INDIVIDUAL_SIZE[0], INDIVIDUAL_SIZE[1] * 1.25),
        sharex=True,
        gridspec_kw={"height_ratios": [3.0, 0.9]},
    )
    x = pd.to_numeric(summary["Time_min"], errors="coerce").to_numpy(dtype=float)
    q25 = pd.to_numeric(summary["CircularityQ25_valid"], errors="coerce").to_numpy(dtype=float)
    med = pd.to_numeric(summary["MedianCircularity_valid"], errors="coerce").to_numpy(dtype=float)
    q75 = pd.to_numeric(summary["CircularityQ75_valid"], errors="coerce").to_numpy(dtype=float)
    area_weighted = pd.to_numeric(summary["AreaWeightedCircularity_valid"], errors="coerce").to_numpy(dtype=float)
    n = pd.to_numeric(summary["ValidCircularityN"], errors="coerce").to_numpy(dtype=float)

    band = np.isfinite(x) & np.isfinite(q25) & np.isfinite(q75)
    ax.fill_between(x[band], q25[band], q75[band], color=WONG_COLORS["sky_blue"], alpha=0.22, label="IQR")
    line = np.isfinite(x) & np.isfinite(med)
    ax.plot(x[line], med[line], color=WONG_COLORS["blue"], linewidth=LINEWIDTH, label="Median")
    weighted = np.isfinite(x) & np.isfinite(area_weighted)
    ax.plot(
        x[weighted],
        area_weighted[weighted],
        color=WONG_COLORS["bluish_green"],
        linewidth=LINEWIDTH,
        label="Area-weighted",
    )
    ax.set_ylabel("Circularity (-)")
    style_axes(ax)
    _legend_above(ax, ncol=3)

    count_mask = np.isfinite(x) & np.isfinite(n)
    ax_n.plot(x[count_mask], n[count_mask], color="#555555", linewidth=0.8)
    ax_n.fill_between(x[count_mask], 0, n[count_mask], color="#BDBDBD", alpha=0.45)
    ax_n.set_ylabel("n")
    ax_n.set_xlabel("Time (min)")
    style_axes(ax_n)
    fig.tight_layout(pad=0.6, h_pad=0.4)
    return _save_figure(fig, out_dir, "S14_circularity_median_iqr", dpi)


def _bin_width_stem(bin_width_min):
    width = float(bin_width_min)
    text = f"{width:g}".replace(".", "p")
    return f"{text}min"


def plot_binned_iqr(binned, out_dir, bin_width_min=20, dpi=300):
    configure_nature_style()
    fig, ax = plt.subplots(figsize=INDIVIDUAL_SIZE)
    if not binned.empty:
        x = pd.to_numeric(binned["TimeBinCenter_min"], errors="coerce").to_numpy(dtype=float)
        q25 = pd.to_numeric(binned["CircularityQ25_valid"], errors="coerce").to_numpy(dtype=float)
        med = pd.to_numeric(binned["MedianCircularity_valid"], errors="coerce").to_numpy(dtype=float)
        q75 = pd.to_numeric(binned["CircularityQ75_valid"], errors="coerce").to_numpy(dtype=float)
        area_weighted = pd.to_numeric(binned["AreaWeightedCircularity_valid"], errors="coerce").to_numpy(dtype=float)
        mask = np.isfinite(x) & np.isfinite(med) & np.isfinite(q25) & np.isfinite(q75)
        yerr = np.vstack([med[mask] - q25[mask], q75[mask] - med[mask]])
        ax.errorbar(
            x[mask],
            med[mask],
            yerr=yerr,
            color=WONG_COLORS["blue"],
            marker="o",
            markersize=MARKER_SIZE,
            markerfacecolor="white",
            markeredgecolor=WONG_COLORS["blue"],
            linewidth=LINEWIDTH,
            capsize=2.5,
            label=f"Median +/- IQR ({bin_width_min:g} min bins)",
        )
        weighted = np.isfinite(x) & np.isfinite(area_weighted)
        ax.plot(
            x[weighted],
            area_weighted[weighted],
            color=WONG_COLORS["bluish_green"],
            linewidth=LINEWIDTH,
            marker="s",
            markersize=MARKER_SIZE,
            markerfacecolor="white",
            markeredgecolor=WONG_COLORS["bluish_green"],
            label="Area-weighted",
        )
    ax.set_xlabel("Time (min)")
    ax.set_ylabel("Circularity (-)")
    style_axes(ax)
    _legend_above(ax, ncol=1)
    fig.tight_layout(pad=0.6)
    stem = f"S15_circularity_binned_iqr_errorbar_{_bin_width_stem(bin_width_min)}"
    return _save_figure(fig, out_dir, stem, dpi)


def plot_stage_violin(valid_blobs, out_dir, dpi=300):
    configure_nature_style()
    fig, ax = plt.subplots(figsize=INDIVIDUAL_SIZE)
    groups = [
        valid_blobs.loc[valid_blobs["DissolutionStage"] == stage, "Circularity"].dropna().to_numpy(dtype=float)
        for stage in STAGE_ORDER
    ]
    used = [(stage, values) for stage, values in zip(STAGE_ORDER, groups) if len(values)]
    if used:
        labels, values = zip(*used)
        positions = np.arange(1, len(values) + 1)
        violins = ax.violinplot(values, positions=positions, showmeans=False, showmedians=True)
        for body in violins["bodies"]:
            body.set_facecolor(WONG_COLORS["sky_blue"])
            body.set_edgecolor(WONG_COLORS["blue"])
            body.set_alpha(0.35)
        for key in ("cmedians", "cbars", "cmins", "cmaxes"):
            if key in violins:
                violins[key].set_color(WONG_COLORS["blue"])
                violins[key].set_linewidth(0.8)
        ax.set_xticks(positions)
        ax.set_xticklabels([f"{label}\nn={len(vals)}" for label, vals in used])
    ax.set_xlabel("Dissolution stage")
    ax.set_ylabel("Valid blob circularity (-)")
    style_axes(ax)
    fig.tight_layout(pad=0.6)
    return _save_figure(fig, out_dir, "S16_circularity_stage_violin", dpi)


def write_workbook(summary, binned_by_width, stage_summary, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "S14_circularity_median_iqr_data.xlsx"
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        sheets = {"frame_summary": summary, "stage_summary": stage_summary}
        for width, binned in binned_by_width.items():
            sheets[f"binned_{_bin_width_stem(width)}"] = binned
        for sheet_name, data in sheets.items():
            safe_sheet_name = sheet_name[:31]
            data.to_excel(writer, sheet_name=safe_sheet_name, index=False)
            worksheet = writer.sheets[safe_sheet_name]
            if len(data.columns):
                worksheet.freeze_panes(1, 0)
                worksheet.autofilter(0, 0, len(data), len(data.columns) - 1)
            for idx, column in enumerate(data.columns):
                width = min(max(len(str(column)) + 2, 12), 34)
                worksheet.set_column(idx, idx, width)
    return path


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Create circularity median/IQR diagnostics from blob_detail_all_frames.csv."
    )
    parser.add_argument("output_dir", help="Pipeline output directory.")
    parser.add_argument("--csv", dest="csv_path", help="Explicit timeseries CSV path.")
    parser.add_argument("--blob-detail", help="Explicit blob_detail_all_frames.csv path.")
    parser.add_argument("--figures-dir", help="Output directory; default: <output_dir>/figures_circularity_qc.")
    parser.add_argument("--min-blob-area-px", type=float, default=20.0)
    parser.add_argument("--min-sn-norm", type=float, default=VALID_SN_THRESHOLD)
    parser.add_argument(
        "--max-circularity",
        default="1.05",
        help="Maximum valid circularity; use 'none' to disable upper filtering.",
    )
    parser.add_argument(
        "--bin-width-min",
        default="20",
        help="Time-bin width(s) in minutes for binned errorbar plots; comma-separated values allowed.",
    )
    parser.add_argument("--skip-frames", type=int, default=0)
    parser.add_argument("--min-time-min", type=float, default=None)
    parser.add_argument("--dpi", type=int, default=300)
    return parser


def _parse_max_circularity(value):
    if value is None:
        return None
    if str(value).strip().lower() in {"none", "nan", "off"}:
        return None
    parsed = float(value)
    if parsed <= 0:
        raise ValueError("--max-circularity must be positive or 'none'.")
    return parsed


def _parse_bin_widths(value):
    widths = []
    for item in str(value).split(","):
        item = item.strip()
        if not item:
            continue
        width = float(item)
        if width <= 0:
            raise ValueError("--bin-width-min values must be positive.")
        widths.append(width)
    if not widths:
        raise ValueError("--bin-width-min must contain at least one positive value.")
    return widths


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir)
    csv_path = Path(args.csv_path) if args.csv_path else find_timeseries_csv(output_dir)
    blob_detail_path = find_blob_detail_csv(output_dir, args.blob_detail)
    figures_dir = Path(args.figures_dir) if args.figures_dir else output_dir / "figures_circularity_qc"

    timeseries = prepare_timeseries(
        load_timeseries(csv_path),
        skip_frames=args.skip_frames,
        min_time_min=args.min_time_min,
    )
    blob_detail = pd.read_csv(blob_detail_path)
    max_circularity = _parse_max_circularity(args.max_circularity)
    bin_widths = _parse_bin_widths(args.bin_width_min)
    summary, valid_blobs = compute_circularity_summary(
        timeseries,
        blob_detail,
        min_blob_area_px=args.min_blob_area_px,
        min_sn_norm=args.min_sn_norm,
        max_circularity=max_circularity,
    )
    binned_by_width = {
        width: compute_binned_summary(valid_blobs, bin_width_min=width)
        for width in bin_widths
    }
    stage_summary = compute_stage_summary(valid_blobs)

    written = []
    written.extend(plot_frame_iqr(summary, figures_dir, dpi=args.dpi))
    for width, binned in binned_by_width.items():
        written.extend(plot_binned_iqr(binned, figures_dir, bin_width_min=width, dpi=args.dpi))
    written.extend(plot_stage_violin(valid_blobs, figures_dir, dpi=args.dpi))
    written.append(write_workbook(summary, binned_by_width, stage_summary, figures_dir))

    print(f"Read timeseries: {csv_path}")
    print(f"Read blob detail: {blob_detail_path}")
    print(f"Rows: {len(summary)} frames; valid blobs: {len(valid_blobs)}")
    print(f"Output directory: {figures_dir}")
    for path in written:
        print(f"Saved: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
