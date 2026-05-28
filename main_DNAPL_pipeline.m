function results = main_DNAPL_pipeline(config)
% MAIN_DNAPL_PIPELINE  Complete DNAPL image analysis pipeline.
%
%   results = main_DNAPL_pipeline()
%   results = main_DNAPL_pipeline(config)
%
%   Supports two input modes:
%     Mode 1 — Multi-page TIF: one .tif with N pages (default)
%     Mode 2 — Separate files: cell array of individual image paths
%
%   Processing stages:
%       1. Load images   — read multi-page TIF or separate files
%       2. Preprocessing — rotation, illumination correction, alignment
%       3. Flow domain   — extract pore-space mask from most-dissolved frame
%       4. Segmentation  — identify DNAPL pixels (Lab color space + GMM)
%       5. Analysis      — saturation, blob geometry, interfaces, mass transfer
%       6. Time series   — dissolution dynamics across all frames
%       7. Visualization — publication-quality figures
%       8. Export        — save results to .mat / .csv
%D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\01 databased\02 Pretest 4\02 Water Dis
%   Input:
%       config - (optional) Configuration struct from config_pipeline()
%
%   Output:
%       results - Struct containing all analysis results

    %% ====================================================================
    %  Initialization
    %  ====================================================================
    if nargin < 1 || isempty(config)
        config = config_pipeline();
    end

    total_timer = tic;

    % Add all sub-folders to MATLAB path
    pipeline_root = fileparts(mfilename('fullpath'));
    add_project_paths(pipeline_root);

    % Ensure output directory exists
    if ~isfolder(config.output_path)
        mkdir(config.output_path);
    end

    heartbeat = init_pipeline_heartbeat(config);
    heartbeat = write_pipeline_heartbeat(heartbeat, struct( ...
        'status', 'starting', ...
        'step', 'STEP 0', ...
        'step_label', 'Loading Images', ...
        'current_frame', 0, ...
        'total_frames', 0, ...
        'message', 'Initializing pipeline', ...
        'force', true));

    log_cleanup = []; %#ok<NASGU>
    [save_log, ~] = get_output_option(config, 'save_log', true);
    if save_log
        log_dir = fullfile(config.output_path, 'logs');
        if ~isfolder(log_dir)
            mkdir(log_dir);
        end
        log_path = fullfile(log_dir, ['pipeline_log_' datestr(now, 'yyyymmdd_HHMMSS') '.txt']);
        safe_diary_off();
        diary(log_path);
        log_cleanup = onCleanup(@safe_diary_off);
    else
        log_path = '';
    end

    fprintf('==========================================================\n');
    fprintf('   DNAPL Image Analysis Pipeline v2.5\n');
    fprintf('==========================================================\n\n');
    if save_log
        fprintf('  Log file: %s\n\n', log_path);
    end

    try

    %% ====================================================================
    %  STEP 0: Load Images (multi-page TIF or separate files)
    %  ====================================================================
    fprintf('STEP 0: Loading Images\n');
    fprintf('--------------------------------------------------------\n');

    switch lower(config.input_mode)
        case 'multipage_tif'
            % --- Multi-page TIF mode: build frame index (NO image loading) ---
            tif_paths = config.multipage_tif_path;
            if ischar(tif_paths)
                tif_paths = {tif_paths};
            end

            % Scan all TIF files to count pages
            n_files = numel(tif_paths);
            pages_per_file = zeros(1, n_files);
            fprintf('  Scanning %d TIF files...\n', n_files);
            for f = 1:n_files
                info_f = imfinfo(tif_paths{f});
                pages_per_file(f) = numel(info_f);
            end
            total_pages = sum(pages_per_file);
            fprintf('  Total pages across all files: %d\n', total_pages);

            % Build frame index: struct array mapping global index -> (tif_path, page)
            frame_index = struct('tif_path', {}, 'page', {});
            idx = 0;
            for f = 1:n_files
                for p = 1:pages_per_file(f)
                    idx = idx + 1;
                    frame_index(idx).tif_path = tif_paths{f};
                    frame_index(idx).page = p;
                end
            end

            % Apply page selection (if specified)
            if ~isempty(config.pages)
                valid = config.pages(config.pages >= 1 & config.pages <= total_pages);
                frame_index = frame_index(valid);
            end
            num_frames = numel(frame_index);

            % Determine flow domain frame index
            if isempty(config.flow_domain_frame)
                fd_idx = num_frames;
            else
                if isempty(config.pages)
                    fd_idx = config.flow_domain_frame;
                else
                    fd_idx = find(config.pages == config.flow_domain_frame, 1);
                    if isempty(fd_idx)
                        fd_idx = num_frames;
                        warning('main:fdFrame', ...
                            'flow_domain_frame %d not in pages list. Using last frame.', ...
                            config.flow_domain_frame);
                    end
                end
            end

            results.input_mode  = 'multipage_tif';
            results.tif_path    = config.multipage_tif_path;
            results.total_pages = total_pages;

            fprintf('  Mode: multi-page TIF (%d total pages, %d selected)\n', ...
                total_pages, num_frames);
            fprintf('  Memory: lazy loading (only 1 frame in memory at a time)\n');

        case 'separate_files'
            % --- Separate files mode (legacy) ---
            image_files = config.image_files;
            num_frames  = numel(image_files);
            total_pages = num_frames;

            % Build frame index for separate files
            frame_index = struct('tif_path', {}, 'page', {});
            for k = 1:num_frames
                frame_index(k).tif_path = image_files{k};
                frame_index(k).page = 1;  % single page per file
            end

            if isempty(config.flow_domain_frame)
                fd_idx = num_frames;
            else
                fd_idx = config.flow_domain_frame;
            end

            results.input_mode = 'separate_files';
            fprintf('  Mode: separate files (%d frames, lazy loading)\n', num_frames);

        otherwise
            error('main:badMode', 'Unknown input_mode "%s".', config.input_mode);
    end

    % Auto-generate time vector
    if isfield(config, 'time_interval') && ~isempty(config.time_interval)
        % Fixed interval: [0, dt, 2*dt, ...]
        dt = config.time_interval;
        config.time_vector = (0:(num_frames - 1)) * dt;
        fprintf('  Time interval: %.1f s per frame\n', dt);
    elseif isempty(config.time_vector)
        config.time_vector = 0:(num_frames - 1);
    end
    if numel(config.time_vector) ~= num_frames
        warning('main:timeVec', ...
            'time_vector length (%d) does not match frame count (%d). Auto-generating.', ...
            numel(config.time_vector), num_frames);
        config.time_vector = 0:(num_frames - 1);
    end

    fprintf('  Frames to analyze: %d\n', num_frames);
    fprintf('  Flow domain frame: index %d\n', fd_idx);
    if isfield(config, 'input') && isfield(config.input, 'is_linear_rgb') && config.input.is_linear_rgb
        fprintf('  Input RGB encoding: linear RGB -> normalized to sRGB for segmentation\n');
    else
        fprintf('  Input RGB encoding: sRGB/default\n');
    end
    fprintf('  Output: %s\n\n', config.output_path);
    heartbeat = write_pipeline_heartbeat(heartbeat, struct( ...
        'status', 'running', ...
        'step', 'STEP 0', ...
        'step_label', 'Loading Images', ...
        'current_frame', 0, ...
        'total_frames', num_frames, ...
        'message', sprintf('Loaded frame index for %d frames', num_frames), ...
        'force', true));

    %% ====================================================================
    %  Pixel Size Calibration (if requested)
    %  ====================================================================
    if ischar(config.physical.pixel_size) && strcmpi(config.physical.pixel_size, 'calibrate')
        fprintf('PIXEL SIZE CALIBRATION\n');
        fprintf('--------------------------------------------------------\n');
        channel_um = config.physical.channel_width_um;
        fprintf('  Known channel width: %.0f μm (from config)\n', channel_um);
        fprintf('  Draw a line across the inlet/outlet channel on the image.\n\n');

        fig_cal = figure('Name', 'Pixel Size Calibration', ...
            'Position', [100 100 900 750], 'Color', 'w');
        imshow(load_frame(1, frame_index, config));
        title(sprintf('Draw a line across the channel (%.0f μm). Double-click to confirm.', channel_um), ...
            'FontSize', 13);

        h_line = imdistline;
        try
            wait(h_line);
        catch
            if ishandle(fig_cal), close(fig_cal); end
            error('main:calibrationCancelled', ...
                'Pixel calibration cancelled — figure was closed before confirmation.');
        end
        if ~ishandle(fig_cal)
            error('main:calibrationCancelled', ...
                'Pixel calibration cancelled — figure was closed before confirmation.');
        end
        line_px = getDistance(h_line);
        close(fig_cal);

        pixel_size_m = (channel_um * 1e-6) / line_px;
        config.physical.pixel_size = pixel_size_m;
        fprintf('  Channel width: %.1f pixels\n', line_px);
        fprintf('  ► pixel_size = %.2f μm/px = %.2e m/px\n', pixel_size_m * 1e6, pixel_size_m);
        fprintf('  Tip: Set config.physical.pixel_size = %.2e to skip next time.\n\n', pixel_size_m);
    end

    %% ====================================================================
    %  Interactive ROI Selection (if requested)
    %  ====================================================================
    if ischar(config.preprocess.manual_crop_rect) && ...
            strcmpi(config.preprocess.manual_crop_rect, 'interactive')
        fprintf('INTERACTIVE ROI: Click vertices around the chip boundary.\n');
        fprintf('  Double-click the last vertex to close the polygon.\n');

        ref_img = load_frame(fd_idx, frame_index, config);
        [H_orig, W_orig, ~] = size(ref_img);
        fig_roi = figure('Name', 'Select Chip ROI', ...
            'Position', [100 100 900 750], 'Color', 'w');
        imshow(ref_img);
        title('Click vertices around the chip. Double-click last vertex to confirm.', ...
            'FontSize', 13);

        roi = drawpolygon('Color', 'r', 'LineWidth', 2);
        try
            wait(roi);
        catch
            if ishandle(fig_roi), close(fig_roi); end
            error('main:roiCancelled', ...
                'ROI selection cancelled — figure was closed before confirmation.');
        end
        if ~ishandle(fig_roi)
            error('main:roiCancelled', ...
                'ROI selection cancelled — figure was closed before confirmation.');
        end
        vertices = roi.Position;  % Nx2 [x, y]
        close(fig_roi);

        % Bounding box from polygon (with small margin)
        margin = 5;
        x0 = max(1, floor(min(vertices(:,1))) - margin);
        y0 = max(1, floor(min(vertices(:,2))) - margin);
        x1 = min(W_orig, ceil(max(vertices(:,1))) + margin);
        y1 = min(H_orig, ceil(max(vertices(:,2))) + margin);
        config.preprocess.manual_crop_rect = [x0, y0, x1 - x0, y1 - y0];

        % Store polygon vertices for chip mask creation after cropping
        config.preprocess.roi_vertices = vertices;

        fprintf('  Crop rect: [%d, %d, %d, %d]\n', config.preprocess.manual_crop_rect);
        fprintf('  Polygon: %d vertices\n\n', size(vertices, 1));
    end

    %% ====================================================================
    %  Interactive ROI on clean reference image (if provided)
    %  ====================================================================
    use_clean_ref = isfield(config, 'flow_domain_image') && ~isempty(config.flow_domain_image);

    if use_clean_ref
        fd_path = config.flow_domain_image;
        fd_page = 1;
        if isfield(config, 'flow_domain_image_page') && ~isempty(config.flow_domain_image_page)
            fd_page = config.flow_domain_image_page;
        end

        % Read clean reference image
        rgb_clean = imread(fd_path, fd_page);
        if isa(rgb_clean, 'uint16'), rgb_clean = im2uint8(rgb_clean); end
        if size(rgb_clean, 3) == 1, rgb_clean = repmat(rgb_clean, [1 1 3]); end
        rgb_clean = prepare_rgb_input_encoding(rgb_clean, config);
        fprintf('  Clean reference image: %s (page %d)\n', fd_path, fd_page);

        % Interactive ROI on clean image (if no saved rect)
        if ~isfield(config, 'flow_domain_crop_rect') || isempty(config.flow_domain_crop_rect)
            fprintf('INTERACTIVE ROI: Select chip boundary on the CLEAN reference image.\n');
            [H_c, W_c, ~] = size(rgb_clean);
            fig_clean = figure('Name', 'Select Chip ROI on Clean Reference', ...
                'Position', [100 100 900 750], 'Color', 'w');
            imshow(rgb_clean);
            title('Clean reference: Click vertices around the chip. Double-click to confirm.', ...
                'FontSize', 13);

            roi_c = drawpolygon('Color', 'g', 'LineWidth', 2);
            try
                wait(roi_c);
            catch
                if ishandle(fig_clean), close(fig_clean); end
                error('main:cleanRoiCancelled', ...
                    'Clean reference ROI cancelled — figure was closed before confirmation.');
            end
            if ~ishandle(fig_clean)
                error('main:cleanRoiCancelled', ...
                    'Clean reference ROI cancelled — figure was closed before confirmation.');
            end
            clean_verts = roi_c.Position;
            close(fig_clean);

            margin = 5;
            cx0 = max(1, floor(min(clean_verts(:,1))) - margin);
            cy0 = max(1, floor(min(clean_verts(:,2))) - margin);
            cx1 = min(W_c, ceil(max(clean_verts(:,1))) + margin);
            cy1 = min(H_c, ceil(max(clean_verts(:,2))) + margin);
            config.flow_domain_crop_rect = [cx0, cy0, cx1 - cx0, cy1 - cy0];

            fprintf('  Clean image crop: [%d, %d, %d, %d]\n', config.flow_domain_crop_rect);
            fprintf('  Tip: Save this rect to config to skip next time.\n\n');
        end
    end

    %% ====================================================================
    %  STEP 1: Preprocess the flow-domain reference frame
    %  ====================================================================
    heartbeat = write_pipeline_heartbeat(heartbeat, struct( ...
        'status', 'running', ...
        'step', 'STEP 1', ...
        'step_label', 'Preprocessing reference frame', ...
        'current_frame', 0, ...
        'total_frames', num_frames, ...
        'message', 'Preparing reference frame', ...
        'force', true));
    fprintf('STEP 1: Preprocessing reference frame\n');
    fprintf('--------------------------------------------------------\n');

    if use_clean_ref && ~isempty(config.flow_domain_crop_rect)
        % --- Clean reference with its own ROI: crop + resize ---
        fprintf('  Using external clean reference (crop + resize to experiment)\n');

        % Crop clean image to its own ROI
        rgb_fd_rot = imcrop(rgb_clean, config.flow_domain_crop_rect);

        % Resolve experiment crop dimensions for resizing.
        exp_rect = [];
        exp_angle = config.preprocess.rotation_angle;
        if isempty(exp_angle), exp_angle = 0; end

        if isfield(config.preprocess, 'manual_crop_rect') && ...
                isnumeric(config.preprocess.manual_crop_rect) && ...
                numel(config.preprocess.manual_crop_rect) == 4
            exp_rect = config.preprocess.manual_crop_rect;
        else
            % manual_crop_rect can be [] (auto). In that case, derive crop
            % from an experiment frame so clean reference is resized safely.
            [~, exp_angle, exp_rect] = rotate_and_crop(load_frame(fd_idx, frame_index, config), config);
            fprintf('  Auto-detected experiment crop for resize: [%d x %d]\n', ...
                exp_rect(3), exp_rect(4));
        end

        if numel(exp_rect) ~= 4 || any(exp_rect(3:4) <= 0)
            error('main:badExperimentCrop', ...
                'Invalid experiment crop_rect. Expected [x,y,w,h] with w,h>0.');
        end

        rgb_fd_rot = imresize(rgb_fd_rot, [exp_rect(4), exp_rect(3)]);
        fprintf('  Resized clean reference to [%d x %d]\n', exp_rect(3), exp_rect(4));

        % Use experiment crop for saved_crop_rect (for experiment frames)
        crop_rect = exp_rect;
        config.preprocess.saved_crop_rect = crop_rect;
        angle_deg = exp_angle;
    else
        % --- Use experiment frame as reference ---
        if use_clean_ref
            fprintf('  Using external reference (same scale)\n');
            rgb_fd = rgb_clean;
        else
            fprintf('  Using experiment frame index %d\n', fd_idx);
            rgb_fd = load_frame(fd_idx, frame_index, config);
        end

        % 1a. Rotate and crop
        [rgb_fd_rot, angle_deg, crop_rect] = rotate_and_crop(rgb_fd, config);
        config.preprocess.saved_crop_rect = crop_rect;
    end

    % 1b. Interactive kernel size selection (if requested)
    if ischar(config.illumination.kernel_size) && ...
            strcmpi(config.illumination.kernel_size, 'interactive')
        config.illumination.kernel_size = select_illumination_kernel(rgb_fd_rot);
        fprintf('  Tip: Set config.illumination.kernel_size = %d to skip next time.\n', ...
            config.illumination.kernel_size);
    end

    % 1c. Illumination correction
    [rgb_fd_corr, illum_field] = correct_illumination(rgb_fd_rot, ...
        config.illumination.method, config.illumination, config.parallel.use_gpu);

    results.preprocessing.rotation_angle = angle_deg;
    results.preprocessing.crop_rect      = crop_rect;
    results.preprocessing.illumination_field = illum_field;

    %% ====================================================================
    %  STEP 2: Extract flow domain from the reference frame
    %  ====================================================================
    heartbeat = write_pipeline_heartbeat(heartbeat, struct( ...
        'status', 'running', ...
        'step', 'STEP 2', ...
        'step_label', 'Flow Domain Extraction', ...
        'current_frame', 0, ...
        'total_frames', num_frames, ...
        'message', 'Extracting flow domain', ...
        'force', true));
    fprintf('\nSTEP 2: Flow Domain Extraction\n');
    fprintf('--------------------------------------------------------\n');

    % Build chip mask from polygon ROI (if available)
    chip_mask = [];
    if isfield(config.preprocess, 'roi_vertices') && ~isempty(config.preprocess.roi_vertices)
        verts = config.preprocess.roi_vertices;
        crop = config.preprocess.saved_crop_rect;
        vx = verts(:,1) - crop(1);
        vy = verts(:,2) - crop(2);
        [H_crop, W_crop, ~] = size(rgb_fd_rot);
        chip_mask = poly2mask(vx, vy, H_crop, W_crop);
        fprintf('  Using polygon chip mask (%d vertices)\n', size(verts, 1));
    end

    % Use pre-correction image for flow domain extraction (preserves color)
    [flow_domain, solid_mask] = extract_flow_domain(rgb_fd_rot, chip_mask);
    results.flow_domain = flow_domain;
    results.solid_mask  = solid_mask;


    %% ====================================================================
    %  STEP 3: Process the first frame for single-image analysis
    %  ====================================================================
    heartbeat = write_pipeline_heartbeat(heartbeat, struct( ...
        'status', 'running', ...
        'step', 'STEP 3', ...
        'step_label', 'Single-Image Analysis', ...
        'current_frame', min(num_frames, 1), ...
        'total_frames', num_frames, ...
        'message', 'Analyzing frame 1', ...
        'force', true));
    fprintf('\nSTEP 3: Single-Image Analysis (frame 1)\n');
    fprintf('--------------------------------------------------------\n');

    % Preprocess frame 1
    rgb1 = load_frame(1, frame_index, config);
    [rgb1_rot, ~, ~] = rotate_and_crop(rgb1, config);
    [rgb1_corr, ~]   = correct_illumination(rgb1_rot, ...
        config.illumination.method, config.illumination, config.parallel.use_gpu);

    % Resize to match flow domain if needed
    if size(rgb1_corr,1) ~= size(flow_domain,1) || size(rgb1_corr,2) ~= size(flow_domain,2)
        rgb1_corr = imresize(rgb1_corr, size(flow_domain));
    end
    results.ref_image = rgb1_corr;

    % Visualize preprocessing
    if config.visualization.show_figures
        visualize_preprocessing(rgb1, illum_field, rgb1_corr, ...
            flow_domain, rgb1_corr, config, solid_mask);
    end

    %% 3a. DNAPL Segmentation
    fprintf('\n  Segmenting DNAPL...\n');
    if endsWith(config.segmentation.method, '_v2')
        [dnapl_mask, confidence_map, seg_info] = segment_DNAPL_v2(rgb1_corr, flow_domain, config);
    else
        [dnapl_mask, confidence_map, seg_info] = segment_DNAPL(rgb1_corr, flow_domain, config);
    end
    results.dnapl_mask = dnapl_mask;
    results.segmentation.confidence_map = confidence_map;
    results.segmentation.info = seg_info;

    if config.visualization.show_figures
        visualize_segmentation(rgb1_corr, seg_info.color_channel, dnapl_mask, ...
            flow_domain, confidence_map, config);
    end

    %% 3b. Saturation
    fprintf('\n  Calculating saturation...\n');
    sat = calculate_saturation(dnapl_mask, flow_domain, config.physical.pixel_size);
    chip_area_px = sum(flow_domain(:)) + sum(solid_mask(:));
    results.chip_geometric_volume_m3 = chip_area_px * config.physical.pixel_size^2 * config.physical.depth;
    results.flow_domain_volume_m3 = sat.pore_area_m2 * config.physical.depth;
    sat.dnapl_volume_m3 = sat.dnapl_area_m2 * config.physical.depth;
    results.saturation = sat;
    fprintf('    Sn = %.4f,  Sw = %.4f\n', sat.Sn, sat.Sw);

    %% 3c. Blob Geometry
    fprintf('\n  Analyzing blob geometry...\n');
    geometry_opts = [];
    if isfield(config, 'geometry')
        geometry_opts = config.geometry;
    end
    blob = analyze_blob_geometry(dnapl_mask, config.physical.pixel_size, ...
        flow_domain, solid_mask, geometry_opts);
    results.blobs = blob;
    fprintf('    %d blobs detected\n', blob.num_blobs);

    if config.visualization.show_figures
        visualize_blobs(blob, config);
    end

    %% 3d. Interface Analysis
    fprintf('\n  Analyzing interfaces...\n');
    iface = analyze_interfaces(dnapl_mask, flow_domain, ...
        config.physical.pixel_size, config);
    results.interfaces = iface;

    if config.visualization.show_figures
        visualize_interfaces(dnapl_mask, flow_domain, iface, config);
    end

    %% 3e. Residual Architecture Classification
    fprintf('\n  Classifying residual architecture...\n');
    arch = classify_residual_architecture(blob, iface, sat, config);
    results.architecture = arch;
    fprintf('    Architecture: %s\n', arch.type);

    %% 3f. Mass Transfer Estimation
    fprintf('\n  Estimating mass transfer...\n');
    mt = calculate_mass_transfer(iface, sat, blob, config);
    results.mass_transfer = mt;

    %% ====================================================================
    %  STEP 4: Time Series — Solubilization Dynamics
    %  ====================================================================
    if num_frames > 1
        heartbeat = write_pipeline_heartbeat(heartbeat, struct( ...
            'status', 'running', ...
            'step', 'STEP 4', ...
            'step_label', 'Solubilization Dynamics', ...
            'current_frame', 1, ...
            'total_frames', num_frames, ...
            'message', 'Entering time-series analysis', ...
            'force', true));
        fprintf('\n\nSTEP 4: Solubilization Dynamics (%d frames)\n', num_frames);
        fprintf('========================================================\n');

        [sol, heartbeat] = characterize_solubilization_v2(frame_index, flow_domain, ...
            config.time_vector, config, heartbeat, solid_mask);
        results.solubilization = sol;
        results.time_vector = config.time_vector(1:numel(sol.saturation_vs_time));
        results.pipeline_status = sol.pipeline_status;
        if strcmp(sol.pipeline_status, 'paused')
            results.resume_from_frame = sol.resume_from_frame;
            fprintf('\n  Safe pause after frame %d.\n', sol.last_completed_frame);
            fprintf('  Re-run with the same output_path to resume from frame %d.\n', ...
                sol.resume_from_frame);
            return;
        end

        if config.visualization.show_figures
            visualize_solubilization(sol, config.time_vector, config);
        end
    end
    if ~isfield(results, 'pipeline_status')
        results.pipeline_status = 'completed';
    end

    %% ====================================================================
    %  STEP 5: Export Results
    %  ====================================================================
    heartbeat = write_pipeline_heartbeat(heartbeat, struct( ...
        'status', 'running', ...
        'step', 'STEP 5', ...
        'step_label', 'Exporting Results', ...
        'current_frame', num_frames, ...
        'total_frames', num_frames, ...
        'message', 'Exporting results and reports', ...
        'force', true));
    fprintf('\n\nSTEP 5: Exporting Results\n');
    fprintf('--------------------------------------------------------\n');
    export_results(results, config.output_path, {'mat', 'csv'}, config);
    generate_report(results, config);

    %% ====================================================================
    %  Summary
    %  ====================================================================
    total_time = toc(total_timer);
    fprintf('\n==========================================================\n');
    fprintf('  Pipeline completed in %.1f seconds\n', total_time);
    fprintf('  Results saved to: %s\n', config.output_path);
    fprintf('==========================================================\n');
    heartbeat = write_pipeline_heartbeat(heartbeat, struct( ...
        'status', 'completed', ...
        'step', 'STEP 5', ...
        'step_label', 'Exporting Results', ...
        'current_frame', num_frames, ...
        'total_frames', num_frames, ...
        'message', sprintf('Pipeline completed in %.1f seconds', total_time), ...
        'force', true));
    catch ME
        heartbeat = write_pipeline_heartbeat(heartbeat, struct( ...
            'status', 'failed', ...
            'message', format_exception_message(ME), ...
            'force', true));
        rethrow(ME);
    end
end


function [value, exists] = get_output_option(config, field_name, default_value)
    exists = isfield(config, 'output') && isfield(config.output, field_name);
    if exists && ~isempty(config.output.(field_name))
        value = config.output.(field_name);
    else
        value = default_value;
    end
end


function safe_diary_off()
    try
        diary off;
    catch
        % Best effort cleanup if diary is not active.
    end
end


function heartbeat = init_pipeline_heartbeat(config)
    [save_heartbeat, ~] = get_output_option(config, 'save_heartbeat', true);
    if ~save_heartbeat
        heartbeat = struct('enabled', false);
        return;
    end

    [frame_interval, ~] = get_output_option(config, 'heartbeat_frame_interval', 10);
    [time_interval_sec, ~] = get_output_option(config, 'heartbeat_time_interval_sec', 30);

    status_dir = fullfile(config.output_path, 'status');
    if ~isfolder(status_dir)
        mkdir(status_dir);
    end

    heartbeat = struct();
    heartbeat.enabled = true;
    heartbeat.output_path = config.output_path;
    heartbeat.status_dir = status_dir;
    heartbeat.json_path = fullfile(status_dir, 'heartbeat_latest.json');
    heartbeat.mat_path = fullfile(status_dir, 'heartbeat_latest.mat');
    heartbeat.frame_interval = frame_interval;
    heartbeat.time_interval_sec = time_interval_sec;
    heartbeat.last_write_datenum = 0;
    heartbeat.last_written_frame = 0;
    matlab_pid = 0;
    try
        matlab_pid = feature('getpid');
    catch
        matlab_pid = 0;
    end
    hostname = getenv('COMPUTERNAME');
    if isempty(hostname)
        hostname = '';
    end

    heartbeat.payload = struct( ...
        'run_id', ['run_' datestr(now, 'yyyymmdd_HHMMSS')], ...
        'updated_at', '', ...
        'status', 'starting', ...
        'step', '', ...
        'step_label', '', ...
        'current_frame', 0, ...
        'total_frames', 0, ...
        'progress_ratio', 0, ...
        'last_checkpoint', '', ...
        'matlab_pid', matlab_pid, ...
        'hostname', hostname, ...
        'output_path', config.output_path, ...
        'message', '');
end


function message = format_exception_message(ME)
    if isempty(ME.identifier)
        message = ME.message;
    else
        message = sprintf('%s: %s', ME.identifier, ME.message);
    end
end


function add_project_paths(project_root)
    remove_worktree_paths(project_root);

    parts = strsplit(genpath(project_root), pathsep);
    worktree_root = normalize_path(fullfile(project_root, '.worktrees'));
    keep = {};
    for i = 1:numel(parts)
        p = parts{i};
        if isempty(p)
            continue;
        end
        if startsWith(normalize_path(p), worktree_root)
            continue;
        end
        keep{end+1} = p; %#ok<AGROW>
    end

    if ~isempty(keep)
        addpath(strjoin(keep, pathsep));
    end
end


function remove_worktree_paths(project_root)
    worktree_root = normalize_path(fullfile(project_root, '.worktrees'));
    parts = strsplit(path, pathsep);
    for i = 1:numel(parts)
        p = parts{i};
        if isempty(p)
            continue;
        end
        if startsWith(normalize_path(p), worktree_root)
            rmpath(p);
        end
    end
end


function p_norm = normalize_path(p)
    p_norm = lower(strrep(char(p), '/', filesep));
    while ~isempty(p_norm) && p_norm(end) == filesep
        p_norm = p_norm(1:end-1);
    end
end
