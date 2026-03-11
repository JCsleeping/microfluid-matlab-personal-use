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
    assert_pos_integer(config.output.save_interval, 'output.save_interval');
    assert_pos_integer(config.output.progress_interval, 'output.progress_interval');

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

function assert_logical_scalar(val, name)
    if ~(islogical(val) && isscalar(val))
        error('validate_config:badParam', ...
            '%s must be a logical scalar, got %s.', name, mat2str(val));
    end
end
