# RESEARCH HAC 检验 NaN 过滤 (HAC_NAN_FILTER)

> **版本**: v1.0 (2026-11-16)
> **调研工具**: `mcp_paper-search` (Semantic Scholar / OpenAlex / Crossref) + 源码静态核对
> **上游**: [MAD 实验 §6 O1](../analysis/MAD_WINSORIZE_O1_EXPERIMENT.md) /
> [PROJECT_STATUS §2 P2](../PROJECT_STATUS.md)
> **范围**: `backtest/ablation_runner.py::ledoit_wolf_hac_test` 在收益序列含 NaN 时
> 静默返回 NaN 的缺陷; 不涉及 HAC 估计量本身的重构, 也不涉及 bootstrap 路径。

## §1 调研问题清单

- **Q1**: NaN 从哪来? 为什么 `ledoit_wolf_hac_test` 会静默返回 NaN?
- **Q2**: 对含缺失观测的时序做 HAC 估计, 「删除缺失后按等间隔处理」(drop-and-compress)
  是否有学术依据? 与「保留时间空隙」相比偏差/方差如何?
- **Q3**: 删除缺失应**逐序列独立**还是**成对联合**? 对本函数的 ΔSR 检验有何影响?
- **Q4**: 清洗后的样本量 `n` 是否应作为 Newey-West 带宽 `q` 与矩条件的基数?
- **Q5**: 有效配对不足时应返回什么? 与现有退化约定是否一致?
- **Q6**: 该修复对无缺失输入是否零影响?
- **Q7**: 同模块的 `mean_diff_hac_statsmodels` 是否属于同一修复范围?

## §2 学术文献调研

| 引用 | 标识 | 关键结论 | 状态 |
|------|------|---------|------|
| Newey & West (1987), Econometrica 55(3):703 | DOI: 10.2307/1913610 | Bartlett 核 HAC 协方差; 本实现的核与带宽公式来源 | ✅ VERIFIED (Crossref) |
| Ledoit & Wolf (2008), J. Empirical Finance 15(5):850-859 | DOI: 10.1016/j.jempfin.2008.03.002 | Sharpe 差的 delta method + HAC 检验; 本函数 H0: SR_a = SR_b 的来源 | ✅ VERIFIED (Crossref) |
| Datta & Du (2012), IFDP 2012(1060):1-48, Fed | DOI: 10.17016/ifdp.2012.1060 | 含缺失观测的 HAC: 提出 Amplitude Modulated (AM) 与 Equal Spacing (ES) 两个一致估计量; **ES = 把观测序列按等间隔处理后再套 Newey-West**; Monte Carlo 中 ES 多数情形偏差更低, AM 仅在小样本 + 低自相关时方差更低 | ✅ VERIFIED (Crossref, 摘要) |

**对 Q2 的结论**: 本项目拟采用的「删除缺失 → 压缩为等间隔序列 → 按原公式估 HAC」
即 Datta & Du (2012) 的 **Equal Spacing 估计量**, 具有渐近一致性; 原文 Monte Carlo
显示其多数情形优于 AM (偏差更低)。因此该修复不是权宜之计, 而是有文献支撑的一致估计量。

**口径边界**: 原文指出「仅用观测数据直接估谱」的朴素做法会导致错误推断, 其修正正是
ES/AM 两个估计量。本实现选择 ES (改动最小、与现有 Newey-West 代码逐行一致);
未实现 AM (需按缺失指示变量调整核权重), 记为观察项 (见 §4 O1)。

**对本项目的适用性**: MAD 实验中 LS/IC 序列各仅含 1 个 NaN (241/11 期),
缺失比例 0.4% / 9%; ES 的偏差优势在此量级缺失下占主导, AM 的方差优势不构成理由。
月频 n=11 且缺 1 期时有效样本 10, 仍高于本函数的最小观测门槛 (Q5)。

## §3 工程事实 (F1-F12)

| # | 事实 | 证据 |
|---|------|------|
| F1 | `ledoit_wolf_hac_test` 入口仅做 `np.asarray` + 长度对齐, **无任何 NaN/Inf 过滤**; 后续 `np.mean` / `np.std` / 矩条件均被 NaN 污染 | [ablation_runner.py L68-L141](../../backtest/ablation_runner.py#L68-L141) |
| F2 | 返回 `(float(t_stat), float(p_value))`, NaN 会原样传出 (不抛异常) | [ablation_runner.py L137-L141](../../backtest/ablation_runner.py#L137-L141) |
| F3 | `compare` 用 `ls_return_series` 调 HAC; `p_value_hac` 直接写入 `AblationComparison` | [ablation_runner.py L1339-L1343](../../backtest/ablation_runner.py#L1339-L1343) |
| F4 | `compare` 已有 P0-1 兜底: `p_hac` 为 NaN 时 `is_significant` 退回仅看 bootstrap | [ablation_runner.py L1385-L1394](../../backtest/ablation_runner.py#L1385-L1394) |
| F5 | `compare_all` 的 BH-FDR 分母用 **bootstrap p**, 不用 HAC p; HAC 仅作显著性门控 | [ablation_runner.py L1429-L1452](../../backtest/ablation_runner.py#L1429-L1452) |
| F6 | `AblationResult.ls_return_series` / `ic_series` 类型为 `np.ndarray` | [ablation_runner.py L362-L373](../../backtest/ablation_runner.py#L362-L373) |
| F7 | `compute_long_short_returns` 预填 `np.full(n_periods-1, np.nan)`; 每期有效配对 `< MIN_VALID_PAIRS` 时保留 NaN | [factor_metrics.py L323-L333](../../backtest/factor_metrics.py#L323-L333) |
| F8 | `compute_ic_series` 同样预填 `np.full(n_periods-1, np.nan)`, 无效期保留 NaN | [factor_metrics.py L149](../../backtest/factor_metrics.py#L149) |
| F9 | `_compute_metrics` 对多因子取 `np.nanmean` 聚合, 但**聚合后仍可能残留 NaN** (该期所有因子均无效) | [ablation_runner.py L850-L861](../../backtest/ablation_runner.py#L850-L861) |
| F10 | MAD 实验实测: LT 的 LS/IC 序列各含 1 个 NaN → `compare` 的 HAC t/p 均为 NaN; 已用 NW 截距 t 补算 | [MAD 实验 §6 O1](../analysis/MAD_WINSORIZE_O1_EXPERIMENT.md) |
| F11 | `circular_block_bootstrap._stat` 对每条序列**各自** `~np.isnan` 过滤 (均值统计量, 不要求成对) | [ablation_runner.py L210-L230](../../backtest/ablation_runner.py#L210-L230) |
| F12 | `mean_diff_hac_statsmodels` 仅被 `tests/test_backtest/test_ablation_runner.py` 调用, 生产路径无引用 | grep `mean_diff_hac_statsmodels` 全仓 6 处, 其中 5 处为文档/定义 |

## §4 分析

### 4.1 Q3: 必须成对联合删除

本函数检验的统计量是 ΔSR, 其方差为

```
Var(ΔSR) = Var(SR_a) + Var(SR_b) - 2·Cov(SR_a, SR_b)
```

其中 `Cov` 由交叉矩条件 `h_a,t ⊗ h_b,t` 估计。若对两条序列**各自独立**删除 NaN,
则 `h_a` 与 `h_b` 的第 t 行不再对应同一时刻 → 交叉协方差无意义。
因此掩码必须是 `isfinite(a) & isfinite(b)` 的**联合掩码** (complete-case pairing)。

### 4.2 Q4: 清洗后的 n 作为基数

带宽 `q = max(1, int(4·(n/100)^(2/9)))` 与所有 `/ T` 归一化都必须使用清洗后的 `n`,
否则分母与实际参与求和的项数不一致, 方差会被系统性低估。

### 4.3 Q5: 不足有效配对时的返回

现有退化约定 (零方差 / 零方差差) 均返回 `(0.0, 1.0)` = 「无证据」。
新增 `n < 3` 分支沿用该约定: `p=1.0` 在 `compare` 中不显著, 在 `compare_all`
中退回 bootstrap 门控, 不产生假阳性。**不返回 NaN**, 因为 NaN 正是本次要消除的
「静默失效」信号。

### 4.4 Q6: 无缺失输入零影响

当两条序列均无 NaN/Inf 时, 联合掩码全 True, 清洗后 `n = T`, 所有计算与现状逐位相同
(仅多一次 O(n) 掩码运算)。因此该修复对既有测试与生产数值零影响。

### 4.5 Q7: 范围边界

`mean_diff_hac_statsmodels` 是**均值差参考检验**, 仅测试引用, 不属于本次缺陷
(其缺失处理不在 P2 条目内)。本次不改, 记为观察项 O2, 避免无关行为变更。

## §5 观察项

| # | 观察 | 影响 | 建议 |
|---|------|------|------|
| O1 | 未实现 Datta & Du (2012) 的 AM 估计量 (按缺失指示变量加权核) | 缺失比例很高时 ES 方差可能偏大; 本项目缺失比例低, 影响可忽略 | 若未来出现 >20% 缺失的消融场景再评估 |
| O2 | `mean_diff_hac_statsmodels` 同样未做 NaN 过滤 | 仅测试路径, 无生产影响 | 若该函数转为生产主路径, 同步修复 |
| O3 | ES 会压缩时间轴, 使缺失点之后的滞后对应关系偏移 1 期 | 单点缺失时影响 O(1/n); 多点连续缺失时会低估长期自相关 | 在 docstring 中显式声明该口径 |

## §6 调研结论

- **可直接引用**: Newey & West (1987) / Ledoit & Wolf (2008) / Datta & Du (2012),
  三条均经 Crossref 核实 (DOI + 卷期页)。
- **修复口径**: 联合 `isfinite` 掩码 (成对 complete-case) + 清洗后 `n` 重算带宽;
  `n < 3` 返回 `(0.0, 1.0)`。等价于 Datta & Du (2012) 的 Equal Spacing 估计量。
- **不可引用 (已证伪)**: 「删除 NaN 会破坏 HAC 一致性」——Datta & Du (2012)
  明确给出 ES 的渐近一致性证明。
- **范围外**: AM 估计量、`mean_diff_hac_statsmodels`、`circular_block_bootstrap` 的
  成对语义 (后者检验均值, 不要求成对)。

## §7 步骤 2 review 记录 (接口对齐 + 引用核实)

| # | 检查项 | 结论 |
|---|--------|------|
| R1 | 三条引用 DOI / 卷期页与 Crossref 返回一致 | ✅ 一致 |
| R2 | F1-F12 行号与当前源码一致 (以 v3.4.9 工作区为准) | ✅ 一致 |
| R3 | 「ES = 删除缺失后按等间隔套 NW」与 Datta & Du 摘要表述一致 | ✅ 一致 |
| R4 | 未把 AM 的方差优势误写为 ES 的劣势 | ✅ 已按原文区分 (ES 低偏差 / AM 低方差) |
| R5 | Q5 的 `(0.0, 1.0)` 与源码既有退化返回一致 | ✅ 一致 (L83-L84, L113-L114, L134-L135) |

**review 结论**: PASS, 无需修复项。
