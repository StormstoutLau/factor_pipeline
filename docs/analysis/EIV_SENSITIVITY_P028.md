# EIV 构造敏感性只读诊断（P-028 Wave 1）

> **日期**：2026-11-24
> **批次**：P-028（EIV 适用性与 remedy 审计）Wave 1 执行
> **性质**：只读探针；**未改生产代码**；脚本不导入 `factor_pipeline`，直接读取 `E:\Ashare_data`
> **上游**：[P-028 SESSION](../../spec/p028-eiv-applicability-audit/SESSION.md) / [分析 §12.7](ENDOGENEITY_PREMIUM_GOVERNANCE_ANALYSIS.md#L536-L564)
> **工件**：`out/eiv_sensitivity_p028.py` / `out/eiv_sensitivity_p028.json`

---

## §1 目的与范围

P-028 审计结论是「Shanken 不适用、外部 IV 不可得、衰减系数不可识别」，并建议 Wave 1 用**构造变体敏感性**替代硬修正。本报告执行该建议，回答：

1. 同一因子在不同构造（缩尾 / rank→normal / 市值中性化 / 行业+市值中性化）下，溢价估计是否稳定？
2. 若不稳，主要来源是缩尾、分布变换，还是暴露中性化？
3. 这是否足以支持在 P-027 Stage 1 / P-009 之前先固定「因子输入阶段」？

**不在范围**：因果识别、EIV 硬修正、生产接线、τ 融合。

---

## §2 方法与口径

| 项 | 口径 |
|---|---|
| 数据 | `E:\Ashare_data\market_data`：close / adj / amount / list_date / market_value / stock_ind；2020-01-02 → 2026-01-30 |
| 因子 | 4 个量价因子：`momentum_1m` / `reversal_1w` / `volatility_1m` / `amihud_1m`（与 `scripts/verify_layer3_hac_real.py` 同口径） |
| 频率 | 月末横截面；下月前瞻收益 `price_m.shift(-1)/price_m − 1`；上市满 365 日；月内有效股票 <300 剔除；`|r|>1` 剔除 |
| 估计器 | 复刻 [PremiumEstimator](../../modules/factor_health/__init__.py#L30-L60)：逐期横截面 OLS 斜率 β_t → Epanechnikov 核平滑（h=12）→ λ̂(t)；HAC（Newey-West, Bartlett）计算 premium_mean SE |
| 变体 | `raw_z`（不缩尾→zscore）、`winsor_z`（1/99 缩尾→zscore，当前预处理口径）、`rank_z`（raw→rank→normal）、`winsor_rank_z`（缩尾→rank→normal）、`size_neutral_z`（缩尾→市值中性化→zscore）、`size_rank_z`（缩尾→市值中性化→rank→normal） |
| 补充 | `ind_size_neutral_z`（缩尾→行业+市值中性化→zscore），仅行业数据可得的 2020-01 → 2023-06 |
| 尺度 | 所有变体最终 zscore，溢价按「每 1 个截面标准差」比较；rank 变体的 `mean_cs_std` 约 0.93-0.96（约 4-7% 尺度差，不足以解释 2-3 倍差异） |
| 预注册规则 | `range_rel = (max premium − min premium) / |median premium|`；`sensitive = range_rel > 0.5` 或分量符号不一致或 t 显著性翻转 |

> **边界**：带宽固定 12；未做 24 的稳健性；未做多重检验；行业数据 2023-06 后缺失，行业变体只在共同窗口比较；脚本为独立复刻，未与仓内 `estimate_with_errors` 对拍（工作区 untrusted，未执行仓内代码）。

---

## §3 全样本结果（2020-01 → 2026-01，68-70 个有效月）

### 3.1 溢价均值（t 值）

| 因子 | raw_z | winsor_z | rank_z | winsor_rank_z | size_neutral_z | size_rank_z |
|---|---:|---:|---:|---:|---:|---:|
| momentum_1m | −0.00325 (−1.92) | −0.00326 (−1.91) | −0.00745 (−1.50) | −0.00730 (−1.45) | −0.00298 (−1.82) | −0.00657 (−1.42) |
| reversal_1w | 0.00400 (3.40) | 0.00409 (3.38) | 0.01031 (2.99) | 0.01075 (3.10) | 0.00372 (3.32) | 0.00873 (2.67) |
| volatility_1m | 0.00483 (3.02) | 0.00471 (2.94) | 0.01254 (2.68) | 0.01268 (2.68) | 0.00498 (3.34) | 0.01244 (2.79) |
| amihud_1m | −0.00234 (−1.48) | −0.00500 (−2.54) | −0.01688 (−3.08) | −0.01721 (−3.11) | −0.00306 (−1.98) | −0.00635 (−1.86) |

### 3.2 分解

| 因子 | 缩尾效应 (winsor/raw−1) | rank 效应 (winsor_rank/winsor−1) | 市值中性化效应 (size/winsor−1) | size 后 rank 效应 (size_rank/size−1) | `range_rel`（不含 rank） | `range_rel`（全部） | 判定 |
|---|---:|---:|---:|---:|---:|---:|---|
| momentum_1m | −0.3% | **+124.0%** | −8.5% | **+120.6%** | 8.6% | 90.9% | sensitive |
| reversal_1w | +2.2% | **+163.0%** | −9.0% | **+134.5%** | 9.2% | 109.8% | sensitive |
| volatility_1m | −2.5% | **+169.0%** | +5.6% | **+150.0%** | 5.4% | 91.5% | sensitive |
| amihud_1m | **+113.8%** | **+244.4%** | **−38.8%** | **+107.7%** | **86.9%** | 262.0% | sensitive（t 翻转） |

---

## §4 行业窗口结果（2020-01 → 2023-06，40-42 个有效月）

同一窗口内比较，避免全样本与行业窗口混用：

| 因子 | winsor_z | size_neutral_z | ind_size_neutral_z | ind vs winsor | λ̂ 秩相关（ind vs winsor） |
|---|---:|---:|---:|---:|---:|
| momentum_1m | −0.00487 (−1.91) | −0.00439 (−1.78) | −0.00374 (−2.23) | −23.2% | 0.963 |
| reversal_1w | 0.00481 (3.29) | 0.00458 (3.26) | 0.00335 (2.88) | −30.3% | 0.922 |
| volatility_1m | 0.00768 (3.92) | 0.00761 (3.86) | 0.00635 (4.27) | −17.3% | 0.687 |
| amihud_1m | −0.00276 (−1.65) | −0.00078 (−0.57) | −0.00098 (−0.82) | **−64.5%** | **0.207** |

> 该窗口内 winsor 的 amihud t 仅 −1.65；ind+size 后为 −0.82。不能表述为「原本显著、中性化后不显著」，应表述为「该窗口内 amihud 溢价本身较弱，行业+市值中性化后进一步收缩」。

---

## §5 发现

**F-1｜缩尾对 3/4 因子几乎无影响，但 amihud 例外。**
momentum / reversal / volatility 的 raw→winsor 差异在 ±3% 内；amihud 的溢价从 −0.00234 变为 −0.00500（+114%），t 从 −1.48 变为 −2.54。amihud 的溢价由少数极端值显著驱动。

**F-2｜rank→normal 是最大的一阶来源。**
在相同缩尾条件下，rank 变换使溢价幅度增加 **124% / 163% / 169% / 244%**（四因子）。3/4 因子的 λ̂ 轨迹秩相关仍高（0.96-0.985），说明主要是尺度/曲率变化；amihud 的秩相关降到 **0.127**，说明轨迹本身也改变。

**F-3｜市值中性化对 3/4 因子是二阶效应。**
3/4 因子 size/winsor 变化在 −9% ~ +6%；amihud 为 −38.8%，t 从 −2.54 降到 −1.98。行业+市值中性化在 2020-2023 窗口进一步把 amihud 收缩 64.5%，λ̂ 秩相关仅 0.207。

**F-4｜按预注册规则，4/4 因子都被判定为构造敏感。**
`range_rel`（全部变体）0.91-2.62，全部 >0.5。若剔除所有 rank 变体，只有 amihud（86.9%）仍敏感，其余三因子 <10%。

**F-5｜溢价不是「构造不变」量。**
`PremiumEstimator` 对因子的单调变换不具不变性；溢价只在「给定构造」下有定义。rank→normal 恰好是当前 Static 管道的默认变换，因此**生产输入阶段不同，Layer 3 的 premium / premium_health 不可直接比较**。

**F-6｜这支持 P-027 Stage 1 的「阶段绑定」前置，而不是支持 Shanken 修正。**
问题不是「β 估计误差的 generated-regressor 偏差」，而是「因子构造/尺度未声明」。先固定输入阶段，再谈 τ 与标签的交互。

---

## §6 解释与边界

- **不是经典 EIV 衰减**：缩尾/中性化/rank 改变的是因子的截面分布与暴露，不是单纯的测量误差方差；因此不能用 reliability ratio 或 Shanken 修正「修好」。
- **rank 变体的尺度检查**：`mean_cs_std` 0.93-0.96，折算成 1 sd 只增加约 4-7%，不能解释 2-3 倍差异；差异来自单调变换下的曲率/权重变化。
- **amihud 的特殊性**：缩尾、市值中性化、行业中性化、rank 四个方向都能显著改变其溢价，属于「构造高度敏感」因子；在任何治理标签使用前应单列。
- **限制**：仅 4 个量价因子；带宽固定 12；月末 FM；行业数据止于 2023-06；未做 24 带宽、未做多重检验、未与仓内 `estimate_with_errors` 对拍（工作区 untrusted）。

---

## §7 对 P-027 / P-009 的影响

1. **P-027 Stage 1 必须先固定因子输入阶段**：至少声明 `construction_id`（raw / winsor / rank / size-neutral / ind-size-neutral）与 `premium_stage`；否则 τ 与 premium 的联动没有可比性。
2. **P-009 的 B1（阶段口径）得到实测支持**：在没有 `tau_stage` ↔ `diagnose` 输入阶段绑定前，不应启动交互。
3. **不建议 Shanken / 硬修正**：本诊断再次确认 P-028 的裁决；Wave 1 的交付物就是「敏感性披露」，不是「修正后的溢价」。
4. **amihud 单列**：若未来需要 Layer 3 标签，amihud 类因子应先做构造稳定性复核，或明确标注 `construction_sensitive=True`。

---

## §8 复现

| 工件 | 路径 |
|---|---|
| 探针脚本（独立复刻，不导入本包） | `out/eiv_sensitivity_p028.py` |
| 完整结果 JSON | `out/eiv_sensitivity_p028.json` |
| 运行方式（需可信环境 + `E:\Ashare_data`） | `python out/eiv_sensitivity_p028.py` |

> 脚本为**只读研究工件**，不是生产代码，不进入 `fit/transform`，不新增依赖，不改变默认路径。
