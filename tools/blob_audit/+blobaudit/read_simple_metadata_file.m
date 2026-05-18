function metadata = read_simple_metadata_file(path)
% READ_SIMPLE_METADATA_FILE  Read simple JSON/YAML/CSV/MAT metadata.

    metadata = struct();
    if isempty(path) || ~isfile(path)
        return;
    end
    [~, ~, ext] = fileparts(path);
    ext = lower(ext);
    try
        switch ext
            case '.json'
                metadata = jsondecode(fileread(path));
            case {'.yaml', '.yml'}
                metadata = read_simple_yaml(path);
            case '.csv'
                T = readtable(path, 'VariableNamingRule', 'preserve');
                metadata = table_to_metadata(T);
            case '.mat'
                vars = whos('-file', path);
                names = {vars.name};
                if ~isempty(names)
                    S = load(path, names{:});
                    metadata = S;
                end
        end
    catch
        metadata = struct();
    end
end


function s = read_simple_yaml(path)
    s = struct();
    lines = regexp(fileread(path), '\r?\n', 'split');
    for idx = 1:numel(lines)
        line = strtrim(lines{idx});
        if isempty(line) || startsWith(line, '#') || ~contains(line, ':')
            continue;
        end
        parts = regexp(line, ':', 'split', 'once');
        key = matlab.lang.makeValidName(strtrim(parts{1}));
        value = strtrim(parts{2});
        s.(key) = value;
    end
    s.yaml_parse_mode = 'simple_key_value_only';
end


function s = table_to_metadata(T)
    s = struct();
    if width(T) >= 2 && any(strcmpi(T.Properties.VariableNames, 'key'))
        key_col = T.Properties.VariableNames{strcmpi(T.Properties.VariableNames, 'key')};
        value_col = T.Properties.VariableNames{min(width(T), 2)};
        for idx = 1:height(T)
            key = matlab.lang.makeValidName(char(string(T.(key_col)(idx))));
            s.(key) = char(string(T.(value_col)(idx)));
        end
    else
        for idx = 1:width(T)
            s.(matlab.lang.makeValidName(T.Properties.VariableNames{idx})) = T{1, idx};
        end
    end
end
