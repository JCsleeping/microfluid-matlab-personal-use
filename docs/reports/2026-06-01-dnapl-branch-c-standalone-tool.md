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

Initial package result before the 2026-06-03 style/parameter expansion:

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

This figure set is superseded by the 11-figure analysis package documented in
the 2026-06-03 sections below.

## 2026-06-03 Analysis Package Style and Parameter Expansion

Updated `tools/analysis_package/build_branch_c_analysis_package.py` so the
analysis-package figures follow the existing `visualization/plot_timeseries.py`
Nature-style conventions:

```text
figure_style = nature_timeseries_v1
Wong color palette
white-face line markers with sparse markevery
hidden top/right axes, light major grid, minor ticks
600 dpi PNG output and editable SVG text
```

The package also now writes:

```text
analysis_parameter_summary.csv
07_endpoint_sensitivity_and_x_extent.png/svg
```

Supplemented parameters include:

```text
run duration and full/residual phase duration
endpoint A/B sensitivity median/p95/max
full/residual S_NAPL_color and red-mask retention ratios
full/residual L_ow, solid-contact fraction, and a_i_2D proxy
blob count, largest connected component, droplet/column/cluster fractions
x-zone S_NAPL_color and active/extent fraction proxies
all-sequence and residual-role first outlet-zone ge_0p2/ge_0p5 timing proxies
```

These outputs remain operational Branch C/C2 descriptors. They are derived from
the existing realtime CSVs and residual postprocess summary, and do not change
the source CSVs or claim endpoint-validated physical Sn.

## 2026-06-03 Legacy Research Parameter Alignment

Extended the analysis-package builder so the standalone Branch C/C2 pipeline
can generate the parameters that are currently computable from existing
realtime, segmentation, and residual-proxy CSVs, while explicitly marking the
quantities that still require physical metadata or mask-stack inputs.

New output tables:

```text
analysis_timeseries_derived.csv
branch_c_legacy_plot_timeseries.csv
analysis_qc_summary.csv
research_parameter_alignment.csv
```

Policy recorded in provenance:

```text
analysis_policy_version = branch_c_proxy_alignment_v1
```

The derived time-series table now includes:

```text
Branch C S_NAPL_color A/B and endpoint sensitivity
S_color_norm / Sn / SnNorm proxy columns
DissolutionRate_* proxy columns
full/residual stage labels and near-depleted flags
red_mask_area_fraction and retention proxies
blob count, size, largest-component, circularity, and Req proxies
droplet/column/cluster area and count fractions
dnapl_water_length_px / dnapl_water_length_m
dnapl_solid_length_px / dnapl_solid_length_m
InterfaceArea as a legacy alias of dnapl_water_length_px
solid_contact_fraction and a_i_2D proxy
x-zone inlet/mid/outlet and front/extent proxies
```

The legacy plotting adapter is intentionally guarded. It exposes the old column
names needed by scripts such as `visualization/plot_timeseries.py`, but also
writes:

```text
Sn_semantics = operational_S_NAPL_color_proxy
InterfaceArea_semantics = legacy_alias_of_dnapl_water_length_px
AdapterWarning = not_endpoint_validated_physical_Sn
```

Missing physical quantities are not inferred. `analysis_qc_summary.csv` and
`research_parameter_alignment.csv` mark pore volume, pixel size, mass data,
true fingering/TOA mask-stack metrics, and other unavailable physical outputs
as `missing_metadata` or `not_computable`.

The legacy plotting adapter is plot-only and guarded; it does not zero-fill
missing numeric values. Unavailable physical or per-blob fields remain `NaN`,
and QC records them under:

```text
legacy_adapter_nonfinite_required_value_count
```

The alignment registry was expanded to cover physical metadata from
`visualization/recover_experiment_metadata.py`, window/mass-rate names from
rate-correlation utilities, per-blob morphology fields such as aspect ratio,
solidity, Euler number, AreaGini, size-distribution slope, and shape entropy,
plus true fingering/TOA fields that require a frame-level mask stack.

The analysis package figure set is now:

```text
01_S_NAPL_color_A_B_vs_realtime
02_residual_zoom
03_red_mask_area_and_blob_morphology
04_xzone_S_NAPL_color
05_residual_trapping_summary
06_interface_contact_metrics
07_endpoint_sensitivity_and_x_extent
08_S_color_norm_and_rate
09_legacy_morphology_metrics
10_proxy_architecture_stage
11_qc_alignment_summary
```

Verification after implementation:

```text
python -m py_compile tools\analysis_package\build_branch_c_analysis_package.py
python -m pytest tests\test_branch_c_analysis_package.py -q
python -m pytest tests\test_branch_c_analysis_package.py tests\test_branch_c_timeseries_tool.py tests\test_residual_trapping_metrics.py -q
```

Result:

```text
1 passed
5 passed
```

Full3585 compatibility checks after regenerating the package:

```powershell
python visualization\plot_timeseries.py "outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\analysis_package_full3585" --csv "outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\analysis_package_full3585\branch_c_legacy_plot_timeseries.csv" --figures-dir "C:\tmp\branch_c_legacy_plot_timeseries_verify" --dpi 120
python visualization\plot_rate_correlations.py "outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\analysis_package_full3585" --csv "outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\analysis_package_full3585\branch_c_legacy_plot_timeseries.csv" --figures-dir "C:\tmp\branch_c_legacy_rate_verify" --dpi 120
```

Result:

```text
plot_timeseries.py read 3585 rows and completed
plot_rate_correlations.py read 3585 rows and completed
legacy_plot_timeseries_ready = true
legacy_adapter_nonfinite_required_value_count = 0
research_parameter_alignment rows = 62
```

## 2026-06-03 Runner Postprocess Step Integration

Extended `run_dnapl_branch_c_timeseries_tool.py` with standard postprocess
steps:

```text
timeline -> tools/timeline/join_branch_c_realtime.py
residual -> tools/residual/compute_residual_trapping_metrics.py
analysis -> tools/analysis_package/build_branch_c_analysis_package.py
```

The runner now resolves default directories:

```text
<output_root>\timeline_postprocess\<run_id>
<output_root>\residual_trapping_postprocess\<run_id>
<output_root>\analysis_package_<run_suffix>
```

Mode-specific A1 run labels are recorded in
`configs/a1_1bo_6ul_branch_c_timeseries.json`:

```text
A1 1-BO 6uL pilot100 Branch C/C2
A1 1-BO 6uL full3585 Branch C/C2
```

Command used to verify the existing full3585 outputs:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode full --steps validate timeline residual analysis --manifest-dir "outputs\manifests_20260601\A1_1BO_6UL_manual_roi_page_expanded_full3585" --cache-dir "outputs\basicpy_hdf5_cache_page_expanded_full3585_20260601\A1_1BO_6UL_manual_roi" --matlab-dir "outputs\hdf5_cache_branch_c_pipeline_page_expanded_full3585_combined_fast_20260601\A1_1BO_6UL_manual_roi" --segmentation-morphology-dir "outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\segmentation_morphology\a1_1bo_6ul_manual_roi_full3585" --timeline-dir "outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\timeline_postprocess\a1_1bo_6ul_manual_roi_full3585" --residual-dir "outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\residual_trapping_postprocess\a1_1bo_6ul_manual_roi_full3585" --analysis-dir "outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\analysis_package_full3585"
```

Result:

```text
run_summary.status = pass
timeline_join_summary.status = pass
timeline rows = 3585
residual_trapping_summary.status = pass
residual timeseries rows = 3585
analysis_package.status = pass
analysis figures = 11 PNG + 11 SVG (pre-maskanalysis package)
analysis_timeseries_derived rows = 3585
branch_c_legacy_plot_timeseries rows = 3585
run_summary.commands = 3 postprocess commands
```

The physical-metadata gate remains unchanged: postprocess integration does not
promote proxy outputs to physical quantities. Pixel size, PV, mass-transfer,
endpoint-validation, and mask-stack dependent metrics still require their own
trusted metadata/validation inputs before they can be marked calibrated.

## 2026-06-03 Physical Metadata Gate and 3X Scale Update

Added an optional physical metadata manifest path to the standalone runner and
analysis-package builder:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode full --steps analysis --physical-metadata D:\path\to\physical_metadata.json
```

The A1 config now records the active processing-grid scale as provenance:

```text
physical_metadata.trusted = false
physical_metadata.processing_scale_factor = 3
```

This reflects the 019e8b57-254a-7131-aa7f-20e379729629 update from 2X to 3X.
Historical 2X preview plans remain historical notes; the current standalone A1
Branch C/C2 processing contract is 3X.

The metadata gate is intentionally conservative:

```text
trusted=false or missing metadata -> provenance only
trusted=true or trusted/calibrated metadata_status -> physical derivations allowed
```

Trusted metadata can unlock:

```text
dnapl_water_length_m
dnapl_solid_length_m
PV
dS_dPV
velocity_m_per_s
capillary_number
```

The package still does not infer physical Sn, mass-transfer coefficients,
TOA, fingering, or per-blob shape distributions from aggregate proxy CSVs.
TOA/front/blob-distribution outputs are unlocked only when `maskanalysis`
consumes the per-frame C2 mask stack and blob-detail inputs. Physical Sn and
mass-transfer quantities remain gated by endpoint audit and mass calibration.

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

## 2026-06-04 Strict C2 Mask-Stack TOA / Fingering / Blob Detail Analysis

Added the standalone `maskanalysis` runner step:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config configs\a1_1bo_6ul_branch_c_timeseries.json --mode full --steps maskanalysis analysis
```

The step calls:

```text
tools\mask_stack_analysis\analyze_c2_mask_stack.py
```

Inputs are the locked C2 segmentation artifacts:

```text
red_mask_stack.h5
red_mask_stack_manifest.csv
red_blob_detail_all_frames.csv
```

The strict postprocess writes:

```text
mask_stack_analysis_timeseries.csv
phase_mask_timeseries.csv
geometry_core_edge_timeseries.csv
blob_morphology_timeseries.csv
toa_x_summary.csv
toa_frame_index.npy
full_baseline_union_mask.npy
full_baseline_frequency.npy
residual_frequency.npy
residual_persistence_count.npy
last_seen_frame_index.npy
final_residual_mask.npy
phase_retention_class.npy
flow_domain_mask.npy
core_flow_mask.npy
edge_band_mask.npy
solid_distance_px.npy
solid_contact_zone_mask.npy
core_edge_qc_overlays\
mask_stack_analysis_summary.json
```

For the A1 full3585 chunked-blob-detail run:

```text
mask_stack_analysis.status = pass
mask_stack_analysis_timeseries rows = 3585
phase_mask_timeseries rows = 3585
geometry_core_edge_timeseries rows = 3585
blob_morphology_timeseries rows = 3585
toa_x_summary rows = 2391
mask_stack_ready = true
toa_ready = true
mask_front_fingering_ready = true
phase_aware_mask_ready = true
geometric_core_edge_ready = true
blob_detail_distribution_ready = true
```

The regenerated analysis package now reports:

```text
analysis_package.status = pass
analysis figures = 14 PNG + 14 SVG
analysis_timeseries_derived rows = 3585
research_parameter_alignment.TOA = aligned_mask_stack
research_parameter_alignment.full_NAPL_baseline_mask = aligned_phase_mask
research_parameter_alignment.residual_persistence_map = aligned_phase_mask
research_parameter_alignment.depletion/last_seen_map = aligned_phase_mask
research_parameter_alignment.geometric_core_edge_regions = aligned_geometric_mask
research_parameter_alignment.edge_retention = aligned_geometric_mask
research_parameter_alignment.mask_stack_front = aligned_mask_stack
research_parameter_alignment.true_fingering = aligned_mask_stack_proxy
research_parameter_alignment.AreaGini = aligned_blob_detail
research_parameter_alignment.AspectRatio* = aligned_blob_detail
research_parameter_alignment.Solidity* = aligned_blob_detail
research_parameter_alignment.EulerNumber* = aligned_blob_detail
research_parameter_alignment.shape_entropy = aligned_blob_detail
```

Semantic boundary:

```text
TOA/front/finger fields come from C2 red_mask_stack.h5, not x-zone color proxies.
finger_count_proxy is a mask-stack leading-front-band proxy, not pore-graph branch density.
phase-aware residual metrics use the union of full_napl role C2 masks as the baseline.
geometric core/edge metrics use flow_domain distance on the 3X C2 processing grid.
core/edge contact length fields use C2 chain-code adjacency; boundary-pixel counts remain QC fields.
pore_graph_fingering_ready remains false until graph/skeleton analysis is added.
```

The phase-aware outputs answer a different question from TOA: given the
full-NAPL baseline mask, how much red DNAPL support remains in residual frames,
how much has depleted, and where residual mask support appears outside the
baseline. `phase_retention_class.npy` is a compact map of those classes:

```text
0 = background / not in full baseline
1 = full baseline pixel absent in all residual frames
2 = residual transient but absent from final residual frame
3 = retained in the final residual frame
4 = residual outside the full baseline
```

For the A1 full3585 chunked-blob-detail rerun, the phase-aware summary was:

```text
full_frame_count = 498
residual_frame_count = 3087
full_baseline_area_px = 825419
residual_union_fraction_of_full = 0.227351
final_residual_retained_from_full_fraction = 0.154491
transient_residual_from_full_fraction = 0.072860
depleted_before_residual_fraction = 0.772649
new_outside_full_fraction_of_full = 0.004624
residual_persistence_frequency_p90 = 0.998704
```

For the same rerun, geometric core/edge metrics used the cached
`mask_crop.h5:/flow_domain_mask` on the 3X C2 processing grid:

```text
core_flow_min_dist_px = 3.0
flow_domain_area_px = 1794675
core_flow_area_px = 1783223
edge_band_area_px = 11452
edge_band_fraction_of_flow_domain = 0.006381
residual_core_red_mask_fraction_median = 0.071665
residual_edge_red_mask_fraction_median = 0.022005
residual_core_to_edge_red_mask_fraction_ratio_median = 3.258645
final_residual_core_retained_from_full_fraction = 0.155099
final_residual_edge_retained_from_full_fraction = 0.042787
residual_core_dnapl_water_length_px_median = 99055.790125
residual_edge_dnapl_water_length_px_median = 104.840620
residual_core_dnapl_solid_length_px_median = 0.000000
residual_edge_dnapl_solid_length_px_median = 72.384776
core_edge_qc_overlays PNG count = 7
```
