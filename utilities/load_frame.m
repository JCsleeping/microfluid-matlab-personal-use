function rgb = load_frame(idx, frame_index, config)
% LOAD_FRAME  Load a single frame on-demand from a TIF file.
%
%   rgb = load_frame(idx, frame_index)
%   rgb = load_frame(idx, frame_index, config)
%
%   Inputs:
%       idx         - Frame index (1-based, into frame_index)
%       frame_index - Struct array with fields:
%                       .tif_path  - path to the TIF file
%                       .page      - page number within that TIF
%       config      - Optional pipeline config with input encoding settings
%
%   Output:
%       rgb - uint8 RGB image (M x N x 3)

    tif_path = frame_index(idx).tif_path;
    page_num = frame_index(idx).page;

    try
        img = imread(tif_path, page_num);
    catch
        % Chinese path workaround: copy to temp
        [~, ~, ext] = fileparts(tif_path);
        tmp_tif = [tempname ext];
        copyfile(tif_path, tmp_tif, 'f');
        img = imread(tmp_tif, page_num);
        delete(tmp_tif);
    end

    % Handle 16-bit -> 8-bit
    if isa(img, 'uint16')
        img = im2uint8(img);
    end

    % Handle grayscale -> RGB
    if size(img, 3) == 1
        img = repmat(img, [1 1 3]);
    end

    rgb = img;
    if nargin >= 3 && ~isempty(config)
        rgb = prepare_rgb_input_encoding(rgb, config);
    end
end
