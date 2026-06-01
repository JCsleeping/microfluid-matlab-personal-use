function tests = test_geometry_sample_validation_mock
% TEST_GEOMETRY_SAMPLE_VALIDATION_MOCK  Tests for small-frame geometry validation.

    setup_path();
    tests = functiontests(localfunctions);
end


function test_selects_stratified_frames_and_maps_timeline(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    write_dissolution_rates(fixture.postprocess_dir, 12);
    write_timeline(fixture.output_root, fixture.raw_dir, 12);

    validation = run_geometry_sample_validation(fixture.output_root, fixture.postprocess_dir, ...
        fixture.metadata_json, 'OutputDir', fixture.validation_dir, 'MaxFrames', 20, ...
        'RawImageDir', fixture.raw_dir);

    selected = readtable(fullfile(fixture.validation_dir, 'selected_frames.csv'), ...
        'VariableNamingRule', 'preserve');

    verifyLessThanOrEqual(testCase, height(selected), 12);
    verifyGreaterThan(testCase, height(selected), 0);
    verifyTrue(testCase, all(ismember(selected.FrameIndex, (1:12)')));
    verifyTrue(testCase, all(contains(selected.TifPath, fixture.raw_dir)));
    verifyEqual(testCase, validation.status, 'PRECHECK_FAILED');
end


function test_uses_explicit_selected_frames_csv(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    write_dissolution_rates(fixture.postprocess_dir, 12);
    write_timeline(fixture.output_root, fixture.raw_dir, 12);
    selected_csv = fullfile(fixture.postprocess_dir, 'selected_geometry_validation_frames_g21.csv');
    FrameIndex = [7; 2; 11]; %#ok<NASGU>
    SelectionReason = {'rate_peak'; 'initial_stage'; 'late_stage'}; %#ok<NASGU>
    T = table(FrameIndex, SelectionReason);
    writetable(T, selected_csv);

    run_geometry_sample_validation(fixture.output_root, fixture.postprocess_dir, ...
        fixture.metadata_json, 'OutputDir', fixture.validation_dir, 'MaxFrames', 20, ...
        'RawImageDir', fixture.raw_dir, 'SelectedFramesCsv', selected_csv);

    selected = readtable(fullfile(fixture.validation_dir, 'selected_frames.csv'), ...
        'VariableNamingRule', 'preserve');
    verifyEqual(testCase, selected.FrameIndex, [7; 2; 11]);
    verifyEqual(testCase, selected.SelectionReason, SelectionReason);
    verifyEqual(testCase, selected.PageInTif, [7; 2; 11]);
end


function test_stops_safely_when_segmentation_context_missing(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    write_dissolution_rates(fixture.postprocess_dir, 4);
    write_timeline(fixture.output_root, fixture.raw_dir, 4);

    validation = run_geometry_sample_validation(fixture.output_root, fixture.postprocess_dir, ...
        fixture.metadata_json, 'OutputDir', fixture.validation_dir, 'RawImageDir', fixture.raw_dir);

    verifyEqual(testCase, validation.status, 'PRECHECK_FAILED');
    verifyTrue(testCase, isfile(fullfile(fixture.validation_dir, 'geometry_validation_preflight.csv')));
    verifyTrue(testCase, isfile(fullfile(fixture.validation_dir, 'geometry_validation_report.md')));

    blob_table = readtable(fullfile(fixture.validation_dir, 'geometry_sample_blob_table.csv'), ...
        'VariableNamingRule', 'preserve');
    verifyEqual(testCase, height(blob_table), 0);

    comparison = readtable(fullfile(fixture.validation_dir, 'geometry_level_a_comparison.csv'), ...
        'VariableNamingRule', 'preserve');
    verifyTrue(testCase, all(strcmp(comparison.Notes, 'not_applicable_no_generated_geometry')));
end


function test_computes_geometry_from_mock_masks(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    mask_dir = fullfile(fixture.root, 'masks');
    mkdir(mask_dir);
    write_dissolution_rates(fixture.postprocess_dir, 2);
    write_timeline(fixture.output_root, fixture.raw_dir, 2);
    write_existing_blob_csv(fixture.output_root);

    mask1 = false(30, 40);
    mask1(5:12, 6:18) = true;
    mask1(18:24, 25:32) = true;
    mask2 = false(30, 40);
    mask2(8:22, 8:28) = true;
    imwrite(uint8(mask1) * 255, fullfile(mask_dir, 'frame_000001_mask.png'));
    imwrite(uint8(mask2) * 255, fullfile(mask_dir, 'frame_000002_mask.png'));

    validation = run_geometry_sample_validation(fixture.output_root, fixture.postprocess_dir, ...
        fixture.metadata_json, 'OutputDir', fixture.validation_dir, 'RawImageDir', fixture.raw_dir, ...
        'MaskDir', mask_dir, 'MaxFrames', 20);

    verifyEqual(testCase, validation.status, 'PASS_WITH_MASKS');

    blob_table = readtable(fullfile(fixture.validation_dir, 'geometry_sample_blob_table.csv'), ...
        'VariableNamingRule', 'preserve');
    verifyGreaterThanOrEqual(testCase, height(blob_table), 2);
    verifyTrue(testCase, all(blob_table.BoundaryAvailable));
    verifyTrue(testCase, all(isfinite(blob_table.MajorAxisLength)));
    verifyTrue(testCase, all(isfinite(blob_table.MinorAxisLength)));
    verifyTrue(testCase, all(isfinite(blob_table.Orientation)));
    verifyTrue(testCase, all(isfinite(blob_table.ConvexPerimeter)));
    verifyTrue(testCase, all(isfinite(blob_table.ProjectedRoughness)));

    comparison = readtable(fullfile(fixture.validation_dir, 'geometry_level_a_comparison.csv'), ...
        'VariableNamingRule', 'preserve');
    verifyTrue(testCase, ismember('BlobCountPass', comparison.Properties.VariableNames));
    verifyTrue(testCase, ismember('TotalAreaPass', comparison.Properties.VariableNames));
end


function test_computes_geometry_from_raw_when_context_ready(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    write_dissolution_rates(fixture.postprocess_dir, 20);
    write_raw_timeline_for_segmentation(fixture.output_root, fixture.raw_dir, 20);
    write_results_with_segmentation_context(fixture.output_root);
    audit_dir = write_ready_segmentation_context_audit(fixture.postprocess_dir);

    validation = run_geometry_sample_validation(fixture.output_root, fixture.postprocess_dir, ...
        fixture.metadata_json, 'OutputDir', fixture.validation_dir, 'RawImageDir', fixture.raw_dir, ...
        'SegmentationContextAuditDir', audit_dir, 'MaxFrames', 20);

    verifyEqual(testCase, validation.status, 'PASS_WITH_RAW_CONTEXT');
    verifyTrue(testCase, isfolder(fullfile(fixture.validation_dir, 'validation_masks')));

    blob_table = readtable(fullfile(fixture.validation_dir, 'geometry_sample_blob_table.csv'), ...
        'VariableNamingRule', 'preserve');
    verifyGreaterThan(testCase, height(blob_table), 0);
    verifyTrue(testCase, all(blob_table.BoundaryAvailable));
    verifyTrue(testCase, all(isfinite(blob_table.ConvexPerimeter)));

    masks = dir(fullfile(fixture.validation_dir, 'validation_masks', '*.tif'));
    verifyGreaterThan(testCase, numel(masks), 0);
end


function test_partial_mask_coverage_is_not_reported_as_pass(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    mask_dir = fullfile(fixture.root, 'masks');
    mkdir(mask_dir);
    write_dissolution_rates(fixture.postprocess_dir, 2);
    write_timeline(fixture.output_root, fixture.raw_dir, 2);

    mask1 = false(30, 40);
    mask1(5:12, 6:18) = true;
    imwrite(uint8(mask1) * 255, fullfile(mask_dir, 'frame_000001_mask.png'));

    validation = run_geometry_sample_validation(fixture.output_root, fixture.postprocess_dir, ...
        fixture.metadata_json, 'OutputDir', fixture.validation_dir, 'RawImageDir', fixture.raw_dir, ...
        'MaskDir', mask_dir, 'MaxFrames', 20);

    verifyEqual(testCase, validation.status, 'PARTIAL_MASK_COVERAGE');
    verifyEqual(testCase, height(validation.geometry_sample_blob_table), 1);
    preflight = readtable(fullfile(fixture.validation_dir, 'geometry_validation_preflight.csv'), ...
        'VariableNamingRule', 'preserve');
    missing_row = preflight(strcmp(preflight.Check, 'missing_mask_frames'), :);
    verifyEqual(testCase, missing_row.Details{1}, '2');
end


function test_max_frames_must_be_between_20_and_50(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    write_dissolution_rates(fixture.postprocess_dir, 12);
    write_timeline(fixture.output_root, fixture.raw_dir, 12);

    verifyError(testCase, @() run_geometry_sample_validation(fixture.output_root, ...
        fixture.postprocess_dir, fixture.metadata_json, 'OutputDir', fixture.validation_dir, ...
        'RawImageDir', fixture.raw_dir, 'MaxFrames', 19), ...
        'run_geometry_sample_validation:badMaxFrames');
    verifyError(testCase, @() run_geometry_sample_validation(fixture.output_root, ...
        fixture.postprocess_dir, fixture.metadata_json, 'OutputDir', fixture.validation_dir, ...
        'RawImageDir', fixture.raw_dir, 'MaxFrames', 51), ...
        'run_geometry_sample_validation:badMaxFrames');
end


function test_mask_matching_does_not_use_partial_frame_number(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    mask_dir = fullfile(fixture.root, 'masks');
    mkdir(mask_dir);
    write_dissolution_rates(fixture.postprocess_dir, 1);
    write_timeline(fixture.output_root, fixture.raw_dir, 1);
    wrong_mask = false(30, 40);
    wrong_mask(5:12, 6:18) = true;
    imwrite(uint8(wrong_mask) * 255, fullfile(mask_dir, 'frame_000010_mask.png'));

    validation = run_geometry_sample_validation(fixture.output_root, fixture.postprocess_dir, ...
        fixture.metadata_json, 'OutputDir', fixture.validation_dir, 'RawImageDir', fixture.raw_dir, ...
        'MaskDir', mask_dir, 'MaxFrames', 20);

    verifyEqual(testCase, validation.status, 'PRECHECK_FAILED');
    verifyEqual(testCase, height(validation.geometry_sample_blob_table), 0);
end


function test_relative_output_dir_resolves_under_postprocess(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    write_dissolution_rates(fixture.postprocess_dir, 2);
    write_timeline(fixture.output_root, fixture.raw_dir, 2);
    old_dir = pwd;
    restore = onCleanup(@() cd(old_dir)); %#ok<NASGU>
    cd(fixture.root);

    validation = run_geometry_sample_validation(fixture.output_root, fixture.postprocess_dir, ...
        fixture.metadata_json, 'OutputDir', 'geometry_relative', 'RawImageDir', fixture.raw_dir);

    expected = fullfile(fixture.postprocess_dir, 'geometry_relative');
    verifyEqual(testCase, validation.output_dir, expected);
    verifyTrue(testCase, isfolder(expected));
    verifyFalse(testCase, isfolder(fullfile(fixture.root, 'geometry_relative')));
    cd(old_dir);
end


function test_refuses_nonempty_output_without_overwrite(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    write_dissolution_rates(fixture.postprocess_dir, 2);
    write_timeline(fixture.output_root, fixture.raw_dir, 2);
    mkdir(fixture.validation_dir);
    write_text(fullfile(fixture.validation_dir, 'old.txt'), 'old');

    verifyError(testCase, @() run_geometry_sample_validation(fixture.output_root, ...
        fixture.postprocess_dir, fixture.metadata_json, 'OutputDir', fixture.validation_dir), ...
        'run_geometry_sample_validation:nonemptyOutputDir');
end


function setup_path()
    root = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root));
end


function fixture = make_fixture()
    fixture.root = tempname;
    mkdir(fixture.root);
    fixture.output_root = fullfile(fixture.root, 'output');
    fixture.postprocess_dir = fullfile(fixture.output_root, 'postprocess_residual_structure_test');
    fixture.raw_dir = fullfile(fixture.root, 'raw');
    fixture.validation_dir = fullfile(fixture.postprocess_dir, 'geometry_sample_validation_test');
    fixture.metadata_json = fullfile(fixture.root, 'experiment_metadata_recovered.json');
    mkdir(fixture.output_root);
    mkdir(fixture.postprocess_dir);
    mkdir(fixture.raw_dir);
    write_text(fixture.metadata_json, '{"fields":{"pixel_size_m":{"value":4.1e-6}}}');
end


function cleanup_fixture(fixture)
    if isfolder(fixture.root)
        rmdir(fixture.root, 's');
    end
end


function write_dissolution_rates(postprocess_dir, n)
    FrameIndex = (1:n)';
    RealTime_s = (FrameIndex - 1) * 3;
    DissolutionRate_Sn_per_min = linspace(0.01, 0.05, n)';
    stage_values = {'early', 'middle', 'late', 'near-depleted'};
    Stage = stage_values(mod(FrameIndex - 1, numel(stage_values)) + 1)';
    T = table(FrameIndex, RealTime_s, DissolutionRate_Sn_per_min, Stage);
    writetable(T, fullfile(postprocess_dir, 'dissolution_rates.csv'));
end


function write_timeline(output_root, raw_dir, n)
    tif_name = 'sample_stack.tif';
    tif_path = fullfile(raw_dir, tif_name);
    for i = 1:n
        img = uint8(ones(30, 40, 3) * (20 + i));
        if i == 1
            imwrite(img, tif_path);
        else
            imwrite(img, tif_path, 'WriteMode', 'append');
        end
    end

    GlobalFrame = (1:n)';
    RealTime_s = (GlobalFrame - 1) * 3;
    TifFile = repmat({tif_name}, n, 1);
    PageInTif = GlobalFrame;
    Interval_s = repmat(3, n, 1);
    T = table(GlobalFrame, RealTime_s, TifFile, PageInTif, Interval_s);
    writetable(T, fullfile(output_root, 'frame_timeline_mock.csv'));
end


function write_raw_timeline_for_segmentation(output_root, raw_dir, n)
    tif_name = 'sample_raw_stack.tif';
    tif_path = fullfile(raw_dir, tif_name);
    for i = 1:n
        img = uint8(ones(30, 40, 3) * 255);
        img(8:18, 10:23, 1) = 255;
        img(8:18, 10:23, 2) = 0;
        img(8:18, 10:23, 3) = 0;
        if i == 1
            imwrite(img, tif_path);
        else
            imwrite(img, tif_path, 'WriteMode', 'append');
        end
    end

    GlobalFrame = (1:n)';
    RealTime_s = (GlobalFrame - 1) * 3;
    TifFile = repmat({tif_name}, n, 1);
    PageInTif = GlobalFrame;
    Interval_s = repmat(3, n, 1);
    T = table(GlobalFrame, RealTime_s, TifFile, PageInTif, Interval_s);
    writetable(T, fullfile(output_root, 'frame_timeline_mock.csv'));
end


function write_results_with_segmentation_context(output_root)
    config = struct();
    config.preprocess.rotation_angle = 0;
    config.preprocess.manual_crop_rect = 'interactive';
    config.preprocess.saved_crop_rect = [];
    config.illumination.method = 'morphological';
    config.illumination.kernel_size = 1;
    config.segmentation.method = 'gmm';
    config.segmentation.num_components = 2;
    config.segmentation.min_blob_area = 1;
    config.segmentation.morph_radius = 1;
    config.parallel.use_gpu = false;

    results = struct();
    results.flow_domain = true(30, 40);
    results.solid_mask = false(30, 40);
    results.segmentation.info.threshold = 5;
    results.preprocessing.crop_rect = [1 1 39 29];
    save(fullfile(output_root, 'results_mock.mat'), 'config', 'results');
end


function audit_dir = write_ready_segmentation_context_audit(postprocess_dir)
    audit_dir = fullfile(postprocess_dir, 'segmentation_context_audit_ready');
    mkdir(audit_dir);
    SafeForValidationExtraction = true;
    DecisionLabel = {'READY_FOR_VALIDATION_GEOMETRY'};
    RecommendedSource = {'raw_frames_with_recorded_segmentation_context'};
    BlockingMissingItems = {''};
    RecoverableItems = {'results_flow_domain;results_segmentation_threshold;frame_timeline'};
    T = table(SafeForValidationExtraction, DecisionLabel, RecommendedSource, ...
        BlockingMissingItems, RecoverableItems);
    writetable(T, fullfile(audit_dir, 'geometry_validation_readiness.csv'));
end


function write_existing_blob_csv(output_root)
    FrameIndex = [1; 2];
    BlobID = [1; 1];
    Area = [200; 300];
    Perimeter = [60; 80];
    Circularity = [0.7; 0.6];
    AspectRatio = [1.2; 1.4];
    Solidity = [0.9; 0.95];
    T = table(FrameIndex, BlobID, Area, Perimeter, Circularity, AspectRatio, Solidity);
    writetable(T, fullfile(output_root, 'blob_detail_all_frames.csv'));
end


function write_text(path, text)
    fid = fopen(path, 'w');
    cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, '%s', text);
end
