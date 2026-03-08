$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$wb = $excel.Workbooks.Open('D:\00 Claude Code\01 MATLAB CODE\01 Microfluid\Microfluidic_Experiment_Template.xlsx')

# ============================================================
# Sheet: 列表与参数 (Lists) — Update fluid parameters
# ============================================================
$ws = $wb.Worksheets.Item('列表与参数 (Lists)')

# --- Update interface tension references (Column D-E, rows 2-8) ---
# Header already exists at [1,4]="常用界面张力参考", [1,5]="数值 (mN/m)"

# Row 2: keep 纯水-空气 = 72
# Row 3: update to our first fluid
$ws.Cells.Item(3, 4).Value2 = "水-正十二烷 (n-Dodecane)"
$ws.Cells.Item(3, 5).Value2 = 52.8

# Row 4: update to our second fluid
$ws.Cells.Item(4, 4).Value2 = "水-溴代十二烷 (1-Bromododecane)"
$ws.Cells.Item(4, 5).Value2 = 40.5

# Row 5: update to our third fluid
$ws.Cells.Item(5, 4).Value2 = "水-溴代辛烷 (1-Bromooctane)"
$ws.Cells.Item(5, 5).Value2 = 38.2

# Row 6: add SDS reference
$ws.Cells.Item(6, 4).Value2 = "加SDS水-油 (典型)"
$ws.Cells.Item(6, 5).Value2 = 5

# --- Add comprehensive fluid property table (Column D-E, rows 8+) ---
# Chip parameters already at rows 7-11, shift fluid data below

# Row 13: Header for fluid properties
$ws.Cells.Item(13, 1).Value2 = "流体物性参考 Fluid Properties (25°C)"
$ws.Cells.Item(13, 1).Font.Bold = $true

# Row 14: Sub-headers
$ws.Cells.Item(14, 1).Value2 = "属性 Property"
$ws.Cells.Item(14, 2).Value2 = "正十二烷 n-Dodecane"
$ws.Cells.Item(14, 3).Value2 = "溴代十二烷 1-Bromododecane"
$ws.Cells.Item(14, 4).Value2 = "溴代辛烷 1-Bromooctane"
$ws.Cells.Item(14, 5).Value2 = "单位"
$ws.Cells.Item(14, 1).Font.Bold = $true
$ws.Cells.Item(14, 2).Font.Bold = $true
$ws.Cells.Item(14, 3).Font.Bold = $true
$ws.Cells.Item(14, 4).Font.Bold = $true
$ws.Cells.Item(14, 5).Font.Bold = $true

# Row 15: Molecular formula
$ws.Cells.Item(15, 1).Value2 = "分子式"
$ws.Cells.Item(15, 2).Value2 = "C12H26"
$ws.Cells.Item(15, 3).Value2 = "C12H25Br"
$ws.Cells.Item(15, 4).Value2 = "C8H17Br"

# Row 16: Molecular weight
$ws.Cells.Item(16, 1).Value2 = "分子量 MW"
$ws.Cells.Item(16, 2).Value2 = 170.34
$ws.Cells.Item(16, 3).Value2 = 249.23
$ws.Cells.Item(16, 4).Value2 = 193.13
$ws.Cells.Item(16, 5).Value2 = "g/mol"

# Row 17: CAS number
$ws.Cells.Item(17, 1).Value2 = "CAS号"
$ws.Cells.Item(17, 2).Value2 = "112-40-3"
$ws.Cells.Item(17, 3).Value2 = "143-15-7"
$ws.Cells.Item(17, 4).Value2 = "111-83-1"

# Row 18: Density
$ws.Cells.Item(18, 1).Value2 = "密度 Density (20°C)"
$ws.Cells.Item(18, 2).Value2 = 0.749
$ws.Cells.Item(18, 3).Value2 = 1.038
$ws.Cells.Item(18, 4).Value2 = 1.117
$ws.Cells.Item(18, 5).Value2 = "g/cm³"

# Row 19: Dynamic Viscosity
$ws.Cells.Item(19, 1).Value2 = "动力粘度 (20-25°C)"
$ws.Cells.Item(19, 2).Value2 = 1.34
$ws.Cells.Item(19, 3).Value2 = 3.7
$ws.Cells.Item(19, 4).Value2 = 2.1
$ws.Cells.Item(19, 5).Value2 = "mPa·s"

# Row 20: Interface Tension with water
$ws.Cells.Item(20, 1).Value2 = "水界面张力 IFT"
$ws.Cells.Item(20, 2).Value2 = 52.8
$ws.Cells.Item(20, 3).Value2 = 40.5
$ws.Cells.Item(20, 4).Value2 = 38.2
$ws.Cells.Item(20, 5).Value2 = "mN/m"

# Row 21: Water solubility
$ws.Cells.Item(21, 1).Value2 = "水溶解度 (25°C)"
$ws.Cells.Item(21, 2).Value2 = "<0.001"
$ws.Cells.Item(21, 3).Value2 = "<0.001"
$ws.Cells.Item(21, 4).Value2 = "0.004"
$ws.Cells.Item(21, 5).Value2 = "g/100g"

# Row 22: Diffusion coeff in water
$ws.Cells.Item(22, 1).Value2 = "水中扩散系数 D (25°C)"
$ws.Cells.Item(22, 2).Value2 = "4.8E-10"
$ws.Cells.Item(22, 3).Value2 = "3.8E-10"
$ws.Cells.Item(22, 4).Value2 = "5.2E-10"
$ws.Cells.Item(22, 5).Value2 = "m²/s"

# Row 23: Boiling point
$ws.Cells.Item(23, 1).Value2 = "沸点 BP"
$ws.Cells.Item(23, 2).Value2 = "216-218"
$ws.Cells.Item(23, 3).Value2 = "260 (decomp)"
$ws.Cells.Item(23, 4).Value2 = "199-201"
$ws.Cells.Item(23, 5).Value2 = "°C"

# Row 24: Vapor pressure
$ws.Cells.Item(24, 1).Value2 = "蒸气压 VP (20°C)"
$ws.Cells.Item(24, 2).Value2 = 0.034
$ws.Cells.Item(24, 3).Value2 = 0.004
$ws.Cells.Item(24, 4).Value2 = 0.133
$ws.Cells.Item(24, 5).Value2 = "kPa"

# Row 25: Surface tension
$ws.Cells.Item(25, 1).Value2 = "表面张力 (20°C)"
$ws.Cells.Item(25, 2).Value2 = 25.35
$ws.Cells.Item(25, 3).Value2 = 29.2
$ws.Cells.Item(25, 4).Value2 = 27.8
$ws.Cells.Item(25, 5).Value2 = "mN/m"

# Row 26: Flash point
$ws.Cells.Item(26, 1).Value2 = "闪点 FP"
$ws.Cells.Item(26, 2).Value2 = 71
$ws.Cells.Item(26, 3).Value2 = 110
$ws.Cells.Item(26, 4).Value2 = 62
$ws.Cells.Item(26, 5).Value2 = "°C"

# Row 27: Refractive index
$ws.Cells.Item(27, 1).Value2 = "折射率 nD (20°C)"
$ws.Cells.Item(27, 2).Value2 = 1.421
$ws.Cells.Item(27, 3).Value2 = 1.458
$ws.Cells.Item(27, 4).Value2 = 1.450

# Row 28: Phase position
$ws.Cells.Item(28, 1).Value2 = "与水分层位置"
$ws.Cells.Item(28, 2).Value2 = "上层 (ρ<水)"
$ws.Cells.Item(28, 3).Value2 = "下层 (ρ>水)"
$ws.Cells.Item(28, 4).Value2 = "下层 (ρ>水)"

# Row 29: Toxicity rating
$ws.Cells.Item(29, 1).Value2 = "毒性等级 NFPA"
$ws.Cells.Item(29, 2).Value2 = "1 (低毒)"
$ws.Cells.Item(29, 3).Value2 = "1 (低毒)"
$ws.Cells.Item(29, 4).Value2 = "2 (中度)"

# Row 30: Safety note
$ws.Cells.Item(30, 1).Value2 = "安全提示"
$ws.Cells.Item(30, 2).Value2 = "易燃, 通风"
$ws.Cells.Item(30, 3).Value2 = "低挥发, 手套"
$ws.Cells.Item(30, 4).Value2 = "高挥发, 通风橱"

# Row 32: Data source
$ws.Cells.Item(32, 1).Value2 = "数据来源: CRC Handbook, NIST WebBook, Sigma-Aldrich MSDS"
$ws.Cells.Item(32, 1).Font.Italic = $true

# Auto-fit column widths
$ws.Columns.Item(1).ColumnWidth = 24
$ws.Columns.Item(2).ColumnWidth = 24
$ws.Columns.Item(3).ColumnWidth = 28
$ws.Columns.Item(4).ColumnWidth = 24
$ws.Columns.Item(5).ColumnWidth = 12

# ============================================================
# Sheet: 数据记录 (Data Record) — Update sample test data
# ============================================================
$ws2 = $wb.Worksheets.Item('数据记录 (Data Record)')

# Update Test1: n-Dodecane displacement by water
$ws2.Cells.Item(2, 4).Value2 = 52.8   # sigma = water-dodecane IFT
$ws2.Cells.Item(2, 8).Value2 = 1.0    # mu_w = water viscosity
$ws2.Cells.Item(2, 9).Value2 = 1.34   # mu_o = dodecane viscosity
$ws2.Cells.Item(2, 16).Value2 = "正十二烷, 水驱"

# Update Test2: 1-Bromododecane displacement by water
$ws2.Cells.Item(3, 4).Value2 = 40.5   # sigma = water-bromododecane IFT
$ws2.Cells.Item(3, 8).Value2 = 1.0    # mu_w = water viscosity
$ws2.Cells.Item(3, 9).Value2 = 3.7    # mu_o = bromododecane viscosity
$ws2.Cells.Item(3, 16).Value2 = "溴代十二烷, 水驱"

# Update Test3: 1-Bromooctane displacement by water
$ws2.Cells.Item(4, 4).Value2 = 38.2   # sigma = water-bromooctane IFT
$ws2.Cells.Item(4, 8).Value2 = 1.0    # mu_w = water viscosity
$ws2.Cells.Item(4, 9).Value2 = 2.1    # mu_o = bromooctane viscosity
$ws2.Cells.Item(4, 16).Value2 = "溴代辛烷, 水驱, 加表活剂"

# Save and close
$wb.Save()
$wb.Close($false)
$excel.Quit()
[System.Runtime.Interopservices.Marshal]::ReleaseComObject($excel) | Out-Null

Write-Host "Done! Excel template updated successfully."
