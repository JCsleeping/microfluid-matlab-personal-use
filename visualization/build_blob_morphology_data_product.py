"""Helpers for the G21 blob morphology data product.

This module starts with the sidecar-native schema and classification helpers
used by the streaming builder added in later plan tasks.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


SCOPE_LANGUAGE = (
    "full-duration 2D projected blob morphology data product from sidecar; "
    "not tracking, fractal analysis, 3D roughness, or true fluid-fluid interfacial area"
)
DATASET_SUBSET_NAME = "full_duration_sidecar"

REQUIRED_SIDECAR_FILES = (
    "geometry_by_blob.csv",
    "geometry_summary_by_frame.csv",
    "geometry_qc_summary.csv",
    "geometry_provenance.json",
    "geometry_level_a_comparison_all_frames.csv",
    "geometry_discrepancy_diagnostics_all_frames.csv",
)

OPTIONAL_SIDECAR_FILES = ("geometry_sidecar_manifest.csv",)

OUTPUT_FILENAMES = (
    "blob_morphology_by_blob.csv",
    "blob_morphology_by_frame.csv",
    "blob_reliability_summary_by_frame.csv",
    "blob_morphology_reliability_by_tier.csv",
    "blob_shape_class_by_blob.csv",
    "blob_shape_class_summary_by_frame.csv",
    "blob_morphology_thresholds.json",
    "representative_blob_candidates.csv",
    "blob_morphology_manifest.json",
    "blob_morphology_qc_summary.md",
    "blob_morphology_qc_summary.csv",
)

SHAPE_THRESHOLD_METRICS = (
    "ProjectedSphericity2D",
    "AspectRatio01",
    "AxisAspectRatio",
    "Solidity2D",
    "ProjectedRoughness_boundary",
    "PtotalOverPouter",
    "ProjectedRegularity2D",
)

SUMMARY_MEDIAN_METRICS = (
    "ProjectedSphericity2D",
    "Circularity2D_boundary",
    "AspectRatio01",
    "AxisAspectRatio",
    "Solidity2D",
    "ProjectedRoughness_boundary",
    "PtotalOverPouter",
    "ProjectedRegularity2D",
)

FRAME_MORPHOLOGY_MEDIAN_METRICS = (
    "ProjectedRegularity2D",
    "ProjectedSphericity2D",
    "AspectRatio01",
    "Solidity2D",
    "Circularity2D_boundary",
    "ProjectedRoughness_boundary",
)

RELIABILITY_CLASSES = (
    ("high_confidence", "HighConfidenceCount"),
    ("geometry_valid", "GeometryValidCount"),
    ("count_only_small", "CountOnlySmallCount"),
    ("boundary_invalid", "BoundaryInvalidCount"),
)

REPRESENTATIVE_CANDIDATE_COLUMNS = [
    "FrameIndex",
    "BlobID",
    "ShapeClass",
    "Area_px",
    "AreaTier",
    "ProjectedSphericity2D",
    "Circularity2D_boundary",
    "AspectRatio01",
    "AxisAspectRatio",
    "Solidity2D",
    "ProjectedRoughness_boundary",
    "PtotalOverPouter",
    "ProjectedRegularity2D",
    "MaskPath",
    "LabelPath",
    "ExemplarType",
    "SelectionReason",
]

SHAPE_QUANTILES = {
    "q25": 0.25,
    "q50": 0.50,
    "q75": 0.75,
    "q90": 0.90,
}


class SidecarValidation:
    def __init__(self, sidecar_dir: Path, paths: dict[str, Path], qc_metrics: dict[str, object]):
        self.sidecar_dir = sidecar_dir
        self.paths = paths
        self.qc_metrics = qc_metrics


def _numeric(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype="float64")
    return pd.to_numeric(df[column], errors="coerce")


def _bool_series(df: pd.DataFrame, column: str, default: bool = False) -> pd.Series:
    if column not in df.columns:
        return pd.Series(default, index=df.index, dtype="bool")
    values = df[column]
    if pd.api.types.is_bool_dtype(values):
        return values.fillna(default).astype(bool)
    if pd.api.types.is_numeric_dtype(values):
        return values.fillna(int(default)).astype(bool)
    normalized = values.astype(str).str.strip().str.lower()
    result = normalized.isin({"true", "1", "yes", "y", "t"})
    false_like = normalized.isin({"false", "0", "no", "n", "f", "", "nan", "none"})
    return result.where(result | false_like, default).astype(bool)


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    numerator_values = pd.to_numeric(numerator, errors="coerce").astype("float64")
    denominator_values = pd.to_numeric(denominator, errors="coerce").astype("float64")
    result = numerator_values / denominator_values.replace(0, np.nan)
    return result.replace([np.inf, -np.inf], np.nan)


def add_projected_shape_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Add sidecar-derived projected 2D morphology metrics."""
    out = df.copy()
    area = _numeric(out, "Area_px")
    major = _numeric(out, "MajorAxisLength_px")
    minor = _numeric(out, "MinorAxisLength_px")
    convex_area = _numeric(out, "ConvexArea_px")
    p_outer = _numeric(out, "P_outer_boundary")
    pc_outer = _numeric(out, "Pc_outer_boundary")
    p_total = _numeric(out, "P_total_boundary")

    out["EquivRadius_px"] = np.sqrt(area.clip(lower=0) / np.pi)
    out["EquivDiameter_px"] = 2.0 * out["EquivRadius_px"]
    out["ProjectedSphericity2D"] = _safe_divide(2.0 * np.sqrt(np.pi * area.clip(lower=0)), p_outer)
    out["AspectRatio01"] = _safe_divide(minor, major)
    out["AxisAspectRatio"] = _safe_divide(major, minor)

    solidity_from_area = _safe_divide(area, convex_area)
    if "Solidity_geometry" in out.columns:
        solidity_source = _numeric(out, "Solidity_geometry")
        out["Solidity2D"] = solidity_from_area.where(solidity_from_area.notna(), solidity_source)
    else:
        out["Solidity2D"] = solidity_from_area

    out["ProjectedConvexityPerimeter"] = _safe_divide(pc_outer, p_outer)
    out["PtotalOverPouter"] = _safe_divide(p_total, p_outer)
    out["ProjectedRegularity2D"] = out[
        ["ProjectedSphericity2D", "AspectRatio01", "Solidity2D"]
    ].mean(axis=1, skipna=True)
    return out


def assign_reliability_class(df: pd.DataFrame) -> pd.Series:
    """Assign row-level reliability classes from area and boundary validity."""
    area = _numeric(df, "Area_px")
    valid_area = np.isfinite(area)
    boundary_valid = _bool_series(df, "BoundaryMetricValid")
    reliability = pd.Series("boundary_invalid", index=df.index, dtype="object")
    reliability.loc[valid_area & boundary_valid & (area >= 250)] = "geometry_valid"
    reliability.loc[valid_area & boundary_valid & (area >= 500)] = "high_confidence"
    reliability.loc[valid_area & (area < 250)] = "count_only_small"
    return reliability


def _threshold(thresholds: dict, metric: str, quantile: str, default: float) -> float:
    try:
        value = thresholds[metric][quantile]
    except KeyError:
        return default
    value = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if not np.isfinite(value):
        return default
    return float(value)


def compute_shape_thresholds(valid_rows: pd.DataFrame) -> dict:
    """Compute deterministic quantile thresholds from valid reference rows."""
    boundary_valid = _bool_series(valid_rows, "BoundaryMetricValid")
    area = _numeric(valid_rows, "Area_px")
    reference = valid_rows.loc[boundary_valid & (area >= 250)]

    thresholds = {}
    for metric in SHAPE_THRESHOLD_METRICS:
        values = _numeric(reference, metric).dropna()
        thresholds[metric] = {}
        for label, quantile in SHAPE_QUANTILES.items():
            if values.empty:
                thresholds[metric][label] = np.nan
            else:
                thresholds[metric][label] = float(values.quantile(quantile, interpolation="linear"))
    return thresholds


def assign_shape_class(df: pd.DataFrame, thresholds: dict) -> pd.DataFrame:
    """Assign descriptive shape classes in the approved class order."""
    out = df.copy()
    if "ReliabilityClass" not in out.columns:
        out["ReliabilityClass"] = assign_reliability_class(out)

    area = _numeric(out, "Area_px")
    valid_area = np.isfinite(area)
    boundary_valid = _bool_series(out, "BoundaryMetricValid")
    roughness_lt_one = _bool_series(out, "RoughnessLessThanOne")
    circularity_gt_1p05 = _bool_series(out, "CircularityGreaterThan1p05")
    area_tier = out.get("AreaTier", pd.Series("", index=out.index)).astype(str).str.lower()

    sphericity = _numeric(out, "ProjectedSphericity2D")
    aspect01 = _numeric(out, "AspectRatio01")
    axis_ratio = _numeric(out, "AxisAspectRatio")
    solidity = _numeric(out, "Solidity2D")
    roughness = _numeric(out, "ProjectedRoughness_boundary")
    ptotal_ratio = _numeric(out, "PtotalOverPouter")

    sph_q75 = _threshold(thresholds, "ProjectedSphericity2D", "q75", 0.8)
    aspect_q75 = _threshold(thresholds, "AspectRatio01", "q75", 0.8)
    axis_q75 = _threshold(thresholds, "AxisAspectRatio", "q75", 2.5)
    axis_q90 = _threshold(thresholds, "AxisAspectRatio", "q90", 4.0)
    solidity_q25 = _threshold(thresholds, "Solidity2D", "q25", 0.65)
    solidity_q75 = _threshold(thresholds, "Solidity2D", "q75", 0.9)
    roughness_q75 = _threshold(thresholds, "ProjectedRoughness_boundary", "q75", 1.3)
    roughness_q90 = _threshold(thresholds, "ProjectedRoughness_boundary", "q90", 1.6)
    ptotal_q75 = _threshold(thresholds, "PtotalOverPouter", "q75", 1.5)

    eligible = valid_area & boundary_valid & (area >= 250)
    medium = eligible & (area < 500) & area_tier.eq("medium")
    compact_round = (
        eligible
        & (sphericity >= sph_q75)
        & (aspect01 >= aspect_q75)
        & (axis_ratio <= axis_q75)
        & (solidity >= solidity_q75)
        & ~roughness_lt_one
        & ~circularity_gt_1p05
    )
    elongated = eligible & (axis_ratio >= axis_q90)
    concave = (
        eligible
        & (solidity <= solidity_q25)
        & (axis_ratio < axis_q90)
        & (roughness < roughness_q90)
        & (ptotal_ratio < ptotal_q75)
    )
    branched = (
        eligible
        & (solidity <= solidity_q25)
        & ((axis_ratio >= axis_q90) | (roughness >= roughness_q90) | (ptotal_ratio >= ptotal_q75))
    )
    compact_irregular = (
        eligible
        & (solidity >= solidity_q75)
        & ((roughness >= roughness_q75) | roughness_lt_one | circularity_gt_1p05)
    )

    shape_class = pd.Series("", index=out.index, dtype="object")
    reason = pd.Series("", index=out.index, dtype="object")

    def assign_first(predicate: pd.Series, class_name: str, class_reason: str) -> None:
        target = predicate & shape_class.eq("")
        shape_class.loc[target] = class_name
        reason.loc[target] = class_reason

    small = area < 250
    area_invalid = ~valid_area
    invalid_boundary = area_invalid | (~boundary_valid & valid_area & (area >= 250))

    assign_first(small, "small_unclassified", "area_lt_250")
    assign_first(invalid_boundary, "boundary_invalid", "boundary_metric_invalid")
    reason.loc[area_invalid & shape_class.eq("boundary_invalid")] = "area_missing_or_invalid"
    assign_first(medium, "medium_caution", "medium_area_tier")
    assign_first(compact_round, "compact_round", "high_sphericity_high_solidity_low_elongation")
    assign_first(elongated, "elongated", "high_axis_aspect_ratio")
    assign_first(concave, "concave_lobed", "low_solidity_moderate_elongation")
    assign_first(branched, "branched_complex", "low_solidity_with_high_elongation_or_boundary_complexity")
    assign_first(compact_irregular, "compact_irregular", "compact_geometry_with_boundary_qc_caution")
    assign_first(shape_class.eq(""), "ambiguous_valid", "valid_geometry_fallback")

    invalid_reasons = pd.Series("", index=out.index, dtype="object")
    invalid_reasons.loc[small] = "area_lt_250"
    invalid_reasons.loc[~boundary_valid & valid_area & (area >= 250)] = "boundary_metric_invalid"
    invalid_reasons.loc[area_invalid] = "area_missing_or_invalid"
    invalid_reasons.loc[roughness_lt_one] = invalid_reasons.loc[roughness_lt_one].map(
        lambda text: "roughness_lt_1" if not text else f"{text};roughness_lt_1"
    )
    invalid_reasons.loc[circularity_gt_1p05] = invalid_reasons.loc[circularity_gt_1p05].map(
        lambda text: "circularity_gt_1p05" if not text else f"{text};circularity_gt_1p05"
    )

    out["ShapeClass"] = shape_class
    out["ShapeClassReason"] = reason
    out["ShapeInvalidReason"] = invalid_reasons
    out["ShapeValid"] = invalid_reasons.eq("")
    return out


def normalize_sidecar_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize sidecar-native names and add projected shape outputs."""
    out = df.copy()
    if "BlobID" not in out.columns and "BlobID_sidecar" in out.columns:
        out["BlobID"] = out["BlobID_sidecar"]

    out = add_projected_shape_metrics(out)
    if "SidecarSubset" not in out.columns:
        out["SidecarSubset"] = DATASET_SUBSET_NAME
    out["ReliabilityClass"] = assign_reliability_class(out)

    for column, default in (
        ("ShapeClass", ""),
        ("ShapeClassReason", ""),
        ("ShapeInvalidReason", ""),
    ):
        if column not in out.columns:
            out[column] = default
    if "ShapeValid" not in out.columns:
        out["ShapeValid"] = False
    return out


def _parse_qc_value(value: object) -> object:
    if pd.isna(value):
        return None
    text = str(value).strip()
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    numeric = pd.to_numeric(pd.Series([text]), errors="coerce").iloc[0]
    if pd.notna(numeric):
        number = float(numeric)
        if number.is_integer():
            return int(number)
        return number
    return text


def _parse_geometry_qc_summary(path: Path) -> dict[str, object]:
    qc = pd.read_csv(path)
    if not {"Metric", "Value"}.issubset(qc.columns):
        raise ValueError(f"{path.name} must contain long-form Metric,Value columns")
    return {str(row.Metric): _parse_qc_value(row.Value) for row in qc.itertuples(index=False)}


def _as_number(metrics: dict[str, object], name: str) -> float:
    value = metrics.get(name)
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        raise ValueError(f"geometry_qc_summary.csv gate {name} is missing or non-numeric")
    return float(numeric)


def _as_bool(metrics: dict[str, object], name: str) -> bool:
    value = metrics.get(name)
    if isinstance(value, bool):
        return value
    if value is None:
        raise ValueError(f"geometry_qc_summary.csv gate {name} is missing")
    return str(value).strip().lower() in {"true", "1", "yes", "y", "t"}


def validate_sidecar_inputs(sidecar_dir: str | Path) -> SidecarValidation:
    """Validate required sidecar files and interpretation gates."""
    sidecar_path = Path(sidecar_dir)
    if not sidecar_path.exists():
        raise FileNotFoundError(f"Sidecar directory does not exist: {sidecar_path}")
    if not sidecar_path.is_dir():
        raise NotADirectoryError(f"Sidecar path is not a directory: {sidecar_path}")

    missing = [name for name in REQUIRED_SIDECAR_FILES if not (sidecar_path / name).exists()]
    if missing:
        raise FileNotFoundError(f"Missing required sidecar file(s): {', '.join(missing)}")

    paths = {Path(name).stem: sidecar_path / name for name in REQUIRED_SIDECAR_FILES}
    for name in OPTIONAL_SIDECAR_FILES:
        path = sidecar_path / name
        if path.exists():
            paths[Path(name).stem] = path

    qc_metrics = _parse_geometry_qc_summary(paths["geometry_qc_summary"])
    failures: list[str] = []
    if str(qc_metrics.get("OverallStatus", "")).upper() != "PASS":
        failures.append(f"OverallStatus={qc_metrics.get('OverallStatus')!r} (expected PASS)")

    processed_frames = _as_number(qc_metrics, "ProcessedFrames")
    geometry_blob_rows = _as_number(qc_metrics, "GeometryBlobRows")
    blob_count_pass_frames = _as_number(qc_metrics, "BlobCountPassFrames")
    total_area_pass_frames = _as_number(qc_metrics, "TotalAreaPassFrames")
    empty_geometry_frames = _as_number(qc_metrics, "EmptyGeometryFrames")
    mismatch_name = (
        "EffectiveMaxConsecutiveMismatchFrames"
        if "EffectiveMaxConsecutiveMismatchFrames" in qc_metrics
        else "MaxConsecutiveMismatchFrames"
    )
    max_consecutive_mismatch = _as_number(qc_metrics, mismatch_name)
    blocked = _as_bool(qc_metrics, "BlockedForInterpretation")

    if processed_frames <= 0:
        failures.append(f"ProcessedFrames={processed_frames:g} (expected > 0)")
    if geometry_blob_rows <= 0:
        failures.append(f"GeometryBlobRows={geometry_blob_rows:g} (expected > 0)")
    if blob_count_pass_frames != processed_frames:
        failures.append(
            f"BlobCountPassFrames={blob_count_pass_frames:g} "
            f"(expected ProcessedFrames={processed_frames:g})"
        )
    if total_area_pass_frames != processed_frames:
        failures.append(
            f"TotalAreaPassFrames={total_area_pass_frames:g} "
            f"(expected ProcessedFrames={processed_frames:g})"
        )
    if empty_geometry_frames != 0:
        failures.append(f"EmptyGeometryFrames={empty_geometry_frames:g} (expected 0)")
    if max_consecutive_mismatch > 0:
        failures.append(f"{mismatch_name}={max_consecutive_mismatch:g} (expected <= 0)")
    if blocked:
        failures.append("BlockedForInterpretation=true (expected false)")

    if failures:
        raise ValueError("Sidecar QC gate failed: " + "; ".join(failures))
    return SidecarValidation(sidecar_path, paths, qc_metrics)


def _default_output_dir(sidecar_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return sidecar_dir.parent / f"g21_blob_morphology_data_product_{timestamp}"


def _prepare_output_dir(output_dir: Path, overwrite: bool, dry_run: bool) -> None:
    product_prefix = "g21_blob_morphology_data_product_"
    if dry_run:
        if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
            raise FileExistsError(f"Output directory is non-empty; pass --overwrite to reuse it: {output_dir}")
        return
    if output_dir.exists() and any(output_dir.iterdir()):
        if not overwrite:
            raise FileExistsError(f"Output directory is non-empty; pass --overwrite to reuse it: {output_dir}")
        if not output_dir.name.startswith(product_prefix):
            raise ValueError(
                "Refusing to overwrite a non-product output directory. "
                f"Expected directory name to start with {product_prefix!r}: {output_dir}"
            )
        for child in output_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    output_dir.mkdir(parents=True, exist_ok=True)


def _read_csv_chunks(path: Path, chunksize: int) -> Iterable[pd.DataFrame]:
    return pd.read_csv(path, chunksize=chunksize)


def _compute_streaming_thresholds(
    blob_path: Path,
    chunksize: int,
) -> tuple[dict[str, dict[str, float]], dict[str, object], dict[object, float]]:
    values_by_metric: dict[str, list[np.ndarray]] = {metric: [] for metric in SHAPE_THRESHOLD_METRICS}
    row_count = 0
    reference_count = 0
    boundary_metric_valid_rows = 0
    frame_indices: set[int] = set()
    invalid_frame_index_count = 0
    frame_area_totals: dict[object, float] = {}

    for chunk in _read_csv_chunks(blob_path, chunksize):
        normalized = normalize_sidecar_columns(chunk)
        row_count += len(normalized)
        if "FrameIndex" in normalized.columns:
            frame_values = pd.to_numeric(normalized["FrameIndex"], errors="coerce")
            valid_frame_values = frame_values.dropna()
            invalid_frame_index_count += int(frame_values.isna().sum())
            non_integer = valid_frame_values[~np.isclose(valid_frame_values, np.round(valid_frame_values))]
            invalid_frame_index_count += int(len(non_integer))
            frame_indices.update(int(value) for value in valid_frame_values[np.isclose(valid_frame_values, np.round(valid_frame_values))])
            area = _numeric(normalized, "Area_px")
            for frame_index, frame_area in area.groupby(normalized["FrameIndex"], dropna=False):
                if pd.isna(frame_index):
                    continue
                frame_area_totals[frame_index] = frame_area_totals.get(frame_index, 0.0) + float(frame_area.fillna(0).sum())
        area = _numeric(normalized, "Area_px")
        boundary_valid = _bool_series(normalized, "BoundaryMetricValid")
        boundary_metric_valid_rows += int(boundary_valid.sum())
        reference_mask = boundary_valid & (area >= 250)
        reference_count += int(reference_mask.sum())
        reference = normalized.loc[reference_mask]
        for metric in SHAPE_THRESHOLD_METRICS:
            metric_values = _numeric(reference, metric).dropna().to_numpy(dtype="float64")
            if metric_values.size:
                values_by_metric[metric].append(metric_values)

    thresholds: dict[str, dict[str, float]] = {}
    for metric, arrays in values_by_metric.items():
        values = np.concatenate(arrays) if arrays else np.array([], dtype="float64")
        thresholds[metric] = {}
        for label, quantile in SHAPE_QUANTILES.items():
            if values.size:
                thresholds[metric][label] = float(pd.Series(values).quantile(quantile, interpolation="linear"))
            else:
                thresholds[metric][label] = np.nan

    counts = {
        "blob_rows": row_count,
        "threshold_reference_rows": reference_count,
        "frames_observed_in_blob_csv": len(frame_indices),
        "frame_indices_observed": sorted(frame_indices),
        "invalid_frame_index_count": invalid_frame_index_count,
        "boundary_metric_valid_rows": boundary_metric_valid_rows,
    }
    return thresholds, counts, frame_area_totals


def _validate_chunksize(chunksize: int) -> None:
    if isinstance(chunksize, bool) or not isinstance(chunksize, (int, np.integer)) or int(chunksize) <= 0:
        raise ValueError(f"chunksize must be a positive integer, got {chunksize!r}")


def _validate_first_pass_gates(counts: dict[str, object], validation: SidecarValidation) -> None:
    expected_rows = int(_as_number(validation.qc_metrics, "GeometryBlobRows"))
    expected_frames = int(_as_number(validation.qc_metrics, "ProcessedFrames"))
    observed_rows = int(counts.get("blob_rows", 0))
    observed_frames = int(counts.get("frames_observed_in_blob_csv", 0))
    observed_indices = set(counts.get("frame_indices_observed", []))
    expected_indices = set(range(1, expected_frames + 1))
    failures: list[str] = []

    if observed_rows != expected_rows:
        failures.append(f"GeometryBlobRows sidecar={expected_rows} observed={observed_rows}")
    if observed_frames != expected_frames:
        failures.append(f"ProcessedFrames sidecar={expected_frames} observed_unique_frames={observed_frames}")
    if int(counts.get("invalid_frame_index_count", 0)):
        failures.append(f"FrameIndex invalid/non-integer rows={counts['invalid_frame_index_count']}")
    if observed_indices != expected_indices:
        missing = sorted(expected_indices - observed_indices)[:10]
        extra = sorted(observed_indices - expected_indices)[:10]
        failures.append(f"FrameIndex must be contiguous 1..{expected_frames}; missing={missing} extra={extra}")
    if "BoundaryMetricValidRows" in validation.qc_metrics:
        expected_boundary_valid = int(_as_number(validation.qc_metrics, "BoundaryMetricValidRows"))
        observed_boundary_valid = int(counts.get("boundary_metric_valid_rows", 0))
        if observed_boundary_valid != expected_boundary_valid:
            failures.append(
                f"BoundaryMetricValidRows sidecar={expected_boundary_valid} observed={observed_boundary_valid}"
            )

    if failures:
        raise ValueError("First-pass sidecar acceptance gate failed: " + "; ".join(failures))


def _append_csv(df: pd.DataFrame, path: Path, header: bool) -> None:
    df.to_csv(path, mode="w" if header else "a", header=header, index=False)


def _init_frame_stats() -> dict[object, dict[str, object]]:
    return {}


def _new_frame_record() -> dict[str, object]:
    return {
        "BlobCount": 0,
        "AreaSum_px": 0.0,
        "AreaGe250Count": 0,
        "AreaGe500Count": 0,
        "BoundaryMetricValidCount": 0,
        "BoundaryMetricValidAreaSum_px": 0.0,
        "HighConfidenceAreaSum_px": 0.0,
        "BorderTouchingCount": 0,
        "ShapeValidCount": 0,
        "ReliabilityCounts": {column: 0 for _, column in RELIABILITY_CLASSES},
        "values": {
            "Area_px": [],
            "EquivRadius_px": [],
            **{metric: [] for metric in FRAME_MORPHOLOGY_MEDIAN_METRICS},
        },
    }


def _append_numeric_values(record: dict[str, object], name: str, values: pd.Series) -> None:
    numeric_values = pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype="float64")
    if numeric_values.size:
        record["values"][name].append(numeric_values)


def _update_frame_stats(stats: dict[object, dict[str, object]], classified: pd.DataFrame) -> None:
    area = _numeric(classified, "Area_px")
    boundary_valid = _bool_series(classified, "BoundaryMetricValid")
    shape_valid = _bool_series(classified, "ShapeValid")
    border_touching = _bool_series(classified, "TouchesImageBorder")
    reliability = classified.get("ReliabilityClass", pd.Series("", index=classified.index)).astype(str)

    for frame_index, group in classified.groupby("FrameIndex", dropna=False):
        record = stats.setdefault(frame_index, _new_frame_record())
        group_index = group.index
        group_area = area.loc[group_index]
        group_boundary_valid = boundary_valid.loc[group_index]
        group_shape_valid = shape_valid.loc[group_index]
        group_border_touching = border_touching.loc[group_index]
        group_reliability = reliability.loc[group_index]
        group_area_filled = group_area.fillna(0)

        record["BlobCount"] += int(len(group))
        record["AreaSum_px"] += float(group_area_filled.sum())
        record["AreaGe250Count"] += int((group_area >= 250).sum())
        record["AreaGe500Count"] += int((group_area >= 500).sum())
        record["BoundaryMetricValidCount"] += int(group_boundary_valid.sum())
        record["BoundaryMetricValidAreaSum_px"] += float(group_area_filled.loc[group_boundary_valid].sum())
        record["HighConfidenceAreaSum_px"] += float(group_area_filled.loc[group_reliability.eq("high_confidence")].sum())
        record["BorderTouchingCount"] += int(group_border_touching.sum())
        record["ShapeValidCount"] += int(group_shape_valid.sum())
        for reliability_class, column in RELIABILITY_CLASSES:
            record["ReliabilityCounts"][column] += int(group_reliability.eq(reliability_class).sum())

        _append_numeric_values(record, "Area_px", group_area)
        _append_numeric_values(record, "EquivRadius_px", group["EquivRadius_px"])
        for metric in FRAME_MORPHOLOGY_MEDIAN_METRICS:
            _append_numeric_values(record, metric, group[metric])


def _concat_record_values(record: dict[str, object], name: str) -> np.ndarray:
    arrays = record["values"].get(name, [])
    return np.concatenate(arrays) if arrays else np.array([], dtype="float64")


def _quantile(values: np.ndarray, quantile: float) -> float:
    if not values.size:
        return np.nan
    return float(pd.Series(values).quantile(quantile, interpolation="linear"))


def _finalize_frame_morphology_stats(stats: dict[object, dict[str, object]]) -> pd.DataFrame:
    rows = []
    for frame_index, record in sorted(stats.items(), key=lambda item: item[0]):
        area_values = _concat_record_values(record, "Area_px")
        radius_values = _concat_record_values(record, "EquivRadius_px")
        area_sum = float(record["AreaSum_px"])
        positive_area_values = area_values[np.isfinite(area_values)]
        top3_sum = float(np.sort(positive_area_values)[-3:].sum()) if positive_area_values.size else np.nan
        row = {
            "FrameIndex": frame_index,
            "BlobCount": int(record["BlobCount"]),
            "AreaSum_px": area_sum,
            "AreaMedian_px": float(np.median(area_values)) if area_values.size else np.nan,
            "Area_px_p10": _quantile(area_values, 0.10),
            "Area_px_p90": _quantile(area_values, 0.90),
            "EquivRadius_px_p10": _quantile(radius_values, 0.10),
            "EquivRadius_px_p90": _quantile(radius_values, 0.90),
            "AreaGe250Count": int(record["AreaGe250Count"]),
            "AreaGe500Count": int(record["AreaGe500Count"]),
            "BoundaryMetricValidCount": int(record["BoundaryMetricValidCount"]),
            "BoundaryMetricValidFraction": record["BoundaryMetricValidCount"] / record["BlobCount"]
            if record["BlobCount"]
            else np.nan,
            "BoundaryMetricValidAreaFraction": record["BoundaryMetricValidAreaSum_px"] / area_sum
            if area_sum
            else np.nan,
            "HighConfidenceAreaFraction": record["HighConfidenceAreaSum_px"] / area_sum if area_sum else np.nan,
            "BorderTouchingCount": int(record["BorderTouchingCount"]),
            "Amax_Atotal": float(np.max(area_values)) / area_sum if area_sum and area_values.size else np.nan,
            "A_top3_Atotal": top3_sum / area_sum if area_sum and np.isfinite(top3_sum) else np.nan,
        }
        for metric in FRAME_MORPHOLOGY_MEDIAN_METRICS:
            values = _concat_record_values(record, metric)
            row[f"{metric}_median"] = float(np.median(values)) if values.size else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def _finalize_frame_reliability_stats(stats: dict[object, dict[str, object]]) -> pd.DataFrame:
    rows = []
    for frame_index, record in sorted(stats.items(), key=lambda item: item[0]):
        row = {
            "FrameIndex": frame_index,
            "BlobCount": int(record["BlobCount"]),
            "AreaSum_px": float(record["AreaSum_px"]),
            "BoundaryMetricValidCount": int(record["BoundaryMetricValidCount"]),
            "ShapeValidCount": int(record["ShapeValidCount"]),
        }
        row.update({column: int(count) for column, count in record["ReliabilityCounts"].items()})
        row["BoundaryMetricValidFraction"] = (
            row["BoundaryMetricValidCount"] / row["BlobCount"] if row["BlobCount"] else np.nan
        )
        row["ShapeValidFraction"] = row["ShapeValidCount"] / row["BlobCount"] if row["BlobCount"] else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def _shape_frame_summary(classified: pd.DataFrame) -> pd.DataFrame:
    working = classified.copy()
    working["Area_px_numeric"] = _numeric(working, "Area_px")
    working["ShapeValid_bool"] = _bool_series(working, "ShapeValid")
    working["ShapeInvalid_bool"] = ~working["ShapeValid_bool"]
    return (
        working.groupby(["FrameIndex", "ShapeClass"], dropna=False)
        .agg(
            BlobCount=("BlobID", "count"),
            AreaSum_px=("Area_px_numeric", "sum"),
            ShapeValidCount=("ShapeValid_bool", "sum"),
            ShapeInvalidCount=("ShapeInvalid_bool", "sum"),
        )
        .reset_index()
    )


def _init_tier_stats() -> dict[str, dict[str, object]]:
    return {}


def _tier_group_names(row_area: pd.Series, area_tier: pd.Series) -> list[tuple[str, pd.Series]]:
    return [
        ("all", pd.Series(True, index=row_area.index)),
        ("area_ge_250", row_area >= 250),
        ("area_ge_500", row_area >= 500),
        *[(f"AreaTier:{tier}", area_tier.eq(tier)) for tier in sorted(area_tier.dropna().unique())],
    ]


def _update_tier_stats(stats: dict[str, dict[str, object]], classified: pd.DataFrame) -> None:
    area = _numeric(classified, "Area_px")
    area_tier = classified.get("AreaTier", pd.Series("", index=classified.index)).fillna("").astype(str)
    boundary_valid = _bool_series(classified, "BoundaryMetricValid")
    roughness_lt_one = _bool_series(classified, "RoughnessLessThanOne")
    circularity_gt = _bool_series(classified, "CircularityGreaterThan1p05")
    for group_name, mask in _tier_group_names(area, area_tier):
        group = classified.loc[mask]
        if group.empty:
            continue
        record = stats.setdefault(
            group_name,
            {
                "N": 0,
                "AreaSum_px": 0.0,
                "BoundaryMetricValidCount": 0,
                "RoughnessLtOneCount": 0,
                "CircularityGt1p05Count": 0,
                "metrics": {metric: [] for metric in SHAPE_THRESHOLD_METRICS},
                "summary_metrics": {metric: [] for metric in SUMMARY_MEDIAN_METRICS},
            },
        )
        group_area = area.loc[mask]
        record["N"] += int(len(group))
        record["AreaSum_px"] += float(group_area.fillna(0).sum())
        record["BoundaryMetricValidCount"] += int(boundary_valid.loc[mask].sum())
        record["RoughnessLtOneCount"] += int(roughness_lt_one.loc[mask].sum())
        record["CircularityGt1p05Count"] += int(circularity_gt.loc[mask].sum())
        valid_group = group.loc[boundary_valid.loc[mask].to_numpy()]
        for metric in SHAPE_THRESHOLD_METRICS:
            metric_values = _numeric(valid_group, metric).dropna().to_numpy(dtype="float64")
            if metric_values.size:
                record["metrics"][metric].append(metric_values)
        for metric in SUMMARY_MEDIAN_METRICS:
            metric_values = _numeric(valid_group, metric).dropna().to_numpy(dtype="float64")
            if metric_values.size:
                record["summary_metrics"][metric].append(metric_values)


def _finalize_tier_stats(stats: dict[str, dict[str, object]]) -> pd.DataFrame:
    total_area = float(stats.get("all", {}).get("AreaSum_px", 0.0))
    rows = []
    for group_name, record in sorted(stats.items()):
        n = int(record["N"])
        area_sum = float(record["AreaSum_px"])
        row = {
            "AreaTierGroup": group_name,
            "N": n,
            "AreaSum_px": area_sum,
            "AreaFraction": area_sum / total_area if total_area else np.nan,
            "BoundaryMetricValidFraction": record["BoundaryMetricValidCount"] / n if n else np.nan,
            "RoughnessLtOneFraction": record["RoughnessLtOneCount"] / n if n else np.nan,
            "CircularityGt1p05Fraction": record["CircularityGt1p05Count"] / n if n else np.nan,
        }
        for metric, arrays in record["summary_metrics"].items():
            values = np.concatenate(arrays) if arrays else np.array([], dtype="float64")
            row[f"{metric}_median"] = float(np.median(values)) if values.size else np.nan
        if group_name == "area_ge_500":
            row["InterpretationTier"] = "high_confidence_projected_boundary_metrics"
            row["Reason"] = "Area_px >= 500 with valid sidecar boundary metrics summarized where available"
        elif group_name == "area_ge_250":
            row["InterpretationTier"] = "geometry_valid_projected_boundary_metrics"
            row["Reason"] = "Area_px >= 250 threshold reference population"
        elif group_name == "all":
            row["InterpretationTier"] = "all_detected_blobs"
            row["Reason"] = "Includes small and boundary-invalid rows"
        else:
            row["InterpretationTier"] = "sidecar_area_tier"
            row["Reason"] = "Sidecar-native AreaTier group"
        rows.append(row)
    return pd.DataFrame(rows)


def _candidate_row(row: pd.Series, exemplar_type: str, reason: str) -> dict[str, object]:
    out = {field: row.get(field, np.nan) for field in REPRESENTATIVE_CANDIDATE_COLUMNS}
    out["ExemplarType"] = exemplar_type
    out["SelectionReason"] = reason
    return out


def _representative_scores(classified: pd.DataFrame, thresholds: dict[str, dict[str, float]]) -> pd.DataFrame:
    out = classified.copy()
    median_score = pd.Series(0.0, index=out.index)
    extreme_score = pd.Series(0.0, index=out.index)
    for metric in SHAPE_THRESHOLD_METRICS:
        values = _numeric(out, metric)
        q25 = _threshold(thresholds, metric, "q25", np.nan)
        q50 = _threshold(thresholds, metric, "q50", np.nan)
        q90 = _threshold(thresholds, metric, "q90", np.nan)
        span = abs(q90 - q25) if np.isfinite(q90) and np.isfinite(q25) and q90 != q25 else 1.0
        if np.isfinite(q50):
            median_score += (values - q50).abs().fillna(span) / span
            extreme_score += (values - q50).abs().fillna(0) / span
    out["_median_score"] = median_score
    out["_high_confidence_score"] = _numeric(out, "Area_px").fillna(0) + (
        _numeric(out, "ProjectedRegularity2D").fillna(0) * 100.0
    )
    out["_extreme_score"] = extreme_score
    return out


def _update_representatives(
    representatives: dict[tuple[str, str], tuple[float, dict[str, object]]],
    classified: pd.DataFrame,
    thresholds: dict[str, dict[str, float]],
) -> tuple[int, int]:
    scored = _representative_scores(classified, thresholds)
    eligible = scored[
        _bool_series(scored, "BoundaryMetricValid")
        & _bool_series(scored, "ShapeValid")
        & (_numeric(scored, "Area_px") >= 250)
        & ~scored["ShapeClass"].isin(["small_unclassified", "boundary_invalid"])
    ]
    missing_mask_paths = int(scored.get("MaskPath", pd.Series("", index=scored.index)).fillna("").astype(str).str.len().eq(0).sum())
    missing_label_paths = int(scored.get("LabelPath", pd.Series("", index=scored.index)).fillna("").astype(str).str.len().eq(0).sum())
    for shape_class, group in eligible.groupby("ShapeClass", dropna=False):
        median_row = group.sort_values("_median_score", kind="mergesort").iloc[0]
        _maybe_store_representative(
            representatives,
            (shape_class, "class_medoid"),
            -float(median_row["_median_score"]),
            _candidate_row(median_row, "class_medoid", "closest_to_global_valid_metric_medians"),
        )

        high_confidence = group[group["ReliabilityClass"].eq("high_confidence")]
        if high_confidence.empty:
            high_confidence = group
        high_row = high_confidence.sort_values("_high_confidence_score", ascending=False, kind="mergesort").iloc[0]
        _maybe_store_representative(
            representatives,
            (shape_class, "high_confidence_exemplar"),
            float(high_row["_high_confidence_score"]),
            _candidate_row(high_row, "high_confidence_exemplar", "largest_high_confidence_area_and_regularity"),
        )

        extreme_row = group.sort_values("_extreme_score", ascending=False, kind="mergesort").iloc[0]
        _maybe_store_representative(
            representatives,
            (shape_class, "shape_extreme"),
            float(extreme_row["_extreme_score"]),
            _candidate_row(extreme_row, "shape_extreme", "furthest_from_global_valid_metric_medians"),
        )

        large_row = group.sort_values("Area_px", ascending=False, kind="mergesort").iloc[0]
        _maybe_store_representative(
            representatives,
            (shape_class, "large_area_exemplar"),
            float(pd.to_numeric(pd.Series([large_row.get("Area_px")]), errors="coerce").iloc[0]),
            _candidate_row(large_row, "large_area_exemplar", "largest_area_within_shape_class"),
        )

    qc_exclusions = scored.loc[~scored.index.isin(eligible.index)]
    if not qc_exclusions.empty:
        for shape_class, group in qc_exclusions.groupby("ShapeClass", dropna=False):
            row = group.sort_values("Area_px", ascending=False, kind="mergesort").iloc[0]
            area_score = pd.to_numeric(pd.Series([row.get("Area_px")]), errors="coerce").iloc[0]
            score = float(area_score) if pd.notna(area_score) else 0.0
            _maybe_store_representative(
                representatives,
                (str(shape_class), "qc_exclusion_example"),
                score,
                _candidate_row(row, "qc_exclusion_example", str(row.get("ShapeInvalidReason", "excluded_by_qc"))),
            )
    return missing_mask_paths, missing_label_paths


def _maybe_store_representative(
    representatives: dict[tuple[str, str], tuple[float, dict[str, object]]],
    key: tuple[str, str],
    score: float,
    row: dict[str, object],
) -> None:
    existing = representatives.get(key)
    if existing is None or score > existing[0]:
        representatives[key] = (score, row)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=_json_default), encoding="utf-8")


def _json_default(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        if np.isnan(value):
            return None
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return str(value)


def _git_commit(repo_path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-c", f"safe.directory={repo_path}", "rev-parse", "HEAD"],
            cwd=repo_path,
            text=True,
            capture_output=True,
            check=True,
        )
    except Exception:
        return None
    return result.stdout.strip() or None


def _git_commit_or_status_note(repo_path: Path) -> str:
    commit = _git_commit(repo_path)
    if commit is None:
        return "git commit unavailable; repository status could not be read"
    try:
        result = subprocess.run(
            ["git", "-c", f"safe.directory={repo_path}", "status", "--short"],
            cwd=repo_path,
            text=True,
            capture_output=True,
            check=True,
        )
    except Exception:
        return f"{commit}; git status unavailable"
    status_lines = [line for line in result.stdout.splitlines() if line.strip()]
    if status_lines:
        return f"{commit}; working tree has uncommitted or untracked changes"
    return commit


def _file_inventory(paths: dict[str, Path]) -> dict[str, dict[str, object]]:
    inventory: dict[str, dict[str, object]] = {}
    for name, path in sorted(paths.items()):
        inventory[name] = {
            "path": str(path),
            "bytes": int(path.stat().st_size) if path.exists() else None,
        }
    return inventory


def _write_manifest_with_stable_inventory(
    manifest_path: Path,
    manifest: dict[str, object],
    output_paths: dict[str, Path],
    max_passes: int = 10,
) -> None:
    """Write a manifest whose output inventory includes the manifest itself."""
    manifest["output_file_inventory"] = {}
    _write_json(manifest_path, manifest)
    for _ in range(max_passes):
        inventory = _file_inventory(output_paths)
        if inventory == manifest.get("output_file_inventory"):
            return
        manifest["output_file_inventory"] = inventory
        _write_json(manifest_path, manifest)

    final_inventory = _file_inventory(output_paths)
    if final_inventory != manifest.get("output_file_inventory"):
        raise RuntimeError("Manifest output_file_inventory did not stabilize after repeated writes")


def _write_qc_outputs(
    output_dir: Path,
    validation: SidecarValidation,
    manifest: dict[str, object],
    missing_mask_paths: int,
    missing_label_paths: int,
) -> None:
    qc_rows = [
        ("Scope", SCOPE_LANGUAGE),
        ("SidecarSubset", DATASET_SUBSET_NAME),
        ("OverallStatus", validation.qc_metrics.get("OverallStatus")),
        ("ProcessedFrames", validation.qc_metrics.get("ProcessedFrames")),
        ("GeometryBlobRows", validation.qc_metrics.get("GeometryBlobRows")),
        ("OutputBlobRows", manifest["row_counts"]["blob_rows"]),
        ("OutputFrameCount", manifest["frame_counts"]["morphology_frames"]),
        ("MissingMaskPathRows", missing_mask_paths),
        ("MissingLabelPathRows", missing_label_paths),
        ("ProjectedRoughnessBoundaryMeaning", "2D exterior-boundary proxy"),
        ("POuterBoundaryMeaning", "not full NAPL-water interfacial area"),
    ]
    pd.DataFrame(qc_rows, columns=["Metric", "Value"]).to_csv(
        output_dir / "blob_morphology_qc_summary.csv",
        index=False,
    )
    lines = [
        "# Blob Morphology QC Summary",
        "",
        f"- Scope: {SCOPE_LANGUAGE}.",
        f"- Sidecar subset: {DATASET_SUBSET_NAME}.",
        f"- Sidecar QC status: {validation.qc_metrics.get('OverallStatus')}.",
        f"- Processed frames: {validation.qc_metrics.get('ProcessedFrames')}.",
        f"- Geometry blob rows reported by sidecar: {validation.qc_metrics.get('GeometryBlobRows')}.",
        f"- Blob rows written: {manifest['row_counts']['blob_rows']}.",
        f"- Missing MaskPath rows: {missing_mask_paths}.",
        f"- Missing LabelPath rows: {missing_label_paths}.",
        "",
        "ProjectedRoughness_boundary is a 2D exterior-boundary proxy derived from sidecar boundary metrics.",
        "P_outer_boundary is not full NAPL-water interfacial area and must not be interpreted as true 3D interface.",
    ]
    (output_dir / "blob_morphology_qc_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_blob_morphology_data_product(
    sidecar_dir: str | Path,
    output_dir: str | Path | None = None,
    chunksize: int = 200_000,
    overwrite: bool = False,
    dry_run: bool = False,
) -> dict[str, object]:
    """Build the full-duration projected 2D blob morphology data product."""
    validation = validate_sidecar_inputs(sidecar_dir)
    _validate_chunksize(chunksize)
    out_dir = Path(output_dir) if output_dir is not None else _default_output_dir(validation.sidecar_dir)

    planned = {
        "dry_run": True,
        "sidecar_dir": str(validation.sidecar_dir),
        "output_dir": str(out_dir),
        "chunksize": chunksize,
        "planned_outputs": list(OUTPUT_FILENAMES),
        "sidecar_subset": DATASET_SUBSET_NAME,
        "row_counts": {
            "ProcessedFrames": validation.qc_metrics.get("ProcessedFrames"),
            "GeometryBlobRows": validation.qc_metrics.get("GeometryBlobRows"),
        },
        "sidecar_qc_metrics": validation.qc_metrics,
        "scope": SCOPE_LANGUAGE,
    }
    if dry_run:
        return planned

    blob_path = validation.paths["geometry_by_blob"]
    thresholds, counts, frame_area_totals = _compute_streaming_thresholds(blob_path, chunksize)
    _validate_first_pass_gates(counts, validation)
    _prepare_output_dir(out_dir, overwrite=overwrite, dry_run=dry_run)

    by_blob_path = out_dir / "blob_morphology_by_blob.csv"
    shape_by_blob_path = out_dir / "blob_shape_class_by_blob.csv"
    frame_stats = _init_frame_stats()
    shape_frame_parts: list[pd.DataFrame] = []
    tier_stats = _init_tier_stats()
    representatives: dict[tuple[str, str], tuple[float, dict[str, object]]] = {}
    first_blob_write = True
    first_shape_write = True
    missing_mask_paths = 0
    missing_label_paths = 0

    for chunk in _read_csv_chunks(blob_path, chunksize):
        classified = assign_shape_class(normalize_sidecar_columns(chunk), thresholds)
        frame_totals = classified["FrameIndex"].map(frame_area_totals)
        classified["A_blob_Atotal"] = _safe_divide(_numeric(classified, "Area_px"), frame_totals)
        _append_csv(classified, by_blob_path, first_blob_write)
        first_blob_write = False

        shape_columns = [
            column
            for column in [
                "FrameIndex",
                "RealTime_s",
                "SidecarSubset",
                "BlobID",
                "ShapeClass",
                "ShapeClassReason",
                "ShapeValid",
                "ShapeInvalidReason",
                "ReliabilityClass",
                "Area_px",
                "AreaTier",
                "ProjectedSphericity2D",
                "Circularity2D_boundary",
                "AspectRatio01",
                "AxisAspectRatio",
                "Solidity2D",
                "ProjectedRoughness_boundary",
                "PtotalOverPouter",
                "ProjectedRegularity2D",
                "A_blob_Atotal",
                "MaskPath",
                "LabelPath",
            ]
            if column in classified.columns
        ]
        _append_csv(classified[shape_columns], shape_by_blob_path, first_shape_write)
        first_shape_write = False

        _update_frame_stats(frame_stats, classified)
        shape_frame_parts.append(_shape_frame_summary(classified))
        _update_tier_stats(tier_stats, classified)
        missing_mask, missing_label = _update_representatives(representatives, classified, thresholds)
        missing_mask_paths += missing_mask
        missing_label_paths += missing_label

    morphology_by_frame = _finalize_frame_morphology_stats(frame_stats)
    morphology_by_frame.to_csv(out_dir / "blob_morphology_by_frame.csv", index=False)
    reliability_by_frame = _finalize_frame_reliability_stats(frame_stats)
    reliability_by_frame.to_csv(out_dir / "blob_reliability_summary_by_frame.csv", index=False)
    shape_by_frame = _combine_shape_frame_parts(shape_frame_parts)
    shape_by_frame.to_csv(out_dir / "blob_shape_class_summary_by_frame.csv", index=False)
    _finalize_tier_stats(tier_stats).to_csv(out_dir / "blob_morphology_reliability_by_tier.csv", index=False)

    representative_rows = [row for _, row in sorted(representatives.values(), key=lambda item: (item[1]["ShapeClass"], item[1]["ExemplarType"]))]
    pd.DataFrame(representative_rows, columns=REPRESENTATIVE_CANDIDATE_COLUMNS).to_csv(
        out_dir / "representative_blob_candidates.csv",
        index=False,
    )

    threshold_payload = {
        "reference_filter": {"BoundaryMetricValid": True, "min_area_px": 250},
        "sidecar_subset": DATASET_SUBSET_NAME,
        "quantiles": SHAPE_QUANTILES,
        "thresholds": thresholds,
        "reference_row_count": counts["threshold_reference_rows"],
    }
    _write_json(out_dir / "blob_morphology_thresholds.json", threshold_payload)

    repo_path = Path(__file__).resolve().parents[1]
    input_paths = {path.name: path for path in validation.paths.values()}
    output_paths = {name: out_dir / name for name in OUTPUT_FILENAMES}
    output_files = {name: str(path) for name, path in output_paths.items()}
    manifest = {
        "schema_version": "1.1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": SCOPE_LANGUAGE,
        "sidecar_subset": DATASET_SUBSET_NAME,
        "input_dir": str(validation.sidecar_dir),
        "input_sidecar_dir": str(validation.sidecar_dir),
        "input_files": {key: str(path) for key, path in validation.paths.items()},
        "input_file_inventory": _file_inventory(input_paths),
        "sidecar_qc_metrics": validation.qc_metrics,
        "sidecar_qc": validation.qc_metrics,
        "chunksize": chunksize,
        "command_line_args": {
            "sidecar_dir": str(validation.sidecar_dir),
            "output_dir": str(out_dir),
            "chunksize": chunksize,
            "overwrite": overwrite,
            "dry_run": dry_run,
        },
        "config": {
            "chunksize": chunksize,
            "overwrite_existing_output_dir": overwrite,
            "default_output_policy": "timestamped_directory_when_output_dir_is_omitted",
        },
        "row_counts": counts,
        "frame_counts": {
            "morphology_frames": int(morphology_by_frame["FrameIndex"].nunique()) if not morphology_by_frame.empty else 0,
            "shape_summary_frames": int(shape_by_frame["FrameIndex"].nunique()) if not shape_by_frame.empty else 0,
        },
        "thresholds": thresholds,
        "output_files": output_files,
        "output_file_inventory": {},
        "no_rerun_statement": (
            "This product was generated from the sidecar files listed in input_file_inventory; "
            "do not rerun or overwrite outputs unless the sidecar inventory, command_line_args, "
            "and git provenance are intentionally updated."
        ),
        "git_commit": _git_commit(repo_path),
        "git_commit_or_status_note": _git_commit_or_status_note(repo_path),
    }
    _write_qc_outputs(out_dir, validation, manifest, missing_mask_paths, missing_label_paths)
    _write_manifest_with_stable_inventory(out_dir / "blob_morphology_manifest.json", manifest, output_paths)
    return manifest


def _combine_shape_frame_parts(parts: list[pd.DataFrame]) -> pd.DataFrame:
    if not parts:
        return pd.DataFrame(
            columns=["FrameIndex", "ShapeClass", "BlobCount", "AreaSum_px", "ShapeValidCount", "ShapeInvalidCount"]
        )
    combined = pd.concat(parts, ignore_index=True)
    return (
        combined.groupby(["FrameIndex", "ShapeClass"], dropna=False)
        .agg(
            BlobCount=("BlobCount", "sum"),
            AreaSum_px=("AreaSum_px", "sum"),
            ShapeValidCount=("ShapeValidCount", "sum"),
            ShapeInvalidCount=("ShapeInvalidCount", "sum"),
        )
        .reset_index()
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sidecar-dir", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--chunksize", type=int, default=200_000)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = build_blob_morphology_data_product(
        args.sidecar_dir,
        output_dir=args.output_dir,
        chunksize=args.chunksize,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
