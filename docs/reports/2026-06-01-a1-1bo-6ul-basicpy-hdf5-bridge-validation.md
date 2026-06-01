# A1 1-BO 6 uL BasicPy HDF5 Bridge Validation

Date: 2026-06-01

## Purpose

Validate that MATLAB can reproduce the Python BasicPy exact-audit Branch C chroma result when MATLAB reads the same corrected RGB arrays from HDF5.

This test intentionally bypasses the segmentation pipeline. It only checks:

```text
Python BasicPy corrected RGB cache
-> MATLAB h5read
-> compute_bulk_sn_color(chroma)
-> S_NAPL_color
```

## Cache Contract

Cache root:

`outputs/basicpy_hdf5_cache_20260601/A1_1BO_6UL_manual_roi_page1/`

Each corrected frame is stored as:

```text
dataset = /rgb_corrected
dtype = float32
shape = H x W x 3
range = [0, 1]
storage_order = python_hwc
correction = basicpy_rgb_all
basicpy_working_size = 256
basicpy_max_iterations = 20
```

The cache includes:

- 3 water endpoint candidates
- 7 full-NAPL frames
- 43 residual frames
- cropped ROI mask in `mask_crop.h5`
- `manifest.csv`
- `cache_manifest.json`

MATLAB `h5read` reverses dimensions for Python/h5py HWC storage, so the bridge explicitly applies:

```matlab
rgb = single(permute(raw, [3 2 1]));
mask = logical(raw_mask');
```

## Scripts

Python cache builder:

`run_a1_1bo_6ul_build_basicpy_hdf5_cache.py`

MATLAB bridge:

`run_a1_1bo_6ul_bridge_hdf5_chroma.m`

Bridge output:

`outputs/bridge_hdf5_chroma_20260601/A1_1BO_6UL_manual_roi_page1/`

## Result

Bridge summary:

`outputs/bridge_hdf5_chroma_20260601/A1_1BO_6UL_manual_roi_page1/bridge_comparison_summary.csv`

| Endpoint | MATLAB full median | Python full median | abs diff | MATLAB residual median | Python residual median | abs diff | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| A_full_consistency_primary | 1.000000 | 1.000206 | 0.000206 | 0.156809 | 0.155181 | 0.001628 | pass |
| B_residual_separation_primary | 0.998155 | 0.997950 | 0.000205 | 0.155087 | 0.153475 | 0.001613 | pass |

Gate threshold:

```text
abs(full_median_diff) <= 0.01
abs(residual_median_diff) <= 0.01
```

Both endpoint variants passed.

## Interpretation

The earlier MATLAB morphology run produced residual `S_NAPL_color` around `0.19-0.20`. The HDF5 bridge produces residual `S_NAPL_color` around `0.155-0.157`, matching the Python BasicPy exact audit.

Therefore, the Python-vs-MATLAB difference is primarily caused by illumination correction/preprocessing, not by MATLAB's `compute_bulk_sn_color`, ROI mask handling, HDF5 reading, or chroma endpoint normalization.

## Decision

Use this as the next pipeline direction:

```text
Primary quantitative preprocessing:
  Python BasicPy corrected RGB HDF5 cache

Primary MATLAB quantitative output:
  S_NAPL_color from compute_bulk_sn_color(chroma)

Endpoint policy:
  A_full_consistency_primary = default
  B_residual_separation_primary = sensitivity check

Segmentation/mask pipeline:
  secondary visualization and morphology diagnostics
```

The next implementation step is to add a full-run mode that feeds MATLAB Branch C from the BasicPy HDF5 cache, while keeping segmentation-derived mask Sn clearly secondary.
