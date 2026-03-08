function front = track_leading_front(water_connected, inlet_side, pore_space)
% TRACK_LEADING_FRONT  Leading front + cumulative invaded area.
%
%   front = track_leading_front(water_connected, inlet_side, pore_space)
%
%   Physics enhancement: also computes cumulative water invasion area
%   A_invaded to counter diamond cross-section velocity distortion.
%
%   Inputs:
%       water_connected - M x N logical (inlet-connected water)
%       inlet_side      - 'left' | 'right' | 'top' | 'bottom'
%       pore_space      - M x N logical (for normalization)
%
%   Output:
%       front - Struct with x_lead, front_width, A_invaded, front_profile

    if nargin < 3, pore_space = true(size(water_connected)); end

    [H, W] = size(water_connected);

    switch lower(inlet_side)
        case 'left'
            col_presence = any(water_connected, 1);
            if any(col_presence)
                front.x_lead = find(col_presence, 1, 'last');
                leading_col = water_connected(:, front.x_lead);
                front.front_width = sum(leading_col);
                % Normalized front width: width / pore_space width at that column
                pore_at_lead = sum(pore_space(:, front.x_lead));
                front.front_width_norm = front.front_width / max(pore_at_lead, 1);
            else
                front.x_lead = 0; front.front_width = 0; front.front_width_norm = 0;
            end
            front.front_profile = sum(water_connected, 1);

        case 'right'
            col_presence = any(water_connected, 1);
            if any(col_presence)
                front.x_lead = W - find(col_presence, 1, 'first') + 1;
                lead_col_idx = find(col_presence, 1, 'first');
                front.front_width = sum(water_connected(:, lead_col_idx));
                pore_at_lead = sum(pore_space(:, lead_col_idx));
                front.front_width_norm = front.front_width / max(pore_at_lead, 1);
            else
                front.x_lead = 0; front.front_width = 0; front.front_width_norm = 0;
            end
            front.front_profile = fliplr(sum(water_connected, 1));

        case 'top'
            row_presence = any(water_connected, 2);
            if any(row_presence)
                front.x_lead = find(row_presence, 1, 'last');
                front.front_width = sum(water_connected(front.x_lead, :));
                pore_at_lead = sum(pore_space(front.x_lead, :));
                front.front_width_norm = front.front_width / max(pore_at_lead, 1);
            else
                front.x_lead = 0; front.front_width = 0; front.front_width_norm = 0;
            end
            front.front_profile = sum(water_connected, 2)';

        case 'bottom'
            row_presence = any(water_connected, 2);
            if any(row_presence)
                front.x_lead = H - find(row_presence, 1, 'first') + 1;
                lead_row_idx = find(row_presence, 1, 'first');
                front.front_width = sum(water_connected(lead_row_idx, :));
                pore_at_lead = sum(pore_space(lead_row_idx, :));
                front.front_width_norm = front.front_width / max(pore_at_lead, 1);
            else
                front.x_lead = 0; front.front_width = 0; front.front_width_norm = 0;
            end
            front.front_profile = flipud(sum(water_connected, 2))';
    end

    %% Cumulative invaded area (counters diamond cross-section distortion)
    front.A_invaded = sum(water_connected(:));
    front.A_pore = sum(pore_space(:));
    front.A_invaded_norm = front.A_invaded / max(front.A_pore, 1);
end
