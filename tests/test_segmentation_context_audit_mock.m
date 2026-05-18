function tests = test_segmentation_context_audit_mock
% TEST_SEGMENTATION_CONTEXT_AUDIT_MOCK  Mock tests for segmentation context audit.

    setup_path();
    tests = functiontests(localfunctions);
end


function test_missing_threshold_crop_and_mapping_requires_manual_config(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    write_raw_tifs(fixture.raw_dir, 2);
    config = struct();
    config.segmentation = struct('method', 'fixed');
    flow_domain = true(8, 9); %#ok<NASGU>
    solid_mask = false(8, 9); %#ok<NASGU>
    save(fullfile(fixture.output_root, 'results_missing_context.mat'), ...
        'config', 'flow_domain', 'solid_mask');

    audit = run_segmentation_context_audit(fixture.output_root, ...
        'PostprocessDir', fixture.postprocess_dir, ...
        'MetadataRecoveryDir', fixture.metadata_dir, ...
        'RawImageDir', fixture.raw_dir, ...
        'WriteReport', true);

    verifyFalse(testCase, audit.SafeForValidationExtraction);
    verifyEqual(testCase, audit.Decision, 'NEED_MANUAL_CONFIG');

    availability = readtable(fullfile(audit.AuditDir, 'segmentation_context_availability.csv'), ...
        'VariableNamingRule', 'preserve');
    verifyCheckStatus(testCase, availability, 'segmentation_threshold_context', false);
    verifyCheckStatus(testCase, availability, 'crop_resize_preprocessing_context', false);

    frame_mapping = readtable(fullfile(audit.AuditDir, 'frame_mapping_readiness.csv'), ...
        'VariableNamingRule', 'preserve');
    verifyFalse(testCase, logical(frame_mapping.MappingReady(1)));
end


function test_missing_mapping_and_no_existing_masks_not_recoverable(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    config = struct();
    config.segmentation = struct('method', 'gmm', 'gmm_threshold', 0.42);
    config.preprocessing = struct('crop_rect', [1 1 8 9], 'resize_factor', 1);
    flow_domain = true(8, 9); %#ok<NASGU>
    solid_mask = false(8, 9); %#ok<NASGU>
    save(fullfile(fixture.output_root, 'results_ready_context.mat'), ...
        'config', 'flow_domain', 'solid_mask');

    audit = run_segmentation_context_audit(fixture.output_root, ...
        'PostprocessDir', fixture.postprocess_dir, ...
        'MetadataRecoveryDir', fixture.metadata_dir, ...
        'RawImageDir', fixture.raw_dir, ...
        'WriteReport', true);

    verifyFalse(testCase, audit.SafeForValidationExtraction);
    verifyEqual(testCase, audit.Decision, 'NOT_RECOVERABLE_WITHOUT_RERUN');
end


function test_existing_masks_and_labels_are_preferred(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    mask_dir = fullfile(fixture.postprocess_dir, 'segmentation_masks');
    label_dir = fullfile(fixture.postprocess_dir, 'segmentation_labels');
    mkdir(mask_dir);
    mkdir(label_dir);
    imwrite(uint8([0 255; 255 0]), fullfile(mask_dir, 'frame_000001_mask.tif'));
    labels = uint16([0 1; 2 0]); %#ok<NASGU>
    save(fullfile(label_dir, 'frame_000001_labels.mat'), 'labels');

    config = struct();
    config.segmentation = struct('method', 'fixed');
    save(fullfile(fixture.output_root, 'results_incomplete_context.mat'), 'config');

    audit = run_segmentation_context_audit(fixture.output_root, ...
        'PostprocessDir', fixture.postprocess_dir, ...
        'MetadataRecoveryDir', fixture.metadata_dir, ...
        'RawImageDir', fixture.raw_dir, ...
        'WriteReport', true);

    verifyTrue(testCase, audit.SafeForValidationExtraction);
    verifyEqual(testCase, audit.Decision, 'READY_FOR_VALIDATION_GEOMETRY');
    verifyEqual(testCase, audit.ExtractionSource, 'existing_masks_labels');

    readiness = readtable(fullfile(audit.AuditDir, 'geometry_validation_readiness.csv'), ...
        'VariableNamingRule', 'preserve');
    verifyEqual(testCase, readiness.RecommendedSource{1}, 'existing_masks_labels');
end


function test_corrupted_results_mat_is_recorded_without_crash(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    write_text(fullfile(fixture.output_root, 'results_corrupted.mat'), 'not a mat file');

    audit = run_segmentation_context_audit(fixture.output_root, ...
        'PostprocessDir', fixture.postprocess_dir, ...
        'MetadataRecoveryDir', fixture.metadata_dir, ...
        'RawImageDir', fixture.raw_dir, ...
        'WriteReport', true);

    verifyEqual(testCase, audit.Decision, 'NOT_RECOVERABLE_WITHOUT_RERUN');

    inventory = readtable(fullfile(audit.AuditDir, 'mat_variable_inventory.csv'), ...
        'VariableNamingRule', 'preserve');
    verifyEqual(testCase, height(inventory), 1);
    verifyFalse(testCase, logical(inventory.Readable(1)));
    verifyTrue(testCase, contains(inventory.OpenFailureClass{1}, 'MAT_OPEN_FAILURE'));
end


function test_required_outputs_written_and_no_writes_outside_audit_dir(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    write_raw_tifs(fixture.raw_dir, 2);
    write_frame_timeline(fixture.output_root, 2);
    config = struct();
    config.segmentation = struct('method', 'fixed', 'threshold', 0.51);
    config.preprocessing = struct('crop_rect', [1 1 8 9], 'resize_factor', 1);
    flow_domain = true(8, 9); %#ok<NASGU>
    solid_mask = false(8, 9); %#ok<NASGU>
    save(fullfile(fixture.output_root, 'results_full_context.mat'), ...
        'config', 'flow_domain', 'solid_mask');

    before = snapshot_files(fixture.root);

    audit = run_segmentation_context_audit(fixture.output_root, ...
        'PostprocessDir', fixture.postprocess_dir, ...
        'MetadataRecoveryDir', fixture.metadata_dir, ...
        'RawImageDir', fixture.raw_dir, ...
        'WriteReport', true);

    required = {'segmentation_context_audit_report.md', ...
        'segmentation_context_audit.json', ...
        'mat_variable_inventory.csv', ...
        'segmentation_context_availability.csv', ...
        'frame_mapping_readiness.csv', ...
        'geometry_validation_readiness.csv', ...
        'recommended_next_action.json'};
    for idx = 1:numel(required)
        verifyTrue(testCase, isfile(fullfile(audit.AuditDir, required{idx})), required{idx});
    end

    verifyTrue(testCase, audit.SafeForValidationExtraction);
    verifyEqual(testCase, audit.Decision, 'READY_FOR_VALIDATION_GEOMETRY');

    after = snapshot_files(fixture.root);
    new_paths = setdiff(after.Path, before.Path);
    outside = new_paths(~startsWith(new_paths, [audit.AuditDir filesep]) & ~strcmp(new_paths, audit.AuditDir));
    verifyEmpty(testCase, outside);

    common = intersect(before.Path, after.Path);
    for idx = 1:numel(common)
        b = before(strcmp(before.Path, common{idx}), :);
        a = after(strcmp(after.Path, common{idx}), :);
        verifyEqual(testCase, a.Bytes, b.Bytes, common{idx});
        verifyEqual(testCase, a.Modified, b.Modified, common{idx});
    end
end


function test_explicit_timeline_csv_enables_mapping(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    write_raw_tifs(fixture.raw_dir, 2);
    timeline_dir = fullfile(fixture.postprocess_dir, 'frame_timeline_recovery_mock');
    mkdir(timeline_dir);
    write_frame_timeline(timeline_dir, 2);
    timeline_csv = fullfile(timeline_dir, 'frame_timeline_mock.csv');

    config = struct();
    config.segmentation = struct('method', 'fixed', 'threshold', 0.51);
    config.preprocessing = struct('crop_rect', [1 1 8 9], 'resize_factor', 1);
    flow_domain = true(8, 9); %#ok<NASGU>
    solid_mask = false(8, 9); %#ok<NASGU>
    save(fullfile(fixture.output_root, 'results_full_context.mat'), ...
        'config', 'flow_domain', 'solid_mask');

    audit = run_segmentation_context_audit(fixture.output_root, ...
        'PostprocessDir', fixture.postprocess_dir, ...
        'MetadataRecoveryDir', fixture.metadata_dir, ...
        'RawImageDir', fixture.raw_dir, ...
        'FrameTimelineCsv', timeline_csv, ...
        'WriteReport', true);

    verifyTrue(testCase, audit.SafeForValidationExtraction);
    verifyEqual(testCase, audit.Decision, 'READY_FOR_VALIDATION_GEOMETRY');

    frame_mapping = readtable(fullfile(audit.AuditDir, 'frame_mapping_readiness.csv'), ...
        'VariableNamingRule', 'preserve');
    verifyTrue(testCase, logical(frame_mapping.MappingReady(1)));
    verifyEqual(testCase, frame_mapping.TimelinePath{1}, timeline_csv);
    verifyFalse(testCase, isfile(fullfile(fixture.output_root, 'frame_timeline_mock.csv')));
end


function test_nested_results_segmentation_context_is_detected(testCase)
    fixture = make_fixture();
    cleanup = onCleanup(@() cleanup_fixture(fixture)); %#ok<NASGU>

    write_raw_tifs(fixture.raw_dir, 2);
    write_frame_timeline(fixture.output_root, 2);
    config = struct();
    config.segmentation = struct('method', 'gmm');
    config.preprocessing = struct('crop_rect', [1 1 8 9], 'resize_factor', 1);
    results = struct();
    results.flow_domain = true(8, 9);
    results.solid_mask = false(8, 9);
    results.preprocessing = struct('crop_rect', [1 1 8 9]);
    results.segmentation = struct();
    results.segmentation.info = struct('threshold', 0.42, 'method', 'gmm');
    save(fullfile(fixture.output_root, 'results_nested_context.mat'), ...
        'config', 'results');

    audit = run_segmentation_context_audit(fixture.output_root, ...
        'PostprocessDir', fixture.postprocess_dir, ...
        'MetadataRecoveryDir', fixture.metadata_dir, ...
        'RawImageDir', fixture.raw_dir, ...
        'WriteReport', true);

    verifyTrue(testCase, audit.SafeForValidationExtraction);
    verifyEqual(testCase, audit.Decision, 'READY_FOR_VALIDATION_GEOMETRY');

    availability = readtable(fullfile(audit.AuditDir, 'segmentation_context_availability.csv'), ...
        'VariableNamingRule', 'preserve');
    verifyCheckStatus(testCase, availability, 'flow_domain', true);
    verifyCheckStatus(testCase, availability, 'solid_mask', true);
    verifyCheckStatus(testCase, availability, 'segmentation_threshold_context', true);
end


function verifyCheckStatus(testCase, availability, check_name, expected_available)
    row = availability(strcmp(availability.Check, check_name), :);
    verifyEqual(testCase, height(row), 1);
    verifyEqual(testCase, logical(row.Available(1)), expected_available);
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
    fixture.metadata_dir = fullfile(fixture.output_root, 'metadata_recovery');
    fixture.raw_dir = fullfile(fixture.root, 'raw');
    mkdir(fixture.output_root);
    mkdir(fixture.postprocess_dir);
    mkdir(fixture.metadata_dir);
    mkdir(fixture.raw_dir);
end


function cleanup_fixture(fixture)
    if isfolder(fixture.root)
        rmdir(fixture.root, 's');
    end
end


function write_raw_tifs(raw_dir, n)
    for idx = 1:n
        img = uint8(ones(8, 9) * idx);
        imwrite(img, fullfile(raw_dir, sprintf('frame_%06d.tif', idx)));
    end
end


function write_frame_timeline(output_root, n)
    GlobalFrame = (1:n)';
    TifFile = cell(n, 1);
    PageInTif = ones(n, 1);
    RealTime_s = (GlobalFrame - 1) * 3;
    for idx = 1:n
        TifFile{idx} = sprintf('frame_%06d.tif', idx);
    end
    T = table(GlobalFrame, TifFile, PageInTif, RealTime_s);
    writetable(T, fullfile(output_root, 'frame_timeline_mock.csv'));
end


function write_text(path, text)
    fid = fopen(path, 'w');
    assert(fid > 0, 'Failed to open %s for writing.', path);
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, '%s', text);
end


function files = snapshot_files(root_dir)
    listing = recursive_files(root_dir);
    n = numel(listing);
    Path = cell(n, 1);
    Bytes = zeros(n, 1);
    Modified = zeros(n, 1);
    for idx = 1:n
        Path{idx} = listing(idx).path;
        info = dir(listing(idx).path);
        Bytes(idx) = info.bytes;
        Modified(idx) = info.datenum;
    end
    files = table(Path, Bytes, Modified);
end


function listing = recursive_files(root_dir)
    listing = struct('path', {});
    entries = dir(root_dir);
    for idx = 1:numel(entries)
        name = entries(idx).name;
        if strcmp(name, '.') || strcmp(name, '..')
            continue;
        end
        path = fullfile(root_dir, name);
        if entries(idx).isdir
            child = recursive_files(path);
            listing = [listing; child]; %#ok<AGROW>
        else
            listing(end + 1, 1).path = path; %#ok<AGROW>
        end
    end
end
