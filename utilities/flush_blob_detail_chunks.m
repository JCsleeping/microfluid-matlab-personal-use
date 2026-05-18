function [writer, flushed_paths] = flush_blob_detail_chunks(writer)
% FLUSH_BLOB_DETAIL_CHUNKS  Atomically write the buffered frames to MAT.

    flushed_paths = {};
    if ~isfield(writer, 'buffer_frame_count') || writer.buffer_frame_count == 0
        return;
    end

    tic_flush = tic;
    frame_manifest = vertcat(writer.buffer_manifest_rows{:});
    nonempty_tables = cellfun(@(T) height(T) > 0, writer.buffer_tables);
    if any(nonempty_tables)
        blob_detail_table = vertcat(writer.buffer_tables{nonempty_tables});
    else
        blob_detail_table = make_empty_blob_detail_table(writer.schema);
    end

    chunk = struct();
    chunk.version = 1;
    chunk.frame_manifest = frame_manifest;
    chunk.blob_detail_table = blob_detail_table;
    chunk.schema_variable_names = writer.schema.variable_names;
    chunk.created_at = datestr(now, 30);
    chunk.frame_start = writer.buffer_frame_start;
    chunk.frame_end = writer.buffer_frame_end;

    final_path = fullfile(writer.chunks_dir, sprintf( ...
        'blob_detail_%06d_%06d.mat', chunk.frame_start, chunk.frame_end));
    tmp_path = make_chunk_temp_path(writer.chunks_dir, chunk.frame_start, chunk.frame_end);

    if exist(tmp_path, 'file') == 2
        delete(tmp_path);
    end

    save_args = save_args_for_blob_detail_format(writer.save_format);
    check_v7_chunk_size_guard(chunk, writer);
    try
        save(tmp_path, 'chunk', save_args{:});
    catch ME
        cleanup_file_if_present(tmp_path);
        rethrow(ME);
    end
    validate_blob_detail_chunk(tmp_path, writer.schema);
    atomic_replace_file(tmp_path, final_path, ...
        @(path) validate_blob_detail_chunk(path, writer.schema));

    writer.buffer_manifest_rows = {};
    writer.buffer_tables = {};
    writer.buffer_frame_count = 0;
    writer.buffer_frame_start = NaN;
    writer.buffer_frame_end = NaN;
    writer.chunk_flush_time_sec = writer.chunk_flush_time_sec + toc(tic_flush);
    flushed_paths = {final_path};
end


function check_v7_chunk_size_guard(chunk, writer)
    if ~strcmp(char(string(writer.save_format)), 'v7')
        return;
    end

    chunk_info = whos('chunk');
    warn_limit = 512 * 1024^2;
    if isfield(writer, 'chunk_warn_bytes') && ~isempty(writer.chunk_warn_bytes)
        warn_limit = writer.chunk_warn_bytes;
    end
    hard_limit = 1.5 * 1024^3;
    if isfield(writer, 'v7_hard_max_bytes') && ~isempty(writer.v7_hard_max_bytes)
        hard_limit = writer.v7_hard_max_bytes;
    end

    if chunk_info.bytes > hard_limit
        error('flush_blob_detail_chunks:v7ChunkTooLarge', ...
            ['Blob detail chunk is %.3g bytes, which exceeds the robust v7 ' ...
             'limit %.3g bytes. Reduce output.blob_detail_chunk_size or use ' ...
             'an ASCII-only v7.3 chunk directory.'], ...
            chunk_info.bytes, hard_limit);
    end
    if chunk_info.bytes > warn_limit
        warning('flush_blob_detail_chunks:v7ChunkLarge', ...
            ['Blob detail chunk is %.3g bytes. This is still below the hard ' ...
             'v7 guard, but consider reducing output.blob_detail_chunk_size.'], ...
            chunk_info.bytes);
    end
end


function cleanup_file_if_present(path)
    if exist(path, 'file') == 2
        delete(path);
    end
end


function tmp_path = make_chunk_temp_path(chunks_dir, frame_start, frame_end)
    tmp_path = fullfile(chunks_dir, sprintf( ...
        'blob_detail_%06d_%06d_%s.tmp.mat', ...
        frame_start, frame_end, datestr(now, 'yyyymmdd_HHMMSSFFF')));
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
            error('flush_blob_detail_chunks:invalidSaveFormat', ...
                'Unsupported blob detail save format: %s.', char(string(save_format)));
    end
end
