function [rgb_image, flow_domain] = load_images(rgb_path, flow_domain_path)
% LOAD_IMAGES  Load and validate RGB image and/or flow domain mask.
%
%   [rgb_image, flow_domain] = load_images(rgb_path, flow_domain_path)
%
%   Either path can be empty '' to skip loading that image.
%
%   Inputs:
%       rgb_path         - Path to RGB image (or '' to skip)
%       flow_domain_path - Path to binary flow domain mask (or '' to skip)
%
%   Outputs:
%       rgb_image    - M x N x 3 uint8 RGB image (or [] if skipped)
%       flow_domain  - M x N logical mask: 1 = pore, 0 = solid (or [])

    rgb_image   = [];
    flow_domain = [];

    %% Load RGB image
    if ~isempty(rgb_path)
        if ~isfile(rgb_path)
            error('load_images:fileNotFound', 'RGB image not found: %s', rgb_path);
        end
        rgb_image = imread(rgb_path);
        % Handle 16-bit TIF: convert to 8-bit uint8
        if isa(rgb_image, 'uint16')
            rgb_image = im2uint8(rgb_image);
        end
        if size(rgb_image, 3) ~= 3
            error('load_images:notRGB', 'Expected 3-channel RGB image, got %d channels.', size(rgb_image, 3));
        end
        fprintf('  Loaded RGB image: %d x %d pixels  (%s)\n', ...
            size(rgb_image, 1), size(rgb_image, 2), rgb_path);
    end

    %% Load flow domain mask
    if ~isempty(flow_domain_path)
        if ~isfile(flow_domain_path)
            error('load_images:fileNotFound', 'Flow domain file not found: %s', flow_domain_path);
        end
        fd_raw = imread(flow_domain_path);
        if ndims(fd_raw) == 3
            fd_raw = rgb2gray(fd_raw);
        end
        flow_domain = fd_raw > 128;  % threshold to binary
        fprintf('  Loaded flow domain: %d x %d pixels  (porosity %.1f%%)\n', ...
            size(flow_domain, 1), size(flow_domain, 2), ...
            100 * sum(flow_domain(:)) / numel(flow_domain));
    end
end
