# DNAPL Branch C Standalone Tool

Date: 2026-06-01

## Purpose

Create an agent-independent runner for the BasicPy HDF5 + MATLAB Branch C
`S_NAPL_color` workflow so the run can be repeated later with a different
ROI mask, output directory, or selected stage list.

## Added Entry Point

```text
run_dnapl_branch_c_timeseries_tool.py
```

Default configuration:

```text
configs/a1_1bo_6ul_branch_c_timeseries.json
```

User guide:

```text
docs/guides/dnapl_branch_c_timeseries_tool.md
```

The tool orchestrates:

1. manifest generation;
2. BasicPy HDF5 cache construction;
3. MATLAB Branch C chroma `S_NAPL_color(frame)` and x-bin `S_NAPL_color(x,frame)`;
4. output validation and `run_summary.json`.

## Verification

Syntax check:

```powershell
python -m py_compile run_dnapl_branch_c_timeseries_tool.py run_a1_1bo_6ul_make_full_frames_manifest.py run_a1_1bo_6ul_build_basicpy_hdf5_cache.py
```

Dry-run command check:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode pilot --dry-run
```

Existing 3585-page validation:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode full --steps validate --manifest-dir outputs\manifests_20260601\A1_1BO_6UL_manual_roi_page_expanded_full3585 --cache-dir outputs\basicpy_hdf5_cache_page_expanded_full3585_20260601\A1_1BO_6UL_manual_roi --matlab-dir outputs\hdf5_cache_branch_c_pipeline_page_expanded_full3585_combined_fast_20260601\A1_1BO_6UL_manual_roi
```

Result:

```text
status = pass
rows = 3585 primary / 3585 sensitivity / 3585 comparison
NaNs = 0
endpoint sensitivity median = 0.001684
```

100-page pilot generated through the standalone tool:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode pilot --steps manifest --force-manifest
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode pilot --steps cache matlab validate
```

Pilot output:

```text
outputs/standalone_branch_c_runs_20260601/A1_1BO_6UL_manual_roi/branch_c_timeseries/a1_1bo_6ul_manual_roi_pilot100/run_summary.json
```

Pilot result:

```text
status = pass
rows = 102 primary / 102 sensitivity / 102 comparison
NaNs = 0
A full median = 1.000000
A residual median = 0.171867
B full median = 0.998511
B residual median = 0.170145
endpoint sensitivity median = 0.001722
```

The pilot reports one `full_napl` row below 0.5
(`full_01_water_1s_3_p043`). This is treated as a warning because the role is a
file-level label and the file can span a transition.

## 2026-06-02 Time and X-Bin Extension

The standalone tool can pass a configurable sequence time axis through the
manifest, BasicPy cache, MATLAB Branch C outputs, comparison CSV, and
`run_summary.json`. This is disabled by default because real acquisition time
is a post-processing concern.

Default config:

```text
manifest.time_start_s = 0.0
manifest.time_step_s = null
```

For physical elapsed time, use `utilities/reconstruct_timeline.m` on the
downstream MATLAB result `.mat`, for example:

```matlab
T = reconstruct_timeline('D:\path\to\results_*.mat')
```

The MATLAB bridge now also writes long-format x-bin outputs:

```text
S_NAPL_color_xbins_primary_A.csv
S_NAPL_color_xbins_sensitivity_B.csv
```

The x-bins are computed from flow-domain mask pixels sorted by x coordinate.
The current setting uses 20 bins with approximately equal pixel counts per bin.

Updated pilot validation:

```text
status = pass
rows = 102 primary / 102 sensitivity / 102 comparison
xbin rows = 2040 primary / 2040 sensitivity
time_s = blank by default
NaNs = 0
A full median = 1.000000
A residual median = 0.171867
B full median = 0.998511
B residual median = 0.170145
endpoint sensitivity median = 0.001722
```

## Usage Notes

For a new ROI, rerun at least:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode pilot --roi-mask "D:\path\to\Mask.tif"
```

For a new output location:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode pilot --output-root "D:\DNAPL_runs\A1_test"
```

After pilot validation passes, run the full series:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode full
```
