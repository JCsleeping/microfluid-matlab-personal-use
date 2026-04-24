%% extract_blob_pdf.m
%  Extract residual-state blob size PDF for all experiments.
%  Uses results.blobs.blob_table from results_*.mat (already final-frame data).
%  Output: blob_pdf_all_conditions.csv
%
%  Based on: plan_blob_size_pdf.md

pipeline_root = 'D:\00 Claude Code\01 MATLAB CODE\01 Microfluid';
addpath(genpath(pipeline_root));

output_dir = 'D:\00 Claude Code\03 会议\03 Result Analysis\01 Draft-Claude';

%% Experiment list with expected Sn_res and blob counts for verification
experiments = {
    % Label,    Contaminant, Q, mat_path,                                                                                     expected_Sn, expected_blobs
    'Dod-2',   'Dodecane', 2,  'D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\01 databased\14 LNAPL-2UL\02 Water Displacement\output_20260319_203848\results_20260319_213238.mat',  0.334, 319
    'Dod-4',   'Dodecane', 4,  'G:\微流控\06 LNAPL-4UL\02 WATER DISPLACE\output_20260309_115339\results_20260309_124221.mat',   0.316, 338
    'Dod-6',   'Dodecane', 6,  'D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\01 databased\13 LNAPL-6UL\02 Water Displacement\output_20260318_224745\results_20260318_232323.mat',  0.293, 387
    'BD-2',    'BD',       2,  'G:\微流控\08 1-BD 2UL\02\output_20260312_181726\results_20260312_193808.mat',                    0.354, 198
    'BD-4',    'BD',       4,  'G:\微流控\07 1-BD 4UL\02 Water Displacement\output_20260310_231726\results_20260311_065711.mat', 0.343, 244
    'BD-6',    'BD',       6,  'G:\微流控\09 1-BD 6UL\02 Water Displacement\output_20260313_151504\results_20260313_163944.mat', 0.268, 265
    'BO-2',    'BO',       2,  'G:\微流控\10 1-BO 2UL\02  Water Displacement\output_20260318_000749\results_20260318_004331.mat',0.300, 241
    'BO-4',    'BO',       4,  'G:\微流控\11 1-BO 4 UL\02  Water Displacement\output_20260313_193027\results_20260313_201738.mat',0.198, 269
    'BO-6',    'BO',       6,  'G:\微流控\12 1-BO 6 UL\1\02  Water Displacement\output_20260317_003659\results_20260317_012632.mat',0.158, 302
};

N_bins_pdf = 30;

fprintf('==========================================================\n');
fprintf('  Blob Size PDF Extraction\n');
fprintf('==========================================================\n\n');

all_pdf = table();  % combined output

for e = 1:size(experiments, 1)
    label       = experiments{e, 1};
    contaminant = experiments{e, 2};
    Q_val       = experiments{e, 3};
    mat_path    = experiments{e, 4};
    expected_Sn = experiments{e, 5};
    expected_N  = experiments{e, 6};

    fprintf('\n----------------------------------------------------------\n');
    fprintf('  [%d/%d] %s (%s, Q=%d µL/min)\n', e, size(experiments,1), label, contaminant, Q_val);
    fprintf('----------------------------------------------------------\n');

    %% Load results
    if ~exist(mat_path, 'file')
        try
            tmp_mat = [tempname '.mat'];
            ps_cmd = sprintf('powershell -Command "Copy-Item -LiteralPath ''%s'' -Destination ''%s''"', mat_path, tmp_mat);
            [st, ~] = system(ps_cmd);
            if st ~= 0
                fprintf('  SKIPPED: Cannot access %s\n', mat_path);
                continue;
            end
            loaded = load(tmp_mat, 'config', 'results');
            delete(tmp_mat);
        catch ME
            fprintf('  SKIPPED: %s\n', ME.message);
            continue;
        end
    else
        try
            loaded = load(mat_path, 'config', 'results');
        catch
            tmp_mat = [tempname '.mat'];
            copyfile(mat_path, tmp_mat, 'f');
            loaded = load(tmp_mat, 'config', 'results');
            delete(tmp_mat);
        end
    end

    config = loaded.config;
    results = loaded.results;

    %% Extract blob areas
    if ~isfield(results, 'blobs') || ~isfield(results.blobs, 'blob_table') ...
            || isempty(results.blobs.blob_table)
        fprintf('  WARNING: No blob_table found. Skipping.\n');
        continue;
    end

    blob_table = results.blobs.blob_table;
    areas_px = blob_table.Area;
    n_blobs = numel(areas_px);

    % Pixel size
    px_um = config.physical.pixel_size * 1e6;  % convert m to µm
    areas_um2 = areas_px * px_um^2;

    %% Verification
    fprintf('  Pixel size: %.2f µm/px\n', px_um);
    fprintf('  Blob count: %d (expected ~ %d)\n', n_blobs, expected_N);

    % Compute Sn from blob areas
    if isfield(results, 'flow_domain')
        total_pore_px = sum(results.flow_domain(:));
        Sn_check = sum(areas_px) / total_pore_px;
        fprintf('  Sn from blobs: %.3f (expected %.3f)\n', Sn_check, expected_Sn);

        if Sn_check > 0.5
            fprintf('  *** WARNING: Sn > 0.5 — possibly wrong frame! ***\n');
        end
        if abs(Sn_check - expected_Sn) > 0.10
            fprintf('  *** WARNING: Sn mismatch > 0.10 ***\n');
        end
    else
        fprintf('  (no flow_domain for Sn verification)\n');
    end

    %% Compute log-binned PDF
    if isempty(areas_um2) || all(areas_um2 <= 0)
        fprintf('  WARNING: No valid blob areas. Skipping.\n');
        continue;
    end

    areas_um2 = areas_um2(areas_um2 > 0);
    edges = logspace(log10(min(areas_um2)), log10(max(areas_um2)), N_bins_pdf + 1);
    counts = histcounts(areas_um2, edges);
    bin_centers = sqrt(edges(1:end-1) .* edges(2:end));  % geometric mean
    bin_widths = diff(edges);
    pdf_values = counts ./ (sum(counts) .* bin_widths);

    % Remove zero bins for cleaner output
    valid = counts > 0;
    bc = bin_centers(valid)';
    pv = pdf_values(valid)';
    n_valid = sum(valid);

    % Build table rows
    Label_col = repmat({label}, n_valid, 1);
    Contaminant_col = repmat({contaminant}, n_valid, 1);
    Q_col = repmat(Q_val, n_valid, 1);

    T_part = table(bc, pv, Label_col, Contaminant_col, Q_col, ...
        'VariableNames', {'BinCenter_um2', 'PDF', 'Label', 'Contaminant', 'Q_uLmin'});

    all_pdf = [all_pdf; T_part]; %#ok<AGROW>

    fprintf('  PDF: %d non-zero bins out of %d\n', n_valid, N_bins_pdf);

    %% Optional: power-law fit
    if n_valid >= 5
        log_bc = log10(bc);
        log_pv = log10(pv);
        % Fit middle portion
        fit_start = max(1, round(n_valid * 0.15));
        fit_end = min(n_valid, round(n_valid * 0.85));
        fit_idx = fit_start:fit_end;
        if numel(fit_idx) >= 3
            p = polyfit(log_bc(fit_idx), log_pv(fit_idx), 1);
            fprintf('  Power-law exponent α = %.2f\n', p(1));
        end
    end
end

%% Save combined CSV
output_csv = fullfile(output_dir, 'blob_pdf_all_conditions.csv');
writetable(all_pdf, output_csv);
fprintf('\n==========================================================\n');
fprintf('  Saved: %s\n', output_csv);
fprintf('  Total: %d rows from %d conditions\n', height(all_pdf), size(experiments, 1));
fprintf('==========================================================\n');
