function width_result = compute_local_width(mask, skeleton, solid_mask, pixel_size)
% COMPUTE_LOCAL_WIDTH  Local width via distance transform with solid boundaries.
%
%   width_result = compute_local_width(mask, skeleton, solid_mask)
%   width_result = compute_local_width(mask, skeleton, solid_mask, pixel_size)
%
%   Physics constraint: bwdist zero-boundary includes solid_mask walls,
%   so the distance transform reflects the true confined hydraulic radius.
%   w(s) = 2 * D(s) at skeleton pixels, where D accounts for solid walls.
%
%   Inputs:
%       mask       - M x N logical, binary mask of the object
%       skeleton   - M x N logical, skeleton of the same object
%       solid_mask - M x N logical, solid pillar locations
%       pixel_size - (optional) physical pixel size [m]
%
%   Output:
%       width_result - Struct with width distribution and heatmap

    if nargin < 4, pixel_size = []; end

    fprintf('    Computing local width (solid-wall-bounded)...\n');

    %% Distance transform: boundary = ~mask OR solid walls
    % This ensures distance is measured to the nearest non-mask pixel
    % INCLUDING solid pillar walls, reflecting true hydraulic confinement.
    boundary = ~mask | solid_mask;
    D = bwdist(boundary);
    width_result.distance_map = D;

    %% Extract widths at skeleton pixels
    skel_idx = find(skeleton);
    local_radii = D(skel_idx);
    local_widths = 2 * local_radii;

    width_result.local_widths_px = local_widths;

    %% Statistics
    if ~isempty(local_widths) && any(local_widths > 0)
        valid = local_widths > 0;
        lw = local_widths(valid);
        width_result.mean_width_px   = mean(lw);
        width_result.median_width_px = median(lw);
        width_result.width_p90_px    = prctile(lw, 90);
        width_result.width_std_px    = std(lw);
        width_result.width_cv        = std(lw) / max(mean(lw), eps);
        width_result.width_min_px    = min(lw);
        width_result.width_max_px    = max(lw);
    else
        width_result.mean_width_px   = 0;
        width_result.median_width_px = 0;
        width_result.width_p90_px    = 0;
        width_result.width_std_px    = 0;
        width_result.width_cv        = 0;
        width_result.width_min_px    = 0;
        width_result.width_max_px    = 0;
    end

    %% Equivalent width (secondary metric, A/L_skel)
    skel_length = sum(skeleton(:));
    area = sum(mask(:));
    width_result.W_eq_px = area / max(skel_length, 1);

    %% Width heatmap
    heatmap = zeros(size(mask));
    heatmap(skel_idx) = local_widths;
    width_result.width_heatmap = heatmap;

    %% Physical units
    if ~isempty(pixel_size) && isnumeric(pixel_size) && pixel_size > 0
        um = pixel_size * 1e6;
        width_result.mean_width_um   = width_result.mean_width_px * um;
        width_result.median_width_um = width_result.median_width_px * um;
        width_result.width_p90_um    = width_result.width_p90_px * um;
        width_result.W_eq_um         = width_result.W_eq_px * um;
    end

    fprintf('      Mean width:   %.1f px (solid-bounded)\n', width_result.mean_width_px);
    fprintf('      Median width: %.1f px\n', width_result.median_width_px);
    fprintf('      P90 width:    %.1f px\n', width_result.width_p90_px);
    fprintf('      CV:           %.3f\n', width_result.width_cv);
    fprintf('      W_eq (A/L):   %.1f px (secondary)\n', width_result.W_eq_px);
end
