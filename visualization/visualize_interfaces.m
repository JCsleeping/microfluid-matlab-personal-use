function fig = visualize_interfaces(dnapl_mask, flow_domain, iface, config)
% VISUALIZE_INTERFACES  Display DNAPL interface analysis results.
%
%   fig = visualize_interfaces(dnapl_mask, flow_domain, iface, config)
%
%   Shows DNAPL-water interfaces in green and DNAPL-solid contacts in
%   yellow, overlaid on the three-phase map.

    fig = figure('Name', 'Interface Analysis', ...
        'Position', [50 50 1400 700], 'Color', 'w');

    % Guard: if critical inputs are empty, show placeholder and return
    if isempty(dnapl_mask) || isempty(flow_domain) || isempty(iface)
        text(0.5, 0.5, 'No interface data available', ...
            'HorizontalAlignment', 'center', 'FontSize', 16, 'Units', 'normalized');
        axis off;
        return;
    end

    %% Panel 1: Combined interface overlay (large panel)
    subplot(2,3,[1 4]);
    % Build base image: solid=dark gray, water=light gray, DNAPL=red
    base = zeros([size(flow_domain), 3], 'uint8');
    solid = ~flow_domain;
    water = flow_domain & ~dnapl_mask;
    % Use double for arithmetic to avoid uint8 overflow, convert at end
    base_d = zeros([size(flow_domain), 3]);
    base_d(:,:,1) = double(solid)*80  + double(water)*200 + double(dnapl_mask)*200;
    base_d(:,:,2) = double(solid)*80  + double(water)*200 + double(dnapl_mask)*60;
    base_d(:,:,3) = double(solid)*80  + double(water)*200 + double(dnapl_mask)*60;

    % Overlay interfaces using logical masking (no uint8 arithmetic issues)
    gw = iface.dnapl_water_interface;  % green
    ys = iface.dnapl_solid_interface;  % yellow

    % Apply green for DNAPL-water interface
    base_d(:,:,1) = base_d(:,:,1) .* ~gw;
    base_d(:,:,2) = base_d(:,:,2) .* ~gw + double(gw) * 255;
    base_d(:,:,3) = base_d(:,:,3) .* ~gw;

    % Apply yellow for DNAPL-solid interface (overwrites green where both exist)
    base_d(:,:,1) = base_d(:,:,1) .* ~ys + double(ys) * 255;
    base_d(:,:,2) = base_d(:,:,2) .* ~ys + double(ys) * 255;
    base_d(:,:,3) = base_d(:,:,3) .* ~ys;

    base = uint8(min(max(base_d, 0), 255));

    imshow(base);
    title('Interface Map', 'FontSize', 12);
    % Add legend as text (normalized units, bottom-left corner)
    text(0.02, 0.08, 'Green = DNAPL-Water', 'Units', 'normalized', ...
        'Color', [0 1 0], 'FontSize', 10, 'FontWeight', 'bold', ...
        'BackgroundColor', [0.1 0.1 0.1], 'Margin', 3);
    text(0.02, 0.02, 'Yellow = DNAPL-Solid', 'Units', 'normalized', ...
        'Color', [1 1 0], 'FontSize', 10, 'FontWeight', 'bold', ...
        'BackgroundColor', [0.1 0.1 0.1], 'Margin', 3);

    %% Panel 2: DNAPL-water interface
    subplot(2,3,2);
    imshow(gw);
    title(sprintf('DNAPL-Water Interface\n%.0f px', iface.dnapl_water_length_px), 'FontSize', 10);

    %% Panel 3: DNAPL-solid interface
    subplot(2,3,3);
    imshow(ys);
    title(sprintf('DNAPL-Solid Contact\n%.0f px', iface.dnapl_solid_length_px), 'FontSize', 10);

    %% Panel 4: Per-blob interface bar chart
    subplot(2,3,5);
    n_blobs = numel(iface.per_blob_interfaces);
    if n_blobs > 0 && n_blobs <= 30
        water_vals = [iface.per_blob_interfaces.water_px];
        solid_vals = [iface.per_blob_interfaces.solid_px];
        bar_data = [water_vals(:), solid_vals(:)];
        bar(bar_data, 'stacked');
        colororder([0.2 0.8 0.2; 0.9 0.9 0.1]);
        xlabel('Blob ID');
        ylabel('Interface Length [px]');
        legend('Water', 'Solid', 'Location', 'best');
        title('Per-Blob Interfaces', 'FontSize', 10);
    elseif n_blobs > 30
        contact_fracs = [iface.per_blob_interfaces.contact_fraction];
        histogram(contact_fracs, 20, 'FaceColor', [0.9 0.6 0.2]);
        xlabel('Solid Contact Fraction');
        ylabel('Count');
        title('Contact Fraction Distribution', 'FontSize', 10);
    else
        axis off;
        text(0.5, 0.5, 'No blobs', 'HorizontalAlignment', 'center');
    end
    grid on;

    %% Panel 5: Summary statistics
    subplot(2,3,6);
    axis off;
    total = iface.dnapl_water_length_px + iface.dnapl_solid_length_px;
    wf = iface.dnapl_water_length_px / max(total, 1);

    txt = {
        'Interface Summary'
        '--------------------------'
        sprintf('DNAPL-Water: %.0f px', iface.dnapl_water_length_px)
        sprintf('DNAPL-Solid: %.0f px', iface.dnapl_solid_length_px)
        sprintf('Total:       %.0f px', total)
        ''
        sprintf('Water fraction: %.1f%%', wf * 100)
        sprintf('Solid fraction: %.1f%%', (1 - wf) * 100)
        ''
        sprintf('a_nw = %.2f [1/px or m^-^1]', iface.specific_interfacial_area)
    };
    text(0.05, 0.95, txt, 'VerticalAlignment', 'top', ...
        'FontSize', 10, 'FontName', 'FixedWidth');

    sgtitle('DNAPL Interface Analysis', 'FontSize', 14, 'FontWeight', 'bold');

    if config.visualization.save_figures
        save_subplots(fig, config.output_path, 4, config.visualization.figure_format);
    end
end
