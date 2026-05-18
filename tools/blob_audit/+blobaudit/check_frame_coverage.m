function info = check_frame_coverage(audit, schema_source)
% CHECK_FRAME_COVERAGE  Compare observed blob rows to manifest and nblobs.

    manifest = table();
    T = schema_source.table;
    coverage_unknown = false;
    if strcmp(schema_source.type, 'chunks')
        manifest = schema_source.manifest;
    elseif strcmp(schema_source.type, 'csv') && ~isempty(T) && any(strcmp(T.Properties.VariableNames, 'FrameIndex'))
        if isfield(audit, 'csv_info') && isfield(audit.csv_info, 'csv_integrity') && ...
                height(audit.csv_info.csv_integrity) > 0 && ...
                audit.csv_info.csv_integrity.full_frame_coverage_unknown(1)
            coverage_unknown = true;
        end
        frames = unique(T.FrameIndex);
        counts = zeros(numel(frames), 1);
        times = nan(numel(frames), 1);
        for idx = 1:numel(frames)
            counts(idx) = sum(T.FrameIndex == frames(idx));
            if any(strcmp(T.Properties.VariableNames, 'FrameTime'))
                times(idx) = T.FrameTime(find(T.FrameIndex == frames(idx), 1));
            end
        end
        status = repmat({'ok'}, numel(frames), 1);
        errors = repmat({''}, numel(frames), 1); %#ok<NASGU>
        manifest = table(frames(:), times(:), status, counts(:), ...
            'VariableNames', {'FrameIndex', 'FrameTime', 'FrameStatus', 'DetailRowCount'});
    end

    if isempty(manifest) || height(manifest) == 0
        info = struct('frame_coverage', empty_frame_table(), 'has_fatal_coverage_error', false);
        return;
    end

    frames = unique(manifest.FrameIndex);
    if isfield(audit.results_info, 'last_completed_frame') && isfinite(audit.results_info.last_completed_frame)
        expected = (1:audit.results_info.last_completed_frame).';
    else
        expected = (min(frames):max(frames)).';
    end
    all_frames = unique([expected; frames(:)]);
    rows = cell(numel(all_frames), 11);
    fatal = false;

    for idx = 1:numel(all_frames)
        frame = all_frames(idx);
        m_idx = find(manifest.FrameIndex == frame);
        manifest_present = ~isempty(m_idx);
        blob_count = count_blob_rows(T, frame);
        frame_time = NaN;
        status = 'missing';
        expected_n = NaN;
        row_manifest = 'unknown';
        row_nblobs = 'unknown';
        notes = '';
        if manifest_present
            first = m_idx(1);
            if any(strcmp(manifest.Properties.VariableNames, 'FrameTime'))
                frame_time = manifest.FrameTime(first);
            end
            status = manifest.FrameStatus{first};
            if strcmp(status, 'failed')
                row_manifest = bool_text(blob_count == 0 && manifest.DetailRowCount(first) == 0);
                row_nblobs = 'not_applicable_failed_frame';
            else
                row_manifest = bool_text(blob_count == manifest.DetailRowCount(first));
            end
        end
        if isfield(audit.results_info, 'has_nblobs_arr') && audit.results_info.has_nblobs_arr && frame <= numel(audit.results_info.nblobs_arr)
            expected_n = audit.results_info.nblobs_arr(frame);
            if ~strcmp(status, 'failed')
                row_nblobs = bool_text(blob_count == expected_n);
            end
        end
        has_core_nans = has_core_field_nans(T, frame);
        has_negative_area = has_negative(T, frame, 'Area');
        has_negative_perimeter = has_negative(T, frame, 'Perimeter');
        if manifest_present && ~strcmp(row_manifest, 'true')
            fatal = true;
            notes = 'row count mismatch';
        elseif ~manifest_present && ismember(frame, expected) && ~coverage_unknown
            fatal = true;
            notes = 'expected frame missing';
        elseif ~manifest_present && ismember(frame, expected) && coverage_unknown
            notes = 'coverage unknown due to sampled/header-only CSV profile';
        end
        rows(idx, :) = {frame, frame_time, manifest_present, blob_count > 0, blob_count, ...
            expected_n, status, row_manifest, row_nblobs, has_core_nans, ...
            sprintf('%s%s%s', notes, flag_note(has_negative_area, ' negative Area'), ...
            flag_note(has_negative_perimeter, ' negative Perimeter'))};
    end

    FrameIndex = cell2mat(rows(:, 1));
    FrameTime = cell2mat(rows(:, 2));
    ManifestPresent = cell2mat(rows(:, 3));
    CsvRowsPresent = cell2mat(rows(:, 4));
    BlobRowCount = cell2mat(rows(:, 5));
    ExpectedNBlobs = cell2mat(rows(:, 6));
    FrameStatus = rows(:, 7);
    RowCountMatchesManifest = rows(:, 8);
    RowCountMatchesNBlobs = rows(:, 9);
    HasCoreFieldNaNs = cell2mat(rows(:, 10));
    Notes = rows(:, 11);
    frame_coverage = table(FrameIndex, FrameTime, ManifestPresent, CsvRowsPresent, ...
        BlobRowCount, ExpectedNBlobs, FrameStatus, RowCountMatchesManifest, ...
        RowCountMatchesNBlobs, HasCoreFieldNaNs, Notes);
    info = struct('frame_coverage', frame_coverage, 'has_fatal_coverage_error', fatal);
end


function n = count_blob_rows(T, frame)
    if isempty(T) || ~istable(T) || ~any(strcmp(T.Properties.VariableNames, 'FrameIndex'))
        n = 0;
    else
        n = sum(T.FrameIndex == frame);
    end
end


function value = bool_text(tf)
    if tf
        value = 'true';
    else
        value = 'false';
    end
end


function tf = has_core_field_nans(T, frame)
    tf = false;
    vars = {'Area', 'Perimeter'};
    if isempty(T) || ~istable(T) || ~any(strcmp(T.Properties.VariableNames, 'FrameIndex'))
        return;
    end
    mask = T.FrameIndex == frame;
    for idx = 1:numel(vars)
        if any(strcmp(T.Properties.VariableNames, vars{idx}))
            values = T.(vars{idx})(mask);
            tf = tf || any(isnan(values));
        end
    end
end


function tf = has_negative(T, frame, varname)
    tf = false;
    if isempty(T) || ~istable(T) || ~any(strcmp(T.Properties.VariableNames, 'FrameIndex')) || ...
            ~any(strcmp(T.Properties.VariableNames, varname))
        return;
    end
    values = T.(varname)(T.FrameIndex == frame);
    tf = any(values < 0);
end


function txt = flag_note(tf, label)
    if tf
        txt = label;
    else
        txt = '';
    end
end


function T = empty_frame_table()
    T = table(zeros(0,1), zeros(0,1), false(0,1), false(0,1), zeros(0,1), ...
        zeros(0,1), cell(0,1), cell(0,1), cell(0,1), false(0,1), cell(0,1), ...
        'VariableNames', {'FrameIndex', 'FrameTime', 'ManifestPresent', ...
        'CsvRowsPresent', 'BlobRowCount', 'ExpectedNBlobs', 'FrameStatus', ...
        'RowCountMatchesManifest', 'RowCountMatchesNBlobs', 'HasCoreFieldNaNs', 'Notes'});
end
