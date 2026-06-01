function [dnapl_mask, confidence_map, seg_info] = segment_DNAPL(ref_image, flow_domain, config)
% SEGMENT_DNAPL  Segment DNAPL (pink/red) pixels from a reference image.
%
%   [dnapl_mask, confidence_map, seg_info] = segment_DNAPL(ref_image, flow_domain, config)
%
%   Uses Lab color space: the a* channel separates pink/red DNAPL from
%   white/gray water-filled pores. A 2-component GMM classifies pore
%   pixels into DNAPL and water clusters.
%
%   Inputs:
%       ref_image   - M x N x 3 uint8 preprocessed RGB image
%       flow_domain - M x N logical pore-space mask (1 = pore)
%       config      - Pipeline configuration struct
%
%   Outputs:
%       dnapl_mask     - M x N logical (1 = DNAPL, 0 = else)
%       confidence_map - M x N double, posterior probability of DNAPL [0,1]
%       seg_info       - Struct with segmentation diagnostics:
%                          .method, .threshold, .color_channel, .gmm_model

    method       = config.segmentation.method;
    min_area     = config.segmentation.min_blob_area;
    morph_radius = config.segmentation.morph_radius;

    %% Step 1: Color space conversion
    lab_image = rgb2lab(im2double(ref_image));
    a_channel = lab_image(:,:,2);   % red-green axis (pink DNAPL → positive a*)
    b_channel = lab_image(:,:,3);   % yellow-blue axis

    seg_info.color_channel = a_channel;
    seg_info.method = method;
    seg_info.gmm_model = [];
    seg_info.threshold = NaN;
    seg_info.input_is_linear_rgb = false;
    if isfield(config, 'input') && isfield(config.input, 'is_linear_rgb')
        seg_info.input_is_linear_rgb = logical(config.input.is_linear_rgb);
    end
    seg_info.rgb_encoding_for_segmentation = "srgb";

    %% Step 2: Extract pore-only pixels
    pore_idx = find(flow_domain);
    pore_a = a_channel(pore_idx);
    pore_b = b_channel(pore_idx);

    %% Step 3: Classification
    confidence_map = zeros(size(flow_domain));

    % Check for locked threshold (from time-series processing)
    if isfield(config.segmentation, 'fixed_threshold') && ...
            ~isnan(config.segmentation.fixed_threshold)
        % Use the locked threshold — no GMM/Otsu fitting, no flipping risk
        thresh = config.segmentation.fixed_threshold;
        [dnapl_pore, conf_pore] = segment_fixed_threshold(pore_a, thresh);
        seg_info.threshold = thresh;
        seg_info.method = [method ' (locked)'];

    else
    switch lower(method)
        case 'gmm'
            [dnapl_pore, conf_pore, gmm_model, thresh] = ...
                segment_gmm(pore_a, pore_b, config.segmentation.num_components);
            seg_info.gmm_model = gmm_model;
            seg_info.threshold = thresh;

        case 'otsu'
            [dnapl_pore, conf_pore, thresh] = segment_otsu(pore_a);
            seg_info.threshold = thresh;

        case 'adaptive'
            [dnapl_pore, conf_pore, thresh] = segment_adaptive(a_channel, flow_domain);
            seg_info.threshold = thresh;

        otherwise
            error('segment_DNAPL:badMethod', 'Unknown segmentation method "%s".', method);
    end
    end  % end if fixed_threshold

    %% Step 4: Build full-size mask
    dnapl_mask = false(size(flow_domain));
    dnapl_mask(pore_idx(dnapl_pore)) = true;
    confidence_map(pore_idx) = conf_pore;

    %% Step 5: Morphological cleanup
    dnapl_mask = refine_mask(dnapl_mask, morph_radius, min_area);

    %% Step 6: Enforce pore-space constraint
    dnapl_mask = dnapl_mask & flow_domain;

    fprintf('  DNAPL segmented (%s): %d pixels (Sn = %.3f)\n', ...
        method, sum(dnapl_mask(:)), sum(dnapl_mask(:)) / max(sum(flow_domain(:)), 1));
end


%% ========================================================================
%  GMM-based segmentation (primary method)
%  ========================================================================
function [is_dnapl, conf, gmm_model, thresh] = segment_gmm(pore_a, pore_b, n_comp)
    features = pore_a(:);  % use a* channel only for robustness

    % Sub-sample if too many pixels (speed)
    max_samples = 50000;
    if numel(features) > max_samples
        rng(42);
        sample_idx = randperm(numel(features), max_samples);
        features_sample = features(sample_idx);
    else
        features_sample = features;
    end

    % Fit GMM
    try
        gmm_model = fitgmdist(features_sample, n_comp, ...
            'RegularizationValue', 0.01, ...
            'Options', statset('MaxIter', 200));
    catch
        warning('segment_DNAPL:gmmFailed', 'GMM fit failed. Falling back to Otsu.');
        [is_dnapl, conf, thresh] = segment_otsu(pore_a);
        gmm_model = [];
        return;
    end

    % Classify all pore pixels
    [cluster_idx, ~, posterior] = cluster(gmm_model, features);

    % Identify DNAPL cluster (higher a* mean = more pink/red)
    cluster_means = gmm_model.mu;
    [~, dnapl_cluster] = max(cluster_means);

    is_dnapl = (cluster_idx == dnapl_cluster);
    conf = posterior(:, dnapl_cluster);

    % Approximate threshold (intersection of two Gaussians)
    thresh = mean(cluster_means);
end


%% ========================================================================
%  Otsu thresholding on a* channel (fallback)
%  ========================================================================
function [is_dnapl, conf, thresh] = segment_otsu(pore_a)
    % Normalize a* to [0,1] for graythresh
    a_min = min(pore_a);
    a_max = max(pore_a);
    a_norm = (pore_a - a_min) / (a_max - a_min + eps);

    thresh_norm = graythresh(a_norm);
    thresh = thresh_norm * (a_max - a_min) + a_min;

    is_dnapl = pore_a > thresh;

    % Simple confidence: distance from threshold normalized
    conf = (pore_a - thresh) / (a_max - thresh + eps);
    conf = max(min(conf, 1), 0);
end


%% ========================================================================
%  Adaptive thresholding on a* channel
%  ========================================================================
function [is_dnapl, conf, thresh] = segment_adaptive(a_channel, flow_domain)
    % Adaptive threshold on the a* channel image
    a_uint8 = im2uint8(mat2gray(a_channel));
    T = adaptthresh(a_uint8, 0.5, 'NeighborhoodSize', [51 51]);
    bw = imbinarize(a_uint8, T);

    pore_idx = find(flow_domain);
    is_dnapl = bw(pore_idx);

    % Confidence from distance to local threshold
    conf = double(is_dnapl);
    thresh = NaN;  % spatially varying
end


%% ========================================================================
%  Fixed threshold segmentation (for locked-threshold mode)
%  ========================================================================
function [is_dnapl, conf] = segment_fixed_threshold(pore_a, thresh)
    is_dnapl = pore_a > thresh;

    a_max = max(pore_a);
    conf = (pore_a - thresh) / (a_max - thresh + eps);
    conf = max(min(conf, 1), 0);
end
