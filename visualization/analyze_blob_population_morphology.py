"""Population morphology analysis from per-blob detail tables."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


DEFAULT_OUTPUT_DIR = Path(
    r"G:\微流控\17 1-BO 4UL 5% TWEEM 80 6UL WATER DISPLACE\Tween 80\output_20260428_214120"
)

NUMERIC_COLUMNS = (
    "FrameIndex",
    "FrameTime",
    "BlobID",
    "Area",
    "Perimeter",
    "Circularity",
    "AspectRatio",
    "Solidity",
    "EquivRadius",
    "EulerNumber",
)
AREA_STAT_COLUMNS = ("Area", "EquivRadius")
SHAPE_COLUMNS = ("Circularity", "AspectRatio", "Solidity")
TOPOLOGY_CLASSES = ("Droplets", "Columns", "Clusters", "Other")
WONG_COLORS = {
    "blue": "#0072B2",
    "orange": "#E69F00",
    "bluish_green": "#009E73",
    "vermillion": "#D55E00",
    "reddish_purple": "#CC79A7",
    "black": "#000000",
}
MM_PER_INCH = 25.4
INDIVIDUAL_SIZE = (89 / MM_PER_INCH, 68 / MM_PER_INCH)
LINEWIDTH = 1.8


def find_blob_csv(output_dir, explicit_path=None):
    if explicit_path:
        path = Path(explicit_path)
    else:
        path = Path(output_dir) / "blob_detail_all_frames.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"blob_detail_all_frames.csv not found at {path}. "
            "This Python script requires the combined CSV because MATLAB .mat chunks "
            "store blob_detail_table as an opaque MCOS table."
        )
    return path


def find_timeseries_csv(output_dir, explicit_path=None):
    if explicit_path:
        path = Path(explicit_path)
        return path if path.exists() else None
    candidates = list(Path(output_dir).glob("timeseries_realtime*.csv"))
    if not candidates:
        return None
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name))


def find_pixel_size_um(output_dir):
    report = Path(output_dir) / "analysis_report.txt"
    if not report.exists():
        return None
    text = report.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"Pixel\s*Size\s*:\s*([0-9.]+)", text, flags=re.IGNORECASE)
    return float(match.group(1)) if match else None


def load_blob_detail(blob_csv):
    available = pd.read_csv(blob_csv, nrows=0).columns
    usecols = [col for col in [
        "FrameIndex",
        "FrameTime",
        "BlobID",
        "Area",
        "Perimeter",
        "Circularity",
        "AspectRatio",
        "Solidity",
        "EquivRadius",
        "EulerNumber",
        "TopologyType",
    ] if col in available]
    missing = {"FrameIndex", "Area"} - set(usecols)
    if missing:
        raise ValueError(f"Missing required blob-detail column(s): {', '.join(sorted(missing))}")
    blobs = pd.read_csv(blob_csv, usecols=usecols)
    for column in NUMERIC_COLUMNS:
        if column in blobs.columns:
            blobs[column] = pd.to_numeric(blobs[column], errors="coerce")
    return blobs


def load_timeseries(timeseries_csv):
    if timeseries_csv is None:
        return None
    timeseries = pd.read_csv(timeseries_csv)
    for column in ("Time", "RealTime_s", "Sn"):
        if column in timeseries.columns:
            timeseries[column] = pd.to_numeric(timeseries[column], errors="coerce")
    return timeseries


def _percentile(values, q):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    return float(np.percentile(values, q)) if values.size else np.nan


def _stats(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return {"median": np.nan, "mean": np.nan, "p10": np.nan, "p90": np.nan}
    return {
        "median": float(np.median(values)),
        "mean": float(np.mean(values)),
        "p10": float(np.percentile(values, 10)),
        "p90": float(np.percentile(values, 90)),
    }


def area_gini(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values) & (values >= 0)]
    if values.size == 0:
        return np.nan
    mean = float(np.mean(values))
    if mean <= 0:
        return 0.0
    diff_sum = np.abs(values[:, None] - values[None, :]).sum()
    return float(diff_sum / (2.0 * values.size * values.size * mean))


def _area_weighted_mean(group, metric):
    valid = (
        pd.to_numeric(group.get(metric), errors="coerce").notna()
        & pd.to_numeric(group.get("Area"), errors="coerce").notna()
        & (pd.to_numeric(group.get("Area"), errors="coerce") > 0)
    )
    subset = group.loc[valid]
    if subset.empty:
        return np.nan
    total_area = subset["Area"].sum()
    return float((subset["Area"] * subset[metric]).sum() / total_area) if total_area > 0 else np.nan


def compute_frame_morphology(
    blob_detail,
    pixel_size_um=None,
    min_shape_area_px=9,
    min_shape_perimeter_px=8,
):
    blobs = blob_detail.copy()
    for column in NUMERIC_COLUMNS:
        if column in blobs.columns:
            blobs[column] = pd.to_numeric(blobs[column], errors="coerce")
    if "EquivRadius" not in blobs.columns and "Area" in blobs.columns:
        blobs["EquivRadius"] = np.sqrt(blobs["Area"] / np.pi)

    rows = []
    for frame_index, group in blobs.groupby("FrameIndex", sort=True):
        area = pd.to_numeric(group["Area"], errors="coerce")
        positive_area = area[np.isfinite(area) & (area > 0)]
        row = {
            "FrameIndex": frame_index,
            "BlobCount": int(len(positive_area)),
            "TotalArea_px": float(positive_area.sum()) if len(positive_area) else np.nan,
        }
        if "FrameTime" in group.columns:
            row["FrameTime"] = group["FrameTime"].iloc[0]

        for column in AREA_STAT_COLUMNS:
            values = pd.to_numeric(group[column], errors="coerce") if column in group.columns else pd.Series(dtype=float)
            values = values[np.isfinite(values) & (values > 0)]
            stats = _stats(values)
            prefix = f"{column}_"
            suffix = "_px" if column == "EquivRadius" else "_px"
            for name, value in stats.items():
                row[f"{prefix}{name}{suffix}"] = value

        if pixel_size_um:
            for name in ("median", "mean", "p10", "p90"):
                row[f"Area_{name}_um2"] = row[f"Area_{name}_px"] * float(pixel_size_um) ** 2
                row[f"EquivRadius_{name}_um"] = row[f"EquivRadius_{name}_px"] * float(pixel_size_um)

        if len(positive_area):
            sorted_area = np.sort(positive_area.to_numpy(dtype=float))[::-1]
            row["Amax_Atotal"] = float(sorted_area[0] / sorted_area.sum())
            row["A_top3_Atotal"] = float(sorted_area[:3].sum() / sorted_area.sum())
            row["AreaGini"] = area_gini(sorted_area)
        else:
            row["Amax_Atotal"] = np.nan
            row["A_top3_Atotal"] = np.nan
            row["AreaGini"] = np.nan

        shape_base = (
            (pd.to_numeric(group.get("Area"), errors="coerce") >= float(min_shape_area_px))
            & (pd.to_numeric(group.get("Perimeter"), errors="coerce") >= float(min_shape_perimeter_px))
        )
        shape_group = group.loc[shape_base].copy()
        for column in SHAPE_COLUMNS:
            values = pd.to_numeric(shape_group[column], errors="coerce") if column in shape_group.columns else pd.Series(dtype=float)
            values = values[np.isfinite(values)]
            row[f"{column}_median"] = float(values.median()) if len(values) else np.nan
            row[f"{column}_mean"] = float(values.mean()) if len(values) else np.nan
            row[f"{column}_area_weighted_mean"] = _area_weighted_mean(shape_group, column)

        euler = pd.to_numeric(group.get("EulerNumber"), errors="coerce") if "EulerNumber" in group.columns else pd.Series(dtype=float)
        euler_valid = euler[np.isfinite(euler)]
        row["EulerNumber_mean"] = float(euler_valid.mean()) if len(euler_valid) else np.nan
        row["EulerNumber_median"] = float(euler_valid.median()) if len(euler_valid) else np.nan
        row["EulerNumber_min"] = float(euler_valid.min()) if len(euler_valid) else np.nan
        row["EulerNumber_max"] = float(euler_valid.max()) if len(euler_valid) else np.nan
        for value, count in euler_valid.astype(int).value_counts().items():
            label = str(value).replace("-", "neg")
            row[f"EulerNumber_count_{label}"] = int(count)
        rows.append(row)

    return pd.DataFrame(rows).sort_values("FrameIndex").reset_index(drop=True)


def _topology_class(value):
    text = str(value).strip().lower()
    if "droplet" in text:
        return "Droplets"
    if "column" in text:
        return "Columns"
    if "cluster" in text:
        return "Clusters"
    return "Other"


def compute_topology_population(blob_detail):
    blobs = blob_detail.copy()
    blobs["Area"] = pd.to_numeric(blobs["Area"], errors="coerce")
    blobs = blobs[np.isfinite(blobs["Area"]) & (blobs["Area"] > 0)]
    blobs["TopologyClass"] = blobs.get("TopologyType", pd.Series("other", index=blobs.index)).map(_topology_class)
    rows = []
    for frame_index, group in blobs.groupby("FrameIndex", sort=True):
        total_count = len(group)
        total_area = float(group["Area"].sum())
        row = {
            "FrameIndex": frame_index,
            "BlobCount": int(total_count),
            "TotalArea_px": total_area,
        }
        for label in TOPOLOGY_CLASSES:
            subset = group[group["TopologyClass"] == label]
            count = int(len(subset))
            area = float(subset["Area"].sum())
            row[f"count{label}"] = count
            row[f"countFrac{label}"] = count / total_count if total_count else np.nan
            row[f"areaFrac{label}"] = area / total_area if total_area > 0 else np.nan
        rows.append(row)
    return pd.DataFrame(rows).sort_values("FrameIndex").reset_index(drop=True)


def compute_size_distribution_slopes(blob_detail, q_low=0.10, q_high=0.90, min_slope_points=20):
    blobs = blob_detail.copy()
    if "EquivRadius" not in blobs.columns:
        blobs["EquivRadius"] = np.sqrt(pd.to_numeric(blobs["Area"], errors="coerce") / np.pi)
    rows = []
    for frame_index, group in blobs.groupby("FrameIndex", sort=True):
        req = pd.to_numeric(group["EquivRadius"], errors="coerce").to_numpy(dtype=float)
        req = np.sort(req[np.isfinite(req) & (req > 0)])
        row = {
            "FrameIndex": frame_index,
            "Slope_logN_gt_Req_vs_logReq": np.nan,
            "Intercept": np.nan,
            "R2": np.nan,
            "FitN": 0,
            "FitReqMin": np.nan,
            "FitReqMax": np.nan,
        }
        if req.size >= int(min_slope_points):
            low = float(np.quantile(req, float(q_low)))
            high = float(np.quantile(req, float(q_high)))
            fit_req = req[(req >= low) & (req <= high)]
            if fit_req.size >= int(min_slope_points) and np.unique(fit_req).size >= 2:
                unique_req = np.unique(fit_req)
                survival = np.array([(req >= value).sum() for value in unique_req], dtype=float)
                valid = (unique_req > 0) & (survival > 0)
                x = np.log10(unique_req[valid])
                y = np.log10(survival[valid])
                if x.size >= 2:
                    slope, intercept = np.polyfit(x, y, 1)
                    y_hat = slope * x + intercept
                    ss_res = float(np.sum((y - y_hat) ** 2))
                    ss_tot = float(np.sum((y - y.mean()) ** 2))
                    row.update(
                        {
                            "Slope_logN_gt_Req_vs_logReq": float(slope),
                            "Intercept": float(intercept),
                            "R2": float(1.0 - ss_res / ss_tot) if ss_tot > 0 else np.nan,
                            "FitN": int(fit_req.size),
                            "FitReqMin": float(fit_req.min()),
                            "FitReqMax": float(fit_req.max()),
                        }
                    )
        rows.append(row)
    return pd.DataFrame(rows).sort_values("FrameIndex").reset_index(drop=True)


def align_timeseries(frame_df, timeseries):
    aligned = frame_df.copy()
    if timeseries is None:
        return aligned
    ts = timeseries.copy()
    if "Time" in ts.columns:
        ts["FrameIndex"] = pd.to_numeric(ts["Time"], errors="coerce").astype("Int64") + 1
    elif "FrameIndex" not in ts.columns:
        return aligned
    if "RealTime_s" in ts.columns:
        ts["Time_min"] = pd.to_numeric(ts["RealTime_s"], errors="coerce") / 60.0
    elif "Time_min" not in ts.columns and "Time" in ts.columns:
        ts["Time_min"] = pd.to_numeric(ts["Time"], errors="coerce")
    if "Sn" in ts.columns:
        sn = pd.to_numeric(ts["Sn"], errors="coerce")
        sn0 = sn[np.isfinite(sn) & (sn > 0)].iloc[0] if (np.isfinite(sn) & (sn > 0)).any() else np.nan
        ts["SnNorm"] = sn / sn0 if np.isfinite(sn0) and sn0 > 0 else np.nan
    keep = [column for column in ("FrameIndex", "RealTime_s", "Time_min", "Sn", "SnNorm") if column in ts.columns]
    return aligned.merge(ts.loc[:, keep].drop_duplicates("FrameIndex"), on="FrameIndex", how="left")


def configure_style():
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


def legend_above(ax, handles=None, labels=None, ncol=None):
    if handles is None or labels is None:
        handles, labels = ax.get_legend_handles_labels()
    pairs = [(handle, label) for handle, label in zip(handles, labels) if label and not label.startswith("_")]
    if not pairs:
        return None
    handles, labels = zip(*pairs)
    return ax.legend(
        handles,
        labels,
        loc="lower center",
        bbox_to_anchor=(0.5, 1.04),
        ncol=ncol or min(len(labels), 3),
        frameon=False,
        handlelength=1.6,
        handletextpad=0.4,
        columnspacing=1.2,
        borderaxespad=0.0,
    )


def style_twin_axis(ax):
    style_axes(ax)
    ax.spines["left"].set_visible(False)
    ax.spines["right"].set_visible(True)
    ax.spines["right"].set_linewidth(0.9)
    ax.spines["right"].set_color("#2B2B2B")
    ax.grid(False)
    return ax


def save_figure(fig, figures_dir, stem, dpi):
    figures_dir = Path(figures_dir)
    figures_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for suffix in ("png", "svg"):
        path = figures_dir / f"{stem}.{suffix}"
        fig.savefig(path, dpi=dpi if suffix == "png" else None, facecolor="white")
        paths.append(path)
    return paths


def _x(df):
    return df["Time_min"] if "Time_min" in df.columns and df["Time_min"].notna().any() else df["FrameIndex"]


def create_figures(frame_summary, topology, slopes, figures_dir, dpi=300):
    configure_style()
    written = []

    x = _x(frame_summary)
    xlabel = "Time (min)" if "Time_min" in frame_summary.columns and frame_summary["Time_min"].notna().any() else "Frame index"

    fig, ax = plt.subplots(figsize=INDIVIDUAL_SIZE)
    ax.plot(x, frame_summary["Area_median_px"], color=WONG_COLORS["blue"], linewidth=LINEWIDTH, label="Area median")
    ax.fill_between(x, frame_summary["Area_p10_px"], frame_summary["Area_p90_px"], color=WONG_COLORS["blue"], alpha=0.18, linewidth=0)
    ax2 = ax.twinx()
    ax2.plot(x, frame_summary["EquivRadius_median_px"], color=WONG_COLORS["vermillion"], linewidth=LINEWIDTH, label="Req median")
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Area (px2)")
    ax2.set_ylabel("Equivalent radius (px)")
    style_axes(ax)
    style_twin_axis(ax2)
    handles, labels = ax.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    legend_above(ax, handles + handles2, labels + labels2, ncol=2)
    fig.tight_layout(pad=0.6)
    written.extend(save_figure(fig, figures_dir, "01_area_req_distribution_summary", dpi))
    plt.close(fig)

    fig, ax = plt.subplots(figsize=INDIVIDUAL_SIZE)
    for column, label, color in [
        ("Circularity_area_weighted_mean", "Circularity", WONG_COLORS["blue"]),
        ("AspectRatio_area_weighted_mean", "Aspect ratio", WONG_COLORS["orange"]),
        ("Solidity_area_weighted_mean", "Solidity", WONG_COLORS["bluish_green"]),
    ]:
        if column in frame_summary.columns:
            ax.plot(x, frame_summary[column], label=label, color=color, linewidth=LINEWIDTH)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Area-weighted shape metric")
    style_axes(ax)
    legend_above(ax, ncol=3)
    fig.tight_layout(pad=0.6)
    written.extend(save_figure(fig, figures_dir, "02_shape_metrics_area_weighted", dpi))
    plt.close(fig)

    topo_aligned = topology
    if "Time_min" not in topo_aligned.columns and "Time_min" in frame_summary.columns:
        topo_aligned = topo_aligned.merge(frame_summary[["FrameIndex", "Time_min"]], on="FrameIndex", how="left")
    xt = _x(topo_aligned)
    fig, ax = plt.subplots(figsize=INDIVIDUAL_SIZE)
    for column, label, color in [
        ("areaFracDroplets", "Droplets", WONG_COLORS["blue"]),
        ("areaFracColumns", "Columns", WONG_COLORS["orange"]),
        ("areaFracClusters", "Clusters", WONG_COLORS["bluish_green"]),
    ]:
        if column in topo_aligned.columns:
            ax.plot(xt, topo_aligned[column], label=label, color=color, linewidth=LINEWIDTH)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Area fraction")
    ax.set_ylim(-0.02, 1.02)
    style_axes(ax)
    legend_above(ax, ncol=3)
    fig.tight_layout(pad=0.6)
    written.extend(save_figure(fig, figures_dir, "03_topology_area_fractions", dpi))
    plt.close(fig)

    slope_aligned = slopes
    if "Time_min" not in slope_aligned.columns and "Time_min" in frame_summary.columns:
        slope_aligned = slope_aligned.merge(frame_summary[["FrameIndex", "Time_min"]], on="FrameIndex", how="left")
    xs = _x(slope_aligned)
    fig, ax = plt.subplots(figsize=INDIVIDUAL_SIZE)
    ax.plot(xs, slope_aligned["Slope_logN_gt_Req_vs_logReq"], color=WONG_COLORS["reddish_purple"], linewidth=LINEWIDTH)
    ax.axhline(0, color="#999999", linewidth=0.7, linestyle="--")
    ax.set_xlabel(xlabel)
    ax.set_ylabel("2D population size-distribution slope")
    style_axes(ax)
    fig.tight_layout(pad=0.6)
    written.extend(save_figure(fig, figures_dir, "04_size_distribution_slope_vs_time", dpi))
    plt.close(fig)

    fig, ax = plt.subplots(figsize=INDIVIDUAL_SIZE)
    ax.plot(x, frame_summary["Amax_Atotal"], color=WONG_COLORS["blue"], linewidth=LINEWIDTH, label="Amax / Atotal")
    ax.plot(x, frame_summary["A_top3_Atotal"], color=WONG_COLORS["orange"], linewidth=LINEWIDTH, label="A top3 / Atotal")
    ax2 = ax.twinx()
    ax2.plot(x, frame_summary["AreaGini"], color=WONG_COLORS["black"], linewidth=LINEWIDTH, label="Area Gini")
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Area concentration")
    ax2.set_ylabel("Area Gini")
    ax.set_ylim(-0.02, 1.02)
    ax2.set_ylim(-0.02, 1.02)
    style_axes(ax)
    style_twin_axis(ax2)
    handles, labels = ax.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    legend_above(ax, handles + handles2, labels + labels2, ncol=3)
    fig.tight_layout(pad=0.6)
    written.extend(save_figure(fig, figures_dir, "05_area_concentration_metrics", dpi))
    plt.close(fig)

    return written


def create_summary(frame_summary, topology, slopes, pixel_size_um):
    return {
        "n_frames": int(len(frame_summary)),
        "pixel_size_um": pixel_size_um,
        "median_blob_count": float(frame_summary["BlobCount"].median()) if not frame_summary.empty else np.nan,
        "median_total_area_px": float(frame_summary["TotalArea_px"].median()) if not frame_summary.empty else np.nan,
        "median_area_gini": float(frame_summary["AreaGini"].median()) if not frame_summary.empty else np.nan,
        "slope_name": "2D population size-distribution slope",
        "n_slope_frames": int(slopes["Slope_logN_gt_Req_vs_logReq"].notna().sum()) if not slopes.empty else 0,
        "topology_columns": [column for column in topology.columns if column.startswith(("areaFrac", "countFrac"))],
    }


def write_blob_population_outputs(
    blob_csv,
    postprocess_dir,
    chunksize=200000,
    dpi=300,
    no_figures=False,
    min_slope_points=20,
):
    """Write blob-population Level A outputs for the batch postprocess driver."""
    _ = chunksize
    postprocess_dir = Path(postprocess_dir)
    postprocess_dir.mkdir(parents=True, exist_ok=True)
    output_root = postprocess_dir.parent
    pixel_size_um = find_pixel_size_um(output_root)
    timeseries_csv = find_timeseries_csv(output_root)

    blobs = load_blob_detail(blob_csv)
    timeseries = load_timeseries(timeseries_csv)
    frame_summary = compute_frame_morphology(blobs, pixel_size_um=pixel_size_um)
    frame_summary = align_timeseries(frame_summary, timeseries)
    topology = compute_topology_population(blobs)
    topology = align_timeseries(topology, timeseries)
    slopes = compute_size_distribution_slopes(blobs, min_slope_points=min_slope_points)
    slopes = align_timeseries(slopes, timeseries)

    frame_summary.to_csv(postprocess_dir / "blob_population_morphology_by_frame.csv", index=False)
    topology.to_csv(postprocess_dir / "topology_population_by_frame.csv", index=False)
    slopes.to_csv(postprocess_dir / "size_distribution_slope_vs_time.csv", index=False)
    summary = create_summary(frame_summary, topology, slopes, pixel_size_um)
    with (postprocess_dir / "blob_population_morphology_summary.json").open("w", encoding="utf-8") as fp:
        json.dump(summary, fp, indent=2, ensure_ascii=False, default=_json_default)

    written = []
    if not no_figures:
        written = create_figures(
            frame_summary,
            topology,
            slopes,
            postprocess_dir / "figures_blob_population",
            dpi=dpi,
        )

    return {
        "frame_summary": frame_summary,
        "topology": topology,
        "slopes": slopes,
        "summary": summary,
        "figures": written,
    }


def build_arg_parser():
    parser = argparse.ArgumentParser(description="Analyze per-frame blob population morphology.")
    parser.add_argument("output_dir", nargs="?", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--blob-csv", dest="blob_csv")
    parser.add_argument("--timeseries-csv", dest="timeseries_csv")
    parser.add_argument("--figures-dir", dest="figures_dir")
    parser.add_argument("--pixel-size-um", type=float, default=None)
    parser.add_argument("--min-shape-area-px", type=float, default=9.0)
    parser.add_argument("--min-shape-perimeter-px", type=float, default=8.0)
    parser.add_argument("--slope-q-low", type=float, default=0.10)
    parser.add_argument("--slope-q-high", type=float, default=0.90)
    parser.add_argument("--min-slope-points", type=int, default=20)
    parser.add_argument("--dpi", type=int, default=300)
    return parser


def _json_default(obj):
    if isinstance(obj, (np.integer, np.floating)):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if pd.isna(obj) if not isinstance(obj, (dict, list, tuple)) else False:
        return None
    return obj


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir)
    blob_csv = find_blob_csv(output_dir, args.blob_csv)
    timeseries_csv = find_timeseries_csv(output_dir, args.timeseries_csv)
    figures_dir = Path(args.figures_dir) if args.figures_dir else output_dir / "figures_blob_population"
    pixel_size_um = args.pixel_size_um if args.pixel_size_um is not None else find_pixel_size_um(output_dir)

    blobs = load_blob_detail(blob_csv)
    timeseries = load_timeseries(timeseries_csv)

    frame_summary = compute_frame_morphology(
        blobs,
        pixel_size_um=pixel_size_um,
        min_shape_area_px=args.min_shape_area_px,
        min_shape_perimeter_px=args.min_shape_perimeter_px,
    )
    frame_summary = align_timeseries(frame_summary, timeseries)
    topology = compute_topology_population(blobs)
    topology = align_timeseries(topology, timeseries)
    slopes = compute_size_distribution_slopes(
        blobs,
        q_low=args.slope_q_low,
        q_high=args.slope_q_high,
        min_slope_points=args.min_slope_points,
    )
    slopes = align_timeseries(slopes, timeseries)

    morphology_csv = output_dir / "blob_population_morphology_by_frame.csv"
    slopes_csv = output_dir / "size_distribution_slope_vs_time.csv"
    topology_csv = output_dir / "topology_population_by_frame.csv"
    summary_json = output_dir / "blob_population_morphology_summary.json"

    frame_summary.to_csv(morphology_csv, index=False)
    slopes.to_csv(slopes_csv, index=False)
    topology.to_csv(topology_csv, index=False)
    summary = create_summary(frame_summary, topology, slopes, pixel_size_um)
    with open(summary_json, "w", encoding="utf-8") as fp:
        json.dump(summary, fp, indent=2, ensure_ascii=False, default=_json_default)

    written = create_figures(frame_summary, topology, slopes, figures_dir, dpi=args.dpi)

    print(f"Read: {blob_csv}")
    if timeseries_csv is not None:
        print(f"Aligned timeseries: {timeseries_csv}")
    print(f"Frames: {len(frame_summary)}")
    print(f"Blobs: {len(blobs)}")
    if pixel_size_um is not None:
        print(f"Pixel size: {pixel_size_um} um/px")
    print(f"Saved: {morphology_csv}")
    print(f"Saved: {slopes_csv}")
    print(f"Saved: {topology_csv}")
    print(f"Saved: {summary_json}")
    for path in written:
        print(f"Saved: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
