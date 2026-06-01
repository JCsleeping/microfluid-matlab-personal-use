function outputs = run_a1_1bo_6ul_hdf5_cache_branch_c_pipeline(cache_dir, out_dir, endpoint_policy_path)
% RUN_A1_1BO_6UL_HDF5_CACHE_BRANCH_C_PIPELINE  Cache-fed Branch C Sn(t) pipeline.
%
% The primary quantitative input is the Python BasicPy HDF5 cache. This
% runner intentionally keeps segmentation-derived mask Sn out of the primary
% output and promotes chroma S_NAPL_color as the operational color-index Sn(t).

    repo_root = fileparts(mfilename('fullpath'));
    addpath(genpath(repo_root));

    if nargin < 1 || isempty(cache_dir)
        cache_dir = fullfile(repo_root, 'outputs', ...
            'basicpy_hdf5_cache_20260601', 'A1_1BO_6UL_manual_roi_page1');
    end
    if nargin < 2 || isempty(out_dir)
        out_dir = fullfile(repo_root, 'outputs', ...
            'hdf5_cache_branch_c_pipeline_20260601', ...
            'A1_1BO_6UL_manual_roi_page1');
    end
    if nargin < 3
        endpoint_policy_path = '';
    end
    if ~isfolder(out_dir)
        mkdir(out_dir);
    end

    assert_cache_ready(cache_dir);
    summary = run_a1_1bo_6ul_bridge_hdf5_chroma( ...
        cache_dir, out_dir, endpoint_policy_path);

    row_A = single_summary_row(summary, "A");
    row_B = single_summary_row(summary, "B");
    ts_A = readtable(char(row_A.timeseries_csv(1)), 'TextType', 'string');
    ts_B = readtable(char(row_B.timeseries_csv(1)), 'TextType', 'string');

    primary_A = add_output_semantics(ts_A, "primary", ...
        "S_NAPL_color operational color-index saturation", ...
        "A_full_consistency_primary");
    sensitivity_B = add_output_semantics(ts_B, "sensitivity", ...
        "S_NAPL_color endpoint sensitivity check", ...
        "B_residual_separation_primary");
    comparison = build_sensitivity_comparison(primary_A, sensitivity_B);

    primary_path = fullfile(out_dir, 'S_NAPL_color_primary_A.csv');
    sensitivity_path = fullfile(out_dir, 'S_NAPL_color_sensitivity_B.csv');
    comparison_path = fullfile(out_dir, 'S_NAPL_color_A_B_sensitivity_comparison.csv');
    summary_path = fullfile(out_dir, 'branch_c_cache_pipeline_summary.csv');
    manifest_path = fullfile(out_dir, 'cache_branch_c_manifest.json');
    plot_path = fullfile(out_dir, 'S_NAPL_color_A_B_sensitivity.png');

    writetable(primary_A, primary_path);
    writetable(sensitivity_B, sensitivity_path);
    writetable(comparison, comparison_path);
    writetable(summary, summary_path);
    write_pipeline_manifest(manifest_path, cache_dir, out_dir, ...
        endpoint_policy_path, summary, primary_path, sensitivity_path, ...
        comparison_path, plot_path);
    plot_sensitivity(primary_A, sensitivity_B, plot_path);

    outputs = struct();
    outputs.output_dir = out_dir;
    outputs.summary = summary;
    outputs.primary_csv = primary_path;
    outputs.sensitivity_csv = sensitivity_path;
    outputs.comparison_csv = comparison_path;
    outputs.summary_csv = summary_path;
    outputs.manifest_json = manifest_path;
    outputs.plot_png = plot_path;

    fprintf('CACHE_BRANCH_C_PIPELINE %s\n', out_dir);
end


function assert_cache_ready(cache_dir)
    required = { ...
        fullfile(cache_dir, 'manifest.csv'), ...
        fullfile(cache_dir, 'cache_manifest.json'), ...
        fullfile(cache_dir, 'mask_crop.h5')};
    for idx = 1:numel(required)
        if ~isfile(required{idx})
            error('hdf5_cache_branch_c_pipeline:missingCacheFile', ...
                ['Missing required cache file: %s\nRun: ' ...
                 'python run_a1_1bo_6ul_build_basicpy_hdf5_cache.py --force'], ...
                required{idx});
        end
    end
end


function row = single_summary_row(summary, short_name)
    row = summary(summary.endpoint_short_name == string(short_name), :);
    if height(row) ~= 1
        error('hdf5_cache_branch_c_pipeline:badSummary', ...
            'Expected exactly one endpoint %s summary row.', short_name);
    end
end


function table_out = add_output_semantics(table_in, output_role, semantics, endpoint_id)
    table_out = table_in;
    table_out.output_role = repmat(string(output_role), height(table_out), 1);
    table_out.output_name = repmat("S_NAPL_color", height(table_out), 1);
    table_out.output_semantics = repmat(string(semantics), height(table_out), 1);
    table_out.endpoint_policy = repmat(string(endpoint_id), height(table_out), 1);
    table_out.segmentation_mask_role = repmat("not_used_for_primary_sn", height(table_out), 1);
end


function comparison = build_sensitivity_comparison(primary_A, sensitivity_B)
    if height(primary_A) ~= height(sensitivity_B)
        error('hdf5_cache_branch_c_pipeline:frameCountMismatch', ...
            'Endpoint A and B timeseries row counts differ.');
    end
    if any(primary_A.label ~= sensitivity_B.label)
        error('hdf5_cache_branch_c_pipeline:labelMismatch', ...
            'Endpoint A and B timeseries labels differ.');
    end

    comparison = table();
    comparison.frame_index = primary_A.frame_index;
    comparison.label = primary_A.label;
    comparison.role = primary_A.role;
    comparison.S_NAPL_color_A = primary_A.S_NAPL_color;
    comparison.S_NAPL_color_B = sensitivity_B.S_NAPL_color;
    comparison.S_NAPL_color_B_minus_A = ...
        comparison.S_NAPL_color_B - comparison.S_NAPL_color_A;
    comparison.abs_endpoint_sensitivity = abs(comparison.S_NAPL_color_B_minus_A);
end


function write_pipeline_manifest(path_value, cache_dir, out_dir, ...
        endpoint_policy_path, summary, primary_path, sensitivity_path, ...
        comparison_path, plot_path)
    manifest = struct();
    manifest.pipeline = 'A1_1BO_6UL_HDF5_cache_Branch_C_chroma';
    manifest.created_at = datestr(now, 'yyyy-mm-ddTHH:MM:SS');
    manifest.cache_dir = cache_dir;
    manifest.output_dir = out_dir;
    manifest.endpoint_policy_path = endpoint_policy_path;
    manifest.cache_contract = 'basicpy_hdf5_float32_hwc';
    manifest.primary_output = 'S_NAPL_color';
    manifest.primary_output_semantics = ...
        'operational color-index saturation from BasicPy corrected RGB';
    manifest.primary_endpoint = 'A_full_consistency_primary';
    manifest.sensitivity_endpoint = 'B_residual_separation_primary';
    manifest.segmentation_mask_role = 'secondary_visualization_diagnostics_only';
    manifest.score_mode = 'chroma';
    manifest.statistic = 'winsorized_mean';
    manifest.winsor_percentiles = [1, 99];
    manifest.endpoint_status = 'masked_audit_passed_exact';
    manifest.full_napl_median_A = summary.matlab_full_median( ...
        summary.endpoint_short_name == "A");
    manifest.residual_median_A = summary.matlab_residual_median( ...
        summary.endpoint_short_name == "A");
    manifest.full_napl_median_B = summary.matlab_full_median( ...
        summary.endpoint_short_name == "B");
    manifest.residual_median_B = summary.matlab_residual_median( ...
        summary.endpoint_short_name == "B");
    manifest.bridge_pass = all(summary.bridge_pass);
    manifest.files = struct( ...
        'primary_csv', primary_path, ...
        'sensitivity_csv', sensitivity_path, ...
        'comparison_csv', comparison_path, ...
        'plot_png', plot_path);

    fid = fopen(path_value, 'w');
    if fid < 0
        error('hdf5_cache_branch_c_pipeline:manifestOpenFailed', ...
            'Cannot write manifest: %s', path_value);
    end
    cleanup = onCleanup(@() fclose(fid));
    fwrite(fid, jsonencode(manifest), 'char');
end


function plot_sensitivity(primary_A, sensitivity_B, path_value)
    fig = figure('Visible', 'off', 'Color', 'w');
    cleaner = onCleanup(@() close(fig));
    x = primary_A.frame_index;
    plot(x, primary_A.S_NAPL_color, '-o', 'LineWidth', 1.2, ...
        'DisplayName', 'Endpoint A primary');
    hold on;
    plot(x, sensitivity_B.S_NAPL_color, '-s', 'LineWidth', 1.2, ...
        'DisplayName', 'Endpoint B sensitivity');
    xlabel('Frame index');
    ylabel('S\_NAPL\_color');
    title('BasicPy HDF5 Branch C chroma S\_NAPL\_color');
    grid on;
    legend('Location', 'best');
    exportgraphics(fig, path_value, 'Resolution', 150);
end
