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
from scipy import ndimage as ndi


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

PHASE_TIMESERIES_FIELDS = [
    "frame_index",
    "label",
    "role",
    "RealTime_s",
    "Time_min",
    "mask_grid",
    "processing_scale_factor",
    "full_baseline_area_px",
    "current_mask_area_px",
    "current_mask_fraction_of_full_baseline",
    "retained_from_full_px",
    "retained_from_full_fraction",
    "depleted_from_full_px",
    "depleted_from_full_fraction",
    "new_outside_full_px",
    "new_outside_full_fraction",
    "residual_cumulative_union_px",
    "residual_cumulative_union_fraction_of_full",
    "phase_is_residual",
]

GEOMETRY_CORE_EDGE_FIELDS = [
    "frame_index",
    "label",
    "role",
    "RealTime_s",
    "Time_min",
    "mask_grid",
    "processing_scale_factor",
    "core_edge_definition",
    "core_flow_min_dist_px",
    "interface_solid_dilation_px",
    "flow_domain_area_px",
    "core_flow_area_px",
    "edge_band_area_px",
    "current_mask_area_px",
    "core_mask_area_px",
    "edge_mask_area_px",
    "core_red_mask_fraction",
    "edge_red_mask_fraction",
    "core_fraction_of_mask",
    "edge_fraction_of_mask",
    "core_to_edge_red_mask_fraction_ratio",
    "core_retained_from_full_px",
    "core_retained_from_full_fraction",
    "edge_retained_from_full_px",
    "edge_retained_from_full_fraction",
    "core_depleted_from_full_fraction",
    "edge_depleted_from_full_fraction",
    "core_dnapl_water_boundary_px",
    "edge_dnapl_water_boundary_px",
    "core_dnapl_solid_boundary_px",
    "edge_dnapl_solid_boundary_px",
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


def read_segmentation_manifest(segmentation_dir: Path) -> dict[str, Any]:
    path = segmentation_dir / "segmentation_manifest.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid segmentation_manifest.json: {path}") from exc


def aligned_flow_domain(raw: np.ndarray, expected_shape: tuple[int, int]) -> np.ndarray:
    mask = np.asarray(raw) > 0
    if mask.shape == expected_shape:
        return mask
    if mask.T.shape == expected_shape:
        return mask.T
    raise ValueError(f"flow_domain_mask shape {mask.shape} does not match expected {expected_shape}")


def load_flow_domain_from_segmentation(
    segmentation_dir: Path,
    expected_shape: tuple[int, int],
) -> tuple[np.ndarray | None, dict[str, Any]]:
    manifest = read_segmentation_manifest(segmentation_dir)
    cache_dir_text = manifest.get("cache_dir", "")
    if not cache_dir_text:
        return None, {
            "geometry_status": "missing_cache_dir",
            "geometry_source": "",
            "interface_solid_dilation_px": math.nan,
        }
    cache_dir = Path(cache_dir_text)
    mask_path = cache_dir / "mask_crop.h5"
    if not mask_path.is_file():
        return None, {
            "geometry_status": "missing_mask_crop_h5",
            "geometry_source": str(mask_path),
            "interface_solid_dilation_px": finite_or_nan(manifest.get("interface_solid_dilation", math.nan)),
        }
    with h5py.File(mask_path, "r") as handle:
        if "flow_domain_mask" not in handle:
            raise KeyError(f"flow_domain_mask dataset not found in {mask_path}")
        flow_domain = aligned_flow_domain(np.asarray(handle["flow_domain_mask"]), expected_shape)
    return flow_domain, {
        "geometry_status": "ok",
        "geometry_source": str(mask_path),
        "interface_solid_dilation_px": finite_or_nan(manifest.get("interface_solid_dilation", 1)),
    }


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
    core_flow_min_dist_px: float = 3.0,
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
    full_seen_count: np.ndarray | None = None
    residual_seen_count: np.ndarray | None = None
    last_seen_frame: np.ndarray | None = None
    final_residual_mask: np.ndarray | None = None
    full_frame_count = 0
    residual_frame_count = 0
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
                full_seen_count = np.zeros(mask.shape, dtype=np.int32)
                residual_seen_count = np.zeros(mask.shape, dtype=np.int32)
                last_seen_frame = np.zeros(mask.shape, dtype=np.int32)
                final_residual_mask = np.zeros(mask.shape, dtype=bool)
            elif toa_frame.shape != mask.shape:
                raise ValueError(f"Mask shape changed within stack: {mask.shape} vs {toa_frame.shape}")
            assert full_seen_count is not None
            assert residual_seen_count is not None
            assert last_seen_frame is not None
            assert final_residual_mask is not None

            new_arrivals = (toa_frame == 0) & mask
            new_count = int(new_arrivals.sum())
            if new_count:
                toa_frame[new_arrivals] = frame_index
                cumulative_arrived += new_count
            last_seen_frame[mask] = frame_index
            if role == "full_napl":
                full_seen_count += mask.astype(np.int32)
                full_frame_count += 1
            elif role == "residual":
                residual_seen_count += mask.astype(np.int32)
                final_residual_mask = mask.copy()
                residual_frame_count += 1
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
    assert full_seen_count is not None
    assert residual_seen_count is not None
    assert last_seen_frame is not None
    assert final_residual_mask is not None

    toa_path = out_dir / "toa_frame_index.npy"
    out_dir.mkdir(parents=True, exist_ok=True)
    np.save(toa_path, toa_frame)
    toa_x_rows = build_toa_x_rows(toa_frame, first_time_by_frame)
    phase_outputs = save_phase_maps(
        out_dir,
        full_seen_count=full_seen_count,
        residual_seen_count=residual_seen_count,
        last_seen_frame=last_seen_frame,
        final_residual_mask=final_residual_mask,
        full_frame_count=full_frame_count,
        residual_frame_count=residual_frame_count,
    )
    flow_domain, geometry_metadata = load_flow_domain_from_segmentation(segmentation_dir, toa_frame.shape)
    geometry_context: dict[str, Any] | None = None
    geometry_outputs: dict[str, str] = {}
    if flow_domain is not None:
        interface_dilation = finite_or_nan(geometry_metadata.get("interface_solid_dilation_px"))
        if not math.isfinite(interface_dilation):
            interface_dilation = 1.0
        geometry_context = build_core_edge_context(
            flow_domain,
            core_flow_min_dist_px=core_flow_min_dist_px,
            interface_solid_dilation_px=interface_dilation,
        )
        geometry_outputs = save_core_edge_maps(out_dir, geometry_context)
    with h5py.File(stack_path, "r") as handle:
        dataset = handle[dataset_name]
        phase_rows = build_phase_timeseries_rows(
            dataset,
            manifest_rows,
            timeline,
            full_seen_count=full_seen_count,
        )
        geometry_rows = (
            build_geometry_core_edge_rows(
                dataset,
                manifest_rows,
                timeline,
                full_seen_count=full_seen_count,
                context=geometry_context,
            )
            if geometry_context is not None
            else []
        )
    write_csv(out_dir / "mask_stack_analysis_timeseries.csv", mask_rows, MASK_TIMESERIES_FIELDS)
    write_csv(out_dir / "toa_x_summary.csv", toa_x_rows, TOA_X_FIELDS)
    write_csv(out_dir / "phase_mask_timeseries.csv", phase_rows, PHASE_TIMESERIES_FIELDS)
    write_csv(out_dir / "geometry_core_edge_timeseries.csv", geometry_rows, GEOMETRY_CORE_EDGE_FIELDS)

    breakthrough = breakthrough_summary(
        mask_rows,
        leading_front_breakthrough_fraction=leading_front_breakthrough_fraction,
    )
    phase = phase_summary(
        full_seen_count=full_seen_count,
        residual_seen_count=residual_seen_count,
        final_residual_mask=final_residual_mask,
        full_frame_count=full_frame_count,
        residual_frame_count=residual_frame_count,
    )
    geometry = geometry_core_edge_summary(geometry_rows, geometry_context, geometry_metadata)
    return {
        "mask_timeseries_rows": len(mask_rows),
        "toa_frame_index_npy": str(toa_path),
        "toa_x_summary_rows": len(toa_x_rows),
        "phase_mask_timeseries_rows": len(phase_rows),
        "phase_outputs": phase_outputs,
        "phase_aware": phase,
        "geometry_core_edge_timeseries_rows": len(geometry_rows),
        "geometry_outputs": geometry_outputs,
        "geometry_core_edge": geometry,
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


def finite_stats(values: np.ndarray) -> dict[str, float]:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return {"p10": math.nan, "p50": math.nan, "p90": math.nan, "mean": math.nan}
    return {
        "p10": float(np.percentile(arr, 10)),
        "p50": float(np.percentile(arr, 50)),
        "p90": float(np.percentile(arr, 90)),
        "mean": float(np.mean(arr)),
    }


def save_phase_maps(
    out_dir: Path,
    *,
    full_seen_count: np.ndarray,
    residual_seen_count: np.ndarray,
    last_seen_frame: np.ndarray,
    final_residual_mask: np.ndarray,
    full_frame_count: int,
    residual_frame_count: int,
) -> dict[str, str]:
    full_baseline = full_seen_count > 0
    residual_union = residual_seen_count > 0
    retained_final = full_baseline & final_residual_mask
    transient_residual = full_baseline & residual_union & ~final_residual_mask
    depleted_before_residual = full_baseline & ~residual_union
    new_outside_full = (~full_baseline) & residual_union

    retention_class = np.zeros(full_baseline.shape, dtype=np.uint8)
    retention_class[depleted_before_residual] = 1
    retention_class[transient_residual] = 2
    retention_class[retained_final] = 3
    retention_class[new_outside_full] = 4

    full_frequency = (
        full_seen_count.astype(np.float32) / float(full_frame_count)
        if full_frame_count
        else np.zeros(full_seen_count.shape, dtype=np.float32)
    )
    residual_frequency = (
        residual_seen_count.astype(np.float32) / float(residual_frame_count)
        if residual_frame_count
        else np.zeros(residual_seen_count.shape, dtype=np.float32)
    )
    outputs = {
        "full_baseline_union_mask_npy": out_dir / "full_baseline_union_mask.npy",
        "full_baseline_frequency_npy": out_dir / "full_baseline_frequency.npy",
        "residual_frequency_npy": out_dir / "residual_frequency.npy",
        "residual_persistence_count_npy": out_dir / "residual_persistence_count.npy",
        "last_seen_frame_index_npy": out_dir / "last_seen_frame_index.npy",
        "final_residual_mask_npy": out_dir / "final_residual_mask.npy",
        "phase_retention_class_npy": out_dir / "phase_retention_class.npy",
    }
    np.save(outputs["full_baseline_union_mask_npy"], full_baseline.astype(np.uint8))
    np.save(outputs["full_baseline_frequency_npy"], full_frequency)
    np.save(outputs["residual_frequency_npy"], residual_frequency)
    np.save(outputs["residual_persistence_count_npy"], residual_seen_count.astype(np.int32))
    np.save(outputs["last_seen_frame_index_npy"], last_seen_frame.astype(np.int32))
    np.save(outputs["final_residual_mask_npy"], final_residual_mask.astype(np.uint8))
    np.save(outputs["phase_retention_class_npy"], retention_class)
    return {key: str(value) for key, value in outputs.items()}


def phase_summary(
    *,
    full_seen_count: np.ndarray,
    residual_seen_count: np.ndarray,
    final_residual_mask: np.ndarray,
    full_frame_count: int,
    residual_frame_count: int,
) -> dict[str, Any]:
    full_baseline = full_seen_count > 0
    residual_union = residual_seen_count > 0
    full_area = int(full_baseline.sum())
    residual_union_area = int(residual_union.sum())
    final_area = int(final_residual_mask.sum())
    retained_final = full_baseline & final_residual_mask
    transient_residual = full_baseline & residual_union & ~final_residual_mask
    depleted_before_residual = full_baseline & ~residual_union
    new_outside_full = (~full_baseline) & residual_union
    frequency_values = residual_seen_count[full_baseline].astype(float) / float(residual_frame_count) if residual_frame_count and full_area else np.array([], dtype=float)
    count_values = residual_seen_count[full_baseline].astype(float) if full_area else np.array([], dtype=float)
    frequency_stats = finite_stats(frequency_values)
    count_stats = finite_stats(count_values)
    return {
        "full_frame_count": full_frame_count,
        "residual_frame_count": residual_frame_count,
        "full_baseline_area_px": full_area,
        "residual_union_area_px": residual_union_area,
        "residual_union_fraction_of_full": safe_fraction(float((residual_union & full_baseline).sum()), float(full_area)),
        "new_outside_full_area_px": int(new_outside_full.sum()),
        "new_outside_full_fraction_of_full": safe_fraction(float(new_outside_full.sum()), float(full_area)),
        "final_residual_area_px": final_area,
        "final_residual_retained_from_full_px": int(retained_final.sum()),
        "final_residual_retained_from_full_fraction": safe_fraction(float(retained_final.sum()), float(full_area)),
        "transient_residual_from_full_px": int(transient_residual.sum()),
        "transient_residual_from_full_fraction": safe_fraction(float(transient_residual.sum()), float(full_area)),
        "depleted_before_residual_px": int(depleted_before_residual.sum()),
        "depleted_before_residual_fraction": safe_fraction(float(depleted_before_residual.sum()), float(full_area)),
        "residual_persistence_frequency_p10": frequency_stats["p10"],
        "residual_persistence_frequency_p50": frequency_stats["p50"],
        "residual_persistence_frequency_p90": frequency_stats["p90"],
        "residual_persistence_frequency_mean": frequency_stats["mean"],
        "residual_persistence_count_p10": count_stats["p10"],
        "residual_persistence_count_p50": count_stats["p50"],
        "residual_persistence_count_p90": count_stats["p90"],
        "residual_persistence_count_mean": count_stats["mean"],
    }


def build_phase_timeseries_rows(
    dataset: h5py.Dataset,
    manifest_rows: list[dict[str, str]],
    timeline: dict[str, dict[str, str]],
    *,
    full_seen_count: np.ndarray,
) -> list[dict[str, Any]]:
    full_baseline = full_seen_count > 0
    full_area = int(full_baseline.sum())
    residual_cumulative_union = np.zeros(full_baseline.shape, dtype=bool)
    rows: list[dict[str, Any]] = []
    for manifest_row in manifest_rows:
        frame_index = int_value(manifest_row["frame_index"])
        label = manifest_row["label"]
        role = manifest_row["role"]
        mask = aligned_mask(dataset, manifest_row)
        if mask.shape != full_baseline.shape:
            raise ValueError(f"Mask shape changed within stack: {mask.shape} vs {full_baseline.shape}")
        if role == "residual":
            residual_cumulative_union |= mask

        current_area = int(mask.sum())
        retained = int((mask & full_baseline).sum())
        depleted = full_area - retained
        new_outside = int((mask & ~full_baseline).sum())
        cumulative_retained = int((residual_cumulative_union & full_baseline).sum())
        row = {
            **time_fields(label, frame_index, timeline),
            "role": role,
            "mask_grid": manifest_row["mask_grid"],
            "processing_scale_factor": finite_or_nan(manifest_row.get("processing_scale_factor")),
            "full_baseline_area_px": full_area,
            "current_mask_area_px": current_area,
            "current_mask_fraction_of_full_baseline": safe_fraction(float(current_area), float(full_area)),
            "retained_from_full_px": retained,
            "retained_from_full_fraction": safe_fraction(float(retained), float(full_area)),
            "depleted_from_full_px": depleted,
            "depleted_from_full_fraction": safe_fraction(float(depleted), float(full_area)),
            "new_outside_full_px": new_outside,
            "new_outside_full_fraction": safe_fraction(float(new_outside), float(full_area)),
            "residual_cumulative_union_px": cumulative_retained if role == "residual" else math.nan,
            "residual_cumulative_union_fraction_of_full": safe_fraction(float(cumulative_retained), float(full_area)) if role == "residual" else math.nan,
            "phase_is_residual": role == "residual",
        }
        rows.append(row)
    return rows


def binary_boundary(mask: np.ndarray) -> np.ndarray:
    mask = np.asarray(mask, dtype=bool)
    if not np.any(mask):
        return np.zeros(mask.shape, dtype=bool)
    eroded = ndi.binary_erosion(mask, structure=np.ones((3, 3), dtype=bool), border_value=0)
    return mask & ~eroded


def build_core_edge_context(
    flow_domain: np.ndarray,
    *,
    core_flow_min_dist_px: float,
    interface_solid_dilation_px: float,
) -> dict[str, Any]:
    flow_domain = np.asarray(flow_domain, dtype=bool)
    solid_distance = ndi.distance_transform_edt(flow_domain)
    core_flow = flow_domain & (solid_distance >= core_flow_min_dist_px)
    edge_band = flow_domain & ~core_flow
    solid_contact_zone = flow_domain & (solid_distance <= interface_solid_dilation_px)
    return {
        "flow_domain": flow_domain,
        "solid_distance": solid_distance,
        "core_flow": core_flow,
        "edge_band": edge_band,
        "solid_contact_zone": solid_contact_zone,
        "flow_domain_area_px": int(flow_domain.sum()),
        "core_flow_area_px": int(core_flow.sum()),
        "edge_band_area_px": int(edge_band.sum()),
        "core_flow_min_dist_px": float(core_flow_min_dist_px),
        "interface_solid_dilation_px": float(interface_solid_dilation_px),
        "core_edge_definition": "core_flow=flow_domain&distance_transform_edt(flow_domain)>=core_flow_min_dist_px;edge_band=flow_domain&~core_flow",
    }


def save_core_edge_maps(out_dir: Path, context: dict[str, Any]) -> dict[str, str]:
    outputs = {
        "flow_domain_mask_npy": out_dir / "flow_domain_mask.npy",
        "core_flow_mask_npy": out_dir / "core_flow_mask.npy",
        "edge_band_mask_npy": out_dir / "edge_band_mask.npy",
        "solid_distance_px_npy": out_dir / "solid_distance_px.npy",
        "solid_contact_zone_mask_npy": out_dir / "solid_contact_zone_mask.npy",
    }
    np.save(outputs["flow_domain_mask_npy"], context["flow_domain"].astype(np.uint8))
    np.save(outputs["core_flow_mask_npy"], context["core_flow"].astype(np.uint8))
    np.save(outputs["edge_band_mask_npy"], context["edge_band"].astype(np.uint8))
    np.save(outputs["solid_distance_px_npy"], context["solid_distance"].astype(np.float32))
    np.save(outputs["solid_contact_zone_mask_npy"], context["solid_contact_zone"].astype(np.uint8))
    return {key: str(value) for key, value in outputs.items()}


def build_geometry_core_edge_rows(
    dataset: h5py.Dataset,
    manifest_rows: list[dict[str, str]],
    timeline: dict[str, dict[str, str]],
    *,
    full_seen_count: np.ndarray,
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    flow_domain = context["flow_domain"]
    core_flow = context["core_flow"]
    edge_band = context["edge_band"]
    solid_contact_zone = context["solid_contact_zone"]
    full_baseline = full_seen_count > 0
    core_full_area = int((full_baseline & core_flow).sum())
    edge_full_area = int((full_baseline & edge_band).sum())
    core_area = int(context["core_flow_area_px"])
    edge_area = int(context["edge_band_area_px"])
    rows: list[dict[str, Any]] = []
    for manifest_row in manifest_rows:
        frame_index = int_value(manifest_row["frame_index"])
        label = manifest_row["label"]
        role = manifest_row["role"]
        mask = aligned_mask(dataset, manifest_row) & flow_domain
        if mask.shape != flow_domain.shape:
            raise ValueError(f"Mask shape changed within stack: {mask.shape} vs {flow_domain.shape}")
        boundary = binary_boundary(mask)
        water_boundary = boundary & ~solid_contact_zone
        solid_boundary = boundary & solid_contact_zone
        current_area = int(mask.sum())
        core_mask_area = int((mask & core_flow).sum())
        edge_mask_area = int((mask & edge_band).sum())
        core_retained = int((mask & full_baseline & core_flow).sum())
        edge_retained = int((mask & full_baseline & edge_band).sum())
        core_fraction = safe_fraction(float(core_mask_area), float(core_area))
        edge_fraction = safe_fraction(float(edge_mask_area), float(edge_area))
        row = {
            **time_fields(label, frame_index, timeline),
            "role": role,
            "mask_grid": manifest_row["mask_grid"],
            "processing_scale_factor": finite_or_nan(manifest_row.get("processing_scale_factor")),
            "core_edge_definition": context["core_edge_definition"],
            "core_flow_min_dist_px": context["core_flow_min_dist_px"],
            "interface_solid_dilation_px": context["interface_solid_dilation_px"],
            "flow_domain_area_px": context["flow_domain_area_px"],
            "core_flow_area_px": core_area,
            "edge_band_area_px": edge_area,
            "current_mask_area_px": current_area,
            "core_mask_area_px": core_mask_area,
            "edge_mask_area_px": edge_mask_area,
            "core_red_mask_fraction": core_fraction,
            "edge_red_mask_fraction": edge_fraction,
            "core_fraction_of_mask": safe_fraction(float(core_mask_area), float(current_area)),
            "edge_fraction_of_mask": safe_fraction(float(edge_mask_area), float(current_area)),
            "core_to_edge_red_mask_fraction_ratio": core_fraction / edge_fraction if math.isfinite(core_fraction) and math.isfinite(edge_fraction) and edge_fraction else math.nan,
            "core_retained_from_full_px": core_retained,
            "core_retained_from_full_fraction": safe_fraction(float(core_retained), float(core_full_area)),
            "edge_retained_from_full_px": edge_retained,
            "edge_retained_from_full_fraction": safe_fraction(float(edge_retained), float(edge_full_area)),
            "core_depleted_from_full_fraction": 1 - safe_fraction(float(core_retained), float(core_full_area)) if core_full_area else math.nan,
            "edge_depleted_from_full_fraction": 1 - safe_fraction(float(edge_retained), float(edge_full_area)) if edge_full_area else math.nan,
            "core_dnapl_water_boundary_px": int((water_boundary & core_flow).sum()),
            "edge_dnapl_water_boundary_px": int((water_boundary & edge_band).sum()),
            "core_dnapl_solid_boundary_px": int((solid_boundary & core_flow).sum()),
            "edge_dnapl_solid_boundary_px": int((solid_boundary & edge_band).sum()),
        }
        rows.append(row)
    return rows


def median_finite(rows: list[dict[str, Any]], column: str) -> float:
    values = np.asarray([finite_or_nan(row.get(column)) for row in rows], dtype=float)
    values = values[np.isfinite(values)]
    return float(np.median(values)) if values.size else math.nan


def geometry_core_edge_summary(
    rows: list[dict[str, Any]],
    context: dict[str, Any] | None,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    if context is None:
        return {
            "geometry_status": metadata.get("geometry_status", "not_available"),
            "geometry_source": metadata.get("geometry_source", ""),
            "geometry_core_edge_rows": len(rows),
        }
    residual_rows = [row for row in rows if row.get("role") == "residual"]
    final_residual = residual_rows[-1] if residual_rows else {}
    return {
        "geometry_status": metadata.get("geometry_status", "ok"),
        "geometry_source": metadata.get("geometry_source", ""),
        "geometry_core_edge_rows": len(rows),
        "core_edge_definition": context["core_edge_definition"],
        "core_flow_min_dist_px": context["core_flow_min_dist_px"],
        "interface_solid_dilation_px": context["interface_solid_dilation_px"],
        "flow_domain_area_px": context["flow_domain_area_px"],
        "core_flow_area_px": context["core_flow_area_px"],
        "edge_band_area_px": context["edge_band_area_px"],
        "edge_band_fraction_of_flow_domain": safe_fraction(float(context["edge_band_area_px"]), float(context["flow_domain_area_px"])),
        "residual_core_red_mask_fraction_median": median_finite(residual_rows, "core_red_mask_fraction"),
        "residual_edge_red_mask_fraction_median": median_finite(residual_rows, "edge_red_mask_fraction"),
        "residual_core_to_edge_red_mask_fraction_ratio_median": median_finite(residual_rows, "core_to_edge_red_mask_fraction_ratio"),
        "final_residual_core_retained_from_full_fraction": finite_or_nan(final_residual.get("core_retained_from_full_fraction")),
        "final_residual_edge_retained_from_full_fraction": finite_or_nan(final_residual.get("edge_retained_from_full_fraction")),
        "final_residual_core_depleted_from_full_fraction": finite_or_nan(final_residual.get("core_depleted_from_full_fraction")),
        "final_residual_edge_depleted_from_full_fraction": finite_or_nan(final_residual.get("edge_depleted_from_full_fraction")),
        "boundary_length_semantics": "core/edge boundary fields are C2 boundary-pixel proxies split by geometric region and solid-contact zone",
    }


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
        "phase_mask_timeseries_csv": str(out_dir / "phase_mask_timeseries.csv"),
        "geometry_core_edge_timeseries_csv": str(out_dir / "geometry_core_edge_timeseries.csv"),
        "blob_morphology_timeseries_csv": str(out_dir / "blob_morphology_timeseries.csv"),
        "mask_stack_analysis_summary_json": str(out_dir / "mask_stack_analysis_summary.json"),
    }
    outputs.update(stack_summary.get("phase_outputs", {}))
    outputs.update(stack_summary.get("geometry_outputs", {}))
    readiness = {
        "mask_stack_ready": stack_summary["mask_timeseries_rows"] > 0,
        "toa_ready": stack_summary["toa_x_summary_rows"] > 0 and Path(stack_summary["toa_frame_index_npy"]).is_file(),
        "mask_front_fingering_ready": stack_summary["mask_timeseries_rows"] > 0,
        "phase_aware_mask_ready": stack_summary["phase_mask_timeseries_rows"] > 0
        and stack_summary.get("phase_aware", {}).get("full_baseline_area_px", 0) > 0
        and stack_summary.get("phase_aware", {}).get("residual_frame_count", 0) > 0,
        "geometric_core_edge_ready": stack_summary["geometry_core_edge_timeseries_rows"] > 0
        and stack_summary.get("geometry_core_edge", {}).get("geometry_status") == "ok"
        and stack_summary.get("geometry_core_edge", {}).get("core_flow_area_px", 0) > 0
        and stack_summary.get("geometry_core_edge", {}).get("edge_band_area_px", 0) > 0,
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
            "phase_mask_timeseries": stack_summary["phase_mask_timeseries_rows"],
            "geometry_core_edge_timeseries": stack_summary["geometry_core_edge_timeseries_rows"],
            "blob_morphology_timeseries": blob_summary["blob_morphology_rows"],
            "blob_detail_frames_with_rows": blob_summary["blob_detail_frames_with_rows"],
        },
        "readiness": readiness,
        "breakthrough": stack_summary["breakthrough"],
        "phase_aware": stack_summary["phase_aware"],
        "geometry_core_edge": stack_summary["geometry_core_edge"],
        "semantics": {
            "TOA": "pixel-level first frame index from C2 red_mask_stack.h5; 0 in the .npy map means never arrived",
            "leading_front_fraction": "rightmost active C2 red-mask column normalized by processing-grid width",
            "finger_count_proxy": "contiguous active row segments within the current leading-front band; mask-stack derived, not pore-graph fingering",
            "phase_aware": "full-NAPL union defines the baseline; residual metrics report retained, depleted, transient, and new-outside-full mask support",
            "phase_retention_class": "0 background/not-full-baseline, 1 full baseline absent in residual, 2 residual transient but absent final, 3 retained in final residual, 4 residual outside full baseline",
            "geometric_core_edge": "core_flow and edge_band are split from flow_domain_mask by distance_transform_edt(flow_domain) on the 3X processing grid",
            "core_edge_boundary_px": "core/edge DNAPL-water and DNAPL-solid fields are boundary-pixel proxies, not chain-code MATLAB global L_ow",
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
        core_flow_min_dist_px=getattr(args, "core_flow_min_dist_px", 3.0),
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
    parser.add_argument("--core-flow-min-dist-px", type=float, default=3.0)
    return parser.parse_args()


def main() -> int:
    summary = run_analysis(parse_args())
    print(f"MASK_STACK_ANALYSIS {summary['outputs']['mask_stack_analysis_summary_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
