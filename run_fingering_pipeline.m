% RUN_FINGERING_PIPELINE  Top-level script for fingering analysis.
%
%   One-stop entry point for running fingering analysis on DNAPL water-drive
%   experiments. Supports three modes:
%
%     Mode 1 — Default:    Analyze the last pipeline result (results.dnapl_mask)
%     Mode 2 — Single:     Analyze a specific frame from the TIF stack
%     Mode 3 — Continuous: Analyze all TIF frames continuously (stride-based)
%
%   Usage:
%     1. Edit the USER SETTINGS section below
%     2. Run this script in MATLAB:  >> run_fingering_pipeline
%
%   Prerequisites:
%     - main_DNAPL_pipeline must have been run and results saved
%     - OR provide a .mat file path containing results and config
%
%   See also: run_fingering_analysis, run_fingering_timeseries

clear;
clc;
fprintf('==========================================================\n');
fprintf('   Fingering Analysis Pipeline\n');
fprintf('==========================================================\n\n');

%% ====================================================================
%  USER SETTINGS — 修改这里
%  ====================================================================

% --- 数据来源 ---
% 方式A: 从已有的 pipeline 输出 .mat 文件加载
mat_file = 'D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\01 databased\06 LNAPL-4UL\01 NAPL WATER\output_20260308_151758\results_20260308_154658.mat';  % ← 填 .mat 路径，例如 'D:\...\output_xxx\pipeline_results.mat'
%   ↑ 如果为空，则重新运行 config_pipeline() + main_DNAPL_pipeline()

% 方式B: 直接运行 pipeline（mat_file 为空时生效）

% --- 分析模式 ---
analysis_mode = 'continuous';  % 'default' | 'single' | 'continuous'
%   ↑ 'default':    使用 pipeline 保存的 results.dnapl_mask（单帧）
%   ↑ 'single':     加载指定帧分析（下面设 single_frame_idx）
%   ↑ 'continuous': 扫描全部 TIF 页做连续分析（最重要的模式）

% --- 单帧模式设置 ---
single_frame_idx = 500;        % analysis_mode='single' 时的帧号

% --- 连续模式设置 ---
stride = 1;          % 步长：1 = 每帧都分析, 5 = 每5帧分析一次, 10 = 每10帧
%   ↑ 大数据集建议先用 stride=10 快速预览，确认后再用 stride=1 全量分析
%   ↑ 500 帧 stride=1 → 500 次分析；stride=5 → 100 次
%   ↑ 每帧分析耗时约 5-15 秒（取决于图像大小和柱子数量）

manual_frames = [];  % 手动指定帧列表，例如 [1, 50, 100, 200, 300, 500]
%   ↑ 为空时按 stride 扫描全部帧
%   ↑ 不为空时忽略 stride

% --- 指进分析参数 ---
fconfig.flow_direction = 'left_to_right';  % 流动方向
fconfig.inlet_side     = 'left';           % 入口侧
fconfig.min_finger_pore_factor   = 2.0;    % 最短指进 = N × 孔径
fconfig.min_finger_advance_factor = 1.5;   % 指进前进量阈值

%% ====================================================================
%  STEP 1: Load or Run Pipeline
%  ====================================================================
fprintf('STEP 1: Loading data\n');
fprintf('--------------------------------------------------------\n');

if ~isempty(mat_file) && isfile(mat_file)
    fprintf('  Loading from: %s\n', mat_file);
    loaded = load(mat_file);

    if isfield(loaded, 'results')
        results = loaded.results;
    else
        fn = fieldnames(loaded);
        results = loaded.(fn{1});
    end

    if isfield(loaded, 'config')
        config = loaded.config;
        fprintf('  Config loaded from .mat\n');
    else
        fprintf('  WARNING: config not saved in .mat (old format).\n');
        fprintf('           Re-running config_pipeline() and patching from results...\n');
        config = config_pipeline();
        % Patch critical interactive params from results.preprocessing
        if isfield(results, 'preprocessing')
            if isfield(results.preprocessing, 'rotation_angle')
                config.preprocess.rotation_angle = results.preprocessing.rotation_angle;
            end
            if isfield(results.preprocessing, 'crop_rect')
                config.preprocess.manual_crop_rect = results.preprocessing.crop_rect;
            end
        end
        % Disable interactive modes for batch
        if ischar(config.preprocess.manual_crop_rect) && ...
                strcmpi(config.preprocess.manual_crop_rect, 'interactive')
            config.preprocess.manual_crop_rect = [];  % auto-detect
            fprintf('  Disabled interactive crop (set to auto-detect).\n');
        end
        if ischar(config.physical.pixel_size) && ...
                strcmpi(config.physical.pixel_size, 'calibrate')
            config.physical.pixel_size = 1e-6;  % safe fallback
            fprintf('  Disabled interactive calibration (using 1e-6 m/px fallback).\n');
        end
    end
else
    fprintf('  No .mat file specified. Running full pipeline...\n\n');
    config = config_pipeline();
    results = main_DNAPL_pipeline(config);
end

fprintf('  Data loaded.\n');
fprintf('  Flow domain: [%d × %d]\n', size(results.flow_domain, 1), size(results.flow_domain, 2));
fprintf('  DNAPL pixels: %d\n\n', sum(results.dnapl_mask(:)));

%% ====================================================================
%  STEP 2: Configure mode
%  ====================================================================
fprintf('STEP 2: Configuring analysis\n');
fprintf('--------------------------------------------------------\n');

switch lower(analysis_mode)
    case 'default'
        fprintf('  Mode: DEFAULT — single frame from pipeline\n\n');
        fconfig.frame_idx = [];

    case 'single'
        fprintf('  Mode: SINGLE — frame %d\n\n', single_frame_idx);
        fconfig.frame_idx = single_frame_idx;

    case 'continuous'
        fprintf('  Mode: CONTINUOUS TIF ANALYSIS\n');
        fconfig.stride = stride;

        if ~isempty(manual_frames)
            fconfig.frame_idx = manual_frames;
            fprintf('  Manual selection: %d frames\n', numel(manual_frames));
        else
            % 'all' → run_fingering_timeseries scans all TIF pages
            fconfig.frame_idx = 'all';
            fprintf('  Scanning ALL TIF pages, stride = %d\n', stride);

            % Estimate job size
            tif_paths = config.multipage_tif_path;
            if ischar(tif_paths), tif_paths = {tif_paths}; end
            total = 0;
            for f = 1:numel(tif_paths)
                info_f = imfinfo(tif_paths{f});
                total = total + numel(info_f);
            end
            n_to_analyze = numel(1:stride:total);
            fprintf('  Total pages: %d → %d frames to analyze\n', total, n_to_analyze);
            fprintf('  Estimated time: %.0f – %.0f min (at 5–15 s/frame)\n\n', ...
                n_to_analyze * 5 / 60, n_to_analyze * 15 / 60);
        end

    otherwise
        error('run_fingering_pipeline:badMode', ...
            'Unknown analysis_mode "%s". Use ''default'', ''single'', or ''continuous''.', ...
            analysis_mode);
end

%% ====================================================================
%  STEP 3: Run Fingering Analysis
%  ====================================================================
fprintf('STEP 3: Running fingering analysis\n');
fprintf('========================================================\n');

fres = run_fingering_analysis(results, config, fconfig);

%% ====================================================================
%  STEP 4: Save workspace
%  ====================================================================
fprintf('\nSTEP 4: Saving workspace\n');
fprintf('--------------------------------------------------------\n');

if isfield(config, 'output_path') && isfolder(config.output_path)
    qc_dir = fullfile(config.output_path, 'fingering_qc');
    if ~isfolder(qc_dir), mkdir(qc_dir); end

    save_path = fullfile(qc_dir, 'fingering_workspace.mat');
    save(save_path, 'fres', 'fconfig', 'config', '-v7.3');
    fprintf('  Workspace saved to: %s\n', save_path);
end

%% ====================================================================
%  Summary
%  ====================================================================
fprintf('\n==========================================================\n');
fprintf('  Fingering Pipeline Complete\n');
fprintf('  Mode: %s\n', analysis_mode);

switch lower(analysis_mode)
    case 'default'
        if isfield(fres, 'napl') && isfield(fres.napl, 'residual')
            fprintf('  Sr = %.4f, Nc = %d\n', fres.napl.residual.Sr, fres.napl.residual.Nc);
        end
        if isfield(fres, 'water') && isfield(fres.water, 'fingers')
            fprintf('  Fingers: %d, tau = %.3f\n', ...
                fres.water.fingers.num_fingers, fres.water.tortuosity.tau_backbone);
        end

    case 'single'
        fprintf('  Frame: %d\n', single_frame_idx);
        if isfield(fres, 'napl') && isfield(fres.napl, 'residual')
            fprintf('  Sr = %.4f, Nc = %d\n', fres.napl.residual.Sr, fres.napl.residual.Nc);
        end

    case 'continuous'
        fprintf('  Frames analyzed: %d / %d\n', ...
            numel(fres.frame_indices), fres.total_frames_in_tif);
        fprintf('  Stride: %d\n', fres.stride);
        if isfield(fres, 'stats') && isfield(fres.stats, 'Sr')
            fprintf('  Sr: %.4f → %.4f (%.1f%% removed)\n', ...
                fres.stats.Sr.start, fres.stats.Sr.final, ...
                100 * (1 - fres.stats.Sr.final / max(fres.stats.Sr.start, eps)));
        end
        if isfield(fres, 'stats') && isfield(fres.stats, 'fingers')
            fprintf('  Fingers: %d – %d (mean %.1f)\n', ...
                fres.stats.fingers.min, fres.stats.fingers.max, ...
                fres.stats.fingers.mean);
        end
        if ~isempty(fres.failed_frames)
            fprintf('  Failed: %d frames\n', numel(fres.failed_frames));
        end
end

if isfield(config, 'output_path')
    fprintf('  Output: %s\n', config.output_path);
end
fprintf('==========================================================\n');
