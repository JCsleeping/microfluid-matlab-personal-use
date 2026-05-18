function tracking = assess_tracking_feasibility(schema, geometry)
% ASSESS_TRACKING_FEASIBILITY  Assess ability to build blob trajectories.

    if has(schema, 'TrackID')
        status = 'READY_EXISTING_TRACKID';
    elseif geometry.has_existing_mask_label || has(schema, 'PixelIdxList')
        status = 'READY_FOR_IOU_TRACKING';
    elseif has_all(schema, {'CentroidX', 'CentroidY', 'Area', 'BoundingBox'})
        status = 'READY_FOR_APPROX_TRACKING';
    elseif has_all(schema, {'CentroidX', 'CentroidY', 'Area'})
        status = 'LOW_CONFIDENCE_TRACKING';
    else
        status = 'NOT_POSSIBLE';
    end
    tracking = struct('status', status);
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
