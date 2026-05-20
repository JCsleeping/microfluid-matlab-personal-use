"""Build G21 shape-class v1 refinement from the morphology data product."""

from __future__ import annotations

import argparse
import json
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
    "shape_class_v1_qc.md",
    "shape_class_v1_manifest.json",
]

STAGE_ORDER = ["early_depletion", "active_dissolution", "late_depletion", "endpoint"]


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


def _threshold(thresholds: dict, metric: str, quantile: str, default: float) -> float:
    try:
        value = thresholds["thresholds"][metric][quantile]
    except KeyError:
        return default
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return float(number) if pd.notna(number) and np.isfinite(number) else default


def _load_thresholds(morphology_dir: Path) -> dict:
    path = morphology_dir / "blob_morphology_thresholds.json"
    if not path.exists():
        return {"thresholds": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_shape_table(morphology_dir: Path) -> pd.DataFrame:
    path = morphology_dir / "blob_morphology_by_blob.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing morphology table: {path}")
    usecols = {
        "FrameIndex",
        "RealTime_s",
        "BlobID",
        "BlobID_sidecar",
        "ShapeClass",
        "ShapeClassReason",
        "Area_px",
        "AreaTier",
        "MajorAxisLength_px",
        "MinorAxisLength_px",
        "Eccentricity",
        "Extent",
        "BoundaryMetricValid",
        "AxisAspectRatio",
        "AspectRatio01",
        "Solidity2D",
        "ProjectedSphericity2D",
        "Circularity2D_boundary",
        "ProjectedRoughness_boundary",
        "PtotalOverPouter",
        "ProjectedRegularity2D",
        "P_outer_boundary",
        "Pc_outer_boundary",
        "P_total_boundary",
        "A_blob_Atotal",
        "CircularityGreaterThan1p05",
        "RoughnessLessThanOne",
        "TouchesImageBorder",
        "MaskPath",
        "LabelPath",
    }
    df = pd.read_csv(path, usecols=lambda column: column in usecols)
    if "BlobID" not in df.columns and "BlobID_sidecar" in df.columns:
        df["BlobID"] = df["BlobID_sidecar"]
    if "ShapeClass" not in df.columns:
        raise ValueError("Input morphology table must contain ShapeClass")
    return df


def assign_sn_stage_from_frame(df: pd.DataFrame) -> pd.Series:
    """Fallback stage labels when the Level A table is not supplied."""
    frame = _numeric(df, "FrameIndex")
    if frame.dropna().empty:
        return pd.Series("unknown", index=df.index, dtype="object")
    max_frame = int(frame.max())
    endpoint_start = int(np.ceil(max_frame * 0.95))
    stage = pd.Series("active_dissolution", index=df.index, dtype="object")
    stage.loc[frame < endpoint_start * 0.20] = "early_depletion"
    stage.loc[frame >= endpoint_start * 0.65] = "late_depletion"
    stage.loc[frame >= endpoint_start] = "endpoint"
    return stage


def add_level_a_stages(df: pd.DataFrame, level_a_dir: Path | None) -> pd.DataFrame:
    out = df.copy()
    if level_a_dir is None:
        out["SnStage"] = assign_sn_stage_from_frame(out)
        return out
    level_a_path = level_a_dir / "dissolution_rates.csv"
    if not level_a_path.exists():
        out["SnStage"] = assign_sn_stage_from_frame(out)
        return out
    level_a = pd.read_csv(level_a_path, usecols=lambda column: column in {"FrameIndex", "SnMonotone"})
    level_a["FrameIndex"] = _numeric(level_a, "FrameIndex").astype("Int64")
    sn = _numeric(level_a, "SnMonotone")
    frame = level_a["FrameIndex"].astype(int)
    endpoint_start = int(np.ceil(int(frame.max()) * 0.95))
    stage = pd.Series("active_dissolution", index=level_a.index, dtype="object")
    stage.loc[sn >= 0.20] = "early_depletion"
    stage.loc[(sn >= 0.005) & (sn < 0.05)] = "late_depletion"
    stage.loc[(sn < 0.005) | (frame >= endpoint_start)] = "endpoint"
    level_a["SnStage"] = stage
    out = out.merge(level_a[["FrameIndex", "SnStage"]], on="FrameIndex", how="left", validate="many_to_one")
    out["SnStage"] = out["SnStage"].fillna("unknown")
    return out


def assign_shape_class_v1(df: pd.DataFrame, thresholds: dict) -> pd.DataFrame:
    out = df.copy()
    area = _numeric(out, "Area_px")
    boundary_valid = _bool_series(out, "BoundaryMetricValid")
    roughness_invalid = _bool_series(out, "RoughnessLessThanOne")
    circularity_artifact = _bool_series(out, "CircularityGreaterThan1p05")
    touches_border = _bool_series(out, "TouchesImageBorder")

    sphericity = _numeric(out, "ProjectedSphericity2D")
    aspect01 = _numeric(out, "AspectRatio01")
    axis = _numeric(out, "AxisAspectRatio")
    solidity = _numeric(out, "Solidity2D")
    roughness = _numeric(out, "ProjectedRoughness_boundary")
    ptotal_ratio = _numeric(out, "PtotalOverPouter")
    v0 = out["ShapeClass"].astype(str)

    sph_q50 = _threshold(thresholds, "ProjectedSphericity2D", "q50", 0.75)
    sph_q75 = _threshold(thresholds, "ProjectedSphericity2D", "q75", 0.85)
    aspect_q50 = _threshold(thresholds, "AspectRatio01", "q50", 0.55)
    aspect_q75 = _threshold(thresholds, "AspectRatio01", "q75", 0.68)
    axis_q50 = _threshold(thresholds, "AxisAspectRatio", "q50", 1.8)
    axis_q75 = _threshold(thresholds, "AxisAspectRatio", "q75", 2.34)
    axis_q90 = _threshold(thresholds, "AxisAspectRatio", "q90", 2.99)
    solidity_q25 = _threshold(thresholds, "Solidity2D", "q25", 0.74)
    solidity_q50 = _threshold(thresholds, "Solidity2D", "q50", 0.86)
    solidity_q75 = _threshold(thresholds, "Solidity2D", "q75", 0.92)
    rough_q75 = _threshold(thresholds, "ProjectedRoughness_boundary", "q75", 1.22)
    rough_q90 = _threshold(thresholds, "ProjectedRoughness_boundary", "q90", 1.37)
    ptotal_q75 = _threshold(thresholds, "PtotalOverPouter", "q75", 1.0)

    cls = pd.Series("ambiguous_valid", index=out.index, dtype="object")
    reason = pd.Series("valid_geometry_fallback_v1", index=out.index, dtype="object")
    tier = pd.Series("geometry_interpretable", index=out.index, dtype="object")

    low_area_lt100 = area < 100
    low_area_100_249 = area.ge(100) & area.lt(250)
    valid_area = area.notna()
    eligible = valid_area & area.ge(250) & boundary_valid
    boundary_invalid = valid_area & area.ge(250) & ~boundary_valid

    cls.loc[low_area_lt100] = "count_only_lt100"
    reason.loc[low_area_lt100] = "area_lt_100_count_only"
    tier.loc[low_area_lt100] = "count_only"

    low_compact = low_area_100_249 & (axis <= axis_q50) & (solidity >= solidity_q75) & (sphericity >= sph_q50)
    low_elongated = low_area_100_249 & ~low_compact & (axis >= axis_q75)
    low_caution = low_area_100_249 & ~low_compact & ~low_elongated
    cls.loc[low_compact] = "low_area_compact_candidate_100_249"
    reason.loc[low_compact] = "area_100_249_compact_projected_shape_caution"
    cls.loc[low_elongated] = "low_area_elongated_candidate_100_249"
    reason.loc[low_elongated] = "area_100_249_elongated_projected_shape_caution"
    cls.loc[low_caution] = "low_area_projected_shape_caution_100_249"
    reason.loc[low_caution] = "area_100_249_projected_shape_caution"
    tier.loc[low_area_100_249] = "low_area_shape_caution"

    cls.loc[boundary_invalid] = "boundary_invalid"
    reason.loc[boundary_invalid] = "area_ge_250_boundary_metric_invalid"
    tier.loc[boundary_invalid] = "no_boundary_interpretation"

    def assign_first(mask: pd.Series, name: str, why: str) -> None:
        target = mask & eligible & cls.eq("ambiguous_valid")
        cls.loc[target] = name
        reason.loc[target] = why

    assign_first(v0.eq("branched_complex"), "branched_complex", "preserved_v0_branched_complex")
    assign_first(v0.eq("compact_round"), "compact_regular", "renamed_v0_compact_round")
    assign_first(axis >= axis_q90, "elongated", "axis_aspect_ratio_ge_q90")
    assign_first(v0.eq("concave_lobed"), "concave_lobed", "preserved_v0_concave_lobed")
    assign_first(v0.eq("compact_irregular"), "compact_irregular", "preserved_v0_compact_irregular")

    near_compact = (
        (sphericity >= sph_q75)
        & (aspect01 >= aspect_q50)
        & (solidity >= solidity_q75)
        & ~circularity_artifact
        & ~roughness_invalid
    )
    moderate_elongated = axis.ge(axis_q75) & axis.lt(axis_q90)
    moderate_concave = solidity.ge(solidity_q25) & solidity.lt(solidity_q50)
    assign_first(near_compact, "near_compact_regular", "intermediate_compact_regular_v1")
    assign_first(moderate_elongated, "moderately_elongated", "axis_aspect_ratio_q75_to_q90")
    assign_first(moderate_concave, "moderately_concave", "solidity_q25_to_q50_projected_low_solidity")

    high_boundary_complex = eligible & roughness.ge(rough_q90)
    moderate_boundary_complex = eligible & roughness.ge(rough_q75) & roughness.lt(rough_q90)
    internal_boundary = eligible & ptotal_ratio.gt(1.0)

    out["ShapeClassV0"] = v0
    out["ShapeClassV1"] = cls
    out["ShapeClassV1Reason"] = reason
    out["ShapeClassVersion"] = "v1"
    out["ShapeV1InterpretationTier"] = tier
    out["MetricSource"] = "full_duration_sidecar"
    out["BoundaryMetricSource"] = "corrected_sidecar_boundary"
    out["CorrectedBoundaryAvailable"] = boundary_valid & area.ge(250)
    out["DatasetSubset"] = "full_duration_sidecar"
    out["FullSidecarDerived"] = True
    out["LowAreaProjectedShapeCaution"] = low_area_100_249
    out["ModerateBoundaryComplexityFlag"] = moderate_boundary_complex
    out["HighBoundaryComplexityFlag"] = high_boundary_complex
    out["InternalBoundarySignalFlag"] = internal_boundary
    out["TouchesImageBorderFlag"] = touches_border
    out["CircularityArtifactFlag"] = circularity_artifact
    out["RoughnessInvalidFlag"] = roughness_invalid
    return out


def _summary_by(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    total_n = len(df)
    total_area = _numeric(df, "Area_px").sum(skipna=True)
    rows = []
    for key, sub in df.groupby(group_cols, dropna=False, sort=True):
        if not isinstance(key, tuple):
            key = (key,)
        area_sum = _numeric(sub, "Area_px").sum(skipna=True)
        row = {column: value for column, value in zip(group_cols, key)}
        row.update(
            {
                "NRows": int(len(sub)),
                "CountFraction": float(len(sub) / total_n) if total_n else np.nan,
                "AreaSum_px": float(area_sum),
                "AreaFraction": float(area_sum / total_area) if total_area else np.nan,
                "MedianArea_px": float(_numeric(sub, "Area_px").median()),
                "MedianAxisAspectRatio": float(_numeric(sub, "AxisAspectRatio").median()),
                "MedianSolidity2D": float(_numeric(sub, "Solidity2D").median()),
                "MedianProjectedSphericity2D": float(_numeric(sub, "ProjectedSphericity2D").median()),
                "MedianProjectedRoughness_boundary": float(_numeric(sub, "ProjectedRoughness_boundary").median()),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def _transition_tables(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    count = pd.crosstab(df["ShapeClassV0"], df["ShapeClassV1"]).reset_index().rename(columns={"ShapeClassV0": "ShapeClassV0"})
    area = (
        df.pivot_table(
            index="ShapeClassV0",
            columns="ShapeClassV1",
            values="Area_px",
            aggfunc="sum",
            fill_value=0.0,
        )
        .reset_index()
        .rename_axis(None, axis=1)
    )
    return count, area


def _write_qc(path: Path, df: pd.DataFrame, class_summary: pd.DataFrame) -> dict[str, object]:
    total = len(df)
    shape_valid_mask = ~df["ShapeClassV1"].isin(["count_only_lt100", "boundary_invalid"]) & ~df["ShapeClassV1"].str.startswith("low_area")
    ambiguous = int(df["ShapeClassV1"].eq("ambiguous_valid").sum())
    interpretable = int(shape_valid_mask.sum())
    ambiguous_all = ambiguous / total if total else np.nan
    ambiguous_interpretable = ambiguous / interpretable if interpretable else np.nan
    low_area_promoted = int(((_numeric(df, "Area_px") < 250) & ~df["ShapeClassV1"].str.startswith(("count_only", "low_area"))).sum())
    roughness_valid_violations = int((_bool_series(df, "RoughnessLessThanOne") & df["ShapeClassV1"].isin(["compact_regular", "near_compact_regular"])).sum())
    circularity_regular_violations = int(
        (_bool_series(df, "CircularityGreaterThan1p05") & df["ShapeClassV1"].isin(["compact_regular", "near_compact_regular"])).sum()
    )
    hard_gate_failed = low_area_promoted > 0 or roughness_valid_violations > 0 or circularity_regular_violations > 0
    if hard_gate_failed:
        decision_label = "REVIEW_GATE_VIOLATION"
    elif ambiguous_interpretable <= 0.25:
        decision_label = "PASS"
    elif ambiguous_interpretable <= 0.26:
        decision_label = "PASS_WITH_NEAR_THRESHOLD_NOTE"
    else:
        decision_label = "REVIEW_AMBIGUOUS_REMAINS_HIGH"
    lines = [
        "# G21 Shape-Class V1 QC",
        "",
        "This package refines shape-class v0 without changing sidecar geometry extraction.",
        "",
        f"Decision: `{decision_label}`",
        "",
        "## Gate Summary",
        "",
        "- Area < 100 px remains count-only.",
        "- 100 <= Area < 250 px is low-area projected-shape caution.",
        "- Area >= 250 px with corrected boundary metrics is the reliable morphology tier.",
        "- `near_compact_round` is not used; the v1 label is `near_compact_regular`.",
        "",
        "## QC Metrics",
        "",
        f"- Total rows: {total}",
        f"- Ambiguous valid rows: {ambiguous}",
        f"- Ambiguous fraction of all rows: {ambiguous_all:.6g}",
        f"- Ambiguous fraction of interpretable rows: {ambiguous_interpretable:.6g}",
        f"- Area < 250 rows promoted to boundary classes: {low_area_promoted}",
        f"- RoughnessLessThanOne regular-class violations: {roughness_valid_violations}",
        f"- CircularityGreaterThan1p05 regular-class violations: {circularity_regular_violations}",
        "",
        "The target ambiguous fraction for interpretable rows is 25%. Values just above this target are kept as a near-threshold note rather than forcing looser class gates.",
        "",
        "## Scope",
        "",
        "ShapeClassV1 remains projected 2D morphology. It does not imply tracking, split/merge lineage, fractal dimension, 3D roughness, or true fluid-fluid interfacial area.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return {
        "decision_label": decision_label,
        "ambiguous_fraction_all": ambiguous_all,
        "ambiguous_fraction_interpretable": ambiguous_interpretable,
        "low_area_promoted_to_boundary_classes": low_area_promoted,
        "roughness_regular_violations": roughness_valid_violations,
        "circularity_regular_violations": circularity_regular_violations,
        "class_count": int(class_summary.shape[0]),
    }


def build_shape_class_v1_refinement(
    morphology_dir: str | Path,
    level_a_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, object]:
    morphology_path = Path(morphology_dir)
    if output_dir is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = morphology_path / f"g21_shape_class_v1_refinement_{stamp}"
    else:
        out_dir = Path(output_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise FileExistsError(f"Output directory is not empty: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    thresholds = _load_thresholds(morphology_path)
    df = _load_shape_table(morphology_path)
    df = add_level_a_stages(df, Path(level_a_dir) if level_a_dir else morphology_path.parent)
    v1 = assign_shape_class_v1(df, thresholds)

    out_cols = [
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
        "CorrectedBoundaryAvailable",
        "DatasetSubset",
        "FullSidecarDerived",
        "Area_px",
        "AreaTier",
        "MajorAxisLength_px",
        "MinorAxisLength_px",
        "Eccentricity",
        "Extent",
        "AxisAspectRatio",
        "AspectRatio01",
        "Solidity2D",
        "ProjectedSphericity2D",
        "Circularity2D_boundary",
        "ProjectedRoughness_boundary",
        "PtotalOverPouter",
        "ProjectedRegularity2D",
        "P_outer_boundary",
        "Pc_outer_boundary",
        "P_total_boundary",
        "A_blob_Atotal",
        "LowAreaProjectedShapeCaution",
        "ModerateBoundaryComplexityFlag",
        "HighBoundaryComplexityFlag",
        "InternalBoundarySignalFlag",
        "TouchesImageBorderFlag",
        "CircularityArtifactFlag",
        "RoughnessInvalidFlag",
    ]
    present_cols = [column for column in out_cols if column in v1.columns]
    v1[present_cols].to_csv(out_dir / "blob_shape_class_v1_by_blob.csv", index=False)

    class_summary = _summary_by(v1, ["ShapeClassV1"])
    stage_summary = _summary_by(v1, ["SnStage", "ShapeClassV1"])
    transition_count, transition_area = _transition_tables(v1)
    class_summary.to_csv(out_dir / "shape_class_v1_summary_by_class.csv", index=False)
    stage_summary.to_csv(out_dir / "shape_class_v1_summary_by_stage.csv", index=False)
    transition_count.to_csv(out_dir / "shape_class_v0_to_v1_transition_count.csv", index=False)
    transition_area.to_csv(out_dir / "shape_class_v0_to_v1_transition_area.csv", index=False)
    qc = _write_qc(out_dir / "shape_class_v1_qc.md", v1, class_summary)

    manifest = {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "morphology_dir": str(morphology_path),
        "level_a_dir": str(Path(level_a_dir) if level_a_dir else morphology_path.parent),
        "output_dir": str(out_dir),
        "row_counts": {
            "rows": int(v1.shape[0]),
            "frames": int(v1["FrameIndex"].nunique()),
        },
        "qc": qc,
        "outputs": OUTPUTS,
        "scope": {
            "shape_class_version": "v1",
            "projected_2d_only": True,
            "full_sidecar_derived": True,
            "tracking": False,
            "fractal": False,
            "roughness_3d": False,
            "true_fluid_fluid_interfacial_area": False,
        },
    }
    (out_dir / "shape_class_v1_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build G21 shape-class v1 refinement package.")
    parser.add_argument("--morphology-dir", required=True)
    parser.add_argument("--level-a-dir")
    parser.add_argument("--output-dir")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_shape_class_v1_refinement(args.morphology_dir, args.level_a_dir, args.output_dir)
    print(json.dumps({"output_dir": result["output_dir"], "row_counts": result["row_counts"], "qc": result["qc"]}, indent=2))


if __name__ == "__main__":
    main()
