function export_blob_detail_chunks_csv(chunks_dir, csv_path, expected_schema)
% EXPORT_BLOB_DETAIL_CHUNKS_CSV  Stream MAT chunks into final CSV artifact.

    if nargin < 3 || isempty(expected_schema)
        expected_schema = get_blob_detail_legacy_schema();
    end

    chunk_files = list_blob_detail_chunk_files(chunks_dir);
    tmp_csv = fullfile(fileparts(csv_path), 'blob_detail_all_frames.tmp.csv');
    if exist(tmp_csv, 'file') == 2
        delete(tmp_csv);
    end

    first_write = true;
    for idx = 1:numel(chunk_files)
        chunk = validate_blob_detail_chunk(chunk_files(idx).path, expected_schema);
        T = chunk.blob_detail_table;
        if isempty(T) || height(T) == 0
            continue;
        end
        if first_write
            writetable(T, tmp_csv);
            first_write = false;
        else
            writetable(T, tmp_csv, 'WriteMode', 'append', 'WriteVariableNames', false);
        end
    end

    if first_write
        writetable(make_empty_blob_detail_table(expected_schema), tmp_csv);
    end
    atomic_replace_file(tmp_csv, csv_path, @(path) readtable(path, ...
        'VariableNamingRule', 'preserve'));
end
