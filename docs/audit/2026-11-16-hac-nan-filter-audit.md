# 2026-11-16 代码质量审计 — v3.4.10 HAC 检验 NaN 过滤

> **审计对象**: `backtest/ablation_runner.py::ledoit_wolf_hac_test` 的缺失值处理
> **代码版本**: 3.4.10
> **审计依据**: [RESEARCH_HAC_NAN_FILTER.md](../research/RESEARCH_HAC_NAN_FILTER.md) /
> [DESIGN_HAC_NAN_FILTER.md](../private/DESIGN_HAC_NAN_FILTER.md) /
> [EXECUTION_V3.4.10_HAC_NAN_FILTER.md](../EXECUTION_V3.4.10_HAC_NAN_FILTER.md) /
> [CHECKLIST_V3.4.10.md](CHECKLIST_V3.4.10.md) /
> [CONSISTENCY_REVIEW_V3.4.10.md](CONSISTENCY_REVIEW_V3.4.10.md)
> **审计方法**: audit-driven-development 4 阶段 (Spec Inventory → Code-vs-Spec → Defect Scan → Verdict)

## Phase 1 — Spec Inventory

| 工件 | 版本 | 状态 |
|------|------|------|
| RESEARCH_HAC_NAN_FILTER.md | v1.0 | ✅ 3 条引用经 Crossref 核实; F1-F12 行号核对 |
| DESIGN_HAC_NAN_FILTER.md (private) | v1.0 | ✅ G1-G7 / E1-E7 / 兼容性 |
| EXECUTION_V3.4.10_HAC_NAN_FILTER.md | v1.0 | ✅ 代码片段 + 验收表 |
| CHECKLIST_V3.4.10.md | v1.0 | ✅ A/B/C/D/E |
| CONSISTENCY_REVIEW_V3.4.10.md | v1.0 | ✅ 判定 PASS |

## Phase 2 — Code vs Spec Audit

| 规格 | 代码证据 | 结论 |
|------|---------|------|
| G1 成对联合 `isfinite` 掩码 | [ablation_runner.py L88-L89](../../backtest/ablation_runner.py#L88-L89) | ✅ |
| G2 清洗后样本作基数 | [L95-L102](../../backtest/ablation_runner.py#L95-L102) (`T = n_valid` 后计算 `q`) | ✅ |
| G3 `n < 3` → `(0.0, 1.0)` | [L95-L96](../../backtest/ablation_runner.py#L95-L96) | ✅ |
| G4 签名 / 返回类型不变 | [L46-L50](../../backtest/ablation_runner.py#L46-L50) | ✅ |
| G5 丢弃时 1 条 debug | [L90-L94](../../backtest/ablation_runner.py#L90-L94) | ✅ |
| G6 docstring 声明 ES 口径 + 局限 | [L64-L68](../../backtest/ablation_runner.py#L64-L68) | ✅ |
| G7 `compare` / `compare_all` / bootstrap 零改动 | `git diff` 未触及 L1330-L1460 | ✅ |
| E1-E6 六例 | [test_ablation_runner.py L199-L339](../../tests/test_backtest/test_ablation_runner.py#L199-L339) | ✅ |
| A8 `mean_diff_hac_statsmodels` 零改动 | `git diff` 未触及 | ✅ |

**掩码顺序核查**: 先按 `min(len)` 截断尾部, 再算联合掩码 → 保留窗口与旧实现一致,
仅剔除窗口内的非有限配对。`T` 重赋值后, 后续 `h` 矩阵、`/T` 归一化与 `q`
全部使用清洗后样本 (L104-L160)。

## Phase 3 — Defect Scan

| # | 候选问题 | 判定 | 处置 |
|---|---------|------|------|
| D1 | `n < 3` 守卫也作用于**无缺失但极短**的输入 (T=1/2), 旧实现返回 NaN/未定义 | 真实但可接受 | 已在 DESIGN §5 / CHANGELOG 口径表显式标注; 无既有测试依赖 T<3 |
| D2 | `alpha` 参数在函数体内未被使用 | 既有现状, 非本次引入 | 范围外, 不修改 |
| D3 | ES 压缩时间轴 → 缺失点后的滞后对应前移 | 方法固有 | docstring + RESEARCH O3 声明; 缺失率低时影响可忽略 |
| D4 | `mean_diff_hac_statsmodels` 同样未过滤 NaN | 真实, 仅测试路径 | 范围外 (RESEARCH O2) |
| D5 | `circular_block_bootstrap` 逐序列 (非成对) 过滤 | 均值统计量不要求成对 | 范围外, 语义正确 |
| D6 | `compare` 的 P0-1 NaN 兜底保留 | 防御性代码, 修复后正常路径不触发 | 保留, 删除会扩大变更面 |

**Phase 3 结论**: 无 P0/P1 缺陷; D1 为已文档化的边界行为变更, D2-D6 为范围外或有意保留。

## Phase 4 — 测试与回归证据

| 项 | 结果 | 状态 |
|---|------|------|
| Red (`TestLedoitWolfHAC`) | 6 failed / 5 passed | ✅ 复现缺陷 |
| Green (`TestLedoitWolfHAC`) | 11 passed | ✅ |
| `tests/test_backtest/test_ablation_runner.py` | 89 passed (4.95s) | ✅ |
| `tests/test_backtest` | 594 passed / 8 skipped (664.96s) | ✅ |
| 全量 `tests/` | 1741 passed / 15 skipped / 0 failed (1437.31s; 基线 1735 → +6) | ✅ |
| 版本统一 | 7 passed + 手工 6/6 | ✅ |

## Phase 5 — 自审 (独立视角)

| # | 问题 | 结论 |
|---|------|------|
| S1 | 掩码是否会改变无缺失输入的数值? | 不会: 全 True, `n_valid == T`, 后续运算与旧路径逐位相同 (既有 5 例全绿) |
| S2 | 逐序列删除能否替代联合掩码? | 不能: 交叉矩条件 `h_a[t]⊗h_b[t]` 会错位; E2 已用数值对照证明差异 |
| S3 | 「无证据」返回 `(0.0, 1.0)` 是否会制造假阳性? | 不会: `p=1.0` 在 `compare` 判不显著, `compare_all` 退回 bootstrap 门控 |
| S4 | 是否有调用方依赖 NaN 返回值? | 无: 全仓仅 `compare` 与测试调用; `compare` 已有 NaN 兜底 |
| S5 | 文档行号是否与实现一致? | 一致 (Phase 2 已逐条核对) |

## Phase 6 — 审计结论

**PASS**。变更面收敛 (1 个函数 + 6 例测试 + 版本锚点 + 文档),
缺口语义有文献支撑 (Datta & Du 2012, ES 估计量),
Red→Green 可复现, 无 P0/P1 缺陷, 生产管线与缓存零影响。
