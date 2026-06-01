# A1 1-BO 6 uL Manifest-Driven Cache Pipeline

Date: 2026-06-01

## Purpose

Convert the A1 1-BO 6 uL Branch C pipeline from a hard-coded 53-frame
validation run into a manifest-driven run.

The production time series source is:

`G:\Microfluid\00 A1 1-BO 6 UL WATER DISPLACEMENT\01 WATER`

The clean-water endpoint source remains:

`G:\Microfluid\00 A1 1-BO 6 UL WATER DISPLACEMENT\00 NAPL`

## Generated Inputs

Generator:

`run_a1_1bo_6ul_make_full_frames_manifest.py`

Output:

`outputs/manifests_20260601/A1_1BO_6UL_manual_roi_page1/`

Files:

- `accepted_frames.csv`
- `endpoint_policy.json`
- `accepted_frames_summary.json`

Manifest summary:

```text
frame_count = 53
water_endpoint = 3
full_napl = 7
residual = 43
timeseries_frame_count = 50
```

The first 7 production frames are marked `full_napl`; the remaining 43
production frames are marked `residual`.

## Commands

Generate accepted-frame manifest and endpoint policy:

```powershell
python run_a1_1bo_6ul_make_full_frames_manifest.py --force
```

Build manifest-driven BasicPy HDF5 cache:

```powershell
python run_a1_1bo_6ul_build_basicpy_hdf5_cache.py `
  --manifest "outputs\manifests_20260601\A1_1BO_6UL_manual_roi_page1\accepted_frames.csv" `
  --out "outputs\basicpy_hdf5_cache_manifest_20260601\A1_1BO_6UL_manual_roi_page1" `
  --force
```

Run MATLAB Branch C from the manifest-driven cache:

```powershell
matlab -batch "cd('D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\.worktrees\interpolation-assisted-segmentation-20260527'); outputs = run_a1_1bo_6ul_hdf5_cache_branch_c_pipeline('outputs\basicpy_hdf5_cache_manifest_20260601\A1_1BO_6UL_manual_roi_page1','outputs\hdf5_cache_branch_c_pipeline_manifest_20260601\A1_1BO_6UL_manual_roi_page1','outputs\manifests_20260601\A1_1BO_6UL_manual_roi_page1\endpoint_policy.json');"
```

## Output

Cache output:

`outputs/basicpy_hdf5_cache_manifest_20260601/A1_1BO_6UL_manual_roi_page1/`

Branch C output:

`outputs/hdf5_cache_branch_c_pipeline_manifest_20260601/A1_1BO_6UL_manual_roi_page1/`

Primary output files:

- `S_NAPL_color_primary_A.csv`
- `S_NAPL_color_sensitivity_B.csv`
- `S_NAPL_color_A_B_sensitivity_comparison.csv`
- `branch_c_cache_pipeline_summary.csv`
- `cache_branch_c_manifest.json`
- `S_NAPL_color_A_B_sensitivity.png`

## Result

Branch C summary:

| Endpoint | Full-NAPL median | Residual median | Bridge gate |
| --- | ---: | ---: | --- |
| A_full_consistency_primary | 1.000000 | 0.156809 | pass |
| B_residual_separation_primary | 0.998156 | 0.155087 | pass |

Regression against the previous hard-coded cache-fed run:

```text
rows_old = 50
rows_new = 50
label_match = True
max_abs_A_diff = 0.0
max_abs_B_diff = 0.0
max_abs_sensitivity_diff = 0.0
```

## Decision

The manifest-driven pipeline is functionally equivalent to the prior
hard-coded 53-frame pipeline for A1 1-BO 6 uL. It should be the next operating
mode because future frame inclusion/exclusion, endpoint selection, and
timeseries ordering can be changed in `accepted_frames.csv` and
`endpoint_policy.json` without editing code.

Segmentation remains outside the primary `S_NAPL_color` calculation.
