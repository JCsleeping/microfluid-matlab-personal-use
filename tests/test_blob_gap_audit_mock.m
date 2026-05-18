function tests = test_blob_gap_audit_mock
% TEST_BLOB_GAP_AUDIT_MOCK  Mock tests for read-only blob audit tool.

    setup_path();
    tests = functiontests(localfunctions);
end


function test_csv_only_level_a_fields(testCase)
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    write_blob_csv(fixture_dir, true, true, false);

    audit = run_blob_gap_audit(fixture_dir, 'WriteReport', true);

    verifyEqual(testCase, audit.primary_source.type, 'csv');
    verifyTrue(testCase, isfile(fullfile(audit.env.audit_dir, 'audit_summary.json')));
    verifyMetricStatus(testCase, audit, 'circularity_2d', {'READY_EXISTING', 'READY_DERIVED'});
    verifyMetricStatus(testCase, audit, 'projected_roughness', {'NEED_BOUNDARY_OR_MASK'});
    verifyTrue(testCase, isfile(fullfile(audit.env.audit_dir, 'recommended_next_actions.md')));
end


function test_valid_new_chunk_schema(testCase)
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    write_chunk(fixture_dir, 1:3, [1 0 2], {'ok', 'ok', 'ok'});

    audit = run_blob_gap_audit(fixture_dir, 'WriteReport', false);

    verifyEqual(testCase, audit.primary_source.type, 'chunks');
    verifyFalse(testCase, any(strcmp(audit.status_flags, 'FAIL_CHUNK_INTEGRITY')));
    verifyEqual(testCase, height(audit.outputs.chunk_integrity), 1);
    verifyTrue(testCase, audit.outputs.chunk_integrity.load_ok(1));
    verifyTrue(testCase, audit.outputs.chunk_integrity.row_count_ok(1));
end


function test_failed_frame_manifest_allows_carried_forward_nblobs(testCase)
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    write_chunk(fixture_dir, 1:3, [1 0 1], {'ok', 'failed', 'ok'});
    nblobs_arr = [1; 99; 1]; %#ok<NASGU>
    last_completed_frame = 3; %#ok<NASGU>
    save(fullfile(fixture_dir, 'checkpoint_0003.mat'), 'nblobs_arr', 'last_completed_frame');

    audit = run_blob_gap_audit(fixture_dir, 'WriteReport', false);

    frame2 = audit.outputs.frame_coverage(audit.outputs.frame_coverage.FrameIndex == 2, :);
    verifyEqual(testCase, frame2.FrameStatus{1}, 'failed');
    verifyEqual(testCase, frame2.RowCountMatchesNBlobs{1}, 'not_applicable_failed_frame');
    verifyFalse(testCase, any(strcmp(audit.status_flags, 'FAIL_FRAME_COVERAGE')));
end


function test_missing_perimeter_blocks_circularity(testCase)
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    write_blob_csv(fixture_dir, false, true, false);
    csv_path = fullfile(fixture_dir, 'blob_detail_all_frames.csv');
    T = readtable(csv_path, 'VariableNamingRule', 'preserve');
    T.Circularity = [];
    writetable(T, csv_path);

    audit = run_blob_gap_audit(fixture_dir, 'WriteReport', false);

    verifyMetricStatus(testCase, audit, 'circularity_2d', {'UNKNOWN', 'NEED_BOUNDARY_OR_MASK'});
end


function test_missing_frame_time_marks_shrink_rate_metadata_needed(testCase)
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    write_blob_csv(fixture_dir, true, false, false);

    audit = run_blob_gap_audit(fixture_dir, 'WriteReport', false);

    verifyMetricStatus(testCase, audit, 'total_area', {'READY_DERIVED'});
    verifyMetricStatus(testCase, audit, 'total_area_shrink_rate', {'NEED_EXPERIMENT_METADATA'});
end


function test_existing_boundary_and_convex_hull_ready(testCase)
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    write_blob_csv(fixture_dir, true, true, true);

    audit = run_blob_gap_audit(fixture_dir, 'WriteReport', false);

    verifyMetricStatus(testCase, audit, 'boundary_fractal_dimension', {'READY_FROM_EXISTING_GEOMETRY_SOURCE'});
    verifyMetricStatus(testCase, audit, 'convex_perimeter', {'READY_FROM_EXISTING_GEOMETRY_SOURCE'});
end


function test_existing_mask_requires_geometry_extraction(testCase)
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    write_blob_csv(fixture_dir, true, true, false);
    imwrite(uint8([0 255; 255 0]), fullfile(fixture_dir, 'frame_0001_mask.png'));

    audit = run_blob_gap_audit(fixture_dir, 'WriteReport', false);

    verifyMetricStatus(testCase, audit, 'boundary_fractal_dimension', {'NEED_GEOMETRY_EXTRACTION_FROM_EXISTING_MASK', 'NEED_IMAGE_PROCESSING_TOOLBOX'});
end


function test_corrupted_chunk_with_csv_does_not_fallback(testCase)
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    chunks_dir = fullfile(fixture_dir, 'blob_detail_chunks');
    mkdir(chunks_dir);
    write_text(fullfile(chunks_dir, 'blob_detail_000001_000001.mat'), 'not a mat file');
    write_blob_csv(fixture_dir, true, true, false);

    audit = run_blob_gap_audit(fixture_dir, 'WriteReport', false);

    verifyEqual(testCase, audit.primary_source.type, 'chunks');
    verifyEqual(testCase, audit.overall_status, 'FAIL_CHUNK_INTEGRITY');
end


function test_no_source_found_warns_and_strict_errors_after_outputs(testCase)
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    audit = run_blob_gap_audit(fixture_dir, 'WriteReport', false);
    verifyEqual(testCase, audit.overall_status, 'WARN_NO_BLOB_SOURCE');
    verifyTrue(testCase, isfile(fullfile(audit.env.audit_dir, 'audit_summary.json')));

    verifyError(testCase, @() run_blob_gap_audit(fixture_dir, 'WriteReport', false, 'StrictMode', true), ...
        'run_blob_gap_audit:strictModeFailure');
    audit_dirs = dir(fullfile(fixture_dir, 'audit_blob_morphology_gap_*'));
    verifyGreaterThanOrEqual(testCase, numel(audit_dirs), 2);
end


function test_legacy_chunk_arrays_are_candidate_not_failure(testCase)
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    chunks_dir = fullfile(fixture_dir, 'blob_detail_chunks');
    mkdir(chunks_dir);
    T = make_blob_table([1; 1], [1; 2]);
    chunk = struct();
    chunk.processed_frame_indices = [1 2];
    chunk.frame_times = [0 1];
    chunk.nblobs_by_frame = [1 1];
    chunk.frame_status = {'ok', 'ok'};
    chunk.error_message = {'', ''};
    chunk.blob_detail_table = T;
    save(fullfile(chunks_dir, 'blob_detail_000001_000002.mat'), 'chunk');

    audit = run_blob_gap_audit(fixture_dir, 'WriteReport', false);

    verifyEqual(testCase, audit.outputs.chunk_integrity.schema_class{1}, 'legacy_candidate');
    verifyTrue(testCase, audit.outputs.chunk_integrity.needs_manifest_migration(1));
    verifyFalse(testCase, any(strcmp(audit.status_flags, 'FAIL_CHUNK_INTEGRITY')));
end


function test_old_audit_directories_are_excluded(testCase)
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    old_dir = fullfile(fixture_dir, 'audit_blob_morphology_gap_20000101_000000');
    mkdir(old_dir);
    write_blob_csv(old_dir, true, true, false);

    audit = run_blob_gap_audit(fixture_dir, 'WriteReport', false);

    verifyEqual(testCase, audit.overall_status, 'WARN_NO_BLOB_SOURCE');
    verifyFalse(testCase, any(strcmp(audit.outputs.file_inventory.path, fullfile(old_dir, 'blob_detail_all_frames.csv'))));
end


function test_non_ascii_path_succeeds(testCase)
    fixture_dir = fullfile(tempdir, ['blob_audit_中文_' datestr(now, 'yyyymmdd_HHMMSSFFF')]);
    mkdir(fixture_dir);
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    write_blob_csv(fixture_dir, true, true, false);

    audit = run_blob_gap_audit(fixture_dir, 'WriteReport', true);

    verifyTrue(testCase, isfolder(audit.env.audit_dir));
    verifyTrue(testCase, isfile(fullfile(audit.env.audit_dir, 'file_inventory.csv')));
end


function test_read_only_integrity_unchanged(testCase)
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    csv_path = write_blob_csv(fixture_dir, true, true, false);
    before = dir(csv_path);

    audit = run_blob_gap_audit(fixture_dir, 'WriteReport', false);
    after = dir(csv_path);

    verifyEqual(testCase, before.bytes, after.bytes);
    verifyEqual(testCase, before.datenum, after.datenum);
    verifyFalse(testCase, any(audit.outputs.read_only_integrity.modified));
end


function test_large_csv_uses_sampled_or_header_mode(testCase)
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    write_blob_csv(fixture_dir, true, true, false);

    audit = run_blob_gap_audit(fixture_dir, 'WriteReport', false, 'MaxCsvBytesForFullRead', 1, ...
        'MaxCsvRowsForProfiling', 2);

    verifyTrue(testCase, any(strcmp(audit.outputs.csv_integrity.csv_read_mode{1}, ...
        {'sampled_large_csv', 'header_only'})));
    verifyTrue(testCase, audit.outputs.csv_integrity.full_frame_coverage_unknown(1));
end


function test_rows_only_chunk_marks_partial_manifest(testCase)
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    chunks_dir = fullfile(fixture_dir, 'blob_detail_chunks');
    mkdir(chunks_dir);
    chunk = struct();
    chunk.blob_detail_table = make_blob_table([1; 2], [1; 2]);
    save(fullfile(chunks_dir, 'blob_detail_rows_only.mat'), 'chunk');

    audit = run_blob_gap_audit(fixture_dir, 'WriteReport', false);

    verifyEqual(testCase, audit.outputs.chunk_integrity.manifest_quality{1}, 'partial_from_rows_only');
    verifyTrue(testCase, audit.outputs.chunk_integrity.zero_blob_frames_not_recoverable(1));
end


function test_manifest_duplicate_frames_flagged(testCase)
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    write_chunk(fixture_dir, [1 1], [1 1], {'ok', 'ok'});

    audit = run_blob_gap_audit(fixture_dir, 'WriteReport', false);

    verifyTrue(testCase, audit.outputs.chunk_integrity.has_duplicate_manifest_frames(1));
    verifyEqual(testCase, audit.overall_status, 'FAIL_CHUNK_INTEGRITY');
end


function test_chunk_overlap_flagged(testCase)
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    write_chunk(fixture_dir, 1:2, [1 1], {'ok', 'ok'}, 'blob_detail_000001_000002.mat');
    write_chunk(fixture_dir, 2:3, [1 1], {'ok', 'ok'}, 'blob_detail_000002_000003.mat');

    audit = run_blob_gap_audit(fixture_dir, 'WriteReport', false);

    verifyTrue(testCase, any(audit.outputs.chunk_integrity.has_overlap));
    verifyEqual(testCase, audit.overall_status, 'FAIL_CHUNK_INTEGRITY');
end


function test_metadata_alias_recovery(testCase)
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    write_blob_csv(fixture_dir, true, true, false);
    write_text(fullfile(fixture_dir, 'experiment_metadata.yaml'), sprintf('pixel_size_um: 3.2\nflow_rate: 1.5\nsurfactant_concentration: 5%%\n'));

    audit = run_blob_gap_audit(fixture_dir, 'ExperimentMetadataFile', fullfile(fixture_dir, 'experiment_metadata.yaml'), ...
        'WriteReport', false);

    metadata = audit.outputs.experiment_metadata;
    verifyTrue(testCase, any(strcmp(metadata.metadata_key, 'pixel_size_um') & metadata.found));
    verifyTrue(testCase, any(strcmp(metadata.metadata_key, 'flow_rate') & metadata.found));
end


function test_write_report_false_skips_markdown_only(testCase)
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    write_blob_csv(fixture_dir, true, true, false);

    audit = run_blob_gap_audit(fixture_dir, 'WriteReport', false);

    verifyTrue(testCase, isfile(fullfile(audit.env.audit_dir, 'audit_summary.json')));
    verifyTrue(testCase, isfile(fullfile(audit.env.audit_dir, 'metric_feasibility_matrix.csv')));
    verifyFalse(testCase, isfile(fullfile(audit.env.audit_dir, 'audit_report.md')));
    verifyFalse(testCase, isfile(fullfile(audit.env.audit_dir, 'recommended_next_actions.md')));
end


function test_existing_track_id_marks_tracking_ready(testCase)
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    csv_path = write_blob_csv(fixture_dir, true, true, false);
    T = readtable(csv_path, 'VariableNamingRule', 'preserve');
    T.TrackID = [100; 101; 100];
    writetable(T, csv_path);

    audit = run_blob_gap_audit(fixture_dir, 'WriteReport', false);

    verifyEqual(testCase, audit.tracking_info.status, 'READY_EXISTING_TRACKID');
    verifyMetricStatus(testCase, audit, 'per_blob_area_shrink_rate', {'READY_DERIVED'});
end


function test_ok_frame_nblobs_mismatch_fails_coverage(testCase)
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    write_chunk(fixture_dir, 1:2, [1 1], {'ok', 'ok'});
    nblobs_arr = [1; 3]; %#ok<NASGU>
    last_completed_frame = 2; %#ok<NASGU>
    save(fullfile(fixture_dir, 'checkpoint_0002.mat'), 'nblobs_arr', 'last_completed_frame');

    audit = run_blob_gap_audit(fixture_dir, 'WriteReport', false);

    verifyEqual(testCase, audit.overall_status, 'FAIL_CHUNK_INTEGRITY');
    frame2 = audit.outputs.frame_coverage(audit.outputs.frame_coverage.FrameIndex == 2, :);
    verifyEqual(testCase, frame2.RowCountMatchesNBlobs{1}, 'false');
end


function test_unknown_chunk_schema_is_fatal(testCase)
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    chunks_dir = fullfile(fixture_dir, 'blob_detail_chunks');
    mkdir(chunks_dir);
    chunk = struct('unexpected_field', 1); %#ok<NASGU>
    save(fullfile(chunks_dir, 'blob_detail_bad_schema.mat'), 'chunk');
    write_blob_csv(fixture_dir, true, true, false);

    audit = run_blob_gap_audit(fixture_dir, 'WriteReport', false);

    verifyEqual(testCase, audit.primary_source.type, 'chunks');
    verifyEqual(testCase, audit.overall_status, 'FAIL_CHUNK_INTEGRITY');
    verifyFalse(testCase, audit.outputs.chunk_integrity.schema_ok(1));
end


function test_sampled_csv_does_not_fail_unsampled_coverage(testCase)
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    write_blob_csv(fixture_dir, true, true, false);
    nblobs_arr = [2; 1; 0; 0; 0]; %#ok<NASGU>
    last_completed_frame = 5; %#ok<NASGU>
    save(fullfile(fixture_dir, 'checkpoint_0005.mat'), 'nblobs_arr', 'last_completed_frame');

    audit = run_blob_gap_audit(fixture_dir, 'WriteReport', false, ...
        'MaxCsvBytesForFullRead', 1, 'MaxCsvRowsForProfiling', 2);

    verifyTrue(testCase, audit.outputs.csv_integrity.full_frame_coverage_unknown(1));
    verifyFalse(testCase, any(strcmp(audit.status_flags, 'FAIL_FRAME_COVERAGE')));
end


function test_track_id_without_area_or_time_does_not_mark_rates_ready(testCase)
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    FrameIndex = [1; 2];
    BlobID = [1; 1];
    TrackID = [10; 10];
    T = table(FrameIndex, BlobID, TrackID);
    writetable(T, fullfile(fixture_dir, 'blob_detail_all_frames.csv'));

    audit = run_blob_gap_audit(fixture_dir, 'WriteReport', false);

    verifyMetricStatus(testCase, audit, 'per_blob_area_shrink_rate', {'UNKNOWN'});
    verifyMetricStatus(testCase, audit, 'centroid_speed', {'UNKNOWN'});
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
        try
            rmdir(fixture_dir, 's');
        catch
        end
    end
end


function csv_path = write_blob_csv(folder, include_perimeter, include_frame_time, include_geometry)
    frame = [1; 1; 2];
    blob = [1; 2; 1];
    area = [10; 20; 12];
    circularity = [0.8; 0.7; 0.85];
    aspect_ratio = [1.2; 1.5; 1.1];
    centroid_x = [5; 10; 6];
    centroid_y = [6; 11; 7];
    T = table(frame, blob, area, circularity, aspect_ratio, centroid_x, centroid_y, ...
        'VariableNames', {'FrameIndex', 'BlobID', 'Area', 'Circularity', 'AspectRatio', ...
        'Centroid_X', 'Centroid_Y'});
    if include_frame_time
        T = addvars(T, [0; 0; 1], 'After', 'FrameIndex', 'NewVariableNames', {'FrameTime'});
    end
    if include_perimeter
        T = addvars(T, [12; 18; 13], 'After', 'Area', 'NewVariableNames', {'Perimeter'});
    end
    if include_geometry
        T.Boundary = repmat({'[0 0;1 0;1 1;0 1]'}, height(T), 1);
        T.ConvexHull = repmat({'[0 0;1 0;1 1;0 1]'}, height(T), 1);
    end
    csv_path = fullfile(folder, 'blob_detail_all_frames.csv');
    writetable(T, csv_path);
end


function write_chunk(folder, frame_indices, row_counts, statuses, filename)
    if nargin < 5
        filename = sprintf('blob_detail_%06d_%06d.mat', min(frame_indices), max(frame_indices));
    end
    chunks_dir = fullfile(folder, 'blob_detail_chunks');
    if ~isfolder(chunks_dir)
        mkdir(chunks_dir);
    end

    frames_col = frame_indices(:);
    frame_times = frames_col - 1;
    frame_status = reshape(string(statuses), [], 1);
    detail_counts = row_counts(:);
    error_message = strings(numel(frames_col), 1);
    chunk = struct();
    chunk.version = 1;
    chunk.frame_start = min(frames_col);
    chunk.frame_end = max(frames_col);
    chunk.frame_manifest = table(frames_col, frame_times, frame_status, detail_counts, error_message, ...
        'VariableNames', {'FrameIndex', 'FrameTime', 'FrameStatus', 'DetailRowCount', 'ErrorMessage'});

    blob_ids = [];
    blob_frames = [];
    for idx = 1:numel(frames_col)
        if strcmp(char(frame_status(idx)), 'ok')
            n = detail_counts(idx);
            blob_ids = [blob_ids; (1:n)']; %#ok<AGROW>
            blob_frames = [blob_frames; repmat(frames_col(idx), n, 1)]; %#ok<AGROW>
        end
    end
    chunk.blob_detail_table = make_blob_table(blob_ids, blob_frames);
    chunk.schema_variable_names = chunk.blob_detail_table.Properties.VariableNames;
    chunk.created_at = datestr(now, 30);
    save(fullfile(chunks_dir, filename), 'chunk');
end


function T = make_blob_table(blob_ids, frame_indices)
    blob_ids = blob_ids(:);
    frame_indices = frame_indices(:);
    n = numel(blob_ids);
    frame_times = frame_indices - 1;
    area = 10 + blob_ids;
    perimeter = 12 + blob_ids;
    circularity = 0.8 * ones(n, 1);
    aspect_ratio = 1.2 * ones(n, 1);
    eccentricity = 0.3 * ones(n, 1);
    solidity = 0.9 * ones(n, 1);
    equiv_diameter = 2 * sqrt(area / pi);
    equiv_radius = equiv_diameter / 2;
    compactness = solidity;
    euler_number = ones(n, 1);
    centroid_x = 5 + blob_ids;
    centroid_y = 6 + blob_ids;
    ganglia = repmat("ganglion", n, 1);
    topo = repmat("droplet", n, 1);
    T = table(frame_indices, frame_times, blob_ids, area, perimeter, circularity, aspect_ratio, ...
        eccentricity, solidity, equiv_diameter, equiv_radius, compactness, euler_number, ...
        centroid_x, centroid_y, ganglia, topo, ...
        'VariableNames', {'FrameIndex', 'FrameTime', 'BlobID', 'Area', 'Perimeter', ...
        'Circularity', 'AspectRatio', 'Eccentricity', 'Solidity', 'EquivDiameter', ...
        'EquivRadius', 'Compactness', 'EulerNumber', 'Centroid_X', 'Centroid_Y', ...
        'GangliaType', 'TopologyType'});
end


function write_text(path, txt)
    fid = fopen(path, 'w');
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fwrite(fid, txt);
end


function verifyMetricStatus(testCase, audit, metric_id, expected_statuses)
    M = audit.outputs.metric_feasibility;
    row = M(strcmp(M.metric_id, metric_id), :);
    verifyEqual(testCase, height(row), 1, ['Metric missing: ' metric_id]);
    verifyTrue(testCase, any(strcmp(row.current_status{1}, expected_statuses)), ...
        sprintf('Metric %s had status %s', metric_id, row.current_status{1}));
end
