function sol = characterize_solubilization(image_paths, flow_domain, time_vector, config)
% CHARACTERIZE_SOLUBILIZATION  Track DNAPL dissolution across a time series.
%
%   sol = characterize_solubilization(image_paths, flow_domain, time_vector, config)
%
%   Processes each frame through preprocessing and segmentation, then
%   tracks saturation, blob count, interfacial area, and dissolution
%   rate over time. Fits an exponential decay model.
%
%   Inputs:
%       image_paths  - Cell array of RGB image file paths
%       flow_domain  - M x N logical pore-space mask (constant)
%       time_vector  - 1 x N_frames time stamps [s or PV]
%       config       - Pipeline configuration struct
%
%   Output:
%       sol - Struct with time-series results

    % DEPRECATED: This is the v1 standalone file-based implementation.
    %   The main pipeline uses characterize_solubilization_v2.m instead.
    %   This function is retained for backward compatibility with scripts
    %   that pass file paths rather than pre-loaded images.
    warning('characterize_solubilization:deprecated', ...
        'characterize_solubilization (v1) is deprecated. Use characterize_solubilization_v2 instead.');

    num_frames = numel(image_paths);
    px = config.physical.pixel_size;

    %% Preallocate
    sol.saturation_vs_time     = zeros(num_frames, 1);
    sol.num_blobs_vs_time      = zeros(num_frames, 1);
    sol.mean_blob_size_vs_time = zeros(num_frames, 1);
    sol.interface_area_vs_time = zeros(num_frames, 1);
    sol.masks                  = cell(num_frames, 1);

    %% Process each frame
    for t = 1:num_frames
        fprintf('\n  --- Frame %d / %d ---\n', t, num_frames);

        % Load and preprocess
        rgb = imread(image_paths{t});
        if isa(rgb, 'uint16'), rgb = im2uint8(rgb); end
        [rgb_rot, ~, ~] = rotate_and_crop(rgb, config);
        [rgb_corr, ~]   = correct_illumination(rgb_rot, ...
            config.illumination.method, config.illumination);

        % Align to flow domain size
        if size(rgb_corr,1) ~= size(flow_domain,1) || size(rgb_corr,2) ~= size(flow_domain,2)
            rgb_corr = imresize(rgb_corr, size(flow_domain));
        end

        % Segment
        [dnapl_mask, ~, ~] = segment_DNAPL(rgb_corr, flow_domain, config);
        sol.masks{t} = dnapl_mask;

        % Saturation
        sat = calculate_saturation(dnapl_mask, flow_domain, px);
        sol.saturation_vs_time(t) = sat.Sn;

        % Blob geometry
        blob = analyze_blob_geometry(dnapl_mask, px);
        sol.num_blobs_vs_time(t) = blob.num_blobs;
        sol.mean_blob_size_vs_time(t) = blob.size_distribution.mean;

        % Interface
        iface = analyze_interfaces(dnapl_mask, flow_domain, px, config);
        sol.interface_area_vs_time(t) = iface.dnapl_water_length_px;
    end

    %% Dissolution rate: dSn/dt
    dt = diff(time_vector(:));
    dt(dt == 0) = 1;  % avoid division by zero for equal time stamps
    sol.dissolution_rate = diff(sol.saturation_vs_time) ./ dt;

    %% Fit exponential decay model: Sn(t) = Sn0 * exp(-k*t)
    sol.fitted_model = struct();
    t_col = time_vector(:);
    Sn_col = sol.saturation_vs_time(:);

    if num_frames >= 3 && any(Sn_col > 0)
        try
            ft = fittype('a*exp(b*x)', 'independent', 'x');
            f = fit(t_col, Sn_col, ft, ...
                'StartPoint', [Sn_col(1), -0.1], ...
                'Lower', [0, -Inf], 'Upper', [1, 0]);
            sol.fitted_model.exponential.Sn0 = f.a;
            sol.fitted_model.exponential.k   = -f.b;
            sol.fitted_model.exponential.fit_obj = f;
        catch
            % Manual fallback: log-linear fit
            valid = Sn_col > 0;
            if sum(valid) >= 2
                p = polyfit(t_col(valid), log(Sn_col(valid)), 1);
                sol.fitted_model.exponential.k   = -p(1);
                sol.fitted_model.exponential.Sn0 = exp(p(2));
                sol.fitted_model.exponential.fit_obj = [];
            else
                sol.fitted_model.exponential.k   = NaN;
                sol.fitted_model.exponential.Sn0 = NaN;
                sol.fitted_model.exponential.fit_obj = [];
            end
        end
    else
        sol.fitted_model.exponential.k   = NaN;
        sol.fitted_model.exponential.Sn0 = NaN;
        sol.fitted_model.exponential.fit_obj = [];
    end

    %% Change detection between consecutive frames
    sol.change = struct('dissolved_px', [], 'appeared_px', [], 'net_px', []);
    for t = 2:num_frames
        dissolved  = sol.masks{t-1} &  ~sol.masks{t};
        appeared   = ~sol.masks{t-1} &  sol.masks{t};
        sol.change(t-1).dissolved_px = sum(dissolved(:));
        sol.change(t-1).appeared_px  = sum(appeared(:));
        sol.change(t-1).net_px       = sol.change(t-1).appeared_px - sol.change(t-1).dissolved_px;
    end

    %% Cumulative mass dissolved estimate
    depth = config.physical.depth;
    rho   = config.physical.dnapl_density;
    pore_vol = sum(flow_domain(:)) * px^2 * depth;  % [m^3]
    sol.mass_dissolved = (sol.saturation_vs_time(1) - sol.saturation_vs_time(end)) ...
                         * pore_vol * rho;  % [kg]

    fprintf('\n  Solubilization complete. Sn: %.3f -> %.3f (%.1f%% removed)\n', ...
        sol.saturation_vs_time(1), sol.saturation_vs_time(end), ...
        100 * (1 - sol.saturation_vs_time(end) / max(sol.saturation_vs_time(1), eps)));
end
