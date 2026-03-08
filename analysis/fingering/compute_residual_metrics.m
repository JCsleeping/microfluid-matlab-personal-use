function res = compute_residual_metrics(dnapl_mask_clean, pore_space, solid_mask)
% COMPUTE_RESIDUAL_METRICS  Residual NAPL metrics with topology cleanup.
%
%   res = compute_residual_metrics(dnapl_mask_clean, pore_space, solid_mask)
%
%   Physics constraints enforced:
%     - Sr denominator = pore_space (NOT flow_domain or total image)
%     - Euler number topology cleanup: holes that merely surround solid
%       pillars (DNAPL wrapping around a pillar) are NOT counted as beta_1.
%       Only holes containing actual water phase are physical enclosures.
%
%   Inputs:
%       dnapl_mask_clean - M x N logical
%       pore_space       - M x N logical (flow_domain, excludes solids)
%       solid_mask       - M x N logical (pillar locations)
%
%   Output:
%       res - Struct with corrected residual metrics

    fprintf('    Computing residual NAPL metrics (topology-corrected)...\n');

    %% Residual area fraction (Sr) — denominator = pore_space
    A_napl = sum(dnapl_mask_clean(:) & pore_space(:));
    A_pore = sum(pore_space(:));
    res.Sr = A_napl / max(A_pore, 1);
    res.A_napl = A_napl;
    res.A_pore_space = A_pore;

    %% Connected components (beta_0)
    cc = bwconncomp(dnapl_mask_clean, 8);
    res.Nc = cc.NumObjects;
    res.beta_0 = cc.NumObjects;

    %% Component area distribution
    comp_areas = cellfun(@numel, cc.PixelIdxList);
    if ~isempty(comp_areas)
        [sorted_areas, ~] = sort(comp_areas, 'descend');
        res.component_areas = sorted_areas;
        res.largest_component_fraction = sorted_areas(1) / max(A_napl, 1);
    else
        res.component_areas = [];
        res.largest_component_fraction = 0;
    end

    %% Holes with topology cleanup (critical physics requirement)
    % Step 1: Find all holes in DNAPL mask
    filled = imfill(dnapl_mask_clean, 'holes');
    all_holes = filled & ~dnapl_mask_clean;

    % Step 2: Classify each hole
    %   Physical hole: contains water phase (pore space without DNAPL)
    %   Pseudo hole: merely wraps around a solid pillar
    water_in_pore = pore_space & ~dnapl_mask_clean;  % actual water phase

    physical_holes = 0;
    pseudo_holes = 0;

    if any(all_holes(:))
        cc_holes = bwconncomp(all_holes, 8);
        for k = 1:cc_holes.NumObjects
            hole_pixels = false(size(dnapl_mask_clean));
            hole_pixels(cc_holes.PixelIdxList{k}) = true;

            % Check what's inside this hole
            water_fraction = sum(hole_pixels(:) & water_in_pore(:)) / numel(cc_holes.PixelIdxList{k});
            solid_fraction = sum(hole_pixels(:) & solid_mask(:)) / numel(cc_holes.PixelIdxList{k});

            if water_fraction > 0.1
                % Contains significant water → physical enclosure
                physical_holes = physical_holes + 1;
            else
                % Dominated by solid → DNAPL wrapping around pillar
                pseudo_holes = pseudo_holes + 1;
            end
        end
    end

    res.beta_1 = physical_holes;           % Only physical holes
    res.beta_1_pseudo = pseudo_holes;      % Pillar-wrapping artifacts
    res.beta_1_total = physical_holes + pseudo_holes;  % All holes (for reference)

    %% Euler number (corrected)
    res.EulerNumber = res.beta_0 - res.beta_1;

    %% Small ganglia
    small_threshold = 50;
    if ~isempty(comp_areas)
        small_mask = comp_areas < small_threshold;
        res.num_small_ganglia = sum(small_mask);
        res.small_ganglia_area_total = sum(comp_areas(small_mask));
    else
        res.num_small_ganglia = 0;
        res.small_ganglia_area_total = 0;
    end

    %% Print summary
    fprintf('      Sr = %.4f (denom = pore_space = %d px)\n', res.Sr, A_pore);
    fprintf('      Nc = %d, beta_0 = %d\n', res.Nc, res.beta_0);
    fprintf('      Holes total = %d: physical = %d, pseudo (pillar-wrap) = %d\n', ...
        res.beta_1_total, res.beta_1, res.beta_1_pseudo);
    fprintf('      Euler (corrected) = %d\n', res.EulerNumber);
    fprintf('      Largest component: %.1f%%\n', 100*res.largest_component_fraction);
    fprintf('      Small ganglia (<%d px): %d\n', small_threshold, res.num_small_ganglia);
end
