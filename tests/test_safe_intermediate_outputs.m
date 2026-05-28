function tests = test_safe_intermediate_outputs
% Regression tests for safe logging and lightweight progress snapshots.
    tests = functiontests(localfunctions);
end


function test_config_exposes_safe_output_defaults(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    [fixture_dir, tif_path] = create_config_tif_fixture();
    c = onCleanup(@() cleanup_tempdir(fixture_dir)); %#ok<NASGU>

    config = config_pipeline('data_path', fixture_dir, ...
        'multipage_tif_path', {tif_path}, ...
        'output_path', fullfile(fixture_dir, 'out'));

    verifyTrue(testCase, isfield(config, 'output'));
    verifyTrue(testCase, isfield(config.output, 'save_log'));
    verifyTrue(testCase, config.output.save_log);
    verifyTrue(testCase, isfield(config.output, 'save_progress'));
    verifyFalse(testCase, config.output.save_progress);
    verifyTrue(testCase, isfield(config.output, 'progress_interval'));
    verifyEqual(testCase, config.output.progress_interval, 50);
    verifyTrue(testCase, isfield(config.output, 'save_heartbeat'));
    verifyTrue(testCase, config.output.save_heartbeat);
    verifyTrue(testCase, isfield(config.output, 'save_blob_detail'));
    verifyTrue(testCase, config.output.save_blob_detail);
    verifyTrue(testCase, isfield(config.output, 'heartbeat_frame_interval'));
    verifyEqual(testCase, config.output.heartbeat_frame_interval, 10);
    verifyTrue(testCase, isfield(config.output, 'heartbeat_time_interval_sec'));
    verifyEqual(testCase, config.output.heartbeat_time_interval_sec, 30);
    verifyTrue(testCase, isfield(config.output, 'max_frames_per_session'));
    verifyTrue(testCase, isinf(config.output.max_frames_per_session));
    verifyTrue(testCase, isfield(config, 'geometry'));
    verifyEqual(testCase, config.geometry.mode, 'core_only');
    verifyEqual(testCase, config.geometry.object_connectivity, 8);
    verifyEqual(testCase, config.geometry.schema_version, 'geometry_v2_core_only');
    verifyTrue(testCase, config.geometry.include_heavy_shape_props);
    verifyEqual(testCase, config.geometry.roi_pad, 1);
    verifyEqual(testCase, config.geometry.max_roi_area_fraction, 0.25);
    verifyEqual(testCase, config.geometry.max_roi_pixels, 2e6);
end


function test_config_rejects_invalid_safe_output_settings(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    [fixture_dir, tif_path] = create_config_tif_fixture();
    c = onCleanup(@() cleanup_tempdir(fixture_dir)); %#ok<NASGU>
    make_config = @(varargin) config_pipeline('data_path', fixture_dir, ...
        'multipage_tif_path', {tif_path}, ...
        'output_path', fullfile(fixture_dir, 'out'), varargin{:});

    verifyError(testCase, ...
        @() make_config('output.save_log', 7), ...
        'validate_config:badParam');
    verifyError(testCase, ...
        @() make_config('output.save_progress', -1), ...
        'validate_config:badParam');
    verifyError(testCase, ...
        @() make_config('output.progress_interval', 0), ...
        'validate_config:badParam');
    verifyError(testCase, ...
        @() make_config('output.save_heartbeat', 4), ...
        'validate_config:badParam');
    verifyError(testCase, ...
        @() make_config('output.heartbeat_frame_interval', 0), ...
        'validate_config:badParam');
    verifyError(testCase, ...
        @() make_config('output.heartbeat_time_interval_sec', 0), ...
        'validate_config:badParam');
    verifyError(testCase, ...
        @() make_config('output.max_frames_per_session', 0), ...
        'validate_config:badParam');
    verifyError(testCase, ...
        @() make_config('output.max_frames_per_session', 4, 'output.checkpoint', false), ...
        'validate_config:badParam');
    verifyError(testCase, ...
        @() make_config('output.max_frames_per_session', 5, 'output.save_interval', 2), ...
        'validate_config:badParam');
    verifyError(testCase, ...
        @() make_config('output.max_frames_per_session', 4, 'parallel.enabled', true), ...
        'validate_config:badParam');
    verifyError(testCase, ...
        @() make_config('geometry.mode', 'not_a_mode'), ...
        'validate_config:badParam');
    verifyError(testCase, ...
        @() make_config('geometry.object_connectivity', 6), ...
        'validate_config:badParam');
end


function test_main_pipeline_writes_log_and_progress_snapshot(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));
    assume_default_tif_available(testCase);

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
    assume_default_tif_available(testCase);

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


function test_step4_pauses_on_checkpoint_boundary_and_resumes(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    out_dir = fullfile(tempdir, ['dnapl_session_pause_' datestr(now, 'yyyymmdd_HHMMSSFFF')]);
    c1 = onCleanup(@() cleanup_tempdir(out_dir)); %#ok<NASGU>
    mkdir(out_dir);

    [frame_index, flow_domain, time_vector] = create_synthetic_checkpoint_fixture(out_dir, 6);
    config = make_synthetic_step4_config(out_dir, size(flow_domain));
    config.output.save_blob_detail = true;
    config.output.blob_detail_chunk_size = 10;
    config.output.blob_detail_save_format = 'v7';

    sol1 = characterize_solubilization_v2(frame_index, flow_domain, time_vector, config);
    results1 = struct('pipeline_status', sol1.pipeline_status, ...
        'resume_from_frame', sol1.resume_from_frame, ...
        'solubilization', sol1);
    verifyEqual(testCase, string(results1.pipeline_status), "paused");
    verifyEqual(testCase, results1.resume_from_frame, 3);
    verifyTrue(testCase, isfile(fullfile(out_dir, 'checkpoint_0002.mat')));
    checkpoint1 = fullfile(out_dir, 'checkpoint_0002.mat');
    checkpoint1_vars = who('-file', checkpoint1);
    verifyTrue(testCase, any(strcmp(checkpoint1_vars, 'locked_threshold')));
    verifyTrue(testCase, isfolder(fullfile(out_dir, 'blob_detail_chunks')));
    verifyTrue(testCase, isfile(fullfile(out_dir, 'blob_detail_chunks', ...
        'blob_detail_000001_000002.mat')));
    verifyFalse(testCase, isfile(fullfile(out_dir, 'blob_detail_all_frames.csv')));
    verifyFalse(testCase, results1.solubilization.blob_detail_csv_exported);
    verifyEqual(testCase, results1.solubilization.blob_detail_csv, '');

    sol2 = characterize_solubilization_v2(frame_index, flow_domain, time_vector, config);
    results2 = struct('pipeline_status', sol2.pipeline_status, ...
        'resume_from_frame', sol2.resume_from_frame, ...
        'solubilization', sol2);
    verifyEqual(testCase, string(results2.pipeline_status), "paused");
    verifyEqual(testCase, results2.resume_from_frame, 5);
    verifyTrue(testCase, isfile(fullfile(out_dir, 'checkpoint_0004.mat')));
    checkpoint2 = fullfile(out_dir, 'checkpoint_0004.mat');
    checkpoint2_vars = who('-file', checkpoint2);
    verifyTrue(testCase, any(strcmp(checkpoint2_vars, 'locked_threshold')));
    verifyTrue(testCase, isfile(fullfile(out_dir, 'blob_detail_chunks', ...
        'blob_detail_000003_000004.mat')));
    verifyFalse(testCase, isfile(fullfile(out_dir, 'blob_detail_all_frames.csv')));
    verifyFalse(testCase, results2.solubilization.blob_detail_csv_exported);

    config.output.max_frames_per_session = inf;
    sol3 = characterize_solubilization_v2(frame_index, flow_domain, time_vector, config);
    results3 = struct('pipeline_status', sol3.pipeline_status, ...
        'last_completed_frame', sol3.last_completed_frame, ...
        'solubilization', sol3);
    verifyEqual(testCase, string(results3.pipeline_status), "completed");
    verifyEqual(testCase, results3.last_completed_frame, 6);
    verifyTrue(testCase, isfile(fullfile(out_dir, 'blob_detail_chunks', ...
        'blob_detail_000005_000006.mat')));
    final_blob_csv = fullfile(out_dir, 'blob_detail_all_frames.csv');
    verifyTrue(testCase, isfile(final_blob_csv));
    verifyTrue(testCase, results3.solubilization.blob_detail_csv_exported);
    verifyEqual(testCase, results3.solubilization.blob_detail_csv, final_blob_csv);
    blob_detail_table = readtable(final_blob_csv, 'VariableNamingRule', 'preserve');
    verifyEqual(testCase, height(blob_detail_table), ...
        sum(results3.solubilization.num_blobs_vs_time));
    verifyTrue(testCase, all(ismember( ...
        {'GeometryMode', 'GeometrySchemaVersion', 'ObjectConnectivity', ...
         'HoleClassificationComputed', 'HoleCountSource', 'EulerHoleCount', ...
         'RoiFallbackUsed', 'RoiFallbackReason', 'TouchesImageBorder', ...
         'RoiAreaFraction'}, ...
        blob_detail_table.Properties.VariableNames)));
    verifyTrue(testCase, all(string(blob_detail_table.GeometryMode) == "core_only"));
    verifyTrue(testCase, all(string(blob_detail_table.GeometrySchemaVersion) == "geometry_v2_core_only"));

    schema_path = fullfile(out_dir, 'status', 'geometry_schema.mat');
    verifyTrue(testCase, isfile(schema_path));
    schema_data = load(schema_path, 'geometry_schema');
    verifyEqual(testCase, string(schema_data.geometry_schema.GeometryMode), "core_only");
    verifyEqual(testCase, string(schema_data.geometry_schema.GeometrySchemaVersion), "geometry_v2_core_only");

    breadcrumb_path = fullfile(out_dir, 'status', 'last_geometry_state.mat');
    verifyTrue(testCase, isfile(breadcrumb_path));
    breadcrumb_data = load(breadcrumb_path, 'breadcrumb');
    verifyTrue(testCase, ismember(string(breadcrumb_data.breadcrumb.stage), ...
        ["before_blob_metrics", "after_blob_metrics"]));
    verifyEqual(testCase, string(breadcrumb_data.breadcrumb.geometry_mode), "core_only");
end


function test_step4_rejects_incompatible_geometry_schema_manifest(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    out_dir = fullfile(tempdir, ['dnapl_geometry_schema_mismatch_' datestr(now, 'yyyymmdd_HHMMSSFFF')]);
    c1 = onCleanup(@() cleanup_tempdir(out_dir)); %#ok<NASGU>
    mkdir(fullfile(out_dir, 'status'));

    [frame_index, flow_domain, time_vector] = create_synthetic_checkpoint_fixture(out_dir, 3);
    config = make_synthetic_step4_config(out_dir, size(flow_domain));
    config.output.save_blob_detail = true;
    config.output.checkpoint = false;
    config.output.max_frames_per_session = inf;

    geometry_schema = struct( ...
        'GeometryMode', "legacy_fullframe", ...
        'GeometrySchemaVersion', "geometry_v1_legacy_fullframe", ...
        'ObjectConnectivity', 8, ...
        'HoleClassificationComputed', true, ...
        'CreatedAt', datestr(now, 30)); %#ok<NASGU>
    save(fullfile(out_dir, 'status', 'geometry_schema.mat'), 'geometry_schema', '-v7');

    verifyError(testCase, ...
        @() characterize_solubilization_v2(frame_index, flow_domain, time_vector, config), ...
        'geometry:schemaMismatch');
end


function test_step4_roi_mode_exports_geometry_v3_schema(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    out_dir = fullfile(tempdir, ['dnapl_roi_step4_' datestr(now, 'yyyymmdd_HHMMSSFFF')]);
    c1 = onCleanup(@() cleanup_tempdir(out_dir)); %#ok<NASGU>
    mkdir(out_dir);

    [frame_index, flow_domain, time_vector] = create_synthetic_checkpoint_fixture(out_dir, 4);
    config = make_synthetic_step4_config(out_dir, size(flow_domain));
    config.output.save_blob_detail = true;
    config.output.checkpoint = false;
    config.output.max_frames_per_session = inf;
    config.geometry.mode = 'roi';
    config.geometry.schema_version = 'geometry_v3_roi_holes';
    solid_mask = false(size(flow_domain));

    sol = characterize_solubilization_v2(frame_index, flow_domain, time_vector, ...
        config, struct('enabled', false), solid_mask);

    verifyEqual(testCase, string(sol.pipeline_status), "completed");
    final_blob_csv = fullfile(out_dir, 'blob_detail_all_frames.csv');
    verifyTrue(testCase, isfile(final_blob_csv));
    blob_detail_table = readtable(final_blob_csv, 'VariableNamingRule', 'preserve');
    verifyGreaterThan(testCase, height(blob_detail_table), 0);
    verifyTrue(testCase, all(string(blob_detail_table.GeometryMode) == "roi"));
    verifyTrue(testCase, all(string(blob_detail_table.GeometrySchemaVersion) == "geometry_v3_roi_holes"));
    verifyTrue(testCase, all(blob_detail_table.HoleClassificationComputed == 1));
    verifyTrue(testCase, all(string(blob_detail_table.HoleCountSource) == "roi_domain_aware"));
    verifyTrue(testCase, all(ismember( ...
        {'RoiFallbackUsed', 'RoiFallbackReason', 'TouchesImageBorder', 'RoiAreaFraction'}, ...
        blob_detail_table.Properties.VariableNames)));

    schema_data = load(fullfile(out_dir, 'status', 'geometry_schema.mat'), 'geometry_schema');
    verifyEqual(testCase, string(schema_data.geometry_schema.GeometryMode), "roi");
    verifyEqual(testCase, string(schema_data.geometry_schema.GeometrySchemaVersion), "geometry_v3_roi_holes");
    verifyTrue(testCase, schema_data.geometry_schema.HoleClassificationComputed);
    verifyEqual(testCase, schema_data.geometry_schema.RoiPad, 1);
end


function test_blob_detail_csv_export_failure_preserves_completed_run(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    out_dir = fullfile(tempdir, ['dnapl_blob_csv_export_fail_' datestr(now, 'yyyymmdd_HHMMSSFFF')]);
    c1 = onCleanup(@() cleanup_tempdir(out_dir)); %#ok<NASGU>
    mkdir(out_dir);

    [frame_index, flow_domain, time_vector] = create_synthetic_checkpoint_fixture(out_dir, 4);
    config = make_synthetic_step4_config(out_dir, size(flow_domain));
    config.output.checkpoint = false;
    config.output.max_frames_per_session = inf;
    config.output.save_blob_detail = true;
    config.output.blob_detail_chunk_size = 10;

    mkdir(fullfile(out_dir, 'blob_detail_all_frames.tmp.csv'));
    lastwarn('');
    sol = characterize_solubilization_v2(frame_index, flow_domain, time_vector, config);
    [warn_msg, warn_id] = lastwarn;

    verifyEqual(testCase, string(sol.pipeline_status), "completed");
    verifyEqual(testCase, sol.last_completed_frame, 4);
    verifyEqual(testCase, warn_id, 'characterize_solubilization_v2:blobDetailCsvExportFailed');
    verifyTrue(testCase, contains(warn_msg, 'Failed to export blob detail CSV'));
    verifyTrue(testCase, isfolder(fullfile(out_dir, 'blob_detail_chunks')));
    verifyTrue(testCase, isfile(fullfile(out_dir, 'blob_detail_chunks', ...
        'blob_detail_000001_000004.mat')));
    verifyFalse(testCase, isfile(fullfile(out_dir, 'blob_detail_all_frames.csv')));
    verifyFalse(testCase, sol.blob_detail_csv_exported);
    verifyEqual(testCase, sol.blob_detail_csv, '');
    verifyEqual(testCase, sol.blob_detail_csv_path, fullfile(out_dir, 'blob_detail_all_frames.csv'));
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
    expected_chunks_dir = fullfile(config.output_path, 'blob_detail_chunks');
    enabled_log = evalc('characterize_solubilization_v2(frame_index, flow_domain, time_vector, config);');
    verifyTrue(testCase, contains(enabled_log, ['Per-blob detail chunks: ' expected_chunks_dir]));
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
    verifyTrue(testCase, isfield(sol_parallel, 'blob_detail_csv'));
    verifyEqual(testCase, sol_parallel.blob_detail_csv, '');
    verifyFalse(testCase, sol_parallel.blob_detail_csv_exported);
    verifyFalse(testCase, isfile(expected_path));

    source_path = fullfile(root_dir, 'analysis', 'characterize_solubilization_v2.m');
    source_text = fileread(source_path);
    fallback_pos = strfind(source_text, 'characterize_solubilization_v2:parallelMaskFootprint');
    decision_pos = strfind(source_text, 'do_write_blob_detail = do_save_blob_detail && ~use_parallel');
    log_pos = strfind(source_text, 'Per-blob detail CSV:');
    reconcile_pos = strfind(source_text, 'reconcile_blob_detail_chunks(blob_detail_chunks_dir');
    verifyNotEmpty(testCase, fallback_pos);
    verifyNotEmpty(testCase, decision_pos);
    verifyNotEmpty(testCase, log_pos);
    verifyNotEmpty(testCase, reconcile_pos);
    verifyLessThan(testCase, fallback_pos(1), decision_pos(1));
    verifyLessThan(testCase, decision_pos(1), log_pos(1));
    verifyLessThan(testCase, log_pos(1), reconcile_pos(1));
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


function [fixture_dir, tif_path] = create_config_tif_fixture()
    fixture_dir = fullfile(tempdir, ['dnapl_config_fixture_' datestr(now, 'yyyymmdd_HHMMSSFFF')]);
    mkdir(fixture_dir);
    tif_path = fullfile(fixture_dir, 'fixture.tif');
    rgb = uint8(zeros(8, 8, 3));
    rgb(:, :, 1) = 180;
    rgb(:, :, 2) = 120;
    rgb(:, :, 3) = 120;
    imwrite(rgb, tif_path);
end


function assume_default_tif_available(testCase)
    default_data_path = 'G:\Microfluid\18 1-BO 4UL 5% TWEEM 80 4UL WATER DISPLACE\01 Tween 80';
    has_tif = ~isempty(dir(fullfile(default_data_path, '*.tif')));
    assumeTrue(testCase, has_tif, ...
        'Default real-data path is unavailable in this test environment.');
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


function [frame_index, flow_domain, time_vector] = create_synthetic_checkpoint_fixture(fixture_dir, num_frames)
    if nargin < 2
        num_frames = 4;
    end
    flow_domain = true(32, 32);
    time_vector = (0:num_frames-1).';
    frame_masks = cell(num_frames, 1);
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
    for i = 5:num_frames
        frame_masks{i} = false(32, 32);
        side_len = max(3, 12 - i);
        top = min(3 + i, 28 - side_len);
        left = min(4 + mod(i, 5), 28 - side_len);
        frame_masks{i}(top:top+side_len, left:left+side_len) = true;
        if mod(i, 2) == 0
            frame_masks{i}(20:23, 18:21) = true;
        end
    end

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
    config.geometry = struct( ...
        'mode', 'core_only', ...
        'object_connectivity', 8, ...
        'schema_version', 'geometry_v2_core_only', ...
        'include_heavy_shape_props', true);
    config.output_path = output_dir;
end
