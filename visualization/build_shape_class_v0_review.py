"""Review G21 shape-class v0 quality without changing class assignments.

This script diagnoses the large `ambiguous_valid` class and suggests whether a
future v1 refinement is warranted. It reads existing morphology outputs only.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


METRICS = [
    "Area_px",
    "ProjectedSphericity2D",
    "AxisAspectRatio",
    "Solidity2D",
    "ProjectedRoughness_boundary",
    "PtotalOverPouter",
    "ProjectedRegularity2D",
]

SUBCLASS_RULES = {
    "near_compact_round": "high projected compactness and solidity, but below v0 compact_round gate",
    "moderately_elongated": "axis ratio above q75 but below v0 elongated q90 gate",
    "moderately_concave": "solidity between q25 and q50",
    "moderate_boundary_complex": "roughness between q75 and q90",
    "smooth_irregular": "moderate metrics with no single dominant extreme",
}


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_output_dir(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise FileExistsError(f"Output directory exists and is not empty: {path}")
    path.mkdir(parents=True, exist_ok=True)


def _read_thresholds(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing thresholds JSON: {path}")
    return json.loads(path.read_text(encoding="utf-8"))["thresholds"]


def _threshold(thresholds: dict, metric: str, q: str) -> float:
    return float(thresholds[metric][q])


def _quantile_summary(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for metric in METRICS:
        values = pd.to_numeric(df[metric], errors="coerce").dropna()
        rows.append(
            {
                "Metric": metric,
                "N": int(values.count()),
                "q10": float(values.quantile(0.10)),
                "q25": float(values.quantile(0.25)),
                "q50": float(values.quantile(0.50)),
                "q75": float(values.quantile(0.75)),
                "q90": float(values.quantile(0.90)),
            }
        )
    return pd.DataFrame(rows)


def _assign_candidate_subclass(df: pd.DataFrame, thresholds: dict) -> pd.Series:
    axis = pd.to_numeric(df["AxisAspectRatio"], errors="coerce")
    sph = pd.to_numeric(df["ProjectedSphericity2D"], errors="coerce")
    sol = pd.to_numeric(df["Solidity2D"], errors="coerce")
    rough = pd.to_numeric(df["ProjectedRoughness_boundary"], errors="coerce")

    subclass = pd.Series("smooth_irregular", index=df.index, dtype="object")
    near_compact = (
        (sph >= _threshold(thresholds, "ProjectedSphericity2D", "q50"))
        & (sol >= _threshold(thresholds, "Solidity2D", "q50"))
        & (axis < _threshold(thresholds, "AxisAspectRatio", "q75"))
    )
    moderate_elongated = (
        (axis >= _threshold(thresholds, "AxisAspectRatio", "q75"))
        & (axis < _threshold(thresholds, "AxisAspectRatio", "q90"))
    )
    moderate_concave = (
        (sol >= _threshold(thresholds, "Solidity2D", "q25"))
        & (sol < _threshold(thresholds, "Solidity2D", "q50"))
        & ~moderate_elongated
    )
    moderate_boundary = (
        (rough >= _threshold(thresholds, "ProjectedRoughness_boundary", "q75"))
        & (rough < _threshold(thresholds, "ProjectedRoughness_boundary", "q90"))
        & ~moderate_elongated
        & ~moderate_concave
    )

    subclass.loc[near_compact] = "near_compact_round"
    subclass.loc[moderate_elongated] = "moderately_elongated"
    subclass.loc[moderate_concave] = "moderately_concave"
    subclass.loc[moderate_boundary] = "moderate_boundary_complex"
    return subclass


def _subclass_summary(ambiguous: pd.DataFrame, thresholds: dict) -> pd.DataFrame:
    working = ambiguous.copy()
    working["CandidateSubclass"] = _assign_candidate_subclass(working, thresholds)
    total_n = len(working)
    total_area = float(pd.to_numeric(working["Area_px"], errors="coerce").sum())
    rows = []
    for subclass, group in working.groupby("CandidateSubclass", sort=False):
        area = pd.to_numeric(group["Area_px"], errors="coerce")
        rows.append(
            {
                "CandidateSubclass": subclass,
                "RuleDescription": SUBCLASS_RULES.get(subclass, ""),
                "N": int(len(group)),
                "CountFractionOfAmbiguous": float(len(group) / total_n) if total_n else np.nan,
                "AreaSum_px": float(area.sum()),
                "AreaFractionOfAmbiguous": float(area.sum() / total_area) if total_area else np.nan,
                "MedianArea_px": float(area.median()),
                "MedianProjectedSphericity2D": float(pd.to_numeric(group["ProjectedSphericity2D"], errors="coerce").median()),
                "MedianAxisAspectRatio": float(pd.to_numeric(group["AxisAspectRatio"], errors="coerce").median()),
                "MedianSolidity2D": float(pd.to_numeric(group["Solidity2D"], errors="coerce").median()),
                "MedianProjectedRoughnessBoundary": float(pd.to_numeric(group["ProjectedRoughness_boundary"], errors="coerce").median()),
            }
        )
    return pd.DataFrame(rows).sort_values("AreaFractionOfAmbiguous", ascending=False)


def _representatives(ambiguous: pd.DataFrame, thresholds: dict) -> pd.DataFrame:
    working = ambiguous.copy()
    working["CandidateSubclass"] = _assign_candidate_subclass(working, thresholds)
    rows = []
    for subclass, group in working.groupby("CandidateSubclass", sort=False):
        metrics = group[["ProjectedSphericity2D", "AxisAspectRatio", "Solidity2D", "ProjectedRoughness_boundary"]].apply(
            pd.to_numeric, errors="coerce"
        )
        center = metrics.median()
        distance = ((metrics - center) / metrics.std(ddof=0).replace(0, np.nan)).pow(2).sum(axis=1)
        medoid = group.loc[distance.idxmin()].copy()
        medoid["ExemplarType"] = "candidate_subclass_medoid"
        rows.append(medoid)
        largest = group.loc[pd.to_numeric(group["Area_px"], errors="coerce").idxmax()].copy()
        largest["ExemplarType"] = "candidate_subclass_largest_area"
        rows.append(largest)
    columns = [
        "CandidateSubclass",
        "ExemplarType",
        "FrameIndex",
        "BlobID",
        "Area_px",
        "ProjectedSphericity2D",
        "AxisAspectRatio",
        "Solidity2D",
        "ProjectedRoughness_boundary",
        "PtotalOverPouter",
        "MaskPath",
        "LabelPath",
    ]
    return pd.DataFrame(rows)[columns]


def _write_review_md(path: Path, total_rows: int, ambiguous_rows: int, subclass_summary: pd.DataFrame) -> None:
    ambiguous_fraction = ambiguous_rows / total_rows if total_rows else np.nan
    largest = subclass_summary.iloc[0] if not subclass_summary.empty else None
    recommendation = "RECOMMEND_SHAPE_CLASS_V1_REFINEMENT" if ambiguous_fraction > 0.20 else "KEEP_V0_CLASSES"
    if largest is not None and float(largest["AreaFractionOfAmbiguous"]) > 0.70:
        recommendation = "KEEP_V0_CLASSES_REVIEW_THRESHOLD_ONLY"
    lines = [
        "# G21 Shape-Class V0 Review",
        "",
        f"Total shape rows: {total_rows:,}",
        f"`ambiguous_valid` rows: {ambiguous_rows:,} ({100 * ambiguous_fraction:.1f}% of all rows)",
        "",
        f"Decision: `{recommendation}`",
        "",
        "## Rationale",
        "",
        "`ambiguous_valid` is a valid geometry fallback class. It is not a QC failure. A large ambiguous fraction means many blobs sit between the current extreme gates for compact-round, elongated, and branched-complex classes.",
        "",
        "Candidate subclasses below are diagnostic only. They are not applied to the official morphology product until a v1 rule change is explicitly approved.",
        "",
        "## Candidate Subclasses",
        "",
        subclass_summary.to_markdown(index=False),
        "",
        "## Scope Limits",
        "",
        "- Do not treat candidate subclasses as final labels yet.",
        "- Do not infer split/merge, tracking, fractal dimension, 3D roughness, or true interfacial area.",
        "- Use this review only to decide whether shape-class v1 refinement is worth implementing.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_shape_class_v0_review(morphology_dir: Path, output_dir: Path) -> dict:
    _safe_output_dir(output_dir)
    shape_path = morphology_dir / "blob_shape_class_by_blob.csv"
    if not shape_path.exists():
        raise FileNotFoundError(f"Missing shape-class table: {shape_path}")
    thresholds = _read_thresholds(morphology_dir / "blob_morphology_thresholds.json")
    usecols = [
        "FrameIndex",
        "BlobID",
        "ShapeClass",
        "Area_px",
        "ProjectedSphericity2D",
        "AxisAspectRatio",
        "Solidity2D",
        "ProjectedRoughness_boundary",
        "PtotalOverPouter",
        "ProjectedRegularity2D",
        "MaskPath",
        "LabelPath",
    ]
    shape = pd.read_csv(shape_path, usecols=usecols)
    ambiguous = shape[shape["ShapeClass"].astype(str).eq("ambiguous_valid")].copy()
    quantiles = _quantile_summary(ambiguous)
    subclass_summary = _subclass_summary(ambiguous, thresholds)
    reps = _representatives(ambiguous, thresholds)

    quantiles.to_csv(output_dir / "ambiguous_valid_diagnostic.csv", index=False)
    subclass_summary.to_csv(output_dir / "ambiguous_valid_candidate_subclasses.csv", index=False)
    reps.to_csv(output_dir / "ambiguous_valid_representatives.csv", index=False)
    _write_review_md(output_dir / "shape_class_v0_review.md", len(shape), len(ambiguous), subclass_summary)

    manifest = {
        "schema_version": "1.0",
        "created_at_utc": _utc_now(),
        "morphology_dir": str(morphology_dir),
        "output_dir": str(output_dir),
        "row_counts": {
            "shape_rows": int(len(shape)),
            "ambiguous_valid_rows": int(len(ambiguous)),
        },
        "outputs": [
            "ambiguous_valid_diagnostic.csv",
            "ambiguous_valid_candidate_subclasses.csv",
            "ambiguous_valid_representatives.csv",
            "shape_class_v0_review.md",
            "shape_class_v0_review_manifest.json",
        ],
        "scope": {
            "review_only": True,
            "changes_official_shape_classes": False,
            "tracking": False,
            "fractal": False,
            "roughness_3d": False,
            "true_fluid_fluid_interfacial_area": False,
        },
    }
    (output_dir / "shape_class_v0_review_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review G21 shape-class v0 ambiguous_valid population.")
    parser.add_argument("--morphology-dir", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    out = args.output_dir or args.morphology_dir / f"g21_shape_class_v0_review_{_timestamp()}"
    manifest = build_shape_class_v0_review(args.morphology_dir, out)
    print(json.dumps({"output_dir": manifest["output_dir"], "row_counts": manifest["row_counts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
