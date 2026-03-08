function sol = characterize_solubilization_v2(frame_index, flow_domain, time_vector, config)
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

    num_frames = numel(frame_index);
    px = config.physical.pixel_size;

    % Check parallel config
    use_parallel = isfield(config, 'parallel') && ...
                   isfield(config.parallel, 'enabled') && ...
                   config.parallel.enabled;

    %% Preallocate
    sn_arr     = zeros(num_frames, 1);
    nblobs_arr = zeros(num_frames, 1);
    mbs_arr    = zeros(num_frames, 1);
    iface_arr  = zeros(num_frames, 1);
    masks_arr  = cell(num_frames, 1);

    %% ================================================================
    %  Frame 1: establish threshold (must run first, always sequential)
    %  ================================================================
    fprintf('\n  --- Frame 1 / %d ---\n', num_frames);
    rgb = load_frame(1, frame_index);
    [rgb_rot, ~, ~] = rotate_and_crop(rgb, config);
    [rgb_corr, ~]   = correct_illumination(rgb_rot, ...
        config.illumination.method, config.illumination);
    if size(rgb_corr,1) ~= size(flow_domain,1) || size(rgb_corr,2) ~= size(flow_domain,2)
        rgb_corr = imresize(rgb_corr, size(flow_domain));
    end

    if endsWith(config.segmentation.method, '_v2')
        [dnapl_mask, ~, seg_info_1] = segment_DNAPL_v2(rgb_corr, flow_domain, config);
    else
        [dnapl_mask, ~, seg_info_1] = segment_DNAPL(rgb_corr, flow_domain, config);
    end
    locked_threshold = seg_info_1.threshold;
    fprintf('  >> Threshold locked at %.4f (from frame 1)\n', locked_threshold);

    masks_arr{1} = dnapl_mask;
    sat = calculate_saturation(dnapl_mask, flow_domain, px);
    sn_arr(1) = sat.Sn;
    blob = analyze_blob_geometry(dnapl_mask, px);
    nblobs_arr(1) = blob.num_blobs;
    mbs_arr(1) = blob.size_distribution.mean;
    iface = analyze_interfaces(dnapl_mask, flow_domain, px, config);
    iface_arr(1) = iface.dnapl_water_length_px;

    %% ================================================================
    %  Frames 2-N: use locked threshold (parallelizable)
    %  ================================================================
    if num_frames < 2
        % Only 1 frame, skip
    elseif use_parallel && ~isempty(which('parfor'))
        % --- Parallel mode ---
        pool = gcp('nocreate');
        if isempty(pool)
            pool = parpool('local');
        end
        fprintf('\n  Parallel mode: %d workers\n', pool.NumWorkers);

        % Prepare config with locked threshold
        config_locked = config;
        config_locked.segmentation.fixed_threshold = locked_threshold;
        is_v2 = endsWith(config.segmentation.method, '_v2');

        parfor t = 2:num_frames
            rgb_t = load_frame(t, frame_index);
            [rgb_rot_t, ~, ~] = rotate_and_crop(rgb_t, config_locked);
            [rgb_corr_t, ~]   = correct_illumination(rgb_rot_t, ...
                config_locked.illumination.method, config_locked.illumination);
            if size(rgb_corr_t,1) ~= size(flow_domain,1) || size(rgb_corr_t,2) ~= size(flow_domain,2)
                rgb_corr_t = imresize(rgb_corr_t, size(flow_domain));
            end

            if is_v2
                [mask_t, ~, ~] = segment_DNAPL_v2(rgb_corr_t, flow_domain, config_locked);
            else
                [mask_t, ~, ~] = segment_DNAPL(rgb_corr_t, flow_domain, config_locked);
            end
            masks_arr{t} = mask_t;

            sat_t = calculate_saturation(mask_t, flow_domain, px);
            sn_arr(t) = sat_t.Sn;
            blob_t = analyze_blob_geometry(mask_t, px);
            nblobs_arr(t) = blob_t.num_blobs;
            mbs_arr(t) = blob_t.size_distribution.mean;
            iface_t = analyze_interfaces(mask_t, flow_domain, px, config_locked);
            iface_arr(t) = iface_t.dnapl_water_length_px;
        end
        fprintf('  Parallel processing complete.\n');

    else
        % --- Sequential mode (fallback) ---
        config_locked = config;
        config_locked.segmentation.fixed_threshold = locked_threshold;

        for t = 2:num_frames
            fprintf('\n  --- Frame %d / %d ---\n', t, num_frames);
            rgb_t = load_frame(t, frame_index);
            [rgb_rot_t, ~, ~] = rotate_and_crop(rgb_t, config_locked);
            [rgb_corr_t, ~]   = correct_illumination(rgb_rot_t, ...
                config_locked.illumination.method, config_locked.illumination);
            if size(rgb_corr_t,1) ~= size(flow_domain,1) || size(rgb_corr_t,2) ~= size(flow_domain,2)
                rgb_corr_t = imresize(rgb_corr_t, size(flow_domain));
            end

            if endsWith(config.segmentation.method, '_v2')
                [mask_t, ~, ~] = segment_DNAPL_v2(rgb_corr_t, flow_domain, config_locked);
            else
                [mask_t, ~, ~] = segment_DNAPL(rgb_corr_t, flow_domain, config_locked);
            end
            masks_arr{t} = mask_t;

            sat_t = calculate_saturation(mask_t, flow_domain, px);
            sn_arr(t) = sat_t.Sn;
            blob_t = analyze_blob_geometry(mask_t, px);
            nblobs_arr(t) = blob_t.num_blobs;
            mbs_arr(t) = blob_t.size_distribution.mean;
            iface_t = analyze_interfaces(mask_t, flow_domain, px, config_locked);
            iface_arr(t) = iface_t.dnapl_water_length_px;
        end
    end

    %% Pack results
    sol.saturation_vs_time     = sn_arr;
    sol.num_blobs_vs_time      = nblobs_arr;
    sol.mean_blob_size_vs_time = mbs_arr;
    sol.interface_area_vs_time = iface_arr;
    sol.masks                  = masks_arr;

    %% Dissolution rate: dSn/dt
    dt = diff(time_vector(:));
    dt(dt == 0) = 1;
    sol.dissolution_rate = diff(sol.saturation_vs_time) ./ dt;

    %% Change detection (sequential — needs consecutive frames)
    sol.change = struct('dissolved_px', [], 'appeared_px', [], 'net_px', []);
    for t = 2:num_frames
        dissolved  = sol.masks{t-1} &  ~sol.masks{t};
        appeared   = ~sol.masks{t-1} &  sol.masks{t};
        sol.change(t-1).dissolved_px = sum(dissolved(:));
        sol.change(t-1).appeared_px  = sum(appeared(:));
        sol.change(t-1).net_px       = sol.change(t-1).appeared_px - sol.change(t-1).dissolved_px;
    end

    %% Mass dissolved
    depth = config.physical.depth;
    rho   = config.physical.dnapl_density;
    pore_vol = sum(flow_domain(:)) * px^2 * depth;
    sol.mass_dissolved = (sol.saturation_vs_time(1) - sol.saturation_vs_time(end)) ...
                         * pore_vol * rho;

    fprintf('\n  Solubilization complete. Sn: %.3f -> %.3f (%.1f%% removed)\n', ...
        sol.saturation_vs_time(1), sol.saturation_vs_time(end), ...
        100 * (1 - sol.saturation_vs_time(end) / max(sol.saturation_vs_time(1), eps)));
end
