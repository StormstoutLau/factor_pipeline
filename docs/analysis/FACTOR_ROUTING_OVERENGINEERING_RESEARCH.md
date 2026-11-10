# 因子静态/动态/混合路由是否过度工程化 —— 调研报告

> **文档类型**: 步骤 1 调研 + 步骤 2 review (spec 工作流, 不做代码改动)
> **版本**: v1.1
> **日期**: 2026-11-09
> **对象**: `FactorProcessingPipelineV2` 三路分类路由 (v3.3.7)
> **定位**: 回答五个问题 —— 过度工程化 / 基准不可比 / 结构突变可检性 / 收益增益 / 统一方法选择
> **方法**: 代码回源 + 本地真实数据实测 + 学术与社区外部锚点

---

## 0. 结论速览

| 问题 | 结论 | 关键证据强度 |
|------|------|--------------|
| Q1 三路路由是否过度工程化 | **是**，且分三层: 未接线 / 冗余 / 阈值无依据 | 代码事实 (强) + 实测 (强) |
| Q2 不同历史参数是否导致基准不可比 | **部分是**。窗口长度 (≥120 天) 不是主因; **采样频率、分类方法、管道选择**才是 | 实测 (强) |
| Q3 能否检测因子的结构性变化 | **不能**。路由路径内无任何断点检验; 唯一相关开关默认关闭且不参与路由; AR(1) 本身会被突变污染 | 代码事实 (强) + 模拟 (强) |
| Q4 分类处理能否提升因子投资收益 | **不能** (本样本)。12 个因子全判为 static/mixed, 而这两条管道秩等价 → 路由为 no-op; 改走 Dynamic 则 \|IC\| 平均 −37.6% (11/12 变差) | 实测 (中强, 样本有限) |
| Q5 若回退统一方法选什么 | **单一横截面秩管道**: ffill → MAD 缩尾 → 中性化 → rank→normal (CSRankNorm) | 实测 + 社区/学术锚点 (强) |

一句话总结: **本框架实际执行的是「VR/DF 硬路由 + 单管道」, 而围绕它构建的软权重、五步多维决策树、线性混合器从未进入生产路径; 两个仓库内分类器标签一致率仅 49.5%; Static 与 Mixed 两条管道在排序意义上完全等价; 而 Dynamic 管道的 AR 残差在本样本中把横截面信号削弱了约 38%。**

---

## 1. 调研范围与方法

### 1.1 三条证据线

| 证据线 | 内容 | 可核查性 |
|--------|------|----------|
| **A. 代码回源** | 三路路由的全部判定函数、阈值、调用点、默认值 | 本仓库文件 + 行号 |
| **B. 本地实测** | 101 个真实 A 股财务因子 + 5 个日频 / 5 个月频构造价量因子; 覆盖 AR(1) 敏感性、断点检验、三管道输出对比、IC 增益检验 | 数据路径与脚本全文见 §9 |
| **C. 外部锚点** | 学术文献 (计量/资产定价/组合预测) + 开源与商业社区文档 | 链接见 §8 |

### 1.2 实测数据与环境

| 项 | 值 |
|----|----|
| 财务因子 | `E:\Ashare_data\financial_factors` 下 101 个 `.pkl` 面板, 每文件 `(1472, 6508)`, 含 `trade_date` 列 |
| 日期范围 | 2020-01-02 → 2026-01-27 (1472 个交易日) |
| 价量数据 | `E:\Ashare_data\market_data\stock_close.pkl` `(1475, 5688)` / `stock_amount.pkl` 同日 |
| 股票池 | close 覆盖率 ≥95% → 3634 只; 财务因子列覆盖率 ≥1000 个有效日 → 最多 5754 列 |
| 运行环境 | Python 3.12.10 (`C:\Users\Peng\AppData\Local\Programs\Python\Python312`) |
| 未使用 | `factor_db.duckdb` 的 `factor_wide` (930 万行) 仅抽取用过; `factor_data` 长表因 5.7 GB 内存上限未全表扫描 |

> **口径声明**: 实测复刻的是**框架自身的定义** —— 每只股票 OLS 拟合 AR(1) 后取截面中位数, 并保留框架的两道过滤 (`min_obs_per_stock=12`、`min_cv_threshold=0.01`、`min_stocks=10`)。这一点很关键, 因为过滤本身会改变"哪些股票进入中位数"。

---

## 2. 现状事实: 三路路由到底做了什么

### 2.1 三层判定机制 + 一层执行

| 层 | 组件 | 位置 | 输入 | 输出 | 阈值 |
|----|------|------|------|------|------|
| L1 指纹分类 | `AdaptiveFactorClassifier` | [classifier.py](../../modules/factor_fingerprint/core/classifier.py#L124-L131) | `ar1_median` | `ClassificationResult` | `0.80` / `0.40` |
| L2 软路由 | `_get_pipeline_weights` | [pipelines_v2.py](../../pipelines_v2.py#L54-L97) | `ClassificationResult` | `{static,mixed,dynamic}` 权重 | 硬路由 `0.90` |
| L3 多维路由 | `_get_multi_dim_pipeline_weights` | [pipelines_v2.py](../../pipelines_v2.py#L104-L225) | 21 维指纹 | 权重 (五步决策树) | `1.5` / `5.0` / `1.0` / `0.3` / `0.1`, 偏移上限 `0.15`/`0.10` |
| 执行 | `StatisticalClassifier` (VR q=5 + 面板 DF) | [statistical_classifier/__init__.py](../../modules/statistical_classifier/__init__.py#L32-L82) | 因子面板 | 单个 `pipe_type` | `alpha=0.05` |

### 2.2 生产路径的真实执行链

`FactorProcessingPipelineV2.fit` 的关键两行:

```python
# pipelines_v2.py L1373
pipe_type = stat_clf.classify(factor_data[name])
# 只用这一个管道, fit 一次
factor_pipes[pipe_type] = self._create_pipeline(pipe_type, ...)
```

`transform` 明确是硬路由:

```python
# pipelines_v2.py L1438-L1450
# Step 7: Hard routing — 单管道变换, 无加权
pipe_type = pipe_keys[0]  # exactly one pipeline (hard routing)
pipe = factor_pipes[pipe_type]
```

而 L1/L2/L3 的产物 (`self.factor_classifications[name]`) 在 `fit` 中仅被记录:

```python
# pipelines_v2.py L1370
self.factor_classifications[name] = classification
# L1374 仅打印日志
logger.info(f"  {name} → {pipe_type} (StatisticalClassifier, was {classification.primary_type.value})")
```

> **代码事实 A1**: 全仓库 `*.py` 检索 `_get_pipeline_weights` / `_get_multi_dim_pipeline_weights` / `_apply_weighted_transform`, 命中位置只有 `pipelines_v2.py` 的定义处、`tests/` 与 `notebooks/demo_v3_1_0.py`。**没有任何生产调用点**。
>
> **代码事实 A2**: `enable_multi_dim_routing` 默认 `False`([pipelines_v2.py](../../pipelines_v2.py#L724)), 且该配置项在全仓库**没有任何读取点** —— 置 `True` 也不会改变任何行为。

### 2.3 软路由在默认参数下根本不可达

`_get_pipeline_weights` 的硬路由分支要求 `is_hard and primary_prob > 0.90`。但在默认 `soft_boundary=True`、`sigmoid_steepness=10.0` 下, 概率是 `ar1` 的 sigmoid 函数, **static/mixed 的 `primary_prob` 上界达不到 0.9**:

| ar1 | primary | primary_prob | is_hard | 权重 |
|-----|---------|--------------|---------|------|
| 0.000 | dynamic | 0.9820 | True | `{dynamic: 1.0}` |
| 0.100 | dynamic | 0.9526 | True | `{dynamic: 1.0}` |
| 0.180 | dynamic | 0.9002 | True | `{dynamic: 1.0}` (临界) |
| 0.200 | dynamic | 0.8808 | True | `{dynamic: 0.883, mixed: 0.117}` |
| 0.400 | dynamic | 0.5000 | False | `{dynamic: 0.509, mixed: 0.491}` |
| 0.600 | mixed | 0.7616 | True | `{mixed: 0.865, dynamic: 0.135}` |
| 0.800 | static | 0.5000 | False | `{static: 0.509, mixed: 0.491}` |
| 0.950 | static | 0.8176 | False | `{static: 0.821, mixed: 0.179}` |
| 1.000 | static | 0.8808 | True | `{static: 0.883, mixed: 0.117}` |

> **代码事实 A7**: 默认参数下, `primary_prob` 的上确界为: 静态 `sigmoid(10 × 0.2) = 0.8808` (在 ar1=1 处取得)、混合 `0.7616` (在 ar1=0.6 处取得); 动态概率随 ar1 单调递减, 在 ar1→−1 处趋近 1 (ar1=0 处为 0.9820, ar1=−0.0586 处即 ≈0.990)。因此:
> - **STATIC 与 MIXED 永远不会走硬路由分支** —— static 需要 `ar1 > 1.0197` 才能越过 0.90, 已超出 AR(1) 系数的合理取值; mixed 的概率峰值 0.7616 < 0.90。无论 ar1 多极端, 权重都会被拆成"主 + mixed"或"mixed + dynamic"两路;
> - **DYNAMIC 仅在 `ar1 < 0.1803` 时**才能硬路由 (ar1=0.180 处 p=0.9002, 恰好越过阈值);
> - 在混合区中心 `ar1 = 0.60`, 系统给出的权重是 `mixed 0.865 / dynamic 0.135`, 即"最像混合"的因子仍被掺入 13.5% 的动态管道。(复现注: ar1=0.6 时 p_static 与 p_dynamic 在精确数学下同为 0.1192, "次类型 = dynamic"来自 numpy 浮点在 1e-16 量级的不对称; 稳定排序在精确相等时会选 static。)

这条与 §2.4 的"Static/Mixed 等价"叠加后意味着: **软路由即使被接线, 对 static 因子也只是把一个等价管道与其自身按 88:12 混合, 输出近似不变; 对 mixed 因子则会掺入 AR 残差。** 复杂度只带来了噪声。

### 2.4 三条管道的实质差异

| 步骤 | Static | Mixed | Dynamic |
|------|--------|-------|---------|
| 缺失 | `ffill_ts` | `ffill_ts` | `ffill_ts` |
| 极值 | 逐日截面 **1%/99% 分位** | 逐日截面 **±3σ** | 无 |
| 中性化 | 行业(+市值) | 行业(+市值) | **双重中性化** (原值 + AR 残差) |
| 变换 | **rank → normal** (`'rank'`) | **rank → normal** (`'rank'`) | **AR 解耦残差** |
| 标准化 | `auto`→`z_score` | `z_score` | `z_score` |
| 可选 | GARCH (默认关) | — | 禁止 GARCH |

对应代码: [StaticFactorPipeline](../../pipelines_v2.py#L860-L938)、[MixedFactorPipeline](../../pipelines_v2.py#L1054-L1175)、[DynamicFactorPipeline](../../pipelines_v2.py#L941-L1051); 默认变换方法见 [pipelines_v2.py](../../pipelines_v2.py#L693-L696)。

> **代码事实 A3**: `static_transformation_method` 与 `mixed_transformation_method` 默认都是 `'rank'`, `target_distribution` 都是 `'normal'`。因此 **Static 与 Mixed 的唯一实质差异是缩尾规则 (1%/99% 分位 vs ±3σ)**。
>
> **代码事实 A4**: `ProcessingAdapter` 在构造期把 `'auto'` 一律解析为无状态 `rank`([adapters.py](../../adapters.py#L360-L377)), 因此"自适应变换选型"也已被移除。

### 2.5 结构性变化相关的三条潜在通道, 全部关闭

| 通道 | 默认 | 作用对象 | 是否影响路由 |
|------|------|----------|--------------|
| `FingerprintConfig.enable_regime_switching` | `False` → `regime_transition_prob = NaN` | 因子值 (Markov 两状态) | 否 (仅 L3 第 4b 步 ±0.10, 而 L3 未接线) |
| `PipelineV2Config.enable_cusum_drift_monitor` | `False` | 因子值矩阵的**横截面均值/标准差** | 否 (事后告警, 见 [L1547-L1645](../../pipelines_v2.py#L1547-L1645)) |
| `_get_multi_dim_pipeline_weights` 第 4b 步 | 需 `regime_transition_prob > 0.1` | — | 否 (未接线 + 输入恒为 NaN) |

> **代码事实 A5**: [fingerprint.py](../../modules/factor_fingerprint/core/fingerprint.py#L184-L189) 在开关关闭时把三个 regime 字段直接置 `np.nan`; L3 的 `regime_valid` 判断因此恒为 `False`, 4b 步永不执行。

---

## 3. Q1: 是否过度工程化

### 3.1 判定标准

工程复杂度的合理性需要一个可证伪的判据。本调研采用四条:

1. **可执行性**: 该复杂度是否真的参与决策 (排除死代码);
2. **信息增益**: 引入的每个分支是否携带独立于其它分支的信息 (排除冗余);
3. **参数可证据性**: 每个阈值是否来自校准/回测/文献, 还是手设;
4. **可维护性**: 组件间是否自洽 (是否存在会导致崩溃或无法解释的组合)。

### 3.2 逐条核查

| # | 组件 | 可执行性 | 信息增益 | 参数来源 | 自洽性 |
|---|------|----------|----------|----------|--------|
| 1 | L1 指纹 AR(1) 分类 | 仅记录 | 与执行层独立 (VR/DF) | `0.80/0.40` 手设, 无校准 | 与 L4 不一致率 50.5% |
| 2 | L2 软路由权重 | **未接线** | 0 (无调用) | `0.90` 手设 | 硬路由分支对 static/mixed 不可达; `UNKNOWN` 会产出 `{'unknown': 0.0}`, 下游 `_create_pipeline` 抛 `ValueError` |
| 3 | L3 五步多维树 | **未接线** | 0 | 5 个阈值 + 2 个偏移上限全手设 | 依赖 L2; 4b 输入恒 NaN |
| 4 | `_apply_weighted_transform` | **未接线** | 0 | 权重下限 `0.001` 手设 | 混合异质统计量, 见 §4.6 |
| 5 | L4 VR/DF 分类 | **唯一执行** | 有 | `alpha=0.05`, `q=5` 沿用文献方法 | 与 L1 冲突时静默以 L4 为准 |
| 6 | regime 指标 | 关闭 | 0 | `0.1` 手设 | 开关关闭后全 NaN |
| 7 | CUSUM 漂移 | 关闭 | 0 (仅告警) | `k=0.5`, `h=5.5` | 不接入路由 |

### 3.3 结论

**过度工程化成立, 且是三重叠加:**

- **(a) 未接线复杂度**: L2 + L3 + 混合器合计约 220 行 ([pipelines_v2.py](../../pipelines_v2.py#L54-L271))、9 个手设阈值 (去重计数), 生产路径零调用, 但有 31 个相关单测在维护它。测试绿灯给出的是"这段代码没坏", 不是"这段代码有用"。
- **(b) 冗余复杂度**: Static 与 Mixed 在数学上只差缩尾规则; 而 rank→normal 对任何**单调**裁剪不敏感, 故两者输出几乎相同 (§4.3 实测 Spearman 0.999998, 相对 L2 距离 0.032)。**三条管道实际只有两条不同的信号定义**。
- **(c) 决策权错配**: 真正决定走哪条管道的是 L4 (`StatisticalClassifier`), 而 L1/L2/L3 是为另一个分类器的输出设计的。两套分类器在同一批因子上的标签一致率只有 **49.5%**, 见 §4.4。

> 一个必要的公平说明: 三条管道在**设计意图**上是有区别的 (静态因子重截面排序、动态因子重时序变化), 这不是无意义的重复。问题不在"想法", 而在"实现已经退化 + 决策链断开 + 参数无证据"。

---

## 4. Q2: 不同历史参数是否导致基准不可比较

### 4.1 四个可能的参数轴

| 轴 | 变化 | 是否影响标签 | 是否影响输出数值 |
|----|------|--------------|------------------|
| P1 窗口长度 | 60 / 120 / 250 / 500 / 750 / 1000 / all | 见 §4.2 | 见 §4.2 |
| P2 采样频率 | 日频 / 月频 | **是** (§4.5) | 是 |
| P3 分类方法 | 指纹 AR(1) / VR+DF | **是** (§4.4) | 是 |
| P4 管道选择 | static / mixed / dynamic | — | **是** (§4.3) |

### 4.2 P1 窗口长度: 标签其实很稳, 但有"悬崖"

101 个真实财务因子, 按框架自身定义计算 AR(1) 中位数:

| 窗口 | 可计算因子数 | AR(1) 中位数 | static 占比 | mixed | dynamic |
|------|--------------|--------------|-------------|-------|---------|
| 60 | **1 / 101** | 0.9213 | 100% | 0 | 0 |
| 120 | 101 | 0.9444 | 100% | 0 | 0 |
| 250 | 101 | 0.9887 | 100% | 0 | 0 |
| 500 | 101 | 0.9919 | 100% | 0 | 0 |
| 750 | 101 | 0.9933 | 100% | 0 | 0 |
| 1000 | 101 | 0.9945 | 100% | 0 | 0 |
| all | 101 | 0.9951 | 100% | 0 | 0 |

- **窗口 ≥120 天时, 101/101 因子在每个窗口下都只有一个类型, 跨窗口零翻转**。
- 但 AR(1) 数值本身并不稳定: 跨窗口极差中位数 **0.0506** (p90 = 0.0529), 跨窗口 Spearman 秩相关均值 **0.681**, 最低 **0.256**。即"排序不稳, 但都落在 static 区间"。
- **60 天窗口是悬崖**: 100/101 因子的 AR(1) 无法计算。原因是框架的 `min_cv_threshold=0.01` 过滤把"60 个交易日内近似常数"的季度因子全部剔除, 有效股票数 <10 → 返回 NaN → `classify` 落到 `UNKNOWN`, `primary_prob = 0.0`([classifier.py](../../modules/factor_fingerprint/core/classifier.py#L79-L84))。

> **结论 P1**: 对本样本这类"季度更新 + 日频前向填充"的财务因子, **不存在"换个窗口就换类型"的问题** —— 它们在任何 ≥120 天的窗口下都是 static。真正的风险是**短窗口使分类整体失效**(UNKNOWN / 概率 0), 而不是分类漂移。

### 4.3 P4 管道选择: Static≈Mixed 完全等价; Dynamic 是另一套信号

直接实例化三条生产管道, 在同一批真实因子上 fit/transform (Dynamic 的 neutralizer 保持启用, 因为 AR 解耦就发生在该步骤内), 逐日计算输出的截面 Spearman 与相对 L2 距离:

| 因子类 | n | Spearman(static~mixed) | relL2(static~mixed) | Spearman(static~dynamic) | relL2(static~dynamic) |
|--------|---|------------------------|---------------------|--------------------------|-----------------------|
| 财务因子 (roe / debt_to_assets / netprofit_yoy / assets_turn / bps / current_ratio) | 6 | 0.999996–0.999999 | 0.0266–0.0331 | −0.112–0.573 | 1.128–1.491 |
| 价量因子 (mom_60 / rev_5 / lowvol_20 / abnvol_120) | 4 | 0.999996–0.999998 | 0.0314–0.0427 | 0.155–0.503 | 0.989–1.300 |

- **Static 与 Mixed 的输出几乎重合**: 秩相关中位 0.999998, 相对 L2 距离中位 0.032 (仅来自缩尾造成的尾部 tie 间距差异)。对排序型下游, 这两条管道**在功能上是一条**。
- **Dynamic 则是一套完全不同的信号**: 秩相关中位 **0.308** (最低 −0.112), 相对 L2 距离中位 **1.251** (0.99–1.49)。即"换到 Dynamic 管道"不是换量纲, 而是**换信号**。

> 注: 本表因子名单与 §6.2 不同 (本表财务因子含 `bps`、无 `grossprofit_margin`), 因为两次实测选取了不同子样本; 结论不依赖名单一致。

> **这解释了"基准不可比较"的真实机制**:
> - Static↔Mixed 切换: 排序不变, 只有尾部间距微变 → 对 rank IC / 分位组合**无影响**; 对数值加权组合有 ~3% 的尺度差异。
> - Static↔Dynamic 切换: 排序与尺度**同时改变** → 同一因子、同一数据、同一窗口, 只要分类标签变了, 得到的因子值与历史基准**不可比较**。
>
> **代码事实 A8**: `DynamicFactorPipeline` 的 `module_enabled={'neutralizer': False}` 会**同时关闭 AR 解耦**(解耦器在 neutralizer 分支内创建, 见 [pipelines_v2.py](../../pipelines_v2.py#L998-L1012))。也就是说, 消融开关把"中性化"与"AR 解耦"绑成了一个开关 —— 这是本轮实测第一次得到"三管道排序几乎相同"的原因 (关闭 neutralizer 后 Dynamic 退化为 imputer + z-score)。该现象本身说明**组件的可分离性不足**。

### 4.4 P3 分类方法: 两套分类器一致率 49.5%

同一批 101 因子, 同一窗口 (`all`):

| | 指纹 AR(1) 分类 | VR/DF 分类 |
|---|---|---|
| static | 100% | 49.5% |
| mixed | 0% | 50.5% |
| dynamic | 0% | 0% |
| **一致率** | — | **49.5%** |

在 12 因子 IC 子样本上, 指纹给出 10 static / 2 mixed、无 dynamic (§6.2); 这批因子的 VR/DF 标签未单独留存, 因此本节的一致率结论仅基于 101 因子全样本。

> **结论 P3**: 生产路径用的是 VR/DF, 记录与展示用的是指纹 AR(1)。两者对同一因子给出不同标签的概率约 50%。**这本身就是"基准不可比"——日志/报告里的类型与真正执行的管道不是一回事。**

### 4.5 P2 采样频率: 同一个因子在日频是 static, 在月频是 dynamic

使用同一批价量数据, 只改变采样频率 (日频 vs 月末收盘重采样), 其余口径完全不变:

| 因子 | 频率 | 观测数 | AR(1) 中位数 | 分类 |
|------|------|--------|--------------|------|
| mom_60 | 日 | 1475 | 0.9776 | static |
| rev_5 | 日 | 1475 | **0.8042** | **static(距阈值 0.0042)** |
| lowvol_20 | 日 | 1475 | 0.9823 | static |
| abnvol_120 | 日 | 1475 | **0.7796** | **mixed(距阈值 0.0204)** |
| mom_250 | 日 | 1475 | 0.9906 | static |
| mom_1m | 月 | 73 | **−0.0586** | **dynamic** |
| rev_1m | 月 | 73 | **−0.0586** | **dynamic** |
| mom_3m | 月 | 73 | 0.5881 | mixed |
| mom_12m | 月 | 73 | 0.8340 | static |
| vol_6m | 月 | 73 | 0.8400 | static |

> 注: `rev_1m` 与 `mom_1m` 互为相反数, AR(1) 相同, 因此月频实际是 4 个独立因子。
>
> **结论 P2**: 经济含义完全相同的"1 个月反转", 在日频面板上被判为 **static**(0.804, 且只比阈值高 0.004), 在月频面板上被判为 **dynamic**(−0.059)。**分类标签是采样频率的函数, 不是因子的内在属性。** 这条比窗口长度重要得多, 也是"基准不可比"的最强来源。
>
> 机制解释: 日频因子值存在重叠窗口自相关 + 个股层面的持续性, 使 AR(1) 趋近 1; 月频去掉了这层机械平滑后, 才暴露出真实的均值回复。**框架从未规定"用哪个频率提取指纹", 也没有把频率写入指纹的元数据。**

### 4.6 P2+P4 组合: 混量纲加权 (仅当软路由被启用时)

`_apply_weighted_transform` 对多条管道输出做线性加权:

```python
# pipelines_v2.py L228-L271
result = result + transformed * weight
```

- Static/Mixed 输出是 **rank→normal 分位分数**; Dynamic 输出是 **AR 残差 z-score**。
- 两者虽然都做了近似标准化, 但**统计对象不同**(横截面序 vs 时序残差)。线性混合后的量既不是分位分数, 也不是残差, 其 IC 无法与任一单管道基准对齐。
- 该函数当前未接线, 因此这是**潜在**问题; 一旦按设计意图启用软路由, 基准不可比将从"管道切换"升级为"每一次输出都不可比"。

---

## 5. Q3: 能否检测因子的结构性变化

### 5.1 框架内现状: 无检测, 且相关通道全部关闭

| 能力 | 是否存在 | 默认 | 是否影响路由 |
|------|----------|------|--------------|
| Chow / sup-F / Bai-Perron 断点检验 | **无** | — | — |
| CUSUM 在线漂移 | 有 (`CUSUMDriftMonitor`) | 关闭 | 否, 只写 `drift_alerts` |
| Markov 体制转换 | 有 (`regime_transition_prob`) | 关闭 (NaN) | 否 (L3 未接线) |
| 迁移监测 | 有 (`FactorFingerprintMonitor`) | 始终实例化 | 否, 仅记录/告警, 迁移检查需显式调用 `check_type_migration` |

> **代码事实 A6**: 路由链上没有任何统计检验能回答"因子结构是否变了"。唯一的"变化信号"是 `ar1_median` 本身 —— 它既是分类依据, 又被突变污染 (见 §5.3)。

### 5.2 学术锚点: 检测方法早已成熟, 且知道 AR(1) 不适合

| 主题 | 锚点 | 与本框架的关系 |
|------|------|----------------|
| 单位根检验功效低 | Dickey & Fuller (1979); Elliott, Rothenberg & Stock (1996) DF-GLS | 框架用 DF τ 做 stationarity 判定, 但未讨论低功效 |
| 方差比检验 | Lo & MacKinlay (1988) | `StatisticalClassifier` 直接采用 (VR q=5) |
| **突变下的单位根偏误** | **Perron (1989)** | 含一次性突变的平稳序列会使标准单位根检验无法拒绝单位根假设 (等价于 AR(1) 估计趋近 1) → 分类被污染 |
| 未知断点 sup-F | Andrews (1993); Chow (1960) | 框架无 |
| 多断点估计与检验 | Bai & Perron (1998, 2003) | 框架无 |
| 方差突变 CUSUM | Inclán & Tiao (1994) | 框架的 CUSUM 只做均值/标准差在线监测 |
| 体制转换 | Hamilton (1989) | 框架的 Markov 指标默认关闭 |
| 因子模型的结构突变 | Koo, Wong & Zhong (2023), "Disentangling Structural Breaks in Factor Models for Macroeconomic Data" (arXiv:2303.00178) | 说明因子层面的突变是可建模、可检验的对象 |
| 伪因子 | Onatski & Wang (2021), *Spurious Factor Analysis*, Econometrica 89(2) | 平滑/近单位根序列易产出伪因子, 与"高 AR(1) 即静态"的直觉冲突 |
| 因子动物园与多重检验 | Harvey, Liu & Zhu (2016), RFS 29(1); Feng, Giglio & Xiu (2020), JF 75(3); Hou, Xue & Zhang (2020), RFS 33(5) | 阈值 `0.80/0.40` 属未校正的手设切分, 与多重检验框架不兼容 |

### 5.3 模拟证明: 一个均值突变就足以改变分类

设计: 200 只股票, T=750, 真实 AR(1) `phi=0.20`(一个货真价实的 dynamic 因子), 在第 375 期让**一半横截面**发生永久性水平位移 `shift` 个标准差; 按框架口径计算全样本 AR(1) 中位数。

| 真实 phi | 位移(σ) | 全样本 AR(1) | 分类 | 断点前子样本 | 断点后子样本 |
|----------|---------|--------------|------|--------------|--------------|
| 0.20 | 0.0 | 0.1959 | dynamic | 0.1954 | 0.1965 |
| 0.20 | 1.0 | 0.2711 | dynamic | 0.1915 | 0.1955 |
| 0.20 | **2.0** | **0.4041** | **mixed** | 0.2030 | 0.2004 |
| 0.20 | **3.0** | **0.4815** | **mixed** | 0.2027 | 0.2009 |
| 0.50 | 0.0 | 0.4996 | mixed | 0.4961 | 0.4995 |
| 0.50 | 1.0 | 0.5337 | mixed | 0.4882 | 0.5023 |
| 0.50 | 2.0 | 0.6205 | mixed | 0.4947 | 0.4971 |
| 0.50 | 3.0 | 0.6630 | mixed | 0.4884 | 0.4916 |

> **结论**: 2σ 的横截面均值突变即可把一个 dynamic 因子推过 `0.40` 阈值, 变成 mixed; 3σ 时逼近 static。**断点前后各自的 AR(1) 都还是 0.20, 说明断点本身可被"分段估计"识别 —— 但框架只估计全样本, 于是把突变吸收进了类型标签。** 这正是 Perron (1989) 描述的方向。

### 5.4 实测: 本样本内没有显著断点, 但也没有检测能力

对每个因子, 取 250 天滚动 AR(1) 中位数路径 (stride 20, 62 个点):

| 指标 | 结果 |
|------|------|
| sup-F (Andrews) 未知断点检验, 自助零分布 (B=400) | p<0.05: **0 / 101**; p<0.10: **0 / 101** |
| CUSUM (h=1.0σ) 命中率 | **4.95%** (≈ 名义 5% 误报率) |
| AR(1) 路径极差 (max−min) 中位数 | **0.0169**; p90 = 0.0230 |
| 路径中跨越 0.80 或 0.40 阈值的因子 | **0 / 101** |

> **读法**: 这些是"慢因子", AR(1) 路径本来就平坦, 所以"没检测到断点"是**正确的**; CUSUM 命中率 4.95% 恰好等于误报率, 说明没有系统性漂移。但这不能推出"框架能检测断点" —— 它只是说明**在这批因子上没有可检测的东西**。
>
> 对快因子 (价量/情绪), 一旦发生风格切换, AR(1) 会跳变, 而框架既无检验、也无分段估计, 只会把新状态直接写进新标签, 并切换管道 —— 历史基准随之中断。

---

## 6. Q4: 分类处理能否提升因子投资收益

### 6.1 先看理论: 排序型下游对单调变换不变

横截面分位组合、rank IC、Spearman 相关只依赖**截面序**。任何严格单调变换 (缩尾、Box-Cox、z-score、rank) 都不改变序, 因此:

- **Static 与 Mixed 的差异 (1%/99% vs 3σ) 在排序意义上几乎不存在**;
- **会改变截面序的只有两类操作**: 行业/市值中性化 (三条管道都有, 相同), 与 **AR 残差化** (每只股票的 phi/截距不同, 等价于逐股票仿射变换, 因而改变秩; 只有 Dynamic 有)。

这解释了 §4.3 的实测: Static 与 Mixed 的秩相关 0.999998 (排序不变), 而 Static 与 Dynamic 仅为 0.308 (排序被改变)。

### 6.2 实测协议

| 项 | 设置 |
|----|------|
| 因子 | 12 个: 6 财务 (`roe` / `debt_to_assets` / `grossprofit_margin` / `current_ratio` / `assets_turn` / `netprofit_yoy`) + 6 价量 (`mom_60` / `rev_5` / `lowvol_20` / `abnvol_120` / `illiq_20` / `mom_250`) |
| 股票池 | 3634 只 (close 覆盖率 ≥95%); 每因子取前 2000 列做管道拟合 |
| 拟合窗 | 前 750 个交易日 (生产管道只在该窗口 `fit`) |
| 评估 | 其余交易日, 每 20 日一个调仓点, 共 36 个 |
| 收益 | 20 日前向收益 |
| 对照 | `StaticFactorPipeline` vs `DynamicFactorPipeline` (仓库内的真实生产类, 不做任何简化复刻) |
| 分类 | 指纹 AR(1) 在拟合窗内计算: 10 static / 2 mixed, 无 dynamic (`fp_classify12.py`) |

> 采用真实管道类而非参数化变体, 是为了避免"自己实现一遍 AR 残差"带来的口径偏差。绝对 IC 水平随股票池与调仓点变化, 本节只做**相对比较**。

### 6.3 结果

| 指标 | Static | Dynamic |
|------|--------|---------|
| 平均 \|IC\| | **0.1156** | **0.0721** |
| Static 更优的因子数 | — | **11 / 12** |
| 逐因子 \|IC\| 中位比值 (D / S) | — | **0.567** (即 −43%) |
| 输出截面秩相关 (S vs D) 中位 | — | **0.412** |

> 注: 本表 0.412 与 §4.3 的 0.308 来自不同的股票池子集 (2000 列 vs 400 列 / 全池), 量级一致。

### 6.4 结论: 路由决策对本样本是 no-op, 改判则是负收益

1. **12 个因子全部落在 static/mixed 类** → 路由实际只在 Static 与 Mixed 之间选。而这两条管道输出的秩相关为 0.999998 (§4.3), **对排序型下游完全等价**。因此"分类 → 选管道"在这些因子上的最好结果是 **no-op**。
2. **若这些因子被改判为 dynamic**(例如改用月频指纹, §4.5), 下游拿到的就是 Dynamic 的输出: 它与 Static 的秩相关仅 0.412, 平均 \|IC\| 从 0.1156 降到 0.0721 (**−37.6%**), 11/12 因子变差, 逐因子中位比值 0.567。
3. 因此, **"分类处理提升收益"在两个方向都不成立**: 选 static/mixed 等于没选, 选 dynamic 则明显变差。

### 6.5 为什么 AR 残差会削弱横截面信号

对慢变因子, AR(1) 残差近似 `r_t ≈ (1−φ)·y_t + (y_t − y_{t−1})`。`(1−φ)` 很小 (φ≈0.99), 残差主要由**一阶差分噪声**主导, 而截面排序真正需要的是**水平差异**。于是"去掉时序可预测性"与"保留截面区分度"在这里是冲突目标。Dynamic 管道的设计前提是"因子的价值在时序变化", 但对**用于截面选股**的因子, 这个前提不成立。

### 6.6 外部锚点: 分类/择时类增益在文献中普遍弱且不稳

| 主题 | 锚点 | 结论 |
|------|------|------|
| 因子择时 | Asness, Chandra, Ilmanen & Israel (2017), *Contrarian Factor Timing is Deceptively Difficult*, JPM 43(5) | 因子估值择时"看似可行、实则极难", 静态暴露通常优于择时 |
| 因子动量 (在因子**收益**层) | Ehsani & Linnainmaa (2022), *Factor Momentum and the Momentum Factor*, JF 77(3) | 自相关存在于因子**收益**序列, 不是因子**取值**序列; 可利用, 但作用位置在组合层 |
| 组合预测 | Bates & Granger (1969); Timmermann (2006); Smith & Wallis (2009); Claeskens et al. (2016) | "预测组合谜题": 简单/等权组合常优于估计权重组合, 因权重估计误差 |
| 模型/管道选择 | Thornton et al. (2013) Auto-WEKA (CASH); Feurer et al. (2015) Auto-sklearn | 管道选择是 CASH 问题, 收益依赖嵌套验证与集成; 无免费午餐结论 (AutoML 讲义, §8.3) 提示平均最优管道未必优于强基线 |
| 过拟合与选择偏差 | Bailey & López de Prado (2014) Deflated Sharpe; Bailey et al. (2017) PBO | 每次"按历史表现选管道"都在消耗显著性预算 |
| 研究自由度 | Gelman & Loken (2014) forking paths; Simmons et al. (2011) researcher degrees of freedom | 即使只跑一次分析, 未记录的分支选择也会制造假阳性 |
| 因子显著性门槛 | Harvey, Liu & Zhu (2016): t > 3.0 | 新增复杂度的收益必须跨过更高门槛 |

> **判断**: 把"分类 → 换管道"看作一种**按因子属性进行的择时/选择**, 文献给出的先验是**负面的**: 选择误差大、增益小、需要严格 OOS。本样本的实测与这个先验一致。

---

## 7. Q5: 若回退到统一方法, 选什么

### 7.1 推荐 U1: 单一横截面秩管道

```
原始因子面板 (T×N)
  → 1. 因果缺失处理: 按股票 ffill(仅用 t−1 及之前)
  → 2. 稳健极值: 逐日横截面 MAD 缩尾 (3×MAD; 或 1%/99% 分位)
  → 3. 中性化: 行业去均值(+ 市值回归残差)   ← U1 内唯一会改变序的步骤, 只做一次
  → 4. 变换: 逐日横截面 rank → normal (CSRankNorm)
  → 5. (可选) 标准化: 市值加权 z-score
```

即 **把现有 Static 管道作为唯一管道**, 把 Mixed 的 3σ 缩尾合并为同一条 MAD/分位规则。

### 7.2 为什么不是别的统一方案

| 候选 | 否决理由 |
|------|----------|
| 统一时序 z-score (整段标准化) | 非平稳: 用全样本均值/方差等价于用未来信息; 且丢失横截面可比性 |
| 统一 AR 残差化 | 实测 Dynamic 平均 \|IC\| 0.0721 vs Static 0.1156 (逐因子中位比值 0.567); 对截面选股是反向操作 |
| 统一 3σ 缩尾 + 原始值 (不 rank) | 厚尾因子仍会主导权重; 分位组合与权重口径不一致 |
| 保留三管道但默认 static | 只是把问题藏起来: 分类仍在跑、日志仍会给出不一致标签 |

### 7.3 外部锚点: 统一预处理是行业与学术的默认做法

| 来源 | 做法 | 是否按因子类型路由 |
|------|------|--------------------|
| Microsoft **Qlib** | 提供 `CSRankNorm`(截面秩→正态)、`CSZScoreNorm`、`RobustZScoreNorm`, Alpha158 用统一处理器链 | **否** |
| **WorldQuant** 101 Formulaic Alphas (Kakushadze 2016, arXiv:1601.00991) | 公式内统一使用 `rank(x)` 截面秩算子 | **否** |
| **Alphalens** (Quantopian) | 因子直接进入 `quantiles=5` 分位分桶, 可选 `filter_zscore` | **否** |
| **Ricequant** 因子检验 API | `Winzorization(method='mad'/'std'/'percentile')` + 标准化, 参数化而非类型化 | **否** |
| **BigQuant** | 典型链: 去极值 → 横截面标准化 → 中性化 → score | **否** |
| **DolphinDB** 因子评价框架 | `preprocess` 对全部因子统一做去极值/标准化/中性化 | **否** |
| **MSCI Barra** Risk Model Handbook | Descriptor 统一标准化 (对估计域做 z-score), 再做行业/风格处理 | **否** |
| Gu, Kelly & Xiu (2020), RFS 33(5) | 对全部特征采用统一的标准化/预处理流程, 未见按因子类型分流 | **否** |

> **检索结论**: 在主流开源/商业因子处理栈中, **没有找到"按因子时序类型分流到不同预处理管道"的公开实现**。Qlib/Alphalens/WorldQuant/Ricequant/BigQuant/DolphinDB/Barra 全部是**单一处理链 + 可配置参数**。这不是"别人没想到", 而是"排序型下游不需要"。

### 7.4 时序信息应该放在哪

不是"丢弃", 而是**移位**:

| 需求 | 正确位置 | 理由 |
|------|----------|------|
| 去自相关 / 提取变化 | **信号合成层**(因子→打分), 或组合层 | 那里才有时序目标函数; 预处理层不应改变截面序 |
| 因子择时 / 风格轮动 | 组合层 (权重时序) | Ehsani-Linnainmaa 的因子动量作用在**因子收益**上 |
| 结构突变监测 | **监控层**, 只告警 | 不应自动切换管道 (见 §5) |
| 频率选择 | **元数据**, 写进指纹与规格日志 | 见 §4.5: 频率决定标签, 必须显式记录 |

### 7.5 迁移路径 (最小改动, 供后续设计步骤参考)

| 步 | 内容 | 风险 |
|----|------|------|
| M1 | 统一缩尾规则 (Static 与 Mixed 合并为 MAD / 分位) | 数值输出变化, 需重算历史基准 |
| M2 | 默认只用 Static 管道; `Dynamic` 仅在显式 A/B 实验开启 | 行为变化, 需版本化 |
| M3 | 软路由 / 五步树 / 混合器标记废弃 (无生产调用) | 需同步删除对应单测或改为"契约存在性"测试 |
| M4 | 指纹降级为**诊断**: 只进入 monitor/health 报告, 不参与路由 | 报告口径变化 |
| M5 | 管道选择写入 `SpecificationLogger`(v3.1.0 E2 已有, 默认关) | 让"用了哪条管道"成为可审计元数据 |
| M6 | 断点/漂移检测移到监控层 (sup-F / CUSUM on rolling AR1 或 IC), 只告警 | 新增依赖 (statsmodels / 自实现) |

> 注: M5 直接复用了仓库里已有的 p-hacking 防御设施 ([pipelines_v2.py](../../pipelines_v2.py#L743-L748)), 这是"用已有能力替代新复杂度"的典型例子。

---

## 8. 外部信息锚点总表

### 8.1 计量与统计

| 文献 | 用途 | 核查 |
|------|------|------|
| Dickey & Fuller (1979), JASA 74(366):427-431 | DF τ 检验 (框架已用) | 代码注释已引 |
| Elliott, Rothenberg & Stock (1996), Econometrica 64(4):813-836 | DF-GLS: 常规 DF 功效低 | [BC 讲义](http://fmwww.bc.edu/EC-C/S2000/EC771B/UnitRootTests.pdf) |
| Lo & MacKinlay (1988), RFS 1(1):41-66 | 方差比检验 (框架已用 q=5) | [NBER w2168](https://www.nber.org/system/files/working_papers/w2168/w2168.pdf) |
| Perron (1989), Econometrica 57(6):1361-1401 | 突变下单位根检验的偏误 | [原文 PDF](http://www.ssc.wisc.edu/~bhansen/718/Perron1989.pdf) |
| Chow (1960), Econometrica 28(3):591-605 | 已知断点检验 | 标准文献 |
| Andrews (1993), Econometrica 61(4):821-856 | 未知断点 sup-F | 标准文献 |
| Bai & Perron (1998), Econometrica 66(1):47-78 | 多断点估计与检验 | [DOI 10.2307/2998540](https://doi.org/10.2307/2998540) |
| Bai & Perron (2003), J. Applied Econometrics 18:1-22 | 多断点计算 | [PDF](http://www.columbia.edu/~jb3064/papers/2003_Computation_and_analysis_of_multiple_structural_changes.pdf) |
| Inclán & Tiao (1994), JASA 89(428):913-923 | 方差突变 CUSUM | 标准文献 |
| Hamilton (1989), Econometrica 57(2):357-384 | Markov 体制转换 | 标准文献 |
| Newey & West (1987), Econometrica 55(3):703-708 | HAC 标准误 | 标准文献 |
| Onatski & Wang (2021), Econometrica 89(2):591-614 | 伪因子 / 平滑序列 | [RePEc](https://ideas.repec.org/a/wly/emetrp/v89y2021i2p591-614.html) |

### 8.2 资产定价与因子研究

| 文献 | 用途 | 核查 |
|------|------|------|
| Harvey, Liu & Zhu (2016), RFS 29(1):5-68 | 因子多重检验, t>3.0 | [Oxford Academic](https://academic.oup.com/rfs/article/29/1/5/1843824) |
| Feng, Giglio & Xiu (2020), JF 75(3):1327-1370 | Taming the factor zoo | 标准文献 |
| Hou, Xue & Zhang (2020), RFS 33(5):2019-2133 | Replicating Anomalies: 异象可复制性 | 标准文献 |
| Novy-Marx & Velikov (2016), RFS 29(1):104-147 | 异象交易成本与净收益 | 标准文献 |
| Ehsani & Linnainmaa (2022), JF 77(3) | 因子动量: 自相关在因子**收益**上 | [NBER w25551](https://www.nber.org/system/files/working_papers/w25551/w25551.pdf) |
| Asness, Chandra, Ilmanen & Israel (2017), JPM 43(5) | 因子择时极难 | [JPM PDF](https://www.pm-research.com/content/iijpormgmt%3A%3A%3A43%3A%3A%3A5%3A%3A%3A72.full.pdf) |
| Gu, Kelly & Xiu (2020), RFS 33(5):2223-2273 | 统一截面标准化 + ML 基准 | [PDF](https://dachxiu.chicagobooth.edu/download/ML.pdf) |
| Fama & MacBeth (1973), JPE 81(3) | 截面排序/回归的标准做法 | 标准文献 |

### 8.3 组合预测、过拟合与研究自由度

| 文献 | 用途 | 核查 |
|------|------|------|
| Bates & Granger (1969), Operational Research Quarterly 20(4) | 组合预测起源 | 标准文献 |
| Timmermann (2006), Handbook of Economic Forecasting (Vol. 1, Ch. 4) | 组合预测综述 | 标准文献 |
| Smith & Wallis (2009), Oxford Bull. Econ. Stat. 71(3) | 预测组合谜题 | [PDF](https://www.urmh.edu.mx/a-simple-explanation-of-the-forecast-combination-puzzle_Yjo0ODoyNA.pdf) |
| Claeskens, Magnus, Vasnev & Wang (2016), Int. J. Forecasting 32(3):754-762 | 谜题的理论解释 (随机权重有偏) | [PDF](https://repub.eur.nl/pub/77116/2014-127.pdf) |
| Bailey & López de Prado (2014), JPM 40(5) | Deflated Sharpe Ratio | [SSRN 2460551](https://doi.org/10.2139/ssrn.2460551) |
| Bailey et al. (2017), J. Computational Finance | Probability of Backtest Overfitting | 标准文献 |
| Gelman & Loken (2014), American Scientist 102(6) | The Statistical Crisis in Science (forking paths 概念见其 2013 同名工作论文) | [原文](https://www.americanscientist.org/article/the-statistical-crisis-in-science) |
| Simmons, Nelson & Simonsohn (2011), Psychological Science 22(11):1359-1366 | 研究者自由度 (specification curve 见 Simonsohn et al. 2020, Nature Human Behaviour) | 标准文献 |
| Thornton et al. (2013), KDD | Auto-WEKA / CASH 问题 | [arXiv 1208.3719](https://arxiv.org/abs/1208.3719); AutoML 讲义 (无免费午餐): [PDF](https://web.stanford.edu/~udell/orie4741/lectures/automl.pdf) |
| Feurer et al. (2015), NeurIPS | Auto-sklearn / 管道选择需嵌套验证 | [NeurIPS PDF](https://proceedings.neurips.cc/paper_files/paper/2015/file/11d0e6287202fced83f79975ec59a3a6-Paper.pdf) |

### 8.4 社区与文档

| 来源 | 相关内容 |
|------|----------|
| [Qlib Data Layer 文档](https://qlib.readthedocs.io/en/stable/component/data.html) | `CSRankNorm` / `CSZScoreNorm` / `RobustZScoreNorm` 为统一处理器 |
| [Alphalens 文档](https://quantopian.github.io/alphalens/alphalens.html) | 因子直接按 `quantiles` 分桶, 无类型路由 |
| [Kakushadze (2016) 101 Formulaic Alphas](https://arxiv.org/pdf/1601.00991.pdf) | 全部公式使用 `rank()` 截面算子 |
| [Ricequant 因子检验](https://www.ricequant.com/doc/rqfactor/api/factor-test) | `Winzorization(method='mad'/'3σ'/'2.5%')` |
| [BigQuant 使用手册](https://fund.bigquant.com/wiki/doc/QD6MH2MJBS) | 去极值→横截面标准化→中性化→score 单链 |
| [DolphinDB 因子评价框架](https://docs.dolphindb.cn/zh/tutorials/factor_evaluation_framework.html) | `preprocess` 统一处理 |
| [Barra Risk Model Handbook](https://roycheng.cn/files/riskModels/barra_risk_model_handbook.pdf) | Descriptor Standardization 统一标准化 |

---

## 9. 复现材料

所有实测脚本均放在临时目录, **未进入仓库** (本调研不做代码改动)。为便于复算, 脚本清单与用途如下:

| 脚本 | 用途 | 关键输出 |
|------|------|----------|
| `fp_measure_windows.py` | 101 因子 × 7 窗口的指纹 AR1 与 VR/DF 分类 | `fp_window_types.csv` / `fp_summary.json` |
| `fp_measure_breaks.py` | 250 天滚动 AR1 路径的 sup-F(自助) 与 CUSUM | `fp_breaks.csv` / `fp_breaks_summary.json` |
| `fp_measure_freq.py` | 日频 vs 月频的 AR1 与分类 | `fp_frequency_ar1.csv` |
| `fp_compare_pipelines_v2.py` | 三管道输出 Spearman / 相对 L2 (Dynamic 的 AR 解耦保持启用) | `fp_pipeline_compare_v2.csv` |
| `fp_compare_pipelines.py` / `fp_compare_pipelines_pv.py` | 早期版本: 误关 neutralizer 导致 Dynamic 退化为 z-score, 仅保留作为"组件不可分离"的反例 | `fp_pipeline_compare*.csv` |
| `fp_ic_real_pipelines.py` | 生产类 Static vs Dynamic 的 \|IC\| 与秩相关 (Q4 主证据) | `fp_ic_real_pipelines.csv` / `fp_ic_real_summary.json` |
| `fp_ic_crosscheck.py` | 校验对齐: 原始 rank vs Static 管道 (两者秩相关 0.999999) | 控制台输出 |
| `fp_measure_ic.py` / `fp_ic_abs.py` | 早期参数化变体 A/B/C/D 试验; 因股票池口径与绝对 IC 量级不一致, **未用于正文结论** | `fp_ic_results.csv` / `fp_ic_abs_summary.json` |
| `fp_sim_break.py` | 突变对 AR(1) 分类的污染模拟 | `fp_break_simulation.csv` |
| `fp_classify12.py` | 12 因子在 750 天拟合窗内的指纹分类 (供 §6.2 使用) | 控制台输出 |
| `fp_clean_summary.py` | 剔除 60 天窗口后的干净聚合 | `fp_summary_clean.json` |

复算要点:
1. 指纹口径必须包含 `min_obs_per_stock=12`、`min_cv_threshold=0.01`、`min_stocks=10` 三道过滤;
2. VR/DF 口径按 [statistical_classifier](../../modules/statistical_classifier/__init__.py#L32-L82) 的 `q=5` + Fuller 表临界值 `−1.95`;
3. IC 检验的 AR 残差必须只用 `t−1` 及之前信息重估 `phi`, 否则会引入前视;
4. 比较管道时**必须保留 Dynamic 的 `neutralizer` 步骤** —— AR 解耦就在其中; 若按"中性化对三条管道相同"的直觉把它关掉, Dynamic 会静默退化为 imputer + z-score, 得出"三管道排序几乎相同"的错误结论。

---

## 10. 局限与未覆盖

| 局限 | 影响 | 缓解 |
|------|------|------|
| 样本仅为 A 股 2020–2026 | 结论不自动外推到美股/期货 | 结论主要落在"机制"层 (排序不变性、突变污染), 机制与市场无关 |
| 财务因子全部为季度更新 + 日频填充 | 天然全 static, 未覆盖真正的 dynamic 因子 | 用 5 个日频 + 5 个月频构造价量因子补充 (§4.5) |
| IC 检验仅 12 个因子 / 36 个调仓点 / 单市场 | 统计功效有限 | 用真实生产类而非自写变体; 报告逐因子结果; 结论方向与文献先验一致 |
| 未做行业/市值中性化 | 与生产管道不完全等价 | 中性化在三管道中相同, 不改变"管道之间"的比较 |
| `factor_data` 长表 (930 万行) 未全表扫描 | 未覆盖库内 5680 个登记因子的全量 | 用 101 个真实面板 + 5 日频/5 月频构造因子, 覆盖 6 大财务类别 |
| 未评估真实交易成本/换手 | 多空/IC 为毛收益 | 仅用于**相对比较**, 不作绝对业绩声明 |

---

## 11. 结论与建议分级

### 11.1 五个问题的最终回答

1. **过度工程化**: 是。三层判定中两层从未接线, 第三层与执行层标签一致率 49.5%, 三条管道中两条数学上等价; 且默认 sigmoid 参数下, "硬路由"分支对 static/mixed 类**在数学上不可达** (`primary_prob` 上界 0.8808 / 0.7616 < 0.90)。复杂度没有换来决策信息。
2. **基准不可比**: 部分是。窗口长度在 ≥120 天时不改变标签 (101/101 单类型); 真正的不可比来源是**采样频率**(同因子 static↔dynamic)、**分类方法**(指纹 vs VR/DF 差 50%)、**管道切换**(Static↔Dynamic 的秩相关仅 0.308、相对 L2 距离 1.25, 即换分类=换信号), 以及短窗口下分类整体失效。
3. **结构性变化检测**: 不能。路由链无断点检验; 唯一相关的两个开关默认关闭且不参与路由; AR(1) 本身会被均值突变污染 (2σ 即可把 dynamic 推成 mixed)。
4. **收益增益**: 不能 (本样本)。12 个因子全部判为 static/mixed, 而 Static 与 Mixed 输出秩等价 (路由为 no-op); 若改判为 dynamic, 平均 \|IC\| 从 0.1156 降至 0.0721 (−37.6%), 11/12 因子变差。
5. **统一方法**: 选 **U1 单一横截面秩管道** (ffill → MAD 缩尾 → 中性化 → rank→normal), 与 Qlib/WorldQuant/Alphalens/Barra 的通行做法一致。

### 11.2 建议分级 (供后续设计步骤决策, 本调研不实施)

| 级别 | 建议 | 依据 |
|------|------|------|
| P0 | 明确"生产只走单管道"的事实, 停用/删除未接线的软路由与多维树 | 代码事实 A1/A2; Q1 |
| P0 | 统一 Static/Mixed 缩尾规则, 把三管道收敛为一条 | Q1(b); §2.4; §7.1 |
| P1 | 指纹降级为诊断; 让执行层分类器与展示层分类器不再各说各话 | §4.4 (49.5%) |
| P1 | 管道选择写入 `SpecificationLogger`, 并把采样频率写入指纹元数据 | §4.5; §7.5 M5 |
| P2 | 结构突变检测移到监控层 (sup-F / CUSUM on rolling AR1 或 IC), 只告警不切换 | §5; Perron 1989; Bai-Perron 1998 |
| P2 | 若要保留 Dynamic, 仅在显式 A/B 实验中开启, 并做 OOS 显著性检验 | §6.3; Bailey-López de Prado 2014 |

### 11.3 一句话总结

> 这套三路路由的**想法**是合理的 (不同类型的因子确实有不同的时序结构), 但**实现**已经退化为"一个手设阈值的分类器 + 两条等价管道 + 一条会削弱信号的 AR 管道", 而**决策链**被拆成三层互不通气的机制。在截面选股这个下游任务上, 统一秩管道更简单、更稳、也更有证据支持。

---

**调研状态**: 调研 (步骤 1) + review (步骤 2) 完成
**下一步**: 步骤 3 设计文档 (若采纳 §11.2)
**代码改动**: 无

---

## 修订记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-11-09 | 步骤 1 调研初稿 |
| v1.1 | 2026-11-09 | 步骤 2 调研 review 修订 (CRITICAL 0 / MAJOR 3 / MINOR 12, 全部修复)。M1 §2.3 代码事实 A7: 动态概率上确界更正 (ar1→−1 处趋近 1, 0.9820 仅为 ar1=0 处取值), 标注 static 硬路由需 ar1>1.0197、硬路由边界精确为 0.1803、表值 0.9002, 补 ar1=0.6 平局的浮点复现注; M2 arXiv:2303.00178 作者更正为 Koo, Wong & Zhong (原误挂 Chen et al.), 标题补 "for Macroeconomic Data"; M3 Feurer 2015 的"常被强单管道追平"主张重新归因于 AutoML 讲义的无免费午餐结论 (原结论非该文); m1 §3.3(a) 行数 300→220、阈值 11→9 (去重)、单测 20+→31 (实数); m2 §4.3 补与 §6.2 因子名单差异的脚注; m3 §5.2 Perron 表述贴原文 (检验无法拒绝单位根假设); m4 §6.6/§8.3 Simmons 2011 由"specification curve"更正为"研究者自由度"; m5 §8.3 Gelman-Loken 链接替换为 American Scientist 原文并区分 2013 工作论文, Claeskens 作者展开 (Magnus, Vasnev, Wang), Timmermann 书名补 "Economic"; m6 §7.3 Ricequant 参数名更正 (mad/std/percentile); m7 §8.1/8.2 卷期页补全 (ERS 813-836、Inclán-Tiao 428、HXZ 2019-2133、FGX 核查栏改标准文献); m8 §8.3 Thornton 补 arXiv 1208.3719; m9 §2.3 引言限定为 static/mixed 上界 |

**调研 review 结论**: 2026-11-09; 双轨 review (代码引用对齐 + 学术引用核实) 均为 PASS with fixes。代码事实 A1–A8 逐条核实成立, 含 §2.3 表 9 行 sigmoid 数值验算、三函数调用点全仓库检索 (仅定义处 + tests ×3 + notebooks)、`enable_multi_dim_routing` 零读取点、相关单核实数 31 个; 学术锚点 P0 15 项中 13 项完全核实 (Perron 方向、HLZ t>3.0、因子动量在收益层、组合预测谜题、伪因子、CASH、GKX 统一预处理等承重主张全部与原文一致), 2 项修正后一致; 链接抽查 20 个 (19 可访问, pm-research 与 SSRN 两处反爬拦截经旁证确认映射); 报告内部数字自洽 (−37.6% 等算术复核通过)。五项结论方向 (未接线 / 冗余 / 不可检 / no-op / 统一秩管道) 全部获得支持。可进入步骤 3 (设计文档)。

**步骤 8 勘误注** (2026-11-10): 上表 v1.1 行的 "MINOR 12" 为**发现数**, m1–m9 为**修订条目号** (12 项 MINOR 发现归并为 9 条修订落盘), 二者不逐项对应。详见 [CONSISTENCY_REVIEW_V3.4.0.md](../audit/CONSISTENCY_REVIEW_V3.4.0.md)。步骤 8 四方对账复核: 本文档全部数值锚点 (0.999998 / 0.308 / 49.5% / −37.6% / 2σ→0.4041 / T=750→26 点) 在设计/实施/checklist 中无转抄漂移。
