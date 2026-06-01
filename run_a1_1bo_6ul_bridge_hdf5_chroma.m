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
    if isfile(python_summary_path)
        python_summary = readtable(python_summary_path, 'TextType', 'string');
    else
        python_summary = table();
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

    config = bridge_config(spec);
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
    if height(py_row) == 1
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
    row.pass_full_tolerance = isfinite(row.abs_full_median_diff) && ...
        row.abs_full_median_diff <= 0.01;
    row.pass_residual_tolerance = isfinite(row.abs_residual_median_diff) && ...
        row.abs_residual_median_diff <= 0.01;
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
