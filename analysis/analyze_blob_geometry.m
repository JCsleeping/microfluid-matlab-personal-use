function blob = analyze_blob_geometry(dnapl_mask, pixel_size)
% ANALYZE_BLOB_GEOMETRY  Compute geometric properties of connected DNAPL blobs.
%
%   blob = analyze_blob_geometry(dnapl_mask, pixel_size)
%
%   Inputs:
%       dnapl_mask - M x N logical DNAPL mask
%       pixel_size - Physical pixel size [m] (optional, can be [])
%
%   Output:
%       blob - Struct with fields:
%           .num_blobs          Number of connected blobs
%           .labeled_image      uint32 labeled image
%           .props              struct array from regionprops + derived metrics
%           .blob_table         Table of per-blob properties
%           .size_distribution  Summary statistics struct

    if nargin < 2, pixel_size = []; end

    %% Label connected components (8-connectivity)
    cc = bwconncomp(dnapl_mask, 8);
    blob.labeled_image = uint32(labelmatrix(cc));
    blob.num_blobs = cc.NumObjects;

    if blob.num_blobs == 0
        blob.props = struct([]);
        blob.blob_table = table();
        blob.size_distribution = struct('mean',0,'median',0,'std',0,'min',0,'max',0,'total',0);
        blob.max_blob_fraction = 0;
        blob.Req_distribution = struct('mean',0,'median',0,'std',0, ...
            'p10',0,'p25',0,'p75',0,'p90',0);
        blob.topology_summary = struct('n_droplets',0,'n_columns',0,'n_clusters',0, ...
            'frac_droplets',0,'frac_columns',0,'frac_clusters',0);
        return;
    end

    %% Compute standard properties
    props = regionprops(cc, 'Area', 'Perimeter', 'Centroid', ...
        'BoundingBox', 'MajorAxisLength', 'MinorAxisLength', ...
        'Eccentricity', 'Orientation', 'EquivDiameter', 'Solidity', ...
        'ConvexArea', 'FilledArea');

    %% Compute derived metrics
    for i = 1:blob.num_blobs
        P = props(i).Perimeter;
        A = props(i).Area;

        % Circularity (1 = perfect circle)
        props(i).Circularity = 4 * pi * A / (P^2 + eps);

        % Aspect ratio
        props(i).AspectRatio = props(i).MajorAxisLength / ...
            max(props(i).MinorAxisLength, eps);

        % Compactness (area / convex area)
        props(i).Compactness = A / max(props(i).ConvexArea, 1);

        blob_mask = false(size(dnapl_mask));
        blob_mask(cc.PixelIdxList{i}) = true;
        props(i).EulerNumber = bweuler(blob_mask, 8);
        props(i).EquivRadius = props(i).EquivDiameter / 2;

        % Physical units
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

        if props(i).EulerNumber < 1
            props(i).TopologyType = "cluster";
        elseif props(i).Circularity > 0.5
            props(i).TopologyType = "droplet";
        else
            props(i).TopologyType = "column";
        end

        % Ganglia classification (Mayer & Miller, 1996 style)
        % Physical thresholds: singlet < 50 um^2, ganglion < 5000 um^2
        if ~isempty(pixel_size) && pixel_size > 0
            area_um2 = A * (pixel_size * 1e6)^2;  % convert m^2 to um^2
            if area_um2 < 50
                props(i).GangliaType = "singlet";
            elseif area_um2 < 5000
                props(i).GangliaType = "ganglion";
            else
                props(i).GangliaType = "pool";
            end
        else
            % Fallback: pixel-based thresholds (legacy behavior)
            if A < 50
                props(i).GangliaType = "singlet";
            elseif A < 500
                props(i).GangliaType = "ganglion";
            else
                props(i).GangliaType = "pool";
            end
        end
    end

    blob.props = props;

    %% Build table
    BlobID = (1:blob.num_blobs)';
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
    GangliaType = reshape(string({props.GangliaType}), [], 1);
    TopologyType = reshape(string({props.TopologyType}), [], 1);
    Centroid_X = cellfun(@(c) c(1), {props.Centroid})';
    Centroid_Y = cellfun(@(c) c(2), {props.Centroid})';

    blob.blob_table = table(BlobID, Area, Perimeter, Circularity, ...
        AspectRatio, Eccentricity, Solidity, EquivDiameter, EquivRadius, ...
        Compactness, EulerNumber, Centroid_X, Centroid_Y, GangliaType, TopologyType);

    %% Size distribution statistics
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
