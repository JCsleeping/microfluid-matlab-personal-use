function tests = test_geometry_perimeter_estimators_mock
% TEST_GEOMETRY_PERIMETER_ESTIMATORS_MOCK  Tests corrected boundary metrics.

    setup_path();
    tests = functiontests(localfunctions);
end


function test_boundary_perimeter_qc_for_convex_mask(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    mask = false(80, 90);
    mask(20:49, 25:54) = true;
    write_validation_fixture(fixture.validation_dir, mask);

    result = compare_perimeter_estimators(fixture.validation_dir, ...
        'OutputDir', fixture.v2_dir, 'WriteFigures', false);

    qc = readtable(fullfile(fixture.v2_dir, 'perimeter_estimator_qc.csv'), ...
        'VariableNamingRule', 'preserve');
    verifyEqual(testCase, result.DecisionLabel, 'READY_FOR_FULL_SIDECAR');
    verifyGreaterThanOrEqual(testCase, qc.P_boundary(1) + 1e-9, qc.Pc_boundary(1));
    verifyGreaterThanOrEqual(testCase, qc.ProjectedRoughness_boundary(1) + 1e-9, 1);
    verifyEqual(testCase, qc.AreaTier{1}, 'high_confidence');
    verifyTrue(testCase, logical(qc.BoundaryMetricValid(1)));
end


function test_area_tiers_and_metric_validity_are_deterministic(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    mask = false(90, 120);
    mask(3:5, 3:6) = true;          % 12 px tiny
    mask(10:15, 10:17) = true;      % 48 px small
    mask(25:36, 20:31) = true;      % 144 px medium
    mask(45:62, 45:62) = true;      % 324 px large
    mask(20:49, 80:109) = true;     % 900 px high confidence
    write_validation_fixture(fixture.validation_dir, mask);

    compare_perimeter_estimators(fixture.validation_dir, ...
        'OutputDir', fixture.v2_dir, 'WriteFigures', false);

    qc = readtable(fullfile(fixture.v2_dir, 'perimeter_estimator_qc.csv'), ...
        'VariableNamingRule', 'preserve');
    verifyEqual(testCase, qc.AreaTier(:), ...
        {'tiny'; 'small'; 'medium'; 'large'; 'high_confidence'});
    verifyFalse(testCase, logical(qc.BoundaryMetricValid(1)));
    verifyFalse(testCase, logical(qc.BoundaryMetricValid(2)));
    verifyFalse(testCase, logical(qc.BoundaryMetricValid(3)));
    verifyTrue(testCase, logical(qc.BoundaryMetricValid(4)));
    verifyTrue(testCase, logical(qc.BoundaryMetricValid(5)));
end


function test_frame_one_is_initial_note_not_deleted(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    mask = false(50, 60);
    mask(10:30, 10:35) = true;
    write_validation_fixture(fixture.validation_dir, mask);

    compare_perimeter_estimators(fixture.validation_dir, ...
        'OutputDir', fixture.v2_dir, 'WriteFigures', false);

    manual_qc = readtable(fullfile(fixture.v2_dir, 'manual_overlay_qc.csv'), ...
        'VariableNamingRule', 'preserve');
    verifyEqual(testCase, manual_qc.FrameIndex(1), 1);
    verifyEqual(testCase, manual_qc.Decision{1}, 'ACCEPT_WITH_INITIAL_FRAME_NOTE');
    verifyTrue(testCase, ismember('ReviewedByHuman', manual_qc.Properties.VariableNames));
    verifyTrue(testCase, ismember('ReviewSource', manual_qc.Properties.VariableNames));
    verifyFalse(testCase, logical(manual_qc.ReviewedByHuman(1)));
    verifyEqual(testCase, manual_qc.ReviewSource{1}, 'AUTO_DEFAULT');
    by_blob = readtable(fullfile(fixture.v2_dir, 'geometry_validation_by_blob.csv'), ...
        'VariableNamingRule', 'preserve');
    verifyEqual(testCase, height(by_blob), 1);
end


function test_missing_level_a_comparison_blocks_v2_gate(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    mask = false(80, 90);
    mask(20:49, 25:54) = true;
    write_validation_fixture(fixture.validation_dir, mask);
    delete(fullfile(fixture.validation_dir, 'geometry_level_a_comparison.csv'));

    result = compare_perimeter_estimators(fixture.validation_dir, ...
        'OutputDir', fixture.v2_dir, 'WriteFigures', false);

    verifyEqual(testCase, result.DecisionLabel, 'BLOCKED_BY_MISSING_COMPARISON');
    verifyFalse(testCase, result.HasLevelAComparison);
    verifyFalse(testCase, result.BlobCountGatePassed);
    verifyFalse(testCase, result.AreaGatePassed);
end


function test_sidecar_runner_refuses_failed_v2_gate(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    mkdir(fixture.failed_v2_dir);
    summary = struct();
    summary.DecisionLabel = 'BLOCKED_BY_PERIMETER_QC';
    write_json(fullfile(fixture.failed_v2_dir, 'geometry_validation_summary.json'), summary);

    verifyError(testCase, @() run_geometry_sidecar_extraction(fixture.output_root, ...
        fixture.postprocess_dir, 'ValidationV2Dir', fixture.failed_v2_dir, ...
        'SegmentationContextAuditDir', fixture.audit_dir, 'MetadataJson', fixture.metadata_json, ...
        'RawImageDir', fixture.raw_dir, 'DryRun', true), ...
        'run_geometry_sidecar_extraction:v2GateNotReady');
end


function test_sidecar_full_run_writes_geometry_for_mock_raw(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    write_mock_raw_sidecar_context(fixture, 4);
    mkdir(fixture.v2_dir);
    summary = struct();
    summary.DecisionLabel = 'READY_FOR_FULL_SIDECAR';
    write_json(fullfile(fixture.v2_dir, 'geometry_validation_summary.json'), summary);

    result = run_geometry_sidecar_extraction(fixture.output_root, fixture.postprocess_dir, ...
        'ValidationV2Dir', fixture.v2_dir, 'SegmentationContextAuditDir', fixture.audit_dir, ...
        'MetadataJson', fixture.metadata_json, 'RawImageDir', fixture.raw_dir, ...
        'OutputDir', fixture.sidecar_dir, 'ConfirmFullRun', true, 'MaxFrames', 4, ...
        'WriteMasks', true);

    verifyEqual(testCase, result.Status, 'PASS');
    by_blob = readtable(fullfile(fixture.sidecar_dir, 'geometry_by_blob.csv'), ...
        'VariableNamingRule', 'preserve');
    verifyGreaterThan(testCase, height(by_blob), 0);
    verifyTrue(testCase, ismember('P_outer_boundary', by_blob.Properties.VariableNames));
    verifyTrue(testCase, ismember('P_total_boundary', by_blob.Properties.VariableNames));
    verifyTrue(testCase, ismember('ProjectedRoughness_boundary', by_blob.Properties.VariableNames));
    masks = dir(fullfile(fixture.sidecar_dir, 'masks_or_labels', '*_mask.tif'));
    verifyEqual(testCase, numel(masks), 4);
    labels = dir(fullfile(fixture.sidecar_dir, 'masks_or_labels', '*_labels.tif'));
    verifyEqual(testCase, numel(labels), 4);
    manifest = readtable(fullfile(fixture.sidecar_dir, 'geometry_sidecar_manifest.csv'), ...
        'VariableNamingRule', 'preserve');
    verifyEqual(testCase, height(manifest), 1);
    verifyEqual(testCase, manifest.RowCount(1), height(by_blob));
end


function test_total_boundary_includes_internal_holes(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    mask = false(80, 80);
    mask(10:60, 10:60) = true;
    mask(28:40, 28:40) = false;
    write_validation_fixture(fixture.validation_dir, mask);

    compare_perimeter_estimators(fixture.validation_dir, ...
        'OutputDir', fixture.v2_dir, 'WriteFigures', false);
    qc = readtable(fullfile(fixture.v2_dir, 'perimeter_estimator_qc.csv'), ...
        'VariableNamingRule', 'preserve');

    verifyTrue(testCase, ismember('P_outer_boundary', qc.Properties.VariableNames));
    verifyTrue(testCase, ismember('P_total_boundary', qc.Properties.VariableNames));
    verifyGreaterThan(testCase, qc.P_total_boundary(1), qc.P_outer_boundary(1));
    verifyEqual(testCase, qc.ProjectedRoughness_boundary(1), ...
        qc.P_outer_boundary(1) / qc.Pc_outer_boundary(1), 'AbsTol', 1e-12);
end


function test_sidecar_dry_run_writes_only_new_output_dir(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    mkdir(fixture.v2_dir);
    summary = struct();
    summary.DecisionLabel = 'READY_FOR_FULL_SIDECAR';
    write_json(fullfile(fixture.v2_dir, 'geometry_validation_summary.json'), summary);

    before_listing = dir(fixture.output_root);
    result = run_geometry_sidecar_extraction(fixture.output_root, fixture.postprocess_dir, ...
        'ValidationV2Dir', fixture.v2_dir, 'SegmentationContextAuditDir', fixture.audit_dir, ...
        'MetadataJson', fixture.metadata_json, 'RawImageDir', fixture.raw_dir, ...
        'OutputDir', fixture.sidecar_dir, 'DryRun', true);
    after_listing = dir(fixture.output_root);

    verifyEqual(testCase, result.Status, 'DRY_RUN_READY');
    verifyTrue(testCase, isfolder(fixture.sidecar_dir));
    verifyTrue(testCase, isfile(fullfile(fixture.sidecar_dir, 'geometry_provenance.json')));
    verifyEqual(testCase, sort({before_listing.name}), sort({after_listing.name}));
end


function test_initial_frame_area_mismatch_is_pass_with_note(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    write_mock_raw_sidecar_context(fixture, 4);
    write_mock_blob_csv_with_areas(fixture.output_root, [200; 150; 150; 150]);
    write_ready_v2_gate(fixture.v2_dir);

    result = run_geometry_sidecar_extraction(fixture.output_root, fixture.postprocess_dir, ...
        'ValidationV2Dir', fixture.v2_dir, 'SegmentationContextAuditDir', fixture.audit_dir, ...
        'MetadataJson', fixture.metadata_json, 'RawImageDir', fixture.raw_dir, ...
        'OutputDir', fixture.sidecar_dir, 'ConfirmFullRun', true, 'MaxFrames', 4, ...
        'WriteMasks', false, 'AllowInitialFrameAreaMismatch', true, 'InitialFrameIndex', 1);

    verifyEqual(testCase, result.Status, 'PASS_WITH_INITIAL_FRAME_NOTE');
    verifyFalse(testCase, result.Blocked);
    qc = readtable(fullfile(fixture.sidecar_dir, 'geometry_qc_summary.csv'), ...
        'VariableNamingRule', 'preserve');
    verify_metric_value(testCase, qc, 'ExemptedInitialFrameMismatchCount', '1');
    verify_metric_value(testCase, qc, 'NonExemptMismatchFrames', '0');
    verify_metric_value(testCase, qc, 'EffectiveTotalAreaPassFrames', '4');
end


function test_non_initial_mismatch_remains_warn(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    write_mock_raw_sidecar_context(fixture, 4);
    write_mock_blob_csv_with_areas(fixture.output_root, [150; 200; 150; 150]);
    write_ready_v2_gate(fixture.v2_dir);

    result = run_geometry_sidecar_extraction(fixture.output_root, fixture.postprocess_dir, ...
        'ValidationV2Dir', fixture.v2_dir, 'SegmentationContextAuditDir', fixture.audit_dir, ...
        'MetadataJson', fixture.metadata_json, 'RawImageDir', fixture.raw_dir, ...
        'OutputDir', fixture.sidecar_dir, 'ConfirmFullRun', true, 'MaxFrames', 4, ...
        'WriteMasks', false);

    verifyEqual(testCase, result.Status, 'WARN_QC_REVIEW');
    verifyTrue(testCase, result.Blocked);
    qc = readtable(fullfile(fixture.sidecar_dir, 'geometry_qc_summary.csv'), ...
        'VariableNamingRule', 'preserve');
    verify_metric_value(testCase, qc, 'NonExemptMismatchFrames', '1');
end


function test_frame_indices_and_qc_stride_control_processed_frames(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    write_mock_raw_sidecar_context(fixture, 6);
    write_ready_v2_gate(fixture.v2_dir);

    result = run_geometry_sidecar_extraction(fixture.output_root, fixture.postprocess_dir, ...
        'ValidationV2Dir', fixture.v2_dir, 'SegmentationContextAuditDir', fixture.audit_dir, ...
        'MetadataJson', fixture.metadata_json, 'RawImageDir', fixture.raw_dir, ...
        'OutputDir', fixture.sidecar_dir, 'ConfirmFullRun', true, ...
        'FrameIndices', [2 5], 'MaxFrames', 6, 'WriteMasks', false, ...
        'WriteQCImages', true, 'QCImageStride', 2);

    verifyEqual(testCase, result.ProcessedFrameCount, 2);
    comparison = readtable(fullfile(fixture.sidecar_dir, 'geometry_level_a_comparison_all_frames.csv'), ...
        'VariableNamingRule', 'preserve');
    verifyEqual(testCase, comparison.FrameIndex, [2; 5]);
    vis = dir(fullfile(fixture.sidecar_dir, 'mask_visualization', '*.png'));
    verifyEqual(testCase, numel(vis), 1);
end


function test_sidecar_accepts_explicit_frame_timeline_csv(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    write_mock_raw_sidecar_context(fixture, 3);
    write_ready_v2_gate(fixture.v2_dir);
    recovery_dir = fullfile(fixture.postprocess_dir, 'frame_timeline_recovery_mock');
    mkdir(recovery_dir);
    explicit_timeline = fullfile(recovery_dir, 'frame_timeline_recovered.csv');
    movefile(fullfile(fixture.output_root, 'frame_timeline_mock.csv'), explicit_timeline);

    result = run_geometry_sidecar_extraction(fixture.output_root, fixture.postprocess_dir, ...
        'ValidationV2Dir', fixture.v2_dir, 'SegmentationContextAuditDir', fixture.audit_dir, ...
        'MetadataJson', fixture.metadata_json, 'RawImageDir', fixture.raw_dir, ...
        'FrameTimelineCsv', explicit_timeline, 'OutputDir', fixture.sidecar_dir, ...
        'ConfirmFullRun', true, 'MaxFrames', 3, 'WriteMasks', false, ...
        'WriteQCImages', false);

    verifyEqual(testCase, result.ProcessedFrameCount, 3);
    verifyFalse(testCase, isfile(fullfile(fixture.output_root, 'frame_timeline_mock.csv')));
    provenance_text = fileread(fullfile(fixture.sidecar_dir, 'geometry_provenance.json'));
    verifyTrue(testCase, contains(provenance_text, 'frame_timeline_recovered.csv'));
end


function test_all_empty_part_preserves_blob_schema(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    write_mock_raw_sidecar_context(fixture, 3, 'blank');
    write_mock_blob_csv_with_areas(fixture.output_root, zeros(3, 1));
    write_ready_v2_gate(fixture.v2_dir);

    run_geometry_sidecar_extraction(fixture.output_root, fixture.postprocess_dir, ...
        'ValidationV2Dir', fixture.v2_dir, 'SegmentationContextAuditDir', fixture.audit_dir, ...
        'MetadataJson', fixture.metadata_json, 'RawImageDir', fixture.raw_dir, ...
        'OutputDir', fixture.sidecar_dir, 'ConfirmFullRun', true, 'MaxFrames', 3, ...
        'PartFrameSize', 2, 'WriteMasks', false, 'WriteQCImages', false);

    parts = dir(fullfile(fixture.sidecar_dir, 'parts', 'geometry_by_blob_part_*.csv'));
    verifyGreaterThanOrEqual(testCase, numel(parts), 1);
    part_table = readtable(fullfile(parts(1).folder, parts(1).name), ...
        'VariableNamingRule', 'preserve');
    verifyTrue(testCase, ismember('FrameIndex', part_table.Properties.VariableNames));
    verifyTrue(testCase, ismember('P_outer_boundary', part_table.Properties.VariableNames));
end


function test_tif_mismatch_cluster_summary_flags_repeated_mismatch(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    write_mock_raw_sidecar_context(fixture, 5);
    write_mock_blob_csv_with_areas(fixture.output_root, [200; 200; 200; 200; 150]);
    write_ready_v2_gate(fixture.v2_dir);

    result = run_geometry_sidecar_extraction(fixture.output_root, fixture.postprocess_dir, ...
        'ValidationV2Dir', fixture.v2_dir, 'SegmentationContextAuditDir', fixture.audit_dir, ...
        'MetadataJson', fixture.metadata_json, 'RawImageDir', fixture.raw_dir, ...
        'OutputDir', fixture.sidecar_dir, 'ConfirmFullRun', true, 'MaxFrames', 5, ...
        'WriteMasks', false, 'AllowInitialFrameAreaMismatch', false);

    verifyEqual(testCase, result.Status, 'BLOCKED_BY_FRAME_MAPPING_OR_SEGMENTATION_QC');
    cluster = readtable(fullfile(fixture.sidecar_dir, 'geometry_mismatch_cluster_summary.csv'), ...
        'VariableNamingRule', 'preserve');
    verifyTrue(testCase, any(logical(cluster.ReviewRequired)));
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
    fixture.validation_dir = fullfile(fixture.postprocess_dir, 'geometry_sample_validation_test');
    fixture.v2_dir = fullfile(fixture.postprocess_dir, 'geometry_sample_validation_v2_test');
    fixture.failed_v2_dir = fullfile(fixture.postprocess_dir, 'geometry_sample_validation_v2_failed');
    fixture.sidecar_dir = fullfile(fixture.postprocess_dir, 'geometry_sidecar_test');
    fixture.audit_dir = fullfile(fixture.postprocess_dir, 'segmentation_context_audit_ready');
    fixture.raw_dir = fullfile(fixture.root, 'raw');
    fixture.metadata_json = fullfile(fixture.root, 'metadata.json');
    mkdir(fixture.output_root);
    mkdir(fixture.postprocess_dir);
    mkdir(fixture.validation_dir);
    mkdir(fixture.audit_dir);
    mkdir(fixture.raw_dir);
    write_text(fixture.metadata_json, '{"pixel_size_um":4.1}');
end


function cleanup_fixture(fixture)
    if isfolder(fixture.root)
        rmdir(fixture.root, 's');
    end
end


function write_validation_fixture(validation_dir, mask)
    mask_dir = fullfile(validation_dir, 'validation_masks');
    qc_dir = fullfile(validation_dir, 'qc_images');
    mkdir(mask_dir);
    mkdir(qc_dir);
    mask_path = fullfile(mask_dir, 'frame_000001_validation_mask.tif');
    imwrite(uint8(mask) * 255, mask_path);
    imwrite(repmat(uint8(mask) * 255, [1 1 3]), fullfile(qc_dir, 'frame_000001_overlay.png'));

    cc = bwconncomp(mask, 8);
    props = regionprops(cc, 'Area', 'Perimeter', 'MajorAxisLength', ...
        'MinorAxisLength', 'Orientation', 'ConvexArea', 'Solidity');
    n = numel(props);
    FrameIndex = ones(n, 1);
    BlobID = (1:n)';
    Area = [props.Area]';
    Perimeter = [props.Perimeter]';
    MajorAxisLength = [props.MajorAxisLength]';
    MinorAxisLength = [props.MinorAxisLength]';
    Orientation = [props.Orientation]';
    ConvexArea = [props.ConvexArea]';
    ConvexPerimeter = NaN(n, 1);
    BoundaryAvailable = true(n, 1);
    ProjectedRoughness = NaN(n, 1);
    Circularity2D = 4 * pi * Area ./ max(Perimeter .^ 2, eps);
    AspectRatio = MajorAxisLength ./ max(MinorAxisLength, eps);
    Solidity = [props.Solidity]';
    MaskPath = repmat({mask_path}, n, 1);
    T = table(FrameIndex, BlobID, Area, Perimeter, MajorAxisLength, ...
        MinorAxisLength, Orientation, ConvexArea, ConvexPerimeter, ...
        BoundaryAvailable, ProjectedRoughness, Circularity2D, AspectRatio, ...
        Solidity, MaskPath);
    writetable(T, fullfile(validation_dir, 'geometry_sample_blob_table.csv'));

    selected = table(1, {mask_path}, 'VariableNames', {'FrameIndex', 'MaskPath'});
    writetable(selected, fullfile(validation_dir, 'selected_frames.csv'));

    ExistingBlobCount = n;
    GeneratedBlobCount = n;
    BlobCountRelativeDiff = 0;
    BlobCountPass = true;
    ExistingTotalArea = sum(Area);
    GeneratedTotalArea = sum(Area);
    TotalAreaRelativeDiff = 0;
    TotalAreaPass = true;
    Notes = {'within acceptance thresholds'};
    comparison = table(FrameIndex(1), ExistingBlobCount, GeneratedBlobCount, ...
        BlobCountRelativeDiff, BlobCountPass, ExistingTotalArea, GeneratedTotalArea, ...
        TotalAreaRelativeDiff, TotalAreaPass, Notes, 'VariableNames', ...
        {'FrameIndex', 'ExistingBlobCount', 'GeneratedBlobCount', ...
        'BlobCountRelativeDiff', 'BlobCountPass', 'ExistingTotalArea', ...
        'GeneratedTotalArea', 'TotalAreaRelativeDiff', 'TotalAreaPass', 'Notes'});
    writetable(comparison, fullfile(validation_dir, 'geometry_level_a_comparison.csv'));
end


function write_mock_raw_sidecar_context(fixture, n, mode)
    if nargin < 3
        mode = 'blob';
    end
    write_mock_frame_timeline(fixture.output_root, fixture.raw_dir, n, mode);
    write_mock_dissolution_rates(fixture.postprocess_dir, n);
    write_mock_results_mat(fixture.output_root);
    write_mock_blob_csv(fixture.output_root, n);
end


function write_mock_frame_timeline(output_root, raw_dir, n, mode)
    tif_name = 'mock_raw_stack.tif';
    tif_path = fullfile(raw_dir, tif_name);
    for i = 1:n
        img = uint8(ones(30, 40, 3) * 255);
        if ~strcmp(mode, 'blank')
            img(8:18, 10:23, 1) = 255;
            img(8:18, 10:23, 2) = 0;
            img(8:18, 10:23, 3) = 0;
        end
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


function write_mock_dissolution_rates(postprocess_dir, n)
    FrameIndex = (1:n)';
    RealTime_s = (FrameIndex - 1) * 3;
    Stage = repmat({'mock'}, n, 1);
    DissolutionRate_Sn_per_min = zeros(n, 1);
    T = table(FrameIndex, RealTime_s, Stage, DissolutionRate_Sn_per_min);
    writetable(T, fullfile(postprocess_dir, 'dissolution_rates.csv'));
end


function write_mock_results_mat(output_root)
    config = struct();
    config.preprocess.rotation_angle = 0;
    config.preprocess.manual_crop_rect = [1 1 39 29];
    config.preprocess.saved_crop_rect = [1 1 39 29];
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
    results.preprocessing.rotation_angle = 0;
    save(fullfile(output_root, 'results_mock.mat'), 'config', 'results');
end


function write_mock_blob_csv(output_root, n)
    write_mock_blob_csv_with_areas(output_root, repmat(150, n, 1));
end


function write_mock_blob_csv_with_areas(output_root, areas)
    frames = (1:numel(areas))';
    keep = areas(:) > 0;
    FrameIndex = frames(keep);
    BlobID = ones(sum(keep), 1);
    Area = areas(keep);
    Perimeter = repmat(50, sum(keep), 1);
    T = table(FrameIndex, BlobID, Area, Perimeter);
    writetable(T, fullfile(output_root, 'blob_detail_all_frames.csv'));
end


function write_ready_v2_gate(v2_dir)
    mkdir(v2_dir);
    summary = struct();
    summary.DecisionLabel = 'READY_FOR_FULL_SIDECAR';
    write_json(fullfile(v2_dir, 'geometry_validation_summary.json'), summary);
end


function verify_metric_value(testCase, qc, metric_name, expected)
    idx = strcmp(qc.Metric, metric_name);
    verifyTrue(testCase, any(idx), ['Missing metric: ' metric_name]);
    raw = qc.Value(find(idx, 1));
    if iscell(raw)
        actual = raw{1};
    elseif isstring(raw)
        actual = char(raw(1));
    elseif isnumeric(raw) || islogical(raw)
        actual = num2str(raw(1));
    else
        actual = char(string(raw(1)));
    end
    verifyEqual(testCase, actual, expected);
end


function write_json(path, value)
    fid = fopen(path, 'w');
    cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, '%s', jsonencode(value));
end


function write_text(path, text)
    fid = fopen(path, 'w');
    cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, '%s', text);
end
