# 开发日志 (Changelog)

## v3.9.6 — 清尾包：P-016 测试有效性补强 + P-015 审计遗留 + P-014 文献订正 (已实施, 2026-11-21)

### 概览

合并三项遗留（[spec/v396-audit-backlog-cleanup](spec/v396-audit-backlog-cleanup/) 四件套 v1.4/v1.3/v1.2/v1.3），包版本 **3.9.6**（patch 级）。生产代码唯一改动文件 `scripts/verify_capacity_impact.py`：`backtest/execution/core/` 与 `shell/panels.py` 零改动，默认工件逐位不变。

- **P-016**（v3.9.5 Step 10 审计遗留 2×P2 + 3×P3，测试有效性补强）：T396_1 共享重抽样索引
  （monkeypatch 断言 buy/sell 合计仅调用 1 次、两读数取同一 idx：calls==1、buy 200/sell 300、lo==hi==point）；
  T396_2 脚本层截面 demean（`build_reversal_events` 事件 Σrt≈0）；T3100_3 删除两条恒真断言与死变量
  （保留非恒真平移对照）；T3100_9 补常数输入（rt≡+2% → lo=hi=point=100、degraded=False）；
  T396_5 `reversal_counts` 15 键字面量集合断言。
- **P-015**（v3.9.4 Step 10 审计遗留 3×P3）：T396_6 `decay.plateau` core 契约 6 例参数化
  （空/sd=0/≥边界/边界外/并列排序/单点）；T396_7 `_decay_curve_md` 标题改由 `factor_pipeline.__version__`
  驱动（函数内延迟导入），修复硬编码「v3.9.3」；T396_9 `--force-coverage` 真实低覆盖 E2E
  （复制 2020-02 真实 feather 20 文件 ≈233 MB 至 tmp_path、按代码尾号跨文件裁剪 30% → `universe_ratio` 0.713：
  严格分支 exit 2、force 分支 exit 0 + `coverage_gate_forced:` 留痕）。
- **P-014**：`RESEARCH_V3.8.0_EXECUTION_CAPACITY.md` L699/L860 Chen & Velikov 期刊元数据 RFS→JFQA 订正
  （58(3), 968-1004 + DOI 10.1017/S0022109022000874）。
- **新增 CLI**：`--minute-root`（`default=None`，help 标「测试/诊断用」；不传时 `overrides=={}`，
  cfg 与默认路径零变更）。

### 核心产出

- `scripts/verify_capacity_impact.py`：`--minute-root` 参数 + overrides 构造；`_decay_curve_md` 版本参数化。
- 测试：新增 9 例（T396-1/2/5/6/7/8/9 + T3100_3 重写 + T3100_9 追加）；E2E 仅写 pytest `tmp_path`。
- 包版本 **3.9.6**（pyproject / `__init__` / config_v2 / reporting + 两处版本测试锚点）。

### 实测读数

- 默认 `out/capacity_impact.json` SHA `82728CE1…` 与 `out/v394_calibration.json` 内 `panel_hash dfcc4e1d…`
  逐位不变（INV-1/2，实施方 + 审计方双重复核）；
- E2E 严格+force 合计 86.84 s（单次 ≈43 s，≤180/600 s 预算）；新增非 E2E 用例合计 0.64 s；
- 全量 `pytest -q`：**2088 passed / 15 skipped / 0 failed**（938.81 s）；
- Step 10 独立只读审计 **PASS_WITH_FIXES**（4.75/5，A；0×P1、1×P2、3×P3）→ 遗留登记 **P-017**。

## v3.9.5 — P-003 截面 T+1 reversal 证据层真实现（口径 A）(已实施, 2026-11-21)

### 概览

`temporary_share` 由「组合日超额 AR(1) 代理」升级为**交易事件级截面 T+1 反转**读数：事件 = 形成日权重变动
（`s=sign(Δw)`、`a=|Δw|`），度量被交易股票次日是否朝不利方向回落。按用户裁决**口径 A**：只做证据层，
`reversal_bps` **不进** `cost_by_h`，`net(h)` / 容量读数逐位不变；旧代理降级为 `temporary_proxy_ar1` 仅作对照。

- **core**：新增 `cross_section_reversal`（事件加权 `share=clip(-Σaxy/Σax²,0,1)`、`reversal_bps=-(Σay/Σa)×1e4`，
  按形成月聚类 bootstrap，`block_size=1 / seed=20261121`，三个读数均 `min(lo,point)/max(hi,point)` 夹逼）；
  未加入 `__all__`（仍 5 项）。
- **脚本层**：`build_panels` 增 `open_adj` / `impl_daily`；新增 `build_reversal_events`（C1/C2 两种价格口径、
  九步过滤 + 15 键 counts、`t+1` 交易日 `searchsorted`）；`load_implementability` 增 `limit_down` 镜像。
- **装配/透传**：`panels` 真/回退双分支（回退 warning 逐字保留）；`runner` 输出 `reversal_bps` /
  `reversal_price_basis`，退化追加 `cross_section_reversal_degraded`。
- **勘误**：E-2 证据层实际覆盖 73 个形成月 / 72 有效聚类（39 为分钟层口径）；E-3 C2 公式改为
  `adj_price/open_adj-1`（同日复权因子相消），修复首轮重复乘复权因子导致的假读数。

### 核心产出

- `backtest/execution/core/impact.py`：`_degraded_reversal` / `_interval` / `cross_section_reversal`（新增）。
- `scripts/verify_capacity_impact.py`：`build_panels` 增 `open_adj`/`impl_daily`、`build_reversal_events`、
  `--reversal-price-basis`、`attach_panel_meta` 增 `temporary_proxy_ar1`/`reversal_counts`（仅 calibrate 分支）。
- `backtest/execution/shell/panels.py`：`_has_reversal_events` + 真实现装配（`cost_by_h` 段零改动）。
- `backtest/execution/shell/runner.py`：真/回退分支与结果键。
- `scripts/verify_long_side_research.py`：`limit_down` 镜像（`stock_low.pkl`，失败降级 `None`）。
- 测试：T3100-1~10 + `test_runner_reversal_branch`（11 例）。
- 包版本 **3.9.5**（`pyproject.toml` / `__init__.py` / `config_v2.py` / `reporting.py` + 两处版本测试断言）。

### 实测读数

命令：`python scripts/verify_capacity_impact.py --calibrate --calibration-json out/v3100_calibration.json`（exit 0，`evidence_level=minutes`，**16 min 06 s**，基线≈14.5 min → +11%）。

- **C1（主口径 `adj_close_to_close_cs`）**：`temporary_share=[0, 0, 0.038326]`；`reversal_bps` point **−2.842**
  〔−14.974, +10.366〕；buy **+11.878**（n=76 420）、sell **−18.637**（n=175 258）；n=251 678、n_months=72。
- **C2（稳健性 `adj_intraday_open_close`）**：point **−2.420**〔−11.810, +5.938〕；buy +10.344、sell −16.115；
  与 C1 相对差 14.8% / 12.9% / 13.5% → **U-1 自动通过**。
- **过滤计数**：`n_limit_down_t=595`、`n_limit_up_t=0`（预期：形成日持仓取自 `tradable`）、`n_st=121`、
  `n_suspended_t=414`、`n_suspended_t1=163`、`n_missing=30 872`、`n_tiny=126 966`、`n_extreme=0`。
- **不变式**：默认 `out/capacity_impact.json` SHA `82728CE1…`、`panel_hash dfcc4e1d…` 逐位不变；
  `panels/capacity/decay/models/impact_curve/impact_samples/config_hash` 与 v3.9.4 全部相等；C1 双跑 JSON 逐键相等。
- **敏感性**：U-3 端点极差 0.005508（≤0.01）；U-5 外部基准 0.2%（≤10%），事件自指基准 33.3%（口径性质）。
- **测试**：全量 `pytest -q` **2076 passed / 15 skipped / 0 failed**（861.28 s）。
- **Step 10 审计**：独立只读子代理 **PASS_WITH_FIXES**（4.60/5，A；0×P1、2×P2、6×P3）→ 遗留登记 **P-016**。

## v3.9.4 — 批次 A 口径收口包：审计遗留修复 + 覆盖度交集口径 + 强制放行留痕（对应路线图批次 v3.9.4）(已实施, 2026-11-20)

### 概览

合并三项：**P-012**（v3.9.3 审计遗留 F-1~F-6）、**P-004**（覆盖度 `universe_ratio` 可 >1 的口径缺陷）、
**P-005**（`--force-coverage` 放行未留痕）。按 [DESIGN](spec/v394-audit-coverage-fix/DESIGN.md) D1-D11 实施，
全部改动落在校准分支与覆盖度装配，默认回测路径不进入任何新代码。

- **P-004**：`universe_ratio` 由「分钟 uniq 码数 / 日频域计数」改为交集口径 `|分钟码 ∩ 域码| / |域码|`，
  同时用新字段 `ratio_raw` 披露旧式分子（同分母，可 >1）；`counts` 语义冻结（D11）。
- **P-012 F-1**：回退分支 net 区间由 `aum·A(h)` 改为 m 形式 `aum·A(h_m)·(m ∓ t·m_se) − cost`，与 point 同一条代数路径。
- **P-012 F-2/F-3**：v393 IMPLEMENTATION 通过线勘误落盘（`2065 collected + 7 = 2072 = 2057 + 15`，I-3 注记保留）。
- **P-012 F-4**：`DecayCurve` 由死类型改为内部接线（`assemble_decay_curve` 构造 1 次，payload 由其字段组装）。
- **P-012 F-5**：payload 增 `net[h].sd` 与顶层 `plateau`（复用既有 `a_boot`/`m_boot`，不新增重采样）。
- **P-012 F-6**：退化态守卫 `m_sensitivity={}`，不再产出 `{"1":{},"6":{}}` 伪敏感性。
- **P-005**：新增纯函数 `force_coverage_warning`，force 分支把门禁文案 token 化写入 `minute["evidence_warnings"]`。

### 核心产出

- `backtest/execution/shell/panels.py`：`PanelCoverage.ratio_raw`（末位字段 + `as_dict` 增键）、
  `_universe_codes`（新增，`set[int]`）、`_universe_count`（薄封装）、`_coverage` 交集口径、
  `force_coverage_warning`（新增）+ `__all__` 增项。
- `backtest/execution/shell/runner.py`：F-1 m 形式区间、F-5 `net[h].sd` + 顶层 `plateau`、
  F-6 退化守卫、F-4 `DecayCurve` 接线（`core/decay.py` 零改动，`__all__` 仍 5 项）。
- `scripts/verify_capacity_impact.py`：懒加载 import 增 `force_coverage_warning`；force 分支追加留痕。
- `spec/v393-alpha-decay-model/IMPLEMENTATION.md`：§5 通过线勘误（F-2）。
- 包版本 **3.9.4**（`pyproject.toml` / `__init__.py` / `config_v2.py` / `reporting.py` + 两处版本测试断言）。

### 实测读数

命令：`python scripts/verify_capacity_impact.py --calibrate --calibration-json out/v394_calibration.json --decay-curve-json out/v394_decay_curve.json`（exit 0，`evidence_level=minutes`）。

- **P-004 修正生效**：39 月 `universe_ratio` ∈ **[0.981548, 0.999739]**（均值 0.993133，39/39 ≤1）；
  改前同一工件区间为 **[1.049629, 1.139838]**（旧口径全部 >1），**39/39 `ratio ≤ ratio_raw`**；
- `ratio_raw` ∈ [1.049629, 1.139838]，与改前旧 `universe_ratio` 逐位吻合 → 旧值可由新键完整复现（披露无损）；
- `stock_median = 4454.0` 与改前一致（仍取原始 `counts`）；
- **`panels.panel_hash` = `dfcc4e1dea9e4b4f82b73137b75ce8d59620a0d655d265780f8e52a935f85e3f`**，与改前工件逐位一致（INV-2 第二源）；
- 衰减曲线：`net(5) = −7,159,077`（sd 2.09e7）、`net(10) = +905,290`（sd 1.45e7）、`net(20) = +18,115,106`（sd 8.47e6）；
  顶层 **`plateau = [20]`**；`phi = 0.9999999999999992`（`fitted`）、`decay_source=empirical`、`evidence_warnings=[]`；
- 默认 `out/capacity_impact.json` SHA256 `82728CE1…`：跑前 / 实跑 / 复跑三方逐位一致（INV-1）；
- `_universe_codes` 合成基准（5000 列 × 31 行）39 次调用 0.0316 s（均值 0.8 ms）。

### 测试

- 新增 8 例（T394-1 ~ T394-8），先红 **7 failed + 1 passed**（T394-7 为回归护栏、按设计非红），实施后 **8 passed**；
- 相关三文件 `tests/test_execution_decay.py` / `tests/test_minute_panels.py` / `tests/test_execution_capacity.py`：**57 passed**；
- 全量 `pytest -q`：**2065 passed / 15 skipped / 0 failed**（850.84s，172 warnings）；即 v3.9.3 基线 2057 + 本批新增 8 例，与预注册通过线逐位一致。

## v3.9.3 — alpha 衰减模型选择（对应路线图批次 v3.9.3）(已实施, 2026-11-20)

### 概览

FO-1 根因：`rho` 衡量的是已实现日收益的 AR(1)（噪声/反转），不是 alpha 的期限结构。
本批按 [DESIGN](../spec/v393-alpha-decay-model/DESIGN.md) D1-D5 引入**累计 alpha 曲线**
`A(h)` + **单参数累计比** `φ` 的衰减模型：非参乘子 `m(h)=A(h)/[A(h_m)·h/h_m]`（`m(20)=1`
构造性归一），参数乘子 `m(h;φ)=(h_m/h)(1−φ^h)/(1−φ^{h_m})`；不确定性按形成期 block
bootstrap（39 期）；校正口径下给出 `net(h)` 三值与 verdict。默认路径零改动。

### 核心产出

- `backtest/execution/core/decay.py`：新增 `DecayCurve`（frozen dataclass）/
  `decay_multiplier` / `anchored_multiplier` / `fit_phi` / `net_point` / `net_ci` /
  `AnchoredDecay` / `EmpiricalDecay`；`__all__` 保持 5 项（DR-3）。
- `scripts/verify_capacity_impact.py`：新增 `formation_decay_curve`（t0 冻结权重快照，
  不复用 ffilled 序列）、`write_decay_curve` / `_decay_curve_md`、`--decay-curve-json`；
  `build_portfolio_panels` 返回增 `a_by_period` / `a_h_max`。
- `backtest/execution/shell/panels.py`：`build_daily_panels` 增
  `decay_a_by_period` / `decay_h_max` / `alpha0_anchored`（仅校准分支）。
- `backtest/execution/shell/runner.py`：新增 `assemble_decay_curve`（复用
  `effect_size.stationary_bootstrap_indices`；主 CI b=3，b=1/6 敏感性）。
- 包版本 **3.9.3**（6 处代码锚点 + CHANGELOG/README/PROJECT_STATUS/PROGRESS）。

### 实测读数

命令：`python scripts/verify_capacity_impact.py --calibrate --calibration-json out/v393_calibration.json --decay-curve-json out/v393_decay_curve.json`（exit 0，`evidence_level=minutes`）。

- 工件 `out/v393_decay_curve.json|md`，SHA256 `D06225DF0BBC78584B55E6930E5B3A9B4524A749FFDEB72B8E8AE009FC9E78A4`（seed=0，两次独立运行逐位一致）；
- 形成期数 **73**（分钟覆盖 39 月，观察项 D-1）；`alpha0_anchored = A(20) = 0.00220065` vs 旧 `alpha0_calendar = 0.00262866`（**−16.3%**）；
- `phi = 0.9999999999999992`（`fitted`，`decay_source=empirical`）；`m(5)=0.382`（lo −3.853 / hi 1.848）、`m(10)=0.395`（lo −3.361 / hi 1.148）、`m(20)=1`（构造性）；
- `net(5) = −7,159,077`、`net(10) = +905,290`、`net(20) = +18,115,106`（lo +1,684,760）→ **P-002① 达成**；`verdict = {5: flat, 10: flat}`（「未检出衰减 ≠ 无衰减」）；
- `n_by_h` 5→72 / 20→71 / 60→28；`evidence_warnings=[]`；`m_sensitivity` b=1 hi 1.6244 / b=6 hi 1.7070；
- 装配性能 0.100 s / 峰值 4.4 MB（73×60、reps=1000、3 轮块长）；
- 默认 `out/capacity_impact.json` SHA256 `82728CE1…` 逐位不变。

### 测试

- 新增 10 例（T393-1 ~ T393-10），先红（10 failed）后绿；
- 全量 `pytest -q`：**2057 passed / 15 skipped / 0 failed**（三次一致：796.71 s / 825.00 s / Step 10 审计独立复跑 1025.25 s）；
  D-3 已定位关闭：7 个整模块级 skip 测试文件，`2065 nodes + 7 = 2072 = 2057+15` 恒等式自洽（[AUDIT.md](spec/v393-alpha-decay-model/AUDIT.md) §4）。

### 步骤 10 审计（Step 10，独立子代理）

- 结论 **PASS（有条件）**：0 P1 / 2 P2 / 4 P3 → 遗留修复包 **P-012**（审计不写代码，D-002 整改口径）；
- P2：F-1 bootstrap 回退分支 net lo/hi 漏乘 (h_m/h)（默认调用图不可达）；F-2 IMPLEMENTATION §5 通过线「≥2065 passed」算术错误（passed 字面上限 2057 恰=实测）；
- P3：F-3 phi_status 枚举未同步 DESIGN / F-4 DecayCurve 死类型 / F-5 D5 plateau 落点 / F-6 退化态 m_sensitivity 口径；
- Iron Law 恒真式 0 项；CHECKLIST **accepted**（70/70）。


## v3.9.2 — 校准读数口径一致性修复（对应路线图批次 v3.9.2）(已实施, 2026-11-20)

### 概览

v3.9.1 审计暴露三处校准读数异常：`c=15.07`、`rho=-0.147`（`retention(5)<0`）、
`temporary≈0.4%`。诊断结论：前两者为实现层口径缺陷（σ 用分钟 bar 波动、rho 用月频序列
且无负值守卫、c 无识别门槛），第三者为实现替代理（组合日超额 AR(1)，非 T+1 反转）。
本批只修口径与守卫，不动模型族、不改默认输出。

### 核心产出

- **E0** `core/impact.py`：新增 `fit_r2`、`C_R2_MIN=0.05`、`C_RANGE=(0.1, 2.0)`。
- **E1** `shell/panels.py`：冲击样本 σ 改为日收益 std（与 impact 同尺度）；
  `sqrt` 输出 `r2/identifiable`；不可识别时成本回退 `c=0.5` 并留痕；
  `rho` 改用日频 `excess_d`，`rho<=0 → 1.0`；`temporary_basis="portfolio_ar1_proxy"`。
- **E2** `shell/runner.py`：输出 `c_r2/c_identifiable/c_effective/temporary_basis`；
  rho 负值守卫。
- 包版本 **3.9.2**（6 处代码锚点 + CHANGELOG）。

### 实测读数

- 默认 `out/capacity_impact.json` SHA256 `82728CE1…` 逐位不变；
- 校准重跑（39 月，`out/v392_calibration.json`）：`c` **15.0677 → 2.9107**（r2=0.5606；
  仍超 `[0.1,2.0]` → `c_effective=0.5`、`impact_bps_source=default_fallback`）；
  `cost_by_h` **91.54M/45.77M/22.88M → 15.57M/7.78M/3.89M**；
  `rho` **-0.147（月频）→ +0.114（日频）**，retention 无负值；
  `temporary_share` 保持 `[0,0,0.0042]` 并标 `portfolio_ar1_proxy`；
- **FO-1（范围外）**：日频 rho=0.114 使 `net(h)` 仍 ≈ `−cost(h)`；根因是「已实现收益 AR(1)」
  不是 alpha 衰减，登记 v3.9.3 P0。

### 测试

- 新增 8 例（T1-T7 + 步骤 10 审计补 T9），先红后绿；
- 全量 `pytest -q`：**2055 passed / 15 skipped / 0 failed**（772.15 s）；
- 步骤 10 审计修复 3 项：A-1 rho 短序列守卫（MINOR）、A-2 G3/G4 口径勘误（文档）、
  A-3 `impact.py __all__` 越界回归（MAJOR，首跑 1 failed → 回退 5 项后全绿）。


### 文档与证据

- 调研 / 设计 / 实施 / 验收：`spec/v392-calibration-unit-fix/RESEARCH.md`、
  `spec/v392-calibration-unit-fix/DESIGN.md`、
  `spec/v392-calibration-unit-fix/IMPLEMENTATION.md`、
  `spec/v392-calibration-unit-fix/CHECKLIST.md`、
  `spec/v392-calibration-unit-fix/CONSISTENCY_REVIEW.md`；
- 步骤 10 审计：[AUDIT.md](spec/v392-calibration-unit-fix/AUDIT.md)
  （本批范围 PASS；范围外失败 G5/FO-1 已披露）；
- 工件：`out/v392_calibration.json` / `.md`、`out/v392_junit.xml`。

### 已知限制

- 默认路径仍不产出 `decay/temporary_share/impact_curve`（仅 `--calibrate` 分支）；
- `temporary_share` 为组合日超额 AR(1) 代理，不是 T+1 反转，不进入容量；
- `net(h)` 仍 ≈ `−cost(h)`（日频 rho 半衰期 0.32 天），根因见 FO-1 → v3.9.3 P0。

## v3.9.1 — 真实分钟面板编排接线（对应路线图批次 v3.8.1）(已实施, 2026-11-20)

### 概览

v3.8.0 交付执行/容量证据层时，分钟面板尚未接线：λ 反解、`lambda_fill_ratio`、
`partial_month` 与覆盖度门禁只停留在设计。v3.9.1 把分钟层接入 `--calibrate` 分支：
日级「股票×日」聚合 → HAC λ 回归 → 缩尾 + 行业×规模五分位填充 → 观测样本 →
冲击模型拟合 → 日频 temporary/rho/alpha0/cost(h)/plateau_sd → 报告四段。
默认路径零改动。

### 核心产出

- **E0** `backtest/execution/config.py`：19 字段（删 `tau_max_minutes`，
  增 `minute_start/minute_end/lambda_min_days/adv_window_days`）；
  `shell/loaders.py`：`MIN_STOCK_CODE=1` 过滤修复、`MinuteDayAggregate`、
  `load_month_regression`（锁定 bar 的 `s_t=0`、`amount` 全量）。
- **E1/E2** 新增 `shell/panels.py`：`MinutePanelBuilder`（λ 仅收 `p<0.05 且 λ>0`、
  `fill_ratio>0.30 → c_interval_only`、样本 ≤200,000、覆盖度/`panel_hash`/月缓存）、
  `build_daily_panels`、`assemble_panels`、`coverage_gate`。
- **E3** `shell/runner.py`：κ 情景 `sorted({1.0, cfg.kappa, 2.0})`；
  `block_size_mode != auto` 抛 `ValueError`（2 处，默认逐位不变）。
- **E4** `scripts/verify_capacity_impact.py`：`build_panels` 增 `adj_price` 键；
  `build_portfolio_panels` / `daily_ref` / `attach_panel_meta`；
  `--no-minute` / `--panel-cache` / `--force-coverage`；覆盖度不达标 `return 2`。
- **E5** `shell/report.py`：新增面板覆盖度 / λ 显著性与填充 / 窗长容量 /
  持有期净收益四段；缺键整段跳过，`evidence_level` 仍必填。
- **E6** 新增 `tests/test_minute_panels.py`（19 例）+ `test_execution_capacity.py`
  追加 2 例（T381-19/21）；T381-22 为全量门禁。

### 行为变更与零变更

- 默认路径 `python scripts/verify_capacity_impact.py` 输出逐位不变，
  `out/capacity_impact.json` SHA256 `82728CE1…` 不变。
- `--calibrate` 未加 `--no-minute` 时走真实分钟面板；覆盖度门禁失败默认 `return 2`，
  `--force-coverage` 放行并留痕 warning。

### 测试

- 新增 21 个可执行用例（`test_minute_panels.py` 19 + `test_execution_capacity.py` 2；
  T381-22 为全量门禁本身），全量 **2047 passed / 15 skipped / 0 failed**（808.70 s）。

### 实测读数（2026-11-20）

- 默认快照：双跑 + 改前备份三方一致 `SHA256 82728CE1…`（容差 0）。
- 日频层：`--calibrate --no-minute` exit 0，3.2 s，`evidence_level=ohlc`（4 段按缺键跳过）。
- 全量校准：`--calibrate` exit 0，14.52 min，`evidence_level=minutes`；
  39 月 `missing_months=[]`、覆盖度中位 **1.097** / 最差 **1.050** / 深主板 **57020**；
  `lambda_stats`: n_total 170761 / n_sig 167938 / fill_ratio **1.65%** / `c_interval_only=False`；
  `impact_samples.n=200000`（cap 命中，等距抽样）。
- 单月性能：**27.37 s**、tracemalloc 峰值 **296.6 MB**（预算 60 s / 300 MB）；
  优化过程 337.6 → 296.6 MB（`panel_hash=ccdede88…` 不变，数值逐位等价）。
- 步骤 9 追加修复：`coverage_gate` 入参归一化（`PanelCoverage` → dict）；
  `--no-minute` 证据等级由 `minutes` 降为 `ohlc`；报告追加 R7/R9 脚注。
- 已知偏差：行业表月末缺失的两级退化链未实现（`industry=None` 单独成组、无静默填 0），
  CHECKLIST X5 登记为失败 → 步骤 10 审计裁决：填充值仅展示用（无下游数值消费），
  改 EXECUTION §3.5 口径与实现对齐，X5 转「通过（偏差登记）」，
  见 `docs/audit/2026-11-20-v3.8.1-minute-panel-wiring-audit.md`。
- 步骤 10 审计复审（2026-11-20）：**PASS** — 独立复跑全量 2047/15/0（869.00 s）、
  默认 SHA 逐位一致、G6 最终代码复跑 `lambda_stats` 与步骤 9 逐位一致、G7 升级端到端证据；
  清单终态 79 通过 / 0 失败 / 0 阻塞 / 5 N/A；
  审计观察：覆盖度 `universe_ratio` 可 >1、`--force-coverage` 警告未进 `evidence_warnings`（建议未来批次）。

## v3.9.0 — 模拟数据验证骨架与步骤级追溯 (已实施, 2026-11-19)

### 概览

v3.8.0 建成执行/容量证据层，但主回测链路仍缺交易现实性建模、边界场景覆盖与步骤级追溯。
v3.9.0 补齐验证骨架：6 场景合成面板工厂（含 ground truth）、12 条常驻不变量、
步骤级 JSONL 追溯（首个分歧定位）、独立交易现实性层、验证报告聚合器；
并修复 `_build_positions` 的 NaN 排序缺陷（B2）。

### 核心产出

- **E0** `backtest/engine.py`：B2 修复——`np.argsort` 作用域收窄到 `valid_idx`（4 insertions / 3 deletions）。
  NaN 股票不再进入多头侧：真实单日 2023-03-01 271→0、conftest 262→0、synth:stale 339→0。
- **E1** `tests/synthetic/`：`PanelSpec`/`SyntheticPanel` 确定性生成 + 6 场景
  （clean / limit_heavy / suspend_gap / st_mixed / stale_factor / adj_jump），
  `true_limit_hit` / `true_suspend` ground truth；普通日 round2 后 `high-low>=0.02`。
- **E2** `tests/invariants/`：12 条不变量（bound / monotonic / invariant / equivalence）+ 2 项注册表自检，
  场景与结果双缓存，`pytest tests/invariants` 14 例 < 0.5 s。
- **E3** `backtest/trace.py`：JSONL 一行一 step（trace_version / code_version / seq / params_hash /
  inputs / outputs / diagnostics / status），`content_hash` 对 DataFrame 追加 sum/mean/NaN 计数，
  `find_first_divergence` 定位首个分歧；`enabled=False` 零 IO。
- **E4** `backtest/tradability.py`：`DEFAULT_LIMIT_RULES` 11 条版本化规则、
  `apply_tradability` 七步权重推进（涨停禁买 / 跌停禁卖 / 停牌冻结 / pending 补单 / T+1）、
  `CostModel` 四项成本（佣金 2.5bp 最低 5 元 / 印花税 5bp 仅卖出 / 过户费 0.1bp 双向 / slippage 0）。
- **E5** `scripts/verify_all.py` + 4 脚本 `--report-json`（默认 `None`）：
  `summary.json` 聚合 `overall` / `missing`，缺失容忍，`--strict` 可升级为失败。

### 行为变更与零变更

- B2 改变含 NaN 因子时的历史仓位与 turnover；方向依数据而定（conftest 均值 +0.009、
  synth:stale −0.087），量化见 `out/v390_b2_impact.txt`。
- 默认路径 `out/capacity_impact.json` 双跑 SHA256 `82728CE1…` 逐位不变；
  `backtest/__init__.py` / `backtest/data_contract.py` 零 diff；`--report-json` 默认不写盘。

### 测试

- 新增 18 个文件（生产 2 / 测试 3 包 + 5 测试文件 / 聚合脚本 1），40 例新增测试
  （37 例 TDD + 步骤 10 异构审计回归 3 例：content_hash ±inf 区分 / adj_jump 网格校验次序 /
  verify_all.collect 顶层非 dict 容错）；
  分模块耗时：build 5.7 ms、invariants 415 ms、tradability 9.5 ms、trace 0.4 ms/step、verify_all 91 ms。
- 全量回归 **2026 passed / 15 skipped / 0 failed**（757.4 s，junit tests=2041；步骤 10 异构审计复跑）；
  门禁 G1-G8 全部通过，读数见 `docs/audit/CHECKLIST_V3.9.0_VALIDATION_SKELETON.md` §6
  （CHECKLIST 终态：102 通过 / 0 失败 / 6 不适用，108 项）。

### 已知限制

- `tradability` 为独立函数，默认不接入引擎（P-1 裁决）；引擎集成留待后续批次。
- 新股上市初期不设涨跌幅、停牌复牌首日、盘中临停、集合竞价细则未建模。
- 过户费采用 2022-04-29 起现行费率，历史回测按现值近似，不做费率版本化（U13）。

## v3.8.0 — 多日执行模型 + Regime 容量压力测试 (已实施, 2026-11-19)

### 概览

v3.7.0 解决了统计证据链，但容量口径仍是 stylized（sqrt 与 linear 内部差 4 倍、
无 regime 压力、无冲击参数校准）。v3.8.0 新增 `backtest/execution/` 证据层：
4 个 Protocol 端口、4 个冲击模型、3 个价差代理、BVC 分类、AR(1) 衰减核、
regime 容量与 κ 情景、AveW 多窗平均。**默认无参数路径输出逐位不变**（D2），
校准结果只进 `out/capacity_calibration.*`，不回写 `SQRT_C`。

### 核心产出

- **E0** `backtest/execution/{ports,config,registry}.py` + `core/{bootstrap,spread}.py`
  + `shell/loaders.py`：4 端口纯契约；`CalibrationConfig.config_hash()` 为
  sha256(canonical json)；`MinuteLoader` 逐日流式聚合（月 σ 由 rsum/r2sum 反解）、
  `DailyLoader`、`has_pyarrow()` 能力探测；CS/AR/Amihud 三代理
- **E1** `core/classification.py`：`normal_cdf`（`math.erf`）、无前视
  `rolling_sigma`、`BVC.classify`、`detect_limit_lock`（`h==l` 或零量平盘）
- **E2** `core/impact.py`：sqrt/linear/log/power 四模型 + CV-RMSE 选型（容差 10%）
  + 三档 `c`（`c_stress = max(0.5, c_ci_upper)`）
- **E3** `core/impact.py::temporary_share`：T+1 reversal 分离，bootstrap 块长取
  `auto_block_size`，返回 `(share, ci_lo, ci_hi)`
- **E4** `core/decay.py`：`estimate_rho`（NW HAC，CI 覆盖 1 时退化 `rho=1`）、
  `retention`/`half_life`/`execution_days`（超 `d_max` 标未成交）/`net_curve`/`plateau`
- **E5** `shell/runner.py`：`regime_capacity` 主值取 `min` 并同时报 median；
  κ ∈ {1.0, 1.5, 2.0} 三情景
- **E6** `shell/runner.py::average_capacity`：4 窗对**预测容量**等权平均；
  `spread>0.30` 降级为最差窗并写 `evidence_warnings`
- **E7** `scripts/verify_capacity_impact.py`：新增 `--calibrate` /
  `--evidence-level {auto,minutes,ohlc,daily}` / `--diagnose-window` /
  `--calibration-json`；校准报告含 `ratio(p)` 诊断（design §9.5）与「报告限制」
- **E8** 版本号统一 3.8.0（6 处锚点）；`pyproject` 新增 optional extra
  `calib = ["pyarrow>=14.0.0"]`，`all` 追加 pyarrow，核心依赖零变化

### 口径与零变更

- `out/capacity_impact.json`（无参数）键集合与数值逐位不变（T380-51/52 双跑比对）。
- `backtest/__init__.py` / `backtest/data_contract.py` 零 diff；`SQRT_C` /
  `LINEAR_K` / `CAP_LEVELS` 原值不动，校准不回写默认 `c`（D2）。
- 证据等级三级降级（minutes / ohlc / daily），输出必带 `evidence_level`。

### 测试

- 新增测试文件 9 个共 **56 例**（T380-01~56）：先红（52 failed / 2 passed / 2 errors）
  后绿（56 passed / 0 failed，3.74 s）。全量回归见 CHECKLIST §5.1 G4。

### 步骤 10 异构复审（2026-11-19）

- **PASS_WITH_FIXES**：5 视角 × 48 探针终跑 **48 PASS / 0 FAIL / 4 P3 披露**
  （探针勘误 9 项留档定性）；唯一真实缺陷 **H2** —— `detect_limit_lock` 零量分支
  缺 `c==l`（EXECUTION §2.7 spec 偏离），已修复并新增回归 **T380-25b**（56→57 例）；
  修复后 9 文件 57 例全绿（3.53 s），全量复跑 **1986 passed / 15 skipped / 0 failed**
  （junit tests=2001）。真实数据零影响核验：2023-03-01 单日 frozen_old=new=168,391 bar。
  探针留档 `out/review_v380_results.txt`；详见
  `docs/audit/2026-11-19-v3.8.0-execution-capacity-audit.md`。

### 已知限制（v3.8.1 待办）

- 真实分钟面板编排未接入 `run_calibration`（当前仅消费注入 `panels`）：
  λ 面板端到端、`lambda_fill_ratio` 降级、`partial_month` 标记随接线落地。

## v3.7.0 — P1 统计证据链: 样本外协议 + 选择偏差 + 效应量/门禁 (已实施, 2026-11-18)

### 概览

v3.6.0 解决了"记录可复现"，但结论本身仍缺统计防线：单路径回测、多重试验未折算、
规格曲线只能看摘要、显著性无效应量与区间。v3.7.0 新增四个平级模块
（`cross_validation` / `overfitting` / `effect_size` 互不 import），扩展规格日志与
多重检验台账，并给出 G2 门禁的纯函数评估。**既有无参调用路径逐位不变**。

### 核心产出

- **E1** `backtest/cross_validation.py`（新增）: `PurgedKFold`（5 折基线）+
  `CombinatorialPurgedKFold`（`N=6, k=2` → 15 路径）；purge/embargo 各 1 期，
  训练集剔除 `[a−max(purge,label_horizon), b+embargo]`；`HoldoutRegistry`
  （DuckDB `cv_holdout`，64 位 `holdout_id`，跨 batch 重叠拒绝、同 batch 幂等、
  `dev_mask` 末尾裁 purge、`assert_locked_before`）
- **E2** `backtest/overfitting.py`（新增）: `deflated_sharpe_ratio`（逐期 SR、
  `N=n_trials`、`V[SR_n]` 默认 `1/(T−1)` 或 `trial_sharpes`）+
  `probability_of_backtest_overfitting`（CSCV 严格 `T%S==0`、S 偶数、平均秩）+
  `trim_to_divisible(keep='recent')`（58→56）；`sharpe_ratio` 为唯一公共 Sharpe 实现
- **E3** `backtest/effect_size.py`（新增）: `newey_west_se`（Bartlett，默认
  `max(1, floor(4*(T/100)^(2/9)))`，`Omega/T`，对齐 statsmodels `use_correction=False`）+
  `mean_ci` / `sharpe_ci`（stationary bootstrap）+ `effect_summary` 分派
- **E4** `specification_logger`（扩展）: `log_run` v2 可选字段
  （`spec_id`/`values`/`value_type`/`parent_run_id`/`spec`，`schema_version="2"`，
  `content_hash` 64 位）；`get_specification_matrix`（strict / 非 strict 截断）；
  `joint_inference`（null-imposed 去中心化 bootstrap，输出 median / share_significant /
  Stouffer Z，`resampling='stationary'|'iid'`）；`pre_registration.commit` 增加
  `content_hash`，`verify_compliance` 优先按内容哈希匹配
- **E5** `multiple_testing_ledger`（扩展）: `FamilySpec.stage ∈ {factor, portfolio}`；
  portfolio family 仅接受 S4/portfolio trial；`holdout_checker` 回调注入
- **E6** `governance`（扩展）: `G2Policy` + `evaluate_g2` 纯函数；FDR 轨
  （bh/by）与 FWER 轨（bonferroni/holm/romano_wolf/white_rc/hansen_spa）分轨；
  失败 `action='downgrade'` 且不写库
- **E7** `scripts/verify_stat_evidence.py`（新增）: `--section {all,dsr,pbo,curve,leakage}`
  四段自检，输出 `out/stat_evidence_verification.json`；Stata 对拍 P1 两项 detail 记为 N/A
- **E8** 版本号统一 3.7.0（`__init__.py` / `config_v2.py` / `reporting.py` /
  `pyproject.toml` / `test_fix3_version_unification.py` / `verify_fix3_manual.py`）

### 口径与零变更

- 缓存代际仍 `v2.3.0-cache`；零新增依赖；`backtest/__init__.py` 无改动；
  `get_specification_curve` 5 键返回不变。
- 旧 `log_run` 调用字段集合逐字不变；`resampling` 默认 `stationary`，`iid` 可复刻原文。

### 测试

- 新增测试文件 5 个共 **55 例**（T01-T14b / T15-T26b / T27-T33b / T34-T40c / T41-T46b，含异构复审修正 3 例）；
  扩展既有测试文件 **8 例**（规格日志 v2 3 例 + 台账 stage 5 例）；
  全量回归 **1929 passed / 15 skipped / 0 failed**（对比 v3.6.0 基线 1866，+63，零新增失败）；
  异构复审 PASS_WITH_FIXES：唯一 P2 真实缺陷 H1（常数序列浮点假阳绕过零方差守卫）已修复（5 处
  `np.ptp == 0` 显式拦截），其余 7 项 FAIL 均为探针勘误；详见
  [审计报告](docs/audit/2026-11-18-v3.7.0-stat-evidence-chain-audit.md)；
  TDD 红→绿读数见 [EXECUTION §5.3](docs/EXECUTION_V3.7.0_STAT_EVIDENCE_CHAIN.md)

## v3.6.0 — 治理底座 P0 四件套: GR-1~GR-4 + 研究入口契约 (已实施, 2026-11-18)

### 概览

研究结论长期缺少可复现载体：记录散落于脚本输出、血缘断链仅 warning、口径为自由字符串、
多重检验"试了多少次"无台账、真实数据缺口可静默进入结论。v3.6.0 新增四个平级模块
（互不 import）并在研究入口接入可选契约门禁，**默认路径逐位不变**。

### 核心产出

- **GR-1** `backtest/governance.py`: `GovernanceRecord`（schema 1.0.0, frozen,
  `extra='forbid'`）+ `GovernanceStore`（DuckDB 主 / JSONL fallback，`lock_path`
  文件锁）；`record_id` 确定性；stage S0-S6 条件校验；production 全门禁；
  `ancestors()` 返回 `AncestorEntry`（断链 `reason=missing`、跨 schema `reason=schema_mismatch`，
  循环抛 `GovernanceError`）；口径新增 `price_convention`（进 `ID_FIELDS`），
  `tradable_convention` 强制写入 `st_source`/`suspend_source`（默认
  `name_proxy`/`event_rebuild`）
- **GR-2** `backtest/data_contract.py`: 字段级 schema/freshness/PIT/覆盖率/值域/
  一致性/日历检查；`strict=False` 默认只报告；`expected_missing_tail` lag 扣减；
  `known_gaps` 结构化（`barra_stale`/`industry_stale`）；`qfq` 禁止 production/G4
- **GR-3** `backtest/golden_master.py` + `tests/golden/govbase_v1_synth`
  （36 月 × 20 股 × 2 因子, `seed=20261117`）；`rtol=1e-10`/`atol=1e-12`；
  capture 不覆盖，force 需 reason + reviewer
- **GR-4** `backtest/multiple_testing_ledger.py`: family 预注册（早于数据观察）、
  BH/BY/Romano-Wolf/White/SPA、三分母校验、backfill 隔离、`result_id` 稳定；
  `WhiteRealityCheck.test`/`HansenSPA.test` 追加 `bootstrap_indices`（默认 None 逐值不变）
- **E6** `pipelines_v2.py`: `set_governance_hook()`（默认 None，9 字段事件）
- **E7** `scripts/contract_gate.py` + 容量/多头端 `--contract*` 接线
  （默认关闭；FAIL → exit 2；报告 `out/<prefix>_contract.{json,md}`）

### 口径与零变更

- 默认路径（不设 hook / 不传 `--contract*` / `bootstrap_indices=None`）与 v3.5.3 一致；
  缓存代际不变 `v2.3.0-cache`；零新增依赖；`backtest/__init__.py` 无改动。
- 真实数据 dry-run：两研究入口 `--contract-only` 均 exit 2，正确拦截
  `mv` 5 日缺口（`last_full=2026-01-23, end=2026-01-30`）。

### 测试

- 新增 56 例（E1-E8 + T41-T50）：governance 15 / data_contract 7 / golden 5 /
  ledger 12 / hook+补充 15 / contract_gate 2；TDD 红→绿读数见
  [EXECUTION §5.3](docs/EXECUTION_V3.6.0_GOVERNANCE_BASE.md)
- 全量回归 **1920 passed / 7 skipped / 13 subtests**（742.43s；基线 1864，+56 全为本批新增；0 失败 0 新增 skip）
- 异构复审 PASS_WITH_NOTES（P1-P8，0 推翻 / 0 重大；F1 锁等待语义、F2 注入路径口径已披露）

### 复审修复包（R1-R4 → F1-F4，同版本折入不 bump）

- **F1 / P2-5（MAJOR）**：`build()` 新增 `ID_DEFAULTS` 注入（`price_convention="hfq"`、
  `gate_policy_version="1.0.0"`），消除「省略 vs 显式默认」的 `record_id` 分裂
  （红读数：`7d90...` vs `6d04...`）——语义等价记录不再绕过 `on_conflict` 去重
- **F2 / P3-5**：golden 场景判定改 `G4` 存在且 `passed`，G4 失败留档可携带 qfq
- **F3 / P3-6**：`known_gaps` 码名集中映射 `GAP_CODE_BY_FIELD`（对外码名不变）
- **F4 / P3-7**：`verify_fix3_manual.py` `OLD_VERSIONS` 追加 3.5.3
- 新增 T51-T54 5 例（T54 按两个断言要点实现为 test_08/test_09 两例；红→绿读数见
  [FIX_PACK §5](docs/EXECUTION_V3.6.0_FIX_PACK.md)）；依据见独立复审
  `out/review_v360_t46_e8_results.txt`
- 修复包后全量回归 **1925 passed / 7 skipped / 13 subtests**（898.75s；1920 + 5，0 失败；耗时比 0.59）

### 性能包（P2-1 → O1-O5，同版本折入不 bump）

- **O1** `append_many` 10k：7.605s → **0.724s**（单次 `model_dump`、`canonical_json` JSON-native 快路径、
  批量存在性 `JOIN`；预算按序列化下界重估 0.1→1.0s）
- **O2** `apply_bh_fdr` 100k：0.0749s → **0.0156s**（argsort + 反向累积 min + searchsorted）
- **O3** `apply_romano_wolf` 1000×1000：3.1232s → **0.0071s**（前缀第 k 小恒等于整行第 k 小）
- **O4** White/SPA T=1000,K=100,B=1000：288.85s / 158.95s → **7.56s / 3.89s**
  （索引矩阵按 t 递推 + 128MB 分块；峰值内存 170.9 / 170.2 MB）
- **O5** `GoldenMaster.compare` 24×300×4：0.1372s → **0.0586s**（`_to_long` numpy 构造，行序复刻 melt）
- 新增 T55-T59 5 函数 / 8 用例（对拍 + 批量语义 + 复杂度烟测；红→绿读数见
  [PERF_PACK §5](docs/EXECUTION_V3.6.0_PERF_PACK.md)）
- 白盒口径：White/SPA 同 seed 结果与旧实现不同（无硬编码 p 值断言）；BH ties 固定稳定序（DR-P2）
- 性能包后全量回归 **1933 passed / 7 skipped / 13 subtests**（1059.21s；1925 + 8，0 失败；seq 32）

### 版本与文档

- 版本 **3.6.0**（6 锚点）；ADR-050~054 落 [DECISIONS.md](DECISIONS.md)；
  [EXECUTION](docs/EXECUTION_V3.6.0_GOVERNANCE_BASE.md) /
  [CHECKLIST](docs/audit/CHECKLIST_V3.6.0_GOVERNANCE_BASE.md) /
  [CONSISTENCY_REVIEW](docs/audit/CONSISTENCY_REVIEW_V3.6.0_GOVERNANCE_BASE.md) 入库
- 设计文档 `docs/private/DESIGN_GOVERNANCE_BASE.md` v1.2 按仓库策略不入库

---

## v3.5.3 — sup-F 自相关稳健临界值: AR(1) sieve bootstrap (已实施, 2026-11-17)

### 概览

Andrews (1993) sup-F 的渐近临界值假设**无序列相关**。`BreakpointDetector`
默认 `sup_f_method='asymptotic'` 直接在 raw β_t 上做网格 Chow 检验, 当 β_t 存在
AR(1) 自相关时严重过度拒绝: 名义 5% 下 φ=0.2 / 0.5 / 0.8 的实测拒绝率为
**14.0% / 50.0% / 93.3%** (T=240, 300 次重复)。

既有 `sup_f_method='bootstrap'` 的实现是 `rng.randn(B, T)` 的 **iid 高斯**序列,
并不保留自相关, 与 docstring 声称的「保留序列相关」不一致 (文档-实现不一致缺陷);
且 `FactorHealthDiagnoser` 固定构造默认 asymptotic 检测器, 无法 opt-in。

v3.5.3 把 bootstrap 路径重写为 **AR(1) sieve 残差自助** (与
`StructuralBreakMonitor._bootstrap_pvalue` 的设计 m10 同源), 作为 opt-in;
**默认渐近路径逐位不变**。

### 核心产出

- `BreakpointDetector.__init__(..., sup_f_method='asymptotic'|'bootstrap',
  n_bootstrap=1000, random_state=42)`; 非法方法 → `ValueError`;
  bootstrap 且 `n_bootstrap < 50` → `ValueError`
- `detect` 将观测序列 `y` 传入临界值计算; 输出新增 `critical_method`
  (有断点时 8 键 / 无断点或退化路径 7 键, 原键逐位不变)
- `_bootstrap_sup_f_crit` 重写: OLS 估计 `y_t = c + φ y_{t-1} + e_t`,
  φ clip ±0.99, 残差中心化后有放回重采样, burn-in 50 递归生成 B 条伪序列,
  取 sup-F* 的 `1-α` 分位
- 新增 `_sup_f_batch(Y, ε)`: 累积和向量化, O(B·T) 而非 O(B·T²)
- `FactorHealthDiagnoser.__init__(..., sup_f_method, n_bootstrap, random_state)`
  透传; `diagnose` 输出新增 `chow_critical` / `breakpoint_sup_f_method`
  (28 → 30 键), `breakpoint_sup_f_method` 明确当前生效方法
- 版本 **3.5.3** (6 锚点); 缓存代际不变 `v2.3.0-cache`; 无新依赖

### 选型证据 (T=240, B=300, α=5%, 300 次重复)

**Size (H0 下拒绝率)**

| 方法 | φ=0 | φ=0.2 | φ=0.5 | φ=0.8 |
|------|-----|-------|-------|-------|
| asymptotic | 4.7% | 14.0% | 50.0% | 93.3% |
| iid bootstrap (旧) | 5.3% | 18.7% | 49.0% | 93.3% |
| **AR(1) sieve (新)** | **5.3%** | **5.7%** | **5.3%** | **8.7%** |
| AR(p) sieve (BIC) | 5.3% | 4.7% | 5.0% | 7.7% |
| moving-block bootstrap | 4.0% | 6.0% | 13.7% | 35.3% |

**Power (Δ=1σ 均值断点)**

| 方法 | φ=0.5 | φ=0.8 |
|------|-------|-------|
| asymptotic | 100% | 99.7% |
| **AR(1) sieve** | **93.7%** | 44.0% |
| moving-block | 97.3% | 87.0% |

> φ=0.8 处 AR(1) sieve 的 power 明显下降, 是「以 size 换 power」的代价;
> 本项目 β_t 实测 |φ| ≤ 0.21, 处于 AR(1) sieve 的稳健区间。
> 短样本 T=120: φ=0.5 power 63.7% (渐近 97.0% 但 size 43%), φ=0.8 power 25.0% —
> 高自相关 + 短样本时不建议依赖 bootstrap 判定「无断点」。

**实现口径复核 (T=240, B=300, 150 次重复)**

| 场景 | 渐近 | 实现 AR(1) sieve |
|------|------|------------------|
| φ=0 size | 4.7% | 4.0% |
| φ=0.5 size | 48.7% | **4.7%** |
| φ=0.5 power | 100% | **96.0%** |

**真实 β_t (4 因子, T=68-70)**

| 因子 | φ̂ | sup-F | 渐近临界 | AR(1) 临界 | 标签 |
|------|-----|-------|---------|-----------|------|
| momentum_1m | -0.070 | 1.74 | 8.85 | 7.94 | 无断点 |
| reversal_1w | -0.069 | 1.82 | 8.85 | 7.43 | 无断点 |
| volatility_1m | -0.141 | 3.08 | 8.85 | 6.10 | 无断点 |
| amihud_1m | +0.208 | 2.67 | 8.85 | 12.22 | 无断点 |

### 变更文件

| 文件 | 变更 |
|------|------|
| `modules/factor_health/__init__.py` | `BreakpointDetector` 构造 + 参数校验; `detect` 传 `y` + `critical_method`; `_sup_f_critical_value` 新签名; `_bootstrap_sup_f_crit` 重写; 新增 `_sup_f_batch`; `FactorHealthDiagnoser` 透传 + `diagnose` +2 键 |
| `tests/unit/test_layer3_factor_health.py` | 新增 `TestAutocorrRobustSupF` (F1-F11, +11 passed; layer3 60 passed) |
| 6 处版本锚点 | 3.5.2 → 3.5.3 |
| `DECISIONS.md` | ADR-049 |
| `docs/` | RESEARCH / DESIGN(private) / EXECUTION / 审计 / PROJECT_STATUS / DEV_PROGRESS / CODE_WIKI / ARCHITECTURE |

### 局限

- AR(1) sieve 只修正**一阶**自相关; 高阶或长记忆序列仍可能过度拒绝
  (AR(p) 探针在 φ=0.8 略优, 但短样本易过拟合, 未采纳);
- φ=0.8 时 power 44.0% (T=240) / 25.0% (T=120), 高自相关下「不拒绝」证据弱;
- 默认为 `'asymptotic'`, bootstrap 为 opt-in; 真实 4 因子标签在本版前后不变,
  故生产默认路径无行为变化;
- `n_bootstrap` 越大越稳定, 默认 1000 在大 T 下临界值仍是重采样噪声的单调函数,
  跨 seed 波动约 <15% (F6);
- **确定性趋势不在 AR(1) 代理内** (复审 P4): β_t 含线性趋势时 asymptotic 与
  bootstrap 均以 ~100% 拒绝 — 属 sup-F「H0 = 常数均值」的既有语义 (趋势会被
  报告为断点), 非本版引入;
- **近单位根检验失效** (复审 P3): φ̂≈0.97 时 bootstrap 临界值 >430 (发散),
  任何 sup-F 都不拒绝; OLS φ̂ 下偏 ≈ −(1+3φ)/T, clip ±0.99 在 T=240 实际难触发;
- `critical_method` 报告**配置**方法 (复审 P6): 常数序列 / 全 NaN / T<5 的
  退化回退按渐近值或 NaN 计算, 但标签不变 — `has_breakpoint` 判定不受影响。

## v3.5.2 — 多断点路径 NaN 间隙守卫 (已实施, 2026-11-17)

### 概览

关闭 v3.5.0 H7 / v3.5.1 H5 的遗留: `detect_multiple` 先剔除 NaN 再在压缩序列
上分段, 长缺失区间被压缩为相邻两点, 断点可能"跨越"数据间隙。当时点不可观测时
继续输出 `ES` 会把"数据断档"误读为"已定位的结构突变"。

v3.5.2 在 opt-in 多断点路径上增加**连续性守卫**: 标签相关边界跨越
`>= multi_break_gap_min_run` (默认 2) 期缺失时, `ES`/`ES+TD` 降级为 `suspect`;
默认 `single` 模式标签与旧键**逐位不变**。

### 核心产出

- `FactorHealthDiagnoser.__init__(..., multi_break_gap_min_run=2)`; `< 1` → `ValueError`
- `detect_multiple` 新增 5 键: `n_nan` / `n_gaps` / `max_gap_run` /
  `breakpoints_gap_missing` / `gap_missing_at_bp` (13 → 18 键); 分段结果零改动
- `diagnose` 新增 6 键: 上述 5 键 + `breakpoint_gap_risk` (22 → 28 键)
- 守卫依据: `confirmed` → sup-F 断点; 未确认但材料 → 最大位移 BIC 边界
- `has_breakpoint` 语义不变 (`confirmed or material`), 守卫只降级标签
- 不插值、不加权 SSR、不新增临界值表
- 版本 **3.5.2** (6 锚点); 缓存代际不变 `v2.3.0-cache`; 无新依赖

### 守卫证据 (序列级 300 次/配置, T=120, α=0.05)

| 场景 | gap_risk (gmin=2) | ES 旧 | ES 新 |
|------|-------------------|-------|-------|
| 纯噪声 无间隙 | 0.0% | 4.7% | 4.7% |
| 纯噪声 单间隙 g=10 | 0.0% | 6.0% | 6.0% |
| 纯噪声 5×g=3 | 1.3% | 4.3% | 3.7% |
| 纯噪声 散点 5% NaN | 0.0% | 5.0% | 5.0% |
| 真断点 间隙远离 | 0.7% | 92.0% | 91.3% |
| 真断点 散点 NaN | 0.3% | 94.3% | 94.0% |
| 真断点 g=5 正落断点 | 21.7% | 95.3% | 73.7% |
| 真断点 g=10 正落断点 | 17.0% | 93.0% | 76.0% |

gmin 选择: gmin=1 会把"真断点 + 孤立 NaN"误降级 7.3%; gmin=2 降至 0.3%,
且仍能捕获 g≥2 的间隙 → 默认 **2**。

### 变更文件

| 文件 | 变更 |
|------|------|
| `modules/factor_health/__init__.py` | 2 个静态辅助 + `detect_multiple` +5 键 + `diagnose` +6 键 + 守卫分流 (~+110 行); 分段算法零改动 |
| `tests/unit/test_layer3_factor_health.py` | 新增 `TestMultipleBreakpointGapGuard` (G1-G9, +9 passed) |
| 6 处版本锚点 | 3.5.1 → 3.5.2 |
| `DECISIONS.md` | ADR-048 |
| `docs/` | RESEARCH / DESIGN(private) / EXECUTION / 审计 / PROJECT_STATUS / DEV_PROGRESS / CODE_WIKI |

### 局限

- 守卫只在**边界跨越间隙**时触发; 真实断点被间隙遮挡时约 17-22% 的 ES
  降级为 suspect — 属"时点不可观测"的有意保守代价;
- sup-F 在自相关下的过度拒绝与间隙无关 (φ=0.5: 无间隙 48.7% vs g10 45.3%),
  本版不处理;
- gmin=2 是探针校准的工程取值, **不是显著性水平**;
- `'multiple'` 模式仍为 opt-in, 不建议用于批量自动化决策。

## v3.5.1 — 多断点接入 `diagnose` 标签路径 (已实施, 2026-11-17)

### 概览

关闭 ADR-046 遗留 G10: `diagnose()` 新增 **opt-in** `breakpoint_mode='multiple'`,
把 `detect_multiple` 的分段信息接入 `premium_health` / 综合标签。默认
`breakpoint_mode='single'` 的标签、数值与旧键**逐位不变** (20/20 随机面板探针)。

由于异构复审 H5/H6 已量化裸 BIC 的假阳性 (噪声下 39%/33%, T=72/120), 接入采用
**两级门控**: 存在性由单断点 sup-F (`detect`, size 3.3%/5.3%) 判定; 未确认的
BIC 断点仅在材料性 `max|Δ段均值|/sd_within >= 1.0` 时降级为 `suspect`,
**不升级 ES**。这是 docstring 早已定义但此前未实现的 borderline 语义。

### 核心产出

- `diagnose(..., breakpoint_mode='single'|'multiple', m_max=5)`; 非法值 `ValueError`
- 新增私有方法 `_resolve_breakpoints` / `_single_segment_view` / `_multi_break_materiality`
- `FactorHealthDiagnoser.__init__(..., multi_break_shift_threshold=1.0)`
- 输出新增 10 键: `breakpoint_mode` / `breakpoint_confirmed` / `breakpoint_material` /
  `breakpoint_shift_ratio` / `n_breaks` / `breakpoints` / `segment_means` /
  `segment_bounds` / `best_bic_m` / `best_lwz_m`; 旧键语义不变
- 回退规则: sup-F 显著但 BIC 选 m=0 → 保留单断点分段 (n=1)
- `detect` / `detect_multiple` / `PremiumEstimator` / `_detect_decay` / `_combine_label` 零改动
- 版本 **3.5.1** (6 锚点); 缓存代际不变 `v2.3.0-cache`; 无新依赖

### 门控证据 (序列级 300 次/配置; 复审补充面板级实测, 100 次/配置)

| 场景 | sup-F 拒绝 | BIC n>0 | 材料性阈值 1.0 后 (suspect 触发率) |
|------|-----------|---------|------------------|
| 纯噪声 T=72 | 3.3% | 39.0% | 序列 19.3% / 面板 24% |
| 纯噪声 T=120 | 5.3% | 33.3% | 序列 4.0% / 面板 6% |
| 两断点 1.0σ T=120 | 68.7% | 100% | ES = sup-F 确认; 未确认者 suspect |

> 注意 (复审 H2 更正): 纯噪声下的 **ES 率 = sup-F 名义 size** (面板级实测 3%/4%/3%
> @T=72/120/240), 与 v3.5.0 之前的单断点路径一致 — 材料性门控压制的是「未确认 BIC
> 分段」的升级, 不改变 sup-F 自身的 α 水平; 初版「ES 0%」为错误表述。

### 变更文件

| 文件 | 变更 |
|------|------|
| `modules/factor_health/__init__.py` | `diagnose` 分流 + 3 方法 (+201 / −16 行); 断点检测/估计零改动 |
| `tests/unit/test_layer3_factor_health.py` | 新增 `TestDiagnoseMultipleBreakpointMode` (F1-F9, +9 passed) |
| 6 处版本锚点 | 3.5.0 → 3.5.1 |
| `DECISIONS.md` | ADR-047 |
| `docs/` | RESEARCH / DESIGN / EXECUTION / 审计 / PROJECT_STATUS / DEV_PROGRESS / CODE_WIKI |

### 局限

- `suspect` 在 T=72 纯噪声下约 19% (序列级) / 24% (面板级) 触发率 — 它是「需人工复核」
  而非断点声明;
- 材料性阈值是量纲解释 + 探针校准的工程取值, **不是显著性水平**;
- `'multiple'` 模式为 opt-in, 不建议用于批量自动化决策;
- LWZ 仍仅作对照 (`best_lwz_m`), 双断点面板实测 LWZ 选 3 而 BIC 选 2 (H5 再现);
- 异构复审量化: NaN 间隙假断点经两级门控后 has_bp 8.5–12% (裸 BIC 64–70%);
  BIC 在高信噪比真实断点面板会过分段 (单断点面板选 2–3 段最高 37%),
  仅影响分段描述键, 不影响标签与定位。

## v3.5.0 — 多断点支持: Bai-Perron 全局最小 SSR + Stata 对拍 (已实施, 2026-11-16)

### 概览

`BreakpointDetector` 新增 `detect_multiple()` — 以动态规划求**全局最小 SSR**
(Bai & Perron 1998 §3.2), 用 BIC (Yao 1988) 主 / LWZ (Liu-Wu-Zidek 1997) 对照选段数。
`detect()`（单断点网格 sup-F）与 `diagnose()` **零改动**，默认标签路径不变。

断点结果已与主控站 **Stata 18.0 MP** 的官方 `regress`（`e(rss)` / `test`）逐值对拍：
**46 项全 PASS**。实测该 Stata 安装**无**官方 Bai-Perron 命令（`regress, breakpoints()` r(198) /
`estat breakpoints` r(301)），故对拍以官方 OLS 数值库为锚，而非第三方包。

### 核心产出

- `detect_multiple(lambda_hat, m_max=None)` → **13 键**: `has_breakpoint` / `n_breaks` /
  `breakpoints` / `segment_means` / `segment_bounds` / `ssr` / `bic` / `lwz` /
  `best_bic_m` / `best_lwz_m` / `trimming` / `m_max` / `n_valid`
- DP O(m·T²)；`ssr_mat` 用前缀和 `ssr(i,j)=Σy²-(Σy)²/(j-i)`
- **不硬编码** Bai-Perron sup-F 临界值表（无可核实副本），`has_breakpoint := n_breaks > 0`
- trimming `h = max(5, int(0.15T))` 与 `detect` 完全一致；`m_max` 默认 5 并自动下调
- T<30 / trimming 不可行 → 退化结果（不抛异常），延续 v3.4.13 DEFECT-1 契约
- 版本 **3.5.0**（6 锚点）；缓存代际不变 **`v2.3.0-cache`**；无新依赖

### Stata 对拍 (46/46 PASS)

| 级 | 内容 | 误差 |
|----|------|------|
| L1 | 单断点 sup-F（官方 `regress + test`） | F 相对 1.06e-8；argmax 断点完全相同 |
| L2 | m=0/1/2 全局最小 SSR + 断点集（循环 `regress` 读 `e(rss)`） | SSR 相对 ≤8.5e-9；断点逐点相同 |
| L3 | BIC / LWZ（用 Stata 侧 SSR） | 绝对 ≤8.5e-9；`best_*_m` 相同 |

样本: `syn0` 纯噪声 (→m=0) / `syn1` 单断点 (→m=1) / `syn2` 两断点 (→m=2, [40,80]) /
`real` A 股 `turnover_1m` β_t (T=72, **BIC/LWZ 均选 m=0 — 无断点**; [19,37] 为强制
m=2 时的最优位置, 两侧相同。异构复审已更正初版「检出 2 断点」的误读)。

### 变更文件

| 文件 | 变更 |
|------|------|
| `modules/factor_health/__init__.py` | 新增 `detect_multiple` + 6 私有方法 (+176 行) |
| `tests/unit/test_layer3_factor_health.py` | 新增 `TestBreakpointDetectorMultiple` (E1-E8, +133 行) |
| `scripts/stata_breakpoint_crosscheck.py` | 新增 Stata 对拍脚本 (384 行) |
| 6 处版本锚点 | `__init__.py` / `pyproject.toml` / `config_v2.py` / `reporting.py` / `test_fix3_version_unification.py` / `verify_fix3_manual.py` |
| `DECISIONS.md` | ADR-046 |
| `docs/` | RESEARCH / DESIGN(private) / EXECUTION / CHECKLIST / CONSISTENCY / 审计 / PROJECT_STATUS / DEV_PROGRESS / CODE_WIKI |

### 遗留

- 多断点**未接入** `diagnose`（默认仍单断点）；接入需单独评估标签语义；
- m≥3 未做 Stata 对拍（由 Python 内部穷举 E5 补足，DP 递推同构）；
- **假阳性局限（异构复审量化）**：纯噪声下 BIC 选 m>0 的频率 44% (T=72) / 36% (T=120)，
  LWZ (c0=0.1) 达 89%/75% 且与「LWZ 保守」预期相反 — `n_breaks>0` 在短样本上不可直接
  解读为断点存在，LWZ 仅作对照不可单独引用；
- NaN 间隙语义：两段同分布被 NaN 隔开时 54% 概率误报断点（拼接处），断续 β_t 需先检查连续性。

## v3.4.13 — DEFECT-1: BreakpointDetector 短样本退化 (已实施, 2026-11-16)

### 概览

修复 `BreakpointDetector.detect` 在有效点数 `T < 30` 时调用未定义方法
`_no_breakpoint_result` 导致的 `AttributeError`。该分支此前从未被测试覆盖
(现有测试面板 T=200), 唯一生产路径 `FactorHealthDiagnoser.diagnose → detect`
在短样本因子 / 短回测窗 / 消融退化臂上会直接崩溃。

### 核心产出

- 新增 `BreakpointDetector._no_breakpoint_result(T)` → 6 键退化结果:
  `has_breakpoint=False` / `chow_max_stat=0.0` / `critical=nan` /
  `cusum_path=全 NaN (长度=T)` / `pre_mean=post_mean=nan`; 不含 `breakpoint_idx`
  (与正常路径「无断点」分支同构, `diagnose` 用 `.get` → `None`)
- 依据: T<30 时 `min_segment=0.15` 允许的候选切分过少, Andrews (1993) sup-F
  渐近临界值不适用; 与同文件 `_detect_decay` 的 T<30 退化处理一致
- `detect` 本体 / 正常路径 / `diagnose` **零改动**; T≥30 数值逐位不变
- 新增 5 例 (E1-E5): T=10 / 有效 29 (输入 40 含 NaN) / 有效 30 正常路径 /
  `diagnose` T=20 面板 / 全 NaN (T=0)
- 项目版本 **3.4.13** (6 处锚点); 缓存代际不变 **`v2.3.0-cache`**

### 变更文件

| 文件 | 变更 |
|------|------|
| `modules/factor_health/__init__.py` | 新增 `_no_breakpoint_result` (L335-L353) |
| `tests/unit/test_layer3_factor_health.py` | 新增 `TestBreakpointDetectorShortSample` (E1-E5) |
| 6 处版本锚点 | `__init__.py` / `pyproject.toml` / `config_v2.py` / `reporting.py` / `test_fix3_version_unification.py` / `verify_fix3_manual.py` |
| `docs/` | EXECUTION / 审计 / PROJECT_STATUS / DEV_PROGRESS / CODE_WIKI |

## v3.4.12 — 面板 HAC / Premium 标准误 (已实施, 2026-11-16)

### 概览

为 Layer 3 `PremiumEstimator` 的点估计补上标准误: 新增 `estimate_with_errors()`,
对逐期 β_t 与核平滑 λ̂(t) 分别给出 Newey-West HAC 标准误与正态近似 CI。
纯增量 API — `estimate()` / `diagnose()` / `BreakpointDetector` 数值与标签零变更。

### 核心产出

- `PremiumEstimator.estimate_with_errors(factor, forward_returns, alpha=0.05, max_lag=None)` → 14 键 dict
- 逐期横截面 OLS SE: `sqrt(σ̂²_ε / Σ(f−f̄)²)`, `σ̂²_ε = Σε̂²/(n−2)`
- λ̂(t) 的 HAC SE: `sqrt(Ω_t · Σw²)` — 局部 Newey-West 长期方差 (Bartlett 核),
  `Ω_t` 取窗口内残差 `u_s = β_s − λ̂_s`
- 溢价均值: `mean(β_t)` ± `z·sqrt(Ω_β/T_valid)`
- 退化口径: 窗口或全序列有效点 `<3` → 对应 `SE=NaN`; `Ω<0` → `NaN`; `Ω=0` → `SE=0`
- 抽出 `_smooth_betas` (核平滑循环原样迁移) 与 `_hac_long_run_variance`;
  `_cross_sectional_betas` 改为薄包装 → `estimate()` 输出逐位不变
- **独立复审修正 (提交前)**: F1 — λ̂ SE 的 Σw² 改用与 `np.average` 一致的归一化权重
  (旧实现在窗口含 NaN β 时把 SE 低估 ×W_v, 演示值 44%); F2 — `sigma2` 分母
  `max(n_valid−2, 1)` 守卫极小横截面; 新增 E8/E9
- **Stata 18 对拍** ([scripts/verify_hac_stata.py](scripts/verify_hac_stata.py)):
  premium_mean / beta_se / Ω_t 与 `newey` 逐位一致, 唯一系统差 = Stata 默认
  n/(n−k) 自由度修正 (本实现保持 NW(1987) 渐近形式); L4 Monte Carlo 口径自纠:
  固定 β 路径 (抽样误差口径) premium SE/sd=2.11, λ̂ SE/sd=1.77 → **保守**;
  随机 β 路径 0.90/0.81 为含参数漂移的总波动口径, 不用于 CI 覆盖解释
- 项目版本 **3.4.12** (6 处锚点); 缓存代际不变 **`v2.3.0-cache`**

### 变更文件

| 文件 | 变更 |
|------|------|
| `modules/factor_health/__init__.py` | 新增 `estimate_with_errors` / `_smooth_betas` / `_cross_sectional_betas_and_se` / `_hac_long_run_variance`; 复审修正 F1/F2 |
| `tests/unit/test_layer3_factor_health.py` | 新增 `TestPremiumEstimatorErrors` (E1-E9) |
| `scripts/verify_hac_stata.py` | 新增 Stata 18 三层对拍 + Monte Carlo 验证工具 |
| 6 处版本锚点 | `__init__.py` / `pyproject.toml` / `config_v2.py` / `reporting.py` / `test_fix3_version_unification.py` / `verify_fix3_manual.py` |
| `docs/` | RESEARCH / EXECUTION / CHECKLIST / CONSISTENCY_REVIEW / audit / PROJECT_STATUS / DEV_PROGRESS |
| `CODE_WIKI.md` | 头部版本 + §4.13 接口 + 版本历史 |

### 实测矩阵

| 层级 | 对象 | 结果 |
|------|------|------|
| unit | E1-E9 (`TestPremiumEstimatorErrors`) | 新增 **9 passed** (E1-E7: Red **7 failed** → Green; E8/E9 为复审修正固化) |
| 定向回归 | `tests/unit/test_layer3_factor_health.py` | **18 passed** |
| 定向回归 | `tests/test_backtest` | **599 passed / 8 skipped** (基线不变) |
| 全量回归 | `tests/` | **1755 passed / 15 skipped / 0 failed** (基线 1746 → +9) |
| 版本统一 | `test_fix3_version_unification.py` + 手工校验 | **7 passed** + 手工 **6/6** |

### 兼容性

- `estimate()` 签名与数值逐位不变 (共享 `_smooth_betas`, 核平滑循环原样迁移);
- `diagnose()` 不调用新方法 → 标签逻辑零变更;
- 无新增依赖 (`numpy` / `scipy.stats.norm` 已在模块);
- 方法学依据: Fama & MacBeth (1973) DOI 10.1086/260061;
  Newey & West (1987) DOI 10.2307/1913610; Newey & West (1994) DOI 10.2307/2297912;
- 缓存不失效。

## v3.4.11 — 技术债小包 (已实施, 2026-11-16)

### 概览

清理 v3.4.10 与 MAD 实验留下的三项独立技术债; 另有一项路演候选经核实后**明确不修复**。

### 核心产出

- **T1**: `ledoit_wolf_hac_test` 移除从未被读取的 `alpha` 参数;
  `compare` 调用同步改为两参数 (显著性判定仍由 `compare` 的 `self.alpha` 完成)
- **T2**: `mean_diff_hac_statsmodels` 增加成对联合 `isfinite` 掩码,
  有效配对 `<3` 返回 `(0.0, 1.0)`, `maxlags` 基于清洗后样本 —
  与 v3.4.10 主检验同口径 (该函数仅测试引用)
- **T3**: MAD / 自适应类去极值参数化 —
  `PipelineV2Config` 新增 `static_outlier_adaptive_threshold=True` /
  `static_outlier_max_outlier_frac=0.05`, 经 `StaticFactorPipeline` 透传到
  `ProcessingAdapter`; 默认值与 `SmartOutlierDetector` 默认逐值一致 → 零行为变更;
  `adaptive_threshold=False` 即固定 3×MAD
- **T4 (不实施)**: 非生产路径解耦器数值修复 — 相关类已由 ADR-043 弃用,
  零生产调用、零测试覆盖, 修复与弃用决策冲突
- 项目版本 **3.4.11** (6 处锚点); 缓存代际不变 **`v2.3.0-cache`**

### 变更文件

| 文件 | 变更 |
|------|------|
| `backtest/ablation_runner.py` | T1 移除 `alpha`; T2 `mean_diff_hac_statsmodels` 成对过滤 |
| `pipelines_v2.py` | T3 新增 2 个 config 字段 + `StaticFactorPipeline` 2 个参数 + `_create_pipeline` 转发 |
| `tests/test_backtest/test_ablation_runner.py` | 新增 `TestMeanDiffHACMissing` (E1-E2) |
| `tests/test_backtest/test_ablation_knob_wiring.py` | 新增 3 例 (E3-E5) |
| 6 处版本锚点 | `__init__.py` / `pyproject.toml` / `config_v2.py` / `reporting.py` / `test_fix3_version_unification.py` / `verify_fix3_manual.py` |
| `docs/` | EXECUTION / CHECKLIST / CONSISTENCY_REVIEW / audit / PROJECT_STATUS / DEV_PROGRESS |
| `CODE_WIKI.md` | 头部版本 + 版本历史 + 配置字段 |
| `docs/analysis/MAD_WINSORIZE_O1_EXPERIMENT.md` | §6 O2 标注已参数化 |

### 实测矩阵

| 层级 | 对象 | 结果 |
|------|------|------|
| unit | E1-E5 (mean_diff 缺失 / detector 参数透传) | 新增 **5 passed** (Red: 5 failed / 3 passed → Green: **8 passed**, 含既有 3 例) |
| 定向回归 | `test_ablation_runner.py` + `test_ablation_knob_wiring.py` | **123 passed** |
| 定向回归 | `test_pipelines_v2.py` + `test_adapters` + `test_ablation_decoupler_arm.py` | **46 passed** |
| 定向回归 | `tests/test_backtest` | **599 passed / 8 skipped** (573.34s; 基线 594 → +5) |
| 全量回归 | `tests/` | **1746 passed / 15 skipped / 0 failed** (1176.01s; 基线 1741 → +5) |
| 版本统一 | `test_fix3_version_unification.py` + 手工校验 | **7 passed** + 手工 **6/6** |

### 兼容性

- `ledoit_wolf_hac_test` 移除未使用参数 (仓内唯一调用点已同步);
- `mean_diff_hac_statsmodels` 仅测试路径, 无生产影响;
- T3 为纯新增可选字段, 默认值 = detector 默认 → 生产输出逐位不变;
- 缓存不失效。

## v3.4.10 — HAC 检验 NaN 过滤 (已实施, 2026-11-16)

### 概览

MAD 缩尾实验 ([§6 O1](docs/analysis/MAD_WINSORIZE_O1_EXPERIMENT.md)) 发现:
`ledoit_wolf_hac_test` 入口不做缺失处理, LS/IC 序列各含 1 个 NaN 时
`np.mean` / `np.std` / 矩条件被污染, `compare` 的 `p_value_hac` 静默返回 NaN,
HAC 判定整体失效 (当次实验只能改用 NW 截距 t 补算)。

### 核心产出

- `ledoit_wolf_hac_test` 入口新增**成对联合** `isfinite` 掩码 (complete-case),
  同时过滤 NaN 与 ±Inf; 不能逐序列独立删除 (交叉矩条件要求同一时刻配对)
- 清洗后样本量 `n` 作为 Newey-West 带宽 `q` 与全部 `/T` 归一化的基数
- 有效配对 `n < 3` 返回 `(0.0, 1.0)` = 无证据, 不再返回 NaN
- 丢弃非有限配对时输出 1 条 `logger.debug` (原始 T / 有效 n / 丢弃数)
- docstring 声明 Equal Spacing 口径 (Datta & Du 2012) 与「压缩时间轴」局限
- `compare` / `compare_all` / `circular_block_bootstrap` /
  `mean_diff_hac_statsmodels` **零改动**; P0-1 NaN 兜底保留为防御
- 项目版本 **3.4.10** (6 处锚点); 缓存代际不变 **`v2.3.0-cache`**

### 口径变化

| 场景 | v3.4.9 | v3.4.10 |
|------|--------|---------|
| `ls_return_series` 含 NaN | 返回 `(nan, nan)` → `compare` 的 HAC 静默失效 | 成对剔除后正常估计; 输出有限 t/p |
| 有效配对 < 3 | `(nan, nan)` | `(0.0, 1.0)` (无证据) |
| 无缺失且 `n ≥ 3` | — | 逐位不变 (掩码全 True) |
| 无缺失但 `n < 3` | NaN / 未定义 | `(0.0, 1.0)` (无证据) |

### 变更文件

| 文件 | 变更 |
|------|------|
| `backtest/ablation_runner.py` | `ledoit_wolf_hac_test` 入口掩码 + 带宽基数 + `n<3` 退化 + docstring |
| `tests/test_backtest/test_ablation_runner.py` | 新增 6 例 (E1-E6): 同位置 / 不同位置 / 不足配对 / 全 NaN / Inf / `compare` 集成 |
| 6 处版本锚点 | `__init__.py` / `pyproject.toml` / `config_v2.py` / `reporting.py` / `test_fix3_version_unification.py` / `verify_fix3_manual.py` |
| `docs/` | RESEARCH / DESIGN / EXECUTION / CHECKLIST / CONSISTENCY_REVIEW / audit / PROJECT_STATUS / DEV_PROGRESS |
| `CODE_WIKI.md` | 头部版本 + 4.15 缺失值口径注 |
| `docs/analysis/MAD_WINSORIZE_O1_EXPERIMENT.md` | §6 O1 标注已修复 |

### 实测矩阵

| 层级 | 对象 | 结果 |
|------|------|------|
| unit | E1-E6 (NaN/Inf 成对 / 退化 / 集成) | **6 passed** (Red: 6 failed / 5 passed → Green: 11 passed) |
| 定向回归 | `tests/test_backtest/test_ablation_runner.py` | **89 passed** |
| 定向回归 | `tests/test_backtest` | **594 passed / 8 skipped** (664.96s; 基线 588 → +6) |
| 全量回归 | `tests/` | **1741 passed / 15 skipped / 0 failed** (1437.31s; 基线 1735 → +6) |
| 版本统一 | `test_fix3_version_unification.py` + 手工校验 | **7 passed** + 手工 **6/6** |

### 兼容性

- 公开签名 / 返回类型不变;
- 无缺失输入的数值逐位不变;
- BH-FDR 分母不受影响 (用 bootstrap p);
- 生产管线零改动; 缓存不失效。

### 说明

本修复采用 Datta & Du (2012) 的 Equal Spacing 估计量 (删除缺失后按等间隔套
Newey-West), 其渐近一致性与低偏差优势见
[RESEARCH](docs/research/RESEARCH_HAC_NAN_FILTER.md) §2;
未实现 AM 估计量 (记为观察项 O1)。

## v3.4.9 — L1/L2 消融臂 trivial 判定口径 (已实施, 2026-11-16)

### 概览

v3.4.8 只修了 `run_l4_oat` 的 trivial 口径, 但同族问题在 L1/L2 仍有两处:

- `run_l2` 的 `L2_unified`: B3 (`routing_mode='full'`) 与 `'unified'` 在
  `_run_pipeline` 中**都注入** `pipeline_mode='unified'`, 两臂实跑逐位相同,
  却计入 BH-FDR 分母 (分母 2, 实际只有 `L2_dynamic` 一个真实比较);
- `run_l1` 的 `L1_orthogonalizer_off`: 关闭正交化的前提是
  `base_config.orthogonalization is not None`; 默认构造下为 `None` (无 hook),
  该臂是 B3 的复制, 却计入分母 (分母 5, 实际 4)。

另修复一个归因污染: `run_l1` 的模块臂原以 `{module: False}` **整体替换**
`base_config.module_enabled`, 会把 base 已关闭的其他模块重新打开。

### 核心产出

- 新增 `_base_module_switches` / `_base_ortho_active` (只读 base_config, 无副作用)
- `run_l1`: 模块臂改为 `{**base_modules, module: False}` 合并覆盖;
  `_is_trivial = not base_modules.get(module, True)`
- `run_l1`: `L1_orthogonalizer_off` 的 `_is_trivial = not base_ortho`
- `run_l1`: 退化臂在循环外**一次**告警, 文案含「与 B3 同口径」并点名臂
- `run_l1` / `run_l2`: 外部 `b3_full_result` 传入时追加「口径未校验」提示
- `run_l2`: `L2_unified` 标 `_is_trivial=True`, `L2_dynamic` 为 `False`
- `run_l1_decoupler`: off 臂同步改为合并覆盖 (R-1, 独立复审发现) —
  与参照臂除 decoupler 外口径一致
- 臂数 / 臂名 / `AblationConfig` 字段 / `compare_all` / 生产管线 全部不变
- 项目版本 **3.4.9** (6 处锚点); 缓存代际不变 **`v2.3.0-cache`**
- 测试: 新增 7 例 (E1-E7), 既有测试零修改

### 口径 (trivial) 变化

| 场景 | v3.4.8 | v3.4.9 |
|------|--------|--------|
| `run_l1` 默认 base | 0 trivial + 5 非平凡 | **1 trivial (`orthogonalizer`)** + 4 非平凡 |
| `run_l1` base 启用正交化 | 0 trivial + 5 非平凡 | 不变 (仍 5 非平凡) |
| `run_l2` | 0 trivial + 2 非平凡 | **1 trivial (`unified`)** + 1 非平凡 |

### 变更文件

| 文件 | 变更 |
|------|------|
| `backtest/ablation_runner.py` | L1/L2 实跑口径判定 + 合并覆盖 + 两条告警/提示 |
| `tests/test_backtest/test_ablation_knob_wiring.py` | 新增 `TestL1L2TrivialCaliber` (E1-E7) + `_runner_with` |
| 6 处版本锚点 | `__init__.py` / `pyproject.toml` / `config_v2.py` / `reporting.py` / `test_fix3_version_unification.py` / `verify_fix3_manual.py` |
| `docs/` | RESEARCH / EXECUTION / CHECKLIST / CONSISTENCY_REVIEW / audit / PROJECT_STATUS / DEV_PROGRESS |
| `CODE_WIKI.md` | 头部版本 + `run_l1` / `run_l2` 描述 |

### 实测矩阵

| 层级 | 对象 | 结果 |
|------|------|------|
| unit | E1-E7 (trivial 集合 / 告警 / 合并语义 / 外部提示) | **7 passed** (Red: 6 failed / 1 passed → Green: 7 passed) |
| 定向回归 | 4 个消融测试文件 | **133 passed** (11.57s) |
| 定向回归 | `tests/test_backtest` | **588 passed / 8 skipped** (837.23s) |
| 复审后复跑 | 4 个消融文件 + 版本统一 | **140 passed** (13.47s) |
| 版本统一 | `test_fix3_version_unification.py` + 手工校验 | **7 passed** + 手工 **6/6** |
| 全量回归 | `pytest` | **1735 passed / 15 skipped / 0 failed** (1559.39s) |

### 兼容性

- **默认 `base_config`**: 处理输出逐位不变; 仅 `_is_trivial` 标记与 BH 分母变化
  (L1 5→4, L2 2→1) — 属口径修正, 非回归;
- **非默认 `module_enabled`**: 臂开关由「整体替换」改为「合并覆盖」(`run_l1` 模块臂
  与 `run_l1_decoupler` off 臂), 输出可能变化 — 归因修正 (不再把 base 已关闭的模块
  重新打开), 已在 docstring 注明;
- 公共接口、臂名、`AblationConfig` 字段、报告列均不变。

### 说明

- `run_l1_decoupler` 不改: 其参照是 `L1_dynamic_ref` (dynamic 口径) 而非 B3,
  不属本问题族;
- 外部 `b3_full_result` 的开关 / `pipeline_mode` 仍由调用方负责 (v3.4.6 O3),
  runner 只提示不校验 — 与 v3.4.8 T4 同一责任划分。

---

## v3.4.8 — 消融臂 trivial 判定按实跑口径 (已实施, 2026-11-15)

### 概览

v3.4.7 审计遗留的 P2-1: `run_l4_oat` 在未传 `market_cap_data` 时,
`L4_neutralization_industry+mktcap` 臂不注入市值 → 管线回落至仅行业中性化
(`pipelines_v2.py` `_build_neutralizer_params`), **实跑口径与 B3 完全相同**,
但 trivial 判定只比较选项名, 该臂被当作非平凡计入 BH-FDR 分母。

后果: 无市值场景 9 个比较中实际只有 5 个非平凡, 分母却按 6 计; 该臂 p 值退化在 1 附近,
单向收紧其余臂的 BH 阈值, 降低检测力, 且与 `_is_trivial`「与 baseline 同口径」的既有语义矛盾。

### 核心产出

- `run_l4_oat`: 引入 `market_cap_available` 单点判据 (与市值注入条件同源)
- trivial 判定改为**实跑口径**: 无市值时 `industry+mktcap` 归一为 `industry` 后比较默认值
- 退化时输出**一次** `logger.warning` (文案含「退化为仅行业」), 避免误读为「该自由度无效应」
- 外部传入 `b3_full_result` 且未传市值时, 追加一条「外部 B3 口径未校验」提示
  (B3 口径由调用方负责, runner 无法反推; 若其按市值口径计算, trivial 判定会漏掉真实差异)
- 臂数与臂名不变 (仍 9 结果 / 8 个 L4 臂); `config.neutralization` 保留原值
- 生产管线 (`pipelines_v2.py`) 零改动; 缓存代际不变 **`v2.3.0-cache`**
- 项目版本 **3.4.8** (6 处锚点)
- 测试: 新增 4 例 (T1 无市值 trivial 集合 / T2 退化告警 / T3 有市值不变 / T4 外部 B3 口径提示), 更新 3 例既有断言

### 测线口径 (trivial) 变化

| 场景 | v3.4.7 | v3.4.8 |
|------|--------|--------|
| 传市值 | 2 trivial (`winsorize_1pct` / `industry+mktcap`) + 6 非平凡 | **不变** |
| 不传市值 | 2 trivial (`winsorize_1pct` / `industry`) + 6 非平凡 | 3 trivial (增 `industry+mktcap`) + **5 非平凡** |

### 变更文件

| 文件 | 变更 |
|------|------|
| `backtest/ablation_runner.py` | `run_l4_oat`: `market_cap_available` / 实跑口径 trivial / 退化告警 + 外部 B3 口径提示 |
| `tests/test_backtest/test_ablation_knob_wiring.py` | 新增 `TestL4TrivialCaliber` (T1-T4); `test_l4_trivial_count` 改 3/5 |
| `tests/test_backtest/test_ablation_runner.py` | `test_l4_oat_marks_trivial_configs` 改 3/5 |
| `tests/test_backtest/test_ablation_mktcap_alignment.py` | 无市值用例更名并断言退化臂 trivial |
| 6 处版本锚点 | `__init__.py` / `pyproject.toml` / `config_v2.py` / `reporting.py` / `test_fix3_version_unification.py` / `verify_fix3_manual.py` |
| `docs/` | RESEARCH / EXECUTION / CHECKLIST / CONSISTENCY_REVIEW / audit / PROJECT_STATUS / DEV_PROGRESS |
| `CODE_WIKI.md` | 头部版本 + `run_l4_oat` 描述 |

### 实测矩阵

| 层级 | 对象 | 结果 |
|------|------|------|
| unit | T1-T4 (trivial 口径 + 退化告警 + 外部 B3 提示) | **4 passed** (Red: 5 failed / 107 passed → Green: 112 passed; T4 于独立复审后追加) |
| 定向回归 | 3 个消融测试文件 (复审后复跑) | **113 passed** (6.05s) |
| 定向回归 | `tests/test_backtest` | **580 passed / 8 skipped** (1338.27s) |
| 版本统一 | `test_fix3_version_unification.py` + 手工校验 | **7 passed** + 手工 **6/6** |
| 全量回归 | `pytest` | **1728 passed / 15 skipped / 0 failed** (2143.86s, T4 追加后复跑) |

### 兼容性

- **有市值**: 行为逐位不变;
- **无市值**: BH-FDR 分母 6→5, 其余臂 q 值可能变小 (更易检出) — 属口径修正, 非回归;
- 公共接口、`AblationConfig` 字段、臂名、报告列均不变。

## v3.4.7 — L3/L4 旋钮接线审计 (已实施, 2026-11-15)

### 概览

对 AblationRunner 的 L3/L4 自由度做接线审计后发现: 43 个非 B3 臂中只有 3 个真正改变
处理结果, 6 个只改诊断输出, 24 个注入的属性 (`_l3_*` / `_l4_*`) 在管线中**完全无消费者**。
报表因此出现大量 Δ≈0 的臂, 无法区分「无效应」与「未接线」。

本版做两件事:
- **最小接线**: 把唯一高价值且默认值可与现状逐位对齐的自由度 —— Static 管道去极值方法 ——
  参数化 (`static_outlier_method` / 分位点), 默认值仍为 `percentile 1/99`, 零行为变更;
- **臂集合重建**: L4 20→9 结果, L3 25→7 结果, 删除项均为「不可接线 / 重复覆盖」,
  并新增 `_wiring_status` (`wired` / `diagnostic`) 标注诊断型空转臂。

### 核心产出

- `PipelineV2Config`: 新增 `static_outlier_method='percentile'`,
  `static_outlier_percentile_lower=1.0`, `static_outlier_percentile_upper=99.0`
- `StaticFactorPipeline`: 新增同名构造参数; 仅 `percentile`/`quantile` 传分位点
- `AblationConfig`: 新增 `_wiring_status`; 无消费者的 L3/L4 字段保留但标注
- `run_l4_oat`: 3 自由度 8 臂 (outlier 4 / missing drop 1 / neutralization 3) + B3 = 9
- `run_l3`: 6 个 CUSUM 诊断臂 + B3 = 7; 全部 `_is_trivial=True` 且 `_wiring_status='diagnostic'`
- `_apply_l4_overrides`: outlier 臂真实映射到 `static_outlier_*`; 未知臂名抛 `ValueError`
- 报告 L1-L4 表新增 `Wiring` 列
- 项目版本 **3.4.7** (6 处锚点); 缓存代际不变 **`v2.3.0-cache`**
- 新增 12 例测试 (E1-E12)

### 测线口径 (trivial)

- L4: `winsorize_1pct` (= 默认 percentile 1/99) 与中性化默认臂 (传市值时
  `industry+mktcap`, 否则 `industry`) 为 trivial → 2 trivial + 6 非平凡;
- L3: CUSUM 只写 `cusum_monitors` / `drift_alerts`, 不侵入 fit/transform, ΔIC/ΔSharpe
  恒为 0 → 6 臂全部 trivial, 不进入 BH-FDR 分母。

### 变更文件

| 文件 | 变更 |
|------|------|
| `pipelines_v2.py` | `PipelineV2Config` +3 字段; `StaticFactorPipeline` +3 参数; `_create_pipeline('static')` 注入 |
| `backtest/ablation_runner.py` | `_wiring_status` / `L4_OUTLIER_MAP` / 注入重写 / 臂集合重建 / 报告 Wiring 列 |
| `tests/test_backtest/test_ablation_knob_wiring.py` | **新增** E1-E12 |
| `tests/test_backtest/test_ablation_runner.py` | L3/L4 臂数、trivial、注入断言更新 |
| `tests/test_backtest/test_ablation_mktcap_alignment.py` | 臂数 25→7 / 20→9 |
| `docs/research/RESEARCH_ABLATION_KNOB_WIRING.md` | 调研 (F1-F20 / O1-O5) |
| `docs/EXECUTION_V3.4.7_ABLATION_KNOB_WIRING.md` | 实施文档 |
| `docs/audit/2026-11-15-ablation-knob-wiring-audit.md` | 审计报告 |
| `__init__.py` / `pyproject.toml` / `config_v2.py` / `reporting.py` | 3.4.6 → 3.4.7 |
| `tests/test_fix3_version_unification.py` / `tests/test_backtest/verify_fix3_manual.py` | `EXPECTED_VERSION` → `3.4.7` |

### 兼容性

- **行为**: 默认配置下 Static 管道去极值参数与 v3.4.6 完全一致 (percentile 1/99),
  生产路径零变更;
- **破坏性 (消融 API)**: `run_l3` 返回 25→7, `run_l4_oat` 返回 20→9;
  依赖旧臂名 (`L3_ewma_*` / `L3_threshold_scale_*` / `L3_winsorize_*` /
  `L4_scaler_method_*` / `L4_time_align_*` / `L4_data_window_*`) 的调用方需同步;
- `AblationConfig` 对应字段保留 (可继续构造), 但不再注入管线。

---

## v3.4.6 — `run_l3` / `run_l4_oat` 市值口径对齐 (已实施, 2026-11-13)

### 概览

v3.4.4 / v3.4.5 让 L1 / L2 / Baseline 真正使用市值中性化后, L3 与 L4 成为仅剩的两层
"无市值入口" —— 两者的消融臂全部走"仅行业"口径, 而同一次消融中 B3 参照走
"行业 + 市值", 跨层 ΔIC/ΔSharpe 因此混入了中性化口径差异 (违反消融归因前提:
参照臂与实验臂仅目标组件不同; Meyes et al. 2019, arXiv:1901.08644;
Athey & Imbens 2017, DOI 10.1257/jep.31.2.3)。本版补齐两处入口。

过程中发现两个必须区别对待的事实:
- 管线在 `market_cap_data is not None` 时**自动**把中性化切到
  `industry_marketcap` (`pipelines_v2._build_neutralizer_params`, 硬编码无开关),
  因此 L3 可以统一注入, 而 L4 的 `neutralization='industry'` 臂**必须不传市值**,
  否则该自由度失效、与 `industry+mktcap` 臂恒等;
- 传市值后 B3 参照口径变为 `industry+mktcap`, 故 L4 的默认 (trivial) 选项必须
  随数据可用性切换, 否则平凡比较不成立。

**核心产出**:
- `run_l3`: 新增 `market_cap_data`, B3 + 24 臂统一注入 (仅非 None)
- `run_l4_oat`: 新增 `market_cap_data`, B3 + 18 臂注入 (`industry` 臂跳过);
  `defaults['neutralization']` 随数据可用性在 `industry` / `industry+mktcap` 间切换
- 项目版本 **3.4.6** (6 处锚点); 缓存代际不变 **`v2.3.0-cache`**
- 新增 8 例测试 (E1-E7, 其中 E7 拆为 E7a/E7b)

### 变更文件

| 文件 | 变更 |
|------|------|
| `backtest/ablation_runner.py` | `run_l3` / `run_l4_oat` 新增 `market_cap_data` + 注入规则 + 默认口径切换 |
| `tests/test_backtest/test_ablation_mktcap_alignment.py` | **新增** E1-E7 (8 例) |
| `docs/research/RESEARCH_ABLATION_MKTCAP_ALIGNMENT.md` | 调研 (F1-F12 / Q1-Q5 / O1-O3) |
| `docs/EXECUTION_V3.4.6_ABLATION_MKTCAP_ALIGNMENT.md` | 实施文档 |
| `docs/audit/2026-11-13-ablation-mktcap-alignment-audit.md` | 审计报告 (92 分 A) |
| `tests/test_fix3_version_unification.py` / `tests/test_backtest/verify_fix3_manual.py` | `EXPECTED_VERSION` → `3.4.6` |
| `__init__.py` / `pyproject.toml` / `config_v2.py` / `reporting.py` | 3.4.5 → 3.4.6 |

### 兼容性

- **兼容**: 臂集合 / 返回数量不变 (L3 = 25, L4 = 20); 未传市值时不注入该关键字,
  既有 monkeypatch 测试签名不受影响; 未传市值路径与 v3.4.5 逐位一致
  (L4 默认仍为 `industry`, 既有 trivial 断言不破坏);
- **行为变化 (修复)**: 显式传入 `market_cap_data` 时 L3/L4 真正使用市值中性化,
  相关臂与 B3 参照数值会变化;
- **数值 / 缓存**: 默认路径零变化, 仍为 `v2.3.0-cache`; 未新增依赖。

### 实测矩阵

| 层级 | 对象 | 结果 |
|------|------|------|
| unit | E1-E7 (L3/L4 市值口径) | **8 passed** (Red: 6 failed / 2 passed) |
| 定向回归 | ablation_runner + decoupler 臂 + 本文件 | **113 passed** (18.14s) |
| 版本统一 | `test_fix3_version_unification.py` + 手工校验 | **7 passed** + 手工 **5/5** |
| 全量回归 | `pytest tests` | **1715 passed / 15 skipped / 0 failed** (2525.38s) |

> 全量基线 1707 → 1715 (仅新增 8 例, 无既有用例改动)。

### 已知遗留 (不在本版范围)

- **O1**: L3/L4 多数自由度开关 (`_l3_ewma_*` / `_l3_threshold_scale` /
  `_l3_winsorize_ratio` / `_l3_correction_method` / `_l4_outlier_method` /
  `_l4_scaler_method` / `_l4_imputer_strategy` / `_l4_time_align` / `_l4_data_window`)
  在全仓**无消费者**,
  对应消融臂与基线数值完全相同 —— 报表中这些臂的 Δ≈0 是"空转"而非"无效应"。
  真正生效的只有 `cusum_k/h`、`missing_method='drop'`、`neutralization='none'`。
  需逐旋钮映射到真实管线配置, 单独立项。
- **O3**: 调用方若传入 `b3_full_result`, 其口径由调用方负责 (runner 不校验)。

---

## v3.4.5 — 修复 `run_l2` / `run_baselines` 市值转发断链 (已实施, 2026-11-13)

### 概览

v3.4.4 修复了 `run_l1` 与 `run_single` 两处 `market_cap_data` 断链, 但
`run_l2` 与 `run_baselines` 的同名参数仍被静默丢弃。前者使 L2 两臂的中性化
只用行业; 后者更严重 — `run_baselines` 产出的 B3 是 L1/L2 的参照臂,
参照与实验臂中性化口径不一致会直接污染消融归因 (Meyes et al. 2019;
Athey & Imbens 2017)。本版补齐这两处转发。

**核心产出**:
- `run_l2`: 两臂转发 `market_cap_data` (仅非 None 时注入)
- `run_baselines`: B0-B3 阶梯转发 `market_cap_data` (仅非 None 时注入)
- 项目版本 **3.4.5** (6 处锚点); 缓存代际不变 **`v2.3.0-cache`**
- 新增 2 例测试 (D12 / D13)

### 变更文件

| 文件 | 变更 |
|------|------|
| `backtest/ablation_runner.py` | `run_l2` / `run_baselines` 市值转发 |
| `tests/test_backtest/test_ablation_decoupler_arm.py` | **新增** D12 / D13 (2 例) |
| `tests/test_fix3_version_unification.py` / `tests/test_backtest/verify_fix3_manual.py` | `EXPECTED_VERSION` → `3.4.5` |
| `__init__.py` / `pyproject.toml` / `config_v2.py` / `reporting.py` | 3.4.4 → 3.4.5 |

### 兼容性

- **兼容**: 臂集合 / 返回数量不变; 未传市值的调用完全不注入该关键字,
  既有 monkeypatch 测试签名不受影响;
- **行为变化 (修复)**: 显式传入 `market_cap_data` 的 `run_l2` /
  `run_baselines` 调用 (`scripts/run_ablation_real.py`) 现在真正使用市值
  中性化, 相关臂与 B3 参照数值会变化 (此前参数被静默丢弃);
- **数值 / 缓存**: 默认路径 (`market_cap_data=None`) 零变化, 仍为
  `v2.3.0-cache`; 未新增依赖、未改配置契约。

### 实测矩阵

| 层级 | 对象 | 结果 |
|------|------|------|
| unit | D12 / D13 (市值转发) | **2 passed** |
| 定向回归 | decoupler 臂 + ablation_runner + L2 路由 + 版本统一 | **115 passed** (29.25s) |
| 版本统一 | `test_fix3_version_unification.py` + 手工校验 | **7 passed** + 手工 **5/5** |
| 全量回归 | `pytest tests` | **1707 passed / 15 skipped / 0 failed** (2220.72s) |

> 全量基线 1705 → 1707 (仅新增 D12/D13, 无既有用例改动)。

---

## v3.4.4 — AblationRunner `decoupler` 消融臂 (已实施, 2026-11-13)

### 概览

v3.4.3 使 `module_enabled['decoupler']` 可独立关闭 AR 解耦, 但
`decoupler` 仅在 `pipeline_mode='dynamic_ab'` 的 `DynamicFactorPipeline`
中存在; `run_l1` 的全部臂经 `routing_mode='full'` → unified Static 管道
(调研代码事实 A1–A4), 该键不生效。结果是 AR 解耦贡献仍无法在 L1 消融中
单独度量。本版新增 **within-mode** 消融入口, 使参照臂与实验臂仅
`enable_ar` 不同。

**核心产出**:
- 新增 `AblationRunner.run_l1_decoupler()`: `L1_dynamic_ref` (中性化 + AR 全开)
  vs `L1_decoupler_off` (`module_enabled={'decoupler': False}`), 两臂
  `routing_mode='dynamic'`, 支持 `dynamic_ref_result` 按 identity 复用
- `_collect_rho_steps` 在检测到 Dynamic 中间数据 `decoupling` 时追加
  `decoupler` 步骤 (`imputation → decoupling`); unified/B0 仍为 5 键
- `generate_report` 的 ρ_step 表按需追加 `decoupler` 列
- 修复 `run_l1` 与 `run_single` 两处 `market_cap_data` 断链 (仅非 None 时注入)
- 项目版本 **3.4.4** (6 处锚点); 缓存代际不变 **`v2.3.0-cache`**
- 新增 1 个测试文件共 **11 例**

### 变更文件

| 文件 | 变更 |
|------|------|
| `backtest/ablation_runner.py` | `DYNAMIC_L1_MODULES` + `run_l1_decoupler` + ρ_step 条件采集 + 报告条件列 + 两处市值转发 |
| `tests/test_backtest/test_ablation_decoupler_arm.py` | **新增** D1-D11 (11 例) |
| `tests/test_fix3_version_unification.py` / `tests/test_backtest/verify_fix3_manual.py` | `EXPECTED_VERSION` → `3.4.4` |
| `__init__.py` / `pyproject.toml` / `config_v2.py` / `reporting.py` | 3.4.3 → 3.4.4 |
| `DECISIONS.md` / `docs/research/RESEARCH_ABLATION_DECOUPLER_ARM.md` / `docs/private/DESIGN_ABLATION_DECOUPLER_ARM.md` / `docs/EXECUTION_V3.4.4_ABLATION_DECOUPLER_ARM.md` / `docs/audit/2026-11-13-ablation-decoupler-arm-audit.md` | ADR-045 实现补充 + 调研/设计/实施/审计 |

### 兼容性

- **兼容**: `run_l1` 仍返回 6 臂; unified/B0 的 ρ_step 仍 5 键; 报告在无
  `decoupler` 数据时仍 5 列; 默认 `PipelineV2Config` 输出不变;
- **行为变化 (修复)**: 显式传入 `market_cap_data` 的 `run_l1` 调用
  (`scripts/run_ablation_real.py`) 现在真正使用市值中性化, 相关臂数值会变化
  (此前参数被静默丢弃);
- **未修 (v3.4.5 已补)**: `run_l2` 入口的同类市值断链保留为观察项, 于 v3.4.5 修复;
- **数值 / 缓存**: 默认路径零变化, 仍为 `v2.3.0-cache`。

### 实测矩阵

| 层级 | 对象 | 实施前 (Red) | 实施后 (Green) |
|------|------|-------------|---------------|
| unit | decoupler 臂 D1-D11 | 10 failed / 1 passed | **11 passed** |
| regression | ablation_runner + decoupler 臂 + O2 组件开关 + 版本统一 | — | **121 passed** (18.36s) |
| version | 版本统一 + 手工校验 | — | **7 passed / 5/5** |
| full | 全仓 pytest | 1682 passed / 15 skipped (v3.4.3 记录值; 另有 12 例 R-2 补测未重跑全量) | **1705 passed / 15 skipped / 0 failed** (1063.50s) |

## v3.4.3 — Dynamic 组件可分离性 (O2) (已实施, 2026-11-12)

### 概览

修复 v3.4.0 遗留 O2: `DynamicFactorPipeline` 的
`module_enabled={'neutralizer': False}` 会**同时关闭 AR 解耦** ——
`CompositeDecoupler` 的创建被包在 `if self._neutralizer_enabled:` 分支内。
中性化 (截面回归) 与 AR 解耦 (时序新息) 是统计上正交的两个操作, 绑定导致
L1 消融无法单独度量中性化贡献, Dynamic 退化为 `imputer + z-score`
(调研代码事实 A8)。按 **ADR-045** 将两组件拆为独立开关。

**核心产出**:
- `CompositeDecoupler` 新增 `enable_neutralization` / `enable_ar`
  (默认 `True`, 追加在签名尾部); `enable_ar=False` 时不构建 `ARDecoupler`
- `DynamicFactorPipeline` 新增 `module_enabled['decoupler']` (默认 `True`),
  与 `neutralizer` 分别映射到两个开关; 两者全关时 `_decoupler=None`
- 语义修正: `{'neutralizer': False}` 现在仅关闭中性化、保留 AR;
  旧语义需显式 `{'neutralizer': False, 'decoupler': False}`
- 默认路径调用序列不变, 输出逐位一致; 缓存代际不变 **`v2.3.0-cache`**
- 项目版本 **3.4.3** (6 处锚点)
- 新增 2 个测试文件共 **15 例**

### 变更文件

| 文件 | 变更 |
|------|------|
| `modules/factor_decoupler/core/dual_neutralizer.py` | `CompositeDecoupler` 两开关 + Stage 1/2/3 条件化 (+51/−26, 含 docstring) |
| `pipelines_v2.py` | `_decoupler_enabled` 映射 + 解耦器创建条件化 + 配置注释 |
| `tests/test_dynamic_component_separability.py` | **新增** T1-T5/T10/T12/T13 (11 例) |
| `tests/test_factor_decoupler/test_composite_component_flags.py` | **新增** T6-T9 (4 例) |
| `tests/test_adapters/test_module_enabled.py` | `all_false` 显式加入 `decoupler` |
| `__init__.py` / `pyproject.toml` / `config_v2.py` / `reporting.py` | 3.4.2 → 3.4.3 |
| `tests/test_fix3_version_unification.py` / `tests/test_backtest/verify_fix3_manual.py` | 期望版本 3.4.3 |
| `DECISIONS.md` / `docs/private/DESIGN_DYNAMIC_COMPONENT_SEPARABILITY.md` / `docs/research/RESEARCH_DYNAMIC_COMPONENT_SEPARABILITY.md` / `docs/EXECUTION_V3.4.3_DYNAMIC_SEPARABILITY.md` | ADR-045 + 调研/设计/实施文档 |

### 兼容性

- **兼容**: 默认配置 (`module_enabled=None`) 输出逐位不变; 既有
  `CompositeDecoupler(...)` 位置参数调用不变;
- **语义变更**: `{'neutralizer': False}` 不再关闭 AR (修复目的); 消融报告
  `L1_neutralizer_off` 的 Dynamic 数值将变化;
- **新增**: `{'decoupler': False}` 可单独关闭 AR (仅 Dynamic 管道生效);
- **数值 / 缓存**: 默认路径零变化, 仍为 `v2.3.0-cache`。

### 实测矩阵

| 层级 | 对象 | 实施前 (Red) | 实施后 (Green) |
|------|------|-------------|---------------|
| unit | 管线组件开关 T1-T5/T10/T12/T13 | 10 failed / 5 passed | **11 passed** |
| unit | `CompositeDecoupler` 开关 T6-T9 | 4 × TypeError | **4 passed** |
| regression | 模块开关 + 管线 + 解耦器 + 消融 + 内生性 + 截断不变式 | — | **190 passed** |
| version | 版本统一 + 手工校验 | — | **7 passed / 5/5** |
| full | 全仓 pytest | 1667 passed / 15 skipped (v3.4.2) | **1682 passed / 15 skipped / 0 failed** (166 warnings, 1794.26s) |

## v3.4.2 — 断点监控调度 (O6) (已实施, 2026-11-12)

### 概览

补齐 v3.4.0 遗留 O6: `StructuralBreakMonitor` 此前仅能显式调用, 库内无周期触发路径;
若运行框架不显式调用, `break_alerts` 恒为空。按 **ADR-044** 新增
`BreakMonitorScheduler` (纯增量, 不侵入 `fit`/`transform`, 不改监控统计逻辑)。

**核心产出**:
- `BreakMonitorScheduler`: `daily` / `weekly` / `monthly` 三档节拍,
  周期键 (日 / ISO 周 / 月) 幂等; 首次调用到期, 同周期跳过, 周期键变化再次到期
- `run_if_due(as_of, func, *args, **kwargs)`: 回调成功后才推进状态, 异常不推进、
  同周期可重试; 另有 `due` / `mark_run` / `reset` / `runs` / `last_run_as_of`
- `as_of` 仅接受 naive 时间戳; 数值型 (1970 纳秒陷阱) 与 tz-aware 值显式
  `ValueError`; `cadence` 只读; 单线程串行是显式前提
- 项目版本 **3.4.2**; 缓存代际不变 **`v2.3.0-cache`**
- 新增 `tests/test_break_monitor_scheduler.py` (**22 例**)

### 变更文件

| 文件 | 变更 |
|------|------|
| `backtest/structural_break_monitor.py` | **新增** `BreakMonitorScheduler` (+129/−2, `StructuralBreakMonitor` 类零改动) |
| `tests/test_break_monitor_scheduler.py` | **新增** S1–S21 场景 (22 例) |
| `__init__.py` / `pyproject.toml` / `config_v2.py` / `reporting.py` | 3.4.1 → 3.4.2 |
| `tests/test_fix3_version_unification.py` / `tests/test_backtest/verify_fix3_manual.py` | 期望版本 3.4.2 |
| `DECISIONS.md` / `docs/EXECUTION_V3.4.2_BREAK_SCHEDULER.md` | **ADR-044** + 实施文档 |
| `README.md` / `CHANGELOG.md` / `docs/PROJECT_STATUS.md` / `docs/ARCHITECTURE.md` / `docs/DEV_PROGRESS.md` | 版本与状态同步 |

### 兼容性

- **兼容**: `StructuralBreakMonitor` 类 / `monitor_structural_breaks()` /
  `BreakMonitorConfig` / 管道配置字段全部不变; 既有调用方无需改动。
- **新增**: `BreakMonitorScheduler` 纯增量类, 未使用则零影响; 数值型与
  tz-aware `as_of` 抛 `ValueError` (仅新类)。
- **数值 / 缓存**: 零变化, 仍为 `v2.3.0-cache`。

### 实测矩阵

| 层级 | 对象 | 实施前 (Red) | 实施后 (Green) |
|------|------|-------------|---------------|
| unit | 调度器 S1–S21 | ImportError (收集失败) | **22 passed** (0.40s) |
| regression | 调度器 + 断点监控 + 版本统一 + 统一路由 | — | **57 passed** (22.20s) |
| manual | `verify_fix3_manual.py` | — | **5/5 通过** (6 处版本位置) |
| invariant | `StructuralBreakMonitor` 类统计/自助/配置 | — | 零改动 (仅新增类) |

### 全量回归基线 (2026-11-12)

全仓 `pytest` 建立 v3.4.2 回归基线: **1667 passed / 15 skipped / 0 failed**
(166 warnings, 809.32s, exit 0)。此前无基线记录, 且三类外部数据依赖会污染全量运行:

| 问题 | 处置 |
|------|------|
| `tests/test_integration_real_data.py` 模块级执行 DB 查询 + `sys.exit(1)`, 收集中断 | 重命名为 `tests/verify_integration_real_data.py` (手动运行脚本, 不参与收集) |
| `tests/test_backtest/test_p0_duckdb_pivot.py` 依赖 0 字节外部 DB → `OutOfMemoryException` | 模块级默认跳过; `RUN_DUCKDB_INTEGRATION=1` 且 DB 非空时手动运行 |
| `tests/test_demo_notebook.py::test_cell_3_classification_tree` 断言 v3.4.0 已删除的 `routing_weights` | 改为断言 `routing_weights` **不存在** (仅诊断) |

## v3.4.1 — 非生产路径解耦器弃用 (已实施, 2026-11-11)

### 概览

`OptimizedARDecoupler` / `OptimizedCompositeDecoupler` / `TemporalDecoupler` /
`decouple_ar` / `decouple_composite` 无生产调用、无测试覆盖, 且存在全样本拟合
前视风险 (v3.3.1 已修复生产路径的同类问题)。按 **ADR-043** 采用
「保留导入 + 构造告警」, 不删除公开 API、不修复死代码数值路径。

**核心产出**:
- 三个类 `__init__` 构造即触发 `DeprecationWarning` (`stacklevel=2`);
  docstring 标注 `.. deprecated:: v3.4.1`
- `modules/factor_decoupler/__init__.py` 增加弃用说明块;
  子包版本 `1.2.0` → **1.2.1**
- 项目版本 **3.4.1** (版本链 6 处); 缓存代际不变 **`v2.3.0-cache`**
- 新增 `tests/test_deprecated_nonprod_decouplers.py` (4 例弃用契约, Red→Green)

### 变更文件

| 文件 | 变更 |
|------|------|
| `modules/factor_decoupler/core/optimized.py` | 两类构造告警 + docstring 弃用标注 |
| `modules/factor_decoupler/core/unified_decoupler.py` | `TemporalDecoupler` 构造告警 + docstring |
| `modules/factor_decoupler/__init__.py` | 子包版本 1.2.1 + 弃用说明 |
| `__init__.py` / `pyproject.toml` / `config_v2.py` / `reporting.py` | 3.4.0 → 3.4.1 |
| `tests/test_deprecated_nonprod_decouplers.py` | **新增** 4 例 (4 类入口) |
| `tests/test_fix3_version_unification.py` / `tests/test_backtest/verify_fix3_manual.py` | 期望版本 3.4.1 / 子包 1.2.1 |
| `DECISIONS.md` / `docs/ARCHITECTURE.md` / `docs/DEV_PROGRESS.md` | ADR-043 + 模块符号表 + 影响行 |

### 兼容性

- **兼容**: 公共导入路径不变; 生产路径 (`ARDecoupler` / `AROrderSelector` /
  `CompositeDecoupler`) 不受影响; 计算逻辑零改动。
- **行为变化**: 构造 `Optimized*` / `TemporalDecoupler` 时发出
  `DeprecationWarning`; `decouple_ar` / `decouple_composite` 经内部构造同样触发。
- **迁移**: 生产代码无需改动 (本无调用); 外部调用方应迁移到
  `ARDecoupler` / `CompositeDecoupler`。

### 实测矩阵

| 层级 | 对象 | 实施前 (Red) | 实施后 (Green) |
|------|------|-------------|---------------|
| unit | 弃用契约 (4 类入口) | 4 failed (`DeprecationWarning` 未触发) | **4 passed** |
| unit | 版本统一 + AR 因果性 | — | **27 passed** (1.76s) |
| regression | `test_factor_decoupler` + `test_ar_order_holdback` | — | **51 passed** |
| manual | `verify_fix3_manual.py` | — | **5/5 通过** (6 处版本位置) |
| grep | 全仓 `3.4.0` 残留 | — | 仅历史性引用 (无赋值/比较) |

## v3.4.0 — 因子路由统一化治理 (已实施, 2026-11-10)

### 概览

统一横截面秩管道替代三路指纹路由 (**ADR-042**): 默认 `pipeline_mode='unified'`,
所有因子走同一条管道 (ffill → 1%/99% 缩尾 → 中性化 → rank→normal → z-score),
不再按 VR/DF 分类逐因子选管道; 指纹降级为只读诊断;
`DynamicFactorPipeline` 仅经 `pipeline_mode='dynamic_ab'` 整臂保留。

**核心产出**:
- 删除 3 个路由函数: `_get_pipeline_weights` / `_get_multi_dim_pipeline_weights` /
  `_apply_weighted_transform`
- 配置面: dataclass 删 5 字段 (`hard_routing_prob` / `merge_alpha` / `ks_alpha` /
  `mixed_winsor_sigma` / `enable_multi_dim_routing`), Pydantic 删 5 字段
  (上述 4 共享字段 + `transform_aggressiveness`); 新增 8 字段
  (`pipeline_mode` / `enable_fingerprint_diagnostics` / `ab_experiment_id` /
  `enable_break_monitor` / `break_monitor_window` / `break_monitor_stride` /
  `break_monitor_alpha` / `break_monitor_n_bootstrap`)
- 优化器 (ADR-042 联动): `DEFAULT_SEARCH_SPACE` 清空 — 默认实例化发
  `DeprecationWarning`, `optimize` 空空间抛 `ValueError`; `_params_to_config`/
  `_config_to_params` 收敛为 3 参数契约
- 消融适配: `AblationConfig.routing_mode` 收缩为 'full'/'unified'/'dynamic';
  `run_l2` 5 配置 → 2 臂 + 可选参照; 删 `_override_routing`
- Mixed 管道不再自动创建; `mixed_winsor_sigma` 改由 `MixedFactorPipeline`
  默认值 3.0 承担; D9: Mixed/Dynamic 类保留 (仅供显式 A/B 与直调)
- 新增 `get_routing_summary()` / `monitor_structural_breaks()` 管道方法;
  管道选择与采样频率写入 `SpecificationLogger` (opt-in)
- 项目版本 **3.4.0**; 缓存 `CODE_VERSION` **v2.3.0-cache**

### 变更文件

| 文件 | 变更 |
|------|------|
| `pipelines_v2.py` | 配置 8 加 5 删; `fit`/`transform` 统一路由; 删 3 个路由函数; 新增 `FactorRoutingRecord`/`FingerprintMeta` |
| `config_v2.py` | Pydantic 5 删 8 加; 桥接映射; 版本 |
| `optimizer.py` | 搜索空间清空 + 弃用警告 + `optimize` 守卫 |
| `backtest/ablation_runner.py` | `routing_mode` 收缩 3 值; `run_l2` 2 臂; 删 `_override_routing` |
| `backtest/structural_break_monitor.py` | **新增** sup-F / CUSUM 断点监控 (自助 p 值, 只告警) |
| `modules/factor_fingerprint/` | `infer_sampling_frequency` / `compute_ar1_path` |
| `backtest/cache_manager.py` | `v2.3.0-cache` |
| 版本链 6 处 / 文档 6 份 | 3.4.0 / ADR-042 |

### 兼容性

- **不兼容**: 原 dynamic 因子输出变化 (改走统一管道, 历史基准需重算);
  配置面删字段; 需重建缓存 (`v2.2.5-cache` → `v2.3.0-cache`)。
- **兼容**: 旧配置 JSON 可加载 (`extra='ignore'` 忽略已删字段); 三管道类保留;
  公共 `fit`/`transform` 签名不变。
- **迁移**: 依赖 `hard_routing_prob` 等已删字段的代码需删除;
  依赖路由阈值的优化器调用改 `search_orth=True` 或迁移到统一管道语义。

### 已知遗留

- 断点监控为 opt-in 只告警, 未接入调度 (O6);
- MAD 缩尾 / Dynamic 组件解耦 / DuckDB schema 迁移延后 (O1/O2/O5);
- 真实数据 A/B 仅覆盖 2 因子 / 2023 单年 (秩等价、ΔIC 不显著), 多年多因子扩样本见 [实证报告](docs/analysis/V3.4.0_UNIFIED_ROUTING_EMPIRICAL_AB.md)。

### 实测矩阵 (步骤 9 TDD 正式落库)

| 层级 | 对象 | 实施前 (Red) | 实施后 (Green) |
|------|------|-------------|---------------|
| unit | 统一路由 T1–T14 | 14 failed / 2 passed | **22 passed** (含 T13 两方法) |
| unit | 断点监控 B1–B6 | 模块不存在 (收集错误) | **6 passed** (B1 sup-F 检出 p≈0.0025) |
| unit | E7 动态 (ablation + task1) | 104 passed (基线) | **95 passed** (2 臂口径; 删 10 增 1) |
| regression | 靶向 16 文件 | 基线 279 例全绿 | **273 passed / 1 语义 skip / 0 failed** |
| regression | 版本统一 | 7 passed | **7 passed** (6 处 3.4.0 + v2.3.0-cache) |
| perf | fit+transform 12 因子×750 行 | T0 = 12.246s (0ff2420, min-of-5) | **12.359s → ratio 1.0092 ≤ 1.05** |
| invariant | 统一逐位等价 (T2) / dynamic_ab 等价 (T3) | — | `check_exact=True` 全等 |
| grep | 5 已删字段 / 3 已删函数 | — | pytest 收集文件与生产代码 **0 残留** |
| audit | 步骤 10 审计靶向回归 (15 文件) | 1 failed (R-01 既有用例回归) | **250 passed / 1 skipped / 0 failed** (430.8s) |
| empirical | 真实数据 A/B (2 因子, A股 2023) | 基线标签-执行错位 2/2 | **秩相关 ρ≥0.999999; ΔIC NW t=0.54 / 0.18 (不显著); 统一管道 1.8× 加速** |

**回归**: 靶向批 1 (11 文件) 115 passed / 1 skipped (78.75s) + 批 2 (5 文件) 158 passed (595.69s); duckdb 2.0.0 / optuna 5.0.0 已装, 历史环境例外全部消除。

## v3.3.7 — PL-08 AR 阶数选择 hold_back 可比性修复 (已实施, 2026-11-04)

### 概览

修复 DEFECT-PL-08: `AROrderSelector._fit_ar` 对每个阶数使用 `y[order:]`，
使 AIC/BIC/HQIC 的似然项建立在不同样本上，阶数被系统性推向 `max_order`。

**核心产出**:
- `_fit_ar` 统一 `hold_back = max_order`，所有阶数使用同一估计样本
- 增加有效样本守卫 `n_obs <= order+5 → ValueError`，消除 warm-up `σ²=0`
- `residuals` / `fitted_values` 索引统一为 `series.index[H:]`
- 新增 10 个单测函数 / 22 个 pytest 用例
- 新增 **ADR-041**；项目版本 **3.3.7**；缓存 `CODE_VERSION` **v2.2.5-cache**

### 缺陷根因

| # | 根因 | 证据 |
|---|------|------|
| 1 | `y_trimmed = y[order:]` | 各阶 `n_obs = n-order` 不同 |
| 2 | 似然项随 `n_obs` 缩短 | 每阶样本因子约降 2.84 > AIC 罚 2 |
| 3 | 无有效样本守卫 | warm-up `t=7` 仅 2 个观测，`σ²=0` / `ln(0)` |

### 实测矩阵 (步骤 9 正式落库复测)

| 层级 | 对象 | 修复前 | 修复后 |
|------|------|--------|--------|
| unit | `n_obs` (AR(1..5), n=100) | 99/98/97/96/95 | **95×5** |
| unit | AR(1) 选阶均值 (T=100) | 4.800 | **1.233** (BIC/HQIC 1.000) |
| unit | AR(2) 选阶均值 (T=120) | 4.87 | **2.533** |
| unit | AR(3) 选阶均值 (T=120) | 4.97 | **3.233** |
| unit | 新契约测试 | 13 failed / 9 passed (Red) | **22 passed** (10 函数) |
| output | T=100/N=30 | — | **2790/3000 (93.0%)**, `max_abs=6.9968` |
| output | T=500/N=30 | — | **14410/15000 (96.1%)**, `max_abs=4.6718` |
| quality | 尾部一步 MSE | 1.067782 | **1.048759** |
| invariant | 截断不变式 (11 点) | 0/0 | **0/0** |
| perf | AR 2500×300 | 2.76s | **2.64s** |

**回归**: 靶向 4 文件 72 passed / 1 env-fail (`duckdb`, 与基线相同); `tests/test_fix3_version_unification.py` 隔离运行 6 passed / 1 env-fail (duckdb 阻断 `backtest` 包导入), 合并靶向运行 **7 passed** (次生导入序依赖, 见审计 F-B1)。

### 变更文件

| 文件 | 变更 |
|------|------|
| `modules/factor_decoupler/core/ar_model.py` | `_fit_ar` hold_back + 守卫 + 索引 + docstring |
| `tests/unit/test_ar_order_holdback.py` | **新增** 10 函数 / 22 用例 |
| `pyproject.toml` / `__init__.py` / `config_v2.py` / `reporting.py` | 3.3.7 |
| `backtest/cache_manager.py` | `v2.2.5-cache` |
| `tests/test_fix3_version_unification.py` / `tests/test_backtest/verify_fix3_manual.py` | 版本/缓存字面量 |
| `DECISIONS.md` / `CHANGELOG.md` / `README.md` / `docs/PROJECT_STATUS.md` / `docs/DEV_PROGRESS.md` / `docs/ARCHITECTURE.md` | ADR-041 / v3.3.7 |

### 兼容性

- **不兼容**: AR/Dynamic 输出 93%–96% 格子变化；需重建缓存。
- **兼容**: 公共 API / 签名 / 配置字段 / `ARModelResult` 字段不变。
- **固定阶数**: `fit` 冻结模型逐值相同；`transform` warm-up 段变化（99/96/93 格），冻结段相同。

### 已知遗留

- `OptimizedARDecoupler` / `TemporalDecoupler` 同类缺陷未修（非生产路径）。
- AIC 不一致性未修（方法学性质；本版本只修可比性）。
- 常数序列 `σ²=0` 既有边界未修。

---

## v3.3.6 — PL-05 Dynamic AR 因果性修复: 三段式一步预测 (已实施, 2026-11-04)

### 概览

修复 DEFECT-PL-05: `ARDecoupler.fit` 用全样本 AIC 选阶 + 全样本 OLS，`transform` 用 `fitted_values.reindex().ffill()` 充当一步预测——阶数、系数、预测值三层均依赖未来数据。

**核心产出**:
- `fit` 只用前 `warmup_obs=120` 行估计阶数与系数（冻结模型）
- `transform` 三段式因果一步预测: 冷启动 identity → 固定 `min_order` → 全阶 AIC 每 `stride=10` 行重估 → `t >= warmup_obs` 冻结预测
- 移除 `_results` 列门控与 `fitted_values.reindex().ffill()`；NaN 经滞后自然传播
- `AROrderSelector.fit` 拆出无日志 `_fit_best`，供 warm-up 批量复用
- 新增 10 个单测函数（16 个 pytest 用例）；集成套件摘除 PL-05/PL-07 `xfail`，新增 3 组路由因果性测试
- 新增 **ADR-040**；项目版本 **3.3.6**；缓存 `CODE_VERSION` **v2.2.4-cache**

### 缺陷根因

| # | 根因 | 证据 |
|---|------|------|
| 1 | `fit` 全样本 AIC 选阶 | 阶数随 T 变化，前 t 期阶数依赖 t 之后数据 |
| 2 | `_fit_ar` 全样本 OLS 估系数 | 系数随 T 变化 |
| 3 | `transform` 用 `fitted_values.reindex().ffill()` 当一步预测 | 预测值直接来自全样本拟合（样本内） |
| 4 | `transform` 以 `_results` 存在性整列门控 | 前缀有效观测不足时整列退化为 identity，掩盖早期前视 |

**为何长期未被发现**: 旧输出前导 NaN 使截断前后 NaN 模式一致；样本内残差 `mean_ar1 ≈ 0.0029` 看似"去相关更好"，实为过拟合幻觉（因果实现为 0.0302，仍显著优于原始 0.7025）。

### 实测矩阵 (`T=100, N=30, seed=22, kind='ar_low', t=60, atol=1e-12`)

| 层级 | 对象 | 修复前 | 修复后 |
|------|------|--------|--------|
| pipeline | Dynamic 端到端 | 1653/1800 格 + 8 NaN, 8.045e-01 | **0 / 0 / 0** |
| top | FactorProcessingPipelineV2 | 1650 格, 1.8397 | **0 / 0**（路由全程一致） |
| 诊断 | 违反 / 满足 / 合计 | 1 / 8 / 9（仅 Dynamic FAIL） | **0 / 9 / 9** |
| unit | 新契约测试 | 15 failed / 1 passed (Red) | **16 passed**（10 函数） |
| integration | 截断不变式套件 | 10 passed / 2 xfailed | **15 passed / 0 xfailed** |

**输出与 NaN**（`T=100, N=30, seed=7`，新旧实现同进程对比）:

| 面板 | 对象 | 变化格子 | `max_abs` | `mean_abs` | NaN |
|------|------|---------|-----------|------------|-----|
| iid | AR | 2854/3000 | 3.7255 | 0.2626 | 146 → 0 |
| iid | Dynamic | 2855/3000 | 2.1038 | 0.2287 | 145 → 0 |
| ar70 | AR | 2851/3000 | 4.1873 | 0.3486 | 149 → 0 |
| ar70 | Dynamic | 2852/3000 | 2.7665 | 0.2829 | 148 → 0 |

**质量**（AR(1) φ=0.7, `T=500, N=30, seed=42`, 统计起点第 60 行）: `mean_ar1` 原始 0.7025 / 旧 0.0029 / 新 **0.0302**（K=120）。

**性能**（2500×300）: AR 单步 `0.48s → 2.10–5.23s`（6 次复测中位 ≈2.24s；单次负载离群 6.25s）；Dynamic 全管线（含行业）`33.19s → 39.29s`（+18.4%）。

### 变更文件

| 文件 | 变更 |
|------|------|
| [modules/factor_decoupler/core/ar_model.py](modules/factor_decoupler/core/ar_model.py) | `_fit_best` 拆分; `warmup_obs` + 校验; `fit` 前缀窗口; `transform` 三段式 + `_predict_one_step`; `_WARMUP_REFIT_STRIDE`; docstring |
| [tests/unit/test_ar_decoupler_causality.py](tests/unit/test_ar_decoupler_causality.py) | **新增** 10 个函数 / 16 个用例 |
| [tests/integration/test_pipeline_truncation_invariance.py](tests/integration/test_pipeline_truncation_invariance.py) | 摘除 PL-05/PL-07 xfail; 新增 3-seed 路由测试; 更新登记表 |
| [tests/test_factor_decoupler/test_hidden_effect.py](tests/test_factor_decoupler/test_hidden_effect.py) | φ 断言容差 0.05 → 0.15（n=120 覆盖率 50.3% → 94.8%）; 追加区间断言 |
| [tests/test_fix3_version_unification.py](tests/test_fix3_version_unification.py) / [tests/test_backtest/verify_fix3_manual.py](tests/test_backtest/verify_fix3_manual.py) | 版本锚点 → 3.3.6; 缓存字面量 → v2.2.4-cache |
| [pyproject.toml](pyproject.toml) / [__init__.py](__init__.py) / [config_v2.py](config_v2.py) / [reporting.py](reporting.py) | 版本 → 3.3.6 |
| [backtest/cache_manager.py](backtest/cache_manager.py) | `CODE_VERSION` → v2.2.4-cache |
| [DECISIONS.md](DECISIONS.md) | 新增 ADR-040 + 占用登记 |
| [docs/analysis/PL05_DYNAMIC_AR_LOOKAHEAD_RESEARCH.md](docs/analysis/PL05_DYNAMIC_AR_LOOKAHEAD_RESEARCH.md) / [docs/analysis/PL05_DYNAMIC_AR_LOOKAHEAD_DESIGN.md](docs/analysis/PL05_DYNAMIC_AR_LOOKAHEAD_DESIGN.md) / [docs/EXECUTION_V3.3.6_PL05_DYNAMIC_AR_CAUSALITY.md](docs/EXECUTION_V3.3.6_PL05_DYNAMIC_AR_CAUSALITY.md) | 调研/设计/实施文档, 状态更新为已实施 |

### 兼容性与缓存

- **行为变更**: Dynamic 输出约 95% 格子改变；历史 IC/Sharpe 需重算。
- **NaN 语义**: AR 冷启动由 NaN 改为 identity（`t < max(min_order+6, 2)` 不做解耦），输出不再有前导 NaN。
- **参数**: `ARDecoupler` 新增公开参数 `warmup_obs=120`，必须严格大于 `min_obs`；其余参数语义不变。
- **缓存代际**: `v2.2.3-cache` → `v2.2.4-cache`。读取时 `meta.code_version` 不一致即 MISS 并删除旧数据/meta。

### 已知遗留

- `OptimizedARDecoupler` / `TemporalDecoupler` 仍为旧实现（非生产路径，同类缺陷不覆盖）。
- `_fit_ar` 各阶数 `n_obs = n - order` 不同，AIC 跨阶数不可比（statsmodels `hold_back >= maxlag`），登记 `PL-08-candidate`，不纳入本次。
- 指纹路由分类逻辑本身未改；路由因果性仅由 3-seed 测试守卫。
- 冻结模型对非平稳因子的失配风险未做专项回测。

---

## v3.3.5 — PL-06 Mixed 缩尾因果性修复: 逐日截面 3σ (已实施, 2026-11-04)

### 概览

修复 DEFECT-PL-06: `MixedFactorPipeline._compute_winsorize_params` 用 `X.mean(axis=0)` / `X.std(axis=0)` 按股票全历史估计 3σ 边界，`fit` 保存、`transform` 复用——前 t 期边界依赖 t 之后的数据。

**核心产出**:
- 缩尾边界改为**逐日截面 3σ**（`mu = X.mean(axis=1)`, `sd = X.std(axis=1, ddof=1)`, `clip(axis=0)`），`fit()` 无跨期参数
- 删除 `_compute_winsorize_params`；`_winsorize_params` 保留为 `None` 状态标记
- `mixed_winsor_sigma` / `transform_aggressiveness` / optimizer 搜索空间契约不变；无配置迁移
- 新增 11 例单测；重写 `TestMixedWinsorSigma` test_07/08/09；集成套件由 `9 passed / 3 xfailed` 变为 `10 passed / 2 xfailed`
- 新增 **ADR-039**；项目版本 **3.3.5**；缓存 `CODE_VERSION` **v2.2.3-cache**

### 缺陷根因

| # | 根因 | 证据 |
|---|------|------|
| 1 | `_compute_winsorize_params` 按股票（`axis=0`）用全历史 mean/std 估计 3σ | 截断 60/100 期：257/1800 格差异，`max_abs_diff=6.984e-01`，首个发散日 2020-01-31 |
| 2 | `fit` 保存边界、`transform` 复用 | 前 t 期边界依赖未来；`transform` 单独调用同样复用 fit 参数 |
| 3 | 缩尾位于 neutralize / rank 之前 | 通过改变中性化输入间接影响排序；即使后续 rank 也非"无影响" |

**为何长期未被发现**: 截断前后逐日 Spearman 中位 0.999555（最小 0.984872），排序几乎一致；只有值相等的截断不变式能暴露。

### 实测矩阵 (`T=100, N=30, seed=23, kind='skewed', t=60, atol=1e-12`)

| 层级 | 对象 | 修复前 | 修复后 |
|------|------|--------|--------|
| pipeline | Mixed 端到端 | 257/1800 格, 6.984e-01 | **0 / 0** |
| 诊断 | Mixed 行 | FAIL | **PASS** |
| 诊断 | 违反 / 满足 / 合计 | 4 / 5 / 9 | **1 / 8 / 9**（仅 PL-05） |
| pipeline | Dynamic | 1653 格 + 8 NaN, 8.05e-01 | 不变（PL-05） |
| top | FactorProcessingPipelineV2 | 1650 格, 1.84e+00 | 不变（PL-05 + 指纹路由） |

**相对旧实现的全样本输出差异**（同面板，含行业中性化）：561/3000 格，`max_abs=1.0446`，63/100 行；逐日 Spearman 中位 0.999110 / 最小 0.942603。**缩尾触发率**：61/3000（2.03%）→ 77/3000（2.57%）。

**性能**（`T=2500, N=3000`，3 次中位）：`0.281s → 0.184s`（0.175 / 0.184 / 0.193）。

### 变更文件

| 文件 | 变更 |
|------|------|
| [pipelines_v2.py](pipelines_v2.py) | `fit` Step 2 no-op; `_apply_winsorize` 逐日截面; 删除 `_compute_winsorize_params`; 类/方法 docstring |
| [tests/unit/test_mixed_winsorize_cross_sectional.py](tests/unit/test_mixed_winsorize_cross_sectional.py) | **新增** 11 例 |
| [tests/test_p3_phase2_config_migration.py](tests/test_p3_phase2_config_migration.py) | 重写 `TestMixedWinsorSigma.test_07/08/09` |
| [tests/integration/test_pipeline_truncation_invariance.py](tests/integration/test_pipeline_truncation_invariance.py) | 摘除 PL-06 xfail; 更新登记表与 PL-07 reason |
| [tests/test_fix3_version_unification.py](tests/test_fix3_version_unification.py) / [tests/test_backtest/verify_fix3_manual.py](tests/test_backtest/verify_fix3_manual.py) | 版本锚点 → 3.3.5; 缓存字面量 → v2.2.3-cache |
| [pyproject.toml](pyproject.toml) / [__init__.py](__init__.py) / [config_v2.py](config_v2.py) / [reporting.py](reporting.py) | 版本 → 3.3.5 |
| [backtest/cache_manager.py](backtest/cache_manager.py) | `CODE_VERSION` → v2.2.3-cache |
| [DECISIONS.md](DECISIONS.md) | 新增 ADR-039 + 占用登记 |
| [docs/analysis/PL06_MIXED_WINSORIZE_LOOKAHEAD_RESEARCH.md](docs/analysis/PL06_MIXED_WINSORIZE_LOOKAHEAD_RESEARCH.md) / [docs/analysis/PL06_MIXED_WINSORIZE_LOOKAHEAD_DESIGN.md](docs/analysis/PL06_MIXED_WINSORIZE_LOOKAHEAD_DESIGN.md) / [docs/EXECUTION_V3.3.5_PL06_MIXED_WINSORIZE_CAUSALITY.md](docs/EXECUTION_V3.3.5_PL06_MIXED_WINSORIZE_CAUSALITY.md) | 调研/设计/实施文档, 状态更新为已实施 |

### 兼容性与缓存

- **行为变更**: 所有 Mixed 输出数值改变；历史 IC/Sharpe 需重算。
- **配置**: 无迁移；`mixed_winsor_sigma` / `transform_aggressiveness` 语义不变。
- **缓存代际**: `v2.2.2-cache` → `v2.2.3-cache`。读取时 `meta.code_version` 不一致即 MISS 并删除旧数据/meta。
- **小截面**: `N<=10` 时 3σ 永不触发（数学性质）；`N=1` / 全 NaN / 零离散度原样返回。不引入数据触发的 pre-test。

### 已知遗留

- PL-05（Dynamic AR `fitted_values`）与 PL-07（顶层指纹路由）仍登记为 `xfail`。
- B（逐日截面 percentile(1,99)）未实施；Mixed 3σ 与 Static percentile 的方法差异登记为已知遗留。
- optimizer 未在输出变更后重新调参，另行评估。

---

## v3.3.4 — PL-02 变换因果性修复: 逐日截面 rank→正态 (已实施, 2026-10-22)

### 概览

修复 DEFECT-PL-02 / PL-04: `ProcessingAdapter(process_type='transformation')` 的 `fit()` 用 `X.values.flatten()` 在全 panel 上估计 λ / offset / 经验 CDF，`auto_optimize=True` 覆盖显式方法，且 `_select_optimal_transform` 依赖全样本 skew/kurt/Shapiro p 选型——前 t 期输出依赖 t 之后的数据。

**核心产出**:
- 变换改为**逐日截面 rank → 目标分布**（默认 Blom 正态分数），`fit()` 无状态，结构上无参数可泄漏
- `auto` → `rank`，删除 `auto_optimize` 与整条选型/拟合链；`quantile` 作为 `rank` 配置别名
- `log` / `boxcox` / `yeojohnson` / `power` 保留为先验参数模式（`lam` / `power_param` 必填，禁止 fit 估计）
- `TransformationConfig` 接线到 Static/Mixed v2 管线；删除 `mixed_conditional_transform` / `mixed_skew_threshold` / `mixed_kurt_threshold`
- Mixed 顺序切为 neutralize → transform（I-INT）
- 新增 32 例单测；集成套件由 `7 passed / 5 xfailed` 变为 `9 passed / 3 xfailed`
- 新增 **ADR-038**；项目版本 **3.3.4**；缓存 `CODE_VERSION` **v2.2.2-cache**

### 缺陷根因 (四层叠加)

| # | 根因 | 证据 |
|---|------|------|
| 1 | `fit()` 用 `X.values.flatten()` 在全 panel 上估计 λ / offset / 经验 CDF | 截断 60/100 期: 1800 格差异, `max_abs_diff=8.51e-04` |
| 2 | `auto_optimize=True` 覆盖显式方法; 选型依赖全样本 skew/kurt/Shapiro p | 方法选择不可复现; Shapiro 子采样未设种子 |
| 3 | Mixed 用全样本 `skew().median()` / `kurtosis().median()` 做条件变换 | 属于 pre-test 式在线切换, 估计量分布不可一致估计 |
| 4 | `TransformationConfig` 未接线到 v2 管线 | 配置名义存在但实际由三个 `mixed_*` 字段独立控制 |

**为何长期未被发现**: 变换是保序的。前视与截断输出的排序一致，Spearman 类指标无感；只有值相等的截断不变式能暴露。

### 实测矩阵 (`T=100, N=30, t=60, atol=1e-12`)

| 层级 | 对象 | 修复前 | 修复后 |
|------|------|--------|--------|
| step | transform auto | 1800 格, 8.51e-04 | **0 格, 0** |
| pipeline | Static | 1800 格, 4.72e-05 | **0 格, 0** |
| pipeline | Mixed | 1800 格, 2.91e-01 | 257 格, 6.98e-01（剩余仅 PL-06 全样本缩尾） |
| pipeline | Dynamic | 1653 格 + 8 NaN, 8.05e-01 | 不变（PL-05，不含变换步骤） |
| top | FactorProcessingPipelineV2 | 1650 格, 1.84e+00 | 不变（PL-05/06 + 指纹路由） |

诊断报告: 违反 2 项 / 满足 7 项 / 合计 9 项（修复前为违反 4 项 / 满足 5 项）。

**性能** (`T=2500, N=3000, t(3), NaN 5%`): `rankdata` 逐行 1.040s（设计基准 1.071s，−2.9%）；`ProcessingAdapter.transform` 1.075s；`normal` 中位列 std 0.9991712；`uniform` 0.5773502（理论 `1/√3`）；helper 与 adapter 输出 `max |diff| = 0`。

### 变更文件

| 文件 | 变更 |
|------|------|
| [modules/factor_adaptive_winsor/core/transformers.py](modules/factor_adaptive_winsor/core/transformers.py) | 模块级 `rank_transform_1d` + 别名常量; `AdaptiveTransformer` 无状态重写; 删除选型链与 `_fit_*` |
| [adapters.py](adapters.py) | PL-02 常量; 构造期方法解析; `fit` no-op; `transform` identity 短路与截面 rank; `get_stats` |
| [config_v2.py](config_v2.py) | `TransformationConfig` 收敛 + `target_distribution`; 删除 `conditional_transform`; 桥接映射 |
| [pipelines_v2.py](pipelines_v2.py) | `PipelineV2Config` 四字段; Static/Mixed 入参; Mixed 顺序; 删除 `_diagnose_transform_need` |
| [demo_v2.py](demo_v2.py) | 删除 2 处 `mixed_conditional_transform=True` |
| [tests/unit/test_transform_rank_cross_sectional.py](tests/unit/test_transform_rank_cross_sectional.py) | **新增** 28 函数 / 32 例 |
| [tests/unit/test_adaptive_transformer_identity.py](tests/unit/test_adaptive_transformer_identity.py) | **重写** 为 rank/先验方法行为测试 (9 例) |
| [tests/integration/test_pipeline_truncation_invariance.py](tests/integration/test_pipeline_truncation_invariance.py) | 摘除 PL-02/PL-04 xfail; 更新登记表与 PL-06/PL-07 reason |
| [tests/test_fix2_config_unification.py](tests/test_fix2_config_unification.py) | `test_09` / `test_11` 改用 `transformation.method/target_distribution` |
| `tests/test_pipelines_v2.py` / `tests/test_p3_phase2_config_migration.py` / `tests/test_adapters/test_module_enabled.py` | 删除已废弃字段; rank 无状态契约 |
| `tests/test_backtest/verify_fix2_manual.py` / `verify_fix3_manual.py` | 字段与版本锚点同步 |
| [tests/test_fix3_version_unification.py](tests/test_fix3_version_unification.py) | `EXPECTED_VERSION` → 3.3.4; 缓存断言 → v2.2.2-cache |
| [pyproject.toml](pyproject.toml) / [__init__.py](__init__.py) / [config_v2.py](config_v2.py) / [reporting.py](reporting.py) | 版本 → 3.3.4 |
| [backtest/cache_manager.py](backtest/cache_manager.py) | `CODE_VERSION` → v2.2.2-cache |
| [DECISIONS.md](DECISIONS.md) | 新增 ADR-038 + 占用登记 |
| [docs/analysis/PL02_TRANSFORM_LOOKAHEAD_RESEARCH.md](docs/analysis/PL02_TRANSFORM_LOOKAHEAD_RESEARCH.md) / [..._DESIGN.md](docs/analysis/PL02_TRANSFORM_LOOKAHEAD_DESIGN.md) | 调研/设计文档, 状态更新为已实施 |

### 兼容性与缓存

- **行为变更**: Static/Mixed 变换输出全部改变（逐日截面 rank，不再池化拟合与自选方法）；依赖旧变换数值的存量结果与缓存失效。
- **配置字段删除**: `PipelineV2Config.mixed_conditional_transform` / `mixed_skew_threshold` / `mixed_kurt_threshold` 与 `MixedPipelineConfig.conditional_transform`、`TransformationConfig.skew_threshold` / `kurt_threshold` 已删除。Pydantic 默认 `extra='ignore'`，旧 JSON/YAML 不会报错，但字段被**静默忽略**——尤其 `conditional_transform=False` 的原意是禁用变换，现在仍会执行 `rank`。原语义需迁移为 `transformation.method='identity'`。
- **显式方法**: `boxcox` / `yeojohnson` 现在必须提供 `lam`，`power` 必须提供 `power_param`；不再自动拟合。旧配置若依赖 auto 拟合，将得到 `ValueError`。
- **缓存代际**: `v2.2.1-cache` → `v2.2.2-cache`。`CacheManager.get_with_meta` 读取时校验 `meta.code_version`，不一致即 MISS 并删除旧数据/meta；首次访问旧缓存自动重建。
- **小截面**: 截面有效观测 `N<10` 回落逐日截面 z-score；`N<2` 原样返回（仅保护，不改变方法语义）。
- **ties**: 平均秩 → 相同输出值；排序不受影响。

### 实施偏差记录 (2026-10-22)

1. `tests/test_adapters/test_module_enabled.py::test_transformation_enabled_ignored_in_processing`：原断言 `fit` 后 `_processor is not None`；rank 无状态后改为断言 `_processor is None` 且 `transform` 确实改变数值，保持“transformation 不可消融”的原意。
2. `tests/test_pipelines_v2.py::test_neutralize_before_transform_reduces_industry_correlation`：旧顺序包含最后一步 OLS 中性化，R² 构造性为 0；新顺序 `neutralize→rank` 因非线性使 R² 轻微抬升（seed=999 实测 0.0057）。阈值由 `+0.005` 调整为 `+0.02`（仍为“行业信号基本消除”上限）。
3. `tests/unit/test_transform_rank_cross_sectional.py` 的有限样本矩断言按精确公式计算（`uniform` std `sqrt((N+1)/(3N))`；`normal` std 取 Blom 分数样本矩），而非极限值 `1/√3` / `1`。
4. `tests/unit/test_adaptive_transformer_identity.py` 的 `normal` std 同样改为 Blom 分数精确样本矩（N=2000 时 `0.9988613`，极限值差 `1.14e-3`）。

---

## v3.3.3 — PL-01 去极值因果性修复: 逐日横截面 (已实施, 2026-10-22)

### 概览

修复 DEFECT-PL-01: `ProcessingAdapter(process_type='outlier')` 的缩尾参数在全 panel 上池化拟合，且 `SmartOutlierDetector(auto_select=True)` 会覆盖显式方法——前 t 期输出依赖 t 之后的数据，同时名义上的 `percentile(1,99)` 实际按全样本特征自选方法执行。

**核心产出**:
- 去极值改为**逐日横截面**：每行只使用当日数据；`fit()` 对 outlier 成为 no-op，结构上无参数可泄漏
- `method='auto'` 构造期解析为 `percentile`；显式方法按声明执行；detector 侧始终 `auto_select=False`
- `percentile` 走向量化快速路径（2500×3000 面板 0.212–0.226s，逐行循环 2.56s）；其他方法逐行复用 detector，保留原截断语义
- 新增 30 项单测；集成套件由 `6 passed / 6 xfailed` 变为 `7 passed / 5 xfailed`（PL-01 摘除 xfail）
- 新增 **ADR-037**；项目版本 **3.3.3**；缓存 `CODE_VERSION` **v2.2.1-cache**（读取时校验代际，旧缓存自愈失效）
- 关联回归: 37 passed / 5 xfailed（新单测 + 集成）；适配器回归 38 passed / 2 skipped；缓存相关 91 passed

### 缺陷根因 (三层叠加)

| # | 根因 | 证据 |
|---|------|------|
| 1 | `fit()` 用 `X.values.flatten()` 在全 panel 上拟合缩尾参数 | 截断 60/100 期: 187 格差异, `max_abs_diff=1.68e-01` |
| 2 | `auto_select=True` 用全 panel 分布特征覆盖显式 `method` | 显式 `percentile` 实际拟合 `mad`, `threshold=2.7725`; 200/200 个变波动率面板截断前后选型不同 |
| 3 | 管线配置的分位/阈值参数未被 adapter 消费 | 修复前经 `to_pipeline_config()` 传入，`fit()` 实例化 detector 时 `TypeError`；修复后不再报错，但字段仍被忽略（后续任务） |

这也是 **ADR-027 的实施缺口**: "所有 `auto` → 固定方法" 与 "Winsorizer percentile(1,99)" 早已决定，但 adapter 层未落实。

**为何长期未被发现**: 缩尾是单调变换。前视与截断输出的逐日 Spearman 中位数 = 1.000，最小值 = 0.9973；排序类指标几乎无感，只有值相等的截断不变式能暴露。

### 实测矩阵 (`T=100, N=30, t=60, atol=1e-12`)

| 层级 | 对象 | 修复前 | 修复后 |
|------|------|--------|--------|
| step | outlier percentile | 187 格, 1.68e-01 | **0 格, 0** |
| step | transform auto | 1800 格, 8.51e-04 | 1800 格, 8.51e-04（PL-02，未修） |
| pipeline | Static | 1800 格, 1.33e-02 | **1800 格, 4.72e-05**（残留仅 PL-02） |
| pipeline | Dynamic | 1653 格 + 8 NaN, 8.05e-01 | 不变（PL-05，不含 outlier 步骤） |
| pipeline | Mixed | 1800 格, 2.91e-01 | 不变（PL-06，使用自身全样本缩尾） |
| top | FactorProcessingPipelineV2 | 1650 格, 1.84e+00 | 不变（PL-07，含指纹路由） |

诊断报告: 违反 4 项 / 满足 5 项（修复前为违反 5 项 / 满足 4 项）。

### 变更文件

| 文件 | 变更 |
|------|------|
| [adapters.py](adapters.py) | outlier 常量 + 构造期解析/校验 + `fit` no-op + `transform` 分支 + 3 个 helper + `get_stats` 字段 |
| [tests/unit/test_outlier_cross_sectional.py](tests/unit/test_outlier_cross_sectional.py) | **新增** 15 项测试（参数化后 30 例）：方法解析 / 边界 / 因果性 / NaN / 小截面 / 零离散 / identity / 统计字段 |
| [tests/integration/test_pipeline_truncation_invariance.py](tests/integration/test_pipeline_truncation_invariance.py) | 移除 PL-01 xfail; 更新缺陷登记表与 PL-04/05/06/07 reason |
| [tests/test_fix3_version_unification.py](tests/test_fix3_version_unification.py) | 版本锚点 → 3.3.3; 缓存断言 → v2.2.1-cache |
| [pyproject.toml](pyproject.toml) / [__init__.py](__init__.py) / [config_v2.py](config_v2.py) / [reporting.py](reporting.py) | 版本 → 3.3.3 |
| `backtest/cache_manager.py` + 4 个缓存默认值 | `CODE_VERSION` → v2.2.1-cache |
| [DECISIONS.md](DECISIONS.md) | 新增 ADR-037 + 占用登记; ADR-029 追加后续测量 |
| [docs/analysis/PL01_OUTLIER_LOOKAHEAD_RESEARCH.md](docs/analysis/PL01_OUTLIER_LOOKAHEAD_RESEARCH.md) / [..._DESIGN.md](docs/analysis/PL01_OUTLIER_LOOKAHEAD_DESIGN.md) | 调研/设计文档, 状态更新为已实施 |

### 兼容性与缓存

- **行为变更**: 去极值输出数值改变（不再池化、不再自选方法），依赖旧缩尾数值的存量结果与缓存失效。
- **缓存代际**: `v2.2.0-cache` → `v2.2.1-cache`。`CacheManager.get_with_meta` 读取时校验 `meta.code_version`，不一致即 MISS 并删除旧数据/meta；`verify` 返回 `code_version mismatch`。首次访问旧缓存会自动重建；缓存版本仍不跟随项目版本。
- **单一来源**: 4 个子缓存默认值改为引用 `cache_manager.CODE_VERSION`，避免多处字面量漂移。
- **接口**: 无公开 API 破坏。`ProcessingAdapter(outlier)` 仍接受原参数；未知方法/非法分位改为构造期 `ValueError`（原为静默覆盖或延迟失败）。
- **小截面**: 行内有效观测 < 3 或零离散度时该行原样返回（不缩尾），与 detector 内部判据一致。

### 评审修订 (2026-10-22)

评审发现初版缓存 bump 只改了 `CODE_VERSION` 常量，但 `CacheManager.get/verify` 从未校验 `meta.code_version`，旧缓存仍会命中并返回修复前的数值。已补：

- `CacheManager.get_with_meta`: 代际不一致 → MISS + 删除旧数据/meta
- `CacheManager.verify`: 代际不一致 → `is_valid=False`
- 新增 `TestCodeVersionGeneration` 3 项单测 + `test_07` 五处默认值一致性测试
- 修正 ADR-037 中配置 `TypeError` 的发生位置（`fit` 而非桥接）、Arnott 等作者名单、性能实测口径

### 已知未修 (保持 xfail 登记)

- **PL-02**: 变换 `fit` 仍全 panel flatten 拟合 λ（8.51e-04）
- **PL-05**: 解耦器 AR 用样本内 `fitted_values` 充当 OOS 预测（8.05e-01, 8 NaN）
- **PL-06**: Mixed 自有 `_compute_winsorize_params` 全样本缩尾（2.91e-01）
- **PL-07**: 顶层叠加残留缺陷 + 指纹路由依赖全样本（1.84e+00）

---

## v3.3.2 — 管线级因果性测试 + 标准化因果性修复 + ADR 编号治理 (已实施, 2026-10-21)

### 概览

接续 Claude 外部评审对新管线级缺陷的指认, 本轮不以"修某个函数"为起点, 而是先建立**可证伪的因果性测量仪器**, 由测试暴露问题清单, 再按实测幅度决定修复顺序。同时清理长期存在的 ADR 编号冲突与未记录的已实施决策。

**核心产出**:
- 新增管线级**截断不变式测试** (12 项, 6 通过 / 6 登记缺陷), 把"无前视"变成可执行判据
- 修复 DEFECT-PL-03: 标准化 `method='auto'` 全样本前视 (实测 6.18e-01 → 0)
- 处置 ADR-030 记录的 Mixin 耦合风险 (发现并修掉一处**布局注释与实现相反**的陷阱)
- ADR 编号治理: 建立登记规则 + 勘误表 + 补记 ADR-030~036 (7 条)
- **版本号统一到 3.3.2**: 4 处声明 (pyproject / `__init__` / config_v2 / reporting) 收敛, 字段级测试改为比对本包 `__version__`
- 关联回归: 80 passed / 6 xfailed / 0 failed

**修正了两项此前的判断** (见下文各节):
1. 外部评审称"Mixed 管线输出不再是单位方差"——**不成立**, 实测为 1.0
2. 此前的分析认为"标准化逐日截面即因果"——**只对 `z_score` 成立**, `'auto'` 走的是 per-column 全样本分支

### 新增: 管线级截断不变式测试

**文件**: [tests/integration/test_pipeline_truncation_invariance.py](tests/integration/test_pipeline_truncation_invariance.py)

**不变式**: 对任意截断点 t, 用 `[0, t]` 数据跑出的 `[0, t]` 期输出, 必须等于全样本 `[0, T]` 跑后截取 `[0, t]` 期的输出。这是"无前视"的操作化定义, 不依赖实现者是否想到某个步骤有前视。

**结构** (三层 + 仪器):

| 层 | 内容 | 作用 |
|----|------|------|
| `TestIsolatedStepInvariance` | 每步单独喂**相同输入**独立测量 | 定位首个违反步骤, 避免上游前视污染下游判定 |
| `TestSubPipelineInvariance` | Static / Dynamic / Mixed 端到端 | 暴露步骤间传播效应 |
| `TestTopLevelInvariance` | `FactorProcessingPipelineV2` 全链路 | 含指纹路由决策的前视 |
| `test_diagnostic_report` | 恒通过的测量表 | 修复前后可对比, 逐行 `n_diff_cells` 应降为 0 |

**缺陷登记机制**: 预期违反的测试标 `xfail(strict=True, raises=AssertionError)`, reason 携带缺陷编号与实测数值。套件保持全绿的同时登记已知缺陷; 缺陷一旦修好, 该测试报 "unexpectedly passing" **强制摘标记**。`raises=AssertionError` 确保 ImportError/KeyError 等仍作为真错误暴露, 不被 xfail 吞掉。

**实测矩阵** (PL-03 修复后, `T=100, N=30, t=60, atol=1e-12`, Python 3.12):

| 层级 | 对象 | 状态 | 差异格 | 最大绝对差 |
|------|------|------|--------|-----------|
| step | imputer `ffill_ts` | PASS | 0 | 0 |
| step | outlier percentile | FAIL (PL-01) | 187 | 1.680e-01 |
| step | neutralize (逐日 OLS) | PASS | 0 | 0 |
| step | transform auto | FAIL (PL-02) | 1800 | 8.506e-04 |
| step | standardize `'auto'` | PASS (已修) | 0 | 0 |
| step | standardize `'z_score'` | PASS | 0 | 0 |
| pipeline | Static | FAIL | 1800 | 1.326e-02 |
| pipeline | Dynamic | FAIL (+8 NaN) | 1653 | 8.045e-01 |
| pipeline | Mixed | FAIL | 1800 | 2.906e-01 |

**结论**: 5 个处理步骤中, 插补 / 中性化 / 标准化(`z_score`)满足因果性; 去极值 / 变换不满足。解耦器 AR 另有结构性缺陷 (PL-05)。

### 修复 1: DEFECT-PL-03 标准化 `'auto'` 全样本前视

**位置**: [adapters.py](adapters.py) `ProcessingAdapter.__init__`

**根因 (两层)**:
1. **分支判定用 method 字面量**: `_cross_sectional_zscore` 仅在 `method == 'z_score'` 时为 True。`StaticFactorPipeline` 传 `'auto'`, 落入 per-column 分支 — `fit()` 在全样本上对每列拟合 `(mean, std)`, `transform()` 套用固定参数 → 前 t 期结果依赖 t 之后样本
2. **`'auto'` 的方法选择本身依赖全样本**: `AdaptiveStandardizer._vote_on_method` 依据 `outlier_ratio / is_heavy_tailed / is_skewed / cv` 投票选出方法 → 第二重前视源, 且同一输入在不同窗口可能选到不同方法

**修复**: `standardization + 'auto'` 于构造期解析为 `'z_score'`, 命中逐日横截面分支。该分支 `fit()` 为 no-op (不存参数), `transform()` 逐期独立计算 `(x - mean_t) / std_t` → **结构上无可泄漏参数**。

| 对象 | 修复前 | 修复后 |
|------|--------|--------|
| `standardize(method='auto')` 单步 | 1800/1800 格差异, 6.18e-01 | **0** |
| `StaticFactorPipeline` 端到端 | 4.03e-01 | **1.33e-02** (降 30 倍) |

**破坏性影响**: `StaticFactorPipeline` 输出数值变更, 此前用它产出的因子值 / IC / Sharpe 需重算。

**测试契约变更** (2 处, 已记入 ADR-029):
`tests/test_adapters/test_module_enabled.py` 与 `tests/test_pipelines_v2.py` 原断言 `result.mean(axis=0) ≈ 0` (列均值)。依据: **列均值 == 0 恰是全样本 per-column 标准化的定义特征**——任何因果变换在数学上都无法满足该等式, 故该断言成立本身就是前视的症状。已改为逐日横截面断言 (行均值 ≈ 0、行标准差 ≈ 1)。

**外部评审结论修正**: 评审称"混合因子偏度 > 2 触发变换时, 标准化参数来自未变换尺度, 输出不再是单位方差"——**不成立**。Mixed 传的是 `'z_score'`, 命中行内重算分支, 完全不读 fit 参数。新增 `test_mixed_pipeline_output_is_unit_variance` 实测逐日截面 std 中位数 ≈ 1.0 予以固定。

### 修复 2: ADR-030 Mixin 耦合风险处置

**位置**: [modules/factor_decoupler/diagnostics/hidden_effect.py](modules/factor_decoupler/diagnostics/hidden_effect.py) · [core/ar_model.py](modules/factor_decoupler/core/ar_model.py) · [core/dual_neutralizer.py](modules/factor_decoupler/core/dual_neutralizer.py)

补记 ADR-030 时核查代码, 发现耦合风险的实际形态**比原记录更严重**:

| # | 形态 | 性质 |
|---|------|------|
| 1 | 探测私有 `_results` → 结构变则返回 `None` → 报 `'AR model not fitted'` | 误报 (模型其实已 fit) |
| 2 | 该分支同时返回 `is_incremental_endogenous=False` | **假阴性: 谎报"无内生性"** |
| 3 | `ARModelResult.coefficients` 注释写 `[phi_1, ..., phi_p, intercept]`, 而 `_fit_ar` 把常数项插在**列首** | **布局陷阱**: 照注释改代码会静默取错 φ, 不报错 |

**处置**:

| 措施 | 实现 |
|------|------|
| φ 提取收拢为显式契约 | 宿主实现 `_get_ar_phi_for_diagnosis()`; Mixin 不再探测任何私有属性 |
| 布局假设单点化 | `AR_COEF_INTERCEPT_INDEX` / `AR_COEF_PHI1_INDEX` 具名常量, 仅在 `ARDecoupler` 钩子内使用 |
| 注释纠偏 | `ARModelResult.coefficients` 注释改为真实布局 `[intercept, phi_1, ..., phi_p]` |
| `CompositeDecoupler` 纯委托 | 钩子只转发内部 `ARDecoupler`, 本类不假设内层结构 |
| **破坏即报错** | 已 fit 却取不到 φ → 抛 `DiagnosticContractError`, 不再静默降级 |
| 语义钉子 | 新增 `TestDiagnosticContract` 8 项 |

**未 fit 仍走软提示** (两阶段分离语义不变, E1-T21 继续通过); 契约收紧只作用于「已 fit 但取不到 φ」这一原本会误报的情形。

### 治理: ADR 编号冲突与补记

**冲突规模** (排查后远大于单个编号): 3 份规划文档各自把 ADR-026 分配给不同决策, 且 v3.1.0 一次性预留 ADR-026~031 共 6 个编号, 与实际占用大面积冲突。

**处置** (详见 [DECISIONS.md](DECISIONS.md) 文首「ADR 编号登记规则与勘误」):
- 建立 3 条登记规则 (编号唯一集中分配 / 规划文档不得预留 / 引用须可检索)
- 勘误表 8 行, 逐条标注「作废 + 改记去向」
- 补记 7 条此前从未写入的 ADR: ADR-030 (E1 隐藏效应) / 031 (E2 P-hacking) / 032 (E3 内生性 S1-S4) / 033 (E4 格兰杰) / 034 (E5 三层正则化) / 035 (E6 估计层) / 036 (消融对照机制)
- 4 处冲突点置入 ⚠️ 勘误注 (EXECUTION_V3.1.0 / EXECUTION_ABLATION_V3.0.0 / audit 报告)

**勘误表自身的一次腐化与修正**: 首版用精确行号 (`:539, :3944`), 但在 DECISIONS.md 顶部插入内容后行号全部失效。已改为只标「文件名 + 出现次数」, 以「声明内容」列为检索键, 消除此类漂移。

**连带修正**:
- 代码注释编号错误: `pipelines_v2.py` 中 E1/E2 原标 `ADR-024` (实际是"指纹 21 维"), 改为 ADR-030 / ADR-031
- `ARCHITECTURE.md` 三处模块 ADR 归属: `endogeneity_check` 原归 ADR-026 (错误归属) → ADR-032; 并修正类名 `Ivx`→`IVXEstimator`、`Regularizer`→`EndogeneityRegularizer` 等
- `WORKFLOW_METHODOLOGY.md`: `ADR-001 至 ADR-025` → `至 ADR-036`

### 统一: 版本号 3.3.2

此前 `pyproject.toml` / `__init__.__version__` 停留在 `2.5.0`, 而本条目按 `3.3.x` 演进, 属上一轮显式记录的遗留缺口。本轮收敛:

| 位置 | 值 |
|------|-----|
| [pyproject.toml](pyproject.toml) | `3.3.2` |
| [__init__.py](__init__.py) | `__version__ = "3.3.2"` |
| [config_v2.py](config_v2.py) | `PipelineV2ConfigUnified.version = "3.3.2"` |
| [reporting.py](reporting.py) | `PipelineExecutionReport.pipeline_version = "3.3.2"` |

**消除重复锚点**: `tests/unit/test_config_v2.py` / `test_reporting.py` / `test_factor_orthogonalizer/test_adapter.py` 原各自持有字面量 (上一轮 `2.5.0` 的漂移正是这样发生的), 现改为比对本包 `factor_pipeline.__version__`; 唯一绝对锚点留在 `tests/test_fix3_version_unification.py` 的 `EXPECTED_VERSION`, 并新增 `test_06_pyproject_version_matches_package` 校验 `pyproject.toml` 与包版本一致。

**不参与统一**: `backtest/cache_manager.py` 的 `CODE_VERSION = "v2.2.0-cache"` 是缓存语义版本, 与项目版本解耦 (v3.3.3 因 PL-01 算法变更 bump 至 `v2.2.1-cache`, 见上); `modules/*` 子包各自维护独立版本 (decoupler 1.2.0 等)。

### 测试结果

| 范围 | 结果 |
|------|------|
| 新增 `test_pipeline_truncation_invariance.py` | 12 项 (6 通过 / 6 xfail 登记缺陷) |
| `test_hidden_effect.py` | 29 passed (原 21 + 契约测试 8) |
| `test_factor_decoupler/` + `test_pipelines_v2` + `test_pipelines_v2/` + `integration/` | **80 passed, 6 xfailed, 0 failed** |
| `unit/` + `demo_notebook` + `integration` (PL-03 阶段) | 262 passed, 2 skipped, 0 failed |
| 适配器 / 管线 / 多维度 / P1 (PL-03 阶段靶向) | 123 passed, 2 skipped, 6 xfailed, 0 failed |
| 版本统一靶向 (`test_fix3_version_unification` + `unit/test_config_v2` + `unit/test_reporting` + `orthogonalizer/test_adapter`) | **62 passed, 0 failed**; 手工校验脚本 5/5 (4 处声明 + pyproject, 缓存独立) |

### 已知遗留

**缺陷登记** (xfail 追踪, 按实测幅度排序):

| 编号 | 缺陷 | 实测 |
|------|------|------|
| DEFECT-PL-01 | `ProcessingAdapter` 去极值 `X.values.flatten()` 全 panel 拟合 → 全样本分位数 | 187 格 / 1.68e-01 |
| DEFECT-PL-05 | 解耦器 `ar_model.transform` 用样本内 `fitted_values` 充当 OOS 预测 | 8.05e-01 + 8 格 NaN 模式差 |
| DEFECT-PL-02 | 变换全 panel 拟合 λ; `'auto'` 选型亦依赖全样本 | 8.51e-04 (普遍但量级小) |

**其它**:
- 标准化 `'robust' / 'min_max' / 'quantile'` 仍走 per-column 全样本分支 (非因果), 三条生产管线均未使用, 已在测试文件登记为"已知未登记"
- ~~版本号漂移~~ **已在本轮消除**: 4 处声明统一为 `3.3.2`, 见上文「统一: 版本号 3.3.2」
- 全量 800+ 套件未完成长跑: `tests/test_backtest/test_p3_phase4_integration.py` 的 optimizer 模拟为主要耗时来源, 需单独安排

### 文档产出

- `DECISIONS.md`: ADR-029 (新增) + ADR 编号登记规则与勘误 + ADR-030~036 (补记) + ADR-030 耦合风险处置小节
- `docs/ARCHITECTURE.md`: ADR 索引与模块归属更新
- `docs/WORKFLOW_METHODOLOGY.md`: ADR 范围、模板占位符 (ADR-0XX) 修正
- `docs/EXECUTION_V3.1.0.md` / `docs/EXECUTION_ABLATION_V3.0.0.md` / `docs/audit/2026-07-08-ablation-code-quality-audit.md`: 勘误注

---

## v3.3.1 — 插补模块 P2 完成 + 学术引用修正 (已实施, 2026-07-27)

### 概览

v3.3.0 完成后, 对插补模块 (`factor_imputer`) 进行 P2 阶段收尾, 包含 3 项学术引用修正 + 3 项 P2 任务 (向量化 + e2e 测试 + 消融实验)。同时新增架构文档 / 进度矩阵 / 工作流方法论升级 (v1.3)。

**核心产出**:
- 3 项学术引用修正 (Little & Rubin 术语 / Breiman 2001 多输出 RF / Lopez de Prado 章号)
- P2-1: `_transform_rf_shared` 向量化 (1 次 predict 替代 N 次循环, 1e-12 精度等价)
- P2-3: 9 项端到端测试 (含静态扫描 + 严格因果性验证)
- P2-4: 10 项消融实验 (含 IC 范围 + 严格因果性消融)
- 全量回归: 803 passed / 10 skipped / 0 regressions

**文档产出**:
- `docs/ARCHITECTURE.md` v1.0 — 项目架构总览 (6 层分层 + 模块边界 + 数据流)
- `docs/DEV_PROGRESS.md` v1.0 — 版本 × 模块双维度进度矩阵
- `docs/EXECUTION_V3.3.1_IMPUTER_P2.md` — 本次会话详细实施记录
- `docs/WORKFLOW_METHODOLOGY.md` v1.3 — 整合 10 步 spec 规范 (调研→设计→实施→验收)

### 修正 1: Little & Rubin §4.3 术语

| 项 | 值 |
|----|-----|
| 问题 | 原引用 "因果填充原则" 非 Little & Rubin (2002) 标准术语 |
| 修正 | 改为 "fill within-unit first, then across-units" + 标注非标准术语 |
| 位置 | [tests/unit/test_imputer_lookahead_fix.py:11-13](tests/unit/test_imputer_lookahead_fix.py#L11-L13) |

### 修正 2: Breiman 2001 多输出 RF 补专门文献

| 项 | 值 |
|----|-----|
| 问题 | Breiman (2001) 未明确讨论 multi-output RF, 作为共享 RF 方案唯一引用不严谨 |
| 修正 | 新增 Segal & Xiao (2011) WIREs DMKD + van der Westhuizen et al. (2023) Geoderma |
| 位置 | [docs/analysis/IMPUTER_LOOKAHEAD_FIX_PLAN.md:520-521](docs/analysis/IMPUTER_LOOKAHEAD_FIX_PLAN.md#L520-L521) |

### 修正 3: Lopez de Prado §7 章号保守引用

| 项 | 值 |
|----|-----|
| 问题 | §7 章号未能从数据库逐章核验 |
| 修正 | 改为 "Chapter on Cross-Validation Methods in Finance" 保守引用 (附 ISBN 978-1-119-44811-0) |
| 位置 | [tests/unit/test_imputer_lookahead_fix.py:15-18](tests/unit/test_imputer_lookahead_fix.py#L15-L18) |

### P2-1: 向量化剩余 for 循环

| 项 | 值 |
|----|-----|
| 实现 | [modules/factor_imputer/core/imputers.py:587-645](modules/factor_imputer/core/imputers.py#L587-L645) |
| 改动 | N 次 predict → 1 次 predict + `missing_mask` 一次性填充 |
| 等价性 | `test_shared_model_batch_equivalent_to_per_row` (1e-12 精度) |
| 保留 for 循环 | KNN walk_forward (因果本质不能向量化) + FactorSpecificImputer missing indicator (单列赋值已 O(T)) |

### P2-3: 端到端测试 (9 项)

| 测试类 | 数量 | 验证内容 |
|--------|------|---------|
| `TestE2ECausalProperty` | 2 | ffill_ts 截断不变性 + 无未来异常值泄漏 |
| `TestE2ELookaheadSafeOnOff` | 2 | lookahead_safe=True/False 两条路径都跑通 |
| `TestE2EAllStrategiesCausal` | 1 | cross_sectional 因果性 (参数化) |
| `TestE2ESourceScan` (新增) | 2 | 静态扫描 adapters.py / imputers.py 无 .bfill() |
| `TestE2EStrictCausality` (新增) | 2 | 严格因果: 截断任意时间点历史不变 + 修改未来数据历史不变 |

### P2-4: 消融实验 (10 项)

| 测试类 | 数量 | 验证内容 |
|--------|------|---------|
| `TestAblationLookaheadSafe` | 3 | ON/OFF 跑通 + 前期填充值不同 + KNN walk_forward vs legacy 差异 |
| `TestAblationAdapterLevel` | 3 | lookahead_safe 透传 + ON/OFF 结果不同 |
| `TestAblationICRange` (新增) | 2 | IC ∈ [-1, 1] (cross_sectional + KNN walk_forward) |
| `TestAblationStrictCausality` (新增) | 2 | ON 满足截断不变性 + OFF 不满足 (验证切换确实改变语义) |

### 测试结果

```
插补相关测试: 52 passed in 5.21s
全量回归: 803 passed / 10 skipped / 0 regressions
```

| 测试文件 | 通过 / 总数 |
|---------|------------|
| `test_imputer_lookahead_fix.py` | 33 / 33 |
| `test_imputer_e2e_causal.py` | 9 / 9 |
| `test_imputer_ablation_lookahead.py` | 10 / 10 |

### 工作流方法论升级 (v1.3)

`docs/WORKFLOW_METHODOLOGY.md` 从 v1.2 升级至 v1.3, 新增 §13 整合 10 步 spec 规范:
- 10 步 ↔ 7 阶段映射表 (调研→设计→实施→验收显式化)
- 三类新工件定义: 调研文档 / 验收 checklist / 跨文档一致性 review
- 双幻觉消除 review (步骤 4 + 步骤 6)
- 工程细节显式检查 (版本 / 依赖 / 兼容 / 接口 / 签名 / 低效操作)
- 适用范围与裁剪规则 (大/中/小任务)
- v3.3.1 回溯适用性 (部分实例, 后续版本应补全步骤 7-8)

---

## v3.3.0 — Layer 3 溢价健康诊断双层体系 (已实施, 2026-07-15)

### 概览

在 v3.2.0 学术准则驱动管线重构基础上，完成 6 项改进任务 + 新增 Layer 3 FactorHealthDiagnoser 模块。实现从"因子分类"到"溢价健康诊断"的完整诊断链路：Layer 2 StatisticalClassifier 解决"因子是什么类型" → Layer 3 FactorHealthDiagnoser 解决"因子是否还在定价"。与 Layer 5 FactorHealthMonitor 互补不合并。

**核心产出**:
- 6 项任务全部完成: L2 Routing 消融修复 + 更多因子测试 + 跨市场验证 + 原则评分 92% + 真实数据全量消融 + Pipeline 日志
- 1 个新模块: `modules/factor_health/` (3 个核心类: PremiumEstimator + BreakpointDetector + FactorHealthDiagnoser)
- 1 项新 ADR: ADR-028 (Layer 3 溢价健康诊断)
- 兼容性分析: FactorHealthDiagnoser vs FactorHealthMonitor — 互补不合并
- 全量回归: 128/128 passed (v3.2.0 基线) + 9/9 Layer 3 TDD 测试
- 真实数据验证: A股 3 因子 (momentum=pricing, volatility=review, turnover=review)

### Task 1: L2 Routing 消融修复 (P0)

| 项 | 值 |
|----|-----|
| 问题 | 硬路由 (Hard routing) 使用 StatisticalClassifier 的 return_type 替代原 softmax 权重，消融实验配置需更新 |
| 修复 | 5 个消融配置全部适配新路由，`run_l2` 方法名修正 |
| 测试 | 5 tests — 5 配置消融全部通过 (B3 IC=-0.0003, Sharpe=0.111) |

### Task 2: 更多因子测试 (P1)

| 项 | 值 |
|----|-----|
| 目的 | 验证 StatisticalClassifier 在更多因子上的分类稳定性 |
| 结果 | 10 因子分类验证通过，分类结果与预期一致 |
| 脚本 | `scripts/test_more_factors.py` |

### Task 3: 跨市场验证 (P1)

| 项 | 值 |
|----|-----|
| 目的 | 验证 StatisticalClassifier 的跨市场迁移性 |
| 结果 | 4 市场 (A股/美股/港股/加密货币) 544 因子 100% 分类一致 |
| 脚本 | `scripts/test_cross_market.py` |

### Task 4: 原则评分 92% (P1)

| 项 | 值 |
|----|-----|
| 改动 | StatisticalClassifier: AR(1) 平稳性从硬编码 0.98 阈值 → Dickey-Fuller τ 检验 (Dickey & Fuller 1979) |
| 改动 | adapters.py: AR check 从硬编码 R²>0.01 → F-test + Bonferroni 校正 (Fisher 1924) |
| 改动 | dead code 清理: adapters.py 移除不可达 `return result` |
| 原则评分 | 68% → ~92% (+24% 原则比重) |
| 测试 | 4 tests — DF 检验正确性 + F-test 正确性 |

### Task 5: 真实数据全量消融 (P1)

| 指标 | 值 |
|------|-----|
| B3 IC_mean | -0.0003 |
| B3 Sharpe | 0.111 |
| winsorizer ΔIC | 显著 |
| scaler ΔIC | 显著 |
| 脚本 | `scripts/run_ablation_real.py` |

### Task 6: Pipeline 日志 (P2)

| 项 | 值 |
|----|-----|
| 新增字段 | `_intermediate_data: Dict[str, Dict[str, pd.DataFrame]]` |
| 新增方法 | `get_intermediate_data()` |
| 改动 | pipelines_v2.py transform 循环收集中间数据 |
| 测试 | 4 tests — 中间数据记录/可访问性/格式正确性 |

### Layer 3: FactorHealthDiagnoser (新模块)

**模块结构**:

| 类 | 职责 | 行数 | 学术依据 |
|----|------|------|---------|
| `PremiumEstimator` | Fama-MacBeth + Epanechnikov 核 → λ̂(t) | ~70 | Fama-MacBeth 1973 + Epanechnikov 1969 |
| `BreakpointDetector` | 网格搜索 Chow F-test 断点检测 | ~70 | Chow 1960 + Bai-Perron 1998 |
| `FactorHealthDiagnoser` | 多状态综合诊断 (pricing/recalibrate/monitor/review/suspect) | ~170 | 综合上述 |

**关键设计决策**:
1. 断点检测用 raw β_t 不用 kernel-smoothed λ̂_t (避免 F 统计量膨胀)
2. 无 Bonferroni 校正 (对 raw betas 过于保守)
3. bandwidth=24 (≈2年月度), half_life_threshold=60 (5年)

**与 FactorHealthMonitor 的兼容性**:

| 维度 | FactorHealthMonitor (已有) | FactorHealthDiagnoser (新增) |
|------|--------------------------|---------------------------|
| 分析视角 | 横截面快照 | 时间序列过程 |
| 核心问题 | "因子现在健康吗？" | "溢价什么时候断的？还在定价吗？" |
| 输入数据 | factor + returns + market_cap + volume | factor + forward_returns + return_type |
| 方法论 | IC/IR/HHI/换手率 启发式阈值 | Fama-MacBeth + Chow F-test + Epanechnikov 核 |
| 输出 | FactorHealthReport (0-100分) | dict (分类标签 + 溢价统计) |

**合并决策**: **不合并，保持独立互补**。两个模块正交 — HealthMonitor 在"因子使用"层面，HealthDiagnoser 在"因子定价"层面。建议顺序使用：HealthMonitor 快速筛选 → 对 flagged 因子用 HealthDiagnoser 深度诊断。

**A股 3 因子真实验证**:

| 因子 | premium_health | combined label | 断点位置 | pre_mean | post_mean |
|------|---------------|----------------|---------|----------|-----------|
| momentum_1m | stable | pricing | 无 | — | — |
| volatility_1m | ES | review | t=44 | -0.0038 | 0.0120 |
| turnover | ES | review | t=133 | -0.00002 | 0.00008 |

### 学术依据

- Fama, E. F., & MacBeth, J. D. (1973). Risk, return, and equilibrium: Empirical tests. *JPE*, 81(3), 607-636.
- Epanechnikov, V. A. (1969). Non-parametric estimation of a multivariate probability density. *Theory of Probability & Its Applications*, 14(1), 153-158.
- Chow, G. C. (1960). Tests of equality between sets of coefficients in two linear regressions. *Econometrica*, 28(3), 591-605.
- Bai, J., & Perron, P. (1998). Estimating and testing linear models with multiple structural changes. *Econometrica*, 66(1), 47-78.
- Dickey, D. A., & Fuller, W. A. (1979). Distribution of the estimators for autoregressive time series with a unit root. *JASA*, 74(366), 427-431.
- Fisher, R. A. (1924). On a distribution yielding the error functions of several well known statistics. *Proceedings of the International Congress of Mathematics*, 2, 805-813.

---

## v3.2.0 — 学术准则驱动管线重构 (已实施, 2026-07-10)

### 概览

系统审计 5 个核心处理模块的统计决策准则，发现 ~32% 依赖硬编码启发式阈值（数据迁就）。基于 15 篇学术文献（Box-Cox 1964 / Shapiro-Wilk 1965 / Bali-Engle-Murray 2016 / Lo-MacKinlay 1988 等）制定严格的统计决策准则，并逐步 TDD 实施。9 阶段执行计划中 P0 三步 + P1 Hard routing 已完成，全量回归 168/168 零回归。

**核心产出**:
- 3 篇分析文档: [academic_literature_decision_criteria.md](docs/analysis/academic_literature_decision_criteria.md) (含 §9 改进方案 + §10 执行顺序 + §11 验收标准) + [principle_vs_hacking_audit.md](docs/analysis/principle_vs_hacking_audit.md) + [ablation_post_fix_analysis.md](docs/analysis/ablation_post_fix_analysis.md) (含 P1 顺序 A/B 测试附录)
- 6 个 commits, 12 files changed, +1098/-185
- 消融实验: P0 三步后重跑，B3 IC=-0.0067, Sharpe=0.0028，winsorizer+scaler 显著 (p_bootstrap=0.016)
- 全量回归: 168/168 passed + 4 warnings (零回归)

### Step 1: Winsorizer `method='percentile'` (1%/99%) — Bali et al. 2016

| 项 | 值 |
|----|-----|
| 学术依据 | Bali, Engle & Murray (2016): "all variables are winsorized at the 1st and 99th percentiles" — JFE/JF/RFS 事实标准 |
| 改动 | `SmartOutlierDetector` 新增 `method='percentile'` → `np.percentile([1, 99])` + `np.clip` |
| 管线 | 三个管线 `method='auto'` → `method='percentile', percentile_lower=1.0, percentile_upper=99.0` |
| MixedPipeline | `_compute_winsorize_params` 从 3σ → `np.nanpercentile(arr, [1, 99], axis=0)` |
| 测试 | 4 tests — fit/clip/preservation/cross-sectional |
| commit | `38966db` |

### Step 2: Transformer Shapiro-Wilk 正态性检验 — Shapiro & Wilk 1965

| 项 | 值 |
|----|-----|
| 学术依据 | Shapiro & Wilk (1965): 形式正态性检验 H₀: normal, α=0.05 |
| 改动 | `_analyze_features`: 启发式 `abs(skew)<0.5 & abs(kurt)<1` → `shapiro(sample).pvalue ≥ 0.05` |
| fallback | Shapiro-Wilk 失败时 (degenerate data) → heuristic fallback |
| 新增字段 | `normality_p_value`, `normality_test` |
| 测试 | 2 新测试 (8 total) — N(0,1)→identity / skewed exp(2)→yeojohnson |
| commit | `480cb3d` |

### Step 3: Imputer `strategy='ffill_ts'` — Little & Rubin 2002

| 项 | 值 |
|----|-----|
| 学术依据 | Little & Rubin (2002) §4.3: "fill within-unit first, then across-units" |
| 改动 | `ImputerAdapter` 内置 `_transform_ffill_ts`: `X.ffill(axis=0)` → `row_median.fillna` → `fillna(0)` |
| 向量化 | O(T×N) pandas/numpy, 零 for 循环 |
| 管线 | 三个管线 `strategy='auto'` → `strategy='ffill_ts'` |
| 测试 | 4 tests — ffill/cross-median/no-nan-preserved |
| commit | `7e6bc08` |

### Step 4: 消融重跑

| 指标 | P0 前 (auto mode) | P0 后 (fixed methods) |
|------|------------------|----------------------|
| B3 IC_mean | -0.0074 | -0.0067 |
| B3 Sharpe | 0.0007 | 0.0028 |
| winsorizer ΔIC | -44.1% (**p=0.026**, 边界显著) | -51.7% (**p=0.016**, **显著**) |
| scaler ΔIC | +122.0% (**p=0.018**) | +128.0% (**p=0.016**, **显著**) |

关键发现: 固定方法后 winsorizer 的显著性从边界提升到正式显著 (p 从 0.026→0.016)，说明消除 auto 策略噪声后信号更干净。

### Step 7: Hard Routing + StatisticalClassifier — Lo & MacKinlay 1988

| 项 | 值 |
|----|-----|
| 学术依据 | Lo & MacKinlay (1988): Variance Ratio test + AR(1) stationarity |
| 新增模块 | `modules/statistical_classifier/` — 向量化面板分类 |
| 路由变更 | SOFT routing (加权混合) → **hard routing** (单管路线性变换) |
| 分类规则 | VR rejects random walk + stationary → static / VR OK + stationary → dynamic / else → mixed |
| 测试 | 4 tests — static→static / dynamic→dynamic / valid-type / speed<1s |
| commit | `add441b` |

### 决策历史

| 决策 | 结论 | 依据 |
|------|------|------|
| P1 StaticPipeline 顺序 | 保留新顺序 (no-revert) | A/B p=0.80 不显著，原则性更好，Spearman ρ=0.9958 近乎等价 |
| 市值中性化 | 集成到 B3 baseline | 市值是 momentum >70% alpha 来源，行业+市值 OLS 双重中性化 |
| SOFT → hard routing | 实施 | 无学术依据，破坏可审计性 |
| Auto → 固定方法 | 实施 | 消融可复现性 > IC 优化 |
| identity 回退 | 实施 | Box-Cox 不强制变换正态数据 |
| kurtosis 阈值 bug | 已修复 | scipy.stats.kurtosis 返回 excess kurtosis (~0 for N(0,1))，原代码错误假设 ~3 |

### Step 8: Anderson-Rubin 后验检验 (P2 监控) — Anderson & Rubin 1949

| 项 | 值 |
|----|-----|
| 学术依据 | Anderson & Rubin (1949), FWL 定理: 中性化后残差应正交于 dummies → R²≈0 |
| 改动 | `NeutralizerAdapter`: 新增 `enable_ar_check` + `_compute_ar_r2()` 静态方法 |
| 实现 | `_neutralize_with_cache` 循环内，OLS 拟合后 `np.linalg.lstsq(X, residuals)` → R² |
| 阈值 | mean R² > 0.01 → WARNING (中性化可能不完整); else → INFO |
| 性能 | O(k³) per period (k≤30 行业), 零额外循环 (复用 OLS residuals) |
| 默认 | `enable_ar_check=False` (向后兼容, 仅监控) |
| 测试 | 3 tests — disabled/enabled/near-zero R² |
| commit | `17447cf` |

### Step 9: 审计文档 v2.0 — 原则评分修正

| 项 | 值 |
|----|-----|
| 文档 | `docs/analysis/principle_vs_hacking_audit_v2.md` |
| 核心 | v1.0 评分 68%→88% (+20% 原则比重) |
| 逐模块 | Imputer 50%→85% / Winsorizer 50%→90% / Transformer 60%→85% / Routing 30%→80% |
| 剩余迁就 | 12%: Transformer 非正态分支 + Routing 0.98 阈值 + AR R² 0.01 阈值 (三者均可消除但 trade-off 合理) |
| 结论 | v3.2.0 为可迁移的学术级管线，每一步有 15 篇核心文献 (1964-2016) 支撑 |

### 学术依据 (15 篇)

| 文献 | 用途 |
|------|------|
| Box & Cox (1964) | 变换似然比检验 |
| Shapiro & Wilk (1965) | 正态性形式检验 |
| Lo & MacKinlay (1988) | Variance Ratio 可预测性 |
| KPSS (1992) | 平稳性检验 |
| Fama & French (1993, 2015) | 多因子模型残差中性化 |
| Jegadeesh & Titman (1993) | 动量因子基准 |
| Little & Rubin (2002) | 面板缺失插补 ffill |
| Huber & Ronchetti (2009) | 稳健统计缩尾 |
| Van Buuren (2011) | MICE 多重插补 |
| Bali, Engle & Murray (2016) | 1%/99% 缩尾行业标准 |
| Barroso & Santa-Clara (2015) | 动量波动率时变 |
| Novy-Marx & Velikov (2016) | 异常因子分类学 |
| Frisch & Waugh (1933) / Lovell (1963) | FWL 定理 — 中性化顺序等价 |

---

## v3.1.0 — Audit-Driven Code Quality Remediation (已实施, 2026-07-09)

执行 audit-driven-development 4 阶段流程: P0×8 + P1×8 + P2+×15 (断言恒真式重写 5 + 设计约束测试 10 + 端到端 2 + E5 测试补强 5) + spec 反向对齐 11 项。子集回归 754 passed + 1 skipped (零回归, E1-E10 + V3.1.0 E1-E6 范围)。

**断言恒真式重写 (A1-A4, 5 测试)**:
- RN-E2 Romano-Wolf: 相同 random_state bootstrap 一致 + 不同 random_state 差异
- E3-T21 critical_alert: 20 seed 循环非平凡触发
- E6-T10 IVX bias: IVX β 比 OLS β 更接近真值 0.3
- E6-T17/T18 SCAD/MCP: λ=1.0/5.0 时 n_zeroed>0 + λ 敏感性对照

**设计约束测试 (B1-B3, 10 测试)**:
- B1 Config 字段存在性 (3) / B2 配置生效 oster_r_max_multiplier+alert_threshold (2) / B3 method_formal_name+选择器逻辑 (5)

**E5 测试补强 (5 测试)**:
- 已知关系识别 (gpd_shape→ic_mean, β=0.3) / β 范围 (|β|≤1) / 零权重零贡献 / BH 单调性 (p_adj≥p) / 显著交互 (构造 β=2.0)

**spec 反向对齐 (11 项)**: E1 签名 / E2 stepdown / E4 log+SQL / E5 Layer2 / E9 _trend

**审计报告**: [docs/audit/2026-07-08-research-notes-v3.1.0-code-quality-audit.md](docs/audit/2026-07-08-research-notes-v3.1.0-code-quality-audit.md)
**commit**: 6192edb (7 files, +820/-87)

---

## v3.0.0 T3 — CUSUM 在线漂移检测 + BH-FDR 共享模块 (已实施, 2026-07-07)

### 概览

实施 v3.0.0 远期规划 T3 任务: Page (1954) CUSUM 算法实现 + ARL Monte Carlo 校准 + 管线集成 + BH-FDR 共享模块 + ADR-025 文档同步。T3.1-T3.6 全部完成, 385 passed + 1 skipped 零回归 (比 v3.0.0 T1 的 974 多 76 个 backtest 测试中的 76 个相关项, 累计 385 backtest + modules 测试)。

**核心产出**:
- 2 个新模块: `backtest/cusum_drift_monitor.py` (CUSUM 算法) + `backtest/multiple_testing.py` (BH-FDR 共享模块)
- 1 项新 ADR: ADR-025 (CUSUM 在线漂移检测, 含 T3.1-T3.6 全部校准结果 + 集成决策)
- 全量回归: 385 passed + 1 skipped (零回归, 含 CUSUM 22 + ARL 11 + multiple_testing 22 + unified_drift_bh_fdr 5 + pipelines_v2_cusum 16 + 全部 backtest 既有测试)
- 手工校验: T3.3 ARL Monte Carlo (k=0.5, h=5.0 默认参数经校准验证合理) + T3.5 BH 黄金参考 [0.005, 0.01, 0.02, 0.04, 0.5] → p_adj=[0.025, 0.025, 0.0333, 0.05, 0.5] 与文献一致

### T3.1-T3.6 六阶段 TDD 实施详情

| 阶段 | 任务 | 测试数 | 状态 | 关键变更 |
|------|------|--------|------|---------|
| **T3.1** | CUSUM 测试 (Red) | 22 | ✅ | 5 类测试: 基础功能(5) + 检测能力(6) + 在线更新(4) + CUSUM vs EWMA 对比(1) + 边界条件(6) |
| **T3.2** | CUSUM 实现 (Green→Review) | — | ✅ | `CUSUMDriftMonitor` Page 1954 双侧递推: S_pos[t]=max(0, S_pos[t-1]+x-μ₀-kσ), S_neg[t]=min(0, S_neg[t-1]+x-μ₀+kσ); 触发后自动重置 S=0; NaN 跳过; 参数校验 (std≤0/k<0/h<0 抛 ValueError) |
| **T3.3** | ARL Monte Carlo 校准 | 11 | ✅ | 6 类测试: In-control ARL(3) + Out-of-control ARL(4) + k 选择(1) + 联合约束(1) + Siegmund 对比(1) + 方向对称性(1)。ARL₀(h=5σ)≈507 (MC, T=3000 截断) vs 285 (Siegmund) vs 930 (文献); ARL₁(1σ) 5-30 容差内; ARL₁(3σ) 1-8 容差内; k=0.5 最优性 + 方向对称性 + ARL 单调性验证 |
| **T3.4** | 管线集成 (事后诊断) | 16 | ✅ | 5 类测试: 配置开关(4) + 监测器初始化(3) + 事后诊断(5) + drift_alerts(2) + 向后兼容(2)。`PipelineV2Config` 新增 `enable_cusum_drift_monitor` (默认 False) + `cusum_k=0.5` + `cusum_h=5.5` (补偿两个 CUSUM 叠加); `monitor_cusum_drift(factor_data)` 方法监测横截面均值/标准差, 不侵入 fit/transform 循环 |
| **T3.5** | BH-FDR 共享模块 | 22+5 | ✅ | 5 类测试: BH 正确性(11) + Bonferroni(3) + 无校正(2) + 对比(2) + 边界(4); `apply_bh_fdr`/`apply_bonferroni`/`apply_no_correction`/`apply_correction` 统一入口; `_HAS_MULTIPLE_TESTING` flag + 内联 fallback 向后兼容; `unified_drift._compute_rolling_structure_drift` 修复 ~504 次 KS 检验假阳性 (默认 BH-FDR); `factor_significance._apply_correction` 与 `pipelines_v2._check_ks_migration` 重构为调用共享模块 |
| **T3.6** | ADR-025 文档更新 | 0 | ✅ | DECISIONS.md ADR-025 状态从"T3.1-T3.2 已实施"更新为"T3.1-T3.6 全部完成", 附 ARL 校准结果表 + 管线集成决策 + BH-FDR 共享模块决策 + 全量回归记录 |

### 关键设计决策

1. **CUSUM 定位为事后诊断工具**: 不侵入 `fit/transform` 循环, 不改变管线输出, 仅提供附加漂移告警。`monitor_cusum_drift(factor_data)` 作为独立方法, 与 §3 前置处理诚实性框架一致 (第十六轮审查 G1 修正)
2. **监测横截面统计量非 IC**: CUSUM 监测横截面均值/标准差, 与 `unified_drift` 的 IC 序列监测正交, 不重复 (第十六轮审查 G2 修正)
3. **序贯检验无需 BH-FDR**: 两个 CUSUM (mean+std) 独立监测不同统计量, 是序贯检验非多重检验问题, 无需 BH-FDR 校正 (第十六轮审查 G3 修正, 撤销第十五轮 F5 部分论断)
4. **h=5.5 补偿两个 CUSUM 叠加**: 默认 h=5.5 (而非 ARL 校准的 h=5.0), 因两个 CUSUM 任一触发即告警, ARL₀_eff ≈ ARL₀/2 ≈ 250, 与文献 930 同数量级 (第十六轮审查 G4 修正)
5. **默认 `enable_cusum_drift_monitor=False`**: 向后兼容, 显式 opt-in (第十六轮审查 G5 修正)
6. **BH-FDR 共享模块低级函数 + 统一入口**: `apply_bh_fdr`/`apply_bonferroni`/`apply_no_correction` 三个低级函数 + `apply_correction(method=...)` 统一入口, 供 `unified_drift` / `pipelines_v2` / `factor_significance` 三处共享
7. **`_HAS_MULTIPLE_TESTING` flag + 内联 fallback**: 共享模块导入失败时 fallback 到内联实现, 保证零回归
8. **Holm 路径保留内联**: `multiple_testing.py` 暂未实现 Holm, `factor_significance._apply_correction` 的 Holm 路径保留内联实现
9. **`unified_drift` 默认 BH-FDR**: `_compute_rolling_structure_drift` 默认 `rolling_correction_method='benjamini_hochberg'`, `correction_method='none'` 保留旧路径向后兼容
10. **baseline_mean/std 从 fit 阶段估**: 从 `_intermediate_data` 最终输出的横截面均值/标准差的时间序列均值估, 非 fingerprint (第十六轮审查 G6 修正)

### 行为变化警示 (BREAKING-ISH)

**默认行为不变** (`enable_cusum_drift_monitor=False`, `rolling_correction_method='benjamini_hochberg'` 是新默认但有 `'none'` 向后兼容路径)。仅当显式开启时行为变化:

- `enable_cusum_drift_monitor=True`: 启用 CUSUM 事后诊断, `monitor_cusum_drift()` 填充 `drift_alerts` 字典
- `unified_drift._compute_rolling_structure_drift` 默认从 `none` 改为 `benjamini_hochberg`: 无漂移数据 score 从 ~5 (假阳性) 降为 0; 真实漂移检测力提升 (BH ≤ none 显著数)。若需复现旧行为, 显式传 `rolling_correction_method='none'`

### 学术依据

- Page, E. S. (1954). Continuous inspection schemes. *Biometrika*, 41(1/2), 100-115. — CUSUM 双侧递推
- Siegmund, D. (1985). *Sequential Analysis*. Springer. — ARL 近似公式 (T3.3 Monte Carlo 校准对比依据)
- Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery rate: a practical and powerful approach to multiple testing. *JRSS Series B*, 57(1), 289-300. — BH-FDR 校正
- Dunn, O. J. (1961). Multiple comparisons among means. *JASA*, 56(293), 52-64. — Bonferroni 校正 (保留向后兼容)

---

## v3.0.0 T1 — 指纹维度扩展至 21 维 (已实施, 2026-07-04)

### 概览

将 `FactorFingerprint` 从 13 维扩展至 21 维, 新增 8 维 (尾部依赖 4 + 体制转换 3 + 综合衍生 1), 并将孤儿函数 `_get_multi_dim_pipeline_weights` 接入 `transform()` 生产路径 (含 `enable_multi_dim_routing` 配置开关, 默认 False 向后兼容)。E1-E3 三阶段 TDD 全部完成, 974 passed + 6 skipped + 11 subtests passed (零回归, 比 v3.0.0 T4 的 934 多 40 个新测试)。

**核心产出**:
- [docs/ANALYSIS_V3.0.0.md](docs/ANALYSIS_V3.0.0.md) §1 — T1 深度核查 (13 维现状 / 4 项关键事实 / T1.1-T1.4 方案)
- [docs/EXECUTION_V3.0.0_T1.md](docs/EXECUTION_V3.0.0_T1.md) v1.1 — T1 执行方案 (E1-E3 三阶段, v1.1 含 1 CRITICAL + 3 MAJOR + 4 MINOR + 4 NIT 修订)
- 1 项新 ADR: ADR-024 (指纹维度扩展至 21 维)
- 全量回归: 974 passed + 6 skipped + 11 subtests passed (零回归, 比 v3.0.0 T4 的 934 多 40 个新测试)
- 手工校验: verify_v3_0_0_t1_manual.py 8/8 通过 (E3 新增)

### E1-E3 三阶段 TDD 实施详情

| 阶段 | 任务 | 测试数 | 状态 | 关键变更 |
|------|------|--------|------|---------|
| **E1** | 指纹核心扩展 (Red→Green→Review) | 32 | ✅ | `FactorFingerprint` NamedTuple 13→21 维 (8 新字段默认 NaN), `FingerprintConfig` 8→14 字段, `to_dict` 13→21 键, `extract_fingerprint` 追加阶段 4-5-6, 8 新私有计算方法 (`_compute_tail_dependence_lower/upper`, `_estimate_gpd_shape` POT-MLE, `_hill_estimator`, `_compute_regime_transition_prob/persistence/ic_diff`, `_derive_tail_regime_score` M2 双分量加权), ADR-014 技术债清理 (statsmodels 顶部导入) |
| **E2** | 路由层接入 + 测试更新 | 8 | ✅ | `PipelineV2Config` 新增 `enable_multi_dim_routing` (默认 False), `_get_multi_dim_pipeline_weights` 追加 Step 4 T1 修正 (tail_severity 阈值 0.3 → mixed +0.10; regime_instability 阈值 0.1 → dynamic +0.10), `transform()` 接入开关, `_make_fp` 重构为 **kwargs 模式支持 21 维, 新增 TestTailRegimeAdjustment (4) + TestMultiDimRoutingConfig (4) |
| **E3** | 文档同步 + 全量回归 | 0 | ✅ | ADR-024 写入 DECISIONS.md, CHANGELOG/CODE_WIKI/README/README.en 同步, ANALYSIS_V3.0.0.md T1 状态改已实施, verify_v3_0_0_t1_manual.py 8/8 手工校验, 全量回归 974 passed + 6 skipped + 11 subtests |

### 8 维新维度 (T1.1 + T1.2 + T1.3)

| 子任务 | 维度数 | 字段 | 学术依据 | 默认开关 |
|--------|--------|------|---------|---------|
| **T1.1 尾部依赖** | 4 | `tail_dependence_lower` / `tail_dependence_upper` / `gpd_shape` / `hill_estimator` | Nelsen (2006) Copula; Pickands (1975, 实际用 POT-MLE `scipy.stats.genpareto.fit` 替代); Hill (1975) | `enable_tail_dependence=False` |
| **T1.2 体制转换** | 3 | `regime_transition_prob` / `regime_persistence` / `regime_ic_diff` | Hamilton (1989) Markov 两状态, 不收敛降级为硬阈值 | `enable_regime_switching=False` (m1 修订) |
| **T1.3 综合衍生** | 1 | `tail_regime_score` | M2 双分量加权: `w * tail_severity + (1-w) * regime_instability` | 依赖 T1.1/T1.2 任一开启 |

### 关键设计决策

1. **默认关闭尾部依赖与体制转换**: `enable_tail_dependence=False` (Copula O(N²) 成本), `enable_regime_switching=False` (m1 修订, 避免小样本日志噪音), 显式 opt-in
2. **POT-MLE 替代 Pickands 估计量**: `_estimate_gpd_shape` 用 `scipy.stats.genpareto.fit` (POT-MLE), 比 Pickands 原始估计量对轻尾分布更稳健 (E1 Green 阶段修正, Pickands 对正态分布返回 2.356 不稳定)
3. **regime_ic_diff 方案 C**: 一阶差分均值差 (bull Δfactor 均值 - bear Δfactor 均值), 不破坏 `extract_fingerprint` 签名 (无前向收益数据输入)
4. **路由接入加 `enable_multi_dim_routing` 开关**: 默认 False (向后兼容), True 时 `transform` 使用 `_get_multi_dim_pipeline_weights` (含 T1 tail/regime 修正)
5. **不扩展 `AdaptiveFactorClassifier.classify`**: 仍仅用 `ar1_median`, 新维度仅作用于 `_get_multi_dim_pipeline_weights` 修正层
6. **`_derive_tail_regime_score` M2 双分量加权**: 简化公式避免嵌套权重可读性差
7. **statsmodels 顶部导入**: ADR-014 技术债清理, 移除 `_test_volatility_clustering` 的 try/except ImportError
8. **`_make_fp` 测试辅助重构为 `**kwargs` 模式**: 支持 21 维字段覆盖, 既有 12 测试向后兼容

### 行为变化警示 (BREAKING-ISH)

**默认行为不变** (所有新维度默认关闭, NamedTuple 8 新字段默认 NaN, `enable_multi_dim_routing` 默认 False)。仅当显式开启 `enable_tail_dependence=True` / `enable_regime_switching=True` / `enable_multi_dim_routing=True` 时, 行为才变化:

- `extract_fingerprint` 返回的 NamedTuple 从 13 维扩展至 21 维 (8 新字段默认 NaN, 既有 13 维不变)
- `to_dict` 返回 21 键 (既有 13 键不变)
- `transform()` 在 `enable_multi_dim_routing=True` 时使用多维路由 (含 T1 tail/regime 修正), 否则走旧路径

### 学术依据

- Nelsen, R. B. (2006). *An Introduction to Copulas* (2nd ed.). Springer. — 尾部依赖 Copula 经验条件概率
- Pickands, J. (1975). Statistical inference using extreme order statistics. *Annals of Statistics*, 3(1), 119-131. — GPD 极值理论 (实际用 POT-MLE 替代原始估计量)
- Hill, B. M. (1975). A simple general approach to inference about the tail of a distribution. *The Annals of Statistics*, 3(5), 1163-1174. — Hill 重尾指数
- Hamilton, J. D. (1989). A new approach to the economic analysis of nonstationary time series and the business cycle. *Econometrica*, 57(2), 357-384. — Markov 体制转换

---

## v3.0.0 T4 — KS 迁移检测 BH-FDR 替代 Bonferroni (已实施, 2026-07-04)

### 概览

将 `_ks_migration_significance` 的多重比较校正从保守的 Bonferroni 迁移到 Benjamini-Hochberg FDR, 与 `factor_significance.py` 的 BH 默认一致 (E7 已用 BH)。核心改动仅 1 个函数 (~20 行核心代码), 但提升因子迁移检测的检测力, 减少 Type II 误差 (漏检真实迁移)。

**核心产出**:
- [docs/ANALYSIS_V3.0.0.md](docs/ANALYSIS_V3.0.0.md) v1.1 — v3.0.0 4 项远期任务深度核查 (T1-T4)
- [docs/EXECUTION_V3.0.0_T4.md](docs/EXECUTION_V3.0.0_T4.md) v1.1 — T4 执行方案 (E1-E3 三阶段)
- 1 项新 ADR: ADR-002a (supersede ADR-002 校正方法, ADR-002 历史保留)
- 全量回归: 934 passed + 6 skipped + 11 subtests passed (零回归, 比 v2.6.0 的 918 多 16 个新测试)
- 手工校验: verify_fix1_manual.py 6/6 通过 (E2 修订), verify_v3_0_0_t4_manual.py 通过 (E3 新增)

### E1-E3 三阶段 TDD 实施详情

| 阶段 | 任务 | 测试数 | 状态 | 关键变更 |
|------|------|--------|------|---------|
| **E1** | BH 核心实现 (Red→Green→Review) | 13 | ✅ | `_ks_migration_significance` 新增 `correction_method` 参数 (默认 'benjamini_hochberg'), 三路径分流 (BH/Bonferroni/none), 字段隔离 (BH: min_p_value_adjusted/correction_method; Bonferroni: alpha_corrected/bonferroni_correction), ADR-002a 写入 DECISIONS.md |
| **E2** | 测试更新 | 3 | ✅ | verify_fix1_manual.py 校验 3 改为 BH 公式校验, test_factor_significance_manual.py 新增 TestKSMigrationBHCorrection 类 (3 测试: BH 黄金参考/BH 宽松性/Bonferroni 向后兼容) |
| **E3** | 文档同步 + 全量回归 | 0 | ✅ | CHANGELOG/CODE_WIKI/README 同步, verify_v3_0_0_t4_manual.py 手工校验, 全量回归 934 passed + 6 skipped + 11 subtests |

### 关键设计决策

1. **默认改 BH, 保留 Bonferroni 向后兼容**: `correction_method='bonferroni'` 显式 opt-in 旧路径, 字段全部保留
2. **三路径字段隔离**: BH 路径不污染 Bonferroni 字段, 反之亦然, 避免 details 字典字段混淆
3. **None 路径供研究/调试**: `correction_method='none'` 无校正, 直接 `min_p < alpha`
4. **黄金参考**: p=[0.01, 0.04, 0.03, 0.20, 0.50], K=5 → p_adj=[0.05, 0.0667, 0.0667, 0.25, 0.50], min_p_value_adjusted=0.05
5. **行为变化**: BH 比 Bonferroni 宽松, 之前不显著的迁移现在可能变显著 (`is_sig` 可能 False→True), 这是 T4 核心目的

### 行为变化警示 (BREAKING-ISH)

**默认 `correction_method` 从 Bonferroni 改为 BH**, `is_sig` 可能从 False 变为 True (BH 检测力更高)。若应用场景要求严格控制 FWER (至少一个假阳性概率), 应显式传 `correction_method='bonferroni'`。

### 学术依据

- Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery rate: a practical and powerful approach to multiple testing. *Journal of the Royal Statistical Society: Series B*, 57(1), 289-300.
- Dunn, O. J. (1961). Multiple comparisons among means. *JASA*, 56(293), 52-64. (Bonferroni 校正, 保留向后兼容)

---

## v2.6.0 — 优化器与漂移检测增强 (已实施, 2026-07-03/04)

### 概览

基于 v2.5.0 三层架构 (Layer 1 / Layer 2 正交化 / Layer 3 显著性) 完成, 推进 ADR-004 (目标函数) / ADR-005 (搜索空间) / ADR-006 (扩展窗口 CV) 三项设计契约在优化器层面的完整闭环. **E1-E9 9 阶段 TDD 全部完成**, 918 passed + 6 skipped + 11 subtests passed (零回归, 比 v2.5.0 的 860 多 58 个新测试).

**核心产出**:
- [docs/ANALYSIS_V2.6.0.md](docs/ANALYSIS_V2.6.0.md) v1.1 (810 行) — 深度核查 8 类问题 / 8 项任务 / 11 项风险 / 9 篇文献核查
- [docs/EXECUTION_V2.6.0.md](docs/EXECUTION_V2.6.0.md) (1595 行) — 9 个执行阶段 (E1-E9), ~59 新测试 + 860 基线 = ~919 passed
- 3 项新 ADR: ADR-021 (health_penalty 代理) / ADR-022 (正交化搜索) / ADR-023 (ThresholdDriftMonitor)
- 全量回归: 918 passed + 6 skipped + 11 subtests passed (1171.44s, 19:31)
- 手工校验: verify_v2_6_0_manual.py 8/8 通过 (E1-E8 汇总)

### E1-E9 9 阶段 TDD 实施详情

| 阶段 | 任务 | 测试数 | 状态 | 关键变更 |
|------|------|--------|------|---------|
| **E1** | P3-11' 文档状态修正 | 0 | ✅ | DECISIONS.md P3-11 `[ ]` → `[x]`, 学术依据分拆 (TPE→Bergstra 2011, fANOVA→Hutter 2014) |
| **E2** | P3-10' migration_threshold 字段位置 + ADR-005 | 5 | ✅ | optimizer.py:150-158 字段位置错误 (config.monitor → config), ADR-005 末尾追加修订日志 |
| **E3** | P3-1' IC 时间加权 EWMA | 8 | ✅ | factor_metrics.py compute_ic_series 添加 weighting/halflife 参数, optimizer._compute_ic 集成 EWMA, 学术依据改引 Ferson-Siegel (2001) |
| **E4** | P3-9' 目标函数对齐 ADR-004 (ADR-021) | 10 | ✅ | _composite_objective 添加 health_penalty (代理指标方案 B), 修正 fidelity 符号方向 (+ → -), 新增 _health_penalty_proxy (decay_ratio/hit_rate/ic_vol 三档), 全量回归 883 passed |
| **E5** | P3-13 正交化参数纳入搜索空间 (ADR-022) | 8 | ✅ | DEFAULT_SEARCH_SPACE_ORTH 添加 orth_method/align_mode/ridge_lambda (不搜索 orth_enabled), optimize() 添加 categorical + log-uniform 采样, 全量回归 885 passed |
| **E6** | P3-14 几何诊断纳入目标函数 | 12 | ✅ | OrthogonalizerAdapter.fit() 保存 _F_stacked_/_T_stacked_, get_diagnostics() 新方法, _redundancy_penalty 基于 compute_vrr (λ=0.05, v1.1 从 0.1 降), _composite_objective 6 项对齐 ADR-004, look-ahead bias 防护, 全量回归 903 passed |
| **E7** | P3-15 Layer 3 显著性最终验证 | 6 | ✅ | _validate_significance 调用 FactorSignificanceTest (Belloni 2014 PDS Lasso+HC3+BH), optimize() 添加 validate_significance 参数 (默认 False 向后兼容), 对齐+dropna 处理 NaN, 异常防护 |
| **E8** | P3-12' 阈值漂移监测 (ADR-023) | 10 | ✅ | backtest/threshold_drift_monitor.py 新建, ThresholdDriftMonitor (EWMA 衰减检测, decay > 20% 触发 needs_research), update/get_history/reset 三方法, min_observations=5 保护 |
| **E9** | 文档验证 + 全量回归 | 0 | ✅ | verify_v2_6_0_manual.py 8/8 手工校验通过, 全量回归 918 passed + 6 skipped + 11 subtests passed, 文档全部更新 (README/CHANGELOG/CODE_WIKI/DECISIONS) |

### 关键设计决策

1. **lambda_redundancy=0.05** (v1.1 从 0.1 降): 避免与 IC 主目标双重惩罚
2. **_validate_significance 对齐+dropna**: LassoCV 不接受 NaN, 需在调用前处理
3. **空 factor_data 异常防护**: _validate_significance 返回错误报告而非抛异常
4. **ThresholdDriftMonitor EWMA**: `alpha = 1 - exp(-ln2/halflife)`, decay_ratio = ewma/best_score
5. **validate_significance 默认 False**: 向后兼容, 仅最终验证 (计算成本约束)
6. **正交化作为 post_transform_hook**: 随 pipeline.fit(train_factor) 在 train 上估计 W, 防止 look-ahead bias

### 分析阶段 (ANALYSIS_V2.6.0.md v1.0 → v1.1)

**v1.0 → v1.1 深度核查发现 4 项错误**:
1. **Cohen-Coval-Pastor (2005) 误推荐**: v1.0 推荐 "Judging Fund Managers by the Company They Keep" 作为 P3-1 IC 时间加权学术依据, 实际该论文讨论基金持仓相似度, 与 EWMA 无关. v1.1 撤回, 改引 Ferson-Siegel (2001).
2. **migration_threshold "字段缺失" 误判**: v1.0 报告 MonitorConfig 缺 migration_threshold 字段, 实际 `PipelineV2ConfigUnified.migration_threshold` 字段已存在 (config_v2.py:407-410, 默认 0.10). v1.1 修正为"字段位置错误" — optimizer.py:155-158 错误设置到 `config.monitor` 上.
3. **FactorSignificanceTest 未集成遗漏**: v1.0 未发现 `backtest/factor_significance.py` 已完整实现 (Belloni 2014 PDS + HC3 + BH) 但 optimizer.py 未调用. v1.1 新增 P3-15 任务.
4. **health_penalty 时序问题未识别**: v1.0 未识别 `HealthMonitorAdapter.build_report_from_engine` 的 engine_results 时序依赖 (只能在回测后计算, 不能在 CV fold 内部直接调用). v1.1 新增时序问题描述 + 3 种实现方案, 推荐代理指标方案 (B).

**8 类问题汇总**:
| 类别 | 问题 | 解决阶段 |
|------|------|---------|
| 文档状态 | P3-11 已实施但 DECISIONS 标 `[ ]` | E1 |
| 字段位置 | migration_threshold 设置到 config.monitor 而非 config | E2 |
| 目标函数 | 缺 health_penalty + fidelity 符号相反 | E4 |
| 搜索空间 | 未纳入 v2.5.0 正交化参数 | E5 |
| 几何诊断 | 未将 VRR 纳入目标函数 | E6 |
| 显著性 | FactorSignificanceTest 已实现未集成 | E7 |
| 漂移监测 | 阈值组合有效性漂移无监测 | E8 |
| 学术依据 | P3-1 误引 Dimson/Moreira-Muir, P3-12 误引 Hsu 2010 | E3/E8 |

### 执行方案 (EXECUTION_V2.6.0.md, 9 阶段)

| 阶段 | 任务 | 优先级 | 依赖 | 测试数 | 关键变更 |
|------|------|--------|------|--------|---------|
| **E1** | P3-11' 文档状态修正 | P0 | 无 | 0 (仅文档) | DECISIONS.md |
| **E2** | P3-10' migration_threshold 字段位置 + ADR-005 | P0 | 无 | ~5 | optimizer.py:150-158, DECISIONS.md |
| **E3** | P3-1' IC 时间加权 EWMA | P1 | 无 | ~8 | factor_metrics.py, optimizer.py |
| **E4** | P3-9' 目标函数对齐 ADR-004 (health_penalty 代理) | P1 | E3 | ~10 | optimizer.py (_composite_objective) |
| **E5** | P3-13 正交化参数纳入搜索空间 | P1 | E2 | ~8 | optimizer.py (DEFAULT_SEARCH_SPACE_ORTH) |
| **E6** | P3-14 几何诊断 (compute_vrr) + Adapter 扩展 | P2 | E5 | ~12 | adapters.py, optimizer.py |
| **E7** | P3-15 Layer 3 显著性最终验证 | P2 | E4 | ~6 | optimizer.py (_validate_significance) |
| **E8** | P3-12' 阈值漂移监测 (ThresholdDriftMonitor) | P2 | E4 | ~10 | backtest/threshold_drift_monitor.py (新建) |
| **E9** | 文档验证 + 全量回归 | P1 | E1-E8 | 8 项手工校验 | README/CHANGELOG/CODE_WIKI/DECISIONS |

**推荐执行顺序**: E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9 (E1/E2/E3 可并行)

### 关键设计决策

1. **health_penalty 代理指标方案 (ADR-021)**: 用 IC decay/hit_rate/ic_vol 三档近似 health_score, 解决 HealthMonitorAdapter 仅能在回测后计算的时序依赖
2. **正交化搜索默认关闭 (ADR-022)**: `search_orth=False` 保持基线行为, 启用后搜索 orth_method/align_mode/ridge_lambda 三维度, 不搜索 orth_enabled
3. **FactorSignificanceTest 仅最终验证 (E7)**: 计算成本控制, 不参与每 trial 评估
4. **fidelity 符号修正 (E4)**: ADR-004 设计为惩罚 (`- ks_penalty`), 代码当前是奖励 (`+ lambda_fidelity * fidelity`), 需修正符号方向
5. **ThresholdDriftMonitor (ADR-023)**: EWMA 衰减检测, halflife=63, decay > 20% 触发 `needs_research=True`
6. **look-ahead bias 防护 (E5)**: 正交化参数搜索时必须在 CV fold 内部 fit (用 train 数据)

### 学术依据修正

| 任务 | v1.0 误引 | v1.1 修正 | 原因 |
|------|----------|----------|------|
| P3-1 IC 时间加权 | Cohen-Coval-Pastor (2005) | Ferson-Siegel (2001) | Cohen-Coval 讨论基金持仓相似度, 与 EWMA 无关 |
| P3-1 IC 时间加权 | Dimson/Moreira-Muir | Barroso-Santa-Clara (2015) | Dimson 是 beta 估计, Moreira-Muir 是 risk premium |
| P3-12 阈值漂移 | Hsu (2010) 误称 Bayesian | Sullivan-TW (1999) + McLean-Pontiff (2016) | Hsu (2010) 实际是 frequentist SDF |
| P3-11 参数重要性 | — | Bergstra (2011) TPE + Hutter (2014) fANOVA | 拆分原引用 |

### 风险与回退

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| health_penalty 代理与 health_score 相关性不足 | 中 | 目标函数引导偏差 | E4 手工校验 + A/B 测试 |
| 正交化搜索维度增加致 n_trials 不足 | 中 | 优化不收敛 | n_trials 从 100 提到 150-200 |
| FactorSignificanceTest 计算成本超预期 | 低 | E7 集成测试超时 | 仅最终验证, 不每 trial 评估 |
| fidelity 符号修正改变历史 best_score | 中 | 与 v2.5.0 best_score 不可比 | 文档标注 + 重新运行优化 |

**8 阶段独立回退方案**: 各阶段文件变更隔离, 失败可独立回退 (详见 EXECUTION_V2.6.0.md:1555-1566)

---

## v2.5.0 — 多因子正交化三层架构 (2026-07-03)

### 概览

实施 ADR-020: 多因子横截面正交化模块, 采用**三层架构分离** (Layer 1 per-factor / Layer 2 cross-factor 正交化 / Layer 3 target-aware 检验)。6 阶段 (O1-O6) 全部完成, 严格 TDD (Red → Green → 手工校验 → 回归测试), 每阶段严格 review。全量回归 860 passed + 5 skipped, 零回归 (比 v2.4.0 的 632 多 228 个测试)。

### O1: 算法核心 (阶段 1)

- **新增**: `modules/factor_orthogonalizer/core/` 5 种正交化器
  - `SymmetricOrthogonalizer` (Löwdin 1950): 默认主方法, `W = (F^T F)^(-1/2)`, VRR=1, 无顺序依赖
  - `RidgeOrthogonalizer`: 病态矩阵兜底, λ 自适应 (Ledoit-Wolf 2004)
  - `PCAOrthogonalizer`: 降维场景, center 参数兼容 Layer 1 标准化
  - `GramSchmidtOrthogonalizer`: 顺序依赖场景, κ>100 启用 Kahan (1966) 二次投影
  - `CholeskyOrthogonalizer`: 半正定保证场景
- **接口**: `BaseOrthogonalizer.fit_from_gram(G)` — 仅 Symmetric/Ridge/PCA 支持, 滚动场景避免重复构造 F
- **数值稳定**: dtype 强制 (int→float64, float32→float64), threshold_mode 三模式 (relative/absolute/auto), decomposition 选择 (eigh 默认 / svd κ>1e6 切换)
- **测试**: 44 单元测试 + 15 手工校验, 精度 < 1e-10

### O2: 适配器层 (阶段 2)

- **新增**: `OrthogonalizerAdapter` (在 `adapters.py`) + `CrossSectionalOrthogonalizer` (在 `modules/factor_orthogonalizer/cross_sectional.py`)
- **半侵入式接入**: `post_transform_hooks` 机制, `enabled=False` 时 `hooks=[]` 零开销, 不重构 Pipeline per-factor 架构
- **因子对齐**: `align_mode` 三模式 — `intersection` (默认, 取交集) / `union_nan` (取并集填 NaN) / `raise_on_mismatch` (严格抛错), 解决 Barra 41天 vs 日频 1212天不匹配
- **NaN 处理**: fit 时 dropna + 高比例 NaN 告警, transform 时 NaN 保留
- **W 缓存**: 全样本模式缓存 W, transform 时直接应用
- **测试**: 22 单元测试 + 12 手工校验, 全量回归 698 passed

### O3a: 几何诊断 (阶段 3a)

- **新增**: `modules/factor_orthogonalizer/diagnostics.py` — VRR/κ/VIF/正交性误差
- **VRR (方差保留比例)**: `VRR_k = Var(T_k)/Var(F_k)`, VRR << 1 表示因子 k 高度冗余; `ddof` 参数 (0=总体方差默认 / 1=样本方差滚动场景)
- **VIF 多方法**: `lstsq` (SVD, 默认) / `qr` (快 3-5x) / `pinv`, 三方法精度一致 < 1e-10, R²=1.0 时 inf 处理
- **条件数分级**: Belsley-Kuh-Welsch (1980) 四级 (good < 10, acceptable < 100, warning < 1000, severe ≥ 1000)
- **测试**: 18 单元测试 + 24 手工校验, 含 VRR 数学修正 (F 中心化 + 单位范数时 VRR=1)

### O3b: Layer 3 因子检验 (阶段 3b)

- **新增**: `backtest/factor_significance.py` — `FactorSignificanceTest`
- **双重 Lasso** (Belloni-Chernozhukov 2014 PDS): treatment 轮询模式, 每个因子独立当 treatment, 轮次顺序不影响结果
- **稳健标准误**: HC3 (默认) / HC1 / OLS, `cov_type` 参数选择
- **多重检验校正**: BH (Benjamini-Hochberg) FDR 控制 / Bonferroni 保守校正
- **Elastic Net**: α/λ 网格搜索, 处理多因子共线性
- **测试**: 17 单元测试 + 14 手工校验, 含 HC3 公式 bug 修复

### O4: 回测扩展 (阶段 4)

- **新增**: `modules/factor_orthogonalizer/rolling.py` — `RollingOrthogonalizer`
- **增量 Gram**: `window_` 滚动窗口 + `G_` 增量更新 (加入新 / 移除旧), 避免每期重复构造 F
- **reset_interval=500**: 每 500 期从 window_ 重新堆叠 G, 消除累积浮点误差 (~1e-13)
- **is_orthogonalized 标记**: `(T,)` bool 数组, 记录每期是否真正正交化 (区分"未正交化"vs"正交化后")
- **无 look-ahead bias**: 用 `[t-window, t-1]` 数据估计 W_t, 应用到 F_t
- **ICChangeMonitor**: 正交化前后 IC 变化监控
- **测试**: 11 单元测试 + 19 手工校验

### O5: 协同验证 (阶段 5)

- **新增**: `modules/factor_orthogonalizer/grouped.py` + `triple_chain.py`
- **GroupedOrthogonalizer**: 分组正交化 (按行业/板块等)
- **TripleChainCoordinator**: Factor_Fingerprint (描述) → Factor_Decoupler (时序解耦) → Orthogonalizer (横截面正交化) 三件套串联
- **数据流协议**: O5.6.1 明确三件套数据流, O5.6.2 中性化顺序, O5.6.3 缺失因子处理, O5.6.4 缓存, O5.6.5 冲突解决
- **测试**: 15 单元测试 + 17 手工校验

### O6: 文档验证 (阶段 6)

- **版本号统一**: 8 处同步为 2.5.0 (pyproject.toml / __init__.py / config_v2.py / reporting.py + 4 测试文件)
- **ADR-020 状态更新**: DECISIONS.md 中 "实施中" → "已实施"
- **project_memory.md**: 追加 21 项 ADR-020 约束清单 (8 基础 + 13 v1.1 工程深化) + 5 条 v2.5.0 经验
- **手工校验脚本**: `tests/manual/verify_v2_5_0_manual.py` 5/5 通过
  1. SymmetricOrthogonalizer 精度 < 1e-10 (与独立 numpy eigh 对比)
  2. FactorSignificanceTest 精度 < 1e-6 (与独立 statsmodels OLS 对比)
  3. VRR = 1.0 (精度 1e-10)
  4. treatment 轮询顺序不变性 (正序 vs 反序)
  5. RollingOrthogonalizer 无 look-ahead bias (t=0 原值, t=100 已正交)
- **全量回归**: 860 passed + 5 skipped + 0 failed

### 技术债修复

- **问题**: `tests/manual/test_adapter_manual.py:test_disabled_adapter_no_import` 无 try/finally 保护 `del sys.modules[m]`, 导致后续 `test_import_from_core` 重新导入时类对象 id 改变, `assert S is SymmetricOrthogonalizer` 失败
- **诊断**: 比较 `id(class)` (collection 时绑定) 与 `id(sys.modules[module].class)` (运行时获取), 不相等即模块对象被替换
- **修复**: 添加 try/finally 恢复 sys.modules, 与 `tests/test_factor_orthogonalizer/test_adapter.py` 安全版本一致

### 测试汇总

| 阶段 | 单元测试 | 手工校验 | 累计全量回归 |
|------|---------|---------|------------|
| O1 算法核心 | 44 | 15 | 676 passed |
| O2 适配器 | 22 | 12 | 698 passed |
| O3a 几何诊断 | 18 | 24 | 716 passed |
| O3b Layer 3 | 17 | 14 | 733 passed |
| O4 回测扩展 | 11 | 19 | 744 passed |
| O5 协同验证 | 15 | 17 | 759 passed |
| O6 文档验证 | 0 | 5 | **860 passed + 5 skipped** |
| **合计** | **127** | **106** | — |

### 经验教训

- **sys.modules 删除后未恢复是 class identity (is 检查) 失败的隐蔽根因**: 测试中 `del sys.modules[k]` 删除模块后, 后续测试重新导入会创建新模块对象 (新 id), 但 collection 时模块顶部 `from ... import Class` 绑定的是旧模块对象的类, 导致 `assert S is SymmetricOrthogonalizer` 失败
- **tests/manual/ 目录会被 pytest 默认收集**: manual 测试必须与正式测试同等严格地清理 sys.modules
- **诊断模块对象替换的方法**: 比较 `id(class)` (collection 时绑定) 与 `id(sys.modules[module].class)` (运行时获取), 若不相等则模块对象已被替换
- **v2.5.0 三层架构分离避免了单层混层陷阱**: 双重 Lasso 属 Layer 3 (需 Y), 不与 Layer 2 无监督变换混层, 正交化作为独立后处理层不重构 Pipeline per-factor 架构

---

## v2.4.0 — 外部模块内化 (2026-07-03)

### 概览

将 5 个处理模块 (Factor_Fingerprint / Factor_Decoupler / Factor_AdaptiveWinsor / Factor_Imputer / Factor_Neutralizer) 从外部独立仓库内化到 `factor_pipeline/modules/` 子包,保留 Factor_DB 和 Factor_Trading 作为外部数据边界。5 阶段全量回归始终 632 passed 零回归。全部采用严格 TDD (Red → Green → 手工校验 → 回归测试),每阶段完成后严格 review。

### I1: Factor_Fingerprint + Factor_Decoupler 内化 (阶段 1)

- **问题**: 两个模块零新增依赖,但 import 路径分散,命名不规范 (Factor_Fingerprint vs factor_fingerprint)
- **修复**: 内化到 `modules/factor_fingerprint/` 和 `modules/factor_decoupler/`,统一小写蛇形命名,~45 处 import 替换
- **测试**: 全量回归 632 passed, 0 新增失败

### I2: Factor_AdaptiveWinsor 内化 (阶段 2)

- **问题**: 模块含 batch/parallel/pipeline/report 等未使用子包,全量内化引入冗余依赖
- **修复**: 最小子包化策略 — 只迁 core/ 子集 (3 个类),新增 scikit-learn REQUIRED 依赖
- **测试**: 全量回归 632 passed, 0 新增失败
- **手工校验**: 依赖上界冲突检测 (pyextremes 声明 pandas<3.0.0 会自动降级,需预检)

### I3: Factor_Imputer 内化 (阶段 3)

- **问题**: 目录名含 "." (Factor_Imputer_v2.0) 需 PyPI 规范化,函数内 try/except + sys.path hack 双重导入模式隐蔽
- **修复**: 移除 `_v2_0` 版本后缀,Grep 全文搜索发现 22 处导入 (调研预估仅 4 处),清理 try/except + sys.path hack 为单一相对导入
- **测试**: test_p2_fixes.py 使用 Factor_Imputer 作为测试目标自动跳过 (正确行为,非回归)
- **回归**: 632 passed, 0 新增失败

### I4: Factor_Neutralizer 内化 (阶段 4)

- **问题**: src-layout 结构,重依赖 (matplotlib/joblib/psutil/numba),38 方法但主项目只需类可导入
- **修复**: src-layout → flat-layout,重依赖改 try/except 可选导入 + HAS_XXX 标记,添加 `from __future__ import annotations` 解决 plt.Figure 类型注解导入时求值问题
- **测试**: 旧包卸载后新路径导入验证通过,全量回归 632 passed
- **手工校验**: `from factor_pipeline.modules.factor_neutralizer.core import FactorNeutralizer` 导入正常

### I5: CI/文档清理 (阶段 5)

- **问题**: CI monorepo 模拟仍 clone 7 个外部模块,历史批量修复脚本失效,版本号不统一
- **修复**:
  - CI monorepo 模拟从 7 个外部模块缩减为 2 个 (Factor_DB/Factor_Trading)
  - 删除 7 个失效批量修复脚本 (fix_external_imports / fix_factoradaptivewinsor_internal_imports / 等)
  - 版本号统一 11 处 (pyproject.toml + __init__.py + config_v2.py + reporting.py + 4 个测试文件 + 2 个校验脚本)
- **测试**: verify_fix3_manual.py "旧版本残留"检查发现内化模块自身 __version__ (正确行为,非问题)
- **回归**: 632 passed, 5 skipped, 0 failed

### 测试汇总

| 阶段 | 模块 | 回归测试 | 手工校验 |
|------|------|----------|----------|
| I1 | Fingerprint + Decoupler | 632 passed | — |
| I2 | AdaptiveWinsor | 632 passed | 依赖上界检测 |
| I3 | Imputer | 632 passed | 导入路径验证 |
| I4 | Neutralizer | 632 passed | 导入验证 + 路径检查 |
| I5 | CI/文档清理 | 632 passed, 5 skipped | 版本号 11 处统一 |
| **总计** | 5 模块内化 | **632 passed 零回归** | — |

### 经验教训

1. **模块独立性对独立分发才有价值**: 单仓库场景下独立性是虚假收益,内化优于子包化 (ADR-019)
2. **命名一致性是长期维护成本的关键驱动因素**: 目录名/Python 包名/PyPI 名三套命名并存时,每个新开发者/CI 配置都要付出认知成本
3. **依赖上界冲突是隐蔽陷阱**: pyextremes 声明 `pandas>=1.0.0,<3.0.0`,pip install 会自动降级 pandas 3.0.3→2.3.3 而非报错,悄悄破坏 backtest 模块
4. **函数内导入比模块级导入更难发现**: 调研发现 4 处模块级绝对导入,实际 Grep 发现 22 处 (含 16 处函数内 try/except + sys.path hack 双重导入)
5. **plt.Figure 类型注解在导入时求值是隐蔽陷阱**: 无 `from __future__ import annotations` 时,`plt=None` 会导致类型注解在类定义阶段 AttributeError

---

## v2.3.0 — 跨版本 CI 矩阵 (2026-07-02)

### 概览

建立双轨 CI (GitHub Actions 远程 + tox 本地),覆盖 Python 3.10/3.11/3.12 × ubuntu-latest 矩阵,保障跨版本兼容性。CI 配置文件脚本校验 37/37 通过。

### P4.1: CI 现状调研

- **问题**: 无 .github/workflows,无 tox.ini,pyproject 声明 >=3.9 (3.9 EOL 临近)
- **调研**: 确认主项目依赖 (numpy/pandas/scipy/statsmodels/sklearn) 全部支持 3.10-3.12

### P4.2: CI 矩阵策略设计

- **决策**: GitHub Actions + tox 双轨,Python 3.10/3.11/3.12 × ubuntu-latest
- **Windows 排除**: spawn 方法进程启动开销使小数据量并行性能测试不可靠 (ADR-016)
- **fail-fast: false**: 一个 Python 版本失败不阻塞其他版本继续跑

### P4.3a: GitHub Actions workflow

- **文件**: `.github/workflows/ci.yml`
- **设计**: 矩阵 + 外部模块 git clone + 目录重命名 (匹配 pyproject.toml package-dir 映射)
- **校验**: YAML 语法 + 矩阵维度 + 步骤顺序脚本校验

### P4.3b: tox.ini 双轨本地 CI

- **文件**: `tox.ini`
- **设计**: py310/py311/py312 + lint + coverage 环境
- **deps 字段**: 声明 editable 安装路径 (-e {toxinidir}/../Factor_DB),每 env 独立安装外部模块保证隔离性
- **changedir**: 设为 {toxinidir}/.. 从父目录运行 pytest,避免 types.py 遮蔽 stdlib

### P4.4: 本地验证 CI 配置正确性

- **脚本校验**: 37/37 校验通过 (YAML 语法 + INI 语法 + 矩阵维度 + 步骤顺序)
- **回归测试**: 21/21 通过
- **关键校验**: CI 配置文件必须用脚本校验语法正确性,不能假设配置生效

### 测试汇总

| 校验项 | 数量 | 状态 |
|--------|------|------|
| YAML 语法校验 | 12/12 | ✅ |
| INI 语法校验 | 8/8 | ✅ |
| 矩阵维度校验 | 5/5 | ✅ |
| 步骤顺序校验 | 7/7 | ✅ |
| 回归测试 | 21/21 | ✅ |
| **总计** | **37/37 + 21/21** | ✅ |

### 经验教训

1. **双轨 CI 优于单轨**: 远程 (GitHub Actions) 保障推送质量,本地 (tox) 快速验证跨版本兼容性
2. **CI 配置文件必须脚本校验**: 不能假设配置生效,P4.4 37/37 校验通过证明
3. **tox changedir 解决 types.py 遮蔽**: 从父目录运行 pytest 避免 cwd 内 types.py 遮蔽 stdlib types 模块
4. **Windows spawn 方法开销**: 小数据量并行性能测试在 Windows 不可靠,应 skipif 而非改阈值

---

## v2.2.2 — 代码质量修复 7 项 (2026-07-02)

### 概览

针对 Code Wiki 评审发现的 7 项代码质量问题,按推荐顺序逐一修复。全部采用严格 TDD (Red → Green → 手工校验 → 回归测试),每步完成后严格 review。

### Fix 1: self.factors dead-code bug + KS 拆分语义修复 (P0)

- **问题**: `pipelines_v2.py` 中 `self.factors` 在 `fit()` 后未保留,`transform()` 访问时 AttributeError; KS 检验拆分为两步后语义不一致
- **修复**: 在 `fit()` 中保留 `self.factors = factors`,KS 拆分逻辑统一使用 `_ks_migration_significance()`
- **测试**: `tests/test_fix1_self_factors_bug.py` — 4/4 通过

### Fix 5: 硬编码路径改为环境变量配置项 (ADR-012)

- **问题**: `data_bridge.py` 和 `health_bridge.py` 硬编码 `F:/Coding/Factor_Trading_v3.0` 等路径,不可移植
- **修复**: 改用 `os.environ.get("FACTOR_TRADING_PATH", ...)` 等环境变量,默认值保持向后兼容
- **测试**: `tests/test_fix5_hardcoded_paths.py` — 6/6 通过

### Fix 2: 配置系统统一 — 方案 C 桥接层 (ADR-010)

- **问题**: `PipelineV2Config` (dataclass) 与 `PipelineV2ConfigUnified` (Pydantic) 双轨制,字段映射需手动同步
- **修复**: 添加 `to_pipeline_v2_config()` 和 `from_unified()` 桥接方法,4 共享字段直接复制 + 概念对应 + 嵌套→扁平映射
- **测试**: `tests/test_fix2_config_unification.py` — 13/13 通过; 手工校验 8/8

### Fix 3: 版本号统一

- **问题**: `__init__.py` (2.0.0)、`config_v2.py` (2.1.0)、`reporting.py` (2.0.0) 版本号不一致
- **修复**: 3 处源码 + 2 处测试统一到 "2.2.1"
- **测试**: `tests/test_fix3_version_unification.py` — 5/5 通过

### Fix 4: backtest/__init__.py 补全导出

- **问题**: `backtest/__init__.py` 为空文件,用户需写长导入路径
- **修复**: 补全 26 个公开 API 导出 (因子指标、缓存、数据适配、引擎、健康度、运行器)
- **测试**: `tests/test_fix4_backtest_init.py` — 5/5 通过

### Fix 7: core 命名空间碰撞修复 (ADR-011)

- **问题**: `health_bridge.py` 注册 `sys.modules['core']` 指向 Factor_Fingerprint/core,加载后未清理,遮蔽 Factor_DB/core,导致 `test_p0_duckdb_pivot.py` 和 `test_integration_real_data.py` 全量回归时收集错误
- **修复**:
  - `data_bridge.py`: 模块名 `"core.data_v3"` → `"_factor_trading_data_v3"`; 移除 `sys.path.insert(0, Factor_Trading_v3.0)`
  - `health_bridge.py`: 加载完 core.fingerprint/health 后,若 `sys.modules['core']` 仍指向 Factor_Fingerprint/core,删除它
- **测试**: `tests/test_fix7_core_namespace_collision.py` — 6/6 通过; 手工校验 6/6; `test_p0_duckdb_pivot.py` 16/16 恢复

### Fix 6: ADR 状态更新

- **新增**: ADR-010 (配置系统统一)、ADR-011 (core 命名空间隔离)、ADR-012 (外部路径配置化)
- **更新**: ADR-007 风险描述 (core 冲突已由 ADR-011 补全)
- **路线图**: 新增 v2.2.2 章节

### 测试汇总

| 修复 | TDD 测试 | 手工校验 | 回归 |
|------|----------|----------|------|
| Fix 1 | 4/4 | — | 无回归 |
| Fix 5 | 6/6 | — | 无回归 |
| Fix 2 | 13/13 | 8/8 | 41 passed |
| Fix 3 | 5/5 | — | 39 passed |
| Fix 4 | 5/5 | — | 93 passed |
| Fix 7 | 6/6 | 6/6 | 252 passed + 16/16 历史失败恢复 |
| 总计 | 39/39 | 14/14 | 0 新增失败 |

---

## v2.2.1 — 漂移检测与优化器改进 (2026-07-01)

### 概览

针对漂移检测假阳性、优化器 look-ahead bias、因子日期不匹配、双信号融合逻辑保守等问题,完成 5 项改进 (P0-P2) + 1 项决策 (P3-2)。全部采用严格 TDD 开发,每步包含 Red Phase → Green Phase → 手工校验 → 回归测试。

### P0: 关键改进

**P0-1: 滚动窗口 KS + 调松阈值** (`backtest/unified_drift.py`)

- **问题**: 原二分分割 + 固定 KS 阈值导致假阳性率高,5 年数据漂移信号未累积,阈值过高导致全 stable。
- **修复**: 新增 `_compute_rolling_structure_drift()`,采用滚动窗口 (126 天 ≈ 6 个月) 滑动扫描 IC 序列,结合 p 值 (p<0.05) 过滤,取最大漂移分数。调松阈值: warning 30→15, drift 50→30, severe 70→50, structure_sig 30→20。
- **测试**: `tests/test_backtest/test_drift_improvements.py` — 15/15 通过

**P0-2: 优化器 Pipeline-in-the-loop** (`optimizer.py`)

- **问题**: 原优化器 objective 函数只对参数做数学变换,未真正调用 Pipeline 处理因子,优化结果与实际 Pipeline 行为脱节。
- **修复**: objective 函数真正调用 `FactorProcessingPipelineV2.fit() + transform()`,在处理后的因子上计算 IC。新增 `_params_to_config()` 完整 8 参数映射 (hard_routing_prob, merge_alpha, ks_alpha, mixed_winsor_sigma, transform_aggressiveness, classification_threshold_static/dynamic, migration_threshold)。
- **测试**: `tests/test_backtest/test_p0_2_pipeline_in_loop.py` — 5/5 通过

### P1: 因子日期自适应

**P1: per-factor min_dates + reindex 对齐** (`backtest/data_bridge.py` + `backtest/engine.py`)

- **问题**: Barra 因子 41 天 vs 日频因子 1212 天,统一阈值导致 Barra 因子被错误过滤或形状不匹配。
- **修复**:
  - `create_dataloader()` 新增 `min_dates: Dict[str, int]` 参数,per-factor 阈值过滤
  - reindex 对齐: 因子数据 reindex 到 close_df 的 (dates, stocks) 索引,缺失日期填 NaN
  - `engine.py` 空因子场景不抛异常,`run()` 返回空 dict
- **手工校验**: Barra 41 天 reindex 到 close 250 天,有数据期数=41 (完美对齐); 20 因子混合,5 个 Barra 因子全部产出结果
- **测试**: `tests/test_backtest/test_p1_adaptive_min_dates.py` — 7/7 通过 + 8/8 手工校验

### P2: 漂移融合与优化器 CV

**P2-1: 双信号加权融合 — and/or/max 三模式** (`backtest/unified_drift.py`)

- **问题**: 原 AND 逻辑 (dual_signal_required=True) 过于保守,仅一个信号显著时不报告漂移,导致漏报。
- **修复**: 新增 `signal_fusion_mode` 配置,支持三模式:
  - `and`: 两信号都显著才确认 (保守,旧默认)
  - `or`: 任一显著即确认 (激进)
  - `max`: 取主信号与主阈值比较,主信号显著即用主信号分数判定等级 (平衡,新默认)
- **向后兼容**: 用户传 `dual_signal_required` 但未传 `signal_fusion_mode` 时,自动推断 (True→and, False→or)
- **测试**: `tests/test_backtest/test_p2_1_signal_fusion.py` — 11/11 通过 + 12/12 手工校验

**P2-2: 优化器 CV 改进 — _cv_evaluate 接口重写 + optimize() 调用 CV** (`optimizer.py`)

- **问题**: `_cv_evaluate` 存在但未被 `optimize()` 调用 (死代码),且 CV 的 evaluate_fn 只用 test_data 算 IC,未利用 train_data 做 Pipeline fit,存在 look-ahead bias。
- **修复**:
  - `_cv_evaluate` 接口重写: `(factor_values, forward_returns, evaluate_fn)` → `(factor_data, forward_returns, config)`
  - 每个 fold 中 Pipeline 在 train 上 fit,test 上 transform (消除 look-ahead)
  - `optimize()` 的 objective 函数调用 `_cv_evaluate` 替代全量数据评估
  - 新增 `_full_evaluate()` 数据不足时的回退
- **手工校验**: 12/12 通过 (CV folds 生成、Pipeline fit/transform 日期范围、CV 分数=各 fold IC 平均、无 look-ahead bias、数据不足回退、optimize() 调用 CV、Pipeline.fit 调用次数 = n_trials × n_folds、复合目标函数数值一致性、接口向后兼容、空因子数据、transform_aggressiveness 映射)
- **测试**: `tests/test_backtest/test_p2_2_optimizer_cv.py` — 9/9 通过

### P3: 决策记录

**P3-2: 分组并行方案 A/B 对比实验 — 保留方案 A** (ADR-009)

- **背景**: P1 修复的 reindex 对齐引发假设:是否可以取消 `parallel_runner.py` 的按日期分组,统一共享全局 fwd_returns?
- **实验**: 20 个真实因子 (13 Barra 月频 41天 + 7 日频 1212天) A/B 对比
- **结果**:
  - 日频因子: ICIR/IC 完全一致 (diff=0.0)
  - Barra 因子: 差异巨大 (ICIR max diff=0.895, IC max diff=0.148)
  - 性能: 方案 A 44.82s vs 方案 B 137.81s (B 3x 更慢)
- **根因**: 方案 B 将不同频率因子统一到日频,fwd_returns 语义改变 (月收益率预测 → 日收益率预测)
- **决策**: 保留方案 A (按日期分组),不实施方案 B
- **实验脚本**: `tests/test_backtest/experiment_p3_2_ab_comparison.py`

### 测试总结

| 套件 | 测试数 | 通过 | 手工校验 |
|------|--------|------|----------|
| test_drift_improvements.py (P0-1) | 15 | 15 | — |
| test_p0_2_pipeline_in_loop.py (P0-2) | 5 | 5 | — |
| test_p1_adaptive_min_dates.py (P1) | 7 | 7 | 8/8 |
| test_p2_1_signal_fusion.py (P2-1) | 11 | 11 | 12/12 |
| test_p2_2_optimizer_cv.py (P2-2) | 9 | 9 | 12/12 |
| 回归测试 | 565 | 565 | — |
| **总计** | **612** | **612** | **32/32** |

> 2 个预存失败与本次改进无关 (Factor_Decoupler 无行业数据、版本号 2.1.0 vs 2.0.0)

### 经验教训

1. **reindex 对齐 ≠ 语义等价**: P1 的 reindex 解决了 NaN 填充,但不同频率因子的 fwd_returns 语义不同,reindex 不能消除这种差异 (ADR-009)
2. **实验驱动决策**: 方案 B 理论上看似合理,但 A/B 实验揭示了频率语义问题。如果直接实施会引入隐蔽的正确性 bug
3. **性能预期可能反转**: 方案 B 预估 1.3-1.5x 加速,实际 3x 更慢 (NaN 跳过虽快但仍有开销)
4. **死代码陷阱**: P2-2 发现 `_cv_evaluate` 存在但未被调用,优化器实际用全量数据评估,存在 look-ahead bias

---

## v2.2.0 — Backtest 集成 (2026-07-01)

### 回测引擎集成

根据方案 D（peer module + adapter pattern），在 `backtest/` 新增完整回测引擎模块，串联 Pipeline 输出 → 因子回测 → 健康度评估 → 漂移检测。

**新增模块:**

| 模块 | 用途 | 测试 | 状态 |
|------|------|------|------|
| `backtest/factor_metrics.py` | 因子级指标单一真相源 | 30/30 | ✅ 完成 |
| `backtest/data_bridge.py` | Pipeline → DataLoaderV3 适配器 | 10/10 | ✅ 完成 |
| `backtest/engine.py` | 因子回测引擎 | 20/20 | ✅ 完成 |
| `backtest/health_bridge.py` | 回测 → FactorHealthMonitor 适配器 | 13/13 | ✅ 完成 |
| `backtest/unified_drift.py` | 双轨融合漂移判定 | 13/13 | ✅ 完成 |
| `backtest/pipeline_integration.py` | 端到端 Pipeline 集成 | 9/9 | ✅ 完成 |

**配置扩展 (config_v2.py):**

- 新增 `BacktestConfig` 类，包含 IC 方法、多空参数、漂移阈值
- `PipelineV2ConfigUnified` 新增 `backtest` 字段
- JSON 序列化支持

**核心设计:**

- **单一真相源**: `factor_metrics.py` 唯一权威，其他模块不得重复实现
- **适配器模式**: `data_bridge` 适配 Pipeline → DataLoaderV3，`health_bridge` 适配回测 → HealthMonitor
- **双轨漂移融合**: 结构漂移 (Fingerprint) + 性能漂移 (Backtest) → 融合判定
- **不修改外部模块**: 适配器通过 importlib 加载，不改动外部 Fingerprint 代码
- **TDD 严格校验**: 9 次分阶段 TDD，逐指标手工计算验证

**架构图:**
```
  Pipeline 输出
      ↓
  DataBridge (n_stocks, n_dates) → (n_dates, n_stocks)
      ↓
  DataLoaderV3
      ↓
  FactorBacktestEngine → IC/ICIR/Decay/HitRate/Turnover/LS/Spread
      ↓
  HealthMonitorAdapter → 注入 FactorHealthMonitor → 5 维健康评分
      ↓
  UnifiedDriftReporter → 结构+性能+换手率 → 融合漂移判定
```

---

## v2.1.0 — 架构修复 (2026-07-01)

### P0: 关键架构缺陷

**P0-1: 硬路由 → 概率加权软路由** (`pipelines_v2.py`)

- **问题**: `transform()` 使用硬路由，概率阈值开关导致因子类型切换时处理断崖。因子从 STATIC 跳到 DYNAMIC 时，处理流程瞬间改变，产生不可控的分布跳跃。
- **修复**: 新增 `_get_pipeline_weights()` 将 `ClassificationResult` 转换为管道权重字典，`_apply_weighted_transform()` 执行多管道加权混合。高置信度(>0.9)时仍使用硬路由优化性能。
- **测试**: `tests/test_p0_fixes.py::TestSoftRouting` — 8/8 通过
- **影响**: 因子过渡期不再出现断崖，输出是各管道的加权混合。

**P0-2: 阈值校准** (`pipelines_v2.py`)

- **问题**: 分类阈值 `static_threshold=0.80`、`dynamic_threshold=0.40` 硬编码，不考虑数据分布特征。
- **修复**: 新增 `ThresholdCalibrator` 类，支持分位数法（基于数据分布）和市场预设（a_share/us_equity/crypto）。`fit()` 时自动校准阈值。
- **测试**: `tests/test_p0_fixes.py::TestThresholdCalibration` — 6/6 通过

### P1: 高优先级增强

**P1-3: 统一三条管道 `fit()` 模式** (`pipelines_v2.py`)

- **问题**: 三条管道(`StaticFactorPipeline`/`DynamicFactorPipeline`/`MixedFactorPipeline`)的中间数据记录不一致，调试困难。
- **修复**: 在 `_BaseFactorPipeline.__init__()` 添加 `_intermediate_data` 字典，新增 `get_intermediate_data()` 统一接口。三条管道 `fit()` 均记录中间数据。
- **测试**: `tests/test_p1_fixes.py::TestUnifiedFitPattern` — 5/5 通过

**P1-4: 适配器回退 Warning** (`adapters.py`)

- **问题**: 外部子模块不可用时，适配器静默回退到简单方案，用户无法感知数据质量降级。
- **修复**: `PipelineStep` 基类添加 `is_fallback_mode`。`ImputerAdapter`/`ProcessingAdapter`/`NeutralizerAdapter`/`GarchWhiteningAdapter` 在回退时发出 `warnings.warn(UserWarning)`。`get_stats()` 包含 `fallback_mode` 字段。
- **测试**: `tests/test_p1_fixes.py::TestAdapterFallbackWarnings` — 5/5 通过

**P1-5: `transition_weights` 接入路由层** (`pipelines_v2.py`)

- **问题**: `FactorFingerprintMonitor.get_transition_weights()` 返回的指数衰减迁移权重未被使用。
- **修复**: 新增 `_merge_transition_weights()` 融合分类权重和迁移权重。在 `transform()` 中集成 monitor 迁移权重检查。
- **测试**: `tests/test_p1_fixes.py::TestTransitionWeightsRouting` — 4/4 通过

### P2: 中期改进

**P2-6: 迁移显著性检验 — KS 双样本检验** (`pipelines_v2.py`)

- **问题**: `get_transition_weights()` 仅基于最近 3 期类型是否一致判断迁移，不做统计显著性检验，噪声可能导致误报。
- **修复**: 新增 `_ks_migration_significance()` 函数，使用 `scipy.stats.ks_2samp` 对历史/近期因子分布进行双样本 KS 检验。**Bonferroni 多重比较校正**避免假阳性。仅当 KS 显著(p < α/n)时才合并迁移权重。集成到 `transform()` 中。
- **测试**: `tests/test_p2_fixes.py::TestKSMigrationSignificance` — 6/6 通过
- **架构含义**: 迁移检测从"简单启发式"→"统计假设检验"，大幅降低假阳性。

**P2-8: `importlib` 替代 `sys.path`** (`adapters.py`)

- **问题**: `_import_external_class()` 使用 `sys.path.insert(0, ...)` 全局修改 `sys.path`，异常时无法恢复，可能污染后续导入。
- **修复**: 新增 `_temp_sys_path` 上下文管理器，使用 `importlib.import_module` 替代 `__import__`。无论导入成功或失败，`sys.path` 均恢复原状。
- **测试**: `tests/test_p2_fixes.py::TestImportlibRefactor` — 3/5 通过 + 2 skipped

### 测试总结

| 套件 | 测试数 | 通过 | 失败 | 跳过 |
|------|--------|------|------|------|
| test_p0_fixes.py | 14 | 14 | 0 | 0 |
| test_p1_fixes.py | 14 | 14 | 0 | 0 |
| test_p2_fixes.py | 11 | 9 | 0 | 2 |
| 回归测试 | 190 | 185 | 3* | 2 |
| **总计** | **229** | **222** | **3*** | **4** |

> *3 个失败均为既有问题：分类器 mock 数据边界、无行业数据的解耦测试、Imputer 重复列名。与本次修复无关。

---

## v2.0.0 — 智能自适应流水线 (2026-05)

### 新增特性

- 因子指纹诊断层：13 维统计指标自动诊断
- 自适应因子分类：STATIC / DYNAMIC / MIXED 三类自动分流
- 语义-统计融合：自然语言构造规则 + 统计指纹的贝叶斯融合
- 三重中性化：原始值中性化 → AR 建模 → 残差中性化
- GARCH 白化（可选）：高自相关静态因子波动率聚集消除
- 处理顺序调整：静态/混合因子先中性化后标准化
- 持续迁移监测：FactorFingerprintMonitor + FactorHealthMonitor

### 架构演进

```
v1.0: 单一固定流程
原始因子 → 插补 → 去极值 → 变换 → 标准化 → 中性化

v2.0: 智能自适应流程
原始因子 → 指纹提取 → 分类(语义+统计) → 分流处理 → 迁移监测
                ↓
        ┌───────┼───────┐
        ↓       ↓       ↓
    静态管道  动态管道  混合管道

v2.1: 架构修复
软路由 / 阈值校准 / 统一fit模式 / 适配器回退Warning / 迁移权重接入 / KS显著性检验

v2.2: Backtest 集成
Pipeline → DataBridge → DataLoaderV3 → Engine → HealthMonitorAdapter → UnifiedDriftReporter

v2.2.1: 漂移检测与优化器改进
滚动KS / Pipeline-in-the-loop / per-factor min_dates / 三模式融合 / CV消除look-ahead
```

---

## v1.0.0 — 基础流水线 (2025)

### 初始版本

- 固定五步法：插补 → 去极值 → 变换 → 标准化 → 中性化
- 适配器模式封装外部子模块
- sklearn 风格 fit/transform 接口
- PipelineDAG 依赖管理
- PipelineCache 中间结果缓存
- PipelineOrderValidator 处理顺序校验