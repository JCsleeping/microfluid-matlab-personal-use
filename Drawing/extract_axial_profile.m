%% extract_axial_profile.m
%  Batch-extract axial saturation profiles Sn(x) from all experiments.
%  Re-segments the final frame on-the-fly from TIF data using pipeline config.
%  Output: one CSV per experiment → axial_profile_<LABEL>.csv
%
%  Based on: plan_axial_saturation_profile.md

pipeline_root = 'D:\00 Claude Code\01 MATLAB CODE\01 Microfluid';
addpath(genpath(pipeline_root));

output_csv_dir = 'D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\01 databased';

%% Experiment list
experiments = {
    % Label,           mat_path
    'Dod-2', 'D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\01 databased\14 LNAPL-2UL\02 Water Displacement\output_20260319_203848\results_20260319_213238.mat'
    'Dod-4', 'G:\微流控\06 LNAPL-4UL\02 WATER DISPLACE\output_20260309_115339\results_20260309_124221.mat'
    'Dod-6', 'D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\01 databased\13 LNAPL-6UL\02 Water Displacement\output_20260318_224745\results_20260318_232323.mat'
    'BD-2',  'G:\微流控\08 1-BD 2UL\02\output_20260312_181726\results_20260312_193808.mat'
    'BD-4',  'G:\微流控\07 1-BD 4UL\02 Water Displacement\output_20260310_231726\results_20260311_065711.mat'
    'BD-6',  'G:\微流控\09 1-BD 6UL\02 Water Displacement\output_20260313_151504\results_20260313_163944.mat'
    'BO-2',  'G:\微流控\10 1-BO 2UL\02  Water Displacement\output_20260318_000749\results_20260318_004331.mat'
    'BO-4',  'G:\微流控\11 1-BO 4 UL\02  Water Displacement\output_20260313_193027\results_20260313_201738.mat'
    'BO-6-1','G:\微流控\12 1-BO 6 UL\1\02  Water Displacement\output_20260317_003659\results_20260317_012632.mat'
    'BO-6-2','G:\微流控\12 1-BO 6 UL\2\02  Water Displacement\output_20260316_234803\results_20260317_002816.mat'
};

N_bins = 50;

fprintf('==========================================================\n');
fprintf('  Axial Saturation Profile Extraction\n');
fprintf('==========================================================\n\n');

for e = 1:size(experiments, 1)
    label = experiments{e, 1};
    mat_path = experiments{e, 2};

    fprintf('\n----------------------------------------------------------\n');
    fprintf('  [%d/%d] %s\n', e, size(experiments,1), label);
    fprintf('----------------------------------------------------------\n');

    if ~exist(mat_path, 'file')
        % Chinese path: try loading via temp copy
        try
            tmp_mat = [tempname '.mat'];
            ps_cmd = sprintf('powershell -Command "Copy-Item -LiteralPath ''%s'' -Destination ''%s''"', mat_path, tmp_mat);
            [st, ~] = system(ps_cmd);
            if st ~= 0
                fprintf('  SKIPPED: Cannot access %s\n', mat_path);
                continue;
            end
            loaded = load(tmp_mat, 'config', 'results');
            delete(tmp_mat);
        catch ME
            fprintf('  SKIPPED: %s\n', ME.message);
            continue;
        end
    else
        try
            loaded = load(mat_path, 'config', 'results');
        catch
            tmp_mat = [tempname '.mat'];
            copyfile(mat_path, tmp_mat, 'f');
            loaded = load(tmp_mat, 'config', 'results');
            delete(tmp_mat);
        end
    end

    config = loaded.config;

    %% Get flow_domain
    if isfield(loaded, 'results') && isfield(loaded.results, 'flow_domain')
        flow_domain = loaded.results.flow_domain;
        fprintf('  Flow domain loaded from results.\n');
    else
        fprintf('  Reconstructing flow domain...\n');
        tif_paths_cfg = config.multipage_tif_path;
        if ischar(tif_paths_cfg), tif_paths_cfg = {tif_paths_cfg}; end
        frame_index_fd = struct('tif_path', tif_paths_cfg{1}, 'page', 1);
        rgb_fd = load_frame(1, frame_index_fd);
        [rgb_fd_rot, ~, ~] = rotate_and_crop(rgb_fd, config);
        chip_mask = true(size(rgb_fd_rot,1), size(rgb_fd_rot,2));
        [flow_domain, ~] = extract_flow_domain(rgb_fd_rot, chip_mask);
    end
    [H, W] = size(flow_domain);
    fprintf('  Image size: %d × %d\n', H, W);

    %% Build frame index to find the last frame
    tif_paths = config.multipage_tif_path;
    if ischar(tif_paths), tif_paths = {tif_paths}; end

    frame_index = struct('tif_path', {}, 'page', {});
    for f = 1:numel(tif_paths)
        fp = tif_paths{f};
        try
            info_f = imfinfo(fp);
        catch
            % Try PowerShell copy
            [~, ~, ext] = fileparts(fp);
            tmp_tif = [tempname ext];
            ps_cmd = sprintf('powershell -Command "Copy-Item -LiteralPath ''%s'' -Destination ''%s''"', fp, tmp_tif);
            [st, ~] = system(ps_cmd);
            if st == 0 && exist(tmp_tif, 'file')
                info_f = imfinfo(tmp_tif);
                delete(tmp_tif);
            else
                if exist(tmp_tif, 'file'), delete(tmp_tif); end
                continue;  % skip this file, will try dir fallback below
            end
        end
        for p = 1:numel(info_f)
            idx = numel(frame_index) + 1;
            frame_index(idx).tif_path = fp;
            frame_index(idx).page = p;
        end
    end

    % Fallback: if frame_index is empty, scan TIF directory directly
    if isempty(frame_index)
        fprintf('  Config TIF paths inaccessible. Scanning directory...\n');
        tif_dir = fileparts(fileparts(mat_path));  % up from output_xxx
        d_tifs = dir(fullfile(tif_dir, '*.tif'));
        d_tiffs = dir(fullfile(tif_dir, '*.tiff'));
        d_tifs = [d_tifs; d_tiffs];

        % Match config basenames to filter relevant files
        config_basenames = cell(numel(tif_paths), 1);
        for k = 1:numel(tif_paths)
            [~, bn, ex] = fileparts(tif_paths{k});
            config_basenames{k} = [bn ex];
        end
        keep = false(numel(d_tifs), 1);
        for k = 1:numel(d_tifs)
            keep(k) = any(strcmp(d_tifs(k).name, config_basenames));
        end
        if any(keep)
            d_tifs = d_tifs(keep);
        end

        % Sort naturally
        sort_keys = zeros(numel(d_tifs), 2);
        for k = 1:numel(d_tifs)
            nums = regexp(d_tifs(k).name, '(\d+)', 'tokens');
            if numel(nums) >= 1, sort_keys(k,1) = str2double(nums{1}{1}); end
            if numel(nums) >= 2, sort_keys(k,2) = str2double(nums{end}{1}); end
        end
        [~, si] = sortrows(sort_keys);
        d_tifs = d_tifs(si);

        % For each TIF, estimate page count from file size
        max_bytes = max([d_tifs.bytes]);
        bpp = max_bytes / 72;  % bytes per page estimate
        for f = 1:numel(d_tifs)
            fp = fullfile(tif_dir, d_tifs(f).name);
            np_est = round(d_tifs(f).bytes / bpp);
            if np_est < 1, np_est = 1; end
            for p = 1:np_est
                idx = numel(frame_index) + 1;
                frame_index(idx).tif_path = fp;
                frame_index(idx).page = p;
            end
        end
        fprintf('  Found %d TIF files → %d estimated frames\n', numel(d_tifs), numel(frame_index));
    end

    % Apply config.pages filter
    if isfield(config, 'pages') && ~isempty(config.pages)
        valid_pages = config.pages(config.pages >= 1 & config.pages <= numel(frame_index));
        frame_index = frame_index(valid_pages);
    end

    total_frames = numel(frame_index);
    fprintf('  Total frames: %d\n', total_frames);
    fprintf('  Loading final frame (#%d)...\n', total_frames);

    %% Load and segment the final frame
    rgb_last = load_frame(total_frames, frame_index);
    [rgb_rot, ~, ~] = rotate_and_crop(rgb_last, config);
    [rgb_corr, ~] = correct_illumination(rgb_rot, ...
        config.illumination.method, config.illumination, false);

    % Lock threshold
    is_v2 = endsWith(config.segmentation.method, '_v2');
    config_locked = config;

    % Extract threshold from first frame
    if ~isfield(config.segmentation, 'fixed_threshold') || isempty(config.segmentation.fixed_threshold)
        rgb1 = load_frame(1, frame_index);
        [rgb1_rot, ~, ~] = rotate_and_crop(rgb1, config);
        [rgb1_corr, ~] = correct_illumination(rgb1_rot, ...
            config.illumination.method, config.illumination, false);
        if is_v2
            [~, ~, seg_info] = segment_DNAPL_v2(rgb1_corr, flow_domain, config);
        else
            [~, ~, seg_info] = segment_DNAPL(rgb1_corr, flow_domain, config);
        end
        locked_threshold = seg_info.threshold;
    else
        locked_threshold = config.segmentation.fixed_threshold;
    end
    config_locked.segmentation.fixed_threshold = locked_threshold;

    % Segment final frame
    if is_v2
        [final_mask, ~, ~] = segment_DNAPL_v2(rgb_corr, flow_domain, config_locked);
    else
        [final_mask, ~, ~] = segment_DNAPL(rgb_corr, flow_domain, config_locked);
    end
    final_mask = final_mask & flow_domain;

    Sn_total = sum(final_mask(:)) / sum(flow_domain(:));
    fprintf('  Final Sn = %.3f\n', Sn_total);

    %% Bin along x-axis
    bin_edges = linspace(1, W+1, N_bins+1);
    Sn_x = zeros(N_bins, 1);
    x_centers = zeros(N_bins, 1);
    W_domain = zeros(N_bins, 1);

    for b = 1:N_bins
        col_start = round(bin_edges(b));
        col_end = round(bin_edges(b+1)) - 1;
        col_end = min(col_end, W);

        strip_mask = final_mask(:, col_start:col_end);
        strip_domain = flow_domain(:, col_start:col_end);

        pore_pixels = sum(strip_domain(:));
        napl_pixels = sum(strip_mask(:) & strip_domain(:));

        if pore_pixels > 0
            Sn_x(b) = napl_pixels / pore_pixels;
        end
        x_centers(b) = (col_start + col_end) / 2;
        W_domain(b) = sum(any(strip_domain, 2));
    end

    % Normalise x
    x_norm = (x_centers - min(x_centers)) / (max(x_centers) - min(x_centers));

    %% Export CSV
    T = table(x_norm, Sn_x, W_domain, ...
        'VariableNames', {'x_norm', 'Sn_x', 'W_domain_px'});

    csv_path = fullfile(output_csv_dir, sprintf('axial_profile_%s.csv', label));
    writetable(T, csv_path);
    fprintf('  Saved: %s\n', csv_path);
end

fprintf('\n==========================================================\n');
fprintf('  All axial profiles extracted.\n');
fprintf('==========================================================\n');
