# MAD 缩尾独立实验 (ADR-042 O1)

> **版本**: v1.0 (2026-11-16)
> **代码版本**: factor_pipeline 3.4.9
> **上游**: [ADR-042](../../DECISIONS.md) 替代方案「MAD 缩尾 — 延后为独立实验 (O1)」 /
> [PROJECT_STATUS §2 P1 #2](../PROJECT_STATUS.md)
> **结论摘要**: 排序层面与 percentile 1/99 几乎等价 (ρ≥0.9997), 预测力无可检出改善;
> **不建议切换默认**, MAD 保留为 `static_outlier_method` 可选项。

---

## §1 目的

回答三个问题:

1. 把默认去极值从 `percentile 1/99` 换成 `mad`, 因子处理**输出**改变多少?
2. 对下游预测力 (IC / ICIR / 多空 Sharpe) 是否有可检出影响?
3. 是否应切换默认?

---

## §2 数据与口径

| 项 | 值 |
|----|-----|
| 因子 | `LT_debt_ratio` (日频, 242 × 5589, NaN 5.03%) / `UTR_turnover` (月频, 12 × 5659, NaN 0%) |
| 价格 | `cache/` 内 2023 年不复权收盘价 (242 × 5381) |
| 前瞻收益 | 日频: 次日/当日−1; 月频: 下一月末/当月末−1 (取 ≤ 月末最后交易日) |
| 管线 | `PipelineV2Config()` 默认 (unified: imputer → outlier → 中性化(无数据跳过) → rank→normal) |
| 对照 | B3 `percentile 1/99` vs `L4_outlier_method_mad` |
| 有效 IC 观测 | LT 241 期; UTR 11 期 |
| 显著性 | Newey-West HAC 截距 t (lag=5) 对 ΔIC 序列; runner `compare` 的 bootstrap p |

### 2.1 `mad` 的实际实现 (重要口径)

`SmartOutlierDetector` 构造默认 `adaptive_threshold=True`, `max_outlier_frac=0.05`
([transformers.py L30-L41](../../modules/factor_adaptive_winsor/core/transformers.py#L30-L41)),
而 `ProcessingAdapter` 未向它传 `adaptive_threshold`
(白名单 [adapters.py L53-L55](../../adapters.py#L53-L55) 中无此 key, 管线也不传)。

因此本实验的 `mad` 不是教科书固定 **3×MAD**, 而是:

```
threshold = clip( P95(|x − median| / MAD_t), 2.0, 4.0 )   # 逐日截面, 自适应
out       = smooth_clip(x, median − threshold·MAD, median + threshold·MAD)
```

`smooth_clip` 为 tanh 平滑过渡的 C¹ 截断, 不是硬 clip
([transformers.py L339-L366](../../modules/factor_adaptive_winsor/core/transformers.py#L339-L366))。

---

## §3 输出层结果

### 3.1 去极值单步 (隔离缩尾本身)

| 指标 | LT (日频) | UTR (月频) |
|------|-----------|------------|
| 逐期截面秩相关 (mean / min / p10) | 0.999981 / 0.999970 / 0.999977 | 0.999703 / 0.999677 / 0.999684 |
| ρ≥0.99 期数占比 | 100% | 100% |
| 被改动样本比例 (pct / mad) | 2.02% / 2.30% | 2.01% / 8.21% |
| 最大绝对位移 (pct / mad) | **63.98 / 0.019** | **831.27 / 652.42** |
| 平均绝对位移 (pct / mad) | 0.0206 / 0.0002 | **2.396 / 19.154** |
| 原始 >3×MAD 极端值保留率 (pct / mad) | 94.18% / 88.28% | 91.63% / **31.84%** |

**解读**: 两种方法对**排序**的影响可忽略 (ρ≥0.9997); 差异全部集中在**截断幅度**,
且方向随数据分布反转:

- **LT (日频)**: percentile 把极端负债率硬截到 1% 分位, 最大位移达 63.98
  (原值量级); MAD 的截断边界远宽于该因子的极端值分布, 最大位移仅 0.019
  → **MAD 几乎不截断 LT 的极端值**;
- **UTR (月频)**: 反向 —— MAD 的平均位移 19.15 是 percentile 2.40 的 8 倍,
  仅 31.8% 的 >3×MAD 样本被完整保留 (percentile 为 91.6%), 改动样本比例 4 倍。

这说明「MAD 比 percentile 更稳健」不能一概而论: 在日频厚尾因子上它几乎不生效,
在月频截面上它显著更严。

### 3.2 管线最终输出 (z 分数)

| 指标 | LT pct | LT mad | UTR pct | UTR mad |
|------|--------|--------|---------|---------|
| \|z\|>2.5 占比 | 2.00% | 1.25% | 2.01% | 1.24% |
| \|z\|>3.0 占比 | 0.00% | 0.25% | 0.00% | 0.28% |
| std | 1.000 | 1.000 | 1.000 | 1.000 |

`|z|>2.5` 占比下降说明 MAD 分支的最终分布更集中于中部。
`|z|>3` 从 0 变为约 0.25% 属 rank→normal 在阈值附近的离散跳变
(排序几乎相同, 但阈值边界处的少量样本跨过 3.0), **不宜解读为「MAD 尾部更厚」**。

---

## §4 预测力结果

| 指标 | LT pct | LT mad | UTR pct | UTR mad |
|------|--------|--------|---------|---------|
| IC 均值 | -0.003033 | -0.003076 | -0.072497 | -0.072236 |
| ΔIC | — | **-0.000043** | — | **+0.000262** |
| ICIR (年化) | -0.0329 | -0.0339 | -0.6497 | -0.6504 |
| 多空 Sharpe | -0.1181 | -0.1181 | -0.3000 | -0.3000 |
| ΔSharpe | — | 0.0000 | — | 0.0000 |
| IC 序列秩相关 | — | 0.9994 | — | 1.0000 |
| NW(ΔIC) t / p (lag=5) | — | -0.238 / **0.812** | — | 3.585 / **0.0003** |
| bootstrap p (ΔIC) | — | 0.814 | — | 0.099 |
| runner `compare` HAC p | — | NaN (见 §6 O1) | — | NaN (见 §6 O1) |

**判定**:

- **LT (日频, 241 期)**: ΔIC 量级 4e-5, NW p=0.81, bootstrap p=0.81 → 无差异;
- **UTR (月频, 11 期)**: ΔIC 量级 2.6e-4 (相对 |IC| 0.072 为 0.36%), NW p=0.0003
  与 bootstrap p=0.099 **方向冲突**; NW lag=5 在 n=11 下消耗过半自由度,
  该 p 值不可作为采纳依据 → 判定为**无可靠证据**;
- **ΔSharpe 恒为 0**: 多空权重基于排序, 两种方法的排序几乎相同 → 收益序列一致。

---

## §5 结论与建议

1. **不切换默认**: `percentile 1/99` 保持不变。理由有三:
   (a) 排序层面等价、预测力无可检出改善;
   (b) MAD 的自适应阈值缺少稳定口径含义 —— 同一实现在日频厚尾因子上几乎不截断,
   在月频截面上却显著更严 (§3.1), 切换等于把默认行为交给数据分布;
   (c) 切换会使缓存失效 (需 bump 缓存代际) 并触发全链路重算, 收益为零。
2. **保留可选项**: `static_outlier_method='mad'` 已可用 (v3.4.7 参数化),
   需要更严格尾部控制的场景 (如月频低流动性因子) 可按需显式指定。
3. **若未来重启评估**, 需扩大样本至 ≥3 年、≥10 因子, 并启用行业/市值中性化
   (本实验因无元数据跳过中性化), 同时显式测试固定 3×MAD 与自适应阈值两种口径。

---

## §6 观察项

| # | 观察 | 影响 | 建议 |
|---|------|------|------|
| O1 | `ledoit_wolf_hac_test` 未过滤 NaN: LS/IC 序列各含 1 个 NaN → `compare` 的 HAC t/p 全为 NaN | 本实验的 HAC 判定失效, 已改用 NW 截距 t 补算; `compare_all` 会把 NaN p 值当 1.0, 不产生假阳性但丢失 HAC 结论 | ✅ **v3.4.10 已修复**: 入口成对 `isfinite` 掩码 (complete-case), 带宽/归一化用清洗后 n; 本实验的 NW 补算结论不受影响 |
| O2 | MAD 阈值不可参数化: `ProcessingAdapter` 不传 `adaptive_threshold` / `max_outlier_frac`, 只能用默认自适应口径 | 无法做 3×MAD 与 2.5/3.5×MAD 的敏感性实验 | 如需敏感性, 在 `StaticFactorPipeline` 增加 `static_outlier_mad_threshold` |
| O3 | 月频 11 期样本统计功效不足 | NW 与 bootstrap 结论冲突, 不可据此采纳 | 扩样本后再评估 |

---

## §7 复现

```powershell
python F:\Coding\_tmp\mad_experiment.py   # 输出 F:\Coding\_tmp\mad_experiment_results.json
```

脚本为一次性实验代码, 不入库; 数据来自仓库 `cache/` (2023 年缓存)。
LT 36.1s + UTR 27.3s (含两条管线各一次完整 fit/transform)。

---

## §8 局限

1. 2 个因子、2023 单年; 月频仅 11 个前瞻观测;
2. 价格不复权 (`adjust=none`), 前瞻收益含除权除息噪声;
3. 无行业/市值数据, 中性化被跳过; 结论不能外推到启用中性化的场景;
4. 未做交易成本 / 停牌 / 涨跌停过滤, 多空收益为理论值;
5. `mad` 使用仓内自适应阈值口径 (§2.1), 未与教科书 3×MAD 对比。
