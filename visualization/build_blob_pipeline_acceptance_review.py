"""Build a blob morphology pipeline acceptance review.

The review checks that an already-generated morphology data product is
internally closed: row counts reconcile across products, all expected frames
are covered, projected 2D metric invariants hold, and shape-class gates are
applied consistently. It does not run segmentation, sidecar extraction,
tracking, fractal analysis, or 3D roughness analysis.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


OUTPUT_FILES = [
    "g21_blob_pipeline_acceptance_review.md",
    "g21_blob_computation_qc_summary.csv",
    "g21_blob_computation_by_frame_qc.csv",
    "g21_blob_metric_range_audit.csv",
    "g21_blob_row_reconciliation.csv",
    "g21_blob_pipeline_release_manifest.json",
]

BOUNDARY_MORPHOLOGY_CLASSES_V1 = {
    "compact_regular",
    "near_compact_regular",
    "moderately_elongated",
    "elongated",
    "moderately_concave",
    "concave_lobed",
    "branched_complex",
    "compact_irregular",
    "ambiguous_valid",
}

MORPHOLOGY_REQUIRED_COLUMNS = {
    "FrameIndex",
    "BlobID",
    "Area_px",
    "MajorAxisLength_px",
    "MinorAxisLength_px",
    "AxisAspectRatio",
    "AspectRatio01",
    "Solidity2D",
    "ProjectedSphericity2D",
    "Circularity2D_boundary",
    "ProjectedRoughness_boundary",
    "PtotalOverPouter",
    "P_outer_boundary",
    "Pc_outer_boundary",
    "P_total_boundary",
    "BoundaryMetricValid",
}

V1_REQUIRED_COLUMNS = {
    "FrameIndex",
    "BlobID",
    "ShapeClassV1",
    "ShapeClassVersion",
    "ShapeV1InterpretationTier",
    "Area_px",
    "MetricSource",
    "BoundaryMetricSource",
    "DatasetSubset",
    "FullSidecarDerived",
}


@dataclass(frozen=True)
class Inputs:
    output_root: Path
    postprocess_dir: Path
    morphology_dir: Path
    shape_class_v1_dir: Path
    structure_statistics_dir: Path | None
    output_dir: Path


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


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_output_dir(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise FileExistsError(f"Output directory exists and is not empty: {path}")
    path.mkdir(parents=True, exist_ok=True)


def _csv_row_count(path: Path) -> int | None:
    if not path.exists():
        return None
    with path.open("rb") as handle:
        row_count = sum(1 for _ in handle) - 1
    return max(0, int(row_count))


def _read_csv_required(path: Path, required: set[str], label: str, usecols: list[str] | None = None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing {label}: {path}")
    header = pd.read_csv(path, nrows=0).columns
    missing = sorted(required - set(header))
    if missing:
        raise ValueError(f"{label} is missing required column(s): {', '.join(missing)}")
    selected = usecols if usecols is not None else list(header)
    selected = [column for column in selected if column in set(header)]
    return pd.read_csv(path, usecols=selected)


def _numeric(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype="float64")
    return pd.to_numeric(df[column], errors="coerce")


def _bool(df: pd.DataFrame, column: str, default: bool = False) -> pd.Series:
    if column not in df.columns:
        return pd.Series(default, index=df.index, dtype="bool")
    values = df[column]
    if pd.api.types.is_bool_dtype(values):
        return values.fillna(default).astype(bool)
    if pd.api.types.is_numeric_dtype(values):
        return values.fillna(int(default)).astype(bool)
    normalized = values.astype(str).str.strip().str.lower()
    true_like = normalized.isin({"true", "1", "yes", "y", "t"})
    false_like = normalized.isin({"false", "0", "no", "n", "f", "", "nan", "none"})
    return true_like.where(true_like | false_like, default).astype(bool)


def _status_from_violations(violations: int, *, warn_only: bool = False) -> str:
    if int(violations) == 0:
        return "PASS"
    return "WARN" if warn_only else "FAIL"


def _load_morphology(inputs: Inputs) -> pd.DataFrame:
    path = inputs.morphology_dir / "blob_morphology_by_blob.csv"
    optional = {
        "RealTime_s",
        "AreaTier",
        "RoughnessLessThanOne",
        "CircularityGreaterThan1p05",
        "MaskPath",
        "LabelPath",
    }
    usecols = sorted(MORPHOLOGY_REQUIRED_COLUMNS | optional)
    data = _read_csv_required(path, MORPHOLOGY_REQUIRED_COLUMNS, "morphology by-blob table", usecols)
    data["FrameIndex"] = _numeric(data, "FrameIndex").astype("Int64")
    data["BlobID"] = _numeric(data, "BlobID").astype("Int64")
    return data


def _load_v1(inputs: Inputs) -> pd.DataFrame:
    path = inputs.shape_class_v1_dir / "blob_shape_class_v1_by_blob.csv"
    optional = {
        "ShapeClassV1Reason",
        "SnStage",
        "RoughnessInvalidFlag",
        "CircularityArtifactFlag",
        "LowAreaProjectedShapeCaution",
        "CorrectedBoundaryAvailable",
        "FullSidecarDerived",
        "AreaTier",
    }
    usecols = sorted(V1_REQUIRED_COLUMNS | optional)
    data = _read_csv_required(path, V1_REQUIRED_COLUMNS, "formal shape-class v1 by-blob table", usecols)
    data["FrameIndex"] = _numeric(data, "FrameIndex").astype("Int64")
    data["BlobID"] = _numeric(data, "BlobID").astype("Int64")
    return data


def build_row_reconciliation(inputs: Inputs, morphology: pd.DataFrame, v1: pd.DataFrame) -> pd.DataFrame:
    level_a_path = inputs.output_root / "blob_detail_all_frames.csv"
    morphology_path = inputs.morphology_dir / "blob_morphology_by_blob.csv"
    v0_path = inputs.morphology_dir / "blob_shape_class_by_blob.csv"
    v1_path = inputs.shape_class_v1_dir / "blob_shape_class_v1_by_blob.csv"
    morphology_manifest = _read_json(inputs.morphology_dir / "blob_morphology_manifest.json")
    formal_manifest = _read_json(inputs.shape_class_v1_dir / "shape_class_v1_formal_manifest.json")
    stats_manifest = (
        _read_json(inputs.structure_statistics_dir / "blob_structure_statistics_manifest.json")
        if inputs.structure_statistics_dir is not None
        else {}
    )

    sources = [
        ("level_a_blob_detail_all_frames", level_a_path, _csv_row_count(level_a_path), None),
        ("morphology_by_blob", morphology_path, len(morphology), int(morphology["FrameIndex"].nunique())),
        ("shape_class_v0_by_blob", v0_path, _csv_row_count(v0_path), None),
        ("shape_class_v1_by_blob", v1_path, len(v1), int(v1["FrameIndex"].nunique())),
        (
            "morphology_manifest",
            inputs.morphology_dir / "blob_morphology_manifest.json",
            morphology_manifest.get("row_counts", {}).get("blob_rows"),
            morphology_manifest.get("frame_counts", {}).get("frames")
            or morphology_manifest.get("row_counts", {}).get("frames_observed_in_blob_csv"),
        ),
        (
            "shape_class_v1_formal_manifest",
            inputs.shape_class_v1_dir / "shape_class_v1_formal_manifest.json",
            formal_manifest.get("row_counts", {}).get("rows"),
            formal_manifest.get("row_counts", {}).get("frames"),
        ),
        (
            "structure_statistics_manifest",
            (inputs.structure_statistics_dir / "blob_structure_statistics_manifest.json")
            if inputs.structure_statistics_dir is not None
            else Path(""),
            stats_manifest.get("row_counts", {}).get("blob_rows"),
            stats_manifest.get("row_counts", {}).get("frames"),
        ),
    ]
    rows = []
    for source, path, rows_value, frames_value in sources:
        rows.append(
            {
                "Check": "source_row_count",
                "Source": source,
                "Path": str(path),
                "Rows": rows_value,
                "Frames": frames_value,
                "ReferenceRows": "",
                "DifferenceRows": "",
                "Status": "PASS" if rows_value is not None else "WARN",
                "Note": "source available" if rows_value is not None else "source missing or row count unavailable",
            }
        )

    def add_pair(check: str, left_source: str, right_source: str, left: int | None, right: int | None, fail_on_diff: bool) -> None:
        if left is None or right is None:
            status = "WARN"
            diff = ""
            note = "comparison source missing"
        else:
            diff = int(left) - int(right)
            status = "PASS" if diff == 0 else ("FAIL" if fail_on_diff else "WARN")
            note = "matched" if diff == 0 else "row-count difference documented"
        rows.append(
            {
                "Check": check,
                "Source": left_source,
                "Path": right_source,
                "Rows": left,
                "Frames": "",
                "ReferenceRows": right,
                "DifferenceRows": diff,
                "Status": status,
                "Note": note,
            }
        )

    level_a_rows = _csv_row_count(level_a_path)
    morphology_rows = int(len(morphology))
    v1_rows = int(len(v1))
    stats_rows = stats_manifest.get("row_counts", {}).get("blob_rows")
    add_pair("level_a_vs_morphology_rows", "level_a_blob_detail_all_frames", "morphology_by_blob", level_a_rows, morphology_rows, False)
    add_pair("morphology_vs_v1_rows", "morphology_by_blob", "shape_class_v1_by_blob", morphology_rows, v1_rows, True)
    add_pair("v1_vs_structure_statistics_rows", "shape_class_v1_by_blob", "structure_statistics_manifest", v1_rows, stats_rows, True)
    return pd.DataFrame(rows)


def build_frame_qc(morphology: pd.DataFrame, v1: pd.DataFrame) -> pd.DataFrame:
    morph = morphology.copy()
    morph["BoundaryMetricValid_bool"] = _bool(morph, "BoundaryMetricValid")
    morph["Area_px_num"] = _numeric(morph, "Area_px")
    morph_summary = (
        morph.groupby("FrameIndex", dropna=False)
        .agg(
            MorphologyBlobRows=("BlobID", "size"),
            MorphologyAreaSum_px=("Area_px_num", "sum"),
            BoundaryMetricValidRows=("BoundaryMetricValid_bool", "sum"),
        )
        .reset_index()
    )

    v1_work = v1.copy()
    v1_work["Area_px_num"] = _numeric(v1_work, "Area_px")
    v1_work["GeometryInterpretable"] = v1_work["ShapeV1InterpretationTier"].astype(str).eq("geometry_interpretable")
    v1_work["LowAreaShapeCaution"] = v1_work["ShapeV1InterpretationTier"].astype(str).eq("low_area_shape_caution")
    v1_work["CountOnly"] = v1_work["ShapeV1InterpretationTier"].astype(str).eq("count_only")
    v1_summary = (
        v1_work.groupby("FrameIndex", dropna=False)
        .agg(
            V1BlobRows=("BlobID", "size"),
            V1AreaSum_px=("Area_px_num", "sum"),
            GeometryInterpretableRows=("GeometryInterpretable", "sum"),
            LowAreaShapeCautionRows=("LowAreaShapeCaution", "sum"),
            CountOnlyRows=("CountOnly", "sum"),
        )
        .reset_index()
    )
    frame = morph_summary.merge(v1_summary, on="FrameIndex", how="outer").sort_values("FrameIndex")
    frame["RowCountDelta_MorphologyMinusV1"] = frame["MorphologyBlobRows"].fillna(0) - frame["V1BlobRows"].fillna(0)
    frame["AreaDelta_MorphologyMinusV1_px"] = frame["MorphologyAreaSum_px"].fillna(0) - frame["V1AreaSum_px"].fillna(0)
    max_frame = int(frame["FrameIndex"].max()) if len(frame) else 0
    expected = pd.DataFrame({"FrameIndex": np.arange(1, max_frame + 1, dtype=int)})
    frame = expected.merge(frame, on="FrameIndex", how="left")
    frame["FrameStatus"] = np.where(
        frame["MorphologyBlobRows"].isna() | frame["V1BlobRows"].isna(),
        "MISSING_FRAME",
        np.where(frame["RowCountDelta_MorphologyMinusV1"].fillna(0).ne(0), "ROW_MISMATCH", "PASS"),
    )
    return frame


def build_metric_range_audit(morphology: pd.DataFrame, v1: pd.DataFrame) -> pd.DataFrame:
    area = _numeric(morphology, "Area_px")
    major = _numeric(morphology, "MajorAxisLength_px")
    minor = _numeric(morphology, "MinorAxisLength_px")
    axis_ratio = _numeric(morphology, "AxisAspectRatio")
    aspect01 = _numeric(morphology, "AspectRatio01")
    solidity = _numeric(morphology, "Solidity2D")
    sphericity = _numeric(morphology, "ProjectedSphericity2D")
    circularity = _numeric(morphology, "Circularity2D_boundary")
    roughness = _numeric(morphology, "ProjectedRoughness_boundary")
    p_total_over_outer = _numeric(morphology, "PtotalOverPouter")
    p_outer = _numeric(morphology, "P_outer_boundary")
    p_convex = _numeric(morphology, "Pc_outer_boundary")
    p_total = _numeric(morphology, "P_total_boundary")
    boundary_valid = _bool(morphology, "BoundaryMetricValid")

    rows = []

    def add(metric: str, rule: str, mask: pd.Series, universe: pd.Series | None = None, warn_only: bool = False) -> None:
        if universe is None:
            universe = pd.Series(True, index=morphology.index)
        universe = universe.fillna(False).astype(bool)
        violations = int((mask.fillna(False).astype(bool) & universe).sum())
        n_checked = int(universe.sum())
        rows.append(
            {
                "Metric": metric,
                "Rule": rule,
                "RowsChecked": n_checked,
                "ViolationRows": violations,
                "ViolationFraction": float(violations / n_checked) if n_checked else np.nan,
                "Status": _status_from_violations(violations, warn_only=warn_only),
            }
        )

    finite_area = area.notna()
    add("Area_px", "Area_px > 0", area <= 0, finite_area)
    add("MajorMinorAxis", "MajorAxisLength_px >= MinorAxisLength_px", major < minor, major.notna() & minor.notna())
    add("AxisAspectRatio", "AxisAspectRatio >= 1", axis_ratio < 1, axis_ratio.notna())
    add("AspectRatio01", "0 < AspectRatio01 <= 1", (aspect01 <= 0) | (aspect01 > 1), aspect01.notna())
    add("Solidity2D", "0 <= Solidity2D <= 1", (solidity < 0) | (solidity > 1), solidity.notna())
    add(
        "ProjectedSphericity2D",
        "0 <= ProjectedSphericity2D <= 1.05 for boundary-valid rows",
        (sphericity < 0) | (sphericity > 1.05),
        boundary_valid & sphericity.notna(),
    )
    add(
        "ProjectedSphericity2D_all_rows",
        "0 <= ProjectedSphericity2D <= 1.05 outside boundary-valid rows is diagnostic only",
        (sphericity < 0) | (sphericity > 1.05),
        sphericity.notna() & ~boundary_valid,
        warn_only=True,
    )
    add("P_outer_boundary", "P_outer_boundary > 0 for boundary-valid rows", p_outer <= 0, boundary_valid & p_outer.notna())
    add("Pc_outer_boundary", "Pc_outer_boundary > 0 for boundary-valid rows", p_convex <= 0, boundary_valid & p_convex.notna())
    add("P_total_boundary", "P_total_boundary >= P_outer_boundary for boundary-valid rows", p_total < p_outer, boundary_valid & p_total.notna() & p_outer.notna())
    add("ProjectedRoughness_boundary", "ProjectedRoughness_boundary >= 1 for boundary-valid rows", roughness < 1, boundary_valid & roughness.notna())
    add("Circularity2D_boundary", "Circularity2D_boundary <= 1.05 for boundary-valid rows", circularity > 1.05, boundary_valid & circularity.notna())
    add("PtotalOverPouter", "PtotalOverPouter >= 1 for boundary-valid rows", p_total_over_outer < 1, boundary_valid & p_total_over_outer.notna())

    v1_classes = v1["ShapeClassV1"].astype(str)
    v1_area = _numeric(v1, "Area_px")
    tier = v1["ShapeV1InterpretationTier"].astype(str)

    def add_v1(metric: str, rule: str, mask: pd.Series, universe: pd.Series | None = None) -> None:
        if universe is None:
            universe = pd.Series(True, index=v1.index)
        universe = universe.fillna(False).astype(bool)
        violations = int((mask.fillna(False).astype(bool) & universe).sum())
        n_checked = int(universe.sum())
        rows.append(
            {
                "Metric": metric,
                "Rule": rule,
                "RowsChecked": n_checked,
                "ViolationRows": violations,
                "ViolationFraction": float(violations / n_checked) if n_checked else np.nan,
                "Status": _status_from_violations(violations),
            }
        )

    add_v1("ShapeClassV1", "Area < 100 px rows are count_only_lt100", ~v1_classes.eq("count_only_lt100"), v1_area < 100)
    add_v1("ShapeClassV1", "100 <= Area < 250 px rows stay in low_area_* classes", ~v1_classes.str.startswith("low_area_"), v1_area.ge(100) & v1_area.lt(250))
    add_v1("ShapeClassV1", "Area < 250 px rows are not boundary morphology classes", v1_classes.isin(BOUNDARY_MORPHOLOGY_CLASSES_V1), v1_area < 250)
    add_v1("ShapeV1InterpretationTier", "geometry_interpretable rows have Area >= 250 px", v1_area < 250, tier.eq("geometry_interpretable"))
    add_v1("ShapeClassVersion", "ShapeClassVersion == v1", ~v1["ShapeClassVersion"].astype(str).eq("v1"))
    add_v1("MetricSource", "MetricSource == full_duration_sidecar", ~v1["MetricSource"].astype(str).eq("full_duration_sidecar"))
    add_v1("BoundaryMetricSource", "BoundaryMetricSource == corrected_sidecar_boundary", ~v1["BoundaryMetricSource"].astype(str).eq("corrected_sidecar_boundary"))
    add_v1("DatasetSubset", "DatasetSubset == full_duration_sidecar", ~v1["DatasetSubset"].astype(str).eq("full_duration_sidecar"))
    add_v1("FullSidecarDerived", "FullSidecarDerived is true", ~_bool(v1, "FullSidecarDerived"))
    return pd.DataFrame(rows)


def build_qc_summary(
    row_reconciliation: pd.DataFrame,
    frame_qc: pd.DataFrame,
    metric_audit: pd.DataFrame,
    morphology: pd.DataFrame,
    v1: pd.DataFrame,
) -> pd.DataFrame:
    rows = []

    def add(gate: str, status: str, value: object, expected: str, notes: str = "") -> None:
        rows.append({"Gate": gate, "Status": status, "Value": value, "Expected": expected, "Notes": notes})

    add(
        "row_reconciliation_has_no_failures",
        "PASS" if not row_reconciliation["Status"].astype(str).eq("FAIL").any() else "FAIL",
        int(row_reconciliation["Status"].astype(str).eq("FAIL").sum()),
        "0 FAIL rows",
        "Level A vs morphology differences may be WARN if downstream products are internally conserved.",
    )
    warn_rows = int(row_reconciliation["Status"].astype(str).eq("WARN").sum())
    add("row_reconciliation_warnings_documented", "WARN" if warn_rows else "PASS", warn_rows, "0 or documented WARN")
    missing_frames = int(frame_qc["FrameStatus"].astype(str).eq("MISSING_FRAME").sum())
    row_mismatch_frames = int(frame_qc["FrameStatus"].astype(str).eq("ROW_MISMATCH").sum())
    add("frame_coverage_complete", "PASS" if missing_frames == 0 else "FAIL", missing_frames, "0 missing frames")
    add("frame_row_counts_match_v1", "PASS" if row_mismatch_frames == 0 else "FAIL", row_mismatch_frames, "0 row-mismatch frames")
    add("frame_count_12024", "PASS" if int(frame_qc["FrameIndex"].nunique()) == 12024 else "WARN", int(frame_qc["FrameIndex"].nunique()), "12024")
    metric_failures = int(metric_audit["Status"].astype(str).eq("FAIL").sum())
    metric_warnings = int(metric_audit["Status"].astype(str).eq("WARN").sum())
    add("metric_invariant_failures", "PASS" if metric_failures == 0 else "FAIL", metric_failures, "0 FAIL rows")
    add("metric_invariant_warnings", "WARN" if metric_warnings else "PASS", metric_warnings, "0 or documented WARN rows")
    add("morphology_rows", "PASS", int(len(morphology)), "recorded")
    add("shape_class_v1_rows", "PASS" if len(morphology) == len(v1) else "FAIL", int(len(v1)), str(len(morphology)))
    add(
        "geometry_interpretable_rows",
        "PASS",
        int(v1["ShapeV1InterpretationTier"].astype(str).eq("geometry_interpretable").sum()),
        "recorded",
        "Rows eligible for projected 2D boundary morphology interpretation.",
    )
    add(
        "count_only_rows",
        "PASS",
        int(v1["ShapeV1InterpretationTier"].astype(str).eq("count_only").sum()),
        "recorded",
        "Rows retained for population counts only.",
    )
    return pd.DataFrame(rows)


def _decision(qc_summary: pd.DataFrame, row_reconciliation: pd.DataFrame) -> str:
    if qc_summary["Status"].astype(str).eq("FAIL").any():
        return "BLOCKED_BLOB_PIPELINE_QC"
    if qc_summary["Status"].astype(str).eq("WARN").any() or row_reconciliation["Status"].astype(str).eq("WARN").any():
        return "ACCEPT_BLOB_PIPELINE_WITH_DOCUMENTED_WARNINGS"
    return "ACCEPT_BLOB_PIPELINE"


def write_review(
    path: Path,
    decision: str,
    row_reconciliation: pd.DataFrame,
    frame_qc: pd.DataFrame,
    metric_audit: pd.DataFrame,
    qc_summary: pd.DataFrame,
    morphology: pd.DataFrame,
    v1: pd.DataFrame,
) -> None:
    rows_total = int(len(v1))
    frames_total = int(frame_qc["FrameIndex"].nunique())
    geometry_interpretable = int(v1["ShapeV1InterpretationTier"].astype(str).eq("geometry_interpretable").sum())
    low_area = int(v1["ShapeV1InterpretationTier"].astype(str).eq("low_area_shape_caution").sum())
    count_only = int(v1["ShapeV1InterpretationTier"].astype(str).eq("count_only").sum())
    fail_gates = qc_summary[qc_summary["Status"].astype(str).eq("FAIL")]
    warn_gates = qc_summary[qc_summary["Status"].astype(str).eq("WARN")]
    level_a_diff = row_reconciliation[row_reconciliation["Check"].eq("level_a_vs_morphology_rows")]
    diff_text = "not available"
    diff_fraction_text = "not available"
    if not level_a_diff.empty:
        diff_value = pd.to_numeric(pd.Series([level_a_diff.iloc[0]["DifferenceRows"]]), errors="coerce").iloc[0]
        level_a_rows = pd.to_numeric(pd.Series([level_a_diff.iloc[0]["Rows"]]), errors="coerce").iloc[0]
        diff_text = str(int(diff_value)) if pd.notna(diff_value) else str(level_a_diff.iloc[0]["DifferenceRows"])
        if pd.notna(diff_value) and pd.notna(level_a_rows) and level_a_rows:
            diff_fraction_text = f"{float(diff_value) / float(level_a_rows):.6%}"
    boundary_sphericity = metric_audit[
        metric_audit["Metric"].astype(str).eq("ProjectedSphericity2D")
    ]
    all_row_sphericity = metric_audit[
        metric_audit["Metric"].astype(str).eq("ProjectedSphericity2D_all_rows")
    ]
    boundary_sphericity_violations = (
        int(boundary_sphericity.iloc[0]["ViolationRows"]) if not boundary_sphericity.empty else 0
    )
    all_row_sphericity_violations = (
        int(all_row_sphericity.iloc[0]["ViolationRows"]) if not all_row_sphericity.empty else 0
    )
    all_row_sphericity_checked = (
        int(all_row_sphericity.iloc[0]["RowsChecked"]) if not all_row_sphericity.empty else 0
    )

    lines = [
        "# G21 Blob Pipeline Acceptance Review",
        "",
        f"Decision: `{decision}`",
        "",
        "## Coverage",
        "",
        f"- Blob morphology rows: `{rows_total}`.",
        f"- Frames covered: `{frames_total}`.",
        f"- Geometry-interpretable rows: `{geometry_interpretable}`.",
        f"- Low-area projected-shape caution rows: `{low_area}`.",
        f"- Count-only rows: `{count_only}`.",
        f"- Level A minus morphology row difference: `{diff_text}` rows (`{diff_fraction_text}` of Level A blob rows).",
        "",
        "## QC Gates",
        "",
        f"- FAIL gates: `{len(fail_gates)}`.",
        f"- WARN gates: `{len(warn_gates)}`.",
        f"- Metric invariant failures: `{int(metric_audit['Status'].astype(str).eq('FAIL').sum())}`.",
        f"- Missing-frame rows in frame QC: `{int(frame_qc['FrameStatus'].astype(str).eq('MISSING_FRAME').sum())}`.",
        "",
        "## Interpretation Scope",
        "",
        "This review validates the projected 2D blob computation pipeline and row-level morphology data product. It does not run or claim tracking, split/merge lineage, boundary fractal dimension, 3D roughness, true Wadell roundness, or true fluid-fluid interfacial area.",
        "",
        "Boundary and roughness-related terms remain projected 2D proxies. `ProjectedRoughness_boundary` is interpreted only as a 2D exterior-boundary complexity proxy.",
        "",
        "## Warning Interpretation",
        "",
        "The Level A to morphology row-count warning is documented rather than blocking because the downstream morphology, ShapeClassV0, ShapeClassV1, and structure-statistics products are internally conserved. This review treats `blob_detail_all_frames.csv` as the upstream scalar reference and the sidecar-derived morphology product as the authoritative source for corrected 2D geometry rows.",
        "",
        f"The all-row `ProjectedSphericity2D` warning is diagnostic only: `{all_row_sphericity_violations}` of `{all_row_sphericity_checked}` non-boundary-valid rows exceed the display bound, while boundary-valid rows have `{boundary_sphericity_violations}` violations. Boundary interpretation therefore remains restricted to `BoundaryMetricValid` / geometry-interpretable rows.",
        "",
        "## Required Output Tables",
        "",
        "- `g21_blob_computation_qc_summary.csv`",
        "- `g21_blob_computation_by_frame_qc.csv`",
        "- `g21_blob_metric_range_audit.csv`",
        "- `g21_blob_row_reconciliation.csv`",
        "- `g21_blob_pipeline_release_manifest.json`",
        "",
    ]
    if not warn_gates.empty:
        lines.extend(["## Warning Gates", ""])
        for _, row in warn_gates.iterrows():
            lines.append(f"- `{row['Gate']}`: value `{row['Value']}`; expected `{row['Expected']}`.")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def build_pipeline_acceptance_review(inputs: Inputs) -> dict[str, object]:
    _safe_output_dir(inputs.output_dir)
    morphology = _load_morphology(inputs)
    v1 = _load_v1(inputs)
    row_reconciliation = build_row_reconciliation(inputs, morphology, v1)
    frame_qc = build_frame_qc(morphology, v1)
    metric_audit = build_metric_range_audit(morphology, v1)
    qc_summary = build_qc_summary(row_reconciliation, frame_qc, metric_audit, morphology, v1)
    decision = _decision(qc_summary, row_reconciliation)

    row_reconciliation.to_csv(inputs.output_dir / "g21_blob_row_reconciliation.csv", index=False)
    frame_qc.to_csv(inputs.output_dir / "g21_blob_computation_by_frame_qc.csv", index=False)
    metric_audit.to_csv(inputs.output_dir / "g21_blob_metric_range_audit.csv", index=False)
    qc_summary.to_csv(inputs.output_dir / "g21_blob_computation_qc_summary.csv", index=False)
    write_review(
        inputs.output_dir / "g21_blob_pipeline_acceptance_review.md",
        decision,
        row_reconciliation,
        frame_qc,
        metric_audit,
        qc_summary,
        morphology,
        v1,
    )
    manifest = {
        "schema_version": "1.0",
        "created_at_utc": _utc_now(),
        "git_commit": _git_commit(),
        "decision_label": decision,
        "output_root": str(inputs.output_root),
        "postprocess_dir": str(inputs.postprocess_dir),
        "morphology_dir": str(inputs.morphology_dir),
        "shape_class_v1_dir": str(inputs.shape_class_v1_dir),
        "structure_statistics_dir": str(inputs.structure_statistics_dir) if inputs.structure_statistics_dir else "",
        "output_dir": str(inputs.output_dir),
        "row_counts": {
            "morphology_rows": int(len(morphology)),
            "shape_class_v1_rows": int(len(v1)),
            "frames": int(frame_qc["FrameIndex"].nunique()),
            "geometry_interpretable_rows": int(v1["ShapeV1InterpretationTier"].astype(str).eq("geometry_interpretable").sum()),
            "low_area_shape_caution_rows": int(v1["ShapeV1InterpretationTier"].astype(str).eq("low_area_shape_caution").sum()),
            "count_only_rows": int(v1["ShapeV1InterpretationTier"].astype(str).eq("count_only").sum()),
        },
        "qc": {
            "fail_gates": int(qc_summary["Status"].astype(str).eq("FAIL").sum()),
            "warn_gates": int(qc_summary["Status"].astype(str).eq("WARN").sum()),
            "metric_failures": int(metric_audit["Status"].astype(str).eq("FAIL").sum()),
            "missing_frames": int(frame_qc["FrameStatus"].astype(str).eq("MISSING_FRAME").sum()),
            "row_mismatch_frames": int(frame_qc["FrameStatus"].astype(str).eq("ROW_MISMATCH").sum()),
        },
        "outputs": OUTPUT_FILES,
        "scope": {
            "projected_2d_blob_pipeline_qc": True,
            "full_duration_sidecar_derived": True,
            "tracking": False,
            "split_merge_lineage": False,
            "fractal": False,
            "roughness_3d": False,
            "true_wadell_roundness": False,
            "true_fluid_fluid_interfacial_area": False,
        },
    }
    (inputs.output_dir / "g21_blob_pipeline_release_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--postprocess-dir", required=True, type=Path)
    parser.add_argument("--morphology-dir", required=True, type=Path)
    parser.add_argument("--shape-class-v1-dir", required=True, type=Path)
    parser.add_argument("--structure-statistics-dir", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    output_dir = args.output_dir or args.morphology_dir / f"g21_blob_pipeline_acceptance_{_timestamp()}"
    manifest = build_pipeline_acceptance_review(
        Inputs(
            output_root=args.output_root,
            postprocess_dir=args.postprocess_dir,
            morphology_dir=args.morphology_dir,
            shape_class_v1_dir=args.shape_class_v1_dir,
            structure_statistics_dir=args.structure_statistics_dir,
            output_dir=output_dir,
        )
    )
    print(json.dumps({"output_dir": manifest["output_dir"], "decision_label": manifest["decision_label"], "qc": manifest["qc"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
