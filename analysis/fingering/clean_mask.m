function mask_clean = clean_mask(mask, flow_domain, opts)
% CLEAN_MASK  Preprocess a binary mask for fingering analysis.
%
%   mask_clean = clean_mask(mask, flow_domain)
%   mask_clean = clean_mask(mask, flow_domain, opts)
%
%   Operations:
%     1. Constrain to flow_domain
%     2. Remove small noise blobs (bwareaopen)
%     3. Fill small internal holes (imfill + area filter)
%     4. Optional morphological smoothing (open-close)
%
%   Inputs:
%       mask        - M x N logical binary mask
%       flow_domain - M x N logical pore-space mask
%       opts        - (optional) struct with fields:
%           .min_area       - minimum blob area to keep [px] (default: 20)
%           .fill_holes     - fill internal holes (default: true)
%           .max_hole_area  - max hole area to fill [px] (default: 200)
%           .smooth_radius  - morphological smoothing disk radius (default: 0, off)
%
%   Output:
%       mask_clean - M x N logical, cleaned mask

    if nargin < 3, opts = struct(); end

    min_area      = get_opt(opts, 'min_area', 20);
    fill_holes    = get_opt(opts, 'fill_holes', true);
    max_hole_area = get_opt(opts, 'max_hole_area', 200);
    smooth_radius = get_opt(opts, 'smooth_radius', 0);

    %% 1. Constrain to flow domain
    mask_clean = mask & flow_domain;

    %% 2. Remove small noise blobs
    mask_clean = bwareaopen(mask_clean, min_area);

    %% 3. Fill internal holes (only small ones)
    if fill_holes
        % Find all holes
        filled = imfill(mask_clean, 'holes');
        holes = filled & ~mask_clean;

        if any(holes(:))
            % Only fill holes smaller than max_hole_area
            cc_holes = bwconncomp(holes);
            for k = 1:cc_holes.NumObjects
                if numel(cc_holes.PixelIdxList{k}) <= max_hole_area
                    mask_clean(cc_holes.PixelIdxList{k}) = true;
                end
            end
        end
    end

    %% 4. Morphological smoothing (optional)
    if smooth_radius > 0
        se = strel('disk', smooth_radius);
        mask_clean = imopen(mask_clean, se);
        mask_clean = imclose(mask_clean, se);
    end

    %% Re-enforce flow domain constraint
    mask_clean = mask_clean & flow_domain;
end


function val = get_opt(opts, field, default)
    if isfield(opts, field)
        val = opts.(field);
    else
        val = default;
    end
end
