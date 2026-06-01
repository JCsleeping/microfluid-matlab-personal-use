function config = validate_config(config)
% VALIDATE_CONFIG  Check pipeline configuration for invalid parameter values.
%
%   config = validate_config(config)
%
%   Validates critical parameters and throws descriptive errors for values
%   that would cause silent downstream failures. Called automatically at
%   the end of config_pipeline().
%
%   Input/Output:
%       config - Pipeline configuration struct (returned unchanged if valid)

    %% v3.3 processing-grid defaults and calibration aliases
    config = ensure_v33_defaults(config);

    %% Physical parameters
    config = reconcile_pixel_size_alias(config);
    if ~is_calibrate_token(config.physical.pixel_size)
        assert_positive(config.physical.pixel_size, 'physical.pixel_size');
    end
    if isnumeric(config.calibration.native_pixel_size_m) && ...
            ~isempty(config.calibration.native_pixel_size_m)
        assert_positive(config.calibration.native_pixel_size_m, ...
            'calibration.native_pixel_size_m');
        config = derive_processing_calibration(config);
    end
    assert_positive(config.physical.diffusion_coeff, 'physical.diffusion_coeff');
    assert_nonneg(config.physical.solubility, 'physical.solubility');
    assert_positive(config.physical.dnapl_density, 'physical.dnapl_density');
    assert_positive(config.physical.depth, 'physical.depth');

    %% Segmentation parameters
    if config.segmentation.num_components < 1
        error('validate_config:badParam', ...
            'segmentation.num_components must be >= 1, got %d.', ...
            config.segmentation.num_components);
    end
    assert_nonneg(config.segmentation.morph_radius, 'segmentation.morph_radius');
    if config.segmentation.min_blob_area < 1
        error('validate_config:badParam', ...
            'segmentation.min_blob_area must be >= 1, got %g.', ...
            config.segmentation.min_blob_area);
    end
    if ~isfield(config.segmentation, 'high_saturation_guard') || ...
            ~isstruct(config.segmentation.high_saturation_guard)
        config.segmentation.high_saturation_guard = struct();
    end
    config.segmentation.high_saturation_guard = set_default( ...
        config.segmentation.high_saturation_guard, 'enabled', true);
    config.segmentation.high_saturation_guard = set_default( ...
        config.segmentation.high_saturation_guard, 'a_floor', 5);
    config.segmentation.high_saturation_guard = set_default( ...
        config.segmentation.high_saturation_guard, 'low_quantile', 5);
    assert_logical_scalar(config.segmentation.high_saturation_guard.enabled, ...
        'segmentation.high_saturation_guard.enabled');
    assert_finite_positive_scalar(config.segmentation.high_saturation_guard.a_floor, ...
        'segmentation.high_saturation_guard.a_floor');
    assert_quantile(config.segmentation.high_saturation_guard.low_quantile, ...
        'segmentation.high_saturation_guard.low_quantile');

    if ~isfield(config.segmentation, 'water_reference') || ...
            ~isstruct(config.segmentation.water_reference)
        config.segmentation.water_reference = struct();
    end
    config.segmentation.water_reference = set_default( ...
        config.segmentation.water_reference, 'enabled', false);
    config.segmentation.water_reference = set_default( ...
        config.segmentation.water_reference, 'threshold_quantile', 99.5);
    config.segmentation.water_reference = set_default( ...
        config.segmentation.water_reference, 'mad_k', 4);
    config.segmentation.water_reference = set_default( ...
        config.segmentation.water_reference, 'margin_a', 0.5);
    config.segmentation.water_reference = set_default( ...
        config.segmentation.water_reference, 'margin_delta_a', 2);
    assert_logical_scalar(config.segmentation.water_reference.enabled, ...
        'segmentation.water_reference.enabled');
    assert_quantile(config.segmentation.water_reference.threshold_quantile, ...
        'segmentation.water_reference.threshold_quantile');
    assert_finite_positive_scalar(config.segmentation.water_reference.mad_k, ...
        'segmentation.water_reference.mad_k');
    assert_finite_nonnegative_scalar(config.segmentation.water_reference.margin_a, ...
        'segmentation.water_reference.margin_a');
    assert_finite_nonnegative_scalar(config.segmentation.water_reference.margin_delta_a, ...
        'segmentation.water_reference.margin_delta_a');

    if ~isfield(config.segmentation, 'napl_reference') || ...
            ~isstruct(config.segmentation.napl_reference)
        config.segmentation.napl_reference = struct();
    end
    config.segmentation.napl_reference = set_default( ...
        config.segmentation.napl_reference, 'enabled', false);
    config.segmentation.napl_reference = set_default( ...
        config.segmentation.napl_reference, 'deltaE_threshold', 8);
    config.segmentation.napl_reference = set_default( ...
        config.segmentation.napl_reference, 'l_weight', 1);
    config.segmentation.napl_reference = set_default( ...
        config.segmentation.napl_reference, 'a_weight', 1);
    config.segmentation.napl_reference = set_default( ...
        config.segmentation.napl_reference, 'b_weight', 1);
    assert_logical_scalar(config.segmentation.napl_reference.enabled, ...
        'segmentation.napl_reference.enabled');
    assert_finite_positive_scalar(config.segmentation.napl_reference.deltaE_threshold, ...
        'segmentation.napl_reference.deltaE_threshold');
    assert_finite_positive_scalar(config.segmentation.napl_reference.l_weight, ...
        'segmentation.napl_reference.l_weight');
    assert_finite_positive_scalar(config.segmentation.napl_reference.a_weight, ...
        'segmentation.napl_reference.a_weight');
    assert_finite_positive_scalar(config.segmentation.napl_reference.b_weight, ...
        'segmentation.napl_reference.b_weight');
    if ~isfield(config.segmentation, 'fixed_threshold') || ...
            isempty(config.segmentation.fixed_threshold)
        config.segmentation.fixed_threshold = NaN;
    end
    assert_nonnegative_or_nan(config.segmentation.fixed_threshold, ...
        'segmentation.fixed_threshold');

    %% Bulk color-index Sn(t)
    if ~isfield(config, 'bulk_sn') || ~isstruct(config.bulk_sn)
        config.bulk_sn = struct();
    end
    config.bulk_sn = set_default_bulk_sn(config.bulk_sn, 'enabled', true);
    config.bulk_sn = set_default_bulk_sn(config.bulk_sn, 'primary_output', true);
    config.bulk_sn = set_default_bulk_sn(config.bulk_sn, 'score_mode', 'normalized_red');
    config.bulk_sn = set_default_bulk_sn(config.bulk_sn, 'statistic', 'winsorized_mean');
    config.bulk_sn = set_default_bulk_sn(config.bulk_sn, 'winsor_percentiles', [1 99]);
    config.bulk_sn = set_default_bulk_sn(config.bulk_sn, 'core_flow_min_dist_px', []);
    config.bulk_sn = set_default_bulk_sn(config.bulk_sn, 'emit_regions', true);
    config.bulk_sn = set_default_bulk_sn(config.bulk_sn, 'n_x_bins', 20);
    config.bulk_sn = set_default_bulk_sn(config.bulk_sn, 'use_background', false);
    config.bulk_sn = set_default_bulk_sn(config.bulk_sn, ...
        'pdf_method_reference', 'es4c11735_si_001.pdf');
    config.bulk_sn = set_default_bulk_sn(config.bulk_sn, 'min_endpoint_delta', 1e-6);
    assert_logical_scalar(config.bulk_sn.enabled, 'bulk_sn.enabled');
    assert_logical_scalar(config.bulk_sn.primary_output, 'bulk_sn.primary_output');
    assert_logical_scalar(config.bulk_sn.emit_regions, 'bulk_sn.emit_regions');
    assert_logical_scalar(config.bulk_sn.use_background, 'bulk_sn.use_background');
    valid_bulk_score_modes = {'normalized_red', 'excess_red', 'lab_a', ...
        'chroma', 'lab_ab_projection'};
    bulk_score_mode = char(string(config.bulk_sn.score_mode));
    if ~ismember(bulk_score_mode, valid_bulk_score_modes)
        error('validate_config:badParam', ...
            'bulk_sn.score_mode must be one of: %s. Got "%s".', ...
            strjoin(valid_bulk_score_modes, ', '), bulk_score_mode);
    end
    config.bulk_sn.score_mode = bulk_score_mode;
    valid_bulk_statistics = {'winsorized_mean', 'mean'};
    bulk_statistic = char(string(config.bulk_sn.statistic));
    if ~ismember(bulk_statistic, valid_bulk_statistics)
        error('validate_config:badParam', ...
            'bulk_sn.statistic must be one of: %s. Got "%s".', ...
            strjoin(valid_bulk_statistics, ', '), bulk_statistic);
    end
    config.bulk_sn.statistic = bulk_statistic;
    if ~isnumeric(config.bulk_sn.winsor_percentiles) || ...
            numel(config.bulk_sn.winsor_percentiles) ~= 2 || ...
            any(~isfinite(config.bulk_sn.winsor_percentiles)) || ...
            config.bulk_sn.winsor_percentiles(1) < 0 || ...
            config.bulk_sn.winsor_percentiles(2) > 100 || ...
            config.bulk_sn.winsor_percentiles(1) >= config.bulk_sn.winsor_percentiles(2)
        error('validate_config:badParam', ...
            'bulk_sn.winsor_percentiles must be [lo hi] with 0 <= lo < hi <= 100.');
    end
    if ~isempty(config.bulk_sn.core_flow_min_dist_px)
        assert_finite_nonnegative_scalar(config.bulk_sn.core_flow_min_dist_px, ...
            'bulk_sn.core_flow_min_dist_px');
    end
    assert_pos_integer(config.bulk_sn.n_x_bins, 'bulk_sn.n_x_bins');
    assert_finite_positive_scalar(config.bulk_sn.min_endpoint_delta, ...
        'bulk_sn.min_endpoint_delta');
    assert_text_or_empty(config.bulk_sn.pdf_method_reference, ...
        'bulk_sn.pdf_method_reference');

    %% Reference image fields
    assert_text_or_empty(read_config_field(config, 'flow_domain_image', ''), ...
        'flow_domain_image');
    assert_text_or_empty(read_config_field(config, 'water_reference_image', ''), ...
        'water_reference_image');
    flow_domain_image_role = char(string(read_config_field(config, ...
        'flow_domain_image_role', 'clean_water_reference')));
    valid_flow_domain_image_roles = {'clean_water_reference', ...
        'alignment_reference', 'flow_domain_reference'};
    if ~ismember(flow_domain_image_role, valid_flow_domain_image_roles)
        error('validate_config:badParam', ...
            'flow_domain_image_role must be one of: %s. Got "%s".', ...
            strjoin(valid_flow_domain_image_roles, ', '), ...
            flow_domain_image_role);
    end
    config.flow_domain_image_role = flow_domain_image_role;
    if isfield(config, 'flow_domain_image_page') && ...
            ~isempty(config.flow_domain_image_page)
        assert_pos_integer(config.flow_domain_image_page, ...
            'flow_domain_image_page');
    end
    if isfield(config, 'water_reference_image_page') && ...
            ~isempty(config.water_reference_image_page)
        assert_pos_integer(config.water_reference_image_page, ...
            'water_reference_image_page');
    end
    if isfield(config, 'flow_domain_crop_rect') && ...
            ~isempty(config.flow_domain_crop_rect)
        assert_crop_rect(config.flow_domain_crop_rect, ...
            'flow_domain_crop_rect');
    end
    if isfield(config, 'water_reference_crop_rect') && ...
            ~isempty(config.water_reference_crop_rect)
        assert_crop_rect(config.water_reference_crop_rect, ...
            'water_reference_crop_rect');
    end
    assert_text_or_empty(config.napl_reference_image, 'napl_reference_image');
    assert_pos_integer(config.napl_reference_image_page, ...
        'napl_reference_image_page');
    if ~isempty(config.napl_reference_crop_rect)
        assert_crop_rect(config.napl_reference_crop_rect, ...
            'napl_reference_crop_rect');
    end

    %% Flow-domain extraction
    if ~isfield(config, 'flow_domain') || ~isstruct(config.flow_domain)
        config.flow_domain = struct();
    end
    if ~isfield(config.flow_domain, 'extraction_method') || ...
            isempty(config.flow_domain.extraction_method)
        config.flow_domain.extraction_method = 'auto';
    end
    valid_flow_domain_methods = {'auto', 'lab_color', 'morphological', ...
        'white_pillars', 'mask'};
    flow_domain_method = char(string(config.flow_domain.extraction_method));
    if ~ismember(flow_domain_method, valid_flow_domain_methods)
        error('validate_config:badParam', ...
            'flow_domain.extraction_method must be one of: %s. Got "%s".', ...
            strjoin(valid_flow_domain_methods, ', '), flow_domain_method);
    end
    config.flow_domain.extraction_method = flow_domain_method;
    config.flow_domain = set_default(config.flow_domain, 'color_contrast_min', 5);
    config.flow_domain = set_default(config.flow_domain, 'morph_contrast_min', 0.003);
    config.flow_domain = set_default(config.flow_domain, 'min_pillar_frac', 0.03);
    config.flow_domain = set_default(config.flow_domain, 'max_pillar_frac', 0.70);
    config.flow_domain = set_default(config.flow_domain, 'warn_pillar_frac', 0.05);
    config.flow_domain = set_default(config.flow_domain, 'otsu_min_frac', 0.05);
    config.flow_domain = set_default(config.flow_domain, 'otsu_max_frac', 0.60);
    config.flow_domain = set_default(config.flow_domain, 'bright_min_frac', 0.08);
    config.flow_domain = set_default(config.flow_domain, 'bright_max_frac', 0.55);
    config.flow_domain = set_default(config.flow_domain, 'quantile_min_frac', 0.05);
    config.flow_domain = set_default(config.flow_domain, 'quantile_max_frac', 0.45);
    config.flow_domain = set_default(config.flow_domain, 'target_pillar_frac', 0.18);
    config.flow_domain = set_default(config.flow_domain, 'max_pillar_area_frac', 0.05);
    config.flow_domain = set_default(config.flow_domain, ...
        'white_pillar_sensitivity', 0.45);
    config.flow_domain = set_default(config.flow_domain, ...
        'white_pillar_neighborhood_px', 41);
    config.flow_domain = set_default(config.flow_domain, ...
        'white_pillar_min_area_px', 4);
    config.flow_domain = set_default(config.flow_domain, ...
        'white_pillar_max_area_px', inf);
    config.flow_domain = set_default(config.flow_domain, ...
        'white_pillar_min_circularity', 0.15);
    config.flow_domain = set_default(config.flow_domain, ...
        'solid_mask_path', '');
    config.flow_domain = set_default(config.flow_domain, ...
        'flow_domain_mask_path', '');
    config.flow_domain = set_default(config.flow_domain, ...
        'mask_grid', 'target');
    config.flow_domain = set_default(config.flow_domain, ...
        'mask_resize_method', 'nearest');
    config.flow_domain = set_default(config.flow_domain, ...
        'dxf_boundary_mode', 'circle_bbox');
    config.flow_domain = set_default(config.flow_domain, ...
        'dxf_transform_model', 'affine');
    config.flow_domain = set_default(config.flow_domain, ...
        'expected_porosity', NaN);
    config.flow_domain = set_default(config.flow_domain, ...
        'porosity_tolerance', 0.05);
    config.flow_domain = set_default(config.flow_domain, ...
        'hard_fail', true);
    assert_finite_nonnegative_scalar(config.flow_domain.color_contrast_min, ...
        'flow_domain.color_contrast_min');
    assert_finite_nonnegative_scalar(config.flow_domain.morph_contrast_min, ...
        'flow_domain.morph_contrast_min');
    assert_fraction_scalar(config.flow_domain.min_pillar_frac, ...
        'flow_domain.min_pillar_frac');
    assert_fraction_scalar(config.flow_domain.max_pillar_frac, ...
        'flow_domain.max_pillar_frac');
    if config.flow_domain.min_pillar_frac >= config.flow_domain.max_pillar_frac
        error('validate_config:badParam', ...
            'flow_domain.min_pillar_frac must be less than max_pillar_frac.');
    end
    assert_fraction_scalar(config.flow_domain.warn_pillar_frac, ...
        'flow_domain.warn_pillar_frac');
    assert_fraction_scalar(config.flow_domain.otsu_min_frac, ...
        'flow_domain.otsu_min_frac');
    assert_fraction_scalar(config.flow_domain.otsu_max_frac, ...
        'flow_domain.otsu_max_frac');
    if config.flow_domain.otsu_min_frac >= config.flow_domain.otsu_max_frac
        error('validate_config:badParam', ...
            'flow_domain.otsu_min_frac must be less than otsu_max_frac.');
    end
    assert_fraction_scalar(config.flow_domain.bright_min_frac, ...
        'flow_domain.bright_min_frac');
    assert_fraction_scalar(config.flow_domain.bright_max_frac, ...
        'flow_domain.bright_max_frac');
    if config.flow_domain.bright_min_frac >= config.flow_domain.bright_max_frac
        error('validate_config:badParam', ...
            'flow_domain.bright_min_frac must be less than bright_max_frac.');
    end
    assert_fraction_scalar(config.flow_domain.quantile_min_frac, ...
        'flow_domain.quantile_min_frac');
    assert_fraction_scalar(config.flow_domain.quantile_max_frac, ...
        'flow_domain.quantile_max_frac');
    if config.flow_domain.quantile_min_frac >= config.flow_domain.quantile_max_frac
        error('validate_config:badParam', ...
            'flow_domain.quantile_min_frac must be less than quantile_max_frac.');
    end
    assert_fraction_scalar(config.flow_domain.target_pillar_frac, ...
        'flow_domain.target_pillar_frac');
    assert_fraction_scalar(config.flow_domain.max_pillar_area_frac, ...
        'flow_domain.max_pillar_area_frac');
    assert_fraction_scalar(config.flow_domain.white_pillar_sensitivity, ...
        'flow_domain.white_pillar_sensitivity');
    assert_pos_integer(config.flow_domain.white_pillar_neighborhood_px, ...
        'flow_domain.white_pillar_neighborhood_px');
    assert_pos_integer(config.flow_domain.white_pillar_min_area_px, ...
        'flow_domain.white_pillar_min_area_px');
    assert_pos_integer_or_inf(config.flow_domain.white_pillar_max_area_px, ...
        'flow_domain.white_pillar_max_area_px');
    assert_fraction_scalar(config.flow_domain.white_pillar_min_circularity, ...
        'flow_domain.white_pillar_min_circularity');
    assert_text_or_empty(config.flow_domain.solid_mask_path, ...
        'flow_domain.solid_mask_path');
    assert_text_or_empty(config.flow_domain.flow_domain_mask_path, ...
        'flow_domain.flow_domain_mask_path');
    config.flow_domain = validate_flow_domain_mask_options(config.flow_domain);
    assert_fraction_or_nan(config.flow_domain.expected_porosity, ...
        'flow_domain.expected_porosity');
    assert_fraction_open_scalar(config.flow_domain.porosity_tolerance, ...
        'flow_domain.porosity_tolerance');
    assert_logical_scalar(config.flow_domain.hard_fail, ...
        'flow_domain.hard_fail');

    if ~isfield(config, 'qc') || ~isstruct(config.qc)
        config.qc = struct();
    end
    if ~isfield(config.qc, 'flow_domain') || ~isstruct(config.qc.flow_domain)
        config.qc.flow_domain = struct();
    end
    config.qc.flow_domain = set_default(config.qc.flow_domain, 'hard_fail', true);
    config.qc.flow_domain = set_default(config.qc.flow_domain, 'porosity_min', 0.40);
    config.qc.flow_domain = set_default(config.qc.flow_domain, 'porosity_max', 0.70);
    config.qc.flow_domain = set_default(config.qc.flow_domain, 'pillar_fraction_min', 0.20);
    assert_logical_scalar(config.qc.flow_domain.hard_fail, ...
        'qc.flow_domain.hard_fail');
    assert_fraction_scalar(config.qc.flow_domain.porosity_min, ...
        'qc.flow_domain.porosity_min');
    assert_fraction_scalar(config.qc.flow_domain.porosity_max, ...
        'qc.flow_domain.porosity_max');
    if config.qc.flow_domain.porosity_min >= config.qc.flow_domain.porosity_max
        error('validate_config:badParam', ...
            'qc.flow_domain.porosity_min must be less than porosity_max.');
    end
    assert_fraction_scalar(config.qc.flow_domain.pillar_fraction_min, ...
        'qc.flow_domain.pillar_fraction_min');

    %% Interface parameters
    assert_nonneg(config.interface.solid_dilation, 'interface.solid_dilation');

    %% Blob geometry parameters
    valid_geometry_modes = {'core_only', 'roi', 'legacy_fullframe'};
    geometry_mode = char(string(config.geometry.mode));
    if ~ismember(geometry_mode, valid_geometry_modes)
        error('validate_config:badParam', ...
            'geometry.mode must be one of: %s. Got "%s".', ...
            strjoin(valid_geometry_modes, ', '), geometry_mode);
    end
    config.geometry.mode = geometry_mode;
    assert_integer_in_set(config.geometry.object_connectivity, ...
        'geometry.object_connectivity', [4 8]);
    assert_integer_in_set(config.geometry.hole_connectivity, ...
        'geometry.hole_connectivity', [4 8]);
    assert_logical_scalar(config.geometry.include_heavy_shape_props, ...
        'geometry.include_heavy_shape_props');
    assert_nonnegative_integer(config.geometry.roi_pad, 'geometry.roi_pad');
    assert_fraction_scalar(config.geometry.max_roi_area_fraction, ...
        'geometry.max_roi_area_fraction');
    assert_finite_positive_scalar(config.geometry.max_roi_pixels, ...
        'geometry.max_roi_pixels');
    valid_large_roi_policies = {'core_only_fallback', 'error'};
    large_roi_policy = char(string(config.geometry.large_roi_policy));
    if ~ismember(large_roi_policy, valid_large_roi_policies)
        error('validate_config:badParam', ...
            'geometry.large_roi_policy must be one of: %s. Got "%s".', ...
            strjoin(valid_large_roi_policies, ', '), large_roi_policy);
    end
    config.geometry.large_roi_policy = large_roi_policy;

    if isempty(config.geometry.schema_version)
        config.geometry.schema_version = geometry_schema_for_mode(geometry_mode);
    elseif strcmp(char(string(config.geometry.schema_version)), 'geometry_v2_core_only')
        if strcmp(geometry_mode, 'roi')
            config.geometry.schema_version = 'geometry_v3_roi_holes';
        elseif strcmp(geometry_mode, 'legacy_fullframe')
            config.geometry.schema_version = 'geometry_v1_legacy_fullframe';
        end
    end
    if ~(ischar(config.geometry.schema_version) || isstring(config.geometry.schema_version)) || ...
            strlength(string(config.geometry.schema_version)) == 0
        error('validate_config:badParam', ...
            'geometry.schema_version must be a non-empty string.');
    end
    config.geometry.schema_version = char(string(config.geometry.schema_version));

    %% Time parameters
    if isfield(config, 'time_interval') && ~isempty(config.time_interval)
        assert_positive(config.time_interval, 'time_interval');
    end

    %% Page indices
    if ~isempty(config.pages)
        if any(config.pages < 1) || any(mod(config.pages, 1) ~= 0)
            error('validate_config:badParam', ...
                'pages must be positive integers. Got invalid values: %s', ...
                mat2str(config.pages(config.pages < 1 | mod(config.pages, 1) ~= 0)));
        end
    end

    %% Input mode
    valid_modes = {'multipage_tif', 'separate_files'};
    if ~ismember(lower(config.input_mode), valid_modes)
        error('validate_config:badParam', ...
            'input_mode must be one of: %s. Got "%s".', ...
            strjoin(valid_modes, ', '), config.input_mode);
    end

    %% Output controls
    if ~isfield(config.output, 'blob_detail_chunk_size') || isempty(config.output.blob_detail_chunk_size)
        config.output.blob_detail_chunk_size = 100;
    end
    if ~isfield(config.output, 'blob_detail_save_format') || isempty(config.output.blob_detail_save_format)
        config.output.blob_detail_save_format = 'v7';
    end
    if ~isfield(config.output, 'blob_detail_allow_format_fallback') || isempty(config.output.blob_detail_allow_format_fallback)
        config.output.blob_detail_allow_format_fallback = true;
    end
    if ~isfield(config.output, 'blob_detail_chunk_max_bytes') || isempty(config.output.blob_detail_chunk_max_bytes)
        config.output.blob_detail_chunk_max_bytes = 512 * 1024^2;
    end

    assert_logical_scalar(config.output.checkpoint, 'output.checkpoint');
    assert_logical_scalar(config.output.save_log, 'output.save_log');
    assert_logical_scalar(config.output.save_progress, 'output.save_progress');
    assert_logical_scalar(config.output.save_heartbeat, 'output.save_heartbeat');
    assert_logical_scalar(config.output.save_blob_detail, 'output.save_blob_detail');
    assert_logical_scalar(config.output.emit_reliability_exports, ...
        'output.emit_reliability_exports');
    assert_logical_scalar(config.output.emit_manifest, 'output.emit_manifest');
    assert_pos_integer(config.output.save_interval, 'output.save_interval');
    assert_pos_integer(config.output.progress_interval, 'output.progress_interval');
    assert_pos_integer(config.output.heartbeat_frame_interval, 'output.heartbeat_frame_interval');
    assert_pos_integer(config.output.heartbeat_time_interval_sec, 'output.heartbeat_time_interval_sec');
    assert_integer_in_range(config.output.blob_detail_chunk_size, ...
        'output.blob_detail_chunk_size', 10, 5000);
    valid_blob_detail_formats = {'v7', 'v7.3', 'v7.3-nocompression'};
    if ~(ischar(config.output.blob_detail_save_format) || isstring(config.output.blob_detail_save_format)) || ...
            ~ismember(char(string(config.output.blob_detail_save_format)), valid_blob_detail_formats)
        error('validate_config:badParam', ...
            'output.blob_detail_save_format must be one of: %s. Got "%s".', ...
            strjoin(valid_blob_detail_formats, ', '), char(string(config.output.blob_detail_save_format)));
    end
    assert_logical_scalar(config.output.blob_detail_allow_format_fallback, ...
        'output.blob_detail_allow_format_fallback');
    assert_min_finite_positive_scalar(config.output.blob_detail_chunk_max_bytes, ...
        'output.blob_detail_chunk_max_bytes', 10 * 1024^2);
    assert_pos_integer_or_inf(config.output.max_frames_per_session, 'output.max_frames_per_session');

    if isfield(config, 'parallel') && isfield(config.parallel, 'enabled') && ...
            config.parallel.enabled && config.output.save_blob_detail
        error('validate_config:badParam', ...
            ['output.save_blob_detail=true is not supported when parallel.enabled=true. ' ...
             'Set output.save_blob_detail=false or disable parallel processing.']);
    end

    %% Upscale / manifest / reliability parameters
    try
        config.preprocessing.rgb_encoding = ...
            normalize_rgb_encoding(config.preprocessing.rgb_encoding);
    catch err
        error('validate_config:badParam', '%s', err.message);
    end
    assert_logical_scalar(config.preprocessing.upscale.enabled, ...
        'preprocessing.upscale.enabled');
    assert_pos_integer(config.preprocessing.upscale.scale_factor, ...
        'preprocessing.upscale.scale_factor');
    valid_engines = {'matlab_imresize', 'imagej_bicubic', 'fiji_bicubic'};
    engine = char(string(config.preprocessing.upscale.engine));
    if ~ismember(engine, valid_engines)
        error('validate_config:badParam', ...
            'preprocessing.upscale.engine must be one of: %s. Got "%s".', ...
            strjoin(valid_engines, ', '), engine);
    end
    if ismember(engine, {'imagej_bicubic', 'fiji_bicubic'})
        error('validate_config:notImplementedYet', ...
            'preprocessing.upscale.engine "%s" is reserved for a future milestone.', engine);
    end
    valid_methods = {'bilinear', 'bicubic'};
    method = char(string(config.preprocessing.upscale.method));
    if ~ismember(method, valid_methods)
        error('validate_config:badParam', ...
            'preprocessing.upscale.method for RGB frames must be one of: %s. Got "%s".', ...
            strjoin(valid_methods, ', '), method);
    end
    valid_output_dtype = {'single', 'like_input'};
    output_dtype = char(string(config.preprocessing.upscale.output_dtype));
    if ~ismember(output_dtype, valid_output_dtype)
        error('validate_config:badParam', ...
            'preprocessing.upscale.output_dtype must be one of: %s. Got "%s".', ...
            strjoin(valid_output_dtype, ', '), output_dtype);
    end
    assert_finite_positive_scalar(config.preprocessing.upscale.max_frame_memory_mb, ...
        'preprocessing.upscale.max_frame_memory_mb');
    valid_memory_policy = {'warn', 'error'};
    memory_policy = char(string(config.preprocessing.upscale.memory_budget_policy));
    if ~ismember(memory_policy, valid_memory_policy)
        error('validate_config:badParam', ...
            'preprocessing.upscale.memory_budget_policy must be one of: %s. Got "%s".', ...
            strjoin(valid_memory_policy, ', '), memory_policy);
    end
    assert_logical_scalar(config.preprocessing.upscale.shadow_validation.enabled, ...
        'preprocessing.upscale.shadow_validation.enabled');
    if config.preprocessing.upscale.shadow_validation.enabled
        error('validate_config:notImplementedYet', ...
            ['preprocessing.upscale.shadow_validation.enabled=true is reserved for the ' ...
             'native-vs-assisted diagnostic milestone and is not implemented yet.']);
    end
    assert_logical_scalar(config.checkpoint.allow_legacy_resume, ...
        'checkpoint.allow_legacy_resume');
    valid_hash_policy = {'full', 'size_mtime_only', 'disabled_with_warning'};
    hash_policy = char(string(config.manifest.hash_policy));
    if ~ismember(hash_policy, valid_hash_policy)
        error('validate_config:badParam', ...
            'manifest.hash_policy must be one of: %s. Got "%s".', ...
            strjoin(valid_hash_policy, ', '), hash_policy);
    end
    assert_finite_positive_scalar(config.reliability.min_review_native_equiv_diameter_px, ...
        'reliability.min_review_native_equiv_diameter_px');
    assert_finite_positive_scalar(config.reliability.min_reliable_native_equiv_diameter_px, ...
        'reliability.min_reliable_native_equiv_diameter_px');
    if config.reliability.min_reliable_native_equiv_diameter_px <= ...
            config.reliability.min_review_native_equiv_diameter_px
        error('validate_config:badParam', ...
            'reliability.min_reliable_native_equiv_diameter_px must exceed min_review_native_equiv_diameter_px.');
    end

    if isfinite(config.output.max_frames_per_session)
        if ~config.output.checkpoint
            error('validate_config:badParam', ...
                ['output.max_frames_per_session requires output.checkpoint=true ' ...
                 'so the pipeline can pause on a safe resume boundary.']);
        end
        if mod(config.output.max_frames_per_session, config.output.save_interval) ~= 0
            error('validate_config:badParam', ...
                ['output.max_frames_per_session (%g) must be an integer multiple of ' ...
                 'output.save_interval (%g).'], ...
                config.output.max_frames_per_session, config.output.save_interval);
        end
        if isfield(config, 'parallel') && isfield(config.parallel, 'enabled') && config.parallel.enabled
            error('validate_config:badParam', ...
                ['output.max_frames_per_session only supports sequential Step 4 runs. ' ...
                 'Set parallel.enabled=false when using session pause.']);
        end
    end

    %% Residual structure architecture thresholds
    assert_fraction_scalar(config.architecture.pool_like.max_blob_fraction_min, ...
        'architecture.pool_like.max_blob_fraction_min');
    assert_pos_integer(config.architecture.pool_like.num_blobs_max, ...
        'architecture.pool_like.num_blobs_max');
    assert_finite_positive_scalar(config.architecture.pool_like.a_i_2D_max, ...
        'architecture.pool_like.a_i_2D_max');
    assert_fraction_scalar(config.architecture.ganglia_rich.max_blob_fraction_max, ...
        'architecture.ganglia_rich.max_blob_fraction_max');
    assert_pos_integer(config.architecture.ganglia_rich.num_blobs_min, ...
        'architecture.ganglia_rich.num_blobs_min');
    assert_finite_positive_scalar(config.architecture.ganglia_rich.a_i_2D_min, ...
        'architecture.ganglia_rich.a_i_2D_min');

    if ~(config.architecture.pool_like.max_blob_fraction_min > ...
            config.architecture.ganglia_rich.max_blob_fraction_max)
        error('validate_config:badParam', ...
            ['architecture.pool_like.max_blob_fraction_min (%g) must be greater than ' ...
             'architecture.ganglia_rich.max_blob_fraction_max (%g).'], ...
            config.architecture.pool_like.max_blob_fraction_min, ...
            config.architecture.ganglia_rich.max_blob_fraction_max);
    end

    if ~(config.architecture.pool_like.a_i_2D_max < ...
            config.architecture.ganglia_rich.a_i_2D_min)
        error('validate_config:badParam', ...
            ['architecture.pool_like.a_i_2D_max (%g) must be less than ' ...
             'architecture.ganglia_rich.a_i_2D_min (%g).'], ...
            config.architecture.pool_like.a_i_2D_max, ...
            config.architecture.ganglia_rich.a_i_2D_min);
    end

    %% Segmentation method
    valid_seg = {'gmm', 'otsu', 'adaptive', 'gmm_v2', 'otsu_v2', ...
        'fixed_threshold', 'calibrated_a_threshold', 'calibrated_delta_a', ...
        'napl_reference_deltae', 'dual_reference_fraction', ...
        'dual_reference_fraction_hysteresis', 'dual_reference_nearest'};
    seg_method = lower(char(string(config.segmentation.method)));
    if ~ismember(seg_method, valid_seg)
        error('validate_config:badParam', ...
            'segmentation.method must be one of: %s. Got "%s".', ...
            strjoin(valid_seg, ', '), config.segmentation.method);
    end
    config.segmentation.method = seg_method;
    if requires_clean_water_reference(seg_method)
        water_reference_image = read_config_field(config, ...
            'water_reference_image', '');
        if ~isempty(water_reference_image)
            assert_nonempty_text(water_reference_image, ...
                'water_reference_image');
        elseif strcmp(config.flow_domain_image_role, 'clean_water_reference')
            assert_nonempty_text(read_config_field(config, ...
                'flow_domain_image', ''), 'flow_domain_image');
        else
            error('validate_config:badWaterReferenceRole', ...
                ['Water-referenced segmentation requires water_reference_image, ' ...
                 'or flow_domain_image_role=''clean_water_reference''.']);
        end
    end
    if is_dual_reference_method(seg_method)
        assert_nonempty_text(config.napl_reference_image, ...
            'napl_reference_image');
        if isfinite(config.segmentation.fixed_threshold)
            error('validate_config:conflictingFixedAndDualReference', ...
                ['segmentation.fixed_threshold must be NaN when using ' ...
                 'dual-reference segmentation methods.']);
        end
        validate_dual_reference_options(config.segmentation.dual_reference);
        validate_hsv_red_options(config.segmentation.hsv_red);
        validate_bulk_check_options(config.segmentation.bulk_check);
    end
end


function config = ensure_v33_defaults(config)
    if ~isfield(config, 'calibration') || ~isstruct(config.calibration)
        config.calibration = struct();
    end
    if ~isfield(config.calibration, 'native_pixel_size_m')
        config.calibration.native_pixel_size_m = [];
    end
    if ~isfield(config.calibration, 'reference_length')
        config.calibration.reference_length = 1;
    end
    if ~isfield(config.calibration, 'reference_unit')
        config.calibration.reference_unit = 'cm';
    end

    config = set_default(config, 'napl_reference_image', '');
    config = set_default(config, 'napl_reference_image_page', 1);
    config = set_default(config, 'napl_reference_crop_rect', []);
    config = set_default(config, 'water_reference_image', '');
    config = set_default(config, 'water_reference_image_page', 1);
    config = set_default(config, 'water_reference_crop_rect', []);
    config = set_default(config, 'flow_domain_image_role', ...
        'clean_water_reference');

    if ~isfield(config, 'preprocessing') || ~isstruct(config.preprocessing)
        config.preprocessing = struct();
    end
    config.preprocessing = set_default(config.preprocessing, ...
        'rgb_encoding', 'srgb');
    if ~isfield(config.preprocessing, 'upscale') || ~isstruct(config.preprocessing.upscale)
        config.preprocessing.upscale = struct();
    end
    config.preprocessing.upscale = set_default(config.preprocessing.upscale, ...
        'enabled', true);
    config.preprocessing.upscale = set_default(config.preprocessing.upscale, ...
        'scale_factor', 2);
    config.preprocessing.upscale = set_default(config.preprocessing.upscale, ...
        'engine', 'matlab_imresize');
    config.preprocessing.upscale = set_default(config.preprocessing.upscale, ...
        'method', 'bicubic');
    config.preprocessing.upscale = set_default(config.preprocessing.upscale, ...
        'output_dtype', 'single');
    config.preprocessing.upscale = set_default(config.preprocessing.upscale, ...
        'max_frame_memory_mb', 2048);
    config.preprocessing.upscale = set_default(config.preprocessing.upscale, ...
        'memory_budget_policy', 'warn');
    if ~isfield(config.preprocessing.upscale, 'shadow_validation') || ...
            ~isstruct(config.preprocessing.upscale.shadow_validation)
        config.preprocessing.upscale.shadow_validation = struct();
    end
    config.preprocessing.upscale.shadow_validation = set_default( ...
        config.preprocessing.upscale.shadow_validation, 'enabled', false);

    if ~isfield(config, 'output') || ~isstruct(config.output)
        config.output = struct();
    end
    config.output = set_default(config.output, 'emit_reliability_exports', true);
    config.output = set_default(config.output, 'emit_manifest', true);

    if ~isfield(config, 'segmentation') || ~isstruct(config.segmentation)
        config.segmentation = struct();
    end
    if ~isfield(config.segmentation, 'high_saturation_guard') || ...
            ~isstruct(config.segmentation.high_saturation_guard)
        config.segmentation.high_saturation_guard = struct();
    end
    config.segmentation.high_saturation_guard = set_default( ...
        config.segmentation.high_saturation_guard, 'enabled', true);
    config.segmentation.high_saturation_guard = set_default( ...
        config.segmentation.high_saturation_guard, 'a_floor', 5);
    config.segmentation.high_saturation_guard = set_default( ...
        config.segmentation.high_saturation_guard, 'low_quantile', 5);

    config.segmentation = set_default(config.segmentation, ...
        'fixed_threshold', NaN);
    if ~isfield(config.segmentation, 'water_reference') || ...
            ~isstruct(config.segmentation.water_reference)
        config.segmentation.water_reference = struct();
    end
    config.segmentation.water_reference = set_default( ...
        config.segmentation.water_reference, 'enabled', false);
    config.segmentation.water_reference = set_default( ...
        config.segmentation.water_reference, 'threshold_quantile', 99.5);
    config.segmentation.water_reference = set_default( ...
        config.segmentation.water_reference, 'mad_k', 4);
    config.segmentation.water_reference = set_default( ...
        config.segmentation.water_reference, 'margin_a', 0.5);
    config.segmentation.water_reference = set_default( ...
        config.segmentation.water_reference, 'margin_delta_a', 2);

    if ~isfield(config.segmentation, 'napl_reference') || ...
            ~isstruct(config.segmentation.napl_reference)
        config.segmentation.napl_reference = struct();
    end
    config.segmentation.napl_reference = set_default( ...
        config.segmentation.napl_reference, 'enabled', false);
    config.segmentation.napl_reference = set_default( ...
        config.segmentation.napl_reference, 'deltaE_threshold', 8);
    config.segmentation.napl_reference = set_default( ...
        config.segmentation.napl_reference, 'l_weight', 1);
    config.segmentation.napl_reference = set_default( ...
        config.segmentation.napl_reference, 'a_weight', 1);
    config.segmentation.napl_reference = set_default( ...
        config.segmentation.napl_reference, 'b_weight', 1);

    if ~isfield(config.segmentation, 'dual_reference') || ...
            ~isstruct(config.segmentation.dual_reference)
        config.segmentation.dual_reference = struct();
    end
    config.segmentation.dual_reference = set_default( ...
        config.segmentation.dual_reference, 'feature_mode', 'lab_ab');
    config.segmentation.dual_reference = set_default( ...
        config.segmentation.dual_reference, 'use_channels', 'ab');
    config.segmentation.dual_reference = set_default( ...
        config.segmentation.dual_reference, 'lab_weights', [0 1 1]);
    config.segmentation.dual_reference = set_default( ...
        config.segmentation.dual_reference, 'frac_threshold', 0.50);
    config.segmentation.dual_reference = set_default( ...
        config.segmentation.dual_reference, 'frac_high', 0.65);
    config.segmentation.dual_reference = set_default( ...
        config.segmentation.dual_reference, 'frac_low', 0.35);
    config.segmentation.dual_reference = set_default( ...
        config.segmentation.dual_reference, 'min_endpoint_distance', 3.0);
    config.segmentation.dual_reference = set_default( ...
        config.segmentation.dual_reference, 'max_invalid_endpoint_fraction', 0.10);
    config.segmentation.dual_reference = set_default( ...
        config.segmentation.dual_reference, 'max_invalid_endpoint_fraction_fail', ...
        0.20);
    config.segmentation.dual_reference = set_default( ...
        config.segmentation.dual_reference, 'endpoint_mode', 'auto');
    config.segmentation.dual_reference = set_default( ...
        config.segmentation.dual_reference, 'endpoint_fail_policy', ...
        'fallback_global');
    config.segmentation.dual_reference = set_default( ...
        config.segmentation.dual_reference, 'emit_uncertainty_band', true);
    config.segmentation.dual_reference = set_default( ...
        config.segmentation.dual_reference, 'use_hsv_seed', true);
    config.segmentation.dual_reference = set_default( ...
        config.segmentation.dual_reference, 'self_test_enabled', true);
    config.segmentation.dual_reference = set_default( ...
        config.segmentation.dual_reference, 'self_test_clean_water_max_sn', 0.05);
    config.segmentation.dual_reference = set_default( ...
        config.segmentation.dual_reference, 'self_test_full_napl_min_sn', 0.85);
    config.segmentation.dual_reference = set_default( ...
        config.segmentation.dual_reference, 'self_test_full_napl_frac_p95_min', 0.80);

    if ~isfield(config.segmentation, 'hsv_red') || ...
            ~isstruct(config.segmentation.hsv_red)
        config.segmentation.hsv_red = struct();
    end
    config.segmentation.hsv_red = set_default( ...
        config.segmentation.hsv_red, 'enabled', true);
    config.segmentation.hsv_red = set_default( ...
        config.segmentation.hsv_red, 'h_high1', 0.03);
    config.segmentation.hsv_red = set_default( ...
        config.segmentation.hsv_red, 'h_high2', 0.97);
    config.segmentation.hsv_red = set_default( ...
        config.segmentation.hsv_red, 'h_low1', 0.07);
    config.segmentation.hsv_red = set_default( ...
        config.segmentation.hsv_red, 'h_low2', 0.93);
    config.segmentation.hsv_red = set_default( ...
        config.segmentation.hsv_red, 's_high', 0.20);
    config.segmentation.hsv_red = set_default( ...
        config.segmentation.hsv_red, 's_low', 0.08);
    config.segmentation.hsv_red = set_default( ...
        config.segmentation.hsv_red, 'v_min', 0.10);
    config.segmentation.hsv_red = set_default( ...
        config.segmentation.hsv_red, 'min_seed_fraction', 0.01);
    config.segmentation.hsv_red = set_default( ...
        config.segmentation.hsv_red, 'frac_hsv_min', 0.02);

    if ~isfield(config.segmentation, 'bulk_check') || ...
            ~isstruct(config.segmentation.bulk_check)
        config.segmentation.bulk_check = struct();
    end
    config.segmentation.bulk_check = set_default( ...
        config.segmentation.bulk_check, 'enabled', false);
    config.segmentation.bulk_check = set_default( ...
        config.segmentation.bulk_check, 'metric', 'dual_reference_fraction_mean');
    config.segmentation.bulk_check = set_default( ...
        config.segmentation.bulk_check, 'max_abs_difference', 0.10);

    if ~isfield(config, 'flow_domain') || ~isstruct(config.flow_domain)
        config.flow_domain = struct();
    end
    config.flow_domain = set_default(config.flow_domain, 'extraction_method', 'auto');
    config.flow_domain = set_default(config.flow_domain, 'color_contrast_min', 5);
    config.flow_domain = set_default(config.flow_domain, 'morph_contrast_min', 0.003);
    config.flow_domain = set_default(config.flow_domain, 'min_pillar_frac', 0.03);
    config.flow_domain = set_default(config.flow_domain, 'max_pillar_frac', 0.70);
    config.flow_domain = set_default(config.flow_domain, 'warn_pillar_frac', 0.05);
    config.flow_domain = set_default(config.flow_domain, 'otsu_min_frac', 0.05);
    config.flow_domain = set_default(config.flow_domain, 'otsu_max_frac', 0.60);
    config.flow_domain = set_default(config.flow_domain, 'bright_min_frac', 0.08);
    config.flow_domain = set_default(config.flow_domain, 'bright_max_frac', 0.55);
    config.flow_domain = set_default(config.flow_domain, 'quantile_min_frac', 0.05);
    config.flow_domain = set_default(config.flow_domain, 'quantile_max_frac', 0.45);
    config.flow_domain = set_default(config.flow_domain, 'target_pillar_frac', 0.18);
    config.flow_domain = set_default(config.flow_domain, 'max_pillar_area_frac', 0.05);
    config.flow_domain = set_default(config.flow_domain, ...
        'white_pillar_sensitivity', 0.45);
    config.flow_domain = set_default(config.flow_domain, ...
        'white_pillar_neighborhood_px', 41);
    config.flow_domain = set_default(config.flow_domain, ...
        'white_pillar_min_area_px', 4);
    config.flow_domain = set_default(config.flow_domain, ...
        'white_pillar_max_area_px', inf);
    config.flow_domain = set_default(config.flow_domain, ...
        'white_pillar_min_circularity', 0.15);
    config.flow_domain = set_default(config.flow_domain, ...
        'solid_mask_path', '');
    config.flow_domain = set_default(config.flow_domain, ...
        'flow_domain_mask_path', '');
    config.flow_domain = set_default(config.flow_domain, ...
        'mask_grid', 'target');
    config.flow_domain = set_default(config.flow_domain, ...
        'mask_resize_method', 'nearest');
    config.flow_domain = set_default(config.flow_domain, ...
        'dxf_boundary_mode', 'circle_bbox');
    config.flow_domain = set_default(config.flow_domain, ...
        'dxf_transform_model', 'affine');
    config.flow_domain = set_default(config.flow_domain, ...
        'expected_porosity', NaN);
    config.flow_domain = set_default(config.flow_domain, ...
        'porosity_tolerance', 0.05);
    config.flow_domain = set_default(config.flow_domain, 'hard_fail', true);

    if ~isfield(config, 'qc') || ~isstruct(config.qc)
        config.qc = struct();
    end
    if ~isfield(config.qc, 'flow_domain') || ~isstruct(config.qc.flow_domain)
        config.qc.flow_domain = struct();
    end
    config.qc.flow_domain = set_default(config.qc.flow_domain, 'hard_fail', true);
    config.qc.flow_domain = set_default(config.qc.flow_domain, 'porosity_min', 0.40);
    config.qc.flow_domain = set_default(config.qc.flow_domain, 'porosity_max', 0.70);
    config.qc.flow_domain = set_default(config.qc.flow_domain, ...
        'pillar_fraction_min', 0.20);

    if ~isfield(config, 'checkpoint') || ~isstruct(config.checkpoint)
        config.checkpoint = struct();
    end
    config.checkpoint = set_default(config.checkpoint, ...
        'allow_legacy_resume', false);

    if ~isfield(config, 'manifest') || ~isstruct(config.manifest)
        config.manifest = struct();
    end
    config.manifest = set_default(config.manifest, 'hash_policy', 'full');

    if ~isfield(config, 'reliability') || ~isstruct(config.reliability)
        config.reliability = struct();
    end
    config.reliability = set_default(config.reliability, ...
        'min_review_native_equiv_diameter_px', 4);
    config.reliability = set_default(config.reliability, ...
        'min_reliable_native_equiv_diameter_px', 8);

    if ~isfield(config, 'geometry') || ~isstruct(config.geometry)
        config.geometry = struct();
    end
    config.geometry = set_default(config.geometry, 'mode', 'core_only');
    config.geometry = set_default(config.geometry, 'schema_version', ...
        geometry_schema_for_mode(config.geometry.mode));
    config.geometry = set_default(config.geometry, 'object_connectivity', 8);
    config.geometry = set_default(config.geometry, 'hole_connectivity', 8);
    config.geometry = set_default(config.geometry, 'include_heavy_shape_props', true);
    config.geometry = set_default(config.geometry, 'roi_pad', 1);
    config.geometry = set_default(config.geometry, 'max_roi_area_fraction', 0.25);
    config.geometry = set_default(config.geometry, 'max_roi_pixels', 2e6);
    config.geometry = set_default(config.geometry, 'large_roi_policy', ...
        'core_only_fallback');
end


function s = set_default(s, field_name, value)
    if ~isfield(s, field_name) || isempty(s.(field_name))
        s.(field_name) = value;
    end
end


function schema = geometry_schema_for_mode(mode)
    mode = char(string(mode));
    switch mode
        case 'roi'
            schema = 'geometry_v3_roi_holes';
        case 'legacy_fullframe'
            schema = 'geometry_v1_legacy_fullframe';
        otherwise
            schema = 'geometry_v2_core_only';
    end
end


function config = reconcile_pixel_size_alias(config)
    physical_px = config.physical.pixel_size;
    calibration_px = config.calibration.native_pixel_size_m;
    physical_is_calibrate = is_calibrate_token(physical_px);
    calibration_is_calibrate = is_calibrate_token(calibration_px);

    if calibration_is_calibrate
        config.calibration.native_pixel_size_m = [];
        calibration_px = [];
        calibration_is_calibrate = false; %#ok<NASGU>
    end

    calibration_has_value = isnumeric(calibration_px) && ~isempty(calibration_px);
    if physical_is_calibrate
        if calibration_has_value
            config.physical.pixel_size = calibration_px;
        end
        return;
    end

    physical_has_value = isnumeric(physical_px) && ~isempty(physical_px);

    if physical_has_value && ~calibration_has_value
        config.calibration.native_pixel_size_m = physical_px;
        return;
    end

    if calibration_has_value && ~physical_has_value
        config.physical.pixel_size = calibration_px;
        return;
    end

    if physical_has_value && calibration_has_value
        if abs(physical_px - calibration_px) > 1e-12
            error('validate_config:badParam', ...
                ['physical.pixel_size and calibration.native_pixel_size_m must ' ...
                 'match within 1e-12. Got %.16g and %.16g.'], ...
                physical_px, calibration_px);
        end
        config.physical.pixel_size = calibration_px;
    end
end


function validate_dual_reference_options(opts)
    if ~isstruct(opts)
        error('validate_config:badParam', ...
            'segmentation.dual_reference must be a struct.');
    end
    valid_channels = {'a', 'b', 'ab', 'lab'};
    valid_feature_modes = {'lab_a', 'lab_ab', 'lab', 'a_plus_chroma', ...
        'normalized_rgb', 'od_fraction'};
    feature_mode = char(string(opts.feature_mode));
    if ~ismember(feature_mode, valid_feature_modes)
        error('validate_config:badParam', ...
            ['segmentation.dual_reference.feature_mode must be one of: %s. ' ...
             'Got "%s".'], strjoin(valid_feature_modes, ', '), feature_mode);
    end
    use_channels = char(string(opts.use_channels));
    if ~ismember(use_channels, valid_channels)
        error('validate_config:badParam', ...
            'segmentation.dual_reference.use_channels must be one of: %s. Got "%s".', ...
            strjoin(valid_channels, ', '), use_channels);
    end
    if isempty(opts.lab_weights) || ~isnumeric(opts.lab_weights) || ...
            numel(opts.lab_weights) ~= 3 || any(~isfinite(opts.lab_weights(:))) || ...
            any(opts.lab_weights(:) < 0)
        error('validate_config:badParam', ...
            ['segmentation.dual_reference.lab_weights must be a numeric ' ...
             'length-3 nonnegative finite vector.']);
    end
    assert_fraction_open_scalar(opts.frac_threshold, ...
        'segmentation.dual_reference.frac_threshold');
    assert_fraction_open_scalar(opts.frac_high, ...
        'segmentation.dual_reference.frac_high');
    assert_fraction_open_scalar(opts.frac_low, ...
        'segmentation.dual_reference.frac_low');
    if opts.frac_high <= opts.frac_low
        error('validate_config:badParam', ...
            'segmentation.dual_reference.frac_high must be greater than frac_low.');
    end
    assert_finite_positive_scalar(opts.min_endpoint_distance, ...
        'segmentation.dual_reference.min_endpoint_distance');
    assert_fraction_zero_to_one_scalar(opts.max_invalid_endpoint_fraction, ...
        'segmentation.dual_reference.max_invalid_endpoint_fraction');
    assert_fraction_zero_to_one_scalar(opts.max_invalid_endpoint_fraction_fail, ...
        'segmentation.dual_reference.max_invalid_endpoint_fraction_fail');
    if opts.max_invalid_endpoint_fraction_fail < opts.max_invalid_endpoint_fraction
        error('validate_config:badParam', ...
            ['segmentation.dual_reference.max_invalid_endpoint_fraction_fail ' ...
             'must be >= max_invalid_endpoint_fraction.']);
    end
    valid_endpoint_modes = {'auto', 'per_pixel', 'robust_global'};
    endpoint_mode = char(string(opts.endpoint_mode));
    if ~ismember(endpoint_mode, valid_endpoint_modes)
        error('validate_config:badParam', ...
            ['segmentation.dual_reference.endpoint_mode must be one of: %s. ' ...
             'Got "%s".'], strjoin(valid_endpoint_modes, ', '), endpoint_mode);
    end
    valid_policies = {'fallback_global', 'warn', 'error'};
    policy = char(string(opts.endpoint_fail_policy));
    if ~ismember(policy, valid_policies)
        error('validate_config:badParam', ...
            ['segmentation.dual_reference.endpoint_fail_policy must be one ' ...
             'of: %s. Got "%s".'], strjoin(valid_policies, ', '), policy);
    end
    assert_logical_scalar(opts.emit_uncertainty_band, ...
        'segmentation.dual_reference.emit_uncertainty_band');
    assert_logical_scalar(opts.use_hsv_seed, ...
        'segmentation.dual_reference.use_hsv_seed');
    assert_logical_scalar(opts.self_test_enabled, ...
        'segmentation.dual_reference.self_test_enabled');
    assert_fraction_zero_to_one_scalar(opts.self_test_clean_water_max_sn, ...
        'segmentation.dual_reference.self_test_clean_water_max_sn');
    assert_fraction_zero_to_one_scalar(opts.self_test_full_napl_min_sn, ...
        'segmentation.dual_reference.self_test_full_napl_min_sn');
    assert_fraction_zero_to_one_scalar(opts.self_test_full_napl_frac_p95_min, ...
        'segmentation.dual_reference.self_test_full_napl_frac_p95_min');
end


function validate_hsv_red_options(opts)
    if ~isstruct(opts)
        error('validate_config:badParam', ...
            'segmentation.hsv_red must be a struct.');
    end
    assert_logical_scalar(opts.enabled, 'segmentation.hsv_red.enabled');
    assert_fraction_zero_to_one_scalar(opts.h_high1, ...
        'segmentation.hsv_red.h_high1');
    assert_fraction_zero_to_one_scalar(opts.h_high2, ...
        'segmentation.hsv_red.h_high2');
    assert_fraction_zero_to_one_scalar(opts.h_low1, ...
        'segmentation.hsv_red.h_low1');
    assert_fraction_zero_to_one_scalar(opts.h_low2, ...
        'segmentation.hsv_red.h_low2');
    assert_fraction_zero_to_one_scalar(opts.s_high, ...
        'segmentation.hsv_red.s_high');
    assert_fraction_zero_to_one_scalar(opts.s_low, ...
        'segmentation.hsv_red.s_low');
    assert_fraction_zero_to_one_scalar(opts.v_min, ...
        'segmentation.hsv_red.v_min');
    assert_fraction_zero_to_one_scalar(opts.min_seed_fraction, ...
        'segmentation.hsv_red.min_seed_fraction');
    assert_fraction_zero_to_one_scalar(opts.frac_hsv_min, ...
        'segmentation.hsv_red.frac_hsv_min');
    if opts.h_high1 > opts.h_low1 || opts.h_high2 < opts.h_low2
        error('validate_config:badParam', ...
            ['HSV high-confidence red hue must be inside the weak hue band: ' ...
             'h_high1 <= h_low1 and h_high2 >= h_low2.']);
    end
    if opts.s_high < opts.s_low
        error('validate_config:badParam', ...
            'segmentation.hsv_red.s_high must be >= s_low.');
    end
end


function validate_bulk_check_options(opts)
    if ~isstruct(opts)
        error('validate_config:badParam', ...
            'segmentation.bulk_check must be a struct.');
    end
    assert_logical_scalar(opts.enabled, 'segmentation.bulk_check.enabled');
    valid_metrics = {'dual_reference_fraction_mean'};
    metric = char(string(opts.metric));
    if ~ismember(metric, valid_metrics)
        error('validate_config:badParam', ...
            'segmentation.bulk_check.metric must be one of: %s. Got "%s".', ...
            strjoin(valid_metrics, ', '), metric);
    end
    assert_fraction_zero_to_one_scalar(opts.max_abs_difference, ...
        'segmentation.bulk_check.max_abs_difference');
end


function opts = validate_flow_domain_mask_options(opts)
    mask_grid = char(string(opts.mask_grid));
    valid_mask_grids = {'target', 'native_full', 'native_cropped', ...
        'processing_grid'};
    if ~ismember(mask_grid, valid_mask_grids)
        error('validate_config:badParam', ...
            'flow_domain.mask_grid must be one of: %s. Got "%s".', ...
            strjoin(valid_mask_grids, ', '), mask_grid);
    end
    opts.mask_grid = mask_grid;

    resize_method = char(string(opts.mask_resize_method));
    valid_resize_methods = {'nearest'};
    if ~ismember(resize_method, valid_resize_methods)
        error('validate_config:badParam', ...
            'flow_domain.mask_resize_method must be one of: %s. Got "%s".', ...
            strjoin(valid_resize_methods, ', '), resize_method);
    end
    opts.mask_resize_method = resize_method;

    dxf_boundary_mode = char(string(opts.dxf_boundary_mode));
    valid_boundary_modes = {'smallest_containing_circles', 'largest_closed_polyline', ...
        'circle_bbox'};
    if ~ismember(dxf_boundary_mode, valid_boundary_modes)
        error('validate_config:badParam', ...
            'flow_domain.dxf_boundary_mode must be one of: %s. Got "%s".', ...
            strjoin(valid_boundary_modes, ', '), dxf_boundary_mode);
    end
    opts.dxf_boundary_mode = dxf_boundary_mode;

    if isfield(opts, 'dxf_transform_model')
        dxf_transform_model = char(string(opts.dxf_transform_model));
        valid_transform_models = {'affine', 'projective'};
        if ~ismember(lower(dxf_transform_model), valid_transform_models)
            error('validate_config:badParam', ...
                'flow_domain.dxf_transform_model must be one of: %s. Got "%s".', ...
                strjoin(valid_transform_models, ', '), dxf_transform_model);
        end
        opts.dxf_transform_model = lower(dxf_transform_model);
    end

    solid_path = string(opts.solid_mask_path);
    pore_path = string(opts.flow_domain_mask_path);
    if strlength(solid_path) > 0 && strlength(pore_path) > 0
        error('validate_config:badParam', ...
            ['Set only one of flow_domain.solid_mask_path or ' ...
             'flow_domain.flow_domain_mask_path.']);
    end
end


function tf = is_dual_reference_method(method)
    tf = ismember(char(string(method)), {'dual_reference_fraction', ...
        'dual_reference_fraction_hysteresis', 'dual_reference_nearest'});
end


function tf = requires_clean_water_reference(method)
    tf = ismember(char(string(method)), {'calibrated_a_threshold', ...
        'calibrated_delta_a', 'dual_reference_fraction', ...
        'dual_reference_fraction_hysteresis', 'dual_reference_nearest'});
end


function tf = is_calibrate_token(value)
    tf = (ischar(value) || (isstring(value) && isscalar(value))) && ...
        strcmpi(value, 'calibrate');
end


function value = read_config_field(config, field_name, default_value)
    if isstruct(config) && isfield(config, field_name) && ...
            ~isempty(config.(field_name))
        value = config.(field_name);
    else
        value = default_value;
    end
end


function assert_text_or_empty(val, name)
    if isempty(val)
        return;
    end
    if ~((ischar(val) && isrow(val)) || (isstring(val) && isscalar(val)))
        error('validate_config:badParam', ...
            '%s must be a string scalar or char row.', name);
    end
end


function s = set_default_bulk_sn(s, field_name, value)
    if ~isfield(s, field_name) || isempty(s.(field_name))
        s.(field_name) = value;
    end
end


function assert_nonempty_text(val, name)
    assert_text_or_empty(val, name);
    if strlength(string(val)) == 0
        error('validate_config:badParam', ...
            '%s must be non-empty for dual-reference segmentation.', name);
    end
end


function assert_crop_rect(val, name)
    if isempty(val)
        return;
    end
    if ~isnumeric(val) || numel(val) ~= 4 || any(~isfinite(val(:))) || ...
            any(val(1:2) < 0) || any(val(3:4) <= 0)
        error('validate_config:badParam', ...
            '%s must be [] or a finite numeric [x y width height] vector.', ...
            name);
    end
end


function assert_positive(val, name)
    if isempty(val) || ~isnumeric(val) || val <= 0
        error('validate_config:badParam', ...
            '%s must be a positive number, got %s.', name, mat2str(val));
    end
end

function assert_nonneg(val, name)
    if isempty(val) || ~isnumeric(val) || val < 0
        error('validate_config:badParam', ...
            '%s must be non-negative, got %s.', name, mat2str(val));
    end
end

function assert_pos_integer(val, name)
    if isempty(val) || ~isnumeric(val) || ~isscalar(val) || val < 1 || mod(val, 1) ~= 0
        error('validate_config:badParam', ...
            '%s must be a positive integer, got %s.', name, mat2str(val));
    end
end

function assert_nonnegative_integer(val, name)
    if isempty(val) || ~isnumeric(val) || ~isscalar(val) || val < 0 || mod(val, 1) ~= 0
        error('validate_config:badParam', ...
            '%s must be a non-negative integer, got %s.', name, mat2str(val));
    end
end

function assert_integer_in_set(val, name, allowed)
    if isempty(val) || ~isnumeric(val) || ~isscalar(val) || mod(val, 1) ~= 0 || ...
            ~ismember(val, allowed)
        error('validate_config:badParam', ...
            '%s must be one of %s, got %s.', name, mat2str(allowed), mat2str(val));
    end
end

function assert_pos_integer_or_inf(val, name)
    if isempty(val) || ~isnumeric(val) || ~isscalar(val)
        error('validate_config:badParam', ...
            '%s must be Inf or a positive integer, got %s.', name, mat2str(val));
    end
    if isinf(val)
        if val < 0
            error('validate_config:badParam', ...
                '%s must be Inf or a positive integer, got %s.', name, mat2str(val));
        end
        return;
    end
    if val < 1 || mod(val, 1) ~= 0
        error('validate_config:badParam', ...
            '%s must be Inf or a positive integer, got %s.', name, mat2str(val));
    end
end

function assert_integer_in_range(val, name, min_val, max_val)
    if isempty(val) || ~isnumeric(val) || ~isscalar(val) || ~isfinite(val) || ...
            val < min_val || val > max_val || mod(val, 1) ~= 0
        error('validate_config:badParam', ...
            '%s must be an integer in [%d, %d], got %s.', ...
            name, min_val, max_val, mat2str(val));
    end
end

function assert_min_finite_positive_scalar(val, name, min_val)
    if isempty(val) || ~isnumeric(val) || ~isscalar(val) || ~isfinite(val) || val < min_val
        error('validate_config:badParam', ...
            '%s must be a finite numeric scalar >= %g, got %s.', ...
            name, min_val, mat2str(val));
    end
end

function assert_logical_scalar(val, name)
    if ~(islogical(val) && isscalar(val))
        error('validate_config:badParam', ...
            '%s must be a logical scalar, got %s.', name, mat2str(val));
    end
end

function assert_fraction_scalar(val, name)
    if isempty(val) || ~isnumeric(val) || ~isscalar(val) || ~isfinite(val) || val <= 0 || val > 1
        error('validate_config:badParam', ...
            '%s must be a finite scalar fraction in (0, 1], got %s.', name, mat2str(val));
    end
end

function assert_fraction_open_scalar(val, name)
    if isempty(val) || ~isnumeric(val) || ~isscalar(val) || ~isfinite(val) || ...
            val <= 0 || val >= 1
        error('validate_config:badParam', ...
            '%s must be a finite scalar fraction in (0, 1), got %s.', ...
            name, mat2str(val));
    end
end

function assert_fraction_zero_to_one_scalar(val, name)
    if isempty(val) || ~isnumeric(val) || ~isscalar(val) || ~isfinite(val) || ...
            val < 0 || val > 1
        error('validate_config:badParam', ...
            '%s must be a finite scalar fraction in [0, 1], got %s.', ...
            name, mat2str(val));
    end
end

function assert_fraction_or_nan(val, name)
    if isempty(val) || ~isnumeric(val) || ~isscalar(val) || ...
            (~isnan(val) && (~isfinite(val) || val <= 0 || val > 1))
        error('validate_config:badParam', ...
            '%s must be NaN or a finite scalar fraction in (0, 1], got %s.', ...
            name, mat2str(val));
    end
end

function assert_finite_positive_scalar(val, name)
    if isempty(val) || ~isnumeric(val) || ~isscalar(val) || ~isfinite(val) || val <= 0
        error('validate_config:badParam', ...
            '%s must be a finite positive scalar, got %s.', name, mat2str(val));
    end
end

function assert_finite_nonnegative_scalar(val, name)
    if isempty(val) || ~isnumeric(val) || ~isscalar(val) || ~isfinite(val) || val < 0
        error('validate_config:badParam', ...
            '%s must be a finite non-negative scalar, got %s.', name, mat2str(val));
    end
end

function assert_nonnegative_or_nan(val, name)
    if isempty(val) || ~isnumeric(val) || ~isscalar(val) || ...
            (~isnan(val) && (~isfinite(val) || val < 0))
        error('validate_config:badParam', ...
            '%s must be NaN or a finite non-negative scalar, got %s.', ...
            name, mat2str(val));
    end
end

function assert_quantile(val, name)
    if isempty(val) || ~isnumeric(val) || ~isscalar(val) || ~isfinite(val) || ...
            val <= 0 || val >= 100
        error('validate_config:badParam', ...
            '%s must be a finite scalar quantile in (0, 100), got %s.', ...
            name, mat2str(val));
    end
end
