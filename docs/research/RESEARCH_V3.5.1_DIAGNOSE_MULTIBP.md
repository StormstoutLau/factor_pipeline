# RESEARCH — v3.5.1 多断点接入 `diagnose` 标签路径

> 版本: v3.5.1 (步骤 1-2 产物) | 日期: 2026-11-17
> 前置: [v3.5.0 多断点](RESEARCH_V3.5.0_MULTIPLE_BREAKPOINTS.md) / [ADR-046](../DECISIONS.md) / [v3.5.0 异构复审](../EXECUTION_V3.5.0_MULTIPLE_BREAKPOINTS.md#L228-L263)

## §1 目标与问题

ADR-046 遗留 (G10): `detect_multiple` 已交付, 但 `diagnose()` 仍只消费单断点
`detect()`; 多断点结果**不进入** `premium_health` / 综合标签。本任务评估并接通该路径,
同时回答三个问题:

- **Q1**: 接入后默认行为是否变化? (结论: 默认不变, 见 DESIGN G1)
- **Q2**: 以什么依据判定「断点存在」? (结论: 形式检验 sup-F, 见 §3)
- **Q3**: BIC 在短样本假阳性 44%/36% (复审 H6), 如何避免把假阳性写进 ES 标签? (结论: 两级门控, 见 §4)

**非目标**: 不替换 `detect()`; 不改变 `'single'` 模式任何数值/标签; 不把 LWZ 作为
标签依据 (H5: c0=0.1 口径假阳性 89%/75%, 与「保守」预期相反); 不接入 `BreakpointScheduler`。

## §2 关键事实 (已有证据, 不重复测试)

| 事实 | 来源 |
|------|------|
| `detect_multiple` 输出 13 键, `has_breakpoint := n_breaks > 0` (纯 BIC) | v3.5.0 实现 |
| Stata 18.0 MP 官方 `regress` 对拍 46/46 PASS | v3.5.0 EXECUTION §7 |
| 纯噪声 BIC 选 m>0 的假阳性: 44% (T=72) / 36% (T=120) | 复审 H6 (200 次/配置) |
| 纯噪声 LWZ 假阳性: 89% (T=72) / 75% (T=120) | 复审 H5 |
| 同分布两段被 NaN 隔开 → 54% 假断点 | 复审 H7 |
| 单断点 sup-F 在纯噪声的假阳性 ≈ 3.3% (T=72) / 5.3% (T=120) | 本次探针 P-A (300 次/配置) |

结论: **不能**把 `n_breaks > 0` 直接映射为 ES。多断点的价值在**分段信息**,
存在性仍需形式检验背书 (Constitution 原则 3: 所有统计判断必须有显著性检验支撑)。

## §3 存在性 vs 选段数 (本次探针 P-A, 300 次/配置)

| 场景 | sup-F 拒绝率 | BIC n>0 率 | 二者同时 (∧) |
|------|------------|-----------|-------------|
| 纯噪声 T=72 | 3.3% | 39.0% | **3.3%** |
| 纯噪声 T=120 | 5.3% | 33.3% | **5.3%** |
| 单断点 d=0.8σ T=120 | 96.0% | 99.7% | 96.0% |
| 单断点 d=1.0σ T=120 | 100% | 100% | 100% |
| 两断点 d=0.8σ T=120 | 47.7% | 98.0% | 47.7% |
| 两断点 d=1.0σ T=120 | 68.7% | 100% | 68.7% |

- sup-F 对**单断点**功效高, 且 size 受控 → 适合做存在性判定 (`breakpoint_confirmed`);
- 对**双断点** sup-F 功效降至 48%–69%, 但 BIC 分段几乎总能识别 — 因此不应丢弃
  「形式检验未过、但 BIC 分段材料性显著」的情形, 否则多断点接入没有增量;
- BIC n>0 在探针中几乎是 sup-F 的超集 (∧ 率 = sup-F 率), 佐证 `n_breaks` 不能单独作 ES 依据。

## §4 材料性门控 (本次探针 P-B, 300 次/配置)

定义 `shift_ratio = max_j |μ_{j+1} − μ_j| / sd_within`, 其中
`sd_within = sqrt(SSR_best / T)` (分段内残差标准差)。

| 阈值 | 噪声假阳性 T=72 | 噪声假阳性 T=120 | 单断点 d=0.8 功效 | 双断点 d=1.0 功效 |
|------|----------------|-----------------|------------------|------------------|
| 0.75 | 31.7% | 13.0% | 73.7% | 99.0% |
| **1.0** | **19.3%** | **4.0%** | 26.7% | 87.3% |
| 1.25 | 10.7% | 0.0% | 7.7% | 48.3% |
| 1.5 | 4.3% | 0.0% | 1.3% | 19.3% |

- 阈值 1.0 是「相邻段均值差 ≥ 1 个段内标准差」, 可解释且与现有 `suspect` 语义衔接
  (`BreakpointDetector` docstring: 「breakpoint detected but pre-post difference small → suspect」);
- 该门控**只用于未形式确认**的 BIC 发现, 命中时降级为 `suspect` (不升级 ES);
  材料性不作为独立显著性声明;
- 1.0 在 T=72 仍有 19% 的 suspect 触发率 — 已优于裸 BIC 的 39%, 且在 opt-in 模式下可接受,
  在文档中明示「suspect ≠ 断点确认」。

> 注 (复审补充): 表中假阳性为 **suspect 触发率** (未确认但材料的 BIC 分段); 纯噪声下的
> **ES 率由 sup-F 名义 size 决定** (序列级 3.3%/5.3%, 面板级实测 3-4%), 不随阈值变化 —
> ES 判定完全独立于材料性门控。

## §5 待验证假设

| # | 假设 | 验证方式 |
|---|------|---------|
| H1 | `'single'` 模式标签/数值逐位不变 | F1 + 全量回归 |
| H2 | 强单断点面板在多断点模式下 confirmed=True, n_breaks=1 | F2 (T=240, N=150) |
| H3 | 双断点面板 n_breaks=2, 断点 [80,160] | F3 (探针 P-C 实测) |
| H4 | 纯噪声面板不产生 ES; 若 has_bp 则必为 suspect | F4 |
| H5 | 未确认但材料 → suspect; 未确认且不材料 → 不改标签 | F7/F8 (monkeypatch) |

## §6 参考

- Bai, J., & Perron, P. (1998). Estimating and testing linear models with multiple structural changes. *Econometrica*, 66(1), 47-78.
- Bai, J., & Perron, P. (2003). Computation and analysis of multiple structural change models. *Journal of Applied Econometrics*, 18(1), 1-22.
- Yao, Y.-C. (1988). Estimating the number of change-points via Schwarz' criterion. *Statistics & Probability Letters*, 6(3), 181-189.
- Liu, J., Wu, S., & Zidek, J. V. (1997). On segmented multivariate regression. *Statistica Sinica*, 7(2), 497-525.
- Andrews, D. W. K. (1993). Tests for parameter instability and structural change with unknown change point. *Econometrica*, 61(4), 821-856.

## §7 交付物

DESIGN_V3.5.1 (G1-G12) → EXECUTION_V3.5.1 (F1-F9) → 代码 + 测试 → 审计 + ADR-047。
