# Factor Pipeline 架构总览

> **版本**: v1.0 (2026-07-27)
> **范围**: 项目整体架构、模块边界、依赖关系、数据流、接口契约
> **更新规则**: 任何架构变更 (新增模块 / 接口重构 / 依赖调整) 必须同步更新本文档 + 对应 ADR
> **关联文档**: [DECISIONS.md](../DECISIONS.md) | [CHANGELOG.md](../CHANGELOG.md) | [DEV_PROGRESS.md](DEV_PROGRESS.md) | [WORKFLOW_METHODOLOGY.md](WORKFLOW_METHODOLOGY.md)

---

## §1 项目定位

**factor_pipeline** 是面向量化研究的因子处理统一流水线,实现从原始因子数据到回测就绪因子值的端到端处理。

**核心价值**:
- **顺序校验**: 基于 DAG 的拓扑验证,确保处理步骤顺序符合统计理论 (插补→去极值→变换→标准化→中性化)
- **自适应分类**: 通过 21 维因子指纹 + 统计检验 (VR + DF τ) 将因子分为 Static / Dynamic / Mixed 三类,自动路由到对应管线
- **因果性保证**: 插补与去极值禁止使用未来数据 (插补 lookahead_safe=True 默认; 去极值逐日横截面, fit 不存参数),通过截断不变性测试验证
- **学术可验证**: 每个统计决策都有显著性检验支撑,关键算法有学术文献引用 (经独立验证,排除幻觉)

**版本基线**: v3.3.0 (2026-07-15) → v3.3.1 (2026-07-27, 插补模块 P2 完成) → v3.3.2 (2026-10-21, 管线级因果性测试 + PL-03 修复 + 版本号统一) → v3.3.3 (2026-10-22, PL-01 去极值逐日横截面 + ADR-037) → v3.3.4 (2026-10-22, PL-02 变换逐日截面 rank→正态 + ADR-038) → v3.3.5 (2026-11-04, PL-06 Mixed 缩尾逐日截面 3σ + ADR-039)

---

## §2 顶层架构分层

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 5: Backtest Engine (backtest/)                           │
│  - 回测引擎 + 漂移监测 + 缓存层 + 归因分析                       │
├─────────────────────────────────────────────────────────────────┤
│  Layer 4: Pipeline Orchestration (pipelines_v2.py)              │
│  - StaticFactorPipeline / DynamicFactorPipeline / MixedPipeline │
│  - 软路由 (ADR-001) + 阈值校准 + KS 迁移检测                     │
├─────────────────────────────────────────────────────────────────┤
│  Layer 3: Health Diagnosis (modules/factor_health/)             │
│  - PremiumEstimator (Fama-MacBeth + Epanechnikov)              │
│  - BreakpointDetector (Chow F-test)                             │
│  - FactorHealthDiagnoser (ES/TD/stable/suspect)                 │
├─────────────────────────────────────────────────────────────────┤
│  Layer 2: Factor Classification (modules/factor_fingerprint/)   │
│  - FactorFingerprinter (21 维指纹)                              │
│  - StatisticalClassifier (VR + DF τ, 零 for 循环)              │
│  - SemanticStatisticalFusion (语义 + 统计融合)                  │
├─────────────────────────────────────────────────────────────────┤
│  Layer 1: Processing Steps (adapters.py + modules/)             │
│  - ImputerAdapter (ffill_ts 因果路径, 默认 lookahead_safe=True) │
│  - ProcessingAdapter (SmartOutlier / AdaptiveTransformer / Std) │
│  - NeutralizerAdapter (行业 + 风格中性化)                       │
│  - GarchWhiteningAdapter (可选, GARCH 白化)                     │
│  - OrthogonalizerAdapter (对称正交化为主方法, ADR-020)          │
├─────────────────────────────────────────────────────────────────┤
│  Layer 0: Infrastructure                                         │
│  - PipelineDAG (networkx) + Config (pydantic) + Cache (DuckDB)  │
└─────────────────────────────────────────────────────────────────┘
```

---

## §3 模块清单与职责

### §3.1 核心编排层 (项目根目录)

| 文件 | 职责 | 关键类/函数 | ADR |
|------|------|------------|-----|
| [pipeline.py](../pipeline.py) | 顺序校验 + 步骤执行 + 状态追踪 | `PipelineOrderValidator` (委托给 `PipelineDAG`) | — |
| [pipelines_v2.py](../pipelines_v2.py) | v2.0 自适应管线 (软路由 + 阈值校准) | `StaticFactorPipeline`, `DynamicFactorPipeline`, `MixedFactorPipeline`, `FactorProcessingPipelineV2`, `_get_pipeline_weights`, `_ks_migration_significance` | ADR-001 (软路由), ADR-002a (BH-FDR) |
| [adapters.py](../adapters.py) | 5 个 Adapter 封装外部模块为 `PipelineStep` | `ImputerAdapter`, `ProcessingAdapter`, `NeutralizerAdapter`, `GarchWhiteningAdapter`, `OrthogonalizerAdapter` | ADR-015, ADR-018 |
| [dag.py](../dag.py) | DAG 拓扑验证 (networkx.DiGraph) | `PipelineDAG` | — |
| [config.py](../config.py) / [config_v2.py](../config_v2.py) | 配置管理 (dataclass / pydantic) | `StepType` (5 步骤枚举), `PipelineConfig`, `PipelineV2Config` | ADR-010 |
| [cache.py](../cache.py) | 管线级缓存 | `PipelineCache` | — |
| [exceptions.py](../exceptions.py) | 异常层次 | `OrderValidationError`, `StepExecutionError`, `FactorTypeError`, `AdapterImportError` | — |
| [optimizer.py](../optimizer.py) | 超参搜索 (Optuna, 可选) | — | ADR-004, ADR-005, ADR-006 |

### §3.2 处理模块 (modules/)

| 模块路径 | 职责 | 关键类 | ADR / 版本 |
|---------|------|-------|------------|
| `factor_fingerprint/` | 21 维指纹 + 统计分类 + 语义融合 | `FactorFingerprinter`, `AdaptiveFactorClassifier`, `StatisticalClassifier`, `SemanticStatisticalFusion` | ADR-024 (v3.0.0 T1) |
| `factor_imputer/` | 缺失插补 (因果路径 ffill_ts) | `ImputerAdapter`, `HierarchicalImputer`, `CrossSectionalImputer`, `TimeSeriesImputer`, `MLAdvancedImputer`, `FactorSpecificImputer` | IMPUTER_LOOKAHEAD_FIX_PLAN v2.3 |
| `factor_adaptive_winsor/` | 自适应去极值 + 变换 + 标准化 | `SmartOutlierDetector`, `AdaptiveTransformer`, `AdaptiveStandardizer` | ADR-019 (v2.4.0 内化) |
| `factor_neutralizer/` | 行业 + 风格中性化 | `FactorNeutralizer` | ADR-018 (fit/transform 语义重构) |
| `factor_orthogonalizer/` | 多因子正交化 (对称为主) | `BaseOrthogonalizer`, `SymmetricOrthogonalizer`, `GramSchmidt`, `Cholesky`, `PCA`, `Ridge` | ADR-020 (v2.5.0) |
| `factor_decoupler/` | 时序解耦 (AR / 差分 / HP) | `TemporalDecoupler`, `decouple_ar`, `decouple_difference`, `decouple_hp`, `decouple_auto` | — |
| `factor_health/` | Layer 3 溢价健康诊断 | `PremiumEstimator`, `BreakpointDetector`, `FactorHealthDiagnoser` | ADR-028 (v3.3.0) |
| `statistical_classifier/` | VR + DF τ 面板分类 (零 for 循环) | `StatisticalClassifier` | ADR-027 (v3.2.0) |
| `endogeneity_check/` | 内生性诊断 (AET / IFE / Lewbel / Oster) | `EndogeneityDiagnosticOrchestrator`, `AetChecker`, `IfeChecker`, `LewbelIV`, `OsterDelta`, `ThreatAssessor`, `MissingnessChecker` | ADR-032 (v3.1.0, 2026-10 补记) |
| `endogeneity_estimators/` | 内生性估计器 (IVX / Profile GMM / Regularized DOLS / PFGMM) | `IVXEstimator`, `ProfileGMMEstimator`, `RegularizedDOLSEstimator`, `PFGMMEstimator`, `EstimationMethodSelector` | ADR-035 (v3.1.0, 2026-10 补记) |
| `endogeneity_regularizer/` | 内生性正则化 | `EndogeneityRegularizer` | ADR-034 (v3.1.0, 2026-10 补记) |

### §3.3 回测层 (backtest/)

| 文件 | 职责 | ADR |
|------|------|-----|
| `engine.py` | 回测引擎核心 | ADR-007 |
| `cache_manager.py` + `cached_data_loader.py` | L2 磁盘缓存 | ADR-008 |
| `parallel_runner.py` | 分组并行 | ADR-009 |
| `factor_cache.py` + `price_cache.py` + `fwd_returns_cache.py` | 因子/价格/前向收益缓存 | — |
| `cusum_drift_monitor.py` | CUSUM 在线漂移检测 | ADR-025 |
| `threshold_drift_monitor.py` | 阈值漂移监测 | ADR-023 |
| `unified_drift.py` | 双轨漂移融合 (CUSUM + Threshold) | — |
| `attribution_analyzer.py` + `granger_attribution/` | 归因分析 (Toda-Yamamoto) | — |
| `specification_logger/` | 规范曲线 + 预注册 | — |
| `ablation_runner.py` | 消融实验 | — |
| `statistical_decision_bridge.py` | 统计决策桥 | — |
| `markov_regime_identifier.py` | 马尔可夫状态识别 | — |
| `three_channel_decomposition.py` | 三通道分解 | — |
| `multiple_testing.py` | 多重检验校正 | — |

---

## §4 数据流

### §4.1 主流水线数据流

```
原始因子数据 (T×N DataFrame, 含 NaN)
        │
        ▼
┌───────────────────┐
│ 1. IMPUTATION      │  ImputerAdapter (strategy='ffill_ts', lookahead_safe=True)
│                    │  → ffill(axis=0) → 截面 median → 0
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 2. OUTLIER         │  ProcessingAdapter (process_type='outlier')
│    DETECTION       │  → 逐日横截面缩尾 (percentile 1/99; 其他方法逐行复用 SmartOutlierDetector)
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 3. TRANSFORMATION  │  ProcessingAdapter (process_type='transformation')
│    (可选)          │  → AdaptiveTransformer (Box-Cox / Log / Yeo-Johnson)
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 4. STANDARDIZATION │  ProcessingAdapter (process_type='standardization')
│                    │  → AdaptiveStandardizer (Z-score / Robust / MinMax)
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 5. NEUTRALIZATION  │  NeutralizerAdapter
│                    │  → FactorNeutralizer (行业 + 风格, fit 预计算 dummies)
└───────────────────┘
        │
        ▼
回测就绪因子值 (T×N DataFrame, 无 NaN, 已中性化)
```

**顺序约束** (由 `PipelineDAG` 拓扑验证):
- IMPUTATION 必须是第一步 (缺失数据导致后续统计量有偏)
- OUTLIER_DETECTION 必须在 TRANSFORMATION/STANDARDIZATION 之前 (极值扭曲变换参数)
- NEUTRALIZATION 必须是最后一步 (中性化后残差不应再分布变换)

### §4.2 自适应路由数据流 (v2.0+)

```
原始因子数据
        │
        ▼
┌───────────────────┐
│ FactorFingerprinter │  → 21 维指纹 (VR, AR(1), 尾依赖, 状态切换, ...)
└───────────────────┘
        │
        ▼
┌───────────────────────┐
│ StatisticalClassifier │  → VR + DF τ → Static / Dynamic / Mixed
└───────────────────────┘
        │
        ▼
┌─────────────────────┐
│ _get_pipeline_weights│  → 概率权重 (软路由, ADR-001)
└─────────────────────┘
        │
        ▼
   ┌─────┬─────┬─────┐
   ▼     ▼     ▼     ▼
 Static Dynamic Mixed (并行 3 管线, 加权混合)
   │     │     │
   └─────┴─────┘
        │
        ▼
  _apply_weighted_transform (加权混合输出)
```

### §4.3 健康诊断数据流 (v3.3.0+)

```
因子值 (T×N) + 前向收益 (T×N)
        │
        ▼
┌───────────────────┐
│ PremiumEstimator   │  → Fama-MacBeth β_t + Epanechnikov kernel → λ̂(t)
└───────────────────┘
        │
        ▼
┌────────────────────┐
│ BreakpointDetector  │  → Chow F-test grid search → 断点位置
└────────────────────┘
        │
        ▼
┌──────────────────────┐
│ FactorHealthDiagnoser│  → ES (有效) / TD (时变) / ES+TD / stable / suspect
└──────────────────────┘
        │
        ▼
  与 Layer 2 分类组合 → return_type × premium_health → 治理标签
```

---

## §5 依赖关系

### §5.1 必装依赖 (pyproject.toml `dependencies`)

| 依赖 | 版本 | 用途 |
|------|------|------|
| numpy | >=1.22.0 | 数值计算 |
| pandas | >=2.0.0 | DataFrame |
| scipy | >=1.7.0 | 统计检验 |
| networkx | >=2.8.0 | DAG 拓扑 |
| pydantic | >=2.0.0 | 配置验证 (config_v2) |
| duckdb | >=0.10.0 | 缓存数据库 |
| statsmodels | >=0.13.0 | 回归 / 检验 (REQUIRED, ADR-015) |
| scikit-learn | >=1.0.0 | ML 插补 (KNN / RF) |
| factor-db | — | 数据边界 (不内化) |

### §5.2 可选依赖 (`project.optional-dependencies`)

| Extra | 依赖 | 用途 |
|-------|------|------|
| `semantic` | jieba>=0.42.0 | 语义理解 (中文分词) |
| `backtest` | factor-trading-v3 | DataLoaderV3 (需外部安装 Factor_Trading_v3.0) |
| `garch` | arch>=5.0.0 | GARCH 白化 |
| `optimizer` | optuna>=3.0.0 | 超参搜索 |
| `dev` | pytest, pytest-cov | 测试 |

### §5.3 模块内依赖图 (关键路径)

```
pipelines_v2.py
  ├── adapters.py (ImputerAdapter / ProcessingAdapter / NeutralizerAdapter / OrthogonalizerAdapter)
  │     ├── modules/factor_imputer/ (ImputerAdapter 委托)
  │     ├── modules/factor_adaptive_winsor/ (ProcessingAdapter 委托)
  │     ├── modules/factor_neutralizer/ (NeutralizerAdapter 委托)
  │     └── modules/factor_orthogonalizer/ (OrthogonalizerAdapter 委托)
  ├── modules/factor_fingerprint/ (分类 + 指纹)
  │     ├── StatisticalClassifier (VR + DF τ)
  │     └── SemanticStatisticalFusion
  ├── modules/factor_health/ (Layer 3 诊断, v3.3.0)
  └── dag.py + config.py + cache.py
```

### §5.4 Python 版本兼容

- **requires-python**: >=3.9
- **测试矩阵** (ADR-017): 3.9 / 3.10 / 3.11 / 3.12
- **当前开发**: Python 3.10.11 (实测)

---

## §6 接口契约

### §6.1 PipelineStep 抽象基类

所有 Adapter 必须实现 `PipelineStep` 接口 (adapters.py):

```python
class PipelineStep(ABC):
    @abstractmethod
    def fit(self, X: pd.DataFrame, y: Optional[pd.DataFrame] = None) -> "PipelineStep":
        """拟合 (训练统计量 / 模型)"""

    @abstractmethod
    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """变换 (应用拟合结果)"""

    def fit_transform(self, X: pd.DataFrame, y: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """拟合 + 变换 (默认实现: fit 后 transform)"""
        return self.fit(X, y).transform(X)
```

**契约约束**:
- `fit` 必须返回 `self` (链式调用)
- `transform` 必须不修改输入 X (内部 copy)
- `transform` 必须不引入 NaN (除非显式说明)
- `fit` 在 `lookahead_safe=True` 时只能使用 [0, t] 数据 (因果性)

### §6.2 StepType 枚举 (5 步骤)

```python
class StepType(Enum):
    IMPUTATION = "imputation"
    OUTLIER_DETECTION = "outlier"
    TRANSFORMATION = "transformation"
    STANDARDIZATION = "standardization"
    NEUTRALIZATION = "neutralization"
```

合法顺序由 `PipelineDAG._STANDARD_VALID_ORDERS` 定义 (4 种),`PipelineOrderValidator.validate()` 校验。

### §6.3 ImputerAdapter 因果性契约 (v2.3, IMPUTER_LOOKAHEAD_FIX_PLAN)

```python
class ImputerAdapter(PipelineStep):
    def __init__(self, strategy: str = 'ffill_ts', lookahead_safe: bool = True, **params):
        """
        strategy: 'ffill_ts' (生产路径, 因果) | 'cross_sectional' | 'time_series' | ...
        lookahead_safe: True (默认, 强制因果) | False (DEPRECATED, legacy 全样本)
        """
```

**生产路径**: `strategy='ffill_ts'` + `lookahead_safe=True`
- Step 1: `X.ffill(axis=0)` (per-stock forward fill, 因果)
- Step 2: 剩余 NaN → 当期截面 median (axis=1, 跨资产, 不含未来)
- Step 3: 整行 NaN → 0

**因果性验证**: 52 项测试覆盖 (33 unit + 9 e2e + 10 ablation), 包括截断不变性 + 未来数据无关性 + 静态扫描无 bfill。

---

## §7 关键设计决策 (ADR 索引)

完整 ADR 见 [DECISIONS.md](../DECISIONS.md)。按主题分组:

### §7.1 架构与路由
- [ADR-001: 软路由替代硬路由](../DECISIONS.md#adr-001-软路由替代硬路由) (v2.1.0)
- [ADR-019: 外部模块内化](../DECISIONS.md#adr-019-外部模块内化) (v2.4.0)
- [ADR-027: 学术准则驱动管线重构](../DECISIONS.md#adr-027-学术准则驱动管线重构) (v3.2.0)

### §7.2 统计方法
- [ADR-002: Bonferroni KS 双样本检验](../DECISIONS.md#adr-002-bonferroni-校正的-ks-双样本检验替代简单迁移检测)
- [ADR-002a: BH-FDR 替代 Bonferroni](../DECISIONS.md#adr-002a-benjamini-hochberg-fdr-替代-bonferroni) (v3.0.0 T4)
- [ADR-024: 指纹维度扩展至 21 维](../DECISIONS.md#adr-024-指纹维度扩展至-21-维-v300-t1) (v3.0.0 T1)
- [ADR-025: CUSUM 在线漂移检测](../DECISIONS.md#adr-025-cusum-在线漂移检测-v300-t3-2026-07-07) (v3.0.0 T3)
- [ADR-028: Layer 3 溢价健康诊断](../DECISIONS.md#adr-028-layer-3-溢价健康诊断) (v3.3.0)
- [ADR-029: 标准化统一为逐日横截面 Z-Score (因果性修复)](../DECISIONS.md#adr-029-标准化统一为逐日横截面-z-score-因果性修复) (2026-10)
- ADR-030~036: v3.1.0 E1-E6 内生性诊断链 + 消融对照机制 (v3.1.0/v3.0.0 决策, 2026-10 补记) — 见 [DECISIONS.md](../DECISIONS.md)「ADR-030 ~ ADR-036 补记说明」

### §7.3 工程实践
- [ADR-003: importlib + 上下文管理器](../DECISIONS.md#adr-003-importlib-上下文管理器替代-syspath-操作)
- [ADR-013: 外部模块子包化](../DECISIONS.md#adr-013-外部模块子包化--直接导入替代-importlibsyspath-黑魔法)
- [ADR-014: 依赖锁定](../DECISIONS.md#adr-014-依赖锁定--pyprojecttoml--requiredoptional-分离--删除优雅回退)
- [ADR-015: adapters 重构](../DECISIONS.md#adr-015-adapters-重构--neutralizeradapter-required-化--garchwhiteningadapter-模块级导入)
- [ADR-017: 跨版本 CI 矩阵](../DECISIONS.md#adr-017-跨版本-ci-矩阵--github-actions--tox-双轨)
- [ADR-020: 多因子正交化](../DECISIONS.md#adr-020-多因子横截面正交化模块--对称正交化为主方法) (v2.5.0)

---

## §8 测试架构

### §8.1 测试目录结构

```
tests/
├── unit/                    # 单元测试 (33 项 imputer + 其他)
├── integration/             # 集成测试 (9 项 e2e + 10 项 ablation)
├── manual/                  # 手动验证脚本
├── test_backtest/           # 回测层测试
├── test_endogeneity_*/      # 内生性测试
├── test_factor_decoupler/   # 解耦器测试
├── test_factor_fingerprint/ # 指纹测试
├── test_factor_orthogonalizer/ # 正交化测试
└── conftest.py              # 共享 fixtures
```

### §8.2 测试统计 (2026-07-27 实测)

| 测试集 | 数量 | 状态 |
|--------|------|------|
| `test_imputer_lookahead_fix.py` | 33 | ✅ 全部通过 |
| `test_imputer_e2e_causal.py` | 9 | ✅ 全部通过 |
| `test_imputer_ablation_lookahead.py` | 10 | ✅ 全部通过 |
| `test_step3_imputer_ffill_ts.py` | 4 | ✅ 全部通过 |
| **全量回归** | **803 passed, 10 skipped** | ✅ 0 regressions |

### §8.3 测试运行

```powershell
# 从父目录运行 (避免 types.py 遮蔽标准库)
cd f:\Coding
python -m pytest factor_pipeline/tests/ -q --tb=short

# 仅插补相关
python -m pytest factor_pipeline/tests/unit/test_imputer_lookahead_fix.py `
                   factor_pipeline/tests/integration/test_imputer_e2e_causal.py `
                   factor_pipeline/tests/integration/test_imputer_ablation_lookahead.py -v
```

---

## §9 已知限制与未来方向

### §9.1 当前限制

| 限制 | 影响 | 缓解 |
|------|------|------|
| `types.py` 在项目根遮蔽标准库 | 必须从父目录运行 pytest | 长期: 重命名 types.py |
| KNN walk_forward 不能向量化 | 每个 (asset, t) 用不同训练集, 性能较慢 | 因果算法本质, 保留 for 循环 |
| MissingTypeDiagnoser 使用全样本 EM | strategy='auto' 时有间接前视 | P3 待办 (expanding EM) |
| PanelHierarchicalImputer 间接前视 | 通过子组件继承 | 已通过子组件修复传导 (§4.5) |

### §9.2 未来方向 (v3.4.0+)

- 内生性-溢价诊断交互 (τ 修正因子)
- 多断点支持 (Bai-Perron LWZ)
- 面板 HAC 稳健估计 (Newey-West)
- 流式处理支持 (v3.0.0 T2)
- Anderson-Rubin 后验检验 (中性化质量监控)

---

## §10 文档导航

| 文档 | 用途 |
|------|------|
| [ARCHITECTURE.md](ARCHITECTURE.md) (本文档) | 架构总览 |
| [DEV_PROGRESS.md](DEV_PROGRESS.md) | 版本×模块双维度进度矩阵 |
| [WORKFLOW_METHODOLOGY.md](WORKFLOW_METHODOLOGY.md) | 10 步 spec 规范工作流 |
| [PROJECT_STATUS.md](PROJECT_STATUS.md) | 待办追踪 (单一真相源) |
| [../DECISIONS.md](../DECISIONS.md) | ADR 决策记录 (28 项) |
| [../CHANGELOG.md](../CHANGELOG.md) | 开发日志 |
| [analysis/IMPUTER_LOOKAHEAD_FIX_PLAN.md](analysis/IMPUTER_LOOKAHEAD_FIX_PLAN.md) | 插补模块前视偏差修复方案 v2.3 |
| [EXECUTION_V3.3.1_IMPUTER_P2.md](EXECUTION_V3.3.1_IMPUTER_P2.md) | v3.3.1 插补 P2 实施记录 |
