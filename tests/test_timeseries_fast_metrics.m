function tests = test_timeseries_fast_metrics
% Regression tests for Step-4 lightweight timeseries metrics.
    tests = functiontests(localfunctions);
end


function test_fast_blob_metrics_match_full_analysis(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    mask = false(16, 16);
    mask(2:4, 2:5) = true;
    mask(8:10, 7:9) = true;
    mask(12, 13) = true;

    full_blob = analyze_blob_geometry(mask, 3.92e-6);
    [num_blobs, mean_blob_size] = compute_timeseries_blob_metrics(mask);

    verifyEqual(testCase, num_blobs, full_blob.num_blobs);
    verifyEqual(testCase, mean_blob_size, full_blob.size_distribution.mean, 'AbsTol', 1e-12);
end


function test_fast_interface_length_matches_full_analysis(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    flow_domain = true(24, 24);
    flow_domain(:, 1:2) = false;
    flow_domain(1:2, :) = false;

    mask = false(24, 24);
    mask(4:8, 4:9) = true;
    mask(10:14, 2:6) = true; % touches the solid wall/contact zone

    config = struct('interface', struct('solid_dilation', 1));
    full_iface = analyze_interfaces(mask, flow_domain, 3.92e-6, config);

    solid_contact_zone = build_solid_contact_zone(flow_domain, config);
    dnapl_water_length_px = compute_timeseries_interface_length(mask, solid_contact_zone);

    verifyEqual(testCase, dnapl_water_length_px, full_iface.dnapl_water_length_px, 'AbsTol', 1e-12);
end


function test_fast_blob_metrics_handle_empty_mask(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    mask = false(12, 12);
    [num_blobs, mean_blob_size] = compute_timeseries_blob_metrics(mask);

    verifyEqual(testCase, num_blobs, 0);
    verifyEqual(testCase, mean_blob_size, 0);
end
