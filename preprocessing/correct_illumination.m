function [corrected, illumination_field] = correct_illumination(rgb_image, method, params, use_gpu)
% CORRECT_ILLUMINATION  Correct non-uniform illumination across an RGB image.
%
%   [corrected, illumination_field] = correct_illumination(rgb_image, method, params, use_gpu)
%
%   Inputs:
%       rgb_image  - M x N x 3 uint8 RGB image
%       method     - 'morphological' (default) or 'polynomial'
%       params     - Struct with method-specific parameters:
%                      .kernel_size  - disk SE radius (morphological, default 50)
%       use_gpu    - (optional) GPU accelerate imopen. Default false.
%                    Callers should pass config.parallel.use_gpu.
%
%   Outputs:
%       corrected        - Illumination-corrected uint8 RGB image
%       illumination_field - Estimated illumination (grayscale double)

    if nargin < 2 || isempty(method), method = 'morphological'; end
    if nargin < 3, params = struct(); end
    if nargin < 4, use_gpu = false; end

    img_double = im2double(rgb_image);

    switch lower(method)
        case 'morphological'
            kernel_size = 50;
            if isfield(params, 'kernel_size')
                kernel_size = params.kernel_size;
            end
            [corrected, illumination_field] = correct_morphological(img_double, kernel_size, use_gpu);

        case 'polynomial'
            poly_order = 3;
            if isfield(params, 'polynomial_order')
                poly_order = params.polynomial_order;
            end
            [corrected, illumination_field] = correct_polynomial(img_double, poly_order);

        otherwise
            error('correct_illumination:badMethod', ...
                'Unknown method "%s". Use "morphological" or "polynomial".', method);
    end

    corrected = im2uint8(corrected);
    fprintf('  Illumination corrected (%s method)\n', method);
end


function [corrected, illum] = correct_morphological(img, kernel_size, use_gpu)
% Estimate background illumination via morphological opening on each
% channel, then normalize. Supports optional GPU acceleration.

    if nargin < 3, use_gpu = false; end

    se = strel('disk', kernel_size);
    corrected = zeros(size(img));

    % Estimate illumination from grayscale
    gray = rgb2gray(im2uint8(img));

    % GPU acceleration for imopen (only when use_gpu=true and GPU available)
    if use_gpu
        try
            if gpuDeviceCount > 0
                g = gpuArray(gray);
                illum = im2double(gather(imopen(g, se)));
                clear g;  % release GPU memory immediately
            else
                illum = im2double(imopen(gray, se));
            end
        catch
            illum = im2double(imopen(gray, se));
        end
    else
        illum = im2double(imopen(gray, se));
    end
    illum(illum < 0.01) = 0.01;  % avoid division by zero

    mean_illum = mean(illum(:));

    for c = 1:3
        channel = img(:,:,c);
        corrected(:,:,c) = channel ./ illum * mean_illum;
    end

    % Clip to valid range
    corrected = min(max(corrected, 0), 1);
end


function [corrected, illum] = correct_polynomial(img, poly_order)
% Fit a 2D polynomial surface to the grayscale image to estimate
% background illumination.

    gray = rgb2gray(im2uint8(img));
    gray_d = im2double(gray);

    [rows, cols] = size(gray_d);

    % Adaptive step: ~100 samples along the shorter dimension
    step = max(1, round(min(rows, cols) / 100));
    [X, Y] = meshgrid(1:step:cols, 1:step:rows);
    Z = gray_d(1:step:rows, 1:step:cols);

    % Normalize coordinates to [-1, 1]
    xn = 2 * (X(:) - 1) / (cols - 1) - 1;
    yn = 2 * (Y(:) - 1) / (rows - 1) - 1;
    z  = Z(:);

    % Build Vandermonde-like matrix for 2D polynomial
    A = [];
    for i = 0:poly_order
        for j = 0:(poly_order - i)
            A = [A, (xn .^ i) .* (yn .^ j)]; %#ok<AGROW>
        end
    end

    % Least-squares fit
    coeffs = A \ z;

    % Evaluate on full grid
    [Xf, Yf] = meshgrid(1:cols, 1:rows);
    xn_full = 2 * (Xf(:) - 1) / (cols - 1) - 1;
    yn_full = 2 * (Yf(:) - 1) / (rows - 1) - 1;

    A_full = [];
    for i = 0:poly_order
        for j = 0:(poly_order - i)
            A_full = [A_full, (xn_full .^ i) .* (yn_full .^ j)]; %#ok<AGROW>
        end
    end

    illum = reshape(A_full * coeffs, rows, cols);
    illum(illum < 0.01) = 0.01;

    mean_illum = mean(illum(:));

    corrected = zeros(size(img));
    for c = 1:3
        corrected(:,:,c) = img(:,:,c) ./ illum * mean_illum;
    end
    corrected = min(max(corrected, 0), 1);
end
