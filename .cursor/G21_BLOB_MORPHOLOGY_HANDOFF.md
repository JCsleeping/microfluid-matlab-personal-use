# G21 Blob Morphology Handoff

Last updated: 2026-05-21

This handoff is for cross-agent coordination. It records the current state of
the G21 blob morphology pipeline, the frozen data products, the accepted scope,
and the next planned work. It is not a results interpretation document.

## Repository State

```text
repo: D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\.worktrees\residual-structure-metrics-20260424
branch: feat/residual-structure-metrics-20260424
latest pipeline commit before this handoff: 526db3a Add blob structure data figure bundle builder
tracked worktree state at handoff creation: clean before adding this handoff
latest regenerated data/figure bundle after validation hardening: g21_blob_structure_data_figure_bundle_20260521_203432
```

Known local scratch file moved out of the repo:

```text
C:\tmp\microfluid_scratch\20260521_git_cleanup\build_g21_level_b_geometry_package.py
```

That file was an old limited Level B interpretation-package draft. It is not
part of the accepted blob morphology pipeline and should not be reintroduced
without tests and a revised non-interpretive scope.

## Frozen G21 Product Chain

Use these directories as the current official G21 data chain:

```text
Level A postprocess:
C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418

Blob morphology data product:
C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418\g21_blob_morphology_data_product_20260520_124541

ShapeClassV1 formal package:
C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418\g21_blob_morphology_data_product_20260520_124541\g21_shape_class_v1_formal_package_20260521_105739

Blob structure statistics:
C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418\g21_blob_morphology_data_product_20260520_124541\g21_blob_structure_statistics_v1_20260521_113634

Pipeline acceptance:
C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418\g21_blob_morphology_data_product_20260520_124541\g21_blob_pipeline_acceptance_20260521_144653

Data and figure bundle:
C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418\g21_blob_morphology_data_product_20260520_124541\g21_blob_structure_data_figure_bundle_20260521_203432
```

## Current Pipeline Capabilities

The current worktree can reproduce the accepted G21 blob morphology data chain
from already completed pipeline outputs. It does not need to rerun the raw
segmentation pipeline for the current G21 products.

### Level A Postprocess And QC

Current code can:

```text
read completed G21 timeseries and blob-detail CSV outputs
stream large blob tables by chunk
compute SnNorm and Removal
compute SnMonotone
compute local-regression dissolution rates
generate 5/10/20 min rate-window sensitivity outputs
write Level A architecture, topology, blob-population, rate, and association tables
write Level A figures
run Level A interpretation-safety QC
recover experiment metadata into postprocess outputs
```

Current Level A restrictions:

```text
rate interpretation uses SnMonotone + local regression, not raw Sn differencing
Level A metrics are scalar/population projected morphology metrics
Level A does not provide corrected boundary masks, tracking, fractal dimensions, or 3D roughness
```

### Segmentation Context And Geometry Validation

Current code can:

```text
recover or validate frame_timeline mapping from raw TIF inventory
run segmentation context audit with explicit FrameTimelineCsv
select G21-specific geometry validation frames from Level A outputs
run selected-frame geometry sample validation
run V2 perimeter estimator QC on validation outputs
```

Current accepted G21 validation status:

```text
sample validation passed
V2 perimeter QC passed
500-frame sidecar smoke passed
full 12024-frame sidecar is not part of the frozen default product chain
```

### Geometry Sidecar Smoke

Current code can:

```text
run sidecar dry-run
run stratified 40-frame sidecar smoke
run MaxFrames=100 and MaxFrames=500 sidecar smoke
write geometry_by_blob, geometry_summary_by_frame, comparison, manifest, QC, masks, and labels for selected smoke runs
verify blob-count and total-area agreement against Level A for processed frames
```

Current sidecar scope:

```text
500-frame sidecar is accepted as backend/subset support
full sidecar is not required for the current blob morphology data/figure bundle
do not claim full-duration boundary trends from 500-frame smoke
```

### Blob Morphology Data Product

Current code can:

```text
assemble a morphology-ready by-blob table
standardize projected shape fields across source tables
compute AreaTier and interpretation tiers
compute ProjectedSphericity2D, Circularity2D_boundary, AxisAspectRatio, AspectRatio01, Solidity2D, ProjectedRegularity2D, ProjectedRoughness_boundary, and PtotalOverPouter where source columns allow
assign ShapeClassV0 and ShapeClassV1 labels
write ShapeClassV1 formal package tables, transition matrices, gate audits, schema, field dictionary, formula notes, and acceptance review
select representative blob candidates
render representative blob atlas panels from accepted mask/label sources
```

ShapeClassV1 can currently distinguish:

```text
compact_regular
near_compact_regular
moderately_elongated
elongated
moderately_concave
concave_lobed
branched_complex
compact_irregular
ambiguous_valid
low_area_compact_candidate_100_249
low_area_elongated_candidate_100_249
low_area_projected_shape_caution_100_249
count_only_lt100
boundary_invalid
```

### Blob Structure Statistics

Current code can:

```text
summarize ShapeClassV1 count fractions and projected-area fractions
summarize ShapeClassV1 by SnStage
summarize projected shape metrics by class and stage
summarize stage-wise transitions in count and projected area
write metric dictionary and representative atlas review files
write structure statistics manifest
```

These outputs are data summaries for user-side analysis. They are not final
scientific interpretation.

### Pipeline Acceptance And Release QC

Current code can:

```text
check expected frame coverage
check row-count reconciliation between morphology, ShapeClassV1, and structure statistics products
check metric range invariants
write frame-level computation QC
write warning inventory
write acceptance matrix
write run-status markdown
write release manifest with git commit and scope flags
```

Current accepted G21 decision:

```text
ACCEPT_BLOB_PIPELINE_WITH_DOCUMENTED_WARNINGS
```

The warnings are documented limitations, not blocking failures.

### Data And Figure Bundle

Current code can:

```text
package accepted G21 blob morphology tables into a user-facing data bundle
write data_inventory.csv and figure_inventory.csv
write field_dictionary.csv
write formula_notes.md
write qc_and_scope_notes.md
write bundle_manifest.json
render neutral figures as PNG and SVG
copy or summarize representative atlas metadata
```

Current bundle figures:

```text
Fig_ShapeClassV1_CountAreaFractions
Fig_ShapeClassV1_ByStage
Fig_AreaTier_Distribution
Fig_GeometryInterpretable_Fraction
Fig_ShapeParameter_Distributions
Fig_Sphericity_Roundness_Proxy_Map
Fig_RepresentativeBlobAtlas
```

### Not Currently Implemented As Accepted Outputs

Do not assume the current pipeline can produce accepted results for:

```text
full-duration Level B geometry interpretation
full-duration corrected boundary trend
tracking trajectories
split/merge lineage
single-blob lifetime
boundary fractal dimension
3D roughness
true fluid-fluid interfacial area
true Wadell roundness
transport dimensionless-number interpretation
mechanism or causal claims
```

## Current Accepted Status

```text
G21_BLOB_MORPHOLOGY_PIPELINE_COMPLETE
FRAME_COVERAGE_ACCEPTED
SHAPE_CLASS_V1_ACCEPTED
DATA_FIGURE_BUNDLE_GENERATED
PIPELINE_ACCEPTED_WITH_DOCUMENTED_WARNINGS
```

Current acceptance numbers:

```text
frames = 12024 / 12024
missing frames = 0
unexpected frames = 0
row mismatch frames = 0
morphology rows = 1,362,316
ShapeClassV1 rows = 1,362,316
geometry-interpretable rows = 636,397
decision = ACCEPT_BLOB_PIPELINE_WITH_DOCUMENTED_WARNINGS
```

Current data/figure bundle numbers:

```text
shape_class_v1_rows = 1,362,316
frames = 12,024
tables = 6
figure files = 14
acceptance = ACCEPT_BLOB_PIPELINE_WITH_DOCUMENTED_WARNINGS
scope.writes_scientific_interpretation = false
scope.full_level_b_interpretation = false
```

## Important Scope Boundary

The current goal is to prepare data and figures for the user to analyze.
Agents should not write scientific interpretation unless the user explicitly
requests it.

Allowed current work:

```text
data tables
summary tables
neutral figures
figure inventory
data inventory
field dictionary
formula notes
QC and provenance notes
figure polish
bundle regeneration
```

Do not do by default:

```text
mechanism interpretation
claim register
results paragraphs
causal language
full Level B interpretation
tracking
split/merge lineage
fractal dimension
3D roughness
true fluid-fluid interfacial area
```

Terminology rules:

```text
ShapeClassV1 = projected 2D morphology class.
ProjectedSphericity2D is not 3D sphericity.
Circularity2D_boundary is not Wadell roundness.
ProjectedRoughness_boundary is a 2D exterior-boundary proxy.
P_outer_boundary is not true fluid-fluid interfacial area.
Area < 250 px is not a default boundary morphology interpretation tier.
```

## Code Added In Latest Phase

Data/figure bundle builder:

```text
visualization/build_blob_structure_data_figure_bundle.py
tests/test_blob_structure_data_figure_bundle.py
docs/plans/2026-05-21-g21-blob-structure-data-figure-bundle-design.md
docs/plans/2026-05-21-g21-blob-structure-data-figure-bundle.md
```

The builder creates:

```text
README_data_figure_bundle.md
data_inventory.csv
figure_inventory.csv
field_dictionary.csv
formula_notes.md
qc_and_scope_notes.md
bundle_manifest.json
tables/
figures/
```

Verification already run for latest builder:

```text
python -m unittest tests.test_blob_structure_data_figure_bundle -v
python -m unittest tests.test_blob_structure_data_figure_bundle tests.test_blob_structure_statistics tests.test_blob_structure_figure_package -v
python -m unittest tests.test_blob_pipeline_acceptance_review tests.test_blob_structure_data_figure_bundle tests.test_blob_structure_statistics tests.test_blob_structure_figure_package tests.test_shape_class_v1_formal_package -v
python -m py_compile visualization\build_blob_structure_data_figure_bundle.py
python visualization\build_blob_structure_data_figure_bundle.py --help
```

## Regenerate Or Refresh The Current Data/Figure Bundle

From the repo root:

```powershell
python visualization\build_blob_structure_data_figure_bundle.py `
  --postprocess-dir "C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418" `
  --morphology-dir "C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418\g21_blob_morphology_data_product_20260520_124541" `
  --shape-class-v1-dir "C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418\g21_blob_morphology_data_product_20260520_124541\g21_shape_class_v1_formal_package_20260521_105739" `
  --structure-statistics-dir "C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418\g21_blob_morphology_data_product_20260520_124541\g21_blob_structure_statistics_v1_20260521_113634" `
  --acceptance-dir "C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418\g21_blob_morphology_data_product_20260520_124541\g21_blob_pipeline_acceptance_20260521_144653" `
  --repo-root "D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\.worktrees\residual-structure-metrics-20260424"
```

This command creates a new timestamped bundle directory by default. To refresh
the exact frozen bundle path, add:

```powershell
  --output-dir "C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418\g21_blob_morphology_data_product_20260520_124541\g21_blob_structure_data_figure_bundle_20260521_203432" `
  --overwrite
```

For cross-agent reproducibility, prefer creating a new timestamped bundle and
then updating this handoff if it becomes the official frozen version.

## Next Short-Term Work

The next recommended work is figure and table polish only.

Possible tasks:

```text
1. Review figures in g21_blob_structure_data_figure_bundle_20260521_203432.
2. Improve layout, class order, colors, labels, and legend placement.
3. Add Chinese/English label variants if needed.
4. Keep all captions neutral and non-interpretive.
5. Regenerate the bundle and update inventories.
```

Priority figures to inspect:

```text
Fig_ShapeClassV1_CountAreaFractions
Fig_ShapeClassV1_ByStage
Fig_AreaTier_Distribution
Fig_GeometryInterpretable_Fraction
Fig_ShapeParameter_Distributions
Fig_Sphericity_Roundness_Proxy_Map
Fig_RepresentativeBlobAtlas
```

## Medium-Term Plan

Make the current workflow experiment-agnostic:

```text
1. Replace G21-specific paths with config files.
2. Apply the same package chain to G18/G20/G21.
3. Emit identical data/figure bundle schemas for each experiment.
4. Maintain one release registry per experiment.
```

Engineering cleanup to keep on the medium-term list:

```text
build_blob_morphology_data_product.py reads large CSVs in chunks, but some
quantile and frame-summary steps still accumulate arrays before writing final
tables. This is acceptable for the current G21 product, but future G18/G20/G21
batch runs should move those summaries to bounded-memory or two-pass streaming
aggregation before scaling to larger experiments.
```

Target release registry fields:

```text
ExperimentID
LevelAPostprocessDir
MorphologyProductDir
ShapeClassV1Dir
StructureStatisticsDir
AcceptanceDir
DataFigureBundleDir
GitCommit
DecisionLabel
FrameCoverage
RowCounts
Warnings
AllowedUse
ForbiddenUse
```

## Long-Term Plan

Only after the data products are consistent across experiments, prepare
cross-experiment data tables and figures:

```text
G18 vs G20 vs G21 shape-class count fraction
G18 vs G20 vs G21 shape-class projected-area fraction
AreaTier distributions across experiments
geometry-interpretable fraction across experiments
stage-wise projected morphology summaries across experiments
```

Still out of scope unless separately approved:

```text
full sidecar reruns
tracking pilot
split/merge lineage
fractal method validation
3D roughness
true fluid-fluid interfacial area
```

## Notes For Future Agents

1. Do not treat `g21_blob_structure_data_figure_bundle_*` as an interpretation package.
2. Do not write results conclusions unless the user explicitly asks.
3. Do not silently switch to older G21 output directories.
4. Do not commit generated `C:\tmp` data products.
5. Do not reintroduce the old Level B interpretation draft without a new plan and tests.
6. Keep scope language strict: this is projected 2D blob morphology data and figures.
