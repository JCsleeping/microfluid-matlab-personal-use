function txt = json_encode_safe(value)
% JSON_ENCODE_SAFE  Encode JSON with a small compatibility fallback.

    try
        txt = jsonencode(value, 'PrettyPrint', true);
    catch
        try
            txt = jsonencode(value);
        catch ME
            txt = jsonencode(struct('json_error', ME.message));
        end
    end
end
