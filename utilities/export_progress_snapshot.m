function export_progress_snapshot(output_path, time_vector, sn_arr, nblobs_arr, ...
        mbs_arr, max_blob_frac_arr, Req_median_arr, Req_mean_arr, Req_std_arr, ...
        mean_circularity_arr, a_i_2D_arr, n_droplets_arr, n_columns_arr, ...
        n_clusters_arr, frac_droplets_arr, frac_columns_arr, frac_clusters_arr, ...
        iface_arr, last_frame, locked_threshold)
% EXPORT_PROGRESS_SNAPSHOT  Save lightweight Step-4 progress to disk.
%
%   export_progress_snapshot(output_path, time_vector, sn_arr, nblobs_arr, ...
%       mbs_arr, max_blob_frac_arr, Req_median_arr, Req_mean_arr, Req_std_arr, ...
%       mean_circularity_arr, a_i_2D_arr, n_droplets_arr, n_columns_arr, ...
%       n_clusters_arr, frac_droplets_arr, frac_columns_arr, frac_clusters_arr, ...
%       iface_arr, last_frame, locked_threshold)

    if nargin < 20 || isempty(last_frame) || last_frame < 1
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
    progress.MaxBlobFrac = max_blob_frac_arr(idx);
    progress.ReqMedian = Req_median_arr(idx);
    progress.ReqMean = Req_mean_arr(idx);
    progress.ReqStd = Req_std_arr(idx);
    progress.MeanCircularity = mean_circularity_arr(idx);
    progress.a_i_2D = a_i_2D_arr(idx);
    progress.nDroplets = n_droplets_arr(idx);
    progress.nColumns = n_columns_arr(idx);
    progress.nClusters = n_clusters_arr(idx);
    progress.fracDroplets = frac_droplets_arr(idx);
    progress.fracColumns = frac_columns_arr(idx);
    progress.fracClusters = frac_clusters_arr(idx);
    progress.InterfaceArea = iface_arr(idx);
    progress.locked_threshold = locked_threshold;
    progress.updated_at = datestr(now, 'yyyy-mm-dd HH:MM:SS');

    save(fullfile(progress_dir, 'progress_latest.mat'), 'progress');

    T = table(progress.time_vector(:), progress.Sn(:), progress.NumBlobs(:), ...
        progress.MeanBlobSize(:), progress.MaxBlobFrac(:), progress.ReqMedian(:), ...
        progress.ReqMean(:), progress.ReqStd(:), progress.MeanCircularity(:), ...
        progress.a_i_2D(:), progress.nDroplets(:), progress.nColumns(:), ...
        progress.nClusters(:), progress.fracDroplets(:), progress.fracColumns(:), ...
        progress.fracClusters(:), progress.InterfaceArea(:), ...
        'VariableNames', {'Time', 'Sn', 'NumBlobs', 'MeanBlobSize', ...
        'MaxBlobFrac', 'ReqMedian', 'ReqMean', 'ReqStd', 'MeanCircularity', ...
        'a_i_2D', 'nDroplets', 'nColumns', 'nClusters', 'fracDroplets', ...
        'fracColumns', 'fracClusters', 'InterfaceArea'});
    writetable(T, fullfile(progress_dir, 'progress_latest.csv'));

    fprintf('  Progress snapshot updated: frame %d\n', last_frame);
end
