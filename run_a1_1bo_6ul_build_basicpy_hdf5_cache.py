from __future__ import annotations

import argparse
import gc
import json
import sys
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
import tifffile


REPO = Path(__file__).resolve().parent
OUT_DEFAULT = (
    REPO
    / "outputs"
    / "basicpy_hdf5_cache_20260601"
    / "A1_1BO_6UL_manual_roi_page1"
)
MASK_PATH = REPO / "outputs" / "roi_templates_20260601" / "A1_1BO_6UL" / "Mask.tif"

sys.path.insert(0, str(REPO / "tools" / "color_tuning"))
import tune_light_field as tlf  # noqa: E402


WATER = [
    (
        "water_ep_00_napl_00_3s",
        r"G:\Microfluid\00 A1 1-BO 6 UL WATER DISPLACEMENT\00 NAPL\00 NAPL 3 SECONDS.tif",
    ),
    (
        "water_ep_00_napl_00_3s_1",
        r"G:\Microfluid\00 A1 1-BO 6 UL WATER DISPLACEMENT\00 NAPL\00 NAPL 3 SECONDS_1.tif",
    ),
    (
        "water_ep_00_napl_01_1s",
        r"G:\Microfluid\00 A1 1-BO 6 UL WATER DISPLACEMENT\00 NAPL\01 NAPL 1 SECONDS.tif",
    ),
]

FULL_NAPL = [
    (
        "full_00_water_3s",
        r"G:\Microfluid\00 A1 1-BO 6 UL WATER DISPLACEMENT\01 WATER\00 WATER 3 SECONDS.tif",
    ),
    (
        "full_00_water_3s_1",
        r"G:\Microfluid\00 A1 1-BO 6 UL WATER DISPLACEMENT\01 WATER\00 WATER 3 SECONDS_1.tif",
    ),
    (
        "full_00_water_3s_2",
        r"G:\Microfluid\00 A1 1-BO 6 UL WATER DISPLACEMENT\01 WATER\00 WATER 3 SECONDS_2.tif",
    ),
    (
        "full_01_water_1s",
        r"G:\Microfluid\00 A1 1-BO 6 UL WATER DISPLACEMENT\01 WATER\01 WATER 1 SECONDS.tif",
    ),
    (
        "full_01_water_1s_1",
        r"G:\Microfluid\00 A1 1-BO 6 UL WATER DISPLACEMENT\01 WATER\01 WATER 1 SECONDS_1.tif",
    ),
    (
        "full_01_water_1s_2",
        r"G:\Microfluid\00 A1 1-BO 6 UL WATER DISPLACEMENT\01 WATER\01 WATER 1 SECONDS_2.tif",
    ),
    (
        "full_01_water_1s_3",
        r"G:\Microfluid\00 A1 1-BO 6 UL WATER DISPLACEMENT\01 WATER\01 WATER 1 SECONDS_3.tif",
    ),
]

RESIDUAL = [
    (
        "residual_02_water_3s",
        r"G:\Microfluid\00 A1 1-BO 6 UL WATER DISPLACEMENT\01 WATER\02 WATER 3 SECONDS.tif",
    ),
    *[
        (
            f"residual_02_water_3s_{index}",
            rf"G:\Microfluid\00 A1 1-BO 6 UL WATER DISPLACEMENT\01 WATER\02 WATER 3 SECONDS_{index}.tif",
        )
        for index in range(1, 43)
    ],
]

PAGE = 1
BASICPY_WORKING_SIZE = 256
BASICPY_MAX_ITERATIONS = 20
MATLAB_CROP_RECT = [1, 595, 2391, 828]


def mask_bbox(mask_path: Path) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    full_mask = tifffile.imread(mask_path) > 0
    ys, xs = np.where(full_mask)
    x0 = int(xs.min())
    x1 = int(xs.max()) + 1
    y0 = int(ys.min())
    y1 = int(ys.max()) + 1
    return full_mask[y0:y1, x0:x1], (x0, y0, x1 - x0, y1 - y0)


def read_rgb_page(path: str, page: int, bbox: tuple[int, int, int, int]) -> np.ndarray:
    x0, y0, width, height = bbox
    image = tifffile.imread(path, key=page - 1)
    image = image[y0 : y0 + height, x0 : x0 + width, :3]
    return np.clip(image.astype(np.float32) / 255.0, 0.0, 1.0)


def default_frame_specs() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for order, (label, path) in enumerate(WATER, 1):
        rows.append(
            {
                "label": label,
                "role": "water_endpoint",
                "path": path,
                "source_page": PAGE,
                "frame_order": order,
                "timeseries_order": "",
                "time_s": "",
                "include_in_timeseries": 0,
                "fit_sample": 1,
            }
        )
    offset = len(rows)
    for order, (label, path) in enumerate(FULL_NAPL, 1):
        rows.append(
            {
                "label": label,
                "role": "full_napl",
                "path": path,
                "source_page": PAGE,
                "frame_order": offset + order,
                "timeseries_order": order,
                "time_s": "",
                "include_in_timeseries": 1,
                "fit_sample": 1,
            }
        )
    offset = len(rows)
    for order, (label, path) in enumerate(RESIDUAL, 1):
        rows.append(
            {
                "label": label,
                "role": "residual",
                "path": path,
                "source_page": PAGE,
                "frame_order": offset + order,
                "timeseries_order": len(FULL_NAPL) + order,
                "time_s": "",
                "include_in_timeseries": 1,
                "fit_sample": 1,
            }
        )
    return rows


def normalize_bool(value: object, default: bool) -> bool:
    if pd.isna(value):
        return default
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer, float, np.floating)):
        return bool(int(value))
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return default


def load_frame_specs(manifest_path: Path | None) -> list[dict[str, object]]:
    if manifest_path is None:
        return default_frame_specs()

    table = pd.read_csv(manifest_path)
    required = {"label", "role", "frame_order", "source_path", "source_page"}
    missing = sorted(required - set(table.columns))
    if missing:
        raise ValueError(f"Manifest is missing required columns: {missing}")

    if table["label"].duplicated().any():
        duplicated = sorted(table.loc[table["label"].duplicated(), "label"].astype(str))
        raise ValueError(f"Manifest labels must be unique. Duplicates: {duplicated}")

    specs: list[dict[str, object]] = []
    for row in table.to_dict(orient="records"):
        source_path = Path(str(row["source_path"]))
        if not source_path.is_file():
            raise FileNotFoundError(f"Manifest source_path does not exist: {source_path}")
        source_page = int(row["source_page"])
        if source_page < 1:
            raise ValueError(f"source_page must be 1-based for {source_path}")
        specs.append(
            {
                "label": str(row["label"]),
                "role": str(row["role"]),
                "path": str(source_path),
                "source_page": source_page,
                "frame_order": int(row["frame_order"]),
                "timeseries_order": row.get("timeseries_order", ""),
                "time_s": row.get("time_s", ""),
                "include_in_timeseries": int(
                    normalize_bool(row.get("include_in_timeseries", True), True)
                ),
                "fit_sample": int(normalize_bool(row.get("fit_sample", True), True)),
            }
        )

    fit_count = sum(int(spec["fit_sample"]) for spec in specs)
    if fit_count == 0:
        raise ValueError("Manifest must mark at least one row fit_sample=1.")
    return specs


def write_rgb_h5(
    path: Path,
    label: str,
    rgb: np.ndarray,
    attrs: dict[str, object],
    compression: str | None,
) -> None:
    with h5py.File(path, "w") as handle:
        data = handle.create_dataset(
            "/rgb_corrected",
            data=np.asarray(rgb, dtype=np.float32),
            dtype="float32",
            compression=compression,
        )
        data.attrs["storage_order"] = "python_hwc"
        data.attrs["matlab_h5read_permute"] = "permute(raw, [3 2 1])"
        for key, value in attrs.items():
            handle.attrs[key] = value
        handle.attrs["label"] = label


def write_mask_h5(path: Path, mask: np.ndarray, attrs: dict[str, object]) -> None:
    with h5py.File(path, "w") as handle:
        data = handle.create_dataset(
            "/flow_domain_mask",
            data=np.asarray(mask, dtype=np.uint8),
            dtype="uint8",
        )
        data.attrs["storage_order"] = "python_hw"
        data.attrs["matlab_h5read_transform"] = "logical(raw')"
        for key, value in attrs.items():
            handle.attrs[key] = value


def apply_basicpy_rgb_for_specs(
    frames: dict[str, np.ndarray],
    specs: list[dict[str, object]],
) -> dict[str, np.ndarray]:
    labels = [str(spec["label"]) for spec in specs]
    fit_labels = [str(spec["label"]) for spec in specs if int(spec["fit_sample"])]
    if len(fit_labels) == len(labels):
        return tlf.apply_basicpy_rgb(
            frames,
            BASICPY_WORKING_SIZE,
            BASICPY_MAX_ITERATIONS,
        )

    try:
        from basicpy import BaSiC
    except ImportError as exc:
        raise RuntimeError(
            "BaSiCPy is not installed. Install it with: python -m pip install BaSiCPy"
        ) from exc

    height, width = frames[labels[0]].shape[:2]
    corrected = {
        label: np.zeros((height, width, 3), dtype=np.float32)
        for label in labels
    }
    for channel in range(3):
        fit_stack = np.stack(
            [frames[label][:, :, channel] for label in fit_labels],
            axis=0,
        ).astype(np.float32)
        all_stack = np.stack(
            [frames[label][:, :, channel] for label in labels],
            axis=0,
        ).astype(np.float32)
        model = BaSiC(
            get_darkfield=False,
            sort_intensity=True,
            working_size=BASICPY_WORKING_SIZE,
            max_iterations=BASICPY_MAX_ITERATIONS,
        )
        model.fit(fit_stack, skip_shape_warning=True)
        corrected_stack = model.transform(all_stack, use_tqdm=False)
        if isinstance(corrected_stack, tuple):
            corrected_stack = corrected_stack[0]
        corrected_stack = np.asarray(corrected_stack, dtype=np.float32)
        for index, label in enumerate(labels):
            corrected[label][:, :, channel] = corrected_stack[index]
    return {label: np.clip(rgb, 0.0, 1.0) for label, rgb in corrected.items()}


def fit_basicpy_rgb_models(
    frames: dict[str, np.ndarray],
    labels: list[str],
) -> list[object]:
    try:
        from basicpy import BaSiC
    except ImportError as exc:
        raise RuntimeError(
            "BaSiCPy is not installed. Install it with: python -m pip install BaSiCPy"
        ) from exc

    models: list[object] = []
    for channel in range(3):
        stack = np.stack(
            [frames[label][:, :, channel] for label in labels],
            axis=0,
        ).astype(np.float32)
        model = BaSiC(
            get_darkfield=False,
            sort_intensity=True,
            working_size=BASICPY_WORKING_SIZE,
            max_iterations=BASICPY_MAX_ITERATIONS,
        )
        model.fit(stack, skip_shape_warning=True)
        models.append(model)
    return models


def transform_basicpy_rgb_batch(
    models: list[object],
    frames: dict[str, np.ndarray],
    labels: list[str],
) -> dict[str, np.ndarray]:
    height, width = frames[labels[0]].shape[:2]
    corrected = {
        label: np.zeros((height, width, 3), dtype=np.float32)
        for label in labels
    }
    for channel, model in enumerate(models):
        stack = np.stack(
            [frames[label][:, :, channel] for label in labels],
            axis=0,
        ).astype(np.float32)
        corrected_stack = model.transform(stack, use_tqdm=False)
        if isinstance(corrected_stack, tuple):
            corrected_stack = corrected_stack[0]
        corrected_stack = np.asarray(corrected_stack, dtype=np.float32)
        for index, label in enumerate(labels):
            corrected[label][:, :, channel] = corrected_stack[index]
    return {label: np.clip(rgb, 0.0, 1.0) for label, rgb in corrected.items()}


def h5_path_for_spec(frames_dir: Path, index: int, spec: dict[str, object]) -> Path:
    return frames_dir / f"{index:03d}_{spec['label']}.h5"


def compression_label(compression: str | None) -> str:
    return compression if compression else "none"


def manifest_row_for_rgb(
    index: int,
    spec: dict[str, object],
    h5_path: Path,
    rgb: np.ndarray,
    bbox_text: str,
    matlab_crop_text: str,
    compression: str | None,
) -> dict[str, object]:
    return {
        "label": str(spec["label"]),
        "role": spec["role"],
        "frame_order": spec["frame_order"],
        "timeseries_order": spec["timeseries_order"],
        "source_path": spec["path"],
        "source_page": int(spec["source_page"]),
        "time_s": spec["time_s"],
        "include_in_timeseries": int(spec["include_in_timeseries"]),
        "fit_sample": int(spec["fit_sample"]),
        "h5_path": str(h5_path),
        "dataset": "/rgb_corrected",
        "shape_h": rgb.shape[0],
        "shape_w": rgb.shape[1],
        "shape_c": rgb.shape[2],
        "dtype": "float32",
        "range_min": float(np.nanmin(rgb)),
        "range_max": float(np.nanmax(rgb)),
        "bbox_zero_based_xywh": bbox_text,
        "matlab_crop_rect_xywh": matlab_crop_text,
        "correction": "basicpy_rgb_all",
        "basicpy_working_size": BASICPY_WORKING_SIZE,
        "basicpy_max_iterations": BASICPY_MAX_ITERATIONS,
        "storage_order": "python_hwc",
        "matlab_h5read_permute": "3 2 1",
        "hdf5_compression": compression_label(compression),
        "no_per_frame_contrast": True,
        "no_per_frame_rescale": True,
    }


def read_rgb_frames(
    specs: list[dict[str, object]],
    bbox: tuple[int, int, int, int],
    prefix: str,
) -> dict[str, np.ndarray]:
    frames: dict[str, np.ndarray] = {}
    for index, spec in enumerate(specs, 1):
        print(f"{prefix} {index:03d}/{len(specs):03d} {spec['label']}", flush=True)
        frames[str(spec["label"])] = read_rgb_page(
            str(spec["path"]),
            int(spec["source_page"]),
            bbox,
        )
    return frames


def build_cache(
    out_dir: Path,
    force: bool,
    manifest_path: Path | None,
    mask_path: Path,
    compression: str | None,
    batch_size: int,
    resume: bool,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(exist_ok=True)

    mask, bbox = mask_bbox(mask_path)
    x0, y0, width, height = bbox
    bbox_text = f"{x0} {y0} {width} {height}"
    matlab_crop_text = " ".join(str(value) for value in MATLAB_CROP_RECT)

    specs = load_frame_specs(manifest_path)
    mask_h5 = out_dir / "mask_crop.h5"
    if mask_h5.exists() and not (force or resume):
        raise FileExistsError(f"Refusing to overwrite existing file: {mask_h5}")
    if not (mask_h5.exists() and resume and not force):
        write_mask_h5(
            mask_h5,
            mask,
            {
                "mask_source_path": str(mask_path),
                "bbox_zero_based_xywh": bbox_text,
                "matlab_crop_rect_xywh": matlab_crop_text,
                "mask_pixel_count": int(mask.sum()),
            },
        )

    if batch_size <= 0:
        frames = read_rgb_frames(specs, bbox, "READ")
        print("BASICPY_START", flush=True)
        corrected = apply_basicpy_rgb_for_specs(frames, specs)
        del frames
        gc.collect()
        print("BASICPY_DONE", flush=True)
        manifest_rows = write_corrected_frames(
            specs,
            corrected,
            frames_dir,
            force,
            False,
            bbox_text,
            matlab_crop_text,
            compression,
        )
    else:
        manifest_rows = build_cache_batched(
            specs,
            frames_dir,
            bbox,
            force,
            resume,
            bbox_text,
            matlab_crop_text,
            compression,
            batch_size,
        )

    manifest = pd.DataFrame(manifest_rows)
    cache_manifest_csv = out_dir / "manifest.csv"
    manifest.to_csv(cache_manifest_csv, index=False)

    run_manifest = {
        "cache_contract": "basicpy_hdf5_float32_hwc",
        "output_dir": str(out_dir),
        "manifest_csv": str(cache_manifest_csv),
        "input_manifest_csv": str(manifest_path) if manifest_path else "",
        "mask_h5": str(mask_h5),
        "frame_count": len(manifest_rows),
        "roles": manifest["role"].value_counts().to_dict(),
        "timeseries_frame_count": int(manifest["include_in_timeseries"].sum()),
        "fit_sample_frame_count": int(manifest["fit_sample"].sum()),
        "dataset": "/rgb_corrected",
        "dtype": "float32",
        "shape": "H x W x 3",
        "range": "[0,1]",
        "correction": "basicpy_rgb_all",
        "basicpy_working_size": BASICPY_WORKING_SIZE,
        "basicpy_max_iterations": BASICPY_MAX_ITERATIONS,
        "bbox_zero_based_xywh": [x0, y0, width, height],
        "matlab_crop_rect_xywh": MATLAB_CROP_RECT,
        "hdf5_compression": compression_label(compression),
        "batch_size": batch_size,
        "resume": resume,
        "no_per_frame_contrast": True,
        "no_per_frame_rescale": True,
    }
    (out_dir / "cache_manifest.json").write_text(json.dumps(run_manifest, indent=2), encoding="utf-8")
    print(f"CACHE_DONE {out_dir}", flush=True)


def write_corrected_frames(
    specs: list[dict[str, object]],
    corrected: dict[str, np.ndarray],
    frames_dir: Path,
    force: bool,
    resume: bool,
    bbox_text: str,
    matlab_crop_text: str,
    compression: str | None,
    indices: list[int] | None = None,
    total_count: int | None = None,
) -> list[dict[str, object]]:
    manifest_rows = []
    if indices is None:
        indices = list(range(1, len(specs) + 1))
    if total_count is None:
        total_count = len(indices)
    for index, spec in zip(indices, specs):
        label = str(spec["label"])
        h5_path = h5_path_for_spec(frames_dir, index, spec)
        if h5_path.exists() and resume and not force:
            print(f"SKIP_EXISTING {index:03d}/{total_count:03d} {label}", flush=True)
            rgb = h5read_rgb_python_hwc(h5_path)
            manifest_rows.append(
                manifest_row_for_rgb(
                    index,
                    spec,
                    h5_path,
                    rgb,
                    bbox_text,
                    matlab_crop_text,
                    compression,
                )
            )
            continue
        if h5_path.exists() and not force:
            raise FileExistsError(f"Refusing to overwrite existing file: {h5_path}")
        rgb = corrected[label]
        print(f"WRITE {index:03d}/{total_count:03d} {label}", flush=True)
        write_frame_h5(
            h5_path,
            label,
            rgb,
            spec,
            bbox_text,
            matlab_crop_text,
            compression,
        )
        manifest_rows.append(
            manifest_row_for_rgb(
                index,
                spec,
                h5_path,
                rgb,
                bbox_text,
                matlab_crop_text,
                compression,
            )
        )
    return manifest_rows


def build_cache_batched(
    specs: list[dict[str, object]],
    frames_dir: Path,
    bbox: tuple[int, int, int, int],
    force: bool,
    resume: bool,
    bbox_text: str,
    matlab_crop_text: str,
    compression: str | None,
    batch_size: int,
) -> list[dict[str, object]]:
    fit_specs = [spec for spec in specs if int(spec["fit_sample"])]
    fit_frames = read_rgb_frames(fit_specs, bbox, "READ_FIT")
    fit_labels = [str(spec["label"]) for spec in fit_specs]
    print("BASICPY_FIT_START", flush=True)
    models = fit_basicpy_rgb_models(fit_frames, fit_labels)
    del fit_frames
    gc.collect()
    print("BASICPY_FIT_DONE", flush=True)

    manifest_rows: list[dict[str, object]] = []
    for start in range(0, len(specs), batch_size):
        batch_specs = specs[start : start + batch_size]
        pending_specs = []
        pending_indices = []
        for offset, spec in enumerate(batch_specs):
            index = start + offset + 1
            h5_path = h5_path_for_spec(frames_dir, index, spec)
            label = str(spec["label"])
            if h5_path.exists() and resume and not force:
                print(f"SKIP_EXISTING {index:03d}/{len(specs):03d} {label}", flush=True)
                rgb = h5read_rgb_python_hwc(h5_path)
                manifest_rows.append(
                    manifest_row_for_rgb(
                        index,
                        spec,
                        h5_path,
                        rgb,
                        bbox_text,
                        matlab_crop_text,
                        compression,
                    )
                )
                continue
            if h5_path.exists() and not force:
                raise FileExistsError(f"Refusing to overwrite existing file: {h5_path}")
            pending_specs.append(spec)
            pending_indices.append(index)

        if not pending_specs:
            continue
        frames = read_rgb_frames(pending_specs, bbox, "READ_BATCH")
        labels = [str(spec["label"]) for spec in pending_specs]
        print(
            f"BASICPY_TRANSFORM_BATCH {pending_indices[0]:03d}-{pending_indices[-1]:03d}",
            flush=True,
        )
        corrected = transform_basicpy_rgb_batch(models, frames, labels)
        del frames
        gc.collect()
        rows = write_corrected_frames(
            pending_specs,
            corrected,
            frames_dir,
            True,
            False,
            bbox_text,
            matlab_crop_text,
            compression,
            pending_indices,
            len(specs),
        )
        manifest_rows.extend(rows)
        del corrected
        gc.collect()

    return sorted(manifest_rows, key=lambda row: int(row["frame_order"]))


def write_frame_h5(
    h5_path: Path,
    label: str,
    rgb: np.ndarray,
    spec: dict[str, object],
    bbox_text: str,
    matlab_crop_text: str,
    compression: str | None,
) -> None:
    write_rgb_h5(
        h5_path,
        label,
        rgb,
        {
            "source_path": spec["path"],
            "source_page": int(spec["source_page"]),
            "role": spec["role"],
            "timeseries_order": str(spec["timeseries_order"]),
            "time_s": str(spec["time_s"]),
            "include_in_timeseries": int(spec["include_in_timeseries"]),
            "fit_sample": int(spec["fit_sample"]),
            "bbox_zero_based_xywh": bbox_text,
            "matlab_crop_rect_xywh": matlab_crop_text,
            "correction": "basicpy_rgb_all",
            "basicpy_working_size": BASICPY_WORKING_SIZE,
            "basicpy_max_iterations": BASICPY_MAX_ITERATIONS,
            "rgb_dtype": "float32",
            "rgb_range": "[0,1]",
            "no_per_frame_contrast": True,
            "no_per_frame_rescale": True,
        },
        compression,
    )


def h5read_rgb_python_hwc(h5_path: Path) -> np.ndarray:
    with h5py.File(h5_path, "r") as handle:
        return np.asarray(handle["/rgb_corrected"], dtype=np.float32)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Accepted-frame CSV. If omitted, use the built-in 53-frame validation set.",
    )
    parser.add_argument("--mask", type=Path, default=MASK_PATH)
    parser.add_argument(
        "--compression",
        choices=["gzip", "lzf", "none"],
        default="none",
        help="Optional HDF5 compression for /rgb_corrected datasets.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=0,
        help="Transform frames in batches after fitting on fit_sample rows. 0 keeps legacy all-in-memory mode.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip existing frame HDF5 files and rebuild manifest from the available cache.",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    compression = None if args.compression == "none" else args.compression
    build_cache(
        args.out,
        args.force,
        args.manifest,
        args.mask,
        compression,
        args.batch_size,
        args.resume,
    )


if __name__ == "__main__":
    main()
