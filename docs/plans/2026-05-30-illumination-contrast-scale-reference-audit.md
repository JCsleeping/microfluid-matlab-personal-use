# Illumination Contrast Scale Reference Audit Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a stepwise Python-first validation workflow that removes the central illumination halo, tests brightness/contrast and 2x scale for segmentation support, audits reference endpoints and color scores, and only then ports the winning path to MATLAB batch processing.

**Architecture:** Keep quantitative color scoring separate from visualization/segmentation enhancement. Illumination correction produces the quantitative corrected RGB used for reference audit; brightness/contrast and 2x scale are downstream aids for visual inspection and mask generation, not the default input for endpoint-normalized color scores.

**Tech Stack:** Python diagnostics in `tools/color_tuning`, BaSiCPy/NumPy/scikit-image/OpenCV/matplotlib for tuning, existing MATLAB processing-grid helpers for later batch integration.

---

## Current Working Hypothesis

The current segmentation failure is mainly caused by two coupled issues:

1. The middle light halo and dark chip ends make left/center/right color statistics inconsistent.
2. The current NAPL reference candidates do not behave like true full-NAPL endpoints in the flow domain.

The next work must prove or reject each processing step in order. Do not move directly to MATLAB batch until the Python audit identifies a correction/reference/score combination that passes the explicit gates below.

## Fixed Starting Inputs

Use the same crop/domain assumptions during all steps unless a step explicitly tests an alternative.

- Worktree: `D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\.worktrees\interpolation-assisted-segmentation-20260527`
- Crop: `[1 568 2392 841]` one-based `x y width height`
- Python output root: `outputs/python_stepwise_illumination_reference_20260530`
- Clean water reference:
  - `G:\Microfluid\02 A1 2 UL WATER DISPLACEMENT\01 WATER\00 WATER 3 SECONDS.tif`
- Current NAPL reference candidates:
  - `G:\Microfluid\02 A1 2 UL WATER DISPLACEMENT\00 NAPL\00 NAPL 1 SECONDS_2.tif`
  - `G:\Microfluid\01 A1 4 UL WATER DISPLACEMENT\01 NAPL 3 SECONDS_13.tif`
- High-saturation validation frame:
  - `G:\Microfluid\02 A1 2 UL WATER DISPLACEMENT\01 WATER\01 WATER 1 SECONDS_9.tif`
- Residual validation frame:
  - `G:\Microfluid\02 A1 2 UL WATER DISPLACEMENT\01 WATER\03 WATER 3 SECONDS_16.tif`

If a better full-NAPL or high-saturation frame is found, add it as a candidate instead of replacing the old candidates. The audit should show why a candidate is rejected.

## Data Flow To Validate

```text
raw RGB
  -> crop / flow_domain / core_flow
  -> illumination correction
  -> quantitative corrected RGB
       -> reference endpoint audit
       -> color score audit
  -> brightness/contrast enhancement
  -> 2x upscale
  -> segmentation preview / mask candidate
  -> scale-aware geometry check
```

The quantitative branch and segmentation branch share the same illumination-corrected source, but only the segmentation branch receives contrast stretching and 2x upscale by default.

## Pass/Fail Gates

### Gate A: Illumination Correction

Pass when all are true:

- The central halo is visibly reduced in corrected montage.
- Left/center/right luminance profiles are closer after correction than before correction.
- Chip ends remain visible and are not crushed to black.
- The correction does not create obvious color inversion or channel clipping.

Fail when:

- The center remains much brighter than both ends.
- A method improves luminance but removes the NAPL color signal.
- The correction is frame-specific in a way that breaks shared reference assumptions.

### Gate B: Brightness/Contrast Enhancement

Pass when all are true:

- End regions become easier to inspect.
- No more than a small fraction of pixels are clipped to pure 0 or 1.
- The enhanced preview improves visual separability without changing quantitative audit inputs.

Fail when:

- Contrast enhancement makes water/NAPL colors look separated only because of clipping.
- It changes score ranking if accidentally used in the quantitative branch.

### Gate C: 2x Scale

Pass when all are true:

- RGB is upscaled with bicubic or Lanczos interpolation.
- Binary masks are upscaled with nearest-neighbor interpolation.
- Area thresholds scale by `scale_factor^2`.
- Radius, length, and distance thresholds scale by `scale_factor`.
- Output metrics retain `processing_scale_factor = 2` so native-equivalent values can be recovered.

Fail when:

- RGB and masks use incompatible grid sizes.
- 2x scale changes reported physical units without explicit correction.
- Mask holes or thin channels appear only because of interpolation artifacts.

### Gate D: Reference Endpoint And Score Audit

Pass when at least one NAPL candidate plus one score mode satisfies:

- `Q_napl` is clearly different from `Q_water`.
- `Q_high` is close to `Q_napl`.
- `Q_residual` is closer to `Q_water`.
- Left/center/right regions show the same direction.
- `abs(endpoint_delta)` is large enough to be robust.

Fail when:

- The file name says NAPL but flow-domain statistics look water-like.
- `S_residual > S_high`.
- Endpoint direction flips between left, center, and right.
- Only one score passes visually but fails the numeric gates.

## Task 1: Establish Baseline Outputs

**Files:**
- Use: `tools/color_tuning/tune_light_field.py`
- Use: `tools/color_tuning/audit_reference_scores.py`
- Output: `outputs/python_stepwise_illumination_reference_20260530/00_baseline`

**Step 1: Run no-correction baseline**

Run `tune_light_field.py` with `--basicpy off` and include the clean water, NAPL candidate, high, and residual frames.

Expected outputs:

- `rgb_montage.png`
- `luminance_profile.png`
- `normalized_red_profile.png`
- `metrics.csv`
- `sn_metrics.csv`

**Step 2: Record baseline failure modes**

Write a short note in the output folder or summary:

- Is the middle brighter than both ends?
- Are chip ends visible?
- Which score modes have left/center/right disagreement?
- Does high-saturation look closer to NAPL or residual?

**Step 3: Decision**

Proceed only if the baseline captures the observed ImageJ problem. If not, fix crop/page/frame selection before tuning methods.

## Task 2: Test Illumination Correction Methods

**Files:**
- Use: `tools/color_tuning/tune_light_field.py`
- Output: `outputs/python_stepwise_illumination_reference_20260530/01_illumination`

**Step 1: Compare candidate methods**

Run the same frame set through:

- `basicpy_rgb_all`
- `basicpy_luma_all`
- `water_rgb_sigma160`
- `water_luma_sigma160`
- `self_rgb_sigma160`
- optional `clahe_l_preview` for preview only

**Step 2: Inspect montages and profiles**

Rank methods by:

- center-vs-edge luminance flattening
- preservation of red/pink NAPL signal
- no severe clipping
- left/center/right consistency

**Step 3: Decision**

Choose one primary correction and one fallback. Current expectation is:

- Primary: `basicpy_rgb_all` or `basicpy_luma_all`
- Fallback: water-reference flat-field if BaSiCPy is unstable or too slow

Do not choose `self_rgb` for quantitative endpoint audit unless it is only used as a diagnostic, because frame-specific correction can remove true NAPL color differences.

## Task 3: Add Brightness/Contrast Preview Branch

**Files:**
- Modify: `tools/color_tuning/tune_light_field.py`
- Test: `tests/test_tune_light_field.py`
- Output: `outputs/python_stepwise_illumination_reference_20260530/02_contrast_preview`

**Step 1: Add test coverage**

Add tests for a preview transform that:

- keeps output in `[0, 1]`
- reports clipping fraction
- does not mutate the quantitative corrected RGB

**Step 2: Implement preview options**

Add CLI options:

- `--contrast-mode none|percentile|clahe_l`
- `--contrast-low-percentile`
- `--contrast-high-percentile`
- `--contrast-clip-limit`

**Step 3: Write outputs**

For each correction method, write both:

- `*_corrected.png` for quantitative RGB
- `*_preview.png` for enhanced visual/segmentation RGB

**Step 4: Decision**

Keep a contrast method only if it helps the dark ends without high clipping. If no method helps, leave contrast disabled and solve visibility through illumination correction or masks.

## Task 4: Add 2x Preview/Segmentation Scale Branch

**Files:**
- Modify: `tools/color_tuning/tune_light_field.py`
- Test: `tests/test_tune_light_field.py`
- Output: `outputs/python_stepwise_illumination_reference_20260530/03_scale2_preview`

**Step 1: Add test coverage**

Test that `--scale-factor 2`:

- doubles RGB height and width
- keeps quantitative metrics computed on the native corrected image unless explicitly requested
- writes metadata with `processing_scale_factor = 2`

**Step 2: Implement scale outputs**

Add CLI options:

- `--scale-factor 1|2|3`
- `--scale-method bicubic|lanczos`
- `--scale-branch preview|quantitative|both`

Default should be `preview`, not quantitative.

**Step 3: Write scaled previews**

Write:

- `*_preview_scale2.png`
- `processing_metadata.json`

**Step 4: Decision**

Use 2x scale for segmentation support only if visual boundaries improve without creating false bridges across pores.

## Task 5: Expand Reference Audit

**Files:**
- Modify: `tools/color_tuning/audit_reference_scores.py`
- Test: `tests/test_reference_score_audit.py`
- Output: `outputs/python_stepwise_illumination_reference_20260530/04_reference_audit`

**Step 1: Add more candidate inputs**

Audit every plausible full-NAPL endpoint:

- current same-dataset NAPL file
- current cross-dataset NAPL file
- one or more high-saturation frames as provisional endpoint candidates
- any user-confirmed full-NAPL frame

If a validation high frame is also tested as a candidate endpoint, use a different high frame for validation or mark the result as a self-endpoint sanity check.

**Step 2: Keep all score modes**

Audit:

- `Q_normalized_red`
- `Q_excess_red`
- `Q_lab_a`
- `Q_chroma`
- `Q_lab_ab_projection`
- `Q_OD_red`
- `Q_OD_green`
- `Q_OD_composite`

**Step 3: Improve ranking report**

Ranking should make the decision explicit:

- best passed candidate, if any
- best failed candidate and why it failed
- per-region `S_high` and `S_residual`
- endpoint direction
- endpoint delta

**Step 4: Decision**

Only a `pass` row is eligible for MATLAB implementation. A candidate with `bad_endpoint_delta`, `inverted_high_residual`, or `unstable_regions` cannot be used as the production NAPL endpoint.

## Task 6: Combine Winning Illumination + Preview + Audit

**Files:**
- Use: `tools/color_tuning/tune_light_field.py`
- Use: `tools/color_tuning/audit_reference_scores.py`
- Output: `outputs/python_stepwise_illumination_reference_20260530/05_winning_combo`

**Step 1: Run the chosen correction**

Use the winning illumination method from Task 2.

**Step 2: Run selected contrast and 2x preview**

Use the chosen preview settings from Tasks 3 and 4.

**Step 3: Run expanded reference audit**

Use all confirmed candidate endpoints and score modes.

**Step 4: Decision**

The Python phase is complete only if the output folder contains:

- corrected quantitative montage
- enhanced 2x preview montage
- reference score ranking
- at least one pass/fail conclusion that is explainable from the numeric gates

If no candidate/score passes, stop and acquire or identify a better full-NAPL reference before MATLAB integration.

## Task 7: MATLAB Port Design After Python Pass

**Files:**
- Modify later: `preprocessing/correct_illumination.m`
- Modify later: `preprocessing/prepare_frame_for_processing_grid.m`
- Modify later: `segmentation/segment_DNAPL.m`
- Modify later: `main_DNAPL_pipeline.m`
- Test later: MATLAB tests around water-referenced segmentation and upscale-assisted segmentation

**Step 1: Port only the winning illumination method**

Do not port every Python method. Port the method that passed the Python gates.

**Step 2: Preserve branch separation**

MATLAB should keep:

- quantitative corrected RGB for score/reference math
- enhanced/upscaled RGB for segmentation support
- scale metadata for geometry correction

**Step 3: Add provenance**

Every run should record:

- illumination method
- contrast mode
- scale factor
- score mode
- endpoint reference path
- reference audit status

**Step 4: Decision**

MATLAB batch is allowed only after one representative frame set reproduces the Python conclusion.

## Task 8: Final Confirmation Matrix

**Files:**
- Create: `outputs/python_stepwise_illumination_reference_20260530/decision_matrix.csv`

The final matrix should contain one row per tested method combination:

- illumination method
- contrast mode
- scale factor
- NAPL endpoint candidate
- score mode
- illumination gate status
- preview gate status
- reference audit status
- final decision: `reject`, `diagnostic_only`, `segmentation_only`, or `production_candidate`

Only `production_candidate` moves into MATLAB batch processing.

## Immediate Next Commands

After this plan is accepted, start with Task 1 and Task 2:

```powershell
python tools/color_tuning/tune_light_field.py `
  --water "G:\Microfluid\02 A1 2 UL WATER DISPLACEMENT\01 WATER\00 WATER 3 SECONDS.tif" `
  --napl "G:\Microfluid\02 A1 2 UL WATER DISPLACEMENT\00 NAPL\00 NAPL 1 SECONDS_2.tif" `
  --high "G:\Microfluid\02 A1 2 UL WATER DISPLACEMENT\01 WATER\01 WATER 1 SECONDS_9.tif" `
  --residual "G:\Microfluid\02 A1 2 UL WATER DISPLACEMENT\01 WATER\03 WATER 3 SECONDS_16.tif" `
  --page 1 `
  --crop "1 568 2392 841" `
  --basicpy required `
  --basicpy-working-size 128 `
  --basicpy-max-iterations 80 `
  --out "outputs\python_stepwise_illumination_reference_20260530\01_illumination"
```

Then run reference audit with the selected correction:

```powershell
python tools/color_tuning/audit_reference_scores.py `
  --water "G:\Microfluid\02 A1 2 UL WATER DISPLACEMENT\01 WATER\00 WATER 3 SECONDS.tif" `
  --napl-candidate "same_dataset_00_napl=G:\Microfluid\02 A1 2 UL WATER DISPLACEMENT\00 NAPL\00 NAPL 1 SECONDS_2.tif" `
  --napl-candidate "cross_dataset_01_napl=G:\Microfluid\01 A1 4 UL WATER DISPLACEMENT\01 NAPL 3 SECONDS_13.tif" `
  --high "G:\Microfluid\02 A1 2 UL WATER DISPLACEMENT\01 WATER\01 WATER 1 SECONDS_9.tif" `
  --residual "G:\Microfluid\02 A1 2 UL WATER DISPLACEMENT\01 WATER\03 WATER 3 SECONDS_16.tif" `
  --page 1 `
  --crop "1 568 2392 841" `
  --correction basicpy_rgb_all `
  --basicpy-working-size 128 `
  --basicpy-max-iterations 80 `
  --min-endpoint-delta 0.01 `
  --min-separation 0.35 `
  --max-region-range 0.25 `
  --out "outputs\python_stepwise_illumination_reference_20260530\04_reference_audit"
```

## Stop Conditions

Stop and ask for user confirmation when:

- no NAPL candidate passes the reference audit
- the best illumination method still leaves strong left/center/right disagreement
- contrast enhancement is necessary for visual inspection but changes quantitative ranking
- 2x scale improves appearance but worsens mask topology
