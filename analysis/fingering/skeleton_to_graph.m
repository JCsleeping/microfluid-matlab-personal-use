function G = skeleton_to_graph(skeleton)
% SKELETON_TO_GRAPH  Convert pixel skeleton to graph with junction merging.
%
%   G = skeleton_to_graph(skeleton)
%
%   Converts a 1-pixel-wide skeleton into a graph structure:
%     1. Detect endpoints (degree 1) and branchpoints (degree >= 3)
%     2. Merge adjacent branchpoint pixels into single junction nodes
%     3. Trace edges between junctions/endpoints
%
%   Input:
%       skeleton - M x N logical, 1-pixel-wide skeleton
%
%   Output:
%       G - Struct with fields:
%           .nodes         - N_nodes x 1 struct array (row, col, type, cluster_id)
%           .num_nodes     - total nodes
%           .num_endpoints - endpoints count
%           .num_junctions - merged junction count
%           .edges         - E x 2 matrix of node index pairs
%           .edge_lengths  - E x 1 vector of edge geodesic lengths
%           .node_image    - M x N labeled image (0=bg, >0=node id)

    fprintf('    Converting skeleton to graph...\n');

    %% Step 1: Detect key pixels
    ep_mask = bwmorph(skeleton, 'endpoints');
    bp_mask = bwmorph(skeleton, 'branchpoints');

    %% Step 2: Merge adjacent branchpoints into junctions
    % Adjacent branchpoint pixels (within 3x3 neighborhood) form one junction
    bp_cc = bwconncomp(bp_mask, 8);
    n_junctions = bp_cc.NumObjects;

    % Build node list: first junctions, then endpoints
    nodes = struct('row', {}, 'col', {}, 'type', {}, 'pixel_idx', {});
    node_id = 0;

    % Junction nodes (merged branchpoint clusters)
    [H, W] = size(skeleton);
    node_image = zeros(H, W);

    for k = 1:n_junctions
        node_id = node_id + 1;
        [rows, cols] = ind2sub([H, W], bp_cc.PixelIdxList{k});
        % Centroid of the cluster
        nodes(node_id).row = round(mean(rows));
        nodes(node_id).col = round(mean(cols));
        nodes(node_id).type = 'junction';
        nodes(node_id).pixel_idx = bp_cc.PixelIdxList{k};
        % Mark all pixels of this cluster
        node_image(bp_cc.PixelIdxList{k}) = node_id;
    end

    % Endpoint nodes
    [ep_rows, ep_cols] = find(ep_mask);
    for k = 1:numel(ep_rows)
        node_id = node_id + 1;
        nodes(node_id).row = ep_rows(k);
        nodes(node_id).col = ep_cols(k);
        nodes(node_id).type = 'endpoint';
        nodes(node_id).pixel_idx = sub2ind([H, W], ep_rows(k), ep_cols(k));
        node_image(ep_rows(k), ep_cols(k)) = node_id;
    end

    n_endpoints = numel(ep_rows);

    %% Step 3: Trace edges between nodes
    % Remove node pixels from skeleton to get "edge pixels"
    edge_skeleton = skeleton & ~bp_mask & ~ep_mask;

    % Label edge segments
    edge_cc = bwconncomp(edge_skeleton, 8);
    n_segments = edge_cc.NumObjects;

    edges = [];
    edge_lengths = [];

    for k = 1:n_segments
        seg_mask = false(H, W);
        seg_mask(edge_cc.PixelIdxList{k}) = true;

        % Find which nodes this segment connects to
        seg_dilated = imdilate(seg_mask, ones(3));
        touching_nodes = unique(node_image(seg_dilated & (node_image > 0)));
        touching_nodes = touching_nodes(touching_nodes > 0);

        if numel(touching_nodes) == 2
            % Normal case: edge connects two distinct nodes
            edges = [edges; touching_nodes(1), touching_nodes(2)]; %#ok<AGROW>
            edge_lengths = [edge_lengths; compute_segment_length(edge_cc.PixelIdxList{k}, H, W)]; %#ok<AGROW>
        elseif numel(touching_nodes) == 1
            % Loop or dangling segment — record as self-edge (informational)
            edges = [edges; touching_nodes(1), touching_nodes(1)]; %#ok<AGROW>
            edge_lengths = [edge_lengths; compute_segment_length(edge_cc.PixelIdxList{k}, H, W)]; %#ok<AGROW>
        end
        % segments touching 0 or >2 nodes are noise — skip
    end

    %% Package output
    G.nodes = nodes;
    G.num_nodes = node_id;
    G.num_endpoints = n_endpoints;
    G.num_junctions = n_junctions;
    G.edges = edges;
    G.edge_lengths = edge_lengths;
    G.node_image = node_image;

    fprintf('      Nodes: %d (%d junctions + %d endpoints)\n', ...
        node_id, n_junctions, n_endpoints);
    fprintf('      Edges: %d (total length = %.1f px)\n', ...
        size(edges, 1), sum(edge_lengths));
end


function L = compute_segment_length(pixel_list, H, W)
% Chain-code corrected segment length
    [rows, cols] = ind2sub([H, W], pixel_list);
    coords = sortrows([rows, cols]);  % approximate ordering

    L = 0;
    for j = 1:(size(coords,1) - 1)
        dy = abs(coords(j+1,1) - coords(j,1));
        dx = abs(coords(j+1,2) - coords(j,2));
        if dx + dy == 2
            L = L + sqrt(2);
        elseif dx + dy == 1
            L = L + 1;
        else
            % Non-adjacent: estimate
            L = L + sqrt(double(dx^2 + dy^2));
        end
    end
    if L == 0
        L = numel(pixel_list);
    end
end
