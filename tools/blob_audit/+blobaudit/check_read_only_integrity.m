function T = check_read_only_integrity(before_state, after_state)
% CHECK_READ_ONLY_INTEGRITY  Compare before/after state for source files.

    n = height(before_state);
    path = before_state.path;
    bytes_before = before_state.bytes;
    bytes_after = nan(n, 1);
    modified_time_before = before_state.modified_time;
    modified_time_after = cell(n, 1);
    modified = false(n, 1);
    notes = cell(n, 1);

    for idx = 1:n
        match = find(strcmp(after_state.path, path{idx}), 1);
        if isempty(match)
            bytes_after(idx) = NaN;
            modified_time_after{idx} = '';
            modified(idx) = true;
            notes{idx} = 'file missing from after snapshot';
        else
            bytes_after(idx) = after_state.bytes(match);
            modified_time_after{idx} = after_state.modified_time{match};
            modified(idx) = ~isequaln(bytes_before(idx), bytes_after(idx)) || ...
                ~strcmp(modified_time_before{idx}, modified_time_after{idx});
            if modified(idx)
                notes{idx} = 'bytes or modified_time changed';
            else
                notes{idx} = '';
            end
        end
    end

    T = table(path, bytes_before, bytes_after, modified_time_before, ...
        modified_time_after, modified, notes, ...
        'VariableNames', {'path', 'bytes_before', 'bytes_after', ...
        'modified_time_before', 'modified_time_after', 'modified', 'notes'});
end
