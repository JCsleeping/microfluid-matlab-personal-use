function M = assess_metric_feasibility(catalog, schema, geometry, metadata, frame_info, env)
% ASSESS_METRIC_FEASIBILITY  Assign feasibility status to each catalog metric.

    n = height(catalog);
    current_status = cell(n, 1);
    missing_fields = cell(n, 1);
    missing_geometry = cell(n, 1);
    missing_metadata = cell(n, 1);
    can_compute_without_rerun = false(n, 1);
    requires_geometry_extraction = false(n, 1);
    requires_tracking = false(n, 1);
    requires_step4_rerun = false(n, 1);
    requires_full_pipeline_rerun = false(n, 1);

    for idx = 1:n
        metric = catalog.metric_id{idx};
        [status, miss_f, miss_g, miss_m] = decide(metric, schema, geometry, metadata, frame_info, env);
        current_status{idx} = status;
        missing_fields{idx} = miss_f;
        missing_geometry{idx} = miss_g;
        missing_metadata{idx} = miss_m;
        can_compute_without_rerun(idx) = any(strcmp(status, {'READY_EXISTING', 'READY_DERIVED', ...
            'READY_FROM_EXISTING_GEOMETRY_SOURCE'}));
        requires_geometry_extraction(idx) = strcmp(status, 'NEED_GEOMETRY_EXTRACTION_FROM_EXISTING_MASK');
        requires_tracking(idx) = strcmp(status, 'NEED_TRACKING');
        requires_step4_rerun(idx) = strcmp(status, 'NEED_RAW_FRAME_RERUN');
        requires_full_pipeline_rerun(idx) = strcmp(status, 'NEED_RAW_FRAME_RERUN') && ~geometry.has_existing_mask_label;
    end

    M = catalog;
    M.current_status = current_status;
    M.missing_fields = missing_fields;
    M.missing_geometry = missing_geometry;
    M.missing_metadata = missing_metadata;
    M.can_compute_without_rerun = can_compute_without_rerun;
    M.requires_geometry_extraction = requires_geometry_extraction;
    M.requires_tracking = requires_tracking;
    M.requires_step4_rerun = requires_step4_rerun;
    M.requires_full_pipeline_rerun = requires_full_pipeline_rerun;
end


function [status, missing_fields, missing_geometry, missing_metadata] = decide(metric, schema, geometry, metadata, frame_info, env)
    missing_fields = '';
    missing_geometry = '';
    missing_metadata = '';
    switch metric
        case 'area_px'
            [status, missing_fields] = existing_or_missing(schema, 'Area');
        case 'area_physical'
            if ~has(schema, 'Area')
                status = 'UNKNOWN'; missing_fields = 'Area';
            elseif ~metadata.has_pixel_scale
                status = 'NEED_EXPERIMENT_METADATA'; missing_metadata = 'pixel_size_um';
            else
                status = 'READY_DERIVED';
            end
        case 'equiv_diameter_2d'
            [status, missing_fields] = derived_if(schema, {'Area'});
        case 'perimeter'
            [status, missing_fields] = existing_or_missing(schema, 'Perimeter');
        case 'major_axis'
            [status, missing_fields] = existing_or_missing(schema, 'MajorAxisLength');
        case 'minor_axis'
            [status, missing_fields] = existing_or_missing(schema, 'MinorAxisLength');
        case 'aspect_ratio'
            if has(schema, 'AspectRatio')
                status = 'READY_EXISTING';
            else
                [status, missing_fields] = derived_if(schema, {'MajorAxisLength', 'MinorAxisLength'});
            end
        case 'orientation'
            [status, missing_fields] = existing_or_missing(schema, 'Orientation');
        case 'circularity_2d'
            if has(schema, 'Circularity2D')
                status = 'READY_EXISTING';
            else
                [status, missing_fields] = derived_if(schema, {'Area', 'Perimeter'});
            end
        case {'projected_sphericity_2d', 'regularity_2d'}
            [status, missing_fields] = derived_if(schema, {'Area', 'Perimeter'});
        case 'ellipse_perimeter_proxy'
            if has_all(schema, {'MajorAxisLength', 'MinorAxisLength'})
                status = 'READY_DERIVED';
            elseif has_all(schema, {'AspectRatio', 'Area'})
                status = 'READY_DERIVED';
            else
                status = 'UNKNOWN'; missing_fields = 'MajorAxisLength,MinorAxisLength or AspectRatio,Area';
            end
        case 'solidity'
            if has(schema, 'Solidity')
                status = 'READY_EXISTING';
            else
                [status, missing_fields] = derived_if(schema, {'Area', 'ConvexArea'});
            end
        case {'convex_perimeter', 'projected_roughness', 'angularity_proxy', 'boundary_fractal_dimension'}
            [status, missing_geometry] = geometry_status(geometry, env);
            if strcmp(metric, 'projected_roughness') && ~has(schema, 'Perimeter')
                missing_fields = append_missing(missing_fields, 'Perimeter');
            end
        case 'blob_count'
            if has(schema, 'FrameIndex') || ~isempty(frame_info.frame_coverage)
                status = 'READY_DERIVED';
            else
                status = 'UNKNOWN'; missing_fields = 'FrameIndex or nblobs_arr';
            end
        case 'total_area'
            [status, missing_fields] = derived_if(schema, {'Area', 'FrameIndex'});
        case {'size_distribution_slope', 'population_fractal_dimension'}
            [status, missing_fields] = derived_if(schema, {'Area'});
        case 'area_weighted_circularity'
            if has_all(schema, {'Area', 'Circularity2D'})
                status = 'READY_DERIVED';
            else
                status = 'UNKNOWN'; missing_fields = 'Area,Circularity2D';
            end
        case 'total_area_shrink_rate'
            if ~has_all(schema, {'Area', 'FrameIndex'})
                status = 'UNKNOWN'; missing_fields = 'Area,FrameIndex';
            elseif ~has(schema, 'FrameTime') && ~metadata.has_time
                status = 'NEED_EXPERIMENT_METADATA'; missing_metadata = 'FrameTime';
            else
                status = 'READY_DERIVED';
            end
        case {'per_blob_area_shrink_rate', 'normalized_shrink_rate', 'centroid_speed', 'split_merge_events'}
            if ~has(schema, 'TrackID')
                status = 'NEED_TRACKING';
            elseif any(strcmp(metric, {'per_blob_area_shrink_rate', 'normalized_shrink_rate'}))
                if ~has(schema, 'Area')
                    status = 'UNKNOWN'; missing_fields = 'Area';
                elseif ~has(schema, 'FrameTime') && ~metadata.has_time
                    status = 'NEED_EXPERIMENT_METADATA'; missing_metadata = 'FrameTime';
                else
                    status = 'READY_DERIVED';
                end
            elseif strcmp(metric, 'centroid_speed')
                if ~has_all(schema, {'CentroidX', 'CentroidY'})
                    status = 'UNKNOWN'; missing_fields = 'CentroidX,CentroidY';
                elseif ~has(schema, 'FrameTime') && ~metadata.has_time
                    status = 'NEED_EXPERIMENT_METADATA'; missing_metadata = 'FrameTime';
                else
                    status = 'READY_DERIVED';
                end
            else
                if geometry.has_existing_geometry || geometry.has_existing_mask_label
                    status = 'READY_DERIVED';
                else
                    status = 'NEED_BOUNDARY_OR_MASK'; missing_geometry = 'mask or geometry for split/merge events';
                end
            end
        case {'exposed_interface_length', 'dead_end_exposure_proxy'}
            if ~metadata.has_flow
                status = 'NEED_EXPERIMENT_METADATA'; missing_metadata = 'flow/pore geometry metadata';
            else
                [status, missing_geometry] = geometry_status(geometry, env);
            end
        case {'capillary_number', 'peclet_number', 'sherwood_proxy'}
            status = 'NEED_EXPERIMENT_METADATA';
            missing_metadata = 'transport physical metadata';
        otherwise
            status = 'UNKNOWN';
    end
end


function [status, missing] = existing_or_missing(schema, role)
    if has(schema, role)
        status = 'READY_EXISTING';
        missing = '';
    else
        status = 'UNKNOWN';
        missing = role;
    end
end


function [status, missing] = derived_if(schema, roles)
    if has_all(schema, roles)
        status = 'READY_DERIVED';
        missing = '';
    else
        status = 'UNKNOWN';
        missing = strjoin(roles(~cellfun(@(r) has(schema, r), roles)), ',');
    end
end


function [status, missing_geometry] = geometry_status(geometry, env)
    if geometry.has_existing_geometry
        status = 'READY_FROM_EXISTING_GEOMETRY_SOURCE';
        missing_geometry = '';
    elseif geometry.has_existing_mask_label
        if env.has_image_processing_toolbox
            status = 'NEED_GEOMETRY_EXTRACTION_FROM_EXISTING_MASK';
        else
            status = 'NEED_IMAGE_PROCESSING_TOOLBOX';
        end
        missing_geometry = 'extracted boundary/convex hull';
    elseif geometry.has_raw_frames
        status = 'NEED_RAW_FRAME_RERUN';
        missing_geometry = 'mask/label/boundary';
    else
        status = 'NEED_BOUNDARY_OR_MASK';
        missing_geometry = 'boundary/ConvexHull/PixelIdxList/mask/label';
    end
end


function tf = has(schema, role)
    tf = isfield(schema, 'has') && isfield(schema.has, role) && schema.has.(role);
end


function tf = has_all(schema, roles)
    tf = true;
    for idx = 1:numel(roles)
        tf = tf && has(schema, roles{idx});
    end
end


function txt = append_missing(txt, addition)
    if isempty(txt)
        txt = addition;
    else
        txt = [txt ',' addition];
    end
end
