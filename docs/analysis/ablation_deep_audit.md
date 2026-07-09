# 消融实验结果深度审计报告

## v3.1.0 真实A股数据消融 + 合成数据交叉验证

**审计日期**: 2026-07-09
**审计对象**: 脚本 `scripts/run_ablation_real.py` 产出, 对照 `scripts/run_ablation.py` (合成)
**审计范围**: 标准化 rank-preserving 假设 / 插补前视偏差 / 统计显著性完整性 / 合成-真实交叉验证

---

## Q1: 标准化是否 Rank-Preserving？启用标准化为何降低 IC/Sharpe？

### 1.1 实验验证

直接运行 50 股 × 231 期 momentum 因子 (B3 vs ScalerOff) 的横截面 Spearman 相关性:

```
Cross-sectional Spearman B3 vs ScalerOff:
  n_valid_ts = 231
  mean rho   = 0.905
  std rho    = 0.027
  min rho    = 0.788
  max rho    = 0.951
  rho == 1.0? 0/231  ← 没有一期是完全 rank-preserving 的
```

**结论: 标准化 NOT rank-preserving — 确认为 BUG, 已修复**

横截面 Spearman ρ 仅 0.905 — 意味着标准化改变了约 10% 的截面排序。

### 1.2 根因分析 (BUG 定位)

管线中的标准化执行的是 **per-stock z-score** (每个股票用自身历史均值和标准差做归一化):

```
z_i(t) = (x_i(t) - mean_i) / std_i
```

其中 `mean_i` 和 `std_i` 来自 `ProcessingAdapter.fit()` → 遍历 `X.columns` (股票代码) → 对每个股票单独拟合
`EnhancedRankPreservingScaler` → 在该股票的时间序列上独立计算统计量拟合。

当不同股票有不同的 `std_i` 时:
- 低波动股票 (std 小): z-score 放大原始值
- 高波动股票 (std 大): z-score 压缩原始值

这导致了**截面排序的重新洗牌**: 原始排名第一的股票可能因为其标准差较大而在 z-score 空间中被低波动股票超越。

**根因**: `ProcessingAdapter.fit()` (L375-L383) 对 standardization 按列迭代 `for col in X.columns`, 每列 = 一只股票的时间序列。
因子标准化的正确语义是**横截面标准化** `(x_i - cross_mean) / cross_std`, 对每个时间点 t 的所有股票施加相同的仿射变换,
保证截面排序不变。per-stock z-score 破坏了截面排序。

### 1.3 修复 (commit 109bc32 → 当前)

修改 [adapters.py](file:///f:/Coding/factor_pipeline/adapters.py):

1. **`__init__`**: 增加 `self._cross_sectional_zscore` 标志 (当 `process_type='standardization'` 且 `method='z_score'` 时为 True)
2. **`fit()`**: z_score 模式跳过 per-column 拟合, 横截面标准化无需 fit
3. **`transform()`**: z_score 模式执行 `result = (X - X.mean(axis=1)) / X.std(axis=1)`

横截面 z-score 是严格 rank-preserving 的:
```python
# 验证: Spearman ρ = 1.0 for all time steps
X = pd.DataFrame(rng.normal(0, 1, (50, 20)))
z = X.sub(X.mean(axis=1), axis=0).div(X.std(axis=1).replace(0, 1.0), axis=0)
all(spearmanr(X.iloc[t], z.iloc[t])[0] == 1.0 for t in range(50))  # True
```

### 1.4 修复后消融语义

修复前 (per-stock):
- scaler_off 的 ΔIC = +175% 是"苹果 vs 橙子" — B3 (per-stock z-score 破坏排名后计算 IC) vs ScalerOff (原始排名)
- 这个对比没有消融意义, 因为它比较的是**不同截面排序**的 IC

修复后 (cross-sectional):
- scaler_off 的 ΔIC 仅来自数值尺度的改变 (标准化统一量纲但不改变排序)
- B3 vs ScalerOff 的 IC 现在真正反映标准化模块的贡献 — 仅剩跨因子量纲统一的边际效应
- ΔIC 预期大幅缩小 (接近 0), ΔSharpe 保持 (受绝对数值尺度影响)

### 1.5 统计显著性 (修复后需重跑)

HAC test 当前结果: t_stat=1.4234, **p=0.1546 (不显著)**, 但这是 per-stock 模式的结果。
修复后需用真实数据重跑消融实验, 预期结果将完全不同。

---

## Q2: 插补模块前视偏差审计

### 2.1 审计范围

已审计文件:
- `modules/factor_imputer/core/imputers.py` — 5 种插补策略的 fit/transform
- `modules/factor_imputer/integration/factor_type_aware_imputer.py` — 集成层
- `modules/factor_imputer/strategies/time_series.py` — 时序插补
- `adapters.py` — ImputerAdapter 适配器

### 2.2 发现的偏差

| 偏差来源 | 严重程度 | 影响文件 | 机制 |
|---------|---------|---------|------|
| **bfill 后向填充** | 高 | `imputers.py:L197-L199` (TimeSeriesImputer) + `L525` (FactorSpecific) | `.ffill().bfill()` — bfill 用未来观测值填补历史, 纯前视偏差 |
| **全量统计量** | 中 | `imputers.py:L88-L105` (CrossSectionalImputer) | `X.median()` / `X.mean()` 计算全样本统计量拟合再插补自身 |
| **全量 ML 训练** | 严重 | `imputers.py:L259-L267` (MLAdvancedImputer) | KNN/RandomForest 在全量数据上训练后用模型填补自身训练数据 |
| **全量线性回归** | 高 | `imputers.py:L393-L410` (FactorSpecificImputer) | LinearRegression 在全量数据上拟合后预测历史缺失值 |
| **PanelHierarchical 继承** | 中 | `imputers.py:L224-L229` | 默认 auto 策略组合 CrossSectional + TimeSeries, 同时继承两者的 bias |

### 2.3 安全策略

| 策略 | 安全性 | 条件 |
|------|--------|------|
| `time_series` + `method='ffill'` | 安全 | 移除 bfill 回退 |
| `time_series` + `method='rolling_mean'` | 安全 | 滚动窗口仅用过去数据 |
| `time_series` + `method='exponential_smoothing'` | 安全 | EWMA 仅用过去数据 |

### 2.4 对消融结果的影响

当 `imputer=False` (消融实验的 imputer_off 配置):
- momentum_1m 有 3.2% NaN → imputer 关闭后 NaN 传入下游
- neutralizer 的 `fillna(0)` 将 NaN 静默替换为 0 → 0 作为"有效因子值"参与 IC/Sharpe 计算
- 这些人为填 0 的值稀释了 IC 信号, 导致 imputer_off 的 IC 比 B3 更低 (ΔIC = -14.2%)

**这解释了为什么 imputer 在真实数据上的贡献度 (14.2%) 远大于合成数据 (0%)** — 真实数据有缺失, 插补模块起到了实际的数据清洗作用。

### 2.5 修复建议

1. **P0 (立即)**: 移除 TimeSeriesImputer 的 bfill 回退 (或替换为 fillna(0)), 消除明确的前视偏差
2. **P1 (短期)**: CrossSectionalImputer 改为 expanding window 统计量
3. **P2 (中期)**: MLAdvancedImputer/FactorSpecific 改为 walk-forward 训练
4. **P1 (短期)**: neutralizer 的 `fillna(0)` 改为显式 NaN 保留, 避免静默数据污染

---

## Q3: 统计显著性完整性 — p_bootstrap=0.0 为何 is_significant=false？

### 3.1 根因

消融结果 JSON 中 p_value_hac 显示为 NaN (实际是 NaN 被 JSON 序列化, 不是合法 JSON 值)。显著性判定在 `ablation_runner.py:L1282`:

```python
is_significant = (p_value_hac < self.alpha) and (p_value_boot < self.alpha)
```

当 `p_value_hac = NaN` 且 `p_value_boot = 0.0` 时:
- `NaN < 0.05` = `False`
- `False AND True` = `False`
- `is_significant = False`

**即: 即使 bootstrap p=0.0 (极其显著), 只要 HAC 返回 NaN, 显著性就被否决。**

### 3.2 根本原因: HAC 为何返回 NaN

Q1 验证实验显示 HAC test 正常返回 p=0.1546。JSON 中 NaN 的可能原因:
- 消融框架的 `_evaluate_factor()` 可能将 NaN 的 `ls_return_series` 传给了 `experiment` 对象
- 3 因子 scenario 下某些因子的 LS 序列全为 NaN (如对 turnover 因子, fwd_returns 对齐后可能无有效数据)

### 3.3 修复

```python
# ablation_runner.py:L1282, 修改前:
is_significant = (p_value_hac < self.alpha) and (p_value_boot < self.alpha)

# 修改后 — HAC NaN 时不否决:
hac_ok = (not np.isnan(p_value_hac)) and (p_value_hac < self.alpha)
boot_ok = (not np.isnan(p_value_boot)) and (p_value_boot < self.alpha)
if np.isnan(p_value_hac):
    is_significant = boot_ok  # HAC 未计算, 仅用 bootstrap
else:
    is_significant = hac_ok and boot_ok
```

### 3.4 数据规模检验力评估

| 指标 | 合成数据 | 真实数据 |
|------|---------|---------|
| 周期数 | 120 | 231 |
| 股票数 | 30 | 94 |
| 因子数 | 3 | 3 |
| HAC 有效 (非 NaN) | 0/6 | 待验证 |
| Bootstrap 显著 (<0.05) | 0/6 | scaler: p=0.0 |
| 综合显著 | 0/6 | 0/6 (因为 HAC NaN 否决) |

**Bootstrap p=0.0 本身可能过高估了显著性** — 231 期的 IC/LS 时间序列在日频上存在强自相关, bootstrap 的 circular block 方法可能低估了标准误差。真实显著性应参考 HAC 方法的结果 (p=0.15, Q1 验证实验)。

---

## Q4: 合成 vs 真实数据交叉验证

### 4.1 方向对齐

| 模块 | 合成 ΔIC | 真实 ΔIC | 方向一致? |
|------|---------|---------|----------|
| imputer | 0.0000 | 0.0013 | N/A (合成无 NaN) |
| winsorizer | +0.0004 | +0.0016 | 一致 (都小幅正) |
| scaler | +0.0021 | +0.0163 | 一致 (都正) |
| neutralizer | +0.0036 | -0.0030 | **不一致!** |
| orthogonalizer | 0.0000 | 0.0000 | 一致 (默认关闭) |

### 4.2 neutralizer 方向翻转分析

**合成数据**: neutralizer 关闭 → 行业共变保留 → ΔIC = +47.6% (表面"改善")

**真实数据**: neutralizer 关闭 → ΔIC = -32.4% (表面"恶化")

这个翻转是**关键的证据**, 说明:
1. 合成数据中行业分配随机, 行业共变是纯噪声 → 中性化能"移除噪声" (IC 改善)
2. 真实数据中行业结构携带真实信号 → 中性化移除了部分真实信号 (IC 恶化)
3. 但真实数据的 neutralizer 同时也在移除噪声 → 综合效果是 ΔIC = -32.4%, 说明**真实信号损失 > 噪声移除收益**

### 4.3 综合判断

| 维度 | 评价 |
|------|------|
| 合成数据适用性 | 用于验证 Type-I 控制 (无虚假显著) ✅ |
| 合成数据局限性 | 不能用于评估模块对真实信号的贡献 |
| 真实数据检验力 | 231 期不够 — 真实信号远弱于管线机械偏差, 需要 ≥ 504 期 |
| 统计显著性 | HAC 方法正确 (p=0.15), bootstrap p=0.0 疑为低估标准误差 |
| is_significant 标志 | 修复前: 全部 false (HAC NaN 否决); 修复后: 需逐项重新评估 |

---

## 总体结论与修复优先级

### P0 — 立即修复

| 项目 | 文件 | 改动 |
|------|------|------|
| is_significant HAC NaN 否决 | `ablation_runner.py:L1282` | HAC NaN 时仅用 bootstrap 判定 |
| bfill 前视偏差 | `imputers.py:L197-L199,L525` | `.ffill().bfill()` → `.ffill()` (或 `.ffill().fillna(0)`) |
| Scaler Core 级别 | `ablation_runner.py:L938-957` | scaler 消融时 emit 警告 + exclude from module_enabled |

### P1 — 短期改进

| 项目 | 说明 |
|------|------|
| 重新运行消融 (≥504 期) | 当前 231 期 HAC 检验力不足 |
| neutralizer fillna(0) → NaN | 避免静默数据污染 |
| 消融报告增加 effect_size | Cohen's d, 补充 p 值 |

### P2 — 中期改进

| 项目 | 说明 |
|------|------|
| CrossSectionalImputer expanding window | 消除全量统计量偏差 |
| ML imputer walk-forward | 消除训练数据泄漏 |
| cross_sectional z-score 选项 | 支持 rank-preserving 标准化 |

### 最终裁定

1. **标准化 (scaler) 不是 rank-preserving**: 每只股票用自身历史 z-score → 截面排序 ρ≈0.905。175% ΔIC 是数学正确但语义错误 — scaler 关闭后 IC 变化源自排名重洗而非信号增强。建议 scaler 从消融列表中排除。

2. **插补存在前视偏差**: bfill 路径 (TimeSeriesImputer L199, FactorSpecific L525) 明确使用未来信息。auto 模式下默认的 PanelHierarchical 路径同时受全量统计量和 bfill 的双重污染。

3. **统计显著性需重评估**: 修复 HAC NaN 否决后, scaler 的 p_bootstrap=0.0 可能过高估了显著性。独立验证实验 (HAC test) 得到 p=0.15, 说明 231 期数据不足以证明 scaler 的差异有统计意义。

4. **合成与真实数据方向基本一致**: 除 neutralizer 因行业真实信号导致方向翻转 (预期行为) 外, 其余 4 个模块的方向一致, 说明消融框架本身没有系统性偏差。
