function outputs = run_a1_1bo_6ul_hdf5_cache_segmentation_morphology(cache_dir, out_dir, config_path, run_mode)
% RUN_A1_1BO_6UL_HDF5_CACHE_SEGMENTATION_MORPHOLOGY
% Segmentation-derived red DNAPL mask pilot and morphology outputs.
%
% This C2 branch reads the same BasicPy corrected HDF5 cache as Branch C, but
% it produces binary red-mask occupancy and per-frame morphology. These masks
% are not used for endpoint-normalized Sn.

    repo_root = fileparts(mfilename('fullpath'));
    addpath(genpath(repo_root));

    if nargin < 1 || isempty(cache_dir)
        cache_dir = fullfile(repo_root, 'outputs', ...
            'basicpy_hdf5_cache_20260601', 'A1_1BO_6UL_manual_roi_page1');
    end
    if nargin < 2 || isempty(out_dir)
        out_dir = fullfile(repo_root, 'outputs', ...
            'hdf5_cache_segmentation_morphology_20260601', ...
            'A1_1BO_6UL_manual_roi_page1');
    end
    if nargin < 3
        config_path = '';
    end
    if nargin < 4 || isempty(run_mode)
        run_mode = 'pilot';
    end
    run_mode = lower(char(string(run_mode)));
    if ~isfolder(out_dir)
        mkdir(out_dir);
    end

    manifest_path = fullfile(cache_dir, 'manifest.csv');
    mask_path = fullfile(cache_dir, 'mask_crop.h5');
    if ~isfile(manifest_path)
        error('segmentation_morphology:missingCacheManifest', ...
            'Missing cache manifest: %s', manifest_path);
    end
    if ~isfile(mask_path)
        error('segmentation_morphology:missingMask', ...
            'Missing cache mask: %s', mask_path);
    end

    manifest = readtable(manifest_path, 'TextType', 'string');
    frame_rows = timeseries_frame_rows(manifest);
    flow_domain = read_hdf5_mask(mask_path);
    solid_mask = false(size(flow_domain));
    config = read_segmentation_config(config_path);

    switch run_mode
        case 'pilot'
            outputs = run_segmentation_pilot(frame_rows, flow_domain, ...
                solid_mask, out_dir, config, cache_dir, config_path);
        case {'morphology', 'production'}
            outputs = run_segmentation_morphology(frame_rows, flow_domain, ...
                solid_mask, out_dir, config, cache_dir, config_path);
        otherwise
            error('segmentation_morphology:badRunMode', ...
                'run_mode must be pilot or morphology, got %s.', run_mode);
    end

    fprintf('SEGMENTATION_MORPHOLOGY_%s %s\n', upper(run_mode), out_dir);
end


function outputs = run_segmentation_pilot(frame_rows, flow_domain, ~, ...
        out_dir, config, cache_dir, config_path)
    score_modes = string(config.score_modes);
    percentiles = double(config.threshold_percentiles(:)');
    threshold_rows = repmat(empty_threshold_row(), 0, 1);
    candidate_rows = repmat(empty_candidate_row(), 0, 1);
    overlays_dir = fullfile(out_dir, 'mask_qc_overlays');
    if ~isfolder(overlays_dir)
        mkdir(overlays_dir);
    end
    overlay_frames = sample_frame_indices(height(frame_rows), config.overlay_sample_max);

    for mode_idx = 1:numel(score_modes)
        score_mode = score_modes(mode_idx);
        fprintf('SEG_PILOT_SCORE_MODE %s\n', score_mode);
        thresholds = estimate_mode_thresholds(frame_rows, flow_domain, ...
            score_mode, percentiles, config);
        mode_rows = repmat(empty_threshold_row(), ...
            height(frame_rows) * numel(thresholds), 1);
        output_idx = 0;
        for frame_idx = 1:height(frame_rows)
            rgb = read_hdf5_rgb(frame_rows.h5_path(frame_idx));
            score = red_score_map(rgb, score_mode);
            label = string(frame_rows.label(frame_idx));
            role = string(frame_rows.role(frame_idx));
            time_s = frame_time_s(frame_rows, frame_idx);
            for thr_idx = 1:numel(thresholds)
                output_idx = output_idx + 1;
                threshold = thresholds(thr_idx);
                mask = cleanup_red_mask(score >= threshold.value & flow_domain, ...
                    config, flow_domain);
                metrics = mask_pilot_metrics(mask, flow_domain);
                mode_rows(output_idx) = threshold_row(frame_idx, time_s, ...
                    label, role, score_mode, threshold, metrics);
                if ismember(frame_idx, overlay_frames)
                    write_overlay(overlays_dir, score_mode, threshold, ...
                        frame_idx, label, rgb, mask);
                end
            end
        end

        mode_table = struct2table(mode_rows);
        mode_path = fullfile(out_dir, sprintf('threshold_sweep_%s.csv', ...
            sanitize_token(score_mode)));
        writetable(mode_table, mode_path);
        threshold_rows = [threshold_rows; mode_rows]; %#ok<AGROW>
        candidate_rows = [candidate_rows; summarize_candidates(mode_rows)]; %#ok<AGROW>
    end

    threshold_path = fullfile(out_dir, 'threshold_sweep_all.csv');
    candidate_path = fullfile(out_dir, 'candidate_summary.csv');
    manifest_path = fullfile(out_dir, 'segmentation_pilot_manifest.json');
    writetable(struct2table(threshold_rows), threshold_path);
    writetable(struct2table(candidate_rows), candidate_path);
    write_segmentation_manifest(manifest_path, 'pilot', config, cache_dir, ...
        out_dir, config_path, threshold_path, candidate_path, '');

    outputs = struct();
    outputs.output_dir = out_dir;
    outputs.threshold_sweep_csv = threshold_path;
    outputs.candidate_summary_csv = candidate_path;
    outputs.manifest_json = manifest_path;
end


function outputs = run_segmentation_morphology(frame_rows, flow_domain, ...
        solid_mask, out_dir, config, cache_dir, config_path)
    [score_mode, threshold] = locked_production_threshold(config);
    total_frames = height(frame_rows);
    run_indices = morphology_run_indices(total_frames, config);
    overlays_dir = fullfile(out_dir, 'mask_qc_overlays_sample');
    if ~isfolder(overlays_dir)
        mkdir(overlays_dir);
    end
    overlay_frames = sample_frame_indices(total_frames, config.overlay_sample_max);
    detail_path = fullfile(out_dir, 'red_blob_detail_all_frames.csv');
    detail_chunks_dir = fullfile(out_dir, char(config.blob_detail_chunks_dir_name));
    detail_chunk_path = '';
    use_chunked_blob_detail = config.write_blob_detail && ...
        config.blob_detail_output_mode == "chunked_csv";
    mask_stack_path = fullfile(out_dir, 'red_mask_stack.h5');
    mask_stack_manifest_path = fullfile(out_dir, 'red_mask_stack_manifest.csv');
    timeseries_path = fullfile(out_dir, 'red_mask_timeseries.csv');
    summary_path = fullfile(out_dir, 'red_blob_summary_timeseries.csv');
    manifest_path = fullfile(out_dir, 'segmentation_manifest.json');
    replace_outputs = ~config.resume_outputs;

    initialize_struct_csv(timeseries_path, empty_morphology_row(), replace_outputs);
    initialize_struct_csv(summary_path, empty_morphology_row(), replace_outputs);
    if config.write_blob_detail
        if use_chunked_blob_detail
            if replace_outputs
                if isfile(detail_path)
                    delete(detail_path);
                end
                if isfolder(detail_chunks_dir)
                    rmdir(detail_chunks_dir, 's');
                end
            end
            if ~isfolder(detail_chunks_dir)
                mkdir(detail_chunks_dir);
            end
            detail_chunk_path = fullfile(detail_chunks_dir, sprintf( ...
                'red_blob_detail_%06d_%06d.csv', run_indices(1), run_indices(end)));
            initialize_blob_detail_csv(detail_chunk_path, true);
        else
            initialize_blob_detail_csv(detail_path, replace_outputs);
        end
    end
    if config.write_mask_stack
        if replace_outputs || ~isfile(mask_stack_path)
            initialize_mask_stack_h5(mask_stack_path, size(flow_domain), ...
                total_frames, config, score_mode, threshold);
        end
        initialize_struct_csv(mask_stack_manifest_path, empty_mask_stack_row(), ...
            replace_outputs);
    end

    fprintf('SEG_MORPH_CHUNK %d/%d-%d/%d\n', run_indices(1), total_frames, ...
        run_indices(end), total_frames);
    for frame_idx = run_indices
        rgb = read_hdf5_rgb(frame_rows.h5_path(frame_idx));
        score = red_score_map(rgb, score_mode);
        mask = cleanup_red_mask(score >= threshold.value & flow_domain, ...
            config, flow_domain);
        label = string(frame_rows.label(frame_idx));
        role = string(frame_rows.role(frame_idx));
        time_s = frame_time_s(frame_rows, frame_idx);
        [metrics, blob_table] = mask_summary_metrics(mask, flow_domain, ...
            solid_mask, config);
        ts_row = morphology_row(frame_idx, time_s, label, role, ...
            score_mode, threshold, metrics);
        append_struct_row_csv(timeseries_path, ts_row);
        append_struct_row_csv(summary_path, ts_row);
        if config.write_blob_detail
            blob_table = add_blob_detail_context(blob_table, frame_idx, time_s, ...
                label, role, score_mode, threshold, config);
            if use_chunked_blob_detail
                append_blob_detail_csv(detail_chunk_path, blob_table);
            else
                append_blob_detail_csv(detail_path, blob_table);
            end
        end
        if config.write_mask_stack
            h5write(mask_stack_path, config.mask_stack_dataset, uint8(mask), ...
                [1, 1, frame_idx], [size(mask, 1), size(mask, 2), 1]);
            stack_row = mask_stack_row(frame_idx, time_s, ...
                label, role, config, threshold, metrics, size(mask));
            append_struct_row_csv(mask_stack_manifest_path, stack_row);
        end
        if ismember(frame_idx, overlay_frames)
            write_overlay(overlays_dir, score_mode, threshold, frame_idx, ...
                label, rgb, mask);
        end
        if frame_idx == run_indices(1) || frame_idx == run_indices(end) || mod(frame_idx, 100) == 0
            fprintf('SEG_MORPH_PROGRESS %d/%d\n', frame_idx, total_frames);
        end
    end

    if ~config.write_blob_detail
        detail_path = '';
        detail_chunks_dir = '';
        detail_chunk_path = '';
    elseif ~use_chunked_blob_detail
        detail_chunks_dir = '';
        detail_chunk_path = '';
    end
    if ~config.write_mask_stack
        mask_stack_path = '';
        mask_stack_manifest_path = '';
    end
    write_segmentation_manifest(manifest_path, 'morphology', config, cache_dir, ...
        out_dir, config_path, timeseries_path, summary_path, detail_path, ...
        mask_stack_path, mask_stack_manifest_path, detail_chunks_dir, ...
        detail_chunk_path);

    outputs = struct();
    outputs.output_dir = out_dir;
    outputs.red_mask_timeseries_csv = timeseries_path;
    outputs.red_blob_summary_csv = summary_path;
    outputs.red_blob_detail_csv = detail_path;
    outputs.red_blob_detail_chunks_dir = detail_chunks_dir;
    outputs.red_blob_detail_chunk_csv = detail_chunk_path;
    outputs.red_mask_stack_h5 = mask_stack_path;
    outputs.red_mask_stack_manifest_csv = mask_stack_manifest_path;
    outputs.manifest_json = manifest_path;
end


function config = read_segmentation_config(config_path)
    config = default_segmentation_config();
    if nargin < 1 || isempty(config_path) || ~isfile(config_path)
        return;
    end
    json_text = fileread(char(config_path));
    if ~isempty(json_text) && double(json_text(1)) == 65279
        json_text = json_text(2:end);
    end
    root = jsondecode(json_text);
    if ~isfield(root, 'segmentation_metrics')
        return;
    end
    user_config = root.segmentation_metrics;
    fields = fieldnames(user_config);
    for idx = 1:numel(fields)
        config.(fields{idx}) = user_config.(fields{idx});
    end
    config = normalize_segmentation_config(config);
end


function config = default_segmentation_config()
    config = struct();
    config.enabled = true;
    config.score_modes = ["lab_a", "excess_red", "chroma", "normalized_red"];
    config.production_score_mode = "lab_a";
    config.locked_threshold = [];
    config.threshold_percentiles = [90, 92.5, 95, 97.5, 99];
    config.threshold_sample_frame_stride = 1;
    config.min_area_px = 20;
    config.morph_radius = 1;
    config.overlay_sample_max = 12;
    config.write_blob_detail = false;
    config.blob_detail_output_mode = "single_csv";
    config.blob_detail_chunks_dir_name = "red_blob_detail_chunks";
    config.write_mask_stack = false;
    config.mask_stack_format = "hdf5";
    config.mask_stack_dataset = "/red_mask";
    config.mask_stack_deflate = 4;
    config.mask_grid = "processing_grid";
    config.threshold_source = "pilot_locked";
    config.output_semantics = "segmentation-derived red DNAPL 2D occupancy";
    config.processing_pixel_size_m = [];
    config.processing_scale_factor = 1;
    config.interface_solid_dilation = 1;
    config.frame_start_index = 1;
    config.frame_end_index = [];
    config.resume_outputs = false;
end


function config = normalize_segmentation_config(config)
    config.score_modes = string(config.score_modes);
    config.production_score_mode = string(config.production_score_mode);
    config.threshold_percentiles = double(config.threshold_percentiles(:)');
    config.threshold_sample_frame_stride = max(1, round(double( ...
        config.threshold_sample_frame_stride)));
    config.min_area_px = max(0, round(double(config.min_area_px)));
    config.morph_radius = max(0, round(double(config.morph_radius)));
    config.overlay_sample_max = max(0, round(double(config.overlay_sample_max)));
    config.write_blob_detail = logical(config.write_blob_detail);
    if ~isfield(config, 'blob_detail_output_mode') || ...
            isempty(config.blob_detail_output_mode)
        config.blob_detail_output_mode = "single_csv";
    end
    blob_mode = lower(strrep(char(string(config.blob_detail_output_mode)), ...
        '-', '_'));
    if strcmp(blob_mode, 'chunked')
        blob_mode = 'chunked_csv';
    elseif strcmp(blob_mode, 'single') || strcmp(blob_mode, 'singlecsv')
        blob_mode = 'single_csv';
    end
    if ~ismember(blob_mode, {'single_csv', 'chunked_csv'})
        error('segmentation_morphology:badBlobDetailOutputMode', ...
            'Unsupported blob_detail_output_mode: %s.', blob_mode);
    end
    config.blob_detail_output_mode = string(blob_mode);
    if ~isfield(config, 'blob_detail_chunks_dir_name') || ...
            isempty(config.blob_detail_chunks_dir_name)
        config.blob_detail_chunks_dir_name = "red_blob_detail_chunks";
    end
    config.blob_detail_chunks_dir_name = string(config.blob_detail_chunks_dir_name);
    if ~isfield(config, 'write_mask_stack') || isempty(config.write_mask_stack)
        config.write_mask_stack = false;
    end
    config.write_mask_stack = logical(config.write_mask_stack);
    if ~isfield(config, 'mask_stack_format') || isempty(config.mask_stack_format)
        config.mask_stack_format = "hdf5";
    end
    config.mask_stack_format = string(config.mask_stack_format);
    if config.mask_stack_format ~= "hdf5"
        error('segmentation_morphology:badMaskStackFormat', ...
            'Only HDF5 mask stack output is supported, got %s.', ...
            char(config.mask_stack_format));
    end
    if ~isfield(config, 'mask_stack_dataset') || isempty(config.mask_stack_dataset)
        config.mask_stack_dataset = "/red_mask";
    end
    config.mask_stack_dataset = string(config.mask_stack_dataset);
    if ~startsWith(config.mask_stack_dataset, "/")
        config.mask_stack_dataset = "/" + config.mask_stack_dataset;
    end
    if ~isfield(config, 'mask_stack_deflate') || isempty(config.mask_stack_deflate)
        config.mask_stack_deflate = 4;
    end
    config.mask_stack_deflate = max(0, min(9, round(double(config.mask_stack_deflate))));
    if ~isfield(config, 'mask_grid') || isempty(config.mask_grid)
        config.mask_grid = "processing_grid";
    end
    config.mask_grid = string(config.mask_grid);
    config.threshold_source = string(config.threshold_source);
    if ~isfield(config, 'processing_scale_factor') || ...
            isempty(config.processing_scale_factor)
        config.processing_scale_factor = 1;
    end
    config.processing_scale_factor = double(config.processing_scale_factor);
    if ~isscalar(config.processing_scale_factor) || ...
            ~isfinite(config.processing_scale_factor) || ...
            config.processing_scale_factor <= 0
        config.processing_scale_factor = 1;
    end
    if ~isfield(config, 'processing_pixel_size_m') || ...
            isempty(config.processing_pixel_size_m)
        config.processing_pixel_size_m = [];
    else
        config.processing_pixel_size_m = double(config.processing_pixel_size_m);
        if ~isscalar(config.processing_pixel_size_m) || ...
                ~isfinite(config.processing_pixel_size_m) || ...
                config.processing_pixel_size_m <= 0
            config.processing_pixel_size_m = [];
        end
    end
    if ~isfield(config, 'interface_solid_dilation') || ...
            isempty(config.interface_solid_dilation)
        config.interface_solid_dilation = 1;
    end
    config.interface_solid_dilation = max(0, round(double( ...
        config.interface_solid_dilation)));
    if ~isfield(config, 'frame_start_index') || isempty(config.frame_start_index)
        config.frame_start_index = 1;
    end
    config.frame_start_index = max(1, round(double(config.frame_start_index)));
    if ~isfield(config, 'frame_end_index') || isempty(config.frame_end_index)
        config.frame_end_index = [];
    else
        config.frame_end_index = max(1, round(double(config.frame_end_index)));
    end
    if ~isfield(config, 'resume_outputs') || isempty(config.resume_outputs)
        config.resume_outputs = false;
    end
    config.resume_outputs = logical(config.resume_outputs);
end


function thresholds = estimate_mode_thresholds(frame_rows, flow_domain, ...
        score_mode, percentiles, config)
    sample_stride = config.threshold_sample_frame_stride;
    frame_indices = 1:sample_stride:height(frame_rows);
    frame_percentiles = NaN(numel(frame_indices), numel(percentiles));
    for idx = 1:numel(frame_indices)
        row_idx = frame_indices(idx);
        rgb = read_hdf5_rgb(frame_rows.h5_path(row_idx));
        score = red_score_map(rgb, score_mode);
        values = score(flow_domain);
        values = values(isfinite(values));
        if ~isempty(values)
            frame_percentiles(idx, :) = prctile(values, percentiles);
        end
    end
    thresholds = repmat(empty_threshold_spec(), numel(percentiles), 1);
    for idx = 1:numel(percentiles)
        thresholds(idx).percentile = percentiles(idx);
        thresholds(idx).value = median(frame_percentiles(:, idx), 'omitnan');
        thresholds(idx).source = "pilot_pooled_frame_percentile_median";
    end
end


function score = red_score_map(rgb, score_mode)
    rgb = normalize_rgb_seg(rgb);
    r = rgb(:, :, 1);
    g = rgb(:, :, 2);
    b = rgb(:, :, 3);
    switch lower(char(string(score_mode)))
        case 'lab_a'
            lab = rgb2lab(rgb);
            score = lab(:, :, 2);
        case 'excess_red'
            score = r - 0.5 .* (g + b);
        case 'chroma'
            lab = rgb2lab(rgb);
            score = hypot(lab(:, :, 2), lab(:, :, 3));
        case 'normalized_red'
            score = r ./ max(r + g + b, eps('single'));
        otherwise
            error('segmentation_morphology:badScoreMode', ...
                'Unsupported score mode: %s.', char(string(score_mode)));
    end
end


function mask = cleanup_red_mask(mask, config, flow_domain)
    mask = logical(mask) & logical(flow_domain);
    if config.morph_radius > 0
        se = strel('disk', config.morph_radius, 0);
        mask = imopen(mask, se);
        mask = imclose(mask, se);
    end
    if config.min_area_px > 1
        mask = bwareaopen(mask, config.min_area_px, 8);
    end
    mask = mask & logical(flow_domain);
end


function [metrics, blob_table] = mask_summary_metrics(mask, flow_domain, solid_mask, config)
    opts = struct();
    opts.mode = 'core_only';
    opts.object_connectivity = 8;
    opts.scale_factor = config.processing_scale_factor;
    opts.processing_pixel_size_m = config.processing_pixel_size_m;
    opts.primary_branch = 'C2_red_segmentation_morphology';
    opts.sn_semantics_version = 'segmentation_2d_occupancy_v1';
    opts.frame_validation_status = 'not_ground_truth_validated';
    [blob_metrics, blob_table] = compute_timeseries_blob_metrics(mask, ...
        flow_domain, solid_mask, opts);
    flow_area = nnz(flow_domain);
    red_area = nnz(mask & flow_domain);
    metrics = blob_metrics;
    metrics.red_mask_area_px = red_area;
    metrics.domain_area_px = flow_area;
    metrics.red_mask_area_fraction = red_area / max(flow_area, 1);
    metrics.component_count = blob_metrics.num_blobs;
    metrics = add_interface_metrics(metrics, mask, flow_domain, red_area, config);
end


function metrics = mask_pilot_metrics(mask, flow_domain)
    flow_area = nnz(flow_domain);
    red_area = nnz(mask & flow_domain);
    cc = bwconncomp(mask & flow_domain, 8);
    if cc.NumObjects > 0
        areas = cellfun(@numel, cc.PixelIdxList);
        largest = max(areas);
        mean_area = mean(areas);
        req_values = sqrt(double(areas) ./ pi);
        req_median = median(req_values);
        req_mean = mean(req_values);
        req_std = std(req_values);
        max_blob_frac = largest / max(red_area, 1);
    else
        mean_area = 0;
        req_median = 0;
        req_mean = 0;
        req_std = 0;
        max_blob_frac = 0;
    end
    metrics = struct();
    metrics.red_mask_area_px = red_area;
    metrics.domain_area_px = flow_area;
    metrics.red_mask_area_fraction = red_area / max(flow_area, 1);
    metrics.num_blobs = cc.NumObjects;
    metrics.component_count = cc.NumObjects;
    metrics.mean_blob_size = mean_area;
    metrics.max_blob_frac = max_blob_frac;
    metrics.Req_median = req_median;
    metrics.Req_mean = req_mean;
    metrics.Req_std = req_std;
    metrics.mean_circularity = NaN;
    metrics.n_droplets = NaN;
    metrics.n_columns = NaN;
    metrics.n_clusters = NaN;
    metrics.frac_droplets = NaN;
    metrics.frac_columns = NaN;
    metrics.frac_clusters = NaN;
    metrics = add_empty_interface_metrics(metrics, "not_computed_in_segpilot");
end


function metrics = add_interface_metrics(metrics, mask, flow_domain, red_area, config)
    pixel_size_m = [];
    if isstruct(config) && isfield(config, 'processing_pixel_size_m') && ...
            ~isempty(config.processing_pixel_size_m)
        pixel_size_m = double(config.processing_pixel_size_m);
    end
    solid_dilation = 1;
    if isstruct(config) && isfield(config, 'interface_solid_dilation')
        solid_dilation = config.interface_solid_dilation;
    end
    iface = compute_global_interface_contact(mask & flow_domain, flow_domain, ...
        solid_dilation);

    water_px = double(iface.water_length_px);
    solid_px = double(iface.solid_length_px);
    metrics.dnapl_water_length_px = water_px;
    metrics.dnapl_solid_length_px = solid_px;
    if ~isempty(pixel_size_m)
        metrics.dnapl_water_length_m = water_px * pixel_size_m;
        metrics.dnapl_solid_length_m = solid_px * pixel_size_m;
    else
        metrics.dnapl_water_length_m = NaN;
        metrics.dnapl_solid_length_m = NaN;
    end
    metrics.InterfaceArea = water_px;
    total_length = water_px + solid_px;
    if total_length > 0
        metrics.solid_contact_fraction = solid_px / total_length;
    else
        metrics.solid_contact_fraction = NaN;
    end
    if red_area > 0
        metrics.a_i_2D_proxy = water_px / double(red_area);
    else
        metrics.a_i_2D_proxy = NaN;
    end
    metrics.interface_semantics = ...
        "InterfaceArea_legacy_alias_of_dnapl_water_length_px_not_area";
end


function iface = compute_global_interface_contact(mask, flow_domain, solid_dilation)
    contact_config = struct();
    contact_config.interface = struct('solid_dilation', solid_dilation);
    solid_contact_zone = build_solid_contact_zone(flow_domain, contact_config);
    iface = struct( ...
        'water_length_px', ...
            compute_timeseries_interface_length(mask, solid_contact_zone), ...
        'solid_length_px', ...
            compute_timeseries_interface_length(mask, ~solid_contact_zone));
end


function metrics = add_empty_interface_metrics(metrics, semantics)
    metrics.dnapl_water_length_px = NaN;
    metrics.dnapl_solid_length_px = NaN;
    metrics.dnapl_water_length_m = NaN;
    metrics.dnapl_solid_length_m = NaN;
    metrics.InterfaceArea = NaN;
    metrics.solid_contact_fraction = NaN;
    metrics.a_i_2D_proxy = NaN;
    metrics.interface_semantics = string(semantics);
end


function rows = summarize_candidates(mode_rows)
    if isempty(mode_rows)
        rows = repmat(empty_candidate_row(), 0, 1);
        return;
    end
    table_in = struct2table(mode_rows);
    keys = unique(table_in(:, {'score_mode', 'threshold_percentile'}), 'rows');
    rows = repmat(empty_candidate_row(), height(keys), 1);
    for idx = 1:height(keys)
        score_mode = keys.score_mode(idx);
        pct = keys.threshold_percentile(idx);
        mask = table_in.score_mode == score_mode & ...
            table_in.threshold_percentile == pct;
        subset = table_in(mask, :);
        full_subset = subset(subset.role == "full_napl", :);
        residual_subset = subset(subset.role == "residual", :);
        row = empty_candidate_row();
        row.score_mode = score_mode;
        row.threshold_percentile = pct;
        row.threshold_value = median(subset.threshold_value, 'omitnan');
        row.row_count = height(subset);
        row.full_red_mask_area_fraction_median = median_or_nan( ...
            full_subset.red_mask_area_fraction);
        row.residual_red_mask_area_fraction_median = median_or_nan( ...
            residual_subset.red_mask_area_fraction);
        row.full_num_blobs_median = median_or_nan(full_subset.num_blobs);
        row.residual_num_blobs_median = median_or_nan(residual_subset.num_blobs);
        row.residual_largest_component_fraction_median = median_or_nan( ...
            residual_subset.largest_component_fraction);
        row.full_minus_residual_area_fraction = ...
            row.full_red_mask_area_fraction_median - ...
            row.residual_red_mask_area_fraction_median;
        row.production_candidate_status = "pilot_review_required";
        rows(idx) = row;
    end
end


function [score_mode, threshold] = locked_production_threshold(config)
    score_mode = string(config.production_score_mode);
    if isempty(config.locked_threshold)
        error('segmentation_morphology:missingLockedThreshold', ...
            ['segmentation_metrics.locked_threshold is required for ' ...
             'production morphology. Run segpilot first and lock one threshold.']);
    end
    threshold = empty_threshold_spec();
    threshold.percentile = NaN;
    threshold.value = double(config.locked_threshold);
    threshold.source = string(config.threshold_source);
end


function row = threshold_row(frame_index, time_s, label, role, score_mode, threshold, metrics)
    row = empty_threshold_row();
    row.frame_index = frame_index;
    row.time_s = time_s;
    row.label = string(label);
    row.role = string(role);
    row.score_mode = string(score_mode);
    row.threshold_percentile = threshold.percentile;
    row.threshold_value = threshold.value;
    row.threshold_source = string(threshold.source);
    row.red_mask_area_px = metrics.red_mask_area_px;
    row.domain_area_px = metrics.domain_area_px;
    row.red_mask_area_fraction = metrics.red_mask_area_fraction;
    row.num_blobs = metrics.num_blobs;
    row.component_count = metrics.component_count;
    row.mean_blob_size = metrics.mean_blob_size;
    row.max_blob_frac = metrics.max_blob_frac;
    row.Req_median = metrics.Req_median;
    row.Req_mean = metrics.Req_mean;
    row.Req_std = metrics.Req_std;
    row.mean_circularity = metrics.mean_circularity;
    row.largest_component_fraction = metrics.max_blob_frac;
    row.n_droplets = metrics.n_droplets;
    row.n_columns = metrics.n_columns;
    row.n_clusters = metrics.n_clusters;
    row.frac_droplets = metrics.frac_droplets;
    row.frac_columns = metrics.frac_columns;
    row.frac_clusters = metrics.frac_clusters;
    row.dnapl_water_length_px = metrics.dnapl_water_length_px;
    row.dnapl_solid_length_px = metrics.dnapl_solid_length_px;
    row.dnapl_water_length_m = metrics.dnapl_water_length_m;
    row.dnapl_solid_length_m = metrics.dnapl_solid_length_m;
    row.InterfaceArea = metrics.InterfaceArea;
    row.solid_contact_fraction = metrics.solid_contact_fraction;
    row.a_i_2D_proxy = metrics.a_i_2D_proxy;
    row.interface_semantics = metrics.interface_semantics;
end


function row = morphology_row(frame_index, time_s, label, role, score_mode, threshold, metrics)
    row = empty_morphology_row();
    source = threshold_row(frame_index, time_s, label, role, score_mode, ...
        threshold, metrics);
    fields = fieldnames(source);
    for idx = 1:numel(fields)
        row.(fields{idx}) = source.(fields{idx});
    end
    row.segmentation_output = "red_napl_mask";
    row.output_semantics = "segmentation-derived red DNAPL 2D occupancy";
    row.endpoint_dependency = "none";
end


function row = empty_threshold_row()
    row = struct( ...
        'frame_index', NaN, ...
        'time_s', NaN, ...
        'label', "", ...
        'role', "", ...
        'score_mode', "", ...
        'threshold_percentile', NaN, ...
        'threshold_value', NaN, ...
        'threshold_source', "", ...
        'red_mask_area_px', NaN, ...
        'domain_area_px', NaN, ...
        'red_mask_area_fraction', NaN, ...
        'num_blobs', NaN, ...
        'component_count', NaN, ...
        'mean_blob_size', NaN, ...
        'max_blob_frac', NaN, ...
        'Req_median', NaN, ...
        'Req_mean', NaN, ...
        'Req_std', NaN, ...
        'mean_circularity', NaN, ...
        'largest_component_fraction', NaN, ...
        'n_droplets', NaN, ...
        'n_columns', NaN, ...
        'n_clusters', NaN, ...
        'frac_droplets', NaN, ...
        'frac_columns', NaN, ...
        'frac_clusters', NaN, ...
        'dnapl_water_length_px', NaN, ...
        'dnapl_solid_length_px', NaN, ...
        'dnapl_water_length_m', NaN, ...
        'dnapl_solid_length_m', NaN, ...
        'InterfaceArea', NaN, ...
        'solid_contact_fraction', NaN, ...
        'a_i_2D_proxy', NaN, ...
        'interface_semantics', "");
end


function row = empty_morphology_row()
    row = empty_threshold_row();
    row.segmentation_output = "";
    row.output_semantics = "";
    row.endpoint_dependency = "";
end


function row = empty_candidate_row()
    row = struct( ...
        'score_mode', "", ...
        'threshold_percentile', NaN, ...
        'threshold_value', NaN, ...
        'row_count', NaN, ...
        'full_red_mask_area_fraction_median', NaN, ...
        'residual_red_mask_area_fraction_median', NaN, ...
        'full_num_blobs_median', NaN, ...
        'residual_num_blobs_median', NaN, ...
        'residual_largest_component_fraction_median', NaN, ...
        'full_minus_residual_area_fraction', NaN, ...
        'production_candidate_status', "");
end


function spec = empty_threshold_spec()
    spec = struct('percentile', NaN, 'value', NaN, 'source', "");
end


function frame_rows = timeseries_frame_rows(manifest)
    frame_rows = manifest(ismember(manifest.role, ...
        ["full_napl", "residual", "production"]), :);
    if ismember('include_in_timeseries', manifest.Properties.VariableNames)
        frame_rows = frame_rows(truthy_vector(frame_rows.include_in_timeseries), :);
    end
    if ismember('timeseries_order', frame_rows.Properties.VariableNames) && ...
            any(~ismissing(frame_rows.timeseries_order))
        frame_rows = sortrows(frame_rows, "timeseries_order");
    else
        frame_rows = sortrows(frame_rows, "frame_order");
    end
end


function indices = morphology_run_indices(total_frames, config)
    if total_frames < 1
        error('segmentation_morphology:noFrames', ...
            'No full_napl/residual/production frames are available for C2 morphology.');
    end
    start_idx = min(max(1, config.frame_start_index), total_frames);
    if isempty(config.frame_end_index)
        end_idx = total_frames;
    else
        end_idx = min(max(1, config.frame_end_index), total_frames);
    end
    if start_idx > end_idx
        error('segmentation_morphology:badFrameRange', ...
            'frame_start_index (%d) must be <= frame_end_index (%d).', ...
            start_idx, end_idx);
    end
    indices = start_idx:end_idx;
end


function values = truthy_vector(raw)
    values = false(size(raw));
    for idx = 1:numel(raw)
        item = raw(idx);
        if isnumeric(item) || islogical(item)
            values(idx) = logical(item);
        else
            text_value = lower(strtrim(string(item)));
            values(idx) = any(text_value == ["1", "true", "yes", "y"]);
        end
    end
end


function value = frame_time_s(frame_rows, row_idx)
    value = NaN;
    if ~ismember('time_s', frame_rows.Properties.VariableNames)
        return;
    end
    raw = frame_rows.time_s(row_idx);
    if isnumeric(raw)
        value = double(raw);
        return;
    end
    text_value = strtrim(string(raw));
    if ismissing(text_value) || text_value == ""
        return;
    end
    parsed = str2double(text_value);
    if isfinite(parsed)
        value = parsed;
    end
end


function rgb = read_hdf5_rgb(path_value)
    raw = h5read(char(path_value), '/rgb_corrected');
    if size(raw, 1) ~= 3
        error('segmentation_morphology:badRgbShape', ...
            'Expected MATLAB h5read shape 3 x W x H from Python H x W x 3 cache.');
    end
    rgb = permute(raw, [3 2 1]);
end


function mask = read_hdf5_mask(path_value)
    raw = h5read(char(path_value), '/flow_domain_mask');
    mask = logical(raw');
end


function rgb = normalize_rgb_seg(rgb)
    if isa(rgb, 'single') || isa(rgb, 'double')
        rgb = single(rgb);
        if max(rgb(:)) > 1
            rgb = rgb ./ 255;
        end
    else
        rgb = im2single(rgb);
    end
    rgb = min(max(rgb, 0), 1);
end


function indices = sample_frame_indices(n_rows, sample_max)
    if sample_max <= 0 || n_rows <= 0
        indices = [];
        return;
    end
    sample_max = min(sample_max, n_rows);
    indices = unique(round(linspace(1, n_rows, sample_max)));
end


function write_overlay(root_dir, score_mode, threshold, frame_index, label, rgb, mask)
    mode_dir = fullfile(root_dir, sanitize_token(score_mode));
    threshold_dir = fullfile(mode_dir, sprintf('pct_%s', ...
        sanitize_token(num2str(threshold.percentile, '%.3g'))));
    if ~isfolder(threshold_dir)
        mkdir(threshold_dir);
    end
    rgb = normalize_rgb_seg(rgb);
    overlay = rgb;
    red = overlay(:, :, 1);
    green = overlay(:, :, 2);
    blue = overlay(:, :, 3);
    red(mask) = 1.0;
    green(mask) = 0.15 .* green(mask);
    blue(mask) = 0.15 .* blue(mask);
    overlay(:, :, 1) = red;
    overlay(:, :, 2) = green;
    overlay(:, :, 3) = blue;
    path_value = fullfile(threshold_dir, sprintf('frame_%06d_%s_overlay.png', ...
        frame_index, sanitize_token(label)));
    imwrite(im2uint8(overlay), path_value);
end


function initialize_struct_csv(path_value, empty_row, replace_existing)
    if replace_existing && isfile(path_value)
        delete(path_value);
    end
    if ~isfile(path_value)
        empty_rows = repmat(empty_row, 0, 1);
        writetable(struct2table(empty_rows), path_value);
    end
end


function append_struct_row_csv(path_value, row)
    writetable(struct2table(row), path_value, 'WriteMode', 'append', ...
        'WriteVariableNames', false);
end


function initialize_mask_stack_h5(path_value, mask_shape, frame_count, config, ...
        score_mode, threshold)
    if isfile(path_value)
        delete(path_value);
    end
    dataset = char(string(config.mask_stack_dataset));
    h = mask_shape(1);
    w = mask_shape(2);
    create_args = {'Datatype', 'uint8', 'ChunkSize', [h, w, 1]};
    if config.mask_stack_deflate > 0
        create_args = [create_args, {'Deflate', config.mask_stack_deflate}]; %#ok<AGROW>
    end
    h5create(path_value, dataset, [h, w, frame_count], create_args{:});
    h5writeatt(path_value, dataset, 'mask_grid', char(string(config.mask_grid)));
    h5writeatt(path_value, dataset, 'processing_scale_factor', ...
        config.processing_scale_factor);
    h5writeatt(path_value, dataset, 'score_mode', char(string(score_mode)));
    h5writeatt(path_value, dataset, 'threshold_value', threshold.value);
    h5writeatt(path_value, dataset, 'threshold_source', ...
        char(string(threshold.source)));
    h5writeatt(path_value, dataset, 'min_area_px', config.min_area_px);
    h5writeatt(path_value, dataset, 'morph_radius', config.morph_radius);
end


function row = empty_mask_stack_row()
    row = struct( ...
        'frame_index', NaN, ...
        'label', "", ...
        'role', "", ...
        'time_s', NaN, ...
        'h5_dataset', "", ...
        'h5_frame_index', NaN, ...
        'mask_grid', "", ...
        'mask_height', NaN, ...
        'mask_width', NaN, ...
        'processing_scale_factor', NaN, ...
        'score_mode', "", ...
        'threshold_value', NaN, ...
        'threshold_source', "", ...
        'red_mask_area_px', NaN, ...
        'domain_area_px', NaN);
end


function row = mask_stack_row(frame_index, time_s, label, role, config, ...
        threshold, metrics, mask_shape)
    row = empty_mask_stack_row();
    row.frame_index = frame_index;
    row.label = string(label);
    row.role = string(role);
    row.time_s = time_s;
    row.h5_dataset = string(config.mask_stack_dataset);
    row.h5_frame_index = frame_index;
    row.mask_grid = string(config.mask_grid);
    row.mask_height = mask_shape(1);
    row.mask_width = mask_shape(2);
    row.processing_scale_factor = config.processing_scale_factor;
    row.score_mode = string(config.production_score_mode);
    row.threshold_value = threshold.value;
    row.threshold_source = string(threshold.source);
    row.red_mask_area_px = metrics.red_mask_area_px;
    row.domain_area_px = metrics.domain_area_px;
end


function initialize_blob_detail_csv(path_value, replace_existing)
    if replace_existing && isfile(path_value)
        delete(path_value);
    end
    if ~isfile(path_value)
        writetable(empty_c2_blob_detail_table(), path_value);
    end
end


function append_blob_detail_csv(path_value, blob_table)
    if isempty(blob_table) || height(blob_table) == 0
        return;
    end
    writetable(blob_table, path_value, 'WriteMode', 'append', ...
        'WriteVariableNames', false);
end


function blob_table = add_blob_detail_context(blob_table, frame_index, time_s, ...
        label, role, score_mode, threshold, config)
    if isempty(blob_table)
        blob_table = empty_c2_blob_detail_table();
        return;
    end
    blob_table.frame_index = repmat(frame_index, height(blob_table), 1);
    blob_table.time_s = repmat(time_s, height(blob_table), 1);
    blob_table.label = repmat(string(label), height(blob_table), 1);
    blob_table.role = repmat(string(role), height(blob_table), 1);
    blob_table.score_mode = repmat(string(score_mode), height(blob_table), 1);
    blob_table.threshold_value = repmat(threshold.value, height(blob_table), 1);
    blob_table.threshold_source = repmat(string(threshold.source), height(blob_table), 1);
    blob_table.mask_grid = repmat(string(config.mask_grid), height(blob_table), 1);
    blob_table.processing_scale_factor = repmat( ...
        config.processing_scale_factor, height(blob_table), 1);
    blob_table = normalize_c2_blob_detail_table(blob_table);
end


function T = empty_c2_blob_detail_table()
    schema = get_blob_detail_legacy_schema();
    T = schema.empty_table;
    T.frame_index = zeros(0, 1);
    T.time_s = zeros(0, 1);
    T.label = strings(0, 1);
    T.role = strings(0, 1);
    T.score_mode = strings(0, 1);
    T.threshold_value = zeros(0, 1);
    T.threshold_source = strings(0, 1);
    T.mask_grid = strings(0, 1);
end


function T = normalize_c2_blob_detail_table(T)
    template = empty_c2_blob_detail_table();
    target_names = template.Properties.VariableNames;
    n_rows = height(T);
    for idx = 1:numel(target_names)
        name = target_names{idx};
        if ~ismember(name, T.Properties.VariableNames)
            T.(name) = default_table_column(template.(name), n_rows);
        end
    end
    T = T(:, target_names);
end


function values = default_table_column(template_values, n_rows)
    if isstring(template_values)
        values = strings(n_rows, 1);
    elseif islogical(template_values)
        values = false(n_rows, 1);
    else
        values = zeros(n_rows, 1);
    end
end


function write_segmentation_manifest(path_value, run_mode, config, cache_dir, ...
        out_dir, config_path, primary_path, secondary_path, detail_path, ...
        mask_stack_path, mask_stack_manifest_path, detail_chunks_dir, ...
        detail_chunk_path)
    if nargin < 10
        mask_stack_path = '';
    end
    if nargin < 11
        mask_stack_manifest_path = '';
    end
    if nargin < 12
        detail_chunks_dir = '';
    end
    if nargin < 13
        detail_chunk_path = '';
    end
    manifest = struct();
    manifest.pipeline = 'A1_1BO_6UL_HDF5_cache_C2_red_segmentation_morphology';
    manifest.created_at = datestr(now, 'yyyy-mm-ddTHH:MM:SS');
    manifest.run_mode = run_mode;
    manifest.cache_dir = cache_dir;
    manifest.output_dir = out_dir;
    manifest.config_path = config_path;
    manifest.segmentation_output = 'red_napl_mask';
    manifest.output_semantics = 'segmentation-derived red DNAPL 2D occupancy';
    manifest.interface_semantics = ...
        'InterfaceArea is a legacy alias of dnapl_water_length_px/L_ow, not area';
    manifest.endpoint_dependency = 'none';
    manifest.mask_grid = char(string(config.mask_grid));
    manifest.processing_scale_factor = config.processing_scale_factor;
    manifest.score_modes = cellstr(string(config.score_modes));
    manifest.production_score_mode = char(string(config.production_score_mode));
    manifest.locked_threshold = config.locked_threshold;
    manifest.threshold_source = char(string(config.threshold_source));
    manifest.threshold_percentiles = config.threshold_percentiles;
    manifest.min_area_px = config.min_area_px;
    manifest.morph_radius = config.morph_radius;
    manifest.processing_pixel_size_m = config.processing_pixel_size_m;
    manifest.interface_solid_dilation = config.interface_solid_dilation;
    manifest.frame_start_index = config.frame_start_index;
    manifest.frame_end_index = config.frame_end_index;
    manifest.resume_outputs = config.resume_outputs;
    manifest.blob_detail_output_mode = char(string(config.blob_detail_output_mode));
    manifest.blob_detail_chunks_dir_name = char(string( ...
        config.blob_detail_chunks_dir_name));
    manifest.files = struct( ...
        'primary_csv', primary_path, ...
        'secondary_csv', secondary_path, ...
        'blob_detail_csv', detail_path, ...
        'blob_detail_chunks_dir', detail_chunks_dir, ...
        'blob_detail_chunk_csv', detail_chunk_path, ...
        'red_mask_stack_h5', mask_stack_path, ...
        'red_mask_stack_manifest_csv', mask_stack_manifest_path);

    fid = fopen(path_value, 'w');
    if fid < 0
        error('segmentation_morphology:manifestOpenFailed', ...
            'Cannot write manifest: %s', path_value);
    end
    cleanup = onCleanup(@() fclose(fid));
    fwrite(fid, jsonencode(manifest), 'char');
end


function token = sanitize_token(value)
    token = regexprep(char(string(value)), '[^A-Za-z0-9_-]+', '_');
    token = regexprep(token, '_+', '_');
    token = regexprep(token, '^_|_$', '');
    if isempty(token)
        token = 'value';
    end
end


function value = median_or_nan(values)
    values = values(isfinite(values));
    if isempty(values)
        value = NaN;
    else
        value = median(values);
    end
end
