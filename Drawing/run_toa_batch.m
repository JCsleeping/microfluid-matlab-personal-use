% RUN_TOA_BATCH  Batch-generate Time-of-Arrival maps for all 9 experiments.
%
%   Edit the experiment table below, then run this script.
%   Output figures go to: D:\00 Claude Code\03 会议\03 Result Analysis\01 Draft-Claude\figures\
%
%   Prerequisites: Each experiment must have a results_*.mat with 'config'.

clear; clc;
fprintf('==========================================================\n');
fprintf('  Batch ToA Map Generator\n');
fprintf('==========================================================\n\n');

pipeline_root = 'D:\00 Claude Code\01 MATLAB CODE\01 Microfluid';
addpath(genpath(pipeline_root));

output_dir = 'D:\00 Claude Code\03 会议\03 Result Analysis\01 Draft-Claude\figures';
if ~isfolder(output_dir), mkdir(output_dir); end

%% Experiment Table
%  Format: { label, mat_path, pixel_size_um }
%  Fill in the mat_paths for each experiment.
%  Use extract_pixel_sizes_v2() to find the mat_paths and pixel sizes.

experiments = {
%   Label           MAT file path                                                                                                pixel_size_um
    'Dodecane-2.5', 'G:\微流控\05 LNAPL-2.5ul\02 water displace\output_20260319_163747\results_20260319_174825.mat',              3.92
    'Dodecane-4',   'G:\微流控\06 LNAPL-4UL\02 WATER DISPLACE\output_20260309_115339\results_20260309_124221.mat',                4.25
    'Dodecane-6',   'D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\01 databased\13 LNAPL-6UL\02 Water Displacement\output_20260318_224745\results_20260318_232323.mat', 4.25
    'BD-2',         'G:\微流控\08 1-BD 2UL\02\output_20260312_181726\results_20260312_193808.mat',                                4.01
    'BD-4',         'G:\微流控\07 1-BD 4UL\02 Water Displacement\output_20260310_231726\results_20260311_065711.mat',              4.28
    'BD-6',         'G:\微流控\09 1-BD 6UL\02 Water Displacement\output_20260313_151504\results_20260313_163944.mat',              4.00
    'BO-2',         'G:\微流控\10 1-BO 2UL\02  Water Displacement\output_20260318_000749\results_20260318_004331.mat',             4.88
    'BO-4',         'G:\微流控\11 1-BO 4 UL\02  Water Displacement\output_20260313_193027\results_20260313_201738.mat',            4.16
    'BO-6',         'G:\微流控\12 1-BO 6 UL\1\02  Water Displacement\output_20260317_003659\results_20260317_012632.mat',          4.25
};

%% Run
n = size(experiments, 1);
results_summary = cell(n, 3);  % {label, status, time_s}

for i = 1:n
    lbl  = experiments{i, 1};
    matf = experiments{i, 2};
    px   = experiments{i, 3};

    fprintf('\n\n========== [%d/%d] %s ==========\n', i, n, lbl);

    if ~isfile(matf)
        fprintf('  ⚠ MAT file not found: %s\n', matf);
        fprintf('    Skipping...\n');
        results_summary{i,1} = lbl;
        results_summary{i,2} = 'SKIPPED (no MAT)';
        results_summary{i,3} = 0;
        continue;
    end

    t0 = tic;
    try
        generate_toa_map(matf, px, lbl, output_dir);
        results_summary{i,1} = lbl;
        results_summary{i,2} = 'OK';
        results_summary{i,3} = toc(t0);
    catch ME
        fprintf('  ✗ ERROR: %s\n', ME.message);
        results_summary{i,1} = lbl;
        results_summary{i,2} = ['ERROR: ' ME.message];
        results_summary{i,3} = toc(t0);
    end
end

%% Summary
fprintf('\n\n==========================================================\n');
fprintf('  BATCH SUMMARY\n');
fprintf('==========================================================\n');
for i = 1:n
    fprintf('  %-15s  %-10s  (%.0f s)\n', results_summary{i,:});
end
fprintf('==========================================================\n');
fprintf('  Output: %s\n', output_dir);
fprintf('==========================================================\n');
