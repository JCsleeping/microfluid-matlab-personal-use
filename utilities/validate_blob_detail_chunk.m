function chunk = validate_blob_detail_chunk(chunk_or_path, expected_schema)
% VALIDATE_BLOB_DETAIL_CHUNK  Load and validate one blob-detail chunk.

    if nargin < 2 || isempty(expected_schema)
        expected_schema = get_blob_detail_legacy_schema();
    end

    if ischar(chunk_or_path) || isstring(chunk_or_path)
        data = load(char(chunk_or_path), 'chunk');
        if ~isfield(data, 'chunk')
            error('validate_blob_detail_chunk:missingChunk', ...
                'Chunk file %s does not contain variable chunk.', char(chunk_or_path));
        end
        chunk = data.chunk;
    else
        chunk = chunk_or_path;
    end

    required_fields = {'version', 'frame_start', 'frame_end', 'frame_manifest', ...
        'blob_detail_table', 'schema_variable_names', 'created_at'};
    for idx = 1:numel(required_fields)
        if ~isfield(chunk, required_fields{idx})
            error('validate_blob_detail_chunk:missingField', ...
                'Chunk is missing field %s.', required_fields{idx});
        end
    end

    if chunk.version ~= 1
        error('validate_blob_detail_chunk:unsupportedVersion', ...
            'Unsupported blob detail chunk version %g.', chunk.version);
    end

    manifest = chunk.frame_manifest;
    expected_manifest_vars = {'FrameIndex', 'FrameTime', 'FrameStatus', 'DetailRowCount', 'ErrorMessage'};
    if ~istable(manifest) || ~isequal(manifest.Properties.VariableNames, expected_manifest_vars)
        error('validate_blob_detail_chunk:badManifestSchema', ...
            'Chunk frame_manifest has an invalid schema.');
    end
    if ~isnumeric(manifest.FrameIndex) || ~isnumeric(manifest.FrameTime) || ...
            ~isnumeric(manifest.DetailRowCount)
        error('validate_blob_detail_chunk:badManifestTypes', ...
            'FrameIndex, FrameTime, and DetailRowCount must be numeric.');
    end
    manifest.FrameStatus = string(manifest.FrameStatus);
    manifest.ErrorMessage = string(manifest.ErrorMessage);

    if height(manifest) == 0
        error('validate_blob_detail_chunk:emptyManifest', ...
            'Chunk manifest must contain at least one frame.');
    end
    if any(~isfinite(manifest.FrameIndex)) || any(manifest.FrameIndex < 1) || ...
            any(manifest.FrameIndex ~= fix(manifest.FrameIndex)) || ...
            numel(unique(manifest.FrameIndex)) ~= numel(manifest.FrameIndex)
        error('validate_blob_detail_chunk:invalidFrameIndex', ...
            'Chunk manifest contains invalid or duplicate FrameIndex values.');
    end
    if any(diff(manifest.FrameIndex) <= 0)
        error('validate_blob_detail_chunk:nonIncreasingManifest', ...
            'Chunk manifest FrameIndex values must be strictly increasing.');
    end
    if chunk.frame_start ~= min(manifest.FrameIndex) || chunk.frame_end ~= max(manifest.FrameIndex)
        error('validate_blob_detail_chunk:rangeMismatch', ...
            'Chunk frame_start/frame_end do not match manifest range.');
    end

    statuses = string(manifest.FrameStatus);
    if any(~(statuses == "ok" | statuses == "failed"))
        error('validate_blob_detail_chunk:invalidFrameStatus', ...
            'FrameStatus must be ok or failed.');
    end

    T = chunk.blob_detail_table;
    if ~istable(T)
        error('validate_blob_detail_chunk:badBlobTable', ...
            'chunk.blob_detail_table must be a table.');
    end
    if ~isequal(T.Properties.VariableNames, expected_schema.variable_names)
        error('validate_blob_detail_chunk:schemaMismatch', ...
            'Chunk blob_detail_table does not match canonical schema.');
    end
    actual_schema = reshape(cellstr(chunk.schema_variable_names), 1, []);
    if ~isequal(actual_schema, expected_schema.variable_names)
        error('validate_blob_detail_chunk:schemaVariableMismatch', ...
            'Chunk schema_variable_names do not match canonical schema.');
    end
    if height(T) > 0
        if any(~ismember(T.FrameIndex, manifest.FrameIndex))
            error('validate_blob_detail_chunk:unknownBlobFrame', ...
                'Blob rows contain FrameIndex values not present in manifest.');
        end
    end

    for idx = 1:height(manifest)
        frame = manifest.FrameIndex(idx);
        rows_for_frame = sum(T.FrameIndex == frame);
        if statuses(idx) == "ok"
            if rows_for_frame ~= manifest.DetailRowCount(idx)
                error('validate_blob_detail_chunk:detailRowCountMismatch', ...
                    'Frame %d has %d rows but manifest records %d.', ...
                    frame, rows_for_frame, manifest.DetailRowCount(idx));
            end
        else
            if manifest.DetailRowCount(idx) ~= 0 || rows_for_frame ~= 0
                error('validate_blob_detail_chunk:failedFrameHasRows', ...
                    'Failed frame %d must have zero blob rows.', frame);
            end
        end
    end
end
