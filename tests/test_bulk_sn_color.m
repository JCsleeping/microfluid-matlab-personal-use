function tests = test_bulk_sn_color
% Tests for bulk/regional color-index saturation.
    tests = functiontests(localfunctions);
end


function test_score_modes_return_finite_color_saturation(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    [water_rgb, napl_rgb, frame_rgb, flow_domain, solid_mask] = make_color_fixture();
    config = make_bulk_config();
    modes = {'normalized_red', 'excess_red', 'lab_a', 'chroma', 'lab_ab_projection'};

    for i = 1:numel(modes)
        config.bulk_sn.score_mode = modes{i};
        [sn, info] = compute_bulk_sn_color(frame_rgb, water_rgb, napl_rgb, ...
            flow_domain, solid_mask, config);

        verifySize(testCase, info.score_frame_map, size(flow_domain));
        verifyTrue(testCase, isfinite(sn), modes{i});
        verifyGreaterThanOrEqual(testCase, sn, 0, modes{i});
        verifyLessThanOrEqual(testCase, sn, 1, modes{i});
        verifyEqual(testCase, info.score_mode, string(modes{i}));
    end
end


function test_clean_water_and_full_napl_reference_endpoints(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    [water_rgb, napl_rgb, ~, flow_domain, solid_mask] = make_color_fixture();
    config = make_bulk_config();

    [sn_water, info_water] = compute_bulk_sn_color(water_rgb, water_rgb, ...
        napl_rgb, flow_domain, solid_mask, config);
    [sn_napl, info_napl] = compute_bulk_sn_color(napl_rgb, water_rgb, ...
        napl_rgb, flow_domain, solid_mask, config);

    verifyEqual(testCase, sn_water, 0, 'AbsTol', 1e-10);
    verifyEqual(testCase, sn_napl, 1, 'AbsTol', 1e-10);
    verifyEqual(testCase, info_water.reference_transfer_status, "ok");
    verifyEqual(testCase, info_napl.reference_transfer_status, "ok");
end


function test_core_flow_excludes_solid_boundary(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    [water_rgb, napl_rgb, frame_rgb, flow_domain, solid_mask] = make_color_fixture();
    config = make_bulk_config();
    config.bulk_sn.core_flow_min_dist_px = 3;

    [~, info] = compute_bulk_sn_color(frame_rgb, water_rgb, napl_rgb, ...
        flow_domain, solid_mask, config);

    expected_core = flow_domain & bwdist(solid_mask) >= 3;
    verifyEqual(testCase, info.core_flow_area_px, nnz(expected_core));
    verifyLessThan(testCase, info.core_flow_area_px, nnz(flow_domain));
    verifyGreaterThan(testCase, info.edge_excluded_fraction, 0);
end


function test_bulk_color_outputs_provisional_endpoint_provenance(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    [water_rgb, napl_rgb, frame_rgb, flow_domain, solid_mask] = make_color_fixture();
    config = make_bulk_config();
    config.bulk_sn.endpoint_status = 'provisional';
    config.bulk_sn.endpoint_source = 'high_frame_candidate_A';
    config.bulk_sn.mask_id = 'core_flow';
    config.bulk_sn.rgb_source = 'corrected_quantitative';

    [sn, info] = compute_bulk_sn_color(frame_rgb, water_rgb, napl_rgb, ...
        flow_domain, solid_mask, config);

    verifyEqual(testCase, info.endpoint_status, "provisional");
    verifyEqual(testCase, info.endpoint_source, "high_frame_candidate_A");
    verifyEqual(testCase, info.mask_id, "core_flow");
    verifyEqual(testCase, info.rgb_source, "corrected_quantitative");
    verifyEqual(testCase, double(info.S_NAPL_color_core), sn, 'AbsTol', 1e-10);
    verifyTrue(testCase, isfield(info, 'S_NAPL_color_edge'));
    verifyFalse(testCase, isfield(info, 'Sn_final'));
end


function test_mask_id_controls_measurement_mask(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    [water_rgb, napl_rgb, frame_rgb, flow_domain, solid_mask] = make_color_fixture();
    config = make_bulk_config();
    config.bulk_sn.core_flow_min_dist_px = 3;
    config.bulk_sn.mask_id = 'flow_domain';

    [~, info_flow] = compute_bulk_sn_color(frame_rgb, water_rgb, napl_rgb, ...
        flow_domain, solid_mask, config);

    config.bulk_sn.mask_id = 'core_flow';
    [~, info_core] = compute_bulk_sn_color(frame_rgb, water_rgb, napl_rgb, ...
        flow_domain, solid_mask, config);

    verifyEqual(testCase, info_flow.mask_id, "flow_domain");
    verifyEqual(testCase, info_flow.measurement_mask_area_px, nnz(flow_domain));
    verifyEqual(testCase, info_core.mask_id, "core_flow");
    verifyEqual(testCase, info_core.measurement_mask_area_px, info_core.core_flow_area_px);
    verifyGreaterThan(testCase, info_flow.measurement_mask_area_px, ...
        info_core.measurement_mask_area_px);
end


function test_winsorized_mean_resists_single_pixel_outlier(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    [water_rgb, napl_rgb, ~, flow_domain, solid_mask] = make_color_fixture(40, 40);
    frame_rgb = water_rgb;
    frame_rgb(20, 20, :) = reshape(single([1, 0, 0]), 1, 1, 3);

    config = make_bulk_config();
    config.bulk_sn.winsor_percentiles = [1 99];

    [sn, info] = compute_bulk_sn_color(frame_rgb, water_rgb, napl_rgb, ...
        flow_domain, solid_mask, config);

    verifyLessThan(testCase, sn, 0.05);
    verifyEqual(testCase, info.statistic, "winsorized_mean");
end


function test_timeseries_table_does_not_fake_missing_color_index(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    sol = struct();
    sol.saturation_vs_time = [0.9; 0.4];
    sol.num_blobs_vs_time = [2; 3];
    sol.mean_blob_size_vs_time = [10; 12];
    sol.interface_area_vs_time = [40; 44];

    T = build_solubilization_timeseries_table([0; 1], sol);

    verifyTrue(testCase, all(isnan(T.S_NAPL_color)));
    verifyTrue(testCase, all(isnan(T.S_NAPL_color_raw)));
    verifyEqual(testCase, string(T.endpoint_status), ...
        ["not_computed"; "not_computed"]);
    verifyEqual(testCase, string(T.rgb_source), [""; ""]);
end


function test_timeseries_table_exposes_color_sn_and_mask_secondary(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    sol = struct();
    sol.saturation_vs_time = [0.9; 0.4];
    sol.S_NAPL_color_raw_vs_time = [0.92; 0.38];
    sol.S_NAPL_color_vs_time = [0.9; 0.4];
    sol.Sn_mask_secondary_vs_time = [0.55; 0.12];
    sol.mask_color_abs_difference_vs_time = abs( ...
        sol.Sn_mask_secondary_vs_time - sol.S_NAPL_color_vs_time);
    sol.bulk_sn_score_mode_vs_time = ["normalized_red"; "normalized_red"];
    sol.bulk_sn_score_frame_vs_time = [0.73; 0.49];
    sol.bulk_sn_score_water_ref_vs_time = [0.33; 0.33];
    sol.bulk_sn_score_napl_ref_vs_time = [0.78; 0.78];
    sol.bulk_sn_core_flow_area_px_vs_time = [100; 100];
    sol.bulk_sn_flow_domain_area_px_vs_time = [125; 125];
    sol.bulk_sn_edge_excluded_fraction_vs_time = [0.2; 0.2];
    sol.bulk_sn_endpoint_status_vs_time = ["provisional"; "masked_audit_passed"];
    sol.bulk_sn_endpoint_source_vs_time = ["high_frame_candidate_A"; "independent_high_B"];
    sol.bulk_sn_mask_id_vs_time = ["core_flow"; "core_flow"];
    sol.bulk_sn_rgb_source_vs_time = ["corrected_quantitative"; "corrected_quantitative"];
    sol.bulk_sn_qc_status_vs_time = ["ok"; "mask_color_disagreement"];
    sol.num_blobs_vs_time = [2; 3];
    sol.mean_blob_size_vs_time = [10; 12];
    sol.interface_area_vs_time = [40; 44];
    sol.processing_scale_factor = [1; 1];
    sol.primary_branch = ["native"; "native"];
    sol.sn_semantics_version = ["v4_bulk_color_index"; "v4_bulk_color_index"];
    sol.frame_validation_status = ["not_run"; "not_run"];
    sol.object_validation_status = ["not_object_matched"; "not_object_matched"];
    sol.quantification_status = ["bulk_color_primary"; "bulk_color_primary"];

    T = build_solubilization_timeseries_table([0; 1], sol);

    verifyEqual(testCase, T.Sn, sol.S_NAPL_color_vs_time);
    verifyEqual(testCase, T.S_NAPL_color, sol.S_NAPL_color_vs_time);
    verifyEqual(testCase, T.Sn_mask_secondary, sol.Sn_mask_secondary_vs_time);
    verifyEqual(testCase, T.mask_color_abs_difference, ...
        sol.mask_color_abs_difference_vs_time);
    verifyEqual(testCase, string(T.score_mode), sol.bulk_sn_score_mode_vs_time);
    verifyEqual(testCase, string(T.endpoint_status), sol.bulk_sn_endpoint_status_vs_time);
    verifyEqual(testCase, string(T.endpoint_source), sol.bulk_sn_endpoint_source_vs_time);
    verifyEqual(testCase, string(T.mask_id), sol.bulk_sn_mask_id_vs_time);
    verifyEqual(testCase, string(T.rgb_source), sol.bulk_sn_rgb_source_vs_time);
end


function [water_rgb, napl_rgb, frame_rgb, flow_domain, solid_mask] = make_color_fixture(varargin)
    if nargin >= 2
        h = varargin{1};
        w = varargin{2};
    else
        h = 24;
        w = 24;
    end

    water_rgb = repmat(reshape(single([0.55, 0.55, 0.55]), 1, 1, 3), h, w, 1);
    napl_rgb = repmat(reshape(single([0.86, 0.12, 0.16]), 1, 1, 3), h, w, 1);
    frame_rgb = repmat(reshape(single([0.70, 0.34, 0.36]), 1, 1, 3), h, w, 1);

    solid_mask = false(h, w);
    solid_mask(:, round(w/2)) = true;
    flow_domain = ~solid_mask;
end


function config = make_bulk_config()
    config = struct();
    config.bulk_sn = struct( ...
        'enabled', true, ...
        'primary_output', true, ...
        'score_mode', 'normalized_red', ...
        'statistic', 'winsorized_mean', ...
        'winsor_percentiles', [1 99], ...
        'core_flow_min_dist_px', 2, ...
        'emit_regions', true, ...
        'n_x_bins', 4, ...
        'use_background', false, ...
        'pdf_method_reference', 'es4c11735_si_001.pdf');
    config.preprocessing = struct('rgb_encoding', 'srgb');
end
