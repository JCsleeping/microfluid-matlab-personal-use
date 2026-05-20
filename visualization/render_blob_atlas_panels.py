"""Render a 2D projected representative blob atlas from morphology candidates."""

from __future__ import annotations

import argparse
import math
import re
import shutil
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import tifffile
from skimage import measure, morphology


MANIFEST_COLUMNS = [
    "CandidateIndex",
    "FrameIndex",
    "BlobID",
    "ShapeClass",
    "ExemplarType",
    "Status",
    "PanelPath",
    "LabelPath",
    "MaskPath",
    "BBoxY0",
    "BBoxX0",
    "BBoxY1",
    "BBoxX1",
    "Area_px",
    "AreaTier",
    "ProjectedSphericity2D",
    "AspectRatio01",
    "Solidity2D",
    "ProjectedRoughness_boundary",
    "PtotalOverPouter",
    "Message",
]

def _safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except TypeError:
        pass
    text = str(value).strip()
    return text if text else default


def _safe_number(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return math.nan
    return number if math.isfinite(number) else math.nan


def _safe_int(value: Any) -> int | None:
    number = _safe_number(value)
    if not math.isfinite(number):
        return None
    rounded = int(number)
    if abs(number - rounded) > 1e-9:
        return None
    return rounded


def _format_metric(value: Any, digits: int = 3) -> str:
    number = _safe_number(value)
    if not math.isfinite(number):
        return "NA"
    return f"{number:.{digits}g}"


def _slug(value: Any) -> str:
    text = _safe_text(value, "unknown").lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "unknown"


def _atlas_dir_name_allowed(path: Path) -> bool:
    return path.name == "representative_blob_atlas" or path.name.startswith("representative_blob_atlas_")


def _prepare_output_dir(output_dir: Path, overwrite: bool) -> None:
    if output_dir.exists() and any(output_dir.iterdir()):
        if not overwrite:
            raise ValueError(f"Output directory exists and is non-empty: {output_dir}; pass --overwrite to replace it")
        if not _atlas_dir_name_allowed(output_dir):
            raise ValueError(f"Refusing to overwrite non-atlas output directory: {output_dir}")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def _read_label_image(path: Path) -> np.ndarray:
    labels = np.asarray(tifffile.imread(path))
    labels = np.squeeze(labels)
    if labels.ndim == 3:
        labels = labels[..., 0] if labels.shape[-1] in {3, 4} else labels[0]
    if labels.ndim != 2:
        raise ValueError(f"Expected a 2D label image, got shape {labels.shape}")
    return labels


def _bbox_from_mask(mask: np.ndarray) -> tuple[int, int, int, int]:
    coords = np.argwhere(mask)
    y0, x0 = coords.min(axis=0)
    y1, x1 = coords.max(axis=0) + 1
    return int(y0), int(x0), int(y1), int(x1)


def _padded_slice(
    bbox: tuple[int, int, int, int],
    image_shape: tuple[int, int],
    padding: int,
) -> tuple[slice, slice]:
    y0, x0, y1, x1 = bbox
    height, width = image_shape
    crop_y0 = max(0, y0 - padding)
    crop_x0 = max(0, x0 - padding)
    crop_y1 = min(height, y1 + padding)
    crop_x1 = min(width, x1 + padding)
    return slice(crop_y0, crop_y1), slice(crop_x0, crop_x1)


def _candidate_filename(row: pd.Series, blob_id: int, candidate_index: int) -> str:
    frame = _safe_int(row.get("FrameIndex"))
    frame_part = f"frame_{frame:06d}" if frame is not None else f"candidate_{candidate_index:04d}"
    shape = _slug(row.get("ShapeClass"))
    exemplar = _slug(row.get("ExemplarType"))
    return f"{frame_part}_blob_{blob_id:06d}_{shape}_{exemplar}.png"


def _draw_contours(ax: plt.Axes, mask: np.ndarray, *, color: str, linewidth: float, linestyle: str = "-") -> None:
    for contour in measure.find_contours(mask.astype(float), 0.5):
        ax.plot(contour[:, 1], contour[:, 0], color=color, linewidth=linewidth, linestyle=linestyle)


def _region_axis_vectors(orientation_rad: float) -> tuple[np.ndarray, np.ndarray]:
    """Return skimage regionprops major/minor unit vectors in image x/y coords."""
    # skimage defines orientation relative to the row axis in image coordinates.
    # These formulas match the regionprops example and avoid Matplotlib's
    # Cartesian angle convention, which is easy to misuse with imshow.
    major = np.array([-math.sin(orientation_rad), -math.cos(orientation_rad)], dtype=float)
    minor = np.array([math.cos(orientation_rad), -math.sin(orientation_rad)], dtype=float)
    return major, minor


def _draw_region_proxy(ax: plt.Axes, mask: np.ndarray) -> None:
    props = measure.regionprops(mask.astype(np.uint8))
    if not props:
        return
    prop = props[0]
    cy, cx = prop.centroid
    ax.plot(cx, cy, marker="+", color="#b30059", markersize=9, markeredgewidth=1.8)
    if prop.major_axis_length <= 1 or prop.minor_axis_length <= 1:
        return

    major_vec, minor_vec = _region_axis_vectors(prop.orientation)
    major_half = prop.major_axis_length / 2.0
    minor_half = prop.minor_axis_length / 2.0
    t = np.linspace(0, 2 * math.pi, 240)
    ellipse_xy = (
        np.array([cx, cy])[:, None]
        + major_half * np.outer(major_vec, np.cos(t))
        + minor_half * np.outer(minor_vec, np.sin(t))
    )
    ax.plot(ellipse_xy[0], ellipse_xy[1], color="#b30059", linewidth=1.2, alpha=0.9)

    ax.plot(
        [cx - major_half * major_vec[0], cx + major_half * major_vec[0]],
        [cy - major_half * major_vec[1], cy + major_half * major_vec[1]],
        color="#b30059",
        linewidth=1.0,
    )
    ax.plot(
        [cx - minor_half * minor_vec[0], cx + minor_half * minor_vec[0]],
        [cy - minor_half * minor_vec[1], cy + minor_half * minor_vec[1]],
        color="#b30059",
        linewidth=1.0,
        alpha=0.75,
    )


def _metric_annotation(row: pd.Series, blob_id: int) -> str:
    lines = [
        f"ShapeClass: {_safe_text(row.get('ShapeClass'), 'NA')}",
        f"Exemplar: {_safe_text(row.get('ExemplarType'), 'NA')}",
        f"FrameIndex: {_safe_text(row.get('FrameIndex'), 'NA')}   BlobID: {blob_id}",
        f"AreaTier: {_safe_text(row.get('AreaTier'), 'NA')}   Area_px: {_format_metric(row.get('Area_px'), 0)}",
        f"S2D: {_format_metric(row.get('ProjectedSphericity2D'))}   AR01: {_format_metric(row.get('AspectRatio01'))}",
        f"Solidity2D: {_format_metric(row.get('Solidity2D'))}",
        f"Projected roughness: {_format_metric(row.get('ProjectedRoughness_boundary'))}",
        f"Ptotal/Pouter: {_format_metric(row.get('PtotalOverPouter'))}",
    ]
    return "\n".join(lines)


def _render_panel(row: pd.Series, blob_id: int, labels: np.ndarray, output_path: Path) -> tuple[int, int, int, int]:
    mask = labels == blob_id
    if not np.any(mask):
        raise LookupError(f"BlobID {blob_id} is absent from label image")

    bbox = _bbox_from_mask(mask)
    y_slice, x_slice = _padded_slice(bbox, mask.shape, padding=20)
    crop_mask = mask[y_slice, x_slice]
    hull = morphology.convex_hull_image(crop_mask)

    fig, ax = plt.subplots(figsize=(6.4, 5.0), dpi=160)
    rgb = np.zeros((*crop_mask.shape, 3), dtype=float)
    rgb[..., 0] = 0.88 * crop_mask
    rgb[..., 1] = 0.70 * crop_mask
    rgb[..., 2] = 0.28 * crop_mask
    ax.imshow(rgb, interpolation="nearest")
    _draw_contours(ax, crop_mask, color="#1f77b4", linewidth=1.7)
    _draw_contours(ax, hull, color="#17becf", linewidth=1.2, linestyle="--")
    _draw_region_proxy(ax, crop_mask)
    ax.text(
        0.015,
        0.985,
        _metric_annotation(row, blob_id),
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=8,
        color="#111111",
        bbox={"facecolor": "white", "edgecolor": "#dddddd", "boxstyle": "round,pad=0.35", "alpha": 0.92},
    )
    ax.set_title("2D projected representative blob", fontsize=10)
    ax.set_axis_off()
    fig.tight_layout(pad=0.2)
    fig.savefig(output_path)
    plt.close(fig)
    return bbox


def _manifest_base(row: pd.Series, candidate_index: int, status: str) -> dict[str, Any]:
    base = {
        "CandidateIndex": candidate_index,
        "FrameIndex": row.get("FrameIndex", ""),
        "BlobID": row.get("BlobID", ""),
        "ShapeClass": row.get("ShapeClass", ""),
        "ExemplarType": row.get("ExemplarType", ""),
        "Status": status,
        "PanelPath": "",
        "LabelPath": row.get("LabelPath", ""),
        "MaskPath": row.get("MaskPath", ""),
        "BBoxY0": "",
        "BBoxX0": "",
        "BBoxY1": "",
        "BBoxX1": "",
        "Area_px": row.get("Area_px", ""),
        "AreaTier": row.get("AreaTier", ""),
        "ProjectedSphericity2D": row.get("ProjectedSphericity2D", ""),
        "AspectRatio01": row.get("AspectRatio01", ""),
        "Solidity2D": row.get("Solidity2D", ""),
        "ProjectedRoughness_boundary": row.get("ProjectedRoughness_boundary", ""),
        "PtotalOverPouter": row.get("PtotalOverPouter", ""),
        "Message": "",
    }
    return base


def _write_summary(output_dir: Path, manifest: pd.DataFrame) -> None:
    rendered_count = int((manifest["Status"] == "RENDERED").sum())
    missing_count = int((manifest["Status"] != "RENDERED").sum())
    status_counts = manifest["Status"].value_counts().sort_index()
    status_lines = "\n".join(f"- {status}: {count}" for status, count in status_counts.items())
    if not status_lines:
        status_lines = "- none"
    summary = "\n".join(
        [
            "# Representative Blob Atlas Summary",
            "",
            "This is a visual atlas of 2D projected representative blobs rendered from label sidecars.",
            "It is not tracking, fractal analysis, 3D roughness, true roundness, or true fluid-fluid interface measurement.",
            "",
            f"- Input candidates: {len(manifest)}",
            f"- Rendered candidates: {rendered_count}",
            f"- Missing or failed candidates: {missing_count}",
            "",
            "## Status Counts",
            "",
            status_lines,
            "",
        ]
    )
    (output_dir / "representative_blob_atlas_summary.md").write_text(summary, encoding="utf-8")


def render_blob_atlas(
    candidates_csv: str | Path,
    *,
    output_dir: str | Path | None = None,
    limit: int | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    candidates_csv = Path(candidates_csv)
    output_dir = Path(output_dir) if output_dir is not None else candidates_csv.parent / "representative_blob_atlas"
    _prepare_output_dir(output_dir, overwrite=overwrite)

    candidates = pd.read_csv(candidates_csv)
    if limit is not None:
        if limit < 0:
            raise ValueError("--limit must be non-negative")
        candidates = candidates.head(limit)

    rows: list[dict[str, Any]] = []
    for candidate_index, row in candidates.reset_index(drop=True).iterrows():
        manifest_row = _manifest_base(row, candidate_index, "PENDING")
        blob_id = _safe_int(row.get("BlobID"))
        if blob_id is None:
            manifest_row["Status"] = "INVALID_BLOB_ID"
            manifest_row["Message"] = f"Invalid BlobID: {_safe_text(row.get('BlobID'), 'missing')}"
            rows.append(manifest_row)
            continue

        manifest_row["BlobID"] = blob_id
        label_text = _safe_text(row.get("LabelPath"))
        label_path = Path(label_text) if label_text else None
        if label_path is None or not label_path.is_file():
            manifest_row["Status"] = "MISSING_LABEL_PATH"
            manifest_row["Message"] = f"LabelPath is missing or unreadable: {label_text}"
            rows.append(manifest_row)
            continue

        try:
            labels = _read_label_image(label_path)
        except Exception as exc:
            manifest_row["Status"] = "LABEL_READ_ERROR"
            manifest_row["Message"] = str(exc)
            rows.append(manifest_row)
            continue

        panel_path = output_dir / _candidate_filename(row, blob_id, candidate_index)
        try:
            bbox = _render_panel(row, blob_id, labels, panel_path)
        except LookupError as exc:
            manifest_row["Status"] = "MISSING_BLOB_LABEL"
            manifest_row["Message"] = str(exc)
            rows.append(manifest_row)
            continue
        except Exception as exc:
            manifest_row["Status"] = "RENDER_ERROR"
            manifest_row["Message"] = str(exc)
            rows.append(manifest_row)
            continue

        manifest_row["Status"] = "RENDERED"
        manifest_row["PanelPath"] = str(panel_path)
        manifest_row["BBoxY0"], manifest_row["BBoxX0"], manifest_row["BBoxY1"], manifest_row["BBoxX1"] = bbox
        rows.append(manifest_row)

    manifest = pd.DataFrame(rows, columns=MANIFEST_COLUMNS)
    manifest_path = output_dir / "representative_blob_atlas_manifest.csv"
    manifest.to_csv(manifest_path, index=False)
    _write_summary(output_dir, manifest)

    rendered_count = int((manifest["Status"] == "RENDERED").sum())
    return {
        "output_dir": output_dir,
        "manifest_path": manifest_path,
        "summary_path": output_dir / "representative_blob_atlas_summary.md",
        "candidate_count": len(manifest),
        "rendered_count": rendered_count,
        "missing_count": int(len(manifest) - rendered_count),
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates-csv", required=True, type=Path, help="Path to representative_blob_candidates.csv")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory; defaults to representative_blob_atlas next to the candidates CSV",
    )
    parser.add_argument("--limit", type=int, default=None, help="Render at most N input candidates")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing atlas output directory")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = render_blob_atlas(
        args.candidates_csv,
        output_dir=args.output_dir,
        limit=args.limit,
        overwrite=args.overwrite,
    )
    print(f"Wrote {result['rendered_count']} rendered panels to {result['output_dir']}")
    print(f"Manifest: {result['manifest_path']}")
    print(f"Summary: {result['summary_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
