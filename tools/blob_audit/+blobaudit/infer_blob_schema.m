function info = infer_blob_schema(schema_source)
% INFER_BLOB_SCHEMA  Infer semantic roles and missingness from blob table.

    T = schema_source.table;
    info = struct();
    info.source_type = schema_source.type;
    info.has = struct();
    info.role_to_variable = struct();
    info.variable_names = {};

    if isempty(T) || ~istable(T) || width(T) == 0
        info.schema_inventory = empty_schema_inventory();
        return;
    end

    names = T.Properties.VariableNames;
    roles = blobaudit.classify_variable_semantics(names);
    info.variable_names = names;

    rows = cell(numel(names), 10);
    for idx = 1:numel(names)
        v = T.(names{idx});
        role = roles{idx};
        if ~strcmp(role, 'Unknown')
            info.has.(role) = true;
            info.role_to_variable.(role) = names{idx};
        end
        [missing_fraction, nan_fraction, min_value, max_value, example_value] = summarize_variable(v);
        rows(idx, :) = {names{idx}, class(v), role, isnumeric(v), is_text(v), ...
            missing_fraction, nan_fraction, min_value, max_value, example_value};
    end

    variable_name = rows(:, 1);
    matlab_class = rows(:, 2);
    semantic_role = rows(:, 3);
    is_numeric = cell2mat(rows(:, 4));
    is_text_col = cell2mat(rows(:, 5));
    missing_fraction = cell2mat(rows(:, 6));
    nan_fraction = cell2mat(rows(:, 7));
    min_value = cell2mat(rows(:, 8));
    max_value = cell2mat(rows(:, 9));
    example_value = rows(:, 10);
    supports_metrics = ~strcmp(semantic_role, 'Unknown');
    info.schema_inventory = table(variable_name, matlab_class, semantic_role, ...
        is_numeric, is_text_col, missing_fraction, nan_fraction, min_value, ...
        max_value, example_value, supports_metrics, ...
        'VariableNames', {'variable_name', 'matlab_class', 'semantic_role', ...
        'is_numeric', 'is_text', 'missing_fraction', 'nan_fraction', ...
        'min_value', 'max_value', 'example_value', 'supports_metrics'});
end


function [missing_fraction, nan_fraction, min_value, max_value, example_value] = summarize_variable(v)
    n = numel(v);
    missing_fraction = 0;
    nan_fraction = 0;
    min_value = NaN;
    max_value = NaN;
    example_value = '';
    if n == 0
        return;
    end
    if isnumeric(v)
        nan_fraction = sum(isnan(v(:))) / n;
        missing_fraction = nan_fraction;
        finite_v = v(isfinite(v));
        if ~isempty(finite_v)
            min_value = min(finite_v(:));
            max_value = max(finite_v(:));
        end
        example_value = num2str(v(1));
    elseif iscell(v)
        missing_fraction = sum(cellfun(@isempty, v(:))) / n;
        if ~isempty(v{1})
            example_value = char(string(v{1}));
        end
    elseif isstring(v)
        missing_fraction = sum(ismissing(v(:))) / n;
        example_value = char(v(1));
    elseif islogical(v)
        min_value = double(min(v(:)));
        max_value = double(max(v(:)));
        example_value = num2str(v(1));
    else
        try
            example_value = char(string(v(1)));
        catch
            example_value = class(v);
        end
    end
end


function tf = is_text(v)
    tf = iscellstr(v) || isstring(v) || ischar(v) || iscell(v);
end


function T = empty_schema_inventory()
    T = table(cell(0,1), cell(0,1), cell(0,1), false(0,1), false(0,1), ...
        zeros(0,1), zeros(0,1), zeros(0,1), zeros(0,1), cell(0,1), false(0,1), ...
        'VariableNames', {'variable_name', 'matlab_class', 'semantic_role', ...
        'is_numeric', 'is_text', 'missing_fraction', 'nan_fraction', ...
        'min_value', 'max_value', 'example_value', 'supports_metrics'});
end
