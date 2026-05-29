function diag = diagnose_dual_reference_frame(results_in, config_in)
% DIAGNOSE_DUAL_REFERENCE_FRAME  Layer-2 colour/illumination diagnostic.
%
%   diag = diagnose_dual_reference_frame(results_mat_path)
%   diag = diagnose_dual_reference_frame(results_struct, config_struct)
%
%   Explains *why* a dual-reference frame under-estimates NAPL saturation,
%   using only quantities already produced by the pipeline (no re-processing):
%       results.segmentation.info           - seg_info with frac diagnostics
%       results.flow_domain                  - pore mask
%       config.segmentation.water_reference.calibration.water_lab   - water Lab
%       config.segmentation.napl_reference.calibration.reference_lab - NAPL Lab
%
%   It separates the four common failure modes:
%       (1) Illumination tilt   -> centre/edge frac means differ markedly
%       (2) Ill-posed endpoints -> water & NAPL references too close in Lab
%       (3) Global under-shoot  -> frac p95 below the decision threshold
%       (4) Clamping            -> large fraction of raw frac < 0 or > 1
%
%   The figure has 6 panels; the returned struct carries the numbers and a
%   plain-text verdict (diag.verdict) summarising the most likely cause.
%
%   Run this AFTER the CAD alignment (Layer 1) is clean — a corrupted flow
%   domain will contaminate every colour statistic below.

    if nargin < 1 || isempty(results_in)
        error('diagnose_dual_reference_frame:noInput', ...
            'Provide a results.mat path or a results struct.');
    end

    % ---- Load results + config -------------------------------------------
    if ischar(results_in) || isstring(results_in)
        mat_path = char(results_in);
        if exist(mat_path, 'file') ~= 2
            error('diagnose_dual_reference_frame:fileNotFound', ...
                'File not found: %s', mat_path);
        end
        S = load(mat_path);
        if ~isfield(S, 'results')
            error('diagnose_dual_reference_frame:noResults', ...
                'MAT file has no "results" variable: %s', mat_path);
        end
        results = S.results;
        if nargin >= 2 && ~isempty(config_in)
            config = config_in;
        elseif isfield(S, 'config')
            config = S.config;
        else
            config = struct();
            warning('diagnose_dual_reference_frame:noConfig', ...
                'No config in MAT and none supplied; endpoint panels skipped.');
        end
    else
        results = results_in;
        if nargin < 2 || isempty(config_in)
            config = struct();
        else
            config = config_in;
        end
    end

    seg_info = get_field_path(results, {'segmentation', 'info'}, struct());
    if isempty(fieldnames(seg_info))
        error('diagnose_dual_reference_frame:noSegInfo', ...
            'results.segmentation.info is missing or empty.');
    end
    flow_domain = get_field_path(results, {'flow_domain'}, []);
    if isempty(flow_domain)
        error('diagnose_dual_reference_frame:noFlowDomain', ...
            'results.flow_domain is missing.');
    end
    flow_domain = logical(flow_domain);
    pore_count = max(nnz(flow_domain), 1);

    method_used = char(string(get_field(seg_info, 'method_used', ...
        get_field(seg_info, 'method', 'unknown'))));

    % ---- Pull the scalar diagnostics seg_info already carries ------------
    diag = struct();
    diag.method_used   = method_used;
    diag.pore_count    = pore_count;
    diag.frac_threshold = get_field(seg_info, 'frac_threshold', NaN);
    diag.frac_high      = get_field(seg_info, 'frac_high', NaN);
    diag.frac_low       = get_field(seg_info, 'frac_low', NaN);
    diag.frac_p05  = get_field(seg_info, 'frac_p05', NaN);
    diag.frac_p50  = get_field(seg_info, 'frac_p50', NaN);
    diag.frac_p95  = get_field(seg_info, 'frac_p95', NaN);
    diag.frac_raw_p05 = get_field(seg_info, 'frac_raw_p05', NaN);
    diag.frac_raw_p50 = get_field(seg_info, 'frac_raw_p50', NaN);
    diag.frac_raw_p95 = get_field(seg_info, 'frac_raw_p95', NaN);
    diag.frac_center_mean = get_field(seg_info, 'frac_center_mean', NaN);
    diag.frac_edge_mean   = get_field(seg_info, 'frac_edge_mean', NaN);
    diag.frac_center_edge_difference = get_field(seg_info, ...
        'frac_center_edge_difference', ...
        diag.frac_center_mean - diag.frac_edge_mean);
    diag.frac_clamped_low_fraction  = get_field(seg_info, 'frac_clamped_low_fraction', NaN);
    diag.frac_clamped_high_fraction = get_field(seg_info, 'frac_clamped_high_fraction', NaN);
    diag.invalid_endpoint_fraction  = get_field(seg_info, 'invalid_endpoint_fraction', NaN);
    diag.bulk_color_fraction_mean   = get_field(seg_info, 'bulk_color_fraction_mean', NaN);
    diag.Sn_mid   = get_field(seg_info, 'Sn_mid', NaN);
    diag.Sn_lower = get_field(seg_info, 'Sn_lower', NaN);
    diag.Sn_upper = get_field(seg_info, 'Sn_upper', NaN);

    frac_map = get_field(seg_info, 'napl_color_fraction_index', []);
    frac_raw_map = get_field(seg_info, 'napl_color_fraction_raw', []);

    % ---- Reference endpoint separation (computable from the two Lab maps) -
    water_lab = get_field_path(config, ...
        {'segmentation', 'water_reference', 'calibration', 'water_lab'}, []);
    napl_lab = get_field_path(config, ...
        {'segmentation', 'napl_reference', 'calibration', 'reference_lab'}, []);

    lab_weights = get_field(seg_info, 'dual_reference_lab_weights', [0 1 0]);
    if numel(lab_weights) ~= 3 || ~all(isfinite(lab_weights))
        lab_weights = [0 1 0];
    end

    min_endpoint_distance = get_field_path(config, ...
        {'segmentation', 'dual_reference', 'min_endpoint_distance'}, NaN);
    if ~isempty(water_lab) && ~isempty(napl_lab) && ...
            isequal(size(water_lab), size(napl_lab)) && ...
            isequal(size(water_lab, 1), size(flow_domain, 1)) && ...
            isequal(size(water_lab, 2), size(flow_domain, 2))
        dL = (napl_lab(:,:,1) - water_lab(:,:,1)) * lab_weights(1);
        dA = (napl_lab(:,:,2) - water_lab(:,:,2)) * lab_weights(2);
        dB = (napl_lab(:,:,3) - water_lab(:,:,3)) * lab_weights(3);
        dist_map = sqrt(dL.^2 + dA.^2 + dB.^2);
        endpoint_dist = dist_map(flow_domain);
        endpoint_dist = endpoint_dist(isfinite(endpoint_dist));
        diag.endpoint_distance_p05 = percentile_safe(endpoint_dist, 5);
        diag.endpoint_distance_p50 = percentile_safe(endpoint_dist, 50);
        diag.endpoint_distance_p95 = percentile_safe(endpoint_dist, 95);
    else
        diag.endpoint_distance_p05 = NaN;
        diag.endpoint_distance_p50 = NaN;
        diag.endpoint_distance_p95 = NaN;
    end
    diag.min_endpoint_distance = min_endpoint_distance;

    % ---- Heuristic verdict ------------------------------------------------
    verdict = build_verdict(diag);
    diag.verdict = verdict;

    % ---- Figure -----------------------------------------------------------
    render_figure(flow_domain, frac_map, frac_raw_map, ...
        water_lab, napl_lab, diag, verdict);

    % ---- Console summary --------------------------------------------------
    fprintf('\n=== Dual-reference Layer-2 diagnostic (%s) ===\n', method_used);
    fprintf('  Sn_mid                  : %.4f  [%.4f, %.4f]\n', ...
        diag.Sn_mid, diag.Sn_lower, diag.Sn_upper);
    fprintf('  bulk colour fraction    : %.4f\n', diag.bulk_color_fraction_mean);
    fprintf('  frac p05/p50/p95        : %.3f / %.3f / %.3f  (thresh=%.3f)\n', ...
        diag.frac_p05, diag.frac_p50, diag.frac_p95, diag.frac_threshold);
    fprintf('  frac centre / edge      : %.3f / %.3f  (diff=%.3f)\n', ...
        diag.frac_center_mean, diag.frac_edge_mean, diag.frac_center_edge_difference);
    fprintf('  clamped low / high      : %.3f / %.3f\n', ...
        diag.frac_clamped_low_fraction, diag.frac_clamped_high_fraction);
    fprintf('  invalid endpoint frac   : %.3f\n', diag.invalid_endpoint_fraction);
    fprintf('  endpoint dist p05/50/95 : %.2f / %.2f / %.2f  (min req=%.2f)\n', ...
        diag.endpoint_distance_p05, diag.endpoint_distance_p50, ...
        diag.endpoint_distance_p95, diag.min_endpoint_distance);
    fprintf('  VERDICT:\n');
    for k = 1:numel(verdict)
        fprintf('    - %s\n', verdict{k});
    end
    fprintf('\n');
end


% =========================================================================
function verdict = build_verdict(d)
    verdict = {};

    if isfinite(d.frac_center_edge_difference) && ...
            abs(d.frac_center_edge_difference) > 0.15
        verdict{end+1} = sprintf(['Illumination tilt suspected: centre vs edge ' ...
            'frac differ by %.2f (>0.15). Residual low-order lighting is biasing ' ...
            'frac spatially.'], d.frac_center_edge_difference); %#ok<AGROW>
    end

    if isfinite(d.endpoint_distance_p50) && isfinite(d.min_endpoint_distance) && ...
            d.endpoint_distance_p50 < 1.5 * d.min_endpoint_distance
        verdict{end+1} = sprintf(['Endpoints nearly collinear: median water->NAPL ' ...
            'distance %.2f is close to the %.2f minimum. Dual-reference is ' ...
            'ill-posed where references overlap.'], ...
            d.endpoint_distance_p50, d.min_endpoint_distance); %#ok<AGROW>
    end

    if isfinite(d.invalid_endpoint_fraction) && d.invalid_endpoint_fraction > 0.10
        verdict{end+1} = sprintf(['High invalid-endpoint fraction (%.2f > 0.10): ' ...
            'many pores have unusable per-pixel references; global fallback or ' ...
            'illumination unification likely needed.'], ...
            d.invalid_endpoint_fraction); %#ok<AGROW>
    end

    if isfinite(d.frac_p95) && isfinite(d.frac_threshold) && ...
            d.frac_p95 < d.frac_threshold
        verdict{end+1} = sprintf(['Global under-shoot: even frac p95 (%.2f) is below ' ...
            'the decision threshold (%.2f). The frame sits near the WATER endpoint ' ...
            'everywhere -> check illumination/encoding/NAPL reference, not just ' ...
            'thresholds.'], d.frac_p95, d.frac_threshold); %#ok<AGROW>
    end

    if isfinite(d.frac_clamped_low_fraction) && d.frac_clamped_low_fraction > 0.10
        verdict{end+1} = sprintf(['Heavy low clamping (%.2f of pores have raw frac<0): ' ...
            'frame is bluer/greener than the water reference -> illumination/white ' ...
            'balance mismatch between frame and reference.'], ...
            d.frac_clamped_low_fraction); %#ok<AGROW>
    end

    if isempty(verdict)
        verdict{end+1} = ['No dominant failure signature. frac distribution, ' ...
            'endpoints, and spatial balance all look reasonable; if Sn is still ' ...
            'low, revisit Layer-1 CAD alignment or the NAPL reference itself.'];
    end
end


% =========================================================================
function render_figure(flow_domain, frac_map, frac_raw_map, ...
        water_lab, napl_lab, d, verdict)

    fig = figure('Name', 'Dual-reference Layer-2 diagnostic', ...
        'Color', 'w', 'Position', [40 40 1500 940]); %#ok<NASGU>

    % Panel 1: frac map
    subplot(2,3,1);
    if ~isempty(frac_map)
        show = frac_map;  show(~flow_domain) = NaN;
        imagesc(show, 'AlphaData', ~isnan(show)); axis image off;
        caxis([0 1]); colormap(gca, parula); colorbar;
        title(sprintf('NAPL colour fraction  (%s)', d.method_used), ...
            'Interpreter', 'none');
    else
        text(0.5, 0.5, 'frac map not stored', 'HorizontalAlignment', 'center');
        axis off;  title('NAPL colour fraction');
    end

    % Panel 2: frac histogram (clamped) with thresholds
    subplot(2,3,2);
    if ~isempty(frac_map)
        v = frac_map(flow_domain);  v = v(isfinite(v));
        histogram(v, linspace(0,1,50), 'FaceColor', [0.2 0.4 0.8], ...
            'EdgeColor', 'none'); hold on;
        draw_vline(d.frac_threshold, [0.85 0.1 0.1], 'thresh');
        draw_vline(d.frac_high, [0.1 0.6 0.1], 'high');
        draw_vline(d.frac_low,  [0.9 0.6 0.0], 'low');
        xlabel('clamped frac'); ylabel('pore pixels'); xlim([0 1]);
        title(sprintf('frac hist  (p05/50/95 = %.2f/%.2f/%.2f)', ...
            d.frac_p05, d.frac_p50, d.frac_p95));
    else
        axis off; title('frac hist');
    end

    % Panel 3: raw frac histogram (shows clamping mass at <0 and >1)
    subplot(2,3,3);
    if ~isempty(frac_raw_map)
        vr = frac_raw_map(flow_domain);  vr = vr(isfinite(vr));
        edges = linspace(-0.5, 1.5, 60);
        histogram(vr, edges, 'FaceColor', [0.5 0.5 0.5], 'EdgeColor', 'none');
        hold on;
        draw_vline(0, [0.1 0.1 0.1], '0');
        draw_vline(1, [0.1 0.1 0.1], '1');
        xlabel('raw frac'); ylabel('pore pixels'); xlim([-0.5 1.5]);
        title(sprintf('raw frac  (clamp lo/hi = %.2f/%.2f)', ...
            d.frac_clamped_low_fraction, d.frac_clamped_high_fraction));
    else
        axis off; title('raw frac hist');
    end

    % Panel 4: centre vs edge frac
    subplot(2,3,4);
    vals = [d.frac_center_mean, d.frac_edge_mean];
    vals(~isfinite(vals)) = 0;
    b = bar(vals, 0.6); b.FaceColor = 'flat';
    b.CData(1,:) = [0.85 0.33 0.10];  b.CData(2,:) = [0.0 0.45 0.74];
    set(gca, 'XTickLabel', {'centre', 'edge'});
    ylabel('mean frac'); ylim([0 1]);
    title(sprintf('centre vs edge  (diff=%.3f)', d.frac_center_edge_difference));

    % Panel 5: reference endpoint separation
    subplot(2,3,5);
    if ~isempty(water_lab) && ~isempty(napl_lab) && ...
            isequal(size(water_lab,1), size(flow_domain,1)) && ...
            isequal(size(water_lab,2), size(flow_domain,2))
        wa = water_lab(:,:,2);  na = napl_lab(:,:,2);
        wa = wa(flow_domain);   na = na(flow_domain);
        edges = linspace(min([wa;na]), max([wa;na]), 50);
        histogram(wa, edges, 'FaceColor', [0.0 0.45 0.74], ...
            'FaceAlpha', 0.55, 'EdgeColor', 'none'); hold on;
        histogram(na, edges, 'FaceColor', [0.85 0.10 0.10], ...
            'FaceAlpha', 0.55, 'EdgeColor', 'none');
        legend({'water a*', 'NAPL a*'}, 'Location', 'best');
        xlabel('a* (pore)'); ylabel('pixels');
        title(sprintf('reference a* separation  (endpt p50=%.1f)', ...
            d.endpoint_distance_p50));
    else
        text(0.5, 0.5, 'reference Lab not in config', ...
            'HorizontalAlignment', 'center'); axis off;
        title('reference a* separation');
    end

    % Panel 6: text verdict
    subplot(2,3,6); axis off;
    lines = {sprintf('Sn_{mid} = %.3f  [%.3f, %.3f]', ...
        d.Sn_mid, d.Sn_lower, d.Sn_upper); ...
        sprintf('bulk colour fraction = %.3f', d.bulk_color_fraction_mean); ...
        sprintf('invalid endpoint frac = %.3f', d.invalid_endpoint_fraction); ...
        ''; 'VERDICT:'};
    lines = [lines; verdict(:)];
    text(0.02, 0.98, wrap_lines(lines, 60), 'VerticalAlignment', 'top', ...
        'FontSize', 9, 'Interpreter', 'none');

    try
        sgtitle('Dual-reference Layer-2 colour / illumination diagnostic', ...
            'FontWeight', 'bold');
    catch
    end
end


% =========================================================================
function draw_vline(x, color, label)
    if ~isfinite(x), return; end
    yl = ylim;
    plot([x x], yl, '--', 'Color', color, 'LineWidth', 1.5);
    text(x, yl(2)*0.95, label, 'Color', color, 'FontSize', 8, ...
        'Rotation', 90, 'VerticalAlignment', 'bottom');
end


function out = wrap_lines(lines, width)
    out = {};
    for i = 1:numel(lines)
        s = lines{i};
        while numel(s) > width
            brk = find(s(1:width) == ' ', 1, 'last');
            if isempty(brk), brk = width; end
            out{end+1} = s(1:brk); %#ok<AGROW>
            s = ['  ' strtrim(s(brk+1:end))];
        end
        out{end+1} = s; %#ok<AGROW>
    end
    out = char(out);
end


function p = percentile_safe(v, q)
    v = v(isfinite(v));
    if isempty(v), p = NaN; return; end
    p = interp1(linspace(0, 100, numel(v)), sort(v), q, 'linear', 'extrap');
end


function value = get_field(s, name, default_value)
    if isstruct(s) && isfield(s, name) && ~isempty(s.(name))
        value = s.(name);
    else
        value = default_value;
    end
end


function value = get_field_path(s, path, default_value)
    value = s;
    for i = 1:numel(path)
        if isstruct(value) && isfield(value, path{i})
            value = value.(path{i});
        else
            value = default_value;
            return;
        end
    end
    if isempty(value)
        value = default_value;
    end
end
