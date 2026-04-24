# Plan: Extract Axial Saturation Profile Sn(x) from results_*.mat

## Goal

From each experiment's `results_*.mat` file, extract the **final-frame binary mask** and compute a one-dimensional residual saturation profile $S_n(x)$ along the flow direction. Export as CSV for Python plotting.

## Data Locations

| Label | results_*.mat path |
|---|---|
| Dod-2 | `D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\01 databased\14 LNAPL-2UL\output_*\results_*.mat` |
| Dod-4 | `G:\微流控\06 LNAPL-4UL\02 Water Displacement\output_*\results_*.mat` |
| Dod-6 | `G:\微流控\13 LNAPL-6UL\02 Water Displacement\output_*\results_*.mat` |
| BD-2 | `G:\微流控\08 1-BD 2UL\02 Water Displacement\output_*\results_*.mat` |
| BD-4 | `G:\微流控\07 1-BD 4UL\02 Water Displacement\output_*\results_*.mat` |
| BD-6 | `G:\微流控\09 1-BD 6UL\02 Water Displacement\output_*\results_*.mat` |
| BO-2 | `G:\微流控\10 1-BO 2UL\02 Water Displacement\output_*\results_*.mat` |
| BO-4 | `G:\微流控\11 1-BO 4 UL\02 Water Displacement\output_*\results_*.mat` |
| BO-6 | `G:\微流控\12 1-BO 6 UL\1\02 Water Displacement\output_*\results_*.mat` |

> [!NOTE]
> Each `output_*` folder contains one `results_*.mat` file. Use `dir()` or `glob` to find it.

## What's Inside results_*.mat

The `.mat` file is saved by the MATLAB microfluidic analysis pipeline. Expected variables:

- **`masks_stack`** or **`all_masks`**: 3D logical array `(H × W × N_frames)` — binary segmentation masks for each frame. `true` = NAPL pixel, `false` = water/grain.
- **`chip_mask`** or **`domain_mask`**: 2D logical array `(H × W)` — the pore-space domain (diamond chip geometry). `true` = pore space, `false` = solid grain or outside.
- **`config`** or **`params`**: struct with experiment metadata (pixel size, etc.)

> [!IMPORTANT]
> Variable names may differ. Use `whos('-file', matPath)` to list all variables first. Look for the largest 3D logical/uint8 array (that's the masks stack) and a 2D logical array of similar H×W dimensions (that's the domain mask).

## Algorithm

### Step 1: Load final-frame mask and domain mask

```matlab
data = load(matPath);
% Find the mask stack (largest 3D variable)
final_mask = data.masks_stack(:,:,end);  % last frame = residual state
domain_mask = data.chip_mask;             % or domain_mask
```

### Step 2: Bin along x-axis (flow direction = columns)

Divide the image width into `N_bins = 50` vertical strips:

```matlab
N_bins = 50;
[H, W] = size(final_mask);
bin_edges = linspace(1, W+1, N_bins+1);

Sn_x = zeros(N_bins, 1);
x_centers = zeros(N_bins, 1);

for b = 1:N_bins
    col_start = round(bin_edges(b));
    col_end = round(bin_edges(b+1)) - 1;
    
    % Extract the vertical strip
    strip_mask = final_mask(:, col_start:col_end);
    strip_domain = domain_mask(:, col_start:col_end);
    
    % Sn = NAPL pixels / pore-space pixels in this strip
    pore_pixels = sum(strip_domain(:));
    napl_pixels = sum(strip_mask(:) & strip_domain(:));
    
    if pore_pixels > 0
        Sn_x(b) = napl_pixels / pore_pixels;
    end
    x_centers(b) = (col_start + col_end) / 2;
end
```

### Step 3: Convert x from pixels to normalised position

```matlab
x_norm = (x_centers - min(x_centers)) / (max(x_centers) - min(x_centers));
% x_norm ranges from 0 (inlet) to 1 (outlet)
```

### Step 4: Also extract domain width profile

```matlab
% Channel width at each x-bin (for diamond chip outline overlay)
W_domain = zeros(N_bins, 1);
for b = 1:N_bins
    col_start = round(bin_edges(b));
    col_end = round(bin_edges(b+1)) - 1;
    strip_domain = domain_mask(:, col_start:col_end);
    W_domain(b) = sum(any(strip_domain, 2));  % number of rows with pore space
end
```

### Step 5: Export to CSV

```matlab
% Save one CSV per experiment
T = table(x_norm, Sn_x, W_domain, ...
    'VariableNames', {'x_norm', 'Sn_x', 'W_domain_px'});
writetable(T, outputCsvPath);
```

## Output

For each experiment, save CSV to: `D:\00 Claude Code\03 会议\03 Result Analysis\01 Draft-Claude\axial_profile_<LABEL>.csv`

Where `<LABEL>` is: `Dod-2`, `Dod-4`, `Dod-6`, `BD-2`, `BD-4`, `BD-6`, `BO-2`, `BO-4`, `BO-6`

CSV format:

| x_norm | Sn_x | W_domain_px |
|---|---|---|
| 0.01 | 0.05 | 120 |
| 0.03 | 0.15 | 180 |
| ... | ... | ... |

## Expected Result

The Sn(x) curve should show a **dome shape**: low near inlet (x≈0) and outlet (x≈1), peaking near x≈0.5 where the diamond chip is widest. The `W_domain_px` column will confirm this geometry.
