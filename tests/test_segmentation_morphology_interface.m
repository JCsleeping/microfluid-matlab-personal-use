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


function test_morphology_writes_mask_stack_and_blob_detail_provenance(testCase)
    repo_root = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(repo_root));
    cache_dir = fullfile(tempdir, ['segmorph_stack_cache_' char(java.util.UUID.randomUUID)]);
    out_dir = fullfile(tempdir, ['segmorph_stack_out_' char(java.util.UUID.randomUUID)]);
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
    config_path = write_test_config(cache_dir, true);

    outputs = run_a1_1bo_6ul_hdf5_cache_segmentation_morphology( ...
        cache_dir, out_dir, config_path, 'morphology');

    verifyTrue(testCase, isfield(outputs, 'red_mask_stack_h5'));
    verifyTrue(testCase, isfield(outputs, 'red_mask_stack_manifest_csv'));
    verifyTrue(testCase, isfield(outputs, 'red_blob_detail_csv'));
    verifyTrue(testCase, isfile(outputs.red_mask_stack_h5));
    verifyTrue(testCase, isfile(outputs.red_mask_stack_manifest_csv));
    verifyTrue(testCase, isfile(outputs.red_blob_detail_csv));

    mask_stack = h5read(outputs.red_mask_stack_h5, '/red_mask');
    verifyEqual(testCase, size(mask_stack, 1), h);
    verifyEqual(testCase, size(mask_stack, 2), w);
    verifyEqual(testCase, class(mask_stack), 'uint8');
    verifyGreaterThan(testCase, nnz(mask_stack), 0);

    stack_manifest = readtable(outputs.red_mask_stack_manifest_csv, ...
        'TextType', 'string');
    verifyEqual(testCase, height(stack_manifest), 1);
    verifyEqual(testCase, stack_manifest.mask_grid(1), "processing_grid");
    verifyEqual(testCase, stack_manifest.processing_scale_factor(1), 3);
    verifyEqual(testCase, stack_manifest.h5_dataset(1), "/red_mask");
    verifyEqual(testCase, stack_manifest.h5_frame_index(1), 1);
    verifyEqual(testCase, stack_manifest.mask_height(1), h);
    verifyEqual(testCase, stack_manifest.mask_width(1), w);

    detail = readtable(outputs.red_blob_detail_csv, 'TextType', 'string');
    required = ["frame_index", "label", "role", "mask_grid", ...
        "processing_scale_factor", "Area", "Area_processing_px2", ...
        "Area_native_equiv_px2", "AspectRatio", "Solidity", ...
        "EulerNumber", "TopologyType"];
    verifyTrue(testCase, all(ismember(required, ...
        string(detail.Properties.VariableNames))));
    verifyGreaterThan(testCase, height(detail), 0);
    verifyEqual(testCase, detail.mask_grid(1), "processing_grid");
    verifyEqual(testCase, detail.processing_scale_factor(1), 3);
    verifyEqual(testCase, detail.Area_native_equiv_px2(1), ...
        detail.Area_processing_px2(1) / 9, 'RelTol', 1e-12);
end


function test_morphology_writes_chunked_blob_detail(testCase)
    repo_root = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(repo_root));
    cache_dir = fullfile(tempdir, ['segmorph_chunk_cache_' char(java.util.UUID.randomUUID)]);
    out_dir = fullfile(tempdir, ['segmorph_chunk_out_' char(java.util.UUID.randomUUID)]);
    mkdir(cache_dir);
    mkdir(out_dir);
    cleanup = onCleanup(@() cleanup_dirs({cache_dir, out_dir}));

    h = 10;
    w = 12;
    flow_domain = true(h, w);
    flow_domain(1:2, :) = false;
    mask_path = fullfile(cache_dir, 'mask_crop.h5');
    write_test_mask(mask_path, flow_domain);

    frame_paths = strings(2, 1);
    for idx = 1:2
        frame_paths(idx) = string(fullfile(cache_dir, sprintf('frame_%03d.h5', idx)));
        write_test_frame(char(frame_paths(idx)), h, w);
    end
    write_test_manifest_multi(fullfile(cache_dir, 'manifest.csv'), frame_paths);
    config_path = write_test_config(cache_dir, true, struct( ...
        'blob_detail_output_mode', 'chunked_csv', ...
        'frame_start_index', 1, ...
        'frame_end_index', 2, ...
        'resume_outputs', false));

    outputs = run_a1_1bo_6ul_hdf5_cache_segmentation_morphology( ...
        cache_dir, out_dir, config_path, 'morphology');

    verifyTrue(testCase, isfield(outputs, 'red_blob_detail_chunk_csv'));
    verifyTrue(testCase, isfield(outputs, 'red_blob_detail_chunks_dir'));
    verifyTrue(testCase, isfolder(outputs.red_blob_detail_chunks_dir));
    verifyTrue(testCase, isfile(outputs.red_blob_detail_chunk_csv));
    verifyFalse(testCase, isfile(fullfile(out_dir, 'red_blob_detail_all_frames.csv')));

    detail = readtable(outputs.red_blob_detail_chunk_csv, 'TextType', 'string');
    verifyGreaterThan(testCase, height(detail), 0);
    verifyTrue(testCase, all(ismember(["frame_index", "label", ...
        "mask_grid", "processing_scale_factor", "Area"], ...
        string(detail.Properties.VariableNames))));
    verifyEqual(testCase, unique(detail.frame_index)', [1 2]);
    verifyEqual(testCase, detail.mask_grid(1), "processing_grid");
    verifyEqual(testCase, detail.processing_scale_factor(1), 3);
end


function test_morphology_frame_range_appends_incremental_outputs(testCase)
    repo_root = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(repo_root));
    cache_dir = fullfile(tempdir, ['segmorph_range_cache_' char(java.util.UUID.randomUUID)]);
    out_dir = fullfile(tempdir, ['segmorph_range_out_' char(java.util.UUID.randomUUID)]);
    mkdir(cache_dir);
    mkdir(out_dir);
    cleanup = onCleanup(@() cleanup_dirs({cache_dir, out_dir}));

    h = 10;
    w = 12;
    flow_domain = true(h, w);
    flow_domain(1:2, :) = false;
    mask_path = fullfile(cache_dir, 'mask_crop.h5');
    write_test_mask(mask_path, flow_domain);

    frame_paths = strings(3, 1);
    for idx = 1:3
        frame_paths(idx) = string(fullfile(cache_dir, sprintf('frame_%03d.h5', idx)));
        write_test_frame(char(frame_paths(idx)), h, w);
    end
    write_test_manifest_multi(fullfile(cache_dir, 'manifest.csv'), frame_paths);

    config_path_1 = write_test_config(cache_dir, true, struct( ...
        'frame_start_index', 1, ...
        'frame_end_index', 2, ...
        'resume_outputs', false));
    outputs = run_a1_1bo_6ul_hdf5_cache_segmentation_morphology( ...
        cache_dir, out_dir, config_path_1, 'morphology');

    T1 = readtable(outputs.red_mask_timeseries_csv, 'TextType', 'string');
    S1 = readtable(outputs.red_mask_stack_manifest_csv, 'TextType', 'string');
    verifyEqual(testCase, height(T1), 2);
    verifyEqual(testCase, height(S1), 2);
    verifyEqual(testCase, T1.frame_index', [1 2]);

    config_path_2 = write_test_config(cache_dir, true, struct( ...
        'frame_start_index', 3, ...
        'frame_end_index', 3, ...
        'resume_outputs', true));
    outputs = run_a1_1bo_6ul_hdf5_cache_segmentation_morphology( ...
        cache_dir, out_dir, config_path_2, 'morphology');

    T2 = readtable(outputs.red_mask_timeseries_csv, 'TextType', 'string');
    B2 = readtable(outputs.red_blob_summary_csv, 'TextType', 'string');
    S2 = readtable(outputs.red_mask_stack_manifest_csv, 'TextType', 'string');
    verifyEqual(testCase, height(T2), 3);
    verifyEqual(testCase, height(B2), 3);
    verifyEqual(testCase, height(S2), 3);
    verifyEqual(testCase, T2.frame_index', [1 2 3]);
    verifyEqual(testCase, S2.h5_frame_index', [1 2 3]);

    mask_stack = h5read(outputs.red_mask_stack_h5, '/red_mask');
    verifyEqual(testCase, size(mask_stack, 3), 3);
    verifyGreaterThan(testCase, nnz(mask_stack(:, :, 3)), 0);
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


function write_test_manifest_multi(path_value, frame_paths)
    n = numel(frame_paths);
    label = strings(n, 1);
    role = strings(n, 1);
    frame_order = zeros(n, 1);
    timeseries_order = zeros(n, 1);
    h5_path = strings(n, 1);
    time_s = NaN(n, 1);
    include_in_timeseries = true(n, 1);
    for idx = 1:n
        label(idx) = "unit_frame_" + idx;
        role(idx) = "residual";
        frame_order(idx) = idx;
        timeseries_order(idx) = idx;
        h5_path(idx) = string(frame_paths(idx));
    end
    manifest = table(label, role, frame_order, timeseries_order, h5_path, ...
        time_s, include_in_timeseries);
    writetable(manifest, path_value);
end


function config_path = write_test_config(cache_dir, write_outputs, extra_metrics)
    if nargin < 2
        write_outputs = false;
    end
    if nargin < 3
        extra_metrics = struct();
    end
    config_path = fullfile(cache_dir, 'config.json');
    config = struct();
    config.segmentation_metrics = struct( ...
        'production_score_mode', 'normalized_red', ...
        'locked_threshold', 0.5, ...
        'threshold_source', 'unit_test_locked', ...
        'min_area_px', 0, ...
        'morph_radius', 0, ...
        'overlay_sample_max', 0, ...
        'write_blob_detail', write_outputs, ...
        'write_mask_stack', write_outputs, ...
        'processing_scale_factor', 3);
    extra_fields = fieldnames(extra_metrics);
    for idx = 1:numel(extra_fields)
        config.segmentation_metrics.(extra_fields{idx}) = ...
            extra_metrics.(extra_fields{idx});
    end
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
