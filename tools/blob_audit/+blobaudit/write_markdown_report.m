function write_markdown_report(audit, audit_dir)
% WRITE_MARKDOWN_REPORT  Human-readable audit report.

    lines = {};
    lines{end+1} = '# Blob Morphology Gap Audit Report';
    lines{end+1} = '';
    lines{end+1} = '## 1. Input and Environment';
    lines{end+1} = bullet('root output dir', audit.env.root_output_dir);
    lines{end+1} = bullet('MATLAB version', audit.env.matlab_version);
    lines{end+1} = bullet('platform', audit.env.platform);
    lines{end+1} = bullet('audit timestamp', audit.env.timestamp);
    lines{end+1} = bullet('overall status', audit.overall_status);
    lines{end+1} = '';
    lines{end+1} = '## 2. Read-Only Integrity';
    lines{end+1} = summary_line(audit.outputs.read_only_integrity, 'modified', 'non-audit files modified');
    lines{end+1} = '';
    lines{end+1} = '## 3. Source Discovery';
    lines{end+1} = count_line(audit.outputs.file_inventory, 'blob_chunk_mat', 'chunks found');
    lines{end+1} = count_line(audit.outputs.file_inventory, 'blob_csv', 'CSV found');
    lines{end+1} = count_line(audit.outputs.file_inventory, 'results_mat', 'results MAT found');
    lines{end+1} = count_line(audit.outputs.file_inventory, 'mask_image', 'masks found');
    lines{end+1} = count_line(audit.outputs.file_inventory, 'label_mat', 'labels found');
    lines{end+1} = count_line(audit.outputs.file_inventory, 'raw_image', 'raw frames found');
    lines{end+1} = '';
    lines{end+1} = '## 4. Primary Source Decision';
    lines{end+1} = bullet('selected source', audit.primary_source.type);
    lines{end+1} = bullet('source path', audit.primary_source.path);
    lines{end+1} = bullet('trust level', audit.primary_source.trust_level);
    lines{end+1} = '';
    lines{end+1} = '## 5. Chunk Integrity';
    lines{end+1} = table_count_summary(audit.outputs.chunk_integrity);
    lines{end+1} = '';
    lines{end+1} = '## 6. CSV Integrity';
    if isfield(audit.outputs, 'csv_integrity') && height(audit.outputs.csv_integrity) > 0
        lines{end+1} = bullet('CSV read mode', audit.outputs.csv_integrity.csv_read_mode{1});
        lines{end+1} = bullet('CSV read ok', logical_text(audit.outputs.csv_integrity.csv_read_ok(1)));
    else
        lines{end+1} = '- No blob CSV found.';
    end
    lines{end+1} = '';
    lines{end+1} = '## 7. Blob Table Schema';
    lines{end+1} = schema_summary(audit.outputs.blob_schema_inventory);
    lines{end+1} = '';
    lines{end+1} = '## 8. Frame Coverage';
    lines{end+1} = table_count_summary(audit.outputs.frame_coverage);
    lines{end+1} = '';
    lines{end+1} = '## 9. Geometry Availability';
    lines{end+1} = geometry_sentence(audit.geometry_info);
    lines{end+1} = '';
    lines{end+1} = '## 10. Experiment Metadata Availability';
    lines{end+1} = metadata_summary(audit.outputs.experiment_metadata);
    lines{end+1} = '';
    lines{end+1} = '## 11. Metric Feasibility Summary';
    lines = append_metric_lists(lines, audit.outputs.metric_feasibility);
    lines{end+1} = '';
    lines{end+1} = '## 12. Tracking Feasibility';
    lines{end+1} = bullet('tracking feasibility', audit.tracking_info.status);
    lines{end+1} = '';
    lines{end+1} = '## 13. Literature Method Mapping';
    lines{end+1} = 'Static literature mapping is written to `literature_method_mapping.csv`.';
    lines{end+1} = '';
    lines{end+1} = '## 14. Recommended Next Actions';
    lines{end+1} = 'See `recommended_next_actions.md` for the ordered decision.';
    lines{end+1} = '';
    lines{end+1} = '## 15. Limitations';
    lines{end+1} = '- This audit does not compute final morphology metrics.';
    lines{end+1} = '- This audit does not rerun segmentation or Step 4.';
    lines{end+1} = '- 2D projected morphology must not be interpreted as true 3D morphology.';
    lines{end+1} = '- Circularity2D is not Wadell roundness.';
    lines{end+1} = '- Boundary roughness and fractal dimension require mask/boundary data and are sensitive to segmentation.';
    lines{end+1} = '- Tracking feasibility does not guarantee tracking correctness.';

    blobaudit.write_text_file_utf8(fullfile(audit_dir, 'audit_report.md'), strjoin(lines, newline));
end


function txt = bullet(k, v)
    txt = sprintf('- %s: %s', k, char(string(v)));
end


function txt = count_line(T, type, label)
    if isempty(T) || height(T) == 0
        n = 0;
    else
        n = sum(strcmp(T.file_type, type));
    end
    txt = sprintf('- %s: %d', label, n);
end


function txt = summary_line(T, col, label)
    if isempty(T) || height(T) == 0
        n = 0;
    else
        n = sum(T.(col));
    end
    txt = sprintf('- %s: %d', label, n);
end


function txt = table_count_summary(T)
    if isempty(T) || height(T) == 0
        txt = '- No rows.';
    else
        txt = sprintf('- Rows audited: %d', height(T));
    end
end


function txt = schema_summary(T)
    if isempty(T) || height(T) == 0
        txt = '- No blob table schema available.';
    else
        roles = T.semantic_role(~strcmp(T.semantic_role, 'Unknown'));
        txt = ['- Recognized fields: ' strjoin(unique(roles).', ', ')];
    end
end


function txt = geometry_sentence(g)
    if g.has_existing_geometry
        txt = 'Boundary-level metrics are directly computable from existing blob table geometry.';
    elseif g.has_existing_mask_label
        txt = 'Boundary-level metrics are computable after geometry extraction from existing mask/label files.';
    elseif g.has_raw_frames
        txt = 'Boundary-level metrics require rerunning segmentation or Step 4.';
    else
        txt = 'Boundary-level metrics are not recoverable from current outputs.';
    end
end


function txt = metadata_summary(T)
    if isempty(T) || height(T) == 0
        txt = '- No metadata audited.';
    else
        txt = sprintf('- Metadata found: %d of %d keys.', sum(T.found), height(T));
    end
end


function lines = append_metric_lists(lines, M)
    statuses = {
        'READY_EXISTING', 'Directly computable now';
        'READY_DERIVED', 'Computable after scalar post-processing';
        'NEED_GEOMETRY_EXTRACTION_FROM_EXISTING_MASK', 'Requires geometry extraction from existing mask/label';
        'NEED_TRACKING', 'Requires tracking';
        'NEED_EXPERIMENT_METADATA', 'Requires metadata';
        'NEED_RAW_FRAME_RERUN', 'Requires Step 4 or segmentation rerun';
        'NOT_RECOMMENDED', 'Not recommended at this stage'
        };
    for idx = 1:size(statuses, 1)
        lines{end+1} = ['### ' statuses{idx, 2}]; %#ok<AGROW>
        mask = strcmp(M.current_status, statuses{idx, 1});
        if any(mask)
            vals = M.metric_id(mask);
            for j = 1:numel(vals)
                lines{end+1} = ['- ' vals{j}]; %#ok<AGROW>
            end
        else
            lines{end+1} = '- None identified.'; %#ok<AGROW>
        end
    end
end


function txt = logical_text(tf)
    if tf, txt = 'true'; else, txt = 'false'; end
end
