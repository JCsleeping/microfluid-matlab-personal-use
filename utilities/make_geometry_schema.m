function geometry_schema = make_geometry_schema(geometry_opts)
% MAKE_GEOMETRY_SCHEMA  Canonical geometry schema manifest struct.

    if nargin < 1 || isempty(geometry_opts)
        geometry_opts = struct();
    end

    if ~isfield(geometry_opts, 'mode') || isempty(geometry_opts.mode)
        geometry_opts.mode = 'core_only';
    end
    if ~isfield(geometry_opts, 'object_connectivity') || isempty(geometry_opts.object_connectivity)
        geometry_opts.object_connectivity = 8;
    end
    if ~isfield(geometry_opts, 'schema_version') || isempty(geometry_opts.schema_version)
        if strcmp(char(string(geometry_opts.mode)), 'legacy_fullframe')
            geometry_opts.schema_version = 'geometry_v1_legacy_fullframe';
        else
            geometry_opts.schema_version = 'geometry_v2_core_only';
        end
    end
    if ~isfield(geometry_opts, 'include_heavy_shape_props') || isempty(geometry_opts.include_heavy_shape_props)
        geometry_opts.include_heavy_shape_props = true;
    end

    mode = char(string(geometry_opts.mode));
    geometry_schema = struct();
    geometry_schema.GeometryMode = mode;
    geometry_schema.GeometrySchemaVersion = char(string(geometry_opts.schema_version));
    geometry_schema.ObjectConnectivity = double(geometry_opts.object_connectivity);
    geometry_schema.HoleClassificationComputed = strcmp(mode, 'legacy_fullframe');
    geometry_schema.IncludeHeavyShapeProps = logical(geometry_opts.include_heavy_shape_props);
    geometry_schema.CreatedAt = datestr(now, 30);
end
