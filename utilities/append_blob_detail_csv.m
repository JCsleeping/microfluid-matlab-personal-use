function append_blob_detail_csv(csv_path, frame_index, frame_time, blob_table)
% APPEND_BLOB_DETAIL_CSV  Append one frame of per-blob detail to a cumulative CSV.

    if nargin < 4 || isempty(blob_table) || height(blob_table) == 0
        return;
    end

    frame_table = addvars(blob_table, ...
        repmat(frame_index, height(blob_table), 1), ...
        repmat(frame_time, height(blob_table), 1), ...
        'Before', 1, ...
        'NewVariableNames', {'FrameIndex', 'FrameTime'});

    if exist(csv_path, 'file') == 2
        writetable(frame_table, csv_path, 'WriteMode', 'append', 'WriteVariableNames', false);
    else
        writetable(frame_table, csv_path);
    end
end
