function [metrics, blob_table] = compute_timeseries_blob_metrics(mask)
% COMPUTE_TIMESERIES_BLOB_METRICS  Step-4 blob summary sourced from analyze_blob_geometry.

    blob = analyze_blob_geometry(mask, []);
    blob_table = blob.blob_table;

    metrics = zero_blob_metrics();
    if blob.num_blobs == 0
        return;
    end

    metrics.num_blobs = blob.num_blobs;
    metrics.mean_blob_size = blob.size_distribution.mean;
    metrics.max_blob_frac = blob.max_blob_fraction;
    metrics.Req_median = blob.Req_distribution.median;
    metrics.Req_mean = blob.Req_distribution.mean;
    metrics.Req_std = blob.Req_distribution.std;

    if ~isempty(blob_table) && ismember('Circularity', blob_table.Properties.VariableNames)
        metrics.mean_circularity = mean(blob_table.Circularity);
    end

    metrics.n_droplets = blob.topology_summary.n_droplets;
    metrics.n_columns = blob.topology_summary.n_columns;
    metrics.n_clusters = blob.topology_summary.n_clusters;
    metrics.frac_droplets = blob.topology_summary.frac_droplets;
    metrics.frac_columns = blob.topology_summary.frac_columns;
    metrics.frac_clusters = blob.topology_summary.frac_clusters;
end


function metrics = zero_blob_metrics()
    metrics = struct( ...
        'num_blobs', 0, ...
        'mean_blob_size', 0, ...
        'max_blob_frac', 0, ...
        'Req_median', 0, ...
        'Req_mean', 0, ...
        'Req_std', 0, ...
        'mean_circularity', 0, ...
        'n_droplets', 0, ...
        'n_columns', 0, ...
        'n_clusters', 0, ...
        'frac_droplets', 0, ...
        'frac_columns', 0, ...
        'frac_clusters', 0);
end
