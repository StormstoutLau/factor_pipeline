# v3.9.2 调研 — 真实校准读数诊断（c / rho / temporary 三项裁决）

---
id: v392-calibration-unit-fix-RESEARCH
type: design
version: 1.1
status: verified
date: 2026-11-20
depends: []
upstream: null
---

> **版本**: v1.1 (2026-11-20；v1.0→v1.1：步骤 2 复审修正 5 类锚点/算术/口径问题，见 §9)
> **批次**: v3.9.2（已登记：`PROJECT_STATUS.md §1` 路线图 + `docs/PROGRESS.md`）
> **上游依据**:
> [RESEARCH_V3.8.0_EXECUTION_CAPACITY.md](../../docs/research/RESEARCH_V3.8.0_EXECUTION_CAPACITY.md)（§3.1 平方根律 / §4.1 回归口径 / §7 T+1 reversal / §5 R1-R8，均经 §19 复审）、
> [RESEARCH_V3.8.1_MINUTE_PANEL_WIRING.md](../../docs/research/RESEARCH_V3.8.1_MINUTE_PANEL_WIRING.md)（§6 U3/U4/U5/U12 未裁决项，v1.2）、
> [DESIGN_EXECUTION_CAPACITY_V3.8.0.md](../../docs/private/DESIGN_EXECUTION_CAPACITY_V3.8.0.md) §5.1 / §7 / §10（σ_d、rho 日频、net(h)）、
> [EXECUTION_V3.8.0_EXECUTION_CAPACITY.md](../../docs/EXECUTION_V3.8.0_EXECUTION_CAPACITY.md) §2.4 / §2.5 / §2.8
> **调研工具**: 仓库读码（Read / Grep）+ 校准工件重放（Python 直读 `out/v381_audit_calibration.json`，2026-11-20）；
> **不新增外部学术检索**——三项读数全部落在既有模型族内（sqrt 冲击 / AR(1) 衰减 / T+1 reversal），
> 口径依据已在 v3.8.0 经 §19 异构复审；重复检索只会制造版本分叉（沿用 v3.8.1 先例，见其 §2 说明）
> **实测证据**: [out/v381_audit_calibration.json](../../out/v381_audit_calibration.json) /
> [out/v381_audit_calibration.md](../../out/v381_audit_calibration.md)（v3.8.1 步骤 10 审计独立复跑，39 月、最终代码）
> **范围**: 只裁决 `c_calib_point=15.07`、`decay.rho=-0.147`、`temporary_share≈0.4%` 三个读数**属于哪一类问题**，
> 以及为后续设计给出最小修复边界；**不实施**（实施归步骤 9）

---

## §1 调研问题清单

| # | 问题 | 结论落点 |
|---|------|---------|
| Q1 | `c_calib_point=15.07`（默认 0.5）是数据口径问题还是实现问题？ | §4.1 / B1 |
| Q2 | `rho=-0.147` 且 `retention(5)<0`，根因是估计频率、符号守卫还是数据？ | §4.2 / B2 |
| Q3 | `temporary_share=[0, 0, 0.0042]` 是否可解释为「临时冲击占比」？ | §4.3 / B3 |
| Q4 | `net(h)` 全为负（≈ `-cost(h)`）与研究报告 exQ1 净超额 +2.39% 的冲突如何归因？ | §4.4 / B4 |
| Q5 | 三项读数中哪些必须改代码，哪些只需口径说明/降级标注？ | §5 / B5 |
| Q6 | 修复是否会改变默认 `out/capacity_impact.json`（SHA `82728CE1…`）？ | §5.4 / B6 |
| Q7 | 最小修复白名单、版本档位与测试边界？ | §5.3 / B7 |
| Q8 | 修复后仍不可识别的部分如何处理（不得伪精确）？ | §5.2 / B8 |

---

## §2 判定依据（复用已复审口径，不新增学术主张）

| 口径 | 原文位置 | 对本次裁决的约束 |
|------|----------|-----------------|
| `sqrt` 冲击：`frac = c · σ_d · p^0.5`，输出为**价格比率** | DESIGN §5.1（L222） | `c` 无量纲；σ 必须是**日收益波动**，与 y 同尺度 |
| 选型样本：`股票×月` 的 `(p, impact, σ)`，按时间切折 | DESIGN §5.2（L237-243）〔P-010 v3.9.8 勘误：该节不存在；实际为 DESIGN §1.2 L38 非目标 + EXECUTION_V3.8.0 L219 docstring〕 | 当前实现按「股票×日」取样，属粒度偏差（B9） |
| `sigma` clip `[0.005, 0.20]` | DESIGN §5.1（L231） | clip 不得替代真实尺度；下界截断会使 c 二次膨胀 |
| `rho`：AR(1)，**IC 序列或组合收益序列，日频** | DESIGN §7（L330-340） | 月频序列 → 日频 `rho**h` 属单位错配 |
| `retention(h)=rho**h`，`h` 为**交易日**；CI 覆盖 1 → 1.0 | DESIGN §7 / §10（L334、L498、L518） | 设计未覆盖 `rho<=0`，属规则缺口 |
| T+1 reversal：`reversal_bps = −s·(P_{t+1}−P_t)/P_t` | RESEARCH_V3.8.0 §7（L191-194） | 需要**交易方向 s** 与**截面价格**；组合收益 AR(1) 不等价 |
| 临时冲击只影响容量假设，不进入默认输出 | DESIGN §10 / EXECUTION §2.8 | 允许标注降级，不允许伪精确 |
| `net(h)=aum·alpha0·rho**h − cost(h,D)` | DESIGN §10.2（L498-500） | 三项读数经此式共同决定业务结论 |

---

## §3 读数复算（E1：工件与代码可原样重放）

### 3.1 三个读数与代码落点

| 读数 | 值 | 生产代码 | 消费代码 |
|------|----|---------|---------|
| `c_calib_point` | 15.0677（CI 15.0027–15.1261） | [panels.py `_month_lambda`](../../backtest/execution/shell/panels.py#L283-L324) 构造样本；[SqrtImpact.fit](../../backtest/execution/core/impact.py#L59-L68) 过原点 OLS | [runner.py L208-L245](../../backtest/execution/shell/runner.py#L208-L245) 拟合 + bootstrap；容量经 `impact_fit` 进入 [build_daily_panels L555-L575](../../backtest/execution/shell/panels.py#L555-L575) |
| `decay.rho` | -0.1470（CI -0.3398–0.0457） | [panels.py L516-L523](../../backtest/execution/shell/panels.py#L516-L523) 传入 `excess_m`；[estimate_rho](../../backtest/execution/core/decay.py#L15-L44) | [runner.py L281-L285](../../backtest/execution/shell/runner.py#L281-L285) → `retention` / `net_curve` |
| `temporary_share` | `[0.0, 0.0, 0.004225]` | [panels.py L510-L514](../../backtest/execution/shell/panels.py#L510-L514) 构造 `(r1, rev1)`；[temporary_share](../../backtest/execution/core/impact.py#L174-L207) | 报告字段，未进入容量 |

### 3.2 `c` 的尺度反推（E1，可逐位复算）

- `impact_curve` 在 `p=1%` 处为 **75.3383 bps**，反解
  `σ_ref = 75.3383e-4 / (15.067658 × sqrt(0.01)) = 0.005000` → 恰为 `sigma_clip` **下界**；
- 即进入拟合的 σ 中位数 ≤ 0.005，被下界截断。σ 的来源是
  [loaders.py L256-L262](../../backtest/execution/shell/loaders.py#L256-L262) 对**全月分钟收益**求方差（`r2sum/rsum/n`），
  量级是**单根 bar 的波动**，不是日收益波动；
- 拟合式为 `c = Σ(xy)/Σx²`，其中 `x = σ_bar·sqrt(p)`、`y = |ret_day|`（[panels.py L320-L323](../../backtest/execution/shell/panels.py#L320-L323)），
  故 `c ≈ E[y] / E_w[x]`，是把「日收益绝对值的噪声底」折算成 `1/(σ_bar·sqrt(p))` 的**尺度换算系数**；
- `sqrt(240) ≈ 15.49`，与 `c=15.07` 同量级（比值 0.97），与「日尺度 / 分钟尺度」的 `sqrt(bar 数)` 解释一致（E3 推断）。

### 3.3 `rho` 的序列与统计量（E1）

- `excess_m` = 月频组合超额（39 个点），`estimate_rho` 对相邻月做去均值 AR(1)：
  `rho = Σ(x0·x1)/Σx0² = -0.1470`；
- HAC SE 由 CI 反解 `(0.0457+0.3398)/(2×1.96) ≈ 0.0983`，`t ≈ -1.50` → **与 0 不可区分**，CI 覆盖 0、不覆盖 1；
- 代码仅处理「CI 覆盖 1 → 1.0」，未处理「点估计 ≤ 0」；`retention(5)=(-0.147)^5=-6.9e-5`，
  奇数 h 为负、偶数 h 趋 0 —— 这是**符号翻转**，不是「无衰减」。

### 3.4 `temporary` 的实际构造（E1）

```python
r1  = ex_d[:-1]      # 组合日超额，前一日起
rev1 = ex_d[1:]      # 组合日超额，次日起
share = clip(-cov(r1, rev1) / var(r1), 0, 1)   # 即 clip(-AR(1), 0, 1)
```

这是**组合日超额收益的一阶自相关**，既没有交易方向 `s`，也不是截面「买入后次日反转」；
`0.4%` 只能读作「组合日收益近似无自相关」，不能读作「临时冲击占比 0.4%」。

### 3.5 `net(h)` 与成本（E1）

| h | cost(h) | alpha 项 `aum·alpha0·rho**h` | net(h) |
|---|---------|------------------------------|--------|
| 5 | 91,537,190 | ≈ -1,806 | -91,539,000 |
| 10 | 45,768,595 | ≈ +0.12 | -45,768,595 |
| 20 | 22,884,298 | ≈ 0 | -22,884,298 |

`cost(h) = (20/h)·aum·turnover·2·(FEE_BPS+impact_bps)/1e4`，三项恰为 2× 递减；
`p_cost` 中位落在 0.5%–1% 时，对应 `impact_bps` 为 53.3–75.3，冲击项占成本 **83%–88%**（费率为 10 bps）；
`p_cost` 与 `turnover` 的逐月真值不在校准 JSON 中，故只给区间，不反推单值。

---

## §4 三项裁决

### 4.1 `c=15.07`：**实现缺陷（σ 与 y 尺度不一致）+ 识别不足**，非纯数据限制

**证据链**

1. DESIGN §5.1 要求 `σ_d`（日收益波动），EXECUTION §2.4 的 loader 契约写「日内收益标准差」——**两份文档本身冲突**；
2. 实现取了分钟 bar 波动（中位被 clip 到 0.005），而 `y=|ret_day|` 是日收益 → `x` 与 `y` 相差约 `sqrt(bar 数)` 倍；
3. 过原点拟合把 `y` 的噪声底（日 |收益| 的无条件均值）整体折算进 `c`：即使把 σ 换成日频（0.02 量级），
   `c ≈ 15.07×0.005/0.02 ≈ 3.8`（E3 代数换算），仍远离设计默认 0.5，说明**仅修尺度不足以恢复可识别性**；
4. 样本粒度也与 DESIGN §5.2 不符：设计为「股票×月」，实现为「股票×日」最多 200,000 行，
   CV 按行顺序切折而非按月聚类（B9）。

**裁决**：`c=15.07` **不可作为冲击水平使用**；根因是实现层的尺度错误（可修），
叠加设计层的识别规则缺失（需补门槛）。数据限制（BVC 无逐笔方向）会进一步放大噪声，但不是主因。

**证据等级**：E1（σ=0.005 反解、代码锚点）+ E3（尺度换算与噪声底推断）。

### 4.2 `rho=-0.147`：**实现缺陷（频率错配 + 负值未守卫）**，并暴露文档链未裁决

**证据链**

1. DESIGN §7 明确「IC 序列或组合收益序列，**日频**」；实现传入 `excess_m`（月频）；
2. 该选择源自 v3.8.1 调研 §6 **U3**「建议组合月超额 AR(1)」，但 U3 从未在设计阶段裁决，
   与 DESIGN §7 冲突未被步骤 8 捕获（B10）；
3. 月频 `rho` 被直接代入「`h` 为交易日」的 `rho**h`，h=5/10/20 实际被解释为 5/10/20 **个月**；
4. 设计只规定「CI 覆盖 1 → 1.0」，未规定 `rho<=0`；实现照搬公式，产生负保留率与 `half_life=nan`。

**裁决**：属**实现/口径缺陷**，不是数据限制。正确做法是用日频组合超额（`excess_d`）估计；
并对 `rho<=0` 给出与「无显著衰减」一致的回退（`retention≡1`）与留痕。

**证据等级**：E1（代码/设计原文逐条对照）。

### 4.3 `temporary≈0.4%`：**口径说明（代理定义偏离设计）+ 数据限制**，非算术错误

**证据链**

1. 设计/调研要求 `−s·(P_{t+1}−P_t)/P_t` 的截面 T+1 反转，需要逐笔/日频交易方向；
2. 实现用组合日超额 AR(1) 替代，数学上正确（`clip(-AR1,0,1)`），但**测的不是同一对象**；
3. 现有 daily panels 只注入组合级 `excess_d`，没有股票级价格与方向，属**输入能力缺口**（B11）；
4. 0.4% 落在「组合日收益几乎无自相关」的合理区间，不能反推临时冲击很小。

**裁决**：本批不改算法；必须把该读数**降级标注**为「组合 AR(1) 代理，非 T+1 反转」，
并在报告中声明不进入容量。真正的截面实现列入后续批次（需要股票级输入契约扩展）。

**证据等级**：E1（代码）+ E2（读数区间复核）+ E4（截面实现能力缺失，未实现）。

### 4.4 `net(h)` 全负的业务冲突：**由 §4.1 + §4.2 传导**，非独立缺陷

- 当前 `net(h) ≈ −cost(h)`：rho 近 0 杀掉 alpha 项，c=15 把成本抬高约 2–4 倍；
- 若按 §4.1/§4.2 修复（σ 日频 + rho 日频/无衰减），在 `p_cost=1%` 下冲击约 10–40 bps、
  月成本约 5.4e6–1.3e7，`h=20` 的 `net` 转正（约 +1.3e7…+2.1e7），
  折 1.6%–2.5%/年，与研究报告 exQ1 净超额 **+2.39%** 同量级（E3 推断，待步骤 9 实测复核）；
- 因此业务冲突不是「策略不赚钱」，而是**校准读数的两个输入错误叠加**。

---

## §5 修复边界与方案候选（供步骤 3 设计）

### 5.1 候选方案

| 方案 | 内容 | 结论 |
|------|------|------|
| A | 仅文档说明，不改代码 | ❌ 否决：c=15 仍驱动成本/容量，业务读数继续失真 |
| **B** | **尺度修正 + 守卫 + 识别门槛 + 降级标注** | ✅ 推荐（最小、可测、默认路径不变） |
| C | 全面重估：股票×月聚类、带截距/符号冲击、截面 T+1 反转 | ❌ 本批不做：需要新输入契约与更长工期，拆为 v3.9.3+ |

### 5.2 方案 B 的四项动作

1. **σ 同尺度**：冲击样本的 σ 改为「该股当月日收益标准差」（由 `ret_day` 聚合，clip 保持 `[0.005,0.20]`）；
   分钟 bar σ 仅保留给 BVC 分类与 λ 诊断，不再进入 `impact_samples`；
2. **c 识别门槛**：为 `sqrt` 拟合输出过原点 `R²`（`1 − SSE/SST`）；
   若 `R² < 0.05` 或 `c ∉ [0.1, 2.0]` → 标 `c_identifiable=False`，
   成本/容量回退 `c_default=0.5`，`c_calib_*` 仅作 `[区间]` 诊断并写 `evidence_warnings`；
3. **rho 日频 + 非正守卫**：用 `excess_d` 估计 `rho`（`rho_series` 改日频并标 `rho_freq="daily"`）；
   若 `rho<=0` → 回退 `1.0` 并留痕「无正持续性，按无衰减处理」；
4. **temporary 降级标注**：保留数值，新增 `temporary_basis="portfolio_ar1_proxy"` 与
   `evidence_warnings`「非 T+1 反转，不进入容量」；容量计算不使用该字段（现状已如此）。

### 5.3 文件白名单（预估）

`backtest/execution/shell/panels.py`、`backtest/execution/shell/runner.py`、
`backtest/execution/core/impact.py`（仅 fit 返回 R²，不破端口签名）、
`backtest/execution/shell/report.py`（可选：展示降级标注）、
`tests/test_minute_panels.py`、`tests/test_execution_capacity.py`、版本 6 锚点、CHANGELOG/文档。

### 5.4 默认路径不变性

`out/capacity_impact.json` 仅含 `meta/results`，**无** `decay` / `temporary_share` / `impact_curve` 字段；
四项动作只作用于 `--calibrate` 面板路径。步骤 9 仍须重跑默认路径并核对 SHA256 `82728CE1…`（B6）。

---

## §6 数据限制与未核实项

| # | 项 | 影响 | 状态 |
|---|----|------|------|
| U1 | 分钟数据无逐笔方向，BVC 为代理 | 冲击样本的 `y` 含方向噪声 | 已知限制（DESIGN §0） |
| U2 | 分钟数据止于 2023-03-30 | 2023-04 之后只能 `[代理推断]` | 已知限制 |
| U3 | 日收益 `ret_day=close_last/open_first−1` 不含隔夜 | σ 与 `y` 都同日频、同口径，可接受 | 本批确认 |
| U4 | 组合日超额序列长度 | 日频 rho 的 HAC 带宽与自相关稳健性 | 步骤 9 实测（E1） |
| U5 | 修复后 c 是否落入可识别区间 | 决定容量是否回退默认 | 步骤 9 实测（E1），不预设 |
| U6 | 截面 T+1 reversal 的输入契约 | 本批不实现 | E4，后续批次 |

---

## §7 验收判据（进入步骤 3 的硬约束）

| # | 判据 |
|---|------|
| B1 | `impact_samples` 的 σ 与 `impact` 同为日频尺度；分钟 bar σ 不再进入样本 |
| B2 | `rho` 由日频组合超额估计，`rho_series` 标记 `daily`；`rho<=0` 回退 1.0 且 warnings 可查 |
| B3 | `temporary_share` 附 `temporary_basis` 与非 T+1 声明；容量不消费 |
| B4 | `net(h)` 在修复后不得出现符号翻转；h=20 与 exQ1 口径可对账 |
| B5 | 三类判定在 IMPLEMENTATION/CHECKLIST 中逐条可追溯 |
| B6 | 默认 `out/capacity_impact.json` SHA256 `82728CE1…` 逐位不变 |
| B7 | 文件白名单 + 版本 3.9.2 六锚点一致；Python 3.9 语法 |
| B8 | c 不可识别时明确回退默认，禁止伪精确 |
| B9 | 股票×日 vs 股票×月的粒度偏差必须显式登记（本批不修） |
| B10 | 文档链冲突（U3 vs DESIGN §7）在 v3.9.2 设计中正式裁决并留痕 |
| B11 | 截面 T+1 reversal 作为后续批次待办登记，不在本批伪实现 |

---

## §9 步骤 2 复审记录（v1.0 → v1.1，2026-11-20）

**复审方式**：对照 `out/v381_audit_calibration.json` 重放全部算式 + 逐条读码核对锚点（Read/Grep），
不引入新文献；判定边界按「代码行为是否偏离设计原文」而非「结果是否符合预期」。

### 9.1 复核通过项

| # | 项 | 复核结果 |
|---|----|---------|
| P1 | `σ_ref=0.005` 反解 | `75.3383e-4/(15.067658×0.1)=0.005000` ✅ |
| P2 | HAC SE / t | `(0.0457+0.3398)/3.92=0.0983`，`t=-1.50` ✅ |
| P3 | `net(h)` 三项 | `rho**5=-6.87e-5`，alpha≈-1,806；`rho**10`≈+0.12；cost 恰 2× 递减 ✅ |
| P4 | 锚点 | `panels.py` L283-324/L510-523/L555-575、`runner.py` L208-245/L281-285、`impact.py` L59-68/L174-207、`decay.py` L15-44、`loaders.py` L256-262 全部命中 ✅ |
| P5 | 默认路径隔离 | 脚本 L428 `if args.calibrate or args.diagnose_window` 才构造面板；默认 JSON 仅 `meta/results` ✅ |
| P6 | `temporary` 未入容量 | `runner.py` 仅 L325 输出该字段，容量分支不消费 ✅ |
| P7 | 设计原文 | DESIGN L222/L231/L330-340/L498-500 与 RESEARCH_V3.8.0 L191-194 引用一致 ✅ |

### 9.2 发现与修正

| # | 级别 | 发现 | 修正 |
|---|------|------|------|
| F1 | P3 | `panels.py` 链接写成 `../..//backtest`（双斜杠） | 改为 `../../backtest/...` |
| F2 | P3 | `rho**10` 的 alpha 项误写 +0.6 | 复算为 +0.12 |
| F3 | P2 | 用 `p_cost=1%` 单点断言「冲击占成本 88%」，但 `p_cost/turnover` 真值不在工件中 | 改为 0.5%–1% 对应 83%–88% 区间，声明不可反推单值 |
| F4 | P2 | 「成本抬高 3–7 倍」无直接证据 | 按 cost 区间复算改为 2–4 倍 |
| F5 | P3 | 年化区间重复且与单月混写 | 统一为 1.6%–2.5%/年 |

### 9.3 白名单复核

- 增补 `tests/test_minute_panels.py`（面板构造主测试）；
- `scripts/verify_capacity_impact.py` **不纳入**：`attach_panel_meta` L236-262 只透传 `sigma_median` 与
  `impact_fit`，σ 改口径后曲线自动重算，无需改脚本；
- 结论与 §4 三项裁决、§5 方案 B 不变；B1-B11 不变。

### 9.4 复审结论

**PASS_WITH_FIXES（已闭环）**。三项裁决维持：
`c` = 实现缺陷（尺度）+ 设计层识别规则缺失；`rho` = 实现缺陷（频率 + 负值守卫）；
`temporary` = 口径说明（代理偏离设计）+ 数据限制。进入步骤 3 设计。
