# G21 Blob Morphology Data Product Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a full-duration, sidecar-native G21 2D blob morphology data product with reliable morphology metrics, shape classes, representative blob candidates, manifest, and QC outputs.

**Architecture:** Implement a two-pass streaming Python builder over the passed full sidecar `geometry_by_blob.csv`, preserving the sidecar as immutable input. The first pass computes denominators, thresholds, and frame reducers; the second pass writes normalized by-blob rows, shape classes, reliability summaries, and bounded candidate lists. Atlas rendering is a follow-up task after table QC passes.

**Tech Stack:** Python, pandas chunked CSV reads, NumPy reducers, matplotlib/scikit-image only for the later atlas renderer, existing MATLAB sidecar outputs as read-only inputs.

---

## Context

Primary repo:

```text
D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\.worktrees\residual-structure-metrics-20260424
```

Primary sidecar input:

```text
C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418\geometry_sidecar_full_20260519_172548
```

Accepted sidecar QC:

```text
OverallStatus = PASS
ProcessedFrames = 12024
GeometryBlobRows = 1362316
BoundaryMetricValidRows = 636397
BlobCountPassFrames = 12024
TotalAreaPassFrames = 12024
MaxConsecutiveMismatchFrames = 0
EmptyGeometryFrames = 0
BlockedForInterpretation = false
```

Design reference:

```text
docs/plans/2026-05-19-g21-blob-morphology-data-product-design.md
```

## Task 1: Add Sidecar-Native Schema Helpers

**Files:**

- Create: `visualization/build_blob_morphology_data_product.py`
- Test: `tests/test_blob_morphology_data_product.py`

**Step 1: Write failing tests for schema normalization**

Add tests that build a small sidecar-like dataframe with source columns:

```text
FrameIndex
RealTime_s
BlobID_sidecar
Area_px
MajorAxisLength_px
MinorAxisLength_px
ConvexArea_px
Solidity_geometry
Eccentricity
Extent
P_outer_boundary
Pc_outer_boundary
P_total_boundary
ProjectedRoughness_boundary
Circularity2D_boundary
AreaTier
BoundaryAvailable
BoundaryMetricValid
RoughnessLessThanOne
CircularityGreaterThan1p05
TouchesImageBorder
GeometryQCFlag
```

Expected normalized columns include:

```text
BlobID
EquivDiameter_px
EquivRadius_px
ProjectedSphericity2D
AspectRatio01
AxisAspectRatio
Solidity2D
ProjectedConvexityPerimeter
PtotalOverPouter
ReliabilityClass
ShapeClass
ShapeClassReason
ShapeValid
ShapeInvalidReason
```

**Step 2: Run the failing test**

Run:

```powershell
python -m unittest tests.test_blob_morphology_data_product -v
```

Expected: failure because the module does not exist.

**Step 3: Implement minimal helper functions**

Implement:

```python
def normalize_sidecar_columns(df: pd.DataFrame) -> pd.DataFrame:
    ...

def add_projected_shape_metrics(df: pd.DataFrame) -> pd.DataFrame:
    ...
```

Use:

```text
ProjectedSphericity2D = 2 * sqrt(pi * Area_px) / P_outer_boundary
Circularity2D_boundary = existing source field
AspectRatio01 = MinorAxisLength_px / MajorAxisLength_px
AxisAspectRatio = MajorAxisLength_px / MinorAxisLength_px
Solidity2D = Area_px / ConvexArea_px or source Solidity_geometry
ProjectedConvexityPerimeter = Pc_outer_boundary / P_outer_boundary
PtotalOverPouter = P_total_boundary / P_outer_boundary
```

Guard divisions by zero with `NaN`, not zero.

**Step 4: Verify tests pass**

Run:

```powershell
python -m unittest tests.test_blob_morphology_data_product -v
python -m py_compile visualization\build_blob_morphology_data_product.py
```

Expected: pass.

## Task 2: Add Reliability and Shape-Class Assignment

**Files:**

- Modify: `visualization/build_blob_morphology_data_product.py`
- Test: `tests/test_blob_morphology_data_product.py`

**Step 1: Write failing reliability tests**

Test these rules:

```text
Area_px < 250 -> ReliabilityClass=count_only_small, ShapeClass=small_unclassified
BoundaryMetricValid=false -> ShapeClass=boundary_invalid
Area_px >= 250 and BoundaryMetricValid=true -> geometry_valid
Area_px >= 500 and BoundaryMetricValid=true -> high_confidence
tiny/small rows never receive compact/elongated/concave/boundary classes
RoughnessLessThanOne=true cannot be shape-valid for boundary classes
CircularityGreaterThan1p05=true cannot be high-confidence circularity-valid
```

**Step 2: Write failing threshold tests**

Create a valid reference population and assert:

```text
thresholds are computed only from BoundaryMetricValid=true and Area_px>=250
thresholds contain q25/q50/q75/q90 for ProjectedSphericity2D, AspectRatio01, AxisAspectRatio, Solidity2D, ProjectedRoughness_boundary, PtotalOverPouter
threshold computation is deterministic
```

**Step 3: Implement**

Implement:

```python
def compute_shape_thresholds(valid_rows: pd.DataFrame) -> dict:
    ...

def assign_reliability_class(df: pd.DataFrame) -> pd.Series:
    ...

def assign_shape_class(df: pd.DataFrame, thresholds: dict) -> pd.DataFrame:
    ...
```

Class order:

```text
small_unclassified
boundary_invalid
medium_caution
compact_round
elongated
concave_lobed
branched_complex
compact_irregular
ambiguous_valid
```

**Step 4: Verify**

Run:

```powershell
python -m unittest tests.test_blob_morphology_data_product -v
```

Expected: pass.

## Task 3: Implement Sidecar Discovery and QC Gating

**Files:**

- Modify: `visualization/build_blob_morphology_data_product.py`
- Test: `tests/test_blob_morphology_data_product.py`

**Step 1: Write failing tests**

Use temporary directories to test:

```text
missing geometry_by_blob.csv -> hard fail
missing geometry_summary_by_frame.csv -> hard fail
OverallStatus != PASS -> hard fail
ProcessedFrames mismatch -> hard fail
GeometryBlobRows mismatch -> hard fail
BlockedForInterpretation=true -> hard fail
output dir exists and non-empty without --overwrite -> hard fail
```

**Step 2: Implement discovery**

Implement:

```python
def discover_sidecar(sidecar_dir: Path) -> SidecarInputs:
    ...

def load_sidecar_qc(qc_csv: Path) -> dict:
    ...

def gate_sidecar_qc(qc: dict, expected_frames: int | None, expected_rows: int | None) -> None:
    ...
```

**Step 3: Verify**

Run:

```powershell
python -m unittest tests.test_blob_morphology_data_product -v
```

Expected: pass.

## Task 4: Implement Two-Pass Streaming Builder

**Files:**

- Modify: `visualization/build_blob_morphology_data_product.py`
- Test: `tests/test_blob_morphology_data_product.py`

**Step 1: Write tests for chunk boundaries**

Create a CSV fixture where one `FrameIndex` is split across chunks. Assert:

```text
frame BlobCount is correct
frame TotalArea_px is correct
A_blob_Atotal uses full-frame total, not chunk total
sum(frame BlobCount) == by-blob row count
```

**Step 2: Implement first pass**

Implement:

```python
def first_pass_frame_scalars(blob_csv: Path, chunksize: int) -> FrameReducers:
    ...
```

Compute per-frame:

```text
BlobCount
TotalArea_px
Amax_Atotal
A_top3_Atotal
Area_median_px
Area_p10_px
Area_p90_px
EquivRadius_median_px
EquivRadius_p10_px
EquivRadius_p90_px
BoundaryMetricValidCount
BoundaryMetricValidAreaFraction
HighConfidenceAreaFraction
BorderTouchingCount
```

**Step 3: Implement second pass**

Implement:

```python
def second_pass_write_products(...):
    ...
```

Append chunk-normalized rows to:

```text
blob_morphology_by_blob.csv
blob_shape_class_by_blob.csv
```

Update reducers for:

```text
blob_morphology_by_frame.csv
blob_shape_class_summary_by_frame.csv
blob_reliability_summary_by_frame.csv
blob_morphology_reliability_by_tier.csv
representative_blob_candidates.csv
```

**Step 4: Verify**

Run:

```powershell
python -m unittest tests.test_blob_morphology_data_product -v
python -m py_compile visualization\build_blob_morphology_data_product.py
```

Expected: pass.

## Task 5: Add CLI and Manifest

**Files:**

- Modify: `visualization/build_blob_morphology_data_product.py`
- Test: `tests/test_blob_morphology_data_product.py`

**Step 1: Write CLI tests**

Test:

```text
--help exits 0
--sidecar-dir required
--output-dir optional
--chunksize default 200000
--overwrite required for non-empty output dir
--dry-run validates inputs without writing full products
```

**Step 2: Implement CLI**

CLI:

```powershell
python visualization\build_blob_morphology_data_product.py `
  --sidecar-dir "C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418\geometry_sidecar_full_20260519_172548" `
  --output-dir "C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418\g21_blob_morphology_data_product_<timestamp>" `
  --chunksize 200000
```

**Step 3: Implement manifest and QC summary**

Write:

```text
blob_morphology_manifest.json
blob_morphology_qc_summary.md
blob_morphology_qc_summary.csv
blob_morphology_thresholds.json
```

Manifest fields:

```text
schema_version
input_sidecar_dir
input_file_inventory
sidecar_qc
command_line_args
thresholds
output_file_inventory
no_rerun_statement
git_commit_or_status_note
```

**Step 4: Verify**

Run:

```powershell
python visualization\build_blob_morphology_data_product.py --help
python -m unittest tests.test_blob_morphology_data_product -v
```

Expected: pass.

## Task 6: Run Real G21 Data Product Build

**Files:**

- Output only under: `C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418\g21_blob_morphology_data_product_<timestamp>`

**Step 1: Run dry-run**

Run:

```powershell
python visualization\build_blob_morphology_data_product.py `
  --sidecar-dir "C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418\geometry_sidecar_full_20260519_172548" `
  --dry-run
```

Expected:

```text
OverallStatus PASS
ProcessedFrames 12024
GeometryBlobRows 1362316
BoundaryMetricValidRows 636397
READY_TO_BUILD
```

**Step 2: Run full product build**

Run:

```powershell
python visualization\build_blob_morphology_data_product.py `
  --sidecar-dir "C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418\geometry_sidecar_full_20260519_172548" `
  --chunksize 200000
```

Expected:

```text
DATA_PRODUCT_PASS
by_blob_rows = 1362316
by_frame_rows = 12024
```

**Step 3: Verify output inventory**

Check all required files exist:

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
blob_morphology_qc_summary.csv
```

**Step 4: Verify acceptance gates**

Run a small verification mode or script assertions:

```text
by_blob_rows == 1362316
by_frame_rows == 12024
BoundaryMetricValidRows == 636397
FrameIndex contiguous 1:12024
No tiny/small rows assigned boundary morphology classes
All thresholds recorded
Manifest output inventory complete
```

## Task 7: Add Representative Atlas Renderer

**Files:**

- Create: `visualization/render_blob_atlas_panels.py`
- Test: `tests/test_blob_atlas_panels.py`

**Step 1: Write tests for candidate-to-label mapping**

Use tiny synthetic label images. Assert:

```text
selected label exists
crop contains selected blob
mask pixel count equals candidate Area_px
missing label path is reported
panel manifest records errors instead of silently skipping
```

**Step 2: Implement renderer CLI**

CLI:

```powershell
python visualization\render_blob_atlas_panels.py `
  --data-product-dir "<g21_blob_morphology_data_product_dir>" `
  --sidecar-dir "C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418\geometry_sidecar_full_20260519_172548"
```

Outputs:

```text
representative_blob_atlas_manifest.csv
figures_blob_morphology_atlas/
```

**Step 3: Implement panel content**

Each panel should include:

```text
binary blob mask
outer boundary
convex hull
equivalent ellipse or major/minor axis
centroid
ShapeClass
AreaTier
Area_px
ProjectedSphericity2D
Circularity2D_boundary
AspectRatio01
AxisAspectRatio
Solidity2D
ProjectedRoughness_boundary
PtotalOverPouter
FrameIndex / RealTime_s
```

**Step 4: Verify**

Run:

```powershell
python -m unittest tests.test_blob_atlas_panels -v
python -m py_compile visualization\render_blob_atlas_panels.py
```

Expected: pass.

## Task 8: Final Verification and Commit

**Files:**

- Code: `visualization/build_blob_morphology_data_product.py`
- Code: `visualization/render_blob_atlas_panels.py`
- Tests: `tests/test_blob_morphology_data_product.py`
- Tests: `tests/test_blob_atlas_panels.py`
- Docs: `docs/plans/2026-05-19-g21-blob-morphology-data-product-design.md`
- Docs: `docs/plans/2026-05-19-g21-blob-morphology-data-product.md`

**Step 1: Run unit tests**

Run:

```powershell
python -m unittest tests.test_blob_morphology_data_product tests.test_blob_atlas_panels -v
```

Expected: all pass.

**Step 2: Compile Python**

Run:

```powershell
python -m py_compile visualization\build_blob_morphology_data_product.py visualization\render_blob_atlas_panels.py
```

Expected: exit code 0.

**Step 3: Diff check**

Run:

```powershell
git diff --check
```

Expected: no whitespace errors.

**Step 4: Review generated output exclusions**

Run:

```powershell
git status --short
```

Expected:

```text
code, tests, and docs only
no large g21_blob_morphology_data_product output directory tracked
no masks/labels/figures tracked unless explicitly intended
```

**Step 5: Commit**

Run:

```powershell
git add visualization\build_blob_morphology_data_product.py visualization\render_blob_atlas_panels.py tests\test_blob_morphology_data_product.py tests\test_blob_atlas_panels.py docs\plans\2026-05-19-g21-blob-morphology-data-product-design.md docs\plans\2026-05-19-g21-blob-morphology-data-product.md
git commit -m "Add G21 blob morphology data product plan and builder"
```

Expected: commit succeeds.

## Stop Rules

Stop and report before proceeding if:

```text
sidecar QC is not PASS
by-blob row count differs from 1362316
by-frame row count differs from 12024
BoundaryMetricValidRows differs from 636397
builder needs to rerun sidecar or segmentation
atlas renderer cannot map candidates to labels
unit tests fail after implementation
```

Do not run:

```text
tracking
fractal dimension
3D roughness
new full sidecar extraction
new segmentation
results narrative interpretation
```
