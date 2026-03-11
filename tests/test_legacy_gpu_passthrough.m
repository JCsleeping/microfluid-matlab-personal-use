function tests = test_legacy_gpu_passthrough
% TEST_LEGACY_GPU_PASSTHROUGH  Regression tests for legacy GPU flag passthrough.
    tests = functiontests(localfunctions);
end


function test_legacy_path_passes_parallel_gpu_flag(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    legacy_file = fullfile(root_dir, 'others', 'legacy', 'characterize_solubilization.m');
    file_text = fileread(legacy_file);

    verifyTrue(testCase, ...
        contains(file_text, ...
        "config.illumination.method, config.illumination, config.parallel.use_gpu"), ...
        'Legacy characterize_solubilization must pass config.parallel.use_gpu to correct_illumination.');
end
