function [sn_primary, info] = compute_bulk_sn_from_config(frame_rgb, ...
        flow_domain, solid_mask, config, sn_mask_secondary)
% COMPUTE_BULK_SN_FROM_CONFIG  Use configured references for primary bulk Sn.

    if nargin < 5
        sn_mask_secondary = NaN;
    end

    info = disabled_info(sn_mask_secondary);
    sn_primary = sn_mask_secondary;

    if ~bulk_sn_enabled(config)
        return;
    end

    [ok, water_rgb, napl_rgb] = bulk_reference_images(config);
    if ~ok
        info.enabled = false;
        info.qc_status = "bulk_sn_missing_reference";
        return;
    end

    [sn_primary, info] = compute_bulk_sn_color(frame_rgb, water_rgb, napl_rgb, ...
        flow_domain, solid_mask, config);
    info.enabled = true;
    info.Sn_mask_secondary = sn_mask_secondary;
    if isfinite(sn_primary) && isfinite(sn_mask_secondary)
        info.mask_color_abs_difference = abs(sn_mask_secondary - sn_primary);
    else
        info.mask_color_abs_difference = NaN;
    end

    threshold = mask_color_threshold(config);
    if isfinite(info.mask_color_abs_difference) && ...
            info.mask_color_abs_difference > threshold
        info.qc_status = append_qc_status(info.qc_status, "mask_color_disagreement");
    end
end


function tf = bulk_sn_enabled(config)
    tf = isstruct(config) && isfield(config, 'bulk_sn') && ...
        isstruct(config.bulk_sn) && ...
        read_logical(config.bulk_sn, 'enabled', false) && ...
        read_logical(config.bulk_sn, 'primary_output', true);
end


function [ok, water_rgb, napl_rgb] = bulk_reference_images(config)
    water_rgb = [];
    napl_rgb = [];
    ok = false;
    if ~isstruct(config) || ~isfield(config, 'segmentation') || ...
            ~isstruct(config.segmentation)
        return;
    end

    if isfield(config.segmentation, 'water_reference') && ...
            isstruct(config.segmentation.water_reference) && ...
            isfield(config.segmentation.water_reference, 'calibration') && ...
            isstruct(config.segmentation.water_reference.calibration) && ...
            isfield(config.segmentation.water_reference.calibration, 'water_rgb')
        water_rgb = config.segmentation.water_reference.calibration.water_rgb;
    end

    if isfield(config.segmentation, 'napl_reference') && ...
            isstruct(config.segmentation.napl_reference) && ...
            isfield(config.segmentation.napl_reference, 'calibration') && ...
            isstruct(config.segmentation.napl_reference.calibration) && ...
            isfield(config.segmentation.napl_reference.calibration, 'reference_rgb')
        napl_rgb = config.segmentation.napl_reference.calibration.reference_rgb;
    end

    ok = ~isempty(water_rgb) && ~isempty(napl_rgb);
end


function value = read_logical(s, field_name, default_value)
    value = default_value;
    if isstruct(s) && isfield(s, field_name) && ...
            islogical(s.(field_name)) && isscalar(s.(field_name))
        value = s.(field_name);
    end
end


function threshold = mask_color_threshold(config)
    threshold = 0.10;
    if isstruct(config) && isfield(config, 'segmentation') && ...
            isstruct(config.segmentation) && ...
            isfield(config.segmentation, 'bulk_check') && ...
            isstruct(config.segmentation.bulk_check) && ...
            isfield(config.segmentation.bulk_check, 'max_abs_difference') && ...
            ~isempty(config.segmentation.bulk_check.max_abs_difference)
        threshold = config.segmentation.bulk_check.max_abs_difference;
    end
    if isstruct(config) && isfield(config, 'bulk_sn') && ...
            isstruct(config.bulk_sn) && ...
            isfield(config.bulk_sn, 'mask_color_max_abs_difference') && ...
            ~isempty(config.bulk_sn.mask_color_max_abs_difference)
        threshold = config.bulk_sn.mask_color_max_abs_difference;
    end
end


function text = append_qc_status(text, token)
    text = string(text);
    token = string(token);
    if text == ""
        text = token;
    elseif ~contains(text, token)
        text = text + ";" + token;
    end
end


function info = disabled_info(sn_mask_secondary)
    info = struct();
    info.enabled = false;
    info.S_NAPL_color_raw = NaN;
    info.S_NAPL_color = NaN;
    info.S_NAPL_color_core_raw = NaN;
    info.S_NAPL_color_core = NaN;
    info.S_NAPL_color_edge_raw = NaN;
    info.S_NAPL_color_edge = NaN;
    info.Sn_mask_secondary = sn_mask_secondary;
    info.mask_color_abs_difference = NaN;
    info.endpoint_status = "not_computed";
    info.endpoint_source = "";
    info.mask_id = "";
    info.rgb_source = "";
    info.score_mode = "";
    info.statistic = "";
    info.score_frame = NaN;
    info.score_water_ref = NaN;
    info.score_napl_ref = NaN;
    info.core_flow_area_px = NaN;
    info.flow_domain_area_px = NaN;
    info.measurement_mask_area_px = NaN;
    info.edge_excluded_fraction = NaN;
    info.region_S_NAPL_color = nan(1, 0);
    info.region_S_NAPL_color_raw = nan(1, 0);
    info.qc_status = "";
    info.reference_transfer_status = "";
    info.pdf_method_reference = "";
end
