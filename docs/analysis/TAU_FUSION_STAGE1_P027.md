# τ 融合 Stage 1 探针（P-027）

> **日期**：2026-11-24
> **批次**：P-027 Stage 1（固定输入阶段）
> **性质**：只读探针；**未改生产代码**；脚本不导入 `factor_pipeline`，直接读取 `E:\Ashare_data`
> **固定输入阶段**：`construction_id = winsor_rank_z`（1/99 缩尾 → rank→normal → zscore，月末），最接近生产 Static 变换的全样本口径
> **上游**：[路线裁决 §13](ENDOGENEITY_PREMIUM_GOVERNANCE_ANALYSIS.md#L591-L651) / [P-028 EIV 诊断](EIV_SENSITIVITY_P028.md)
> **工件**：`out/p027_stage1_probe.py` / `out/p027_stage1_probe.json`

---

## §1 目的

按 §13.3 的预注册门槛，用真实 A 股数据回答：

1. 默认 E3 分量（Oster δ + AET）在固定输入阶段上产出什么样的 τ 分布？
2. 权重扰动下 τ 的档位是否稳定？加权平均与 `max` 规则是否一致？
3. τ 是否与溢价不稳定性相关（外部效度）？

**不在范围**：τ 接线、Layer 3 交互、生产代码、因果识别。

---

## §2 方法与口径

| 项 | 口径 |
|---|---|
| 因子 | 12 个量价因子：momentum 1m/3m/6m、reversal 1w、high_52w、volatility 1m/3m、amihud 1m/3m、turnover_1m、max_ret_1m、low_beta_1m |
| 数据 | `E:\Ashare_data`，2020-01-02 → 2026-01-30；月末横截面；下月前瞻收益；上市满 365 日；月内有效股票 <300 剔除；`|r|>1` 剔除 |
| 固定阶段 | 每月 1/99 缩尾 → rank→normal → zscore（`winsor_rank_z`） |
| τ 分量 | Oster (2019) δ（`r_max=1.3R²_c`、`threat_threshold=0.1`，τ 映射 0.1/0.9/1−\|δ\|）；AET (2005) selection ratio（τ=min(1,\|SR\|)） |
| 控制变量 | `size_z`（log 市值 zscore）+ 其他 11 个因子面板（zscore，NaN→0）；按 E3 的 pooled OLS 口径 |
| 默认 τ | `(0.4·τ_oster + 0.3·τ_aet) / 0.7`（仅启用 Oster+AET） |
| 档位 | none <0.3；mild <0.7；strong ≥0.7 |
| G1 | 加权平均 vs `max(τ_oster, τ_aet)` 的档位一致率 ≥90% |
| G2 | Dirichlet(4,3) 1000 次权重扰动：档位翻转率 ≤10%，τ Spearman 中位数 ≥0.90 |
| G3 | τ vs 溢价不稳定性（`sign_flip_rate`）：Spearman >0 且单侧置换 p<0.05；bootstrap 95% CI |
| 溢价 | 复刻 `PremiumEstimator`：逐期截面 OLS + Epanechnikov（h=12）+ HAC SE |

> **控制设计说明**：主设计使用「size + 其他因子」的多因子控制集；这不是 `check_endogeneity(controls=None)` 的默认路径，而是可选的 E3 控制场景。默认无控制路径的代码行为见 §6。

---

## §3 逐因子结果

| 因子 | τ_oster | τ_aet | τ_default | 档位 | τ_max | premium | t | sign_flip |
|---|---:|---:|---:|---|---:|---:|---:|---:|
| amihud_1m | 0.100 | 1.000 | 0.486 | mild | 1.000 | −0.01721 | −3.11 | 0.014 |
| amihud_3m | 0.615 | 0.297 | 0.478 | mild | 0.615 | −0.01701 | −3.43 | 0.014 |
| high_52w | 0.100 | 1.000 | 0.486 | mild | 1.000 | −0.00514 | −0.90 | 0.056 |
| low_beta_1m | 0.100 | 1.000 | 0.486 | mild | 1.000 | −0.00709 | −1.27 | 0.014 |
| max_ret_1m | 0.100 | 1.000 | 0.486 | mild | 1.000 | 0.01049 | 2.42 | 0.028 |
| momentum_1m | 0.100 | 1.000 | 0.486 | mild | 1.000 | −0.00730 | −1.45 | 0.042 |
| momentum_3m | 0.100 | 1.000 | 0.486 | mild | 1.000 | −0.00891 | −1.79 | 0.056 |
| momentum_6m | 0.100 | 1.000 | 0.486 | mild | 1.000 | −0.00982 | −1.70 | 0.042 |
| reversal_1w | 0.100 | 1.000 | 0.486 | mild | 1.000 | 0.01075 | 3.10 | 0.014 |
| turnover_1m | 0.100 | 1.000 | 0.486 | mild | 1.000 | 0.01302 | 2.99 | 0.000 |
| volatility_1m | 0.900 | 1.000 | 0.943 | strong | 1.000 | 0.01268 | 2.68 | 0.028 |
| volatility_3m | 0.100 | 1.000 | 0.486 | mild | 1.000 | 0.01113 | 2.26 | 0.056 |

---

## §4 预注册门槛

| 门槛 | 读数 | 判定 |
|---|---|---|
| **G1 聚合一致性** | 2/12 = **16.7%** | ❌ 失败（<90%） |
| **G2 权重稳健性** | 翻转率 **18.8%**；Spearman 中位数 1.000、5% 分位 0.091 | ❌ 失败（翻转率 >10%） |
| **G3 外部效度** | ρ=**0.183**，单侧 p=**0.317**，bootstrap CI **[−0.293, 0.541]** | ❌ 失败（p≥0.05，CI 含 0） |

**Stage 2 判定（按 §13.2 预注册规则）**：三项全失败 → **τ 仅展示，不升级为决策标量；E5 保持 experimental；P-009 关闭为「不实现」**。

---

## §5 发现

**F-1｜分量几乎二值化。**
12 个因子中 10 个是 `τ_oster=0.100`、`τ_aet=1.000` 的极端组合；只有 `amihud_3m`（0.615/0.297）和 `volatility_1m`（0.900/1.000）不同。Oster 的 0.1/0.9 分段映射与 AET 的 \|SR\| 截断共同造成「分量只取少数离散值」。

**F-2｜加权平均把 10/12 因子压到 mild，max 规则判 strong。**
默认 τ≈0.486 → mild；`max`=1.0 → strong。G1 只有 2/12 一致（`amihud_3m`、`volatility_1m`）。这说明加权平均在补偿型聚合下系统性地「抹平」强威胁。

**F-3｜权重扰动翻转率 18.8%，绑定失败项是档位而非排序。**
Dirichlet 扰动下 Spearman 中位数仍为 1.0（排序大多保持），但 τ 在 0.486 附近，权重稍偏向 AET 就越过 0.7；18.8% 的 (draw, factor) 发生档位翻转。

**F-4｜τ 与溢价不稳定性无显著关联。**
主指标 `sign_flip_rate` 的 ρ=0.183、p=0.317；次指标 `premium_cv` 的 ρ=0.118。12 个因子中只有 `volatility_1m` 在分量和外部指标上都偏「高威胁」，不足以支持 τ 的判别力。

**F-5｜默认无控制路径是退化的。**
按代码事实：`controls=None` 时 Oster 的 β_c=β_u、R²_c=R²_u → τ_oster=0（[oster_delta.py L104-L117](../../modules/endogeneity_check/core/oster_delta.py#L104-L117)）；AET 无嵌套控制 → τ_aet=0.5（[aet_checker.py L43-L46](../../modules/endogeneity_check/core/aet_checker.py#L43-L46)）。默认 τ = 0.4·0 + 0.3·0.5 / 0.7 = **0.214（none）**，`max`=0.5（mild），全部因子相同，**没有任何区分度**。因此「无控制」和「多因子控制」两种设计都不能支撑决策标量。

**F-6｜固定输入阶段本身是必要的，但不能挽救 τ。**
本探针已固定 `winsor_rank_z`，排除了 P-028 发现的构造敏感性；τ 仍然不可用。问题在融合层，不在输入阶段。

---

## §6 控制设计边界

- 主设计控制集 = size + 其他 11 个因子，属于多因子控制场景；同族因子（momentum 1m/3m/6m、volatility 1m/3m、amihud 1m/3m）存在共线性，可能放大 AET 的 selection ratio。
- 默认 `controls=None` 路径按代码事实退化（F-5），无法产生区分度。
- 因此当前证据足以判定「τ 不可作为决策标量」，但**不足以**给出「在最优控制设计下 τ 的判别力」的最终结论；若未来重启，应先做控制设计敏感性（size-only / 去同族 / 行业窗口）。
- 本报告不据此声称任何因子「真正内生」或「真正稳健」；Oster/AET 只是威胁诊断。

---

## §7 对路线的影响

1. **Stage 2 判定**：G1/G2/G3 全失败 → τ 仅展示；不新增消费者；P-009 关闭为「不实现」。
2. **Stage 0b 已收口**：披露字段（`weights_version` / `effective_weights` / `s4_input_stage` / `stage_fallback` / E5 `experimental`）已实施并验证——C2/C3/C4 + E5-T18/T19 **5 passed**、内生性两模块 **55 passed**、全量回归 **2274 passed / 36 skipped / 0 failed**，包版本 **3.11.2**；用于「τ 仅展示」场景的可追溯性。
3. **E5 定位**：保持 opt-in + experimental；文档不得表述为「内生性已修正」。
4. **未来重启条件**：① 控制设计敏感性完成；② 出现新的外部准则（溢价不稳定性标签 / 决策损失）；③ 聚合规则改为非补偿并通过 G1/G2/G3。否则不再投入 τ 融合。

---

## §8 限制与复现

- 12 个量价因子；带宽固定 12；月末 FM；无时间固定效应；未启用 IFE/Lewbel（默认 opt-in 关闭）；未跑 S1 缺失机制（默认关闭）。
- G3 的 N=12，置换检验功效有限；ρ 不显著不等于「无关系」，但足以阻止升级。
- Oster/AET 为独立复刻（pooled OLS，与 E3 同口径），未与仓内 `check_endogeneity` 对拍（工作区 untrusted）。
- 工件：`out/p027_stage1_probe.py`、`out/p027_stage1_probe.json`；运行需可信环境 + `E:\Ashare_data`。
