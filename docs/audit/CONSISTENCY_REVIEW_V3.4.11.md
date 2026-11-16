# CONSISTENCY REVIEW v3.4.11

> **review 时机**: 步骤 8 (步骤 7 checklist 完成后, 步骤 9 TDD 实现前)
> **review 对象**: [EXECUTION_V3.4.11_TECH_DEBT_PACK.md](../EXECUTION_V3.4.11_TECH_DEBT_PACK.md) /
> [CHECKLIST_V3.4.11.md](CHECKLIST_V3.4.11.md)

## §1 事实引用一致性

| 事实 | 实施文档 | 源代码 (现状) | 状态 |
|------|---------|-------------|------|
| `alpha` 未使用 | §2 F1 / §3.1 | [ablation_runner.py L46-L160](../../backtest/ablation_runner.py#L46-L160) | ✅ 一致 |
| 唯一调用点 `compare` | §2 F2 | [ablation_runner.py L1343](../../backtest/ablation_runner.py#L1343) | ✅ 一致 |
| `mean_diff` 无过滤 | §2 F3 | L144-L180 | ✅ 一致 |
| Adapter 已支持两参数 | §2 F4 | [adapters.py L53-L55](../../adapters.py#L53-L55) | ✅ 一致 |
| Static 管道未透传 | §2 F5 | [pipelines_v2.py L709-L732](../../pipelines_v2.py#L709-L732) | ✅ 一致 |
| detector 默认值 | §2 F8 | [transformers.py L30-L41](../../modules/factor_adaptive_winsor/core/transformers.py#L30-L41) | ✅ 一致 |
| ADR-043 已弃用 | §2 F9 / §6 | [DECISIONS.md L2967-L2981](../../DECISIONS.md#L2967-L2981) | ✅ 一致 |

## §2 接口签名一致性

| 接口 | 实施文档 | 目标签名 | 状态 |
|------|---------|---------|------|
| `ledoit_wolf_hac_test(returns_a, returns_b)` | §3.1 | 两参数, 返回 `(float, float)` | ✅ |
| `mean_diff_hac_statsmodels(returns_a, returns_b, maxlags=None)` | §3.2 | 签名不变 | ✅ |
| `StaticFactorPipeline(... outlier_adaptive_threshold, outlier_max_outlier_frac)` | §3.3(b) | 仅新增两可选参数 | ✅ |
| `PipelineV2Config.static_outlier_*` | §3.3(a) | 仅新增两字段 | ✅ |

## §3 验收标准一致性

| 验收项 | 实施文档 | checklist | 状态 |
|-------|---------|----------|------|
| 移除 alpha | §3.1 | A1-A2 | ✅ |
| mean_diff 成对过滤 | §3.2 | A3-A4 / B1-B2 | ✅ |
| MAD 参数透传 | §3.3 | A5-A8 / B3-B5 | ✅ |
| 排除非生产解耦器 | §6 | (D2 文档项) | ✅ |

## §4 决策记录对齐

| 决策 | 依据 | 实施文档 | 状态 |
|-----|------|---------|------|
| 不修非生产解耦器 | ADR-043 | §6 | ✅ 对齐 |
| 默认行为零变更 | v3.4.7/v3.4.10 惯例 | §3.3 / §5 | ✅ 对齐 |
| 不新增 ADR | 纯技术债清理, 无方法学选择 | §1 / §5 | ✅ 对齐 |

## §5 不一致项修复

| # | 发现 | 修复 |
|---|------|------|
| — | 未发现不一致项 | — |

**review 结论**: PASS。
