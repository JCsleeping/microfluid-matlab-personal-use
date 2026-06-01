# A1 1-BO 6 UL Exact Full-Pixel Shortlist Audit

Date: 2026-06-01

## Scope

This is the Stage 2 exact full-pixel audit after the sampled Full-NAPL endpoint consistency screening.

It uses the same user-defined manual ROI mask and source roles as the sampled screens. No path names are interpreted as semantic labels.

This run is exact inside the ROI: no pixel sampling is used.

## ROI

Manual ROI mask:

`outputs/roi_templates_20260601/A1_1BO_6UL/Mask.tif`

Mask facts:

- Native image shape: `2048 x 2448`
- Nonzero ROI pixels: `1,794,675`
- ROI coverage: `35.8%`
- Auto-derived computation bbox from the user mask: `[1, 595, 2391, 828]`

The bbox is only a computation optimization. All statistics are computed from nonzero pixels in the user mask.

Exact ROI pixels:

- `all`: `1,794,675`
- `left`: `598,225`
- `center`: `598,225`
- `right`: `598,225`

## Inputs

Correction:

- `basicpy_rgb_all`
- working size: `256`
- max iterations: `20`

Source groups:

- Water endpoints: user-defined water endpoint files under `00 NAPL`.
- Full NAPL candidates: user-defined `00 WATER...` / `01 WATER...` files.
- Residual candidates: `02 WATER 3 SECONDS.tif` through `02 WATER 3 SECONDS_42.tif`.

It does not use root-level `RESIDUAL 1/2/3.tif`.

## Exact Shortlist

| ID | Purpose | Score | Water endpoint | Full NAPL endpoint |
|---|---|---|---|---|
| A | Full-NAPL consistency primary | `chroma` | `water_ep_00_napl_00_3s_1` | `full_01_water_1s_3` |
| B | Residual-separation primary | `chroma` | `water_ep_00_napl_01_1s` | `full_00_water_3s_2` |
| C | Lab a/b endpoint-axis secondary | `lab_ab_projection_global` | `water_ep_00_napl_00_3s_1` | `full_01_water_1s_1` |
| D | Lab a* optional check | `lab_a` | `water_ep_00_napl_00_3s_1` | `full_01_water_1s` |

Each shortlist row validates against:

- 6 independent Full NAPL validation frames
- 43 residual frames

So each row contains `258` exact validation rows.

## Gate

Exact gate thresholds:

- `median(abs(S_full_validation - 1)) <= 0.05`
- `max(abs(S_full_validation - 1)) <= 0.10`
- `max(S_residual) <= 0.35`
- `min(S_full_validation) - max(S_residual) >= 0.50`
- `max full-validation left/center/right range <= 0.15`
- `max residual left/center/right range <= 0.15`
- `abs(endpoint_delta) >= 1.0` for `chroma`, `lab_a`, and `lab_ab_projection_global`

## Results

All exact shortlist candidates pass.

| ID | Score | Stage 2 | Median full error | Max full error | Full S range | Residual S range | Margin | Endpoint delta | Max full region range | Max residual region range |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | `chroma` | pass | 0.001029 | 0.002449 | 0.998862-1.002449 | 0.154098-0.157660 | 0.841202 | 8.964013 | 0.002647 | 0.066070 |
| B | `chroma` | pass | 0.002050 | 0.002977 | 0.997023-1.000609 | 0.152392-0.155954 | 0.841069 | 8.965431 | 0.002788 | 0.065930 |
| C | `lab_ab_projection_global` | pass | 0.001422 | 0.002791 | 0.997209-1.002092 | 0.198086-0.202654 | 0.794555 | 10.180816 | 0.003811 | 0.092836 |
| D | `lab_a` | pass | 0.000245 | 0.001048 | 0.998952-0.999969 | 0.196853-0.202871 | 0.796082 | 10.039386 | 0.004945 | 0.091969 |

## Output Files

`outputs/masked_reference_audit_20260601/A1_1BO_6UL_manual_roi_page1_exact_shortlist/`

Key files:

- `run_exact_shortlist_audit.py`
- `exact_shortlist_reference_score_rows.csv`
- `exact_shortlist_gate_summary.csv`
- `exact_shortlist_mode_summary.csv`
- `exact_shortlist_manifest.json`

## Interpretation

Stage 2 confirms the sampled result. `chroma` is eligible as the MATLAB Branch C primary score for this ROI and page-1 endpoint audit.

The two `chroma` endpoint choices are both valid but optimize slightly different goals:

- A, `water_ep_00_napl_00_3s_1 + full_01_water_1s_3`, is the better Full-NAPL endpoint consistency choice. It has lower median full-validation error.
- B, `water_ep_00_napl_01_1s + full_00_water_3s_2`, is the better residual-separation choice. It has the lowest residual `S` values and slightly smaller residual regional range.

The differences are small. For production tracking, use `chroma` as the primary score and keep both A and B as sensitivity endpoints until time-series behavior is checked.

Recommended Branch C labeling:

```text
score_mode_primary = chroma
endpoint_status = masked_audit_passed_exact
endpoint_variant_A = full_consistency_primary
endpoint_variant_B = residual_separation_primary
```

`lab_ab_projection_global` and `lab_a` should remain secondary checks. They pass the endpoint gate, but residual values are higher than `chroma`.

## Next Step

Run Branch C time-series extraction using exact-gated `chroma`:

1. Compute `S_NAPL_color(t)` with endpoint variant A.
2. Compute `S_NAPL_color(t)` with endpoint variant B.
3. Compare total/core/x-bin time-series shape and residual endpoint behavior.
4. If A and B produce the same trend within tolerance, promote one endpoint to the default MATLAB Branch C endpoint.
