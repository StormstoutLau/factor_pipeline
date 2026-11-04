# PL-05 Dynamic AR 前视缺陷 — 设计文档

**版本**: v1.2 (步骤 8 一致性 review 修订; v1.1 为步骤 4 review 修复后, v1.0 为 2026-11-04 初稿)
**日期**: 2026-11-04
**缺陷编号**: DEFECT-PL-05
**上游调研**: [PL05_DYNAMIC_AR_LOOKAHEAD_RESEARCH.md](PL05_DYNAMIC_AR_LOOKAHEAD_RESEARCH.md) v1.4
**关联决策**: ADR-030 (诊断契约) / ADR-027 (固定方法) / 新增 **ADR-040**
**目标版本**: **v3.3.6**; 缓存 **`v2.2.4-cache`**
**方案状态**: **B'' (两段 warm-up + stride + K 冻结) 已实施 (v3.3.6, 2026-11-04)**; A / B / B' / C 记录为备选 (不实施)
**实施与实测**: [EXECUTION_V3.3.6_PL05_DYNAMIC_AR_CAUSALITY.md](../EXECUTION_V3.3.6_PL05_DYNAMIC_AR_CAUSALITY.md) (v1.3, §7.2)
**行号说明**: 行号仅作导航, 以类名/函数名/测试名为准

---

## §0 设计摘要

| # | 决策 | 状态 |
|---|------|------|
| D1 | `ARDecoupler.fit` 只用**前 `warmup_obs` 行**估计阶数与系数 | **锁定** |
| D2 | `transform` 改为**因果一步预测**: 冷启动 identity → 早期固定低阶 → 全阶逐步重估 → `t ≥ K` 冻结 | **锁定** |
| D3 | 移除 `transform` 对 `_results` 的**存在性门控** (遍历 `data.columns`, 冻结用 `_results.get(col)`) | **锁定** |
| D4 | NaN 通过**滞后值自然传播**, 删除 `fitted_values.reindex().ffill()` | **锁定** |
| D5 | 新增公开参数 `warmup_obs=120`; `_WARMUP_REFIT_STRIDE=10` 为模块私有常量; `warmup_obs <= min_obs` 抛 `ValueError` | **锁定** |
| D6 | φ 布局钉子的容差 `0.05 → 0.15` (附覆盖率注释) | **锁定** |
| D7 | PL-07 拆为"输出不变式 (摘 xfail)" + "路由一致性 (3 seeds)" | **锁定** |
| D8 | 版本 v3.3.6 / 缓存 `v2.2.4-cache` / ADR-040 | **锁定** |
| D9 | 范围仅 `ARDecoupler`; `OptimizedARDecoupler` / `TemporalDecoupler` 不改, 登记为已知同类缺陷 | **锁定** |
| D10 | `_fit_ar` 的 AIC 跨阶数不可比 (`hold_back`) **不纳入本任务**, 登记 `PL-08-candidate` | **锁定** |

**验收目标**:

| 测试 | 基线 | 目标 |
|------|------|------|
| `test_dynamic_pipeline_is_truncation_invariant` | 1653 格 / 8 NaN / 8.045e-01 | **0 / 0 / 0** |
| `test_v2_pipeline_is_truncation_invariant` | 1650 格 / 1.8397 | **0 / 0 / 0**, 路由一致 |
| 新增单测 (AR 单步多截断点) | — | **全部 0 / 0** |

**选定 B'' 的理由**:

1. **因果性**: 阶数/系数/预测三者都只依赖前缀; A/B/B'/B'' 在探针上均为 0/0, 但只有 B'' 同时满足下面的成本与兼容约束。
2. **成本**: 逐 t 重估 (A/B') 在 2500×300 上为 8.4–19.1s 或小时级; B'' 为 2.1–5.8s (AR 阶段 0.48s 基线)。
3. **兼容**: `warmup_obs=120` 时既有 φ 精度断言原样通过 (K=60 会失败); 两段 warm-up 使 `test_information_loss_signal_lost` 保持 `signal_lost`。
4. **外部锚点**: FPP3 §5.10 (warm-up + 只用先验观测)、tsibble `.init/.step`、sktime `initial_window/step_length`、skforecast `refit=n` 的"间歇重估"实践 (cost 49× / metric 1.6%), statsmodels `AutoReg.predict(dynamic=False)` 用真实滞后值。
5. **最小改动**: 只改 `ar_model.py` 一个文件 (两个类: `AROrderSelector` 拆出 `_fit_best`, `ARDecoupler` 三个方法 + `_predict_one_step`); 不触碰 `CompositeDecoupler` 三阶段、配置面、optimizer。

---

## §1 目标与非目标

### 1.1 目标

1. **因果性**: `fit` 与 `transform` 都只使用 `[0, t]` 可观测信息; 满足截断不变式。
2. **行为可解释**: 冷启动 = identity (不解耦), 预热 = 逐步重估, 稳定期 = 冻结模型。三段语义在 docstring 中写明。
3. **契约保持**: `transform(data)` 签名不变; `ARModelResult` 字段不变; `CompositeDecoupler` 三阶段顺序与 `strength` 语义不变。
4. **诊断可用**: `_get_ar_phi_for_diagnosis` / `get_summary` / `get_residual_stats` 仍工作, 但 φ 语义改为"拟合窗口内"。
5. **可测试**: 手算对照 + 多截断点不变式 + 短面板边界。
6. **可回滚**: 版本与缓存代际明确。

### 1.2 非目标

| 项 | 归属/说明 |
|----|-----------|
| `OptimizedARDecoupler` / `OptimizedCompositeDecoupler` | 非生产路径; 登记为同类已知缺陷 |
| `TemporalDecoupler._apply_ar_residual` / `decouple_ar` | 同上 |
| Stage 1 / Stage 3 中性化 | 已实测因果 (0 格), 不改 |
| 指纹路由的分类逻辑 | 本次实测无差异; 仅拆测试 (D7) |
| `_fit_ar` 的 `hold_back` (AIC 可比性) | **不修**; 登记 `PL-08-candidate` |
| `max_order=5` / `min_order=1` / `min_obs=20` 默认值 | 不改 |
| `decorrelation_strength` 语义 | 不改 (`(1-s)·series + s·residual`) |
| `CompositeDecoupler` / `DynamicFactorPipeline` 代码 | 不改 |
| `PipelineV2Config` / optimizer 搜索空间 | 不改; `warmup_obs` 不进入配置面 |
| 恢复到"样本内拟合值"的任何兼容开关 | 不做 (该行为就是缺陷) |
| 移除 AR 步骤 | 不做; 设计意图不变 |

---

## §2 现状与约束

### 2.1 当前代码路径

| 位置 | 现状 | 性质 |
|------|------|------|
| [`ARDecoupler.fit`](../../modules/factor_decoupler/core/ar_model.py#L256-L272) | `self._selector.batch_fit(data)` | 全样本 |
| [`AROrderSelector.fit`](../../modules/factor_decoupler/core/ar_model.py#L80-L129) | 全序列 AIC 选阶 | 前视 1 |
| [`AROrderSelector._fit_ar`](../../modules/factor_decoupler/core/ar_model.py#L131-L176) | 全序列 OLS, `fitted_values` 从第 `order` 行开始 | 前视 2 |
| [`ARDecoupler.transform`](../../modules/factor_decoupler/core/ar_model.py#L298-L331) | `predicted = fitted_values.reindex().ffill()`; `residual = series - predicted` | 前视 3 + NaN 模式 |
| [`ARDecoupler._get_ar_phi_for_diagnosis`](../../modules/factor_decoupler/core/ar_model.py#L274-L296) | 取 `_results` 的 `coefficients[1]` 均值 | 诊断契约 (ADR-030) |
| [`CompositeDecoupler.fit`](../../modules/factor_decoupler/core/dual_neutralizer.py#L384-L428) | Stage1 → `ARDecoupler.fit` | 无变更 |
| [`CompositeDecoupler.transform`](../../modules/factor_decoupler/core/dual_neutralizer.py#L444-L502) | Stage1 → AR → Stage3 | 无变更 |

### 2.2 数据契约

- `X: pd.DataFrame`, index = 日期, columns = 股票; AR 按**列**逐只股票独立建模。
- 位置对齐: `transform` 与 `fit` 的模型按列名匹配, 按行位置递推 (与现实现一致)。
- NaN: `fit` 时逐列 `dropna`; `transform` 时不填充, 滞后值 NaN → 该行输出 NaN。
- 输出保留 index / columns; 已拟合列不新增 NaN。
- 时间方向: 第 `t` 行只允许使用 `vals[0..t]`。

### 2.3 参数与边界

| 参数 | 默认 | 说明 |
|------|------|------|
| `max_order` / `min_order` / `criterion` / `min_obs` / `strength` | 5 / 1 / `'aic'` / 20 / 1.0 | **不变** |
| `warmup_obs` | **120** (新增) | `fit` 的估计窗口长度; 也是冻结起点 |
| `_WARMUP_REFIT_STRIDE` | **10** (模块常量, 新增) | warm-up 内每多少行重估一次系数 |

**派生量**:

```
early = max(min_order + 6, 2)        # AR(1) 至少需要 min_order+6 个观测
warm_end = min(warmup_obs, n)        # n = len(data)
```

**约束**: `warmup_obs > min_obs`; 否则 `__init__` 抛 `ValueError`。`min_obs` 默认 20, `early` 默认 7。

---

## §3 方案设计

### 3.1 `fit`: 只用前 `warmup_obs` 行

```python
def fit(self, data: pd.DataFrame) -> 'ARDecoupler':
    warm = min(self.warmup_obs, len(data))
    self._results = self._selector.batch_fit(data.iloc[:warm])
    self.is_fitted = True
    logger.info(f"AR模型拟合完成: {len(self._results)} 只股票 (窗口={warm} 行)")
    return self
```

- `batch_fit` 内部逐列 `dropna` 并检查 `len(series) >= min_obs`; 行为不变。
- 复杂度 `O(N · K · p²)`; `K=120` 远小于 `T`, 因此**比当前全样本拟合更快**。
- `_results` 的语义从"全样本模型"改为"**冻结模型** (前 K 行)"。

### 3.2 `transform`: 三段式因果一步预测

```python
result = data.copy()
for col in data.columns:                       # D3: 不以 _results 过滤
    vals = data[col].to_numpy(dtype=float)
    n = len(vals)
    res = vals.copy()                          # ① 冷启动 identity

    warm_end = min(self.warmup_obs, n)
    early = max(self.min_order + 6, 2)

    coef, p, last = None, 0, None
    for t in range(min(early, warm_end), warm_end):        # ② warm-up
        if coef is None or (t - last) >= _WARMUP_REFIT_STRIDE:
            ser = pd.Series(vals[:t]).dropna()             # 只用前缀
            try:
                if len(ser) < self.min_obs:
                    r = self._selector._fit_ar(ser, self.min_order)   # 早期固定低阶
                else:
                    r = self._selector._fit_best(ser)             # 全阶 AIC (无 INFO 日志)
            except Exception:
                continue
            coef = np.asarray(r.coefficients).flatten()
            p = r.order
            last = t
        res[t] = vals[t] - self._predict_one_step(vals, t, coef, p)

    frozen = self._results.get(col)            # ③ 冻结
    if frozen is not None and n > self.warmup_obs:
        c = np.asarray(frozen.coefficients).flatten()
        q = frozen.order
        pred = np.full(n, c[0])
        for i in range(1, q + 1):
            pred[i:] += c[i] * vals[: n - i]   # 只在已实现的值上累加
        res[self.warmup_obs:] = vals[self.warmup_obs:] - pred[self.warmup_obs:]

    result[col] = (1 - self.strength) * vals + self.strength * res
```

```python
@staticmethod
def _predict_one_step(vals: np.ndarray, t: int, coef: np.ndarray, p: int) -> float:
    """一步预测 c0 + Σ c_i·y_{t-i}; 滞后值为 NaN 时结果为 NaN."""
    yhat = coef[0]
    for i in range(p):
        yhat += coef[i + 1] * vals[t - 1 - i]
    return float(yhat)
```

**说明**:

1. `_selector._fit_ar` / `_selector._fit_best` 是同模块内的私有方法; 早期窗口 (`t < min_obs`) 不足以做 5 阶 AIC, 故固定 `min_order`; 全阶阶段调用 `_fit_best` 以避免 warm-up 产生 `N×12` 条 INFO 日志。两类私有调用都在 `ARDecoupler` 与 `AROrderSelector` 同属 `ar_model.py` 的前提下可接受。
2. 向量化冻结分支 `O(T·p)`, 不构造滞后矩阵 (numpy 文档指出滑动视图为 `O(N·W)` 且常非最优, 见调研 I5)。
3. `res = vals.copy()` 使 `t < early` 与无法拟合的行保持 identity; 已拟合列不会新增 NaN。
4. `pred` 的 NaN 通过 `vals` 自然传播; 不引入任何 `ffill`。
5. 复杂度: `O(N · (T·p + (K/stride)·p²))`, 无 `O(T²)` / `O(N²)`。

### 3.3 边界语义 (锁定)

| 场景 | 行为 | 依据 |
|------|------|------|
| `n < early` | 全列 identity | 观测不足以拟合 AR(min_order) |
| `early ≤ n ≤ warmup_obs` | 全列 warm-up, 无冻结分支 | `n > warmup_obs` 才进入冻结 |
| `t < early` | 该行 identity | 冷启动 |
| `t ∈ [early, min_obs)` | 固定 `min_order`, 每 stride 行重估 | 观测不足 5 阶 AIC |
| `t ∈ [min_obs, warmup_obs)` | 全阶 AIC, 每 stride 行重估 | warm-up |
| `t ≥ warmup_obs` | 冻结模型一步预测 | 稳定期 |
| 列全 NaN / 前缀有效观测 < early | identity | 无法拟合 |
| 列不在 `_results` 且 `n > warmup_obs` | `t ≥ K` 保持 identity (无冻结模型) | 无模型可用 |
| `fit` 时数据短于 `warmup_obs` | 冻结模型按 `min(K, fit_len)` 估计; 若 `transform` 面板更长, `t ≥ warmup_obs` 仍使用该模型 | 只依赖 `fit` 时可见数据 (因果) |
| 滞后值含 NaN | 该行输出 NaN | 不 ffill |
| `strength=0` | 输出 == 输入 (公式性质) | `(1-0)·series + 0·res` |
| `warmup_obs <= min_obs` | 构造期 `ValueError` | 语义不成立 |

> 与现有实现的差异: 旧行为在 `t < order` 返回 **NaN**, 新行为返回 **identity**。AR 输出 NaN 从 146 → 0 (调研 §3.7)。这是**有意**的行为变更: 缺少模型时"不做解耦"比"制造缺失"更符合数据契约; 且 `T=60` 的 `nan_ratio < 0.3` 断言要求 identity。

### 3.4 诊断契约 (ADR-030)

- `_get_ar_phi_for_diagnosis` 的 docstring 由"**全样本**平均 AR(1) 系数 φ"改为"**拟合窗口 (前 `warmup_obs` 行)** 的平均 AR(1) 系数 φ"。
- 返回值不变 (`coefficients[1]` 的均值); `AR_COEF_PHI1_INDEX` 布局不变。
- ADR-030 正文未固定"全样本"字样, **不需要改 ADR**; 仅在 ADR-040 的"影响"一节说明该语义变化。
- `get_summary()` / `get_residual_stats()` 的统计量改为基于冻结模型 (前 K 行), 语义随之变化, 但字段不变。

### 3.5 备选方案记录 (不实施)

| 代号 | 策略 | 拒绝理由 (调研 §3) |
|------|------|--------------------|
| A | 逐 t 扩展重估 | `O(T²·N)`, 2500×300 外推约 1.9 小时 |
| B | 前 K 冻结 + identity 冷启动 | `T=60` 时整列 identity, `test_soft_decoupling_strength` 失败 |
| B' | 逐 t warm-up + K 冻结 | 8.4–19.1s (2500×300), 成本过高 |
| C | rolling window / RLS | 改变模型类 / 新增窗口与遗忘因子配置 |

### 3.6 关键数值 (来自调研, 不重复测量)

| 指标 | 基线 | B'' (K=120, stride=10) |
|------|------|------------------------|
| AR 单步 (seed=22, t=60) | 1652/1800, `max=8.788e-01`, NaN 7 | **0 / 0 / 0** |
| Dynamic 端到端 | 1653/1800, 8 NaN, `8.045e-01` | **0 / 0 / 0** |
| 顶层 V2 | 1650/1800, `1.8397` | **0 / 0 / 0**, 路由一致 |
| AR 输出 NaN (3000 格) | 146 | **0** |
| `mean_ar1` (φ=0.7, 统计起点第 60 行) | 0.0029 (样本内, 非 OOS) | 0.0302 |
| 阶数 vs 全样本一致率 | — | 89.00% |
| 输出偏移 | — | 2851–2855/3000, `max_abs` 2.1–4.2 |
| AR 性能 (2500×300) | 0.48s | 2.11–5.76s |
| Dynamic 全管线 | 33.19s | 42.50s (+28%) |

---

## §4 测试设计 (TDD)

### 4.1 新增单元测试

文件: `tests/unit/test_ar_decoupler_causality.py`。

| 测试名 | 断言 |
|--------|------|
| `test_fit_uses_only_prefix` | 把第 `K` 行之后的数据替换为极端值, `_results` 的 `order` / `coefficients` 完全不变 |
| `test_truncation_invariant_multi_cut` | 参数化 `t ∈ {10, 15, 25, 30, 45, 60, 80}`; 全样本 vs 截断输出逐元素相等 (`atol=1e-12`) |
| `test_one_step_prediction_matches_hand_calc` | 手工构造 AR 系数与序列, 断言 `res[t] == vals[t] - (c0 + Σ c_i·vals[t-1-i])` (独立通式; 实现用 `max_order=2`) |
| `test_cold_start_is_identity` | `t < min_order+6` 的输出 == 输入 |
| `test_fitted_columns_add_no_nan` | 无 NaN 输入 → 无 NaN 输出 |
| `test_missing_results_column_not_blanket_identity` | 构造一列: 前 K 行有效观测 `min_order+2 ≤ m < min_obs` (实现取 17 个: `iloc[3:20]`) → `t ∈ [early, min_obs)` 走固定低阶分支 (输出 ≠ 输入); `t ≥ K` 无冻结模型保持 identity (锁定 N4; 构造需保证每个 warm-up 前缀至少 `min_order+2` 个有效值, 否则 `_fit_ar` 失败回退 identity) |
| `test_warmup_must_exceed_min_obs` | `warmup_obs <= min_obs` → `ValueError` |
| `test_strength_soft_mix` | `strength=0.5` 时 `out == 0.5·series + 0.5·residual`, 与手动组合一致 |
| `test_warmup_refit_uses_only_prefix` | 用 `unittest.mock.patch` 包装 `AROrderSelector._fit_ar` (含 `_fit_best` 内部调用), 记录每次传入的序列长度; 断言 `max(lengths) <= warmup_obs` 且 `min(lengths) < warmup_obs` (证明逐步扩展且不越界, N1/N2) |
| `test_metadata_preserved` | index / columns 完全一致 |

**测试数据策略**: 手算对照与边界用例必须用小面板手工构造; 不变式与偏移类断言允许合成面板, 但必须走独立参考实现或独立不变量, 不得用被测代码自证。

### 4.2 既有测试变更

| 文件 / 测试 | 变更 |
|-------------|------|
| `tests/test_factor_decoupler/test_hidden_effect.py::test_coefficients_layout_is_intercept_first` | φ 容差 `0.05 → 0.15`, 注释写明"前缀 OLS 的 `T⁻¹` 偏差 + `sd≈sqrt((1-φ²)/n)`; 0.05 在 n=120 覆盖率约 50%" |
| `tests/integration/test_pipeline_truncation_invariance.py::test_dynamic_pipeline_is_truncation_invariant` | 摘除 `xfail`; reason 记录迁入"已修复"表 |
| `tests/integration/...::test_v2_pipeline_is_truncation_invariant` | 摘除 `xfail`; **移除内部 routes 断言**, 只断言输出不变式 |
| `tests/integration/...::TestTopLevelInvariance` | 新增 `test_v2_pipeline_routing_is_causal`, 参数化 `(seed, kind) ∈ {(31,'skewed'), (22,'ar_low'), (7,'smooth')}`; **实测路由**: ⇒ dynamic / dynamic / static (未触发 mixed, mixed 路由由 `test_mixed_pipeline_is_truncation_invariant` 子管线测试覆盖); 只断言 `routes_full == routes_trunc`; **任一 seed 路由不一致 → 该 seed 移出参数化并登记 PL-07, 不得静默 skip** |
| 登记表 docstring | 移除 PL-05 / PL-07; "已修复"追加 PL-05 (1653/8 → 0/0), PL-07 (1.8397 → 0, 路由一致); 备注 `PL-08-candidate` (hold_back) 未登记为 xfail |
| `tests/test_fix3_version_unification.py` | `EXPECTED_VERSION=3.3.6`; 缓存字面量 `v2.2.4-cache`; L83-84 保留历史, L85 追加 PL-05 行 |
| `tests/test_backtest/verify_fix3_manual.py` | `EXPECTED_VERSION=3.3.6` |

### 4.3 回归基线

实施前记录 (本机):

```powershell
C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe -m pytest `
  tests/integration/test_pipeline_truncation_invariance.py `
  tests/test_factor_decoupler `
  tests/test_pipelines_v2.py -q
```

预期 (2026-11-04 实测): 集成 **10 passed / 2 xfailed** (PL-05 / PL-07; PL-06 已修复)。实施后: **15 passed / 0 xfailed** (12 个既有测试全部通过, 其中 2 个摘除 xfail; 新增路由测试参数化 3 seeds)。

---

## §5 验收标准

| # | 标准 | 验证方式 |
|---|------|---------|
| V1 | Dynamic 截断不变式 **0 格 / 0 NaN / 0** | 集成测试 |
| V2 | 顶层 V2 **0 / 0 / 0** 且路由一致 | 集成测试 |
| V3 | 摘除 xfail 后直接通过 (strict 模式下未摘除会 XPASS 报错) | 套件 |
| V4 | 新增单测全部通过 (10 个测试函数 / 16 个 pytest 用例) | pytest |
| V5 | AR 单步多截断点 (10/15/25/30/45/60/80) 均 0/0 | 单测 |
| V6 | 已拟合列不新增 NaN; index/columns 不变 | 单测 |
| V7 | `warmup_obs <= min_obs` 抛 `ValueError` | 单测 |
| V8 | 既有靶向套件全绿 (基线见 §4.3 实测; 实施后计数以步骤 5 记录为准, xfail 摘除与新增测试导致的计数变化不计入退化) | pytest |
| V9 | 性能: AR ≤ 6s, Dynamic 全管线 ≤ 45s (2500×300 本机) | 计时探针 |
| V10 | 输出偏移与调研一致 (2851–2855/3000) | 探针复测 |
| V11 | 版本/缓存/ADR-040/CHANGELOG/架构文档同步 | 文档核对 |
| V12 | `git grep -n "fitted_values\.reindex" -- '*.py'` 0 命中 (ar_model.py L325 删除; 集成测试 xfail reason 随装饰器移除); `fitted_values` 字段本身与 `optimized.py` (非生产) 保留白名单 | grep |

---

## §6 兼容性、版本与回滚

### 6.1 版本与缓存

| 项 | 值 |
|----|-----|
| 项目版本 | **v3.3.6** |
| 缓存 `CODE_VERSION` | **`v2.2.4-cache`** |
| ADR | **ADR-040** (占用表改为 "ADR-041 起 未占用") |
| CHANGELOG | v3.3.6 条目: 根因 / 方案 / 实测 / 影响面 / 迁移说明 |
| 架构/进度 | `ARCHITECTURE.md` / `DEV_PROGRESS.md` 版本基线追加 v3.3.6 |

### 6.2 输出与配置兼容性

- **输出数值变更**: AR 输出约 95% 格子变化 (`mean_abs` 0.23–0.35, `max_abs` 2.1–4.2); Dynamic 全链路结果需重算; 缓存代际 bump 使历史缓存一次性失效。
- **NaN 模式变更**: AR 输出的前导 NaN (146 格) 变为 identity (0 格); 下游排名/标准化会纳入这些早期行。属于行为修正, CHANGELOG 需写明。
- **配置**: 新增 `ARDecoupler(warmup_obs=120)`, 向后兼容 (关键字, 默认值); **不进入** `PipelineV2Config` / optimizer。
- **API**: `transform` 签名不变; `ARModelResult` 不变; `get_summary` / `get_residual_stats` 语义变为"冻结窗口"。
- **诊断**: φ 变为拟合窗口内均值; `diagnose_hidden_effects` 可用。

### 6.3 回滚

1. 恢复 `ARDecoupler.fit` 为 `batch_fit(data)` 全样本;
2. 恢复 `transform` 的 `fitted_values.reindex().ffill()` 与 `_results` 门控;
3. 恢复 `CODE_VERSION = "v2.2.3-cache"` 与版本 v3.3.5;
4. 恢复 PL-05 / PL-07 的 `xfail` 登记;
5. 重建缓存。

---

## §7 实施步骤 (TDD 顺序)

| 步 | 动作 | 产出 |
|----|------|------|
| 1 | Red: 新增 `tests/unit/test_ar_decoupler_causality.py` (10 个函数 / 16 个 pytest 用例; 实测 15 failed / 1 passed), 确认失败 | 失败测试 |
| 2 | Green: 改 `ARDecoupler.__init__/fit/transform` + `_predict_one_step` + `_WARMUP_REFIT_STRIDE` | 单测通过 |
| 3 | 摘除 PL-05 / PL-07 xfail; 新增 3-seed 路由测试; 更新登记表 | 集成全绿 |
| 4 | 放宽 `test_coefficients_layout_is_intercept_first` 的 φ 容差 + 覆盖率注释 + 追加 `0.5 < φ < 0.9` 区间断言 (同步 `test_ar_decoupler_hook_returns_known_phi` 的区间断言) | 靶向套件全绿 |
| 5 | 回归全量靶向套件 + 性能复测 + 输出偏移复测 | 验收记录 |
| 6 | 版本 / 缓存 / ADR-040 / CHANGELOG / 架构文档; 全仓 grep | 文档同步 |

---

## §8 风险与未决问题

| # | 风险/问题 | 处置 |
|---|----------|------|
| R1 | AR 输出 ≈95% 变化, 历史 IC/Sharpe 不可比 | CHANGELOG 明示; 缓存 bump; 重算 |
| R2 | AR 阶段 0.48s → 2.1–5.8s; Dynamic 全管线 +28% | 验收设上限 (V9); 不逐点重估 (外部锚点: skforecast 逐点重估成本 49×/精度 1.6%) |
| R3 | 短面板 (`T ≈ 20–60`) 的早期行仍为 identity/低阶 | 语义已文档化; `T=60` 的既有测试实测通过 |
| R4 | `_fit_ar` 为模块内私有方法调用 | 同模块内可接受; 单测覆盖早期窗口 |
| R5 | φ 诊断语义变为"窗口内", 与 ADR-030 的历史描述有差异 | 改 docstring; ADR-040 说明; 不改 ADR-030 正文 |
| R6 | 容差从 0.05 放宽到 0.15 被视为"弱化测试" | 设计依据: `T⁻¹` 偏差 + 模拟覆盖率 50.3%→94.8%; 该测试本意是布局钉子; 追加 `0.5 < φ < 0.9` 区间断言作补偿 |
| R7 | 路由 3-seed 断言仍非普遍证明 | 外部锚点 (Varma-Simon / Bayğın) 说明路由是独立泄漏向量; 断言保留为回归闸门 |
| R8 | `_fit_ar` 的 AIC 跨阶数不可比 (`hold_back`) 未修 | 登记 `PL-08-candidate`; 会进一步改变输出, 另开任务 |
| R9 | `OptimizedARDecoupler` / `TemporalDecoupler` 同类缺陷未修 | 非生产路径; ADR-040 范围边界登记 |
| R10 | `warmup_obs` 公开后, 用户可能传入极小值 | `ValueError` 校验 + 文档建议 `>= min_obs + 10` |
| R11 | 若把 warm-up 起点改为 `min_obs` (去掉 `[early, min_obs)` 的固定低阶段), `test_information_loss_signal_lost` 会由 `signal_lost` 变 `ambiguous` | **必须保留两段 warm-up**; 该约束写入实现注释与单测 |

---

## §9 代码证据与影响面

### 9.1 必改

| 文件 | 变更 |
|------|------|
| `modules/factor_decoupler/core/ar_model.py` | `AROrderSelector.fit` 拆出无日志 `_fit_best`; `ARDecoupler.__init__` (+`warmup_obs`, 校验); `fit` 前缀窗口; `transform` 三段式 + `_predict_one_step`; 模块常量 `_WARMUP_REFIT_STRIDE`; 类/方法 docstring |
| `tests/unit/test_ar_decoupler_causality.py` | 新增 10 个函数 / 16 个 pytest 用例 |
| `tests/integration/test_pipeline_truncation_invariance.py` | 摘 2 个 xfail; 新增 3-seed 路由测试; 登记表 |
| `tests/test_factor_decoupler/test_hidden_effect.py` | φ 容差 0.05 → 0.15 + 注释 |
| `tests/test_fix3_version_unification.py` / `tests/test_backtest/verify_fix3_manual.py` | 版本 / 缓存字面量 |
| `pyproject.toml` / `__init__.py` / `config_v2.py` / `reporting.py` / `backtest/cache_manager.py` | v3.3.6 / `v2.2.4-cache` |
| `DECISIONS.md` / `CHANGELOG.md` / `docs/ARCHITECTURE.md` / `docs/DEV_PROGRESS.md` | ADR-040 / v3.3.6 |

### 9.2 不改

- `modules/factor_decoupler/core/dual_neutralizer.py` (Stage 1/3 已因果)
- `modules/factor_decoupler/core/optimized.py` / `unified_decoupler.py`
- `pipelines_v2.py` (`DynamicFactorPipeline` / `CompositeDecoupler` 构造)
- `config_v2.py` 的字段集合 (只改版本字符串)
- `optimizer.py` 搜索空间
- `tests/unit/test_mixed_winsorize_cross_sectional.py` 等 PL-06 工件

### 9.3 已知同类缺陷 (不修, 登记)

| 位置 | 问题 | 处置 |
|------|------|------|
| [`OptimizedARDecoupler`](../../modules/factor_decoupler/core/optimized.py#L119) | 全样本选阶 + 全样本系数 | 非生产路径; ADR-040 登记 |
| [`TemporalDecoupler._apply_ar_residual`](../../modules/factor_decoupler/core/unified_decoupler.py#L375-L381) | 返回样本内残差 | 同上 |
| [`AROrderSelector._fit_ar`](../../modules/factor_decoupler/core/ar_model.py#L131-L176) | AIC 跨阶数不可比 (`hold_back`) | `PL-08-candidate` |

---

## §10 ADR-040 决策要点 (供实施时抄录)

1. **决策**: `ARDecoupler` 的 `fit` 只使用前 `warmup_obs=120` 行; `transform` 采用"冷启动 identity → 早期固定低阶 → 全阶逐步重估 (stride=10) → `t ≥ K` 冻结"的三段式因果一步预测。
2. **背景**: 全样本 AIC 选阶 + 全样本 OLS + `fitted_values` 拟合值三重前视; 动态管线截断实测 1653/1800 格差异。
3. **备选**: A 逐 t 扩展 (小时级)、B 纯冻结 (短面板失败)、B' 逐 t warm-up (8.4–19.1s)、C rolling/RLS (改模型类)。
4. **影响**: 输出 ≈95% 变化; NaN 146→0; AR 阶段 0.48→2.1–5.8s; 全管线 +28%; φ 诊断语义改为窗口内。
5. **范围边界**: 不修 `OptimizedARDecoupler` / `TemporalDecoupler`; 不修 `hold_back`; 不改配置面与 optimizer。
6. **外部依据**: FPP3 §5.10、tsibble `.init/.step`、sktime `initial_window/step_length`、skforecast `refit=n`、statsmodels `AutoReg.predict(dynamic=False)` / `apply(refit=False)`、Marriott-Pope/Kendall 偏差、Varma-Simon / Bayğın。

---

## §11 步骤 4 review 记录 (幻觉排查与代码对齐)

**方法**: 逐项核对设计声明 vs 源码 (行号/签名/默认值/调用点)、ADR 原文、既有测试位置、调研数值回源。

### 11.1 核对通过项

| # | 检查项 | 方法 | 结果 |
|---|--------|------|------|
| P1 | 行号: `AROrderSelector.fit` L80 / `_fit_ar` L131 / `ARDecoupler.__init__` L235 / `fit` L256 / `_get_ar_phi_for_diagnosis` L274 / `transform` L298 | grep `^class \|    def` | **全部吻合** |
| P2 | 行号: `CompositeDecoupler.fit` L384 / `transform` L444 (dual_neutralizer.py); `OptimizedARDecoupler` L119 (optimized.py); `_apply_ar_residual` L375 (unified_decoupler.py) | 同上 | **吻合** |
| P3 | 接口: `ARDecoupler` 既有 5 参数默认值 5/1/'aic'/1.0/20 | 读 `__init__` L235-245 | **吻合**; `warmup_obs` 追加到末尾 |
| P4 | 调用点: 全仓 `ARDecoupler(` 共 5 处 (生产 1 处 dual_neutralizer L413 + 测试 4 处), 全部关键字传参 | grep | **无位置参数破坏风险** |
| P5 | `_results` 外部读取面: `_get_ar_phi_for_diagnosis` / `get_residual_stats` / `get_summary` / 布局钉子测试 | grep + 读码 | **属性名与 `ARModelResult` 字段不变**, 契约保持 |
| P6 | ADR-030 正文是否固定"全样本"字样 | 读 DECISIONS.md L2068-2128 | **无该字样**; §3.4 声称成立, 只需改钩子 docstring |
| P7 | `_WARMUP_REFIT_STRIDE` / `warmup_obs` 命名冲突 | 全仓 grep | **无冲突**; 与既有模块常量 `AR_COEF_*` 风格一致 |
| P8 | `_fit_ar(series, order)` 签名与 `self._selector._fit_ar(ser, min_order)` 调用 | 读 L131 | **吻合**; 内部 `lstsq` 失败路径由 try/except 覆盖 |
| P9 | `batch_fit` 逐列 `dropna` + `len >= min_obs` 检查 | 读 L206-217 | **吻合** (§3.1 声明成立) |
| P10 | 伪代码因果性: warm-up 用 `vals[:t]`, 冻结 `pred[t]` 只用 `vals[t-i]`, `t≥i` | 逐行推演 | **无未来引用**; NaN 自然传播成立 |
| P11 | 数值回源: §3.6 全部数字 vs 调研 §3.4 / 探针 7-10 | 逐项比对 | **一致** (1652/1653/1650, 8.788e-01, 8.045e-01, 1.8397, 146→0, 0.0302, 89.00%, 2.11–5.76s, 42.50s) |
| P12 | `test_information_loss_signal_lost` 位置与构造 (n=120, `_fit_composite` 用 max_ar_order=1) | 读 L190-209 | **吻合**; 修复后 fit 窗口=120=全长, 与补丁预演一致 |
| P13 | 布局钉子兼容: K=120 时 intercept 25.218>5, φ=0.7479; hook φ=0.6603 | 探针 5 数据 | **均在 0.15 与 [0.5, 0.9] 断言内** |
| P14 | 版本锚点: 4 处 3.3.5 + `v2.2.3-cache` 位置 | grep | **吻合** §9.1 清单; test_fix3 L83-84 PL-06 注释确认 |
| P15 | `tests/unit/` 目录存在 (25 文件) | Glob | **新测试文件路径有效** |
| P16 | 集成基线 10 passed / 2 xfailed | 实跑 pytest | **实测确认** (2026-11-04) |

### 11.2 发现并已修复的问题

| # | 严重度 | 问题 | 修复 |
|---|--------|------|------|
| F1 | **MAJOR** | §4.3 算术错误: 写"实施后 11 passed / 0 xfailed"; 实际 12 个既有测试全部通过 (含 2 个摘 xfail) + 路由测试 3 参数 = **15 passed** | 已改为 15 passed / 0 xfailed |
| F2 | MINOR | §4.2 路由测试未指定 `_panel` 的 kind (seed=7 无 kind 无法构造), 且未写失败处置 | 已明确 `(seed, kind)` 三组合; 补"不一致 → 移出参数化并登记 PL-07, 不得静默 skip" |
| F2b | MINOR | §4.2 曾声称三组合"覆盖 mixed/dynamic/static 三条路由"; 实施文档准备期实测为 **dynamic/dynamic/static**, 未触发 mixed | 已按实测更正; mixed 路由由 Mixed 子管线测试覆盖 |
| F3 | MINOR | §4.2 未写明 `test_v2_pipeline_is_truncation_invariant` 需**移除内部 routes 断言** (routes 移交新测试), 否则断言重复 | 已补 |
| F4 | MINOR | V12 "全仓 grep 无残留 fitted_values.reindex 生产调用" 口径含糊 (grep `fitted_values` 会命中 optimized.py 与字段定义) | 已精确为 `fitted_values\.reindex` 模式 + 白名单说明 |
| F5 | MINOR | §7 步骤 4 漏写 D6 的 `0.5<φ<0.9` 区间断言 | 已补 (含 hook 测试同步) |
| F6 | MINOR | `test_missing_results_column_not_blanket_identity` 构造描述不精确 (有效观测过少时 `_fit_ar` 失败回退 identity, 断言"仍解耦"会失真) | 已写明构造约束 `min_order+2 ≤ m < min_obs` |
| F7 | MINOR | V8 引用"117 passed 基线不退化"与摘 xfail/新增测试的计数变化冲突 | 已改为"基线见 §4.3, 计数变化不计入退化" |

### 11.3 结论

- 无幻觉级错误 (所有行号、签名、默认值、ADR 引用、数值均可回源)。
- 1 处 MAJOR (测试计数算术) + 6 处 MINOR 已全部修复; 设计文档升为 **v1.1**。
- 设计与调研 v1.3 (步骤 4 时点; 现 v1.4)、源码现状、ADR 登记规则三方一致, 可进入步骤 5 (实施文档)。

---

## §12 步骤 8 一致性 review 修订

详见 [CONSISTENCY_REVIEW_V3.3.6.md](../audit/CONSISTENCY_REVIEW_V3.3.6.md)。本设计在步骤 8 的修订:

| # | 位置 | 修订 |
|---|------|------|
| 1 | §3.2 / §9.1 | warm-up 全阶调用 `_fit_best` (无 INFO 日志); 必改清单补 `AROrderSelector.fit` 拆分 |
| 2 | §3.2 说明 1 | "唯一私有调用" 改为 `_fit_ar` / `_fit_best` 两类 |
| 3 | §4.1 | mock 断言口径与实施 §4.1 对齐 (`max ≤ warmup_obs`, `min < warmup_obs`) |
| 4 | §5 V4 / §7 / §9.1 | 单测计数明确为 10 个函数 / 16 个 pytest 用例 |
| 5 | §3.6 | `mean_ar1` 注明统计起点第 60 行 (与调研 §3.4 的起点 6 口径区分) |
| 6 | §4.2 / §11 P14 | 缓存历史行号 L83-84 → L85 追加 |
| 7 | §3.2 伪代码 | `_predict_one_step(...)` → `self._predict_one_step(...)` (staticmethod 调用); 实施 §3.4 代码块加注"类内方法, 缩进省略" |

---

## 附录 A: 调研数据引用

所有实测数据、探针原始输出、外部锚点原文与证据等级、未验证项见
[PL05_DYNAMIC_AR_LOOKAHEAD_RESEARCH.md](PL05_DYNAMIC_AR_LOOKAHEAD_RESEARCH.md) §3 / §10 / §11 / 附录 A-C。
本文只引用结论, 不重复粘贴原始输出, 避免两处数值漂移。
