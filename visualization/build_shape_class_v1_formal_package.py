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
    "shape_class_v1_schema.md",
    "g21_shape_class_v1_acceptance_review.md",
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


def _git_commit() -> str:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True)
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
    rows = []

    def add(gate: str, status: str, value: object, expected: str) -> None:
        rows.append({"Gate": gate, "Status": status, "Value": value, "Expected": expected})

    add("all_rows_have_shape_class_v1", "PASS" if classes.ne("").all() and classes.notna().all() else "FAIL", int(classes.ne("").sum()), "all rows")
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

    git_commit = _git_commit()
    source_manifest = _read_json(morphology_path / "blob_morphology_manifest.json")
    refinement_manifest = _read_json(v1_path / "shape_class_v1_manifest.json")
    df = _load_v1_table(v1_path)
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
    _write_schema(out_dir / "shape_class_v1_schema.md")

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
