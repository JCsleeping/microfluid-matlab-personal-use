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


def read_rgb_page(path: str, bbox: tuple[int, int, int, int]) -> np.ndarray:
    x0, y0, width, height = bbox
    image = tifffile.imread(path, key=PAGE - 1)
    image = image[y0 : y0 + height, x0 : x0 + width, :3]
    return np.clip(image.astype(np.float32) / 255.0, 0.0, 1.0)


def frame_specs() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for order, (label, path) in enumerate(WATER, 1):
        rows.append({"label": label, "role": "water_endpoint", "path": path, "frame_order": order})
    offset = len(rows)
    for order, (label, path) in enumerate(FULL_NAPL, 1):
        rows.append(
            {
                "label": label,
                "role": "full_napl",
                "path": path,
                "frame_order": offset + order,
            }
        )
    offset = len(rows)
    for order, (label, path) in enumerate(RESIDUAL, 1):
        rows.append(
            {
                "label": label,
                "role": "residual",
                "path": path,
                "frame_order": offset + order,
            }
        )
    return rows


def write_rgb_h5(path: Path, label: str, rgb: np.ndarray, attrs: dict[str, object]) -> None:
    with h5py.File(path, "w") as handle:
        data = handle.create_dataset(
            "/rgb_corrected",
            data=np.asarray(rgb, dtype=np.float32),
            dtype="float32",
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


def build_cache(out_dir: Path, force: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(exist_ok=True)

    mask, bbox = mask_bbox(MASK_PATH)
    x0, y0, width, height = bbox
    bbox_text = f"{x0} {y0} {width} {height}"
    matlab_crop_text = " ".join(str(value) for value in MATLAB_CROP_RECT)

    specs = frame_specs()
    frames: dict[str, np.ndarray] = {}
    for index, spec in enumerate(specs, 1):
        print(f"READ {index:03d}/{len(specs):03d} {spec['label']}", flush=True)
        frames[spec["label"]] = read_rgb_page(spec["path"], bbox)

    print("BASICPY_START", flush=True)
    corrected = tlf.apply_basicpy_rgb(
        frames,
        BASICPY_WORKING_SIZE,
        BASICPY_MAX_ITERATIONS,
    )
    del frames
    gc.collect()
    print("BASICPY_DONE", flush=True)

    mask_h5 = out_dir / "mask_crop.h5"
    if mask_h5.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite existing file: {mask_h5}")
    write_mask_h5(
        mask_h5,
        mask,
        {
            "mask_source_path": str(MASK_PATH),
            "bbox_zero_based_xywh": bbox_text,
            "matlab_crop_rect_xywh": matlab_crop_text,
            "mask_pixel_count": int(mask.sum()),
        },
    )

    manifest_rows = []
    for index, spec in enumerate(specs, 1):
        label = spec["label"]
        rgb = corrected[label]
        h5_name = f"{index:03d}_{label}.h5"
        h5_path = frames_dir / h5_name
        if h5_path.exists() and not force:
            raise FileExistsError(f"Refusing to overwrite existing file: {h5_path}")
        print(f"WRITE {index:03d}/{len(specs):03d} {label}", flush=True)
        write_rgb_h5(
            h5_path,
            label,
            rgb,
            {
                "source_path": spec["path"],
                "source_page": PAGE,
                "role": spec["role"],
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
        )
        manifest_rows.append(
            {
                "label": label,
                "role": spec["role"],
                "frame_order": spec["frame_order"],
                "source_path": spec["path"],
                "source_page": PAGE,
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
                "no_per_frame_contrast": True,
                "no_per_frame_rescale": True,
            }
        )

    manifest = pd.DataFrame(manifest_rows)
    manifest_path = out_dir / "manifest.csv"
    manifest.to_csv(manifest_path, index=False)

    run_manifest = {
        "cache_contract": "basicpy_hdf5_float32_hwc",
        "output_dir": str(out_dir),
        "manifest_csv": str(manifest_path),
        "mask_h5": str(mask_h5),
        "frame_count": len(manifest_rows),
        "roles": manifest["role"].value_counts().to_dict(),
        "dataset": "/rgb_corrected",
        "dtype": "float32",
        "shape": "H x W x 3",
        "range": "[0,1]",
        "correction": "basicpy_rgb_all",
        "basicpy_working_size": BASICPY_WORKING_SIZE,
        "basicpy_max_iterations": BASICPY_MAX_ITERATIONS,
        "bbox_zero_based_xywh": [x0, y0, width, height],
        "matlab_crop_rect_xywh": MATLAB_CROP_RECT,
        "no_per_frame_contrast": True,
        "no_per_frame_rescale": True,
    }
    (out_dir / "cache_manifest.json").write_text(json.dumps(run_manifest, indent=2), encoding="utf-8")
    print(f"CACHE_DONE {out_dir}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    build_cache(args.out, args.force)


if __name__ == "__main__":
    main()
