function normalized = normalize_var_names(names)
% NORMALIZE_VAR_NAMES  Case-insensitive variable-name normalization.

    if ischar(names) || isstring(names)
        names = cellstr(names);
    end
    normalized = cell(size(names));
    for idx = 1:numel(names)
        normalized{idx} = lower(regexprep(char(names{idx}), '[^a-zA-Z0-9]', ''));
    end
end
