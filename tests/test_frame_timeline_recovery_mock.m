function tests = test_frame_timeline_recovery_mock
% TEST_FRAME_TIMELINE_RECOVERY_MOCK  Mock tests for raw TIF timeline recovery.

    setup_path();
    tests = functiontests(localfunctions);
end


function test_rebuilds_timeline_from_raw_tifs_and_timeseries(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    write_multipage_tif(fullfile(fixture.raw_dir, '04 Tween 80 3 SECONDS.tif'), 2);
    write_multipage_tif(fullfile(fixture.raw_dir, '04 Tween 80 3 SECONDS_1.tif'), 3);
    write_timeseries(fixture.output_root, 5, 1);

    result = recover_frame_timeline_from_raw_tifs(fixture.output_root, ...
        'PostprocessDir', fixture.postprocess_dir, ...
        'RawImageDir', fixture.raw_dir, ...
        'WriteReport', true);

    verifyEqual(testCase, result.Decision, 'READY_FOR_CONTEXT_REAUDIT');
    verifyTrue(testCase, isfile(fullfile(result.OutputDir, 'frame_timeline_recovered.csv')));
    verifyTrue(testCase, isfile(fullfile(result.OutputDir, 'raw_tif_inventory.csv')));
    verifyTrue(testCase, isfile(fullfile(result.OutputDir, 'frame_timeline_recovery_report.md')));
    verifyTrue(testCase, isfile(fullfile(result.OutputDir, 'frame_timeline_recovery_summary.json')));
    verifyTrue(testCase, isfile(fullfile(result.OutputDir, 'recommended_next_action.json')));

    timeline = readtable(fullfile(result.OutputDir, 'frame_timeline_recovered.csv'), ...
        'VariableNamingRule', 'preserve');
    verifyEqual(testCase, height(timeline), 5);
    verifyEqual(testCase, timeline.GlobalFrame(:), (1:5)');
    verifyEqual(testCase, timeline.FrameIndex(:), (1:5)');
    verifyEqual(testCase, timeline.PageInTif(:), [1; 2; 1; 2; 3]);
    verifyEqual(testCase, timeline.RealTime_s(:), (0:4)');
    verifyEqual(testCase, timeline.TifFile{1}, '04 Tween 80 3 SECONDS.tif');
    verifyEqual(testCase, timeline.TifFile{3}, '04 Tween 80 3 SECONDS_1.tif');
    verifyTrue(testCase, all(cellfun(@isfile, timeline.TifPath)));

    inventory = readtable(fullfile(result.OutputDir, 'raw_tif_inventory.csv'), ...
        'VariableNamingRule', 'preserve');
    verifyEqual(testCase, sum(inventory.NumPages), 5);
end


function test_page_count_mismatch_blocks_context_reaudit(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    write_multipage_tif(fullfile(fixture.raw_dir, '04 Tween 80 3 SECONDS.tif'), 2);
    write_multipage_tif(fullfile(fixture.raw_dir, '04 Tween 80 3 SECONDS_1.tif'), 3);
    write_timeseries(fixture.output_root, 6, 1);

    result = recover_frame_timeline_from_raw_tifs(fixture.output_root, ...
        'PostprocessDir', fixture.postprocess_dir, ...
        'RawImageDir', fixture.raw_dir, ...
        'WriteReport', true);

    verifyEqual(testCase, result.Decision, 'BLOCKED_BY_TIF_PAGE_COUNT_MISMATCH');
    verifyFalse(testCase, result.ReadyForContextReaudit);
end


function test_existing_timeline_is_validated_not_rebuilt(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    write_multipage_tif(fullfile(fixture.raw_dir, 'raw_a.tif'), 2);
    write_timeseries(fixture.output_root, 2, 2);
    GlobalFrame = (1:2)';
    FrameIndex = GlobalFrame;
    TifFile = {'raw_a.tif'; 'raw_a.tif'};
    PageInTif = [1; 2];
    RealTime_s = [0; 2];
    Interval_s = [2; 2];
    T = table(GlobalFrame, FrameIndex, TifFile, PageInTif, RealTime_s, Interval_s);
    writetable(T, fullfile(fixture.output_root, 'frame_timeline_existing.csv'));

    result = recover_frame_timeline_from_raw_tifs(fixture.output_root, ...
        'PostprocessDir', fixture.postprocess_dir, ...
        'RawImageDir', fixture.raw_dir);

    verifyEqual(testCase, result.Decision, 'READY_FOR_CONTEXT_REAUDIT');
    verifyEqual(testCase, result.MappingSource, 'existing_timeline');
end


function setup_path()
    root = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root));
end


function fixture = make_fixture()
    fixture.root = tempname;
    mkdir(fixture.root);
    fixture.output_root = fullfile(fixture.root, 'output');
    fixture.postprocess_dir = fullfile(fixture.output_root, 'postprocess');
    fixture.raw_dir = fullfile(fixture.root, 'raw');
    mkdir(fixture.output_root);
    mkdir(fixture.postprocess_dir);
    mkdir(fixture.raw_dir);
end


function cleanup_fixture(fixture)
    if isfolder(fixture.root)
        rmdir(fixture.root, 's');
    end
end


function write_multipage_tif(path, n_pages)
    for idx = 1:n_pages
        img = uint8(ones(8, 9) * idx);
        if idx == 1
            imwrite(img, path);
        else
            imwrite(img, path, 'WriteMode', 'append');
        end
    end
end


function write_timeseries(output_root, n_rows, dt)
    Time = ((0:n_rows-1)' * dt); %#ok<NASGU>
    Sn = linspace(1, 0, n_rows)'; %#ok<NASGU>
    T = table(Time, Sn);
    writetable(T, fullfile(output_root, 'timeseries_mock.csv'));
end
