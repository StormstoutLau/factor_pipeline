# v3.10.0 调研 — P-003 截面 T+1 reversal 真实现（证据层，口径 A）

---
id: v3100-reversal-evidence-RESEARCH
type: design
version: 1.3
status: verified
date: 2026-11-21
depends: [research-p003-p007-decisions, v394-audit-coverage-fix-CHECKLIST]
upstream: null
---

> **Feature**: P-003「截面 T+1 reversal 真实现」——用交易方向 × 截面价格的已实现反转，替代 `temporary_share` 的组合日超额 AR(1) 代理。
> **创建日期**: 2026-11-21
> **状态**: v1.3 verified（v1.2 Step 2 复审 PASS_WITH_FIXES；**v1.3 = Step 9 实测读数回填**：§3.5 已用 C1/C2 × 新旧对照表替换「待 E1」，登记勘误 E-2）
> **Spec 步骤**: Step 1-2（v1.3 为 Step 9 回填）
> **包版本**: **3.9.5**（patch；用户 2026-11-21 确认，DESIGN §12.1）
> **档位**: 预计 T1（最终以本批 DESIGN 登记为准，PROGRESS 不单列）
> **口径裁决（2026-11-21，用户，不可推翻）**: 走 **口径 A**——仅证据层真实现，`cost_by_h` / `net(h)` 不变，`core/decay.py` 零改动（证据见 [RESEARCH_P003_P007_DECISIONS.md](../../docs/research/RESEARCH_P003_P007_DECISIONS.md) §2）。
> **执行约束（上游既定）**: Python 3.9 语法；零新增依赖；默认路径 `out/capacity_impact.json` SHA 必须保持 `82728CE103D49AF211DD12DE87D9784040FC909C83FB7A88D521AF30A89B2548`；`panel_hash` 逐位不变；测试基线 **2065 passed / 15 skipped / 0 failed**（920.74 s）。

---

## 1. 调研目标

本批只回答「证据层怎样算得对」，不改变任何成本或容量口径。核心问题：

1. **Q1 输入契约**：把「交易方向 `s` + 截面价格」落成可复核的事件样本，最小字段是什么？在现有 `build_portfolio_panels` / `build_daily_panels` / `runner` 三层之间如何传递，才能不把 pandas 市场数据耦合进 `backtest/execution/shell/`？
2. **Q2 统计量**：`reversal_bps = −s·(P_{t+1}−P_t)/P_t` 怎样从单事件推广到组合层（加权、截面 demean、买卖分侧），并与现有 `temporary_share` 的 `(point, lo, hi)` 三元组契约兼容？
3. **Q3 口径与边界**：A 股 T+1 隔夜折价 5–13 bps/日（上游调研 §2.4）如何在价格端点选择与截面处理中剥离？停牌 / 涨跌停 / 除权 / ST / 首期建仓 / 微权重 / 极端收益如何过滤并披露？
4. **Q4 影响面**：哪些读数允许变、哪些必须逐位不变？39 月校准需要出哪些对照读数？现有测试与工件如何最小改动？

**明确不做**：

- 不把反转接入 `cost_by_h`（口径 A 裁决）；
- 不改 `impact_bps` / `c` / `rho` / `alpha0` / `capacity`；
- 不做永久/临时冲击的因果分解（无逐笔、无反事实，属能力边界）；
- 不做 P-006 的限价取整口径（已并入 P-006）、不做 P-010 的股票×月重采样；
- 不引入 tick / 逐笔数据（数据源无）。

---

## 2. 调研方法

### 2.1 工具与降级声明

| 工具 | 用途 | 查询/范围 |
|------|------|----------|
| 仓内代码检索（Grep / Read / Glob） | 定位现状链路、输入可得性、影响面 | `panels.py` / `runner.py` / `impact.py` / `loaders.py` / `verify_capacity_impact.py` / `verify_long_side_research.py` / `report.py` |
| 既有工件（E1） | 现有读数与键域核对 | `out/v394_calibration.json`、`out/v394_decay_curve.json`、默认 `out/capacity_impact.json` |
| 上游 verified 调研（E1） | 理论框架与 A 股特殊性 | [RESEARCH_P003_P007_DECISIONS.md](../../docs/research/RESEARCH_P003_P007_DECISIONS.md) §2、§5 |
| 外部检索 | **本批降级未新增** | 见 §3.8 理由 |

**降级理由（诚实声明）**：P-003 的方法选择已由用户裁决为口径 A；Step 1 只需把「真实现」落成可执行契约，不需要再选方法。上游调研已由两路独立检索代理完成并留痕（含 DOI/URL），本批**不新增外部题录**，避免用摘要级读数替代原文核验。所有新结论以仓内代码（E3）与既有工件（E1）为依据。

### 2.2 调研范围

- **代码**：`backtest/execution/shell/panels.py`、`runner.py`、`core/impact.py`、`shell/loaders.py`、`scripts/verify_capacity_impact.py`、`scripts/verify_long_side_research.py`、`backtest/execution/shell/report.py`；
- **工件**：v3.9.4 的 39 月校准 JSON / 衰减曲线 / 默认快照；
- **文档**：上游 P-003/P-007 裁决调研、v3.9.4 CHECKLIST/AUDIT、`docs/SPEC_COMPLIANCE.md`；
- **排除**：P-006、P-008、P-010、P-011、P-014、P-015。

### 2.3 证据等级口径

沿用 `docs/ASSERTION_EVIDENCE_FRAMEWORK.md`：E1 = 可重放工件/读数；E3 = 代码级双读；E5 = 未核实。本文所有 E3 锚点以 commit `9b09f8c`（v3.9.4）为基线；Step 9 改码前如行号漂移，以「函数名 + 关键字」复核。

---

## 3. 调研发现

### 3.0 发现总表

| 编号 | 发现 | 证据等级 | 位置 |
|------|------|---------|------|
| F-1 | 现有 `temporary_share` 的输入是**组合日超额**的 t / t+1 序列，不是交易事件 | E3 | [panels.py L550-558](file:///f:/Coding/factor_pipeline/backtest/execution/shell/panels.py#L550-L558)、[runner.py L523-528](file:///f:/Coding/factor_pipeline/backtest/execution/shell/runner.py#L523-L528) |
| F-2 | 组合权重为**月频形成**，日频收益变化主要来自持仓价格，不是当日交易；代理把「持仓收益反转」误当「交易冲击回落」 | E3 | [verify_capacity_impact.py L153-163](file:///f:/Coding/factor_pipeline/scripts/verify_capacity_impact.py#L153-L163)、[L212-268](file:///f:/Coding/factor_pipeline/scripts/verify_capacity_impact.py#L212-L268) |
| F-3 | 真实现所需输入在仓内**全部可得**：月频权重 `w`、`Δw`、日频 `adj_price`、日频 `suspend/st/limit_up`、分钟层 `ret_day`（盘中） | E3 | [verify_capacity_impact.py L87-128](file:///f:/Coding/factor_pipeline/scripts/verify_capacity_impact.py#L87-L128)、[verify_long_side_research.py L74-114](file:///f:/Coding/factor_pipeline/scripts/verify_long_side_research.py#L74-L114)、[loaders.py L64-76](file:///f:/Coding/factor_pipeline/backtest/execution/shell/loaders.py#L64-L76) |
| F-4 | `load_implementability` 只产出 `limit_up`，**无 `limit_down`**；卖出侧过滤需补对称标记 | E3 | [verify_long_side_research.py L97-114](file:///f:/Coding/factor_pipeline/scripts/verify_long_side_research.py#L97-L114) |
| F-5 | 现有 `temporary_share` 是通用 AR(1) 统计量（`-cov/var` + stationary bootstrap），可复用其区间形态，但输入需从「组合序列」改为「交易事件样本」 | E3 | [impact.py L193-227](file:///f:/Coding/factor_pipeline/backtest/execution/core/impact.py#L193-L227) |
| F-6 | `report.py` 的 Markdown **不渲染** `temporary_share`，只渲染 `decay/cost/net` 与 warnings；改口径只影响 JSON 与 warning 文案 | E3 | [report.py L109-141](file:///f:/Coding/factor_pipeline/backtest/execution/shell/report.py#L109-L141) |
| F-7 | 默认路径不产出 `temporary_share`（`--calibrate` 分支才产出）；默认 SHA 不受本批影响 | E1 | 默认 `out/capacity_impact.json` 顶层仅 `meta/results`；v3.9.2 AUDIT §G3 |
| F-8 | 39 月现有读数：`temporary_share = [0.0, 0.0, 0.00422538668409314]`，`temporary_basis="portfolio_ar1_proxy"`，warning「非 T+1 反转，不进入容量」 | E1 | [out/v394_calibration.json](file:///f:/Coding/factor_pipeline/out/v394_calibration.json) L363889-363893、L357801-357804 |
| F-9 | `panel_hash` 的 payload **不含** `temporary` / `temporary_share`；改统计量不改哈希 | E3 | [panels.py L424-440](file:///f:/Coding/factor_pipeline/backtest/execution/shell/panels.py#L424-L440)（键域：adv_window_days / code_range / granularity / lambda_min_days / minute_window / months / n_lambda / n_samples / sigma_clip / windows） |

### 3.1 现状链路（E3）

```
build_portfolio_panels(P, cfg)
  ├─ w = make_weights(...)                       # 月频形成日权重
  ├─ excess_d = daily_portfolio_excess(P, w)     # 日频组合超额（close-to-close）
  └─ portfolio = {... 'excess_d': Series, ...}
        ↓
build_daily_panels(cfg, daily, portfolio)
  ├─ r1 = excess_d[:-1], rev1 = excess_d[1:]
  ├─ out['temporary'] = {'r1': ..., 'rev1': ...}
  ├─ out['temporary_basis'] = 'portfolio_ar1_proxy'
  └─ warning「非 T+1 反转，不进入容量」
        ↓
run_calibration(...)
  ├─ ts = temporary_share(r1, rev1)              # -cov/var + bootstrap CI
  └─ result['temporary_share'] = ts; result['temporary_basis'] = ...
```

关键事实：

1. `daily_portfolio_excess` 的日收益来自 `adj_price.pct_change()` 与月频权重的日频前向填充（[verify_capacity_impact.py L153-163](file:///f:/Coding/factor_pipeline/scripts/verify_capacity_impact.py#L153-L163)）；**除形成日外没有交易**。
2. 因此 `-cov(ex_d_t, ex_d_{t+1}) / var(ex_d_t)` 度量的是**持仓组合的日收益反转**，不是「本笔交易造成的临时冲击回落」。
3. 现有 warning 已如实声明该代理「非 T+1 反转，不进入容量」；本批把它替换为真正的交易事件统计量。

> **状态标注（回应 Step 2 F-1）**：以上是 **当前实现**。本文档定义的是**目标契约**；代码切换发生在 Step 5（IMPLEMENTATION）与 Step 9（实测），Step 1-2 不改任何 `.py`。因此「当前代码仍跑旧代理」不是本阶段缺陷，而是实施排期的前置事实。

### 3.2 现有代理为什么不是 T+1 reversal

| 维度 | 现有代理 | 真实现应满足 |
|------|---------|-------------|
| 样本单位 | 组合日收益（所有交易日） | 股票×形成日交易事件 |
| 交易方向 | 无 | `s = sign(Δw)`，买 +1 / 卖 −1 |
| 交易规模 | 无 | `a = |Δw|`（权重变动） |
| 价格口径 | 组合 close-to-close | 个股价格端点，截面处理 |
| 统计量 | 组合 AR(1) 系数 | 交易事件加权反转份额 + bps |
| T+1 隔夜折价 | 直接混入 | 截面 demean / 盘中口径剥离 |
| 经济含义 | 持仓收益均值回复 | 交易后价格回落（临时冲击近似） |

### 3.3 真实现输入契约与统计量（建议口径）

#### 3.3.1 事件定义

- 形成日 `t`：月频权重 `w_t` 的日期（月末最后一个交易日，`w.index`）。
- 权重变动：`Δw_{i,t} = w_{i,t} − w_{i,t−1}`；首个形成日 `w_{t−1}=0`（建仓）。
- 事件筛选：`|Δw| ≥ 1e-8`；`w ≥ 0`（A 股无融券，卖出只能来自已持有）。
- 交易方向 `s_{i,t} = sign(Δw_{i,t})`；交易规模 `a_{i,t} = |Δw_{i,t}|`。

#### 3.3.2 价格端点与 trade-to-trade

`P_{i,d}` 取**复权收盘价**（`adj_price`），即当日最后一笔成交价；`t+1` 为形成日后的**下一个交易日**（不是自然日）。收益一律用 `pct_change(fill_method=None)`，**不前向填充**，避免停牌日假收益。

- **C1（主口径，注册公式）**：`r_{i,t} = P_{i,t}/P_{i,t−1} − 1`，`r_{i,t+1} = P_{i,t+1}/P_{i,t} − 1`；对每个日期做**截面 demean**（减去当日可投资域等权均值），得到 `r̃`。这是「最后一笔成交价 → 下一交易日最后一笔成交价」的 trade-to-trade 日频实现；市场共同的 T+1 隔夜折价由截面 demean 吸收。
- **C2（稳健性口径）**：`r_{i,t} = close_t/open_t − 1`，`r_{i,t+1} = close_{t+1}/open_{t+1} − 1`（同样截面 demean）。两端均为集合竞价/收盘成交价，**完全剔除隔夜**，用于检验 C1 的残差隔夜污染。日频 `stock_open.pkl` 已在数据源中；分钟层 `ret_day` 亦为盘中口径，可作第二源。
- **C3（VWAP-to-VWAP）**：`amount/volume` 的成交均价；数据单位（千元/手）未校准，暂不作为主口径。

**选择理由**：C1 与 PROGRESS P-003 登记的 `reversal_bps = −s·(P_{t+1}−P_t)/P_t` 逐字一致，且「收盘价 = 最后一笔成交价」满足 trade-to-trade 的「不用买卖报价中点」要求；T+1 隔夜折价作为**市场共同项**由截面 demean 剥离，残差由 C2 对照。C1 与 C2 的分歧留待 Step 9 实测裁决（U-1）。

#### 3.3.3 统计量

对事件集合 `E = {(i,t)}`：

```
x_e = s_e · r̃_{i,t}          # 交易当日、方向调整后的截面超额收益
y_e = s_e · r̃_{i,t+1}        # 次日、方向调整后的截面超额收益

reversal_bps = − (Σ_e a_e y_e / Σ_e a_e) × 1e4
share        = clip( − Σ_e a_e x_e y_e / Σ_e a_e x_e², 0, 1 )
```

- `reversal_bps > 0` 表示「交易后价格朝不利方向回落」（买入后跌 / 卖出后涨），即临时冲击的已实现成本；**口径 A 下只报告，不进入 `cost_by_h`**。
- `share` 是交易事件加权的「当日方向性移动在次日被反转的比例」，与现有 `temporary_share ∈ [0,1]` 语义对齐。
- **买卖分侧**：分别对 `s_e=+1` / `s_e=−1` 计算 `reversal_bps_buy` / `reversal_bps_sell`；合并值按 `a_e` 加权。方向不对称单列，不强行合并解释。
- **区间与三元组兼容**：`temporary_share` 保持现有 `[point, lo, hi]` 三元组（下游/测试不变）；`reversal_bps` 同样输出 `{point, lo, hi}`，且与 `share` 共用同一组 bootstrap 重抽样。按**形成日聚类**的 block bootstrap（39 个月末为 39 个 cluster；同一形成日的数千只股票高度相关，不能按事件独立重采样）。对每个月预计算充分统计量 `(Σ a x², Σ a x y, Σ a y, Σ a)`，bootstrap 只重采样月份，`O(1000×39)`，避免 `1000×15万` 的事件级重采样。seed 固定（建议 20261121），`point` 必须落在 `[lo, hi]` 内（与现有契约一致）；若 cluster <3 或 `Σ a x²=0`，`share=0`、`reversal_bps=NaN` 并写 warning。

#### 3.3.4 输出契约（建议）

`build_daily_panels` 新增/透传：

```
out['temporary'] = {
    'rt':   r̃_{i,t}      (n_events,),   # 截面 demean 后、未乘方向
    'rt1':  r̃_{i,t+1}    (n_events,),
    'side': s_e           (n_events,),   # ±1
    'weight': a_e         (n_events,),
    'month': m_e          (n_events,),   # 0..T-1，用于聚类 bootstrap
    'price_basis': 'adj_close_to_close_cs',
}
out['temporary_basis'] = 'cross_section_t1'
out['temporary_proxy_ar1'] = [point, lo, hi]   # 旧代理，仅对照
out['temporary_proxy_basis'] = 'portfolio_ar1_proxy'
out['reversal_counts'] = {n_events, n_months, n_buy, n_sell, n_first_period, ...}
```

`runner` 保持 `result['temporary_share']` / `result['temporary_basis']` 两个既有键；新增 `result['reversal_bps']`（`{point, lo, hi, buy: {point, lo, hi}, sell: {point, lo, hi}, n, n_months}`）与 `result['reversal_price_basis']`。**不回写** `cost_by_h` / `net`。`temporary_share` 与 `reversal_bps` 的区间来自同一组月份重抽样，避免两个读数 CI 口径不一致。

**兼容策略**：若 `temporary` 中无 `rt/rt1/side/weight/month`（如现有最小测试面板），回退旧代理并保留 `temporary_basis="portfolio_ar1_proxy"` 与原 warning。这样 `test_temporary_basis_flagged` 等既有最小用例不必改语义，校准路径则走真实现。

### 3.4 边界条件

| 情形 | 判定 | 处置 | 披露计数 |
|------|------|------|---------|
| 停牌 `t` | `suspend_{i,t}=1` | 剔除事件（当日无法交易） | `n_suspended_t` |
| 停牌 `t+1` | `suspend=1` 或价格 NaN | 剔除（次日无法形成可交易价格） | `n_suspended_t1` |
| 涨停 `t` 且买入 | `limit_up_{i,t}=1` | 剔除（买不进） | `n_limit_up_t` |
| 跌停 `t` 且卖出 | `limit_down_{i,t}=1`（**Step 9 必须补齐**） | 剔除（卖不出） | `n_limit_down_t` |
| 涨跌停 `t+1` | `limit_up/limit_down=1` | 剔除（价格不可交易/失真） | `n_limit_t1` |
| ST `t` 或 `t+1` | `st=1` | 剔除（5% 限价、退市噪声） | `n_st` |
| 除权除息 | — | 使用 `adj_price` / 复权 open；不额外处理 | — |
| 首期建仓 | `t` 为首个形成日 | 保留并打 `first_period` 标记；Step 9 出「剔除首期」敏感性 | `n_first_period` |
| 微权重 | `|Δw| < 1e-8` | 剔除（数值噪声） | `n_tiny` |
| 极端收益 | `|r| > 0.5` | 剔除（数据错误守卫） | `n_extreme` |
| 退市/缺失 | `P` NaN | 自动剔除 | `n_missing` |
| 卖出但未持有 | `Δw<0` 且 `w_{t−1}=0` | 理论不可能（long-only）；断言 | — |

**除权说明**：`adj_price = close × adj`（[verify_capacity_impact.py L89](file:///f:/Coding/factor_pipeline/scripts/verify_capacity_impact.py#L89)）；涨跌停标记使用 `raw_ret`（[verify_long_side_research.py L90-114](file:///f:/Coding/factor_pipeline/scripts/verify_long_side_research.py#L90-L114)），两者不可混用。反转收益必须用复权价，否则除权日会出现假反转。

**`limit_down` 的验收前置（回应 Step 2 F-3）**：`load_implementability` 目前只产出 `limit_up`（[verify_long_side_research.py L97-114](file:///f:/Coding/factor_pipeline/scripts/verify_long_side_research.py#L97-L114)）。P-003 验收标准③要求单测覆盖「涨跌停边界」，因此 Step 9 **必须在实现 `limit_down` 镜像标记后才允许把 CHECKLIST 置为 accepted**；若镜像公式在真实数据上不可用（例如 `stock_low.pkl` 缺失或单位不符），则退化为「仅用 `suspend` + 价格缺失 + `|r|>0.5` 过滤卖出侧」，并在 `reversal_counts.n_limit_down_unavailable=True` 与 `evidence_warnings` 双处披露，不得静默通过。该项已登记为 U-2。

### 3.5 代理 vs 真实现差异对照（验收②的骨架）

| 维度 | 旧代理（`portfolio_ar1_proxy`） | 真实现（`cross_section_t1`） | 预期差异方向 |
|------|--------------------------------|------------------------------|-------------|
| 样本 | 约 1475 个交易日 | **73 个形成日 / 72 个有效聚类月 × 约 5000 只（25.2 万事件）** | 事件数大增；聚类单位是形成月（E-2） |
| 单位 | 组合超额收益 | 个股方向调整截面收益 | 组合层异质性与行业/风格抵消被移除 |
| 交易条件 | 无 | `s=sign(Δw)`、`a=|Δw|` | 只度量真正被交易的股票 |
| 隔夜 | close-to-close 混入 | 截面 demean + C2 对照 | C2 剔除隔夜后量级缩小约 13–15% |
| 估计量 | `-cov/var` | 加权 `-Σaxy/Σax²` | 对买卖不对称、事件规模敏感 |
| 现有读数 | `[0, 0, 0.004225]` | **C1 `[0, 0, 0.038326]`／C2 `[0.044918, 0.013728, 0.075428]`** | C1 点估计原始值 <0 被 clip 至 0；C2 点估计 >0 |
| 成本影响 | 无 | 无（口径 A） | `cost_by_h` / `net(h)` 逐位不变 |

**Step 9 实测对照（2026-11-21，`out/v3100_calibration*.json`）**

| 读数 | C1 `adj_close_to_close_cs` | C2 `adj_intraday_open_close` | 旧代理 `portfolio_ar1_proxy` |
|---|---|---|---|
| `temporary_share` [point, lo, hi] | `[0.000000, 0.000000, 0.038326]` | `[0.044918, 0.013728, 0.075428]` | `[0.000000, 0.000000, 0.004225]` |
| `reversal_bps` point [lo, hi] | −2.842 [−14.974, +10.366] | −2.420 [−11.810, +5.938] | — |
| buy point [lo, hi]（n） | +11.878 [−0.125, +26.424]（76 420） | +10.344 [+0.543, +20.504]（76 452） | — |
| sell point [lo, hi]（n） | −18.637 [−34.491, −4.709]（175 258） | −16.115 [−29.427, −4.408]（175 292） | — |
| n / n_months | 251 678 / 72 | 251 744 / 72 | 1474 日序列 |
| 口径相对差 | — | point 14.8% / buy 12.9% / sell 13.5%（≤50% → U-1 自动通过） | — |

> **解读纪律**：C1/C2 同号为负且量级接近，说明「交易后次日整体仍小幅不利回落」；但 95% CI 均跨 0，**不得**据此声称反转显著。买卖不对称（buy 为正、sell 为负）与「卖出后价格继续下跌」一致，属方向性证据而非成本接入依据（口径 A）。
> **勘误 E-2**：本节「39 月」为分钟层覆盖；证据层锚定月频形成日全集，实测 73 个形成月（72 个有效聚类）。

### 3.6 影响面与不变量

**允许变化（仅证据层）**

- `out/v3100_calibration.json` 的 `temporary_share`、`temporary_basis`、新增 `reversal_bps` / `reversal_price_basis` / `temporary_proxy_ar1`；
- `evidence_warnings` 中旧代理文案（真实现路径改为「截面 T+1 反转，证据层，不进入容量」）；
- 校准 JSON 的 `panels.temporary` 摘要（不挂原始数组，避免工件膨胀）。

**必须逐位不变**

1. 默认 `out/capacity_impact.json` SHA `82728CE1…`；
2. `panel_hash`（payload 不含 `temporary`，F-9；[panels.py L424-440](file:///f:/Coding/factor_pipeline/backtest/execution/shell/panels.py#L424-L440)）；
3. `cost_by_h`、`net(h)`、`rho`、`alpha0`、`alpha0_anchored`、`impact_fit`、`c`、`capacity`；
4. `core/decay.py` 零改动，`__all__` 5 项；
5. Python 3.9、零新增依赖。

**消费隔离（为什么改 `temporary` 不会碰到成本）**：`cost_by_h` 只依赖 `aum_ref`、`turnover_m`、`FEE_BPS`、`impact_bps`（[panels.py L621-652](file:///f:/Coding/factor_pipeline/backtest/execution/shell/panels.py#L621-L652)）；`runner` 的 `net` 只消费 `panels['alpha0']`、`aum`、`rho`、`panels['cost_by_h']`（[runner.py L557-564](file:///f:/Coding/factor_pipeline/backtest/execution/shell/runner.py#L557-L564)）；`temporary_share` 只在 result 顶层落盘，**无任何下游函数读取它**（全仓 grep 仅定义/装配/测试）。因此新增 `reversal_bps` 不会进入成本或容量路径。Step 9 仍以 B-3 逐位对比兜底。

**测试影响**

- 既有 `test_temporary_basis_flagged`（[test_minute_panels.py L630-635](file:///f:/Coding/factor_pipeline/tests/test_minute_panels.py#L630-L635)）走最小面板 → 回退旧代理，语义不变；
- 既有 `test_runner_reports_c_gate`（[test_execution_capacity.py L171-190](file:///f:/Coding/factor_pipeline/tests/test_execution_capacity.py#L171-L190)）手工注入 `temporary_basis` → 透传不变；
- 新增用例见 §6.6；基线从 2065 起，新增 N 例后应为 `2065+N passed / 15 skipped / 0 failed`。

### 3.7 数据可得性核查

| 输入 | 来源 | 频率 | 缺口 |
|------|------|------|------|
| 月频权重 `w` | `make_weights` 返回值 | 月末 | 无 |
| `Δw` / `s` / `a` | `month_trades` 同款 `w − w.shift(1)` | 月末 | 无 |
| 日频复权收盘 `adj_price` | `build_panels` → `P['adj_price']` | 日频 | 无 |
| 日频 open | `market_data/stock_open.pkl` | 日频 | 未接入 `P`，C2 需在 `build_panels` 补 `open_adj` |
| 停牌 / ST / 涨停 | `load_implementability` → `facts`（日频） | 日频 | `P` 只返回形成日快照，C1 过滤 t+1 需补日频字段 |
| 跌停 | **无** | 日频 | 需按涨停同款镜像计算（F-4 / U-2） |
| 分钟 `ret_day` | `MinuteDayAggregate.ret_day` | 股票×日 | 可作 C2 第二源；需按日期/代码映射 |
| 成交量/额 | `stock_volume.pkl` / `stock_amount.pkl` | 日频 | 单位未校准，C3 暂缓 |

### 3.8 外部文献（沿用上游，不新增）

上游 [RESEARCH_P003_P007_DECISIONS.md](../../docs/research/RESEARCH_P003_P007_DECISIONS.md) 已完成两路独立检索与项目内实核，本批直接沿用以下结论，不重复检索、不新增未核验题录：

- 反转 ≡ 临时冲击的度量，与价差/冲击叠加会重复计价（Almgren & Chriss 2001；Almgren et al. 2005；Huang & Stoll 1996；Glosten & Harris 1988；Roll 1984）；
- A 股 close-to-close 反转被 T+1 隔夜折价污染（《金融研究》2025；深交所研究）；
- 业界主流回测框架无「反转」成本项（Qlib / Zipline / vnpy / AQR）。

本批新增的只是**工程契约**，不是新的外部事实；因此 §5.1 的文献验证表按「上游已核验 + 本批未新增」登记。

---

## 4. 综合分析

### 4.1 关键发现总结

1. 现状代理的根因不是「公式写错」，而是**样本单位错**：组合日收益序列不是交易事件，无法识别交易诱发回落。[置信度 ★★★★★，E3]
2. 真实现所需数据在仓内基本齐备；最大缺口是**跌停标记**与**日频 t+1 过滤字段**，均可在脚本层补，不需改 `core/decay.py`。[★★★★★，E3]
3. 截面 demean 是剥离 T+1 隔夜折价的最低成本手段；盘中口径 C2 是最强对照，但会改变「反转窗口」语义，宜作稳健性而非主口径。[★★★★☆，E3 + 上游 E1]
4. 改口径**不影响** `cost_by_h` / `net` / `panel_hash` / 默认 SHA；变更面集中在 `panels.py` / `runner.py` 与脚本注入，属可逆的 Type-2 证据层改动。[★★★★★，E3]
5. 事件级重采样会低估区间；必须按形成日聚类 bootstrap。[★★★★★，统计常识 + 39 个月结构]

### 4.2 技术 landscape

| 方案 | 主口径价格 | 隔夜处理 | 数据成本 | 结论 |
|------|-----------|---------|---------|------|
| C1 截面 close-to-close | `adj close_t → close_{t+1}` | 截面 demean 去共同项 | 低（现有） | **推荐主口径** |
| C2 截面盘中 | `open→close` on t / t+1 | 完全剔除 | 中（补 `open_adj` 或分钟） | **稳健性对照** |
| C3 VWAP-to-VWAP | `amount/volume` | 截面 demean | 高（单位校准） | 暂缓 |

### 4.3 研究空白（必须实测）

- 39 月 C1 与 C2 的 `reversal_bps` / `share` 差异（决定主口径是否成立，U-1）；
- 买卖分侧的符号与量级（U-4）；
- 聚类 bootstrap 在 39 个 cluster 下的区间稳定性（U-3）；
- 剔除首期建仓后的敏感性；
- 新读数与旧代理 `[0, 0, 0.004225]` 的对照（验收②）。

---

## 5. 幻觉抑制审查（Step 2 前置自审）

### 5.1 文献验证

| 引用 | ID/URL | 验证方式 | 状态 |
|------|--------|---------|------|
| Almgren & Chriss (2001) | DOI 10.21314/JOR.2001.041 | 上游调研已核验；本批未重新解析 | 沿用（非本批 ✅） |
| Almgren et al. (2005) | 上游调研 URL | 同上 | 沿用 |
| Huang & Stoll (1996) | DOI 10.1016/0304-405X(95)00867-E | 同上 | 沿用 |
| Glosten & Harris (1988) | DOI 10.1016/0304-405X(88)90041-4 | 同上 | 沿用 |
| Roll (1984) | DOI 10.1111/j.1540-6261.1984.tb03897.x | 同上 | 沿用 |
| 《金融研究》2025 T+1 折价 | <http://www.jryj.org.cn/CN/Y2025/V535/I1/170> | 同上 | 沿用 |

> 本批**没有新增外部引用**；上表用于标明理论依据的出处，不作为本批新结论的独立证据。若 Step 2 复审要求原文化核，需另开检索轮次（不阻断本批契约设计）。

### 5.2 技术声明验证

| 声明 | 来源 | 状态 |
|------|------|------|
| 现有 `temporary` 由 `excess_d` 的 t/t+1 构造 | panels.py L550-554 | ✅ 已验证 |
| 权重为月频、日频收益来自持仓 | verify_capacity_impact.py L153-163、L212-268 | ✅ 已验证 |
| `temporary_share` 为 `-cov/var` + bootstrap | impact.py L193-227 | ✅ 已验证 |
| `load_implementability` 无 `limit_down` | verify_long_side_research.py L97-114 | ✅ 已验证 |
| `adj_price = close × adj` | verify_capacity_impact.py L89 | ✅ 已验证 |
| 分钟 `ret_day = close_last/open_first − 1` | loaders.py L228-245 | ✅ 已验证 |
| `report.py` 不渲染 `temporary_share` | report.py L109-141 | ✅ 已验证 |
| 默认路径不含 `temporary_share` | 默认 JSON 顶层键 + v3.9.2 AUDIT §G3 | ✅ 已验证（E1） |
| `panel_hash` 不含 `temporary` | panels.py 键域 | ✅ 已验证（E3，Step 9 二核） |
| 39 月现有读数 `[0,0,0.004225]` | v394_calibration.json L363889-363893 | ✅ 已验证（E1） |

### 5.3 待修正项

- [ ] 日频 `open` 未接入 `P`；C2 需在 `build_panels` 补 `open_adj`（Step 9，若 C2 入选）。
- [x] `limit_down` 未实现 → 已转 U-2 + §3.4「验收前置」，Step 9 必须补齐或显式退化披露。
- [x] `P['facts']` 是形成日快照 → DESIGN 必须定「日频过滤字段」的层位（脚本注入 vs `P` 扩展）。
- [ ] C1/C2 的 39 月实测差异未知；U-1 保留，不得在 Step 9 前预设结论。

---

## 6. 对设计的输入

### 6.1 推荐方案

| 项 | 推荐 | 备选（需在 DESIGN 记被拒理由） |
|----|------|--------------------------------|
| 主口径 | C1 截面 close-to-close + 截面 demean | C2 盘中；C3 VWAP |
| 统计量 | 加权 `reversal_bps` + 加权 `share`，按形成日聚类 bootstrap | 事件级 bootstrap（低估区间，拒） |
| 架构 | 脚本计算事件样本 → `portfolio['reversal']` → `panels.build_daily_panels` 装配 → `runner` 计算/透传 | 在 `panels.py` 内直接读 pandas（违反分层，拒） |
| 兼容 | 无事件样本时回退旧代理 | 删除旧代理（破坏最小测试，拒） |
| 输出 | 保留 `temporary_share` 键，新增 `reversal_bps` / `temporary_proxy_ar1` | 改名（下游/文档连锁改动，拒） |
| 成本 | 不接入（口径 A） | 接入 `cost_by_h`（已被用户裁决否决） |

### 6.2 关键约束

1. 默认 SHA `82728CE1…` 逐位不变；
2. `panel_hash` 逐位不变；
3. `cost_by_h` / `net(h)` / `rho` / `alpha0` / `impact_fit` / `capacity` 逐位不变；
4. `core/decay.py` 零改动，`__all__` 5 项；
5. Python 3.9、零新增依赖；
6. 不重写 v3.9.4 verified 文档；本批新增 `spec/v3100-reversal-evidence/` 四件套；
7. 测试基线 `2065 + N`，0 failed。

### 6.3 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| C1 与 C2 分歧大 | 主口径不成立，需 Step 3 复议 | U-1；Step 9 先出双口径对照再定稿 |
| 39 个 cluster 太少 | CI 过宽/不稳定 | 报告 cluster 数与 CI；U-3 检查 seed/重复数稳定性 |
| 跌停标记缺失 | 卖出侧样本偏乐观 | U-2 镜像实现 + 单测；缺标记时披露 |
| t+1 过滤字段未接入 | 停牌/涨跌停污染 | DESIGN 明确层位；Step 9 抽查计数 |
| 事件样本含首期建仓 | 全买入、方向单边 | 打标 + 剔除首期敏感性 |
| 工件膨胀 | 校准 JSON 过大 | 只挂摘要，不挂 `rt/rt1/side/weight/month` 原始数组 |
| 旧测试语义漂移 | 回归噪声 | 兼容回退路径；只新增用例，不改旧断言 |

### 6.4 未决项登记（四元块）

- **U-1 主口径 C1 vs C2**
  - **判据**：39 月两口径的 `reversal_bps` / `share` 同号且量级差异 ≤50%，或分歧有书面裁决（C1 保留 / C2 替换）
  - **触发条件**：Step 9 首次 39 月校准产出双口径读数（机械可识别：`reversal_bps_c1` 与 `reversal_bps_c2` 同时非空）
  - **当前倾向**：C1 为主（与注册公式一致），C2 仅作稳健性；若 C1 被隔夜残差主导则改 C2
  - **证据等级**：待核（需 E1）

- **U-2 `limit_down` 镜像标记**
  - **判据**：卖出事件在跌停日的过滤计数非零且与 `limit_up` 对称；单测覆盖
  - **触发条件**：Step 9 实现日频过滤时
  - **当前倾向**：按 `raw_ret <= −(thr − 0.3) & close <= low × 1.001` 镜像实现（与涨停同款）
  - **证据等级**：E3（公式可推导，待实现验证）

- **U-3 聚类 bootstrap 稳定性**
  - **判据**：1000 / 2000 / 5000 reps 与 3 个 seed 下，`share` 区间端点差异 ≤0.01；point ∈ [lo, hi]
  - **触发条件**：Step 9 首跑
  - **当前倾向**：1000 reps、seed=20261121、按形成日 stationary block bootstrap
  - **证据等级**：待核（需 E1）

- **U-4 买卖不对称**
  - **判据**：`reversal_bps_buy` 与 `reversal_bps_sell` 的差异有 CI，且报告不强行合并
  - **触发条件**：Step 9 首跑产出分侧读数
  - **当前倾向**：分侧报告；合并值仅作总览；若卖出侧显著更大，披露 T+1 / 跌停不可卖的解释
  - **证据等级**：待核（需 E1）

- **U-5 截面基准选择**
  - **判据**：全市场等权 / 可投资域等权 / 事件样本等权 三者的 `reversal_bps` 差异 ≤10%
  - **触发条件**：Step 9 敏感性表
  - **当前倾向**：全市场等权（与 `daily_portfolio_excess` 的基准一致）
  - **证据等级**：E3

### 6.5 阻断性断言（B 类，Step 9 必须验证）

- **B-1** 默认 `out/capacity_impact.json` SHA `82728CE1…` 逐位不变；
- **B-2** `panel_hash` 改前/改后逐位相同；
- **B-3** `cost_by_h` / `net(h)` / `rho` / `alpha0` / `impact_fit` / `capacity` 逐位不变（可用 JSON 子对象对比）；
- **B-4** 新 `temporary_share` 在固定 seed 下两次运行逐位一致；point ∈ [lo, hi]；
- **B-5** 全量 `2065 + N passed / 15 skipped / 0 failed`；`core/decay.py` `__all__` 仍 5 项。

### 6.6 测试计划（T3100-1 ~ T3100-10）

| ID | 用例 | 覆盖 |
|----|------|------|
| T3100-1 | 合成买入 + 次日下跌 → `reversal_bps > 0`；次日上涨 → `< 0` | 符号 |
| T3100-2 | 合成卖出 + 次日上涨 → `reversal_bps > 0`；下跌 → `< 0` | 方向对称 |
| T3100-3 | 全市场 t+1 收益统一平移 +c → `reversal_bps` 不变 | 截面 demean |
| T3100-4 | `suspend_{t}` / `suspend_{t+1}` 样本被剔除，计数正确 | 停牌 |
| T3100-5 | 涨停买入 / 跌停卖出 / t+1 涨跌停样本被剔除 | 涨跌停 |
| T3100-6 | 首期建仓全为买入，`first_period` 标记与剔除敏感性 | 建仓 |
| T3100-7 | 除权日：`adj_price` 连续、raw price 跳变不产生假反转 | 除权 |
| T3100-8 | `x` 方差为 0 / 样本 <3 → `share=0` + warning，不崩 | 退化 |
| T3100-9 | 聚类 bootstrap：point ∈ [lo,hi]，固定 seed 可复现 | 区间 |
| T3100-10 | 无事件样本 → 回退旧代理，`temporary_basis="portfolio_ar1_proxy"` | 兼容 |

### 6.7 影响文件清单（预估）

| 文件 | 改动 |
|------|------|
| `scripts/verify_capacity_impact.py` | `build_panels` 补日频 `open_adj` / 日频 `suspend/st/limit_up/limit_down`（或等价字段）；`build_portfolio_panels` 生成 reversal 事件样本；`attach_panel_meta` 只挂摘要 |
| `scripts/verify_long_side_research.py` | 补 `limit_down` 镜像标记 |
| `backtest/execution/core/impact.py` | 新增 `cross_section_reversal(...)`（纯 numpy，事件加权 + 月份聚类 bootstrap） |
| `backtest/execution/shell/panels.py` | `build_daily_panels` 装配 `temporary` 真实现字段；旧代理保留为 `temporary_proxy_ar1`；warning 文案切换 |
| `backtest/execution/shell/runner.py` | 真实现分支调用新函数；输出 `reversal_bps` / `reversal_price_basis`；旧路径回退 |
| `tests/test_minute_panels.py` / `tests/test_execution_capacity.py` | 新增 T3100 用例；旧用例不改语义 |
| `tests/test_version_unification.py` 等 | 版本 3.10.0（4 处代码 + 2 处测试断言） |

---

## 7. 参考文献

**仓内**

1. [RESEARCH_P003_P007_DECISIONS.md](../../docs/research/RESEARCH_P003_P007_DECISIONS.md)（P-003/P-007 裁决前调研，§2 反转理论与 A 股证据）
2. [v3.9.4 CHECKLIST.md](../v394-audit-coverage-fix/CHECKLIST.md)（本批前置批次收口）
3. [SPEC_COMPLIANCE.md](../../docs/SPEC_COMPLIANCE.md)（Step 2 门禁 a-d、E-TODO 出口门禁）
4. 代码锚点：`backtest/execution/shell/panels.py`、`runner.py`、`core/impact.py`、`shell/loaders.py`、`scripts/verify_capacity_impact.py`、`scripts/verify_long_side_research.py`、`shell/report.py`

**外部（沿用上游，不新增）**

5. Almgren & Chriss (2001), DOI 10.21314/JOR.2001.041；Almgren et al. (2005)
6. Huang & Stoll (1996), DOI 10.1016/0304-405X(95)00867-E；Glosten & Harris (1988), DOI 10.1016/0304-405X(88)90041-4；Roll (1984), DOI 10.1111/j.1540-6261.1984.tb03897.x
7. 《金融研究》2025 T+1 隔夜折价 <http://www.jryj.org.cn/CN/Y2025/V535/I1/170>；深交所隔夜收益研究

---

## 8. 步骤 2 复审记录

> **复审方式**：独立上下文子代理（只读，不带主会话推理链），先读本文件与上游裁决调研，再逐条重放 E3 锚点；主会话仅做处置与回写。
> **独立性声明（RULE-4/5）**：子代理与撰写者**同基座**，非异构基座（本机无第二基座可用，沿用 D-001 降级）；但已做到**独立上下文、只读、不共享推理链**。按 v3.9.3/v3.9.4 惯例，Step 8 一致性复审仍由独立上下文执行，本节结论以该次复审为最终把关。
> **锚点基线**：commit `9b09f8c`（v3.9.4）；Step 9 改码前如行号漂移，以函数名 + 关键字复核。

### 8.1 复审结论

**PASS_WITH_FIXES** —— 无 P1 级事实错误；3 项 P1 为「Step 1 未实施」或「输出契约未写全」的步骤错位，处置后 2 项回写、1 项转 Step 9 验收前置；2 项 P2 为复核者漏读 §3.5/§3.6，已补显式说明。

### 8.2 复审发现与处置

| # | 级别 | 复审发现 | 处置 |
|---|---|---|---|
| F-1 | P1 | 「当前代码仍生成旧 `temporary_share`，未体现新真实现输出契约」 | **步骤错位**：Step 1-2 只出契约，不改码；已在 §3.1/§3.6 明确「当前=旧代理、目标=本契约、实施在 Step 5/9」，并补「消费隔离」段 |
| F-2 | P1 | `reversal_bps` 未定义 CI/point，与 `temporary_share` 三元组兼容性未说明 | **采纳**：§3.3.3 补「同一组月份重抽样、`{point, lo, hi}`、退化态」；§3.3.4 补输出形态 |
| F-3 | P1 | `limit_down` 缺失，与验收③「涨跌停边界单测」冲突 | **采纳**：§3.4 增「验收前置」——Step 9 必须实现镜像标记或显式退化披露，否则不得 accepted；T3100-5 覆盖卖出侧 |
| F-4 | P2 | 差异对照未填新读数 | **不采纳**：§3.5 已写「Step 9 前不得填写新读数」；Step 2 填数会构成编造 |
| F-5 | P2 | 「必须不变」清单不完整 | **部分采纳**：§3.6 原已列 5 项；补「消费隔离」段并显式说明新键不写入成本/容量 |

**复审期间自查到的真实锚点错误**：F-9 原引 `panels.py L403-419`，实为 `_coverage` 尾部；`_panel_hash` 实际位于 **L424-440**，已更正（§3.0/§3.6 两处）。该错误由处置阶段逐行重放发现，说明复审者的 E3 重放并不充分，Step 9 仍需独立复核。

### 8.3 锚点重放（主会话处置阶段）

| # | 声明 | 重放结果 |
|---|---|---|
| 1 | `temporary` 由 `excess_d` t/t+1 构造 | panels.py L550-558 ✅ |
| 2 | runner 调用 `temporary_share` | runner.py L523-528 ✅ |
| 3 | `temporary_share` 为 `-cov/var` + bootstrap | impact.py L193-227 ✅ |
| 4 | 组合日超额构造 | verify_capacity_impact.py L153-163 ✅ |
| 5 | `build_portfolio_panels` 月频权重/日频超额 | verify_capacity_impact.py L212-268 ✅ |
| 6 | `load_implementability` 无 `limit_down` | verify_long_side_research.py L97-114 ✅ |
| 7 | `panel_hash` 不含 `temporary` | panels.py L424-440 ✅（原引 L403-419 错误，已更正） |
| 8 | `report.py` 不渲染 `temporary_share` | report.py L109-141 ✅ |
| 9 | 39 月读数 `[0,0,0.004225]` | v394_calibration.json L363889-363893 ✅（E1） |
| 10 | `MinuteDayAggregate.ret_day` 为盘中 | loaders.py L228-245 ✅ |

### 8.4 Step 2 清单 + 门禁 a-d

**清单**：
- [x] 所有 arXiv/DOI 已验证 — **N/A**（本批不新增外部引用；沿用上游，§5.1 已标「沿用」而非 ✅）
- [x] 作者/年份/标题已验证 — **N/A**（同上）
- [x] 技术声明有文献/代码支撑 — 10 条 E3 锚点全部重放通过（§8.3）
- [x] 无未标注推测 — C1/C2 差异、新读数、bootstrap 稳定性均标「待 E1」并落 U-1~U-5
- [x] 置信度标注完整 — §4.1 五条均带 ★ 级

**门禁**：
- [x] **(a) FALSIFIED 断言已改写并记入修订记录** — 无既有断言被证伪；「改序列即可得 T+1 反转」的前序隐含假设在 §3.2 被证伪，并改写为事件级契约。
- [x] **(b) CONFLICT / STEP_GAP_OPEN 已仲裁** — 注册公式（close-to-close）与上游「trade-to-trade/隔夜剥离」的口径冲突，已仲裁为 **C1 主 + C2 稳健性 + U-1 实测裁决**；不遗留 OPEN。
- [x] **(c) 阻断性断言双源满足** — B-1/B-2 已有 v3.9.4 E1 双源；B-3/B-4/B-5 当前仅 E3 静态 → 标 **[单源-待二核]**，第二源为 Step 9 实测（不阻断 Step 3）。
- [x] **(d) 假设区条目已显式携带** — U-1~U-5 四元块齐备，触发条件可机械识别；C1/C2 选择以 [待定] 随 U-1 进入 DESIGN。

### 8.5 契约取证字段（F1-F5）

| 字段 | 状态 | 说明 |
|---|---|---|
| F1 来源日期 | 出具（沿用） | 外部文献日期以上游调研为准；本批未新增 |
| F2 来源版本 | 出具 | 仓内文档标版本 + 行号 @9b09f8c；外部标 DOI/URL |
| F3 降级链 | 出具（无降级） | 本批未调用外部检索，理由见 §2.1；非通道失败 |
| F4 引用验证表 | 出具（沿用） | §5.1 六条，均标「上游已核验；本批未重新解析」，未冒充 ✅ |
| F5 先失败记录 | N/A + 理由 | Step 9 才触发红→绿；届时两读数块留痕 |

### 8.6 结论

**PASS_WITH_FIXES → v1.1 verified**。F-2/F-3 已回写；F-1/F-4/F-5 已说明或转 Step 9 前置；锚点错误已更正。允许进入 **Step 3（DESIGN）**，但 DESIGN 必须显式承接：U-1（C1/C2 主口径）、U-2（`limit_down` 验收前置）、U-3（bootstrap 稳定性）、U-4（买卖分侧）、U-5（截面基准）。

### 8.7 异构复审记录（v1.2 增补，2026-11-21）

> **触发**：用户指令「执行异构复审」。撰写者（本文件 v1.0-1.1）与复审者为**不同基座模型**（复审者 GLM-5.3 独立上下文只读子代理，不带撰写推理链）——本次构成**真异构复审**，D-001「同基座降级」声明在本文件上不再适用（后续批次文档仍按实际基座情况声明）。
> **方式**：先通读本文件与上游裁决调研，再逐条重放 E3 锚点（12 组，含 §8.3 十组之外的 `FEE_BPS` 与 runner JSON 写入两处）；数据可得性由主会话 Glob 复核（复审子代理沙箱不可达 E 盘）。

**结论**：**PASS_WITH_FIXES**（无 P1；2×P2 + 2×P3，处置后全部关闭）。

**门禁 a-d 复核**：

- **(a) 锚点：过** —— 12/12 一致（行号微漂移、语义逐字一致；`cost_by_h` 公式、`load_implementability`、`report.py` 渲染段等均实读核对）；
- **(b) 口径：过** —— C1 主 + C2 稳健性 + U-1 实测裁决的仲裁结构完整；`cost_by_h`（panels.py L647-652）确不依赖 `temporary_share` / `reversal_bps`；
- **(c) 数据：过** —— 复审子代理 Glob 不可达 E 盘（沙箱限制），主会话复核 `E:\Ashare_data\market_data\` 下 `stock_open/low/close/high.pkl` **四文件全部存在**；§3.7 数据表结论维持；
- **(d) 隔离：过** —— `temporary_share` 仅 result 顶层落盘、无下游读取方；`net` 只消费 `alpha0/aum/rho/cost_by_h`。

**发现与处置**：

| # | 级别 | 异构复审发现 | 处置 |
|---|---|---|---|
| H-1 | P2 | `temporary_share` 写入校准 JSON 但 Markdown 报告不渲染，文档应显式区分两通道 | **已涵盖、无需增补**：§3.6 消费隔离段已写「只在 result 顶层落盘、无任何下游函数读取」+ §8.3 #8（report.py L109-141 不渲染）；异构复审实读两锚点后确认区分成立 |
| H-2 | P2 | `load_implementability` 无 `limit_down`，卖出侧过滤缺失 | **重合确认**：与 §8.2 F-3 / §3.4 验收前置 / U-2 同一事项，Step 9 镜像或退化披露前置不变；T3100-5 覆盖不变 |
| H-3 | P3 | `stock_open.pkl` / `stock_low.pkl` 在复审沙箱未找到，C2 / limit_down 数据可得性存疑 | **沙箱假阴性，已关闭**：主会话 Glob 实核四文件（open/low/close/high）全部存在；§3.7 无需修改 |
| H-4 | P3 | E3 锚点行号依赖 commit `9b09f8c`，改码后可能漂移 | **已覆盖**：§8 头部「锚点基线」已登记 commit +「Step 9 改码前以函数名 + 关键字复核」纪律；本次异构重放未发现漂移 |

**锚点重放（12/12 一致）**：`FEE_BPS=10`（panels.py L33）；`_panel_hash` payload 约 10 键不含 temporary（L424-440）；temporary 旧代理构造 + warning（L550-558）；`cost_by_h` 公式（L647-652）；runner 调用 `temporary_share`（L523-528）；runner 写入 result（L598-599）；`temporary_share` = `-cov/var` clip + seed 20261118（impact.py L193-227）；`daily_portfolio_excess`（verify_capacity_impact.py L153-163）；`build_portfolio_panels`（L212-268）；`load_implementability` 仅 limit_up（verify_long_side_research.py L74-114）；`ret_day` 盘中口径（loaders.py L228-245）；Markdown 只渲染 decay/cost/net/warnings（report.py L109-141）。

**对 §8.1-8.6 既有（同基座）复审记录的复核意见**：既有 PASS_WITH_FIXES 结论**维持**；F-1（步骤错位说明）、F-2（CI 形态回写）、F-3（`limit_down` 前置）、F-4（不填数纪律）、F-5（不变量清单）的处置均合理且经本次独立重放验证落地；F-9 锚点更正（`_panel_hash` 实位于 L424-440）再次确认。既有记录「复审者 E3 重放不充分」的自我披露与本次全量重放结果一致，进一步支持「Step 9 仍需独立复核」的纪律。

**v1.2 结论**：真异构复审通过（PASS_WITH_FIXES，4 项发现全部关闭，门禁 a-d 复核通过）；v1.1 的「允许进入 Step 3（DESIGN）」结论**维持不变**，DESIGN 仍必须显式承接 U-1~U-5（含 U-2 `limit_down` 验收前置）。
