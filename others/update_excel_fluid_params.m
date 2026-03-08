%% update_excel_fluid_params.m
% Update Microfluidic_Experiment_Template.xlsx with fluid parameters
% for n-Dodecane, 1-Bromododecane, 1-Bromooctane

xlsFile = fullfile(pwd, 'Microfluidic_Experiment_Template.xlsx');
listSheet = 2;  % Sheet index for Lists
dataSheet = 3;  % Sheet index for Data Record

%% ---- Update interface tension references on Lists sheet ----
% Row 3-6, Columns D-E (4-5)
xlswrite(xlsFile, {'水-正十二烷 (n-Dodecane)'}, listSheet, 'D3');
xlswrite(xlsFile, {52.8}, listSheet, 'E3');

xlswrite(xlsFile, {'水-溴代十二烷 (1-Bromododecane)'}, listSheet, 'D4');
xlswrite(xlsFile, {40.5}, listSheet, 'E4');

xlswrite(xlsFile, {'水-溴代辛烷 (1-Bromooctane)'}, listSheet, 'D5');
xlswrite(xlsFile, {38.2}, listSheet, 'E5');

xlswrite(xlsFile, {'加SDS水-油 (典型)'}, listSheet, 'D6');
xlswrite(xlsFile, {5}, listSheet, 'E6');

fprintf('  [OK] Interface tension references updated\n');

%% ---- Add comprehensive fluid property table on Lists sheet ----
% Starting from Row 13

% Title row
xlswrite(xlsFile, {'流体物性参考 Fluid Properties (25°C)'}, listSheet, 'A13');

% Headers
headers = {'属性 Property', '正十二烷 n-Dodecane', '溴代十二烷 1-Bromododecane', ...
           '溴代辛烷 1-Bromooctane', '单位 Unit'};
xlswrite(xlsFile, headers, listSheet, 'A14');

% Data rows (15-30)
propData = {
    '分子式',          'C12H26',       'C12H25Br',        'C8H17Br',         '';
    '分子量 MW',       170.34,         249.23,             193.13,            'g/mol';
    'CAS号',           '112-40-3',     '143-15-7',         '111-83-1',        '';
    '密度 Density (20°C)',  0.749,      1.038,              1.117,             'g/cm3';
    '动力粘度 (20-25°C)',   1.34,       3.7,                2.1,               'mPa·s';
    '水界面张力 IFT',       52.8,       40.5,               38.2,              'mN/m';
    '水溶解度 (25°C)',      '<0.001',   '<0.001',           '0.004',           'g/100g';
    '水中扩散系数 D (25°C)', '4.8E-10', '3.8E-10',          '5.2E-10',         'm2/s';
    '沸点 BP',              '216-218',  '260 (decomp)',     '199-201',         'deg C';
    '蒸气压 VP (20°C)',     0.034,      0.004,              0.133,             'kPa';
    '表面张力 (20°C)',      25.35,      29.2,               27.8,              'mN/m';
    '闪点 FP',              71,         110,                62,                'deg C';
    '折射率 nD (20°C)',     1.421,      1.458,              1.450,             '';
    '与水分层位置',         '上层 (rho<水)', '下层 (rho>水)',  '下层 (rho>水)',   '';
    '毒性等级 NFPA',        '1 (低毒)', '1 (低毒)',          '2 (中度)',        '';
    '安全提示',             '易燃, 通风', '低挥发, 手套',     '高挥发, 通风橱',  ''
};
xlswrite(xlsFile, propData, listSheet, 'A15');

% Source note
xlswrite(xlsFile, {'数据来源: CRC Handbook, NIST WebBook, Sigma-Aldrich MSDS'}, listSheet, 'A32');

fprintf('  [OK] Fluid property table added (rows 13-31)\n');

%% ---- Update Data Record sheet sample test data ----
% Test1: n-Dodecane
xlswrite(xlsFile, {52.8}, dataSheet, 'D2');   % sigma
xlswrite(xlsFile, {1.0},  dataSheet, 'H2');   % mu_w
xlswrite(xlsFile, {1.34}, dataSheet, 'I2');   % mu_o
xlswrite(xlsFile, {'正十二烷, 水驱'}, dataSheet, 'P2');

% Test2: 1-Bromododecane
xlswrite(xlsFile, {40.5}, dataSheet, 'D3');   % sigma
xlswrite(xlsFile, {1.0},  dataSheet, 'H3');   % mu_w
xlswrite(xlsFile, {3.7},  dataSheet, 'I3');   % mu_o
xlswrite(xlsFile, {'溴代十二烷, 水驱'}, dataSheet, 'P3');

% Test3: 1-Bromooctane
xlswrite(xlsFile, {38.2}, dataSheet, 'D4');   % sigma
xlswrite(xlsFile, {1.0},  dataSheet, 'H4');   % mu_w
xlswrite(xlsFile, {2.1},  dataSheet, 'I4');   % mu_o
xlswrite(xlsFile, {'溴代辛烷, 水驱'}, dataSheet, 'P4');

fprintf('  [OK] Data Record test rows updated\n');
fprintf('\nDone! Excel template updated successfully.\n');
