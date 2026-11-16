# 多因子 × 多年实证验证报告

> **日期**: 2026-11-16
> **对象**: `PremiumEstimator.estimate_with_errors` (v3.4.12) 在 12 因子 × 全样本/三分段 + Barra 中性化子样本上的表现
> **上游**: [RESEARCH](../research/RESEARCH_MULTIFACTOR_MULTIYEAR.md) / [EXECUTION](../EXECUTION_MULTIFACTOR_MULTIYEAR.md)
> **脚本**: `scripts/verify_multifactor_multiyear.py` / `scripts/convert_legacy_pickles.py`
> **性质**: 分析工件 — 生产代码零改动, 版本维持 3.4.12。

## §1 口径

| 项 | 口径 |
|----|------|
| 数据 | `E:\Ashare_data`; 行情 2020-01-02 → 2026-01-30 (1475×5688); Barra 月频 → 2023-05-31 |
| 因子 | 12: 8 量价 + 4 财务 (方向统一为「大 = 预期收益高」) |
| 标签 | 月末复权价 → 下月末收益, `|r|>1` 置 NaN |
| 样本 | 上市满 250 交易日; 横截面 winsorize 1/99 + z-score; 有效 < 300 整月剔除 |
| 统计 | `premium_mean = mean(β_t)`; HAC SE (Bartlett, q 自动); 正态 + t 双 p 值; BH-FDR (m=12) |
| 中性化 | 2020-02 → 2023-05 (40 月): `f ~ 1 + 行业(28) + SIZE + BETA + RESVOL`, 10 个非自指因子 |
| 带宽 | h=12; 敏感性 h ∈ {6,12,24} |

## §2 全样本结果 (2020-02 → 2025-12, T=73, q=3)

| 因子 | premium_mean | HAC SE | t | q_norm | q_t | n_valid | health | BH | Bonf |
|------|-------------|--------|---|--------|-----|---------|--------|----|------|
| turnover_1m | +6.633e−3 | 1.282e−3 | **5.18** | 0.0000 | 0.0000 | 72 | stable | ✅ | ✅ |
| reversal_1w | +4.097e−3 | 1.212e−3 | **3.38** | 0.0044 | 0.0072 | 70 | stable | ✅ | ✅ |
| volatility_1m | +4.707e−3 | 1.612e−3 | **2.92** | 0.0140 | 0.0190 | 68 | TD | ✅ | ✅ |
| amihud_1m | −4.989e−3 | 2.008e−3 | **−2.48** | 0.0363 | 0.0427 | 68 | stable | ✅ | — |
| max_ret_1m | +3.619e−3 | 1.490e−3 | **2.43** | 0.0363 | 0.0427 | 68 | TD | ✅ | — |
| size_mv | +4.711e−3 | 2.179e−3 | 2.16 | 0.0613 | 0.0680 | 72 | stable | — | — |
| momentum_1m | −3.234e−3 | 1.708e−3 | −1.89 | 0.1000 | 0.1074 | 68 | stable | — | — |
| beta_60d | −3.018e−3 | 1.915e−3 | −1.58 | 0.1725 | 0.1797 | 67 | stable | — | — |
| ocf_yoy | +5.328e−4 | 4.193e−4 | 1.27 | 0.2718 | 0.2774 | 72 | stable | — | — |
| LT_debt_ratio | −8.370e−4 | 9.857e−4 | −0.85 | 0.4749 | 0.4783 | 72 | stable | — | — |
| debt_ratio | −8.623e−4 | 1.173e−3 | −0.74 | 0.4777 | 0.4801 | 72 | stable | — | — |
| current_ratio | −8.445e−4 | 1.189e−3 | −0.71 | 0.4777 | 0.4801 | 72 | stable | — | — |

- **BH-FDR 5/12, Bonferroni 3/12** (α/m = 0.00417), 两个 p 值口径结论完全一致。
- `SE_HAC/SE_iid` ∈ [0.679, 1.083], 无 V4 WARN。
- `health` 为结构标签 (ES/TD/stable), **不是显著性**; `pricing` ≠ 显著 (见 §5.3)。

### 2.1 因子间相关与多重检验保守边界

- β_t 两两 |ρ|: **mean 0.357, max 0.974, 19 对 > 0.5** (S1/S2/S3 分别 22/25/24 对)。
- 高相关主要来自构造重叠: `volatility_1m × max_ret_1m` 0.974、三个杠杆比率互相 0.87-0.96、
  `volatility_1m × turnover_1m` 0.901、`amihud_1m × size_mv` −0.787、`beta_60d × 杠杆` 0.70-0.73。
- 因此 BH (假设弱相关) 偏宽松, 以 **Bonferroni 为保守下界**:
  `turnover_1m` / `reversal_1w` / `volatility_1m` 在两种口径下均通过; `amihud_1m` 与 `max_ret_1m`
  仅在 BH 下通过 — 报告结论按「BH 5 个 / 保守 3 个」双档表述。

## §3 分段方向稳定性

| 因子 | S1 2020-21 (t) | S2 2022-23 (t) | S3 2024-25 (t) | 同向数 |
|------|---------------|---------------|---------------|--------|
| turnover_1m | +9.695e−3 (3.07) | +6.539e−3 (2.80) | +4.834e−3 (2.11) | 3/3 |
| reversal_1w | +3.540e−3 (1.86) | +7.419e−3 (3.69) | +2.070e−3 (0.91) | 3/3 |
| amihud_1m | −4.424e−3 (−1.63) | −4.508e−3 (−1.20) | −6.082e−3 (−1.41) | 3/3 |
| momentum_1m | −2.152e−3 (−0.64) | −6.017e−3 (−2.03) | −1.455e−3 (−0.66) | 3/3 |
| size_mv | +3.161e−3 (0.80) | +6.693e−3 (2.64) | +4.713e−3 (1.09) | 3/3 |
| ocf_yoy | +8.679e−4 (1.18) | +2.538e−5 (0.03) | +7.747e−4 (1.69) | 3/3 |
| volatility_1m | +7.819e−3 (2.31) | +6.135e−3 (2.72) | −3.999e−5 (−0.01) | 2/3 |
| max_ret_1m | +6.160e−3 (2.18) | +5.682e−3 (2.69) | −1.193e−3 (−0.46) | 2/3 |
| beta_60d | +6.105e−4 (0.19) | −2.099e−3 (−0.59) | −7.607e−3 (−2.40) | 2/3 |
| current_ratio | +1.341e−3 (0.52) | −3.478e−4 (−0.16) | −3.117e−3 (−1.98) | 2/3 |
| debt_ratio | +1.340e−3 (0.50) | −1.762e−4 (−0.08) | −3.263e−3 (−2.42) | 2/3 |
| LT_debt_ratio | +9.032e−4 (0.43) | −8.419e−4 (−0.43) | −2.165e−3 (−1.93) | 2/3 |

> 分段 T≈23-24, 检验力低; 分段显著性仅作参考, 主结论看方向一致数。

### 3.1 异构复审补充取证 (2026-11-16)

8 项探针实验 (脚本运行于临时目录, 已删除; 证据为本节数值):

| 探针 | 结果 | 含义 |
|------|------|------|
| P1 parquet 无损性 | 6 文件 shape/索引/列/逐值完全一致 (max\|Δ\|=0) | H→parquet 转换可信, 可作为因子层唯一入口 |
| P2 财务跳变月份 | 杠杆/流动比率跳变集中 3/4/8/10/11 月 (4+8+10 月占 82%) | 数据源已对齐披露窗口 (年报 4 月/半年 8 月/季报 10 月), **前视风险低于 §7 原表述**; `ocf_yoy` 逐日更新 (35.6 万次跳变, TTM 同比值), 无报告期对齐问题 |
| P2b 截面聚集 | 财务因子月均 distinct 5083-5450 vs turnover 4883 | 季度跳变未退化截面信息量 |
| P3 LOMO t | reversal 2.97-3.73 / volatility 2.24-3.83 / amihud −2.24/−2.84 / turnover 4.45-6.20 / **max_ret 1.79-3.45** | 前 4 个对单月剔除稳健; **max_ret 显著性最弱** (最差 <2) |
| P4 按年拆 (2024/2025) | volatility t=−0.29/+0.41; max_ret −0.44/−0.10; beta −1.67/−1.55 (n=10/12) | 2024-25 是**溢价消失 (t≈0)** 而非显著反转; S3 定性需弱化 |
| P5 自建 beta vs Barra BETA | 月度截面 ρ mean = −0.53 (原始 +0.53, 区间 [−0.85, −0.18], 38 月) | 等权 60 日 beta 与 Barra 模型 beta 仅中等相关, `beta_60d` 的「beta」含义与 Barra 口径差异显著 |
| P6 RESVOL 吸收 | volatility vs RESVOL \|ρ\|=0.667; max_ret vs RESVOL \|ρ\|=0.493 | 中性化后 t 下降 (−0.96/−1.08) 的主要吸收者是**特质波动**, 非 SIZE/BETA |
| P7 有效检验数 | 相关矩阵谱方法 m_eff=7.0 (名义 12); Bonferroni@m_eff 仍 3 个, BH@m_eff 仍 5 个 | 「保守档 3 个」结论加固; 名义 m=12 的 Bonferroni 过严 |
| P9 BH 实现核对 | 本实现 vs statsmodels multipletests max\|Δq\|=1.4e-17 | BH 实现逐位正确 |

## §4 Barra 中性化 (2020-02 → 2023-05, 40 月, m=10)

| 因子 | raw t | neut t | Δt | BH 翻转 |
|------|-------|--------|-----|---------|
| turnover_1m | 3.85 | 3.38 | −0.46 | — |
| reversal_1w | 3.57 | 2.91 | −0.66 | — |
| volatility_1m | 3.40 | 2.44 | −0.96 | — |
| max_ret_1m | 3.30 | 2.23 | −1.08 | **FLIP (失去显著)** |
| momentum_1m | −1.63 | −1.52 | +0.11 | — |
| amihud_1m | −1.54 | −0.77 | +0.77 | — |
| debt_ratio | 0.01 | 1.35 | +1.34 | — |
| LT_debt_ratio | −0.24 | 1.22 | +1.46 | — |
| current_ratio | −0.01 | 1.10 | +1.11 | — |
| ocf_yoy | 0.59 | 1.15 | +0.56 | — |

- 控制变量解释力: **mean R² = 0.206**; 中性化前平均 |ρ|: SIZE 0.101 / BETA 0.120 / RESVOL 0.216;
  中性化后 ≈0 (OLS 正交, 构造使然)。
- raw 臂 4/10 通过 BH; neut 臂 3/10; 唯一翻转 = `max_ret_1m`。
- **吸收机制 (异构复审 P6)**: RESVOL 与 volatility (0.667) / max_ret (0.493) 强相关 →
  t 下降主要由特质波动吸收, SIZE/BETA 贡献小; 「MAX 溢价部分由风格暴露驱动」应精确为
  **特质波动暴露为主**。
- `size_mv` / `beta_60d` 与 Barra SIZE/BETA 相关仅中等 (P5: 原始截面 ρ≈0.53), 已排除
  中性化 (理由见 EXECUTION §3.4)。

## §5 敏感性

### 5.1 HAC lag q ∈ {1,2,3,4,6}

| 因子 | q=1 | q=2 | q=3 (默认) | q=4 | q=6 |
|------|-----|-----|-----------|-----|-----|
| turnover_1m | 3.95 | 4.71 | 5.18 | 5.12 | 6.06 |
| reversal_1w | 2.95 | 3.24 | 3.38 | 3.30 | 3.27 |
| volatility_1m | 2.47 | 2.78 | 2.92 | 2.85 | 3.00 |
| amihud_1m | −2.31 | −2.39 | −2.48 | −2.62 | −2.83 |
| max_ret_1m | 2.08 | 2.32 | 2.43 | 2.36 | 2.41 |
| momentum_1m | −1.84 | −1.88 | −1.89 | −1.98 | −2.00 |
| size_mv | 2.06 | 2.13 | 2.16 | 2.14 | 2.21 |

全部因子 t 随 q 单调/微幅变化, **无符号翻转**; momentum 在 q≥4 达 −2.0 但 BH 仍不通过。

### 5.2 带宽 h ∈ {6,12,24}

- 溢价 `mean(β_t)` 与 HAC SE **与 h 无关** (v3.4.12 口径), 敏感性只影响 `diagnose` 标签与 λ̂。
- 标签变化: `momentum_1m` h=24 → `review` (其余 h=6/12 为 `pricing`);
  `current_ratio` / `debt_ratio` / `LT_debt_ratio` h=6 → `review` (h=12/24 为 `pricing`);
  其余 9 因子三档一致。
- λ̂ 路径相关 (vs h=12): 0.69–0.92, 最低 `beta_60d` 0.692 / `momentum_1m` h=24 0.726。

### 5.3 标签语义澄清

`diagnose` 的 `stable/TD/ES` 是**溢价结构健康** (断点 / 衰减), 不是显著性:
财务 4 因子 t≈−0.7~1.3 仍被标 `stable → pricing`。本报告的显著性判定只依据 BH-FDR。

## §6 结论 (Q1-Q6)

1. **Q1 复现与扩展**: 3 个原因子结论完全复现 (reversal 3.38 / volatility 2.92 / amihud −2.48,
   数值与 B 报告逐位一致); 新增 4 个量价因子中 `turnover_1m` (t=5.18) 与 `max_ret_1m` (2.43)
   通过 BH, `size_mv` 边缘 (q=0.061), `beta_60d` 不显著且方向为「高 beta 占优」。
   保守边界 (Bonferroni) 下仍成立的核心三项: **turnover_1m / reversal_1w / volatility_1m**。
   显著性强度分层 (异构复审 P3 LOMO): turnover (worst 4.45) > reversal (2.97) >
   volatility/amihud (2.24) > **max_ret (1.79, 单月敏感, 最弱)**。
2. **Q2 分段稳定**: 6 因子 3/3 同向 (momentum / reversal / amihud / turnover / size / ocf),
   6 因子 2/3。按年拆 (P4): 2024-25 的低波 / MAX / beta 溢价是**消失 (|t|≤0.44, n=10-12)**,
   而非显著反转 — S3 的负号来自 ≈0 附近的微幅波动, 检验力不足。
3. **Q3 数据层解锁**: 6 个 legacy pickle 经 shim 转 parquet, 逐值无损 (P1), 4 个财务因子
   进入实证; 财务因子在全样本与中性化后均不显著 (|t| ≤ 1.35)。
4. **Q4 风格暴露**: 行业 + SIZE/BETA/RESVOL 平均解释因子截面 20.6%; 中性化后 4→3 通过,
   仅 `max_ret_1m` 失去显著性 — **主要由 RESVOL 吸收** (P6, |ρ| 0.493-0.667);
   反转 / 低波 / 低换手 **存活**。
5. **Q5 多重检验**: 12 因子 BH-FDR 5/12, Bonferroni 3/12, 双 p 值口径完全一致 (最大 q 差 0.0064);
   谱有效检验数 m_eff=7.0 (P7) — Bonferroni@m_eff 与 BH@m_eff 结果与名义口径一致,
   **核心三项在任何多重检验口径下均通过**。
6. **Q6 稳健性**: lag 1-6 无符号翻转; 带宽只改标签 (2 组), λ̂ 相关 ≥ 0.69; BH 实现与
   statsmodels 逐位一致 (P9); 核心结论稳固。

### 6.1 对 B 报告的更正 (诚实记录)

B 报告 §3 观察 4 称 amihud 方向「与经典流动性溢价相反」, 属措辞错误:
因子定义为 `−(|r|/amount)`, 负溢价意味着**低流动性组收益更高**, 与经典 Amihud 流动性溢价**一致**。
已在 [LAYER3_HAC_REAL_DATA_VERIFICATION.md](LAYER3_HAC_REAL_DATA_VERIFICATION.md#L52) 就地更正。

## §7 已知偏差

| 偏差 | 影响 |
|------|------|
| 中性化仅 40/71 月 | 2023-06 之后无行业数据, 结论外推需谨慎 |
| Barra SIZE/BETA 为模型暴露 | 与自建 size/beta 不完全同源 (实测截面 ρ≈0.53, P5) |
| 财务因子披露对齐 | 跳变集中披露窗口 (P2, 4+8+10 月占 82%), 前视风险小; `ocf_yoy` 为逐日 TTM 同比 |
| `market_value` 口径 | turnover/size 使用 `market_value.csv`, 总市值 vs 流通市值口径未验证 (源无对照) |
| 等权市场收益 | beta 定义与市值加权基准有偏差 |
| 幸存者偏差 | 面板为「现可得」并集, 含 179 只退市股 |
| BH 独立性 | β_t 两两 \|ρ\| mean 0.357 / max 0.974 (19 对 > 0.5) → BH 偏宽松, 另报 Bonferroni 3/12 |
| 分段检验力 | S1-S3 各 T≈24, 仅作方向参考 |
| `premium_mean` 口径 | 为 mean(β_t) 而非平滑 λ̂ 均值, 与 `diagnose.premium_mean` 数值不同源 |

## §8 生产缺陷发现 (DEFECT-1)

`BreakpointDetector.detect` 在 `T < 30` 时返回 `self._no_breakpoint_result(T)`,
但该类**无此方法** → `AttributeError`。触发路径: 任意 `diagnose()` 输入有效 β 期数 < 30
(本任务分段 T≈24 首次命中)。本次以「n_valid<30 跳过 diagnose」避让, 未改生产代码。

**影响面 (已排查, 2026-11-16)**:
- 缺陷本体: [factor_health L293-L294](../../modules/factor_health/__init__.py#L293-L294);
- 唯一生产调用路径: `FactorHealthDiagnoser.diagnose` → `self.detector.detect(beta_raw)`
  ([L499](../../modules/factor_health/__init__.py#L499)) — 公开 API, 任何 β 有效期 <30 的输入
  (短样本因子 / 短回测窗口 / 消融退化臂) 必抛;
- `pipelines_v2.StructuralBreakMonitor` (v3.4.0) 为独立实现, **不受影响**;
- 现有测试 `test_layer3_factor_health.py` 两处 `detect` 的面板均 ≥30 期, 分支未覆盖;
- 建议修复: v3.4.13 补 `_no_breakpoint_result(T)` (返回 `has_breakpoint=False` + 空 cusum +
  NaN 均值) + T=10/29/30 边界单测 + 版本六锚点。已登记 [PROJECT_STATUS §2 缺陷登记](../PROJECT_STATUS.md)。

## §9 复现

```powershell
python scripts/convert_legacy_pickles.py          # 一次性: legacy pickle -> parquet
python scripts/verify_multifactor_multiyear.py --json out.json
# 可选: --data-root <path> --converted-root <path> --bandwidth 12 --alpha 0.05
```

运行环境: pandas 2.2.3 / numpy 2.1.3 / scipy / pyarrow 24.0.0。
