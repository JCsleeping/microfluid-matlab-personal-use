"""Build a ShapeClassV1 representative blob atlas from an existing data product.

This script does not run sidecar extraction. It joins the formal v1 shape-class
table with the accepted morphology data product to recover mask/label paths,
selects representative candidates for each v1 class, and optionally renders the
panels with ``render_blob_atlas_panels.py``.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

try:  # pragma: no cover - exercised by CLI execution
    from .render_blob_atlas_panels import render_blob_atlas
except ImportError:  # pragma: no cover - script execution from visualization/
    from render_blob_atlas_panels import render_blob_atlas


V1_REQUIRED_COLUMNS = {
    "FrameIndex",
    "BlobID",
    "ShapeClassV1",
    "ShapeClassV1Reason",
    "ShapeClassVersion",
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
}

MORPHOLOGY_REQUIRED_COLUMNS = {
    "FrameIndex",
    "BlobID",
    "MaskPath",
    "LabelPath",
}

CANDIDATE_COLUMNS = [
    "FrameIndex",
    "BlobID",
    "ShapeClass",
    "ShapeClassV1",
    "ShapeClassV1Reason",
    "ShapeClassVersion",
    "ShapeV1InterpretationTier",
    "MetricSource",
    "BoundaryMetricSource",
    "DatasetSubset",
    "FullSidecarDerived",
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

MEDOID_METRICS = [
    "Area_px",
    "ProjectedSphericity2D",
    "AxisAspectRatio",
    "Solidity2D",
    "ProjectedRoughness_boundary",
    "PtotalOverPouter",
]

V1_CLASS_ORDER = [
    "compact_regular",
    "near_compact_regular",
    "moderately_elongated",
    "elongated",
    "moderately_concave",
    "branched_complex",
    "ambiguous_valid",
    "low_area_compact_candidate_100_249",
    "low_area_elongated_candidate_100_249",
    "low_area_projected_shape_caution_100_249",
    "count_only_lt100",
]


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git_commit() -> str:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True)
        return result.stdout.strip()
    except Exception:
        return "unknown"


def _read_csv_required(path: Path, required: set[str], label: str, usecols: list[str] | None = None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing {label}: {path}")
    header = pd.read_csv(path, nrows=0).columns
    missing = sorted(required - set(header))
    if missing:
        raise ValueError(f"{label} is missing required column(s): {', '.join(missing)}")
    return pd.read_csv(path, usecols=usecols)


def _load_candidate_source(morphology_dir: Path, shape_class_v1_dir: Path) -> pd.DataFrame:
    v1_path = shape_class_v1_dir / "blob_shape_class_v1_by_blob.csv"
    morph_path = morphology_dir / "blob_morphology_by_blob.csv"

    v1_header = pd.read_csv(v1_path, nrows=0).columns if v1_path.exists() else []
    optional_v1 = [
        "ShapeV1InterpretationTier",
        "MetricSource",
        "BoundaryMetricSource",
        "DatasetSubset",
        "FullSidecarDerived",
    ]
    v1_usecols = [col for col in list(V1_REQUIRED_COLUMNS) + optional_v1 if col in v1_header]
    v1 = _read_csv_required(v1_path, V1_REQUIRED_COLUMNS, "formal v1 by-blob table", v1_usecols)

    morph = _read_csv_required(
        morph_path,
        MORPHOLOGY_REQUIRED_COLUMNS,
        "morphology by-blob table",
        ["FrameIndex", "BlobID", "MaskPath", "LabelPath"],
    )
    for table in (v1, morph):
        table["FrameIndex"] = pd.to_numeric(table["FrameIndex"], errors="coerce").astype("Int64")
        table["BlobID"] = pd.to_numeric(table["BlobID"], errors="coerce").astype("Int64")

    merged = v1.merge(morph, on=["FrameIndex", "BlobID"], how="left", validate="one_to_one")
    missing_labels = merged["LabelPath"].fillna("").astype(str).str.len().eq(0).sum()
    if missing_labels:
        raise ValueError(f"{int(missing_labels)} v1 rows do not have a LabelPath after joining morphology data")

    merged["ShapeClass"] = merged["ShapeClassV1"].astype(str)
    for column in MEDOID_METRICS + ["Circularity2D_boundary", "AspectRatio01", "ProjectedRegularity2D"]:
        if column in merged.columns:
            merged[column] = pd.to_numeric(merged[column], errors="coerce")
    return merged


def _class_order(classes: Iterable[str]) -> list[str]:
    classes = [str(cls) for cls in classes]
    known = [cls for cls in V1_CLASS_ORDER if cls in classes]
    extra = sorted(cls for cls in classes if cls not in set(known))
    return known + extra


def _finite_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)


def _unused_index(candidate: pd.Series, used: set[int]) -> int | None:
    if candidate.empty:
        return None
    for idx in candidate.index:
        if int(idx) not in used:
            return int(idx)
    return int(candidate.index[0])


def _medoid_index(group: pd.DataFrame, used: set[int]) -> int | None:
    metrics = [col for col in MEDOID_METRICS if col in group.columns]
    if not metrics:
        return _unused_index(group, used)
    values = group.loc[:, metrics].apply(_finite_numeric)
    med = values.median(skipna=True)
    q25 = values.quantile(0.25)
    q75 = values.quantile(0.75)
    scale = (q75 - q25).replace(0, np.nan)
    scale = scale.fillna(values.std(skipna=True)).replace(0, 1.0).fillna(1.0)
    distance = ((values - med).abs() / scale).sum(axis=1, skipna=True)
    return _unused_index(group.loc[distance.sort_values(kind="mergesort").index], used)


def _largest_area_index(group: pd.DataFrame, used: set[int]) -> int | None:
    area = _finite_numeric(group["Area_px"]) if "Area_px" in group.columns else pd.Series(np.nan, index=group.index)
    return _unused_index(group.loc[area.sort_values(ascending=False, kind="mergesort").index], used)


def _extreme_index(group: pd.DataFrame, shape_class: str, used: set[int]) -> tuple[int | None, str]:
    if shape_class in {"elongated", "moderately_elongated", "low_area_elongated_candidate_100_249"}:
        metric, ascending = "AxisAspectRatio", False
        reason = "max_axis_aspect_ratio"
    elif shape_class in {"branched_complex", "moderately_concave"}:
        metric, ascending = "Solidity2D", True
        reason = "min_solidity2d"
    elif shape_class in {"compact_regular", "near_compact_regular", "low_area_compact_candidate_100_249"}:
        metric, ascending = "ProjectedRegularity2D", False
        reason = "max_projected_regularity2d"
    elif shape_class == "low_area_projected_shape_caution_100_249":
        metric, ascending = "ProjectedRoughness_boundary", False
        reason = "max_projected_roughness_boundary"
    else:
        metric, ascending = "Area_px", False
        reason = "max_area_px"
    if metric not in group.columns:
        return _largest_area_index(group, used), "fallback_largest_area"
    values = _finite_numeric(group[metric])
    return _unused_index(group.loc[values.sort_values(ascending=ascending, kind="mergesort").index], used), reason


def _candidate_row(row: pd.Series, exemplar_type: str, reason: str) -> dict[str, object]:
    record = {column: row.get(column, "") for column in CANDIDATE_COLUMNS}
    record["ShapeClass"] = row.get("ShapeClassV1", row.get("ShapeClass", ""))
    record["ShapeClassV1"] = row.get("ShapeClassV1", record["ShapeClass"])
    record["ExemplarType"] = exemplar_type
    record["SelectionReason"] = reason
    return record


def select_v1_representative_candidates(data: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for shape_class in _class_order(data["ShapeClassV1"].dropna().astype(str).unique()):
        group = data[data["ShapeClassV1"].astype(str).eq(shape_class)].copy()
        if group.empty:
            continue
        group = group[group["LabelPath"].fillna("").astype(str).str.len() > 0]
        if group.empty:
            continue
        used: set[int] = set()
        selections = [
            ("class_medoid", _medoid_index(group, used), "nearest_class_median_in_scaled_metric_space"),
            ("large_area_exemplar", None, "largest_projected_area_within_class"),
            ("shape_extreme", None, ""),
        ]
        for exemplar_type, idx, reason in selections:
            if exemplar_type == "large_area_exemplar":
                idx = _largest_area_index(group, used)
            elif exemplar_type == "shape_extreme":
                idx, reason = _extreme_index(group, shape_class, used)
            if idx is None:
                continue
            used.add(int(idx))
            rows.append(_candidate_row(group.loc[idx], exemplar_type, reason))
    return pd.DataFrame(rows, columns=CANDIDATE_COLUMNS)


def write_candidate_manifest(path: Path, candidates: pd.DataFrame, morphology_dir: Path, shape_class_v1_dir: Path) -> None:
    class_counts = candidates["ShapeClass"].value_counts().sort_index().to_dict() if not candidates.empty else {}
    manifest = {
        "schema_version": "1.0",
        "created_at_utc": _utc_now(),
        "git_commit": _git_commit(),
        "morphology_dir": str(morphology_dir),
        "shape_class_v1_dir": str(shape_class_v1_dir),
        "candidate_count": int(len(candidates)),
        "shape_class_count": int(candidates["ShapeClass"].nunique()) if not candidates.empty else 0,
        "class_counts": {str(key): int(value) for key, value in class_counts.items()},
        "selection_policy": {
            "class_medoid": "nearest class median in scaled metric space",
            "large_area_exemplar": "largest projected area within class",
            "shape_extreme": "class-specific extreme metric",
        },
        "scope": {
            "projected_2d_shape_classes": True,
            "tracking": False,
            "fractal": False,
            "roughness_3d": False,
            "wadell_roundness": False,
        },
    }
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def build_v1_representative_atlas(
    morphology_dir: Path,
    shape_class_v1_dir: Path,
    output_dir: Path | None = None,
    render: bool = True,
    atlas_dir: Path | None = None,
    overwrite_atlas: bool = False,
) -> dict[str, object]:
    morphology_dir = Path(morphology_dir)
    shape_class_v1_dir = Path(shape_class_v1_dir)
    output_dir = Path(output_dir) if output_dir is not None else shape_class_v1_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    data = _load_candidate_source(morphology_dir, shape_class_v1_dir)
    candidates = select_v1_representative_candidates(data)
    candidates_path = output_dir / "representative_blob_candidates.csv"
    candidates.to_csv(candidates_path, index=False)
    manifest_path = output_dir / "representative_blob_candidates_manifest.json"
    write_candidate_manifest(manifest_path, candidates, morphology_dir, shape_class_v1_dir)

    result: dict[str, object] = {
        "candidate_count": int(len(candidates)),
        "candidates_csv": str(candidates_path),
        "candidate_manifest": str(manifest_path),
    }
    if render:
        atlas_dir = Path(atlas_dir) if atlas_dir is not None else output_dir / "representative_blob_atlas"
        atlas_result = render_blob_atlas(candidates_path, output_dir=atlas_dir, overwrite=overwrite_atlas)
        result.update(
            {
                "atlas_dir": str(atlas_result["output_dir"]),
                "atlas_manifest": str(atlas_result["manifest_path"]),
                "rendered_count": int(atlas_result["rendered_count"]),
                "missing_count": int(atlas_result["missing_count"]),
            }
        )
    return result


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--morphology-dir", required=True, type=Path)
    parser.add_argument("--shape-class-v1-dir", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--atlas-dir", type=Path, default=None)
    parser.add_argument("--no-render", action="store_true")
    parser.add_argument("--overwrite-atlas", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = build_v1_representative_atlas(
        args.morphology_dir,
        args.shape_class_v1_dir,
        output_dir=args.output_dir,
        render=not args.no_render,
        atlas_dir=args.atlas_dir,
        overwrite_atlas=args.overwrite_atlas,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
