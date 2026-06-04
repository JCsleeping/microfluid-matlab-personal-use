# A1 1-BO 6 uL Endpoint Consistency Postprocess

Date: 2026-06-04

## Scope

This adds a reproducible postprocess for the masked endpoint-audit gate after
Branch C has produced endpoint-normalized A/B `S_NAPL_color` CSVs.

It does not rerun RGB correction and does not regenerate segmentation masks. It
checks whether expanded manifest roles are consistent with the already selected
masked-audit endpoints:

```text
full_napl pages should stay near S_NAPL_color = 1
residual pages should stay near S_NAPL_color = 0
```

The practical goal is to catch file-level role labels that span an internal
transition. This is separate from deciding whether page-1 endpoint A/B passed
the masked reference audit.

## Implementation

New postprocess:

```text
tools/reference_audit/endpoint_consistency_postprocess.py
```

Runner step:

```powershell
python run_dnapl_branch_c_timeseries_tool.py --config outputs\standalone_branch_c_runs_20260601\A1_1BO_6UL_manual_roi\smoke_configs\a1_1bo_6ul_chunked_blobdetail_full3585.json --mode full --steps endpointaudit
```

Outputs:

```text
outputs/standalone_branch_c_runs_20260601/A1_1BO_6UL_manual_roi/endpoint_audit/a1_1bo_6ul_manual_roi_full3585_chunked_blobdetail/
```

Key files:

- `endpoint_consistency_timeseries.csv`
- `endpoint_consistency_flags.csv`
- `endpoint_consistency_source_summary.csv`
- `endpoint_consistency_summary.json`

Default thresholds:

```text
full_napl pass: S_NAPL_color_A/B >= 0.9
residual pass:  S_NAPL_color_A/B <= 0.35
```

## A1 Result

Summary:

```text
status = review
rows = 3585
flags = 59
full_napl_below_threshold_count = 59
residual_above_threshold_count = 0
```

All flags are from one expanded full-NAPL source:

```text
source = 01 WATER 1 SECONDS_3.tif
role = full_napl
pages flagged = 11-69
S_NAPL_color_A range over source = 0.157941-1.000000
S_NAPL_color_A median over source = 0.160028
S_NAPL_color_B range over source = 0.156256-0.998834
S_NAPL_color_B median over source = 0.158343
```

The page-1 policy endpoint remains present:

```text
policy_napl_labels =
  full_00_water_3s_2_p001
  full_01_water_1s_3_p001
```

## Interpretation

This does not invalidate the exact page-1 masked endpoint audit. It shows that
`01 WATER 1 SECONDS_3.tif` is not uniformly full-NAPL across all pages. Page 1
is a valid endpoint candidate, but pages 11-69 behave like a transition or
residual-like sequence and should not be used as full-NAPL validation baseline
frames.

The Branch C endpoint A/B sensitivity remains small for the flagged frames; the
issue is expanded role semantics, not disagreement between endpoint A and B.

## Next Action

For strict phase-aware baseline and endpoint validation, either:

1. restrict `01 WATER 1 SECONDS_3.tif` to full-NAPL pages 1-10 through
   `production_role_overrides`, or
2. keep the current manifest and treat endpoint consistency flags as a review
   mask when summarizing full-NAPL baseline statistics.

Do not use file-level `full_napl` role counts alone as proof that every page in
that file is a full-NAPL endpoint validation frame.
