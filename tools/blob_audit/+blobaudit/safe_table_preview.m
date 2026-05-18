function preview = safe_table_preview(T, max_rows)
% SAFE_TABLE_PREVIEW  Return at most max_rows rows from a table.

    if nargin < 2
        max_rows = 20;
    end
    if isempty(T) || ~istable(T)
        preview = table();
        return;
    end
    preview = T(1:min(height(T), max_rows), :);
end
