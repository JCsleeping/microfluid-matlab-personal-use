function tests = test_flow_domain_mask_grid
% Tests for flow-domain mask coordinate provenance.
    tests = functiontests(localfunctions);
end


function test_native_full_mask_is_cropped_before_resize(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    tmp_dir = tempname;
    mkdir(tmp_dir);
    cleanup = onCleanup(@() cleanup_dir(tmp_dir));

    full_mask = false(40, 50);
    full_mask(6:25, 11:30) = true;
    mask_path = fullfile(tmp_dir, 'native_full_mask.tif');
    imwrite(uint8(full_mask) * 255, mask_path);

    ref_image = repmat(uint8(180), 20, 20, 3);
    chip_mask = true(20, 20);
    config = struct();
    config.preprocessing.rgb_encoding = 'srgb';
    config.flow_domain.extraction_method = 'mask';
    config.flow_domain.flow_domain_mask_path = mask_path;
    config.flow_domain.mask_grid = 'native_full';
    config.flow_domain.mask_resize_method = 'nearest';
    config.flow_domain.hard_fail = false;
    config.flow_domain.expected_porosity = NaN;
    config.preprocess.saved_crop_rect = [11, 6, 19, 19];
    config.qc.flow_domain.hard_fail = false;

    [flow_domain, solid_mask, info] = extract_flow_domain(ref_image, chip_mask, config);

    verifyEqual(testCase, size(flow_domain), [20 20]);
    verifyTrue(testCase, all(flow_domain(:)));
    verifyFalse(testCase, any(solid_mask(:)));
    verifyEqual(testCase, info.mask_grid, 'native_full');
    verifyEqual(testCase, info.mask_crop_rect, [11, 6, 19, 19]);
    verifyFalse(testCase, info.mask_resized);
end


function test_target_mask_keeps_existing_behavior(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(root_dir));

    tmp_dir = tempname;
    mkdir(tmp_dir);
    cleanup = onCleanup(@() cleanup_dir(tmp_dir));

    target_mask = true(20, 20);
    target_mask(:, 1) = false;
    mask_path = fullfile(tmp_dir, 'target_mask.tif');
    imwrite(uint8(target_mask) * 255, mask_path);

    ref_image = repmat(uint8(180), 20, 20, 3);
    chip_mask = true(20, 20);
    config = struct();
    config.preprocessing.rgb_encoding = 'srgb';
    config.flow_domain.extraction_method = 'mask';
    config.flow_domain.flow_domain_mask_path = mask_path;
    config.flow_domain.mask_grid = 'target';
    config.flow_domain.mask_resize_method = 'nearest';
    config.flow_domain.hard_fail = false;
    config.flow_domain.expected_porosity = NaN;
    config.preprocess.saved_crop_rect = [2, 2, 2, 2];
    config.qc.flow_domain.hard_fail = false;

    [flow_domain, ~, info] = extract_flow_domain(ref_image, chip_mask, config);

    verifyEqual(testCase, flow_domain, target_mask);
    verifyEqual(testCase, info.mask_grid, 'target');
    verifyFalse(testCase, isfield(info, 'mask_crop_rect'));
    verifyFalse(testCase, info.mask_resized);
end


function cleanup_dir(path_value)
    if exist(path_value, 'dir') == 7
        rmdir(path_value, 's');
    end
end
