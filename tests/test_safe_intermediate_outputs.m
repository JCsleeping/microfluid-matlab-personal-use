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


function cleanup_tempdir(out_dir)
    if isfolder(out_dir)
        try
            rmdir(out_dir, 's');
        catch
            % Best effort cleanup for test output.
        end
    end
end
