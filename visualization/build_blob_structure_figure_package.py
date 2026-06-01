"""Build presentation-ready G21 projected blob-structure figures.

Inputs are the accepted morphology data product and the derived structure
statistics package. This script only plots existing data; it does not run
sidecar extraction, tracking, fractal analysis, or 3D roughness analysis.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


CLASS_COLORS = {
    "ambiguous_valid": "#0072B2",
    "branched_complex": "#D55E00",
    "compact_round": "#009E73",
    "compact_regular": "#009E73",
    "near_compact_regular": "#56B4E9",
    "elongated": "#CC79A7",
    "moderately_elongated": "#CC79A7",
    "moderately_concave": "#E69F00",
    "low_area_compact_candidate_100_249": "#8DD3C7",
    "low_area_elongated_candidate_100_249": "#BEBADA",
    "low_area_projected_shape_caution_100_249": "#FDB462",
    "count_only_lt100": "#B3B3B3",
    "small_unclassified": "#7F7F7F",
    "boundary_invalid": "#999999",
}

CLASS_ORDER_V0 = [
    "branched_complex",
    "ambiguous_valid",
    "elongated",
    "compact_round",
    "small_unclassified",
]
CLASS_ORDER_V1 = [
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

STAGE_ORDER = ["early_depletion", "active_dissolution", "late_depletion", "endpoint"]


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_output_dir(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise FileExistsError(f"Output directory exists and is not empty: {path}")
    path.mkdir(parents=True, exist_ok=True)


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return pd.read_csv(path)


def _pct_axis(ax) -> None:
    ax.yaxis.set_major_formatter(lambda value, _: f"{100 * value:.0f}%")


def _class_order(classes: Iterable[str], shape_class_version: str = "v0") -> list[str]:
    classes = [str(cls) for cls in classes]
    preferred = CLASS_ORDER_V1 if str(shape_class_version).lower() == "v1" else CLASS_ORDER_V0
    known = [cls for cls in preferred if cls in classes]
    extras = sorted(cls for cls in classes if cls not in set(known))
    return known + extras


def _display_class_label(shape_class: object) -> str:
    labels = {
        "compact_regular": "compact\nregular",
        "near_compact_regular": "near compact\nregular",
        "moderately_elongated": "moderately\nelongated",
        "moderately_concave": "moderately\nconcave",
        "branched_complex": "branched\ncomplex",
        "ambiguous_valid": "ambiguous\nvalid",
        "low_area_compact_candidate_100_249": "low-area compact\n100-249 px",
        "low_area_elongated_candidate_100_249": "low-area elongated\n100-249 px",
        "low_area_projected_shape_caution_100_249": "low-area projected\nshape caution",
        "count_only_lt100": "count-only\n<100 px",
        "small_unclassified": "small\nunclassified",
        "compact_round": "compact\nround",
    }
    text = str(shape_class)
    return labels.get(text, text.replace("_", "\n"))


def plot_class_fractions(class_summary: pd.DataFrame, out_path: Path, class_order: list[str]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data = class_summary.set_index("ShapeClass").reindex(class_order).dropna(how="all").reset_index()
    x = np.arange(len(data))
    fig, ax = plt.subplots(figsize=(max(9, 0.82 * len(data)), 5.2))
    ax.bar(x - 0.18, data["CountFraction"], width=0.36, color="#56B4E9", label="Count fraction")
    ax.bar(x + 0.18, data["AreaFraction"], width=0.36, color="#E69F00", label="Projected area fraction")
    ax.set_xticks(x)
    ax.set_xticklabels(data["ShapeClass"], rotation=25, ha="right")
    ax.set_ylabel("Fraction")
    _pct_axis(ax)
    ax.set_title("G21 projected blob shape-class composition")
    ax.legend(frameon=False)
    ax.grid(axis="y", color="#DDDDDD", linewidth=0.7)
    fig.tight_layout()
    fig.savefig(out_path, dpi=220)
    plt.close(fig)


def plot_stage_area_fractions(transition: pd.DataFrame, out_path: Path, class_order: list[str]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data = transition.set_index("SnStage").reindex(STAGE_ORDER).dropna(how="all")
    fig, ax = plt.subplots(figsize=(9.5, 5))
    bottom = np.zeros(len(data))
    labels = list(data.index)
    for cls in class_order:
        col = f"area_frac_{cls}"
        if col not in data:
            continue
        values = data[col].fillna(0).to_numpy()
        ax.bar(labels, values, bottom=bottom, color=CLASS_COLORS.get(cls, "#999999"), label=cls)
        bottom += values
    ax.set_ylabel("Within-stage projected area fraction")
    _pct_axis(ax)
    ax.set_ylim(0, 1.0)
    ax.set_title("G21 projected shape-class area fractions by Sn stage")
    ax.tick_params(axis="x", rotation=20)
    ax.legend(frameon=False, fontsize=8, ncols=2)
    fig.tight_layout()
    fig.savefig(out_path, dpi=220)
    plt.close(fig)


def plot_shape_map(
    morphology_dir: Path,
    out_path: Path,
    class_order: list[str],
    max_points: int = 120000,
    shape_class_v1_dir: Path | None = None,
) -> dict[str, int]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if shape_class_v1_dir is not None:
        path = shape_class_v1_dir / "blob_shape_class_v1_by_blob.csv"
        cols = ["ShapeClassV1", "Area_px", "ProjectedSphericity2D", "ProjectedRoughness_boundary"]
        data = pd.read_csv(path, usecols=cols).rename(columns={"ShapeClassV1": "ShapeClass"})
        data["ShapeValid"] = ~data["ShapeClass"].astype(str).isin({"count_only_lt100", "boundary_invalid"})
    else:
        path = morphology_dir / "blob_shape_class_by_blob.csv"
        cols = ["ShapeClass", "ShapeValid", "Area_px", "ProjectedSphericity2D", "ProjectedRoughness_boundary"]
        data = pd.read_csv(path, usecols=cols)
        data["ShapeValid"] = data["ShapeValid"].astype(str).str.lower().isin({"true", "1", "yes"})
    valid = data[data["ShapeValid"]].dropna(subset=["ProjectedSphericity2D", "ProjectedRoughness_boundary", "Area_px"])
    if len(valid) > max_points:
        valid = valid.sample(n=max_points, random_state=21)

    fig, ax = plt.subplots(figsize=(8.4, 6.4))
    for cls in class_order:
        sub = valid[valid["ShapeClass"] == cls]
        if sub.empty:
            continue
        size = np.clip(np.sqrt(sub["Area_px"].to_numpy()) / 2.5, 4, 36)
        ax.scatter(
            sub["ProjectedRoughness_boundary"],
            sub["ProjectedSphericity2D"],
            s=size,
            alpha=0.22,
            linewidths=0,
            color=CLASS_COLORS.get(cls, "#999999"),
            label=cls,
        )
    ax.set_xlabel("ProjectedRoughness_boundary (2D exterior-boundary proxy)")
    ax.set_ylabel("ProjectedSphericity2D (2D compactness proxy)")
    ax.set_title("G21 projected blob shape map")
    ax.set_xlim(0.95, min(3.5, np.nanpercentile(valid["ProjectedRoughness_boundary"], 99.5)))
    ax.set_ylim(0, 1.05)
    ax.grid(color="#DDDDDD", linewidth=0.7)
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=220)
    plt.close(fig)
    return {"plotted_points": int(len(valid)), "available_valid_points": int(len(data[data["ShapeValid"]]))}


def build_atlas_montage(
    morphology_dir: Path,
    out_path: Path,
    class_order: list[str],
    atlas_dir: Path | None = None,
    max_panels: int = 8,
) -> dict[str, object]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.image as mpimg

    atlas_dir = atlas_dir or morphology_dir / "representative_blob_atlas"
    manifest_path = atlas_dir / "representative_blob_atlas_manifest.csv"
    atlas = _read_csv(manifest_path)
    atlas = atlas[atlas["Status"].astype(str).eq("RENDERED")].copy()
    preferred = []
    for cls in class_order:
        if len(preferred) >= max_panels:
            break
        candidates = atlas[atlas["ShapeClass"] == cls]
        if candidates.empty:
            continue
        medoid = candidates[candidates["ExemplarType"] == "class_medoid"]
        preferred.append((medoid.iloc[0] if not medoid.empty else candidates.iloc[0]).to_dict())
    if not preferred:
        preferred = [row.to_dict() for _, row in atlas.head(max_panels).iterrows()]

    n = len(preferred)
    if n == 0:
        raise ValueError("No rendered atlas panels found")
    ncols = min(4, n)
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(3.25 * ncols, 3.45 * nrows))
    axes_array = np.asarray(axes).reshape(-1)
    for ax, row in zip(axes_array, preferred):
        image = mpimg.imread(row["PanelPath"])
        ax.imshow(image)
        ax.set_axis_off()
        ax.set_title(_display_class_label(row["ShapeClass"]), fontsize=9)
    for ax in axes_array[len(preferred):]:
        ax.set_axis_off()
    fig.suptitle("Representative projected blob examples", fontsize=13)
    fig.tight_layout()
    fig.savefig(out_path, dpi=220)
    plt.close(fig)
    return {"panels": n, "shape_classes": [str(row["ShapeClass"]) for row in preferred]}


def copy_existing_metric_figure(stats_dir: Path, out_dir: Path) -> list[str]:
    copied = []
    src = stats_dir / "figures_blob_structure" / "valid_metric_distributions_by_shape_class.png"
    if src.exists():
        dst = out_dir / "Fig_ValidMetricDistributionsByShapeClass.png"
        shutil.copy2(src, dst)
        copied.append(str(dst))
    return copied


def write_caption_bank(path: Path, figure_records: dict[str, object], shape_class_version: str = "v0") -> None:
    summary_lines = ["| Figure | Render details |", "|---|---|"]
    for name, record in figure_records.items():
        details = []
        if "plotted_points" in record:
            details.append(f"{record['plotted_points']} plotted points")
        if "available_valid_points" in record:
            details.append(f"{record['available_valid_points']} available valid rows")
        if "panels" in record:
            details.append(f"{record['panels']} atlas panels")
        if "source" in record:
            details.append(f"source: {record['source']}")
        summary_lines.append(f"| `{name}` | {'; '.join(details) if details else 'rendered'} |")

    lines = [
        "# G21 Blob Structure Figure Caption Bank",
        "",
        f"Shape-class version: `{shape_class_version}`.",
        "",
        "All captions describe projected 2D blob morphology. Do not use these figures to claim tracking, split/merge lineage, boundary fractal dimension, 3D roughness, true fluid-fluid interfacial area, or Wadell roundness.",
        "",
        "## Fig_BlobShapeClassFractions",
        "",
        "G21 projected blob shape-class composition across the morphology data product. Count fractions and projected-area fractions are shown separately because small objects dominate counts but not projected area.",
        "",
        "## Fig_ShapeClassBySnStage",
        "",
        "Within-stage projected-area fractions by SnMonotone stage. Fractions are normalized within each stage and therefore describe stage composition, not total experiment mass.",
        "",
        "## Fig_BlobShapeMap_Sphericity_Roughness",
        "",
        "Projected 2D blob shape map using `ProjectedRoughness_boundary` as a 2D exterior-boundary complexity proxy and `ProjectedSphericity2D` as a 2D compactness proxy. Points are shape-valid rows sampled deterministically for plotting only.",
        "",
        "## Fig_RepresentativeBlobAtlas",
        "",
        "Representative projected blob examples from the rendered atlas panels. The panels are examples of shape classes, not tracked blob histories.",
        "",
        "## Fig_ValidMetricDistributionsByShapeClass",
        "",
        "Shape-valid projected metric distributions by class. These metrics are 2D projected proxies and should not be described as 3D morphology or Wadell roundness.",
        "",
        "## Render Summary",
        "",
        *summary_lines,
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_figure_package(
    morphology_dir: Path,
    statistics_dir: Path,
    output_dir: Path,
    shape_class_v1_dir: Path | None = None,
    atlas_dir: Path | None = None,
    max_atlas_panels: int = 8,
) -> dict[str, object]:
    _safe_output_dir(output_dir)
    class_summary = _read_csv(statistics_dir / "blob_structure_class_summary.csv")
    transition = _read_csv(statistics_dir / "blob_structure_transition_by_sn_stage.csv")
    shape_class_version = "v1" if shape_class_v1_dir is not None else "v0"
    if "ShapeClassVersion" in class_summary.columns:
        nonempty_versions = class_summary["ShapeClassVersion"].dropna().astype(str)
        if not nonempty_versions.empty:
            shape_class_version = nonempty_versions.iloc[0]
    class_order = _class_order(class_summary["ShapeClass"].astype(str).tolist(), shape_class_version)

    figure_records: dict[str, object] = {}
    class_path = output_dir / "Fig_BlobShapeClassFractions.png"
    plot_class_fractions(class_summary, class_path, class_order)
    figure_records["Fig_BlobShapeClassFractions.png"] = {"path": str(class_path)}

    stage_path = output_dir / "Fig_ShapeClassBySnStage.png"
    plot_stage_area_fractions(transition, stage_path, class_order)
    figure_records["Fig_ShapeClassBySnStage.png"] = {"path": str(stage_path)}

    map_path = output_dir / "Fig_BlobShapeMap_Sphericity_Roughness.png"
    figure_records["Fig_BlobShapeMap_Sphericity_Roughness.png"] = {
        "path": str(map_path),
        **plot_shape_map(morphology_dir, map_path, class_order, shape_class_v1_dir=shape_class_v1_dir),
    }

    atlas_path = output_dir / "Fig_RepresentativeBlobAtlas.png"
    figure_records["Fig_RepresentativeBlobAtlas.png"] = {
        "path": str(atlas_path),
        **build_atlas_montage(
            morphology_dir,
            atlas_path,
            class_order,
            atlas_dir=atlas_dir,
            max_panels=max_atlas_panels,
        ),
    }

    for copied in copy_existing_metric_figure(statistics_dir, output_dir):
        figure_records[Path(copied).name] = {"path": copied, "source": "statistics_package"}

    write_caption_bank(output_dir / "figure_caption_bank.md", figure_records, shape_class_version)
    manifest = {
        "schema_version": "1.0",
        "created_at_utc": _utc_now(),
        "morphology_dir": str(morphology_dir),
        "statistics_dir": str(statistics_dir),
        "shape_class_v1_dir": str(shape_class_v1_dir) if shape_class_v1_dir is not None else "",
        "atlas_dir": str(atlas_dir) if atlas_dir is not None else str(morphology_dir / "representative_blob_atlas"),
        "shape_class_version": shape_class_version,
        "output_dir": str(output_dir),
        "figures": figure_records,
        "scope": {
            "projected_2d_blob_structure_figures": True,
            "tracking": False,
            "split_merge": False,
            "fractal": False,
            "roughness_3d": False,
            "true_fluid_fluid_interfacial_area": False,
            "wadell_roundness": False,
        },
    }
    (output_dir / "figure_package_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build presentation-ready G21 blob structure figure package.")
    parser.add_argument("--morphology-dir", required=True, type=Path)
    parser.add_argument("--statistics-dir", required=True, type=Path)
    parser.add_argument("--shape-class-v1-dir", type=Path, default=None)
    parser.add_argument("--atlas-dir", type=Path, default=None)
    parser.add_argument("--max-atlas-panels", type=int, default=8)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    out = args.output_dir or args.statistics_dir / f"g21_blob_structure_figure_package_{_timestamp()}"
    manifest = build_figure_package(
        args.morphology_dir,
        args.statistics_dir,
        out,
        shape_class_v1_dir=args.shape_class_v1_dir,
        atlas_dir=args.atlas_dir,
        max_atlas_panels=args.max_atlas_panels,
    )
    print(json.dumps({"output_dir": manifest["output_dir"], "figures": list(manifest["figures"].keys())}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
