function tests = test_residual_structure_pipeline
% TEST_RESIDUAL_STRUCTURE_PIPELINE  Focused tests for residual structure metrics.

    setup_path();
    tests = functiontests(localfunctions);
end


function test_classify_residual_architecture_pool_like(testCase)
    setup_path();
    arch = classify_residual_architecture( ...
        make_blob_struct(0.72, 4, 18.5), ...
        make_iface_struct(2.1e4, 1.3e-3), ...
        make_sat_struct(0.34), ...
        make_architecture_config());

    verifyEqual(testCase, arch.type, 'pool-like');
    verifyEqual(testCase, arch.scores.pool_like, 3);
    verifyEqual(testCase, arch.scores.ganglia_rich, 0);
    verifyEqual(testCase, arch.indicators.Sn0, 0.34);
    verifyEqual(testCase, arch.indicators.N_b, 4);
    verifyEqual(testCase, arch.scatter_data.x, 0.72);
    verifyEqual(testCase, arch.scatter_data.y, 2.1e4);
end


function test_classify_residual_architecture_ganglia_rich(testCase)
    setup_path();
    arch = classify_residual_architecture( ...
        make_blob_struct(0.18, 41, 6.0), ...
        make_iface_struct(8.4e4, 2.8e-3), ...
        make_sat_struct(0.11), ...
        make_architecture_config());

    verifyEqual(testCase, arch.type, 'ganglia-rich');
    verifyEqual(testCase, arch.scores.pool_like, 0);
    verifyEqual(testCase, arch.scores.ganglia_rich, 3);
    verifyEqual(testCase, arch.indicators.a_i_2D, 8.4e4);
    verifyEqual(testCase, arch.indicators.max_blob_fraction, 0.18);
    verifyEqual(testCase, arch.indicators.Req_median, 6.0);
end


function test_classify_residual_architecture_safe_defaults(testCase)
    setup_path();
    arch = classify_residual_architecture( ...
        make_blob_struct(0.65, 6, 12.0), ...
        make_iface_struct(2.5e4, 1.1e-3), ...
        make_sat_struct(0.27));

    verifyEqual(testCase, arch.type, 'pool-like');
    verifyEqual(testCase, arch.thresholds.pool_like.max_blob_fraction_min, 0.50);
    verifyEqual(testCase, arch.thresholds.ganglia_rich.a_i_2D_min, 6.0e4);
end


function test_classify_residual_architecture_nonfinite_ai2d_pool_like(testCase)
    setup_path();
    arch = classify_residual_architecture( ...
        make_blob_struct(0.68, 5, 14.0), ...
        make_iface_struct(NaN, 9.5e-4), ...
        make_sat_struct(0.22), ...
        make_architecture_config());

    verifyEqual(testCase, arch.type, 'pool-like');
    verifyEqual(testCase, arch.scores.pool_like, 2);
    verifyEqual(testCase, arch.scores.ganglia_rich, 0);
    verifyTrue(testCase, isnan(arch.indicators.a_i_2D));
end


function test_compute_timeseries_blob_metrics_extended_summary(testCase)
    setup_path();
    mask = false(40, 40);
    mask(3:8, 4:9) = true;
    mask(22:34, 26:27) = true;

    [metrics, blob_table] = compute_timeseries_blob_metrics(mask);
    blob = analyze_blob_geometry(mask, []);

    verifyEqual(testCase, metrics.num_blobs, blob.num_blobs);
    verifyEqual(testCase, metrics.mean_blob_size, blob.size_distribution.mean, 'AbsTol', 1e-12);
    verifyEqual(testCase, metrics.max_blob_frac, blob.max_blob_fraction, 'AbsTol', 1e-12);
    verifyEqual(testCase, metrics.Req_median, blob.Req_distribution.median, 'AbsTol', 1e-12);
    verifyEqual(testCase, metrics.Req_mean, blob.Req_distribution.mean, 'AbsTol', 1e-12);
    verifyEqual(testCase, metrics.Req_std, blob.Req_distribution.std, 'AbsTol', 1e-12);
    verifyEqual(testCase, metrics.mean_circularity, mean(blob.blob_table.Circularity), 'AbsTol', 1e-12);
    verifyEqual(testCase, metrics.n_droplets, blob.topology_summary.n_droplets);
    verifyEqual(testCase, metrics.n_columns, blob.topology_summary.n_columns);
    verifyEqual(testCase, metrics.n_clusters, blob.topology_summary.n_clusters);
    verifyEqual(testCase, metrics.frac_droplets, blob.topology_summary.frac_droplets, 'AbsTol', 1e-12);
    verifyEqual(testCase, metrics.frac_columns, blob.topology_summary.frac_columns, 'AbsTol', 1e-12);
    verifyEqual(testCase, metrics.frac_clusters, blob.topology_summary.frac_clusters, 'AbsTol', 1e-12);
    verifyEqual(testCase, blob_table, blob.blob_table);
    verifyEqual(testCase, height(blob_table), 2);
end


function test_append_blob_detail_csv_appends_without_duplicate_headers(testCase)
    setup_path();
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>
    csv_path = fullfile(fixture_dir, 'blob_detail_all_frames.csv');

    blob_table_1 = table([1; 2], [10; 20], [0.8; 0.6], ...
        'VariableNames', {'BlobID', 'Area', 'Circularity'});
    blob_table_2 = table(3, 12, 0.7, ...
        'VariableNames', {'BlobID', 'Area', 'Circularity'});

    append_blob_detail_csv(csv_path, 5, 1.25, blob_table_1);
    append_blob_detail_csv(csv_path, 6, 2.50, blob_table_2);

    verifyTrue(testCase, exist(csv_path, 'file') == 2);
    csv_text = fileread(csv_path);
    verifyEqual(testCase, numel(strfind(csv_text, 'FrameIndex')), 1); %#ok<STRIFCND>

    T = readtable(csv_path, 'VariableNamingRule', 'preserve');
    verifyEqual(testCase, height(T), 3);
    verifyEqual(testCase, T.FrameIndex, [5; 5; 6]);
    verifyEqual(testCase, T.FrameTime, [1.25; 1.25; 2.50], 'AbsTol', 1e-12);
end


function test_export_progress_snapshot_writes_extended_columns(testCase)
    setup_path();
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    export_progress_snapshot(fixture_dir, [0; 1; 2], [0.9; 0.8; 0.7], [4; 5; 6], ...
        [11; 12; 13], [0.5; 0.4; 0.3], [2.0; 2.1; 2.2], [2.3; 2.4; 2.5], ...
        [0.1; 0.2; 0.3], [0.7; 0.6; 0.5], [100; 101; 102], [1; 2; 3], ...
        [4; 5; 6], [7; 8; 9], [0.2; 0.3; 0.4], [0.5; 0.4; 0.3], ...
        [0.3; 0.3; 0.3], [8; 9; 10], 3, 0.42);

    csv_path = fullfile(fixture_dir, 'progress', 'progress_latest.csv');
    mat_path = fullfile(fixture_dir, 'progress', 'progress_latest.mat');
    verifyTrue(testCase, exist(csv_path, 'file') == 2);
    verifyTrue(testCase, exist(mat_path, 'file') == 2);

    T = readtable(csv_path, 'VariableNamingRule', 'preserve');
    expected_columns = {'Time', 'Sn', 'NumBlobs', 'MeanBlobSize', 'MaxBlobFrac', ...
        'ReqMedian', 'ReqMean', 'ReqStd', 'MeanCircularity', 'a_i_2D', ...
        'nDroplets', 'nColumns', 'nClusters', 'fracDroplets', ...
        'fracColumns', 'fracClusters', 'InterfaceArea'};
    verifyEqual(testCase, T.Properties.VariableNames, expected_columns);

    progress_data = load(mat_path, 'progress');
    verifyTrue(testCase, isfield(progress_data.progress, 'MaxBlobFrac'));
    verifyTrue(testCase, isfield(progress_data.progress, 'a_i_2D'));
end


function blob = make_blob_struct(max_blob_fraction, num_blobs, req_median)
    blob = struct( ...
        'max_blob_fraction', max_blob_fraction, ...
        'num_blobs', num_blobs, ...
        'Req_distribution', struct('median', req_median), ...
        'topology_summary', struct( ...
            'n_droplets', 1, ...
            'n_columns', 1, ...
            'n_clusters', 0, ...
            'frac_droplets', 0.4, ...
            'frac_columns', 0.6, ...
            'frac_clusters', 0.0));
end


function iface = make_iface_struct(a_i_2D, dnapl_water_length_m)
    iface = struct( ...
        'a_i_2D', a_i_2D, ...
        'dnapl_water_length_m', dnapl_water_length_m);
end


function sat = make_sat_struct(sn)
    sat = struct('Sn', sn);
end


function config = make_architecture_config()
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


function setup_path()
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));
end


function fixture_dir = make_temp_dir()
    fixture_dir = tempname(tempdir);
    mkdir(fixture_dir);
end


function cleanup_temp_dir(fixture_dir)
    if exist(fixture_dir, 'dir')
        rmdir(fixture_dir, 's');
    end
end
