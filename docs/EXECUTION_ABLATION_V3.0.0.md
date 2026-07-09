# v3.0.0 消融对照机制执行方案 — 四层架构 + Baseline 阶梯

> **版本**: v1.0 (2026-07-08)
> **范围**: v3.0.0 消融对照机制 (P1) — L1-L4 四层消融 + B0-B3 Baseline + Ledoit-Wolf HAC + BH-FDR
> **基础**: [ABLATION_DESIGN_V3.0.0.md](private/ABLATION_DESIGN_V3.0.0.md) v1.0 (第十四轮审查修正 E1-E10)
> **前置**: v3.0.0 T1 (指纹 21 维, ADR-024) + T3 (CUSUM, ADR-025) + T4 (BH-FDR, ADR-002a) 已完成
> **方法**: 与 T1/T4 一致的 E1-E7 分阶段 TDD 流程, 严格 Red→Green→Review
> **学术依据**: Ledoit & Wolf (2008) HAC + bootstrap / Benjamini & Hochberg (1995) BH-FDR

---

## 0. 摘要

### 0.1 目标

为 v3.0.0 管线构建**可执行的消融对照机制**, 覆盖 §3 前置处理诚实性框架的实证义务。基于 [ABLATION_DESIGN_V3.0.0.md](private/ABLATION_DESIGN_V3.0.0.md) 设计文档 (经第十四轮审查修正 10 项), 实现四层消融 + Baseline 阶梯 + 显著性判定。

### 0.2 四层消融架构 + Baseline 阶梯

| 层级 | 名称 | 消融对象 | 组合数 | 依赖 |
|------|------|---------|--------|------|
| **L1** | 组件消融 | 5 模块逐个关闭 (Imputer/Winsorizer/Scaler/Neutralizer/Orthogonalizer) | 5 + 1 baseline (M6: baseline 引用 B3_full) | E1 enabled 开关 |
| **L2** | 路由消融 | 5 配置: 全 static / 全 dynamic / 全 mixed / 随机路由 / 完整路由 | 5 (M6: full 引用 B3_full, 实际运行 4) | E1 + E2 |
| **L3** | 参数消融 | CUSUM 参数 / EWMA 参数 / EWMA 5 分叉阈值 / 5 叉阈值 / winsorize 比例 / 多重比较校正方法 | ~25 (M6: baseline 引用 B3_full) | T3 CUSUM (已完成) |
| **L4** | 前置处理 OAT | 6 自由度单维消融 (去极值/标准化/缺失值/行业中性化/时间对齐/数据起止点) | ~19 + 1 baseline (M6: baseline 引用 B3_full) | E2 |
| **B0-B3** | Baseline 阶梯 | B0 原始+dropna / B1 仅 imputer / B2 imputer+Z-score / B3 完整管线 | 4 (B3_full 作为各层统一参照, 见 §7.2 M6 修正) | E1 + E2 |

**全因子设计不可行**: L4 全因子 4×3×3×3×3×3 = 972 组合, 月度 240 obs 不可行 → 采用 OAT 单维消融 (E1 修正, CRITICAL)。

### 0.3 任务拆解 (E1-E7)

| 阶段 | 任务 | 优先级 | 依赖 | 测试数 | 关键产出 |
|------|------|--------|------|--------|---------|
| **E1** | 5 模块 enabled 开关 | P0 | 无 | ~15 | ImputerAdapter/ProcessingAdapter/NeutralizerAdapter/OrthogonalizerAdapter 加 `enabled: bool = True` |
| **E2** | AblationRunner 核心引擎 | P0 | E1 | ~25 | `backtest/ablation_runner.py` 新建 + Ledoit-Wolf HAC + bootstrap + ρ_step |
| **E3** | L1 组件消融 | P0 | E1, E2 | ~8 | 5 模块逐个关闭 + 显著性对比 |
| **E4** | L2 路由消融 | P0 | E1, E2 | ~8 | 5 路由配置 + 随机路由控制组 |
| **E5** | L4 前置处理 OAT 消融 | P1 | E2 | ~12 | 6 自由度单维消融 + BH-FDR 校正 |
| **E6** | L3 参数消融 | P1 | E2, T3 (已完成) | ~10 | CUSUM/EWMA/5 叉阈值/winsorize 比例 |
| **E7** | Baseline 阶梯 + 报告生成 | P0 | E1-E6 | ~6 | B0-B3 + 消融报告 Markdown |

**推荐执行顺序**: E1 → E2 → (E3, E4, E7 并行) → E5 → E6

### 0.4 关键设计决策

| # | 决策 | 选项 | 理由 |
|---|------|------|------|
| 1 | enabled 开关位置 | Adapter 层 (`adapters.py`), 非模块层 | Adapter 是管线与模块的唯一集成点; OrthogonalizerAdapter 已有 `enabled` 模式 (ADR-020), 复用此模式 |
| 2 | AblationRunner 独立性 | `backtest/ablation_runner.py` 独立模块, 不侵入 fit/transform | 与 T3.4 CUSUM "事后诊断" 设计一致; 消融是离线评估, 非生产路径 |
| 3 | 显著性判定 | Ledoit-Wolf (2008) HAC + circular block bootstrap (B=1000) | 复用因子 IC/Sharpe 序列的时序依赖; HAC 用 Newey-West 核 |
| 4 | 多重比较校正 | BH-FDR (复用 `backtest/multiple_testing.py`) | T4 已实现共享模块, ADR-002a 已采纳 BH-FDR |
| 5 | L4 设计 | OAT 单维消融, 不做全因子 972 组合 | E1 修正 (CRITICAL): 月度 240 obs 不可行 |
| 6 | L2 随机路由控制组 | 固定 seed 随机分配管道 | E2 修正 (CRITICAL): 排除"路由 vs 不路由"的混淆 |
| 7 | ADR 编号 | ADR-026 | T3 已完成 (ADR-025), ADR-026 未占用 |

### 0.5 与 v3.0.0 已实施代码的兼容性

| 已实施 | 版本 | 兼容性 | 协同方式 |
|--------|------|--------|---------|
| T1 指纹 21 维 (ADR-024) | v3.0.0 | ✅ | AblationRunner 复用 fingerprint 驱动路由消融 (L2) |
| T3 CUSUM (ADR-025) | v3.0.0 | ✅ | L3 参数消融直接覆盖 `cusum_k`/`cusum_h` |
| T4 BH-FDR (ADR-002a) | v3.0.0 | ✅ | 消融多重比较校正复用 `apply_bh_fdr` |
| OrthogonalizerAdapter `enabled` | v2.5.0 | ✅ | E1 复用此模式, 扩展到其余 4 个 Adapter |
| `factor_metrics.py` | v2.6.0 | ✅ | IC/ICIR/turnover/long-short returns 复用 |
| `multiple_testing.py` | v3.0.0 T3.5 | ✅ | `apply_bh_fdr` / `apply_bonferroni` 直接调用 |

---

## 1. E1: 各模块 enabled 开关 (L1 组件消融基础)

### 1.1 目标

为 5 个模块的 Adapter 加 `enabled: bool = True` 配置开关, 关闭时走 identity。默认 `True`, 向后兼容 (不破坏现有行为)。

### 1.2 Identity 定义 (E4 修正, MAJOR)

| 模块 | Adapter | 关闭时 identity 行为 | 理由 |
|------|---------|---------------------|------|
| **Imputer** | `ImputerAdapter` | 保留 NaN (不填充), IC 计算时 dropna | E5 修正: B0 原始因子有 NaN, dropna 隔离缺失影响 |
| **Winsorizer** | `ProcessingAdapter(process_type='outlier')` | 跳过 (不截断, 返回 X 原样) | 极值处理的边际贡献 |
| **Scaler** | `ProcessingAdapter(process_type='standardization')` | 跳过 (不标准化, 返回 X 原样) | 标准化的边际贡献 |
| **Neutralizer** | `NeutralizerAdapter` | 跳过 (不中性化, 返回 X 原样) | 风险剥离的边际贡献 |
| **Orthogonalizer** | `OrthogonalizerAdapter` | 跳过 (返回 factor_dict 原样) | 已有 `enabled` (v2.5.0), 复用 |

### 1.3 代码改动

**文件**: `adapters.py`

#### 1.3.1 ImputerAdapter (adapters.py:159-249)

```python
class ImputerAdapter(PipelineStep):
    def __init__(self, strategy: str = 'auto', enabled: bool = True,
                 module_path=None, import_path=None, class_name=None, **params):
        super().__init__(name="FactorImputer", step_type="imputation",
                         strategy=strategy, enabled=enabled, **params)
        self.strategy = strategy
        self.enabled = enabled          # ← 新增
        # ... 既有初始化不变 ...

    def fit(self, X: pd.DataFrame, **kwargs) -> 'ImputerAdapter':
        if not self.enabled:
            self.is_fitted = True       # 标记已拟合 (identity)
            logger.info("ImputerAdapter: enabled=False, 跳过拟合 (identity)")
            return self
        # ... 既有 fit 逻辑不变 ...

    def transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        if not self.enabled:
            return X                    # identity: 保留 NaN
        if not self.is_fitted:
            raise ValueError("插补器未拟合，请先调用 fit()")
        # ... 既有 transform 逻辑不变 ...
```

#### 1.3.2 ProcessingAdapter — Winsorizer + Scaler (adapters.py:252-407)

`ProcessingAdapter` 服务于 3 种子类型 (`outlier` / `transformation` / `standardization`)。E1 仅对 `outlier` (Winsorizer) 和 `standardization` (Scaler) 加开关, `transformation` 不加 (它是 Static 管道的非线性变换, 非消融对象)。

```python
class ProcessingAdapter(PipelineStep):
    def __init__(self, process_type: str = 'outlier', method: str = 'auto',
                 enabled: Optional[bool] = None,  # ← 新增, None = 默认 True
                 module_path=None, import_path=None, class_name=None, **params):
        super().__init__(name=f"FactorProcessing_{process_type}",
                         step_type=process_type, method=method, **params)
        self.process_type = process_type
        self.method = method
        # enabled 仅对 outlier/standardization 生效; transformation 忽略 (永远 True)
        if process_type in ('outlier', 'standardization'):
            self.enabled = enabled if enabled is not None else True
        else:
            self.enabled = True         # transformation 不消融
        # ... 既有初始化不变 ...

    def fit(self, X: pd.DataFrame, **kwargs) -> 'ProcessingAdapter':
        if not self.enabled:
            self.is_fitted = True
            logger.info(f"ProcessingAdapter({self.process_type}): enabled=False, 跳过拟合")
            return self
        # ... 既有 fit 逻辑不变 ...

    def transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        if not self.enabled:
            return X                    # identity: 跳过
        if not self.is_fitted:
            raise ValueError(f"{self.process_type} 未拟合")
        # ... 既有 transform 逻辑不变 ...
```

#### 1.3.3 NeutralizerAdapter (adapters.py:409-600)

```python
class NeutralizerAdapter(PipelineStep):
    def __init__(self, enabled: bool = True, **params):  # ← 新增 enabled
        super().__init__(name="FactorNeutralizer", step_type="neutralization",
                         enabled=enabled, **params)
        self.enabled = enabled
        # ... 既有初始化不变 ...

    def fit(self, X: pd.DataFrame, **kwargs) -> 'NeutralizerAdapter':
        if not self.enabled:
            self.is_fitted = True
            logger.info("NeutralizerAdapter: enabled=False, 跳过拟合")
            return self
        # ... 既有 fit 逻辑不变 ...

    def transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        if not self.enabled:
            return X                    # identity: 跳过
        # ... 既有 transform 逻辑不变 ...
```

#### 1.3.4 OrthogonalizerAdapter (adapters.py:770+) — 已有 enabled, 无需改动

`OrthogonalizerAdapter` 已在 v2.5.0 (ADR-020) 实现 `enabled` 开关 (adapters.py:796: `self.enabled = getattr(config, 'enabled', False)`)。E1 **不改动**此 Adapter, 仅在 AblationRunner 中通过 `OrthogonalizationConfig.enabled` 控制。

### 1.4 管线侧: StaticFactorPipeline / DynamicFactorPipeline / MixedFactorPipeline

三条管道在 `__init__` 构造 Adapter 时需透传 `enabled` 参数。改动方式: 管道 `__init__` 新增 `module_enabled: Optional[Dict[str, bool]] = None` 参数。

**文件**: `pipelines_v2.py` (StaticFactorPipeline:777+, DynamicFactorPipeline:831+, MixedFactorPipeline:959+)

```python
class StaticFactorPipeline(_BaseFactorPipeline):
    def __init__(self, neutralizer_params=None, enable_garch=False,
                 garch_params=None, module_enabled: Optional[Dict[str, bool]] = None):
        super().__init__()
        me = module_enabled or {}       # me = "module_enabled" 缩写

        self.steps = [
            ('imputer', ImputerAdapter(strategy='auto', enabled=me.get('imputer', True))),
            ('outlier', ProcessingAdapter(process_type='outlier', method='auto',
                                          enabled=me.get('winsorizer', True))),
            ('transform', ProcessingAdapter(process_type='transformation', method='auto')),
        ]
        # ... GARCH / neutralize / standardize 逻辑加 enabled ...
        if enable_garch:
            self.steps.append(('garch_whiten', GarchWhiteningAdapter(**garch_kwargs)))

        self.steps.extend([
            ('neutralize', NeutralizerAdapter(enabled=me.get('neutralizer', True),
                                              **(neutralizer_params or {}))),
            ('standardize', ProcessingAdapter(process_type='standardization', method='auto',
                                              enabled=me.get('scaler', True))),
        ])
```

**`FactorProcessingPipelineV2._create_pipeline`** (pipelines_v2.py:1401) 透传 `module_enabled`:

```python
def _create_pipeline(self, pipe_type: str, neutralizer_params: dict,
                     module_enabled: Optional[Dict[str, bool]] = None):
    if pipe_type == 'static':
        return StaticFactorPipeline(
            neutralizer_params=neutralizer_params,
            enable_garch=self.config.static_enable_garch,
            garch_params={...} if self.config.static_enable_garch else None,
            module_enabled=module_enabled,   # ← 新增
        )
    elif pipe_type == 'dynamic':
        return DynamicFactorPipeline(
            ..., module_enabled=module_enabled   # ← 新增
        )
    elif pipe_type == 'mixed':
        return MixedFactorPipeline(
            ..., module_enabled=module_enabled   # ← 新增
        )
```

**默认 `module_enabled=None`** → `me.get(..., True)` → 全部 `True` → 向后兼容。

### 1.5 PipelineV2Config 扩展

**文件**: `pipelines_v2.py` PipelineV2Config (L681)

新增 `module_enabled` 字段 (向后兼容, 有默认值):

```python
@dataclass
class PipelineV2Config:
    # ... 既有字段不变 ...

    # v3.0.0 消融: 模块级 enabled 开关 (L1 组件消融基础)
    # None = 全部启用 (默认, 向后兼容); dict 形式指定各模块开关
    module_enabled: Optional[Dict[str, bool]] = None
```

`FactorProcessingPipelineV2.fit()` 中 `_create_pipeline` 调用透传 `self.config.module_enabled`。

### 1.6 兼容性保证

| 场景 | 行为 | 验证 |
|------|------|------|
| `module_enabled=None` (默认) | 全部 `enabled=True`, 走既有逻辑 | 既有 934+ 测试零回归 |
| `module_enabled={'imputer': False}` | Imputer identity (保留 NaN), 其余正常 | E1 新增测试 |
| `enabled=False` + `fit()` | `is_fitted=True`, 跳过内部拟合 | E1-T1 测试 |
| `enabled=False` + `transform()` | 直接返回 X (identity) | E1-T2 测试 |

### 1.7 E1 测试计划 (TDD)

**文件**: `tests/test_adapters/test_module_enabled.py` (新建)

#### E1-T1 ImputerAdapter enabled 开关

```python
class TestImputerEnabled:
    def test_enabled_false_fit_is_identity(self):
        """enabled=False → fit 不拟合内部 imputer, is_fitted=True"""
    def test_enabled_false_transform_preserves_nan(self):
        """enabled=False → transform 保留 NaN (identity)"""
    def test_enabled_true_normal_behavior(self):
        """enabled=True (默认) → 正常插补, NaN 被填充"""
    def test_default_enabled_is_true(self):
        """构造时不传 enabled → enabled=True"""
```

#### E1-T2 ProcessingAdapter (Winsorizer/Scaler) enabled 开关

```python
class TestProcessingAdapterEnabled:
    def test_outlier_enabled_false_identity(self):
        """outlier enabled=False → transform 返回原样 (不截断)"""
    def test_standardization_enabled_false_identity(self):
        """standardization enabled=False → transform 返回原样 (不标准化)"""
    def test_transformation_ignores_enabled(self):
        """transformation 类型 enabled 永远 True (不消融)"""
    def test_enabled_false_fit_skips_inner(self):
        """enabled=False → fit 不初始化 _processor"""
```

#### E1-T3 NeutralizerAdapter enabled 开关

```python
class TestNeutralizerEnabled:
    def test_enabled_false_identity(self):
        """enabled=False → transform 返回原样 (不中性化)"""
    def test_enabled_false_fit_skips(self):
        """enabled=False → fit 不拟合中性化模型"""
    def test_enabled_true_normal(self):
        """enabled=True → 正常中性化, 均值接近 0"""
```

#### E1-T4 管线级 enabled 透传

```python
class TestPipelineModuleEnabled:
    def test_module_enabled_none_default_behavior(self):
        """module_enabled=None → 全部启用, 与既有行为一致"""
    def test_module_enabled_imputer_false(self):
        """module_enabled={'imputer': False} → 输出保留 NaN"""
    def test_module_enabled_all_false(self):
        """module_enabled 全 False → 输出 = 输入 (全 identity)"""
    def test_create_pipeline_passes_module_enabled(self):
        """_create_pipeline 透传 module_enabled 到各管道"""
```

#### E1-T5 向后兼容回归

```python
class TestBackwardCompat:
    def test_existing_pipeline_config_no_module_enabled(self):
        """PipelineV2Config 无 module_enabled 字段 → 默认 None → 全启用"""
    def test_existing_tests_pass(self):
        """既有 StaticFactorPipeline/DynamicFactorPipeline 测试不破坏"""
```

### 1.8 E1 验收标准

- [ ] E1-T1 ~ E1-T5 测试全部 Red → Green
- [ ] 5 个 Adapter 均有 `enabled: bool = True` 参数 (Orthogonalizer 已有, 验证即可)
- [ ] `enabled=False` 时: Imputer 保留 NaN / 其余 4 个返回 X 原样
- [ ] `module_enabled=None` 默认值, 既有 934+ 测试零回归
- [ ] `PipelineV2Config.module_enabled` 字段存在, 默认 None
- [ ] `_create_pipeline` 透传 `module_enabled` 到三条管道

---

## 2. E2: AblationRunner 核心引擎

### 2.1 目标

新建 `backtest/ablation_runner.py`, 实现:
1. 接收消融配置 (模块开关组合 + 路由模式 + 参数覆盖) + 因子数据 + 前向收益
2. 运行管线 + 收集 metrics (IC/ICIR/Sharpe/turnover/drawdown/ρ_step/condition_number/VRR)
3. Ledoit-Wolf (2008) HAC 标准误 + circular block bootstrap (1000 次) 显著性判定
4. BH-FDR 校正多重比较 (复用 `backtest/multiple_testing.py`)

### 2.2 接口设计

#### 2.2.1 AblationConfig (消融配置)

```python
@dataclass
class AblationConfig:
    """消融实验配置 — 定义一次消融实验的全部开关"""

    # ── 标识 ──
    name: str = "baseline"              # 实验名称 (如 "L1_imputer_off")
    layer: str = "baseline"             # 'L1' | 'L2' | 'L3' | 'L4' | 'baseline'

    # ── L1 组件开关 ──
    module_enabled: Optional[Dict[str, bool]] = None
    # None = 全启用; {'imputer': False, ...} = 指定关闭

    # ── L2 路由模式 ──
    routing_mode: str = 'full'          # 'static' | 'dynamic' | 'mixed' | 'random' | 'full'
    random_seed: Optional[int] = None   # routing_mode='random' 时的 seed

    # ── L3 参数覆盖 ──
    cusum_k: Optional[float] = None     # CUSUM slack (覆盖默认 0.5)
    cusum_h: Optional[float] = None     # CUSUM trigger (覆盖默认 5.5)
    correction_method: Optional[str] = None  # 'benjamini_hochberg' | 'bonferroni' | 'none'
    winsorize_ratio: Optional[float] = None  # 0.01 / 0.03 / 0.05
    # M4 修正: EWMA + 5 叉阈值 (原缺失, 补充)
    ewma_halflife: Optional[int] = None     # EWMA halflife: 6 / 12 / 24
    ewma_alpha: Optional[float] = None      # EWMA 5 分叉阈值 alpha: [0.1, 0.3, 0.5, 0.7, 0.9]
    routing_threshold_scale: Optional[float] = None  # 5 叉阈值缩放: 1.0(基底) / 1.2(±20%) / 1.5(±50%)

    # ── L4 前置处理 OAT ──
    outlier_method: Optional[str] = None    # '3sigma' | 'mad' | 'winsorize_1pct' | 'winsorize_5pct'
    scaler_method: Optional[str] = None     # 'zscore' | 'rank' | 'minmax'
    missing_method: Optional[str] = None    # 'drop' | 'median' | 'knn'
    neutralization: Optional[str] = None    # 'none' | 'industry' | 'industry+mktcap'
    time_align: Optional[str] = None        # 't+1' | 't+5' | 'week_ahead'
    data_window: Optional[Tuple[str, str]] = None  # ('2010-01-01', '2020-12-31')

    # ── L1 ortho 开关 (M3 修正: ortho 不走 module_enabled, 单独控制) ──
    ortho_enabled: Optional[bool] = None    # None=不改; False=关闭正交化 (覆盖 OrthogonalizationConfig.enabled)

    # ── Baseline ──
    baseline_level: Optional[str] = None    # 'B0' | 'B1' | 'B2' | 'B3'
```

#### 2.2.2 AblationResult (单次实验结果)

```python
@dataclass
class AblationResult:
    """单次消融实验结果"""
    config: AblationConfig
    metrics: Dict[str, float]           # 聚合指标
    ic_series: np.ndarray               # IC 时间序列 (用于 bootstrap)
    ls_return_series: np.ndarray        # 多空收益序列 (long-short returns, 用于 bootstrap 计算 Sharpe; 非Sharpe 值序列)
    rho_step: Dict[str, float]          # 各步骤的排序保持性 ρ_step
    ortho_diagnostics: Dict[str, float] # condition_number + VRR
    n_factors: int                      # 因子数
    n_periods: int                      # 期数
    runtime_sec: float                  # 运行时间

    # metrics 包含:
    # 'ic_mean', 'ic_std', 'icir', 'sharpe_ls', 'sharpe_lo',
    # 'turnover_mean', 'max_drawdown', 'hit_rate'
```

#### 2.2.3 AblationComparison (显著性比较结果)

```python
@dataclass
class AblationComparison:
    """两个 AblationResult 的显著性比较"""
    experiment: str                     # 实验名
    reference: str                      # 参照名 (如 "B3_full" 或 "B0_raw")
    delta_ic: float                     # ΔIC
    delta_sharpe: float                 # ΔSharpe
    # Ledoit-Wolf HAC
    t_stat_hac: float                   # HAC t 统计量
    p_value_hac: float                  # HAC p 值 (双侧)
    # Bootstrap
    bootstrap_ci_low: float             # bootstrap 95% CI 下界
    bootstrap_ci_high: float            # bootstrap 95% CI 上界
    p_value_bootstrap: float            # bootstrap p 值
    # 判定
    is_significant: bool                # 综合判定 (HAC + bootstrap 双侧 p < alpha)
```

#### 2.2.4 AblationRunner (核心引擎)

```python
class AblationRunner:
    """消融实验运行器 — 独立于 fit/transform 循环

    架构: 与 CUSUMDriftMonitor 一致, 作为事后诊断/评估工具, 不侵入管线.
    复用: factor_metrics.py (IC/ICIR/Sharpe) + multiple_testing.py (BH-FDR)

    Usage:
        runner = AblationRunner(base_config=PipelineV2Config())
        results = runner.run_l1(factor_data, fwd_returns, industry_data)
        comparison = runner.compare(results, reference=results[-1])
        report = runner.generate_report(results, comparison)
    """

    def __init__(
        self,
        base_config: PipelineV2Config,
        alpha: float = 0.05,
        n_bootstrap: int = 1000,
        block_size: Optional[int] = None,   # circular block bootstrap 块大小 (None = auto)
        n_jobs: int = 1,                    # bootstrap 并行 (joblib)
        random_seed: int = 42,
    ):
        self.base_config = base_config
        self.alpha = alpha
        self.n_bootstrap = n_bootstrap
        self.block_size = block_size
        self.n_jobs = n_jobs
        self.random_seed = random_seed
        self._results: List[AblationResult] = []

    def run_single(
        self,
        config: AblationConfig,
        factor_data: Dict[str, pd.DataFrame],
        fwd_returns: pd.DataFrame,
        industry_data: Optional[pd.Series] = None,
    ) -> AblationResult:
        """运行单次消融实验

        流程:
        1. 从 base_config 构建消融后的 config (覆盖 module_enabled/routing/参数)
        2. 实例化 FactorProcessingPipelineV2(config)
        3. fit_transform(factor_data)
        4. 计算指标 (IC/ICIR/Sharpe/turnover/drawdown/ρ_step/ortho)
        5. 返回 AblationResult
        """

    def run_l1(
        self,
        factor_data: Dict[str, pd.DataFrame],
        fwd_returns: pd.DataFrame,
        industry_data: Optional[pd.Series] = None,
        b3_full_result: Optional[AblationResult] = None,
    ) -> List[AblationResult]:
        """L1 组件消融: 5 模块逐个关闭 + B3 完整管线参照

        返回 6 个 AblationResult:
        - B3_full (全部启用, 参照; M6 修正: 若 b3_full_result 提供, 引用复用)
        - L1_imputer_off
        - L1_winsorizer_off
        - L1_scaler_off
        - L1_neutralizer_off
        - L1_orthogonalizer_off
        """

    def run_l2(
        self,
        factor_data: Dict[str, pd.DataFrame],
        fwd_returns: pd.DataFrame,
        industry_data: Optional[pd.Series] = None,
        b3_full_result: Optional[AblationResult] = None,
    ) -> List[AblationResult]:
        """L2 路由消融: 5 配置

        返回 5 个 AblationResult:
        - L2_all_static (全 static 管道)
        - L2_all_dynamic (全 dynamic 管道)
        - L2_all_mixed (全 mixed 管道)
        - L2_random_routing (随机路由, seed=42)
        - L2_full_routing (完整 5 叉路由, 参照)
        """

    def run_l4_oat(
        self,
        factor_data: Dict[str, pd.DataFrame],
        fwd_returns: pd.DataFrame,
        industry_data: Optional[pd.Series] = None,
        b3_full_result: Optional[AblationResult] = None,
    ) -> List[AblationResult]:
        """L4 前置处理 OAT 单维消融: 6 自由度

        每个自由度单独消融, 其余固定为默认.
        返回 ~20 个 AblationResult (6 自由度 × ~3-4 选项 + 1 baseline; M6 修正: baseline 引用复用 B3_full)
        """

    def run_l3(
        self,
        factor_data: Dict[str, pd.DataFrame],
        fwd_returns: pd.DataFrame,
        industry_data: Optional[pd.Series] = None,
        b3_full_result: Optional[AblationResult] = None,
    ) -> List[AblationResult]:
        """L3 参数消融 (依赖 T3 CUSUM 已完成)

        4 参数组: CUSUM k/h / EWMA / 5 叉阈值 / winsorize 比例
        返回 ~25 个 AblationResult (M4 修正: 含 EWMA halflife 3 + alpha 5 + 5叉阈值 3; M6 修正: baseline 引用复用 B3_full)
        """

    def run_baselines(
        self,
        factor_data: Dict[str, pd.DataFrame],
        fwd_returns: pd.DataFrame,
        industry_data: Optional[pd.Series] = None,
    ) -> List[AblationResult]:
        """B0-B3 Baseline 阶梯

        - B0: 原始因子 + dropna (最小处理)
        - B1: 仅 imputer
        - B2: imputer + Z-score
        - B3: 完整管线 (默认配置, 参照)
        """

    def compare(
        self,
        experiment: AblationResult,
        reference: AblationResult,
    ) -> AblationComparison:
        """Ledoit-Wolf HAC + bootstrap 显著性比较

        对 IC 序列和 Sharpe 序列做:
        1. HAC 标准误 (Newey-West) → t 统计量 + p 值
        2. Circular block bootstrap (B=1000) → CI + p 值
        3. 综合判定: 两侧 p 均显著 → is_significant=True
        """

    def compare_all(
        self,
        results: List[AblationResult],
        reference: AblationResult,
    ) -> List[AblationComparison]:
        """批量比较 + BH-FDR 校正

        对所有 results vs reference 做 compare, 然后对 p 值列表做 BH-FDR 校正.
        复用 backtest/multiple_testing.py apply_bh_fdr.
        """

    def generate_report(
        self,
        results: List[AblationResult],
        comparisons: List[AblationComparison],
    ) -> str:
        """生成 Markdown 消融报告"""

    def get_diagnostics(self) -> Dict[str, Any]:
        """获取诊断信息

        Returns:
            {
                'n_experiments': int,
                'total_runtime_sec': float,
                'base_config': dict,
                'alpha': float,
                'n_bootstrap': int,
                'block_size': int,
                'results_summary': List[dict],  # 每个实验的 name + key metrics
            }
        """
```

### 2.3 算法实现

#### 2.3.1 Ledoit-Wolf (2008) HAC 标准误

**数学公式** (Ledoit & Wolf 2008, §2):

对两个策略 a (消融) 和 b (参照) 的 Sharpe 比率差 ΔSR = SR_a - SR_b, 检验 H₀: ΔSR = 0。

Sharpe 比率 SR = μ / σ, 其中 μ = E[r_t], σ = √Var[r_t]。

梯度向量 (对 (μ, σ²) 参数化, 与矩条件 h_t 第二项 $(r-\mu)^2-\sigma^2$ 一致):

$$
\nabla g = \begin{pmatrix} \partial SR / \partial \mu \\ \partial SR / \partial \sigma^2 \end{pmatrix} = \begin{pmatrix} 1/\sigma \\ -\mu/(2\sigma^3) \end{pmatrix}
$$

> **链式法则推导**: SR = μ/σ, 其中 σ = √(σ²).
> - ∂SR/∂μ = 1/σ
> - ∂SR/∂σ = -μ/σ²
> - ∂σ/∂σ² = 1/(2σ)  (因 σ = (σ²)^(1/2))
> - ∂SR/∂σ² = (∂SR/∂σ)·(∂σ/∂σ²) = (-μ/σ²)·(1/(2σ)) = **-μ/(2σ³)**
>
> 注意: 若矩条件用 σ (而非 σ²) 作参数, 则梯度第二项为 -μ/σ²; 但本实现矩条件第二项为 $(r-\mu)^2-\sigma^2$ (关于方差 σ²), 故梯度必须对 σ² 求导, 即 -μ/(2σ³).

> **归属与参数化说明** (阶段 4 学术核实补充):
> 本实现基于 Ledoit-Wolf (2008) 的 delta method 框架, 但有两处参数化差异:
> 1. **参数化**: 本实现采用 (μ, σ²) (中心化方差), 原文采用 (μ, γ=E[r²]) (非中心化二阶矩). 两者渐近等价, 但小样本数值性质可能不同.
> 2. **HAC 核**: 本实现采用 Newey-West (1987) Bartlett 核, 原文采用 Andrews (1991) 核估计. 两者均为 HAC 估计器, Bartlett 核是 Andrews 核族的特例.
> 数学正确性: 链式法则推导无误, Var(SR) = ∇g^T · Σ_HAC · ∇g 形式正确.

HAC 协方差矩阵 (Newey-West 1987, Bartlett 核):

$$
\hat{\Sigma}_{HAC} = \frac{1}{T} \sum_{t=1}^{T} \hat{h}_t \hat{h}_t^T + \frac{1}{T} \sum_{\ell=1}^{q} \omega_\ell \sum_{t=\ell+1}^{T} (\hat{h}_t \hat{h}_{t-\ell}^T + \hat{h}_{t-\ell} \hat{h}_t^T)
$$

其中 $\hat{h}_t = (r_t - \hat{\mu}, (r_t - \hat{\mu})^2 - \hat{\sigma}^2)^T$, 权重 $\omega_\ell = 1 - \ell/(q+1)$ (Bartlett 核), 带宽 $q = \lfloor 4(T/100)^{2/9} \rfloor$ (Newey-West 自动带宽)。

Sharpe 方差:

$$
\widehat{Var}(SR) = \nabla g^T \cdot \hat{\Sigma}_{HAC} \cdot \nabla g
$$

差值方差 (考虑协方差):

$$
\widehat{Var}(\Delta SR) = \widehat{Var}(SR_a) + \widehat{Var}(SR_b) - 2 \widehat{Cov}(SR_a, SR_b)
$$

t 统计量:

$$
t = \frac{\Delta SR}{\sqrt{\widehat{Var}(\Delta SR)}}
$$

**Python 实现** (手工实现为 Sharpe 差检验的唯一主路径; statsmodels 仅作均值差参考, 见下文):

```python
import numpy as np
from typing import Tuple

def ledoit_wolf_hac_test(
    returns_a: np.ndarray,
    returns_b: np.ndarray,
    alpha: float = 0.05,
) -> Tuple[float, float]:
    """Ledoit-Wolf (2008) HAC 检验: H0: SR_a = SR_b

    Args:
        returns_a: 策略 a 的收益序列 (T,)
        returns_b: 策略 b 的收益序列 (T,)
        alpha: 显著性水平

    Returns:
        (t_stat, p_value): HAC t 统计量 + 双侧 p 值

    Reference:
        Ledoit, O. & Wolf, M. (2008). "Robust performance hypothesis testing
        with the Sharpe ratio." J. Empirical Finance 15(5):850-859.
    """
    from scipy import stats as sp_stats

    T = len(returns_a)
    q = max(1, int(4 * (T / 100) ** (2 / 9)))  # Newey-West 自动带宽

    def _sr_gradient(r: np.ndarray) -> np.ndarray:
        """计算 SR 梯度 + HAC 协方差"""
        mu = np.mean(r)
        sigma = np.std(r, ddof=1)
        if sigma < 1e-12:
            return np.array([0.0, 0.0]), np.zeros((2, 2)), mu / sigma if sigma > 0 else 0.0

        # 矩条件 h_t = (r_t - mu, (r_t - mu)^2 - sigma^2)
        h = np.column_stack([
            r - mu,
            (r - mu) ** 2 - sigma ** 2,
        ])  # shape (T, 2)

        # Newey-West HAC 协方差
        S = np.zeros((2, 2))
        # lag 0
        S = h.T @ h / T
        # lag 1..q
        for ell in range(1, q + 1):
            omega = 1 - ell / (q + 1)  # Bartlett 核
            cross = h[ell:].T @ h[:-ell] / T
            S += omega * (cross + cross.T)

        # SR 梯度 (对 (μ, σ²) 参数化, 与矩条件 h_t 第二项 (r-μ)²-σ² 一致)
        # ∂SR/∂μ = 1/σ;  ∂SR/∂σ² = -μ/(2σ³)  (链式法则: ∂SR/∂σ · ∂σ/∂σ²)
        grad = np.array([1.0 / sigma, -mu / (2.0 * sigma ** 3)])

        # Var(SR) = grad^T S grad
        var_sr = grad @ S @ grad

        return grad, S, mu / sigma

    grad_a, S_a, sr_a = _sr_gradient(returns_a)
    grad_b, S_b, sr_b = _sr_gradient(returns_b)

    # 协方差 Cov(SR_a, SR_b) = grad_a^T S_ab grad_b
    # S_ab: HAC 交叉协方差
    mu_a, mu_b = np.mean(returns_a), np.mean(returns_b)
    sig_a, sig_b = np.std(returns_a, ddof=1), np.std(returns_b, ddof=1)
    h_a = np.column_stack([returns_a - mu_a, (returns_a - mu_a) ** 2 - sig_a ** 2])
    h_b = np.column_stack([returns_b - mu_b, (returns_b - mu_b) ** 2 - sig_b ** 2])

    S_ab = h_a.T @ h_b / T
    for ell in range(1, q + 1):
        omega = 1 - ell / (q + 1)
        S_ab += omega * (h_a[ell:].T @ h_b[:-ell] / T + h_a[:-ell].T @ h_b[ell:] / T)

    cov_sr = grad_a @ S_ab @ grad_b
    var_a = grad_a @ S_a @ grad_a
    var_b = grad_b @ S_b @ grad_b

    var_delta = var_a + var_b - 2 * cov_sr
    if var_delta < 1e-15:
        return 0.0, 1.0

    delta_sr = sr_a - sr_b
    t_stat = delta_sr / np.sqrt(var_delta)
    p_value = 2 * (1 - sp_stats.norm.cdf(abs(t_stat)))  # 双侧

    return float(t_stat), float(p_value)
```

**statsmodels 均值差参考检验** (非 Sharpe 差的等价路径, 仅作 Δμ 对照):

> **重要**: statsmodels `OLS(diff, X).fit(cov_type='HAC')` 检验的是 **均值差** H₀: E[r_a - r_b] = 0 (即 Δμ = 0),
> 而 Ledoit-Wolf (2008) HAC 检验的是 **Sharpe 比率差** H₀: SR_a = SR_b (即 ΔSR = μ₁/σ₁ - μ₂/σ₂ = 0).
> 两者检验的统计量不同 (Δμ vs ΔSR), **不是等价路径**.
> 因此 `ledoit_wolf_hac_test` (手工实现) 是 Sharpe 差检验的**唯一主路径**;
> statsmodels 路径仅作为**均值差参考检验** (reference test), 用于对照 Δμ 是否显著, 不能替代 Sharpe 差检验.

```python
# statsmodels 已是 REQUIRED 依赖 (ADR-014)
from statsmodels.regression.linear_model import OLS

# 均值差参考检验 (非 Sharpe 差等价路径!):
# 对 (r_a - r_b) 做 OLS (仅截距), 用 HAC robust standard error
# 检验 H0: Δμ = E[r_a - r_b] = 0  (注意: 这是均值差, 不是 Sharpe 差)
def mean_diff_hac_statsmodels(returns_a, returns_b, maxlags=None):
    """均值差 HAC 参考检验: H0: E[r_a - r_b] = 0  (Δμ, 非 ΔSR)

    注意: 此函数检验均值差 Δμ, 不是 Ledoit-Wolf (2008) 的 Sharpe 差 ΔSR.
    Sharpe 差检验必须用 ledoit_wolf_hac_test (手工实现), 两者不可互换.
    """
    T = len(returns_a)
    if maxlags is None:
        maxlags = max(1, int(4 * (T / 100) ** (2 / 9)))
    diff = returns_a - returns_b
    X = np.ones((T, 1))  # 仅截距
    model = OLS(diff, X).fit(cov_type='HAC', cov_kwds={'maxlags': maxlags})
    t_stat = model.tvalues[0]
    p_value = model.pvalues[0]
    return float(t_stat), float(p_value)
```

**决策**: Sharpe 差检验 (ΔSR) **唯一主路径** = `ledoit_wolf_hac_test` (手工 Newey-West + delta method).
`mean_diff_hac_statsmodels` 仅作**均值差参考检验** (Δμ 对照), 不替代 Sharpe 差检验, 也不设为优先.
(与 `_manual_ljungbox` 模式一致: 手工实现为唯一主路径, statsmodels 仅在检验对象相同时才作替代.)

#### 2.3.2 Circular Block Bootstrap (Politis & Romano 1992)

**数学公式**:

对 IC 时间序列 {IC_t}_{t=1}^{T}, 用 circular block bootstrap 保留时序依赖:

1. 将序列首尾相连形成环
2. 随机选取起始点, 连续取 `l` 个点作为一个 block (l = block_size)
3. 重复直到取满 T 个点, 形成一个 bootstrap 样本 {IC*_t}
4. 计算 ΔIC* = mean(IC*_a) - mean(IC*_b)
5. 重复 B = 1000 次, 得到 {ΔIC*_(b)}_{b=1}^{B}
6. p 值 = fraction(|ΔIC*| > |ΔIC_observed|)
7. 95% CI = [percentile(ΔIC*, 2.5), percentile(ΔIC*, 97.5)]

**块大小** (Politis & White 2004 自动选择):

$$
\hat{l}_{opt} = \left\lfloor 1.1448 \left( \hat{\rho}^{1/3} + \hat{\rho}^{2/3} \right) T^{1/3} \right\rfloor
$$

其中 $\hat{\rho}$ 为 AR(1) 系数。默认块大小 `l = max(1, int(T ** (1/3)))` (简化版)。

**Python 实现** (numpy):

```python
def circular_block_bootstrap_delta(
    series_a: np.ndarray,
    series_b: np.ndarray,
    n_bootstrap: int = 1000,
    block_size: Optional[int] = None,
    random_seed: int = 42,
    statistic: str = 'mean',   # 'mean' | 'sharpe'
) -> Tuple[float, float, float, float]:
    """Circular block bootstrap for Δstat(a) - Δstat(b)

    Args:
        series_a: 策略 a 的 IC/Sharpe 序列 (T,)
        series_b: 策略 b 的 IC/Sharpe 序列 (T,)
        n_bootstrap: bootstrap 次数 (默认 1000)
        block_size: 块大小 (None = auto, T^(1/3))
        random_seed: 随机种子
        statistic: 'mean' (ΔIC) 或 'sharpe' (ΔSharpe)

    Returns:
        (delta_obs, ci_low, ci_high, p_value)
        delta_obs: 观测到的差值
        ci_low, ci_high: 95% bootstrap CI
        p_value: 双侧 p 值
    """
    rng = np.random.default_rng(random_seed)
    T = len(series_a)
    if block_size is None:
        block_size = max(1, int(T ** (1 / 3)))

    a_clean = series_a[~np.isnan(series_a)]
    b_clean = series_b[~np.isnan(series_b)]

    def _stat(s: np.ndarray) -> float:
        if statistic == 'sharpe':
            std = np.std(s, ddof=1)
            return np.mean(s) / std if std > 1e-12 else 0.0
        return np.mean(s)

    delta_obs = _stat(a_clean) - _stat(b_clean)

    # Circular block bootstrap
    n_blocks = int(np.ceil(T / block_size))
    deltas_boot = np.empty(n_bootstrap)

    for b in range(n_bootstrap):
        # 随机起始点, 环形采样
        starts = rng.integers(0, T, size=n_blocks)
        idx = np.concatenate([
            (np.arange(block_size) + s) % T for s in starts
        ])[:T]

        boot_a = series_a[idx]
        boot_b = series_b[idx]
        # dropna in bootstrap sample
        ba = boot_a[~np.isnan(boot_a)]
        bb = boot_b[~np.isnan(boot_b)]
        if len(ba) < 3 or len(bb) < 3:
            deltas_boot[b] = np.nan
            continue
        deltas_boot[b] = _stat(ba) - _stat(bb)

    deltas_boot = deltas_boot[~np.isnan(deltas_boot)]
    if len(deltas_boot) < 10:
        return delta_obs, np.nan, np.nan, 1.0

    ci_low = float(np.percentile(deltas_boot, 2.5))
    ci_high = float(np.percentile(deltas_boot, 97.5))
    p_value = float(np.mean(np.abs(deltas_boot - np.mean(deltas_boot)) >= np.abs(delta_obs)))

    return float(delta_obs), ci_low, ci_high, p_value
```

#### 2.3.3 排序保持性 ρ_step (§6.3.4)

**数学公式**:

对管线中每个步骤 s (imputer/winsorizer/scaler/neutralizer/orthogonalizer), 测量该步骤前后因子截面排序的 Spearman 相关性:

$$
\rho_{step}^{(s)} = \frac{1}{T} \sum_{t=1}^{T} \text{Spearman}(f_{t,\text{before}}^{(s)}, f_{t,\text{after}}^{(s)})
$$

- ρ_step ≈ 1.0: 步骤保留截面排序 (单调变换)
- ρ_step < 0.95: 步骤改变排序 (如中性化/正交化预期会降低 ρ)
- ρ_step ≈ 0: 步骤完全打乱排序 (异常, 需调查)

**方向与范围明确** (M1 修正):
- ρ_step 是**测量指标** (非可调参数), 取值范围 [-1.0, 1.0], 实际场景中 ∈ [0, 1.0]
- **测量方向**: 对每个步骤 s, 计算 Spearman(f_before, f_after) — 即步骤**前→后**的截面排序相关性
- **变化方向**: ρ_step 从 1.0 (恒等变换, 步骤关闭) **递减** 向 0.0 (完全打乱排序); 步骤变换越激进, ρ_step 越低
- **消融对照**: 模块关闭 (enabled=False) 时该步骤 ρ_step = 1.0 (恒等); 模块开启时 ρ_step 下降, 降幅反映该模块对排序的改变程度
- **ρ_step 参照值** (用于消融判定): `rho_ref = {'identity': 1.0, 'imputer': 0.99, 'winsorizer': 0.95, 'scaler': 0.99, 'neutralizer': 0.85, 'orthogonalizer': 0.70}`

**预期范围** (§6.3.4 推测, 消融实测验证):
- Imputer: ρ ≈ 0.99-1.00 (仅填充, 不改变已有值排序)
- Winsorizer: ρ ≈ 0.95-1.00 (截断极端值, 轻微改变)
- Scaler: ρ ≈ 1.00 (标准化是单调变换)
- Neutralizer: ρ ≈ 0.80-0.95 (剥离风险暴露, 改变排序)
- Orthogonalizer: ρ ≈ 0.50-0.90 (跨因子正交化, 显著改变排序)

**Python 实现**:

```python
from scipy.stats import spearmanr

def compute_rho_step(
    factor_before: pd.DataFrame,
    factor_after: pd.DataFrame,
) -> float:
    """计算单步骤的排序保持性 ρ_step

    Args:
        factor_before: 步骤前的因子值 (n_stocks, T)
        factor_after: 步骤后的因子值 (n_stocks, T)

    Returns:
        ρ_step: 时间平均的 Spearman 秩相关系数
    """
    # 对齐
    common = factor_before.index.intersection(factor_after.index)
    cols = factor_before.columns.intersection(factor_after.columns)
    fb = factor_before.loc[common, cols]
    fa = factor_after.loc[common, cols]

    rhos = []
    for col in cols:
        b = fb[col].dropna()
        a = fa.loc[b.index, col].dropna()
        common_idx = a.index.intersection(b.index)
        if len(common_idx) < 3:
            continue
        rho, _ = spearmanr(b.loc[common_idx], a.loc[common_idx])
        if not np.isnan(rho):
            rhos.append(rho)

    return float(np.mean(rhos)) if rhos else np.nan
```

**集成方式**: AblationRunner 在 `run_single` 中通过 `_BaseFactorPipeline.get_intermediate_data()` 获取每个步骤的中间状态, 计算相邻步骤的 ρ_step。

#### 2.3.4 正交化诊断: condition_number + VRR

复用 `OrthogonalizerAdapter` 的既有诊断 (adapters.py:972 `get_diagnostics`):

```python
def _collect_ortho_diagnostics(
    pipeline: FactorProcessingPipelineV2,
    factor_data: Dict[str, pd.DataFrame],
) -> Dict[str, float]:
    """收集正交化诊断: condition_number + VRR

    复用 OrthogonalizerAdapter.get_diagnostics() (v2.5.0 ADR-020)
    """
    for hook in pipeline.post_transform_hooks:
        if hasattr(hook, 'get_diagnostics') and isinstance(hook, OrthogonalizerAdapter):
            return hook.get_diagnostics()
    return {'condition_number': np.nan, 'vrr_mean': np.nan}
```

### 2.4 指标计算 (复用 factor_metrics.py)

| 指标 | 函数 | 来源 |
|------|------|------|
| IC (rank/pearson) | `compute_rank_ic` / `compute_pearson_ic` | factor_metrics.py:38/70 |
| IC 序列 | `compute_ic_series` | factor_metrics.py:109 |
| ICIR | `compute_icir` | factor_metrics.py:187 |
| Turnover | `compute_turnover` | factor_metrics.py:269 |
| Long-short returns | `compute_long_short_returns` | factor_metrics.py:298 |
| Sharpe (long-short) | `compute_spread` / 自行计算 | factor_metrics.py:370 |
| Hit rate | `compute_hit_rate` | factor_metrics.py:404 |
| ρ_step | `compute_rho_step` (本文件新增) | §2.3.3 |
| condition_number | `OrthogonalizerAdapter.get_diagnostics` | adapters.py:972 |
| VRR | 同上 | adapters.py:972 |

### 2.5 L2 路由消融实现 (随机路由控制组)

**随机路由** (routing_mode='random'): 固定 seed, 对每个因子随机分配管道权重。

```python
def _apply_routing_mode(
    config: PipelineV2Config,
    factor_names: List[str],
    routing_mode: str,
    random_seed: Optional[int] = None,
) -> PipelineV2Config:
    """根据 routing_mode 修改 config

    - 'full': 不修改 (使用完整 5 叉路由)
    - 'static'/'dynamic'/'mixed': 强制分类为单一类型
    - 'random': 随机分配类型 (seed 固定, 控制组)
    """
    config = copy.deepcopy(config)

    if routing_mode == 'full':
        return config  # 不修改

    if routing_mode == 'random':
        # 随机路由: 后处理覆盖分类结果
        # 在 AblationRunner.run_single 中, fit 后修改 factor_classifications
        config._ablation_random_routing = True
        config._ablation_random_seed = random_seed or 42
        return config

    # 全 static/dynamic/mixed: 在 fit 后覆盖分类
    config._ablation_force_type = routing_mode  # 'static' | 'dynamic' | 'mixed'
    return config
```

**实现位置**: `AblationRunner.run_single` 中, `pipeline.fit()` 后, 若 `routing_mode != 'full'`, 修改 `pipeline.factor_classifications` 强制为单一类型或随机类型。

### 2.6 外部依赖

| 依赖 | 版本要求 | 用途 | 是否新增 |
|------|---------|------|---------|
| numpy | >=1.22 | bootstrap + HAC | 否 (已有) |
| scipy | >=1.7 | Spearman + 正态 CDF | 否 (已有) |
| statsmodels | >=0.13 | OLS + HAC 协方差 | 否 (已有, ADR-014 REQUIRED) |
| pandas | >=2.0 | DataFrame 操作 | 否 (已有) |
| joblib | >=1.0 (可选) | bootstrap 并行 | 否 (可选, factor_significance.py 已用) |
| copy | stdlib | deepcopy config | 否 |

**无新增依赖**。所有算法用 numpy/scipy/statsmodels 实现。

### 2.7 性能评估

| 消融层 | 组合数 | 单次管线运行 | bootstrap (1000 次) | 预期总时间 |
|--------|--------|-------------|-------------------|-----------|
| L1 | 6 | ~2s | ~0.5s (IC 序列重采样) | ~15s |
| L2 | 5 | ~2s | ~0.5s | ~13s |
| L3 | ~25 | ~2s | ~0.5s | ~63s |
| L4 OAT | ~20 | ~2s | ~0.5s | ~50s |
| B0-B3 | 4 | ~1s (B0 无管线) | ~0.5s | ~6s |
| **总计** | **~60** | | | **~2.5 min** |

**对比**: 全因子 L4 = 972 组合 × 2s = ~32 min (不可行) → OAT 降至 ~20 组合 × 2s = 40s (可行)。

**bootstrap 性能**: 1000 次重采样 IC 序列 (~240 点) 纯 numpy, 单次 ~0.5ms, 1000 次 ~0.5s。若用 joblib 并行 (n_jobs=4), 降至 ~0.15s。

### 2.8 E2 测试计划 (TDD)

**文件**: `tests/test_backtest/test_ablation_runner.py` (新建)

#### E2-T1 Ledoit-Wolf HAC 检验

```python
class TestLedoitWolfHAC:
    def test_identical_series_zero_t(self):
        """两个相同序列 → ΔSR=0, t≈0, p>0.05"""
    def test_better_series_significant(self):
        """a 明显优于 b → t>0, p<0.05"""
    def test_hac_vs_naive_t_different(self):
        """HAC t 与朴素 t 不同 (时序依赖场景)"""
    def test_statsmodels_mean_diff_is_reference_only(self):
        """statsmodels HAC 路径仅检验均值差 Δμ (非 ΔSR), 作参考; 不与手工 Sharpe 差检验等价"""
    def test_auto_bandwidth(self):
        """T=240 → q≈4 (Newey-West 自动带宽)"""
```

#### E2-T2 Circular Block Bootstrap

```python
class TestCircularBootstrap:
    def test_identical_series_p_value_high(self):
        """两个相同序列 → p_value > 0.05"""
    def test_significant_difference_p_low(self):
        """明显差异 → p_value < 0.05"""
    def test_ci_covers_zero_when_identical(self):
        """相同序列 → 95% CI 包含 0"""
    def test_ci_excludes_zero_when_different(self):
        """明显差异 → 95% CI 不包含 0"""
    def test_block_size_auto(self):
        """T=240 → block_size ≈ 6 (240^(1/3))"""
    def test_reproducible_with_seed(self):
        """相同 seed → 相同结果"""
    def test_sharpe_statistic_mode(self):
        """statistic='sharpe' → 计算 Sharpe 差而非 mean 差"""
```

#### E2-T3 ρ_step 排序保持性

```python
class TestRhoStep:
    def test_identity_transform_rho_one(self):
        """恒等变换 → ρ_step = 1.0"""
    def test_monotonic_transform_rho_one(self):
        """单调变换 (z-score) → ρ_step ≈ 1.0"""
    def test_shuffled_rho_near_zero(self):
        """打乱顺序 → ρ_step ≈ 0"""
    def test_partial_reorder_rho_between(self):
        """部分重排 → ρ_step ∈ (0, 1)"""
    def test_nan_handling(self):
        """含 NaN → 跳过, 不崩溃"""
```

#### E2-T4 AblationConfig + AblationResult

```python
class TestAblationConfig:
    def test_default_config_is_baseline(self):
        """默认 AblationConfig → layer='baseline', 全启用"""
    def test_l1_config_module_enabled(self):
        """L1 config → module_enabled 指定关闭"""
    def test_l2_config_routing_mode(self):
        """L2 config → routing_mode='random' + seed"""
```

#### E2-T5 AblationRunner 单次运行

```python
class TestAblationRunnerSingle:
    def test_run_single_returns_result(self):
        """run_single → AblationResult 含全部 metrics"""
    def test_run_single_b3_full_pipeline(self):
        """B3 完整管线 → IC 非 NaN, ICIR 非 NaN"""
    def test_run_single_b0_raw_dropna(self):
        """B0 原始+dropna → 无管线处理, IC 直接计算"""
    def test_rho_step_collected(self):
        """AblationResult.rho_step 含 5 个步骤"""
    def test_ortho_diagnostics_collected(self):
        """AblationResult.ortho_diagnostics 含 condition_number + VRR"""
```

#### E2-T6 AblationRunner 批量运行

```python
class TestAblationRunnerBatch:
    def test_run_l1_returns_6_results(self):
        """run_l1 → 6 个 AblationResult (5 消融 + 1 参照)"""
    def test_run_l2_returns_5_results(self):
        """run_l2 → 5 个 AblationResult"""
    def test_run_baselines_returns_4_results(self):
        """run_baselines → 4 个 (B0-B3)"""
    def test_run_l4_oat_returns_20_plus(self):
        """run_l4_oat → ≥ 20 个 (6 DOF × 3-4 选项 + 1 baseline)"""
```

#### E2-T7 比较与 BH-FDR

```python
class TestAblationCompare:
    def test_compare_identical_not_significant(self):
        """相同实验 vs 参照 → is_significant=False"""
    def test_compare_better_significant(self):
        """明显优于参照 → is_significant=True"""
    def test_compare_all_bh_fdr_correction(self):
        """compare_all → p 值经 BH-FDR 校正"""
    def test_compare_all_uses_shared_module(self):
        """compare_all 调用 backtest.multiple_testing.apply_bh_fdr"""
```

#### E2-T8 get_diagnostics

```python
class TestGetDiagnostics:
    def test_diagnostics_has_n_experiments(self):
        """get_diagnostics → 含 n_experiments"""
    def test_diagnostics_has_total_runtime(self):
        """get_diagnostics → 含 total_runtime_sec"""
    def test_diagnostics_has_results_summary(self):
        """get_diagnostics → 含 results_summary 列表"""
```

### 2.9 E2 验收标准

- [ ] E2-T1 ~ E2-T8 测试全部 Red → Green
- [ ] `backtest/ablation_runner.py` 新建, 含 AblationConfig/AblationResult/AblationComparison/AblationRunner
- [ ] Ledoit-Wolf HAC Sharpe 差检验: 手工实现 (`ledoit_wolf_hac_test`) 为唯一主路径; statsmodels 仅作均值差 Δμ 参考检验 (非等价)
- [ ] Circular block bootstrap: B=1000, 可重现 (seed), 块大小自动
- [ ] ρ_step: 5 步骤均能计算, 恒等变换 = 1.0
- [ ] 复用 `factor_metrics.py` (IC/ICIR/Sharpe) + `multiple_testing.py` (BH-FDR)
- [ ] `get_diagnostics` 返回完整诊断信息
- [ ] 全量回归 934+ + ~25 新增 = ~959 passed

---

## 3. E3: L1 组件消融

### 3.1 目标

逐模块关闭 (5 组对比), 测量每个模块的边际贡献。参照组 = B3 完整管线。

### 3.2 消融配置

| 实验名 | 关闭模块 | module_enabled | 验证目标 |
|--------|---------|---------------|---------|
| L1_imputer_off | Imputer | `{'imputer': False}` | 插补的边际贡献 |
| L1_winsorizer_off | Winsorizer | `{'winsorizer': False}` | 极值处理的边际贡献 |
| L1_scaler_off | Scaler | `{'scaler': False}` | 标准化的边际贡献 |
| L1_neutralizer_off | Neutralizer | `{'neutralizer': False}` | 风险剥离的边际贡献 |
| L1_orthogonalizer_off | Orthogonalizer | `OrthogonalizationConfig(enabled=False)` (M3 修正: ortho 不走 module_enabled, 见下) | 正交化的边际贡献 |
| B3_full (参照, 引用复用, 见 §7.2 M6 修正) | 无 | `None` (全启用) | 完整管线 baseline (不在 run_l1 中重复运行, 引用 §7.3 结果) |

> **M3 修正 — ortho 关闭路径** (参考 `adapters.py:796`):
> `OrthogonalizerAdapter` 在 v2.5.0 (ADR-020) 已有 `enabled` 开关, 但它读取的是 `OrthogonalizationConfig.enabled`,
> **不**走 `module_enabled['orthogonalizer']` (与 Imputer/Winsorizer/Scaler/Neutralizer 不同).
> 因此 L1 ortho 消融必须通过 `OrthogonalizationConfig(enabled=False)` (或等效 `OrthogonalizerAdapter(enabled=False)`) 关闭,
> 不能仅设 `module_enabled['orthogonalizer']=False` (该字段对 ortho 无效, 会被忽略).
> 见 §1.3.4: "E1 **不改动**此 Adapter, 仅在 AblationRunner 中通过 `OrthogonalizationConfig.enabled` 控制."

### 3.3 代码改动

**文件**: `backtest/ablation_runner.py` — `AblationRunner.run_l1` 方法

```python
def run_l1(self, factor_data, fwd_returns, industry_data=None,
           b3_full_result: Optional[AblationResult] = None):
    results = []
    # 参照: B3 完整管线 (M6 修正: 引用复用, 不重复 run_single)
    # b3_full_result 由 run_baselines 预先计算并注入; 若未提供 (独立运行 run_l1), 则回退到 run_single
    if b3_full_result is not None:
        results.append(b3_full_result)
    else:
        results.append(self.run_single(
            AblationConfig(name='B3_full', layer='L1_reference'),
            factor_data, fwd_returns, industry_data,
        ))
    # 4 模块逐个关闭 (走 module_enabled; ortho 单独处理, 见下)
    modules = ['imputer', 'winsorizer', 'scaler', 'neutralizer']
    for mod in modules:
        me = {m: True for m in modules}
        me[mod] = False
        config = AblationConfig(
            name=f'L1_{mod}_off', layer='L1', module_enabled=me,
        )
        results.append(self.run_single(config, factor_data, fwd_returns, industry_data))

    # ortho 关闭: 不走 module_enabled (OrthogonalizerAdapter 读 OrthogonalizationConfig.enabled,
    #   adapters.py:796, ADR-020). 通过 AblationConfig 新增字段 ortho_enabled=False 控制,
    #   run_single 中据此覆盖 base_config.orthogonalization_config.enabled = False
    results.append(self.run_single(
        AblationConfig(name='L1_orthogonalizer_off', layer='L1',
                       ortho_enabled=False),  # ← 新增字段, 见 AblationConfig
        factor_data, fwd_returns, industry_data,
    ))
    return results
```

> **AblationConfig 新增字段** (M3 修正): `ortho_enabled: Optional[bool] = None`
> - `None` (默认): 不修改 ortho 配置 (向后兼容)
> - `False`: 在 `run_single` 中设 `config.orthogonalization_config.enabled = False` (关闭正交化)
> - `True`: 显式启用 (与 None 等效, 仅语义清晰)

### 3.4 显著性判定

对每个消融实验 vs B3_full 参照:
- ΔIC = IC_消融 - IC_B3
- ΔSharpe = Sharpe_消融 - Sharpe_B3
- Ledoit-Wolf HAC: t 统计量 + p 值
- Bootstrap: 95% CI + p 值
- BH-FDR 校正 5 个比较 (5 模块 vs 参照)
- **判定**: 若 ΔIC 显著为负 → 模块有正贡献; 若 ΔIC 不显著 → 模块无贡献 (可移除)

### 3.5 诚实立场 (双向判定)

| 结果 | 含义 | 行动 |
|------|------|------|
| ΔIC 显著为负 | 模块有正贡献 | 保留, §6.4.2 评定维持/升级 |
| ΔIC 不显著 | 模块无贡献 | 可移除, §6.4.2 评定降级 |
| ΔIC 显著为正 | 模块有害 (过度处理) | 必须移除, §6.4.2 评定降级 |

### 3.6 E3 测试计划

```python
class TestL1Ablation:
    def test_l1_imputer_off_preserves_nan(self):
        """L1 imputer off → 输出含 NaN"""
    def test_l1_neutralizer_off_no_industry_neutral(self):
        """L1 neutralizer off → 输出未中性化"""
    def test_l1_orthogonalizer_off_no_orthogonal(self):
        """L1 orthogonalizer off → factor_dict 不变"""
    def test_l1_all_vs_b3_significant(self):
        """至少 3 个模块消融 vs B3 显著 (p<0.05)"""
    def test_l1_rho_step_neutralizer_low(self):
        """Neutralizer ρ_step < 0.95 (改变排序)"""
    def test_l1_rho_step_scaler_high(self):
        """Scaler ρ_step > 0.99 (单调变换)"""
    def test_l1_bh_fdr_applied(self):
        """5 比较的 p 值经 BH-FDR 校正"""
    def test_l1_report_generated(self):
        """generate_report 输出 Markdown 含 L1 表格"""
```

### 3.7 E3 验收标准

- [ ] 6 个 AblationResult (5 消融 + 1 参照) 全部产出
- [ ] 每个消融的 ΔIC + ΔSharpe + HAC p + bootstrap p 报告完整
- [ ] BH-FDR 校正 5 个多重比较
- [ ] ρ_step 表: 5 模块的排序保持性测量值
- [ ] 诚实立场: 允许"模块无贡献"的结论 (不强制显著)

---

## 4. E4: L2 路由消融

### 4.1 目标

5 路由配置对比, 验证 5 叉决策路由的有效性。E2 修正 (CRITICAL): 含随机路由控制组。

### 4.2 消融配置

| 实验名 | routing_mode | 说明 |
|--------|-------------|------|
| L2_all_static | `'static'` | 所有序列走 StaticFactorPipeline |
| L2_all_dynamic | `'dynamic'` | 所有序列走 DynamicFactorPipeline |
| L2_all_mixed | `'mixed'` | 所有序列走 MixedFactorPipeline |
| L2_random_routing | `'random'`, seed=42 | 随机分配管道 (控制组) |
| L2_full_routing (参照, 引用复用, 见 §7.2 M6 修正) | `'full'` | 完整 5 叉路由 (参照, 实验组); 配置 = B3_full, 不重复运行 |

### 4.3 强制路由实现

**文件**: `backtest/ablation_runner.py` — `AblationRunner.run_single` 中 fit 后修改分类

```python
def _override_routing(
    self,
    pipeline: FactorProcessingPipelineV2,
    factor_names: List[str],
    routing_mode: str,
    random_seed: Optional[int] = None,
):
    """fit 后覆盖分类结果, 强制单一类型或随机路由"""
    if routing_mode == 'full':
        return  # 不修改

    from factor_pipeline.modules.factor_fingerprint import FactorType, ClassificationResult

    if routing_mode in ('static', 'dynamic', 'mixed'):
        force_type = FactorType[routing_mode.upper()]
        for name in factor_names:
            orig = pipeline.factor_classifications.get(name)
            if orig is not None:
                # 强制 primary_type, is_hard=True
                pipeline.factor_classifications[name] = ClassificationResult(
                    primary_type=force_type,
                    primary_prob=1.0,
                    secondary_type=None,
                    secondary_prob=None,
                    is_hard=True,
                )

    elif routing_mode == 'random':
        rng = np.random.default_rng(random_seed or 42)
        types = [FactorType.STATIC, FactorType.DYNAMIC, FactorType.MIXED]
        for name in factor_names:
            rand_type = rng.choice(types)
            pipeline.factor_classifications[name] = ClassificationResult(
                primary_type=rand_type,
                primary_prob=1.0,
                secondary_type=None,
                secondary_prob=None,
                is_hard=True,
            )
```

### 4.4 判定逻辑

**参照 = L2_full_routing (实验组)**, 其余 4 个为消融:

| 比较对 | 判定 |
|--------|------|
| full vs static | 完整路由优于全 static? |
| full vs dynamic | 完整路由优于全 dynamic? |
| full vs mixed | 完整路由优于全 mixed? |
| full vs random | 完整路由优于随机路由? (E2 修正, 关键控制组) |

**关键判定**: 若 full vs random 不显著 → 路由无效 (§6.4.2 降级)。

### 4.5 E4 测试计划

```python
class TestL2Ablation:
    def test_all_static_uses_static_pipeline(self):
        """routing_mode='static' → 所有序列走 StaticFactorPipeline"""
    def test_all_dynamic_uses_dynamic_pipeline(self):
        """routing_mode='dynamic' → 所有序列走 DynamicFactorPipeline"""
    def test_random_routing_reproducible(self):
        """相同 seed → 相同随机分配"""
    def test_random_routing_different_from_full(self):
        """随机路由分类 != 完整路由分类"""
    def test_full_vs_random_significant_or_not(self):
        """full vs random: 显著或诚实接受不显著"""
    def test_full_vs_static(self):
        """full vs static 比较 + HAC p 值"""
    def test_l2_bh_fdr_4_comparisons(self):
        """4 比较经 BH-FDR 校正"""
    def test_l2_report_has_routing_table(self):
        """报告含路由消融表"""
```

### 4.6 E4 验收标准

- [ ] 5 个 AblationResult (4 消融 + 1 参照)
- [ ] 随机路由 seed 固定, 可重现
- [ ] full vs random 的 ΔIC + ΔSharpe + HAC p + bootstrap p 完整
- [ ] BH-FDR 校正 4 个多重比较
- [ ] 诚实立场: 若 full vs random 不显著, 报告明确标注"路由无效"

---

## 5. E5: L4 前置处理 OAT 消融

### 5.1 目标

6 自由度单维消融 (OAT, one-at-a-time), 实证 §3 前置处理诚实性论点。E1 修正 (CRITICAL): 不做全因子 972 组合。

### 5.2 6 自由度 + 选项

| 自由度 | 选项 | 默认 | 预期影响 |
|--------|------|------|---------|
| 去极值方法 | 3σ / MAD / winsorize 1% / winsorize 5% | MAD | t-stat 翻倍 |
| 标准化方式 | z-score / rank / min-max | z-score | IC 分布改变 |
| 缺失值处理 | drop / fill median / KNN | fill median (auto) | 横截面样本改变 |
| 行业中性化 | 不中性 / 中性 / 中性+市值 | 中性 | β 估计变化 |
| 时间对齐 | t+1 / t+5 / week-ahead | t+1 | IC 方向改变 |
| 数据起止点 | 2010-2020 / 2015-2025 / 2010-2025 | 2010-2025 | 结论改变 |

**OAT 原则**: 每个自由度单独消融, 其余固定为默认。每个自由度的选项数: 4 + 3 + 3 + 3 + 3 + 3 = 19 个消融 + 1 baseline = 20 个 AblationResult。

> **M6 修正 — L4_baseline 引用复用**: L4_baseline (默认配置) 与 §7.3 B3_full 在运行层面等价 (全启用 + 默认选项), 通过引用复用 B3_full 结果, 不在 `run_l4_oat` 中重复运行 (见 §7.2 M6 修正)。下文代码中的 `L4_baseline` 占位符在实现时由 `run_baselines` 的 B3_full 结果注入。

> **M5 修正 — 平凡比较标注**: 上表中每个自由度的"默认"选项 (如 去极值方法=MAD, 标准化=z-score, 缺失值=median, 中性化=industry, 时间对齐=t+1, 数据起止=2010-2025) 与 L4_baseline 配置完全相同, 构成**平凡比较** (trivial comparison, ΔIC=0, ΔSharpe=0, p=1.0).
> 这些平凡比较在代码中通过 `_is_trivial` 标记跳过 BH-FDR 校正 (不占用多重比较额度), 但仍保留在结果列表中用于完整性报告.
> 实际非平凡比较数: (4-1) + (3-1) + (3-1) + (3-1) + (3-1) + (3-1) = 3+2+2+2+2+2 = **13 个非平凡比较** (BH-FDR 校正 13 个, 非 19 个).

### 5.3 代码改动

**文件**: `backtest/ablation_runner.py` — `AblationRunner.run_l4_oat` 方法

```python
def run_l4_oat(self, factor_data, fwd_returns, industry_data=None,
               b3_full_result: Optional[AblationResult] = None):
    results = []

    # Baseline: 默认配置 (M6 修正: 引用复用 B3_full, 不重复 run_single)
    # b3_full_result 由 run_baselines 预先计算并注入; 若未提供, 则回退到 run_single
    if b3_full_result is not None:
        results.append(b3_full_result)
    else:
        results.append(self.run_single(
            AblationConfig(name='L4_baseline', layer='L4'),
            factor_data, fwd_returns, industry_data,
        ))

    # M5 修正: 默认选项 = baseline, 标记为 trivial (不参与 BH-FDR)
    # 各自由度的默认值 (与 L4_baseline 相同的选项):
    defaults = {'outlier': 'mad', 'scaler': 'zscore', 'missing': 'median',
                'neutralization': 'industry', 'time_align': 't+1',
                'data_window': '2010-2025'}

    # 自由度 1: 去极值方法
    for method in ['3sigma', 'mad', 'winsorize_1pct', 'winsorize_5pct']:
        is_trivial = (method == defaults['outlier'])  # M5: mad = 默认 → trivial
        results.append(self.run_single(
            AblationConfig(name=f'L4_outlier_{method}', layer='L4',
                           outlier_method=method, _is_trivial=is_trivial),
            factor_data, fwd_returns, industry_data,
        ))

    # 自由度 2: 标准化方式
    for method in ['zscore', 'rank', 'minmax']:
        is_trivial = (method == defaults['scaler'])  # M5: zscore = 默认 → trivial
        results.append(self.run_single(
            AblationConfig(name=f'L4_scaler_{method}', layer='L4',
                           scaler_method=method, _is_trivial=is_trivial),
            factor_data, fwd_returns, industry_data,
        ))

    # 自由度 3-6: 类似结构... (同样标注 _is_trivial)
    # missing_method: 'drop' | 'median' | 'knn'          → median = 默认 (trivial)
    # neutralization: 'none' | 'industry' | 'industry+mktcap' → industry = 默认 (trivial)
    # time_align: 't+1' | 't+5' | 'week_ahead'           → t+1 = 默认 (trivial)
    # data_window: ('2010-01-01', '2020-12-31') / ('2015-01-01', '2025-12-31') / full → full = 默认 (trivial)

    return results  # ~20 个 (含 6 个 trivial; 非平凡 13 个)
```

### 5.4 OAT 参数注入实现

**文件**: `backtest/ablation_runner.py` — `AblationRunner.run_single` 中根据 config 覆盖

```python
def _apply_l4_overrides(self, config: PipelineV2Config,
                        ablation_config: AblationConfig) -> PipelineV2Config:
    """将 L4 OAT 参数注入 PipelineV2Config"""
    config = copy.deepcopy(config)

    # 去极值方法: 修改 ProcessingAdapter outlier method
    if ablation_config.outlier_method is not None:
        # 通过 module_enabled + 自定义 method 覆盖
        # winsorize_1pct → method='winsorize', ratio=0.01
        # 3sigma → method='3sigma'; mad → method='mad'
        config._l4_outlier_method = ablation_config.outlier_method

    # 标准化方式
    if ablation_config.scaler_method is not None:
        config._l4_scaler_method = ablation_config.scaler_method

    # 缺失值处理
    if ablation_config.missing_method is not None:
        if ablation_config.missing_method == 'drop':
            config.module_enabled = config.module_enabled or {}
            config.module_enabled['imputer'] = False  # 关闭 imputer = drop
        elif ablation_config.missing_method == 'median':
            config._l4_imputer_strategy = 'median'
        elif ablation_config.missing_method == 'knn':
            config._l4_imputer_strategy = 'knn'

    # 行业中性化
    if ablation_config.neutralization is not None:
        if ablation_config.neutralization == 'none':
            config.module_enabled = config.module_enabled or {}
            config.module_enabled['neutralizer'] = False
        # 'industry' / 'industry+mktcap' 通过 neutralizer_params 控制

    return config
```

### 5.5 BH-FDR 校正

6 自由度的 19 个消融 vs baseline (含 6 个 trivial 默认选项), 实际 **13 个非平凡比较** → BH-FDR 校正 13 个 p 值 (复用 `apply_bh_fdr`, 排除 `_is_trivial=True` 的比较)。

```python
from backtest.multiple_testing import apply_bh_fdr

def _l4_bh_fdr_correction(comparisons: List[AblationComparison]) -> List[bool]:
    """对 L4 的 13 个非平凡比较做 BH-FDR 校正 (排除 6 个 _is_trivial 平凡比较)"""
    non_trivial = [c for c in comparisons if not getattr(c, '_is_trivial', False)]
    p_values = [c.p_value_hac for c in non_trivial]
    _, is_significant = apply_bh_fdr(p_values, alpha=0.05)
    return is_significant
```

### 5.6 性能评估

| 项目 | OAT | 全因子 |
|------|-----|--------|
| 组合数 | 20 | 972 |
| 单次运行 | ~2s | ~2s |
| 总运行时间 | ~40s | ~32 min |
| 可行性 | ✅ 可行 | ❌ 不可行 (月度 240 obs) |

### 5.7 E5 测试计划

```python
class TestL4OAT:
    def test_outlier_3sigma(self):
        """outlier=3sigma → 极值未被截断"""
    def test_outlier_winsorize_1pct(self):
        """outlier=winsorize_1pct → 1% 截断"""
    def test_scaler_rank(self):
        """scaler=rank → 输出为秩"""
    def test_scaler_minmax(self):
        """scaler=minmax → 输出 ∈ [0, 1]"""
    def test_missing_drop(self):
        """missing=drop → NaN 被移除 (imputer 关闭)"""
    def test_missing_knn(self):
        """missing=knn → KNN 插补"""
    def test_neutralization_none(self):
        """neutralization=none → 中性化关闭"""
    def test_time_align_t5(self):
        """time_align=t+5 → IC 对齐到 t+5"""
    def test_data_window_2010_2020(self):
        """data_window → 仅用 2010-2020 数据"""
    def test_l4_oat_returns_20_results(self):
        """run_l4_oat → 20 个 AblationResult"""
    def test_l4_bh_fdr_13_non_trivial_comparisons(self):
        """13 个非平凡比较经 BH-FDR 校正 (排除 6 个 trivial)"""
    def test_l4_report_has_6_dof_table(self):
        """报告含 6 自由度表格"""
```

### 5.8 E5 验收标准

- [ ] ~20 个 AblationResult (19 消融 + 1 baseline; 其中 6 个消融为 trivial)
- [ ] 6 自由度每个均有 3-4 个选项测试
- [ ] BH-FDR 校正 13 个非平凡多重比较 (排除 6 个 trivial, 非 19 个)
- [ ] 每个自由度的 ΔIC + p 值报告完整
- [ ] 诚实立场: 允许"6 自由度中仅 2-3 个显著"的结论 (§3 论点收窄)

---

## 6. E6: L3 参数消融

### 6.1 目标

4 参数组 + 方法选择消融, 依赖 T3 CUSUM 已完成 (ADR-025)。验证参数选择的稳健性。

### 6.2 4 参数组 + 方法选择

| 参数组 / 方法 | 选项 | 默认 | 依赖 |
|--------|------|------|------|
| CUSUM 参数 | k=0.25 / k=0.5 / k=0.75 / h=4.0 / h=5.5 / h=7.0 | k=0.5, h=5.5 | T3 已完成 |
| EWMA 参数 | halflife=6 / 12 / 24 | 12 | 既有 |
| EWMA 5 分叉阈值 (M4 修正) | alpha=[0.1, 0.3, 0.5, 0.7, 0.9] (5 个平滑系数分叉) | 0.3 | — |
| 5 叉阈值 | 基底 / ±20% / ±50% | 基底 | — |
| winsorize 比例 | 1% / 3% / 5% / MAD 3σ | MAD | — |
| 多重比较校正方法 | benjamini_hochberg / bonferroni / none | benjamini_hochberg | E2 共享模块 |

**组合数**: (3+3) + 3 + 5 + 3 + 4 + 3 = 24 个消融 (CUSUM 拆分 k 和 h; EWMA 5 分叉阈值 alpha 5 值, M4 修正; 多重比较校正方法 3 值) + 1 baseline = 25。实际按 OAT: 6+3+5+3+4+3 = 24 + 1 = 25。

> **M6 修正 — L3_baseline 引用复用**: L3_baseline (默认参数) 与 §7.3 B3_full 在运行层面等价 (默认 CUSUM k=0.5/h=5.5, EWMA halflife=12/alpha=0.3, 5 叉阈值基底, winsorize MAD), 通过引用复用 B3_full 结果, 不在 `run_l3` 中重复运行 (见 §7.2 M6 修正)。下文代码中的 `L3_baseline` 占位符在实现时由 `run_baselines` 的 B3_full 结果注入。

### 6.3 代码改动

**文件**: `backtest/ablation_runner.py` — `AblationRunner.run_l3` 方法

```python
def run_l3(self, factor_data, fwd_returns, industry_data=None,
           b3_full_result: Optional[AblationResult] = None):
    results = []
    # Baseline (M6 修正: 引用复用 B3_full, 不重复 run_single)
    # b3_full_result 由 run_baselines 预先计算并注入; 若未提供, 则回退到 run_single
    if b3_full_result is not None:
        results.append(b3_full_result)
    else:
        results.append(self.run_single(
            AblationConfig(name='L3_baseline', layer='L3'),
            factor_data, fwd_returns, industry_data,
        ))

    # CUSUM k 参数 (h 固定 5.5)
    for k in [0.25, 0.5, 0.75]:
        results.append(self.run_single(
            AblationConfig(name=f'L3_cusum_k{k}', layer='L3', cusum_k=k, cusum_h=5.5),
            factor_data, fwd_returns, industry_data,
        ))

    # CUSUM h 参数 (k 固定 0.5)
    for h in [4.0, 5.5, 7.0]:
        results.append(self.run_single(
            AblationConfig(name=f'L3_cusum_h{h}', layer='L3', cusum_k=0.5, cusum_h=h),
            factor_data, fwd_returns, industry_data,
        ))

    # EWMA halflife 参数 (M4 修正: 原缺失, 补充)
    for halflife in [6, 12, 24]:
        results.append(self.run_single(
            AblationConfig(name=f'L3_ewma_hl{halflife}', layer='L3', ewma_halflife=halflife),
            factor_data, fwd_returns, industry_data,
        ))

    # EWMA 5 分叉阈值 alpha (M4 修正: 原缺失, 补充 5 个平滑系数分叉)
    for alpha in [0.1, 0.3, 0.5, 0.7, 0.9]:
        results.append(self.run_single(
            AblationConfig(name=f'L3_ewma_alpha{alpha}', layer='L3', ewma_alpha=alpha),
            factor_data, fwd_returns, industry_data,
        ))

    # 5 叉阈值 (M4 修正: 原缺失, 补充; 基底/±20%/±50% 扰动)
    for thresh_label, thresh_scale in [('base', 1.0), ('pm20', 1.2), ('pm50', 1.5)]:
        results.append(self.run_single(
            AblationConfig(name=f'L3_5fork_{thresh_label}', layer='L3',
                           routing_threshold_scale=thresh_scale),
            factor_data, fwd_returns, industry_data,
        ))

    # 多重比较校正方法
    for method in ['benjamini_hochberg', 'bonferroni', 'none']:
        results.append(self.run_single(
            AblationConfig(name=f'L3_correction_{method}', layer='L3',
                           correction_method=method),
            factor_data, fwd_returns, industry_data,
        ))

    # winsorize 比例
    for ratio in [0.01, 0.03, 0.05, None]:  # None = MAD 3σ
        name = f'L3_winsor_{ratio}' if ratio else 'L3_winsor_mad'
        results.append(self.run_single(
            AblationConfig(name=name, layer='L3', winsorize_ratio=ratio),
            factor_data, fwd_returns, industry_data,
        ))

    return results  # ~25 个 (M4 修正: 原 ~16, 补充 EWMA halflife 3 + alpha 5 + 5叉阈值 3; MINOR 修正: 补充 correction method 3)
```

### 6.4 参数注入

```python
def _apply_l3_overrides(self, config: PipelineV2Config,
                        ablation_config: AblationConfig) -> PipelineV2Config:
    """L3 参数覆盖"""
    config = copy.deepcopy(config)

    if ablation_config.cusum_k is not None:
        config.cusum_k = ablation_config.cusum_k
        config.enable_cusum_drift_monitor = True
    if ablation_config.cusum_h is not None:
        config.cusum_h = ablation_config.cusum_h
        config.enable_cusum_drift_monitor = True
    if ablation_config.winsorize_ratio is not None:
        config._l3_winsorize_ratio = ablation_config.winsorize_ratio

    # M4 修正: EWMA 参数注入 (原缺失)
    if ablation_config.ewma_halflife is not None:
        config.ewma_halflife = ablation_config.ewma_halflife
    if ablation_config.ewma_alpha is not None:
        # alpha = 2/(halflife+1) → 反推 halflife, 或直接设 alpha (取决于管线实现)
        config._l3_ewma_alpha = ablation_config.ewma_alpha

    # M4 修正: 5 叉阈值缩放注入 (原缺失)
    if ablation_config.routing_threshold_scale is not None:
        config._l3_routing_threshold_scale = ablation_config.routing_threshold_scale

    return config
```

### 6.5 E6 测试计划

```python
class TestL3Ablation:
    def test_cusum_k_variants(self):
        """3 个 k 值 → 3 个不同 CUSUM 行为"""
    def test_cusum_h_variants(self):
        """3 个 h 值 → 3 个不同 ARL"""
    def test_correction_bh_vs_bonferroni(self):
        """BH vs Bonferroni → BH 检测力更高 (更多显著)"""
    def test_winsorize_1pct_vs_5pct(self):
        """1% vs 5% → 5% 截断更多"""
    def test_l3_returns_25_results(self):
        """run_l3 → ~25 个 AblationResult (M4 修正: 含 EWMA + 5叉阈值; MINOR 修正: 含 correction method)"""
    def test_l3_uses_t3_cusum(self):
        """L3 消融复用 T3 CUSUMDriftMonitor"""
    def test_l3_bh_fdr_correction(self):
        """~24 比较经 BH-FDR 校正"""
    def test_l3_report_has_param_table(self):
        """报告含参数消融表"""
    def test_l3_cusum_k025_more_sensitive(self):
        """k=0.25 → 检测更敏感 (更多触发)"""
    def test_l3_cusum_h7_more_conservative(self):
        """h=7.0 → 更保守 (更少触发)"""
    def test_l3_ewma_halflife_variants(self):
        """EWMA halflife 6/12/24 → 3 个不同平滑 (M4 修正)"""
    def test_l3_ewma_alpha_5_fork(self):
        """EWMA alpha 5 分叉 [0.1,0.3,0.5,0.7,0.9] → 5 个不同平滑系数 (M4 修正)"""
    def test_l3_5fork_threshold_scale(self):
        """5 叉阈值缩放 1.0/1.2/1.5 → 3 个不同路由阈值 (M4 修正)"""
```

### 6.6 E6 验收标准

- [ ] ~25 个 AblationResult (24 消融 + 1 baseline; M4 修正: 含 EWMA 3+5 + 5叉阈值 3; MINOR 修正: 含 correction method 3)
- [ ] CUSUM k/h 参数覆盖正常 (依赖 T3 ADR-025 已完成)
- [ ] EWMA halflife (3) + alpha 5 分叉 (5) 参数覆盖正常 (M4 修正)
- [ ] correction method (3: BH/Bonferroni/none) 覆盖正常 (MINOR 修正)
- [ ] 5 叉阈值缩放 (3) 参数覆盖正常 (M4 修正)
- [ ] 多重比较校正 3 方法对比 (BH / Bonferroni / none)
- [ ] winsorize 4 比例对比
- [ ] BH-FDR 校正 ~24 个多重比较
- [ ] 诚实立场: 若 CUSUM 参数不显著 → 标注"参数不敏感"

---

## 7. E7: Baseline 阶梯 + 报告生成

### 7.1 目标

B0-B3 Baseline 阶梯 + 消融报告 Markdown 生成。

### 7.2 B0-B3 定义 (E5 修正)

| Baseline | 配置 | module_enabled | 说明 |
|----------|------|---------------|------|
| **B0** | 原始因子 + dropna | `{'imputer': False, 'winsorizer': False, 'scaler': False, 'neutralizer': False, 'orthogonalizer': False}` | 最小处理, 终极对照 (E5: NaN 用 dropna) |
| **B1** | 仅 imputer | `{'winsorizer': False, 'scaler': False, 'neutralizer': False, 'orthogonalizer': False}` | 隔离后续模块影响 |
| **B2** | imputer + Z-score | `{'winsorizer': False, 'neutralizer': False, 'orthogonalizer': False}` | 业界默认最小管线 |
| **B3** | 完整管线 | `None` (全启用) | 当前实现, 默认配置 |

> **M6 修正 — B3_full 跨层重叠统一**: B3_full (全启用 + 默认参数 + 完整路由) 在各层中被作为参照组重复使用:
> - **§3.2 L1**: `B3_full` (layer='L1_reference') — L1 组件消融参照
> - **§4.2 L2**: `L2_full_routing` (routing_mode='full') — L2 路由消融参照 (默认配置 = 完整路由)
> - **§6.2 L3**: `L3_baseline` (默认参数) — L3 参数消融参照 (默认参数 = B3 配置)
> - **§5.2 L4**: `L4_baseline` (默认配置) — L4 前置处理消融参照 (默认选项 = B3 配置)
> - **§7.3 B0-B3**: `B3_full` (layer='baseline', baseline_level='B3') — Baseline 阶梯顶层
>
> 上述 5 处配置在**运行层面完全等价** (同一份 PipelineV2Config 默认值, 全启用, 完整路由, 默认参数), 重复运行只产生相同结果。
> **统一处理**: B3_full 仅在 `run_baselines` (§7.3) 中运行一次, 其余各层 (`run_l1` / `run_l2` / `run_l3` / `run_l4_oat`) 通过**引用复用** (不重复 run_single), 仅在比较阶段以 `B3_full` 结果作为参照。
> **判定规则**: 若某层的默认配置与 B3_full 存在差异 (如 L2 默认路由非 'full', 或 L3 默认参数与 B3 不一致), 则该层需独立运行自己的 baseline, 不能引用 B3_full。当前设计中 L1/L2/L3/L4 的默认配置均 = B3_full, 因此全部引用复用。

### 7.3 代码改动

**文件**: `backtest/ablation_runner.py`

```python
def run_baselines(self, factor_data, fwd_returns, industry_data=None):
    results = []

    # B0: 原始因子 + dropna (全部关闭, IC 计算时 dropna)
    results.append(self.run_single(
        AblationConfig(name='B0_raw_dropna', layer='baseline', baseline_level='B0',
                       module_enabled={m: False for m in
                          ['imputer', 'winsorizer', 'scaler', 'neutralizer', 'orthogonalizer']}),
        factor_data, fwd_returns, industry_data,
    ))

    # B1: 仅 imputer
    results.append(self.run_single(
        AblationConfig(name='B1_imputer_only', layer='baseline', baseline_level='B1',
                       module_enabled={m: False for m in
                          ['winsorizer', 'scaler', 'neutralizer', 'orthogonalizer']}),
        factor_data, fwd_returns, industry_data,
    ))

    # B2: imputer + Z-score (scaler 启用)
    results.append(self.run_single(
        AblationConfig(name='B2_imputer_zscore', layer='baseline', baseline_level='B2',
                       module_enabled={m: False for m in
                          ['winsorizer', 'neutralizer', 'orthogonalizer']}),
        factor_data, fwd_returns, industry_data,
    ))

    # B3: 完整管线 (参照)
    results.append(self.run_single(
        AblationConfig(name='B3_full', layer='baseline', baseline_level='B3'),
        factor_data, fwd_returns, industry_data,
    ))

    return results
```

### 7.4 报告生成

**文件**: `backtest/ablation_runner.py` — `AblationRunner.generate_report`

```python
def generate_report(self, results: List[AblationResult],
                    comparisons: List[AblationComparison]) -> str:
    """生成 Markdown 消融报告

    报告结构:
    1. 标题 + 元信息 (日期, 数据范围, alpha, n_bootstrap)
    2. Baseline 阶梯表 (B0-B3 + IC/ICIR/Sharpe/turnover/drawdown)
    3. L1 组件消融表 (5 模块 + ΔIC + p_value + is_significant)
    4. L2 路由消融表 (5 配置 + ΔIC + p_value)
    5. L3 参数消融表 (~25 配置)
    6. L4 前置处理 OAT 表 (~20 配置)
    7. ρ_step 排序保持性表 (5 步骤)
    8. 正交化诊断表 (condition_number + VRR)
    9. 诚实立场声明 (负面/正面结果)
    10. 学术依据
    """
    lines = []
    lines.append("# 消融对照实验报告\n")
    lines.append(f"> **生成时间**: {datetime.now().isoformat()}\n")
    lines.append(f"> **alpha**: {self.alpha}, **n_bootstrap**: {self.n_bootstrap}\n")

    # Baseline 阶梯
    lines.append("## 1. Baseline 阶梯\n")
    lines.append("| Baseline | IC | ICIR | Sharpe | Turnover | MaxDD |")
    lines.append("|----------|-----|------|--------|----------|-------|")
    for r in results:
        if r.config.layer == 'baseline':
            m = r.metrics
            lines.append(f"| {r.config.name} | {m.get('ic_mean', float('nan')):.4f} | "
                        f"{m.get('icir', float('nan')):.3f} | "
                        f"{m.get('sharpe_ls', float('nan')):.3f} | "
                        f"{m.get('turnover_mean', float('nan')):.3f} | "
                        f"{m.get('max_drawdown', float('nan')):.3f} |")

    # L1-L4 消融表 + 比较结果
    # ... 类似结构, 每层一个表, 含 ΔIC / ΔSharpe / p_hac / p_boot / is_significant ...

    # ρ_step 表
    lines.append("## 排序保持性 ρ_step\n")
    lines.append("| 步骤 | ρ_step | 预期范围 |")
    lines.append("|------|--------|---------|")
    expected = {'imputer': '0.99-1.00', 'winsorizer': '0.95-1.00',
                'scaler': '0.99-1.00', 'neutralizer': '0.80-0.95',
                'orthogonalizer': '0.50-0.90'}

    # 诚实立场
    lines.append("## 诚实立场声明\n")
    lines.append("- 消融可能暴露负面结果 (路由无效/模块无贡献/参数不敏感)")
    lines.append("- 若消融发现模块无贡献, §6.4.2 评定将诚实降级")
    lines.append("- 若消融发现模块有正贡献, §6.4.2 评定将升级")

    return "\n".join(lines)
```

### 7.5 E7 测试计划

```python
class TestBaselines:
    def test_b0_raw_dropna_no_processing(self):
        """B0 → 全部 module_enabled=False"""
    def test_b1_imputer_only(self):
        """B1 → 仅 imputer 启用"""
    def test_b2_imputer_zscore(self):
        """B2 → imputer + scaler 启用"""
    def test_b3_full_pipeline(self):
        """B3 → 全部启用"""
    def test_baseline_ic_monotone(self):
        """IC: B0 ≤ B1 ≤ B2 ≤ B3 (预期单调, 允许非单调)"""
    def test_report_markdown_valid(self):
        """generate_report → 合法 Markdown"""
```

### 7.6 E7 验收标准

- [ ] 4 个 Baseline AblationResult (B0-B3)
- [ ] B0 = 全部关闭 + dropna (E5 修正)
- [ ] 报告 Markdown 含 6 个章节 (Baseline + L1-L4 + ρ_step + 诚实立场)
- [ ] 报告中每个消融的 ΔIC + p_value + is_significant 完整
- [ ] 诚实立场声明明确

---

## 8. 工程约束检查

### 8.1 enabled=True 默认值 (向后兼容)

| 检查项 | 状态 |
|--------|------|
| 5 个 Adapter `enabled: bool = True` 默认值 | ✅ E1 §1.3 |
| `module_enabled=None` 默认值 → 全启用 | ✅ E1 §1.5 |
| 既有 934+ 测试零回归 | ✅ E1-T5 回归测试 |

### 8.2 AblationRunner 独立性 (不侵入 fit/transform)

| 检查项 | 状态 |
|--------|------|
| `backtest/ablation_runner.py` 独立模块 | ✅ E2 |
| 不修改 PipelineV2Config 既有字段 (仅新增) | ✅ E1 §1.5 |
| 不修改 fit/transform 签名 | ✅ E1 §1.4 (仅 __init__ 新增可选参数) |

### 8.3 复用既有模块

| 复用项 | 来源 | 用途 |
|--------|------|------|
| `apply_bh_fdr` | `backtest/multiple_testing.py:52` | L1/L2/L3/L4 多重比较校正 |
| `compute_rank_ic` / `compute_ic_series` | `backtest/factor_metrics.py:38/109` | IC 计算 |
| `compute_icir` | `backtest/factor_metrics.py:187` | ICIR |
| `compute_turnover` | `backtest/factor_metrics.py:269` | Turnover |
| `compute_long_short_returns` | `backtest/factor_metrics.py:298` | Sharpe |
| `OrthogonalizerAdapter.get_diagnostics` | `adapters.py:972` | condition_number + VRR |

### 8.4 Ledoit-Wolf HAC 实现路径

| 路径 | 实现 | 检验对象 | 角色 |
|------|------|---------|------|
| 手工 Newey-West + delta method | `ledoit_wolf_hac_test` | Sharpe 差 ΔSR | **唯一主路径** (Sharpe 差检验) |
| statsmodels OLS + HAC | `mean_diff_hac_statsmodels` | 均值差 Δμ | 仅作均值差参考检验 (非 ΔSR 等价路径) |

### 8.5 bootstrap 实现

| 项 | 实现 |
|----|------|
| 算法 | Circular block bootstrap (Politis & Romano 1992) |
| 框架 | numpy (默认) / joblib (可选并行) |
| 块大小 | auto: `max(1, int(T ** (1/3)))` |
| 次数 | B=1000 (可配置) |

### 8.6 L4 OAT 约束

| 项 | 值 |
|----|-----|
| 设计 | OAT 单维消融 |
| 全因子组合 | 972 (不可行) |
| OAT 组合 | ~20 (含 6 个 trivial; 非平凡 13) (可行) |
| BH-FDR 校正 | 13 个非平凡比较 (排除 6 个 trivial) |

### 8.7 TDD 惯例

| 阶段 | TDD 步骤 |
|------|---------|
| E1 | Red: 写 E1-T1~T5 测试 → Green: 实现 enabled 开关 |
| E2 | Red: 写 E2-T1~T8 测试 → Green: 实现 AblationRunner |
| E3-E7 | Red: 写各层消融测试 → Green: 实现 run_l1/l2/l3/l4_oat/baselines |

---

## 9. 风险评估

| 风险 | 等级 | 缓解措施 | 归属 |
|------|------|---------|------|
| enabled 开关破坏既有管线行为 | 高 | 默认 True + E1-T5 回归测试 + 934+ 测试零回归 | E1 |
| AblationRunner 与管线集成耦合 | 中 | 独立模块, 不修改 fit/transform, 仅通过 config 覆盖 | E2 |
| Ledoit-Wolf HAC 小样本不稳定 (T=240) | 中 | bootstrap 双重验证 + 报告标注样本量 | E2 |
| L2 随机路由 seed 依赖 | 低 | 固定 seed=42 + 多 seed 稳健性检查 (可选) | E4 |
| L4 OAT 漏检交互效应 | 中 | OAT 设计已知局限, 报告中声明 "OAT 不检测交互" | E5 |
| L3 CUSUM 参数消融依赖 T3 | 低 | T3 已完成 (ADR-025), 直接覆盖 cusum_k/cusum_h | E6 |
| 消融暴露负面结果 (路由无效) | 中 | 诚实立场: §5 明确接受降级可能 | E3/E4 |
| bootstrap 1000 次性能 | 低 | 纯 numpy ~0.5s/1000次 + joblib 可选并行 | E2 |
| ρ_step 中间数据缺失 | 中 | get_intermediate_data 已有 (pipelines_v2.py:767), 验证可用 | E2 |
| 正交化诊断在 ortho 关闭时缺失 | 低 | 返回 NaN + 报告标注 "ortho disabled" | E2 |

---

## 10. 学术依据 (完整引用)

| 方法 | 学术依据 | 引用 |
|------|---------|------|
| Ledoit-Wolf HAC | Ledoit, O. & Wolf, M. (2008). "Robust performance hypothesis testing with the Sharpe ratio." *J. Empirical Finance* 15(5):850-859. | Ledoit & Wolf (2008) |
| Newey-West HAC | Newey, W. K. & West, K. D. (1987). "A Simple, Positive Semi-Definite, Heteroskedasticity and Autocorrelation Consistent Covariance Matrix." *Econometrica* 55(3):703-708. | Newey & West (1987) |
| Andrews HAC (原文采用) | Andrews, D. W. K. (1991). "Heteroskedasticity and Autocorrelation Consistent Covariance Matrix Estimation." *Econometrica* 59(3):817-858. | Andrews (1991) |
| Circular Block Bootstrap | Politis, D. N. & Romano, J. P. (1992). "A Circular Block Resampling Procedure for Stationary Data." *IMS Lecture Notes–Monograph Series* 35:2680-2684. | Politis & Romano (1992) |
| Block Size Selection | Politis, D. N. & White, H. (2004). "Automatic Block-Length Selection for the Dependent Bootstrap." *Econometric Reviews* 23(1):53-70. | Politis & White (2004) |
| BH-FDR | Benjamini, Y. & Hochberg, Y. (1995). "Controlling the False Discovery Rate." *JRSS-B* 57(1):289-300. | Benjamini & Hochberg (1995) |
| CUSUM | Page, E. S. (1954). "Continuous Inspection Scheme." *Biometrika* 41(1/2):100-115. | Page (1954) |
| Spearman Rank | Spearman, C. (1904). "The Proof and Measurement of Association between Two Things." *AJPsychology* 15(1):72-101. | Spearman (1904) |

---

## 11. 与 v3.0.0 已实施代码的衔接

### 11.1 测试基线衔接

| 版本 | passed | skipped | subtests | 增量 |
|------|--------|---------|----------|------|
| v2.6.0 | 918 | 6 | 11 | - |
| v3.0.0 T4 | 934 | 6 | 11 | +16 |
| v3.0.0 T1 | ~962 | 6 | 11 | +~28 |
| v3.0.0 T3 | ~1347 | 7 | 11 | +~385 |
| **v3.0.0 消融 (预期)** | **~1410** | 7 | 11 | **+~84** |

### 11.2 ADR 衔接

| ADR | 状态 | 关系 |
|-----|------|------|
| ADR-024 (T1 指纹 21 维) | 已实施 | L2 路由消融复用 21 维指纹 |
| ADR-025 (T3 CUSUM) | 已实施 | L3 参数消融覆盖 cusum_k/cusum_h |
| ADR-002a (T4 BH-FDR) | 已实施 | 消融多重比较校正复用 |
| **ADR-026 (消融对照机制)** | **待写入 (E7)** | 本文档对应的 ADR |

### 11.3 文档同步清单 (E7 阶段)

| 文档 | 更新内容 |
|------|---------|
| **DECISIONS.md** | 新增 ADR-026 (消融对照机制) |
| **CHANGELOG.md** | 新增 v3.0.0 消融章节 (E1-E7 七阶段表) |
| **CODE_WIKI.md** | 新增 §消融模块: AblationRunner + 4 层架构表 |
| **README.md** | 版本摘要新增 v3.0.0 消融对照机制 |
| **README.en.md** | 同步英文版 |
| **ABLATION_DESIGN_V3.0.0.md** | 状态从"待实施"改为"已实施" |

---

## 12. ADR-026 内容大纲 (E7 写入)

```markdown
## ADR-026: 消融对照机制 (v3.0.0, 四层架构 + Baseline 阶梯)

**日期**: 2026-07-XX
**状态**: 已实施
**supersedes**: 无 (新增)
**关联**: ADR-024 (T1), ADR-025 (T3), ADR-002a (T4)

### 背景
v3.0.0 管线无消融机制, §3 前置处理诚实性论点缺乏实证. 第十四轮审查 (E1-E10) 修正设计文档后, 需工程实现.

### 决策
实现四层消融 + Baseline 阶梯 + Ledoit-Wolf HAC + BH-FDR:
- L1: 5 模块 enabled 开关 (Adapter 层)
- L2: 5 路由配置 (含随机路由控制组)
- L3: 4 参数组 (CUSUM/EWMA/5叉阈值/winsorize)
- L4: 6 自由度 OAT (不做全因子 972)
- B0-B3: Baseline 阶梯
- 显著性: Ledoit-Wolf (2008) HAC + circular block bootstrap (B=1000)
- 多重比较: BH-FDR (复用 T4)

### 关键设计
1. enabled 开关在 Adapter 层 (非模块层), 复用 OrthogonalizerAdapter 模式
2. AblationRunner 独立模块, 不侵入 fit/transform
3. L4 OAT 单维消融 (E1 修正: 全因子 972 不可行)
4. L2 含随机路由控制组 (E2 修正: 排除混淆)
5. 诚实立场: 消融是双向的, 可能降级也可能升级评定

### 影响
- 新增 backtest/ablation_runner.py (~600 行)
- 新增 tests/test_backtest/test_ablation_runner.py (~84 测试)
- adapters.py: 5 Adapter 加 enabled 开关 (~50 行)
- pipelines_v2.py: PipelineV2Config 加 module_enabled + _create_pipeline 透传 (~30 行)
- 全量回归: ~1410 passed, 零回归
```

---

## 13. 待确认项

### 13.1 statsmodels HAC API 确认

**问题**: `OLS.fit(cov_type='HAC', cov_kwds={'maxlags': q})` 的具体行为需在 E2 Green 阶段确认:
- `maxlags` 参数名是否正确?
- t_values / p_values 是否为双侧?

**计划**: E2 Green 阶段用最小化实验确认, 写入 ADR-026 附录。

### 13.2 L4 时间对齐实现

**问题**: `time_align='t+5'` 需要在 IC 计算时偏移前向收益 5 期, 当前 `compute_ic_series` 默认 t+1。

**方案**: AblationRunner 中根据 `time_align` 调整 fwd_returns 的对齐 (shift), 不修改 `factor_metrics.py`。

### 13.3 L4 数据起止点

**问题**: `data_window=('2010-01-01', '2020-12-31')` 需要在 run_single 中截取因子数据的子集。

**方案**: AblationRunner 中根据 `data_window` 切片 factor_data + fwd_returns, 不修改管线。

### 13.4 B0 dropna 实现

**问题**: B0 = 原始因子 + dropna, 但 `compute_rank_ic` 已内置 NaN 处理 (跳过 NaN pair)。B0 是否需要显式 dropna?

**决策**: B0 的 dropna 在 IC 计算层处理 (factor_metrics.py 已跳过 NaN), 管线层全 identity。若横截面 NaN 过多导致样本不足, 报告中标注。

---

## 附录 A: 文件改动清单

| 文件 | 改动类型 | 行数估算 | 归属 |
|------|---------|---------|------|
| `adapters.py` | 修改: 5 Adapter 加 enabled | ~50 | E1 |
| `pipelines_v2.py` | 修改: PipelineV2Config + _create_pipeline + 3 Pipeline 透传 | ~60 | E1 |
| `backtest/ablation_runner.py` | 新建: AblationRunner + 全部算法 | ~600 | E2-E7 |
| `tests/test_adapters/test_module_enabled.py` | 新建: E1 测试 | ~200 | E1 |
| `tests/test_backtest/test_ablation_runner.py` | 新建: E2-E7 测试 | ~800 | E2-E7 |
| `DECISIONS.md` | 新增: ADR-026 | ~50 | E7 |
| `CHANGELOG.md` | 新增: v3.0.0 消融条目 | ~30 | E7 |
| `CODE_WIKI.md` | 更新: 消融模块章节 | ~40 | E7 |
| `README.md` / `README.en.md` | 版本摘要更新 | ~10 | E7 |
| **总计** | | **~1840** | |

---

## 附录 B: 消融组合数与运行时间速查

| 层级 | 组合数 | 单次运行 (s) | bootstrap (s) | 总时间 (s) | 全因子对比 |
|------|--------|-------------|--------------|-----------|-----------|
| L1 | 6 | 2 | 0.5 | 15 | - |
| L2 | 5 | 2 | 0.5 | 13 | - |
| L3 | ~25 | 2 | 0.5 | 63 | - |
| L4 OAT | ~20 | 2 | 0.5 | 50 | 972 不可行 → 20 可行 |
| B0-B3 | 4 | 1-2 | 0.5 | 6 | - |
| **总计** | **~60** | | | **~150s (~2.5min)** | |

---

## 附录 C: AblationRunner 与 PipelineV2Config 协同示意

```
┌─────────────────────────────────────────────────────┐
│ AblationRunner                                       │
│                                                      │
│  base_config = PipelineV2Config()                    │
│                                                      │
│  for ablation_config in [L1, L2, L3, L4, B0-B3]:    │
│      ┌──────────────────────────────────┐            │
│      │ 1. deepcopy(base_config)         │            │
│      │ 2. 覆盖 module_enabled           │            │
│      │ 3. 覆盖 routing_mode             │            │
│      │ 4. 覆盖 cusum_k/cusum_h          │            │
│      │ 5. 覆盖 L4 OAT 参数              │            │
│      └──────────────┬───────────────────┘            │
│                     │                                │
│                     ▼                                │
│      ┌──────────────────────────────────┐            │
│      │ pipeline = FactorProcessing      │            │
│      │   PipelineV2(config)             │            │
│      │ pipeline.fit(factor_data)        │            │
│      │ results = pipeline.transform()   │            │
│      └──────────────┬───────────────────┘            │
│                     │                                │
│                     ▼                                │
│      ┌──────────────────────────────────┐            │
│      │ 计算 metrics:                    │            │
│      │   IC/ICIR/Sharpe (factor_metrics)│            │
│      │   ρ_step (新)                    │            │
│      │   condition_number/VRR (Adapter) │            │
│      └──────────────┬───────────────────┘            │
│                     │                                │
│                     ▼                                │
│      ┌──────────────────────────────────┐            │
│      │ AblationResult                   │            │
│      └──────────────────────────────────┘            │
│                                                      │
│  compare(experiment, reference):                     │
│    Ledoit-Wolf HAC (手工实现, 唯一主路径)          │
│    Circular Block Bootstrap (numpy, B=1000)          │
│    → AblationComparison                              │
│                                                      │
│  compare_all(results, reference):                    │
│    BH-FDR (backtest/multiple_testing.py)             │
│    → List[AblationComparison]                        │
│                                                      │
│  generate_report(results, comparisons):              │
│    → Markdown 报告                                   │
│                                                      │
│  get_diagnostics():                                  │
│    → Dict (n_experiments, runtime, summary)          │
└─────────────────────────────────────────────────────┘
```

---

## 修订日志

| 版本 | 日期 | 修订内容 |
|------|------|---------|
| v1.0 | 2026-07-08 | 初稿, 基于 ABLATION_DESIGN_V3.0.0.md (第十四轮审查修正 E1-E10) + 现有代码调研 (adapters.py / pipelines_v2.py / multiple_testing.py / factor_metrics.py / factor_significance.py) |
