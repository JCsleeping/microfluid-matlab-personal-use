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

Optional C2 segmentation/morphology stages use the same BasicPy HDF5 cache:

```text
segpilot  -> MATLAB red-mask score/threshold sweep for pilot review
segmorph  -> MATLAB locked-threshold red-mask morphology time series
```

These stages produce segmentation-derived 2D occupancy, morphology, and
projected interface/contact metrics. They do not replace Branch C
`S_NAPL_color`.

C2 interface/contact fields are computed from the locked red DNAPL mask and the
flow-domain mask, not approximated from blob perimeters:

```text
dnapl_water_length_px / dnapl_water_length_m = DNAPL-water projected interface length, L_ow
dnapl_solid_length_px / dnapl_solid_length_m = DNAPL-solid contact length
InterfaceArea = legacy alias of dnapl_water_length_px; it is not area
solid_contact_fraction = dnapl_solid_length_px / (dnapl_water_length_px + dnapl_solid_length_px)
a_i_2D_proxy = dnapl_water_length_px / red_mask_area_px
```

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
the existing MATLAB helper for legacy `.mat` results:

```matlab
T = reconstruct_timeline('D:\path\to\results_*.mat')
```

For standalone Branch C/C2 CSV outputs, use the manifest-based joiner:

```powershell
python tools\timeline\join_branch_c_realtime.py --manifest outputs\manifests_20260601\A1_1BO_6UL_manual_roi_page_expanded_full3585\accepted_frames.csv --branch-c-dir outputs\hdf5_cache_branch_c_pipeline_page_expanded_full3585_combined_fast_20260601\A1_1BO_6UL_manual_roi --segmentation-dir outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\segmentation_morphology\a1_1bo_6ul_manual_roi_full3585 --out-dir outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\timeline_postprocess\a1_1bo_6ul_manual_roi_full3585
```

The joiner writes `frame_timeline_manifest.csv`, `timeline_join_summary.json`,
and `_realtime.csv` copies of the requested CSVs. Original Branch C/C2 CSVs are
not modified.

After realtime joining, compute residual trapping proxy metrics from Branch C
and C2 segmentation outputs:

```powershell
python tools\residual\compute_residual_trapping_metrics.py --timeline-dir outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\timeline_postprocess\a1_1bo_6ul_manual_roi_full3585 --out-dir outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\residual_trapping_postprocess\a1_1bo_6ul_manual_roi_full3585
```

This writes `residual_trapping_timeseries.csv`,
`residual_trapping_summary.csv`, and `residual_trapping_summary.json`. These
outputs are operational residual trapping proxies. They combine
`S_NAPL_color`, endpoint sensitivity, red-mask area fraction, blob morphology,
x-zone metrics, and C2 interface/contact metrics. They are not physical trapped
saturation until the endpoint and pore-volume calibration gates are complete.

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
branch_c_timeseries\a1_1bo_6ul_manual_roi_pilot100\S_NAPL_color_xzones_primary_A.csv
branch_c_timeseries\a1_1bo_6ul_manual_roi_pilot100\S_NAPL_color_xzones_sensitivity_B.csv
branch_c_timeseries\a1_1bo_6ul_manual_roi_pilot100\S_NAPL_color_xzone_A_B_sensitivity_comparison.csv
branch_c_timeseries\a1_1bo_6ul_manual_roi_pilot100\S_NAPL_color_regional_proxy_summary.json
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

Run only the C2 segmentation pilot from an existing pilot cache:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode pilot --steps segpilot validate
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
<output_root>\segmentation_pilot\<run_id>
<output_root>\segmentation_morphology\<run_id>
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
flow-domain pixels per bin. To convert frame-index outputs to real time, use the
manifest-based timeline joiner above and join by `label`.

## Regional Proxy Outputs

When x-bin outputs are present, validation also derives flow-direction x-zone
proxy metrics:

```text
S_NAPL_color_xzones_primary_A.csv
S_NAPL_color_xzones_sensitivity_B.csv
S_NAPL_color_xzone_A_B_sensitivity_comparison.csv
S_NAPL_color_regional_proxy_summary.json
```

The default x-zone definition uses the first and last 10% of x-bins as terminal
zones. With the current 20-bin bridge this means:

```text
flow_direction = left_to_right
inlet  = x-bins 1-2
mid    = x-bins 3-18
outlet = x-bins 19-20
```

These fields are operational color-index proxies:

```text
S_x_inlet
S_x_mid
S_x_outlet
S_x_terminal_mean
S_x_inlet_outlet_asymmetry
S_x_mid_minus_terminal
napl_extent_fraction_ge_0p2
napl_extent_fraction_ge_0p5
active_bin_fraction_ge_0p2
active_bin_fraction_ge_0p5
```

Breakthrough/front timing fields in the JSON summary are threshold events from
the x-bin `S_NAPL_color_xbin` signal. They are not binary-mask fingering or blob
statistics.

This is intentionally not geometric core/edge. Literature and the existing
MATLAB code use a pore geometry concept for core/edge: distance from
solid/pillar/wall boundaries, typically via `bwdist(solid_mask)` and a
`core_flow_min_dist_px` threshold. The current standalone Branch C run has only
the user-provided ROI/measurement mask, so true geometric `core_flow` and
`edge_flow` remain disabled until a solid/core mask is supplied.

## C2 Segmentation Pilot

C2 starts with a pilot threshold sweep instead of a production full run. The
default config evaluates fixed thresholds from pooled pilot percentiles for:

```text
lab_a
excess_red
chroma
normalized_red
```

Run:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode pilot --steps segpilot validate
```

Outputs:

```text
segmentation_pilot\a1_1bo_6ul_manual_roi_pilot100\threshold_sweep_all.csv
segmentation_pilot\a1_1bo_6ul_manual_roi_pilot100\threshold_sweep_lab_a.csv
segmentation_pilot\a1_1bo_6ul_manual_roi_pilot100\threshold_sweep_excess_red.csv
segmentation_pilot\a1_1bo_6ul_manual_roi_pilot100\threshold_sweep_chroma.csv
segmentation_pilot\a1_1bo_6ul_manual_roi_pilot100\threshold_sweep_normalized_red.csv
segmentation_pilot\a1_1bo_6ul_manual_roi_pilot100\candidate_summary.csv
segmentation_pilot\a1_1bo_6ul_manual_roi_pilot100\segmentation_pilot_manifest.json
segmentation_pilot\a1_1bo_6ul_manual_roi_pilot100\mask_qc_overlays\
```

Pilot pass/fail is not automatic because there is no ground-truth mask. Use the
candidate summary and overlay folders to choose one production score mode and
one locked threshold. Do not use per-frame percentile thresholds for full-run
morphology; they force every frame toward a similar red area fraction.

After selecting a threshold, edit the config:

```json
"segmentation_metrics": {
  "production_score_mode": "lab_a",
  "locked_threshold": 13.1720056533813,
  "threshold_source": "pilot_locked"
}
```

The current A1 1-BO 6 uL config is already locked to that pilot-reviewed
`lab_a` threshold. Change it only after rerunning `segpilot` for a new ROI,
dataset, correction method, or score-mode decision.

Then run pilot morphology validation:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode pilot --steps segmorph validate
```

After the pilot passes, run full morphology validation:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode full --steps segmorph validate
```

Production C2 outputs are written separately:

```text
segmentation_morphology\<run_id>\red_mask_timeseries.csv
segmentation_morphology\<run_id>\red_blob_summary_timeseries.csv
segmentation_morphology\<run_id>\red_blob_detail_all_frames.csv  (optional)
segmentation_morphology\<run_id>\segmentation_manifest.json
segmentation_morphology\<run_id>\mask_qc_overlays_sample\
```

`segmorph` requires `segmentation_metrics.locked_threshold`. If it is `null`,
the MATLAB stage stops and tells you to run/review `segpilot` first.

Rows labeled `full_napl` are file-level labels. If a file spans a transition,
some later pages can be below the full-NAPL threshold; the summary records this
as a warning rather than a hard failure.

## Residual Trapping Proxy Outputs

The residual postprocess reads realtime Branch C/C2 CSVs and writes a derived
table without changing the source files:

```text
outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\residual_trapping_postprocess\a1_1bo_6ul_manual_roi_full3585\residual_trapping_timeseries.csv
outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\residual_trapping_postprocess\a1_1bo_6ul_manual_roi_full3585\residual_trapping_summary.csv
outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\residual_trapping_postprocess\a1_1bo_6ul_manual_roi_full3585\residual_trapping_summary.json
```

Key definitions:

```text
S_color_retention_ratio_A = S_NAPL_color_A / full-role median S_NAPL_color_A
red_mask_retention_ratio  = red_mask_area_fraction / full-role median red_mask_area_fraction
L_ow_retention_ratio      = dnapl_water_length_px / full-role median dnapl_water_length_px
num_blobs_per_red_area_fraction = num_blobs / red_mask_area_fraction
InterfaceArea             = legacy alias of dnapl_water_length_px/L_ow, not area
solid_contact_fraction    = dnapl_solid_length_px / (dnapl_water_length_px + dnapl_solid_length_px)
a_i_2D_proxy              = dnapl_water_length_px / red_mask_area_px
```

The structure proxy mirrors the available parts of the MATLAB residual
architecture convention:

```text
pool-like    = largest_component_fraction >= 0.50 and num_blobs <= 10
ganglia-rich = largest_component_fraction <= 0.30 and num_blobs >= 25
mixed        = otherwise
```

The structure label is still a morphology proxy rather than the full residual
architecture classifier. `a_i_2D_proxy` is reported separately, but it is a
2D mask-derived proxy and is not yet a pore-scale calibrated interfacial area.

## Analysis Package Outputs

After the full realtime join and residual postprocess pass, build the
researcher-facing figure/report package:

```powershell
python tools\analysis_package\build_branch_c_analysis_package.py --timeline-dir outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\timeline_postprocess\a1_1bo_6ul_manual_roi_full3585 --residual-dir outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\residual_trapping_postprocess\a1_1bo_6ul_manual_roi_full3585 --out-dir outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\analysis_package_full3585 --run-label "A1 1-BO 6uL full3585 Branch C/C2"
```

The package writes:

```text
analysis_package_full3585\analysis_report.md
analysis_package_full3585\run_commands.md
analysis_package_full3585\analysis_parameter_summary.csv
analysis_package_full3585\analysis_package_provenance.json
analysis_package_full3585\figures\01_S_NAPL_color_A_B_vs_realtime.png/svg
analysis_package_full3585\figures\02_residual_zoom.png/svg
analysis_package_full3585\figures\03_red_mask_area_and_blob_morphology.png/svg
analysis_package_full3585\figures\04_xzone_S_NAPL_color.png/svg
analysis_package_full3585\figures\05_residual_trapping_summary.png/svg
analysis_package_full3585\figures\06_interface_contact_metrics.png/svg
analysis_package_full3585\figures\07_endpoint_sensitivity_and_x_extent.png/svg
```

The analysis package is read-only with respect to the source Branch C/C2 CSVs.
Its provenance JSON records input paths, output files, row counts, unmatched
label counts, current Git SHA, figure style, summary metrics, and derived
parameters. Figures use the same compact Nature-style conventions as
`visualization/plot_timeseries.py`: Wong colors, white-face markers, hidden
top/right spines, light major grid, 600 dpi PNG output, and editable SVG text.

`analysis_parameter_summary.csv` records run duration, full/residual phase
counts, endpoint A/B sensitivity, red-mask occupancy, L_ow and solid-contact
metrics, residual blob morphology, x-zone extent proxies, and outlet-zone
front timing proxies. These are operational descriptors derived from existing
Branch C/C2 CSVs; they do not upgrade `S_NAPL_color` to endpoint-validated
physical Sn. The package records both all-sequence outlet-zone first-active
times and residual-role-only first-active times; the all-sequence value can be
0 min when the full-NAPL phase is already active at the outlet.

## MATLAB Compatibility

Use HDF5 compression `none` for MATLAB Branch C runs. `lzf` is intentionally
blocked by the runner unless `--allow-lzf` is passed for diagnostics, because
MATLAB cannot read the existing LZF cache reliably in this workflow.
