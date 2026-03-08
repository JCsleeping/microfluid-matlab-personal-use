"""
Generate Microfluidic Experiment Template Excel file.
Based on the specification in excel.md.
"""
import xlsxwriter

output_path = r"D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\Microfluidic_Experiment_Template.xlsx"

workbook = xlsxwriter.Workbook(output_path)

# ============================================================
#  FORMATS
# ============================================================
fmt_title = workbook.add_format({
    'bold': True, 'font_size': 16, 'font_color': '#1F4E79',
    'bottom': 2, 'bottom_color': '#1F4E79'
})
fmt_header = workbook.add_format({
    'bold': True, 'bg_color': '#D9E1F2', 'border': 1,
    'align': 'center', 'valign': 'vcenter', 'text_wrap': True,
    'font_size': 10
})
fmt_normal = workbook.add_format({'border': 1, 'font_size': 10, 'valign': 'vcenter'})
fmt_pct = workbook.add_format({'border': 1, 'font_size': 10, 'num_format': '0.00%', 'valign': 'vcenter'})
fmt_sci = workbook.add_format({'border': 1, 'font_size': 10, 'num_format': '0.00E+00', 'valign': 'vcenter'})
fmt_formula = workbook.add_format({
    'border': 1, 'font_size': 10, 'bg_color': '#E2EFDA',
    'italic': True, 'valign': 'vcenter'
})
fmt_formula_sci = workbook.add_format({
    'border': 1, 'font_size': 10, 'bg_color': '#E2EFDA',
    'italic': True, 'valign': 'vcenter', 'num_format': '0.00E+00'
})
fmt_readme_title = workbook.add_format({'bold': True, 'font_size': 14, 'font_color': '#1F4E79'})
fmt_readme_sub = workbook.add_format({'bold': True, 'font_size': 11, 'font_color': '#2E75B6'})
fmt_readme_text = workbook.add_format({'font_size': 10, 'text_wrap': True, 'valign': 'top'})
fmt_list_header = workbook.add_format({
    'bold': True, 'bg_color': '#FFF2CC', 'border': 1,
    'align': 'center', 'font_size': 10
})
fmt_list_item = workbook.add_format({'border': 1, 'font_size': 10})

# ============================================================
#  SHEET 1: ReadMe
# ============================================================
ws_readme = workbook.add_worksheet('说明 (ReadMe)')
ws_readme.set_column('A:A', 80)
ws_readme.hide_gridlines(2)

ws_readme.write('A1', '微流控 NAPL 驱替实验数据记录模板', fmt_readme_title)
ws_readme.write('A3', '使用说明', fmt_readme_sub)
ws_readme.write('A4', '1. 每次实验填入一行数据。Q, mu_w, mu_o, sigma 和 S_nr 为必填核心参数。', fmt_readme_text)
ws_readme.write('A5', '2. Ca, log10(Ca) 和黏度比 M 由内置公式自动计算（绿色底色列），无需手动填写。', fmt_readme_text)
ws_readme.write('A6', '3. 结构类型（B列）和流型描述（O列）使用下拉菜单选择，防止输入错误。', fmt_readme_text)
ws_readme.write('A7', '4. S_nr 列自动应用红-黄-绿色阶条件格式，一目了然。', fmt_readme_text)
ws_readme.write('A8', '5. 请在"分析图表"工作表中使用透视图功能进行数据可视化。', fmt_readme_text)

ws_readme.write('A10', '公式说明', fmt_readme_sub)
ws_readme.write('A11', 'F列  Ca = mu_w * v / sigma, 其中 v = Q / (W * D)  -- 芯片参数 W, D 在"列表与参数"表 E8:E9', fmt_readme_text)
ws_readme.write('A12', 'G列  log10(Ca) = LOG10(F列)  -- 毛细数的对数，用于绘制CDC曲线', fmt_readme_text)
ws_readme.write('A13', 'J列  黏度比 M = H列(mu_w) / I列(mu_o)  -- 驱替相与被驱相的黏度比', fmt_readme_text)

ws_readme.write('A14', '参考文献', fmt_readme_sub)
ws_readme.write('A15', 'Lenormand, R., Touboul, E., & Zarcone, C. (1988). Numerical models and experiments on immiscible displacements in porous media. J. Fluid Mech., 189, 165-187.', fmt_readme_text)
ws_readme.write('A16', 'Hilfer, R. (2006). Macroscopic capillarity without a constitutive capillary pressure function. Prog. Colloid Polym. Sci., 132, 110-117.', fmt_readme_text)

ws_readme.write('A18', '图表指南', fmt_readme_sub)
ws_readme.write('A19', '图一：CDC 曲线 -- X: log10(Ca) (G列), Y: S_nr (K列) -> 散点图 + 趋势线', fmt_readme_text)
ws_readme.write('A20', '图二：Lenormand 相图 -- X: log10(Ca) (G列), Y: M (J列, 对数Y轴) -> 按流型分色散点', fmt_readme_text)
ws_readme.write('A21', '图三：多条件 S_nr 对比 -- 数据透视图, 类别=结构类型, 值=平均S_nr -> 柱状图', fmt_readme_text)

ws_readme.write('A23', '实验流程闭环', fmt_readme_sub)
ws_readme.write('A24', '实验台 -> 图像采集 -> MATLAB/Python 脚本提取 S_nr/num_clusters/avg_area -> 填入本表 -> 公式自动算 logCa & M -> 切到图表页刷新 -> 截图汇报', fmt_readme_text)

# ============================================================
#  SHEET 2: Lists
# ============================================================
ws_lists = workbook.add_worksheet('列表与参数 (Lists)')
ws_lists.set_column('A:A', 20)
ws_lists.set_column('B:B', 25)
ws_lists.set_column('D:D', 20)
ws_lists.set_column('E:E', 25)

ws_lists.write('A1', '结构类型', fmt_list_header)
for i, v in enumerate(['均匀', '梯度减少', '双孔径'], start=1):
    ws_lists.write(i, 0, v, fmt_list_item)

ws_lists.write('B1', '流型描述', fmt_list_header)
for i, v in enumerate(['稳定前锋', '毛细指进(CF)', '黏性指进(VF)', '枝状蔓延'], start=1):
    ws_lists.write(i, 1, v, fmt_list_item)

ws_lists.write('D1', '常用界面张力参考', fmt_list_header)
ws_lists.write('E1', '数值 (mN/m)', fmt_list_header)
refs = [('纯水-空气', 72.0), ('水-十二烷', 52.0), ('水-TCE', 35.0), ('加SDS水-油', 5.0)]
for i, (name, val) in enumerate(refs, start=1):
    ws_lists.write(i, 3, name, fmt_list_item)
    ws_lists.write(i, 4, val, fmt_list_item)

# Chip geometry parameters (used by Ca formula)
fmt_param_label = workbook.add_format({'bold': True, 'bg_color': '#DAEEF3', 'border': 1, 'font_size': 10})
fmt_param_value = workbook.add_format({'border': 1, 'font_size': 10, 'num_format': '0', 'bg_color': '#FFFFFF'})
ws_lists.write('D7', '芯片参数', fmt_readme_sub)
ws_lists.write('D8', '通道宽度 W (um)', fmt_param_label)
ws_lists.write('E8', 500, fmt_param_value)   # default 500 um
ws_lists.write('D9', '通道深度 D (um)', fmt_param_label)
ws_lists.write('E9', 20, fmt_param_value)    # default 20 um
ws_lists.write('D10', '单位换算系数', fmt_param_label)
ws_lists.write('E10', '=1000/60', fmt_param_value)  # auto
ws_lists.write('D11', '', workbook.add_format({'font_size': 8, 'italic': True, 'font_color': '#808080'}))
ws_lists.write('D11', 'Ca = mu_w*Q / (sigma*W*D) * k', workbook.add_format({'font_size': 9, 'italic': True, 'font_color': '#808080'}))

# ============================================================
#  SHEET 3: Data Record (CORE)
# ============================================================
ws_data = workbook.add_worksheet('数据记录 (Data Record)')

headers = [
    '实验编号\n(Run ID)',
    '结构类型',
    '接触角 theta\n(deg)',
    '界面张力 sigma\n(mN/m)',
    '流量 Q\n(uL/min)',
    '毛细数 Ca\n(-) [auto]',
    'log10(Ca)\n(-) [auto]',
    '驱替相黏度 mu_w\n(mPa s)',
    '被驱相黏度 mu_o\n(mPa s)',
    '黏度比 M\n(-)',
    '残油饱和度 S_nr\n(%)',
    '有效渗透率 k_eff\n(-)',
    '油团块数量\n(个)',
    '平均团块面积\n(um2)',
    '流型描述',
    '备注说明',
]

col_widths = [14, 12, 12, 14, 12, 16, 12, 16, 16, 12, 16, 14, 12, 16, 16, 20]

for col, (hdr, w) in enumerate(zip(headers, col_widths)):
    ws_data.write(0, col, hdr, fmt_header)
    ws_data.set_column(col, col, w)

ws_data.set_row(0, 40)

# Sample data (col 5=Ca is None because it's a formula now)
sample_data = [
    #  A         B          C   D     E    F     G     H    I    J     K     L     M   N     O                P
    ['Test1', '均匀',       30, 72,  0.5, None, None, 1.0, 0.6, None, 0.35, 0.45, 15, 3000, '毛细指进(CF)', '测试用例'],
    ['Test2', '双孔径',    120, 72,  5.0, None, None, 1.0, 0.6, None, 0.12, 0.85,  3,  500, '稳定前锋',     ''],
    ['Test3', '梯度减少',   60, 35,  2.0, None, None, 1.0, 3.0, None, 0.08, 0.92,  2,  250, '黏性指进(VF)', '加表活剂'],
]

for row_idx, row_data in enumerate(sample_data, start=1):
    for col_idx, value in enumerate(row_data):
        if value is None:
            continue  # formula columns
        if col_idx == 10:  # S_nr
            ws_data.write_number(row_idx, col_idx, value, fmt_pct)
        elif isinstance(value, (int, float)):
            ws_data.write_number(row_idx, col_idx, value, fmt_normal)
        else:
            ws_data.write_string(row_idx, col_idx, value, fmt_normal)

# Sheet name for cross-sheet reference
LS = "'列表与参数 (Lists)'"

# Formulas for rows 2-100
for row in range(1, 100):
    r = row + 1
    # F col (5): Ca = mu_w * Q / (sigma * W * D) * (1000/60)
    # Units: mu[mPa.s]*Q[uL/min] / (sigma[mN/m]*W[um]*D[um]) * 1000/60 -> dimensionless
    ca_formula = ('=IFERROR('
        f'(H{r}*E{r}) / (D{r}*{LS}!$E$8*{LS}!$E$9) * {LS}!$E$10'
        ',"")')
    ws_data.write_formula(row, 5, ca_formula, fmt_formula_sci)
    # G col (6): log10(Ca)
    ws_data.write_formula(row, 6, f'=IFERROR(LOG10(F{r}),"")', fmt_formula)
    # J col (9): M = mu_w / mu_o
    ws_data.write_formula(row, 9, f'=IFERROR(H{r}/I{r},"")', fmt_formula)

# Data validation
ws_data.data_validation('B2:B100', {
    'validate': 'list',
    'source': ['均匀', '梯度减少', '双孔径'],
    'input_title': '结构类型',
    'input_message': '请选择芯片结构类型',
    'error_title': '输入错误',
    'error_message': '请从下拉列表中选择'
})

ws_data.data_validation('O2:O100', {
    'validate': 'list',
    'source': ['稳定前锋', '毛细指进(CF)', '黏性指进(VF)', '枝状蔓延'],
    'input_title': '流型描述',
    'input_message': '请选择观察到的流型',
    'error_title': '输入错误',
    'error_message': '请从下拉列表中选择'
})

# Conditional formatting on S_nr
ws_data.conditional_format('K2:K100', {
    'type': '3_color_scale',
    'min_color': '#63BE7B',
    'mid_color': '#FFEB84',
    'max_color': '#F8696B'
})

ws_data.freeze_panes(1, 0)
ws_data.autofilter(0, 0, 99, 15)

# ============================================================
#  SHEET 4: Analysis Charts
# ============================================================
ws_charts = workbook.add_worksheet('分析图表 (Analysis Charts)')

# Chart 1: CDC Curve
chart1 = workbook.add_chart({'type': 'scatter', 'subtype': 'smooth_with_markers'})
chart1.set_title({'name': '毛细去捕曲线 (CDC Curve)'})
chart1.set_x_axis({
    'name': 'log10(Ca)',
    'major_gridlines': {'visible': True, 'line': {'color': '#D9D9D9'}},
})
chart1.set_y_axis({
    'name': 'S_nr (%)',
    'num_format': '0%',
    'major_gridlines': {'visible': True, 'line': {'color': '#D9D9D9'}},
})
chart1.add_series({
    'name': 'S_nr vs log10(Ca)',
    'categories': ['数据记录 (Data Record)', 1, 6, 99, 6],
    'values':     ['数据记录 (Data Record)', 1, 10, 99, 10],
    'marker': {'type': 'circle', 'size': 8, 'fill': {'color': '#4472C4'}},
    'line': {'color': '#4472C4', 'width': 2},
})
chart1.set_size({'width': 600, 'height': 400})
chart1.set_legend({'position': 'bottom'})
ws_charts.insert_chart('A2', chart1)

# Chart 2: Lenormand Phase Diagram
chart2 = workbook.add_chart({'type': 'scatter'})
chart2.set_title({'name': 'Lenormand Phase Diagram (log10Ca vs M)'})
chart2.set_x_axis({
    'name': 'log10(Ca)',
    'major_gridlines': {'visible': True, 'line': {'color': '#D9D9D9'}},
})
chart2.set_y_axis({
    'name': 'M (-)',
    'log_base': 10,
    'major_gridlines': {'visible': True, 'line': {'color': '#D9D9D9'}},
})
chart2.add_series({
    'name': 'Experiment Data',
    'categories': ['数据记录 (Data Record)', 1, 6, 99, 6],
    'values':     ['数据记录 (Data Record)', 1, 9, 99, 9],
    'marker': {'type': 'diamond', 'size': 10, 'fill': {'color': '#ED7D31'}},
    'line': {'none': True},
})
chart2.set_size({'width': 600, 'height': 400})
chart2.set_legend({'position': 'bottom'})
ws_charts.insert_chart('A22', chart2)

# Chart 3: S_nr bar chart
chart3 = workbook.add_chart({'type': 'column'})
chart3.set_title({'name': '不同结构类型的 S_nr 对比'})
chart3.set_x_axis({'name': '结构类型'})
chart3.set_y_axis({
    'name': 'S_nr (%)',
    'num_format': '0%',
    'major_gridlines': {'visible': True, 'line': {'color': '#D9D9D9'}},
})
chart3.add_series({
    'name': 'S_nr',
    'categories': ['数据记录 (Data Record)', 1, 1, 3, 1],
    'values':     ['数据记录 (Data Record)', 1, 10, 3, 10],
    'fill': {'color': '#4472C4'},
    'gap': 150,
})
chart3.set_size({'width': 600, 'height': 400})
chart3.set_legend({'none': True})
ws_charts.insert_chart('J2', chart3)

ws_charts.set_column('A:A', 12)
ws_charts.write('A1', '以下图表基于"数据记录"表的数据自动生成。添加新数据后，图表会自动更新。',
                workbook.add_format({'bold': True, 'font_size': 11, 'font_color': '#1F4E79'}))

# ============================================================
workbook.close()
print("OK: " + output_path)
