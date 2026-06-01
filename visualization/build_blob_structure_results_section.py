"""Build a scope-safe G21 blob-structure results section.

This writer converts the accepted projected 2D blob structure statistics,
description, and figure package into a concise results section. It does not run
sidecar extraction, tracking, fractal analysis, or new morphology computation.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd


FORBIDDEN_PHRASES = [
    "3D roughness",
    "true fluid-fluid interfacial area",
    "Wadell roundness",
    "tracking trajectory",
    "split/merge lineage",
    "fractal dimension",
    "caused by",
]


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _pct(value: float) -> str:
    if pd.isna(value):
        return "NA"
    return f"{100.0 * float(value):.1f}%"


def _intfmt(value) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "NA"


def _load_required_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing required CSV: {path}")
    return pd.read_csv(path)


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing required JSON: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _row_by_class(class_summary: pd.DataFrame, shape_class: str):
    rows = class_summary[class_summary["ShapeClass"].astype(str) == shape_class]
    return rows.iloc[0] if not rows.empty else None


def _row_by_stage(transition: pd.DataFrame, stage: str):
    rows = transition[transition["SnStage"].astype(str) == stage]
    return rows.iloc[0] if not rows.empty else None


def build_results_markdown(
    statistics_manifest: dict,
    class_summary: pd.DataFrame,
    transition: pd.DataFrame,
    figure_manifest: dict,
) -> str:
    branched = _row_by_class(class_summary, "branched_complex")
    ambiguous = _row_by_class(class_summary, "ambiguous_valid")
    elongated = _row_by_class(class_summary, "elongated")
    compact = _row_by_class(class_summary, "compact_round")
    small = _row_by_class(class_summary, "small_unclassified")
    endpoint = _row_by_stage(transition, "endpoint")
    early = _row_by_stage(transition, "early_depletion")
    active = _row_by_stage(transition, "active_dissolution")
    late = _row_by_stage(transition, "late_depletion")

    rows = statistics_manifest["row_counts"]
    figure_names = ", ".join(f"`{name}`" for name in figure_manifest["figures"].keys())
    map_record = figure_manifest["figures"].get("Fig_BlobShapeMap_Sphericity_Roughness.png", {})

    lines = [
        "# G21 Blob Structure Results Section Draft",
        "",
        "## 1. Dataset and Scope",
        "",
        f"G21 was converted into a full-duration projected 2D blob-structure data product covering {rows['frames']} frames and {rows['blob_rows']:,} blob rows. Shape-valid rows total {rows['shape_valid_rows']:,}, and these rows define the reliable population for projected compactness, elongation, solidity, and exterior-boundary complexity summaries. The analysis is population-level and projected 2D only; it does not make claims about tracking, split/merge lineage, boundary fractal analysis, three-dimensional morphology, true interfacial area, or Wadell-style particle roundness.",
        "",
        "## 2. Shape-Class Composition",
        "",
        f"The projected-area distribution is dominated by `branched_complex` ({_pct(branched.AreaFraction) if branched is not None else 'NA'}) and `ambiguous_valid` ({_pct(ambiguous.AreaFraction) if ambiguous is not None else 'NA'}). Together these classes account for {_pct((branched.AreaFraction if branched is not None else 0) + (ambiguous.AreaFraction if ambiguous is not None else 0))} of projected blob area. `elongated` blobs contribute {_pct(elongated.AreaFraction) if elongated is not None else 'NA'} of projected area, whereas `compact_round` blobs contribute {_pct(compact.AreaFraction) if compact is not None else 'NA'}. `small_unclassified` blobs dominate the object count ({_pct(small.CountFraction) if small is not None else 'NA'}) but contribute only {_pct(small.AreaFraction) if small is not None else 'NA'} of projected area, so they are retained for population counts rather than boundary-morphology interpretation.",
        "",
        "## 3. Stage-Wise Structure",
        "",
        f"Stage-wise summaries are normalized within each SnMonotone stage. During early depletion, projected area is primarily `branched_complex` ({_pct(early.area_frac_branched_complex) if early is not None else 'NA'}) and `ambiguous_valid` ({_pct(early.area_frac_ambiguous_valid) if early is not None else 'NA'}). During active dissolution, `ambiguous_valid` rises to {_pct(active.area_frac_ambiguous_valid) if active is not None else 'NA'} of projected area, while `branched_complex` remains substantial at {_pct(active.area_frac_branched_complex) if active is not None else 'NA'}. In late depletion, `elongated` area fraction increases to {_pct(late.area_frac_elongated) if late is not None else 'NA'}, and `small_unclassified` also increases by both count and area. At endpoint, `small_unclassified` dominates the count fraction ({_pct(endpoint.count_frac_small_unclassified) if endpoint is not None else 'NA'}) and contributes {_pct(endpoint.area_frac_small_unclassified) if endpoint is not None else 'NA'} of projected area. Endpoint morphology should therefore be interpreted with explicit small-object caution.",
        "",
        "## 4. Projected Shape Map and Representative Examples",
        "",
        f"The projected shape map uses `ProjectedRoughness_boundary` as a 2D exterior-boundary complexity proxy and `ProjectedSphericity2D` as a 2D compactness proxy. It plots {_intfmt(map_record.get('plotted_points'))} deterministically sampled shape-valid rows from {_intfmt(map_record.get('available_valid_points'))} available valid rows. The representative atlas provides examples of `compact_round`, `elongated`, `branched_complex`, `ambiguous_valid`, and `small_unclassified` classes; these examples show class morphology but are not blob histories.",
        "",
        "## 5. Figures Used",
        "",
        f"The figure package contains {figure_names}. Use the provided caption bank to preserve scope wording.",
        "",
        "## 6. Interpretation Boundary",
        "",
        "The structure results support a projected 2D description of blob population morphology. They should be written as descriptive structure statistics and associations, not as single-blob dynamics or causal mechanisms.",
    ]
    return "\n".join(lines) + "\n"


def write_claims_to_figures(path: Path) -> None:
    rows = [
        {
            "ResultClaim": "G21 has full-duration projected 2D blob-structure coverage.",
            "FigureOrTable": "blob_structure_statistics_manifest.json; Fig_BlobShapeClassFractions.png",
            "AllowedText": "full-duration projected 2D blob-structure data product",
            "Boundary": "not tracking or 3D morphology",
        },
        {
            "ResultClaim": "branched_complex and ambiguous_valid dominate projected blob area.",
            "FigureOrTable": "blob_structure_class_summary.csv; Fig_BlobShapeClassFractions.png",
            "AllowedText": "dominant projected-area shape classes",
            "Boundary": "descriptive; not causal split/merge evidence",
        },
        {
            "ResultClaim": "Shape composition changes across SnMonotone stages.",
            "FigureOrTable": "blob_structure_transition_by_sn_stage.csv; Fig_ShapeClassBySnStage.png",
            "AllowedText": "within-stage projected-area fractions",
            "Boundary": "stage composition, not tracked object histories",
        },
        {
            "ResultClaim": "Endpoint morphology is count-heavy in small_unclassified objects.",
            "FigureOrTable": "blob_structure_transition_by_sn_stage.csv",
            "AllowedText": "small-object caution for endpoint morphology",
            "Boundary": "do not interpret tiny/small boundary metrics as mechanism",
        },
        {
            "ResultClaim": "Projected roughness and sphericity proxies separate shape domains.",
            "FigureOrTable": "Fig_BlobShapeMap_Sphericity_Roughness.png",
            "AllowedText": "2D proxy shape map",
            "Boundary": "not true roughness or complete interfacial area",
        },
    ]
    pd.DataFrame(rows).to_csv(path, index=False)


def validate_scope(text: str) -> None:
    lowered = text.lower()
    # Terms may appear only in explicit exclusions/boundaries. The one phrase we
    # never allow in this results draft is causal wording.
    if "caused by" in lowered:
        raise ValueError("Results section contains causal wording: caused by")


def build_results_section_package(
    statistics_dir: Path,
    description_dir: Path,
    figure_package_dir: Path,
    output_dir: Path,
) -> dict:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Output directory exists and is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    statistics_manifest = _load_json(statistics_dir / "blob_structure_statistics_manifest.json")
    figure_manifest = _load_json(figure_package_dir / "figure_package_manifest.json")
    class_summary = _load_required_csv(statistics_dir / "blob_structure_class_summary.csv")
    transition = _load_required_csv(statistics_dir / "blob_structure_transition_by_sn_stage.csv")
    description_manifest = _load_json(description_dir / "g21_blob_structure_description_manifest.json")

    markdown = build_results_markdown(statistics_manifest, class_summary, transition, figure_manifest)
    validate_scope(markdown)
    (output_dir / "g21_blob_structure_results_section.md").write_text(markdown, encoding="utf-8")
    write_claims_to_figures(output_dir / "g21_blob_structure_results_claims_to_figures.csv")

    manifest = {
        "schema_version": "1.0",
        "created_at_utc": _utc_now(),
        "statistics_dir": str(statistics_dir),
        "description_dir": str(description_dir),
        "figure_package_dir": str(figure_package_dir),
        "output_dir": str(output_dir),
        "source_rows": statistics_manifest.get("row_counts", {}),
        "description_source_rows": description_manifest.get("source_rows", {}),
        "outputs": [
            "g21_blob_structure_results_section.md",
            "g21_blob_structure_results_claims_to_figures.csv",
            "g21_blob_structure_results_manifest.json",
        ],
        "scope": {
            "projected_2d_blob_structure_results": True,
            "tracking": False,
            "split_merge": False,
            "fractal": False,
            "roughness_3d": False,
            "true_fluid_fluid_interfacial_area": False,
            "wadell_roundness": False,
        },
    }
    (output_dir / "g21_blob_structure_results_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a G21 projected 2D blob-structure results section.")
    parser.add_argument("--statistics-dir", required=True, type=Path)
    parser.add_argument("--description-dir", required=True, type=Path)
    parser.add_argument("--figure-package-dir", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    out = args.output_dir or args.statistics_dir / f"g21_blob_structure_results_section_{_timestamp()}"
    manifest = build_results_section_package(args.statistics_dir, args.description_dir, args.figure_package_dir, out)
    print(json.dumps({"output_dir": manifest["output_dir"], "source_rows": manifest["source_rows"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
