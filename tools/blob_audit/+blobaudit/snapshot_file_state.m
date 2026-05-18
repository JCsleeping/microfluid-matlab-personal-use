function state = snapshot_file_state(inventory, compute_hashes)
% SNAPSHOT_FILE_STATE  Capture bytes and modified time for discovered files.

    n = height(inventory);
    path = inventory.path;
    bytes = nan(n, 1);
    modified_time = cell(n, 1);
    hash = cell(n, 1);
    exists_col = false(n, 1);

    for idx = 1:n
        p = path{idx};
        d = dir(p);
        exists_col(idx) = ~isempty(d);
        if ~isempty(d)
            bytes(idx) = d.bytes;
            modified_time{idx} = datestr(d.datenum, 31);
            if compute_hashes
                hash{idx} = local_hash(p);
            else
                hash{idx} = '';
            end
        else
            modified_time{idx} = '';
            hash{idx} = '';
        end
    end
    state = table(path, exists_col, bytes, modified_time, hash, ...
        'VariableNames', {'path', 'exists', 'bytes', 'modified_time', 'hash'});
end


function value = local_hash(path)
    try
        md = java.security.MessageDigest.getInstance('SHA-256');
        fid = fopen(path, 'r');
        cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
        while true
            data = fread(fid, 1024 * 1024, '*uint8');
            if isempty(data)
                break;
            end
            md.update(data);
        end
        bytes = typecast(md.digest(), 'uint8');
        value = lower(reshape(dec2hex(bytes).', 1, []));
    catch
        value = '';
    end
end
