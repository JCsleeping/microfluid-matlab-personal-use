function fts = run_fingering_timeseries(results, config, fconfig)
% RUN_FINGERING_TIMESERIES  Continuous fingering analysis across all TIF frames.
%
%   fts = run_fingering_timeseries(results, config, fconfig)
%
%   Scans all pages in the multi-page TIF file(s), loading each frame
%   on-demand, segmenting DNAPL, and running full fingering analysis.
%   Collects key metrics into time-series arrays for statistical analysis.
%
%   Inputs:
%       results - Output struct from main_DNAPL_pipeline (provides
%                 flow_domain, solid_mask, preprocessing params)
%       config  - Pipeline configuration struct (must have multipage_tif_path)
%       fconfig - Fingering config struct:
%                   .frame_idx  - Vector of frame indices, OR:
%                                 'all' / [] → analyze ALL frames
%                   .stride     - (optional) Analyze every N-th frame (default: 1)
%                   .inlet_side, .flow_direction, etc.
%
%   Output:
%       fts - Struct with time-series results:
%           .frame_indices             - 1×K frame numbers analyzed
%           .time_vector               - 1×K time stamps [s]
%           .Sr_vs_frame               - 1×K residual NAPL saturation
%           .Nc_vs_frame               - 1×K connected NAPL components
%           .euler_vs_frame            - 1×K Euler number (topology)
%           .napl_width_mean_vs_frame  - 1×K mean NAPL width [px]
%           .napl_width_median_vs_frame- 1×K median NAPL width [px]
%           .num_fingers_vs_frame      - 1×K water finger count
%           .tau_backbone_vs_frame     - 1×K backbone tortuosity
%           .L_backbone_vs_frame       - 1×K backbone length [px]
%           .branch_density_vs_frame   - 1×K branch density [per px]
%           .x_lead_vs_frame           - 1×K leading front position [px]
%           .front_width_norm_vs_frame - 1×K normalized front width
%           .A_invaded_norm_vs_frame   - 1×K normalized invaded area
%           .per_frame                 - 1×K cell array of full fres structs
%           .stats                     - Summary statistics struct
%
%   Usage:
%     % Analyze every frame
%     fconfig.frame_idx = 'all';
%     fts = run_fingering_timeseries(results, config, fconfig);
%
%     % Analyze every 5th frame
%     fconfig.frame_idx = 'all';
%     fconfig.stride = 5;
%     fts = run_fingering_timeseries(results, config, fconfig);
%
%     % Analyze specific frames
%     fconfig.frame_idx = [1, 50, 100, 200, 300, 500];
%     fts = run_fingering_timeseries(results, config, fconfig);
%
%   See also: run_fingering_analysis, run_fingering_pipeline

    fprintf('\n##########################################################\n');
    fprintf('   Fingering Continuous Time-Series Analysis\n');
    fprintf('##########################################################\n\n');

    timer = tic;

    %% 1. Build frame_index from TIF paths (once)
    tif_paths = config.multipage_tif_path;
    if ischar(tif_paths), tif_paths = {tif_paths}; end

    frame_index = struct('tif_path', {}, 'page', {});
    idx = 0;
    for f = 1:numel(tif_paths)
        info_f = imfinfo(tif_paths{f});
        n_pages = numel(info_f);
        for p = 1:n_pages
            idx = idx + 1;
            frame_index(idx).tif_path = tif_paths{f};
            frame_index(idx).page = p;
        end
    end
    total_frames = numel(frame_index);
    fprintf('  TIF stack: %d files, %d total frames\n', numel(tif_paths), total_frames);

    %% 2. Determine which frames to analyze
    stride = 1;
    if isfield(fconfig, 'stride') && ~isempty(fconfig.stride)
        stride = max(1, round(fconfig.stride));
    end

    if ~isfield(fconfig, 'frame_idx') || isempty(fconfig.frame_idx) || ...
            (ischar(fconfig.frame_idx) && strcmpi(fconfig.frame_idx, 'all'))
        % All frames (with stride)
        frame_indices = 1:stride:total_frames;
        fprintf('  Mode: ALL frames, stride = %d\n', stride);
    else
        frame_indices = fconfig.frame_idx(:)';
        % Apply stride to explicit list too
        if stride > 1
            frame_indices = frame_indices(1:stride:end);
        end
        fprintf('  Mode: EXPLICIT list, %d frames\n', numel(frame_indices));
    end

    % Validate
    bad = frame_indices < 1 | frame_indices > total_frames;
    if any(bad)
        error('run_fingering_timeseries:badIdx', ...
            'Frame indices out of range [1, %d]: %s', ...
            total_frames, num2str(frame_indices(bad)));
    end

    K = numel(frame_indices);
    fprintf('  Frames to analyze: %d\n', K);
    if K <= 20
        fprintf('  Indices: [%s]\n', num2str(frame_indices));
    else
        fprintf('  Range: %d → %d (stride %d)\n', ...
            frame_indices(1), frame_indices(end), stride);
    end

    %% 3. Build time vector
    if isfield(config, 'time_interval') && ~isempty(config.time_interval)
        dt = config.time_interval;
        time_vec = (frame_indices - 1) * dt;
        fprintf('  Time interval: %.2f s/frame\n', dt);
    elseif isfield(config, 'time_vector') && ~isempty(config.time_vector) && ...
            numel(config.time_vector) >= max(frame_indices)
        time_vec = config.time_vector(frame_indices);
    else
        time_vec = frame_indices - 1;  % frame-based
    end
    fprintf('\n');

    %% 4. Preallocate
    Sr_arr       = NaN(1, K);
    Nc_arr       = NaN(1, K);
    euler_arr    = NaN(1, K);
    width_m_arr  = NaN(1, K);
    width_md_arr = NaN(1, K);
    fingers_arr  = NaN(1, K);
    tau_arr      = NaN(1, K);
    Lbb_arr      = NaN(1, K);
    bd_arr       = NaN(1, K);
    xlead_arr    = NaN(1, K);
    fw_arr       = NaN(1, K);
    Ainv_arr     = NaN(1, K);
    per_frame    = cell(1, K);

    %% 5. Prepare single-frame fconfig (no recursion)
    fconfig_single = fconfig;
    fconfig_single.frame_idx = [];
    fconfig_single.batch_mode = true;  % suppress per-frame QC figures
    if isfield(fconfig_single, 'stride'), fconfig_single = rmfield(fconfig_single, 'stride'); end

    %% 6. Frame loop
    failed_frames = [];
    for k = 1:K
        fidx = frame_indices(k);
        fprintf('--- [%d/%d] Frame %d ', k, K, fidx);
        if K > 5
            eta_s = toc(timer) / max(k-1,1) * (K - k);
            fprintf('(ETA: %.0f s) ', eta_s);
        end
        fprintf('---\n');

        frame_timer = tic;

        try
            % Load, preprocess, segment
            results_k = load_and_segment_frame_internal(results, config, fidx, frame_index);

            % Run single-frame analysis
            fres_k = run_single_frame_analysis(results_k, config, fconfig_single);

            % Extract metrics
            if isfield(fres_k, 'napl') && isfield(fres_k.napl, 'residual')
                Sr_arr(k)    = fres_k.napl.residual.Sr;
                Nc_arr(k)    = fres_k.napl.residual.Nc;
                euler_arr(k) = fres_k.napl.residual.EulerNumber;
            end
            if isfield(fres_k, 'napl') && isfield(fres_k.napl, 'local_width')
                width_m_arr(k)  = fres_k.napl.local_width.mean_width_px;
                width_md_arr(k) = fres_k.napl.local_width.median_width_px;
            end
            if isfield(fres_k, 'water')
                if isfield(fres_k.water, 'fingers')
                    fingers_arr(k) = fres_k.water.fingers.num_fingers;
                end
                if isfield(fres_k.water, 'tortuosity')
                    tau_arr(k) = fres_k.water.tortuosity.tau_backbone;
                end
                if isfield(fres_k.water, 'backbone')
                    Lbb_arr(k) = fres_k.water.backbone.L_backbone;
                end
                if isfield(fres_k.water, 'branch_density')
                    bd_arr(k) = fres_k.water.branch_density.branch_density;
                end
            end
            if isfield(fres_k, 'front')
                xlead_arr(k) = fres_k.front.x_lead;
                fw_arr(k)    = fres_k.front.front_width_norm;
                Ainv_arr(k)  = fres_k.front.A_invaded_norm;
            end

            per_frame{k} = fres_k;

        catch ME
            fprintf('  *** ERROR on frame %d: %s\n', fidx, ME.message);
            if numel(failed_frames) < 3
                % Print full stack trace for first 3 failures
                for si = 1:numel(ME.stack)
                    fprintf('      at %s (line %d)\n', ME.stack(si).name, ME.stack(si).line);
                end
            end
            failed_frames(end+1) = fidx; %#ok<AGROW>
        end

        fprintf('  Done in %.1f s\n', toc(frame_timer));
    end

    %% 7. Pack results
    fts.frame_indices              = frame_indices;
    fts.time_vector                = time_vec;
    fts.total_frames_in_tif        = total_frames;
    fts.stride                     = stride;
    fts.Sr_vs_frame                = Sr_arr;
    fts.Nc_vs_frame                = Nc_arr;
    fts.euler_vs_frame             = euler_arr;
    fts.napl_width_mean_vs_frame   = width_m_arr;
    fts.napl_width_median_vs_frame = width_md_arr;
    fts.num_fingers_vs_frame       = fingers_arr;
    fts.tau_backbone_vs_frame      = tau_arr;
    fts.L_backbone_vs_frame        = Lbb_arr;
    fts.branch_density_vs_frame    = bd_arr;
    fts.x_lead_vs_frame            = xlead_arr;
    fts.front_width_norm_vs_frame  = fw_arr;
    fts.A_invaded_norm_vs_frame    = Ainv_arr;
    fts.per_frame                  = per_frame;
    fts.failed_frames              = failed_frames;

    %% 8. Compute summary statistics
    fts.stats = compute_summary_stats(fts);

    %% 9. Visualization
    visualize_fingering_timeseries(fts, config);

    %% 10. Export
    if isfield(config, 'output_path') && isfolder(config.output_path)
        qc_dir = fullfile(config.output_path, 'fingering_qc');
        if ~isfolder(qc_dir), mkdir(qc_dir); end

        export_fingering_timeseries_csv(fts, config.output_path);
        save(fullfile(qc_dir, 'fingering_timeseries.mat'), 'fts', '-v7.3');
        fprintf('  Results saved to: %s\n', qc_dir);
    end

    elapsed = toc(timer);
    fprintf('\n##########################################################\n');
    fprintf('  Continuous analysis: %d frames in %.1f s (%.2f s/frame)\n', ...
        K, elapsed, elapsed/K);
    if ~isempty(failed_frames)
        fprintf('  WARNING: %d frames failed: [%s]\n', ...
            numel(failed_frames), num2str(failed_frames));
    end
    fprintf('##########################################################\n');
end


%% ========================================================================
%  Summary statistics
%  ========================================================================
function stats = compute_summary_stats(fts)
    v = ~isnan(fts.Sr_vs_frame);  % valid mask

    stats.n_analyzed = sum(v);
    stats.n_failed   = numel(fts.failed_frames);

    % Sr
    stats.Sr.start  = fts.Sr_vs_frame(find(v, 1, 'first'));
    stats.Sr.final  = fts.Sr_vs_frame(find(v, 1, 'last'));
    stats.Sr.min    = min(fts.Sr_vs_frame(v));
    stats.Sr.max    = max(fts.Sr_vs_frame(v));
    stats.Sr.mean   = mean(fts.Sr_vs_frame(v));
    stats.Sr.std    = std(fts.Sr_vs_frame(v));

    % Fingers
    vf = ~isnan(fts.num_fingers_vs_frame);
    if any(vf)
        stats.fingers.min  = min(fts.num_fingers_vs_frame(vf));
        stats.fingers.max  = max(fts.num_fingers_vs_frame(vf));
        stats.fingers.mean = mean(fts.num_fingers_vs_frame(vf));
        stats.fingers.std  = std(fts.num_fingers_vs_frame(vf));
    end

    % Tortuosity
    vt = ~isnan(fts.tau_backbone_vs_frame);
    if any(vt)
        stats.tau.min  = min(fts.tau_backbone_vs_frame(vt));
        stats.tau.max  = max(fts.tau_backbone_vs_frame(vt));
        stats.tau.mean = mean(fts.tau_backbone_vs_frame(vt));
        stats.tau.std  = std(fts.tau_backbone_vs_frame(vt));
    end

    % Front advance
    vx = ~isnan(fts.x_lead_vs_frame);
    if any(vx)
        stats.front.x_start = fts.x_lead_vs_frame(find(vx, 1, 'first'));
        stats.front.x_final = fts.x_lead_vs_frame(find(vx, 1, 'last'));
        stats.front.advance = stats.front.x_final - stats.front.x_start;
    end

    % Dissolution rate dSr/dt
    if sum(v) >= 2
        valid_idx = find(v);
        dSr = diff(fts.Sr_vs_frame(valid_idx));
        dt  = diff(fts.time_vector(valid_idx));
        dt(dt == 0) = 1;
        stats.dissolution_rate = dSr ./ dt;
        stats.dissolution_rate_mean = mean(stats.dissolution_rate);
    end
end


%% ========================================================================
%  Internal: load + preprocess + segment
%  ========================================================================
function results_k = load_and_segment_frame_internal(results, config, fidx, frame_index)
    rgb = load_frame(fidx, frame_index);

    [rgb_rot, ~, ~] = rotate_and_crop(rgb, config);
    [rgb_corr, ~]   = correct_illumination(rgb_rot, ...
        config.illumination.method, config.illumination);

    [H_fd, W_fd] = size(results.flow_domain);
    if size(rgb_corr, 1) ~= H_fd || size(rgb_corr, 2) ~= W_fd
        rgb_corr = imresize(rgb_corr, [H_fd, W_fd]);
    end

    if endsWith(config.segmentation.method, '_v2')
        [dnapl_mask, ~, ~] = segment_DNAPL_v2(rgb_corr, results.flow_domain, config);
    else
        [dnapl_mask, ~, ~] = segment_DNAPL(rgb_corr, results.flow_domain, config);
    end

    results_k = results;
    results_k.dnapl_mask = dnapl_mask;
    results_k.ref_image  = rgb_corr;
end


%% ========================================================================
%  Internal: run single-frame analysis
%  ========================================================================
function fres = run_single_frame_analysis(results, config, fconfig)
    if nargin < 3 || isempty(fconfig), fconfig = struct(); end
    fconfig = set_defaults_internal(fconfig);

    %% Phase 0
    qc = phase0_precheck(results, config, fconfig);
    fres.qc = qc;

    %% Phase 1: Residual NAPL
    dnapl_clean = clean_mask(qc.dnapl_mask, qc.pore_space, ...
        struct('min_area', 20, 'fill_holes', true, 'max_hole_area', 200));
    fres.napl.dnapl_mask_clean = dnapl_clean;
    fres.napl.residual = compute_residual_metrics(dnapl_clean, qc.pore_space, qc.solid_mask);
    fres.napl.skeleton = extract_skeleton_pruned(dnapl_clean, qc.pore_scale);

    best = fres.napl.skeleton.best_idx;
    fres.napl.local_width = compute_local_width(dnapl_clean, ...
        fres.napl.skeleton.pruned(best).skeleton, qc.solid_mask, qc.pixel_size);

    %% Phase 2: Invading Water
    water_clean = clean_mask(qc.water_mask, qc.pore_space, ...
        struct('min_area', 20, 'fill_holes', false));
    water_connected = extract_inlet_connected(water_clean, qc.pore_space, fconfig.inlet_side);
    fres.water.water_connected = water_connected;

    if sum(water_connected(:)) == 0
        fres.water.skeleton = struct();
        fres.water.graph = struct('num_nodes', 0, 'nodes', struct([]), ...
            'num_junctions', 0, 'num_endpoints', 0, 'edges', [], 'edge_lengths', []);
        fres.water.backbone = struct('backbone_mask', false(size(qc.pore_space)), ...
            'L_backbone', 0, 'inlet_node', 0, 'tip_node', 0);
        fres.water.fingers = struct('num_fingers', 0, 'fingers', [], ...
            'finger_mask', false(size(qc.pore_space)));
        fres.water.tortuosity = struct('tau_backbone', NaN);
        fres.water.branch_density = struct('num_junctions', 0, 'branch_density', 0);
    else
        fres.water.skeleton = extract_skeleton_pruned(water_connected, qc.pore_scale);
        best_w = fres.water.skeleton.best_idx;
        water_skel = fres.water.skeleton.pruned(best_w).skeleton;
        water_skel_len = fres.water.skeleton.pruned(best_w).skel_length;

        fres.water.graph = skeleton_to_graph(water_skel);

        edge_widths = compute_edge_widths_internal(water_skel, water_connected, ...
            qc.solid_mask, fres.water.graph);

        fres.water.backbone = extract_backbone(water_skel, ...
            fres.water.graph, fconfig.inlet_side, edge_widths);

        fres.water.fingers = extract_terminal_branches(water_skel, ...
            fres.water.graph, fres.water.backbone.backbone_mask, ...
            fconfig, qc.pore_scale);

        fres.water.tortuosity = compute_tortuosity(fres.water.backbone, ...
            fres.water.fingers, fres.water.graph);

        fres.water.branch_density = compute_branch_density(fres.water.graph, water_skel_len);
    end

    %% Phase 3: Front Tracking
    fres.front = track_leading_front(water_connected, fconfig.inlet_side, qc.pore_space);
end


%% ========================================================================
%  Internal helpers
%  ========================================================================
function fconfig = set_defaults_internal(fconfig)
    if ~isfield(fconfig, 'flow_direction'),  fconfig.flow_direction = 'left_to_right'; end
    if ~isfield(fconfig, 'inlet_side'),      fconfig.inlet_side = 'left'; end
    if ~isfield(fconfig, 'min_finger_pore_factor'),   fconfig.min_finger_pore_factor = 2.0; end
    if ~isfield(fconfig, 'min_finger_advance_factor'), fconfig.min_finger_advance_factor = 1.5; end
end


function ew = compute_edge_widths_internal(skeleton, mask, solid_mask, G)
    D = bwdist(~mask | solid_mask);
    [H, W] = size(skeleton);
    edge_skel = skeleton & ~(G.node_image > 0);
    edge_cc = bwconncomp(edge_skel, 8);
    n_edges = size(G.edges, 1);
    edge_widths = ones(n_edges, 1);
    for k = 1:edge_cc.NumObjects
        seg_mask = false(H, W);
        seg_mask(edge_cc.PixelIdxList{k}) = true;
        seg_dil = imdilate(seg_mask, ones(3));
        touching = unique(G.node_image(seg_dil & (G.node_image > 0)));
        touching = touching(touching > 0);
        if numel(touching) >= 2
            for e = 1:n_edges
                if (G.edges(e,1)==touching(1) && G.edges(e,2)==touching(2)) || ...
                   (G.edges(e,1)==touching(2) && G.edges(e,2)==touching(1))
                    radii = D(edge_cc.PixelIdxList{k});
                    edge_widths(e) = 2 * mean(radii(radii > 0));
                    break;
                end
            end
        end
    end
    ew.edge_widths = edge_widths;
end


function export_fingering_timeseries_csv(fts, output_path)
    qc_dir = fullfile(output_path, 'fingering_qc');
    if ~isfolder(qc_dir), mkdir(qc_dir); end

    csv_path = fullfile(qc_dir, 'fingering_timeseries.csv');
    fid = fopen(csv_path, 'w');
    fprintf(fid, 'frame_idx,time_s,Sr,Nc,EulerNumber,');
    fprintf(fid, 'napl_width_mean_px,napl_width_median_px,');
    fprintf(fid, 'num_fingers,tau_backbone,L_backbone_px,branch_density,');
    fprintf(fid, 'x_lead_px,front_width_norm,A_invaded_norm\n');

    for k = 1:numel(fts.frame_indices)
        fprintf(fid, '%d,%.2f,%.6f,%d,%d,%.2f,%.2f,%d,%.4f,%.2f,%.6f,%d,%.4f,%.6f\n', ...
            fts.frame_indices(k), ...
            fts.time_vector(k), ...
            fts.Sr_vs_frame(k), ...
            fts.Nc_vs_frame(k), ...
            fts.euler_vs_frame(k), ...
            fts.napl_width_mean_vs_frame(k), ...
            fts.napl_width_median_vs_frame(k), ...
            fts.num_fingers_vs_frame(k), ...
            fts.tau_backbone_vs_frame(k), ...
            fts.L_backbone_vs_frame(k), ...
            fts.branch_density_vs_frame(k), ...
            fts.x_lead_vs_frame(k), ...
            fts.front_width_norm_vs_frame(k), ...
            fts.A_invaded_norm_vs_frame(k));
    end

    fclose(fid);
    fprintf('  CSV saved: %s\n', csv_path);
end
