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
    "elongated": "#CC79A7",
    "small_unclassified": "#7F7F7F",
    "boundary_invalid": "#999999",
}

CLASS_ORDER = [
    "branched_complex",
    "ambiguous_valid",
    "elongated",
    "compact_round",
    "small_unclassified",
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


def plot_class_fractions(class_summary: pd.DataFrame, out_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data = class_summary.set_index("ShapeClass").reindex(CLASS_ORDER).dropna(how="all").reset_index()
    x = np.arange(len(data))
    fig, ax = plt.subplots(figsize=(9, 5))
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


def plot_stage_area_fractions(transition: pd.DataFrame, out_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data = transition.set_index("SnStage").reindex(STAGE_ORDER).dropna(how="all")
    fig, ax = plt.subplots(figsize=(9.5, 5))
    bottom = np.zeros(len(data))
    labels = list(data.index)
    for cls in CLASS_ORDER:
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


def plot_shape_map(morphology_dir: Path, out_path: Path, max_points: int = 120000) -> dict[str, int]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path = morphology_dir / "blob_shape_class_by_blob.csv"
    cols = ["ShapeClass", "ShapeValid", "Area_px", "ProjectedSphericity2D", "ProjectedRoughness_boundary"]
    data = pd.read_csv(path, usecols=cols)
    data["ShapeValid"] = data["ShapeValid"].astype(str).str.lower().isin({"true", "1", "yes"})
    valid = data[data["ShapeValid"]].dropna(subset=["ProjectedSphericity2D", "ProjectedRoughness_boundary", "Area_px"])
    if len(valid) > max_points:
        valid = valid.sample(n=max_points, random_state=21)

    fig, ax = plt.subplots(figsize=(7.8, 6.2))
    for cls in CLASS_ORDER:
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


def build_atlas_montage(morphology_dir: Path, out_path: Path) -> dict[str, object]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.image as mpimg

    manifest_path = morphology_dir / "representative_blob_atlas" / "representative_blob_atlas_manifest.csv"
    atlas = _read_csv(manifest_path)
    atlas = atlas[atlas["Status"].astype(str).eq("RENDERED")].copy()
    preferred = []
    for cls in ["compact_round", "elongated", "branched_complex", "ambiguous_valid"]:
        candidates = atlas[atlas["ShapeClass"] == cls]
        if candidates.empty:
            continue
        medoid = candidates[candidates["ExemplarType"] == "class_medoid"]
        preferred.append((medoid.iloc[0] if not medoid.empty else candidates.iloc[0]).to_dict())
    qc = atlas[atlas["ShapeClass"] == "small_unclassified"]
    if not qc.empty:
        preferred.append(qc.iloc[0].to_dict())

    n = len(preferred)
    if n == 0:
        raise ValueError("No rendered atlas panels found")
    fig, axes = plt.subplots(1, n, figsize=(3.2 * n, 3.4))
    if n == 1:
        axes = [axes]
    for ax, row in zip(axes, preferred):
        image = mpimg.imread(row["PanelPath"])
        ax.imshow(image)
        ax.set_axis_off()
        ax.set_title(str(row["ShapeClass"]), fontsize=10)
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


def write_caption_bank(path: Path, figure_records: dict[str, object]) -> None:
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
        "All captions describe projected 2D blob morphology. Do not use these figures to claim tracking, split/merge lineage, boundary fractal dimension, 3D roughness, true fluid-fluid interfacial area, or Wadell roundness.",
        "",
        "## Fig_BlobShapeClassFractions",
        "",
        "G21 projected blob shape-class composition across the full-duration morphology data product. Count fractions and projected-area fractions are shown separately because small objects dominate counts but not projected area.",
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


def build_figure_package(morphology_dir: Path, statistics_dir: Path, output_dir: Path) -> dict[str, object]:
    _safe_output_dir(output_dir)
    class_summary = _read_csv(statistics_dir / "blob_structure_class_summary.csv")
    transition = _read_csv(statistics_dir / "blob_structure_transition_by_sn_stage.csv")

    figure_records: dict[str, object] = {}
    class_path = output_dir / "Fig_BlobShapeClassFractions.png"
    plot_class_fractions(class_summary, class_path)
    figure_records["Fig_BlobShapeClassFractions.png"] = {"path": str(class_path)}

    stage_path = output_dir / "Fig_ShapeClassBySnStage.png"
    plot_stage_area_fractions(transition, stage_path)
    figure_records["Fig_ShapeClassBySnStage.png"] = {"path": str(stage_path)}

    map_path = output_dir / "Fig_BlobShapeMap_Sphericity_Roughness.png"
    figure_records["Fig_BlobShapeMap_Sphericity_Roughness.png"] = {
        "path": str(map_path),
        **plot_shape_map(morphology_dir, map_path),
    }

    atlas_path = output_dir / "Fig_RepresentativeBlobAtlas.png"
    figure_records["Fig_RepresentativeBlobAtlas.png"] = {
        "path": str(atlas_path),
        **build_atlas_montage(morphology_dir, atlas_path),
    }

    for copied in copy_existing_metric_figure(statistics_dir, output_dir):
        figure_records[Path(copied).name] = {"path": copied, "source": "statistics_package"}

    write_caption_bank(output_dir / "figure_caption_bank.md", figure_records)
    manifest = {
        "schema_version": "1.0",
        "created_at_utc": _utc_now(),
        "morphology_dir": str(morphology_dir),
        "statistics_dir": str(statistics_dir),
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
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    out = args.output_dir or args.statistics_dir / f"g21_blob_structure_figure_package_{_timestamp()}"
    manifest = build_figure_package(args.morphology_dir, args.statistics_dir, out)
    print(json.dumps({"output_dir": manifest["output_dir"], "figures": list(manifest["figures"].keys())}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
