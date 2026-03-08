为了帮助你快速建立这个标准化、自动化的实验数据管理系统，我为你设计了详细的 Excel 模板构建指南。

由于我无法直接向你发送一个 .xlsx 文件，我将模板的表头结构、内置公式、下拉菜单设置和图表制作步骤完整列出。你可以直接复制这些内容到你的 Excel 中，或者使用我附在文末的 Python一键生成脚本 直接生成这个 Excel 文件。

📂 工作簿结构建议

建议在一个新建的 Excel 文件中创建以下 4 个工作表（Sheet）：

说明 (ReadMe)：记录公式计算方法、单位说明和文献参考（如Lenormand相图基准）。

列表与参数 (Lists)：用于存放下拉菜单的选项（避免填错）。

数据记录 (Data Record)：核心工作表，逐行记录实验数据。

分析图表 (Analysis Charts)：基于数据透视表和图表的数据可视化看板。

📝 1. “数据记录”表 (Data Record) 结构与公式

请在 “数据记录” 工作表的第一行（A1:P1）设置以下表头，并在第二行（A2:P2）填入你要求的示例数据和公式。

列号	字段名称 (含单位)	示例数据 (第2行)	填写说明与 Excel 内置公式 (在第二行输入的公式)
A	实验编号 (Run ID)	Test1	手动填写（如 Test1, Run-20231024-1）
B	结构类型	均匀	[下拉菜单] 选择：均匀, 梯度减少, 双孔径
C	润湿性/接触角 θ (°)	30	记录真实接触角，亲水<90°，疏水>90°
D	界面张力 σ (mN/m)	72	建议未加表活剂填72，加了填实测值
E	流量 Q (μL/min)	0.5	(可选) 若由泵控制流量，可填入此列辅助计算
F	设定毛细数 Ca (-)	1.00E-05	科学记数法填写。若是根据Q算，可输入公式*
G	log10(Ca) (-)	=-5	[公式] =IFERROR(LOG10(F2),"")
H	驱替相黏度 μ_w (mPa·s)	1.0	水相或驱替相的黏度
I	被驱相黏度 μ_o (mPa·s)	0.6	NAPL/油相或驻留相的黏度
J	黏度比 M (-)	=1.67	[公式] =IFERROR(H2/I2,"")
K	残油饱和度 S_nr (%)	35%	手动填入小数0.35，Excel设置单元格格式为百分比
L	相对渗透率 k_eff (-)	0.45	测得的有效渗透率/绝对渗透率
M	油团块数量 (个)	15	图像处理脚本输出的 num_clusters
N	平均团块面积 (μm²)	3000	图像处理脚本输出的平均面积
O	流型描述	毛细指进(CF)	[下拉菜单] 稳定前锋, 毛细指进(CF), 黏性指进(VF)
P	备注说明	测试用例	记录特殊情况（如：芯片漏液、气泡干扰等）

(注：如果需要通过 Q 计算 Ca，F2的公式可以写为：=IF(E2="","", (H2*E2*转换系数)/(D2*COS(RADIANS(C2))))，具体转换系数根据芯片截面积换算流速而定。)

⚙️ 2. 自动化与数据验证设置 (Data Validation)

为了防止科研人员输入格式错误，建议做以下设置：

下拉菜单限制：

选中 B列 (结构类型)，点击 数据 -> 数据验证 (Data Validation)，允许选择“序列”，来源输入：均匀,梯度减少,双孔径。

选中 O列 (流型描述)，同理，来源输入：稳定前锋,毛细指进(CF),黏性指进(VF),枝状蔓延。

条件格式 (高亮差异)：

选中 K列 (S_nr)，点击 开始 -> 条件格式 -> 色阶，选择绿-黄-红色阶。这样高饱和度会自动泛红，低饱和度泛绿，一眼就能看出脱油效率。

📊 3. “分析图表”表 (Analysis Charts) 绘图指南

在“分析图表”工作表中预建以下三个图，只需随着“数据记录”表的更新，点击“刷新”即可自动更新：

图一：毛细去捕曲线 (CDC Curve) —— S_nr vs. log10(Ca)

插入图表：插入 -> 带平滑线和数据标记的散点图。

数据选择：

X轴系列：'数据记录'!$G:$G (log10(Ca)列)

Y轴系列：'数据记录'!$K:$K (S_nr列)

美化建议：横轴标签设为 log10(Ca)，纵轴设为 S_nr (%)。可在图表中右键数据点，添加“趋势线(多项式或移动平均)”，直观展示临界毛细数（拐点）。

图二：Lenormand 相图 (模式判别图)

插入图表：插入 -> 散点图。

数据选择：

X轴：'数据记录'!$G:$G (log10(Ca))

Y轴：'数据记录'!$J:$J (黏度比 M) —— 注意：如果 M 跨度很大，建议将Y轴设置为对数刻度 (Logarithmic Scale)。

实现分区标记：

将“数据记录”按“流型描述(O列)”拆分成不同系列（例如单独把CF作为一组，VF作为一组）。让CF显示为红色三角形，VF显示为蓝色正方形，Stable显示为绿色圆圈。

手绘边界：使用Excel的 插入 -> 形状 -> 任意多边形/线条，在图表背景上大致画出 Log(M) ≈ 1 和 Log(Ca) ≈ -4 等经典 Lenormand 边界。

图三：多条件 S_nr 柱状对比图 (透视图)

操作：选中“数据记录”所有数据，点击 插入 -> 数据透视图 (PivotChart)。

字段设置：

轴(类别)：拖入 结构类型 或 润湿性(θ)。

值：拖入 残油饱和度 S_nr（注意：点击值字段设置，将“求和”改为**“平均值”**）。

用途：这会自动生成一个柱状图，直观对比“均匀 vs 双孔径”下的平均残余油量。

💻 附加：一键生成该 Excel 模板的 Python 脚本

如果你有 Python 环境，可以直接运行下面这段代码。它会利用 xlsxwriter 和 pandas 瞬间生成一个格式完美、带公式、带下拉菜单、并且列宽调好的 Microfluidic_Experiment_Template.xlsx 文件。

code
Python
download
content_copy
expand_less
import pandas as pd
import xlsxwriter

# 1. 准备示例数据
data = {
    "实验编号 (Run ID)": ["Test1", "Test2"],
    "结构类型": ["均匀", "双孔径"],
    "接触角 θ (°)": [30, 120],
    "界面张力 σ (mN/m)": [72, 72],
    "设定毛细数 Ca (-)": [1.0E-5, 5.0E-4],
    "log10(Ca) (-)": ["", ""], # 留空给Excel公式
    "驱替相黏度 μ_w (mPa·s)": [1.0, 1.0],
    "被驱相黏度 μ_o (mPa·s)": [0.6, 0.6],
    "黏度比 M (-)": ["", ""],   # 留空给Excel公式
    "残油饱和度 S_nr (%)": [0.35, 0.12],
    "有效渗透率 k_eff (-)": [0.45, 0.85],
    "油团块数量 (个)": [15, 3],
    "平均团块面积 (μm²)": [3000, 500],
    "流型描述": ["毛细指进(CF)", "稳定前锋"]
}
df = pd.DataFrame(data)

# 2. 创建Excel写入器
writer = pd.ExcelWriter("Microfluidic_Experiment_Template.xlsx", engine="xlsxwriter")
df.to_excel(writer, sheet_name="数据记录 (Data Record)", index=False)

workbook = writer.book
worksheet = writer.sheets["数据记录 (Data Record)"]

# 3. 设置单元格格式
header_format = workbook.add_format({'bold': True, 'bg_color': '#D9E1F2', 'border': 1, 'align': 'center'})
pct_format = workbook.add_format({'num_format': '0.00%'})
sci_format = workbook.add_format({'num_format': '0.00E+00'})

# 写入表头并调整列宽
for col_num, value in enumerate(df.columns.values):
    worksheet.write(0, col_num, value, header_format)
    worksheet.set_column(col_num, col_num, 16) # 统一列宽

worksheet.set_column('E:E', 15, sci_format) # Ca列用科学计数法
worksheet.set_column('J:J', 15, pct_format) # S_nr列用百分比显示

# 4. 写入Excel内置公式 (从第2行到100行)
for row in range(1, 101):
    # log10(Ca)列 (F列为引用的Ca列, Excel索引F为E)
    worksheet.write_formula(row, 5, f'=IFERROR(LOG10(E{row+1}), "")')
    # M黏度比列 (引用的H和G列)
    worksheet.write_formula(row, 8, f'=IFERROR(G{row+1}/H{row+1}, "")')

# 5. 设置数据验证 (下拉菜单)
worksheet.data_validation('B2:B101', {'validate': 'list', 'source': ['均匀', '梯度减少', '双孔径']})
worksheet.data_validation('N2:N101', {'validate': 'list', 'source': ['稳定前锋', '毛细指进(CF)', '黏性指进(VF)', '枝状蔓延']})

# 6. 添加条件格式 (S_nr 列红黄绿色阶)
worksheet.conditional_format('J2:J101', {'type': '3_color_scale', 
                                         'min_color': '#63BE7B', # 低饱和度绿
                                         'mid_color': '#FFEB84', 
                                         'max_color': '#F8696B'}) # 高饱和度红

# 7. 添加"说明"工作表
readme_sheet = workbook.add_worksheet("说明 (ReadMe)")
readme_sheet.write(0, 0, "微流控 NAPL 驱替实验记录模板", workbook.add_format({'bold': True, 'size': 14}))
readme_sheet.write(2, 0, "1. 每次实验填入一行数据，Ca 和 S_nr 为必填核心参数。")
readme_sheet.write(3, 0, "2. log10(Ca) 和 黏度比M 由内置公式自动计算，无需手动填写。")
readme_sheet.write(4, 0, "3. 请利用 Excel 透视图功能分析 S_nr 数据。")

writer.close()
print("模板 Microfluidic_Experiment_Template.xlsx 已生成！")
💡 实验流程闭环建议

使用此模板，你可以做到**“实验-图像处理-记录”的标准化**：

实验台：设定条件，启动泵。

脚本端：跑完实验后，用 OpenCV/Python 图像分析脚本提取该帧图像的 S_nr、num_clusters 和 avg_area。

记录端：将脚本终端输出的数据直接抄录/粘贴入该 Excel 对应的行。公式会自动算出 logCa，表格自动亮起对应的颜色。

汇报端：切到“分析图表”页，右键刷新透视图，直接截图放入 PPT 或组会报告。