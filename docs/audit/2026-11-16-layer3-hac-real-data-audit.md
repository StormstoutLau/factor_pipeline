# 2026-11-16 审计 — Layer 3 HAC 真实数据验证

> **审计对象**: [scripts/verify_layer3_hac_real.py](../../scripts/verify_layer3_hac_real.py) + 验证报告
> **代码版本**: 3.4.12 (不升版本; 生产代码零改动)
> **审计依据**: [RESEARCH](../research/RESEARCH_LAYER3_HAC_REAL_DATA.md) /
> [EXECUTION](../EXECUTION_LAYER3_HAC_REAL_DATA.md) /
> [CHECKLIST](CHECKLIST_LAYER3_HAC_REAL_DATA.md) /
> [CONSISTENCY_REVIEW](CONSISTENCY_REVIEW_LAYER3_HAC_REAL_DATA.md)
> **审计方法**: audit-driven-development 4 阶段

## Phase 1 — Spec Inventory

| 工件 | 版本 | 状态 |
|------|------|------|
| RESEARCH_LAYER3_HAC_REAL_DATA.md | v1.0 | ✅ Q1-Q6 + F1-F9 + V1-V6 |
| DESIGN_LAYER3_HAC_REAL_DATA.md (private) | v1.0 | ✅ G1-G7 + 决策 + review |
| EXECUTION_LAYER3_HAC_REAL_DATA.md | v1.0 | ✅ 完整代码 + 验收口径 + review |
| CHECKLIST_LAYER3_HAC_REAL_DATA.md | v1.0 | ✅ A/B/C/D/E |
| CONSISTENCY_REVIEW_LAYER3_HAC_REAL_DATA.md | v1.0 | ✅ PASS (2 项修复) |

## Phase 2 — Code vs Spec

| 规格 | 代码证据 | 结论 |
|------|---------|------|
| A1 数据加载对齐 | `load_market` L38-L53 | ✅ |
| A2 复权 close×adj | L167 `adj_price = close * adj` | ✅ |
| A3 4 因子定义 | `build_factors` L55-L62 | ✅ 与 RESEARCH §3.2 逐一对应 |
| A4 上市满 365 日 | `build_eligible` L69-L78 | ✅ (修正后) |
| A5 月末 + 下月收益 | L65-L66, L171-L172 | ✅ |
| A6 winsorize + z + 300 | `cross_section_prep` L81-L95 | ✅ |
| B1 estimate_with_errors | L104-L105 | ✅ 参数与签名一致 |
| B2-B4 V1-V3 硬断言 | L107-L124 | ✅ |
| B5 V4 软判定 | L126-L129 | ✅ |
| B6 V5 同号 | L131-L139 | ✅ |
| B7 V6 软判定 | L141-L142 | ✅ |
| B8 stdout + JSON | L199-L211 | ✅ |

## Phase 3 — Defect Scan

| # | 候选问题 | 判定 | 处置 |
|---|---------|------|------|
| D1 | 首版 `eligible` 用 `close.notna().cumsum()>=250`, 把面板起点后移一年 (n_valid 57-58, 缺 2020 全年) | **真实缺陷** (实现阶段发现) | ✅ 改为 `list_date + 365 天`; n_valid 68-70; 报告 §5 记录 |
| D2 | 因子方向为人工指定 (vol/amihud 取负) | 有意 (经济正向), 报告已声明 | 不改 |
| D3 | 未做行业/市值中性化 | 范围外 (行业数据仅到 2023-06) | 报告 §6 声明 |
| D4 | 多重检验仅 BH-FDR, 未做 Romano-Wolf | 4 个因子, BH 足够; 已给 p 值与判定 | 不改 |
| D5 | 数据路径硬编码 `E:\Ashare_data` | 有 `--data-root` 覆盖 | 接受 |
| D6 | `MIN_LISTED_DAYS` 常量在改用 list_date 后未引用 | 死常量 | 保留 (文档对齐 250 交易日语义), 或删除; 低优先 |

**Phase 3 结论**: D1 为已修复的实现缺陷; 其余为已声明范围/取舍; 无 P0/P1。

## Phase 4 — 运行证据

| 项 | 结果 |
|---|------|
| 首版运行 | exit 0; 4 因子; 全部 V6 WARN (n_valid 57-58) |
| 修正后运行 | exit 0; 4 因子; WARN 清零; n_valid 68-70; T=73 |
| V2/V3/V5 硬断言 | 4/4 通过 |
| V4 软判定 | 0.786–1.020, 全部在 [0.3, 3.0] |
| 显著性 | reversal 3.38 / volatility 2.92 / amihud −2.48 通过 BH-FDR; momentum −1.89 不通过 |
| 生产代码 | `git diff` 仅 scripts/docs, 无 `modules/` 变更 |

## Phase 5 — 自审

| # | 问题 | 结论 |
|---|------|------|
| S1 | 结果是否可能是前视? | 因子日频右对齐 (≤t), 收益 t→t+1, 月末采样不跨界 |
| S2 | HAC/iid 0.79–1.02 是否说明 HAC 无必要? | 否: reversal/volatility 的 SE 被放大 16–21%, t 值 2.84→3.38; amihud 无自相关属正常 |
| S3 | 保守性 (v3.4.12 MC 1.77×) 是否使结论失真? | 否: 4 个因子中 3 个仍通过 BH-FDR, 结论与 t_naive 一致 |
| S4 | 是否改动生产代码/版本? | 否, 仅新增 scripts + docs |
| S5 | 首版缺陷是否影响报告结论? | 不影响方向, 但 t 值偏小; 报告 §5 已如实记录 |

## Phase 6 — 审计结论 (初版)

**PASS**。脚本可一条命令复现; 断言 V1-V6 全部通过; HAC SE 在真实 A 股上方向正确、
量级合理 (与 iid 同阶), 保守性未导致过度不显著; 实现阶段 D1 已修复并记录;
生产代码零改动, 版本维持 3.4.12。

## Phase 7 — 异构复审 (2026-11-16, 5 视角 + 8 探针取证)

> 与 Phase 1-6 的 checklist 式审计不同, 本轮以异构视角 (计量推断 / 数据质量 /
> 稳健性 / 结论效度 / 可复现性) 主动攻击结论, 用探针实验取证而非仅审文档。

### 7.1 探针证据 (P1-P8)

| 探针 | 视角 | 结果 | 判定 |
|------|------|------|------|
| P1 list_date 覆盖 | 数据质量 | 5688 只缺 1 只 → 静默剔除; 月均 eligible 4753 | 记录, 影响可忽略 |
| P2 因子相关 | 计量推断 | 月度截面均值序列 \|ρ\|≤0.22 | BH 独立性违反轻微 |
| P3 p 值口径 | 计量推断 | 报告 BH 用正态近似未声明; t(df=n−1) 下 BH 仍 3/4 | 文档修正 (报告 §2) |
| P4 平滑带宽 | 计量推断 | premium_mean_se 在 h=6/12/24 完全相同 | 非缺陷: 均值 SE 用全局 Ω_β; 已写入报告 §3.1 |
| P5 子样本 | 稳健性 | 方向 4/4 稳定; volatility 后半 t=0.68 与 TD 判定互证 | 已写入报告 |
| P6 adj 单调性 | 数据质量 | 首版探针自身 bug (误查复权价); 修正后 adj 单调不减中位数 0.999 | RESEARCH F2 确认成立 |
| P7 标签带宽敏感性 | 结论效度 | volatility TD 在 h=6/12/24 稳健; momentum h=24 翻转 (不显著因子) | 已写入报告偏差表 |
| P8 HAC lag q | 计量推断 | q=1→6 SE 变化 −9%~−19%; \|t\| 全程同侧, 无翻转 | 结论对 q 不敏感 |

### 7.2 发现与处置

| # | 级别 | 发现 | 处置 |
|---|------|------|------|
| H1 | P3 | 报告 BH p 值未声明口径 (正态近似) | ✅ 报告 §2 补双口径 (正态 + t), BH 结论两口径一致 |
| H2 | P3 | BH 独立性假设未验证 | ✅ 报告补因子相关矩阵结论 (\|ρ\|≤0.22) |
| H3 | P4 | 1 只股票 list_date 缺失被静默剔除 | ✅ 报告偏差表记录 (月均 4753, 可忽略) |
| H4 | P4 | momentum 的 TD 标签在 h=24 翻转 | ✅ 报告偏差表记录 (不显著因子, 勿过度解读) |
| H5 | 信息 | 均值 SE 不随平滑带宽变化 (全局 Ω_β 口径特性) | ✅ 报告 §3.1 P4 行说明, 防误读为「未测敏感性」 |
| H6 | 自纠 | 首版 P6 探针误查复权价而非 adj 本身 | ✅ 修正重跑; 复审过程在报告 §3.1 尾注披露 |

### 7.3 结论

核心结论经异构攻击后**全部维持**: 3/4 因子通过 BH-FDR (对 p 值口径、lag q、平滑带宽
均不敏感); 方向在子样本稳定; HAC 修正方向正确; 复权口径经全市场抽查确认。
新增 5 条文档披露 (H1-H4 + P4 口径特性), 无代码变更。

**PASS (维持)**。
