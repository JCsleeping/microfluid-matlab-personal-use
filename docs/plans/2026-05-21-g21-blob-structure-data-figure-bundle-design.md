# G21 Blob Structure Data/Figure Bundle Design

## Goal

Create a neutral, reproducible G21 blob-structure data and figure bundle from the accepted morphology data product, ShapeClassV1 package, structure statistics package, and pipeline acceptance package.

The bundle is a data-delivery artifact. It does not write scientific conclusions, mechanism claims, causal language, tracking interpretation, fractal interpretation, or 3D roughness interpretation.

## Inputs

Use the frozen G21 products:

```text
postprocess_residual_structure_20260518_231418
g21_blob_morphology_data_product_20260520_124541
g21_shape_class_v1_formal_package_20260521_105739
g21_blob_structure_statistics_v1_20260521_113634
g21_blob_pipeline_acceptance_20260521_144653
```

The builder should accept these paths as arguments so the same tool can later be reused for G18/G20 or refreshed G21 products.

## Outputs

Write a new directory named:

```text
g21_blob_structure_data_figure_bundle_<timestamp>/
```

Required top-level files:

```text
README_data_figure_bundle.md
data_inventory.csv
figure_inventory.csv
field_dictionary.csv
formula_notes.md
qc_and_scope_notes.md
bundle_manifest.json
```

Required tables:

```text
tables/shape_class_v1_count_area_summary.csv
tables/shape_class_v1_by_stage_summary.csv
tables/area_tier_summary.csv
tables/geometry_interpretable_fraction_by_stage.csv
tables/frame_level_blob_structure_summary.csv
tables/representative_blob_table.csv
```

Required figures:

```text
figures/Fig_ShapeClassV1_CountAreaFractions.png
figures/Fig_ShapeClassV1_CountAreaFractions.svg
figures/Fig_ShapeClassV1_ByStage.png
figures/Fig_ShapeClassV1_ByStage.svg
figures/Fig_AreaTier_Distribution.png
figures/Fig_AreaTier_Distribution.svg
figures/Fig_GeometryInterpretable_Fraction.png
figures/Fig_GeometryInterpretable_Fraction.svg
figures/Fig_ShapeParameter_Distributions.png
figures/Fig_ShapeParameter_Distributions.svg
figures/Fig_Sphericity_Roundness_Proxy_Map.png
figures/Fig_Sphericity_Roundness_Proxy_Map.svg
figures/Fig_RepresentativeBlobAtlas.png
figures/Fig_RepresentativeBlobAtlas.svg
```

## Data Flow

1. Read ShapeClassV1 by-blob rows from `blob_shape_class_v1_by_blob.csv`.
2. Read ShapeClassV1, structure statistics, and pipeline acceptance manifests for provenance and decision labels.
3. Regenerate bundle-facing summary tables from the ShapeClassV1 rows.
4. Write normalized summary tables into `tables/`.
5. Render neutral figures into `figures/`.
6. Write inventories and manifest describing source paths, output paths, row counts, git commit, and scope limits.

The builder should not duplicate the full structure-statistics package. It should use the accepted ShapeClassV1 rows as the table source of truth, while carrying the upstream structure-statistics and acceptance manifests into the bundle manifest.

## Scope Rules

The bundle may describe:

```text
2D projected morphology descriptors
ShapeClassV1 count and projected-area fractions
AreaTier counts and projected-area fractions
geometry-interpretable / low-area / count-only row fractions
representative blob metadata and panels
pipeline QC and provenance
```

The bundle must not describe:

```text
mechanisms
causal interpretation
full Level B interpretation
full-duration boundary trend
tracking, split/merge, or blob lifetime
boundary fractal dimension
3D roughness
true fluid-fluid interfacial area
true Wadell roundness
```

## Formula Notes

`formula_notes.md` must include the key projected 2D formulas and terminology boundaries:

```text
ProjectedSphericity2D
Circularity2D_boundary
AxisAspectRatio
AspectRatio01
Solidity2D
ProjectedRegularity2D
ProjectedRoughness_boundary
PtotalOverPouter
ShapeClassV1
AreaTier
BoundaryMetricValid
```

It must state that the metrics are 2D projected morphology descriptors, not 3D roughness, not true fluid-fluid interfacial area, and not Wadell roundness.

## Neutral Wording

Figure titles, README text, and notes should use neutral wording such as:

```text
Distribution of ShapeClassV1 count and projected-area fractions.
```

They must avoid interpretation wording such as:

```text
proves
indicates
suggests a mechanism
caused
drives
```

## Acceptance Criteria

1. All required files exist.
2. `data_inventory.csv` references every table and required note file.
3. `figure_inventory.csv` references every rendered figure and every path exists.
4. `field_dictionary.csv` includes the core shape fields and source/scope fields.
5. `formula_notes.md` includes formula definitions and explicit exclusions.
6. `qc_and_scope_notes.md` records the acceptance decision, frame coverage, warning list, and exclusions.
7. Table row counts are internally consistent with the input data.
8. README and notes contain no mechanism or causal claims.
9. `bundle_manifest.json` records source directories, git commit, row counts, generated files, and scope.
