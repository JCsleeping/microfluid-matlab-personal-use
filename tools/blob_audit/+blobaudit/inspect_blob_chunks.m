function info = inspect_blob_chunks(inventory, results_info)
% INSPECT_BLOB_CHUNKS  Inspect blob chunk MAT files without fail-fast listing.

    chunk_rows = strcmp(inventory.file_type, 'blob_chunk_mat');
    paths = inventory.path(chunk_rows);
    rows = cell(0, 30);
    all_manifest = {};
    all_tables = {};
    fatal = false;

    for idx = 1:numel(paths)
        [row, manifest, blob_table] = blobaudit.check_chunk_integrity(paths{idx}, results_info);
        rows(end + 1, :) = row; %#ok<AGROW>
        if ~isempty(manifest)
            all_manifest{end + 1} = manifest; %#ok<AGROW>
        end
        if ~isempty(blob_table)
            all_tables{end + 1} = blob_table; %#ok<AGROW>
        end
    end

    chunk_integrity = rows_to_table(rows);
    if height(chunk_integrity) > 1
        chunk_integrity = add_cross_chunk_flags(chunk_integrity);
    end

    if ~isempty(all_manifest)
        manifest = vertcat(all_manifest{:});
    else
        manifest = table();
    end
    if ~isempty(all_tables)
        try
            blob_table = vertcat(all_tables{:});
        catch
            blob_table = all_tables{1};
        end
    else
        blob_table = table();
    end

    if height(chunk_integrity) > 0
        fatal = any(~chunk_integrity.load_ok | ~chunk_integrity.has_chunk_variable | ...
            ~chunk_integrity.schema_ok | ~chunk_integrity.row_count_ok | ...
            chunk_integrity.has_duplicate_manifest_frames | chunk_integrity.has_blob_rows_outside_manifest | ...
            chunk_integrity.has_frame_start_mismatch | chunk_integrity.has_frame_end_mismatch | ...
            chunk_integrity.has_overlap);
    end

    info = struct();
    info.chunk_integrity = chunk_integrity;
    info.manifest = manifest;
    info.blob_table = blob_table;
    info.has_fatal_integrity_error = fatal;
end


function T = rows_to_table(rows)
    names = {'chunk_path', 'load_ok', 'has_chunk_variable', 'schema_class', ...
        'schema_ok', 'frame_start', 'frame_end', 'manifest_min_frame', ...
        'manifest_max_frame', 'n_manifest_frames', 'n_blob_rows', 'n_ok_frames', ...
        'n_failed_frames', 'n_zero_blob_ok_frames', 'row_count_ok', 'status_values', ...
        'has_unknown_status', 'has_duplicate_manifest_frames', 'has_blob_rows_outside_manifest', ...
        'has_frame_start_mismatch', 'has_frame_end_mismatch', 'has_schema_name_mismatch', ...
        'has_overlap', 'has_gap_before', 'nonmonotonic_order', ...
        'duplicate_frame_across_chunks', 'manifest_quality', ...
        'needs_manifest_migration', 'zero_blob_frames_not_recoverable', 'error_message'};
    if isempty(rows)
        T = cell2table(cell(0, numel(names)), 'VariableNames', names);
        T = coerce_types(T);
        return;
    end
    T = cell2table(rows, 'VariableNames', names);
    T = coerce_types(T);
end


function T = coerce_types(T)
    logical_vars = {'load_ok', 'has_chunk_variable', 'schema_ok', 'row_count_ok', ...
        'has_unknown_status', 'has_duplicate_manifest_frames', 'has_blob_rows_outside_manifest', ...
        'has_frame_start_mismatch', 'has_frame_end_mismatch', 'has_schema_name_mismatch', ...
        'has_overlap', 'has_gap_before', 'nonmonotonic_order', ...
        'duplicate_frame_across_chunks', 'needs_manifest_migration', ...
        'zero_blob_frames_not_recoverable'};
    numeric_vars = {'frame_start', 'frame_end', 'manifest_min_frame', 'manifest_max_frame', ...
        'n_manifest_frames', 'n_blob_rows', 'n_ok_frames', 'n_failed_frames', ...
        'n_zero_blob_ok_frames'};
    for idx = 1:numel(logical_vars)
        v = logical_vars{idx};
        if iscell(T.(v)), T.(v) = cell2mat(T.(v)); end
    end
    for idx = 1:numel(numeric_vars)
        v = numeric_vars{idx};
        if iscell(T.(v)), T.(v) = cell2mat(T.(v)); end
    end
end


function T = add_cross_chunk_flags(T)
    [~, order] = sort(T.frame_start);
    prev_end = NaN;
    seen = [];
    for k = 1:numel(order)
        idx = order(k);
        if k > 1
            T.has_gap_before(idx) = T.frame_start(idx) > prev_end + 1;
            T.has_overlap(idx) = T.frame_start(idx) <= prev_end;
            T.nonmonotonic_order(idx) = idx ~= order(k);
        end
        if isfinite(T.manifest_min_frame(idx)) && isfinite(T.manifest_max_frame(idx))
            frames = T.manifest_min_frame(idx):T.manifest_max_frame(idx);
            T.duplicate_frame_across_chunks(idx) = any(ismember(frames, seen));
            seen = [seen, frames]; %#ok<AGROW>
        end
        prev_end = max(prev_end, T.frame_end(idx));
    end
end
