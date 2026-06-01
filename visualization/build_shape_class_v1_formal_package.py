"""Formalize G21 shape-class v1 as a data-product layer."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


OUTPUTS = [
    "blob_shape_class_v1_by_blob.csv",
    "shape_class_v1_summary_by_class.csv",
    "shape_class_v1_summary_by_stage.csv",
    "shape_class_v0_to_v1_transition_count.csv",
    "shape_class_v0_to_v1_transition_area.csv",
    "shape_class_v0_to_v1_transition_by_sn_stage_count.csv",
    "shape_class_v0_to_v1_transition_by_sn_stage_area.csv",
    "shape_class_v1_gate_audit.csv",
    "shape_class_v1_acceptance_gate_audit.csv",
    "shape_class_v1_schema.md",
    "g21_shape_class_v1_acceptance_review.md",
    "g21_shape_class_v1_data_product_acceptance_review.md",
    "g21_blob_shape_parameter_formula_notes_v1.md",
    "g21_shape_class_v1_decision_rules.md",
    "g21_shape_class_v1_field_dictionary.md",
    "shape_class_v1_formal_manifest.json",
]

BOUNDARY_CLASS_V1 = {
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

ACCEPTED_REFINEMENT_DECISIONS = {
    "PASS",
    "PASS_WITH_NEAR_THRESHOLD_NOTE",
}

REQUIRED_V1_COLUMNS = {
    "FrameIndex",
    "ShapeClassV0",
    "ShapeClassV1",
    "ShapeClassV1Reason",
    "ShapeClassVersion",
    "ShapeV1InterpretationTier",
    "MetricSource",
    "BoundaryMetricSource",
    "DatasetSubset",
    "FullSidecarDerived",
    "Area_px",
}


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


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_required_json(path: Path, label: str) -> dict:
    if not path.exists():
        raise ValueError(f"Missing required {label}: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _git_commit(repo_root: Path | None = None) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            cwd=str(repo_root or _default_repo_root()),
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def _load_v1_table(v1_dir: Path) -> pd.DataFrame:
    path = v1_dir / "blob_shape_class_v1_by_blob.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing v1 by-blob table: {path}")
    df = pd.read_csv(path)
    missing = sorted(REQUIRED_V1_COLUMNS - set(df.columns))
    if missing:
        raise ValueError(f"v1 by-blob table is missing required column(s): {', '.join(missing)}")
    return df


def _validate_refinement_manifest(refinement_manifest: dict, df: pd.DataFrame) -> None:
    decision = str(refinement_manifest.get("qc", {}).get("decision_label", ""))
    if decision not in ACCEPTED_REFINEMENT_DECISIONS:
        raise ValueError(
            "shape_class_v1_manifest does not have an accepted refinement decision: "
            f"{decision if decision else 'missing'}"
        )
    row_counts = refinement_manifest.get("row_counts", {}) if isinstance(refinement_manifest, dict) else {}
    expected_rows = row_counts.get("rows")
    if expected_rows is None:
        raise ValueError("shape_class_v1_manifest is missing row_counts.rows")
    if int(expected_rows) != int(len(df)):
        raise ValueError(
            "shape_class_v1_manifest row-count mismatch: "
            f"manifest rows={expected_rows}; table rows={len(df)}"
        )
    expected_frames = row_counts.get("frames")
    if expected_frames is None:
        raise ValueError("shape_class_v1_manifest is missing row_counts.frames")
    observed_frames = int(pd.to_numeric(df["FrameIndex"], errors="coerce").dropna().nunique())
    if int(expected_frames) != observed_frames:
        raise ValueError(
            "shape_class_v1_manifest frame-count mismatch: "
            f"manifest frames={expected_frames}; table frames={observed_frames}"
        )


def _stage_table(level_a_dir: Path | None, frame_index: pd.Series) -> pd.DataFrame:
    if level_a_dir is None:
        level_a_path = None
    else:
        level_a_path = level_a_dir / "dissolution_rates.csv"
    if level_a_path is None or not level_a_path.exists():
        frames = pd.DataFrame({"FrameIndex": sorted(pd.to_numeric(frame_index, errors="coerce").dropna().astype(int).unique())})
        frames["SnStage"] = "unknown"
        return frames

    level_a = pd.read_csv(level_a_path, usecols=lambda c: c in {"FrameIndex", "SnMonotone"})
    level_a["FrameIndex"] = pd.to_numeric(level_a["FrameIndex"], errors="coerce").astype("Int64")
    sn = pd.to_numeric(level_a["SnMonotone"], errors="coerce")
    frame = level_a["FrameIndex"].astype(int)
    endpoint_start = int(np.ceil(int(frame.max()) * 0.95))
    stage = pd.Series("active_dissolution", index=level_a.index, dtype="object")
    stage.loc[sn >= 0.20] = "early_depletion"
    stage.loc[(sn >= 0.005) & (sn < 0.05)] = "late_depletion"
    stage.loc[(sn < 0.005) | (frame >= endpoint_start)] = "endpoint"
    level_a["SnStage"] = stage
    return level_a[["FrameIndex", "SnStage"]]


def _add_formal_provenance(df: pd.DataFrame, morphology_dir: Path, v1_dir: Path, git_commit: str) -> pd.DataFrame:
    out = df.copy()
    out["ShapeClassSource"] = "shape_class_v1_formal_package"
    out["AreaThresholdVersion"] = "area_gate_v1_lt100_100_249_ge250_ge500"
    out["ThresholdsJson"] = str(morphology_dir / "blob_morphology_thresholds.json")
    out["InputMorphologyProduct"] = str(morphology_dir)
    out["InputShapeClassV1Dir"] = str(v1_dir)
    out["GitCommit"] = git_commit
    out["Projected2DOnly"] = True
    return out


def _summary(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    total_n = len(df)
    total_area = _numeric(df, "Area_px").sum(skipna=True)
    rows = []
    for key, sub in df.groupby(group_cols, dropna=False, sort=True):
        if not isinstance(key, tuple):
            key = (key,)
        area_sum = _numeric(sub, "Area_px").sum(skipna=True)
        row = {col: value for col, value in zip(group_cols, key)}
        row.update(
            {
                "NRows": int(len(sub)),
                "CountFraction": float(len(sub) / total_n) if total_n else np.nan,
                "AreaSum_px": float(area_sum),
                "AreaFraction": float(area_sum / total_area) if total_area else np.nan,
                "ShapeClassVersion": "v1",
                "MetricSource": "full_duration_sidecar",
                "BoundaryMetricSource": "corrected_sidecar_boundary",
                "DatasetSubset": "full_duration_sidecar",
                "FullSidecarDerived": True,
                "AreaThresholdVersion": "area_gate_v1_lt100_100_249_ge250_ge500",
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def _transition_count(df: pd.DataFrame) -> pd.DataFrame:
    return pd.crosstab(df["ShapeClassV0"], df["ShapeClassV1"]).reset_index()


def _transition_area(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.pivot_table(index="ShapeClassV0", columns="ShapeClassV1", values="Area_px", aggfunc="sum", fill_value=0.0)
        .reset_index()
        .rename_axis(None, axis=1)
    )


def _stage_transitions(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    counts = (
        df.groupby(["SnStage", "ShapeClassV0", "ShapeClassV1"], dropna=False)
        .size()
        .rename("Count")
        .reset_index()
    )
    areas = (
        df.groupby(["SnStage", "ShapeClassV0", "ShapeClassV1"], dropna=False)["Area_px"]
        .sum()
        .rename("AreaSum_px")
        .reset_index()
    )
    return counts, areas


def _audit_gates(df: pd.DataFrame, transition_count_sum: int, transition_area_sum: float) -> pd.DataFrame:
    area = _numeric(df, "Area_px")
    classes = df["ShapeClassV1"].astype(str)
    shape_version = df["ShapeClassVersion"].astype(str) if "ShapeClassVersion" in df.columns else pd.Series("", index=df.index)
    rows = []

    def add(gate: str, status: str, value: object, expected: str) -> None:
        rows.append({"Gate": gate, "Status": status, "Value": value, "Expected": expected})

    add("all_rows_have_shape_class_v1", "PASS" if classes.ne("").all() and classes.notna().all() else "FAIL", int(classes.ne("").sum()), "all rows")
    add(
        "all_rows_shape_class_version_v1",
        "PASS" if shape_version.eq("v1").all() else "FAIL",
        int(shape_version.eq("v1").sum()),
        "all rows have ShapeClassVersion == v1",
    )
    for column, expected in [
        ("MetricSource", "full_duration_sidecar"),
        ("BoundaryMetricSource", "corrected_sidecar_boundary"),
        ("DatasetSubset", "full_duration_sidecar"),
    ]:
        if column in df.columns:
            values = df[column].astype(str)
            passed = values.eq(expected).all()
            value = int(values.eq(expected).sum())
        else:
            passed = False
            value = "missing"
        add(f"{column}_matches_expected", "PASS" if passed else "FAIL", value, f"all rows are {expected}")
    full_sidecar = _bool_series(df, "FullSidecarDerived", default=False)
    add(
        "FullSidecarDerived_true",
        "PASS" if full_sidecar.all() else "FAIL",
        int(full_sidecar.sum()),
        "all rows true",
    )
    add(
        "area_lt100_count_only",
        "PASS" if classes[area < 100].eq("count_only_lt100").all() else "FAIL",
        int((area < 100).sum()),
        "Area < 100 px rows are count_only_lt100",
    )
    low_area = area.ge(100) & area.lt(250)
    add(
        "area_100_249_low_area_only",
        "PASS" if classes[low_area].str.startswith("low_area_").all() else "FAIL",
        int(low_area.sum()),
        "100 <= Area < 250 px rows are low_area_* caution/candidate",
    )
    promoted = int(((area < 250) & classes.isin(BOUNDARY_CLASS_V1)).sum())
    add("area_lt250_not_boundary_class", "PASS" if promoted == 0 else "FAIL", promoted, "0")
    roughness_invalid = _bool_series(df, "RoughnessInvalidFlag", default=False)
    roughness_boundary_violations = int((roughness_invalid & classes.isin(BOUNDARY_CLASS_V1)).sum())
    add(
        "roughness_invalid_not_boundary_interpretable",
        "PASS" if roughness_boundary_violations == 0 else "FAIL",
        roughness_boundary_violations,
        "0 RoughnessInvalidFlag rows in boundary morphology classes",
    )
    circularity_artifact = _bool_series(df, "CircularityArtifactFlag", default=False)
    compact_regular = classes.isin(["compact_regular", "near_compact_regular"])
    circ_compact_high_conf = int((circularity_artifact & compact_regular & area.ge(500)).sum())
    add(
        "circularity_artifact_not_compact_regular_high_confidence",
        "PASS" if circ_compact_high_conf == 0 else "FAIL",
        circ_compact_high_conf,
        "0 CircularityArtifactFlag rows in compact/regular high-confidence classes",
    )
    add(
        "transition_count_conserved",
        "PASS" if transition_count_sum == len(df) else "FAIL",
        int(transition_count_sum),
        str(len(df)),
    )
    total_area = float(area.sum(skipna=True))
    add(
        "transition_area_conserved",
        "PASS" if np.isclose(transition_area_sum, total_area, rtol=1e-12, atol=1e-6) else "FAIL",
        float(transition_area_sum),
        f"{total_area}",
    )
    interpretable = ~classes.str.startswith("low_area_") & ~classes.isin(["count_only_lt100", "boundary_invalid"])
    ambiguous_fraction = float((classes.eq("ambiguous_valid").sum() / interpretable.sum())) if int(interpretable.sum()) else np.nan
    if ambiguous_fraction <= 0.25:
        amb_status = "PASS"
    elif ambiguous_fraction <= 0.255:
        amb_status = "WARN"
    else:
        amb_status = "FAIL"
    add("ambiguous_interpretable_fraction", amb_status, ambiguous_fraction, "<=0.25, tolerance <=0.255")
    return pd.DataFrame(rows)


def _decision(audit: pd.DataFrame) -> str:
    statuses = set(audit["Status"].astype(str))
    if "FAIL" in statuses:
        return "BLOCKED_SHAPE_CLASS_V1_FORMAL"
    if "WARN" in statuses:
        return "ACCEPT_SHAPE_CLASS_V1_FORMAL_WITH_NEAR_THRESHOLD_NOTE"
    return "ACCEPT_SHAPE_CLASS_V1_FORMAL_WITH_SCOPE_LIMITS"


def _write_schema(path: Path) -> None:
    lines = [
        "# Shape-Class V1 Formal Schema",
        "",
        "Required row-level fields:",
        "",
        "- `ShapeClassV0`: original v0 class label.",
        "- `ShapeClassV1`: formal v1 class label.",
        "- `ShapeClassV1Reason`: deterministic v1 assignment reason.",
        "- `ShapeClassVersion`: fixed value `v1`.",
        "- `ShapeClassSource`: fixed value `shape_class_v1_formal_package`.",
        "- `ShapeV1InterpretationTier`: interpretation tier.",
        "- `MetricSource`: expected `full_duration_sidecar`.",
        "- `BoundaryMetricSource`: expected `corrected_sidecar_boundary`.",
        "- `DatasetSubset`: expected `full_duration_sidecar`.",
        "- `FullSidecarDerived`: true for this G21 product.",
        "- `AreaThresholdVersion`: fixed area-gate identifier.",
        "- `InputMorphologyProduct`: source morphology product directory.",
        "- `InputShapeClassV1Dir`: source v1 refinement directory.",
        "- `GitCommit`: repository commit used to generate the formal package.",
        "",
        "Scope: projected 2D only. No tracking, split/merge lineage, fractal dimension, 3D roughness, or true fluid-fluid interfacial area is implied.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_formula_notes_v1(path: Path) -> None:
    lines = [
        "# G21 Blob Shape Parameter Formula Notes V1",
        "",
        "All terms below are projected 2D image-derived quantities. They do not represent 3D roughness, true Wadell roundness, true 3D sphericity, tracking, split/merge lineage, or full fluid-fluid interfacial area.",
        "",
        "## CR / Circularity Ratio",
        "",
        "`Circularity2D_boundary = 4 * pi * Area_px / P_outer_boundary^2`.",
        "",
        "This is a 2D circularity diagnostic based on exterior projected perimeter. It is not Wadell roundness. Rows with `CircularityArtifactFlag=True` are not valid support for compact/regular high-confidence interpretation.",
        "",
        "## AR / Axis Ratio",
        "",
        "`AxisAspectRatio = MajorAxisLength_px / MinorAxisLength_px` and `AspectRatio01 = MinorAxisLength_px / MajorAxisLength_px`.",
        "",
        "`AxisAspectRatio` is the primary elongation classifier. `AspectRatio01` is its reciprocal compact-axis form and should not be treated as an independent evidence dimension.",
        "",
        "## S / Projected Sphericity Proxy",
        "",
        "`ProjectedSphericity2D = 2 * sqrt(pi * Area_px) / P_outer_boundary`.",
        "",
        "This is a projected 2D compactness proxy. It is mathematically related to `Circularity2D_boundary` and is not 3D particle sphericity.",
        "",
        "## P / Projected Regularity Proxy",
        "",
        "`ProjectedRegularity2D = mean(ProjectedSphericity2D, AspectRatio01, Solidity2D)`.",
        "",
        "This is an internal ranking proxy for representative blob selection and summary sorting. It is not original Krumbein regularity and is not used as a primary mechanism metric.",
        "",
        "## R / Projected Roughness Proxy",
        "",
        "`ProjectedRoughness_boundary = P_outer_boundary / Pc_outer_boundary`.",
        "",
        "`P_outer_boundary` is the exterior projected boundary and `Pc_outer_boundary` is the projected convex-hull perimeter. The ratio is a 2D exterior-boundary complexity proxy only. `P_outer_boundary` is not full NAPL-water interfacial area, and this ratio is not 3D roughness.",
        "",
        "## Additional Geometry Fields",
        "",
        "- `Solidity2D = Area_px / ConvexArea_px`: projected convexity / low-solidity proxy.",
        "- `PtotalOverPouter = P_total_boundary / P_outer_boundary`: projected internal-boundary signal; mostly a diagnostic flag, not a mechanism class.",
        "- `MajorAxisLength_px` and `MinorAxisLength_px`: second-moment ellipse axes. The ellipse summarizes moment geometry and is not a fitted physical boundary.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_decision_rules(path: Path) -> None:
    lines = [
        "# G21 Shape-Class V1 Decision Rules",
        "",
        "Shape-class v1 is a deterministic projected 2D morphology labeling layer. Reliability gates are applied before morphology classes.",
        "",
        "## Reliability Gates",
        "",
        "```text",
        "Area_px < 100 -> count_only_lt100",
        "Area_px < 100",
        "  -> ShapeClassV1 = count_only_lt100",
        "  -> ShapeV1InterpretationTier = count_only",
        "",
        "100 <= Area_px < 250",
        "  -> low_area_compact_candidate_100_249",
        "  -> low_area_elongated_candidate_100_249",
        "  -> low_area_projected_shape_caution_100_249",
        "  -> ShapeV1InterpretationTier = low_area_shape_caution",
        "",
        "Area_px >= 250 and BoundaryMetricValid = false",
        "  -> ShapeClassV1 = boundary_invalid",
        "  -> ShapeV1InterpretationTier = no_boundary_interpretation",
        "",
        "Area_px >= 250 and BoundaryMetricValid = true",
        "  -> eligible for projected 2D morphology classes",
        "",
        "Area_px >= 500 and BoundaryMetricValid = true",
        "  -> high-confidence geometry tier for conservative summaries",
        "```",
        "",
        "## Morphology Class Priority",
        "",
        "The first matching rule wins after the reliability gates:",
        "",
        "```text",
        "1. preserved v0 branched_complex -> branched_complex",
        "2. renamed v0 compact_round -> compact_regular",
        "3. AxisAspectRatio >= q90 -> elongated",
        "4. preserved v0 concave_lobed -> concave_lobed",
        "5. preserved v0 compact_irregular -> compact_irregular",
        "6. high ProjectedSphericity2D + compact axis ratio + high Solidity2D -> near_compact_regular",
        "7. q75 <= AxisAspectRatio < q90 -> moderately_elongated",
        "8. q25 <= Solidity2D < q50 -> moderately_concave",
        "9. otherwise -> ambiguous_valid",
        "```",
        "",
        "## Diagnostic Flags",
        "",
        "The AF-AL columns are non-exclusive diagnostic flags, not mutually exclusive shape classes:",
        "",
        "- `LowAreaProjectedShapeCaution`: 100-249 px low-area caution row.",
        "- `ModerateBoundaryComplexityFlag`: projected roughness between q75 and q90.",
        "- `HighBoundaryComplexityFlag`: projected roughness at or above q90.",
        "- `InternalBoundarySignalFlag`: `PtotalOverPouter > 1`.",
        "- `TouchesImageBorderFlag`: blob touches the image border.",
        "- `CircularityArtifactFlag`: `Circularity2D_boundary > 1.05`.",
        "- `RoughnessInvalidFlag`: `ProjectedRoughness_boundary < 1`.",
        "",
        "These flags can annotate a class but do not replace `ShapeClassV1`.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_field_dictionary(path: Path) -> None:
    rows = [
        ("ShapeClassV0", "string", "Previous v0 label retained for transition auditing.", "Do not mix with v1 summaries without version field."),
        ("ShapeClassV1", "string", "Formal v1 projected 2D shape class.", "Primary class label for v1 summaries."),
        ("ShapeClassV1Reason", "string", "Deterministic assignment rule that produced ShapeClassV1.", "Use for audit and debugging."),
        ("ShapeClassVersion", "string", "Fixed value `v1`.", "Prevents mixing v0 and v1 outputs."),
        ("ShapeV1InterpretationTier", "string", "count_only, low_area_shape_caution, geometry_interpretable, or no_boundary_interpretation.", "Use before any morphology interpretation."),
        ("MetricSource", "string", "Metric source for row-level geometry fields.", "Expected `full_duration_sidecar` in this G21 formal package."),
        ("BoundaryMetricSource", "string", "Source for boundary/perimeter metrics.", "Expected `corrected_sidecar_boundary`."),
        ("DatasetSubset", "string", "Dataset subset represented by the row.", "Expected `full_duration_sidecar`."),
        ("FullSidecarDerived", "boolean", "Whether row came from full sidecar-derived geometry product.", "Must be true for full-duration v1 geometry statistics."),
        ("AreaThresholdVersion", "string", "Identifier for 100/250/500 px gate convention.", "Current value: `area_gate_v1_lt100_100_249_ge250_ge500`."),
        ("LowAreaProjectedShapeCaution", "boolean", "Area between 100 and 249 px.", "Caution only; not reliable boundary morphology."),
        ("ModerateBoundaryComplexityFlag", "boolean", "Projected roughness between q75 and q90.", "Diagnostic flag only."),
        ("HighBoundaryComplexityFlag", "boolean", "Projected roughness at or above q90.", "Diagnostic flag only."),
        ("InternalBoundarySignalFlag", "boolean", "`PtotalOverPouter > 1`.", "Projected internal-boundary diagnostic only."),
        ("TouchesImageBorderFlag", "boolean", "Blob touches the image border.", "Potential crop/border caution."),
        ("CircularityArtifactFlag", "boolean", "`Circularity2D_boundary > 1.05`.", "Exclude from compact/regular high-confidence interpretation."),
        ("RoughnessInvalidFlag", "boolean", "`ProjectedRoughness_boundary < 1`.", "Invalid roughness condition; exclude if present."),
        ("Projected2DOnly", "boolean", "Scope flag.", "No 3D roughness or true interfacial area implied."),
    ]
    lines = [
        "# G21 Shape-Class V1 Field Dictionary",
        "",
        "| Field | Type | Meaning | Interpretation Rule |",
        "|---|---|---|---|",
    ]
    for field, kind, meaning, rule in rows:
        lines.append(f"| `{field}` | {kind} | {meaning} | {rule} |")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_review(path: Path, decision_label: str, audit: pd.DataFrame, manifest: dict) -> None:
    lines = [
        "# G21 Shape-Class V1 Acceptance Review",
        "",
        f"Decision: `{decision_label}`",
        "",
        "Shape-class v1 is accepted as a formal projected 2D data-product layer only within the scope limits below.",
        "",
        "## Gate Interpretation",
        "",
        "- Area < 100 px remains count-only.",
        "- 100 <= Area < 250 px remains low-area projected-shape caution.",
        "- Area >= 250 px is the reliable projected boundary morphology tier.",
        "- The product does not support tracking, split/merge, fractal, 3D roughness, or true fluid-fluid interfacial-area claims.",
        "",
        "## Gate Audit",
        "",
        audit.to_markdown(index=False),
        "",
        "## Conservation",
        "",
        f"- Transition count sum: {manifest['conservation']['transition_count_sum']}",
        f"- Transition area sum: {manifest['conservation']['transition_area_sum_px']:.12g}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_data_product_review(path: Path, decision_label: str, audit: pd.DataFrame, manifest: dict) -> None:
    warn_rows = audit.loc[audit["Status"].astype(str).eq("WARN")]
    fail_rows = audit.loc[audit["Status"].astype(str).eq("FAIL")]
    if decision_label.startswith("BLOCKED"):
        product_decision = "BLOCKED_NEEDS_FIX"
    elif fail_rows.empty:
        product_decision = "ACCEPT_WITH_SCOPE_LIMITS_NEAR_THRESHOLD_NOTE" if not warn_rows.empty else "ACCEPT_WITH_SCOPE_LIMITS"
    else:
        product_decision = "BLOCKED_NEEDS_FIX"
    lines = [
        "# G21 Shape-Class V1 Data Product Acceptance Review",
        "",
        f"Decision: `{product_decision}`",
        f"Formal package decision: `{decision_label}`",
        "",
        "This review freezes the shape-class v1 data product for downstream projected 2D statistics. It ties together the morphology product, formal v1 by-blob table, transition conservation, area gates, provenance fields, and scope exclusions.",
        "",
        "## Accepted Scope",
        "",
        "- Full-duration projected 2D blob morphology statistics.",
        "- Shape-class v1 summaries using `ShapeClassV1` and `ShapeClassVersion = v1`.",
        "- Area-gated interpretation: `<100 px` count-only, `100-249 px` low-area caution, `>=250 px` projected morphology, `>=500 px` high-confidence tier.",
        "- Diagnostic flags AF-AL may annotate rows but are not mutually exclusive shape classes.",
        "",
        "## Excluded Scope",
        "",
        "- Tracking, split/merge lineage, per-blob lifetime, boundary fractal dimension, 3D roughness, true Wadell roundness, and true fluid-fluid interfacial area.",
        "",
        "## Gate Audit",
        "",
        audit.to_markdown(index=False),
        "",
        "## Provenance",
        "",
        f"- Morphology product: `{manifest['morphology_dir']}`",
        f"- Source v1 refinement: `{manifest['shape_class_v1_dir']}`",
        f"- Formal output: `{manifest['output_dir']}`",
        f"- Git commit: `{manifest['git_commit']}`",
        f"- Rows: `{manifest['row_counts']['rows']}`",
        f"- Frames: `{manifest['row_counts']['frames']}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def build_shape_class_v1_formal_package(
    morphology_dir: str | Path,
    shape_class_v1_dir: str | Path,
    level_a_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> dict:
    morphology_path = Path(morphology_dir)
    v1_path = Path(shape_class_v1_dir)
    if output_dir is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = morphology_path / f"g21_shape_class_v1_formal_package_{stamp}"
    else:
        out_dir = Path(output_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise FileExistsError(f"Output directory is not empty: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    git_commit = _git_commit(_default_repo_root())
    source_manifest = _read_json(morphology_path / "blob_morphology_manifest.json")
    refinement_manifest = _read_required_json(v1_path / "shape_class_v1_manifest.json", "ShapeClassV1 refinement manifest")
    df = _load_v1_table(v1_path)
    _validate_refinement_manifest(refinement_manifest, df)
    stages = _stage_table(Path(level_a_dir) if level_a_dir else morphology_path.parent, df["FrameIndex"])
    df["FrameIndex"] = _numeric(df, "FrameIndex").astype("Int64")
    df = df.merge(stages, on="FrameIndex", how="left", validate="many_to_one")
    df["SnStage"] = df["SnStage"].fillna("unknown")
    df = _add_formal_provenance(df, morphology_path, v1_path, git_commit)

    transition_count = _transition_count(df)
    transition_area = _transition_area(df)
    stage_transition_count, stage_transition_area = _stage_transitions(df)
    transition_count_sum = int(transition_count.drop(columns=["ShapeClassV0"]).to_numpy().sum())
    transition_area_sum = float(transition_area.drop(columns=["ShapeClassV0"]).to_numpy().sum())
    audit = _audit_gates(df, transition_count_sum, transition_area_sum)
    decision_label = _decision(audit)

    df.to_csv(out_dir / "blob_shape_class_v1_by_blob.csv", index=False)
    _summary(df, ["ShapeClassV1"]).to_csv(out_dir / "shape_class_v1_summary_by_class.csv", index=False)
    _summary(df, ["SnStage", "ShapeClassV1"]).to_csv(out_dir / "shape_class_v1_summary_by_stage.csv", index=False)
    transition_count.to_csv(out_dir / "shape_class_v0_to_v1_transition_count.csv", index=False)
    transition_area.to_csv(out_dir / "shape_class_v0_to_v1_transition_area.csv", index=False)
    stage_transition_count.to_csv(out_dir / "shape_class_v0_to_v1_transition_by_sn_stage_count.csv", index=False)
    stage_transition_area.to_csv(out_dir / "shape_class_v0_to_v1_transition_by_sn_stage_area.csv", index=False)
    audit.to_csv(out_dir / "shape_class_v1_gate_audit.csv", index=False)
    audit.to_csv(out_dir / "shape_class_v1_acceptance_gate_audit.csv", index=False)
    _write_schema(out_dir / "shape_class_v1_schema.md")
    _write_formula_notes_v1(out_dir / "g21_blob_shape_parameter_formula_notes_v1.md")
    _write_decision_rules(out_dir / "g21_shape_class_v1_decision_rules.md")
    _write_field_dictionary(out_dir / "g21_shape_class_v1_field_dictionary.md")

    manifest = {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "decision_label": decision_label,
        "morphology_dir": str(morphology_path),
        "shape_class_v1_dir": str(v1_path),
        "level_a_dir": str(Path(level_a_dir) if level_a_dir else morphology_path.parent),
        "output_dir": str(out_dir),
        "git_commit": git_commit,
        "source_morphology_git_commit": source_manifest.get("git_commit"),
        "source_refinement_decision": refinement_manifest.get("qc", {}).get("decision_label"),
        "row_counts": {
            "rows": int(df.shape[0]),
            "frames": int(df["FrameIndex"].nunique()),
            "stages": int(df["SnStage"].nunique()),
        },
        "conservation": {
            "transition_count_sum": transition_count_sum,
            "transition_area_sum_px": transition_area_sum,
            "total_rows": int(df.shape[0]),
            "total_area_px": float(_numeric(df, "Area_px").sum(skipna=True)),
        },
        "outputs": OUTPUTS,
        "scope": {
            "shape_class_version": "v1",
            "projected_2d_only": True,
            "full_sidecar_derived": True,
            "tracking": False,
            "split_merge_lineage": False,
            "fractal": False,
            "roughness_3d": False,
            "true_fluid_fluid_interfacial_area": False,
        },
    }
    _write_review(out_dir / "g21_shape_class_v1_acceptance_review.md", decision_label, audit, manifest)
    _write_data_product_review(out_dir / "g21_shape_class_v1_data_product_acceptance_review.md", decision_label, audit, manifest)
    (out_dir / "shape_class_v1_formal_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Formalize G21 shape-class v1 data-product layer.")
    parser.add_argument("--morphology-dir", required=True)
    parser.add_argument("--shape-class-v1-dir", required=True)
    parser.add_argument("--level-a-dir")
    parser.add_argument("--output-dir")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = build_shape_class_v1_formal_package(
        morphology_dir=args.morphology_dir,
        shape_class_v1_dir=args.shape_class_v1_dir,
        level_a_dir=args.level_a_dir,
        output_dir=args.output_dir,
    )
    print(
        json.dumps(
            {
                "output_dir": manifest["output_dir"],
                "decision_label": manifest["decision_label"],
                "row_counts": manifest["row_counts"],
                "conservation": manifest["conservation"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
