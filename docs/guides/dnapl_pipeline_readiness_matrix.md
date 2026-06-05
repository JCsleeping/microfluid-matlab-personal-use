# DNAPL Pipeline Readiness Matrix

This matrix records what the current DNAPL Branch C/C2 pipeline can compute,
what has been validated on the A1 1-BO 6 uL reference run, and which gates are
still experiment-specific.

It is not a replacement for the standalone runner guide. Use this document to
decide whether an output is production-ready, a proxy, or blocked by metadata or
per-experiment review.

## Reference Run

Current reference run:

```text
experiment = A1 1-BO 6 uL
processing grid = 3X
runner = run_dnapl_branch_c_timeseries_tool.py
full-run rows = 3585
analysis package status = pass
analysis figures = 14 PNG + 14 SVG
endpoint consistency status = review
```

The endpoint consistency review does not invalidate the page-1 endpoint policy.
It flags that `01 WATER 1 SECONDS_3.tif` is not uniformly full-NAPL across all
pages. Any final A1 rerun should either restrict that file to full-NAPL pages
1-10 or use the endpoint-consistency flags when summarizing full-NAPL baseline
statistics.

## Readiness Levels

```text
Ready
  Implemented, validated on A1, and can be reused by the standalone runner.

Experiment-gated
  Implemented, but each new experiment must supply ROI, role map, endpoints,
  threshold, or QC acceptance.

Metadata-gated
  Implemented or partially implemented, but physical units require trusted
  physical metadata.

Research-gated
  Not yet implemented as a rigorous metric; current output is a proxy or
  diagnostic only.
```

## Matrix

| Area | Current status | A1 validation | General pipeline readiness | Per-experiment gate | Output artifacts |
| --- | --- | --- | --- | --- | --- |
| Standalone orchestration | Ready | Full A1 runner completed | Ready | Config per experiment | `run_dnapl_branch_c_timeseries_tool.py`, `run_summary.json` |
| Manifest and accepted frame ordering | Ready | 3585 accepted rows | Experiment-gated | Data paths, page expansion, role overrides | `accepted_frames.csv`, `accepted_frames_summary.json` |
| ROI / flow-domain mask | Ready | Manual A1 mask validated | Experiment-gated | User-supplied ROI/mask and overlay QC | `Mask.tif`, `mask_crop.h5`, mask overlay PNGs |
| BasicPy HDF5 cache | Ready | A1 cache completed | Ready after manifest/mask | BasicPy correction sanity check | `rgb_corrected` HDF5 cache, `cache_manifest.json` |
| Branch C `S_NAPL_color(t)` | Ready | A/B chroma outputs completed | Experiment-gated | masked endpoint audit, endpoint policy | `S_NAPL_color_primary_A.csv`, `S_NAPL_color_sensitivity_B.csv` |
| Endpoint A/B sensitivity | Ready | A/B difference small on A1 | Ready after Branch C | endpoint policy must include A/B | `S_NAPL_color_A_B_sensitivity_comparison.csv` |
| Endpoint consistency postprocess | Ready | A1 status `review`, 59 flags | Ready | expanded role semantics must be inspected | `endpoint_consistency_*.csv/json` |
| Realtime timeline join | Ready | A1 realtime outputs joined | Experiment-gated | timeline reconstruction policy | `frame_timeline_manifest.csv`, `_realtime.csv` outputs |
| C2 segmentation pilot | Ready | A1 pilot locked threshold exists | Experiment-gated | score mode and threshold review | `candidate_summary.csv`, `threshold_sweep_all.csv` |
| C2 locked segmentation/morphology | Ready | A1 full C2 morphology completed | Experiment-gated | locked threshold and QC overlays | `red_mask_timeseries.csv`, `red_blob_summary_timeseries.csv` |
| Per-frame mask stack | Ready | A1 HDF5 stack completed | Ready after C2 | C2 locked mask must pass validation | `red_mask_stack.h5`, `red_mask_stack_manifest.csv` |
| Per-blob detail | Ready | A1 chunked blob detail completed | Ready after C2 | chunk merge and schema validation | `red_blob_detail_chunks/`, `red_blob_detail_all_frames.csv` |
| Blob count and area | Ready | A1 outputs present | Ready after C2 | none beyond mask QC | `red_mask_timeseries.csv`, `red_blob_summary_timeseries.csv` |
| Blob shape statistics | Ready | A1 `blob_morphology_timeseries.csv` completed | Ready after blob detail | valid per-blob detail table | `AreaGini`, `ShapeEntropy`, `AspectRatio`, `Solidity`, `EulerNumber` |
| Dynamic blob tracking | Research-gated | Not implemented | Not ready | tracking model and validation | none |
| DNAPL-water interface length `L_ow` | Ready as 2D projected length | A1 completed in px | Metadata-gated for metres | mask QC; pixel size for metres | `dnapl_water_length_px`, `InterfaceArea` |
| DNAPL-solid contact length | Ready as 2D projected contact length | A1 completed in px | Metadata-gated for metres | solid/contact zone QC; pixel size for metres | `dnapl_solid_length_px` |
| `InterfaceArea` | Ready as legacy alias | A1 alias validated | Ready with strict semantics | do not interpret as area | `InterfaceArea = dnapl_water_length_px` |
| `a_i_2D_proxy` | Ready as 2D proxy | A1 completed | Proxy only | red-mask area and L_ow must be finite | `a_i_2D_proxy` |
| X-direction regional `S(x,t)` | Ready as proxy | A1 x-zone outputs completed | Ready after Branch C | flow direction and terminal fraction | `S_NAPL_color_xbins_*`, x-zone derived fields |
| Geometric core/edge occupancy | Ready | A1 core/edge mask analysis passed | Experiment-gated | solid/flow mask alignment and distance threshold | `geometry_core_edge_timeseries.csv` |
| Core/edge interface/contact lengths | Ready as 2D chain-code px | A1 completed | Metadata-gated for metres | geometry mask and pixel size | `core_dnapl_water_length_px`, `edge_dnapl_solid_length_px` |
| Strict TOA map | Ready as mask-stack metric | A1 `toa_frame_index.npy` completed | Ready after mask stack | C2 mask stack must pass | `toa_frame_index.npy`, `toa_x_summary.csv` |
| Breakthrough timing | Ready as mask-stack / x-zone proxy | A1 outputs present | Experiment-gated | time reconstruction and threshold policy | `mask_stack_analysis_summary.json`, x-zone event fields |
| Fingering | Proxy ready | A1 `finger_count_proxy` present | Research-gated for pore graph | graph/skeleton method not implemented | `finger_count_proxy`, `front_roughness` |
| Residual trapping proxy | Ready | A1 residual postprocess completed | Ready after timeline/C2 | residual role definition | `residual_trapping_timeseries.csv`, `residual_trapping_summary.json` |
| Phase-aware residual retention | Ready as mask-stack metric | A1 passed | Experiment-gated | full baseline role must be reviewed | `phase_mask_timeseries.csv`, `phase_retention_class.npy` |
| Analysis package | Ready | A1 package status `pass` | Ready after upstream outputs | upstream QC must pass | `analysis_timeseries_derived.csv`, 14 figure pairs |
| Legacy plotting adapter | Ready as proxy adapter | A1 ready | Ready with warnings | do not label as physical Sn | `branch_c_legacy_plot_timeseries.csv` |
| Physical metre lengths | Metadata-gated | Not unlocked | Needs trusted metadata | `pixel_size_um` or `processing_pixel_size_um` | `dnapl_*_length_m` |
| PV axis and `dS/dPV` | Metadata-gated | Not unlocked | Needs separate metadata script or manifest | flow rate and pore volume | `PV`, `dS_dPV` |
| Capillary number | Metadata-gated | Not unlocked | Needs separate metadata script or manifest | viscosity, velocity, IFT | `capillary_number` |
| Physical `Sn` | Research/metadata-gated | Not unlocked | Not ready | endpoint calibration plus pore volume/optical model | none as final physical `Sn` |
| Mass-transfer coefficient | Research/metadata-gated | Not unlocked | Not ready | physical concentration/mass-transfer model | none |
| Multi-experiment comparison | Deferred | A1 only | Not preconfigured | wait for each experiment result and onboard individually | future per-experiment analysis packages |

## Current Completion Boundary

The pipeline is complete for operational image-derived analysis:

```text
S_NAPL_color(t)
endpoint sensitivity
red mask area fraction
blob count and morphology
2D L_ow and DNAPL-solid contact
x-zone profiles
core/edge metrics
TOA/front/fingering proxies
phase-aware residual retention
analysis package and figures
```

The pipeline is not complete for strict physical interpretation:

```text
physical Sn
metre interface/contact lengths
PV axis
dS/dPV
capillary number
mass-transfer coefficient
true pore-graph fingering
cross-experiment comparison
```

These are intentionally gated. They should not be unlocked by assuming values
from filenames or by treating proxy saturation as physical saturation.

## New Experiment Policy

Do not pre-create multi-experiment configs before data exists. Each new
experiment must be onboarded after the data, ROI/mask, endpoint candidates, and
role map are known.

The repeatable unit is:

```text
one experiment
one config
one ROI/mask provenance package
one endpoint/role audit
one full runner output
one analysis package
one archived report
```

Use `docs/guides/dnapl_new_experiment_onboarding_checklist.md` when a new
experiment result arrives.
