# A1 1-BO 6 UL Manual-ROI Page-1 Reference Audit

Date: 2026-06-01

## Scope

This audit supersedes the earlier discarded diagnostic run that used the wrong residual source and an old MATLAB crop. The current run uses only the user-provided manual ROI mask and the user-defined reference groups.

Manual ROI mask:

`D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\.worktrees\interpolation-assisted-segmentation-20260527\outputs\roi_templates_20260601\A1_1BO_6UL\Mask.tif`

Mask provenance:

- Image shape: `2048 x 2448`
- Mask dtype: `uint8`
- Nonzero pixels: `1,794,675`
- Coverage: `35.8%`
- Mask grid: native full image
- No MATLAB-derived crop was used.

Mask overlay for visual verification:

`outputs/roi_templates_20260601/A1_1BO_6UL/roi_template_native_page1_mask_overlay.png`

## User-Defined Groups

Folder names were not used as semantic labels. The groups below follow the user's definitions.

Water endpoint candidates:

- `00 NAPL\00 NAPL 3 SECONDS.tif`
- `00 NAPL\00 NAPL 3 SECONDS_1.tif`
- `00 NAPL\01 NAPL 1 SECONDS.tif`

Full NAPL candidates:

- `01 WATER\00 WATER 3 SECONDS.tif`
- `01 WATER\00 WATER 3 SECONDS_1.tif`
- `01 WATER\00 WATER 3 SECONDS_2.tif`
- `01 WATER\01 WATER 1 SECONDS.tif`
- `01 WATER\01 WATER 1 SECONDS_1.tif`
- `01 WATER\01 WATER 1 SECONDS_2.tif`
- `01 WATER\01 WATER 1 SECONDS_3.tif`

Residual representative candidates used in this first pass:

- `01 WATER\02 WATER 3 SECONDS.tif`
- `01 WATER\02 WATER 3 SECONDS_21.tif`
- `01 WATER\02 WATER 3 SECONDS_42.tif`

The full residual group has more files. This report is a page-1 representative audit, not an all-file/all-page residual sweep.

## Audit Settings

- Tool: `tools/color_tuning/audit_reference_scores.py`
- Page: `1`
- Correction: `basicpy_rgb_all`
- BaSiC working size: `256`
- BaSiC max iterations: `20`
- Mask id: `flow_domain`
- Mask source: `image`
- Mask grid: `native_full`
- RGB source: `corrected_quantitative`
- High validation frame: `01 WATER\00 WATER 3 SECONDS.tif`, page 1

The high validation frame is also one of the Full NAPL candidates, so that candidate's row is a self-check. The other six Full NAPL candidates are independent high-validation rows in this audit.

Outputs:

`outputs/masked_reference_audit_20260601/A1_1BO_6UL_manual_roi_page1/`

Combined CSV:

- `combined_reference_score_ranking.csv`
- `combined_reference_score_summary.csv`

## Main Result

Across the independent high-validation rows:

| Score mode | Runs | Pass | Eligible | S_residual range | Endpoint delta range |
|---|---:|---:|---:|---:|---:|
| `chroma` | 54 | 54 | 54 | 0.1715-0.1858 | 6.177-6.230 |
| `lab_ab_projection_global` | 54 | 54 | 54 | 0.2000-0.2079 | 7.609-7.627 |
| `lab_a` | 54 | 54 | 54 | 0.1994-0.2065 | 7.485-7.504 |
| `excess_red` | 54 | 54 | 54 | 0.2013-0.2153 | 0.07137-0.07229 |
| `normalized_red` | 54 | 54 | 54 | 0.1982-0.2114 | 0.03200-0.03239 |

Interpretation:

1. All three water endpoint candidates behave consistently in the manual ROI.
2. All six independent Full NAPL candidates pass against the selected high-validation frame across the three residual representatives.
3. `chroma` gives the lowest residual normalized values and the largest robust separation.
4. `lab_ab_projection_global` and `lab_a` are strong quantitative candidates because their endpoint deltas are large and stable.
5. `excess_red` and `normalized_red` are monotonic, but their endpoint deltas are much smaller.

## Recommended Next Step

Use this page-1 result to narrow the next full audit:

- Primary score candidates: `chroma`, `lab_ab_projection_global`, `lab_a`
- Secondary checks: `excess_red`, `normalized_red`
- Water endpoint: any of the three tested candidates is acceptable for the next sweep
- Full NAPL endpoint: any independent Full NAPL candidate passed this first audit

Next audit should expand residual coverage from the three representatives to the full residual file list, and optionally sample more than page 1 per file. Until that expanded audit is run, treat this result as a strong page-1 reference audit, not the final all-frame endpoint validation.
