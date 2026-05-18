# Path Isolation And Config Pipeline Review Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Review the current main-repo fix for MATLAB path pollution from `.worktrees` and the `config_pipeline` override/TIF discovery regression.

**Architecture:** The main repo should be self-contained when launched from `D:\00 Claude Code\01 MATLAB CODE\01 Microfluid`. Project entrypoints must add project paths while excluding `01 Microfluid\.worktrees`, so main files never call functions from worktree checkouts. `config_pipeline` should apply caller overrides before scanning TIF files, and `multipage_tif_path` should be a scan bypass.

**Tech Stack:** MATLAB R2021a-compatible `.m` files, MATLAB path management, `config_pipeline`, `main_DNAPL_pipeline`, `validate_config`, Git diff review.

---

## Files Under Review

- Modify: `D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\config_pipeline.m`
- Modify: `D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\main_DNAPL_pipeline.m`
- Modify: `D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\utilities\validate_config.m`
- Reference only: `D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\.worktrees\residual-structure-metrics-20260424\config_pipeline.m`
- Reference only: `D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\.worktrees\residual-structure-metrics-20260424\utilities\validate_config.m`

## Current Problem To Review

Before this fix, running `config_pipeline()` in the main repo could add `01 Microfluid\.worktrees\...` to MATLAB path via `addpath(genpath(this_dir))`. That allowed the main repo `config_pipeline.m` to call a worktree `validate_config.m`. The mixed versions caused:

```text
Unrecognized field name "save_blob_detail".

Error in validate_config (line 65)
    assert_logical_scalar(config.output.save_blob_detail, 'output.save_blob_detail');
```

The fix should prevent version mixing and also keep the earlier P1 behavior fixed:

```matlab
config_pipeline('data_path', some_dir)
```

must apply `data_path` before TIF scanning, and:

```matlab
config_pipeline('data_path', missing_dir, 'multipage_tif_path', {'D:\dummy.tif'})
```

must not scan `missing_dir`.

## Task 1: Review `config_pipeline` Path Isolation And Scan Order

**Files:**
- Review: `D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\config_pipeline.m`

- [ ] **Step 1: Confirm `.worktrees` is excluded from project path setup**

Check that `config_pipeline` calls a helper equivalent to:

```matlab
this_dir = fileparts(mfilename('fullpath'));
add_project_paths(this_dir);
```

and that `add_project_paths()` builds `genpath(project_root)` while excluding any path under:

```matlab
fullfile(project_root, '.worktrees')
```

Expected: no plain `addpath(genpath(this_dir))` remains in `config_pipeline.m`.

- [ ] **Step 2: Confirm TIF scanning is delayed until after overrides**

Check that defaults set:

```matlab
config.multipage_tif_path = {};
```

before overrides, and that this scan happens only after the override loop:

```matlab
if isempty(config.multipage_tif_path)
    config.multipage_tif_path = discover_tif_paths(config.data_path);
end
```

Expected: there is no `dir(fullfile(config.data_path, '*.tif'))` before the override loop.

- [ ] **Step 3: Confirm `output_path` uses final `data_path` unless explicitly overridden**

Check that `output_path_overridden = has_override(varargin, 'output_path')` is computed before applying overrides, and that this logic appears after overrides:

```matlab
if ~output_path_overridden
    config.output_path = fullfile(config.data_path, default_output_name);
end
```

Expected: `config_pipeline('data_path', data_dir)` creates an output path under `data_dir`, while `config_pipeline('output_path', out_dir)` preserves `out_dir`.

- [ ] **Step 4: Confirm `save_blob_detail` default exists**

Check that defaults include:

```matlab
config.output.save_blob_detail = false;
```

Expected: `validate_config` can safely read `config.output.save_blob_detail` for configs created by main-repo `config_pipeline`.

## Task 2: Review `main_DNAPL_pipeline` Path Isolation

**Files:**
- Review: `D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\main_DNAPL_pipeline.m`

- [ ] **Step 1: Confirm entrypoint path setup excludes `.worktrees`**

Check that the initialization block uses:

```matlab
pipeline_root = fileparts(mfilename('fullpath'));
add_project_paths(pipeline_root);
```

Expected: no plain `addpath(genpath(pipeline_root))` remains in `main_DNAPL_pipeline.m`.

- [ ] **Step 2: Confirm helper behavior is scoped and non-invasive**

Check helper functions at the end of `main_DNAPL_pipeline.m`:

```matlab
add_project_paths(project_root)
remove_worktree_paths(project_root)
normalize_path(p)
```

Expected: the helper removes only paths under `D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\.worktrees`, not arbitrary user paths outside this repo.

## Task 3: Review `validate_config` Compatibility

**Files:**
- Review: `D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\utilities\validate_config.m`

- [ ] **Step 1: Confirm `save_blob_detail` validation is present**

Check that output controls include:

```matlab
assert_logical_scalar(config.output.save_blob_detail, 'output.save_blob_detail');
```

Expected: invalid values such as `7` throw `validate_config:badParam`.

- [ ] **Step 2: Confirm parallel guard is present**

Check that this configuration errors:

```matlab
config_pipeline( ...
    'multipage_tif_path', {'D:\dummy.tif'}, ...
    'output.save_blob_detail', true, ...
    'parallel.enabled', true, ...
    'physical.pixel_size', 1e-6)
```

Expected: `validate_config:badParam`.

## Task 4: Run Reproduction Commands

**Files:**
- Run from: `D:\00 Claude Code\01 MATLAB CODE\01 Microfluid`

- [ ] **Step 1: Reproduce clean default config**

Run:

```powershell
matlab -batch "restoredefaultpath; cd('D:\00 Claude Code\01 MATLAB CODE\01 Microfluid'); clear functions; config = config_pipeline(); fprintf('DEFAULT_OK files=%d save_blob_detail=%d\n', numel(config.multipage_tif_path), config.output.save_blob_detail); which config_pipeline; which validate_config;"
```

Expected output includes:

```text
DEFAULT_OK files=118 save_blob_detail=0
D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\config_pipeline.m
D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\utilities\validate_config.m
```

The exact file count can differ if the default G: dataset changes, but `which` must point to the main repo, not `.worktrees`.

- [ ] **Step 2: Verify `data_path` override scans final path**

Run:

```powershell
matlab -batch "restoredefaultpath; cd('D:\00 Claude Code\01 MATLAB CODE\01 Microfluid'); clear functions; data_dir = 'D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\01 databased\14 LNAPL-2UL\02 Water Displacement'; config = config_pipeline('data_path', data_dir, 'physical.pixel_size', 1e-6); fprintf('OVERRIDE_OK files=%d output_under_data=%d\n', numel(config.multipage_tif_path), startsWith(config.output_path, data_dir));"
```

Expected output:

```text
OVERRIDE_OK files=46 output_under_data=1
```

- [ ] **Step 3: Verify explicit `multipage_tif_path` skips missing `data_path` scan**

Run:

```powershell
matlab -batch "restoredefaultpath; cd('D:\00 Claude Code\01 MATLAB CODE\01 Microfluid'); clear functions; config = config_pipeline('data_path','D:\missing_skip_scan','multipage_tif_path',{'D:\dummy.tif'},'physical.pixel_size',1e-6); fprintf('EXPLICIT_TIF_OK files=%d path=%s\n', numel(config.multipage_tif_path), config.multipage_tif_path{1});"
```

Expected output:

```text
EXPLICIT_TIF_OK files=1 path=D:\dummy.tif
```

- [ ] **Step 4: Verify `save_blob_detail` validation**

Run:

```powershell
matlab -batch "restoredefaultpath; cd('D:\00 Claude Code\01 MATLAB CODE\01 Microfluid'); clear functions; ok1=false; try, config_pipeline('multipage_tif_path',{'D:\dummy.tif'},'output.save_blob_detail',7,'physical.pixel_size',1e-6); catch ME, ok1=strcmp(ME.identifier,'validate_config:badParam'); fprintf('BAD_SAVE_BLOB_ERR=%s\n', ME.identifier); end; ok2=false; try, config_pipeline('multipage_tif_path',{'D:\dummy.tif'},'output.save_blob_detail',true,'parallel.enabled',true,'physical.pixel_size',1e-6); catch ME, ok2=strcmp(ME.identifier,'validate_config:badParam'); fprintf('PARALLEL_SAVE_BLOB_ERR=%s\n', ME.identifier); end; assert(ok1 && ok2);"
```

Expected output:

```text
BAD_SAVE_BLOB_ERR=validate_config:badParam
PARALLEL_SAVE_BLOB_ERR=validate_config:badParam
```

## Task 5: Review Known Risks And Boundaries

**Files:**
- Review: current Git diff only.

- [ ] **Step 1: Check that this plan does not claim the full residual-structure feature is merged into main**

Expected: this main-repo patch only fixes config/path compatibility. It does not backport all worktree residual-structure implementation files.

- [ ] **Step 2: Check for accidental behavior change from rewritten `config_pipeline.m` comments**

Expected: comments were converted to ASCII, but default values should match the intended current main-branch values, especially:

```matlab
config.data_path = 'G:\微流控\17 1-BO 4UL 5% TWEEM 80\Tween 80';
config.segmentation.method = 'gmm_v2';
config.output.checkpoint = true;
config.output.save_interval = 72;
```

- [ ] **Step 3: Check path pollution warning**

Expected: user-facing guidance should say not to run:

```matlab
addpath(genpath(pwd))
```

from the repo root, because it will still include `.worktrees`. The safer entrypoints are:

```matlab
cd('D:\00 Claude Code\01 MATLAB CODE\01 Microfluid')
config = config_pipeline();
results = main_DNAPL_pipeline(config);
```

## Task 6: Commit Criteria

**Files:**
- Review: `git diff -- config_pipeline.m main_DNAPL_pipeline.m utilities/validate_config.m`

- [ ] **Step 1: Confirm review has no P0/P1/P2 findings**

Expected: no blocker remains for `config_pipeline()` or `config_pipeline('data_path', ...)`.

- [ ] **Step 2: Confirm tracked changed files are limited**

Run:

```powershell
git -C "D:\00 Claude Code\01 MATLAB CODE\01 Microfluid" diff --name-status
```

Expected output:

```text
M       config_pipeline.m
M       main_DNAPL_pipeline.m
M       utilities/validate_config.m
A       docs/superpowers/plans/2026-04-28-path-isolation-config-review.md
```

- [ ] **Step 3: If Claude approves, commit with this message**

Run:

```powershell
git -C "D:\00 Claude Code\01 MATLAB CODE\01 Microfluid" add config_pipeline.m main_DNAPL_pipeline.m utilities/validate_config.m docs/superpowers/plans/2026-04-28-path-isolation-config-review.md
git -C "D:\00 Claude Code\01 MATLAB CODE\01 Microfluid" commit -m "fix: isolate worktree paths in pipeline config"
```

Expected: one commit containing only the path-isolation/config compatibility fix and this review plan.

## Self-Review Checklist

- [ ] Spec coverage: covers the original `save_blob_detail` field error, the worktree path pollution root cause, delayed TIF scanning, explicit TIF scan bypass, `output_path` override behavior, and validation compatibility.
- [ ] No placeholders: all commands and expected outputs are concrete.
- [ ] Type consistency: uses existing MATLAB field names `output.save_blob_detail`, `multipage_tif_path`, `data_path`, `output_path`, and `parallel.enabled`.
- [ ] Scope control: does not request backporting the entire residual-structure worktree feature into main.
