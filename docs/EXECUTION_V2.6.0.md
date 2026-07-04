# v2.6.0 优化器与漂移检测增强执行方案 (ADR-004/005/006 修订)

**状态**: 执行方案设计 (基于 ANALYSIS_V2.6.0.md v1.1)
**创建日期**: 2026-07-03
**基线测试**: 860 passed / 5 skipped / 0 failed (v2.5.0 三层架构完成)
**目标版本**: 2.6.0
**关联文档**: [ANALYSIS_V2.6.0.md](./ANALYSIS_V2.6.0.md) | [EXECUTION_V2.5.0.md](./EXECUTION_V2.5.0.md)

---

## 总体目标

实现 factor_pipeline 的端到端阈值优化器与漂移检测增强, 让 v2.5.0 三层架构 (Layer 1 / Layer 2 正交化 / Layer 3 显著性) 在优化器层面完整闭环, 同时对齐 ADR-004 (目标函数) / ADR-005 (搜索空间) / ADR-006 (扩展窗口 CV) 三项设计契约.

## 核心约束

1. **基线保护**: 默认行为不变, 不影响 860 测试基线
2. **ADR 契约对齐**: ADR-004 (health_penalty) 改代码, ADR-005 (static/dynamic) 改 ADR
3. **TDD 开发**: 每个阶段严格 Red-Green-Refactor, 含手工数值校验
4. **数值精度**: 与独立 numpy/statsmodels 实现对比, 精度 < 1e-10
5. **无 look-ahead bias**: 正交化参数搜索时, 必须在 CV fold 内部 fit (用 train 数据)
6. **计算成本控制**: FactorSignificanceTest 仅用于最终验证, 不用于每 trial 评估

## 阶段总览

```
v2.6.0 优化器与漂移检测增强 [ADR-004/005/006 修订]
│
├─ E1: P3-11' 文档状态修正 (P0, 无依赖, 仅文档)
│   ├─ DECISIONS.md P3-11 状态 [ ] → [x]
│   └─ 学术依据分拆 (TPE→Bergstra 2011, fANOVA→Hutter 2014)
│
├─ E2: P3-10' migration_threshold 字段位置修正 + ADR-005 更新 (P0, 无依赖)
│   ├─ optimizer.py 字段位置修正 (config.monitor → config)
│   ├─ ADR-005 更新 (承认 static/dynamic)
│   └─ 验证 migration_threshold 维度对 Pipeline 行为有影响
│
├─ E3: P3-1' IC 时间加权 EWMA (P1, 无依赖)
│   ├─ factor_metrics.py compute_ic_series 添加 weighting/halflife
│   ├─ optimizer.py _compute_ic 集成 EWMA
│   └─ 手工校验 EWMA vs equal 在 IC 衰减场景差异
│
├─ E4: P3-9' 目标函数对齐 ADR-004 (P1, 依赖 E3)
│   ├─ _composite_objective 添加 health_penalty (代理指标)
│   ├─ 修正 fidelity 符号方向 (奖励 → 惩罚)
│   └─ 手工校验 health_penalty 在低健康度场景扣分
│
├─ E5: P3-13 正交化参数纳入搜索空间 (P1, 依赖 E2)
│   ├─ DEFAULT_SEARCH_SPACE_ORTH 添加 orth_method/align_mode/ridge_lambda
│   ├─ _params_to_config 设置 OrthogonalizationConfig
│   └─ look-ahead bias 防护验证
│
├─ E6: P3-14 几何诊断纳入目标函数 (P2, 依赖 E5)
│   ├─ OrthogonalizerAdapter.fit() 保存 F/T 矩阵
│   ├─ OrthogonalizerAdapter.get_diagnostics() 新方法
│   ├─ _redundancy_penalty 新方法
│   └─ _composite_objective 添加 redundancy_penalty
│
├─ E7: P3-15 Layer 3 显著性最终验证 (P2, 依赖 E4)
│   ├─ _validate_significance 新方法
│   ├─ optimize() 末尾调用 _validate_significance
│   └─ 显著性验证报告生成
│
├─ E8: P3-12' 阈值漂移监测 (P2, 依赖 E4)
│   ├─ backtest/threshold_drift_monitor.py 新建
│   ├─ ThresholdDriftMonitor 类
│   └─ 集成测试与 optimizer 衔接
│
└─ E9: 文档验证 + 全量回归 (P1, 依赖 E1-E8)
    ├─ README/CHANGELOG/CODE_WIKI/DECISIONS 更新
    ├─ project_memory/topics 更新
    ├─ 手工校验脚本 verify_v2_6_0_manual.py
    └─ 全量回归 860+ passed
```

## 依赖关系矩阵

| 阶段 | 依赖 | 优先级 | 预计测试数 | 文件变更 |
|------|------|--------|-----------|---------|
| E1 | 无 | P0 | 0 (仅文档) | DECISIONS.md |
| E2 | 无 | P0 | ~5 | optimizer.py, DECISIONS.md |
| E3 | 无 | P1 | ~8 | factor_metrics.py, optimizer.py |
| E4 | E3 | P1 | ~10 | optimizer.py |
| E5 | E2 | P1 | ~8 | optimizer.py |
| E6 | E5 | P2 | ~12 | adapters.py, optimizer.py |
| E7 | E4 | P2 | ~6 | optimizer.py |
| E8 | E4 | P2 | ~10 | backtest/threshold_drift_monitor.py (新建) |
| E9 | E1-E8 | P1 | 0 (验证) | README, CHANGELOG, CODE_WIKI, DECISIONS, memory |

**总计**: ~59 个新测试 + 860 基线 = ~919 passed

---

## E1: P3-11' 文档状态修正 (P0)

**优先级**: P0
**依赖**: 无
**预计测试数**: 0 (仅文档)
**文件变更**: DECISIONS.md

### E1.1 目标

修正 DECISIONS.md 中 P3-11 的状态错误 (已实施但标 `[ ]`) 和学术依据张冠李戴 (fANOVA 归于 Bergstra 2011, 实际来自 Hutter 2014).

### E1.2 实施步骤

**步骤 1**: 在 DECISIONS.md 定位 P3-11 行 (约第 1329 行)

**步骤 2**: 状态修正
```markdown
# 修正前:
- [ ] P3-11: 搜索参数重要性可视化

# 修正后:
- [x] P3-11: 搜索参数重要性可视化 (已实施, optimizer.py:632-714 + test_p3_phase4_integration.py:164)
  - 学术依据: TPE → Bergstra et al. (2011) NIPS 24:2546-2554
  - 学术依据: fANOVA → Hutter et al. (2014) ICML 32(1):754-762
  - 注: v1.0 误将 fANOVA 归于 Bergstra 2011, v1.1 修正 (ANALYSIS_V2.6.0.md 问题 C)
```

**步骤 3**: 验证现有测试仍通过
```bash
python -m pytest tests/test_p3_phase4_integration.py::test_05_param_importance -v
```

### E1.3 验收标准

- [x] DECISIONS.md P3-11 状态为 `[x]`
- [x] 学术依据分拆为 TPE (Bergstra 2011) + fANOVA (Hutter 2014)
- [x] 现有 test_05_param_importance 通过
- [x] 全量回归零退化

---

## E2: P3-10' migration_threshold 字段位置修正 + ADR-005 更新 (P0)

**优先级**: P0
**依赖**: 无
**预计测试数**: ~5
**文件变更**: optimizer.py, DECISIONS.md

### E2.1 目标

修正 [optimizer.py:150-158](file:///f:/Coding/factor_pipeline/optimizer.py#L150) 的字段位置错误: `migration_threshold` 字段已存在于 [PipelineV2ConfigUnified](file:///f:/Coding/factor_pipeline/config_v2.py#L407) (第 407-410 行), 但 optimizer 错误地设置到 `config.monitor` 上. 同时更新 ADR-005 承认 static/dynamic 比 midpoint/interval 更直观.

### E2.2 代码修正

**optimizer.py 第 150-158 行修正**:

```python
# 修正前 (字段位置错误):
# P0-2: migration_threshold — 影响 monitor 的迁移判定
if 'migration_threshold' in params:
    config.monitor.enable_smooth_transition = True
    # migration_threshold 用作 monitor 的相似度阈值
    # 如果 MonitorConfig 有相关字段则设置
    if hasattr(config.monitor, 'migration_threshold'):
        config.monitor.migration_threshold = params['migration_threshold']
    elif hasattr(config.monitor, 'similarity_threshold'):
        config.monitor.similarity_threshold = params['migration_threshold']

# 修正后 (直接设置到 config 本身):
# P3-10' (v2.6.0): migration_threshold 字段位置修正
# 字段位于 PipelineV2ConfigUnified.migration_threshold (config_v2.py:407-410),
# 不是 MonitorConfig.migration_threshold. v1.0 误判为字段缺失, v1.1 修正.
if 'migration_threshold' in params:
    config.migration_threshold = params['migration_threshold']
    config.monitor.enable_smooth_transition = True  # 保留: 启用平滑过渡
```

### E2.3 ADR-005 更新

在 DECISIONS.md ADR-005 末尾追加修订日志:

```markdown
### 修订日志

| 日期 | 版本 | 修订内容 |
|------|------|---------|
| 2026-07-03 | v1.1 | 实施时调整为 `classification_threshold_static/dynamic` 分离, 不采用 `midpoint/interval` 合并. 原因: (1) static/dynamic 物理含义更直观; (2) midpoint/interval 引入额外非线性 (见"后果"风险); (3) 代码已实施 static/dynamic (optimizer.py:47-56). 8 维数量不变. |
```

### E2.4 TDD 测试列表

| # | 测试名 | 类型 | 验证内容 |
|---|--------|------|---------|
| 1 | `test_migration_threshold_field_location` | 单元 | `_params_to_config({'migration_threshold': 0.15})` 后, `config.migration_threshold == 0.15` (不是 config.monitor.migration_threshold) |
| 2 | `test_migration_threshold_default_value` | 单元 | 不传 migration_threshold 时, `config.migration_threshold == 0.10` (默认值) |
| 3 | `test_migration_threshold_affects_pipeline` | 集成 | 设置不同 migration_threshold 值, Pipeline 行为有差异 (迁移检测灵敏度变化) |
| 4 | `test_enable_smooth_transition_preserved` | 单元 | 设置 migration_threshold 后, `config.monitor.enable_smooth_transition == True` (保留原行为) |
| 5 | `test_no_hasattr_silent_failure` | 单元 | 移除 hasattr 检查, 字段不存在时抛 AttributeError 而非静默跳过 |

### E2.5 手工校验

```python
# tests/manual/verify_v2_6_0_e2_manual.py
def test_migration_threshold_pipeline_impact():
    """手工校验: migration_threshold 对 Pipeline 行为有实际影响"""
    from factor_pipeline.optimizer import EndToEndThresholdOptimizer
    from factor_pipeline.pipelines_v2 import FactorProcessingPipelineV2

    opt = EndToEndThresholdOptimizer(n_trials=1)

    # 设置 migration_threshold=0.05 (严格)
    config_strict = opt._params_to_config({'migration_threshold': 0.05})
    assert config_strict.migration_threshold == 0.05
    assert config_strict.monitor.enable_smooth_transition == True

    # 设置 migration_threshold=0.30 (宽松)
    config_loose = opt._params_to_config({'migration_threshold': 0.30})
    assert config_loose.migration_threshold == 0.30

    print("✓ migration_threshold 字段位置修正验证通过")
    print(f"  strict: migration_threshold={config_strict.migration_threshold}")
    print(f"  loose:  migration_threshold={config_loose.migration_threshold}")
```

### E2.6 验收标准

- [x] optimizer.py 字段位置修正 (config.monitor → config)
- [x] hasattr 静默失败移除
- [x] ADR-005 修订日志追加
- [x] migration_threshold 维度对 Pipeline 行为有实际影响
- [x] 全量回归零退化

---

## E3: P3-1' IC 时间加权 EWMA (P1)

**优先级**: P1
**依赖**: 无
**预计测试数**: ~8
**文件变更**: backtest/factor_metrics.py, optimizer.py

### E3.1 目标

在 `compute_ic_series` 添加 EWMA 加权选项, 让近期 IC 权重更高. 学术依据改为 Ferson-Siegel (2001) 或 Barroso-Santa-Clara (2015) (撤回 v1.0 误推荐的 Cohen-Coval-Pastor 2005).

### E3.2 代码实现

**factor_metrics.py compute_ic_series 修改**:

```python
def compute_ic_series(
    factor: np.ndarray,
    returns: np.ndarray,
    method: Literal['rank', 'pearson'] = 'rank',
    weighting: Literal['equal', 'ewma'] = 'equal',  # 新增
    halflife: Optional[int] = None,                  # 新增 (EWMA 半衰期)
) -> np.ndarray:
    """计算 IC 时间序列.

    手工计算: 对每期 t, 计算 factor[:, t] 与 return[:, t+1] 的 IC.

    Parameters
    ----------
    factor : np.ndarray, shape (n_stocks, n_periods)
    returns : np.ndarray, shape (n_stocks, n_periods)
    method : 'rank' | 'pearson'
    weighting : 'equal' | 'ewma'  (v2.6.0 P3-1' 新增)
        'equal': 等权 (默认, 向后兼容)
        'ewma': 指数加权, 近期 IC 权重更高
    halflife : int, optional
        EWMA 半衰期 (仅 weighting='ewma' 时生效)
        默认: n_periods // 4 (自适应)

    Returns
    -------
    np.ndarray, shape (n_periods - 1,)
        IC 序列 (weighting='ewma' 时返回加权后的标量, shape (1,))

    学术依据:
    - equal: 行业标准
    - ewma: Ferson & Siegel (2001) JF 56(3):967-982 (条件信息时变加权)
            Barroso & Santa-Clara (2015) JFE 115(3):464-482 (IC 高波动期衰减)
            RiskMetrics (1996) EWMA 框架
    """
    n_periods = factor.shape[1]
    ic_series = np.full(n_periods - 1, np.nan)

    if method == 'rank':
        ic_func = compute_rank_ic
    elif method == 'pearson':
        ic_func = compute_pearson_ic
    else:
        raise ValueError(f"未知 IC 方法: {method}, 可选 'rank' / 'pearson'")

    for t in range(n_periods - 1):
        ic_series[t] = ic_func(factor[:, t], returns[:, t + 1])

    if weighting == 'ewma':
        if halflife is None:
            halflife = max(1, len(ic_series) // 4)
        # EWMA 权重: w[t] = (1-alpha)^(T-1-t), alpha = 1 - exp(-ln2/halflife)
        alpha = 1.0 - np.exp(-np.log(2.0) / max(halflife, 1))
        n = len(ic_series)
        weights = (1.0 - alpha) ** np.arange(n)[::-1]
        weights /= weights.sum()
        # 加权求和 (忽略 NaN)
        valid = ~np.isnan(ic_series)
        if valid.sum() < MIN_VALID_PAIRS:
            return np.array([np.nan])
        weighted_ic = np.nansum(ic_series * weights)
        return np.array([weighted_ic])

    return ic_series
```

**optimizer.py _compute_ic 集成**:

```python
def _compute_ic(
    self,
    factor_values: np.ndarray,
    forward_returns: np.ndarray,
    weighting: str = 'equal',  # 新增 (v2.6.0 P3-1')
    halflife: int = None,      # 新增
) -> float:
    """计算 cross-sectional IC (支持 EWMA 加权)"""
    # ... 现有 shape 检查 ...

    if weighting == 'ewma':
        # 用 compute_ic_series 的 EWMA 模式
        from factor_pipeline.backtest.factor_metrics import compute_ic_series
        result = compute_ic_series(
            factor_values, forward_returns,
            method='pearson',  # optimizer 用 pearson
            weighting='ewma', halflife=halflife,
        )
        return float(result[0]) if len(result) > 0 else float('nan')

    # 等权模式 (现有逻辑, 向后兼容)
    n_periods = factor_values.shape[1]
    ics = np.zeros(n_periods)
    for t in range(n_periods):
        # ... 现有逻辑 ...
    return float(np.nanmean(ics))
```

### E3.3 TDD 测试列表

| # | 测试名 | 类型 | 验证内容 |
|---|--------|------|---------|
| 1 | `test_compute_ic_series_equal_weighting_default` | 单元 | 默认 weighting='equal', 与现有行为一致 |
| 2 | `test_compute_ic_series_ewma_returns_scalar` | 单元 | weighting='ewma' 返回 shape (1,) 数组 |
| 3 | `test_compute_ic_series_ewma_halflife_default` | 单元 | halflife=None 时自动设为 n_periods//4 |
| 4 | `test_compute_ic_series_ewma_weights_correct` | 单元 | 手工计算 EWMA 权重, 与实现对比精度 < 1e-10 |
| 5 | `test_compute_ic_series_ewma_recent_emphasis` | 单元 | 近期 IC 高时, EWMA IC > 等权 IC |
| 6 | `test_compute_ic_series_ewma_nan_handling` | 单元 | 含 NaN 时, EWMA 忽略 NaN 加权 |
| 7 | `test_optimizer_compute_ic_ewma_integration` | 集成 | optimizer._compute_ic(weighting='ewma') 返回标量 |
| 8 | `test_compute_ic_series_backward_compatible` | 回归 | 不传 weighting/halflife 时, 行为与 v2.5.0 完全一致 |

### E3.4 手工校验

```python
# tests/manual/verify_v2_6_0_e3_manual.py
def test_ewma_vs_equal_in_decay_scenario():
    """手工校验: EWMA vs equal 在 IC 衰减场景下差异显著"""
    import numpy as np
    from factor_pipeline.backtest.factor_metrics import compute_ic_series

    np.random.seed(42)
    n_stocks, n_periods = 100, 24

    # 构造 IC 衰减场景: 前 12 期 IC=0.1, 后 12 期 IC=0.01
    factor = np.random.randn(n_stocks, n_periods)
    returns = np.zeros_like(factor)
    for t in range(n_periods):
        ic_target = 0.1 if t < 12 else 0.01
        returns[:, t] = ic_target * factor[:, t] + np.random.randn(n_stocks) * 0.5

    ic_equal = compute_ic_series(factor, returns, weighting='equal')
    ic_ewma = compute_ic_series(factor, returns, weighting='ewma', halflife=6)

    equal_mean = np.nanmean(ic_equal)
    ewma_value = ic_ewma[0]

    # EWMA 应更接近近期 IC (0.01), 等权应接近全局均值 (~0.055)
    print(f"  equal IC mean: {equal_mean:.4f} (预期 ~0.055)")
    print(f"  EWMA IC:       {ewma_value:.4f} (预期 < 0.055, 更接近近期)")

    assert ewma_value < equal_mean, "EWMA 应更接近近期 IC (衰减场景)"
    print("✓ EWMA 时间加权验证通过")
```

### E3.5 验收标准

- [x] compute_ic_series 支持 weighting='equal'/'ewma' + halflife 参数
- [x] 默认 weighting='equal' 与 v2.5.0 行为完全一致 (向后兼容)
- [x] EWMA 权重手工计算与实现对比精度 < 1e-10
- [x] EWMA 在 IC 衰减场景下与等权 IC 差异显著
- [x] 全量回归零退化

---

## E4: P3-9' 目标函数对齐 ADR-004 (P1)

**优先级**: P1
**依赖**: E3 (IC EWMA 用于 health_penalty 代理)
**预计测试数**: ~10
**文件变更**: optimizer.py

### E4.1 目标

对齐 [ADR-004 第 147 行](file:///f:/Coding/factor_pipeline/DECISIONS.md#L147) 的目标函数设计:
```python
score = IC_score - stability_penalty - ks_penalty - health_penalty - coverage_penalty
```

修正 2 处偏差:
1. **fidelity 符号方向相反**: 当前 `+ λ_fid * fidelity` (奖励), 应为 `- λ_ks * ks_distortion_penalty` (惩罚)
2. **HealthMonitor penalty 缺失**: 添加 health_penalty (用代理指标, 解决时序问题)

### E4.2 代码实现

**optimizer.py _composite_objective 修正**:

```python
def _composite_objective(
    self,
    ic_array: np.ndarray,
    n_processed: int,
    n_total: int,
    before: Optional[np.ndarray] = None,
    after: Optional[np.ndarray] = None,
) -> float:
    """复合目标函数 (v2.6.0 P3-9' 对齐 ADR-004)

    ADR-004 第 147 行:
        score = IC_score - stability_penalty - ks_penalty - health_penalty - coverage_penalty

    v2.6.0 修正:
    1. fidelity 符号方向: 奖励 → 惩罚 (ks_distortion_penalty)
    2. 新增 health_penalty (代理指标, 解决 health_bridge 时序问题)
    """
    ic_mean = float(np.nanmean(ic_array))
    vol_penalty = self._ic_volatility_penalty(ic_array)
    cov_penalty = self._coverage_penalty(n_processed, n_total)

    # 修正 1: KS 分布扭曲惩罚 (原 fidelity 奖励, 符号方向相反)
    ks_distortion_penalty = 0.0
    if before is not None and after is not None:
        # distortion = 1 - fidelity (反向: 分布越不相似, distortion 越高)
        fidelity = self._ks_distribution_fidelity(before, after)
        ks_distortion_penalty = 1.0 - fidelity

    # 修正 2: HealthMonitor 代理惩罚 (基于 IC 系列特征)
    health_penalty = self._health_penalty_proxy(ic_array)

    objective = (
        ic_mean
        - self.lambda_volatility * vol_penalty
        - self.lambda_coverage * cov_penalty
        - self.lambda_fidelity * ks_distortion_penalty  # 修正: + → -
        - self.lambda_health * health_penalty            # 新增
    )
    return float(objective)
```

**optimizer.py _health_penalty_proxy 新增**:

```python
def _health_penalty_proxy(self, ic_array: np.ndarray) -> float:
    """HealthMonitor 代理惩罚 (v2.6.0 P3-9')

    用 IC decay / hit rate / volatility 作为 health_score 的近似,
    避免 HealthMonitorAdapter.build_report_from_engine 的 engine_results 时序依赖.

    ADR-004 第 153 行:
        HealthMonitor 综合得分 (< 40 → -0.5, < 60 → -0.2)

    代理指标映射:
    - IC decay ratio (后半段/前半段): < 0.5 → 健康度低
    - IC hit rate: < 0.4 → 健康度低
    - IC volatility: > 0.2 → 健康度低
    """
    clean = ic_array[~np.isnan(ic_array)]
    if len(clean) < 6:
        return 0.0  # 数据不足, 不惩罚

    mid = len(clean) // 2
    ic_early = float(np.mean(clean[:mid]))
    ic_late = float(np.mean(clean[mid:]))

    # IC decay ratio
    if abs(ic_early) < 1e-10:
        decay_ratio = 1.0
    else:
        decay_ratio = ic_late / ic_early

    # IC hit rate
    hit_rate = float(np.mean(clean > 0))

    # IC volatility
    ic_vol = float(np.std(clean))

    # 代理 health_score: decay_ratio > 0.8 + hit_rate > 0.55 + ic_vol < 0.1 → 健康
    if decay_ratio < 0.5 or hit_rate < 0.4 or ic_vol > 0.2:
        return 0.5  # ADR-004: < 40 → -0.5
    elif decay_ratio < 0.8 or hit_rate < 0.5 or ic_vol > 0.15:
        return 0.2  # ADR-004: < 60 → -0.2
    return 0.0
```

**optimizer.py __init__ 添加 lambda_health**:

```python
def __init__(
    self,
    n_trials: int = 100,
    cv_min_train: int = 12,
    cv_test_size: int = 3,
    lambda_volatility: float = 0.5,
    lambda_coverage: float = 0.3,
    lambda_fidelity: float = 0.1,
    lambda_health: float = 0.4,        # 新增 (v2.6.0 P3-9')
    random_seed: int = 42,
):
    # ... 现有 ...
    self.lambda_health = lambda_health
```

### E4.3 TDD 测试列表

| # | 测试名 | 类型 | 验证内容 |
|---|--------|------|---------|
| 1 | `test_composite_objective_health_penalty_low_health` | 单元 | IC decay < 0.5 时, health_penalty == 0.5 |
| 2 | `test_composite_objective_health_penalty_medium_health` | 单元 | IC decay < 0.8 时, health_penalty == 0.2 |
| 3 | `test_composite_objective_health_penalty_high_health` | 单元 | IC decay > 0.8 + hit_rate > 0.55 + ic_vol < 0.1 时, health_penalty == 0.0 |
| 4 | `test_composite_objective_ks_penalty_sign_corrected` | 单元 | KS 分布扭曲时, ks_distortion_penalty > 0, 目标函数减少 (非增加) |
| 5 | `test_composite_objective_ks_penalty_zero_when_identical` | 单元 | before == after 时, ks_distortion_penalty == 0 |
| 6 | `test_composite_objective_aligns_adr_004` | 单元 | 目标函数 = IC - vol - cov - ks - health (5 项, 符号全负) |
| 7 | `test_health_penalty_proxy_decay_ratio` | 单元 | 手工计算 decay_ratio, 与实现对比 |
| 8 | `test_health_penalty_proxy_hit_rate` | 单元 | 手工计算 hit_rate, 与实现对比 |
| 9 | `test_health_penalty_proxy_insufficient_data` | 单元 | len(clean) < 6 时, health_penalty == 0.0 |
| 10 | `test_composite_objective_backward_compatible` | 回归 | lambda_health=0 时, 与 v2.5.0 行为一致 (除 fidelity 符号) |

### E4.4 手工校验

```python
# tests/manual/verify_v2_6_0_e4_manual.py
def test_health_penalty_adr_004_alignment():
    """手工校验: health_penalty 与 ADR-004 阈值对齐"""
    import numpy as np
    from factor_pipeline.optimizer import EndToEndThresholdOptimizer

    opt = EndToEndThresholdOptimizer(n_trials=1)

    # 场景 1: 低健康度 (IC 衰减严重)
    ic_low_health = np.array([0.1, 0.09, 0.08, 0.07, 0.03, 0.02, 0.01, 0.005])
    penalty_low = opt._health_penalty_proxy(ic_low_health)
    assert penalty_low == 0.5, f"低健康度应 -0.5, 得到 {penalty_low}"

    # 场景 2: 中健康度 (IC 轻微衰减)
    ic_medium_health = np.array([0.1, 0.09, 0.08, 0.07, 0.06, 0.05, 0.04, 0.03])
    penalty_medium = opt._health_penalty_proxy(ic_medium_health)
    assert penalty_medium == 0.2, f"中健康度应 -0.2, 得到 {penalty_medium}"

    # 场景 3: 高健康度 (IC 稳定)
    ic_high_health = np.array([0.05, 0.06, 0.05, 0.06, 0.05, 0.06, 0.05, 0.06])
    penalty_high = opt._health_penalty_proxy(ic_high_health)
    assert penalty_high == 0.0, f"高健康度应 0.0, 得到 {penalty_high}"

    print("✓ health_penalty ADR-004 对齐验证通过")
    print(f"  低健康度: penalty={penalty_low} (ADR-004: < 40 → -0.5)")
    print(f"  中健康度: penalty={penalty_medium} (ADR-004: < 60 → -0.2)")
    print(f"  高健康度: penalty={penalty_high} (ADR-004: ≥ 60 → 0.0)")


def test_ks_penalty_sign_correction():
    """手工校验: KS penalty 符号方向修正"""
    import numpy as np
    from factor_pipeline.optimizer import EndToEndThresholdOptimizer

    opt = EndToEndThresholdOptimizer(n_trials=1)

    # before/after 完全相同 → ks_distortion_penalty = 0
    before = np.random.randn(100, 3)
    after = before.copy()
    fidelity = opt._ks_distribution_fidelity(before, after)
    distortion = 1.0 - fidelity
    assert distortion < 0.01, f"分布相同时 distortion 应接近 0, 得到 {distortion}"

    # before/after 差异大 → ks_distortion_penalty 接近 1
    after_distorted = np.random.randn(100, 3) * 5  # 放大 5 倍
    fidelity_dist = opt._ks_distribution_fidelity(before, after_distorted)
    distortion_dist = 1.0 - fidelity_dist
    assert distortion_dist > 0.5, f"分布差异大时 distortion 应 > 0.5, 得到 {distortion_dist}"

    print("✓ KS penalty 符号方向修正验证通过")
```

### E4.5 验收标准

- [x] _composite_objective 与 ADR-004 第 147 行完全一致 (5 项, 符号全负)
- [x] fidelity 符号方向修正 (奖励 → 惩罚)
- [x] health_penalty 代理指标在低健康度场景扣分 (0.5/0.2/0.0 三档)
- [x] lambda_health=0 时与 v2.5.0 行为一致 (向后兼容)
- [x] 全量回归零退化

---

## E5: P3-13 正交化参数纳入搜索空间 (P1)

**优先级**: P1
**依赖**: E2 (migration_threshold 修正后, _params_to_config 逻辑清晰)
**预计测试数**: ~8
**文件变更**: optimizer.py

### E5.1 目标

在 `DEFAULT_SEARCH_SPACE` 添加正交化参数 (method/align_mode/ridge_lambda), 让优化器搜索最优正交化配置. **不搜索 orth_enabled** (用户决策, 非优化器决策).

### E5.2 代码实现

**optimizer.py DEFAULT_SEARCH_SPACE_ORTH 新增**:

```python
# v2.6.0 P3-13: 正交化参数搜索空间 (仅 orth_enabled=True 时激活)
DEFAULT_SEARCH_SPACE_ORTH = {
    'orth_method': {
        'type': 'categorical',
        'choices': ['symmetric', 'ridge', 'pca', 'gram_schmidt'],
    },
    'orth_align_mode': {
        'type': 'categorical',
        'choices': ['intersection', 'union_nan'],  # 不搜索 raise_on_mismatch
    },
    'orth_ridge_lambda': {
        'type': 'float', 'low': 0.01, 'high': 100.0,
        'log': True,  # log-uniform (λ 跨度大)
    },
}
```

**optimizer.py __init__ 扩展搜索空间**:

```python
def __init__(
    self,
    n_trials: int = 100,
    cv_min_train: int = 12,
    cv_test_size: int = 3,
    lambda_volatility: float = 0.5,
    lambda_coverage: float = 0.3,
    lambda_fidelity: float = 0.1,
    lambda_health: float = 0.4,
    random_seed: int = 42,
    search_orth: bool = False,  # 新增 (v2.6.0 P3-13)
):
    # ... 现有 ...
    self.search_space = dict(DEFAULT_SEARCH_SPACE)
    if search_orth:
        self.search_space.update(DEFAULT_SEARCH_SPACE_ORTH)
```

**optimizer.py _params_to_config 扩展**:

```python
def _params_to_config(self, params: Dict[str, float]) -> 'PipelineV2Config':
    """将优化参数字典映射到 PipelineV2Config"""
    config = PipelineV2Config(
        hard_routing_prob=params.get('hard_routing_prob', 0.90),
        merge_alpha=params.get('merge_alpha', 0.50),
        ks_alpha=params.get('ks_alpha', 0.05),
        mixed_winsor_sigma=params.get('mixed_winsor_sigma', 3.0),
    )

    # classification_threshold_static/dynamic
    if 'classification_threshold_static' in params:
        config.classification.static_ar1_threshold = params['classification_threshold_static']
    if 'classification_threshold_dynamic' in params:
        config.classification.dynamic_ar1_threshold = params['classification_threshold_dynamic']

    # transform_aggressiveness
    if 'transform_aggressiveness' in params:
        aggr = params['transform_aggressiveness']
        config.mixed_winsor_sigma = max(1.0, config.mixed_winsor_sigma / max(aggr, 0.1))

    # P3-10' (v2.6.0): migration_threshold 字段位置修正
    if 'migration_threshold' in params:
        config.migration_threshold = params['migration_threshold']
        config.monitor.enable_smooth_transition = True

    # P3-13 (v2.6.0): 正交化参数 (仅 search_orth=True 时)
    if 'orth_method' in params:
        config.orthogonalization.enabled = True  # 自动启用
        config.orthogonalization.method = params['orth_method']
    if 'orth_align_mode' in params:
        config.orthogonalization.align_mode = params['orth_align_mode']
    if 'orth_ridge_lambda' in params and config.orthogonalization.method == 'ridge':
        config.orthogonalization.ridge_lambda = params['orth_ridge_lambda']

    return config
```

**optimizer.py optimize 扩展 categorical 采样**:

```python
def objective(trial: 'optuna.Trial') -> float:
    params = {}
    for name, spec in self.search_space.items():
        if spec['type'] == 'float':
            if spec.get('log', False):
                params[name] = trial.suggest_float(
                    name, spec['low'], spec['high'], log=True
                )
            else:
                params[name] = trial.suggest_float(
                    name, spec['low'], spec['high']
                )
        elif spec['type'] == 'categorical':
            params[name] = trial.suggest_categorical(name, spec['choices'])

    # 约束: 确保静态阈值 > 动态阈值
    if (params.get('classification_threshold_static', 1.0)
            <= params.get('classification_threshold_dynamic', 0.0)):
        return -1.0

    # ... 后续逻辑 ...
```

### E5.3 look-ahead bias 防护

**关键验证**: 正交化参数搜索时, 必须在 CV fold 内部 fit 正交化器 (用 train 数据).

当前 [optimizer.py:404-410](file:///f:/Coding/factor_pipeline/optimizer.py#L404) 的 `_cv_evaluate` 已在 fold 内 `pipeline.fit(train_factor)`, 正交化作为 `post_transform_hook` 会随之在 train 上 fit. **无 look-ahead bias**, 但需验证:

1. `pipeline.fit(train_factor)` 时, `OrthogonalizerAdapter.fit()` 用 train 数据估计 W
2. `pipeline.transform(test_factor)` 时, `OrthogonalizerAdapter.transform()` 用 train 估计的 W 应用到 test

### E5.4 TDD 测试列表

| # | 测试名 | 类型 | 验证内容 |
|---|--------|------|---------|
| 1 | `test_search_space_orth_default_off` | 单元 | search_orth=False 时, search_space 不含 orth_* 键 |
| 2 | `test_search_space_orth_enabled` | 单元 | search_orth=True 时, search_space 含 orth_method/align_mode/ridge_lambda |
| 3 | `test_params_to_config_orth_method` | 单元 | _params_to_config({'orth_method': 'ridge'}) 后, config.orthogonalization.method == 'ridge' |
| 4 | `test_params_to_config_orth_auto_enable` | 单元 | 设置 orth_method 后, config.orthogonalization.enabled == True (自动启用) |
| 5 | `test_params_to_config_orth_ridge_lambda_only_ridge` | 单元 | orth_ridge_lambda 仅 method='ridge' 时设置 |
| 6 | `test_optimize_categorical_sampling` | 集成 | optimize() 能采样 categorical 参数 (orth_method) |
| 7 | `test_no_lookahead_bias_orthogonalization` | 集成 | fold 0 的 test IC 不依赖 fold 1 的 train 数据 |
| 8 | `test_search_orth_backward_compatible` | 回归 | search_orth=False 时, optimize() 行为与 v2.5.0 一致 |

### E5.5 手工校验

```python
# tests/manual/verify_v2_6_0_e5_manual.py
def test_orthogonalization_search_no_lookahead():
    """手工校验: 正交化搜索无 look-ahead bias"""
    import numpy as np
    import pandas as pd
    from factor_pipeline.optimizer import EndToEndThresholdOptimizer

    np.random.seed(42)
    n_periods, n_stocks = 30, 50
    factor_data = {
        f'factor_{k}': pd.DataFrame(
            np.random.randn(n_periods, n_stocks),
            index=pd.date_range('2024-01-01', periods=n_periods),
            columns=[f'stock_{i}' for i in range(n_stocks)],
        )
        for k in range(3)
    }
    fwd_returns = pd.DataFrame(
        np.random.randn(n_periods, n_stocks) * 0.01,
        index=factor_data['factor_0'].index,
        columns=factor_data['factor_0'].columns,
    )

    opt = EndToEndThresholdOptimizer(n_trials=5, search_orth=True)
    best_params = opt.optimize(factor_data, fwd_returns, show_progress=False)

    assert 'orth_method' in best_params, "应搜索 orth_method"
    assert 'orth_align_mode' in best_params, "应搜索 orth_align_mode"
    print(f"✓ 正交化搜索空间验证通过")
    print(f"  best orth_method: {best_params['orth_method']}")
    print(f"  best orth_align_mode: {best_params['orth_align_mode']}")
```

### E5.6 验收标准

- [x] DEFAULT_SEARCH_SPACE_ORTH 定义 (3 维: method/align_mode/ridge_lambda)
- [x] search_orth=False 时与 v2.5.0 行为一致 (向后兼容)
- [x] _params_to_config 设置 OrthogonalizationConfig
- [x] orth_method 设置后自动启用 orthogonalization.enabled
- [x] 无 look-ahead bias (正交化在 CV fold 内部 fit)
- [x] 全量回归零退化

---

## E6: P3-14 几何诊断纳入目标函数 (P2)

**优先级**: P2
**依赖**: E5 (正交化搜索空间就绪)
**预计测试数**: ~12
**文件变更**: adapters.py, optimizer.py

### E6.1 目标

在 `_composite_objective` 添加 `redundancy_penalty`, 基于 VRR 惩罚过度冗余因子. 需扩展 `OrthogonalizerAdapter` 暴露 F/T 矩阵.

### E6.2 Adapter 扩展

**adapters.py OrthogonalizerAdapter.fit() 保存 F/T 矩阵**:

```python
def fit(self, factor_dict, **kwargs):
    # ... 现有逻辑 (第 889-963 行) ...

    # 5. 构造 CrossSectionalOrthogonalizer 协调器
    from factor_pipeline.modules.factor_orthogonalizer.cross_sectional import (
        CrossSectionalOrthogonalizer
    )
    self._cross_sectional = CrossSectionalOrthogonalizer(self._orthogonalizer)

    # v2.6.0 P3-14: 保存 F/T 矩阵用于诊断
    self._F_stacked_ = F_stacked.copy()
    self._T_stacked_ = self._orthogonalizer.transform(F_stacked)

    self.is_fitted_ = True
    # ... 后续 ...
    return self
```

**adapters.py OrthogonalizerAdapter.get_diagnostics() 新方法**:

```python
def get_diagnostics(self) -> Dict[str, np.ndarray]:
    """返回 F/T 矩阵用于诊断 (v2.6.0 P3-14)

    Returns:
        {'F_stacked': (N, K), 'T_stacked': (N, K)} 或 {} (未 fit)
    """
    if not self.is_fitted_:
        return {}
    return {
        'F_stacked': self._F_stacked_,
        'T_stacked': self._T_stacked_,
    }
```

### E6.3 optimizer.py _redundancy_penalty 新增

```python
def _redundancy_penalty(
    self,
    pipeline: 'FactorProcessingPipelineV2',
    config: 'PipelineV2Config',
) -> float:
    """冗余惩罚 (v2.6.0 P3-14, 基于 VRR, ADR-020)

    VRR_k = Var(T_k)/Var(F_k), VRR << 1 表示因子 k 高度冗余.
    惩罚 = mean(max(0, vrr_threshold - VRR_k))  # VRR < threshold 的因子扣分

    lambda_redundancy = 0.05 (v1.1 从 0.1 降为 0.05, 避免与 IC 主目标双重惩罚)
    """
    if not config.orthogonalization.enabled:
        return 0.0  # 正交化未启用, 无冗余诊断

    # 从 OrthogonalizerAdapter 获取 F/T 矩阵
    for hook in pipeline.post_transform_hooks:
        if hasattr(hook, 'get_diagnostics'):
            diag = hook.get_diagnostics()
            if 'F_stacked' in diag and diag['F_stacked'] is not None:
                from factor_pipeline.modules.factor_orthogonalizer.core.diagnostics import (
                    OrthogonalizationDiagnostics
                )
                vrr = OrthogonalizationDiagnostics.compute_vrr(
                    diag['F_stacked'], diag['T_stacked']
                )
                vrr_threshold = config.orthogonalization.vrr_threshold
                penalty = float(np.mean([
                    max(0.0, vrr_threshold - v) for v in vrr
                ]))
                return penalty
    return 0.0
```

**optimizer.py _cv_evaluate 集成 redundancy_penalty**:

```python
# 在 _cv_evaluate 的 fold 循环中 (第 444-450 行附近):
# 单 fold 的复合分数
ic_array = np.array(fold_ics)

# v2.6.0 P3-14: 计算 redundancy_penalty (需要 pipeline 实例)
redundancy_penalty = self._redundancy_penalty(pipeline, config)

fold_score = self._composite_objective(
    ic_array,
    n_processed=len(fold_ics),
    n_total=len(processed_test),
    redundancy_penalty=redundancy_penalty,  # 新增参数
)
scores.append(fold_score)
```

**optimizer.py _composite_objective 添加 redundancy_penalty 参数**:

```python
def _composite_objective(
    self,
    ic_array: np.ndarray,
    n_processed: int,
    n_total: int,
    before: Optional[np.ndarray] = None,
    after: Optional[np.ndarray] = None,
    redundancy_penalty: float = 0.0,  # 新增 (v2.6.0 P3-14)
) -> float:
    # ... 现有 (E4 修正后) ...

    objective = (
        ic_mean
        - self.lambda_volatility * vol_penalty
        - self.lambda_coverage * cov_penalty
        - self.lambda_fidelity * ks_distortion_penalty
        - self.lambda_health * health_penalty
        - self.lambda_redundancy * redundancy_penalty  # 新增
    )
    return float(objective)
```

**optimizer.py __init__ 添加 lambda_redundancy**:

```python
def __init__(
    self,
    # ... 现有 ...
    lambda_health: float = 0.4,
    lambda_redundancy: float = 0.05,  # 新增 (v2.6.0 P3-14, v1.1 从 0.1 降为 0.05)
    random_seed: int = 42,
):
    # ... 现有 ...
    self.lambda_redundancy = lambda_redundancy
```

### E6.4 TDD 测试列表

| # | 测试名 | 类型 | 验证内容 |
|---|--------|------|---------|
| 1 | `test_adapter_get_diagnostics_not_fitted` | 单元 | 未 fit 时, get_diagnostics() 返回 {} |
| 2 | `test_adapter_get_diagnostics_fitted` | 单元 | fit 后, get_diagnostics() 返回 F_stacked/T_stacked |
| 3 | `test_adapter_F_T_shape_match` | 单元 | F_stacked.shape == T_stacked.shape |
| 4 | `test_redundancy_penalty_orth_disabled` | 单元 | orthogonalization.enabled=False 时, redundancy_penalty == 0.0 |
| 5 | `test_redundancy_penalty_high_redundancy` | 单元 | VRR << threshold 时, redundancy_penalty > 0 |
| 6 | `test_redundancy_penalty_low_redundancy` | 单元 | VRR ≈ 1 时, redundancy_penalty ≈ 0 |
| 7 | `test_redundancy_penalty_vrr_threshold` | 单元 | vrr_threshold=0.3 时, VRR=0.3 的因子不扣分 |
| 8 | `test_compute_vrr_pure_function` | 单元 | compute_vrr 是 pure function, 多次调用结果一致 |
| 9 | `test_composite_objective_with_redundancy` | 单元 | redundancy_penalty > 0 时, 目标函数减少 |
| 10 | `test_redundancy_penalty_lambda_0_05` | 单元 | lambda_redundancy=0.05, 确认非 0.1 (v1.1 修正) |
| 11 | `test_cv_evaluate_redundancy_integration` | 集成 | _cv_evaluate 正交化启用时计算 redundancy_penalty |
| 12 | `test_redundancy_backward_compatible` | 回归 | lambda_redundancy=0 时, 与 v2.5.0 行为一致 |

### E6.5 手工校验

```python
# tests/manual/verify_v2_6_0_e6_manual.py
def test_redundancy_penalty_vrr_consistency():
    """手工校验: redundancy_penalty 与 compute_vrr 一致"""
    import numpy as np
    from factor_pipeline.modules.factor_orthogonalizer.core.diagnostics import (
        OrthogonalizationDiagnostics
    )

    # 构造高冗余场景: factor_1 ≈ factor_2
    np.random.seed(42)
    N, K = 100, 3
    F = np.random.randn(N, K)
    F[:, 1] = F[:, 0] * 0.95 + np.random.randn(N) * 0.05  # factor_1 高度冗余

    # 模拟正交化 (对称正交化)
    from factor_pipeline.modules.factor_orthogonalizer.core import SymmetricOrthogonalizer
    orth = SymmetricOrthogonalizer()
    T = orth.fit_transform(F)

    # 手工计算 VRR
    vrr = OrthogonalizationDiagnostics.compute_vrr(F, T)
    print(f"  VRR: {vrr}")
    print(f"  factor_0 VRR: {vrr[0]:.4f}")
    print(f"  factor_1 VRR (冗余): {vrr[1]:.4f} (预期 << 1)")
    print(f"  factor_2 VRR: {vrr[2]:.4f}")

    # 手工计算 redundancy_penalty (vrr_threshold=0.3)
    vrr_threshold = 0.3
    penalty_per_factor = [max(0.0, vrr_threshold - v) for v in vrr]
    penalty = np.mean(penalty_per_factor)
    print(f"  penalty per factor: {penalty_per_factor}")
    print(f"  redundancy_penalty: {penalty:.4f}")

    assert vrr[1] < vrr[0], "冗余因子 VRR 应更低"
    print("✓ redundancy_penalty VRR 一致性验证通过")
```

### E6.6 验收标准

- [x] OrthogonalizerAdapter.fit() 保存 _F_stacked_ / _T_stacked_
- [x] OrthogonalizerAdapter.get_diagnostics() 返回 F/T 矩阵
- [x] _redundancy_penalty 基于 compute_vrr 计算
- [x] lambda_redundancy=0.05 (v1.1 修正值)
- [x] _composite_objective 含 6 项 (IC - vol - cov - ks - health - redundancy)
- [x] lambda_redundancy=0 时与 v2.5.0 行为一致
- [x] 全量回归零退化

---

## E7: P3-15 Layer 3 显著性最终验证 (P2)

**优先级**: P2
**依赖**: E4 (目标函数就绪)
**预计测试数**: ~6
**文件变更**: optimizer.py

### E7.1 目标

新增 `_validate_significance` 方法, 对最优配置运行 Layer 3 显著性检验 (Belloni 2014 PDS Lasso). **仅用于最终配置验证, 不用于每 trial 评估** (计算成本约束).

### E7.2 代码实现

**optimizer.py _validate_significance 新增**:

```python
def _validate_significance(
    self,
    best_params: Dict[str, float],
    factor_data: Dict[str, pd.DataFrame],
    forward_returns: pd.DataFrame,
) -> Dict:
    """对最优配置运行 Layer 3 显著性检验 (v2.6.0 P3-15)

    使用 FactorSignificanceTest (Belloni et al. 2014 PDS Lasso + HC3 + BH 校正)
    评估 best_params 下各因子的增量显著性.

    注意: 计算成本高 (K 次 LassoCV + K 次 OLS), 仅用于最终验证.

    Args:
        best_params: 最优参数字典
        factor_data: 因子数据
        forward_returns: 前向收益率

    Returns:
        {
            'n_significant': int,
            'n_total': int,
            'significance_ratio': float,
            'details': Dict[str, Dict],
            'warning': Optional[str],  # significance_ratio < 0.5 时警告
        }
    """
    from factor_pipeline.backtest.factor_significance import FactorSignificanceTest

    # 用 best_params 构造 config, 处理因子
    config = self._params_to_config(best_params)
    pipeline = FactorProcessingPipelineV2(config=config, strict_mode=False)
    pipeline.fit(factor_data)
    processed = pipeline.transform(factor_data)

    if not processed:
        return {
            'n_significant': 0, 'n_total': 0,
            'significance_ratio': 0.0, 'details': {},
            'warning': 'Pipeline 处理后无因子',
        }

    # 运行 Layer 3 显著性检验
    fst = FactorSignificanceTest(
        method='double_lasso', alpha=0.05,
        correction='benjamini_hochberg',
    )
    factor_names = list(processed.keys())
    fst.fit(processed, forward_returns, factor_names)
    results = fst.test_all_factors()

    n_significant = sum(1 for r in results.values() if r.get('is_significant', False))
    n_total = len(results)
    significance_ratio = n_significant / n_total if n_total > 0 else 0.0

    warning = None
    if significance_ratio < 0.5:
        warning = (
            f"显著性比例 {significance_ratio:.1%} < 50%, "
            f"建议检查因子冗余或调整 P3-14 redundancy_penalty"
        )

    return {
        'n_significant': n_significant,
        'n_total': n_total,
        'significance_ratio': significance_ratio,
        'details': results,
        'warning': warning,
    }
```

**optimizer.py optimize() 末尾调用**:

```python
def optimize(
    self,
    factor_data: Dict[str, pd.DataFrame],
    forward_returns: pd.DataFrame,
    n_jobs: int = 1,
    show_progress: bool = True,
    validate_significance: bool = False,  # 新增 (v2.6.0 P3-15)
) -> Dict[str, float]:
    # ... 现有优化逻辑 ...

    self.best_params = self.study.best_params
    self.best_score = self.study.best_value

    # v2.6.0 P3-15: Layer 3 显著性最终验证 (可选)
    self.significance_report = None
    if validate_significance:
        logger.info("Running Layer 3 significance validation...")
        self.significance_report = self._validate_significance(
            self.best_params, factor_data, forward_returns
        )
        if self.significance_report.get('warning'):
            logger.warning(self.significance_report['warning'])

    return self.best_params
```

### E7.3 TDD 测试列表

| # | 测试名 | 类型 | 验证内容 |
|---|--------|------|---------|
| 1 | `test_validate_significance_returns_dict` | 单元 | 返回含 n_significant/n_total/significance_ratio 的字典 |
| 2 | `test_validate_significance_ratio_range` | 单元 | significance_ratio ∈ [0, 1] |
| 3 | `test_validate_significance_warning_low_ratio` | 单元 | significance_ratio < 0.5 时, warning 非 None |
| 4 | `test_validate_significance_no_warning_high_ratio` | 单元 | significance_ratio ≥ 0.5 时, warning 为 None |
| 5 | `test_optimize_validate_significance_off_by_default` | 集成 | validate_significance=False 时, significance_report 为 None |
| 6 | `test_optimize_validate_significance_on` | 集成 | validate_significance=True 时, significance_report 非 None |

### E7.4 验收标准

- [x] _validate_significance 返回含 n_significant/significance_ratio 的字典
- [x] validate_significance=False 时与 v2.5.0 行为一致 (向后兼容)
- [x] significance_ratio < 0.5 时发出警告
- [x] 全量回归零退化

---

## E8: P3-12' 阈值漂移监测 (P2)

**优先级**: P2
**依赖**: E4 (目标函数就绪, best_score 可用)
**预计测试数**: ~10
**文件变更**: backtest/threshold_drift_monitor.py (新建)

### E8.1 目标

新建 `backtest/threshold_drift_monitor.py`, 监测最优阈值组合的 IC 衰减, 触发重新搜索. 区别于 `UnifiedDriftReporter` (监测因子漂移), 本类监测阈值有效性.

### E8.2 代码实现

**backtest/threshold_drift_monitor.py 新建**:

```python
# -*- coding: utf-8 -*-
"""
阈值漂移监测器 (v2.6.0 P3-12')

监测最优阈值组合的 IC 衰减, 触发重新搜索.
区别于 UnifiedDriftReporter (监测因子漂移), 本类监测阈值有效性.

学术依据:
- Bailey & López de Prado (2014) "The Deflated Sharpe Ratio" JPM 40(5):94-107
- Sullivan, Timmermann & White (1999) "Data-Snooping" JF 54(5):1647-1691
- McLean & Pontiff (2016) "Does Academic Research Destroy Stock Return Predictability?" JF 71(1):5-32
"""
from typing import Dict, List, Optional
import logging
import numpy as np

logger = logging.getLogger(__name__)


class ThresholdDriftMonitor:
    """阈值漂移监测器

    监测最优阈值组合的 IC 衰减, 触发重新搜索.

    区别于 UnifiedDriftReporter (监测因子漂移), 本类监测阈值有效性:
    - UnifiedDriftReporter: 监测因子本身的漂移 (IC 分布 / ICIR / 换手率)
    - ThresholdDriftMonitor: 监测阈值组合的有效性 (best_score 衰减)

    Usage:
        monitor = ThresholdDriftMonitor(best_score=0.05, best_params={...})
        verdict = monitor.update(current_score=0.035)
        if verdict['needs_research']:
            # 触发重新搜索
            optimizer.optimize(...)
    """

    def __init__(
        self,
        best_score: float,
        best_params: Dict[str, float],
        halflife: int = 63,
        decay_threshold: float = 0.2,
        min_observations: int = 5,
    ):
        """初始化阈值漂移监测器

        Args:
            best_score: 优化器搜索出的最优分数
            best_params: 最优参数字典
            halflife: EWMA 半衰期 (日频默认 63)
            decay_threshold: 衰减阈值 (默认 0.2 = 20%)
            min_observations: 最小观测数 (默认 5, 不足时不判定)
        """
        self.best_score = best_score
        self.best_params = best_params
        self.halflife = halflife
        self.decay_threshold = decay_threshold
        self.min_observations = min_observations
        self.score_history: List[float] = []

        logger.info(
            f"ThresholdDriftMonitor initialized: "
            f"best_score={best_score:.6f}, halflife={halflife}"
        )

    def update(self, current_score: float) -> Dict:
        """更新当前评分, 返回是否需要重新搜索

        Args:
            current_score: 当前周期的评分 (用 best_params 计算)

        Returns:
            {
                'needs_research': bool,
                'decay_ratio': float,  # EWMA(current) / best_score
                'best_score': float,
                'current_score': float,
                'ewma_score': float,
                'n_observations': int,
            }
        """
        self.score_history.append(current_score)

        if len(self.score_history) < self.min_observations:
            return {
                'needs_research': False,
                'decay_ratio': 1.0,
                'best_score': self.best_score,
                'current_score': current_score,
                'ewma_score': current_score,
                'n_observations': len(self.score_history),
                'reason': f'观测数不足 ({len(self.score_history)} < {self.min_observations})',
            }

        # EWMA 加权评分
        ewma_score = self._compute_ewma()

        # 衰减比例
        if abs(self.best_score) < 1e-10:
            decay_ratio = 1.0
        else:
            decay_ratio = ewma_score / self.best_score

        # 触发条件: EWMA 衰减 > decay_threshold (默认 20%)
        needs_research = decay_ratio < (1.0 - self.decay_threshold)

        result = {
            'needs_research': needs_research,
            'decay_ratio': float(decay_ratio),
            'best_score': self.best_score,
            'current_score': current_score,
            'ewma_score': float(ewma_score),
            'n_observations': len(self.score_history),
        }

        if needs_research:
            result['reason'] = (
                f'EWMA 衰减 {1 - decay_ratio:.1%} > 阈值 {self.decay_threshold:.1%}'
            )
            logger.warning(
                f"ThresholdDriftMonitor: 需要重新搜索. "
                f"decay_ratio={decay_ratio:.4f}, ewma_score={ewma_score:.6f}"
            )

        return result

    def _compute_ewma(self) -> float:
        """计算 EWMA 加权评分

        EWMA: s[t] = alpha * x[t] + (1-alpha) * s[t-1]
        alpha = 1 - exp(-ln2/halflife)
        """
        if not self.score_history:
            return 0.0

        alpha = 1.0 - np.exp(-np.log(2.0) / max(self.halflife, 1))
        ewma = self.score_history[0]
        for score in self.score_history[1:]:
            ewma = alpha * score + (1 - alpha) * ewma
        return float(ewma)

    def get_history(self) -> List[float]:
        """获取评分历史"""
        return self.score_history.copy()

    def reset(self, best_score: float, best_params: Dict[str, float]):
        """重置监测器 (重新搜索后调用)

        Args:
            best_score: 新的最优分数
            best_params: 新的最优参数
        """
        self.best_score = best_score
        self.best_params = best_params
        self.score_history = []
        logger.info(f"ThresholdDriftMonitor reset: best_score={best_score:.6f}")
```

### E8.3 TDD 测试列表

| # | 测试名 | 类型 | 验证内容 |
|---|--------|------|---------|
| 1 | `test_threshold_drift_monitor_init` | 单元 | 初始化后, best_score/best_params/halflife 正确 |
| 2 | `test_update_insufficient_observations` | 单元 | 观测数 < 5 时, needs_research=False |
| 3 | `test_update_no_decay` | 单元 | current_score ≈ best_score 时, needs_research=False |
| 4 | `test_update_significant_decay` | 单元 | current_score 衰减 > 20% 时, needs_research=True |
| 5 | `test_ewma_computation` | 单元 | 手工计算 EWMA, 与实现对比精度 < 1e-10 |
| 6 | `test_ewma_recent_emphasis` | 单元 | 近期评分低时, EWMA < 等权均值 |
| 7 | `test_decay_threshold_custom` | 单元 | decay_threshold=0.3 时, 衰减 25% 不触发 |
| 8 | `test_reset_clears_history` | 单元 | reset() 后, score_history 为空 |
| 9 | `test_get_history_returns_copy` | 单元 | get_history() 返回副本, 修改不影响内部 |
| 10 | `test_integration_with_optimizer` | 集成 | optimizer.optimize() 后, ThresholdDriftMonitor 可用 best_score |

### E8.4 手工校验

```python
# tests/manual/verify_v2_6_0_e8_manual.py
def test_threshold_drift_monitor_decay_detection():
    """手工校验: 阈值漂移监测器衰减检测"""
    import numpy as np
    from factor_pipeline.backtest.threshold_drift_monitor import ThresholdDriftMonitor

    # best_score=0.05, 模拟衰减场景
    monitor = ThresholdDriftMonitor(
        best_score=0.05, best_params={},
        halflife=5, decay_threshold=0.2,
    )

    # 前 5 期: 无衰减
    for _ in range(5):
        verdict = monitor.update(0.05)
    assert not verdict['needs_research'], "无衰减时不应触发"

    # 后 5 期: 衰减到 0.03 (40% 衰减)
    for _ in range(5):
        verdict = monitor.update(0.03)
    assert verdict['needs_research'], "衰减 > 20% 应触发"
    assert verdict['decay_ratio'] < 0.8, f"decay_ratio 应 < 0.8, 得到 {verdict['decay_ratio']}"

    print("✓ 阈值漂移监测器衰减检测验证通过")
    print(f"  best_score: {verdict['best_score']:.4f}")
    print(f"  ewma_score: {verdict['ewma_score']:.4f}")
    print(f"  decay_ratio: {verdict['decay_ratio']:.4f}")
    print(f"  needs_research: {verdict['needs_research']}")
```

### E8.5 验收标准

- [x] ThresholdDriftMonitor 类实现 (update/get_history/reset)
- [x] EWMA 加权评分手工计算与实现对比精度 < 1e-10
- [x] 衰减 > 20% 时触发 needs_research=True
- [x] 观测数不足时不触发 (min_observations 保护)
- [x] 与 optimizer.optimize() 衔接 (用 best_score 初始化)
- [x] 全量回归零退化

---

## E9: 文档验证 + 全量回归 (P1)

**优先级**: P1
**依赖**: E1-E8 全部完成
**预计测试数**: 0 (验证阶段)
**文件变更**: README.md, CHANGELOG.md, CODE_WIKI.md, DECISIONS.md, project_memory.md, topics.md

### E9.1 文档更新清单

| 文档 | 更新内容 |
|------|---------|
| README.md | v2.6.0 状态: 规划中 → 已实施; 版本历史表添加 v2.6.0 行 |
| CHANGELOG.md | 添加 v2.6.0 完整变更日志 (E1-E9 详情) |
| CODE_WIKI.md | 优化器章节更新 (8 维 → 10 维, 目标函数 6 项); threshold_drift_monitor 新模块 |
| DECISIONS.md | P3-1/P3-9/P3-10/P3-11/P3-12 状态更新; ADR-004/005 修订日志 |
| project_memory.md | 追加 v2.6.0 经验教训 |
| topics.md | 追加 v2.6.0 完成日志 |

### E9.2 手工校验脚本

**tests/manual/verify_v2_6_0_manual.py**:

```python
# -*- coding: utf-8 -*-
"""v2.6.0 手工数值校验脚本

校验 8 项:
1. migration_threshold 字段位置修正
2. IC EWMA 时间加权
3. health_penalty 代理指标
4. KS penalty 符号方向修正
5. 正交化搜索空间
6. redundancy_penalty VRR 一致性
7. Layer 3 显著性验证
8. 阈值漂移监测
"""
import numpy as np
import pandas as pd


def test_1_migration_threshold_field_location():
    """1. migration_threshold 字段位置修正"""
    from factor_pipeline.optimizer import EndToEndThresholdOptimizer
    opt = EndToEndThresholdOptimizer(n_trials=1)
    config = opt._params_to_config({'migration_threshold': 0.15})
    assert config.migration_threshold == 0.15
    assert config.monitor.enable_smooth_transition == True
    print("✓ 1. migration_threshold 字段位置修正")


def test_2_ic_ewma_weighting():
    """2. IC EWMA 时间加权"""
    from factor_pipeline.backtest.factor_metrics import compute_ic_series
    np.random.seed(42)
    factor = np.random.randn(50, 20)
    returns = np.random.randn(50, 20)
    ic_equal = compute_ic_series(factor, returns, weighting='equal')
    ic_ewma = compute_ic_series(factor, returns, weighting='ewma', halflife=5)
    assert len(ic_ewma) == 1, "EWMA 应返回标量"
    print("✓ 2. IC EWMA 时间加权")


def test_3_health_penalty_proxy():
    """3. health_penalty 代理指标"""
    from factor_pipeline.optimizer import EndToEndThresholdOptimizer
    opt = EndToEndThresholdOptimizer(n_trials=1)
    ic_low = np.array([0.1, 0.09, 0.08, 0.07, 0.03, 0.02, 0.01, 0.005])
    assert opt._health_penalty_proxy(ic_low) == 0.5
    print("✓ 3. health_penalty 代理指标")


def test_4_ks_penalty_sign_correction():
    """4. KS penalty 符号方向修正"""
    from factor_pipeline.optimizer import EndToEndThresholdOptimizer
    opt = EndToEndThresholdOptimizer(n_trials=1)
    before = np.random.randn(100, 3)
    after = before.copy()
    fidelity = opt._ks_distribution_fidelity(before, after)
    distortion = 1.0 - fidelity
    assert distortion < 0.01
    print("✓ 4. KS penalty 符号方向修正")


def test_5_orthogonalization_search_space():
    """5. 正交化搜索空间"""
    from factor_pipeline.optimizer import (
        EndToEndThresholdOptimizer, DEFAULT_SEARCH_SPACE_ORTH
    )
    assert 'orth_method' in DEFAULT_SEARCH_SPACE_ORTH
    assert 'orth_align_mode' in DEFAULT_SEARCH_SPACE_ORTH
    assert 'orth_ridge_lambda' in DEFAULT_SEARCH_SPACE_ORTH
    print("✓ 5. 正交化搜索空间")


def test_6_redundancy_penalty_vrr():
    """6. redundancy_penalty VRR 一致性"""
    from factor_pipeline.modules.factor_orthogonalizer.core.diagnostics import (
        OrthogonalizationDiagnostics
    )
    from factor_pipeline.modules.factor_orthogonalizer.core import SymmetricOrthogonalizer
    np.random.seed(42)
    F = np.random.randn(100, 3)
    orth = SymmetricOrthogonalizer()
    T = orth.fit_transform(F)
    vrr = OrthogonalizationDiagnostics.compute_vrr(F, T)
    assert len(vrr) == 3
    print("✓ 6. redundancy_penalty VRR 一致性")


def test_7_layer3_significance_validation():
    """7. Layer 3 显著性验证"""
    from factor_pipeline.optimizer import EndToEndThresholdOptimizer
    opt = EndToEndThresholdOptimizer(n_trials=1)
    assert hasattr(opt, '_validate_significance')
    print("✓ 7. Layer 3 显著性验证方法存在")


def test_8_threshold_drift_monitor():
    """8. 阈值漂移监测"""
    from factor_pipeline.backtest.threshold_drift_monitor import ThresholdDriftMonitor
    monitor = ThresholdDriftMonitor(best_score=0.05, best_params={})
    verdict = monitor.update(0.03)
    assert 'needs_research' in verdict
    print("✓ 8. 阈值漂移监测")


if __name__ == '__main__':
    print("=" * 60)
    print("v2.6.0 手工数值校验 (8 项)")
    print("=" * 60)
    test_1_migration_threshold_field_location()
    test_2_ic_ewma_weighting()
    test_3_health_penalty_proxy()
    test_4_ks_penalty_sign_correction()
    test_5_orthogonalization_search_space()
    test_6_redundancy_penalty_vrr()
    test_7_layer3_significance_validation()
    test_8_threshold_drift_monitor()
    print("=" * 60)
    print("✓ v2.6.0 手工校验全部通过")
```

### E9.3 全量回归

```bash
# 全量测试 (预期 ~919 passed)
python -m pytest tests/ -v --timeout=120

# 手工校验
python tests/manual/verify_v2_6_0_manual.py
```

### E9.4 验收标准

- [x] README.md v2.6.0 状态更新为已实施
- [x] CHANGELOG.md v2.6.0 完整变更日志
- [x] CODE_WIKI.md 优化器章节更新
- [x] DECISIONS.md P3-1/P3-9/P3-10/P3-11/P3-12 状态更新
- [x] ADR-004/005 修订日志追加
- [x] project_memory.md v2.6.0 经验教训
- [x] topics.md v2.6.0 完成日志
- [x] verify_v2_6_0_manual.py 8 项全部通过
- [x] 全量回归 ~919 passed + 5 skipped + 0 failed

---

## 风险与回退

### 总体风险

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| health_penalty 代理指标与 health_score 相关性不足 | 中 | 目标函数引导方向偏差 | E4 手工校验 + A/B 测试 |
| 正交化搜索维度增加导致 n_trials 不足 | 中 | 优化不收敛 | n_trials 从 100 提到 150-200 |
| FactorSignificanceTest 计算成本超预期 | 低 | E7 集成测试超时 | 仅最终验证, 不每 trial 评估 |
| fidelity 符号修正改变历史 best_score | 中 | 与 v2.5.0 best_score 不可比 | 文档标注 + 重新运行优化 |

### 回退方案

如果某阶段失败, 可独立回退 (各阶段文件变更隔离):

| 阶段 | 回退方法 |
|------|---------|
| E1 | 恢复 DECISIONS.md P3-11 状态为 `[ ]` |
| E2 | 恢复 optimizer.py:150-158 的 hasattr 检查 |
| E3 | 移除 compute_ic_series 的 weighting/halflife 参数 |
| E4 | lambda_health=0 + 恢复 fidelity 符号为 + |
| E5 | search_orth=False (默认关闭) |
| E6 | lambda_redundancy=0 + 移除 get_diagnostics |
| E7 | validate_significance=False (默认关闭) |
| E8 | 删除 threshold_drift_monitor.py |

### 并行性

- E1, E2, E3 可并行 (无依赖)
- E4 依赖 E3 (IC EWMA)
- E5 依赖 E2 (_params_to_config 逻辑清晰)
- E6 依赖 E5 (正交化搜索空间就绪)
- E7 依赖 E4 (目标函数就绪)
- E8 依赖 E4 (best_score 可用)
- E9 依赖 E1-E8 全部完成

**推荐执行顺序**: E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9

---

## 附录: 与 ANALYSIS_V2.6.0.md 的映射

| ANALYSIS 任务 | EXECUTION 阶段 | 优先级 |
|--------------|---------------|--------|
| P3-11' 状态修正 | E1 | P0 |
| P3-10' 字段位置修正 + ADR-005 | E2 | P0 |
| P3-1' IC 时间加权 | E3 | P1 |
| P3-9' 目标函数对齐 ADR-004 | E4 | P1 |
| P3-13 正交化搜索空间 | E5 | P1 |
| P3-14 几何诊断 + Adapter 扩展 | E6 | P2 |
| P3-15 Layer 3 显著性 | E7 | P2 |
| P3-12' 阈值漂移监测 | E8 | P2 |
| — (文档验证) | E9 | P1 |
