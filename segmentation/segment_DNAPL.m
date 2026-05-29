function [dnapl_mask, confidence_map, seg_info] = segment_DNAPL(ref_image, flow_domain, config)
% SEGMENT_DNAPL  Segment DNAPL pixels from a processing-grid RGB image.
%
%   Supports legacy GMM/Otsu/adaptive segmentation plus calibrated
%   water-reference rejection modes, single-reference NAPL matching, and
%   dual-reference NAPL color-fraction methods:
%       calibrated_a_threshold  - raw Lab a* > clean-water upper bound
%       calibrated_delta_a      - frame a* - clean-water a* > delta threshold
%       napl_reference_deltaE   - Lab distance to DNAPL-saturated reference
%       dual_reference_fraction - projection between clean-water and NAPL refs
%       dual_reference_fraction_hysteresis - fraction with seed/candidate growth
%       dual_reference_nearest  - nearest dual-reference endpoint in Lab space

    method = char(string(config.segmentation.method));
    method_lc = lower(method);
    min_area = config.segmentation.min_blob_area;
    morph_radius = config.segmentation.morph_radius;
    high_sat_guard = high_saturation_guard_config(config);
    calib = water_reference_calibration(config);
    napl_calib = napl_reference_calibration(config);

    %% Step 1: Color space conversion
    [rgb_for_lab, rgb_encoding] = prepare_rgb_for_lab(ref_image, config);
    lab_image = rgb2lab(rgb_for_lab);
    a_channel = lab_image(:,:,2);
    b_channel = lab_image(:,:,3);

    seg_info = default_seg_info(method, rgb_encoding, high_sat_guard, calib, napl_calib);
    seg_info.color_channel = a_channel;

    %% Step 2: Extract pore-only pixels
    flow_domain = logical(flow_domain);
    pore_idx = find(flow_domain);
    pore_a = a_channel(pore_idx);
    pore_b = b_channel(pore_idx);
    confidence_map = zeros(size(flow_domain));

    if isempty(pore_idx)
        dnapl_mask = false(size(flow_domain));
        seg_info.method_used = 'empty_flow_domain';
        fprintf('  DNAPL segmented (%s): 0 pixels (Sn = 0.000)\n', method);
        return;
    end

    %% Step 3: Classification
    has_locked_threshold = has_finite_field(config.segmentation, 'fixed_threshold');
    reference_methods = { ...
        'calibrated_delta_a', 'napl_reference_deltae', ...
        'dual_reference_fraction', 'dual_reference_fraction_hysteresis', ...
        'dual_reference_nearest'};
    if has_locked_threshold && ~ismember(method_lc, reference_methods)
        thresh = config.segmentation.fixed_threshold;
        [dnapl_pore, conf_pore] = segment_fixed_threshold(pore_a, thresh);
        seg_info.threshold = thresh;
        seg_info.threshold_value = thresh;
        seg_info.threshold_domain = 'raw_a';
        seg_info.threshold_source = 'locked_threshold';
        seg_info.method_used = 'fixed_threshold_locked';
        seg_info.method = [method ' (locked)'];
    else
        switch method_lc
            case 'calibrated_delta_a'
                [dnapl_pore, conf_pore, signal, thresh] = ...
                    segment_calibrated_delta_a(a_channel, pore_idx, calib);
                seg_info.color_channel = signal;
                seg_info.threshold = thresh;
                seg_info.threshold_value = thresh;
                seg_info.threshold_domain = 'delta_a';
                seg_info.threshold_source = 'water_reference_delta_a';
                seg_info.method_used = 'calibrated_delta_a';

            case 'calibrated_a_threshold'
                thresh = calibrated_raw_threshold(calib);
                [dnapl_pore, conf_pore] = segment_fixed_threshold(pore_a, thresh);
                seg_info.threshold = thresh;
                seg_info.threshold_value = thresh;
                seg_info.threshold_domain = 'raw_a';
                seg_info.threshold_source = 'water_reference_a_star';
                seg_info.method_used = 'calibrated_a_threshold';

            case 'fixed_threshold'
                thresh = fixed_or_calibrated_threshold(config, calib);
                [dnapl_pore, conf_pore] = segment_fixed_threshold(pore_a, thresh);
                seg_info.threshold = thresh;
                seg_info.threshold_value = thresh;
                seg_info.threshold_domain = 'raw_a';
                seg_info.threshold_source = fixed_threshold_source(config, calib);
                seg_info.method_used = 'fixed_threshold';

            case 'napl_reference_deltae'
                [dnapl_pore, conf_pore, signal, thresh] = ...
                    segment_napl_reference_deltaE(lab_image, pore_idx, napl_calib);
                seg_info.color_channel = signal;
                seg_info.threshold = thresh;
                seg_info.threshold_value = thresh;
                seg_info.threshold_domain = 'deltaE_to_napl_reference';
                seg_info.threshold_source = 'napl_reference';
                seg_info.method_used = 'napl_reference_deltaE';

            case {'dual_reference_fraction', 'dual_reference_fraction_hysteresis', ...
                    'dual_reference_nearest'}
                require_calibration(calib, method_lc);
                require_napl_calibration(napl_calib, method_lc);
                [dnapl_pore, conf_pore, signal, thresh, diag] = ...
                    segment_dual_reference(lab_image, rgb_for_lab, pore_idx, ...
                    calib, napl_calib, config, method_lc);
                seg_info = apply_dual_reference_seg_info(seg_info, signal, ...
                    thresh, diag, config, method_lc, calib, napl_calib);

            case 'gmm'
                [guard_hit, dnapl_pore, conf_pore, thresh, guard_source] = ...
                    maybe_apply_high_saturation_guard(pore_a, high_sat_guard, calib);
                if guard_hit
                    seg_info.high_saturation_guard_active = true;
                    seg_info.threshold = thresh;
                    seg_info.threshold_value = thresh;
                    seg_info.threshold_domain = 'raw_a';
                    seg_info.threshold_source = guard_source;
                    seg_info.method_used = 'high_saturation_guard_fixed_threshold';
                else
                    [dnapl_pore, conf_pore, gmm_model, thresh] = ...
                        segment_gmm(pore_a, pore_b, config.segmentation.num_components);
                    seg_info.gmm_model = gmm_model;
                    seg_info.threshold = thresh;
                    seg_info.threshold_value = thresh;
                    seg_info.threshold_domain = 'raw_a';
                    seg_info.threshold_source = 'gmm';
                    seg_info.method_used = 'gmm';
                    seg_info.gmm_means = gmm_means(gmm_model);
                end

            case 'otsu'
                [guard_hit, dnapl_pore, conf_pore, thresh, guard_source] = ...
                    maybe_apply_high_saturation_guard(pore_a, high_sat_guard, calib);
                if guard_hit
                    seg_info.high_saturation_guard_active = true;
                    seg_info.threshold = thresh;
                    seg_info.threshold_value = thresh;
                    seg_info.threshold_domain = 'raw_a';
                    seg_info.threshold_source = guard_source;
                    seg_info.method_used = 'high_saturation_guard_fixed_threshold';
                else
                    [dnapl_pore, conf_pore, thresh] = segment_otsu(pore_a);
                    seg_info.threshold = thresh;
                    seg_info.threshold_value = thresh;
                    seg_info.threshold_domain = 'raw_a';
                    seg_info.threshold_source = 'otsu';
                    seg_info.method_used = 'otsu';
                end

            case 'adaptive'
                [dnapl_pore, conf_pore, thresh] = segment_adaptive(a_channel, flow_domain);
                seg_info.threshold = thresh;
                seg_info.threshold_value = thresh;
                seg_info.threshold_domain = 'spatial_raw_a';
                seg_info.threshold_source = 'adaptive';
                seg_info.method_used = 'adaptive';

            otherwise
                error('segment_DNAPL:badMethod', ...
                    'Unknown segmentation method "%s".', method);
        end
    end

    %% Step 4: Build full-size mask
    dnapl_mask = false(size(flow_domain));
    dnapl_mask(pore_idx(dnapl_pore)) = true;
    confidence_map(pore_idx) = conf_pore;

    %% Step 5: Morphological cleanup
    dnapl_mask = refine_mask(dnapl_mask, morph_radius, min_area);

    %% Step 6: Enforce pore-space constraint
    dnapl_mask = dnapl_mask & flow_domain;
    seg_info = reconcile_dual_reference_seg_info(seg_info, dnapl_mask, flow_domain);

    fprintf('  DNAPL segmented (%s): %d pixels (Sn = %.3f)\n', ...
        seg_info.method_used, sum(dnapl_mask(:)), ...
        sum(dnapl_mask(:)) / max(sum(flow_domain(:)), 1));
end


function seg_info = default_seg_info(method, rgb_encoding, high_sat_guard, calib, napl_calib)
    seg_info = struct();
    seg_info.color_channel = [];
    seg_info.method = method;
    seg_info.method_requested = method;
    seg_info.method_used = method;
    seg_info.gmm_model = [];
    seg_info.gmm_means = [];
    seg_info.threshold = NaN;
    seg_info.threshold_value = NaN;
    seg_info.threshold_domain = '';
    seg_info.threshold_source = '';
    seg_info.rgb_encoding = rgb_encoding;
    seg_info.lab_input_encoding = 'srgb_after_prepare_rgb_for_lab';
    seg_info.processing_scale_factor = read_processing_scale_factor_from_calib(calib);
    if isempty(fieldnames(calib)) && ~isempty(fieldnames(napl_calib))
        seg_info.processing_scale_factor = ...
            read_processing_scale_factor_from_calib(napl_calib);
    end
    seg_info.high_saturation_guard_active = false;
    seg_info.high_saturation_guard_floor = high_sat_guard.a_floor;
    seg_info.high_saturation_guard_low_quantile = high_sat_guard.low_quantile;
    seg_info.high_saturation_guard_threshold = guard_threshold(high_sat_guard, calib);
    seg_info.water_reference_path = read_calib_field(calib, 'water_reference_path', '');
    seg_info.water_reference_sha256 = read_calib_field(calib, 'water_reference_sha256', '');
    seg_info.napl_reference_path = read_calib_field(napl_calib, 'napl_reference_path', '');
    seg_info.napl_reference_sha256 = read_calib_field(napl_calib, 'napl_reference_sha256', '');
    seg_info.threshold_quantile = read_calib_field(calib, 'threshold_quantile', NaN);
    seg_info.threshold_mad_k = read_calib_field(calib, 'threshold_mad_k', NaN);
    seg_info.threshold_margin = read_calib_field(calib, 'threshold_margin', NaN);
end


function [is_dnapl, conf, signal, thresh] = segment_calibrated_delta_a( ...
        a_channel, pore_idx, calib)
    require_calibration(calib, 'calibrated_delta_a');
    if ~isfield(calib, 'water_a_channel') || isempty(calib.water_a_channel)
        error('segment_DNAPL:missingWaterReferenceChannel', ...
            'calibrated_delta_a requires calibration.water_a_channel.');
    end
    if ~isequal(size(calib.water_a_channel), size(a_channel))
        error('segment_DNAPL:waterReferenceSizeMismatch', ...
            ['calibrated_delta_a requires water_a_channel to match frame size. ' ...
             'Got [%s] vs [%s].'], ...
            num2str(size(calib.water_a_channel)), num2str(size(a_channel)));
    end
    signal = a_channel - calib.water_a_channel;
    pore_signal = signal(pore_idx);
    thresh = calibrated_delta_threshold(calib);
    [is_dnapl, conf] = segment_fixed_threshold(pore_signal, thresh);
end


function [is_dnapl, conf, signal, thresh] = segment_napl_reference_deltaE( ...
        lab_image, pore_idx, calib)
    require_napl_calibration(calib, 'napl_reference_deltaE');
    if ~isfield(calib, 'reference_lab') || isempty(calib.reference_lab)
        error('segment_DNAPL:missingNaplReferenceLab', ...
            'napl_reference_deltaE requires calibration.reference_lab.');
    end
    if ~isequal(size(calib.reference_lab), size(lab_image))
        error('segment_DNAPL:naplReferenceSizeMismatch', ...
            ['napl_reference_deltaE requires reference_lab to match frame size. ' ...
             'Got [%s] vs [%s].'], ...
            num2str(size(calib.reference_lab)), num2str(size(lab_image)));
    end

    wL = read_calib_field(calib, 'l_weight', 1);
    wA = read_calib_field(calib, 'a_weight', 1);
    wB = read_calib_field(calib, 'b_weight', 1);
    deltaL = lab_image(:,:,1) - calib.reference_lab(:,:,1);
    deltaA = lab_image(:,:,2) - calib.reference_lab(:,:,2);
    deltaB = lab_image(:,:,3) - calib.reference_lab(:,:,3);
    signal = sqrt(wL .* deltaL.^2 + wA .* deltaA.^2 + wB .* deltaB.^2);
    pore_signal = signal(pore_idx);
    thresh = read_calib_field(calib, 'deltaE_threshold', ...
        read_calib_field(calib, 'threshold_value', NaN));
    if ~isscalar(thresh) || ~isfinite(thresh) || thresh <= 0
        error('segment_DNAPL:missingNaplReferenceThreshold', ...
            'napl_reference_deltaE requires a positive deltaE_threshold.');
    end

    is_dnapl = pore_signal <= thresh;
    conf = 1 - pore_signal ./ (thresh + eps);
    conf = max(min(conf, 1), 0);
end


function [is_dnapl, conf, signal, thresh, diag] = segment_dual_reference( ...
        lab_image, rgb_image, pore_idx, water_calib, napl_calib, config, method_lc)
    opts = dual_reference_options(config);
    hsv_diag = hsv_red_diagnostics(rgb_image, config);
    flow_domain = false(size(lab_image, 1), size(lab_image, 2));
    flow_domain(pore_idx) = true;
    pore_count = max(nnz(flow_domain), 1);

    water_lab = read_calib_field(water_calib, 'water_lab', []);
    if isempty(water_lab)
        error('segment_DNAPL:missingWaterReferenceLab', ...
            '%s requires calibration.water_lab.', method_lc);
    end
    napl_lab = read_calib_field(napl_calib, 'reference_lab', []);
    if isempty(napl_lab)
        error('segment_DNAPL:missingNaplReferenceLab', ...
            '%s requires calibration.reference_lab.', method_lc);
    end
    if ~isequal(size(water_lab), size(lab_image))
        error('segment_DNAPL:waterReferenceSizeMismatch', ...
            '%s requires water_lab to match frame size. Got [%s] vs [%s].', ...
            method_lc, num2str(size(water_lab)), num2str(size(lab_image)));
    end
    if ~isequal(size(napl_lab), size(lab_image))
        error('segment_DNAPL:naplReferenceSizeMismatch', ...
            '%s requires reference_lab to match frame size. Got [%s] vs [%s].', ...
            method_lc, num2str(size(napl_lab)), num2str(size(lab_image)));
    end

    [frame_feature, water_feature, napl_feature, feature_weights, ...
        feature_labels] = build_dual_reference_features(lab_image, rgb_image, ...
        water_calib, napl_calib, opts);
    weights = reshape(sqrt(feature_weights), [1 1 numel(feature_weights)]);
    endpoint_vec = (napl_feature - water_feature) .* weights;
    endpoint_den = sum(endpoint_vec.^2, 3);
    endpoint_distance = sqrt(endpoint_den);
    valid_endpoint = flow_domain & isfinite(endpoint_distance) & ...
        endpoint_distance >= opts.min_endpoint_distance;
    invalid_endpoint_mask = flow_domain & ~valid_endpoint;
    invalid_endpoint_fraction = nnz(invalid_endpoint_mask) / pore_count;

    positive_napl_mask = false(size(flow_domain));
    global_endpoint_fallback_active = false;
    endpoint_per_pixel_warning = invalid_endpoint_fraction > ...
        opts.max_invalid_endpoint_fraction;
    endpoint_per_pixel_unreliable = invalid_endpoint_fraction > ...
        opts.max_invalid_endpoint_fraction_fail;
    endpoint_mode_used = 'per_pixel';

    switch lower(opts.endpoint_mode)
        case 'auto'
            if endpoint_per_pixel_unreliable
                patch_mask = flow_domain;
                global_endpoint_fallback_active = true;
                endpoint_mode_used = 'robust_global';
            else
                patch_mask = invalid_endpoint_mask;
                if endpoint_per_pixel_warning
                    warning('segment_DNAPL:invalidEndpointFractionWarning', ...
                        ['Invalid endpoint fraction %.4f exceeds warning threshold %.4f; ' ...
                         'using per-pixel endpoints with invalid pixels patched.'], ...
                        invalid_endpoint_fraction, opts.max_invalid_endpoint_fraction);
                end
            end

        case 'robust_global'
            patch_mask = flow_domain;
            global_endpoint_fallback_active = true;
            endpoint_mode_used = 'robust_global';

        case 'per_pixel'
            if invalid_endpoint_fraction > opts.max_invalid_endpoint_fraction
                switch lower(opts.endpoint_fail_policy)
                    case 'fallback_global'
                        patch_mask = flow_domain;
                        global_endpoint_fallback_active = true;
                        endpoint_mode_used = 'robust_global';
                    case 'error'
                        error('segment_DNAPL:invalidEndpointFraction', ...
                            ['Invalid dual-reference endpoint fraction %.4f exceeds %.4f. ' ...
                             'Check water/NAPL reference alignment and color contrast.'], ...
                            invalid_endpoint_fraction, opts.max_invalid_endpoint_fraction);
                    case 'warn'
                        warning('segment_DNAPL:invalidEndpointFraction', ...
                            ['Invalid dual-reference endpoint fraction %.4f exceeds %.4f; ' ...
                             'patching invalid endpoints with the robust global endpoint.'], ...
                            invalid_endpoint_fraction, opts.max_invalid_endpoint_fraction);
                        patch_mask = invalid_endpoint_mask;
                    otherwise
                        error('segment_DNAPL:badEndpointFailPolicy', ...
                            'Unknown endpoint_fail_policy "%s".', opts.endpoint_fail_policy);
                end
            else
                patch_mask = invalid_endpoint_mask;
            end

        otherwise
            error('segment_DNAPL:badEndpointMode', ...
                'Unknown endpoint_mode "%s".', opts.endpoint_mode);
    end

    water_baseline = water_feature;
    if opts.global_water_baseline
        % Pure two-colour projection: replace BOTH per-pixel reference maps with
        % single robust colours (scalar water + scalar NAPL endpoint). This makes
        % the fraction independent of per-pixel reference alignment, which is the
        % correct choice when the water/NAPL references come from separate
        % acquisitions that are not pixel co-registered with the frame.
        [global_vec, global_den, positive_napl_mask, global_water] = ...
            global_dual_endpoint(water_feature, napl_feature, napl_lab, ...
            flow_domain, valid_endpoint, weights);
        [H_fd, W_fd] = size(flow_domain);
        endpoint_vec = repmat(global_vec, [H_fd, W_fd]);
        endpoint_den = repmat(global_den, [H_fd, W_fd]);
        endpoint_distance = repmat(sqrt(global_den), [H_fd, W_fd]);
        water_baseline = global_water;
        global_endpoint_fallback_active = true;
        endpoint_mode_used = 'global_two_color';
    elseif any(patch_mask(:))
        [global_vec, global_den, positive_napl_mask] = global_dual_endpoint( ...
            water_feature, napl_feature, napl_lab, flow_domain, valid_endpoint, ...
            weights);
        [endpoint_vec, endpoint_den, endpoint_distance] = patch_endpoint_vec( ...
            endpoint_vec, endpoint_den, endpoint_distance, patch_mask, ...
            global_vec, global_den);
    end

    delta = (frame_feature - water_baseline) .* weights;
    frac_raw = sum(delta .* endpoint_vec, 3) ./ max(endpoint_den, eps);
    frac_raw_map = frac_raw;
    frac_raw_map(~flow_domain) = NaN;
    frac = min(max(frac_raw, 0), 1);
    frac(~flow_domain) = NaN;
    hsv_seed = flow_domain & hsv_diag.seed_mask;
    hsv_candidate = flow_domain & hsv_diag.candidate_mask;
    hsv_seed_fallback_active = false;

    endpoint_gap = NaN(size(flow_domain));

    switch method_lc
        case 'dual_reference_fraction'
            thresh = opts.frac_threshold;
            final_mask = flow_domain & frac > opts.frac_threshold;
            seed_mask = final_mask;
            candidate_mask = final_mask;
            signal = frac;
            conf_map = frac;

        case 'dual_reference_fraction_hysteresis'
            thresh = opts.frac_high;
            frac_core = flow_domain & frac >= opts.frac_high;
            frac_candidate = flow_domain & frac >= opts.frac_low;
            seed_mask = frac_core;
            if opts.use_hsv_seed && hsv_diag.enabled
                hsv_seeded_core = frac_core & hsv_seed;
                hsv_seed_fraction_core = nnz(hsv_seeded_core) / pore_count;
                if any(frac_core(:)) && ...
                        hsv_seed_fraction_core < hsv_diag.min_seed_fraction
                    seed_mask = frac_core;
                    hsv_seed_fallback_active = true;
                else
                    seed_mask = hsv_seeded_core;
                end
            end
            hsv_candidate_gated = hsv_candidate & frac >= hsv_diag.frac_hsv_min;
            candidate_mask = frac_candidate;
            if hsv_diag.enabled
                candidate_mask = candidate_mask | hsv_candidate_gated;
            end
            if any(seed_mask(:))
                final_mask = imreconstruct(seed_mask, candidate_mask) & flow_domain;
            else
                final_mask = false(size(flow_domain));
            end
            signal = frac;
            conf_map = frac;

        case 'dual_reference_nearest'
            thresh = 0;
            d_water = sqrt(sum(delta.^2, 3));
            d_napl = sqrt(sum((delta - endpoint_vec).^2, 3));
            endpoint_gap = d_water - d_napl;
            endpoint_gap(~flow_domain) = NaN;
            final_mask = flow_domain & endpoint_gap > 0;
            seed_mask = final_mask;
            candidate_mask = final_mask;
            signal = endpoint_gap;
            conf_map = d_water ./ max(d_water + d_napl, eps);
            conf_map(~flow_domain) = NaN;

        otherwise
            error('segment_DNAPL:badDualReferenceMethod', ...
                'Unknown dual-reference method "%s".', method_lc);
    end

    is_dnapl = final_mask(pore_idx);
    conf = conf_map(pore_idx);
    conf(~isfinite(conf)) = 0;
    conf = max(min(conf, 1), 0);

    if strcmp(method_lc, 'dual_reference_fraction_hysteresis')
        sn_lower = nnz(seed_mask) / pore_count;
        sn_mid = nnz(final_mask) / pore_count;
        sn_upper = nnz(candidate_mask) / pore_count;
        uncertain_area_fraction = nnz(candidate_mask & ~seed_mask) / pore_count;
    else
        sn_mid = nnz(final_mask) / pore_count;
        sn_lower = sn_mid;
        sn_upper = sn_mid;
        uncertain_area_fraction = 0;
    end

    bulk = bulk_check_diagnostics(final_mask, frac, flow_domain, config);

    diag = struct();
    diag.frac_map = frac;
    diag.frac_raw_map = frac_raw_map;
    diag.endpoint_distance = endpoint_distance;
    diag.invalid_endpoint_mask = invalid_endpoint_mask;
    diag.seed_mask = seed_mask;
    diag.candidate_mask = candidate_mask;
    diag.final_mask = final_mask;
    diag.endpoint_gap = endpoint_gap;
    diag.positive_napl_mask = positive_napl_mask;
    diag.invalid_endpoint_fraction = invalid_endpoint_fraction;
    diag.endpoint_distance_p05 = percentile_or_nan(endpoint_distance(flow_domain), 5);
    diag.endpoint_distance_p50 = percentile_or_nan(endpoint_distance(flow_domain), 50);
    diag.endpoint_distance_p95 = percentile_or_nan(endpoint_distance(flow_domain), 95);
    diag.frac_raw_p05 = percentile_or_nan(frac_raw_map(flow_domain), 5);
    diag.frac_raw_p50 = percentile_or_nan(frac_raw_map(flow_domain), 50);
    diag.frac_raw_p95 = percentile_or_nan(frac_raw_map(flow_domain), 95);
    diag.frac_p05 = percentile_or_nan(frac(flow_domain), 5);
    diag.frac_p50 = percentile_or_nan(frac(flow_domain), 50);
    diag.frac_p95 = percentile_or_nan(frac(flow_domain), 95);
    diag.frac_clamped_low_fraction = nnz(flow_domain & frac_raw_map < 0) / pore_count;
    diag.frac_clamped_high_fraction = nnz(flow_domain & frac_raw_map > 1) / pore_count;
    frac_spatial = spatial_fraction_stats(frac, flow_domain);
    diag.frac_center_mean = frac_spatial.center_mean;
    diag.frac_edge_mean = frac_spatial.edge_mean;
    diag.frac_center_edge_difference = frac_spatial.center_edge_difference;
    diag.positive_napl_fraction = nnz(positive_napl_mask) / pore_count;
    diag.dual_reference_feature_mode = opts.feature_mode;
    diag.dual_reference_feature_labels = feature_labels;
    diag.endpoint_mode = opts.endpoint_mode;
    diag.endpoint_mode_used = endpoint_mode_used;
    diag.endpoint_per_pixel_warning = endpoint_per_pixel_warning;
    diag.endpoint_per_pixel_unreliable = endpoint_per_pixel_unreliable;
    diag.max_invalid_endpoint_fraction_fail = opts.max_invalid_endpoint_fraction_fail;
    diag.endpoint_fail_policy = opts.endpoint_fail_policy;
    diag.global_endpoint_fallback_active = global_endpoint_fallback_active;
    diag.Sn_lower = sn_lower;
    diag.Sn_mid = sn_mid;
    diag.Sn_upper = sn_upper;
    diag.Sn_uncertainty_width = sn_upper - sn_lower;
    diag.uncertain_area_fraction = uncertain_area_fraction;
    diag.hsv_seed_mask = hsv_seed;
    diag.hsv_candidate_mask = hsv_candidate;
    diag.hsv_candidate_gated_mask = hsv_candidate & frac >= hsv_diag.frac_hsv_min;
    diag.hsv_hue_map = hsv_diag.hue_map;
    diag.hsv_saturation_map = hsv_diag.saturation_map;
    diag.hsv_seed_fraction = nnz(hsv_seed) / pore_count;
    diag.hsv_candidate_fraction = nnz(hsv_candidate) / pore_count;
    diag.hsv_candidate_gated_fraction = nnz(diag.hsv_candidate_gated_mask) / pore_count;
    diag.hsv_red_enabled = hsv_diag.enabled;
    diag.hsv_red_use_as_seed = opts.use_hsv_seed && hsv_diag.enabled;
    diag.hsv_red_role = 'seed_and_candidate_assist';
    diag.hsv_seed_min_fraction = hsv_diag.min_seed_fraction;
    diag.hsv_frac_hsv_min = hsv_diag.frac_hsv_min;
    diag.hsv_seed_fallback_active = hsv_seed_fallback_active;
    diag.Sn_bulk_color = bulk.Sn_bulk_color;
    diag.Sn_mask_bulk_abs_difference = bulk.Sn_mask_bulk_abs_difference;
    diag.bulk_color_fraction_mean = bulk.bulk_color_fraction_mean;
    diag.mask_bulk_abs_difference = bulk.mask_bulk_abs_difference;
    diag.segmentation_qc_status = bulk.segmentation_qc_status;
    diag.bulk_check_enabled = bulk.enabled;
    diag.bulk_check_metric = bulk.metric;
    diag.bulk_check_max_abs_difference = bulk.max_abs_difference;
end


function seg_info = apply_dual_reference_seg_info(seg_info, signal, thresh, ...
        diag, config, method_lc, water_calib, napl_calib)
    opts = dual_reference_options(config);
    seg_info.color_channel = signal;
    seg_info.threshold = thresh;
    seg_info.threshold_value = thresh;
    seg_info.threshold_source = 'dual_reference';
    seg_info.threshold_domain = method_lc;
    seg_info.method_used = method_lc;
    seg_info.frac_threshold = opts.frac_threshold;
    seg_info.frac_high = opts.frac_high;
    seg_info.frac_low = opts.frac_low;
    seg_info.dual_reference_feature_mode = diag.dual_reference_feature_mode;
    seg_info.dual_reference_feature_labels = diag.dual_reference_feature_labels;
    seg_info.dual_reference_use_channels = opts.use_channels;
    seg_info.dual_reference_lab_weights = opts.lab_weights;
    seg_info.min_endpoint_distance = opts.min_endpoint_distance;
    seg_info.max_invalid_endpoint_fraction = opts.max_invalid_endpoint_fraction;
    seg_info.max_invalid_endpoint_fraction_fail = ...
        diag.max_invalid_endpoint_fraction_fail;
    seg_info.endpoint_mode = diag.endpoint_mode;
    seg_info.endpoint_mode_used = diag.endpoint_mode_used;
    seg_info.endpoint_per_pixel_warning = diag.endpoint_per_pixel_warning;
    seg_info.endpoint_per_pixel_unreliable = diag.endpoint_per_pixel_unreliable;
    seg_info.endpoint_fail_policy = opts.endpoint_fail_policy;
    seg_info.emit_uncertainty_band = opts.emit_uncertainty_band;
    seg_info.dual_reference_use_hsv_seed = opts.use_hsv_seed;
    seg_info.invalid_endpoint_fraction = diag.invalid_endpoint_fraction;
    seg_info.endpoint_distance_p05 = diag.endpoint_distance_p05;
    seg_info.endpoint_distance_p50 = diag.endpoint_distance_p50;
    seg_info.endpoint_distance_p95 = diag.endpoint_distance_p95;
    seg_info.frac_raw_p05 = diag.frac_raw_p05;
    seg_info.frac_raw_p50 = diag.frac_raw_p50;
    seg_info.frac_raw_p95 = diag.frac_raw_p95;
    seg_info.frac_clamped_low_fraction = diag.frac_clamped_low_fraction;
    seg_info.frac_clamped_high_fraction = diag.frac_clamped_high_fraction;
    seg_info.frac_center_mean = diag.frac_center_mean;
    seg_info.frac_edge_mean = diag.frac_edge_mean;
    seg_info.frac_center_edge_difference = diag.frac_center_edge_difference;
    seg_info.frac_p05 = diag.frac_p05;
    seg_info.frac_p50 = diag.frac_p50;
    seg_info.frac_p95 = diag.frac_p95;
    seg_info.positive_napl_fraction = diag.positive_napl_fraction;
    seg_info.water_reference_path = read_calib_field(water_calib, 'water_reference_path', '');
    seg_info.water_reference_sha256 = read_calib_field(water_calib, 'water_reference_sha256', '');
    seg_info.napl_reference_path = read_calib_field(napl_calib, 'napl_reference_path', '');
    seg_info.napl_reference_sha256 = read_calib_field(napl_calib, 'napl_reference_sha256', '');
    seg_info.global_endpoint_fallback_active = diag.global_endpoint_fallback_active;
    seg_info.Sn_lower = diag.Sn_lower;
    seg_info.Sn_mid = diag.Sn_mid;
    seg_info.Sn_upper = diag.Sn_upper;
    seg_info.Sn_uncertainty_width = diag.Sn_uncertainty_width;
    seg_info.uncertain_area_fraction = diag.uncertain_area_fraction;
    seg_info.napl_color_fraction_index = diag.frac_map;
    seg_info.napl_color_fraction_raw = diag.frac_raw_map;
    seg_info.endpoint_distance = diag.endpoint_distance;
    seg_info.invalid_endpoint_mask = diag.invalid_endpoint_mask;
    seg_info.seed_mask = diag.seed_mask;
    seg_info.candidate_mask = diag.candidate_mask;
    seg_info.final_mask = diag.final_mask;
    seg_info.endpoint_gap = diag.endpoint_gap;
    seg_info.positive_napl_mask = diag.positive_napl_mask;
    seg_info.hsv_seed_mask = diag.hsv_seed_mask;
    seg_info.hsv_candidate_mask = diag.hsv_candidate_mask;
    seg_info.hsv_candidate_gated_mask = diag.hsv_candidate_gated_mask;
    seg_info.hsv_hue_map = diag.hsv_hue_map;
    seg_info.hsv_saturation_map = diag.hsv_saturation_map;
    seg_info.hsv_seed_fraction = diag.hsv_seed_fraction;
    seg_info.hsv_candidate_fraction = diag.hsv_candidate_fraction;
    seg_info.hsv_candidate_gated_fraction = diag.hsv_candidate_gated_fraction;
    seg_info.hsv_red_enabled = diag.hsv_red_enabled;
    seg_info.hsv_red_use_as_seed = diag.hsv_red_use_as_seed;
    seg_info.hsv_red_role = diag.hsv_red_role;
    seg_info.hsv_seed_min_fraction = diag.hsv_seed_min_fraction;
    seg_info.hsv_frac_hsv_min = diag.hsv_frac_hsv_min;
    seg_info.hsv_seed_fallback_active = diag.hsv_seed_fallback_active;
    seg_info.Sn_bulk_color = diag.Sn_bulk_color;
    seg_info.Sn_mask_bulk_abs_difference = diag.Sn_mask_bulk_abs_difference;
    seg_info.bulk_color_fraction_mean = diag.bulk_color_fraction_mean;
    seg_info.mask_bulk_abs_difference = diag.mask_bulk_abs_difference;
    seg_info.segmentation_qc_status = diag.segmentation_qc_status;
    seg_info.bulk_check_enabled = diag.bulk_check_enabled;
    seg_info.bulk_check_metric = diag.bulk_check_metric;
    seg_info.bulk_check_max_abs_difference = diag.bulk_check_max_abs_difference;
end


function seg_info = reconcile_dual_reference_seg_info(seg_info, dnapl_mask, flow_domain)
    method_lc = lower(char(string(read_field(seg_info, 'method_used', ''))));
    if ~startsWith(method_lc, 'dual_reference_')
        return;
    end

    flow_domain = logical(flow_domain);
    refined_mask = logical(dnapl_mask) & flow_domain;
    pore_count = max(nnz(flow_domain), 1);
    sn_refined = nnz(refined_mask) / pore_count;
    emit_band = logical(read_field(seg_info, 'emit_uncertainty_band', true));

    seg_info.final_mask = refined_mask;
    if strcmp(method_lc, 'dual_reference_fraction_hysteresis') && emit_band
        seed_mask = read_same_size_mask(seg_info, 'seed_mask', refined_mask);
        candidate_mask = read_same_size_mask(seg_info, 'candidate_mask', refined_mask);
        seed_mask = seed_mask & refined_mask;
        candidate_support = (candidate_mask | refined_mask) & flow_domain;
        if any(refined_mask(:))
            candidate_mask = imreconstruct(refined_mask, candidate_support) & flow_domain;
        else
            candidate_mask = false(size(flow_domain));
        end

        seg_info.seed_mask = seed_mask;
        seg_info.candidate_mask = candidate_mask;
        seg_info.Sn_lower = nnz(seed_mask) / pore_count;
        seg_info.Sn_mid = sn_refined;
        seg_info.Sn_upper = nnz(candidate_mask) / pore_count;
        seg_info.Sn_uncertainty_width = seg_info.Sn_upper - seg_info.Sn_lower;
        seg_info.uncertain_area_fraction = ...
            nnz(candidate_mask & ~seed_mask) / pore_count;
    else
        seg_info.seed_mask = refined_mask;
        seg_info.candidate_mask = refined_mask;
        seg_info.Sn_lower = sn_refined;
        seg_info.Sn_mid = sn_refined;
        seg_info.Sn_upper = sn_refined;
        seg_info.Sn_uncertainty_width = 0;
        seg_info.uncertain_area_fraction = 0;
    end

    if isfield(seg_info, 'Sn_bulk_color') && ...
            isfield(seg_info, 'bulk_check_enabled')
        threshold = read_field(seg_info, 'bulk_check_max_abs_difference', 0.10);
        seg_info.Sn_mask_bulk_abs_difference = ...
            abs(sn_refined - read_field(seg_info, 'Sn_bulk_color', NaN));
        seg_info.bulk_color_fraction_mean = read_field(seg_info, ...
            'Sn_bulk_color', NaN);
        seg_info.mask_bulk_abs_difference = ...
            seg_info.Sn_mask_bulk_abs_difference;
        if logical(read_field(seg_info, 'bulk_check_enabled', false)) && ...
                isfinite(seg_info.Sn_mask_bulk_abs_difference) && ...
                seg_info.Sn_mask_bulk_abs_difference > threshold
            seg_info.segmentation_qc_status = 'mask_bulk_disagreement';
        else
            seg_info.segmentation_qc_status = '';
        end
    end
end


function mask = read_same_size_mask(s, field_name, default_mask)
    mask = default_mask;
    if isstruct(s) && isfield(s, field_name) && ...
            isequal(size(s.(field_name)), size(default_mask))
        mask = logical(s.(field_name));
    end
end


function diag = hsv_red_diagnostics(rgb_image, config)
    opts = hsv_red_options(config);
    hsv_img = rgb2hsv(rgb_image);
    H = hsv_img(:,:,1);
    S = hsv_img(:,:,2);
    V = hsv_img(:,:,3);
    strong_hue = H <= opts.h_high1 | H >= opts.h_high2;
    weak_hue = H <= opts.h_low1 | H >= opts.h_low2;
    seed_mask = opts.enabled & strong_hue & S >= opts.s_high & V >= opts.v_min;
    candidate_mask = opts.enabled & weak_hue & S >= opts.s_low & V >= opts.v_min;
    diag = struct( ...
        'enabled', opts.enabled, ...
        'seed_mask', seed_mask, ...
        'candidate_mask', candidate_mask, ...
        'hue_map', H, ...
        'saturation_map', S, ...
        'min_seed_fraction', opts.min_seed_fraction, ...
        'frac_hsv_min', opts.frac_hsv_min);
end


function opts = hsv_red_options(config)
    opts = struct( ...
        'enabled', true, ...
        'h_high1', 0.03, ...
        'h_high2', 0.97, ...
        'h_low1', 0.07, ...
        'h_low2', 0.93, ...
        's_high', 0.20, ...
        's_low', 0.08, ...
        'v_min', 0.10, ...
        'min_seed_fraction', 0.01, ...
        'frac_hsv_min', 0.02);
    if isfield(config, 'segmentation') && isstruct(config.segmentation) && ...
            isfield(config.segmentation, 'hsv_red') && ...
            isstruct(config.segmentation.hsv_red)
        s = config.segmentation.hsv_red;
        opts.enabled = read_field(s, 'enabled', opts.enabled);
        opts.h_high1 = read_field(s, 'h_high1', opts.h_high1);
        opts.h_high2 = read_field(s, 'h_high2', opts.h_high2);
        opts.h_low1 = read_field(s, 'h_low1', opts.h_low1);
        opts.h_low2 = read_field(s, 'h_low2', opts.h_low2);
        opts.s_high = read_field(s, 's_high', opts.s_high);
        opts.s_low = read_field(s, 's_low', opts.s_low);
        opts.v_min = read_field(s, 'v_min', opts.v_min);
        opts.min_seed_fraction = read_field(s, ...
            'min_seed_fraction', opts.min_seed_fraction);
        opts.frac_hsv_min = read_field(s, ...
            'frac_hsv_min', opts.frac_hsv_min);
    end
    opts.enabled = logical(opts.enabled);
end


function out = bulk_check_diagnostics(final_mask, frac, flow_domain, config)
    opts = bulk_check_options(config);
    sn_mask = nnz(final_mask & flow_domain) / max(nnz(flow_domain), 1);
    frac_vals = frac(flow_domain);
    frac_vals = frac_vals(isfinite(frac_vals));
    if isempty(frac_vals)
        sn_bulk = NaN;
    else
        sn_bulk = mean(frac_vals);
    end
    diff_abs = abs(sn_mask - sn_bulk);
    status = '';
    if opts.enabled && isfinite(diff_abs) && diff_abs > opts.max_abs_difference
        status = 'mask_bulk_disagreement';
    end
    out = struct( ...
        'enabled', opts.enabled, ...
        'metric', opts.metric, ...
        'max_abs_difference', opts.max_abs_difference, ...
        'Sn_bulk_color', sn_bulk, ...
        'Sn_mask_bulk_abs_difference', diff_abs, ...
        'bulk_color_fraction_mean', sn_bulk, ...
        'mask_bulk_abs_difference', diff_abs, ...
        'segmentation_qc_status', status);
end


function opts = bulk_check_options(config)
    opts = struct( ...
        'enabled', false, ...
        'metric', 'dual_reference_fraction_mean', ...
        'max_abs_difference', 0.10);
    if isfield(config, 'segmentation') && isstruct(config.segmentation) && ...
            isfield(config.segmentation, 'bulk_check') && ...
            isstruct(config.segmentation.bulk_check)
        s = config.segmentation.bulk_check;
        opts.enabled = read_field(s, 'enabled', opts.enabled);
        opts.metric = char(string(read_field(s, 'metric', opts.metric)));
        opts.max_abs_difference = read_field(s, ...
            'max_abs_difference', opts.max_abs_difference);
    end
    opts.enabled = logical(opts.enabled);
end


function opts = dual_reference_options(config)
    opts = struct( ...
        'feature_mode', 'lab_ab', ...
        'use_channels', 'ab', ...
        'lab_weights', [0 1 1], ...
        'frac_threshold', 0.50, ...
        'frac_high', 0.65, ...
        'frac_low', 0.35, ...
        'min_endpoint_distance', 3.0, ...
        'max_invalid_endpoint_fraction', 0.10, ...
        'max_invalid_endpoint_fraction_fail', 0.20, ...
        'endpoint_mode', 'auto', ...
        'endpoint_fail_policy', 'fallback_global', ...
        'emit_uncertainty_band', true, ...
        'global_water_baseline', false, ...
        'use_hsv_seed', true);

    has_lab_weights = false;
    if isfield(config, 'segmentation') && isstruct(config.segmentation) && ...
            isfield(config.segmentation, 'dual_reference') && ...
            isstruct(config.segmentation.dual_reference)
        dr = config.segmentation.dual_reference;
        opts.feature_mode = char(string(read_field(dr, 'feature_mode', opts.feature_mode)));
        opts.use_channels = char(string(read_field(dr, 'use_channels', opts.use_channels)));
        has_lab_weights = isfield(dr, 'lab_weights') && ~isempty(dr.lab_weights);
        if has_lab_weights
            opts.lab_weights = dr.lab_weights;
        end
        opts.frac_threshold = read_field(dr, 'frac_threshold', opts.frac_threshold);
        opts.frac_high = read_field(dr, 'frac_high', opts.frac_high);
        opts.frac_low = read_field(dr, 'frac_low', opts.frac_low);
        opts.min_endpoint_distance = read_field(dr, ...
            'min_endpoint_distance', opts.min_endpoint_distance);
        opts.max_invalid_endpoint_fraction = read_field(dr, ...
            'max_invalid_endpoint_fraction', opts.max_invalid_endpoint_fraction);
        opts.max_invalid_endpoint_fraction_fail = read_field(dr, ...
            'max_invalid_endpoint_fraction_fail', ...
            opts.max_invalid_endpoint_fraction_fail);
        opts.endpoint_mode = char(string(read_field(dr, ...
            'endpoint_mode', opts.endpoint_mode)));
        opts.endpoint_fail_policy = char(string(read_field(dr, ...
            'endpoint_fail_policy', opts.endpoint_fail_policy)));
        opts.emit_uncertainty_band = read_field(dr, ...
            'emit_uncertainty_band', opts.emit_uncertainty_band);
        opts.use_hsv_seed = read_field(dr, ...
            'use_hsv_seed', opts.use_hsv_seed);
        opts.global_water_baseline = read_field(dr, ...
            'global_water_baseline', opts.global_water_baseline);
    end

    if ~has_lab_weights
        opts.lab_weights = lab_weights_from_channels(opts.use_channels);
    end
    opts.lab_weights = double(reshape(opts.lab_weights, 1, []));
    if strcmpi(opts.feature_mode, 'lab_ab') && numel(opts.lab_weights) == 3 && ...
            opts.lab_weights(1) > 0
        opts.feature_mode = 'lab';
    end
    if numel(opts.lab_weights) ~= 3 || any(~isfinite(opts.lab_weights)) || ...
            any(opts.lab_weights < 0)
        error('segment_DNAPL:badDualReferenceWeights', ...
            'dual_reference.lab_weights must contain 3 finite nonnegative values.');
    end
    if ~any(opts.lab_weights > 0)
        error('segment_DNAPL:badDualReferenceWeights', ...
            'At least one dual_reference.lab_weights value must be positive.');
    end
    if ~(isfinite(opts.frac_threshold) && opts.frac_threshold > 0 && ...
            opts.frac_threshold < 1)
        error('segment_DNAPL:badDualReferenceThreshold', ...
            'dual_reference.frac_threshold must be in (0,1).');
    end
    if ~(isfinite(opts.frac_low) && isfinite(opts.frac_high) && ...
            opts.frac_low > 0 && opts.frac_high < 1 && opts.frac_high > opts.frac_low)
        error('segment_DNAPL:badDualReferenceThreshold', ...
            'dual_reference.frac_high must exceed frac_low, both in (0,1).');
    end
    if ~(isfinite(opts.min_endpoint_distance) && opts.min_endpoint_distance > 0)
        error('segment_DNAPL:badDualReferenceEndpoint', ...
            'dual_reference.min_endpoint_distance must be positive.');
    end
    if ~(isfinite(opts.max_invalid_endpoint_fraction) && ...
            opts.max_invalid_endpoint_fraction >= 0 && ...
            opts.max_invalid_endpoint_fraction <= 1)
        error('segment_DNAPL:badDualReferenceEndpoint', ...
            'dual_reference.max_invalid_endpoint_fraction must be in [0,1].');
    end
    if ~(isfinite(opts.max_invalid_endpoint_fraction_fail) && ...
            opts.max_invalid_endpoint_fraction_fail >= 0 && ...
            opts.max_invalid_endpoint_fraction_fail <= 1 && ...
            opts.max_invalid_endpoint_fraction_fail >= opts.max_invalid_endpoint_fraction)
        error('segment_DNAPL:badDualReferenceEndpoint', ...
            ['dual_reference.max_invalid_endpoint_fraction_fail must be in [0,1] ' ...
             'and >= max_invalid_endpoint_fraction.']);
    end
end


function weights = lab_weights_from_channels(use_channels)
    s = lower(char(string(use_channels)));
    weights = [0 0 0];
    if contains(s, 'l')
        weights(1) = 1;
    end
    if contains(s, 'a')
        weights(2) = 1;
    end
    if contains(s, 'b')
        weights(3) = 1;
    end
    if ~any(weights)
        error('segment_DNAPL:badDualReferenceChannels', ...
            'dual_reference.use_channels must include at least one of L, a, b.');
    end
end


function [frame_feature, water_feature, napl_feature, feature_weights, labels] = ...
        build_dual_reference_features(lab_image, rgb_image, water_calib, ...
        napl_calib, opts)
    mode = lower(char(string(opts.feature_mode)));
    water_lab = read_calib_field(water_calib, 'water_lab', []);
    napl_lab = read_calib_field(napl_calib, 'reference_lab', []);
    switch mode
        case {'lab_a', 'a'}
            frame_feature = lab_image(:,:,2);
            water_feature = water_lab(:,:,2);
            napl_feature = napl_lab(:,:,2);
            feature_weights = 1;
            labels = {'a'};

        case {'lab_ab', 'ab'}
            frame_feature = lab_image(:,:,2:3);
            water_feature = water_lab(:,:,2:3);
            napl_feature = napl_lab(:,:,2:3);
            feature_weights = [1 1];
            labels = {'a', 'b'};

        case 'lab'
            frame_feature = lab_image;
            water_feature = water_lab;
            napl_feature = napl_lab;
            feature_weights = opts.lab_weights;
            labels = {'L', 'a', 'b'};

        case 'a_plus_chroma'
            frame_feature = a_chroma_feature(lab_image);
            water_feature = a_chroma_feature(water_lab);
            napl_feature = a_chroma_feature(napl_lab);
            feature_weights = [1 1];
            labels = {'a', 'chroma'};

        case 'normalized_rgb'
            water_rgb = read_required_reference_rgb(water_calib, 'water_rgb', mode);
            napl_rgb = read_required_reference_rgb(napl_calib, 'reference_rgb', mode);
            frame_feature = normalized_rgb_feature(rgb_image);
            water_feature = normalized_rgb_feature(water_rgb);
            napl_feature = normalized_rgb_feature(napl_rgb);
            feature_weights = [1 1 1];
            labels = {'r_norm', 'g_norm', 'b_norm'};

        case 'od_fraction'
            water_rgb = read_required_reference_rgb(water_calib, 'water_rgb', mode);
            napl_rgb = read_required_reference_rgb(napl_calib, 'reference_rgb', mode);
            frame_feature = optical_density_feature(rgb_image);
            water_feature = optical_density_feature(water_rgb);
            napl_feature = optical_density_feature(napl_rgb);
            feature_weights = [1 1 1];
            labels = {'od_r', 'od_g', 'od_b'};

        otherwise
            error('segment_DNAPL:badDualReferenceFeatureMode', ...
                'Unknown dual_reference.feature_mode "%s".', opts.feature_mode);
    end
    feature_weights = double(reshape(feature_weights, 1, []));
end


function feature = a_chroma_feature(lab)
    a = lab(:,:,2);
    b = lab(:,:,3);
    feature = cat(3, a, hypot(a, b));
end


function feature = normalized_rgb_feature(rgb)
    rgb = im2double(rgb);
    denom = sum(rgb, 3) + eps;
    feature = 100 * cat(3, rgb(:,:,1) ./ denom, ...
        rgb(:,:,2) ./ denom, rgb(:,:,3) ./ denom);
end


function feature = optical_density_feature(rgb)
    rgb = max(im2double(rgb), 1e-6);
    feature = 100 * -log(rgb);
end


function rgb = read_required_reference_rgb(calib, field_name, mode)
    rgb = read_calib_field(calib, field_name, []);
    if isempty(rgb)
        error('segment_DNAPL:missingReferenceRgb', ...
            ['dual_reference.feature_mode="%s" requires calibration.%s. ' ...
             'Re-run reference calibration with the current code.'], ...
            mode, field_name);
    end
end


function [global_vec, global_den, positive_napl_mask, global_water] = global_dual_endpoint( ...
        water_feature, napl_feature, napl_lab, flow_domain, valid_endpoint, weights)
    a_napl = napl_lab(:,:,2);
    b_napl = napl_lab(:,:,3);
    chroma_napl = hypot(a_napl, b_napl);
    finite_napl = flow_domain & isfinite(a_napl) & isfinite(chroma_napl);
    a_thresh = percentile_or_nan(a_napl(finite_napl), 80);
    chroma_thresh = percentile_or_nan(chroma_napl(finite_napl), 80);
    positive_napl_mask = finite_napl & a_napl > a_thresh & chroma_napl > chroma_thresh;
    if ~any(positive_napl_mask(:))
        has_positive_signal = max(a_napl(finite_napl)) > 1 && ...
            max(chroma_napl(finite_napl)) > 1;
        if has_positive_signal
            positive_napl_mask = finite_napl & a_napl >= a_thresh & ...
                chroma_napl >= chroma_thresh;
        end
    end
    if ~any(positive_napl_mask(:))
        error('segment_DNAPL:emptyPositiveNaplEndpoint', ...
            ['Could not identify positive-NAPL pixels for the global endpoint. ' ...
             'Check the full-NAPL reference or lower min_endpoint_distance.']);
    end

    water_mask = flow_domain & valid_endpoint;
    if ~any(water_mask(:))
        water_mask = flow_domain;
    end

    global_water = robust_feature_location(water_feature, water_mask);
    global_napl = robust_feature_location(napl_feature, positive_napl_mask);
    global_vec = (global_napl - global_water) .* weights;
    global_den = sum(global_vec.^2, 3);
    if ~isscalar(global_den) || ~isfinite(global_den) || global_den <= eps
        error('segment_DNAPL:invalidGlobalEndpoint', ...
            'Could not compute a positive global dual-reference endpoint.');
    end
end


function loc = robust_feature_location(feature, mask)
    loc = zeros(1, 1, size(feature, 3));
    for ch = 1:size(feature, 3)
        vals = feature(:,:,ch);
        vals = vals(mask);
        vals = vals(isfinite(vals));
        if isempty(vals)
            error('segment_DNAPL:emptyRobustEndpoint', ...
                'Cannot compute robust dual-reference endpoint from an empty finite mask.');
        end
        loc(1, 1, ch) = median(vals);
    end
end


function [endpoint_vec, endpoint_den, endpoint_distance] = patch_endpoint_vec( ...
        endpoint_vec, endpoint_den, endpoint_distance, patch_mask, global_vec, global_den)
    for ch = 1:size(endpoint_vec, 3)
        plane = endpoint_vec(:,:,ch);
        plane(patch_mask) = global_vec(1, 1, ch);
        endpoint_vec(:,:,ch) = plane;
    end
    endpoint_den(patch_mask) = global_den;
    endpoint_distance(patch_mask) = sqrt(global_den);
end


function value = percentile_or_nan(vals, pct)
    vals = vals(isfinite(vals));
    if isempty(vals)
        value = NaN;
    else
        value = prctile(vals, pct);
    end
end


function out = spatial_fraction_stats(frac, flow_domain)
    out = struct('center_mean', NaN, 'edge_mean', NaN, ...
        'center_edge_difference', NaN);
    [rr, cc] = find(flow_domain);
    if isempty(rr)
        return;
    end
    r0 = min(rr); r1 = max(rr);
    c0 = min(cc); c1 = max(cc);
    r_center0 = r0 + (r1 - r0) / 3;
    r_center1 = r0 + 2 * (r1 - r0) / 3;
    c_center0 = c0 + (c1 - c0) / 3;
    c_center1 = c0 + 2 * (c1 - c0) / 3;
    [R, C] = ndgrid(1:size(flow_domain, 1), 1:size(flow_domain, 2));
    center_mask = flow_domain & R >= r_center0 & R <= r_center1 & ...
        C >= c_center0 & C <= c_center1;
    edge_mask = flow_domain & ~center_mask;
    out.center_mean = mean_finite_or_nan(frac(center_mask));
    out.edge_mean = mean_finite_or_nan(frac(edge_mask));
    if isfinite(out.center_mean) && isfinite(out.edge_mean)
        out.center_edge_difference = out.center_mean - out.edge_mean;
    end
end


function value = mean_finite_or_nan(vals)
    vals = vals(isfinite(vals));
    if isempty(vals)
        value = NaN;
    else
        value = mean(vals);
    end
end


function [guard_hit, is_dnapl, conf, thresh, source] = ...
        maybe_apply_high_saturation_guard(pore_a, high_sat_guard, calib)
    guard_hit = false;
    is_dnapl = [];
    conf = [];
    thresh = NaN;
    source = '';
    if ~high_sat_guard.enabled
        return;
    end

    thresh = guard_threshold(high_sat_guard, calib);
    source = guard_threshold_source(calib);
    if prctile(pore_a, high_sat_guard.low_quantile) <= thresh
        return;
    end

    guard_hit = true;
    [is_dnapl, conf] = segment_fixed_threshold(pore_a, thresh);
    conf(:) = 1;
    fprintf(['  High-saturation guard: pore a* p%.1f above %.4f (%s); ' ...
        'using fixed-threshold water rejection\n'], ...
        high_sat_guard.low_quantile, thresh, source);
end


function [is_dnapl, conf, gmm_model, thresh] = segment_gmm(pore_a, ~, n_comp)
    features = pore_a(:);

    max_samples = 50000;
    if numel(features) > max_samples
        rng(42);
        sample_idx = randperm(numel(features), max_samples);
        features_sample = features(sample_idx);
    else
        features_sample = features;
    end

    try
        gmm_model = fitgmdist(features_sample, n_comp, ...
            'RegularizationValue', 0.01, ...
            'Options', statset('MaxIter', 200));
    catch
        warning('segment_DNAPL:gmmFailed', 'GMM fit failed. Falling back to Otsu.');
        [is_dnapl, conf, thresh] = segment_otsu(pore_a);
        gmm_model = [];
        return;
    end

    [cluster_idx, ~, posterior] = cluster(gmm_model, features);
    cluster_means = gmm_model.mu;
    [~, dnapl_cluster] = max(cluster_means);

    is_dnapl = (cluster_idx == dnapl_cluster);
    conf = posterior(:, dnapl_cluster);
    thresh = mean(cluster_means);
end


function [is_dnapl, conf, thresh] = segment_otsu(pore_a)
    a_min = min(pore_a);
    a_max = max(pore_a);
    a_norm = (pore_a - a_min) / (a_max - a_min + eps);

    thresh_norm = graythresh(a_norm);
    thresh = thresh_norm * (a_max - a_min) + a_min;

    is_dnapl = pore_a > thresh;
    conf = (pore_a - thresh) / (a_max - thresh + eps);
    conf = max(min(conf, 1), 0);
end


function [is_dnapl, conf, thresh] = segment_adaptive(a_channel, flow_domain)
    a_uint8 = im2uint8(mat2gray(a_channel));
    T = adaptthresh(a_uint8, 0.5, 'NeighborhoodSize', [51 51]);
    bw = imbinarize(a_uint8, T);

    is_dnapl = bw(flow_domain);
    conf = double(is_dnapl);
    thresh = NaN;
end


function [is_dnapl, conf] = segment_fixed_threshold(pore_signal, thresh)
    is_dnapl = pore_signal > thresh;
    signal_max = max(pore_signal);
    conf = (pore_signal - thresh) / (signal_max - thresh + eps);
    conf = max(min(conf, 1), 0);
end


function high_sat_guard = high_saturation_guard_config(config)
    high_sat_guard = struct('enabled', true, 'a_floor', 5, 'low_quantile', 5);
    if isfield(config, 'segmentation') && isstruct(config.segmentation) && ...
            isfield(config.segmentation, 'high_saturation_guard') && ...
            isstruct(config.segmentation.high_saturation_guard)
        s = config.segmentation.high_saturation_guard;
        high_sat_guard.enabled = read_field(s, 'enabled', high_sat_guard.enabled);
        high_sat_guard.a_floor = read_field(s, 'a_floor', high_sat_guard.a_floor);
        high_sat_guard.low_quantile = read_field(s, 'low_quantile', ...
            high_sat_guard.low_quantile);
    end
end


function calib = water_reference_calibration(config)
    calib = struct();
    if isfield(config, 'segmentation') && isstruct(config.segmentation) && ...
            isfield(config.segmentation, 'water_reference') && ...
            isstruct(config.segmentation.water_reference) && ...
            isfield(config.segmentation.water_reference, 'calibration') && ...
            isstruct(config.segmentation.water_reference.calibration)
        calib = config.segmentation.water_reference.calibration;
    end
end


function calib = napl_reference_calibration(config)
    calib = struct();
    if isfield(config, 'segmentation') && isstruct(config.segmentation) && ...
            isfield(config.segmentation, 'napl_reference') && ...
            isstruct(config.segmentation.napl_reference) && ...
            isfield(config.segmentation.napl_reference, 'calibration') && ...
            isstruct(config.segmentation.napl_reference.calibration)
        calib = config.segmentation.napl_reference.calibration;
    end
end


function require_calibration(calib, method_name)
    if ~isstruct(calib) || isempty(fieldnames(calib))
        error('segment_DNAPL:missingWaterReferenceCalibration', ...
            '%s requires config.segmentation.water_reference.calibration.', ...
            method_name);
    end
end


function require_napl_calibration(calib, method_name)
    if ~isstruct(calib) || isempty(fieldnames(calib))
        error('segment_DNAPL:missingNaplReferenceCalibration', ...
            '%s requires config.segmentation.napl_reference.calibration.', ...
            method_name);
    end
end


function thresh = fixed_or_calibrated_threshold(config, calib)
    if has_finite_field(config.segmentation, 'fixed_threshold')
        thresh = config.segmentation.fixed_threshold;
    elseif is_calibrated(calib)
        thresh = calibrated_raw_threshold(calib);
    else
        error('segment_DNAPL:missingFixedThreshold', ...
            'fixed_threshold segmentation requires segmentation.fixed_threshold or water calibration.');
    end
end


function source = fixed_threshold_source(config, calib)
    if has_finite_field(config.segmentation, 'fixed_threshold')
        source = 'fixed_threshold';
    elseif is_calibrated(calib)
        source = 'water_reference_a_star';
    else
        source = '';
    end
end


function thresh = calibrated_raw_threshold(calib)
    require_calibration(calib, 'calibrated_a_threshold');
    if isfield(calib, 'raw_a_threshold') && ~isempty(calib.raw_a_threshold)
        thresh = calib.raw_a_threshold;
    elseif isfield(calib, 'threshold_value') && ~isempty(calib.threshold_value)
        thresh = calib.threshold_value;
    else
        error('segment_DNAPL:missingWaterReferenceThreshold', ...
            'Water calibration does not contain raw_a_threshold.');
    end
end


function thresh = calibrated_delta_threshold(calib)
    require_calibration(calib, 'calibrated_delta_a');
    if isfield(calib, 'delta_a_threshold') && ~isempty(calib.delta_a_threshold)
        thresh = calib.delta_a_threshold;
    else
        error('segment_DNAPL:missingWaterReferenceThreshold', ...
            'Water calibration does not contain delta_a_threshold.');
    end
end


function thresh = guard_threshold(high_sat_guard, calib)
    if is_calibrated(calib)
        thresh = calibrated_raw_threshold(calib);
    else
        thresh = high_sat_guard.a_floor;
    end
end


function source = guard_threshold_source(calib)
    if is_calibrated(calib)
        source = 'water_reference_a_star';
    else
        source = 'high_saturation_guard_a_floor';
    end
end


function tf = is_calibrated(calib)
    tf = isstruct(calib) && ...
        (isfield(calib, 'raw_a_threshold') || isfield(calib, 'threshold_value'));
end


function tf = has_finite_field(s, field_name)
    tf = isstruct(s) && isfield(s, field_name) && ~isempty(s.(field_name)) && ...
        isnumeric(s.(field_name)) && isscalar(s.(field_name)) && isfinite(s.(field_name));
end


function value = read_field(s, field_name, default_value)
    value = default_value;
    if isstruct(s) && isfield(s, field_name) && ~isempty(s.(field_name))
        value = s.(field_name);
    end
end


function value = read_calib_field(calib, field_name, default_value)
    value = default_value;
    if isstruct(calib) && isfield(calib, field_name) && ~isempty(calib.(field_name))
        value = calib.(field_name);
    end
end


function sf = read_processing_scale_factor_from_calib(calib)
    sf = read_calib_field(calib, 'processing_scale_factor', 1);
end


function means = gmm_means(gmm_model)
    if isempty(gmm_model) || ~isprop(gmm_model, 'mu')
        means = [];
    else
        means = gmm_model.mu;
    end
end
