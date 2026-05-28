function result = run_geometry_sidecar_extraction(output_root, postprocess_dir, varargin)
% RUN_GEOMETRY_SIDECAR_EXTRACTION  Manual-gated sidecar geometry entrypoint.
%
% This entrypoint is intentionally conservative. It validates the selected
% frame v2 gate and can write a dry-run provenance bundle. Full extraction is
% blocked unless the caller explicitly confirms the manual gate in a later run.

    parser = inputParser;
    parser.addRequired('output_root', @(x) ischar(x) || isstring(x));
    parser.addRequired('postprocess_dir', @(x) ischar(x) || isstring(x));
    parser.addParameter('SegmentationContextAuditDir', '', @(x) ischar(x) || isstring(x));
    parser.addParameter('MetadataJson', '', @(x) ischar(x) || isstring(x));
    parser.addParameter('RawImageDir', '', @(x) ischar(x) || isstring(x));
    parser.addParameter('FrameTimelineCsv', '', @(x) ischar(x) || isstring(x));
    parser.addParameter('ValidationV2Dir', '', @(x) ischar(x) || isstring(x));
    parser.addParameter('MaxFrames', inf, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('FrameIndices', [], @(x) isnumeric(x));
    parser.addParameter('WriteMasks', true, @(x) islogical(x) || isnumeric(x));
    parser.addParameter('WriteLabels', [], @(x) isempty(x) || islogical(x) || isnumeric(x));
    parser.addParameter('WriteQCImages', true, @(x) islogical(x) || isnumeric(x));
    parser.addParameter('QCImageStride', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('PartFrameSize', 100, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('AllowInitialFrameAreaMismatch', true, @(x) islogical(x) || isnumeric(x));
    parser.addParameter('InitialFrameIndex', 1, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('OutputDir', '', @(x) ischar(x) || isstring(x));
    parser.addParameter('Overwrite', false, @(x) islogical(x) || isnumeric(x));
    parser.addParameter('DryRun', false, @(x) islogical(x) || isnumeric(x));
    parser.addParameter('ConfirmFullRun', false, @(x) islogical(x) || isnumeric(x));
    parser.parse(output_root, postprocess_dir, varargin{:});
    opts = normalize_options(parser.Results);

    output_root = char(output_root);
    postprocess_dir = char(postprocess_dir);
    assert(isfolder(output_root), 'run_geometry_sidecar_extraction:missingOutputRoot', ...
        'output_root does not exist: %s', output_root);
    assert(isfolder(postprocess_dir), 'run_geometry_sidecar_extraction:missingPostprocessDir', ...
        'postprocess_dir does not exist: %s', postprocess_dir);

    validation_v2_dir = char(opts.ValidationV2Dir);
    if isempty(validation_v2_dir)
        validation_v2_dir = latest_dir(postprocess_dir, 'geometry_sample_validation_v2_*');
    end
    gate = read_v2_gate(validation_v2_dir);
    if ~strcmp(gate.DecisionLabel, 'READY_FOR_FULL_SIDECAR')
        error('run_geometry_sidecar_extraction:v2GateNotReady', ...
            'Validation v2 gate is not ready: %s', gate.DecisionLabel);
    end

    output_dir = resolve_output_dir(postprocess_dir, opts.OutputDir, logical(opts.Overwrite));
    ensure_dir(fullfile(output_dir, 'mask_visualization'));
    ensure_dir(fullfile(output_dir, 'masks_or_labels'));
    write_backend_version_check(fullfile(output_dir, 'geometry_backend_version_check.md'), ...
        validation_v2_dir, output_dir);

    provenance = struct();
    provenance.output_root = output_root;
    provenance.postprocess_dir = postprocess_dir;
    provenance.validation_v2_dir = validation_v2_dir;
    provenance.segmentation_context_audit_dir = char(opts.SegmentationContextAuditDir);
    provenance.metadata_json = char(opts.MetadataJson);
    provenance.raw_image_dir = char(opts.RawImageDir);
    provenance.frame_timeline_csv = char(opts.FrameTimelineCsv);
    provenance.max_frames = opts.MaxFrames;
    provenance.frame_indices = opts.FrameIndices;
    provenance.write_masks = logical(opts.WriteMasks);
    provenance.write_labels = logical(opts.WriteLabels);
    provenance.write_qc_images = logical(opts.WriteQCImages);
    provenance.qc_image_stride = opts.QCImageStride;
    provenance.part_frame_size = opts.PartFrameSize;
    provenance.allow_initial_frame_area_mismatch = logical(opts.AllowInitialFrameAreaMismatch);
    provenance.initial_frame_index = opts.InitialFrameIndex;
    provenance.created_at = datestr(now, 30);
    provenance.manual_gate = 'selected-frame v2 READY_FOR_FULL_SIDECAR required';

    if logical(opts.DryRun)
        status = 'DRY_RUN_READY';
        write_placeholder_outputs(output_dir, provenance, status, gate);
    elseif ~logical(opts.ConfirmFullRun)
        status = 'MANUAL_GATE_REQUIRED';
        write_placeholder_outputs(output_dir, provenance, status, gate);
        error('run_geometry_sidecar_extraction:manualGateRequired', ...
            'Full sidecar extraction requires ConfirmFullRun=true after manual review.');
    else
        run_result = run_streaming_extraction(output_root, postprocess_dir, output_dir, opts, provenance, gate);
        status = run_result.Status;
    end

    result = struct();
    result.Status = status;
    result.OutputDir = output_dir;
    result.ValidationV2Decision = gate.DecisionLabel;
    if exist('run_result', 'var')
        result.ProcessedFrameCount = run_result.ProcessedFrameCount;
        result.GeometryBlobCount = run_result.GeometryBlobCount;
        result.Blocked = run_result.Blocked;
        result.CanProceedWithManualOverride = run_result.CanProceedWithManualOverride;
    end
end


function opts = normalize_options(opts)
    if isempty(opts.WriteLabels)
        opts.WriteLabels = opts.WriteMasks;
    end
    opts.WriteLabels = logical(opts.WriteLabels);
    opts.WriteMasks = logical(opts.WriteMasks);
    opts.WriteQCImages = logical(opts.WriteQCImages);
    opts.AllowInitialFrameAreaMismatch = logical(opts.AllowInitialFrameAreaMismatch);
    opts.InitialFrameIndex = double(opts.InitialFrameIndex);
    opts.PartFrameSize = max(1, floor(double(opts.PartFrameSize)));
    opts.FrameIndices = unique(double(opts.FrameIndices(:)), 'stable');
    if isempty(opts.QCImageStride)
        if ~isempty(opts.FrameIndices) || (isfinite(opts.MaxFrames) && opts.MaxFrames <= 100)
            opts.QCImageStride = 1;
        else
            opts.QCImageStride = 50;
        end
    else
        opts.QCImageStride = max(1, floor(double(opts.QCImageStride)));
    end
end


function result = run_streaming_extraction(output_root, postprocess_dir, output_dir, opts, provenance, gate)
    timeline = load_frame_timeline(output_root, char(opts.RawImageDir), char(opts.FrameTimelineCsv));
    timeline = select_timeline_rows(timeline, opts);
    context = load_raw_segmentation_context(output_root);

    qc_dir = fullfile(output_dir, 'mask_visualization');
    mask_dir = fullfile(output_dir, 'masks_or_labels');
    part_dir = fullfile(output_dir, 'parts');
    ensure_dir(part_dir);
    write_masks = logical(opts.WriteMasks);
    write_labels = logical(opts.WriteLabels);
    write_qc_images = logical(opts.WriteQCImages);
    qc_stride = opts.QCImageStride;
    part_frame_size = opts.PartFrameSize;

    part_blob_tables = {};
    part_infos = {};
    part_index = 1;
    part_start_frame = NaN;
    part_paths = {};
    blob_count_total = 0;
    boundary_valid_total = 0;
    frame_rows = cell(height(timeline), 1);
    comparison_rows = cell(height(timeline), 1);
    all_frame_indices = double(timeline.FrameIndex);

    [existing_ok, existing_counts, existing_areas, existing_message] = ...
        summarize_existing_blob_csv(fullfile(output_root, 'blob_detail_all_frames.csv'), all_frame_indices);

    for i = 1:height(timeline)
        frame_index = timeline.FrameIndex(i);
        try
            mask = segment_timeline_frame(timeline.TifPath{i}, timeline.PageInTif(i), context);
            [blob_table, label_image] = geometry_table_from_mask(mask, frame_index, timeline.RealTime_s(i), timeline.TifFile{i});
            mask_path = '';
            label_path = '';
            if write_masks
                mask_path = fullfile(mask_dir, sprintf('frame_%06d_mask.tif', frame_index));
                imwrite(uint8(mask) * 255, mask_path);
            end
            if write_labels
                label_path = fullfile(mask_dir, sprintf('frame_%06d_labels.tif', frame_index));
                imwrite(uint16(label_image), label_path);
            end
            if write_qc_images && mod(i - 1, qc_stride) == 0
                write_qc_image(qc_dir, frame_index, mask);
            end
            if height(blob_table) > 0
                blob_table.MaskPath = repmat({mask_path}, height(blob_table), 1);
                blob_table.LabelPath = repmat({label_path}, height(blob_table), 1);
            end
            if isempty(part_blob_tables)
                part_start_frame = frame_index;
            end
            part_blob_tables{end+1, 1} = blob_table; %#ok<AGROW>
            blob_count_total = blob_count_total + height(blob_table);
            boundary_valid_total = boundary_valid_total + sum(blob_table.BoundaryMetricValid);
            frame_rows{i} = summarize_geometry_frame(blob_table, frame_index, timeline.RealTime_s(i));
            if existing_ok
                comparison_rows{i} = compare_frame_to_existing(blob_table, frame_index, ...
                    existing_counts(i), existing_areas(i), '');
            else
                comparison_rows{i} = compare_frame_to_existing(blob_table, frame_index, ...
                    NaN, NaN, existing_message);
            end
        catch ME
            if isempty(part_blob_tables)
                part_start_frame = frame_index;
            end
            part_blob_tables{end+1, 1} = empty_geometry_by_blob(); %#ok<AGROW>
            frame_rows{i} = error_frame_summary(frame_index, timeline.RealTime_s(i), ME.message);
            comparison_rows{i} = compare_frame_to_existing(empty_geometry_by_blob(), frame_index, ...
                NaN, NaN, ME.message);
        end
        if mod(i, part_frame_size) == 0 || i == height(timeline)
            [part_path, part_info] = flush_blob_part(part_blob_tables, part_dir, ...
                part_index, part_start_frame, frame_index);
            part_paths{end+1, 1} = part_path; %#ok<AGROW>
            part_infos{end+1, 1} = part_info; %#ok<AGROW>
            part_blob_tables = {};
            part_index = part_index + 1;
            part_start_frame = NaN;
        end
    end

    geometry_summary = vertcat_tables(frame_rows);
    comparison = vertcat_tables(comparison_rows);
    discrepancy = build_discrepancy_all_frames(comparison, timeline, opts);
    cluster_summary = build_mismatch_cluster_summary(discrepancy, opts);
    qc = build_qc_summary(comparison, geometry_summary, blob_count_total, boundary_valid_total, opts, cluster_summary);

    combine_blob_part_csvs(part_paths, fullfile(output_dir, 'geometry_by_blob.csv'));
    writetable(part_manifest_table(part_infos), fullfile(output_dir, 'geometry_sidecar_manifest.csv'));
    writetable(geometry_summary, fullfile(output_dir, 'geometry_summary_by_frame.csv'));
    writetable(comparison, fullfile(output_dir, 'geometry_level_a_comparison_all_frames.csv'));
    writetable(discrepancy, fullfile(output_dir, 'geometry_discrepancy_diagnostics_all_frames.csv'));
    writetable(cluster_summary, fullfile(output_dir, 'geometry_mismatch_cluster_summary.csv'));
    writetable(qc, fullfile(output_dir, 'geometry_qc_summary.csv'));

    provenance.status = qc.Value{strcmp(qc.Metric, 'OverallStatus')};
    provenance.validation_v2_decision = gate.DecisionLabel;
    provenance.processed_frame_count = height(timeline);
    provenance.geometry_blob_count = blob_count_total;
    write_json(fullfile(output_dir, 'geometry_provenance.json'), provenance);
    write_extraction_report(fullfile(output_dir, 'geometry_extraction_report.md'), qc, height(timeline), blob_count_total);
    if height(timeline) == 100
        write_100_qc_review(fullfile(output_dir, 'geometry_sidecar_100_qc_review.md'), ...
            qc, comparison, part_infos, output_dir, opts);
    end

    result = struct();
    result.Status = provenance.status;
    result.ProcessedFrameCount = height(timeline);
    result.GeometryBlobCount = blob_count_total;
    result.Blocked = strcmp(qc.Value{strcmp(qc.Metric, 'BlockedForInterpretation')}, 'true');
    result.CanProceedWithManualOverride = strcmp(qc.Value{strcmp(qc.Metric, 'CanProceedWithManualOverride')}, 'true');
end


function [part_path, info] = flush_blob_part(part_blob_tables, part_dir, part_index, frame_start, frame_end)
    if isempty(part_blob_tables)
        T = empty_geometry_by_blob();
    else
        T = vertcat_geometry_tables(part_blob_tables);
    end
    part_path = fullfile(part_dir, sprintf('geometry_by_blob_part_%06d_%06d.csv', ...
        frame_start, frame_end));
    writetable(T, part_path);
    info = {part_index, frame_start, frame_end, height(T), part_path};
end


function T = vertcat_geometry_tables(tables)
    nonempty = tables(~cellfun(@isempty, tables));
    if isempty(nonempty)
        T = empty_geometry_by_blob();
        return;
    end
    T = vertcat(nonempty{:});
    if width(T) == 0
        T = empty_geometry_by_blob();
    end
end


function manifest = part_manifest_table(part_infos)
    if isempty(part_infos)
        PartIndex = zeros(0, 1);
        FrameStart = zeros(0, 1);
        FrameEnd = zeros(0, 1);
        RowCount = zeros(0, 1);
        Path = cell(0, 1);
    else
        data = vertcat(part_infos{:});
        PartIndex = cell2mat(data(:, 1));
        FrameStart = cell2mat(data(:, 2));
        FrameEnd = cell2mat(data(:, 3));
        RowCount = cell2mat(data(:, 4));
        Path = data(:, 5);
    end
    manifest = table(PartIndex, FrameStart, FrameEnd, RowCount, Path);
end


function combine_blob_part_csvs(part_paths, output_path)
    if isempty(part_paths)
        writetable(empty_geometry_by_blob(), output_path);
        return;
    end
    fid_out = fopen(output_path, 'w');
    if fid_out < 0
        error('run_geometry_sidecar_extraction:writeFailed', ...
            'Could not write %s.', output_path);
    end
    cleanup_out = onCleanup(@() fclose(fid_out)); %#ok<NASGU>
    wrote_header = false;
    for i = 1:numel(part_paths)
        fid_in = fopen(part_paths{i}, 'r');
        if fid_in < 0
            error('run_geometry_sidecar_extraction:readPartFailed', ...
                'Could not read %s.', part_paths{i});
        end
        cleanup_in = onCleanup(@() fclose(fid_in)); %#ok<NASGU>
        line = fgetl(fid_in);
        if ischar(line)
            if ~wrote_header
                fprintf(fid_out, '%s\n', line);
                wrote_header = true;
            end
            line = fgetl(fid_in);
        end
        while ischar(line)
            fprintf(fid_out, '%s\n', line);
            line = fgetl(fid_in);
        end
        clear cleanup_in;
    end
end


function timeline = select_timeline_rows(timeline, opts)
    if ~isempty(opts.FrameIndices)
        [found, loc] = ismember(opts.FrameIndices, double(timeline.FrameIndex));
        if any(~found)
            missing = opts.FrameIndices(~found);
            error('run_geometry_sidecar_extraction:missingFrameIndices', ...
                'Requested FrameIndices not found in frame timeline. First missing: %g', missing(1));
        end
        timeline = timeline(loc, :);
        return;
    end
    max_frames = opts.MaxFrames;
    if isfinite(max_frames)
        timeline = timeline(1:min(height(timeline), max(0, floor(max_frames))), :);
    end
end


function timeline = load_frame_timeline(output_root, raw_image_dir, frame_timeline_csv)
    frame_timeline_csv = char(frame_timeline_csv);
    if ~isempty(frame_timeline_csv)
        timeline_path = frame_timeline_csv;
    else
        timeline_path = latest_file(output_root, 'frame_timeline_*.csv');
    end
    if isempty(timeline_path)
        error('run_geometry_sidecar_extraction:missingFrameTimeline', ...
            'No frame_timeline_*.csv found under %s.', output_root);
    end
    if ~isfile(timeline_path)
        error('run_geometry_sidecar_extraction:missingFrameTimeline', ...
            'FrameTimelineCsv does not exist: %s', timeline_path);
    end
    T = readtable(timeline_path, 'VariableNamingRule', 'preserve');
    required = {'GlobalFrame', 'TifFile', 'PageInTif'};
    for i = 1:numel(required)
        if ~ismember(required{i}, T.Properties.VariableNames)
            error('run_geometry_sidecar_extraction:badFrameTimeline', ...
                'frame timeline missing column %s.', required{i});
        end
    end
    if isempty(raw_image_dir)
        raw_image_dir = fileparts(output_root);
    end
    FrameIndex = double(T.GlobalFrame);
    TifFile = table_text_column(T, 'TifFile');
    PageInTif = double(T.PageInTif);
    if ismember('RealTime_s', T.Properties.VariableNames)
        RealTime_s = double(T.RealTime_s);
    else
        RealTime_s = NaN(height(T), 1);
    end
    if ismember('Interval_s', T.Properties.VariableNames)
        Interval_s = double(T.Interval_s);
    else
        Interval_s = NaN(height(T), 1);
    end
    TifPath = cell(height(T), 1);
    for i = 1:height(T)
        TifPath{i} = fullfile(raw_image_dir, TifFile{i});
        if ~isfile(TifPath{i})
            error('run_geometry_sidecar_extraction:missingRawTif', ...
                'Raw TIF not found for frame %d: %s', FrameIndex(i), TifPath{i});
        end
    end
    timeline = table(FrameIndex, RealTime_s, Interval_s, TifFile, PageInTif, TifPath);
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


function context = load_raw_segmentation_context(output_root)
    results_path = latest_file(output_root, 'results_*.mat');
    if isempty(results_path)
        error('run_geometry_sidecar_extraction:missingResultsMat', ...
            'No results_*.mat file found under %s.', output_root);
    end
    S = load(results_path, 'config', 'results');
    if ~isfield(S, 'config') || ~isfield(S, 'results')
        error('run_geometry_sidecar_extraction:missingSegmentationContext', ...
            'results MAT must contain config and results variables.');
    end
    config = apply_recorded_preprocessing_context(S.config, S.results);
    if isfield(S.results, 'segmentation') && isfield(S.results.segmentation, 'info') && ...
            isfield(S.results.segmentation.info, 'threshold')
        config.segmentation.fixed_threshold = S.results.segmentation.info.threshold;
    elseif ~(isfield(config, 'segmentation') && isfield(config.segmentation, 'fixed_threshold'))
        error('run_geometry_sidecar_extraction:missingThreshold', ...
            'No locked segmentation threshold found in results.segmentation.info.threshold.');
    end
    if isfield(config, 'parallel')
        config.parallel.use_gpu = false;
    else
        config.parallel = struct('use_gpu', false);
    end
    if ~isfield(S.results, 'flow_domain')
        error('run_geometry_sidecar_extraction:missingFlowDomain', ...
            'results.flow_domain is required.');
    end
    context = struct();
    context.config = config;
    context.flow_domain = logical(S.results.flow_domain);
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
        error('run_geometry_sidecar_extraction:unsafeIlluminationContext', ...
            'Sidecar extraction requires a numeric illumination.kernel_size.');
    end
end


function mask = segment_timeline_frame(tif_path, page_in_tif, context)
    rgb = imread(tif_path, max(1, round(page_in_tif)));
    if isa(rgb, 'uint16')
        rgb = im2uint8(rgb);
    end
    if size(rgb, 3) == 1
        rgb = repmat(rgb, [1 1 3]);
    end
    rgb = prepare_rgb_input_encoding(rgb, context.config);
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


function [T, label_image] = geometry_table_from_mask(mask, frame_index, real_time_s, tif_file)
    cc = bwconncomp(mask, 8);
    label_image = labelmatrix(cc);
    props = regionprops(cc, 'Area', 'Perimeter', 'Centroid', 'BoundingBox', ...
        'MajorAxisLength', 'MinorAxisLength', 'Orientation', 'ConvexArea', ...
        'Solidity', 'Eccentricity', 'Extent');
    boundary_metrics = component_boundary_metrics(mask, cc);
    rows = cell(numel(props), 1);
    image_height = size(mask, 1);
    image_width = size(mask, 2);
    for k = 1:numel(props)
        boundary_available = boundary_metrics.available(k);
        p_outer = boundary_metrics.p_outer(k);
        pc_outer = boundary_metrics.pc_outer(k);
        p_total = boundary_metrics.p_total(k);
        boundary_points = boundary_metrics.points(k);
        area = props(k).Area;
        circularity_boundary = 4 * pi * area / max(p_outer ^ 2, eps);
        projected_roughness = p_outer / max(pc_outer, eps);
        area_tier = classify_area_tier(area);
        roughness_lt_one = isfinite(projected_roughness) && projected_roughness < (1 - 1e-9);
        circularity_gt = isfinite(circularity_boundary) && circularity_boundary > 1.05;
        boundary_valid = area >= 250 && boundary_available && isfinite(projected_roughness) && projected_roughness >= (1 - 1e-9);
        qc_flag = make_qc_flag(area_tier, roughness_lt_one, circularity_gt, boundary_available);
        bbox = props(k).BoundingBox;
        touches_border = bbox_touches_border(bbox, image_width, image_height, 10);
        rows{k} = {frame_index, real_time_s, k, tif_file, area, props(k).Centroid(1), ...
            props(k).Centroid(2), props(k).MajorAxisLength, props(k).MinorAxisLength, ...
            props(k).Orientation, props(k).ConvexArea, props(k).Solidity, ...
            props(k).Eccentricity, props(k).Extent, p_outer, pc_outer, p_total, ...
            projected_roughness, circularity_boundary, area_tier, boundary_available, ...
            boundary_valid, roughness_lt_one, circularity_gt, boundary_points, ...
            bbox(1), bbox(2), bbox(3), bbox(4), image_width, image_height, touches_border, qc_flag};
    end
    T = rows_to_geometry_table(rows);
end


function [boundary_available, p_outer, pc_outer, p_total, boundary_points] = boundary_perimeters(blob_mask)
    outer_boundaries = bwboundaries(blob_mask, 8, 'noholes');
    all_boundaries = bwboundaries(blob_mask, 8, 'holes');
    boundary_available = ~isempty(outer_boundaries);
    p_outer = NaN;
    pc_outer = NaN;
    p_total = NaN;
    boundary_points = 0;
    if ~boundary_available
        return;
    end
    lengths = cellfun(@(b) size(b, 1), outer_boundaries);
    [~, best] = max(lengths);
    boundary = outer_boundaries{best};
    boundary_points = size(boundary, 1);
    if boundary_points < 3
        p_outer = 0;
        pc_outer = 0;
        p_total = 0;
        return;
    end
    x = boundary(:, 2);
    y = boundary(:, 1);
    if x(1) ~= x(end) || y(1) ~= y(end)
        x_closed = [x; x(1)];
        y_closed = [y; y(1)];
    else
        x_closed = x;
        y_closed = y;
    end
    p_outer = sum(hypot(diff(x_closed), diff(y_closed)));
    p_total = 0;
    for i = 1:numel(all_boundaries)
        b = all_boundaries{i};
        xb = b(:, 2);
        yb = b(:, 1);
        if xb(1) ~= xb(end) || yb(1) ~= yb(end)
            xb = [xb; xb(1)]; %#ok<AGROW>
            yb = [yb; yb(1)]; %#ok<AGROW>
        end
        p_total = p_total + sum(hypot(diff(xb), diff(yb)));
    end
    try
        hull_idx = convhull(x, y);
        pc_outer = sum(hypot(diff(x(hull_idx)), diff(y(hull_idx))));
    catch
        pc_outer = NaN;
    end
end


function metrics = component_boundary_metrics(mask, cc)
    n = cc.NumObjects;
    metrics.available = false(n, 1);
    metrics.p_outer = NaN(n, 1);
    metrics.pc_outer = NaN(n, 1);
    metrics.p_total = zeros(n, 1);
    metrics.points = zeros(n, 1);
    if n == 0
        return;
    end

    label_image = labelmatrix(cc);
    outer_boundaries = bwboundaries(mask, 8, 'noholes');
    for i = 1:numel(outer_boundaries)
        boundary = outer_boundaries{i};
        label_id = boundary_component_label(label_image, boundary);
        if label_id < 1 || label_id > n
            continue;
        end
        boundary_points = size(boundary, 1);
        if metrics.available(label_id) && boundary_points <= metrics.points(label_id)
            continue;
        end
        [p_outer, pc_outer] = outer_boundary_perimeters(boundary);
        metrics.available(label_id) = true;
        metrics.p_outer(label_id) = p_outer;
        metrics.pc_outer(label_id) = pc_outer;
        metrics.points(label_id) = boundary_points;
    end

    all_boundaries = bwboundaries(mask, 8, 'holes');
    for i = 1:numel(all_boundaries)
        boundary = all_boundaries{i};
        label_id = boundary_component_label(label_image, boundary);
        if label_id < 1 || label_id > n
            continue;
        end
        metrics.p_total(label_id) = metrics.p_total(label_id) + boundary_path_length(boundary);
    end

    missing_total = metrics.available & metrics.p_total == 0;
    metrics.p_total(missing_total) = metrics.p_outer(missing_total);
end


function label_id = boundary_component_label(label_image, boundary)
    label_id = 0;
    if isempty(boundary)
        return;
    end
    h = size(label_image, 1);
    w = size(label_image, 2);
    r = min(max(round(boundary(:, 1)), 1), h);
    c = min(max(round(boundary(:, 2)), 1), w);
    vals = label_image(sub2ind(size(label_image), r, c));
    vals = vals(vals > 0);
    if isempty(vals)
        vals = [];
        for dr = -1:1
            for dc = -1:1
                rr = min(max(r + dr, 1), h);
                cc = min(max(c + dc, 1), w);
                nearby = label_image(sub2ind(size(label_image), rr, cc));
                vals = [vals; nearby(nearby > 0)]; %#ok<AGROW>
            end
        end
    end
    if ~isempty(vals)
        label_id = double(mode(double(vals)));
    end
end


function [p_outer, pc_outer] = outer_boundary_perimeters(boundary)
    p_outer = boundary_path_length(boundary);
    pc_outer = NaN;
    if size(boundary, 1) < 3
        pc_outer = p_outer;
        return;
    end
    x = boundary(:, 2);
    y = boundary(:, 1);
    try
        hull_idx = convhull(x, y);
        pc_outer = sum(hypot(diff(x(hull_idx)), diff(y(hull_idx))));
    catch
        pc_outer = NaN;
    end
end


function p = boundary_path_length(boundary)
    if isempty(boundary)
        p = 0;
        return;
    end
    x = boundary(:, 2);
    y = boundary(:, 1);
    if x(1) ~= x(end) || y(1) ~= y(end)
        x = [x; x(1)]; %#ok<AGROW>
        y = [y; y(1)]; %#ok<AGROW>
    end
    p = sum(hypot(diff(x), diff(y)));
end


function tier = classify_area_tier(area)
    if area < 20
        tier = 'tiny';
    elseif area < 100
        tier = 'small';
    elseif area < 250
        tier = 'medium';
    elseif area < 500
        tier = 'large';
    else
        tier = 'high_confidence';
    end
end


function flag = make_qc_flag(area_tier, roughness_lt_one, circularity_gt_one, boundary_available)
    parts = {};
    if ~boundary_available
        parts{end+1} = 'boundary_missing'; %#ok<AGROW>
    end
    if strcmp(area_tier, 'tiny')
        parts{end+1} = 'tiny_count_only'; %#ok<AGROW>
    elseif strcmp(area_tier, 'small')
        parts{end+1} = 'small_no_boundary_interpretation'; %#ok<AGROW>
    elseif strcmp(area_tier, 'medium')
        parts{end+1} = 'medium_boundary_caution'; %#ok<AGROW>
    end
    if roughness_lt_one
        parts{end+1} = 'roughness_lt_one'; %#ok<AGROW>
    end
    if circularity_gt_one
        parts{end+1} = 'circularity_gt_1p05'; %#ok<AGROW>
    end
    if isempty(parts)
        flag = 'ok';
    else
        flag = strjoin(parts, ';');
    end
end


function tf = bbox_touches_border(bbox, image_width, image_height, margin)
    xmin = bbox(1);
    ymin = bbox(2);
    xmax = bbox(1) + bbox(3);
    ymax = bbox(2) + bbox(4);
    tf = xmin <= margin || ymin <= margin || ...
        xmax >= (image_width - margin) || ymax >= (image_height - margin);
end


function T = rows_to_geometry_table(rows)
    if isempty(rows)
        T = empty_geometry_by_blob();
        return;
    end
    data = vertcat(rows{:});
    FrameIndex = cell2mat(data(:, 1));
    RealTime_s = cell2mat(data(:, 2));
    BlobID_sidecar = cell2mat(data(:, 3));
    TifFile = data(:, 4);
    Area_px = cell2mat(data(:, 5));
    CentroidX_px = cell2mat(data(:, 6));
    CentroidY_px = cell2mat(data(:, 7));
    MajorAxisLength_px = cell2mat(data(:, 8));
    MinorAxisLength_px = cell2mat(data(:, 9));
    Orientation_deg = cell2mat(data(:, 10));
    ConvexArea_px = cell2mat(data(:, 11));
    Solidity_geometry = cell2mat(data(:, 12));
    Eccentricity = cell2mat(data(:, 13));
    Extent = cell2mat(data(:, 14));
    P_outer_boundary = cell2mat(data(:, 15));
    Pc_outer_boundary = cell2mat(data(:, 16));
    P_total_boundary = cell2mat(data(:, 17));
    ProjectedRoughness_boundary = cell2mat(data(:, 18));
    Circularity2D_boundary = cell2mat(data(:, 19));
    AreaTier = data(:, 20);
    BoundaryAvailable = cell2mat(data(:, 21));
    BoundaryMetricValid = cell2mat(data(:, 22));
    RoughnessLessThanOne = cell2mat(data(:, 23));
    CircularityGreaterThan1p05 = cell2mat(data(:, 24));
    BoundaryPointCount = cell2mat(data(:, 25));
    BBoxX = cell2mat(data(:, 26));
    BBoxY = cell2mat(data(:, 27));
    BBoxWidth = cell2mat(data(:, 28));
    BBoxHeight = cell2mat(data(:, 29));
    ImageWidth = cell2mat(data(:, 30));
    ImageHeight = cell2mat(data(:, 31));
    TouchesImageBorder = cell2mat(data(:, 32));
    GeometryQCFlag = data(:, 33);
    MaskPath = repmat({''}, numel(FrameIndex), 1);
    LabelPath = repmat({''}, numel(FrameIndex), 1);
    T = table(FrameIndex, RealTime_s, BlobID_sidecar, TifFile, Area_px, ...
        CentroidX_px, CentroidY_px, MajorAxisLength_px, MinorAxisLength_px, ...
        Orientation_deg, ConvexArea_px, Solidity_geometry, Eccentricity, Extent, ...
        P_outer_boundary, Pc_outer_boundary, P_total_boundary, ...
        ProjectedRoughness_boundary, Circularity2D_boundary, AreaTier, ...
        BoundaryAvailable, BoundaryMetricValid, RoughnessLessThanOne, ...
        CircularityGreaterThan1p05, BoundaryPointCount, BBoxX, BBoxY, BBoxWidth, ...
        BBoxHeight, ImageWidth, ImageHeight, TouchesImageBorder, GeometryQCFlag, ...
        MaskPath, LabelPath);
end


function T = empty_geometry_by_blob()
    FrameIndex = zeros(0, 1);
    RealTime_s = zeros(0, 1);
    BlobID_sidecar = zeros(0, 1);
    TifFile = cell(0, 1);
    Area_px = zeros(0, 1);
    CentroidX_px = zeros(0, 1);
    CentroidY_px = zeros(0, 1);
    MajorAxisLength_px = zeros(0, 1);
    MinorAxisLength_px = zeros(0, 1);
    Orientation_deg = zeros(0, 1);
    ConvexArea_px = zeros(0, 1);
    Solidity_geometry = zeros(0, 1);
    Eccentricity = zeros(0, 1);
    Extent = zeros(0, 1);
    P_outer_boundary = zeros(0, 1);
    Pc_outer_boundary = zeros(0, 1);
    P_total_boundary = zeros(0, 1);
    ProjectedRoughness_boundary = zeros(0, 1);
    Circularity2D_boundary = zeros(0, 1);
    AreaTier = cell(0, 1);
    BoundaryAvailable = false(0, 1);
    BoundaryMetricValid = false(0, 1);
    RoughnessLessThanOne = false(0, 1);
    CircularityGreaterThan1p05 = false(0, 1);
    BoundaryPointCount = zeros(0, 1);
    BBoxX = zeros(0, 1);
    BBoxY = zeros(0, 1);
    BBoxWidth = zeros(0, 1);
    BBoxHeight = zeros(0, 1);
    ImageWidth = zeros(0, 1);
    ImageHeight = zeros(0, 1);
    TouchesImageBorder = false(0, 1);
    GeometryQCFlag = cell(0, 1);
    MaskPath = cell(0, 1);
    LabelPath = cell(0, 1);
    T = table(FrameIndex, RealTime_s, BlobID_sidecar, TifFile, Area_px, ...
        CentroidX_px, CentroidY_px, MajorAxisLength_px, MinorAxisLength_px, ...
        Orientation_deg, ConvexArea_px, Solidity_geometry, Eccentricity, Extent, ...
        P_outer_boundary, Pc_outer_boundary, P_total_boundary, ...
        ProjectedRoughness_boundary, Circularity2D_boundary, AreaTier, ...
        BoundaryAvailable, BoundaryMetricValid, RoughnessLessThanOne, ...
        CircularityGreaterThan1p05, BoundaryPointCount, BBoxX, BBoxY, BBoxWidth, ...
        BBoxHeight, ImageWidth, ImageHeight, TouchesImageBorder, GeometryQCFlag, ...
        MaskPath, LabelPath);
end


function frame_summary = summarize_geometry_frame(blob_table, frame_index, real_time_s)
    NGeometryBlobs = height(blob_table);
    NBoundaryMetricValid = sum(blob_table.BoundaryMetricValid);
    TotalArea_px = sum(blob_table.Area_px);
    if TotalArea_px > 0
        AreaFracBoundaryMetricValid = sum(blob_table.Area_px(blob_table.BoundaryMetricValid)) / TotalArea_px;
    else
        AreaFracBoundaryMetricValid = NaN;
    end
    valid = blob_table.BoundaryMetricValid & isfinite(blob_table.ProjectedRoughness_boundary);
    if any(valid)
        MedianProjectedRoughnessBoundary = median(blob_table.ProjectedRoughness_boundary(valid));
        AreaWeightedProjectedRoughnessBoundary = ...
            sum(blob_table.ProjectedRoughness_boundary(valid) .* blob_table.Area_px(valid)) / sum(blob_table.Area_px(valid));
    else
        MedianProjectedRoughnessBoundary = NaN;
        AreaWeightedProjectedRoughnessBoundary = NaN;
    end
    Status = {'ok'};
    Notes = {''};
    frame_summary = table(frame_index, real_time_s, NGeometryBlobs, TotalArea_px, ...
        NBoundaryMetricValid, AreaFracBoundaryMetricValid, MedianProjectedRoughnessBoundary, ...
        AreaWeightedProjectedRoughnessBoundary, Status, Notes, 'VariableNames', ...
        {'FrameIndex', 'RealTime_s', 'NGeometryBlobs', 'TotalArea_px', ...
        'NBoundaryMetricValid', 'AreaFracBoundaryMetricValid', ...
        'MedianProjectedRoughnessBoundary', 'AreaWeightedProjectedRoughnessBoundary', ...
        'Status', 'Notes'});
end


function frame_summary = error_frame_summary(frame_index, real_time_s, message)
    NGeometryBlobs = 0;
    TotalArea_px = 0;
    NBoundaryMetricValid = 0;
    AreaFracBoundaryMetricValid = NaN;
    MedianProjectedRoughnessBoundary = NaN;
    AreaWeightedProjectedRoughnessBoundary = NaN;
    Status = {'error'};
    Notes = {message};
    frame_summary = table(frame_index, real_time_s, NGeometryBlobs, TotalArea_px, ...
        NBoundaryMetricValid, AreaFracBoundaryMetricValid, MedianProjectedRoughnessBoundary, ...
        AreaWeightedProjectedRoughnessBoundary, Status, Notes, 'VariableNames', ...
        {'FrameIndex', 'RealTime_s', 'NGeometryBlobs', 'TotalArea_px', ...
        'NBoundaryMetricValid', 'AreaFracBoundaryMetricValid', ...
        'MedianProjectedRoughnessBoundary', 'AreaWeightedProjectedRoughnessBoundary', ...
        'Status', 'Notes'});
end


function comparison = compare_frame_to_existing(blob_table, frame_index, existing_count, existing_area, notes)
    GeneratedBlobCount = height(blob_table);
    GeneratedTotalArea = sum(blob_table.Area_px);
    BlobCountRelativeDiff = relative_diff(GeneratedBlobCount, existing_count);
    TotalAreaRelativeDiff = relative_diff(GeneratedTotalArea, existing_area);
    BlobCountPass = isfinite(BlobCountRelativeDiff) && BlobCountRelativeDiff <= 0.10;
    TotalAreaPass = isfinite(TotalAreaRelativeDiff) && TotalAreaRelativeDiff <= 0.05;
    if isempty(notes)
        if BlobCountPass && TotalAreaPass
            Notes = {'within acceptance thresholds'};
        else
            Notes = {'validation mismatch exceeds threshold'};
        end
    else
        Notes = {notes};
    end
    comparison = table(frame_index, existing_count, GeneratedBlobCount, ...
        BlobCountRelativeDiff, BlobCountPass, existing_area, GeneratedTotalArea, ...
        TotalAreaRelativeDiff, TotalAreaPass, Notes, 'VariableNames', ...
        {'FrameIndex', 'ExistingBlobCount', 'GeneratedBlobCount', ...
        'BlobCountRelativeDiff', 'BlobCountPass', 'ExistingTotalArea', ...
        'GeneratedTotalArea', 'TotalAreaRelativeDiff', 'TotalAreaPass', 'Notes'});
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


function [ok, counts, areas, message] = summarize_existing_blob_csv(existing_path, frame_indices)
    ok = true;
    message = '';
    counts = zeros(size(frame_indices));
    areas = zeros(size(frame_indices));
    if ~isfile(existing_path)
        ok = false;
        message = 'blob_detail_all_frames.csv not found';
        counts(:) = NaN;
        areas(:) = NaN;
        return;
    end
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
    frame_col = double(chunk.FrameIndex);
    area_col = double(chunk.Area);
    [tf, loc] = ismember(frame_col, frame_indices);
    valid = tf & loc > 0 & isfinite(area_col);
    if any(valid)
        counts = counts + accumarray(loc(valid), 1, size(counts), @sum, 0);
        areas = areas + accumarray(loc(valid), area_col(valid), size(areas), @sum, 0);
    end
end


function T = vertcat_tables(tables)
    nonempty = tables(~cellfun(@isempty, tables));
    if isempty(nonempty)
        T = table();
    else
        T = vertcat(nonempty{:});
    end
end


function discrepancy = build_discrepancy_all_frames(comparison, timeline, opts)
    SignedAreaDiff = comparison.GeneratedTotalArea - comparison.ExistingTotalArea;
    AreaDiffDirection = repmat({'unknown'}, height(comparison), 1);
    AreaDiffDirection(SignedAreaDiff < 0) = {'generated_less_than_existing'};
    AreaDiffDirection(SignedAreaDiff > 0) = {'generated_greater_than_existing'};
    QCDecision = repmat({'ACCEPT'}, height(comparison), 1);
    bad = (~comparison.BlobCountPass) | (~comparison.TotalAreaPass);
    QCDecision(bad) = {'REVIEW_MISMATCH'};
    initial_exempt = initial_frame_area_exempt(comparison, opts);
    QCDecision(initial_exempt) = {'ACCEPT_WITH_INITIAL_FRAME_NOTE'};
    Notes = comparison.Notes;
    FrameIndex = comparison.FrameIndex;
    [lia, loc] = ismember(FrameIndex, timeline.FrameIndex);
    TifFile = repmat({''}, height(comparison), 1);
    PageInTif = NaN(height(comparison), 1);
    TifFile(lia) = timeline.TifFile(loc(lia));
    PageInTif(lia) = timeline.PageInTif(loc(lia));
    ExistingBlobCount = comparison.ExistingBlobCount;
    GeneratedBlobCount = comparison.GeneratedBlobCount;
    BlobCountRelativeDiff = comparison.BlobCountRelativeDiff;
    ExistingTotalArea = comparison.ExistingTotalArea;
    GeneratedTotalArea = comparison.GeneratedTotalArea;
    TotalAreaRelativeDiff = comparison.TotalAreaRelativeDiff;
    discrepancy = table(FrameIndex, TifFile, PageInTif, ExistingBlobCount, ...
        GeneratedBlobCount, BlobCountRelativeDiff, ExistingTotalArea, ...
        GeneratedTotalArea, TotalAreaRelativeDiff, SignedAreaDiff, ...
        AreaDiffDirection, QCDecision, Notes);
end


function cluster_summary = build_mismatch_cluster_summary(discrepancy, opts)
    if height(discrepancy) == 0
        cluster_summary = empty_mismatch_cluster_summary();
        return;
    end
    tif_values = discrepancy.TifFile;
    unique_tifs = unique(tif_values, 'stable');
    rows = cell(numel(unique_tifs), 1);
    nonexempt_mismatch = strcmp(discrepancy.QCDecision, 'REVIEW_MISMATCH');
    for i = 1:numel(unique_tifs)
        idx = strcmp(tif_values, unique_tifs{i});
        n_frames = sum(idx);
        mismatch_idx = nonexempt_mismatch(idx);
        n_mismatch = sum(mismatch_idx);
        mismatch_fraction = n_mismatch / max(n_frames, 1);
        max_block = max_consecutive_true(mismatch_idx);
        review_required = n_mismatch > 0 && ...
            (max_block > 3 || n_mismatch >= 3);
        rows{i} = {unique_tifs{i}, n_frames, n_mismatch, mismatch_fraction, ...
            max_block, review_required};
    end
    data = vertcat(rows{:});
    TifFile = data(:, 1);
    NFrames = cell2mat(data(:, 2));
    NMismatchFrames = cell2mat(data(:, 3));
    MismatchFraction = cell2mat(data(:, 4));
    MaxConsecutiveMismatchWithinTif = cell2mat(data(:, 5));
    ReviewRequired = cell2mat(data(:, 6));
    cluster_summary = table(TifFile, NFrames, NMismatchFrames, MismatchFraction, ...
        MaxConsecutiveMismatchWithinTif, ReviewRequired);
end


function T = empty_mismatch_cluster_summary()
    TifFile = cell(0, 1);
    NFrames = zeros(0, 1);
    NMismatchFrames = zeros(0, 1);
    MismatchFraction = zeros(0, 1);
    MaxConsecutiveMismatchWithinTif = zeros(0, 1);
    ReviewRequired = false(0, 1);
    T = table(TifFile, NFrames, NMismatchFrames, MismatchFraction, ...
        MaxConsecutiveMismatchWithinTif, ReviewRequired);
end


function qc = build_qc_summary(comparison, geometry_summary, geometry_blob_count, boundary_valid_count, opts, cluster_summary)
    n = height(comparison);
    blob_fail = ~comparison.BlobCountPass;
    area_fail = ~comparison.TotalAreaPass;
    raw_mismatch = blob_fail | area_fail;
    initial_exempt = initial_frame_area_exempt(comparison, opts);
    effective_blob_fail = blob_fail;
    effective_area_fail = area_fail & ~initial_exempt;
    effective_mismatch = effective_blob_fail | effective_area_fail;
    blob_pass = sum(comparison.BlobCountPass);
    area_pass = sum(comparison.TotalAreaPass);
    effective_blob_pass = n - sum(effective_blob_fail);
    effective_area_pass = n - sum(effective_area_fail);
    max_block = max_consecutive_true(raw_mismatch);
    effective_max_block = max_consecutive_true(effective_mismatch);
    empty_frames = sum(geometry_summary.NGeometryBlobs == 0);
    cluster_review_required = any(cluster_summary.ReviewRequired);
    if effective_max_block > 3 || cluster_review_required
        overall = 'BLOCKED_BY_FRAME_MAPPING_OR_SEGMENTATION_QC';
    elseif any(effective_mismatch) || empty_frames > 0
        overall = 'WARN_QC_REVIEW';
    elseif any(initial_exempt)
        overall = 'PASS_WITH_INITIAL_FRAME_NOTE';
    else
        overall = 'PASS';
    end
    blocked = strcmp(overall, 'BLOCKED_BY_FRAME_MAPPING_OR_SEGMENTATION_QC') || ...
        strcmp(overall, 'WARN_QC_REVIEW');
    can_proceed = strcmp(overall, 'PASS') || strcmp(overall, 'PASS_WITH_INITIAL_FRAME_NOTE');
    Metric = {'OverallStatus'; 'ProcessedFrames'; 'GeometryBlobRows'; ...
        'BlobCountPassFrames'; 'TotalAreaPassFrames'; 'MaxConsecutiveMismatchFrames'; ...
        'EffectiveMaxConsecutiveMismatchFrames'; 'EmptyGeometryFrames'; ...
        'BoundaryMetricValidRows'; 'ExemptedInitialFrameMismatchCount'; ...
        'NonExemptMismatchFrames'; 'EffectiveBlobCountPassFrames'; ...
        'EffectiveTotalAreaPassFrames'; 'BlockedForInterpretation'; ...
        'CanProceedWithManualOverride'; 'MismatchClusterReviewRequired'};
    Value = {overall; num2str(n); num2str(geometry_blob_count); ...
        num2str(blob_pass); num2str(area_pass); num2str(max_block); ...
        num2str(effective_max_block); num2str(empty_frames); ...
        num2str(boundary_valid_count); num2str(sum(initial_exempt)); ...
        num2str(sum(effective_mismatch)); num2str(effective_blob_pass); ...
        num2str(effective_area_pass); logical_text(blocked); ...
        logical_text(can_proceed); logical_text(cluster_review_required)};
    qc = table(Metric, Value);
end


function tf = initial_frame_area_exempt(comparison, opts)
    tf = false(height(comparison), 1);
    if ~logical(opts.AllowInitialFrameAreaMismatch)
        return;
    end
    tf = comparison.FrameIndex == opts.InitialFrameIndex & ...
        comparison.BlobCountPass & ~comparison.TotalAreaPass;
end


function text = logical_text(value)
    if value
        text = 'true';
    else
        text = 'false';
    end
end


function n = max_consecutive_true(values)
    n = 0;
    current = 0;
    for i = 1:numel(values)
        if values(i)
            current = current + 1;
            n = max(n, current);
        else
            current = 0;
        end
    end
end


function write_qc_image(qc_dir, frame_index, mask)
    rgb = zeros([size(mask), 3], 'uint8');
    rgb(:, :, 1) = uint8(mask) * 255;
    rgb(:, :, 2) = uint8(mask) * 80;
    imwrite(rgb, fullfile(qc_dir, sprintf('frame_%06d_mask_visualization.png', frame_index)));
end


function write_backend_version_check(path, validation_v2_dir, output_dir)
    fid = fopen(path, 'w');
    if fid < 0
        return;
    end
    cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, '# Geometry Backend Version Check\n\n');
    fprintf(fid, '- created_at: `%s`\n', datestr(now, 30));
    fprintf(fid, '- active ValidationV2Dir: `%s`\n', validation_v2_dir);
    fprintf(fid, '- active SidecarDir: `%s`\n\n', output_dir);
    fprintf(fid, '## compare_perimeter_estimators\n\n');
    fprintf(fid, '```text\n%s```\n\n', evalc('which -all compare_perimeter_estimators'));
    fprintf(fid, '## run_geometry_sidecar_extraction\n\n');
    fprintf(fid, '```text\n%s```\n', evalc('which -all run_geometry_sidecar_extraction'));
end


function write_100_qc_review(path, qc, comparison, part_infos, output_dir, opts)
    fid = fopen(path, 'w');
    if fid < 0
        return;
    end
    cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
    status = qc.Value{strcmp(qc.Metric, 'OverallStatus')};
    nonexempt = qc.Value{strcmp(qc.Metric, 'NonExemptMismatchFrames')};
    empty_frames = qc.Value{strcmp(qc.Metric, 'EmptyGeometryFrames')};
    max_block = qc.Value{strcmp(qc.Metric, 'MaxConsecutiveMismatchFrames')};
    manifest_rows = 0;
    if ~isempty(part_infos)
        data = vertcat(part_infos{:});
        manifest_rows = sum(cell2mat(data(:, 4)));
    end
    mask_count = count_files(fullfile(output_dir, 'masks_or_labels'), '*_mask.tif');
    label_count = count_files(fullfile(output_dir, 'masks_or_labels'), '*_labels.tif');
    fprintf(fid, '# Geometry Sidecar 100-Frame QC Review\n\n');
    fprintf(fid, '- status: `%s`\n', status);
    fprintf(fid, '- decision: `%s`\n', sidecar_100_decision(status));
    fprintf(fid, '- processed frames: `%d`\n', height(comparison));
    fprintf(fid, '- non-exempt mismatch frames: `%s`\n', nonexempt);
    fprintf(fid, '- empty geometry frames: `%s`\n', empty_frames);
    fprintf(fid, '- max consecutive mismatch frames: `%s`\n', max_block);
    fprintf(fid, '- manifest row count: `%d`\n', manifest_rows);
    fprintf(fid, '- mask files: `%d`\n', mask_count);
    fprintf(fid, '- label files: `%d`\n', label_count);
    fprintf(fid, '- initial frame exemption enabled: `%s`\n', logical_text(opts.AllowInitialFrameAreaMismatch));
    fprintf(fid, '- initial frame index: `%g`\n', opts.InitialFrameIndex);
end


function decision = sidecar_100_decision(status)
    if strcmp(status, 'PASS_WITH_INITIAL_FRAME_NOTE')
        decision = 'ACCEPT_100_FRAME_SMOKE_WITH_INITIAL_FRAME_NOTE';
    elseif strcmp(status, 'PASS')
        decision = 'ACCEPT_100_FRAME_SMOKE';
    elseif strcmp(status, 'BLOCKED_BY_FRAME_MAPPING_OR_SEGMENTATION_QC')
        decision = 'BLOCKED_BY_FRAME_MAPPING_OR_SEGMENTATION_QC';
    else
        decision = 'WARN_QC_REVIEW_NEEDS_500_FRAME_CHECK';
    end
end


function n = count_files(folder, pattern)
    if ~isfolder(folder)
        n = 0;
        return;
    end
    n = numel(dir(fullfile(folder, pattern)));
end


function write_extraction_report(path, qc, n_frames, n_blobs)
    fid = fopen(path, 'w');
    if fid < 0
        error('run_geometry_sidecar_extraction:writeFailed', 'Could not write extraction report.');
    end
    cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
    status = qc.Value{strcmp(qc.Metric, 'OverallStatus')};
    fprintf(fid, '# Geometry Sidecar Extraction Report\n\n');
    fprintf(fid, '- status: `%s`\n', status);
    fprintf(fid, '- processed frames: %d\n', n_frames);
    fprintf(fid, '- geometry blob rows: %d\n\n', n_blobs);
    fprintf(fid, '## Limits\n\n');
    fprintf(fid, '- This sidecar extraction does not modify original chunks, CSV, MAT files, or raw TIFs.\n');
    fprintf(fid, '- ProjectedRoughness_boundary is a 2D exterior-boundary proxy, not 3D roughness or full interfacial area.\n');
    fprintf(fid, '- Tracking and boundary fractal dimension are not computed.\n');
end


function gate = read_v2_gate(validation_v2_dir)
    if isempty(validation_v2_dir) || ~isfolder(validation_v2_dir)
        error('run_geometry_sidecar_extraction:missingValidationV2Dir', ...
            'ValidationV2Dir is required and must exist.');
    end
    summary_path = fullfile(validation_v2_dir, 'geometry_validation_summary.json');
    if ~isfile(summary_path)
        error('run_geometry_sidecar_extraction:missingV2Summary', ...
            'geometry_validation_summary.json not found: %s', summary_path);
    end
    try
        gate = jsondecode(fileread(summary_path));
    catch ME
        error('run_geometry_sidecar_extraction:badV2Summary', ...
            'Could not parse validation v2 summary: %s', ME.message);
    end
    if ~isfield(gate, 'DecisionLabel')
        gate.DecisionLabel = 'UNKNOWN';
    end
end


function path = latest_dir(parent_dir, pattern)
    listing = dir(fullfile(parent_dir, pattern));
    listing = listing([listing.isdir]);
    if isempty(listing)
        path = '';
        return;
    end
    [~, idx] = max([listing.datenum]);
    path = fullfile(listing(idx).folder, listing(idx).name);
end


function output_dir = resolve_output_dir(postprocess_dir, explicit_dir, overwrite)
    explicit_dir = char(explicit_dir);
    if isempty(explicit_dir)
        base_dir = fullfile(postprocess_dir, ['geometry_sidecar_' datestr(now, 'yyyymmdd_HHMMSS')]);
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
            error('run_geometry_sidecar_extraction:nonemptyOutputDir', ...
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


function ensure_dir(path)
    if ~isfolder(path)
        mkdir(path);
    end
end


function write_placeholder_outputs(output_dir, provenance, status, gate)
    provenance.status = status;
    provenance.validation_v2_decision = gate.DecisionLabel;
    write_json(fullfile(output_dir, 'geometry_provenance.json'), provenance);

    geometry_by_blob = empty_table({'FrameIndex', 'BlobID_sidecar', 'Area_px', ...
        'P_boundary', 'Pc_boundary', 'ProjectedRoughness_boundary', ...
        'BoundaryMetricValid', 'AreaTier', 'GeometryQCFlag'});
    writetable(geometry_by_blob, fullfile(output_dir, 'geometry_by_blob.csv'));
    ensure_dir(fullfile(output_dir, 'parts'));
    writetable(part_manifest_table({}), fullfile(output_dir, 'geometry_sidecar_manifest.csv'));

    geometry_summary = empty_table({'FrameIndex', 'NGeometryBlobs', ...
        'NBoundaryMetricValid', 'AreaFracBoundaryMetricValid'});
    writetable(geometry_summary, fullfile(output_dir, 'geometry_summary_by_frame.csv'));

    comparison = empty_table({'FrameIndex', 'BlobCountRelativeDiff', ...
        'TotalAreaRelativeDiff', 'QCDecision'});
    writetable(comparison, fullfile(output_dir, 'geometry_level_a_comparison_all_frames.csv'));
    writetable(comparison, fullfile(output_dir, 'geometry_discrepancy_diagnostics_all_frames.csv'));
    writetable(empty_mismatch_cluster_summary(), fullfile(output_dir, 'geometry_mismatch_cluster_summary.csv'));

    Metric = {'v2_gate'};
    Value = {gate.DecisionLabel};
    Status = {status};
    qc = table(Metric, Value, Status);
    writetable(qc, fullfile(output_dir, 'geometry_qc_summary.csv'));

    fid = fopen(fullfile(output_dir, 'geometry_extraction_report.md'), 'w');
    if fid < 0
        error('run_geometry_sidecar_extraction:writeFailed', 'Could not write extraction report.');
    end
    cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, '# Geometry Sidecar Extraction Report\n\n');
    fprintf(fid, '- status: `%s`\n', status);
    fprintf(fid, '- validation v2 decision: `%s`\n\n', gate.DecisionLabel);
    fprintf(fid, 'This run did not modify original chunks, CSV, MAT files, or raw TIFs.\n');
end


function T = empty_table(names)
    values = cell(1, numel(names));
    for i = 1:numel(names)
        values{i} = cell(0, 1);
    end
    T = table(values{:}, 'VariableNames', names);
end


function write_json(path, value)
    fid = fopen(path, 'w');
    if fid < 0
        error('run_geometry_sidecar_extraction:writeJsonFailed', 'Could not write %s', path);
    end
    cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, '%s', jsonencode(value));
end
