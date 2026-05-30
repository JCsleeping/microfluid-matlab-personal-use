# DNAPL Audit / Segmentation / Sn(t) Tracking Checkpoint

## Purpose

This checkpoint consolidates the 2026-05-30 planning work for DNAPL image analysis. It records the agreed boundary between visual DNAPL extraction, endpoint-normalized saturation, provisional color-index time series, and Git tracking.

## Current Findings

- BaSiC-based illumination correction is the current Python-side primary candidate for reducing the central halo while preserving red DNAPL visibility.
- Percentile contrast and 2x preview scaling make red DNAPL visually separable in the high-saturation and residual examples.
- The current NAPL-named reference candidates failed the unmasked endpoint audit; this does not mean red DNAPL cannot be segmented.
- The existing Python audit used a full rectangular crop mask, so production endpoint decisions require a new masked audit using `flow_domain` and `core_flow`.
- A high-saturation frame can be tested as a provisional endpoint, but self-checks cannot qualify production endpoints.

## Final Workflow

```text
Foundation: mask/provenance/global score parity
  -> Branch A: segmentation-only red DNAPL mask
  -> Branch B-min: masked endpoint audit
  -> Branch C: provisional bulk/regional S_NAPL_color(t)
  -> Branch B-full: production endpoint qualification
  -> MATLAB gated port
```

## Branch Boundaries

### Branch A: Segmentation-Only Red DNAPL Mask

- Input may use illumination-corrected preview, percentile contrast, and 2x scale.
- Default score candidates: Lab `a*`, `excess_red`, `normalized_red`, and HSV red/pink gates.
- Output names must use `segmentation_mask` and `red_mask_area_fraction`.
- This branch must not write endpoint-normalized `Sn`.

### Branch B: Masked Endpoint Audit

- Input must use corrected quantitative RGB, not contrast preview.
- Audit must run separately on `flow_domain` and `core_flow`.
- Primary score should be `lab_ab_projection_global`, aligned with MATLAB `compute_bulk_sn_color.m`.
- Current per-pixel Lab a/b projection remains diagnostic unless explicitly promoted.
- Production endpoint pass requires non-self validation, independent high frame validation, residual validation, adequate endpoint delta, and consistent left/center/right direction.

### Branch C: Operational Color-Index Time Series

- Output name must be `S_NAPL_color` or `Sn_color_proxy`, not `Sn_final`.
- Every row must include `endpoint_status`, `endpoint_source`, `score_mode`, `mask_id`, and `rgb_source=corrected_quantitative`.
- Before Branch B passes, `endpoint_status` must be `provisional`.
- This branch can support short-term `Sn(t)` trend analysis but must not be described as endpoint-validated physical saturation.

## Required Foundation Work

- Add `flow_domain` / `core_flow` mask support to the Python audit.
- Record mask provenance: source path, variable name, grid, original and used shape, crop, resize method, pixel counts, and coverage fraction.
- Write mask overlay images for visual alignment checks.
- Mark unmasked audit rows as `unmasked_diagnostic`; they cannot be production endpoint passes.
- Use fixed `failure_reason` values rather than free-text failure labels.

## Git Tracking Policy

- Track plans, Python tools, tests, and small textual summaries.
- Do not track generated `outputs/` artifacts, PNG montages, TIF data, `.mat` outputs, or Python cache files.
- `.gitignore` now excludes `outputs/` to avoid accidentally committing multi-GB diagnostic output.

Recommended lightweight commits:

```text
chore(gitignore): ignore generated outputs
docs(dnapl): archive audit segmentation tracking plan
test(color-tuning): add reference audit guardrails
```

## Verification Before Push

Run before committing the Python/documentation checkpoint:

```powershell
git diff --check
$env:PYTHONDONTWRITEBYTECODE='1'; python -m pytest tests/test_reference_score_audit.py tests/test_tune_light_field.py
python -m py_compile tools/color_tuning/tune_light_field.py tools/color_tuning/audit_reference_scores.py
```

## Open Dependencies

- A trusted same-chip full-NAPL endpoint candidate, or additional high-saturation frames for independent validation.
- A MATLAB-exported `flow_domain` / `core_flow` mask or `results_*.mat` for the audited crop.
- A decision on when to promote provisional `S_NAPL_color(t)` into endpoint-validated saturation after masked audit passes.
