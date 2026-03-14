# DNAPL Microfluidic Image Analysis Toolbox

> **Automated pore-scale DNAPL segmentation, dissolution tracking, and mass transfer analysis for microfluidic chip experiments.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![MATLAB](https://img.shields.io/badge/MATLAB-R2020b+-blue.svg)](https://www.mathworks.com/products/matlab.html)

---

## Overview

This MATLAB toolbox automates the analysis of Dense Non-Aqueous Phase Liquid (DNAPL) experiments in microfluidic porous media chips. It processes time-series microscopy images to quantify DNAPL saturation, blob geometry, interfacial area, dissolution kinetics, and mass transfer — from raw multi-page TIFs to publication-ready figures and reports.

### Key Features

- **Multi-method segmentation**: GMM, Otsu, Adaptive thresholding, and a novel **multi-pass morphological reconstruction** method (v2) that recovers dark spots inside DNAPL
- **Streaming frame processing**: Memory-efficient lazy loading processes thousands of frames without loading all into memory (~14 MB/frame instead of ~22 GB)
- **Automated flow domain extraction**: Dual-method pillar detection (color + morphology) with automatic ROI selection
- **Complete dissolution analysis**: Saturation curves, blob evolution, interfacial area, dissolution rate, and mass transfer estimation
- **Publication-quality visualization**: 5 diagnostic figure generators with subplot export
- **Automated reporting**: Generates `.txt` and `.md` analysis reports with key metrics

---

## Requirements

### MATLAB

- **MATLAB R2020b** or later

### Required Toolboxes

| Toolbox | Used For |
|---------|----------|
| **Image Processing Toolbox** | `imread`, `imfill`, `imerode`, `imreconstruct`, `strel`, `bwconncomp`, etc. |
| **Statistics and Machine Learning Toolbox** | `fitgmdist`, `cluster`, `prctile` |

### Optional

- **Parallel Computing Toolbox** — enables `parfor` acceleration for Step 4. Worker GPU use is disabled automatically in parallel mode.

---

## Installation

```bash
git clone https://github.com/JCsleeping/microfluid.git
cd DNAPL-Microfluidic-Analysis
```

In MATLAB:

```matlab
% Add all subdirectories to path
addpath(genpath(pwd));

% Verify installation
runtests('tests');
```

---

## Quick Start

### 1. Configure

Edit `config_pipeline.m` to set your data path:

```matlab
config.data_path = 'path/to/your/tif/files';
```

The pipeline automatically scans for `.tif` files and sorts them by date.

### 2. Run

```matlab
results = main_DNAPL_pipeline();
```

### 3. Results

Output is saved to `<data_path>/output_<timestamp>/`:

| File | Contents |
|------|----------|
| `results_*.mat` | Full results struct |
| `timeseries_*.csv` | Sn, blob count, interface area vs. time |
| `blob_properties_*.csv` | Per-blob geometry metrics |
| `saturation_*.csv` | Frame-1 saturation, chip/pore volume, and DNAPL 2.5D volume summary |
| `analysis_report.md` | Formatted summary report |
| `fig_*.png` | Publication-quality figures |
| `logs/pipeline_log_*.txt` | Full command-window run log (enabled by default) |
| `progress/progress_latest.*` | Lightweight Step-4 progress snapshot (optional) |
| `status/heartbeat_latest.*` | Latest structured run status for watchers and debugging |

`progress_latest.mat/.csv` only store numeric time-series progress. They do not save full per-frame masks or diagnostic images.
`heartbeat_latest.json/.mat` store only the latest pipeline status snapshot; they are overwritten in place.
Heartbeat `status` may be `starting`, `running`, `paused`, `completed`, or `failed`. A `paused` run is a safe checkpoint-boundary stop, not an error.
Heartbeat payloads now include `matlab_pid` and `hostname`, which let the watcher bind a live status file to the specific MATLAB process that created it.
Sequential checkpoints now persist the locked Step-4 threshold, so resumed runs continue with the same segmentation threshold instead of re-locking from frame 1. Older checkpoints remain readable, but they emit a legacy warning and recompute the threshold once.
`results.chip_geometric_volume_m3`, `results.flow_domain_volume_m3`, and `results.saturation.dnapl_volume_m3` are estimated as `2D area × config.physical.depth`; they are 2.5D volume estimates, not full 3D reconstructions. `flow_domain_volume_m3` is the pore-space volume after subtracting pillars, while `chip_geometric_volume_m3` is the full ROI geometric volume.

To monitor a run from another terminal:

```powershell
powershell -File utilities/watch_pipeline_status.ps1 -OutputPath <output_path>
```

The watcher polls the specified `output_path` every 10 minutes by default. It prefers `status/heartbeat_latest.json` and falls back to logs/checkpoints when heartbeat is unavailable. When heartbeat is present it checks the recorded `matlab_pid`; when heartbeat is missing it uses a conservative fallback: fresh artifacts mean `running`, stale artifacts mean `stalled`, and only stale artifacts with no matching MATLAB process are treated as `crashed`.

To cap long MATLAB sessions without changing segmentation math, enable checkpoint-boundary safe pause:

```matlab
config.output.checkpoint = true;
config.output.save_interval = 72;
config.output.max_frames_per_session = 288;
config.parallel.enabled = false;
```

When `max_frames_per_session` is finite, the pipeline only pauses after a checkpoint is saved. The budget tracks Step-4 work done in the current MATLAB session: on a fresh run frame 1 counts because it establishes the locked threshold, while resumed runs count only newly advanced frames beyond the checkpoint. Re-run the same config with the same `output_path` to continue from the latest checkpoint. This mode is only supported for sequential Step 4 runs.

---

## Segmentation Methods

| Method | Config Value | Description |
|--------|-------------|-------------|
| **GMM** | `'gmm'` | 2-component Gaussian Mixture Model on Lab a* channel (default) |
| **Otsu** | `'otsu'` | Global threshold via Otsu's method (GMM fallback) |
| **Adaptive** | `'adaptive'` | Local adaptive thresholding (51×51 neighborhood) |
| **GMM + Morph v2** | `'gmm_v2'` | GMM + morphological reconstruction for dark-spot recovery |
| **Otsu + Morph v2** | `'otsu_v2'` | Otsu + morphological reconstruction |

### v2 Multi-Pass Segmentation

The v2 methods address dark spots (suspended particles, bubbles) inside DNAPL that cause holes in the segmentation mask:

```
Pass 1: Color-based segmentation (a* channel → GMM/Otsu)
Pass 2: Morphological reconstruction — erode background, reconstruct,
        difference = internal holes filled
Final:  Union + imfill + morphological cleanup
```

Enable with:

```matlab
config.segmentation.method = 'gmm_v2';
config.segmentation.hole_fill_radius = 3;  % max dark-spot diameter [px]
```

---

## Project Structure

```
├── main_DNAPL_pipeline.m          Main entry point
├── config_pipeline.m              Configuration (all parameters)
│
├── preprocessing/                 Image preprocessing
│   ├── rotate_and_crop.m          Rotation correction & chip cropping
│   ├── correct_illumination.m     Illumination normalization
│   ├── align_images.m             Frame-to-frame registration
│   └── select_illumination_kernel.m  Interactive kernel selection
│
├── segmentation/                  Segmentation modules
│   ├── extract_flow_domain.m      Pore-space mask extraction
│   ├── segment_DNAPL.m            DNAPL segmentation v1 (color-based)
│   ├── segment_DNAPL_v2.m         DNAPL segmentation v2 (+ morph reconstruction)
│   └── refine_mask.m              Morphological cleanup
│
├── analysis/                      Quantitative analysis
│   ├── calculate_saturation.m     Sn/Sw calculation
│   ├── analyze_blob_geometry.m    Blob size, shape, classification
│   ├── analyze_interfaces.m       DNAPL-water/solid interface detection
│   ├── calculate_mass_transfer.m  Mass transfer rate estimation
│   └── characterize_solubilization_v2.m  Time-series dissolution analysis
│
├── visualization/                 Figure generation
│   ├── visualize_preprocessing.m
│   ├── visualize_segmentation.m
│   ├── visualize_blobs.m
│   ├── visualize_interfaces.m
│   └── visualize_solubilization.m
│
├── utilities/                     Helper functions
│   ├── load_frame.m               On-demand frame loading (streaming)
│   ├── load_images.m              Single image loading
│   ├── read_multipage_tif.m       Multi-page TIF reader
│   ├── save_subplots.m            Subplot export utility
│   ├── validate_config.m          Configuration validation
│   ├── export_results.m           MAT/CSV/XLSX export
│   └── generate_report.m          Analysis report generator
│
├── tests/                         Test suite
│   ├── test_main_pipeline_clean_ref_auto_crop.m
│   ├── test_extract_flow_domain_robustness.m
│   └── test_core_functions_synthetic.m
│
├── ISSUES.md                      Version history & known issues
├── 技术报告.md                     Technical report (Chinese)
├── 使用指南.md                     User guide (Chinese)
└── 分割方法技术讨论.md              Segmentation methods discussion (Chinese)
```

---

## Configuration Reference

Key parameters in `config_pipeline.m`:

```matlab
% Input
config.data_path = 'path/to/tifs';          % Directory with .tif files
config.input_mode = 'multipage_tif';        % 'multipage_tif' | 'separate_files'

% Preprocessing
config.preprocess.auto_rotate = false;
config.illumination.method = 'morphological';  % 'morphological' | 'polynomial'

% Segmentation
config.segmentation.method = 'gmm_v2';     % See table above
config.segmentation.num_components = 2;     % GMM components
config.segmentation.hole_fill_radius = 3;   % v2: dark-spot max diameter [px]

% Physical parameters
config.physical.pixel_size = 'calibrate';   % Interactive calibration or value [mm/px]
config.physical.channel_width_um = 400;     % Known channel width [μm]
config.physical.depth = 100e-6;             % Chip depth [m]
config.physical.dnapl_density = 1630;       % DNAPL density [kg/m³]

% Output
config.visualization.show_figures = true;
config.visualization.save_figures = true;
```

---

## Documentation

| Document | Language | Description |
|----------|----------|-------------|
| [技术报告.md](技术报告.md) | Chinese | Full technical report with algorithms and equations |
| [使用指南.md](使用指南.md) | Chinese | User guide with step-by-step instructions |
| [分割方法技术讨论.md](分割方法技术讨论.md) | Chinese | In-depth segmentation method analysis |
| [ISSUES.md](ISSUES.md) | Chinese | Version history, changelog, known issues |

---

## Citation

If you use this toolbox in your research, please cite:

```bibtex
@software{dnapl_microfluidic_toolbox,
  title  = {DNAPL Microfluidic Image Analysis Toolbox},
  year   = {2026},
  url    = {https://github.com/YOUR_USERNAME/DNAPL-Microfluidic-Analysis}
}
```

---

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

---

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.
