function rgb = prepare_rgb_input_encoding(rgb, config)
% PREPARE_RGB_INPUT_ENCODING Normalize raw RGB input encoding for the pipeline.
%
%   rgb = prepare_rgb_input_encoding(rgb, config)
%
%   The existing segmentation pipeline expects sRGB-encoded RGB images
%   before illumination correction and Lab conversion. By default this
%   function is a no-op. When config.input.is_linear_rgb is true, input
%   linear-light RGB values are converted to sRGB encoding once at load time.

    if nargin < 2 || isempty(config) || ~isfield(config, 'input') || ...
            ~isfield(config.input, 'is_linear_rgb') || ~config.input.is_linear_rgb
        return;
    end

    if ~isnumeric(rgb) && ~islogical(rgb)
        error('prepare_rgb_input_encoding:badInput', ...
            'RGB input must be a numeric or logical image array.');
    end

    if ndims(rgb) > 3 || ~(size(rgb, 3) == 1 || size(rgb, 3) == 3)
        error('prepare_rgb_input_encoding:badInput', ...
            'RGB input must be an MxN, MxNx1, or MxNx3 image array.');
    end

    x = im2double(rgb);
    x = min(max(x, 0), 1);

    y = zeros(size(x));
    linear_branch = x <= 0.0031308;
    y(linear_branch) = 12.92 .* x(linear_branch);
    y(~linear_branch) = 1.055 .* x(~linear_branch).^(1 / 2.4) - 0.055;
    y = min(max(y, 0), 1);

    rgb = im2uint8(y);
    if size(rgb, 3) == 1
        rgb = repmat(rgb, [1 1 3]);
    end
end
