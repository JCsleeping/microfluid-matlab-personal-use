function [row, manifest, blob_table] = check_chunk_integrity(chunk_path, results_info)
% CHECK_CHUNK_INTEGRITY  Inspect one chunk file and return audit row.

    manifest = table();
    blob_table = table();
    defaults = {chunk_path, false, false, 'unreadable', false, NaN, NaN, NaN, NaN, ...
        0, 0, 0, 0, 0, false, '', false, false, false, false, false, false, ...
        false, false, false, false, 'none', false, false, ''};
    row = defaults;

    try
        S = load(chunk_path, 'chunk');
        row{2} = true;
    catch ME
        row{30} = ME.message;
        return;
    end
    if ~isfield(S, 'chunk')
        row{30} = 'MAT file does not contain variable chunk';
        return;
    end
    row{3} = true;
    chunk = S.chunk;

    [schema_class, manifest, blob_table, manifest_quality, needs_migration, zero_blob_unknown] = derive_chunk_tables(chunk);
    row{4} = schema_class;
    row{27} = manifest_quality;
    row{28} = needs_migration;
    row{29} = zero_blob_unknown;
    row{5} = ~strcmp(schema_class, 'unknown');

    if isfield(chunk, 'frame_start'), row{6} = double(chunk.frame_start); end
    if isfield(chunk, 'frame_end'), row{7} = double(chunk.frame_end); end
    if ~isempty(manifest) && height(manifest) > 0
        row{8} = min(manifest.FrameIndex);
        row{9} = max(manifest.FrameIndex);
        row{10} = height(manifest);
        row{12} = sum(strcmp(manifest.FrameStatus, 'ok'));
        row{13} = sum(strcmp(manifest.FrameStatus, 'failed'));
        ok_rows = strcmp(manifest.FrameStatus, 'ok');
        row{14} = sum(ok_rows & manifest.DetailRowCount == 0);
        row{16} = strjoin(unique(manifest.FrameStatus).', '|');
        row{17} = any(~ismember(manifest.FrameStatus, {'ok', 'failed'}));
        row{18} = numel(unique(manifest.FrameIndex)) ~= numel(manifest.FrameIndex);
    end
    if ~isempty(blob_table)
        row{11} = height(blob_table);
    end
    if ~isempty(manifest) && ~isempty(blob_table) && any(strcmp(blob_table.Properties.VariableNames, 'FrameIndex'))
        row{19} = any(~ismember(blob_table.FrameIndex, manifest.FrameIndex));
    end
    if isfinite(row{6}) && isfinite(row{8})
        row{20} = row{6} ~= row{8};
    end
    if isfinite(row{7}) && isfinite(row{9})
        row{21} = row{7} ~= row{9};
    end
    if isfield(chunk, 'schema_variable_names') && ~isempty(blob_table)
        row{22} = ~isequal(cellstr(chunk.schema_variable_names(:).'), blob_table.Properties.VariableNames);
    end

    row{15} = check_row_counts(manifest, blob_table, results_info);
end


function [schema_class, manifest, blob_table, manifest_quality, needs_migration, zero_blob_unknown] = derive_chunk_tables(chunk)
    schema_class = 'unknown';
    manifest = table();
    blob_table = table();
    manifest_quality = 'none';
    needs_migration = false;
    zero_blob_unknown = false;

    if isfield(chunk, 'blob_detail_table') && istable(chunk.blob_detail_table)
        blob_table = chunk.blob_detail_table;
    end

    if all(isfield(chunk, {'version', 'frame_start', 'frame_end', 'frame_manifest', ...
            'blob_detail_table', 'schema_variable_names', 'created_at'})) && istable(chunk.frame_manifest)
        schema_class = 'new_v1';
        manifest = normalize_manifest(chunk.frame_manifest);
        manifest_quality = 'frame_manifest';
        return;
    end

    legacy_fields = {'processed_frame_indices', 'frame_times', 'nblobs_by_frame', ...
        'frame_status', 'error_message'};
    if all(isfield(chunk, legacy_fields))
        schema_class = 'legacy_candidate';
        needs_migration = true;
        frames = chunk.processed_frame_indices(:);
        times = chunk.frame_times(:);
        status = cellstr(string(chunk.frame_status(:)));
        counts = chunk.nblobs_by_frame(:);
        errors = cellstr(string(chunk.error_message(:)));
        manifest = table(frames, times, status, counts, errors, ...
            'VariableNames', {'FrameIndex', 'FrameTime', 'FrameStatus', 'DetailRowCount', 'ErrorMessage'});
        manifest = normalize_manifest(manifest);
        manifest_quality = 'legacy_arrays';
        return;
    end

    if ~isempty(blob_table) && any(strcmp(blob_table.Properties.VariableNames, 'FrameIndex'))
        schema_class = 'rows_only';
        frames = unique(blob_table.FrameIndex);
        counts = zeros(numel(frames), 1);
        times = nan(numel(frames), 1);
        for idx = 1:numel(frames)
            counts(idx) = sum(blob_table.FrameIndex == frames(idx));
            if any(strcmp(blob_table.Properties.VariableNames, 'FrameTime'))
                times(idx) = blob_table.FrameTime(find(blob_table.FrameIndex == frames(idx), 1));
            end
        end
        status = repmat({'unknown'}, numel(frames), 1);
        errors = repmat({''}, numel(frames), 1);
        manifest = table(frames(:), times(:), status, counts(:), errors, ...
            'VariableNames', {'FrameIndex', 'FrameTime', 'FrameStatus', 'DetailRowCount', 'ErrorMessage'});
        manifest_quality = 'partial_from_rows_only';
        zero_blob_unknown = true;
    end
end


function manifest = normalize_manifest(manifest)
    if ~iscell(manifest.FrameStatus)
        manifest.FrameStatus = cellstr(string(manifest.FrameStatus));
    end
    if ~iscell(manifest.ErrorMessage)
        manifest.ErrorMessage = cellstr(string(manifest.ErrorMessage));
    end
    manifest.FrameIndex = double(manifest.FrameIndex);
    manifest.FrameTime = double(manifest.FrameTime);
    manifest.DetailRowCount = double(manifest.DetailRowCount);
end


function ok = check_row_counts(manifest, blob_table, results_info)
    ok = true;
    if isempty(manifest) || height(manifest) == 0
        ok = false;
        return;
    end
    has_frame_index = ~isempty(blob_table) && any(strcmp(blob_table.Properties.VariableNames, 'FrameIndex'));
    for idx = 1:height(manifest)
        frame = manifest.FrameIndex(idx);
        if has_frame_index
            row_count = sum(blob_table.FrameIndex == frame);
        else
            row_count = 0;
        end
        status = manifest.FrameStatus{idx};
        if strcmp(status, 'failed')
            if manifest.DetailRowCount(idx) ~= 0 || row_count ~= 0
                ok = false;
            end
            continue;
        elseif strcmp(status, 'ok')
            if row_count ~= manifest.DetailRowCount(idx)
                ok = false;
            end
            if nargin >= 3 && isfield(results_info, 'has_nblobs_arr') && results_info.has_nblobs_arr && ...
                    frame <= numel(results_info.nblobs_arr)
                if manifest.DetailRowCount(idx) ~= results_info.nblobs_arr(frame)
                    ok = false;
                end
            end
        end
    end
end
