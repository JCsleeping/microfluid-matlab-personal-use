%% fix_BD4_axial.m
%  Re-extract BD-4 axial saturation profile from the LAST frame.
%  The previous version was extracted from the wrong frame.
%
%  Output: overwrites axial_profile_BD-4.csv

pipeline_root = 'D:\00 Claude Code\01 MATLAB CODE\01 Microfluid';
addpath(genpath(pipeline_root));

mat_path = 'G:\微流控\07 1-BD 4UL\02 Water Displacement\output_20260310_231726\results_20260311_065711.mat';
output_csv = 'D:\00 Claude Code\03 会议\03 Result Analysis\01 Draft-Claude\axial_profile_BD-4.csv';
N_bins = 50;

fprintf('==========================================================\n');
fprintf('  Fix BD-4 Axial Saturation Profile\n');
fprintf('==========================================================\n\n');

%% Load results
fprintf('  Loading results...\n');
try
    loaded = load(mat_path, 'config', 'results');
catch
    % Chinese path fallback: copy to temp
    tmp_mat = [tempname '.mat'];
    ps_cmd = sprintf('powershell -Command "Copy-Item -LiteralPath ''%s'' -Destination ''%s''"', mat_path, tmp_mat);
    [st, ~] = system(ps_cmd);
    if st ~= 0
        error('Cannot access %s', mat_path);
    end
    loaded = load(tmp_mat, 'config', 'results');
    delete(tmp_mat);
end
config = loaded.config;

%% Get flow domain
if isfield(loaded, 'results') && isfield(loaded.results, 'flow_domain')
    flow_domain = loaded.results.flow_domain;
    fprintf('  Flow domain loaded.\n');
else
    error('No flow_domain in results.');
end
[H, W] = size(flow_domain);
fprintf('  Image size: %d × %d\n', H, W);

%% Build frame index
tif_paths = config.multipage_tif_path;
if ischar(tif_paths), tif_paths = {tif_paths}; end

frame_index = struct('tif_path', {}, 'page', {});
for f = 1:numel(tif_paths)
    fp = tif_paths{f};
    try
        info_f = imfinfo(fp);
    catch
        [~, ~, ext] = fileparts(fp);
        tmp_tif = [tempname ext];
        ps_cmd = sprintf('powershell -Command "Copy-Item -LiteralPath ''%s'' -Destination ''%s''"', fp, tmp_tif);
        [st, ~] = system(ps_cmd);
        if st == 0 && exist(tmp_tif, 'file')
            info_f = imfinfo(tmp_tif);
            delete(tmp_tif);
        else
            if exist(tmp_tif, 'file'), delete(tmp_tif); end
            continue;
        end
    end
    for p = 1:numel(info_f)
        idx = numel(frame_index) + 1;
        frame_index(idx).tif_path = fp;
        frame_index(idx).page = p;
    end
end

% Dir fallback
if isempty(frame_index)
    fprintf('  Config paths inaccessible. Scanning directory...\n');
    tif_dir = fileparts(fileparts(mat_path));
    d_tifs = dir(fullfile(tif_dir, '*.tif'));
    d_tiffs = dir(fullfile(tif_dir, '*.tiff'));
    d_tifs = [d_tifs; d_tiffs];

    config_basenames = cell(numel(tif_paths), 1);
    for k = 1:numel(tif_paths)
        [~, bn, ex] = fileparts(tif_paths{k});
        config_basenames{k} = [bn ex];
    end
    keep = false(numel(d_tifs), 1);
    for k = 1:numel(d_tifs)
        keep(k) = any(strcmp(d_tifs(k).name, config_basenames));
    end
    if any(keep), d_tifs = d_tifs(keep); end

    sort_keys = zeros(numel(d_tifs), 2);
    for k = 1:numel(d_tifs)
        nums = regexp(d_tifs(k).name, '(\d+)', 'tokens');
        if numel(nums) >= 1, sort_keys(k,1) = str2double(nums{1}{1}); end
        if numel(nums) >= 2, sort_keys(k,2) = str2double(nums{end}{1}); end
    end
    [~, si] = sortrows(sort_keys);
    d_tifs = d_tifs(si);

    max_bytes = max([d_tifs.bytes]);
    bpp = max_bytes / 72;
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

% Apply pages filter
if isfield(config, 'pages') && ~isempty(config.pages)
    valid_pages = config.pages(config.pages >= 1 & config.pages <= numel(frame_index));
    frame_index = frame_index(valid_pages);
end

total_frames = numel(frame_index);
fprintf('  Total frames: %d\n', total_frames);
fprintf('  Loading LAST frame (#%d)...\n', total_frames);

%% Segment the last frame
rgb_last = load_frame(total_frames, frame_index);
[rgb_rot, ~, ~] = rotate_and_crop(rgb_last, config);
[rgb_corr, ~] = correct_illumination(rgb_rot, ...
    config.illumination.method, config.illumination, false);

is_v2 = endsWith(config.segmentation.method, '_v2');
config_locked = config;

% Get threshold from first frame
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
    config_locked.segmentation.fixed_threshold = seg_info.threshold;
else
    config_locked.segmentation.fixed_threshold = config.segmentation.fixed_threshold;
end

if is_v2
    [final_mask, ~, ~] = segment_DNAPL_v2(rgb_corr, flow_domain, config_locked);
else
    [final_mask, ~, ~] = segment_DNAPL(rgb_corr, flow_domain, config_locked);
end
final_mask = final_mask & flow_domain;

Sn_total = sum(final_mask(:)) / sum(flow_domain(:));
fprintf('\n  *** VERIFICATION ***\n');
fprintf('  Final Sn = %.3f  (expected Sn_res ≈ 0.343)\n', Sn_total);
if Sn_total > 0.5
    error('Sn > 0.5 — this is NOT the residual frame!');
end

%% Bin along x-axis
bin_edges = linspace(1, W+1, N_bins+1);
Sn_x = zeros(N_bins, 1);
x_centers = zeros(N_bins, 1);
W_domain = zeros(N_bins, 1);

for b = 1:N_bins
    col_start = round(bin_edges(b));
    col_end = min(round(bin_edges(b+1)) - 1, W);
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

x_norm = (x_centers - min(x_centers)) / (max(x_centers) - min(x_centers));

%% Save
T = table(x_norm, Sn_x, W_domain, ...
    'VariableNames', {'x_norm', 'Sn_x', 'W_domain_px'});
writetable(T, output_csv);
fprintf('  Saved: %s\n', output_csv);

% Also copy to 01 databased
writetable(T, fullfile('D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\01 databased', 'axial_profile_BD-4.csv'));
fprintf('  Also saved to 01 databased\n');

fprintf('\n  Sn_x range: [%.3f, %.3f]\n', min(Sn_x), max(Sn_x));
fprintf('  Weighted mean Sn: %.3f\n', sum(Sn_x .* W_domain) / sum(W_domain));
fprintf('==========================================================\n');
