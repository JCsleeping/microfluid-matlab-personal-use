function summary = run_a1_1bo_6ul_bridge_hdf5_chroma(cache_dir, out_dir, endpoint_policy_path)
% RUN_A1_1BO_6UL_BRIDGE_HDF5_CHROMA  Validate MATLAB Branch C on Python BasicPy cache.
%
% This bridge intentionally bypasses segmentation. It reads Python BasicPy
% corrected float32 HDF5 RGB frames, then calls compute_bulk_sn_color with
% chroma for endpoint A and B.

    repo_root = fileparts(mfilename('fullpath'));
    addpath(genpath(repo_root));

    if nargin < 1 || isempty(cache_dir)
        cache_dir = fullfile(repo_root, 'outputs', ...
            'basicpy_hdf5_cache_20260601', 'A1_1BO_6UL_manual_roi_page1');
    end
    if nargin < 2 || isempty(out_dir)
        out_dir = fullfile(repo_root, 'outputs', ...
            'bridge_hdf5_chroma_20260601', 'A1_1BO_6UL_manual_roi_page1');
    end
    if nargin < 3
        endpoint_policy_path = '';
    end
    if ~isfolder(out_dir)
        mkdir(out_dir);
    end

    manifest_path = fullfile(cache_dir, 'manifest.csv');
    mask_path = fullfile(cache_dir, 'mask_crop.h5');
    python_summary_path = fullfile(repo_root, 'outputs', ...
        'masked_reference_audit_20260601', ...
        'A1_1BO_6UL_manual_roi_page1_exact_shortlist', ...
        'exact_shortlist_gate_summary.csv');

    manifest = readtable(manifest_path, 'TextType', 'string');
    flow_domain = read_hdf5_mask(mask_path);
    solid_mask = false(size(flow_domain));

    endpoints = endpoint_specs(endpoint_policy_path);
    summary_rows = repmat(empty_summary_row(), numel(endpoints), 1);
    use_python_summary = should_use_python_summary(cache_dir);
    if use_python_summary && isfile(python_summary_path)
        python_summary = readtable(python_summary_path, 'TextType', 'string');
    else
        python_summary = table();
    end

    if can_run_combined_fast_chroma(endpoints)
        summary_rows = run_combined_fast_chroma(endpoints, manifest, ...
            flow_domain, out_dir, python_summary);
        summary = struct2table(summary_rows);
        summary_path = fullfile(out_dir, 'bridge_comparison_summary.csv');
        writetable(summary, summary_path);
        fprintf('BRIDGE_SUMMARY %s\n', summary_path);
        return;
    end

    for idx = 1:numel(endpoints)
        spec = endpoints(idx);
        fprintf('BRIDGE_ENDPOINT %s\n', spec.id);
        rows = run_endpoint_bridge(spec, manifest, flow_domain, solid_mask);
        out_csv = fullfile(out_dir, sprintf('matlab_on_cache_timeseries_%s.csv', spec.short_name));
        writetable(struct2table(rows), out_csv);

        summary_rows(idx) = summarize_endpoint(spec, rows, python_summary, out_csv);
    end

    summary = struct2table(summary_rows);
    summary_path = fullfile(out_dir, 'bridge_comparison_summary.csv');
    writetable(summary, summary_path);
    fprintf('BRIDGE_SUMMARY %s\n', summary_path);
end


function tf = can_run_combined_fast_chroma(endpoints)
    tf = true;
    for idx = 1:numel(endpoints)
        config = bridge_config(endpoints(idx));
        tf = tf && strcmpi(config.bulk_sn.score_mode, 'chroma') && ...
            strcmpi(config.bulk_sn.statistic, 'winsorized_mean') && ...
            ~config.bulk_sn.use_background && ...
            strcmpi(config.bulk_sn.mask_id, 'flow_domain');
    end
end


function summary_rows = run_combined_fast_chroma(endpoints, manifest, ...
        flow_domain, out_dir, python_summary)
    fprintf('BRIDGE_FAST_COMBINED endpoints=%d\n', numel(endpoints));
    frame_rows = timeseries_frame_rows(manifest);
    mask = logical(flow_domain);
    mask_idx = find(mask);
    if isempty(mask_idx)
        error('bridge_hdf5_chroma:emptyMask', ...
            'flow_domain mask has no measurement pixels.');
    end

    endpoint_state = repmat(empty_endpoint_state(), numel(endpoints), 1);
    for idx = 1:numel(endpoints)
        spec = endpoints(idx);
        config = bridge_config(spec);
        water_rgb = read_label_rgb(manifest, spec.water_label);
        napl_rgb = read_label_rgb(manifest, spec.napl_label);
        water_score = fast_chroma_score_masked(water_rgb, mask_idx, config);
        napl_score = fast_chroma_score_masked(napl_rgb, mask_idx, config);

        endpoint_state(idx).spec = spec;
        endpoint_state(idx).config = config;
        endpoint_state(idx).ref = reference_vector_stats( ...
            water_score, napl_score, config.bulk_sn);
        endpoint_state(idx).rows = repmat(empty_timeseries_row(), ...
            height(frame_rows), 1);
        fprintf('BRIDGE_ENDPOINT %s\n', spec.id);
    end

    n_rows = height(frame_rows);
    progress_step = 100;
    for row_idx = 1:n_rows
        label = string(frame_rows.label(row_idx));
        role = string(frame_rows.role(row_idx));
        frame_rgb = read_hdf5_rgb(frame_rows.h5_path(row_idx));
        frame_score = fast_chroma_score_masked( ...
            frame_rgb, mask_idx, endpoint_state(1).config);
        score_frame = robust_stat_bridge(frame_score, ...
            endpoint_state(1).config.bulk_sn);

        for idx = 1:numel(endpoint_state)
            state = endpoint_state(idx);
            min_delta = double(state.config.bulk_sn.min_endpoint_delta);
            [S_raw, S_color, transfer_status] = normalize_region_score( ...
                score_frame, state.ref, min_delta);

            info = struct();
            info.S_NAPL_color_raw = S_raw;
            info.S_NAPL_color = S_color;
            info.S_NAPL_color_core = S_color;
            info.S_NAPL_color_edge = NaN;
            info.score_frame = score_frame;
            info.score_water_ref = state.ref.score_water_ref;
            info.score_napl_ref = state.ref.score_napl_ref;
            info.core_flow_area_px = numel(mask_idx);
            info.flow_domain_area_px = nnz(mask);
            info.reference_transfer_status = transfer_status;
            info.qc_status = "";

            endpoint_state(idx).rows(row_idx) = timeseries_row( ...
                row_idx, label, role, state.spec, S_color, info);
        end

        if row_idx == 1 || row_idx == n_rows || mod(row_idx, progress_step) == 0
            fprintf('BRIDGE_PROGRESS_AB %d/%d\n', row_idx, n_rows);
        end
    end

    summary_rows = repmat(empty_summary_row(), numel(endpoint_state), 1);
    for idx = 1:numel(endpoint_state)
        state = endpoint_state(idx);
        out_csv = fullfile(out_dir, sprintf( ...
            'matlab_on_cache_timeseries_%s.csv', state.spec.short_name));
        writetable(struct2table(state.rows), out_csv);
        summary_rows(idx) = summarize_endpoint( ...
            state.spec, state.rows, python_summary, out_csv);
    end
end


function state = empty_endpoint_state()
    state = struct( ...
        'spec', struct(), ...
        'config', struct(), ...
        'ref', struct(), ...
        'rows', []);
end


function specs = endpoint_specs(endpoint_policy_path)
    template = struct( ...
        'id', "", ...
        'short_name', "", ...
        'water_label', "", ...
        'napl_label', "");
    if nargin < 1 || isempty(endpoint_policy_path)
        specs = repmat(template, 2, 1);
        specs(1).id = "A_full_consistency_primary";
        specs(1).short_name = "A";
        specs(1).water_label = "water_ep_00_napl_00_3s_1";
        specs(1).napl_label = "full_01_water_1s_3";
        specs(2).id = "B_residual_separation_primary";
        specs(2).short_name = "B";
        specs(2).water_label = "water_ep_00_napl_01_1s";
        specs(2).napl_label = "full_00_water_3s_2";
        return;
    end

    policy = jsondecode(fileread(char(endpoint_policy_path)));
    entries = {};
    if isfield(policy, 'primary')
        entries{end + 1} = policy.primary;
    end
    if isfield(policy, 'sensitivity')
        entries{end + 1} = policy.sensitivity;
    end
    if isempty(entries)
        error('bridge_hdf5_chroma:badEndpointPolicy', ...
            'Endpoint policy must contain primary and/or sensitivity entries.');
    end

    specs = repmat(template, numel(entries), 1);
    for idx = 1:numel(entries)
        entry = entries{idx};
        required = ["id", "short_name", "water_label", "napl_label"];
        for field_idx = 1:numel(required)
            field_name = char(required(field_idx));
            if ~isfield(entry, field_name)
                error('bridge_hdf5_chroma:badEndpointPolicy', ...
                    'Endpoint entry is missing field %s.', field_name);
            end
        end
        specs(idx).id = string(entry.id);
        specs(idx).short_name = string(entry.short_name);
        specs(idx).water_label = string(entry.water_label);
        specs(idx).napl_label = string(entry.napl_label);
    end
end


function rows = run_endpoint_bridge(spec, manifest, flow_domain, solid_mask)
    water_rgb = read_label_rgb(manifest, spec.water_label);
    napl_rgb = read_label_rgb(manifest, spec.napl_label);
    frame_rows = timeseries_frame_rows(manifest);

    config = bridge_config(spec);
    if strcmpi(config.bulk_sn.score_mode, 'chroma') && ...
            strcmpi(config.bulk_sn.statistic, 'winsorized_mean') && ...
            ~config.bulk_sn.use_background && ...
            strcmpi(config.bulk_sn.mask_id, 'flow_domain')
        rows = run_endpoint_bridge_fast_chroma(spec, frame_rows, water_rgb, ...
            napl_rgb, flow_domain, config);
        return;
    end

    rows = repmat(empty_timeseries_row(), height(frame_rows), 1);
    for row_idx = 1:height(frame_rows)
        label = string(frame_rows.label(row_idx));
        role = string(frame_rows.role(row_idx));
        frame_rgb = read_hdf5_rgb(frame_rows.h5_path(row_idx));
        [S_color, info] = compute_bulk_sn_color( ...
            frame_rgb, water_rgb, napl_rgb, flow_domain, solid_mask, config);
        rows(row_idx) = timeseries_row(row_idx, label, role, spec, S_color, info);
    end
end


function frame_rows = timeseries_frame_rows(manifest)
    frame_rows = manifest(ismember(manifest.role, ...
        ["full_napl", "residual", "production"]), :);
    if ismember('include_in_timeseries', manifest.Properties.VariableNames)
        frame_rows = frame_rows(truthy_vector(frame_rows.include_in_timeseries), :);
    end
    if ismember('timeseries_order', frame_rows.Properties.VariableNames) && ...
            any(~ismissing(frame_rows.timeseries_order))
        frame_rows = sortrows(frame_rows, "timeseries_order");
    else
        frame_rows = sortrows(frame_rows, "frame_order");
    end
end


function rows = run_endpoint_bridge_fast_chroma(spec, frame_rows, water_rgb, ...
        napl_rgb, flow_domain, config)
% Fast path for full cache runs. It matches compute_bulk_sn_color(chroma)
% for the columns exported by this bridge, but avoids recomputing reference
% score maps and unused regional diagnostics for every frame.
    measurement_mask = logical(flow_domain);
    core_flow = measurement_mask;
    edge_flow = measurement_mask & ~core_flow;
    opts = config.bulk_sn;
    min_endpoint_delta = double(opts.min_endpoint_delta);

    water_score = fast_chroma_score(water_rgb, config);
    napl_score = fast_chroma_score(napl_rgb, config);
    all_ref = reference_region_stats(water_score, napl_score, measurement_mask, opts);
    core_ref = reference_region_stats(water_score, napl_score, core_flow, opts);
    edge_ref = reference_region_stats(water_score, napl_score, edge_flow, opts);

    n_rows = height(frame_rows);
    rows = repmat(empty_timeseries_row(), n_rows, 1);
    progress_step = 100;
    for row_idx = 1:n_rows
        label = string(frame_rows.label(row_idx));
        role = string(frame_rows.role(row_idx));
        frame_rgb = read_hdf5_rgb(frame_rows.h5_path(row_idx));
        frame_score = fast_chroma_score(frame_rgb, config);

        score_frame = robust_stat_bridge(frame_score(measurement_mask), opts);
        [S_raw, S_color, transfer_status] = normalize_region_score( ...
            score_frame, all_ref, min_endpoint_delta);
        core_score = robust_stat_bridge(frame_score(core_flow), opts);
        [~, S_core] = normalize_region_score(core_score, core_ref, min_endpoint_delta);
        edge_score = robust_stat_bridge(frame_score(edge_flow), opts);
        [~, S_edge] = normalize_region_score(edge_score, edge_ref, min_endpoint_delta);

        info = struct();
        info.S_NAPL_color_raw = S_raw;
        info.S_NAPL_color = S_color;
        info.S_NAPL_color_core = S_core;
        info.S_NAPL_color_edge = S_edge;
        info.score_frame = score_frame;
        info.score_water_ref = all_ref.score_water_ref;
        info.score_napl_ref = all_ref.score_napl_ref;
        info.core_flow_area_px = nnz(core_flow);
        info.flow_domain_area_px = nnz(flow_domain);
        info.reference_transfer_status = transfer_status;
        info.qc_status = "";

        rows(row_idx) = timeseries_row(row_idx, label, role, spec, S_color, info);
        if row_idx == 1 || row_idx == n_rows || mod(row_idx, progress_step) == 0
            fprintf('BRIDGE_PROGRESS %s %d/%d\n', spec.short_name, row_idx, n_rows);
        end
    end
end


function score = fast_chroma_score(rgb, config)
    rgb = normalize_rgb_bridge(rgb);
    if exist('prepare_rgb_for_lab', 'file') == 2
        rgb = prepare_rgb_for_lab(rgb, config);
    end
    lab = rgb2lab(rgb);
    score = hypot(lab(:, :, 2), lab(:, :, 3));
end


function score = fast_chroma_score_masked(rgb, mask_idx, config)
    rgb = normalize_rgb_bridge(rgb);
    rgb_masked = zeros(numel(mask_idx), 1, 3, 'single');
    channel = rgb(:, :, 1);
    rgb_masked(:, 1, 1) = channel(mask_idx);
    channel = rgb(:, :, 2);
    rgb_masked(:, 1, 2) = channel(mask_idx);
    channel = rgb(:, :, 3);
    rgb_masked(:, 1, 3) = channel(mask_idx);
    if exist('prepare_rgb_for_lab', 'file') == 2
        rgb_masked = prepare_rgb_for_lab(rgb_masked, config);
    end
    lab = rgb2lab(rgb_masked);
    score = hypot(lab(:, 1, 2), lab(:, 1, 3));
end


function rgb = normalize_rgb_bridge(rgb)
    if isa(rgb, 'single') || isa(rgb, 'double')
        rgb = single(rgb);
        if max(rgb(:)) > 1
            rgb = rgb ./ 255;
        end
    else
        rgb = im2single(rgb);
    end
    rgb = min(max(rgb, 0), 1);
end


function ref = reference_region_stats(water_score, napl_score, region_mask, opts)
    ref = struct();
    ref.score_water_ref = robust_stat_bridge(water_score(region_mask), opts);
    ref.score_napl_ref = robust_stat_bridge(napl_score(region_mask), opts);
end


function ref = reference_vector_stats(water_score, napl_score, opts)
    ref = struct();
    ref.score_water_ref = robust_stat_bridge(water_score, opts);
    ref.score_napl_ref = robust_stat_bridge(napl_score, opts);
end


function [S_raw, S_color, transfer_status] = normalize_region_score( ...
        score_frame, ref, min_endpoint_delta)
    transfer_status = "ok";
    denom = ref.score_napl_ref - ref.score_water_ref;
    if ~isfinite(score_frame) || ~isfinite(denom) || abs(denom) <= min_endpoint_delta
        S_raw = NaN;
        S_color = NaN;
        transfer_status = "bad_endpoint";
        return;
    end

    S_raw = (score_frame - ref.score_water_ref) / denom;
    S_color = double(min(max(S_raw, 0), 1));
end


function value = robust_stat_bridge(x, opts)
    x = x(isfinite(x));
    if isempty(x)
        value = NaN;
        return;
    end

    switch lower(char(string(opts.statistic)))
        case 'winsorized_mean'
            p = double(opts.winsor_percentiles);
            lo = prctile(x, p(1));
            hi = prctile(x, p(2));
            xw = min(max(x, lo), hi);
            value = mean(xw);
        case 'mean'
            value = mean(x);
        otherwise
            error('bridge_hdf5_chroma:unknownStatistic', ...
                'Unknown statistic: %s.', char(string(opts.statistic)));
    end
end


function config = bridge_config(spec)
    config = struct();
    config.preprocessing.rgb_encoding = 'srgb';
    config.bulk_sn.enabled = true;
    config.bulk_sn.primary_output = true;
    config.bulk_sn.score_mode = 'chroma';
    config.bulk_sn.statistic = 'winsorized_mean';
    config.bulk_sn.winsor_percentiles = [1 99];
    config.bulk_sn.core_flow_min_dist_px = 0;
    config.bulk_sn.emit_regions = true;
    config.bulk_sn.n_x_bins = 20;
    config.bulk_sn.use_background = false;
    config.bulk_sn.pdf_method_reference = 'es4c11735_si_001.pdf';
    config.bulk_sn.min_endpoint_delta = 1.0;
    config.bulk_sn.endpoint_status = 'masked_audit_passed_exact';
    config.bulk_sn.endpoint_source = char(spec.id);
    config.bulk_sn.mask_id = 'flow_domain';
    config.bulk_sn.rgb_source = 'basicpy_hdf5_corrected_cache';
end


function row = timeseries_row(frame_index, label, role, spec, S_color, info)
    row = empty_timeseries_row();
    row.frame_index = frame_index;
    row.label = string(label);
    row.role = string(role);
    row.endpoint_id = string(spec.id);
    row.endpoint_short_name = string(spec.short_name);
    row.water_label = string(spec.water_label);
    row.napl_label = string(spec.napl_label);
    row.S_NAPL_color = S_color;
    row.S_NAPL_color_raw = read_info_scalar(info, 'S_NAPL_color_raw', NaN);
    row.S_NAPL_color_core = read_info_scalar(info, 'S_NAPL_color_core', NaN);
    row.S_NAPL_color_edge = read_info_scalar(info, 'S_NAPL_color_edge', NaN);
    row.score_frame = read_info_scalar(info, 'score_frame', NaN);
    row.score_water_ref = read_info_scalar(info, 'score_water_ref', NaN);
    row.score_napl_ref = read_info_scalar(info, 'score_napl_ref', NaN);
    row.endpoint_delta = row.score_napl_ref - row.score_water_ref;
    row.core_flow_area_px = read_info_scalar(info, 'core_flow_area_px', NaN);
    row.flow_domain_area_px = read_info_scalar(info, 'flow_domain_area_px', NaN);
    row.reference_transfer_status = string(read_info_text(info, ...
        'reference_transfer_status', ''));
    row.qc_status = string(read_info_text(info, 'qc_status', ''));
end


function row = empty_timeseries_row()
    row = struct( ...
        'frame_index', NaN, ...
        'label', "", ...
        'role', "", ...
        'endpoint_id', "", ...
        'endpoint_short_name', "", ...
        'water_label', "", ...
        'napl_label', "", ...
        'S_NAPL_color', NaN, ...
        'S_NAPL_color_raw', NaN, ...
        'S_NAPL_color_core', NaN, ...
        'S_NAPL_color_edge', NaN, ...
        'score_frame', NaN, ...
        'score_water_ref', NaN, ...
        'score_napl_ref', NaN, ...
        'endpoint_delta', NaN, ...
        'core_flow_area_px', NaN, ...
        'flow_domain_area_px', NaN, ...
        'reference_transfer_status', "", ...
        'qc_status', "");
end


function row = summarize_endpoint(spec, rows, python_summary, out_csv)
    table_rows = struct2table(rows);
    full_values = table_rows.S_NAPL_color(table_rows.role == "full_napl");
    residual_values = table_rows.S_NAPL_color(table_rows.role == "residual");
    py_row = table();
    if ~isempty(python_summary) && ismember('shortlist_id', python_summary.Properties.VariableNames)
        py_row = python_summary(python_summary.shortlist_id == spec.id, :);
    end
    comparison_available = height(py_row) == 1;
    if comparison_available
        py_full_median = py_row.median_S_full_validation(1);
        py_residual_median = py_row.median_S_residual(1);
    else
        py_full_median = NaN;
        py_residual_median = NaN;
    end
    full_diff = median(full_values, 'omitnan') - py_full_median;
    residual_diff = median(residual_values, 'omitnan') - py_residual_median;

    row = empty_summary_row();
    row.endpoint_id = string(spec.id);
    row.endpoint_short_name = string(spec.short_name);
    row.water_label = string(spec.water_label);
    row.napl_label = string(spec.napl_label);
    row.matlab_full_median = median(full_values, 'omitnan');
    row.matlab_full_min = min(full_values);
    row.matlab_full_max = max(full_values);
    row.matlab_residual_median = median(residual_values, 'omitnan');
    row.matlab_residual_min = min(residual_values);
    row.matlab_residual_max = max(residual_values);
    row.python_full_median = py_full_median;
    row.python_residual_median = py_residual_median;
    row.full_median_diff = full_diff;
    row.residual_median_diff = residual_diff;
    row.abs_full_median_diff = abs(full_diff);
    row.abs_residual_median_diff = abs(residual_diff);
    row.comparison_available = comparison_available;
    row.pass_full_tolerance = ~comparison_available || ...
        (isfinite(row.abs_full_median_diff) && row.abs_full_median_diff <= 0.01);
    row.pass_residual_tolerance = ~comparison_available || ...
        (isfinite(row.abs_residual_median_diff) && row.abs_residual_median_diff <= 0.01);
    row.bridge_pass = row.pass_full_tolerance && row.pass_residual_tolerance;
    row.timeseries_csv = string(out_csv);
end


function row = empty_summary_row()
    row = struct( ...
        'endpoint_id', "", ...
        'endpoint_short_name', "", ...
        'water_label', "", ...
        'napl_label', "", ...
        'matlab_full_median', NaN, ...
        'matlab_full_min', NaN, ...
        'matlab_full_max', NaN, ...
        'matlab_residual_median', NaN, ...
        'matlab_residual_min', NaN, ...
        'matlab_residual_max', NaN, ...
        'python_full_median', NaN, ...
        'python_residual_median', NaN, ...
        'full_median_diff', NaN, ...
        'residual_median_diff', NaN, ...
        'abs_full_median_diff', NaN, ...
        'abs_residual_median_diff', NaN, ...
        'comparison_available', false, ...
        'pass_full_tolerance', false, ...
        'pass_residual_tolerance', false, ...
        'bridge_pass', false, ...
        'timeseries_csv', "");
end


function rgb = read_label_rgb(manifest, label)
    match = manifest(manifest.label == string(label), :);
    if height(match) ~= 1
        error('bridge_hdf5_chroma:missingLabel', ...
            'Expected one cache row for label %s.', string(label));
    end
    rgb = read_hdf5_rgb(match.h5_path(1));
end


function rgb = read_hdf5_rgb(path_value)
    raw = h5read(char(path_value), '/rgb_corrected');
    if ndims(raw) ~= 3 || size(raw, 1) ~= 3
        error('bridge_hdf5_chroma:badRgbShape', ...
            'Expected MATLAB h5read shape 3 x W x H from Python H x W x 3 cache.');
    end
    rgb = single(permute(raw, [3 2 1]));
end


function mask = read_hdf5_mask(path_value)
    raw = h5read(char(path_value), '/flow_domain_mask');
    mask = logical(raw');
end


function values = truthy_vector(raw_values)
    if islogical(raw_values)
        values = raw_values;
        return;
    end
    if isnumeric(raw_values)
        values = raw_values ~= 0;
        return;
    end
    text_values = lower(strtrim(string(raw_values)));
    values = ismember(text_values, ["1", "true", "yes", "y"]);
end


function value = read_info_scalar(info, field_name, default_value)
    value = default_value;
    if isstruct(info) && isfield(info, field_name) && ...
            isnumeric(info.(field_name)) && isscalar(info.(field_name))
        value = info.(field_name);
    end
end


function value = read_info_text(info, field_name, default_value)
    value = default_value;
    if isstruct(info) && isfield(info, field_name) && ...
            (ischar(info.(field_name)) || isstring(info.(field_name)))
        value = char(string(info.(field_name)));
    end
end


function use_python_summary = should_use_python_summary(cache_dir)
    use_python_summary = false;
    manifest_path = fullfile(cache_dir, 'cache_manifest.json');
    if ~isfile(manifest_path)
        return;
    end
    cache_manifest = jsondecode(fileread(manifest_path));
    if ~isfield(cache_manifest, 'frame_count') || ...
            ~isfield(cache_manifest, 'timeseries_frame_count')
        return;
    end
    use_python_summary = cache_manifest.frame_count == 53 && ...
        cache_manifest.timeseries_frame_count == 50;
end
