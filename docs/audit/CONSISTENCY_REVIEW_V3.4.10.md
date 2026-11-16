# CONSISTENCY REVIEW v3.4.10

> **review 时机**: 步骤 8 (步骤 7 checklist 完成后, 步骤 9 TDD 实现前)
> **review 对象**: [RESEARCH_HAC_NAN_FILTER.md](../research/RESEARCH_HAC_NAN_FILTER.md) /
> [DESIGN_HAC_NAN_FILTER.md](../private/DESIGN_HAC_NAN_FILTER.md) /
> [EXECUTION_V3.4.10_HAC_NAN_FILTER.md](../EXECUTION_V3.4.10_HAC_NAN_FILTER.md) /
> [CHECKLIST_V3.4.10.md](CHECKLIST_V3.4.10.md)

## §1 引用一致性

| 引用 | 调研文档 | 设计文档 | 实施文档 | checklist | 状态 |
|------|---------|---------|---------|----------|------|
| Newey & West (1987), Econometrica 55(3):703, DOI 10.2307/1913610 | §2 | §3.1 (核/带宽) | §3.1 (公式不变) | — | ✅ 一致 |
| Ledoit & Wolf (2008), JEF 15(5):850-859, DOI 10.1016/j.jempfin.2008.03.002 | §2 | §1 (ΔSR 检验) | §1 | — | ✅ 一致 |
| Datta & Du (2012), IFDP 2012(1060):1-48, DOI 10.17016/ifdp.2012.1060 | §2 (ES 定义) | §3.1 / §5 | §3.1 / §3.2 docstring | A6 | ✅ 一致 |
| `p=1.0` 无证据约定 | §4.3 | §3.3 | §3.1 | A3 | ✅ 一致 |

## §2 接口签名一致性

| 接口 | 设计文档 | 实施文档 | 源代码 (现状) | 状态 |
|------|---------|---------|-------------|------|
| `ledoit_wolf_hac_test(returns_a, returns_b, alpha=0.05) -> Tuple[float, float]` | §2 | §1 / §3 | [ablation_runner.py L46-L50](../../backtest/ablation_runner.py#L46-L50) | ✅ 一致 |
| `compare` / `compare_all` 不变 | G7 | §1 / A8 | L1318-L1454 | ✅ 一致 |
| `AblationResult.ls_return_series: np.ndarray` | §2 | E6 | L362-L373 | ✅ 一致 |

## §3 验收标准一致性

| 验收项 | 实施文档 | checklist | 状态 |
|-------|---------|----------|------|
| 联合掩码 | §3.1 / G1 | A1-A2 | ✅ 一致 |
| 清洗后基数 | §3.1 / G2 | A4 | ✅ 一致 |
| `n < 3` 退化 | §3.1 / G3 | A3 | ✅ 一致 |
| 同位置 NaN 等价 (E1) | §4 E1 | B1 | ✅ 一致 |
| 不同位置 NaN 成对 (E2) | §4 E2 | B2 | ✅ 一致 |
| 不足有效配对 (E3) | §4 E3 | B3 | ✅ 一致 |
| 全 NaN (E4) | §4 E4 | B4 | ✅ 一致 |
| inf 等价 (E5) | §4 E5 | B5 | ✅ 一致 |
| `compare` 集成 (E6) | §4 E6 | B6 | ✅ 一致 |
| 既有用例零影响 (E7) | §4 E7 | C1 | ✅ 一致 |

## §4 决策记录对齐

| 决策 | 调研文档 | 设计文档 | 实施文档 | 状态 |
|-----|---------|---------|---------|------|
| 采用 ES (drop-and-compress) 而非 AM | §4.1 / §5 O1 | §3.1 / §6 | §3.1 | ✅ 对齐 |
| 联合掩码而非逐序列 | §4.1 | §3.1 | §3.1 | ✅ 对齐 |
| `mean_diff_hac_statsmodels` 范围外 | §4.5 / O2 | §6 | §3 / A8 | ✅ 对齐 |
| 不新增 ADR (既有 ADR-036 消融评估链的实现修复) | §6 | — | §2 | ✅ 对齐 |

> ADR 说明: 本次为 `ledoit_wolf_hac_test` 的实现缺陷修复, 不改变方法选择
> (Ledoit-Wolf 2008 仍为唯一主路径), 因此不新增 ADR; 与 ADR-036 的
> 「消融显著性判定」实现保持一致。

## §5 不一致项修复

| # | 发现 | 修复 |
|---|------|------|
| — | 未发现不一致项 | — |

**review 结论**: PASS。
