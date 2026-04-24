function reconcile_blob_detail_csv(csv_path, nblobs_arr, checkpoint_last_frame)
% RECONCILE_BLOB_DETAIL_CSV  Validate/truncate blob detail CSV on checkpoint resume.

    checkpoint_last_frame = max(0, min(checkpoint_last_frame, numel(nblobs_arr)));
    expected_rows = sum(nblobs_arr(1:checkpoint_last_frame));

    if exist(csv_path, 'file') ~= 2
        if expected_rows > 0
            error('reconcile_blob_detail_csv:missingHistoricalCsv', ...
                ['Missing blob detail CSV %s, but checkpoint history expects %d ' ...
                 'per-blob rows through frame %d.'], ...
                csv_path, expected_rows, checkpoint_last_frame);
        end
        return;
    end

    T = readtable(csv_path, 'VariableNamingRule', 'preserve');
    if ~ismember('FrameIndex', T.Properties.VariableNames)
        error('reconcile_blob_detail_csv:missingFrameIndex', ...
            'Blob detail CSV %s does not contain required FrameIndex column.', csv_path);
    end

    historical_rows = T.FrameIndex <= checkpoint_last_frame;
    T_history = T(historical_rows, :);
    actual_rows = height(T_history);
    if actual_rows ~= expected_rows
        error('reconcile_blob_detail_csv:rowCountMismatch', ...
            ['Blob detail CSV %s has %d historical rows through frame %d, ' ...
             'but checkpoint nblobs_arr expects %d.'], ...
            csv_path, actual_rows, checkpoint_last_frame, expected_rows);
    end

    if any(~historical_rows)
        writetable(T_history, csv_path);
    end
end
