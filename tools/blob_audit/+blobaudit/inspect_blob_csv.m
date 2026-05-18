function info = inspect_blob_csv(inventory, opts)
% INSPECT_BLOB_CSV  Inspect blob_detail_all_frames.csv with large-file guard.

    csv_rows = strcmp(inventory.file_type, 'blob_csv');
    paths = inventory.path(csv_rows);
    info = struct('csv_integrity', empty_csv_table(), 'read_ok', false, ...
        'table', table(), 'profile_mode', 'none');
    if isempty(paths)
        return;
    end
    csv_path = paths{1};
    d = dir(csv_path);
    csv_bytes = d.bytes;
    mode = 'full_read';
    read_ok = false;
    T = table();
    err = '';
    full_unknown = false;
    n_profiled = 0;
    n_total_known = NaN;

    try
        if csv_bytes <= opts.MaxCsvBytesForFullRead
            T = readtable(csv_path, 'VariableNamingRule', 'preserve');
            n_profiled = height(T);
            n_total_known = height(T);
            read_ok = true;
        else
            full_unknown = true;
            try
                ds = tabularTextDatastore(csv_path, 'ReadSize', max(1, opts.MaxCsvRowsForProfiling));
                T = read(ds);
                if height(T) > opts.MaxCsvRowsForProfiling
                    T = T(1:opts.MaxCsvRowsForProfiling, :);
                end
                mode = 'sampled_large_csv';
                n_profiled = height(T);
                read_ok = true;
            catch ME_ds
                opts_import = detectImportOptions(csv_path);
                names = opts_import.VariableNames;
                T = cell2table(cell(0, numel(names)), 'VariableNames', names);
                mode = 'header_only';
                err = ME_ds.message;
                read_ok = true;
            end
        end
    catch ME
        err = ME.message;
        mode = 'unreadable';
    end

    row = build_csv_row(csv_path, csv_bytes, mode, read_ok, T, n_profiled, n_total_known, full_unknown, err);
    info.csv_integrity = row;
    info.read_ok = read_ok;
    info.table = T;
    info.profile_mode = mode;
end


function row = build_csv_row(path, bytes, mode, read_ok, T, n_profiled, n_total_known, full_unknown, err)
    vars = {};
    if istable(T)
        vars = T.Properties.VariableNames;
    end
    has_frame = any(strcmp(vars, 'FrameIndex'));
    has_time = any(strcmp(vars, 'FrameTime'));
    has_blob = any(strcmp(vars, 'BlobID'));
    has_area = any(strcmp(vars, 'Area'));
    has_perimeter = any(strcmp(vars, 'Perimeter'));
    min_frame = NaN;
    max_frame = NaN;
    if has_frame && height(T) > 0
        min_frame = min(T.FrameIndex);
        max_frame = max(T.FrameIndex);
    end
    schema_ok = has_frame && has_blob && has_area && has_perimeter;
    csv_path = {path};
    csv_exists = true;
    csv_read_mode = {mode};
    csv_read_ok = read_ok;
    csv_bytes = bytes;
    n_rows_profiled = n_profiled;
    n_total_rows_known = n_total_known;
    has_frame_index = has_frame;
    has_frame_time = has_time;
    has_blob_id = has_blob;
    has_area_col = has_area;
    has_perimeter_col = has_perimeter;
    min_frame_profiled = min_frame;
    max_frame_profiled = max_frame;
    schema_ok_for_level_a = schema_ok;
    full_frame_coverage_unknown = full_unknown;
    error_message = {err};
    row = table(csv_path, csv_exists, csv_read_mode, csv_read_ok, csv_bytes, ...
        n_rows_profiled, n_total_rows_known, has_frame_index, has_frame_time, ...
        has_blob_id, has_area_col, has_perimeter_col, min_frame_profiled, ...
        max_frame_profiled, schema_ok_for_level_a, full_frame_coverage_unknown, ...
        error_message, ...
        'VariableNames', {'csv_path', 'csv_exists', 'csv_read_mode', 'csv_read_ok', ...
        'csv_bytes', 'n_rows_profiled', 'n_total_rows_known', 'has_frame_index', ...
        'has_frame_time', 'has_blob_id', 'has_area', 'has_perimeter', ...
        'min_frame_profiled', 'max_frame_profiled', 'schema_ok_for_level_a', ...
        'full_frame_coverage_unknown', 'error_message'});
end


function T = empty_csv_table()
    T = build_csv_row('', NaN, 'none', false, table(), 0, NaN, false, '');
    T(1, :) = [];
end
