# 代码改动总结 — Dual-reference / CAD 对齐（2026-05-29）

本次会话围绕"DNAPL 饱和度被严重低估"的排查，做了 4 项代码改动 + 1 个新诊断工具。
所有改动**默认行为不变**（新功能均为 opt-in 或仅在已有路径触发），并通过 `checkcode`
静态检查；投影变换另做了数值正确性验证。

工作树根：`.worktrees/interpolation-assisted-segmentation-20260527/`

---

## 改动总览

| # | 文件 | 类型 | 摘要 |
|---|------|------|------|
| 1 | `segmentation/extract_flow_domain.m` | 新功能 | DXF 控制点对齐新增**投影变换 (homography)** 选项 |
| 2 | `segmentation/extract_flow_domain.m` | **Bug 修复** | `load_flow_domain_mask_override` 的 `nargin` 差一错误丢弃了 `ref_image` |
| 3 | `config_pipeline.m` / `utilities/validate_config.m` | 配置 | 新增并校验 `flow_domain.dxf_transform_model` |
| 4 | `segmentation/segment_DNAPL.m` | 新功能 | dual-reference 新增**全局双色端点** `global_water_baseline`（摆脱逐像素配准） |
| 5 | `tools/diagnose_dual_reference_frame.m` | 新文件 | Layer-2 颜色/光照诊断脚本 |

---

## 1. DXF 控制点：投影变换 (homography) 选项

**问题**：`compute_dxf_affine` 是 6 自由度仿射，无法表达透视/镜头畸变。控制点残差在
仿射模型下若卡在高位（如 ~40px），再精确手点也降不下去。

**改动文件**：`segmentation/extract_flow_domain.m`

| 位置 | 内容 |
|------|------|
| `rasterize_dxf_control_points_mode` (≈L701–783) | 读取 `dxf_transform_model`（≈L742），按 `affine` / `projective` 分支选择变换与栅格化；info 增加 `dxf_transform_model` 字段（L777）；未知值报错（L760） |
| `compute_dxf_projective` (L907–) | 新增：带 Hartley 归一化的 DLT 单应估计 |
| `normalize_points_2d` (L943–) | 新增：点集归一化（质心 0、均距 √2） |
| `project_points_homography` (L956–) | 新增：单应投影（含 w 透视除法） |
| `rasterize_circles_projective` (L1003–) | 新增：按圆心局部雅可比近似椭圆栅格化 |
| `homography_jacobian` (L1038–) | 新增：投影映射在 (x,y) 处的 2×2 雅可比 |
| `rasterize_polyline_projective` (L1053–) | 新增：单应下的多边形栅格化 |

**启用**：
```matlab
config.flow_domain.dxf_transform_model = 'projective';   % 默认 'affine'
```

**验证**：用已知 homography 生成点，DLT 精确拟合 residual ≈ 6.8e-14 px，H 恢复误差 ≈ 3e-14（机器精度）。

---

## 2. Bug 修复：`ref_image` 被错误丢弃（控制点弹窗无法触发）

**问题**：`load_flow_domain_mask_override` 有 5 个形参（第 5 个是 `ref_image`），但守卫写成
`if nargin < 6`。调用时传 5 个实参（`nargin=5`），`5 < 6` 为真 → `ref_image` 被重置为 `[]`，
导致 control_points 模式找不到参考图而报错。bbox 模式不用 `ref_image`，所以此 bug 长期潜伏。

**改动文件**：`segmentation/extract_flow_domain.m`
- L313：`if nargin < 6` → `if nargin < 5`

同链路其他守卫（`read_mask_override`、`rasterize_dxf_solid_mask`，均 4 参配 `nargin < 4`）核对无误。

---

## 3. 配置项：`flow_domain.dxf_transform_model`

**`config_pipeline.m`**
- L94–98：新增默认值 `config.flow_domain.dxf_transform_model = 'affine';`（含注释说明 affine/projective 含义）

**`utilities/validate_config.m`**
- L210、L803：两处默认值块新增 `set_default(..., 'dxf_transform_model', 'affine')`
- L1073–1081：新增取值校验（仅允许 `affine` / `projective`，否则报错；归一化为小写）

---

## 4. dual-reference：全局双色端点 `global_water_baseline`

**问题**：水参考、NAPL 参考、当前帧来自**独立采集**时无法逐像素配准。原 `robust_global`
回退只把**端点向量**全局化，`delta = frame − water_feature` 仍用**逐像素水参考**，配准误差
继续通过水基线漏入 → frac 被污染（实测 invalid endpoint 20%、满 NAPL 自检 Sn 仅 0.226）。

**改动文件**：`segmentation/segment_DNAPL.m`

| 位置 | 内容 |
|------|------|
| `global_dual_endpoint` (L1018) | 签名新增返回值 `global_water`（标量鲁棒水色，函数内已计算） |
| `segment_dual_reference` (L372–398) | 新增 `water_baseline`；当 `global_water_baseline=true` 时计算全局端点，把 `endpoint_vec/den/distance` 广播成整图全局值、`water_baseline` 取标量 `global_water`，`delta` 改用它（L398）；`endpoint_mode_used='global_two_color'` |
| `dual_reference_options` (L822) | 默认 `'global_water_baseline', false` |
| `dual_reference_options` (L854–855) | 从 `config.segmentation.dual_reference` 读取该字段 |

**效果**：打开后为**纯双色投影**（标量水色 + 标量 NAPL 色），frac 不再依赖逐像素配准；
`invalid_endpoint_fraction` 退化为纯诊断指标。

**启用**：
```matlab
config.segmentation.dual_reference.global_water_baseline = true;   % 默认 false
```

---

## 5. 新文件：Layer-2 颜色/光照诊断脚本

**文件**：`tools/diagnose_dual_reference_frame.m`（新增）

只读已有产物（不重跑预处理），从 `results.segmentation.info` + `results.flow_domain` +
config 校准读取，输出 6 联诊断图 + 文字判读，自动区分四种低估成因：
1. 光照倾斜（中心/边缘 frac 差异）
2. 端点退化（水/NAPL 参考在 Lab 中过近）
3. 全局欠拟合（frac p95 仍低于阈值）
4. 截断（大量 raw frac < 0 / > 1）

**用法**：
```matlab
diag = diagnose_dual_reference_frame('outputs\<run>\results_*.mat');
```

**已知局限**：`endpoint dist` 面板需要完整的 `water_lab`/`reference_lab`，而 `results.mat`
默认只存精简 manifest 块，离线读取时该面板显示 NaN（不影响其余判读，关键的
`invalid_endpoint_fraction` 等仍来自 seg_info）。

---

## 验证情况

- `checkcode`：`extract_flow_domain.m`、`segment_DNAPL.m`、`validate_config.m`、
  `config_pipeline.m`、`tools/diagnose_dual_reference_frame.m` 均无实质告警。
- 投影变换：独立数值用例确认 DLT 精确恢复已知 homography（残差 ~1e-14 px）。
- 实跑（baseline_check_01，affine + per-pixel）：CAD residual=19.71px、porosity 43.2%
  ≈ 期望 42.6%（CAD 层已收口）；诊断定位根因为参考图未配准（待用 `global_water_baseline` 复跑验证）。

---

## 尚未改动 / 后续可选

- `global_water_baseline` 的合成数据回归用例尚未加入 `tests/`。
- 诊断脚本的 endpoint-distance 面板离线可用性（需在 `results.mat` 持久化校准 Lab，或改为实时计算）。
