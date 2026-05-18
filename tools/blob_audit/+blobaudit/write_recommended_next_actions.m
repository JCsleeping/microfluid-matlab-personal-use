function write_recommended_next_actions(audit, audit_dir)
% WRITE_RECOMMENDED_NEXT_ACTIONS  Write ordered operational decision.

    [primary, secondary, not_rec] = decide_actions(audit);
    lines = {};
    lines{end+1} = '# Recommended Next Actions';
    lines{end+1} = '';
    lines{end+1} = '## Primary recommendation';
    lines{end+1} = primary;
    lines{end+1} = '';
    lines{end+1} = '## Secondary recommendation';
    lines{end+1} = secondary;
    lines{end+1} = '';
    lines{end+1} = '## Not recommended at this stage';
    lines{end+1} = not_rec;
    lines{end+1} = '';
    lines{end+1} = ['Recommended action: ' extract_case(primary)];
    blobaudit.write_text_file_utf8(fullfile(audit_dir, 'recommended_next_actions.md'), strjoin(lines, newline));
end


function [primary, secondary, not_rec] = decide_actions(audit)
    has_table = any(strcmp(audit.primary_source.type, {'chunks', 'csv'}));
    has_area = has_sem(audit.schema_info, 'Area');
    has_perim = has_sem(audit.schema_info, 'Perimeter');
    has_frame = has_sem(audit.schema_info, 'FrameIndex');
    has_time = has_sem(audit.schema_info, 'FrameTime') || audit.metadata_info.has_time;

    if has_table && has_area && has_perim && has_frame && has_time
        primary = 'Case A: Proceed with Level A morphology post-processing. No pipeline rerun required.';
    elseif audit.geometry_info.has_existing_mask_label && has_table
        primary = 'Case B: Run a geometry extraction stage from existing masks/labels. Full pipeline rerun is not required.';
    elseif ~has_table && audit.geometry_info.has_raw_frames
        primary = 'Case D: Rerun Step 4 or blob-detail extraction only.';
    elseif audit.geometry_info.has_raw_frames
        primary = 'Case E: Rerun segmentation-related pipeline, possibly full pipeline.';
    else
        primary = 'Case F: Only macro-level trends can be analyzed. Per-blob morphology, boundary roughness, fractal dimension, and tracking are not recoverable from current outputs.';
    end

    if ~has_sem(audit.schema_info, 'TrackID') && any(strcmp(audit.tracking_info.status, ...
            {'READY_FOR_IOU_TRACKING', 'READY_FOR_APPROX_TRACKING', 'LOW_CONFIDENCE_TRACKING'}))
        secondary = 'Case C: Implement tracking post-processing. Do not rerun pipeline unless geometry sources are missing.';
    elseif audit.geometry_info.has_existing_mask_label && ~audit.geometry_info.has_existing_geometry
        secondary = 'Case B: Geometry extraction from existing masks/labels can unlock boundary-level metrics.';
    else
        secondary = 'No secondary action is higher priority than resolving metadata or geometry gaps listed in the matrix.';
    end
    not_rec = 'Do not compute final morphology metrics, statistical models, or paper figures during this audit stage.';
end


function tf = has_sem(schema_info, role)
    tf = isfield(schema_info, 'has') && isfield(schema_info.has, role) && schema_info.has.(role);
end


function c = extract_case(text)
    tokens = regexp(text, 'Case ([A-F])', 'tokens', 'once');
    if isempty(tokens)
        c = 'UNKNOWN';
    else
        c = tokens{1};
    end
end
