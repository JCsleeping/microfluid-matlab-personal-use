function tests = test_reconstruct_timeline
% Regression tests for reconstruct_timeline real-time rebuilding.
    tests = functiontests(localfunctions);
end


function test_timestamp_sort_preserves_nominal_time(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    base_dir = fullfile(tempdir, ['reconstruct_timeline_' datestr(now, 'yyyymmdd_HHMMSSFFF')]);
    output_dir = fullfile(base_dir, 'output_20260416_000000');
    cleanup = onCleanup(@() cleanup_tempdir(base_dir)); %#ok<NASGU>
    mkdir(base_dir);
    mkdir(output_dir);

    create_test_tif(fullfile(base_dir, '10 tween 80 3s.tif'), 2, 11);
    create_test_tif(fullfile(base_dir, '10 tween 80 3s_1.tif'), 2, 21);
    create_test_tif(fullfile(base_dir, '12 tween 80 10S.tif'), 2, 31);

    t0 = datetime(2026, 4, 14, 9, 0, 0);
    set_file_time(fullfile(base_dir, '10 tween 80 3s.tif'), t0 + seconds(6));
    set_file_time(fullfile(base_dir, '10 tween 80 3s_1.tif'), t0 + seconds(12));
    set_file_time(fullfile(base_dir, '12 tween 80 10S.tif'), t0 + seconds(32));

    nominal_time = (0:5).';
    nominal_sn = linspace(0.9, 0.4, 6).';
    writetable(table(nominal_time, nominal_sn, 'VariableNames', {'Time', 'Sn'}), ...
        fullfile(output_dir, 'timeseries_20260416_000000.csv'));

    config = struct('pages', []);
    save(fullfile(output_dir, 'results_20260416_000000.mat'), 'config');

    T = reconstruct_timeline(fullfile(output_dir, 'results_20260416_000000.mat'), output_dir);

    verifyEqual(testCase, T.TifFile(1:2), repmat({'10 tween 80 3s.tif'}, 2, 1));
    verifyEqual(testCase, T.TifFile(3:4), repmat({'10 tween 80 3s_1.tif'}, 2, 1));
    verifyEqual(testCase, T.TifFile(5:6), repmat({'12 tween 80 10S.tif'}, 2, 1));
    verifyEqual(testCase, unique(T.Interval_s), [3; 10]);
    verifyEqual(testCase, T.RealTime_s, [0; 3; 6; 9; 12; 22], 'AbsTol', 1e-9);

    realtime_csv = latest_output_file(output_dir, 'timeseries_realtime_*.csv');
    ts = readtable(realtime_csv);

    verifyTrue(testCase, ismember('Time', ts.Properties.VariableNames));
    verifyTrue(testCase, ismember('RealTime_s', ts.Properties.VariableNames));
    verifyEqual(testCase, ts.Time, nominal_time);
    verifyEqual(testCase, ts.RealTime_s, [0; 3; 6; 9; 12; 22], 'AbsTol', 1e-9);
end


function test_infers_missing_interval_from_timestamp_delta(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    base_dir = fullfile(tempdir, ['reconstruct_timeline_infer_' datestr(now, 'yyyymmdd_HHMMSSFFF')]);
    output_dir = fullfile(base_dir, 'output_20260416_000001');
    cleanup = onCleanup(@() cleanup_tempdir(base_dir)); %#ok<NASGU>
    mkdir(base_dir);
    mkdir(output_dir);

    create_test_tif(fullfile(base_dir, 'known 4s.tif'), 2, 11);
    create_test_tif(fullfile(base_dir, 'mystery capture.tif'), 2, 21);
    create_test_tif(fullfile(base_dir, 'known 8s.tif'), 2, 31);

    t0 = datetime(2026, 4, 14, 10, 0, 0);
    set_file_time(fullfile(base_dir, 'known 4s.tif'), t0 + seconds(8));
    set_file_time(fullfile(base_dir, 'mystery capture.tif'), t0 + seconds(16));
    set_file_time(fullfile(base_dir, 'known 8s.tif'), t0 + seconds(32));

    writetable(table((0:5).', (1:6).', 'VariableNames', {'Time', 'Sn'}), ...
        fullfile(output_dir, 'timeseries_20260416_000001.csv'));

    config = struct('pages', []);
    save(fullfile(output_dir, 'results_20260416_000001.mat'), 'config');

    T = reconstruct_timeline(fullfile(output_dir, 'results_20260416_000001.mat'), output_dir);

    verifyEqual(testCase, T.Interval_s(1:4), [4; 4; 4; 4], 'AbsTol', 1e-9);
    verifyEqual(testCase, T.Interval_s(5:6), [8; 8], 'AbsTol', 1e-9);
    verifyEqual(testCase, T.RealTime_s, [0; 4; 8; 12; 16; 24], 'AbsTol', 1e-9);
end


function test_name_fallback_for_tied_timestamps(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    base_dir = fullfile(tempdir, ['reconstruct_timeline_tie_' datestr(now, 'yyyymmdd_HHMMSSFFF')]);
    output_dir = fullfile(base_dir, 'output_20260416_000002');
    cleanup = onCleanup(@() cleanup_tempdir(base_dir)); %#ok<NASGU>
    mkdir(base_dir);
    mkdir(output_dir);

    create_test_tif(fullfile(base_dir, 'phase 3s_2.tif'), 1, 11);
    create_test_tif(fullfile(base_dir, 'phase 3s.tif'), 1, 21);
    create_test_tif(fullfile(base_dir, 'phase 3s_1.tif'), 1, 31);

    tied_time = datetime(2026, 4, 14, 11, 0, 0);
    set_file_time(fullfile(base_dir, 'phase 3s_2.tif'), tied_time);
    set_file_time(fullfile(base_dir, 'phase 3s.tif'), tied_time);
    set_file_time(fullfile(base_dir, 'phase 3s_1.tif'), tied_time);

    writetable(table((0:2).', [1; 2; 3], 'VariableNames', {'Time', 'Sn'}), ...
        fullfile(output_dir, 'timeseries_20260416_000002.csv'));

    config = struct('pages', []);
    save(fullfile(output_dir, 'results_20260416_000002.mat'), 'config');

    T = reconstruct_timeline(fullfile(output_dir, 'results_20260416_000002.mat'), output_dir);

    verifyEqual(testCase, T.TifFile, {'phase 3s.tif'; 'phase 3s_1.tif'; 'phase 3s_2.tif'});
    verifyEqual(testCase, T.RealTime_s, [0; 3; 6], 'AbsTol', 1e-9);
end


function create_test_tif(path, n_pages, seed_value)
    img = uint8(seed_value * ones(4, 4));
    imwrite(img, path, 'Compression', 'none');
    for k = 2:n_pages
        imwrite(img + uint8(k - 1), path, 'WriteMode', 'append', 'Compression', 'none');
    end
end


function set_file_time(path, dt_value)
    file_obj = java.io.File(path);
    millis = int64(posixtime(datetime(dt_value)) * 1000);
    ok = file_obj.setLastModified(millis);
    assert(ok, 'Failed to set file timestamp for %s', path);
end


function path_out = latest_output_file(output_dir, pattern)
    files = dir(fullfile(output_dir, pattern));
    assert(~isempty(files), 'Missing output file matching %s', pattern);
    [~, idx] = sort({files.name});
    path_out = fullfile(output_dir, files(idx(end)).name);
end


function cleanup_tempdir(out_dir)
    if isfolder(out_dir)
        try
            rmdir(out_dir, 's');
        catch
            % Best effort cleanup for temp test output.
        end
    end
end
