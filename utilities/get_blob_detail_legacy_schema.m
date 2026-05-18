function schema = get_blob_detail_legacy_schema()
% GET_BLOB_DETAIL_LEGACY_SCHEMA  Canonical per-blob detail CSV schema.
%
% The final blob_detail_all_frames.csv keeps the historical FrameIndex and
% FrameTime columns, followed by the per-blob geometry columns produced by
% analyze_blob_geometry().

    schema.variable_names = {'FrameIndex', 'FrameTime', ...
        'BlobID', 'Area', 'Perimeter', 'Circularity', 'AspectRatio', ...
        'Eccentricity', 'Solidity', 'EquivDiameter', 'EquivRadius', ...
        'Compactness', 'EulerNumber', 'Centroid_X', 'Centroid_Y', ...
        'GangliaType', 'TopologyType'};

    schema.string_variables = {'GangliaType', 'TopologyType'};
    schema.empty_table = make_empty_blob_detail_table(schema);
end

