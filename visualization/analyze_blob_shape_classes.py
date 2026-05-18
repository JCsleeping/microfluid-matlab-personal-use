from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from residual_postprocess_common import ensure_dir, save_figure, timestamp  # noqa: E402


SHAPE_CLASSES = (
    "large_dominant",
    "small_fragment",
    "concave_irregular",
    "elongated",
    "compact_round",
    "ambiguous",
)

SCALAR_USECOLS = [
    "FrameIndex",
    "FrameTime",
    "BlobID",
    "Area",
    "Circularity",
    "Circularity2D",
    "AspectRatio",
    "Solidity",
    "EquivRadius",
]

NUMERIC_COLUMNS = [
    "FrameIndex",
    "FrameTime",
    "BlobID",
    "Area",
    "Circularity2D",
    "AspectRatio",
    "Solidity",
    "EquivRadius",
]

TINY_BLOB_AREA_MAX = 1.0


def available_usecols(blob_csv):
    columns = list(pd.read_csv(blob_csv, nrows=0).columns)
    selected = [c for c in SCALAR_USECOLS if c in columns]
    missing = {"FrameIndex", "Area"} - set(selected)
    if missing:
        raise ValueError(f"Missing required blob scalar column(s): {', '.join(sorted(missing))}")
    return selected


def normalize_blob_chunk(chunk):
    out = chunk.copy()
    if "Circularity2D" not in out.columns:
        if "Circularity" in out.columns:
            out["Circularity2D"] = out["Circularity"]
        else:
            out["Circularity2D"] = np.nan
    if "Circularity" in out.columns:
        out = out.drop(columns=["Circularity"])
    for column in NUMERIC_COLUMNS:
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    if "EquivRadius" not in out.columns:
        area = pd.to_numeric(out["Area"], errors="coerce")
        out["EquivRadius"] = np.sqrt(area.where(area >= 0) / np.pi)
    if "BlobID" not in out.columns:
        out["BlobID"] = np.nan
    return out


def collect_frame_scalars(blob_csv, chunksize=200000):
    usecols = available_usecols(blob_csv)
    total_area = defaultdict(float)
    equiv_radius_parts = defaultdict(list)
    blob_count = defaultdict(int)
    reader = pd.read_csv(blob_csv, usecols=usecols, chunksize=chunksize)
    try:
        for chunk in reader:
            chunk = normalize_blob_chunk(chunk)
            for frame, group in chunk.groupby("FrameIndex", dropna=True):
                frame_key = int(frame)
                area = pd.to_numeric(group["Area"], errors="coerce").to_numpy(dtype=float)
                radius = pd.to_numeric(group["EquivRadius"], errors="coerce").to_numpy(dtype=float)
                total_area[frame_key] += float(np.nansum(area))
                equiv_radius_parts[frame_key].append(radius)
                blob_count[frame_key] += int(len(group))
    finally:
        reader.close()

    radius_p25 = {}
    for frame, parts in equiv_radius_parts.items():
        values = np.concatenate(parts).astype(float) if parts else np.array([], dtype=float)
        values = values[np.isfinite(values)]
        radius_p25[frame] = float(np.percentile(values, 25)) if values.size else np.nan
    return dict(total_area), radius_p25, dict(blob_count), usecols


def projected_sphericity_2d(circularity):
    circ = pd.to_numeric(pd.Series(circularity), errors="coerce").to_numpy(dtype=float)
    out = np.full(circ.shape, np.nan, dtype=float)
    valid = np.isfinite(circ) & (circ >= 0.0) & (circ <= 1.05)
    out[valid] = np.sqrt(circ[valid])
    return out


def regularity_2d_proxy(circularity, projected_sphericity):
    circ = pd.to_numeric(pd.Series(circularity), errors="coerce").to_numpy(dtype=float)
    sph = pd.to_numeric(pd.Series(projected_sphericity), errors="coerce").to_numpy(dtype=float)
    valid_circ = np.isfinite(circ) & (circ >= 0.0) & (circ <= 1.05)
    circ_for_mean = np.where(valid_circ, circ, np.nan)
    out = np.full(circ.shape, np.nan, dtype=float)
    valid_count = np.isfinite(circ_for_mean).astype(int) + np.isfinite(sph).astype(int)
    value_sum = np.nan_to_num(circ_for_mean, nan=0.0) + np.nan_to_num(sph, nan=0.0)
    ok = valid_count > 0
    out[ok] = value_sum[ok] / valid_count[ok]
    return out


def invalid_reasons_for_row(row):
    reasons = []
    circ = row.get("Circularity2D", np.nan)
    area = row.get("Area", np.nan)
    radius = row.get("EquivRadius", np.nan)
    if np.isfinite(circ) and circ > 1.05:
        reasons.append("circularity_gt_1p05")
    elif np.isfinite(circ) and circ < 0.0:
        reasons.append("circularity_negative")
    if (np.isfinite(area) and area <= TINY_BLOB_AREA_MAX) or (np.isfinite(radius) and radius <= 0.0):
        reasons.append("tiny_blob")
    return ";".join(reasons)


def classify_shape_row(row):
    area_frac = row.get("A_blob_Atotal", np.nan)
    radius = row.get("EquivRadius", np.nan)
    frame_radius_p25 = row.get("EquivRadius_frame_p25", np.nan)
    solidity = row.get("Solidity", np.nan)
    aspect = row.get("AspectRatio", np.nan)
    circularity = row.get("Circularity2D", np.nan)
    circularity_valid = np.isfinite(circularity) and 0.0 <= circularity <= 1.05

    if np.isfinite(area_frac) and area_frac >= 0.20:
        return "large_dominant"
    if np.isfinite(radius) and np.isfinite(frame_radius_p25) and radius <= frame_radius_p25:
        return "small_fragment"
    if np.isfinite(solidity) and solidity < 0.80:
        return "concave_irregular"
    if (np.isfinite(aspect) and aspect >= 2.0) or (circularity_valid and circularity < 0.45):
        return "elongated"
    if circularity_valid and circularity >= 0.75 and np.isfinite(solidity) and solidity >= 0.90:
        return "compact_round"
    return "ambiguous"


def classify_blob_chunk(chunk, total_area_by_frame, radius_p25_by_frame):
    out = normalize_blob_chunk(chunk)
    frame_index = pd.to_numeric(out["FrameIndex"], errors="coerce")
    area = pd.to_numeric(out["Area"], errors="coerce")
    total_area = frame_index.map(lambda frame: total_area_by_frame.get(int(frame), np.nan) if np.isfinite(frame) else np.nan)
    out["A_blob_Atotal"] = np.where(total_area > 0, area / total_area, np.nan)
    out["EquivRadius_frame_p25"] = frame_index.map(
        lambda frame: radius_p25_by_frame.get(int(frame), np.nan) if np.isfinite(frame) else np.nan
    )
    out["ProjectedSphericity2D"] = projected_sphericity_2d(out["Circularity2D"])
    out["Regularity2D_proxy"] = regularity_2d_proxy(out["Circularity2D"], out["ProjectedSphericity2D"])
    out["ShapeInvalidReason"] = out.apply(invalid_reasons_for_row, axis=1)
    out["ShapeValid"] = out["ShapeInvalidReason"].eq("")
    out["ShapeClass"] = out.apply(classify_shape_row, axis=1)
    return out


def entropy_from_fractions(values):
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr) & (arr > 0)]
    if arr.size == 0:
        return np.nan
    return float(-np.sum(arr * np.log(arr)))


def area_weighted_mean(values, weights):
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    ok = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if ok.sum() == 0:
        return np.nan
    return float(np.average(values[ok], weights=weights[ok]))


def summarize_frame_group(frame, group):
    frame_key = int(frame)
    area = pd.to_numeric(group["Area"], errors="coerce").to_numpy(dtype=float)
    valid_area = np.where(np.isfinite(area) & (area > 0), area, 0.0)
    total_area = float(np.sum(valid_area))
    total_count = int(len(group))
    row = {
        "FrameIndex": frame_key,
        "BlobCount": total_count,
        "TotalArea_px": total_area,
        "ShapeValidCount": int(group["ShapeValid"].sum()),
        "ShapeInvalidCount": int((~group["ShapeValid"]).sum()),
        "ShapeInvalidFraction": float((~group["ShapeValid"]).sum() / total_count) if total_count else np.nan,
        "Amax_Atotal": float(np.nanmax(group["A_blob_Atotal"])) if total_count else np.nan,
    }
    count_fracs = []
    area_fracs = []
    for shape_class in SHAPE_CLASSES:
        sub = group[group["ShapeClass"] == shape_class]
        count = int(len(sub))
        class_area = float(np.nansum(pd.to_numeric(sub["Area"], errors="coerce")))
        count_frac = float(count / total_count) if total_count else np.nan
        area_frac = float(class_area / total_area) if total_area > 0 else np.nan
        row[f"count_{shape_class}"] = count
        row[f"area_{shape_class}_px"] = class_area
        row[f"areaFrac_{shape_class}"] = area_frac
        row[f"countFrac_{shape_class}"] = count_frac
        count_fracs.append(count_frac)
        area_fracs.append(area_frac)
    row["ShapeEntropy_count"] = entropy_from_fractions(count_fracs)
    row["ShapeEntropy_area"] = entropy_from_fractions(area_fracs)
    for column in ["Circularity2D", "ProjectedSphericity2D", "Regularity2D_proxy", "AspectRatio", "Solidity"]:
        if column in group.columns:
            row[f"{column}_area_weighted_mean"] = area_weighted_mean(group[column], valid_area)
    return row


def summarize_by_frame(by_blob):
    rows = [summarize_frame_group(frame, group) for frame, group in by_blob.groupby("FrameIndex", sort=True)]
    return pd.DataFrame(rows)


def qc_summary(by_blob):
    total = int(len(by_blob))
    invalid = int((~by_blob["ShapeValid"]).sum()) if total else 0
    reasons = by_blob["ShapeInvalidReason"].fillna("").astype(str)
    return pd.DataFrame(
        [
            {
                "analysis_level": "Level A",
                "blob_count": total,
                "invalid_shape_count": invalid,
                "invalid_shape_fraction": float(invalid / total) if total else np.nan,
                "invalid_circularity_gt_1p05_count": int(reasons.str.contains("circularity_gt_1p05", regex=False).sum()),
                "tiny_blob_count": int(reasons.str.contains("tiny_blob", regex=False).sum()),
                "primary_interpretation": "area_fractions",
                "secondary_interpretation": "count_fractions",
                "not_computed": "Wadell roundness, boundary roughness, boundary fractal dimension, tracking metrics",
            }
        ]
    )


def pearson(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 2:
        return np.nan
    x = x[ok]
    y = y[ok]
    if np.nanstd(x) == 0 or np.nanstd(y) == 0:
        return np.nan
    return float(np.corrcoef(x, y)[0, 1])


def spearman(x, y):
    xs = pd.Series(x, dtype="float64").rank(method="average")
    ys = pd.Series(y, dtype="float64").rank(method="average")
    return pearson(xs, ys)


def rate_columns(rates):
    numeric = [c for c in rates.columns if pd.api.types.is_numeric_dtype(rates[c])]
    candidates = [c for c in numeric if "rate" in c.lower()]
    return candidates


def shape_metric_columns(summary):
    prefixes = ("areaFrac_", "countFrac_", "ShapeEntropy_", "Circularity2D_", "ProjectedSphericity2D_", "Regularity2D_proxy_", "AspectRatio_", "Solidity_")
    return [c for c in summary.columns if c.startswith(prefixes)]


def compute_rate_associations(summary, dissolution_rates_csv=None):
    columns = ["rate_column", "metric", "n", "pearson_r", "spearman_r"]
    if not dissolution_rates_csv:
        return pd.DataFrame(columns=columns)
    path = Path(dissolution_rates_csv)
    if not path.exists():
        return pd.DataFrame(columns=columns)
    rates = pd.read_csv(path)
    if "FrameIndex" not in rates.columns:
        return pd.DataFrame(columns=columns)
    merged = pd.merge(summary, rates, on="FrameIndex", how="inner", suffixes=("", "_rate"))
    rows = []
    for rate_col in rate_columns(rates):
        for metric in shape_metric_columns(summary):
            x = pd.to_numeric(merged[rate_col], errors="coerce")
            y = pd.to_numeric(merged[metric], errors="coerce")
            ok = np.isfinite(x) & np.isfinite(y)
            rows.append(
                {
                    "rate_column": rate_col,
                    "metric": metric,
                    "n": int(ok.sum()),
                    "pearson_r": pearson(x, y),
                    "spearman_r": spearman(x, y),
                }
            )
    return pd.DataFrame(rows, columns=columns)


def analyze_blob_shape_classes(blob_csv, chunksize=200000, dissolution_rates_csv=None):
    blob_csv = Path(blob_csv)
    total_area_by_frame, radius_p25_by_frame, _, usecols = collect_frame_scalars(blob_csv, chunksize=chunksize)
    chunks = []
    reader = pd.read_csv(blob_csv, usecols=usecols, chunksize=chunksize)
    try:
        for chunk in reader:
            chunks.append(classify_blob_chunk(chunk, total_area_by_frame, radius_p25_by_frame))
    finally:
        reader.close()
    by_blob = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
    preferred = [
        "FrameIndex",
        "FrameTime",
        "BlobID",
        "Area",
        "A_blob_Atotal",
        "EquivRadius",
        "EquivRadius_frame_p25",
        "Circularity2D",
        "ProjectedSphericity2D",
        "Regularity2D_proxy",
        "AspectRatio",
        "Solidity",
        "ShapeClass",
        "ShapeValid",
        "ShapeInvalidReason",
    ]
    by_blob = by_blob[[c for c in preferred if c in by_blob.columns]]
    summary = summarize_by_frame(by_blob) if not by_blob.empty else pd.DataFrame()
    associations = compute_rate_associations(summary, dissolution_rates_csv=dissolution_rates_csv)
    qc = qc_summary(by_blob)
    return by_blob, summary, associations, qc


def make_output_dir(postprocess_dir, explicit=None, overwrite=False):
    postprocess_dir = ensure_dir(postprocess_dir)
    if explicit:
        out = Path(explicit)
        if not out.is_absolute():
            out = postprocess_dir / out
    else:
        out = postprocess_dir / f"blob_shape_classes_{timestamp()}"
    if out.exists() and any(out.iterdir()) and not overwrite:
        raise FileExistsError(f"Shape-class output directory already exists and is not empty: {out}")
    return ensure_dir(out)


def create_figures(summary, output_dir, dpi=300):
    figures_dir = ensure_dir(Path(output_dir) / "figures_shape_classes")
    paths = []
    if summary.empty:
        return paths

    fig, ax = plt.subplots(figsize=(8, 4))
    for shape_class in SHAPE_CLASSES:
        col = f"areaFrac_{shape_class}"
        if col in summary.columns:
            ax.plot(summary["FrameIndex"], summary[col], label=shape_class)
    ax.set_xlabel("FrameIndex")
    ax.set_ylabel("Shape-class area fraction")
    ax.legend(frameon=False, fontsize=8, ncol=2)
    paths.extend(save_figure(fig, figures_dir, "01_shape_area_fractions", dpi=dpi))

    fig, ax = plt.subplots(figsize=(8, 4))
    for col in ["ShapeEntropy_area", "ShapeEntropy_count"]:
        if col in summary.columns:
            ax.plot(summary["FrameIndex"], summary[col], label=col)
    ax.set_xlabel("FrameIndex")
    ax.set_ylabel("Shape-class entropy")
    ax.legend(frameon=False, fontsize=8)
    paths.extend(save_figure(fig, figures_dir, "02_shape_entropy", dpi=dpi))
    return paths


def run_analysis(args):
    postprocess_dir = Path(args.postprocess_dir)
    output_dir = make_output_dir(postprocess_dir, args.output_dir, overwrite=args.overwrite)
    by_blob, summary, associations, qc = analyze_blob_shape_classes(
        args.blob_csv,
        chunksize=args.chunksize,
        dissolution_rates_csv=args.dissolution_rates_csv,
    )
    by_blob.to_csv(output_dir / "blob_shape_class_by_blob.csv", index=False)
    summary.to_csv(output_dir / "blob_shape_class_summary_by_frame.csv", index=False)
    associations.to_csv(output_dir / "blob_shape_rate_associations.csv", index=False)
    qc.to_csv(output_dir / "blob_shape_qc_summary.csv", index=False)
    ensure_dir(output_dir / "figures_shape_classes")
    if not args.no_figures:
        create_figures(summary, output_dir, dpi=args.dpi)
    return output_dir


def build_parser():
    parser = argparse.ArgumentParser(description="Analyze Level A scalar-only blob shape classes.")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--postprocess-dir", required=True)
    parser.add_argument("--blob-csv", required=True)
    parser.add_argument("--dissolution-rates-csv", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--chunksize", type=int, default=200000)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--no-figures", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    output_dir = run_analysis(args)
    print(f"Blob shape-class directory: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
