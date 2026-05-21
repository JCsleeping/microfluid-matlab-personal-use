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
C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418\g21_blob_morphology_data_product_20260520_124541\g21_blob_structure_data_figure_bundle_20260521_192409
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
python -m py_compile visualization\build_blob_structure_data_figure_bundle.py
python visualization\build_blob_structure_data_figure_bundle.py --help
```

## Regenerate The Current Data/Figure Bundle

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

## Next Short-Term Work

The next recommended work is figure and table polish only.

Possible tasks:

```text
1. Review figures in g21_blob_structure_data_figure_bundle_20260521_192409.
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
