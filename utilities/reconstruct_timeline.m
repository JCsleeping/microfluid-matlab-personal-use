function T = reconstruct_timeline(mat_path, output_dir)
% RECONSTRUCT_TIMELINE  Build real elapsed-time for each frame from TIF metadata.
%
%   T = reconstruct_timeline(mat_path)
%   T = reconstruct_timeline(mat_path, output_dir)
%
%   Reads the TIF directory referenced by a results_*.mat, orders files by
%   acquisition timestamp, parses capture intervals from filenames (for
%   example "1 second", "3 seconds", "3s", "10S"), and reconstructs a
%   real elapsed-time vector across frames.
%
%   Outputs (new files, never modifies originals):
%     timeseries_realtime_<ts>.csv  - corrected timeseries with RealTime_s
%     frame_timeline_<ts>.csv       - full frame-to-time mapping
%
%   Inputs:
%     mat_path   - Path to results_*.mat
%     output_dir - (optional) Output directory, default = same as mat_path
%
%   Example:
%     T = reconstruct_timeline('D:\...\results_xxx.mat');

    pipeline_root = 'D:\00 Claude Code\01 MATLAB CODE\01 Microfluid';
    addpath(genpath(pipeline_root));

    if nargin < 2 || isempty(output_dir)
        output_dir = fileparts(mat_path);
    end

    fprintf('==========================================================\n');
    fprintf('  Timeline Reconstruction\n');
    fprintf('==========================================================\n\n');

    %% 1. Load config
    fprintf('  Loading config...\n');
    try
        loaded = load(mat_path, 'config');
    catch
        tmp = [tempname '.mat'];
        copyfile(mat_path, tmp, 'f');
        loaded = load(tmp, 'config');
        delete(tmp);
    end
    if ~isfield(loaded, 'config')
        error('reconstruct_timeline:noConfig', 'MAT file does not contain config.');
    end
    config = loaded.config;

    % Get TIF directory: parent of the output folder
    [output_parent, ~, ~] = fileparts(mat_path);
    tif_dir = fileparts(output_parent);
    fprintf('  TIF directory: %s\n', tif_dir);

    %% 2. Scan and order TIF files
    fprintf('\n  Scanning TIF files in directory...\n');
    all_tifs = dir(fullfile(tif_dir, '*.tif'));
    all_tiffs = dir(fullfile(tif_dir, '*.tiff'));
    all_tifs = [all_tifs; all_tiffs];

    if isempty(all_tifs)
        error('reconstruct_timeline:noTifs', 'No TIF files found in %s', tif_dir);
    end

    all_tifs = sort_tifs_by_timestamp(all_tifs);

    n_files = numel(all_tifs);
    fprintf('  Found %d TIF files.\n', n_files);

    file_info = repmat(struct( ...
        'path', '', ...
        'basename', '', ...
        'dt', nan, ...
        'dt_source', '', ...
        'n_pages', 0, ...
        'datenum', nan, ...
        'bytes', 0), n_files, 1);

    for i = 1:n_files
        bname_full = all_tifs(i).name;
        [~, bname, ~] = fileparts(bname_full);

        info_f = imfinfo(fullfile(tif_dir, bname_full));
        [dt_i, dt_source] = parse_interval_from_name(bname);

        file_info(i).path = fullfile(tif_dir, bname_full);
        file_info(i).basename = bname_full;
        file_info(i).dt = dt_i;
        file_info(i).dt_source = dt_source;
        file_info(i).n_pages = numel(info_f);
        file_info(i).datenum = all_tifs(i).datenum;
        file_info(i).bytes = all_tifs(i).bytes;
    end

    file_info = infer_missing_intervals(file_info);

    for i = 1:n_files
        src = file_info(i).dt_source;
        src_note = '';
        if ~strcmp(src, 'filename')
            src_note = sprintf(' [%s]', src);
        end

        fprintf('    [%d/%d] %s  -> %d pages x %s s = %s s%s  (%.0f MB)\n', ...
            i, n_files, strip_extension(file_info(i).basename), file_info(i).n_pages, ...
            format_scalar(file_info(i).dt), ...
            format_scalar(file_info(i).n_pages * file_info(i).dt), ...
            src_note, file_info(i).bytes / 1e6);
    end

    %% 3. Detect gaps between files
    fprintf('\n  Detecting gaps...\n');
    gaps = zeros(max(n_files - 1, 0), 1);
    has_gap = false(max(n_files - 1, 0), 1);

    for i = 1:n_files - 1
        if ~isfinite(file_info(i).datenum) || ~isfinite(file_info(i + 1).datenum)
            continue;
        end

        recording_dur_next = file_info(i + 1).n_pages * file_info(i + 1).dt;
        start_next = file_info(i + 1).datenum - recording_dur_next / 86400;
        end_current = file_info(i).datenum;
        gap_seconds = (start_next - end_current) * 86400;
        threshold = 1.5 * file_info(i + 1).dt;

        if gap_seconds > threshold
            gaps(i) = gap_seconds;
            has_gap(i) = true;
            fprintf('    Gap after file %d: %.1f s  (~%.0f missing frames at %s s)\n', ...
                i, gap_seconds, gap_seconds / file_info(i).dt, format_scalar(file_info(i).dt));
        end
    end

    n_gaps = sum(has_gap);
    if n_gaps == 0
        fprintf('    No gaps detected - all files appear continuous.\n');
    else
        fprintf('    Detected %d gap(s), total %.1f s\n', n_gaps, sum(gaps));
    end

    %% 4. Build cumulative time array
    fprintf('\n  Building timeline...\n');
    total_frames = sum([file_info.n_pages]);
    t_real_all = zeros(total_frames, 1);
    frame_tif_idx = zeros(total_frames, 1);
    frame_page = zeros(total_frames, 1);
    frame_dt = zeros(total_frames, 1);

    t_offset = 0;
    frame_cursor = 0;

    for i = 1:n_files
        np = file_info(i).n_pages;
        dt_i = file_info(i).dt;

        for p = 1:np
            frame_cursor = frame_cursor + 1;
            t_real_all(frame_cursor) = t_offset + (p - 1) * dt_i;
            frame_tif_idx(frame_cursor) = i;
            frame_page(frame_cursor) = p;
            frame_dt(frame_cursor) = dt_i;
        end

        t_offset = t_offset + np * dt_i;
        if i < n_files && has_gap(i)
            t_offset = t_offset + gaps(i);
        end
    end

    if isempty(t_real_all)
        total_time = 0;
    else
        total_time = t_real_all(end);
    end
    fprintf('  Total frames: %d\n', total_frames);
    fprintf('  Total real time: %.1f s (%.1f min)\n', total_time, total_time / 60);

    %% 5. Apply config.pages filter
    if isfield(config, 'pages') && ~isempty(config.pages)
        valid = config.pages(config.pages >= 1 & config.pages <= total_frames);
        t_real = t_real_all(valid);
        tif_idx_filtered = frame_tif_idx(valid);
        page_filtered = frame_page(valid);
        dt_filtered = frame_dt(valid);
        fprintf('  After page filter: %d frames\n', numel(valid));
    else
        t_real = t_real_all;
        tif_idx_filtered = frame_tif_idx;
        page_filtered = frame_page;
        dt_filtered = frame_dt;
    end

    %% 6. Save frame_timeline CSV
    ts = datestr(now, 'yyyymmdd_HHMMSS');

    TifFile = cell(numel(t_real), 1);
    for k = 1:numel(t_real)
        TifFile{k} = file_info(tif_idx_filtered(k)).basename;
    end

    T = table( ...
        (1:numel(t_real))', ...
        t_real, ...
        TifFile, ...
        page_filtered, ...
        dt_filtered, ...
        'VariableNames', {'GlobalFrame', 'RealTime_s', 'TifFile', 'PageInTif', 'Interval_s'});

    timeline_csv = fullfile(output_dir, sprintf('frame_timeline_%s.csv', ts));
    writetable(T, timeline_csv);
    fprintf('\n  Saved: %s\n', timeline_csv);

    %% 7. Patch timeseries CSV
    ts_files = dir(fullfile(output_dir, 'timeseries_*.csv'));
    ts_files = ts_files(~contains({ts_files.name}, 'realtime'));

    if ~isempty(ts_files)
        [~, sidx] = sort({ts_files.name});
        ts_src = fullfile(output_dir, ts_files(sidx(end)).name);

        fprintf('  Patching: %s\n', ts_files(sidx(end)).name);
        ts_data = readtable(ts_src);

        n_rows = height(ts_data);
        n_times = numel(t_real);
        [real_time_series, interval_series] = align_realtime_columns(t_real, dt_filtered, n_rows);

        if n_rows ~= n_times
            if n_rows < n_times
                fprintf('  WARNING: timeseries has %d rows but timeline has %d frames. Using first %d.\n', ...
                    n_rows, n_times, n_rows);
            else
                fprintf('  WARNING: timeseries has %d rows but timeline has %d frames. Padding.\n', ...
                    n_rows, n_times);
            end
        end

        ts_data.RealTime_s = real_time_series;
        ts_data.Interval_s = interval_series;

        rt_csv = fullfile(output_dir, sprintf('timeseries_realtime_%s.csv', ts));
        writetable(ts_data, rt_csv);
        fprintf('  Saved: %s\n', rt_csv);
    else
        fprintf('  No timeseries_*.csv found in output directory. Skipping patch.\n');
    end

    %% Summary
    fprintf('\n==========================================================\n');
    fprintf('  Timeline reconstruction complete.\n');
    fprintf('  %d files, %d frames, %.1f min total\n', n_files, numel(t_real), total_time / 60);
    if n_gaps > 0
        fprintf('  %d gap(s) detected, total %.1f s\n', n_gaps, sum(gaps));
    end
    fprintf('==========================================================\n');
end


function all_tifs = sort_tifs_by_timestamp(all_tifs)
    if numel(all_tifs) <= 1
        return;
    end

    names = {all_tifs.name};
    name_rank = natural_name_rank(names);
    date_nums = [all_tifs.datenum].';
    invalid_time = ~(isfinite(date_nums) & date_nums > 0);
    primary_time = date_nums;
    primary_time(invalid_time) = inf;

    sort_keys = [double(invalid_time), primary_time, double(name_rank(:))];
    [~, sort_idx] = sortrows(sort_keys, [1 2 3]);
    all_tifs = all_tifs(sort_idx);
end


function rank = natural_name_rank(names)
    sorted_names = natsort(names);
    [~, rank] = ismember(names, sorted_names);
    if any(rank == 0)
        rank = 1:numel(names);
    end
end


function [dt_value, source] = parse_interval_from_name(bname)
    dt_value = nan;
    source = '';

    patterns = { ...
        '(\d+)\s*seconds?', ...
        '(?:(?<=^)|(?<=\s)|(?<=_))(\d+)\s*[sS](?=[_\s.]|$)'};

    for i = 1:numel(patterns)
        tok = regexp(bname, patterns{i}, 'tokens', 'once');
        if ~isempty(tok)
            dt_value = str2double(tok{1});
            if isfinite(dt_value) && dt_value > 0
                source = 'filename';
                return;
            end
        end
    end
end


function file_info = infer_missing_intervals(file_info)
    for i = 1:numel(file_info)
        if isfinite(file_info(i).dt) && file_info(i).dt > 0
            continue;
        end

        [dt_value, source] = infer_interval_from_neighbors(file_info, i);
        if ~isfinite(dt_value) || dt_value <= 0
            dt_value = 1;
            source = 'default_1s';
        end

        file_info(i).dt = normalize_interval_seconds(dt_value);
        file_info(i).dt_source = source;
        fprintf('    INFO: %s interval inferred as %s s via %s.\n', ...
            strip_extension(file_info(i).basename), ...
            format_scalar(file_info(i).dt), source);
    end
end


function [dt_value, source] = infer_interval_from_neighbors(file_info, idx)
    dt_value = nan;
    source = '';

    if idx > 1 && file_info(idx).n_pages > 0 && ...
            isfinite(file_info(idx - 1).datenum) && isfinite(file_info(idx).datenum)
        delta_sec = (file_info(idx).datenum - file_info(idx - 1).datenum) * 86400;
        if delta_sec > 0
            dt_value = delta_sec / file_info(idx).n_pages;
            source = 'prev_timestamp_delta';
            return;
        end
    end

    prev_dt = nan;
    next_dt = nan;
    if idx > 1 && isfinite(file_info(idx - 1).dt) && file_info(idx - 1).dt > 0
        prev_dt = file_info(idx - 1).dt;
    end
    if idx < numel(file_info) && isfinite(file_info(idx + 1).dt) && file_info(idx + 1).dt > 0
        next_dt = file_info(idx + 1).dt;
    end

    if isfinite(prev_dt) && isfinite(next_dt) && abs(prev_dt - next_dt) < 1e-9
        dt_value = prev_dt;
        source = 'neighbor_consensus';
    elseif isfinite(prev_dt)
        dt_value = prev_dt;
        source = 'prev_neighbor_dt';
    elseif isfinite(next_dt)
        dt_value = next_dt;
        source = 'next_neighbor_dt';
    end
end


function dt_value = normalize_interval_seconds(dt_value)
    if ~isfinite(dt_value) || dt_value <= 0
        return;
    end

    rounded = round(dt_value);
    if abs(dt_value - rounded) < 0.25
        dt_value = rounded;
    end
end


function [real_time_series, interval_series] = align_realtime_columns(t_real, dt_filtered, n_rows)
    n_times = numel(t_real);

    if n_times == 0
        real_time_series = (0:max(n_rows - 1, 0)).';
        interval_series = ones(n_rows, 1);
        return;
    end

    if n_rows <= n_times
        real_time_series = t_real(1:n_rows);
        interval_series = dt_filtered(1:n_rows);
        return;
    end

    if n_times >= 2
        extra_dt = t_real(end) - t_real(end - 1);
    else
        extra_dt = 1;
    end
    if isempty(dt_filtered)
        last_interval = 1;
    else
        last_interval = dt_filtered(end);
    end

    extra_count = n_rows - n_times;
    real_time_series = [t_real; t_real(end) + (1:extra_count)' * extra_dt];
    interval_series = [dt_filtered; repmat(last_interval, extra_count, 1)];
end


function txt = format_scalar(value)
    if abs(value - round(value)) < 1e-9
        txt = sprintf('%d', round(value));
    else
        txt = sprintf('%.4g', value);
    end
end


function name = strip_extension(path_in)
    [~, name, ~] = fileparts(path_in);
end
