# G21 Blob Pipeline Acceptance Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Harden the G21 blob pipeline acceptance review so row reconciliation, frame coverage, numeric completeness, metric invariants, and provenance become strict reusable gates.

**Architecture:** Extend `visualization/build_blob_pipeline_acceptance_review.py` with threshold configuration, expected-frame coverage, required numeric completeness checks, and deterministic repo provenance. Preserve the existing output files and decision labels so downstream workflows continue to work.

**Tech Stack:** Python, pandas, NumPy, unittest, existing full-duration G21 morphology/ShapeClassV1 outputs as read-only generated inputs.

---

## Task 1: Row-Difference Thresholds

**Files:**

- Modify: `visualization/build_blob_pipeline_acceptance_review.py`
- Modify: `tests/test_blob_pipeline_acceptance_review.py`

**Step 1: Write failing tests**

Add tests for:

```text
12-row Level A vs morphology difference => WARN
large Level A vs morphology difference beyond row and fraction thresholds => FAIL
```

Run:

```powershell
python -m unittest tests.test_blob_pipeline_acceptance_review -v
```

Expected: fail because thresholds are not implemented.

**Step 2: Implement threshold config**

Add fields:

```python
row_diff_warn_max_rows: int = 20
row_diff_warn_max_fraction: float = 0.00005
```

Apply:

```text
PASS if diff == 0
WARN if abs(diff) <= max_rows OR abs(diff)/level_a_rows <= max_fraction
FAIL otherwise
```

**Step 3: Verify**

Run:

```powershell
python -m unittest tests.test_blob_pipeline_acceptance_review -v
```

Expected: pass.

## Task 2: Expected Frame Coverage

**Files:**

- Modify: `visualization/build_blob_pipeline_acceptance_review.py`
- Modify: `tests/test_blob_pipeline_acceptance_review.py`

**Step 1: Write failing tests**

Add tests for:

```text
missing final FrameIndex produces FAIL
missing interior FrameIndex produces FAIL
unexpected FrameIndex beyond expected range produces FAIL
```

Run:

```powershell
python -m unittest tests.test_blob_pipeline_acceptance_review -v
```

Expected: fail because current logic uses observed max frame.

**Step 2: Implement expected frame logic**

Add:

```python
expected_frames: int | None
```

Frame QC should use:

```text
1:expected_frames
```

If not supplied, infer from manifests where possible. If inference fails, mark expected-frame provenance as WARN.

**Step 3: Verify**

Run targeted test.

## Task 3: Numeric Completeness Gates

**Files:**

- Modify: `visualization/build_blob_pipeline_acceptance_review.py`
- Modify: `tests/test_blob_pipeline_acceptance_review.py`

**Step 1: Write failing tests**

Add tests for:

```text
Area_px NaN => FAIL
P_outer_boundary NaN in BoundaryMetricValid row => FAIL
```

**Step 2: Implement completeness audit**

Add metric audit rows for:

```text
required numeric all-row columns are present and finite
boundary-valid required boundary columns are present and finite
```

**Step 3: Verify**

Run targeted test.

## Task 4: Provenance and Manifest Hardening

**Files:**

- Modify: `visualization/build_blob_pipeline_acceptance_review.py`
- Modify: `tests/test_blob_pipeline_acceptance_review.py`

**Step 1: Write failing tests**

Assert manifest records:

```text
repo_root
expected_frames
row_diff_warn_max_rows
row_diff_warn_max_fraction
blocking_issues
warning_issues
```

**Step 2: Implement CLI / manifest fields**

Add CLI:

```powershell
--expected-frames
--row-diff-warn-max-rows
--row-diff-warn-max-fraction
--repo-root
```

Make `_git_commit` accept `repo_root`.

**Step 3: Verify**

Run targeted test and `python -m py_compile`.

## Task 5: Regenerate G21 Acceptance Package

**Files:** generated under `C:\tmp`, not committed.

Run:

```powershell
python visualization\build_blob_pipeline_acceptance_review.py `
  --output-root "C:\tmp\g21_output_20260515_190825" `
  --postprocess-dir "C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418" `
  --morphology-dir "C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418\g21_blob_morphology_data_product_20260520_124541" `
  --shape-class-v1-dir "C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418\g21_blob_morphology_data_product_20260520_124541\g21_shape_class_v1_formal_package_20260521_105739" `
  --structure-statistics-dir "C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418\g21_blob_morphology_data_product_20260520_124541\g21_blob_structure_statistics_v1_20260521_113634" `
  --expected-frames 12024
```

Expected:

```text
Decision = ACCEPT_BLOB_PIPELINE_WITH_DOCUMENTED_WARNINGS
fail_gates = 0
missing_frames = 0
row_mismatch_frames = 0
metric_failures = 0
```

Inspect new run-status outputs:

```text
g21_blob_pipeline_run_status.md
g21_blob_pipeline_acceptance_matrix.csv
g21_blob_frame_coverage_summary.csv
g21_blob_computation_warning_inventory.csv
```

Expected run-status content:

```text
Expected frames = 12024
PASS frames = 12024
Missing frames = 0
Unexpected frames = 0
Row-mismatch frames = 0
Blocking issues = none
Warning inventory contains only documented row reconciliation and non-boundary-valid diagnostic warnings
```

## Task 6: Final Verification and Commit

Run:

```powershell
python -m py_compile visualization\build_blob_pipeline_acceptance_review.py
python -m unittest tests.test_blob_pipeline_acceptance_review -v
python -m unittest discover -s tests -p "test_*.py" -v
git diff --check
```

Commit only:

```text
docs/plans/2026-05-21-g21-blob-pipeline-acceptance-hardening-design.md
docs/plans/2026-05-21-g21-blob-pipeline-acceptance-hardening.md
visualization/build_blob_pipeline_acceptance_review.py
tests/test_blob_pipeline_acceptance_review.py
```

Do not stage:

```text
visualization/build_g21_level_b_geometry_package.py
```

Commit message:

```text
Harden blob pipeline acceptance gates
```
