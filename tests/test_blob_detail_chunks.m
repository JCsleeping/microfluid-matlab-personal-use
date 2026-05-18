function tests = test_blob_detail_chunks
% TEST_BLOB_DETAIL_CHUNKS  Tests for chunked per-blob detail output.

    setup_path();
    tests = functiontests(localfunctions);
end


function test_writer_flush_export_and_failed_manifest(testCase)
    setup_path();
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    schema = get_blob_detail_legacy_schema();
    writer = init_blob_detail_chunk_writer(fixture_dir, 10, ...
        'v7', 'fresh', schema, 0);

    writer = append_blob_detail_chunk(writer, 1, 0.0, make_blob_detail_table([1; 2]), "ok", "");
    writer = append_blob_detail_chunk(writer, 2, 1.0, table(), "ok", "");
    writer = append_blob_detail_chunk(writer, 3, 2.0, table(), "failed", ...
        [repmat('x', 1, 510) sprintf('\nline2')]);
    verifyEqual(testCase, writer.buffer_frame_count, 3);
    verifyEqual(testCase, writer.buffer_frame_start, 1);
    verifyEqual(testCase, writer.buffer_frame_end, 3);
    [writer, paths] = flush_blob_detail_chunks(writer);

    verifyEqual(testCase, numel(paths), 1);
    verifyEqual(testCase, writer.buffer_frame_count, 0);

    chunk = validate_blob_detail_chunk(paths{1}, schema);
    verifyEqual(testCase, chunk.frame_start, 1);
    verifyEqual(testCase, chunk.frame_end, 3);
    verifyEqual(testCase, string(chunk.frame_manifest.FrameStatus), ["ok"; "ok"; "failed"]);
    verifyEqual(testCase, chunk.frame_manifest.DetailRowCount, [2; 0; 0]);
    verifyLessThanOrEqual(testCase, strlength(chunk.frame_manifest.ErrorMessage(3)), 500);
    verifyFalse(testCase, contains(chunk.frame_manifest.ErrorMessage(3), newline));

    csv_path = fullfile(fixture_dir, 'blob_detail_all_frames.csv');
    export_blob_detail_chunks_csv(writer.chunks_dir, csv_path, schema);
    T = readtable(csv_path, 'VariableNamingRule', 'preserve', 'TextType', 'string');
    verifyEqual(testCase, height(T), 2);
    verifyEqual(testCase, T.FrameIndex, [1; 1]);
    verifyFalse(testCase, any(strcmp(T.Properties.VariableNames, 'FrameStatus')));
end


function test_reconcile_rejects_missing_zero_frame_manifest(testCase)
    setup_path();
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    schema = get_blob_detail_legacy_schema();
    writer = init_blob_detail_chunk_writer(fixture_dir, 10, ...
        'v7', 'fresh', schema, 0);
    writer = append_blob_detail_chunk(writer, 1, 0.0, make_blob_detail_table(1), "ok", "");
    writer = append_blob_detail_chunk(writer, 3, 2.0, make_blob_detail_table(3), "ok", "");
    [writer, ~] = flush_blob_detail_chunks(writer);

    verifyError(testCase, ...
        @() reconcile_blob_detail_chunks(writer.chunks_dir, [1; 0; 1], 3, ...
        writer.csv_path, 'resume'), ...
        'reconcile_blob_detail_chunks:missingHistoricalFrames');
end


function test_writer_rejects_duplicate_frame(testCase)
    setup_path();
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    schema = get_blob_detail_legacy_schema();
    writer = init_blob_detail_chunk_writer(fixture_dir, 10, ...
        'v7', 'fresh', schema, 0);
    writer = append_blob_detail_chunk(writer, 1, 0.0, table(), "ok", "");

    verifyError(testCase, ...
        @() append_blob_detail_chunk(writer, 1, 0.5, table(), "ok", ""), ...
        'append_blob_detail_chunk:nonIncreasingFrameIndex');
end


function test_reconcile_truncates_future_chunk_and_archives_stale_csv(testCase)
    setup_path();
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    schema = get_blob_detail_legacy_schema();
    writer = init_blob_detail_chunk_writer(fixture_dir, 10, ...
        'v7', 'fresh', schema, 0);
    writer = append_blob_detail_chunk(writer, 1, 0.0, make_blob_detail_table(1), "ok", "");
    writer = append_blob_detail_chunk(writer, 2, 1.0, table(), "ok", "");
    writer = append_blob_detail_chunk(writer, 3, 2.0, make_blob_detail_table(3), "ok", "");
    writer = append_blob_detail_chunk(writer, 4, 3.0, make_blob_detail_table(4), "ok", "");
    [~, paths] = flush_blob_detail_chunks(writer);
    verifyTrue(testCase, isfile(paths{1}));

    csv_path = fullfile(fixture_dir, 'blob_detail_all_frames.csv');
    writetable(table(1, 'VariableNames', {'FrameIndex'}), csv_path);

    status = reconcile_blob_detail_chunks(fullfile(fixture_dir, 'blob_detail_chunks'), ...
        [1; 0; 1; 1], 2, csv_path, 'resume');

    verifyTrue(testCase, status.ok);
    verifyFalse(testCase, isfile(paths{1}));
    verifyTrue(testCase, isfile(fullfile(fixture_dir, 'blob_detail_chunks', ...
        'blob_detail_000001_000002.mat')));
    verifyFalse(testCase, isfile(csv_path));
    verifyEqual(testCase, numel(dir(fullfile(fixture_dir, 'blob_detail_all_frames.stale_*.csv'))), 1);
end


function test_reconcile_allows_failed_frame_with_carried_forward_nblobs(testCase)
    setup_path();
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    schema = get_blob_detail_legacy_schema();
    writer = init_blob_detail_chunk_writer(fixture_dir, 10, ...
        'v7', 'fresh', schema, 0);
    writer = append_blob_detail_chunk(writer, 1, 0.0, make_blob_detail_table(1), "ok", "");
    writer = append_blob_detail_chunk(writer, 2, 1.0, table(), "failed", ...
        "synthetic failure");
    [writer, ~] = flush_blob_detail_chunks(writer);

    status = reconcile_blob_detail_chunks(writer.chunks_dir, [1; 1], 2, ...
        writer.csv_path, 'resume');
    verifyTrue(testCase, status.ok);

    export_blob_detail_chunks_csv(writer.chunks_dir, writer.csv_path, schema);
    T = readtable(writer.csv_path, 'VariableNamingRule', 'preserve');
    verifyEqual(testCase, height(T), 1);
    verifyEqual(testCase, T.FrameIndex, 1);
end


function test_legacy_csv_migration_archives_original(testCase)
    setup_path();
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    csv_path = fullfile(fixture_dir, 'blob_detail_all_frames.csv');
    append_blob_detail_csv(csv_path, 1, 0.0, make_blob_detail_table([1; 2]));

    status = reconcile_blob_detail_chunks(fullfile(fixture_dir, 'blob_detail_chunks'), ...
        [2], 1, csv_path, 'resume');

    verifyTrue(testCase, status.ok);
    verifyTrue(testCase, status.migrated_legacy_csv);
    verifyFalse(testCase, isfile(csv_path));
    verifyEqual(testCase, numel(dir(fullfile(fixture_dir, ...
        'blob_detail_all_frames.legacy_migrated_*.csv'))), 1);
    verifyTrue(testCase, isfile(fullfile(fixture_dir, 'blob_detail_chunks', ...
        'blob_detail_000001_000001.mat')));
end


function test_writer_falls_back_to_v7_for_non_ascii_v73_path(testCase)
    setup_path();
    fixture_dir = make_non_ascii_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    schema = get_blob_detail_legacy_schema();
    writer = init_blob_detail_chunk_writer(fixture_dir, 10, ...
        'v7.3-nocompression', 'fresh', schema, 0, true, 512 * 1024^2);

    verifyEqual(testCase, writer.requested_save_format, 'v7.3-nocompression');
    verifyEqual(testCase, writer.save_format, 'v7');
    verifyTrue(testCase, writer.format_probe.fallback_used);
    verifyTrue(testCase, writer.chunks_dir_has_non_ascii);
end


function test_writer_errors_on_non_ascii_v73_path_without_fallback(testCase)
    setup_path();
    fixture_dir = make_non_ascii_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    schema = get_blob_detail_legacy_schema();
    verifyError(testCase, ...
        @() init_blob_detail_chunk_writer(fixture_dir, 10, ...
        'v7.3-nocompression', 'fresh', schema, 0, false, 512 * 1024^2), ...
        'init_blob_detail_chunk_writer:nonAsciiV73Path');
end


function test_flush_errors_when_v7_chunk_exceeds_hard_limit(testCase)
    setup_path();
    fixture_dir = make_temp_dir();
    cleanup = onCleanup(@() cleanup_temp_dir(fixture_dir)); %#ok<NASGU>

    schema = get_blob_detail_legacy_schema();
    writer = init_blob_detail_chunk_writer(fixture_dir, 10, ...
        'v7', 'fresh', schema, 0);
    writer = append_blob_detail_chunk(writer, 1, 0.0, make_blob_detail_table(1), "ok", "");
    writer.v7_hard_max_bytes = 1;

    verifyError(testCase, @() flush_blob_detail_chunks(writer), ...
        'flush_blob_detail_chunks:v7ChunkTooLarge');
end


function test_config_rejects_invalid_blob_detail_settings(testCase)
    setup_path();

    fake_tif = {fullfile(tempdir, 'not_used.tif')};
    verifyError(testCase, @() config_pipeline('multipage_tif_path', fake_tif, ...
        'output.blob_detail_chunk_size', 0), 'validate_config:badParam');
    verifyError(testCase, @() config_pipeline('multipage_tif_path', fake_tif, ...
        'output.blob_detail_chunk_size', 5001), 'validate_config:badParam');
    verifyError(testCase, @() config_pipeline('multipage_tif_path', fake_tif, ...
        'output.blob_detail_chunk_size', 10.5), 'validate_config:badParam');
    verifyError(testCase, @() config_pipeline('multipage_tif_path', fake_tif, ...
        'output.blob_detail_save_format', 'bad-format'), 'validate_config:badParam');
    verifyError(testCase, @() config_pipeline('multipage_tif_path', fake_tif, ...
        'output.blob_detail_allow_format_fallback', 1), 'validate_config:badParam');
    verifyError(testCase, @() config_pipeline('multipage_tif_path', fake_tif, ...
        'output.blob_detail_chunk_max_bytes', 1024), 'validate_config:badParam');
end


function test_validate_config_fills_missing_blob_detail_defaults(testCase)
    setup_path();
    fake_tif = {fullfile(tempdir, 'not_used.tif')};
    config = config_pipeline('multipage_tif_path', fake_tif);
    config.output = rmfield(config.output, {'blob_detail_chunk_size', ...
        'blob_detail_save_format', 'blob_detail_allow_format_fallback', ...
        'blob_detail_chunk_max_bytes'});

    config = validate_config(config);

    verifyEqual(testCase, config.output.blob_detail_chunk_size, 100);
    verifyEqual(testCase, config.output.blob_detail_save_format, 'v7');
    verifyTrue(testCase, config.output.blob_detail_allow_format_fallback);
    verifyEqual(testCase, config.output.blob_detail_chunk_max_bytes, 512 * 1024^2);
end


function setup_path()
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));
end


function fixture_dir = make_temp_dir()
    fixture_dir = tempname(tempdir);
    mkdir(fixture_dir);
end


function fixture_dir = make_non_ascii_temp_dir()
    fixture_dir = fullfile(tempdir, ['blob_detail_中文_' datestr(now, 'yyyymmdd_HHMMSSFFF')]);
    mkdir(fixture_dir);
end


function cleanup_temp_dir(fixture_dir)
    if exist(fixture_dir, 'dir')
        rmdir(fixture_dir, 's');
    end
end


function blob_table = make_blob_detail_table(blob_ids)
    blob_ids = blob_ids(:);
    blob_table = table(blob_ids, blob_ids * 10, blob_ids * 2, ...
        0.5 + blob_ids * 0.01, blob_ids + 1, 0.1 * blob_ids, ...
        0.9 + zeros(size(blob_ids)), blob_ids * 3, blob_ids * 1.5, ...
        0.8 + zeros(size(blob_ids)), ones(size(blob_ids)), ...
        blob_ids * 4, blob_ids * 5, repmat("ganglion", size(blob_ids)), ...
        repmat("droplet", size(blob_ids)), ...
        'VariableNames', {'BlobID', 'Area', 'Perimeter', 'Circularity', ...
        'AspectRatio', 'Eccentricity', 'Solidity', 'EquivDiameter', ...
        'EquivRadius', 'Compactness', 'EulerNumber', 'Centroid_X', ...
        'Centroid_Y', 'GangliaType', 'TopologyType'});
end
