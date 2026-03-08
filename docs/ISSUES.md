# ISSUES — DNAPL 图像分析流水线

> 此文件记录所有已知问题、待办事项和更新日志。每次会话结束前更新。

---

## 当前状态

- **版本**: v3.0
- **最后更新**: 2026-03-03
- **总文件数**: 28 个 .m 文件 + 4 个 .md 文件
- **输入模式**: 多页 TIF + 独立文件模式
- **默认数据**: 02 Pretest 4 / 01 NAPL WATER (3 TIF, 145 页, 1s/帧)
- **新增功能**: 多次分割叠加 v2, 流式帧加载, 子图独立保存

---

## 已完成

- [x] 项目目录结构建立
- [x] 配置系统 (`config_pipeline.m`)
- [x] 预处理模块：旋转校正、光照校正、帧间配准
- [x] 分割模块：流域提取、DNAPL 分割（Lab a* + GMM）、形态学清洗
- [x] 分析模块：饱和度、液滴几何、界面分析、传质速率、溶解动力学
- [x] 可视化模块：5 个出版质量图形生成器
- [x] 工具模块：图像加载、结果导出
- [x] 主控脚本 (`main_DNAPL_pipeline.m`)
- [x] 多页 TIF 支持 (`read_multipage_tif.m`, `characterize_solubilization_v2.m`)
- [x] 16-bit TIF 支持（所有 imread 入口均处理 uint16 → uint8）
- [x] 文件重新分发至 `01 MATLAB CODE/01 Microfluid/`
- [x] 中文技术报告和使用指南
- [x] CLAUDE.md 项目概览
- [x] 删除 OneDrive 不兼容文件 (`_ul`)
- [x] 删除过时文件 (`Overview.ini`)
- [x] pixel_size 交互式标定
- [x] 分割可视化遮罩改进
- [x] 小柱子检测阈值优化 (MIN_BLOB_AREA 降至 2/3)
- [x] 子图独立保存 (`save_subplots.m`)
- [x] 多次分割叠加法 (`segment_DNAPL_v2.m`, DNAPL 内部黑点回收)
- [x] 流式帧加载 (`load_frame.m`, 内存优化)
- [x] 孔隙率一致性检查 bug 修复
- [x] 预处理量化指标 (SSIM, NCC)

---

## 待优化 / 已知问题

### P1 — 高优先级

- [x] **旋转角度**: 芯片 45 deg 设计, 默认 `rotation_angle = 0`
- [x] **流域提取验证**: 双方法检测 + 面积阈值优化
- [x] **小柱子检测**: 面积阈值 15->5, 20->8, imopen 半径 2->1, CAD 补漏
- [ ] **72 页 TIF 内存占用**: 建议 `config.pages` 指定子集

### P2 — 中优先级

- [ ] **分割参数调优**: GMM 分割在不同光照条件下可能需要调整 `morph_radius` 和 `min_blob_area`。需在实际数据上确定最优参数。
- [ ] **界面长度精度**: 链码法在低分辨率下可能不够精确。可考虑亚像素级边界检测。
- [ ] **传质模型选择**: Powers/Wilson 关联式是经验公式，用户需根据实验体系校准。

### P3 — 低优先级

- [ ] 添加 `parfor` 并行处理支持（需 Parallel Computing Toolbox）
- [ ] 添加图像降采样选项（用于快速预览大图像）
- [ ] 生成 HTML/PDF 自动报告
- [ ] 支持视频输入（.avi, .mp4）
- [ ] 添加 GUI 界面（App Designer）

---

## 文件清单 (v2.9)

```
01 MATLAB CODE/01 Microfluid/
├── main_DNAPL_pipeline.m              主控脚本 (v2.0 - 支持多页TIF)
├── config_pipeline.m                   配置 (v2.7 - 含参数验证)
├── ISSUES.md                           本文件
├── 技术报告.md                          技术报告
├── 使用指南.md                          使用指南
│
├── preprocessing/
│   ├── rotate_and_crop.m               旋转校正
│   ├── correct_illumination.m          光照校正 (v2.7 - 自适应子采样)
│   ├── align_images.m                  图像配准
│   └── select_illumination_kernel.m    交互式 kernel 选择
│
├── segmentation/
│   ├── extract_flow_domain.m           流域提取 (v2.7 - 命名常量)
│   ├── segment_DNAPL.m                 DNAPL 分割 (a* + GMM/Otsu)
│   ├── segment_DNAPL_v2.m              多次分割叠加 (v3.0 新增, 黑点回收)
│   └── refine_mask.m                   形态学清洗
│
├── analysis/
│   ├── calculate_saturation.m          饱和度
│   ├── analyze_blob_geometry.m         液滴几何 (v2.7 - 物理尺寸分类)
│   ├── analyze_interfaces.m            界面分析
│   ├── calculate_mass_transfer.m       传质速率
│   ├── characterize_solubilization.m   溶解动力学 (v1 - DEPRECATED)
│   └── characterize_solubilization_v2.m 溶解动力学 (v2 - 预加载图像)
│
├── visualization/
│   ├── visualize_preprocessing.m       (v2.7 - 空数据保护)
│   ├── visualize_segmentation.m        (v2.7 - 空数据保护)
│   ├── visualize_blobs.m
│   ├── visualize_interfaces.m          (v2.7 - 空数据保护)
│   └── visualize_solubilization.m      (v2.7 - 空数据保护)
│
├── utilities/
│   ├── load_images.m                   单图加载
│   ├── load_frame.m                    按需帧加载 (v3.0 新增, 流式处理)
│   ├── read_multipage_tif.m            多页 TIF 读取 (v2.7 - 内存预估)
│   ├── save_subplots.m                 子图独立保存 (v2.9 新增)
│   ├── validate_config.m              参数验证 (v2.8 - 支持 calibrate)
│   └── export_results.m               结果导出
│
├── tests/
│   ├── test_main_pipeline_clean_ref_auto_crop.m
│   ├── test_extract_flow_domain_robustness.m
│   └── test_core_functions_synthetic.m  (v2.7 新增, 18 测试用例)
│
├── data/output/                        输出目录
│
└── 01 databased/                       实验数据
    └── 01 Pretest 5/
        └── 酒精清洗.tif                72 页多页 TIF (约 1 GB)
```

---

## 数据文件说明

| 文件 | 位置 | 页数 | 说明 |
|------|------|------|------|
| dnapl Test 5 ul min 1 seconds.tif | 01 databased/02 Pretest 4/01 NAPL WATER/ | 72 | DNAPL 注入实验 (默认) |
| dnapl Test 5 ul min 1 seconds_1.tif | 同上 | 72 | 续拍 |
| dnapl Test 5 ul min 1 seconds_2.tif | 同上 | 1 | 续拍 (合计 145 页) |
| 酒精清洗.tif | 01 databased/01 Pretest 5/ | 72 | 酒精清洗实验 (~1 GB) |

---

## 快速运行命令

```matlab
% 导航到项目目录
cd 'D:\00 Claude Code\01 MATLAB CODE\01 Microfluid'

% 使用默认配置（3个TIF合并, 145页, 1s/帧）—— 注意内存！
results = main_DNAPL_pipeline();

% 推荐：只分析部分页面以节省内存
config = config_pipeline('pages', [1, 20, 40, 60, 80, 100, 120, 145]);
results = main_DNAPL_pipeline(config);

% 切换数据集: 只需修改 data_path 和 multipage_tif_path
config = config_pipeline('data_path', 'D:\...\your_data_dir');
config.multipage_tif_path = fullfile(config.data_path, 'your_file.tif');
results = main_DNAPL_pipeline(config);
```

---

## 更新日志

### v2.5 (2026-02-07) — Multi-TIF + Top-Hat Pillar Detection

- **REWRITE** `extract_flow_domain.m`: 全面重写柱子检测算法
  - 从全局 Otsu 改为形态学 top-hat (`imtophat`) 检测局部亮特征
  - 移除圆形度过滤器（柱子为不规则形状）
  - 仅使用面积范围过滤: 30 < area < chip_area * 0.5%
  - 新增 `stdfilt` 纹理方法作为后备
- **FEATURE** `config_pipeline.m`: 新增 `data_path` 参数，TIF 路径基于此目录
- **FEATURE** `config_pipeline.m`: `multipage_tif_path` 支持 cell 数组（多 TIF 合并）
- **FEATURE** `config_pipeline.m`: 新增 `time_interval` 参数（固定帧间时间间隔）
- **FEATURE** `main_DNAPL_pipeline.m`: STEP 0 支持多 TIF 顺序读取 + 合并页号选择
- **FEATURE** `main_DNAPL_pipeline.m`: `time_interval` 自动生成 `time_vector`
- **DATA** 默认数据改为 02 Pretest 4 / 01 NAPL WATER (3 TIF, 72+72+1=145 页, 1s/帧)
- **MIGRATE** 项目从 OneDrive (`C:\Users\ASUS\OneDrive\02 Claude Code`) 迁移到 `D:\00 Claude Code`

### v2.4 (2026-02-07) — Manual ROI + Crop Alignment

- **FEATURE** `config_pipeline.m`: 新增 `preprocess.manual_crop_rect` 参数，支持手动指定芯片 ROI `[x,y,w,h]`
- **FIX** `config_pipeline.m`: `flow_domain_image` 默认改为 `''`（用实验自身帧），避免放缩比例不匹配
- **CRITICAL** `rotate_and_crop.m`: 裁剪优先级: manual_crop_rect > saved_crop_rect > auto-detect；新增 `clip_crop_rect` 辅助函数
- **FIX** `main_DNAPL_pipeline.m`: 参考帧处理后将 `crop_rect` 保存到 `config.preprocess.saved_crop_rect`
- **发现**: Clean chip / Full water 与实验图像放缩比例不同 (柱子间距 26px vs 39px, ~1.5x)，不能直接用作参考

### v2.2 (2026-02-07) — No-Rotation + Robust Flow Domain

- **FIX** `config_pipeline.m`: `rotation_angle` 默认改为 `0`（芯片 45° 设计无需旋转）；`auto_rotate` 默认 `false`
- **FIX** `rotate_and_crop.m`: `angle=0` 时跳过 `imrotate` 调用
- **REWRITE** `extract_flow_domain.m`:
  - 背景检测从硬编码 `gray < 0.2` 改为 Otsu 自适应阈值
  - 只保留最大连通分量作为芯片区域
  - 柱子检测改为在芯片内部单独计算 Otsu（不受背景干扰）
  - 添加空像素保护

### v2.1 (2026-02-07) — Code Review Bugfixes

- **CRITICAL** `visualize_segmentation.m`: 修复 overlay 索引越界（移除死代码，简化为 double 算术叠加）
- **CRITICAL** `visualize_interfaces.m`: 修复 uint8 溢出（改用 double 运算后转 uint8）
- **CRITICAL** `export_results.m`: xlsx 导出添加 `isfield(results.blobs, 'blob_table')` 检查
- **CRITICAL** `rotate_and_crop.m`: 重写 `detect_chip_angle`（移除死代码分支，改用 PCA + snap-to-90° 算法）
- **COMPAT** 4 个文件中 `size(X,[1 2])` 替换为 `size(X,1)/size(X,2)`（兼容 R2019a 以下）
  - `main_DNAPL_pipeline.m`, `characterize_solubilization.m`, `characterize_solubilization_v2.m`, `visualize_preprocessing.m`
- **FIX** `calculate_mass_transfer.m`: 修正单位转换注释（mg/L → kg/m^3）

### v2.0 (2026-02-07)

- 新增多页 TIF 支持（`read_multipage_tif.m`）
- 新增 `characterize_solubilization_v2.m`（接收预加载图像）
- `config_pipeline.m` 新增 `input_mode`, `multipage_tif_path`, `pages` 参数
- `main_DNAPL_pipeline.m` 重写图像加载逻辑，支持双模式
- 默认输入改为 `01 databased/01 Pretest 5/酒精清洗.tif`
- 文件重新分发至 `01 MATLAB CODE/01 Microfluid/`

### v1.0 (2026-02-07)

- 初始版本：20 个 MATLAB 文件
- 支持独立 TIF/PNG 文件输入
- 完整分析流水线（预处理→分割→5项分析→可视化→导出）

### v2.6 (2026-02-10) - Stability Fixes (Crash + Robust Flow Domain)

### v2.7 (2026-02-21) - Validation, Robustness & Testing

- `validate_config.m`, `test_core_functions_synthetic.m`, 命名常量重构, 多项修复（详见 git log）

### v2.8 (2026-03-01) - Pixel Size 标定 + 小柱子检测

**新增功能:**

- `config.physical.channel_width_um = 400`: 通道物理宽度
- `config.physical.pixel_size = 'calibrate'`: 交互画线标定模式

**柱子检测改进:**

- `extract_flow_domain.m`: MIN_BLOB_AREA 15→2/20→3, imopen 半径 2→1

### v3.0 (2026-03-03) - 多次分割叠加 + 流式帧加载

**新增功能:**

- **NEW** `segmentation/segment_DNAPL_v2.m`: 三次分割叠加法，解决 DNAPL 内部黑点漏判
  - Pass 1: a* 通道红色分割 (复用现有 segment_DNAPL)
  - Pass 2: L* 通道低亮度检测 (百分位阈值)
  - Pass 3: 空间约束过滤 (只保留红色区域附近的暗点)
  - 方法名: `'gmm_v2'` / `'otsu_v2'`
- **NEW** `utilities/load_frame.m`: 按需帧加载，支持流式处理
- `config.segmentation.dark_percentile = 10`: 暗点检测百分位阈值
- `config.segmentation.dark_dilate_radius = 5`: 红色掩膜膨胀半径

**内存优化:**

- `main_DNAPL_pipeline.m`: 重构为流式加载（frame_index + load_frame），不再预加载全部帧
- 多 TIF 场景内存从 ~22 GB 降至 ~14 MB/帧
- `config_pipeline.m`: TIF 文件自动扫描 + 日期排序

### v2.9 (2026-03-01) - 子图独立保存 + 代码清理

**新增功能:**

- **NEW** `utilities/save_subplots.m`: 每个可视化自动保存组图 (X-0) + 子图 (X-1~X-6)
- 5 个 `visualize_*.m` 全部改用 `save_subplots` 输出

**移除功能:**

- **DEL** `utilities/register_cad_to_experiment.m`: CAD 辅助验证功能已移除
- **DEL** `config.cad_image_path`: 配置参数已移除

**可视化修复:**

- `visualize_segmentation.m`: a*/概率图仅显示孔隙区域 + imagesc AlphaData 语法修复
- `visualize_preprocessing.m`: 孔隙率分母 bug 修复 + TeX 解析错误修复
- `validate_config.m`: 支持 pixel_size='calibrate'
- `run_dual_comparison.m`: mask 尺寸匹配 + user_overrides 格式修复
- **SAFETY** `read_multipage_tif.m`: 读取前估算内存用量，超过可用 RAM 80% 时发出 warning
- **REFACTOR** `extract_flow_domain.m`: 40+ 个硬编码阈值提取为函数顶部命名常量（`P.MIN_PILLAR_FRAC` 等），通过 `P` struct 传入子函数
- **FIX** `analyze_blob_geometry.m`: Ganglia 分类改用物理面积阈值（singlet<50µm², pool>5000µm²），无 pixel_size 时保留像素阈值 fallback
- **FIX** `export_results.m`: 所有文件写入操作包裹 try-catch，失败时 warning 而非崩溃；跳过数据时打印明确提示
- **FIX** `correct_illumination.m`: 多项式拟合子采样步长从硬编码 10 改为自适应 `max(1, round(min(H,W)/100))`
- **GUARD** 4 个 `visualize_*.m`: 新增空数据 early-return 保护（preprocessing, segmentation, interfaces, solubilization）
- **DEPRECATE** `characterize_solubilization.m` (v1): 添加 deprecation warning，推荐使用 v2

- **CRITICAL FIX** `main_DNAPL_pipeline.m`: 修复 `flow_domain_image` 启用且 `preprocess.manual_crop_rect=[]` 时的索引越界崩溃（`exp_rect(4)` 访问空数组）。
  - 行为变更：当 `manual_crop_rect` 为空时，自动从实验帧推导 `exp_rect`，再对 clean reference 做 resize。
  - 增加 `exp_rect` 合法性检查，避免无效 ROI 静默传播。
- **ROBUSTNESS** `extract_flow_domain.m`: 提升柱子检测鲁棒性，避免出现 `0% pillars`。
  - 当 Lab 颜色法结果异常（过低/过高）时，自动尝试 morphological fallback 并择优采用。
  - 对 L* 分割异常场景新增 quantile fallback，避免“全部 non-DNAPL 合并后被面积过滤清空”。
- **WARN FIX** `extract_flow_domain.m`: 诊断图中将 `contour` 边界绘制替换为 `bwperim + plot`，消除 `Contour not rendered for constant ZData` 警告。
- **TEST** 新增回归测试：
  - `tests/test_main_pipeline_clean_ref_auto_crop.m`（覆盖 clean reference + auto crop 崩溃场景）
  - `tests/test_extract_flow_domain_robustness.m`（覆盖非零柱子比例与 contour 警告场景）

## 推荐配置示例（v2.6 稳定版）

```matlab
% 目标：
% 1) 使用 clean reference 提高 flow domain 稳定性
% 2) manual_crop_rect 使用 [] 自动裁剪（v2.6 已修复崩溃）
% 3) 先抽样页快速检查，再跑全量

config = config_pipeline( ...
    'preprocess.manual_crop_rect', [], ...
    'illumination.kernel_size', 50, ...
    'flow_domain_image', 'D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\01 databased\00 Saturation\1BD NAPL SATURATION1_2.tif', ...
    'flow_domain_crop_rect', [1, 1, 2447, 2047], ...
    'flow_domain_frame', 1, ...
    'pages', [1, 20, 40, 60, 80, 100, 120, 140], ...
    'visualization.show_figures', false, ...
    'visualization.save_figures', true);

results = main_DNAPL_pipeline(config);
```
