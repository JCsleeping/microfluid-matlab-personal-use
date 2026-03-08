function fig = visualize_solubilization(sol, time_vector, config)
% VISUALIZE_SOLUBILIZATION  Display DNAPL dissolution dynamics over time.
%
%   fig = visualize_solubilization(sol, time_vector, config)

    fig = figure('Name', 'Solubilization Dynamics', ...
        'Position', [50 50 1400 800], 'Color', 'w');

    % Guard: if critical inputs are empty, show placeholder and return
    if isempty(sol) || isempty(time_vector) || ...
            ~isfield(sol, 'saturation_vs_time') || isempty(sol.saturation_vs_time)
        text(0.5, 0.5, 'No solubilization data available', ...
            'HorizontalAlignment', 'center', 'FontSize', 16, 'Units', 'normalized');
        axis off;
        return;
    end

    tv = time_vector(:);

    %% Panel 1: Saturation vs time
    subplot(2,3,1);
    plot(tv, sol.saturation_vs_time, 'b-o', 'LineWidth', 2, 'MarkerSize', 6);
    xlabel('Time [s]');
    ylabel('S_n');
    title('DNAPL Saturation vs Time', 'FontSize', 11);
    grid on;

    %% Panel 2: Number of blobs vs time
    subplot(2,3,2);
    plot(tv, sol.num_blobs_vs_time, 'g-s', 'LineWidth', 2, 'MarkerSize', 6);
    xlabel('Time');
    ylabel('Number of Blobs');
    title('Blob Count Evolution', 'FontSize', 11);
    grid on;

    %% Panel 3: Mean blob size vs time
    subplot(2,3,3);
    plot(tv, sol.mean_blob_size_vs_time, 'm-^', 'LineWidth', 2, 'MarkerSize', 6);
    xlabel('Time');
    ylabel('Mean Blob Area [px]');
    title('Mean Blob Size Evolution', 'FontSize', 11);
    grid on;

    %% Panel 4: Interfacial area vs time
    subplot(2,3,4);
    plot(tv, sol.interface_area_vs_time, 'c-d', 'LineWidth', 2, 'MarkerSize', 6);
    xlabel('Time');
    ylabel('DNAPL-Water Interface [px]');
    title('Interface Evolution', 'FontSize', 11);
    grid on;

    %% Panel 5: Dissolution rate vs time
    subplot(2,3,5);
    if numel(tv) >= 2
        mid_t = (tv(1:end-1) + tv(2:end)) / 2;
        plot(mid_t, -sol.dissolution_rate, 'k-', 'LineWidth', 2);
        xlabel('Time');
        ylabel('-dS_n/dt');
        title('Dissolution Rate', 'FontSize', 11);
        grid on;
    else
        axis off;
        text(0.5, 0.5, 'Need >= 2 frames', 'HorizontalAlignment', 'center');
    end

    %% Panel 6: Cumulative dissolved mass OR summary
    subplot(2,3,6);
    if isfield(sol, 'mass_dissolved_vs_time') && any(sol.mass_dissolved_vs_time ~= 0)
        plot(tv, sol.mass_dissolved_vs_time * 1e6, 'r-p', 'LineWidth', 2, 'MarkerSize', 6);
        xlabel('Time');
        ylabel('Dissolved Mass [\mug]');
        title('Cumulative Dissolved Mass', 'FontSize', 11);
        grid on;
        % Add summary text as annotation
        Sn0 = sol.saturation_vs_time(1);
        Snf = sol.saturation_vs_time(end);
        reduction = (1 - Snf / max(Sn0, eps)) * 100;
        annotation_txt = sprintf('S_n: %.3f→%.3f (−%.0f%%),  m=%.2e kg', ...
            Sn0, Snf, reduction, sol.mass_dissolved);
        xlabel({annotation_txt, 'Time'}, 'FontSize', 9);
    else
        axis off;
        Sn0 = sol.saturation_vs_time(1);
        Snf = sol.saturation_vs_time(end);
        reduction = (1 - Snf / max(Sn0, eps)) * 100;
        txt = {
            'Solubilization Summary'
            '----------------------------'
            sprintf('Initial S_n:    %.4f', Sn0)
            sprintf('Final S_n:      %.4f', Snf)
            sprintf('Reduction:      %.1f%%', reduction)
            ''
            sprintf('Initial blobs:  %d', sol.num_blobs_vs_time(1))
            sprintf('Final blobs:    %d', sol.num_blobs_vs_time(end))
        };
        if isfield(sol, 'mass_dissolved') && ~isnan(sol.mass_dissolved)
            txt{end+1} = '';
            txt{end+1} = sprintf('Mass dissolved: %.2e kg', sol.mass_dissolved);
        end
        text(0.05, 0.95, txt, 'VerticalAlignment', 'top', ...
            'FontSize', 10, 'FontName', 'FixedWidth');
    end

    sgtitle('DNAPL Dissolution Dynamics', 'FontSize', 14, 'FontWeight', 'bold');

    if config.visualization.save_figures
        save_subplots(fig, config.output_path, 5, config.visualization.figure_format);
    end
end
