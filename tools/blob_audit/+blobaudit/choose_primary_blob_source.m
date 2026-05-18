function [primary, decisions] = choose_primary_blob_source(inventory)
% CHOOSE_PRIMARY_BLOB_SOURCE  Select blob source using fixed priority.

    primary = struct('type', 'none', 'path', '', 'trust_level', 'none');
    rows = {};

    chunk_rows = strcmp(inventory.file_type, 'blob_chunk_mat');
    csv_rows = strcmp(inventory.file_type, 'blob_csv');
    result_rows = strcmp(inventory.file_type, 'results_mat');
    has_chunks = any(chunk_rows);
    has_csv = any(csv_rows);
    has_results = any(result_rows);

    if has_chunks
        primary.type = 'chunks';
        primary.path = first_path(inventory, chunk_rows);
        primary.trust_level = 'high_pending_integrity';
    elseif has_csv
        primary.type = 'csv';
        primary.path = first_path(inventory, csv_rows);
        primary.trust_level = 'medium_legacy';
    elseif has_results
        primary.type = 'results_mat_only';
        primary.path = first_path(inventory, result_rows);
        primary.trust_level = 'low_reconstructability_only';
    end

    rows = add_row(rows, 1, 'chunks', path_list(inventory, chunk_rows), strcmp(primary.type, 'chunks'), ...
        trust_for('chunks', primary), reason_for('chunks', has_chunks, primary), '');
    rows = add_row(rows, 2, 'csv', path_list(inventory, csv_rows), strcmp(primary.type, 'csv'), ...
        trust_for('csv', primary), reason_for('csv', has_csv, primary), '');
    rows = add_row(rows, 3, 'results_mat', path_list(inventory, result_rows), strcmp(primary.type, 'results_mat_only'), ...
        trust_for('results_mat_only', primary), reason_for('results_mat', has_results, primary), '');

    source_rank = cell2mat(rows(:, 1));
    source_type = rows(:, 2);
    path = rows(:, 3);
    selected = cell2mat(rows(:, 4));
    trust_level = rows(:, 5);
    reason = rows(:, 6);
    notes = rows(:, 7);
    decisions = table(source_rank, source_type, path, selected, trust_level, reason, notes, ...
        'VariableNames', {'source_rank', 'source_type', 'path', 'selected', ...
        'trust_level', 'reason', 'notes'});
end


function rows = add_row(rows, rank, type, path, selected, trust, reason, notes)
    rows(end + 1, :) = {rank, type, path, selected, trust, reason, notes};
end


function p = first_path(inventory, mask)
    idx = find(mask, 1, 'first');
    if isempty(idx)
        p = '';
    else
        p = inventory.path{idx};
    end
end


function txt = path_list(inventory, mask)
    values = inventory.path(mask);
    if isempty(values)
        txt = '';
    else
        txt = strjoin(values(:).', '; ');
    end
end


function trust = trust_for(type, primary)
    if strcmp(primary.type, type)
        trust = primary.trust_level;
    elseif strcmp(type, 'csv') && strcmp(primary.type, 'chunks')
        trust = 'secondary_reference_only';
    else
        trust = 'not_selected';
    end
end


function reason = reason_for(type, exists_flag, primary)
    if strcmp(type, 'chunks')
        if exists_flag
            reason = 'chunks exist and are selected pending integrity audit';
        else
            reason = 'no chunk files found';
        end
    elseif strcmp(type, 'csv')
        if strcmp(primary.type, 'chunks') && exists_flag
            reason = 'ignored as primary because chunks exist';
        elseif exists_flag
            reason = 'CSV selected because chunks are absent';
        else
            reason = 'no blob_detail_all_frames.csv found';
        end
    else
        if exists_flag && any(strcmp(primary.type, {'chunks', 'csv'}))
            reason = 'used only for metadata because blob table source exists';
        elseif exists_flag
            reason = 'used for reconstructability only because blob table sources are absent';
        else
            reason = 'no results MAT found';
        end
    end
end
