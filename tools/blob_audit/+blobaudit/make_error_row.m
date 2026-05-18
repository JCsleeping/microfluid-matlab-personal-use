function row = make_error_row(message)
% MAKE_ERROR_ROW  Create a small one-row error table.

    error_message = {char(message)};
    row = table(error_message, 'VariableNames', {'error_message'});
end
