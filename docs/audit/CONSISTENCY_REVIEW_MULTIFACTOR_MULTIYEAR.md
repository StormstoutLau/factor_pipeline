# CONSISTENCY REVIEW — 多因子 × 多年实证扩展 (MULTIFACTOR_MULTIYEAR)

> **版本**: v1.0 (2026-11-16)
> **流程**: `docs/WORKFLOW_METHODOLOGY.md` §13.8 步骤 7
> **审查对象**: [RESEARCH](../research/RESEARCH_MULTIFACTOR_MULTIYEAR.md) / DESIGN (private) /
> [EXECUTION](../EXECUTION_MULTIFACTOR_MULTIYEAR.md) / `scripts/convert_legacy_pickles.py` /
> `scripts/verify_multifactor_multiyear.py` / [验证报告](../analysis/MULTIFACTOR_MULTIYEAR_VERIFICATION.md)

## §1 交叉核对 (规格 ↔ 代码 ↔ 报告)

| 项 | 规格 | 代码 | 结论 |
|----|------|------|------|
| 因子集 | RESEARCH §3.1 12 个 | `ALL_FACTORS` 12 个, 顺序一致 | ✅ |
| 因子方向 | 「大 = 预期收益高」 | 8 量价含负号 / 财务 current+、杠杆− | ✅ |
| eligible | list_date+365 | `build_eligible` (B 任务复用) | ✅ |
| 标签 | 下月末复利收益, `|r|>1` → NaN | `price_m.shift(-1)/price_m-1`, `mask(abs>1)` | ✅ |
| 横截面 | 1/99 + z + 300 门槛 | `cross_section_prep` 复用 | ✅ |
| 中性化 | 行业(28) + SIZE/BETA/RESVOL | `neutralize_panel` | ✅ |
| 自指排除 | size/beta 不中性化 | `SELF_REFERENTIAL` | ✅ |
| BH | 双 p 口径 + q 单调化 | `bh_fdr` (两处调用) | ✅ |
| 硬断言 | V1/V2/V3/V5/V7/V9 | `verify_factor` | ✅ |
| 软判定 | V4/V6 | `warnings` | ✅ |
| 版本 | 不升 | 3.4.12, 生产零改动 | ✅ |

## §2 发现的不一致与处置

| # | 不一致 | 位置 | 处置 |
|---|--------|------|------|
| I1 | RESEARCH V7 写「剔除并记录」, 脚本实际硬断言中断 | RESEARCH §4 | 改为「硬 (失败即中断)」 |
| I2 | RESEARCH §5 要求报告 12 因子实测相关, 首版脚本未输出 | RESEARCH §5 / 脚本 | 新增 `beta_corr` (mean/max \|ρ\| + >0.5 对列表); 并补 Bonferroni 保守边界 |
| I3 | EXECUTION §6 V8 计数写 8/4, 实跑为 6 因子 3/3、6 因子 2/3 | EXECUTION §6 | 更正为 6/6 |
| I4 | 验证报告 Q2 沿用 8/4 错误计数 | 报告 §6 | 更正为 6/6 |
| I5 | 「月末最后交易日」与 `resample('ME')` 索引 (日历月末) 语义差异未说明 | RESEARCH §3.2 | 补口径注 (值 vs 索引, 不参与日频连接) |
| I6 | B 报告 amihud 方向措辞「与经典相反」与因子负号矛盾 | B 报告 §3 | 就地更正为「一致」, 新报告 §6.1 披露 |
| I7 | 报告 §7 表格单元格 `\|ρ\|` 未转义, 破坏表格列 | 报告 §7 | 转义 `\\|ρ\\|` |

## §3 数据/数值一致性抽查

| 抽查 | 手工值 | 脚本输出 | 结论 |
|------|--------|---------|------|
| 4 个原因子 premium | B 报告 −0.003234 / +0.004097 / +0.004707 / −0.004989 | 全样本逐位一致 | ✅ |
| `premium_mean == mean(β_t)` | 断言 rel 1e-12 | 12 因子通过 | ✅ |
| BH 双口径 | 最大 q 差 0.0064 | 逐因子一致 | ✅ |
| Bonferroni | α/12 = 0.004167 | 3 通过 (turnover/reversal/volatility) | ✅ |
| Barra 对齐 | 173 月无重复; 40 月交集 | `Period('M')` 连接 | ✅ |
| 中性化有效性 | mean R² 0.206, 前置 \|ρ\| 0.10-0.22 | 与构造一致 | ✅ |
| 财务覆盖 | 月频有效 ≥ 4073 | 断言 ≥ 300 通过 | ✅ |

## §4 未消除的已知限制

- BH 在 β_t 强相关 (max 0.974) 下仍偏宽松; 已用 Bonferroni 给保守下界, Romano-Wolf 未做。
- 中性化区间仅 40 月, 2023-06 之后无行业数据。
- 财务因子无公告日, 季度值 ffilled 存在轻微前视风险。
- 分段 T≈24 检验力低, 只解释方向。

## §5 结论

**PASS**。7 项不一致全部处置完毕; 核心数值与 B 任务逐位复现; 生产代码零改动。
