# PL-05 Dynamic AR 前视缺陷调研

**文档版本**: v1.4 (2026-11-04; 步骤 8 一致性 review 修订: 重估次数 / 性能口径 / 缓存行号 / 证据等级)
**日期**: 2026-11-04
**缺陷编号**: DEFECT-PL-05
**目标版本**: **v3.3.6** (设计已定稿; 缓存 `v2.2.4-cache`)
**实施状态**: **已实施 (v3.3.6, 2026-11-04)**; 实测与验收见 [EXECUTION_V3.3.6 §7.2](../EXECUTION_V3.3.6_PL05_DYNAMIC_AR_CAUSALITY.md)
**调研范围**: `ARDecoupler` 的 `fit`/`transform`、`AROrderSelector`、`CompositeDecoupler` Stage 2、`DynamicFactorPipeline` 端到端
**调研方法**: 源码逐行核对 + 截断不变式探针 + 候选方案对拍 + 既有测试预演 (运行时补丁) + WebSearch
**核心原则**: t 时刻的预测只能使用 `F_{t-1}` 中已实现的滞后值, 且 AR 阶数与系数只能由 t 时刻及以前的样本估计; 同一交易日内的横截面信息属于 `F_t`, 未来交易日不属于

**证据等级**:
- **A**: 直接读到原文/摘要/官方方法论文档, 可核对
- **B**: 搜索结果摘要、二手文献或项目内文档转引, 未读到原文对应段落
- **C**: 项目内部代码/文档, 可逐行核对
- **U**: 未能验证, 明确标注, 不作为论据

---

## §0 摘要 (TL;DR)

PL-05 是 **Dynamic 管线中 AR 解耦的全样本拟合 + 用样本内拟合值充当一步预测**:

| # | 事实 | 性质 | 实测 |
|---|------|------|------|
| 1 | `ARDecoupler.fit` → `AROrderSelector.batch_fit(data)` 在**整条序列**上用 AIC 选阶 | 前视: 阶数依赖 t 之后的数据 | `ARDecoupler` 单步截断 (seed=22): **1652 / 1800 格**, `max_abs=8.788e-01` |
| 2 | `AROrderSelector._fit_ar` 在**整条序列**上用 OLS 估计 `[intercept, φ_1..φ_p]` | 前视: 系数依赖 t 之后的数据 | 同上 |
| 3 | `ARDecoupler.transform` 用 `fitted_values.reindex(series.index).ffill()` 当作 "预测" | 用**样本内拟合值**(每点都用了未来信息) 当一步预测; 前 `order` 行无值 → NaN | AR 输出 NaN = **146 / 3000** (= Σorder × 30, 阶数 4–5) |
| 4 | Dynamic 端到端 (t=60/100) | 缺陷 1–3 的合成结果 | **1653 格 / 8 NaN / 8.045e-01**, 57/60 行, 首个发散日 2020-04-30 |

**结论**:

1. **前视有两层, 不止 fitted_values**。只把 `fitted_values` 换成递归预测、但保留全样本阶数/系数, 仍会因 `φ` 依赖未来样本而违反截断不变式。因此修复必须同时因果化 **阶数选择** 与 **系数估计**。
2. 四种候选 (A 逐 t 扩展重估 / B 前 K 冻结 / B' 逐 t warm-up + 冻结 / B'' 两段 warm-up + stride + 冻结) 在探针面板上全部满足截断不变式 (0 格 / 0)。但 A 的复杂度是 `O(T²·N)`, 2500×300 外推约 1.9 小时, 不可实施; B 冷启动过长 (K 行完全不处理); B' 太慢 (8.4–19.1s/2500×300); **B'' 是唯一同时满足"因果 + 秒级 + 既有测试不改"的方案**。
3. **B'' 的关键参数由既有测试反推**: `warmup_obs=120` (K≤60 时两个 φ 精度断言会失败)、`stride=10`、冷启动 `t < min_order+6` identity、`min_order+6 ≤ t < min_obs` 固定低阶、`min_obs ≤ t < K` 逐步重估、`t ≥ K` 冻结。详见 §3.4 / §5.2。
4. **`transform` 中对 `_results` 的存在性门控必须移除**: 截断到 `t < min_obs` 时 `batch_fit` 不会产出任何结果, 门控会让整列退化为 identity, 而全样本运行会正常解耦 → `t=10/15` 仍违反不变式 (实测 90 / 240 格)。这是探针发现的**第二个必要条件**, 设计文档必须纳入。
5. 修复后 Dynamic 端到端与顶层 V2 端到端均 **0 格 / 0 NaN / 0**, **PL-07 的 xfail 也会转绿** (其实测差异 1.8397 完全来自 PL-05, 同面板路由全程一致)。实施时需同步摘除 PL-07 标记, 否则 `strict=True` 的 xfail 会以 XPASS 报错。
6. 代价: AR 单步 0.48s → **2.1–5.8s** (两次探针, 机器负载差异); Dynamic 全管线 33.19s → **42.50s** (+28%); 存量输出 ≈95% 格子变化 (2851–2855/3000, `max_abs` 2.1–4.2), 版本与缓存代际必须 bump。

---

## §1 缺陷复现与范围

### 1.1 代码路径

| 位置 | 行为 | 性质 |
|------|------|------|
| [`DynamicFactorPipeline.fit`](../../pipelines_v2.py#L985-L1023) | 插补 → 构造 [`CompositeDecoupler`](../../pipelines_v2.py#L1000) → `fit` → `transform` → 拟合标准化器 | AR 在 Stage 2 进入 |
| [`CompositeDecoupler.fit`](../../modules/factor_decoupler/core/dual_neutralizer.py#L384-L428) | Stage 1 逐日中性化 (因果) → `ARDecoupler.fit(residuals_stage1)` | **全样本 AR 拟合入口** |
| [`CompositeDecoupler.transform`](../../modules/factor_decoupler/core/dual_neutralizer.py#L444-L502) | Stage 1 → `_ar_decoupler.transform` → Stage 3 逐日中性化 (因果) | Stage 1/3 已实测 0 格 |
| [`ARDecoupler.fit`](../../modules/factor_decoupler/core/ar_model.py#L256-L272) | `self._selector.batch_fit(data)` | 全样本 AIC 选阶 |
| [`AROrderSelector.fit`](../../modules/factor_decoupler/core/ar_model.py#L80-L129) | `series.dropna()` 后遍历 `order ∈ [min_order, max_order]`, 取最优准则 | **前视 1: 阶数** |
| [`AROrderSelector._fit_ar`](../../modules/factor_decoupler/core/ar_model.py#L131-L176) | 滞后矩阵 + `np.linalg.lstsq` 全样本 OLS; `fitted_values` 索引从 `series.index[order]` 开始 | **前视 2: 系数** |
| [`ARDecoupler.transform`](../../modules/factor_decoupler/core/ar_model.py#L298-L331) | `predicted = ar_result.fitted_values.reindex(series.index).ffill()`; `residual = series - predicted` | **前视 3: 样本内拟合值 + NaN 模式** |
| [`_get_ar_phi_for_diagnosis`](../../modules/factor_decoupler/core/ar_model.py#L274-L296) | 从 `_results` 取 `coefficients[1]` 的均值 | ADR-030 诊断契约; 若 `fit` 全样本, φ 也是全样本量 |
| [`DualNeutralizer.transform`](../../modules/factor_decoupler/core/dual_neutralizer.py#L112-L209) | 逐日期截面 OLS (行业哑变量静态) | 已实测因果 (0 格) |
| [`_neutralize_ar_residuals`](../../modules/factor_decoupler/core/dual_neutralizer.py#L508-L537) | 逐日期截面 OLS | 已实测因果 (0 格) |

### 1.2 实测基线

**面板 A (集成测试精确数据集)**: `T=100, N=30, seed=22, kind='ar_low'`, 行业 4 组, 截断 `t=60`, `atol=1e-12`。该面板与 `test_dynamic_pipeline_is_truncation_invariant` 完全一致。

| 指标 | AR 单步 | Dynamic 端到端 | 登记值 (xfail reason) |
|------|---------|----------------|----------------------|
| 差异格子 / 总格子 | **1652 / 1800** | **1653 / 1800** | — |
| 有差异行 / 总行 | 56 / 60 | 57 / 60 | — |
| `max_abs_diff` | **8.788029568942268e-01** | **8.045313632310727e-01** | 8.05e-01 ✓ |
| NaN 模式不一致 | **7** | **8** | 8 格 ✓ |
| 首个发散日 | 2020-05-31 (第 5 期) | 2020-04-30 (第 4 期) | — |
| 全样本 AR 输出 NaN | **146 / 3000** | — | — |

> AR 阶数分布 (该面板全样本): `{4: 4, 5: 26}`, mean **4.867**; NaN 146 = `4×4 + 5×26` = Σorder × 30。这解释了 NaN 的来源: `fitted_values` 从第 `order` 期才开始, `reindex` 产生前导 NaN, `ffill` 不向前填充。

**面板 B (顶层 V2)**: `T=100, N=30, seed=31, kind='skewed'`。

| 指标 | 基线 | 说明 |
|------|------|------|
| 差异格子 | **1650 / 1800** | 与 PL-07 登记值 "1650 格" 一致 |
| `max_abs_diff` | **1.8397305724759783** | 与 PL-07 登记值 1.84e+00 一致 |
| 路由 (全样本 vs 截断) | **相同** | 说明本数据集的顶层差异**不是**路由造成的 |

### 1.3 生产路径映射

| 管线 | 是否使用 AR | 是否受 PL-05 影响 |
|------|------------|------------------|
| `StaticFactorPipeline` | 否 | 否 |
| `DynamicFactorPipeline` | **是** (`CompositeDecoupler` Stage 2) | **是** |
| `MixedFactorPipeline` | 否 | 否 |

其他含同类模式的实现**不在生产路径**, 本次不修 (见 §5.4):

| 位置 | 同类问题 |
|------|---------|
| [`OptimizedARDecoupler`](../../modules/factor_decoupler/core/optimized.py#L119) | 全样本选阶 + 全样本系数; `transform` 用实际滞后值预测 (无 `fitted_values` 前视), 但阶数/系数仍全样本 |
| [`TemporalDecoupler._apply_ar_residual`](../../modules/factor_decoupler/core/unified_decoupler.py#L375-L381) | 直接返回 `ARModelResult.residuals` (样本内残差), 前导 NaN |

### 1.4 与其余缺陷的关系

| 缺陷 | 关系 |
|------|------|
| PL-01 / PL-02 / PL-06 | 同类根因 (全样本估计参数), 宿主不同; 修复口径可作先例 |
| PL-03 | 标准化解析, 与本缺陷无交集 |
| PL-07 | 登记原因为 "上游 PL-05 + 路由"; 本次实测**路由全程一致**, 差异 100% 来自 PL-05。修复后 PL-07 的 xfail 转绿 (§5.2) |

### 1.5 为什么此前没有暴露

1. **样本内残差天然"更白"**。全样本 `fitted_values` 是在同一批数据上做 OLS 得到的, 残差与滞后值的样本内相关性被机械压低: 实测 AR(1) 因子 (φ=0.7) 的样本内残差 `mean_ar1 ≈ -0.0001`, 而因果一步残差为 `+0.048 ~ +0.065`。也就是说, 当前实现报告的"去相关效果"部分是**过拟合幻觉**。
2. **NaN 被下游吸收**。AR 前导 NaN 经 Stage 3 `dropna` 与逐日 z-score 后大部分消失, 只在截断比较中以"NaN 模式不一致"的形式暴露 (8 格), 不易在常规指标里看到。
3. **排序类指标不敏感**。AR 残差之后还有 Stage 3 中性化与标准化, 逐日排序差异被压缩; 只有**逐元素相等的截断不变式**能稳定探出。

---

## §2 判据: 什么是"因果的 AR 解耦"

### 2.1 操作化定义

对任意截断点 `t`, 记 `F([0,t])` 为只用 `[0,t]` 数据 `fit` + `transform` 的结果。要求:

```
F([0,t] 数据)[0,t] ≡ F([0,T] 数据)[0,t]      (逐元素, 容差 0)
```

对 AR 解耦而言, 第 `i` 期的输出只能依赖:
- 第 `i` 期及以前的因子值 (含当日, 因为因子在当日收盘后可观测);
- 由第 `i-1` 期及以前样本估计的 AR 阶数与系数。

### 2.2 理想的结构性质

| # | 性质 | 说明 |
|---|------|------|
| N1 | 阶数选择只用前缀 | `t` 期的阶数不得由 `[t+1, T]` 的 AIC 决定 |
| N2 | 系数估计只用前缀 | 同上 |
| N3 | 预测只用已实现的滞后值 | `ŷ_t = c_0 + Σ c_i y_{t-i}`; 不使用任何"拟合值" |
| N4 | 短截断面板不得因缺少 `_results` 而整列退化为 identity | 否则 `t<min_obs` 的截断运行与全样本运行不一致 (§3.8) |

N1/N2 是本次调研最重要的发现: **只改 N3 不够**。若保留全样本阶数与系数, `t` 期的 `ŷ_t` 仍随 `T` 变化, 截断不变式不成立。

### 2.3 数据契约

- `X: pd.DataFrame`, index = 日期, columns = 股票。
- 逐列独立拟合; 每列至少 `min_obs` 个非 NaN 观测才允许进入 AIC 选阶。
- NaN 通过滞后值自然传播: 若 `y_{t-i}` 为 NaN, 则 `ŷ_t` 为 NaN, 该格输出 NaN。
- 冷启动 (`t < min_order+6`) 输出 **identity** (原始值), 不新增 NaN (理由见 §3.7)。
- 输出保留 index / columns; 已拟合列的输出不新增 NaN。

### 2.4 与"样本内拟合值"的区别

```
当前:  ŷ_t = x_tᵀ β̂(全样本)          ← β̂ 与 x_t 都参与同一批样本的 OLS
因果:  ŷ_t = c_0 + Σ c_i y_{t-i}      ← 只用 t-1 及以前的值; c 由前缀估计 (或早期前缀 + 冻结)
```

两者在 `t` 上形式相同, 但 `β̂(全样本)` 的估计样本包含 `t+1..T`, 因此当前 `ŷ_t` 是**平滑过的样本内拟合**, 不是可交易的一步预测。

---

## §3 候选方案评估

### 3.0 候选枚举

| 代号 | 策略 | 阶数/系数来源 | 预测 |
|------|------|--------------|------|
| A | 逐 t 扩展重估 | `[0,t)` 全量 AIC + OLS | 递归一步 |
| B | 前 K 冻结 | `[0,K)` 一次 AIC + OLS | `t≥K` 递归; `t<K` identity |
| B' | 逐 t warm-up + K 冻结 | `[min_obs,K)` 每个 t 重估; `[0,K)` 冻结 | 同上 |
| B'' | **两段 warm-up + stride + K 冻结** | 早期固定 `min_order`; `[min_obs,K)` 每 `stride` 行重估; `[0,K)` 冻结 | 同上 |
| C | rolling window / RLS | 每 t 用固定窗口或递推最小二乘 | 递归一步 |

### 3.1 方案 A: 逐 t 扩展重估 (拒绝)

```python
for t in range(min_obs, T):
    model = fit(y[:t])                 # AIC + OLS
    yhat[t] = c0 + sum(c_i * y[t-i])
```

**实测**:

| 指标 | 数值 |
|------|------|
| 截断不变式 (t=10/15/25/30/45/60/80) | **0 / 0** (全部) |
| NaN | 0 |
| 性能 (T=100, N=30, 单次) | ≈ **1.07s** |
| 外推 (T=2500, N=300) | ≈ **1.9 小时** (`O(T²·N)`) |
| 外推 (T=2500, N=3000) | ≈ **18 小时** |

**结论**: 因果性最好, 但成本不可接受。拒绝。

### 3.2 方案 B: 前 K 冻结 + identity 冷启动 (拒绝)

`K=60`, `t<K` 全部 identity。

**实测**: 截断不变式 0/0; 2500×300 **0.25s**。

**问题**: `T=100` 时 60 行不做解耦; `T=60` 的既有测试 (`test_pipelines_v2.TestDynamicFactorPipeline`, `n_periods=60`) 会**整条序列 identity**, 使 `test_soft_decoupling_strength` 的 `strength=1.0` 与 `0.5` 输出完全相同而失败。**拒绝**。

### 3.3 方案 B': 逐 t warm-up + K 冻结 (成本过高)

`[min_obs, K)` 每个 t 都做 AIC + OLS, `t ≥ K` 冻结。

**实测**:

| 指标 | 数值 |
|------|------|
| 截断不变式 | 0 / 0 |
| 性能 (2500×300) | **8.37s** (探针 4) / **19.06s** (探针 6, 同语义重写) |
| `mean_ar1` (φ=0.7, K=60) | 0.0979 |
| 早期行 (`min_obs ≤ t < K`) | 正常解耦 |

**问题**: warm-up 阶段每个 t 都要跑 5 个阶数的 OLS, `(K-min_obs)×5×N` 次小 OLS; 2500×300 上 8–19s, 相对 AR 阶段本身 (0.48s) 放大约 20–40 倍。**降级为备选**。

### 3.4 方案 B'': 两段 warm-up + stride + K 冻结 (**推荐**)

```python
early = max(min_order + 6, 2)          # AR(1) 最少 7 个观测
# t < early                → identity
# early ≤ t < min_obs      → 固定 min_order, 每 stride 行重估 (只用前缀)
# min_obs ≤ t < warmup_obs → AIC 选阶, 每 stride 行重估 (只用前缀)
# t ≥ warmup_obs           → 冻结模型 (fit 只用前 warmup_obs 行) 做一步递归
```

参数 (设计已定稿, 见 DESIGN D5):

| 参数 | 定稿值 | 依据 |
|------|--------|------|
| `warmup_obs` (K) | **120** | K≤60 会使两个既有 φ 精度断言失败 (§5.2); K=120 时两者均通过 |
| `warmup_refit_stride` | **10** (私有常量) | 把 warm-up 重估次数由 ~100 降到 **12** (t=7,17,…,117); `K=120, stride=10` 实测 5.76s (探针 6) / 2.11s (探针 8, 两段变体); 质量差 0.048 vs 0.064 (统计起点不同, 量级相当) |
| 冷启动 | identity, `t < min_order+6` | 避免 NaN 污染 (§3.7); `T=60` 的 `nan_ratio < 0.3` 断言需 identity |
| 早期阶数 | 固定 `min_order` | `t<min_obs` 时不足以做 5 阶 AIC |

**实测**:

| 指标 | 数值 |
|------|------|
| 截断不变式 (AR 单步, t=10/15/25/30/45/60/80) | **0 / 0** (全部) |
| 截断不变式 (AR 单步, seed=22, t=60) | **0 格 / 0 NaN / 0.0** |
| Dynamic 端到端 (seed=22, t=60) | **0 / 0 / 0.0** |
| 顶层 V2 (seed=31, t=60) | **0 / 0 / 0.0**, 路由一致 |
| 全样本 AR 输出 NaN | **0** (当前 146) |
| `mean_ar1` (φ=0.7, 500×30, 起点 6) | **0.0647** (当前 ≈ 0.000) |
| 性能 (2500×300, AR 单步) | **2.11–5.76s** (探针 8 / 探针 6; 取保守 5.76s), 当前 0.48s |
| 性能 (Dynamic 全管线 2500×300) | **42.50s** (当前 33.19s, +28%) |
| 冻结阶数 vs 全样本一致率 | **89.00%** (2500×300, seed=11); 阶数均值 4.85 vs 4.94 |
| φ 诊断 (iid 面板) | 前 120 行 **-0.0101** vs 全样本 **-0.0005** |

### 3.5 方案 C: rolling window / RLS (拒绝)

- **rolling window**: 每个 t 都要重估, 成本与方案 A 同阶 (`O(T·W·N)`), 且引入窗口长度这一新配置面。
- **RLS (递推最小二乘)**: 可在线更新、`O(T·N)` 成本, 但改变了模型类 (遗忘因子、数值稳定性、初始化), 与"最小改动修复前视"的目标不符。

**结论**: 不选; 若未来要做自适应系数, 应作为独立能力任务。

### 3.6 方案对比

| 维度 | A 逐 t 扩展 | B 纯冻结 | B' 逐 t warm-up | **B'' 两段+stride** | C rolling/RLS |
|------|------------|----------|----------------|-------------------|---------------|
| 截断不变式 | 0 | 0 | 0 | **0** | 预期 0 |
| 冷启动处理 | 全解耦 | 前 K 行 identity | `t<min_obs` identity | `t<7` identity | 前 W 行 |
| 已有测试 (`T=60`) | 通过 | **`soft_decoupling_strength` 失败** | 通过 | **通过** | 未测 |
| AR 性能 (2500×300) | ~1.9h (外推) | **0.25s** | 8.4–19.1s | **2.11–5.76s** | 未测 |
| 残差白化质量 | 最好 | 中 | 中 | **中上** | 依赖参数 |
| 新增配置面 | 无 | `K` | `K` | **`K` (公开) + `stride` (私有常量)** | 窗口/遗忘因子 |
| 推荐 | 拒绝 (成本) | 拒绝 (短面板失效) | 备选 (成本) | **默认候选** | 拒绝 |

### 3.7 冷启动语义: identity vs NaN vs 延续 NaN (本次实测/推算)

| 策略 | AR 输出 NaN (`T=100, N=30`) | `DynamicPipeline` 的 `nan_ratio` (`T=60`) | 诊断 `information_loss` |
|------|------------------------------|------------------------------------------|------------------------|
| 当前 (前导 `order` 行 NaN) | **146** | 约 7–8% (推算) | `signal_lost` (既有断言) |
| **identity (`t<min_order+6`)** | **0** | **0** | `signal_lost` (实测通过) |
| NaN (`t<min_obs` 全 NaN) | 600 (推算) | **33.3% → `nan_ratio<0.3` 失败** (推算) | 未测 |
| 仅 warm-up 起点 `min_obs`, 更少 identity | 0 | 0 | **`ambiguous` (实测失败)** |

> 关键实测: 若 warm-up 从 `min_obs=20` 才开始 (即 `t<20` 全部 identity), `test_information_loss_signal_lost` 会由 `signal_lost` 变成 `ambiguous` —— 20/120 行的未解耦原值把 `ic_after` 抬高到阈值以上。加入 `t ∈ [7, 20)` 的固定低阶 warm-up 后该测试恢复。这就是"两段 warm-up"的必要性证据。

### 3.8 第二个必要条件: 移除 `transform` 的 `_results` 存在性门控

当前 [`transform`](../../modules/factor_decoupler/core/ar_model.py#L317-L319) 有:

```python
for col in data.columns:
    if col not in self._results:
        continue                      # ← 整列保持 identity
```

`_results` 由 `batch_fit` 产出, 而 `batch_fit` 要求每列至少有 `min_obs` 个非 NaN 观测。因此**截断到 `t < min_obs` 时 `_results` 全空**, 整列退化为 identity; 而全样本运行的同一列在 `t ∈ [7, 20)` 已被解耦。实测 (B'' 首次实现, 两段 warm-up 已就位, 未移除门控):

| 截断点 | 差异格 / NaN 不一致 / max_abs |
|--------|------------------------------|
| t=10 | **90 / 0 / 3.1811** |
| t=15 | **240 / 0 / 3.1811** |
| t=25 / 30 / 45 / 60 / 80 | 0 / 0 / 0 |

移除门控 (改为遍历 `data.columns`, 冻结分支用 `self._results.get(col)`) 后, 上表全部转为 **0 / 0 / 0**。

**含义**: 因果性不能只靠"参数只用前缀", 还必须保证**同一条列在任意截断长度下的处理路径一致**。设计文档需把"不以 `_results` 作为列过滤条件"写成显式约束 (C3)。

---

## §4 学术与工业证据

> 本次外部检索以 WebSearch 为主 (MCP paper-search 本轮不可用, 见附录 B)。以下条目标注证据等级; **未读原文的条目不作为强论据**。

| 主题 | 来源 | 结论 | 等级 |
|------|------|------|------|
| 时序评估只能用历史信息 | Hyndman & Athanasopoulos (2021), *Forecasting: Principles and Practice* (3rd ed.), §5.10 时序交叉验证 | "the training set consists only of observations that occurred **prior** to the observation that forms the test set ... the earliest observations are not considered as test sets"; `tsCV` 默认 expanding window, 单步预测记为 `ŷ_{t|t-1}` | **A** (原文已读, 2026-11-04 WebFetch) |
| 前视偏差污染样本内评估 | López de Prado (2018), *Advances in Financial Machine Learning*, Ch. 7 | 金融样本内评估因前视/泄漏不可信; 需按时间切分 | **B** (项目 PL-01/PL-02 已引用; 本次未重读原文) |
| 递归/一步预测的经典表述 | Hamilton (1994), *Time Series Analysis*, Ch. 3–5 | AR(p) 的一步预测为 `c_0 + Σ c_i y_{t-i}`, 参数由历史样本估计 | **B** (教科书通行结论, 未逐页核对) |
| 扩展窗口 vs 滚动窗口 | Hyndman (2023) `tsCV()` 文档 / 二手讲义 | expanding window 默认保留全部历史; 数据非平稳时用 rolling | **B** (搜索结果摘要) |
| 自适应在线估计 | Haykin (2002), *Adaptive Filter Theory* | RLS 可 `O(p²)` 在线更新系数 | **B** (未读原文; 仅作方案 C 的可行性依据) |
| 项目截面/时序口径 | ADR-027 / ADR-037 / ADR-038 | 因子面板统一逐日截面; 拒绝 per-stock 全历史参数 | **C** |
| 解码器诊断契约 | ADR-030 | φ 由 `_get_ar_phi_for_diagnosis` 单点提取, 布局 `[intercept, φ_1..φ_p]` | **C** |

**证据小结**:

1. "用截止到 `t-1` 的样本做单步预测"是时序预测的标准做法 (B), 不依赖任何特定论文; 当前实现的反例 (样本内拟合值) 在文献中属于典型的 in-sample evaluation, 不能当作 OOS 预测。
2. 项目内部已有三处同类修复 (PL-01/02/06), 口径一致: **参数只由当日或前缀决定**。PL-05 与之同构, 无需新的方法学决策。
3. `K`/`stride` 的取值没有学术最优解, 是**工程折中** (质量 vs 成本 vs 既有断言); 证据等级为 C (本地实测)。

---

## §5 项目内部约束与矛盾

### 5.1 ADR-030 诊断契约

- `ARDecoupler._get_ar_phi_for_diagnosis` 返回 `_results` 中 `coefficients[1]` 的均值; docstring 目前写作"**全样本**平均 AR(1) 系数 φ"。
- 若 `fit` 改为只用前 `warmup_obs` 行, 该 docstring 需改为"拟合窗口内平均"。ADR-030 的正文并未固定"全样本"字样 (grep `全样本平均` 在 `DECISIONS.md` 无命中), 因此**只需改代码 docstring, 不需要改 ADR**。
- 诊断链 (`diagnose_hidden_effects` → `incremental_endogeneity` → φ) 是 post-hoc 分析 API, 不在 `fit_transform` 的生产路径内; 因果化后仍可用。

### 5.2 既有测试预演 (用运行时补丁跑真实测试, 不改仓库代码)

方法: 临时 pytest 插件 `pl05_patch` 在 `pytest_configure` 中替换 `ARDecoupler.fit/transform`, 然后跑靶向测试。

| 测试集 | 结果 |
|--------|------|
| `tests/test_factor_decoupler` (含 `test_hidden_effect.py`) | **全通过** |
| `tests/test_pipelines_v2.py` | **全通过** (含 `T=60` 的 `test_dynamic_pipeline_processing` 与 `test_soft_decoupling_strength`) |
| `tests/test_p0_fixes.py` / `test_p1_fixes.py` / `test_adapters/test_module_enabled.py` | **全通过** |
| `tests/test_endogeneity_regularizer` | **全通过** |
| `tests/integration/test_pipeline_truncation_invariance.py` | 除 2 个 `xfail` 外全通过 |
| **合计** | **117 passed + 11 subtests passed** |

**两个 xfail 均以 XPASS 报错**, 必须在实施时摘除:

| 测试 | 基线 | 补丁后 |
|------|------|--------|
| `test_dynamic_pipeline_is_truncation_invariant` (PL-05) | 1653 格 / 8 NaN / 8.045e-01 | **0 / 0 / 0** → XPASS |
| `test_v2_pipeline_is_truncation_invariant` (PL-07) | 1650 格 / 1.8397 | **0 / 0 / 0**, 路由一致 → XPASS |

**两个反例 (参数取值的直接依据)**:

| 变体 | 失败 | 原因 |
|------|------|------|
| 冷启动 20 行 identity (warm-up 从 `min_obs` 起) | `test_information_loss_signal_lost` → `ambiguous` | 未解耦原值抬高 `ic_after` |
| `K=60` (fit 只用前 60 行) | `test_coefficients_layout_is_intercept_first` (`|φ-0.7|=0.1382 > 0.05`); `test_ar_decoupler_hook_returns_known_phi` (`|φ-0.7|=0.1165 > 0.08`) | 60 个观测的 OLS 噪声 (SE≈0.09) |

**K 敏感性 (两个 φ 精度断言的实测)**:

| K | 用例 1 `\|φ-0.7\|` (阈值 0.05) | 用例 2 `\|mean φ-0.7\|` (阈值 0.08) |
|---|-------------------------------|-----------------------------------|
| 20 | 0.1292 FAIL | 0.3287 FAIL |
| 40 | 0.0905 FAIL | 0.1663 FAIL |
| 60 | 0.1382 FAIL | 0.1165 FAIL |
| 80 | 0.0752 FAIL | 0.0644 PASS |
| 100 | 0.0490 PASS (余量 0.001) | 0.0493 PASS |
| **120** | **0.0479 PASS** | **0.0397 PASS** |
| 160 | 0.0606 FAIL | 0.0379 PASS |
| 200 | 0.0457 PASS | — |

> K=100/120 在用例 1 上余量极小 (0.001–0.002), 属于确定性数据上的"恰好通过"。**§10.2 的 2000 次模拟表明 0.05 容差在 n=120 时覆盖率仅 50.3%**, 因此无论 K 取何值都应放宽该容差 (建议 0.15); 把 K 提到 200 不能替代这一修正。

### 5.3 版本 / 缓存 / 文档

| 项 | 当前 | 建议 |
|----|------|------|
| `__version__` / `config_v2.version` / `reporting.pipeline_version` / `pyproject.toml` | 3.3.5 | **3.3.6** |
| `backtest/cache_manager.CODE_VERSION` | `v2.2.3-cache` | **`v2.2.4-cache`** (Dynamic 输出 ≈95% 变化) |
| `tests/test_fix3_version_unification.py` | `EXPECTED_VERSION=3.3.5`; `v2.2.3-cache` 出现 6 行 (L14/79/84/93/94/109) | 同步: L32 锚点与 L12/39/47/56 文案 → 3.3.6; L14/79/93/94/109 → `v2.2.4-cache`; L84 历史保留, L85 追加 PL-05 行 |
| `tests/test_backtest/verify_fix3_manual.py` | `EXPECTED_VERSION=3.3.5` | 同步 |
| `DECISIONS.md` | ADR-040 起未占用 | 新增 **ADR-040** |
| `CHANGELOG.md` / `docs/ARCHITECTURE.md` / `docs/DEV_PROGRESS.md` | v3.3.5 | 追加 v3.3.6 |

### 5.4 范围边界

| 项 | 归属 |
|----|------|
| `OptimizedARDecoupler` / `OptimizedCompositeDecoupler` | **不在本任务** (仅 `__init__` 导出, 生产未用); 记录为"同类已知缺陷" |
| `TemporalDecoupler._apply_ar_residual` | **不在本任务** (同上) |
| `decouple_ar` 便捷函数 | 跟随 `TemporalDecoupler`, 不在本任务 |
| Stage 1 / Stage 3 中性化 | 已因果 (实测 0 格), 不改 |
| 指纹路由 | 本次实测未造成顶层差异; 如未来出现, 另立缺陷 |
| AR 模型类/阶数范围 (`max_order=5`) | 不改 |
| `decorrelation_strength` 语义 | 不改 (`(1-s)·series + s·residual`) |
| optimizer 参数搜索空间 | 不改 |

### 5.5 为什么不能只改 `transform`

若 `fit` 仍全样本, 但 `transform` 改成"用 `_results` 的系数 + 实际滞后值"递归预测:

- 阶数与系数仍依赖 `[t+1, T]` → 不满足 N1/N2;
- 截断后 `_results` 会变化 → `ŷ_t` 随 `T` 变化 → 不变式仍失败。

因此 **`fit` 也必须因果化**。这也是本次选择"`fit` 只用前 `warmup_obs` 行"而不是"保留全样本 `_results` 做诊断"的原因: 双模型会让 `transform` 与 `get_summary()`/`get_residual_stats()` 的口径分叉, 且诊断链 (φ→τ→`skip_stage2`) 仍暴露在全样本上。

---

## §6 对设计/实施的约束

### 6.1 必须满足

| # | 约束 |
|---|------|
| C1 | `fit` 只用前 `warmup_obs` 行估计阶数与系数 (N1/N2) |
| C2 | `transform` 只用已实现滞后值做一步预测 (N3) |
| C3 | `transform` 不得因 `_results` 缺失而整列退化为 identity; 未冻结列继续用 warm-up 结果 (N4) |
| C4 | 冷启动 `t < min_order+6` → identity; 已拟合列不新增 NaN |
| C5 | NaN 经滞后自然传播; 不得引入 `ffill` 式的跨期填充 |
| C6 | 不改变 `CompositeDecoupler` 的三阶段顺序与 `strength` 语义 |
| C7 | 输出数值变更 → 版本 + 缓存代际 bump; 历史 Dynamic 结果需重算 |
| C8 | 不触碰 Static / Mixed / Stage 1 / Stage 3 / 指纹路由 |

### 6.2 验收标准草案

1. `test_dynamic_pipeline_is_truncation_invariant` 摘除 `xfail`, **0 格 / 0 NaN / 0**。
2. `test_v2_pipeline_is_truncation_invariant` 摘除 `xfail`, **0 格 / 0 / 0** 且路由一致。
3. 新增单元测试 (建议 `tests/unit/test_ar_decoupler_causality.py`), 覆盖:
   - `fit` 只读前缀 (`warmup_obs` 之后的数据被截掉, `_results` 不变);
   - 多截断点 (10/15/25/30/45/60/80) 的 AR 单步不变式;
   - 一步预测公式与手算对照 (`c_0 + Σ c_i y_{t-i}`);
   - 冷启动 identity、已拟合列 0 新增 NaN;
   - `_results` 缺失的列不回退为整列 identity (N4);
   - `max_order=1` 时阶数固定、`min_order>1` 时早期窗口对齐;
   - `warmup_obs <= min_obs` 的边界行为 (报错或退化, 设计定稿);
   - `strength ∈ {1.0, 0.5}` 的软混合语义。
4. 既有靶向测试全绿 (117 passed + 11 subtests, §5.2)。
5. 性能记录: AR 单步 ≤ 6s (2500×300); Dynamic 全管线 ≤ 45s (2500×300)。
6. 诊断报告 `test_diagnostic_report` 中 Dynamic 行由 FAIL 转 PASS (该报告仅 6 个 step 行 + 3 个 pipeline 行, **无顶层行**; 顶层由摘除 xfail 后的 `test_v2_pipeline_is_truncation_invariant` 直接断言)。

### 6.3 兼容性

- **输出**: AR 输出 ≈95% 格子变化 (`mean_abs` 0.23–0.35, `max_abs` 2.1–4.2); NaN 146 → 0。缓存必须 bump。
- **配置**: 新增 `ARDecoupler.warmup_obs` (默认 120); `PipelineV2Config` / optimizer 不新增字段。
- **API**: `ARDecoupler.__init__` 新增关键字参数 (向后兼容); `transform` 行为变化 (语义修正)。
- **版本**: 建议 v3.3.6; 缓存 `v2.2.4-cache`。

---

## §7 未决问题 (留给设计文档)

> **状态 (2026-11-04)**: 1-3 / 5 已由 §10 给出建议并被 DESIGN v1.2 采纳; 4 采用"复用 `_results`"; 6 登记为同类已知缺陷; 7 仅改代码 docstring。本节保留为决策轨迹。

1. **K 与容差**: 取 `K=120` 并把 `test_coefficients_layout_is_intercept_first` 的 φ 容差从 0.05 放宽到 0.15 (§10.2 最终建议), 还是取 `K=200` 保持容差不变 (warm-up 成本翻倍)? → **见 §10.1 / §10.2**
2. **stride 是否公开**: `warmup_refit_stride=10` 作为私有常量, 还是作为 `ARDecoupler` 的公开参数? → **建议见 §10.1**
3. **`warmup_obs <= min_obs` 的边界处理**: `ValueError` 还是自动钳制为 `min_obs + 10`? → **建议见 §10.1**
4. **`_results` 之外的存储**: 冻结模型是否直接复用 `_results` (推荐, 零额外内存), 还是单独 `_frozen_results` (便于诊断区分)?
5. **PL-07 登记方式**: 直接摘除 xfail (断言整体不变式), 还是拆成"路由因果性"独立测试 (当前无证据表明路由有问题)? → **建议见 §10.3**
6. **`OptimizedARDecoupler` / `TemporalDecoupler`**: 是否在文档中登记为"同类已知缺陷 (非生产路径)", 或在代码 docstring 加注?
7. **`_get_ar_phi_for_diagnosis` docstring**: 改为"拟合窗口内平均"是否需要同步 ADR-030 的附录说明?

---

## §8 参考文献

> 证据等级见文首。B 级条目本次未重读原文段落。

1. Hyndman, R. J., & Athanasopoulos, G. (2021). *Forecasting: Principles and Practice* (3rd ed.). OTexts. §5.10 时序交叉验证 (`tsCV`, expanding window, `ŷ_{t|t-1}`, warm-up). https://otexts.com/fpp3/tscv.html (A: 原文已读)
2. López de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley. Ch. 7 Cross-Validation in Finance (前视/泄漏). (B)
3. Hamilton, J. D. (1994). *Time Series Analysis*. Princeton University Press. Ch. 3–5 (AR(p) 一步预测). (B)
4. Haykin, S. (2002). *Adaptive Filter Theory* (4th ed.). Prentice Hall. (B, 仅作方案 C 的可行性依据)
5. 项目内文档: `docs/analysis/PL06_MIXED_WINSORIZE_LOOKAHEAD_RESEARCH.md`、`PL02_TRANSFORM_LOOKAHEAD_RESEARCH.md`、`PL01_OUTLIER_LOOKAHEAD_RESEARCH.md`; `DECISIONS.md` ADR-027 / ADR-030 / ADR-037 / ADR-038 / ADR-039. (C)
6. Marriott, F. H. C., & Pope, J. A. (1954). Bias in the estimation of autocorrelations. *Biometrika*, 41(3–4), 390–402. https://doi.org/10.1093/biomet/41.3-4.390 (A: Biometrika 元数据 + 本次数值验证)
7. Kendall, M. G. (1954). Note on bias in the estimation of autocorrelation. *Biometrika*, 41(3–4), 403–404. https://doi.org/10.1093/biomet/41.3-4.403 (A: Biometrika 元数据)
8. Varma, S., & Simon, R. (2006). Bias in error estimation when using cross-validation for model selection. *BMC Bioinformatics*, 7, 91. https://doi.org/10.1186/1471-2105-7-91 (A: 原文摘要 + PMC 元数据)
9. Cawley, G. C., & Talbot, N. L. C. (2010). On over-fitting in model selection and subsequent selection bias in performance evaluation. *Journal of Machine Learning Research*, 11, 2079–2107. (A: 摘要 + JMLR 元数据; 页码 B)
10. Bergmeir, C., & Benítez, J. M. (2012). On the use of cross-validation for time series predictor evaluation. *Information Sciences*, 191, 192–213. (A: 摘要; 卷期页码 B)
11. tsibble 官方参考: `stretch_tsibble(.step, .init)` — https://tsibble.tidyverts.org/reference/stretch_tsibble.html (A: 参数原文)
12. sktime 文档: `ExpandingWindowSplitter(initial_window, step_length)` — https://sktime-backup.readthedocs.io/en/stable/api_reference/auto_generated/sktime.split.expandingwindow.ExpandingWindowSplitter.html (B: 搜索摘要, 未逐页)
13. skforecast 官方文档: "Backtesting"（refit / intermittent refit / 成本-精度表）— https://skforecast.org/latest/user_guides/backtesting (A: 已读原文)
14. statsmodels 文档: `ar_select_order` / `AutoReg` 的 `hold_back` — https://www.statsmodels.org/dev/generated/statsmodels.tsa.ar_model.ar_select_order.html (A: 已读原文)
15. scikit-learn 文档: `TimeSeriesSplit` (`gap`) — https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit (A: 参数原文)
16. Hyndman & Athanasopoulos, FPP3 §5.10 原文 — https://otexts.com/fpp3/tscv.html (A: 已读原文)
17. statsmodels `AutoReg.predict(params, dynamic=False)` — https://www.statsmodels.org/dev/generated/statsmodels.tsa.ar_model.AutoReg.predict.html (A: 原文)
18. statsmodels `ARDL/UECMResults.apply(endog, refit=False)` — https://www.statsmodels.org/v0.14.6/generated/statsmodels.tsa.ardl.UECMResults.apply.html (A: 文档摘要)
19. statsmodels "Forecasting in statsmodels"（扩展窗口 one-step 流程）— https://statsmodels.github.io/stable/examples/notebooks/generated/statespace_forecasting.html (A: 原文)
20. numpy `numpy.lib.stride_tricks.sliding_window_view` — https://numpy.org/doc/stable/reference/generated/numpy.lib.stride_tricks.sliding_window_view.html (A: 原文)
21. `arch` `GARCH.simulate(burn=500)` — https://arch.readthedocs.io/en/latest/univariate/generated/generated/arch.univariate.GARCH.simulate.html (A: 原文; 语义限定为模拟初始化)
22. `pmdarima.auto_arima` — https://alkaline-ml.com/pmdarima/modules/generated/pmdarima.arima.auto_arima.html (B: 文档摘要)
23. Bayğın, M., Kutlu Sengul, M., & Tuncer, T. (2026). Model validation in machine learning: A scenario-based guide from hold-out splits to nested group cross-validation. arXiv:2610.01284. (A: 摘要)
24. Yates, L. A., Aandahl, Z., Richards, S., & Brook, B. (2022). Cross validation for model selection: a primer with examples from ecology. arXiv:2203.04552. (B: 摘要)

---

## §9 步骤 2 review 记录

| # | 检查项 | 方法 | 结果 |
|---|--------|------|------|
| R1 | **接口对齐**: 新增 `warmup_obs` 是否破坏现有调用 | 全仓核对 `ARDecoupler(` 调用点 | 现有 5 个参数全部以关键字传入 (`ARDecoupler(max_order=..., min_order=..., criterion=...)`); 追加到参数列表末尾即可, 无位置参数破坏 |
| R2 | **属性契约**: `_results` 是否被外部读取 | grep `_results` | 仅 `_get_ar_phi_for_diagnosis`、`get_residual_stats`、`get_summary` 与一个布局钉子测试读取; 属性名与 `ARModelResult` 字段均不变 |
| R3 | **引用核实**: 每条参考文献的证据等级 | 逐条比对"是否读原文" | 步骤 2 时 §5.10 仅经二手讲义/`tsCV` 文档确认 (B); **步骤 2b 已 WebFetch 原文, 见 §4 / 附录 C, 等级升为 A**; 其余 B 级条目已在 §4 与附录 C 标注 |
| R4 | **数字回源**: 所有实测数字 | 对照附录 A 原始输出 | 全部可追溯; 例外已在附录 C 标注为"推算" |
| R5 | **幻觉排查 #1**: AR 单步基线 | 重新测量 seed=22 | 原 v1.0 误用了另一面板/另一层级的数字 (1653 / 3.7558 / NaN 0 / 2020-04-30); **已改为实测** 1652 / 8.788e-01 / NaN 7 / 2020-05-31 |
| R6 | **幻觉排查 #2**: 方案 B 的 `mean_ar1` | 回看探针 4 的 C 节 | 0.0979 属于 V2 (warm-up+冻结) 而非 V1 (纯冻结); **已删除该归属**, 仅保留性能 0.25s |
| R7 | **幻觉排查 #3**: 计时口径 | 对照探针 6/8 | v1.0 只写 2.11s; **已改为 2.11–5.76s 区间**, 并说明 42.50s 对应保守端 |
| R8 | **遗漏的必要条件**: `_results` 门控 | 回看探针 7 的 t=10/15 失败 | v1.0 仅出现在 §0 摘要, **已补 §3.8** 并修正 §2.2 N4 的交叉引用 |
| R9 | **未验证项登记** | — | 见附录 C (NaN 冷启动 `nan_ratio`、`mean_ar1` 起点敏感性、生产面板规模) |

**结论**: 步骤 2 通过 (v1.1); 追加 §10 补充调研后为 **v1.2**, 可作为设计文档的唯一学术依据源。

---

## §10 补充调研: 三项待定决策的外部锚点 (步骤 2b)

**检索说明**: 2026-11-04 追加调研。StackExchange MCP 仍返回 `quota_remaining: -1` (配额耗尽), Semantic Scholar 返回空; 本节以 **FPP3 原文**、**官方库文档** (statsmodels / sktime / skforecast / scikit-learn / tsibble)、**JMLR/Biometrika/Bioinformatics 元数据**为主, 并补两组本地数值实验。证据等级沿用文首定义。

### 10.1 决策 1: warm-up 长度 `K` 与 refit stride

| # | 锚点 | 原文/摘要要点 | 对本项目的映射 | 等级 |
|---|------|--------------|----------------|------|
| E1 | Hyndman & Athanasopoulos, FPP3 §5.10 (已读原文) | "the training set consists only of observations that occurred **prior** to the observation that forms the test set. Thus, no future observations can be used in constructing the forecast. Since it is not possible to obtain a reliable forecast based on a small training set, **the earliest observations are not considered as test sets**" | (a) 因果定义 = 只用先验观测; (b) **warm-up 是标准组成部分**, 不是本项目发明的补丁 | **A** |
| E2 | tsibble `stretch_tsibble(.init, .step)` 官方参考 | `.init` = "a positive integer for an **initial window size**"; `.step` = "a positive integer for **incremental step**" | 直接对应 `warmup_obs=K` 与 refit stride; FPP3 示例 `.init=3, .step=1` | **A** |
| E3 | sktime `ExpandingWindowSplitter` 文档 | `initial_window` = "Window length of **initial training fold**" (默认 10); `step_length` = "**Step length between windows**" (默认 1) | 同上: 初始训练窗 + 窗口步长 | **B** (文档摘要, 未逐页) |
| E4 | skforecast "Backtesting" 官方文档 | `refit=False`: "the model is **trained only once** and used sequentially ... this approach ... is much faster"; `refit=n`: "**retrained every n iterations** ... usually achieves a good balance between the computational cost of retraining and avoiding model degradation" | `t≥K` 冻结 = `refit=False`; warm-up 内每 stride 重估 = `refit=n` | **A** |
| E5 | skforecast 同页实测表 | `False`: 1.4s / 262.5; `30`: 4.0s / 263.4; `14`: 6.3s / 262.5; `7`: 11.1s / 261.4; `True`: **69.1s / 258.3** | 逐点重估成本 **49×**, 误差仅改善 **1.6%**; 且 `refit=30` 反而差于 `False` (差异在噪声级) → 支持"冻结 + 间歇重估" | **A** |
| E6 | Box-Jenkins / Chatfield 经验下限 | ARIMA 类模型建议至少 **50** 个等间隔观测 (Box, Jenkins & Reinsel 1994; Chatfield 1996) | K=120 满足; K=60 仅略高于下限; `min_obs=20` 明显不足 | **B** |
| E7 | statsmodels `ar_select_order` / `AutoReg` 的 `hold_back` | "Set to a non-zero value to **produce comparable models** with different lag length ... both models are estimated using observations 3,…,nobs"; `hold_back ≥ maxlag` | 阶数比较应使用同一样本; 当前 `_fit_ar` 不满足 → 见 §10.4 | **A** |

**本地质量曲线** (K sweep; `T=500, N=30, φ=0.7`, 统计起点第 60 行):

| K | `mean_ar1` | 相对 raw (0.7025) 的残留比例 |
|---|-----------|------------------------------|
| 40 | 0.1255 | 17.9% |
| 60 | 0.0998 | 14.2% |
| 80 | 0.0772 | 11.0% |
| 100 | 0.0359 | 5.1% |
| **120** | **0.0302** | **4.3%** |
| 160 | 0.0303 | 4.3% |
| 200 | 0.0236 | 3.4% |
| 300 | 0.0228 | 3.2% |
| current (全样本) | 0.0029 | 0.4% (样本内过拟合, 不是 OOS) |

**建议**:

1. **K=120**: 120 是质量曲线的拐点 (100→120 有明显改善 0.0359→0.0302, 120→160 完全持平 0.0302→0.0303); K>200 只带来 0.007 的边际收益, 却使 warm-up 重估次数增加约 80%。
2. **`warmup_obs` 公开, `warmup_refit_stride` 私有**: FPP3/tsibble/sktime/skforecast 把 `init/window` 与 `step/refit` 作为**评估框架**参数, 使用者需要为每个数据集选择; 本项目是**数据变换管线**, `warmup_obs` 决定"前多少行不做解耦"这一可解释语义, 值得公开; 而 stride 只是"用多少行更新一次系数"的实现细节, 对使用者无意义, 公开只会扩大配置面 (与 ADR-027 的收敛方向冲突)。因此 `_WARMUP_REFIT_STRIDE = 10` 作为模块级私有常量。
3. **`warmup_obs <= min_obs` → `ValueError`**: 静默钳制会让实际行为与调用者传入值不符; 报错信息给出 `warmup_obs >= min_obs + 10` 的建议。
4. **不选 K=200**: 质量仅再降 0.0066, warm-up 成本 +80%, 且**不能解决 §10.2 的容差问题** (K=200 时 `P(|Δφ|<0.05)` 仍只有 64.5%)。

### 10.2 决策 2: `test_coefficients_layout_is_intercept_first` 的 φ 容差

**解析锚点**:

- AR(1) 的 OLS 估计存在 `T⁻¹` 偏差: `E[φ̂] - φ ≈ -(1+3φ)/n` (Marriott & Pope, 1954; Kendall, 1954)。**A** (Biometrika 元数据 + 本次数值验证)
- 平稳 AR(1) 的 OLS 渐近标准差 `sd(φ̂) ≈ sqrt((1-φ²)/n)` (教科书通行结论, Hamilton 1994)。**B**
- 代入 `n=120, φ=0.7`: 偏差 **-0.0258**, `sd` **0.0652**。

**数值验证** (2000 次重复, 与测试同生成式 `y_t = 30 + 0.7·y_{t-1} + N(0, 0.1²)`, 含 30 期 burn-in):

| n | mean(φ̂) | sd | bias | `P(\|Δ\|<0.05)` | `P(<0.10)` | `P(<0.15)` |
|---|---------|----|------|-----------------|-----------|-----------|
| 40 | 0.6211 | 0.1326 | -0.0789 | 31.25% | 55.90% | 72.55% |
| 60 | 0.6476 | 0.1021 | -0.0524 | 38.20% | 65.35% | 82.80% |
| 80 | 0.6600 | 0.0872 | -0.0400 | 44.05% | 74.30% | 88.50% |
| 100 | 0.6688 | 0.0757 | -0.0312 | 48.75% | 78.95% | 92.75% |
| **120** | **0.6717** | **0.0699** | **-0.0283** | **50.30%** | **83.00%** | **94.75%** |
| 160 | 0.6817 | 0.0602 | -0.0183 | 60.00% | 89.30% | 97.40% |
| 200 | 0.6828 | 0.0544 | -0.0172 | 64.45% | 91.75% | 98.60% |

**结论**: 在 n=120 上, 0.05 容差的覆盖率只有 **50.3%** —— 与实测 `|φ̂-0.7|=0.0479` 的"恰好通过"完全吻合, 是**确定性数据上的抛硬币**。任何前缀拟合都无法稳定满足 0.05。

**建议**: 容差放宽到 **0.15** (n=120 覆盖率 94.8%, 约 2.1σ), 并在测试注释写明"前缀 OLS 的 `T⁻¹` 偏差 + 抽样误差"。该断言的本意是**布局钉子** (区分 `[intercept, φ_1]` 与 `[φ_1, intercept]`), φ 的精度不是它的目的; 放宽容差不削弱其意图。可选加固: 追加 `0.5 < φ̂ < 0.9` 的区间断言, 保证"仍是 AR(1) 量级"。

> 注: 这与是否选 K=200 无关 —— 即使 K=200, 0.05 容差也只有 64.5% 覆盖率。**放宽容差是必要条件, 不是 K 的替代品**。

### 10.3 决策 3: PL-07 的登记方式

| # | 锚点 | 要点 | 对本项目的映射 | 等级 |
|---|------|------|----------------|------|
| E8 | Varma & Simon (2006), *BMC Bioinformatics* 7:91 (doi:10.1186/1471-2105-7-91) | "using CV to compute an error estimate for a classifier that has itself been tuned using CV gives a significantly biased estimate of the true error"; "**all steps of the algorithm, including classifier parameter tuning, be repeated in each CV loop**" | 指纹路由 = 在数据上做**模型选择**; 用全样本指纹决定路由, 前 t 期的路由可能依赖未来。**路由必须在前缀内重做** | **A** (原文摘要 + PMC 元数据) |
| E9 | Cawley & Talbot (2010), *JMLR* 11 | 模型选择层面的过拟合会产生后续评估的选择偏差, 量级可与算法差异相比 | 路由/分类是"第二层推断", 必须纳入时间切分 | **A** (摘要 + JMLR 元数据) |
| E10 | Bergmeir & Benítez (2012), *Information Sciences* | 时序评估应使用 blocked CV / rolling origin, 以最后一段评估 | 支持以"截断不变式"作为路由闸门 | **A** (摘要) |
| E11 | scikit-learn `TimeSeriesSplit(gap)` 文档 | "train/test indices to split time-ordered data ..."; `gap` = "samples to exclude from the end of each train set before the test set" | 选择/预处理都必须在 train 侧完成 | **A** |
| E12 | López de Prado (2018) Ch. 7 | purging / embargo | 同上 | **B** |
| E13 | Bayğın, Kutlu Sengul & Tuncer (2026), *Model validation in machine learning* (arXiv:2610.01284) | "**Every data-dependent operation must also exclude the observations used for performance estimation**" (每个数据依赖的操作都必须排除用于评估的观测) | 直接覆盖"路由/特征选择/预处理"等所有数据依赖步骤; 本项目的截断不变式就是这一原则的操作化 | **A** (摘要, 经 `semantic_scholar_search` 取得) |
| E14 | Yates et al. (2022), *Cross validation for model selection: a primer* (arXiv:2203.04552) | CV 用于模型选择时需考虑 score 估计不确定性; 建议使用校正的 one-SE 规则 | 路由选择本身应有不确定性意识, 不能只看单次最优 | **B** (摘要) |

**建议**: 不整体删除该测试, 而是**拆分**:

1. `test_v2_pipeline_is_truncation_invariant` 摘除 xfail, 只断言**输出不变式** (当前实测 0/0/0)。
2. `assert routes_full == routes_trunc` 保留为**独立断言**, docstring 说明它是"模型选择因果性"闸门; 但单种子通过不等于普遍成立 → **参数化至少 3 个种子** (如 31/22/7), 全部通过则不登记缺陷; 任一失败则重新登记为 PL-07 (路由选择前视)。
3. 这样既不掩盖真实风险 (E8–E12 说明路由确实是一个独立泄漏向量), 也不会因单数据集通过就删掉守卫。

### 10.4 附带发现: AIC 跨阶数不可比 (不在本任务)

`_fit_ar` 对每个阶数使用 `y[order:]` 作为因变量, 使各阶数的 `n_obs = n - order` 不同; AIC 的似然项因此建立在**不同样本**上。statsmodels 明确要求 `hold_back ≥ maxlag` 才能"produce comparable models with different lag length" (E7)。当前实现违反这一条件。

- **性质**: 方法学瑕疵 (模型选择准则不可比), 与 PL-05 的"前视"是不同缺陷类别; 对 `n=120`、阶数 1–5, `Δn = 4` (约 3%), 影响通常小于前视。
- **处置**: **不纳入 PL-05** (会进一步改变阶数选择与存量输出, 扩大范围); 建议在设计文档登记为独立缺陷候选 (暂记 `PL-08-candidate`), 由用户决定是否另立任务。
- **若未来修复**: 需在 `_fit_ar` 中统一 `hold_back = max_order`, 并重新评估阶数分布与输出变化。

### 10.5 三项决策的建议汇总

| 决策 | 建议 | 外部锚点 | 内部依据 |
|------|------|---------|---------|
| warm-up K | **120** | E1 (warm-up 标准), E2/E3 (init 窗口), E6 (≥50) | K sweep 拐点 120; 既有 φ 断言全绿 |
| refit stride | **10, 私有常量** | E2/E3 (step), E4/E5 (间歇重估成本-精度) | 2.11–5.76s vs 8.4–19.1s |
| K 的可见性 | **`warmup_obs` 公开; stride 私有** | E4 (框架参数 vs 实现细节) | 语义可解释性 / 配置面收敛 (ADR-027) |
| K 的边界 | **`warmup_obs <= min_obs` 抛 `ValueError`** | — | 静默钳制会造成语义不符 |
| φ 容差 | **0.15** (附覆盖率注释) | Marriott-Pope/Kendall 偏差 + `sqrt((1-φ²)/n)` | 2000 次模拟: 0.05 仅 50.3% |
| PL-07 | **拆为"输出不变式"(摘 xfail) + "路由断言"(3 seeds)** | E8–E12 | 单种子通过不足以证明 |

---

## §11 MCP 复测与实现调研 (步骤 2c)

### 11.1 MCP 工具可用性复测 (2026-11-04)

| 工具 | 本次结果 | 结论 |
|------|---------|------|
| `mcp_stackexchange_search_questions` ×3 | 全部 `quota_remaining = -1` | 配额仍未恢复; 不再重试 |
| `mcp_paper-search_search_semantic` | 返回 `[]` | 不可用 |
| `mcp_paper-search_search_arxiv` | 返回不相关结果 | 不可用 |
| `mcp_english-search_search_web` / `_academic` | HTTP 404 | 不可用 |
| **`mcp_scholar-mirror_check_mirrors`** | **可用**: 9 个镜像中 5 个在线 (`xs.gupiaoq.com` 1050ms, `xs.typicalgame.com` 1404ms, `sc.panda985.com` 1511ms, `so.cljtscd.com` 3676ms, `www.typicalgame.com` 4207ms) | 镜像层正常 |
| **`mcp_scholar-mirror_search_papers`** | **工具自身故障**: `type object 'URL' has no attribute 'quote'` (两次不同 query 均复现) | 非配额问题; 不可用 |
| **`mcp_research-tools_arxiv_search`** | **工具自身故障**: `'Search' object has no attribute 'results'` | 不可用 |
| **`mcp_research-tools_semantic_scholar_search`** | **可用** (首次串行检索返回 8 条, 含 Varma & Simon 全文摘要); 并行 3 次后触发 **429** | 需**串行 + 退避**; 本次已获得所需条目 |
| `WebSearch` / `WebFetch` | 可用 | 主力来源 |

> 说明: 用户提到的 "donsetch MCP" 在可用工具列表中不存在 (可能是拼写差异)。本次实际复测了上述全部 MCP 检索工具, 并新增 `semantic_scholar_search` 的成功结果。

### 11.2 实现层锚点

| # | 锚点 | 原文要点 | 对本项目实现的映射 | 等级 |
|---|------|---------|-------------------|------|
| I1 | statsmodels `AutoReg.predict(params, dynamic=False)` 文档 | `params` = "The fitted model parameters"; `dynamic=False` 时 "**true endogenous values will be used for prediction**" | 一步预测必须用**真实滞后值**, 而非 `fitted_values`; 参数可显式传入 → 冻结模型的标准用法 | **A** (原文) |
| I2 | statsmodels `ARDL/UECMResults.apply(endog, refit=False)` 文档 | "Apply the fitted parameters to **new data** unrelated to the original data ... `refit=False`" | `t ≥ K` 冻结分支的标准语义: 只应用参数, 不重估 | **A** (文档摘要) |
| I3 | statsmodels "Forecasting in statsmodels" 示例 | "Fit model parameters on a training sample; produce h-step-ahead forecasts ... **Expand the sample to include the next observation, and repeat**" | 扩展窗口 one-step 评估的标准流程; 与 §10.1 E1 一致 | **A** (原文) |
| I4 | statsmodels `ar_select_order(missing=...)` 文档 | `missing ∈ {'none','drop','raise'}`; `hold_back ≥ maxlag` | 逐列 `dropna` 后拟合 (与现实现一致); `hold_back` 见 §10.4 | **A** (原文) |
| I5 | numpy `sliding_window_view` 文档 | "a sliding window approach with input size N and window size W will scale as **O(N·W)** ... often **not** optimal; a special algorithm can achieve O(N)" | `p ≤ 5` 时直接用 `pred[i:] += c_i · vals[:n-i]` (`O(T·p)`) 优于构造完整滞后矩阵 | **A** (原文) |
| I6 | `arch` `GARCH.simulate(burn=500)` 文档 | `burn` = "Number of additional observations to generate when **initializing the simulation**" | 主流计量库把 burn-in 作为显式参数 (量级 500); **语义不同**: 模拟初始化 ≠ 估计预热, 仅作"warm-up 是常规概念"的旁证 | **A** (原文, 语义已限定) |
| I7 | `pmdarima.auto_arima(max_p=5, max_order=5, out_of_sample_size=0)` | 阶数搜索上限默认 5; `out_of_sample_size` 可选做 OOS 评分 | 项目 `max_order=5` 与主流默认一致, 不是特例 | **B** (文档摘要) |
| I8 | skforecast `refit=n` / `initial_train_size` | 见 §10.1 E4/E5 | 实现形态与本方案同构 | **A** |

### 11.3 实现建议 (可直接进设计文档)

**`fit`**:

```python
warm = min(self.warmup_obs, len(data))
self._results = self._selector.batch_fit(data.iloc[:warm])
```

复杂度 `O(N · K · p²)` (与当前 `O(N · T · p²)` 相比更小, 因为 K=120 << T)。

**`transform`** (逐列, 不构造滞后矩阵):

```python
vals = data[col].to_numpy(float)
res = vals.copy()                       # identity 冷启动
# warm-up: [max(min_order+6, 2), min(warmup_obs, n))
#   每 stride 行用 vals[:t].dropna() 重估 (t<min_obs 用 _fit_ar(min_order))
#   yhat = c0 + Σ c_i·vals[t-1-i]
# 冻结: t >= warmup_obs
pred = np.full(n, c0)
for i in range(1, p + 1):
    pred[i:] += c[i] * vals[: n - i]
res[warmup_obs:] = vals[warmup_obs:] - pred[warmup_obs:]
```

- 复杂度: `O(N · (T·p + (K/stride)·p²))`; 不引入 `O(T²)` 或 `O(N²)`。
- NaN: 滞后值含 NaN → `pred` 自然为 NaN → 该行输出 NaN; **不使用 `ffill`** (I1 语义)。
- 列过滤: 遍历 `data.columns`; 冻结模型用 `self._results.get(col)` (N4 / §3.8)。
- 预测公式抽成 `_predict_one_step(vals, t, coef, p)`, 便于手算对照单测 (I1)。

**测试锚点**:

| 测试 | 锚点 |
|------|------|
| 一步预测与手算对照 | I1 (`dynamic=False` = 用真实滞后值) |
| 冻结参数应用到 `t ≥ K` | I2 (`apply(..., refit=False)`) |
| 多截断点不变式 | I3 (扩展窗口 one-step 流程) |
| NaN 传播 (无 ffill) | I4 (`missing='drop'` 只在拟合时丢 NaN) |

### 11.4 实现调研结论

1. **"显式传入冻结参数做预测"** 与 **"每 n 次重训"** 在 statsmodels / skforecast / pmdarima 中都是公开 API 的标准配置 (I1/I2/I8), 本方案不是自创形态。
2. **"用真实滞后值做一步预测"** 是 statsmodels `predict(dynamic=False)` 的默认语义 (I1), 直接否定了当前 `fitted_values` 做法。
3. **"两段 warm-up (低阶固定 → 全阶 AIC)"** 没有外部直接对应物, 属实现细节; 其必要性由本地测试 `test_information_loss_signal_lost` 证明 (§3.7), 不构成风险。
4. **性能路径** 用"按阶数累加移位数组"而非滞后矩阵/滑动视图 (I5), 与探针实现一致; 无需引入 numba / Cython。

---

## 附录 A: 探针脚本与原始输出

### A.1 复现方式

- 解释器: `C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe`
- 工作目录: `F:\Coding\factor_pipeline`; `factor_pipeline` 为可导入包
- 探针脚本存放于 `%TEMP%` (不在仓库内): `pl05_probe.py` … `pl05_probe10.py`, `pl05_patch.py`
- 面板约定: index=日期 (`freq='ME'`), columns=`S000..`; 截断 `frac=0.6` → `t=60`

### A.2 原始输出 (摘录)

```
=== PL-05 探针 1 (根因定位, 与 seed=22 同族面板) ===
baseline: n_diff=1653 n_nan=8 max_abs=8.045314e-01 rows_bad=57 first=2020-04-30 total_cells=1800
stage1_only: n_diff=0 n_nan=0 max_abs=0.000000e+00
AR orders: n=30 min=4 max=5 mean=4.767 dist={5:23, 4:7}
current AR output NaN: full=143 trunc=143
candidate_B(K=20,identity): n_diff=0 n_nan=0; NaN full=0; vs current diff_cells=2857, max=2.6914
candidate_A(expanding,min_obs=20): n_diff=0 n_nan=0; runtime(2 runs,100x30)=2.15s
ARDecoupler.fit_transform 2500x300: 0.52s

=== PL-05 补充 (AR 单步, seed=22 ar_low, t=60) ===
baseline AR: (1652, 7, 0.8788, rows=56, first=2020-05-31), nan_full=146
patched  AR: (0, 0, 0.0, rows=0, first=None), nan_full=0
AR order dist (seed=22 全样本): {4: 4, 5: 26}, mean=4.867

=== PL-05 探针 4 (候选变体; panel(100,30) seed=7 iid, 截断 t=60) ===
A. 截断不变式 T=100/N=30
current   t=10:154/0/8.0e-01  t=25:602/2/1.7e+00  t=30:752/2/1.8e+00  t=45:1202/2/1.6e+00  t=60:1652/2/9.4e-01  t=80:2254/0/5.9e-01
V1 frozen(K=60)            t=10..80: 0/0/0
V2 warmup+freeze(K=60)     t=10..80: 0/0/0
V3 warmup_fixed+freeze     t=10..80: 0/0/0
B. 性能 2500x300
current 0.52s | V1 0.25s | V2 8.37s | V3 7.60s
C. 质量 AR(1) phi=0.7 T=500/N=30
raw 0.7023 | current -0.0001 | V2 0.0979 | V3 0.0975
D. 旧测试兼容
  用例1 full-sample phi=0.7457 (|d|=0.0457 PASS); first-K=60 phi=0.8382 (|d|=0.1382 FAIL)
  用例2 full-sample mean_phi=0.6896 (|d|=0.0104 PASS); first-K=60 mean_phi=0.5835 (|d|=0.1165 FAIL)

=== PL-05 探针 6 (stride 变体) ===
A. 不变式: K=60/stride=1, K=100/10, K=120/10, K=120/20 全部 0/0 (t=10..80)
B. 性能 2500x300: K=60/stride=1 19.06s | K=100/10 4.80s | K=120/10 5.76s | K=120/20 3.21s
C. 质量: raw 0.7023 | K=60/1 0.0979 | K=100/10 0.0538 | K=120/10 0.0482 | K=120/20 0.0579

=== PL-05 探针 7/10 (端到端, 两段 warm-up) ===
A. 基线
  Dynamic seed=22 ar_low t=60: (1653, 8, 0.8045313632310727)
  顶层    seed=31 skewed t=60: (1650, 0, 1.8397305724759783), routes_equal=True
B. 修复后
  Dynamic seed=22 ar_low t=60: (0, 0, 0.0)
  顶层    seed=31 skewed t=60: (0, 0, 0.0), routes_equal=True
D. AR 单步多截断点: t=10/15/25/30/45/60/80 全部 (0, 0, 0.0)
E. NaN: ar_low 0/3000; ar70 0/3000
F. 质量: raw mean_ar1=+0.7003; causal output +0.0647; mean_abs=0.8320

=== PL-05 探针 8 (稳定计时) ===
修复前 AR 2500x300: min=0.48s max=0.49s (3 次)
修复后 AR 2500x300: min=2.11s max=5.36s (3 次, ×4.4)
冻结阶数: 前120行 mean=4.850 dist={3:7,4:31,5:262}; 全样本 mean=4.937 dist={2:1,4:16,5:283}; 一致 89.00%
phi: 前120行 -0.0101 vs 全样本 -0.0005

=== PL-05 探针 9 (输出偏移) ===
[iid]   AR      cells=2854/3000 max_abs=3.7255 mean_abs=0.2626 rows_changed=96  NaN 146→0
[iid]   Dynamic cells=2855/3000 max_abs=2.1038 mean_abs=0.2287 rows_changed=96  NaN 145→0
[ar70]  AR      cells=2851/3000 max_abs=4.1873 mean_abs=0.3486 rows_changed=96  NaN 149→0
[ar70]  Dynamic cells=2852/3000 max_abs=2.7665 mean_abs=0.2829 rows_changed=96  NaN 148→0

=== 管线总耗时 (2500x300) ===
DynamicPipeline 修复前: 33.19s
DynamicPipeline 修复后: 42.50s (+28%)

=== PL-05 探针 11 (步骤 2b) ===
A. AR(1) 前缀 OLS 的 phi 偏差与容差覆盖率 (2000 次, phi=0.7)
n= 40: mean=0.6211 sd=0.1326 bias=-0.0789 | P(|d|<0.05)=31.25% P(<0.10)=55.90% P(<0.15)=72.55%
n= 60: mean=0.6476 sd=0.1021 bias=-0.0524 | P(|d|<0.05)=38.20% P(<0.10)=65.35% P(<0.15)=82.80%
n= 80: mean=0.6600 sd=0.0872 bias=-0.0400 | P(|d|<0.05)=44.05% P(<0.10)=74.30% P(<0.15)=88.50%
n=100: mean=0.6688 sd=0.0757 bias=-0.0312 | P(|d|<0.05)=48.75% P(<0.10)=78.95% P(<0.15)=92.75%
n=120: mean=0.6717 sd=0.0699 bias=-0.0283 | P(|d|<0.05)=50.30% P(<0.10)=83.00% P(<0.15)=94.75%
n=160: mean=0.6817 sd=0.0602 bias=-0.0183 | P(|d|<0.05)=60.00% P(<0.10)=89.30% P(<0.15)=97.40%
n=200: mean=0.6828 sd=0.0544 bias=-0.0172 | P(|d|<0.05)=64.45% P(<0.10)=91.75% P(<0.15)=98.60%

B. warm-up 长度 K 与输出质量 (AR(1) phi=0.7, T=500, N=30)
raw: mean_ar1=+0.7025
K= 40: mean_ar1=+0.1255  mean_abs=0.9089
K= 60: mean_ar1=+0.0998  mean_abs=0.8666
K= 80: mean_ar1=+0.0772  mean_abs=0.8462
K=100: mean_ar1=+0.0359  mean_abs=0.8308
K=120: mean_ar1=+0.0302  mean_abs=0.8244
K=160: mean_ar1=+0.0303  mean_abs=0.8204
K=200: mean_ar1=+0.0236  mean_abs=0.8167
K=300: mean_ar1=+0.0228  mean_abs=0.8138
current(全样本): mean_ar1=+0.0029

=== 外部锚点原文 (已读) ===
FPP3 §5.10: "the training set consists only of observations that occurred prior to the
  observation that forms the test set. Thus, no future observations can be used in
  constructing the forecast. Since it is not possible to obtain a reliable forecast based
  on a small training set, the earliest observations are not considered as test sets."
skforecast: "Backtesting without refit ... the model is trained only once ... much faster"
  "The model is retrained every n iterations ... usually achieves a good balance between
  the computational cost of retraining and avoiding model degradation."
statsmodels `ar_select_order`: "hold_back ... Set to a non-zero value to produce comparable
  models with different lag length ... hold_back must be >= the maximum lag in the model."
```

> 计时为单机单进程, 存在 2–5s 级波动 (探针 8 的 2.11/5.36s 极差即为例证); 表中数值用于量级判断, 不作为跨机器基准。

---

## 附录 B: 检索记录与失败说明

| 时间 | 工具 | 查询/用途 | 结果 |
|------|------|-----------|------|
| 2026-11-04 | `mcp_paper-search_search_semantic` | "causal AR model walk-forward one-step prediction look-ahead" | 返回空 |
| 2026-11-04 | `mcp_english-search_search_web` | "expanding window AR one step ahead forecast bias" | HTTP 404 |
| 2026-11-04 | `mcp_paper-search_search_arxiv` | "AR order selection look-ahead bias" | 返回不相关结果 (电机故障诊断) |
| 2026-11-04 | `WebSearch` | "walk-forward expanding window one-step-ahead look-ahead bias" | 成功 (Hyndman `tsCV`, RLS, look-ahead bias 概览) |
| 2026-11-04 | `WebSearch` | "Hyndman Athanasopoulos 5.10 time series cross-validation" | 成功 (确认 §5.10 为时序交叉验证, `tsCV` 默认 expanding) |
| 2026-11-04 (步骤 2b) | `mcp_stackexchange_search_questions` ×3 | AR 最小样本 / walk-forward 模型选择 / expanding 重估频率 | 全部失败: `quota_remaining = -1` |
| 2026-11-04 (步骤 2b) | `mcp_paper-search_search_semantic` | "nested cross-validation time series model selection leakage" | 返回 `[]` |
| 2026-11-04 (步骤 2b) | `WebSearch` ×5 | Marriott-Pope/Kendall 偏差、Varma-Simon、Cawley-Talbot、Bergmeir-Benítez、statsmodels `hold_back`、Box-Jenkins 最小样本 | 成功 (元数据与摘要) |
| 2026-11-04 (步骤 2b) | `WebFetch` ×4 | FPP3 §5.10、statsmodels `ar_select_order`、skforecast Backtesting、Wikipedia AR | 成功 (前三个已读原文; Wikipedia 未给出方差公式, 未作锚点) |
| 2026-11-04 (步骤 2b) | `WebSearch` ×2 | sktime `ExpandingWindowSplitter`、tsibble `stretch_tsibble` | 成功 (官方文档参数片段) |
| 2026-11-04 (步骤 2c) | `mcp_scholar-mirror_check_mirrors` | 镜像可用性 | 成功: 9 个中 5 个在线 |
| 2026-11-04 (步骤 2c) | `mcp_scholar-mirror_search_papers` ×2 | "autoregressive model look-ahead bias walk-forward one-step prediction" / "autoregressive model look ahead bias walk forward" | **工具 bug**: `type object 'URL' has no attribute 'quote'` (两次均复现) |
| 2026-11-04 (步骤 2c) | `mcp_research-tools_arxiv_search` | "walk-forward validation hyperparameter selection leakage time series" | **工具 bug**: `'Search' object has no attribute 'results'` |
| 2026-11-04 (步骤 2c) | **`mcp_research-tools_semantic_scholar_search`** ×1 (串行) | "bias in error estimation cross-validation model selection nested" | **成功**: 8 条, 含 Varma & Simon 全文摘要、Bayğın (2026)、Yates (2022)、Guan (2018) |
| 2026-11-04 (步骤 2c) | `mcp_research-tools_semantic_scholar_search` ×3 (并行) | AR 阶数有限样本 / warm-up / expanding 成本 | **全部 429** (限流); 需串行 + 退避 |
| 2026-11-04 (步骤 2c) | `mcp_english-search_search_web` / `_academic` | statsmodels 冻结参数 / 最小样本 | HTTP 404 |
| 2026-11-04 (步骤 2c) | `WebSearch` ×2 / `WebFetch` ×3 | statsmodels `predict`/`apply`、numpy `sliding_window_view`、pmdarima `auto_arima`、`arch` `burn` | 成功 (官方文档原文) |

**处理**: StackExchange 配额耗尽后不再重试; `mcp_english-search` 两次 404, 不再调用; `mcp_scholar-mirror` 检索层有代码 bug, 仅用其镜像检测; 论文检索改用 `mcp_research-tools_semantic_scholar_search` (串行) + WebSearch/WebFetch 官方文档。所有引用逐条标注等级, 未读原文者标 B。

---

## 附录 C: 未验证/不确定事项

| 项 | 状态 | 处置 |
|----|------|------|
| Hyndman & Athanasopoulos §5.10 原文逐字表述 | **已核验** (2026-11-04 WebFetch 读取原文) | 升为 **A**, 可直接引用 §5.10 原句 |
| López de Prado Ch. 7 的章节号 | 项目 PL-01/PL-02 沿用 "Ch. 7"; 本次未重读 | 标注 B; 设计文档沿用既有引用口径 |
| `T=60` 下 NaN 冷启动的 `nan_ratio` | **推算** (20/60 = 33.3% > 0.3), 未实跑 | 设计文档若考虑 NaN 冷启动, 必须实跑该断言 |
| `mean_ar1` 的统计起点敏感性 | 起点 6 得 0.0647, 起点 20 得 0.0482 | 报告区间, 不声称单值 |
| 生产面板的典型 T/N | 未统计 | 性能结论按 2500×300 合成面板陈述 |
| `OptimizedARDecoupler` 的完整影响面 | 仅确认非生产路径 | 实施前全仓 grep 复核一次 |
| sktime `ExpandingWindowSplitter` 参数原文 | 仅凭搜索摘要, 未逐页打开 | 标注 B; 设计文档引用时降级为"同类库亦有初始窗口 + 步长参数" |
| Cawley & Talbot (2010) 页码 2079–2107 | JMLR 卷号已核 (vol 11, no 70), 页码凭记忆 | 引用时标注页码为 B |
| Bergmeir & Benítez (2012) 卷期页码 | 仅核到期刊名与标题 | 引用时标注 B |
| K 质量曲线 (探针 11) 为单面板单种子 | `T=500, N=30, seed=42` | 只用于"拐点"判断, 不声称总体最优 |
| φ 覆盖率模拟 (探针 11) 假设正态新息与固定 φ | 与既有测试同生成式 | 仅用于论证容差量级, 不外推到非平稳因子 |
| AIC `hold_back` 的实际影响量级 | 未测量阶数变化 | 若用户决定登记 PL-08-candidate, 需先量化 |
| `mcp_scholar-mirror_search_papers` 故障 | 工具代码 bug (`URL.quote`), 与配额无关 | 本任务不再使用; 建议反馈工具维护方 |
| `mcp_research-tools_arxiv_search` 故障 | `'Search'.results` 缺失 | 同上 |
| Semantic Scholar 限流 | 串行 1 次成功, 并行 3 次全部 429 | 后续检索必须串行 + 退避 (≥1s) |
| `pmdarima` 的 `min_size` 行为 | 官方页未给出; 未验证 | 不引用 |
| `arch` `burn` 的语义 | 属**模拟初始化**, 非估计预热 | 仅作"warm-up 概念普遍存在"的旁证, 不当作 K 的依据 |
| Bayğın et al. (2026) 为预印本 | arXiv:2610.01284, 未见同行评审 | 作为"当前最佳实践"引用, 不当作定论 |
