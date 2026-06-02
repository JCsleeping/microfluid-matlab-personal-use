# DNAPL Interface Contact Analysis Package Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add DNAPL-water interface length, DNAPL-solid contact length, and legacy `InterfaceArea` semantics to the C2 red-mask workflow, then use those fields in residual trapping and analysis-package outputs.

**Architecture:** The MATLAB C2 `segmorph` stage owns interface/contact calculation because it already reconstructs the locked red DNAPL mask and has the `flow_domain` mask needed to classify DNAPL-water versus DNAPL-solid boundaries. Python postprocess tools only consume those CSV fields and should not approximate boundary length from blob summaries.

**Tech Stack:** MATLAB Image Processing Toolbox for mask boundary/contact metrics; Python stdlib CSV/JSON postprocess tools; existing Branch C/C2 standalone runner and realtime joiner.

---

## Confirmed Semantics

```text
dnapl_water_length_px / dnapl_water_length_m
  DNAPL-water projected interface length, L_ow. This is the primary interface
  metric for residual structure, dissolution, and mass-transfer interpretation.

dnapl_solid_length_px / dnapl_solid_length_m
  DNAPL-solid contact length. This is a wetting/contact proxy, not the primary
  mass-transfer interface.

InterfaceArea
  Legacy alias for dnapl_water_length_px / L_ow in processing-grid pixels.
  It is not area.

solid_contact_fraction
  dnapl_solid_length_px / (dnapl_water_length_px + dnapl_solid_length_px).

a_i_2D_proxy
  dnapl_water_length_px / red_mask_area_px. This is a segmentation-mask proxy,
  not a physical calibrated interfacial area unless pixel-size and mask gates
  are explicitly satisfied.
```

## Non-Goals

- Do not claim physical trapped saturation.
- Do not claim true geometric core/edge until a solid/core mask gate exists.
- Do not compute Python perimeter approximations from blob fields.
- Do not rename `InterfaceArea`; keep it only as a documented legacy alias.

## Pilot Pass Conditions

1. `red_mask_timeseries.csv` and realtime joined CSVs include:
   `dnapl_water_length_px`, `dnapl_solid_length_px`,
   `dnapl_water_length_m`, `dnapl_solid_length_m`, `InterfaceArea`,
   `solid_contact_fraction`, `a_i_2D_proxy`, and `interface_semantics`.
2. `InterfaceArea == dnapl_water_length_px` for every row.
3. If `processing_pixel_size_m` is available, metre fields equal pixel fields
   multiplied by pixel size; otherwise metre fields are `NaN`.
4. Rows with nonzero red mask have `dnapl_water_length_px > 0`;
   `dnapl_solid_length_px >= 0`; `0 <= solid_contact_fraction <= 1`;
   `a_i_2D_proxy >= 0`.
5. `a_i_2D_proxy == dnapl_water_length_px / red_mask_area_px`; zero red area
   yields `NaN`, not a fabricated zero.
6. The pilot analysis figure separates full/residual stages and the report
   explicitly states `InterfaceArea` is a legacy length alias.

## Task 1: Extend MATLAB C2 Segmorph Interface Columns

**Files:**
- Modify: `run_a1_1bo_6ul_hdf5_cache_segmentation_morphology.m`
- Test: `tests/test_segmentation_morphology_interface.m`

**Steps:**

1. Add a MATLAB test fixture that writes a tiny HDF5 cache with one red mask
   frame, a `flow_domain` boundary, and a locked `normalized_red` threshold.
2. Run the test and confirm it fails because interface/contact columns do not
   exist yet.
3. Extend `mask_summary_metrics` to compute interface metrics from the locked
   red mask and `flow_domain`.
4. Add the new fields to `empty_threshold_row`, `threshold_row`, and
   `morphology_row`.
5. Write `interface_semantics` to the CSV and manifest.
6. Run the MATLAB test and syntax check.

## Task 2: Extend Standalone Runner Validation

**Files:**
- Modify: `run_dnapl_branch_c_timeseries_tool.py`

**Steps:**

1. Validate that the C2 morphology CSV contains all interface/contact fields.
2. Add metric summaries for `dnapl_water_length_px`,
   `dnapl_solid_length_px`, `solid_contact_fraction`, and `a_i_2D_proxy`.
3. Fail validation if required px/ratio/proxy fields are missing or non-finite.
4. Do not fail when metre fields are `NaN` and no pixel-size field is supplied.

## Task 3: Extend Residual Trapping Postprocess

**Files:**
- Modify: `tools/residual/compute_residual_trapping_metrics.py`
- Modify: `tests/test_residual_trapping_metrics.py`

**Steps:**

1. Add synthetic fixture columns for interface/contact metrics.
2. Add output fields:
   `dnapl_water_length_px`, `dnapl_water_length_m`,
   `dnapl_solid_length_px`, `dnapl_solid_length_m`, `InterfaceArea`,
   `solid_contact_fraction`, `a_i_2D_proxy`, `L_ow_retention_ratio`.
3. Add summary distributions for full/residual and final residual rows.
4. Keep `InterfaceArea` as a legacy alias and never treat it as area.

## Task 4: Pilot Rerun and Realtime Join

**Files/Outputs:**
- Existing pilot cache and manifest under
  `outputs/standalone_branch_c_runs_20260601/A1_1BO_6UL_manual_roi`
- New/updated C2 pilot morphology CSV
- New/updated realtime joined CSVs
- New/updated residual trapping pilot postprocess

**Steps:**

1. Run 100-page pilot `segmorph validate`.
2. Run manifest realtime join for pilot C2/Branch C CSVs.
3. Run residual trapping postprocess on pilot realtime CSVs.
4. Check all six pilot pass conditions.

## Task 5: Documentation Updates

**Files:**
- Modify: `docs/guides/dnapl_branch_c_timeseries_tool.md`
- Modify: `docs/reports/2026-06-01-dnapl-branch-c-standalone-tool.md`

**Steps:**

1. Document interface/contact field semantics.
2. Document pilot command and output fields.
3. Record pilot pass/fail result.
4. List remaining work after this stage.

## Status 2026-06-02

Completed in this stage:

1. Added C2 interface/contact fields to `red_mask_timeseries.csv`.
2. Added standalone runner validation for all interface/contact fields.
3. Added residual trapping postprocess fields and summaries.
4. Re-ran the 100-page pilot `segmorph validate`, realtime join, and residual
   trapping postprocess.
5. Re-ran full3585 `segmorph validate`; status is `pass`.
6. Re-ran full3585 realtime join; status is `pass`, 3585 timeline rows, 0
   unmatched rows.
7. Re-ran full3585 residual trapping postprocess; status is `pass`, 498
   full-role rows and 3087 residual-role rows.

Full3585 interface/contact snapshot:

```text
all-frame median dnapl_water_length_px = 41453.624643
all-frame median dnapl_solid_length_px = 148.911688
all-frame median solid_contact_fraction = 0.003579
all-frame median a_i_2D_proxy = 0.323424
residual median L_ow_retention_ratio = 0.276201
final residual dnapl_water_length_px = 41249.114975
final residual L_ow_retention_ratio = 0.275005
```

## Remaining Work After This Stage

1. Build the researcher-facing analysis package:
   - `S_NAPL_color_A/B vs RealTime`
   - residual zoom
   - red-mask area fraction
   - blob morphology
   - x-zone S(t)
   - residual trapping summary bar
   - interface/contact/a_i_2D proxy figure
2. Add `run_commands.md`, provenance JSON, and Markdown report under an
   `analysis_package_full3585` output directory.
3. Add optional SI/unit conversion once a trusted processing pixel size is
   recorded; until then metre fields remain `NaN`.
4. Only after those pass, decide whether to backport selected fields into the
   main MATLAB pipeline exports.
