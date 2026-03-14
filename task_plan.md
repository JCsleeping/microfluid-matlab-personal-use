# Task Plan: Fix Pipeline Long-Run Crash / Hang

## Problem Summary

Running `main_DNAPL_pipeline` on full dataset (1723 frames, 4 workers) causes MATLAB to "crash" — actually the desktop frontend goes unresponsive / window disappears while worker processes keep running. Short runs (6 frames) pass fine.

## Root Cause Analysis

Three factors compound:

1. **Memory: full mask retention** — `characterize_solubilization_v2.m:123` stores every frame's mask in `masks_arr{t}` during parfor. At 1821×1916×1723 frames ≈ **5.6 GB** just for masks, plus 4 workers each holding image buffers.
2. **Worker count too high** — 4 workers × (image + morphology + mask) intermediates push total RAM well past 16 GB on this machine.
3. **Excessive I/O** — Every frame prints 3-4 fprintf lines from workers, all funneled through diary. 1723 × 4 lines ≈ 7000 log entries during parfor.

## Optimization Phases

### Phase 1: Eliminate in-flight mask storage (Memory fix) ⬜
- **What**: Instead of `masks_arr{t} = mask_t` inside parfor, compute change-detection metrics (dissolved_px, appeared_px, net_px) inline per frame. Only keep scalar results + first/last mask.
- **Why**: Drops peak memory from ~5.6 GB → ~7 MB (two masks).
- **Files**: `analysis/characterize_solubilization_v2.m`
- **Risk**: Change detection currently needs consecutive masks (`masks{t-1}` vs `masks{t}`). In parfor, frames are out of order → must switch to comparing each frame against frame 1 (reference-based change), or fall back to sequential-only change detection with streaming approach.

### Phase 2: Reduce default workers from 4 → 2 ⬜
- **What**: Change `config.parallel.num_workers` default from 4 to 2.
- **Why**: 2 workers is the sweet spot for 16 GB RAM with large images. Each worker needs ~1.5 GB for image processing intermediates.
- **Files**: `config_pipeline.m:131`

### Phase 3: Throttle parfor logging ⬜
- **What**: Replace per-frame fprintf inside parfor with a batch summary. Workers should be silent; only main thread reports progress (e.g., every 50 frames in sequential mode, or a completion count after parfor).
- **Why**: Reduces diary I/O from ~7000 lines to ~35 lines. Prevents diary buffer from destabilizing the frontend.
- **Files**: `preprocessing/correct_illumination.m`, `segmentation/segment_DNAPL_v2.m`, `analysis/analyze_interfaces.m`, `analysis/characterize_solubilization_v2.m`

### Phase 4: Streaming change detection (sequential mode) ⬜
- **What**: In sequential mode, compute change detection on-the-fly (keep only previous mask), then discard. No need to store all masks.
- **Why**: Sequential mode also benefits from lower memory. Enables checkpoint/resume without saving gigabytes of masks.
- **Files**: `analysis/characterize_solubilization_v2.m`

## Decision Log

| # | Decision | Rationale | Date |
|---|----------|-----------|------|
| 1 | Pending: how to handle change detection in parallel mode | parfor doesn't guarantee order, so consecutive-frame comparison is impossible inline. Options: (A) reference-based change only, (B) parfor for metrics + sequential streaming pass for change detection, (C) drop parfor change detection entirely | TBD |

## Status: PLANNING — awaiting user approval
