%% extract_all.m
%  Unified batch extraction: axial saturation profiles + blob size PDFs.
%
%  Two-tier strategy to obtain the residual-frame mask:
%    1) PRIMARY:  Load last_mask from the last checkpoint_*.mat 
%                 (pipeline's own result with locked threshold — most accurate)
%    2) FALLBACK: Re-segment the last frame from TIF on-the-fly
%                 (same approach as the pipeline, but threshold may differ slightly)
%
%  Both paths compute blob areas via bwconncomp (NOT from results.blobs,
%  which is from frame 1 / initial state).
%
%  Outputs:
%    axial_profile_<LABEL>.csv  — per-experiment axial Sn(x)
%    blob_pdf_all_conditions.csv — combined blob size PDFs

pipeline_root = 'D:\00 Claude Code\01 MATLAB CODE\01 Microfluid';
addpath(genpath(pipeline_root));

output_dir = 'D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\Drawing\00';
if ~isfolder(output_dir), mkdir(output_dir); end

%% Experiment list
%  Label, Contaminant, Q(µL/min), mat_path, expected_Sn_res, expected_blobs, residual_tif
%  residual_tif: (optional) path to the TIF file whose LAST PAGE is the residual frame.
%               Used as fallback when no checkpoint is available.
experiments = {
    'Dod-2',  'Dodecane', 2, 'D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\01 databased\14 LNAPL-2UL\02 Water Displacement\output_20260319_203848\results_20260319_213238.mat',  0.334, 319, ''
    'Dod-4',  'Dodecane', 4, 'G:\微流控\06 LNAPL-4UL\02 WATER DISPLACE\output_20260309_115339\results_20260309_124221.mat',   0.316, 338, 'G:\微流控\06 LNAPL-4UL\02 WATER DISPLACE\02 WATER NAPL 2 3 SECONDS_15.tif'
    'Dod-6',  'Dodecane', 6, 'D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\01 databased\13 LNAPL-6UL\02 Water Displacement\output_20260318_224745\results_20260318_232323.mat',  0.293, 387, ''
    'BD-2',   'BD',       2, 'G:\微流控\08 1-BD 2UL\02\output_20260312_181726\results_20260312_193808.mat',                    0.354, 198, ''
    'BD-4',   'BD',       4, 'G:\微流控\07 1-BD 4UL\02 Water Displacement\output_20260310_231726\results_20260311_065711.mat', 0.343, 244, 'G:\微流控\07 1-BD 4UL\02 Water Displacement\01 DNAPL 3S 4UL 3_33.tif'
    'BD-6',   'BD',       6, 'G:\微流控\09 1-BD 6UL\02 Water Displacement\output_20260313_151504\results_20260313_163944.mat', 0.268, 265, ''
    'BO-2',   'BO',       2, 'G:\微流控\10 1-BO 2UL\02  Water Displacement\output_20260318_000749\results_20260318_004331.mat',0.300, 241, ''
    'BO-4',   'BO',       4, 'G:\微流控\11 1-BO 4 UL\02  Water Displacement\output_20260313_193027\results_20260313_201738.mat',0.198, 269, ''
    'BO-6-1', 'BO',       6, 'G:\微流控\12 1-BO 6 UL\1\02  Water Displacement\output_20260317_003659\results_20260317_012632.mat',0.158, 302, ''
    'BO-6-2', 'BO',       6, 'G:\微流控\12 1-BO 6 UL\2\02  Water Displacement\output_20260316_234803\results_20260317_002816.mat',0.158, 302, ''
};

N_bins_axial = 50;
N_bins_pdf = 30;

fprintf('==========================================================\n');
fprintf('  Unified Extraction: Axial Profiles + Blob PDFs\n');
fprintf('  Strategy: checkpoint → TIF fallback\n');
fprintf('==========================================================\n\n');

all_pdf = table();

for e = 1:size(experiments, 1)
    label       = experiments{e, 1};
    contaminant = experiments{e, 2};
    Q_val       = experiments{e, 3};
    mat_path    = experiments{e, 4};
    expected_Sn = experiments{e, 5};
    expected_N  = experiments{e, 6};
    residual_tif = experiments{e, 7};

    fprintf('\n----------------------------------------------------------\n');
    fprintf('  [%d/%d] %s (%s, Q=%d µL/min)\n', e, size(experiments,1), label, contaminant, Q_val);
    fprintf('----------------------------------------------------------\n');

    output_folder = fileparts(mat_path);

    %% ============ Load MAT file ============
    try
        loaded = load(mat_path, 'config', 'results');
    catch
        try
            tmp_mat = [tempname '.mat'];
            ps_cmd = sprintf('powershell -Command "Copy-Item -LiteralPath ''%s'' -Destination ''%s''"', mat_path, tmp_mat);
            [st, ~] = system(ps_cmd);
            if st ~= 0
                fprintf('  SKIPPED: Cannot access MAT file\n');
                continue;
            end
            loaded = load(tmp_mat, 'config', 'results');
            delete(tmp_mat);
        catch ME
            fprintf('  SKIPPED: %s\n', ME.message);
            continue;
        end
    end

    config = loaded.config;
    results = loaded.results;

    if ~isfield(results, 'flow_domain')
        fprintf('  WARNING: No flow_domain. Skipping.\n');
        continue;
    end
    flow_domain = results.flow_domain;
    [H, W] = size(flow_domain);
    fprintf('  Flow domain: %d × %d\n', H, W);

    %% ============ TIER 1: Try loading last_mask from checkpoint ============
    final_mask = [];
    mask_source = '';
    locked_threshold = [];

    % Try to find checkpoint files in the output folder
    cp_loaded_ok = false;
    try
        cp_files = dir(fullfile(output_folder, 'checkpoint_*.mat'));
        if ~isempty(cp_files)
            [~, si] = sort({cp_files.name});
            last_cp = fullfile(output_folder, cp_files(si(end)).name);
            try
                cp_data = load(last_cp, 'last_mask', 'locked_threshold', 'last_frame');
                cp_loaded_ok = true;
            catch
                tmp_cp = [tempname '.mat'];
                copyfile(last_cp, tmp_cp, 'f');
                cp_data = load(tmp_cp, 'last_mask', 'locked_threshold', 'last_frame');
                delete(tmp_cp);
                cp_loaded_ok = true;
            end
        end
    catch
        % dir() may fail on Chinese paths; try PowerShell
    end

    if ~cp_loaded_ok
        try
            ps_cmd = sprintf('powershell -Command "Get-ChildItem -LiteralPath ''%s'' -Filter ''checkpoint_*.mat'' | Sort-Object Name | Select-Object -Last 1 -ExpandProperty Name"', output_folder);
            [st, ps_out] = system(ps_cmd);
            if st == 0 && ~isempty(strtrim(ps_out))
                last_cp_name = strtrim(ps_out);
                last_cp_path = fullfile(output_folder, last_cp_name);
                tmp_cp = [tempname '.mat'];
                ps_cmd2 = sprintf('powershell -Command "Copy-Item -LiteralPath ''%s'' -Destination ''%s''"', last_cp_path, tmp_cp);
                [st2, ~] = system(ps_cmd2);
                if st2 == 0
                    cp_data = load(tmp_cp, 'last_mask', 'locked_threshold', 'last_frame');
                    delete(tmp_cp);
                    cp_loaded_ok = true;
                end
            end
        catch
            % PowerShell also failed; no checkpoint available
        end
    end

    if cp_loaded_ok && isfield(cp_data, 'last_mask') && ~isempty(cp_data.last_mask)
        final_mask = logical(cp_data.last_mask);
        mask_source = 'checkpoint';
        if isfield(cp_data, 'locked_threshold')
            locked_threshold = cp_data.locked_threshold;
        end
        if isfield(cp_data, 'last_frame')
            fprintf('  ✓ Checkpoint loaded (frame %d)', cp_data.last_frame);
        else
            fprintf('  ✓ Checkpoint loaded');
        end
        if ~isempty(locked_threshold)
            fprintf(', threshold=%.4f', locked_threshold);
        end
        fprintf('\n');

        % Resize if needed
        if size(final_mask,1) ~= H || size(final_mask,2) ~= W
            final_mask = imresize(final_mask, [H, W], 'nearest') > 0;
        end
        final_mask = final_mask & flow_domain;
    end

    %% ============ TIER 2: Re-segment from TIF (fallback) ============
    if isempty(final_mask)
        mask_source = 'tif_resegment';

        %% --- If a specific residual TIF is provided, use it directly ---
        if ~isempty(residual_tif)
            fprintf('  No checkpoint. Using specified residual TIF:\n');
            fprintf('    %s\n', residual_tif);

            % Read the TIF (may need PowerShell copy for Chinese path)
            try
                info_r = imfinfo(residual_tif);
                last_page = numel(info_r);
                rgb_last = imread(residual_tif, last_page);
            catch
                [~, ~, ext] = fileparts(residual_tif);
                tmp_tif = [tempname ext];
                ps_cmd = sprintf('powershell -Command "Copy-Item -LiteralPath ''%s'' -Destination ''%s''"', residual_tif, tmp_tif);
                [st, ~] = system(ps_cmd);
                if st ~= 0 || ~exist(tmp_tif, 'file')
                    fprintf('  ERROR: Cannot access residual TIF. Skipping.\n');
                    continue;
                end
                info_r = imfinfo(tmp_tif);
                last_page = numel(info_r);
                rgb_last = imread(tmp_tif, last_page);
                delete(tmp_tif);
            end
            if isa(rgb_last, 'uint16'), rgb_last = im2uint8(rgb_last); end
            if size(rgb_last, 3) == 1, rgb_last = repmat(rgb_last, [1 1 3]); end
            fprintf('  Loaded page %d/%d\n', last_page, last_page);

            % Preprocess and segment
            [rgb_rot, ~, ~] = rotate_and_crop(rgb_last, config);
            [rgb_corr, ~] = correct_illumination(rgb_rot, ...
                config.illumination.method, config.illumination, false);

            is_v2 = endsWith(config.segmentation.method, '_v2');
            config_locked = config;

            % Get threshold from frame 1 of the original TIF stack
            tif_paths = config.multipage_tif_path;
            if ischar(tif_paths), tif_paths = {tif_paths}; end
            try
                rgb1 = imread(tif_paths{1}, 1);
            catch
                [~, ~, ext1] = fileparts(tif_paths{1});
                tmp1 = [tempname ext1];
                ps_cmd = sprintf('powershell -Command "Copy-Item -LiteralPath ''%s'' -Destination ''%s''"', tif_paths{1}, tmp1);
                [st, ~] = system(ps_cmd);
                if st == 0
                    rgb1 = imread(tmp1, 1);
                    delete(tmp1);
                else
                    % Use the residual TIF's first page as fallback
                    try
                        rgb1 = imread(residual_tif, 1);
                    catch
                        % Already copied above; re-copy
                        tmp_tif2 = [tempname ext];
                        ps_cmd = sprintf('powershell -Command "Copy-Item -LiteralPath ''%s'' -Destination ''%s''"', residual_tif, tmp_tif2);
                        system(ps_cmd);
                        rgb1 = imread(tmp_tif2, 1);
                        delete(tmp_tif2);
                    end
                end
            end
            if isa(rgb1, 'uint16'), rgb1 = im2uint8(rgb1); end
            if size(rgb1, 3) == 1, rgb1 = repmat(rgb1, [1 1 3]); end
            [rgb1_rot, ~, ~] = rotate_and_crop(rgb1, config);
            [rgb1_corr, ~] = correct_illumination(rgb1_rot, ...
                config.illumination.method, config.illumination, false);

            if ~isfield(config.segmentation, 'fixed_threshold') || isempty(config.segmentation.fixed_threshold)
                if is_v2
                    [~, ~, seg_info] = segment_DNAPL_v2(rgb1_corr, flow_domain, config);
                else
                    [~, ~, seg_info] = segment_DNAPL(rgb1_corr, flow_domain, config);
                end
                config_locked.segmentation.fixed_threshold = seg_info.threshold;
                fprintf('  Threshold from frame 1: %.4f\n', seg_info.threshold);
            else
                config_locked.segmentation.fixed_threshold = config.segmentation.fixed_threshold;
            end

            if is_v2
                [final_mask, ~, ~] = segment_DNAPL_v2(rgb_corr, flow_domain, config_locked);
            else
                [final_mask, ~, ~] = segment_DNAPL(rgb_corr, flow_domain, config_locked);
            end
            final_mask = final_mask & flow_domain;
            mask_source = 'specified_tif';
        else
        %% --- Generic TIF fallback (frame estimation) ---
        fprintf('  No checkpoint found. Re-segmenting from TIF...\n');

        % Build frame index
        tif_paths = config.multipage_tif_path;
        if ischar(tif_paths), tif_paths = {tif_paths}; end

        frame_index = struct('tif_path', {}, 'page', {});
        for f = 1:numel(tif_paths)
            fp = tif_paths{f};
            try
                info_f = imfinfo(fp);
            catch
                [~, ~, ext] = fileparts(fp);
                tmp_tif = [tempname ext];
                ps_cmd = sprintf('powershell -Command "Copy-Item -LiteralPath ''%s'' -Destination ''%s''"', fp, tmp_tif);
                [st, ~] = system(ps_cmd);
                if st == 0 && exist(tmp_tif, 'file')
                    info_f = imfinfo(tmp_tif);
                    delete(tmp_tif);
                else
                    if exist(tmp_tif, 'file'), delete(tmp_tif); end
                    continue;
                end
            end
            for p = 1:numel(info_f)
                idx = numel(frame_index) + 1;
                frame_index(idx).tif_path = fp;
                frame_index(idx).page = p;
            end
        end

        % Dir fallback if config paths fail
        if isempty(frame_index)
            fprintf('  Config TIF paths inaccessible. Scanning directory...\n');
            tif_dir = fileparts(fileparts(mat_path));
            d_tifs = [dir(fullfile(tif_dir, '*.tif')); dir(fullfile(tif_dir, '*.tiff'))];

            cfg_basenames = cell(numel(tif_paths), 1);
            for k = 1:numel(tif_paths)
                [~, bn, ex] = fileparts(tif_paths{k});
                cfg_basenames{k} = [bn ex];
            end
            keep = false(numel(d_tifs), 1);
            for k = 1:numel(d_tifs)
                keep(k) = any(strcmp(d_tifs(k).name, cfg_basenames));
            end
            if any(keep), d_tifs = d_tifs(keep); end

            sk = zeros(numel(d_tifs), 2);
            for k = 1:numel(d_tifs)
                nums = regexp(d_tifs(k).name, '(\d+)', 'tokens');
                if numel(nums) >= 1, sk(k,1) = str2double(nums{1}{1}); end
                if numel(nums) >= 2, sk(k,2) = str2double(nums{end}{1}); end
            end
            [~, si] = sortrows(sk);
            d_tifs = d_tifs(si);

            max_bytes = max([d_tifs.bytes]);
            bpp = max_bytes / 72;
            for f = 1:numel(d_tifs)
                fp = fullfile(tif_dir, d_tifs(f).name);
                np_est = max(1, round(d_tifs(f).bytes / bpp));
                for p = 1:np_est
                    idx = numel(frame_index) + 1;
                    frame_index(idx).tif_path = fp;
                    frame_index(idx).page = p;
                end
            end
            fprintf('  Found %d TIF files → %d estimated frames\n', numel(d_tifs), numel(frame_index));
        end

        % Apply pages filter
        if isfield(config, 'pages') && ~isempty(config.pages)
            valid_pages = config.pages(config.pages >= 1 & config.pages <= numel(frame_index));
            frame_index = frame_index(valid_pages);
        end

        total_frames = numel(frame_index);
        if total_frames == 0
            fprintf('  ERROR: No frames accessible. Skipping.\n');
            continue;
        end
        fprintf('  Total frames: %d → loading last frame...\n', total_frames);

        % Segment last frame
        rgb_last = load_frame(total_frames, frame_index);
        [rgb_rot, ~, ~] = rotate_and_crop(rgb_last, config);
        [rgb_corr, ~] = correct_illumination(rgb_rot, ...
            config.illumination.method, config.illumination, false);

        is_v2 = endsWith(config.segmentation.method, '_v2');
        config_locked = config;

        if ~isfield(config.segmentation, 'fixed_threshold') || isempty(config.segmentation.fixed_threshold)
            rgb1 = load_frame(1, frame_index);
            [rgb1_rot, ~, ~] = rotate_and_crop(rgb1, config);
            [rgb1_corr, ~] = correct_illumination(rgb1_rot, ...
                config.illumination.method, config.illumination, false);
            if is_v2
                [~, ~, seg_info] = segment_DNAPL_v2(rgb1_corr, flow_domain, config);
            else
                [~, ~, seg_info] = segment_DNAPL(rgb1_corr, flow_domain, config);
            end
            config_locked.segmentation.fixed_threshold = seg_info.threshold;
            fprintf('  Threshold from frame 1: %.4f\n', seg_info.threshold);
        else
            config_locked.segmentation.fixed_threshold = config.segmentation.fixed_threshold;
            fprintf('  Using config fixed_threshold: %.4f\n', config.segmentation.fixed_threshold);
        end

        if is_v2
            [final_mask, ~, ~] = segment_DNAPL_v2(rgb_corr, flow_domain, config_locked);
        else
            [final_mask, ~, ~] = segment_DNAPL(rgb_corr, flow_domain, config_locked);
        end
        final_mask = final_mask & flow_domain;
        end  % end of else (generic TIF fallback)
    end

    %% ============ Verify Sn ============
    Sn_from_mask = sum(final_mask(:)) / sum(flow_domain(:));

    if isfield(results, 'solubilization') && isfield(results.solubilization, 'saturation_vs_time')
        Sn_pipeline = results.solubilization.saturation_vs_time(end);
        fprintf('  Sn from mask:     %.3f  [source: %s]\n', Sn_from_mask, mask_source);
        fprintf('  Sn from pipeline: %.3f\n', Sn_pipeline);
        fprintf('  Expected Sn_res:  %.3f\n', expected_Sn);
    else
        fprintf('  Sn from mask: %.3f (expected %.3f)  [source: %s]\n', Sn_from_mask, expected_Sn, mask_source);
    end

    if Sn_from_mask > 0.5
        fprintf('  *** WARNING: Sn > 0.5 — possible wrong frame ***\n');
    end

    %% ============ PART 1: Blob Size PDF ============
    fprintf('\n  --- Blob PDF ---\n');

    cc = bwconncomp(final_mask, 8);
    props = regionprops(cc, 'Area');
    areas_px = [props.Area]';
    n_blobs = numel(areas_px);

    px_um = config.physical.pixel_size * 1e6;
    areas_um2 = areas_px * px_um^2;

    fprintf('  Pixel size: %.2f µm/px\n', px_um);
    fprintf('  Blob count: %d (expected ~ %d)\n', n_blobs, expected_N);

    areas_valid = areas_um2(areas_um2 > 0);
    if ~isempty(areas_valid) && numel(areas_valid) >= 2
        edges = logspace(log10(min(areas_valid)), log10(max(areas_valid)), N_bins_pdf + 1);
        counts = histcounts(areas_valid, edges);
        bin_centers = sqrt(edges(1:end-1) .* edges(2:end));
        bin_widths = diff(edges);
        pdf_values = counts ./ (sum(counts) .* bin_widths);

        valid = counts > 0;
        bc = bin_centers(valid)';
        pv = pdf_values(valid)';
        n_valid = sum(valid);

        T_part = table(bc, pv, ...
            repmat({label}, n_valid, 1), ...
            repmat({contaminant}, n_valid, 1), ...
            repmat(Q_val, n_valid, 1), ...
            'VariableNames', {'BinCenter_um2', 'PDF', 'Label', 'Contaminant', 'Q_uLmin'});
        all_pdf = [all_pdf; T_part]; %#ok<AGROW>

        fprintf('  PDF: %d non-zero bins\n', n_valid);

        if n_valid >= 5
            fit_s = max(1, round(n_valid * 0.15));
            fit_e = min(n_valid, round(n_valid * 0.85));
            fit_idx = fit_s:fit_e;
            if numel(fit_idx) >= 3
                p = polyfit(log10(bc(fit_idx)), log10(pv(fit_idx)), 1);
                fprintf('  Power-law α = %.2f\n', p(1));
            end
        end
    else
        fprintf('  WARNING: Not enough valid blob areas for PDF.\n');
    end

    %% ============ PART 2: Axial Saturation Profile ============
    fprintf('\n  --- Axial Profile ---\n');

    bin_edges = linspace(1, W+1, N_bins_axial+1);
    Sn_x = zeros(N_bins_axial, 1);
    x_centers = zeros(N_bins_axial, 1);
    W_domain = zeros(N_bins_axial, 1);

    for b = 1:N_bins_axial
        c1 = round(bin_edges(b));
        c2 = min(round(bin_edges(b+1)) - 1, W);
        strip_m = final_mask(:, c1:c2);
        strip_d = flow_domain(:, c1:c2);
        pp = sum(strip_d(:));
        np = sum(strip_m(:) & strip_d(:));
        if pp > 0, Sn_x(b) = np / pp; end
        x_centers(b) = (c1 + c2) / 2;
        W_domain(b) = sum(any(strip_d, 2));
    end

    x_norm = (x_centers - min(x_centers)) / (max(x_centers) - min(x_centers));

    T_ax = table(x_norm, Sn_x, W_domain, ...
        'VariableNames', {'x_norm', 'Sn_x', 'W_domain_px'});
    csv_ax = fullfile(output_dir, sprintf('axial_profile_%s.csv', label));
    writetable(T_ax, csv_ax);
    fprintf('  Sn_x range: [%.3f, %.3f]\n', min(Sn_x), max(Sn_x));
    fprintf('  Saved: axial_profile_%s.csv\n', label);
end

%% Save combined blob PDF
pdf_csv = fullfile(output_dir, 'blob_pdf_all_conditions.csv');
writetable(all_pdf, pdf_csv);

fprintf('\n==========================================================\n');
fprintf('  All done!\n');
fprintf('  Axial profiles: see %s\n', output_dir);
fprintf('  Blob PDF: %d rows → %s\n', height(all_pdf), pdf_csv);
fprintf('==========================================================\n');
