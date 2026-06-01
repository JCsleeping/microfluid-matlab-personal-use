# G21 Blob Morphology Data Product Design

## Decision

Build a full-duration G21 2D blob morphology data product from the passed full sidecar output:

```text
C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418\geometry_sidecar_full_20260519_172548
```

This supersedes the earlier limited/subset morphology plan. The current full sidecar has already passed the execution gate:

```text
ProcessedFrames = 12024
GeometryBlobRows = 1362316
BlobCountPassFrames = 12024
TotalAreaPassFrames = 12024
MaxConsecutiveMismatchFrames = 0
EmptyGeometryFrames = 0
BoundaryMetricValidRows = 636397
BlockedForInterpretation = false
MismatchClusterReviewRequired = false
```

The data product is a measurement layer, not a results interpretation package. It should produce reusable CSV/JSON/figure artifacts that describe projected blob structure and representative blob examples.

## Scientific Scope

Allowed:

- Full-duration 2D projected blob morphology.
- Projected area and equivalent projected diameter.
- 2D circularity / compactness.
- Projected elongation from long/short axes.
- 2D convexity / solidity / concavity.
- Exterior-boundary irregularity proxy in reliable tiers.
- Area-tier and boundary-valid reliability filtering.
- Representative blob atlas built from labels/masks.

Not allowed:

- 3D sphericity.
- True Wadell roundness as a final metric.
- 3D roughness.
- True fluid-fluid interfacial area.
- Boundary fractal dimension.
- Tracking, split/merge lineage, or per-blob lifetime.
- Causal mechanism claims from morphology distributions alone.

## Literature Translation

The particle-shape literature motivates the product but should not be copied literally.

- Cho et al. style shape scales separate global form, major feature roundness, and surface roughness.
- QICPIC-style binary image metrics use projected area, projected perimeter, Feret diameters, and convex hull area.
- The 2013 image-based sand-particle approach uses aspect ratio, convexity, and a projected sphericity-like metric.
- The 2018 stress-dilatancy study defines binary-image metrics as `S_C = P_eq / P_r`, `A_R = D_min^F / D_max^F`, `C_X = A / ConvexHullArea`, and `O_R = (S_C + A_R + C_X) / 3`.

For G21 blobs, these become 2D projected analogues because the segmentation is a fixed projection, not a freely oriented 3D particle measurement.

## Metric Mapping

| Literature concept | G21 product field | Definition | Interpretation |
|---|---|---|---|
| Sphericity `S` | `ProjectedSphericity2D` | `2 * sqrt(pi * Area_px) / P_outer_boundary` | 2D projected circle-form analogue, not 3D sphericity |
| Circularity / compactness `CR` | `Circularity2D_boundary` | `4 * pi * Area_px / P_outer_boundary^2` | Square of projected sphericity; use only in valid tiers |
| Aspect ratio `AR` | `AspectRatio01` | `MinorAxisLength_px / MajorAxisLength_px` | Literature-style 0-1 projected aspect ratio |
| Elongation | `AxisAspectRatio` | `MajorAxisLength_px / MinorAxisLength_px` | Engineering-friendly elongation metric |
| Convexity `C_X` | `Solidity2D` | `Area_px / ConvexArea_px` | 2D concavity / convex-hull filling |
| Perimeter `P` | `P_outer_boundary`, `P_total_boundary`, `Pc_outer_boundary` | Existing sidecar fields | Separate exterior, total, and convex perimeter diagnostics |
| Roundness `R` | no direct final metric | not computed as Wadell corner-radius roundness | Too scale-sensitive for pixelated NAPL boundaries |
| Regularity `rho` or `O_R` | `ProjectedRegularity2D` | mean of `ProjectedSphericity2D`, `AspectRatio01`, and `Solidity2D` | Composite 2D projected regularity, not particle regularity |
| Roughness proxy | `ProjectedRoughness_boundary` | `P_outer_boundary / Pc_outer_boundary` | 2D exterior-boundary irregularity proxy |
| Internal boundary diagnostic | `PtotalOverPouter` | `P_total_boundary / P_outer_boundary` | Projected total-boundary diagnostic, not true interface area |

`ProjectedSphericity2D` and `Circularity2D_boundary` are redundant but useful in different contexts. The former aligns with QICPIC-style `S_C`; the latter is common in image analysis and already exists in sidecar outputs.

## Reliability Policy

All blobs can be used for counts, area distributions, and population size statistics. Boundary-derived morphology must be filtered.

Default reliability classes:

```text
count_only_small      Area_px < 250
caution_medium        AreaTier == medium or marginal boundary quality
geometry_valid        Area_px >= 250 and BoundaryMetricValid == true
high_confidence       Area_px >= 500 and BoundaryMetricValid == true
boundary_invalid      BoundaryMetricValid == false for boundary metrics
```

Boundary metrics must be summarized with denominators:

```text
N_total
N_boundary_valid
AreaFraction_boundary_valid
N_area_ge_250
N_area_ge_500
```

Tiny/small blobs must not be promoted into boundary-mechanism classes.

## Shape-Class v0

Shape classes should be descriptive and measurement-based:

```text
small_unclassified
boundary_invalid
medium_caution
compact_round
compact_irregular
elongated
concave_lobed
branched_complex
ambiguous_valid
```

Default assignment order:

1. `Area_px < 250` -> `small_unclassified`
2. `BoundaryMetricValid == false` -> `boundary_invalid`
3. `AreaTier == medium` and not high-confidence -> `medium_caution`
4. high `ProjectedSphericity2D`, high `Solidity2D`, low `AxisAspectRatio` -> `compact_round`
5. high `AxisAspectRatio` -> `elongated`
6. low `Solidity2D` and moderate elongation -> `concave_lobed`
7. low `Solidity2D` plus high elongation or high `ProjectedRoughness_boundary` -> `branched_complex`
8. otherwise -> `ambiguous_valid`

Thresholds should be derived from the valid reference population:

```text
BoundaryMetricValid == true
Area_px >= 250
```

Use quantiles (`q25`, `q50`, `q75`, `q90`) and store all thresholds in `blob_morphology_thresholds.json`.

## Data Product Outputs

Primary outputs:

```text
blob_morphology_by_blob.csv
blob_morphology_by_frame.csv
blob_reliability_summary_by_frame.csv
blob_morphology_reliability_by_tier.csv
blob_shape_class_by_blob.csv
blob_shape_class_summary_by_frame.csv
blob_morphology_thresholds.json
representative_blob_candidates.csv
blob_morphology_manifest.json
blob_morphology_qc_summary.md
```

Atlas outputs, generated after table QC passes:

```text
representative_blob_atlas_manifest.csv
figures_blob_morphology_atlas/
```

## Representative Atlas

The atlas should emulate particle-shape chart logic without overclaiming.

Recommended figures:

1. Full-duration morphology metric distributions.
2. 2D shape-space density with representative blob thumbnails.
3. Representative binary blob atlas arranged by circularity/solidity/aspect ratio.
4. Table-like audit panel with binary mask, boundary overlay, area, circularity, aspect ratio, solidity, and QC flags.
5. QC/exclusion atlas showing why some blobs are count-only or boundary-invalid.

Representative selection should use medoids in standardized morphology space:

```text
log_area
ProjectedSphericity2D
AspectRatio01
Solidity2D
ProjectedRoughness_boundary
PtotalOverPouter
```

Selection reasons must be explicit:

```text
class_medoid
high_confidence_exemplar
shape_extreme
large_area_exemplar
qc_exclusion_example
```

## Implementation Constraints

- Do not rerun segmentation, sidecar extraction, tracking, or fractal analysis.
- Treat sidecar output as immutable input.
- Use chunked/two-pass reads over `geometry_by_blob.csv`.
- Do not load the full by-blob CSV into memory as one dataframe.
- Write only to a new timestamped data product directory.
- Preserve all input paths, row counts, byte sizes, and thresholds in the manifest.

## Acceptance Gates

Hard product gates:

```text
by_blob_rows == 1362316
by_frame_rows == 12024
FrameIndex contiguous 1:12024
BoundaryMetricValidRows == 636397
sum(frame BlobCount) == by_blob_rows
sidecar OverallStatus == PASS
sidecar BlockedForInterpretation == false
```

Schema gates:

```text
Every row has AreaTier
Every row has ReliabilityClass
Every row has ShapeClass
Every row has ShapeInvalidReason or ShapeClassReason
All thresholds used by classification are stored in JSON
```

Reliability gates:

```text
No small/tiny rows assigned boundary morphology classes
No roughness < 1 rows promoted to valid boundary classes
No circularity > 1.05 rows promoted to high-confidence circularity classes
Invalid boundary rows are retained and flagged, not silently dropped
```

Manifest gates:

```text
Input sidecar dir recorded
Input Level A dir recorded if used
V2 validation dir recorded as provenance
Git commit or git status limitation recorded
Command line args recorded
Output inventory recorded
No-rerun statement included
```
