function arch = classify_residual_architecture(blob, iface, sat, config)
% CLASSIFY_RESIDUAL_ARCHITECTURE  Classify residual DNAPL architecture.
%
%   arch = classify_residual_architecture(blob, iface, sat, config)

    if nargin < 4 || isempty(config)
        config = get_safe_default_config();
    else
        config = ensure_architecture_defaults(config);
    end

    th = config.architecture;

    max_blob_fraction = read_struct_field(blob, {'max_blob_fraction'}, NaN);
    num_blobs = read_struct_field(blob, {'num_blobs'}, NaN);
    a_i_2D = read_struct_field(iface, {'a_i_2D'}, NaN);

    pool_score = 0;
    pool_score = pool_score + double(max_blob_fraction >= th.pool_like.max_blob_fraction_min);
    pool_score = pool_score + double(num_blobs <= th.pool_like.num_blobs_max);
    pool_score = pool_score + double(a_i_2D <= th.pool_like.a_i_2D_max);

    ganglia_score = 0;
    ganglia_score = ganglia_score + double(max_blob_fraction <= th.ganglia_rich.max_blob_fraction_max);
    ganglia_score = ganglia_score + double(num_blobs >= th.ganglia_rich.num_blobs_min);
    ganglia_score = ganglia_score + double(a_i_2D >= th.ganglia_rich.a_i_2D_min);

    if ~isfinite(a_i_2D)
        if pool_score >= 2 && ganglia_score == 0
            arch_type = 'pool-like';
        elseif ganglia_score >= 2 && pool_score == 0
            arch_type = 'ganglia-rich';
        else
            arch_type = 'mixed';
        end
    else
        if pool_score >= 2 && ganglia_score <= 1
            arch_type = 'pool-like';
        elseif ganglia_score >= 2 && pool_score == 0
            arch_type = 'ganglia-rich';
        else
            arch_type = 'mixed';
        end
    end

    arch = struct();
    arch.type = arch_type;
    arch.indicators = struct( ...
        'Sn0', read_struct_field(sat, {'Sn'}, NaN), ...
        'N_b', num_blobs, ...
        'L_ow', read_struct_field(iface, {'dnapl_water_length_m'}, NaN), ...
        'a_i_2D', a_i_2D, ...
        'max_blob_fraction', max_blob_fraction, ...
        'Req_median', read_struct_field(blob, {'Req_distribution', 'median'}, NaN));
    arch.topology = read_struct_field(blob, {'topology_summary'}, struct());
    arch.scatter_data = struct('x', max_blob_fraction, 'y', a_i_2D);
    arch.scores = struct('pool_like', pool_score, 'ganglia_rich', ganglia_score);
    arch.thresholds = th;
end


function config = get_safe_default_config()
    persistent cached_config;

    if isempty(cached_config)
        cached_config = default_architecture_config();
        try
            pipeline_config = config_pipeline();
            if isstruct(pipeline_config) && isfield(pipeline_config, 'architecture')
                cached_config.architecture = pipeline_config.architecture;
            end
        catch
            % Fall back to the local defaults when config_pipeline cannot
            % bootstrap in a hermetic or data-free environment.
        end
    end

    config = cached_config;
end


function config = ensure_architecture_defaults(config)
    defaults = default_architecture_config();

    if ~isstruct(config)
        config = defaults;
        return;
    end

    if ~isfield(config, 'architecture') || ~isstruct(config.architecture)
        config.architecture = defaults.architecture;
        return;
    end

    config.architecture = merge_architecture(config.architecture, defaults.architecture);
end


function architecture = merge_architecture(architecture, defaults)
    if ~isfield(architecture, 'pool_like') || ~isstruct(architecture.pool_like)
        architecture.pool_like = defaults.pool_like;
    else
        architecture.pool_like = merge_scalar_fields(architecture.pool_like, defaults.pool_like);
    end

    if ~isfield(architecture, 'ganglia_rich') || ~isstruct(architecture.ganglia_rich)
        architecture.ganglia_rich = defaults.ganglia_rich;
    else
        architecture.ganglia_rich = merge_scalar_fields(architecture.ganglia_rich, defaults.ganglia_rich);
    end
end


function s = merge_scalar_fields(s, defaults)
    names = fieldnames(defaults);
    for i = 1:numel(names)
        name = names{i};
        if ~isfield(s, name) || isempty(s.(name))
            s.(name) = defaults.(name);
        end
    end
end


function value = read_struct_field(s, path_tokens, default_value)
    value = default_value;
    if ~isstruct(s)
        return;
    end

    current = s;
    for i = 1:numel(path_tokens)
        token = path_tokens{i};
        if ~isstruct(current) || ~isfield(current, token)
            return;
        end
        current = current.(token);
    end

    value = current;
end


function config = default_architecture_config()
    config = struct();
    config.architecture = struct( ...
        'pool_like', struct( ...
            'max_blob_fraction_min', 0.50, ...
            'num_blobs_max', 10, ...
            'a_i_2D_max', 3.0e4), ...
        'ganglia_rich', struct( ...
            'max_blob_fraction_max', 0.30, ...
            'num_blobs_min', 25, ...
            'a_i_2D_min', 6.0e4));
end
