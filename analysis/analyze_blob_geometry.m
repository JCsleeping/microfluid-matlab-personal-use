function blob = analyze_blob_geometry(dnapl_mask, pixel_size, flow_domain, solid_mask, geometry_opts)
% ANALYZE_BLOB_GEOMETRY  Compute geometric properties of connected DNAPL blobs.
%
%   blob = analyze_blob_geometry(dnapl_mask, pixel_size)
%   blob = analyze_blob_geometry(dnapl_mask, pixel_size, flow_domain, solid_mask)
%   blob = analyze_blob_geometry(..., geometry_opts)
%
%   geometry_opts.mode:
%       core_only        - scalar regionprops + EulerNumber, no domain-aware holes
%       roi              - scalar regionprops + ROI-local domain-aware holes
%       legacy_fullframe - original per-blob full-frame hole classification
%
%   The default core_only mode remains the stable production baseline. ROI
%   mode records per-row fallback provenance when domain-aware hole
%   classification is unavailable or the local ROI exceeds configured limits.

    if nargin < 2, pixel_size = []; end
    if nargin < 3, flow_domain = []; end
    if nargin < 4, solid_mask = []; end
    if nargin < 5, geometry_opts = []; end

    geometry_opts = normalize_geometry_options(geometry_opts);

    if ~ismember(geometry_opts.mode, {'core_only', 'roi', 'legacy_fullframe'})
        error('analyze_blob_geometry:badGeometryMode', ...
            'Unsupported geometry mode: %s', geometry_opts.mode);
    end

    conn = geometry_opts.object_connectivity;
    cc = bwconncomp(dnapl_mask, conn);
    label_image = labelmatrix(cc);
    blob.labeled_image = uint32(label_image);
    blob.num_blobs = cc.NumObjects;

    if blob.num_blobs == 0
        blob.props = struct([]);
        blob.blob_table = make_blob_geometry_table(struct([]), geometry_opts);
        blob.size_distribution = struct('mean',0,'median',0,'std',0,'min',0,'max',0,'total',0);
        blob.max_blob_fraction = 0;
        blob.Req_distribution = struct('mean',0,'median',0,'std',0, ...
            'p10',0,'p25',0,'p75',0,'p90',0);
        blob.topology_summary = struct('n_droplets',0,'n_columns',0,'n_clusters',0, ...
            'frac_droplets',0,'frac_columns',0,'frac_clusters',0);
        return;
    end

    props = compute_base_props(cc, label_image, geometry_opts);

    for i = 1:blob.num_blobs
        P = props(i).Perimeter;
        A = props(i).Area;

        props(i).Circularity = 4 * pi * A / (P^2 + eps);
        props(i).AspectRatio = props(i).MajorAxisLength / ...
            max(props(i).MinorAxisLength, eps);
        props(i).Compactness = A / max(props(i).ConvexArea, 1);
        props(i).EquivRadius = props(i).EquivDiameter / 2;

        switch geometry_opts.mode
            case 'core_only'
                hole_info = default_hole_info_core(props(i).EulerNumber);

            case 'roi'
                hole_info = classify_blob_holes_roi(cc.PixelIdxList{i}, ...
                    size(dnapl_mask), flow_domain, solid_mask, conn, ...
                    geometry_opts, props(i).EulerNumber);

            case 'legacy_fullframe'
                blob_mask = false(size(dnapl_mask));
                blob_mask(cc.PixelIdxList{i}) = true;
                props(i).EulerNumber = bweuler(blob_mask, conn);
                hole_info = classify_blob_holes(blob_mask, dnapl_mask, ...
                    flow_domain, solid_mask, conn);
                hole_info.EulerHoleCount = max(0, 1 - props(i).EulerNumber);
                hole_info.HoleClassificationComputed = true;
                hole_info.HoleCountSource = "legacy_domain_aware";

            otherwise
                error('analyze_blob_geometry:badGeometryMode', ...
                    'Unsupported geometry mode: %s', geometry_opts.mode);
        end

        props(i).HoleCount = hole_info.HoleCount;
        props(i).EulerHoleCount = hole_info.EulerHoleCount;
        props(i).WaterHoleCount = hole_info.WaterHoleCount;
        props(i).SolidHoleCount = hole_info.SolidHoleCount;
        props(i).MixedHoleCount = hole_info.MixedHoleCount;
        props(i).UnknownHoleCount = hole_info.UnknownHoleCount;
        props(i).EffectiveEulerNumber = hole_info.EffectiveEulerNumber;
        props(i).DominantHoleType = hole_info.DominantHoleType;
        props(i).HoleClassificationComputed = hole_info.HoleClassificationComputed;
        props(i).HoleCountSource = hole_info.HoleCountSource;
        props(i).GeometryMode = string(geometry_opts.mode);
        props(i).GeometrySchemaVersion = string(geometry_opts.schema_version);
        props(i).ObjectConnectivity = conn;
        props(i).RoiFallbackUsed = hole_info.RoiFallbackUsed;
        props(i).RoiFallbackReason = hole_info.RoiFallbackReason;
        props(i).TouchesImageBorder = hole_info.TouchesImageBorder;
        props(i).RoiAreaFraction = hole_info.RoiAreaFraction;

        if ~isempty(pixel_size) && pixel_size > 0
            props(i).Area_m2          = A * pixel_size^2;
            props(i).Perimeter_m      = P * pixel_size;
            props(i).EquivDiameter_m  = props(i).EquivDiameter * pixel_size;
            props(i).EquivRadius_m    = props(i).EquivRadius * pixel_size;
        else
            props(i).Area_m2          = NaN;
            props(i).Perimeter_m      = NaN;
            props(i).EquivDiameter_m  = NaN;
            props(i).EquivRadius_m    = NaN;
        end

        if hole_info.DomainAware
            if props(i).WaterHoleCount + props(i).MixedHoleCount > 0
                props(i).TopologyType = "cluster";
            elseif props(i).Circularity > 0.5
                props(i).TopologyType = "droplet";
            else
                props(i).TopologyType = "column";
            end
        elseif props(i).EulerHoleCount > 0
            props(i).TopologyType = "cluster";
        elseif props(i).Circularity > 0.5
            props(i).TopologyType = "droplet";
        else
            props(i).TopologyType = "column";
        end

        props(i).GangliaType = classify_ganglia_type(A, pixel_size);
    end

    blob.props = props;
    blob.blob_table = make_blob_geometry_table(props, geometry_opts);

    areas = [props.Area];
    equiv_radii = [props.EquivRadius];
    topology_types = string({props.TopologyType});
    total_area = sum(areas);
    blob.size_distribution.mean   = mean(areas);
    blob.size_distribution.median = median(areas);
    blob.size_distribution.std    = std(areas);
    blob.size_distribution.min    = min(areas);
    blob.size_distribution.max    = max(areas);
    blob.size_distribution.total  = total_area;
    blob.max_blob_fraction = max(areas) / max(total_area, eps);
    blob.Req_distribution = struct( ...
        'mean', mean(equiv_radii), ...
        'median', median(equiv_radii), ...
        'std', std(equiv_radii), ...
        'p10', compute_percentile(equiv_radii, 10), ...
        'p25', compute_percentile(equiv_radii, 25), ...
        'p75', compute_percentile(equiv_radii, 75), ...
        'p90', compute_percentile(equiv_radii, 90));
    blob.topology_summary = struct( ...
        'n_droplets', sum(topology_types == "droplet"), ...
        'n_columns', sum(topology_types == "column"), ...
        'n_clusters', sum(topology_types == "cluster"), ...
        'frac_droplets', sum(areas(topology_types == "droplet")) / max(total_area, eps), ...
        'frac_columns', sum(areas(topology_types == "column")) / max(total_area, eps), ...
        'frac_clusters', sum(areas(topology_types == "cluster")) / max(total_area, eps));
end


function geometry_opts = normalize_geometry_options(geometry_opts)
    if nargin < 1 || isempty(geometry_opts)
        geometry_opts = struct();
    elseif ischar(geometry_opts) || isstring(geometry_opts)
        geometry_opts = struct('mode', char(string(geometry_opts)));
    end

    if ~isfield(geometry_opts, 'mode') || isempty(geometry_opts.mode)
        geometry_opts.mode = 'core_only';
    end
    geometry_opts.mode = char(string(geometry_opts.mode));

    if ~isfield(geometry_opts, 'object_connectivity') || isempty(geometry_opts.object_connectivity)
        geometry_opts.object_connectivity = 8;
    end
    if ~isnumeric(geometry_opts.object_connectivity) || ...
            ~isscalar(geometry_opts.object_connectivity) || ...
            ~ismember(geometry_opts.object_connectivity, [4 8])
        error('analyze_blob_geometry:badGeometryMode', ...
            'geometry.object_connectivity must be 4 or 8.');
    end

    if ~isfield(geometry_opts, 'schema_version') || isempty(geometry_opts.schema_version)
        if strcmp(geometry_opts.mode, 'legacy_fullframe')
            geometry_opts.schema_version = 'geometry_v1_legacy_fullframe';
        elseif strcmp(geometry_opts.mode, 'roi')
            geometry_opts.schema_version = 'geometry_v3_roi_holes';
        else
            geometry_opts.schema_version = 'geometry_v2_core_only';
        end
    end
    geometry_opts.schema_version = char(string(geometry_opts.schema_version));

    if ~isfield(geometry_opts, 'include_heavy_shape_props') || isempty(geometry_opts.include_heavy_shape_props)
        geometry_opts.include_heavy_shape_props = true;
    end
    if ~isfield(geometry_opts, 'roi_pad') || isempty(geometry_opts.roi_pad)
        geometry_opts.roi_pad = 1;
    end
    if ~isfield(geometry_opts, 'max_roi_area_fraction') || isempty(geometry_opts.max_roi_area_fraction)
        geometry_opts.max_roi_area_fraction = 0.25;
    end
    if ~isfield(geometry_opts, 'max_roi_pixels') || isempty(geometry_opts.max_roi_pixels)
        geometry_opts.max_roi_pixels = 2e6;
    end
    geometry_opts.roi_pad = double(geometry_opts.roi_pad);
    geometry_opts.max_roi_area_fraction = double(geometry_opts.max_roi_area_fraction);
    geometry_opts.max_roi_pixels = double(geometry_opts.max_roi_pixels);
end


function props = compute_base_props(cc, label_image, geometry_opts)
    base_props = {'Area', 'Perimeter', 'Centroid', ...
        'BoundingBox', 'MajorAxisLength', 'MinorAxisLength', ...
        'Eccentricity', 'Orientation', 'EquivDiameter', 'Solidity', ...
        'ConvexArea'};

    if geometry_opts.include_heavy_shape_props
        base_props{end+1} = 'FilledArea';
    end

    switch geometry_opts.mode
        case {'core_only', 'roi'}
            core_props = [base_props, {'EulerNumber'}];
            props = regionprops(label_image, core_props{:});

        case 'legacy_fullframe'
            props = regionprops(cc, base_props{:});
    end

    if ~isfield(props, 'FilledArea')
        [props.FilledArea] = deal(NaN);
    end
end


function hole_info = default_hole_info_core(euler_number, source, fallback_used, fallback_reason, touches_border, roi_area_fraction)
    if nargin < 2 || isempty(source), source = "euler_number"; end
    if nargin < 3 || isempty(fallback_used), fallback_used = false; end
    if nargin < 4 || isempty(fallback_reason), fallback_reason = "not_applicable"; end
    if nargin < 5 || isempty(touches_border), touches_border = false; end
    if nargin < 6 || isempty(roi_area_fraction), roi_area_fraction = NaN; end

    if isempty(euler_number) || isnan(euler_number)
        euler_hole_count = NaN;
    else
        euler_hole_count = max(0, 1 - euler_number);
    end

    hole_info = struct( ...
        'HoleCount', euler_hole_count, ...
        'EulerHoleCount', euler_hole_count, ...
        'WaterHoleCount', NaN, ...
        'SolidHoleCount', NaN, ...
        'MixedHoleCount', NaN, ...
        'UnknownHoleCount', NaN, ...
        'EffectiveEulerNumber', euler_number, ...
        'DominantHoleType', "not_classified", ...
        'DomainAware', false, ...
        'HoleClassificationComputed', false, ...
        'HoleCountSource', string(source), ...
        'RoiFallbackUsed', logical(fallback_used), ...
        'RoiFallbackReason', string(fallback_reason), ...
        'TouchesImageBorder', logical(touches_border), ...
        'RoiAreaFraction', double(roi_area_fraction));
end


function ganglia_type = classify_ganglia_type(area_px, pixel_size)
    if ~isempty(pixel_size) && pixel_size > 0
        area_um2 = area_px * (pixel_size * 1e6)^2;
        if area_um2 < 50
            ganglia_type = "singlet";
        elseif area_um2 < 5000
            ganglia_type = "ganglion";
        else
            ganglia_type = "pool";
        end
    else
        if area_px < 50
            ganglia_type = "singlet";
        elseif area_px < 500
            ganglia_type = "ganglion";
        else
            ganglia_type = "pool";
        end
    end
end


function T = make_blob_geometry_table(props, geometry_opts)
    if isempty(props)
        T = make_empty_blob_geometry_table();
        return;
    end

    BlobID = (1:numel(props))';
    Area = [props.Area]';
    Perimeter = [props.Perimeter]';
    Circularity = [props.Circularity]';
    AspectRatio = [props.AspectRatio]';
    Eccentricity = [props.Eccentricity]';
    Solidity = [props.Solidity]';
    EquivDiameter = [props.EquivDiameter]';
    EquivRadius = [props.EquivRadius]';
    Compactness = [props.Compactness]';
    EulerNumber = [props.EulerNumber]';
    EulerHoleCount = [props.EulerHoleCount]';
    HoleCount = [props.HoleCount]';
    WaterHoleCount = [props.WaterHoleCount]';
    SolidHoleCount = [props.SolidHoleCount]';
    MixedHoleCount = [props.MixedHoleCount]';
    UnknownHoleCount = [props.UnknownHoleCount]';
    EffectiveEulerNumber = [props.EffectiveEulerNumber]';
    DominantHoleType = reshape(string({props.DominantHoleType}), [], 1);
    GangliaType = reshape(string({props.GangliaType}), [], 1);
    TopologyType = reshape(string({props.TopologyType}), [], 1);
    Centroid_X = cellfun(@(c) c(1), {props.Centroid})';
    Centroid_Y = cellfun(@(c) c(2), {props.Centroid})';
    GeometryMode = repmat(string(geometry_opts.mode), numel(props), 1);
    GeometrySchemaVersion = repmat(string(geometry_opts.schema_version), numel(props), 1);
    ObjectConnectivity = [props.ObjectConnectivity]';
    HoleClassificationComputed = logical([props.HoleClassificationComputed]');
    HoleCountSource = reshape(string({props.HoleCountSource}), [], 1);
    RoiFallbackUsed = logical([props.RoiFallbackUsed]');
    RoiFallbackReason = reshape(string({props.RoiFallbackReason}), [], 1);
    TouchesImageBorder = logical([props.TouchesImageBorder]');
    RoiAreaFraction = [props.RoiAreaFraction]';

    T = table(BlobID, Area, Perimeter, Circularity, ...
        AspectRatio, Eccentricity, Solidity, EquivDiameter, EquivRadius, ...
        Compactness, EulerNumber, HoleCount, WaterHoleCount, SolidHoleCount, ...
        MixedHoleCount, UnknownHoleCount, EffectiveEulerNumber, DominantHoleType, ...
        Centroid_X, Centroid_Y, GangliaType, TopologyType, ...
        GeometryMode, GeometrySchemaVersion, ObjectConnectivity, ...
        HoleClassificationComputed, HoleCountSource, EulerHoleCount, ...
        RoiFallbackUsed, RoiFallbackReason, TouchesImageBorder, RoiAreaFraction);
end


function names = blob_table_variable_names()
    names = {'BlobID', 'Area', 'Perimeter', 'Circularity', ...
        'AspectRatio', 'Eccentricity', 'Solidity', 'EquivDiameter', 'EquivRadius', ...
        'Compactness', 'EulerNumber', 'HoleCount', 'WaterHoleCount', 'SolidHoleCount', ...
        'MixedHoleCount', 'UnknownHoleCount', 'EffectiveEulerNumber', 'DominantHoleType', ...
        'Centroid_X', 'Centroid_Y', 'GangliaType', 'TopologyType', ...
        'GeometryMode', 'GeometrySchemaVersion', 'ObjectConnectivity', ...
        'HoleClassificationComputed', 'HoleCountSource', 'EulerHoleCount', ...
        'RoiFallbackUsed', 'RoiFallbackReason', 'TouchesImageBorder', ...
        'RoiAreaFraction'};
end


function T = make_empty_blob_geometry_table()
    names = blob_table_variable_names();
    string_names = {'DominantHoleType', 'GangliaType', 'TopologyType', ...
        'GeometryMode', 'GeometrySchemaVersion', 'HoleCountSource', ...
        'RoiFallbackReason'};
    logical_names = {'HoleClassificationComputed', 'RoiFallbackUsed', ...
        'TouchesImageBorder'};

    vars = cell(1, numel(names));
    for idx = 1:numel(names)
        if ismember(names{idx}, string_names)
            vars{idx} = strings(0, 1);
        elseif ismember(names{idx}, logical_names)
            vars{idx} = false(0, 1);
        else
            vars{idx} = zeros(0, 1);
        end
    end

    T = table(vars{:}, 'VariableNames', names);
end


function hole_info = classify_blob_holes_roi(pixel_idx, image_size, flow_domain, solid_mask, conn, geometry_opts, euler_number)
    [local_blob, rows, cols, touches_border] = make_local_blob_mask( ...
        pixel_idx, image_size, geometry_opts.roi_pad);
    roi_pixels = numel(local_blob);
    roi_area_fraction = roi_pixels / prod(double(image_size));

    if roi_pixels > geometry_opts.max_roi_pixels
        hole_info = default_hole_info_core(euler_number, ...
            "euler_number_large_roi_fallback", true, ...
            "max_roi_pixels_exceeded", touches_border, roi_area_fraction);
        return;
    end

    if roi_area_fraction > geometry_opts.max_roi_area_fraction
        hole_info = default_hole_info_core(euler_number, ...
            "euler_number_large_roi_fallback", true, ...
            "max_roi_area_fraction_exceeded", touches_border, roi_area_fraction);
        return;
    end

    domain_ok = ~isempty(flow_domain) && ~isempty(solid_mask) && ...
        isequal(size(flow_domain), image_size) && isequal(size(solid_mask), image_size);
    if ~domain_ok
        hole_info = default_hole_info_core(euler_number, ...
            "euler_number_domain_unavailable", true, ...
            "domain_masks_unavailable", touches_border, roi_area_fraction);
        return;
    end

    local_flow = logical(flow_domain(rows, cols));
    local_solid = logical(solid_mask(rows, cols));

    padded_blob = padarray(local_blob, [1 1], false, 'both');
    filled_blob = imfill(padded_blob, conn, 'holes');
    hole_mask_padded = filled_blob & ~padded_blob;
    hole_mask = hole_mask_padded(2:end-1, 2:end-1);
    hole_cc = bwconncomp(hole_mask, conn);

    hole_info = classify_hole_components_local(hole_cc, hole_mask, ...
        local_blob, local_flow, local_solid);
    hole_info.EulerHoleCount = max(0, 1 - euler_number);
    hole_info.HoleClassificationComputed = true;
    hole_info.HoleCountSource = "roi_domain_aware";
    hole_info.RoiFallbackUsed = false;
    hole_info.RoiFallbackReason = "none";
    hole_info.TouchesImageBorder = logical(touches_border);
    hole_info.RoiAreaFraction = roi_area_fraction;
end


function [local_mask, rows, cols, touches_border] = make_local_blob_mask(pixel_idx, image_size, pad)
    H = image_size(1);
    W = image_size(2);
    [r, c] = ind2sub(image_size, pixel_idx);

    rmin = min(r);
    rmax = max(r);
    cmin = min(c);
    cmax = max(c);
    touches_border = rmin == 1 || rmax == H || cmin == 1 || cmax == W;

    r1 = max(rmin - pad, 1);
    r2 = min(rmax + pad, H);
    c1 = max(cmin - pad, 1);
    c2 = min(cmax + pad, W);

    rows = r1:r2;
    cols = c1:c2;
    local_mask = false(numel(rows), numel(cols));

    rr = r - r1 + 1;
    cc = c - c1 + 1;
    local_mask(sub2ind(size(local_mask), rr, cc)) = true;
end


function hole_info = classify_hole_components_local(hole_cc, hole_mask, local_blob, local_flow, local_solid)
    hole_info = struct( ...
        'HoleCount', hole_cc.NumObjects, ...
        'EulerHoleCount', NaN, ...
        'WaterHoleCount', 0, ...
        'SolidHoleCount', 0, ...
        'MixedHoleCount', 0, ...
        'UnknownHoleCount', 0, ...
        'EffectiveEulerNumber', 1, ...
        'DominantHoleType', "none", ...
        'DomainAware', true, ...
        'HoleClassificationComputed', true, ...
        'HoleCountSource', "roi_domain_aware", ...
        'RoiFallbackUsed', false, ...
        'RoiFallbackReason', "none", ...
        'TouchesImageBorder', false, ...
        'RoiAreaFraction', NaN);

    if hole_cc.NumObjects == 0
        return;
    end

    water_mask = logical(local_flow) & ~logical(local_solid) & ~logical(local_blob);
    local_solid = logical(local_solid);

    for k = 1:hole_cc.NumObjects
        hole_pixels = hole_cc.PixelIdxList{k};
        area_px = numel(hole_pixels);
        solid_px = sum(local_solid(hole_pixels));
        water_px = sum(water_mask(hole_pixels));
        unknown_px = max(0, area_px - solid_px - water_px);

        if solid_px / area_px >= 0.5
            hole_info.SolidHoleCount = hole_info.SolidHoleCount + 1;
        elseif water_px / area_px >= 0.5
            hole_info.WaterHoleCount = hole_info.WaterHoleCount + 1;
        elseif solid_px > 0 && water_px > 0
            hole_info.MixedHoleCount = hole_info.MixedHoleCount + 1;
        elseif unknown_px > 0
            hole_info.UnknownHoleCount = hole_info.UnknownHoleCount + 1;
        else
            hole_info.UnknownHoleCount = hole_info.UnknownHoleCount + 1;
        end
    end

    hole_info.EffectiveEulerNumber = 1 - hole_info.WaterHoleCount - hole_info.MixedHoleCount;
    hole_info.DominantHoleType = dominant_hole_type(hole_info);
end


function hole_info = classify_blob_holes(blob_mask, dnapl_mask, flow_domain, solid_mask, conn)
    if nargin < 5 || isempty(conn)
        conn = 8;
    end

    hole_mask = imfill(blob_mask, conn, 'holes') & ~blob_mask;
    hole_cc = bwconncomp(hole_mask, conn);

    hole_info = struct( ...
        'HoleCount', hole_cc.NumObjects, ...
        'EulerHoleCount', NaN, ...
        'WaterHoleCount', 0, ...
        'SolidHoleCount', 0, ...
        'MixedHoleCount', 0, ...
        'UnknownHoleCount', 0, ...
        'EffectiveEulerNumber', 1, ...
        'DominantHoleType', "none", ...
        'DomainAware', false, ...
        'HoleClassificationComputed', true, ...
        'HoleCountSource', "legacy_domain_aware", ...
        'RoiFallbackUsed', false, ...
        'RoiFallbackReason', "not_applicable", ...
        'TouchesImageBorder', touches_image_border(blob_mask), ...
        'RoiAreaFraction', NaN);

    if hole_cc.NumObjects == 0
        return;
    end

    domain_ok = ~isempty(flow_domain) && ~isempty(solid_mask) && ...
        isequal(size(flow_domain), size(blob_mask)) && ...
        isequal(size(solid_mask), size(blob_mask));
    if ~domain_ok
        hole_info.UnknownHoleCount = hole_cc.NumObjects;
        hole_info.DominantHoleType = "unknown";
        return;
    end

    hole_info.DomainAware = true;
    flow_domain = logical(flow_domain);
    solid_mask = logical(solid_mask);
    dnapl_mask = logical(dnapl_mask);
    water_mask = flow_domain & ~solid_mask & ~dnapl_mask;

    for k = 1:hole_cc.NumObjects
        hole_pixels = hole_cc.PixelIdxList{k};
        area_px = numel(hole_pixels);
        solid_px = sum(solid_mask(hole_pixels));
        water_px = sum(water_mask(hole_pixels));
        unknown_px = max(0, area_px - solid_px - water_px);

        if solid_px / area_px >= 0.5
            hole_info.SolidHoleCount = hole_info.SolidHoleCount + 1;
        elseif water_px / area_px >= 0.5
            hole_info.WaterHoleCount = hole_info.WaterHoleCount + 1;
        elseif solid_px > 0 && water_px > 0
            hole_info.MixedHoleCount = hole_info.MixedHoleCount + 1;
        elseif unknown_px > 0
            hole_info.UnknownHoleCount = hole_info.UnknownHoleCount + 1;
        else
            hole_info.UnknownHoleCount = hole_info.UnknownHoleCount + 1;
        end
    end

    hole_info.EffectiveEulerNumber = 1 - hole_info.WaterHoleCount - hole_info.MixedHoleCount;
    hole_info.DominantHoleType = dominant_hole_type(hole_info);
end


function value = dominant_hole_type(hole_info)
    type_counts = [
        hole_info.WaterHoleCount, ...
        hole_info.SolidHoleCount, ...
        hole_info.MixedHoleCount, ...
        hole_info.UnknownHoleCount];
    nonzero_types = sum(type_counts > 0);
    if nonzero_types == 0
        value = "none";
    elseif nonzero_types > 1 || hole_info.MixedHoleCount > 0
        value = "mixed";
    elseif hole_info.WaterHoleCount > 0
        value = "water";
    elseif hole_info.SolidHoleCount > 0
        value = "solid";
    else
        value = "unknown";
    end
end


function value = touches_image_border(blob_mask)
    value = any(blob_mask(1, :)) || any(blob_mask(end, :)) || ...
        any(blob_mask(:, 1)) || any(blob_mask(:, end));
end


function value = compute_percentile(values, percentile)
    values = sort(values(:));
    n = numel(values);

    if n == 0
        value = 0;
        return;
    end

    if n == 1
        value = values(1);
        return;
    end

    position = 1 + (n - 1) * (percentile / 100);
    lower_idx = floor(position);
    upper_idx = ceil(position);

    if lower_idx == upper_idx
        value = values(lower_idx);
        return;
    end

    weight = position - lower_idx;
    value = values(lower_idx) + weight * (values(upper_idx) - values(lower_idx));
end
