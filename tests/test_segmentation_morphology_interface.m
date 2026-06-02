function tests = test_segmentation_morphology_interface
% TEST_SEGMENTATION_MORPHOLOGY_INTERFACE  C2 interface/contact CSV contract.
    tests = functiontests(localfunctions);
end


function test_morphology_outputs_interface_contact_columns(testCase)
    repo_root = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(repo_root));
    cache_dir = fullfile(tempdir, ['segmorph_iface_cache_' char(java.util.UUID.randomUUID)]);
    out_dir = fullfile(tempdir, ['segmorph_iface_out_' char(java.util.UUID.randomUUID)]);
    mkdir(cache_dir);
    mkdir(out_dir);
    cleanup = onCleanup(@() cleanup_dirs({cache_dir, out_dir}));

    h = 10;
    w = 12;
    flow_domain = true(h, w);
    flow_domain(1:2, :) = false;
    frame_path = fullfile(cache_dir, 'frame_001.h5');
    mask_path = fullfile(cache_dir, 'mask_crop.h5');
    write_test_frame(frame_path, h, w);
    write_test_mask(mask_path, flow_domain);
    write_test_manifest(fullfile(cache_dir, 'manifest.csv'), frame_path);
    config_path = write_test_config(cache_dir);

    outputs = run_a1_1bo_6ul_hdf5_cache_segmentation_morphology( ...
        cache_dir, out_dir, config_path, 'morphology');
    T = readtable(outputs.red_mask_timeseries_csv, 'TextType', 'string');

    required = ["dnapl_water_length_px", "dnapl_solid_length_px", ...
        "dnapl_water_length_m", "dnapl_solid_length_m", "InterfaceArea", ...
        "solid_contact_fraction", "a_i_2D_proxy", "interface_semantics"];
    verifyTrue(testCase, all(ismember(required, string(T.Properties.VariableNames))));
    verifyGreaterThan(testCase, T.red_mask_area_px(1), 0);
    verifyGreaterThan(testCase, T.dnapl_water_length_px(1), 0);
    verifyGreaterThanOrEqual(testCase, T.dnapl_solid_length_px(1), 0);
    verifyEqual(testCase, T.InterfaceArea(1), T.dnapl_water_length_px(1), ...
        'AbsTol', 1e-12);
    verifyEqual(testCase, T.a_i_2D_proxy(1), ...
        T.dnapl_water_length_px(1) / T.red_mask_area_px(1), 'RelTol', 1e-12);
    verifyGreaterThanOrEqual(testCase, T.solid_contact_fraction(1), 0);
    verifyLessThanOrEqual(testCase, T.solid_contact_fraction(1), 1);
    verifyTrue(testCase, ismissing(T.dnapl_water_length_m(1)) || ...
        isnan(T.dnapl_water_length_m(1)));
    verifyEqual(testCase, T.interface_semantics(1), ...
        "InterfaceArea_legacy_alias_of_dnapl_water_length_px_not_area");
end


function write_test_frame(path_value, h, w)
    raw = zeros(3, w, h, 'single');
    for y = 3:6
        for x = 4:8
            raw(1, x, y) = 1;
        end
    end
    h5create(path_value, '/rgb_corrected', size(raw), 'Datatype', 'single');
    h5write(path_value, '/rgb_corrected', raw);
end


function write_test_mask(path_value, flow_domain)
    raw = uint8(flow_domain');
    h5create(path_value, '/flow_domain_mask', size(raw), 'Datatype', 'uint8');
    h5write(path_value, '/flow_domain_mask', raw);
end


function write_test_manifest(path_value, frame_path)
    label = "unit_frame";
    role = "residual";
    frame_order = 1;
    timeseries_order = 1;
    h5_path = string(frame_path);
    time_s = NaN;
    include_in_timeseries = true;
    manifest = table(label, role, frame_order, timeseries_order, h5_path, ...
        time_s, include_in_timeseries);
    writetable(manifest, path_value);
end


function config_path = write_test_config(cache_dir)
    config_path = fullfile(cache_dir, 'config.json');
    config = struct();
    config.segmentation_metrics = struct( ...
        'production_score_mode', 'normalized_red', ...
        'locked_threshold', 0.5, ...
        'threshold_source', 'unit_test_locked', ...
        'min_area_px', 0, ...
        'morph_radius', 0, ...
        'overlay_sample_max', 0, ...
        'write_blob_detail', false);
    fid = fopen(config_path, 'w');
    cleaner = onCleanup(@() fclose(fid));
    fwrite(fid, jsonencode(config), 'char');
end


function cleanup_dirs(paths)
    for idx = 1:numel(paths)
        if isfolder(paths{idx})
            rmdir(paths{idx}, 's');
        end
    end
end
