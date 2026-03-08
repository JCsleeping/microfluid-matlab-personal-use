function qc = phase0_precheck(results, config, fconfig)
% PHASE0_PRECHECK  Data precheck with three-phase decoupling.
%
%   qc = phase0_precheck(results, config, fconfig)
%
%   Critical: extracts solid_mask to achieve three-phase space decoupling:
%     solid_mask -> pore_space = flow_domain (already = chip & ~solid)
%     water_mask = pore_space & ~dnapl_mask
%   Ensures solid pillars are NEVER counted as water or effective flow area.
%
%   Inputs:
%       results - Output struct from main_DNAPL_pipeline
%       config  - Pipeline config struct
%       fconfig - Fingering analysis config
%
%   Output:
%       qc - Struct with validated masks, pixel_size, pore_scale

    fprintf('\n=== Phase 0: Data Precheck (Three-Phase Decoupling) ===\n');

    qc.pass = true;

    %% 0.1 Extract core masks
    qc.flow_domain = results.flow_domain;
    qc.dnapl_mask  = results.dnapl_mask;
    qc.ref_image   = results.ref_image;

    % Solid mask: from pipeline results or derived
    if isfield(results, 'solid_mask')
        qc.solid_mask = results.solid_mask;
        fprintf('  solid_mask loaded from pipeline results.\n');
    else
        % Fallback: derive from flow_domain
        % flow_domain = chip_interior & ~solid_mask, so we approximate
        chip_hull = imfill(qc.flow_domain, 'holes');
        qc.solid_mask = chip_hull & ~qc.flow_domain;
        fprintf('  solid_mask derived from flow_domain (fallback).\n');
    end

    %% 0.2 Three-phase decoupling
    % pore_space = flow_domain (already excludes solid pillars)
    qc.pore_space = qc.flow_domain;

    % water_mask = pore space minus DNAPL (NOT flow_domain minus DNAPL)
    qc.water_mask = qc.pore_space & ~qc.dnapl_mask;

    %% 0.3 Pixel size and pore scale
    if isfield(config, 'physical') && isfield(config.physical, 'pixel_size')
        qc.pixel_size = config.physical.pixel_size;
    else
        qc.pixel_size = [];
    end

    % Estimate average pore scale for threshold anchoring
    qc.pore_scale = estimate_pore_scale(qc.pore_space, qc.solid_mask);

    % Flow direction
    qc.flow_direction = fconfig.flow_direction;
    qc.inlet_side     = fconfig.inlet_side;

    %% 0.4 Quality report
    solid_area = sum(qc.solid_mask(:));
    pore_area  = sum(qc.pore_space(:));
    dnapl_area = sum(qc.dnapl_mask(:) & qc.pore_space(:));
    water_area = sum(qc.water_mask(:));
    total_px   = numel(qc.flow_domain);

    fprintf('  Flow direction: %s, Inlet: %s\n', qc.flow_direction, qc.inlet_side);
    fprintf('  Pixel size: ');
    if ~isempty(qc.pixel_size), fprintf('%.2f um\n', qc.pixel_size*1e6);
    else, fprintf('not calibrated\n'); end
    fprintf('  Pore scale: %.1f px\n', qc.pore_scale);
    fprintf('  --- Three-Phase Budget ---\n');
    fprintf('    Solid pillars:  %d px\n', solid_area);
    fprintf('    Pore space:     %d px (denominator for Sr)\n', pore_area);
    fprintf('    DNAPL in pore:  %d px (Sr = %.4f)\n', dnapl_area, dnapl_area/max(pore_area,1));
    fprintf('    Water in pore:  %d px (Sw = %.4f)\n', water_area, water_area/max(pore_area,1));
    fprintf('    Budget check:   DNAPL+Water = %d, Pore = %d, diff = %d\n', ...
        dnapl_area+water_area, pore_area, pore_area - dnapl_area - water_area);

    if pore_area < 0.05 * total_px
        warning('phase0:smallPore', 'Pore space < 5%% of image.');
        qc.pass = false;
    end
    if water_area == 0
        warning('phase0:noWater', 'Water mask is empty.');
        qc.pass = false;
    end

    %% 0.5 QC overlay figure with solid boundaries (skip in batch mode)
    show_qc_figure = true;
    if isfield(fconfig, 'batch_mode') && fconfig.batch_mode
        show_qc_figure = false;
    end

    if show_qc_figure
        fig = figure('Name', 'Phase 0: Three-Phase QC', ...
            'Position', [50 50 1400 700], 'Color', 'w');

        % Panel 1: Original
        subplot(2,3,1); imshow(qc.ref_image);
        title('(a) Original', 'FontSize', 11);

        % Panel 2: Solid mask
        subplot(2,3,2); imshow(qc.ref_image); hold on;
        solid_boundary = bwperim(qc.solid_mask);
        [sr, sc] = find(solid_boundary);
        plot(sc, sr, 'y.', 'MarkerSize', 1);
        title(sprintf('(b) Solid Pillars (%d px)', solid_area), 'FontSize', 11);

        % Panel 3: Pore space
        subplot(2,3,3);
        pore_vis = uint8(cat(3, ...
            uint8(qc.pore_space)*50, ...
            uint8(qc.pore_space)*50, ...
            uint8(qc.pore_space)*80));
        imshow(pore_vis + uint8(~qc.pore_space)*30);
        title(sprintf('(c) Pore Space (%d px)', pore_area), 'FontSize', 11);

        % Panel 4: DNAPL overlay + solid boundary
        subplot(2,3,4); imshow(qc.ref_image); hold on;
        red_ov = cat(3, ones(size(qc.dnapl_mask)), zeros(size(qc.dnapl_mask)), zeros(size(qc.dnapl_mask)));
        h = imshow(red_ov); set(h, 'AlphaData', 0.4*double(qc.dnapl_mask));
        plot(sc, sr, 'y.', 'MarkerSize', 1);
        title(sprintf('(d) DNAPL (Sr=%.3f)', dnapl_area/max(pore_area,1)), 'FontSize', 11);

        % Panel 5: Water overlay + solid boundary
        subplot(2,3,5); imshow(qc.ref_image); hold on;
        blue_ov = cat(3, zeros(size(qc.water_mask)), zeros(size(qc.water_mask)), ones(size(qc.water_mask)));
        h2 = imshow(blue_ov); set(h2, 'AlphaData', 0.4*double(qc.water_mask));
        plot(sc, sr, 'y.', 'MarkerSize', 1);
        title(sprintf('(e) Water (Sw=%.3f)', water_area/max(pore_area,1)), 'FontSize', 11);

        % Panel 6: Three-phase combined
        subplot(2,3,6);
        combined = im2double(qc.ref_image);
        r_ch = combined(:,:,1); g_ch = combined(:,:,2); b_ch = combined(:,:,3);
        r_ch(qc.dnapl_mask) = min(r_ch(qc.dnapl_mask)+0.4, 1);
        b_ch(qc.water_mask) = min(b_ch(qc.water_mask)+0.4, 1);
        r_ch(qc.solid_mask) = r_ch(qc.solid_mask)*0.5;
        g_ch(qc.solid_mask) = g_ch(qc.solid_mask)*0.5+0.3;
        b_ch(qc.solid_mask) = b_ch(qc.solid_mask)*0.5;
        imshow(cat(3, r_ch, g_ch, b_ch));
        title('(f) Three-Phase (R=NAPL, B=Water, G=Solid)', 'FontSize', 11);

        sgtitle('Phase 0: Three-Phase Decoupling QC', 'FontSize', 14, 'FontWeight', 'bold');

        if isfield(config, 'output_path') && isfolder(config.output_path)
            qc_dir = fullfile(config.output_path, 'fingering_qc');
            if ~isfolder(qc_dir), mkdir(qc_dir); end
            saveas(fig, fullfile(qc_dir, 'phase0_three_phase_qc.png'));
            fprintf('  QC figure saved.\n');
        end
    end

    fprintf('  Phase 0 complete. Pass = %s\n', string(qc.pass));
end


function pore_scale = estimate_pore_scale(pore_space, solid_mask)
% ESTIMATE_PORE_SCALE  Estimate average pore throat size.
%   Uses distance transform of pore space from solid boundaries.
    D = bwdist(solid_mask | ~pore_space);
    pore_radii = D(pore_space);
    pore_radii = pore_radii(pore_radii > 0);
    if ~isempty(pore_radii)
        pore_scale = 2 * median(pore_radii);  % diameter
    else
        pore_scale = 10;  % fallback
    end
    fprintf('  Estimated pore scale: %.1f px (median pore throat diameter)\n', pore_scale);
end
