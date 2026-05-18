function audit = run_segmentation_context_audit(output_root, varargin)
% RUN_SEGMENTATION_CONTEXT_AUDIT  Read-only audit of segmentation context.
%
% The audit inspects existing segmentation outputs and metadata before any
% geometry extraction or segmentation rerun. It never runs segmentation and
% writes only to a new segmentation_context_audit_* directory under
% PostprocessDir.

    parser = inputParser();
    parser.addRequired('output_root', @(x) ischar(x) || isstring(x));
    parser.addParameter('PostprocessDir', '', @(x) ischar(x) || isstring(x));
    parser.addParameter('MetadataRecoveryDir', '', @(x) ischar(x) || isstring(x));
    parser.addParameter('RawImageDir', '', @(x) ischar(x) || isstring(x));
    parser.addParameter('FrameTimelineCsv', '', @(x) ischar(x) || isstring(x));
    parser.addParameter('WriteReport', true, @(x) islogical(x) || isnumeric(x));
    parser.addParameter('StrictMode', false, @(x) islogical(x) || isnumeric(x));
    parser.parse(output_root, varargin{:});
    opts = parser.Results;

    output_root = char(output_root);
    postprocess_dir = char(opts.PostprocessDir);
    metadata_recovery_dir = char(opts.MetadataRecoveryDir);
    raw_image_dir = char(opts.RawImageDir);
    frame_timeline_csv = char(opts.FrameTimelineCsv);
    write_report_flag = logical(opts.WriteReport);
    strict_mode = logical(opts.StrictMode);

    assert(isfolder(output_root), 'run_segmentation_context_audit:missingOutputRoot', ...
        'output_root does not exist: %s', output_root);
    if isempty(postprocess_dir)
        postprocess_dir = output_root;
    end
    assert(isfolder(postprocess_dir), 'run_segmentation_context_audit:missingPostprocessDir', ...
        'PostprocessDir does not exist: %s', postprocess_dir);
    if isempty(raw_image_dir)
        raw_image_dir = output_root;
    end

    audit_dir = make_audit_dir(postprocess_dir);

    audit = struct();
    audit.OutputRoot = output_root;
    audit.PostprocessDir = postprocess_dir;
    audit.MetadataRecoveryDir = metadata_recovery_dir;
    audit.RawImageDir = raw_image_dir;
    audit.FrameTimelineCsv = frame_timeline_csv;
    audit.AuditDir = audit_dir;
    audit.Timestamp = datestr(now, 30);
    audit.WriteReport = write_report_flag;
    audit.StrictMode = strict_mode;
    audit.Errors = {};

    results_files = discover_named_files(output_root, '^results_.*\.mat$');
    results_files = exclude_audit_paths(results_files);
    audit.ResultsMatFiles = results_files(:)';

    mat_inventory = inspect_results_mat_files(results_files, output_root);
    context = assess_segmentation_context(mat_inventory, results_files);
    existing = assess_existing_masks_and_labels(postprocess_dir);
    frame_mapping = assess_frame_mapping(output_root, raw_image_dir, frame_timeline_csv);

    availability = build_availability_table(context, existing, frame_mapping, mat_inventory);
    readiness = build_readiness(context, existing, frame_mapping, mat_inventory);

    audit.SafeForValidationExtraction = readiness.SafeForValidationExtraction;
    audit.Decision = readiness.Decision;
    audit.ExtractionSource = readiness.RecommendedSource;
    audit.BlockingIssues = split_issue_list(readiness.BlockingIssues);
    audit.Context = context;
    audit.ExistingSegmentation = existing;
    audit.FrameMapping = frame_mapping;

    writetable(mat_inventory, fullfile(audit_dir, 'mat_variable_inventory.csv'));
    writetable(availability, fullfile(audit_dir, 'segmentation_context_availability.csv'));
    writetable(frame_mapping.table, fullfile(audit_dir, 'frame_mapping_readiness.csv'));
    writetable(readiness.table, fullfile(audit_dir, 'geometry_validation_readiness.csv'));

    write_json_file(fullfile(audit_dir, 'recommended_next_action.json'), ...
        recommended_next_action(audit));
    write_json_file(fullfile(audit_dir, 'segmentation_context_audit.json'), ...
        audit_json_summary(audit, mat_inventory, availability, frame_mapping.table, readiness.table));
    write_markdown_report(fullfile(audit_dir, 'segmentation_context_audit_report.md'), ...
        audit, availability, frame_mapping.table, readiness.table);

    if strict_mode && ~audit.SafeForValidationExtraction
        error('run_segmentation_context_audit:strictModeFailure', ...
            'Segmentation context audit failed in StrictMode with decision %s.', audit.Decision);
    end
end


function audit_dir = make_audit_dir(postprocess_dir)
    timestamp = datestr(now, 'yyyymmdd_HHMMSS');
    base_dir = fullfile(postprocess_dir, ['segmentation_context_audit_' timestamp]);
    audit_dir = base_dir;
    suffix = 0;
    while isfolder(audit_dir)
        suffix = suffix + 1;
        audit_dir = sprintf('%s_%02d', base_dir, suffix);
    end
    mkdir(audit_dir);
end


function files = discover_named_files(root_dir, name_pattern)
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
            files = [files; discover_named_files(path, name_pattern)]; %#ok<AGROW>
        elseif ~isempty(regexp(name, name_pattern, 'once'))
            files{end + 1, 1} = path; %#ok<AGROW>
        end
    end
end


function files = exclude_audit_paths(files)
    keep = true(size(files));
    for idx = 1:numel(files)
        parts = regexp(files{idx}, '[\\/]', 'split');
        keep(idx) = ~any(startsWith(parts, 'segmentation_context_audit_'));
    end
    files = files(keep);
end


function inventory = inspect_results_mat_files(results_files, output_root)
    MatFile = {};
    RelativePath = {};
    Readable = false(0, 1);
    VariableName = {};
    Class = {};
    SizeText = {};
    Bytes = [];
    OpenFailureClass = {};
    OpenFailureMessage = {};
    IsHugeCandidate = false(0, 1);

    for file_idx = 1:numel(results_files)
        path = results_files{file_idx};
        try
            vars = whos('-file', path);
            if isempty(vars)
                [MatFile, RelativePath, Readable, VariableName, Class, SizeText, Bytes, ...
                    OpenFailureClass, OpenFailureMessage, IsHugeCandidate] = append_inventory_row( ...
                    MatFile, RelativePath, Readable, VariableName, Class, SizeText, Bytes, ...
                    OpenFailureClass, OpenFailureMessage, IsHugeCandidate, path, output_root, ...
                    true, '', '', '', 0, '', '', false);
            else
                for var_idx = 1:numel(vars)
                    sz = vars(var_idx).size;
                    [MatFile, RelativePath, Readable, VariableName, Class, SizeText, Bytes, ...
                        OpenFailureClass, OpenFailureMessage, IsHugeCandidate] = append_inventory_row( ...
                        MatFile, RelativePath, Readable, VariableName, Class, SizeText, Bytes, ...
                        OpenFailureClass, OpenFailureMessage, IsHugeCandidate, path, output_root, ...
                        true, vars(var_idx).name, vars(var_idx).class, size_text(sz), ...
                        double(vars(var_idx).bytes), '', '', double(vars(var_idx).bytes) > 100 * 1024^2);
                end
            end
        catch ME
            failure_class = 'MAT_OPEN_FAILURE';
            if contains_non_ascii(path)
                failure_class = 'MAT_OPEN_FAILURE_POSSIBLE_PATH_ENCODING';
            end
            [MatFile, RelativePath, Readable, VariableName, Class, SizeText, Bytes, ...
                OpenFailureClass, OpenFailureMessage, IsHugeCandidate] = append_inventory_row( ...
                MatFile, RelativePath, Readable, VariableName, Class, SizeText, Bytes, ...
                OpenFailureClass, OpenFailureMessage, IsHugeCandidate, path, output_root, ...
                false, '', '', '', 0, failure_class, ME.message, false);
        end
    end

    inventory = table(MatFile, RelativePath, Readable, VariableName, Class, SizeText, Bytes, ...
        OpenFailureClass, OpenFailureMessage, IsHugeCandidate);
end


function [MatFile, RelativePath, Readable, VariableName, Class, SizeText, Bytes, ...
        OpenFailureClass, OpenFailureMessage, IsHugeCandidate] = append_inventory_row( ...
        MatFile, RelativePath, Readable, VariableName, Class, SizeText, Bytes, ...
        OpenFailureClass, OpenFailureMessage, IsHugeCandidate, path, output_root, ...
        readable, var_name, class_name, size_value, bytes_value, failure_class, failure_message, is_huge)

    MatFile{end + 1, 1} = path;
    RelativePath{end + 1, 1} = relative_path(path, output_root);
    Readable(end + 1, 1) = logical(readable);
    VariableName{end + 1, 1} = var_name;
    Class{end + 1, 1} = class_name;
    SizeText{end + 1, 1} = size_value;
    Bytes(end + 1, 1) = bytes_value;
    OpenFailureClass{end + 1, 1} = failure_class;
    OpenFailureMessage{end + 1, 1} = failure_message;
    IsHugeCandidate(end + 1, 1) = logical(is_huge);
end


function context = assess_segmentation_context(inventory, results_files)
    var_names = lower(inventory.VariableName(inventory.Readable));
    context = struct();
    context.HasReadableResultsMat = any(inventory.Readable);
    context.HasUnreadableResultsMat = any(~inventory.Readable);
    context.HasChinesePathMatOpenFailure = any(strcmp(inventory.OpenFailureClass, ...
        'MAT_OPEN_FAILURE_POSSIBLE_PATH_ENCODING'));
    context.HasConfig = any(strcmp(var_names, 'config'));
    context.HasConfigSegmentation = false;
    context.HasFlowDomain = any(strcmp(var_names, 'flow_domain'));
    context.HasSolidMask = any(strcmp(var_names, 'solid_mask'));
    context.HasThresholdContext = any(ismember(var_names, lower(threshold_variable_names())));
    context.HasCropResizePreprocessing = any(ismember(var_names, lower(preprocessing_variable_names())));
    context.ConfigSource = '';
    context.ThresholdSource = '';
    context.PreprocessingSource = '';

    if context.HasThresholdContext
        context.ThresholdSource = 'explicit_mat_variable';
    end
    if context.HasCropResizePreprocessing
        context.PreprocessingSource = 'explicit_mat_variable';
    end

    for idx = 1:numel(results_files)
        path = results_files{idx};
        if ~has_readable_var(inventory, path, 'config')
            continue;
        end
        bytes_value = inventory.Bytes(strcmp(inventory.MatFile, path) & strcmp(inventory.VariableName, 'config'));
        if ~isempty(bytes_value) && bytes_value(1) > 50 * 1024^2
            continue;
        end
        try
            loaded = load(path, 'config');
            if isfield(loaded, 'config')
                config = loaded.config;
                context.ConfigSource = path;
                if isstruct(config) && isfield(config, 'segmentation')
                    context.HasConfigSegmentation = true;
                    segmentation = config.segmentation;
                    if has_named_field(segmentation, threshold_variable_names())
                        context.HasThresholdContext = true;
                        context.ThresholdSource = 'config.segmentation';
                    end
                end
                if isstruct(config)
                    if has_named_field(config, preprocessing_variable_names())
                        context.HasCropResizePreprocessing = true;
                        context.PreprocessingSource = 'config';
                    end
                    if isfield(config, 'preprocessing') && ...
                            has_named_field(config.preprocessing, preprocessing_variable_names())
                        context.HasCropResizePreprocessing = true;
                        context.PreprocessingSource = 'config.preprocessing';
                    end
                end
            end
        catch
            % whos succeeded, but loading config failed. Keep the audit read-only
            % and continue with conservative availability flags.
        end
    end

    for idx = 1:numel(results_files)
        path = results_files{idx};
        if ~has_readable_var(inventory, path, 'results')
            continue;
        end
        bytes_value = inventory.Bytes(strcmp(inventory.MatFile, path) & strcmp(inventory.VariableName, 'results'));
        if ~isempty(bytes_value) && bytes_value(1) > 200 * 1024^2
            continue;
        end
        try
            loaded = load(path, 'results');
            if isfield(loaded, 'results') && isstruct(loaded.results)
                results = loaded.results;
                if isfield(results, 'flow_domain')
                    context.HasFlowDomain = true;
                end
                if isfield(results, 'solid_mask')
                    context.HasSolidMask = true;
                end
                if isfield(results, 'segmentation')
                    segmentation = results.segmentation;
                    if has_named_field(segmentation, threshold_variable_names())
                        context.HasThresholdContext = true;
                        context.ThresholdSource = 'results.segmentation';
                    end
                    if isstruct(segmentation) && isfield(segmentation, 'info') && ...
                            has_named_field(segmentation.info, threshold_variable_names())
                        context.HasThresholdContext = true;
                        context.ThresholdSource = 'results.segmentation.info';
                    end
                end
                if isfield(results, 'preprocessing') && ...
                        has_named_field(results.preprocessing, preprocessing_variable_names())
                    context.HasCropResizePreprocessing = true;
                    context.PreprocessingSource = 'results.preprocessing';
                end
            end
        catch
            % Loading the results struct is a best-effort nested-field check.
            % If it fails, the top-level whos inventory still records the file.
        end
    end

    context.RawReconstructionContextComplete = context.HasReadableResultsMat && ...
        context.HasConfig && context.HasConfigSegmentation && ...
        context.HasFlowDomain && context.HasSolidMask && ...
        context.HasThresholdContext && context.HasCropResizePreprocessing;
end


function tf = has_readable_var(inventory, path, var_name)
    tf = any(inventory.Readable & strcmp(inventory.MatFile, path) & strcmp(inventory.VariableName, var_name));
end


function names = threshold_variable_names()
    names = {'threshold', 'thresh', 'fixed_threshold', 'segmentation_threshold', ...
        'binary_threshold', 'gmm_threshold', 'gmm_thresholds', 'threshold_value'};
end


function names = preprocessing_variable_names()
    names = {'crop', 'crop_rect', 'crop_rectangle', 'crop_box', 'roi', ...
        'resize', 'resize_factor', 'resize_scale', 'preprocessing', ...
        'preprocess', 'preprocessing_params', 'preprocess_params'};
end


function tf = has_named_field(value, names)
    tf = false;
    if ~isstruct(value)
        return;
    end
    fields = fieldnames(value);
    lower_fields = lower(fields);
    for idx = 1:numel(names)
        name = lower(names{idx});
        if any(strcmp(lower_fields, name)) || any(contains(lower_fields, name))
            tf = true;
            return;
        end
    end
end


function existing = assess_existing_masks_and_labels(postprocess_dir)
    mask_files = discover_semantic_files(postprocess_dir, {'mask'}, ...
        {'.mat', '.tif', '.tiff', '.png'});
    label_files = discover_semantic_files(postprocess_dir, {'label', 'labels'}, ...
        {'.mat', '.tif', '.tiff', '.png'});
    mask_files = exclude_audit_paths(mask_files);
    label_files = exclude_audit_paths(label_files);

    existing = struct();
    existing.MaskFiles = mask_files(:)';
    existing.LabelFiles = label_files(:)';
    existing.HasMasks = ~isempty(mask_files);
    existing.HasLabels = ~isempty(label_files);
    existing.MaskCount = numel(mask_files);
    existing.LabelCount = numel(label_files);
    if existing.HasMasks && existing.HasLabels
        existing.Source = 'existing_masks_labels';
    elseif existing.HasMasks
        existing.Source = 'existing_masks';
    elseif existing.HasLabels
        existing.Source = 'existing_labels';
    else
        existing.Source = 'none';
    end
end


function files = discover_semantic_files(root_dir, tokens, extensions)
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
            files = [files; discover_semantic_files(path, tokens, extensions)]; %#ok<AGROW>
            continue;
        end
        [~, stem, ext] = fileparts(name);
        stem = lower(stem);
        ext = lower(ext);
        if ~any(strcmp(ext, extensions))
            continue;
        end
        has_token = false;
        for token_idx = 1:numel(tokens)
            has_token = has_token || contains(stem, lower(tokens{token_idx}));
        end
        if has_token
            files{end + 1, 1} = path; %#ok<AGROW>
        end
    end
end


function frame_mapping = assess_frame_mapping(output_root, raw_image_dir, frame_timeline_csv)
    frame_timeline_csv = char(frame_timeline_csv);
    if ~isempty(frame_timeline_csv)
        timeline_files = {frame_timeline_csv};
        explicit_timeline = true;
    else
        timeline_files = discover_named_files(output_root, '^frame_timeline_.*\.csv$');
        timeline_files = exclude_audit_paths(timeline_files);
        explicit_timeline = false;
    end
    raw_tifs = discover_raw_tifs(raw_image_dir);

    HasFrameTimeline = false;
    TimelinePath = {''};
    TimelineRows = 0;
    HasTifColumn = false;
    ReferencedTifCount = 0;
    ExistingRawTifCount = 0;
    MissingRawTifCount = 0;
    MappingReady = false;
    if explicit_timeline
        Notes = {'explicit_frame_timeline_not_found'};
    else
        Notes = {'frame_timeline_not_found'};
    end

    if ~isempty(timeline_files)
        if explicit_timeline
            timeline_path = timeline_files{1};
        else
            timeline_path = latest_file(timeline_files);
        end
        HasFrameTimeline = true;
        TimelinePath = {timeline_path};
        if ~isfile(timeline_path)
            Notes = {'explicit_frame_timeline_missing_file'};
        else
            try
            timeline = readtable(timeline_path, 'VariableNamingRule', 'preserve');
            TimelineRows = height(timeline);
            tif_col = first_existing_column(timeline, {'TifFile', 'RawTifFile', 'RawImageFile', 'ImageFile'});
            HasTifColumn = ~isempty(tif_col);
            if HasTifColumn
                tif_values = table_text_column(timeline, tif_col);
                tif_values = tif_values(~cellfun(@isempty, tif_values));
                unique_tifs = unique(tif_values, 'stable');
                ReferencedTifCount = numel(unique_tifs);
                exists_flags = false(numel(unique_tifs), 1);
                for idx = 1:numel(unique_tifs)
                    exists_flags(idx) = raw_tif_exists(raw_image_dir, unique_tifs{idx});
                end
                ExistingRawTifCount = sum(exists_flags);
                MissingRawTifCount = sum(~exists_flags);
                MappingReady = ReferencedTifCount > 0 && MissingRawTifCount == 0;
                if MappingReady
                    Notes = {'frame_timeline_maps_to_existing_raw_tifs'};
                else
                    Notes = {'frame_timeline_references_missing_raw_tifs'};
                end
            else
                Notes = {'frame_timeline_has_no_tif_column'};
            end
            catch ME
                Notes = {['frame_timeline_unreadable: ' ME.message]};
            end
        end
    end

    frame_mapping = struct();
    frame_mapping.HasFrameTimeline = HasFrameTimeline;
    frame_mapping.TimelinePath = TimelinePath{1};
    frame_mapping.TimelineRows = TimelineRows;
    frame_mapping.HasTifColumn = HasTifColumn;
    frame_mapping.ReferencedTifCount = ReferencedTifCount;
    frame_mapping.ExistingRawTifCount = ExistingRawTifCount;
    frame_mapping.MissingRawTifCount = MissingRawTifCount;
    frame_mapping.MappingReady = MappingReady;
    frame_mapping.RawTifCount = numel(raw_tifs);
    frame_mapping.RawTifAvailable = numel(raw_tifs) > 0;
    frame_mapping.Notes = Notes{1};
    frame_mapping.table = table(HasFrameTimeline, TimelinePath, TimelineRows, HasTifColumn, ...
        ReferencedTifCount, ExistingRawTifCount, MissingRawTifCount, MappingReady, ...
        numel(raw_tifs), Notes, 'VariableNames', {'HasFrameTimeline', 'TimelinePath', ...
        'TimelineRows', 'HasTifColumn', 'ReferencedTifCount', 'ExistingRawTifCount', ...
        'MissingRawTifCount', 'MappingReady', 'RawTifCount', 'Notes'});
end


function files = discover_raw_tifs(raw_image_dir)
    files = {};
    if isempty(raw_image_dir) || ~isfolder(raw_image_dir)
        return;
    end
    entries = dir(raw_image_dir);
    for idx = 1:numel(entries)
        name = entries(idx).name;
        if strcmp(name, '.') || strcmp(name, '..')
            continue;
        end
        path = fullfile(raw_image_dir, name);
        if entries(idx).isdir
            files = [files; discover_raw_tifs(path)]; %#ok<AGROW>
            continue;
        end
        [~, ~, ext] = fileparts(name);
        if strcmpi(ext, '.tif') || strcmpi(ext, '.tiff')
            files{end + 1, 1} = path; %#ok<AGROW>
        end
    end
end


function tf = raw_tif_exists(raw_image_dir, tif_value)
    tf = false;
    if isempty(raw_image_dir) || isempty(tif_value)
        return;
    end
    if is_absolute_path(tif_value)
        tf = isfile(tif_value);
        return;
    end
    tf = isfile(fullfile(raw_image_dir, tif_value));
end


function tf = is_absolute_path(path_text)
    path_text = char(path_text);
    tf = false;
    if isempty(path_text)
        return;
    end
    if numel(path_text) >= 2 && path_text(2) == ':'
        tf = true;
        return;
    end
    tf = startsWith(path_text, filesep) || startsWith(path_text, '\\');
end


function path = latest_file(files)
    datenums = zeros(numel(files), 1);
    for idx = 1:numel(files)
        info = dir(files{idx});
        datenums(idx) = info.datenum;
    end
    [~, order] = max(datenums);
    path = files{order};
end


function col = first_existing_column(T, candidates)
    col = '';
    vars = T.Properties.VariableNames;
    for idx = 1:numel(candidates)
        match = strcmp(vars, candidates{idx});
        if any(match)
            col = vars{find(match, 1, 'first')};
            return;
        end
    end
end


function values = table_text_column(T, col)
    raw = T.(col);
    if iscell(raw)
        values = raw;
    elseif isstring(raw)
        values = cellstr(raw);
    elseif ischar(raw)
        values = cellstr(raw);
    else
        values = cellstr(string(raw));
    end
    values = strtrim(values);
end


function availability = build_availability_table(context, existing, frame_mapping, inventory)
    Check = {};
    Available = false(0, 1);
    Source = {};
    Details = {};
    Severity = {};

    [Check, Available, Source, Details, Severity] = add_availability(Check, Available, Source, Details, Severity, ...
        'results_mat_readability', context.HasReadableResultsMat, 'results_*.mat', ...
        sprintf('%d readable variable rows; %d unreadable file rows', sum(inventory.Readable), sum(~inventory.Readable)), 'blocking');
    [Check, Available, Source, Details, Severity] = add_availability(Check, Available, Source, Details, Severity, ...
        'config', context.HasConfig, context.ConfigSource, bool_detail(context.HasConfig), 'blocking');
    [Check, Available, Source, Details, Severity] = add_availability(Check, Available, Source, Details, Severity, ...
        'config_segmentation', context.HasConfigSegmentation, context.ConfigSource, bool_detail(context.HasConfigSegmentation), 'blocking');
    [Check, Available, Source, Details, Severity] = add_availability(Check, Available, Source, Details, Severity, ...
        'flow_domain', context.HasFlowDomain, 'results_*.mat', bool_detail(context.HasFlowDomain), 'blocking');
    [Check, Available, Source, Details, Severity] = add_availability(Check, Available, Source, Details, Severity, ...
        'solid_mask', context.HasSolidMask, 'results_*.mat', bool_detail(context.HasSolidMask), 'blocking');
    [Check, Available, Source, Details, Severity] = add_availability(Check, Available, Source, Details, Severity, ...
        'segmentation_threshold_context', context.HasThresholdContext, context.ThresholdSource, bool_detail(context.HasThresholdContext), 'blocking');
    [Check, Available, Source, Details, Severity] = add_availability(Check, Available, Source, Details, Severity, ...
        'crop_resize_preprocessing_context', context.HasCropResizePreprocessing, context.PreprocessingSource, bool_detail(context.HasCropResizePreprocessing), 'blocking');
    [Check, Available, Source, Details, Severity] = add_availability(Check, Available, Source, Details, Severity, ...
        'frame_timeline_raw_tif_mapping', frame_mapping.MappingReady, frame_mapping.TimelinePath, frame_mapping.Notes, 'blocking');
    [Check, Available, Source, Details, Severity] = add_availability(Check, Available, Source, Details, Severity, ...
        'raw_tif_files', frame_mapping.RawTifAvailable, frame_mapping.RawTifCount, sprintf('%d raw TIF/TIFF files', frame_mapping.RawTifCount), 'blocking');
    [Check, Available, Source, Details, Severity] = add_availability(Check, Available, Source, Details, Severity, ...
        'existing_masks', existing.HasMasks, 'PostprocessDir', sprintf('%d mask files', existing.MaskCount), 'preferred');
    [Check, Available, Source, Details, Severity] = add_availability(Check, Available, Source, Details, Severity, ...
        'existing_labels', existing.HasLabels, 'PostprocessDir', sprintf('%d label files', existing.LabelCount), 'preferred');
    [Check, Available, Source, Details, Severity] = add_availability(Check, Available, Source, Details, Severity, ...
        'chinese_path_mat_open_failures', ~context.HasChinesePathMatOpenFailure, 'results_*.mat', bool_detail(~context.HasChinesePathMatOpenFailure), 'warning');

    availability = table(Check, Available, Source, Details, Severity);
end


function [Check, Available, Source, Details, Severity] = add_availability(Check, Available, Source, Details, Severity, ...
        check_name, available, source, details, severity)
    Check{end + 1, 1} = check_name;
    Available(end + 1, 1) = logical(available);
    Source{end + 1, 1} = char(string(source));
    Details{end + 1, 1} = char(string(details));
    Severity{end + 1, 1} = severity;
end


function readiness = build_readiness(context, existing, frame_mapping, inventory)
    issues = {};
    has_existing_geometry_source = existing.HasMasks || existing.HasLabels;
    if has_existing_geometry_source
        decision = 'READY_FOR_VALIDATION_GEOMETRY';
        safe = true;
        source = existing.Source;
    else
        if ~context.HasReadableResultsMat
            issues{end + 1} = 'no_readable_results_mat'; %#ok<AGROW>
        end
        if context.HasUnreadableResultsMat
            issues{end + 1} = 'unreadable_results_mat_recorded'; %#ok<AGROW>
        end
        if ~context.HasConfig
            issues{end + 1} = 'missing_config'; %#ok<AGROW>
        end
        if ~context.HasConfigSegmentation
            issues{end + 1} = 'missing_config_segmentation'; %#ok<AGROW>
        end
        if ~context.HasFlowDomain
            issues{end + 1} = 'missing_flow_domain'; %#ok<AGROW>
        end
        if ~context.HasSolidMask
            issues{end + 1} = 'missing_solid_mask'; %#ok<AGROW>
        end
        if ~context.HasThresholdContext
            issues{end + 1} = 'missing_threshold_context'; %#ok<AGROW>
        end
        if ~context.HasCropResizePreprocessing
            issues{end + 1} = 'missing_crop_resize_preprocessing_context'; %#ok<AGROW>
        end
        if ~frame_mapping.MappingReady
            issues{end + 1} = 'missing_frame_timeline_raw_tif_mapping'; %#ok<AGROW>
        end
        if ~frame_mapping.RawTifAvailable
            issues{end + 1} = 'missing_raw_tif_files'; %#ok<AGROW>
        end

        if context.RawReconstructionContextComplete && frame_mapping.MappingReady && frame_mapping.RawTifAvailable
            decision = 'READY_FOR_VALIDATION_GEOMETRY';
            safe = true;
            source = 'raw_frames_with_recorded_segmentation_context';
        elseif context.HasReadableResultsMat && frame_mapping.RawTifAvailable && ...
                (~context.HasThresholdContext || ~context.HasCropResizePreprocessing || ...
                ~context.HasConfig || ~context.HasConfigSegmentation)
            decision = 'NEED_MANUAL_CONFIG';
            safe = false;
            source = 'none';
        elseif ~frame_mapping.MappingReady || ~frame_mapping.RawTifAvailable || ~context.HasReadableResultsMat
            decision = 'NOT_RECOVERABLE_WITHOUT_RERUN';
            safe = false;
            source = 'none';
        else
            decision = 'NEED_MANUAL_CONFIG';
            safe = false;
            source = 'none';
        end
    end

    if isempty(issues)
        issue_text = '';
    else
        issue_text = strjoin(unique(issues, 'stable'), ';');
    end

    SafeForValidationExtraction = safe;
    Decision = {decision};
    RecommendedSource = {source};
    ExistingMasksAvailable = existing.HasMasks;
    ExistingLabelsAvailable = existing.HasLabels;
    RawReconstructionContextComplete = context.RawReconstructionContextComplete;
    FrameMappingReady = frame_mapping.MappingReady;
    RawTifAvailable = frame_mapping.RawTifAvailable;
    ReadableResultsMatCount = numel(unique(inventory.MatFile(inventory.Readable)));
    UnreadableResultsMatCount = sum(~inventory.Readable);
    BlockingIssues = {issue_text};

    readiness = struct();
    readiness.SafeForValidationExtraction = SafeForValidationExtraction;
    readiness.Decision = decision;
    readiness.RecommendedSource = source;
    readiness.BlockingIssues = issue_text;
    readiness.table = table(SafeForValidationExtraction, Decision, RecommendedSource, ...
        ExistingMasksAvailable, ExistingLabelsAvailable, RawReconstructionContextComplete, ...
        FrameMappingReady, RawTifAvailable, ReadableResultsMatCount, ...
        UnreadableResultsMatCount, BlockingIssues);
end


function action = recommended_next_action(audit)
    action = struct();
    action.decision = audit.Decision;
    action.safe_for_validation_extraction = audit.SafeForValidationExtraction;
    action.extraction_source = audit.ExtractionSource;
    action.audit_dir = audit.AuditDir;
    action.blocking_issues = audit.BlockingIssues;
    if strcmp(audit.Decision, 'READY_FOR_VALIDATION_GEOMETRY')
        action.next_action = 'Proceed with geometry validation using the recommended source; do not rerun segmentation for this audit.';
    elseif strcmp(audit.Decision, 'NEED_MANUAL_CONFIG')
        action.next_action = 'Provide explicit threshold and preprocessing configuration before validation extraction.';
    else
        action.next_action = 'Do not attempt validation extraction from current artifacts; rerun or recover segmentation outputs first.';
    end
end


function summary = audit_json_summary(audit, mat_inventory, availability, frame_mapping, readiness)
    summary = struct();
    summary.output_root = audit.OutputRoot;
    summary.postprocess_dir = audit.PostprocessDir;
    summary.metadata_recovery_dir = audit.MetadataRecoveryDir;
    summary.raw_image_dir = audit.RawImageDir;
    summary.audit_dir = audit.AuditDir;
    summary.timestamp = audit.Timestamp;
    summary.decision = audit.Decision;
    summary.safe_for_validation_extraction = audit.SafeForValidationExtraction;
    summary.extraction_source = audit.ExtractionSource;
    summary.blocking_issues = audit.BlockingIssues;
    summary.context = audit.Context;
    summary.existing_segmentation = audit.ExistingSegmentation;
    summary.frame_mapping = audit.FrameMapping;
    summary.mat_variable_inventory = table2struct(mat_inventory);
    summary.segmentation_context_availability = table2struct(availability);
    summary.frame_mapping_readiness = table2struct(frame_mapping);
    summary.geometry_validation_readiness = table2struct(readiness);
end


function write_json_file(path, value)
    text = jsonencode(value);
    fid = fopen(path, 'w');
    if fid < 0
        error('run_segmentation_context_audit:writeJsonFailed', 'Failed to write %s.', path);
    end
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, '%s', text);
end


function write_markdown_report(path, audit, availability, frame_mapping, readiness)
    lines = {};
    lines{end + 1} = '# Segmentation Context Audit';
    lines{end + 1} = '';
    lines{end + 1} = ['Decision: ' audit.Decision];
    lines{end + 1} = ['SafeForValidationExtraction: ' logical_text(audit.SafeForValidationExtraction)];
    lines{end + 1} = ['RecommendedSource: ' audit.ExtractionSource];
    lines{end + 1} = ['AuditDir: ' audit.AuditDir];
    lines{end + 1} = '';
    lines{end + 1} = '## Geometry Validation Readiness';
    lines{end + 1} = table_summary_line(readiness);
    lines{end + 1} = '';
    lines{end + 1} = '## Segmentation Context Availability';
    for idx = 1:height(availability)
        lines{end + 1} = sprintf('- %s: %s (%s)', availability.Check{idx}, ...
            logical_text(availability.Available(idx)), availability.Details{idx}); %#ok<AGROW>
    end
    lines{end + 1} = '';
    lines{end + 1} = '## Frame Mapping';
    lines{end + 1} = table_summary_line(frame_mapping);

    fid = fopen(path, 'w');
    if fid < 0
        error('run_segmentation_context_audit:writeReportFailed', 'Failed to write %s.', path);
    end
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    for idx = 1:numel(lines)
        fprintf(fid, '%s\n', lines{idx});
    end
end


function text = table_summary_line(T)
    if height(T) == 0
        text = '(empty)';
    else
        names = T.Properties.VariableNames;
        parts = cell(1, numel(names));
        for idx = 1:numel(names)
            value = T.(names{idx});
            if iscell(value)
                parts{idx} = sprintf('%s=%s', names{idx}, char(string(value{1})));
            else
                parts{idx} = sprintf('%s=%s', names{idx}, char(string(value(1))));
            end
        end
        text = strjoin(parts, ', ');
    end
end


function text = logical_text(value)
    if value
        text = 'true';
    else
        text = 'false';
    end
end


function detail = bool_detail(value)
    if value
        detail = 'available';
    else
        detail = 'missing';
    end
end


function parts = split_issue_list(issue_text)
    if isempty(issue_text)
        parts = {};
    else
        parts = regexp(issue_text, ';', 'split');
    end
end


function text = size_text(sz)
    if isempty(sz)
        text = '';
        return;
    end
    pieces = cell(1, numel(sz));
    for idx = 1:numel(sz)
        pieces{idx} = sprintf('%d', sz(idx));
    end
    text = strjoin(pieces, 'x');
end


function path = relative_path(path, root_dir)
    path = char(path);
    root_dir = char(root_dir);
    if startsWith(lower(path), lower([root_dir filesep]))
        path = path(numel(root_dir) + 2:end);
    end
end


function tf = contains_non_ascii(text)
    text = char(text);
    tf = any(double(text) > 127);
end
