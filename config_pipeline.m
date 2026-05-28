function config = config_pipeline(varargin)
% CONFIG_PIPELINE  Return default configuration for the DNAPL analysis pipeline.
%
%   config = config_pipeline()
%   config = config_pipeline('param1', value1, 'param2', value2, ...)
%
%   Override defaults by passing name-value pairs. Nested fields use dot
%   notation strings, e.g. config_pipeline('physical.pixel_size', 5e-6).

    %% Ensure project code is on the MATLAB path
    this_dir = fileparts(mfilename('fullpath'));
    add_project_paths(this_dir);

    %% User settings

    % --- Data path ---
    config.data_path = 'G:\Microfluid\18 1-BO 4UL 5% TWEEM 80 4UL WATER DISPLACE\01 Tween 80';

    % --- Input files ---
    % Leave empty here. After user overrides are applied, the final
    % data_path is scanned unless multipage_tif_path was explicitly supplied.
    config.multipage_tif_path = {};

    % --- Pages ---
    % [] = all pages; otherwise use global page indices after all TIF files
    % are concatenated in chronological file order.
    config.pages = [];

    % --- Physical parameters ---
    config.physical.pixel_size       = 'calibrate';
    config.physical.channel_width_um = 400;
    config.physical.diffusion_coeff  = 0.43e-9;
    config.physical.solubility       = 4;
    config.physical.dnapl_density    = 1038;
    config.physical.depth            = 20e-6;

    % --- Time ---
    config.time_interval = 1;
    config.time_vector = [];

    % --- Rotation and crop ---
    config.preprocess.rotation_angle = 0;
    config.preprocess.manual_crop_rect = 'interactive';

    % --- Flow-domain reference ---
    config.flow_domain_frame = 1;
    config.flow_domain_image = 'D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\01 databased\00 Saturation\1BD NAPL SATURATION3_1.tif';
    config.flow_domain_image_page = 1;
    config.flow_domain_crop_rect = [];

    %% Advanced settings

    % --- Input mode ---
    config.input_mode = 'multipage_tif';
    config.image_dir = '';
    config.image_files = {};
    config.input.is_linear_rgb = false;  % 0 = sRGB/default, 1 = Linear RGB input

    % --- Output path ---
    default_output_name = ['output_' datestr(now, 'yyyymmdd_HHMMSS')];
    config.output_path = '';

    % --- Preprocessing ---
    config.preprocess.auto_rotate = false;
    config.illumination.method = 'morphological';
    config.illumination.kernel_size = 'interactive';
    config.registration.method = 'none';
    config.registration.transform = 'similarity';

    % --- Segmentation ---
    config.segmentation.color_space = 'Lab';
    config.segmentation.target_channel = 'a';
    config.segmentation.method = 'gmm_v2';
    config.segmentation.num_components = 2;
    config.segmentation.min_blob_area = 10;
    config.segmentation.morph_radius = 2;
    config.segmentation.hole_fill_radius = 3;

    % --- Interface analysis ---
    config.interface.solid_dilation = 1;

    % --- Residual structure metrics ---
    config.architecture.pool_like.max_blob_fraction_min = 0.50;
    config.architecture.pool_like.num_blobs_max = 10;
    config.architecture.pool_like.a_i_2D_max = 3.0e4;
    config.architecture.ganglia_rich.max_blob_fraction_max = 0.30;
    config.architecture.ganglia_rich.num_blobs_min = 25;
    config.architecture.ganglia_rich.a_i_2D_min = 6.0e4;

    % --- Per-blob geometry computation ---
    % Default stable mode avoids per-blob full-frame hole classification.
    % Set geometry.mode='roi' for reusable ROI-local domain-aware hole
    % classification after synthetic validation.
    config.geometry.mode = 'core_only';
    config.geometry.object_connectivity = 8;
    config.geometry.schema_version = 'geometry_v2_core_only';
    config.geometry.include_heavy_shape_props = true;
    config.geometry.roi_pad = 1;
    config.geometry.max_roi_area_fraction = 0.25;
    config.geometry.max_roi_pixels = 2e6;

    % --- Mass transfer model ---
    config.physical.sherwood_correlation = 'powers';

    % --- Visualization ---
    config.visualization.show_figures = false;
    config.visualization.save_figures = false;
    config.visualization.figure_format = 'png';
    config.visualization.colormap_blobs = 'jet';

    % --- Parallel processing ---
    config.parallel.enabled = false;
    config.parallel.num_workers = 2;
    config.parallel.use_gpu = false;

    % --- Checkpoint / resume / safe output controls ---
    config.output.checkpoint = true;
    config.output.save_interval = 72;
    config.output.save_log = true;
    config.output.save_progress = false;
    config.output.progress_interval = 50;
    config.output.save_heartbeat = true;
    config.output.heartbeat_frame_interval = 10;
    config.output.heartbeat_time_interval_sec = 30;
    config.output.save_blob_detail = true;
    config.output.blob_detail_chunk_size = 100;
    config.output.blob_detail_save_format = 'v7';
    config.output.blob_detail_allow_format_fallback = true;
    config.output.blob_detail_chunk_max_bytes = 512 * 1024^2;
    config.output.max_frames_per_session = inf;

    %% Apply user overrides
    output_path_overridden = has_override(varargin, 'output_path');
    for k = 1:2:numel(varargin)
        field_path = varargin{k};
        value = varargin{k+1};
        config = setfield_nested(config, field_path, value);
    end

    %% Resolve paths after overrides
    if isempty(config.multipage_tif_path)
        config.multipage_tif_path = discover_tif_paths(config.data_path);
    end

    if ~output_path_overridden
        config.output_path = fullfile(config.data_path, default_output_name);
    end

    %% Validate configuration
    config = validate_config(config);
end

% -------------------------------------------------------------------------
function tf = has_override(args, field_name)
    tf = false;
    for idx = 1:2:numel(args)
        if ischar(args{idx}) || isstring(args{idx})
            if strcmp(char(args{idx}), field_name)
                tf = true;
                return;
            end
        end
    end
end

% -------------------------------------------------------------------------
function tif_paths = discover_tif_paths(data_path)
    tif_list = dir(fullfile(data_path, '*.tif'));
    if isempty(tif_list)
        error('config_pipeline:noTIF', ...
            ['No .tif files found in:\n  %s\n' ...
             'Please set config.data_path to the folder containing your TIF files.\n' ...
             'Example: config.data_path = ''...\\01 databased\\01 Pretest 5\\03 Water Dis'';'], ...
            data_path);
    end

    [~, date_order] = sort([tif_list.datenum]);
    tif_list = tif_list(date_order);
    tif_paths = arrayfun(@(f) fullfile(f.folder, f.name), ...
        tif_list, 'UniformOutput', false);
end

% -------------------------------------------------------------------------
function s = setfield_nested(s, field_path, value)
    tokens = strsplit(field_path, '.');
    if numel(tokens) == 1
        s.(tokens{1}) = value;
    else
        sub = s.(tokens{1});
        sub = setfield_nested(sub, strjoin(tokens(2:end), '.'), value);
        s.(tokens{1}) = sub;
    end
end

% -------------------------------------------------------------------------
function add_project_paths(project_root)
    remove_worktree_paths(project_root);

    parts = strsplit(genpath(project_root), pathsep);
    worktree_root = normalize_path(fullfile(project_root, '.worktrees'));
    keep = {};
    for i = 1:numel(parts)
        p = parts{i};
        if isempty(p)
            continue;
        end
        if startsWith(normalize_path(p), worktree_root)
            continue;
        end
        keep{end+1} = p; %#ok<AGROW>
    end

    if ~isempty(keep)
        addpath(strjoin(keep, pathsep));
    end
end

% -------------------------------------------------------------------------
function remove_worktree_paths(project_root)
    worktree_root = normalize_path(fullfile(project_root, '.worktrees'));
    parts = strsplit(path, pathsep);
    for i = 1:numel(parts)
        p = parts{i};
        if isempty(p)
            continue;
        end
        if startsWith(normalize_path(p), worktree_root)
            rmpath(p);
        end
    end
end

% -------------------------------------------------------------------------
function p_norm = normalize_path(p)
    p_norm = lower(strrep(char(p), '/', filesep));
    while ~isempty(p_norm) && p_norm(end) == filesep
        p_norm = p_norm(1:end-1);
    end
end
