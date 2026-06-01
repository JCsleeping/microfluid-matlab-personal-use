# G21 Blob Pipeline Acceptance Hardening Design

## Decision

Harden `build_blob_pipeline_acceptance_review.py` into a strict acceptance gate for the full-duration G21 blob morphology data product.

The current G21 acceptance package is usable, but two documented warnings and several soft assumptions need explicit thresholds before the tool is reused for other experiments. The hardened gate should separate:

```text
PASS: internally closed and no warnings
WARN: accepted with bounded, documented differences
FAIL: blocked because coverage, row conservation, metric completeness, or provenance is unsafe
```

## Scope

Allowed:

- Full-duration 2D blob pipeline QC.
- Row reconciliation across Level A, morphology, ShapeClassV0, ShapeClassV1, and structure statistics.
- Frame coverage over a fixed expected frame range.
- Numeric completeness checks for required shape metrics.
- Metric invariant checks for projected 2D shape and corrected boundary metrics.
- Provenance recording for repository commit and threshold configuration.

Not allowed:

- Re-running sidecar extraction.
- Tracking or split/merge lineage.
- Boundary fractal dimension.
- 3D roughness.
- True Wadell roundness.
- True fluid-fluid interfacial area.

## Acceptance Rules

### Row Reconciliation

`LevelARows - MorphologyRows` uses a bounded warning policy:

```text
PASS = diff == 0
WARN = abs(diff) <= 20 rows OR abs(diff) / LevelARows <= 0.005%
FAIL = otherwise
```

For G21:

```text
Level A rows = 1,362,328
Morphology rows = 1,362,316
Diff = 12 rows
Diff fraction = 0.000881%
Decision = WARN
```

Downstream products must remain strict:

```text
MorphologyRows == ShapeClassV1Rows
ShapeClassV1Rows == StructureStatisticsRows
```

Any mismatch in downstream products is a FAIL.

### Frame Coverage

Frame coverage must use an expected frame count, not the observed maximum frame. For G21:

```text
ExpectedFrames = 12024
RequiredFrameIndex = 1:12024
```

Missing final frames, missing interior frames, and frames outside the expected range are FAIL. If `--expected-frames` is not supplied, the tool may infer it from manifests. If inference fails, the result is WARN because a complete coverage claim cannot be made.

### Numeric Completeness

Required metrics must be numeric and non-missing in the rows where they are required.

All rows require:

```text
Area_px
MajorAxisLength_px
MinorAxisLength_px
AxisAspectRatio
AspectRatio01
Solidity2D
ProjectedSphericity2D
Circularity2D_boundary
ProjectedRoughness_boundary
PtotalOverPouter
BoundaryMetricValid
```

Boundary-valid rows additionally require:

```text
P_outer_boundary
Pc_outer_boundary
P_total_boundary
```

Any missing or non-numeric required value is a FAIL.

### Metric Invariants

The existing projected 2D invariant checks remain:

```text
Area_px > 0
MajorAxisLength_px >= MinorAxisLength_px
AxisAspectRatio >= 1
0 < AspectRatio01 <= 1
0 <= Solidity2D <= 1
0 <= ProjectedSphericity2D <= 1.05 for boundary-valid rows
P_outer_boundary > 0 for boundary-valid rows
Pc_outer_boundary > 0 for boundary-valid rows
P_total_boundary >= P_outer_boundary for boundary-valid rows
ProjectedRoughness_boundary >= 1 for boundary-valid rows
Circularity2D_boundary <= 1.05 for boundary-valid rows
PtotalOverPouter >= 1 for boundary-valid rows
```

`ProjectedSphericity2D` outside boundary-valid rows remains a diagnostic WARN because low-area, count-only rows may show pixel-scale artifacts. Boundary interpretation must still be restricted to `BoundaryMetricValid` / geometry-interpretable rows.

### Provenance

The manifest must record:

```text
RepoRoot
GitCommit
ExpectedFrames
RowDiffWarnMaxRows
RowDiffWarnMaxFraction
BlockingIssues
WarningIssues
```

The script should use `--repo-root` when provided. Otherwise it should resolve the repository root from the script location rather than relying only on the caller's current working directory.

## Required Outputs

The output package remains:

```text
g21_blob_pipeline_acceptance_review.md
g21_blob_pipeline_run_status.md
g21_blob_pipeline_acceptance_matrix.csv
g21_blob_frame_coverage_summary.csv
g21_blob_computation_warning_inventory.csv
g21_blob_computation_qc_summary.csv
g21_blob_computation_by_frame_qc.csv
g21_blob_metric_range_audit.csv
g21_blob_row_reconciliation.csv
g21_blob_pipeline_release_manifest.json
```

The review markdown must explain each warning in plain terms and state whether any issue blocks blob-structure statistics.

The run-status markdown and machine-readable matrix files summarize pipeline execution separately from scientific interpretation:

```text
g21_blob_pipeline_run_status.md
  Human-readable run status: coverage, row counts, blocking issues, warning issues, and scope.

g21_blob_pipeline_acceptance_matrix.csv
  One table combining QC summary gates, row reconciliation checks, and metric invariant checks.

g21_blob_frame_coverage_summary.csv
  Compact frame coverage counts: expected, pass, missing, unexpected, mismatch, first, and last frame.

g21_blob_computation_warning_inventory.csv
  All WARN/FAIL checks extracted into a short inventory for review.
```

## Done Criteria

- Current G21 still returns `ACCEPT_BLOB_PIPELINE_WITH_DOCUMENTED_WARNINGS`.
- Missing final frame produces `BLOCKED_BLOB_PIPELINE_QC`.
- Unexpected frame beyond the expected range produces `BLOCKED_BLOB_PIPELINE_QC`.
- Large Level A to morphology row mismatch produces `BLOCKED_BLOB_PIPELINE_QC`.
- Missing required numeric metrics produce `BLOCKED_BLOB_PIPELINE_QC`.
- Boundary-valid metric artifacts produce `BLOCKED_BLOB_PIPELINE_QC`.
- Non-boundary-valid low-area `ProjectedSphericity2D` artifacts remain documented WARN.
- Full Python unittest suite passes.
