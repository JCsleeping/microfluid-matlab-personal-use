# A1 1-BO 6 UL Manual-ROI Full-Residual Sampled Audit

Date: 2026-06-01

## Scope

This run expands the manual-ROI page-1 reference audit from three residual representatives to the full user-defined residual file group.

It uses only the user-defined groups:

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

The bbox was used only to reduce computation. The ROI itself remains the user mask, and statistics are sampled only from nonzero ROI pixels.

Sampling:

- Method: fixed-seed ROI sampling
- Seed: `20260601`
- `all`: up to `300,000` ROI pixels
- `left`, `center`, `right`: up to `100,000` ROI pixels each

This is a screening audit over the full residual file list. It should be followed by an exact full-pixel audit for the final endpoint/score choice before production MATLAB propagation.

## Audit Matrix

Page:

- Page 1 from every source file.

Correction:

- `basicpy_rgb_all`
- working size: `256`
- max iterations: `20`

Matrix size:

```text
3 water endpoint candidates
x 43 residual candidates
x 7 Full NAPL endpoint candidates
x 6 independent high-validation candidates
x 5 score modes
= 27,090 rows
```

Score modes:

- `chroma`
- `lab_ab_projection_global`
- `lab_a`
- `excess_red`
- `normalized_red`

Outputs:

`outputs/masked_reference_audit_20260601/A1_1BO_6UL_manual_roi_page1_full_residual/`

Key files:

- `full_residual_reference_score_rows_sampled.csv`
- `full_residual_endpoint_summary_sampled.csv`
- `full_residual_score_mode_summary_sampled.csv`
- `full_residual_sweep_manifest_sampled.json`

## Score-Mode Result

All tested score modes passed every independent high-validation row.

| Score mode | Rows | Pass | Eligible | S_residual range | Endpoint delta range | Max residual region range |
|---|---:|---:|---:|---:|---:|---:|
| `chroma` | 5418 | 5418 | 5418 | 0.15293-0.15896 | 8.9438-8.9896 | 0.06781 |
| `lab_ab_projection_global` | 5418 | 5418 | 5418 | 0.19681-0.20557 | 10.153-10.176 | 0.09212 |
| `lab_a` | 5418 | 5418 | 5418 | 0.19408-0.20252 | 9.9981-10.037 | 0.09152 |
| `excess_red` | 5418 | 5418 | 5418 | 0.20140-0.21634 | 0.10001-0.10124 | 0.09621 |
| `normalized_red` | 5418 | 5418 | 5418 | 0.19575-0.20981 | 0.03211-0.03248 | 0.09444 |

## Endpoint Ranking

Best screening combination by `chroma`:

- Water endpoint: `water_ep_00_napl_01_1s`
- Full NAPL endpoint: `full_00_water_3s_2`
- Rows: `258`
- Pass rows: `258`
- Eligible rows: `258`
- `S_residual`: `0.15293-0.15687`
- Endpoint delta: `8.9727`
- Minimum separation: `0.83991`
- Max residual left/center/right range: `0.06684`

Other Full NAPL candidates are very close. The first seven `chroma` endpoint rows all pass with `S_residual < 0.158`.

## Interpretation

The full residual sampled audit supports these conclusions:

1. The user-defined water endpoint group is internally consistent for page-1 reference screening.
2. The user-defined Full NAPL group is internally consistent under independent high validation.
3. Every residual file in the user-defined residual group stays much closer to the water endpoint than to the Full NAPL endpoint.
4. `chroma` is currently the strongest primary score for this ROI because it produces the lowest residual normalized values and the smallest residual regional spread.
5. `lab_ab_projection_global` and `lab_a` remain strong secondary quantitative checks with large endpoint deltas.
6. `normalized_red` is monotonic but has a much smaller endpoint delta, so it should not be the primary score.

## Next Gate

Run an exact full-pixel audit for the selected endpoint/score candidates:

```text
Primary:
  score = chroma
  water_endpoint = water_ep_00_napl_01_1s
  napl_endpoint = full_00_water_3s_2

Secondary:
  score = lab_ab_projection_global
  score = lab_a
```

If exact full-pixel results agree with this sampled sweep, the next MATLAB step can use:

```text
S_NAPL_color(t)
endpoint_status = masked_audit_passed
score_mode_primary = chroma
score_mode_secondary = lab_ab_projection_global / lab_a
```

Until the exact full-pixel gate passes, this remains a strong sampled reference-audit result rather than the final production endpoint validation.
