# DNAPL Plan Test Results - 2026-05-30

Worktree:

```text
D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\.worktrees\interpolation-assisted-segmentation-20260527
```

Commit verified:

```text
a87513d feat(dnapl): add masked audit and color-index tools
```

## Summary

All planned guardrail tests for the 2026-05-30 DNAPL masked-audit / segmentation-only / color-index checkpoint passed before pushing.

## Python Verification

Command:

```powershell
python -m pytest tests/test_reference_score_audit.py tests/test_tune_light_field.py tests/test_segment_preview_napl.py -q
```

Result:

```text
20 passed in 2.63s
```

Coverage focus:

- Reference audit mask/provenance guardrails.
- `lab_ab_projection_global` and `lab_ab_projection_pixelwise` split.
- Self-check, contrast-preview, and unmasked audit production-pass rejection.
- Branch A segmentation-only output naming and diagnostics.
- Preview contrast and 2x scale helper behavior.

## Python Compile Check

Command:

```powershell
python -m py_compile tools/color_tuning/tune_light_field.py tools/color_tuning/audit_reference_scores.py tools/color_tuning/segment_preview_napl.py
```

Result:

```text
passed
```

## MATLAB Verification

Command:

```matlab
cd('<worktree>');
addpath(genpath(pwd));
results = runtests({'tests/test_bulk_sn_color.m','tests/test_upscale_assisted_segmentation.m'});
assertSuccess(results);
```

Result:

```text
test_bulk_sn_color: passed
test_upscale_assisted_segmentation: passed
```

Notes:

- The synthetic `test_upscale_assisted_segmentation` suite emitted a known QC warning about flow-domain extraction porosity/pillar fraction in one fixture.
- The warning did not fail the test suite; `assertSuccess(results)` completed successfully.

## Git Checks

Command:

```powershell
git diff --cached --check
```

Result:

```text
passed
```

## Review Check

Subagent re-review confirmed the previous four staged-diff findings were resolved:

- No unstaged `characterize_solubilization_v2` integration dependency remains in the committed test scope.
- Missing `S_NAPL_color*` values are not fabricated from old `saturation_vs_time`.
- MATLAB `mask_id` controls the actual measurement mask.
- Python audit includes JSON manifest, candidate/input provenance, and `eligible_for_segmentation`.

