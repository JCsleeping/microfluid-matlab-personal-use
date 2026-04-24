function tests = test_core_functions_synthetic
% TEST_CORE_FUNCTIONS_SYNTHETIC  Unit tests using synthetic data.
%   No real experimental data required. Tests core analysis functions
%   with programmatically generated inputs.
%
%   Run with:  runtests('test_core_functions_synthetic')

    tests = functiontests(localfunctions);
end


%% ========== validate_config ==========

function test_validate_config_accepts_valid_defaults(testCase)
    setup_path();
    [fixture_dir, tif_path] = create_temp_tif_fixture();
    cleanup = onCleanup(@() cleanup_temp_tif_fixture(fixture_dir)); %#ok<NASGU>
    config = make_valid_test_config(fixture_dir, tif_path);
    config = validate_config(config);
    verifyTrue(testCase, isstruct(config));
end

function test_validate_config_accepts_residual_metric_defaults(testCase)
    setup_path();
    [fixture_dir, tif_path] = create_temp_tif_fixture();
    cleanup = onCleanup(@() cleanup_temp_tif_fixture(fixture_dir)); %#ok<NASGU>
    config = make_valid_test_config(fixture_dir, tif_path);

    verifyFalse(testCase, config.output.save_blob_detail);
    verifyEqual(testCase, config.architecture.pool_like.max_blob_fraction_min, 0.50);
    verifyEqual(testCase, config.architecture.pool_like.num_blobs_max, 10);
    verifyEqual(testCase, config.architecture.pool_like.a_i_2D_max, 3.0e4);
    verifyEqual(testCase, config.architecture.ganglia_rich.max_blob_fraction_max, 0.30);
    verifyEqual(testCase, config.architecture.ganglia_rich.num_blobs_min, 25);
    verifyEqual(testCase, config.architecture.ganglia_rich.a_i_2D_min, 6.0e4);

    config = validate_config(config);
    verifyTrue(testCase, isstruct(config));
end

function test_config_pipeline_scans_overridden_data_path(testCase)
    setup_path();
    [fixture_dir, tif_path] = create_temp_tif_fixture();
    cleanup = onCleanup(@() cleanup_temp_tif_fixture(fixture_dir)); %#ok<NASGU>

    config = config_pipeline('data_path', fixture_dir);

    verifyEqual(testCase, config.data_path, fixture_dir);
    verifyEqual(testCase, config.multipage_tif_path, {tif_path});
    verifyEqual(testCase, fileparts(config.output_path), fixture_dir);
end

function test_config_pipeline_sorts_scanned_tifs_by_datenum(testCase)
    setup_path();
    [fixture_dir, older_tif, newer_tif] = create_ordered_tif_fixture();
    cleanup = onCleanup(@() cleanup_temp_tif_fixture(fixture_dir)); %#ok<NASGU>

    config = config_pipeline('data_path', fixture_dir);

    verifyEqual(testCase, config.multipage_tif_path(:)', {older_tif, newer_tif});
end

function test_config_pipeline_default_scan_smoke_if_data_exists(testCase)
    setup_path();
    default_data_path = get_config_pipeline_default_data_path();
    assumeTrue(testCase, exist(default_data_path, 'dir') == 7);
    assumeFalse(testCase, isempty(dir(fullfile(default_data_path, '*.tif'))));

    config = config_pipeline();
    datenums = cellfun(@(p) dir(p).datenum, config.multipage_tif_path);

    verifyFalse(testCase, isempty(config.multipage_tif_path));
    verifyTrue(testCase, issorted(datenums(:)));
end

function test_config_pipeline_preserves_supplied_multipage_tif_path(testCase)
    setup_path();
    [fixture_dir, tif_path] = create_temp_tif_fixture();
    cleanup = onCleanup(@() cleanup_temp_tif_fixture(fixture_dir)); %#ok<NASGU>
    missing_dir = tempname(tempdir);

    config = config_pipeline( ...
        'data_path', missing_dir, ...
        'multipage_tif_path', {tif_path});

    verifyEqual(testCase, config.data_path, missing_dir);
    verifyEqual(testCase, config.multipage_tif_path, {tif_path});
    verifyEqual(testCase, fileparts(config.output_path), missing_dir);
end

function test_config_pipeline_preserves_explicit_output_path(testCase)
    setup_path();
    [fixture_dir, tif_path] = create_temp_tif_fixture();
    cleanup = onCleanup(@() cleanup_temp_tif_fixture(fixture_dir)); %#ok<NASGU>
    explicit_output_path = tempname(tempdir);

    config = config_pipeline( ...
        'data_path', fixture_dir, ...
        'output_path', explicit_output_path);

    verifyEqual(testCase, config.multipage_tif_path, {tif_path});
    verifyEqual(testCase, config.output_path, explicit_output_path);
end

function test_validate_config_rejects_blob_detail_with_parallel(testCase)
    setup_path();
    [fixture_dir, tif_path] = create_temp_tif_fixture();
    cleanup = onCleanup(@() cleanup_temp_tif_fixture(fixture_dir)); %#ok<NASGU>
    config = make_valid_test_config(fixture_dir, tif_path);
    config.output.save_blob_detail = true;
    config.parallel.enabled = true;

    verifyError(testCase, ...
        @() validate_config(config), ...
        'validate_config:badParam');
end

function test_validate_config_rejects_crossed_architecture_thresholds(testCase)
    setup_path();
    [fixture_dir, tif_path] = create_temp_tif_fixture();
    cleanup = onCleanup(@() cleanup_temp_tif_fixture(fixture_dir)); %#ok<NASGU>
    config = make_valid_test_config(fixture_dir, tif_path);
    config.architecture.pool_like.max_blob_fraction_min = ...
        config.architecture.ganglia_rich.max_blob_fraction_max;

    verifyError(testCase, ...
        @() validate_config(config), ...
        'validate_config:badParam');

    config = make_valid_test_config(fixture_dir, tif_path);
    config.architecture.pool_like.a_i_2D_max = ...
        config.architecture.ganglia_rich.a_i_2D_min;

    verifyError(testCase, ...
        @() validate_config(config), ...
        'validate_config:badParam');
end

function test_validate_config_rejects_out_of_range_architecture_fraction(testCase)
    setup_path();
    [fixture_dir, tif_path] = create_temp_tif_fixture();
    cleanup = onCleanup(@() cleanup_temp_tif_fixture(fixture_dir)); %#ok<NASGU>
    config = make_valid_test_config(fixture_dir, tif_path);
    config.architecture.pool_like.max_blob_fraction_min = 1.25;

    verifyError(testCase, ...
        @() validate_config(config), ...
        'validate_config:badParam');
end

function test_validate_config_rejects_invalid_architecture_blob_counts(testCase)
    setup_path();
    [fixture_dir, tif_path] = create_temp_tif_fixture();
    cleanup = onCleanup(@() cleanup_temp_tif_fixture(fixture_dir)); %#ok<NASGU>
    config = make_valid_test_config(fixture_dir, tif_path);
    config.architecture.pool_like.num_blobs_max = 2.5;

    verifyError(testCase, ...
        @() validate_config(config), ...
        'validate_config:badParam');

    config = make_valid_test_config(fixture_dir, tif_path);
    config.architecture.ganglia_rich.num_blobs_min = inf;

    verifyError(testCase, ...
        @() validate_config(config), ...
        'validate_config:badParam');
end

function test_validate_config_rejects_negative_pixel_size(testCase)
    setup_path();
    [fixture_dir, tif_path] = create_temp_tif_fixture();
    cleanup = onCleanup(@() cleanup_temp_tif_fixture(fixture_dir)); %#ok<NASGU>
    config = make_valid_test_config(fixture_dir, tif_path);
    config.physical.pixel_size = -1;
    verifyError(testCase, ...
        @() validate_config(config), ...
        'validate_config:badParam');
end

function test_validate_config_rejects_zero_pixel_size(testCase)
    setup_path();
    [fixture_dir, tif_path] = create_temp_tif_fixture();
    cleanup = onCleanup(@() cleanup_temp_tif_fixture(fixture_dir)); %#ok<NASGU>
    config = make_valid_test_config(fixture_dir, tif_path);
    config.physical.pixel_size = 0;
    verifyError(testCase, ...
        @() validate_config(config), ...
        'validate_config:badParam');
end

function test_validate_config_rejects_negative_morph_radius(testCase)
    setup_path();
    [fixture_dir, tif_path] = create_temp_tif_fixture();
    cleanup = onCleanup(@() cleanup_temp_tif_fixture(fixture_dir)); %#ok<NASGU>
    config = make_valid_test_config(fixture_dir, tif_path);
    config.segmentation.morph_radius = -1;
    verifyError(testCase, ...
        @() validate_config(config), ...
        'validate_config:badParam');
end

function test_validate_config_rejects_zero_min_blob_area(testCase)
    setup_path();
    [fixture_dir, tif_path] = create_temp_tif_fixture();
    cleanup = onCleanup(@() cleanup_temp_tif_fixture(fixture_dir)); %#ok<NASGU>
    config = make_valid_test_config(fixture_dir, tif_path);
    config.segmentation.min_blob_area = 0;
    verifyError(testCase, ...
        @() validate_config(config), ...
        'validate_config:badParam');
end

function test_validate_config_rejects_bad_input_mode(testCase)
    setup_path();
    [fixture_dir, tif_path] = create_temp_tif_fixture();
    cleanup = onCleanup(@() cleanup_temp_tif_fixture(fixture_dir)); %#ok<NASGU>
    config = make_valid_test_config(fixture_dir, tif_path);
    config.input_mode = 'invalid';
    verifyError(testCase, ...
        @() validate_config(config), ...
        'validate_config:badParam');
end

function test_validate_config_rejects_fractional_pages(testCase)
    setup_path();
    [fixture_dir, tif_path] = create_temp_tif_fixture();
    cleanup = onCleanup(@() cleanup_temp_tif_fixture(fixture_dir)); %#ok<NASGU>
    config = make_valid_test_config(fixture_dir, tif_path);
    config.pages = [1, 2.5, 3];
    verifyError(testCase, ...
        @() validate_config(config), ...
        'validate_config:badParam');
end


%% ========== calculate_saturation ==========

function test_saturation_full_dnapl(testCase)
    setup_path();
    flow_domain = true(100, 100);
    dnapl_mask = true(100, 100);
    sat = calculate_saturation(dnapl_mask, flow_domain, 1e-6);
    verifyEqual(testCase, sat.Sn, 1.0, 'AbsTol', 1e-10);
    verifyEqual(testCase, sat.Sw, 0.0, 'AbsTol', 1e-10);
end

function test_saturation_no_dnapl(testCase)
    setup_path();
    flow_domain = true(100, 100);
    dnapl_mask = false(100, 100);
    sat = calculate_saturation(dnapl_mask, flow_domain, 1e-6);
    verifyEqual(testCase, sat.Sn, 0.0, 'AbsTol', 1e-10);
    verifyEqual(testCase, sat.Sw, 1.0, 'AbsTol', 1e-10);
end

function test_saturation_half_filled(testCase)
    setup_path();
    flow_domain = true(100, 100);
    dnapl_mask = false(100, 100);
    dnapl_mask(1:50, :) = true;
    sat = calculate_saturation(dnapl_mask, flow_domain, 1e-6);
    verifyEqual(testCase, sat.Sn, 0.5, 'AbsTol', 1e-10);
end

function test_saturation_respects_flow_domain(testCase)
    setup_path();
    flow_domain = false(100, 100);
    flow_domain(1:50, :) = true;
    dnapl_mask = true(100, 100);
    sat = calculate_saturation(dnapl_mask, flow_domain, 1e-6);
    % DNAPL outside flow domain should not count; Sn = 1.0 within pore
    verifyEqual(testCase, sat.Sn, 1.0, 'AbsTol', 1e-10);
    verifyEqual(testCase, sat.dnapl_area_px, 5000);
end


%% ========== refine_mask ==========

function test_refine_mask_removes_small_blobs(testCase)
    setup_path();
    mask = false(100, 100);
    mask(10, 10) = true;           % 1-pixel blob (below min_blob_area=10)
    mask(50:60, 50:60) = true;     % 121-pixel blob
    cleaned = refine_mask(mask, 2, 10);
    % Small blob should be removed; large blob should remain (possibly modified)
    verifyGreaterThan(testCase, sum(cleaned(:)), 0);
    verifyEqual(testCase, cleaned(10, 10), false);
end

function test_refine_mask_zero_radius(testCase)
    setup_path();
    mask = true(50, 50);
    cleaned = refine_mask(mask, 0, 1);
    verifyEqual(testCase, sum(cleaned(:)), 2500);
end


%% ========== analyze_blob_geometry ==========

function test_blob_geometry_empty_mask(testCase)
    setup_path();
    mask = false(100, 100);
    blob = analyze_blob_geometry(mask, 1e-6);
    verifyEqual(testCase, blob.num_blobs, 0);
    verifyTrue(testCase, isempty(blob.props));
    verifyEqual(testCase, blob.size_distribution.total, 0);
    verifyEqual(testCase, blob.max_blob_fraction, 0);
    verifyEqual(testCase, blob.Req_distribution.mean, 0);
    verifyEqual(testCase, blob.Req_distribution.median, 0);
    verifyEqual(testCase, blob.Req_distribution.std, 0);
    verifyEqual(testCase, blob.Req_distribution.p10, 0);
    verifyEqual(testCase, blob.Req_distribution.p25, 0);
    verifyEqual(testCase, blob.Req_distribution.p75, 0);
    verifyEqual(testCase, blob.Req_distribution.p90, 0);
    verifyEqual(testCase, blob.topology_summary.n_droplets, 0);
    verifyEqual(testCase, blob.topology_summary.n_columns, 0);
    verifyEqual(testCase, blob.topology_summary.n_clusters, 0);
    verifyEqual(testCase, blob.topology_summary.frac_droplets, 0);
    verifyEqual(testCase, blob.topology_summary.frac_columns, 0);
    verifyEqual(testCase, blob.topology_summary.frac_clusters, 0);
end

function test_blob_geometry_single_blob(testCase)
    setup_path();
    mask = false(100, 100);
    mask(40:60, 40:60) = true;  % 21x21 square blob = 441 px
    blob = analyze_blob_geometry(mask, 1e-6);
    verifyEqual(testCase, blob.num_blobs, 1);
    verifyEqual(testCase, blob.props(1).Area, 441);
    verifyGreaterThan(testCase, blob.props(1).Area_m2, 0);
end

function test_blob_geometry_ganglia_with_pixel_size(testCase)
    setup_path();
    % pixel_size = 1e-6 m/px → 1 px = 1 um^2
    % singlet < 50 um^2, ganglion < 5000 um^2
    mask = false(200, 200);
    % Small blob: 3x3 = 9 px = 9 um^2 → singlet
    mask(10:12, 10:12) = true;
    % Medium blob: 30x30 = 900 px = 900 um^2 → ganglion
    mask(50:79, 50:79) = true;
    % Large blob: 80x80 = 6400 px = 6400 um^2 → pool
    mask(100:179, 100:179) = true;

    blob = analyze_blob_geometry(mask, 1e-6);
    types = [blob.props.GangliaType];
    verifyTrue(testCase, any(types == "singlet"));
    verifyTrue(testCase, any(types == "ganglion"));
    verifyTrue(testCase, any(types == "pool"));
end

function test_blob_geometry_ganglia_without_pixel_size(testCase)
    setup_path();
    % Without pixel_size, uses legacy pixel thresholds (50, 500)
    mask = false(200, 200);
    mask(10, 10) = true;           % 1 px → singlet
    mask(50:59, 50:59) = true;     % 100 px → ganglion
    mask(100:179, 100:179) = true; % 6400 px → pool

    blob = analyze_blob_geometry(mask, []);
    types = [blob.props.GangliaType];
    verifyTrue(testCase, any(types == "singlet"));
    verifyTrue(testCase, any(types == "ganglion"));
    verifyTrue(testCase, any(types == "pool"));
end


function test_blob_geometry_reports_topology_and_req_statistics(testCase)
    setup_path();
    mask = false(120, 120);
    expected_areas = [49, 93, 176];
    expected_radii = sort(sqrt(expected_areas / pi));
    total_area = sum(expected_areas);

    mask(10:16, 10:16) = true;
    mask(20:22, 40:70) = true;
    mask(60:74, 80:94) = true;
    mask(64:70, 84:90) = false;

    blob = analyze_blob_geometry(mask, 2e-6);
    topology_types = string({blob.props.TopologyType});

    verifyEqual(testCase, blob.num_blobs, 3);
    verifyTrue(testCase, all(ismember(["EulerNumber", "EquivRadius", "TopologyType"], ...
        string(blob.blob_table.Properties.VariableNames))));
    verifyTrue(testCase, any(topology_types == "droplet"));
    verifyTrue(testCase, any(topology_types == "column"));
    verifyTrue(testCase, any(topology_types == "cluster"));
    verifyEqual(testCase, blob.max_blob_fraction, max(expected_areas) / total_area, ...
        'AbsTol', 1e-12);
    verifyEqual(testCase, blob.Req_distribution.mean, mean(expected_radii), ...
        'AbsTol', 1e-12);
    verifyEqual(testCase, blob.Req_distribution.median, median(expected_radii), ...
        'AbsTol', 1e-12);
    verifyEqual(testCase, blob.Req_distribution.std, std(expected_radii), ...
        'AbsTol', 1e-12);
    verifyEqual(testCase, blob.Req_distribution.p10, ...
        local_percentile(expected_radii, 10), 'AbsTol', 1e-12);
    verifyEqual(testCase, blob.Req_distribution.p25, ...
        local_percentile(expected_radii, 25), 'AbsTol', 1e-12);
    verifyEqual(testCase, blob.Req_distribution.p75, ...
        local_percentile(expected_radii, 75), 'AbsTol', 1e-12);
    verifyEqual(testCase, blob.Req_distribution.p90, ...
        local_percentile(expected_radii, 90), 'AbsTol', 1e-12);
    verifyEqual(testCase, blob.topology_summary.n_droplets, 1);
    verifyEqual(testCase, blob.topology_summary.n_columns, 1);
    verifyEqual(testCase, blob.topology_summary.n_clusters, 1);
    verifyEqual(testCase, blob.topology_summary.frac_droplets, expected_areas(1) / total_area, ...
        'AbsTol', 1e-12);
    verifyEqual(testCase, blob.topology_summary.frac_columns, expected_areas(2) / total_area, ...
        'AbsTol', 1e-12);
    verifyEqual(testCase, blob.topology_summary.frac_clusters, expected_areas(3) / total_area, ...
        'AbsTol', 1e-12);
    verifyEqual(testCase, blob.topology_summary.frac_droplets + ...
        blob.topology_summary.frac_columns + blob.topology_summary.frac_clusters, ...
        1, 'AbsTol', 1e-10);
end


%% ========== analyze_interfaces ==========

function test_analyze_interfaces_reports_ai_2d(testCase)
    setup_path();
    flow_domain = true(20, 20);
    dnapl_mask = false(20, 20);
    dnapl_mask(6:9, 7:10) = true;
    pixel_size = 2e-6;
    expected_water_length_px = 12;
    expected_dnapl_area_px = 16;
    expected_ai_2d = (expected_water_length_px * pixel_size) / ...
        (expected_dnapl_area_px * pixel_size^2);

    iface = analyze_interfaces(dnapl_mask, flow_domain, pixel_size, struct());

    verifyEqual(testCase, iface.a_i_2D, expected_ai_2d, 'AbsTol', 1e-12);
    verifyGreaterThan(testCase, iface.a_i_2D, iface.specific_interfacial_area);
end


%% ========== Helper ==========

function setup_path()
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));
end

function [fixture_dir, tif_path] = create_temp_tif_fixture()
    fixture_dir = tempname(tempdir);
    mkdir(fixture_dir);

    rgb_image = uint8(zeros(4, 4, 3));
    rgb_image(:, :, 1) = 255;

    tif_path = fullfile(fixture_dir, 'fixture.tif');
    imwrite(rgb_image, tif_path);
end

function [fixture_dir, older_tif, newer_tif] = create_ordered_tif_fixture()
    fixture_dir = tempname(tempdir);
    mkdir(fixture_dir);

    rgb_image = uint8(zeros(4, 4, 3));
    rgb_image(:, :, 1) = 255;

    older_tif = fullfile(fixture_dir, 'z_older_by_time.tif');
    newer_tif = fullfile(fixture_dir, 'a_newer_by_time.tif');

    imwrite(rgb_image, older_tif);
    pause(1.1);
    imwrite(rgb_image, newer_tif);
end

function cleanup_temp_tif_fixture(fixture_dir)
    if exist(fixture_dir, 'dir')
        rmdir(fixture_dir, 's');
    end
end

function config = make_valid_test_config(fixture_dir, tif_path)
    config = config_pipeline( ...
        'data_path', fixture_dir, ...
        'multipage_tif_path', {tif_path}, ...
        'output_path', fullfile(fixture_dir, 'output'));
end

function default_data_path = get_config_pipeline_default_data_path()
    pipeline_source = fileread(which('config_pipeline'));
    tokens = regexp(pipeline_source, "config\.data_path\s*=\s*'((?:''|[^'])*)';", 'tokens', 'once');
    assert(~isempty(tokens), 'test_fixture:parseFailure', ...
        'Failed to derive default data_path from config_pipeline.m.');
    default_data_path = strrep(tokens{1}, '''''', '''');
end

function value = local_percentile(values, percentile)
    values = sort(values(:));
    n = numel(values);

    if n == 0
        value = 0;
        return;
    end

    if n == 1
        value = values(1);
        return;
    end

    position = 1 + (n - 1) * (percentile / 100);
    lower_idx = floor(position);
    upper_idx = ceil(position);

    if lower_idx == upper_idx
        value = values(lower_idx);
        return;
    end

    weight = position - lower_idx;
    value = values(lower_idx) + weight * (values(upper_idx) - values(lower_idx));
end
