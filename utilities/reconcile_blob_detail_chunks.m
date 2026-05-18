function status = reconcile_blob_detail_chunks(chunks_dir, nblobs_arr, last_completed_frame, legacy_csv_path, mode)
% RECONCILE_BLOB_DETAIL_CHUNKS  Make blob-detail chunks consistent with checkpoint.

    if nargin < 5 || isempty(mode)
        mode = 'resume';
    end
    mode = lower(char(string(mode)));
    if ~strcmp(mode, 'resume')
        error('reconcile_blob_detail_chunks:invalidMode', ...
            'Chunk reconciliation is only valid in resume mode.');
    end

    expected_schema = get_blob_detail_legacy_schema();
    last_completed_frame = max(0, min(double(last_completed_frame), numel(nblobs_arr)));
    nblobs_arr = reshape(double(nblobs_arr), [], 1);

    status = struct( ...
        'ok', false, ...
        'action_taken', {{}}, ...
        'deleted_chunks', {{}}, ...
        'truncated_chunks', {{}}, ...
        'migrated_legacy_csv', false, ...
        'last_verified_frame', last_completed_frame, ...
        'error_reason', '');

    output_path = fileparts(chunks_dir);
    if ~isfolder(output_path)
        mkdir(output_path);
    end
    if ~isfolder(chunks_dir)
        mkdir(chunks_dir);
    end

    status = cleanup_stale_temp_files(status, chunks_dir, output_path);

    chunk_files = list_blob_detail_chunk_files(chunks_dir);
    if isempty(chunk_files)
        if exist(legacy_csv_path, 'file') == 2
            migrate_legacy_csv_to_chunk(chunks_dir, legacy_csv_path, ...
                nblobs_arr, last_completed_frame, expected_schema);
            archive_file_with_suffix(legacy_csv_path, 'legacy_migrated');
            status.migrated_legacy_csv = true;
            status.action_taken{end + 1} = 'migrated_legacy_csv';
            chunk_files = list_blob_detail_chunk_files(chunks_dir);
        elseif last_completed_frame == 0 || all(nblobs_arr(1:last_completed_frame) == 0)
            status.ok = true;
            status.action_taken{end + 1} = 'allowed_missing_zero_history';
            return;
        else
            status.error_reason = ['Missing blob-detail chunks and legacy CSV, but ' ...
                'checkpoint history contains nonzero blob counts. save_blob_detail ' ...
                'cannot be toggled off for historical nonzero frames and later resumed.'];
            error('reconcile_blob_detail_chunks:missingHistoricalChunks', status.error_reason);
        end
    elseif exist(legacy_csv_path, 'file') == 2
        archive_file_with_suffix(legacy_csv_path, 'stale');
        status.action_taken{end + 1} = 'archived_stale_csv';
    end

    [chunk_files, status] = reconcile_chunk_ranges(chunks_dir, chunk_files, ...
        last_completed_frame, expected_schema, status);
    status = validate_chunk_coverage(chunk_files, nblobs_arr, ...
        last_completed_frame, expected_schema, status);
    status.ok = true;
end


function status = cleanup_stale_temp_files(status, chunks_dir, output_path)
    tmp_mat = dir(fullfile(chunks_dir, '*.tmp.mat'));
    for idx = 1:numel(tmp_mat)
        delete(fullfile(tmp_mat(idx).folder, tmp_mat(idx).name));
        status.action_taken{end + 1} = ['deleted_temp:' tmp_mat(idx).name]; %#ok<AGROW>
    end

    tmp_csv = dir(fullfile(output_path, '*.tmp.csv'));
    for idx = 1:numel(tmp_csv)
        delete(fullfile(tmp_csv(idx).folder, tmp_csv(idx).name));
        status.action_taken{end + 1} = ['deleted_temp:' tmp_csv(idx).name]; %#ok<AGROW>
    end
end


function [chunk_files, status] = reconcile_chunk_ranges(chunks_dir, chunk_files, last_completed_frame, expected_schema, status)
    for idx = 1:numel(chunk_files)
        path = chunk_files(idx).path;
        chunk = validate_blob_detail_chunk(path, expected_schema);

        if chunk.frame_start > last_completed_frame
            delete(path);
            status.deleted_chunks{end + 1} = path;
            status.action_taken{end + 1} = ['deleted_future_chunk:' path];
            continue;
        end

        if chunk.frame_end > last_completed_frame
            new_path = truncate_crossing_chunk(chunks_dir, path, chunk, last_completed_frame, expected_schema);
            status.truncated_chunks{end + 1} = struct('old_path', path, 'new_path', new_path);
            status.action_taken{end + 1} = ['truncated_chunk:' path];
        end
    end

    chunk_files = list_blob_detail_chunk_files(chunks_dir);
end


function new_final = truncate_crossing_chunk(chunks_dir, old_path, chunk, last_completed_frame, expected_schema)
    keep_rows = chunk.frame_manifest.FrameIndex <= last_completed_frame;
    if ~any(keep_rows)
        delete(old_path);
        new_final = '';
        return;
    end

    kept_manifest = chunk.frame_manifest(keep_rows, :);
    kept_frames = kept_manifest.FrameIndex;
    kept_blob_rows = ismember(chunk.blob_detail_table.FrameIndex, kept_frames);

    new_chunk = chunk;
    new_chunk.frame_manifest = kept_manifest;
    new_chunk.blob_detail_table = chunk.blob_detail_table(kept_blob_rows, :);
    new_chunk.frame_start = min(kept_frames);
    new_chunk.frame_end = max(kept_frames);
    new_chunk.created_at = datestr(now, 30);
    validate_blob_detail_chunk(new_chunk, expected_schema);

    new_final = fullfile(chunks_dir, sprintf('blob_detail_%06d_%06d.mat', ...
        new_chunk.frame_start, new_chunk.frame_end));
    new_tmp = fullfile(chunks_dir, sprintf('blob_detail_%06d_%06d.tmp.mat', ...
        new_chunk.frame_start, new_chunk.frame_end));

    if exist(new_tmp, 'file') == 2
        delete(new_tmp);
    end
    chunk = new_chunk; %#ok<NASGU>
    save(new_tmp, 'chunk', '-v7.3', '-nocompression');
    validate_blob_detail_chunk(new_tmp, expected_schema);
    atomic_replace_file(new_tmp, new_final, ...
        @(path) validate_blob_detail_chunk(path, expected_schema));

    if ~strcmp(old_path, new_final) && exist(old_path, 'file') == 2
        delete(old_path);
    end
end


function status = validate_chunk_coverage(chunk_files, nblobs_arr, last_completed_frame, expected_schema, status)
    previous_end = 0;
    covered = false(last_completed_frame, 1);

    for idx = 1:numel(chunk_files)
        chunk = validate_blob_detail_chunk(chunk_files(idx).path, expected_schema);
        if chunk.frame_start <= previous_end
            if chunk.frame_end <= previous_end
                delete(chunk_files(idx).path);
                continue;
            end
            error('reconcile_blob_detail_chunks:overlappingChunks', ...
                'Blob detail chunks overlap near frame %d.', chunk.frame_start);
        end
        previous_end = chunk.frame_end;

        manifest = chunk.frame_manifest;
        for row = 1:height(manifest)
            frame = manifest.FrameIndex(row);
            if frame > last_completed_frame
                error('reconcile_blob_detail_chunks:futureFrameAfterTruncation', ...
                    'Chunk contains frame %d beyond checkpoint frame %d.', ...
                    frame, last_completed_frame);
            end

            status_value = string(manifest.FrameStatus(row));
            rows_for_frame = sum(chunk.blob_detail_table.FrameIndex == frame);
            if status_value == "ok"
                if manifest.DetailRowCount(row) ~= rows_for_frame || ...
                        manifest.DetailRowCount(row) ~= nblobs_arr(frame)
                    error('reconcile_blob_detail_chunks:perFrameCountMismatch', ...
                        ['Chunk frame %d has DetailRowCount=%d and %d blob rows, ' ...
                         'but checkpoint nblobs_arr expects %d.'], ...
                        frame, manifest.DetailRowCount(row), rows_for_frame, nblobs_arr(frame));
                end
            elseif status_value == "failed"
                if manifest.DetailRowCount(row) ~= 0 || rows_for_frame ~= 0
                    error('reconcile_blob_detail_chunks:failedFrameHasRows', ...
                        'Failed frame %d must have zero blob rows.', frame);
                end
            else
                error('reconcile_blob_detail_chunks:invalidFrameStatus', ...
                    'Unknown FrameStatus "%s".', status_value);
            end
            covered(frame) = true;
        end
    end

    missing_frames = find(~covered);
    if ~isempty(missing_frames)
        error('reconcile_blob_detail_chunks:missingHistoricalFrames', ...
            ['Blob-detail chunks do not cover historical frame %d. Once ' ...
             'chunks exist, every processed historical frame must have a ' ...
             'manifest row, including zero-blob frames.'], ...
            missing_frames(1));
    end
end


function migrate_legacy_csv_to_chunk(chunks_dir, legacy_csv_path, nblobs_arr, last_completed_frame, expected_schema)
    T = readtable(legacy_csv_path, 'VariableNamingRule', 'preserve');
    if ~ismember('FrameIndex', T.Properties.VariableNames)
        error('reconcile_blob_detail_chunks:legacyMissingFrameIndex', ...
            'Legacy CSV %s does not contain FrameIndex.', legacy_csv_path);
    end

    frame_index = double(T.FrameIndex);
    if any(~isfinite(frame_index)) || any(frame_index < 1) || any(frame_index ~= fix(frame_index))
        error('reconcile_blob_detail_chunks:legacyInvalidFrameIndex', ...
            'Legacy CSV %s contains invalid FrameIndex values.', legacy_csv_path);
    end

    historical = frame_index <= last_completed_frame;
    if any(~historical)
        T = T(historical, :);
        frame_index = frame_index(historical);
    end

    normalized = make_empty_blob_detail_table(expected_schema);
    for frame = 1:last_completed_frame
        rows = frame_index == frame;
        actual = sum(rows);
        expected = nblobs_arr(frame);
        if actual ~= expected
            error('reconcile_blob_detail_chunks:legacyCountMismatch', ...
                ['Legacy CSV migration failed at frame %d: found %d rows, ' ...
                 'checkpoint expects %d. Delete stale blob_detail_all_frames.csv ' ...
                 'and rerun from frame 1, or provide a manual manifest override.'], ...
                frame, actual, expected);
        end
        if actual > 0
            frame_time = NaN;
            if ismember('FrameTime', T.Properties.VariableNames)
                frame_time_values = T.FrameTime(rows);
                frame_time = frame_time_values(1);
            end
            frame_table = T(rows, :);
            frame_table = removevars_if_present(frame_table, {'FrameIndex', 'FrameTime'});
            normalized = [normalized; normalize_blob_detail_table(frame_table, frame, frame_time, expected_schema)]; %#ok<AGROW>
        end
    end

    manifest = make_empty_blob_detail_manifest();
    for frame = 1:last_completed_frame
        frame_time = NaN;
        if ismember('FrameTime', T.Properties.VariableNames) && any(frame_index == frame)
            values = T.FrameTime(frame_index == frame);
            frame_time = values(1);
        end
        manifest = [manifest; table(double(frame), double(frame_time), "ok", ...
            double(nblobs_arr(frame)), "", ...
            'VariableNames', manifest.Properties.VariableNames)]; %#ok<AGROW>
    end

    if last_completed_frame == 0
        return;
    end

    chunk = struct();
    chunk.version = 1;
    chunk.frame_start = 1;
    chunk.frame_end = last_completed_frame;
    chunk.frame_manifest = manifest;
    chunk.blob_detail_table = normalized;
    chunk.schema_variable_names = expected_schema.variable_names;
    chunk.created_at = datestr(now, 30);
    validate_blob_detail_chunk(chunk, expected_schema);

    final_path = fullfile(chunks_dir, sprintf('blob_detail_%06d_%06d.mat', ...
        chunk.frame_start, chunk.frame_end));
    tmp_path = fullfile(chunks_dir, sprintf('blob_detail_%06d_%06d.tmp.mat', ...
        chunk.frame_start, chunk.frame_end));
    save(tmp_path, 'chunk', '-v7.3', '-nocompression');
    validate_blob_detail_chunk(tmp_path, expected_schema);
    atomic_replace_file(tmp_path, final_path, ...
        @(path) validate_blob_detail_chunk(path, expected_schema));
end


function T = removevars_if_present(T, names)
    for idx = 1:numel(names)
        if ismember(names{idx}, T.Properties.VariableNames)
            T = removevars(T, names{idx});
        end
    end
end


function archive_file_with_suffix(path, suffix)
    if exist(path, 'file') ~= 2
        return;
    end
    [folder, name, ext] = fileparts(path);
    archive_path = fullfile(folder, sprintf('%s.%s_%s%s', ...
        name, suffix, datestr(now, 'yyyymmdd_HHMMSSFFF'), ext));
    movefile(path, archive_path, 'f');
end
