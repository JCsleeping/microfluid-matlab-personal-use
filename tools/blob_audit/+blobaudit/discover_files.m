function inventory = discover_files(root_output_dir, opts)
% DISCOVER_FILES  Build inventory of relevant non-audit files.

    paths = {};
    roots = {char(root_output_dir)};
    optional_roots = {opts.RawImageDir, opts.MaskDir, opts.LabelDir};
    for idx = 1:numel(optional_roots)
        p = char(optional_roots{idx});
        if ~isempty(p) && isfolder(p)
            roots{end + 1} = p; %#ok<AGROW>
        end
    end

    for idx = 1:numel(roots)
        files = blobaudit.recursive_dir(roots{idx});
        for j = 1:numel(files)
            paths{end + 1} = files(j).path; %#ok<AGROW>
        end
    end
    metadata_file = char(opts.ExperimentMetadataFile);
    if ~isempty(metadata_file) && isfile(metadata_file)
        paths{end + 1} = metadata_file;
    end
    paths = unique(paths, 'stable');

    file_type = {};
    exists_col = false(0, 1);
    bytes = zeros(0, 1);
    modified_time = {};
    parent_dir = {};
    extension = {};
    notes = {};

    for idx = 1:numel(paths)
        p = paths{idx};
        d = dir(p);
        [folder, name, ext] = fileparts(p);
        file_type{idx, 1} = classify_file(p, name, ext); %#ok<AGROW>
        exists_col(idx, 1) = ~isempty(d); %#ok<AGROW>
        if ~isempty(d)
            bytes(idx, 1) = d.bytes; %#ok<AGROW>
            modified_time{idx, 1} = datestr(d.datenum, 31); %#ok<AGROW>
        else
            bytes(idx, 1) = NaN; %#ok<AGROW>
            modified_time{idx, 1} = ''; %#ok<AGROW>
        end
        parent_dir{idx, 1} = folder; %#ok<AGROW>
        extension{idx, 1} = lower(ext); %#ok<AGROW>
        notes{idx, 1} = ''; %#ok<AGROW>
    end

    inventory = table(file_type, paths(:), exists_col, bytes, modified_time, parent_dir, extension, notes, ...
        'VariableNames', {'file_type', 'path', 'exists', 'bytes', 'modified_time', ...
        'parent_dir', 'extension', 'notes'});
end


function file_type = classify_file(path, name, ext)
    lower_path = lower(path);
    lower_name = lower([name ext]);
    lower_ext = lower(ext);
    image_ext = {'.tif', '.tiff', '.png', '.jpg', '.jpeg'};
    video_ext = {'.avi', '.mp4'};

    if contains(lower_path, 'blob_detail_chunks') && strcmp(lower_ext, '.mat')
        file_type = 'blob_chunk_mat';
    elseif strcmp(lower_name, 'blob_detail_all_frames.csv')
        file_type = 'blob_csv';
    elseif contains(lower_name, 'results') && strcmp(lower_ext, '.mat')
        file_type = 'results_mat';
    elseif contains(lower_name, 'checkpoint') && strcmp(lower_ext, '.mat')
        file_type = 'checkpoint_mat';
    elseif contains(lower_name, 'config') && any(strcmp(lower_ext, {'.mat', '.m'}))
        file_type = 'config_file';
    elseif contains(lower_name, 'mask') && any(strcmp(lower_ext, image_ext))
        file_type = 'mask_image';
    elseif (contains(lower_name, 'label') || contains(lower_name, 'labels')) && strcmp(lower_ext, '.mat')
        file_type = 'label_mat';
    elseif any(strcmp(lower_ext, image_ext)) && ~contains(lower_name, 'mask')
        file_type = 'raw_image';
    elseif any(strcmp(lower_ext, video_ext))
        file_type = 'raw_image';
    elseif any(strcmp(lower_ext, {'.json', '.yaml', '.yml'})) || ...
            (strcmp(lower_ext, '.csv') && contains(lower_name, 'metadata'))
        file_type = 'metadata';
    else
        file_type = 'unknown_relevant';
    end
end
