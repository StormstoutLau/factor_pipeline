# 因子路由过度工程化治理 — 设计文档

**版本**: v1.2 (2026-11-10; v1.0 = 步骤 3 设计初稿; v1.1 = 步骤 4 幻觉消除 review 修订; v1.2 = 步骤 8 一致性 review 勘误, 见 §12)
**上游调研**: [FACTOR_ROUTING_OVERENGINEERING_RESEARCH.md](FACTOR_ROUTING_OVERENGINEERING_RESEARCH.md) v1.1
**关联决策**: **ADR 编号待分配** (DECISIONS.md 登记规则 2: 规划文档不得预留编号; 当前空闲号 ADR-042, 全文暂以其指代, 实施落库时回 DECISIONS.md 取号)
**目标版本**: **v3.4.0**; 缓存 **`v2.3.0-cache`**
**方案状态**: **U1 统一横截面秩管道 + §11.2 全部建议(P0/P1/P2)采纳**
**后续工件**: 步骤 4 设计 review → 步骤 5 `EXECUTION_V3.4.0_UNIFIED_ROUTING.md`
**行号说明**: 行号仅作导航, 以类名/函数名/测试名为准

---

## §0 设计摘要

### 0.1 决策清单

| # | 决策 | 对应 §11.2 | 状态 |
|---|------|-----------|------|
| D1 | 新增 `PipelineV2Config.pipeline_mode`, 默认 `'unified'`; 另一合法值 `'dynamic_ab'`(显式 A/B 臂) | P2-2 | **锁定** |
| D2 | `'unified'` 一律走 `StaticFactorPipeline`(即现 Static 链), 不再按因子分类选管道 | P0-2 | **锁定** |
| D3 | 统一缩尾规则 = 逐日横截面 1%/99% 分位硬截断(现 Static 规则); 删除 `mixed_winsor_sigma` | P0-2 | **锁定** |
| D4 | 删除 `_get_pipeline_weights` / `_get_multi_dim_pipeline_weights` / `_apply_weighted_transform` 及 `enable_multi_dim_routing` / `hard_routing_prob` / `merge_alpha` / `ks_alpha` | P0-1 | **锁定** |
| D5 | 指纹降级为**诊断**: `fit` 不再调用 `StatisticalClassifier`; 诊断标签只写入 `FactorRoutingRecord` | P1-1 | **锁定** |
| D6 | 新增 `FactorRoutingRecord` + `FingerprintMeta`(含 `sampling_frequency`); **不修改 21 维 `FactorFingerprint` 契约** | P1-1/P1-2 | **锁定** |
| D7 | `enable_specification_logger=True` 时, `fit` 每因子写一条规格记录(管道/模式/频率/诊断) | P1-2 | **锁定** |
| D8 | 新增 `backtest/structural_break_monitor.py` + `monitor_structural_breaks()`; 默认关闭, 只告警不切换 | P2-1 | **锁定** |
| D9 | `MixedFactorPipeline` / `DynamicFactorPipeline` 保留为**显式组件**(不再被自动选择); 不删除类 | P0-2 | **锁定** |
| D10 | `EndToEndThresholdOptimizer` 默认搜索空间清空(路由阈值已不存在), 仅 `search_orth=True` 时可用 | P0-1 派生 | **锁定** |
| D11 | 版本 **v3.4.0** / 缓存 **`v2.3.0-cache`** / **ADR 编号待分配** (暂用号 ADR-042) | — | **锁定** |
| D12 | 不新增第三方依赖; 断点监控仅用 numpy/pandas 自实现 | — | **锁定** |

### 0.2 验收目标

| 指标 | 当前基线 (v3.3.7) | 目标 |
|------|------------------|------|
| 默认 `pipeline_mode` | 不存在(按 VR/DF 分类路由) | **`'unified'`** |
| 统一管道输出 vs `StaticFactorPipeline` 直调 | — | **`assert_frame_equal(check_exact=True)`** (12 因子) |
| `'dynamic_ab'` 输出 vs `DynamicFactorPipeline` 直调 | — | **完全一致** (12 因子) |
| `MixedFactorPipeline` 被自动创建次数 | 可为 1(当 VR/DF 判 mixed) | **0** |
| 指纹诊断字段 | 无 `sampling_frequency` | **每个因子均有** |
| 规格日志行数 (enabled) | 0(未接线) | **= 因子数** |
| 规格日志行数 (disabled) | 0 | **0, 且不创建文件** |
| 断点监控对 transform 的影响 | — | **0** (`check_exact=True`) |
| 被删符号 | 存在 | **`AttributeError`** |
| 旧 JSON 含已删字段 | 可加载 | **仍可加载** (Pydantic `extra='ignore'`) |
| 定向套件 | 全绿 | **全绿, 无新增失败** |
| `fit+transform` 耗时 (12 因子 × 750 行) | 基线 T0 | **≤ 1.05 × T0** (移除 VR/DF 应更快) |

### 0.3 一句话方案

> **把"按因子历史序列类型分流到三条管道"整体替换为"所有因子走同一条横截面秩管道"**; 指纹保留为只读诊断并附采样频率元数据; 管道选择与采样频率进入规格日志; 结构突变检测下沉到监控层; Dynamic 仅在显式 A/B 模式下作为整臂开关。

---

## §1 目标与非目标

### 1.1 目标

1. **收纳复杂度**: 删除零生产调用的软路由、五步多维树、线性混合器, 以及只服务于它们的配置字段。
2. **消除基准漂移**: 同一因子在任何历史窗口下都走同一条管道, 输出只随数据变化, 不随分类标签跳变。
3. **标签唯一化**: 每个因子只有"诊断类型"一个标签 + "执行管道"一个事实, 两者同表呈现, 不再各说各话。
4. **可审计**: 管道选择、缩尾规则、采样频率、指纹诊断写入 append-only 规格日志(opt-in)。
5. **可观测**: 结构突变检测可在监控层显式调用, 只产出告警, 不改变 `fit`/`transform`。
6. **保留实验能力**: Dynamic 以整臂 A/B 模式保留, 不参与逐因子路由。

### 1.2 非目标

| 项 | 归属/说明 |
|----|-----------|
| 实现 MAD 缩尾 | 与 1%/99% 在排序下游近似等价; 作为独立实验(§9 O1), 本次不做 |
| 删除 `StatisticalClassifier` 模块 | 仍是可独立调用的统计工具(现有 4 个单测文件); 仅移出生产路径 |
| 删除 `MixedFactorPipeline` / `DynamicFactorPipeline` | 作为显式组件/消融基线保留 |
| 修复 Dynamic 的"neutralizer 关 → AR 解耦也关"耦合 | 组件可分离性缺陷, 独立问题(§9 O2) |
| 删除 `_ks_migration_significance` / `check_type_migration` | 迁移诊断工具, 非路由路径; 保留 |
| 改造 `monitor_cusum_drift` | 已属监控层, 行为不变 |
| 修改 21 维指纹数值契约 | 采样频率放入 `FingerprintMeta`, 不改 NamedTuple |
| 重设计 `EndToEndThresholdOptimizer` | 仅收缩搜索空间; 正交化搜索保留 |
| DuckDB 指纹日志 schema 迁移 | `weight_static/dynamic/mixed` 列保留, 不写入 |
| 新增 IC / 组合评估器 | A/B 复用现有回测设施(§6.4) |
| 处理 `migration_threshold` 死字段 | 非路由相关, 登记为独立清理项(§9 O3) |

---

## §2 现状与约束

### 2.1 当前生产路径(代码事实)

| 位置 | 现状 | 与本设计关系 |
|------|------|-------------|
| [`FactorProcessingPipelineV2.fit`](../../pipelines_v2.py#L1282-L1398) | 每因子 `stat_clf.classify(...)` → 单管道 | **替换** |
| [`fit` 路由两行](../../pipelines_v2.py#L1369-L1382) | `pipe_type = stat_clf.classify(...)`; `factor_pipes[pipe_type]` | **删除** |
| [`transform` 硬路由](../../pipelines_v2.py#L1438-L1450) | `pipe_type = pipe_keys[0]` | **保留形态**, 键值改为 `'static'`/`'dynamic'` |
| [`_create_pipeline`](../../pipelines_v2.py#L1493-L1537) | 三分支 `static`/`dynamic`/`mixed` | **保留三分支作为显式工厂**; `fit` 只传 `static`/`dynamic` |
| [`_get_pipeline_weights`](../../pipelines_v2.py#L54-L97) | 软路由权重 | **删除** |
| [`_get_multi_dim_pipeline_weights`](../../pipelines_v2.py#L104-L225) | 五步多维树 | **删除** |
| [`_apply_weighted_transform`](../../pipelines_v2.py#L228-L271) | 线性混合器 | **删除** |
| [`PipelineV2Config`](../../pipelines_v2.py#L680-L790) | `hard_routing_prob` L706 / `merge_alpha` L707 / `ks_alpha` L708 / `mixed_winsor_sigma` L709 / `enable_multi_dim_routing` L724 | **删除 5 个字段** |
| [`StaticFactorPipeline`](../../pipelines_v2.py#L860-L938) | imputer → 1%/99% → 中性化 → rank → z | **作为统一管道** |
| [`DynamicFactorPipeline`](../../pipelines_v2.py#L941-L1051) | imputer → 三重解耦 → z | **A/B 臂** |
| [`MixedFactorPipeline`](../../pipelines_v2.py#L1054-L1175) | imputer → 3σ → 中性化 → rank → z | **显式组件** |
| [`get_classification_summary`](../../pipelines_v2.py#L2139-L2141) | 仅指纹标签 | **加执行管道列** |
| [`get_execution_summary`](../../pipelines_v2.py#L2173-L2196) | 打印指纹分类 | **拆分执行/诊断两段** |
| [`optimizer.DEFAULT_SEARCH_SPACE`](../../optimizer.py#L47-L56) | 8 个路由/管道阈值 | **清空** |
| [`config_v2.to_pipeline_v2_config`](../../config_v2.py#L467-L539) | 桥接 4 个共享字段 | **删字段, 加模式** |

### 2.2 上游调研的承重结论

| 结论 | 证据 | 设计含义 |
|------|------|----------|
| 软路由/多维树/混合器零生产调用 | 调研 A1/A2 | 可删 |
| 默认 sigmoid 下 static/mixed 硬路由不可达 | 调研 A7 | 软路由即使接线也不成立 |
| Static 与 Mixed 秩相关 0.999998 | 调研 §4.3 | 统一为一条不损失信息 |
| Static 与 Dynamic 秩相关 0.308 | 调研 §4.3 | 换管道=换信号, 必须固定 |
| 12 因子改走 Dynamic 平均 \|IC\| −37.6% | 调研 §6.3 | 不作为默认 |
| 指纹两分类器一致率 49.5% | 调研 §4.4 | 标签只保留一套(诊断) |
| 频率改变标签(日频 static / 月频 dynamic) | 调研 §4.5 | 频率必须进元数据 |
| 2σ 均值突变可把 φ=0.20 推到 mixed | 调研 §5.3 | 断点检测只进监控层 |

### 2.3 约束

- `FactorFingerprint` 是 21 个数值字段的 `NamedTuple`, 被 `FingerprintPerformanceLogger` 按字段名消费; **不得插入/重排字段**。
- `fit`/`transform` 的公共签名不变: `fit(factor_data, industry_data=None, market_cap_data=None, descriptions=None, **kwargs)`; `transform(factor_data, **kwargs)`。
- `factor_pipelines` 的既有形态 `{factor_name: {pipe_type: pipe}}` 保持; 键值集合从 `{static,dynamic,mixed}` 收缩为 `{static}` 或 `{dynamic}`。
- `get_classification_summary()` 的既有列 `factor_name/primary_type/primary_prob` 必须保留(现有集成测试按列取值)。
- 与 `PipelineV2ConfigUnified` 的桥接必须同步; 该模型 `extra='ignore'`, 旧 JSON 可继续加载。
- 所有新功能默认关闭或保持现行为; 唯一有意的行为变化是"默认不再按分类选管道"。

---

## §3 方案设计

### 3.1 配置面

#### 3.1.1 新增字段([`PipelineV2Config`](../../pipelines_v2.py#L680))

```python
# v3.4.0 ADR-042: 统一管道模式
# 'unified'    — 所有因子走同一条横截面秩管道 (默认)
# 'dynamic_ab' — 所有因子走 DynamicFactorPipeline (仅显式 A/B 实验)
pipeline_mode: str = 'unified'
# 指纹诊断开关 (默认开, 只读, 不参与任何路由)
enable_fingerprint_diagnostics: bool = True
# A/B 实验标识 (写入规格日志; 非 A/B 时为 None)
ab_experiment_id: Optional[str] = None

# v3.4.0: 结构突变监控 (默认关闭, 只告警)
enable_break_monitor: bool = False
break_monitor_window: int = 250
break_monitor_stride: int = 20
break_monitor_alpha: float = 0.05
break_monitor_n_bootstrap: int = 400
```

`__post_init__` 校验:

```python
def __post_init__(self):
    if self.pipeline_mode not in ('unified', 'dynamic_ab'):
        raise ValueError(
            f"pipeline_mode 必须为 'unified' 或 'dynamic_ab', 实际: {self.pipeline_mode!r}"
        )
```

#### 3.1.2 删除字段

| 字段 | 位置 | 唯一消费者 |
|------|------|-----------|
| `enable_multi_dim_routing` | [pipelines_v2.py L724](../../pipelines_v2.py#L724) | 无(零读取点) |
| `hard_routing_prob` | [L706](../../pipelines_v2.py#L706) | `_get_pipeline_weights` |
| `merge_alpha` | [L707](../../pipelines_v2.py#L707) | 无 |
| `mixed_winsor_sigma` | [L709](../../pipelines_v2.py#L709) | `_create_pipeline('mixed')`(删除传参, 依赖 `MixedFactorPipeline.__init__` 默认 3.0) |
| `ks_alpha` | [L708](../../pipelines_v2.py#L708) | 无(KS 工具用函数参数; 配置侧仅桥接/测试) |

同步删除 `PipelineV2ConfigUnified` 中的 **5 个 Pydantic 字段**(`hard_routing_prob` / `merge_alpha` / `ks_alpha` / `mixed_winsor_sigma` / `transform_aggressiveness`, 后者仅被 optimizer 用于操纵 `mixed_winsor_sigma`, 随之退场; [config_v2.py L404-424](../../config_v2.py#L404-L424)); `to_pipeline_v2_config` 增加 `pipeline_mode` / `enable_fingerprint_diagnostics` / `ab_experiment_id` / 断点监控 5 字段的传递, 删除上述 5 个字段传递。

> 兼容性说明: `PipelineV2ConfigUnified` 设置 `extra='ignore'`, 因此含旧字段的 JSON 仍可加载; dataclass 侧删除字段后, 任何显式传参的调用点必须在同一提交内清理(见 §5.3 清单)。

### 3.2 统一管道

`pipeline_mode='unified'` 时, `fit` 只调用 `_create_pipeline('static', ...)`。`_create_pipeline` 仍保留 `'mixed'` 分支作为**显式工厂**(供消融/测试直接构造), 但删除其中 `mixed_winsor_sigma=self.config.mixed_winsor_sigma` 的传参([pipelines_v2.py L1528](../../pipelines_v2.py#L1528)), 依赖 [`MixedFactorPipeline.__init__` 默认值 3.0](../../pipelines_v2.py#L1071)。

```
原始面板 (T×N)
  → 1. ImputerAdapter(ffill_ts)                       # 因果: 仅用 t−1 及之前
  → 2. ProcessingAdapter(outlier, percentile, 1/99)   # 逐日横截面硬截断
  → 3. NeutralizerAdapter(industry[, marketcap])      # 与现 Static 完全相同
  → 4. ProcessingAdapter(transformation, rank, normal)# CSRankNorm
  → 5. ProcessingAdapter(standardization, z_score)    # 逐日横截面, rank-preserving
  → (可选) GarchWhiteningAdapter                      # 默认关闭
```

**不新增管道类**: 统一管道就是参数化后的 `StaticFactorPipeline`, 构造参数与现 [`_create_pipeline('static')`](../../pipelines_v2.py#L1502-L1517) 完全一致。这样"统一"与"旧 Static"在代码层面是同一条路径, 便于做逐位等价验收。变换方法仍由 `static_transformation_method` / `static_target_distribution` 控制(默认 `rank`/`normal`); 若使用者显式改成非 rank, 属显式规格, 会被写入规格日志(§3.6), 不视为隐藏分支。

**缩尾选择理由**: 1%/99% 分位是现 Static 的既有规则, 研究 §4.3 实测其输出相对 3σ 的截面秩相关中位 0.999998 (1−ρ 中位 ≈2e-6, 因子间范围 1e-6~4e-6), 差异仅来自缩尾尾部 tie 间距, 对 rank IC / 分位组合无影响; 保留它可使 12 个历史 static/mixed 因子的输出**逐位不变**。MAD 作为独立实验保留(§9 O1)。

### 3.3 `fit` / `transform` 重构

#### 3.3.1 `fit`(伪代码)

```python
def fit(self, factor_data, industry_data=None, market_cap_data=None,
        descriptions=None, **kwargs):
    # 1) 输入校验 (不变)
    ...
    # 2) 执行管道由模式唯一决定, 与数据无关
    pipe_type = 'static' if self.config.pipeline_mode == 'unified' else 'dynamic'

    # 3) 指纹提取与监控 (始终执行: 供 monitor/迁移检查/RoutingRecord,
    #    不受诊断开关影响 —— 见 MAJOR-2 修复说明)
    fingerprints = self.fingerprinter.batch_extract(factor_data)

    # 4) 诊断标签 (受 enable_fingerprint_diagnostics 控制)
    classifications = {}
    if self.config.enable_fingerprint_diagnostics:
        classifications = self._classify_diagnostics(
            fingerprints, descriptions, kwargs)

    # 5) 逐因子创建并拟合同一类型的管道
    neutralizer_params = self._build_neutralizer_params(industry_data, market_cap_data)
    for name, df in factor_data.items():
        pipe = self._create_pipeline(pipe_type, neutralizer_params,
                                     self.config.module_enabled)
        pipe.fit(df, **kwargs)
        self.factor_pipelines[name] = {pipe_type: pipe}

        fp = fingerprints.get(name, FactorFingerprint())
        cls = classifications.get(name, _unknown_classification())
        self.factor_classifications[name] = cls          # 兼容属性(诊断)
        record = FactorRoutingRecord(
            factor_name=name,
            pipeline_mode=self.config.pipeline_mode,
            execution_pipe_type=pipe_type,
            diagnostic_type=cls.primary_type.value,
            diagnostic_prob=cls.primary_prob,
            diagnostic_confidence=cls.confidence,
            ar1_median=fp.ar1_median,
            fingerprint_meta=FingerprintMeta(
                sampling_frequency=infer_sampling_frequency(df.index),
                n_obs=int(df.shape[0]),
                n_columns=int(df.shape[1]),
                start=_fmt_ts(df.index.min()) if len(df.index) else None,
                end=_fmt_ts(df.index.max()) if len(df.index) else None,
            ),
        )
        self.factor_routing[name] = record
        self._log_spec(record)

    # 5) 监测器 / 兼容属性 / is_fitted (形态不变)
    ...
```

> `_fmt_ts(ts)` 为 `pd.Timestamp` → ISO 字符串(失败返回 `None`); `_unknown_classification()` 返回 `ClassificationResult(primary_type=FactorType.UNKNOWN, primary_prob=0.0)`。

新增私有方法:

| 方法 | 签名 | 作用 |
|------|------|------|
| `_classify_diagnostics` | `(fingerprints, descriptions, kwargs) -> Dict[str, ClassificationResult]` | 有 `descriptions` 时走 `SemanticStatisticalFusion.classify`, 否则 `AdaptiveFactorClassifier.batch_classify`; **只产标签, 不选管道** |
| `_build_neutralizer_params` | `(industry_data, market_cap_data) -> dict` | 组装 `industry_data` / `market_cap_data` / `neutralization_type`(与现 fit 完全一致) |
| `_log_spec` | `(record) -> Optional[str]` | §3.6 |
| `_fmt_ts` | `(ts) -> Optional[str]` | 元数据时间格式化 |
| `_unknown_classification` | `() -> ClassificationResult` | 诊断关闭时的占位标签 |

> `get_classification_summary()` 以 `factor_classifications` 为主表、`factor_routing` 为右表拼接执行管道列; 诊断关闭时每行 `primary_type='unknown'`(占位, 保持表结构稳定), 执行事实始终可从 `get_routing_summary()` 获取。
>
> **开关语义边界 (review 修正)**: `enable_fingerprint_diagnostics` 只控制**分类标签**的计算; 指纹提取(`batch_extract`)与 `monitor.add_fingerprint` 始终执行 —— 否则会连带关闭 `get_fingerprint_summary()` 与 `check_migrations()` 的数据源, 而"迁移监控"并不在该开关的语义内。

**关键删改**:

| 项 | 变更 |
|----|------|
| `from factor_pipeline.modules.statistical_classifier import StatisticalClassifier` | 删除 |
| `stat_clf = StatisticalClassifier(...)` | 删除 |
| `pipe_type = stat_clf.classify(...)` | 改为由 `pipeline_mode` 决定 |
| `factor_pipes = {}; factor_pipes[pipe_type] = ...` | 简化为直接构造 |
| `self.static_pipeline/dynamic_pipeline/mixed_pipeline` 回填 | 按实际创建类型回填, 其余置 `None` |

#### 3.3.2 `transform`

```python
for name, data in factor_data.items():
    pipes = self.factor_pipelines.get(name)
    if not pipes:
        if self.strict_mode:
            raise ValueError(f"因子 {name} 未在 fit 阶段拟合")
        logger.warning(f"因子 {name} 未拟合, 跳过")
        continue
    pipe_type = next(iter(pipes))          # 唯一管道
    results[name] = pipes[pipe_type].transform(data)
```

- 删除"未分类则跳过"的判断(分类不再是前置条件)。
- 保留 `post_transform_hooks` 与 `_intermediate_data` 逻辑(不变)。
- `_get_pipeline(FactorType)` 仅作为 mock 场景兜底: 按 `pipeline_mode` 返回 `static_pipeline` 或 `dynamic_pipeline`。

### 3.4 诊断数据模型

新增两个不可变 dataclass(放在 `pipelines_v2.py` 配置区之后):

```python
@dataclass(frozen=True)
class FingerprintMeta:
    """指纹采集元数据 — 不进入 21 维数值指纹契约."""
    sampling_frequency: str = 'unknown'   # daily/weekly/monthly/quarterly/annual/irregular/unknown
    n_obs: int = 0
    n_columns: int = 0
    start: Optional[str] = None
    end: Optional[str] = None


@dataclass(frozen=True)
class FactorRoutingRecord:
    """单因子的执行事实 + 诊断标签 (唯一可信来源)."""
    factor_name: str
    pipeline_mode: str
    execution_pipe_type: str              # 'static' | 'dynamic'
    diagnostic_type: str                  # 'static'|'mixed'|'dynamic'|'unknown'
    diagnostic_prob: float
    diagnostic_confidence: float
    ar1_median: float
    fingerprint_meta: FingerprintMeta
```

**为什么不动 `FactorFingerprint`**: 它是 21 维数值 `NamedTuple`, 被 [FingerprintPerformanceLogger](../../backtest/fingerprint_performance_logger.py#L24-L36) 按固定字段名写入 DuckDB。插入字符串/整数字段会破坏"21 维数值指纹"契约, 且需要 schema 迁移。采样频率属于"采集元数据", 放在 `FingerprintMeta` 语义更准确。

`__init__` 新增两个状态容器(初值空):

```python
self.factor_routing: Dict[str, FactorRoutingRecord] = {}
self.break_alerts: Dict[str, Dict] = {}
```

### 3.5 采样频率推断

在 [fingerprint.py](../../modules/factor_fingerprint/core/fingerprint.py) 新增模块级函数并从包 `__init__` 导出:

```python
def infer_sampling_frequency(index: pd.Index) -> str:
    """按索引相邻间隔中位数判定采样频率.

    规则 (median_delta 单位: 自然日):
      < 1                      → 'intraday'
      <= 2                     → 'daily'
      <= 8                     → 'weekly'
      <= 20                    → 'biweekly'
      <= 45                    → 'monthly'
      <= 135                   → 'quarterly'
      <= 400                   → 'annual'
      其他                      → 'irregular'
    非 DatetimeIndex / 有效间隔 < 2 个 → 'unknown'
    """
```

**为什么放在指纹模块**: 频率是"因子历史序列如何被采样"的属性, 与指纹同源; 且未来所有指纹消费方都能复用同一口径。`fit` 直接调用它构造 `FingerprintMeta`, 不依赖 `enable_fingerprint_diagnostics`。阈值口径为自然日: weekly 上界取 8(而非 5)以容纳真周频(中位 7 天)与节假日长周末; 其余各档含常规容差(biweekly 14+6 / monthly 30+15 / quarterly 91+44 / annual 365+35)。

### 3.6 规格日志接线

`__init__` 增加懒初始化引用:

```python
self._spec_logger: Optional[Any] = None      # 已存在, 复用
```

新增私有方法:

```python
def _log_spec(self, record: FactorRoutingRecord) -> Optional[str]:
    if not getattr(self.config, 'enable_specification_logger', False):
        return None
    if self._spec_logger is None:
        from backtest.specification_logger import SpecificationLogger
        self._spec_logger = SpecificationLogger(log_dir=self.config.spec_log_dir)
    try:
        from backtest.cache_manager import CODE_VERSION as _CACHE_VERSION
    except Exception:
        _CACHE_VERSION = 'unknown'
    return self._spec_logger.log_run(
        config={
            'pipeline_mode': record.pipeline_mode,
            'execution_pipe_type': record.execution_pipe_type,
            'diagnostic_type': record.diagnostic_type,
            'diagnostic_prob': record.diagnostic_prob,
            'ar1_median': record.ar1_median,
            'sampling_frequency': record.fingerprint_meta.sampling_frequency,
            'n_obs': record.fingerprint_meta.n_obs,
            'n_columns': record.fingerprint_meta.n_columns,
            # 按"实际执行的管道"派生, 而非硬编码 (review MAJOR-1 修正):
            # static/unified 臂有缩尾+rank 变换; dynamic_ab 臂两者皆无
            'winsor': ('percentile(1,99)' if record.execution_pipe_type == 'static'
                       else 'none'),
            'transformation': (
                f"{self.config.static_transformation_method}"
                f"->{self.config.static_target_distribution}"
                if record.execution_pipe_type == 'static' else 'ar_residual->z_score'
            ),
            'ab_experiment_id': self.config.ab_experiment_id,
            'cache_version': _CACHE_VERSION,
        },
        result={'n_columns': record.fingerprint_meta.n_columns},
        run_type='validation' if self.config.ab_experiment_id else 'exploratory',
        factor_name=record.factor_name,
    )
```

对接的是既有 [`SpecificationLogger.log_run`](../../backtest/specification_logger/spec_log.py#L40-L74), **不新增日志设施**。默认关闭 → 不创建 `logs/specifications/` 目录。

### 3.7 结构突变监控

#### 3.7.1 新模块 `backtest/structural_break_monitor.py`

```python
@dataclass
class BreakMonitorConfig:
    method: str = 'sup_f'        # 'sup_f' | 'cusum'
    window: int = 250            # 滚动 AR(1) 窗口 (与调研 §5.4 一致)
    stride: int = 20
    min_points: int = 20
    trim: float = 0.15           # sup-F 断点搜索区间 [0.15, 0.85]
    alpha: float = 0.05
    n_bootstrap: int = 400       # sup-F 零分布自助次数
    random_state: int = 42


class StructuralBreakMonitor:
    def detect(self, path: pd.Series) -> Dict[str, Any]:
        """输入: AR(1) 中位数路径; 输出: 只读告警字典."""
```

返回契约:

```python
{
    'detected': bool,
    'method': 'sup_f' | 'cusum',
    'stat': float,
    'p_value': float,            # 两种方法均由自助零分布给出 (B=400)
    'break_index': Optional[int],# path 的整数位置
    'break_date': Optional[str],
    'n_points': int,
    'alpha': float,
}
```

实现要点:

| 方法 | 统计量 | 零分布 |
|------|--------|--------|
| `sup_f` | 对路径 `y_t = a + b·1{t>τ} + e_t` 在 `τ ∈ [trim, 1−trim]` 上取 sup-F 型统计量 `sup_τ (SSR₀−SSR₁(τ))/SSR₁(τ)` | 用路径自身 AR(1) 系数生成 B=400 条代理路径, 重算同一统计量 |
| `cusum` | Inclán–Tiao (ICSS) 思路: 对去均值平方 `(y_t − ȳ)²` 的累积和取 max(标准化)。注: 严格 ICSS 原式用残差平方 `e_t²`; 对已平滑的 AR(1) 路径用去均值平方是工程化变体, 在此明示 | 同一自助框架(B=400), 保证 p 值口径统一 |

只依赖 `numpy` / `pandas`, 不引入 `statsmodels`(避免与现有依赖面变化)。

#### 3.7.2 AR(1) 路径复用指纹口径

在 [`FactorFingerprinter`](../../modules/factor_fingerprint/core/fingerprint.py) 新增:

```python
def compute_ar1_path(self, factor_data: pd.DataFrame,
                     window: int = 250, stride: int = 20) -> pd.Series:
    """逐窗口调用 _compute_ar1_median, 返回带日期索引的 AR(1) 中位数路径."""
```

保证监控层与诊断层使用**同一 AR(1) 口径**(含 `min_obs_per_stock=12` / `min_cv_threshold=0.01` / `min_stocks=10`), 避免再次出现"两套口径各说各话"。

> 口径注记: 调研 §5.4 只规定"自助零分布 B=400"; 本设计的"用路径自身 AR(1) 系数生成代理路径"是自行补充的实现选择, 须在实施文档与代码注释中标注为设计决策(非文献直接给法)。

#### 3.7.3 管道方法

```python
def monitor_structural_breaks(
    self,
    factor_data: Dict[str, pd.DataFrame],
    *,
    method: str = 'sup_f',
    window: Optional[int] = None,
    stride: Optional[int] = None,
) -> Dict[str, Dict]:
```

- `enable_break_monitor=False` → 直接返回 `{}`(零成本)。
- 触发时写 `self.break_alerts[name]`(新增实例属性, 初值 `{}`)。
- **不修改 `fit` / `transform` / `factor_pipelines`**, 与 [`monitor_cusum_drift`](../../pipelines_v2.py#L1547-L1652) 同构。
- 成本: 每因子 `⌊(T−window)/stride⌋+1` 次指纹 AR(1) 计算; 默认参数下 1472 天 ≈ 62 次/因子, 显式调用才付出。

### 3.8 汇总表与执行摘要

```python
def get_classification_summary(self) -> pd.DataFrame:
    """诊断标签汇总 (兼容旧列; 新增执行管道列)."""
    # cost: factor_name, primary_type, primary_prob, secondary_type,
    #       secondary_prob, confidence, is_hard,
    #       execution_pipe_type, sampling_frequency
```

```python
def get_routing_summary(self) -> pd.DataFrame:
    """执行事实 + 诊断的单一可信视图."""
    # columns: factor_name, pipeline_mode, execution_pipe_type,
    #          diagnostic_type, diagnostic_prob, diagnostic_confidence,
    #          ar1_median, sampling_frequency, n_obs, n_columns, start, end
```

[`get_execution_summary`](../../pipelines_v2.py#L2173-L2196) 改为两段:

```
[执行管道]
  mode=unified, pipe=static, winsor=percentile(1,99), transform=rank->normal
  因子数: N
[指纹诊断 (只读)]
  roe: type=static, ar1=0.9888, freq=daily, conf=0.94
  ...
```

### 3.9 Dynamic A/B 协议

`pipeline_mode='dynamic_ab'` 只做一件事: 把**整臂**切到 `DynamicFactorPipeline`。A/B 的统计协议不进入代码, 写入文档与规格日志:

| 项 | 要求 |
|----|------|
| 数据切分 | 同一 `fit` 窗口(如前 750 日), 同一 OOS 区间 |
| 调仓/收益 | 同一调仓频率与同一前向收益口径 |
| 评估 | 逐因子 \|IC\| + 组合净值; 报告配对差与 bootstrap 置信区间 |
| 多重检验 | 按因子数做 BH-FDR (Benjamini & Hochberg 1995; 直接复用 [`backtest/multiple_testing.apply_bh_fdr`](../../backtest/multiple_testing.py)); 报告 Deflated Sharpe(Bailey & López de Prado 2014) |
| 结论门槛 | 仅当 Dynamic 臂在 OOS 上显著优于 Unified(校正后)才考虑保留实验 |
| 记录 | `ab_experiment_id` 写入规格日志, `run_type='validation'` |

> 该协议是"防止用 A/B 之名做隐式路由"的闸门: 模式只有两个值, 且每次切换必须留痕。

### 3.10 消融框架适配

[`backtest/ablation_runner.py`](../../backtest/ablation_runner.py) 当前通过 `_override_routing` 在 `fit` 后改写 `factor_classifications`, 以模拟 L2 路由消融。统一管道后该字段不再驱动路由, **若不同步改造, 所有 L2 路由消融会静默变成 no-op**。

改造方案:

| 项 | 现状 | 新设计 |
|----|------|--------|
| `AblationConfig.routing_mode` | `'full'/'static'/'dynamic'/'mixed'/'random'` | `'full'/'unified'/'dynamic'` |
| 生效时点 | `fit` 后覆盖分类 | **`fit` 前设置 `modified_config.pipeline_mode`** |
| `_override_routing` | 改写 `factor_classifications` | **删除**(含 `tests/unit/test_task1_l2_routing_fix.py` 5 个用例与 `test_ablation_runner.py` 全部路由臂断言用例) |
| `AblationRunner.run_l2` | 4 臂(static/dynamic/mixed/random) | **2 臂**(`unified` / `dynamic`) |
| 非法值 | 静默落到 random | `ValueError` |

映射:

```python
mode = 'dynamic_ab' if config.routing_mode == 'dynamic' else 'unified'
modified_config.pipeline_mode = mode
```

> 语义说明: 原 `'static'` 臂等价于新 `'unified'`; 原 `'dynamic'` 臂等价于新 `'dynamic_ab'`; 原 `'mixed'` 与 `'random'` 臂随三路路由一起退场, 不再提供。
>
> 附带发现: L3 消融的 `routing_threshold_scale` 写入 `modified_config._l3_routing_threshold_scale` 后**无任何读取点**(既有死参数), 与本次路由退场叠加后彻底失效; 登记为 §9 O7, 本次不处理。

---

## §4 接口与签名

### 4.1 变更后的公共接口

| 接口 | 变更 | 兼容性 |
|------|------|--------|
| `PipelineV2Config(...)` | 新增 8 字段; 删除 5 字段 | 构造签名变化(见 §5.3) |
| `FactorProcessingPipelineV2.fit(...)` | 签名不变; 行为改为模式驱动 | ✅ |
| `FactorProcessingPipelineV2.transform(...)` | 签名不变; 不再要求分类 | ✅ |
| `FactorProcessingPipelineV2.get_classification_summary()` | 增 2 列 | ✅ 旧列保留 |
| `FactorProcessingPipelineV2.get_routing_summary()` | **新增** | — |
| `FactorProcessingPipelineV2.get_execution_summary()` | 文案/结构变化 | 返回值仍为 `str` |
| `FactorProcessingPipelineV2.monitor_structural_breaks(...)` | **新增** | — |
| `StaticFactorPipeline` / `DynamicFactorPipeline` / `MixedFactorPipeline` | 不变 | ✅ |
| `infer_sampling_frequency(index)` | **新增**(模块级) | — |
| `FactorFingerprinter.compute_ar1_path(...)` | **新增** | — |
| `StructuralBreakMonitor` / `BreakMonitorConfig` | **新增** | — |

### 4.2 删除的符号

| 符号 | 类型 | 现有引用 |
|------|------|----------|
| `_get_pipeline_weights` | 模块函数 | tests ×3 文件 |
| `_get_multi_dim_pipeline_weights` | 模块函数 | tests ×1 文件(20 用例) |
| `_apply_weighted_transform` | 模块函数 | tests ×1 文件 |
| `PipelineV2Config.enable_multi_dim_routing` | 字段 | tests ×1 |
| `PipelineV2Config.hard_routing_prob` | 字段 | optimizer, config_v2, tests |
| `PipelineV2Config.merge_alpha` | 字段 | optimizer, config_v2, tests |
| `PipelineV2Config.mixed_winsor_sigma` | 字段 | optimizer, config_v2, tests |
| `PipelineV2Config.ks_alpha` | 字段 | optimizer, config_v2, tests |

删除后 `from factor_pipeline.pipelines_v2 import _get_pipeline_weights` 应抛 `ImportError`; `getattr(config, 'hard_routing_prob')` 应抛 `AttributeError`。

### 4.3 `factor_pipelines` 数据契约

| 场景 | 形态 |
|------|------|
| `pipeline_mode='unified'` | `{name: {'static': StaticFactorPipeline}}` |
| `pipeline_mode='dynamic_ab'` | `{name: {'dynamic': DynamicFactorPipeline}}` |
| `mixed` | 不再出现 |

### 4.4 优化器收缩

```python
# v3.4.0 ADR-042: 路由阈值退场, 默认无可搜参数
DEFAULT_SEARCH_SPACE: Dict[str, Dict[str, Any]] = {}
```

- `EndToEndThresholdOptimizer(n_trials=...)` 在无 `search_orth` 时发出 `DeprecationWarning`, `optimize()` 抛 `ValueError("无参数可搜索: 路由阈值已随统一管道退场; 如需正交化搜索请传 search_orth=True")`。
- `search_orth=True` 时仅保留 `DEFAULT_SEARCH_SPACE_ORTH`。
- `_params_to_config` 删除 4 个共享字段与 `transform_aggressiveness` 分支; `_config_to_params` 同步。
- `classification_threshold_static/dynamic` 与 `migration_threshold` 也移出搜索空间(前者只影响诊断, 后者无读取点), 但配置字段保留。

---

## §5 实施切分与兼容

### 5.1 任务分解(供步骤 5 实施文档引用)

| 任务 | 内容 | 依赖 |
|------|------|------|
| **E1** 配置面 | 新增/删除字段; `__post_init__` 校验; `config_v2` 桥接; optimizer 收缩 | — |
| **E2** 统一执行 | `fit`/`transform` 重构; `_create_pipeline` 仅由 `fit` 传 `static`/`dynamic`; 兼容属性 | E1 |
| **E3** 诊断层 | `infer_sampling_frequency`; `FingerprintMeta`/`FactorRoutingRecord`; 汇总表 | E2 |
| **E4** 规格日志 | `_log_spec` 接线; 开关/路径/行数验收 | E3 |
| **E5** 断点监控 | `structural_break_monitor.py`; `compute_ar1_path`; `monitor_structural_breaks` | E3 |
| **E6** 清理与发布 | 删除 3 函数 + 相关路由用例(test_multi_dim 20 + test_p0_fixes 8; `TestGetPipelineWeightsHardRouting` 3 实居 test_p3_phase2 — v1.2 勘误); 更新测试; 版本/缓存/ADR/文档 | E2–E5 |
| **E7** 消融适配 | `AblationConfig.routing_mode` 改为模式映射; 删除 `_override_routing` 及其全部路由臂用例(test_task1 5 → 3 净删 2 + test_ablation_runner 路由臂用例改写/删除, 精确账目见实施 §8.2) | E2 |

### 5.2 版本与缓存

| 项 | 现值 | 新值 | 文件 |
|----|------|------|------|
| 项目版本 | 3.3.7 | **3.4.0** | [`__init__.py` L58](../../__init__.py#L58), `pyproject.toml` |
| 缓存代际 | `v2.2.5-cache` | **`v2.3.0-cache`** | [`backtest/cache_manager.py` L58](../../backtest/cache_manager.py#L58) |
| 决策记录 | ADR-041 | **ADR 编号待分配** (暂用号 ADR-042, 落库时取号) | [`DECISIONS.md`](../../DECISIONS.md) |

理由: 默认输出对"原 static/mixed 因子"逐位不变, 对"原 dynamic 因子"变化(改走统一管道), 且删除配置字段; 缓存必须换代。

### 5.3 必须同批清理的调用点

| 文件 | 位置 | 处理 |
|------|------|------|
| [`config_v2.py`](../../config_v2.py#L404-L539) | Pydantic 字段 + 桥接 | 删 5 字段(4 共享 + `transform_aggressiveness`), 加新字段 |
| [`optimizer.py`](../../optimizer.py#L47-L224) | 搜索空间 + 双向映射 | 清空默认空间, 删分支 |
| [`tests/test_multi_dim_classifier.py`](../../tests/test_multi_dim_classifier.py) | 20 用例 | **整文件删除** |
| [`tests/test_p0_fixes.py`](../../tests/test_p0_fixes.py#L31-L500) | `TestSoftRouting`(8, 含加权混合 test_04/05; test_06 为单管道路由 — v1.2 勘误) | 删除该测试类 (`TestGetPipelineWeightsHardRouting` 实居 test_p3_phase2 L80, 见下行 — v1.2 勘误) |
| [`tests/test_p3_phase2_config_migration.py`](../../tests/test_p3_phase2_config_migration.py#L13-L141) | `TestPipelineV2ConfigNewFields`(断言 4 个将删字段) + `TestGetPipelineWeightsHardRouting`(L81-141) + `TestTransformConfigPassing` test_10/11(`PipelineV2Config(ks_alpha=...)`/`(merge_alpha=...)`) | 删除/改写相关用例; `MixedFactorPipeline` 直接构造用例保留 |
| [`tests/test_fix2_config_unification.py`](../../tests/test_fix2_config_unification.py#L90-L300) | 4 共享字段断言 | 改为新字段断言 |
| [`tests/manual/verify_v2_6_0_e7_manual.py`](../../tests/manual/verify_v2_6_0_e7_manual.py) | 手工脚本参数 | 同步删参数 |
| [`tests/manual/verify_v2_6_0_manual.py`](../../tests/manual/verify_v2_6_0_manual.py#L97-L198) | L97 断言 `len(search_space)==8`; L197-198 传 4 字段 | 同步删参数 |
| [`notebooks/demo_v3_1_0.py`](../../notebooks/demo_v3_1_0.py#L124) | `from factor_pipeline.pipelines_v2 import _get_pipeline_weights` | 更新示例或删除该 import |
| [`backtest/ablation_runner.py`](../../backtest/ablation_runner.py#L575-L630) | `_override_routing` + 4 臂 | 按 §3.10 改为模式映射 |
| [`tests/unit/test_task1_l2_routing_fix.py`](../../tests/unit/test_task1_l2_routing_fix.py) | 5 用例(4 override + `test_full_l2_routing_pipeline` 断言 `len==5`) | 改写 3 (2 模式映射 + 1 run_l2 计数), 净删 2 — v1.2 以实施 §8.2/§9.5 为权威口径 |
| [`tests/test_backtest/test_ablation_runner.py`](../../tests/test_backtest/test_ablation_runner.py#L419-L428,L1091-L1144,L1827-L1930) | `test_l2_config_routing_mode` + `TestL2Ablation`(**9 方法**, L1094-1214 — v1.2 勘误) + `TestRoutingOverride`(5 方法, L1826-1930) | 删除/改写为 `pipeline_mode` 注入断言 (处置见实施 §9.5) |
| [`demo_v2.py`](../../demo_v2.py) / [`notebooks/demo_v3_3_0.py`](../../notebooks/demo_v3_3_0.py) | 示例 | 保留类导入; 更新路由叙述 |

### 5.4 数据/因果约束

- 统一管道第 2/4/5 步均为**逐日横截面**, 无跨期拟合参数; 第 1 步 `ffill_ts` 只用历史; 第 3 步中性化按 `fit` 期估计, `transform` 不重估 → 截断不变式保持。
- `monitor_structural_breaks` 只读输入面板, 不写 `fit` 状态, 不改变 `transform` 输出。
- 规格日志为 append-only, 不参与计算。

---

## §6 测试计划(TDD)

### 6.1 新增测试

`tests/test_unified_routing.py`:

| # | 用例 | 断言 |
|---|------|------|
| T1 | 默认模式 | `PipelineV2Config().pipeline_mode == 'unified'`; 非法值 `ValueError` |
| T2 | 统一输出逐位等价 | `fit_transform` 结果与 `StaticFactorPipeline(...).fit_transform` `assert_frame_equal(check_exact=True)`(12 因子) |
| T3 | Dynamic A/B 逐位等价 | `pipeline_mode='dynamic_ab'` 与 `DynamicFactorPipeline(...)` 完全一致 |
| T4 | Mixed 不再自动创建 | 所有 `factor_pipelines` 值中无 `MixedFactorPipeline` |
| T5 | 删除符号 | `import _get_pipeline_weights` → `ImportError`; config 字段 `AttributeError` |
| T6 | 诊断开关 | `enable_fingerprint_diagnostics=False` → `factor_classifications[*].primary_type == 'unknown'` 且 `factor_routing[*].diagnostic_type == 'unknown'`; `transform` 输出与开启时 `check_exact=True`; `get_fingerprint_summary()` 与 `check_migrations()` 数据源**不受影响**(指纹提取始终执行) |
| T7 | 采样频率 | 日频/周频/月频/不规则索引分别映射 `daily`/`weekly`/`monthly`/`irregular`(周频用中位间隔 7 天的索引); 非日期索引 `unknown` |
| T8 | 汇总表 | `get_classification_summary` 含 `execution_pipe_type`/`sampling_frequency`; `get_routing_summary` 行数 = 因子数 |
| T9 | 规格日志(开) | `enable_specification_logger=True` → JSONL 行数 = 因子数, 含 `execution_pipe_type`/`sampling_frequency`; **unified 臂** `winsor='percentile(1,99)'`、`transformation='rank->normal'`; **dynamic_ab 臂** `winsor='none'`、`transformation='ar_residual->z_score'` |
| T10 | 规格日志(关) | 默认关闭 → 目录不创建, 行数 0 |
| T11 | 断点监控默认关 | `monitor_structural_breaks` 返回 `{}` |
| T12 | 断点监控不影响输出 | 开监控前后 `transform` 结果 `check_exact=True` |
| T13 | 未拟合因子 | 严格模式抛错 / 非严格跳过(保留现行为) |
| T14 | 旧 JSON 兼容 | 含 `hard_routing_prob` 等旧字段的 dict → `PipelineV2ConfigUnified(**old)` 成功 |

`tests/test_structural_break_monitor.py`:

| # | 用例 | 断言 |
|---|------|------|
| B1 | 已知断点 | 用 `compute_ar1_path` 从合成面板(**T=1472**, φ=0.2, 中段 +2σ; 注意非调研 §5.3 场景 — 该场景 T=750 仅 26 点, 62 点账目仅对 T=1472 成立)生成**真实滚动路径**(⌊(1472−250)/20⌋+1 = 62 点), `detected=True` 且 `break_index` 落在污染段内(±3 个路径点, 以 path 位置计; AR(1) 对均值突变呈驼峰响应, 定位的是峰值) — v1.2 勘误 |
| B2 | 无断点 | 白噪声路径 `detected=False`(固定种子) |
| B3 | CUSUM 路径 | 方差突变(后半段 **×4**; ×2 在 B=400 自助下属边缘 — v1.2 勘误) `detected=True` |
| B4 | 输入校验 | 空/过短路径 → `detected=False, reason='insufficient data'` |
| B5 | 纯函数 | 同一输入两次调用结果一致(固定种子) |
| B6 | 无副作用 | `detect` 不修改输入 `Series` |

### 6.2 更新/删除测试

| 文件 | 处理 |
|------|------|
| `tests/test_multi_dim_classifier.py` | 删除(20 用例) |
| `tests/test_p0_fixes.py` | 删除 `TestSoftRouting`(8; 加权混合为 test_04/05) — `TestGetPipelineWeightsHardRouting` 实居 test_p3_phase2 (v1.2 勘误) |
| `tests/test_p3_phase2_config_migration.py` | 删除/改写 `TestPipelineV2ConfigNewFields` 与 `TestTransformConfigPassing` 中触雷字段用例; 保留 `MixedFactorPipeline` 直接构造用例 |
| `tests/test_fix2_config_unification.py` | 4 共享字段断言替换为 `pipeline_mode` 断言 |
| `tests/test_pipelines_v2.py` | 集成测试仍通过; 打印列改为 `execution_pipe_type` |
| `tests/integration/test_pipeline_truncation_invariance.py` | 不改(三个类仍存在) |
| `tests/test_adapters/test_module_enabled.py` | 不改 |
| `tests/test_backtest/test_ablation_runner.py` | 删除/改写全部路由臂断言用例 |
| `tests/unit/test_task1_l2_routing_fix.py` | 5 用例 → 3 (2 模式映射 + 1 run_l2 计数), 净删 2 (v1.2 勘误) |

### 6.3 回归基线

- 定向套件: `pytest tests/test_unified_routing.py tests/test_structural_break_monitor.py tests/test_pipelines_v2.py tests/integration/test_pipeline_truncation_invariance.py tests/test_adapters/test_module_enabled.py tests/test_p0_fixes.py -q`
- 实施前记录基线 passed/failed 数; 实施后**新增失败必须为 0**。
- 全量套件若存在环境性失败(如缺数据), 按既有基线对照。

### 6.4 A/B 验收(非单测)

| 项 | 要求 |
|----|------|
| 样本 | 调研 §6.2 的 12 因子; 前 750 日 fit, 其后每 20 日调仓, 20 日前向收益 |
| 记录 | 两臂逐因子 \|IC\|、配对差、bootstrap 95% CI |
| 判定 | 仅当 Dynamic 臂校正后显著更优才保留 A/B 结论; 否则维持 unified |

---

## §7 风险与回滚

| # | 风险 | 影响 | 缓解 |
|---|------|------|------|
| R1 | 原 dynamic 因子输出改变 | 历史基准中断 | 统一为固定规则后**不再随分类漂移**; A/B 可用 `dynamic_ab` 复现旧臂; 文档明示 |
| R2 | 删除配置字段破坏外部调用 | `TypeError` | 同批清理仓库内调用点; CHANGELOG 给迁移表; semver minor(v3.4.0) |
| R3 | 删除多维路由用例导致覆盖下降 | 覆盖数字变化 | 删除的是已删行为(test_multi_dim 20 + test_p0_fixes 8, 另 p3_phase2 8 — v1.2 勘误); 新增 T1–T14/B1–B6 覆盖替代路径 |
| R4 | 规格日志写盘失败 | `fit` 中断 | `_log_spec` 包 `try/except`, 失败仅 warning, 不影响拟合 |
| R5 | 断点监控成本高 | 运行变慢 | 默认关闭; 显式调用; 文档给出 62 次/因子估算 |
| R6 | 频率推断在非日期索引上误判 | 元数据错误 | 非 `DatetimeIndex` 返回 `unknown`, 不猜测 |
| R7 | 旧 DuckDB 指纹日志列 `weight_*` 恒空 | 报表空列 | schema 不动; 文档标注"路由权重列已废弃" |
| R8 | 优化器默认不可用 | 手工脚本报错 | `DeprecationWarning` + 明确 `ValueError`; 正交化搜索保留 |

**回滚**: 运行时无"恢复旧路由"开关(有意, 避免再次形成双路径)。回滚 = `git revert` 本次提交; 配置面回滚需同时恢复 `PipelineV2Config` 字段。A/B 实验不构成回滚路径, 仅用于评估。

---

## §8 外部锚点与设计依据

| 设计点 | 依据 | 调研位置 |
|--------|------|----------|
| 统一横截面秩管道 | Qlib `CSRankNorm`; WorldQuant `rank()`; Alphalens 分位分桶; Barra Descriptor Standardization | 调研 §7.3 |
| 排序对单调变换不变 | Fama-MacBeth (1973) 排序传统; rank IC 定义 | 调研 §6.1/§8.2 |
| 不做按类型择时 | Asness et al. (2017); Ehsani & Linnainmaa (2022) | 调研 §6.6 |
| 管道选择需 OOS + 多重检验 | Bailey & López de Prado (2014); Bailey et al. (2017) | 调研 §6.6 |
| A/B 多重检验校正 | Benjamini & Hochberg (1995), JRSS-B 57(1):289-300; 复用 [`backtest/multiple_testing.apply_bh_fdr`](../../backtest/multiple_testing.py) | — (设计新增引用; 调研无 BH 条目, 调研 §6.6 仅含 OOS/DSR — v1.2 勘误) |
| 选择路径需留痕 | Simmons et al. (2011); Simonsohn, Simmons & Nelson (2020), *Specification Curve Analysis*, Nature Human Behaviour 4(11):1208-1214 | 调研 §8.3 |
| 断点检测方法 | Andrews (1993); Bai & Perron (1998/2003); Inclán & Tiao (1994); Perron (1989) | 调研 §5.2 |
| 突变污染 AR(1) | Perron (1989) | 调研 §5.2/§5.3 |
| 近单位根伪因子 | Onatski & Wang (2021) | 调研 §5.2 |

---

## §9 未决项与后续独立任务

| # | 项 | 说明 | 建议 |
|---|----|------|------|
| O1 | MAD 缩尾实验 | 3×MAD 硬截断 vs 1%/99%; 排序下游预期差异极小 | 独立 A/B, 不与本次混做 |
| O2 | Dynamic 组件可分离性 | `module_enabled={'neutralizer': False}` 同时关闭 AR 解耦(调研 A8) | 独立缺陷修复 |
| O3 | `migration_threshold` 死字段 | 仅被赋值, 无读取点 | 独立清理 |
| O4 | `_ks_migration_significance` 接线或删除 | 仅手工测试引用 | 独立决策 |
| O5 | 指纹性能日志 `weight_*` 列 | 随路由退场恒空 | schema 迁移另行设计 |
| O6 | 断点监控调度 | 当前仅显式调用 | 由运行框架决定(周/月度任务) |
| O7 | `routing_threshold_scale` 死参数 | 写入 `_l3_routing_threshold_scale`, 无读取点 | 独立清理或删除 L3 消融臂 |

---

## §10 §11.2 建议映射

| §11.2 建议 | 级别 | 设计决策 | 验收 |
|-----------|------|----------|------|
| 明确"生产只走单管道", 停用/删除未接线软路由与多维树 | P0 | D4/D10; §3.1.2; §4.2/§4.4 | T5, T14 |
| 统一 Static/Mixed 缩尾规则, 三管道收敛为一条 | P0 | D2/D3; §3.2 | T2/T4 |
| 指纹降级为诊断; 执行层与展示层不再各说各话 | P1 | D5/D6; §3.3/§3.4/§3.8 | T6/T8 |
| 管道选择写入规格日志; 采样频率写入元数据 | P1 | D6/D7; §3.5/§3.6 | T7/T9/T10 |
| 结构突变检测移到监控层, 只告警 | P2 | D8; §3.7 | T11/T12/B1–B6 |
| Dynamic 仅在显式 A/B 开启, 做 OOS 显著性检验 | P2 | D1/D9; §3.9 | T3, §6.4 |

---

## §11 ADR 草案 (编号待分配 — DECISIONS.md 登记规则 2: 规划文档不得预留编号; 当前空闲号 ADR-042, 暂以其指代, 落库时回 DECISIONS.md 取号)

```markdown
## ADR-042 (暂用号, 落库时取正式编号): 统一横截面秩管道替代三路指纹路由 (v3.4.0)

**背景**: 调研 (docs/analysis/FACTOR_ROUTING_OVERENGINEERING_RESEARCH.md v1.1) 证实:
软路由/五步多维树/线性混合器零生产调用; 默认 sigmoid 下 static/mixed 硬路由不可达;
Static 与 Mixed 输出秩相关 0.999998; 指纹与 VR/DF 标签一致率 49.5%;
12 因子改走 Dynamic 平均 |IC| −37.6%; 路由链无结构突变检测,
而 AR(1) 本身会被 2σ 均值突变污染。

**决策**:
1. `PipelineV2Config.pipeline_mode` 默认 `'unified'`, 所有因子走同一条
   横截面秩管道 (imputer → 1%/99% 缩尾 → 中性化 → CSRankNorm → z);
2. 删除 `_get_pipeline_weights` / `_get_multi_dim_pipeline_weights` /
   `_apply_weighted_transform` 及 5 个只服务路由的配置字段;
3. 指纹降级为只读诊断, 采样频率写入 `FingerprintMeta`;
4. 管道选择/采样频率进入 `SpecificationLogger` (opt-in);
5. 结构突变检测下沉到 `StructuralBreakMonitor`, 只告警;
6. Dynamic 仅作为整臂 `'dynamic_ab'` 显式实验保留。

**后果**:
- 原 static/mixed 因子输出逐位不变; 原 dynamic 因子改走统一管道 (基准稳定化);
- 配置面缩小, 优化器默认搜索空间清空;
- 缓存代际 `v2.2.5-cache` → `v2.3.0-cache`。

**替代方案**: 保留三管道但默认 static (否决: 分类仍在跑, 标签仍会漂移);
统一 AR 残差化 (否决: 实测 |IC| 下降); MAD 缩尾 (延后为独立实验)。
```

---

## §12 修订记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-11-10 | 步骤 3 设计初稿: U1 统一管道 + §11.2 P0/P1/P2 全采纳; D1–D12 锁定 |
| v1.1 | 2026-11-10 | 步骤 4 幻觉消除 review 修订 (CRITICAL 1 / MAJOR 3 / MINOR 12, 全部修复)。C1 §5.3 清理清单补全: 新增 `notebooks/demo_v3_1_0.py` L124 的 `_get_pipeline_weights` import、`verify_v2_6_0_manual.py` L97/L197-198、`test_p3_phase2` 的 `TestPipelineV2ConfigNewFields`+`TestTransformConfigPassing` test_10/11、`test_ablation_runner` 的 `TestL2Ablation`(L1091-1144)+`test_l2_config_routing_mode`(L419-428), ablation 改造范围扩为全部路由臂用例。M1 §3.6 规格日志按执行臂派生 winsor/transformation (dynamic_ab 臂为 none/ar_residual->z_score), T9 补双臂断言; M2 §3.3 诊断开关语义边界明示: 指纹提取与 monitor.add_fingerprint 始终执行, 开关只控制分类标签 (否则连带关闭 get_fingerprint_summary/check_migrations), T6 补断言; M3 §3.2 "3e-6" 更正为实测口径 (Spearman 中位 0.999998, 1−ρ 中位 ≈2e-6, 范围 1e-6~4e-6)。m1 用例数勘误: test_multi_dim 31→20 (31 为跨文件合计 20+11), test_task1 4→5 (含 run_l2 全链用例), test_ablation_runner 4→5 方法且范围扩至 TestL2Ablation; m2 `TestWeightedTransform` 类名更正 (加权混合用例在 TestSoftRouting 内); m3 `transform_aggressiveness` 定案为随 Pydantic 侧一并删除 (共 5 字段); m4 §3.1.2 与 §3.2 的 mixed_winsor_sigma 处置统一为"删传参、依赖默认 3.0"; m5 B1 验收改为真实滚动路径 (compute_ar1_path), break_index 容差 ±3 并以 path 位置计; m6 §8 Fama-MacBeth 调研位置 §6.1→§6.1/§8.2; m7 §3.9 BH-FDR 补全归属 (Benjamini & Hochberg 1995) 并注明复用 multiple_testing.apply_bh_fdr, §8 补锚点行; m8 §3.5 weekly 阈值 5→8 (自然日口径下真周频中位 7 天), T7 补周频用例, 补各档容差说明; m9 §3.7 cusum 注明为 ICSS 工程化变体 ((y−ȳ)² vs 残差平方); m10 §3.7.2 注明 AR(1) 代理零分布为设计自行补充; m11 Simonsohn 2020 引用补全卷期 (NHB 4(11):1208-1214); m12 §3.10 用例数同步 |
| v1.2 | 2026-11-10 | 步骤 8 跨文档一致性 review 勘误 (MAJOR 3 / MINOR 4, 全部修复; 详见 docs/audit/CONSISTENCY_REVIEW_V3.4.0.md)。X2 §5.1-E6/§5.3/§6.2/§7-R3: p0_fixes 删除数 11→8 (`TestGetPipelineWeightsHardRouting` 实居 test_p3_phase2 L80, 非 test_p0_fixes; 加权混合为 test_04/05, test_06 为单管道路由); X3 §8 锚点表 BH 1995 行的"调研 §8.3"更正为"设计新增引用" (调研无 BH 条目); X4 §头/§0.1-D11/§5.2/§11: ADR-042 预留编号违 DECISIONS.md 登记规则 2, 全部改为"ADR 编号待分配 (暂用号 ADR-042)"; X6 §6.1 B1 补 T=1472 显式声明 (非调研 §5.3 场景) + 驼峰注记、B3 方差 ×2→×4 (回port 实施 v1.1 C2/m9); X7 §5.3 类名 TestOverrideRouting→TestRoutingOverride (实测 L1826)、TestL2Ablation 4→9 方法; X8 task1 口径统一为"5→3 净删 2" (以实施 §8.2 为权威)。数值锚点 (0.999998/0.308/49.5%/−37.6%/2σ→0.4041) 复核无转抄漂移 |

**设计 review 结论**: 2026-11-10; 双轨 review (阶段 3 接口/算术对齐 + 阶段 4 学术核实) 均为 PASS with fixes。接口侧: 设计承重代码事实 (类/函数/字段/行号/签名/测试类名) 逐项核对属实; 新增字段恰 8 个、删除字段恰 5 个、断点窗口 62 次等算术复核通过; `_l3_routing_threshold_scale` 确认无读取点; 1 条 CRITICAL (清理清单漏 4 处调用点) 已补全, 按新清单执行后定向套件可全绿。学术侧: §8 八行锚点映射七行完全对齐、一行章节号勘误; 全部数字 (0.999998/0.308/49.5%/−37.6%/2σ→0.4041/硬路由不可达) 与调研文档对账一致; 新增引用 (Simonsohn 2020 NHB 4:1208-1214、BH 1995) 真实且主题匹配; trim=0.15 符合 Andrews (1993) 15% 截断惯例; 断点方法学归因准确。设计主体 (统一管道/指纹降级/断点下沉/A-B 整臂化) 无需推翻。可进入步骤 5 (实施文档)。
