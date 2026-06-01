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
    config.data_path = 'G:\微流控\20 1-BO 4UL 5% TWEEN 80 4UL WATER DISPLACEMENT\02 NAPL';

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
    config.physical.channel_width_um = 10000;
    config.physical.diffusion_coeff  = 0.43e-9;
    config.physical.solubility       = 4;
    config.physical.dnapl_density    = 1038;
    config.physical.depth            = 20e-6;
    config.calibration.native_pixel_size_m = [];
    config.calibration.reference_length = 1;
    config.calibration.reference_unit = 'cm';

    % --- Time ---
    config.time_interval = 1;
    config.time_vector = [];

    % --- Rotation and crop ---
    config.preprocess.rotation_angle = 0;
    config.preprocess.manual_crop_rect = 'interactive';
    config.preprocessing.rgb_encoding = 'srgb';
    config.preprocessing.upscale.enabled = true;
    config.preprocessing.upscale.scale_factor = 2;
    config.preprocessing.upscale.engine = 'matlab_imresize';
    config.preprocessing.upscale.method = 'bicubic';
    config.preprocessing.upscale.output_dtype = 'single';
    config.preprocessing.upscale.max_frame_memory_mb = 2048;
    config.preprocessing.upscale.memory_budget_policy = 'warn';
    config.preprocessing.upscale.shadow_validation.enabled = false;

    % --- Flow-domain reference ---
    config.flow_domain_frame = 1;
    config.flow_domain_image = 'D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\01 databased\00 Saturation\1BD NAPL SATURATION3_1.tif';
    config.flow_domain_image_page = 1;
    config.flow_domain_crop_rect = [];
    config.flow_domain_image_role = 'clean_water_reference';
    config.water_reference_image = '';
    config.water_reference_image_page = 1;
    config.water_reference_crop_rect = [];
    config.napl_reference_image = 'D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\01 databased\00 Saturation\1BD NAPL SATURATION1_2.tif';
    config.napl_reference_image_page = 1;
    config.napl_reference_crop_rect = [];
    config.flow_domain.extraction_method = 'auto';
    config.flow_domain.color_contrast_min = 5;
    config.flow_domain.morph_contrast_min = 0.003;
    config.flow_domain.min_pillar_frac = 0.03;
    config.flow_domain.max_pillar_frac = 0.70;
    config.flow_domain.warn_pillar_frac = 0.05;
    config.flow_domain.otsu_min_frac = 0.05;
    config.flow_domain.otsu_max_frac = 0.60;
    config.flow_domain.bright_min_frac = 0.08;
    config.flow_domain.bright_max_frac = 0.55;
    config.flow_domain.quantile_min_frac = 0.05;
    config.flow_domain.quantile_max_frac = 0.45;
    config.flow_domain.target_pillar_frac = 0.18;
    config.flow_domain.max_pillar_area_frac = 0.05;
    config.flow_domain.white_pillar_sensitivity = 0.45;
    config.flow_domain.white_pillar_neighborhood_px = 41;
    config.flow_domain.white_pillar_min_area_px = 4;
    config.flow_domain.white_pillar_max_area_px = inf;
    config.flow_domain.white_pillar_min_circularity = 0.15;
    config.flow_domain.solid_mask_path = '';
    config.flow_domain.flow_domain_mask_path = '';
    config.flow_domain.mask_grid = 'target';
    config.flow_domain.mask_resize_method = 'nearest';
    config.flow_domain.dxf_boundary_mode = 'smallest_containing_circles';
    config.flow_domain.dxf_alignment_mode = 'control_points';
    config.flow_domain.dxf_control_points_image = [];
    % DXF->image transform for control-point alignment:
    %   'affine'     - 6 DOF (default); rotation/scale/shear/translation only.
    %   'projective' - 8 DOF homography; absorbs perspective/keystone when the
    %                  control-point residual stays high under an affine model.
    config.flow_domain.dxf_transform_model = 'affine';
    config.flow_domain.expected_porosity = NaN;
    config.flow_domain.porosity_tolerance = 0.05;
    config.flow_domain.hard_fail = true;

    % --- Input mode ---
    config.input_mode = 'multipage_tif';
    config.image_dir = '';
    config.image_files = {};

    % --- Output path ---
    default_output_name = ['output_' datestr(now, 'yyyymmdd_HHMMSS')];
    config.output_path = '';

    % --- Preprocessing ---
    config.preprocess.auto_rotate = false;
    config.illumination.method = 'morphological';
    config.illumination.kernel_size = 'interactive';
    config.illumination.field_source = 'per_image';
    config.illumination.solid_core_erode_radius = 2;
    config.illumination.solid_core_poly_order = 1;
    config.illumination.target_solid_rgb = [];
    config.registration.method = 'none';
    config.registration.transform = 'similarity';

    % --- Segmentation ---
    config.segmentation.color_space = 'Lab';
    config.segmentation.target_channel = 'a';
    config.segmentation.method = 'dual_reference_fraction_hysteresis';
    config.segmentation.num_components = 2;
    config.segmentation.min_blob_area = 10;
    config.segmentation.morph_radius = 2;
    config.segmentation.hole_fill_radius = 3;
    config.segmentation.high_saturation_guard.enabled = true;
    config.segmentation.high_saturation_guard.a_floor = 5;
    config.segmentation.high_saturation_guard.low_quantile = 5;
    config.segmentation.water_reference.enabled = false;
    config.segmentation.water_reference.threshold_quantile = 99.5;
    config.segmentation.water_reference.mad_k = 4;
    config.segmentation.water_reference.margin_a = 0.5;
    config.segmentation.water_reference.margin_delta_a = 2;
    config.segmentation.napl_reference.enabled = false;
    config.segmentation.napl_reference.deltaE_threshold = 8;
    config.segmentation.napl_reference.l_weight = 1;
    config.segmentation.napl_reference.a_weight = 1;
    config.segmentation.napl_reference.b_weight = 1;
    config.segmentation.dual_reference.feature_mode = 'lab_ab';
    config.segmentation.dual_reference.use_channels = 'ab';
    config.segmentation.dual_reference.lab_weights = [0 1 1];
    config.segmentation.dual_reference.frac_threshold = 0.50;
    config.segmentation.dual_reference.frac_high = 0.65;
    config.segmentation.dual_reference.frac_low = 0.35;
    config.segmentation.dual_reference.min_endpoint_distance = 3.0;
    config.segmentation.dual_reference.max_invalid_endpoint_fraction = 0.10;
    config.segmentation.dual_reference.max_invalid_endpoint_fraction_fail = 0.20;
    config.segmentation.dual_reference.endpoint_mode = 'auto';
    config.segmentation.dual_reference.endpoint_fail_policy = 'fallback_global';
    config.segmentation.dual_reference.emit_uncertainty_band = true;
    config.segmentation.dual_reference.use_hsv_seed = true;
    config.segmentation.dual_reference.self_test_enabled = true;
    config.segmentation.dual_reference.self_test_clean_water_max_sn = 0.05;
    config.segmentation.dual_reference.self_test_full_napl_min_sn = 0.85;
    config.segmentation.dual_reference.self_test_full_napl_frac_p95_min = 0.80;
    config.segmentation.hsv_red.enabled = true;
    config.segmentation.hsv_red.h_high1 = 0.03;
    config.segmentation.hsv_red.h_high2 = 0.97;
    config.segmentation.hsv_red.h_low1 = 0.07;
    config.segmentation.hsv_red.h_low2 = 0.93;
    config.segmentation.hsv_red.s_high = 0.20;
    config.segmentation.hsv_red.s_low = 0.08;
    config.segmentation.hsv_red.v_min = 0.10;
    config.segmentation.hsv_red.min_seed_fraction = 0.01;
    config.segmentation.hsv_red.frac_hsv_min = 0.02;
    config.segmentation.bulk_check.enabled = false;
    config.segmentation.bulk_check.metric = 'dual_reference_fraction_mean';
    config.segmentation.bulk_check.max_abs_difference = 0.10;
    config.segmentation.fixed_threshold = NaN;

    % --- Bulk/regional color-index Sn(t) ---
    config.bulk_sn.enabled = true;
    config.bulk_sn.primary_output = true;
    config.bulk_sn.score_mode = 'normalized_red';
    config.bulk_sn.statistic = 'winsorized_mean';
    config.bulk_sn.winsor_percentiles = [1 99];
    config.bulk_sn.core_flow_min_dist_px = [];
    config.bulk_sn.emit_regions = true;
    config.bulk_sn.n_x_bins = 20;
    config.bulk_sn.use_background = false;
    config.bulk_sn.pdf_method_reference = 'es4c11735_si_001.pdf';
    config.bulk_sn.min_endpoint_delta = 1e-6;

    % --- Interface analysis ---
    config.interface.solid_dilation = 1;

    % --- Blob geometry mode ---
    config.geometry.mode = 'core_only';
    config.geometry.schema_version = 'geometry_v2_core_only';
    config.geometry.object_connectivity = 8;
    config.geometry.hole_connectivity = 8;
    config.geometry.include_heavy_shape_props = true;
    config.geometry.roi_pad = 1;
    config.geometry.max_roi_area_fraction = 0.25;
    config.geometry.max_roi_pixels = 2e6;
    config.geometry.large_roi_policy = 'core_only_fallback';

    % --- Residual structure metrics ---
    config.architecture.pool_like.max_blob_fraction_min = 0.50;
    config.architecture.pool_like.num_blobs_max = 10;
    config.architecture.pool_like.a_i_2D_max = 3.0e4;
    config.architecture.ganglia_rich.max_blob_fraction_max = 0.30;
    config.architecture.ganglia_rich.num_blobs_min = 25;
    config.architecture.ganglia_rich.a_i_2D_min = 6.0e4;

    % --- Mass transfer model ---
    config.physical.sherwood_correlation = 'powers';

    % --- Visualization ---
    config.visualization.show_figures = true;
    config.visualization.save_figures = true;
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
    config.output.save_blob_detail = false;
    config.output.blob_detail_chunk_size = 100;
    config.output.blob_detail_save_format = 'v7';
    config.output.blob_detail_allow_format_fallback = true;
    config.output.blob_detail_chunk_max_bytes = 512 * 1024^2;
    config.output.max_frames_per_session = inf;
    config.output.emit_reliability_exports = true;
    config.output.emit_manifest = true;
    config.checkpoint.allow_legacy_resume = false;
    config.manifest.hash_policy = 'full';
    config.reliability.min_review_native_equiv_diameter_px = 4;
    config.reliability.min_reliable_native_equiv_diameter_px = 8;
    config.qc.flow_domain.hard_fail = true;
    config.qc.flow_domain.porosity_min = 0.40;
    config.qc.flow_domain.porosity_max = 0.70;
    config.qc.flow_domain.pillar_fraction_min = 0.20;

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
