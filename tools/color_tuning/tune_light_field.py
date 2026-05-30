"""Prototype light-field correction for DNAPL color tuning.

This script is intentionally separate from the MATLAB pipeline. It reads a few
representative TIF frames, applies candidate low-frequency illumination
corrections, and writes visual diagnostics plus CSV metrics. Use it to choose a
correction strategy before porting the logic to MATLAB.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import cv2
import matplotlib.pyplot as plt
import numpy as np
import tifffile
from skimage import color


Array = np.ndarray


@dataclass(frozen=True)
class FrameSpec:
    label: str
    path: Path
    page: int


@dataclass(frozen=True)
class MethodSpec:
    name: str
    source: str
    mode: str
    sigma: float


@dataclass(frozen=True)
class PreviewResult:
    image: Array
    clip_low_fraction: float
    clip_high_fraction: float


def parse_crop(value: str | None) -> tuple[int, int, int, int] | None:
    """Parse ImageJ/MATLAB-style x,y,width,height crop rectangle."""
    if value is None or value.strip() == "":
        return None
    parts = [int(v.strip()) for v in value.replace(",", " ").split()]
    if len(parts) != 4:
        raise ValueError("--crop must contain four integers: x y width height")
    x, y, width, height = parts
    if width <= 0 or height <= 0:
        raise ValueError("--crop width and height must be positive")
    return x, y, width, height


def parse_sigmas(value: str) -> list[float]:
    """Parse comma/space-separated Gaussian sigma values."""
    sigmas = [float(v) for v in value.replace(",", " ").split()]
    if not sigmas:
        raise ValueError("--sigmas must contain at least one value")
    if any(v <= 0 for v in sigmas):
        raise ValueError("--sigmas must be positive")
    return sigmas


def read_tif_page(path: Path, page: int) -> Array:
    """Read a one-indexed RGB page from a TIF stack as float32 in [0, 1]."""
    if not path.exists():
        raise FileNotFoundError(path)
    if page < 1:
        raise ValueError("page is one-indexed and must be >= 1")

    with tifffile.TiffFile(path) as tif:
        if page > len(tif.pages):
            raise ValueError(f"{path} has {len(tif.pages)} pages, requested {page}")
        image = tif.pages[page - 1].asarray()

    if image.ndim == 2:
        image = np.repeat(image[:, :, None], 3, axis=2)
    if image.ndim != 3 or image.shape[2] < 3:
        raise ValueError(f"{path} page {page} is not an RGB image: {image.shape}")
    image = image[:, :, :3]

    image_float = image.astype(np.float32)
    if image.dtype == np.uint8:
        return image_float / 255.0
    if image.dtype == np.uint16:
        return image_float / 65535.0
    max_value = float(np.nanmax(image_float))
    if max_value > 1.0:
        image_float = image_float / max_value
    return np.clip(image_float, 0.0, 1.0)


def crop_image(image: Array, crop: tuple[int, int, int, int] | None) -> Array:
    """Crop an image using x,y,width,height with one-based coordinates."""
    if crop is None:
        return image
    x, y, width, height = crop
    x0 = max(x - 1, 0)
    y0 = max(y - 1, 0)
    x1 = min(x0 + width, image.shape[1])
    y1 = min(y0 + height, image.shape[0])
    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"Crop {crop} is outside image shape {image.shape}")
    return image[y0:y1, x0:x1, :]


def luminance(rgb: Array) -> Array:
    """Compute linear RGB luminance proxy."""
    return 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]


def resize_area(image: Array, scale: float) -> Array:
    """Resize using area interpolation for downsampling."""
    height, width = image.shape[:2]
    new_size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    return cv2.resize(image, new_size, interpolation=cv2.INTER_AREA)


def estimate_low_frequency_field(
    rgb: Array,
    sigma: float,
    mode: str,
    downsample: int,
) -> Array:
    """Estimate a low-frequency illumination field."""
    if downsample < 1:
        raise ValueError("downsample must be >= 1")

    small = resize_area(rgb, 1.0 / downsample)
    small_sigma = max(sigma / downsample, 0.5)

    if mode == "rgb":
        blurred = cv2.GaussianBlur(small, ksize=(0, 0), sigmaX=small_sigma, sigmaY=small_sigma)
    elif mode == "luminance":
        gray = luminance(small).astype(np.float32)
        blurred_gray = cv2.GaussianBlur(gray, ksize=(0, 0), sigmaX=small_sigma, sigmaY=small_sigma)
        blurred = np.repeat(blurred_gray[:, :, None], 3, axis=2)
    else:
        raise ValueError(f"Unknown field mode: {mode}")

    field = cv2.resize(blurred, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_CUBIC)
    return np.maximum(field.astype(np.float32), 1e-4)


def apply_flatfield(rgb: Array, field: Array, mask: Array | None = None) -> Array:
    """Apply multiplicative flat-field correction while preserving channel medians."""
    if mask is None:
        mask = np.ones(rgb.shape[:2], dtype=bool)
    corrected = np.empty_like(rgb, dtype=np.float32)
    for channel in range(3):
        values = field[:, :, channel][mask]
        channel_median = float(np.nanmedian(values))
        if not np.isfinite(channel_median) or channel_median <= 0:
            channel_median = 1.0
        normalized_field = field[:, :, channel] / channel_median
        corrected[:, :, channel] = rgb[:, :, channel] / np.maximum(normalized_field, 1e-3)
    return np.clip(corrected, 0.0, 1.0)


def apply_clahe_luminance(rgb: Array, clip_limit: float = 2.0, tile_grid: int = 8) -> Array:
    """Apply CLAHE to Lab L only. Useful for visualization, not quantitative Sn."""
    lab = color.rgb2lab(rgb)
    l_uint8 = np.clip(lab[:, :, 0] * 255.0 / 100.0, 0, 255).astype(np.uint8)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(tile_grid, tile_grid))
    lab[:, :, 0] = clahe.apply(l_uint8).astype(np.float32) * 100.0 / 255.0
    return np.clip(color.lab2rgb(lab).astype(np.float32), 0.0, 1.0)


def apply_contrast_preview(
    rgb: Array,
    mode: str = "none",
    low_percentile: float = 1.0,
    high_percentile: float = 99.0,
    clip_limit: float = 2.0,
) -> PreviewResult:
    """Create a display/segmentation preview without mutating quantitative RGB."""
    if mode == "none":
        return PreviewResult(np.array(rgb, copy=True), 0.0, 0.0)

    if mode == "clahe_l":
        image = apply_clahe_luminance(rgb, clip_limit=clip_limit)
        return PreviewResult(
            image,
            float(np.mean(image <= 0.0)),
            float(np.mean(image >= 1.0)),
        )

    if mode != "percentile":
        raise ValueError(f"Unknown contrast preview mode: {mode}")
    if not 0 <= low_percentile < high_percentile <= 100:
        raise ValueError("contrast percentiles must satisfy 0 <= low < high <= 100")

    low = np.percentile(rgb, low_percentile, axis=(0, 1), keepdims=True)
    high = np.percentile(rgb, high_percentile, axis=(0, 1), keepdims=True)
    span = np.maximum(high - low, 1e-6)
    image = np.clip((rgb - low) / span, 0.0, 1.0).astype(np.float32)
    return PreviewResult(
        image,
        float(np.mean(rgb <= low)),
        float(np.mean(rgb >= high)),
    )


def resize_preview(rgb: Array, scale_factor: int = 1, method: str = "bicubic") -> Array:
    """Resize preview RGB for segmentation inspection."""
    if int(scale_factor) != scale_factor or scale_factor < 1:
        raise ValueError("scale_factor must be a positive integer")
    if scale_factor == 1:
        return np.array(rgb, copy=True)

    interpolation_by_method = {
        "bicubic": cv2.INTER_CUBIC,
        "lanczos": cv2.INTER_LANCZOS4,
    }
    if method not in interpolation_by_method:
        raise ValueError(f"Unknown preview resize method: {method}")

    height, width = rgb.shape[:2]
    size = (width * scale_factor, height * scale_factor)
    return np.clip(
        cv2.resize(rgb, size, interpolation=interpolation_by_method[method]),
        0.0,
        1.0,
    ).astype(np.float32)


def score_map(rgb: Array, score_mode: str) -> Array:
    """Compute a scalar color score map."""
    if score_mode == "normalized_red":
        denom = np.sum(rgb, axis=2) + 1e-6
        return rgb[:, :, 0] / denom
    if score_mode == "excess_red":
        return rgb[:, :, 0] - 0.5 * (rgb[:, :, 1] + rgb[:, :, 2])
    lab = color.rgb2lab(rgb)
    if score_mode == "lab_a":
        return lab[:, :, 1]
    if score_mode == "chroma":
        return np.hypot(lab[:, :, 1], lab[:, :, 2])
    raise ValueError(f"Unknown score mode: {score_mode}")


def winsorized_mean(values: Array, percentiles: tuple[float, float] = (1.0, 99.0)) -> float:
    """Compute a winsorized mean for robust bulk score summaries."""
    flat = np.asarray(values, dtype=np.float32).ravel()
    flat = flat[np.isfinite(flat)]
    if flat.size == 0:
        return float("nan")
    low, high = np.percentile(flat, percentiles)
    return float(np.mean(np.clip(flat, low, high)))


def x_profile(values: Array, mask: Array) -> Array:
    """Compute masked median profile along x."""
    profile = np.full(values.shape[1], np.nan, dtype=np.float32)
    for col in range(values.shape[1]):
        column_values = values[:, col][mask[:, col]]
        if column_values.size:
            profile[col] = np.nanmedian(column_values)
    return profile


def third_masks(shape: tuple[int, int], base_mask: Array) -> dict[str, Array]:
    """Build left/center/right x-third masks."""
    height, width = shape
    thirds = {
        "left": (0, width // 3),
        "center": (width // 3, (2 * width) // 3),
        "right": ((2 * width) // 3, width),
    }
    out: dict[str, Array] = {}
    for name, (x0, x1) in thirds.items():
        mask = np.zeros((height, width), dtype=bool)
        mask[:, x0:x1] = True
        out[name] = mask & base_mask
    return out


def basicpy_available() -> bool:
    """Return true when BaSiCPy is importable."""
    try:
        import basicpy  # noqa: F401
    except ImportError:
        return False
    return True


def build_methods(sigmas: Sequence[float], include_basicpy: bool = False) -> list[MethodSpec]:
    """Create candidate correction methods."""
    methods = [MethodSpec("none", "none", "none", 0.0)]
    for sigma in sigmas:
        methods.append(MethodSpec(f"water_rgb_sigma{int(sigma)}", "water", "rgb", sigma))
        methods.append(MethodSpec(f"water_luma_sigma{int(sigma)}", "water", "luminance", sigma))
        methods.append(MethodSpec(f"self_rgb_sigma{int(sigma)}", "self", "rgb", sigma))
    if include_basicpy:
        methods.append(MethodSpec("basicpy_rgb_all", "all", "basicpy_rgb", 0.0))
        methods.append(MethodSpec("basicpy_luma_all", "all", "basicpy_luma", 0.0))
    methods.append(MethodSpec("clahe_l_preview", "self", "clahe_l", 0.0))
    return methods


def basicpy_transform_stack(
    stack: Array,
    working_size: int,
    max_iterations: int,
) -> Array:
    """Fit BaSiC on a grayscale stack and return corrected images."""
    try:
        from basicpy import BaSiC
    except ImportError as exc:
        raise RuntimeError(
            "BaSiCPy is not installed. Install it with: python -m pip install BaSiCPy"
        ) from exc

    model = BaSiC(
        get_darkfield=False,
        sort_intensity=True,
        working_size=working_size,
        max_iterations=max_iterations,
    )
    stack_f32 = np.asarray(stack, dtype=np.float32)
    model.fit(stack_f32, skip_shape_warning=True)
    corrected = model.transform(stack_f32, use_tqdm=False)
    if isinstance(corrected, tuple):
        corrected = corrected[0]
    return np.asarray(corrected, dtype=np.float32)


def apply_basicpy_rgb(
    frames: dict[str, Array],
    working_size: int,
    max_iterations: int,
) -> dict[str, Array]:
    """Apply BaSiCPy independently to RGB channels."""
    labels = list(frames.keys())
    height, width = frames[labels[0]].shape[:2]
    corrected = {
        label: np.zeros((height, width, 3), dtype=np.float32)
        for label in labels
    }

    for channel in range(3):
        stack = np.stack([frames[label][:, :, channel] for label in labels], axis=0)
        corrected_stack = basicpy_transform_stack(stack, working_size, max_iterations)
        for index, label in enumerate(labels):
            corrected[label][:, :, channel] = corrected_stack[index]

    return {label: np.clip(rgb, 0.0, 1.0) for label, rgb in corrected.items()}


def apply_basicpy_luma(
    frames: dict[str, Array],
    working_size: int,
    max_iterations: int,
) -> dict[str, Array]:
    """Apply a BaSiCPy luminance correction ratio to RGB frames."""
    labels = list(frames.keys())
    luma_stack = np.stack([luminance(frames[label]) for label in labels], axis=0)
    corrected_luma = basicpy_transform_stack(luma_stack, working_size, max_iterations)

    corrected: dict[str, Array] = {}
    for index, label in enumerate(labels):
        ratio = corrected_luma[index] / np.maximum(luma_stack[index], 1e-4)
        ratio = np.clip(ratio, 0.25, 4.0).astype(np.float32)
        corrected[label] = np.clip(frames[label] * ratio[:, :, None], 0.0, 1.0)
    return corrected


def make_method_outputs(
    method: MethodSpec,
    frames: dict[str, Array],
    water_rgb: Array,
    downsample: int,
    basicpy_working_size: int = 128,
    basicpy_max_iterations: int = 100,
) -> tuple[dict[str, Array], dict[str, Array]]:
    """Apply one method to all frames and return corrected images plus fields."""
    corrected: dict[str, Array] = {}
    fields: dict[str, Array] = {}

    if method.name == "none":
        for label, rgb in frames.items():
            corrected[label] = rgb
            fields[label] = np.ones_like(rgb, dtype=np.float32)
        return corrected, fields

    if method.mode == "clahe_l":
        for label, rgb in frames.items():
            corrected[label] = apply_clahe_luminance(rgb)
            fields[label] = np.ones_like(rgb, dtype=np.float32)
        return corrected, fields

    if method.mode == "basicpy_rgb":
        corrected = apply_basicpy_rgb(frames, basicpy_working_size, basicpy_max_iterations)
        fields = {label: np.ones_like(rgb, dtype=np.float32) for label, rgb in corrected.items()}
        return corrected, fields

    if method.mode == "basicpy_luma":
        corrected = apply_basicpy_luma(frames, basicpy_working_size, basicpy_max_iterations)
        fields = {label: np.ones_like(rgb, dtype=np.float32) for label, rgb in corrected.items()}
        return corrected, fields

    shared_field: Array | None = None
    if method.source == "water":
        shared_field = estimate_low_frequency_field(water_rgb, method.sigma, method.mode, downsample)

    for label, rgb in frames.items():
        field = shared_field
        if method.source == "self":
            field = estimate_low_frequency_field(rgb, method.sigma, method.mode, downsample)
        if field is None:
            raise RuntimeError(f"No field for method {method}")
        corrected[label] = apply_flatfield(rgb, field)
        fields[label] = field
    return corrected, fields


def write_rgb(path: Path, rgb: Array) -> None:
    """Write an RGB preview image."""
    path.parent.mkdir(parents=True, exist_ok=True)
    out = np.clip(rgb * 255.0, 0, 255).astype(np.uint8)
    cv2.imwrite(str(path), cv2.cvtColor(out, cv2.COLOR_RGB2BGR))


def write_heatmap(path: Path, values: Array, title: str, cmap: str = "magma") -> None:
    """Write a scalar heatmap."""
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(12, 4))
    plt.imshow(values, cmap=cmap)
    plt.colorbar(fraction=0.03, pad=0.02)
    plt.title(title)
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()


def make_profiles_plot(
    path: Path,
    method_profiles: dict[str, dict[str, Array]],
    ylabel: str,
    title: str,
) -> None:
    """Write x-profile comparison plot."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n_methods = len(method_profiles)
    fig, axes = plt.subplots(n_methods, 1, figsize=(12, max(3, 2.4 * n_methods)), sharex=True)
    if n_methods == 1:
        axes = [axes]
    for ax, (method_name, profiles) in zip(axes, method_profiles.items()):
        for label, profile in profiles.items():
            ax.plot(profile, label=label, linewidth=1.3)
        ax.set_ylabel(ylabel)
        ax.set_title(method_name)
        ax.grid(True, alpha=0.25)
        ax.legend(loc="best", fontsize=8)
    axes[-1].set_xlabel("x pixel in crop")
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def add_metrics_rows(
    rows: list[dict[str, object]],
    method_name: str,
    corrected: dict[str, Array],
    mask: Array,
    score_modes: Iterable[str],
) -> None:
    """Append per-frame/third metrics to summary rows."""
    region_masks = third_masks(mask.shape, mask)
    for label, rgb in corrected.items():
        lum = luminance(rgb)
        norm_red = score_map(rgb, "normalized_red")
        lab_a = score_map(rgb, "lab_a")
        chroma = score_map(rgb, "chroma")
        for region_name, region_mask in region_masks.items():
            rows.append(
                {
                    "method": method_name,
                    "frame": label,
                    "region": region_name,
                    "luminance_median": float(np.nanmedian(lum[region_mask])),
                    "normalized_red_median": float(np.nanmedian(norm_red[region_mask])),
                    "lab_a_median": float(np.nanmedian(lab_a[region_mask])),
                    "chroma_median": float(np.nanmedian(chroma[region_mask])),
                }
            )

        for score_mode in score_modes:
            score = score_map(rgb, score_mode)
            rows.append(
                {
                    "method": method_name,
                    "frame": label,
                    "region": f"all_{score_mode}",
                    "luminance_median": float(np.nanmedian(lum[mask])),
                    "normalized_red_median": winsorized_mean(score[mask]),
                    "lab_a_median": float(np.nanmedian(lab_a[mask])),
                    "chroma_median": float(np.nanmedian(chroma[mask])),
                }
            )


def add_sn_rows(
    rows: list[dict[str, object]],
    method_name: str,
    corrected: dict[str, Array],
    mask: Array,
    score_modes: Iterable[str],
) -> None:
    """Append endpoint-normalized color saturation diagnostics."""
    water = corrected["water"]
    napl = corrected["napl"]
    for score_mode in score_modes:
        q_water = winsorized_mean(score_map(water, score_mode)[mask])
        q_napl = winsorized_mean(score_map(napl, score_mode)[mask])
        denom = q_napl - q_water
        for label, rgb in corrected.items():
            if label in {"water", "napl"}:
                continue
            q_frame = winsorized_mean(score_map(rgb, score_mode)[mask])
            raw = (q_frame - q_water) / denom if abs(denom) > 1e-8 else float("nan")
            rows.append(
                {
                    "method": method_name,
                    "score_mode": score_mode,
                    "frame": label,
                    "q_water": q_water,
                    "q_napl": q_napl,
                    "q_frame": q_frame,
                    "s_color_raw": raw,
                    "s_color_clipped": float(np.clip(raw, 0.0, 1.0)) if np.isfinite(raw) else float("nan"),
                    "endpoint_delta": denom,
                }
            )


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    """Write heterogeneous rows to CSV."""
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, object]) -> None:
    """Write JSON diagnostics with stable formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def make_montage(
    path: Path,
    corrected_by_method: dict[str, dict[str, Array]],
    frame_labels: Sequence[str],
) -> None:
    """Write compact RGB montage for visual inspection."""
    path.parent.mkdir(parents=True, exist_ok=True)
    methods = list(corrected_by_method.keys())
    fig, axes = plt.subplots(
        len(methods),
        len(frame_labels),
        figsize=(4.2 * len(frame_labels), 2.5 * len(methods)),
        squeeze=False,
    )
    for row, method_name in enumerate(methods):
        for col, label in enumerate(frame_labels):
            ax = axes[row][col]
            ax.imshow(corrected_by_method[method_name][label])
            ax.set_axis_off()
            if row == 0:
                ax.set_title(label)
            if col == 0:
                ax.set_ylabel(method_name, rotation=0, labelpad=60, va="center")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--water", required=True, type=Path, help="Clean-water reference TIF")
    parser.add_argument("--napl", required=True, type=Path, help="Full-NAPL reference TIF")
    parser.add_argument("--high", required=True, type=Path, help="High-saturation frame TIF")
    parser.add_argument("--residual", required=True, type=Path, help="Residual frame TIF")
    parser.add_argument("--page", default=1, type=int, help="One-indexed page to read from each TIF")
    parser.add_argument(
        "--crop",
        default=None,
        help="Optional one-based crop rectangle: x y width height",
    )
    parser.add_argument(
        "--sigmas",
        default="120,240,360,480",
        help="Gaussian sigma values in full-resolution pixels",
    )
    parser.add_argument(
        "--downsample",
        default=4,
        type=int,
        help="Downsample factor used while estimating low-frequency fields",
    )
    parser.add_argument(
        "--out",
        default=Path("outputs/python_light_tuning"),
        type=Path,
        help="Output directory",
    )
    parser.add_argument(
        "--basicpy",
        choices=("off", "auto", "required"),
        default="off",
        help="Include BaSiCPy candidates. 'auto' skips when unavailable; 'required' errors.",
    )
    parser.add_argument(
        "--basicpy-working-size",
        default=128,
        type=int,
        help="BaSiCPy working_size used during fitting",
    )
    parser.add_argument(
        "--basicpy-max-iterations",
        default=100,
        type=int,
        help="BaSiCPy max_iterations used during fitting",
    )
    parser.add_argument(
        "--contrast-mode",
        choices=("none", "percentile", "clahe_l"),
        default="none",
        help="Preview-only contrast enhancement written beside quantitative RGB",
    )
    parser.add_argument("--contrast-low-percentile", default=1.0, type=float)
    parser.add_argument("--contrast-high-percentile", default=99.0, type=float)
    parser.add_argument("--contrast-clip-limit", default=2.0, type=float)
    parser.add_argument(
        "--scale-factor",
        default=1,
        type=int,
        help="Preview-only RGB upscale factor for segmentation inspection",
    )
    parser.add_argument(
        "--scale-method",
        choices=("bicubic", "lanczos"),
        default="bicubic",
        help="Interpolation used for preview RGB upscaling",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    crop = parse_crop(args.crop)
    sigmas = parse_sigmas(args.sigmas)
    args.out.mkdir(parents=True, exist_ok=True)

    specs = [
        FrameSpec("water", args.water, args.page),
        FrameSpec("napl", args.napl, args.page),
        FrameSpec("high", args.high, args.page),
        FrameSpec("residual", args.residual, args.page),
    ]
    frames = {spec.label: crop_image(read_tif_page(spec.path, spec.page), crop) for spec in specs}
    mask = np.ones(next(iter(frames.values())).shape[:2], dtype=bool)

    score_modes = ["normalized_red", "excess_red", "lab_a", "chroma"]
    include_basicpy = args.basicpy in {"auto", "required"} and basicpy_available()
    if args.basicpy == "required" and not include_basicpy:
        raise RuntimeError("BaSiCPy was requested but basicpy is not importable.")
    if args.basicpy == "auto" and not include_basicpy:
        print("BaSiCPy not available; skipping basicpy candidates.")

    methods = build_methods(sigmas, include_basicpy=include_basicpy)
    corrected_by_method: dict[str, dict[str, Array]] = {}
    metrics_rows: list[dict[str, object]] = []
    sn_rows: list[dict[str, object]] = []
    preview_rows: list[dict[str, object]] = []
    luminance_profiles: dict[str, dict[str, Array]] = {}
    red_profiles: dict[str, dict[str, Array]] = {}

    for method in methods:
        corrected, fields = make_method_outputs(
            method,
            frames,
            frames["water"],
            args.downsample,
            basicpy_working_size=args.basicpy_working_size,
            basicpy_max_iterations=args.basicpy_max_iterations,
        )
        corrected_by_method[method.name] = corrected
        add_metrics_rows(metrics_rows, method.name, corrected, mask, score_modes)
        add_sn_rows(sn_rows, method.name, corrected, mask, score_modes)

        luminance_profiles[method.name] = {
            label: x_profile(luminance(rgb), mask) for label, rgb in corrected.items()
        }
        red_profiles[method.name] = {
            label: x_profile(score_map(rgb, "normalized_red"), mask)
            for label, rgb in corrected.items()
        }

        method_dir = args.out / method.name
        for label, rgb in corrected.items():
            write_rgb(method_dir / f"{label}_corrected.png", rgb)
            write_heatmap(
                method_dir / f"{label}_normalized_red.png",
                score_map(rgb, "normalized_red"),
                f"{method.name} {label} normalized_red",
                cmap="inferno",
            )
            if args.contrast_mode != "none" or args.scale_factor != 1:
                preview = apply_contrast_preview(
                    rgb,
                    mode=args.contrast_mode,
                    low_percentile=args.contrast_low_percentile,
                    high_percentile=args.contrast_high_percentile,
                    clip_limit=args.contrast_clip_limit,
                )
                preview_rows.append(
                    {
                        "method": method.name,
                        "frame": label,
                        "contrast_mode": args.contrast_mode,
                        "clip_low_fraction": preview.clip_low_fraction,
                        "clip_high_fraction": preview.clip_high_fraction,
                        "scale_factor": args.scale_factor,
                        "scale_method": args.scale_method,
                    }
                )
                if args.contrast_mode != "none":
                    write_rgb(method_dir / f"{label}_preview.png", preview.image)
                if args.scale_factor != 1:
                    scaled_preview = resize_preview(
                        preview.image,
                        scale_factor=args.scale_factor,
                        method=args.scale_method,
                    )
                    write_rgb(
                        method_dir / f"{label}_preview_scale{args.scale_factor}.png",
                        scaled_preview,
                    )
        if method.name != "none" and method.mode != "clahe_l":
            for label, field in fields.items():
                write_heatmap(
                    method_dir / f"{label}_field_luminance.png",
                    luminance(field),
                    f"{method.name} {label} estimated field luminance",
                    cmap="viridis",
                )

    write_csv(args.out / "region_metrics.csv", metrics_rows)
    write_csv(args.out / "sn_color_metrics.csv", sn_rows)
    if preview_rows:
        write_csv(args.out / "preview_processing_metadata.csv", preview_rows)
        write_json(
            args.out / "preview_processing_metadata.json",
            {
                "contrast_mode": args.contrast_mode,
                "contrast_low_percentile": args.contrast_low_percentile,
                "contrast_high_percentile": args.contrast_high_percentile,
                "contrast_clip_limit": args.contrast_clip_limit,
                "scale_factor": args.scale_factor,
                "scale_method": args.scale_method,
                "scale_branch": "preview",
                "frames": preview_rows,
            },
        )
    make_profiles_plot(
        args.out / "luminance_x_profiles.png",
        luminance_profiles,
        "median luminance",
        "X-profile after candidate light correction",
    )
    make_profiles_plot(
        args.out / "normalized_red_x_profiles.png",
        red_profiles,
        "median normalized red",
        "Normalized red x-profile after candidate light correction",
    )
    make_montage(args.out / "rgb_montage.png", corrected_by_method, ["water", "napl", "high", "residual"])

    print(f"Wrote diagnostics to: {args.out.resolve()}")
    print("Key files:")
    print(f"  {args.out / 'rgb_montage.png'}")
    print(f"  {args.out / 'luminance_x_profiles.png'}")
    print(f"  {args.out / 'normalized_red_x_profiles.png'}")
    print(f"  {args.out / 'sn_color_metrics.csv'}")
    if preview_rows:
        print(f"  {args.out / 'preview_processing_metadata.json'}")


if __name__ == "__main__":
    main()
