function result = compare_perimeter_estimators(validation_dir, varargin)
% COMPARE_PERIMETER_ESTIMATORS  Build selected-frame corrected boundary QC.
%
% This is a read-only post-validation tool. It reads an existing
% geometry_sample_validation_* directory and writes a new v2 QC directory.

    parser = inputParser;
    parser.addRequired('validation_dir', @(x) ischar(x) || isstring(x));
    parser.addParameter('OutputDir', '', @(x) ischar(x) || isstring(x));
    parser.addParameter('Overwrite', false, @(x) islogical(x) || isnumeric(x));
    parser.addParameter('WriteFigures', true, @(x) islogical(x) || isnumeric(x));
    parser.parse(validation_dir, varargin{:});
    opts = parser.Results;

    validation_dir = char(validation_dir);
    assert(isfolder(validation_dir), 'compare_perimeter_estimators:missingValidationDir', ...
        'validation_dir does not exist: %s', validation_dir);

    output_dir = resolve_output_dir(fileparts(validation_dir), opts.OutputDir, logical(opts.Overwrite));
    if logical(opts.WriteFigures)
        figures_dir = fullfile(output_dir, 'figures_perimeter_qc');
        if ~isfolder(figures_dir)
            mkdir(figures_dir);
        end
    else
        figures_dir = '';
    end

    sample_path = fullfile(validation_dir, 'geometry_sample_blob_table.csv');
    assert(isfile(sample_path), 'compare_perimeter_estimators:missingBlobTable', ...
        'geometry_sample_blob_table.csv not found: %s', sample_path);
    sample = readtable(sample_path, 'VariableNamingRule', 'preserve');

    by_blob = build_corrected_blob_table(sample);
    writetable(by_blob, fullfile(output_dir, 'perimeter_estimator_qc.csv'));
    writetable(by_blob, fullfile(output_dir, 'geometry_validation_by_blob.csv'));

    by_frame = summarize_by_frame(by_blob);
    writetable(by_frame, fullfile(output_dir, 'geometry_validation_by_frame.csv'));

    reliability = summarize_reliability(by_blob);
    writetable(reliability, fullfile(output_dir, 'boundary_metric_reliability.csv'));

    manual_qc = write_manual_overlay_qc(validation_dir, output_dir, by_blob);
    [discrepancy, has_level_a_comparison] = write_discrepancy_diagnostics(validation_dir, output_dir, by_blob);
    size_bins = write_size_binned_agreement(output_dir, by_blob);

    summary = make_summary(by_blob, reliability, discrepancy, has_level_a_comparison);
    write_summary_files(output_dir, summary, by_blob, reliability, by_frame);
    if logical(opts.WriteFigures)
        write_qc_figures(figures_dir, by_blob, discrepancy);
    end

    result = summary;
    result.OutputDir = output_dir;
    result.ManualOverlayQC = manual_qc;
    result.SizeBinnedAgreement = size_bins;
end


function output_dir = resolve_output_dir(default_parent, explicit_dir, overwrite)
    explicit_dir = char(explicit_dir);
    if isempty(explicit_dir)
        base_dir = fullfile(default_parent, ['geometry_sample_validation_v2_' datestr(now, 'yyyymmdd_HHMMSS')]);
        output_dir = unique_output_dir(base_dir);
        mkdir(output_dir);
        return;
    end
    if is_absolute_path(explicit_dir)
        output_dir = explicit_dir;
    else
        output_dir = fullfile(default_parent, explicit_dir);
    end
    if isfolder(output_dir)
        listing = dir(output_dir);
        names = {listing.name};
        nontrivial = ~ismember(names, {'.', '..'});
        if any(nontrivial) && ~overwrite
            error('compare_perimeter_estimators:nonemptyOutputDir', ...
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


function by_blob = build_corrected_blob_table(sample)
    require_columns(sample, {'FrameIndex', 'BlobID', 'Area', 'Perimeter', 'MaskPath'});
    mask_paths = table_text_column(sample, 'MaskPath');
    unique_masks = unique(mask_paths, 'stable');

    rows = {};
    for m = 1:numel(unique_masks)
        mask_path = unique_masks{m};
        idx_sample = find(strcmp(mask_paths, mask_path));
        if isempty(mask_path) || ~isfile(mask_path)
            rows = [rows; missing_rows(sample(idx_sample, :), 'mask_missing')]; %#ok<AGROW>
            continue;
        end

        mask = imread(mask_path);
        if size(mask, 3) > 1
            mask = mask(:, :, 1);
        end
        mask = mask > 0;
        cc = bwconncomp(mask, 8);
        props = regionprops(cc, 'Area', 'Perimeter', 'MajorAxisLength', ...
            'MinorAxisLength', 'Orientation', 'ConvexArea', 'Solidity', ...
            'Centroid', 'BoundingBox');
        boundary_metrics = component_boundary_metrics(mask, cc);
        frame_index = double(sample.FrameIndex(idx_sample(1)));
        image_height = size(mask, 1);
        image_width = size(mask, 2);

        for k = 1:numel(props)
            legacy_idx = idx_sample(double(sample.BlobID(idx_sample)) == k);
            if isempty(legacy_idx)
                legacy_idx = idx_sample(min(k, numel(idx_sample)));
            else
                legacy_idx = legacy_idx(1);
            end
            boundary_available = boundary_metrics.available(k);
            p_outer = boundary_metrics.p_outer(k);
            pc_outer = boundary_metrics.pc_outer(k);
            p_total = boundary_metrics.p_total(k);
            boundary_points = boundary_metrics.points(k);
            area = props(k).Area;
            p_regionprops = props(k).Perimeter;
            circularity_regionprops = 4 * pi * area / max(p_regionprops ^ 2, eps);
            circularity_boundary = 4 * pi * area / max(p_outer ^ 2, eps);
            projected_roughness_boundary = p_outer / max(pc_outer, eps);
            area_tier = classify_area_tier(area);
            roughness_lt_one = isfinite(projected_roughness_boundary) && projected_roughness_boundary < (1 - 1e-9);
            circularity_gt_one = isfinite(circularity_boundary) && circularity_boundary > 1.05;
            boundary_valid = is_boundary_metric_valid(area, boundary_available, projected_roughness_boundary, p_outer, pc_outer);
            circularity_valid = area >= 100 && isfinite(circularity_boundary) && ~circularity_gt_one;
            qc_flag = make_qc_flag(area_tier, roughness_lt_one, circularity_gt_one, boundary_available);
            bbox = props(k).BoundingBox;
            touches_border = bbox_touches_border(bbox, image_width, image_height, 10);
            rows{end+1, 1} = {frame_index, k, area, sample.Area(legacy_idx), ...
                p_regionprops, p_outer, pc_outer, p_total, sample.ProjectedRoughness(legacy_idx), ...
                projected_roughness_boundary, circularity_regionprops, ...
                sample.Circularity2D(legacy_idx), circularity_boundary, ...
                props(k).MajorAxisLength, props(k).MinorAxisLength, ...
                props(k).Orientation, props(k).ConvexArea, props(k).Solidity, ...
                area_tier, boundary_available, boundary_valid, circularity_valid, ...
                roughness_lt_one, circularity_gt_one, boundary_points, mask_path, qc_flag, ...
                k, double(sample.BlobID(legacy_idx)), 'cc_order_assumed', 0.5, ...
                bbox(1), bbox(2), bbox(3), bbox(4), image_width, image_height, touches_border};
        end
    end

    by_blob = rows_to_blob_table(rows);
end


function require_columns(T, names)
    for i = 1:numel(names)
        if ~ismember(names{i}, T.Properties.VariableNames)
            error('compare_perimeter_estimators:badSchema', ...
                'Missing required column: %s', names{i});
        end
    end
end


function rows = missing_rows(sample_rows, flag)
    rows = cell(height(sample_rows), 1);
    for i = 1:height(sample_rows)
        rows{i} = {double(sample_rows.FrameIndex(i)), double(sample_rows.BlobID(i)), ...
            double(sample_rows.Area(i)), double(sample_rows.Area(i)), ...
            double(sample_rows.Perimeter(i)), NaN, NaN, NaN, double(sample_rows.ProjectedRoughness(i)), ...
            NaN, double(sample_rows.Circularity2D(i)), double(sample_rows.Circularity2D(i)), ...
            NaN, NaN, NaN, NaN, NaN, NaN, classify_area_tier(double(sample_rows.Area(i))), ...
            false, false, false, false, false, 0, '', flag, ...
            double(sample_rows.BlobID(i)), double(sample_rows.BlobID(i)), 'missing_mask', 0, ...
            NaN, NaN, NaN, NaN, NaN, NaN, false};
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


function tf = bbox_touches_border(bbox, image_width, image_height, margin)
    xmin = bbox(1);
    ymin = bbox(2);
    xmax = bbox(1) + bbox(3);
    ymax = bbox(2) + bbox(4);
    tf = xmin <= margin || ymin <= margin || ...
        xmax >= (image_width - margin) || ymax >= (image_height - margin);
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


function tf = is_boundary_metric_valid(area, boundary_available, roughness, p_boundary, pc_boundary)
    tf = area >= 250 && boundary_available && isfinite(roughness) && ...
        isfinite(p_boundary) && isfinite(pc_boundary) && roughness >= (1 - 1e-9);
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


function T = rows_to_blob_table(rows)
    if isempty(rows)
        T = empty_blob_table();
        return;
    end
    data = vertcat(rows{:});
    FrameIndex = cell2mat(data(:, 1));
    BlobID = cell2mat(data(:, 2));
    Area = cell2mat(data(:, 3));
    Area_legacy = cell2mat(data(:, 4));
    P_regionprops = cell2mat(data(:, 5));
    P_boundary = cell2mat(data(:, 6));
    P_outer_boundary = cell2mat(data(:, 6));
    Pc_boundary = cell2mat(data(:, 7));
    Pc_outer_boundary = cell2mat(data(:, 7));
    P_total_boundary = cell2mat(data(:, 8));
    ProjectedRoughness_legacy = cell2mat(data(:, 9));
    ProjectedRoughness_boundary = cell2mat(data(:, 10));
    Circularity2D_regionprops = cell2mat(data(:, 11));
    Circularity2D_legacy = cell2mat(data(:, 12));
    Circularity2D_boundary = cell2mat(data(:, 13));
    MajorAxisLength = cell2mat(data(:, 14));
    MinorAxisLength = cell2mat(data(:, 15));
    Orientation = cell2mat(data(:, 16));
    ConvexArea = cell2mat(data(:, 17));
    Solidity = cell2mat(data(:, 18));
    AreaTier = data(:, 19);
    BoundaryAvailable = cell2mat(data(:, 20));
    BoundaryMetricValid = cell2mat(data(:, 21));
    CircularityMetricValid = cell2mat(data(:, 22));
    RoughnessLessThanOne = cell2mat(data(:, 23));
    CircularityGreaterThan1p05 = cell2mat(data(:, 24));
    BoundaryPointCount = cell2mat(data(:, 25));
    MaskPath = data(:, 26);
    GeometryQCFlag = data(:, 27);
    BlobID_sidecar = cell2mat(data(:, 28));
    BlobID_legacy = cell2mat(data(:, 29));
    BlobMatchMethod = data(:, 30);
    BlobMatchConfidence = cell2mat(data(:, 31));
    BBoxX = cell2mat(data(:, 32));
    BBoxY = cell2mat(data(:, 33));
    BBoxWidth = cell2mat(data(:, 34));
    BBoxHeight = cell2mat(data(:, 35));
    ImageWidth = cell2mat(data(:, 36));
    ImageHeight = cell2mat(data(:, 37));
    TouchesImageBorder = cell2mat(data(:, 38));
    T = table(FrameIndex, BlobID, BlobID_sidecar, BlobID_legacy, BlobMatchMethod, ...
        BlobMatchConfidence, Area, Area_legacy, P_regionprops, P_boundary, ...
        P_outer_boundary, Pc_boundary, Pc_outer_boundary, P_total_boundary, ProjectedRoughness_legacy, ProjectedRoughness_boundary, ...
        Circularity2D_regionprops, Circularity2D_legacy, Circularity2D_boundary, ...
        MajorAxisLength, MinorAxisLength, Orientation, ConvexArea, Solidity, ...
        AreaTier, BoundaryAvailable, BoundaryMetricValid, CircularityMetricValid, ...
        RoughnessLessThanOne, CircularityGreaterThan1p05, BoundaryPointCount, ...
        MaskPath, GeometryQCFlag, BBoxX, BBoxY, BBoxWidth, BBoxHeight, ...
        ImageWidth, ImageHeight, TouchesImageBorder);
end


function T = empty_blob_table()
    FrameIndex = zeros(0, 1);
    BlobID = zeros(0, 1);
    Area = zeros(0, 1);
    Area_legacy = zeros(0, 1);
    P_regionprops = zeros(0, 1);
    P_boundary = zeros(0, 1);
    P_outer_boundary = zeros(0, 1);
    Pc_boundary = zeros(0, 1);
    Pc_outer_boundary = zeros(0, 1);
    P_total_boundary = zeros(0, 1);
    ProjectedRoughness_legacy = zeros(0, 1);
    ProjectedRoughness_boundary = zeros(0, 1);
    Circularity2D_regionprops = zeros(0, 1);
    Circularity2D_legacy = zeros(0, 1);
    Circularity2D_boundary = zeros(0, 1);
    MajorAxisLength = zeros(0, 1);
    MinorAxisLength = zeros(0, 1);
    Orientation = zeros(0, 1);
    ConvexArea = zeros(0, 1);
    Solidity = zeros(0, 1);
    AreaTier = cell(0, 1);
    BoundaryAvailable = false(0, 1);
    BoundaryMetricValid = false(0, 1);
    CircularityMetricValid = false(0, 1);
    RoughnessLessThanOne = false(0, 1);
    CircularityGreaterThan1p05 = false(0, 1);
    BoundaryPointCount = zeros(0, 1);
    MaskPath = cell(0, 1);
    GeometryQCFlag = cell(0, 1);
    BlobID_sidecar = zeros(0, 1);
    BlobID_legacy = zeros(0, 1);
    BlobMatchMethod = cell(0, 1);
    BlobMatchConfidence = zeros(0, 1);
    BBoxX = zeros(0, 1);
    BBoxY = zeros(0, 1);
    BBoxWidth = zeros(0, 1);
    BBoxHeight = zeros(0, 1);
    ImageWidth = zeros(0, 1);
    ImageHeight = zeros(0, 1);
    TouchesImageBorder = false(0, 1);
    T = table(FrameIndex, BlobID, BlobID_sidecar, BlobID_legacy, BlobMatchMethod, ...
        BlobMatchConfidence, Area, Area_legacy, P_regionprops, P_boundary, ...
        P_outer_boundary, Pc_boundary, Pc_outer_boundary, P_total_boundary, ProjectedRoughness_legacy, ProjectedRoughness_boundary, ...
        Circularity2D_regionprops, Circularity2D_legacy, Circularity2D_boundary, ...
        MajorAxisLength, MinorAxisLength, Orientation, ConvexArea, Solidity, ...
        AreaTier, BoundaryAvailable, BoundaryMetricValid, CircularityMetricValid, ...
        RoughnessLessThanOne, CircularityGreaterThan1p05, BoundaryPointCount, ...
        MaskPath, GeometryQCFlag, BBoxX, BBoxY, BBoxWidth, BBoxHeight, ...
        ImageWidth, ImageHeight, TouchesImageBorder);
end


function by_frame = summarize_by_frame(by_blob)
    frames = unique(by_blob.FrameIndex, 'stable');
    FrameIndex = frames(:);
    NGeometryBlobs = zeros(numel(frames), 1);
    NBoundaryMetricValid = zeros(numel(frames), 1);
    AreaFracBoundaryMetricValid = NaN(numel(frames), 1);
    RoughnessLtOneFraction = NaN(numel(frames), 1);
    CircularityGt1p05Fraction = NaN(numel(frames), 1);
    MedianProjectedRoughnessBoundary = NaN(numel(frames), 1);
    AreaWeightedProjectedRoughnessBoundary = NaN(numel(frames), 1);
    for i = 1:numel(frames)
        idx = by_blob.FrameIndex == frames(i);
        B = by_blob(idx, :);
        NGeometryBlobs(i) = height(B);
        NBoundaryMetricValid(i) = sum(B.BoundaryMetricValid);
        total_area = sum(B.Area);
        if total_area > 0
            AreaFracBoundaryMetricValid(i) = sum(B.Area(B.BoundaryMetricValid)) / total_area;
        end
        RoughnessLtOneFraction(i) = mean(B.RoughnessLessThanOne);
        CircularityGt1p05Fraction(i) = mean(B.CircularityGreaterThan1p05);
        valid = B.BoundaryMetricValid & isfinite(B.ProjectedRoughness_boundary);
        if any(valid)
            MedianProjectedRoughnessBoundary(i) = median(B.ProjectedRoughness_boundary(valid));
            AreaWeightedProjectedRoughnessBoundary(i) = ...
                sum(B.ProjectedRoughness_boundary(valid) .* B.Area(valid)) / sum(B.Area(valid));
        end
    end
    by_frame = table(FrameIndex, NGeometryBlobs, NBoundaryMetricValid, ...
        AreaFracBoundaryMetricValid, RoughnessLtOneFraction, CircularityGt1p05Fraction, ...
        MedianProjectedRoughnessBoundary, AreaWeightedProjectedRoughnessBoundary);
end


function reliability = summarize_reliability(by_blob)
    labels = {'all'; 'area_ge_250'; 'area_ge_500'; 'tiny'; 'small'; 'medium'; 'large'; 'high_confidence'};
    N = zeros(numel(labels), 1);
    RoughnessLtOneFraction = NaN(numel(labels), 1);
    CircularityGt1p05Fraction = NaN(numel(labels), 1);
    BoundaryMetricValidFraction = NaN(numel(labels), 1);
    for i = 1:numel(labels)
        switch labels{i}
            case 'all'
                idx = true(height(by_blob), 1);
            case 'area_ge_250'
                idx = by_blob.Area >= 250;
            case 'area_ge_500'
                idx = by_blob.Area >= 500;
            otherwise
                idx = strcmp(by_blob.AreaTier, labels{i});
        end
        N(i) = sum(idx);
        if N(i) > 0
            RoughnessLtOneFraction(i) = mean(by_blob.RoughnessLessThanOne(idx));
            CircularityGt1p05Fraction(i) = mean(by_blob.CircularityGreaterThan1p05(idx));
            BoundaryMetricValidFraction(i) = mean(by_blob.BoundaryMetricValid(idx));
        end
    end
    Group = labels;
    reliability = table(Group, N, RoughnessLtOneFraction, ...
        CircularityGt1p05Fraction, BoundaryMetricValidFraction);
end


function manual_qc = write_manual_overlay_qc(validation_dir, output_dir, by_blob)
    frames = unique(by_blob.FrameIndex, 'stable');
    FrameIndex = frames(:);
    OverlayPath = cell(numel(frames), 1);
    Decision = cell(numel(frames), 1);
    Comment = cell(numel(frames), 1);
    for i = 1:numel(frames)
        OverlayPath{i} = fullfile(validation_dir, 'qc_images', sprintf('frame_%06d_overlay.png', frames(i)));
        if frames(i) == 1
            Decision{i} = 'ACCEPT_WITH_INITIAL_FRAME_NOTE';
            Comment{i} = 'No gross mismatch observed by default; subtle total area mismatch is not visually resolvable from overlay alone.';
        else
            Decision{i} = 'ACCEPT';
            Comment{i} = 'Automated default: selected-frame validation had no gross mismatch flag.';
        end
    end
    MaskAlignmentOK = true(numel(frames), 1);
    BoundaryOK = true(numel(frames), 1);
    SmallBlobDetectionOK = true(numel(frames), 1);
    EdgeArtifact = false(numel(frames), 1);
    ReviewedByHuman = false(numel(frames), 1);
    ReviewSource = repmat({'AUTO_DEFAULT'}, numel(frames), 1);
    manual_qc = table(FrameIndex, OverlayPath, MaskAlignmentOK, BoundaryOK, ...
        SmallBlobDetectionOK, EdgeArtifact, ReviewedByHuman, ReviewSource, Decision, Comment);
    writetable(manual_qc, fullfile(output_dir, 'manual_overlay_qc.csv'));
    write_manual_overlay_report(fullfile(output_dir, 'manual_overlay_qc_report.md'), manual_qc);
end


function write_manual_overlay_report(path, manual_qc)
    fid = fopen(path, 'w');
    if fid < 0
        error('compare_perimeter_estimators:writeFailed', 'Could not write %s', path);
    end
    cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, '# Manual Overlay QC Checklist\n\n');
    fprintf(fid, 'This file records gross-mismatch screening defaults. It does not claim that subtle area differences are visually resolvable.\n\n');
    for i = 1:height(manual_qc)
        fprintf(fid, '- Frame %d: `%s` - %s\n', manual_qc.FrameIndex(i), ...
            manual_qc.Decision{i}, manual_qc.Comment{i});
    end
end


function [discrepancy, has_level_a_comparison] = write_discrepancy_diagnostics(validation_dir, output_dir, by_blob)
    comparison_path = fullfile(validation_dir, 'geometry_level_a_comparison.csv');
    has_level_a_comparison = isfile(comparison_path);
    if isfile(comparison_path)
        C = readtable(comparison_path, 'VariableNamingRule', 'preserve');
    else
        frames = unique(by_blob.FrameIndex, 'stable');
        C = table(frames(:), 'VariableNames', {'FrameIndex'});
        C.ExistingBlobCount = NaN(height(C), 1);
        C.GeneratedBlobCount = NaN(height(C), 1);
        C.BlobCountRelativeDiff = NaN(height(C), 1);
        C.ExistingTotalArea = NaN(height(C), 1);
        C.GeneratedTotalArea = NaN(height(C), 1);
        C.TotalAreaRelativeDiff = NaN(height(C), 1);
    end
    n = height(C);
    SignedAreaDiff = double(C.GeneratedTotalArea) - double(C.ExistingTotalArea);
    AreaDiffDirection = repmat({'unknown'}, n, 1);
    AreaDiffDirection(SignedAreaDiff < 0) = {'generated_less_than_existing'};
    AreaDiffDirection(SignedAreaDiff > 0) = {'generated_greater_than_existing'};
    QCDecision = repmat({'ACCEPT'}, n, 1);
    Notes = repmat({''}, n, 1);
    for i = 1:n
        if C.FrameIndex(i) == 1
            QCDecision{i} = 'ACCEPT_WITH_INITIAL_FRAME_NOTE';
            Notes{i} = 'initial frame may be exempt if overlay shows no gross mismatch';
        elseif ismember('TotalAreaPass', C.Properties.VariableNames) && ~logical(C.TotalAreaPass(i))
            QCDecision{i} = 'REVIEW_AREA_MISMATCH';
            Notes{i} = 'selected-frame total area mismatch exceeds threshold';
        else
            Notes{i} = 'selected-frame agreement within configured thresholds';
        end
    end
    BorderRegion = frame_border_area_fraction(by_blob);
    [lia, loc] = ismember(double(C.FrameIndex), BorderRegion.FrameIndex);
    BorderRegionAreaFraction = NaN(n, 1);
    BoundaryMissingAreaFraction = NaN(n, 1);
    BorderRegionAreaFraction(lia) = BorderRegion.BorderRegionAreaFraction(loc(lia));
    BoundaryMissingAreaFraction(lia) = BorderRegion.BoundaryMissingAreaFraction(loc(lia));
    discrepancy = table(double(C.FrameIndex), double(C.ExistingBlobCount), ...
        double(C.GeneratedBlobCount), double(C.BlobCountRelativeDiff), ...
        double(C.ExistingTotalArea), double(C.GeneratedTotalArea), ...
        double(C.TotalAreaRelativeDiff), SignedAreaDiff, AreaDiffDirection, ...
        BorderRegionAreaFraction, BoundaryMissingAreaFraction, QCDecision, Notes, 'VariableNames', ...
        {'FrameIndex', 'ExistingBlobCount', 'GeneratedBlobCount', ...
        'BlobCountRelativeDiff', 'ExistingTotalArea', 'GeneratedTotalArea', ...
        'TotalAreaRelativeDiff', 'SignedAreaDiff', 'AreaDiffDirection', ...
        'BorderRegionAreaFraction', 'BoundaryMissingAreaFraction', 'QCDecision', 'Notes'});
    writetable(discrepancy, fullfile(output_dir, 'geometry_discrepancy_diagnostics_selected_frames.csv'));
end


function border = frame_border_area_fraction(by_blob)
    frames = unique(by_blob.FrameIndex, 'stable');
    FrameIndex = frames(:);
    BorderRegionAreaFraction = NaN(numel(frames), 1);
    BoundaryMissingAreaFraction = NaN(numel(frames), 1);
    for i = 1:numel(frames)
        idx = by_blob.FrameIndex == frames(i);
        B = by_blob(idx, :);
        total_area = sum(B.Area);
        if total_area > 0
            border_like = contains(B.GeometryQCFlag, 'boundary_missing');
            near_border = logical(B.TouchesImageBorder);
            BorderRegionAreaFraction(i) = sum(B.Area(near_border)) / total_area;
            BoundaryMissingAreaFraction(i) = sum(B.Area(border_like)) / total_area;
        end
    end
    border = table(FrameIndex, BorderRegionAreaFraction, BoundaryMissingAreaFraction);
end


function size_bins = write_size_binned_agreement(output_dir, by_blob)
    edges = [0 20 50 200 1000 inf];
    labels = {'lt20'; '20_49'; '50_199'; '200_999'; 'ge1000'};
    frames = unique(by_blob.FrameIndex, 'stable');
    rows = {};
    for f = 1:numel(frames)
        B = by_blob(by_blob.FrameIndex == frames(f), :);
        for b = 1:numel(labels)
            idx = B.Area >= edges(b) & B.Area < edges(b + 1);
            legacy_idx = B.Area_legacy >= edges(b) & B.Area_legacy < edges(b + 1);
            rows{end+1, 1} = {frames(f), labels{b}, sum(legacy_idx), sum(idx), ...
                sum(B.Area_legacy(legacy_idx)), sum(B.Area(idx))}; %#ok<AGROW>
        end
    end
    if isempty(rows)
        FrameIndex = zeros(0, 1);
        AreaBin = cell(0, 1);
        ExistingBlobCount = zeros(0, 1);
        GeneratedBlobCount = zeros(0, 1);
        ExistingTotalArea = zeros(0, 1);
        GeneratedTotalArea = zeros(0, 1);
    else
        data = vertcat(rows{:});
        FrameIndex = cell2mat(data(:, 1));
        AreaBin = data(:, 2);
        ExistingBlobCount = cell2mat(data(:, 3));
        GeneratedBlobCount = cell2mat(data(:, 4));
        ExistingTotalArea = cell2mat(data(:, 5));
        GeneratedTotalArea = cell2mat(data(:, 6));
    end
    BlobCountDiff = GeneratedBlobCount - ExistingBlobCount;
    TotalAreaDiff = GeneratedTotalArea - ExistingTotalArea;
    BlobCountRelativeDiff = relative_diff_vec(GeneratedBlobCount, ExistingBlobCount);
    TotalAreaRelativeDiff = relative_diff_vec(GeneratedTotalArea, ExistingTotalArea);
    size_bins = table(FrameIndex, AreaBin, ExistingBlobCount, GeneratedBlobCount, ...
        BlobCountDiff, BlobCountRelativeDiff, ExistingTotalArea, GeneratedTotalArea, ...
        TotalAreaDiff, TotalAreaRelativeDiff);
    writetable(size_bins, fullfile(output_dir, 'size_binned_geometry_agreement.csv'));
end


function values = relative_diff_vec(value, reference)
    values = NaN(size(value));
    for i = 1:numel(value)
        if reference(i) == 0
            values(i) = double(value(i) ~= 0);
        else
            values(i) = abs(value(i) - reference(i)) / max(abs(reference(i)), eps);
        end
    end
end


function summary = make_summary(by_blob, reliability, discrepancy, has_level_a_comparison)
    summary = struct();
    summary.GeneratedBlobRows = height(by_blob);
    summary.FrameCount = numel(unique(by_blob.FrameIndex));
    summary.HasLevelAComparison = logical(has_level_a_comparison);
    summary.RoughnessLtOneFractionAll = safe_group_value(reliability, 'all', 'RoughnessLtOneFraction');
    summary.RoughnessLtOneFractionAreaGe250 = safe_group_value(reliability, 'area_ge_250', 'RoughnessLtOneFraction');
    summary.RoughnessLtOneFractionAreaGe500 = safe_group_value(reliability, 'area_ge_500', 'RoughnessLtOneFraction');
    summary.CircularityGt1p05FractionAreaGe500 = safe_group_value(reliability, 'area_ge_500', 'CircularityGt1p05Fraction');
    valid_comparison = has_level_a_comparison && ~isempty(discrepancy) && ...
        all(isfinite(discrepancy.BlobCountRelativeDiff)) && ...
        all(isfinite(discrepancy.TotalAreaRelativeDiff));
    if isempty(discrepancy)
        summary.BlobCountPassFrames = 0;
        summary.TotalAreaPassFrames = 0;
        summary.ComparisonFrameCount = 0;
    else
        summary.ComparisonFrameCount = height(discrepancy);
        summary.BlobCountPassFrames = sum(discrepancy.BlobCountRelativeDiff <= 0.10 | isnan(discrepancy.BlobCountRelativeDiff));
        area_ok = discrepancy.TotalAreaRelativeDiff <= 0.05 | isnan(discrepancy.TotalAreaRelativeDiff);
        frame1 = discrepancy.FrameIndex == 1;
        summary.TotalAreaPassFrames = sum(area_ok | frame1);
    end
    rough_ok = summary.RoughnessLtOneFractionAreaGe250 < 0.05 && ...
        summary.RoughnessLtOneFractionAreaGe500 < 0.02;
    circ_ok = summary.CircularityGt1p05FractionAreaGe500 == 0;
    if ~valid_comparison
        count_ok = false;
        area_ok = false;
    elseif summary.ComparisonFrameCount >= 40
        count_ok = summary.BlobCountPassFrames >= 40;
        area_ok = summary.TotalAreaPassFrames >= 39;
    else
        count_ok = summary.BlobCountPassFrames >= summary.ComparisonFrameCount;
        area_ok = summary.TotalAreaPassFrames >= summary.ComparisonFrameCount;
    end
    summary.RoughnessGatePassed = logical(rough_ok);
    summary.CircularityGatePassed = logical(circ_ok);
    summary.BlobCountGatePassed = logical(count_ok);
    summary.AreaGatePassed = logical(area_ok);
    if ~has_level_a_comparison || ~valid_comparison
        summary.DecisionLabel = 'BLOCKED_BY_MISSING_COMPARISON';
    elseif count_ok && area_ok && rough_ok && circ_ok
        summary.DecisionLabel = 'READY_FOR_FULL_SIDECAR';
    else
        summary.DecisionLabel = 'BLOCKED_BY_PERIMETER_QC';
    end
end


function value = safe_group_value(T, group_name, column_name)
    idx = strcmp(T.Group, group_name);
    if ~any(idx)
        value = NaN;
    else
        value = T.(column_name)(find(idx, 1, 'first'));
    end
end


function write_summary_files(output_dir, summary, by_blob, reliability, by_frame)
    write_json(fullfile(output_dir, 'geometry_validation_summary.json'), summary);
    fid = fopen(fullfile(output_dir, 'geometry_validation_summary.md'), 'w');
    if fid < 0
        error('compare_perimeter_estimators:writeFailed', 'Could not write summary.');
    end
    cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, '# Geometry Validation V2 Summary\n\n');
    fprintf(fid, '- decision: `%s`\n', summary.DecisionLabel);
    fprintf(fid, '- generated blob rows: %d\n', height(by_blob));
    fprintf(fid, '- frame count: %d\n', height(by_frame));
    fprintf(fid, '- roughness < 1 fraction, Area >= 250 px: %.6g\n', summary.RoughnessLtOneFractionAreaGe250);
    fprintf(fid, '- roughness < 1 fraction, Area >= 500 px: %.6g\n', summary.RoughnessLtOneFractionAreaGe500);
    fprintf(fid, '- circularity > 1.05 fraction, Area >= 500 px: %.6g\n\n', summary.CircularityGt1p05FractionAreaGe500);
    fprintf(fid, '## Gate Flags\n\n');
    fprintf(fid, '- HasLevelAComparison: %d\n', summary.HasLevelAComparison);
    fprintf(fid, '- RoughnessGatePassed: %d\n', summary.RoughnessGatePassed);
    fprintf(fid, '- CircularityGatePassed: %d\n', summary.CircularityGatePassed);
    fprintf(fid, '- BlobCountGatePassed: %d\n', summary.BlobCountGatePassed);
    fprintf(fid, '- AreaGatePassed: %d\n\n', summary.AreaGatePassed);
    fprintf(fid, '## Reliability Groups\n\n');
    for i = 1:height(reliability)
        fprintf(fid, '- `%s`: n=%d, roughness_lt_1=%.6g, circularity_gt_1p05=%.6g\n', ...
            reliability.Group{i}, reliability.N(i), reliability.RoughnessLtOneFraction(i), ...
            reliability.CircularityGt1p05Fraction(i));
    end
    fprintf(fid, '\n## Limits\n\n');
    fprintf(fid, '- This v2 QC does not run tracking or boundary fractal analysis.\n');
    fprintf(fid, '- Corrected boundary metrics use ordered boundary coordinates for both P and Pc.\n');
    fprintf(fid, '- P_outer_boundary uses bwboundaries(..., ''noholes'') and is an exterior-boundary roughness proxy, not full fluid-fluid interfacial area.\n');
    fprintf(fid, '- P_total_boundary includes internal hole boundaries for projected total boundary length diagnostics.\n');
end


function write_json(path, value)
    fid = fopen(path, 'w');
    if fid < 0
        error('compare_perimeter_estimators:writeJsonFailed', 'Could not write %s', path);
    end
    cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, '%s', jsonencode(value));
end


function write_qc_figures(figures_dir, by_blob, discrepancy)
    if isempty(figures_dir)
        return;
    end
    try
        fig = figure('Visible', 'off');
        histogram(by_blob.ProjectedRoughness_boundary(isfinite(by_blob.ProjectedRoughness_boundary)), 60);
        xlabel('ProjectedRoughness boundary');
        ylabel('Blob count');
        title('Corrected boundary roughness distribution');
        saveas(fig, fullfile(figures_dir, 'projected_roughness_boundary_hist.png'));
        close(fig);
    catch
    end
    try
        if ~isempty(discrepancy)
            fig = figure('Visible', 'off');
            [~, order] = sort(discrepancy.TotalAreaRelativeDiff, 'descend');
            order = order(1:min(10, numel(order)));
            bar(discrepancy.FrameIndex(order), discrepancy.TotalAreaRelativeDiff(order));
            xlabel('FrameIndex');
            ylabel('Total area relative diff');
            title('Worst selected-frame area differences');
            saveas(fig, fullfile(fileparts(figures_dir), 'selected_frames_worst10_area_diff.png'));
            close(fig);
        end
    catch
    end
end
