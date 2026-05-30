"""Segment visually red DNAPL from illumination-corrected preview RGB.

This Branch A tool is deliberately segmentation-only. It may use contrast and
2x preview images, but it does not compute endpoint-normalized saturation.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Iterable

import cv2
import numpy as np
from skimage import color

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import tune_light_field as tlf
import audit_reference_scores as audit


Array = np.ndarray


@dataclass(frozen=True)
class SegmentationResult:
    mask: Array
    score: Array
    diagnostics: dict[str, object]


def score_preview_rgb(rgb: Array, score_mode: str) -> Array:
    """Compute a red-sensitive preview score without endpoint references."""
    rgb = np.asarray(rgb, dtype=np.float32)
    if rgb.ndim != 3 or rgb.shape[2] < 3:
        raise ValueError(f"Expected RGB image, got shape {rgb.shape}")
    rgb = np.clip(rgb[:, :, :3], 0.0, 1.0)
    r = rgb[:, :, 0]
    g = rgb[:, :, 1]
    b = rgb[:, :, 2]

    if score_mode == "excess_red":
        return r - 0.5 * (g + b)
    if score_mode == "normalized_red":
        return r / np.maximum(r + g + b, 1e-6)
    if score_mode == "lab_a":
        return color.rgb2lab(rgb)[:, :, 1]
    if score_mode == "chroma":
        lab = color.rgb2lab(rgb)
        return np.hypot(lab[:, :, 1], lab[:, :, 2])
    if score_mode == "hsv_red_pink":
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        hue = np.mod(hsv[:, :, 0], 360.0)
        sat = hsv[:, :, 1]
        val = hsv[:, :, 2]
        hue_distance = np.minimum(hue, 360.0 - hue)
        red_weight = np.clip(1.0 - hue_distance / 35.0, 0.0, 1.0)
        return red_weight * sat * val
    raise ValueError(f"Unsupported score mode: {score_mode}")


def component_diagnostics(mask: Array) -> dict[str, object]:
    """Return connected-component diagnostics for a binary mask."""
    mask = np.asarray(mask, dtype=bool)
    area = int(np.count_nonzero(mask))
    if area == 0:
        return {
            "component_count": 0,
            "largest_component_area_px": 0,
            "largest_component_fraction": 0.0,
        }

    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    component_areas = [int(stats[i, cv2.CC_STAT_AREA]) for i in range(1, num_labels)]
    largest = max(component_areas) if component_areas else 0
    return {
        "component_count": len(component_areas),
        "largest_component_area_px": largest,
        "largest_component_fraction": float(largest / area) if area else 0.0,
    }


def remove_small_components(mask: Array, min_area_px: int) -> Array:
    """Remove connected components smaller than min_area_px."""
    mask = np.asarray(mask, dtype=bool)
    if min_area_px <= 1 or not np.any(mask):
        return mask
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    keep = np.zeros_like(mask, dtype=bool)
    for label in range(1, num_labels):
        if int(stats[label, cv2.CC_STAT_AREA]) >= min_area_px:
            keep |= labels == label
    return keep


def hysteresis_mask(score: Array, domain_mask: Array, seed_threshold: float, candidate_threshold: float) -> Array:
    """Keep candidate connected components that contain at least one seed pixel."""
    candidate = (score >= candidate_threshold) & domain_mask
    seed = (score >= seed_threshold) & domain_mask
    if not np.any(candidate) or not np.any(seed):
        return np.zeros_like(domain_mask, dtype=bool)
    num_labels, labels, _, _ = cv2.connectedComponentsWithStats(candidate.astype(np.uint8), connectivity=8)
    keep_labels = set(np.unique(labels[seed]))
    keep_labels.discard(0)
    out = np.zeros_like(domain_mask, dtype=bool)
    for label in range(1, num_labels):
        if label in keep_labels:
            out |= labels == label
    return out


def threshold_sweep(score: Array, domain_mask: Array, thresholds: Iterable[float]) -> list[dict[str, object]]:
    """Evaluate red-mask stability across thresholds."""
    domain_mask = np.asarray(domain_mask, dtype=bool)
    domain_area = int(np.count_nonzero(domain_mask))
    rows: list[dict[str, object]] = []
    for threshold in thresholds:
        mask = (score >= threshold) & domain_mask
        diagnostics = component_diagnostics(mask)
        rows.append(
            {
                "threshold": float(threshold),
                "mask_area_px": int(np.count_nonzero(mask)),
                "mask_area_fraction": float(np.count_nonzero(mask) / max(domain_area, 1)),
                **diagnostics,
            }
        )
    return rows


def score_quantiles(score: Array, mask: Array) -> dict[str, float]:
    values = np.asarray(score[mask], dtype=np.float32)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return {"red_score_p05": float("nan"), "red_score_p50": float("nan"), "red_score_p95": float("nan")}
    return {
        "red_score_p05": float(np.percentile(values, 5)),
        "red_score_p50": float(np.percentile(values, 50)),
        "red_score_p95": float(np.percentile(values, 95)),
    }


def segment_red_napl(
    rgb: Array,
    *,
    domain_mask: Array | None = None,
    core_mask: Array | None = None,
    score_mode: str = "lab_a",
    threshold: float | None = None,
    threshold_percentile: float = 95.0,
    seed_threshold: float | None = None,
    candidate_threshold: float | None = None,
    min_area_px: int = 0,
) -> SegmentationResult:
    """Segment red DNAPL for Branch A preview-mask extraction."""
    score = score_preview_rgb(rgb, score_mode)
    if domain_mask is None:
        domain_mask = np.ones(score.shape, dtype=bool)
    else:
        domain_mask = np.asarray(domain_mask, dtype=bool)
    if domain_mask.shape != score.shape:
        raise ValueError("domain_mask must match RGB height/width")

    domain_area = int(np.count_nonzero(domain_mask))
    values = score[domain_mask]
    if threshold is None:
        threshold = float(np.percentile(values, threshold_percentile))

    seed_fraction = float("nan")
    candidate_fraction = float("nan")
    growth_ratio = float("nan")
    if seed_threshold is not None or candidate_threshold is not None:
        if seed_threshold is None or candidate_threshold is None:
            raise ValueError("seed_threshold and candidate_threshold must be provided together")
        seed = (score >= seed_threshold) & domain_mask
        candidate = (score >= candidate_threshold) & domain_mask
        mask = hysteresis_mask(score, domain_mask, seed_threshold, candidate_threshold)
        seed_fraction = float(np.count_nonzero(seed) / max(domain_area, 1))
        candidate_fraction = float(np.count_nonzero(candidate) / max(domain_area, 1))
    else:
        mask = (score >= threshold) & domain_mask

    mask = remove_small_components(mask, min_area_px)
    final_fraction = float(np.count_nonzero(mask) / max(domain_area, 1))
    if np.isfinite(seed_fraction) and seed_fraction > 0:
        growth_ratio = final_fraction / seed_fraction

    diagnostics: dict[str, object] = {
        "segmentation_output": "segmentation_mask",
        "endpoint_dependency": "none",
        "score_mode": score_mode,
        "threshold": float(threshold),
        "threshold_percentile": float(threshold_percentile),
        "domain_area_px": domain_area,
        "red_mask_area_px": int(np.count_nonzero(mask)),
        "red_mask_area_fraction": final_fraction,
        "seed_fraction": seed_fraction,
        "candidate_fraction": candidate_fraction,
        "growth_ratio": growth_ratio,
        "final_from_hsv_only_fraction": final_fraction if score_mode == "hsv_red_pink" else 0.0,
    }
    diagnostics.update(component_diagnostics(mask))
    diagnostics.update(score_quantiles(score, domain_mask))

    if core_mask is not None:
        core_mask = np.asarray(core_mask, dtype=bool)
        if core_mask.shape != score.shape:
            raise ValueError("core_mask must match RGB height/width")
        edge_mask = domain_mask & ~core_mask
        diagnostics.update(
            {
                "core_flow_area_px": int(np.count_nonzero(core_mask)),
                "edge_band_area_px": int(np.count_nonzero(edge_mask)),
                "red_mask_area_fraction_core": float(
                    np.count_nonzero(mask & core_mask) / max(np.count_nonzero(core_mask), 1)
                ),
                "red_mask_area_fraction_edge": float(
                    np.count_nonzero(mask & edge_mask) / max(np.count_nonzero(edge_mask), 1)
                ),
            }
        )
    else:
        diagnostics.update(
            {
                "core_flow_area_px": 0,
                "edge_band_area_px": 0,
                "red_mask_area_fraction_core": float("nan"),
                "red_mask_area_fraction_edge": float("nan"),
            }
        )

    return SegmentationResult(mask=mask, score=score, diagnostics=diagnostics)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_outputs(
    out_dir: Path,
    label: str,
    rgb: Array,
    result: SegmentationResult,
    sweep_rows: list[dict[str, object]],
) -> None:
    """Write Branch A mask, overlay, score, and diagnostics outputs."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_dir / f"{label}_segmentation_mask.png"), result.mask.astype(np.uint8) * 255)
    tlf.write_heatmap(out_dir / f"{label}_red_score.png", result.score, f"{label} {result.diagnostics['score_mode']}")
    overlay = np.clip(rgb, 0.0, 1.0).copy()
    overlay[result.mask] = 0.55 * overlay[result.mask] + 0.45 * np.array([1.0, 0.0, 0.0], dtype=np.float32)
    tlf.write_rgb(out_dir / f"{label}_segmentation_overlay.png", overlay)
    with (out_dir / f"{label}_segmentation_diagnostics.json").open("w", encoding="utf-8") as handle:
        json.dump(result.diagnostics, handle, indent=2, sort_keys=True)
        handle.write("\n")
    write_csv(out_dir / f"{label}_threshold_sweep.csv", sweep_rows)


def parse_thresholds(value: str) -> list[float]:
    return [float(item) for item in value.replace(",", " ").split()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--label", default="preview")
    parser.add_argument("--page", default=1, type=int)
    parser.add_argument("--crop", default=None)
    parser.add_argument("--score-mode", default="lab_a", choices=("lab_a", "excess_red", "normalized_red", "chroma", "hsv_red_pink"))
    parser.add_argument("--threshold", default=None, type=float)
    parser.add_argument("--threshold-percentile", default=95.0, type=float)
    parser.add_argument("--seed-threshold", default=None, type=float)
    parser.add_argument("--candidate-threshold", default=None, type=float)
    parser.add_argument("--min-area-px", default=0, type=int)
    parser.add_argument("--sweep-thresholds", default="")
    parser.add_argument("--domain-mask", default=None, type=Path)
    parser.add_argument("--core-mask", default=None, type=Path)
    parser.add_argument("--mask-source", default="image", choices=("image", "mat"))
    parser.add_argument("--domain-mask-variable", default="")
    parser.add_argument("--core-mask-variable", default="")
    parser.add_argument("--mask-grid", default="native_cropped", choices=audit.MASK_GRIDS)
    parser.add_argument("--out", default=Path("outputs/preview_napl_segmentation"), type=Path)
    return parser.parse_args()


def load_optional_cli_mask(
    path: Path | None,
    *,
    target_shape: tuple[int, int],
    crop: tuple[int, int, int, int] | None,
    mask_id: str,
    mask_source: str,
    variable_name: str,
    mask_grid: str,
) -> Array | None:
    if path is None:
        return None
    raw_mask, resolved_variable = audit.load_mask_array(path, mask_source, variable_name)
    selection = audit.prepare_mask(
        raw_mask,
        target_shape=target_shape,
        crop=crop,
        mask_id=mask_id,
        mask_source=mask_source,
        mask_source_path=path,
        mask_variable_name=resolved_variable,
        mask_grid=mask_grid,
    )
    return selection.mask


def main() -> None:
    args = parse_args()
    crop = tlf.parse_crop(args.crop)
    rgb = tlf.crop_image(tlf.read_tif_page(args.image, args.page), crop)
    domain_mask = load_optional_cli_mask(
        args.domain_mask,
        target_shape=rgb.shape[:2],
        crop=crop,
        mask_id="flow_domain",
        mask_source=args.mask_source,
        variable_name=args.domain_mask_variable,
        mask_grid=args.mask_grid,
    )
    core_mask = load_optional_cli_mask(
        args.core_mask,
        target_shape=rgb.shape[:2],
        crop=crop,
        mask_id="core_flow",
        mask_source=args.mask_source,
        variable_name=args.core_mask_variable,
        mask_grid=args.mask_grid,
    )
    result = segment_red_napl(
        rgb,
        domain_mask=domain_mask,
        core_mask=core_mask,
        score_mode=args.score_mode,
        threshold=args.threshold,
        threshold_percentile=args.threshold_percentile,
        seed_threshold=args.seed_threshold,
        candidate_threshold=args.candidate_threshold,
        min_area_px=args.min_area_px,
    )
    if args.sweep_thresholds:
        thresholds = parse_thresholds(args.sweep_thresholds)
    else:
        thresholds = list(np.percentile(result.score[np.isfinite(result.score)], [80, 85, 90, 95, 97, 99]))
    if domain_mask is None:
        domain_mask = np.ones(result.score.shape, dtype=bool)
    sweep_rows = threshold_sweep(result.score, domain_mask, thresholds)
    write_outputs(args.out, args.label, rgb, result, sweep_rows)
    print(f"Wrote segmentation-only outputs to: {args.out.resolve()}")


if __name__ == "__main__":
    main()
