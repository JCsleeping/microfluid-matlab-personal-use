# Reference Endpoint Audit Repair Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the mismatch between visually successful DNAPL preview segmentation and reference endpoint audit rejection, while preserving a provisional color-index time series path for `Sn(t)` analysis.

**Architecture:** Separate four concepts that were previously mixed in interpretation: visual DNAPL extraction, segmentation mask generation, operational bulk/regional color-index time series, and endpoint-normalized saturation. The repaired workflow must use the correct domain mask for endpoint statistics, audit high-saturation frames as provisional endpoints without self-validation, keep contrast/2x scale out of quantitative color scoring unless explicitly tested, and label provisional color-index outputs so they are not confused with endpoint-validated physical `Sn`.

**Tech Stack:** Python diagnostics in `tools/color_tuning`, BaSiCPy/NumPy/scikit-image/OpenCV/matplotlib, existing MATLAB flow-domain/core-flow masks and processing-grid metadata for later porting.

---

## Cross-Check Brief

### Background

The project analyzes DNAPL in microfluidic chip images. The current Python prototype was introduced before MATLAB batch integration to solve two observed image problems:

- a bright central illumination halo;
- dark/low-visibility chip ends.

The current preview pipeline is:

```text
raw RGB
  -> crop
  -> BaSiC illumination correction
  -> percentile brightness/contrast preview
  -> 2x RGB upscale
```

This preview makes the red DNAPL visually clear in both:

- a high-saturation frame, expected to be near full saturation;
- a residual frame, expected to contain sparse remaining DNAPL clusters.

The user correctly observed that red DNAPL appears extractable from the preview images.

### Current Outputs

Key outputs:

- `outputs/python_stepwise_illumination_reference_20260530/03_scale2_preview/basicpy_rgb_all/high_preview.png`
- `outputs/python_stepwise_illumination_reference_20260530/03_scale2_preview/basicpy_rgb_all/residual_preview.png`
- `outputs/python_stepwise_illumination_reference_20260530/04_reference_audit/reference_score_ranking.csv`
- `outputs/python_stepwise_illumination_reference_20260530/04_reference_audit_high_as_endpoint_selfcheck/reference_score_ranking.csv`
- `outputs/python_stepwise_illumination_reference_20260530/decision_matrix.csv`

The previous audit rejected two NAPL reference candidates:

- `same_dataset_00_napl`
- `cross_dataset_01_napl`

The rejection was based on endpoint-normalized color scores:

```text
S = (Q_frame - Q_water) / (Q_napl - Q_water)
```

The expected physical pattern is:

```text
S_high close to 1
S_residual closer to 0
left/center/right direction consistent
endpoint_delta large enough
```

But the current audit often found:

```text
S_residual > S_high
```

or endpoint deltas too small.

### Important Clarification

There are two different tasks:

1. **Segmentation-only DNAPL extraction**
   - Goal: identify red DNAPL pixels/clusters.
   - The preview images suggest this is feasible.
   - Brightness/contrast and 2x scale are allowed here as segmentation aids.

2. **Quantitative endpoint-normalized saturation**
   - Goal: map color score to a water-to-full-NAPL scale.
   - This requires a valid water endpoint and a valid full-NAPL endpoint.
   - Contrast-stretched preview should not be used by default because it changes color statistics.

The audit rejection does not mean red DNAPL cannot be segmented. It means the tested NAPL reference files did not behave like full-NAPL endpoints under the current audit setup. It also does not mean all time-series work must stop: an operational color-index time series can proceed if it is clearly labeled as provisional and not mixed with endpoint-validated `Sn`.

### Known Audit Weakness

Current code in `tools/color_tuning/audit_reference_scores.py` uses a rectangular all-true mask:

```python
mask = np.ones(shape, dtype=bool)
```

That means endpoint statistics are currently computed over the full crop, not over CAD-derived `flow_domain` or `core_flow`.

This is a likely source of error because the crop includes:

- chip boundary/background;
- solid pillars;
- non-flow areas;
- edge artifacts;
- illumination residuals.

Endpoint audit should instead run on the same `flow_domain/core_flow` used by the MATLAB pipeline.

### High-Frame Self-Endpoint Check

As a diagnostic, the high-saturation frame was temporarily used as a NAPL endpoint candidate against itself.

Result:

```text
high_as_endpoint_selfcheck + lab_ab_projection: pass
S_high = 1.000
S_residual = 0.505
```

This shows:

- the high frame is compatible with a Lab a/b projection endpoint direction;
- `lab_ab_projection` is more plausible than single-channel red metrics in this setting;
- a high-saturation frame may be a better provisional endpoint than the existing NAPL-named reference files.

This does not prove:

- the high frame is a true full-NAPL endpoint;
- the residual value is physically calibrated;
- the result generalizes to other frames;
- self-validation is sufficient.

The high frame cannot validate itself. A separate high-saturation validation frame is needed.

## Working Root-Cause Hypotheses

### Hypothesis 1: Current NAPL Reference Files Are Not Full-NAPL Endpoints

Evidence:

- Both current NAPL-named candidates fail most score modes.
- Residual appears closer to the candidate endpoint than the high frame for many scores.
- The visual high frame looks more endpoint-like than the existing NAPL reference candidates.

### Hypothesis 2: Endpoint Audit Mask Is Too Broad

Evidence:

- `audit_reference_scores.py` currently uses an all-true rectangular crop mask.
- The decision should be made in `flow_domain/core_flow`, not in chip background and solid structures.
- The user asked specifically to evaluate within `crop / flow_domain / core_flow`, but the current Python implementation only does crop.

### Hypothesis 3: Preview Segmentation And Quantitative Endpoint Audit Are Being Interpreted As The Same Test

Evidence:

- Preview contrast and 2x scale make DNAPL visually separable.
- Quantitative audit intentionally avoids preview contrast.
- A method can be good for segmentation but invalid for endpoint-normalized saturation.

## New Repair Strategy

Repair the workflow by splitting it into three independent branches:

```text
Branch A: segmentation-only DNAPL extraction
  -> use corrected + contrast preview + 2x scale
  -> detect red DNAPL
  -> morphology cleanup
  -> restrict to flow_domain/core_flow
  -> validate masks visually and by qualitative area-fraction ordering
  -> output red_mask_area_fraction, not endpoint-normalized Sn

Branch B: quantitative endpoint audit
  -> use corrected quantitative RGB
  -> use flow_domain/core_flow mask
  -> audit candidate references and score modes
  -> require independent validation frames

Branch C: operational bulk/regional color-index time series
  -> use corrected quantitative RGB
  -> use flow_domain, core_flow, edge_band, and x-bin regions
  -> compute S_NAPL_color(t) using provisional or audit-passed endpoints
  -> label endpoint_status = provisional | masked_audit_passed
  -> output color-index proxy, not physical Sn unless Branch B passes
```

Do not block Branch A on endpoint audit. Do not block Branch C if it is labeled as a provisional operational index. Do block MATLAB endpoint-normalized saturation on a valid masked, non-self endpoint audit.

## Terminology To Freeze Before Implementation

Use these names consistently in CSV, JSON, MATLAB manifests, and reports:

- `red_mask_area_fraction`: area fraction from segmentation-only red mask.
- `segmentation_mask`: binary mask from Branch A.
- `endpoint_score`: scalar color score used for endpoint audit.
- `endpoint_normalized_S`: water-to-NAPL normalized saturation from Branch B.
- `S_NAPL_color`: operational color-index saturation from Branch C.
- `provisional_endpoint`: endpoint candidate not yet independently validated.
- `production_endpoint`: endpoint candidate that passed masked independent audit.
- `self_endpoint_check`: diagnostic where candidate and high validation are the same frame.
- `independent_validation`: validation using frames different from the endpoint candidate.
- `mask_id`: `none`, `flow_domain`, `core_flow`, `edge_band`, or `xbin_*`.
- `rgb_source`: `corrected_quantitative`, `contrast_preview`, or `scale2_preview`.

## Task 1: Add Real Domain Mask Support To Python Audit

**Files:**

- Modify: `tools/color_tuning/audit_reference_scores.py`
- Test: `tests/test_reference_score_audit.py`
- Output: `outputs/python_stepwise_illumination_reference_20260530/06_masked_reference_audit`

**Steps:**

1. Add CLI options:
   - `--domain-mask path`
   - `--core-mask path`
   - `--mask-source none|image|mat`
   - `--mask-resize nearest`
   - `--mask-grid native_cropped|processing_grid|preview_scale2`
   - `--mask-variable-name name` for `.mat` inputs
   - `--core-erode-px value`
2. Load mask as boolean.
3. Crop/resize mask to match audited RGB shape.
4. Build `all/left/center/right` regions from the selected mask using x-quantiles of mask pixels, not full-crop thirds.
5. Write mask overlay PNGs for water, high, and residual frames.
6. Record mask provenance in output CSV and JSON.
7. Re-run current candidates separately with `flow_domain` and `core_flow`.

**Pass condition:**

- Audit no longer uses full rectangular crop when a domain mask is provided.
- If no domain/core mask is provided, rows are marked `unmasked_diagnostic` and cannot be `eligible_for_quantitative_endpoint`.
- Region stats only include pixels inside the selected domain.
- Output records `mask_coverage_fraction`, `flow_domain_area_px`, `core_flow_area_px`, mask shape before/after use, resize method, mask grid, mask source path, and `core_erode_px`.
- Output records `rgb_shape_h`, `rgb_shape_w`, `mask_pixel_count_all`, `mask_pixel_count_left`, `mask_pixel_count_center`, and `mask_pixel_count_right`.
- Mask overlays are visually inspectable before any masked audit conclusion is trusted.

## Task 2: Add Segmentation-Only Red DNAPL Extraction

**Files:**

- Create or modify: `tools/color_tuning/segment_preview_napl.py`
- Test: `tests/test_segment_preview_napl.py`
- Output: `outputs/python_stepwise_illumination_reference_20260530/07_preview_segmentation`

**Steps:**

1. Input corrected or preview RGB.
2. Compute candidate red scores:
   - Lab `a*`
   - `excess_red`
   - `normalized_red`
   - HSV red/pink hue gate as optional support
   - Lab a/b projection if endpoints are provided
3. Default segmentation must not require a production endpoint.
4. Endpoint-informed projection is diagnostic unless the manifest records `endpoint_dependency = production`.
5. Restrict to `flow_domain/core_flow`.
6. Use threshold sweep instead of one fixed threshold.
7. Apply morphology cleanup:
   - remove small objects;
   - close small gaps;
   - optionally preserve thin red films.
8. Output:
   - binary mask;
   - overlay;
   - `red_mask_area_fraction`;
   - per-region area fraction;
   - threshold sweep table;
   - score histograms inside `flow_domain` and `core_flow`;
   - component diagnostics.

**Pass condition:**

- High frame mask is coherent and covers visually red DNAPL regions.
- Residual frame mask captures sparse clusters without flooding the whole chip.
- High frame `red_mask_area_fraction` is greater than residual frame `red_mask_area_fraction`.
- Threshold sweep has a stable plateau.
- `largest_component_fraction` and `growth_ratio` do not indicate residual-frame flooding.
- Output must not call segmentation-only area fraction endpoint-normalized `Sn`.

**Required diagnostics:**

- `threshold`
- `mask_area_fraction`
- `largest_component_fraction`
- `component_count`
- `seed_fraction`
- `candidate_fraction`
- `final_fraction`
- `growth_ratio`
- `final_from_hsv_only_fraction`
- `red_score_p05`
- `red_score_p50`
- `red_score_p95`
- `core_flow_fraction`
- `edge_band_fraction`

## Task 3: Rebuild Endpoint Candidate Set

**Files:**

- Modify: `tools/color_tuning/audit_reference_scores.py`
- Output: `outputs/python_stepwise_illumination_reference_20260530/08_endpoint_candidates`

**Steps:**

1. Keep existing NAPL-named files as candidates but do not privilege them.
2. Add high-saturation frames as provisional NAPL endpoint candidates.
3. Require each endpoint candidate to be validated against different frames:
   - candidate endpoint frame;
   - separate high-saturation validation frame;
   - residual validation frame;
   - clean-water frame.
4. Mark self-check rows explicitly as `self_endpoint_check`.
5. Do not allow self-check pass to become production pass.
6. Record `endpoint_candidate_role`:
   - `existing_napl_named`
   - `provisional_high`
   - `self_check`
7. Record endpoint/crop/dataset provenance:
   - `candidate_id`
   - `candidate_frame`
   - `candidate_dataset`
   - `candidate_chip_id`
   - `candidate_crop_id`
   - `water_reference_id`
   - `independent_high_validation_id`
   - `residual_validation_id`

**Pass condition:**

- A production endpoint candidate must pass using an independent high validation frame.

## Task 4: Prioritize Score Modes By Physical Behavior

**Files:**

- Modify: `tools/color_tuning/audit_reference_scores.py`
- Test: `tests/test_reference_score_audit.py`

**Steps:**

1. Keep all existing scores for diagnostics.
2. Split Lab a/b projection into:
   - `lab_ab_projection_global`: one global endpoint vector from masked robust endpoint statistics, aligned with MATLAB `compute_bulk_sn_color.m`;
   - `lab_ab_projection_pixelwise`: current per-pixel diagnostic projection, allowed only for diagnostics unless explicitly promoted.
3. Promote candidate score modes in this order:
   - `lab_ab_projection_global`
   - `excess_red`
   - `lab_a`
   - `chroma`
   - OD modes only if their endpoint deltas are stable.
   - OD modes require known black level/dark current handling, consistent exposure/white balance, no clipping after correction, and no contrast-preview input.
4. Add report columns:
   - `eligible_for_segmentation`
   - `eligible_for_color_index_timeseries`
   - `eligible_for_quantitative_endpoint`
5. Use a fixed `failure_reason` enum:
   - `none`
   - `self_validation_only`
   - `bad_endpoint_delta`
   - `wrong_score_direction`
   - `residual_exceeds_high`
   - `bad_region_consistency`
   - `unmasked_domain`
   - `insufficient_domain_pixels`
   - `endpoint_contaminated_by_background`
   - `endpoint_candidate_not_full_napl`

**Pass condition:**

- The ranking table distinguishes "useful for red segmentation" from "valid quantitative endpoint."
- Production endpoint eligibility requires `self_endpoint_check = false`, an independent high validation frame, adequate endpoint delta, `S_high > S_residual` by margin, and left/center/right direction consistency.

## Task 5: Add Bulk/Regional Color-Index Time Series Branch

**Files:**

- Create or modify: `tools/color_tuning/compute_color_index_timeseries.py`
- Test: `tests/test_color_index_timeseries.py`
- Output: `outputs/python_stepwise_illumination_reference_20260530/09_color_index_timeseries`

**Steps:**

1. Read a frame list or TIF stack.
2. Apply the selected quantitative illumination correction.
3. Compute score maps on corrected quantitative RGB only.
4. Compute operational color-index saturation:

```text
S_color_raw =
    (stat(score_frame(mask)) - stat(score_water(mask))) /
    (stat(score_endpoint(mask)) - stat(score_water(mask)))

S_color = clip(S_color_raw, 0, 1)
```

5. Support score modes:
   - `lab_ab_projection_global`
   - `excess_red`
   - `normalized_red`
   - `chroma`
   - `lab_a`
6. Use `winsorized_mean` by default, with median as a diagnostic option.
7. Compute regions:
   - `flow_domain`
   - `core_flow`
   - `edge_band`
   - `xbin_01`, `xbin_02`, ...
8. Write output columns:
   - `S_NAPL_color_raw`
   - `S_NAPL_color_clamped`
   - `S_NAPL_color_core`
   - `S_NAPL_color_edge`
   - `S_NAPL_color_xbin_*`
   - `score_water_ref`
   - `score_endpoint_ref`
   - `score_frame`
   - `endpoint_source`
   - `endpoint_status = provisional|masked_audit_passed`
   - `mask_id`
   - `rgb_source`

**Pass condition:**

- The branch produces a time series even when Branch B has not passed, but every row is labeled `endpoint_status = provisional`.
- The output is named `S_NAPL_color` or `Sn_color_proxy`, not `Sn_final`.
- Once Branch B passes, the same branch can be re-run with `endpoint_status = masked_audit_passed`.

## Task 6: MATLAB Port Gate

**Files:**

- Later modify: `preprocessing/correct_illumination.m`
- Later modify: `segmentation/segment_DNAPL.m`
- Later modify: `main_DNAPL_pipeline.m`
- Later modify: `preprocessing/prepare_frame_for_processing_grid.m`

**Gate for segmentation-only MATLAB port:**

- BaSiC or chosen illumination correction has a MATLAB equivalent or precomputed correction path.
- Preview segmentation mask passes high/residual sanity checks.
- Scale metadata records `processing_scale_factor = 2`.
- Outputs `mask_color_disagreement`, `largest_component_fraction`, and component diagnostics.
- Segmentation-only results must not be written into endpoint-normalized `Sn` fields.

**Gate for bulk color-index time series MATLAB port:**

- May proceed provisionally if Branch C Python output is stable and clearly labeled.
- Must write `S_NAPL_color` or `Sn_color_proxy`, not `Sn_final`, until Branch B passes.
- Must record endpoint status, endpoint source, score mode, mask id, and RGB source.

**Gate for quantitative saturation MATLAB port:**

- A non-self endpoint candidate passes masked audit.
- A score mode has stable left/center/right behavior.
- `S_high > S_residual` by a configured margin.
- Endpoint provenance is recorded in manifest.
- Independent high validation frame is present.
- Audit passes separately on `flow_domain` and `core_flow`, or records `core_flow_valid = true` and `edge_band_uncertain = true`.

## Task 7: Add Guardrail Tests

**Files:**

- Test: `tests/test_reference_score_audit.py`
- Test: `tests/test_segment_preview_napl.py`
- Test: `tests/test_color_index_timeseries.py`

**Required tests:**

- all-true mask and `core_flow` mask produce different stats on a synthetic fixture.
- checkerboard mask only includes selected pixels.
- crop-offset synthetic mask aligns to expected pixels.
- mask resize uses nearest-neighbor only.
- left/center/right x-quantile regions have valid mask-pixel counts.
- self-check cannot set `eligible_for_quantitative_endpoint = true`.
- contrast preview is rejected for quantitative endpoint audit unless explicitly marked diagnostic.
- segmentation branch can run without any endpoint.
- CSV/JSON provenance fields are complete.

## Information Needed From User

To complete the repair, we need at least one of:

1. A CAD-derived or MATLAB-exported `flow_domain/core_flow` mask for the same crop/page.
2. A path to `results_*.mat` containing `flow_domain` and `core_flow` for these frames.
3. One or more additional frames that the user visually confirms are near full-NAPL but not identical to the high validation frame.
4. Whether provisional `S_NAPL_color(t)` is acceptable as an interim time-series output before endpoint audit passes.

## Expected Outcome

After repair:

- DNAPL segmentation can proceed from preview images even before final endpoint calibration.
- Endpoint audit will no longer be confounded by full-rectangular crop contamination.
- Current NAPL-named files may still be rejected if masked flow-domain statistics show they are not valid full-NAPL endpoints.
- A high-saturation frame can be tested as a provisional endpoint without invalid self-validation.
- Operational color-index time series can proceed as `S_NAPL_color(t)` or `Sn_color_proxy`, with clear `endpoint_status` provenance.
