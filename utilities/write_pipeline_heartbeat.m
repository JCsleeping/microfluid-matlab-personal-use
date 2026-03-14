function heartbeat = write_pipeline_heartbeat(heartbeat, update)
% WRITE_PIPELINE_HEARTBEAT  Update and persist lightweight pipeline status.
%
%   heartbeat = write_pipeline_heartbeat(heartbeat, update)
%
%   The heartbeat context carries throttling state and output paths. The
%   update struct can set any public payload field plus an optional
%   logical field `.force` to bypass write throttling.

    if nargin < 1 || isempty(heartbeat)
        heartbeat = struct('enabled', false);
        return;
    end
    if nargin < 2 || isempty(update)
        update = struct();
    end
    if ~isstruct(heartbeat) || ~isfield(heartbeat, 'enabled') || ~heartbeat.enabled
        return;
    end

    force = false;
    if isfield(update, 'force')
        force = logical(update.force);
        update = rmfield(update, 'force');
    end

    previous_step = '';
    previous_status = '';
    previous_checkpoint = '';
    if isfield(heartbeat, 'payload') && isstruct(heartbeat.payload)
        previous_step = get_char_field(heartbeat.payload, 'step', '');
        previous_status = get_char_field(heartbeat.payload, 'status', '');
        previous_checkpoint = get_char_field(heartbeat.payload, 'last_checkpoint', '');
    else
        heartbeat.payload = struct();
    end

    update_fields = fieldnames(update);
    for idx = 1:numel(update_fields)
        field_name = update_fields{idx};
        heartbeat.payload.(field_name) = update.(field_name);
    end

    heartbeat.payload = normalize_payload(heartbeat.payload, heartbeat.output_path);

    current_step = get_char_field(heartbeat.payload, 'step', '');
    current_status = get_char_field(heartbeat.payload, 'status', '');
    current_checkpoint = get_char_field(heartbeat.payload, 'last_checkpoint', '');

    if ~strcmp(current_step, previous_step) || ~strcmp(current_status, previous_status) || ...
            ~strcmp(current_checkpoint, previous_checkpoint)
        force = true;
    end

    current_frame = get_numeric_field(heartbeat.payload, 'current_frame', 0);
    frame_due = current_frame >= heartbeat.last_written_frame + heartbeat.frame_interval;
    elapsed_sec = (now - heartbeat.last_write_datenum) * 86400;
    time_due = elapsed_sec >= heartbeat.time_interval_sec;

    if ~(force || frame_due || time_due)
        return;
    end

    if ~isfolder(heartbeat.status_dir)
        mkdir(heartbeat.status_dir);
    end

    heartbeat.payload.updated_at = datestr(now, 'yyyy-mm-dd HH:MM:SS');
    write_json_atomic(heartbeat.json_path, jsonencode(heartbeat.payload));

    heartbeat_debug = heartbeat.payload; %#ok<NASGU>
    save(heartbeat.mat_path, 'heartbeat_debug');

    heartbeat.last_write_datenum = now;
    heartbeat.last_written_frame = current_frame;
end


function payload = normalize_payload(payload, output_path)
    if ~isfield(payload, 'run_id') || isempty(payload.run_id)
        payload.run_id = ['run_' datestr(now, 'yyyymmdd_HHMMSS')];
    end
    if ~isfield(payload, 'updated_at') || isempty(payload.updated_at)
        payload.updated_at = '';
    end
    if ~isfield(payload, 'status') || isempty(payload.status)
        payload.status = 'starting';
    end
    if ~isfield(payload, 'step') || isempty(payload.step)
        payload.step = '';
    end
    if ~isfield(payload, 'step_label') || isempty(payload.step_label)
        payload.step_label = '';
    end
    if ~isfield(payload, 'current_frame') || isempty(payload.current_frame)
        payload.current_frame = 0;
    end
    if ~isfield(payload, 'total_frames') || isempty(payload.total_frames)
        payload.total_frames = 0;
    end
    if payload.total_frames > 0
        payload.progress_ratio = min(max(double(payload.current_frame) / double(payload.total_frames), 0), 1);
    else
        payload.progress_ratio = 0;
    end
    if ~isfield(payload, 'last_checkpoint') || isempty(payload.last_checkpoint)
        payload.last_checkpoint = '';
    end
    if ~isfield(payload, 'matlab_pid') || isempty(payload.matlab_pid)
        payload.matlab_pid = 0;
    end
    if ~isfield(payload, 'hostname') || isempty(payload.hostname)
        payload.hostname = '';
    end
    payload.output_path = output_path;
    if ~isfield(payload, 'message') || isempty(payload.message)
        payload.message = '';
    end
end


function write_json_atomic(json_path, json_text)
    temp_path = [json_path '.tmp'];
    fid = fopen(temp_path, 'w');
    if fid < 0
        error('write_pipeline_heartbeat:openFailed', ...
            'Could not open heartbeat temp file: %s', temp_path);
    end

    cleaner = onCleanup(@() fclose_if_open(fid)); %#ok<NASGU>
    fwrite(fid, json_text, 'char');
    fclose(fid);
    movefile(temp_path, json_path, 'f');
end


function fclose_if_open(fid)
    if fid > 0
        try
            fclose(fid);
        catch
            % Best effort cleanup.
        end
    end
end


function value = get_char_field(s, field_name, default_value)
    if isfield(s, field_name) && ~isempty(s.(field_name))
        value = char(s.(field_name));
    else
        value = default_value;
    end
end


function value = get_numeric_field(s, field_name, default_value)
    if isfield(s, field_name) && isnumeric(s.(field_name)) && isscalar(s.(field_name))
        value = double(s.(field_name));
    else
        value = default_value;
    end
end
