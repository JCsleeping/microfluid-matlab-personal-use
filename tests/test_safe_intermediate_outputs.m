function tests = test_safe_intermediate_outputs
% Regression tests for safe logging and lightweight progress snapshots.
    tests = functiontests(localfunctions);
end


function test_config_exposes_safe_output_defaults(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    config = config_pipeline();

    verifyTrue(testCase, isfield(config, 'output'));
    verifyTrue(testCase, isfield(config.output, 'save_log'));
    verifyTrue(testCase, config.output.save_log);
    verifyTrue(testCase, isfield(config.output, 'save_progress'));
    verifyFalse(testCase, config.output.save_progress);
    verifyTrue(testCase, isfield(config.output, 'progress_interval'));
    verifyEqual(testCase, config.output.progress_interval, 50);
    verifyTrue(testCase, isfield(config.output, 'save_heartbeat'));
    verifyTrue(testCase, config.output.save_heartbeat);
    verifyTrue(testCase, isfield(config.output, 'heartbeat_frame_interval'));
    verifyEqual(testCase, config.output.heartbeat_frame_interval, 10);
    verifyTrue(testCase, isfield(config.output, 'heartbeat_time_interval_sec'));
    verifyEqual(testCase, config.output.heartbeat_time_interval_sec, 30);
    verifyTrue(testCase, isfield(config.output, 'max_frames_per_session'));
    verifyTrue(testCase, isinf(config.output.max_frames_per_session));
end


function test_config_rejects_invalid_safe_output_settings(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    verifyError(testCase, ...
        @() config_pipeline('output.save_log', 7), ...
        'validate_config:badParam');
    verifyError(testCase, ...
        @() config_pipeline('output.save_progress', -1), ...
        'validate_config:badParam');
    verifyError(testCase, ...
        @() config_pipeline('output.progress_interval', 0), ...
        'validate_config:badParam');
    verifyError(testCase, ...
        @() config_pipeline('output.save_heartbeat', 4), ...
        'validate_config:badParam');
    verifyError(testCase, ...
        @() config_pipeline('output.heartbeat_frame_interval', 0), ...
        'validate_config:badParam');
    verifyError(testCase, ...
        @() config_pipeline('output.heartbeat_time_interval_sec', 0), ...
        'validate_config:badParam');
    verifyError(testCase, ...
        @() config_pipeline('output.max_frames_per_session', 0), ...
        'validate_config:badParam');
    verifyError(testCase, ...
        @() config_pipeline('output.max_frames_per_session', 4, 'output.checkpoint', false), ...
        'validate_config:badParam');
    verifyError(testCase, ...
        @() config_pipeline('output.max_frames_per_session', 5, 'output.save_interval', 2), ...
        'validate_config:badParam');
    verifyError(testCase, ...
        @() config_pipeline('output.max_frames_per_session', 4, 'parallel.enabled', true), ...
        'validate_config:badParam');
end


function test_main_pipeline_writes_log_and_progress_snapshot(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    old_vis = get(groot, 'defaultFigureVisible');
    set(groot, 'defaultFigureVisible', 'off');
    c1 = onCleanup(@() set(groot, 'defaultFigureVisible', old_vis)); %#ok<NASGU>

    out_dir = fullfile(tempdir, ['dnapl_safe_outputs_' datestr(now, 'yyyymmdd_HHMMSSFFF')]);
    c2 = onCleanup(@() cleanup_tempdir(out_dir)); %#ok<NASGU>

    config = config_pipeline( ...
        'pages', 1:2, ...
        'physical.pixel_size', 3.92e-6, ...
        'preprocess.manual_crop_rect', [380 40 1821 1927], ...
        'flow_domain_crop_rect', [372 66 1821 1933], ...
        'illumination.kernel_size', 30, ...
        'visualization.show_figures', false, ...
        'visualization.save_figures', false, ...
        'parallel.enabled', false, ...
        'output_path', out_dir, ...
        'output.save_progress', true, ...
        'output.progress_interval', 1, ...
        'output.checkpoint', false);

    results = main_DNAPL_pipeline(config);

    verifyTrue(testCase, isfield(results, 'solubilization'));
    verifyTrue(testCase, isfield(results, 'chip_geometric_volume_m3'));
    verifyTrue(testCase, isfield(results, 'flow_domain_volume_m3'));
    verifyTrue(testCase, isfield(results.saturation, 'dnapl_volume_m3'));
    chip_mask = results.flow_domain | results.solid_mask;
    chip_area_px = sum(chip_mask(:));
    verifyEqual(testCase, results.chip_geometric_volume_m3, ...
        chip_area_px * config.physical.pixel_size^2 * config.physical.depth, 'AbsTol', 1e-18);
    verifyEqual(testCase, results.flow_domain_volume_m3, ...
        results.saturation.pore_area_m2 * config.physical.depth, 'AbsTol', 1e-18);
    verifyEqual(testCase, results.saturation.dnapl_volume_m3, ...
        results.saturation.dnapl_area_m2 * config.physical.depth, 'AbsTol', 1e-18);

    log_files = dir(fullfile(out_dir, 'logs', 'pipeline_log_*.txt'));
    verifyEqual(testCase, numel(log_files), 1);

    log_text = fileread(fullfile(log_files(1).folder, log_files(1).name));
    verifyTrue(testCase, contains(log_text, 'STEP 0: Loading Images'));
    verifyTrue(testCase, contains(log_text, 'STEP 5: Exporting Results'));
    verifyTrue(testCase, contains(log_text, 'Results saved to:'));

    heartbeat_path = fullfile(out_dir, 'status', 'heartbeat_latest.json');
    verifyTrue(testCase, isfile(heartbeat_path));
    heartbeat = jsondecode(fileread(heartbeat_path));
    verifyEqual(testCase, string(heartbeat.status), "completed");
    verifyEqual(testCase, string(heartbeat.step), "STEP 5");
    verifyEqual(testCase, heartbeat.current_frame, 2);
    verifyEqual(testCase, heartbeat.total_frames, 2);
    verifyTrue(testCase, isfield(heartbeat, 'updated_at'));
    verifyTrue(testCase, isfield(heartbeat, 'message'));
    verifyTrue(testCase, isfield(heartbeat, 'matlab_pid'));
    verifyGreaterThan(testCase, heartbeat.matlab_pid, 0);
    verifyTrue(testCase, isfield(heartbeat, 'hostname'));

    mat_path = fullfile(out_dir, 'progress', 'progress_latest.mat');
    csv_path = fullfile(out_dir, 'progress', 'progress_latest.csv');
    verifyTrue(testCase, isfile(mat_path));
    verifyTrue(testCase, isfile(csv_path));

    progress_data = load(mat_path, 'progress');
    verifyTrue(testCase, isfield(progress_data, 'progress'));
    verifyEqual(testCase, progress_data.progress.last_frame, 2);
    verifyEqual(testCase, numel(progress_data.progress.Sn), 2);
    verifyEqual(testCase, numel(progress_data.progress.NumBlobs), 2);
    verifyEqual(testCase, numel(progress_data.progress.MeanBlobSize), 2);
    verifyEqual(testCase, numel(progress_data.progress.InterfaceArea), 2);
    verifyTrue(testCase, isfield(progress_data.progress, 'locked_threshold'));
    verifyTrue(testCase, isfield(progress_data.progress, 'updated_at'));

    T = readtable(csv_path);
    verifyEqual(testCase, height(T), 2);
    verifyTrue(testCase, all(ismember( ...
        {'Time', 'Sn', 'NumBlobs', 'MeanBlobSize', 'InterfaceArea'}, ...
        T.Properties.VariableNames)));

    result_files = dir(fullfile(out_dir, 'results_*.mat'));
    verifyGreaterThanOrEqual(testCase, numel(result_files), 1);
    saved_data = load(fullfile(result_files(1).folder, result_files(1).name), 'results');
    verifyTrue(testCase, isfield(saved_data, 'results'));
    verifyTrue(testCase, isfield(saved_data.results, 'chip_geometric_volume_m3'));
    verifyTrue(testCase, isfield(saved_data.results, 'flow_domain_volume_m3'));
    verifyTrue(testCase, isfield(saved_data.results.saturation, 'dnapl_volume_m3'));
    verifyFalse(testCase, isfield(saved_data.results.solubilization, 'masks'));

    sat_files = dir(fullfile(out_dir, 'saturation_*.csv'));
    verifyEqual(testCase, numel(sat_files), 1);
    sat_table = readtable(fullfile(sat_files(1).folder, sat_files(1).name));
    verifyTrue(testCase, all(ismember( ...
        {'Sn', 'Sw', 'DNAPL_area_px', 'Pore_area_px', 'Chip_volume_m3', 'Pore_volume_m3', 'DNAPL_volume_m3'}, ...
        sat_table.Properties.VariableNames)));
    verifyEqual(testCase, sat_table.Chip_volume_m3(1), results.chip_geometric_volume_m3, 'AbsTol', 1e-18);
    verifyEqual(testCase, sat_table.Pore_volume_m3(1), results.flow_domain_volume_m3, 'AbsTol', 1e-18);
    verifyEqual(testCase, sat_table.DNAPL_volume_m3(1), results.saturation.dnapl_volume_m3, 'AbsTol', 1e-18);

    timeseries_files = dir(fullfile(out_dir, 'timeseries_*.csv'));
    verifyEqual(testCase, numel(timeseries_files), 1);
    timeseries_table = readtable(fullfile(timeseries_files(1).folder, timeseries_files(1).name));
    verifyFalse(testCase, any(strcmp(timeseries_table.Properties.VariableNames, 'Pore_volume_m3')));
    verifyFalse(testCase, any(strcmp(timeseries_table.Properties.VariableNames, 'DNAPL_volume_m3')));

    report_txt = fileread(fullfile(out_dir, 'analysis_report.txt'));
    verifyTrue(testCase, contains(report_txt, 'Chip Geometric Volume'));
    verifyTrue(testCase, contains(report_txt, 'Flow Domain Pore Volume'));
    verifyTrue(testCase, contains(report_txt, 'DNAPL Volume'));
end


function test_main_pipeline_keeps_only_first_and_last_masks_in_memory(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    old_vis = get(groot, 'defaultFigureVisible');
    set(groot, 'defaultFigureVisible', 'off');
    c1 = onCleanup(@() set(groot, 'defaultFigureVisible', old_vis)); %#ok<NASGU>

    out_dir = fullfile(tempdir, ['dnapl_mask_stream_' datestr(now, 'yyyymmdd_HHMMSSFFF')]);
    c2 = onCleanup(@() cleanup_tempdir(out_dir)); %#ok<NASGU>

    config = config_pipeline( ...
        'pages', 1:3, ...
        'physical.pixel_size', 3.92e-6, ...
        'preprocess.manual_crop_rect', [380 40 1821 1927], ...
        'flow_domain_crop_rect', [372 66 1821 1933], ...
        'illumination.kernel_size', 30, ...
        'visualization.show_figures', false, ...
        'visualization.save_figures', false, ...
        'parallel.enabled', false, ...
        'output_path', out_dir, ...
        'output.save_progress', false, ...
        'output.checkpoint', false);

    results = main_DNAPL_pipeline(config);
    masks = results.solubilization.masks;

    verifyEqual(testCase, numel(masks), 3);
    verifyFalse(testCase, isempty(masks{1}));
    verifyTrue(testCase, isempty(masks{2}));
    verifyFalse(testCase, isempty(masks{3}));
    verifyEqual(testCase, numel(results.solubilization.change), 2);
end


function test_main_pipeline_pauses_on_checkpoint_boundary_and_resumes(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    old_vis = get(groot, 'defaultFigureVisible');
    set(groot, 'defaultFigureVisible', 'off');
    c1 = onCleanup(@() set(groot, 'defaultFigureVisible', old_vis)); %#ok<NASGU>

    out_dir = fullfile(tempdir, ['dnapl_session_pause_' datestr(now, 'yyyymmdd_HHMMSSFFF')]);
    c2 = onCleanup(@() cleanup_tempdir(out_dir)); %#ok<NASGU>

    config = config_pipeline( ...
        'pages', 1:6, ...
        'physical.pixel_size', 3.92e-6, ...
        'preprocess.manual_crop_rect', [380 40 1821 1927], ...
        'flow_domain_crop_rect', [372 66 1821 1933], ...
        'illumination.kernel_size', 30, ...
        'visualization.show_figures', false, ...
        'visualization.save_figures', false, ...
        'parallel.enabled', false, ...
        'output_path', out_dir, ...
        'output.checkpoint', true, ...
        'output.save_interval', 2, ...
        'output.max_frames_per_session', 2, ...
        'output.save_progress', false);

    results1 = main_DNAPL_pipeline(config);
    verifyEqual(testCase, string(results1.pipeline_status), "paused");
    verifyEqual(testCase, results1.resume_from_frame, 3);
    verifyTrue(testCase, isfield(results1, 'chip_geometric_volume_m3'));
    verifyTrue(testCase, isfield(results1, 'flow_domain_volume_m3'));
    verifyTrue(testCase, isfield(results1.saturation, 'dnapl_volume_m3'));
    verifyTrue(testCase, isfile(fullfile(out_dir, 'checkpoint_0002.mat')));
    verifyEmpty(testCase, dir(fullfile(out_dir, 'results_*.mat')));
    checkpoint1 = fullfile(out_dir, 'checkpoint_0002.mat');
    checkpoint1_vars = who('-file', checkpoint1);
    verifyTrue(testCase, any(strcmp(checkpoint1_vars, 'locked_threshold')));

    heartbeat1 = jsondecode(fileread(fullfile(out_dir, 'status', 'heartbeat_latest.json')));
    verifyEqual(testCase, string(heartbeat1.status), "paused");
    verifyEqual(testCase, heartbeat1.current_frame, 2);

    results2 = main_DNAPL_pipeline(config);
    verifyEqual(testCase, string(results2.pipeline_status), "paused");
    verifyEqual(testCase, results2.resume_from_frame, 5);
    verifyTrue(testCase, isfile(fullfile(out_dir, 'checkpoint_0004.mat')));
    checkpoint2 = fullfile(out_dir, 'checkpoint_0004.mat');
    checkpoint2_vars = who('-file', checkpoint2);
    verifyTrue(testCase, any(strcmp(checkpoint2_vars, 'locked_threshold')));

    heartbeat2 = jsondecode(fileread(fullfile(out_dir, 'status', 'heartbeat_latest.json')));
    verifyEqual(testCase, string(heartbeat2.status), "paused");
    verifyEqual(testCase, heartbeat2.current_frame, 4);
    log_files = dir(fullfile(out_dir, 'logs', 'pipeline_log_*.txt'));
    [~, latest_log_idx] = max([log_files.datenum]);
    resume_log_text = fileread(fullfile(log_files(latest_log_idx).folder, log_files(latest_log_idx).name));
    verifyTrue(testCase, contains(resume_log_text, 'Using locked threshold from checkpoint'));
    verifyFalse(testCase, contains(resume_log_text, 'Threshold locked at'));

    results3 = main_DNAPL_pipeline(config);
    verifyEqual(testCase, string(results3.pipeline_status), "completed");
    verifyFalse(testCase, isfield(results3, 'resume_from_frame'));
    verifyFalse(testCase, isempty(dir(fullfile(out_dir, 'results_*.mat'))));

    heartbeat3 = jsondecode(fileread(fullfile(out_dir, 'status', 'heartbeat_latest.json')));
    verifyEqual(testCase, string(heartbeat3.status), "completed");
    verifyEqual(testCase, heartbeat3.current_frame, 6);
end


function test_legacy_checkpoint_marks_task4_history_unknown(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    fixture_dir = fullfile(tempdir, ['dnapl_legacy_checkpoint_' datestr(now, 'yyyymmdd_HHMMSSFFF')]);
    c1 = onCleanup(@() cleanup_tempdir(fixture_dir)); %#ok<NASGU>
    mkdir(fixture_dir);

    [frame_index, flow_domain, time_vector] = create_synthetic_checkpoint_fixture(fixture_dir);
    config = make_synthetic_step4_config(fixture_dir, size(flow_domain));

    sol1 = characterize_solubilization_v2(frame_index, flow_domain, time_vector, config);
    verifyEqual(testCase, string(sol1.pipeline_status), "paused");

    checkpoint_path = fullfile(fixture_dir, 'checkpoint_0002.mat');
    verifyTrue(testCase, isfile(checkpoint_path));
    rewrite_checkpoint_as_legacy(checkpoint_path);

    checkpoint_vars = who('-file', checkpoint_path);
    verifyTrue(testCase, any(strcmp(checkpoint_vars, 'locked_threshold')));
    verifyFalse(testCase, any(ismember(task4_checkpoint_metric_fields(), checkpoint_vars)));

    lastwarn('');
    sol2 = characterize_solubilization_v2(frame_index, flow_domain, time_vector, config);
    [warn_msg, warn_id] = lastwarn;

    verifyEqual(testCase, warn_id, 'characterize_solubilization_v2:legacyResidualMetricsCheckpoint');
    verifyTrue(testCase, contains(warn_msg, 'marked NaN'));
    verifyEqual(testCase, string(sol2.pipeline_status), "completed");

    historical_idx = 1:2;
    resumed_idx = 3:4;

    verifyTrue(testCase, all(isnan(sol2.max_blob_frac_vs_time(historical_idx))));
    verifyTrue(testCase, all(isnan(sol2.Req_mean_vs_time(historical_idx))));
    verifyTrue(testCase, all(isnan(sol2.mean_circularity_vs_time(historical_idx))));
    verifyTrue(testCase, all(isnan(sol2.a_i_2D_vs_time(historical_idx))));
    verifyTrue(testCase, all(isnan(sol2.n_droplets_vs_time(historical_idx))));
    verifyTrue(testCase, all(isnan(sol2.frac_droplets_vs_time(historical_idx))));

    verifyTrue(testCase, all(isfinite(sol2.max_blob_frac_vs_time(resumed_idx))));
    verifyTrue(testCase, all(isfinite(sol2.Req_mean_vs_time(resumed_idx))));
    verifyTrue(testCase, all(isfinite(sol2.mean_circularity_vs_time(resumed_idx))));
    verifyTrue(testCase, all(isfinite(sol2.a_i_2D_vs_time(resumed_idx))));
    verifyTrue(testCase, all(isfinite(sol2.n_droplets_vs_time(resumed_idx))));
    verifyTrue(testCase, all(isfinite(sol2.frac_droplets_vs_time(resumed_idx))));

    verifyTrue(testCase, all(isfinite(sol2.num_blobs_vs_time(historical_idx))));
    verifyTrue(testCase, all(isfinite(sol2.mean_blob_size_vs_time(historical_idx))));
end


function test_prefixed_ai2d_checkpoint_units_mark_history_unknown(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    fixture_dir = fullfile(tempdir, ['dnapl_ai2d_checkpoint_' datestr(now, 'yyyymmdd_HHMMSSFFF')]);
    c1 = onCleanup(@() cleanup_tempdir(fixture_dir)); %#ok<NASGU>
    mkdir(fixture_dir);

    [frame_index, flow_domain, time_vector] = create_synthetic_checkpoint_fixture(fixture_dir);
    config = make_synthetic_step4_config(fixture_dir, size(flow_domain));
    config.physical.pixel_size = 2.0;

    sol1 = characterize_solubilization_v2(frame_index, flow_domain, time_vector, config);
    verifyEqual(testCase, string(sol1.pipeline_status), "paused");

    checkpoint_path = fullfile(fixture_dir, 'checkpoint_0002.mat');
    verifyTrue(testCase, isfile(checkpoint_path));
    checkpoint_vars = who('-file', checkpoint_path);
    verifyTrue(testCase, any(strcmp(checkpoint_vars, 'a_i_2D_arr')));
    verifyTrue(testCase, any(strcmp(checkpoint_vars, 'a_i_2D_units')));
    verifyTrue(testCase, any(strcmp(checkpoint_vars, 'a_i_2D_pixel_size')));

    rewrite_checkpoint_without_ai2d_units(checkpoint_path);
    checkpoint_vars = who('-file', checkpoint_path);
    verifyTrue(testCase, any(strcmp(checkpoint_vars, 'a_i_2D_arr')));
    verifyFalse(testCase, any(strcmp(checkpoint_vars, 'a_i_2D_units')));
    verifyFalse(testCase, any(strcmp(checkpoint_vars, 'a_i_2D_pixel_size')));

    lastwarn('');
    sol2 = characterize_solubilization_v2(frame_index, flow_domain, time_vector, config);
    [warn_msg, warn_id] = lastwarn;

    verifyEqual(testCase, warn_id, 'characterize_solubilization_v2:legacyAi2DCheckpointUnits');
    verifyTrue(testCase, contains(warn_msg, 'a_i_2D'));
    verifyEqual(testCase, string(sol2.pipeline_status), "completed");

    historical_idx = 1:2;
    resumed_idx = 3:4;

    verifyTrue(testCase, all(isnan(sol2.a_i_2D_vs_time(historical_idx))));
    verifyTrue(testCase, all(isfinite(sol2.a_i_2D_vs_time(resumed_idx))));
    verifyTrue(testCase, all(isfinite(sol2.max_blob_frac_vs_time(historical_idx))));
    verifyTrue(testCase, all(isfinite(sol2.mean_circularity_vs_time(historical_idx))));
end


function test_blob_detail_status_line_reports_disabled_and_enabled_path(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    fixture_dir = fullfile(tempdir, ['dnapl_blob_detail_status_' datestr(now, 'yyyymmdd_HHMMSSFFF')]);
    c1 = onCleanup(@() cleanup_tempdir(fixture_dir)); %#ok<NASGU>
    mkdir(fixture_dir);

    [frame_index, flow_domain, time_vector] = create_synthetic_checkpoint_fixture(fixture_dir);
    config = make_synthetic_step4_config(fixture_dir, size(flow_domain));
    config.output.checkpoint = false;
    config.output.max_frames_per_session = inf;

    disabled_log = evalc('characterize_solubilization_v2(frame_index, flow_domain, time_vector, config);');
    verifyTrue(testCase, contains(disabled_log, ...
        'Per-blob detail CSV: disabled (set output.save_blob_detail=true for sequential runs)'));

    config.output.save_blob_detail = true;
    expected_path = fullfile(config.output_path, 'blob_detail_all_frames.csv');
    enabled_log = evalc('characterize_solubilization_v2(frame_index, flow_domain, time_vector, config);');
    verifyTrue(testCase, contains(enabled_log, ['Per-blob detail CSV: ' expected_path]));

    if isfile(expected_path)
        delete(expected_path);
    end
    config.parallel.enabled = true;
    parallel_frame_index = frame_index(1);
    parallel_time_vector = time_vector(1);
    parallel_log = evalc('sol_parallel = characterize_solubilization_v2(parallel_frame_index, flow_domain, parallel_time_vector, config);');
    verifyTrue(testCase, contains(parallel_log, ...
        'Per-blob detail CSV: disabled in parallel mode'));
    verifyFalse(testCase, contains(parallel_log, ['Per-blob detail CSV: ' expected_path]));
    verifyFalse(testCase, isfield(sol_parallel, 'blob_detail_csv'));
    verifyFalse(testCase, isfile(expected_path));
end


function cleanup_tempdir(out_dir)
    if isfolder(out_dir)
        try
            rmdir(out_dir, 's');
        catch
            % Best effort cleanup for test output.
        end
    end
end


function rewrite_checkpoint_without_ai2d_units(checkpoint_path)
    checkpoint_data = load(checkpoint_path);
    if isfield(checkpoint_data, 'a_i_2D_units')
        checkpoint_data = rmfield(checkpoint_data, 'a_i_2D_units');
    end
    if isfield(checkpoint_data, 'a_i_2D_pixel_size')
        checkpoint_data = rmfield(checkpoint_data, 'a_i_2D_pixel_size');
    end
    if isfield(checkpoint_data, 'a_i_2D_arr')
        checkpoint_data.a_i_2D_arr(1:checkpoint_data.last_frame) = ...
            (1:checkpoint_data.last_frame).';
    end
    save(checkpoint_path, '-v7.3', '-struct', 'checkpoint_data');
end


function rewrite_checkpoint_as_legacy(checkpoint_path)
    checkpoint_data = load(checkpoint_path);
    field_names = task4_checkpoint_metric_fields();
    for i = 1:numel(field_names)
        field_name = field_names{i};
        if isfield(checkpoint_data, field_name)
            checkpoint_data = rmfield(checkpoint_data, field_name);
        end
    end
    save(checkpoint_path, '-v7.3', '-struct', 'checkpoint_data');
end


function field_names = task4_checkpoint_metric_fields()
    field_names = { ...
        'max_blob_frac_arr', ...
        'Req_median_arr', ...
        'Req_mean_arr', ...
        'Req_std_arr', ...
        'mean_circularity_arr', ...
        'a_i_2D_arr', ...
        'n_droplets_arr', ...
        'n_columns_arr', ...
        'n_clusters_arr', ...
        'frac_droplets_arr', ...
        'frac_columns_arr', ...
        'frac_clusters_arr'};
end


function [frame_index, flow_domain, time_vector] = create_synthetic_checkpoint_fixture(fixture_dir)
    flow_domain = true(32, 32);
    time_vector = (0:3).';
    frame_masks = cell(4, 1);
    frame_masks{1} = false(32, 32);
    frame_masks{1}(4:15, 4:15) = true;
    frame_masks{2} = false(32, 32);
    frame_masks{2}(5:12, 5:12) = true;
    frame_masks{2}(20:25, 20:24) = true;
    frame_masks{3} = false(32, 32);
    frame_masks{3}(6:10, 6:10) = true;
    frame_masks{3}(18:22, 19:22) = true;
    frame_masks{4} = false(32, 32);
    frame_masks{4}(8:11, 8:11) = true;

    frame_index = repmat(struct('tif_path', '', 'page', 1), numel(frame_masks), 1);
    for i = 1:numel(frame_masks)
        rgb = render_mask_frame(frame_masks{i});
        tif_path = fullfile(fixture_dir, sprintf('frame_%02d.tif', i));
        imwrite(rgb, tif_path);
        frame_index(i).tif_path = tif_path;
        frame_index(i).page = 1;
    end
end


function rgb = render_mask_frame(mask)
    rgb = uint8(235 * ones([size(mask), 3]));
    rgb(:, :, 2) = uint8(230);
    rgb(:, :, 3) = uint8(230);

    red_channel = rgb(:, :, 1);
    green_channel = rgb(:, :, 2);
    blue_channel = rgb(:, :, 3);

    red_channel(mask) = 220;
    green_channel(mask) = 40;
    blue_channel(mask) = 60;

    rgb(:, :, 1) = red_channel;
    rgb(:, :, 2) = green_channel;
    rgb(:, :, 3) = blue_channel;
end


function config = make_synthetic_step4_config(output_dir, image_size)
    config = struct();
    config.segmentation = struct( ...
        'method', 'otsu', ...
        'fixed_threshold', NaN, ...
        'min_blob_area', 1, ...
        'morph_radius', 0, ...
        'num_components', 2);
    config.physical = struct( ...
        'pixel_size', 1.0, ...
        'depth', 1.0, ...
        'dnapl_density', 1.0);
    config.parallel = struct( ...
        'enabled', false, ...
        'use_gpu', false, ...
        'num_workers', 1);
    config.illumination = struct( ...
        'method', 'morphological', ...
        'kernel_size', 1);
    config.registration = struct('method', 'none');
    config.preprocess = struct( ...
        'rotation_angle', 0, ...
        'manual_crop_rect', [1, 1, image_size(2) - 1, image_size(1) - 1], ...
        'saved_crop_rect', []);
    config.interface = struct('solid_dilation', 1);
    config.output = struct( ...
        'save_progress', false, ...
        'progress_interval', 1, ...
        'checkpoint', true, ...
        'save_interval', 2, ...
        'max_frames_per_session', 2, ...
        'save_blob_detail', false);
    config.output_path = output_dir;
end
