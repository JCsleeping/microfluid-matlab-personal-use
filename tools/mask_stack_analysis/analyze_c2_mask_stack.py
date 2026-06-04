"""Analyze C2 red-mask stacks for strict TOA/front and blob detail metrics."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import h5py
import numpy as np


MASK_TIMESERIES_FIELDS = [
    "frame_index",
    "label",
    "role",
    "RealTime_s",
    "Time_min",
    "mask_grid",
    "processing_scale_factor",
    "mask_height",
    "mask_width",
    "red_mask_area_px_manifest",
    "red_mask_area_px_stack",
    "red_mask_area_fraction_stack",
    "mask_stack_area_delta_px",
    "active_x_min_px",
    "leading_front_x_px",
    "leading_front_fraction",
    "row_front_p10_px",
    "row_front_p50_px",
    "row_front_p90_px",
    "front_roughness_px",
    "active_row_fraction",
    "inlet_band_active_fraction",
    "outlet_band_active_fraction",
    "outlet_band_active_px",
    "outlet_band_breakthrough",
    "finger_count_proxy",
    "finger_band_width_px",
    "toa_new_pixel_count",
    "toa_cumulative_arrived_fraction",
]

BLOB_MORPHOLOGY_FIELDS = [
    "frame_index",
    "label",
    "role",
    "RealTime_s",
    "Time_min",
    "mask_grid",
    "processing_scale_factor",
    "blob_count_detail",
    "blob_area_total_px2",
    "blob_area_max_fraction",
    "blob_area_top3_fraction",
    "AreaGini",
    "AreaEntropy",
    "AspectRatio_median",
    "AspectRatio_p90",
    "AspectRatio_area_weighted_mean",
    "Solidity_median",
    "Solidity_p10",
    "Solidity_area_weighted_mean",
    "EulerNumber_median",
    "EulerNumber_mean",
    "EulerNumber_min",
    "EulerHoleCount_sum",
    "TopologyType_droplet_count_fraction",
    "TopologyType_column_count_fraction",
    "TopologyType_cluster_count_fraction",
    "TopologyType_other_count_fraction",
    "TopologyType_droplet_area_fraction",
    "TopologyType_column_area_fraction",
    "TopologyType_cluster_area_fraction",
    "TopologyType_other_area_fraction",
    "ShapeEntropy_count",
    "ShapeEntropy_area",
]

TOA_X_FIELDS = [
    "x_px",
    "arrived_pixel_count",
    "arrived_fraction",
    "first_arrival_frame_index",
    "first_arrival_time_min",
    "p50_arrival_frame_index",
    "p90_arrival_frame_index",
]


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing required CSV: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_optional_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    return read_csv_rows(path)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: format_value(row.get(field, "")) for field in fieldnames})


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def number(value: object) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return math.nan
    return result if math.isfinite(result) else math.nan


def finite_or_nan(value: object) -> float:
    result = number(value)
    return result if math.isfinite(result) else math.nan


def int_value(value: object, *, default: int = 0) -> int:
    result = number(value)
    return int(round(result)) if math.isfinite(result) else default


def format_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    try:
        result = float(value)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(result):
        return "NaN"
    return f"{result:.12g}"


def percentile(values: np.ndarray | list[float], q: float) -> float:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return math.nan
    return float(np.percentile(arr, q))


def safe_fraction(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else math.nan


def entropy_from_counts(values: list[float]) -> float:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr) & (arr > 0)]
    total = float(arr.sum())
    if total <= 0:
        return math.nan
    p = arr / total
    return float(-np.sum(p * np.log(p)))


def area_gini(values: list[float]) -> float:
    arr = np.sort(np.asarray(values, dtype=float))
    arr = arr[np.isfinite(arr) & (arr >= 0)]
    if arr.size == 0:
        return math.nan
    total = float(arr.sum())
    if total <= 0:
        return 0.0
    index = np.arange(1, arr.size + 1, dtype=float)
    return float(np.sum((2 * index - arr.size - 1) * arr) / (arr.size * total))


def weighted_mean(values: list[float], weights: list[float]) -> float:
    v = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    ok = np.isfinite(v) & np.isfinite(w) & (w > 0)
    if not np.any(ok):
        return math.nan
    return float(np.average(v[ok], weights=w[ok]))


def timeline_lookup(timeline_dir: Path | None) -> dict[str, dict[str, str]]:
    if timeline_dir is None:
        return {}
    rows = read_optional_csv_rows(timeline_dir / "red_mask_timeseries_realtime.csv")
    return {row.get("label", ""): row for row in rows if row.get("label", "")}


def load_stack_manifest(segmentation_dir: Path) -> list[dict[str, str]]:
    rows = read_csv_rows(segmentation_dir / "red_mask_stack_manifest.csv")
    required = {
        "frame_index",
        "label",
        "role",
        "h5_dataset",
        "h5_frame_index",
        "mask_grid",
        "mask_height",
        "mask_width",
        "processing_scale_factor",
        "red_mask_area_px",
        "domain_area_px",
    }
    missing = required - set(rows[0]) if rows else required
    if missing:
        raise ValueError(f"red_mask_stack_manifest.csv missing columns: {', '.join(sorted(missing))}")
    return sorted(rows, key=lambda row: int_value(row.get("frame_index")))


def aligned_mask(dataset: h5py.Dataset, row: dict[str, str]) -> np.ndarray:
    h5_index = int_value(row.get("h5_frame_index")) - 1
    if h5_index < 0 or h5_index >= dataset.shape[0]:
        raise IndexError(f"h5_frame_index out of range: {row.get('h5_frame_index')}")
    mask = np.asarray(dataset[h5_index]) > 0
    expected = (int_value(row.get("mask_height")), int_value(row.get("mask_width")))
    if mask.shape == expected:
        return mask
    if mask.T.shape == expected:
        return mask.T
    raise ValueError(
        "Mask shape does not match manifest: "
        f"h5_frame_index={h5_index + 1} h5_shape={mask.shape} expected={expected}"
    )


def contiguous_true_segments(values: np.ndarray) -> int:
    if values.size == 0:
        return 0
    padded = np.concatenate(([False], values.astype(bool), [False]))
    starts = np.flatnonzero((~padded[:-1]) & padded[1:])
    return int(starts.size)


def time_fields(label: str, frame_index: int, timeline: dict[str, dict[str, str]]) -> dict[str, Any]:
    row = timeline.get(label, {})
    return {
        "RealTime_s": finite_or_nan(row.get("RealTime_s")),
        "Time_min": finite_or_nan(row.get("Time_min")),
        "frame_index": frame_index,
        "label": label,
        "role": row.get("role", ""),
    }


def analyze_stack(
    segmentation_dir: Path,
    timeline_dir: Path | None,
    out_dir: Path,
    *,
    dataset_name: str = "/red_mask",
    column_active_fraction: float = 0.002,
    outlet_band_fraction: float = 0.02,
    outlet_active_fraction_threshold: float = 0.001,
    outlet_active_min_px: int = 10,
    leading_front_breakthrough_fraction: float = 0.98,
    finger_band_fraction: float = 0.03,
) -> dict[str, Any]:
    manifest_rows = load_stack_manifest(segmentation_dir)
    timeline = timeline_lookup(timeline_dir)
    stack_path = segmentation_dir / "red_mask_stack.h5"
    if not stack_path.is_file():
        raise FileNotFoundError(f"Missing red_mask_stack.h5: {stack_path}")

    mask_rows: list[dict[str, Any]] = []
    first_time_by_frame: dict[int, float] = {}
    first_label_by_frame: dict[int, str] = {}
    toa_frame: np.ndarray | None = None
    cumulative_arrived = 0

    with h5py.File(stack_path, "r") as handle:
        if dataset_name not in handle:
            raise KeyError(f"Dataset {dataset_name!r} not found in {stack_path}")
        dataset = handle[dataset_name]
        if dataset.shape[0] < len(manifest_rows):
            raise ValueError(
                f"Mask stack has fewer frames ({dataset.shape[0]}) than manifest rows ({len(manifest_rows)})."
            )
        for manifest_row in manifest_rows:
            frame_index = int_value(manifest_row["frame_index"])
            label = manifest_row["label"]
            role = manifest_row["role"]
            mask = aligned_mask(dataset, manifest_row)
            height, width = mask.shape
            if toa_frame is None:
                toa_frame = np.zeros(mask.shape, dtype=np.int32)
            elif toa_frame.shape != mask.shape:
                raise ValueError(f"Mask shape changed within stack: {mask.shape} vs {toa_frame.shape}")

            new_arrivals = (toa_frame == 0) & mask
            new_count = int(new_arrivals.sum())
            if new_count:
                toa_frame[new_arrivals] = frame_index
                cumulative_arrived += new_count
            time_row = timeline.get(label, {})
            time_min = finite_or_nan(time_row.get("Time_min"))
            if math.isfinite(time_min):
                first_time_by_frame[frame_index] = time_min
            first_label_by_frame[frame_index] = label

            area_stack = int(mask.sum())
            domain_area = finite_or_nan(manifest_row.get("domain_area_px"))
            col_min_px = max(1, int(math.ceil(height * column_active_fraction)))
            column_counts = mask.sum(axis=0)
            active_x = np.flatnonzero(column_counts >= col_min_px)
            active_x_min = float(active_x.min()) if active_x.size else math.nan
            leading_x = float(active_x.max()) if active_x.size else math.nan
            leading_fraction = leading_x / (width - 1) if math.isfinite(leading_x) and width > 1 else math.nan

            row_has_active = mask.any(axis=1)
            row_front = np.array([], dtype=float)
            if np.any(row_has_active):
                reversed_argmax = np.argmax(mask[row_has_active, ::-1], axis=1)
                row_front = (width - 1 - reversed_argmax).astype(float)
            row_p10 = percentile(row_front, 10)
            row_p50 = percentile(row_front, 50)
            row_p90 = percentile(row_front, 90)
            roughness = row_p90 - row_p10 if math.isfinite(row_p90) and math.isfinite(row_p10) else math.nan

            band_width = max(1, int(math.ceil(width * outlet_band_fraction)))
            inlet_band = mask[:, :band_width]
            outlet_band = mask[:, width - band_width :]
            outlet_px = int(outlet_band.sum())
            outlet_fraction = safe_fraction(outlet_px, outlet_band.size)
            inlet_fraction = safe_fraction(int(inlet_band.sum()), inlet_band.size)
            breakthrough = bool(
                outlet_px >= outlet_active_min_px
                and math.isfinite(outlet_fraction)
                and outlet_fraction >= outlet_active_fraction_threshold
            )

            finger_band_width = max(1, int(math.ceil(width * finger_band_fraction)))
            if math.isfinite(leading_x) and row_front.size:
                front_rows = row_front >= max(0.0, leading_x - finger_band_width)
                finger_count = contiguous_true_segments(front_rows)
            else:
                finger_count = 0

            row = {
                **time_fields(label, frame_index, timeline),
                "role": role,
                "mask_grid": manifest_row["mask_grid"],
                "processing_scale_factor": finite_or_nan(manifest_row.get("processing_scale_factor")),
                "mask_height": height,
                "mask_width": width,
                "red_mask_area_px_manifest": finite_or_nan(manifest_row.get("red_mask_area_px")),
                "red_mask_area_px_stack": area_stack,
                "red_mask_area_fraction_stack": area_stack / domain_area if math.isfinite(domain_area) and domain_area > 0 else math.nan,
                "mask_stack_area_delta_px": area_stack - finite_or_nan(manifest_row.get("red_mask_area_px")),
                "active_x_min_px": active_x_min,
                "leading_front_x_px": leading_x,
                "leading_front_fraction": leading_fraction,
                "row_front_p10_px": row_p10,
                "row_front_p50_px": row_p50,
                "row_front_p90_px": row_p90,
                "front_roughness_px": roughness,
                "active_row_fraction": safe_fraction(float(row_has_active.sum()), float(height)),
                "inlet_band_active_fraction": inlet_fraction,
                "outlet_band_active_fraction": outlet_fraction,
                "outlet_band_active_px": outlet_px,
                "outlet_band_breakthrough": breakthrough,
                "finger_count_proxy": finger_count,
                "finger_band_width_px": finger_band_width,
                "toa_new_pixel_count": new_count,
                "toa_cumulative_arrived_fraction": safe_fraction(float(cumulative_arrived), float(toa_frame.size)),
            }
            mask_rows.append(row)

    if toa_frame is None:
        raise ValueError("No mask frames were analyzed.")

    toa_path = out_dir / "toa_frame_index.npy"
    out_dir.mkdir(parents=True, exist_ok=True)
    np.save(toa_path, toa_frame)
    toa_x_rows = build_toa_x_rows(toa_frame, first_time_by_frame)
    write_csv(out_dir / "mask_stack_analysis_timeseries.csv", mask_rows, MASK_TIMESERIES_FIELDS)
    write_csv(out_dir / "toa_x_summary.csv", toa_x_rows, TOA_X_FIELDS)

    breakthrough = breakthrough_summary(
        mask_rows,
        leading_front_breakthrough_fraction=leading_front_breakthrough_fraction,
    )
    return {
        "mask_timeseries_rows": len(mask_rows),
        "toa_frame_index_npy": str(toa_path),
        "toa_x_summary_rows": len(toa_x_rows),
        "breakthrough": breakthrough,
        "first_label_by_frame": first_label_by_frame,
    }


def build_toa_x_rows(toa_frame: np.ndarray, first_time_by_frame: dict[int, float]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    height, width = toa_frame.shape
    for x in range(width):
        values = toa_frame[:, x]
        arrived = values[values > 0]
        first_frame = int(arrived.min()) if arrived.size else 0
        rows.append(
            {
                "x_px": x,
                "arrived_pixel_count": int(arrived.size),
                "arrived_fraction": arrived.size / height if height else math.nan,
                "first_arrival_frame_index": first_frame if first_frame else math.nan,
                "first_arrival_time_min": first_time_by_frame.get(first_frame, math.nan),
                "p50_arrival_frame_index": percentile(arrived, 50) if arrived.size else math.nan,
                "p90_arrival_frame_index": percentile(arrived, 90) if arrived.size else math.nan,
            }
        )
    return rows


def first_row_where(rows: list[dict[str, Any]], predicate: Any) -> dict[str, Any] | None:
    for row in rows:
        if predicate(row):
            return row
    return None


def breakthrough_summary(
    mask_rows: list[dict[str, Any]],
    *,
    leading_front_breakthrough_fraction: float,
) -> dict[str, Any]:
    first_any = first_row_where(mask_rows, lambda row: finite_or_nan(row.get("red_mask_area_px_stack")) > 0)
    first_outlet = first_row_where(mask_rows, lambda row: bool(row.get("outlet_band_breakthrough")))
    first_front = first_row_where(
        mask_rows,
        lambda row: finite_or_nan(row.get("leading_front_fraction")) >= leading_front_breakthrough_fraction,
    )

    def compact(row: dict[str, Any] | None) -> dict[str, Any]:
        if row is None:
            return {}
        return {
            "frame_index": row.get("frame_index"),
            "label": row.get("label"),
            "role": row.get("role"),
            "RealTime_s": row.get("RealTime_s"),
            "Time_min": row.get("Time_min"),
            "leading_front_fraction": row.get("leading_front_fraction"),
            "outlet_band_active_fraction": row.get("outlet_band_active_fraction"),
        }

    return {
        "first_any_red_mask": compact(first_any),
        "first_outlet_band_breakthrough": compact(first_outlet),
        "first_leading_front_breakthrough": compact(first_front),
        "leading_front_breakthrough_fraction": leading_front_breakthrough_fraction,
    }


@dataclass
class BlobAccumulator:
    label: str = ""
    role: str = ""
    mask_grid: str = ""
    processing_scale_factor: float = math.nan
    areas: list[float] = field(default_factory=list)
    aspect_ratios: list[float] = field(default_factory=list)
    solidities: list[float] = field(default_factory=list)
    euler_numbers: list[float] = field(default_factory=list)
    euler_hole_counts: list[float] = field(default_factory=list)
    topology_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    topology_areas: dict[str, float] = field(default_factory=lambda: defaultdict(float))


def topology_bucket(value: object) -> str:
    text = str(value or "").strip().lower()
    if "drop" in text:
        return "droplet"
    if "col" in text:
        return "column"
    if "cluster" in text or "ganglia" in text:
        return "cluster"
    return "other"


def blob_frame_index(row: dict[str, str]) -> int:
    if row.get("frame_index", "") not in {"", "NaN", "nan"}:
        return int_value(row.get("frame_index"))
    value = int_value(row.get("FrameIndex"))
    return value + 1 if value >= 0 else value


def accumulate_blob_detail(blob_csv: Path) -> dict[int, BlobAccumulator]:
    accumulators: dict[int, BlobAccumulator] = defaultdict(BlobAccumulator)
    if not blob_csv.is_file():
        return accumulators
    with blob_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"Area"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{blob_csv} missing required blob columns: {', '.join(sorted(missing))}")
        for row in reader:
            frame = blob_frame_index(row)
            if frame <= 0:
                continue
            acc = accumulators[frame]
            acc.label = row.get("label", acc.label)
            acc.role = row.get("role", acc.role)
            acc.mask_grid = row.get("mask_grid", acc.mask_grid)
            scale = finite_or_nan(row.get("processing_scale_factor"))
            if math.isfinite(scale):
                acc.processing_scale_factor = scale
            area = finite_or_nan(row.get("Area_processing_px2", row.get("Area")))
            if math.isfinite(area) and area > 0:
                acc.areas.append(area)
            for source, target in (
                ("AspectRatio", acc.aspect_ratios),
                ("Solidity", acc.solidities),
                ("EulerNumber", acc.euler_numbers),
                ("EulerHoleCount", acc.euler_hole_counts),
            ):
                value = finite_or_nan(row.get(source))
                if math.isfinite(value):
                    target.append(value)
            bucket = topology_bucket(row.get("TopologyType", row.get("GangliaType", "")))
            acc.topology_counts[bucket] += 1
            if math.isfinite(area) and area > 0:
                acc.topology_areas[bucket] += area
    return accumulators


def summarize_blob_accumulator(
    frame_index: int,
    manifest_row: dict[str, str],
    timeline: dict[str, dict[str, str]],
    acc: BlobAccumulator | None,
) -> dict[str, Any]:
    label = manifest_row.get("label", "")
    role = manifest_row.get("role", "")
    if acc is None:
        acc = BlobAccumulator(label=label, role=role)
    areas = np.asarray(acc.areas, dtype=float)
    total_area = float(np.nansum(areas)) if areas.size else 0.0
    sorted_area = np.sort(areas[np.isfinite(areas) & (areas > 0)])[::-1]

    def topology_fraction(kind: str, source: dict[str, float] | dict[str, int], denominator: float) -> float:
        if denominator <= 0:
            return math.nan
        return float(source.get(kind, 0)) / denominator

    count_total = sum(acc.topology_counts.values())
    area_total = sum(acc.topology_areas.values())
    row = {
        **time_fields(label, frame_index, timeline),
        "role": role,
        "mask_grid": manifest_row.get("mask_grid", acc.mask_grid),
        "processing_scale_factor": finite_or_nan(manifest_row.get("processing_scale_factor", acc.processing_scale_factor)),
        "blob_count_detail": int(sorted_area.size),
        "blob_area_total_px2": total_area,
        "blob_area_max_fraction": sorted_area[0] / total_area if sorted_area.size and total_area > 0 else math.nan,
        "blob_area_top3_fraction": sorted_area[:3].sum() / total_area if sorted_area.size and total_area > 0 else math.nan,
        "AreaGini": area_gini(acc.areas),
        "AreaEntropy": entropy_from_counts(acc.areas),
        "AspectRatio_median": percentile(acc.aspect_ratios, 50),
        "AspectRatio_p90": percentile(acc.aspect_ratios, 90),
        "AspectRatio_area_weighted_mean": weighted_mean(acc.aspect_ratios, acc.areas[: len(acc.aspect_ratios)]),
        "Solidity_median": percentile(acc.solidities, 50),
        "Solidity_p10": percentile(acc.solidities, 10),
        "Solidity_area_weighted_mean": weighted_mean(acc.solidities, acc.areas[: len(acc.solidities)]),
        "EulerNumber_median": percentile(acc.euler_numbers, 50),
        "EulerNumber_mean": float(np.nanmean(acc.euler_numbers)) if acc.euler_numbers else math.nan,
        "EulerNumber_min": float(np.nanmin(acc.euler_numbers)) if acc.euler_numbers else math.nan,
        "EulerHoleCount_sum": float(np.nansum(acc.euler_hole_counts)) if acc.euler_hole_counts else math.nan,
        "ShapeEntropy_count": entropy_from_counts(list(acc.topology_counts.values())),
        "ShapeEntropy_area": entropy_from_counts(list(acc.topology_areas.values())),
    }
    for kind in ("droplet", "column", "cluster", "other"):
        row[f"TopologyType_{kind}_count_fraction"] = topology_fraction(kind, acc.topology_counts, float(count_total))
        row[f"TopologyType_{kind}_area_fraction"] = topology_fraction(kind, acc.topology_areas, float(area_total))
    return row


def analyze_blob_detail(
    segmentation_dir: Path,
    timeline_dir: Path | None,
    out_dir: Path,
    manifest_rows: list[dict[str, str]],
) -> dict[str, Any]:
    timeline = timeline_lookup(timeline_dir)
    blob_csv = segmentation_dir / "red_blob_detail_all_frames.csv"
    accumulators = accumulate_blob_detail(blob_csv)
    rows = [
        summarize_blob_accumulator(
            int_value(manifest_row["frame_index"]),
            manifest_row,
            timeline,
            accumulators.get(int_value(manifest_row["frame_index"])),
        )
        for manifest_row in manifest_rows
    ]
    write_csv(out_dir / "blob_morphology_timeseries.csv", rows, BLOB_MORPHOLOGY_FIELDS)
    return {
        "blob_detail_csv": str(blob_csv) if blob_csv.is_file() else "",
        "blob_morphology_rows": len(rows),
        "blob_detail_frames_with_rows": sum(1 for row in rows if finite_or_nan(row.get("blob_count_detail")) > 0),
    }


def build_summary(
    out_dir: Path,
    segmentation_dir: Path,
    timeline_dir: Path | None,
    stack_summary: dict[str, Any],
    blob_summary: dict[str, Any],
) -> dict[str, Any]:
    outputs = {
        "mask_stack_analysis_timeseries_csv": str(out_dir / "mask_stack_analysis_timeseries.csv"),
        "toa_x_summary_csv": str(out_dir / "toa_x_summary.csv"),
        "toa_frame_index_npy": stack_summary["toa_frame_index_npy"],
        "blob_morphology_timeseries_csv": str(out_dir / "blob_morphology_timeseries.csv"),
        "mask_stack_analysis_summary_json": str(out_dir / "mask_stack_analysis_summary.json"),
    }
    readiness = {
        "mask_stack_ready": stack_summary["mask_timeseries_rows"] > 0,
        "toa_ready": stack_summary["toa_x_summary_rows"] > 0 and Path(stack_summary["toa_frame_index_npy"]).is_file(),
        "mask_front_fingering_ready": stack_summary["mask_timeseries_rows"] > 0,
        "blob_detail_distribution_ready": blob_summary["blob_detail_frames_with_rows"] > 0,
    }
    return {
        "status": "pass" if all(readiness.values()) else "review",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "analysis_policy_version": "mask_stack_strict_toa_fingering_v1",
        "input_paths": {
            "segmentation_dir": str(segmentation_dir),
            "timeline_dir": str(timeline_dir or ""),
        },
        "outputs": outputs,
        "row_counts": {
            "mask_stack_analysis_timeseries": stack_summary["mask_timeseries_rows"],
            "toa_x_summary": stack_summary["toa_x_summary_rows"],
            "blob_morphology_timeseries": blob_summary["blob_morphology_rows"],
            "blob_detail_frames_with_rows": blob_summary["blob_detail_frames_with_rows"],
        },
        "readiness": readiness,
        "breakthrough": stack_summary["breakthrough"],
        "semantics": {
            "TOA": "pixel-level first frame index from C2 red_mask_stack.h5; 0 in the .npy map means never arrived",
            "leading_front_fraction": "rightmost active C2 red-mask column normalized by processing-grid width",
            "finger_count_proxy": "contiguous active row segments within the current leading-front band; mask-stack derived, not pore-graph fingering",
            "AreaGini": "per-frame inequality of C2 per-blob Area_processing_px2 distribution",
        },
    }


def run_analysis(args: argparse.Namespace) -> dict[str, Any]:
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_rows = load_stack_manifest(args.segmentation_dir)
    stack_summary = analyze_stack(
        args.segmentation_dir,
        args.timeline_dir,
        out_dir,
        dataset_name=args.h5_dataset,
        column_active_fraction=args.column_active_fraction,
        outlet_band_fraction=args.outlet_band_fraction,
        outlet_active_fraction_threshold=args.outlet_active_fraction_threshold,
        outlet_active_min_px=args.outlet_active_min_px,
        leading_front_breakthrough_fraction=args.leading_front_breakthrough_fraction,
        finger_band_fraction=args.finger_band_fraction,
    )
    blob_summary = analyze_blob_detail(args.segmentation_dir, args.timeline_dir, out_dir, manifest_rows)
    summary = build_summary(out_dir, args.segmentation_dir, args.timeline_dir, stack_summary, blob_summary)
    write_json(out_dir / "mask_stack_analysis_summary.json", summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segmentation-dir", type=Path, required=True)
    parser.add_argument("--timeline-dir", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--h5-dataset", default="/red_mask")
    parser.add_argument("--column-active-fraction", type=float, default=0.002)
    parser.add_argument("--outlet-band-fraction", type=float, default=0.02)
    parser.add_argument("--outlet-active-fraction-threshold", type=float, default=0.001)
    parser.add_argument("--outlet-active-min-px", type=int, default=10)
    parser.add_argument("--leading-front-breakthrough-fraction", type=float, default=0.98)
    parser.add_argument("--finger-band-fraction", type=float, default=0.03)
    return parser.parse_args()


def main() -> int:
    summary = run_analysis(parse_args())
    print(f"MASK_STACK_ANALYSIS {summary['outputs']['mask_stack_analysis_summary_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
