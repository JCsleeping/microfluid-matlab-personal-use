# A1 1-BO 6 uL HDF5 Cache-Fed Branch C Pipeline

Date: 2026-06-01

## Purpose

Promote the validated Python BasicPy HDF5 bridge into a MATLAB Branch C
pipeline run for operational `S_NAPL_color(t)`.

This run intentionally keeps segmentation-derived mask saturation out of the
primary quantitative output. Segmentation remains a secondary visualization and
morphology diagnostic path.

## Pipeline Contract

Input cache:

`outputs/basicpy_hdf5_cache_20260601/A1_1BO_6UL_manual_roi_page1/`

Primary runner:

`run_a1_1bo_6ul_hdf5_cache_branch_c_pipeline.m`

The runner calls:

`run_a1_1bo_6ul_bridge_hdf5_chroma.m`

Quantitative contract:

```text
Python BasicPy corrected RGB HDF5 cache
-> MATLAB h5read bridge
-> compute_bulk_sn_color(chroma)
-> S_NAPL_color(t)
```

Score and statistic:

```text
score_mode = chroma
statistic = winsorized_mean
winsor_percentiles = 1, 99
endpoint_status = masked_audit_passed_exact
```

Endpoint policy:

```text
primary endpoint     = A_full_consistency_primary
sensitivity endpoint = B_residual_separation_primary
```

## Output

Output directory:

`outputs/hdf5_cache_branch_c_pipeline_20260601/A1_1BO_6UL_manual_roi_page1/`

Primary files:

- `S_NAPL_color_primary_A.csv`
- `S_NAPL_color_sensitivity_B.csv`
- `S_NAPL_color_A_B_sensitivity_comparison.csv`
- `branch_c_cache_pipeline_summary.csv`
- `cache_branch_c_manifest.json`
- `S_NAPL_color_A_B_sensitivity.png`

## Result Summary

`branch_c_cache_pipeline_summary.csv`:

| Endpoint | Full-NAPL median | Full-NAPL range | Residual median | Residual range | Bridge gate |
| --- | ---: | ---: | ---: | ---: | --- |
| A_full_consistency_primary | 1.000000 | 0.998873-1.000000 | 0.156809 | 0.155751-0.159308 | pass |
| B_residual_separation_primary | 0.998156 | 0.997029-1.000000 | 0.155087 | 0.154029-0.157586 | pass |

Endpoint sensitivity across 50 frames:

```text
max_abs_endpoint_sensitivity ~= 0.00184448
mean_abs_endpoint_sensitivity ~= 0.00164851
```

The A and B endpoint policies produce nearly overlapping `S_NAPL_color(t)`.
The full-NAPL frames remain near 1, and residual frames remain near
approximately 0.155-0.157.

## Interpretation

This is the first MATLAB-side Branch C run that uses the Python BasicPy
corrected RGB cache as the quantitative source. It confirms the bridge
validation result: when MATLAB and Python use the same corrected RGB arrays,
the Branch C chroma endpoint-normalized color index is stable.

The practical decision is:

```text
Use S_NAPL_color from endpoint A as the primary operational Branch C time series.
Use endpoint B as a sensitivity check.
Do not mix segmentation mask area into the primary S_NAPL_color field.
```

## Next Step

Extend this wrapper from the 50-frame endpoint/residual validation set to the
full A1 1-BO 6 uL time series:

1. build or reuse the BasicPy HDF5 cache for every accepted frame;
2. preserve the same HDF5 contract and ROI mask provenance;
3. run the cache-fed MATLAB Branch C wrapper over the full cache;
4. export `S_NAPL_color(t)` plus endpoint sensitivity diagnostics;
5. keep segmentation overlays as secondary QA outputs.
