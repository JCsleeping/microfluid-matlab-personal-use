function fres = run_fingering_analysis(results, config, fconfig)
% RUN_FINGERING_ANALYSIS  Physics-enhanced fingering analysis (v2.0).
%
%   fres = run_fingering_analysis(results, config)
%   fres = run_fingering_analysis(results, config, fconfig)
%
%   Supports on-demand frame selection:
%     fconfig.frame_idx = N      → loads frame N, re-segments DNAPL (single)
%     fconfig.frame_idx = [N,M,...]  → batch analysis across listed frames
%     fconfig.frame_idx = 'all'  → continuous scan of all TIF pages
%     fconfig.frame_idx = []     → uses results.dnapl_mask as-is (default)
%     fconfig.stride = S         → analyze every S-th frame (continuous mode)
%
%   Dual-line analysis with three-phase decoupling:
%     Line A: Residual NAPL (Sr on pore_space, topology-corrected Euler)
%     Line B: Invading water (hydraulic-resistance backbone, Euclidean tau)
%
%   Usage:
%     % Option 1: Analyze the saved results directly
%     results = main_DNAPL_pipeline(config);
%     fres = run_fingering_analysis(results, config);
%
%     % Option 2: Analyze a specific frame (e.g., frame 500)
%     fconfig.frame_idx = 500;
%     fres = run_fingering_analysis(results, config, fconfig);
%
%     % Option 3: Continuous TIF analysis
%     fconfig.frame_idx = 'all';
%     fconfig.stride = 5;  % every 5th frame
%     fts = run_fingering_analysis(results, config, fconfig);

    fprintf('\n##########################################################\n');
    fprintf('   Fingering Analysis Module v2.0 (Physics-Enhanced)\n');
    fprintf('##########################################################\n\n');

    timer = tic;

    if nargin < 3 || isempty(fconfig), fconfig = struct(); end
    fconfig = set_defaults(fconfig);

    %% On-demand frame loading + re-segmentation
    if isfield(fconfig, 'frame_idx') && ~isempty(fconfig.frame_idx)
        if ischar(fconfig.frame_idx) || numel(fconfig.frame_idx) > 1
            % Continuous / batch mode: route to time-series analysis
            if ischar(fconfig.frame_idx)
                fprintf('  frame_idx = ''%s'' → continuous TIF analysis\n', fconfig.frame_idx);
            else
                fprintf('  frame_idx is a vector (%d frames) → batch mode\n', ...
                    numel(fconfig.frame_idx));
            end
            fres = run_fingering_timeseries(results, config, fconfig);
            return;
        end
        results = load_and_segment_frame(results, config, fconfig.frame_idx);
    end

    %% ================================================================
    %  Phase 0: Three-Phase Decoupling
    %  ================================================================
    fprintf('Phase 0: Three-Phase Decoupling\n');
    fprintf('------------------------------------------------------\n');
    qc = phase0_precheck(results, config, fconfig);
    fres.qc = qc;

    %% ================================================================
    %  Phase 1: Residual NAPL Line (Line A)
    %  ================================================================
    fprintf('\nPhase 1: Residual NAPL Analysis\n');
    fprintf('------------------------------------------------------\n');

    % 1.1 Clean mask
    dnapl_clean = clean_mask(qc.dnapl_mask, qc.pore_space, ...
        struct('min_area', 20, 'fill_holes', true, 'max_hole_area', 200));
    fres.napl.dnapl_mask_clean = dnapl_clean;

    % 1.2 Residual metrics (topology-corrected)
    fres.napl.residual = compute_residual_metrics(dnapl_clean, qc.pore_space, qc.solid_mask);

    % 1.3 Skeleton (pore-scale-anchored pruning)
    fres.napl.skeleton = extract_skeleton_pruned(dnapl_clean, qc.pore_scale);

    % 1.4 Local width (solid-wall-bounded)
    best = fres.napl.skeleton.best_idx;
    fres.napl.local_width = compute_local_width(dnapl_clean, ...
        fres.napl.skeleton.pruned(best).skeleton, qc.solid_mask, qc.pixel_size);

    %% ================================================================
    %  Phase 2: Invading Water Line (Line B)
    %  ================================================================
    fprintf('\nPhase 2: Invading Water Analysis\n');
    fprintf('------------------------------------------------------\n');

    % 2.1 Inlet-connected water
    water_clean = clean_mask(qc.water_mask, qc.pore_space, ...
        struct('min_area', 20, 'fill_holes', false));
    water_connected = extract_inlet_connected(water_clean, qc.pore_space, fconfig.inlet_side);
    fres.water.water_connected = water_connected;

    if sum(water_connected(:)) == 0
        fprintf('  WARNING: No inlet-connected water. Skipping Phase 2 details.\n');
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
        % 2.2 Skeleton
        fres.water.skeleton = extract_skeleton_pruned(water_connected, qc.pore_scale);
        best_w = fres.water.skeleton.best_idx;
        water_skel = fres.water.skeleton.pruned(best_w).skeleton;
        water_skel_len = fres.water.skeleton.pruned(best_w).skel_length;

        % 2.3 Graph (with junction merging, cyclic-safe)
        fres.water.graph = skeleton_to_graph(water_skel);

        % 2.4 Edge widths for hydraulic resistance
        edge_widths = compute_edge_widths(water_skel, water_connected, ...
            qc.solid_mask, fres.water.graph);

        % 2.5 Backbone (min hydraulic resistance via Dijkstra)
        fres.water.backbone = extract_backbone(water_skel, ...
            fres.water.graph, fconfig.inlet_side, edge_widths);

        % 2.6 Terminal branches (pore-scale-anchored)
        fres.water.fingers = extract_terminal_branches(water_skel, ...
            fres.water.graph, fres.water.backbone.backbone_mask, ...
            fconfig, qc.pore_scale);

        % 2.7 Tortuosity (Euclidean denominator)
        fres.water.tortuosity = compute_tortuosity(fres.water.backbone, ...
            fres.water.fingers, fres.water.graph);

        % 2.8 Branch density
        fres.water.branch_density = compute_branch_density(fres.water.graph, water_skel_len);
    end

    %% ================================================================
    %  Phase 3: Front Tracking
    %  ================================================================
    fprintf('\nPhase 3: Front Tracking\n');
    fprintf('------------------------------------------------------\n');
    fres.front = track_leading_front(water_connected, fconfig.inlet_side, qc.pore_space);
    fprintf('  x_lead = %d px, front_width = %d px, W_norm = %.3f\n', ...
        fres.front.x_lead, fres.front.front_width, fres.front.front_width_norm);
    fprintf('  A_invaded = %d px (%.4f of pore space)\n', ...
        fres.front.A_invaded, fres.front.A_invaded_norm);

    %% Visualization (all overlays with solid boundaries)
    fprintf('\nVisualization\n');
    fprintf('------------------------------------------------------\n');
    visualize_fingering(qc.ref_image, fres, config);

    %% Export
    if isfield(config, 'output_path') && isfolder(config.output_path)
        export_fingering_summary(fres, config.output_path);
    end

    elapsed = toc(timer);
    fprintf('\n##########################################################\n');
    fprintf('  Fingering analysis v2.0 completed in %.1f seconds\n', elapsed);
    fprintf('##########################################################\n');
end


function fconfig = set_defaults(fconfig)
    if ~isfield(fconfig, 'flow_direction'),  fconfig.flow_direction = 'left_to_right'; end
    if ~isfield(fconfig, 'inlet_side'),      fconfig.inlet_side = 'left'; end
    if ~isfield(fconfig, 'min_finger_pore_factor'),   fconfig.min_finger_pore_factor = 2.0; end
    if ~isfield(fconfig, 'min_finger_advance_factor'), fconfig.min_finger_advance_factor = 1.5; end
end


function ew = compute_edge_widths(skeleton, mask, solid_mask, G)
% COMPUTE_EDGE_WIDTHS  Mean local width along each graph edge.
%   Used to assign hydraulic resistance weights to backbone extraction.
    D = bwdist(~mask | solid_mask);
    [H, W] = size(skeleton);

    % Remove node pixels
    edge_skel = skeleton & ~(G.node_image > 0);
    edge_cc = bwconncomp(edge_skel, 8);

    n_edges = size(G.edges, 1);
    edge_widths = ones(n_edges, 1);  % default width = 1

    for k = 1:edge_cc.NumObjects
        seg_mask = false(H, W);
        seg_mask(edge_cc.PixelIdxList{k}) = true;
        seg_dil = imdilate(seg_mask, ones(3));

        touching = unique(G.node_image(seg_dil & (G.node_image > 0)));
        touching = touching(touching > 0);

        if numel(touching) >= 2
            % Find corresponding edge
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


function export_fingering_summary(fres, output_path)
    qc_dir = fullfile(output_path, 'fingering_qc');
    if ~isfolder(qc_dir), mkdir(qc_dir); end

    save(fullfile(qc_dir, 'fingering_results.mat'), 'fres');

    fid = fopen(fullfile(qc_dir, 'fingering_summary.csv'), 'w');
    fprintf(fid, 'Metric,Value,Unit,Note\n');

    if isfield(fres, 'napl') && isfield(fres.napl, 'residual')
        r = fres.napl.residual;
        fprintf(fid, 'Sr,%.6f,fraction,denom=pore_space\n', r.Sr);
        fprintf(fid, 'Nc,%d,count,\n', r.Nc);
        fprintf(fid, 'beta_0,%d,count,\n', r.beta_0);
        fprintf(fid, 'beta_1_physical,%d,count,topology_corrected\n', r.beta_1);
        fprintf(fid, 'beta_1_pseudo,%d,count,pillar_wrapping\n', r.beta_1_pseudo);
        fprintf(fid, 'EulerNumber,%d,count,corrected\n', r.EulerNumber);
        fprintf(fid, 'largest_comp_frac,%.4f,fraction,\n', r.largest_component_fraction);
    end

    if isfield(fres, 'napl') && isfield(fres.napl, 'local_width')
        w = fres.napl.local_width;
        fprintf(fid, 'napl_width_mean,%.2f,px,solid_bounded\n', w.mean_width_px);
        fprintf(fid, 'napl_width_median,%.2f,px,solid_bounded\n', w.median_width_px);
        fprintf(fid, 'napl_width_p90,%.2f,px,\n', w.width_p90_px);
        fprintf(fid, 'napl_width_cv,%.4f,ratio,\n', w.width_cv);
    end

    if isfield(fres, 'water')
        if isfield(fres.water, 'backbone')
            fprintf(fid, 'L_backbone,%.2f,px,min_resistance_dijkstra\n', fres.water.backbone.L_backbone);
        end
        if isfield(fres.water, 'fingers')
            fprintf(fid, 'num_fingers,%d,count,pore_scale_anchored\n', fres.water.fingers.num_fingers);
        end
        if isfield(fres.water, 'tortuosity')
            fprintf(fid, 'tau_backbone,%.4f,ratio,euclidean_denom\n', fres.water.tortuosity.tau_backbone);
        end
        if isfield(fres.water, 'branch_density')
            fprintf(fid, 'branch_density,%.6f,per_px,merged_junctions\n', fres.water.branch_density.branch_density);
        end
    end

    if isfield(fres, 'front')
        fprintf(fid, 'x_lead,%d,px,\n', fres.front.x_lead);
        fprintf(fid, 'front_width,%d,px,\n', fres.front.front_width);
        fprintf(fid, 'front_width_norm,%.4f,ratio,\n', fres.front.front_width_norm);
        fprintf(fid, 'A_invaded,%d,px,\n', fres.front.A_invaded);
        fprintf(fid, 'A_invaded_norm,%.6f,fraction,\n', fres.front.A_invaded_norm);
    end

    fclose(fid);
    fprintf('  Results saved to: %s\n', qc_dir);
end


function results = load_and_segment_frame(results, config, frame_idx)
% LOAD_AND_SEGMENT_FRAME  Load a specific frame from TIF, preprocess, and segment.
%
%   results = load_and_segment_frame(results, config, frame_idx)
%
%   Rebuilds the frame_index from config.multipage_tif_path, loads the
%   requested frame, applies the same preprocessing (rotate_and_crop +
%   correct_illumination) as the main pipeline, then runs DNAPL
%   segmentation. Updates results.dnapl_mask and results.ref_image.

    fprintf('  [Frame Loader] Loading frame %d...\n', frame_idx);

    %% 1. Build frame_index from TIF paths
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

    % Validate frame_idx
    if frame_idx < 1 || frame_idx > numel(frame_index)
        error('load_and_segment_frame:badIdx', ...
            'frame_idx = %d is out of range [1, %d].', ...
            frame_idx, numel(frame_index));
    end

    %% 2. Load frame
    rgb = load_frame(frame_idx, frame_index, config);
    fprintf('  [Frame Loader] Loaded: %s (page %d), size [%d x %d]\n', ...
        frame_index(frame_idx).tif_path, frame_index(frame_idx).page, ...
        size(rgb, 1), size(rgb, 2));

    %% 3. Preprocessing: rotate & crop (using saved parameters)
    [rgb_rot, ~, ~] = rotate_and_crop(rgb, config);

    %% 4. Illumination correction
    [rgb_corr, ~] = correct_illumination(rgb_rot, ...
        config.illumination.method, config.illumination, config.parallel.use_gpu);

    % Resize to match flow_domain if needed
    [H_fd, W_fd] = size(results.flow_domain);
    if size(rgb_corr, 1) ~= H_fd || size(rgb_corr, 2) ~= W_fd
        rgb_corr = imresize(rgb_corr, [H_fd, W_fd]);
    end

    %% 5. Segment DNAPL
    fprintf('  [Frame Loader] Segmenting DNAPL (method: %s)...\n', ...
        config.segmentation.method);
    if endsWith(config.segmentation.method, '_v2')
        [dnapl_mask, ~, ~] = segment_DNAPL_v2(rgb_corr, results.flow_domain, config);
    else
        [dnapl_mask, ~, ~] = segment_DNAPL(rgb_corr, results.flow_domain, config);
    end

    %% 6. Update results
    results.dnapl_mask = dnapl_mask;
    results.ref_image  = rgb_corr;

    Sn = sum(dnapl_mask(:)) / max(sum(results.flow_domain(:)), 1);
    fprintf('  [Frame Loader] Frame %d ready: Sn = %.4f (%d DNAPL pixels)\n', ...
        frame_idx, Sn, sum(dnapl_mask(:)));
end
