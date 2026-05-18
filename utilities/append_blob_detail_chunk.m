function writer = append_blob_detail_chunk(writer, frame_index, frame_time, blob_table, frame_status, error_message)
% APPEND_BLOB_DETAIL_CHUNK  Buffer one frame of per-blob detail.

    if nargin < 5 || isempty(frame_status)
        frame_status = "ok";
    end
    if nargin < 6
        error_message = "";
    end

    tic_push = tic;
    frame_index = double(frame_index);
    if ~isscalar(frame_index) || ~isfinite(frame_index) || frame_index < 1 || frame_index ~= fix(frame_index)
        error('append_blob_detail_chunk:invalidFrameIndex', ...
            'FrameIndex must be a finite positive integer.');
    end
    if frame_index <= writer.last_written_frame
        error('append_blob_detail_chunk:nonIncreasingFrameIndex', ...
            'FrameIndex %d is not greater than last written frame %d.', ...
            frame_index, writer.last_written_frame);
    end

    frame_status = lower(string(frame_status));
    if ~(frame_status == "ok" || frame_status == "failed")
        error('append_blob_detail_chunk:invalidFrameStatus', ...
            'FrameStatus must be ''ok'' or ''failed''.');
    end

    error_message = sanitize_blob_detail_error_message(error_message);
    if frame_status == "failed"
        normalized_table = make_empty_blob_detail_table(writer.schema);
    else
        normalized_table = normalize_blob_detail_table(blob_table, frame_index, frame_time, writer.schema);
    end

    detail_row_count = height(normalized_table);
    if frame_status == "failed" && detail_row_count ~= 0
        error('append_blob_detail_chunk:failedFrameHasRows', ...
            'Failed frames must not contain blob detail rows.');
    end

    manifest_template = make_empty_blob_detail_manifest();
    manifest_row = table(frame_index, double(frame_time), frame_status, ...
        double(detail_row_count), error_message, ...
        'VariableNames', manifest_template.Properties.VariableNames);

    writer.buffer_frame_count = writer.buffer_frame_count + 1;
    writer.buffer_manifest_rows{writer.buffer_frame_count, 1} = manifest_row;
    writer.buffer_tables{writer.buffer_frame_count, 1} = normalized_table;
    if writer.buffer_frame_count == 1
        writer.buffer_frame_start = frame_index;
    end
    writer.buffer_frame_end = frame_index;
    writer.last_written_frame = frame_index;
    writer.buffer_push_time_sec = writer.buffer_push_time_sec + toc(tic_push);
end


function message = sanitize_blob_detail_error_message(message)
    message = string(message);
    if numel(message) == 0
        message = "";
    else
        message = message(1);
    end
    message = replace(message, sprintf('\r'), ' ');
    message = replace(message, sprintf('\n'), ' ');
    if strlength(message) > 500
        message = extractBefore(message, 501);
    end
end
