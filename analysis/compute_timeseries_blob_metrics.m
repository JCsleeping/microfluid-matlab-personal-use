function [num_blobs, mean_blob_size] = compute_timeseries_blob_metrics(mask)
% COMPUTE_TIMESERIES_BLOB_METRICS  Lightweight blob metrics for Step 4.

    cc = bwconncomp(mask, 8);
    num_blobs = cc.NumObjects;
    if num_blobs == 0
        mean_blob_size = 0;
        return;
    end

    blob_sizes = cellfun(@numel, cc.PixelIdxList);
    mean_blob_size = mean(blob_sizes);
end
