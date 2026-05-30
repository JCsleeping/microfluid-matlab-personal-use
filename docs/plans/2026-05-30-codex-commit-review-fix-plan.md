# Codex Commit Review Fix Plan

Date: 2026-05-30

Source review:
`C:\Users\ASUS\.gemini\antigravity-ide\brain\e6ff6069-4a6a-4c0d-b6ed-bfeb8074c2c2\codex_commit_review.md`

## Scope

This follow-up addresses the review items that can affect the next DNAPL audit or segmentation run:

1. Fix Branch A `hsv_red_pink` hue wrap-around for red hues near 360 degrees.
2. Add explicit comments for `lab_ab_projection_global` so future maintainers do not mistake the linear Q projection for a pre-normalized saturation value.
3. Clarify that failed endpoint audit rows can still be eligible for provisional Branch C color-index time series when the RGB source and mask are valid.
4. Add a clear MATLAB v7.3/HDF5 `.mat` mask loading error path.
5. Reject prepared masks with zero selected pixels after crop/resize.
6. Report disabled MATLAB Branch C provenance as `endpoint_status = "not_computed"` instead of `"provisional"`.

## Test-First Checklist

- Add Python tests for empty prepared masks, MATLAB v7.3/HDF5 mask load errors, sparse region masks, and near-zero global Lab endpoint deltas.
- Add a Python test for `hsv_red_pink` scoring around the 360 degree hue boundary.
- Add a MATLAB test for disabled Branch C provenance.
- Run the new tests before production code changes and confirm they fail for the expected reasons.

## Deferred Follow-Up

The full synthetic TIF CLI integration test remains useful, but it is not required to close the review's must-fix items. It should be added with the first real masked-audit batch runner so the test can cover the production command-line surface without duplicating fixture setup.

## Completion Gate

The fix is complete only after:

- Python unit tests pass for `test_reference_score_audit.py`, `test_segment_preview_napl.py`, and `test_tune_light_field.py`.
- Python color-tuning scripts compile with `py_compile`.
- MATLAB `test_bulk_sn_color.m` passes.
- `git diff --check` passes.
- The fix is committed and pushed on `feat/interpolation-assisted-segmentation-20260527`.

## Execution Results

Implemented in this follow-up:

- `audit_reference_scores.py` now rejects zero-pixel prepared masks, reports clear MATLAB v7.3/HDF5 `.mat` mask-load guidance, and documents Branch C provisional eligibility plus global Lab Q projection semantics.
- `segment_preview_napl.py` now uses an explicit circular hue distance for `hsv_red_pink`.
- `compute_bulk_sn_from_config.m` now reports disabled Branch C as `endpoint_status = "not_computed"` and `rgb_source = ""`.
- Tests now cover sparse mask partitioning, empty mask rejection, v7.3/HDF5 `.mat` error reporting, near-zero Lab endpoint deltas, HSV red wrap-around, and disabled MATLAB provenance.

Verification run:

- `python -m pytest tests/test_reference_score_audit.py tests/test_segment_preview_napl.py tests/test_tune_light_field.py -q` -> 25 passed.
- `python -m py_compile tools/color_tuning/tune_light_field.py tools/color_tuning/audit_reference_scores.py tools/color_tuning/segment_preview_napl.py` -> passed.
- `matlab -batch "cd('<repo>'); addpath(genpath(pwd)); results = runtests('tests/test_bulk_sn_color.m'); assertSuccess(results);"` -> passed.
- `git diff --check` -> passed.
