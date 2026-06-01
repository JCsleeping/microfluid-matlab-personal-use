function assert_geometry_schema_compatible(output_path, geometry_opts)
% ASSERT_GEOMETRY_SCHEMA_COMPATIBLE  Fail before mixing incompatible chunks.

    expected = make_geometry_schema(geometry_opts);
    schema_path = fullfile(output_path, 'status', 'geometry_schema.mat');

    if exist(schema_path, 'file') ~= 2
        if has_existing_blob_detail_outputs(output_path)
            error('geometry:schemaMissing', ...
                ['Existing blob-detail outputs were found without status/geometry_schema.mat. ' ...
                 'Use a fresh output directory or run an explicit schema migration.']);
        end
        return;
    end

    S = load(schema_path, 'geometry_schema');
    if ~isfield(S, 'geometry_schema')
        error('geometry:schemaMismatch', ...
            'Existing geometry schema manifest is missing geometry_schema.');
    end

    old_schema = S.geometry_schema;
    mismatches = {};

    if ~isfield(old_schema, 'GeometryMode') || ...
            ~strcmp(char(string(old_schema.GeometryMode)), expected.GeometryMode)
        mismatches{end+1} = 'GeometryMode'; %#ok<AGROW>
    end
    if ~isfield(old_schema, 'GeometrySchemaVersion') || ...
            ~strcmp(char(string(old_schema.GeometrySchemaVersion)), expected.GeometrySchemaVersion)
        mismatches{end+1} = 'GeometrySchemaVersion'; %#ok<AGROW>
    end
    if ~isfield(old_schema, 'ObjectConnectivity') || ...
            double(old_schema.ObjectConnectivity) ~= expected.ObjectConnectivity
        mismatches{end+1} = 'ObjectConnectivity'; %#ok<AGROW>
    end

    if ~isempty(mismatches)
        error('geometry:schemaMismatch', ...
            ['Existing output uses an incompatible geometry schema (%s). ' ...
             'Use a new output directory or run an explicit schema migration.'], ...
            strjoin(mismatches, ', '));
    end
end


function tf = has_existing_blob_detail_outputs(output_path)
    tf = false;
    chunks_dir = fullfile(output_path, 'blob_detail_chunks');
    if exist(chunks_dir, 'dir') == 7
        chunk_files = dir(fullfile(chunks_dir, 'blob_detail_*.mat'));
        if ~isempty(chunk_files)
            tf = true;
            return;
        end
    end

    csv_path = fullfile(output_path, 'blob_detail_all_frames.csv');
    if exist(csv_path, 'file') == 2
        tf = true;
    end
end
