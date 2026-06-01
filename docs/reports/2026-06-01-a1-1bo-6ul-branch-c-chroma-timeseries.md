# A1 1-BO 6 UL Branch C Chroma Time-Series

Date: 2026-06-01

## Scope

This derives the first Branch C operational color-index time-series from the exact full-pixel endpoint audit.

It does not rerun illumination correction. It uses the exact audit rows from:

`outputs/masked_reference_audit_20260601/A1_1BO_6UL_manual_roi_page1_exact_shortlist/exact_shortlist_reference_score_rows.csv`

The output is an operational color-index saturation:

```text
S_NAPL_color(t)
```

It should not be renamed to final physical `Sn` until the MATLAB production path and any volume/geometry calibration are finalized.

## Inputs

Mask:

- Manual ROI: `outputs/roi_templates_20260601/A1_1BO_6UL/Mask.tif`
- Exact ROI pixels: `1,794,675`

Score:

- Primary score: `chroma`
- Endpoint status: `masked_audit_passed_exact`

Endpoint variants:

| Variant | Purpose | Water endpoint | Full NAPL endpoint |
|---|---|---|---|
| A | Full-NAPL consistency primary | `water_ep_00_napl_00_3s_1` | `full_01_water_1s_3` |
| B | Residual-separation primary | `water_ep_00_napl_01_1s` | `full_00_water_3s_2` |

Frames:

- 7 user-defined Full NAPL frames
- 43 user-defined residual frames
- 50 frames total per endpoint variant

The frame order is the user-defined list order, not inferred from directory names.

## Outputs

Output directory:

`outputs/branch_c_timeseries_20260601/A1_1BO_6UL_manual_roi_page1_chroma_exact/`

Key files:

- `derive_branch_c_chroma_timeseries.py`
- `branch_c_chroma_timeseries_endpoint_variants.csv`
- `branch_c_chroma_endpoint_variant_comparison.csv`
- `branch_c_chroma_timeseries_summary.csv`
- `branch_c_chroma_endpoint_variant_timeseries.png`

## Time-Series Summary

| Variant | Frame role | Frames | Min S | Median S | Max S | Max region range |
|---|---|---:|---:|---:|---:|---:|
| A | Full NAPL | 7 | 0.998862 | 1.000000 | 1.002449 | 0.002647 |
| A | Residual | 43 | 0.154098 | 0.155181 | 0.157660 | 0.066070 |
| B | Full NAPL | 7 | 0.997023 | 0.998160 | 1.000609 | 0.002788 |
| B | Residual | 43 | 0.152392 | 0.153475 | 0.155954 | 0.065930 |

## Endpoint Variant Difference

The A/B difference is small and nearly constant.

| Frame role | Count | Min abs(A-B) | Median abs(A-B) | Max abs(A-B) |
|---|---:|---:|---:|---:|
| Full NAPL | 7 | 0.001839 | 0.001840 | 0.001840 |
| Residual | 43 | 0.001706 | 0.001706 | 0.001706 |

This means endpoint selection between A and B has negligible impact on the time-series shape for this page-1 ROI. B shifts values slightly lower, but the trend is unchanged.

## Interpretation

Branch C is now operational for this ROI/page combination.

The observed structure is consistent with the endpoint audit:

- Full NAPL frames stay near `S_NAPL_color = 1`.
- Residual frames stay near `S_NAPL_color = 0.153-0.158`.
- A and B endpoint variants are effectively equivalent for trend analysis.
- `chroma` remains the preferred Branch C score because it gives lower residual values than `lab_a` and `lab_ab_projection_global`.

Recommended default:

```text
score_mode_primary = chroma
endpoint_default = A_full_consistency_primary
endpoint_sensitivity = B_residual_separation_primary
endpoint_status = masked_audit_passed_exact
output_name = S_NAPL_color
```

The reason to default to A is that it optimizes Full-NAPL endpoint consistency. B should be retained as a sensitivity check because it gives the lowest residual baseline.

## MATLAB Port Implication

The MATLAB Branch C port can now implement:

1. BaSiC/equivalent quantitative RGB correction.
2. Manual ROI / flow-domain mask support.
3. `chroma` score inside ROI.
4. Endpoint normalization using default endpoint A.
5. Optional sensitivity output using endpoint B.
6. Per-frame outputs:
   - `S_NAPL_color_raw`
   - `S_NAPL_color_clamped`
   - left/center/right regional values
   - endpoint provenance
   - `endpoint_status = masked_audit_passed_exact`

The current Python-derived time-series has total and left/center/right regional values. Finer x-bin outputs can be added in the MATLAB port if needed for spatial profiles.
