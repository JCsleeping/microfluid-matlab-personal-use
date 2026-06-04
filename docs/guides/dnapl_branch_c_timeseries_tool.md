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
5. Optional `timeline`, `residual`, `endpointaudit`, `maskanalysis`, and
   `analysis` steps run the realtime joiner, residual trapping proxy
   postprocess, endpoint consistency postprocess, strict C2 mask-stack
   analysis, and analysis-package builder.

Optional C2 segmentation/morphology stages use the same BasicPy HDF5 cache:

```text
segpilot  -> MATLAB red-mask score/threshold sweep for pilot review
segmorph  -> MATLAB locked-threshold red-mask morphology time series
endpointaudit -> Python Branch C endpoint consistency flags from A/B CSVs
maskanalysis -> Python strict TOA/front/blob-detail postprocess from C2 HDF5/CSV
```

These stages produce segmentation-derived 2D occupancy, morphology, and
projected interface/contact metrics. They do not replace Branch C
`S_NAPL_color`.

`endpointaudit` is a postprocess for the masked endpoint-audit gate. It reads
the manifest and existing Branch C A/B CSVs; it does not rerun RGB correction or
generate new masks. Its purpose is to catch cases where a file-level
`full_napl` role spans a transition, so page 1 can pass as an endpoint while
later pages in the same TIFF are no longer full-NAPL-like.

```text
endpoint_audit\<run_id>\endpoint_consistency_timeseries.csv
endpoint_audit\<run_id>\endpoint_consistency_flags.csv
endpoint_audit\<run_id>\endpoint_consistency_source_summary.csv
endpoint_audit\<run_id>\endpoint_consistency_summary.json
```

Default gate values are:

```text
full_napl pages: S_NAPL_color_A/B >= 0.9
residual pages:  S_NAPL_color_A/B <= 0.35
```

Rows flagged by `endpointaudit` mean the expanded role label needs review. They
do not invalidate the page-1 masked endpoint audit by themselves.

`maskanalysis` reads the `segmorph` outputs directly:

```text
red_mask_stack.h5
red_mask_stack_manifest.csv
red_blob_detail_all_frames.csv
```

It writes pixel-level TOA/front and blob-detail distribution outputs without
regenerating masks from RGB:

```text
mask_stack_analysis\<run_id>\mask_stack_analysis_timeseries.csv
mask_stack_analysis\<run_id>\phase_mask_timeseries.csv
mask_stack_analysis\<run_id>\geometry_core_edge_timeseries.csv
mask_stack_analysis\<run_id>\blob_morphology_timeseries.csv
mask_stack_analysis\<run_id>\toa_x_summary.csv
mask_stack_analysis\<run_id>\toa_frame_index.npy
mask_stack_analysis\<run_id>\full_baseline_union_mask.npy
mask_stack_analysis\<run_id>\full_baseline_frequency.npy
mask_stack_analysis\<run_id>\residual_frequency.npy
mask_stack_analysis\<run_id>\residual_persistence_count.npy
mask_stack_analysis\<run_id>\last_seen_frame_index.npy
mask_stack_analysis\<run_id>\final_residual_mask.npy
mask_stack_analysis\<run_id>\phase_retention_class.npy
mask_stack_analysis\<run_id>\flow_domain_mask.npy
mask_stack_analysis\<run_id>\core_flow_mask.npy
mask_stack_analysis\<run_id>\edge_band_mask.npy
mask_stack_analysis\<run_id>\solid_distance_px.npy
mask_stack_analysis\<run_id>\solid_contact_zone_mask.npy
mask_stack_analysis\<run_id>\core_edge_qc_overlays\
mask_stack_analysis\<run_id>\mask_stack_analysis_summary.json
```

`TOA` and front/fingering proxy fields are strict C2 mask-stack outputs, not
x-zone color-index proxy crossings. `finger_count_proxy` counts contiguous
active row segments in the current leading-front band; it is not yet a
pore-graph tortuosity or branch-density analysis.

Phase-aware mask metrics use the union of rows labeled `full_napl` as the
full-NAPL baseline. Residual-role rows are then reported as retained from that
baseline, depleted from that baseline, transient residual, or new outside the
full baseline. `phase_retention_class.npy` uses this coding:

```text
0 = background / not in full baseline
1 = full baseline pixel absent in all residual frames
2 = residual transient but absent from final residual frame
3 = retained in the final residual frame
4 = residual outside the full baseline
```

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

Production role overrides may be limited to specific pages when a TIFF spans
both calibration and transition frames. Use `page_start`/`page_end`, `pages`,
or `page_ranges` on a `production_role_overrides` entry; pages outside the
selector fall back to the default filename-derived role. For example, to mark
only p001-p036 as full NAPL:

```json
{
  "production_role_overrides": [
    {
      "file_name": "03 WATER 1 SECOND_2.tif",
      "role": "full_napl",
      "page_start": 1,
      "page_end": 36
    }
  ]
}
```

Default processing metadata:

```text
physical_metadata.trusted = false
physical_metadata.processing_scale_factor = 3
```

The active A1 Branch C/C2 segmentation and morphology path records 3X
processing-grid upscale. This is provenance-only until physical calibration
fields are filled and marked trusted. Older 2X preview notes in historical
plans are not the active processing-grid contract for this runner.

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

The standalone runner can execute the same postprocess chain after Branch C/C2
outputs exist:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode full --steps validate timeline residual endpointaudit analysis
```

Use `timeline residual endpointaudit analysis` when realtime, residual, endpoint
consistency, and analysis-package outputs need to be rebuilt. If Branch C
outputs already exist and only expanded-role endpoint consistency needs review,
run:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode full --steps endpointaudit
```

If postprocess outputs already exist and only the figure/report package needs
rebuilding, run:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode full --steps maskanalysis analysis
```

Custom postprocess output locations can be supplied with `--timeline-dir`,
`--residual-dir`, `--endpoint-audit-dir`, and `--analysis-dir`.

## Physical Metadata Manifest

The runner can pass a physical metadata manifest to the analysis-package step:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode full --steps analysis --physical-metadata D:\path\to\physical_metadata.json
```

The A1 config also contains a provenance-only template. To unlock physical
derived fields, the manifest must be explicitly trusted:

```json
{
  "schema_version": 1,
  "trusted": true,
  "processing_scale_factor": 3,
  "pixel_size_um": 4.1,
  "processing_pixel_size_um": 1.3666666667,
  "flow_rate_ul_min": 6.0,
  "pore_volume_ul": 3.0,
  "channel_width_um": 1000.0,
  "channel_depth_um": 100.0,
  "viscosity_Pa_s": 0.001,
  "IFT_mN_m": 30.0,
  "temperature_C": 25.0,
  "diffusion_coefficient_m2_s": 4.3e-10,
  "surfactant_name": "",
  "surfactant_concentration": ""
}
```

Without `trusted=true` or a trusted/calibrated `metadata_status`, the package
records metadata as provenance only. It will not promote proxy outputs to
physical quantities.

When old MATLAB/postprocess metadata has already been recovered, build the
Branch C manifest from that JSON instead of manually transcribing units:

```powershell
python tools\analysis_package\build_physical_metadata_manifest.py --recovered-metadata D:\path\to\recovered_metadata.json --processing-scale-factor 3 --trusted --out D:\path\to\physical_metadata.json
```

The standalone runner can also do this conversion from config:

```json
{
  "physical_metadata_recovery": {
    "path": "D:/path/to/recovered_metadata.json",
    "trusted": true,
    "processing_scale_factor": 3
  }
}
```

The adapter maps old recovery fields into Branch C units, including
`pore_volume_m3 -> pore_volume_ul`, `channel_depth_m -> channel_depth_um`,
`flow_domain_width_m -> channel_width_um`, `active_flow_rate_ul_min`, and
`interfacial_tension (N/m) -> IFT_mN_m`. Field provenance is retained in
`field_provenance`.

Trusted metadata enables only fields with explicit formulas:

```text
processing_pixel_size_um = pixel_size_um / processing_scale_factor
dnapl_water_length_m = dnapl_water_length_px * processing_pixel_size_m * 1e-6
dnapl_solid_length_m = dnapl_solid_length_px * processing_pixel_size_m * 1e-6
PV = flow_rate_ul_min * RealTime_s / 60 / pore_volume_ul
dS_dPV = -dS_color_norm/dPV, using the existing monotone proxy rate convention
velocity_m_per_s = flow_rate / (channel_width * channel_depth)
capillary_number = viscosity * velocity / IFT
```

Mass-transfer coefficients, physical Sn, TOA, true fingering, and per-blob
shape statistics still require their own calibration or mask-stack inputs.

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

Build realtime, residual, and analysis-package outputs from existing Branch C/C2
results:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode full --steps validate timeline residual analysis
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
<output_root>\timeline_postprocess\<run_id>
<output_root>\residual_trapping_postprocess\<run_id>
<output_root>\analysis_package_<run_suffix>
<output_root>\run_configs\<run_id>_effective.json
```

## Existing Output Validation

To validate the already completed 3585-page run:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode full --steps validate --manifest-dir outputs\manifests_20260601\A1_1BO_6UL_manual_roi_page_expanded_full3585 --cache-dir outputs\basicpy_hdf5_cache_page_expanded_full3585_20260601\A1_1BO_6UL_manual_roi --matlab-dir outputs\hdf5_cache_branch_c_pipeline_page_expanded_full3585_combined_fast_20260601\A1_1BO_6UL_manual_roi
```

To validate the same existing run and rebuild realtime/residual/analysis-package
outputs in one call:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode full --steps validate timeline residual analysis --manifest-dir "outputs\manifests_20260601\A1_1BO_6UL_manual_roi_page_expanded_full3585" --cache-dir "outputs\basicpy_hdf5_cache_page_expanded_full3585_20260601\A1_1BO_6UL_manual_roi" --matlab-dir "outputs\hdf5_cache_branch_c_pipeline_page_expanded_full3585_combined_fast_20260601\A1_1BO_6UL_manual_roi" --segmentation-morphology-dir "outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\segmentation_morphology\a1_1bo_6ul_manual_roi_full3585" --timeline-dir "outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\timeline_postprocess\a1_1bo_6ul_manual_roi_full3585" --residual-dir "outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\residual_trapping_postprocess\a1_1bo_6ul_manual_roi_full3585" --analysis-dir "outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\analysis_package_full3585"
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
`core_flow_min_dist_px` threshold. After C2 `segmorph` has written
`segmentation_manifest.json`, `maskanalysis` can now recover the cached
`mask_crop.h5:/flow_domain_mask` and emit geometric core/edge outputs:

```text
core_flow = flow_domain & distance_transform_edt(flow_domain) >= core_flow_min_dist_px
edge_band = flow_domain & ~core_flow
```

For A1, the default `core_flow_min_dist_px = 3` is on the 3X processing grid.
These geometric fields are separate from x-zone fields and are written to
`geometry_core_edge_timeseries.csv` as red-mask occupancy, retained/depleted
fraction relative to the full-NAPL baseline, and regional DNAPL-water /
DNAPL-solid chain-code length split by core/edge. Boundary pixel counts are
kept as `*_boundary_px` QC fields, while the primary contact fields are:

```text
core_dnapl_water_length_px
edge_dnapl_water_length_px
core_dnapl_solid_length_px
edge_dnapl_solid_length_px
```

`core_edge_qc_overlays\` contains a core/edge region preview, a distance-map
preview, and sampled red-mask overlays on the geometric regions.

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
segmentation_morphology\<run_id>\red_mask_stack.h5
segmentation_morphology\<run_id>\red_mask_stack_manifest.csv
segmentation_morphology\<run_id>\red_blob_detail_all_frames.csv
segmentation_morphology\<run_id>\segmentation_manifest.json
segmentation_morphology\<run_id>\mask_qc_overlays_sample\
```

For the current A1 config, C2 writes the mask stack as one HDF5 file:

```text
dataset: /red_mask
type: uint8, values 0/1
grid: processing_grid
processing_scale_factor: 3
frame order: same as red_mask_timeseries.csv
```

`red_mask_stack_manifest.csv` records one row per frame with label, role,
time, mask shape, HDF5 dataset name, HDF5 frame index, score mode, threshold,
and `processing_scale_factor`. This stack is the future source for strict TOA,
fingering, and connected-mask analyses.

`red_blob_detail_all_frames.csv` records per-blob morphology on the same 3X
processing grid. Required downstream fields include `Area`,
`Area_processing_px2`, `Area_native_equiv_px2`, `AspectRatio`, `Solidity`,
`EulerNumber`, `TopologyType`, `mask_grid`, and `processing_scale_factor`.
Shape entropy, AreaGini, and stricter blob-population statistics should be
computed from this per-blob table, not from aggregate frame summaries.

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
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode full --steps analysis
```

The runner calls `tools\analysis_package\build_branch_c_analysis_package.py`
with the mode-specific default run label. The package builder can still be run
directly for diagnostics:

```powershell
python tools\analysis_package\build_branch_c_analysis_package.py --timeline-dir outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\timeline_postprocess\a1_1bo_6ul_manual_roi_full3585 --residual-dir outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\residual_trapping_postprocess\a1_1bo_6ul_manual_roi_full3585 --mask-analysis-dir outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\mask_stack_analysis\a1_1bo_6ul_manual_roi_full3585 --out-dir outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\analysis_package_full3585 --run-label "A1 1-BO 6uL full3585 Branch C/C2"
```

The package writes:

```text
analysis_package_full3585\analysis_report.md
analysis_package_full3585\run_commands.md
analysis_package_full3585\analysis_parameter_summary.csv
analysis_package_full3585\analysis_timeseries_derived.csv
analysis_package_full3585\branch_c_legacy_plot_timeseries.csv
analysis_package_full3585\analysis_qc_summary.csv
analysis_package_full3585\research_parameter_alignment.csv
analysis_package_full3585\analysis_package_provenance.json
analysis_package_full3585\figures\01_S_NAPL_color_A_B_vs_realtime.png/svg
analysis_package_full3585\figures\02_residual_zoom.png/svg
analysis_package_full3585\figures\03_red_mask_area_and_blob_morphology.png/svg
analysis_package_full3585\figures\04_xzone_S_NAPL_color.png/svg
analysis_package_full3585\figures\05_residual_trapping_summary.png/svg
analysis_package_full3585\figures\06_interface_contact_metrics.png/svg
analysis_package_full3585\figures\07_endpoint_sensitivity_and_x_extent.png/svg
analysis_package_full3585\figures\08_S_color_norm_and_rate.png/svg
analysis_package_full3585\figures\09_legacy_morphology_metrics.png/svg
analysis_package_full3585\figures\10_proxy_architecture_stage.png/svg
analysis_package_full3585\figures\11_qc_alignment_summary.png/svg
analysis_package_full3585\figures\12_mask_stack_toa_fingering.png/svg
analysis_package_full3585\figures\13_phase_aware_retention.png/svg
analysis_package_full3585\figures\14_geometric_core_edge.png/svg
```

The analysis package is read-only with respect to the source Branch C/C2 CSVs.
Its provenance JSON records input paths, output files, row counts, unmatched
label counts, current Git SHA, figure style, summary metrics, derived
parameters, and `analysis_policy_version =
branch_c_proxy_alignment_v3_recovered_metadata_gate`. Figures use the same compact Nature-style conventions as
`visualization/plot_timeseries.py`: Wong colors, white-face markers, hidden
top/right spines, light major grid, 600 dpi PNG output, and editable SVG text.

`analysis_parameter_summary.csv` records run duration, full/residual phase
counts, endpoint A/B sensitivity, red-mask occupancy, L_ow and solid-contact
metrics, residual blob morphology, x-zone extent proxies, mask-stack
TOA/front/finger proxies, phase-aware residual retention/depletion metrics,
geometric core/edge mask metrics, and blob-detail distribution statistics such
as AreaGini, ShapeEntropy, AspectRatio, Solidity, and EulerNumber. These are
operational descriptors derived from existing Branch C/C2 outputs; they do not
upgrade `S_NAPL_color` to endpoint-validated physical Sn. The package records
both all-sequence outlet-zone first-active times and residual-role-only
first-active times; the all-sequence value can be 0 min when the full-NAPL
phase is already active at the outlet.

`analysis_timeseries_derived.csv` is the main researcher-facing derived table.
It joins Branch C color-index saturation, endpoint A/B sensitivity, C2 red-mask
occupancy, blob morphology, interface/contact metrics, x-zone proxies,
mask-stack TOA/front/fingering proxies, phase-aware mask retention/depletion
fields, blob-detail distribution metrics, rate proxies, and stage/architecture
proxy labels by `label`. The compatibility columns `Sn`, `SnNorm`,
`DissolutionRate_per_min`, and related legacy names are operational
`S_NAPL_color` proxies, not endpoint-validated physical saturation.

`branch_c_legacy_plot_timeseries.csv` is a guarded adapter for the older
`visualization/plot_timeseries.py` style scripts. It includes the required
legacy column names plus semantic guard columns:

```text
Sn_semantics = operational_S_NAPL_color_proxy
InterfaceArea_semantics = legacy_alias_of_dnapl_water_length_px
AdapterWarning = not_endpoint_validated_physical_Sn
```

Use this adapter only for legacy plotting compatibility. Scientific reporting
should cite the Branch C/C2 proxy names unless the masked endpoint and
pore-volume calibration gates have passed.

The adapter does not zero-fill missing numeric fields. If a physical or
per-blob statistic is not available from the aggregate Branch C/C2 CSV inputs,
the value remains `NaN` and `analysis_qc_summary.csv` counts it under
`legacy_adapter_nonfinite_required_value_count`. This prevents missing
metadata from becoming a real zero in architecture, rate, or mass-transfer
plots.

`analysis_qc_summary.csv` records whether each downstream contract is ready.
The current standalone Branch C/C2 package can be ready for legacy time-series
plotting while still reporting:

```text
pixel_size_ready = false
pv_ready = false
mass_ready = false
true_fingering_ready = false
toa_ready = false
```

Those fields stay false until the required physical metadata or mask-stack
inputs are supplied. After `maskanalysis` passes, the package can report:

```text
mask_stack_ready = true
toa_ready = true
mask_front_fingering_ready = true
phase_aware_mask_ready = true
geometric_core_edge_ready = true
true_fingering_ready = true
blob_detail_distribution_ready = true
pore_graph_fingering_ready = false
```

Here `true_fingering_ready` means strict C2 mask-stack front/finger proxy
metrics are available. Pore-graph fingering, tortuosity, and branch-density
metrics remain gated by a separate graph/skeleton analysis.

`processing_scale_factor = 3` is recorded separately as
processing-grid provenance, and physical length conversion uses
`processing_pixel_size_um`, not native `pixel_size_um`, when the source length
is a processing-grid pixel count. Missing physical quantities are written as
`NaN`, `missing_metadata`, or `not_computable`; they are not guessed from
filenames or proxy curves.

`research_parameter_alignment.csv` maps legacy MATLAB/visualization parameter
names to one of these statuses:

```text
aligned_proxy
aligned_alias
derived_proxy
partial_proxy
missing_metadata
not_computable
```

This table is the handoff checklist for deciding what can be used immediately
and what still needs calibration metadata, pore volume, mass data, pixel size,
solid/core masks, or a full mask stack.

## MATLAB Compatibility

Use HDF5 compression `none` for MATLAB Branch C runs. `lzf` is intentionally
blocked by the runner unless `--allow-lzf` is passed for diagnostics, because
MATLAB cannot read the existing LZF cache reliably in this workflow.
