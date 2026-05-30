function [S_NAPL_color, info] = compute_bulk_sn_color(frame_rgb, water_rgb, ...
        napl_rgb, flow_domain, solid_mask, config, bg_mask)
% COMPUTE_BULK_SN_COLOR  Endpoint-normalized bulk color-index saturation.
%
%   S_NAPL_color is an operational color-index saturation for Sn(t). It is
%   not a calibrated local volume fraction.

    if nargin < 6
        config = struct();
    end
    if nargin < 7
        bg_mask = [];
    end

    opts = bulk_sn_options(config);
    flow_domain = logical(flow_domain);
    if nargin < 5 || isempty(solid_mask)
        solid_mask = false(size(flow_domain));
    else
        solid_mask = logical(solid_mask);
    end

    validate_image_size(frame_rgb, flow_domain, 'frame_rgb');
    validate_image_size(water_rgb, flow_domain, 'water_rgb');
    validate_image_size(napl_rgb, flow_domain, 'napl_rgb');

    [core_flow, core_status] = make_core_flow(flow_domain, solid_mask, opts);
    use_background = opts.use_background && ~isempty(bg_mask);
    if use_background
        bg_mask = logical(bg_mask);
        if ~isequal(size(bg_mask), size(flow_domain))
            error('compute_bulk_sn_color:bgMaskSizeMismatch', ...
                'bg_mask must match flow_domain size.');
        end
    end

    measurement_mask = select_measurement_mask(flow_domain, core_flow, opts.mask_id);

    [score_frame, score_water, score_napl, score_meta] = score_maps( ...
        frame_rgb, water_rgb, napl_rgb, opts.score_mode, config, measurement_mask);

    [Q_t, stats_frame] = robust_stat(score_frame(measurement_mask), opts);
    [Q_w, stats_water] = robust_stat(score_water(measurement_mask), opts);
    [Q_n, stats_napl] = robust_stat(score_napl(measurement_mask), opts);

    if use_background
        B_t = robust_stat(score_frame(bg_mask), opts);
        B_w = robust_stat(score_water(bg_mask), opts);
        B_n = robust_stat(score_napl(bg_mask), opts);
        A_t = Q_t - B_t;
        A_w = Q_w - B_w;
        A_n = Q_n - B_n;
    else
        B_t = NaN;
        B_w = NaN;
        B_n = NaN;
        A_t = Q_t;
        A_w = Q_w;
        A_n = Q_n;
    end

    denom = A_n - A_w;
    reference_transfer_status = "ok";
    if ~isfinite(denom) || abs(denom) <= opts.min_endpoint_delta
        S_raw = NaN;
        S_NAPL_color = NaN;
        reference_transfer_status = "bad_endpoint";
    else
        S_raw = (A_t - A_w) / denom;
        S_NAPL_color = double(min(max(S_raw, 0), 1));
    end

    [region_raw, region_clamped, region_area] = regional_color_sn( ...
        score_frame, score_water, score_napl, measurement_mask, opts, ...
        use_background, bg_mask);
    edge_flow = flow_domain & ~core_flow;
    [core_raw, core_clamped] = single_region_color_sn( ...
        score_frame, score_water, score_napl, core_flow, opts, ...
        use_background, bg_mask);
    [edge_raw, edge_clamped] = single_region_color_sn( ...
        score_frame, score_water, score_napl, edge_flow, opts, ...
        use_background, bg_mask);

    qc = strings(0, 1);
    if core_status ~= "ok"
        qc(end + 1) = core_status;
    end
    if reference_transfer_status ~= "ok"
        qc(end + 1) = reference_transfer_status;
    end

    info = struct();
    info.S_NAPL_color_raw = S_raw;
    info.S_NAPL_color = S_NAPL_color;
    info.S_NAPL_color_core_raw = core_raw;
    info.S_NAPL_color_core = core_clamped;
    info.S_NAPL_color_edge_raw = edge_raw;
    info.S_NAPL_color_edge = edge_clamped;
    info.endpoint_status = string(opts.endpoint_status);
    info.endpoint_source = string(opts.endpoint_source);
    info.mask_id = string(opts.mask_id);
    info.rgb_source = string(opts.rgb_source);
    info.score_mode = string(opts.score_mode);
    info.statistic = string(opts.statistic);
    info.winsor_percentiles = opts.winsor_percentiles;
    info.score_frame = Q_t;
    info.score_water_ref = Q_w;
    info.score_napl_ref = Q_n;
    info.background_frame = B_t;
    info.background_water_ref = B_w;
    info.background_napl_ref = B_n;
    info.use_background = use_background;
    info.core_flow_area_px = nnz(core_flow);
    info.flow_domain_area_px = nnz(flow_domain);
    info.measurement_mask_area_px = nnz(measurement_mask);
    info.edge_excluded_fraction = 1 - nnz(core_flow) / max(nnz(flow_domain), 1);
    info.core_flow_min_dist_px = opts.core_flow_min_dist_px;
    info.reference_transfer_status = reference_transfer_status;
    info.score_frame_map = score_frame;
    info.score_water_map = score_water;
    info.score_napl_map = score_napl;
    info.score_frame_q05 = stats_frame.q05;
    info.score_frame_q50 = stats_frame.q50;
    info.score_frame_q95 = stats_frame.q95;
    info.score_water_q50 = stats_water.q50;
    info.score_napl_q50 = stats_napl.q50;
    info.region_S_NAPL_color_raw = region_raw;
    info.region_S_NAPL_color = region_clamped;
    info.region_area_px = region_area;
    info.n_x_bins = opts.n_x_bins;
    info.emit_regions = opts.emit_regions;
    info.qc_status = join_qc(qc);
    info.pdf_method_reference = string(opts.pdf_method_reference);
    info.score_meta = score_meta;
end


function opts = bulk_sn_options(config)
    opts = struct();
    opts.enabled = true;
    opts.primary_output = true;
    opts.score_mode = 'normalized_red';
    opts.statistic = 'winsorized_mean';
    opts.winsor_percentiles = [1 99];
    opts.core_flow_min_dist_px = [];
    opts.emit_regions = true;
    opts.n_x_bins = 20;
    opts.use_background = false;
    opts.pdf_method_reference = 'es4c11735_si_001.pdf';
    opts.min_endpoint_delta = 1e-6;
    opts.endpoint_status = 'provisional';
    opts.endpoint_source = 'configured_reference';
    opts.mask_id = 'core_flow';
    opts.rgb_source = 'corrected_quantitative';

    if isstruct(config) && isfield(config, 'bulk_sn') && isstruct(config.bulk_sn)
        user = config.bulk_sn;
        names = fieldnames(opts);
        for i = 1:numel(names)
            name = names{i};
            if isfield(user, name) && ~isempty(user.(name))
                opts.(name) = user.(name);
            end
        end
    end

    if isempty(opts.core_flow_min_dist_px)
        sf = 1;
        if isstruct(config) && isfield(config, 'preprocessing') && ...
                isstruct(config.preprocessing) && ...
                isfield(config.preprocessing, 'upscale') && ...
                isstruct(config.preprocessing.upscale) && ...
                isfield(config.preprocessing.upscale, 'scale_factor') && ...
                ~isempty(config.preprocessing.upscale.scale_factor)
            sf = config.preprocessing.upscale.scale_factor;
        end
        opts.core_flow_min_dist_px = 2 * sf;
    end

    opts.score_mode = char(string(opts.score_mode));
    opts.statistic = char(string(opts.statistic));
    opts.winsor_percentiles = double(opts.winsor_percentiles);
    opts.core_flow_min_dist_px = double(opts.core_flow_min_dist_px);
    opts.n_x_bins = double(opts.n_x_bins);
    opts.endpoint_status = char(string(opts.endpoint_status));
    opts.endpoint_source = char(string(opts.endpoint_source));
    opts.mask_id = char(string(opts.mask_id));
    opts.rgb_source = char(string(opts.rgb_source));
end


function validate_image_size(rgb, flow_domain, label)
    if ndims(rgb) ~= 3 || size(rgb, 3) ~= 3
        error('compute_bulk_sn_color:badRgb', '%s must be an MxNx3 RGB image.', label);
    end
    if size(rgb, 1) ~= size(flow_domain, 1) || ...
            size(rgb, 2) ~= size(flow_domain, 2)
        error('compute_bulk_sn_color:sizeMismatch', ...
            '%s size [%d x %d] does not match flow_domain [%d x %d].', ...
            label, size(rgb, 1), size(rgb, 2), ...
            size(flow_domain, 1), size(flow_domain, 2));
    end
end


function [core_flow, status] = make_core_flow(flow_domain, solid_mask, opts)
    status = "ok";
    if any(solid_mask(:)) && opts.core_flow_min_dist_px > 0
        core_flow = flow_domain & bwdist(solid_mask) >= opts.core_flow_min_dist_px;
    else
        core_flow = flow_domain;
    end

    if ~any(core_flow(:))
        core_flow = flow_domain;
        status = "core_flow_empty_fallback";
    end
end


function measurement_mask = select_measurement_mask(flow_domain, core_flow, mask_id)
    switch lower(char(string(mask_id)))
        case 'core_flow'
            measurement_mask = core_flow;
        case 'flow_domain'
            measurement_mask = flow_domain;
        otherwise
            error('compute_bulk_sn_color:unknownMaskId', ...
                'Unknown bulk_sn.mask_id: %s', char(string(mask_id)));
    end
end


function [score_frame, score_water, score_napl, meta] = score_maps( ...
        frame_rgb, water_rgb, napl_rgb, mode, config, core_flow)
    meta = struct();
    mode = lower(char(string(mode)));

    switch mode
        case {'normalized_red', 'excess_red', 'lab_a', 'chroma'}
            score_frame = compute_color_score(frame_rgb, mode, config);
            score_water = compute_color_score(water_rgb, mode, config);
            score_napl = compute_color_score(napl_rgb, mode, config);

        case 'lab_ab_projection'
            [F_frame, F_water, F_napl] = lab_ab_features(frame_rgb, water_rgb, napl_rgb, config);
            water_endpoint = [median(F_water.a(core_flow), 'omitnan'), ...
                median(F_water.b(core_flow), 'omitnan')];
            napl_endpoint = [median(F_napl.a(core_flow), 'omitnan'), ...
                median(F_napl.b(core_flow), 'omitnan')];
            v = napl_endpoint - water_endpoint;
            denom = max(norm(v), eps);
            score_frame = (F_frame.a .* v(1) + F_frame.b .* v(2)) ./ denom;
            score_water = (F_water.a .* v(1) + F_water.b .* v(2)) ./ denom;
            score_napl = (F_napl.a .* v(1) + F_napl.b .* v(2)) ./ denom;
            meta.water_endpoint_ab = water_endpoint;
            meta.napl_endpoint_ab = napl_endpoint;

        otherwise
            error('compute_bulk_sn_color:unknownScoreMode', ...
                'Unknown bulk_sn.score_mode: %s', mode);
    end
end


function score = compute_color_score(rgb, mode, config)
    rgb = normalize_rgb(rgb);
    R = rgb(:, :, 1);
    G = rgb(:, :, 2);
    B = rgb(:, :, 3);

    switch mode
        case 'normalized_red'
            score = R ./ max(R + G + B, eps('single'));

        case 'excess_red'
            score = R - 0.5 .* (G + B);

        case 'lab_a'
            lab = rgb2lab_for_bulk(rgb, config);
            score = lab(:, :, 2);

        case 'chroma'
            lab = rgb2lab_for_bulk(rgb, config);
            score = hypot(lab(:, :, 2), lab(:, :, 3));

        otherwise
            error('compute_bulk_sn_color:unknownScoreMode', ...
                'Unknown scalar score mode: %s', mode);
    end
end


function [F_frame, F_water, F_napl] = lab_ab_features(frame_rgb, water_rgb, napl_rgb, config)
    lab_frame = rgb2lab_for_bulk(normalize_rgb(frame_rgb), config);
    lab_water = rgb2lab_for_bulk(normalize_rgb(water_rgb), config);
    lab_napl = rgb2lab_for_bulk(normalize_rgb(napl_rgb), config);
    F_frame = struct('a', lab_frame(:, :, 2), 'b', lab_frame(:, :, 3));
    F_water = struct('a', lab_water(:, :, 2), 'b', lab_water(:, :, 3));
    F_napl = struct('a', lab_napl(:, :, 2), 'b', lab_napl(:, :, 3));
end


function lab = rgb2lab_for_bulk(rgb, config)
    if exist('prepare_rgb_for_lab', 'file') == 2
        rgb = prepare_rgb_for_lab(rgb, config);
    end
    lab = rgb2lab(rgb);
end


function rgb = normalize_rgb(rgb)
    if isa(rgb, 'single') || isa(rgb, 'double')
        rgb = single(rgb);
        if max(rgb(:)) > 1
            rgb = rgb ./ 255;
        end
    else
        rgb = im2single(rgb);
    end
    rgb = min(max(rgb, 0), 1);
end


function [value, stats] = robust_stat(x, opts)
    x = x(isfinite(x));
    if isempty(x)
        value = NaN;
        stats = empty_stats();
        return;
    end

    switch lower(opts.statistic)
        case 'winsorized_mean'
            p = opts.winsor_percentiles;
            lo = prctile(x, p(1));
            hi = prctile(x, p(2));
            xw = min(max(x, lo), hi);
            value = mean(xw);

        case 'mean'
            value = mean(x);

        otherwise
            error('compute_bulk_sn_color:unknownStatistic', ...
                'Unknown bulk_sn.statistic: %s', opts.statistic);
    end

    stats = struct( ...
        'q05', prctile(x, 5), ...
        'q50', median(x), ...
        'q95', prctile(x, 95));
end


function stats = empty_stats()
    stats = struct('q05', NaN, 'q50', NaN, 'q95', NaN);
end


function [raw_values, clamped_values, area_values] = regional_color_sn( ...
        score_frame, score_water, score_napl, core_flow, opts, ...
        use_background, bg_mask)
    if ~opts.emit_regions || opts.n_x_bins < 1
        raw_values = nan(1, 0);
        clamped_values = nan(1, 0);
        area_values = nan(1, 0);
        return;
    end

    n_bins = opts.n_x_bins;
    raw_values = nan(1, n_bins);
    clamped_values = nan(1, n_bins);
    area_values = zeros(1, n_bins);

    [~, cols] = find(core_flow);
    if isempty(cols)
        return;
    end

    edges = linspace(min(cols), max(cols) + 1, n_bins + 1);
    [xx, ~] = meshgrid(1:size(core_flow, 2), 1:size(core_flow, 1));
    for b = 1:n_bins
        region = core_flow & xx >= edges(b) & xx < edges(b + 1);
        area_values(b) = nnz(region);
        if ~any(region(:))
            continue;
        end

        Q_t = robust_stat(score_frame(region), opts);
        Q_w = robust_stat(score_water(region), opts);
        Q_n = robust_stat(score_napl(region), opts);
        if use_background
            Q_t = Q_t - robust_stat(score_frame(bg_mask), opts);
            Q_w = Q_w - robust_stat(score_water(bg_mask), opts);
            Q_n = Q_n - robust_stat(score_napl(bg_mask), opts);
        end
        denom = Q_n - Q_w;
        if isfinite(denom) && abs(denom) > opts.min_endpoint_delta
            raw_values(b) = (Q_t - Q_w) / denom;
            clamped_values(b) = min(max(raw_values(b), 0), 1);
        end
    end
end


function [raw_value, clamped_value] = single_region_color_sn( ...
        score_frame, score_water, score_napl, region_mask, opts, ...
        use_background, bg_mask)
    raw_value = NaN;
    clamped_value = NaN;
    if ~any(region_mask(:))
        return;
    end

    Q_t = robust_stat(score_frame(region_mask), opts);
    Q_w = robust_stat(score_water(region_mask), opts);
    Q_n = robust_stat(score_napl(region_mask), opts);
    if use_background
        Q_t = Q_t - robust_stat(score_frame(bg_mask), opts);
        Q_w = Q_w - robust_stat(score_water(bg_mask), opts);
        Q_n = Q_n - robust_stat(score_napl(bg_mask), opts);
    end
    denom = Q_n - Q_w;
    if isfinite(denom) && abs(denom) > opts.min_endpoint_delta
        raw_value = (Q_t - Q_w) / denom;
        clamped_value = min(max(raw_value, 0), 1);
    end
end


function text = join_qc(qc)
    qc = qc(qc ~= "");
    if isempty(qc)
        text = "";
    else
        text = strjoin(cellstr(qc), ';');
    end
end
