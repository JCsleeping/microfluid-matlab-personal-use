function skel_result = extract_skeleton_pruned(mask, pore_scale, min_branch_factors)
% EXTRACT_SKELETON_PRUNED  Skeleton with pore-scale-anchored pruning.
%
%   skel_result = extract_skeleton_pruned(mask, pore_scale)
%   skel_result = extract_skeleton_pruned(mask, pore_scale, min_branch_factors)
%
%   Pruning thresholds are anchored to pore_scale (not arbitrary pixels):
%     MinBranchLength = factor * pore_scale
%   Default factors: [0.5, 1.0] (i.e., prune branches < 0.5 or 1.0 pore diameters)
%
%   Inputs:
%       mask               - M x N logical
%       pore_scale         - average pore throat diameter [px]
%       min_branch_factors - vector of factors (default: [0.5, 1.0])
%
%   Output:
%       skel_result - Struct with raw + pruned skeletons

    if nargin < 3 || isempty(min_branch_factors)
        min_branch_factors = [0.5, 1.0];
    end

    fprintf('    Extracting skeleton (pore-scale-anchored pruning)...\n');
    fprintf('      Pore scale = %.1f px\n', pore_scale);

    %% Raw skeleton
    skel_raw = bwskel(logical(mask));
    skel_result.skeleton_raw = skel_raw;
    skel_result.skel_length_raw = compute_chain_length(skel_raw);

    fprintf('      Raw: %d px, chain-length = %.1f\n', ...
        sum(skel_raw(:)), skel_result.skel_length_raw);

    %% Pruned at each factor level
    n_levels = numel(min_branch_factors);
    pruned_arr = struct('factor', {}, 'min_branch_length', {}, ...
        'skeleton', {}, 'skel_length', {}, 'num_endpoints', {}, 'num_branchpoints', {});

    for i = 1:n_levels
        mbl = round(min_branch_factors(i) * pore_scale);
        mbl = max(mbl, 3);  % absolute minimum

        skel_pruned = bwskel(logical(mask), 'MinBranchLength', mbl);
        endpoints = bwmorph(skel_pruned, 'endpoints');
        branchpoints = bwmorph(skel_pruned, 'branchpoints');

        pruned_arr(i).factor = min_branch_factors(i);
        pruned_arr(i).min_branch_length = mbl;
        pruned_arr(i).skeleton = skel_pruned;
        pruned_arr(i).skel_length = compute_chain_length(skel_pruned);
        pruned_arr(i).num_endpoints = sum(endpoints(:));
        pruned_arr(i).num_branchpoints = sum(branchpoints(:));

        fprintf('      Factor=%.1f -> MinBranch=%d px: L=%.1f, ep=%d, bp=%d\n', ...
            min_branch_factors(i), mbl, pruned_arr(i).skel_length, ...
            pruned_arr(i).num_endpoints, pruned_arr(i).num_branchpoints);
    end

    skel_result.pruned = pruned_arr;
    skel_result.best_idx = min(2, n_levels);  % prefer more aggressive pruning
    skel_result.pore_scale = pore_scale;
end


function L = compute_chain_length(skel)
    boundaries = bwboundaries(skel, 8, 'noholes');
    L = 0;
    for k = 1:numel(boundaries)
        B = boundaries{k};
        for j = 1:(size(B,1)-1)
            dy = abs(B(j+1,1)-B(j,1));
            dx = abs(B(j+1,2)-B(j,2));
            if dx+dy==2, L=L+sqrt(2); else, L=L+1; end
        end
    end
    if L==0, L=sum(skel(:)); end
end
