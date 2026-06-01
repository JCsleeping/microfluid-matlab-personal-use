# A1 1-BO 6 uL Page-Expanded Full Time-Series Run

Date: 2026-06-01

## Purpose

Run the manifest-driven BasicPy HDF5 Branch C workflow beyond file-level page 1:

1. Run a 100-page pilot.
2. Run the full 3585-page time series.
3. Verify the output before turning the flow into a standalone non-agent tool.

The output remains operational `S_NAPL_color(t)`, not final physical `Sn`.

## Inputs

- Production image directory: `G:\Microfluid\00 A1 1-BO 6 UL WATER DISPLACEMENT\01 WATER`
- Water endpoint directory: `G:\Microfluid\00 A1 1-BO 6 UL WATER DISPLACEMENT\00 NAPL`
- Manual ROI mask: `outputs\roi_templates_20260601\A1_1BO_6UL\Mask.tif`
- Score mode: `chroma`
- Statistic: `winsorized_mean`, 1-99 percentile winsorization
- Endpoint policy:
  - A: water `water_ep_00_napl_00_3s_1`, NAPL `full_01_water_1s_3_p001`
  - B: water `water_ep_00_napl_01_1s`, NAPL `full_00_water_3s_2_p001`

## Pilot Result

The 100-page pilot manifest contained 105 rows:

- 3 water endpoint rows
- 102 time-series pages
- 16 fit-sample rows

The gzip pilot completed in MATLAB:

| Endpoint | Full median | Residual median | Bridge pass |
| --- | ---: | ---: | --- |
| A | 1.000000 | 0.171867 | true |
| B | 0.998511 | 0.170145 | true |

The lzf cache was rejected by MATLAB because the HDF5 lzf filter is not registered. Gzip is MATLAB-readable but slow. For MATLAB full runs, use uncompressed HDF5.

## Full Manifest And Cache

Full page-expanded manifest:

`outputs\manifests_20260601\A1_1BO_6UL_manual_roi_page_expanded_full3585\accepted_frames.csv`

Manifest summary:

- Total cache rows: 3588
- Time-series rows: 3585
- Water endpoint rows: 3
- Full-NAPL-labeled rows: 498
- Residual rows: 3087
- Fit-sample rows: 77

Full BasicPy HDF5 cache:

`outputs\basicpy_hdf5_cache_page_expanded_full3585_20260601\A1_1BO_6UL_manual_roi`

Cache sanity check:

- `frames\*.h5` count: 3588
- `cache_manifest.json` frame count: 3588
- `cache_manifest.json` time-series count: 3585
- HDF5 compression: none

## MATLAB Full Run

The original bridge path was too slow for the full run because it recomputed reference chroma maps and unused regional diagnostics for every frame and endpoint. It was stopped before producing output.

The bridge was updated with a combined chroma fast path:

- Read each frame once.
- Compute masked chroma once per frame.
- Normalize against endpoint A and B in the same sweep.
- Precompute water/NAPL reference scores once per endpoint.
- Print progress as `BRIDGE_PROGRESS_AB`.

Full output directory:

`outputs\hdf5_cache_branch_c_pipeline_page_expanded_full3585_combined_fast_20260601\A1_1BO_6UL_manual_roi`

Main outputs:

- `S_NAPL_color_primary_A.csv`
- `S_NAPL_color_sensitivity_B.csv`
- `S_NAPL_color_A_B_sensitivity_comparison.csv`
- `branch_c_cache_pipeline_summary.csv`
- `cache_branch_c_manifest.json`
- `S_NAPL_color_A_B_sensitivity.png`

Summary:

| Endpoint | Full median | Residual median | Bridge pass |
| --- | ---: | ---: | --- |
| A | 1.000000 | 0.154290 | true |
| B | 0.998529 | 0.152606 | true |

Sanity checks:

- A rows: 3585
- B rows: 3585
- Comparison rows: 3585
- A/B labels match: true
- A NaN count: 0
- B NaN count: 0
- A range: 0.152940 to 1.000000
- B range: 0.151256 to 1.000000
- Endpoint sensitivity median: 0.001684
- Endpoint sensitivity p95: 0.001685
- Endpoint sensitivity max: 0.001825

Role-level summary:

| Endpoint | Role | Count | Min | Median | Max |
| --- | --- | ---: | ---: | ---: | ---: |
| A | full_napl | 498 | 0.157941 | 1.000000 | 1.000000 |
| A | residual | 3087 | 0.152940 | 0.154290 | 0.157224 |
| B | full_napl | 498 | 0.156256 | 0.998529 | 1.000000 |
| B | residual | 3087 | 0.151256 | 0.152606 | 0.155540 |

## Important Interpretation

The low minimum in the `full_napl` role is not a numerical failure. The source group `full_01_water_1s_3` transitions after early pages:

- `full_01_water_1s_3_p001` to about `p009` are near full NAPL.
- From `p010` onward the score falls quickly.
- 53 rows in this file group fall below `S_NAPL_color < 0.5`.

Therefore `full_napl` is a user-provided role label for the source file group, not proof that every page in that file is full saturation. For endpoint validation and summary statistics, page-level state detection or role refinement is needed.

## Repro Commands

Create the full manifest:

```powershell
python run_a1_1bo_6ul_make_full_frames_manifest.py --expand-pages --fit-sample-stride 50 --out-dir "outputs\manifests_20260601\A1_1BO_6UL_manual_roi_page_expanded_full3585" --force
```

Build the uncompressed BasicPy HDF5 cache:

```powershell
python run_a1_1bo_6ul_build_basicpy_hdf5_cache.py --manifest "outputs\manifests_20260601\A1_1BO_6UL_manual_roi_page_expanded_full3585\accepted_frames.csv" --out "outputs\basicpy_hdf5_cache_page_expanded_full3585_20260601\A1_1BO_6UL_manual_roi" --batch-size 20 --compression none --force
```

Run MATLAB Branch C:

```powershell
matlab -batch "cd('D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\.worktrees\interpolation-assisted-segmentation-20260527'); outputs = run_a1_1bo_6ul_hdf5_cache_branch_c_pipeline('outputs\basicpy_hdf5_cache_page_expanded_full3585_20260601\A1_1BO_6UL_manual_roi','outputs\hdf5_cache_branch_c_pipeline_page_expanded_full3585_combined_fast_20260601\A1_1BO_6UL_manual_roi','outputs\manifests_20260601\A1_1BO_6UL_manual_roi_page_expanded_full3585\endpoint_policy.json'); disp(outputs.summary(:, {'endpoint_short_name','matlab_full_median','matlab_residual_median','comparison_available','bridge_pass'}));"
```

## Next Tooling Step

Build a standalone runner so the same workflow can be run without an agent:

- One config file for paths, ROI mask, output root, endpoints, page range, and compression.
- One command for pilot mode.
- One command for full mode.
- Resume support for HDF5 cache generation.
- Progress logs and CSV sanity checks.
- Explicit warning when a full-NAPL-labeled file contains page-level low-saturation sections.
