# DNAPL New Experiment Onboarding Checklist

Use this checklist when a new experiment result is available. Do not create or
lock multi-experiment configs before the data exists. Each experiment is
onboarded independently, then compared only after its own gates pass.

The goal is to make every new run reproducible without relying on an agent to
remember prior decisions.

## Required Inputs

Collect these before starting:

```text
experiment name
raw TIFF directories
water endpoint candidates
full-NAPL endpoint candidates
residual / production frame list
manual ROI or flow-domain mask
expected processing scale factor
known phase order
optional physical metadata
```

For the current Branch C/C2 pipeline, the active processing grid is:

```text
processing_scale_factor = 3
```

Do not reuse historical 2X preview assumptions for new production runs.

## Step 1 - Data Inventory

Create a short inventory before writing a config:

```text
raw_data_root
water_endpoint_dir
production_dir
candidate full-NAPL files
candidate residual files
number of TIFF files
page count per TIFF
files that should never be used
```

Rules:

- Do not infer phase semantics from folder names alone.
- Record user-defined roles explicitly.
- If a TIFF contains a transition, do not label the whole file as `full_napl`.
- Prefer page-range role overrides over file-level role labels when needed.

## Step 2 - ROI / Mask

Prepare one ROI or flow-domain mask for the experiment:

```text
mask source
native image shape
mask grid
mask nonzero pixel count
mask coverage fraction
overlay PNG
```

Minimum acceptance:

- overlay visually aligns with the chip / flow domain;
- mask is not empty;
- mask excludes obvious background outside the flow domain;
- downstream processing records the 3X processing-grid provenance.

If the ROI is changed, rerun the endpoint audit and the full pipeline. Do not
reuse endpoint decisions from a different ROI.

## Step 3 - Endpoint And Role Map

Define roles explicitly:

```text
water_endpoint
full_napl
residual
production
exclude
```

Required review:

- water endpoint candidates are clean water / non-NAPL reference frames;
- full-NAPL endpoint candidates are truly near full saturation in the selected
  ROI;
- residual frames are not root-level placeholders unless explicitly approved;
- page-expanded files with internal phase changes get page-range overrides.

The endpoint policy should include:

```text
primary endpoint A
sensitivity endpoint B
score mode
endpoint status
water label
full-NAPL label
```

## Step 4 - Build Or Update Config

Use the A1 config as the structural template, not as a semantic template.

Config fields to update:

```text
run_name
water_endpoint_dir
production_dir
roi_mask
output_root
endpoint_policy
water_endpoints
napl_endpoints, if external endpoint files are needed
production_role_overrides, if page ranges or nonstandard roles are needed
manifest.page_selection
manifest.max_pages
segmentation_metrics.processing_scale_factor = 3
physical_metadata, if trusted values are available
```

Do not change the config to make filenames fit the old A1 labels. Configure the
labels instead.

## Step 5 - Manifest Smoke Run

Run manifest first:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config <config.json> --mode pilot --steps manifest
```

Check:

```text
accepted_frames.csv exists
endpoint_policy.json exists
role counts make sense
page-expanded labels match endpoint policy
excluded files are absent
```

If role counts are wrong, fix role definitions before running BasicPy or
MATLAB.

## Step 6 - Endpoint Audit

Run or reproduce masked endpoint audit before trusting `S_NAPL_color`:

```text
water endpoint candidates
full-NAPL candidates
residual candidates
score modes: chroma, lab_a, lab_ab_projection_global, excess_red
mask: user ROI / flow domain
RGB source: corrected quantitative only
```

Gate:

```text
full validation near 1
residual validation below threshold
left / center / right consistency
endpoint delta sufficient
self-validation not counted as production pass
```

If the endpoint audit fails, Branch C can still output an operational
color-index proxy, but it must not be promoted as endpoint-normalized
production saturation.

## Step 7 - Pilot Segmentation

Run a pilot for threshold and mask sanity:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config <config.json> --mode pilot --steps cache matlab segpilot validate
```

Check:

```text
S_NAPL_color A/B agreement
red mask overlays
candidate threshold sweep
residual mask not flooding
full-NAPL mask coherent
interface/contact fields present
```

Lock `segmentation_metrics.locked_threshold` only after visual and table checks.

## Step 8 - Full Run

Run the full pipeline after the pilot passes:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config <config.json> --mode full --steps manifest cache matlab segmorph validate timeline residual endpointaudit maskanalysis analysis
```

For long runs, keep:

```text
segmentation_metrics.blob_detail_output_mode = chunked_csv
segmentation_metrics.write_mask_stack = true
segmentation_metrics.processing_scale_factor = 3
```

Do not skip `endpointaudit` or `maskanalysis` in the final run.

## Step 9 - QC Review

Review these files:

```text
<matlab_dir>/run_summary.json
<endpoint_audit_dir>/endpoint_consistency_summary.json
<segmentation_morphology_dir>/segmentation_manifest.json
<mask_stack_analysis_dir>/mask_stack_analysis_summary.json
<analysis_dir>/analysis_package_provenance.json
<analysis_dir>/analysis_qc_summary.csv
<analysis_dir>/research_parameter_alignment.csv
```

Minimum pass conditions:

```text
run_summary status = pass
row counts match expected frames
missing label counts = 0
endpoint sensitivity finite
endpointaudit flags explained or zero
mask_stack_ready = true
phase_aware_mask_ready = true, if full/residual roles are meaningful
geometric_core_edge_ready = true
blob_detail_distribution_ready = true
legacy adapter ready, if old plotting scripts are needed
```

If `endpointaudit` is `review`, decide whether to:

```text
fix role overrides and rerun
or keep flags as documented exclusions
```

Do not hide endpointaudit review flags in the final report.

## Step 10 - Output Interpretation

Allowed language:

```text
S_NAPL_color = operational endpoint-normalized color-index proxy
red_mask_area_fraction = 2D mask occupancy proxy
dnapl_water_length_px = 2D projected DNAPL-water interface length, L_ow
dnapl_solid_length_px = 2D DNAPL-solid contact length
InterfaceArea = legacy alias of dnapl_water_length_px, not area
a_i_2D_proxy = interface length per red-mask area proxy
finger_count_proxy = mask-stack front-band proxy, not pore-graph fingering
```

Forbidden language unless physical gates pass:

```text
physical Sn
physical mass transfer coefficient
metre interface length
PV-normalized rate
capillary number
true pore-graph fingering
```

## Step 11 - Optional Physical Metadata

Only after trusted measurements are available, add:

```text
pixel_size_um
processing_pixel_size_um, if measured directly
flow_rate_ul_min
pore_volume_ul
channel_width_um
channel_depth_um
viscosity_Pa_s
IFT_mN_m
temperature_C
diffusion_coefficient_m2_s
surfactant information
```

Then rerun the analysis step or a dedicated physical metadata script to unlock:

```text
dnapl_water_length_m
dnapl_solid_length_m
PV
dS/dPV
capillary_number
```

Do not fabricate physical metadata from filenames, frame order, or old notes.

## Step 12 - Archive And Commit

For each experiment, archive:

```text
config json
ROI/mask and overlay
endpoint audit report
endpointaudit summary
run_summary.json
analysis_package_provenance.json
analysis_report.md
figures
QC notes
```

Commit code/config/documentation changes separately from large generated
outputs unless the repository policy explicitly tracks those outputs.

Suggested report naming:

```text
docs/reports/YYYY-MM-DD-<experiment>-branch-c-c2-full-run.md
```

## Decision Rule

If a new experiment cannot answer these questions, it is not ready for a full
run:

```text
What is the ROI?
Which frames are water endpoints?
Which frames/pages are full-NAPL endpoints?
Which frames/pages are residual?
Which files must be excluded?
Which segmentation threshold is locked?
Does endpointaudit pass or have explained review flags?
```

Stop at the earliest failing gate, fix that gate, then rerun. Do not push a
partially interpreted experiment into cross-experiment comparison.
