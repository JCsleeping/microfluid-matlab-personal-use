function visualize_fingering_timeseries(fts, config)
% VISUALIZE_FINGERING_TIMESERIES  Statistical plots for continuous fingering analysis.
%
%   visualize_fingering_timeseries(fts, config)
%
%   Generates 5 figures:
%     Fig 1: 6-panel time-series evolution (line plots with trend)
%     Fig 2: NAPL dissolution curve with rate
%     Fig 3: Histograms of key metrics
%     Fig 4: Correlation / phase diagrams
%     Fig 5: Statistical summary table
%
%   Saves all figures to output_path/fingering_qc/

    fprintf('  Generating statistical figures...\n');

    output_dir = '';
    if isfield(config, 'output_path') && isfolder(config.output_path)
        output_dir = fullfile(config.output_path, 'fingering_qc');
        if ~isfolder(output_dir), mkdir(output_dir); end
    end

    % Choose x-axis
    if isfield(fts, 'time_vector') && max(fts.time_vector) > 0
        x = fts.time_vector;
        x_label = 'Time [s]';
    else
        x = fts.frame_indices;
        x_label = 'Frame Index';
    end

    v = ~isnan(fts.Sr_vs_frame);  % valid frames mask

    % Color palette
    c1 = [0.85 0.15 0.15];  % red
    c2 = [0.90 0.50 0.10];  % orange
    c3 = [0.10 0.45 0.80];  % blue
    c4 = [0.15 0.70 0.35];  % green
    c5 = [0.55 0.20 0.75];  % purple
    c6 = [0.20 0.60 0.65];  % teal
    mk = 4;  % marker size

    %% ====================================================================
    %  Figure 1: 6-panel evolution overview (line plots)
    %  ====================================================================
    fig1 = figure('Name', 'Fingering Evolution', ...
        'Position', [30 30 1500 900], 'Color', 'w');

    % (a) Sr
    subplot(2,3,1);
    plot_with_trend(x, fts.Sr_vs_frame, c1, mk, v);
    xlabel(x_label); ylabel('S_r');
    title('(a) Residual NAPL Saturation', 'FontSize', 11);
    grid on; set(gca, 'FontSize', 9);

    % (b) Nc
    subplot(2,3,2);
    plot_with_trend(x, fts.Nc_vs_frame, c2, mk, v);
    xlabel(x_label); ylabel('N_c');
    title('(b) NAPL Components', 'FontSize', 11);
    grid on; set(gca, 'FontSize', 9);

    % (c) tau
    subplot(2,3,3);
    plot_with_trend(x, fts.tau_backbone_vs_frame, c3, mk, v);
    xlabel(x_label); ylabel('\tau_{backbone}');
    title('(c) Backbone Tortuosity', 'FontSize', 11);
    grid on; set(gca, 'FontSize', 9);

    % (d) num_fingers
    subplot(2,3,4);
    stem(x(v), fts.num_fingers_vs_frame(v), 'filled', 'Color', c4, ...
        'MarkerSize', mk, 'LineWidth', 1);
    xlabel(x_label); ylabel('Finger Count');
    title('(d) Water Fingers', 'FontSize', 11);
    grid on; set(gca, 'FontSize', 9);

    % (e) x_lead
    subplot(2,3,5);
    plot_with_trend(x, fts.x_lead_vs_frame, c5, mk, v);
    xlabel(x_label); ylabel('x_{lead} [px]');
    title('(e) Leading Front Position', 'FontSize', 11);
    grid on; set(gca, 'FontSize', 9);

    % (f) front_width_norm
    subplot(2,3,6);
    plot_with_trend(x, fts.front_width_norm_vs_frame, c6, mk, v);
    xlabel(x_label); ylabel('W_{front} / W_{domain}');
    title('(f) Normalized Front Width', 'FontSize', 11);
    grid on; set(gca, 'FontSize', 9);

    sgtitle(sprintf('Fingering Evolution (%d frames, stride=%d)', ...
        sum(v), fts.stride), 'FontSize', 14, 'FontWeight', 'bold');
    if ~isempty(output_dir)
        saveas(fig1, fullfile(output_dir, 'fig_ts_evolution.png'));
    end

    %% ====================================================================
    %  Figure 2: NAPL dissolution curve with rate
    %  ====================================================================
    fig2 = figure('Name', 'Dissolution Curve', ...
        'Position', [60 60 1000 500], 'Color', 'w');

    % Left: Sr vs time
    subplot(1,2,1);
    area(x(v), fts.Sr_vs_frame(v), 'FaceColor', [1 0.7 0.7], ...
        'EdgeColor', c1, 'LineWidth', 1.5, 'FaceAlpha', 0.5);
    hold on;
    plot(x(v), fts.Sr_vs_frame(v), '-o', 'Color', c1, ...
        'LineWidth', 1.5, 'MarkerSize', mk, 'MarkerFaceColor', c1);
    xlabel(x_label); ylabel('S_r');
    title('(a) NAPL Dissolution Curve', 'FontSize', 12);

    % Annotate start/end
    if sum(v) >= 2
        text(x(find(v,1,'first')), fts.Sr_vs_frame(find(v,1,'first')), ...
            sprintf('  %.3f', fts.Sr_vs_frame(find(v,1,'first'))), ...
            'FontSize', 9, 'Color', c1);
        text(x(find(v,1,'last')), fts.Sr_vs_frame(find(v,1,'last')), ...
            sprintf('  %.3f', fts.Sr_vs_frame(find(v,1,'last'))), ...
            'FontSize', 9, 'Color', c1);
    end
    grid on;

    % Right: dissolution rate dSr/dt
    subplot(1,2,2);
    if isfield(fts, 'stats') && isfield(fts.stats, 'dissolution_rate')
        valid_idx = find(v);
        x_rate = x(valid_idx(2:end));
        bar(x_rate, fts.stats.dissolution_rate, 1, ...
            'FaceColor', c3, 'EdgeColor', 'none', 'FaceAlpha', 0.7);
        hold on;
        yline(fts.stats.dissolution_rate_mean, '--r', ...
            sprintf('mean = %.2e', fts.stats.dissolution_rate_mean), ...
            'LineWidth', 1.5, 'FontSize', 9);
        xlabel(x_label); ylabel('dS_r/dt [1/s]');
        title('(b) Dissolution Rate', 'FontSize', 12);
        grid on;
    end

    sgtitle('NAPL Dissolution Dynamics', 'FontSize', 14, 'FontWeight', 'bold');
    if ~isempty(output_dir)
        saveas(fig2, fullfile(output_dir, 'fig_ts_dissolution.png'));
    end

    %% ====================================================================
    %  Figure 3: Histograms of key metrics
    %  ====================================================================
    fig3 = figure('Name', 'Metric Distributions', ...
        'Position', [90 90 1400 800], 'Color', 'w');

    % (a) Sr distribution
    subplot(2,3,1);
    data_a = fts.Sr_vs_frame(~isnan(fts.Sr_vs_frame));
    if ~isempty(data_a)
        histogram(data_a, 'FaceColor', c1, 'EdgeColor', 'w', 'FaceAlpha', 0.8);
        mu = mean(data_a);
        if isfinite(mu), hold on; xline(mu, '--k', sprintf('\\mu=%.3f', mu), 'LineWidth', 1.5); end
    end
    xlabel('S_r'); ylabel('Count');
    title('(a) S_r Distribution', 'FontSize', 11);

    % (b) Nc distribution
    subplot(2,3,2);
    data_b = fts.Nc_vs_frame(~isnan(fts.Nc_vs_frame));
    if ~isempty(data_b)
        histogram(data_b, 'FaceColor', c2, 'EdgeColor', 'w', 'FaceAlpha', 0.8, ...
            'BinMethod', 'integers');
        mu = mean(data_b);
        if isfinite(mu), hold on; xline(mu, '--k', sprintf('\\mu=%.1f', mu), 'LineWidth', 1.5); end
    end
    xlabel('N_c'); ylabel('Count');
    title('(b) Component Count Distribution', 'FontSize', 11);

    % (c) tau_backbone distribution
    subplot(2,3,3);
    data_c = fts.tau_backbone_vs_frame(~isnan(fts.tau_backbone_vs_frame));
    if ~isempty(data_c)
        histogram(data_c, 'FaceColor', c3, 'EdgeColor', 'w', 'FaceAlpha', 0.8);
        mu = mean(data_c);
        if isfinite(mu), hold on; xline(mu, '--k', sprintf('\\mu=%.2f', mu), 'LineWidth', 1.5); end
    end
    xlabel('\tau_{backbone}'); ylabel('Count');
    title('(c) Tortuosity Distribution', 'FontSize', 11);

    % (d) num_fingers distribution
    subplot(2,3,4);
    data_d = fts.num_fingers_vs_frame(~isnan(fts.num_fingers_vs_frame));
    if ~isempty(data_d)
        histogram(data_d, 'FaceColor', c4, 'EdgeColor', 'w', 'FaceAlpha', 0.8, ...
            'BinMethod', 'integers');
        mu = mean(data_d);
        if isfinite(mu), hold on; xline(mu, '--k', sprintf('\\mu=%.1f', mu), 'LineWidth', 1.5); end
    end
    xlabel('Finger Count'); ylabel('Count');
    title('(d) Finger Count Distribution', 'FontSize', 11);

    % (e) NAPL width distribution
    subplot(2,3,5);
    data_e = fts.napl_width_mean_vs_frame(~isnan(fts.napl_width_mean_vs_frame));
    if ~isempty(data_e)
        histogram(data_e, 'FaceColor', c5, 'EdgeColor', 'w', 'FaceAlpha', 0.8);
        mu = mean(data_e);
        if isfinite(mu), hold on; xline(mu, '--k', sprintf('\\mu=%.1f', mu), 'LineWidth', 1.5); end
    end
    xlabel('Mean Width [px]'); ylabel('Count');
    title('(e) NAPL Width Distribution', 'FontSize', 11);

    % (f) front_width_norm distribution
    subplot(2,3,6);
    data_f = fts.front_width_norm_vs_frame(~isnan(fts.front_width_norm_vs_frame));
    if ~isempty(data_f)
        histogram(data_f, 'FaceColor', c6, 'EdgeColor', 'w', 'FaceAlpha', 0.8);
        mu = mean(data_f);
        if isfinite(mu), hold on; xline(mu, '--k', sprintf('\\mu=%.3f', mu), 'LineWidth', 1.5); end
    end
    xlabel('W_{front} / W_{domain}'); ylabel('Count');
    title('(f) Front Width Distribution', 'FontSize', 11);

    sgtitle('Metric Distributions Across All Frames', ...
        'FontSize', 14, 'FontWeight', 'bold');
    if ~isempty(output_dir)
        saveas(fig3, fullfile(output_dir, 'fig_ts_histograms.png'));
    end

    %% ====================================================================
    %  Figure 4: Correlation / Phase Diagrams
    %  ====================================================================
    fig4 = figure('Name', 'Phase Diagrams', ...
        'Position', [120 120 1400 500], 'Color', 'w');

    % (a) Sr vs num_fingers — instability coupling
    subplot(1,3,1);
    vv = v & ~isnan(fts.num_fingers_vs_frame);
    if sum(vv) >= 2
        scatter(fts.Sr_vs_frame(vv), fts.num_fingers_vs_frame(vv), 40, ...
            x(vv), 'filled', 'MarkerEdgeColor', 'k', 'LineWidth', 0.5);
        colorbar_h = colorbar; ylabel(colorbar_h, x_label);
        colormap(gca, parula);
        % Add arrow showing temporal direction
        hold on;
        for i = 1:sum(vv)-1
            idx_all = find(vv);
            quiver(fts.Sr_vs_frame(idx_all(i)), fts.num_fingers_vs_frame(idx_all(i)), ...
                fts.Sr_vs_frame(idx_all(i+1)) - fts.Sr_vs_frame(idx_all(i)), ...
                fts.num_fingers_vs_frame(idx_all(i+1)) - fts.num_fingers_vs_frame(idx_all(i)), ...
                0, 'Color', [0.6 0.6 0.6], 'MaxHeadSize', 0.6, 'LineWidth', 0.5);
        end
    end
    xlabel('S_r'); ylabel('Finger Count');
    title('(a) S_r vs Fingers', 'FontSize', 12);
    grid on;

    % (b) x_lead vs A_invaded_norm — invasion efficiency
    subplot(1,3,2);
    vv2 = v & ~isnan(fts.A_invaded_norm_vs_frame);
    if sum(vv2) >= 2
        scatter(fts.x_lead_vs_frame(vv2), fts.A_invaded_norm_vs_frame(vv2), 40, ...
            x(vv2), 'filled', 'MarkerEdgeColor', 'k', 'LineWidth', 0.5);
        colorbar_h = colorbar; ylabel(colorbar_h, x_label);
        colormap(gca, parula);
    end
    xlabel('x_{lead} [px]'); ylabel('A_{invaded} / A_{pore}');
    title('(b) Front vs Invasion Efficiency', 'FontSize', 12);
    grid on;

    % (c) tau vs branch_density — network complexity evolution
    subplot(1,3,3);
    vv3 = ~isnan(fts.tau_backbone_vs_frame) & ~isnan(fts.branch_density_vs_frame);
    if sum(vv3) >= 2
        scatter(fts.tau_backbone_vs_frame(vv3), fts.branch_density_vs_frame(vv3), 40, ...
            x(vv3), 'filled', 'MarkerEdgeColor', 'k', 'LineWidth', 0.5);
        colorbar_h = colorbar; ylabel(colorbar_h, x_label);
        colormap(gca, parula);
    end
    xlabel('\tau_{backbone}'); ylabel('Branch Density [per px]');
    title('(c) Tortuosity vs Branching', 'FontSize', 12);
    grid on;

    sgtitle('Phase Diagrams (color = time)', ...
        'FontSize', 14, 'FontWeight', 'bold');
    if ~isempty(output_dir)
        saveas(fig4, fullfile(output_dir, 'fig_ts_phase_diagrams.png'));
    end

    %% ====================================================================
    %  Figure 5: Statistical summary table
    %  ====================================================================
    fig5 = figure('Name', 'Summary Statistics', ...
        'Position', [150 150 700 600], 'Color', 'w');
    axis off;

    lines = {};
    lines{end+1} = '════════════════════════════════════════════════';
    lines{end+1} = '         FINGERING TIME-SERIES SUMMARY         ';
    lines{end+1} = '════════════════════════════════════════════════';
    lines{end+1} = '';
    lines{end+1} = sprintf('  Frames analyzed:  %d / %d (stride %d)', ...
        sum(v), fts.total_frames_in_tif, fts.stride);
    if ~isempty(fts.failed_frames)
        lines{end+1} = sprintf('  Failed frames:    %d', numel(fts.failed_frames));
    end
    lines{end+1} = '';

    if isfield(fts, 'stats') && isfield(fts.stats, 'Sr')
        lines{end+1} = '  ─── NAPL Saturation (Sr) ───';
        lines{end+1} = sprintf('    Start → End:    %.4f → %.4f', ...
            fts.stats.Sr.start, fts.stats.Sr.final);
        lines{end+1} = sprintf('    Range:          [%.4f, %.4f]', ...
            fts.stats.Sr.min, fts.stats.Sr.max);
        lines{end+1} = sprintf('    Mean ± Std:     %.4f ± %.4f', ...
            fts.stats.Sr.mean, fts.stats.Sr.std);
        removal = 100 * (1 - fts.stats.Sr.final / max(fts.stats.Sr.start, eps));
        lines{end+1} = sprintf('    Removal:        %.1f%%', removal);
        lines{end+1} = '';
    end

    if isfield(fts, 'stats') && isfield(fts.stats, 'fingers')
        lines{end+1} = '  ─── Water Fingers ───';
        lines{end+1} = sprintf('    Range:          [%d, %d]', ...
            fts.stats.fingers.min, fts.stats.fingers.max);
        lines{end+1} = sprintf('    Mean ± Std:     %.1f ± %.1f', ...
            fts.stats.fingers.mean, fts.stats.fingers.std);
        lines{end+1} = '';
    end

    if isfield(fts, 'stats') && isfield(fts.stats, 'tau')
        lines{end+1} = '  ─── Backbone Tortuosity ───';
        lines{end+1} = sprintf('    Range:          [%.3f, %.3f]', ...
            fts.stats.tau.min, fts.stats.tau.max);
        lines{end+1} = sprintf('    Mean ± Std:     %.3f ± %.3f', ...
            fts.stats.tau.mean, fts.stats.tau.std);
        lines{end+1} = '';
    end

    if isfield(fts, 'stats') && isfield(fts.stats, 'front')
        lines{end+1} = '  ─── Front Advance ───';
        lines{end+1} = sprintf('    Start → End:    %d → %d px', ...
            fts.stats.front.x_start, fts.stats.front.x_final);
        lines{end+1} = sprintf('    Total advance:  %d px', fts.stats.front.advance);
    end

    text(0.05, 0.95, strjoin(lines, '\n'), ...
        'FontSize', 10, 'FontName', 'Consolas', ...
        'VerticalAlignment', 'top', 'Interpreter', 'none');

    if ~isempty(output_dir)
        saveas(fig5, fullfile(output_dir, 'fig_ts_summary.png'));
    end

    fprintf('  Statistical figures saved (%d figures).\n', 5);
end


%% ========================================================================
%  Helper: plot line with moving-average trend
%  ========================================================================
function plot_with_trend(x, y, color, mk, valid)
    if nargin < 5, valid = ~isnan(y); end
    xv = x(valid);
    yv = y(valid);

    plot(xv, yv, '-o', 'Color', color, 'LineWidth', 1.2, ...
        'MarkerSize', mk, 'MarkerFaceColor', color);

    % Add trend line if enough points
    if numel(yv) >= 7
        hold on;
        win = max(3, round(numel(yv) / 5));
        y_smooth = movmean(yv, win);
        plot(xv, y_smooth, '--', 'Color', color * 0.6, 'LineWidth', 2);
        hold off;
    end
end
