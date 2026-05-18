from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from residual_postprocess_common import ensure_dir, finite_stats, save_figure  # noqa: E402


USECOLS = [
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
    "Centroid_X",
    "Centroid_Y",
    "GangliaType",
    "TopologyType",
]

NUMERIC_COLUMNS = [
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
    "Centroid_X",
    "Centroid_Y",
]

TOPOLOGY_CLASSES = ("Droplets", "Columns", "Clusters", "Other")


def available_usecols(blob_csv):
    columns = list(pd.read_csv(blob_csv, nrows=0).columns)
    selected = [c for c in USECOLS if c in columns]
    missing = {"FrameIndex", "Area"} - set(selected)
    if missing:
        raise ValueError(f"Missing required blob-detail column(s): {', '.join(sorted(missing))}")
    return selected


def normalize_topology(value):
    text = str(value).strip().lower()
    if "droplet" in text:
        return "Droplets"
    if "column" in text:
        return "Columns"
    if "cluster" in text or "ganglia" in text:
        return "Clusters"
    return "Other"


def append_frame_values(store, topology_store, chunk):
    chunk = chunk.copy()
    for column in NUMERIC_COLUMNS:
        if column in chunk.columns:
            chunk[column] = pd.to_numeric(chunk[column], errors="coerce")
    if "Circularity" in chunk.columns:
        chunk["Circularity2D"] = pd.to_numeric(chunk["Circularity"], errors="coerce")
    else:
        chunk["Circularity2D"] = np.nan
    if "EquivRadius" not in chunk.columns:
        chunk["EquivRadius"] = np.sqrt(pd.to_numeric(chunk["Area"], errors="coerce") / np.pi)
    topo_col = "TopologyType" if "TopologyType" in chunk.columns else ("GangliaType" if "GangliaType" in chunk.columns else None)
    if topo_col:
        chunk["TopologyClass"] = chunk[topo_col].map(normalize_topology)
    else:
        chunk["TopologyClass"] = "Other"

    for frame, group in chunk.groupby("FrameIndex", dropna=True):
        frame_key = int(frame)
        for column in ["Area", "Perimeter", "EquivRadius", "Circularity2D", "AspectRatio", "Solidity"]:
            if column in group.columns:
                store[frame_key][column].append(pd.to_numeric(group[column], errors="coerce").to_numpy(dtype=float))
        for cls in TOPOLOGY_CLASSES:
            sub = group[group["TopologyClass"] == cls]
            topology_store[frame_key][f"count{cls}"] += int(len(sub))
            topology_store[frame_key][f"area{cls}_px"] += float(pd.to_numeric(sub["Area"], errors="coerce").sum())


def normalize_blob_chunk(chunk):
    chunk = chunk.copy()
    for column in NUMERIC_COLUMNS:
        if column in chunk.columns:
            chunk[column] = pd.to_numeric(chunk[column], errors="coerce")
    if "Circularity" in chunk.columns:
        chunk["Circularity2D"] = pd.to_numeric(chunk["Circularity"], errors="coerce")
    else:
        chunk["Circularity2D"] = np.nan
    if "EquivRadius" not in chunk.columns:
        chunk["EquivRadius"] = np.sqrt(pd.to_numeric(chunk["Area"], errors="coerce") / np.pi)
    topo_col = "TopologyType" if "TopologyType" in chunk.columns else ("GangliaType" if "GangliaType" in chunk.columns else None)
    if topo_col:
        chunk["TopologyClass"] = chunk[topo_col].map(normalize_topology)
    else:
        chunk["TopologyClass"] = "Other"
    return chunk


def area_weighted_mean(values, weights):
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    finite = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if finite.sum() == 0:
        return np.nan
    return float(np.average(values[finite], weights=weights[finite]))


def concat_values(parts):
    if not parts:
        return np.array([], dtype=float)
    return np.concatenate(parts).astype(float)


def compute_frame_summary(store):
    rows = []
    for frame in sorted(store):
        values = {name: concat_values(parts) for name, parts in store[frame].items()}
        area = values.get("Area", np.array([], dtype=float))
        row = {
            "FrameIndex": frame,
            "BlobCount": int(np.isfinite(area).sum()),
            "TotalArea_px": float(np.nansum(area)) if area.size else 0.0,
            "Amax_Atotal": float(np.nanmax(area) / np.nansum(area)) if area.size and np.nansum(area) > 0 else np.nan,
        }
        for column, prefix in [
            ("Area", "Area"),
            ("EquivRadius", "EquivRadius"),
            ("Circularity2D", "Circularity2D"),
            ("AspectRatio", "AspectRatio"),
            ("Solidity", "Solidity"),
        ]:
            stats = finite_stats(values.get(column, np.array([], dtype=float)))
            for stat_name, stat_value in stats.items():
                row[f"{prefix}_{stat_name}"] = stat_value
            if column not in ("Area", "EquivRadius"):
                row[f"{prefix}_area_weighted_mean"] = area_weighted_mean(values.get(column, []), area)
        rows.append(row)
    return pd.DataFrame(rows)


def summarize_frame_group(frame, group):
    frame_key = int(frame)
    area = pd.to_numeric(group["Area"], errors="coerce").to_numpy(dtype=float)
    row = {
        "FrameIndex": frame_key,
        "BlobCount": int(np.isfinite(area).sum()),
        "TotalArea_px": float(np.nansum(area)) if area.size else 0.0,
        "Amax_Atotal": float(np.nanmax(area) / np.nansum(area)) if area.size and np.nansum(area) > 0 else np.nan,
    }
    for column, prefix in [
        ("Area", "Area"),
        ("EquivRadius", "EquivRadius"),
        ("Circularity2D", "Circularity2D"),
        ("AspectRatio", "AspectRatio"),
        ("Solidity", "Solidity"),
    ]:
        values = pd.to_numeric(group[column], errors="coerce").to_numpy(dtype=float) if column in group.columns else np.array([])
        stats = finite_stats(values)
        for stat_name, stat_value in stats.items():
            row[f"{prefix}_{stat_name}"] = stat_value
        if column not in ("Area", "EquivRadius"):
            row[f"{prefix}_area_weighted_mean"] = area_weighted_mean(values, area)
    return row


def compute_topology_table(topology_store):
    rows = []
    for frame in sorted(topology_store):
        entry = topology_store[frame]
        total_count = sum(entry.get(f"count{cls}", 0) for cls in TOPOLOGY_CLASSES)
        total_area = sum(entry.get(f"area{cls}_px", 0.0) for cls in TOPOLOGY_CLASSES)
        row = {"FrameIndex": frame, "BlobCount": int(total_count), "TotalArea_px": float(total_area)}
        for cls in TOPOLOGY_CLASSES:
            count = entry.get(f"count{cls}", 0)
            area = entry.get(f"area{cls}_px", 0.0)
            row[f"count{cls}"] = int(count)
            row[f"countFrac{cls}"] = float(count / total_count) if total_count else np.nan
            row[f"area{cls}_px"] = float(area)
            row[f"areaFrac{cls}"] = float(area / total_area) if total_area else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def summarize_topology_group(frame, group):
    frame_key = int(frame)
    total_count = int(len(group))
    total_area = float(pd.to_numeric(group["Area"], errors="coerce").sum())
    row = {"FrameIndex": frame_key, "BlobCount": total_count, "TotalArea_px": total_area}
    for cls in TOPOLOGY_CLASSES:
        sub = group[group["TopologyClass"] == cls]
        count = int(len(sub))
        area = float(pd.to_numeric(sub["Area"], errors="coerce").sum())
        row[f"count{cls}"] = count
        row[f"countFrac{cls}"] = float(count / total_count) if total_count else np.nan
        row[f"area{cls}_px"] = area
        row[f"areaFrac{cls}"] = float(area / total_area) if total_area else np.nan
    return row


def compute_size_distribution_slopes_from_store(store, q_low=0.10, q_high=0.90, min_slope_points=20):
    rows = []
    for frame in sorted(store):
        req = concat_values(store[frame].get("EquivRadius", []))
        if req.size == 0:
            area = concat_values(store[frame].get("Area", []))
            req = np.sqrt(area / np.pi)
        req = req[np.isfinite(req) & (req > 0)]
        req.sort()
        if req.size < min_slope_points:
            rows.append(
                {
                    "FrameIndex": frame,
                    "FitN": int(req.size),
                    "Slope_logN_gt_Req_vs_logReq": np.nan,
                    "Intercept": np.nan,
                    "R2": np.nan,
                    "FitReqMin": float(req[0]) if req.size else np.nan,
                    "FitReqMax": float(req[-1]) if req.size else np.nan,
                    "FractalProxyOnly": True,
                }
            )
            continue
        lo = np.quantile(req, q_low)
        hi = np.quantile(req, q_high)
        fit_req = req[(req >= lo) & (req <= hi)]
        if fit_req.size < min_slope_points:
            fit_req = req
        unique_req = np.unique(fit_req)
        counts = np.array([(req >= value).sum() for value in unique_req], dtype=float)
        valid = (unique_req > 0) & (counts > 0)
        x = np.log(unique_req[valid])
        y = np.log(counts[valid])
        if x.size < 2:
            slope = intercept = r2 = np.nan
        else:
            slope, intercept = np.polyfit(x, y, 1)
            pred = slope * x + intercept
            ss_res = np.sum((y - pred) ** 2)
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
        rows.append(
            {
                "FrameIndex": frame,
                "FitN": int(req.size),
                "Slope_logN_gt_Req_vs_logReq": float(slope) if np.isfinite(slope) else np.nan,
                "Intercept": float(intercept) if np.isfinite(intercept) else np.nan,
                "R2": float(r2) if np.isfinite(r2) else np.nan,
                "FitReqMin": float(np.nanmin(fit_req)) if fit_req.size else np.nan,
                "FitReqMax": float(np.nanmax(fit_req)) if fit_req.size else np.nan,
                "FractalProxyOnly": True,
            }
        )
    return pd.DataFrame(rows)


def summarize_slope_group(frame, group, q_low=0.10, q_high=0.90, min_slope_points=20):
    frame_key = int(frame)
    if "EquivRadius" in group.columns:
        req = pd.to_numeric(group["EquivRadius"], errors="coerce").to_numpy(dtype=float)
    else:
        area = pd.to_numeric(group["Area"], errors="coerce").to_numpy(dtype=float)
        req = np.sqrt(area / np.pi)
    req = req[np.isfinite(req) & (req > 0)]
    req.sort()
    base = {
        "FrameIndex": frame_key,
        "FitN": int(req.size),
        "FitReqMin": float(req[0]) if req.size else np.nan,
        "FitReqMax": float(req[-1]) if req.size else np.nan,
        "FractalProxyOnly": True,
    }
    if req.size < min_slope_points:
        base.update({"Slope_logN_gt_Req_vs_logReq": np.nan, "Intercept": np.nan, "R2": np.nan})
        return base
    lo = np.quantile(req, q_low)
    hi = np.quantile(req, q_high)
    fit_req = req[(req >= lo) & (req <= hi)]
    if fit_req.size < min_slope_points:
        fit_req = req
    unique_req = np.unique(fit_req)
    counts = np.array([(req >= value).sum() for value in unique_req], dtype=float)
    valid = (unique_req > 0) & (counts > 0)
    x = np.log(unique_req[valid])
    y = np.log(counts[valid])
    if x.size < 2:
        slope = intercept = r2 = np.nan
    else:
        slope, intercept = np.polyfit(x, y, 1)
        pred = slope * x + intercept
        ss_res = np.sum((y - pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
    base.update(
        {
            "Slope_logN_gt_Req_vs_logReq": float(slope) if np.isfinite(slope) else np.nan,
            "Intercept": float(intercept) if np.isfinite(intercept) else np.nan,
            "R2": float(r2) if np.isfinite(r2) else np.nan,
            "FitReqMin": float(np.nanmin(fit_req)) if fit_req.size else np.nan,
            "FitReqMax": float(np.nanmax(fit_req)) if fit_req.size else np.nan,
        }
    )
    return base


def assert_grouped_frame_order(chunk):
    frames = pd.to_numeric(chunk["FrameIndex"], errors="coerce").dropna().to_numpy(dtype=float)
    if frames.size > 1 and np.any(np.diff(frames) < 0):
        raise ValueError("blob_detail_all_frames.csv is not grouped by FrameIndex; cannot stream safely")


def analyze_blob_population(blob_csv, chunksize=200000, min_slope_points=20, q_low=0.10, q_high=0.90):
    blob_csv = Path(blob_csv)
    usecols = available_usecols(blob_csv)
    frame_rows = []
    topology_rows = []
    slope_rows = []
    carryover = pd.DataFrame()
    last_finalized_frame = -np.inf
    reader = pd.read_csv(blob_csv, usecols=usecols, chunksize=chunksize)
    try:
        for chunk in reader:
            chunk = normalize_blob_chunk(chunk)
            if not carryover.empty:
                chunk = pd.concat([carryover, chunk], ignore_index=True)
            assert_grouped_frame_order(chunk)
            frame_values = pd.to_numeric(chunk["FrameIndex"], errors="coerce")
            if frame_values.dropna().empty:
                carryover = pd.DataFrame()
                continue
            open_frame = frame_values.max()
            complete = chunk[frame_values != open_frame]
            carryover = chunk[frame_values == open_frame].copy()
            for frame, group in complete.groupby("FrameIndex", sort=True):
                if frame <= last_finalized_frame:
                    raise ValueError("blob_detail_all_frames.csv is not grouped by FrameIndex; cannot stream safely")
                frame_rows.append(summarize_frame_group(frame, group))
                topology_rows.append(summarize_topology_group(frame, group))
                slope_rows.append(summarize_slope_group(frame, group, q_low=q_low, q_high=q_high, min_slope_points=min_slope_points))
                last_finalized_frame = frame
    finally:
        reader.close()
    if not carryover.empty:
        for frame, group in carryover.groupby("FrameIndex", sort=True):
            if frame <= last_finalized_frame:
                raise ValueError("blob_detail_all_frames.csv is not grouped by FrameIndex; cannot stream safely")
            frame_rows.append(summarize_frame_group(frame, group))
            topology_rows.append(summarize_topology_group(frame, group))
            slope_rows.append(summarize_slope_group(frame, group, q_low=q_low, q_high=q_high, min_slope_points=min_slope_points))
            last_finalized_frame = frame
    frame_summary = pd.DataFrame(frame_rows)
    topology = pd.DataFrame(topology_rows)
    slopes = pd.DataFrame(slope_rows)
    return frame_summary, topology, slopes


def create_figures(frame_summary, topology, slopes, figures_dir, dpi=300):
    figures_dir = ensure_dir(figures_dir)
    paths = []
    if not frame_summary.empty:
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.plot(frame_summary["FrameIndex"], frame_summary["TotalArea_px"], label="Total area")
        ax.set_xlabel("FrameIndex")
        ax.set_ylabel("Total area (px)")
        paths.extend(save_figure(fig, figures_dir, "01_total_area_by_frame", dpi))

        fig, ax = plt.subplots(figsize=(7, 4))
        for col in ["Circularity2D_area_weighted_mean", "AspectRatio_area_weighted_mean", "Solidity_area_weighted_mean"]:
            if col in frame_summary.columns:
                ax.plot(frame_summary["FrameIndex"], frame_summary[col], label=col)
        ax.set_xlabel("FrameIndex")
        ax.set_ylabel("Area-weighted metric")
        ax.legend(frameon=False, fontsize=8)
        paths.extend(save_figure(fig, figures_dir, "02_shape_metrics_area_weighted", dpi))

    if not topology.empty:
        fig, ax = plt.subplots(figsize=(7, 4))
        for cls in ["Droplets", "Columns", "Clusters"]:
            col = f"areaFrac{cls}"
            if col in topology.columns:
                ax.plot(topology["FrameIndex"], topology[col], label=cls)
        ax.set_xlabel("FrameIndex")
        ax.set_ylabel("Topology area fraction")
        ax.legend(frameon=False, fontsize=8)
        paths.extend(save_figure(fig, figures_dir, "03_topology_area_fractions", dpi))

    if not slopes.empty:
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.plot(slopes["FrameIndex"], slopes["Slope_logN_gt_Req_vs_logReq"])
        ax.set_xlabel("FrameIndex")
        ax.set_ylabel("Size-distribution slope")
        paths.extend(save_figure(fig, figures_dir, "04_size_distribution_slope_vs_time", dpi))
    return paths


def write_blob_population_outputs(blob_csv, postprocess_dir, chunksize=200000, dpi=300, no_figures=False, min_slope_points=20):
    postprocess_dir = ensure_dir(postprocess_dir)
    frame_summary, topology, slopes = analyze_blob_population(
        blob_csv,
        chunksize=chunksize,
        min_slope_points=min_slope_points,
    )
    frame_summary.to_csv(postprocess_dir / "blob_population_morphology_by_frame.csv", index=False)
    topology.to_csv(postprocess_dir / "topology_population_by_frame.csv", index=False)
    slopes.to_csv(postprocess_dir / "size_distribution_slope_vs_time.csv", index=False)
    figures = []
    if not no_figures:
        figures = create_figures(frame_summary, topology, slopes, postprocess_dir / "figures_blob_population", dpi=dpi)
    else:
        ensure_dir(postprocess_dir / "figures_blob_population")
    return {"frame_summary": frame_summary, "topology": topology, "slopes": slopes, "figures": figures}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Analyze per-frame blob population morphology.")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--postprocess-dir", required=True)
    parser.add_argument("--blob-csv", required=True)
    parser.add_argument("--chunksize", type=int, default=200000)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--no-figures", action="store_true")
    args = parser.parse_args(argv)
    write_blob_population_outputs(
        args.blob_csv,
        args.postprocess_dir,
        chunksize=args.chunksize,
        dpi=args.dpi,
        no_figures=args.no_figures,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
