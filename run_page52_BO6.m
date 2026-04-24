% RUN_PAGE52_BO6  Run full pipeline on page 52 of "02 water 1 seconds_7.tif"
%   from: G:\微流控\12 1-BO 6 UL\2\02  Water Displacement
%
%   Since the existing results .mat is corrupted, this script builds a
%   fresh config targeting ONLY page 52 of that single TIF file.
%   Interactive prompts (crop ROI, pixel calibration) will appear on first run.
%
%   After first run, copy the printed crop_rect and pixel_size values
%   back into this script to skip interactive steps on re-runs.
%
%   Usage:  >> run_page52_BO6

clear; clc;

%% ====================================================================
%  SETTINGS
%  ====================================================================
target_tif  = 'G:\微流控\12 1-BO 6 UL\2\02  Water Displacement\02 water 1 seconds_7.tif';
target_page = 52;

%% ====================================================================
%  STEP 1: Build config from scratch
%  ====================================================================
fprintf('==========================================================\n');
fprintf('   Re-run Pipeline: Page %d\n', target_page);
fprintf('   TIF: %s\n', target_tif);
fprintf('==========================================================\n\n');

% Verify TIF has enough pages
info = imfinfo(target_tif);
n_pages = numel(info);
fprintf('TIF has %d pages\n', n_pages);
if target_page > n_pages
    error('run_page52:badPage', ...
        'Page %d requested but TIF only has %d pages.', target_page, n_pages);
end

% Build config — point to only this single TIF
config = config_pipeline();

% Override data path and TIF list — ONLY this one file
config.data_path = fileparts(target_tif);
config.multipage_tif_path = {target_tif};

% Process only page 52
config.pages = [target_page];

% Output to a new timestamped folder
config.output_path = fullfile(config.data_path, ...
    sprintf('output_page%d_%s', target_page, datestr(now, 'yyyymmdd_HHMMSS')));

% Time config for single frame
config.time_interval = 1;
config.time_vector   = [];

% No checkpoint needed for 1 frame
config.output.checkpoint = false;

% Show figures
config.visualization.show_figures = true;
config.visualization.save_figures = true;

fprintf('\n  Target page: %d\n', target_page);
fprintf('  Output:      %s\n\n', config.output_path);

%% ====================================================================
%  STEP 2: Preview the target page
%  ====================================================================
fprintf('Loading page %d for preview...\n', target_page);
img_preview = imread(target_tif, target_page);
figure('Name', sprintf('Preview: Page %d', target_page), ...
    'Position', [100 100 800 600]);
imshow(img_preview);
title(sprintf('Page %d — 02 water 1 seconds\\_7.tif', target_page), ...
    'FontSize', 13);

%% ====================================================================
%  STEP 3: Run full pipeline
%  ====================================================================
fprintf('\n>>> Running main_DNAPL_pipeline on page %d <<<\n\n', target_page);
results = main_DNAPL_pipeline(config);

%% ====================================================================
%  Summary
%  ====================================================================
fprintf('\n==========================================================\n');
fprintf('  Pipeline completed for page %d\n', target_page);
fprintf('  Sn = %.4f\n', results.saturation.Sn);
fprintf('  Blobs: %d\n', results.blobs.num_blobs);
fprintf('  Output: %s\n', config.output_path);
fprintf('==========================================================\n');

% Print config values for re-use (skip interactive next time)
fprintf('\n--- Copy these values to skip interactive prompts next time ---\n');
if isfield(results, 'preprocessing')
    if isfield(results.preprocessing, 'crop_rect')
        cr = results.preprocessing.crop_rect;
        fprintf('config.preprocess.manual_crop_rect = [%d, %d, %d, %d];\n', cr);
    end
    if isfield(results.preprocessing, 'rotation_angle')
        fprintf('config.preprocess.rotation_angle = %.2f;\n', results.preprocessing.rotation_angle);
    end
end
fprintf('config.physical.pixel_size = %.6e;\n', config.physical.pixel_size);
if isnumeric(config.illumination.kernel_size)
    fprintf('config.illumination.kernel_size = %d;\n', config.illumination.kernel_size);
end
