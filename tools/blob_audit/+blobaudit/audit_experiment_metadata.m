function info = audit_experiment_metadata(audit, opts)
% AUDIT_EXPERIMENT_METADATA  Check physical/time/transport metadata aliases.

    external = blobaudit.read_simple_metadata_file(char(opts.ExperimentMetadataFile));
    sources = {external};
    if isfield(audit.results_info, 'config')
        sources{end + 1} = audit.results_info.config;
    end
    sources{end + 1} = audit.results_info;

    keys = metadata_keys();
    rows = cell(numel(keys), 6);
    found_any_required_missing = false;
    for idx = 1:numel(keys)
        key = keys(idx).canonical;
        aliases = keys(idx).aliases;
        [found, value, source_name] = lookup_alias(sources, aliases);
        if strcmp(key, 'frame_interval_s') && ~found && isfield(audit.schema_info, 'has') && ...
                isfield(audit.schema_info.has, 'FrameTime') && audit.schema_info.has.FrameTime
            found = true;
            value = 'FrameTime column';
            source_name = 'blob_table';
        end
        if strcmp(key, 'pixel_size_um') && isfield(audit.results_info, 'has_pixel_scale') && audit.results_info.has_pixel_scale
            found = true;
            value = num2str(audit.results_info.pixel_size);
            source_name = 'results_or_config';
        end
        if strcmp(key, 'frame_interval_s') && isfield(audit.results_info, 'frame_interval') && isfinite(audit.results_info.frame_interval)
            found = true;
            value = num2str(audit.results_info.frame_interval);
            source_name = 'results_or_config';
        end
        rows(idx, :) = {key, found, source_name, value, keys(idx).unit, keys(idx).required_for};
        if ~found && keys(idx).required
            found_any_required_missing = true;
        end
    end

    metadata_key = rows(:, 1);
    found = cell2mat(rows(:, 2));
    source_file = rows(:, 3);
    value_preview = rows(:, 4);
    unit = rows(:, 5);
    required_for = rows(:, 6);
    missing_impact = cell(numel(found), 1);
    for idx = 1:numel(found)
        if found(idx)
            missing_impact{idx} = '';
        else
            missing_impact{idx} = ['Missing metadata limits ' required_for{idx}];
        end
    end
    info = struct();
    info.experiment_metadata = table(metadata_key, found, source_file, value_preview, ...
        unit, required_for, missing_impact);
    info.is_incomplete = found_any_required_missing;
    info.has_pixel_scale = any(strcmp(metadata_key, 'pixel_size_um') & found);
    info.has_time = any(strcmp(metadata_key, 'frame_interval_s') & found);
    info.has_flow = any(strcmp(metadata_key, 'flow_rate') & found);
    info.has_treatment = any(strcmp(metadata_key, 'surfactant_concentration') & found);
end


function keys = metadata_keys()
    keys = struct('canonical', {}, 'aliases', {}, 'unit', {}, 'required_for', {}, 'required', {});
    keys(end+1) = item('pixel_size_um', {'pixel_size', 'pixel_size_um', 'px_um', 'micron_per_pixel', 'um_per_px', 'scale_um_per_px'}, 'um/px', 'physical area and length', true);
    keys(end+1) = item('frame_interval_s', {'FrameTime', 'frame_times', 'time_arr', 'time_vector', 't', 'timestamp', 'frame_interval', 'dt', 'time_interval', 'seconds_per_frame'}, 's', 'dissolution rate', true);
    keys(end+1) = item('flow_rate', {'flow_rate', 'Q', 'injection_rate', 'pump_rate'}, '', 'transport interpretation', true);
    keys(end+1) = item('surfactant_concentration', {'surfactant_concentration', 'C_surfactant', 'tween80_percent', 'cmc_ratio'}, '', 'treatment comparison', true);
    keys(end+1) = item('surfactant_type', {'surfactant', 'surfactant_type', 'chemical', 'treatment'}, '', 'treatment grouping', false);
    keys(end+1) = item('viscosity', {'viscosity', 'mu'}, 'Pa*s', 'capillary number', false);
    keys(end+1) = item('interfacial_tension', {'interfacial_tension', 'IFT', 'gamma'}, 'N/m', 'capillary number', false);
    keys(end+1) = item('diffusion_coefficient', {'diffusion_coefficient', 'diffusion_coeff', 'D'}, 'm^2/s', 'Peclet/Sherwood proxy', false);
    keys(end+1) = item('channel_height', {'channel_height', 'depth', 'h'}, 'm', 'volume proxy', false);
    keys(end+1) = item('temperature', {'temperature', 'T_C'}, 'C', 'property correction', false);
    keys(end+1) = item('porous_geometry_mask', {'pore_mask', 'solid_mask', 'porous_geometry_mask'}, '', 'exposure proxy', false);
end


function s = item(canonical, aliases, unit, required_for, required)
    s = struct('canonical', canonical, 'aliases', {aliases}, 'unit', unit, ...
        'required_for', required_for, 'required', required);
end


function [found, value, source_name] = lookup_alias(sources, aliases)
    found = false;
    value = '';
    source_name = '';
    alias_norm = blobaudit.normalize_var_names(aliases);
    for idx = 1:numel(sources)
        S = sources{idx};
        [found, value] = recursive_lookup(S, alias_norm);
        if found
            source_name = sprintf('source_%d', idx);
            return;
        end
    end
end


function [found, value] = recursive_lookup(S, alias_norm)
    found = false;
    value = '';
    if ~isstruct(S)
        return;
    end
    names = fieldnames(S);
    norm_names = blobaudit.normalize_var_names(names);
    for idx = 1:numel(names)
        if any(strcmp(norm_names{idx}, alias_norm))
            if value_is_present(S.(names{idx}))
                found = true;
                value = value_to_text(S.(names{idx}));
                return;
            end
        end
        if isstruct(S.(names{idx}))
            [found, value] = recursive_lookup(S.(names{idx}), alias_norm);
            if found, return; end
        end
    end
end


function tf = value_is_present(v)
    if isnumeric(v)
        tf = ~isempty(v) && any(isfinite(v(:)));
    elseif ischar(v)
        tf = ~isempty(strtrim(v));
    elseif isstring(v)
        tf = ~isempty(v) && any(strlength(v(:)) > 0);
    else
        tf = ~isempty(v);
    end
end


function txt = value_to_text(v)
    if isnumeric(v)
        txt = mat2str(v(1:min(numel(v), 3)));
    elseif ischar(v)
        txt = v;
    elseif isstring(v)
        txt = char(v(1));
    else
        txt = class(v);
    end
end
