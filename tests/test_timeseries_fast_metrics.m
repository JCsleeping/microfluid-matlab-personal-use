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

    full_blob = analyze_blob_geometry(mask, []);
    [metrics, blob_table] = compute_timeseries_blob_metrics(mask);

    verifyEqual(testCase, metrics.num_blobs, full_blob.num_blobs);
    verifyEqual(testCase, metrics.mean_blob_size, full_blob.size_distribution.mean, 'AbsTol', 1e-12);
    verifyEqual(testCase, metrics.max_blob_frac, full_blob.max_blob_fraction, 'AbsTol', 1e-12);
    verifyEqual(testCase, metrics.Req_median, full_blob.Req_distribution.median, 'AbsTol', 1e-12);
    verifyEqual(testCase, blob_table, full_blob.blob_table);
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


function test_characterize_ai_2d_uses_physical_pixel_size(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    fixture_dir = fullfile(tempdir, ['dnapl_ai2d_units_' datestr(now, 'yyyymmdd_HHMMSSFFF')]);
    mkdir(fixture_dir);
    cleanup = onCleanup(@() cleanup_tempdir(fixture_dir)); %#ok<NASGU>

    flow_domain = true(24, 24);
    flow_domain(:, 1:2) = false;
    flow_domain(1:2, :) = false;

    mask = false(24, 24);
    mask(5:10, 5:12) = true;
    mask(14:18, 9:13) = true;

    tif_path = fullfile(fixture_dir, 'frame_01.tif');
    imwrite(render_mask_frame(mask), tif_path);
    frame_index = struct('tif_path', tif_path, 'page', 1);

    px = 3.92e-6;
    config = make_step4_ai2d_config(fixture_dir, size(flow_domain), px);
    sol = characterize_solubilization_v2(frame_index, flow_domain, 0, config);

    expected_iface = analyze_interfaces(mask, flow_domain, px, config);

    verifyEqual(testCase, sol.masks{1}, mask);
    verifyEqual(testCase, sol.a_i_2D_vs_time(1), expected_iface.a_i_2D, 'RelTol', 1e-12);
end


function test_fast_blob_metrics_handle_empty_mask(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    mask = false(12, 12);
    [metrics, blob_table] = compute_timeseries_blob_metrics(mask);

    verifyEqual(testCase, metrics.num_blobs, 0);
    verifyEqual(testCase, metrics.mean_blob_size, 0);
    verifyEqual(testCase, metrics.max_blob_frac, 0);
    verifyEqual(testCase, metrics.Req_median, 0);
    verifyTrue(testCase, isempty(blob_table));
end


function rgb = render_mask_frame(mask)
    rgb = uint8(235 * ones([size(mask), 3]));
    rgb(:, :, 2) = uint8(230);
    rgb(:, :, 3) = uint8(230);

    red_channel = rgb(:, :, 1);
    green_channel = rgb(:, :, 2);
    blue_channel = rgb(:, :, 3);

    red_channel(mask) = 220;
    green_channel(mask) = 40;
    blue_channel(mask) = 60;

    rgb(:, :, 1) = red_channel;
    rgb(:, :, 2) = green_channel;
    rgb(:, :, 3) = blue_channel;
end


function config = make_step4_ai2d_config(output_dir, image_size, px)
    config = struct();
    config.segmentation = struct( ...
        'method', 'otsu', ...
        'fixed_threshold', 10, ...
        'min_blob_area', 1, ...
        'morph_radius', 0, ...
        'num_components', 2);
    config.physical = struct( ...
        'pixel_size', px, ...
        'depth', 1.0, ...
        'dnapl_density', 1.0);
    config.parallel = struct( ...
        'enabled', false, ...
        'use_gpu', false, ...
        'num_workers', 1);
    config.illumination = struct( ...
        'method', 'morphological', ...
        'kernel_size', 1);
    config.registration = struct('method', 'none');
    config.preprocess = struct( ...
        'rotation_angle', 0, ...
        'manual_crop_rect', [1, 1, image_size(2) - 1, image_size(1) - 1], ...
        'saved_crop_rect', []);
    config.interface = struct('solid_dilation', 1);
    config.output = struct( ...
        'save_progress', false, ...
        'progress_interval', 1, ...
        'checkpoint', false, ...
        'save_interval', 1, ...
        'max_frames_per_session', inf, ...
        'save_blob_detail', false);
    config.output_path = output_dir;
end


function cleanup_tempdir(out_dir)
    if isfolder(out_dir)
        try
            rmdir(out_dir, 's');
        catch
            % Best effort cleanup for test output.
        end
    end
end
