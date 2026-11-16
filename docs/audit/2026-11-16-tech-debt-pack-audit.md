# 2026-11-16 代码质量审计 — v3.4.11 技术债小包

> **审计对象**: T1 `alpha` 清理 / T2 `mean_diff_hac_statsmodels` 缺失口径 /
> T3 MAD detector 参数透传 / T4 非生产解耦器不修复
> **代码版本**: 3.4.11
> **审计依据**: [EXECUTION_V3.4.11_TECH_DEBT_PACK.md](../EXECUTION_V3.4.11_TECH_DEBT_PACK.md) /
> [CHECKLIST_V3.4.11.md](CHECKLIST_V3.4.11.md) /
> [CONSISTENCY_REVIEW_V3.4.11.md](CONSISTENCY_REVIEW_V3.4.11.md)
> **审计方法**: audit-driven-development 4 阶段

## Phase 1 — Spec Inventory

| 工件 | 版本 | 状态 |
|------|------|------|
| EXECUTION_V3.4.11_TECH_DEBT_PACK.md | v1.0 | ✅ 4 项任务 + F1-F9 + 代码片段 |
| CHECKLIST_V3.4.11.md | v1.0 | ✅ A/B/C/D/E |
| CONSISTENCY_REVIEW_V3.4.11.md | v1.0 | ✅ PASS |

## Phase 2 — Code vs Spec Audit

| 规格 | 代码证据 | 结论 |
|------|---------|------|
| T1 移除 `alpha` | [ablation_runner.py L46-L49](../../backtest/ablation_runner.py#L46-L49) 签名两参数; [L1375](../../backtest/ablation_runner.py#L1375) 调用两参数 | ✅ |
| T2 成对过滤 | [L188-L204](../../backtest/ablation_runner.py#L188-L204) | ✅ |
| T2 `n<3` 退化 | [L197-L198](../../backtest/ablation_runner.py#L197-L198) | ✅ |
| T3 config 两字段 | [pipelines_v2.py L476-L478](../../pipelines_v2.py#L476-L478) | ✅ |
| T3 pipeline 两参数 | [L715-L716](../../pipelines_v2.py#L715-L716) | ✅ |
| T3 非分位透传 | [L733-L738](../../pipelines_v2.py#L733-L738) | ✅ |
| T3 config 注入 | [L1360-L1361](../../pipelines_v2.py#L1360-L1361) | ✅ |
| T4 不修复 + 文档标注 | PROJECT_STATUS 路标 `[—]` | ✅ |

**默认值核查**: config `True` / `0.05` 与 `SmartOutlierDetector.__init__` 默认逐值一致;
percentile/quantile 分支仍只传分位点 → 生产默认输出逐位不变。

## Phase 3 — Defect Scan

| # | 候选问题 | 判定 | 处置 |
|---|---------|------|------|
| D1 | `StaticFactorPipeline` 新增参数对 `percentile` 无效 | 有意 (分位点控制) | 文档已说明 |
| D2 | `mean_diff_hac_statsmodels` 的 `(0.0, 1.0)` 与零方差分支语义重叠 | 一致 (同为「无证据」) | 不改 |
| D3 | 移除 `alpha` 对仓外调用方是破坏性变更 | 真实但可控 | 该参数无功能; 仓内唯一调用点已同步, CHANGELOG 已声明 |
| D4 | `max_outlier_frac` 无范围校验 | 边界输入由 detector 承担 | 不在本次范围 |

**Phase 3 结论**: 无 P0/P1; D3 为已声明的 API 清理。

## Phase 4 — 测试与回归证据

| 项 | 结果 | 状态 |
|---|------|------|
| Red (E1-E5) | 5 failed / 3 passed | ✅ 复现 |
| Green (E1-E5) | 8 passed (新增 5 + 既有 3) | ✅ |
| `test_ablation_runner.py` + `test_ablation_knob_wiring.py` | 123 passed (6.35s) | ✅ |
| `test_pipelines_v2.py` + `test_adapters` + `test_ablation_decoupler_arm.py` | 46 passed (5.73s) | ✅ |
| `tests/test_backtest` | 599 passed / 8 skipped (573.34s) | ✅ |
| 全量 `tests/` | 1746 passed / 15 skipped / 0 failed (1176.01s; 基线 1741 → +5) | ✅ |
| 版本统一 | 7 passed + 手工 6/6 | ✅ |

## Phase 5 — 自审

| # | 问题 | 结论 |
|---|------|------|
| S1 | 默认配置是否真的零行为变更? | `adaptive_threshold=True` + `0.05` 与 detector 默认相同; percentile 分支未变 |
| S2 | `adaptive_threshold=False` 是否真的固定 3.0? | `_fit_mad_method` / `_fit_z_score_method` 的 else 分支为 3.0 |
| S3 | 移除 `alpha` 后显著性判定是否丢失? | 不丢: `compare` 用 `self.alpha` 比较 `p_value_hac` |
| S4 | `mean_diff` 过滤是否破坏参考检验语义? | 不破坏: 与主检验同口径, 参考检验仍只测 Δμ |
| S5 | T4 不修复是否有遗漏风险? | 无: ADR-043 已弃用, 零生产调用 |

## Phase 6 — 审计结论

**PASS**。三项变更均为局部、默认可逆; T4 的剔除有 ADR 依据;
Red→Green 可复现; 无 P0/P1 缺陷; 生产默认输出与缓存代际不变。
