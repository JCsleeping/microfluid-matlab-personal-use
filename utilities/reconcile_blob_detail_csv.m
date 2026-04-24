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

    frame_index = T.FrameIndex;
    if ~isnumeric(frame_index)
        error('reconcile_blob_detail_csv:invalidFrameIndex', ...
            ['Blob detail CSV %s contains invalid FrameIndex values. ' ...
             'FrameIndex must contain finite positive integers.'], ...
            csv_path);
    end

    historical_rows = ~(frame_index > checkpoint_last_frame);
    T_history = T(historical_rows, :);
    historical_frame_index = frame_index(historical_rows);
    if any(~isfinite(historical_frame_index)) || ...
            any(historical_frame_index < 1) || ...
            any(historical_frame_index ~= fix(historical_frame_index))
        error('reconcile_blob_detail_csv:invalidFrameIndex', ...
            ['Blob detail CSV %s contains invalid historical FrameIndex values. ' ...
             'Historical FrameIndex values must contain finite positive integers.'], ...
            csv_path);
    end

    actual_rows = height(T_history);
    if actual_rows ~= expected_rows
        error('reconcile_blob_detail_csv:rowCountMismatch', ...
            ['Blob detail CSV %s has %d historical rows through frame %d, ' ...
             'but checkpoint nblobs_arr expects %d.'], ...
            csv_path, actual_rows, checkpoint_last_frame, expected_rows);
    end

    if checkpoint_last_frame > 0
        expected_counts = nblobs_arr(1:checkpoint_last_frame);
        actual_counts = accumarray(historical_frame_index, 1, ...
            [checkpoint_last_frame, 1], @sum, 0);
        mismatch_frame = find(actual_counts ~= expected_counts(:), 1, 'first');
        if ~isempty(mismatch_frame)
            error('reconcile_blob_detail_csv:perFrameCountMismatch', ...
                ['Blob detail CSV %s has %d rows for historical frame %d, ' ...
                 'but checkpoint nblobs_arr expects %d.'], ...
                csv_path, actual_counts(mismatch_frame), mismatch_frame, ...
                expected_counts(mismatch_frame));
        end
    end

    if any(~historical_rows)
        writetable(T_history, csv_path);
    end
end
