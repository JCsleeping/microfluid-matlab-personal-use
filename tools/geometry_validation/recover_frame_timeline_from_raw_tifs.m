function result = recover_frame_timeline_from_raw_tifs(output_root, varargin)
% RECOVER_FRAME_TIMELINE_FROM_RAW_TIFS  Rebuild frame-to-TIF mapping without segmentation.
%
% This tool is read-only with respect to pipeline outputs. It writes a new
% frame_timeline_recovery_* directory under the postprocess directory.

    parser = inputParser;
    parser.addRequired('output_root', @(x) ischar(x) || isstring(x));
    parser.addParameter('PostprocessDir', '', @(x) ischar(x) || isstring(x));
    parser.addParameter('RawImageDir', '', @(x) ischar(x) || isstring(x));
    parser.addParameter('TimeseriesCsv', '', @(x) ischar(x) || isstring(x));
    parser.addParameter('OutputDir', '', @(x) ischar(x) || isstring(x));
    parser.addParameter('WriteReport', true, @(x) islogical(x) || isnumeric(x));
    parser.addParameter('Overwrite', false, @(x) islogical(x) || isnumeric(x));
    parser.addParameter('StrictMode', false, @(x) islogical(x) || isnumeric(x));
    parser.parse(output_root, varargin{:});
    opts = parser.Results;

    output_root = char(output_root);
    if ~isfolder(output_root)
        error('recover_frame_timeline:missingOutputRoot', 'Output root does not exist: %s', output_root);
    end
    postprocess_dir = char(opts.PostprocessDir);
    if isempty(postprocess_dir)
        postprocess_dir = output_root;
    end
    if ~isfolder(postprocess_dir)
        mkdir(postprocess_dir);
    end
    raw_image_dir = char(opts.RawImageDir);
    if isempty(raw_image_dir)
        raw_image_dir = fileparts(output_root);
    end

    output_dir = char(opts.OutputDir);
    if isempty(output_dir)
        output_dir = fullfile(postprocess_dir, ['frame_timeline_recovery_' datestr(now, 'yyyymmdd_HHMMSS')]);
    end
    if isfolder(output_dir) && ~logical(opts.Overwrite) && ~isempty(dir(fullfile(output_dir, '*')))
        error('recover_frame_timeline:outputExists', 'Output directory already exists and is not empty: %s', output_dir);
    end
    if ~isfolder(output_dir)
        mkdir(output_dir);
    end

    raw_inventory = build_raw_tif_inventory(raw_image_dir);
    timeseries = read_timeseries(output_root, char(opts.TimeseriesCsv));
    existing_candidates = find_existing_timeline_candidates(output_root, postprocess_dir, raw_image_dir, output_dir);
    [existing_timeline, existing_path, existing_ok, existing_issue] = load_first_valid_existing_timeline( ...
        existing_candidates, raw_inventory, timeseries);

    if existing_ok
        timeline = existing_timeline;
        mapping_source = 'existing_timeline';
        decision = validate_timeline(timeline, raw_inventory, timeseries);
        issue = decision.BlockingIssue;
    else
        [timeline, mapping_source] = rebuild_timeline(raw_inventory, timeseries);
        decision = validate_timeline(timeline, raw_inventory, timeseries);
        issue = decision.BlockingIssue;
        if isempty(issue) && ~isempty(existing_issue)
            issue = '';
        end
    end

    writetable(raw_inventory.table, fullfile(output_dir, 'raw_tif_inventory.csv'));
    if ~isempty(timeline)
        writetable(timeline, fullfile(output_dir, 'frame_timeline_recovered.csv'));
    else
        writetable(empty_timeline_table(), fullfile(output_dir, 'frame_timeline_recovered.csv'));
    end
    write_unparsed_review(output_dir, raw_inventory);

    summary = struct();
    summary.output_root = output_root;
    summary.postprocess_dir = postprocess_dir;
    summary.raw_image_dir = raw_image_dir;
    summary.output_dir = output_dir;
    summary.timestamp = datestr(now, 'yyyymmddTHHMMSS');
    summary.decision = decision.Decision;
    summary.ready_for_context_reaudit = strcmp(decision.Decision, 'READY_FOR_CONTEXT_REAUDIT');
    summary.mapping_source = mapping_source;
    summary.existing_timeline_path = existing_path;
    summary.existing_timeline_issue = existing_issue;
    summary.blocking_issue = issue;
    summary.raw_tif_count = height(raw_inventory.table);
    summary.raw_tif_total_pages = raw_inventory.TotalPages;
    summary.timeline_rows = height(timeline);
    summary.expected_frame_count = timeseries.ExpectedFrameCount;
    summary.last_real_time_s = decision.LastRealTime_s;
    write_json_file(fullfile(output_dir, 'frame_timeline_recovery_summary.json'), summary);

    action = struct();
    action.decision = decision.Decision;
    action.ready_for_context_reaudit = summary.ready_for_context_reaudit;
    action.frame_timeline_csv = fullfile(output_dir, 'frame_timeline_recovered.csv');
    action.next_action = recommended_action(decision.Decision);
    action.blocking_issue = issue;
    write_json_file(fullfile(output_dir, 'recommended_next_action.json'), action);

    if logical(opts.WriteReport)
        write_report(fullfile(output_dir, 'frame_timeline_recovery_report.md'), summary, decision);
    end

    result = struct();
    result.OutputDir = output_dir;
    result.FrameTimelineCsv = fullfile(output_dir, 'frame_timeline_recovered.csv');
    result.RawTifInventoryCsv = fullfile(output_dir, 'raw_tif_inventory.csv');
    result.Decision = decision.Decision;
    result.ReadyForContextReaudit = summary.ready_for_context_reaudit;
    result.MappingSource = mapping_source;
    result.BlockingIssue = issue;
    result.TimelineRows = height(timeline);
    result.RawTifTotalPages = raw_inventory.TotalPages;
end


function inventory = build_raw_tif_inventory(raw_image_dir)
    files = discover_tifs(raw_image_dir);
    n = numel(files);
    FullPath = files(:);
    TifFile = cell(n, 1);
    FileOrder = zeros(n, 1);
    StagePrefix = NaN(n, 1);
    NumericSuffix = NaN(n, 1);
    NumPages = zeros(n, 1);
    Width = zeros(n, 1);
    Height = zeros(n, 1);
    BitDepth = zeros(n, 1);
    ParsedInterval_s = NaN(n, 1);
    ParsedStageLabel = cell(n, 1);
    OrderParseStatus = cell(n, 1);

    for idx = 1:n
        [~, name, ext] = fileparts(files{idx});
        TifFile{idx} = [name ext];
        parsed = parse_tif_name(TifFile{idx});
        StagePrefix(idx) = parsed.StagePrefix;
        NumericSuffix(idx) = parsed.NumericSuffix;
        ParsedInterval_s(idx) = parsed.Interval_s;
        ParsedStageLabel{idx} = parsed.StageLabel;
        OrderParseStatus{idx} = parsed.Status;
        try
            info = imfinfo(files{idx});
            NumPages(idx) = numel(info);
            if ~isempty(info)
                Width(idx) = info(1).Width;
                Height(idx) = info(1).Height;
                if isfield(info, 'BitDepth')
                    BitDepth(idx) = info(1).BitDepth;
                end
            end
        catch
            NumPages(idx) = 0;
        end
    end

    if n > 0
        sort_table = table(StagePrefix, NumericSuffix, string(lower(TifFile)), (1:n)', ...
            'VariableNames', {'StagePrefix', 'NumericSuffix', 'NameKey', 'OriginalIndex'});
        sort_table.StagePrefix(isnan(sort_table.StagePrefix)) = inf;
        sort_table.NumericSuffix(isnan(sort_table.NumericSuffix)) = inf;
        [~, order] = sortrows(sort_table, {'StagePrefix', 'NumericSuffix', 'NameKey', 'OriginalIndex'});
    else
        order = [];
    end

    FullPath = FullPath(order);
    TifFile = TifFile(order);
    StagePrefix = StagePrefix(order);
    NumericSuffix = NumericSuffix(order);
    NumPages = NumPages(order);
    Width = Width(order);
    Height = Height(order);
    BitDepth = BitDepth(order);
    ParsedInterval_s = ParsedInterval_s(order);
    ParsedStageLabel = ParsedStageLabel(order);
    OrderParseStatus = OrderParseStatus(order);
    FileOrder = (1:n)';

    inventory.table = table(TifFile, FullPath, FileOrder, StagePrefix, NumericSuffix, NumPages, ...
        Width, Height, BitDepth, ParsedInterval_s, ParsedStageLabel, OrderParseStatus);
    inventory.TotalPages = sum(NumPages);
end


function files = discover_tifs(root_dir)
    files = {};
    if isempty(root_dir) || ~isfolder(root_dir)
        return;
    end
    entries = dir(root_dir);
    for idx = 1:numel(entries)
        name = entries(idx).name;
        if strcmp(name, '.') || strcmp(name, '..')
            continue;
        end
        path = fullfile(root_dir, name);
        if entries(idx).isdir
            child = discover_tifs(path);
            files = [files; child]; %#ok<AGROW>
        else
            [~, ~, ext] = fileparts(name);
            if strcmpi(ext, '.tif') || strcmpi(ext, '.tiff')
                files{end + 1, 1} = path; %#ok<AGROW>
            end
        end
    end
end


function parsed = parse_tif_name(name)
    [~, base, ~] = fileparts(name);
    stage = regexp(base, '^\s*(\d+)', 'tokens', 'once');
    suffix = regexp(base, '_(\d+)$', 'tokens', 'once');
    interval = regexp(base, '(\d+)\s*SECONDS?', 'tokens', 'once');
    if isempty(stage)
        parsed.StagePrefix = NaN;
    else
        parsed.StagePrefix = str2double(stage{1});
    end
    if isempty(suffix)
        parsed.NumericSuffix = 0;
    else
        parsed.NumericSuffix = str2double(suffix{1});
    end
    if isempty(interval)
        parsed.Interval_s = NaN;
    else
        parsed.Interval_s = str2double(interval{1});
    end
    parsed.StageLabel = regexprep(base, '_\d+$', '');
    if isnan(parsed.StagePrefix)
        parsed.Status = 'unparsed_stage_prefix';
    else
        parsed.Status = 'parsed';
    end
end


function timeseries = read_timeseries(output_root, explicit_path)
    if ~isempty(explicit_path)
        path = explicit_path;
    else
        path = latest_file(output_root, 'timeseries_realtime_*.csv');
        if isempty(path)
            path = latest_file(output_root, 'timeseries_*.csv');
        end
    end
    timeseries = struct();
    timeseries.Path = path;
    timeseries.ExpectedFrameCount = NaN;
    timeseries.RealTime_s = [];
    timeseries.Interval_s = [];
    if isempty(path) || ~isfile(path)
        return;
    end
    T = readtable(path, 'VariableNamingRule', 'preserve');
    timeseries.ExpectedFrameCount = height(T);
    time_col = first_existing_column(T, {'RealTime_s', 'Time_s', 'FrameTime', 'Time'});
    if ~isempty(time_col)
        t = double(T.(time_col));
        timeseries.RealTime_s = t(:);
        if numel(t) > 1
            dt = [t(2) - t(1); diff(t)];
        else
            dt = NaN;
        end
        timeseries.Interval_s = dt(:);
    end
end


function candidates = find_existing_timeline_candidates(output_root, postprocess_dir, raw_image_dir, output_dir)
    roots = unique_nonempty({output_root, postprocess_dir, raw_image_dir});
    patterns = {'^frame_timeline_.*\.csv$', '^timeline.*\.csv$', '^frame_map.*\.csv$'};
    candidates = {};
    for r = 1:numel(roots)
        files = recursive_files(roots{r});
        for i = 1:numel(files)
            if startsWith(files{i}, [output_dir filesep])
                continue;
            end
            [~, name, ext] = fileparts(files{i});
            base = [name ext];
            for p = 1:numel(patterns)
                if ~isempty(regexp(base, patterns{p}, 'once'))
                    candidates{end + 1, 1} = files{i}; %#ok<AGROW>
                    break;
                end
            end
        end
    end
    candidates = unique(candidates, 'stable');
end


function [timeline, path, ok, issue] = load_first_valid_existing_timeline(candidates, raw_inventory, timeseries)
    timeline = empty_timeline_table();
    path = '';
    ok = false;
    issue = '';
    for idx = 1:numel(candidates)
        try
            T = readtable(candidates{idx}, 'VariableNamingRule', 'preserve');
            T = normalize_timeline_table(T, raw_inventory);
            decision = validate_timeline(T, raw_inventory, timeseries);
            if strcmp(decision.Decision, 'READY_FOR_CONTEXT_REAUDIT')
                timeline = T;
                path = candidates{idx};
                ok = true;
                return;
            end
            issue = decision.BlockingIssue;
        catch ME
            issue = ME.message;
        end
    end
end


function [timeline, mapping_source] = rebuild_timeline(raw_inventory, timeseries)
    inv = raw_inventory.table;
    total_pages = sum(inv.NumPages);
    if total_pages <= 0
        timeline = empty_timeline_table();
        mapping_source = 'raw_tif_inventory';
        return;
    end
    GlobalFrame = zeros(total_pages, 1);
    FrameIndex = zeros(total_pages, 1);
    TifFile = cell(total_pages, 1);
    PageInTif = zeros(total_pages, 1);
    TifPath = cell(total_pages, 1);
    row = 0;
    for i = 1:height(inv)
        for page = 1:inv.NumPages(i)
            row = row + 1;
            GlobalFrame(row) = row;
            FrameIndex(row) = row;
            TifFile{row} = inv.TifFile{i};
            PageInTif(row) = page;
            TifPath{row} = inv.FullPath{i};
        end
    end
    [RealTime_s, Interval_s, time_source] = timeline_time(total_pages, timeseries, inv);
    MappingSource = repmat({'raw_tif_inventory'}, total_pages, 1);
    MappingConfidence = repmat({'high'}, total_pages, 1);
    TimeSource = repmat({time_source}, total_pages, 1);
    timeline = table(GlobalFrame, FrameIndex, TifFile, PageInTif, RealTime_s, Interval_s, ...
        TifPath, MappingSource, MappingConfidence, TimeSource);
    mapping_source = 'rebuilt_from_raw_tifs';
end


function [RealTime_s, Interval_s, source] = timeline_time(n, timeseries, raw_inventory_table)
    if numel(timeseries.RealTime_s) == n
        RealTime_s = timeseries.RealTime_s(:);
        if numel(timeseries.Interval_s) == n
            Interval_s = timeseries.Interval_s(:);
        else
            Interval_s = [NaN; diff(RealTime_s)];
        end
        source = 'timeseries';
        return;
    end
    intervals = raw_inventory_table.ParsedInterval_s;
    intervals = intervals(isfinite(intervals) & intervals > 0);
    if ~isempty(intervals)
        dt = mode(intervals);
    else
        dt = 1;
    end
    RealTime_s = (0:n-1)' * dt;
    Interval_s = repmat(dt, n, 1);
    source = 'filename_interval_fallback';
end


function T = normalize_timeline_table(T, raw_inventory)
    if ~ismember('GlobalFrame', T.Properties.VariableNames)
        if ismember('FrameIndex', T.Properties.VariableNames)
            T.GlobalFrame = T.FrameIndex;
        else
            T.GlobalFrame = (1:height(T))';
        end
    end
    if ~ismember('FrameIndex', T.Properties.VariableNames)
        T.FrameIndex = T.GlobalFrame;
    end
    if ~ismember('TifFile', T.Properties.VariableNames)
        tif_col = first_existing_column(T, {'RawTifFile', 'RawImageFile', 'ImageFile'});
        if isempty(tif_col)
            error('recover_frame_timeline:badTimeline', 'Timeline lacks TifFile column.');
        end
        T.TifFile = T.(tif_col);
    end
    if ~ismember('PageInTif', T.Properties.VariableNames)
        error('recover_frame_timeline:badTimeline', 'Timeline lacks PageInTif column.');
    end
    if ~ismember('RealTime_s', T.Properties.VariableNames)
        T.RealTime_s = NaN(height(T), 1);
    end
    if ~ismember('Interval_s', T.Properties.VariableNames)
        T.Interval_s = NaN(height(T), 1);
    end
    if ~ismember('TifPath', T.Properties.VariableNames)
        tif_values = table_text_column(T, 'TifFile');
        TifPath = cell(height(T), 1);
        for i = 1:height(T)
            match = find(strcmp(raw_inventory.table.TifFile, tif_values{i}), 1);
            if isempty(match)
                TifPath{i} = '';
            else
                TifPath{i} = raw_inventory.table.FullPath{match};
            end
        end
        T.TifPath = TifPath;
    end
    if ~ismember('MappingSource', T.Properties.VariableNames)
        T.MappingSource = repmat({'existing_timeline'}, height(T), 1);
    end
    if ~ismember('MappingConfidence', T.Properties.VariableNames)
        T.MappingConfidence = repmat({'high'}, height(T), 1);
    end
    if ~ismember('TimeSource', T.Properties.VariableNames)
        T.TimeSource = repmat({'existing_timeline'}, height(T), 1);
    end
    T = T(:, {'GlobalFrame', 'FrameIndex', 'TifFile', 'PageInTif', 'RealTime_s', ...
        'Interval_s', 'TifPath', 'MappingSource', 'MappingConfidence', 'TimeSource'});
end


function decision = validate_timeline(T, raw_inventory, timeseries)
    decision = struct('Decision', 'READY_FOR_CONTEXT_REAUDIT', 'BlockingIssue', '', 'LastRealTime_s', NaN);
    n = height(T);
    if raw_inventory.TotalPages ~= n
        decision.Decision = 'BLOCKED_BY_TIF_PAGE_COUNT_MISMATCH';
        decision.BlockingIssue = sprintf('timeline_rows_%d_vs_raw_pages_%d', n, raw_inventory.TotalPages);
        return;
    end
    if isfinite(timeseries.ExpectedFrameCount) && timeseries.ExpectedFrameCount ~= n
        decision.Decision = 'BLOCKED_BY_TIF_PAGE_COUNT_MISMATCH';
        decision.BlockingIssue = sprintf('timeline_rows_%d_vs_timeseries_rows_%d', n, timeseries.ExpectedFrameCount);
        return;
    end
    if n == 0 || ~isequal(double(T.GlobalFrame(:)), (1:n)') || ~isequal(double(T.FrameIndex(:)), (1:n)')
        decision.Decision = 'BLOCKED_BY_TIF_PAGE_COUNT_MISMATCH';
        decision.BlockingIssue = 'noncontiguous_global_or_frame_index';
        return;
    end
    tif_values = table_text_column(T, 'TifFile');
    page_values = double(T.PageInTif);
    for i = 1:n
        match = find(strcmp(raw_inventory.table.TifFile, tif_values{i}), 1);
        if isempty(match) || ~isfile(T.TifPath{i})
            decision.Decision = 'BLOCKED_BY_MISSING_RAW_TIF';
            decision.BlockingIssue = ['missing_raw_tif_for_frame_' num2str(i)];
            return;
        end
        if page_values(i) < 1 || page_values(i) > raw_inventory.table.NumPages(match)
            decision.Decision = 'BLOCKED_BY_TIF_PAGE_COUNT_MISMATCH';
            decision.BlockingIssue = ['page_out_of_range_for_frame_' num2str(i)];
            return;
        end
    end
    unparsed = strcmp(raw_inventory.table.OrderParseStatus, 'unparsed_stage_prefix');
    if any(unparsed) && height(raw_inventory.table) > 1
        decision.Decision = 'BLOCKED_BY_UNRESOLVED_FILE_ORDER';
        decision.BlockingIssue = 'unparsed_file_order';
        return;
    end
    if ismember('RealTime_s', T.Properties.VariableNames)
        time = double(T.RealTime_s);
        if any(isfinite(time))
            decision.LastRealTime_s = time(find(isfinite(time), 1, 'last'));
            if any(diff(time(isfinite(time))) < 0)
                decision.Decision = 'BLOCKED_BY_TIME_AXIS_CONFLICT';
                decision.BlockingIssue = 'real_time_not_monotone';
                return;
            end
        end
    end
end


function T = empty_timeline_table()
    GlobalFrame = zeros(0, 1);
    FrameIndex = zeros(0, 1);
    TifFile = cell(0, 1);
    PageInTif = zeros(0, 1);
    RealTime_s = zeros(0, 1);
    Interval_s = zeros(0, 1);
    TifPath = cell(0, 1);
    MappingSource = cell(0, 1);
    MappingConfidence = cell(0, 1);
    TimeSource = cell(0, 1);
    T = table(GlobalFrame, FrameIndex, TifFile, PageInTif, RealTime_s, Interval_s, ...
        TifPath, MappingSource, MappingConfidence, TimeSource);
end


function write_unparsed_review(output_dir, raw_inventory)
    T = raw_inventory.table(strcmp(raw_inventory.table.OrderParseStatus, 'unparsed_stage_prefix'), :);
    if height(T) > 0
        writetable(T, fullfile(output_dir, 'unparsed_file_order_review.csv'));
    end
end


function action = recommended_action(decision)
    switch decision
        case 'READY_FOR_CONTEXT_REAUDIT'
            action = 'Rerun segmentation context audit with FrameTimelineCsv set to frame_timeline_recovered.csv.';
        case 'BLOCKED_BY_TIF_PAGE_COUNT_MISMATCH'
            action = 'Review raw TIF page counts versus timeseries frame count before geometry validation.';
        case 'BLOCKED_BY_UNRESOLVED_FILE_ORDER'
            action = 'Manually resolve raw TIF file order before geometry validation.';
        case 'BLOCKED_BY_TIME_AXIS_CONFLICT'
            action = 'Resolve time-axis conflict before geometry validation.';
        case 'BLOCKED_BY_MISSING_RAW_TIF'
            action = 'Locate missing raw TIF files before geometry validation.';
        otherwise
            action = 'Review frame timeline recovery report.';
    end
end


function write_report(path, summary, decision)
    fid = fopen(path, 'w');
    assert(fid > 0, 'Failed to open report for writing: %s', path);
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, '# Frame Timeline Recovery Report\n\n');
    fprintf(fid, '- output_root: `%s`\n', summary.output_root);
    fprintf(fid, '- raw_image_dir: `%s`\n', summary.raw_image_dir);
    fprintf(fid, '- decision: `%s`\n', summary.decision);
    fprintf(fid, '- mapping_source: `%s`\n', summary.mapping_source);
    fprintf(fid, '- raw_tif_count: `%d`\n', summary.raw_tif_count);
    fprintf(fid, '- raw_tif_total_pages: `%d`\n', summary.raw_tif_total_pages);
    fprintf(fid, '- timeline_rows: `%d`\n', summary.timeline_rows);
    fprintf(fid, '- expected_frame_count: `%g`\n', summary.expected_frame_count);
    fprintf(fid, '- blocking_issue: `%s`\n\n', decision.BlockingIssue);
    fprintf(fid, 'No segmentation, geometry validation, sidecar extraction, tracking, or fractal analysis was run.\n');
end


function write_json_file(path, value)
    fid = fopen(path, 'w');
    assert(fid > 0, 'Failed to open JSON for writing: %s', path);
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, '%s', jsonencode(value));
end


function files = recursive_files(root_dir)
    files = {};
    if isempty(root_dir) || ~isfolder(root_dir)
        return;
    end
    entries = dir(root_dir);
    for idx = 1:numel(entries)
        name = entries(idx).name;
        if strcmp(name, '.') || strcmp(name, '..')
            continue;
        end
        path = fullfile(root_dir, name);
        if entries(idx).isdir
            child = recursive_files(path);
            files = [files; child]; %#ok<AGROW>
        else
            files{end + 1, 1} = path; %#ok<AGROW>
        end
    end
end


function path = latest_file(root_dir, pattern)
    files = dir(fullfile(root_dir, pattern));
    if isempty(files)
        path = '';
        return;
    end
    [~, idx] = max([files.datenum]);
    path = fullfile(files(idx).folder, files(idx).name);
end


function name = first_existing_column(T, candidates)
    name = '';
    for idx = 1:numel(candidates)
        if ismember(candidates{idx}, T.Properties.VariableNames)
            name = candidates{idx};
            return;
        end
    end
end


function values = table_text_column(T, name)
    raw = T.(name);
    if iscell(raw)
        values = raw;
    elseif isstring(raw)
        values = cellstr(raw);
    else
        values = cellstr(string(raw));
    end
end


function values = unique_nonempty(values)
    values = values(~cellfun(@isempty, values));
    values = unique(values, 'stable');
end
