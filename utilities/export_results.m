function export_results(results, output_path, formats, config)
% EXPORT_RESULTS  Save analysis results to files.
%
%   export_results(results, output_path, formats)
%   export_results(results, output_path, formats, config)
%
%   Inputs:
%       results     - Pipeline results struct
%       output_path - Directory to save files
%       formats     - Cell array of format strings: 'mat', 'csv', 'xlsx'
%       config      - (optional) Pipeline config struct, saved in .mat

    if nargin < 3, formats = {'mat', 'csv'}; end
    if nargin < 4, config = []; end
    if ~isfolder(output_path), mkdir(output_path); end

    timestamp = datestr(now, 'yyyymmdd_HHMMSS');

    for k = 1:numel(formats)
        switch lower(formats{k})
            case 'mat'
                try
                    fname = fullfile(output_path, ['results_' timestamp '.mat']);
                    % Strip bulky masks before saving (copy-on-write: caller unaffected)
                    if isfield(results, 'solubilization') && ...
                            isfield(results.solubilization, 'masks')
                        results.solubilization = rmfield(results.solubilization, 'masks');
                    end
                    % Save to temp file first (workaround for non-ASCII paths)
                    tmp_mat = [tempname '.mat'];
                    if ~isempty(config)
                        save(tmp_mat, 'results', 'config', '-v7.3');
                    else
                        save(tmp_mat, 'results', '-v7.3');
                    end
                    [ok, msg] = copyfile(tmp_mat, fname, 'f');
                    if ~ok
                        warning('export_results:copyFailed', ...
                            'Saved temp MAT but copy failed: %s', msg);
                        fprintf('  Temp MAT at: %s\n', tmp_mat);
                    else
                        delete(tmp_mat);
                        fprintf('  Saved: %s (masks excluded to reduce size)\n', fname);
                    end
                catch ME
                    warning('export_results:saveFailed', ...
                        'Failed to save MAT file: %s', ME.message);
                end

            case 'csv'
                % Blob properties table
                if isfield(results, 'blobs') && isfield(results.blobs, 'blob_table') ...
                        && ~isempty(results.blobs.blob_table)
                    try
                        fname = fullfile(output_path, ['blob_properties_' timestamp '.csv']);
                        writetable(results.blobs.blob_table, fname);
                        fprintf('  Saved: %s\n', fname);
                    catch ME
                        warning('export_results:saveFailed', ...
                            'Failed to save blob CSV: %s', ME.message);
                    end
                else
                    fprintf('  Skipped: blob_properties.csv (no blob data)\n');
                end

                % Saturation summary
                if isfield(results, 'saturation')
                    try
                        fname = fullfile(output_path, ['saturation_' timestamp '.csv']);
                        sat = results.saturation;
                        T = table(sat.Sn, sat.Sw, sat.dnapl_area_px, sat.pore_area_px, ...
                            results.chip_geometric_volume_m3, ...
                            results.flow_domain_volume_m3, sat.dnapl_volume_m3, ...
                            'VariableNames', {'Sn','Sw','DNAPL_area_px','Pore_area_px', ...
                                              'Chip_volume_m3','Pore_volume_m3','DNAPL_volume_m3'});
                        writetable(T, fname);
                        fprintf('  Saved: %s\n', fname);
                    catch ME
                        warning('export_results:saveFailed', ...
                            'Failed to save saturation CSV: %s', ME.message);
                    end
                else
                    fprintf('  Skipped: saturation.csv (no saturation data)\n');
                end

                % Time series
                if isfield(results, 'solubilization')
                    try
                        sol = results.solubilization;
                        fname = fullfile(output_path, ['timeseries_' timestamp '.csv']);
                        T = build_solubilization_timeseries_table(results.time_vector, sol);
                        writetable(T, fname);
                        fprintf('  Saved: %s\n', fname);
                    catch ME
                        warning('export_results:saveFailed', ...
                            'Failed to save timeseries CSV: %s', ME.message);
                    end
                else
                    fprintf('  Skipped: timeseries.csv (no solubilization data)\n');
                end

                % Architecture summary
                if isfield(results, 'architecture')
                    try
                        fname = fullfile(output_path, ['architecture_' timestamp '.csv']);
                        T = build_architecture_export_table(results.architecture);
                        writetable(T, fname);
                        fprintf('  Saved: %s\n', fname);
                    catch ME
                        warning('export_results:saveFailed', ...
                            'Failed to save architecture CSV: %s', ME.message);
                    end
                else
                    fprintf('  Skipped: architecture.csv (no architecture data)\n');
                end

            case 'xlsx'
                try
                    fname = fullfile(output_path, ['results_' timestamp '.xlsx']);
                    if isfield(results, 'blobs') && isfield(results.blobs, 'blob_table') ...
                            && ~isempty(results.blobs.blob_table)
                        writetable(results.blobs.blob_table, fname, 'Sheet', 'Blob Properties');
                    end
                    if isfield(results, 'solubilization')
                        sol = results.solubilization;
                        T = build_solubilization_timeseries_table(results.time_vector, sol);
                        writetable(T, fname, 'Sheet', 'Time Series');
                    end
                    if isfield(results, 'architecture')
                        T = build_architecture_export_table(results.architecture);
                        writetable(T, fname, 'Sheet', 'Architecture');
                    end
                    fprintf('  Saved: %s\n', fname);
                catch ME
                    warning('export_results:saveFailed', ...
                        'Failed to save XLSX file: %s', ME.message);
                end
        end
    end
end


function T = build_architecture_export_table(architecture)
    T = table( ...
        {read_architecture_field(architecture, {'type'}, '')}, ...
        read_architecture_field(architecture, {'indicators', 'Sn0'}, NaN), ...
        read_architecture_field(architecture, {'indicators', 'N_b'}, NaN), ...
        read_architecture_field(architecture, {'indicators', 'L_ow'}, NaN), ...
        read_architecture_field(architecture, {'indicators', 'a_i_2D'}, NaN), ...
        read_architecture_field(architecture, {'indicators', 'max_blob_fraction'}, NaN), ...
        read_architecture_field(architecture, {'indicators', 'Req_median'}, NaN), ...
        read_architecture_field(architecture, {'scores', 'pool_like'}, NaN), ...
        read_architecture_field(architecture, {'scores', 'ganglia_rich'}, NaN), ...
        'VariableNames', {'Type', 'Sn0', 'NumBlobs', 'L_ow', 'a_i_2D', ...
        'MaxBlobFraction', 'ReqMedian', 'PoolScore', 'GangliaScore'});
end


function value = read_architecture_field(s, path_tokens, default_value)
    value = default_value;
    current = s;

    for i = 1:numel(path_tokens)
        token = path_tokens{i};
        if ~isstruct(current) || ~isfield(current, token)
            return;
        end
        current = current.(token);
    end

    value = current;
end
