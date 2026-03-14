function [sol, heartbeat] = characterize_solubilization_v2(frame_index, flow_domain, time_vector, config, heartbeat)
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
%
%   Output:
%       sol - Struct with time-series results:
%           .saturation_vs_time, .num_blobs_vs_time, .mean_blob_size_vs_time,
%           .interface_area_vs_time, .dissolution_rate, .fitted_model,
%           .change, .mass_dissolved, .masks

    if nargin < 5
        heartbeat = struct('enabled', false);
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
            available_vars = who('-file', cp_latest);
            requested_vars = {'sn_arr', 'nblobs_arr', 'mbs_arr', 'iface_arr', ...
                              'last_frame', 'change_arr', 'first_mask', 'prev_mask', ...
                              'last_mask', 'masks_arr', 'locked_threshold'};
            load_vars = requested_vars(ismember(requested_vars, available_vars));
            cp_data = load(cp_latest, load_vars{:});

            sn_arr     = cp_data.sn_arr;
            nblobs_arr = cp_data.nblobs_arr;
            mbs_arr    = cp_data.mbs_arr;
            iface_arr  = cp_data.iface_arr;

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
            last_completed_frame = min(cp_data.last_frame, num_frames);
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
            [nblobs_arr(1), mbs_arr(1)] = compute_timeseries_blob_metrics(first_mask);
            iface_arr(1) = compute_timeseries_interface_length(first_mask, solid_contact_zone);
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
            [nblobs_arr(t), mbs_arr(t)] = compute_timeseries_blob_metrics(mask_t);
            iface_arr(t) = compute_timeseries_interface_length(mask_t, solid_contact_zone);
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
            [nblobs_arr(t), mbs_arr(t)] = compute_timeseries_blob_metrics(mask_t);
            iface_arr(t) = compute_timeseries_interface_length(mask_t, solid_contact_zone);
            change_arr(t-1) = compute_change_metrics(prev_mask, mask_t);
            prev_mask = mask_t;
            last_completed_frame = t;
            processed_this_session = processed_this_session + 1;
            heartbeat = write_pipeline_heartbeat(heartbeat, struct( ...
                'status', 'running', ...
                'step', 'STEP 4', ...
                'step_label', 'Solubilization Dynamics', ...
                'current_frame', t, ...
                'total_frames', num_frames, ...
                'message', sprintf('Processed frame %d of %d', t, num_frames)));

            if do_checkpoint && mod(t, save_interval) == 0
                last_frame = t; %#ok<NASGU>
                cp_file = fullfile(cp_dir, sprintf('checkpoint_%04d.mat', t));
                save(cp_file, 'sn_arr', 'nblobs_arr', 'mbs_arr', ...
                     'iface_arr', 'change_arr', 'first_mask', 'prev_mask', ...
                     'last_mask', 'last_frame', 'locked_threshold', '-v7.3');
                last_checkpoint_path = cp_file;
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
                            nblobs_arr, mbs_arr, iface_arr, t, locked_threshold);
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
                        sn_arr, nblobs_arr, mbs_arr, iface_arr, change_arr, change_template, ...
                        masks_arr, first_mask, last_mask, use_parallel, time_vector, ...
                        flow_domain, px, config.physical.depth, config.physical.dnapl_density, ...
                        last_completed_frame, session_status, ...
                        resume_from_frame, last_checkpoint_path);
                    return;
                end
            end

            if do_save_progress && mod(t, progress_interval) == 0
                export_progress_snapshot(config.output_path, time_vector, sn_arr, ...
                    nblobs_arr, mbs_arr, iface_arr, t, locked_threshold);
                last_progress_frame_saved = t;
            end
        end
    end

    if do_save_progress && last_progress_frame_saved ~= last_completed_frame
        export_progress_snapshot(config.output_path, time_vector, sn_arr, ...
            nblobs_arr, mbs_arr, iface_arr, last_completed_frame, locked_threshold);
    end
    sol = finalize_solubilization( ...
        sn_arr, nblobs_arr, mbs_arr, iface_arr, change_arr, change_template, ...
        masks_arr, first_mask, last_mask, use_parallel, time_vector, ...
        flow_domain, px, config.physical.depth, config.physical.dnapl_density, ...
        last_completed_frame, session_status, ...
        resume_from_frame, last_checkpoint_path);
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


function sol = finalize_solubilization(sn_arr, nblobs_arr, mbs_arr, iface_arr, ...
        change_arr, change_template, masks_arr, first_mask, last_mask, ...
        use_parallel, time_vector, flow_domain, px, depth, rho, last_completed_frame, ...
        session_status, resume_from_frame, last_checkpoint_path)

    valid_frames = max(min(last_completed_frame, numel(sn_arr)), 1);

    sol.saturation_vs_time     = sn_arr(1:valid_frames);
    sol.num_blobs_vs_time      = nblobs_arr(1:valid_frames);
    sol.mean_blob_size_vs_time = mbs_arr(1:valid_frames);
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
