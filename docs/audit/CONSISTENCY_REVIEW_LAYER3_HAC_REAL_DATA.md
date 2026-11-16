# CONSISTENCY REVIEW — Layer 3 HAC 真实数据验证

> **review 时机**: 步骤 8 (CHECKLIST 完成后, 脚本实现前)
> **review 对象**: [RESEARCH](../research/RESEARCH_LAYER3_HAC_REAL_DATA.md) / DESIGN (private) /
> [EXECUTION](../EXECUTION_LAYER3_HAC_REAL_DATA.md) / [CHECKLIST](CHECKLIST_LAYER3_HAC_REAL_DATA.md)

## §1 数据事实一致性

| 事实 | 文档 | 实测 | 状态 |
|------|------|------|------|
| 日频面板 1475×5688, 2020-01-02 → 2026-01-30 | RESEARCH F1 / EXEC F1 | `stock_close.pkl` | ✅ |
| 复权 = close×adj, adj 递增 | RESEARCH F2 / EXEC A2 | 000001 adj=109.1694 | ✅ |
| amount 日成交额 | RESEARCH F3 | median 1.32e6 | ✅ |
| list_date 5797 行 | RESEARCH F8 / EXEC F4 | `list_date_df.pkl` | ✅ |
| 财务/UTR pickle 不兼容 | RESEARCH F5 / EXEC F5 | 抛 `StringDtype` 错 | ✅ |
| 退市 179 只 / 新股 1315 只 | RESEARCH F7/F8 | last/first_valid 分布 | ✅ |
| 行业仅到 2023-06-13 | RESEARCH F6 | `stock_ind.pkl` | ✅ |

## §2 接口一致性

| 接口 | 文档 | 源码 | 状态 |
|------|------|------|------|
| `estimate_with_errors(factor, forward_returns, alpha=0.05, max_lag=None)` | EXEC §2 | [L65-L68](../modules/factor_health/__init__.py#L65-L68) | ✅ |
| 返回 14 键 | EXEC §2 `KEYS` | [L140-L154](../modules/factor_health/__init__.py#L140-L154) | ✅ |
| `premium_mean = mean(beta_t[finite])` | V2 | [L128-L130](../modules/factor_health/__init__.py#L128-L130) | ✅ |
| `premium_mean_se = sqrt(Ω_β/n_valid)` | RESEARCH §3 | [L131-L135](../modules/factor_health/__init__.py#L131-L135) | ✅ |
| `diagnose(...)['premium_mean']` 存在 | V5 | [L381](../modules/factor_health/__init__.py#L381) | ✅ |
| `FactorHealthDiagnoser(bandwidth, alpha)` | EXEC §2 | [L335-L341](../modules/factor_health/__init__.py#L335-L341) | ✅ |

## §3 口径一致性

| 项 | RESEARCH | DESIGN | EXECUTION | CHECKLIST | 状态 |
|----|---------|--------|-----------|-----------|------|
| 月末 FM + 下月收益 | §3.1 | G3 | A5 | A5 | ✅ |
| 4 因子定义 | §3.2 | §2 | A3 | A3 | ✅ |
| 上市 250 日 | §3.3 | 3.2 | A4 | A4 | ✅ |
| winsorize 1/99 + z | §3.3 | 3.3 | A6 | A6 | ✅ |
| 月有效 ≥300 | §3.1 | 3.6 | A6 | A6 | ✅ |
| V4 软判定 | §4 | 3.5/G5 | §3 | B5 | ✅ (DESIGN G5 已同步修订) |
| 已知偏差 | §5 | §6 | — | D3 | ✅ |

## §4 不一致项修复

| # | 发现 | 修复 |
|---|------|------|
| I1 | DESIGN G5 原写「断言 V2-V5 全部硬失败」, 与 §3.5「V4 不掩盖、作为发现」及 EXECUTION V4 软判定冲突 | DESIGN G5 改为「V2/V3/V5 硬失败; V4/V6 软判定」 |
| I2 | 实现阶段: 首版 `eligible` 用 `close.notna().cumsum()>=250`, 把面板起点后移一年 (n_valid 57-58, 缺 2020 全年) | 改为 `build_eligible` 基于 `list_date + 365 天`; EXECUTION 代码块与 CHECKLIST A4 同步; 结果 n_valid 68-70 |

**review 结论**: PASS (2 项不一致已修复)。
