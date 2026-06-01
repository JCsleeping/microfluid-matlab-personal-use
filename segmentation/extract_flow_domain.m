function [flow_domain, solid_mask, info] = extract_flow_domain(ref_image, chip_mask, config)
% EXTRACT_FLOW_DOMAIN  Generate binary pore-space mask from a reference image.
%
%   [flow_domain, solid_mask] = extract_flow_domain(ref_image)
%   [flow_domain, solid_mask] = extract_flow_domain(ref_image, chip_mask)
%   [flow_domain, solid_mask] = extract_flow_domain(ref_image, chip_mask, config)
%   [flow_domain, solid_mask, info] = extract_flow_domain(...)
%
%   Detection strategy:
%     1. Optional mask override from a binary image/MAT file or DXF.
%     2. Lab color-based: Uses a* channel to detect DNAPL (pink).
%        Pillars = bright non-DNAPL pixels. Best with DNAPL-saturated frame.
%     3. Morphological fallback: Multi-scale top-hat/bottom-hat.
%        Used when reference has no color contrast (clean/water image).
%
%   Inputs:
%       ref_image   - M x N x 3 uint8 RGB image (preprocessed)
%       chip_mask   - (optional) M x N logical mask defining chip interior.
%       config      - (optional) Pipeline configuration struct.
%
%   Outputs:
%       flow_domain - M x N logical (1 = pore space, 0 = solid)
%       solid_mask  - M x N logical (1 = solid pillar, 0 = pore)
%       info        - Provenance for Lab conversion and extraction method

    [H, W, ~] = size(ref_image);
    if nargin < 2
        chip_mask = [];
    end
    if nargin < 3
        config = struct();
    end
    info = default_flow_domain_info(config);

    %% Detection parameters
    P = flow_domain_detection_params(config);
    P.MORPH_RADII          = [3, 5, 8, 10, 15, 20, 25, 30, 40, 50];
    P.MIN_BLOB_AREA_COLOR  = 2;      % color method (minimal to catch tiny pillars)
    P.MIN_BLOB_AREA_MORPH  = 3;      % morphological method (minimal to catch tiny pillars)
    P.QUANTILE_RANGE       = 65:2:98;

    %% Step 1: Determine chip interior
    if nargin >= 2 && ~isempty(chip_mask)
        chip_interior = logical(chip_mask);
        fprintf('  Using user-provided chip mask (%d pixels)\n', sum(chip_interior(:)));
    else
        gray = rgb2gray(ref_image);
        level = graythresh(gray);
        auto_mask = imbinarize(gray, level * 0.85);
        auto_mask = imclose(auto_mask, strel('disk', 15));
        auto_mask = imfill(auto_mask, 'holes');
        auto_mask = bwareaopen(auto_mask, round(H * W * 0.01));

        cc = bwconncomp(auto_mask);
        if cc.NumObjects > 1
            sizes = cellfun(@numel, cc.PixelIdxList);
            [~, idx] = max(sizes);
            auto_mask = false(H, W);
            auto_mask(cc.PixelIdxList{idx}) = true;
        end
        auto_mask = imfill(auto_mask, 'holes');
        chip_interior = imerode(auto_mask, strel('disk', 5));
    end

    if sum(chip_interior(:)) < 100
        solid_mask = false(H, W);
        flow_domain = chip_interior;
        info.method = 'chip_too_small';
        info.porosity = NaN;
        info.pillar_fraction = NaN;
        info.qc_status = 'not_run';
        info.qc_message = 'Chip mask contains fewer than 100 pixels.';
        fprintf('  Flow domain: chip too small\n');
        return;
    end

    total_chip = sum(chip_interior(:));
    requested_method = get_requested_flow_domain_method(config);

    if strcmp(requested_method, 'mask')
        [flow_domain, solid_mask, chip_interior, info] = ...
            load_flow_domain_mask_override([H W], chip_interior, ...
            config, info, ref_image);
        info = validate_flow_domain_qc(flow_domain, solid_mask, ...
            chip_interior, config, info);
        print_flow_domain_summary(H, W, solid_mask, info);
        show_mask_override_diagnostics(ref_image, chip_interior, ...
            solid_mask, info);
        return;
    end

    %% Step 2: Check for DNAPL color in Lab space
    [rgb_for_lab, rgb_encoding] = prepare_rgb_for_lab(ref_image, config);
    info.rgb_encoding = rgb_encoding;
    lab = rgb2lab(rgb_for_lab);
    L_ch = lab(:,:,1);   % Lightness [0, 100]
    a_ch = lab(:,:,2);   % green-red axis; positive = red/pink

    a_vals = a_ch(chip_interior);
    a_p5 = prctile(a_vals, 5);
    a_p95 = prctile(a_vals, 95);
    a_range = a_p95 - a_p5;
    info.a_range = a_range;
    info.a_p5 = a_p5;
    info.a_p95 = a_p95;
    info.a_median = median(a_vals);
    info.color_contrast_min = P.COLOR_CONTRAST_MIN;
    info.morph_contrast_min = P.MORPH_CONTRAST_MIN;
    info.otsu_min_frac = P.OTSU_MIN_FRAC;
    info.otsu_max_frac = P.OTSU_MAX_FRAC;

    fprintf('  Lab a* stats: range=%.1f, p5=%.1f, p95=%.1f, median=%.1f\n', ...
        a_range, info.a_p5, info.a_p95, info.a_median);

    if strcmp(requested_method, 'morphological')
        fprintf('  Flow-domain method forced to morphological.\n');
        info.method = 'morphological_forced';
        solid_mask = detect_pillars_morphological(ref_image, chip_interior, total_chip, P);
    elseif strcmp(requested_method, 'white_pillars')
        fprintf('  Flow-domain method forced to white_pillars.\n');
        info.method = 'white_pillars_forced';
        solid_mask = detect_pillars_white_local(L_ch, chip_interior, total_chip, P);
    elseif a_range > P.COLOR_CONTRAST_MIN || strcmp(requested_method, 'lab_color')
        info.method = 'lab_color';
        info.color_contrast_status = 'above_threshold';
        solid_mask = detect_pillars_color(a_ch, L_ch, chip_interior, total_chip, P);
        color_frac = sum(solid_mask(:)) / max(total_chip, 1);

        % Guardrail: if color segmentation is implausible, try morphological fallback.
        if color_frac < P.MIN_PILLAR_FRAC || color_frac > P.MAX_PILLAR_FRAC
            fprintf('  Color-based result %.1f%% is implausible. Trying morphological fallback...\n', ...
                color_frac * 100);
            solid_mask_morph = detect_pillars_morphological(ref_image, chip_interior, total_chip, P);
            morph_frac = sum(solid_mask_morph(:)) / max(total_chip, 1);

            if (morph_frac >= P.MIN_PILLAR_FRAC && morph_frac <= P.MAX_PILLAR_FRAC) || ...
                    (color_frac < P.MIN_PILLAR_FRAC && morph_frac > color_frac + 0.01 && morph_frac < 0.85)
                solid_mask = solid_mask_morph;
                info.method = 'morphological_fallback';
                fprintf('  Using morphological fallback result: %.1f%% pillars\n', ...
                    morph_frac * 100);
            else
                fprintf('  Keeping color-based result (fallback=%.1f%% not better)\n', ...
                    morph_frac * 100);
            end
        end
    else
        info.color_contrast_status = 'below_threshold';
        fprintf(['  Low color contrast (a* range=%.1f <= %.1f). ' ...
            'Trying white-pillar detection.\n'], a_range, P.COLOR_CONTRAST_MIN);
        solid_white = detect_pillars_white_local(L_ch, chip_interior, total_chip, P);
        white_frac = sum(solid_white(:)) / max(total_chip, 1);
        if white_frac >= P.MIN_PILLAR_FRAC && white_frac <= P.MAX_PILLAR_FRAC
            info.method = 'white_pillars_low_contrast';
            solid_mask = solid_white;
            fprintf('  Using white-pillar result: %.1f%% pillars\n', white_frac * 100);
        else
            fprintf('  White-pillar result %.1f%% not plausible. Using morphological method.\n', ...
                white_frac * 100);
            info.method = 'morphological_low_contrast';
            solid_mask = detect_pillars_morphological(ref_image, chip_interior, total_chip, P);
        end
    end

    %% Build flow domain
    flow_domain = chip_interior & ~solid_mask;

    %% Report
    info = validate_flow_domain_qc(flow_domain, solid_mask, chip_interior, config, info);
    pillar_fraction = info.pillar_fraction;
    porosity = info.porosity;

    print_flow_domain_summary(H, W, solid_mask, info);

    if pillar_fraction < P.WARN_PILLAR_FRAC
        fprintf('  WARNING: pillar fraction very low.\n');
        fprintf('    Use a DNAPL-saturated frame (flow_domain_frame = 1) for best results.\n');
    end

    %% Diagnostic figure
    figure('Name', 'Flow Domain Extraction - Diagnostics', ...
        'Position', [50 50 1500 700], 'Color', 'w');

    subplot(2,3,1);
    imshow(ref_image);
    title('Input to extract\_flow\_domain', 'FontSize', 11);

    subplot(2,3,2);
    imagesc(a_ch); colormap(gca, 'jet'); colorbar;
    hold on;
    boundary = bwperim(chip_interior);
    [yy, xx] = find(boundary);
    if ~isempty(xx)
        plot(xx, yy, 'w.', 'MarkerSize', 1);
    end
    title(sprintf('Lab a* (range=%.1f)', a_range), 'FontSize', 11);
    axis image off;

    subplot(2,3,3);
    histogram(a_vals, 100);
    xlabel('a* value'); ylabel('Count');
    title('a* distribution (chip only)', 'FontSize', 11);

    subplot(2,3,4);
    imshow(chip_interior);
    title(sprintf('chip\\_interior (%d px)', sum(chip_interior(:))), 'FontSize', 11);

    subplot(2,3,5);
    imshow(solid_mask);
    title(sprintf('solid\\_mask (%d px, %.1f%%)', ...
        sum(solid_mask(:)), pillar_fraction*100), 'FontSize', 11);

    subplot(2,3,6);
    overlay = im2double(ref_image);
    for c = 1:3
        ch = overlay(:,:,c);
        ch(solid_mask) = (c == 1);  % red for pillars
        overlay(:,:,c) = ch;
    end
    imshow(overlay);
    title(sprintf('Pillars (red) | porosity=%.1f%%', porosity*100), 'FontSize', 11);

    method_str = sprintf('%s (a* range=%.1f)', info.method, a_range);
    sgtitle(['Flow Domain Diagnostics — method: ' method_str], ...
        'FontSize', 14, 'FontWeight', 'bold');
end


function method = get_requested_flow_domain_method(config)
    method = 'auto';
    if isstruct(config) && isfield(config, 'flow_domain') && ...
            isstruct(config.flow_domain) && ...
            isfield(config.flow_domain, 'extraction_method') && ...
            ~isempty(config.flow_domain.extraction_method)
        method = char(string(config.flow_domain.extraction_method));
    end
    if ~ismember(method, {'auto', 'lab_color', 'morphological', ...
            'white_pillars', 'mask'})
        error('extract_flow_domain:badExtractionMethod', ...
            ['flow_domain.extraction_method must be auto, lab_color, morphological, ' ...
             'white_pillars, or mask, got "%s".'], ...
            method);
    end
end


function info = default_flow_domain_info(config)
    rgb_encoding = 'srgb';
    if isstruct(config) && isfield(config, 'preprocessing') && ...
            isstruct(config.preprocessing) && ...
            isfield(config.preprocessing, 'rgb_encoding') && ...
            ~isempty(config.preprocessing.rgb_encoding)
        rgb_encoding = normalize_rgb_encoding(config.preprocessing.rgb_encoding);
    end
    info = struct( ...
        'rgb_encoding', rgb_encoding, ...
        'lab_input_encoding', 'srgb_after_prepare_rgb_for_lab', ...
        'a_range', NaN, ...
        'a_p5', NaN, ...
        'a_p95', NaN, ...
        'a_median', NaN, ...
        'color_contrast_min', NaN, ...
        'morph_contrast_min', NaN, ...
        'color_contrast_status', '', ...
        'method', 'not_run');
end


function P = flow_domain_detection_params(config)
    P = struct();
    P.COLOR_CONTRAST_MIN = read_flow_domain_param(config, 'color_contrast_min', 5);
    P.MORPH_CONTRAST_MIN = read_flow_domain_param(config, 'morph_contrast_min', 0.003);
    P.MIN_PILLAR_FRAC = read_flow_domain_param(config, 'min_pillar_frac', 0.03);
    P.MAX_PILLAR_FRAC = read_flow_domain_param(config, 'max_pillar_frac', 0.70);
    P.WARN_PILLAR_FRAC = read_flow_domain_param(config, 'warn_pillar_frac', 0.05);
    P.OTSU_MIN_FRAC = read_flow_domain_param(config, 'otsu_min_frac', 0.05);
    P.OTSU_MAX_FRAC = read_flow_domain_param(config, 'otsu_max_frac', 0.60);
    P.BRIGHT_MIN_FRAC = read_flow_domain_param(config, 'bright_min_frac', 0.08);
    P.BRIGHT_MAX_FRAC = read_flow_domain_param(config, 'bright_max_frac', 0.55);
    P.QUANTILE_MIN_FRAC = read_flow_domain_param(config, ...
        'quantile_min_frac', 0.05);
    P.QUANTILE_MAX_FRAC = read_flow_domain_param(config, ...
        'quantile_max_frac', 0.45);
    P.TARGET_PILLAR_FRAC = read_flow_domain_param(config, ...
        'target_pillar_frac', 0.18);
    P.MAX_PILLAR_AREA_FRAC = read_flow_domain_param(config, ...
        'max_pillar_area_frac', 0.05);
    P.WHITE_PILLAR_SENSITIVITY = read_flow_domain_param(config, ...
        'white_pillar_sensitivity', 0.45);
    P.WHITE_PILLAR_NEIGHBORHOOD_PX = read_flow_domain_param(config, ...
        'white_pillar_neighborhood_px', 41);
    P.WHITE_PILLAR_MIN_AREA_PX = read_flow_domain_param(config, ...
        'white_pillar_min_area_px', 4);
    P.WHITE_PILLAR_MAX_AREA_PX = read_flow_domain_param(config, ...
        'white_pillar_max_area_px', inf);
    P.WHITE_PILLAR_MIN_CIRCULARITY = read_flow_domain_param(config, ...
        'white_pillar_min_circularity', 0.15);
end


function value = read_flow_domain_param(config, field_name, default_value)
    value = default_value;
    if isstruct(config) && isfield(config, 'flow_domain') && ...
            isstruct(config.flow_domain) && isfield(config.flow_domain, field_name) && ...
            ~isempty(config.flow_domain.(field_name))
        value = config.flow_domain.(field_name);
    end
end


function [flow_domain, solid_mask, chip_interior, info] = load_flow_domain_mask_override( ...
        target_size, chip_interior, config, info, ref_image)
    if nargin < 5, ref_image = []; end
    [mask_path, mask_role] = get_mask_override_path(config);
    [mask, source_format, mask_info] = read_mask_override(mask_path, ...
        target_size, config, ref_image);

    chip_interior = logical(chip_interior);
    dxf_chip_mask_applied = false;
    if isfield(mask_info, 'chip_mask') && ~isempty(mask_info.chip_mask)
        chip_interior = chip_interior & logical(mask_info.chip_mask);
        mask_info = rmfield(mask_info, 'chip_mask');
        dxf_chip_mask_applied = true;
    end
    switch mask_role
        case 'solid'
            solid_mask = mask & chip_interior;
            flow_domain = chip_interior & ~solid_mask;
            if strcmp(source_format, 'dxf')
                info.method = 'dxf_solid_mask_override';
            else
                info.method = 'solid_mask_override';
            end
        case 'flow_domain'
            flow_domain = mask & chip_interior;
            solid_mask = chip_interior & ~flow_domain;
            info.method = 'flow_domain_mask_override';
        otherwise
            error('extract_flow_domain:badMaskRole', ...
                'Unsupported flow-domain mask role "%s".', mask_role);
    end

    info.color_contrast_status = 'mask_override';
    info.mask_path = char(mask_path);
    info.mask_role = mask_role;
    info.mask_source_format = source_format;
    info.mask_resized = mask_info.resized;
    info.mask_input_size = mask_info.input_size;
    info.mask_target_size = target_size;
    info.dxf_chip_mask_applied = dxf_chip_mask_applied;
    info = merge_struct_fields(info, mask_info);

    fprintf('  Flow-domain method forced to mask override.\n');
    fprintf('  Mask path: %s\n', char(mask_path));
    fprintf('  Mask role: %s (%s)\n', mask_role, source_format);
end


function [mask_path, mask_role] = get_mask_override_path(config)
    solid_path = string(read_flow_domain_param(config, 'solid_mask_path', ''));
    flow_path = string(read_flow_domain_param(config, 'flow_domain_mask_path', ''));
    if strlength(solid_path) > 0 && strlength(flow_path) > 0
        error('extract_flow_domain:ambiguousMaskPath', ...
            ['Set only one of flow_domain.solid_mask_path or ' ...
             'flow_domain.flow_domain_mask_path.']);
    end
    if strlength(solid_path) > 0
        mask_path = solid_path;
        mask_role = 'solid';
        return;
    end
    if strlength(flow_path) > 0
        mask_path = flow_path;
        mask_role = 'flow_domain';
        return;
    end
    error('extract_flow_domain:missingMaskPath', ...
        ['flow_domain.extraction_method = ''mask'' requires ' ...
         'flow_domain.solid_mask_path or flow_domain.flow_domain_mask_path.']);
end


function [mask, source_format, info] = read_mask_override(mask_path, ...
        target_size, config, ref_image)
    if nargin < 4, ref_image = []; end
    path_char = char(mask_path);
    if ~exist(path_char, 'file')
        error('extract_flow_domain:maskNotFound', ...
            'Flow-domain mask file not found: %s', path_char);
    end

    [~, ~, ext] = fileparts(path_char);
    ext = lower(ext);
    switch ext
        case {'.png', '.tif', '.tiff', '.bmp', '.jpg', '.jpeg'}
            mask = read_image_mask(path_char);
            source_format = 'image';
            info = struct();
        case '.mat'
            mask = read_mat_mask(path_char);
            source_format = 'mat';
            info = struct();
        case '.dxf'
            [mask, info] = rasterize_dxf_solid_mask(path_char, ...
                target_size, config, ref_image);
            source_format = 'dxf';
        otherwise
            error('extract_flow_domain:unsupportedMaskFormat', ...
                'Unsupported flow-domain mask format "%s".', ext);
    end

    mask_grid = char(string(read_flow_domain_param(config, ...
        'mask_grid', 'target')));
    if strcmp(mask_grid, 'native_full') && ~strcmp(source_format, 'dxf')
        [mask, crop_rect] = crop_native_full_mask(mask, config);
        info.mask_crop_rect = crop_rect;
    end

    input_size = size(mask);
    if numel(input_size) > 2
        input_size = input_size(1:2);
    end
    resized = ~isequal(input_size, target_size);
    if resized
        mask = resize_logical_mask(mask, target_size, config);
    else
        mask = logical(mask);
    end

    info.input_size = input_size;
    info.resized = resized;
    info.mask_grid = mask_grid;
end


function [mask, crop_rect] = crop_native_full_mask(mask, config)
    crop_rect = [];
    if isstruct(config) && isfield(config, 'preprocess') && ...
            isstruct(config.preprocess)
        if isfield(config.preprocess, 'saved_crop_rect') && ...
                isnumeric(config.preprocess.saved_crop_rect) && ...
                numel(config.preprocess.saved_crop_rect) == 4
            crop_rect = config.preprocess.saved_crop_rect;
        elseif isfield(config.preprocess, 'manual_crop_rect') && ...
                isnumeric(config.preprocess.manual_crop_rect) && ...
                numel(config.preprocess.manual_crop_rect) == 4
            crop_rect = config.preprocess.manual_crop_rect;
        end
    end
    if isempty(crop_rect)
        error('extract_flow_domain:missingMaskCropRect', ...
            ['flow_domain.mask_grid="native_full" requires ' ...
             'preprocess.saved_crop_rect or preprocess.manual_crop_rect.']);
    end
    crop_rect = clip_mask_crop_rect(crop_rect, size(mask));
    mask = imcrop(mask, crop_rect) > 0;
end


function crop_rect = clip_mask_crop_rect(crop_rect, mask_size)
    x = max(1, round(crop_rect(1)));
    y = max(1, round(crop_rect(2)));
    w = max(1, round(crop_rect(3)));
    h = max(1, round(crop_rect(4)));
    x = min(x, mask_size(2));
    y = min(y, mask_size(1));
    w = min(w, mask_size(2) - x + 1);
    h = min(h, mask_size(1) - y + 1);
    crop_rect = [x, y, w, h];
end


function mask = read_image_mask(path)
    raw = imread(path);
    if ndims(raw) == 3
        mask = any(raw > 0, 3);
    else
        mask = raw > 0;
    end
end


function mask = read_mat_mask(path)
    loaded = load(path);
    preferred_names = {'solid_mask', 'flow_domain', 'flow_domain_mask', 'mask'};
    for i = 1:numel(preferred_names)
        name = preferred_names{i};
        if isfield(loaded, name) && is_mask_like(loaded.(name))
            mask = logical(loaded.(name));
            return;
        end
    end

    names = fieldnames(loaded);
    for i = 1:numel(names)
        value = loaded.(names{i});
        if is_mask_like(value)
            mask = logical(value);
            return;
        end
    end
    error('extract_flow_domain:noMaskVariable', ...
        'MAT mask file must contain a 2-D logical or numeric mask.');
end


function tf = is_mask_like(value)
    tf = (islogical(value) || isnumeric(value)) && ismatrix(value) && ...
        ~isempty(value);
end


function mask = resize_logical_mask(mask, target_size, config)
    method = char(string(read_flow_domain_param(config, ...
        'mask_resize_method', 'nearest')));
    if ~strcmp(method, 'nearest')
        error('extract_flow_domain:badMaskResizeMethod', ...
            'Only nearest-neighbor mask resizing is supported.');
    end
    mask = imresize(double(mask), target_size, method) > 0.5;
end


function [mask, info] = rasterize_dxf_solid_mask(path, target_size, config, ref_image)
    if nargin < 4, ref_image = []; end
    [circles, polylines] = read_dxf_entities(path);
    if isempty(circles)
        error('extract_flow_domain:noDxfSolids', ...
            'DXF mask conversion requires at least one CIRCLE solid entity.');
    end

    circle_rows = unique([[circles.x]' [circles.y]' [circles.r]'], 'rows');
    circles = struct( ...
        'x', num2cell(circle_rows(:,1)), ...
        'y', num2cell(circle_rows(:,2)), ...
        'r', num2cell(circle_rows(:,3)), ...
        'layer', repmat({''}, size(circle_rows, 1), 1));

    alignment_mode = char(string(read_flow_domain_param(config, ...
        'dxf_alignment_mode', 'bbox')));

    switch alignment_mode
        case 'control_points'
            [mask, info] = rasterize_dxf_control_points_mode( ...
                circles, polylines, target_size, config, ref_image);
        otherwise
            [mask, info] = rasterize_dxf_bbox_mode( ...
                circles, polylines, target_size, config);
    end
    info.dxf_alignment_mode = alignment_mode;
end


function [circles, polylines] = read_dxf_entities(path)
    raw = regexp(fileread(path), '\r\n|\n|\r', 'split');
    pair_count = floor(numel(raw) / 2);
    circles = struct('x', {}, 'y', {}, 'r', {}, 'layer', {});
    polylines = struct('x', {}, 'y', {}, 'closed', {}, 'layer', {});
    in_entities = false;
    entity = empty_dxf_entity('');

    for idx = 1:pair_count
        code = strtrim(raw{2 * idx - 1});
        value = strtrim(raw{2 * idx});
        if strcmp(code, '2') && strcmp(value, 'ENTITIES')
            in_entities = true;
            continue;
        end
        if ~in_entities
            continue;
        end
        if strcmp(code, '0') && strcmp(value, 'ENDSEC')
            [circles, polylines] = append_dxf_entity(circles, ...
                polylines, entity);
            break;
        end
        if strcmp(code, '0')
            [circles, polylines] = append_dxf_entity(circles, ...
                polylines, entity);
            entity = empty_dxf_entity(value);
            continue;
        end
        entity = collect_dxf_entity_code(entity, code, value);
    end
end


function entity = empty_dxf_entity(type)
    entity = struct('type', type, 'layer', '', 'x', [], 'y', [], ...
        'r', NaN, 'flags', 0);
end


function entity = collect_dxf_entity_code(entity, code, value)
    if isempty(entity.type)
        return;
    end
    switch code
        case '8'
            entity.layer = value;
        case '10'
            entity.x(end+1) = str2double(value);
        case '20'
            entity.y(end+1) = str2double(value);
        case '40'
            entity.r = str2double(value);
        case '70'
            entity.flags = str2double(value);
    end
end


function [circles, polylines] = append_dxf_entity(circles, polylines, entity)
    switch entity.type
        case 'CIRCLE'
            if ~isempty(entity.x) && ~isempty(entity.y) && ...
                    isfinite(entity.x(1)) && isfinite(entity.y(1)) && ...
                    isfinite(entity.r) && entity.r > 0
                circles(end+1) = struct( ... %#ok<AGROW>
                    'x', entity.x(1), ...
                    'y', entity.y(1), ...
                    'r', entity.r, ...
                    'layer', entity.layer);
            end
        case 'LWPOLYLINE'
            n = min(numel(entity.x), numel(entity.y));
            if n >= 3
                polylines(end+1) = struct( ... %#ok<AGROW>
                    'x', entity.x(1:n), ...
                    'y', entity.y(1:n), ...
                    'closed', bitand(uint16(entity.flags), uint16(1)) ~= 0, ...
                    'layer', entity.layer);
            end
    end
end


function [bbox, boundary_index] = select_dxf_fit_bbox(circles, polylines, mode)
    circle_x = [circles.x]';
    circle_y = [circles.y]';
    circle_r = [circles.r]';
    circle_bbox = [min(circle_x - circle_r), min(circle_y - circle_r), ...
        max(circle_x + circle_r), max(circle_y + circle_r)];

    boundary_index = 0;
    switch mode
        case 'circle_bbox'
            bbox = circle_bbox;
            return;
        case 'largest_closed_polyline'
            best_area = -inf;
            for i = 1:numel(polylines)
                if ~polylines(i).closed
                    continue;
                end
                area = polyarea(polylines(i).x, polylines(i).y);
                if area > best_area
                    best_area = area;
                    boundary_index = i;
                end
            end
        otherwise
            best_area = inf;
            for i = 1:numel(polylines)
                if ~polylines(i).closed
                    continue;
                end
                inside = inpolygon(circle_x, circle_y, ...
                    polylines(i).x, polylines(i).y);
                if ~all(inside)
                    continue;
                end
                area = polyarea(polylines(i).x, polylines(i).y);
                if area < best_area
                    best_area = area;
                    boundary_index = i;
                end
            end
    end

    if boundary_index == 0
        bbox = circle_bbox;
    else
        x = polylines(boundary_index).x;
        y = polylines(boundary_index).y;
        bbox = [min(x), min(y), max(x), max(y)];
    end
end


function mask = rasterize_dxf_polyline_mask(polyline, bbox, target_size)
    H = target_size(1);
    W = target_size(2);
    sx = (W - 1) / (bbox(3) - bbox(1));
    sy = (H - 1) / (bbox(4) - bbox(2));
    x = 1 + (polyline.x - bbox(1)) * sx;
    y = 1 + (bbox(4) - polyline.y) * sy;
    mask = poly2mask(x, y, H, W);
end


function [mask, info] = rasterize_dxf_bbox_mode(circles, polylines, target_size, config)
% Original bbox-based DXF rasterization (backward-compatible mode).
    boundary_mode = char(string(read_flow_domain_param(config, ...
        'dxf_boundary_mode', 'smallest_containing_circles')));
    [bbox, boundary_index] = select_dxf_fit_bbox(circles, polylines, ...
        boundary_mode);
    if bbox(3) <= bbox(1) || bbox(4) <= bbox(2)
        error('extract_flow_domain:badDxfBounds', ...
            'DXF bounds are degenerate and cannot be rasterized.');
    end

    H = target_size(1); W = target_size(2);
    sx = (W - 1) / (bbox(3) - bbox(1));
    sy = (H - 1) / (bbox(4) - bbox(2));
    mask = false(H, W);

    for i = 1:numel(circles)
        if ~isfinite(circles(i).r) || circles(i).r <= 0, continue; end
        cx = 1 + (circles(i).x - bbox(1)) * sx;
        cy = 1 + (bbox(4) - circles(i).y) * sy;
        rx = max(circles(i).r * sx, 0.5);
        ry = max(circles(i).r * sy, 0.5);
        c0 = max(1, floor(cx - rx - 1));  c1 = min(W, ceil(cx + rx + 1));
        r0 = max(1, floor(cy - ry - 1));  r1 = min(H, ceil(cy + ry + 1));
        if c0 > c1 || r0 > r1, continue; end
        [yy, xx] = ndgrid(r0:r1, c0:c1);
        disk = ((xx - cx) ./ rx).^2 + ((yy - cy) ./ ry).^2 <= 1;
        sub = mask(r0:r1, c0:c1); sub(disk) = true;
        mask(r0:r1, c0:c1) = sub;
    end

    chip_mask = [];
    if boundary_index > 0
        chip_mask = rasterize_dxf_polyline_mask(polylines(boundary_index), ...
            bbox, target_size);
    end
    info = struct('dxf_circle_count', numel(circles), ...
        'dxf_polyline_count', numel(polylines), ...
        'dxf_boundary_mode', boundary_mode, ...
        'dxf_boundary_index', boundary_index, ...
        'dxf_fit_bbox', bbox, 'chip_mask', chip_mask);
end


function [mask, info] = rasterize_dxf_control_points_mode( ...
        circles, polylines, target_size, config, ref_image)
% Control-point-based DXF rasterization using affine alignment.
    circle_x = [circles.x]';  circle_y = [circles.y]';
    circle_r = [circles.r]';

    % Find the hexagonal boundary polyline (smallest containing all circles)
    boundary_index = find_hex_boundary_polyline(circles, polylines);
    hex_poly = polylines(boundary_index);

    % Extract the 6 hexagonal corners from the boundary polyline
    [hex_corners, corner_labels] = extract_hex_corners(hex_poly);

    % Get saved control points or prompt interactive selection
    control_pts_img = read_flow_domain_param(config, ...
        'dxf_control_points_image', []);
    if isempty(control_pts_img) || ...
            size(control_pts_img, 1) ~= size(hex_corners, 1)
        if isempty(ref_image)
            error('extract_flow_domain:noControlPoints', ...
                ['DXF control_points alignment requires either ' ...
                 'config.flow_domain.dxf_control_points_image or ' ...
                 'a reference image for interactive selection.']);
        end
        control_pts_img = select_dxf_control_points(ref_image, ...
            hex_corners, corner_labels);
        % Print for user to copy into config
        fprintf('\n  >>> Save these control points to skip interactive selection:\n');
        fprintf('    config.flow_domain.dxf_control_points_image = [\n');
        for k = 1:size(control_pts_img, 1)
            fprintf('      %.1f, %.1f', control_pts_img(k,1), control_pts_img(k,2));
            if k < size(control_pts_img, 1), fprintf('; ...'); end
            fprintf('  %% %s\n', corner_labels{k});
        end
        fprintf('    ];\n\n');
    end

    % Compute DXF->image transform. Affine (6 DOF) is the default; projective
    % (homography, 8 DOF) absorbs perspective/keystone when an affine cannot
    % bring the control-point residual down (e.g. camera not perpendicular).
    transform_model = lower(char(string(read_flow_domain_param(config, ...
        'dxf_transform_model', 'affine'))));
    Himg = target_size(1);  Wimg = target_size(2);

    switch transform_model
        case 'projective'
            [Tform, residual] = compute_dxf_projective(hex_corners, control_pts_img);
            fprintf('  DXF projective alignment: %d control points, residual = %.2f px\n', ...
                size(hex_corners, 1), residual);
            mask      = rasterize_circles_projective(circles, Tform, Himg, Wimg);
            chip_mask = rasterize_polyline_projective(hex_poly, Tform, Himg, Wimg);
        case 'affine'
            [Tform, residual] = compute_dxf_affine(hex_corners, control_pts_img);
            fprintf('  DXF affine alignment: %d control points, residual = %.2f px\n', ...
                size(hex_corners, 1), residual);
            mask      = rasterize_circles_affine(circles, Tform, Himg, Wimg);
            chip_mask = rasterize_polyline_affine(hex_poly, Tform, Himg, Wimg);
        otherwise
            error('extract_flow_domain:unknownTransformModel', ...
                ['Unknown flow_domain.dxf_transform_model "%s". ' ...
                 'Use "affine" or "projective".'], transform_model);
    end

    if residual > 20
        warning('extract_flow_domain:highAffineResidual', ...
            'DXF %s residual (%.1f px) is high. Check control points.', ...
            transform_model, residual);
    end

    fit_bbox = [min(circle_x - circle_r), min(circle_y - circle_r), ...
        max(circle_x + circle_r), max(circle_y + circle_r)];
    info = struct('dxf_circle_count', numel(circles), ...
        'dxf_polyline_count', numel(polylines), ...
        'dxf_boundary_index', boundary_index, ...
        'dxf_fit_bbox', fit_bbox, ...
        'dxf_affine_residual', residual, ...
        'dxf_transform_model', transform_model, ...
        'dxf_control_points_dxf', hex_corners, ...
        'dxf_control_points_image', control_pts_img, ...
        'chip_mask', chip_mask);
end


function boundary_index = find_hex_boundary_polyline(circles, polylines)
% Find the smallest closed polyline that contains all circle centers.
    cx = [circles.x]';  cy = [circles.y]';
    best_area = inf;  boundary_index = 0;
    for i = 1:numel(polylines)
        if ~polylines(i).closed, continue; end
        n = min(numel(polylines(i).x), numel(polylines(i).y));
        inside = inpolygon(cx, cy, polylines(i).x(1:n), polylines(i).y(1:n));
        if ~all(inside), continue; end
        a = polyarea(polylines(i).x(1:n), polylines(i).y(1:n));
        if a < best_area
            best_area = a;  boundary_index = i;
        end
    end
    if boundary_index == 0
        error('extract_flow_domain:noHexBoundary', ...
            'No closed polyline found that contains all DXF circles.');
    end
end


function [hex_corners, labels] = extract_hex_corners(polyline)
% Extract 6 main hexagonal corners from a 12-vertex polyline with channel slits.
%   Returns corners sorted clockwise from upper-left (in DXF Y-up convention)
%   with descriptive labels for each.
    n = min(numel(polyline.x), numel(polyline.y));
    px = polyline.x(1:n);  py = polyline.y(1:n);

    xmin_v = min(px);  xmax_v = max(px);
    tol_x = (xmax_v - xmin_v) * 0.02;

    % Channel endpoint vertices sit at the extreme x positions — remove them
    keep = (abs(px - xmin_v) >= tol_x) & (abs(px - xmax_v) >= tol_x);
    kx = px(keep);  ky = py(keep);

    if numel(kx) < 6
        warning('extract_flow_domain:hexCornerFallback', ...
            'Cannot isolate channel endpoints; using all %d polyline vertices.', n);
        kx = px;  ky = py;
    end

    % Group remaining vertices by x. Pairs with small delta-y are channel
    % junctions and get merged to their midpoint; pairs with large delta-y
    % are two separate hex corners.
    y_range = max(ky) - min(ky);
    y_tol = y_range * 0.15;
    used = false(numel(kx), 1);
    corners = zeros(0, 2);

    for i = 1:numel(kx)
        if used(i), continue; end
        pair = find(abs(kx(:) - kx(i)) < tol_x & ~used & (1:numel(kx))' ~= i);
        if ~isempty(pair)
            j = pair(1);
            if abs(ky(i) - ky(j)) < y_tol
                corners(end+1,:) = [(kx(i)+kx(j))/2, (ky(i)+ky(j))/2]; %#ok<AGROW>
            else
                corners(end+1,:) = [kx(i), ky(i)]; %#ok<AGROW>
                corners(end+1,:) = [kx(j), ky(j)]; %#ok<AGROW>
            end
            used(i) = true;  used(j) = true;
        else
            corners(end+1,:) = [kx(i), ky(i)]; %#ok<AGROW>
            used(i) = true;
        end
    end

    if size(corners,1) > 6
        corners = corners(1:6,:);
    end
    if size(corners,1) ~= 6
        warning('extract_flow_domain:hexCornerCount', ...
            'Expected 6 hex corners, found %d.', size(corners,1));
    end

    % Sort clockwise from upper-left.
    % Upper-left = smallest x among points clearly above centre.
    mx = mean(corners(:,1));  my = mean(corners(:,2));
    y_half = y_range * 0.25;  % threshold to exclude mid-height channel openings
    top_half = corners(:,2) > my + y_half;
    if any(top_half)
        top_x = corners(:,1);  top_x(~top_half) = inf;
        [~, ul] = min(top_x);                          % smallest x in upper quarter
    else
        [~, ul] = max(corners(:,2));                    % fallback: topmost point
    end
    angles = atan2(corners(:,2)-my, corners(:,1)-mx);
    cw_dist = mod(angles(ul) - angles, 2*pi);
    [~, order] = sort(cw_dist);
    hex_corners = corners(order,:);

    % Generate position-based labels
    labels = cell(size(hex_corners,1), 1);
    for i = 1:size(hex_corners,1)
        dx = hex_corners(i,1) - mx;
        dy = hex_corners(i,2) - my;
        if abs(dy) < y_range * 0.12
            if dx > 0, labels{i} = 'Right channel opening';
            else,      labels{i} = 'Left channel opening'; end
        elseif dy > 0
            if dx < 0, labels{i} = 'Upper-left corner';
            else,      labels{i} = 'Upper-right corner'; end
        else
            if dx < 0, labels{i} = 'Lower-left corner';
            else,      labels{i} = 'Lower-right corner'; end
        end
    end
end


function [T, residual] = compute_dxf_affine(dxf_pts, img_pts)
% Least-squares 2-D affine: [col;row] = T * [x_dxf; y_dxf; 1]
    n = size(dxf_pts, 1);
    A = [dxf_pts, ones(n,1)];
    t_col = A \ img_pts(:,1);
    t_row = A \ img_pts(:,2);
    T = [t_col'; t_row'; 0 0 1];
    pred = T(1:2,:) * [dxf_pts'; ones(1,n)];
    err  = pred - img_pts';
    residual = sqrt(mean(sum(err.^2, 1)));
end


function [Hmat, residual] = compute_dxf_projective(dxf_pts, img_pts)
% Least-squares homography (DLT) mapping DXF coords -> image pixels.
%   [col; row; 1] ~ Hmat * [x_dxf; y_dxf; 1]   (with perspective division)
%   Uses Hartley normalization for numerical stability. Needs n >= 4 points.
    n = size(dxf_pts, 1);
    if n < 4
        error('extract_flow_domain:projectiveNeeds4', ...
            'Projective alignment needs at least 4 control points (got %d).', n);
    end

    [Ns, src_n] = normalize_points_2d(dxf_pts);
    [Nd, dst_n] = normalize_points_2d(img_pts);

    A = zeros(2*n, 9);
    for k = 1:n
        x = src_n(k,1);  y = src_n(k,2);
        u = dst_n(k,1);  v = dst_n(k,2);
        A(2*k-1, :) = [-x, -y, -1,  0,  0,  0,  u*x, u*y, u];
        A(2*k,   :) = [ 0,  0,  0, -x, -y, -1,  v*x, v*y, v];
    end

    [~, ~, V] = svd(A, 0);
    Hn = reshape(V(:, end), 3, 3)';     % row-major: rows = h1..h3, h4..h6, h7..h9

    % Denormalize: u ~ inv(Nd) * Hn * Ns * x
    Hmat = Nd \ (Hn * Ns);
    if abs(Hmat(3,3)) > eps
        Hmat = Hmat / Hmat(3,3);
    end

    pred = project_points_homography(Hmat, dxf_pts);
    err  = pred - img_pts;
    residual = sqrt(mean(sum(err.^2, 2)));
end


function [Tn, pts_n] = normalize_points_2d(pts)
% Hartley normalization: translate to centroid, scale to mean distance sqrt(2).
    c = mean(pts, 1);
    d = pts - c;
    mean_dist = mean(sqrt(sum(d.^2, 2)));
    if mean_dist < eps, mean_dist = 1; end
    s = sqrt(2) / mean_dist;
    Tn = [s, 0, -s*c(1); 0, s, -s*c(2); 0, 0, 1];
    P  = Tn * [pts, ones(size(pts,1),1)]';
    pts_n = P(1:2, :)';
end


function pts_img = project_points_homography(Hmat, pts)
% Apply homography to N-by-2 points (with perspective division) -> N-by-2.
    n = size(pts, 1);
    P = Hmat * [pts, ones(n,1)]';
    w = P(3, :);
    w(abs(w) < eps) = eps;
    pts_img = [(P(1,:)./w)', (P(2,:)./w)'];
end


function mask = rasterize_circles_affine(circles, T, H, W)
% Rasterize DXF circles as affine-transformed ellipses.
    mask = false(H, W);
    M   = T(1:2, 1:2);
    MMt = M * M';
    Q   = inv(MMt);              % ellipse metric
    dx_s = sqrt(MMt(1,1));       % bounding-box scale factors
    dy_s = sqrt(MMt(2,2));

    for i = 1:numel(circles)
        r = circles(i).r;
        if ~isfinite(r) || r <= 0, continue; end
        pt  = T(1:2,:) * [circles(i).x; circles(i).y; 1];
        cpx = pt(1);  cpy = pt(2);

        dx = r * dx_s + 1;  dy = r * dy_s + 1;
        c0 = max(1, floor(cpx-dx));  c1 = min(W, ceil(cpx+dx));
        r0 = max(1, floor(cpy-dy));  r1 = min(H, ceil(cpy+dy));
        if c0 > c1 || r0 > r1, continue; end

        [cc, rr] = meshgrid(c0:c1, r0:r1);
        dc = cc - cpx;  dr = rr - cpy;
        inside = Q(1,1)*dc.^2 + 2*Q(1,2)*dc.*dr + Q(2,2)*dr.^2 <= r^2;
        sub = mask(r0:r1, c0:c1);  sub(inside) = true;
        mask(r0:r1, c0:c1) = sub;
    end
end


function mask = rasterize_polyline_affine(polyline, T, H, W)
% Rasterize a DXF polyline as a filled polygon using affine transform.
    n   = min(numel(polyline.x), numel(polyline.y));
    pts = T(1:2,:) * [polyline.x(1:n); polyline.y(1:n); ones(1,n)];
    mask = poly2mask(pts(1,:), pts(2,:), H, W);
end


function mask = rasterize_circles_projective(circles, Hmat, H, W)
% Rasterize DXF circles under a homography. Each circle maps to a local
% ellipse approximated from the 2x2 Jacobian of the projective map at its
% centre (exact to first order; perspective scale varies smoothly across the
% small pillar radius, so the approximation is sub-pixel for typical chips).
    mask = false(H, W);
    for i = 1:numel(circles)
        r = circles(i).r;
        if ~isfinite(r) || r <= 0, continue; end
        x = circles(i).x;  y = circles(i).y;

        p = Hmat * [x; y; 1];
        if abs(p(3)) < eps, continue; end
        cpx = p(1)/p(3);  cpy = p(2)/p(3);

        J = homography_jacobian(Hmat, x, y);
        JJt = J * J';
        if rcond(JJt) < 1e-12, continue; end
        Q = inv(JJt);
        dx_s = sqrt(JJt(1,1));  dy_s = sqrt(JJt(2,2));

        dx = r*dx_s + 1;  dy = r*dy_s + 1;
        c0 = max(1, floor(cpx-dx));  c1 = min(W, ceil(cpx+dx));
        r0 = max(1, floor(cpy-dy));  r1 = min(H, ceil(cpy+dy));
        if c0 > c1 || r0 > r1, continue; end

        [cc, rr] = meshgrid(c0:c1, r0:r1);
        dc = cc - cpx;  dr = rr - cpy;
        inside = Q(1,1)*dc.^2 + 2*Q(1,2)*dc.*dr + Q(2,2)*dr.^2 <= r^2;
        sub = mask(r0:r1, c0:c1);  sub(inside) = true;
        mask(r0:r1, c0:c1) = sub;
    end
end


function J = homography_jacobian(Hmat, x, y)
% 2x2 Jacobian d[col; row]/d[x; y] of the projective map at (x, y).
    a = Hmat(1,1); b = Hmat(1,2); c = Hmat(1,3);
    d = Hmat(2,1); e = Hmat(2,2); f = Hmat(2,3);
    g = Hmat(3,1); h = Hmat(3,2); ii = Hmat(3,3);
    u = a*x + b*y + c;
    v = d*x + e*y + f;
    w = g*x + h*y + ii;
    if abs(w) < eps, w = eps; end
    w2 = w*w;
    J = [ (a*w - u*g)/w2, (b*w - u*h)/w2; ...
          (d*w - v*g)/w2, (e*w - v*h)/w2 ];
end


function mask = rasterize_polyline_projective(polyline, Hmat, H, W)
% Rasterize a DXF polyline as a filled polygon under a homography.
    n  = min(numel(polyline.x), numel(polyline.y));
    px = polyline.x(1:n);  py = polyline.y(1:n);
    pts = project_points_homography(Hmat, [px(:), py(:)]);
    mask = poly2mask(pts(:,1), pts(:,2), H, W);
end


function info = merge_struct_fields(info, extra)
    names = fieldnames(extra);
    for i = 1:numel(names)
        info.(names{i}) = extra.(names{i});
    end
end


function print_flow_domain_summary(H, W, solid_mask, info)
    fprintf('  Flow domain: %d x %d\n', H, W);
    fprintf('  Pillars: %d pixels (%.1f%% of chip)\n', ...
        sum(solid_mask(:)), info.pillar_fraction * 100);
    fprintf('  Porosity: %.1f%%\n', info.porosity * 100);
end


function show_mask_override_diagnostics(ref_image, chip_interior, solid_mask, info)
    figure('Name', 'Flow Domain Mask Override - Diagnostics', ...
        'Position', [50 50 1400 420], 'Color', 'w');

    subplot(1,4,1);
    imshow(ref_image);
    title('Input reference', 'FontSize', 11);

    subplot(1,4,2);
    imshow(chip_interior);
    title(sprintf('chip\\_interior (%d px)', nnz(chip_interior)), ...
        'FontSize', 11);

    subplot(1,4,3);
    imshow(solid_mask);
    title(sprintf('solid\\_mask (%d px)', nnz(solid_mask)), ...
        'FontSize', 11);

    subplot(1,4,4);
    overlay = im2double(ref_image);
    for c = 1:3
        channel = overlay(:,:,c);
        channel(solid_mask) = (c == 1);
        overlay(:,:,c) = channel;
    end
    imshow(overlay);
    title(sprintf('Mask overlay | porosity=%.1f%%', ...
        info.porosity * 100), 'FontSize', 11);

    sgtitle(sprintf('Flow-domain mask override: %s', info.method), ...
        'FontSize', 13, 'FontWeight', 'bold');
end


%% ========================================================================
%  COLOR-BASED PILLAR DETECTION (Lab a* channel)
%  ========================================================================
function solid_mask = detect_pillars_color(a_ch, L_ch, chip_interior, total_chip, P)
    fprintf('  Using Lab a* color-based pillar detection\n');
    [H, W] = size(a_ch);

    % Otsu on a* within chip to separate DNAPL (high a*) from non-DNAPL
    a_chip = a_ch(chip_interior);
    a_min = min(a_chip);
    a_max = max(a_chip);
    a_norm = (a_chip - a_min) / (a_max - a_min);
    a_thresh = graythresh(uint8(a_norm * 255)) * (a_max - a_min) + a_min;

    fprintf('  a* Otsu threshold: %.1f\n', a_thresh);

    % DNAPL = high a* (pink), non-DNAPL = low a* (pillars + water)
    dnapl_region = (a_ch > a_thresh) & chip_interior;
    non_dnapl = (~dnapl_region) & chip_interior;

    dnapl_frac = sum(dnapl_region(:)) / total_chip;
    non_dnapl_frac = sum(non_dnapl(:)) / total_chip;
    fprintf('  DNAPL: %.1f%%, non-DNAPL: %.1f%%\n', dnapl_frac * 100, non_dnapl_frac * 100);

    % Among non-DNAPL pixels, use L* to separate bright pillars from water
    L_non_dnapl = L_ch(non_dnapl);

    if numel(L_non_dnapl) > 100
        % Otsu on L* to split bright pillars from dimmer water
        L_norm = (L_non_dnapl - min(L_non_dnapl)) / max(max(L_non_dnapl) - min(L_non_dnapl), 1);
        L_thresh_rel = graythresh(uint8(L_norm * 255));
        L_thresh = L_thresh_rel * (max(L_non_dnapl) - min(L_non_dnapl)) + min(L_non_dnapl);

        pillar_cand = non_dnapl & (L_ch > L_thresh);
        pillar_frac_bright = sum(pillar_cand(:)) / total_chip;

        fprintf('  L* threshold: %.1f, bright pillars: %.1f%% of chip\n', ...
            L_thresh, pillar_frac_bright * 100);

        % If bright pillars are plausible (10-50%), use them
        if pillar_frac_bright > P.BRIGHT_MIN_FRAC && pillar_frac_bright < P.BRIGHT_MAX_FRAC
            fprintf('  Using bright-pillar method\n');
        else
            fprintf('  Bright-pillar fraction not plausible (%.1f%%). ', pillar_frac_bright * 100);
            [q_mask, q_frac, q_thresh] = select_bright_quantile_mask(L_ch, non_dnapl, total_chip, P);
            if ~isempty(q_mask)
                pillar_cand = q_mask;
                fprintf('Using quantile fallback (L*=%.1f, %.1f%% of chip).\n', ...
                    q_thresh, q_frac * 100);
            else
                fprintf('Using all non-DNAPL as provisional pillars.\n');
                pillar_cand = non_dnapl;
            end
        end
    else
        pillar_cand = non_dnapl;
        fprintf('  Very few non-DNAPL pixels; treating all as pillars\n');
    end

    % Morphological cleanup
    pillar_cand = imclose(pillar_cand, strel('disk', 2));
    pillar_cand = imopen(pillar_cand, strel('disk', 1));  % radius=1 to preserve small pillars
    pillar_cand = bwareaopen(pillar_cand, P.MIN_BLOB_AREA_COLOR);
    pillar_cand = imfill(pillar_cand, 'holes');

    % Filter individual connected components by area
    max_pillar_area = total_chip * P.MAX_PILLAR_AREA_FRAC;
    stats = regionprops(pillar_cand, 'Area', 'PixelIdxList');
    solid_mask = false(H, W);
    for k = 1:numel(stats)
        a = stats(k).Area;
        if a > P.MIN_BLOB_AREA_COLOR && a < max_pillar_area
            solid_mask(stats(k).PixelIdxList) = true;
        end
    end

    pillar_fraction = sum(solid_mask(:)) / total_chip;
    fprintf('  Color-based result: %.1f%% pillars\n', pillar_fraction * 100);
end


function [best_mask, best_frac, best_thresh] = select_bright_quantile_mask(L_ch, non_dnapl, total_chip, P)
% Select a robust bright subset of non-DNAPL pixels when Otsu on L* is unstable.
    best_mask = [];
    best_frac = 0;
    best_thresh = NaN;

    L_vals = L_ch(non_dnapl);
    if numel(L_vals) < 100
        return;
    end

    best_score = inf;

    for q = P.QUANTILE_RANGE
        th = prctile(L_vals, q);
        cand = non_dnapl & (L_ch > th);
        frac = sum(cand(:)) / max(total_chip, 1);

        if frac >= P.QUANTILE_MIN_FRAC && frac <= P.QUANTILE_MAX_FRAC
            score = abs(frac - P.TARGET_PILLAR_FRAC);
            if score < best_score
                best_score = score;
                best_mask = cand;
                best_frac = frac;
                best_thresh = th;
            end
        end
    end
end


%% ========================================================================
%  WHITE-PILLAR DETECTION (local L* threshold + component shape filter)
%  ========================================================================
function solid_mask = detect_pillars_white_local(L_ch, chip_interior, total_chip, P)
    fprintf('  Using local white-pillar detection on L* channel\n');
    [H, W] = size(L_ch);
    L_norm = mat2gray(L_ch);
    bg_value = median(L_norm(chip_interior));
    L_work = L_norm;
    L_work(~chip_interior) = bg_value;

    nhood = max(3, round(P.WHITE_PILLAR_NEIGHBORHOOD_PX));
    if mod(nhood, 2) == 0
        nhood = nhood + 1;
    end

    T = adaptthresh(L_work, P.WHITE_PILLAR_SENSITIVITY, ...
        'ForegroundPolarity', 'bright', ...
        'NeighborhoodSize', [nhood nhood]);
    pillar_cand = imbinarize(L_work, T) & chip_interior;
    pillar_cand = imopen(pillar_cand, strel('disk', 1));
    pillar_cand = imclose(pillar_cand, strel('disk', 1));
    pillar_cand = bwareaopen(pillar_cand, P.WHITE_PILLAR_MIN_AREA_PX);

    max_area = min(total_chip * P.MAX_PILLAR_AREA_FRAC, ...
        P.WHITE_PILLAR_MAX_AREA_PX);
    stats = regionprops(pillar_cand, 'Area', 'Perimeter', 'PixelIdxList');
    solid_mask = false(H, W);
    for k = 1:numel(stats)
        area_k = stats(k).Area;
        perim_k = max(stats(k).Perimeter, eps);
        circularity = 4 * pi * area_k / (perim_k^2);
        if area_k >= P.WHITE_PILLAR_MIN_AREA_PX && area_k <= max_area && ...
                circularity >= P.WHITE_PILLAR_MIN_CIRCULARITY
            solid_mask(stats(k).PixelIdxList) = true;
        end
    end

    pillar_fraction = sum(solid_mask(:)) / max(total_chip, 1);
    fprintf('  White-pillar result: %.1f%% pillars (sensitivity=%.2f, nhood=%d)\n', ...
        pillar_fraction * 100, P.WHITE_PILLAR_SENSITIVITY, nhood);
end


%% ========================================================================
%  MORPHOLOGICAL PILLAR DETECTION (grayscale fallback)
%  ========================================================================
function solid_mask = detect_pillars_morphological(ref_image, chip_interior, total_chip, P)
    fprintf('  Using multi-scale morphological pillar detection\n');

    gray = rgb2gray(ref_image);
    gray_d = im2double(gray);
    [H, W] = size(gray);

    % Multi-scale top-hat and bottom-hat
    radii = P.MORPH_RADII;
    tophat_max = zeros(H, W);
    bothat_max = zeros(H, W);
    for r = radii
        se = strel('disk', r);
        tophat_max = max(tophat_max, imtophat(gray_d, se));
        bothat_max = max(bothat_max, imbothat(gray_d, se));
    end

    top_range = prctile(tophat_max(chip_interior), 99) - median(tophat_max(chip_interior));
    bot_range = prctile(bothat_max(chip_interior), 99) - median(bothat_max(chip_interior));

    if top_range >= bot_range
        feature_map = tophat_max;
        fprintf('  top-hat contrast=%.3f\n', top_range);
    else
        feature_map = bothat_max;
        fprintf('  bottom-hat contrast=%.3f\n', bot_range);
    end

    feature_vals = feature_map(chip_interior);
    max_feat = max(feature_vals);

    if max_feat < P.MORPH_CONTRAST_MIN
        fprintf('  Very low morphological contrast (%.4f)\n', max_feat);
        solid_mask = false(H, W);
    else
        feature_norm = feature_map / max_feat;
        th = graythresh(uint8(feature_norm(chip_interior) * 255));
        pillar_cand = (feature_norm > th) & chip_interior;

        pillar_cand = imopen(pillar_cand, strel('disk', 1));  % radius=1 to preserve small pillars
        pillar_cand = imclose(pillar_cand, strel('disk', 2));
        pillar_cand = bwareaopen(pillar_cand, P.MIN_BLOB_AREA_MORPH);
        pillar_cand = imfill(pillar_cand, 'holes');

        max_pillar_area = total_chip * P.MAX_PILLAR_AREA_FRAC;
        stats = regionprops(pillar_cand, 'Area', 'PixelIdxList');
        solid_mask = false(H, W);
        for k = 1:numel(stats)
            a = stats(k).Area;
            if a > P.MIN_BLOB_AREA_MORPH && a < max_pillar_area
                solid_mask(stats(k).PixelIdxList) = true;
            end
        end
    end

    % Otsu fallback if morphological found nothing
    pillar_fraction = sum(solid_mask(:)) / total_chip;
    if pillar_fraction < P.WARN_PILLAR_FRAC
        fprintf('  Morphological found few pillars (%.1f%%). Trying Otsu...\n', ...
            pillar_fraction * 100);

        chip_vals = gray_d(chip_interior);
        otsu_level = graythresh(uint8(chip_vals * 255)) * ...
            (max(chip_vals) - min(chip_vals)) + min(chip_vals);

        bright_mask = (gray_d > otsu_level) & chip_interior;
        dark_mask   = (gray_d <= otsu_level) & chip_interior;

        if sum(bright_mask(:)) < sum(dark_mask(:))
            pillar_raw = bright_mask;
        else
            pillar_raw = dark_mask;
        end

        pillar_raw = imopen(pillar_raw, strel('disk', 1));  % radius=1 to preserve small pillars
        pillar_raw = imclose(pillar_raw, strel('disk', 2));
        pillar_raw = bwareaopen(pillar_raw, P.MIN_BLOB_AREA_MORPH);
        pillar_raw = imfill(pillar_raw, 'holes');

        max_pillar_area = total_chip * P.MAX_PILLAR_AREA_FRAC;
        stats2 = regionprops(pillar_raw, 'Area', 'PixelIdxList');
        solid_mask2 = false(H, W);
        for k = 1:numel(stats2)
            a = stats2(k).Area;
            if a > P.MIN_BLOB_AREA_MORPH && a < max_pillar_area
                solid_mask2(stats2(k).PixelIdxList) = true;
            end
        end

        frac2 = sum(solid_mask2(:)) / total_chip;
        if frac2 > P.OTSU_MIN_FRAC && frac2 < P.OTSU_MAX_FRAC
            solid_mask = solid_mask2;
            fprintf('  Otsu result: %.1f%% pillars\n', frac2 * 100);
        else
            fprintf('  Otsu result %.1f%% not plausible\n', frac2 * 100);
        end
    end
end
