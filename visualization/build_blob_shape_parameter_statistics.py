"""Build projected 2D blob shape-parameter statistics and formula notes."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


STAGE_ORDER = ["early_depletion", "active_dissolution", "late_depletion", "endpoint"]

METRIC_COLUMNS = [
    "Area_px",
    "EquivRadius_px",
    "EquivDiameter_px",
    "MajorAxisLength_px",
    "MinorAxisLength_px",
    "AxisAspectRatio",
    "AspectRatio01",
    "Eccentricity",
    "Extent",
    "ConvexArea_px",
    "Solidity2D",
    "ProjectedSphericity2D",
    "Circularity2D_boundary",
    "ProjectedConvexityPerimeter",
    "ProjectedRoughness_boundary",
    "PtotalOverPouter",
    "ProjectedRegularity2D",
    "P_outer_boundary",
    "Pc_outer_boundary",
    "P_total_boundary",
]

REQUIRED_OUTPUTS = [
    "g21_blob_shape_parameter_formula_notes.md",
    "blob_shape_parameter_metric_dictionary.csv",
    "blob_shape_parameter_overall_statistics.csv",
    "blob_shape_parameter_shape_valid_statistics.csv",
    "blob_shape_parameter_by_reliability_class.csv",
    "blob_shape_parameter_by_area_tier.csv",
    "blob_shape_parameter_by_class.csv",
    "blob_shape_parameter_by_sn_stage.csv",
    "blob_shape_parameter_by_class_stage.csv",
    "blob_shape_parameter_statistics_manifest.json",
]

V1_EXTRA_OUTPUTS = [
    "g21_blob_shape_parameter_formula_notes_v1.md",
    "g21_shape_class_v1_decision_rules.md",
    "g21_shape_class_v1_field_dictionary.md",
]


def _numeric(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype="float64")
    return pd.to_numeric(df[column], errors="coerce")


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    den = pd.to_numeric(denominator, errors="coerce").replace(0, np.nan)
    num = pd.to_numeric(numerator, errors="coerce")
    return (num / den).replace([np.inf, -np.inf], np.nan)


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


def add_missing_projected_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Fill missing derived metric columns from sidecar geometry columns."""
    out = df.copy()
    area = _numeric(out, "Area_px")
    major = _numeric(out, "MajorAxisLength_px")
    minor = _numeric(out, "MinorAxisLength_px")
    convex_area = _numeric(out, "ConvexArea_px")
    p_outer = _numeric(out, "P_outer_boundary")
    pc_outer = _numeric(out, "Pc_outer_boundary")
    p_total = _numeric(out, "P_total_boundary")

    if "EquivRadius_px" not in out.columns:
        out["EquivRadius_px"] = np.sqrt(area.clip(lower=0) / np.pi)
    if "EquivDiameter_px" not in out.columns:
        out["EquivDiameter_px"] = 2.0 * _numeric(out, "EquivRadius_px")
    if "ProjectedSphericity2D" not in out.columns:
        out["ProjectedSphericity2D"] = _safe_divide(2.0 * np.sqrt(np.pi * area.clip(lower=0)), p_outer)
    if "AspectRatio01" not in out.columns:
        out["AspectRatio01"] = _safe_divide(minor, major)
    if "AxisAspectRatio" not in out.columns:
        out["AxisAspectRatio"] = _safe_divide(major, minor)
    if "Solidity2D" not in out.columns:
        out["Solidity2D"] = _safe_divide(area, convex_area)
    if "ProjectedConvexityPerimeter" not in out.columns:
        out["ProjectedConvexityPerimeter"] = _safe_divide(pc_outer, p_outer)
    if "PtotalOverPouter" not in out.columns:
        out["PtotalOverPouter"] = _safe_divide(p_total, p_outer)
    if "ProjectedRegularity2D" not in out.columns:
        out["ProjectedRegularity2D"] = out[
            ["ProjectedSphericity2D", "AspectRatio01", "Solidity2D"]
        ].mean(axis=1, skipna=True)
    return out


def assign_sn_stage(level_a: pd.DataFrame) -> pd.DataFrame:
    """Assign fixed SnMonotone stages with endpoint taking precedence."""
    required = {"FrameIndex", "SnMonotone"}
    missing = required - set(level_a.columns)
    if missing:
        raise ValueError(f"Level A dissolution table is missing column(s): {', '.join(sorted(missing))}")
    out = level_a.copy()
    out["FrameIndex"] = _numeric(out, "FrameIndex").astype("Int64")
    out["SnMonotone"] = _numeric(out, "SnMonotone")
    max_frame = int(out["FrameIndex"].max())
    endpoint_start = int(np.ceil(max_frame * 0.95))
    frame = out["FrameIndex"].astype(int)
    sn = out["SnMonotone"]
    stage = pd.Series("active_dissolution", index=out.index, dtype="object")
    stage.loc[sn >= 0.20] = "early_depletion"
    stage.loc[(sn >= 0.005) & (sn < 0.05)] = "late_depletion"
    stage.loc[(sn < 0.005) | (frame >= endpoint_start)] = "endpoint"
    out["SnStage"] = stage
    out["StageOrder"] = out["SnStage"].map({name: idx for idx, name in enumerate(STAGE_ORDER)})
    return out[["FrameIndex", "SnMonotone", "SnStage", "StageOrder"]]


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_v1_shape_inputs(shape_class_v1_dir: Path) -> tuple[pd.DataFrame, dict]:
    manifest_path = shape_class_v1_dir / "shape_class_v1_formal_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing v1 formal manifest: {manifest_path}")
    manifest = _read_json(manifest_path)
    decision_label = str(manifest.get("decision_label", ""))
    if decision_label.startswith("BLOCKED"):
        raise ValueError(f"v1 formal package is blocked: {decision_label}")
    by_blob_path = shape_class_v1_dir / "blob_shape_class_v1_by_blob.csv"
    if not by_blob_path.exists():
        raise FileNotFoundError(f"Missing v1 formal shape table: {by_blob_path}")
    wanted = {
        "FrameIndex",
        "RealTime_s",
        "BlobID",
        "ShapeClassV0",
        "ShapeClassV1",
        "ShapeClassV1Reason",
        "ShapeClassVersion",
        "ShapeV1InterpretationTier",
        "MetricSource",
        "BoundaryMetricSource",
        "DatasetSubset",
        "FullSidecarDerived",
        "AreaThresholdVersion",
        "Area_px",
        "AreaTier",
        "MajorAxisLength_px",
        "MinorAxisLength_px",
        "Eccentricity",
        "Extent",
        "ConvexArea_px",
        "Solidity_geometry",
        "Solidity2D",
        "P_outer_boundary",
        "Pc_outer_boundary",
        "P_total_boundary",
        "ProjectedSphericity2D",
        "Circularity2D_boundary",
        "AspectRatio01",
        "AxisAspectRatio",
        "ProjectedConvexityPerimeter",
        "ProjectedRoughness_boundary",
        "PtotalOverPouter",
        "ProjectedRegularity2D",
        "BoundaryMetricValid",
        "RoughnessLessThanOne",
        "CircularityGreaterThan1p05",
        "LowAreaProjectedShapeCaution",
        "ModerateBoundaryComplexityFlag",
        "HighBoundaryComplexityFlag",
        "InternalBoundarySignalFlag",
        "TouchesImageBorderFlag",
        "CircularityArtifactFlag",
        "RoughnessInvalidFlag",
    }
    shape = pd.read_csv(by_blob_path, usecols=lambda column: column in wanted)
    required = {"ShapeClassV1", "ShapeClassV1Reason", "ShapeClassVersion", "ShapeV1InterpretationTier"}
    missing = required - set(shape.columns)
    if missing:
        raise ValueError(f"v1 formal shape table missing required column(s): {', '.join(sorted(missing))}")
    expected_rows = manifest.get("row_counts", {}).get("rows") if isinstance(manifest.get("row_counts"), dict) else None
    if expected_rows is not None and int(expected_rows) != int(len(shape)):
        raise ValueError(f"v1 formal row-count mismatch: manifest={expected_rows}, table={len(shape)}")
    shape["ShapeClass"] = shape["ShapeClassV1"].astype(str)
    shape["ShapeValid"] = shape["ShapeV1InterpretationTier"].astype(str).eq("geometry_interpretable")
    shape["ShapeInvalidReason"] = np.where(shape["ShapeValid"], "", shape["ShapeV1InterpretationTier"].astype(str))
    shape["ReliabilityClass"] = shape["ShapeV1InterpretationTier"].astype(str)
    shape["ShapeClassReason"] = shape["ShapeClassV1Reason"].astype(str)
    return shape, manifest


def read_shape_inputs(
    morphology_dir: Path,
    level_a_dir: Path,
    shape_class_version: str = "v0",
    shape_class_v1_dir: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict, dict]:
    by_blob_path = morphology_dir / "blob_morphology_by_blob.csv"
    level_a_path = level_a_dir / "dissolution_rates.csv"
    thresholds_path = morphology_dir / "blob_morphology_thresholds.json"
    if not level_a_path.exists():
        raise FileNotFoundError(f"Missing Level A dissolution table: {level_a_path}")
    shape_meta: dict = {"version": "v0", "source_file": str(by_blob_path), "source_manifest": {}}
    if shape_class_version == "v1":
        if shape_class_v1_dir is None:
            raise ValueError("--shape-class-v1-dir is required when --shape-class-version v1")
        shape, v1_manifest = _read_v1_shape_inputs(shape_class_v1_dir)
        shape_meta = {
            "version": "v1",
            "source_dir": str(shape_class_v1_dir),
            "source_file": str(shape_class_v1_dir / "blob_shape_class_v1_by_blob.csv"),
            "manifest_file": str(shape_class_v1_dir / "shape_class_v1_formal_manifest.json"),
            "source_manifest": v1_manifest,
        }
    else:
        if not by_blob_path.exists():
            raise FileNotFoundError(f"Missing blob morphology table: {by_blob_path}")
        wanted = {
            "FrameIndex",
            "RealTime_s",
            "BlobID",
            "BlobID_sidecar",
            "ShapeClass",
            "ShapeValid",
            "ShapeInvalidReason",
            "ReliabilityClass",
            "Area_px",
            "AreaTier",
            "MajorAxisLength_px",
            "MinorAxisLength_px",
            "Eccentricity",
            "Extent",
            "ConvexArea_px",
            "Solidity_geometry",
            "Solidity2D",
            "P_outer_boundary",
            "Pc_outer_boundary",
            "P_total_boundary",
            "ProjectedSphericity2D",
            "Circularity2D_boundary",
            "AspectRatio01",
            "AxisAspectRatio",
            "ProjectedConvexityPerimeter",
            "ProjectedRoughness_boundary",
            "PtotalOverPouter",
            "ProjectedRegularity2D",
            "BoundaryMetricValid",
            "RoughnessLessThanOne",
            "CircularityGreaterThan1p05",
        }
        shape = pd.read_csv(by_blob_path, usecols=lambda column: column in wanted)
        if "BlobID" not in shape.columns and "BlobID_sidecar" in shape.columns:
            shape["BlobID"] = shape["BlobID_sidecar"]
        if "Solidity2D" not in shape.columns and "Solidity_geometry" in shape.columns:
            shape["Solidity2D"] = _numeric(shape, "Solidity_geometry")
    shape = add_missing_projected_metrics(shape)

    level_a = pd.read_csv(level_a_path, usecols=lambda column: column in {"FrameIndex", "SnMonotone"})
    stages = assign_sn_stage(level_a)
    thresholds = json.loads(thresholds_path.read_text(encoding="utf-8")) if thresholds_path.exists() else {}
    return shape, stages, thresholds, shape_meta


def add_stage_columns(shape: pd.DataFrame, stages: pd.DataFrame) -> pd.DataFrame:
    out = shape.merge(stages, on="FrameIndex", how="left", validate="many_to_one")
    if out["SnStage"].isna().any():
        missing = int(out["SnStage"].isna().sum())
        raise ValueError(f"{missing} shape rows did not match Level A FrameIndex")
    out["ShapeValid_bool"] = _bool_series(out, "ShapeValid")
    out["Area_px"] = _numeric(out, "Area_px")
    return out


def _area_weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    valid = values.notna() & weights.notna() & (weights > 0)
    if not valid.any():
        return float("nan")
    return float(np.average(values[valid], weights=weights[valid]))


def _summarize_one_group(sub: pd.DataFrame, group_values: dict[str, object]) -> list[dict[str, object]]:
    area = _numeric(sub, "Area_px")
    rows = []
    for metric in [column for column in METRIC_COLUMNS if column in sub.columns]:
        values = _numeric(sub, metric)
        valid = values.dropna()
        if valid.empty:
            stats = {
                "MetricN": 0,
                "Mean": np.nan,
                "Std": np.nan,
                "Min": np.nan,
                "P10": np.nan,
                "P25": np.nan,
                "Median": np.nan,
                "P75": np.nan,
                "P90": np.nan,
                "P95": np.nan,
                "Max": np.nan,
                "AreaWeightedMean": np.nan,
            }
        else:
            stats = {
                "MetricN": int(valid.shape[0]),
                "Mean": float(valid.mean()),
                "Std": float(valid.std(ddof=1)) if valid.shape[0] > 1 else 0.0,
                "Min": float(valid.min()),
                "P10": float(valid.quantile(0.10)),
                "P25": float(valid.quantile(0.25)),
                "Median": float(valid.quantile(0.50)),
                "P75": float(valid.quantile(0.75)),
                "P90": float(valid.quantile(0.90)),
                "P95": float(valid.quantile(0.95)),
                "Max": float(valid.max()),
                "AreaWeightedMean": _area_weighted_mean(values, area),
            }
        rows.append(
            {
                **group_values,
                "Metric": metric,
                "NRows": int(sub.shape[0]),
                "AreaSum_px": float(area.sum(skipna=True)),
                **stats,
            }
        )
    return rows


def summarize_metrics(df: pd.DataFrame, group_cols: list[str] | None = None) -> pd.DataFrame:
    if not group_cols:
        return pd.DataFrame(_summarize_one_group(df, {"Group": "all"}))
    rows: list[dict[str, object]] = []
    for key, sub in df.groupby(group_cols, dropna=False, sort=True):
        if not isinstance(key, tuple):
            key = (key,)
        group_values = {column: value for column, value in zip(group_cols, key)}
        rows.extend(_summarize_one_group(sub, group_values))
    return pd.DataFrame(rows)


def build_metric_dictionary() -> pd.DataFrame:
    rows = [
        {
            "MetricAlias": "AR_axis_aspect_ratio",
            "PipelineColumn": "AxisAspectRatio",
            "Formula": "MajorAxisLength_px / MinorAxisLength_px",
            "Interpretation": "Projected elongation magnitude; values >= 1.",
            "Boundary": "Not tracking and not deformation history.",
        },
        {
            "MetricAlias": "AR01_compact_axis_ratio",
            "PipelineColumn": "AspectRatio01",
            "Formula": "MinorAxisLength_px / MajorAxisLength_px",
            "Interpretation": "Projected axis compactness in the 0-1 direction.",
            "Boundary": "Not Wadell roundness.",
        },
        {
            "MetricAlias": "S_projected_sphericity_proxy",
            "PipelineColumn": "ProjectedSphericity2D",
            "Formula": "2 * sqrt(pi * Area_px) / P_outer_boundary",
            "Interpretation": "Projected 2D compactness relative to a circle.",
            "Boundary": "Not 3D sphericity.",
        },
        {
            "MetricAlias": "CR_circularity2d_boundary_proxy",
            "PipelineColumn": "Circularity2D_boundary",
            "Formula": "4 * pi * Area_px / P_outer_boundary^2",
            "Interpretation": "2D circularity diagnostic.",
            "Boundary": "Not Wadell roundness; tiny/small artifacts excluded.",
        },
        {
            "MetricAlias": "CR_projected_convexity_perimeter_proxy",
            "PipelineColumn": "ProjectedConvexityPerimeter",
            "Formula": "Pc_outer_boundary / P_outer_boundary",
            "Interpretation": "Projected perimeter convexity diagnostic.",
            "Boundary": "Reported separately because CR naming differs across particle-shape literature.",
        },
        {
            "MetricAlias": "R_projected_roughness_proxy",
            "PipelineColumn": "ProjectedRoughness_boundary",
            "Formula": "P_outer_boundary / Pc_outer_boundary",
            "Interpretation": "2D exterior-boundary complexity proxy.",
            "Boundary": "Not 3D roughness and not full fluid-fluid interfacial area.",
        },
        {
            "MetricAlias": "P_projected_regularity_proxy",
            "PipelineColumn": "ProjectedRegularity2D",
            "Formula": "mean(ProjectedSphericity2D, AspectRatio01, Solidity2D)",
            "Interpretation": "Compact summary used for ranking projected 2D shape.",
            "Boundary": "Not original Krumbein regularity.",
        },
        {
            "MetricAlias": "solidity_projected_convexity",
            "PipelineColumn": "Solidity2D",
            "Formula": "Area_px / ConvexArea_px",
            "Interpretation": "Projected convexity/concavity proxy.",
            "Boundary": "2D projection only.",
        },
        {
            "MetricAlias": "major_axis_length",
            "PipelineColumn": "MajorAxisLength_px",
            "Formula": "major axis of the equivalent second-moment ellipse",
            "Interpretation": "Projected long-axis length.",
            "Boundary": "Ellipse is a moment descriptor, not a fitted physical boundary.",
        },
        {
            "MetricAlias": "minor_axis_length",
            "PipelineColumn": "MinorAxisLength_px",
            "Formula": "minor axis of the equivalent second-moment ellipse",
            "Interpretation": "Projected short-axis length.",
            "Boundary": "Ellipse is a moment descriptor, not a fitted physical boundary.",
        },
    ]
    return pd.DataFrame(rows)


def _fmt(value: object) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return "NA"
    return f"{float(numeric):.6g}"


def write_formula_notes(output_dir: Path, thresholds: dict, shape_class_version: str = "v0") -> None:
    threshold_data = thresholds.get("thresholds", {}) if isinstance(thresholds, dict) else {}
    class_label = "v1" if shape_class_version == "v1" else "v0"
    lines = [
        "# G21 Blob Shape Parameter Formula and Classification Notes",
        "",
        f"This document records the projected 2D shape-parameter formulas and {class_label} class gates used by the G21 morphology data product.",
        "",
        "## Core Formulas",
        "",
        "```text",
        "EquivRadius_px = sqrt(Area_px / pi)",
        "EquivDiameter_px = 2 * EquivRadius_px",
        "AxisAspectRatio = MajorAxisLength_px / MinorAxisLength_px",
        "AspectRatio01 = MinorAxisLength_px / MajorAxisLength_px",
        "Solidity2D = Area_px / ConvexArea_px",
        "ProjectedSphericity2D = 2 * sqrt(pi * Area_px) / P_outer_boundary",
        "Circularity2D_boundary = 4 * pi * Area_px / P_outer_boundary^2",
        "ProjectedConvexityPerimeter = Pc_outer_boundary / P_outer_boundary",
        "ProjectedRoughness_boundary = P_outer_boundary / Pc_outer_boundary",
        "PtotalOverPouter = P_total_boundary / P_outer_boundary",
        "ProjectedRegularity2D = mean(ProjectedSphericity2D, AspectRatio01, Solidity2D)",
        "```",
        "",
        "## Literature-Term Mapping",
        "",
        "- `AR` is represented by `AxisAspectRatio` and `AspectRatio01`.",
        "- `S` is represented by `ProjectedSphericity2D`, a projected compactness proxy.",
        "- `CR` is reported as separate circularity and perimeter-convexity diagnostics because CR notation differs across particle-shape papers.",
        "- `P` is represented by `ProjectedRegularity2D`, a ranking proxy.",
        "- `R` is represented by `ProjectedRoughness_boundary`, a projected exterior-boundary proxy.",
        "",
        "## Scope Boundaries",
        "",
        "- ProjectedSphericity2D is not 3D sphericity.",
        "- Circularity2D_boundary is not Wadell roundness.",
        "- ProjectedRegularity2D is not original Krumbein regularity.",
        "- ProjectedRoughness_boundary is a 2D exterior-boundary proxy.",
        "- P_outer_boundary does not represent full NAPL-water interfacial area.",
        "- Mean channel depth can support only apparent quasi-2D volume convention, not 3D roughness.",
        "",
        "## Metric Independence and Provenance",
        "",
        "- AxisAspectRatio and AspectRatio01 are reciprocal forms. Use one primary axis-ratio form for classification to avoid double-counting elongation.",
        "- ProjectedSphericity2D and Circularity2D_boundary are mathematically related because both use projected area and exterior perimeter.",
        "- ProjectedRegularity2D is a ranking proxy only. It is not a calibrated physical regularity or a primary mechanism metric.",
        "- MetricSource, BoundaryMetricSource, DatasetSubset, and FullSidecarDerived fields should be used when comparing products from different geometry sources.",
        "- ShapeClassV0 and ShapeClassV1 must not be mixed in the same summary without an explicit version column.",
        "",
        "## Reliability Gate",
        "",
        "```text",
        "v0:",
        "  Area_px < 250 -> small_unclassified / count-only",
        "  Area_px >= 250 and BoundaryMetricValid=false -> boundary_invalid",
        "  250 <= Area_px < 500 -> medium_caution",
        "",
        "v1:",
        "  Area_px < 100 -> count_only_lt100",
        "  100 <= Area_px < 250 -> low_area_*_100_249 projected-shape caution",
        "  Area_px >= 250 and BoundaryMetricValid=false -> boundary_invalid",
        "  Area_px >= 250 and BoundaryMetricValid=true -> geometry_interpretable",
        "  Area_px >= 500 and BoundaryMetricValid=true -> high-confidence geometry tier",
        "```",
        "",
        f"## {class_label.upper()} Shape-Class Gate",
        "",
        "The reference population for thresholds is `BoundaryMetricValid=true` and `Area_px>=250`.",
        "The stored threshold quantiles are:",
        "",
        "| Metric | q25 | q50 | q75 | q90 |",
        "|---|---:|---:|---:|---:|",
    ]
    for metric in [
        "ProjectedSphericity2D",
        "AspectRatio01",
        "AxisAspectRatio",
        "Solidity2D",
        "ProjectedRoughness_boundary",
        "PtotalOverPouter",
        "ProjectedRegularity2D",
    ]:
        q = threshold_data.get(metric, {})
        lines.append(
            f"| `{metric}` | {_fmt(q.get('q25'))} | {_fmt(q.get('q50'))} | {_fmt(q.get('q75'))} | {_fmt(q.get('q90'))} |"
        )
    lines.extend(
        [
            "",
            f"{class_label.upper()} classes are assigned after the reliability gate:",
            "",
            "```text",
            "v0 compact_round / v1 compact_regular:",
            "  high ProjectedSphericity2D, high AspectRatio01, low AxisAspectRatio, high Solidity2D",
            "",
            "elongated:",
            "  AxisAspectRatio >= q90",
            "",
            "concave_lobed:",
            "  low Solidity2D with moderate elongation and without strong boundary-complex signal",
            "",
            "branched_complex:",
            "  low Solidity2D plus high elongation, high exterior-boundary complexity, or high PtotalOverPouter",
            "",
            "compact_irregular:",
            "  high Solidity2D with boundary-QC caution signal",
            "",
            "v1 near_compact_regular:",
            "  intermediate compact regular projected shape; avoids the term Wadell roundness",
            "",
            "v1 moderately_elongated:",
            "  q75 <= AxisAspectRatio < q90",
            "",
            "v1 moderately_concave:",
            "  q25 <= Solidity2D < q50; projected low-solidity proxy only",
            "",
            "ambiguous_valid:",
            "  passes reliability gate but does not satisfy the class gates above",
            "```",
            "",
            "These labels describe population-level projected 2D structure. They do not imply tracking, split/merge lineage, boundary fractal dimension, 3D roughness, or true fluid-fluid interfacial area.",
            "",
        ]
    )
    (output_dir / "g21_blob_shape_parameter_formula_notes.md").write_text("\n".join(lines), encoding="utf-8")
    if shape_class_version == "v1":
        (output_dir / "g21_blob_shape_parameter_formula_notes_v1.md").write_text("\n".join(lines), encoding="utf-8")


def write_v1_decision_rules(output_dir: Path) -> None:
    lines = [
        "# G21 Shape-Class V1 Decision Rules",
        "",
        "Shape-class v1 applies reliability gates before projected 2D morphology labels.",
        "",
        "```text",
        "Area_px < 100 -> count_only_lt100",
        "100 <= Area_px < 250 -> low_area_*_100_249 caution classes",
        "Area_px >= 250 and BoundaryMetricValid=false -> boundary_invalid",
        "Area_px >= 250 and BoundaryMetricValid=true -> projected 2D morphology classes",
        "Area_px >= 500 and BoundaryMetricValid=true -> high-confidence geometry tier",
        "```",
        "",
        "Morphology rule order: branched_complex, compact_regular, elongated, concave_lobed, compact_irregular, near_compact_regular, moderately_elongated, moderately_concave, then ambiguous_valid.",
        "",
        "Diagnostic flags are non-exclusive annotations and do not replace `ShapeClassV1`.",
        "",
    ]
    (output_dir / "g21_shape_class_v1_decision_rules.md").write_text("\n".join(lines), encoding="utf-8")


def write_v1_field_dictionary(output_dir: Path) -> None:
    lines = [
        "# G21 Shape-Class V1 Field Dictionary",
        "",
        "| Field | Meaning |",
        "|---|---|",
        "| `ShapeClassV1` | Formal v1 projected 2D shape class. |",
        "| `ShapeClassV1Reason` | Deterministic assignment reason. |",
        "| `ShapeV1InterpretationTier` | Count-only, low-area caution, geometry-interpretable, or boundary-invalid tier. |",
        "| `MetricSource` | Row-level metric source. |",
        "| `BoundaryMetricSource` | Boundary/perimeter metric source. |",
        "| `DatasetSubset` | Dataset subset represented by the row. |",
        "| `FullSidecarDerived` | Whether rows derive from the full sidecar geometry table. |",
        "| `LowAreaProjectedShapeCaution` | 100-249 px low-area caution. |",
        "| `ModerateBoundaryComplexityFlag` | Projected roughness q75-q90. |",
        "| `HighBoundaryComplexityFlag` | Projected roughness >= q90. |",
        "| `InternalBoundarySignalFlag` | `PtotalOverPouter > 1`. |",
        "| `TouchesImageBorderFlag` | Blob touches image border. |",
        "| `CircularityArtifactFlag` | `Circularity2D_boundary > 1.05`; exclude from compact/regular high-confidence interpretation. |",
        "| `RoughnessInvalidFlag` | `ProjectedRoughness_boundary < 1`; exclude if present. |",
        "",
    ]
    (output_dir / "g21_shape_class_v1_field_dictionary.md").write_text("\n".join(lines), encoding="utf-8")


def build_shape_parameter_statistics(
    morphology_dir: str | Path,
    level_a_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    shape_class_version: str = "v0",
    shape_class_v1_dir: str | Path | None = None,
) -> dict[str, object]:
    morphology_path = Path(morphology_dir)
    level_a_path = Path(level_a_dir) if level_a_dir is not None else morphology_path.parent
    version = shape_class_version.lower()
    if version not in {"v0", "v1"}:
        raise ValueError("shape_class_version must be 'v0' or 'v1'")
    if output_dir is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = "_v1" if version == "v1" else ""
        out_dir = morphology_path / f"g21_blob_shape_parameter_statistics{suffix}_{stamp}"
    else:
        out_dir = Path(output_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise FileExistsError(f"Output directory is not empty: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    shape, stages, thresholds, shape_meta = read_shape_inputs(
        morphology_path,
        level_a_path,
        shape_class_version=version,
        shape_class_v1_dir=Path(shape_class_v1_dir) if shape_class_v1_dir is not None else None,
    )
    data = add_stage_columns(shape, stages)
    if "ReliabilityClass" not in data.columns:
        data["ReliabilityClass"] = "unknown"
    if "AreaTier" not in data.columns:
        data["AreaTier"] = "unknown"

    metric_dictionary = build_metric_dictionary()
    overall = summarize_metrics(data)
    shape_valid = summarize_metrics(data.loc[_bool_series(data, "ShapeValid")])
    by_reliability = summarize_metrics(data, ["ReliabilityClass"])
    by_area_tier = summarize_metrics(data, ["AreaTier"])
    by_class = summarize_metrics(data, ["ShapeClass"])
    by_stage = summarize_metrics(data, ["SnStage"])
    by_class_stage = summarize_metrics(data, ["SnStage", "ShapeClass"])

    write_formula_notes(out_dir, thresholds, shape_class_version=version)
    if version == "v1":
        write_v1_decision_rules(out_dir)
        write_v1_field_dictionary(out_dir)
    metric_dictionary.to_csv(out_dir / "blob_shape_parameter_metric_dictionary.csv", index=False)
    overall.to_csv(out_dir / "blob_shape_parameter_overall_statistics.csv", index=False)
    shape_valid.to_csv(out_dir / "blob_shape_parameter_shape_valid_statistics.csv", index=False)
    by_reliability.to_csv(out_dir / "blob_shape_parameter_by_reliability_class.csv", index=False)
    by_area_tier.to_csv(out_dir / "blob_shape_parameter_by_area_tier.csv", index=False)
    by_class.to_csv(out_dir / "blob_shape_parameter_by_class.csv", index=False)
    by_stage.to_csv(out_dir / "blob_shape_parameter_by_sn_stage.csv", index=False)
    by_class_stage.to_csv(out_dir / "blob_shape_parameter_by_class_stage.csv", index=False)

    outputs = REQUIRED_OUTPUTS + (V1_EXTRA_OUTPUTS if version == "v1" else [])
    manifest = {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "morphology_dir": str(morphology_path),
        "level_a_dir": str(level_a_path),
        "output_dir": str(out_dir),
        "shape_class": shape_meta,
        "row_counts": {
            "blob_rows": int(data.shape[0]),
            "frames": int(data["FrameIndex"].nunique()),
            "shape_valid_rows": int(_bool_series(data, "ShapeValid").sum()),
        },
        "outputs": outputs,
        "scope": {
            "projected_2d_only": True,
            "shape_class_version": version,
            "tracking": False,
            "split_merge_lineage": False,
            "fractal_dimension": False,
            "roughness_3d": False,
            "true_fluid_fluid_interfacial_area": False,
            "wadell_roundness": False,
        },
    }
    (out_dir / "blob_shape_parameter_statistics_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build G21 projected 2D blob shape-parameter statistics.")
    parser.add_argument("--morphology-dir", required=True, help="Morphology data product directory.")
    parser.add_argument("--level-a-dir", help="Level A postprocess directory. Defaults to morphology-dir parent.")
    parser.add_argument("--output-dir", help="Optional explicit output directory.")
    parser.add_argument("--shape-class-version", choices=["v0", "v1"], default="v0")
    parser.add_argument("--shape-class-v1-dir", help="Formal shape-class v1 package directory.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_shape_parameter_statistics(
        args.morphology_dir,
        args.level_a_dir,
        args.output_dir,
        shape_class_version=args.shape_class_version,
        shape_class_v1_dir=args.shape_class_v1_dir,
    )
    print(json.dumps({"output_dir": result["output_dir"], "row_counts": result["row_counts"]}, indent=2))


if __name__ == "__main__":
    main()
