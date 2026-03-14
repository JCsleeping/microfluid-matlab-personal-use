function dnapl_water_length_px = compute_timeseries_interface_length(mask, solid_contact_zone)
% COMPUTE_TIMESERIES_INTERFACE_LENGTH  Lightweight DNAPL-water interface length.

    dnapl_boundary = bwperim(mask);
    dnapl_water_interface = dnapl_boundary & ~solid_contact_zone;
    dnapl_water_length_px = compute_boundary_length_local(dnapl_water_interface);
end


function total_length = compute_boundary_length_local(boundary_mask)
    boundaries = bwboundaries(boundary_mask, 8, 'noholes');
    total_length = 0;

    for k = 1:numel(boundaries)
        B = boundaries{k};
        n = size(B, 1);
        if n < 2
            continue;
        end

        for j = 1:(n - 1)
            dy = abs(B(j+1, 1) - B(j, 1));
            dx = abs(B(j+1, 2) - B(j, 2));
            if dx + dy == 2
                total_length = total_length + sqrt(2);
            else
                total_length = total_length + 1;
            end
        end
    end

    if total_length == 0
        total_length = sum(boundary_mask(:));
    end
end
