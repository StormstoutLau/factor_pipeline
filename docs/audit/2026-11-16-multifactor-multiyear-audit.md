# 2026-11-16 代码/实证审计 — 多因子 × 多年扩展 (MULTIFACTOR_MULTIYEAR)

> **审计对象**: 12 因子实证 + Barra 中性化 + legacy pickle 兼容层
> **代码版本**: 3.4.12 (生产代码零改动)
> **审计依据**: [RESEARCH](../research/RESEARCH_MULTIFACTOR_MULTIYEAR.md) /
> [EXECUTION](../EXECUTION_MULTIFACTOR_MULTIYEAR.md) /
> [CHECKLIST](CHECKLIST_MULTIFACTOR_MULTIYEAR.md) /
> [CONSISTENCY_REVIEW](CONSISTENCY_REVIEW_MULTIFACTOR_MULTIYEAR.md) /
> [验证报告](../analysis/MULTIFACTOR_MULTIYEAR_VERIFICATION.md)

## Phase 1 — Spec Inventory

| 工件 | 版本 | 状态 |
|------|------|------|
| RESEARCH_MULTIFACTOR_MULTIYEAR.md | v1.0 | ✅ F1-F16 + Q1-Q6 + V1-V12 |
| DESIGN_MULTIFACTOR_MULTIYEAR.md (private) | v1.0 | ✅ G1-G10 + 退化表 + 非目标 |
| EXECUTION_MULTIFACTOR_MULTIYEAR.md | v1.0 | ✅ 代码结构 + 验收映射 + §7 修正 D1-D4 |
| CHECKLIST / CONSISTENCY_REVIEW | v1.0 | ✅ A-F / I1-I7 |

## Phase 2 — Code vs Spec

| 规格 | 代码证据 | 结论 |
|------|---------|------|
| G1 shim Unpickler | `convert_legacy_pickles.py` `_CompatUnpickler.find_class` | ✅ |
| G2 单命令 C+I | `verify_multifactor_multiyear.py: main()` | ✅ |
| G3 12 因子 | `ALL_FACTORS` / `build_price_factors` / `load_financials` | ✅ |
| G4/G5 分段 | `SEGMENTS` + `run_sample` + `stability` | ✅ |
| G6 中性化 | `neutralize_panel` (行业 + SIZE/BETA/RESVOL) | ✅ |
| G7 带宽 | `bandwidth_sensitivity` (标签 + λ̂ 相关) | ✅ |
| G8 lag | `lag_sensitivity` (q=1..6) | ✅ |
| G9 断言 | `verify_factor` assert + `warnings` | ✅ |
| G10 复用 | `from verify_layer3_hac_real import ...` | ✅ |

## Phase 3 — Defect Scan

| # | 候选 | 判定 | 处置 |
|---|------|------|------|
| D1 | 财务覆盖断言把末月 0 计入 → V7 误报 | 实现缺陷 | 只统计有标签月份 |
| D2 | `diagnose` 在 T<30 触发 `_no_breakpoint_result` 缺失 → AttributeError | **生产缺陷 (DEFECT-1)** | 本次避让 (n_valid<30 跳过 diagnose), 缺陷另案 |
| D3 | 中性化正交性检查构造上恒 0, 无信息量 | 验证缺陷 | 补前置 \|ρ\| + R² |
| D4 | `load_financials` 误用 `columns.index` | 实现缺陷 | 改按 `close.index/columns` reindex |
| D5 | `premium_mean_se` 与带宽无关 (P4) | 设计事实, 非缺陷 | 报告 §5.2 说明 |
| D6 | `diagnose` 标签 `pricing` 易被误读为显著 | 语义风险 | 报告 §5.3 澄清 |

### DEFECT-1 复现 (生产代码, 未修)

```python
from factor_pipeline.modules.factor_health import BreakpointDetector
BreakpointDetector().detect(np.linspace(0.1, 0.2, 12))
# AttributeError: 'BreakpointDetector' object has no attribute '_no_breakpoint_result'
```

- 触发条件: `detect()` 输入有效点 `T < 30` (代码 L293-L294)。
- 影响面: 任意 `diagnose()` 的 β 有效期数 < 30 时抛异常 (而非返回「无断点」)。
- 建议: v3.4.13 补 `_no_breakpoint_result(T)` (返回 `has_breakpoint=False` + 空 cusum + NaN 均值)、
  单测 (T=10/29/30)、版本六锚点。

## Phase 4 — 数据完整性

| 检查 | 结果 |
|------|------|
| legacy pickle 根因 | `StringDtype.__init__` 3 位置参数 (版本不兼容), 非文件损坏 |
| 转换一致性 | 6/6 shape + NaN 比例回读一致 |
| 财务列交集 | 5585-5685 / 5688 |
| 月频财务覆盖 | 最小 4073 (≫ 300) |
| Barra 月份 | 173 唯一, 无重复; 2020-02→2023-05 40 月 |
| 中性化覆盖 | 每月 ≥ 300 (断言通过) |
| 标签离群 | `|r|>1` 掩码生效 (无 |r|>1 残留) |

## Phase 5 — 结论效度

| 主张 | 证据 | 强度 |
|------|------|------|
| 5/12 通过 BH-FDR | q 表 + 双 p 口径一致 | 中 (BH 受强相关影响) |
| 3/12 通过 Bonferroni | α/12=0.004167 | 强 (保守下界) |
| 低换手 / 短反转 / 低波 | t=5.18 / 3.38 / 2.92, 分段 3/3、3/3、2/3, 中性化后存活 | 强 |
| amihud 溢价方向与经典一致 | 因子负号 + 负溢价 | 强 (已更正 B 措辞) |
| MAX 部分由风格暴露驱动 | 中性化后 3.30→2.23, BH FLIP | 中 |
| 财务因子无溢价 | |t| ≤ 1.35, 中性化后 ≤ 1.35 | 中 (区间仅 40-71 月) |
| 低波 / MAX 在 2024-25 消失 | S3 方向反转, 分段 T≈24 | 弱-中 |
| 2020-2023 行情的结构性差异 | S1/S2/S3 对照 | 描述性 |

## Phase 6 — 审计结论 (初版)

**PASS**。规格-代码-报告三方一致 (7 项不一致已处置); 硬断言全部通过; 核心结论有保守边界支撑;
生产代码零改动。遗留: DEFECT-1 (生产缺陷, 另案)、BH 强相关、中性化区间限制。

## Phase 7 — 自审 (对本次审计自身的攻击)

| 质疑 | 回应 |
|------|------|
| 12 因子 BH 是否夸大显著性? | 是, 已并列 Bonferroni 3/12, 并在结论中按保守档表述 |
| 财务因子「无溢价」是否因前视/缺失导致? | 覆盖 ≥ 4073/月, 无前视 (ffill 仅 5 日), 但无公告日 → 结论限定为「样本期内无可检出溢价」 |
| 4 个原因子逐位复现是否只是同一脚本? | 因子定义/样本口径与 B 一致, 属预期; 独立价值在新因子与中性化 |
| 中性化后 \|ρ\|=0 是否说明代码没跑? | 前置 \|ρ\| 0.10-0.22 且 R²=0.206, 证明回归生效; 残差正交是 OLS 性质 |
| `pricing` 标签是否被当作显著? | 报告 §5.3 明确「标签 = 结构健康, 非显著性」 |
| S3 反转是否样本期噪声? | 仅作方向描述, 未据此下结论 |

**最终结论**: PASS (维持)。无阻断问题; DEFECT-1 建议独立小版本修复。

## Phase 8 — 异构复审 (2026-11-16, 攻击式取证)

> 5 视角 (计量推断 / 数据质量 / 稳健性 / 结论效度 / 可复现性), 8 项探针实验,
> 证据落 [验证报告 §3.1](../analysis/MULTIFACTOR_MULTIYEAR_VERIFICATION.md)。

| 发现 | 视角 | 证据 | 处置 |
|------|------|------|------|
| H1 parquet 转换无损 | 数据质量/可复现性 | P1: 6 文件逐值 max\|Δ\|=0 | 正面确认, 无文档变更 |
| H2 财务因子前视风险被高估 | 数据质量 | P2: 跳变集中披露窗口 (4+8+10 月占 82%); ocf_yoy 逐日 TTM | 报告 §7 偏差行改写 (前视风险小) |
| H3 财务截面无聚集退化 | 数据质量 | P2b: distinct 5083-5450 vs turnover 4883 | 正面确认 |
| H4 BH 实现正确 | 可复现性 | P9: vs statsmodels max\|Δq\|=1.4e-17 | 正面确认 |
| H5 名义 m=12 Bonferroni 过严 | 计量推断 | P7: m_eff=7.0 (谱方法); Bonferroni@m_eff 仍 3 个 | 报告 §6.5 改写 (核心三项任一口径通过) |
| H6 max_ret 是 5 个 BH 因子中最弱 | 结论效度 | P3 LOMO: max_ret worst t=1.79 (<2), 其余 ≥2.24 | 报告 §6.1 补强度分层 |
| H7 S3「反转」实为溢价消失 | 稳健性 | P4 按年拆: 2024/25 \|t\|≤0.44 (n=10-12) | 报告 §6.2 改写 (不再称「显著反转」) |
| H8 中性化吸收主体 = RESVOL; 自建 beta 与 Barra BETA 仅 ρ≈0.53 | 计量推断 | P6: RESVOL vs volatility/max_ret \|ρ\|=0.667/0.493; P5: beta 截面 ρ −0.53 | 报告 §4/§6.4/§7 改写 (「特质波动暴露为主」) |

**复审结论**: 核心结论 (保守档 3 因子: turnover / reversal / volatility) 经攻击后全部成立并加固;
4 处文档表述修正 (H2/H5/H6/H7/H8), 全部文档级, 无代码变更。DEFECT-1 影响面排查完成
(唯一生产路径 `diagnose → detect`, `StructuralBreakMonitor` 不受影响, 现有测试未覆盖),
已登记 PROJECT_STATUS §2 缺陷登记, 建议独立 v3.4.13 修复。
