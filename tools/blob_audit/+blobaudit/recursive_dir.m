function files = recursive_dir(root_dir)
% RECURSIVE_DIR  Recursively list files, excluding prior audit directories.

    files = struct('path', {});
    if ~isfolder(root_dir)
        return;
    end
    listing = dir(root_dir);
    for idx = 1:numel(listing)
        item = listing(idx);
        if strcmp(item.name, '.') || strcmp(item.name, '..')
            continue;
        end
        full_path = fullfile(item.folder, item.name);
        if item.isdir
            if startsWith(item.name, 'audit_blob_morphology_gap_')
                continue;
            end
            child = blobaudit.recursive_dir(full_path);
            files = [files, child]; %#ok<AGROW>
        else
            files(end + 1).path = full_path; %#ok<AGROW>
        end
    end
end
