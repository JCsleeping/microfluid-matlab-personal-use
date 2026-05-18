function writer = init_blob_detail_chunk_writer(output_path, chunk_size, save_format, mode, expected_schema, last_verified_frame, allow_format_fallback, chunk_warn_bytes)
% INIT_BLOB_DETAIL_CHUNK_WRITER  Initialize MAT chunk writer state.

    if nargin < 5 || isempty(expected_schema)
        expected_schema = get_blob_detail_legacy_schema();
    end
    if nargin < 6 || isempty(last_verified_frame)
        last_verified_frame = 0;
    end
    if nargin < 7 || isempty(allow_format_fallback)
        allow_format_fallback = true;
    end
    if nargin < 8 || isempty(chunk_warn_bytes)
        chunk_warn_bytes = 512 * 1024^2;
    end

    mode = lower(char(string(mode)));
    if ~ismember(mode, {'fresh', 'resume'})
        error('init_blob_detail_chunk_writer:invalidMode', ...
            'mode must be ''fresh'' or ''resume''.');
    end

    if ~isfolder(output_path)
        mkdir(output_path);
    end

    chunks_dir = fullfile(output_path, 'blob_detail_chunks');
    csv_path = fullfile(output_path, 'blob_detail_all_frames.csv');

    if strcmp(mode, 'fresh')
        archive_existing_blob_detail_outputs(output_path, chunks_dir, csv_path);
        if ~isfolder(chunks_dir)
            mkdir(chunks_dir);
        end
    elseif ~isfolder(chunks_dir)
        mkdir(chunks_dir);
    end

    requested_save_format = char(string(save_format));
    [selected_save_format, format_probe] = select_blob_detail_save_format( ...
        chunks_dir, requested_save_format, allow_format_fallback, expected_schema);

    writer = struct();
    writer.output_path = output_path;
    writer.chunks_dir = chunks_dir;
    writer.csv_path = csv_path;
    writer.chunk_size = chunk_size;
    writer.requested_save_format = requested_save_format;
    writer.save_format = selected_save_format;
    writer.allow_format_fallback = logical(allow_format_fallback);
    writer.chunk_warn_bytes = double(chunk_warn_bytes);
    writer.v7_hard_max_bytes = 1.5 * 1024^3;
    writer.chunks_dir_has_non_ascii = contains_non_ascii_path(chunks_dir);
    writer.format_probe = format_probe;
    writer.matlab_version = version;
    writer.hdf5_version = hdf5_library_version();
    writer.schema = expected_schema;
    writer.last_written_frame = double(last_verified_frame);
    writer.buffer_manifest_rows = {};
    writer.buffer_tables = {};
    writer.buffer_frame_count = 0;
    writer.buffer_frame_start = NaN;
    writer.buffer_frame_end = NaN;
    writer.buffer_push_time_sec = 0;
    writer.chunk_flush_time_sec = 0;
    writer.csv_merge_time_sec = 0;
end


function [selected_format, probe] = select_blob_detail_save_format(chunks_dir, requested_format, allow_fallback, schema)
    requested_format = char(string(requested_format));
    has_non_ascii_path = contains_non_ascii_path(chunks_dir);
    probe = struct('requested', requested_format, 'selected', requested_format, ...
        'fallback_used', false, 'message', '', 'chunks_dir_has_non_ascii', has_non_ascii_path);

    if startsWith(requested_format, 'v7.3') && has_non_ascii_path
        message = ['Requested blob-detail MAT format is HDF5-based and the chunk ' ...
            'directory contains non-ASCII characters. Using v7 avoids known Windows ' ...
            'HDF5 filename issues.'];
        if allow_fallback
            probe = probe_format_or_error(chunks_dir, 'v7', schema, probe, message, true);
            selected_format = 'v7';
            return;
        end
        error('init_blob_detail_chunk_writer:nonAsciiV73Path', message);
    end

    try
        probe_format(chunks_dir, requested_format, schema);
        selected_format = requested_format;
        probe.selected = selected_format;
        probe.message = 'requested_format_probe_ok';
    catch requested_error
        if ~(allow_fallback && ~strcmp(requested_format, 'v7'))
            error('init_blob_detail_chunk_writer:saveFormatProbeFailed', ...
                'Blob-detail MAT save/load probe failed for format "%s": %s', ...
                requested_format, requested_error.message);
        end
        message = sprintf('Requested format "%s" failed probe: %s', ...
            requested_format, requested_error.message);
        probe = probe_format_or_error(chunks_dir, 'v7', schema, probe, message, true);
        selected_format = 'v7';
    end
end


function probe = probe_format_or_error(chunks_dir, format, schema, probe, message, fallback_used)
    try
        probe_format(chunks_dir, format, schema);
    catch fallback_error
        error('init_blob_detail_chunk_writer:saveFormatProbeFailed', ...
            'Blob-detail MAT save/load probe failed for fallback format "%s": %s', ...
            format, fallback_error.message);
    end

    probe.selected = format;
    probe.fallback_used = logical(fallback_used);
    probe.message = message;
    warning('init_blob_detail_chunk_writer:saveFormatFallback', '%s Selected format: %s.', ...
        message, format);
end


function probe_format(chunks_dir, save_format, schema)
    chunk = make_probe_chunk(schema);
    probe_path = fullfile(chunks_dir, sprintf('blob_detail_save_probe_%s.mat', ...
        datestr(now, 'yyyymmdd_HHMMSSFFF')));
    cleanup = onCleanup(@() cleanup_file_if_present(probe_path)); %#ok<NASGU>
    save_args = save_args_for_blob_detail_format(save_format);
    save(probe_path, 'chunk', save_args{:});
    validate_blob_detail_chunk(probe_path, schema);
end


function chunk = make_probe_chunk(schema)
    manifest_template = make_empty_blob_detail_manifest();
    frame_index = 1;
    frame_time = 0;
    frame_status = "ok";
    detail_row_count = 0;
    error_message = "";

    chunk = struct();
    chunk.version = 1;
    chunk.frame_start = 1;
    chunk.frame_end = 1;
    chunk.frame_manifest = table(frame_index, frame_time, frame_status, ...
        detail_row_count, error_message, ...
        'VariableNames', manifest_template.Properties.VariableNames);
    chunk.blob_detail_table = make_empty_blob_detail_table(schema);
    chunk.schema_variable_names = schema.variable_names;
    chunk.created_at = datestr(now, 30);
end


function args = save_args_for_blob_detail_format(save_format)
    switch char(string(save_format))
        case 'v7'
            args = {'-v7'};
        case 'v7.3'
            args = {'-v7.3'};
        case 'v7.3-nocompression'
            args = {'-v7.3', '-nocompression'};
        otherwise
            error('init_blob_detail_chunk_writer:invalidSaveFormat', ...
                'Unsupported blob detail save format: %s.', char(string(save_format)));
    end
end


function tf = contains_non_ascii_path(path)
    path_chars = char(string(path));
    tf = any(double(path_chars) > 127);
end


function version_text = hdf5_library_version()
    try
        [major, minor, relnum] = H5.get_libversion();
        version_text = sprintf('%d.%d.%d', major, minor, relnum);
    catch
        version_text = 'unavailable';
    end
end


function cleanup_file_if_present(path)
    if exist(path, 'file') == 2
        delete(path);
    end
end


function archive_existing_blob_detail_outputs(output_path, chunks_dir, csv_path)
    timestamp = datestr(now, 'yyyymmdd_HHMMSSFFF');

    if isfolder(chunks_dir)
        archive_dir = fullfile(output_path, ['blob_detail_chunks_archived_' timestamp]);
        movefile(chunks_dir, archive_dir);
    end

    if exist(csv_path, 'file') == 2
        archive_csv = fullfile(output_path, ['blob_detail_all_frames.archived_' timestamp '.csv']);
        movefile(csv_path, archive_csv);
    end
end
