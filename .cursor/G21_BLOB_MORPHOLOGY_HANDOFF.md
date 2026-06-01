# G21 Blob Morphology Handoff

Last updated: 2026-06-01

This handoff is for cross-agent coordination. It records the current state of
the G21 blob morphology pipeline, the frozen data products, the accepted scope,
and the next planned work. It is not a results interpretation document.

## Repository State

```text
current main-route worktree: D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\.worktrees\Matlab 2 Stage Analsysis
branch: feat/residual-structure-metrics-20260424
latest reusable-pipeline commits:
  f220178 Stabilize per-blob geometry core-only mode
  247c57c Add Linear RGB input normalization toggle
  5673377 Add reusable ROI hole geometry mode
tracked worktree state at 2026-06-01 update: one local config_pipeline.m edit exists
local config edit observed: config.physical.channel_width_um 400 -> 10000
latest regenerated data/figure bundle after validation hardening: g21_blob_structure_data_figure_bundle_20260521_203432
```

The worktree directory was renamed on 2026-06-01 to make its role explicit.
Use this path as the current active route for MATLAB two-stage analysis work:

```text
D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\.worktrees\Matlab 2 Stage Analsysis
```

The spelling `Analsysis` is intentional because it matches the current
filesystem path. Do not silently switch agents back to the old
`residual-structure-metrics-20260424` path.

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

The current worktree has two roles:

```text
1. It can reproduce the accepted G21 blob morphology data chain from already
   completed G21 pipeline outputs.
2. It is now also the reusable raw-TIF pipeline route for new experiments that
   need full-frame per-blob detail output.
```

It does not need to rerun the raw segmentation pipeline for the frozen G21
products. For new experiments, use the two-stage geometry route below.

### Reusable Two-Stage Geometry Route

Current code supports these reusable geometry modes:

```text
Phase 1:
  geometry.mode = 'core_only'
  geometry.schema_version = 'geometry_v2_core_only'
  purpose = stable full-frame per-blob scalar export
  hole semantics = Euler-based only, no domain-aware hole classification

Phase 2:
  geometry.mode = 'roi'
  geometry.schema_version = 'geometry_v3_roi_holes'
  purpose = ROI-local domain-aware hole classification
  hole semantics = ROI imfill/bwconncomp with flow/solid domain labels

Debug/regression only:
  geometry.mode = 'legacy_fullframe'
  purpose = old per-blob full-frame hole path for small tests
```

Do not switch Phase 1 and Phase 2 inside the same output directory. The schema
manifest under `status/geometry_schema.mat` is intended to fail fast on
incompatible resume or mixed-schema writes.

Default run settings for full per-blob output:

```text
config.output.save_blob_detail = true
config.parallel.enabled = false
config.visualization.show_figures = false
config.visualization.save_figures = false
```

Input encoding support:

```text
config.input.is_linear_rgb = false  % default, existing sRGB behavior
config.input.is_linear_rgb = true   % convert Linear RGB to sRGB before segmentation
```

Linear RGB support is a forward-looking input normalization option. Existing
outputs are not migrated.

### G18 Phase 1/2 Validation Run

Recent G18 raw-pipeline runs demonstrate that the two-stage route is usable
outside the frozen G21 product chain.

```text
Experiment path:
G:\Microfluid\18 1-BO 4UL 5% TWEEM 80 4UL WATER DISPLACE\01 Tween 80

Phase 1 completed output:
G:\Microfluid\18 1-BO 4UL 5% TWEEM 80 4UL WATER DISPLACE\01 Tween 80\output_core_only_20260528_104228

Phase 2 completed output:
G:\Microfluid\18 1-BO 4UL 5% TWEEM 80 4UL WATER DISPLACE\01 Tween 80\output_roi_phase2_20260528_140506
```

Phase 2 output check:

```text
pipeline completed = true
frames = 5852 / 5852
blob_detail_all_frames.csv rows = 1,322,608
timeseries NumBlobs sum = 1,322,608
blob detail chunks = 82
chunk coverage = 1-5852 with no gaps
GeometryMode = roi for all rows
GeometrySchemaVersion = geometry_v3_roi_holes for all rows
HoleClassificationComputed = true for all rows
HoleCountSource = roi_domain_aware for all rows
RoiFallbackUsed = false for all rows
```

Phase 2 caution:

```text
HoleCount total = 111,956
EulerHoleCount total = 123,985
rows where EulerHoleCount exceeds ROI HoleCount = 11,875
```

This is not a pipeline-completion failure, but hole statistics should receive a
small Phase 2.1 QC before any scientific interpretation of hole counts. The
likely issue is a definition/connectivity difference between Euler topology and
ROI imfill/domain-aware component classification.

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

Full-frame per-blob detail export is now implemented for new raw pipeline runs
through `core_only` and `roi`. That is still a data product, not an accepted
scientific interpretation layer.

## Current Accepted Status

```text
G21_BLOB_MORPHOLOGY_PIPELINE_COMPLETE
FRAME_COVERAGE_ACCEPTED
SHAPE_CLASS_V1_ACCEPTED
DATA_FIGURE_BUNDLE_GENERATED
PIPELINE_ACCEPTED_WITH_DOCUMENTED_WARNINGS
MATLAB_TWO_STAGE_ANALYSIS_WORKTREE_REGISTERED
G18_PHASE1_CORE_ONLY_COMPLETED
G18_PHASE2_ROI_COMPLETED
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
  --repo-root "D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\.worktrees\Matlab 2 Stage Analsysis"
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

The next recommended work is to keep the two routes separate:

```text
G21 frozen product route:
  figure and table polish only

Reusable raw-pipeline route:
  Phase 2.1 hole-count QC before interpreting hole statistics
  then build neutral data/figure bundles from Phase 2 outputs
```

Possible tasks:

```text
1. Review figures in g21_blob_structure_data_figure_bundle_20260521_203432.
2. Improve layout, class order, colors, labels, and legend placement.
3. Add Chinese/English label variants if needed.
4. Keep all captions neutral and non-interpretive.
5. Regenerate the G21 bundle and update inventories if the frozen bundle changes.
6. For G18 Phase 2, run a focused HoleCount vs EulerHoleCount QC.
7. Build neutral G18 blob-structure tables and figures only after the QC passes.
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
5. Record geometry mode and schema version in every release registry entry.
6. Keep Phase 1 and Phase 2 outputs as separate releases unless an explicit
   migration/merge tool is written.
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
7. Use `D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\.worktrees\Matlab 2 Stage Analsysis` as the active two-stage MATLAB analysis worktree.
8. Do not mix `geometry_v2_core_only` and `geometry_v3_roi_holes` rows without explicit schema labeling.
9. Treat the current `config_pipeline.m` local change as run-specific until the user approves committing it.
