# G21 Blob Structure Data/Figure Bundle Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a neutral data and figure bundle for the accepted G21 blob morphology outputs.

**Architecture:** Add a reusable Python builder that reads accepted ShapeClassV1, structure statistics, representative atlas, and pipeline acceptance artifacts, then writes normalized data tables, neutral figures, inventories, notes, and a manifest. The builder does not run sidecar extraction or write scientific interpretation.

**Tech Stack:** Python, pandas, matplotlib, unittest, existing G21 CSV/PNG products.

---

### Task 1: Write Tests For Bundle Outputs

**Files:**
- Create: `tests/test_blob_structure_data_figure_bundle.py`

**Step 1: Write failing tests**

Add a fixture with minimal ShapeClassV1 rows, structure statistics rows, representative atlas metadata, and acceptance QC tables. Assert that the builder writes all required files, inventories point to existing outputs, formula notes contain required definitions, and notes avoid forbidden interpretation wording.

**Step 2: Verify RED**

Run:

```powershell
python -m unittest tests.test_blob_structure_data_figure_bundle -v
```

Expected: fails because `visualization.build_blob_structure_data_figure_bundle` does not exist.

### Task 2: Implement Bundle Builder

**Files:**
- Create: `visualization/build_blob_structure_data_figure_bundle.py`

**Step 1: Implement CLI and inputs**

Add arguments:

```text
--postprocess-dir
--morphology-dir
--shape-class-v1-dir
--structure-statistics-dir
--acceptance-dir
--output-dir
--repo-root
--overwrite
```

**Step 2: Implement table writers**

Write:

```text
tables/shape_class_v1_count_area_summary.csv
tables/shape_class_v1_by_stage_summary.csv
tables/area_tier_summary.csv
tables/geometry_interpretable_fraction_by_stage.csv
tables/frame_level_blob_structure_summary.csv
tables/representative_blob_table.csv
```

**Step 3: Implement neutral figures**

Write PNG and SVG for required figures. Use neutral titles and labels only.

**Step 4: Implement notes and inventories**

Write README, field dictionary, formula notes, QC/scope notes, data inventory, figure inventory, and manifest.

**Step 5: Verify GREEN**

Run:

```powershell
python -m unittest tests.test_blob_structure_data_figure_bundle -v
python -m py_compile visualization\build_blob_structure_data_figure_bundle.py
```

Expected: pass.

### Task 3: Generate G21 Bundle

**Files:**
- Output only under `C:\tmp\g21_output_20260515_190825\...\g21_blob_structure_data_figure_bundle_<timestamp>`

**Step 1: Run builder on frozen G21 inputs**

Use:

```powershell
python visualization\build_blob_structure_data_figure_bundle.py `
  --postprocess-dir "C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418" `
  --morphology-dir "C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418\g21_blob_morphology_data_product_20260520_124541" `
  --shape-class-v1-dir "C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418\g21_blob_morphology_data_product_20260520_124541\g21_shape_class_v1_formal_package_20260521_105739" `
  --structure-statistics-dir "C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418\g21_blob_morphology_data_product_20260520_124541\g21_blob_structure_statistics_v1_20260521_113634" `
  --acceptance-dir "C:\tmp\g21_output_20260515_190825\postprocess_residual_structure_20260518_231418\g21_blob_morphology_data_product_20260520_124541\g21_blob_pipeline_acceptance_20260521_144653" `
  --repo-root "D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\.worktrees\residual-structure-metrics-20260424"
```

**Step 2: Inspect generated manifest**

Confirm the decision label, row counts, generated tables, and generated figures.

### Task 4: Final Verification And Commit

**Files to stage:**
- `docs/plans/2026-05-21-g21-blob-structure-data-figure-bundle-design.md`
- `docs/plans/2026-05-21-g21-blob-structure-data-figure-bundle.md`
- `tests/test_blob_structure_data_figure_bundle.py`
- `visualization/build_blob_structure_data_figure_bundle.py`

Do not stage:

```text
visualization/build_g21_level_b_geometry_package.py
C:\tmp generated bundle outputs
```

Run:

```powershell
python -m unittest tests.test_blob_structure_data_figure_bundle -v
python -m py_compile visualization\build_blob_structure_data_figure_bundle.py
git diff --check
git status --short
```

Commit:

```powershell
git commit -m "Add blob structure data figure bundle builder"
```
