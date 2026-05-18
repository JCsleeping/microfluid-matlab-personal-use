function chunk_files = list_blob_detail_chunk_files(chunks_dir)
% LIST_BLOB_DETAIL_CHUNK_FILES  Return validated chunk paths sorted by metadata.

    if ~isfolder(chunks_dir)
        chunk_files = struct('path', {}, 'frame_start', {}, 'frame_end', {});
        return;
    end

    files = dir(fullfile(chunks_dir, 'blob_detail_*.mat'));
    files = files(~contains({files.name}, '.tmp.'));
    chunk_files = struct('path', {}, 'frame_start', {}, 'frame_end', {});

    for idx = 1:numel(files)
        path = fullfile(files(idx).folder, files(idx).name);
        data = load(path, 'chunk');
        if ~isfield(data, 'chunk')
            error('list_blob_detail_chunk_files:missingChunk', ...
                'Chunk file %s does not contain variable chunk.', path);
        end
        chunk_files(end + 1).path = path; %#ok<AGROW>
        chunk_files(end).frame_start = data.chunk.frame_start;
        chunk_files(end).frame_end = data.chunk.frame_end;
    end

    if isempty(chunk_files)
        return;
    end

    [~, order] = sort([chunk_files.frame_start]);
    chunk_files = chunk_files(order);
end

