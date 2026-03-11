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

    log_files = dir(fullfile(out_dir, 'logs', 'pipeline_log_*.txt'));
    verifyEqual(testCase, numel(log_files), 1);

    log_text = fileread(fullfile(log_files(1).folder, log_files(1).name));
    verifyTrue(testCase, contains(log_text, 'STEP 0: Loading Images'));
    verifyTrue(testCase, contains(log_text, 'STEP 5: Exporting Results'));
    verifyTrue(testCase, contains(log_text, 'Results saved to:'));

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
    verifyFalse(testCase, isfield(saved_data.results.solubilization, 'masks'));
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
