function export_progress_snapshot(output_path, time_vector, sn_arr, nblobs_arr, ...
        mbs_arr, iface_arr, last_frame, locked_threshold)
% EXPORT_PROGRESS_SNAPSHOT  Save lightweight Step-4 progress to disk.
%
%   export_progress_snapshot(output_path, time_vector, sn_arr, nblobs_arr, ...
%       mbs_arr, iface_arr, last_frame, locked_threshold)

    if nargin < 8 || isempty(last_frame) || last_frame < 1
        return;
    end

    progress_dir = fullfile(output_path, 'progress');
    if ~isfolder(progress_dir)
        mkdir(progress_dir);
    end

    last_frame = min(last_frame, numel(sn_arr));
    idx = 1:last_frame;

    progress = struct();
    progress.last_frame = last_frame;
    progress.time_vector = time_vector(idx);
    progress.Sn = sn_arr(idx);
    progress.NumBlobs = nblobs_arr(idx);
    progress.MeanBlobSize = mbs_arr(idx);
    progress.InterfaceArea = iface_arr(idx);
    progress.locked_threshold = locked_threshold;
    progress.updated_at = datestr(now, 'yyyy-mm-dd HH:MM:SS');

    save(fullfile(progress_dir, 'progress_latest.mat'), 'progress');

    T = table(progress.time_vector(:), progress.Sn(:), progress.NumBlobs(:), ...
        progress.MeanBlobSize(:), progress.InterfaceArea(:), ...
        'VariableNames', {'Time', 'Sn', 'NumBlobs', 'MeanBlobSize', 'InterfaceArea'});
    writetable(T, fullfile(progress_dir, 'progress_latest.csv'));

    fprintf('  Progress snapshot updated: frame %d\n', last_frame);
end
