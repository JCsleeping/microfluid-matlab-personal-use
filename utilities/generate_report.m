function generate_report(results, config)
% GENERATE_REPORT  Generate a formatted analysis report (.txt + .md).
%
%   generate_report(results, config)
%
%   Produces:
%     1. A human-readable text report: <output_path>/analysis_report.txt
%     2. A Markdown report:            <output_path>/analysis_report.md
%
%   Report contents:
%     - Experiment metadata (data path, num frames, method, etc.)
%     - Single-frame analysis summary (Sn, blob count, interface)
%     - Time-series statistics (smoothed mean blob size, dissolution phases)
%     - Key metrics table

    out_dir = config.output_path;
    if ~isfolder(out_dir), mkdir(out_dir); end

    %% Collect data
    R = struct();

    % Metadata
    R.data_path  = config.data_path;
    R.method     = config.segmentation.method;
    R.num_frames = numel(results.time_vector);
    R.pixel_size = config.physical.pixel_size;
    R.timestamp  = datestr(now, 'yyyy-mm-dd HH:MM:SS');

    % Single-frame (STEP 3)
    if isfield(results, 'saturation')
        R.Sn_single = results.saturation.Sn;
        R.Sw_single = results.saturation.Sw;
        R.dnapl_volume_m3 = results.saturation.dnapl_volume_m3;
    end
    if isfield(results, 'chip_geometric_volume_m3')
        R.chip_geometric_volume_m3 = results.chip_geometric_volume_m3;
    end
    if isfield(results, 'flow_domain_volume_m3')
        R.flow_domain_volume_m3 = results.flow_domain_volume_m3;
    end
    if isfield(results, 'blobs')
        R.num_blobs_single = results.blobs.num_blobs;
    end

    % Time-series (STEP 4)
    has_sol = isfield(results, 'solubilization');
    if has_sol
        sol = results.solubilization;
        tv  = results.time_vector(:);

        R.Sn_initial = sol.saturation_vs_time(1);
        R.Sn_final   = sol.saturation_vs_time(end);
        R.Sn_reduction = 100 * (R.Sn_initial - R.Sn_final) / max(R.Sn_initial, eps);

        R.blobs_initial = sol.num_blobs_vs_time(1);
        R.blobs_final   = sol.num_blobs_vs_time(end);
        R.blobs_max     = max(sol.num_blobs_vs_time);

        % Smoothed mean blob size (median filter, window=5)
        raw_mbs = sol.mean_blob_size_vs_time;
        if numel(raw_mbs) >= 5
            R.mean_blob_smooth = medfilt1(raw_mbs, 5);
        else
            R.mean_blob_smooth = raw_mbs;
        end
        R.mean_blob_initial = R.mean_blob_smooth(1);
        R.mean_blob_final   = R.mean_blob_smooth(end);

        % Interface
        R.interface_initial = sol.interface_area_vs_time(1);
        R.interface_final   = sol.interface_area_vs_time(end);
        R.interface_max     = max(sol.interface_area_vs_time);

        % Dissolution rate
        R.diss_rate_mean = mean(abs(sol.dissolution_rate));
        R.diss_rate_max  = max(abs(sol.dissolution_rate));

        % Mass dissolved
        R.mass_dissolved = sol.mass_dissolved;

        % Duration
        R.duration_s = tv(end) - tv(1);

        % Phase detection: find transition point (max |dSn/dt|)
        if numel(sol.dissolution_rate) > 1
            [~, trans_idx] = max(abs(sol.dissolution_rate));
            R.transition_time = tv(min(trans_idx+1, numel(tv)));
            R.transition_frame = trans_idx;
        else
            R.transition_time = NaN;
            R.transition_frame = NaN;
        end
    end

    %% Write TXT report
    txt_path = fullfile(out_dir, 'analysis_report.txt');
    fid = fopen(txt_path, 'w');
    write_report(fid, R, has_sol, 'txt');
    fclose(fid);
    fprintf('  Report saved: %s\n', txt_path);

    %% Write MD report
    md_path = fullfile(out_dir, 'analysis_report.md');
    fid = fopen(md_path, 'w');
    write_report(fid, R, has_sol, 'md');
    fclose(fid);
    fprintf('  Report saved: %s\n', md_path);
end


function write_report(fid, R, has_sol, fmt)
    is_md = strcmp(fmt, 'md');

    %% Title
    if is_md
        fprintf(fid, '# DNAPL Analysis Report\n\n');
        fprintf(fid, '> Generated: %s\n\n', R.timestamp);
    else
        fprintf(fid, '==========================================================\n');
        fprintf(fid, '  DNAPL ANALYSIS REPORT\n');
        fprintf(fid, '  Generated: %s\n', R.timestamp);
        fprintf(fid, '==========================================================\n\n');
    end

    %% Section 1: Experiment Info
    section_header(fid, '1. Experiment Info', is_md);
    kv(fid, 'Data Path',        R.data_path, is_md);
    kv(fid, 'Segmentation',     R.method, is_md);
    kv(fid, 'Total Frames',     sprintf('%d', R.num_frames), is_md);
    if isnumeric(R.pixel_size)
        kv(fid, 'Pixel Size', sprintf('%.4f mm/px', R.pixel_size), is_md);
    else
        kv(fid, 'Pixel Size', R.pixel_size, is_md);
    end
    if isfield(R, 'chip_geometric_volume_m3')
        kv(fid, 'Chip Geometric Volume', sprintf('%.4e m^3', R.chip_geometric_volume_m3), is_md);
    end
    if isfield(R, 'flow_domain_volume_m3')
        kv(fid, 'Flow Domain Pore Volume', sprintf('%.4e m^3', R.flow_domain_volume_m3), is_md);
    end
    fprintf(fid, '\n');

    %% Section 2: Single-Frame Analysis
    if isfield(R, 'Sn_single')
        section_header(fid, '2. Single-Frame Analysis (Frame 1)', is_md);
        kv(fid, 'DNAPL Saturation (Sn)',  sprintf('%.4f', R.Sn_single), is_md);
        kv(fid, 'Water Saturation (Sw)',   sprintf('%.4f', R.Sw_single), is_md);
        if isfield(R, 'dnapl_volume_m3')
            kv(fid, 'DNAPL Volume (Frame 1)', sprintf('%.4e m^3', R.dnapl_volume_m3), is_md);
        end
        if isfield(R, 'num_blobs_single')
            kv(fid, 'Number of Blobs',     sprintf('%d', R.num_blobs_single), is_md);
        end
        fprintf(fid, '\n');
    end

    %% Section 3: Time-Series Summary
    if has_sol
        section_header(fid, '3. Dissolution Dynamics', is_md);

        % 3a. Saturation
        sub_header(fid, 'Saturation', is_md);
        kv(fid, 'Initial Sn',   sprintf('%.4f', R.Sn_initial), is_md);
        kv(fid, 'Final Sn',     sprintf('%.4f', R.Sn_final), is_md);
        kv(fid, 'Reduction',    sprintf('%.1f%%', R.Sn_reduction), is_md);
        kv(fid, 'Duration',     sprintf('%.0f s (%.1f min)', R.duration_s, R.duration_s/60), is_md);
        fprintf(fid, '\n');

        % 3b. Blobs
        sub_header(fid, 'Blob Evolution', is_md);
        kv(fid, 'Initial Blobs', sprintf('%d', R.blobs_initial), is_md);
        kv(fid, 'Final Blobs',   sprintf('%d', R.blobs_final), is_md);
        kv(fid, 'Peak Blobs',    sprintf('%d', R.blobs_max), is_md);
        kv(fid, 'Mean Blob Size (initial, smoothed)', sprintf('%.0f px', R.mean_blob_initial), is_md);
        kv(fid, 'Mean Blob Size (final, smoothed)',   sprintf('%.0f px', R.mean_blob_final), is_md);
        fprintf(fid, '\n');

        % 3c. Interface
        sub_header(fid, 'Interface', is_md);
        kv(fid, 'Initial DNAPL-Water Interface',  sprintf('%.0f px', R.interface_initial), is_md);
        kv(fid, 'Final DNAPL-Water Interface',    sprintf('%.0f px', R.interface_final), is_md);
        kv(fid, 'Peak Interface',                  sprintf('%.0f px', R.interface_max), is_md);
        fprintf(fid, '\n');

        % 3d. Dissolution
        sub_header(fid, 'Dissolution Rate', is_md);
        kv(fid, 'Mean |dSn/dt|',  sprintf('%.6f s^-1', R.diss_rate_mean), is_md);
        kv(fid, 'Max |dSn/dt|',   sprintf('%.6f s^-1', R.diss_rate_max), is_md);
        kv(fid, 'Mass Dissolved',  sprintf('%.4e kg', R.mass_dissolved), is_md);
        fprintf(fid, '\n');

        % 3e. Phase transition
        if ~isnan(R.transition_time)
            sub_header(fid, 'Phase Transition', is_md);
            kv(fid, 'Transition Time',  sprintf('%.0f s (frame %d)', R.transition_time, R.transition_frame), is_md);
            fprintf(fid, '\n');
        end
    end

    %% Section 4: Summary Table (MD only)
    if is_md && has_sol
        section_header(fid, '4. Key Metrics Summary', is_md);
        fprintf(fid, '| Metric | Initial | Final | Change |\n');
        fprintf(fid, '| ------ | ------- | ----- | ------ |\n');
        fprintf(fid, '| Sn | %.4f | %.4f | -%.1f%% |\n', R.Sn_initial, R.Sn_final, R.Sn_reduction);
        fprintf(fid, '| Blob Count | %d | %d | %+d |\n', R.blobs_initial, R.blobs_final, R.blobs_final - R.blobs_initial);
        fprintf(fid, '| Mean Blob Size [px] | %.0f | %.0f | %.1f%% |\n', ...
            R.mean_blob_initial, R.mean_blob_final, ...
            100*(R.mean_blob_final - R.mean_blob_initial)/max(R.mean_blob_initial, eps));
        fprintf(fid, '| Interface [px] | %.0f | %.0f | %.1f%% |\n', ...
            R.interface_initial, R.interface_final, ...
            100*(R.interface_final - R.interface_initial)/max(R.interface_initial, eps));
        fprintf(fid, '\n');
    end
end


%% Helper functions
function section_header(fid, title, is_md)
    if is_md
        fprintf(fid, '## %s\n\n', title);
    else
        fprintf(fid, '--- %s ---\n\n', upper(title));
    end
end

function sub_header(fid, title, is_md)
    if is_md
        fprintf(fid, '### %s\n\n', title);
    else
        fprintf(fid, '  [%s]\n', title);
    end
end

function kv(fid, key, val, is_md)
    if is_md
        fprintf(fid, '- **%s**: %s\n', key, val);
    else
        fprintf(fid, '  %-40s %s\n', [key ':'], val);
    end
end
