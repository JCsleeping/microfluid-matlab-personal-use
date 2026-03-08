function water_connected = extract_inlet_connected(water_mask, flow_domain, inlet_side)
% EXTRACT_INLET_CONNECTED  Keep only water pixels connected to inlet boundary.
%
%   water_connected = extract_inlet_connected(water_mask, flow_domain, inlet_side)
%
%   From the full water_mask, extracts only the connected component(s) that
%   touch the inlet boundary. Trapped/isolated water pockets are excluded.
%
%   Inputs:
%       water_mask  - M x N logical (flow_domain & ~dnapl_mask)
%       flow_domain - M x N logical pore-space mask
%       inlet_side  - 'left' | 'right' | 'top' | 'bottom'
%
%   Output:
%       water_connected - M x N logical, inlet-connected water only

    fprintf('    Extracting inlet-connected water phase...\n');

    [H, W] = size(water_mask);

    %% Build inlet boundary mask (1-pixel strip at the inlet edge)
    inlet_mask = false(H, W);
    switch lower(inlet_side)
        case 'left'
            inlet_mask(:, 1:3) = true;    % 3-pixel strip for robustness
        case 'right'
            inlet_mask(:, (W-2):W) = true;
        case 'top'
            inlet_mask(1:3, :) = true;
        case 'bottom'
            inlet_mask((H-2):H, :) = true;
        otherwise
            error('extract_inlet_connected:badSide', ...
                'Unknown inlet_side "%s". Use left/right/top/bottom.', inlet_side);
    end

    % Inlet boundary within flow domain
    inlet_region = inlet_mask & flow_domain;

    %% Find connected components of water_mask
    cc = bwconncomp(water_mask, 8);

    %% Keep only components touching the inlet
    water_connected = false(H, W);
    n_connected = 0;

    for k = 1:cc.NumObjects
        comp_mask = false(H, W);
        comp_mask(cc.PixelIdxList{k}) = true;

        % Check if this component overlaps the inlet boundary
        if any(comp_mask(:) & inlet_region(:))
            water_connected = water_connected | comp_mask;
            n_connected = n_connected + 1;
        end
    end

    total_water = sum(water_mask(:));
    connected_water = sum(water_connected(:));
    excluded_water = total_water - connected_water;

    fprintf('      Total water components: %d\n', cc.NumObjects);
    fprintf('      Inlet-connected: %d components, %d px\n', n_connected, connected_water);
    fprintf('      Excluded (isolated): %d px (%.1f%%)\n', ...
        excluded_water, 100*excluded_water/max(total_water, 1));
end
