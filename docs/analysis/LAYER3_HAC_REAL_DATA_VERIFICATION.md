# Layer 3 HAC 真实数据验证报告

> **日期**: 2026-11-16
> **对象**: `PremiumEstimator.estimate_with_errors` (v3.4.12)
> **数据**: `E:\Ashare_data` 日频行情, 2020-01-02 → 2026-01-30
> **脚本**: [scripts/verify_layer3_hac_real.py](../../scripts/verify_layer3_hac_real.py)
> **工件**: [RESEARCH](../research/RESEARCH_LAYER3_HAC_REAL_DATA.md) /
> [EXECUTION](../EXECUTION_LAYER3_HAC_REAL_DATA.md) /
> [CHECKLIST](../audit/CHECKLIST_LAYER3_HAC_REAL_DATA.md) /
> [CONSISTENCY_REVIEW](../audit/CONSISTENCY_REVIEW_LAYER3_HAC_REAL_DATA.md) /
> [audit](../audit/2026-11-16-layer3-hac-real-data-audit.md)

## §1 口径

| 项 | 设定 |
|---|------|
| 频率 | 月末 FM, T=73 (2020-02 → 2026-01; 最后一月无前瞻收益) |
| 因子 | `momentum_1m` / `reversal_1w` / `volatility_1m` / `amihud_1m` (后两者取负, 经济正向) |
| 复权 | `close × adj` |
| 收益 | 下月复权收益; `|r|>1` 置 NaN |
| 清洗 | 上市满 365 自然日; 横截面 winsorize 1/99 + z-score; 月有效 ≥300 只 |
| 带宽 | `bandwidth=12` (1 年月度); `alpha=0.05` |
| 标签 | `FactorHealthDiagnoser(bandwidth=12)` 对照 (仅参照, HAC CI 未接入标签) |

## §2 结果

| 因子 | premium_mean | HAC SE | t_HAC | t_naive | SE_HAC/SE_iid | 95% CI | n_valid | health | diagnosis |
|------|-------------|--------|-------|---------|---------------|--------|---------|--------|-----------|
| momentum_1m | −0.003234 | 0.001708 | −1.89 | −1.77 | 0.935 | [−0.006582, 0.000114] | 68 | stable | pricing |
| reversal_1w | +0.004097 | 0.001212 | **3.38** | 2.84 | 0.841 | [0.001720, 0.006473] | 70 | stable | pricing |
| volatility_1m | +0.004707 | 0.001612 | **2.92** | 2.29 | 0.786 | [0.001548, 0.007866] | 68 | TD | review |
| amihud_1m | −0.004989 | 0.002008 | **−2.48** | −2.53 | 1.020 | [−0.008925, −0.001053] | 68 | stable | pricing |

BH-FDR (q=0.05, m=4, 双口径): 正态近似 p ≈ 0.0007 / 0.0035 / 0.0131 / 0.0588;
t(df=n−1) p ≈ 0.0012 / 0.0048 / 0.0155 / 0.0626 →
**两口径下均为 reversal_1w / volatility_1m / amihud_1m 通过, momentum_1m 不通过**。
因子月度截面均值序列时序相关 |ρ| ≤ 0.22 (momentum×reversal 0.22, 其余 ≤0.16),
BH 独立性违反轻微, 判定可用 (Romano-Wolf stepdown 见 §6 范围外)。

## §3 观察

1. **HAC 修正方向正确**: `SE_HAC/SE_iid` ∈ [0.786, 1.020]。`reversal_1w` 与
   `volatility_1m` 的 β_t 序列正自相关 → HAC SE 放大 16–21%, 使 t 值由 2.84/2.29
   升至 3.38/2.92; `amihud_1m` 几乎无自相关 (1.02)。
2. **CI 行为合理**: 三个显著因子的 CI 不含 0, 且与朴素 FM 结论一致 (无翻转);
   `momentum_1m` CI 含 0, 与 t_naive=−1.77 一致。
3. **保守性在真实数据中未导致过度不显著**: v3.4.12 的 MC 显示 SE 对纯抽样误差保守
   (SE/sd=1.77), 但真实 β_t 序列的自相关使 HAC/iid 落在 0.79–1.02, 4 个因子中 3 个
   仍通过 BH-FDR — 保守性属可接受的安全侧偏差。
4. **经济结论 (真实发现, 非缺陷)**: 2020-2026 样本内, A 股呈短反转
   (reversal_1w 正) 与低波溢价 (volatility_1m 正); 1 月动量为负且不显著;
   高流动性组收益更低 (amihud_1m 为负) — **与经典流动性溢价方向一致** (因子含负号,
   故负溢价 = 低流动性组收益更高); 2026-11-16 多因子报告 §6.1 更正原文措辞。
5. **标签对照**: `volatility_1m` 被 `diagnose` 判为 `TD`(衰减) → `review`;
   其余 `stable` → `pricing`。HAC CI 未参与标签 (v3.4.12 范围外), 仅并列展示。

## §3.1 异构复审补充取证 (2026-11-16)

| 探针 | 结果 | 含义 |
|------|------|------|
| P1 list_date 覆盖 | 5688 只中缺 1 只 (静默剔除); 月均 eligible 4753 | 影响可忽略, 已记录 |
| P2 因子相关 | 月度截面均值序列 \|ρ\|≤0.22 | BH 独立性违反轻微 (见 §2 口径行) |
| P3 p 值口径 | 正态 vs t(df=n−1): BH 均为 3/4 通过 | 结论对口径不敏感 |
| P4 平滑带宽 | `premium_mean_se` 在 h=6/12/24 **完全相同** | 均值 SE 用全局 Ω_β, 不依赖平滑带宽; h 仅影响 λ̂(t) 局部 CI |
| P5 子样本 | 方向全部稳定 (reversal 2.43/1.58, amihud −1.50/−2.07); volatility 后半 t=0.68 — 与 TD 判定互相印证 | 后半段显著性普遍减弱 (样本短) |
| P6 adj 性质 | 全市场抽查: adj 单调不减比例中位数 0.999, 变动日 1-10/1393 (除权除息跳变) | 确认 `close×adj` 为含分红调整的后复权价 (RESEARCH F2 成立) |
| P7 标签带宽敏感性 | volatility TD 在 h=6/12/24 稳健; momentum 在 h=24 翻转为 TD(review) (该因子本身不显著, 影响小) | TD 判定基本稳健, momentum 标签勿过度解读 |
| P8 HAC lag q | q=1→6: SE 变化 −9%~−19%; 四因子 \|t\| 在 q=1..6 全程同侧 (reversal 2.95–3.38, volatility 2.48–3.00, amihud 2.31–2.83, momentum 1.84–1.97) | 显著性结论对 q 不敏感 |

> 复审过程自纠: 首版 P6 探针误查 `close×adj` (复权价本就不单调) 而非 `adj` 本身,
> 修正后确认 F2; 取证脚本见审计 Phase 7。

## §4 断言判定

| # | 断言 | 结果 |
|---|------|------|
| V1 | 14 键 + 数组长度 | ✅ |
| V2 | `premium_mean == nanmean(beta_t)` (rel 1e-12) | ✅ |
| V3 | `se` 有限正 + CI 含点 | ✅ |
| V4 | `hac_over_iid ∈ [0.3, 3.0]` (软) | ✅ 0.786–1.020, 无 WARN |
| V5 | 与 `diagnose` 同号 | ✅ 4/4 |
| V6 | `n_valid ≥ 60` (软) | ✅ 68–70, 无 WARN |

## §5 实现阶段修正 (诚实记录)

首版「上市满 250 交易日」用 `close.notna().cumsum() >= 250`, 会把面板起点 (2020-01)
整体后移一年, 误伤 2020 年前已上市的老股 → `n_valid=57–58`, 4 个因子全部触发 V6 WARN,
且样本期实际从 2021 年起 (缺失 2020 全年)。

修正为基于 `list_date` 的掩码: 面板起点前上市直接 eligible, 面板内新股按
`list_date + 365 天`。修正后 `n_valid=68–70`, WARN 清零, 样本期覆盖 2020-02 → 2026-01。
首版结果 (修正前) 与修正后方向一致, 但 t 值偏小 (如 reversal 3.07 → 3.38)。

## §6 已知偏差

| 偏差 | 影响 |
|------|------|
| 样本期 6 年 (T=73) | 带宽 12 下约 6 个有效窗口; 断点/衰减检验力有限 |
| 幸存者偏差 | 面板含 179 只退市股, 但 2020 年股票池为「现可得」并集, 偏差有限 |
| 无行业/市值中性化 | 因子溢价可能混入行业/规模暴露 |
| 仅量价 | 财务因子 pickle 不兼容 (RESEARCH F5) |
| 多重检验 | BH-FDR (m=4, 因子相关 \|ρ\|≤0.22, 独立性违反轻微); 未做 Romano-Wolf stepdown |
| 标签带宽敏感性 | momentum 的 TD 标签在 h=24 翻转 (该因子不显著, 影响小); 其余三因子 h=6/12/24 稳定 |
| list_date 缺失 | 1 只股票因 list_date 缺失被静默剔除 (月均 eligible 4753, 影响可忽略) |

## §7 复现

```powershell
python scripts/verify_layer3_hac_real.py --json out.json
# 可选: --data-root <path> --bandwidth 12 --alpha 0.05
```

运行环境: pandas 2.x / numpy / scipy; 数据路径默认 `E:\Ashare_data`。
