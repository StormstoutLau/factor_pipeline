# v3.0.0 T1 执行方案 — 指纹维度扩展至 21 维 v1.1

> **版本**: v1.1 (2026-07-04)
> **范围**: T1 (P1) 指纹维度扩展, 13 维 → 21 维 (新增 8 维)
> **基础**: [ANALYSIS_V3.0.0.md](ANALYSIS_V3.0.0.md) §1 + fingerprint.py 调研报告
> **前置**: v3.0.0 T4 已完成 (934 passed + 6 skipped + 11 subtests)
> **方法**: 与 T4 一致的 E1-E3 三阶段 TDD 流程, 严格 Red→Green→Review
> **v1.1 修订**: 根据 review (1 CRITICAL + 3 MAJOR + 4 MINOR + 4 NIT) 系统性修订, 详见末尾修订日志

---

## 0. 摘要

### 0.1 目标

将 `FactorFingerprint` 从 13 维扩展至 21 维, 新增 8 维:

| 子任务 | 维度数 | 字段 | 学术依据 |
|--------|--------|------|---------|
| **T1.1 尾部依赖** | 4 | tail_dependence_lower / tail_dependence_upper / gpd_shape / hill_estimator | Nelsen (2006) / Pickands (1975) / Hill (1975) |
| **T1.2 体制转换** | 3 | regime_transition_prob / regime_persistence / regime_ic_diff | Hamilton (1989) |
| **T1.3 综合衍生 (新)** | 1 | tail_regime_score | _derive_sd_score 模式 |

> **M1 修订**: T1.3 "综合衍生 (新)" 与既有 "综合衍生 3 维" (sd_score/complexity_need/snr_estimate) 是不同类别, 标注 "(新)" 避免混淆。

### 0.2 关键设计决策 (调研后自主确定)

| # | 决策 | 选项 | 理由 |
|---|------|------|------|
| 1 | 路由接入 | 接入 + 配置开关 (`enable_multi_dim_routing` 默认 False) | 平衡新维度影响与回归风险, 显式 opt-in |
| 2 | 分类器扩展 | 仅扩展指纹, 不改 `classify()` | 聚焦改动, 新维度仅影响 `_get_multi_dim_pipeline_weights` 修正层 |
| 3 | 测试基线 | E1 扩展时同步补齐黄金参考 + `to_dict` 字段完整性测试 | TDD 严格模式, 锁定 13 维行为 + 验证 21 维 |
| 4 | 实施范围 | 全部 8 维 (T1.1+T1.2+T1.3), Markov 加降级方案 | 一次达到 21 维目标, Markov 不收敛返回 NaN |

### 0.3 调研发现的关键事实 (超出 ANALYSIS 预期)

1. **孤儿函数**: `_get_multi_dim_pipeline_weights` (pipelines_v2.py:96-179) 在生产代码中**从未被调用**, `transform()` L1187 仍用单维 `_get_pipeline_weights` → T1 必须接入生产路径
2. **分类器单维瓶颈**: `AdaptiveFactorClassifier.classify` (classifier.py:77) 仅用 `ar1_median`, 其余 12 维未读取 → T1 不扩展分类器, 新维度仅作用于路由修正层
3. **测试基线薄弱**: 无 `extract_fingerprint` 黄金参考测试, 无 `to_dict` 字段完整性测试 → T1 必须补齐
4. **statsmodels 延迟导入**: `_test_volatility_clustering` (fingerprint.py:261) 用 try/except 包裹 statsmodels, 违反 ADR-014 → T1 顺手清理技术债

### 0.4 三阶段划分

| 阶段 | 任务 | 测试数 | 关键产出 |
|------|------|--------|---------|
| **E1** | 指纹核心扩展 (Red→Green→Review) | ~20 | `FactorFingerprint` 21 维 + 8 个新计算方法 + `FingerprintConfig` 扩展 + 黄金参考测试 + `to_dict` 完整性测试 |
| **E2** | 路由层接入 + 测试更新 | ~8 | `_get_multi_dim_pipeline_weights` 接入 transform + 配置开关 + 新维度修正逻辑 + 测试更新 |
| **E3** | 文档同步 + 全量回归 | 0 | CHANGELOG/CODE_WIKI/README + ADR-024 + 手工校验 + 全量回归 |

---

## 1. E1 核心改动: 指纹维度扩展

### 1.1 FactorFingerprint NamedTuple 扩展 (fingerprint.py:34-70)

**当前 13 维** → **目标 21 维** (新增 8 维, 追加在末尾, 向后兼容):

```python
class FactorFingerprint(NamedTuple):
    # ── 时序稳定性指标 (5 维, 不变) ──
    ar1_median: float = np.nan
    rank_autocorr: float = np.nan
    vol_clustering_pvalue: float = np.nan
    half_life: float = np.nan
    level_diff_ic_ratio: float = np.nan
    # ── 截面稳定性指标 (5 维, 不变) ──
    skewness_std: float = np.nan
    kurtosis_std: float = np.nan
    js_divergence_mean: float = np.nan
    missing_cv: float = np.nan
    coverage_ratio: float = np.nan
    # ── 综合衍生指标 (3 维, 不变) ──
    sd_score: float = np.nan
    complexity_need: float = np.nan
    snr_estimate: float = np.nan
    # ── T1.1 尾部依赖指标 (4 维, 新增) ──
    tail_dependence_lower: float = np.nan      # 下尾依赖系数
    tail_dependence_upper: float = np.nan      # 上尾依赖系数
    gpd_shape: float = np.nan                  # GPD 形状参数 ξ
    hill_estimator: float = np.nan             # Hill 重尾指数
    # ── T1.2 体制转换指标 (3 维, 新增) ──
    regime_transition_prob: float = np.nan     # Markov 两状态转移概率
    regime_persistence: float = np.nan         # regime 平均持续期
    regime_ic_diff: float = np.nan             # 两 regime 间 IC 差异
    # ── T1.3 综合衍生指标 (1 维, 新增) ──
    tail_regime_score: float = np.nan          # 尾部+体制综合得分
```

### 1.2 FingerprintConfig 扩展 (fingerprint.py:73-83)

新增 6 个配置字段 (向后兼容, 有默认值):

```python
@dataclass
class FingerprintConfig:
    # ── 既有 8 字段 (不变) ──
    min_window: int = 24
    decay_halflife: int = 12
    min_obs_per_stock: int = 12
    min_stocks: int = 10
    min_cv_threshold: float = 0.01
    js_bins: int = 20
    vol_cluster_lags: int = 12
    ar1_max_lag: int = 20
    # ── T1.1 尾部依赖配置 (3 字段, 新增) ──
    tail_quantile: float = 0.05                # 尾部分位数阈值 (下/上 5%)
    min_extreme_samples: int = 100             # GPD/Hill 最小极值点数
    enable_tail_dependence: bool = False       # Copula 拟合开关 (默认关闭, O(N²) 成本)
    # ── T1.2 体制转换配置 (2 字段, 新增) ──
    enable_regime_switching: bool = False       # Markov 拟合开关 (m1 修订: 默认 False, 避免小样本日志噪音)
    regime_min_samples: int = 200              # Markov 拟合最小样本数
    # ── T1.3 综合得分配置 (1 字段, 新增) ──
    tail_regime_weight: float = 0.5            # tail_regime_score 中尾部权重 (1-w 为体制权重)
```

### 1.3 新增 8 个私有计算方法

#### T1.1 尾部依赖 (4 方法)

**`_compute_tail_dependence_lower(self, factor_data) -> float`**:
- 计算下尾依赖系数 λ_L = P(U < q | V < q), q = `tail_quantile`
- 学术依据: Nelsen (2006) An Introduction to Copulas
- 实现: 对每只股票的因子值序列, 取下 `tail_quantile` 分位数, 计算同时低于该分位数的联合概率
- 守卫: `enable_tail_dependence=False` 或样本数 < `min_extreme_samples` → 返回 NaN
- 复杂度: O(N²) per stock (Copula 经验估计), 仅在 `enable_tail_dependence=True` 时计算

**`_compute_tail_dependence_upper(self, factor_data) -> float`**:
- 计算上尾依赖系数 λ_U = P(U > q | V > q), q = 1 - `tail_quantile`
- 实现同 `_compute_tail_dependence_lower`, 方向取上尾
- 守卫同上

**`_estimate_gpd_shape(self, factor_data) -> float`**:
- 估计 GPD 形状参数 ξ (Pickands 1975 estimator)
- 学术依据: Pickands (1975) Statistical inference using extreme order statistics
- 实现: 对每只股票的因子值序列, 取绝对值最大的 `min_extreme_samples` 个点, 用 Pickands 估计量计算 ξ
- 公式: ξ_pickands = (1/log2) * log((X_{n-k} - X_{n-2k}) / (X_{n-2k} - X_{n-4k}))
- 守卫: 样本数 < `min_extreme_samples` * 4 → 返回 NaN
- 数值范围: ξ ∈ (-0.5, +∞), 正值表示重尾

**`_hill_estimator(self, factor_data) -> float`**:
- Hill 重尾指数估计量 (Hill 1975)
- 学术依据: Hill (1975) A simple general approach to inference about the tail of a distribution
- 实现: 对每只股票的因子值序列的正尾部分 (上 `min_extreme_samples` 个点), 计算 Hill 估计量
- 公式: α_hill = (1/k) * Σ log(X_{n-i+1} / X_{n-k}), ξ_hill = 1/α_hill
- 守卫: 样本数 < `min_extreme_samples` → 返回 NaN
- 与 gpd_shape 互补: Hill 仅估计正尾部, GPD 双尾

#### T1.2 体制转换 (3 方法)

**`_compute_regime_transition_prob(self, factor_data) -> float`**:
- Markov 两状态转移概率 (Hamilton 1989)
- 学术依据: Hamilton (1989) A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle
- 实现: 对因子截面均值序列 (T,), 用 statsmodels MarkovRegression 拟合两状态模型, 取转移概率 P(bull→bear)
- 依赖: `from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression` (顶部显式导入, ADR-014)
- 守卫: `enable_regime_switching=False` 或样本数 < `regime_min_samples` → 返回 NaN
- 降级方案: 拟合不收敛 (ConvergenceWarning) → 返回 NaN + 降级为硬阈值 bull/bear 划分 (复用 health.py:1452 `_split_bull_bear` 思路)

**`_compute_regime_persistence(self, factor_data) -> float`**:
- regime 平均持续期 = 1 / P(leave), P(leave) = 转移概率
- 实现: 从 `_compute_regime_transition_prob` 的拟合结果中取 P(bull→bear) 和 P(bear→bull), 计算平均持续期
- 公式: persistence_bull = 1 / P(bull→bear), persistence_bear = 1 / P(bear→bull), 取均值
- 守卫: 同 `_compute_regime_transition_prob`

**`_compute_regime_ic_diff(self, factor_data) -> float`**:
- 两 regime 间因子一阶差分均值差 (bull Δfactor 均值 - bear Δfactor 均值)
- **方案选择 (C1 修订)**: `extract_fingerprint` 仅接受 `factor_data`, 无前向收益数据, 故采用方案 C (一阶差分均值差, 语义近似 IC 差异, 不破坏函数签名)
- 实现: 从 Markov 拟合结果获取 smoothed_probabilities, 划分 bull/bear 时段, 计算各时段因子一阶差分均值差
- 公式: ic_diff = mean(Δfactor_bull) - mean(Δfactor_bear), Δfactor_t = factor_t - factor_{t-1}
- 守卫: 同 `_compute_regime_transition_prob`

#### T1.3 综合衍生 (1 方法)

**`_derive_tail_regime_score(self, tail_lower, tail_upper, gpd_shape, hill_estimator, regime_trans_prob, regime_persistence, regime_ic_diff) -> float`**:
- 尾部+体制综合得分, 遵循 `_derive_sd_score` (fingerprint.py:425-452) 归一化模式
- **M2 修订: 简化公式, 分步计算**
- 实现:
  1. NaN 守卫: 若 gpd_shape 和 regime_trans_prob 均为 NaN → 返回 NaN
  2. 分步归一化到 [0, 1]:
     - `tail_severity = np.clip((abs(gpd_shape) + abs(hill_estimator)) / 2, 0, 1)` if 两者非 NaN else 0.5
     - `regime_instability = np.clip(regime_trans_prob / 0.5, 0, 1)` if 非 NaN else 0.5
  3. 加权求和 (权重由 `FingerprintConfig.tail_regime_weight` 控制):
     - `score = tail_regime_weight * tail_severity + (1 - tail_regime_weight) * regime_instability`
  4. `return float(np.clip(score, 0, 1))`
- 设计理由: 简化为双分量加权 (尾部严重度 + 体制不稳定度), 避免嵌套权重可读性差; tail_lower/tail_upper/regime_persistence/regime_ic_diff 已被各自基础指标 (gpd_shape/regime_trans_prob) 概括, 不重复计入

### 1.4 extract_fingerprint 流程扩展 (fingerprint.py:107-160)

在现有三阶段后追加 **阶段 4 — T1 新维度计算**:

```python
# 阶段 4 — T1 尾部依赖 + 体制转换 (v3.0.0)
tail_lower = self._compute_tail_dependence_lower(factor_data)
tail_upper = self._compute_tail_dependence_upper(factor_data)
gpd_shape = self._estimate_gpd_shape(factor_data)
hill_est = self._hill_estimator(factor_data)
regime_trans = self._compute_regime_transition_prob(factor_data)
regime_persist = self._compute_regime_persistence(factor_data)
regime_ic = self._compute_regime_ic_diff(factor_data)
# 阶段 5 — T1 综合衍生
tail_regime = self._derive_tail_regime_score(
    tail_lower, tail_upper, gpd_shape, hill_est,
    regime_trans, regime_persist, regime_ic
)
```

`FactorFingerprint(...)` 构造调用追加 8 个字段赋值。

### 1.5 to_dict 方法同步 (fingerprint.py:55-70)

追加 8 个键值对:

```python
'tail_dependence_lower': self.tail_dependence_lower,
'tail_dependence_upper': self.tail_dependence_upper,
'gpd_shape': self.gpd_shape,
'hill_estimator': self.hill_estimator,
'regime_transition_prob': self.regime_transition_prob,
'regime_persistence': self.regime_persistence,
'regime_ic_diff': self.regime_ic_diff,
'tail_regime_score': self.tail_regime_score,
```

### 1.6 技术债清理 (顺手)

1. **statsmodels 延迟导入清理**: 将 `_test_volatility_clustering` (fingerprint.py:261) 的 `try/except` 延迟导入改为顶部 `from statsmodels.stats.diagnostic import acorr_ljungbox` (n1 修订: 违反 ADR-014 "REQUIRED 依赖 (scipy/statsmodels) 禁止 try/except 包裹")
2. **`_manual_ljungbox` 回退方法**: statsmodels 显式导入后保留此方法 (n2 修订: 保留理由 — 作为算法文档, 项目惯例是保留手工实现作为 fallback 算法参考, 且删除会破坏既有测试)
3. **未使用导入清理**: `Any, List, Tuple` 导入未使用 → 删除

### 1.7 E1 测试计划 (TDD)

#### E1-T1 黄金参考测试 (新增, 锁定 13 维 + 8 维行为)

**文件**: `tests/test_factor_fingerprint/test_extract_fingerprint_golden.py` (新建目录与文件)

**测试类**: `TestExtractFingerprintGolden`

```python
def test_golden_reference_21_dims(self):
    """黄金参考: 固定输入 → 固定 21 维输出 (atol=1e-4)"""
    # 构造固定输入 DataFrame (seed=42, T=300, N=50)
    # 期望: 21 维 FactorFingerprint 字段值全部精确匹配
    # 覆盖: 13 既有维度 + 8 新维度
```

#### E1-T2 to_dict 字段完整性测试 (新增)

**测试类**: `TestToDictCompleteness`

```python
def test_to_dict_has_21_keys(self):
    """to_dict 返回 21 个键, 覆盖全部 FactorFingerprint 字段"""
def test_to_dict_keys_match_namedtuple_fields(self):
    """to_dict 键集合 == FactorFingerprint._fields"""
```

#### E1-T3 尾部依赖维度测试 (新增 4 维)

**测试类**: `TestTailDependenceDimensions`

```python
def test_tail_dependence_lower_disabled_returns_nan(self):
    """enable_tail_dependence=False → tail_dependence_lower=NaN"""
def test_tail_dependence_lower_normal_case(self):
    """正常计算: 重尾分布 → tail_dependence_lower > 0"""
def test_tail_dependence_upper_normal_case(self):
    """正常计算: 重尾分布 → tail_dependence_upper > 0"""
def test_gpd_shape_heavy_tail(self):
    """t 分布 (df=3) → gpd_shape > 0 (重尾)"""
def test_gpd_shape_normal_distribution(self):
    """正态分布 → gpd_shape ≈ 0"""
def test_hill_estimator_heavy_tail(self):
    """t 分布 (df=3) → hill_estimator > 0"""
def test_hill_estimator_insufficient_samples(self):
    """样本数 < min_extreme_samples → hill_estimator=NaN"""
```

#### E1-T4 体制转换维度测试 (新增 3 维)

**测试类**: `TestRegimeSwitchingDimensions`

```python
def test_regime_transition_prob_normal_case(self):
    """构造两状态序列 → regime_transition_prob ∈ (0, 1)"""
def test_regime_persistence_normal_case(self):
    """构造两状态序列 → regime_persistence > 1"""
def test_regime_ic_diff_normal_case(self):
    """构造 IC 差异序列 → regime_ic_diff != 0"""
def test_regime_disabled_returns_nan(self):
    """enable_regime_switching=False → 3 维体制指标全 NaN"""
def test_regime_insufficient_samples_returns_nan(self):
    """样本数 < regime_min_samples → 3 维体制指标全 NaN"""
def test_regime_non_convergent_returns_nan(self):
    """构造不收敛序列 → 3 维体制指标全 NaN (降级方案)"""
```

#### E1-T5 tail_regime_score 综合得分测试 (新增 1 维)

**测试类**: `TestTailRegimeScore`

```python
def test_all_nan_inputs_returns_nan(self):
    """所有输入 NaN → tail_regime_score=NaN"""
def test_normal_inputs_returns_in_01(self):
    """正常输入 → tail_regime_score ∈ [0, 1]"""
def test_heavy_tail_high_score(self):
    """重尾 + 体制不稳定 → tail_regime_score > 0.5"""
def test_light_tail_low_score(self):
    """轻尾 + 体制稳定 → tail_regime_score < 0.5"""
```

#### E1-T6 既有 13 维行为不破坏 (回归测试)

**测试类**: `TestBackwardCompat13Dims`

```python
def test_existing_13_dims_unchanged(self):
    """扩展后既有 13 维字段值与扩展前一致 (黄金参考对比)"""
def test_default_config_disables_tail_and_regime(self):
    """默认配置: enable_regime_switching=False, enable_tail_dependence=False (m1 修订)"""
def test_extract_fingerprint_with_min_window_returns_nan(self):
    """样本数 < min_window → 全 21 维 NaN"""
```

### 1.8 E1 验收标准

- [ ] E1-T1 ~ E1-T6 测试全部 Red → Green
- [ ] `FactorFingerprint` NamedTuple 包含 21 个字段
- [ ] `FingerprintConfig` 包含 14 个字段 (8 既有 + 6 新增)
- [ ] `to_dict` 返回 21 个键
- [ ] `extract_fingerprint` 默认配置: 体制转换关闭, 尾部依赖关闭 (m1 修订)
- [ ] 既有 13 维字段值与扩展前一致 (黄金参考回归)
- [ ] statsmodels 顶部显式导入 (技术债清理)
- [ ] 全量回归 934 passed 不变 (新测试额外 +~20)

---

## 2. E2 路由层接入 + 测试更新

### 2.1 接入 _get_multi_dim_pipeline_weights 到 transform

**当前状态**: `transform()` (行号待 E2 实施时确认, 调研报告标注为 L1187 附近) 调用单维 `_get_pipeline_weights`, 多维函数 `_get_multi_dim_pipeline_weights` 是孤儿 (M3 修订: 行号待确认)

**改动方案**: 在 `PipelineConfig` 新增 `enable_multi_dim_routing: bool = False` 开关 (默认关闭, 向后兼容)

```python
# pipelines_v2.py transform() L1187 附近
if self.config.enable_multi_dim_routing:
    weights = _get_multi_dim_pipeline_weights(fingerprint, classification)
else:
    weights = _get_pipeline_weights(classification)  # 旧路径
```

### 2.2 _get_multi_dim_pipeline_weights 新维度修正逻辑

在现有 skewness/kurtosis/snr 修正后, 追加 T1 新维度修正:

```python
# T1 新维度修正 (v3.0.0)
tail_severity = fingerprint.gpd_shape  # 或 hill_estimator
tail_valid = not (tail_severity is None or (isinstance(tail_severity, float) and np.isnan(tail_severity)))

if tail_valid and abs(tail_severity) > 0.3:  # 重尾阈值 0.3
    # 重尾 → 向 mixed 偏移 (重尾因子需要更复杂处理)
    tail_shift = min(0.10, (abs(tail_severity) - 0.3) / 3.0)
    if weights['static'] > 0:
        weights['static'] = max(0.0, weights['static'] - tail_shift)
    weights['mixed'] = weights['mixed'] + tail_shift

regime_instability = fingerprint.regime_transition_prob
regime_valid = not (regime_instability is None or (isinstance(regime_instability, float) and np.isnan(regime_instability)))

if regime_valid and regime_instability > 0.1:  # 体制不稳定阈值
    # 体制不稳定 → 向 dynamic 偏移
    regime_shift = min(0.10, (regime_instability - 0.1) / 2.0)
    if weights['static'] > 0:
        weights['static'] = max(0.0, weights['static'] - regime_shift * 0.5)
    if weights['mixed'] > 0:
        weights['mixed'] = max(0.0, weights['mixed'] - regime_shift * 0.5)
    weights['dynamic'] = weights['dynamic'] + regime_shift
```

### 2.3 E2 测试计划

**文件**: `tests/test_multi_dim_classifier.py` (扩展现有)

- 更新 `_make_fp` 辅助函数支持 21 维 (新增 8 维参数, 默认 NaN)
- 新增 `TestTailRegimeAdjustment` 测试类 (~4 测试):
  - `test_heavy_tail_shifts_toward_mixed`
  - `test_light_tail_no_effect`
  - `test_regime_instability_shifts_toward_dynamic`
  - `test_stable_regime_no_effect`
- 新增 `TestMultiDimRoutingConfig` 测试类 (~4 测试):
  - `test_enable_multi_dim_routing_false_uses_single_dim` (默认走旧路径)
  - `test_enable_multi_dim_routing_true_uses_multi_dim`
  - `test_config_default_is_false`
  - `test_transform_with_multi_dim_routing_integration`

### 2.4 E2 验收标准

- [ ] `_get_multi_dim_pipeline_weights` 接入 transform, 配置开关默认 False
- [ ] 新维度修正逻辑 (tail_severity / regime_instability) 实现
- [ ] `_make_fp` 辅助函数支持 21 维
- [ ] 新增 ~8 测试全部 Red → Green
- [ ] 既有 12 测试不破坏 (test_multi_dim_classifier.py)
- [ ] 全量回归 934 + ~20 (E1) + ~8 (E2) = ~962 passed

---

## 3. E3 文档同步 + 全量回归

### 3.1 文档同步清单

| 文档 | 更新内容 |
|------|---------|
| **DECISIONS.md** | 新增 ADR-024 (指纹维度扩展至 21 维) |
| **CHANGELOG.md** | 新增 v3.0.0 T1 章节 (E1-E3 三阶段表 + 8 维新维度 + 学术依据) |
| **CODE_WIKI.md** | 更新 §指纹模块: 13 维 → 21 维表格 + 新维度计算方法说明 |
| **README.md** | 版本摘要新增 v3.0.0 T1 + 版本历史新增行 + 版本信息升级 |
| **README.en.md** | 同步英文版 v3.0.0 T1 |
| **ANALYSIS_V3.0.0.md** | T1 状态从"待启动"改为"已实施" |

### 3.2 手工校验脚本

**文件**: `tests/test_factor_fingerprint/verify_v3_0_0_t1_manual.py` (新建)

8 项手工校验:
1. 21 维字段完整性 (NamedTuple `_fields` 长度 = 21)
2. `to_dict` 返回 21 个键
3. `FingerprintConfig` 14 个字段
4. 默认配置: `enable_regime_switching=False`, `enable_tail_dependence=False` (m1 修订)
5. 尾部依赖关闭时 4 维 NaN
6. 体制转换开启时 3 维有值
7. `tail_regime_score` ∈ [0, 1]
8. 既有 13 维黄金参考回归

### 3.3 全量回归

**期望**: 934 (T4 基线) + ~20 (E1) + ~8 (E2) = **~962 passed**, 6 skipped, 11 subtests

### 3.4 ADR-024 内容大纲

```markdown
## ADR-024: 指纹维度扩展至 21 维 (v3.0.0 T1)

**日期**: 2026-07-XX
**状态**: 已实施
**supersedes**: 无 (扩展 ADR-019 内化模块的指纹定义)

### 背景
FactorFingerprint 仅 13 维, 尾部依赖完全缺失 (全仓库 0 命中), 体制转换仅 HealthMonitor 有弱相关实现。

### 决策
扩展至 21 维, 新增 8 维:
- T1.1 尾部依赖 (4 维): tail_dependence_lower/upper, gpd_shape, hill_estimator
- T1.2 体制转换 (3 维): regime_transition_prob, regime_persistence, regime_ic_diff
- T1.3 综合衍生 (1 维): tail_regime_score

### 关键设计
1. 默认 enable_tail_dependence=False (Copula O(N²) 成本), enable_regime_switching=True
2. Markov 拟合不收敛 → 返回 NaN + 降级硬阈值
3. 路由接入加 enable_multi_dim_routing 开关 (默认 False, 向后兼容)
4. 不扩展 AdaptiveFactorClassifier.classify (仍仅用 ar1)

### 学术依据
- Nelsen (2006), Pickands (1975), Hill (1975), Hamilton (1989)
```

---

## 4. 风险评估 (扩展 ANALYSIS §1.3)

| 风险 | 等级 | 缓解措施 | E1/E2/E3 归属 |
|------|------|---------|--------------|
| 尾部估计小样本不稳定 (GPD/Hill 需 ≥100 极值点) | 高 | `min_extreme_samples=100` 配置, 不足返回 NaN | E1 |
| Markov 拟合不收敛 (EM 局部最优) | 中 | ConvergenceWarning 检测 + 降级硬阈值 + 返回 NaN | E1 |
| Copula 拟合 O(N²) 计算成本 | 中 | `enable_tail_dependence=False` 默认关闭 | E1 |
| 新维度数值范围跨度大 (GPD shape ∈ (-0.5, +∞)) | 中 | 严格遵循 `_derive_sd_score` clip 归一化 | E1 |
| 孤儿函数接入生产路径回归风险 | 高 | `enable_multi_dim_routing=False` 默认关闭; 既有 12 测试针对 `_get_multi_dim_pipeline_weights` 本身 (非 transform 集成), E2 需新增 transform 集成测试 (m4 修订) | E2 |
| `_make_fp` 硬编码 13 维字段 → 扩展维护成本 | 低 | 重构为 `**kwargs` 模式, 自动填充 NaN | E2 |
| statsmodels Markov API 可能版本变化 | 低 | statsmodels 已 REQUIRED (ADR-014), 锁定版本 | E1 |
| 21 维 NamedTuple 性能 (vs dataclass) | 低 | NamedTuple 内存效率优于 dataclass, 保持 | E1 |

---

## 5. 学术依据 (完整引用)

| 维度 | 学术依据 | 引用格式 |
|------|---------|---------|
| 尾部依赖 (Copula) | Nelsen (2006) An Introduction to Copulas, 2nd ed., Springer | Nelsen, R. B. (2006). An Introduction to Copulas (2nd ed.). Springer. |
| GPD 极值理论 | Pickands (1975) Statistical inference using extreme order statistics | Pickands, J. (1975). Statistical inference using extreme order statistics. Annals of Statistics, 3(1), 119-131. |
| Hill 估计量 | Hill (1975) A simple general approach to inference about the tail of a distribution | Hill, B. M. (1975). A simple general approach to inference about the tail of a distribution. *The Annals of Statistics*, 3(5), 1163-1174. |
| Markov 体制转换 | Hamilton (1989) A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle | Hamilton, J. D. (1989). A new approach to the economic analysis of nonstationary time series and the business cycle. Econometrica, 57(2), 357-384. |

---

## 6. v2.6.0 / v3.0.0 T4 衔接

### 6.1 测试基线衔接

| 版本 | passed | skipped | subtests | 增量 |
|------|--------|---------|----------|------|
| v2.6.0 | 918 | 6 | 11 | - |
| v3.0.0 T4 | 934 | 6 | 11 | +16 |
| **v3.0.0 T1 (预期)** | **~962** | 6 | 11 | **+~28** |

### 6.2 文档衔接

- **ANALYSIS_V3.0.0.md §1**: T1 分析 (已完成 v1.1)
- **EXECUTION_V3.0.0_T1.md**: 本文档 (v1.0, 待 review)
- **DECISIONS.md ADR-024**: 待 E3 写入

---

## 7. 待确认项

### 7.1 Markov 拟合实现细节

**问题**: statsmodels `MarkovRegression` 的具体 API 调用方式需在 E1 实施时确认:
- `MarkovRegression(endog, k_regimes=2, switching_ar=False)` 是否合适?
- `smoothed_probabilities` 如何提取 bull/bear 时段?
- `ConvergenceWarning` 的捕获方式?

**计划**: E1 Green 阶段通过最小化实验确认 API, 写入 ADR-024 附录。

### 7.2 IC 计算依赖 (已决策, 见 §1.3 C1 修订)

**决策**: 采用方案 C (一阶差分均值差), 不破坏 `extract_fingerprint` 签名, 语义近似 IC 差异。详见 §1.3 `_compute_regime_ic_diff`。

### 7.3 尾部依赖计算复杂度

**问题**: Copula 经验估计 O(N²) per stock, 50 只股票 × 300 期 = 150000 次比较, 可能较慢。

**方案**:
- 默认 `enable_tail_dependence=False`
- 仅在用户显式开启时计算
- E1 实施时测试性能, 若 >1s 则考虑用 numpy 向量化或 numba

---

## 附录 A: fingerprint.py 调研速查

### A.1 三处必须同步修改

| 位置 | 行号 | 修改内容 |
|------|------|---------|
| NamedTuple 字段声明 | L34-53 | 追加 8 个字段 |
| `to_dict` 方法 | L55-70 | 追加 8 个键值对 |
| `extract_fingerprint` 构造 | L143-157 | 追加 8 个字段赋值 |

### A.2 _derive_sd_score 归一化模式 (新维度必须遵循)

```python
# 1. NaN 守卫
if np.isnan(critical_input): return np.nan
# 2. 归一化到 [0, 1]
norm = np.clip((x + bound) / range, 0, 1)
# 3. 非关键输入 NaN → 0.5 (中性值)
norm = 0.5 if np.isnan(x) else np.clip(x / upper, 0, 1)
# 4. 加权求和 (权重和 = 1.0)
score = w1 * n1 + w2 * n2 + ...
# 5. float 返回
return float(score)
```

### A.3 既有 15 个私有方法清单

| 类型 | 方法 | 行号 |
|------|------|------|
| 时序 (5) | _compute_ar1_median / _compute_rank_autocorr / _test_volatility_clustering / _estimate_half_life / _compute_level_diff_ic_ratio | L164-340 |
| 截面 (5) | _compute_skewness_std / _compute_kurtosis_std / _compute_js_divergence_mean / _compute_missing_cv / _compute_coverage_ratio | L344-421 |
| 衍生 (3) | _derive_sd_score / _derive_complexity_need / _estimate_snr | L425-492 |
| 工具 (1) | _exponential_weights | L496-501 |
| 回退 (1) | _manual_ljungbox | L269-279 |

---

## 附录 B: T1 新维度数学公式速查

### B.1 尾部依赖系数 (Nelsen 2006)

```
λ_L = P(U < q | V < q) = lim_{q→0+} P(U < q | V < q)
λ_U = P(U > q | V > q) = lim_{q→1-} P(U > q | V > q)

经验估计 (k 个极值点):
λ_L ≈ (# {U_i < q, V_i < q}) / (# {V_i < q})
λ_U ≈ (# {U_i > q, V_i > q}) / (# {V_i > q})
```

### B.2 GPD 形状参数 (Pickands 1975)

```
ξ_pickands = (1/log2) * log((X_{(n-k)} - X_{(n-2k)}) / (X_{(n-2k)} - X_{(n-4k)}))

其中 X_{(1)} ≤ X_{(2)} ≤ ... ≤ X_{(n)} 为顺序统计量 (n4 修订: X_{(i)} 表示第 i 小的值)
X_{(n-k)} 为第 (n-k) 顺序统计量 (即上数第 k+1 大的值)
k 为极值点数, 推荐 k = n/4
```

### B.3 Hill 估计量 (Hill 1975)

```
α_hill = (1/k) * Σ_{i=1}^{k} log(X_{(n-i+1)} / X_{(n-k)})
ξ_hill = 1/α_hill

其中 X_{(n-k)} 为阈值, k 为极值点数
正尾部 (上尾) 估计, ξ > 0 表示重尾
```

### B.4 Markov 转移概率 (Hamilton 1989)

```
两状态 Markov 链: s_t ∈ {0 (bear), 1 (bull)}
转移矩阵 P = [[p_00, p_01], [p_10, p_11]]
  p_01 = P(s_t=1 | s_{t-1}=0)  (bear → bull)
  p_10 = P(s_t=0 | s_{t-1}=1)  (bull → bear)

持续期:
  E[持续期_bull] = 1 / p_10
  E[持续期_bear] = 1 / p_01

statsmodels API:
  model = MarkovRegression(endog, k_regimes=2, switching_ar=False)
  result = model.fit()
  result.regime_transitions  # 转移矩阵
```

---

## 修订日志

| 版本 | 日期 | 修订内容 |
|------|------|---------|
| v1.0 | 2026-07-04 | 初稿, 基于 ANALYSIS_V3.0.0.md §1 + fingerprint.py 调研报告 |
| v1.1 | 2026-07-04 | review 修订: 1 CRITICAL (C1: regime_ic_diff 方案 C 提前至 §1.3) + 3 MAJOR (M1: T1.3 标注 "(新)"; M2: tail_regime_score 公式简化; M3: transform 行号待确认) + 4 MINOR (m1: enable_regime_switching 默认 False; m2: 测试类名 Dims 复数; m3: ADR-024 编号已验证; m4: 风险表澄清既有测试) + 4 NIT (n1: ADR-014 标题; n2: _manual_ljungbox 保留理由; n3: Hill 期刊名; n4: Pickands 公式说明) |
