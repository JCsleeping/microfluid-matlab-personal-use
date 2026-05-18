function info = inspect_results_mat(inventory)
% INSPECT_RESULTS_MAT  Safely inspect results/checkpoint/config MAT files.

    info = struct();
    info.files_inspected = {};
    info.variables_found = {};
    info.variables_missing = {};
    info.has_results_mat = any(strcmp(inventory.file_type, 'results_mat'));
    info.has_config = false;
    info.has_nblobs_arr = false;
    info.nblobs_arr = [];
    info.last_completed_frame = NaN;
    info.has_frame_times = false;
    info.frame_times = [];
    info.has_pixel_scale = false;
    info.pixel_size = NaN;
    info.frame_interval = NaN;
    info.config = struct();

    mat_rows = strcmp(inventory.file_type, 'results_mat') | ...
        strcmp(inventory.file_type, 'checkpoint_mat') | ...
        (strcmp(inventory.file_type, 'config_file') & strcmp(inventory.extension, '.mat'));
    paths = inventory.path(mat_rows);
    candidates = {'results', 'sol', 'config', 'nblobs_arr', 'last_completed_frame', ...
        'last_frame', 'frame_times', 'time_arr', 'time_vector', 'pages', ...
        'pixel_size', 'pixel_size_um', 'scale', 'frame_interval'};

    for idx = 1:numel(paths)
        mat_path = paths{idx};
        info.files_inspected{end + 1} = mat_path; %#ok<AGROW>
        try
            vars = whos('-file', mat_path);
            names = {vars.name};
            info.variables_found = unique([info.variables_found, names], 'stable');
            load_names = candidates(ismember(candidates, names));
            if isempty(load_names)
                continue;
            end
            S = load(mat_path, load_names{:});
            info = harvest_loaded_struct(info, S);
        catch ME
            info.variables_missing{end + 1} = sprintf('%s: %s', mat_path, ME.message); %#ok<AGROW>
        end
    end
end


function info = harvest_loaded_struct(info, S)
    if isfield(S, 'config')
        info.has_config = true;
        info.config = S.config;
        info = harvest_config(info, S.config);
    end
    if isfield(S, 'results')
        R = S.results;
        if isfield(R, 'solubilization')
            info = harvest_sol(info, R.solubilization);
        end
        if isfield(R, 'time_vector')
            info.frame_times = R.time_vector(:);
            info.has_frame_times = true;
        end
        if isfield(R, 'config')
            info.has_config = true;
            info.config = R.config;
            info = harvest_config(info, R.config);
        end
    end
    if isfield(S, 'sol')
        info = harvest_sol(info, S.sol);
    end
    if isfield(S, 'nblobs_arr')
        info.has_nblobs_arr = true;
        info.nblobs_arr = S.nblobs_arr(:);
    end
    if isfield(S, 'last_completed_frame')
        info.last_completed_frame = double(S.last_completed_frame);
    elseif isfield(S, 'last_frame')
        info.last_completed_frame = double(S.last_frame);
    end
    time_fields = {'frame_times', 'time_arr', 'time_vector'};
    for idx = 1:numel(time_fields)
        f = time_fields{idx};
        if isfield(S, f) && isnumeric(S.(f))
            info.has_frame_times = true;
            info.frame_times = S.(f)(:);
        end
    end
    scale_fields = {'pixel_size', 'pixel_size_um', 'scale'};
    for idx = 1:numel(scale_fields)
        f = scale_fields{idx};
        if isfield(S, f) && isnumeric(S.(f)) && ~isempty(S.(f))
            info.has_pixel_scale = true;
            info.pixel_size = double(S.(f)(1));
        end
    end
    if isfield(S, 'frame_interval') && isnumeric(S.frame_interval)
        info.frame_interval = double(S.frame_interval(1));
    end
end


function info = harvest_sol(info, sol)
    if isfield(sol, 'num_blobs_vs_time')
        info.has_nblobs_arr = true;
        info.nblobs_arr = sol.num_blobs_vs_time(:);
    end
    if isfield(sol, 'last_completed_frame')
        info.last_completed_frame = double(sol.last_completed_frame);
    end
end


function info = harvest_config(info, config)
    if isfield(config, 'physical')
        if isfield(config.physical, 'pixel_size') && isnumeric(config.physical.pixel_size)
            info.has_pixel_scale = true;
            info.pixel_size = double(config.physical.pixel_size);
        end
        if isfield(config.physical, 'depth') && isnumeric(config.physical.depth)
            info.channel_height = config.physical.depth;
        end
    end
    if isfield(config, 'time_interval') && isnumeric(config.time_interval) && ~isempty(config.time_interval)
        info.frame_interval = double(config.time_interval(1));
    end
    if isfield(config, 'time_vector') && isnumeric(config.time_vector) && ~isempty(config.time_vector)
        info.has_frame_times = true;
        info.frame_times = config.time_vector(:);
    end
end
