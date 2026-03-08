function fb = extract_terminal_branches(skeleton, G, backbone_mask, fconfig, pore_scale)
% EXTRACT_TERMINAL_BRANCHES  Valid fingers with pore-scale-anchored thresholds.
%
%   fb = extract_terminal_branches(skeleton, G, backbone_mask, fconfig, pore_scale)
%
%   Finger definition (strict):
%     1. Attached to backbone
%     2. Geodesic length >= min_finger_pore_factor * pore_scale
%     3. Euclidean root-to-tip distance >= min_finger_advance_factor * pore_scale
%
%   Inputs:
%       skeleton      - M x N logical
%       G             - Graph struct
%       backbone_mask - M x N logical
%       fconfig       - config (for factors, fallback pixel values)
%       pore_scale    - average pore scale [px]
%
%   Output:
%       fb - Struct with num_fingers, per-finger metrics, finger_mask

    fprintf('    Extracting terminal branches (pore-scale-anchored)...\n');

    % Threshold anchoring: "at least 2-3 pore diameters"
    if isfield(fconfig, 'min_finger_pore_factor')
        len_factor = fconfig.min_finger_pore_factor;
    else
        len_factor = 2.0;  % default: 2 pore diameters
    end
    if isfield(fconfig, 'min_finger_advance_factor')
        adv_factor = fconfig.min_finger_advance_factor;
    else
        adv_factor = 1.5;  % default: 1.5 pore diameters
    end

    min_len = len_factor * pore_scale;
    min_adv = adv_factor * pore_scale;

    fprintf('      Pore scale = %.1f px\n', pore_scale);
    fprintf('      min_finger_length = %.1f px (%.1f x pore)\n', min_len, len_factor);
    fprintf('      min_finger_advance = %.1f px (%.1f x pore)\n', min_adv, adv_factor);

    [H, W] = size(skeleton);

    %% Find branch segments (skeleton minus backbone)
    branch_skel = skeleton & ~backbone_mask;
    branch_cc = bwconncomp(branch_skel, 8);
    backbone_dilated = imdilate(backbone_mask, ones(3));

    all_branches = struct('mask', {}, 'length', {}, 'euclid_dist', {}, ...
        'tip_row', {}, 'tip_col', {}, 'root_row', {}, 'root_col', {}, 'is_valid', {});

    for k = 1:branch_cc.NumObjects
        seg_mask = false(H, W);
        seg_mask(branch_cc.PixelIdxList{k}) = true;

        % Must touch backbone
        seg_dil = imdilate(seg_mask, ones(3));
        if ~any(seg_dil(:) & backbone_mask(:)), continue; end

        % Endpoints
        seg_ep = bwmorph(seg_mask, 'endpoints');
        [ep_r, ep_c] = find(seg_ep);
        if isempty(ep_r), continue; end

        % Geodesic length
        geo_len = compute_branch_len(branch_cc.PixelIdxList{k}, H, W);

        % Root = touching backbone, Tip = farthest
        is_root = false(numel(ep_r), 1);
        for j = 1:numel(ep_r)
            test = false(H,W); test(ep_r(j),ep_c(j)) = true;
            if any(imdilate(test,ones(3)) & backbone_mask), is_root(j) = true; end
        end

        root_idx = find(is_root, 1, 'first');
        tip_idx  = find(~is_root, 1, 'first');
        if isempty(root_idx), root_idx = 1; end
        if isempty(tip_idx), tip_idx = numel(ep_r); end

        tip_r = ep_r(tip_idx); tip_c = ep_c(tip_idx);
        root_r = ep_r(root_idx); root_c = ep_c(root_idx);

        % Euclidean distance (root to tip)
        euclid = sqrt((tip_r-root_r)^2 + (tip_c-root_c)^2);

        idx = numel(all_branches) + 1;
        all_branches(idx).mask = seg_mask;
        all_branches(idx).length = geo_len;
        all_branches(idx).euclid_dist = euclid;
        all_branches(idx).tip_row = tip_r;
        all_branches(idx).tip_col = tip_c;
        all_branches(idx).root_row = root_r;
        all_branches(idx).root_col = root_c;
        all_branches(idx).is_valid = (geo_len >= min_len) && (euclid >= min_adv);
    end

    %% Filter valid fingers
    valid_idx = find([all_branches.is_valid]);
    fb.num_fingers = numel(valid_idx);
    fb.all_branches = all_branches;

    finger_mask = false(H, W);
    fingers = struct('length', {}, 'euclid_dist', {}, ...
        'tip_row', {}, 'tip_col', {}, 'root_row', {}, 'root_col', {});

    for k = 1:numel(valid_idx)
        i = valid_idx(k);
        fingers(k).length      = all_branches(i).length;
        fingers(k).euclid_dist = all_branches(i).euclid_dist;
        fingers(k).tip_row     = all_branches(i).tip_row;
        fingers(k).tip_col     = all_branches(i).tip_col;
        fingers(k).root_row    = all_branches(i).root_row;
        fingers(k).root_col    = all_branches(i).root_col;
        finger_mask = finger_mask | all_branches(i).mask;
    end

    fb.fingers = fingers;
    fb.finger_mask = finger_mask;
    fb.min_len_used = min_len;
    fb.min_adv_used = min_adv;

    fprintf('      Total backbone-attached branches: %d\n', numel(all_branches));
    fprintf('      Valid fingers: %d\n', fb.num_fingers);
    if fb.num_fingers > 0
        fprintf('      Finger lengths: mean=%.1f, range=[%.1f, %.1f] px\n', ...
            mean([fingers.length]), min([fingers.length]), max([fingers.length]));
    end
end


function L = compute_branch_len(px_list, H, W)
    [r,c] = ind2sub([H,W], px_list);
    coords = sortrows([r,c]);
    L = 0;
    for j=1:(size(coords,1)-1)
        dy=abs(coords(j+1,1)-coords(j,1)); dx=abs(coords(j+1,2)-coords(j,2));
        if dx+dy==2, L=L+sqrt(2); elseif dx+dy==1, L=L+1;
        else, L=L+sqrt(double(dx^2+dy^2)); end
    end
    if L==0, L=numel(px_list); end
end
