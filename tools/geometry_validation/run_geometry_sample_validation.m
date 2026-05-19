function validation = run_geometry_sample_validation(output_root, postprocess_dir, metadata_json, varargin)
% RUN_GEOMETRY_SAMPLE_VALIDATION  Validate small-frame blob geometry extraction.
%
% This tool is intentionally conservative. It writes only to a new validation
% directory and computes geometry from explicit validation masks when provided.
% Without masks it records why raw-frame segmentation is not safe to run.

    parser = inputParser;
    parser.addRequired('output_root', @(x) ischar(x) || isstring(x));
    parser.addRequired('postprocess_dir', @(x) ischar(x) || isstring(x));
    parser.addRequired('metadata_json', @(x) ischar(x) || isstring(x));
    parser.addParameter('OutputDir', '', @(x) ischar(x) || isstring(x));
    parser.addParameter('RawImageDir', '', @(x) ischar(x) || isstring(x));
    parser.addParameter('MaskDir', '', @(x) ischar(x) || isstring(x));
    parser.addParameter('SegmentationContextAuditDir', '', @(x) ischar(x) || isstring(x));
    parser.addParameter('FrameTimelineCsv', '', @(x) ischar(x) || isstring(x));
    parser.addParameter('SelectedFramesCsv', '', @(x) ischar(x) || isstring(x));
    parser.addParameter('MaxFrames', 40, @(x) isnumeric(x) && isscalar(x) && isfinite(x));
    parser.addParameter('Overwrite', false, @(x) islogical(x) || isnumeric(x));
    parser.parse(output_root, postprocess_dir, metadata_json, varargin{:});
    opts = parser.Results;

    output_root = char(opts.output_root);
    postprocess_dir = char(opts.postprocess_dir);
    metadata_json = char(opts.metadata_json);
    max_frames = floor(opts.MaxFrames);
    if max_frames < 20 || max_frames > 50
        error('run_geometry_sample_validation:badMaxFrames', ...
            'MaxFrames must be between 20 and 50 for small-sample validation.');
    end

    assert(isfolder(output_root), 'run_geometry_sample_validation:missingOutputRoot', ...
        'output_root does not exist: %s', output_root);
    assert(isfolder(postprocess_dir), 'run_geometry_sample_validation:missingPostprocessDir', ...
        'postprocess_dir does not exist: %s', postprocess_dir);

    output_dir = resolve_output_dir(postprocess_dir, opts.OutputDir, logical(opts.Overwrite));
    qc_dir = fullfile(output_dir, 'qc_images');
    if ~isfolder(qc_dir)
        mkdir(qc_dir);
    end

    raw_image_dir = char(opts.RawImageDir);
    if isempty(raw_image_dir)
        raw_image_dir = fileparts(output_root);
    end
    mask_dir = char(opts.MaskDir);
    context_audit_dir = char(opts.SegmentationContextAuditDir);
    if isempty(context_audit_dir)
        context_audit_dir = latest_segmentation_context_audit_dir(postprocess_dir);
    end

    selected = select_and_map_frames(output_root, postprocess_dir, raw_image_dir, max_frames, ...
        char(opts.FrameTimelineCsv), char(opts.SelectedFramesCsv));
    writetable(selected, fullfile(output_dir, 'selected_frames.csv'));

    metadata_exists = is_valid_metadata_json(metadata_json);
    [mask_present, missing_mask_frames] = mask_coverage_for_selected(mask_dir, selected.FrameIndex);
    has_any_masks = any(mask_present);
    has_all_masks = ~isempty(mask_present) && all(mask_present);
    can_segment_raw = segmentation_context_ready(context_audit_dir);
    preflight = make_preflight_table(metadata_exists, raw_image_dir, mask_dir, has_any_masks, ...
        has_all_masks, missing_mask_frames, can_segment_raw);
    writetable(preflight, fullfile(output_dir, 'geometry_validation_preflight.csv'));

    if has_all_masks
        status = 'PASS_WITH_MASKS';
        blob_table = compute_geometry_from_masks(selected, mask_dir, qc_dir);
    elseif has_any_masks
        status = 'PARTIAL_MASK_COVERAGE';
        blob_table = compute_geometry_from_masks(selected, mask_dir, qc_dir);
    elseif can_segment_raw
        status = 'PASS_WITH_RAW_CONTEXT';
        blob_table = compute_geometry_from_raw_context(selected, output_root, output_dir, qc_dir);
    else
        status = 'PRECHECK_FAILED';
        blob_table = empty_blob_table();
    end
    writetable(blob_table, fullfile(output_dir, 'geometry_sample_blob_table.csv'));

    comparison = compare_to_existing_level_a(output_root, selected, blob_table, status);
    writetable(comparison, fullfile(output_dir, 'geometry_level_a_comparison.csv'));

    availability = build_metric_availability(blob_table, has_any_masks || can_segment_raw, status);
    writetable(availability, fullfile(output_dir, 'geometry_metric_availability.csv'));
    write_report(fullfile(output_dir, 'geometry_validation_report.md'), status, selected, preflight, blob_table, comparison);

    validation = struct();
    validation.status = status;
    validation.output_dir = output_dir;
    validation.selected_frames = selected;
    validation.preflight = preflight;
    validation.geometry_sample_blob_table = blob_table;
    validation.geometry_level_a_comparison = comparison;
    validation.geometry_metric_availability = availability;
end


function output_dir = resolve_output_dir(postprocess_dir, explicit_dir, overwrite)
    explicit_dir = char(explicit_dir);
    if isempty(explicit_dir)
        base_dir = fullfile(postprocess_dir, ['geometry_sample_validation_' datestr(now, 'yyyymmdd_HHMMSS')]);
        output_dir = unique_output_dir(base_dir);
        mkdir(output_dir);
        return;
    end

    if is_absolute_path(explicit_dir)
        output_dir = explicit_dir;
    else
        output_dir = fullfile(postprocess_dir, explicit_dir);
    end
    if isfolder(output_dir)
        listing = dir(output_dir);
        names = {listing.name};
        nontrivial = ~ismember(names, {'.', '..'});
        if any(nontrivial) && ~overwrite
            error('run_geometry_sample_validation:nonemptyOutputDir', ...
                'OutputDir already exists and is not empty: %s', output_dir);
        end
    else
        mkdir(output_dir);
    end
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


function output_dir = unique_output_dir(base_dir)
    output_dir = base_dir;
    suffix = 1;
    while isfolder(output_dir)
        listing = dir(output_dir);
        names = {listing.name};
        nontrivial = ~ismember(names, {'.', '..'});
        if ~any(nontrivial)
            return;
        end
        output_dir = sprintf('%s_%03d', base_dir, suffix);
        suffix = suffix + 1;
    end
end


function ok = is_valid_metadata_json(metadata_json)
    ok = false;
    if ~isfile(metadata_json)
        return;
    end
    try
        text = fileread(metadata_json);
        decoded = jsondecode(text); %#ok<NASGU>
        ok = true;
    catch
        ok = false;
    end
end


function context_dir = latest_segmentation_context_audit_dir(postprocess_dir)
    context_dir = '';
    listing = dir(fullfile(postprocess_dir, 'segmentation_context_audit_*'));
    listing = listing([listing.isdir]);
    if isempty(listing)
        return;
    end
    [~, idx] = max([listing.datenum]);
    context_dir = fullfile(listing(idx).folder, listing(idx).name);
end


function ok = segmentation_context_ready(context_audit_dir)
    ok = false;
    if isempty(context_audit_dir) || ~isfolder(context_audit_dir)
        return;
    end
    readiness_path = fullfile(context_audit_dir, 'geometry_validation_readiness.csv');
    if ~isfile(readiness_path)
        return;
    end
    try
        T = readtable(readiness_path, 'VariableNamingRule', 'preserve');
        if height(T) < 1 || ~ismember('SafeForValidationExtraction', T.Properties.VariableNames)
            return;
        end
        safe = logical(T.SafeForValidationExtraction(1));
        if ismember('RecommendedSource', T.Properties.VariableNames)
            source = T.RecommendedSource{1};
        else
            source = '';
        end
        ok = safe && contains(char(source), 'raw_frames');
    catch
        ok = false;
    end
end


function selected = select_and_map_frames(output_root, postprocess_dir, raw_image_dir, max_frames, frame_timeline_csv, selected_frames_csv)
    selected_frames_csv = char(selected_frames_csv);
    if ~isempty(selected_frames_csv)
        selected = read_explicit_selected_frames(selected_frames_csv, max_frames);
    else
        rates_path = fullfile(postprocess_dir, 'dissolution_rates.csv');
        if ~isfile(rates_path)
            error('run_geometry_sample_validation:missingDissolutionRates', ...
                'dissolution_rates.csv not found: %s', rates_path);
        end
        rates = readtable(rates_path, 'VariableNamingRule', 'preserve');
        if ~ismember('FrameIndex', rates.Properties.VariableNames)
            error('run_geometry_sample_validation:missingFrameIndex', 'dissolution_rates.csv has no FrameIndex column.');
        end
        rates.FrameIndex = double(rates.FrameIndex);
        if ~ismember('Stage', rates.Properties.VariableNames)
            rates.Stage = repmat({'unknown'}, height(rates), 1);
        end
        if isstring(rates.Stage)
            rates.Stage = cellstr(rates.Stage);
        end
        if ~ismember('DissolutionRate_Sn_per_min', rates.Properties.VariableNames)
            rates.DissolutionRate_Sn_per_min = NaN(height(rates), 1);
        end

        frame_ids = stratified_frame_ids(rates, max_frames);
        frame_ids = unique(frame_ids(:), 'stable');
        if numel(frame_ids) > max_frames
            frame_ids = frame_ids(1:max_frames);
        end

        selected = table(frame_ids(:), 'VariableNames', {'FrameIndex'});
    end
    frame_timeline_csv = char(frame_timeline_csv);
    if ~isempty(frame_timeline_csv)
        timeline_path = frame_timeline_csv;
    else
        timeline_path = latest_file(output_root, 'frame_timeline_*.csv');
    end
    if ~isempty(timeline_path)
        timeline = readtable(timeline_path, 'VariableNamingRule', 'preserve');
        if ismember('GlobalFrame', timeline.Properties.VariableNames)
            timeline.GlobalFrame = double(timeline.GlobalFrame);
            [lia, loc] = ismember(selected.FrameIndex, timeline.GlobalFrame);
            TifFile = repmat({''}, height(selected), 1);
            PageInTif = NaN(height(selected), 1);
            RealTime_s = NaN(height(selected), 1);
            Interval_s = NaN(height(selected), 1);
            TifPath = repmat({''}, height(selected), 1);
            if any(lia)
                if ismember('TifFile', timeline.Properties.VariableNames)
                    tif_values = table_text_column(timeline, 'TifFile');
                    TifFile(lia) = tif_values(loc(lia));
                end
                if ismember('PageInTif', timeline.Properties.VariableNames)
                    PageInTif(lia) = double(timeline.PageInTif(loc(lia)));
                end
                if ismember('RealTime_s', timeline.Properties.VariableNames)
                    RealTime_s(lia) = double(timeline.RealTime_s(loc(lia)));
                end
                if ismember('Interval_s', timeline.Properties.VariableNames)
                    Interval_s(lia) = double(timeline.Interval_s(loc(lia)));
                end
                if ismember('TifPath', timeline.Properties.VariableNames)
                    tif_paths = table_text_column(timeline, 'TifPath');
                    TifPath(lia) = tif_paths(loc(lia));
                end
            end
            selected.TifFile = TifFile;
            selected.PageInTif = PageInTif;
            selected.RealTime_s = RealTime_s;
            selected.Interval_s = Interval_s;
            selected.TifPath = TifPath;
        end
    end
    if ~ismember('TifFile', selected.Properties.VariableNames)
        selected.TifFile = repmat({''}, height(selected), 1);
        selected.PageInTif = NaN(height(selected), 1);
        selected.RealTime_s = NaN(height(selected), 1);
        selected.Interval_s = NaN(height(selected), 1);
        selected.TifPath = repmat({''}, height(selected), 1);
    end
    TifPath = table_text_column(selected, 'TifPath');
    for i = 1:height(selected)
        if ~isempty(TifPath{i})
            continue;
        elseif isempty(selected.TifFile{i})
            TifPath{i} = '';
        elseif is_absolute_path(selected.TifFile{i})
            TifPath{i} = selected.TifFile{i};
        else
            TifPath{i} = fullfile(raw_image_dir, selected.TifFile{i});
        end
    end
    selected.TifPath = TifPath;
end


function selected = read_explicit_selected_frames(selected_frames_csv, max_frames)
    if ~isfile(selected_frames_csv)
        error('run_geometry_sample_validation:missingSelectedFramesCsv', ...
            'SelectedFramesCsv not found: %s', selected_frames_csv);
    end
    selected = readtable(selected_frames_csv, 'VariableNamingRule', 'preserve');
    if ~ismember('FrameIndex', selected.Properties.VariableNames)
        error('run_geometry_sample_validation:missingFrameIndex', ...
            'SelectedFramesCsv must contain FrameIndex.');
    end
    selected.FrameIndex = double(selected.FrameIndex);
    selected = selected(isfinite(selected.FrameIndex), :);
    [~, ia] = unique(selected.FrameIndex, 'stable');
    selected = selected(sort(ia), :);
    if height(selected) == 0
        error('run_geometry_sample_validation:emptySelectedFrames', ...
            'SelectedFramesCsv contains no valid FrameIndex values.');
    end
    if height(selected) > max_frames
        error('run_geometry_sample_validation:tooManySelectedFrames', ...
            'SelectedFramesCsv has %d frames, exceeding MaxFrames=%d.', height(selected), max_frames);
    end
end


function ids = stratified_frame_ids(rates, max_frames)
    stages = unique(rates.Stage, 'stable');
    stages = stages(~cellfun(@isempty, stages));
    if isempty(stages)
        stages = {'unknown'};
    end
    per_stage = max(1, floor(max_frames * 0.75 / numel(stages)));
    ids = [];
    for s = 1:numel(stages)
        idx = find(strcmp(rates.Stage, stages{s}));
        if isempty(idx)
            continue;
        end
        take = min(per_stage, numel(idx));
        q = unique(round(linspace(1, numel(idx), take)));
        ids = [ids; rates.FrameIndex(idx(q))]; %#ok<AGROW>
    end

    rate = double(rates.DissolutionRate_Sn_per_min);
    finite = find(isfinite(rate));
    if ~isempty(finite)
        [~, order] = sort(rate(finite), 'descend');
        n_top = min(max_frames - numel(unique(ids)), numel(order));
        if n_top > 0
            ids = [ids; rates.FrameIndex(finite(order(1:n_top)))]; %#ok<AGROW>
        end
    end
    if isempty(ids)
        ids = rates.FrameIndex(1:min(max_frames, height(rates)));
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


function [present, missing_frames] = mask_coverage_for_selected(mask_dir, frame_indices)
    present = false(size(frame_indices));
    missing_frames = [];
    if isempty(mask_dir) || ~isfolder(mask_dir)
        missing_frames = frame_indices(:);
        return;
    end
    for i = 1:numel(frame_indices)
        present(i) = ~isempty(find_mask_path(mask_dir, frame_indices(i)));
    end
    missing_frames = frame_indices(~present);
end


function preflight = make_preflight_table(metadata_exists, raw_image_dir, mask_dir, has_any_masks, has_all_masks, missing_mask_frames, can_segment_raw)
    Check = {'metadata_json_exists'; 'raw_image_dir_exists'; 'mask_dir_has_selected_masks'; ...
        'mask_dir_has_all_selected_masks'; 'missing_mask_frames'; 'raw_segmentation_context_safe'; 'decision'};
    Passed = [metadata_exists; isfolder(raw_image_dir); has_any_masks; has_all_masks; isempty(missing_mask_frames); ...
        can_segment_raw; has_any_masks || can_segment_raw];
    Details = {
        bool_detail(metadata_exists, 'metadata JSON is readable', 'metadata JSON missing; geometry can still be audited in pixel units');
        bool_detail(isfolder(raw_image_dir), 'raw image directory exists', 'raw image directory missing');
        bool_detail(has_any_masks, 'at least one selected-frame validation mask was found', 'no validation masks for selected frames');
        bool_detail(has_all_masks, 'validation masks cover all selected frames', 'validation masks cover only part of the selected frames');
        join_frame_list(missing_mask_frames);
        bool_detail(can_segment_raw, 'raw segmentation context is safe', 'raw-frame segmentation is not attempted without recovered crop/flow-domain/threshold context');
        bool_detail(has_any_masks || can_segment_raw, 'geometry extraction can proceed for available masks', 'stopping before segmentation to avoid unsafe partial rerun')
        };
    preflight = table(Check, Passed, Details);
end


function text = join_frame_list(frame_indices)
    if isempty(frame_indices)
        text = '';
        return;
    end
    frame_indices = frame_indices(:)';
    parts = cell(1, numel(frame_indices));
    for i = 1:numel(frame_indices)
        parts{i} = sprintf('%d', frame_indices(i));
    end
    text = strjoin(parts, ';');
end


function text = bool_detail(flag, yes_text, no_text)
    if flag
        text = yes_text;
    else
        text = no_text;
    end
end


function blob_table = compute_geometry_from_masks(selected, mask_dir, qc_dir)
    rows = {};
    for i = 1:height(selected)
        frame_index = selected.FrameIndex(i);
        mask_path = find_mask_path(mask_dir, frame_index);
        if isempty(mask_path)
            continue;
        end
        mask = imread(mask_path);
        if size(mask, 3) > 1
            mask = mask(:, :, 1);
        end
        mask = mask > 0;
        rows = [rows; geometry_rows_for_frame(mask, frame_index, mask_path)]; %#ok<AGROW>
        write_qc_image(qc_dir, frame_index, mask);
    end
    blob_table = rows_to_blob_table(rows);
end


function blob_table = compute_geometry_from_raw_context(selected, output_root, output_dir, qc_dir)
    mask_dir = fullfile(output_dir, 'validation_masks');
    if ~isfolder(mask_dir)
        mkdir(mask_dir);
    end
    context = load_raw_segmentation_context(output_root);
    rows = {};
    for i = 1:height(selected)
        frame_index = selected.FrameIndex(i);
        if isempty(selected.TifPath{i}) || ~isfile(selected.TifPath{i}) || ~isfinite(selected.PageInTif(i))
            continue;
        end
        mask = segment_selected_raw_frame(selected.TifPath{i}, selected.PageInTif(i), context);
        mask_path = fullfile(mask_dir, sprintf('frame_%06d_validation_mask.tif', frame_index));
        imwrite(uint8(mask) * 255, mask_path);
        rows = [rows; geometry_rows_for_frame(mask, frame_index, mask_path)]; %#ok<AGROW>
        write_qc_image(qc_dir, frame_index, mask);
    end
    blob_table = rows_to_blob_table(rows);
end


function context = load_raw_segmentation_context(output_root)
    results_path = latest_file(output_root, 'results_*.mat');
    if isempty(results_path)
        error('run_geometry_sample_validation:missingResultsMat', ...
            'No results_*.mat file found under %s.', output_root);
    end
    S = load(results_path, 'config', 'results');
    if ~isfield(S, 'config') || ~isfield(S, 'results')
        error('run_geometry_sample_validation:missingSegmentationContext', ...
            'results MAT must contain config and results variables.');
    end
    results = S.results;
    if ~isfield(results, 'flow_domain') || ~isfield(results, 'solid_mask')
        error('run_geometry_sample_validation:missingFlowDomain', ...
            'results.flow_domain and results.solid_mask are required for raw validation.');
    end
    config = S.config;
    config = apply_recorded_preprocessing_context(config, results);
    if isfield(results, 'segmentation') && isfield(results.segmentation, 'info') && ...
            isfield(results.segmentation.info, 'threshold')
        config.segmentation.fixed_threshold = results.segmentation.info.threshold;
    elseif ~(isfield(config, 'segmentation') && isfield(config.segmentation, 'fixed_threshold'))
        error('run_geometry_sample_validation:missingThreshold', ...
            'No locked segmentation threshold found in results.segmentation.info.threshold.');
    end
    if isfield(config, 'parallel') && isfield(config.parallel, 'use_gpu')
        config.parallel.use_gpu = false;
    end
    context = struct();
    context.config = config;
    context.flow_domain = logical(results.flow_domain);
    context.fd_size = [size(context.flow_domain, 1), size(context.flow_domain, 2)];
end


function config = apply_recorded_preprocessing_context(config, results)
    if ~isfield(config, 'preprocess') || ~isstruct(config.preprocess)
        config.preprocess = struct();
    end
    if isfield(results, 'preprocessing') && isstruct(results.preprocessing)
        preprocessing = results.preprocessing;
        if isfield(preprocessing, 'crop_rect') && isnumeric(preprocessing.crop_rect) && ...
                numel(preprocessing.crop_rect) == 4
            config.preprocess.saved_crop_rect = double(preprocessing.crop_rect);
            config.preprocess.manual_crop_rect = double(preprocessing.crop_rect);
        end
        if isfield(preprocessing, 'rotation_angle') && isnumeric(preprocessing.rotation_angle) && ...
                isscalar(preprocessing.rotation_angle)
            config.preprocess.rotation_angle = double(preprocessing.rotation_angle);
        end
    end
    if ~isfield(config.preprocess, 'rotation_angle') || isempty(config.preprocess.rotation_angle)
        config.preprocess.rotation_angle = 0;
    end
    if isfield(config, 'illumination') && isfield(config.illumination, 'method') && ...
            strcmpi(char(config.illumination.method), 'morphological') && ...
            isfield(config.illumination, 'kernel_size') && ...
            ~(isnumeric(config.illumination.kernel_size) && isscalar(config.illumination.kernel_size))
        error('run_geometry_sample_validation:unsafeIlluminationContext', ...
            'Validation requires a numeric illumination.kernel_size; interactive settings are not safe.');
    end
end


function mask = segment_selected_raw_frame(tif_path, page_in_tif, context)
    rgb = imread(tif_path, max(1, round(page_in_tif)));
    if size(rgb, 3) == 1
        rgb = repmat(rgb, [1 1 3]);
    end
    [rgb_rot, ~, ~] = rotate_and_crop(rgb, context.config);
    if isfield(context.config, 'illumination') && isfield(context.config.illumination, 'method')
        [rgb_corr, ~] = correct_illumination(rgb_rot, ...
            context.config.illumination.method, context.config.illumination, false);
    else
        rgb_corr = rgb_rot;
    end
    if size(rgb_corr, 1) ~= context.fd_size(1) || size(rgb_corr, 2) ~= context.fd_size(2)
        rgb_corr = imresize(rgb_corr, context.fd_size);
    end
    if endsWith(context.config.segmentation.method, '_v2')
        [mask, ~, ~] = segment_DNAPL_v2(rgb_corr, context.flow_domain, context.config);
    else
        [mask, ~, ~] = segment_DNAPL(rgb_corr, context.flow_domain, context.config);
    end
    if size(mask, 1) ~= context.fd_size(1) || size(mask, 2) ~= context.fd_size(2)
        mask = imresize(mask, context.fd_size) > 0;
    end
    mask = logical(mask) & context.flow_domain;
end


function mask_path = find_mask_path(mask_dir, frame_index)
    candidates = {
        fullfile(mask_dir, sprintf('frame_%06d_mask.png', frame_index));
        fullfile(mask_dir, sprintf('frame_%04d_mask.png', frame_index));
        fullfile(mask_dir, sprintf('frame_%d_mask.png', frame_index));
        fullfile(mask_dir, sprintf('mask_%06d.png', frame_index));
        fullfile(mask_dir, sprintf('mask_%04d.png', frame_index));
        fullfile(mask_dir, sprintf('mask_%d.png', frame_index))
        };
    exts = {'.png', '.tif', '.tiff', '.bmp'};
    for i = 1:numel(candidates)
        [folder, stem, ~] = fileparts(candidates{i});
        for e = 1:numel(exts)
            path = fullfile(folder, [stem exts{e}]);
            if isfile(path)
                mask_path = path;
                return;
            end
        end
    end
    mask_path = '';
end


function rows = geometry_rows_for_frame(mask, frame_index, mask_path)
    cc = bwconncomp(mask, 8);
    props = regionprops(cc, 'Area', 'Perimeter', 'Centroid', 'BoundingBox', ...
        'MajorAxisLength', 'MinorAxisLength', 'Orientation', 'ConvexArea', ...
        'Solidity', 'EquivDiameter');
    rows = cell(numel(props), 1);
    for k = 1:numel(props)
        blob_mask = false(size(mask));
        blob_mask(cc.PixelIdxList{k}) = true;
        [boundary_available, convex_perimeter] = convex_perimeter_from_mask(blob_mask);
        area = props(k).Area;
        perimeter = props(k).Perimeter;
        circularity = 4 * pi * area / max(perimeter^2, eps);
        aspect_ratio = props(k).MajorAxisLength / max(props(k).MinorAxisLength, eps);
        projected_roughness = perimeter / max(convex_perimeter, eps);
        rows{k} = {frame_index, k, area, perimeter, props(k).MajorAxisLength, ...
            props(k).MinorAxisLength, props(k).Orientation, props(k).ConvexArea, ...
            convex_perimeter, boundary_available, projected_roughness, circularity, ...
            aspect_ratio, props(k).Solidity, mask_path};
    end
end


function [boundary_available, convex_perimeter] = convex_perimeter_from_mask(blob_mask)
    boundaries = bwboundaries(blob_mask, 8, 'noholes');
    boundary_available = ~isempty(boundaries);
    convex_perimeter = NaN;
    if ~boundary_available
        return;
    end
    boundary = boundaries{1};
    if size(boundary, 1) < 3
        convex_perimeter = 0;
        return;
    end
    x = boundary(:, 2);
    y = boundary(:, 1);
    try
        hull_idx = convhull(x, y);
        dx = diff(x(hull_idx));
        dy = diff(y(hull_idx));
        convex_perimeter = sum(sqrt(dx.^2 + dy.^2));
    catch
        convex_perimeter = NaN;
    end
end


function T = rows_to_blob_table(rows)
    if isempty(rows)
        T = empty_blob_table();
        return;
    end
    data = vertcat(rows{:});
    FrameIndex = cell2mat(data(:, 1));
    BlobID = cell2mat(data(:, 2));
    Area = cell2mat(data(:, 3));
    Perimeter = cell2mat(data(:, 4));
    MajorAxisLength = cell2mat(data(:, 5));
    MinorAxisLength = cell2mat(data(:, 6));
    Orientation = cell2mat(data(:, 7));
    ConvexArea = cell2mat(data(:, 8));
    ConvexPerimeter = cell2mat(data(:, 9));
    BoundaryAvailable = cell2mat(data(:, 10));
    ProjectedRoughness = cell2mat(data(:, 11));
    Circularity2D = cell2mat(data(:, 12));
    AspectRatio = cell2mat(data(:, 13));
    Solidity = cell2mat(data(:, 14));
    MaskPath = data(:, 15);
    T = table(FrameIndex, BlobID, Area, Perimeter, MajorAxisLength, MinorAxisLength, ...
        Orientation, ConvexArea, ConvexPerimeter, BoundaryAvailable, ProjectedRoughness, ...
        Circularity2D, AspectRatio, Solidity, MaskPath);
end


function T = empty_blob_table()
    FrameIndex = zeros(0, 1);
    BlobID = zeros(0, 1);
    Area = zeros(0, 1);
    Perimeter = zeros(0, 1);
    MajorAxisLength = zeros(0, 1);
    MinorAxisLength = zeros(0, 1);
    Orientation = zeros(0, 1);
    ConvexArea = zeros(0, 1);
    ConvexPerimeter = zeros(0, 1);
    BoundaryAvailable = false(0, 1);
    ProjectedRoughness = zeros(0, 1);
    Circularity2D = zeros(0, 1);
    AspectRatio = zeros(0, 1);
    Solidity = zeros(0, 1);
    MaskPath = cell(0, 1);
    T = table(FrameIndex, BlobID, Area, Perimeter, MajorAxisLength, MinorAxisLength, ...
        Orientation, ConvexArea, ConvexPerimeter, BoundaryAvailable, ProjectedRoughness, ...
        Circularity2D, AspectRatio, Solidity, MaskPath);
end


function comparison = compare_to_existing_level_a(output_root, selected, blob_table, status)
    existing_path = fullfile(output_root, 'blob_detail_all_frames.csv');
    FrameIndex = selected.FrameIndex;
    ExistingBlobCount = NaN(height(selected), 1);
    GeneratedBlobCount = NaN(height(selected), 1);
    BlobCountRelativeDiff = NaN(height(selected), 1);
    BlobCountPass = false(height(selected), 1);
    ExistingTotalArea = NaN(height(selected), 1);
    GeneratedTotalArea = NaN(height(selected), 1);
    TotalAreaRelativeDiff = NaN(height(selected), 1);
    TotalAreaPass = false(height(selected), 1);
    Notes = repmat({''}, height(selected), 1);

    if strcmp(status, 'PRECHECK_FAILED')
        Notes(:) = {'not_applicable_no_generated_geometry'};
        comparison = table(FrameIndex, ExistingBlobCount, GeneratedBlobCount, BlobCountRelativeDiff, ...
            BlobCountPass, ExistingTotalArea, GeneratedTotalArea, TotalAreaRelativeDiff, TotalAreaPass, Notes);
        return;
    end

    if ~isfile(existing_path)
        Notes(:) = {'blob_detail_all_frames.csv not found'};
        comparison = table(FrameIndex, ExistingBlobCount, GeneratedBlobCount, BlobCountRelativeDiff, ...
            BlobCountPass, ExistingTotalArea, GeneratedTotalArea, TotalAreaRelativeDiff, TotalAreaPass, Notes);
        return;
    end

    try
        [ok, counts, areas, message] = summarize_existing_blob_csv(existing_path, FrameIndex);
    catch ME
        ok = false;
        counts = NaN(size(FrameIndex));
        areas = NaN(size(FrameIndex));
        message = ['could not read blob CSV: ' ME.message];
    end
    if ~ok
        Notes(:) = {message};
        comparison = table(FrameIndex, ExistingBlobCount, GeneratedBlobCount, BlobCountRelativeDiff, ...
            BlobCountPass, ExistingTotalArea, GeneratedTotalArea, TotalAreaRelativeDiff, TotalAreaPass, Notes);
        return;
    end

    for i = 1:numel(FrameIndex)
        f = FrameIndex(i);
        generated_rows = blob_table(blob_table.FrameIndex == f, :);
        ExistingBlobCount(i) = counts(i);
        GeneratedBlobCount(i) = height(generated_rows);
        ExistingTotalArea(i) = areas(i);
        GeneratedTotalArea(i) = sum(generated_rows.Area);
        BlobCountRelativeDiff(i) = relative_diff(GeneratedBlobCount(i), ExistingBlobCount(i));
        TotalAreaRelativeDiff(i) = relative_diff(GeneratedTotalArea(i), ExistingTotalArea(i));
        BlobCountPass(i) = BlobCountRelativeDiff(i) <= 0.10;
        TotalAreaPass(i) = TotalAreaRelativeDiff(i) <= 0.05;
        if isempty(generated_rows)
            Notes{i} = 'no generated geometry for frame';
        elseif BlobCountPass(i) && TotalAreaPass(i)
            Notes{i} = 'within acceptance thresholds';
        else
            Notes{i} = 'validation mismatch exceeds threshold';
        end
    end
    comparison = table(FrameIndex, ExistingBlobCount, GeneratedBlobCount, BlobCountRelativeDiff, ...
        BlobCountPass, ExistingTotalArea, GeneratedTotalArea, TotalAreaRelativeDiff, TotalAreaPass, Notes);
end


function [ok, counts, areas, message] = summarize_existing_blob_csv(existing_path, frame_indices)
    ok = true;
    message = '';
    counts = zeros(size(frame_indices));
    areas = zeros(size(frame_indices));

    try
        ds = tabularTextDatastore(existing_path, 'SelectedVariableNames', {'FrameIndex', 'Area'});
        while hasdata(ds)
            chunk = read(ds);
            [counts, areas] = accumulate_blob_summary(chunk, frame_indices, counts, areas);
        end
    catch
        try
            opts = detectImportOptions(existing_path, 'VariableNamingRule', 'preserve');
            opts.SelectedVariableNames = {'FrameIndex', 'Area'};
            chunk = readtable(existing_path, opts);
            [counts, areas] = accumulate_blob_summary(chunk, frame_indices, counts, areas);
        catch ME
            ok = false;
            message = ['blob CSV lacks readable FrameIndex/Area columns: ' ME.message];
            counts(:) = NaN;
            areas(:) = NaN;
        end
    end
end


function [counts, areas] = accumulate_blob_summary(chunk, frame_indices, counts, areas)
    if ~ismember('FrameIndex', chunk.Properties.VariableNames) || ~ismember('Area', chunk.Properties.VariableNames)
        error('run_geometry_sample_validation:badBlobCsvSchema', 'Missing FrameIndex or Area column.');
    end
    frame_col = double(chunk.FrameIndex);
    area_col = double(chunk.Area);
    for i = 1:numel(frame_indices)
        idx = frame_col == frame_indices(i);
        if any(idx)
            counts(i) = counts(i) + sum(idx);
            areas(i) = areas(i) + sum(area_col(idx));
        end
    end
end


function d = relative_diff(value, reference)
    if ~isfinite(value) || ~isfinite(reference)
        d = NaN;
    elseif reference == 0
        d = double(value ~= 0);
    else
        d = abs(value - reference) / max(abs(reference), eps);
    end
end


function availability = build_metric_availability(blob_table, has_masks, status)
    Metric = {'MajorAxisLength'; 'MinorAxisLength'; 'Orientation'; 'ConvexArea'; ...
        'ConvexPerimeter'; 'BoundaryAvailable'; 'ProjectedRoughness'};
    Available = false(numel(Metric), 1);
    for i = 1:numel(Metric)
        Available(i) = has_masks && height(blob_table) > 0 && ismember(Metric{i}, blob_table.Properties.VariableNames);
    end
    Status = repmat({status}, numel(Metric), 1);
    Notes = repmat({''}, numel(Metric), 1);
    for i = 1:numel(Metric)
        if Available(i)
            Notes{i} = 'computed from validation masks';
        else
            Notes{i} = 'not computed; requires masks or safe segmentation context';
        end
    end
    availability = table(Metric, Available, Status, Notes);
end


function write_qc_image(qc_dir, frame_index, mask)
    rgb = zeros([size(mask), 3], 'uint8');
    rgb(:, :, 1) = uint8(mask) * 255;
    rgb(:, :, 2) = uint8(mask) * 80;
    path = fullfile(qc_dir, sprintf('frame_%06d_overlay.png', frame_index));
    imwrite(rgb, path);
end


function write_report(path, status, selected, preflight, blob_table, comparison)
    fid = fopen(path, 'w');
    if fid < 0
        error('run_geometry_sample_validation:reportWriteFailed', 'Could not write report: %s', path);
    end
    cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, '# Geometry Sample Validation Report\n\n');
    fprintf(fid, '## Summary\n');
    fprintf(fid, '- status: `%s`\n', status);
    fprintf(fid, '- selected frames: %d\n', height(selected));
    fprintf(fid, '- generated blob rows: %d\n\n', height(blob_table));
    fprintf(fid, '## Preflight\n');
    for i = 1:height(preflight)
        fprintf(fid, '- `%s`: %d - %s\n', preflight.Check{i}, preflight.Passed(i), preflight.Details{i});
    end
    fprintf(fid, '\n## Level A Agreement\n');
    if isempty(comparison) || height(comparison) == 0
        fprintf(fid, '- no comparison rows available\n');
    elseif strcmp(status, 'PRECHECK_FAILED')
        fprintf(fid, '- not applicable: geometry extraction did not run\n');
    else
        n_count_pass = sum(comparison.BlobCountPass);
        n_area_pass = sum(comparison.TotalAreaPass);
        fprintf(fid, '- Blob count pass frames: %d / %d\n', n_count_pass, height(comparison));
        fprintf(fid, '- Total area pass frames: %d / %d\n', n_area_pass, height(comparison));
    end
    fprintf(fid, '\n## Limits\n');
    fprintf(fid, '- This validation does not run full segmentation or Step 4.\n');
    fprintf(fid, '- Boundary fractal dimension and tracking are not computed.\n');
    fprintf(fid, '- Passing this check only supports a later limited geometry extraction plan.\n');
end
