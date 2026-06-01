# A1 1-BO 6 UL Full-NAPL Endpoint Consistency Screening

Date: 2026-06-01

## Scope

This is Stage 1 sampled screening for Full-NAPL endpoint consistency. It uses the same user-defined manual ROI mask and source groups as the full-residual sampled audit.

The purpose is endpoint screening, not segmentation tuning. It asks whether each user-defined Full NAPL candidate behaves like a stable high endpoint when validated against the other Full NAPL frames, then checks that the full-residual group remains separated from that endpoint.

Path names are not interpreted as semantic labels. Roles are the user-defined roles:

- Water endpoints: the three user-specified files under `00 NAPL`.
- Full NAPL candidates: the seven user-specified `00 WATER...` / `01 WATER...` files.
- Residual candidates: `02 WATER 3 SECONDS.tif` through `02 WATER 3 SECONDS_42.tif`.

It does not use root-level `RESIDUAL 1/2/3.tif`.

## ROI And Sampling

Manual ROI mask:

`outputs/roi_templates_20260601/A1_1BO_6UL/Mask.tif`

Mask facts:

- Native image shape: `2048 x 2448`
- Nonzero ROI pixels: `1,794,675`
- ROI coverage: `35.8%`
- Auto-derived computation bbox from the user mask: `[1, 595, 2391, 828]`

The bbox is only a computation optimization. Statistics remain restricted to nonzero pixels in the user mask.

Sampling:

- Method: fixed-seed ROI sampling
- Seed: `20260601`
- `all`: up to `300,000` ROI pixels
- `left`, `center`, `right`: up to `100,000` ROI pixels each

## Inputs

This screening is derived from the sampled full-residual audit rows:

`outputs/masked_reference_audit_20260601/A1_1BO_6UL_manual_roi_page1_full_residual/full_residual_reference_score_rows_sampled.csv`

Derived Stage 1 output files:

- `outputs/masked_reference_audit_20260601/A1_1BO_6UL_manual_roi_page1_full_residual/full_napl_endpoint_consistency_ranking_sampled.csv`
- `outputs/masked_reference_audit_20260601/A1_1BO_6UL_manual_roi_page1_full_residual/full_napl_endpoint_consistency_mode_summary_sampled.csv`

Score modes:

- `chroma`
- `lab_ab_projection_global`
- `lab_a`
- `excess_red`
- `normalized_red`

OD modes are not used in this screen.

## Stage 1 Gate

For each score mode, water endpoint, and Full NAPL endpoint candidate, independent Full NAPL validation frames must satisfy:

- `median(abs(S_full_validation - 1)) <= 0.05`
- `max(abs(S_full_validation - 1)) <= 0.10`
- `max(S_residual) <= 0.35`
- `min(S_full_validation) - max(S_residual) >= 0.50`
- `max full-validation left/center/right range <= 0.15`
- `max residual left/center/right range <= 0.15`

Endpoint delta thresholds:

- `chroma`, `lab_a`, `lab_ab_projection_global`: `abs(endpoint_delta) >= 1.0`
- `excess_red`: `abs(endpoint_delta) >= 0.03`
- `normalized_red`: `abs(endpoint_delta) >= 0.01`

## Score-Mode Summary

All tested combinations pass Stage 1.

Each score mode contains:

```text
3 water endpoint candidates
x 7 Full NAPL endpoint candidates
= 21 candidate endpoint combinations
```

| Score mode | Candidates | Passed | Median full-error range | Max full-error range | Minimum margin | Max residual |
|---|---:|---:|---:|---:|---:|---:|
| `chroma` | 21 | 21 | 0.001269-0.002510 | 0.001908-0.003229 | 0.838334 | 0.158964 |
| `lab_a` | 21 | 21 | 0.000256-0.001646 | 0.001321-0.002261 | 0.795686 | 0.202517 |
| `lab_ab_projection_global` | 21 | 21 | 0.001307-0.003414 | 0.002623-0.005433 | 0.789769 | 0.205574 |
| `excess_red` | 21 | 21 | 0.001693-0.004696 | 0.003762-0.007316 | 0.777994 | 0.216342 |
| `normalized_red` | 21 | 21 | 0.001685-0.004655 | 0.003693-0.007069 | 0.784669 | 0.209810 |

## Best Stage 1 Rows

Best overall row by Full-NAPL internal consistency:

- Score mode: `chroma`
- Water endpoint: `water_ep_00_napl_00_3s_1`
- Full NAPL endpoint: `full_01_water_1s_3`
- Full validation frames: `6`
- Median full-validation error: `0.001269`
- Max full-validation error: `0.001908`
- `S_full_validation`: `0.998092-1.001309`
- Max full left/center/right range: `0.003491`
- Residual frames: `43`
- `S_residual`: `0.154724-0.158661`
- Residual margin: `0.839431`
- Max residual left/center/right range: `0.067719`
- Endpoint delta: `8.977864`

Best `lab_ab_projection_global` row:

- Water endpoint: `water_ep_00_napl_00_3s_1`
- Full NAPL endpoint: `full_01_water_1s_1`
- Median full-validation error: `0.001307`
- Max full-validation error: `0.003448`
- `S_residual`: `0.197241-0.202543`
- Residual margin: `0.794009`
- Endpoint delta: `10.176185`

Best `lab_a` row:

- Water endpoint: `water_ep_00_napl_00_3s_1`
- Full NAPL endpoint: `full_01_water_1s`
- Median full-validation error: `0.000256`
- Max full-validation error: `0.001594`
- `S_residual`: `0.195483-0.202194`
- Residual margin: `0.796212`
- Endpoint delta: `10.029954`

## Interpretation

Stage 1 supports the Full NAPL endpoint group. The seven user-defined Full NAPL candidates are mutually consistent under independent high validation, and every residual frame remains much closer to the water endpoint than to the Full NAPL endpoint.

The earlier residual-focused sampled audit selected:

```text
score = chroma
water_endpoint = water_ep_00_napl_01_1s
napl_endpoint = full_00_water_3s_2
```

because it minimized residual normalized values. This Stage 1 consistency screen selects:

```text
score = chroma
water_endpoint = water_ep_00_napl_00_3s_1
napl_endpoint = full_01_water_1s_3
```

because it has the smallest independent Full-NAPL validation error.

These are not contradictory. They optimize different parts of the endpoint gate:

- Full-NAPL internal consistency: best at `full_01_water_1s_3`.
- Residual separation: best sampled residual behavior previously observed at `full_00_water_3s_2`.
- Primary score family: `chroma` remains strongest because it keeps residual values lowest and has low regional spread.
- Secondary checks: `lab_ab_projection_global` and `lab_a` remain strong endpoint-axis checks.

## Exact Full-Pixel Shortlist

Before promoting `chroma` into MATLAB Branch C as the main score, run exact full-pixel confirmation without sampling.

Recommended exact shortlist:

1. Full-NAPL consistency primary:
   - `score = chroma`
   - `water_endpoint = water_ep_00_napl_00_3s_1`
   - `napl_endpoint = full_01_water_1s_3`

2. Residual-separation primary:
   - `score = chroma`
   - `water_endpoint = water_ep_00_napl_01_1s`
   - `napl_endpoint = full_00_water_3s_2`

3. Endpoint-axis secondary check:
   - `score = lab_ab_projection_global`
   - `water_endpoint = water_ep_00_napl_00_3s_1`
   - `napl_endpoint = full_01_water_1s_1`

Optional fourth check if runtime permits:

- `score = lab_a`
- `water_endpoint = water_ep_00_napl_00_3s_1`
- `napl_endpoint = full_01_water_1s`

## Current Gate Status

Stage 1 sampled Full-NAPL endpoint consistency screening: passed.

Production gate status: not final yet.

The next gate is exact full-pixel audit on the shortlist above. If exact results agree with this sampled screen, `chroma` can be promoted as the MATLAB Branch C primary score with `endpoint_status = masked_audit_passed`.
