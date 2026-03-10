function [dnapl_mask, confidence_map, seg_info] = segment_DNAPL_v2(ref_image, flow_domain, config)
% SEGMENT_DNAPL_V2  Multi-pass DNAPL segmentation with morphological hole recovery.
%
%   [dnapl_mask, confidence_map, seg_info] = segment_DNAPL_v2(ref_image, flow_domain, config)
%
%   Two-pass segmentation to recover dark spots inside DNAPL:
%     Pass 1 (Color):  a* channel GMM/Otsu → mask_red  (delegates to segment_DNAPL v1)
%     Pass 2 (Shape):  Morphological reconstruction — fills small background
%                      fragments enclosed by mask_red within the pore space.
%                      Uses erosion + geodesic reconstruction: no color thresholds.
%     Final:           mask_red | recovered_holes + imfill + refine_mask
%
%   Config parameter:
%     config.segmentation.hole_fill_radius — erosion radius for background
%         reconstruction (default: 3). Background fragments narrower than
%         2*r pixels are treated as internal holes and filled. This should
%         approximate the maximum dark-spot diameter in pixels.
%
%   Inputs / Outputs: same as segment_DNAPL (drop-in replacement)

    %% Read config with defaults
    if isfield(config.segmentation, 'hole_fill_radius')
        fill_r = config.segmentation.hole_fill_radius;
    else
        fill_r = 3;
    end
    min_area     = config.segmentation.min_blob_area;
    morph_radius = config.segmentation.morph_radius;

    %% ================================================================
    %  Pass 1: Color-based segmentation (delegate to existing v1)
    %  ================================================================
    config_v1 = config;
    base_method = regexprep(config.segmentation.method, '_v2$', '');
    if isempty(base_method), base_method = 'gmm'; end
    config_v1.segmentation.method = base_method;

    [mask_red, confidence_map, seg_info] = segment_DNAPL(ref_image, flow_domain, config_v1);

    red_px = sum(mask_red(:));
    fprintf('    Pass 1 (color): %d pixels\n', red_px);

    %% ================================================================
    %  Pass 2: Morphological reconstruction — fill internal holes
    %  ================================================================
    %  Principle: erode the background (non-DNAPL within pore space).
    %  Small background fragments (dark spots creating holes) are destroyed
    %  by erosion. Geodesic reconstruction recovers only the surviving
    %  background (real water channels). The difference = internal holes.

    bg = flow_domain & ~mask_red;               % background in pore space
    se = strel('disk', fill_r);

    % GPU config (defensive: default false if field missing)
    use_gpu = isfield(config, 'parallel') && ...
              isfield(config.parallel, 'use_gpu') && ...
              config.parallel.use_gpu;

    % GPU-accelerated erosion (only when use_gpu=true and GPU available)
    if use_gpu
        try
            if gpuDeviceCount > 0
                bg_eroded = gather(imerode(gpuArray(bg), se));
            else
                bg_eroded = imerode(bg, se);
            end
        catch
            bg_eroded = imerode(bg, se);
        end
    else
        bg_eroded = imerode(bg, se);
    end
    bg_reconstructed = imreconstruct(bg_eroded, bg);  % CPU (GPU support limited)
    holes = bg & ~bg_reconstructed;              % what was destroyed = holes

    hole_px = sum(holes(:));
    fprintf('    Pass 2 (morph reconstruction, r=%d): %d hole pixels\n', ...
        fill_r, hole_px);

    %% ================================================================
    %  Final: Combine + cleanup
    %  ================================================================
    dnapl_mask = mask_red | holes;

    % Fill any remaining topologically enclosed holes
    dnapl_mask = imfill(dnapl_mask, 'holes');

    % Morphological cleanup (shared with v1)
    dnapl_mask = refine_mask(dnapl_mask, morph_radius, min_area);

    % Enforce pore-space constraint
    dnapl_mask = dnapl_mask & flow_domain;

    % Update seg_info
    seg_info.method = config.segmentation.method;
    seg_info.v2_hole_fill_radius = fill_r;
    seg_info.v2_red_pixels = red_px;
    seg_info.v2_hole_pixels = hole_px;

    final_px = sum(dnapl_mask(:));
    added_px = final_px - red_px;
    fprintf('    Final: %d pixels (+%d recovered, %.1f%% increase)\n', ...
        final_px, max(added_px,0), 100*max(added_px,0)/max(red_px,1));
end
