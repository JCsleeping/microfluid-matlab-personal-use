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
                    if ~isempty(config)
                        save(fname, 'results', 'config', '-v7.3');
                    else
                        save(fname, 'results', '-v7.3');
                    end
                    fprintf('  Saved: %s\n', fname);
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
                            'VariableNames', {'Sn','Sw','DNAPL_area_px','Pore_area_px'});
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
                        % Build base columns
                        cols = {results.time_vector(:), ...
                            sol.saturation_vs_time, ...
                            sol.num_blobs_vs_time, ...
                            sol.mean_blob_size_vs_time, ...
                            sol.interface_area_vs_time};
                        names = {'Time','Sn','NumBlobs','MeanBlobSize','InterfaceArea'};
                        % Append mass curve if available
                        if isfield(sol, 'mass_dissolved_vs_time')
                            cols{end+1} = sol.mass_dissolved_vs_time;
                            names{end+1} = 'MassDissolvedKg';
                        end
                        T = table(cols{:}, 'VariableNames', names);
                        writetable(T, fname);
                        fprintf('  Saved: %s\n', fname);
                    catch ME
                        warning('export_results:saveFailed', ...
                            'Failed to save timeseries CSV: %s', ME.message);
                    end
                else
                    fprintf('  Skipped: timeseries.csv (no solubilization data)\n');
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
                        cols = {results.time_vector(:), ...
                            sol.saturation_vs_time, ...
                            sol.num_blobs_vs_time, ...
                            sol.mean_blob_size_vs_time, ...
                            sol.interface_area_vs_time};
                        names = {'Time','Sn','NumBlobs','MeanBlobSize','InterfaceArea'};
                        if isfield(sol, 'mass_dissolved_vs_time')
                            cols{end+1} = sol.mass_dissolved_vs_time;
                            names{end+1} = 'MassDissolvedKg';
                        end
                        T = table(cols{:}, 'VariableNames', names);
                        writetable(T, fname, 'Sheet', 'Time Series');
                    end
                    fprintf('  Saved: %s\n', fname);
                catch ME
                    warning('export_results:saveFailed', ...
                        'Failed to save XLSX file: %s', ME.message);
                end
        end
    end
end
