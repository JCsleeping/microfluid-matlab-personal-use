function audit = run_blob_gap_audit(root_output_dir, varargin)
% RUN_BLOB_GAP_AUDIT  Read-only audit for blob morphology data availability.

    parser = inputParser();
    parser.addRequired('root_output_dir', @(x) ischar(x) || isstring(x));
    parser.addParameter('RawImageDir', '', @(x) ischar(x) || isstring(x));
    parser.addParameter('MaskDir', '', @(x) ischar(x) || isstring(x));
    parser.addParameter('LabelDir', '', @(x) ischar(x) || isstring(x));
    parser.addParameter('ExperimentMetadataFile', '', @(x) ischar(x) || isstring(x));
    parser.addParameter('MaxChunkSamplesForPreview', 5, @(x) isnumeric(x) && isscalar(x) && x >= 0);
    parser.addParameter('MaxRowsPreview', 20, @(x) isnumeric(x) && isscalar(x) && x >= 0);
    parser.addParameter('MaxCsvBytesForFullRead', 512 * 1024^2, @(x) isnumeric(x) && isscalar(x) && x >= 0);
    parser.addParameter('MaxCsvRowsForProfiling', 200000, @(x) isnumeric(x) && isscalar(x) && x >= 0);
    parser.addParameter('ComputeFileHashes', false, @(x) islogical(x) && isscalar(x));
    parser.addParameter('WriteReport', true, @(x) islogical(x) && isscalar(x));
    parser.addParameter('StrictMode', false, @(x) islogical(x) && isscalar(x));
    parser.parse(root_output_dir, varargin{:});
    opts = parser.Results;

    root_output_dir = char(root_output_dir);
    assert(isfolder(root_output_dir), 'root_output_dir does not exist.');

    this_dir = fileparts(mfilename('fullpath'));
    addpath(this_dir);
    addpath(fileparts(this_dir));

    timestamp = datestr(now, 'yyyymmdd_HHMMSS');
    audit_dir = fullfile(root_output_dir, ['audit_blob_morphology_gap_' timestamp]);
    suffix = 0;
    while isfolder(audit_dir)
        suffix = suffix + 1;
        audit_dir = fullfile(root_output_dir, sprintf('audit_blob_morphology_gap_%s_%02d', timestamp, suffix));
    end
    mkdir(audit_dir);
    mkdir(fullfile(audit_dir, 'previews'));

    audit = struct();
    audit.params = opts;
    audit.env = struct();
    audit.env.matlab_version = version;
    audit.env.platform = computer;
    audit.env.root_output_dir = root_output_dir;
    audit.env.timestamp = datestr(now, 30);
    audit.env.audit_dir = audit_dir;
    audit.env.has_image_processing_toolbox = license('test', 'image_toolbox');
    audit.status_flags = {};
    audit.overall_status = 'PASS';
    audit.errors = {};
    audit.outputs = struct();

    try
        audit.outputs.file_inventory = blobaudit.discover_files(root_output_dir, opts);
        before_state = blobaudit.snapshot_file_state(audit.outputs.file_inventory, opts.ComputeFileHashes);

        [audit.primary_source, audit.outputs.source_priority_decision] = ...
            blobaudit.choose_primary_blob_source(audit.outputs.file_inventory);

        audit.results_info = blobaudit.inspect_results_mat(audit.outputs.file_inventory);

        audit.chunk_info = blobaudit.inspect_blob_chunks(audit.outputs.file_inventory, audit.results_info);
        audit.outputs.chunk_integrity = audit.chunk_info.chunk_integrity;

        audit.csv_info = blobaudit.inspect_blob_csv(audit.outputs.file_inventory, opts);
        audit.outputs.csv_integrity = audit.csv_info.csv_integrity;

        schema_source = choose_schema_source(audit);
        audit.schema_info = blobaudit.infer_blob_schema(schema_source);
        audit.outputs.blob_schema_inventory = audit.schema_info.schema_inventory;

        audit.frame_info = blobaudit.check_frame_coverage(audit, schema_source);
        audit.outputs.frame_coverage = audit.frame_info.frame_coverage;

        audit.geometry_info = blobaudit.audit_geometry_sources(audit.outputs.file_inventory, audit.schema_info, opts, audit.env);
        audit.outputs.geometry_source_audit = audit.geometry_info.geometry_source_audit;

        audit.metadata_info = blobaudit.audit_experiment_metadata(audit, opts);
        audit.outputs.experiment_metadata = audit.metadata_info.experiment_metadata;

        audit.metric_catalog = blobaudit.build_metric_catalog();
        audit.outputs.metric_feasibility = blobaudit.assess_metric_feasibility( ...
            audit.metric_catalog, audit.schema_info, audit.geometry_info, audit.metadata_info, audit.frame_info, audit.env);

        audit.tracking_info = blobaudit.assess_tracking_feasibility(audit.schema_info, audit.geometry_info);

        audit.outputs.literature_method_mapping = blobaudit.write_literature_method_mapping(audit_dir);

        audit = update_status_flags(audit);

        after_state = blobaudit.snapshot_file_state(audit.outputs.file_inventory, opts.ComputeFileHashes);
        audit.outputs.read_only_integrity = blobaudit.check_read_only_integrity(before_state, after_state);
        if any(audit.outputs.read_only_integrity.modified)
            audit.status_flags = unique([audit.status_flags, {'FAIL_READ_ONLY_VIOLATION'}], 'stable');
        end
        audit = update_overall_status(audit);

        blobaudit.write_audit_outputs(audit, audit_dir);
        if opts.WriteReport
            blobaudit.write_markdown_report(audit, audit_dir);
            blobaudit.write_recommended_next_actions(audit, audit_dir);
        end
    catch ME
        audit.errors{end + 1} = ME.message;
        audit.status_flags = unique([audit.status_flags, {'FAIL_INTERNAL_ERROR'}], 'stable');
        audit = update_overall_status(audit);
        ensure_minimal_outputs(audit, audit_dir);
        blobaudit.write_audit_outputs(audit, audit_dir);
        if opts.WriteReport
            blobaudit.write_markdown_report(audit, audit_dir);
            blobaudit.write_recommended_next_actions(audit, audit_dir);
        end
        if opts.StrictMode
            error('run_blob_gap_audit:strictModeFailure', ...
                'Blob gap audit failed in StrictMode: %s', ME.message);
        end
        return;
    end

    if opts.StrictMode && any(strncmp(audit.status_flags, 'FAIL_', 5))
        error('run_blob_gap_audit:strictModeFailure', ...
            'Blob gap audit failed in StrictMode with status %s.', audit.overall_status);
    end
    if opts.StrictMode && any(strcmp(audit.status_flags, 'WARN_NO_BLOB_SOURCE'))
        error('run_blob_gap_audit:strictModeFailure', ...
            'Blob gap audit found no usable blob source in StrictMode.');
    end
end


function schema_source = choose_schema_source(audit)
    schema_source = struct('type', 'none', 'table', table(), 'manifest', table());
    if strcmp(audit.primary_source.type, 'chunks') && isfield(audit.chunk_info, 'blob_table')
        schema_source.type = 'chunks';
        schema_source.table = audit.chunk_info.blob_table;
        schema_source.manifest = audit.chunk_info.manifest;
    elseif strcmp(audit.primary_source.type, 'csv') && isfield(audit.csv_info, 'table')
        schema_source.type = 'csv';
        schema_source.table = audit.csv_info.table;
        schema_source.manifest = table();
    end
end


function audit = update_status_flags(audit)
    flags = audit.status_flags;
    if strcmp(audit.primary_source.type, 'none')
        flags{end + 1} = 'WARN_NO_BLOB_SOURCE';
    elseif strcmp(audit.primary_source.type, 'csv')
        flags{end + 1} = 'WARN_CSV_ONLY_LEGACY';
    end
    if isfield(audit.chunk_info, 'has_fatal_integrity_error') && audit.chunk_info.has_fatal_integrity_error
        flags{end + 1} = 'FAIL_CHUNK_INTEGRITY';
    end
    if strcmp(audit.primary_source.type, 'csv') && isfield(audit.csv_info, 'read_ok') && ~audit.csv_info.read_ok
        flags{end + 1} = 'FAIL_CSV_UNREADABLE';
    end
    if isfield(audit.frame_info, 'has_fatal_coverage_error') && audit.frame_info.has_fatal_coverage_error
        flags{end + 1} = 'FAIL_FRAME_COVERAGE';
    end
    if isfield(audit.geometry_info, 'has_boundary_or_mask') && ~audit.geometry_info.has_boundary_or_mask
        flags{end + 1} = 'WARN_GEOMETRY_INCOMPLETE';
    end
    if isfield(audit.metadata_info, 'is_incomplete') && audit.metadata_info.is_incomplete
        flags{end + 1} = 'WARN_METADATA_INCOMPLETE';
    end
    audit.status_flags = unique(flags, 'stable');
    audit = update_overall_status(audit);
end


function audit = update_overall_status(audit)
    flags = audit.status_flags;
    if isempty(flags)
        audit.overall_status = 'PASS';
        return;
    end
    fail_flags = flags(strncmp(flags, 'FAIL_', 5));
    warn_flags = flags(strncmp(flags, 'WARN_', 5));
    if ~isempty(fail_flags)
        audit.overall_status = fail_flags{1};
    elseif ~isempty(warn_flags)
        audit.overall_status = warn_flags{1};
    else
        audit.overall_status = 'PASS';
    end
end


function ensure_minimal_outputs(audit, audit_dir)
    if ~isfield(audit, 'outputs')
        audit.outputs = struct();
    end
    names = {'file_inventory', 'source_priority_decision', 'blob_schema_inventory', ...
        'frame_coverage', 'chunk_integrity', 'csv_integrity', 'geometry_source_audit', ...
        'experiment_metadata', 'metric_feasibility', 'literature_method_mapping', ...
        'read_only_integrity'};
    for idx = 1:numel(names)
        if ~isfield(audit.outputs, names{idx})
            audit.outputs.(names{idx}) = table();
        end
    end
    if ~isfolder(fullfile(audit_dir, 'previews'))
        mkdir(fullfile(audit_dir, 'previews'));
    end
end
