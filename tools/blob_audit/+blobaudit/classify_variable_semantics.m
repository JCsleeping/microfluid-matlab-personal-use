function roles = classify_variable_semantics(var_names)
% CLASSIFY_VARIABLE_SEMANTICS  Map variable names to audit semantic roles.

    roles = repmat({'Unknown'}, size(var_names));
    aliases = alias_map();
    fields = fieldnames(aliases);
    norm_vars = blobaudit.normalize_var_names(var_names);
    for i = 1:numel(var_names)
        for j = 1:numel(fields)
            alias_norm = blobaudit.normalize_var_names(aliases.(fields{j}));
            if any(strcmp(norm_vars{i}, alias_norm))
                roles{i} = fields{j};
                break;
            end
        end
    end
end


function aliases = alias_map()
    aliases = struct();
    aliases.FrameIndex = {'FrameIndex', 'frame_index', 'ProcessedFrameIndex', 'Frame'};
    aliases.FrameTime = {'FrameTime', 'frame_time', 'Time', 't'};
    aliases.BlobID = {'BlobID', 'blob_id', 'ObjectID', 'LabelID', 'ComponentID'};
    aliases.Area = {'Area', 'MorphArea', 'BlobArea', 'area_px', 'PixelArea'};
    aliases.Perimeter = {'Perimeter', 'MorphPerimeter', 'BoundaryLength', 'perimeter_px'};
    aliases.MajorAxisLength = {'MajorAxisLength', 'MajorAxis', 'LongAxis', 'MajorAxisPx'};
    aliases.MinorAxisLength = {'MinorAxisLength', 'MinorAxis', 'ShortAxis', 'MinorAxisPx'};
    aliases.Orientation = {'Orientation', 'Angle', 'BlobAngle', 'MajorAxisAngle'};
    aliases.Circularity2D = {'Circularity2D', 'Circularity', 'MorphCircularity'};
    aliases.AspectRatio = {'AspectRatio', 'AR', 'AxisRatio'};
    aliases.Solidity = {'Solidity', 'solidity'};
    aliases.ConvexArea = {'ConvexArea', 'convex_area', 'HullArea'};
    aliases.ConvexHull = {'ConvexHull', 'convex_hull', 'HullXY'};
    aliases.ConvexPerimeter = {'ConvexPerimeter', 'MorphConvexPerimeter', 'HullPerimeter'};
    aliases.Boundary = {'Boundary', 'BoundaryXY', 'boundary_xy', 'Contour', 'ContourXY'};
    aliases.PixelIdxList = {'PixelIdxList', 'pixel_idx', 'PixelList'};
    aliases.MaskPath = {'MaskPath', 'mask_path', 'BlobMaskPath'};
    aliases.LabelPath = {'LabelPath', 'label_path', 'LabelMatrixPath'};
    aliases.TrackID = {'TrackID', 'track_id'};
    aliases.CentroidX = {'CentroidX', 'X', 'Centroid_1', 'CenterX', 'Centroid_X'};
    aliases.CentroidY = {'CentroidY', 'Y', 'Centroid_2', 'CenterY', 'Centroid_Y'};
    aliases.BoundingBox = {'BoundingBox', 'bbox', 'Box'};
end
