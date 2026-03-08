function bd = compute_branch_density(G, skel_length)
% COMPUTE_BRANCH_DENSITY  Branch density from merged junction count.
%
%   bd = compute_branch_density(G, skel_length)
%
%   Uses merged junction count (NOT raw branchpoint pixel count).
%   rho_b = N_junction / L_skel
%
%   Inputs:
%       G           - Graph struct from skeleton_to_graph
%       skel_length - total skeleton length [px]
%
%   Output:
%       bd - Struct with:
%           .num_junctions   - number of merged junctions
%           .num_bp_pixels   - raw branchpoint pixel count (for reference only)
%           .branch_density  - rho_b = N_junction / L_skel
%           .note            - clarification string

    fprintf('    Computing branch density...\n');

    bd.num_junctions = G.num_junctions;

    % Raw branchpoint pixel count (for comparison only, NOT used as metric)
    bp_raw = 0;
    for k = 1:numel(G.nodes)
        if strcmp(G.nodes(k).type, 'junction')
            bp_raw = bp_raw + numel(G.nodes(k).pixel_idx);
        end
    end
    bd.num_bp_pixels = bp_raw;

    % Branch density = merged junctions / skeleton length
    bd.branch_density = G.num_junctions / max(skel_length, 1);

    bd.note = 'branch_density = N_junction (merged) / L_skel. NOT raw branchpoint pixels.';

    fprintf('      Junctions (merged): %d\n', bd.num_junctions);
    fprintf('      Raw BP pixels: %d (NOT used as metric)\n', bp_raw);
    fprintf('      Branch density: %.5f junctions/px\n', bd.branch_density);
end
