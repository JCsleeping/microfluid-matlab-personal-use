function generate_toa_map(mat_path, pixel_size_um, label, output_dir, pages, tif_path, soil_img)
% GENERATE_TOA_MAP  Generate Time-of-Arrival heatmap from pipeline results.
%
%   generate_toa_map(mat_path, pixel_size_um, label, output_dir, pages, tif_path, soil_img)
%
%   Inputs:
%       mat_path      - Path to results_*.mat (must contain 'config')
%       pixel_size_um - Pixel size in µm/px (overrides config if given)
%       label         - Experiment label, e.g. 'BD-4' (used in filenames)
%       output_dir    - Directory to save figures (default: same as mat)
%       pages         - (optional) Page indices to process, e.g. 1:500
%       tif_path      - (optional) Override TIF file path from config
%       soil_img      - (optional) Path to soil-only reference image (TIF)
%                       and page number as {path, page}, e.g. {'data.tif', 5}
%                       Or just a path string (uses page 1)
%                       When provided, generates extra figures:
%                       grey=solid, black=NAPL, white=water
%
%   Examples:
%       generate_toa_map('...results.mat', 4.28, 'BD-4')
%       generate_toa_map('...results.mat', 4.28, 'BD-4', [], 41:48, 'data.tif', {'data.tif', 3})
%
%   See also: main_DNAPL_pipeline, characterize_solubilization_v2

    %% ====================================================================
    %  Setup
    %  ====================================================================
    if nargin < 4 || isempty(output_dir)
        output_dir = fileparts(mat_path);
    end
    if nargin < 5, pages = []; end
    if nargin < 6, tif_path = ''; end
    if nargin < 7, soil_img = ''; end
    if ~isfolder(output_dir), mkdir(output_dir); end

    % Add pipeline to path
    pipeline_root = 'D:\00 Claude Code\01 MATLAB CODE\01 Microfluid';
    addpath(genpath(pipeline_root));

    fprintf('==========================================================\n');
    fprintf('  Time-of-Arrival Map Generator\n');
    fprintf('==========================================================\n\n');
    fprintf('  MAT file: %s\n', mat_path);
    fprintf('  Label: %s\n', label);

    % Sanitize label for use in filenames
    label_safe = regexprep(label, '[/\\:*?"<>|]', '-');

    %% ====================================================================
    %  Load config (with Chinese path workaround)
    %  ====================================================================
    fprintf('\n  Loading config...\n');
    try
        loaded = load(mat_path, 'config', 'results');
    catch
        tmp = [tempname '.mat'];
        copyfile(mat_path, tmp, 'f');
        loaded = load(tmp, 'config', 'results');
        delete(tmp);
    end

    if ~isfield(loaded, 'config')
        error('generate_toa_map:noConfig', 'MAT file does not contain config variable.');
    end
    config = loaded.config;

    % Override pixel_size if provided
    if nargin >= 2 && ~isempty(pixel_size_um)
        config.physical.pixel_size = pixel_size_um * 1e-6;
    end
    px_um = config.physical.pixel_size * 1e6;
    fprintf('  Pixel size: %.2f µm/px\n', px_um);

    % Disable interactive modes and figure display
    config.visualization.show_figures = false;
    config.visualization.save_figures = false;
    if ischar(config.preprocess.manual_crop_rect) && ...
            strcmpi(config.preprocess.manual_crop_rect, 'interactive')
        config.preprocess.manual_crop_rect = [];
    end

    %% ====================================================================
    %  Build frame index
    %  ====================================================================
    fprintf('  Building frame index    ...\n');
    tif_path_empty = isempty(tif_path) || (ischar(tif_path) && strcmp(tif_path, ''));
    if ~tif_path_empty
        tif_paths = tif_path;
        if ischar(tif_path)
            fprintf('  Using user-specified TIF: %s\n', tif_path);
        else
            fprintf('  Using user-specified TIF cell array (%d files)\n', numel(tif_path));
        end
    else
        tif_paths = config.multipage_tif_path;
    end
    if ischar(tif_paths), tif_paths = {tif_paths}; end

    frame_index = struct('tif_path', {}, 'page', {});
    for f = 1:numel(tif_paths)
        try
            info_f = imfinfo(tif_paths{f});
        catch
            % Chinese path workaround: copy to temp
            [~, ~, ext] = fileparts(tif_paths{f});
            tmp_tif = [tempname ext];
            fprintf('  Copying TIF to temp (Chinese path workaround)...\n');
            copyfile(tif_paths{f}, tmp_tif, 'f');
            info_f = imfinfo(tmp_tif);
            delete(tmp_tif);
        end
        for p = 1:numel(info_f)
            idx = numel(frame_index) + 1;
            frame_index(idx).tif_path = tif_paths{f};
            frame_index(idx).page = p;
        end
    end

    % Apply page selection: user argument > config.pages
    if ~isempty(pages)
        valid = pages(pages >= 1 & pages <= numel(frame_index));
        frame_index = frame_index(valid);
        fprintf('  Using user-specified pages: %d-%d (%d frames)\n', min(valid), max(valid), numel(valid));
    elseif ~isempty(config.pages)
        valid = config.pages(config.pages >= 1 & config.pages <= numel(frame_index));
        frame_index = frame_index(valid);
    end
    num_frames = numel(frame_index);
    fprintf('  Total frames: %d\n', num_frames);

    %% ====================================================================
    %  Reconstruct flow domain
    %  ====================================================================
    fprintf('  Reconstructing flow domain...\n');
    if isfield(loaded, 'results') && isfield(loaded.results, 'flow_domain')
        flow_domain = loaded.results.flow_domain;
        fprintf('  Flow domain loaded from results.\n');
    else
        % Rebuild from last frame
        fd_idx = num_frames;
        rgb_fd = load_frame(fd_idx, frame_index);
        [rgb_fd_rot, ~, crop_rect] = rotate_and_crop(rgb_fd, config);
        config.preprocess.saved_crop_rect = crop_rect;
        chip_mask = [];
        if isfield(config.preprocess, 'roi_vertices') && ~isempty(config.preprocess.roi_vertices)
            verts = config.preprocess.roi_vertices;
            vx = verts(:,1) - crop_rect(1);
            vy = verts(:,2) - crop_rect(2);
            chip_mask = poly2mask(vx, vy, size(rgb_fd_rot,1), size(rgb_fd_rot,2));
        end
        [flow_domain, ~] = extract_flow_domain(rgb_fd_rot, chip_mask);
    end
    [H, W] = size(flow_domain);

    %% ====================================================================
    %  Get locked threshold
    %  ====================================================================
    % Try from checkpoint first, then from results
    locked_threshold = [];
    cp_dir = fileparts(mat_path);
    cp_files = dir(fullfile(cp_dir, 'checkpoint_*.mat'));
    if ~isempty(cp_files)
        [~, sidx] = sort({cp_files.name});
        cp_latest = fullfile(cp_dir, cp_files(sidx(end)).name);
        try
            cp_data = load(cp_latest, 'locked_threshold');
            if isfield(cp_data, 'locked_threshold')
                locked_threshold = cp_data.locked_threshold;
            end
        catch
            try
                tmp = [tempname '.mat'];
                copyfile(cp_latest, tmp, 'f');
                cp_data = load(tmp, 'locked_threshold');
                if isfield(cp_data, 'locked_threshold')
                    locked_threshold = cp_data.locked_threshold;
                end
                delete(tmp);
            catch
            end
        end
    end

    if isempty(locked_threshold)
        % Compute from frame 1
        fprintf('  Computing threshold from frame 1...\n');
        rgb1 = load_frame(1, frame_index);
        [rgb1_rot, ~, ~] = rotate_and_crop(rgb1, config);
        [rgb1_corr, ~] = correct_illumination(rgb1_rot, ...
            config.illumination.method, config.illumination, false);
        if size(rgb1_corr,1) ~= H || size(rgb1_corr,2) ~= W
            rgb1_corr = imresize(rgb1_corr, [H W]);
        end
        if endsWith(config.segmentation.method, '_v2')
            [~, ~, seg_info] = segment_DNAPL_v2(rgb1_corr, flow_domain, config);
        else
            [~, ~, seg_info] = segment_DNAPL(rgb1_corr, flow_domain, config);
        end
        locked_threshold = seg_info.threshold;
    end
    fprintf('  Locked threshold: %.4f\n', locked_threshold);

    %% ====================================================================
    %  Frame-by-frame processing: compute ToA
    %  ====================================================================
    fprintf('\n  Computing Time-of-Arrival map (%d frames)...\n', num_frames);
    t_arrival = NaN(H, W);
    config_locked = config;
    config_locked.segmentation.fixed_threshold = locked_threshold;
    is_v2 = endsWith(config.segmentation.method, '_v2');

    prev_mask = [];
    timer_start = tic;

    % Capture every frame
    snapshot_frames = 1:num_frames;
    snapshot_masks = cell(numel(snapshot_frames), 1);
    snapshot_labels_t = zeros(numel(snapshot_frames), 1);


    for t = 1:num_frames
        % Load and preprocess
        rgb_t = load_frame(t, frame_index);
        [rgb_rot_t, ~, ~] = rotate_and_crop(rgb_t, config_locked);
        [rgb_corr_t, ~] = correct_illumination(rgb_rot_t, ...
            config_locked.illumination.method, config_locked.illumination, false);
        if size(rgb_corr_t,1) ~= H || size(rgb_corr_t,2) ~= W
            rgb_corr_t = imresize(rgb_corr_t, [H W]);
        end

        % Segment
        if is_v2
            [mask_t, ~, ~] = segment_DNAPL_v2(rgb_corr_t, flow_domain, config_locked);
        else
            [mask_t, ~, ~] = segment_DNAPL(rgb_corr_t, flow_domain, config_locked);
        end
        mask_t = mask_t > 0;
        if size(mask_t,1) ~= H || size(mask_t,2) ~= W
            mask_t = imresize(mask_t, [H W], 'nearest') > 0;
        end

        % Detect transitions: NAPL→water
        if t >= 2 && ~isempty(prev_mask)
            newly_water = prev_mask & ~mask_t;
            t_arrival(newly_water & isnan(t_arrival)) = t;
        end
        prev_mask = mask_t;

        % Capture snapshot if at a key time point
        snap_idx = find(snapshot_frames == t, 1);
        if ~isempty(snap_idx)
            snapshot_masks{snap_idx} = mask_t;
            snapshot_labels_t(snap_idx) = t;
        end

        % Progress
        if mod(t, 100) == 0 || t == num_frames
            elapsed = toc(timer_start);
            eta = elapsed / t * (num_frames - t);
            fprintf('    Frame %d/%d  (%.0fs elapsed, ETA %.0fs)\n', ...
                t, num_frames, elapsed, eta);
        end

        clear rgb_t rgb_rot_t rgb_corr_t;
    end

    % Determine residual NAPL (still NAPL at last frame)
    residual_napl = prev_mask & flow_domain;

    % Pixels that are pore space but were NEVER NAPL → already water at t=0
    % (addresses ~5% initial unsaturation)
    ever_napl = ~isnan(t_arrival) | residual_napl;
    initially_water = flow_domain & ~ever_napl;
    t_arrival(initially_water) = 0;
    fprintf('  Initially-water pixels (never NAPL): %d\n', sum(initially_water(:)));

    fprintf('  ToA computation complete. (%.1f s)\n', toc(timer_start));
    fprintf('  Displaced pixels: %d\n', sum(~isnan(t_arrival(:))));
    fprintf('  Residual NAPL pixels: %d\n', sum(residual_napl(:)));

    %% ====================================================================
    %  Generate figure
    %  ====================================================================
    fprintf('\n  Generating figure...\n');

    % Build RGB image
    % Normalise arrival times to [0, 1] for colormap
    t_max = num_frames;
    t_norm = t_arrival / t_max;  % NaN stays NaN

    % Choose colormap
    cmap = turbo(256);

    % Create RGB canvas
    img = ones(H, W, 3);  % white background (solid)

    % Map displaced pixels to colormap
    displaced = ~isnan(t_arrival) & flow_domain;
    t_idx = round(t_norm * 255) + 1;
    t_idx = min(max(t_idx, 1), 256);
    for c = 1:3
        ch = img(:,:,c);
        color_ch = cmap(:, c);
        ch(displaced) = color_ch(t_idx(displaced));
        img(:,:,c) = ch;
    end

    % Residual NAPL = black
    for c = 1:3
        ch = img(:,:,c);
        ch(residual_napl) = 0;
        img(:,:,c) = ch;
    end

    % Solid = light grey
    solid = ~flow_domain;
    for c = 1:3
        ch = img(:,:,c);
        ch(solid) = 0.85;
        img(:,:,c) = ch;
    end

    % Create figure with correct aspect ratio
    fig = figure('Visible', 'off', 'Color', 'w');
    fig_w = 1000;
    fig_h = round(fig_w * H / W);
    fig.Position = [100 100 fig_w+150 fig_h];  % +150 for colorbar space

    % Axes in mm
    x_mm = (0:W-1) * px_um / 1000;
    y_mm = (0:H-1) * px_um / 1000;

    imagesc(x_mm, y_mm, img);
    axis image;
    xlabel('x (mm)', 'FontSize', 12);
    ylabel('y (mm)', 'FontSize', 12);
    title(sprintf('Time of Arrival — %s', label), 'FontSize', 14, 'FontWeight', 'bold');

    % Colorbar
    colormap(cmap);
    cb = colorbar;
    % Time vector for labels
    if isfield(config, 'time_interval') && ~isempty(config.time_interval)
        dt = config.time_interval;
        caxis([0 num_frames * dt]);
        cb.Label.String = 'Time of arrival (s)';
    else
        caxis([1 num_frames]);
        cb.Label.String = 'Frame index';
    end
    cb.Label.FontSize = 11;

    % Add residual NAPL legend as text annotation
    text(x_mm(end)*0.02, y_mm(end)*0.97, 'Black = Residual NAPL', ...
        'Color', 'w', 'FontSize', 10, 'FontWeight', 'bold', ...
        'BackgroundColor', [0 0 0 0.6], 'Margin', 3);

    set(gca, 'FontSize', 11);

    %% ====================================================================
    %  Save
    %  ====================================================================
    % PNG (300 dpi)
    png_name = fullfile(output_dir, sprintf('ToA_%s.png', label_safe));
    exportgraphics(fig, png_name, 'Resolution', 300);
    fprintf('  Saved: %s\n', png_name);

    % PDF
    pdf_name = fullfile(output_dir, sprintf('ToA_%s.pdf', label_safe));
    exportgraphics(fig, pdf_name, 'ContentType', 'vector');
    fprintf('  Saved: %s\n', pdf_name);

    % Save ToA data as .mat
    toa_mat = fullfile(output_dir, sprintf('toa_data_%s.mat', label_safe));
    tmp = [tempname '.mat'];
    save(tmp, 't_arrival', 'residual_napl', 'flow_domain', 'px_um', 'label', 'num_frames');
    copyfile(tmp, toa_mat, 'f');
    delete(tmp);
    fprintf('  Saved: %s\n', toa_mat);

    %% ====================================================================
    %  Binary Snapshots (water = white, NAPL = black)
    %  ====================================================================
    fprintf('\n  Generating binary snapshots...\n');

    % Filter out empty snapshots
    valid_snaps = ~cellfun('isempty', snapshot_masks);
    snapshot_masks  = snapshot_masks(valid_snaps);
    snapshot_labels_t = snapshot_labels_t(valid_snaps);
    n_snaps = numel(snapshot_masks);

    if n_snaps > 0
        % Determine grid layout
        if n_snaps <= 3
            n_rows = 1; n_cols = n_snaps;
        elseif n_snaps <= 4
            n_rows = 1; n_cols = n_snaps;
        else
            n_rows = 2; n_cols = ceil(n_snaps / 2);
        end

        fig_snap = figure('Visible', 'off', 'Color', 'w');
        fig_snap.Position = [100 100 350*n_cols 400*n_rows];

        for s = 1:n_snaps
            subplot(n_rows, n_cols, s);

            % Binary image: white = water (pore & not NAPL), black = NAPL
            % Only show pore space; solid grains become white background
            bw = ones(H, W);             % white background
            napl_px = snapshot_masks{s} & flow_domain;  % NAPL in pore space
            bw(napl_px) = 0;             % NAPL = black

            imagesc(x_mm, y_mm, bw);
            colormap(gca, gray(2));
            caxis([0 1]);
            axis image; axis off;

            % Time label
            if isfield(config, 'time_interval') && ~isempty(config.time_interval)
                t_sec = snapshot_labels_t(s) * config.time_interval;
                title(sprintf('t = %.0f s  (frame %d)', t_sec, snapshot_labels_t(s)), ...
                    'FontSize', 11);
            else
                title(sprintf('Frame %d / %d', snapshot_labels_t(s), num_frames), ...
                    'FontSize', 11);
            end
        end

        sgtitle(sprintf('Displacement Snapshots — %s', label), ...
            'FontSize', 14, 'FontWeight', 'bold');

        % Save combined panel
        snap_png = fullfile(output_dir, sprintf('Snapshots_%s.png', label_safe));
        exportgraphics(fig_snap, snap_png, 'Resolution', 300);
        fprintf('  Saved: %s\n', snap_png);

        % Also save each snapshot individually
        for s = 1:n_snaps
            fig_single = figure('Visible', 'off', 'Color', 'w');
            fig_single.Position = [100 100 800 round(800 * H / W)];

            bw = ones(H, W);
            napl_px = snapshot_masks{s} & flow_domain;
            bw(napl_px) = 0;

            imagesc(x_mm, y_mm, bw);
            colormap(gca, gray(2));
            caxis([0 1]);
            axis image; axis off;

            single_png = fullfile(output_dir, sprintf('Snap_%s_f%04d.png', label_safe, snapshot_labels_t(s)));
            exportgraphics(fig_single, single_png, 'Resolution', 300, 'BackgroundColor', 'w');
            close(fig_single);
        end
        fprintf('  Saved %d individual snapshots\n', n_snaps);

        close(fig_snap);
    end

    %% ====================================================================
    %  Black-White-Grey Snapshots (black=NAPL, white=water, grey=solid)
    %  ====================================================================
    if n_snaps > 0
        fprintf('\n  Generating black-white-grey snapshots...\n');

        % Combined panel
        if n_snaps <= 4
            br = 1; bc = n_snaps;
        else
            br = 2; bc = ceil(n_snaps / 2);
        end

        fig_bwg = figure('Visible', 'off', 'Color', 'w');
        fig_bwg.Position = [100 100 350*bc 400*br];

        for s = 1:n_snaps
            subplot(br, bc, s);

            % grey=solid(0.5), black=NAPL(0), white=water(1)
            bwg = ones(H, W) * 0.5;         % solid = grey
            water_px = flow_domain & ~snapshot_masks{s};
            napl_px  = snapshot_masks{s} & flow_domain;
            bwg(water_px) = 1;               % water = white
            bwg(napl_px)  = 0;               % NAPL = black

            imagesc(x_mm, y_mm, bwg);
            colormap(gca, gray(256));
            caxis([0 1]);
            axis image; axis off;

            if isfield(config, 'time_interval') && ~isempty(config.time_interval)
                t_sec = snapshot_labels_t(s) * config.time_interval;
                title(sprintf('t = %.0f s  (frame %d)', t_sec, snapshot_labels_t(s)), ...
                    'FontSize', 11);
            else
                title(sprintf('Frame %d / %d', snapshot_labels_t(s), num_frames), ...
                    'FontSize', 11);
            end
        end

        sgtitle(sprintf('Displacement — %s  (black=NAPL, white=water, grey=solid)', label), ...
            'FontSize', 12, 'FontWeight', 'bold');

        bwg_png = fullfile(output_dir, sprintf('SnapBWG_%s.png', label_safe));
        exportgraphics(fig_bwg, bwg_png, 'Resolution', 300);
        fprintf('  Saved: %s\n', bwg_png);

        % Individual frames
        for s = 1:n_snaps
            fig_s = figure('Visible', 'off', 'Color', 'w');
            fig_s.Position = [100 100 800 round(800 * H / W)];

            bwg = ones(H, W) * 0.5;
            water_px = flow_domain & ~snapshot_masks{s};
            napl_px  = snapshot_masks{s} & flow_domain;
            bwg(water_px) = 1;
            bwg(napl_px)  = 0;

            imagesc(x_mm, y_mm, bwg);
            colormap(gca, gray(256));
            caxis([0 1]);
            axis image; axis off;

            s_png = fullfile(output_dir, sprintf('SnapBWG_%s_f%04d.png', label_safe, snapshot_labels_t(s)));
            exportgraphics(fig_s, s_png, 'Resolution', 300);
            close(fig_s);
        end
        fprintf('  Saved %d BWG individual snapshots\n', n_snaps);
        close(fig_bwg);
    end

    %% ====================================================================
    %  Soil-Reference Snapshots (grey=solid, black=NAPL, white=water)
    %  ====================================================================
    if ~isempty(soil_img) && n_snaps > 0
        fprintf('\n  Generating soil-reference snapshots...\n');

        % Parse soil_img input: {path, page} or just path
        if iscell(soil_img)
            soil_tif = soil_img{1};
            soil_page = soil_img{2};
        else
            soil_tif = soil_img;
            soil_page = 1;
        end

        % Load and preprocess soil image through same pipeline
        try
            rgb_soil = imread(soil_tif, soil_page);
        catch
            [~, ~, ext] = fileparts(soil_tif);
            tmp_s = [tempname ext];
            copyfile(soil_tif, tmp_s, 'f');
            rgb_soil = imread(tmp_s, soil_page);
            delete(tmp_s);
        end
        [rgb_soil_rot, ~, ~] = rotate_and_crop(rgb_soil, config_locked);
        [rgb_soil_corr, ~] = correct_illumination(rgb_soil_rot, ...
            config_locked.illumination.method, config_locked.illumination, false);
        if size(rgb_soil_corr,1) ~= H || size(rgb_soil_corr,2) ~= W
            rgb_soil_corr = imresize(rgb_soil_corr, [H W]);
        end

        % Convert to greyscale for background
        if size(rgb_soil_corr, 3) == 3
            soil_gray = rgb2gray(im2double(rgb_soil_corr));
        else
            soil_gray = im2double(rgb_soil_corr);
        end

        % Normalize to [0.3, 0.9] range for nice grey tones
        soil_gray = (soil_gray - min(soil_gray(:))) / (max(soil_gray(:)) - min(soil_gray(:)) + eps);
        soil_gray = 0.3 + soil_gray * 0.6;

        % Generate combined panel
        fig_soil = figure('Visible', 'off', 'Color', 'k');
        if n_snaps <= 4
            sr = 1; sc = n_snaps;
        else
            sr = 2; sc = ceil(n_snaps / 2);
        end
        fig_soil.Position = [100 100 350*sc 400*sr];

        for s = 1:n_snaps
            subplot(sr, sc, s);

            % Build 3-channel image
            % Start with soil greyscale background
            rgb_out = repmat(soil_gray, [1 1 3]);

            % Pore space that is NAPL → black
            napl_px = snapshot_masks{s} & flow_domain;
            for c = 1:3
                ch = rgb_out(:,:,c);
                ch(napl_px) = 0;
                rgb_out(:,:,c) = ch;
            end

            % Pore space that is water → white
            water_px = flow_domain & ~snapshot_masks{s};
            for c = 1:3
                ch = rgb_out(:,:,c);
                ch(water_px) = 1;
                rgb_out(:,:,c) = ch;
            end

            imagesc(x_mm, y_mm, rgb_out);
            axis image; axis off;

            if isfield(config, 'time_interval') && ~isempty(config.time_interval)
                t_sec = snapshot_labels_t(s) * config.time_interval;
                title(sprintf('t = %.0f s', t_sec), 'FontSize', 11, 'Color', 'w');
            else
                title(sprintf('Frame %d', snapshot_labels_t(s)), 'FontSize', 11, 'Color', 'w');
            end
        end

        sgtitle(sprintf('%s  (grey=solid, black=NAPL, white=water)', label), ...
            'FontSize', 13, 'FontWeight', 'bold', 'Color', 'w');

        soil_png = fullfile(output_dir, sprintf('SoilRef_%s.png', label_safe));
        exportgraphics(fig_soil, soil_png, 'Resolution', 300, 'BackgroundColor', 'k');
        fprintf('  Saved: %s\n', soil_png);

        % Also save individual frames
        for s = 1:n_snaps
            fig_s = figure('Visible', 'off', 'Color', 'k');
            fig_s.Position = [100 100 800 round(800 * H / W)];

            rgb_out = repmat(soil_gray, [1 1 3]);
            napl_px = snapshot_masks{s} & flow_domain;
            water_px = flow_domain & ~snapshot_masks{s};
            for c = 1:3
                ch = rgb_out(:,:,c);
                ch(napl_px) = 0;
                ch(water_px) = 1;
                rgb_out(:,:,c) = ch;
            end

            imagesc(x_mm, y_mm, rgb_out);
            axis image; axis off;

            s_png = fullfile(output_dir, sprintf('SoilRef_%s_f%04d.png', label_safe, snapshot_labels_t(s)));
            exportgraphics(fig_s, s_png, 'Resolution', 300, 'BackgroundColor', 'k');
            close(fig_s);
        end
        fprintf('  Saved %d soil-ref individual snapshots\n', n_snaps);

        close(fig_soil);
    end

    close(fig);

    fprintf('\n==========================================================\n');
    fprintf('  ToA map for %s complete.\n', label);
    fprintf('==========================================================\n');
end
