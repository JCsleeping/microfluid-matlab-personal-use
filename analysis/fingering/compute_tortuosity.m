function tau = compute_tortuosity(backbone, fingers, G)
% COMPUTE_TORTUOSITY  Geometric tortuosity using Euclidean distance.
%
%   tau = compute_tortuosity(backbone, fingers, G)
%
%   Physics constraint (diamond/diverging flow field):
%     Forbidden to use flow-direction projection as denominator.
%     Tortuosity = geodesic_length / Euclidean_distance (tip-to-root)
%
%   Inputs:
%       backbone - struct from extract_backbone
%       fingers  - struct from extract_terminal_branches
%       G        - graph struct (for node positions)
%
%   Output:
%       tau - Struct with tau_backbone, tau_fingers, tau_mean

    fprintf('    Computing tortuosity (Euclidean denominator)...\n');

    nodes = G.nodes;

    %% Backbone tortuosity: L_backbone / Euclidean(inlet, tip)
    if isfield(backbone, 'inlet_node') && isfield(backbone, 'tip_node') && ...
            backbone.inlet_node <= numel(nodes) && backbone.tip_node <= numel(nodes)
        in_n = nodes(backbone.inlet_node);
        tip_n = nodes(backbone.tip_node);
        L_euclid = sqrt((in_n.row - tip_n.row)^2 + (in_n.col - tip_n.col)^2);
        L_euclid = max(L_euclid, 1);

        tau.tau_backbone = backbone.L_backbone / L_euclid;
        tau.L_backbone_geo = backbone.L_backbone;
        tau.L_backbone_euclid = L_euclid;
    else
        tau.tau_backbone = NaN;
        tau.L_backbone_geo = NaN;
        tau.L_backbone_euclid = NaN;
    end

    fprintf('      Backbone: L_geo=%.1f, L_euclid=%.1f, tau=%.3f\n', ...
        tau.L_backbone_geo, tau.L_backbone_euclid, tau.tau_backbone);

    %% Per-finger tortuosity: L_geo / Euclidean(root, tip)
    if ~isempty(fingers) && isfield(fingers, 'fingers') && ~isempty(fingers.fingers)
        n_f = numel(fingers.fingers);
        tau_f = zeros(n_f, 1);

        for k = 1:n_f
            f = fingers.fingers(k);
            L_geo = f.length;
            L_euc = sqrt((f.tip_row - f.root_row)^2 + (f.tip_col - f.root_col)^2);
            L_euc = max(L_euc, 1);
            tau_f(k) = L_geo / L_euc;
        end

        tau.tau_fingers = tau_f;
        tau.tau_mean = mean(tau_f);
        tau.tau_median = median(tau_f);
        tau.tau_std = std(tau_f);

        fprintf('      Fingers: mean tau=%.3f, median=%.3f\n', tau.tau_mean, tau.tau_median);
    else
        tau.tau_fingers = [];
        tau.tau_mean = NaN;
        tau.tau_median = NaN;
        tau.tau_std = NaN;
    end
end
