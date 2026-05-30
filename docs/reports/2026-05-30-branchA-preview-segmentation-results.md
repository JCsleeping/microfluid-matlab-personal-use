# Branch A Preview Segmentation Results - 2026-05-30

Output directory:

```text
D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\.worktrees\interpolation-assisted-segmentation-20260527\outputs\branchA_preview_segmentation_20260530\v1_lab_a_thr40
```

Inputs:

```text
outputs\python_stepwise_illumination_reference_20260530\03_scale2_preview\basicpy_rgb_all\high_preview.png
outputs\python_stepwise_illumination_reference_20260530\03_scale2_preview\basicpy_rgb_all\residual_preview.png
```

Method:

```text
Branch A segmentation-only preview mask
score_mode = lab_a
threshold = 40.0
min_area_px = 20
domain_mask = none/all-image diagnostic
```

Important semantics:

```text
Outputs are segmentation_mask and red_mask_area_fraction only.
They are not endpoint-normalized Sn and not physical saturation.
```

Summary:

| frame | red_mask_area_fraction | component_count | largest_component_fraction |
| --- | ---: | ---: | ---: |
| high | 0.2248 | 348 | 0.694 |
| residual | 0.0594 | 494 | 0.058 |

Generated files:

```text
high_segmentation_overlay.png
high_segmentation_mask.png
high_threshold_sweep.csv
high_segmentation_diagnostics.json
high_red_score.png
residual_segmentation_overlay.png
residual_segmentation_mask.png
residual_threshold_sweep.csv
residual_segmentation_diagnostics.json
residual_red_score.png
segmentation_summary.csv
run_manifest.json
```

Interpretation:

- The high-saturation preview produces a larger, spatially connected red mask.
- The residual preview produces a much smaller and fragmented red mask.
- This is an initial segmentation-only result; the next check is visual review of overlays and threshold sweep before promoting any parameter set to MATLAB batch processing.

