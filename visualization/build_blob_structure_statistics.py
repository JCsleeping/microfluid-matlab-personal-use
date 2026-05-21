"""Build G21 blob structure statistics from the morphology data product.

This script consumes the morphology-ready by-blob table and Level A
SnMonotone timeline, then writes compact statistics and figures for projected
2D blob structure. It does not perform sidecar extraction, tracking, fractal
analysis, or 3D roughness analysis.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


METRIC_COLUMNS = [
    "Area_px",
    "ProjectedSphericity2D",
    "AspectRatio01",
    "AxisAspectRatio",
    "Solidity2D",
    "Circularity2D_boundary",
    "ProjectedRoughness_boundary",
    "PtotalOverPouter",
    "ProjectedRegularity2D",
]

VALID_SHAPE_CLASSES = {
    "compact_round",
    "elongated",
    "concave_lobed",
    "branched_complex",
    "compact_irregular",
    "ambiguous_valid",
    "medium_caution",
}

VALID_SHAPE_CLASSES_BY_VERSION = {
    "v0": VALID_SHAPE_CLASSES,
    "v1": {
        "compact_regular",
        "near_compact_regular",
        "moderately_elongated",
        "elongated",
        "moderately_concave",
        "concave_lobed",
        "branched_complex",
        "compact_irregular",
        "ambiguous_valid",
    },
}

STAGE_ORDER = ["early_depletion", "active_dissolution", "late_depletion", "endpoint"]


@dataclass(frozen=True)
class Inputs:
    morphology_dir: Path
    level_a_dir: Path
    output_dir: Path
    shape_class_version: str = "v0"
    shape_class_v1_dir: Path | None = None


@dataclass(frozen=True)
class ShapeClassSource:
    version: str
    source_dir: Path
    source_file: Path
    manifest_file: Path | None
    active_shape_class_column: str = "ShapeClassActive"
    active_reason_column: str = "ShapeClassReasonActive"


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


def _q25(series: pd.Series) -> float:
    return float(numeric(series).quantile(0.25))


def _q75(series: pd.Series) -> float:
    return float(numeric(series).quantile(0.75))


def _median(series: pd.Series) -> float:
    return float(numeric(series).median())


def _weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    v = numeric(values)
    w = numeric(weights)
    ok = v.notna() & w.notna() & (w > 0)
    if not ok.any():
        return float("nan")
    return float(np.average(v[ok], weights=w[ok]))


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def assign_sn_stage(level_a: pd.DataFrame) -> pd.DataFrame:
    """Assign fixed SnMonotone stages with endpoint taking precedence."""
    out = level_a.copy()
    if "FrameIndex" not in out.columns or "SnMonotone" not in out.columns:
        raise ValueError("Level A table must contain FrameIndex and SnMonotone")
    out["FrameIndex"] = numeric(out["FrameIndex"]).astype("Int64")
    out["SnMonotone"] = numeric(out["SnMonotone"])
    max_frame = int(out["FrameIndex"].max())
    endpoint_start = int(np.ceil(max_frame * 0.95))
    sn = out["SnMonotone"]
    frame = out["FrameIndex"].astype(int)
    stage = pd.Series("active_dissolution", index=out.index, dtype="object")
    stage.loc[sn >= 0.20] = "early_depletion"
    stage.loc[(sn >= 0.005) & (sn < 0.05)] = "late_depletion"
    stage.loc[(sn < 0.005) | (frame >= endpoint_start)] = "endpoint"
    out["SnStage"] = stage
    out["StageOrder"] = out["SnStage"].map({name: idx for idx, name in enumerate(STAGE_ORDER)})
    return out[["FrameIndex", "SnMonotone", "DissolutionRate_Sn_per_min", "SnStage", "StageOrder"]]


def _read_v0_shape_table(inputs: Inputs) -> tuple[pd.DataFrame, ShapeClassSource]:
    shape_path = inputs.morphology_dir / "blob_shape_class_by_blob.csv"
    if not shape_path.exists():
        raise FileNotFoundError(f"Missing morphology shape table: {shape_path}")
    usecols = [
        "FrameIndex",
        "RealTime_s",
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
    ]
    shape = pd.read_csv(shape_path, usecols=lambda c: c in usecols)
    shape["ShapeClassActive"] = shape["ShapeClass"].astype(str)
    shape["ShapeClassReasonActive"] = shape.get("ShapeClassReason", pd.Series("", index=shape.index)).astype(str)
    shape["ShapeClassVersion"] = "v0"
    shape["InterpretationTier"] = np.where(
        shape["ShapeClassActive"].isin(["small_unclassified", "boundary_invalid"]),
        "not_boundary_interpretable",
        "geometry_interpretable",
    )
    shape["ShapeClassSourceDir"] = str(inputs.morphology_dir)
    shape["ShapeClassSourceFile"] = str(shape_path)
    shape_source = ShapeClassSource(
        version="v0",
        source_dir=inputs.morphology_dir,
        source_file=shape_path,
        manifest_file=inputs.morphology_dir / "blob_morphology_manifest.json",
    )
    return shape, shape_source


def _read_v1_shape_table(inputs: Inputs) -> tuple[pd.DataFrame, ShapeClassSource]:
    if inputs.shape_class_v1_dir is None:
        raise ValueError("--shape-class-v1-dir is required when --shape-class-version v1")
    v1_dir = inputs.shape_class_v1_dir
    manifest_path = v1_dir / "shape_class_v1_formal_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing v1 formal manifest: {manifest_path}")
    manifest = _read_json(manifest_path)
    decision_label = str(manifest.get("decision_label", ""))
    if decision_label.startswith("BLOCKED"):
        raise ValueError(f"v1 formal package is blocked: {decision_label}")
    shape_path = v1_dir / "blob_shape_class_v1_by_blob.csv"
    if not shape_path.exists():
        raise FileNotFoundError(f"Missing v1 formal shape table: {shape_path}")
    usecols = [
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
        "ShapeClassSource",
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
    ]
    shape = pd.read_csv(shape_path, usecols=lambda c: c in usecols)
    required = {"ShapeClassV1", "ShapeClassV1Reason", "ShapeClassVersion", "ShapeV1InterpretationTier"}
    missing = required - set(shape.columns)
    if missing:
        raise ValueError(f"v1 formal shape table missing required column(s): {', '.join(sorted(missing))}")
    expected_rows = manifest.get("row_counts", {}).get("rows") if isinstance(manifest.get("row_counts"), dict) else None
    if expected_rows is not None and int(expected_rows) != int(len(shape)):
        raise ValueError(f"v1 formal row-count mismatch: manifest={expected_rows}, table={len(shape)}")
    shape["ShapeClassActive"] = shape["ShapeClassV1"].astype(str)
    shape["ShapeClassReasonActive"] = shape["ShapeClassV1Reason"].astype(str)
    shape["ShapeClassVersion"] = "v1"
    shape["InterpretationTier"] = shape["ShapeV1InterpretationTier"].astype(str)
    shape["ShapeValid"] = shape["InterpretationTier"].eq("geometry_interpretable")
    shape["ShapeInvalidReason"] = np.where(shape["ShapeValid"], "", shape["InterpretationTier"])
    shape["ReliabilityClass"] = shape["InterpretationTier"]
    shape["ShapeClass"] = shape["ShapeClassActive"]
    shape["ShapeClassReason"] = shape["ShapeClassReasonActive"]
    shape["ShapeClassSourceDir"] = str(v1_dir)
    shape["ShapeClassSourceFile"] = str(shape_path)
    shape_source = ShapeClassSource(
        version="v1",
        source_dir=v1_dir,
        source_file=shape_path,
        manifest_file=manifest_path,
    )
    return shape, shape_source


def read_inputs(inputs: Inputs) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame | None, ShapeClassSource]:
    version = inputs.shape_class_version.lower()
    if version not in {"v0", "v1"}:
        raise ValueError("shape_class_version must be 'v0' or 'v1'")
    shape, shape_source = _read_v1_shape_table(inputs) if version == "v1" else _read_v0_shape_table(inputs)

    level_a_path = inputs.level_a_dir / "dissolution_rates.csv"
    if not level_a_path.exists():
        raise FileNotFoundError(f"Missing Level A dissolution table: {level_a_path}")
    level_a = pd.read_csv(level_a_path, usecols=lambda c: c in {
        "FrameIndex",
        "SnMonotone",
        "DissolutionRate_Sn_per_min",
    })
    stages = assign_sn_stage(level_a)

    if version == "v1":
        atlas_path = inputs.shape_class_v1_dir / "representative_blob_atlas" / "representative_blob_atlas_manifest.csv"
    else:
        atlas_path = inputs.morphology_dir / "representative_blob_atlas" / "representative_blob_atlas_manifest.csv"
    atlas = pd.read_csv(atlas_path) if atlas_path.exists() else None
    return shape, stages, atlas, shape_source


def add_analysis_columns(shape: pd.DataFrame, stages: pd.DataFrame) -> pd.DataFrame:
    out = shape.merge(stages, on="FrameIndex", how="left", validate="many_to_one")
    if out["SnStage"].isna().any():
        missing = int(out["SnStage"].isna().sum())
        raise ValueError(f"{missing} morphology rows did not match a Level A FrameIndex")
    out["ShapeValid_bool"] = bool_series(out["ShapeValid"])
    out["BoundaryInterpretable"] = out["ShapeValid_bool"] & numeric(out["Area_px"]).ge(250)
    out["HighConfidenceGeometry"] = out["ShapeValid_bool"] & numeric(out["Area_px"]).ge(500)
    out["CountFractionWeight"] = 1.0
    for column in METRIC_COLUMNS:
        if column in out.columns:
            out[column] = numeric(out[column])
    return out


def summarize_by_group(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    total_n = len(df)
    total_area = float(numeric(df["Area_px"]).sum())
    grouped = df.groupby(group_cols, dropna=False, sort=False)
    for key, group in grouped:
        if not isinstance(key, tuple):
            key = (key,)
        record = {name: value for name, value in zip(group_cols, key)}
        area = numeric(group["Area_px"])
        shape_valid = group["ShapeValid_bool"]
        boundary = group["BoundaryInterpretable"]
        record.update(
            {
                "NBlobs": int(len(group)),
                "CountFraction": float(len(group) / total_n) if total_n else np.nan,
                "AreaSum_px": float(area.sum()),
                "AreaFraction": float(area.sum() / total_area) if total_area > 0 else np.nan,
                "ShapeValidFraction": float(shape_valid.mean()) if len(group) else np.nan,
                "BoundaryInterpretableFraction": float(boundary.mean()) if len(group) else np.nan,
                "HighConfidenceFraction": float(group["HighConfidenceGeometry"].mean()) if len(group) else np.nan,
                "MedianArea_px": _median(group["Area_px"]),
                "Q25Area_px": _q25(group["Area_px"]),
                "Q75Area_px": _q75(group["Area_px"]),
            }
        )
        for metric in [
            "ProjectedSphericity2D",
            "AspectRatio01",
            "AxisAspectRatio",
            "Solidity2D",
            "ProjectedRoughness_boundary",
            "PtotalOverPouter",
            "ProjectedRegularity2D",
        ]:
            if metric not in group.columns:
                record[f"Median_{metric}_valid"] = np.nan
                record[f"Q25_{metric}_valid"] = np.nan
                record[f"Q75_{metric}_valid"] = np.nan
                record[f"AreaWeighted_{metric}_valid"] = np.nan
                continue
            vals = group.loc[boundary, metric]
            record[f"Median_{metric}_valid"] = _median(vals) if not vals.empty else np.nan
            record[f"Q25_{metric}_valid"] = _q25(vals) if not vals.empty else np.nan
            record[f"Q75_{metric}_valid"] = _q75(vals) if not vals.empty else np.nan
            record[f"AreaWeighted_{metric}_valid"] = (
                _weighted_mean(group.loc[boundary, metric], group.loc[boundary, "Area_px"])
                if boundary.any()
                else np.nan
            )
        records.append(record)
    return pd.DataFrame(records)


def build_class_summary(df: pd.DataFrame, shape_class_version: str = "v0") -> pd.DataFrame:
    summary = summarize_by_group(df, ["ShapeClass"])
    valid_classes = VALID_SHAPE_CLASSES_BY_VERSION.get(shape_class_version, VALID_SHAPE_CLASSES)
    summary["InterpretationAllowed"] = summary["ShapeClass"].isin(valid_classes)
    if shape_class_version == "v1":
        summary.loc[
            summary["ShapeClass"].isin(
                [
                    "count_only_lt100",
                    "boundary_invalid",
                    "low_area_compact_candidate_100_249",
                    "low_area_elongated_candidate_100_249",
                    "low_area_projected_shape_caution_100_249",
                ]
            ),
            "InterpretationAllowed",
        ] = False
        note_map = {
            "count_only_lt100": "count_only_area_lt_100",
            "boundary_invalid": "excluded_boundary_metric_invalid",
            "low_area_compact_candidate_100_249": "low_area_projected_shape_caution",
            "low_area_elongated_candidate_100_249": "low_area_projected_shape_caution",
            "low_area_projected_shape_caution_100_249": "low_area_projected_shape_caution",
            "moderately_concave": "projected_low_solidity_proxy",
        }
    else:
        summary.loc[summary["ShapeClass"].isin(["small_unclassified", "boundary_invalid"]), "InterpretationAllowed"] = False
        note_map = {
            "small_unclassified": "count_only_area_lt_250",
            "boundary_invalid": "excluded_boundary_metric_invalid",
            "medium_caution": "geometry_caution_medium_area_tier",
        }
    summary["InterpretationNote"] = summary["ShapeClass"].map(note_map).fillna("geometry_valid_projected_2d")
    summary["ShapeClassVersion"] = shape_class_version
    return summary.sort_values(["InterpretationAllowed", "NBlobs"], ascending=[False, False])


def build_stage_summary(df: pd.DataFrame) -> pd.DataFrame:
    stage_class = summarize_by_group(df, ["SnStage", "ShapeClass"])
    stage_frames = df.groupby("SnStage")["FrameIndex"].nunique().rename("NFrames").reset_index()
    stage_totals = (
        stage_class.groupby("SnStage", as_index=False)
        .agg(StageBlobTotal=("NBlobs", "sum"), StageAreaTotal_px=("AreaSum_px", "sum"))
    )
    stage_class = stage_class.merge(stage_frames, on="SnStage", how="left")
    stage_class = stage_class.merge(stage_totals, on="SnStage", how="left")
    stage_class["StageCountFraction"] = stage_class["NBlobs"] / stage_class["StageBlobTotal"].replace(0, np.nan)
    stage_class["StageAreaFraction"] = stage_class["AreaSum_px"] / stage_class["StageAreaTotal_px"].replace(0, np.nan)
    if "ShapeClassVersion" in df.columns:
        stage_class["ShapeClassVersion"] = str(df["ShapeClassVersion"].dropna().iloc[0])
    stage_class["StageOrder"] = stage_class["SnStage"].map({name: idx for idx, name in enumerate(STAGE_ORDER)})
    return stage_class.sort_values(["StageOrder", "ShapeClass"]).drop(columns=["StageOrder"])


def build_transition_by_stage(stage_summary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for stage, group in stage_summary.groupby("SnStage", sort=False):
        row: dict[str, object] = {
            "SnStage": stage,
            "NFrames": int(group["NFrames"].max()) if "NFrames" in group else np.nan,
            "NBlobs": int(group["NBlobs"].sum()),
            "AreaSum_px": float(group["AreaSum_px"].sum()),
        }
        for _, item in group.iterrows():
            cls = str(item["ShapeClass"])
            row[f"count_frac_{cls}"] = float(item["StageCountFraction"])
            row[f"area_frac_{cls}"] = float(item["StageAreaFraction"])
        rows.append(row)
    transition = pd.DataFrame(rows)
    transition["StageOrder"] = transition["SnStage"].map({name: idx for idx, name in enumerate(STAGE_ORDER)})
    return transition.sort_values("StageOrder").drop(columns=["StageOrder"])


def write_metric_dictionary(path: Path) -> None:
    text = """# G21 Blob Structure Metric Dictionary

This dictionary maps the current pipeline metrics to projected 2D blob-structure descriptors. These are not 3D morphology, true fluid-fluid interfacial area, tracking, split/merge lineage, or boundary fractal dimension.

| Literature shorthand | Pipeline field | Formula / source | Use | Boundary |
|---|---|---|---|---|
| Long axis | `MajorAxisLength_px` | MATLAB `regionprops` major axis on the 2D mask component | projected elongation | 2D projection only |
| Short axis | `MinorAxisLength_px` | MATLAB `regionprops` minor axis on the 2D mask component | projected elongation | 2D projection only |
| AR, axis ratio | `AxisAspectRatio` | `MajorAxisLength_px / MinorAxisLength_px` | elongation magnitude | not a trajectory or deformation history |
| AR01, compact axis ratio | `AspectRatio01` | `MinorAxisLength_px / MajorAxisLength_px` | 0-1 compactness of fitted ellipse | not Wadell roundness |
| S proxy | `ProjectedSphericity2D` | `2*sqrt(pi*Area_px) / P_outer_boundary` | projected compactness relative to a circle | not 3D sphericity |
| CR / circularity proxy | `Circularity2D_boundary` | `4*pi*Area_px / P_outer_boundary^2` | 2D compactness QC / diagnostic | not Wadell roundness; tiny/small artifacts excluded |
| Solidity | `Solidity2D` | `Area_px / ConvexArea_px` | convexity / concavity proxy | 2D projection only |
| R proxy | `ProjectedRoughness_boundary` | `P_outer_boundary / Pc_outer_boundary` | 2D exterior-boundary complexity proxy | not true interfacial roughness |
| Ptotal/Pouter | `PtotalOverPouter` | `P_total_boundary / P_outer_boundary` | projected internal-boundary diagnostic | not full NAPL-water interface area |
| Regularity proxy | `ProjectedRegularity2D` | mean of `ProjectedSphericity2D`, `AspectRatio01`, and `Solidity2D` | compact summary for ranking | proxy only; not original Krumbein regularity |

`P_outer_boundary` is produced from exterior boundaries and is interpreted only as a 2D exterior-boundary proxy. `P_total_boundary` is a projected total-boundary diagnostic. Reliable boundary interpretation requires `ShapeValid`, `BoundaryMetricValid`, and area-tier filtering.
"""
    path.write_text(text, encoding="utf-8")


def write_atlas_review(path: Path, atlas: pd.DataFrame | None, class_summary: pd.DataFrame) -> None:
    if atlas is None:
        path.write_text("# Representative Atlas Review\n\nNo representative atlas manifest was found.\n", encoding="utf-8")
        return
    status_counts = atlas["Status"].value_counts().to_dict() if "Status" in atlas else {}
    class_counts = atlas["ShapeClass"].value_counts().to_dict() if "ShapeClass" in atlas else {}
    missing_classes = sorted(set(class_summary.loc[class_summary["InterpretationAllowed"], "ShapeClass"]) - set(class_counts))
    lines = [
        "# G21 Representative Blob Atlas Review",
        "",
        f"Atlas candidates reviewed: {len(atlas)}",
        f"Render status counts: `{status_counts}`",
        f"Atlas class counts: `{class_counts}`",
        f"Valid interpretable classes not represented in atlas: `{missing_classes}`",
        "",
        "Panels are representative projected 2D blob examples, not tracked blob histories.",
        "Tiny/small and boundary-invalid rows remain excluded from boundary mechanism interpretation.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_scope_summary(path: Path, manifest: dict[str, object]) -> None:
    shape_info = manifest.get("shape_class", {})
    lines = [
        "# G21 Blob Structure Statistics Manifest",
        "",
        f"Created UTC: `{manifest['created_at_utc']}`",
        f"Morphology product: `{manifest['morphology_product_dir']}`",
        f"Level A directory: `{manifest['level_a_dir']}`",
        f"Shape-class version: `{shape_info.get('version', 'v0')}`",
        f"Shape-class source file: `{shape_info.get('source_file', '')}`",
        "",
        "Scope: full-duration projected 2D blob-structure statistics from the accepted morphology data product.",
        "",
        "Allowed: shape-class counts, area fractions, reliable-tier projected compactness, elongation, solidity, and exterior-boundary complexity proxies.",
        "",
        "Excluded: tracking, split/merge lineage, boundary fractal dimension, 3D roughness, true Wadell roundness, and true fluid-fluid interfacial area.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _safe_mkdir(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise FileExistsError(f"Output directory exists and is not empty: {path}")
    path.mkdir(parents=True, exist_ok=True)


def write_figures(output_dir: Path, class_summary: pd.DataFrame, stage_summary: pd.DataFrame, df: pd.DataFrame) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig_dir = output_dir / "figures_blob_structure"
    fig_dir.mkdir(exist_ok=True)
    written: list[str] = []

    class_plot = class_summary.sort_values("AreaFraction", ascending=False)
    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(class_plot))
    ax.bar(x - 0.18, class_plot["CountFraction"], width=0.36, label="count fraction")
    ax.bar(x + 0.18, class_plot["AreaFraction"], width=0.36, label="area fraction")
    ax.set_xticks(x)
    ax.set_xticklabels(class_plot["ShapeClass"], rotation=35, ha="right")
    ax.set_ylabel("Fraction")
    ax.set_title("G21 blob shape-class fractions")
    ax.legend()
    fig.tight_layout()
    path = fig_dir / "shape_class_count_area_fractions.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    written.append(str(path))

    pivot = stage_summary.pivot_table(index="SnStage", columns="ShapeClass", values="StageAreaFraction", aggfunc="sum").fillna(0)
    pivot = pivot.reindex([s for s in STAGE_ORDER if s in pivot.index])
    fig, ax = plt.subplots(figsize=(10, 5))
    bottom = np.zeros(len(pivot))
    for cls in pivot.columns:
        values = pivot[cls].to_numpy()
        ax.bar(pivot.index, values, bottom=bottom, label=cls)
        bottom += values
    ax.set_ylabel("Area fraction")
    ax.set_title("G21 projected shape-class area fractions by Sn stage")
    ax.tick_params(axis="x", rotation=20)
    ax.legend(fontsize=7, ncols=2)
    fig.tight_layout()
    path = fig_dir / "shape_class_area_fraction_by_sn_stage.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    written.append(str(path))

    sample_cols = ["ShapeClass", "ProjectedSphericity2D", "Solidity2D", "AxisAspectRatio", "Area_px"]
    if not set(sample_cols).issubset(df.columns):
        return written
    sample = df.loc[df["ShapeValid_bool"], sample_cols].dropna()
    if len(sample) > 50000:
        sample = sample.sample(n=50000, random_state=21)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), sharex=False)
    for ax, metric in zip(axes, ["ProjectedSphericity2D", "Solidity2D", "AxisAspectRatio"]):
        data = [sample.loc[sample["ShapeClass"] == cls, metric].dropna().to_numpy() for cls in sorted(sample["ShapeClass"].unique())]
        labels = sorted(sample["ShapeClass"].unique())
        ax.boxplot(data, tick_labels=labels, showfliers=False)
        ax.set_title(metric)
        ax.tick_params(axis="x", rotation=45, labelsize=7)
    fig.suptitle("Valid-tier projected structure metrics by shape class")
    fig.tight_layout()
    path = fig_dir / "valid_metric_distributions_by_shape_class.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    written.append(str(path))

    return written


def build_blob_structure_statistics(inputs: Inputs) -> dict[str, object]:
    _safe_mkdir(inputs.output_dir)
    shape, stages, atlas, shape_source = read_inputs(inputs)
    df = add_analysis_columns(shape, stages)

    class_summary = build_class_summary(df, shape_source.version)
    stage_summary = build_stage_summary(df)
    transition = build_transition_by_stage(stage_summary)

    class_summary.to_csv(inputs.output_dir / "blob_structure_class_summary.csv", index=False)
    stage_summary.to_csv(inputs.output_dir / "blob_structure_by_stage.csv", index=False)
    transition.to_csv(inputs.output_dir / "blob_structure_transition_by_sn_stage.csv", index=False)
    write_metric_dictionary(inputs.output_dir / "blob_structure_metric_dictionary.md")
    write_atlas_review(inputs.output_dir / "blob_structure_representative_atlas_review.md", atlas, class_summary)
    figures = write_figures(inputs.output_dir, class_summary, stage_summary, df)

    manifest = {
        "schema_version": "1.0",
        "created_at_utc": _utc_now(),
        "morphology_product_dir": str(inputs.morphology_dir),
        "level_a_dir": str(inputs.level_a_dir),
        "output_dir": str(inputs.output_dir),
        "shape_class": {
            "version": shape_source.version,
            "source_dir": str(shape_source.source_dir),
            "source_file": str(shape_source.source_file),
            "manifest_file": str(shape_source.manifest_file) if shape_source.manifest_file is not None else "",
            "active_shape_class_column": shape_source.active_shape_class_column,
            "active_reason_column": shape_source.active_reason_column,
            "source_manifest": _read_json(shape_source.manifest_file) if shape_source.manifest_file is not None else {},
        },
        "row_counts": {
            "blob_rows": int(len(df)),
            "frames": int(df["FrameIndex"].nunique()),
            "shape_valid_rows": int(df["ShapeValid_bool"].sum()),
            "boundary_interpretable_rows": int(df["BoundaryInterpretable"].sum()),
        },
        "stage_counts": df.groupby("SnStage")["FrameIndex"].nunique().astype(int).to_dict(),
        "shape_class_counts": df["ShapeClass"].value_counts().astype(int).to_dict(),
        "scope": {
            "full_duration_projected_2d_statistics": True,
            "shape_class_version": shape_source.version,
            "tracking": False,
            "fractal_dimension": False,
            "roughness_3d": False,
            "true_fluid_fluid_interfacial_area": False,
            "true_wadell_roundness": False,
        },
        "outputs": {
            "metric_dictionary": "blob_structure_metric_dictionary.md",
            "class_summary": "blob_structure_class_summary.csv",
            "by_stage": "blob_structure_by_stage.csv",
            "transition_by_sn_stage": "blob_structure_transition_by_sn_stage.csv",
            "atlas_review": "blob_structure_representative_atlas_review.md",
            "figures": figures,
        },
    }
    write_scope_summary(inputs.output_dir / "blob_structure_statistics_manifest.md", manifest)
    (inputs.output_dir / "blob_structure_statistics_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build projected 2D blob structure statistics from a morphology product.")
    parser.add_argument("--morphology-dir", required=True, type=Path)
    parser.add_argument("--level-a-dir", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--shape-class-version", choices=["v0", "v1"], default="v0")
    parser.add_argument("--shape-class-v1-dir", type=Path)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output_dir
    if output_dir is None:
        suffix = "_v1" if args.shape_class_version == "v1" else ""
        output_dir = args.morphology_dir / f"g21_blob_structure_statistics{suffix}_{_timestamp()}"
    manifest = build_blob_structure_statistics(
        Inputs(
            morphology_dir=args.morphology_dir,
            level_a_dir=args.level_a_dir,
            output_dir=output_dir,
            shape_class_version=args.shape_class_version,
            shape_class_v1_dir=args.shape_class_v1_dir,
        )
    )
    print(json.dumps({"output_dir": manifest["output_dir"], "row_counts": manifest["row_counts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
