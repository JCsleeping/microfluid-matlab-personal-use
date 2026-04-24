function iface = analyze_interfaces(dnapl_mask, flow_domain, pixel_size, config)
% ANALYZE_INTERFACES  Detect and classify DNAPL boundary interfaces.
%
%   iface = analyze_interfaces(dnapl_mask, flow_domain, pixel_size, config)
%
%   Classifies every DNAPL boundary pixel as either DNAPL-water or
%   DNAPL-solid by checking proximity to solid grains.
%
%   Inputs:
%       dnapl_mask   - M x N logical DNAPL mask
%       flow_domain  - M x N logical pore-space mask
%       pixel_size   - Physical pixel size [m] (can be [])
%       config       - Pipeline configuration struct
%
%   Output:
%       iface - Struct with fields:
%           .dnapl_water_interface   M x N logical
%           .dnapl_solid_interface   M x N logical
%           .dnapl_water_length_px   Total DNAPL-water interface length [pixels]
%           .dnapl_water_length_m    Same in meters
%           .dnapl_solid_length_px   Total DNAPL-solid contact length [pixels]
%           .dnapl_solid_length_m    Same in meters
%           .specific_interfacial_area  a_nw [m^-1]
%           .per_blob_interfaces     Struct array with per-blob breakdown

    if nargin < 3, pixel_size = []; end
    if nargin < 4, config = struct(); end

    solid_dilation = 1;
    if isfield(config, 'interface') && isfield(config.interface, 'solid_dilation')
        solid_dilation = config.interface.solid_dilation;
    end

    %% Step 1: Identify solid grains and their contact zone
    solid_grains = ~flow_domain;
    solid_contact_zone = imdilate(solid_grains, strel('disk', solid_dilation));

    %% Step 2: Find all DNAPL boundary pixels
    dnapl_boundary = bwperim(dnapl_mask);

    %% Step 3: Classify boundary pixels
    iface.dnapl_solid_interface = dnapl_boundary & solid_contact_zone;
    iface.dnapl_water_interface = dnapl_boundary & ~solid_contact_zone;

    %% Step 4: Measure interface lengths using chain code
    iface.dnapl_water_length_px = compute_boundary_length(iface.dnapl_water_interface);
    iface.dnapl_solid_length_px = compute_boundary_length(iface.dnapl_solid_interface);

    %% Step 5: Physical units
    if ~isempty(pixel_size) && pixel_size > 0
        iface.dnapl_water_length_m = iface.dnapl_water_length_px * pixel_size;
        iface.dnapl_solid_length_m = iface.dnapl_solid_length_px * pixel_size;
    else
        iface.dnapl_water_length_m = NaN;
        iface.dnapl_solid_length_m = NaN;
    end

    %% Step 6: Specific interfacial area
    pore_area_m2 = sum(flow_domain(:));
    if ~isempty(pixel_size) && pixel_size > 0
        pore_area_m2 = pore_area_m2 * pixel_size^2;
        iface.specific_interfacial_area = iface.dnapl_water_length_m / pore_area_m2;
    else
        iface.specific_interfacial_area = ...
            iface.dnapl_water_length_px / max(sum(flow_domain(:)), 1);
    end

    dnapl_area_px = sum(dnapl_mask(:) & flow_domain(:));
    if dnapl_area_px > 0
        if ~isempty(pixel_size) && pixel_size > 0
            dnapl_area_m2 = dnapl_area_px * pixel_size^2;
            iface.a_i_2D = iface.dnapl_water_length_m / dnapl_area_m2;
        else
            iface.a_i_2D = iface.dnapl_water_length_px / dnapl_area_px;
        end
    else
        iface.a_i_2D = 0;
    end

    %% Step 7: Per-blob interface analysis
    cc = bwconncomp(dnapl_mask, 8);
    n_blobs = cc.NumObjects;
    per_blob = struct('water_px', cell(1, n_blobs), ...
                      'solid_px', cell(1, n_blobs), ...
                      'contact_fraction', cell(1, n_blobs));

    for i = 1:n_blobs
        blob_mask = false(size(dnapl_mask));
        blob_mask(cc.PixelIdxList{i}) = true;

        blob_boundary = bwperim(blob_mask);
        w = sum(blob_boundary(:) & ~solid_contact_zone(:));
        s = sum(blob_boundary(:) & solid_contact_zone(:));

        per_blob(i).water_px = w;
        per_blob(i).solid_px = s;
        per_blob(i).contact_fraction = s / max(w + s, 1);
    end
    iface.per_blob_interfaces = per_blob;

    fprintf('  Interface analysis: DNAPL-water %.0f px, DNAPL-solid %.0f px\n', ...
        iface.dnapl_water_length_px, iface.dnapl_solid_length_px);
end


function total_length = compute_boundary_length(boundary_mask)
% COMPUTE_BOUNDARY_LENGTH  Compute boundary length accounting for diagonal pixels.
%
%   Traces connected boundaries and counts horizontal/vertical steps as 1,
%   diagonal steps as sqrt(2).

    boundaries = bwboundaries(boundary_mask, 8, 'noholes');
    total_length = 0;

    for k = 1:numel(boundaries)
        B = boundaries{k};
        n = size(B, 1);
        if n < 2, continue; end

        for j = 1:(n - 1)
            dy = abs(B(j+1, 1) - B(j, 1));
            dx = abs(B(j+1, 2) - B(j, 2));
            if dx + dy == 2   % diagonal
                total_length = total_length + sqrt(2);
            else              % horizontal or vertical
                total_length = total_length + 1;
            end
        end
    end

    % If no boundaries were found, fall back to pixel count
    if total_length == 0
        total_length = sum(boundary_mask(:));
    end
end
