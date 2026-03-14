function tests = test_pipeline_status_monitoring
% Regression tests for heartbeat files and the PowerShell watcher.
    tests = functiontests(localfunctions);
end


function test_watcher_reports_completed_from_heartbeat(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    out_dir = fullfile(tempdir, ['dnapl_watch_' datestr(now, 'yyyymmdd_HHMMSSFFF')]);
    cleanup = onCleanup(@() cleanup_tempdir(out_dir)); %#ok<NASGU>
    addpath(genpath(root_dir));

    run_small_pipeline(out_dir);

    script_path = fullfile(root_dir, 'utilities', 'watch_pipeline_status.ps1');
    cmd = sprintf('powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%s" -OutputPath "%s" -RunOnce', ...
        script_path, out_dir);
    [status, cmdout] = system(cmd);

    verifyEqual(testCase, status, 0);
    verifyTrue(testCase, contains(cmdout, 'status=completed'));
    verifyTrue(testCase, contains(cmdout, 'step=STEP 5'));
    verifyFalse(testCase, contains(cmdout, 'heartbeat missing, using log fallback'));
    heartbeat = jsondecode(fileread(fullfile(out_dir, 'status', 'heartbeat_latest.json')));
    verifyTrue(testCase, isfield(heartbeat, 'matlab_pid'));
    verifyGreaterThan(testCase, heartbeat.matlab_pid, 0);
    verifyTrue(testCase, contains(cmdout, 'pid='));
end


function test_watcher_falls_back_to_logs_when_heartbeat_missing(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    out_dir = fullfile(tempdir, ['dnapl_watch_' datestr(now, 'yyyymmdd_HHMMSSFFF')]);
    cleanup = onCleanup(@() cleanup_tempdir(out_dir)); %#ok<NASGU>
    addpath(genpath(root_dir));

    run_small_pipeline(out_dir);
    status_dir = fullfile(out_dir, 'status');
    if isfolder(status_dir)
        rmdir(status_dir, 's');
    end

    script_path = fullfile(root_dir, 'utilities', 'watch_pipeline_status.ps1');
    cmd = sprintf('powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%s" -OutputPath "%s" -RunOnce', ...
        script_path, out_dir);
    [status, cmdout] = system(cmd);

    verifyEqual(testCase, status, 0);
    verifyTrue(testCase, contains(cmdout, 'status=completed'));
    verifyTrue(testCase, contains(cmdout, 'heartbeat missing, using log fallback'));
end


function test_watcher_reports_stalled_without_heartbeat(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    out_dir = fullfile(tempdir, ['dnapl_watch_fallback_' datestr(now, 'yyyymmdd_HHMMSSFFF')]);
    cleanup = onCleanup(@() cleanup_tempdir(out_dir)); %#ok<NASGU>

    mkdir(out_dir);
    mkdir(fullfile(out_dir, 'logs'));

    log_path = fullfile(out_dir, 'logs', 'pipeline_log_fake.txt');
    fid = fopen(log_path, 'w');
    fprintf(fid, 'STEP 0: Loading Images\n');
    fprintf(fid, '  Frames to analyze: 1723\n');
    fprintf(fid, '\nSTEP 4: Solubilization Dynamics (1723 frames)\n');
    fprintf(fid, '  --- Frame 144 / 1723 ---\n');
    fclose(fid);

    fclose(fopen(fullfile(out_dir, 'checkpoint_0144.mat'), 'w'));

    script_path = fullfile(root_dir, 'utilities', 'watch_pipeline_status.ps1');
    cmd = sprintf(['powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%s" ', ...
        '-OutputPath "%s" -RunOnce -StalledThresholdMinutes 0'], ...
        script_path, out_dir);
    [status, cmdout] = system(cmd);

    verifyNotEqual(testCase, status, 0);
    verifyTrue(testCase, contains(cmdout, 'status=stalled'));
    verifyTrue(testCase, contains(cmdout, 'frame=144/1723'));
    verifyTrue(testCase, contains(cmdout, 'heartbeat missing, using log fallback'));
    verifyFalse(testCase, contains(cmdout, 'status=running'));
end


function test_watcher_reports_crashed_without_matching_matlab_process(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    out_dir = fullfile(tempdir, ['dnapl_watch_crash_' datestr(now, 'yyyymmdd_HHMMSSFFF')]);
    cleanup = onCleanup(@() cleanup_tempdir(out_dir)); %#ok<NASGU>

    mkdir(out_dir);
    mkdir(fullfile(out_dir, 'logs'));

    log_path = fullfile(out_dir, 'logs', 'pipeline_log_fake.txt');
    fid = fopen(log_path, 'w');
    fprintf(fid, 'STEP 0: Loading Images\n');
    fprintf(fid, '  Frames to analyze: 1723\n');
    fprintf(fid, '\nSTEP 4: Solubilization Dynamics (1723 frames)\n');
    fprintf(fid, '  --- Frame 144 / 1723 ---\n');
    fclose(fid);

    fclose(fopen(fullfile(out_dir, 'checkpoint_0144.mat'), 'w'));

    script_path = fullfile(root_dir, 'utilities', 'watch_pipeline_status.ps1');
    cmd = sprintf(['powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%s" ', ...
        '-OutputPath "%s" -RunOnce -StalledThresholdMinutes 0 ', ...
        '-ProcessNameOverride "__definitely_missing_matlab_process__"'], ...
        script_path, out_dir);
    [status, cmdout] = system(cmd);

    verifyNotEqual(testCase, status, 0);
    verifyTrue(testCase, contains(cmdout, 'status=crashed'));
    verifyTrue(testCase, contains(cmdout, 'heartbeat missing, using log fallback'));
end


function test_watcher_reports_paused_from_heartbeat(testCase)
    root_dir = fileparts(fileparts(mfilename('fullpath')));
    out_dir = fullfile(tempdir, ['dnapl_watch_pause_' datestr(now, 'yyyymmdd_HHMMSSFFF')]);
    cleanup = onCleanup(@() cleanup_tempdir(out_dir)); %#ok<NASGU>
    addpath(genpath(root_dir));

    config = config_pipeline( ...
        'pages', 1:6, ...
        'physical.pixel_size', 3.92e-6, ...
        'preprocess.manual_crop_rect', [380 40 1821 1927], ...
        'flow_domain_crop_rect', [372 66 1821 1933], ...
        'illumination.kernel_size', 30, ...
        'visualization.show_figures', false, ...
        'visualization.save_figures', false, ...
        'parallel.enabled', false, ...
        'output_path', out_dir, ...
        'output.checkpoint', true, ...
        'output.save_interval', 2, ...
        'output.max_frames_per_session', 2, ...
        'output.save_progress', false);

    results = main_DNAPL_pipeline(config);
    verifyEqual(testCase, string(results.pipeline_status), "paused");

    script_path = fullfile(root_dir, 'utilities', 'watch_pipeline_status.ps1');
    cmd = sprintf('powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%s" -OutputPath "%s" -RunOnce', ...
        script_path, out_dir);
    [status, cmdout] = system(cmd);

    verifyEqual(testCase, status, 0);
    verifyTrue(testCase, contains(cmdout, 'status=paused'));
    verifyTrue(testCase, contains(cmdout, 'frame=2/6'));
    verifyFalse(testCase, contains(cmdout, 'heartbeat missing, using log fallback'));
end


function run_small_pipeline(out_dir)
    old_vis = get(groot, 'defaultFigureVisible');
    set(groot, 'defaultFigureVisible', 'off');
    c1 = onCleanup(@() set(groot, 'defaultFigureVisible', old_vis)); %#ok<NASGU>

    config = config_pipeline( ...
        'pages', 1:2, ...
        'physical.pixel_size', 3.92e-6, ...
        'preprocess.manual_crop_rect', [380 40 1821 1927], ...
        'flow_domain_crop_rect', [372 66 1821 1933], ...
        'illumination.kernel_size', 30, ...
        'visualization.show_figures', false, ...
        'visualization.save_figures', false, ...
        'parallel.enabled', false, ...
        'output_path', out_dir, ...
        'output.save_progress', false, ...
        'output.checkpoint', false);

    main_DNAPL_pipeline(config);
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
