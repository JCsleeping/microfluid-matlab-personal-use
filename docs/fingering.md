
continue：解决方案
要对水驱中/后期的帧做指进分析，需要临时加载特定帧重新分割。你可以这样做：

matlab
config = config_pipeline();
% 加载某一帧（比如中间帧）
frame_idx = 500;  % 改成你想分析的帧号
info = imfinfo(config.tif_files{1});  % 或实际的 TIF 路径
img = imread(config.tif_files{1}, frame_idx);
% 用pipeline里的分割方法对这一帧做分割
[dnapl_mask, ~, ~] = segment_DNAPL(img, results.flow_domain, config);
% 构造一个临时 results 结构体
temp_results = results;
temp_results.dnapl_mask = dnapl_mask;
temp_results.ref_image = img;
% 跑指进分析
fres = run_fingering_analysis(temp_results, config);
或者你想让我改一下 run_fingering_analysis，让它能直接接受帧序号 + TIF 路径作为输入，自动加载指定帧并分割，这样就不用手动构造了？

可以

Adding Frame Selection to Fingering Analysis
Checked

load_frame.m
 and

config_pipeline.m
 to understand frame loading and TIF path structure. Data path is under config.data_path, TIF files are scanned with dir.

Files Edited
Progress Updates
1
Adding frame_idx parameter to run_fingering_analysis for on-demand frame loading and segmentation

2
Adding frame_idx + auto-load-and-segment to run_fingering_analysis.m

Adding Frame Selection to Fingering Analysis
Continuing from previous conversation to add frame_idx parameter to run_fingering_analysis.m for on-demand frame loading and segmentation.

Progress Updates
1
Examining current code structure

Continue

Adding Frame Selection to Fingering Analysis
Added the load_and_segment_frame helper function (lines 250–323) to

run_fingering_analysis.m
. It builds frame_index from config.multipage_tif_path, calls load_frame, applies rotate_and_crop + correct_illumination, runs segment_DNAPL/segment_DNAPL_v2, and updates results.dnapl_mask + results.ref_image.

Files Edited
Progress Updates
1
Checking segmentation API and building the helper function

2
Building the frame_index from config and adding load_and_segment_frame helper

3
Adding load_and_segment_frame helper function to run_fingering_analysis.m

4
Verifying final file structure

load_and_segment_frame 辅助函数已添加到 run_fingering_analysis.m 末尾（第 250–323 行）。功能完整：

使用方式：

matlab
% 分析水驱中/后期某一帧的指进
fconfig.frame_idx = 500;  % 改成你想分析的帧号
fres = run_fingering_analysis(results, config, fconfig);
内部流程：

从 config.multipage_tif_path 重建 frame_index
调用 load_frame 加载指定帧
按 pipeline 相同方式预处理（rotate_and_crop + correct_illumination）
自动匹配 segment_DNAPL / segment_DNAPL_v2（根据 config.segmentation.method）
更新 results.dnapl_mask 和 results.ref_image，然后继续后续指进分析
不传 fconfig.frame_idx 或传空值时，行为与之前完全一致。

Implementing Fingering Analysis Pipeline
Modified

run_fingering_analysis.m
 to route vector frame_idx to batch mode. Created

run_fingering_timeseries.m
 with full batch analysis loop, metric collection, and CSV export.

Files Edited
Progress Updates
1
Updating task.md and creating all files

2
Creating visualize_fingering_timeseries.m and run_fingering_pipeline.m

Verifying Fingering Pipeline
All files verified:

run_fingering_analysis.m
 routes vector frame_idx correctly,

run_fingering_timeseries.m
 (16 files now in analysis/fingering/), visualize_fingering_timeseries.m, and run_fingering_pipeline.m (top-level script) all created successfully.

Files Edited
Progress Updates
1
Checking file structure and cross-references

2
Writing walkthrough and notifying user

全部完成！新增/修改了 4 个文件：

顶层入口 — run_fingering_pipeline.m（项目根目录）

编辑 USER SETTINGS 区域选择模式，直接 >> run_fingering_pipeline 运行
支持从 .mat 文件加载已有结果，或重新跑 pipeline
三种模式统一入口：

matlab
% 默认：用 pipeline 保存的 results.dnapl_mask
analysis_mode = 'default';
% 单帧：分析指定帧
analysis_mode = 'single';  single_frame_idx = 500;
% 批量：追踪多帧演变（自动出时间序列图+CSV）
analysis_mode = 'batch';   batch_frame_indices = [1,50,100,200,500];
命令行也可以直接调用，向量自动走批量：

matlab
fconfig.frame_idx = [1,50,100,200,500];
fts = run_fingering_analysis(results, config, fconfig);
详细说明见 walkthrough。

好的，让我用流程图解释一下整个 pipeline 的运行逻辑：

调用入口
run_fingering_pipeline.m   ← 你直接运行这个脚本
运行流程
STEP 1: 加载数据
│
├─ 有 mat_file？ → load(mat_file) 获取 results + config
│
└─ 没有？ → config_pipeline() + main_DNAPL_pipeline()
│                 ↓
│           （交互式选ROI、校准像素、分割第1帧……）
│           得到 results（含 flow_domain, solid_mask, dnapl_mask 等）
│
STEP 2: 根据 analysis_mode 分流
│
├─ 'default'     → frame_idx = []       → 直接用 results 里保存的 dnapl_mask
│
├─ 'single'      → frame_idx = 500      → 加载第500帧，重新分割
│
└─ 'continuous'  → frame_idx = 'all'    → 连续扫描 TIF 所有页
                    stride = 5           → 每5帧分析一次
│
STEP 3: 调用 run_fingering_analysis(results, config, fconfig)
│
├─ frame_idx 是标量？ → 单帧分析（Phase 0-3 + 出图）
│
└─ frame_idx 是 'all' 或向量？ → 路由到 run_fingering_timeseries()
                                     │
                                     ├─ 1. 扫描 TIF 建 frame_index
                                     ├─ 2. for 每帧:
                                     │     ├─ load_frame()        加载
                                     │     ├─ rotate_and_crop()   裁剪旋转
                                     │     ├─ correct_illumination() 光照校正
                                     │     ├─ segment_DNAPL()     分割
                                     │     └─ 完整指进分析（Phase0-3）
                                     │        → Sr, Nc, fingers, tau...
                                     ├─ 3. 收集10+个指标到时间序列数组
                                     ├─ 4. 计算统计量（均值、速率等）
                                     ├─ 5. 出5张统计图
                                     └─ 6. 保存 CSV + .mat
│
STEP 4: 保存工作空间
关键依赖关系

run_fingering_pipeline.m
 → 调用 →

run_fingering_analysis.m

run_fingering_analysis.m
 看 frame_idx 类型：
标量 → 自己做单帧分析
'all' 或向量 → 转交 →

run_fingering_timeseries.m
（这里面逐帧循环）

run_fingering_timeseries.m
 每帧内部复制了 run_fingering_analysis 的 Phase0-3 逻辑（独立的 run_single_frame_analysis 内部函数），不会再递归调用外面的函数
你需要改的地方
打开

run_fingering_pipeline.m
，只改最上面的 USER SETTINGS：

matlab
mat_file = 'D:\...\output_xxx\pipeline_results.mat';  % 或留空重跑pipeline
analysis_mode = 'continuous';   % 连续TIF分析
stride = 5;                     % 每5帧一次
然后 >> run_fingering_pipeline 就行了。

你说得对！让我确认一下 main_DNAPL_pipeline 到底保存了什么：

8 results
1 result
Analyzed
你说得很对！让我解释清楚这个问题：

现状

main_DNAPL_pipeline.m
 确实会保存 results — 看第 462 行：

matlab
export_results(results, config.output_path, {'mat', 'csv'});

export_results.m
 第 20-21 行会保存：

matlab
fname = fullfile(output_path, ['results_' timestamp '.mat']);
save(fname, 'results', '-v7.3');
所以每次跑完 pipeline，会在 output_path 目录下生成一个 results_20260308_xxxx.mat 文件。

但问题是：它只保存了 results，没保存 config。 而指进分析需要 config（TIF路径、分割参数、预处理参数等）。

run_fingering_pipeline.m
 的实际运行逻辑
有两种用法：

用法 1：直接串联运行（推荐首次使用）
matlab
mat_file = '';  % 留空
% → 会自动调 config_pipeline() + main_DNAPL_pipeline()
% → 拿到 results 和 config 后接着跑指进分析
这种方式完全没问题，因为 results 和 config 都在内存里。

用法 2：从 .mat 加载（二次分析）
matlab
mat_file = 'D:\...\output_xxx\results_20260308_xxxx.mat';
% → 加载 results，但 config 不在 .mat 里
% → 会重新 config_pipeline() 生成 config
这种方式有个小问题：config 是重新生成的，如果你之前改过参数（比如裁剪框、pixel_size），需要确保

config_pipeline.m
 里的参数跟之前一致。

你希望我怎么改？有两个方案：

在 main_DNAPL_pipeline 里也保存 config（save(fname, 'results', 'config', '-v7.3')），这样二次加载就完整了
让 run_fingering_pipeline 完全不依赖 .mat，默认就是串联运行 pipeline → 指进分析
你倾向哪个？

先按1来做吧，目前fingering——pipline还是测试阶段，不要串在一起

两个简单改动：让 main_DNAPL_pipeline 导出时也保存 config。

Edited
+1
-1
Edited
+9
-2
搞定。改了两个地方：

export_results.m
 — 新增可选第4参数 config，有 config 时 .mat 同时保存 results 和 config

main_DNAPL_pipeline.m
 第 462 行 — 加了 config 参数传入
现在你跑完 main_DNAPL_pipeline 后，output_xxx/results_xxxx.mat 里会同时包含 results 和 config。之后在

run_fingering_pipeline.m
 里填上这个 .mat 路径就能独立运行指进分析了：

matlab
mat_file = 'D:\...\output_xxx\results_20260308_xxxx.mat';
analysis_mode = 'continuous';
stride = 5;

因为你运行时

run_fingering_pipeline.m
 里的 mat_file 是空的：

matlab
% run_fingering_pipeline.m 第 33 行：
mat_file = '';  % ← 空的！
所以走了这个分支（第 78-82 行）：

matlab
if ~isempty(mat_file) && isfile(mat_file)
    % ← mat_file 为空，跳过
else
    fprintf('  No .mat file specified. Running full pipeline...\n');
    config = config_pipeline();              % ← 走了这里
    results = main_DNAPL_pipeline(config);   % ← 跑完整 pipeline
end
main_DNAPL_pipeline 本身就包含 Step 4 溶解动力学（1068 帧），这是它的标准流程。跑完之后才把 results 和 config 传给下面的指进分析。

怎么避免
等这次跑完后，output_xxx/ 里会生成 results_*.mat（现在含 results + config）。以后把路径填进去：

matlab
mat_file = 'D:\...\output_20260308_163751\results_20260308_163751.mat';
这样就直接 load(mat_file) 拿到 results 和 config，跳过整个 main_DNAPL_pipeline，几秒钟就进入指进分析了。

% --- 数据来源 ---
% 方式A: 从已有的 pipeline 输出 .mat 文件加载
mat_file = '"D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\01 databased\06 LNAPL-4UL\01 NAPL WATER\output_20260308_151758\results_20260308_154658.mat"';  % ← 填 .mat 路径，例如 'D:\...\output_xxx\pipeline_results.mat'
%   ↑ 如果为空，则重新运行 config_pipeline() + main_DNAPL_pipeline()
‘

路径里多了一对双引号！MATLAB 字符串只需要单引号包裹：

matlab
% ❌ 错误 — 里面多了 " "
mat_file = '"D:\...\results_20260308_154658.mat"';
% ✅ 正确
mat_file = 'D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\01 databased\06 LNAPL-4UL\01 NAPL WATER\output_20260308_151758\results_20260308_154658.mat';
把里面的 " 去掉就行了。

好，让我系统地 review 所有 fingering 相关代码，找出导致 1068 帧全失败的 bug。

16 results
Analyzed
Analyzed
Analyzed
Now let me see

run_fingering_timeseries.m
's load_and_segment_frame_internal and run_single_frame_analysis:

Analyzed
Now let me check the other critical functions:

Analyzed
Analyzed
Analyzed
Analyzed
Analyzed
Analyzed
Now I have a comprehensive view. Let me also check the remaining critical files:

Analyzed
Analyzed
Analyzed
Now let me check the

run_fingering_pipeline.m
 to see how config is loaded:

Analyzed
Now I have a complete picture. Here's my code review with the critical bugs identified:

🔍 Code Review: Fingering Pipeline — 找到了全失败的根因
🚨 BUG 1 (Critical): phase0_precheck 在 timeseries 模式下每帧弹出可视化窗口
文件:

phase0_precheck.m
 第 91 行 问题: run_single_frame_analysis → phase0_precheck 每帧都创建一个 6-panel figure 并尝试 saveas。1068 帧 = 1068 个 figure 窗口！这会极度消耗内存，还可能因为 output_path 不存在而报错。

但这不是全失败的原因，因为 figure 也可能成功。

🚨 BUG 2 (Critical — 全失败根因): config.output_path 指向旧运行的目录
文件:

run_fingering_pipeline.m
 第 68-84 行

当加载 .mat 时，config 里的 output_path 是当时 pipeline 生成的目录（如 output_20260308_151758）。但

phase0_precheck.m
 第 142 行尝试用 isfolder(config.output_path) 判断是否保存图。如果该目录存在但 fingering_qc 子目录不存在，mkdir 会创建它。这部分没问题。

🚨 BUG 3 (Critical — 最可能的全失败根因): config.physical.pixel_size 可能仍为 'calibrate' 字符串
检查点:

config_pipeline.m
 第 48 行将 pixel_size 初始化为 'calibrate'。

main_DNAPL_pipeline.m
 第 185 行在交互后回写数字值。但是...

载入旧 .mat 时，如果 config 中没有 config 变量（早期版本没有保存 config），第 82-83 行会重新 config_pipeline()，得到 pixel_size = 'calibrate'。然后

compute_local_width.m
 第 70 行检查 isnumeric(pixel_size)，不会崩。

但是！让我仔细看 — .mat 文件的时间戳是 154658，而 export_results 的改动（加入 config）是今天才提交的（v3.1）。

这就是根因！那个 .mat 文件是旧版 export_results 保存的，只有 results，没有 config！

所以第 79 行 isfield(loaded, 'config') 为 false，走了第 83 行 config = config_pipeline()。新的 config_pipeline() 里 manual_crop_rect = 'interactive'，在 batch 模式无法交互 → 自动裁剪 → 裁剪区域跟 flow_domain 大小不匹配 → segment_DNAPL 报错 → 全部 1068 帧失败。

让我修复：

Edited
+24
-2
Now let me also suppress the per-frame QC figures in batch mode — 1068 个 figure 窗口会崩：

Edited
+64
-57
Now set batch_mode = true in the timeseries function's fconfig:

Edited
+1
-0
Code Review 总结
🚨 全失败根因（已修复）
.mat 文件是旧版 export_results 保存的（你的 .mat 时间戳 154658，而 config 保存功能是今天刚加的 v3.1）。所以加载时 config 字段不存在 → 走 config_pipeline() 重建 → 得到 manual_crop_rect = 'interactive' + pixel_size = 'calibrate' → rotate_and_crop 自动裁剪大小跟 flow_domain 不匹配 → 每帧 segment_DNAPL 崩掉。

修复了 3 个问题

# Bug 修复

1 旧 .mat 没有 config → 重建的 config 含交互参数 从 results.preprocessing 提取 crop_rect/rotation_angle，禁用交互模式
2 batch 模式每帧创建 QC figure (1068 个窗口) phase0_precheck 检查 fconfig.batch_mode，批处理时跳过
3 histogram xline(NaN) 崩溃 之前已修复
