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

For standalone Branch C/C2 CSV outputs, use the manifest-based joiner:

```powershell
python tools\timeline\join_branch_c_realtime.py --manifest outputs\manifests_20260601\A1_1BO_6UL_manual_roi_page_expanded_full3585\accepted_frames.csv --branch-c-dir outputs\hdf5_cache_branch_c_pipeline_page_expanded_full3585_combined_fast_20260601\A1_1BO_6UL_manual_roi --segmentation-dir outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\segmentation_morphology\a1_1bo_6ul_manual_roi_full3585 --out-dir outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\timeline_postprocess\a1_1bo_6ul_manual_roi_full3585
```

The joiner does not modify original CSVs. It writes `frame_timeline_manifest.csv`,
`timeline_join_summary.json`, and `_realtime.csv` copies with `RealTime_s`,
`Time_min`, and `Interval_s` columns.

Full 3585-page timeline join validation:

```text
status = pass
timeline rows = 3585
joined CSVs = 10
unmatched rows = 0
last RealTime_s = 10214 s
gap_policy = mtime
gap_count = 2 files
total_gap_s = 32 s
```

Validated full timeline outputs:

```text
outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\timeline_postprocess\a1_1bo_6ul_manual_roi_full3585\frame_timeline_manifest.csv
outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\timeline_postprocess\a1_1bo_6ul_manual_roi_full3585\timeline_join_summary.json
outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\timeline_postprocess\a1_1bo_6ul_manual_roi_full3585\S_NAPL_color_primary_A_realtime.csv
outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\timeline_postprocess\a1_1bo_6ul_manual_roi_full3585\S_NAPL_color_xbins_primary_A_realtime.csv
outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\timeline_postprocess\a1_1bo_6ul_manual_roi_full3585\red_mask_timeseries_realtime.csv
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

Full 3585-page x-bin validation:

```text
status = pass
rows = 3585 primary / 3585 sensitivity / 3585 comparison
xbin rows = 71700 primary / 71700 sensitivity
NaNs = 0
A xbin median S_NAPL_color_xbin = 0.155363
B xbin median S_NAPL_color_xbin = 0.150433
A residual xbin median = 0.151238
B residual xbin median = 0.147391
```

## 2026-06-02 Regional Proxy Extension

The standalone validation step now derives x-zone regional proxy outputs when
the MATLAB x-bin CSVs are present:

```text
S_NAPL_color_xzones_primary_A.csv
S_NAPL_color_xzones_sensitivity_B.csv
S_NAPL_color_xzone_A_B_sensitivity_comparison.csv
S_NAPL_color_regional_proxy_summary.json
```

The default x-zone definition is flow-direction based, not geometric core/edge:

```text
flow_direction = left_to_right
terminal_zone_fraction = 0.1
inlet  = first 10% of x-bins
mid    = non-terminal x-bins
outlet = last 10% of x-bins
```

The CSVs expose operational color-index metrics including `S_x_inlet`,
`S_x_mid`, `S_x_outlet`, terminal/mid asymmetry, thresholded extent fraction,
and active-bin fraction. The JSON summary records first outlet/domain events at
the configured thresholds.

Full 3585-page x-zone / front-proxy validation:

```text
status = pass
xzone rows = 3585 primary / 3585 sensitivity / 3585 comparison
A xzone mid median = 0.150015
B xzone mid median = 0.148435
A residual S_x_inlet / S_x_mid / S_x_outlet =
  0.151721 / 0.149931 / 0.211507
B residual S_x_inlet / S_x_mid / S_x_outlet =
  0.148204 / 0.148351 / 0.211022
outlet_first_le_0p5 = frame 439, full_01_water_1s_3_p010
domain_active_fraction_le_5pct_0p5 = frame 450, full_01_water_1s_3_p021
```

Full x-bin / x-zone outputs:

```text
outputs\hdf5_cache_branch_c_pipeline_page_expanded_full3585_combined_fast_20260601\A1_1BO_6UL_manual_roi\S_NAPL_color_xbins_primary_A.csv
outputs\hdf5_cache_branch_c_pipeline_page_expanded_full3585_combined_fast_20260601\A1_1BO_6UL_manual_roi\S_NAPL_color_xbins_sensitivity_B.csv
outputs\hdf5_cache_branch_c_pipeline_page_expanded_full3585_combined_fast_20260601\A1_1BO_6UL_manual_roi\S_NAPL_color_xzones_primary_A.csv
outputs\hdf5_cache_branch_c_pipeline_page_expanded_full3585_combined_fast_20260601\A1_1BO_6UL_manual_roi\S_NAPL_color_xzones_sensitivity_B.csv
outputs\hdf5_cache_branch_c_pipeline_page_expanded_full3585_combined_fast_20260601\A1_1BO_6UL_manual_roi\S_NAPL_color_regional_proxy_summary.json
```

True geometric `core_flow` / `edge_flow` remains a later gate. It requires a
solid/core mask and should follow the existing MATLAB convention based on
distance from solid/pillar/wall boundaries, such as
`core_flow = flow_domain & bwdist(solid_mask) >= core_flow_min_dist_px`.

## 2026-06-02 C2 Segmentation Pilot Extension

Added a separate C2 MATLAB HDF5 stage:

```text
run_a1_1bo_6ul_hdf5_cache_segmentation_morphology.m
```

The standalone runner now accepts:

```text
segpilot  -> red-score threshold sweep and overlay review outputs
segmorph  -> locked-threshold red-mask morphology outputs
```

The C2 branch is deliberately separate from Branch C. It outputs
segmentation-derived red-mask 2D occupancy, blob morphology, and projected
interface/contact metrics, not endpoint-normalized `Sn`.

Pilot command:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode pilot --steps segpilot validate
```

Pilot result:

```text
status = pass
threshold sweep rows = 2040
candidate rows = 20
overlay PNGs = 240
score modes = lab_a / excess_red / chroma / normalized_red
threshold percentiles = 90 / 92.5 / 95 / 97.5 / 99
```

Candidate examples from the pilot:

```text
lab_a pct 92.5:
  full median red area fraction     = 0.387557
  residual median red area fraction = 0.072128
  separation                        = 0.315429

excess_red pct 92.5:
  full median red area fraction     = 0.420129
  residual median red area fraction = 0.071271
  separation                        = 0.348858
```

These are pilot diagnostics only. A production `segmorph` run must wait until a
score mode and locked threshold are selected from overlay review.

Locked C2 pilot morphology candidate:

```text
production_score_mode = lab_a
locked_threshold = 13.1720056533813
threshold_source = pilot_locked
```

Pilot morphology validation:

```text
status = pass
red_mask_timeseries rows = 102
red_blob_summary rows = 102
NaNs = 0
sample overlay PNGs = 12
red_mask_area_fraction median = 0.072146
full_napl median red_mask_area_fraction = 0.387557
residual median red_mask_area_fraction = 0.072128
```

The full-NAPL role still contains a low red-mask row because the role is a
file-level label and one accepted page spans a transition. This remains a label
provenance warning, not a C2 morphology failure.

Full 3585-page C2 morphology validation:

```text
status = pass
red_mask_timeseries rows = 3585
red_blob_summary rows = 3585
NaNs = 0
sample overlay PNGs = 12
red_mask_area_fraction median = 0.071369
full_napl median red_mask_area_fraction = 0.386689
residual median red_mask_area_fraction = 0.071349
num_blobs median = 601
dnapl_water_length_px median = 41453.624643
dnapl_solid_length_px median = 148.911688
solid_contact_fraction median = 0.003579
a_i_2D_proxy median = 0.323424
InterfaceArea alias mismatches = 0
interface/contact validation failures = 0
```

Interface/contact semantics:

```text
dnapl_water_length_px / dnapl_water_length_m = DNAPL-water projected interface length, L_ow
dnapl_solid_length_px / dnapl_solid_length_m = DNAPL-solid contact length
InterfaceArea = legacy alias of dnapl_water_length_px; it is not area
solid_contact_fraction = dnapl_solid_length_px / (dnapl_water_length_px + dnapl_solid_length_px)
a_i_2D_proxy = dnapl_water_length_px / red_mask_area_px
```

Full C2 outputs:

```text
outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\segmentation_morphology\a1_1bo_6ul_manual_roi_full3585\red_mask_timeseries.csv
outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\segmentation_morphology\a1_1bo_6ul_manual_roi_full3585\red_blob_summary_timeseries.csv
outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\segmentation_morphology\a1_1bo_6ul_manual_roi_full3585\segmentation_manifest.json
```

## 2026-06-02 Residual Trapping Proxy Postprocess

Added a standalone residual postprocess:

```text
tools/residual/compute_residual_trapping_metrics.py
```

It reads realtime Branch C/C2 CSVs, joins by `label`, and writes derived
residual trapping proxy metrics without modifying the source files.

Command used for the full 3585-page run:

```powershell
python tools\residual\compute_residual_trapping_metrics.py --timeline-dir outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\timeline_postprocess\a1_1bo_6ul_manual_roi_full3585 --out-dir outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\residual_trapping_postprocess\a1_1bo_6ul_manual_roi_full3585
```

Outputs:

```text
outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\residual_trapping_postprocess\a1_1bo_6ul_manual_roi_full3585\residual_trapping_timeseries.csv
outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\residual_trapping_postprocess\a1_1bo_6ul_manual_roi_full3585\residual_trapping_summary.csv
outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\residual_trapping_postprocess\a1_1bo_6ul_manual_roi_full3585\residual_trapping_summary.json
```

Full-run result:

```text
status = pass
rows = 3585
full rows = 498
residual rows = 3087
missing mask labels = 0
A residual median S_NAPL_color = 0.154290
B residual median S_NAPL_color = 0.152606
residual median red_mask_area_fraction = 0.071349
residual median red_mask_retention_ratio = 0.184512
full median dnapl_water_length_px = 149993.840506
residual median dnapl_water_length_px = 41428.387053
residual median dnapl_solid_length_px = 145.941125
residual median L_ow_retention_ratio = 0.276201
residual median solid_contact_fraction = 0.003508
residual median a_i_2D_proxy = 0.323531
residual median num_blobs = 602
residual median largest_component_fraction = 0.027627
residual median ganglia_area_fraction = 0.906160
final residual label = residual_02_water_3s_42_p063
final residual RealTime_s = 10214
final residual S_NAPL_color_A = 0.153737
final residual red_mask_area_fraction = 0.071089
final residual dnapl_water_length_px = 41249.114975
final residual dnapl_solid_length_px = 80.083261
final residual L_ow_retention_ratio = 0.275005
final residual solid_contact_fraction = 0.001938
final residual a_i_2D_proxy = 0.323317
final residual structure_proxy = ganglia-rich
```

The structure proxy uses only fields available in the C2 CSV:

```text
pool-like    = largest_component_fraction >= 0.50 and num_blobs <= 10
ganglia-rich = largest_component_fraction <= 0.30 and num_blobs >= 25
mixed        = otherwise
```

This mirrors the available parts of `analysis/classify_residual_architecture.m`.
`a_i_2D_proxy` is now reported separately from C2 interface columns, but it is a
2D mask-derived proxy and should not be interpreted as pore-scale calibrated
interfacial area.

## 2026-06-02 Full3585 Analysis Package

Added a standalone package builder:

```text
tools/analysis_package/build_branch_c_analysis_package.py
```

Command used:

```powershell
python tools\analysis_package\build_branch_c_analysis_package.py --timeline-dir outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\timeline_postprocess\a1_1bo_6ul_manual_roi_full3585 --residual-dir outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\residual_trapping_postprocess\a1_1bo_6ul_manual_roi_full3585 --out-dir outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\analysis_package_full3585 --run-label "A1 1-BO 6uL full3585 Branch C/C2"
```

Package result:

```text
status = pass
figures = 6 PNG + 6 SVG
primary rows = 3585
full rows = 498
residual rows = 3087
missing label counts = 0 for mask/sensitivity/comparison/blob/xzone
git_head = e6e8ba01d69882e5f6574d295ac499c8a5d0d3b7
```

Outputs:

```text
outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\analysis_package_full3585\analysis_report.md
outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\analysis_package_full3585\run_commands.md
outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\analysis_package_full3585\analysis_package_provenance.json
outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\analysis_package_full3585\figures\
```

Figure set:

```text
01_S_NAPL_color_A_B_vs_realtime
02_residual_zoom
03_red_mask_area_and_blob_morphology
04_xzone_S_NAPL_color
05_residual_trapping_summary
06_interface_contact_metrics
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
