function visualize_fingering(ref_image, fres, config)
% VISUALIZE_FINGERING  QC overlays with solid_mask boundaries.
%
%   All overlays include solid pillar boundaries (yellow dots).

    fprintf('  Generating fingering QC figures...\n');

    output_dir = '';
    if isfield(config, 'output_path') && isfolder(config.output_path)
        output_dir = fullfile(config.output_path, 'fingering_qc');
        if ~isfolder(output_dir), mkdir(output_dir); end
    end

    % Solid boundary for all overlays
    if isfield(fres, 'qc') && isfield(fres.qc, 'solid_mask')
        solid_bnd = bwperim(fres.qc.solid_mask);
        [sb_r, sb_c] = find(solid_bnd);
        has_solid = true;
    else
        sb_r = []; sb_c = []; has_solid = false;
    end

    %% Figure 1: Skeleton overlay with solid boundaries
    fig1 = figure('Name', 'Fingering: Skeleton Overlay', ...
        'Position', [50 50 1200 600], 'Color', 'w');

    subplot(1,2,1);
    imshow(ref_image); hold on;
    if has_solid, plot(sb_c, sb_r, 'y.', 'MarkerSize', 1); end
    if isfield(fres, 'napl') && isfield(fres.napl, 'skeleton') && isfield(fres.napl.skeleton, 'best_idx')
        skel = fres.napl.skeleton.pruned(fres.napl.skeleton.best_idx).skeleton;
        [sr, sc] = find(skel); plot(sc, sr, 'r.', 'MarkerSize', 1);
    end
    title('(a) NAPL Skeleton + Solid', 'FontSize', 12);

    subplot(1,2,2);
    imshow(ref_image); hold on;
    if has_solid, plot(sb_c, sb_r, 'y.', 'MarkerSize', 1); end
    if isfield(fres, 'water') && isfield(fres.water, 'skeleton') && isfield(fres.water.skeleton, 'best_idx')
        skel_w = fres.water.skeleton.pruned(fres.water.skeleton.best_idx).skeleton;
        [sr, sc] = find(skel_w); plot(sc, sr, 'b.', 'MarkerSize', 1);
    end
    title('(b) Water Skeleton + Solid', 'FontSize', 12);

    sgtitle('Skeleton Overlays (Yellow = Solid Boundary)', 'FontSize', 14, 'FontWeight', 'bold');
    if ~isempty(output_dir), saveas(fig1, fullfile(output_dir, 'fig1_skeleton_overlay.png')); end

    %% Figure 2: Local width heatmap with solid
    if isfield(fres, 'napl') && isfield(fres.napl, 'local_width')
        fig2 = figure('Name', 'Width Heatmap', 'Position', [50 50 1200 600], 'Color', 'w');

        subplot(1,2,1);
        imshow(ref_image); hold on;
        if has_solid, plot(sb_c, sb_r, 'y.', 'MarkerSize', 1); end
        wh = fres.napl.local_width.width_heatmap;
        h_img = imagesc(wh); set(h_img, 'AlphaData', (wh > 0) * 0.7);
        colormap(gca, jet); colorbar;
        title('(a) NAPL Width [px] (solid-bounded)', 'FontSize', 12);

        subplot(1,2,2);
        histogram(fres.napl.local_width.local_widths_px, 50, 'FaceColor', [0.8 0.2 0.2]);
        xlabel('Local Width [px]'); ylabel('Count');
        title(sprintf('(b) Distribution (median=%.1f px)', ...
            fres.napl.local_width.median_width_px), 'FontSize', 12);

        sgtitle('NAPL Width (Solid-Wall-Bounded)', 'FontSize', 14, 'FontWeight', 'bold');
        if ~isempty(output_dir), saveas(fig2, fullfile(output_dir, 'fig2_width_heatmap.png')); end
    end

    %% Figure 3: Backbone + Fingers with solid
    if isfield(fres, 'water') && isfield(fres.water, 'backbone') && ...
            isfield(fres.water.backbone, 'backbone_mask') && any(fres.water.backbone.backbone_mask(:))
        fig3 = figure('Name', 'Backbone & Fingers', 'Position', [50 50 900 750], 'Color', 'w');
        imshow(ref_image); hold on;
        if has_solid, plot(sb_c, sb_r, 'y.', 'MarkerSize', 1); end

        [br, bc] = find(fres.water.backbone.backbone_mask);
        plot(bc, br, 'g.', 'MarkerSize', 2);

        if isfield(fres.water, 'fingers') && isfield(fres.water.fingers, 'finger_mask')
            [fr, fc] = find(fres.water.fingers.finger_mask);
            if ~isempty(fr), plot(fc, fr, 'c.', 'MarkerSize', 2); end
        end

        if isfield(fres.water, 'fingers') && isfield(fres.water.fingers, 'fingers')
            for k = 1:numel(fres.water.fingers.fingers)
                f = fres.water.fingers.fingers(k);
                text(f.tip_col, f.tip_row, sprintf('%d', k), ...
                    'Color', 'y', 'FontSize', 10, 'FontWeight', 'bold');
            end
        end

        n_f = 0; tau_bb = NaN;
        if isfield(fres.water, 'fingers') && isfield(fres.water.fingers, 'num_fingers')
            n_f = fres.water.fingers.num_fingers; end
        if isfield(fres.water, 'tortuosity') && isfield(fres.water.tortuosity, 'tau_backbone')
            tau_bb = fres.water.tortuosity.tau_backbone; end

        title(sprintf('Backbone + %d Fingers (\\tau_{bb}=%.2f)', n_f, tau_bb), 'FontSize', 13);
        legend({'Solid boundary', 'Backbone', 'Fingers'}, 'Location', 'southeast', ...
            'TextColor', 'w', 'Color', [0.2 0.2 0.2]);

        if ~isempty(output_dir), saveas(fig3, fullfile(output_dir, 'fig3_backbone_fingers.png')); end
    end

    %% Figure 4: Summary
    fig4 = figure('Name', 'Summary', 'Position', [50 50 600 500], 'Color', 'w'); axis off;
    lines = {'=== Fingering Analysis Summary (Physics-Enhanced) ===', ''};

    if isfield(fres, 'napl') && isfield(fres.napl, 'residual')
        r = fres.napl.residual;
        lines{end+1} = '--- Residual NAPL ---';
        lines{end+1} = sprintf('  Sr = %.4f (denom=pore_space)', r.Sr);
        lines{end+1} = sprintf('  Nc = %d, Euler = %d', r.Nc, r.EulerNumber);
        lines{end+1} = sprintf('  Holes: physical=%d, pseudo(pillar)=%d', r.beta_1, r.beta_1_pseudo);
    end
    if isfield(fres, 'napl') && isfield(fres.napl, 'local_width')
        w = fres.napl.local_width;
        lines{end+1} = sprintf('  Width: mean=%.1f, med=%.1f, P90=%.1f px (solid-bounded)', ...
            w.mean_width_px, w.median_width_px, w.width_p90_px);
    end
    if isfield(fres, 'water') && isfield(fres.water, 'fingers')
        lines{end+1} = ''; lines{end+1} = '--- Invading Water ---';
        lines{end+1} = sprintf('  Fingers: %d', fres.water.fingers.num_fingers);
    end
    if isfield(fres, 'water') && isfield(fres.water, 'backbone')
        lines{end+1} = sprintf('  Backbone: L=%.1f px (min-resistance)', fres.water.backbone.L_backbone);
    end
    if isfield(fres, 'water') && isfield(fres.water, 'tortuosity')
        lines{end+1} = sprintf('  tau_backbone: %.3f (Euclidean denom)', fres.water.tortuosity.tau_backbone);
    end
    if isfield(fres, 'front')
        lines{end+1} = sprintf('  x_lead: %d px, A_invaded_norm: %.4f', ...
            fres.front.x_lead, fres.front.A_invaded_norm);
    end

    text(0.05, 0.95, strjoin(lines, '\n'), 'FontSize', 10, 'FontName', 'Courier', ...
        'VerticalAlignment', 'top');
    if ~isempty(output_dir), saveas(fig4, fullfile(output_dir, 'fig4_summary.png')); end

    fprintf('  QC figures saved.\n');
end
