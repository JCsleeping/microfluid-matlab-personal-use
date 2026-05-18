function info = audit_geometry_sources(inventory, schema_info, opts, env)
% AUDIT_GEOMETRY_SOURCES  Locate boundary, mask, label, and raw geometry sources.

    has_boundary = has_sem(schema_info, 'Boundary');
    has_hull = has_sem(schema_info, 'ConvexHull');
    has_pixel = has_sem(schema_info, 'PixelIdxList');
    has_mask_path = has_sem(schema_info, 'MaskPath');
    has_label_path = has_sem(schema_info, 'LabelPath');
    mask_files = strcmp(inventory.file_type, 'mask_image');
    label_files = strcmp(inventory.file_type, 'label_mat');
    raw_files = strcmp(inventory.file_type, 'raw_image');
    user_mask = ~isempty(char(opts.MaskDir)) && isfolder(char(opts.MaskDir));
    user_label = ~isempty(char(opts.LabelDir)) && isfolder(char(opts.LabelDir));

    rows = {};
    rows = add_row(rows, 'blob_table_boundary', has_boundary, role_path(schema_info, 'Boundary'), ...
        'table_column', count_role(schema_info, 'Boundary'), false, true, true, true, false, false, '');
    rows = add_row(rows, 'blob_table_convex_hull', has_hull, role_path(schema_info, 'ConvexHull'), ...
        'table_column', count_role(schema_info, 'ConvexHull'), true, false, true, true, false, false, '');
    rows = add_row(rows, 'blob_table_pixel_idx', has_pixel, role_path(schema_info, 'PixelIdxList'), ...
        'table_column', count_role(schema_info, 'PixelIdxList'), true, true, true, true, false, false, '');
    rows = add_row(rows, 'mask_files', any(mask_files) || user_mask || has_mask_path, path_list(inventory, mask_files), ...
        'mask', sum(mask_files), true, true, true, true, true, false, toolbox_note(env));
    rows = add_row(rows, 'label_files', any(label_files) || user_label || has_label_path, path_list(inventory, label_files), ...
        'label', sum(label_files), true, true, true, true, true, false, toolbox_note(env));
    rows = add_row(rows, 'raw_frames', any(raw_files), path_list(inventory, raw_files), ...
        'raw_image', sum(raw_files), false, false, false, true, false, true, '');

    geometry_source = rows(:, 1);
    exists_col = cell2mat(rows(:, 2));
    path_or_column = rows(:, 3);
    data_type = rows(:, 4);
    n_files_or_rows = cell2mat(rows(:, 5));
    supports_convex_perimeter = cell2mat(rows(:, 6));
    supports_boundary_fractal_dimension = cell2mat(rows(:, 7));
    supports_tracking_iou = cell2mat(rows(:, 8));
    supports_qc_plot = cell2mat(rows(:, 9));
    requires_geometry_extraction = cell2mat(rows(:, 10));
    requires_step4_rerun = cell2mat(rows(:, 11));
    notes = rows(:, 12);
    geometry_source_audit = table(geometry_source, exists_col, path_or_column, data_type, ...
        n_files_or_rows, supports_convex_perimeter, supports_boundary_fractal_dimension, ...
        supports_tracking_iou, supports_qc_plot, requires_geometry_extraction, ...
        requires_step4_rerun, notes, ...
        'VariableNames', {'geometry_source', 'exists', 'path_or_column', 'data_type', ...
        'n_files_or_rows', 'supports_convex_perimeter', ...
        'supports_boundary_fractal_dimension', 'supports_tracking_iou', ...
        'supports_qc_plot', 'requires_geometry_extraction', 'requires_step4_rerun', 'notes'});

    info = struct();
    info.geometry_source_audit = geometry_source_audit;
    info.has_existing_geometry = has_boundary || has_hull || has_pixel;
    info.has_boundary = has_boundary;
    info.has_hull = has_hull;
    info.has_pixel_idx = has_pixel;
    info.has_existing_mask_label = any(mask_files) || any(label_files) || user_mask || user_label || has_mask_path || has_label_path;
    info.has_raw_frames = any(raw_files);
    info.has_boundary_or_mask = info.has_existing_geometry || info.has_existing_mask_label;
end


function rows = add_row(rows, source, exists_col, path, type, n, convex, fractal, tracking, qc, extraction, rerun, notes)
    rows(end + 1, :) = {source, exists_col, path, type, n, convex, fractal, tracking, qc, extraction, rerun, notes};
end


function tf = has_sem(schema_info, role)
    tf = isfield(schema_info, 'has') && isfield(schema_info.has, role) && schema_info.has.(role);
end


function n = count_role(schema_info, role)
    if has_sem(schema_info, role)
        n = 1;
    else
        n = 0;
    end
end


function p = role_path(schema_info, role)
    if has_sem(schema_info, role) && isfield(schema_info.role_to_variable, role)
        p = schema_info.role_to_variable.(role);
    else
        p = '';
    end
end


function txt = path_list(inventory, mask)
    values = inventory.path(mask);
    if isempty(values)
        txt = '';
    else
        txt = strjoin(values(:).', '; ');
    end
end


function note = toolbox_note(env)
    if env.has_image_processing_toolbox
        note = '';
    else
        note = 'Image Processing Toolbox not available';
    end
end
