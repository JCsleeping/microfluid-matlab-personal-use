function write_audit_outputs(audit, audit_dir)
% WRITE_AUDIT_OUTPUTS  Write machine-readable audit outputs.

    outputs = audit.outputs;
    write_if_table(outputs, 'file_inventory', fullfile(audit_dir, 'file_inventory.csv'));
    write_if_table(outputs, 'source_priority_decision', fullfile(audit_dir, 'source_priority_decision.csv'));
    write_if_table(outputs, 'blob_schema_inventory', fullfile(audit_dir, 'blob_schema_inventory.csv'));
    write_if_table(outputs, 'frame_coverage', fullfile(audit_dir, 'frame_coverage_audit.csv'));
    write_if_table(outputs, 'chunk_integrity', fullfile(audit_dir, 'chunk_integrity_audit.csv'));
    write_if_table(outputs, 'csv_integrity', fullfile(audit_dir, 'csv_integrity_audit.csv'));
    write_if_table(outputs, 'geometry_source_audit', fullfile(audit_dir, 'geometry_source_audit.csv'));
    write_if_table(outputs, 'experiment_metadata', fullfile(audit_dir, 'experiment_metadata_audit.csv'));
    write_if_table(outputs, 'metric_feasibility', fullfile(audit_dir, 'metric_feasibility_matrix.csv'));
    write_if_table(outputs, 'literature_method_mapping', fullfile(audit_dir, 'literature_method_mapping.csv'));
    write_if_table(outputs, 'read_only_integrity', fullfile(audit_dir, 'read_only_integrity_audit.csv'));

    summary = build_summary(audit);
    blobaudit.write_text_file_utf8(fullfile(audit_dir, 'audit_summary.json'), blobaudit.json_encode_safe(summary));

    preview_dir = fullfile(audit_dir, 'previews');
    if ~isfolder(preview_dir)
        mkdir(preview_dir);
    end
    write_preview(outputs, 'blob_table_preview', fullfile(preview_dir, 'blob_table_preview.csv'));
    write_preview(outputs, 'manifest_preview', fullfile(preview_dir, 'manifest_preview.csv'));
    write_preview(outputs, 'missingness_preview', fullfile(preview_dir, 'missingness_preview.csv'));
end


function write_if_table(outputs, field, path)
    if isfield(outputs, field) && istable(outputs.(field))
        writetable(outputs.(field), path);
    else
        writetable(table(), path);
    end
end


function write_preview(outputs, field, path)
    if isfield(outputs, field) && istable(outputs.(field))
        writetable(outputs.(field), path);
    else
        writetable(table(), path);
    end
end


function summary = build_summary(audit)
    summary = struct();
    summary.overall_status = audit.overall_status;
    summary.status_flags = audit.status_flags;
    summary.env = audit.env;
    if isfield(audit, 'primary_source')
        summary.primary_source = audit.primary_source;
    end
    if isfield(audit, 'results_info')
        summary.has_results_mat = audit.results_info.has_results_mat;
        summary.has_config = audit.results_info.has_config;
        summary.has_nblobs_arr = audit.results_info.has_nblobs_arr;
        summary.last_completed_frame = audit.results_info.last_completed_frame;
        summary.has_frame_times = audit.results_info.has_frame_times;
        summary.has_pixel_scale = audit.results_info.has_pixel_scale;
    end
    if isfield(audit, 'tracking_info')
        summary.tracking_feasibility = audit.tracking_info.status;
    end
    if isfield(audit, 'errors')
        summary.errors = audit.errors;
    end
end
