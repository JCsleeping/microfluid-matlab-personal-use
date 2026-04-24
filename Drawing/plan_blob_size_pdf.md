# Plan: Blob Size PDF (Fig. 6)

## Goal

Compute the probability density function (PDF) of residual blob areas for all 9 experimental conditions and export the data for plotting. The final figure will have two panels:

- **(a)** BD at three flow rates (2 / 4 / 6 µL/min)
- **(b)** All three contaminants at Q = 4 µL/min

## Data Source

Each processed run has a `results_*.mat` file in its output folder. The `.mat` file contains per-frame blob properties. We need the **final frame** (residual state) blob data — specifically the `Area` field (in pixels).

### Confirmed output folders

| Contaminant | Q (µL/min) | Output folder |
|---|---|---|
| Dodecane | 2 | `D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\01 databased\04 LANPL\...\output_*` |
| Dodecane | 4 | `...\06 LNAPL-4UL\02 WATER DISPLACE\output_20260309_115339` |
| Dodecane | 6 | TBD — locate in `05 LNAPL-2.5ul` or new folder |
| BD | 2 | `...\08 1-BD 2UL\...\output_*` |
| BD | 4 | `...\07 1-BD 4UL\02 Water Displacement\output_20260310_231726` |
| BD | 6 | `...\09 1-BD 6UL\02 Water Displacement\output_20260313_151504` |
| BO | 2 | `...\10 1-BO 2UL\...\output_*` |
| BO | 4 | `...\11 1-BO 4 UL\02  Water Displacement\output_20260313_193027` |
| BO | 6 | `...\12 1-BO 6 UL\...\output_*` |

## Step 1: Extract residual-frame blob areas

```matlab
% For each condition, load the results .mat file
% Identify the last frame (residual state)
% Extract blob Area values (in pixels)
% Convert to µm² using spatial calibration (cal² where cal ≈ 3.9–4.9 µm/px)

data = load('results_*.mat');
% Inspect the structure to locate:
%   - per-frame blob properties (likely in data.blob_props{end} or similar)
%   - spatial calibration factor (likely in data.config or data.calibration)

last_frame_blobs = data.blob_props{end};  % adjust field name
areas_px = [last_frame_blobs.Area];
cal = data.calibration;  % µm/px
areas_um2 = areas_px * cal^2;
```

> **Note:** The exact field names need to be discovered by inspecting the `.mat` structure. Use `whos('-file', ...)` or `fieldnames()` to explore.

## Step 1.5: MANDATORY — Verify it is the residual frame

> **⚠️ CRITICAL:** The BD-4 axial profile was previously extracted from the wrong frame (initial state instead of residual state). The same mistake MUST NOT happen here. Before proceeding, run the following checks for EVERY condition:

```matlab
% CHECK 1: Compute total Sn from the extracted frame
%   - Sum of all blob areas / total pore area
%   - Compare against Table 2 Sn_res values:
%     Dod-2: 0.334  |  Dod-4: 0.316  |  Dod-6: 0.293
%      BD-2: 0.354  |   BD-4: 0.343  |   BD-6: 0.268
%      BO-2: 0.300  |   BO-4: 0.198  |   BO-6: 0.158
%   - If Sn > 0.5, this is almost certainly NOT the residual frame. STOP.

Sn_check = sum(areas_px) / total_pore_area;
fprintf('Sn from extracted frame = %.3f  (expected Sn_res = %.3f)\n', ...
        Sn_check, expected_Sn_res);
assert(abs(Sn_check - expected_Sn_res) < 0.05, ...
       'ERROR: Sn mismatch — likely wrong frame!');

% CHECK 2: Blob count should match Table 2 values
%   Dod-2: 319  |  Dod-4: 338  |  Dod-6: 387
%    BD-2: 198  |   BD-4: 244  |   BD-6: 265
%    BO-2: 241  |   BO-4: 269  |   BO-6: 302
n_blobs = numel(areas_px);
fprintf('Blob count = %d  (expected ~ %d)\n', n_blobs, expected_blob_count);

% CHECK 3: If the frame index is available, confirm it is the LAST frame
%   e.g., frame_idx == numel(data.frames) or similar
```

**If any check fails, do NOT proceed. Inspect the `.mat` structure to find the correct residual-frame data.**

## Step 2: Compute log-binned PDF

```matlab
% Use logarithmic bins for the area distribution
edges = logspace(log10(min(areas_um2)), log10(max(areas_um2)), 30);
counts = histcounts(areas_um2, edges);
bin_centers = sqrt(edges(1:end-1) .* edges(2:end));  % geometric mean
bin_widths = diff(edges);
pdf_values = counts ./ (sum(counts) .* bin_widths);  % normalise to PDF
```

## Step 3: Export to CSV

For each condition, save a CSV with columns: `bin_center_um2`, `pdf`, `contaminant`, `Q_uLmin`.

```matlab
% Output path
output_dir = 'D:\00 Claude Code\03 会议\03 Result Analysis\01 Draft-Claude';
T = table(bin_centers(:), pdf_values(:), ...
    'VariableNames', {'BinCenter_um2', 'PDF'});
writetable(T, fullfile(output_dir, 'blob_pdf_BD_4uL.csv'));
```

Repeat for all 9 conditions. Alternatively, save all conditions into one combined CSV with extra columns for `Contaminant` and `Q`.

## Step 4: Optional power-law fit

```matlab
% Fit a power law in the intermediate regime (exclude smallest and largest bins)
% log(pdf) = alpha * log(area) + c
idx = 5:20;  % adjust range to intermediate regime
p = polyfit(log10(bin_centers(idx)), log10(pdf_values(idx)), 1);
alpha = p(1);  % expected ~ -1.5 to -2.0
```

## Expected output files

- `blob_pdf_all_conditions.csv` — combined PDF data for all 9 conditions
- (Optional) `blob_pdf_powerlaw_fits.csv` — fit parameters per condition

## Deliverable for plotting

Once the CSV is ready, Fig. 6 can be plotted in Python with:

```python
# Panel (a): BD at 3 flow rates
# Panel (b): 3 contaminants at Q = 4 µL/min
# Both panels: log-log axes, dashed power-law fit lines
```
