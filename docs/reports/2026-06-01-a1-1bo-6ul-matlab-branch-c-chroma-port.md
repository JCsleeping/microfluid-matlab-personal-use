# A1 1-BO 6 uL MATLAB Branch C Chroma Port

Date: 2026-06-01

## Purpose

Port the exact-gated Python Branch C result to a MATLAB batch preset for the A1 1-BO 6 uL WATER DISPLACEMENT dataset.

The MATLAB output is `S_NAPL_color`, an operational chroma color-index saturation. It is not the segmentation mask area fraction and should not be mixed with endpoint-normalized physical `Sn` until the full endpoint workflow is frozen.

## Inputs

- ROI mask: `outputs/roi_templates_20260601/A1_1BO_6UL/Mask.tif`
- Native crop rectangle: `[1, 595, 2391, 828]`
- Frame policy: first page only from each user-approved multipage TIF
- Full-NAPL validation frames: 7 files from `01 WATER/00 WATER...` and `01 WATER/01 WATER...`
- Residual frames: 43 files from `01 WATER/02 WATER 3 SECONDS...`
- Water endpoint A: `00 NAPL/00 NAPL 3 SECONDS_1.tif`
- Full endpoint A: `01 WATER/01 WATER 1 SECONDS_3.tif`
- Water endpoint B: `00 NAPL/01 NAPL 1 SECONDS.tif`
- Full endpoint B: `01 WATER/00 WATER 3 SECONDS_2.tif`

## MATLAB Preset

Entrypoint:

```matlab
results = run_a1_1bo_6ul_branch_c_chroma();
```

The preset supports optional endpoint selection:

```matlab
results = run_a1_1bo_6ul_branch_c_chroma('endpoints', 'B', ...
    'output_base', '<existing output base>');
```

Important preset choices:

- `bulk_sn.score_mode = 'chroma'`
- `bulk_sn.endpoint_status = 'masked_audit_passed_exact'`
- `bulk_sn.mask_id = 'flow_domain'`
- `flow_domain.mask_grid = 'native_full'`
- `manifest.hash_policy = 'size_mtime_only'`
- `illumination.method = 'morphological'`
- `illumination.kernel_size = 50`

The TIF files are multipage. The preset computes global `pages` indices so each listed TIF contributes only page 1, matching the Python exact audit page-1 convention.

## Run Output

Output base:

`outputs/matlab_branch_c_a1_1bo_6ul_chroma_20260601_160846/`

Endpoint A output:

`outputs/matlab_branch_c_a1_1bo_6ul_chroma_20260601_160846/endpoint_A_full_consistency_primary/`

Endpoint B output:

`outputs/matlab_branch_c_a1_1bo_6ul_chroma_20260601_160846/endpoint_B_residual_separation_primary/`

Endpoint A was interrupted after CSV/MAT/report export because the original manifest attempted full SHA256 hashing of 50 large multipage TIF files. The preset was then changed to `size_mtime_only`, and endpoint B completed with a metadata-only manifest. Future full A+B runs will use the faster manifest policy.

## MATLAB Result Summary

From `Sn_color_timeseries_*.csv`:

| Endpoint | Full S_NAPL_color median | Full range | Residual S_NAPL_color median | Residual range | Final S_NAPL_color |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | 1.000000 | 1.000000-1.000000 | 0.199731 | 0.198293-0.202221 | 0.198293 |
| B | 1.000000 | 0.998503-1.000000 | 0.193628 | 0.192181-0.196131 | 0.192181 |

Secondary segmentation mask fraction from the same run:

| Endpoint | Full mask median | Residual mask median |
| --- | ---: | ---: |
| A | 0.650943 | 0.140767 |
| B | 0.656494 | 0.143287 |

The segmentation self-test marked full-NAPL mask extraction as review/fail because the mask fraction is below the configured `0.85` full-NAPL threshold. This is a segmentation-mask diagnostic and does not invalidate the Branch C chroma `S_NAPL_color` output.

## QC Notes

- Flow-domain QC reports `failed_nonblocking` because the user ROI mask has porosity about `0.905` and pillar fraction about `0.095`, outside the generic automatic-mask QC range.
- This is expected for this user-supplied ROI mask and is intentionally nonblocking in the preset.
- MATLAB residual `S_NAPL_color` is about `0.19-0.20`, whereas the Python BasicPy exact audit residual was about `0.155`.
- The difference should be treated as a preprocessing difference: MATLAB currently uses morphological illumination correction, not the Python BasicPy corrected RGB used in the exact audit.

## Current Recommendation

Use MATLAB endpoint A as the default Branch C chroma output and endpoint B as sensitivity:

```text
score_mode_primary = chroma
endpoint_default = A_full_consistency_primary
endpoint_sensitivity = B_residual_separation_primary
endpoint_status = masked_audit_passed_exact
output_name = S_NAPL_color
```

Before using MATLAB values as the final reported timeseries, decide whether MATLAB should reproduce the Python BasicPy correction or whether the morphological-corrected MATLAB series is acceptable as a separate processing branch.
