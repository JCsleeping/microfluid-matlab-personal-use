function T = extract_pixel_sizes(root_dir)
% EXTRACT_PIXEL_SIZES  扫描所有 output 文件夹，提取每组实验的 pixel_size。
%
%   T = extract_pixel_sizes('D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\01 databased')
%       扫描默认数据库目录 (01 databased)
%
%   T = extract_pixel_sizes(root_dir)
%       扫描指定根目录下的所有 results_*.mat 文件
%
%   返回值:
%       T - table，包含列:
%           Group         — 实验组名 (上层文件夹)
%           Phase         — 实验阶段 (如 01 NAPL, 02 Water Displacement)
%           OutputFolder  — output 文件夹名
%           PixelSize_um  — pixel_size [μm/px]
%           PixelSize_m   — pixel_size [m/px]
%           Source        — 数据来源 ('config' 或 'fallback')
%           MatFile       — .mat 文件完整路径
%
%   示例:
%       T = extract_pixel_sizes();
%       disp(T);
%
%   See also: generate_report, config_pipeline

    if nargin < 1 || isempty(root_dir)
        % 默认：从脚本所在位置推断 databased 目录
        script_dir = fileparts(mfilename('fullpath'));
        root_dir = fullfile(fileparts(script_dir), '01 databased');
    end

    if ~isfolder(root_dir)
        error('extract_pixel_sizes:notFound', '目录不存在: %s', root_dir);
    end

    fprintf('扫描目录: %s\n', root_dir);
    fprintf('========================================================\n');

    % 递归查找所有 results_*.mat
    mat_list = dir(fullfile(root_dir, '**', 'results_*.mat'));

    if isempty(mat_list)
        fprintf('  未找到任何 results_*.mat 文件。\n');
        T = table();
        return;
    end

    fprintf('  找到 %d 个结果文件\n\n', numel(mat_list));

    % 预分配
    n = numel(mat_list);
    groups       = cell(n, 1);
    phases       = cell(n, 1);
    out_folders  = cell(n, 1);
    px_um        = nan(n, 1);
    px_m         = nan(n, 1);
    sources      = cell(n, 1);
    mat_paths    = cell(n, 1);

    for i = 1:n
        mat_path = fullfile(mat_list(i).folder, mat_list(i).name);
        mat_paths{i} = mat_path;

        % 解析路径层级：.../Group/Phase/output_xxx/results_xxx.mat
        parts = strsplit(mat_list(i).folder, filesep);
        % output_xxx 是最后一级
        out_folders{i} = parts{end};

        % 向上找 Phase 和 Group
        rel = strrep(mat_list(i).folder, root_dir, '');
        rel_parts = strsplit(rel, filesep);
        rel_parts = rel_parts(~cellfun('isempty', rel_parts));

        if numel(rel_parts) >= 3
            groups{i} = rel_parts{1};
            phases{i} = rel_parts{2};
        elseif numel(rel_parts) >= 2
            groups{i} = rel_parts{1};
            phases{i} = '';
        else
            groups{i} = '';
            phases{i} = '';
        end

        % 加载 config（只加载需要的变量，节省内存）
        try
            vars = whos('-file', mat_path);
            var_names = {vars.name};

            pixel_val = NaN;
            source = 'not_found';

            if ismember('config', var_names)
                loaded = load(mat_path, 'config');
                cfg = loaded.config;
                if isfield(cfg, 'physical') && isfield(cfg.physical, 'pixel_size')
                    val = cfg.physical.pixel_size;
                    if isnumeric(val) && ~isnan(val)
                        pixel_val = val;
                        source = 'config';
                    elseif ischar(val)
                        source = ['config (string: "' val '")'];
                    end
                end
            end

            % 如果 config 里没有，尝试从 results 里找
            if isnan(pixel_val) && ismember('results', var_names)
                loaded = load(mat_path, 'results');
                res = loaded.results;
                % 有些旧版本可能存在 results.pixel_size
                if isfield(res, 'pixel_size') && isnumeric(res.pixel_size)
                    pixel_val = res.pixel_size;
                    source = 'results';
                end
            end

            px_m(i) = pixel_val;
            px_um(i) = pixel_val * 1e6;
            sources{i} = source;

        catch ME
            sources{i} = ['error: ' ME.message];
        end

        % 打印
        if ~isnan(px_m(i))
            fprintf('  [%d/%d] %s / %s\n', i, n, groups{i}, phases{i});
            fprintf('         pixel_size = %.2f μm/px  (%.2e m/px)  [%s]\n', ...
                px_um(i), px_m(i), sources{i});
        else
            fprintf('  [%d/%d] %s / %s\n', i, n, groups{i}, phases{i});
            fprintf('         pixel_size = *** 未找到 ***  [%s]\n', sources{i});
        end
    end

    % 构建 table
    T = table(groups, phases, out_folders, px_um, px_m, sources, mat_paths, ...
        'VariableNames', {'Group', 'Phase', 'OutputFolder', ...
                          'PixelSize_um', 'PixelSize_m', 'Source', 'MatFile'});

    fprintf('\n========================================================\n');
    fprintf('  汇总: %d 组实验\n', n);
    valid = ~isnan(px_m);
    fprintf('  有效 pixel_size: %d 组\n', sum(valid));
    if any(valid)
        fprintf('  范围: %.2f – %.2f μm/px\n', min(px_um(valid)), max(px_um(valid)));
    end
    fprintf('========================================================\n\n');

    % 显示 table
    disp(T(:, {'Group', 'Phase', 'PixelSize_um', 'Source'}));
end
