function write_geometry_schema_manifest(output_path, geometry_opts)
% WRITE_GEOMETRY_SCHEMA_MANIFEST  Persist geometry schema provenance.

    status_dir = fullfile(output_path, 'status');
    if exist(status_dir, 'dir') ~= 7
        mkdir(status_dir);
    end

    geometry_schema = make_geometry_schema(geometry_opts);
    schema_path = fullfile(status_dir, 'geometry_schema.mat');
    tmp_path = fullfile(status_dir, 'geometry_schema.tmp.mat');

    save(tmp_path, 'geometry_schema', '-v7');
    atomic_replace_file(tmp_path, schema_path, @(p) validate_schema_file(p));
end


function validate_schema_file(path)
    S = load(path, 'geometry_schema');
    if ~isfield(S, 'geometry_schema') || ...
            ~isfield(S.geometry_schema, 'GeometryMode') || ...
            ~isfield(S.geometry_schema, 'GeometrySchemaVersion')
        error('write_geometry_schema_manifest:invalidSchema', ...
            'Geometry schema manifest validation failed.');
    end
end
