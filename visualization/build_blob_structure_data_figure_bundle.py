"""Build a neutral blob-structure data and figure bundle.

The bundle organizes existing blob morphology outputs into tables, figures,
field notes, formula notes, and provenance. It does not perform sidecar
extraction, tracking, fractal analysis, 3D roughness analysis, or scientific
interpretation.
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


REQUIRED_TOP_LEVEL = [
    "README_data_figure_bundle.md",
    "data_inventory.csv",
    "figure_inventory.csv",
    "field_dictionary.csv",
    "formula_notes.md",
    "qc_and_scope_notes.md",
    "bundle_manifest.json",
]

REQUIRED_TABLES = [
    "shape_class_v1_count_area_summary.csv",
    "shape_class_v1_by_stage_summary.csv",
    "area_tier_summary.csv",
    "geometry_interpretable_fraction_by_stage.csv",
    "frame_level_blob_structure_summary.csv",
    "representative_blob_table.csv",
]

REQUIRED_FIGURE_STEMS = [
    "Fig_ShapeClassV1_CountAreaFractions",
    "Fig_ShapeClassV1_ByStage",
    "Fig_AreaTier_Distribution",
    "Fig_GeometryInterpretable_Fraction",
    "Fig_ShapeParameter_Distributions",
    "Fig_Sphericity_Roundness_Proxy_Map",
    "Fig_RepresentativeBlobAtlas",
]

STAGE_ORDER = ["early_depletion", "active_dissolution", "late_depletion", "endpoint"]

CLASS_ORDER = [
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
    "boundary_invalid",
]

CLASS_COLORS = {
    "compact_regular": "#009E73",
    "near_compact_regular": "#56B4E9",
    "moderately_elongated": "#CC79A7",
    "elongated": "#882255",
    "moderately_concave": "#E69F00",
    "branched_complex": "#D55E00",
    "ambiguous_valid": "#0072B2",
    "low_area_compact_candidate_100_249": "#8DD3C7",
    "low_area_elongated_candidate_100_249": "#BEBADA",
    "low_area_projected_shape_caution_100_249": "#FDB462",
    "count_only_lt100": "#B3B3B3",
    "boundary_invalid": "#999999",
}

ACCEPTED_PIPELINE_DECISIONS = {
    "ACCEPT_BLOB_PIPELINE",
    "ACCEPT_BLOB_PIPELINE_WITH_DOCUMENTED_WARNINGS",
}

ACCEPTED_SHAPE_CLASS_DECISIONS = {
    "ACCEPT_SHAPE_CLASS_V1_FORMAL_WITH_SCOPE_LIMITS",
    "ACCEPT_SHAPE_CLASS_V1_FORMAL_WITH_NEAR_THRESHOLD_NOTE",
}


@dataclass(frozen=True)
class Inputs:
    postprocess_dir: Path
    morphology_dir: Path
    shape_class_v1_dir: Path
    structure_statistics_dir: Path
    acceptance_dir: Path
    output_dir: Path | None = None
    repo_root: Path | None = None
    overwrite: bool = False


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_required_json(path: Path, label: str) -> dict[str, object]:
    if not path.exists():
        raise ValueError(f"Missing required {label}: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _require_decision(decision: str, accepted: set[str], label: str) -> None:
    if decision not in accepted:
        raise ValueError(
            f"{label} does not have an accepted decision_label: "
            f"{decision if decision else 'missing'}"
        )


def _require_manifest_count(
    manifest: dict[str, object],
    manifest_label: str,
    key: str,
    expected: int,
) -> None:
    row_counts = manifest.get("row_counts", {})
    if not isinstance(row_counts, dict) or key not in row_counts:
        raise ValueError(f"{manifest_label} is missing row_counts.{key}")
    observed = int(row_counts[key])
    if observed != int(expected):
        raise ValueError(
            f"{manifest_label} row-count mismatch for {key}: "
            f"manifest={observed}; table={int(expected)}"
        )


def _write_json(path: Path, payload: dict[str, object]) -> None:
    def clean(value):
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {str(k): clean(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [clean(v) for v in value]
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating,)):
            return float(value) if np.isfinite(value) else None
        if isinstance(value, (np.bool_,)):
            return bool(value)
        try:
            if pd.isna(value) and not isinstance(value, (str, bytes)):
                return None
        except TypeError:
            pass
        return value

    path.write_text(json.dumps(clean(payload), indent=2, ensure_ascii=False), encoding="utf-8")


def _read_csv(path: Path, label: str, **kwargs) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing {label}: {path}")
    return pd.read_csv(path, **kwargs)


def _numeric(df: pd.DataFrame, column: str, default=np.nan) -> pd.Series:
    if column not in df.columns:
        return pd.Series(default, index=df.index, dtype="float64")
    return pd.to_numeric(df[column], errors="coerce")


def _boolish(df: pd.DataFrame, column: str, default=False) -> pd.Series:
    if column not in df.columns:
        return pd.Series(default, index=df.index, dtype=bool)
    values = df[column]
    if values.dtype == bool:
        return values.fillna(default).astype(bool)
    return values.astype(str).str.lower().isin({"true", "1", "yes"})


def _safe_output_dir(path: Path, overwrite: bool) -> None:
    if path.exists() and any(path.iterdir()) and not overwrite:
        raise FileExistsError(f"Output directory exists and is not empty: {path}")
    path.mkdir(parents=True, exist_ok=True)
    (path / "tables").mkdir(exist_ok=True)
    (path / "figures").mkdir(exist_ok=True)


def _git_commit(repo_root: Path | None) -> str:
    if repo_root is None:
        return ""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _ordered(values: Iterable[str], preferred: list[str]) -> list[str]:
    values = [str(v) for v in values if str(v) != "nan"]
    seen = set(values)
    known = [v for v in preferred if v in seen]
    extras = sorted(seen.difference(known))
    return known + extras


def _pct_axis(ax) -> None:
    ax.yaxis.set_major_formatter(lambda value, _: f"{100 * value:.0f}%")


def _load_shape_table(shape_class_v1_dir: Path) -> pd.DataFrame:
    path = shape_class_v1_dir / "blob_shape_class_v1_by_blob.csv"
    usecols = [
        "FrameIndex",
        "RealTime_s",
        "BlobID",
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
        "BoundaryMetricValid",
        "ProjectedSphericity2D",
        "Circularity2D_boundary",
        "AspectRatio01",
        "AxisAspectRatio",
        "Solidity2D",
        "ProjectedRoughness_boundary",
        "PtotalOverPouter",
        "ProjectedRegularity2D",
        "SnStage",
    ]
    df = _read_csv(path, "ShapeClassV1 by-blob table", usecols=lambda c: c in usecols)
    if "BoundaryMetricValid" not in df.columns:
        df["BoundaryMetricValid"] = df.get("ShapeV1InterpretationTier", "").astype(str).eq("geometry_interpretable")
    else:
        df["BoundaryMetricValid"] = _boolish(df, "BoundaryMetricValid")
    if "SnStage" not in df.columns:
        df["SnStage"] = "unknown"
    df["Area_px"] = _numeric(df, "Area_px")
    return df


def _class_summary(shape: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        shape.groupby("ShapeClassV1", dropna=False)
        .agg(
            N=("Area_px", "size"),
            AreaSum_px=("Area_px", "sum"),
            MedianArea_px=("Area_px", "median"),
            GeometryInterpretableRows=("ShapeV1InterpretationTier", lambda s: int((s.astype(str) == "geometry_interpretable").sum())),
            BoundaryMetricValidRows=("BoundaryMetricValid", "sum"),
        )
        .reset_index()
    )
    total_n = float(grouped["N"].sum())
    total_area = float(grouped["AreaSum_px"].sum())
    grouped["CountFraction"] = grouped["N"] / total_n if total_n else np.nan
    grouped["AreaFraction"] = grouped["AreaSum_px"] / total_area if total_area else np.nan
    grouped["GeometryInterpretableFraction"] = grouped["GeometryInterpretableRows"] / grouped["N"].replace(0, np.nan)
    grouped["BoundaryMetricValidFraction"] = grouped["BoundaryMetricValidRows"] / grouped["N"].replace(0, np.nan)
    order = _ordered(grouped["ShapeClassV1"], CLASS_ORDER)
    grouped["__order"] = grouped["ShapeClassV1"].map({name: idx for idx, name in enumerate(order)})
    return grouped.sort_values("__order").drop(columns="__order")


def _stage_summary(shape: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        shape.groupby(["SnStage", "ShapeClassV1"], dropna=False)
        .agg(N=("Area_px", "size"), AreaSum_px=("Area_px", "sum"))
        .reset_index()
    )
    grouped["CountFractionWithinStage"] = grouped["N"] / grouped.groupby("SnStage")["N"].transform("sum").replace(0, np.nan)
    grouped["AreaFractionWithinStage"] = grouped["AreaSum_px"] / grouped.groupby("SnStage")["AreaSum_px"].transform("sum").replace(0, np.nan)
    stage_order = {name: idx for idx, name in enumerate(STAGE_ORDER)}
    class_order = {name: idx for idx, name in enumerate(_ordered(grouped["ShapeClassV1"], CLASS_ORDER))}
    grouped["__stage"] = grouped["SnStage"].map(stage_order).fillna(len(stage_order))
    grouped["__class"] = grouped["ShapeClassV1"].map(class_order)
    return grouped.sort_values(["__stage", "__class"]).drop(columns=["__stage", "__class"])


def _area_tier_summary(shape: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        shape.groupby("AreaTier", dropna=False)
        .agg(
            N=("Area_px", "size"),
            AreaSum_px=("Area_px", "sum"),
            BoundaryMetricValidRows=("BoundaryMetricValid", "sum"),
        )
        .reset_index()
    )
    total_n = float(grouped["N"].sum())
    total_area = float(grouped["AreaSum_px"].sum())
    grouped["CountFraction"] = grouped["N"] / total_n if total_n else np.nan
    grouped["AreaFraction"] = grouped["AreaSum_px"] / total_area if total_area else np.nan
    grouped["BoundaryMetricValidFraction"] = grouped["BoundaryMetricValidRows"] / grouped["N"].replace(0, np.nan)
    tier_map = {
        "tiny": "count_only",
        "small": "low_area_shape_caution",
        "medium": "geometry_interpretable_with_caution",
        "large": "geometry_interpretable",
        "high_confidence": "geometry_interpretable",
    }
    grouped["ShapeInterpretationTier"] = grouped["AreaTier"].astype(str).map(tier_map).fillna("review")
    tier_order = ["tiny", "small", "medium", "large", "high_confidence"]
    grouped["__order"] = grouped["AreaTier"].astype(str).map({name: idx for idx, name in enumerate(tier_order)}).fillna(len(tier_order))
    return grouped.sort_values("__order").drop(columns="__order")


def _geometry_fraction_by_stage(shape: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for stage, sub in shape.groupby("SnStage", dropna=False):
        area_total = float(_numeric(sub, "Area_px").sum())
        geom = sub["ShapeV1InterpretationTier"].astype(str).eq("geometry_interpretable")
        low = sub["ShapeV1InterpretationTier"].astype(str).eq("low_area_shape_caution")
        count_only = sub["ShapeV1InterpretationTier"].astype(str).eq("count_only")
        rows.append(
            {
                "SnStage": stage,
                "NRows": int(len(sub)),
                "GeometryInterpretableRows": int(geom.sum()),
                "GeometryInterpretableFraction": float(geom.mean()) if len(sub) else np.nan,
                "LowAreaShapeCautionRows": int(low.sum()),
                "LowAreaShapeCautionFraction": float(low.mean()) if len(sub) else np.nan,
                "CountOnlyRows": int(count_only.sum()),
                "CountOnlyFraction": float(count_only.mean()) if len(sub) else np.nan,
                "AreaInterpretableFraction": float(_numeric(sub[geom], "Area_px").sum() / area_total) if area_total else np.nan,
            }
        )
    out = pd.DataFrame(rows)
    out["__stage"] = out["SnStage"].map({name: idx for idx, name in enumerate(STAGE_ORDER)}).fillna(len(STAGE_ORDER))
    return out.sort_values("__stage").drop(columns="__stage")


def _frame_summary(shape: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for frame, sub in shape.groupby("FrameIndex", dropna=False):
        geom = sub["ShapeV1InterpretationTier"].astype(str).eq("geometry_interpretable")
        count_only = sub["ShapeV1InterpretationTier"].astype(str).eq("count_only")
        area_total = float(_numeric(sub, "Area_px").sum())
        rows.append(
            {
                "FrameIndex": int(frame),
                "RealTime_s": float(_numeric(sub, "RealTime_s").dropna().iloc[0]) if "RealTime_s" in sub and _numeric(sub, "RealTime_s").notna().any() else np.nan,
                "SnStage": str(sub["SnStage"].dropna().iloc[0]) if "SnStage" in sub and sub["SnStage"].notna().any() else "",
                "NRows": int(len(sub)),
                "AreaSum_px": area_total,
                "GeometryInterpretableRows": int(geom.sum()),
                "GeometryInterpretableFraction": float(geom.mean()) if len(sub) else np.nan,
                "CountOnlyRows": int(count_only.sum()),
                "CountOnlyFraction": float(count_only.mean()) if len(sub) else np.nan,
                "AreaInterpretableFraction": float(_numeric(sub[geom], "Area_px").sum() / area_total) if area_total else np.nan,
            }
        )
    return pd.DataFrame(rows).sort_values("FrameIndex")


def _representative_table(shape_class_v1_dir: Path) -> pd.DataFrame:
    atlas_manifest = shape_class_v1_dir / "representative_blob_atlas" / "representative_blob_atlas_manifest.csv"
    candidates = shape_class_v1_dir / "representative_blob_candidates.csv"
    if atlas_manifest.exists():
        return pd.read_csv(atlas_manifest)
    if candidates.exists():
        return pd.read_csv(candidates)
    return pd.DataFrame(columns=["FrameIndex", "BlobID", "ShapeClass", "ExemplarType", "Status", "PanelPath"])


def _write_tables(inputs: Inputs, output_dir: Path, shape: pd.DataFrame) -> dict[str, Path]:
    tables_dir = output_dir / "tables"
    tables = {
        "shape_class_v1_count_area_summary.csv": _class_summary(shape),
        "shape_class_v1_by_stage_summary.csv": _stage_summary(shape),
        "area_tier_summary.csv": _area_tier_summary(shape),
        "geometry_interpretable_fraction_by_stage.csv": _geometry_fraction_by_stage(shape),
        "frame_level_blob_structure_summary.csv": _frame_summary(shape),
        "representative_blob_table.csv": _representative_table(inputs.shape_class_v1_dir),
    }
    paths = {}
    for name, df in tables.items():
        path = tables_dir / name
        df.to_csv(path, index=False)
        paths[name] = path
    return paths


def _save_figure(fig, figures_dir: Path, stem: str, written: list[dict[str, str]], caption: str) -> None:
    for suffix in ("png", "svg"):
        path = figures_dir / f"{stem}.{suffix}"
        fig.savefig(path, dpi=250 if suffix == "png" else None, bbox_inches="tight", facecolor="white")
        written.append({"Figure": stem, "Format": suffix, "Path": str(path), "Caption": caption})


def _plot_class_fractions(class_summary: pd.DataFrame, figures_dir: Path, written: list[dict[str, str]]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    order = _ordered(class_summary["ShapeClassV1"], CLASS_ORDER)
    data = class_summary.set_index("ShapeClassV1").reindex(order).dropna(how="all").reset_index()
    x = np.arange(len(data))
    fig, ax = plt.subplots(figsize=(max(9, 0.8 * len(data)), 5.0))
    ax.bar(x - 0.18, data["CountFraction"], width=0.36, color="#56B4E9", label="Count fraction")
    ax.bar(x + 0.18, data["AreaFraction"], width=0.36, color="#E69F00", label="Projected-area fraction")
    ax.set_xticks(x)
    ax.set_xticklabels(data["ShapeClassV1"], rotation=30, ha="right")
    ax.set_ylabel("Fraction")
    _pct_axis(ax)
    ax.set_title("ShapeClassV1 count and projected-area fractions")
    ax.legend(frameon=False)
    ax.grid(axis="y", color="#DDDDDD", linewidth=0.7)
    fig.tight_layout()
    _save_figure(fig, figures_dir, "Fig_ShapeClassV1_CountAreaFractions", written, "Distribution of ShapeClassV1 count and projected-area fractions.")
    plt.close(fig)


def _plot_stage(stage_summary: pd.DataFrame, figures_dir: Path, written: list[dict[str, str]]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    order = _ordered(stage_summary["ShapeClassV1"], CLASS_ORDER)
    data = stage_summary.pivot_table(index="SnStage", columns="ShapeClassV1", values="AreaFractionWithinStage", aggfunc="sum").reindex(STAGE_ORDER).fillna(0)
    data = data[[c for c in order if c in data.columns]]
    fig, ax = plt.subplots(figsize=(9.5, 5.0))
    bottom = np.zeros(len(data))
    labels = list(data.index)
    for cls in data.columns:
        values = data[cls].to_numpy()
        ax.bar(labels, values, bottom=bottom, color=CLASS_COLORS.get(cls, "#999999"), label=cls)
        bottom += values
    ax.set_ylabel("Within-stage projected-area fraction")
    _pct_axis(ax)
    ax.set_ylim(0, 1)
    ax.set_title("ShapeClassV1 projected-area fractions by Sn stage")
    ax.tick_params(axis="x", rotation=20)
    ax.legend(frameon=False, fontsize=8, ncols=2)
    fig.tight_layout()
    _save_figure(fig, figures_dir, "Fig_ShapeClassV1_ByStage", written, "Distribution of ShapeClassV1 projected-area fractions within each Sn stage.")
    plt.close(fig)


def _plot_area_tier(area_tier: pd.DataFrame, figures_dir: Path, written: list[dict[str, str]]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x = np.arange(len(area_tier))
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    ax.bar(x - 0.18, area_tier["CountFraction"], width=0.36, color="#009E73", label="Count fraction")
    ax.bar(x + 0.18, area_tier["AreaFraction"], width=0.36, color="#CC79A7", label="Projected-area fraction")
    ax.set_xticks(x)
    ax.set_xticklabels(area_tier["AreaTier"], rotation=20, ha="right")
    ax.set_ylabel("Fraction")
    _pct_axis(ax)
    ax.set_title("AreaTier count and projected-area fractions")
    ax.legend(frameon=False)
    fig.tight_layout()
    _save_figure(fig, figures_dir, "Fig_AreaTier_Distribution", written, "Distribution of AreaTier count and projected-area fractions.")
    plt.close(fig)


def _plot_geometry_fraction(stage_fraction: pd.DataFrame, figures_dir: Path, written: list[dict[str, str]]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data = stage_fraction.set_index("SnStage").reindex(STAGE_ORDER).dropna(how="all")
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    ax.plot(data.index, data["GeometryInterpretableFraction"], marker="o", color="#0072B2", label="Row fraction")
    ax.plot(data.index, data["AreaInterpretableFraction"], marker="s", color="#D55E00", label="Projected-area fraction")
    ax.set_ylabel("Fraction")
    _pct_axis(ax)
    ax.set_ylim(0, 1.05)
    ax.set_title("Geometry-interpretable fractions by Sn stage")
    ax.tick_params(axis="x", rotation=20)
    ax.legend(frameon=False)
    ax.grid(color="#DDDDDD", linewidth=0.7)
    fig.tight_layout()
    _save_figure(fig, figures_dir, "Fig_GeometryInterpretable_Fraction", written, "Geometry-interpretable row and projected-area fractions by Sn stage.")
    plt.close(fig)


def _plot_metric_distributions(shape: pd.DataFrame, figures_dir: Path, written: list[dict[str, str]]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    metrics = ["ProjectedSphericity2D", "AxisAspectRatio", "Solidity2D", "ProjectedRoughness_boundary"]
    fig, axes = plt.subplots(2, 2, figsize=(9.0, 6.2))
    for ax, metric in zip(axes.ravel(), metrics):
        values = _numeric(shape, metric).dropna()
        ax.hist(values, bins=50, color="#56B4E9", alpha=0.85)
        ax.set_title(metric)
        ax.set_ylabel("Blob count")
    fig.suptitle("Projected shape-parameter distributions")
    fig.tight_layout()
    _save_figure(fig, figures_dir, "Fig_ShapeParameter_Distributions", written, "Distributions of selected projected shape parameters.")
    plt.close(fig)


def _plot_proxy_map(shape: pd.DataFrame, figures_dir: Path, written: list[dict[str, str]]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data = shape.dropna(subset=["ProjectedRoughness_boundary", "ProjectedSphericity2D", "Area_px"])
    if len(data) > 120000:
        data = data.sample(n=120000, random_state=21)
    fig, ax = plt.subplots(figsize=(8.0, 6.0))
    order = _ordered(data["ShapeClassV1"], CLASS_ORDER)
    for cls in order:
        sub = data[data["ShapeClassV1"] == cls]
        if sub.empty:
            continue
        size = np.clip(np.sqrt(_numeric(sub, "Area_px")) / 2.5, 4, 32)
        ax.scatter(
            _numeric(sub, "ProjectedRoughness_boundary"),
            _numeric(sub, "ProjectedSphericity2D"),
            s=size,
            alpha=0.20,
            linewidths=0,
            color=CLASS_COLORS.get(cls, "#999999"),
            label=cls,
        )
    ax.set_xlabel("ProjectedRoughness_boundary (2D exterior-boundary proxy)")
    ax.set_ylabel("ProjectedSphericity2D (2D projected compactness proxy)")
    ax.set_title("Projected sphericity and boundary-proxy map")
    if len(data):
        ax.set_xlim(0.95, min(3.5, float(np.nanpercentile(_numeric(data, "ProjectedRoughness_boundary"), 99.5))))
    ax.set_ylim(0, 1.05)
    ax.grid(color="#DDDDDD", linewidth=0.7)
    ax.legend(frameon=False, fontsize=7, ncols=2)
    fig.tight_layout()
    _save_figure(fig, figures_dir, "Fig_Sphericity_Roundness_Proxy_Map", written, "ProjectedSphericity2D and ProjectedRoughness_boundary proxy map.")
    plt.close(fig)


def _plot_representative_atlas(rep: pd.DataFrame, figures_dir: Path, written: list[dict[str, str]]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    panels = rep.copy()
    if "Status" in panels.columns:
        panels = panels[panels["Status"].astype(str).eq("RENDERED")]
    if "PanelPath" in panels.columns:
        panels = panels[panels["PanelPath"].astype(str).map(lambda p: Path(p).exists())]
    else:
        panels = panels.iloc[0:0].copy()
    if panels.empty:
        fig, ax = plt.subplots(figsize=(6, 2))
        ax.text(0.5, 0.5, "No representative panels available", ha="center", va="center")
        ax.axis("off")
    else:
        panels = panels.head(12)
        n = len(panels)
        cols = min(4, n)
        rows = int(np.ceil(n / cols))
        fig, axes = plt.subplots(rows, cols, figsize=(3.2 * cols, 3.0 * rows))
        axes = np.atleast_1d(axes).ravel()
        for ax, (_, row) in zip(axes, panels.iterrows()):
            image = plt.imread(str(row["PanelPath"]))
            ax.imshow(image)
            ax.set_title(f"{row.get('ShapeClass', row.get('ShapeClassV1', ''))}\n{row.get('ExemplarType', '')}", fontsize=8)
            ax.axis("off")
        for ax in axes[len(panels):]:
            ax.axis("off")
        fig.suptitle("Representative projected blob panels", fontsize=12)
        fig.tight_layout()
    _save_figure(fig, figures_dir, "Fig_RepresentativeBlobAtlas", written, "Representative projected blob panels from the accepted atlas manifest.")
    plt.close(fig)


def _write_figures(output_dir: Path, shape: pd.DataFrame, table_paths: dict[str, Path]) -> pd.DataFrame:
    figures_dir = output_dir / "figures"
    written: list[dict[str, str]] = []
    class_summary = pd.read_csv(table_paths["shape_class_v1_count_area_summary.csv"])
    stage_summary = pd.read_csv(table_paths["shape_class_v1_by_stage_summary.csv"])
    area_tier = pd.read_csv(table_paths["area_tier_summary.csv"])
    stage_fraction = pd.read_csv(table_paths["geometry_interpretable_fraction_by_stage.csv"])
    representative = pd.read_csv(table_paths["representative_blob_table.csv"])
    _plot_class_fractions(class_summary, figures_dir, written)
    _plot_stage(stage_summary, figures_dir, written)
    _plot_area_tier(area_tier, figures_dir, written)
    _plot_geometry_fraction(stage_fraction, figures_dir, written)
    _plot_metric_distributions(shape, figures_dir, written)
    _plot_proxy_map(shape, figures_dir, written)
    _plot_representative_atlas(representative, figures_dir, written)
    return pd.DataFrame(written)


def _field_dictionary() -> pd.DataFrame:
    rows = [
        ("FrameIndex", "Frame identifier from the source time series."),
        ("RealTime_s", "Elapsed time in seconds."),
        ("BlobID", "Per-frame blob identifier from the morphology table."),
        ("ShapeClassV1", "Mutually exclusive projected 2D shape class assigned by the accepted ShapeClassV1 package."),
        ("ShapeClassV1Reason", "Rule label recorded by the ShapeClassV1 package."),
        ("ShapeV1InterpretationTier", "Scope tier for projected shape use: geometry_interpretable, low_area_shape_caution, or count_only."),
        ("MetricSource", "Source label for scalar/projected metrics."),
        ("BoundaryMetricSource", "Source label for boundary-related metrics."),
        ("CorrectedBoundaryAvailable", "Whether corrected boundary context is available for the row."),
        ("DatasetSubset", "Dataset subset label recorded by the shape package."),
        ("FullSidecarDerived", "Whether the row is marked as full-sidecar derived by the source package."),
        ("Area_px", "Projected blob area in pixels."),
        ("AreaTier", "Area-based reliability tier."),
        ("BoundaryMetricValid", "Bundle-level boolean derived from geometry-interpretable shape tier when source column is absent."),
        ("ProjectedSphericity2D", "2D projected compactness proxy."),
        ("Circularity2D_boundary", "2D circularity formula based on projected area and outer boundary."),
        ("AxisAspectRatio", "MajorAxisLength_px divided by MinorAxisLength_px."),
        ("AspectRatio01", "MinorAxisLength_px divided by MajorAxisLength_px."),
        ("Solidity2D", "Projected area divided by projected convex area."),
        ("ProjectedRegularity2D", "Composite projected proxy used for sorting or summary, not original Krumbein regularity."),
        ("ProjectedRoughness_boundary", "Outer-boundary perimeter divided by convex reference perimeter."),
        ("PtotalOverPouter", "P_total_boundary divided by P_outer_boundary."),
        ("SnStage", "Stage label from the accepted shape/statistics package."),
    ]
    return pd.DataFrame(rows, columns=["Field", "Definition"])


def _formula_notes() -> str:
    return """# Formula Notes

All shape quantities in this bundle are 2D projected morphology descriptors.

- `ProjectedSphericity2D`: projected compactness proxy derived from projected area and boundary length. It is not 3D sphericity.
- `Circularity2D_boundary = 4*pi*Area_px / P_outer_boundary^2`. It is not Wadell roundness.
- `AxisAspectRatio = MajorAxisLength_px / MinorAxisLength_px`.
- `AspectRatio01 = MinorAxisLength_px / MajorAxisLength_px`. This is reciprocal to `AxisAspectRatio` and is not an independent shape dimension.
- `Solidity2D = Area_px / ConvexArea_px` where convex area is available from the source morphology table.
- `ProjectedRegularity2D` is a projected ranking proxy, not Krumbein original regularity.
- `ProjectedRoughness_boundary = P_outer_boundary / Pc_outer_boundary`. This is a 2D exterior-boundary proxy and not 3D roughness.
- `PtotalOverPouter = P_total_boundary / P_outer_boundary`.
- `ShapeClassV1` is a projected 2D class label with reliability gates.
- `AreaTier` records area-based reliability bins.
- `BoundaryMetricValid` marks rows used for boundary-related projected morphology summaries.

These quantities are not true fluid-fluid interfacial area and do not describe out-of-plane morphology. Area below 250 px is not used as a default boundary morphology interpretation tier; low-area rows are retained for count and caution summaries.
"""


def _readme(decision_label: str) -> str:
    return f"""# G21 Blob Structure Data/Figure Bundle

This directory organizes accepted G21 blob morphology data tables, neutral figures, formula notes, field definitions, QC notes, and provenance.

Pipeline acceptance decision: `{decision_label}`.

The bundle is intended for downstream analysis by the user. It does not write scientific results, mechanism claims, causal statements, tracking conclusions, fractal conclusions, or 3D roughness conclusions.
"""


def _qc_notes(acceptance_manifest: dict[str, object]) -> str:
    decision = acceptance_manifest.get("decision_label", "")
    row_counts = acceptance_manifest.get("row_counts", {})
    coverage = acceptance_manifest.get("coverage", {})
    warnings = acceptance_manifest.get("warning_issues", [])
    blocking = acceptance_manifest.get("blocking_issues", [])
    return f"""# QC And Scope Notes

Decision label: `{decision}`.

Frame coverage:

```text
expected_frames = {coverage.get('expected_frames', row_counts.get('frames', ''))}
observed_frame_rows = {coverage.get('observed_frame_rows', '')}
missing_frame_count = {coverage.get('missing_frame_count', '')}
unexpected_frame_count = {coverage.get('unexpected_frame_count', '')}
```

Row counts:

```text
morphology_rows = {row_counts.get('morphology_rows', '')}
shape_class_v1_rows = {row_counts.get('shape_class_v1_rows', '')}
geometry_interpretable_rows = {row_counts.get('geometry_interpretable_rows', '')}
count_only_rows = {row_counts.get('count_only_rows', '')}
```

Documented warnings:

```text
{', '.join(map(str, warnings)) if warnings else 'none'}
```

Blocking issues:

```text
{', '.join(map(str, blocking)) if blocking else 'none'}
```

Scope exclusions:

```text
No tracking.
No split/merge lineage.
No boundary fractal dimension.
No 3D roughness.
No true fluid-fluid interfacial area.
No full Level B interpretation in this bundle.
```
"""


def _write_data_inventory(output_dir: Path, table_paths: dict[str, Path]) -> pd.DataFrame:
    rows = []
    for name, path in table_paths.items():
        df = pd.read_csv(path)
        rows.append({"Name": name, "Type": "table", "Path": str(path), "Rows": int(len(df)), "Description": name.replace("_", " ").replace(".csv", "")})
    for name in [
        "README_data_figure_bundle.md",
        "data_inventory.csv",
        "figure_inventory.csv",
        "field_dictionary.csv",
        "formula_notes.md",
        "qc_and_scope_notes.md",
        "bundle_manifest.json",
    ]:
        path = output_dir / name
        rows.append({"Name": name, "Type": "metadata", "Path": str(path), "Rows": "", "Description": name})
    inventory = pd.DataFrame(rows)
    inventory.to_csv(output_dir / "data_inventory.csv", index=False)
    return inventory


def _validate_outputs(output_dir: Path) -> None:
    missing = [name for name in REQUIRED_TOP_LEVEL if not (output_dir / name).exists()]
    missing += [f"tables/{name}" for name in REQUIRED_TABLES if not (output_dir / "tables" / name).exists()]
    for stem in REQUIRED_FIGURE_STEMS:
        for suffix in ("png", "svg"):
            if not (output_dir / "figures" / f"{stem}.{suffix}").exists():
                missing.append(f"figures/{stem}.{suffix}")
    if missing:
        raise RuntimeError(f"Missing required bundle output(s): {missing}")


def build_data_figure_bundle(inputs: Inputs) -> dict[str, object]:
    output_dir = inputs.output_dir or inputs.morphology_dir / f"g21_blob_structure_data_figure_bundle_{_timestamp()}"
    _safe_output_dir(output_dir, inputs.overwrite)

    shape = _load_shape_table(inputs.shape_class_v1_dir)
    acceptance_manifest = _read_required_json(
        inputs.acceptance_dir / "g21_blob_pipeline_release_manifest.json",
        "pipeline acceptance manifest",
    )
    formal_manifest = _read_required_json(
        inputs.shape_class_v1_dir / "shape_class_v1_formal_manifest.json",
        "ShapeClassV1 formal manifest",
    )
    stats_manifest = _read_required_json(
        inputs.structure_statistics_dir / "blob_structure_statistics_manifest.json",
        "structure statistics manifest",
    )
    acceptance_decision = str(acceptance_manifest.get("decision_label", ""))
    formal_decision = str(formal_manifest.get("decision_label", ""))
    _require_decision(acceptance_decision, ACCEPTED_PIPELINE_DECISIONS, "Pipeline acceptance manifest")
    _require_decision(formal_decision, ACCEPTED_SHAPE_CLASS_DECISIONS, "ShapeClassV1 formal manifest")
    n_rows = int(len(shape))
    n_frames = int(shape["FrameIndex"].nunique()) if "FrameIndex" in shape else 0
    _require_manifest_count(formal_manifest, "ShapeClassV1 formal manifest", "rows", n_rows)
    _require_manifest_count(formal_manifest, "ShapeClassV1 formal manifest", "frames", n_frames)
    _require_manifest_count(acceptance_manifest, "Pipeline acceptance manifest", "shape_class_v1_rows", n_rows)
    _require_manifest_count(acceptance_manifest, "Pipeline acceptance manifest", "frames", n_frames)
    _require_manifest_count(stats_manifest, "Structure statistics manifest", "blob_rows", n_rows)
    _require_manifest_count(stats_manifest, "Structure statistics manifest", "frames", n_frames)

    table_paths = _write_tables(inputs, output_dir, shape)
    figure_inventory = _write_figures(output_dir, shape, table_paths)

    decision_label = acceptance_decision
    (output_dir / "README_data_figure_bundle.md").write_text(_readme(decision_label), encoding="utf-8")
    _field_dictionary().to_csv(output_dir / "field_dictionary.csv", index=False)
    (output_dir / "formula_notes.md").write_text(_formula_notes(), encoding="utf-8")
    (output_dir / "qc_and_scope_notes.md").write_text(_qc_notes(acceptance_manifest), encoding="utf-8")
    data_inventory = _write_data_inventory(output_dir, table_paths)
    figure_inventory.to_csv(output_dir / "figure_inventory.csv", index=False)

    manifest = {
        "schema_version": "blob_structure_data_figure_bundle_v1",
        "created_at_utc": _utc_now(),
        "git_commit": _git_commit(inputs.repo_root),
        "output_dir": str(output_dir),
        "source_dirs": {
            "postprocess_dir": str(inputs.postprocess_dir),
            "morphology_dir": str(inputs.morphology_dir),
            "shape_class_v1_dir": str(inputs.shape_class_v1_dir),
            "structure_statistics_dir": str(inputs.structure_statistics_dir),
            "acceptance_dir": str(inputs.acceptance_dir),
        },
        "acceptance_decision_label": decision_label,
        "shape_class_decision_label": formal_manifest.get("decision_label", ""),
        "row_counts": {
            "shape_class_v1_rows": n_rows,
            "frames": n_frames,
            "tables": {name: int(len(pd.read_csv(path))) for name, path in table_paths.items()},
            "figures": int(len(figure_inventory)),
        },
        "input_manifests": {
            "shape_class_v1_formal_manifest": formal_manifest,
            "structure_statistics_manifest": stats_manifest,
            "pipeline_acceptance_manifest": acceptance_manifest,
        },
        "scope": {
            "writes_scientific_interpretation": False,
            "tracking": False,
            "fractal": False,
            "roughness_3d": False,
            "true_fluid_fluid_interfacial_area": False,
            "full_level_b_interpretation": False,
        },
        "outputs": {
            "data_inventory": str(output_dir / "data_inventory.csv"),
            "figure_inventory": str(output_dir / "figure_inventory.csv"),
            "tables": {name: str(path) for name, path in table_paths.items()},
            "figures": figure_inventory["Path"].tolist(),
        },
    }
    _write_json(output_dir / "bundle_manifest.json", manifest)
    _validate_outputs(output_dir)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a neutral blob-structure data/figure bundle.")
    parser.add_argument("--postprocess-dir", required=True)
    parser.add_argument("--morphology-dir", required=True)
    parser.add_argument("--shape-class-v1-dir", required=True)
    parser.add_argument("--structure-statistics-dir", required=True)
    parser.add_argument("--acceptance-dir", required=True)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    manifest = build_data_figure_bundle(
        Inputs(
            postprocess_dir=Path(args.postprocess_dir),
            morphology_dir=Path(args.morphology_dir),
            shape_class_v1_dir=Path(args.shape_class_v1_dir),
            structure_statistics_dir=Path(args.structure_statistics_dir),
            acceptance_dir=Path(args.acceptance_dir),
            output_dir=Path(args.output_dir) if args.output_dir else None,
            repo_root=Path(args.repo_root) if args.repo_root else None,
            overwrite=bool(args.overwrite),
        )
    )
    print(json.dumps({"output_dir": manifest["output_dir"], "row_counts": manifest["row_counts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
