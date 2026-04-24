function T = extract_pixel_sizes(varargin)
% EXTRACT_PIXEL_SIZES  批量扫描多个数据库目录，提取 pixel_size 并导出 CSV。
%
%   T = extract_pixel_sizes(dir1, dir2, ...)
%       批量输入多个目录，一起扫描并汇总输出
%
%   T = extract_pixel_sizes(..., 'OutputFile', 'pixel_sizes.csv')
%       指定输出 CSV 文件路径（默认保存到脚本所在目录）
%
%   示例:
%       % 扫描单个目录
%       T = extract_pixel_sizes('D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\01 databased');
%
%       % 批量扫描多个目录
%       T = extract_pixel_sizes( ...
%           'D:\data\exp01', ...
%           'D:\data\exp02', ...
%           'D:\data\exp03');
%
%       % 指定输出文件名
%       T = extract_pixel_sizes('D:\data', 'OutputFile', 'D:\results\pixel_sizes.csv');
%
%   输出文件 (CSV) 包含列:
%       RootDir       — 来源的根目录
%       Group         — 实验组名 (上层文件夹)
%       Phase         — 实验阶段 (如 01 NAPL, 02 Water Displacement)
%       OutputFolder  — output 文件夹名
%       PixelSize_um  — pixel_size [μm/px]
%       PixelSize_m   — pixel_size [m/px]
%       Source        — 数据来源 ('config' 或 'results')
%       MatFile       — .mat 文件完整路径
%
%   See also: generate_report, config_pipeline

    %% 解析输入参数
    dirs = {};
    out_file = '';

    i = 1;
    while i <= numel(varargin)
        if ischar(varargin{i}) && strcmpi(varargin{i}, 'OutputFile')
            if i + 1 <= numel(varargin)
                out_file = varargin{i+1};
                i = i + 2;
            else
                error('extract_pixel_sizes:missingValue', 'OutputFile 需要指定文件路径');
            end
        else
            dirs{end+1} = varargin{i}; %#ok<AGROW>
            i = i + 1;
        end
    end

    % 如果没有输入任何目录，弹窗让用户选
    if isempty(dirs)
        fprintf('  请在弹窗中选择数据目录（可多次选择，点"取消"结束）\n\n');
        last_path = pwd;
        while true
            folder = uigetdir(last_path, ...
                sprintf('选择第 %d 个数据目录（取消=结束选择）', numel(dirs) + 1));
            if folder == 0
                break;  % 用户点了取消
            end
            dirs{end+1} = folder; %#ok<AGROW>
            last_path = fileparts(folder);
            fprintf('  已添加: %s\n', folder);
        end
        if isempty(dirs)
            fprintf('  未选择任何目录，退出。\n');
            T = table();
            return;
        end
        fprintf('  共选择 %d 个目录\n\n', numel(dirs));
    end

    % 默认输出文件
    if isempty(out_file)
        script_dir = fileparts(mfilename('fullpath'));
        out_file = fullfile(script_dir, ...
            ['pixel_sizes_' datestr(now, 'yyyymmdd_HHMMSS') '.csv']);
    end

    %% 批量扫描所有目录
    all_root     = {};
    all_group    = {};
    all_phase    = {};
    all_outfld   = {};
    all_px_um    = [];
    all_px_m     = [];
    all_source   = {};
    all_matpath  = {};

    for d = 1:numel(dirs)
        root_dir = dirs{d};
        if ~isfolder(root_dir)
            fprintf('  ⚠ 目录不存在，跳过: %s\n', root_dir);
            continue;
        end

        fprintf('扫描目录 [%d/%d]: %s\n', d, numel(dirs), root_dir);
        fprintf('--------------------------------------------------------\n');

        mat_list = dir(fullfile(root_dir, '**', 'results_*.mat'));

        if isempty(mat_list)
            fprintf('  未找到 results_*.mat 文件\n\n');
            continue;
        end

        fprintf('  找到 %d 个结果文件\n\n', numel(mat_list));

        for i = 1:numel(mat_list)
            mat_path = fullfile(mat_list(i).folder, mat_list(i).name);

            % 解析路径层级
            parts = strsplit(mat_list(i).folder, filesep);
            out_folder = parts{end};

            rel = strrep(mat_list(i).folder, root_dir, '');
            rel_parts = strsplit(rel, filesep);
            rel_parts = rel_parts(~cellfun('isempty', rel_parts));

            if numel(rel_parts) >= 3
                group = rel_parts{1};
                phase = rel_parts{2};
            elseif numel(rel_parts) >= 2
                group = rel_parts{1};
                phase = '';
            else
                group = '';
                phase = '';
            end

            % 提取 pixel_size（兼容中文路径）
            pixel_val = NaN;
            source = 'not_found';
            [pixel_val, source] = try_load_pixel_size(mat_path);

            % 打印
            if ~isnan(pixel_val)
                fprintf('  [%d] %s / %s → %.2f μm/px  [%s]\n', ...
                    i, group, phase, pixel_val * 1e6, source);
            else
                fprintf('  [%d] %s / %s → *** 未找到 ***  [%s]\n', ...
                    i, group, phase, source);
            end

            % 累积
            all_root{end+1}    = root_dir;       %#ok<AGROW>
            all_group{end+1}   = group;           %#ok<AGROW>
            all_phase{end+1}   = phase;           %#ok<AGROW>
            all_outfld{end+1}  = out_folder;      %#ok<AGROW>
            all_px_um(end+1)   = pixel_val * 1e6; %#ok<AGROW>
            all_px_m(end+1)    = pixel_val;        %#ok<AGROW>
            all_source{end+1}  = source;          %#ok<AGROW>
            all_matpath{end+1} = mat_path;        %#ok<AGROW>
        end
        fprintf('\n');
    end

    %% 构建 table
    if isempty(all_root)
        fprintf('  未找到任何数据。\n');
        T = table();
        return;
    end

    T = table(all_root(:), all_group(:), all_phase(:), all_outfld(:), ...
              all_px_um(:), all_px_m(:), all_source(:), all_matpath(:), ...
        'VariableNames', {'RootDir', 'Group', 'Phase', 'OutputFolder', ...
                          'PixelSize_um', 'PixelSize_m', 'Source', 'MatFile'});

    %% 汇总
    n = height(T);
    valid = ~isnan(T.PixelSize_m);
    fprintf('========================================================\n');
    fprintf('  汇总: %d 组实验，%d 个有效 pixel_size\n', n, sum(valid));
    if any(valid)
        fprintf('  范围: %.2f – %.2f μm/px\n', ...
            min(T.PixelSize_um(valid)), max(T.PixelSize_um(valid)));
    end

    %% 导出 CSV
    out_dir = fileparts(out_file);
    if ~isempty(out_dir) && ~isfolder(out_dir)
        mkdir(out_dir);
    end
    writetable(T, out_file, 'Encoding', 'UTF-8');
    fprintf('\n  ✓ 已导出 CSV: %s\n', out_file);
    fprintf('========================================================\n\n');

    % 控制台也显示精简表
    disp(T(:, {'Group', 'Phase', 'PixelSize_um', 'Source'}));
end


function [pixel_val, source] = try_load_pixel_size(mat_path)
% TRY_LOAD_PIXEL_SIZE  从 .mat 文件提取 pixel_size，兼容中文路径。
%   先尝试直接 load；如果失败（中文路径问题），则复制到临时文件再加载。
%   搜索顺序：config.physical.pixel_size → results 中递归查找

    pixel_val = NaN;
    source = 'not_found';
    tmp_file = '';

    % === 确定实际加载路径（兼容中文路径）===
    load_path = mat_path;
    try
        whos('-file', mat_path);  % 测试能否直接读取
    catch
        % 直接读取失败 → 复制到临时目录
        tmp_file = [tempname '.mat'];
        [ok, msg] = copyfile(mat_path, tmp_file);
        if ~ok
            source = ['copy_error: ' msg];
            return;
        end
        load_path = tmp_file;
    end

    try
        % === 查看 .mat 中有哪些变量 ===
        vars = whos('-file', load_path);
        var_names = {vars.name};

        % === 策略1: 从 config.physical.pixel_size 读取 ===
        if ismember('config', var_names)
            loaded = load(load_path, 'config');
            cfg = loaded.config;
            if isfield(cfg, 'physical') && isfield(cfg.physical, 'pixel_size')
                val = cfg.physical.pixel_size;
                if isnumeric(val) && val > 0
                    pixel_val = val;
                    source = 'config';
                elseif ischar(val)
                    source = ['config ("' val '")'];
                end
            end
        end

        % === 策略2: 从 results 中递归搜索 pixel_size ===
        if isnan(pixel_val) && ismember('results', var_names)
            loaded = load(load_path, 'results');
            res = loaded.results;
            [pixel_val, source] = search_pixel_size_in_struct(res, 'results');
        end

        % === 策略3: 加载全部变量，逐个搜索 ===
        if isnan(pixel_val)
            loaded = load(load_path);
            fn = fieldnames(loaded);
            for k = 1:numel(fn)
                v = loaded.(fn{k});
                if isstruct(v)
                    [pixel_val, source] = search_pixel_size_in_struct(v, fn{k});
                    if ~isnan(pixel_val), break; end
                end
            end
        end

    catch ME
        source = ['error: ' ME.message];
    end

    % === 清理临时文件 ===
    if ~isempty(tmp_file) && isfile(tmp_file)
        delete(tmp_file);
    end
end


function [val, source] = search_pixel_size_in_struct(s, prefix)
% SEARCH_PIXEL_SIZE_IN_STRUCT  在 struct 中递归搜索名为 pixel_size 的数值字段
    val = NaN;
    source = 'not_found';

    if ~isstruct(s), return; end

    fn = fieldnames(s);
    for k = 1:numel(fn)
        field = fn{k};
        v = s.(field);
        path_str = [prefix '.' field];

        if strcmpi(field, 'pixel_size') && isnumeric(v) && ~isnan(v) && v > 0
            val = v;
            source = path_str;
            return;
        end

        % 递归搜索子 struct（限制深度，避免太深）
        if isstruct(v) && ~isempty(fieldnames(v)) && numel(strsplit(prefix, '.')) < 4
            [val, source] = search_pixel_size_in_struct(v, path_str);
            if ~isnan(val), return; end
        end
    end
end
