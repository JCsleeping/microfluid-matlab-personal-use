function [sol, heartbeat] = characterize_solubilization_v2(frame_index, flow_domain, time_vector, config, heartbeat, solid_mask)
% CHARACTERIZE_SOLUBILIZATION_V2  Track DNAPL dissolution across a time series.
%
%   sol = characterize_solubilization_v2(frame_index, flow_domain, time_vector, config)
%
%   Uses lazy loading: frames are loaded one-by-one via load_frame() to
%   avoid holding all images in memory simultaneously.
%
%   Supports parallel processing (parfor) when Parallel Computing Toolbox
%   is available. Set config.parallel.enabled = true to activate.
%
%   Inputs:
%       frame_index  - Struct array with fields .tif_path, .page (from pipeline)
%       flow_domain  - M x N logical pore-space mask (constant)
%       time_vector  - 1 x N time stamps [s or PV]
%       config       - Pipeline configuration struct
%       solid_mask   - Optional M x N logical solid mask for hole classification
%
%   Output:
%       sol - Struct with time-series results:
%           .saturation_vs_time, .num_blobs_vs_time, .mean_blob_size_vs_time,
%           .interface_area_vs_time, .dissolution_rate, .fitted_model,
%           .change, .mass_dissolved, .masks

    if nargin < 5
        heartbeat = struct('enabled', false);
    end
    if nargin < 6
        solid_mask = [];
    end

    num_frames = numel(frame_index);
    px = config.physical.pixel_size;
    is_v2 = endsWith(config.segmentation.method, '_v2');

    use_parallel = isfield(config, 'parallel') && ...
                   isfield(config.parallel, 'enabled') && ...
                   config.parallel.enabled;
    do_save_progress = isfield(config, 'output') && ...
                       isfield(config.output, 'save_progress') && ...
                       config.output.save_progress;
    progress_interval = 50;
    last_progress_frame_saved = 0;
    if isfield(config, 'output') && isfield(config.output, 'progress_interval') && ...
            ~isempty(config.output.progress_interval)
        progress_interval = config.output.progress_interval;
    end
    max_frames_per_session = inf;
    if isfield(config, 'output') && isfield(config.output, 'max_frames_per_session') && ...
            ~isempty(config.output.max_frames_per_session)
        max_frames_per_session = config.output.max_frames_per_session;
    end
    do_checkpoint = isfield(config, 'output') && ...
                    isfield(config.output, 'checkpoint') && ...
                    config.output.checkpoint;
    do_save_blob_detail = isfield(config, 'output') && ...
                          isfield(config.output, 'save_blob_detail') && ...
                          config.output.save_blob_detail;
    blob_detail_csv_path = fullfile(config.output_path, 'blob_detail_all_frames.csv');
    blob_detail_chunks_dir = fullfile(config.output_path, 'blob_detail_chunks');
    blob_detail_schema = get_blob_detail_legacy_schema();
    geometry_opts = resolve_geometry_options(config);
    blob_detail_writer = [];
    blob_detail_csv_exported = false;
    blob_detail_timing = struct('buffer_push_time_sec', 0, ...
        'chunk_flush_time_sec', 0, 'csv_merge_time_sec', 0);
    blob_detail_chunk_size = 100;
    if isfield(config.output, 'blob_detail_chunk_size') && ~isempty(config.output.blob_detail_chunk_size)
        blob_detail_chunk_size = config.output.blob_detail_chunk_size;
    end
    blob_detail_save_format = 'v7';
    if isfield(config.output, 'blob_detail_save_format') && ~isempty(config.output.blob_detail_save_format)
        blob_detail_save_format = config.output.blob_detail_save_format;
    end
    blob_detail_allow_format_fallback = true;
    if isfield(config.output, 'blob_detail_allow_format_fallback') && ...
            ~isempty(config.output.blob_detail_allow_format_fallback)
        blob_detail_allow_format_fallback = config.output.blob_detail_allow_format_fallback;
    end
    blob_detail_chunk_max_bytes = 512 * 1024^2;
    if isfield(config.output, 'blob_detail_chunk_max_bytes') && ...
            ~isempty(config.output.blob_detail_chunk_max_bytes)
        blob_detail_chunk_max_bytes = config.output.blob_detail_chunk_max_bytes;
    end
    save_interval = [];
    if do_checkpoint
        save_interval = config.output.save_interval;
    end

    session_status = 'completed';
    resume_from_frame = [];
    last_checkpoint_path = '';
    last_completed_frame = 0;
    processed_this_session = 0;
    fresh_session_credit = 0;

    %% Preallocate
    sn_arr     = zeros(num_frames, 1);
    nblobs_arr = zeros(num_frames, 1);
    mbs_arr    = zeros(num_frames, 1);
    max_blob_frac_arr = zeros(num_frames, 1);
    Req_median_arr = zeros(num_frames, 1);
    Req_mean_arr = zeros(num_frames, 1);
    Req_std_arr = zeros(num_frames, 1);
    mean_circularity_arr = zeros(num_frames, 1);
    a_i_2D_arr = zeros(num_frames, 1);
    n_droplets_arr = zeros(num_frames, 1);
    n_columns_arr = zeros(num_frames, 1);
    n_clusters_arr = zeros(num_frames, 1);
    frac_droplets_arr = zeros(num_frames, 1);
    frac_columns_arr = zeros(num_frames, 1);
    frac_clusters_arr = zeros(num_frames, 1);
    iface_arr  = zeros(num_frames, 1);
    masks_arr  = {};
    change_template = struct('dissolved_px', [], 'appeared_px', [], 'net_px', []);
    change_arr = repmat(change_template, max(num_frames - 1, 0), 1);

    %% Runtime controls and shared constants
    do_registration = isfield(config, 'registration') && ...
                      isfield(config.registration, 'method') && ...
                      ~strcmpi(config.registration.method, 'none');
    fd_size = [size(flow_domain,1), size(flow_domain,2)];
    solid_contact_zone = build_solid_contact_zone(flow_domain, config);
    start_frame = 2;
    ref_image = [];
    first_mask = [];
    prev_mask = [];
    last_mask = [];
    locked_threshold = [];
    is_resumed_checkpoint = false;
    used_legacy_checkpoint = false;

    parallel_mask_limit_gb = 2.0;
    estimated_mask_gb = prod(double(fd_size)) * double(num_frames) / (1024 ^ 3);
    if use_parallel && estimated_mask_gb > parallel_mask_limit_gb
        warning('characterize_solubilization_v2:parallelMaskFootprint', ...
            ['Estimated mask footprint %.2f GB across %d frames exceeds the %.2f GB ', ...
             'parallel safety limit. Falling back to sequential mode.'], ...
            estimated_mask_gb, num_frames, parallel_mask_limit_gb);
        use_parallel = false;
        heartbeat = write_pipeline_heartbeat(heartbeat, struct( ...
            'status', 'running', ...
            'step', 'STEP 4', ...
            'step_label', 'Solubilization Dynamics', ...
            'current_frame', last_completed_frame, ...
            'total_frames', num_frames, ...
            'message', sprintf('Sequential fallback: estimated mask footprint %.2f GB', estimated_mask_gb), ...
            'force', true));
    end

    do_write_blob_detail = do_save_blob_detail && ~use_parallel;
    if do_write_blob_detail && ~isfolder(config.output_path)
        mkdir(config.output_path);
    end
    if do_write_blob_detail
        assert_geometry_schema_compatible(config.output_path, geometry_opts);
        write_geometry_schema_manifest(config.output_path, geometry_opts);
        fprintf('  Per-blob detail chunks: %s\n', blob_detail_chunks_dir);
        fprintf('  Per-blob detail CSV: %s (exported on normal completion)\n', blob_detail_csv_path);
        fprintf('  Blob geometry mode: %s (%s)\n', ...
            geometry_opts.mode, geometry_opts.schema_version);
    elseif do_save_blob_detail && use_parallel
        fprintf('  Per-blob detail CSV: disabled in parallel mode\n');
    else
        fprintf('  Per-blob detail CSV: disabled (set output.save_blob_detail=true for sequential runs)\n');
    end

    %% Sequential checkpoint resume happens before frame-1 threshold lock.
    if ~use_parallel && do_checkpoint
        cp_dir = config.output_path;
        if ~isfolder(cp_dir)
            mkdir(cp_dir);
        end

        cp_files = dir(fullfile(cp_dir, 'checkpoint_*.mat'));
        if ~isempty(cp_files)
            [~, idx] = sort({cp_files.name});
            cp_latest = fullfile(cp_dir, cp_files(idx(end)).name);
            try
                available_vars = who('-file', cp_latest);
                requested_vars = {'sn_arr', 'nblobs_arr', 'mbs_arr', 'max_blob_frac_arr', ...
                                  'Req_median_arr', 'Req_mean_arr', 'Req_std_arr', ...
                                  'mean_circularity_arr', 'a_i_2D_arr', 'n_droplets_arr', ...
                                  'n_columns_arr', 'n_clusters_arr', 'frac_droplets_arr', ...
                                  'frac_columns_arr', 'frac_clusters_arr', 'iface_arr', ...
                                  'last_frame', 'change_arr', 'first_mask', 'prev_mask', ...
                                  'last_mask', 'masks_arr', 'locked_threshold', ...
                                  'a_i_2D_units', 'a_i_2D_pixel_size'};
                load_vars = requested_vars(ismember(requested_vars, available_vars));
                cp_data = load(cp_latest, load_vars{:});
            catch ME_cp
                warning('characterize_solubilization_v2:corruptCheckpoint', ...
                    'Checkpoint %s is corrupted or unreadable: %s\nStarting fresh.', ...
                    cp_latest, ME_cp.message);
                cp_files = [];  % fall through to fresh start
            end
        end
        if ~isempty(cp_files)
            checkpoint_last_frame = min(cp_data.last_frame, num_frames);
            sn_arr     = cp_data.sn_arr;
            nblobs_arr = cp_data.nblobs_arr;
            mbs_arr    = cp_data.mbs_arr;
            missing_metric_fields = {};
            [max_blob_frac_arr, is_missing] = checkpoint_series(cp_data, 'max_blob_frac_arr', num_frames, checkpoint_last_frame);
            missing_metric_fields = collect_missing_metric_field(missing_metric_fields, 'max_blob_frac_arr', is_missing);
            [Req_median_arr, is_missing] = checkpoint_series(cp_data, 'Req_median_arr', num_frames, checkpoint_last_frame);
            missing_metric_fields = collect_missing_metric_field(missing_metric_fields, 'Req_median_arr', is_missing);
            [Req_mean_arr, is_missing] = checkpoint_series(cp_data, 'Req_mean_arr', num_frames, checkpoint_last_frame);
            missing_metric_fields = collect_missing_metric_field(missing_metric_fields, 'Req_mean_arr', is_missing);
            [Req_std_arr, is_missing] = checkpoint_series(cp_data, 'Req_std_arr', num_frames, checkpoint_last_frame);
            missing_metric_fields = collect_missing_metric_field(missing_metric_fields, 'Req_std_arr', is_missing);
            [mean_circularity_arr, is_missing] = checkpoint_series(cp_data, 'mean_circularity_arr', num_frames, checkpoint_last_frame);
            missing_metric_fields = collect_missing_metric_field(missing_metric_fields, 'mean_circularity_arr', is_missing);
            [a_i_2D_arr, is_missing] = checkpoint_series(cp_data, 'a_i_2D_arr', num_frames, checkpoint_last_frame);
            missing_metric_fields = collect_missing_metric_field(missing_metric_fields, 'a_i_2D_arr', is_missing);
            if ~is_missing
                [a_i_2D_arr, has_incompatible_ai_units] = ...
                    invalidate_incompatible_ai_2d_checkpoint(a_i_2D_arr, cp_data, checkpoint_last_frame, px);
                if has_incompatible_ai_units
                    warning('characterize_solubilization_v2:legacyAi2DCheckpointUnits', ...
                        ['Checkpoint %s has no compatible a_i_2D units metadata. ' ...
                         'Historical a_i_2D values through frame %d will be marked NaN until recomputed.'], ...
                        cp_files(idx(end)).name, checkpoint_last_frame);
                end
            end
            [n_droplets_arr, is_missing] = checkpoint_series(cp_data, 'n_droplets_arr', num_frames, checkpoint_last_frame);
            missing_metric_fields = collect_missing_metric_field(missing_metric_fields, 'n_droplets_arr', is_missing);
            [n_columns_arr, is_missing] = checkpoint_series(cp_data, 'n_columns_arr', num_frames, checkpoint_last_frame);
            missing_metric_fields = collect_missing_metric_field(missing_metric_fields, 'n_columns_arr', is_missing);
            [n_clusters_arr, is_missing] = checkpoint_series(cp_data, 'n_clusters_arr', num_frames, checkpoint_last_frame);
            missing_metric_fields = collect_missing_metric_field(missing_metric_fields, 'n_clusters_arr', is_missing);
            [frac_droplets_arr, is_missing] = checkpoint_series(cp_data, 'frac_droplets_arr', num_frames, checkpoint_last_frame);
            missing_metric_fields = collect_missing_metric_field(missing_metric_fields, 'frac_droplets_arr', is_missing);
            [frac_columns_arr, is_missing] = checkpoint_series(cp_data, 'frac_columns_arr', num_frames, checkpoint_last_frame);
            missing_metric_fields = collect_missing_metric_field(missing_metric_fields, 'frac_columns_arr', is_missing);
            [frac_clusters_arr, is_missing] = checkpoint_series(cp_data, 'frac_clusters_arr', num_frames, checkpoint_last_frame);
            missing_metric_fields = collect_missing_metric_field(missing_metric_fields, 'frac_clusters_arr', is_missing);
            iface_arr  = cp_data.iface_arr;

            if ~isempty(missing_metric_fields)
                warning('characterize_solubilization_v2:legacyResidualMetricsCheckpoint', ...
                    ['Legacy checkpoint %s is missing Task-4 residual-structure arrays (%s). ' ...
                     'Historical values through frame %d will be marked NaN until recomputed.'], ...
                    cp_files(idx(end)).name, strjoin(missing_metric_fields, ', '), checkpoint_last_frame);
            end

            if isfield(cp_data, 'change_arr')
                change_arr = cp_data.change_arr;
            elseif isfield(cp_data, 'masks_arr')
                change_arr = rebuild_change_from_masks(cp_data.masks_arr, cp_data.last_frame, fd_size);
            end

            if isfield(cp_data, 'first_mask')
                first_mask = normalize_mask_size(cp_data.first_mask, fd_size);
            elseif isfield(cp_data, 'masks_arr') && ~isempty(cp_data.masks_arr) && ...
                    ~isempty(cp_data.masks_arr{1})
                first_mask = normalize_mask_size(cp_data.masks_arr{1}, fd_size);
            end

            if isfield(cp_data, 'prev_mask')
                prev_mask = normalize_mask_size(cp_data.prev_mask, fd_size);
            elseif isfield(cp_data, 'masks_arr') && numel(cp_data.masks_arr) >= cp_data.last_frame && ...
                    ~isempty(cp_data.masks_arr{cp_data.last_frame})
                prev_mask = normalize_mask_size(cp_data.masks_arr{cp_data.last_frame}, fd_size);
            end

            if isfield(cp_data, 'last_mask')
                last_mask = normalize_mask_size(cp_data.last_mask, fd_size);
            else
                last_mask = prev_mask;
            end

            start_frame = min(cp_data.last_frame + 1, num_frames + 1);
            last_completed_frame = checkpoint_last_frame;
            last_checkpoint_path = cp_latest;
            is_resumed_checkpoint = true;

            if isfield(cp_data, 'locked_threshold') && ~isempty(cp_data.locked_threshold)
                locked_threshold = cp_data.locked_threshold;
                fprintf('  Checkpoint: resuming from frame %d (%s)\n', ...
                    start_frame, cp_files(idx(end)).name);
                fprintf('  Using locked threshold from checkpoint %.4f\n', locked_threshold);
                heartbeat = write_pipeline_heartbeat(heartbeat, struct( ...
                    'status', 'running', ...
                    'step', 'STEP 4', ...
                    'step_label', 'Solubilization Dynamics', ...
                    'current_frame', last_completed_frame, ...
                    'total_frames', num_frames, ...
                    'last_checkpoint', cp_latest, ...
                    'message', sprintf('Using locked threshold from checkpoint %s', cp_files(idx(end)).name), ...
                    'force', true));
            else
                used_legacy_checkpoint = true;
                warning('characterize_solubilization_v2:legacyCheckpoint', ...
                    ['Legacy checkpoint %s does not contain locked_threshold. ' ...
                     'Frame-1 threshold will be recomputed for resume compatibility.'], ...
                    cp_files(idx(end)).name);
                fprintf('  Checkpoint: resuming from frame %d (%s)\n', ...
                    start_frame, cp_files(idx(end)).name);
                fprintf('  Legacy checkpoint detected; recomputing locked threshold from frame 1.\n');
                heartbeat = write_pipeline_heartbeat(heartbeat, struct( ...
                    'status', 'running', ...
                    'step', 'STEP 4', ...
                    'step_label', 'Solubilization Dynamics', ...
                    'current_frame', last_completed_frame, ...
                    'total_frames', num_frames, ...
                    'last_checkpoint', cp_latest, ...
                    'message', sprintf('Legacy checkpoint %s; recomputing locked threshold', cp_files(idx(end)).name), ...
                    'force', true));
            end
        end
    end

    if do_write_blob_detail
        if is_resumed_checkpoint
            reconcile_status = reconcile_blob_detail_chunks(blob_detail_chunks_dir, ...
                nblobs_arr, last_completed_frame, blob_detail_csv_path, 'resume');
            blob_detail_writer = init_blob_detail_chunk_writer(config.output_path, ...
                blob_detail_chunk_size, blob_detail_save_format, 'resume', ...
                blob_detail_schema, reconcile_status.last_verified_frame, ...
                blob_detail_allow_format_fallback, blob_detail_chunk_max_bytes);
        else
            blob_detail_writer = init_blob_detail_chunk_writer(config.output_path, ...
                blob_detail_chunk_size, blob_detail_save_format, 'fresh', ...
                blob_detail_schema, 0, blob_detail_allow_format_fallback, ...
                blob_detail_chunk_max_bytes);
        end
        print_blob_detail_writer_diagnostics(blob_detail_writer);
    end

    %% Frame 1 establishes the locked threshold or rebuilds the registration reference.
    need_frame1_reference = do_registration || isempty(locked_threshold) || isempty(first_mask);
    if need_frame1_reference
        show_frame1_header = isempty(locked_threshold);
        if show_frame1_header
            fprintf('\n  --- Frame 1 / %d ---\n', num_frames);
        end

        rgb = load_frame(1, frame_index);
        [rgb_rot, ~, ~] = rotate_and_crop(rgb, config);
        [rgb_corr, ~] = correct_illumination(rgb_rot, ...
            config.illumination.method, config.illumination, config.parallel.use_gpu);
        if size(rgb_corr,1) ~= size(flow_domain,1) || size(rgb_corr,2) ~= size(flow_domain,2)
            rgb_corr = imresize(rgb_corr, size(flow_domain));
        end
        ref_image = rgb_corr;

        if isempty(locked_threshold)
            if is_v2
                [dnapl_mask, ~, seg_info_1] = segment_DNAPL_v2(rgb_corr, flow_domain, config);
            else
                [dnapl_mask, ~, seg_info_1] = segment_DNAPL(rgb_corr, flow_domain, config);
            end

            locked_threshold = seg_info_1.threshold;
            fprintf('  >> Threshold locked at %.4f (from frame 1)\n', locked_threshold);

            first_mask = normalize_mask_size(dnapl_mask, fd_size);
            prev_mask = first_mask;
            last_mask = first_mask;

            sat = calculate_saturation(first_mask, flow_domain, px);
            sn_arr(1) = sat.Sn;
            iface_arr(1) = compute_timeseries_interface_length(first_mask, solid_contact_zone);
            if do_write_blob_detail
                breadcrumb_extra = geometry_breadcrumb_extra(first_mask, geometry_opts);
                write_geometry_breadcrumb(config, geometry_opts, 1, num_frames, ...
                    'before_blob_metrics', breadcrumb_extra);
            end
            [blob_metrics_1, blob_table_1] = compute_timeseries_blob_metrics( ...
                first_mask, flow_domain, solid_mask, geometry_opts);
            if do_write_blob_detail
                write_geometry_breadcrumb(config, geometry_opts, 1, num_frames, ...
                    'after_blob_metrics', breadcrumb_extra);
            end
            nblobs_arr(1) = blob_metrics_1.num_blobs;
            mbs_arr(1) = blob_metrics_1.mean_blob_size;
            max_blob_frac_arr(1) = blob_metrics_1.max_blob_frac;
            Req_median_arr(1) = blob_metrics_1.Req_median;
            Req_mean_arr(1) = blob_metrics_1.Req_mean;
            Req_std_arr(1) = blob_metrics_1.Req_std;
            mean_circularity_arr(1) = blob_metrics_1.mean_circularity;
            a_i_2D_arr(1) = compute_ai_2d(first_mask, iface_arr(1), px, flow_domain);
            n_droplets_arr(1) = blob_metrics_1.n_droplets;
            n_columns_arr(1) = blob_metrics_1.n_columns;
            n_clusters_arr(1) = blob_metrics_1.n_clusters;
            frac_droplets_arr(1) = blob_metrics_1.frac_droplets;
            frac_columns_arr(1) = blob_metrics_1.frac_columns;
            frac_clusters_arr(1) = blob_metrics_1.frac_clusters;
            if do_write_blob_detail && ~is_resumed_checkpoint
                blob_detail_writer = append_blob_detail_chunk(blob_detail_writer, ...
                    1, time_vector(1), blob_table_1, "ok", "");
            end
            last_completed_frame = max(last_completed_frame, 1);

            if ~is_resumed_checkpoint
                fresh_session_credit = 1;
            end

            if used_legacy_checkpoint
                heartbeat_message = sprintf('Legacy checkpoint recovered with threshold %.4f', locked_threshold);
            else
                heartbeat_message = sprintf('Threshold locked at %.4f', locked_threshold);
            end
            heartbeat = write_pipeline_heartbeat(heartbeat, struct( ...
                'status', 'running', ...
                'step', 'STEP 4', ...
                'step_label', 'Solubilization Dynamics', ...
                'current_frame', last_completed_frame, ...
                'total_frames', num_frames, ...
                'last_checkpoint', last_checkpoint_path, ...
                'message', heartbeat_message, ...
                'force', true));
        else
            fprintf('  Rebuilt frame 1 reference image for registration.\n');
        end
    end

    if isempty(first_mask)
        if isempty(ref_image)
            rgb = load_frame(1, frame_index);
            [rgb_rot, ~, ~] = rotate_and_crop(rgb, config);
            [rgb_corr, ~] = correct_illumination(rgb_rot, ...
                config.illumination.method, config.illumination, config.parallel.use_gpu);
            if size(rgb_corr,1) ~= size(flow_domain,1) || size(rgb_corr,2) ~= size(flow_domain,2)
                rgb_corr = imresize(rgb_corr, size(flow_domain));
            end
            ref_image = rgb_corr;
        end

        config_frame1 = config;
        config_frame1.segmentation.fixed_threshold = locked_threshold;
        if is_v2
            [mask_1, ~, ~] = segment_DNAPL_v2(ref_image, flow_domain, config_frame1);
        else
            [mask_1, ~, ~] = segment_DNAPL(ref_image, flow_domain, config_frame1);
        end
        first_mask = normalize_mask_size(mask_1, fd_size);
        if isempty(prev_mask)
            prev_mask = first_mask;
        end
        if isempty(last_mask)
            last_mask = prev_mask;
        end
    end

    % Memory pressure check: warn if system RAM is low for this workload
    try
        mem_info = memory();
        avail_gb = mem_info.MemAvailableAllArrays / (1024^3);
        % Each frame needs ~3 RGB double buffers + 1 logical mask in flight
        bytes_per_frame = prod(double(fd_size)) * 8 * 3 + prod(double(fd_size));
        peak_gb = bytes_per_frame * 4 / (1024^3);  % concurrent buffers
        if peak_gb > avail_gb * 0.5
            warning('characterize_solubilization_v2:memoryPressure', ...
                ['Per-frame working memory ~%.2f GB vs %.2f GB available. ' ...
                 'Consider subsampling with config.pages to reduce memory pressure.'], ...
                peak_gb, avail_gb);
        end
    catch
        % memory() is Windows-only; skip on other platforms
    end

    if use_parallel
        masks_arr = cell(num_frames, 1);
        masks_arr{1} = first_mask;
    end

    %% Frames 2-N use the locked threshold
    if num_frames < 2
        % Only 1 frame, skip.
    elseif use_parallel && ~isempty(which('parfor'))
        pool = gcp('nocreate');
        if isempty(pool)
            pool = parpool('local', config.parallel.num_workers);
        end
        fprintf('\n  Parallel mode: %d workers\n', pool.NumWorkers);
        heartbeat = write_pipeline_heartbeat(heartbeat, struct( ...
            'status', 'running', ...
            'step', 'STEP 4', ...
            'step_label', 'Solubilization Dynamics', ...
            'current_frame', 1, ...
            'total_frames', num_frames, ...
            'message', sprintf('Parallel mode with %d workers', pool.NumWorkers), ...
            'force', true));

        config_locked = config;
        config_locked.segmentation.fixed_threshold = locked_threshold;
        config_locked.parallel.use_gpu = false;
        is_v2 = endsWith(config.segmentation.method, '_v2');

        parfor t = 2:num_frames
            rgb_t = load_frame(t, frame_index);
            [rgb_rot_t, ~, ~] = rotate_and_crop(rgb_t, config_locked);
            [rgb_corr_t, ~] = correct_illumination(rgb_rot_t, ...
                config_locked.illumination.method, config_locked.illumination, false);
            if size(rgb_corr_t,1) ~= size(flow_domain,1) || size(rgb_corr_t,2) ~= size(flow_domain,2)
                rgb_corr_t = imresize(rgb_corr_t, size(flow_domain));
            end
            if do_registration
                [rgb_corr_t, ~] = align_images(rgb_corr_t, ref_image, config_locked);
            end

            if is_v2
                [mask_t, ~, ~] = segment_DNAPL_v2(rgb_corr_t, flow_domain, config_locked);
            else
                [mask_t, ~, ~] = segment_DNAPL(rgb_corr_t, flow_domain, config_locked);
            end
            mask_t = normalize_mask_size(mask_t, fd_size);
            masks_arr{t} = mask_t;

            sat_t = calculate_saturation(mask_t, flow_domain, px);
            sn_arr(t) = sat_t.Sn;
            iface_arr(t) = compute_timeseries_interface_length(mask_t, solid_contact_zone);
            blob_metrics_t = compute_timeseries_blob_metrics(mask_t, flow_domain, solid_mask, geometry_opts);
            nblobs_arr(t) = blob_metrics_t.num_blobs;
            mbs_arr(t) = blob_metrics_t.mean_blob_size;
            max_blob_frac_arr(t) = blob_metrics_t.max_blob_frac;
            Req_median_arr(t) = blob_metrics_t.Req_median;
            Req_mean_arr(t) = blob_metrics_t.Req_mean;
            Req_std_arr(t) = blob_metrics_t.Req_std;
            mean_circularity_arr(t) = blob_metrics_t.mean_circularity;
            a_i_2D_arr(t) = compute_ai_2d(mask_t, iface_arr(t), px, flow_domain);
            n_droplets_arr(t) = blob_metrics_t.n_droplets;
            n_columns_arr(t) = blob_metrics_t.n_columns;
            n_clusters_arr(t) = blob_metrics_t.n_clusters;
            frac_droplets_arr(t) = blob_metrics_t.frac_droplets;
            frac_columns_arr(t) = blob_metrics_t.frac_columns;
            frac_clusters_arr(t) = blob_metrics_t.frac_clusters;
        end
        fprintf('  Parallel processing complete.\n');
        last_completed_frame = num_frames;
        heartbeat = write_pipeline_heartbeat(heartbeat, struct( ...
            'status', 'running', ...
            'step', 'STEP 4', ...
            'step_label', 'Solubilization Dynamics', ...
            'current_frame', num_frames, ...
            'total_frames', num_frames, ...
            'message', 'Parallel processing complete', ...
            'force', true));
    else
        config_locked = config;
        config_locked.segmentation.fixed_threshold = locked_threshold;

        for t = start_frame:num_frames
            fprintf('\n  --- Frame %d / %d ---\n', t, num_frames);
            try
                rgb_t = load_frame(t, frame_index);
                [rgb_rot_t, ~, ~] = rotate_and_crop(rgb_t, config_locked);
                [rgb_corr_t, ~] = correct_illumination(rgb_rot_t, ...
                    config_locked.illumination.method, config_locked.illumination, config.parallel.use_gpu);
                if size(rgb_corr_t,1) ~= size(flow_domain,1) || size(rgb_corr_t,2) ~= size(flow_domain,2)
                    rgb_corr_t = imresize(rgb_corr_t, size(flow_domain));
                end
                if do_registration
                    [rgb_corr_t, ~] = align_images(rgb_corr_t, ref_image, config);
                end

                if endsWith(config.segmentation.method, '_v2')
                    [mask_t, ~, ~] = segment_DNAPL_v2(rgb_corr_t, flow_domain, config_locked);
                else
                    [mask_t, ~, ~] = segment_DNAPL(rgb_corr_t, flow_domain, config_locked);
                end
                mask_t = normalize_mask_size(mask_t, fd_size);
                last_mask = mask_t;

                sat_t = calculate_saturation(mask_t, flow_domain, px);
                sn_arr(t) = sat_t.Sn;
                iface_arr(t) = compute_timeseries_interface_length(mask_t, solid_contact_zone);
                if do_write_blob_detail
                    breadcrumb_extra = geometry_breadcrumb_extra(mask_t, geometry_opts);
                    write_geometry_breadcrumb(config, geometry_opts, t, num_frames, ...
                        'before_blob_metrics', breadcrumb_extra);
                end
                [blob_metrics_t, blob_table_t] = compute_timeseries_blob_metrics( ...
                    mask_t, flow_domain, solid_mask, geometry_opts);
                if do_write_blob_detail
                    write_geometry_breadcrumb(config, geometry_opts, t, num_frames, ...
                        'after_blob_metrics', breadcrumb_extra);
                end
                nblobs_arr(t) = blob_metrics_t.num_blobs;
                mbs_arr(t) = blob_metrics_t.mean_blob_size;
                max_blob_frac_arr(t) = blob_metrics_t.max_blob_frac;
                Req_median_arr(t) = blob_metrics_t.Req_median;
                Req_mean_arr(t) = blob_metrics_t.Req_mean;
                Req_std_arr(t) = blob_metrics_t.Req_std;
                mean_circularity_arr(t) = blob_metrics_t.mean_circularity;
                a_i_2D_arr(t) = compute_ai_2d(mask_t, iface_arr(t), px, flow_domain);
                n_droplets_arr(t) = blob_metrics_t.n_droplets;
                n_columns_arr(t) = blob_metrics_t.n_columns;
                n_clusters_arr(t) = blob_metrics_t.n_clusters;
                frac_droplets_arr(t) = blob_metrics_t.frac_droplets;
                frac_columns_arr(t) = blob_metrics_t.frac_columns;
                frac_clusters_arr(t) = blob_metrics_t.frac_clusters;
                change_arr(t-1) = compute_change_metrics(prev_mask, mask_t);
                if do_write_blob_detail
                    blob_detail_writer = append_blob_detail_chunk(blob_detail_writer, ...
                        t, time_vector(t), blob_table_t, "ok", "");
                end
                prev_mask = mask_t;
            catch ME_frame
                warning('characterize_solubilization_v2:frameError', ...
                    'Frame %d failed: %s. Carrying forward previous values.', t, ME_frame.message);
                % Carry forward previous frame values (sn_arr(t) stays 0 or
                % copies from previous frame)
                if t > 1
                    sn_arr(t)     = sn_arr(t-1);
                    nblobs_arr(t) = nblobs_arr(t-1);
                    mbs_arr(t)    = mbs_arr(t-1);
                    max_blob_frac_arr(t) = max_blob_frac_arr(t-1);
                    Req_median_arr(t) = Req_median_arr(t-1);
                    Req_mean_arr(t) = Req_mean_arr(t-1);
                    Req_std_arr(t) = Req_std_arr(t-1);
                    mean_circularity_arr(t) = mean_circularity_arr(t-1);
                    a_i_2D_arr(t) = a_i_2D_arr(t-1);
                    n_droplets_arr(t) = n_droplets_arr(t-1);
                    n_columns_arr(t) = n_columns_arr(t-1);
                    n_clusters_arr(t) = n_clusters_arr(t-1);
                    frac_droplets_arr(t) = frac_droplets_arr(t-1);
                    frac_columns_arr(t) = frac_columns_arr(t-1);
                    frac_clusters_arr(t) = frac_clusters_arr(t-1);
                    iface_arr(t)  = iface_arr(t-1);
                end
                if do_write_blob_detail
                    blob_detail_writer = append_blob_detail_chunk(blob_detail_writer, ...
                        t, time_vector(t), table(), "failed", ME_frame.message);
                end
            end
            last_completed_frame = t;
            processed_this_session = processed_this_session + 1;

            if do_write_blob_detail && blob_detail_writer.buffer_frame_count >= blob_detail_writer.chunk_size
                [blob_detail_writer, heartbeat] = flush_blob_detail_writer_with_heartbeat( ...
                    blob_detail_writer, heartbeat, t, num_frames);
                blob_detail_timing = writer_timing_struct(blob_detail_writer);
            end

            % Release per-frame intermediate memory immediately
            clear rgb_t rgb_rot_t rgb_corr_t mask_t sat_t;

            % Periodic GPU cache flush (every 50 frames)
            if config.parallel.use_gpu && mod(t, 50) == 0
                try gpu_dev = gpuDevice; wait(gpu_dev); catch; end %#ok<NASGU>
            end
            heartbeat = write_pipeline_heartbeat(heartbeat, struct( ...
                'status', 'running', ...
                'step', 'STEP 4', ...
                'step_label', 'Solubilization Dynamics', ...
                'current_frame', t, ...
                'total_frames', num_frames, ...
                'message', sprintf('Processed frame %d of %d', t, num_frames)));

            if do_checkpoint && mod(t, save_interval) == 0
                if do_write_blob_detail
                    [blob_detail_writer, heartbeat] = flush_blob_detail_writer_with_heartbeat( ...
                        blob_detail_writer, heartbeat, t, num_frames);
                    blob_detail_timing = writer_timing_struct(blob_detail_writer);
                end
                last_frame = t; %#ok<NASGU>
                a_i_2D_units = ai_2d_units_for_pixel_size(px); %#ok<NASGU>
                a_i_2D_pixel_size = ai_2d_checkpoint_pixel_size(px); %#ok<NASGU>
                cp_file = fullfile(cp_dir, sprintf('checkpoint_%04d.mat', t));
                try
                    save(cp_file, 'sn_arr', 'nblobs_arr', 'mbs_arr', ...
                         'max_blob_frac_arr', 'Req_median_arr', 'Req_mean_arr', ...
                         'Req_std_arr', 'mean_circularity_arr', 'a_i_2D_arr', ...
                         'n_droplets_arr', 'n_columns_arr', 'n_clusters_arr', ...
                         'frac_droplets_arr', 'frac_columns_arr', 'frac_clusters_arr', ...
                         'iface_arr', 'change_arr', 'first_mask', 'prev_mask', ...
                         'last_mask', 'last_frame', 'locked_threshold', ...
                         'a_i_2D_units', 'a_i_2D_pixel_size', '-v7.3');
                    last_checkpoint_path = cp_file;
                catch ME_save
                    warning('characterize_solubilization_v2:checkpointSaveFailed', ...
                        'Failed to save checkpoint at frame %d: %s. Continuing without checkpoint.', ...
                        t, ME_save.message);
                end
                heartbeat = write_pipeline_heartbeat(heartbeat, struct( ...
                    'status', 'running', ...
                    'step', 'STEP 4', ...
                    'step_label', 'Solubilization Dynamics', ...
                    'current_frame', t, ...
                    'total_frames', num_frames, ...
                    'last_checkpoint', cp_file, ...
                    'message', sprintf('Checkpoint saved at frame %d', t), ...
                    'force', true));
                fprintf('  Checkpoint saved: %s\n', cp_file);

                if isfinite(max_frames_per_session) && ...
                        (processed_this_session + fresh_session_credit) >= max_frames_per_session && ...
                        t < num_frames
                    if do_save_progress && last_progress_frame_saved ~= t
                        export_progress_snapshot(config.output_path, time_vector, sn_arr, ...
                            nblobs_arr, mbs_arr, max_blob_frac_arr, Req_median_arr, ...
                            Req_mean_arr, Req_std_arr, mean_circularity_arr, ...
                            a_i_2D_arr, n_droplets_arr, n_columns_arr, n_clusters_arr, ...
                            frac_droplets_arr, frac_columns_arr, frac_clusters_arr, ...
                            iface_arr, t, locked_threshold);
                        last_progress_frame_saved = t;
                    end
                    session_status = 'paused';
                    resume_from_frame = t + 1;
                    heartbeat = write_pipeline_heartbeat(heartbeat, struct( ...
                        'status', 'paused', ...
                        'step', 'STEP 4', ...
                        'step_label', 'Solubilization Dynamics', ...
                        'current_frame', t, ...
                        'total_frames', num_frames, ...
                        'last_checkpoint', cp_file, ...
                        'message', sprintf('Safe pause after frame %d. Re-run with the same output_path to resume.', t), ...
                        'force', true));
                    fprintf('  Safe pause reached at checkpoint frame %d. Re-run with the same output_path to resume.\n', t);
                    sol = finalize_solubilization( ...
                        sn_arr, nblobs_arr, mbs_arr, max_blob_frac_arr, Req_median_arr, ...
                        Req_mean_arr, Req_std_arr, mean_circularity_arr, a_i_2D_arr, ...
                        n_droplets_arr, n_columns_arr, n_clusters_arr, ...
                        frac_droplets_arr, frac_columns_arr, frac_clusters_arr, ...
                        iface_arr, change_arr, change_template, ...
                        masks_arr, first_mask, last_mask, use_parallel, time_vector, ...
                        flow_domain, px, config.physical.depth, config.physical.dnapl_density, ...
                        last_completed_frame, session_status, ...
                        resume_from_frame, last_checkpoint_path, ...
                        do_write_blob_detail, blob_detail_chunks_dir, blob_detail_csv_path, ...
                        false, blob_detail_timing);
                    return;
                end
            end

            if do_save_progress && mod(t, progress_interval) == 0
                export_progress_snapshot(config.output_path, time_vector, sn_arr, ...
                    nblobs_arr, mbs_arr, max_blob_frac_arr, Req_median_arr, ...
                    Req_mean_arr, Req_std_arr, mean_circularity_arr, ...
                    a_i_2D_arr, n_droplets_arr, n_columns_arr, n_clusters_arr, ...
                    frac_droplets_arr, frac_columns_arr, frac_clusters_arr, ...
                    iface_arr, t, locked_threshold);
                last_progress_frame_saved = t;
            end
        end
    end

    if do_save_progress && last_progress_frame_saved ~= last_completed_frame
        export_progress_snapshot(config.output_path, time_vector, sn_arr, ...
            nblobs_arr, mbs_arr, max_blob_frac_arr, Req_median_arr, ...
            Req_mean_arr, Req_std_arr, mean_circularity_arr, ...
            a_i_2D_arr, n_droplets_arr, n_columns_arr, n_clusters_arr, ...
            frac_droplets_arr, frac_columns_arr, frac_clusters_arr, ...
            iface_arr, last_completed_frame, locked_threshold);
    end

    if do_write_blob_detail
        [blob_detail_writer, heartbeat] = flush_blob_detail_writer_with_heartbeat( ...
            blob_detail_writer, heartbeat, last_completed_frame, num_frames);
        tic_csv_merge = tic;
        try
            export_blob_detail_chunks_csv(blob_detail_chunks_dir, blob_detail_csv_path, blob_detail_schema);
            blob_detail_csv_exported = true;
        catch csv_export_error
            blob_detail_csv_exported = false;
            warning('characterize_solubilization_v2:blobDetailCsvExportFailed', ...
                ['Failed to export blob detail CSV: %s. Blob detail chunks remain ' ...
                 'available in: %s'], csv_export_error.message, blob_detail_chunks_dir);
        end
        blob_detail_writer.csv_merge_time_sec = blob_detail_writer.csv_merge_time_sec + toc(tic_csv_merge);
        blob_detail_timing = writer_timing_struct(blob_detail_writer);
        fprintf('  Blob detail timing: buffer %.3fs, chunk flush %.3fs, final CSV merge %.3fs\n', ...
            blob_detail_timing.buffer_push_time_sec, ...
            blob_detail_timing.chunk_flush_time_sec, ...
            blob_detail_timing.csv_merge_time_sec);
    end

    sol = finalize_solubilization( ...
        sn_arr, nblobs_arr, mbs_arr, max_blob_frac_arr, Req_median_arr, ...
        Req_mean_arr, Req_std_arr, mean_circularity_arr, a_i_2D_arr, ...
        n_droplets_arr, n_columns_arr, n_clusters_arr, ...
        frac_droplets_arr, frac_columns_arr, frac_clusters_arr, ...
        iface_arr, change_arr, change_template, ...
        masks_arr, first_mask, last_mask, use_parallel, time_vector, ...
        flow_domain, px, config.physical.depth, config.physical.dnapl_density, ...
        last_completed_frame, session_status, ...
        resume_from_frame, last_checkpoint_path, ...
        do_write_blob_detail, blob_detail_chunks_dir, blob_detail_csv_path, ...
        blob_detail_csv_exported, blob_detail_timing);
    heartbeat = write_pipeline_heartbeat(heartbeat, struct( ...
        'status', 'running', ...
        'step', 'STEP 4', ...
        'step_label', 'Solubilization Dynamics', ...
        'current_frame', last_completed_frame, ...
        'total_frames', num_frames, ...
        'message', 'Step 4 complete', ...
        'force', true));

    fprintf('\n  Solubilization complete. Sn: %.3f -> %.3f (%.1f%% removed)\n', ...
        sol.saturation_vs_time(1), sol.saturation_vs_time(end), ...
        100 * (1 - sol.saturation_vs_time(end) / max(sol.saturation_vs_time(1), eps)));
end


function sol = finalize_solubilization(sn_arr, nblobs_arr, mbs_arr, max_blob_frac_arr, ...
        Req_median_arr, Req_mean_arr, Req_std_arr, mean_circularity_arr, ...
        a_i_2D_arr, n_droplets_arr, n_columns_arr, n_clusters_arr, ...
        frac_droplets_arr, frac_columns_arr, frac_clusters_arr, iface_arr, ...
        change_arr, change_template, masks_arr, first_mask, last_mask, ...
        use_parallel, time_vector, flow_domain, px, depth, rho, last_completed_frame, ...
        session_status, resume_from_frame, last_checkpoint_path, ...
        do_write_blob_detail, blob_detail_chunks_dir, blob_detail_csv_path, ...
        blob_detail_csv_exported, blob_detail_timing)

    valid_frames = max(min(last_completed_frame, numel(sn_arr)), 1);

    sol.saturation_vs_time     = sn_arr(1:valid_frames);
    sol.num_blobs_vs_time      = nblobs_arr(1:valid_frames);
    sol.mean_blob_size_vs_time = mbs_arr(1:valid_frames);
    sol.max_blob_frac_vs_time = max_blob_frac_arr(1:valid_frames);
    sol.Req_median_vs_time = Req_median_arr(1:valid_frames);
    sol.Req_mean_vs_time = Req_mean_arr(1:valid_frames);
    sol.Req_std_vs_time = Req_std_arr(1:valid_frames);
    sol.mean_circularity_vs_time = mean_circularity_arr(1:valid_frames);
    sol.a_i_2D_vs_time = a_i_2D_arr(1:valid_frames);
    sol.n_droplets_vs_time = n_droplets_arr(1:valid_frames);
    sol.n_columns_vs_time = n_columns_arr(1:valid_frames);
    sol.n_clusters_vs_time = n_clusters_arr(1:valid_frames);
    sol.frac_droplets_vs_time = frac_droplets_arr(1:valid_frames);
    sol.frac_columns_vs_time = frac_columns_arr(1:valid_frames);
    sol.frac_clusters_vs_time = frac_clusters_arr(1:valid_frames);
    sol.interface_area_vs_time = iface_arr(1:valid_frames);

    dt = diff(time_vector(1:valid_frames).');
    dt(dt == 0) = 1;
    sol.dissolution_rate = diff(sol.saturation_vs_time) ./ dt;

    if use_parallel
        valid_masks = masks_arr(1:valid_frames);
        sol.change = repmat(change_template, max(valid_frames - 1, 0), 1);
        for idx = 2:valid_frames
            sol.change(idx - 1) = compute_change_metrics(valid_masks{idx - 1}, valid_masks{idx});
        end

        sol.masks = cell(valid_frames, 1);
        if valid_frames >= 1
            sol.masks{1} = valid_masks{1};
        end
        if valid_frames > 1
            sol.masks{valid_frames} = valid_masks{valid_frames};
        end
    else
        sol.change = change_arr(1:max(valid_frames - 1, 0));
        sol.masks = cell(valid_frames, 1);
        if valid_frames >= 1
            sol.masks{1} = first_mask;
        end
        if valid_frames > 1
            sol.masks{valid_frames} = last_mask;
        end
    end

    pore_vol = sum(flow_domain(:)) * px^2 * depth;
    sol.mass_dissolved_vs_time = (sol.saturation_vs_time(1) - sol.saturation_vs_time) ...
                                 * pore_vol * rho;
    sol.mass_dissolved = sol.mass_dissolved_vs_time(end);
    sol.last_completed_frame = valid_frames;
    sol.pipeline_status = session_status;
    sol.last_checkpoint = last_checkpoint_path;
    if strcmp(session_status, 'paused')
        sol.resume_from_frame = resume_from_frame;
    end
    sol.blob_detail_chunks_dir = '';
    sol.blob_detail_csv_path = '';
    sol.blob_detail_csv = '';
    sol.blob_detail_csv_exported = false;
    sol.blob_detail_timing = struct('buffer_push_time_sec', 0, ...
        'chunk_flush_time_sec', 0, 'csv_merge_time_sec', 0);
    if do_write_blob_detail
        sol.blob_detail_chunks_dir = blob_detail_chunks_dir;
        sol.blob_detail_csv_path = blob_detail_csv_path;
        sol.blob_detail_csv_exported = logical(blob_detail_csv_exported);
        sol.blob_detail_timing = blob_detail_timing;
        if sol.blob_detail_csv_exported
            sol.blob_detail_csv = blob_detail_csv_path;
        end
    end
end


function [writer, heartbeat] = flush_blob_detail_writer_with_heartbeat(writer, heartbeat, current_frame, total_frames)
    if isempty(writer) || ~isfield(writer, 'buffer_frame_count') || ...
            writer.buffer_frame_count == 0
        return;
    end

    frame_start = writer.buffer_frame_start;
    frame_end = writer.buffer_frame_end;
    heartbeat = write_pipeline_heartbeat(heartbeat, struct( ...
        'status', 'running', ...
        'step', 'STEP 4', ...
        'step_label', sprintf('Solubilization Dynamics (flush %d..%d)', frame_start, frame_end), ...
        'current_frame', current_frame, ...
        'total_frames', total_frames, ...
        'message', sprintf('Flushing blob detail chunk %d..%d', frame_start, frame_end), ...
        'force', true));

    [writer, flushed_paths] = flush_blob_detail_chunks(writer);
    if ~isempty(flushed_paths)
        heartbeat = write_pipeline_heartbeat(heartbeat, struct( ...
            'status', 'running', ...
            'step', 'STEP 4', ...
            'step_label', sprintf('Solubilization Dynamics (flushed %d..%d)', frame_start, frame_end), ...
            'current_frame', current_frame, ...
            'total_frames', total_frames, ...
            'message', sprintf('Flushed blob detail chunk %d..%d', frame_start, frame_end), ...
            'force', true));
    end
end


function timing = writer_timing_struct(writer)
    timing = struct('buffer_push_time_sec', 0, ...
        'chunk_flush_time_sec', 0, 'csv_merge_time_sec', 0);
    if isempty(writer)
        return;
    end
    if isfield(writer, 'buffer_push_time_sec')
        timing.buffer_push_time_sec = writer.buffer_push_time_sec;
    end
    if isfield(writer, 'chunk_flush_time_sec')
        timing.chunk_flush_time_sec = writer.chunk_flush_time_sec;
    end
    if isfield(writer, 'csv_merge_time_sec')
        timing.csv_merge_time_sec = writer.csv_merge_time_sec;
    end
end


function print_blob_detail_writer_diagnostics(writer)
    fprintf('  Blob detail MAT format: requested=%s, selected=%s\n', ...
        writer.requested_save_format, writer.save_format);
    fprintf('  Blob detail chunks dir: %s\n', writer.chunks_dir);
    fprintf('  Blob detail chunks path has non-ASCII: %d\n', writer.chunks_dir_has_non_ascii);
    fprintf('  MATLAB version: %s\n', writer.matlab_version);
    fprintf('  HDF5 version: %s\n', writer.hdf5_version);
    if isfield(writer, 'format_probe') && isfield(writer.format_probe, 'message') && ...
            ~isempty(writer.format_probe.message)
        fprintf('  Blob detail format probe: %s\n', writer.format_probe.message);
    end
end


function geometry_opts = resolve_geometry_options(config)
    if isfield(config, 'geometry') && ~isempty(config.geometry)
        geometry_opts = config.geometry;
    else
        geometry_opts = struct();
    end
    if ~isfield(geometry_opts, 'mode') || isempty(geometry_opts.mode)
        geometry_opts.mode = 'core_only';
    end
    if ~isfield(geometry_opts, 'object_connectivity') || isempty(geometry_opts.object_connectivity)
        geometry_opts.object_connectivity = 8;
    end
    if ~isfield(geometry_opts, 'schema_version') || isempty(geometry_opts.schema_version)
        mode = char(string(geometry_opts.mode));
        if strcmp(mode, 'legacy_fullframe')
            geometry_opts.schema_version = 'geometry_v1_legacy_fullframe';
        elseif strcmp(mode, 'roi')
            geometry_opts.schema_version = 'geometry_v3_roi_holes';
        else
            geometry_opts.schema_version = 'geometry_v2_core_only';
        end
    end
    if ~isfield(geometry_opts, 'include_heavy_shape_props') || isempty(geometry_opts.include_heavy_shape_props)
        geometry_opts.include_heavy_shape_props = true;
    end
    if ~isfield(geometry_opts, 'roi_pad') || isempty(geometry_opts.roi_pad)
        geometry_opts.roi_pad = 1;
    end
    if ~isfield(geometry_opts, 'max_roi_area_fraction') || isempty(geometry_opts.max_roi_area_fraction)
        geometry_opts.max_roi_area_fraction = 0.25;
    end
    if ~isfield(geometry_opts, 'max_roi_pixels') || isempty(geometry_opts.max_roi_pixels)
        geometry_opts.max_roi_pixels = 2e6;
    end
end


function extra = geometry_breadcrumb_extra(mask, geometry_opts)
    extra = struct('num_blobs', NaN, 'nnz_mask', nnz(mask));
    try
        cc_probe = bwconncomp(mask, geometry_opts.object_connectivity);
        extra.num_blobs = cc_probe.NumObjects;
    catch
        % Breadcrumbs are diagnostic only; never change frame processing.
    end
end


function write_geometry_breadcrumb(config, geometry_opts, frame_idx, num_frames, stage, extra)
    if nargin < 6
        extra = struct();
    end

    status_dir = fullfile(config.output_path, 'status');
    if exist(status_dir, 'dir') ~= 7
        mkdir(status_dir);
    end

    breadcrumb = struct();
    breadcrumb.frame = frame_idx;
    breadcrumb.num_frames = num_frames;
    breadcrumb.stage = char(string(stage));
    breadcrumb.timestamp = datestr(now, 30);
    breadcrumb.geometry_mode = char(string(geometry_opts.mode));
    breadcrumb.schema_version = char(string(geometry_opts.schema_version));
    breadcrumb.extra = extra;

    breadcrumb_path = fullfile(status_dir, 'last_geometry_state.mat');
    tmp_path = fullfile(status_dir, 'last_geometry_state.tmp.mat');

    try
        save(tmp_path, 'breadcrumb', '-v7');
        atomic_replace_file(tmp_path, breadcrumb_path, []);
    catch
        if exist(tmp_path, 'file') == 2
            try delete(tmp_path); catch, end %#ok<CTCH>
        end
    end
end


function [value, is_missing] = checkpoint_series(cp_data, field_name, num_frames, checkpoint_last_frame)
    is_missing = ~isfield(cp_data, field_name) || isempty(cp_data.(field_name));
    if is_missing
        value = nan(num_frames, 1);
        if checkpoint_last_frame <= 0
            value(:) = 0;
        end
        return;
    end

    value = nan(num_frames, 1);
    src = cp_data.(field_name);
    src = src(:);
    n = min(num_frames, numel(src));
    value(1:n) = src(1:n);
end


function missing_metric_fields = collect_missing_metric_field(missing_metric_fields, field_name, is_missing)
    if is_missing
        missing_metric_fields{end + 1} = field_name; %#ok<AGROW>
    end
end


function [a_i_2D_arr, is_incompatible] = invalidate_incompatible_ai_2d_checkpoint( ...
        a_i_2D_arr, cp_data, checkpoint_last_frame, px)
    expected_units = ai_2d_units_for_pixel_size(px);
    is_incompatible = true;

    if isfield(cp_data, 'a_i_2D_units') && ...
            strcmp(char(string(cp_data.a_i_2D_units)), expected_units)
        if strcmp(expected_units, 'm^-1')
            is_incompatible = ~(isfield(cp_data, 'a_i_2D_pixel_size') && ...
                isnumeric(cp_data.a_i_2D_pixel_size) && ...
                isscalar(cp_data.a_i_2D_pixel_size) && ...
                isfinite(cp_data.a_i_2D_pixel_size) && ...
                cp_data.a_i_2D_pixel_size == px);
        else
            is_incompatible = false;
        end
    end

    if is_incompatible && checkpoint_last_frame > 0
        a_i_2D_arr(1:checkpoint_last_frame) = NaN;
    end
end


function units = ai_2d_units_for_pixel_size(px)
    if isnumeric(px) && isscalar(px) && isfinite(px) && px > 0
        units = 'm^-1';
    else
        units = 'px^-1';
    end
end


function pixel_size = ai_2d_checkpoint_pixel_size(px)
    if strcmp(ai_2d_units_for_pixel_size(px), 'm^-1')
        pixel_size = px;
    else
        pixel_size = NaN;
    end
end


function a_i_2D = compute_ai_2d(mask, interface_length_px, px, flow_domain)
    dnapl_area_px = sum(mask(:) & flow_domain(:));
    if dnapl_area_px <= 0
        a_i_2D = 0;
        return;
    end

    if isnumeric(px) && isscalar(px) && isfinite(px) && px > 0
        a_i_2D = (interface_length_px * px) / (dnapl_area_px * px^2);
    else
        a_i_2D = interface_length_px / dnapl_area_px;
    end
end


function mask = normalize_mask_size(mask, fd_size)
    if size(mask,1) ~= fd_size(1) || size(mask,2) ~= fd_size(2)
        mask = imresize(mask, fd_size, 'nearest') > 0;
    end
end


function change_metrics = compute_change_metrics(mask_prev, mask_curr)
    mask_prev = logical(mask_prev);
    mask_curr = logical(mask_curr);
    if ~isequal(size(mask_prev), size(mask_curr))
        mask_curr = imresize(mask_curr, size(mask_prev), 'nearest') > 0;
    end

    dissolved = mask_prev & ~mask_curr;
    appeared  = ~mask_prev & mask_curr;
    dissolved_px = sum(dissolved(:));
    appeared_px = sum(appeared(:));

    change_metrics = struct( ...
        'dissolved_px', dissolved_px, ...
        'appeared_px',  appeared_px, ...
        'net_px',       appeared_px - dissolved_px);
end


function change_arr = rebuild_change_from_masks(masks_arr, last_frame, fd_size)
    change_template = struct('dissolved_px', [], 'appeared_px', [], 'net_px', []);
    change_arr = repmat(change_template, max(last_frame - 1, 0), 1);
    for idx = 2:last_frame
        prev_mask = normalize_mask_size(masks_arr{idx - 1}, fd_size);
        curr_mask = normalize_mask_size(masks_arr{idx}, fd_size);
        change_arr(idx - 1) = compute_change_metrics(prev_mask, curr_mask);
    end
end
