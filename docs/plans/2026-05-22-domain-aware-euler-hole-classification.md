# Domain-Aware Euler Hole Classification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Distinguish aqueous holes from solid/pillar holes when using Euler topology for DNAPL blob classification.

**Architecture:** Keep raw `EulerNumber` unchanged, add per-blob hole audit fields, and make `TopologyType="cluster"` depend on water/mixed holes rather than any non-DNAPL enclosed region. Apply identical MATLAB changes in the main tree and `.worktrees/residual-structure-metrics-20260424`.

**Tech Stack:** MATLAB image morphology (`imfill`, `bwconncomp`, `bweuler`, `regionprops`), existing blob-detail chunk writer/schema, existing MATLAB unit tests.

---

## Subagent Review Summary

Independent subagent review confirmed the current bug:

- `analysis/analyze_blob_geometry.m` currently uses `EulerNumber < 1` as a direct `TopologyType="cluster"` trigger.
- `EulerNumber` only sees enclosed non-DNAPL background pixels and cannot distinguish water holes from solid pillar holes.
- The fix should keep raw `EulerNumber`, add domain-aware hole fields, and use `flow_domain/solid_mask` for cluster classification.
- Any `.m` change must be mirrored in `D:/00 Claude Code/01 MATLAB CODE/01 Microfluid/.worktrees/residual-structure-metrics-20260424`.

## Task 1: Add Failing MATLAB Tests For Hole Classification

**Files:**
- Modify: `D:/00 Claude Code/01 MATLAB CODE/01 Microfluid/tests/test_core_functions_synthetic.m`
- Mirror if present/needed: `D:/00 Claude Code/01 MATLAB CODE/01 Microfluid/.worktrees/residual-structure-metrics-20260424/tests/test_core_functions_synthetic.m`

**Step 1: Add water-hole test**

Add a synthetic annulus blob with a hole inside `flow_domain` and no `solid_mask` overlap.

Expected:
- `HoleCount == 1`
- `WaterHoleCount == 1`
- `SolidHoleCount == 0`
- `DominantHoleType == "water"`
- `EffectiveEulerNumber == 0`
- `TopologyType == "cluster"`

**Step 2: Add solid-pillar-hole test**

Add the same annulus geometry, but set the enclosed hole pixels as `solid_mask=true` and `flow_domain=false`.

Expected:
- raw `EulerNumber < 1`
- `HoleCount == 1`
- `SolidHoleCount == 1`
- `WaterHoleCount == 0`
- `DominantHoleType == "solid"`
- `EffectiveEulerNumber == 1`
- `TopologyType ~= "cluster"`; it falls back to droplet/column based on circularity.

**Step 3: Add backwards-compatibility test**

Call existing two-argument API:

```matlab
blob = analyze_blob_geometry(mask, []);
```

Expected:
- No error.
- New columns exist in `blob.blob_table`.
- `DominantHoleType` is `"unknown"` for holed blobs without domain masks.
- Old `EulerNumber` remains present.

**Step 4: Run failing tests**

Run:

```powershell
matlab -batch "cd('D:\00 Claude Code\01 MATLAB CODE\01 Microfluid'); runtests('tests/test_core_functions_synthetic.m')"
```

Expected before implementation: FAIL because new fields and domain-aware classification do not exist.

---

## Task 2: Implement Domain-Aware Hole Audit In `analyze_blob_geometry`

**Files:**
- Modify: `D:/00 Claude Code/01 MATLAB CODE/01 Microfluid/analysis/analyze_blob_geometry.m`
- Modify: `D:/00 Claude Code/01 MATLAB CODE/01 Microfluid/.worktrees/residual-structure-metrics-20260424/analysis/analyze_blob_geometry.m`

**Step 1: Extend function signature**

Change:

```matlab
function blob = analyze_blob_geometry(dnapl_mask, pixel_size)
```

to:

```matlab
function blob = analyze_blob_geometry(dnapl_mask, pixel_size, flow_domain, solid_mask)
```

with:

```matlab
if nargin < 2, pixel_size = []; end
if nargin < 3, flow_domain = []; end
if nargin < 4, solid_mask = []; end
```

Validate size only when masks are non-empty; if sizes mismatch, treat hole type as unknown rather than crashing.

**Step 2: Add helper**

Add a local helper such as:

```matlab
function hole_info = classify_blob_holes(blob_mask, dnapl_mask, flow_domain, solid_mask)
```

Algorithm:
- `hole_mask = imfill(blob_mask, 'holes') & ~blob_mask`
- `cc_holes = bwconncomp(hole_mask, 8)`
- For each hole component:
  - `solid_px = sum(hole_pixels & solid_mask)`
  - `water_px = sum(hole_pixels & flow_domain & ~dnapl_mask)`
  - `unknown_px = area - solid_px - water_px`
- Classify each hole:
  - `solid` if `solid_px / area >= 0.5`
  - `water` if `water_px / area >= 0.5`
  - `mixed` if both solid and water are present but neither dominates
  - `unknown` otherwise

**Step 3: Add props fields**

For every blob, set:

```matlab
props(i).HoleCount
props(i).WaterHoleCount
props(i).SolidHoleCount
props(i).MixedHoleCount
props(i).UnknownHoleCount
props(i).EffectiveEulerNumber
props(i).DominantHoleType
```

Definition:

```matlab
EffectiveEulerNumber = 1 - WaterHoleCount - MixedHoleCount;
```

**Step 4: Replace cluster rule**

Change from raw Euler rule:

```matlab
if props(i).EulerNumber < 1
```

to domain-aware rule:

```matlab
if props(i).WaterHoleCount + props(i).MixedHoleCount > 0
```

Fallback behavior when domain masks are missing:
- Preserve legacy behavior for unknown holes:
  - if `EulerNumber < 1` and `DominantHoleType == "unknown"`, keep `TopologyType="cluster"`.
- This keeps old two-argument usage behavior compatible.

**Step 5: Add fields to output table**

Add the new numeric and string fields to `blob.blob_table`, immediately after `EulerNumber`:

```matlab
HoleCount
WaterHoleCount
SolidHoleCount
MixedHoleCount
UnknownHoleCount
EffectiveEulerNumber
DominantHoleType
```

---

## Task 3: Pass Domain Masks Through Time-Series Metrics

**Files:**
- Modify: `D:/00 Claude Code/01 MATLAB CODE/01 Microfluid/analysis/compute_timeseries_blob_metrics.m`
- Modify: `D:/00 Claude Code/01 MATLAB CODE/01 Microfluid/analysis/characterize_solubilization_v2.m`
- Modify: `D:/00 Claude Code/01 MATLAB CODE/01 Microfluid/main_DNAPL_pipeline.m`
- Modify matching files in `D:/00 Claude Code/01 MATLAB CODE/01 Microfluid/.worktrees/residual-structure-metrics-20260424/`

**Step 1: Extend `compute_timeseries_blob_metrics`**

Change:

```matlab
function [metrics, blob_table] = compute_timeseries_blob_metrics(mask)
```

to:

```matlab
function [metrics, blob_table] = compute_timeseries_blob_metrics(mask, flow_domain, solid_mask)
```

and call:

```matlab
blob = analyze_blob_geometry(mask, [], flow_domain, solid_mask);
```

Keep optional defaults so old tests/calls still work.

**Step 2: Update `characterize_solubilization_v2` calls**

Change all Step-4 calls:

```matlab
compute_timeseries_blob_metrics(mask_t)
```

to:

```matlab
compute_timeseries_blob_metrics(mask_t, flow_domain, solid_mask)
```

Ensure the function has an optional `solid_mask` argument:

```matlab
function [sol, heartbeat] = characterize_solubilization_v2(frame_index, flow_domain, time_vector, config, heartbeat, solid_mask)
```

with `solid_mask=[]` default.

**Step 3: Update `main_DNAPL_pipeline`**

Pass `solid_mask` into:

```matlab
analyze_blob_geometry(dnapl_mask, config.physical.pixel_size, flow_domain, solid_mask)
```

and:

```matlab
characterize_solubilization_v2(frame_index, flow_domain, time_vector, config, heartbeat, solid_mask)
```

---

## Task 4: Update Blob Detail Schema And Chunk Tests

**Files:**
- Modify: `D:/00 Claude Code/01 MATLAB CODE/01 Microfluid/utilities/get_blob_detail_legacy_schema.m`
- Modify: `D:/00 Claude Code/01 MATLAB CODE/01 Microfluid/.worktrees/residual-structure-metrics-20260424/utilities/get_blob_detail_legacy_schema.m`
- Modify tests that construct canonical blob detail rows:
  - `D:/00 Claude Code/01 MATLAB CODE/01 Microfluid/tests/test_blob_detail_chunks.m`
  - `D:/00 Claude Code/01 MATLAB CODE/01 Microfluid/tests/test_blob_gap_audit_mock.m`
  - `D:/00 Claude Code/01 MATLAB CODE/01 Microfluid/tests/test_residual_structure_pipeline.m`

**Step 1: Add schema fields**

Add to `schema.variable_names` after `EulerNumber`:

```matlab
'HoleCount', 'WaterHoleCount', 'SolidHoleCount', 'MixedHoleCount', ...
'UnknownHoleCount', 'EffectiveEulerNumber', 'DominantHoleType'
```

Add to `schema.string_variables`:

```matlab
'DominantHoleType'
```

**Step 2: Verify normalization backfills old partial blob tables**

`normalize_blob_detail_table` already fills missing numeric fields with `NaN` and missing string fields with `""`. Tests should verify new schema fields appear even when old helper tables omit them.

**Step 3: Run schema tests**

Run:

```powershell
matlab -batch "cd('D:\00 Claude Code\01 MATLAB CODE\01 Microfluid'); runtests('tests/test_blob_detail_chunks.m')"
matlab -batch "cd('D:\00 Claude Code\01 MATLAB CODE\01 Microfluid'); runtests('tests/test_residual_structure_pipeline.m')"
```

---

## Task 5: Mirror The MATLAB Changes To The Worktree

**Files:**
- `D:/00 Claude Code/01 MATLAB CODE/01 Microfluid/.worktrees/residual-structure-metrics-20260424/analysis/analyze_blob_geometry.m`
- `D:/00 Claude Code/01 MATLAB CODE/01 Microfluid/.worktrees/residual-structure-metrics-20260424/analysis/compute_timeseries_blob_metrics.m`
- `D:/00 Claude Code/01 MATLAB CODE/01 Microfluid/.worktrees/residual-structure-metrics-20260424/analysis/characterize_solubilization_v2.m`
- `D:/00 Claude Code/01 MATLAB CODE/01 Microfluid/.worktrees/residual-structure-metrics-20260424/main_DNAPL_pipeline.m`
- `D:/00 Claude Code/01 MATLAB CODE/01 Microfluid/.worktrees/residual-structure-metrics-20260424/utilities/get_blob_detail_legacy_schema.m`
- Matching worktree tests where present.

**Step 1: Apply equivalent patches**

Do not copy blindly if worktree files have diverged. Inspect each hunk and apply the same behavior.

**Step 2: Verify no tree is missing the new symbols**

Run:

```powershell
rg -n "WaterHoleCount|SolidHoleCount|DominantHoleType|EffectiveEulerNumber" "D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\analysis" "D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\utilities"
rg -n "WaterHoleCount|SolidHoleCount|DominantHoleType|EffectiveEulerNumber" "D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\.worktrees\residual-structure-metrics-20260424\analysis" "D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\.worktrees\residual-structure-metrics-20260424\utilities"
```

---

## Task 6: Final Verification

**Run MATLAB tests:**

```powershell
matlab -batch "cd('D:\00 Claude Code\01 MATLAB CODE\01 Microfluid'); runtests('tests/test_core_functions_synthetic.m')"
matlab -batch "cd('D:\00 Claude Code\01 MATLAB CODE\01 Microfluid'); runtests('tests/test_blob_detail_chunks.m')"
matlab -batch "cd('D:\00 Claude Code\01 MATLAB CODE\01 Microfluid'); runtests('tests/test_residual_structure_pipeline.m')"
```

**Run Python smoke tests impacted by topology outputs:**

```powershell
python -m unittest tests.test_plot_timeseries tests.test_plot_rate_correlations
```

**Manual acceptance checks:**

- `blob_detail_all_frames.csv` from future reruns contains the new hole fields.
- Solid-only pillar holes do not increase `fracClusters`.
- Water/mixed holes still classify as `cluster`.
- Existing two-argument `analyze_blob_geometry(mask, pixel_size)` calls still run and preserve legacy cluster behavior for unknown holes.

---

## Notes

- Existing already-generated CSV files cannot be corrected by Python alone because they do not contain hole masks or solid overlap information.
- To update historical outputs, rerun the MATLAB pipeline with `output.save_blob_detail=true` after this change.
- Downstream Python scripts can keep using `TopologyType`; once new CSVs are generated, `TopologyType` will already be domain-aware.
