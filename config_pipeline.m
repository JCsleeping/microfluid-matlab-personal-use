function config = config_pipeline(varargin)
% CONFIG_PIPELINE  Returns default configuration for the DNAPL analysis pipeline.
%
%   config = config_pipeline()
%   config = config_pipeline('param1', value1, 'param2', value2, ...)
%
%   Override defaults by passing name-value pairs. Nested fields use dot
%   notation strings, e.g. config_pipeline('physical.pixel_size', 5e-6).

    %% Ensure all subdirectories are on the MATLAB path
    this_dir = fileparts(mfilename('fullpath'));
    addpath(genpath(this_dir));

    %% ====================================================================
    %  USER SETTINGS — 只需修改这一个区域
    %  ====================================================================
    %
    %  以下是你每次实验需要核对/修改的参数。
    %  其余参数（算法参数）在下方"高级设置"区域，通常不需要改动。

    % --- 数据路径 ---
    config.data_path = 'D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\01 databased\02 Pretest 4\02 Water Dis';
    %   ↑ 实验数据所在目录。下面的 TIF 路径基于此目录。

    % --- 输入文件 (自动扫描目录中所有 .tif 文件) ---
    tif_list = dir(fullfile(config.data_path, '*.tif'));
    if isempty(tif_list)
        error('config_pipeline:noTIF', ...
            ['No .tif files found in:\n  %s\n' ...
             'Please set config.data_path to the folder containing your TIF files.\n' ...
             'Example: config.data_path = ''...\\01 databased\\01 Pretest 5\\03 Water Dis'';'], ...
            config.data_path);
    end
    [~, date_order] = sort([tif_list.datenum]);  % 按文件修改日期排序（从早到晚）
    tif_list = tif_list(date_order);
    config.multipage_tif_path = arrayfun(@(f) fullfile(f.folder, f.name), ...
        tif_list, 'UniformOutput', false);
    %   ↑ 自动读取 data_path 下所有 .tif，按文件日期从早到晚排序
    %   ↑ 如需手动指定，改为 config.multipage_tif_path = {'path1.tif'; 'path2.tif'};

    % --- 分析页面 ---
    config.pages = [];   % [] = 全部页; [1,10,72] = 指定页（合并后的全局页号）
    %   ↑ 多TIF时，页号为合并后的连续编号（第1个TIF的页+第2个TIF的页+...）
    %   ↑ 内存不足时用子采样: config.pages = 1:10:1500  → 每10帧取1帧
    %   ↑ 每帧约 14 MB (2048×2448×3)，500帧 ≈ 7 GB，建议不超过 300 帧

    % --- 物理参数 (必填) ---
    config.physical.pixel_size       = 'calibrate';   % [m/pixel] 每像素物理尺寸
    %   ↑ 填数字: 直接使用该值
    %   ↑ 填 'calibrate': 首次弹窗让你画线量通道宽度，自动计算 pixel_size
    config.physical.channel_width_um = 400;     % [μm] 进出口通道物理宽度（来自CAD: 0.4 mm）
    %   ↑ 配合 pixel_size='calibrate' 使用
    config.physical.diffusion_coeff  = 0.43e-9;   % [m^2/s]   分子扩散系数
    config.physical.solubility       = 4;      % [mg/L]    水溶解度
    config.physical.dnapl_density    = 1038;   % [kg/m^3]  DNAPL密度
    config.physical.depth            = 20e-6;  % [m]       通道深度
    %   ↑ 示例: TCE → pixel_size=5e-6, diffusion=8.5e-10, solubility=1100,
    %           density=1460, depth=50e-6

    % --- 时间 ---
    config.time_interval = 1;   % [s] 帧间固定时间间隔; [] = 用time_vector
    %   ↑ 设置后自动生成 time_vector = [0, dt, 2*dt, ...]
    %   ↑ 示例: 每3秒一帧 → config.time_interval = 3;
    config.time_vector = [];  % [] = 自动生成 [0,1,2,...]; 或手动 [0,60,120,...]
    %   ↑ time_interval 优先; 若都为空则自动 [0,1,2,...]

    % --- 旋转与裁剪 ---
    config.preprocess.rotation_angle = 0;   % 0 = 不旋转; [] = 自动检测; -45 = 手动
    %   ↑ 芯片本身就是45°设计，默认不旋转。如需旋转校正再改
    config.preprocess.manual_crop_rect = 'interactive';
    %   ↑ 'interactive' = 弹窗画多边形选择芯片区域（推荐首次使用）
    %   ↑ [] = 自动检测芯片区域
    %   ↑ [x,y,w,h] = 直接指定裁剪区域（像素坐标）
    %   ↑ 确定区域后可把坐标写死，避免每次重新选择

    % --- 流域参考 (DNAPL饱和图，用于检测柱子) ---
    config.flow_domain_frame = 1;  % 备用: 从实验帧中取（仅当 flow_domain_image 为空时生效）
    config.flow_domain_image = 'D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\01 databased\00 Saturation\1BD NAPL SATURATION1_2.tif';  % ← 填入DNAPL饱和图路径（粉色DNAPL + 白色柱子）
    %   ↑ 推荐: 用DNAPL饱和帧，柱子(白)与DNAPL(粉)颜色对比度最高
    %   ↑ 不推荐: 水饱和图/干净图（柱子与孔隙灰度对比度太低，检测失败）
    %   ↑ '' = 使用实验帧 flow_domain_frame 指定的帧
    config.flow_domain_image_page = 1;  % 多页TIF取哪一页
    config.flow_domain_crop_rect = [];  % [] = 弹窗画多边形; [x,y,w,h] = 指定裁剪

    %% ====================================================================
    %  ADVANCED SETTINGS — 高级设置（通常不需要修改）
    %  ====================================================================

    % --- 输入模式 (一般不改) ---
    config.input_mode = 'multipage_tif';  % 'multipage_tif' | 'separate_files'
    config.image_dir = '';                % separate_files模式: 图像目录
    config.image_files = {};              % separate_files模式: 文件路径列表

    % --- 输出路径 ---
    %   每次运行自动创建带时间戳的新文件夹，放在图片同目录下，不会覆盖旧结果
    config.output_path = fullfile(config.data_path, ['output_' datestr(now, 'yyyymmdd_HHMMSS')]);

    % --- 预处理 ---
    config.preprocess.auto_rotate       = false;
    config.illumination.method      = 'morphological'; % 'morphological' | 'polynomial'
    config.illumination.kernel_size = 'interactive';   % 'interactive' = 弹窗对比10种; 50 = 直接用
    %   ↑ 'interactive': 显示 kernel 10~100 的对比图，选最好的
    %   ↑ 数字 (如50): 直接使用该kernel大小，不弹窗
    config.registration.method    = 'none';             % 'none' = skip (default); 'intensity' = intensity-based alignment
    config.registration.transform = 'similarity';      % 'translation' | 'similarity' | 'affine'

    % --- 分割 ---
    config.segmentation.color_space    = 'Lab';    % 'Lab' | 'HSV'
    config.segmentation.target_channel = 'a';      % 'a' (Lab) | 'H' (HSV)
    config.segmentation.method         = 'gmm_v2';    % 'gmm' | 'otsu' | 'adaptive' | 'gmm_v2' | 'otsu_v2'
    %   ↑ 'gmm_v2' / 'otsu_v2' = 多次分割叠加法（自动回收DNAPL内部黑点）
    config.segmentation.num_components = 2;         % GMM 组分数
    config.segmentation.min_blob_area  = 10;        % 最小液滴面积 [像素]
    config.segmentation.morph_radius   = 2;         % 形态学运算半径
    config.segmentation.hole_fill_radius = 3;       % v2: 暗点最大直径 [像素]（形态学重建腐蚀半径）

    % --- 界面分析 ---
    config.interface.solid_dilation = 1;  % 固体膨胀像素数

    % --- 传质模型 ---
    config.physical.sherwood_correlation = 'powers'; % 'powers' | 'wilson' | 'interfacial'

    % --- 可视化 ---
    config.visualization.show_figures  = true;
    config.visualization.save_figures  = true;
    config.visualization.figure_format = 'png';    % 'png' | 'svg' | 'fig'
    config.visualization.colormap_blobs = 'jet';

    % --- Parallel processing (requires Parallel Computing Toolbox) ---
    config.parallel.enabled = false;        % true: 使用 parfor 多核并行处理帧

    %% ---- Apply user overrides (do not modify below) -----------------------
    for k = 1:2:numel(varargin)
        field_path = varargin{k};
        value      = varargin{k+1};
        config     = setfield_nested(config, field_path, value);
    end

    %% Validate configuration
    config = validate_config(config);
end

% -------------------------------------------------------------------------
function s = setfield_nested(s, field_path, value)
    tokens = strsplit(field_path, '.');
    if numel(tokens) == 1
        s.(tokens{1}) = value;
    else
        sub = s.(tokens{1});
        sub = setfield_nested(sub, strjoin(tokens(2:end), '.'), value);
        s.(tokens{1}) = sub;
    end
end
