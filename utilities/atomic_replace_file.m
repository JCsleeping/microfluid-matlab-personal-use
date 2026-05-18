function atomic_replace_file(tmp_path, final_path, validate_after)
% ATOMIC_REPLACE_FILE  Replace a file with restore-on-failure semantics.
%
% Both paths must be in the same directory. The function first moves an
% existing destination to a backup, then moves the temp file into place. If
% validation or move fails, the old destination is restored when possible.

    if nargin < 3
        validate_after = [];
    end

    tmp_path = char(string(tmp_path));
    final_path = char(string(final_path));
    if exist(tmp_path, 'file') ~= 2
        error('atomic_replace_file:missingTemp', ...
            'Temporary file does not exist: %s', tmp_path);
    end

    tmp_dir = fileparts(tmp_path);
    final_dir = fileparts(final_path);
    if ~strcmpi(tmp_dir, final_dir)
        error('atomic_replace_file:differentDirectories', ...
            'Temporary and final files must be in the same directory.');
    end

    backup_path = '';
    if exist(final_path, 'file') == 2
        [folder, name, ext] = fileparts(final_path);
        backup_path = fullfile(folder, sprintf('%s.replace_backup_%s%s', ...
            name, datestr(now, 'yyyymmdd_HHMMSSFFF'), ext));
        movefile(final_path, backup_path, 'f');
    end

    try
        movefile(tmp_path, final_path, 'f');
        if ~isempty(validate_after)
            validate_after(final_path);
        end
        if ~isempty(backup_path) && exist(backup_path, 'file') == 2
            delete(backup_path);
        end
    catch ME
        if exist(final_path, 'file') == 2
            delete(final_path);
        end
        if ~isempty(backup_path) && exist(backup_path, 'file') == 2
            movefile(backup_path, final_path, 'f');
        end
        rethrow(ME);
    end
end

