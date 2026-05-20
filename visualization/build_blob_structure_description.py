"""Build a scope-safe G21 blob structure description package.

The input is the projected 2D blob structure statistics package. The output is
a compact set of narrative and claim-mapping files for results drafting. This
script does not run sidecar extraction or compute new geometry.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd


FORBIDDEN_RESULT_CLAIMS = [
    "full-duration 3D roughness",
    "true fluid-fluid interfacial area",
    "Wadell roundness",
    "tracking trajectory",
    "split/merge lineage",
    "boundary fractal dimension",
    "causal mechanism",
]


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _pct(value: float) -> str:
    if pd.isna(value):
        return "NA"
    return f"{100.0 * float(value):.1f}%"


def _fmt(value: float) -> str:
    if pd.isna(value):
        return "NA"
    return f"{float(value):.3g}"


def load_inputs(stats_dir: Path) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    manifest_path = stats_dir / "blob_structure_statistics_manifest.json"
    class_path = stats_dir / "blob_structure_class_summary.csv"
    transition_path = stats_dir / "blob_structure_transition_by_sn_stage.csv"
    for path in [manifest_path, class_path, transition_path]:
        if not path.exists():
            raise FileNotFoundError(f"Missing required statistics file: {path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    class_summary = pd.read_csv(class_path)
    transition = pd.read_csv(transition_path)
    return manifest, class_summary, transition


def write_description(path: Path, manifest: dict, class_summary: pd.DataFrame, transition: pd.DataFrame) -> None:
    rows = {str(row.ShapeClass): row for row in class_summary.itertuples(index=False)}
    small = rows.get("small_unclassified")
    ambiguous = rows.get("ambiguous_valid")
    branched = rows.get("branched_complex")
    elongated = rows.get("elongated")
    compact = rows.get("compact_round")

    endpoint = transition.loc[transition["SnStage"] == "endpoint"]
    endpoint_row = endpoint.iloc[0] if not endpoint.empty else None

    lines = [
        "# G21 Blob Structure Description",
        "",
        "## Scope",
        "",
        "This description uses the full-duration projected 2D blob morphology data product and the derived blob structure statistics package. It describes population-level projected blob structure. It does not describe tracking trajectories, split/merge lineage, boundary fractal dimension, 3D roughness, true fluid-fluid interfacial area, or Wadell roundness.",
        "",
        "## Metric Interpretation",
        "",
        "`AxisAspectRatio` and `AspectRatio01` describe projected long/short axis shape. `ProjectedSphericity2D` is a projected compactness proxy, not 3D sphericity. `Circularity2D_boundary` is a 2D circularity diagnostic, not Wadell roundness. `Solidity2D` describes projected convexity/concavity. `ProjectedRoughness_boundary` is a 2D exterior-boundary complexity proxy. `PtotalOverPouter` is a projected internal-boundary diagnostic.",
        "",
        "## Dataset Coverage",
        "",
        f"The structure package covers {manifest['row_counts']['frames']} frames and {manifest['row_counts']['blob_rows']:,} blob rows. Shape-valid and boundary-interpretable rows both total {manifest['row_counts']['shape_valid_rows']:,}.",
        "",
        "## Population Structure",
        "",
    ]

    if branched is not None and ambiguous is not None:
        lines.append(
            f"By projected area, `branched_complex` contributes {_pct(branched.AreaFraction)} and `ambiguous_valid` contributes {_pct(ambiguous.AreaFraction)} of the blob population. These two classes therefore dominate reliable projected blob area, while `small_unclassified` contributes {_pct(small.AreaFraction) if small is not None else 'NA'} of area but {_pct(small.CountFraction) if small is not None else 'NA'} of blob count."
        )
        lines.append("")
    if elongated is not None and compact is not None:
        lines.append(
            f"`elongated` blobs account for {_pct(elongated.AreaFraction)} of area and {_pct(elongated.CountFraction)} of count, whereas `compact_round` blobs account for {_pct(compact.AreaFraction)} of area and {_pct(compact.CountFraction)} of count. Compact-round projected shapes are therefore present but not area-dominant."
        )
        lines.append("")

    lines += [
        "## Stage Pattern",
        "",
        "The stage table reports within-stage fractions, so each stage sums to one by count and by area.",
        "",
    ]
    for row in transition.itertuples(index=False):
        lines.append(
            f"- `{row.SnStage}`: {int(row.NFrames)} frames, {int(row.NBlobs):,} blobs. Area fractions: branched_complex {_pct(getattr(row, 'area_frac_branched_complex', float('nan')))}, ambiguous_valid {_pct(getattr(row, 'area_frac_ambiguous_valid', float('nan')))}, elongated {_pct(getattr(row, 'area_frac_elongated', float('nan')))}, compact_round {_pct(getattr(row, 'area_frac_compact_round', float('nan')))}, small_unclassified {_pct(getattr(row, 'area_frac_small_unclassified', float('nan')))}."
        )

    lines += [
        "",
        "## Endpoint Caution",
        "",
    ]
    if endpoint_row is not None:
        lines.append(
            f"At endpoint, `small_unclassified` dominates the count fraction ({_pct(endpoint_row.count_frac_small_unclassified)}) and contributes {_pct(endpoint_row.area_frac_small_unclassified)} of projected area. Endpoint morphology should therefore be interpreted as count-heavy in tiny/small objects, with boundary metrics restricted to shape-valid reliable tiers."
        )
    else:
        lines.append("Endpoint stage rows were not found in the transition table.")

    lines += [
        "",
        "## Allowed Claims",
        "",
        "- G21 has a full-duration projected 2D blob structure data product.",
        "- Shape-valid rows can support projected compactness, elongation, solidity, and exterior-boundary complexity summaries.",
        "- `branched_complex` and `ambiguous_valid` are the dominant reliable projected-area classes.",
        "- Late and endpoint stages require caution because small objects become count-dominant.",
        "",
        "## Explicit Exclusions",
        "",
    ]
    for claim in FORBIDDEN_RESULT_CLAIMS:
        lines.append(f"- Do not claim {claim}.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_claim_table(path: Path) -> None:
    rows = [
        {
            "Claim": "G21 has full-duration projected 2D blob structure coverage.",
            "AllowedStrength": "strong",
            "EvidenceFile": "blob_structure_statistics_manifest.json",
            "AllowedText": "full-duration projected 2D blob morphology",
            "Limitation": "not tracking or 3D morphology",
            "ForbiddenWording": "3D roughness; true fluid-fluid interfacial area",
        },
        {
            "Claim": "Reliable projected area is dominated by branched_complex and ambiguous_valid classes.",
            "AllowedStrength": "moderate",
            "EvidenceFile": "blob_structure_class_summary.csv",
            "AllowedText": "dominant projected-area shape classes",
            "Limitation": "descriptive association only",
            "ForbiddenWording": "causal breakup mechanism; split/merge lineage",
        },
        {
            "Claim": "Endpoint morphology is count-heavy in small_unclassified objects.",
            "AllowedStrength": "strong limitation",
            "EvidenceFile": "blob_structure_transition_by_sn_stage.csv",
            "AllowedText": "endpoint count is dominated by small_unclassified objects",
            "Limitation": "boundary metrics restricted to shape-valid reliable tiers",
            "ForbiddenWording": "endpoint boundary mechanism from tiny/small blobs",
        },
        {
            "Claim": "ProjectedRoughness_boundary can be used as a reliable-tier 2D exterior-boundary proxy.",
            "AllowedStrength": "supporting",
            "EvidenceFile": "blob_structure_metric_dictionary.md; blob_structure_class_summary.csv",
            "AllowedText": "2D exterior-boundary complexity proxy",
            "Limitation": "not complete interfacial area",
            "ForbiddenWording": "true roughness; 3D roughness; full NAPL-water interface",
        },
    ]
    pd.DataFrame(rows).to_csv(path, index=False)


def write_figure_notes(path: Path, stats_dir: Path) -> None:
    lines = [
        "# G21 Blob Structure Figure Notes",
        "",
        "Use these figures as descriptive summaries of projected 2D morphology. Do not caption them as tracking, fractal, 3D roughness, or full interfacial-area results.",
        "",
        "| Figure | Suggested caption boundary |",
        "|---|---|",
        "| `shape_class_count_area_fractions.png` | Count and projected-area fractions by shape class; small objects are count-only, not boundary-mechanism evidence. |",
        "| `shape_class_area_fraction_by_sn_stage.png` | Within-stage projected-area fractions by SnMonotone stage; stage fractions sum to one. |",
        "| `valid_metric_distributions_by_shape_class.png` | Shape-valid projected 2D metrics by class; metrics are proxies, not Wadell roundness or 3D morphology. |",
        "",
        f"Figure directory: `{stats_dir / 'figures_blob_structure'}`",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_description_package(stats_dir: Path, output_dir: Path) -> dict:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Output directory exists and is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest, class_summary, transition = load_inputs(stats_dir)
    write_description(output_dir / "g21_blob_structure_description.md", manifest, class_summary, transition)
    write_claim_table(output_dir / "g21_blob_structure_claims_table.csv")
    write_figure_notes(output_dir / "g21_blob_structure_figure_notes.md", stats_dir)
    package_manifest = {
        "schema_version": "1.0",
        "created_at_utc": _utc_now(),
        "statistics_dir": str(stats_dir),
        "output_dir": str(output_dir),
        "source_rows": manifest.get("row_counts", {}),
        "outputs": [
            "g21_blob_structure_description.md",
            "g21_blob_structure_claims_table.csv",
            "g21_blob_structure_figure_notes.md",
            "g21_blob_structure_description_manifest.json",
        ],
        "scope": {
            "projected_2d_blob_structure_description": True,
            "tracking": False,
            "split_merge": False,
            "fractal": False,
            "roughness_3d": False,
            "true_fluid_fluid_interfacial_area": False,
        },
    }
    (output_dir / "g21_blob_structure_description_manifest.json").write_text(
        json.dumps(package_manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return package_manifest


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a G21 blob structure description package from statistics.")
    parser.add_argument("--statistics-dir", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    out = args.output_dir or args.statistics_dir / f"g21_blob_structure_description_{_timestamp()}"
    manifest = build_description_package(args.statistics_dir, out)
    print(json.dumps({"output_dir": manifest["output_dir"], "source_rows": manifest["source_rows"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
