# CONSISTENCY REVIEW v3.4.12

> **review 时机**: 步骤 8 (步骤 7 checklist 完成后, 步骤 9 TDD 实现前)
> **review 对象**: [RESEARCH](../research/RESEARCH_PREMIUM_HAC_SE.md) / DESIGN (private) /
> [EXECUTION_V3.4.12_PREMIUM_HAC_SE.md](../EXECUTION_V3.4.12_PREMIUM_HAC_SE.md) /
> [CHECKLIST_V3.4.12.md](CHECKLIST_V3.4.12.md)

## §1 事实引用一致性

| 事实 | 文档 | 源代码 (现状) | 状态 |
|------|------|-------------|------|
| `estimate` 内联核平滑 | EXEC §2 F1/F4 | [factor_health/__init__.py L48-L78](../modules/factor_health/__init__.py#L48-L78) | ✅ 一致 |
| β_t 无残差 | EXEC §2 F2 | [L80-L108](../modules/factor_health/__init__.py#L80-L108) | ✅ 一致 |
| 归一化 Epanechnikov | EXEC §2 F3 | [L110-L115](../modules/factor_health/__init__.py#L110-L115) | ✅ 一致 |
| `_newey_west_se` 为 OLS bread | RESEARCH F5 / DESIGN §3.1 | [L489-L523](../modules/factor_health/__init__.py#L489-L523) | ✅ 一致 |
| `norm` 已导入 | EXEC §2 F6 | [L22](../modules/factor_health/__init__.py#L22) | ✅ 一致 |
| 现有测试只覆盖 `estimate` | RESEARCH F6 | [test_layer3_factor_health.py L66-L107](../tests/unit/test_layer3_factor_health.py#L66-L107) | ✅ 一致 |
| `min_stocks` 默认 30 | RESEARCH F8 | [L44-L46](../modules/factor_health/__init__.py#L44-L46) | ✅ 一致 |

## §2 接口签名一致性

| 接口 | 文档 | 目标签名 | 状态 |
|------|------|---------|------|
| `estimate_with_errors` | EXEC §3.4 | `(factor, forward_returns, alpha=0.05, max_lag=None) -> Dict` | ✅ |
| `_cross_sectional_betas` | EXEC §3.2 | 签名不变, 返回 `ndarray` | ✅ |
| `_cross_sectional_betas_and_se` | EXEC §3.2 | `(F, R) -> (beta_t, beta_se)` | ✅ |
| `_hac_long_run_variance` | EXEC §3.3 | `(x, max_lag) -> float` | ✅ |
| `_smooth_betas` | EXEC §3.1 | `(beta_t) -> ndarray` | ✅ |

## §3 验收标准一致性

| 验收项 | RESEARCH | DESIGN | EXECUTION | CHECKLIST | 状态 |
|-------|---------|--------|-----------|-----------|------|
| 逐期 OLS SE | §4.1 | G6 | §3.2 | A3/B4 | ✅ |
| λ̂(t) HAC SE | §4.2 | G7 | §3.4 | A7/B1 | ✅ |
| 均值 HAC SE | §4.3 | G3 | §3.4 | A8/B2 | ✅ |
| 缺失/退化 | §4.4 | G8 / §3.5 | §4 | A7/B5 | ✅ |
| CI 正态近似 | §4.5 | E1/E7 | §3.4 | B1/B7 | ✅ |
| 兼容性 | §4.6 | G5/G9 | §5 | A9/B6 | ✅ |

## §4 决策记录对齐

| 决策 | 依据 | 实施文档 | 状态 |
|-----|------|---------|------|
| 用局部 Ω 而非全局 Ω | DESIGN §3.2 | §3.4 | ✅ 对齐 |
| 不新增 ADR | 纯增量 API, 零行为变更; 方法学已在 DESIGN_DISCUSSION_V3.3.0 §2 | §1/§5 | ✅ 对齐 |
| 不为 CI 改 `diagnose` 标签 | RESEARCH §6 / DESIGN §6 | §5/§8 | ✅ 对齐 |
| 缺失口径与 v3.4.10/v3.4.11 一致 (有限值过滤) | 版本惯例 | §3.4/§4 | ✅ 对齐 |

## §5 不一致项修复

| # | 发现 | 修复 |
|---|------|------|
| I1 | DESIGN §3.2 原写局部 Ω 下限「有效点≥4」, 与 G8/§3.5 的「<3 → NaN」冲突 | 统一为 n≥3 计算、n<3 → NaN (与 `estimate` 窗口门槛一致); DESIGN §3.2 已改 |
| I2 | DESIGN §3.5 原写「σ_ε=0 → beta_se=NaN」与 `SE=sqrt(σ²/Σ(f−f̄)²)` 矛盾 | 改为 `σ̂²_ε=0 → beta_se=0`; `Σ(f−f̄)²≈0 → β/β_se 同为 NaN`; DESIGN/EXECUTION §4 同步 |
| I3 | EXECUTION 初稿漏记 `Σ(f−f̄)²≈0` 与 `σ̂²_ε=0` 两个逐期边界 | §4 退化表补齐 |
| I4 | 原「无共同日期/股票 → `n_periods=0`」混用两种情形: 无共同股票时 T 行仍在 | 拆分为「无共同日期 → T=0」与「无共同股票 → T 行全 NaN」; DESIGN/EXECUTION 同步 |

**review 结论**: PASS (4 项不一致已在步骤 9 前修复)。
