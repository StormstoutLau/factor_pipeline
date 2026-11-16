# 2026-11-16 代码质量审计 — v3.4.12 面板 HAC / Premium 标准误

> **审计对象**: `PremiumEstimator.estimate_with_errors` (逐期 OLS SE + λ̂(t) 局部 HAC SE + 均值 HAC SE/CI)
> **代码版本**: 3.4.12
> **审计依据**: [RESEARCH_PREMIUM_HAC_SE.md](../research/RESEARCH_PREMIUM_HAC_SE.md) /
> [EXECUTION_V3.4.12_PREMIUM_HAC_SE.md](../EXECUTION_V3.4.12_PREMIUM_HAC_SE.md) /
> [CHECKLIST_V3.4.12.md](CHECKLIST_V3.4.12.md) /
> [CONSISTENCY_REVIEW_V3.4.12.md](CONSISTENCY_REVIEW_V3.4.12.md)
> **审计方法**: audit-driven-development 4 阶段

## Phase 1 — Spec Inventory

| 工件 | 版本 | 状态 |
|------|------|------|
| RESEARCH_PREMIUM_HAC_SE.md | v1.0 | ✅ Q1-Q7 + 3 条 Crossref 引用 + F1-F9 |
| DESIGN_PREMIUM_HAC_SE.md (private) | v1.0 | ✅ G1-G9 + E1-E7 + 退化表 (步骤 8 修订 3 处) |
| EXECUTION_V3.4.12_PREMIUM_HAC_SE.md | v1.0 | ✅ 代码片段 + 退化口径 + 步骤 6 review |
| CHECKLIST_V3.4.12.md | v1.0 | ✅ A/B/C/D/E |
| CONSISTENCY_REVIEW_V3.4.12.md | v1.0 | ✅ PASS (4 项不一致已修复) |

## Phase 2 — Code vs Spec Audit

| 规格 | 代码证据 | 结论 |
|------|---------|------|
| G1 方法签名 | [factor_health/__init__.py L65-L68](../../modules/factor_health/__init__.py#L65-L68) | ✅ |
| G2 六个数组 | [L140-L146](../../modules/factor_health/__init__.py#L140-L146) | ✅ |
| G3 四个标量 | [L147-L150](../../modules/factor_health/__init__.py#L147-L150) | ✅ |
| G4 四个元信息 | [L151-L154](../../modules/factor_health/__init__.py#L151-L154) | ✅ |
| G5 `estimate` 数值不变 | [L48-L63](../../modules/factor_health/__init__.py#L48-L63); 平滑循环逐行迁入 [L157-L173](../../modules/factor_health/__init__.py#L157-L173) | ✅ |
| G6 逐期 OLS SE | [L208-L213](../../modules/factor_health/__init__.py#L208-L213) | ✅ |
| G7 λ̂(t) 局部 HAC SE | [L107-L126](../../modules/factor_health/__init__.py#L107-L126) | ✅ |
| G8 退化不抛异常 | [L108-L109](../../modules/factor_health/__init__.py#L108-L109), [L116-L117](../../modules/factor_health/__init__.py#L116-L117), [L128-L138](../../modules/factor_health/__init__.py#L128-L138) | ✅ |
| G9 `diagnose` / `BreakpointDetector` 零改动 | diff 仅 6 个 hunk, 全部位于 `PremiumEstimator` (L63-L240) | ✅ |

**关键口径核查**:
- 局部 SE = `sqrt(Ω_t · Σw²)`, `w` 为经 `_epanechnikov` 归一化后再按有效点过滤的实际权重;
- 全局 SE = `sqrt(Ω_β / n_valid)`, `Ω_β` 为 `beta_t` 有限值的 Newey-West 长期方差 (分母 n, Bartlett 核);
- `Ω<0 → NaN`, `Ω=0 → SE=0`, 有效点 `<3 → NaN`。

## Phase 3 — Defect Scan

| # | 候选问题 | 判定 | 处置 |
|---|---------|------|------|
| D1 | `_cross_sectional_betas` 改为调用带 SE 版本, `estimate()` 多算一次残差/SE | 只增 O(T·N) 算术, 保持单一实现避免双份公式漂移 | 接受 |
| D2 | 核权重在含 NaN 的窗口上归一化 (`Σw<1`), 局部 SE 未重新归一 | 与实际被估计的加权平均一致 (SE 描述该估计量本身) | 不改, 已在方法 docstring 声明近似 |
| D3 | `alpha` 未做 (0,1) 区间校验 | 公开 API 边界输入, 超界由 `norm.ppf` 返回 inf/nan; 与模块既有风格一致 | 记录, 不在本次范围 |
| D4 | `hac_lag` 仅报告全局带宽, 局部带宽可能不同 | 元信息字段语义已注明「全局/均值带宽」 | 已澄清 |
| D5 | `_hac_long_run_variance` 分母用 n 而非 n−lag | Newey-West 半正定估计量的标准写法, 与 `ledoit_wolf_hac_test` 同口径 | 正确 |
| D6 | 局部窗口 3 点时 Ω 噪声大 | 与 `estimate` 的窗口门槛一致; docstring 声明近似性质 | 接受 |

**Phase 3 结论**: 无 P0/P1; D3 为边界输入口径, D2/D6 为已声明的近似性质。

## Phase 4 — 测试与回归证据

| 项 | 结果 | 状态 |
|---|------|------|
| Red (E1-E7) | **7 failed** (AttributeError) | ✅ 复现 |
| Green (E1-E7) | **7 passed** | ✅ |
| E8/E9 (复审修正固化) | **2 passed** | ✅ |
| `tests/unit/test_layer3_factor_health.py` | **18 passed** (既有 9 + 新增 9) | ✅ |
| `tests/test_backtest` | **599 passed / 8 skipped** (与基线一致) | ✅ |
| 全量 `tests/` | **1755 passed / 15 skipped / 0 failed** (基线 1746 → +9) | ✅ |
| 版本统一 | **7 passed** + 手工 **6/6** | ✅ |
| Stata 对拍 + MC | 见 Phase 7.2 | ✅ |

> **过程记录**: 首次全量运行 (与版本锚点升级并行) 出现 1 failed —
> `test_06_pyproject_version_matches_package` 读到 `pyproject=3.4.12` 而进程内
> `__version__=3.4.11`, 属运行期间修改版本文件的竞态; 文件稳定后重跑版本测试
> 7 passed, 全量重跑 0 failed。

## Phase 5 — 自审

| # | 问题 | 结论 |
|---|------|------|
| S1 | `estimate()` 是否真的逐位不变? | 平滑循环原样迁移 (git diff 将其识别为未改动行块); E6 断言输出与 `lambda_hat` 全等 |
| S2 | `Ω·Σw²` 在独立同方差时是否退化为 `σ²Σw²`? | 是, 与 RESEARCH §4.2 推导一致 |
| S3 | 负 Ω 是否被静默截断为 0? | 否: 仅 `Ω≥0` 才写 SE; `Ω<0 → NaN` |
| S4 | 缺失期 λ̂ 与 SE 语义是否混淆? | 注入缺失期: `beta_t/beta_se=NaN`, λ̂ 与 λ̂ SE 由邻期平滑仍有限 — E5 已固化 |
| S5 | 14 个返回键与文档是否一致? | 与 EXECUTION §3.4 / CODE_WIKI §4.13 逐键一致 |
| S6 | 是否影响缓存代际? | 不涉及: 纯增量方法, 生产 `estimate` 路径未变 → `v2.3.0-cache` 不变 |

## Phase 6 — 审计结论 (初版)

**PASS**。改动为纯增量 API: `estimate()` / `diagnose()` / `BreakpointDetector` 数值与标签零变更;
公式与学术引用 (Fama & MacBeth 1973; Newey & West 1987/1994) 对齐; 退化口径完备且有测试覆盖;
Red→Green 可复现; 无 P0/P1 缺陷; 全量回归 0 failed。

## Phase 7 — 独立复审与外部验证 (2026-11-16, 提交前追加)

### 7.1 复审发现

| # | 发现 | 证据 | 处置 |
|---|------|------|------|
| F1 (P2) | `lambda_se` 的 Σw² 用未再归一化权重 ([L119](../../modules/factor_health/__init__.py#L119)), 与 `np.average` 实际权重 (sum=1) 不一致; 窗口含 NaN β 时 SE 低估 ×W_v | 数值演示: 20 期缺失面板, W_v=0.5629, 代码 SE 0.00389 vs 设计口径 0.00690 (低估 44%) | ✅ 已修复: `weights = weights / weights.sum()` (完整面板除以 1, 零影响); 新增 E8 |
| F2 (P3) | `min_stocks≤2` 时 `n_valid−2≤0` → σ̂² 除零 → `beta_se` NaN | 构造 N=2 面板复现 | ✅ 已修复: `/ max(n_valid−2, 1)`; 新增 E9 |
| F3 (信息) | `max_lag=0` 被静默提升为 1; `hac_lag` 仅报告全局带宽 | docstring 已注明 | 不改 |

### 7.2 Stata 18 对拍 ([scripts/verify_hac_stata.py](../../scripts/verify_hac_stata.py), StataMP 18, batch `/e do`)

| 层 | 验证目标 | Stata 命令 | 结果 |
|----|---------|-----------|------|
| L1 | premium_mean / premium_mean_se | `newey beta, lag(4)` → `_b/_se[_cons]` | 均值 EXACT (ratio 0.9999999972); SE ratio = √(200/199) = 1.0025094 |
| L2 | beta_se 全部 200 期 | `statsby by(t): regress r f` | EXACT (beta max dev 2.5e-7, se 6.9e-8 — CSV 往返精度内) |
| L3 | Ω_t (λ̂ SE 成分, 5 窗口) | `newey u, lag(q_local)` → SE²×n | 全部恰为 n/(n−1): 35/34、49/48×3、34/33 — 与 L1 同一约定差 |
| L4 | λ̂ SE 语义 | (无对应命令) Monte Carlo 400 reps | 固定 β 路径: premium SE/sd=2.11, λ̂ SE/sd=1.77 (**保守**); 随机 β 路径: 0.90 / 0.81 (总波动口径, 不用于覆盖解释) |

**约定差识别**: 所有 L1/L3 偏差精确等于 Stata `newey` 默认的小样本自由度修正
n/(n−k) (k=1 截距模型) — 剔除该常数因子后 Bartlett 核权重、1/n 自协方差归一化、
去均值、自动滞后规则与 Python 实现**逐位一致**。本实现保持 NW(1987) 原始渐近形式,
与仓内 `_newey_west_se` / `ledoit_wolf_hac_test` 同风格; 差异为 O(k/n) ≤ 0.5%,
已在 `_hac_long_run_variance` docstring 注明。

**L4 口径自纠**: 首版 MC 每轮重抽 β 真实路径, 经验 sd 混入参数漂移 (时变溢价本身),
据此记为「≈90% 覆盖」属口径错误。固定 β 路径 (只重抽横截面噪声) 后 SE/sd=2.11 (premium) /
1.77 (λ̂), (N,h) ∈ {50,100}×{12,24,36} 六组扫描 1.47–2.74 均 >1 → 当前 SE 对抽样误差**保守**,
不是不足。机制: `Ω_t` 来自残差 `u_s = β_s − λ̂_s`, 含 β 路径被平滑滤掉后的窗口内残余波动,
系统性大于纯抽样长期方差。因此不修改方差公式, 仅修正验证口径与文档 (详见 EXECUTION §9.3)。

### 7.3 Phase 7 结论

F1/F2 已修复并有测试固化 (E8/E9); HAC 引擎经 Stata 三层精确对拍确认;
λ̂ SE 对抽样误差保守 (SE/sd=1.77); Phase 6 的 PASS 维持, 附两项已声明限制
(Stata df 约定差 / CI 偏保守)。

## 最终审计结论

**PASS**。纯增量 API (`estimate` / `diagnose` / `BreakpointDetector` 零变更) +
复审修正 F1/F2 (均有测试固化); HAC 引擎经 Stata 18 三层对拍逐位一致
(唯一系统差 = Stata 的 n/(n−k) df 约定, 已声明); λ̂ SE 经固定 β 路径 MC 确认为保守
(SE/sd=1.77, 覆盖率 ≥95%); 全量回归 0 failed; 缓存代际不变。
