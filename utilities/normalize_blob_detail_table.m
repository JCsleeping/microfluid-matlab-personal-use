function T = normalize_blob_detail_table(blob_table, frame_index, frame_time, schema)
% NORMALIZE_BLOB_DETAIL_TABLE  Convert a per-frame blob table to CSV schema.

    if nargin < 4 || isempty(schema)
        schema = get_blob_detail_legacy_schema();
    end

    if nargin < 1 || isempty(blob_table)
        T = make_empty_blob_detail_table(schema);
        return;
    end

    if ~istable(blob_table)
        error('normalize_blob_detail_table:invalidInput', ...
            'blob_table must be a table.');
    end

    n = height(blob_table);
    if n == 0
        T = make_empty_blob_detail_table(schema);
        return;
    end

    vars = cell(1, numel(schema.variable_names));
    for idx = 1:numel(schema.variable_names)
        name = schema.variable_names{idx};
        if strcmp(name, 'FrameIndex')
            value = repmat(double(frame_index), n, 1);
        elseif strcmp(name, 'FrameTime')
            value = repmat(double(frame_time), n, 1);
        elseif ismember(name, blob_table.Properties.VariableNames)
            value = blob_table.(name);
            if ismember(name, schema.string_variables)
                value = reshape(string(value), [], 1);
            else
                value = reshape(double(value), [], 1);
            end
        else
            if ismember(name, schema.string_variables)
                value = strings(n, 1);
            else
                value = nan(n, 1);
            end
        end
        vars{idx} = value;
    end

    T = table(vars{:}, 'VariableNames', schema.variable_names);
end
