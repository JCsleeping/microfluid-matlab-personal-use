function bb = extract_backbone(skeleton, G, inlet_side, width_at_edges)
% EXTRACT_BACKBONE  Backbone via minimum hydraulic resistance path.
%
%   bb = extract_backbone(skeleton, G, inlet_side, width_at_edges)
%
%   Physics constraint: FORBIDDEN to use geometric longest path in cyclic graphs.
%   Instead, assigns hydraulic resistance weight to each edge:
%     Weight = Length / Width^3  (Hagen-Poiseuille-like resistance)
%   Then uses Dijkstra to find the minimum-resistance path from inlet to
%   the most advanced endpoint.
%
%   Inputs:
%       skeleton       - M x N logical
%       G              - Graph struct from skeleton_to_graph
%       inlet_side     - 'left' | 'right' | 'top' | 'bottom'
%       width_at_edges - struct with edge_widths field (from compute_edge_widths)
%                        or [] for fallback to geometric shortest path
%
%   Output:
%       bb - Struct with backbone_mask, L_backbone, inlet/tip nodes

    fprintf('    Extracting backbone (hydraulic resistance)...\n');

    [H, W] = size(skeleton);
    nodes = G.nodes;
    n_nodes = G.num_nodes;

    if n_nodes < 2
        bb.backbone_mask = skeleton;
        bb.L_backbone = sum(skeleton(:));
        bb.inlet_node = 1; bb.tip_node = 1;
        fprintf('      Skeleton too simple.\n');
        return;
    end

    %% Determine advance coordinate for each node
    node_advance = zeros(n_nodes, 1);
    for i = 1:n_nodes
        switch lower(inlet_side)
            case 'left',   node_advance(i) = nodes(i).col;
            case 'right',  node_advance(i) = W - nodes(i).col;
            case 'top',    node_advance(i) = nodes(i).row;
            case 'bottom', node_advance(i) = H - nodes(i).row;
        end
    end

    %% Find inlet node (min advance) and tip node (max advance among endpoints)
    ep_idx = find(strcmp({nodes.type}, 'endpoint'));
    if isempty(ep_idx), ep_idx = 1:n_nodes; end

    [~, min_i] = min(node_advance(ep_idx));
    [~, max_i] = max(node_advance(ep_idx));
    inlet_node = ep_idx(min_i);
    tip_node   = ep_idx(max_i);

    bb.inlet_node = inlet_node;
    bb.tip_node   = tip_node;

    %% Build weighted graph with hydraulic resistance
    if ~isempty(G.edges) && size(G.edges, 1) > 0
        valid = G.edges(:,1) ~= G.edges(:,2);  % remove self-loops
        edges_v = G.edges(valid, :);
        lens_v  = G.edge_lengths(valid);

        % Compute hydraulic resistance weights
        if ~isempty(width_at_edges) && isfield(width_at_edges, 'edge_widths')
            ew = width_at_edges.edge_widths(valid);
            ew = max(ew, 1);  % avoid division by zero
            % Hagen-Poiseuille: R ~ L / w^3
            weights = lens_v ./ (ew .^ 3);
        else
            % Fallback: uniform weights = edge lengths
            weights = lens_v;
            fprintf('      WARNING: No width data, using geometric shortest path.\n');
        end

        if ~isempty(edges_v)
            mg = graph(edges_v(:,1), edges_v(:,2), weights);
            try
                path_nodes = shortestpath(mg, inlet_node, tip_node);
            catch
                path_nodes = [inlet_node, tip_node];
                fprintf('      WARNING: No path found, using direct connection.\n');
            end
        else
            path_nodes = [inlet_node, tip_node];
        end
    else
        path_nodes = [inlet_node, tip_node];
    end

    %% Reconstruct backbone mask
    backbone_mask = false(H, W);

    for k = 1:numel(path_nodes)
        backbone_mask(nodes(path_nodes(k)).pixel_idx) = true;
    end

    % Find edge segments connecting consecutive path nodes
    bp_mask = G.node_image > 0;
    edge_skel = skeleton & ~bp_mask;
    edge_cc = bwconncomp(edge_skel, 8);

    for k = 1:(numel(path_nodes)-1)
        n1 = path_nodes(k); n2 = path_nodes(k+1);
        m1 = false(H,W); m1(nodes(n1).pixel_idx) = true;
        m2 = false(H,W); m2(nodes(n2).pixel_idx) = true;
        d1 = imdilate(m1, ones(3));
        d2 = imdilate(m2, ones(3));

        for j = 1:edge_cc.NumObjects
            seg = false(H,W);
            seg(edge_cc.PixelIdxList{j}) = true;
            sd = imdilate(seg, ones(3));
            if any(sd(:) & d1(:)) && any(sd(:) & d2(:))
                backbone_mask = backbone_mask | seg;
                break;
            end
        end
    end

    bb.backbone_mask = backbone_mask;

    % Chain-code length
    bb_bound = bwboundaries(backbone_mask, 8, 'noholes');
    L = 0;
    for k = 1:numel(bb_bound)
        B = bb_bound{k};
        for j = 1:(size(B,1)-1)
            dy=abs(B(j+1,1)-B(j,1)); dx=abs(B(j+1,2)-B(j,2));
            if dx+dy==2, L=L+sqrt(2); else, L=L+1; end
        end
    end
    bb.L_backbone = max(L, sum(backbone_mask(:)));

    fprintf('      Backbone: node %d -> %d, L = %.1f px (min-resistance path)\n', ...
        inlet_node, tip_node, bb.L_backbone);
end
