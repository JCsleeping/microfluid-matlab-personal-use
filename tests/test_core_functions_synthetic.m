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

function cleanup_temp_tif_fixture(fixture_dir)
    if exist(fixture_dir, 'dir')
        rmdir(fixture_dir, 's');
    end
end

function config = make_valid_test_config(fixture_dir, tif_path)
    config = derive_config_pipeline_defaults(tif_path);
    config.data_path = fixture_dir;
    config.multipage_tif_path = {tif_path};
    config.output_path = fullfile(fixture_dir, 'output');
end

function config = derive_config_pipeline_defaults(tif_path)
    shadow_dir = tempname(tempdir);
    mkdir(shadow_dir);
    bootstrap_query = get_config_pipeline_bootstrap_query();
    write_dir_shadow(shadow_dir, bootstrap_query, tif_path);
    warning_state = warning('query', 'MATLAB:dispatcher:nameConflict');
    warning('off', 'MATLAB:dispatcher:nameConflict');
    addpath(shadow_dir, '-begin');
    clear('dir');
    rehash();
    cleanup = onCleanup(@() restore_shadow_environment(shadow_dir, warning_state)); %#ok<NASGU>

    config = config_pipeline();
end

function bootstrap_query = get_config_pipeline_bootstrap_query()
    pipeline_source = fileread(which('config_pipeline'));
    tokens = regexp(pipeline_source, "config\.data_path\s*=\s*'((?:''|[^'])*)';", 'tokens', 'once');
    assert(~isempty(tokens), 'test_fixture:parseFailure', ...
        'Failed to derive default data_path from config_pipeline.m.');
    default_data_path = strrep(tokens{1}, '''''', '''');
    bootstrap_query = fullfile(default_data_path, '*.tif');
end

function write_dir_shadow(shadow_dir, bootstrap_query, tif_path)
    shadow_file = fullfile(shadow_dir, 'dir.m');
    fid = fopen(shadow_file, 'w');
    assert(fid ~= -1, 'test_fixture:fileIO', 'Failed to create dir shadow helper.');
    file_cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>

    fprintf(fid, 'function listing = dir(query)\n');
    fprintf(fid, 'if nargin == 1 && (ischar(query) || isstring(query))\n');
    fprintf(fid, '    query = char(query);\n');
    fprintf(fid, '    if strcmp(query, ''%s'')\n', escape_for_matlab_string(bootstrap_query));
    fprintf(fid, '        info = builtin(''dir'', ''%s'');\n', escape_for_matlab_string(tif_path));
    fprintf(fid, '        listing = info;\n');
    fprintf(fid, '        return;\n');
    fprintf(fid, '    end\n');
    fprintf(fid, 'end\n');
    fprintf(fid, 'if nargin == 0\n');
    fprintf(fid, '    listing = builtin(''dir'');\n');
    fprintf(fid, 'else\n');
    fprintf(fid, '    listing = builtin(''dir'', query);\n');
    fprintf(fid, 'end\n');
    fprintf(fid, 'end\n');
end

function escaped = escape_for_matlab_string(value)
    escaped = strrep(value, '''', '''''');
end

function restore_shadow_environment(shadow_dir, warning_state)
    if exist(shadow_dir, 'dir')
        rmpath(shadow_dir);
    end
    clear('dir');
    rehash();

    if exist(shadow_dir, 'dir')
        rmdir(shadow_dir, 's');
    end

    warning(warning_state.state, 'MATLAB:dispatcher:nameConflict');
end
