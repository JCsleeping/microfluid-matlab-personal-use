# C2 Mask Stack And Blob Detail Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the C2 red-mask morphology stage persist per-frame masks and per-blob detail so later TOA, fingering, AreaGini, shape entropy, AspectRatio, Solidity, and EulerNumber analyses have a strict data source.

**Architecture:** The MATLAB C2 morphology stage owns mask generation because it already computes the locked red DNAPL mask from the BasicPy HDF5 cache. It will write a single HDF5 mask stack plus a manifest, and it will stream per-blob detail into a CSV with processing-grid provenance. Python runner validation will only check artifact existence, schema, row counts, and provenance; it will not recompute masks or blob geometry.

**Tech Stack:** MATLAB Image Processing Toolbox, MATLAB HDF5 writer, Python stdlib runner validation, existing Branch C/C2 standalone runner.

---

## Confirmed Decisions

- Default mask-stack format: one HDF5 file, `red_mask_stack.h5`.
- Mask grid: `processing_grid`.
- Active A1 C2 processing scale: `3X`.
- `pixel_size_um` remains native-pixel size; processing-grid length uses `processing_pixel_size_um = pixel_size_um / processing_scale_factor`.
- Per-frame PNG masks are not a default full-run output. They can be added later as sampled QC images.

## Non-Goals

- Do not compute TOA, true fingering, AreaGini, shape entropy, or strict population morphology in this task.
- Do not implement geometric core/edge in this task.
- Do not continue endpoint audit in this task.
- Do not use Python to regenerate C2 masks from RGB. The MATLAB C2 mask is the source of truth.

## Output Contract

### `red_mask_stack.h5`

- Dataset: `/red_mask`
- Shape: `[height, width, frame_count]`
- Type: `uint8`, values `0` or `1`
- Frame order: same row order as `red_mask_timeseries.csv`
- Attributes or manifest fields must record:
  - `mask_grid = processing_grid`
  - `processing_scale_factor = 3`
  - `score_mode`
  - `threshold_value`
  - `threshold_source`
  - `min_area_px`
  - `morph_radius`
  - `flow_domain_shape`

### `red_mask_stack_manifest.csv`

One row per frame:

```text
frame_index,label,role,time_s,h5_dataset,h5_frame_index,
mask_grid,mask_height,mask_width,processing_scale_factor,
score_mode,threshold_value,threshold_source,red_mask_area_px,domain_area_px
```

### `red_blob_detail_all_frames.csv`

The CSV must contain per-blob rows with frame context and morphology fields:

```text
frame_index,time_s,label,role,score_mode,threshold_value,threshold_source,
processing_scale_factor,mask_grid,BlobID,Area,Area_processing_px2,
Area_native_equiv_px2,Perimeter,Perimeter_processing_px,
Perimeter_native_equiv_px,Centroid_X,Centroid_Y,
Centroid_X_native_equiv,Centroid_Y_native_equiv,
Circularity,AspectRatio,Solidity,EulerNumber,TopologyType
```

It may include the larger `analyze_blob_geometry` schema as long as the required fields remain present.

### `segmentation_manifest.json`

Add paths and provenance:

```json
{
  "mask_grid": "processing_grid",
  "processing_scale_factor": 3,
  "red_mask_stack_h5": "...",
  "red_mask_stack_manifest_csv": "...",
  "blob_detail_csv": "..."
}
```

## Task 1: Write Failing MATLAB Test

**Files:**
- Modify: `tests/test_segmentation_morphology_interface.m`

**Steps:**

1. Extend the tiny HDF5 fixture to set:
   - `write_mask_stack = true`
   - `write_blob_detail = true`
   - `processing_scale_factor = 3`
2. Assert `outputs.red_mask_stack_h5` and `outputs.red_mask_stack_manifest_csv` are present.
3. Assert `/red_mask` exists and has one frame in processing-grid dimensions.
4. Assert `red_mask_stack_manifest.csv` records `mask_grid=processing_grid` and `processing_scale_factor=3`.
5. Assert `red_blob_detail_all_frames.csv` exists and contains required fields.

**Run:**

```powershell
matlab -batch "cd('D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\.worktrees\interpolation-assisted-segmentation-20260527'); results = runtests('tests/test_segmentation_morphology_interface.m'); assertSuccess(results);"
```

**Expected before implementation:** fail because C2 does not write `red_mask_stack.h5`, the stack manifest, or processing-grid provenance fields.

## Task 2: Implement C2 Mask Stack Writer

**Files:**
- Modify: `run_a1_1bo_6ul_hdf5_cache_segmentation_morphology.m`

**Steps:**

1. Add config fields:
   - `write_mask_stack`
   - `mask_stack_format = "hdf5"`
   - `mask_stack_dataset = "/red_mask"`
   - `mask_grid = "processing_grid"`
   - `processing_scale_factor`
2. Normalize `processing_scale_factor` as a positive finite scalar; default to `1` if absent.
3. In morphology mode, pre-create `/red_mask` as `[height, width, frame_count]` uint8.
4. On each frame, write `uint8(mask)` to `(:,:,frame_idx)`.
5. Write `red_mask_stack_manifest.csv` with one row per frame.
6. Add stack paths to `outputs` and `segmentation_manifest.json`.

## Task 3: Implement Blob Detail Streaming

**Files:**
- Modify: `run_a1_1bo_6ul_hdf5_cache_segmentation_morphology.m`

**Steps:**

1. Pass `processing_scale_factor` into `compute_timeseries_blob_metrics` options.
2. Add C2 frame context columns:
   - `frame_index`
   - `time_s`
   - `label`
   - `role`
   - `score_mode`
   - `threshold_value`
   - `threshold_source`
   - `mask_grid`
3. Write blob detail incrementally to `red_blob_detail_all_frames.csv`.
4. Preserve empty output behavior: if no blobs exist, write an empty CSV with the required schema rather than omitting the file when `write_blob_detail=true`.

## Task 4: Add Runner Validation

**Files:**
- Modify: `run_dnapl_branch_c_timeseries_tool.py`
- Modify: `tests/test_branch_c_timeseries_tool.py`

**Steps:**

1. Add a helper that validates stack manifest and blob detail schema.
2. If `segmorph` ran and config requests `write_mask_stack`, fail validation when stack artifacts are missing or row count mismatches C2 timeseries.
3. If config requests `write_blob_detail`, fail validation when CSV is missing or required fields are absent.
4. Check `processing_scale_factor` in stack/blob provenance matches config.
5. Add Python unit tests for pass and fail cases using synthetic CSVs.

## Task 5: Update A1 Config And Docs

**Files:**
- Modify: `configs/a1_1bo_6ul_branch_c_timeseries.json`
- Modify: `docs/guides/dnapl_branch_c_timeseries_tool.md`

**Steps:**

1. Set A1:
   - `write_mask_stack = true`
   - `write_blob_detail = true`
   - `processing_scale_factor = 3`
2. Keep B1 test config conservative unless it is ready for full outputs.
3. Document output paths and explain these are processing-grid artifacts.

## Task 6: Verification

**Commands:**

```powershell
matlab -batch "cd('D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\.worktrees\interpolation-assisted-segmentation-20260527'); results = runtests('tests/test_segmentation_morphology_interface.m'); assertSuccess(results);"
python -m pytest tests\test_branch_c_timeseries_tool.py -q
python -m py_compile run_dnapl_branch_c_timeseries_tool.py
```

**Smoke check:**

Run a small pilot or morphology-only command against existing pilot cache if available, then inspect:

```text
red_mask_stack.h5
red_mask_stack_manifest.csv
red_blob_detail_all_frames.csv
segmentation_manifest.json
```

## Follow-Up Tasks

- Add TOA/fingering postprocess from `red_mask_stack.h5`.
- Add strict blob population postprocess from `red_blob_detail_all_frames.csv`.
- Add geometric core/edge after solid/core mask provenance is stable.
- Continue masked endpoint audit separately.
- Add multi-experiment config templates after A1 output contract is stable.
