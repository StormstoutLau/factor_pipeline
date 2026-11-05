# PL-08 AR 阶数选择信息准则可比性 — 设计文档

**版本**: v1.2 (2026-11-04; v1.0 = 步骤 3 设计初稿; v1.1 = 步骤 4 幻觉消除 review 修订, 见 §12; v1.2 = 步骤 8 一致性 review 行号勘误)
**缺陷编号**: DEFECT-PL-08
**上游调研**: [PL08_AR_ORDER_AIC_COMPARABILITY_RESEARCH.md](PL08_AR_ORDER_AIC_COMPARABILITY_RESEARCH.md) v1.2
**关联决策**: 新增 **ADR-041** (ADR-040 已占用; ADR-041 起未占用)
**目标版本**: **v3.3.7**; 缓存 **`v2.2.5-cache`**
**方案状态**: **C (统一 `hold_back=max_order` + 有效样本守卫) 选定**; A/B/D/E 记录为备选 (不实施)
**后续工件**: ~~步骤 4 review~~ (✅ v1.1, §12) → 步骤 5 `EXECUTION_V3.3.7_PL08_*.md`
**行号说明**: 行号仅作导航, 以类名/函数名/测试名为准

---

## §0 设计摘要

| # | 决策 | 状态 |
|---|------|------|
| D1 | `_fit_ar` 统一 `hold_back = self.max_order`; 所有阶数使用同一响应向量 `y[H:]` 与同一估计样本 | **锁定** |
| D2 | `_fit_ar` 增加有效样本守卫 `n_obs <= order + 5 → ValueError`; **有效样本判定唯一在 `_fit_ar`**, `_fit_best` 的总长守卫仅作快速跳过 | **锁定** |
| D3 | `transform` **不改**: `early = min_order + 6` 保留, 守卫使早期行自然保持 identity | **锁定** |
| D4 | `ARModelResult.residuals` / `fitted_values` 索引统一为 `series.index[H:]` | **锁定** |
| D5 | 默认准则保持 `aic`; 不新增 `aicc`, 不切换 BIC/HQIC 默认 | **锁定** |
| D6 | `_fit_best` 的 `len(series) <= order + 5` 守卫**保留不动**; 有效样本判定下沉到 `_fit_ar` | **锁定** |
| D7 | 范围仅 `ar_model.py` 的 `AROrderSelector._fit_ar`; `_fit_best` / `transform` / `ARDecoupler` 其他方法不改 | **锁定** |
| D8 | 版本 **v3.3.7** / 缓存 **`v2.2.5-cache`** / **ADR-041** | **锁定** |
| D9 | 不新增公共参数, 不进入 `PipelineV2Config` / optimizer 搜索空间 | **锁定** |
| D10 | 既有行为测试不改; 仅新增单测文件 + 版本/缓存字面量测试更新 | **锁定** |

**验收目标**:

| 指标 | 当前基线 | 目标 |
|------|---------|------|
| 同一序列 AR(1..5) 的 `n_obs` | 99/98/97/96/95 | **全部 = n - max_order** |
| 与 statsmodels `AutoReg(hold_back=H)` 逐项对比 | — | 系数/`llf`/`σ²`/`n_obs` **完全一致**; AIC 差恒 `-2` |
| AR(1) 真值面板选阶均值 (T=100/N=30 seed=22) | 4.800 | **≤ 2.0** (调研实测 1.233) |
| AR(2) 真值面板选阶均值 (T=120/N=30) | 4.87 | **∈ [1.8, 3.2]** (调研实测 2.53) |
| AR(3) 真值面板选阶均值 (T=120/N=30) | 4.97 | **∈ [2.4, 3.8]** (调研实测 3.23) |
| 截断不变式 (既有 7 点 + 新增早期 5 点, 共 11 个不同截断点) | 0/0 (已满足) | **0 格 / 0 NaN** |
| 退化拟合 (`σ²=0` / `ln(0)`) | 无 (当前无 hold_back) | **0 警告** |
| 固定阶数 `fit` 系数 | — | **与当前逐值相同** (`atol=0`) |
| 靶向套件基线 (实施前) | 72 passed / 1 env-fail | **72 passed / 1 env-fail (无新增失败)** |
| AR 性能 (2500×300) | 2.76s | **≤ 3.1s** (≈ +12%, 含单次运行噪声余量; 调研实测 2.72s) |

**选定 C 的理由**:

1. **方法学正确**: 所有阶数在同一 `n_obs` 上计算似然, 满足 statsmodels 官方"comparable models"条件 (调研 §3.1)。
2. **行为可控**: 阶数分布从 4.8 降至 1.2–1.6, 但 AR(2)/AR(3) 真值仍可识别; 不是"一律 AR(1)" (调研 §6.2)。
3. **不破坏因果性**: 既有 7 点 + 新增早期 5 点共 11 个不同截断点全 0/0; 只改变估计样本长度, 不改变"只用前缀"结构 (调研 §6.4; 早期点由设计期探针实测)。
4. **消除退化**: 守卫使 warm-up `t=7..11` 保持 identity, 重复探针不再出现 `σ²=0` / `max_abs=322.68` (调研 §6.5)。
5. **最小改动**: 仅 `_fit_ar` 一个方法 (约 12 行); `transform` / `_fit_best` / 配置面 / 公共签名全不动。

---

## §1 目标与非目标

### 1.1 目标

1. **可比性**: AIC/BIC/HQIC 的似然项在所有候选阶数上使用同一 `n_obs`, 消除"阶数越高、样本越短、似然项越小"的机械偏向。
2. **契约保持**: `AROrderSelector._fit_ar(series, order)` 签名不变; 返回 `ARModelResult` 字段不变; `ARDecoupler` 公共 API 与 `transform` 三段式结构不变。
3. **因果性保持**: 仍满足 PL-05 的截断不变式 (逐元素, `atol=1e-12`)。
4. **无退化**: warm-up 早期不再出现 `n_obs <= k` 的精确拟合 (`σ²=0` / `ln(0)`)。
5. **可测试**: 与 statsmodels 逐项对齐 + 阶数分布 + 截断不变式 + 固定阶数等价性。
6. **可回滚**: 单方法回滚; 版本/缓存代际明确。

### 1.2 非目标

| 项 | 归属/说明 |
|----|-----------|
| 修复 AIC 的**不一致性** (固定概率过选阶) | 方法学性质, 非本任务; 保持 AIC 默认 (调研 §2.2/§5.2 D4) |
| 新增 AICc | 生产窗口 `n_obs=115` 下无增益 (调研 §6.2/§6.3) |
| 默认准则切换 BIC/HQIC | 超出缺陷范围; BIC 在 AR(3) 面板低估 (调研 §6.2) |
| `OptimizedARDecoupler._fit_ar_order` | 独立副本, 非生产路径; 不修 |
| `TemporalDecoupler` 的 AR 方法 | 共用 `AROrderSelector`, 阶数被动变化; 不修实现 |
| `_fit_best` 的搜索上界 / `max_order=5` / `min_order=1` / `min_obs=20` | 不改 |
| `transform` 的 `early` / `_WARMUP_REFIT_STRIDE` / `warmup_obs` | 不改 (PL-05 已定稿) |
| 常数序列的 `σ²=0` (先于 guard 的既有边界) | 既有行为; 本次仅堵住 `n_obs <= k` 一类; 其余登记 (§9 R7) |
| 配置面 / optimizer | 不改 |
| 恢复到"跨阶不同样本"的兼容开关 | 不做 (该行为就是缺陷) |

---

## §2 现状与约束

### 2.1 当前代码路径

| 位置 | 现状 | 与本缺陷的关系 |
|------|------|---------------|
| [`AROrderSelector._fit_ar`](../../modules/factor_decoupler/core/ar_model.py#L139-L184) | `y_trimmed = y[order:]`; `n_obs = n - order` | **缺陷宿主** |
| [`AROrderSelector._fit_best`](../../modules/factor_decoupler/core/ar_model.py#L101-L137) | 遍历 `order ∈ [min_order, max_order]`; 总长守卫 `len(series) <= order+5` | 调用方; 不改 |
| [`AROrderSelector.fit`](../../modules/factor_decoupler/core/ar_model.py#L80-L99) | `_fit_best` + INFO 日志 | 不改 |
| [`AROrderSelector.batch_fit`](../../modules/factor_decoupler/core/ar_model.py#L199-L225) | 逐列 `dropna` + `len >= min_obs` | 不改 |
| [`ARDecoupler.fit`](../../modules/factor_decoupler/core/ar_model.py#L286-L306) | 只用前 `warmup_obs` 行调用 `batch_fit` | 不改 |
| [`ARDecoupler.transform`](../../modules/factor_decoupler/core/ar_model.py#L341-L403) | 三段式; 短前缀调用 `_fit_ar(ser, min_order)` | 不改; 守卫使其早期行 identity |
| [`ARDecoupler._get_ar_phi_for_diagnosis`](../../modules/factor_decoupler/core/ar_model.py#L308-L330) | 取 `_results` 的 `coefficients[1]` 均值 | 不改; φ 随阶数变化 |
| [`CompositeDecoupler.fit`](../../modules/factor_decoupler/core/dual_neutralizer.py#L384-L428) | 构造 `ARDecoupler(max_order=..., criterion=..., strength=...)` (关键字, 无 `warmup_obs`, 调用点 L413-L417) | 不改; 使用默认 `warmup_obs=120` |

### 2.2 数据契约

- `series: pd.Series`, 索引为日期; `_fit_ar` 的**前置条件**: 已 `dropna` (所有内部调用方均满足)。
- 逐列独立拟合; `order ∈ [min_order, max_order]`。
- 统一估计样本: `y_trimmed = y[H:]`, `H = self.max_order`; 滞后列 `y[H-i : n-i]` 长度均为 `n-H`。
- `n_obs = n - H` 对所有阶数相同; `k = order + 1` (截距 + p 个滞后)。
- 残差与拟合值索引 = `series.index[H:]`。
- `sigma2 = np.var(residuals, ddof=0)` (ML), `ll = -n_obs/2(ln(2πσ²)+1)`; 公式本身不变。
- 时间方向: 第 `t` 行只使用 `vals[0..t]`; 本设计不引入任何未来引用。

### 2.3 参数与派生量

| 参数 | 默认 | 本设计是否改 |
|------|------|-------------|
| `max_order` | 5 | 否; 同时作为 `H` |
| `min_order` | 1 | 否 |
| `criterion` | `'aic'` | 否 |
| `min_obs` | 20 | 否 |
| `strength` | 1.0 | 否 |
| `warmup_obs` | 120 | 否 |

**派生量**:

```
H        = self.max_order
n_obs    = len(series) - H
k        = order + 1
可行条件 = n_obs > order + 5   (即 n_obs >= order + 6)
```

**约束**:
- `order <= self.max_order = H` (所有既有调用满足; `transform` 用 `min_order`)。
- 默认 `min_obs=20, max_order=5` 时, 拟合路径 `n_obs >= 15`, 守卫不触发; 只在 warm-up 短前缀触发。
- `min_obs <= max_order` 的极端配置可能整列不可估 (既有降级路径: `batch_fit` 跳过该列) — §9 R5。

---

## §3 方案设计

### 3.1 `_fit_ar`: 统一 `hold_back`

```python
def _fit_ar(self, series: pd.Series, order: int) -> ARModelResult:
    """拟合指定阶数的 AR 模型 (v3.3.7: 所有阶数使用同一 hold_back 样本)."""
    y = series.values
    n = len(y)
    hold_back = self.max_order              # 所有阶数共享的估计样本起点

    y_trimmed = y[hold_back:]
    n_obs = len(y_trimmed)                   # 所有阶数相同; 也 == len(residuals)
    if n_obs <= order + 5:                  # 有效样本守卫 (D2)
        raise ValueError(
            f"AR({order}) 有效样本不足: n_obs={n_obs} <= order+5={order + 5} "
            f"(n={n}, hold_back={hold_back})"
        )

    # 滞后矩阵: 所有列长度均为 n_obs
    X = np.column_stack([
        y[hold_back - i:n - i] for i in range(1, order + 1)
    ])
    X = np.column_stack([np.ones(n_obs), X])

    beta = np.linalg.lstsq(X, y_trimmed, rcond=None)[0]
    fitted = X @ beta
    residuals = y_trimmed - fitted

    k = len(beta)                            # = order + 1
    sigma2 = np.var(residuals, ddof=0)
    log_likelihood = -n_obs / 2 * (np.log(2 * np.pi * sigma2) + 1)
    r_squared = 1 - np.var(residuals) / np.var(y_trimmed) if np.var(y_trimmed) > 0 else 0

    aic = -2 * log_likelihood + 2 * k
    bic = -2 * log_likelihood + k * np.log(n_obs)
    hqic = -2 * log_likelihood + 2 * k * np.log(np.log(n_obs))

    return ARModelResult(
        order=order,
        coefficients=beta,
        residuals=pd.Series(residuals, index=series.index[hold_back:]),
        fitted_values=pd.Series(fitted, index=series.index[hold_back:]),
        aic=aic, bic=bic, hqic=hqic,
        r_squared=r_squared, sigma2=sigma2,
        log_likelihood=log_likelihood,
    )
```

**与现状的差异 (逐行)**:

| 行 | 现状 | 修复后 |
|----|------|--------|
| `y_trimmed` | `y[order:]` | `y[hold_back:]` |
| 滞后列 | `y[order-i : n-i]` | `y[hold_back-i : n-i]` |
| `n_obs` | `n - order` | `n - hold_back` |
| 守卫 | 无 (由 `_fit_best` 的总长守卫间接约束) | `n_obs <= order+5 → ValueError` |
| 残差索引 | `series.index[order:]` | `series.index[hold_back:]` |
| AIC/BIC/HQIC 公式 | 不变 | 不变 (只改 `n_obs` 的取值口径) |

**复杂度**: `O(n_obs · p²)` 每阶; `p ≤ 5`, 与现状同阶。构造矩阵长度从 `n-order` 变为 `n-H`, 总元素数变化 ≤ `H` 行 × `p` 列, 可忽略。

### 3.2 有效样本守卫 (D2)

**语义**: `n_obs <= order + 5` 时该阶不可估, 抛 `ValueError`。

**为什么是 `order + 5`**:
1. 与 `_fit_best` 现有总长守卫 `len(series) <= order + 5: continue` 同语义, 只是把"总长度"换成"有效样本长度"。
2. 保证 `df_resid = n_obs - k >= 5` (5 个残差自由度), 避免 `n_obs = k` 的精确拟合 (`σ²=0` / `ln(0)`)。
3. 若未来引入 AICc, 保证分母 `n_obs - k - 1 >= 4 > 0` (调研 §6.6)。

**调用方行为**:
- `_fit_best`: `try/except Exception` 捕获 → `continue`; 不影响其它阶。
- `transform` 的短前缀分支: `try/except` 捕获 → `continue` → 该行保持 identity。
- `_fit_best` 的 AR(1) 回退 ([ar_model.py L129-133](../../modules/factor_decoupler/core/ar_model.py#L129-L133)) **不在 try 内**: 若 `n_obs <= 6` 则抛错并向上传播; `batch_fit` 捕获后跳过该列。默认配置 (`n_obs >= 15`) 不触发。

### 3.3 `_fit_best` / `transform` / `ARDecoupler` 不改

| 位置 | 为何不改 |
|------|---------|
| `_fit_best` 的遍历与总长守卫 | 默认 `min_obs=20` 下 `n_obs >= 15`, 总长守卫不会放行不可估阶; 有效样本判定已由 `_fit_ar` 统一负责 |
| `_fit_best` 的 AR(1) 回退 | 默认配置可用; 极端配置的行为由 §9 R5 登记 |
| `transform` 的 `early = min_order + 6` | 守卫在 `_fit_ar` 内自然把 `t=7..11` 留作 identity, 与"early 抬到 `H+min_order+6`"等效; 保持 `test_cold_start_is_identity` 契约 |
| `transform` 的三段式与冻结分支 | 只消费 `r.order` / `r.coefficients`, 不消费 `residuals` 索引; 无影响 |
| `ARDecoupler.__init__` / `fit` / `_get_ar_phi_for_diagnosis` | 无签名/语义变更; φ 随选中阶数变化是预期行为 |

### 3.4 边界语义 (锁定)

| 场景 | 行为 | 依据 |
|------|------|------|
| `n < H` | `y_trimmed` 为空 → 守卫抛错 | 有效样本为负/零 |
| `n = H` | `n_obs=0` → 守卫抛错 | 同上 |
| `n_obs <= order+5` | 该阶抛 `ValueError` | D2 |
| `n_obs > order+5` | 正常拟合; `df_resid >= 5` | D2 |
| `order = max_order` | `H = order`; 与现状 `y[order:]` 等价 (固定阶数) | 数学等价 |
| `min_order == max_order` | `fit` 冻结模型与现状逐值相同; warm-up 段因守卫时点平移而变化 | §5.1 实测 |
| `transform` 的 `t < early` | identity | 不变 (D3) |
| `transform` 的 `early <= t < H+min_order+6` | 守卫跳过 → identity | 新增的早期 identity 行 |
| 滞后值含 NaN | 该行输出 NaN | 不变 (NaN 自然传播) |
| 常数序列 (`np.var(y_trimmed)=0`) | 既有 `σ²=0` 边界, **不在本次范围** | §9 R7 |

### 3.5 备选方案记录 (不实施)

| 代号 | 方案 | 拒绝理由 (调研 §5.4/§6.5) |
|------|------|------------------------------|
| A | 仅统一 `hold_back`, 无守卫 (`n_obs > 1`) | `t=7..11` 退化; `σ²=0`/`ln(0)`; `max_abs=322.68` |
| B | `hold_back` + 守卫 `n_obs > order+2` | 消除 `σ²=0`, 但 `t=9..11` 仍用 4–6 个观测; `max_abs=5.3131` |
| D | C + AICc | 生产窗口下与 AIC 分布几乎相同; MSE 无改善; 增加 API 面 |
| E | C + 默认 BIC | AR(3) 面板均值 2.53 (低估); 超出缺陷范围 |

### 3.6 关键数值 (来自调研 v1.2, 不重复测量)

| 指标 | 当前 | 方案 C |
|------|------|--------|
| `n_obs` (AR(1..5), n=100) | 99/98/97/96/95 | **95/95/95/95/95** |
| 阶数均值 (AR(1) 真值, T=100) | AIC 4.800 / BIC 2.200 / HQIC 3.867 | AIC **1.233** / BIC **1.000** / HQIC **1.000** |
| 阶数均值 (AR(1) 真值, T=500, 拟合窗口 120) | AIC 4.867 | AIC **1.600** |
| 阶数均值 (AR(2) 真值, T=120) | 4.87 | **2.53** |
| 阶数均值 (AR(3) 真值, T=120) | 4.97 | **3.23** |
| 输出偏移 (T=100/N=30 seed=22) | — | **2790/3000 (93.0%)**, `max_abs=6.9968` |
| 输出偏移 (T=500/N=30 seed=42) | — | **14410/15000 (96.1%)**, `max_abs=4.6718` |
| 尾部一步 MSE (T=500) | 1.067782 | **1.048759** |
| 截断不变式 (11 点) | 0/0 | **0/0** |
| AR 性能 (2500×300) | 2.76s | **2.72s** |

### 3.7 与 statsmodels 的语义对齐

- 官方文档: `hold_back=None → maxlag`; `hold_back >= maxlag`; 用于"produce comparable models with different lag length" (调研 §3.1)。
- 源码: `y = y[hold_back:]`, `x = x[hold_back:]`。
- 实测: `AutoReg(lags=p, hold_back=5, trend='c')` 与方案 C 的系数/`llf`/`σ²`/`n_obs` **完全一致**; AIC 恒差 `-2`, 来自 statsmodels `AIC = -2·llf + 2·(df_model+1)`、`df_model=p+1` (调研 §6.8)。
- 实测最大偏差 (p=1..5): `max|Δparam| ≤ 5.6e-16`, `|Δllf| ≤ 2.8e-14`, `|Δσ²| ≤ 2.2e-16`, `|ΔAIC| = 2.000`; T2 用 `atol=1e-10` 有充足余量。
- 本项目 AIC 恒定低 2 **不影响排序**; 设计不修改 AIC 公式, 不引入偏移补偿。

---

## §4 接口与契约

### 4.1 公共 API (不变)

| 接口 | 签名 | 变更 |
|------|------|------|
| `AROrderSelector.__init__` | `(max_order=5, min_order=1, criterion='aic', min_obs=20)` | 无 |
| `AROrderSelector.fit` | `(series: pd.Series) -> ARModelResult` | 无 |
| `AROrderSelector.batch_fit` | `(data: pd.DataFrame) -> Dict[str, ARModelResult]` | 无 |
| `ARDecoupler.__init__` | `(max_order=5, min_order=1, criterion='aic', strength=1.0, min_obs=20, warmup_obs=120)` | 无 |
| `ARDecoupler.fit` / `transform` / `fit_transform` | 同现状 | 无 |
| `ARDecoupler.get_residual_stats` | `() -> Dict[str, Dict[str, float]]` | 无 |

### 4.2 私有方法契约

| 契约 | 内容 |
|------|------|
| `_fit_ar(series, order)` 前置 | `series` 已 `dropna`; `order <= max_order` |
| `_fit_ar` 估计样本 | `y[H:]`, `H = max_order`; 所有阶数一致 |
| `_fit_ar` 抛出 | `n_obs <= order+5` → `ValueError`; `lstsq` 失败 → `ValueError("OLS估计失败")` |
| `_fit_ar` 返回 | `ARModelResult` 字段不变; `residuals`/`fitted_values` 索引从 `H` 开始 |
| `_fit_best` 对异常 | 捕获 `Exception` → `continue`; 最终回退 AR(1) |

### 4.3 `ARModelResult` 字段

字段集合与类型**不变**:

```
order, coefficients, residuals, fitted_values,
aic, bic, hqic, r_squared, sigma2, log_likelihood
```

唯一变化: `residuals.index[0] == series.index[H]` (原 `series.index[order]`), 长度 `n-H` (原 `n-order`)。

### 4.4 调用点核对

| 调用点 | 参数形态 | 影响 |
|--------|---------|------|
| [`dual_neutralizer.py L413`](../../modules/factor_decoupler/core/dual_neutralizer.py#L413-L417) | 关键字 `max_order`/`criterion`/`strength`; 未传 `warmup_obs` | 使用默认 120; 行为变更 (预期) |
| [`unified_decoupler.py L162`](../../modules/factor_decoupler/core/unified_decoupler.py#L162-L165) | `AROrderSelector(max_order=..., criterion=...)` | 非生产; 阶数被动变化 |
| `tests/**` | 关键字 | 无签名破坏 |

**结论**: 无位置参数破坏; 无新增参数。

---

## §5 兼容性与影响面

### 5.1 行为影响 (生产路径)

| 对象 | 影响 | 量化 |
|------|------|------|
| `AROrderSelector.fit` / `batch_fit` | 阶数分布变化 | AR(1) 面板均值 4.800 → 1.233 |
| `ARDecoupler.fit` / `_results` | 冻结模型阶数与系数变化 | 93%–96% 输出格子变化 |
| `ARDecoupler.transform` | 冻结段 (`t >= warmup_obs`) 用新模型; warm-up 段用新阶数/系数 | 同上 |
| `ARDecoupler._get_ar_phi_for_diagnosis` | φ 取自新阶数的 `coefficients[1]` | 语义不变; 数值变 |
| `CompositeDecoupler` / `DynamicFactorPipeline` | 通过 Stage 2 被动变化 | 需重算 |
| `PipelineV2Config` / optimizer | **不变** | 无 |

### 5.2 固定阶数 (`min_order == max_order`) 的精确影响

设计期探针 (`T=100/N=3 seed=11`, AR(1) φ=0.7, `warmup_obs=40`):

| 固定阶数 p | `fit` 系数 | `transform` 差异格子 | `max_abs` | 首个差异行 | 末个差异行 |
|-----------|-----------|----------------------|-----------|-----------|-----------|
| 1 | **逐值相同** | 99/300 | 2.694613 | t=7 | t=39 |
| 2 | **逐值相同** | 96/300 | 5.251495 | t=8 | t=39 |
| 3 | **逐值相同** | 93/300 | 5.973263 | t=9 | t=39 |

**解释**:
- `H = p` 时 `y[H:] = y[p:]`, 冻结模型 (`_results`) 与现状**逐值相同**; `t >= warmup_obs` 的冻结段也相同。
- warm-up 段不同, 因为守卫使首个可拟合 `t` 从 `early = p+6` 推迟到 `t = H+p+6` (n_obs 需 `> p+5`); refit 步点随之平移, 系数前缀不同。
- 这是**有意的**: warm-up 行为属于过渡段, 修复目标是估计样本一致性; 冻结模型与最终输出主体不变。

### 5.3 索引与 NaN 影响

| 消费端 | 影响 |
|--------|------|
| `ARDecoupler.get_residual_stats` | `dropna()` 后计算; 统计值随模型变化, 索引起点不影响 |
| [`TemporalDecoupler._apply_ar_residual`](../../modules/factor_decoupler/core/unified_decoupler.py#L375-L381) | `p < H` 的列: 索引从 `index[p:]` 变 `index[H:]`; `reindex` 后中间 `H-p` 行变 NaN; `p = H` 的列不变 |
| `ARDecoupler.transform` | 不消费 `residuals`; 仅 `order`/`coefficients` → 无影响 |

### 5.4 版本与缓存

| 项 | 当前 | 修复后 | 位置 |
|----|------|--------|------|
| 项目版本 | 3.3.6 | **3.3.7** | `pyproject.toml:7` / `__init__.py:58` / `config_v2.py:371` / `reporting.py:40` |
| 缓存代号 | `v2.2.4-cache` | **`v2.2.5-cache`** | `backtest/cache_manager.py:58` |
| ADR | ADR-040 | **ADR-041** | `DECISIONS.md` 占用表 L43-L44 |
| 版本测试 | `EXPECTED_VERSION=3.3.6` | **3.3.7** | `tests/test_fix3_version_unification.py:33` / `tests/test_backtest/verify_fix3_manual.py:21` |

### 5.5 回滚

1. 恢复 `_fit_ar` 的 `y[order:]` / 滞后列 / `n_obs = n-order` / 残差索引 `series.index[order:]`;
2. 删除有效样本守卫;
3. 恢复 `CODE_VERSION = "v2.2.4-cache"` 与版本 3.3.6;
4. 重建缓存。

无需数据迁移; 回滚后缓存需重建 (新旧代际不兼容)。

---

## §6 测试设计 (TDD)

### 6.1 新增单元测试

建议文件: `tests/unit/test_ar_order_holdback.py`。

| # | 测试名 | 断言 (设计级) |
|---|--------|--------------|
| T1 | `test_common_effective_sample` | 同一序列 `order=1..max_order` 的 `len(res.residuals)` **全部相等** 且 `== n - max_order` |
| T2 | `test_matches_statsmodels_hold_back` | `AutoReg(lags=p, hold_back=H, trend='c').fit()` 对比 `params` / `llf` / `sigma2` / `nobs`, `atol=1e-10`; `res.aic - sm.aic ≈ -2` |
| T3 | `test_guard_rejects_insufficient_effective_sample` | `n = H + order + 5` → `ValueError`; `n = H + order + 6` → 正常返回 |
| T4 | `test_residual_index_starts_at_hold_back` | `res.residuals.index[0] == series.index[H]`; `len == n-H` |
| T5 | `test_order_selection_low_on_ar1` | AR(1) φ=0.7 面板 (T=100/N=30 seed=22), `AROrderSelector(max_order=5).batch_fit` 均值 **≤ 2.0** |
| T6 | `test_order_selection_recovers_ar2` | AR(2) (0.6, 0.3) 面板 (T=120/N=30 seed=11), 均值 **∈ [1.8, 3.2]** |
| T7 | `test_order_selection_recovers_ar3` | AR(3) (0.5, 0.3, 0.2) 面板 (T=120/N=30 seed=5), 均值 **∈ [2.4, 3.8]** |
| T8 | `test_fixed_order_fit_matches_current_formula` | `min_order == max_order == p`; `_results` 系数与独立参考实现 (`y[p:]` + 滞后矩阵) **逐值相同** (`atol=0`) |
| T9 | `test_no_zero_variance_fit_in_warmup` | `ARDecoupler(max_order=5, warmup_obs=40)` 跑 T=80 AR(1) 面板; `warnings.catch_warnings(record=True)` 中**无** `divide by zero` / `invalid value`; 输出全有限; **并断言 `t ∈ {7..11}` 输出 == 输入** (守卫 → identity, 锁定 D3 行为) |
| T10 | `test_warmup_early_truncation_invariant` | 与既有测试同配置 (`max_order=3, warmup_obs=40`, T=100/N=10 seed=22); 参数化 `t ∈ {7, 8, 9, 10, 12}`; 全样本 vs 截断输出逐元素相等 (`atol=1e-12`); 锁定守卫引入的早期 identity 边界 |
| — | 既有 `test_truncation_invariant_multi_cut` | `t ∈ {10,15,25,30,45,60,80}` 不改; 与 T10 并集 = 11 个不同截断点 |

**测试数据策略**: T2 用 statsmodels 作独立参考; T8 用手写参考实现; T5–T7 用固定 seed 的合成面板; 不得用被测代码自证。

### 6.2 既有测试预演 (设计阶段实测)

**方法**: 运行时把 `AROrderSelector._fit_ar` 替换为方案 C 实现 (`%TEMP%\pl08_patch.py`), 跑靶向套件。

| 套件 | 未打补丁 | 打补丁 (方案 C) |
|------|---------|----------------|
| `tests/unit/test_ar_decoupler_causality.py` | 通过 | **通过** |
| `tests/test_factor_decoupler/test_hidden_effect.py` | 通过 | **通过** |
| `tests/test_pipelines_v2.py` | 除 1 项环境失败外通过 | **除 1 项环境失败外通过** |
| `tests/integration/test_pipeline_truncation_invariance.py` | 通过 | **通过** |
| 合计 | **72 passed / 1 failed (17.58s)** | **72 passed / 1 failed (20.64s)** |

**唯一失败**: `test_E10_bridge_init_params_exist` — `ModuleNotFoundError: duckdb`; 未打补丁时同样失败, 属**环境缺包**, 与 PL-08 无关 (pyproject 声明 `duckdb>=0.10.0`, 本机未安装)。

**结论**: 既有行为测试**无新增失败**; 尽管输出 93%–96% 变化, 测试断言的是不变量/关系而非具体 AR 数值。

### 6.3 回归基线命令

```powershell
python -m pytest `
  tests/unit/test_ar_decoupler_causality.py `
  tests/test_factor_decoupler/test_hidden_effect.py `
  tests/test_pipelines_v2.py `
  tests/integration/test_pipeline_truncation_invariance.py -q
```

预期: **72 passed / 1 env-fail (duckdb)**; 新增 `test_ar_order_holdback.py` 后计数相应增加。

---

## §7 验收标准

| # | 标准 | 验证方式 |
|---|------|---------|
| V1 | 同一序列 AR(1..5) 的 `n_obs` 全部相等且 `= n - max_order` | T1 |
| V2 | 系数/`llf`/`σ²`/`n_obs` 与 statsmodels `hold_back` 完全一致; AIC 差恒 -2 | T2 |
| V3 | 守卫边界: `n_obs = order+5` 抛错; `order+6` 通过 | T3 |
| V4 | `residuals` 索引起点 = `index[H]`, 长度 `n-H` | T4 |
| V5 | AR(1) 选阶均值 ≤ 2.0; AR(2)/AR(3) 恢复区间 | T5–T7 |
| V6 | 固定阶数 `fit` 系数与当前逐值相同 | T8 |
| V7 | warm-up 无 `σ²=0` / `ln(0)`; 输出有限 | T9 |
| V8 | 截断不变式: 既有 7 点 + 新增早期 5 点 (7/8/9/10/12), 共 11 个不同截断点 **0 格 / 0 NaN** | 既有 `test_truncation_invariant_multi_cut` + T10 |
| V9 | 靶向套件 **无新增失败** (72 passed / 1 env-fail 基线) | §6.3 |
| V10 | AR 性能 ≤ 3.1s (2500×300 本机) | 计时探针 |
| V11 | 版本 3.3.7 / 缓存 `v2.2.5-cache` / ADR-041 / CHANGELOG / 文档同步 | 文档核对 |
| V12 | 全仓无"跨阶不同 `n_obs`"残留: `git grep -n "y\[order" -- modules/factor_decoupler/core/ar_model.py` **0 命中** (覆盖 `y[order:]` 与 `y[order - i:` 两种模式); `git grep -n "y\[order" -- modules/` 仅剩 `optimized.py` L221-L222 (白名单) | grep |

---

## §8 实施步骤 (TDD 顺序)

| 步 | 动作 | 产出 |
|----|------|------|
| 1 | Red: 新增 `tests/unit/test_ar_order_holdback.py` (T1–T10), 确认失败 (预期多数失败) | 失败测试 |
| 2 | Green: 改 `_fit_ar` (hold_back + 守卫 + 索引) | 新增单测通过 |
| 3 | 回归靶向套件 (§6.3) + 复测 T=100/T=500 输出偏移 | 验收记录 |
| 4 | 性能复测 (2500×300) + 退化警告检查 | 验收记录 |
| 5 | 版本 / 缓存 / ADR-041 / CHANGELOG; 更新版本测试字面量 | 文档同步 |
| 6 | 步骤 10 审计 (audit-driven-development) | 审计报告 |

---

## §9 风险与未决问题

| # | 风险/问题 | 处置 |
|---|----------|------|
| R1 | 输出 93%–96% 变化, 历史 IC/Sharpe 不可比 | CHANGELOG 明示; 缓存 bump; 重算; 下游再校准 |
| R2 | AIC 仍不一致 (固定概率过选阶) | 非目标; 文档写明"可比性修复, 非一致性修复"; 保持 AIC 默认 |
| R3 | 固定阶数时 warm-up 段仍变化 (93–99/300 格, `max_abs` 2.7–6.0) | 文档写明"冻结模型等价, warm-up 过渡段不同"; 不在测试中断言 warm-up 逐值 |
| R4 | `TemporalDecoupler` 阶数与残差 NaN 模式被动变化 | 非生产路径; 登记; 不纳入验收 |
| R5 | `min_obs <= max_order` 极端配置可能整列不可估 | `batch_fit` 既有降级 (跳过该列) + `logger` 提示; 文档写明建议 `min_obs > 2*max_order + 5` (全部阶数可估), 至少 `min_obs > max_order + 6` (AR(1) 可估); 默认 `20 > 15` 满足 |
| R6 | `_fit_ar` 前置要求 `series` 已 dropna | 所有内部调用方已满足; docstring 写明 |
| R7 | 常数序列 (`σ²=0`) 的既有边界未修 | 既有行为; 本次仅堵 `n_obs <= k` 一类; 若需处理另立任务 |
| R8 | AICc 未加入; 若未来 `warmup_obs < 60` 小样本窗口 | 保持 `warmup_obs=120`; 若暴露配置面, 重新评估 AICc |
| R9 | 性能回退 | 实测 2.72s vs 2.76s (反而略快); V10 上限 3.1s ≈ +12%, 覆盖单次运行噪声 |
| R10 | 守卫被误读为"高阶打压" | 文档写明"仅排除不可估阶"; AR(2)/AR(3) 恢复测试作反证 |

---

## §10 ADR-041 决策要点 (供实施时抄录)

1. **决策**: `AROrderSelector._fit_ar` 对所有阶数统一 `hold_back = max_order`, 使 AIC/BIC/HQIC 在同一估计样本上可比; 并增加有效样本守卫 `n_obs <= order+5 → ValueError`。
2. **背景**: 当前 `y[order:]` 使 `n_obs = n - order`, 每多一阶少 1 个观测; 似然项的样本因子约降 `ln(2πσ²)+1 ≈ 2.84` (> AIC 罚 2), 系统性偏向最高阶。AR(1) 真值面板选阶均值 4.800 (AIC) / 2.200 (BIC) / 3.867 (HQIC)。
3. **备选**: A 仅 hold_back (早期 `σ²=0`, `max_abs=322.68`)、B 守卫 `order+2` (早期仍用 4–6 观测)、D +AICc (无增益)、E 默认 BIC (AR(3) 低估)。
4. **影响**: 阶数均值 4.8→1.2–1.6; 输出 93%–96% 变化; 截断不变式 0/0; 性能无变化; `residuals` 索引起点变 `H`; 固定阶数 `fit` 等价、warm-up 段变化。
5. **范围边界**: 只改 `_fit_ar`; 不修 `OptimizedARDecoupler` / `TemporalDecoupler`; 不新增 AICc/不改默认准则; 不改配置面/optimizer。
6. **外部依据**: statsmodels `AutoReg.hold_back` 文档/源码 (A)、Cross Validated Q94718 接受答案 (A)、Shibata (1976) / Hurvich & Tsai (1989/1993) DOI、Ing & Wei (2005) 摘要 (A)、Hurvich NYU 讲义 (A)。
7. **回滚**: 恢复 `_fit_ar` 四处改动; 版本/缓存回退; 重建缓存。

---

## §11 调研依据映射

| 设计条目 | 调研锚点 | 状态 |
|---------|---------|------|
| D1 `hold_back=max_order` | §3.1 statsmodels 文档/源码 | ✅ A |
| D2 守卫 `n_obs > order+5` | §6.5 退化实测; §6.6 AICc 分母 | ✅ C/A |
| D3 `transform` 不改 | §6.4 截断不变式; §6.5 守卫等效 | ✅ C |
| D4 索引 `index[H:]` | §6.1 `n_obs` 表; §7.1 消费端 | ✅ C |
| D5 保持 AIC 默认 | §2.2 AIC 预测有效性; §6.2 T=500/T=100 AICc 对比 | ✅ A/B/C |
| D6 `_fit_best` 不改 | §6.5 默认配置守卫不触发 | ✅ C |
| D7 范围 | §7.1 / §7.3 | ✅ C |
| D8 版本/缓存/ADR | §7.2 | ✅ C |
| D9 不新增参数 | §7.1 配置面不变 | ✅ C |
| D10 既有行为测试不改 (预演 72/1) | §6.2 预演 | ✅ C |

---

## 附录 A: 公式与探针数据

### A.1 统一样本公式

```
H = max_order
n_obs = n - H
y_trim = [y_H, y_{H+1}, ..., y_{n-1}]
X[:, j] = [y_{H-j}, y_{H-j+1}, ..., y_{n-1-j}]   j = 1..order
X = [1, X]                                        (截距前置)
beta = argmin ||y_trim - X beta||²
k = order + 1
sigma2 = mean(residual²)                          (ddof=0)
ll = -(n_obs/2) [ln(2π sigma2) + 1]
AIC = -2 ll + 2k
BIC = -2 ll + k ln(n_obs)
HQIC = -2 ll + 2k ln(ln(n_obs))
```

### A.2 固定阶数探针原始输出

```text
fixed p=1: fit_coef_identical=True cells=99/300 max=2.694613 first_diff_row=7 last_diff_row=39
fixed p=2: fit_coef_identical=True cells=96/300 max=5.251495 first_diff_row=8 last_diff_row=39
fixed p=3: fit_coef_identical=True cells=93/300 max=5.973263 first_diff_row=9 last_diff_row=39
```

数据: `T=100/N=3 seed=11`, φ=0.7, `warmup_obs=40`; `t >= 40` 冻结段无差异。

### A.3 靶向套件预演

```text
未打补丁: 1 failed, 72 passed, 4 warnings in 17.58s
打补丁  : 1 failed, 72 passed, 4 warnings in 20.64s
失败项   : tests/test_pipelines_v2.py::TestPipelineV2ConfigFields::test_E10_bridge_init_params_exist
原因     : ModuleNotFoundError: No module named 'duckdb' (环境缺包, 与 PL-08 无关)
```

---

## §12 步骤 4 review 记录 (幻觉排查与代码对齐)

**方法**: 逐项核对设计声明 vs 源码 (行号/签名/调用点/字段)、版本与 ADR 锚点、调研 v1.2 数值回源、既有测试锚点 (含运行时验证: grep 实测 / 文件存在性 / duckdb 导入)。

### 12.1 核对通过项

| # | 检查项 | 方法 | 结果 |
|---|--------|------|------|
| P1 | 行号: `_fit_ar` L139-184 / `_fit_best` L101-137 / `AROrderSelector.fit` L80-99 / `batch_fit` L199-225 / `ARDecoupler.fit` L286-306 / φ 钩子 L308-339 / `transform` L341-403 | grep + 读码 | **吻合** (步骤 8 勘误: φ 钩子实际止于 **L308-L330**, L332-L339 为 `_predict_one_step`, §2.1 已改; 其余行号吻合) |
| P2 | 签名: `AROrderSelector(max_order=5, min_order=1, criterion='aic', min_obs=20)`; `ARDecoupler(..., strength=1.0, min_obs=20, warmup_obs=120)` | 读 `__init__` | **吻合** |
| P3 | 版本锚点: pyproject L7 / `__init__.py` L58 / `config_v2.py` L371 / `reporting.py` L40 / `cache_manager.py` L58 / `test_fix3` L33 / `verify_fix3_manual` L21 | grep | **全部吻合** |
| P4 | ADR 登记: `DECISIONS.md` L43 (ADR-040) / L44 (ADR-041 起 未占用) | 读码 | **吻合** |
| P5 | §3.6 数值回源: `n_obs` 95×5 / 阶数 4.800→1.233、2.200→1.000、3.867→1.000、4.867→1.600、2.53、3.23 / 输出 2790 与 14410 / MSE 1.067782→1.048759 / 性能 2.76→2.72 | 逐项比对调研 v1.2 §6 | **一致** |
| P6 | §5.2 固定阶数表 vs 探针 A.2: 99/96/93 格、max 2.694613/5.251495/5.973263、first=7/8/9、last=39; `H+p+6` 推迟公式与三点吻合 | 探针输出比对 | **一致** |
| P7 | §6.2 预演: 72 passed / 1 failed; 17.58s / 20.64s | 实跑两组 | **一致** |
| P8 | `_fit_ar` 调用点全集: L117 (循环) / L132 (回退) / L379 (transform); `_fit_best` 调用点 L94/L381; 全部在 `ar_model.py` 内 | grep | **范围声明成立** |
| P9 | 回退 L129-133 不在 try 内; transform 短前缀 try/except→continue→identity | 读码 | **吻合** (§3.2 声明成立) |
| P10 | 既有测试锚点: `test_truncation_invariant_multi_cut` 参数化 7 点; `_panel(n_periods=100, n_stocks=5, seed=7, phi=0.7)`, 既有测试用 `_panel(100, 10, seed=22)` | 读码 | **T10 配置声明成立** |
| P11 | `tests/unit/test_ar_order_holdback.py` 不存在 | Test-Path | **无命名冲突** |
| P12 | `duckdb` 导入失败 (ModuleNotFoundError) | python -c | **环境失败声明成立** |
| P13 | `ARModelResult` 十字段与 §4.3 一致 | 读 dataclass | **吻合** |
| P14 | 学术声明: 全部经调研 v1.2 转引 (statsmodels hold_back 原文/源码、SE Q94718、DOI、Hurvich 讲义), 无新增未核实引用 | 调研 §12 修订记录 | **通过** |
| P15 | V12 可行性: `git grep -n "y\[order:\]" -- modules/` 当前命中 ar_model.py:146 + optimized.py:222; 修复后 ar_model 归零 | 实跑 grep | **白名单声明成立** (V12 已按 F3 精确化) |
| P16 | 默认配置拟合路径可估性: `n_obs >= 15 > 10` (order=5 守卫) | 算术核验 | **成立** |

### 12.2 发现并已修复的问题

| # | 严重度 | 问题 | 修复 |
|---|--------|------|------|
| F1 | MINOR | §2.1 `CompositeDecoupler.fit` 行号锚点写 L405-L428; 实际 `def fit` 在 **L384** (L405-L428 只是 Stage 2 段落) | 已改为 L384-L428, 并补调用点 L413-L417 |
| F2 | MINOR | §3.1 伪代码在 residuals 之后重复 `n_obs = len(residuals)` (与守卫前取值恒等), 实施转录时易困惑 | 已删除, 改为守卫处注释 `n_obs == len(residuals)` |
| F3 | MINOR | V12 只查 `y[order:]` 单模式, 漏 `y[order - i:` 滞后列模式; 白名单行号未写明 | 已改为 `y\[order` 前缀双模式 + ar_model 0 命中 + optimized.py L221-L222 白名单 |
| F4 | MINOR | T9 只断言"无警告 + 输出有限", 未显式锁定守卫引入的 identity 行为 | 已补 `t ∈ {7..11}` 输出 == 输入 断言 |
| F5 | MINOR | §0 性能上限写 "≤ 3.1s (≤ +10%)", 但 3.1/2.76 ≈ +12%, 口径不一致 | 已改为 "≈ +12%, 含噪声余量"; R9 同步 |

### 12.3 结论

- 无幻觉级错误: 全部行号 (除 F1 一处段落锚点)、签名、默认值、ADR 引用、调研数值、测试锚点均可回源。
- 5 处 MINOR 已全部修复; 设计文档升为 **v1.1**。
- 设计与调研 v1.2、源码现状、ADR 登记规则三方一致, 可进入步骤 5 (实施文档)。

---

**设计完成**: 2026-11-04 (v1.2; v1.1 = 步骤 4 review 通过, v1.2 = 步骤 8 一致性 review 行号勘误); 下游工件已推进至步骤 9 (TDD 实现) 前。
