function save_subplots(fig, output_path, group_id, fig_format)
% SAVE_SUBPLOTS  Save combined figure as X-0 and each subplot as X-1..X-N.
%
%   save_subplots(fig, output_path, group_id, fig_format)
%
%   Inputs:
%       fig         - Figure handle
%       output_path - Directory to save into
%       group_id    - Group number (1=preprocessing, 2=segmentation, ...)
%       fig_format  - File extension ('png', 'fig', etc.)
%
%   Output files:
%       <group_id>-0_combined.<fmt>   — full figure with all subplots
%       <group_id>-1_<title>.<fmt>    — first subplot
%       <group_id>-2_<title>.<fmt>    — second subplot, etc.

    if nargin < 4, fig_format = 'png'; end

    % Save combined figure as X-0
    combined_name = sprintf('%d-0_combined.%s', group_id, fig_format);
    saveas(fig, fullfile(output_path, combined_name));
    fprintf('    Saved: %s\n', combined_name);

    % Find all axes that are subplots (exclude legends, colorbars, etc.)
    all_axes = findobj(fig, 'Type', 'axes');

    % Filter: keep only axes with visible content (not annotation axes)
    subplot_axes = [];
    for i = 1:numel(all_axes)
        ax = all_axes(i);
        % Skip invalid handles
        if ~isvalid(ax), continue; end
        % Skip colorbar axes and legend axes
        if isa(ax, 'matlab.graphics.illustration.ColorBar') || ...
           isa(ax, 'matlab.graphics.illustration.Legend')
            continue;
        end
        % Skip axes with Tag 'Colorbar' or 'legend'
        if any(strcmpi(ax.Tag, {'Colorbar', 'legend', 'sgtitle'}))
            continue;
        end
        subplot_axes = [subplot_axes; ax]; %#ok<AGROW>
    end

    % Sort axes by position: top-left to bottom-right (row-major order)
    if isempty(subplot_axes), return; end

    positions = cell2mat(arrayfun(@(a) a.Position, subplot_axes, 'UniformOutput', false));
    % Sort by row (top=high Y first), then by column (left=low X first)
    row_score = -positions(:,2);  % negate Y so top comes first
    col_score = positions(:,1);
    [~, sort_idx] = sortrows([row_score, col_score]);
    subplot_axes = subplot_axes(sort_idx);

    % Save each subplot individually
    for k = 1:numel(subplot_axes)
        ax = subplot_axes(k);

        % Create new figure with just this subplot
        new_fig = figure('Visible', 'off', 'Position', [100 100 800 600], 'Color', 'w');

        % Skip invalid handles (e.g., deleted during earlier iteration)
        if ~isvalid(ax)
            close(new_fig);
            continue;
        end

        % Copy the axes
        new_ax = copyobj(ax, new_fig);
        set(new_ax, 'Position', [0.12 0.12 0.75 0.78]);

        % Copy colorbar if one is associated
        try
            cb = findobj(fig, 'Type', 'ColorBar');
            for ci = 1:numel(cb)
                if isprop(cb(ci), 'Axes') && isequal(cb(ci).Axes, ax)
                    copyobj(cb(ci), new_fig);
                end
            end
        catch
            % No colorbar, that's fine
        end

        % Save with simple numeric name: X-1.png, X-2.png, ...
        subplot_name = sprintf('%d-%d.%s', group_id, k, fig_format);
        try
            saveas(new_fig, fullfile(output_path, subplot_name));
        catch
            % Fallback: print to file
            print(new_fig, fullfile(output_path, sprintf('%d-%d', group_id, k)), '-dpng');
        end
        close(new_fig);
    end

    fprintf('    Saved %d individual subplots (%d-1 ~ %d-%d)\n', ...
        numel(subplot_axes), group_id, group_id, numel(subplot_axes));
end
