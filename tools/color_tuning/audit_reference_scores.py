"""Audit NAPL reference candidates and color scores.

The script compares candidate full-NAPL references against a clean-water
reference, one high-saturation frame, and one residual frame. It is a Python
diagnostic step used before porting any color-index saturation logic to MATLAB.
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
import matplotlib.pyplot as plt
import numpy as np
from skimage import color

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import tune_light_field as tlf


Array = np.ndarray
REGIONS = ("left", "center", "right")
SCORE_MODES = (
    "normalized_red",
    "excess_red",
    "lab_a",
    "chroma",
    "lab_ab_projection_global",
    "lab_ab_projection_pixelwise",
    "od_red",
    "od_green",
    "od_composite",
)
MASK_GRIDS = ("native_full", "native_cropped", "processing_grid", "preview_scale2")
NON_QUANTITATIVE_RGB_SOURCES = {"contrast_preview", "scale2_preview"}


@dataclass(frozen=True)
class AuditConfig:
    page: int
    crop: tuple[int, int, int, int] | None
    correction: str
    sigma: float
    downsample: int
    basicpy_working_size: int
    basicpy_max_iterations: int
    min_endpoint_delta: float
    min_separation: float
    max_region_range: float


@dataclass(frozen=True)
class CandidateSpec:
    label: str
    path: Path


@dataclass(frozen=True)
class MaskProvenance:
    mask_id: str
    mask_source: str
    mask_source_path: str
    mask_variable_name: str
    mask_grid: str
    mask_shape_original: tuple[int, int]
    mask_shape_after_crop: tuple[int, int]
    mask_shape_used: tuple[int, int]
    mask_resize_method: str
    mask_pixel_count_all: int
    mask_coverage_fraction: float
    rgb_shape_h: int
    rgb_shape_w: int
    crop_box_raw_xywh: tuple[int, int, int, int] | None

    def as_row(self) -> dict[str, object]:
        return {
            "mask_id": self.mask_id,
            "mask_source": self.mask_source,
            "mask_source_path": self.mask_source_path,
            "mask_variable_name": self.mask_variable_name,
            "mask_grid": self.mask_grid,
            "mask_shape_original_h": self.mask_shape_original[0],
            "mask_shape_original_w": self.mask_shape_original[1],
            "mask_shape_after_crop_h": self.mask_shape_after_crop[0],
            "mask_shape_after_crop_w": self.mask_shape_after_crop[1],
            "mask_shape_used_h": self.mask_shape_used[0],
            "mask_shape_used_w": self.mask_shape_used[1],
            "mask_resize_method": self.mask_resize_method,
            "mask_pixel_count_all": self.mask_pixel_count_all,
            "mask_coverage_fraction": self.mask_coverage_fraction,
            "rgb_shape_h": self.rgb_shape_h,
            "rgb_shape_w": self.rgb_shape_w,
            "crop_box_raw_xywh": "" if self.crop_box_raw_xywh is None else " ".join(
                str(v) for v in self.crop_box_raw_xywh
            ),
        }


@dataclass(frozen=True)
class MaskSelection:
    mask: Array
    provenance: MaskProvenance


@dataclass(frozen=True)
class EligibilityDecision:
    eligible_for_quantitative_endpoint: bool
    eligible_for_color_index_timeseries: bool
    eligible_for_segmentation: bool
    failure_reason: str

    def as_row(self) -> dict[str, object]:
        return {
            "eligible_for_quantitative_endpoint": self.eligible_for_quantitative_endpoint,
            "eligible_for_color_index_timeseries": self.eligible_for_color_index_timeseries,
            "eligible_for_segmentation": self.eligible_for_segmentation,
            "failure_reason": self.failure_reason,
        }


def classify_candidate(
    *,
    endpoint_delta: float,
    s_high: float,
    s_residual: float,
    region_s_high: dict[str, float],
    region_s_residual: dict[str, float],
    min_endpoint_delta: float,
    min_separation: float,
    max_region_range: float,
) -> str:
    """Classify whether one reference/score combination is usable."""
    if not np.isfinite(endpoint_delta) or abs(endpoint_delta) < min_endpoint_delta:
        return "bad_endpoint_delta"

    if not np.isfinite(s_high) or not np.isfinite(s_residual):
        return "nonfinite_saturation"

    if s_high - s_residual < min_separation:
        return "inverted_high_residual"

    high_values = [region_s_high.get(region, np.nan) for region in REGIONS]
    residual_values = [region_s_residual.get(region, np.nan) for region in REGIONS]
    if not all(np.isfinite(high_values)) or not all(np.isfinite(residual_values)):
        return "nonfinite_region_saturation"
    if max(high_values) - min(high_values) > max_region_range:
        return "unstable_regions"
    if max(residual_values) - min(residual_values) > max_region_range:
        return "unstable_regions"

    return "pass"


def endpoint_eligibility(
    *,
    status: str,
    mask_id: str,
    self_endpoint_check: bool,
    rgb_source: str,
) -> EligibilityDecision:
    """Translate score status into production endpoint eligibility."""
    reason_by_status = {
        "bad_endpoint_delta": "bad_endpoint_delta",
        "inverted_high_residual": "residual_exceeds_high",
        "unstable_regions": "bad_region_consistency",
        "nonfinite_saturation": "nonfinite_saturation",
        "nonfinite_region_saturation": "bad_region_consistency",
    }
    color_index_ok = mask_id != "none" and rgb_source == "corrected_quantitative"

    if status != "pass":
        # Branch C may still produce a provisional color-index time series when
        # the audit RGB and flow-domain mask are valid, even if the endpoint
        # candidate is not eligible for endpoint-normalized production Sn.
        return EligibilityDecision(False, color_index_ok, True, reason_by_status.get(status, status))
    if mask_id == "none":
        return EligibilityDecision(False, False, True, "unmasked_domain")
    if self_endpoint_check:
        return EligibilityDecision(False, color_index_ok, True, "self_validation_only")
    if rgb_source in NON_QUANTITATIVE_RGB_SOURCES or rgb_source != "corrected_quantitative":
        return EligibilityDecision(False, False, True, "non_quantitative_rgb_source")
    return EligibilityDecision(True, True, True, "none")


def read_frame(path: Path, page: int, crop: tuple[int, int, int, int] | None) -> Array:
    """Read and crop one RGB TIF frame."""
    return tlf.crop_image(tlf.read_tif_page(path, page), crop)


def normalize_mask_array(mask: Array) -> Array:
    """Convert image or numeric mask data to a 2-D boolean mask."""
    mask = np.asarray(mask)
    if mask.ndim == 3:
        mask = mask[:, :, 0]
    if mask.ndim != 2:
        raise ValueError(f"Mask must be 2-D or RGB-like, got shape {mask.shape}")
    return np.asarray(mask > 0, dtype=bool)


def crop_mask(mask: Array, crop: tuple[int, int, int, int] | None) -> Array:
    """Crop a 2-D mask using one-based x,y,width,height coordinates."""
    if crop is None:
        return mask
    x, y, width, height = crop
    x0 = max(x - 1, 0)
    y0 = max(y - 1, 0)
    x1 = min(x0 + width, mask.shape[1])
    y1 = min(y0 + height, mask.shape[0])
    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"Mask crop {crop} is outside mask shape {mask.shape}")
    return mask[y0:y1, x0:x1]


def resize_mask_nearest(mask: Array, target_shape: tuple[int, int]) -> Array:
    """Resize a mask with nearest-neighbor interpolation only."""
    if tuple(mask.shape) == tuple(target_shape):
        return np.asarray(mask, dtype=bool)
    resized = cv2.resize(
        mask.astype(np.uint8),
        (int(target_shape[1]), int(target_shape[0])),
        interpolation=cv2.INTER_NEAREST,
    )
    return resized > 0


def prepare_mask(
    raw_mask: Array,
    *,
    target_shape: tuple[int, int],
    crop: tuple[int, int, int, int] | None,
    mask_id: str,
    mask_source: str,
    mask_source_path: Path | str,
    mask_variable_name: str,
    mask_grid: str,
) -> MaskSelection:
    """Prepare an external mask for the audited RGB grid and record provenance."""
    if mask_grid not in MASK_GRIDS:
        raise ValueError(f"Unsupported mask_grid: {mask_grid}")

    mask = normalize_mask_array(raw_mask)
    original_shape = tuple(int(v) for v in mask.shape)
    if mask_grid == "native_full":
        mask = crop_mask(mask, crop)
    after_crop_shape = tuple(int(v) for v in mask.shape)

    resize_method = "none"
    if after_crop_shape != tuple(target_shape):
        mask = resize_mask_nearest(mask, target_shape)
        resize_method = "nearest"
    used_shape = tuple(int(v) for v in mask.shape)
    count = int(np.count_nonzero(mask))
    if count == 0:
        raise ValueError(
            f"Prepared mask {mask_id!r} has zero selected pixels after crop/resize; "
            f"original_shape={original_shape}, after_crop_shape={after_crop_shape}, "
            f"target_shape={target_shape}, mask_grid={mask_grid}"
        )
    coverage = float(count / max(mask.size, 1))
    provenance = MaskProvenance(
        mask_id=mask_id,
        mask_source=mask_source,
        mask_source_path=str(mask_source_path),
        mask_variable_name=mask_variable_name,
        mask_grid=mask_grid,
        mask_shape_original=original_shape,
        mask_shape_after_crop=after_crop_shape,
        mask_shape_used=used_shape,
        mask_resize_method=resize_method,
        mask_pixel_count_all=count,
        mask_coverage_fraction=coverage,
        rgb_shape_h=int(target_shape[0]),
        rgb_shape_w=int(target_shape[1]),
        crop_box_raw_xywh=crop,
    )
    return MaskSelection(mask=mask, provenance=provenance)


def make_unmasked_selection(
    target_shape: tuple[int, int],
    crop: tuple[int, int, int, int] | None,
) -> MaskSelection:
    """Create an all-true diagnostic mask; never production endpoint eligible."""
    mask = np.ones(target_shape, dtype=bool)
    provenance = MaskProvenance(
        mask_id="none",
        mask_source="none",
        mask_source_path="",
        mask_variable_name="",
        mask_grid="processing_grid",
        mask_shape_original=tuple(target_shape),
        mask_shape_after_crop=tuple(target_shape),
        mask_shape_used=tuple(target_shape),
        mask_resize_method="none",
        mask_pixel_count_all=int(mask.size),
        mask_coverage_fraction=1.0,
        rgb_shape_h=int(target_shape[0]),
        rgb_shape_w=int(target_shape[1]),
        crop_box_raw_xywh=crop,
    )
    return MaskSelection(mask=mask, provenance=provenance)


def build_region_masks(mask_or_shape: Array | tuple[int, int], base_mask: Array | None = None) -> dict[str, Array]:
    """Return all/left/center/right masks using x-quantiles of selected pixels."""
    if base_mask is None:
        if isinstance(mask_or_shape, tuple):
            mask = np.ones(mask_or_shape, dtype=bool)
        else:
            mask = normalize_mask_array(mask_or_shape)
    else:
        mask = normalize_mask_array(base_mask)
        if tuple(mask.shape) != tuple(mask_or_shape):
            raise ValueError(f"base_mask shape {mask.shape} does not match requested shape {mask_or_shape}")

    masks = {"all": mask}
    ys, xs = np.where(mask)
    for region in REGIONS:
        masks[region] = np.zeros_like(mask, dtype=bool)
    if xs.size == 0:
        return masks

    order = np.lexsort((ys, xs))
    for region, chunk in zip(REGIONS, np.array_split(order, len(REGIONS))):
        region_mask = np.zeros_like(mask, dtype=bool)
        region_mask[ys[chunk], xs[chunk]] = True
        masks[region] = region_mask
    return masks


def correction_method(correction: str, sigma: float) -> tlf.MethodSpec:
    """Convert CLI correction name to a MethodSpec."""
    if correction == "none":
        return tlf.MethodSpec("none", "none", "none", 0.0)
    if correction == "basicpy_rgb_all":
        return tlf.MethodSpec("basicpy_rgb_all", "all", "basicpy_rgb", 0.0)
    if correction == "basicpy_luma_all":
        return tlf.MethodSpec("basicpy_luma_all", "all", "basicpy_luma", 0.0)
    if correction == "water_rgb":
        return tlf.MethodSpec(f"water_rgb_sigma{int(sigma)}", "water", "rgb", sigma)
    if correction == "water_luma":
        return tlf.MethodSpec(f"water_luma_sigma{int(sigma)}", "water", "luminance", sigma)
    if correction == "self_rgb":
        return tlf.MethodSpec(f"self_rgb_sigma{int(sigma)}", "self", "rgb", sigma)
    raise ValueError(f"Unsupported correction: {correction}")


def correct_frames(frames: dict[str, Array], config: AuditConfig) -> dict[str, Array]:
    """Apply the selected correction to all frames."""
    method = correction_method(config.correction, config.sigma)
    corrected, _ = tlf.make_method_outputs(
        method,
        frames,
        frames["water"],
        config.downsample,
        basicpy_working_size=config.basicpy_working_size,
        basicpy_max_iterations=config.basicpy_max_iterations,
    )
    return corrected


def channel_score(rgb: Array, mode: str) -> Array:
    """Compute scores that do not require endpoint vectors."""
    if mode in {"normalized_red", "excess_red", "lab_a", "chroma"}:
        return tlf.score_map(rgb, mode)
    if mode == "od_red":
        return rgb[:, :, 0]
    if mode == "od_green":
        return rgb[:, :, 1]
    if mode == "od_composite":
        return 0.5 * rgb[:, :, 0] + 0.25 * rgb[:, :, 1] + 0.25 * rgb[:, :, 2]
    raise ValueError(f"Unsupported simple score mode: {mode}")


def compute_score_values(
    corrected: dict[str, Array],
    masks: dict[str, Array],
    score_mode: str,
) -> dict[str, dict[str, float]]:
    """Compute robust Q values for each frame and region."""
    values: dict[str, dict[str, float]] = {}

    if score_mode in {"lab_ab_projection", "lab_ab_projection_global"}:
        endpoint_mask = masks["all"]
        lab_water = color.rgb2lab(corrected["water"])
        lab_napl = color.rgb2lab(corrected["napl"])
        lab_frames = {label: color.rgb2lab(rgb) for label, rgb in corrected.items()}
        water_endpoint = np.array(
            [
                np.nanmedian(lab_water[:, :, 1][endpoint_mask]),
                np.nanmedian(lab_water[:, :, 2][endpoint_mask]),
            ],
            dtype=np.float32,
        )
        napl_endpoint = np.array(
            [
                np.nanmedian(lab_napl[:, :, 1][endpoint_mask]),
                np.nanmedian(lab_napl[:, :, 2][endpoint_mask]),
            ],
            dtype=np.float32,
        )
        vector = napl_endpoint - water_endpoint
        denom = max(float(np.linalg.norm(vector)), 1e-8)
        for label, lab in lab_frames.items():
            # This Q is a linear projection, not a pre-normalized saturation.
            # normalized_saturation() subtracts Q_water and divides by
            # Q_napl - Q_water later, so adding water subtraction here would
            # only change the intermediate Q units without changing S.
            projection = (lab[:, :, 1] * vector[0] + lab[:, :, 2] * vector[1]) / denom
            values[label] = {
                region: tlf.winsorized_mean(projection[mask])
                for region, mask in masks.items()
            }
        return values

    if score_mode == "lab_ab_projection_pixelwise":
        lab_water = color.rgb2lab(corrected["water"])
        lab_napl = color.rgb2lab(corrected["napl"])
        lab_frames = {label: color.rgb2lab(rgb) for label, rgb in corrected.items()}
        water_ab = np.dstack([lab_water[:, :, 1], lab_water[:, :, 2]])
        napl_ab = np.dstack([lab_napl[:, :, 1], lab_napl[:, :, 2]])
        vector = napl_ab - water_ab
        denom = np.sum(vector * vector, axis=2)
        for label, lab in lab_frames.items():
            frame_ab = np.dstack([lab[:, :, 1], lab[:, :, 2]])
            projection = np.sum((frame_ab - water_ab) * vector, axis=2) / np.maximum(denom, 1e-8)
            values[label] = {
                region: tlf.winsorized_mean(projection[mask])
                for region, mask in masks.items()
            }
        return values

    if score_mode.startswith("od_"):
        base = channel_score(corrected["water"], score_mode)
        for label, rgb in corrected.items():
            frame = channel_score(rgb, score_mode)
            od = -np.log((frame + 1e-4) / (base + 1e-4))
            values[label] = {
                region: tlf.winsorized_mean(od[mask])
                for region, mask in masks.items()
            }
        return values

    for label, rgb in corrected.items():
        score = channel_score(rgb, score_mode)
        values[label] = {
            region: tlf.winsorized_mean(score[mask])
            for region, mask in masks.items()
        }
    return values


def normalized_saturation(q_frame: float, q_water: float, endpoint_delta: float) -> float:
    """Map Q values to endpoint-normalized saturation."""
    if not np.isfinite(endpoint_delta) or abs(endpoint_delta) < 1e-12:
        return float("nan")
    return float((q_frame - q_water) / endpoint_delta)


def audit_candidate(
    candidate: CandidateSpec,
    base_frames: dict[str, Array],
    config: AuditConfig,
    mask_selection: MaskSelection | None = None,
    rgb_source: str = "corrected_quantitative",
    water_path: Path | None = None,
    high_path: Path | None = None,
    residual_path: Path | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, Array]]:
    """Audit one NAPL reference candidate."""
    frames = dict(base_frames)
    frames["napl"] = read_frame(candidate.path, config.page, config.crop)
    corrected = correct_frames(frames, config)
    if mask_selection is None:
        mask_selection = make_unmasked_selection(corrected["water"].shape[:2], config.crop)
    masks = build_region_masks(mask_selection.mask)
    mask_row = mask_selection.provenance.as_row()
    self_endpoint_check = same_path(candidate.path, high_path)
    if water_path is not None and high_path is not None and residual_path is not None:
        candidate_row = candidate_provenance_row(
            candidate,
            water_path=water_path,
            high_path=high_path,
            residual_path=residual_path,
            page=config.page,
        )
    else:
        candidate_row = {
            "napl_ref": candidate.label,
            "napl_ref_path": str(candidate.path),
            "endpoint_candidate_role": endpoint_candidate_role(candidate, high_path),
            "page": int(config.page),
        }

    detail_rows: list[dict[str, object]] = []
    ranking_rows: list[dict[str, object]] = []

    for score_mode in SCORE_MODES:
        score_values = compute_score_values(corrected, masks, score_mode)
        q_water = score_values["water"]["all"]
        q_napl = score_values["napl"]["all"]
        q_high = score_values["high"]["all"]
        q_residual = score_values["residual"]["all"]
        endpoint_delta = q_napl - q_water
        s_high = normalized_saturation(q_high, q_water, endpoint_delta)
        s_residual = normalized_saturation(q_residual, q_water, endpoint_delta)

        region_s_high = {
            region: normalized_saturation(
                score_values["high"][region],
                score_values["water"][region],
                score_values["napl"][region] - score_values["water"][region],
            )
            for region in REGIONS
        }
        region_s_residual = {
            region: normalized_saturation(
                score_values["residual"][region],
                score_values["water"][region],
                score_values["napl"][region] - score_values["water"][region],
            )
            for region in REGIONS
        }
        status = classify_candidate(
            endpoint_delta=endpoint_delta,
            s_high=s_high,
            s_residual=s_residual,
            region_s_high=region_s_high,
            region_s_residual=region_s_residual,
            min_endpoint_delta=config.min_endpoint_delta,
            min_separation=config.min_separation,
            max_region_range=config.max_region_range,
        )
        decision = endpoint_eligibility(
            status=status,
            mask_id=mask_selection.provenance.mask_id,
            self_endpoint_check=self_endpoint_check,
            rgb_source=rgb_source,
        )

        ranking_row = {
                "correction": config.correction,
                "rgb_source": rgb_source,
                "score_mode": score_mode,
                "endpoint_delta": endpoint_delta,
                "abs_endpoint_delta": abs(endpoint_delta),
                "direction": "increasing" if endpoint_delta > 0 else "decreasing",
                "S_high": s_high,
                "S_residual": s_residual,
                "separation": s_high - s_residual,
                "left_S_high": region_s_high["left"],
                "center_S_high": region_s_high["center"],
                "right_S_high": region_s_high["right"],
                "left_S_residual": region_s_residual["left"],
                "center_S_residual": region_s_residual["center"],
                "right_S_residual": region_s_residual["right"],
                "status": status,
                "self_endpoint_check": self_endpoint_check,
            }
        ranking_row.update(candidate_row)
        ranking_row.update(mask_row)
        ranking_row.update(decision.as_row())
        ranking_rows.append(ranking_row)

        for frame_label, region_values in score_values.items():
            for region, q_value in region_values.items():
                detail_row = {
                        "correction": config.correction,
                        "rgb_source": rgb_source,
                        "score_mode": score_mode,
                        "frame": frame_label,
                        "region": region,
                        "Q": q_value,
                    }
                detail_row.update(candidate_row)
                detail_row.update(mask_row)
                detail_rows.append(detail_row)

    return detail_rows, ranking_rows, corrected


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    """Write rows to CSV."""
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, object]) -> None:
    """Write a JSON manifest."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def write_score_plot(path: Path, ranking_rows: list[dict[str, object]]) -> None:
    """Plot S_high and S_residual for each candidate score."""
    path.parent.mkdir(parents=True, exist_ok=True)
    labels = [f"{row['napl_ref']}\n{row['score_mode']}" for row in ranking_rows]
    s_high = [float(row["S_high"]) for row in ranking_rows]
    s_residual = [float(row["S_residual"]) for row in ranking_rows]
    statuses = [str(row["status"]) for row in ranking_rows]
    colors = ["#2ca02c" if status == "pass" else "#d62728" for status in statuses]

    fig, ax = plt.subplots(figsize=(max(10, 0.7 * len(labels)), 5))
    x = np.arange(len(labels))
    ax.bar(x - 0.18, s_high, width=0.36, label="high", color="#1f77b4")
    ax.bar(x + 0.18, s_residual, width=0.36, label="residual", color="#ff7f0e")
    for xpos, status, color in zip(x, statuses, colors):
        ax.text(xpos, 1.05, status, rotation=90, va="bottom", ha="center", color=color, fontsize=8)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.axhline(1, color="gray", linewidth=0.8, linestyle="--")
    ax.set_ylabel("Endpoint-normalized S")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=90, fontsize=8)
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def parse_candidate(value: str) -> CandidateSpec:
    """Parse label=path or path candidate syntax."""
    if "=" in value:
        label, path = value.split("=", 1)
        return CandidateSpec(label.strip(), Path(path.strip()))
    path = Path(value)
    return CandidateSpec(path.stem, path)


def same_path(left: Path, right: Path | None) -> bool:
    """Best-effort path equality that also works for not-yet-existing test paths."""
    if right is None:
        return False
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return left == right


def endpoint_candidate_role(candidate: CandidateSpec, high_path: Path | None) -> str:
    """Classify reference role without using it as a production pass condition."""
    if same_path(candidate.path, high_path):
        return "self_check"
    label = candidate.label.lower()
    if "high" in label or "provisional" in label:
        return "provisional_high"
    return "existing_napl_named"


def candidate_provenance_row(
    candidate: CandidateSpec,
    *,
    water_path: Path,
    high_path: Path,
    residual_path: Path,
    page: int,
) -> dict[str, object]:
    """Return endpoint candidate and validation input provenance fields."""
    return {
        "napl_ref": candidate.label,
        "napl_ref_path": str(candidate.path),
        "endpoint_candidate_role": endpoint_candidate_role(candidate, high_path),
        "water_reference_id": water_path.stem,
        "water_reference_path": str(water_path),
        "high_validation_id": high_path.stem,
        "high_validation_path": str(high_path),
        "residual_validation_id": residual_path.stem,
        "residual_validation_path": str(residual_path),
        "page": int(page),
    }


def build_audit_manifest(
    *,
    water_path: Path,
    high_path: Path,
    residual_path: Path,
    candidates: list[CandidateSpec],
    config: dict[str, object],
    mask_selection: MaskSelection,
    rgb_source: str,
) -> dict[str, object]:
    """Build a JSON-serializable audit manifest for long-term tracking."""
    return {
        "rgb_source": rgb_source,
        "config": dict(config),
        "mask": mask_selection.provenance.as_row(),
        "inputs": {
            "water_reference_path": str(water_path),
            "high_validation_path": str(high_path),
            "residual_validation_path": str(residual_path),
            "candidates": [
                {
                    "label": candidate.label,
                    "path": str(candidate.path),
                    "endpoint_candidate_role": endpoint_candidate_role(candidate, high_path),
                }
                for candidate in candidates
            ],
        },
    }


def load_mask_array(path: Path, mask_source: str, variable_name: str = "") -> tuple[Array, str]:
    """Load a mask from an image or MATLAB MAT file."""
    if not path.exists():
        raise FileNotFoundError(path)
    if mask_source == "mat" or path.suffix.lower() == ".mat":
        try:
            from scipy.io import loadmat
        except ImportError as exc:
            raise RuntimeError("Loading .mat masks requires scipy.") from exc
        try:
            payload = loadmat(path)
        except (NotImplementedError, ValueError, OSError) as exc:
            raise RuntimeError(
                f"Could not load MATLAB mask file {path}. If this is a MATLAB v7.3/HDF5 "
                "file, export the mask variable to a v7 MAT file or an image mask before "
                "running the Python audit."
            ) from exc
        if variable_name:
            if variable_name not in payload:
                raise KeyError(f"Variable {variable_name!r} not found in {path}")
            return payload[variable_name], variable_name
        for name, value in payload.items():
            if name.startswith("__"):
                continue
            array = np.asarray(value)
            if array.ndim == 2:
                return array, name
        raise ValueError(f"No 2-D mask-like variable found in {path}")

    if mask_source != "image":
        raise ValueError(f"Unsupported mask_source: {mask_source}")
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError(f"Could not read mask image: {path}")
    return image, variable_name


def load_selected_mask(
    args: argparse.Namespace,
    target_shape: tuple[int, int],
    crop: tuple[int, int, int, int] | None,
) -> MaskSelection:
    """Load the requested audit mask or return an all-true diagnostic mask."""
    if args.mask_id == "none":
        return make_unmasked_selection(target_shape, crop)

    if args.mask_id == "flow_domain":
        mask_path = args.domain_mask
        variable_name = args.domain_mask_variable
    elif args.mask_id == "core_flow":
        mask_path = args.core_mask
        variable_name = args.core_mask_variable
    else:
        raise ValueError(f"Unsupported mask_id: {args.mask_id}")

    if mask_path is None:
        required_arg = "--domain-mask" if args.mask_id == "flow_domain" else "--core-mask"
        raise ValueError(f"{required_arg} is required when --mask-id={args.mask_id}")

    raw_mask, resolved_variable = load_mask_array(mask_path, args.mask_source, variable_name)
    return prepare_mask(
        raw_mask,
        target_shape=target_shape,
        crop=crop,
        mask_id=args.mask_id,
        mask_source=args.mask_source,
        mask_source_path=mask_path,
        mask_variable_name=resolved_variable,
        mask_grid=args.mask_grid,
    )


def write_mask_overlay(path: Path, rgb: Array, mask: Array) -> None:
    """Write a simple cyan overlay showing the audited mask footprint."""
    path.parent.mkdir(parents=True, exist_ok=True)
    image = np.clip(rgb, 0.0, 1.0).copy()
    boundary = cv2.dilate(mask.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=1).astype(bool) & ~mask
    overlay = image.copy()
    overlay[mask] = 0.65 * overlay[mask] + 0.35 * np.array([0.0, 1.0, 1.0], dtype=np.float32)
    overlay[boundary] = np.array([1.0, 1.0, 0.0], dtype=np.float32)
    tlf.write_rgb(path, overlay)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--water", required=True, type=Path)
    parser.add_argument("--napl-candidate", action="append", required=True, help="label=path; repeatable")
    parser.add_argument("--high", required=True, type=Path)
    parser.add_argument("--residual", required=True, type=Path)
    parser.add_argument("--page", default=1, type=int)
    parser.add_argument("--crop", default=None, help="Optional one-based crop rectangle: x y width height")
    parser.add_argument(
        "--correction",
        default="basicpy_rgb_all",
        choices=("none", "basicpy_rgb_all", "basicpy_luma_all", "water_rgb", "water_luma", "self_rgb"),
    )
    parser.add_argument("--sigma", default=160.0, type=float)
    parser.add_argument("--downsample", default=4, type=int)
    parser.add_argument("--basicpy-working-size", default=128, type=int)
    parser.add_argument("--basicpy-max-iterations", default=80, type=int)
    parser.add_argument("--min-endpoint-delta", default=0.01, type=float)
    parser.add_argument("--min-separation", default=0.35, type=float)
    parser.add_argument("--max-region-range", default=0.25, type=float)
    parser.add_argument(
        "--mask-id",
        default="none",
        choices=("none", "flow_domain", "core_flow"),
        help="Mask used for production endpoint audit. none is diagnostic only.",
    )
    parser.add_argument("--domain-mask", default=None, type=Path)
    parser.add_argument("--core-mask", default=None, type=Path)
    parser.add_argument("--mask-source", default="image", choices=("image", "mat"))
    parser.add_argument("--domain-mask-variable", default="")
    parser.add_argument("--core-mask-variable", default="")
    parser.add_argument("--mask-grid", default="native_cropped", choices=MASK_GRIDS)
    parser.add_argument(
        "--rgb-source",
        default="corrected_quantitative",
        choices=("corrected_quantitative", "contrast_preview", "scale2_preview"),
        help="Source class of RGB entering endpoint statistics.",
    )
    parser.add_argument("--out", default=Path("outputs/reference_score_audit"), type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = AuditConfig(
        page=args.page,
        crop=tlf.parse_crop(args.crop),
        correction=args.correction,
        sigma=args.sigma,
        downsample=args.downsample,
        basicpy_working_size=args.basicpy_working_size,
        basicpy_max_iterations=args.basicpy_max_iterations,
        min_endpoint_delta=args.min_endpoint_delta,
        min_separation=args.min_separation,
        max_region_range=args.max_region_range,
    )
    candidates = [parse_candidate(value) for value in args.napl_candidate]

    base_frames = {
        "water": read_frame(args.water, config.page, config.crop),
        "high": read_frame(args.high, config.page, config.crop),
        "residual": read_frame(args.residual, config.page, config.crop),
    }
    mask_selection = load_selected_mask(args, base_frames["water"].shape[:2], config.crop)

    all_detail_rows: list[dict[str, object]] = []
    all_ranking_rows: list[dict[str, object]] = []
    montage_frames: dict[str, dict[str, Array]] = {}

    for candidate in candidates:
        detail_rows, ranking_rows, corrected = audit_candidate(
            candidate,
            base_frames,
            config,
            mask_selection=mask_selection,
            rgb_source=args.rgb_source,
            water_path=args.water,
            high_path=args.high,
            residual_path=args.residual,
        )
        all_detail_rows.extend(detail_rows)
        all_ranking_rows.extend(ranking_rows)
        montage_frames[candidate.label] = corrected

    all_ranking_rows.sort(
        key=lambda row: (
            0 if row["status"] == "pass" else 1,
            -float(row["separation"]) if np.isfinite(row["separation"]) else 0,
            -float(row["abs_endpoint_delta"]) if np.isfinite(row["abs_endpoint_delta"]) else 0,
        )
    )

    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(args.out / "reference_score_audit.csv", all_detail_rows)
    write_csv(args.out / "reference_score_ranking.csv", all_ranking_rows)
    write_json(
        args.out / "reference_score_audit_manifest.json",
        build_audit_manifest(
            water_path=args.water,
            high_path=args.high,
            residual_path=args.residual,
            candidates=candidates,
            config={
                "page": config.page,
                "crop": "" if config.crop is None else list(config.crop),
                "correction": config.correction,
                "sigma": config.sigma,
                "downsample": config.downsample,
                "basicpy_working_size": config.basicpy_working_size,
                "basicpy_max_iterations": config.basicpy_max_iterations,
                "min_endpoint_delta": config.min_endpoint_delta,
                "min_separation": config.min_separation,
                "max_region_range": config.max_region_range,
            },
            mask_selection=mask_selection,
            rgb_source=args.rgb_source,
        ),
    )
    write_score_plot(args.out / "reference_score_ranking.png", all_ranking_rows)

    for label, corrected in montage_frames.items():
        tlf.make_montage(
            args.out / f"{label}_corrected_montage.png",
            {config.correction: corrected},
            ["water", "napl", "high", "residual"],
        )
        for frame_label in ("water", "napl", "high", "residual"):
            write_mask_overlay(
                args.out / f"{label}_{frame_label}_{mask_selection.provenance.mask_id}_mask_overlay.png",
                corrected[frame_label],
                mask_selection.mask,
            )

    print(f"Wrote audit to: {args.out.resolve()}")
    print(f"  {args.out / 'reference_score_ranking.csv'}")
    print(f"  {args.out / 'reference_score_audit.csv'}")
    print(f"  {args.out / 'reference_score_ranking.png'}")
    print("Top rows:")
    for row in all_ranking_rows[:8]:
        print(
            f"  {row['status']:24s} {row['napl_ref']:18s} "
            f"{row['score_mode']:18s} S_high={row['S_high']:.3f} "
            f"S_residual={row['S_residual']:.3f} delta={row['endpoint_delta']:.4g}"
        )


if __name__ == "__main__":
    main()
