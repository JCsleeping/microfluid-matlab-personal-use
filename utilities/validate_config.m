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

    %% Physical parameters
    if ~(ischar(config.physical.pixel_size) && strcmpi(config.physical.pixel_size, 'calibrate'))
        assert_positive(config.physical.pixel_size, 'physical.pixel_size');
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

    %% Interface parameters
    assert_nonneg(config.interface.solid_dilation, 'interface.solid_dilation');

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
    assert_logical_scalar(config.output.checkpoint, 'output.checkpoint');
    assert_logical_scalar(config.output.save_log, 'output.save_log');
    assert_logical_scalar(config.output.save_progress, 'output.save_progress');
    assert_logical_scalar(config.output.save_heartbeat, 'output.save_heartbeat');
    assert_logical_scalar(config.output.save_blob_detail, 'output.save_blob_detail');
    assert_pos_integer(config.output.save_interval, 'output.save_interval');
    assert_pos_integer(config.output.progress_interval, 'output.progress_interval');
    assert_pos_integer(config.output.heartbeat_frame_interval, 'output.heartbeat_frame_interval');
    assert_pos_integer(config.output.heartbeat_time_interval_sec, 'output.heartbeat_time_interval_sec');
    assert_pos_integer_or_inf(config.output.max_frames_per_session, 'output.max_frames_per_session');

    if isfield(config, 'parallel') && isfield(config.parallel, 'enabled') && ...
            config.parallel.enabled && config.output.save_blob_detail
        error('validate_config:badParam', ...
            ['output.save_blob_detail=true is not supported when parallel.enabled=true. ' ...
             'Set output.save_blob_detail=false or disable parallel processing.']);
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
    valid_seg = {'gmm', 'otsu', 'adaptive', 'gmm_v2', 'otsu_v2'};
    if ~ismember(lower(config.segmentation.method), valid_seg)
        error('validate_config:badParam', ...
            'segmentation.method must be one of: %s. Got "%s".', ...
            strjoin(valid_seg, ', '), config.segmentation.method);
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

function assert_finite_positive_scalar(val, name)
    if isempty(val) || ~isnumeric(val) || ~isscalar(val) || ~isfinite(val) || val <= 0
        error('validate_config:badParam', ...
            '%s must be a finite positive scalar, got %s.', name, mat2str(val));
    end
end
