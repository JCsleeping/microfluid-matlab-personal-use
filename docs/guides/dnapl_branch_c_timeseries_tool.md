# DNAPL Branch C Time-Series Standalone Tool

This guide describes how to run the BasicPy HDF5 + MATLAB Branch C
`S_NAPL_color` workflow without an agent.

## Entry Point

Use this script from the worktree root:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode pilot
```

The same entry point can rerun only selected stages, change the ROI mask, and
write to a different output root.

## What It Runs

The tool wraps the existing validated scripts instead of duplicating their
logic:

1. `run_a1_1bo_6ul_make_full_frames_manifest.py`
   builds `accepted_frames.csv` and `endpoint_policy.json`.
2. `run_a1_1bo_6ul_build_basicpy_hdf5_cache.py`
   builds the BasicPy corrected RGB HDF5 cache with the selected ROI mask.
3. `run_a1_1bo_6ul_hdf5_cache_branch_c_pipeline.m`
   computes Branch C chroma `S_NAPL_color(frame)` and x-bin
   `S_NAPL_color(x,frame)` for endpoint A and B.
4. The runner validates row counts, label alignment, NaNs, and endpoint
   sensitivity, then writes `run_summary.json`.

## Default A1 1-BO 6 uL Config

Template:

```text
configs\a1_1bo_6ul_branch_c_timeseries.json
```

Default data paths:

```text
water_endpoint_dir = G:\Microfluid\00 A1 1-BO 6 UL WATER DISPLACEMENT\00 NAPL
production_dir     = G:\Microfluid\00 A1 1-BO 6 UL WATER DISPLACEMENT\01 WATER
roi_mask           = outputs\roi_templates_20260601\A1_1BO_6UL\Mask.tif
```

Default endpoint policy:

```text
A: water_ep_00_napl_00_3s_1 -> full_01_water_1s_3_p001
B: water_ep_00_napl_01_1s   -> full_00_water_3s_2_p001
```

When `expand_pages` is enabled, the manifest builder appends `_p001` to
production NAPL endpoint labels unless the suffix is already present.

Default timeline policy:

```text
time_start_s = 0.0
time_step_s  = null
```

The Branch C pipeline does not infer physical acquisition time by default.
Physical `RealTime_s` should be reconstructed as a post-processing step, using
the existing MATLAB helper:

```matlab
T = reconstruct_timeline('D:\path\to\results_*.mat')
```

`manifest.time_step_s` remains available only for explicit diagnostic sequence
axes. Do not use it as a substitute for reconstructed acquisition time.

## Pilot Run

Run a 100-page pilot first:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode pilot
```

Expected output root:

```text
outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi
```

Key output:

```text
branch_c_timeseries\a1_1bo_6ul_manual_roi_pilot100\run_summary.json
branch_c_timeseries\a1_1bo_6ul_manual_roi_pilot100\S_NAPL_color_primary_A.csv
branch_c_timeseries\a1_1bo_6ul_manual_roi_pilot100\S_NAPL_color_sensitivity_B.csv
branch_c_timeseries\a1_1bo_6ul_manual_roi_pilot100\S_NAPL_color_A_B_sensitivity_comparison.csv
branch_c_timeseries\a1_1bo_6ul_manual_roi_pilot100\S_NAPL_color_xbins_primary_A.csv
branch_c_timeseries\a1_1bo_6ul_manual_roi_pilot100\S_NAPL_color_xbins_sensitivity_B.csv
```

## Full Run

Run all pages after the pilot passes:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode full
```

The full mode uses all production pages and `fit_sample_stride = 50`.

## Dry Run

Print the exact commands without executing them:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode pilot --dry-run
```

## Rerun Selected Steps

Validate an existing run only:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode full --steps validate
```

Rebuild the cache and MATLAB outputs from an existing manifest:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode full --steps cache matlab validate
```

If you deliberately set `time_step_s` for a diagnostic sequence axis, rerun at
least:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode pilot --steps manifest cache matlab validate --force-manifest
```

Force manifest/cache overwrite:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode pilot --force
```

Resume cache construction without recomputing existing frame HDF5 files:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode full --resume-cache
```

## Change ROI

Use a different ROI mask without editing code:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode pilot --roi-mask "D:\path\to\Mask.tif"
```

The ROI mask is passed to the BasicPy HDF5 cache builder. Reusing a cache from
a different ROI is invalid; rerun at least `cache matlab validate` after changing
ROI.

## Change Output Directory

Write all outputs under a new root:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode pilot --output-root "D:\DNAPL_runs\A1_test"
```

The runner creates:

```text
<output_root>\manifests\<run_id>
<output_root>\basicpy_hdf5_cache\<run_id>
<output_root>\branch_c_timeseries\<run_id>
<output_root>\run_configs\<run_id>_effective.json
```

## Existing Output Validation

To validate the already completed 3585-page run:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode full --steps validate --manifest-dir outputs\manifests_20260601\A1_1BO_6UL_manual_roi_page_expanded_full3585 --cache-dir outputs\basicpy_hdf5_cache_page_expanded_full3585_20260601\A1_1BO_6UL_manual_roi --matlab-dir outputs\hdf5_cache_branch_c_pipeline_page_expanded_full3585_combined_fast_20260601\A1_1BO_6UL_manual_roi
```

## Validation Rules

`run_summary.json` records:

- expected vs actual time-series row counts;
- primary A / sensitivity B label alignment;
- optional `time_s` coverage and range when explicitly configured;
- missing or NaN `S_NAPL_color` values;
- missing or NaN x-bin `S_NAPL_color_xbin` values when x-bin outputs exist;
- role-level medians and p05/p95 ranges;
- A/B endpoint sensitivity statistics;
- full-NAPL rows below the configured threshold.

The x-bin output is long-format. Each `frame_index` has one row per `x_bin`;
the current MATLAB bridge uses 20 x-bins with approximately equal numbers of
flow-domain pixels per bin. To convert frame-index outputs to real time, use
`utilities/reconstruct_timeline.m` during post-processing and join by frame/page
order.

Rows labeled `full_napl` are file-level labels. If a file spans a transition,
some later pages can be below the full-NAPL threshold; the summary records this
as a warning rather than a hard failure.

## MATLAB Compatibility

Use HDF5 compression `none` for MATLAB Branch C runs. `lzf` is intentionally
blocked by the runner unless `--allow-lzf` is passed for diagnostics, because
MATLAB cannot read the existing LZF cache reliably in this workflow.
