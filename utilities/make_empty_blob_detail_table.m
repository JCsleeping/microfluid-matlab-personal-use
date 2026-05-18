function T = make_empty_blob_detail_table(schema)
% MAKE_EMPTY_BLOB_DETAIL_TABLE  Build a zero-row table with canonical types.

    if nargin < 1 || isempty(schema)
        schema = get_blob_detail_legacy_schema();
    end

    vars = cell(1, numel(schema.variable_names));
    for idx = 1:numel(schema.variable_names)
        name = schema.variable_names{idx};
        if ismember(name, schema.string_variables)
            vars{idx} = strings(0, 1);
        else
            vars{idx} = zeros(0, 1);
        end
    end

    T = table(vars{:}, 'VariableNames', schema.variable_names);
end

