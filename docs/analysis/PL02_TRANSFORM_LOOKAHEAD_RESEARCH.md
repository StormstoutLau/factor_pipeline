# PL-02 变换步骤前视缺陷调研

**文档版本**: v1.10 (调研完成, 默认方案与实现范围均已决策; v1.1 = review 修正: 代码行号 2 处、probe4 计时标注、probe7 无种子计数标注、数量级表述收紧; v1.2 = 追加 §3.1 方案 A/B vs C 的证据基础 + 参考文献 4 条 + 附录 B 检索记录; v1.3 = 追加 §3.2 regime 判别方法与实测 + 参考文献 8 条 + probe8; v1.4 = 追加 §3.3 A/B 恒等式与端到端实测 + probe9; v1.5 = 追加 §3.3.6/3.3.7 真实 A 股 skew 复测 + probe10, 并修正 §3.3.3 关于"4.58 属极端情形"的判断; v1.6 = 追加 §3.4 rank 变换数学推导与收益分析 + probe11/12; v1.7 = 追加 §3.5 rank 对中性化语义的影响 + probe13; v1.8 = 决策 rank→正态(Blom) + I-INT, 追加 §3.6, 修正 §3.4.5 的 van der Waerden 命名错误; v1.9 = 追加 §3.7 实现范围决策, 修正 §3.6.4 配置契约, 登记旧 transform 路径的逐列维度潜伏缺陷; v1.10 = 追加 §3.8 条件性变换的学术/社区证据 + 参考文献 27-31)
**日期**: 2026-10-22
**实施状态**: 已按本文结论实现 (v3.3.4, ADR-038). 实测: PL-02 隔离 1800 格/8.51e-04 → 0; Static 端到端 4.72e-05 → 0; Mixed 残留 6.98e-01 属 PL-06; Dynamic / 顶层分别受 PL-05 / PL-05+06+路由影响. 详见 CHANGELOG v3.3.4 与 [EXECUTION_V3.3.4_PL02_TRANSFORM_CAUSALITY.md](../EXECUTION_V3.3.4_PL02_TRANSFORM_CAUSALITY.md) §7.
**缺陷编号**: DEFECT-PL-02
**调研范围**: `adapters.py` `ProcessingAdapter(process_type='transformation')` + `factor_adaptive_winsor` 的 `AdaptiveTransformer` + Static / Mixed / 顶层管线的变换路径
**调研方法**: 源码逐行核对 + 截断不变式实测 + 逐方法探针 + MCP 学术/社区检索 (StackExchange / Crossref / Semantic Scholar) + 官方文档与论文原文核对
**核心原则**: t 时刻的输出只能使用 `F_t` (t 时刻及以前可观测的信息). 对 (T, N) 因子面板, 同一交易日内的横截面属于 `F_t`, 未来交易日不属于
**证据等级**:
- **A**: 直接读到原文/摘要/官方文档, 可核对
- **B**: 搜索结果摘要或二手实现说明, 未读到原文对应段落
- **C**: 项目内部代码/文档, 可逐行核对
- **U**: 未能验证, 明确标注, 不作为论据

---

## §0 摘要 (TL;DR)

PL-02 不是单点缺陷, 而是**四层相互叠加**的问题:

| # | 问题 | 性质 | 实测 |
|---|------|------|------|
| 1 | `fit()` 用 `X.values.flatten()` 在**全 panel** 上池化拟合 λ / offset / 经验 CDF | 前视: 前 t 期变换参数依赖 t 之后的数据 | 截断 60/100 期, 隔离 `auto`: 1798/1800 格差异, `max=8.506e-04` |
| 2 | `AdaptiveTransformer` 的 `_select_optimal_transform` 依赖全样本偏度/峰度/Shapiro p; 且 Shapiro 子采样**未设随机种子** | **第二重前视 + 不可复现**: 方法选择依赖未来样本, 同输入多次拟合可能选到不同方法 | 构造未来段偏移后 full→`yeojohnson`, trunc→`identity`, `max=1.736`; 同 10000 点输入 20 次拟合: 8 次 YJ / 12 次 identity |
| 3 | `auto_optimize=True` (默认) 覆盖**所有**显式 `method` | 配置-行为不一致: 显式声明的方法无效 | `method='identity'/'log'/'boxcox'/'quantile'/'power'` 均被改选为 `yeojohnson` |
| 4 | 配置层方法名与实现层不一致 (`box_cox` / `yeo_johnson` / `none` vs `boxcox` / `yeojohnson` / `identity`) | 潜在崩溃, 被第 3 层掩盖 | `method='yeo_johnson'` + `auto_optimize=False` → `ValueError: 未知的变换方法` |

**结论**:
1. 仅把 `auto` 改成固定方法**不能**修复 PL-02: 参数 (λ / offset / CDF) 仍在全样本上估计, 且 `auto_optimize=True` 仍会覆盖显式方法. 必须同时处理**方法选择**与**参数估计**两个面.
2. 变换是**单调**的, 因此逐日 Spearman 排序完全不变 (实测中位数/最小值均为 1.000000). 这解释了为什么 IC / 排序类回测长期未暴露该缺陷; 但值域变化会传导到 Mixed 的后续中性化 (Mixed 顺序为 transform→neutralize) 与多因子组合权重.
3. 修复会改变输出数值, 需要缓存代际 bump (与 PL-01/PL-03 同类处理).
4. 范围边界: 修 PL-02 应同时关闭 PL-04 (Static 残留仅由 PL-02 构成); PL-06 还包含独立的全样本缩尾 (`_compute_winsorize_params`), PL-07 还包含指纹路由依赖全样本, 均不在本文范围.
5. 实现落点 (§3.7): transformation 层新增 `method='rank'`, 输出分布由已有的 `target_distribution` 控制; 必须新增 `ProcessingAdapter._cross_sectional_rank` 分支 — 现有 transform 路径按股票列 (时序) 逐列应用, 对逐元素方法无害, 但对 rank 是语义错误 (潜伏缺陷). rank 无状态, 截断不变性在结构上成立.
6. 条件性变换 (§3.8): 无学术或开源实践支持"逐期按分布检验决定是否变换". 所有命中来源均为固定方法 + 逐截面应用; ORQ (rank→正态) 对任意分布有效, 无 ties 时保证输出正态 (Peterson & Cavanaugh 2019); pre-test / post-selection 估计量的分布不可一致估计 (Leeb & Pötscher 2006/2008), 故在线切换会污染下游统计量.

---

## §1 缺陷复现与范围

### 1.1 代码路径

| 位置 | 行为 | 性质 |
|------|------|------|
| [adapters.py L508-519](../../adapters.py#L508-L519) | `else` 分支: `flat_data = X.values.flatten()` 后 `processor.fit(flat_data)` | 全 panel 池化, 跨日期混样 |
| [adapters.py L563-575](../../adapters.py#L563-L575) | `transform` 逐列 (`for col in X.columns`) 套用同一组拟合参数 | 历史输出随未来样本变化 |
| [transformers.py L511-558](../../modules/factor_adaptive_winsor/core/transformers.py#L511-L558) | `AdaptiveTransformer.fit` 在 `X_clean` 上分析特征、选方法、拟合参数 | 全样本统计量进入拟合 |
| [transformers.py L527-533](../../modules/factor_adaptive_winsor/core/transformers.py#L527-L533) | `if self.method == 'auto' or self.auto_optimize: selected_method = ...` | **显式 method 被静默覆盖** |
| [transformers.py L589-621](../../modules/factor_adaptive_winsor/core/transformers.py#L589-L621) | `_analyze_features`: skew / kurt / Shapiro p / `is_positive` | 选型依赖全样本分布 |
| [transformers.py L605](../../modules/factor_adaptive_winsor/core/transformers.py#L605) | `np.random.choice(X, 5000, replace=False)` **未设 seed** | 选型不可复现 (样本 >5000 时) |
| [transformers.py L623-635](../../modules/factor_adaptive_winsor/core/transformers.py#L623-L635) | `_select_optimal_transform`: identity / yeojohnson / boxcox / log / quantile | 方法选择本身是前视源 |
| [transformers.py L637-791](../../modules/factor_adaptive_winsor/core/transformers.py#L637-L791) | `_fit_yeojohnson` / `_fit_boxcox` / `_fit_quantile` / `_fit_power` / `_fit_log` | λ / offset / CDF / power 参数来自全样本 |
| [pipelines_v2.py L887-906](../../pipelines_v2.py#L887-L906) | Static: `ProcessingAdapter(process_type='transformation', method='auto')` | 三种机制全部命中 |
| [pipelines_v2.py L1099-1105](../../pipelines_v2.py#L1099-L1105) | Mixed: 条件变换, `method='yeo_johnson'` (非法名) | 被 `auto_optimize` 掩盖, 实际仍自动选型 |
| [pipelines_v2.py L1172-1176](../../pipelines_v2.py#L1172-L1176) | `_diagnose_transform_need` 用全样本 median skew/kurt | PL-06 范围, 与 PL-02 叠加 |
| [config_v2.py L66-78](../../config_v2.py#L66-L78) | `TransformationConfig.method` 取值为 `auto/box_cox/yeo_johnson/quantile/log/none` | 与实现层名称不一致 |
| [config.py L117-122](../../config.py#L117-L122) | 旧配置: `{'method': 'auto', 'auto_optimize': True}` | 旧路径同样受影响 |

### 1.2 实测矩阵

**探针环境**: Python 3.12, 项目源码未改动; 探针脚本位于系统临时目录, 不进入仓库. 面板为 `T=100, N=30, t=60`.

#### 1.2.1 与测试登记对齐的基线

| 测量 | 构造 | 结果 |
|------|------|------|
| 隔离 `transform auto` | `seed=11, kind='smooth'` | 1798/1800 格差异, `max=8.506103e-04`; full/trunc 均选 `yeojohnson`; λ=1.08547326 / 1.08620139 |
| `StaticFactorPipeline` 端到端 | `seed=21, kind='smooth'` | `max=4.720e-05` (登记值, 仅 PL-02 残留) |
| `MixedFactorPipeline` 端到端 | `seed=23, kind='skewed'` | `max=2.905632e-01` (与登记 2.906e-01 一致) |
| Mixed 关闭缩尾 | 同上, `module_enabled={'winsorizer': False}` | `max=2.082468e-02` → 默认配置下约 93% 的差异来自 PL-06 的全样本缩尾 |
| `DynamicFactorPipeline` | `kind='ar_low'` | 管线无变换步骤, PL-02 不影响; 残差属 PL-05 |

#### 1.2.2 显式方法的实际语义 (`auto_optimize=False`)

| `method` | full/trunc 选中方法 | 差异格数 | `max_abs_diff` |
|----------|--------------------|---------|----------------|
| `identity` | identity / identity | 0/1800 | 0 |
| `log` | log / log | 0/1800 | 0 (该面板最小值落在前 60 期, offset 恰好相同; **非结构性因果**) |
| `yeojohnson` | YJ / YJ | 1798/1800 | 8.506e-04 |
| `boxcox` | BC / BC | 1800/1800 | 2.319e-02 |
| `power` | power / power | 1800/1800 | 1.576e-02 |
| `quantile` | quantile / quantile | 1799/1800 | **2.065e+00** |

说明: `log` 的 offset 来自全样本最小值, 只是在该面板上恰好未变. 构造"未来段出现新最小值"的面板后:

| `method` | 全样本 vs 截断参数 | 差异格数 | `max_abs_diff` |
|----------|-------------------|---------|----------------|
| `log` | offset 13.6611 vs 3.2514 | 1800/1800 | **2.076e+01** |
| `boxcox` | offset 13.6611 vs 3.2514; λ 0.8921 vs 0.8677 | 1800/1800 | **9.094e+00** |
| `yeojohnson` | λ 1.6369 vs 0.9514 | 1800/1800 | **2.401e+00** |
| 全正数据 `log` | offset 0 / 0 | — | 结构上无参数 |

#### 1.2.3 方法选择翻转

| 构造 | 全样本 | 截断 | 差异 | `max_abs_diff` |
|------|--------|------|------|----------------|
| 未来 40 期整体偏移 +6 | `yeojohnson` (λ=0.5416) | `identity` | 1800/1800 | **1.736441** |
| 未来 40 期 t(2)×3 厚尾 | `yeojohnson` (λ=0.8736) | `identity` | 1799/1800 | **3.916e-01** |
| 200 个波动率缩放面板 | 200/200 YJ | 200/200 YJ | 0/200 翻转 | 同方法时 \|Δλ\|: median 5.090e-02, p95 2.666e-01, max 4.681e-01 |

结论: 方法选择翻转不是"必然每次都发生", 但一旦发生, 值域差异可达 1.7 量级; 即使方法不变, λ 本身也会随未来样本显著漂移.

#### 1.2.4 同输入不可复现

`_analyze_features` 在样本数 >5000 时无种子随机抽取 5000 个值做 Shapiro-Wilk 检验. 对同一份 10000 点输入连续拟合 20 次, 两次独立运行给出不同实现:

- 第 1 次: 8 次选 `yeojohnson`, 12 次选 `identity`; Shapiro p 值范围 0.00064 ~ 0.83563;
- review 复跑 (第 2 次): 12 次选 `yeojohnson`, 8 次选 `identity`; p 值范围 0.00087 ~ 0.47083.

具体计数逐次不同 —— 这正是无种子子采样的直接后果. 同一份数据、同一配置, 仅因随机子采样就可能得到不同变换方法. 这是独立于前视的**可复现性缺陷**.

#### 1.2.5 逐日截面拟合 λ 的稳定性与成本 (N=30)

| 面板 | 统计 | 结果 |
|------|------|------|
| smooth, 100 日 × 30 股 | YJ λ: median / IQR / std / range | 1.0854 / (1.0824, 1.0893) / 0.0056 / [1.0714, 1.1032] |
| skewed, 100 日 × 30 股 | YJ λ: median / IQR / std / range | -0.8221 / (-0.9640, -0.6395) / **0.2515** / [-1.3064, 0.0944] |
| skewed, 100 日 × 30 股 | BC λ: median / IQR / std / range | -0.0029 / (-0.1041, 0.1146) / 0.1477 / [-0.3545, 0.3725] |
| 成本 | 100 次逐日 YJ 拟合 / 单次全 panel 拟合 | 首测 3.78–6.79 s / 17.08 ms; review 复跑 0.48–1.02 s / 5.5 ms (计时随机器负载波动, 比值稳定在约两个数量级) |

解释: 在 N=30 的截面上逐日重估 λ 方差很大; 逐日拟合比单次全 panel 拟合慢约两个数量级 (两次实测比值 221–398× 与 86–184×). 该结果直接约束候选方案 D (见 §3).

#### 1.2.6 为什么 IC/排序没有暴露

| 场景 | Spearman 中位数 | Spearman 最小值 | Pearson 最小值 | 值域 max 差异 |
|------|-----------------|-----------------|----------------|---------------|
| smooth `seed=11` | 1.000000 | 1.000000 | 1.000000 | 8.506e-04 |
| 方法翻转 (未来偏移) | 1.000000 | 1.000000 | 0.969642 | 1.736441 |

原因: 当前实现把**同一个**单调变换函数应用到同一日所有股票, 因此逐日排序完全保持. IC / Rank IC 对这类泄漏天然不敏感; 截断不变式 (值相等) 是更灵敏的探测器. 这也与 PL-01 的发现一致.

### 1.3 生产路径映射

| 路径 | 是否受影响 | 机制 |
|------|-----------|------|
| `StaticFactorPipeline` | **是** | `method='auto'`; 全 panel flatten; 全样本选型; `enabled=False` 被强制忽略 |
| `MixedFactorPipeline` | **是** | 条件变换; 声明 `method='yeo_johnson'` (非法) 被 `auto_optimize` 掩盖; `_diagnose_transform_need` 与缩尾均用全样本 (PL-06) |
| `DynamicFactorPipeline` | 否 | 无变换步骤; 残差属 PL-05 |
| `FactorProcessingPipelineV2` (顶层) | **是** | 路由到 Static/Mixed; 另有指纹路由依赖全样本 (PL-07) |
| 旧 `FactorProcessingPipeline` 配置 | **是** (若使用) | `config.py` 显式 `auto` + `auto_optimize=True` |
| `PipelineV2Config.transformation` | 配置未接线 | `StaticFactorPipeline` / `MixedFactorPipeline` 构造器均硬编码变换方法, 未消费该配置 |

### 1.4 额外契约缺陷

1. **配置名与实现名不一致**: `TransformationConfig` 允许 `box_cox` / `yeo_johnson` / `none`, 而 `AdaptiveTransformer` 只识别 `boxcox` / `yeojohnson` / `identity`; `power` 反向缺失. 当前因 `auto_optimize=True` 永远走自动选型而未暴露.
2. **`auto_optimize` 覆盖范围过大**: `if self.method == 'auto' or self.auto_optimize` 使 `method='identity'` 也被覆盖. 这使"显式固定方法"这一最直接的修复路径失效.
3. **`enabled=False` 对 transformation 无效**: [adapters.py L366](../../adapters.py#L366) 与 L390-394 强制 `enabled=True`; 现有测试 [test_module_enabled.py L79-120](../../tests/test_adapters/test_module_enabled.py#L79-L120) 将其固化为契约. 若设计允许关闭变换, 需同步修改该契约.
4. **`fit` 与 `transform` 的数据口径不一致 (Mixed)**: Mixed 在 `fit` 中用**未缩尾**的 `X` 拟合变换与诊断, 但 `transform` 中先缩尾再变换. 这是 PL-06 范围内的语义问题, 会影响 PL-02 修复后的端到端归因.

---

## §2 判据: 什么是"因果的变换"

对 (T, N) 因子面板, 记 `F_t` 为 t 日收盘后可观测的信息. 要求:

```
transform(x_{i,t}) = f_t( x_{i,t}; θ_t ),   θ_t 只能由 F_t 估计
```

其中 `θ_t` 是该方法需要估计的参数:

| 方法 | 拟合参数 | 若全样本拟合, 泄漏面 |
|------|---------|---------------------|
| `identity` | 无 | 无 |
| `log` | `offset = -min + 1e-8` (存在非正值时) | 未来出现更低最小值 → offset 改变 |
| `boxcox` | `offset` + λ | offset 与 λ 双泄漏 |
| `yeojohnson` | λ | λ 随未来样本漂移 |
| `quantile` | 经验 CDF (`n_quantiles`) | 全局分位映射, 泄漏最大 |
| `power` | 幂指数 (最小化偏度) | 指数随未来样本变化 |
| `auto` | 方法选择 (skew/kurt/Shapiro p) | 方法本身依赖未来样本 |

三条候选形态:

- **逐日截面参数**: `θ_t` 只用当日 `{x_{j,t}}` → 天然因果; 在 N 较小时估计噪声大 (见 §1.2.5).
- **扩展/滚动窗口参数**: `θ_t` 用 `{x_{j,s}: s ≤ t}` → 因果; 保留自适应性; 成本随重估频率线性增长.
- **全样本池化参数** (当前): 使用 `s > t` 的数据 → 违反 `F_t`.

**单调性事实**: 上述方法在共同参数下都是单调变换; 同一日应用同一函数时, 截面排序不变. 因此:
- 排序类指标 (IC / Rank IC) 无法检测;
- 依赖数值的步骤 (标准化后的加权、Mixed 的中性化、ML 输入、组合权重) 会受影响;
- Mixed 的顺序是 transform→neutralize, 变换泄漏会进入中性化; Static 是 neutralize→transform, 中性化本身不受影响, 但后续标准化与组合权重受影响.

---

## §3 候选方案 (研究层评估, 不作最终决策)

| 方案 | 做法 | 因果性 | 可复现性 | 统计语义 | 成本 | 兼容性 |
|------|------|--------|---------|---------|------|--------|
| **A. 参数无关固定变换** | 固定 `identity` / signed log1p / 正数据 `log(offset=0)`; 不估计任何参数 | 结构性满足 | 完全确定 | 放弃自适应; 对厚尾仅做固定压缩 | 最低 | 输出变化; 需更新 `_processor` 契约 |
| **B. 固定方法 + 固定参数** | 构造期固定方法, λ/offset 作为常量 (如 λ=0 的 log、λ=1 的 identity); `fit` no-op | 结构性满足 | 完全确定 | 需事前论证 λ; 不能随因子/ regime 调整 | 最低 | 显式方法语义需先修复 `auto_optimize` |
| **C. 扩展/滚动窗口 λ 调度** | 在重估日 `t_k` 用 `[0, t_k]` 池化拟合 λ/offset; 日间 carry-forward; 批量 API 内存调度表 | 满足 (每个 `θ_t` 只用历史) | 确定 (需固定重估频率) | 保留 YJ/Box-Cox 自适应; 与时间序列 CV 原则一致 | 重估次数 × 单次拟合; 月/季度重估可控 | 需新增调度状态; 早期样本需回退 |
| **D. 逐日截面 λ** | 每个交易日用当日截面拟合 λ/offset | 满足 | 确定 (无随机子采样) | N=30 时 λ 方差大 (YJ std 0.2515); 仅适合大 N | 每日一次拟合; 实测 100 日 0.5–6.8 s (负载相关) | API 可兼容; 但小截面不稳定 |
| **E. 按列扩展窗口** | 每只股票用自己的历史拟合参数 | 满足 | 确定 | **不推荐**: 同一日不同股票使用不同参数, 破坏横截面可比性 (与 PL-01 §2 同理) | 高 | 与因子截面语义冲突 |

**证据倾向** (供设计文档决策, 不是最终选择):
- 若目标是"结构上无泄漏 + 可复现", A/B 是最低保证; 但它们放弃了自适应变换.
- 若必须保留 YJ/Box-Cox 的自适应, C 是唯一同时满足因果性、统计语义与可控成本的方案; 关键设计点是重估频率、早期回退与批量 API 内的调度表.
- D 在 N=30 的面板上不稳定且昂贵, 不建议作为默认路径; 只有在 N 很大 (如全市场数千只) 且按日重估可接受时才考虑.
- E 与因子横截面语义冲突, 排除.

### 3.1 方案 A/B 与 C 的证据基础

**检索结论: 没有找到直接对比"固定变换参数"与"扩展窗口重估变换参数"的实证研究.** 检索覆盖 Semantic Scholar / Crossref / arXiv API / OpenAlex / StackExchange (stats, quant), 没有一篇以变换 λ 或 offset 的重估频率为处理变量. 因此下列证据全部是**类比证据**, 用于给出先验方向, 不能当作裁决性对照实验.

| 证据 | 原文要点 | 对 A/B vs C 的含义 | 等级 | 适用性差距 |
|------|---------|-------------------|------|-----------|
| FPP3 §3.1 (已引) | "...any value of λ between 0.0 and 0.2 would give similar results" | λ 在邻域内不敏感 → C 的统计收益上限低 | A (原文) | 单序列季节调整, 非截面因子 |
| Zanotti (2025) | 比较"持续更新"到"完全不重训": "less frequent retraining strategies maintain the forecast accuracy while reducing the computational costs"; "our findings challenge the conventional belief that frequent retraining is essential" | 重估频率存在边际收益递减; 低频 (季/年) 是合理形态 | A (摘要原文) | 处理变量是模型全量重训, 不是变换 λ |
| Guerrero (1993) | 提出 "essentially model-independent" 的方差稳定化变换选择方法; FPP3 的 `guerrero` 特征对**整条序列**选一个 λ (=0.11) | 经典时序实践是"用全部历史定一个 λ", 与 C 的扩展窗口形态同构 | A (摘要 + FPP3 实现) | 单序列, 无截面维度 |
| De Gaetano (2018) | "(i) the hypothesis of constant model parameters is rejected for all markets... (ii) in all cases, the recursive forecasting approach... is outperformed by forecast combination schemes; (iii) weighting schemes that assign more weight in most recent observations are superior in the majority of cases" | 参数**不稳定**时, 常量参数与纯扩展窗口都会劣化 → 若因子有 regime 切换, B 有实际代价 | A (Crossref 摘要) | HAR-RV 波动率模型, 非变换参数 |
| Artemova et al. (2021) | 灵活滚动窗口在 "structural breaks, complex nonlinearities, or other time-varying properties" 下改善误设模型的预测精度 | 同上, 支持"时变参数"方向 | B (摘要) | 线性 AR 模型 |
| sklearn `PowerTransformer` | 官方 API 文档的 Methods 列表中**没有 `partial_fit`** (该估计器不支持增量拟合) | C 的增量 λ 无法复用现成 API, 需自建调度表与状态 | A (官方文档) | 工程约束, 非统计证据 |
| 本项目实测 (§1.2.5) | N=30 时逐日 λ std=0.2515 (skewed); 逐日重估慢约两个数量级 | D 排除; C 的低频重估成本可控 | C | — |

**关键区分: B 的 λ 必须先验指定.** 若 B 实现为"用全样本估一次 λ 再冻结", 泄漏并未消除, 只是从"每期泄漏"变成"一次泄漏全部未来信息" —— 该 λ 仍是未来样本的函数. 合法的 B 必须是 λ 由外部给定 (经济含义、文献值或先验), 例如 λ=0 (log) 或 λ=1 (identity). 这使 B 的成本从"工程实现"转移到"方法论论证".

**条件化倾向** (供设计文档, 不是最终决策):

- 若因子分布近似平稳 → B 的统计代价小 (FPP3: λ 邻域不敏感), 且结构性因果、零调度状态、易审计; 优先考虑.
- 若因子存在明显 regime 切换 → 固定参数会劣化 (De Gaetano 2018: 常量参数假设被拒), 此时 C 的低频重估 (季/年) 有依据, 且 Zanotti (2025) 表明低频重估不损精度. **但本项目实测 (§3.2.4) 在三类合成面板上未检出显著 regime**, 因此这一分支的适用性需先由 §3.2.5 的信噪比 ρ 判定.
- 两种情形下 C 都不是"更正确", 而是"更贵且更自适应". 是否支付该成本取决于因子族特征, 而非管线通用性.

**证据边界**: 上述类比证据的对象均为"模型参数"或"单序列变换", 本项目是 (T, N) 面板上的截面变换. 跨用需在设计文档中显式声明假设, 不可直接表述为"文献支持方案 X".

### 3.2 regime 切换判别: 方法、因果性与本项目实测

§3.1 的条件化倾向把 C 的收益绑定在"因子存在明显 regime 切换"上. 本节回答两个问题: regime 判别是否有成熟方法, 以及**这些方法能否因果地支撑 C**.

#### 3.2.1 三类判别方法及其实时性

| 方法族 | 代表文献 | 能否因果 | 关键限制 | 证据 |
|--------|---------|---------|---------|------|
| **离线结构突变检验** | Bai & Perron (1998); Chow / sup-F | **否** | 需用全样本定位断点; 原文: "functions as an **offline indicator**, as **real-time detection of breaks is not feasible** with this method" | A (2411.12845 摘要) / B (Bai-Perron 元数据) |
| **Markov switching / HMM** | Hamilton (1989) | **是**, 但仅限滤波概率 | 原文: "the **Markov switching** approach can reduce revisions while being **useful in real time**"; 但平滑概率 `P(s_t \| y_{1:T})` 使用全样本, 直接作信号即前视 | A (2411.12845 摘要) / B (Hamilton 元数据) / B (滤波-平滑区分) |
| **在线监测 / 序贯检验** | Chu, Stinchcombe & White (1996); CUSUM; Page-Hinkley; BOCPD | **是**, 但有延迟 | **检测延迟 (detection delay) 是结构性的**; 原文: 边界函数 "designed to **shorten the detection delay**", 并 "derive the limiting distribution of the **detection delays**" | A (2404.17885 摘要) / B (Chu 等元数据) |

三者的取舍不是"哪个更准", 而是"**实时性 vs 定位精度**": 离线检验能精确给出断点日期但不可实时; 在线监测可实时但把精度换成延迟; Markov switching 介于两者之间, 且给出状态概率而非断点.

#### 3.2.2 因果性硬约束 (若采用 regime 判别)

1. **只用滤波概率**. `P(s_t | y_{1:t})` 是因果的; `P(s_t | y_{1:T})` 用全样本, 若据此触发重估则重估时刻的选择本身含未来信息.
2. **判别器参数也必须滚动估计**. 转移概率、状态数、阈值若用全样本确定, 会把前视从"λ"转移到"判别器" —— 这是**元参数前视**, 不会因为多了一层建模而消失.
3. **检测延迟必须计入 SLA**. 事件触发的重估实际生效时刻 = 真实断点 + 检测延迟. 延迟期内参数已失效但未更新, 这段区间在回测中若被忽略, 等价于隐含了"零延迟"假设.

#### 3.2.3 窗口选择理论: 与 C 直接对应

| 文献 | 结论 | 与 C 的关系 |
|------|------|-----------|
| Pesaran & Timmermann (2007), *J. Econometrics* 137(1):134–161 | 断点存在时, 估计窗口长度需在"偏差 (陈旧数据)"与"方差 (样本量)"之间权衡 | 给出 C 的**窗口选择**理论框架 |
| Inoue, Jin & Rossi (2017), *J. Econometrics* 196(1):55–67 | 提出时变参数下的滚动窗口选择方法 | C 的**重估频率/窗口长度**可直接引用 |
| Hännikäinen (2016), *J. Econometric Methods* 6(1) | "the **expanding window** estimator often yields the most accurate forecasts **after a recent break**" | **直接支撑 C 的扩展窗口形态** (而非滚动窗口) |

#### 3.2.4 本项目实测: 三个代表面板均未检测到显著 regime

探针 `pl02_probe8.py` (附录 A): 对每类面板逐日拟合截面 YJ λ (T=100, N=30), 再检验 λ 序列的持续性与断点.

| 面板 | λ mean / std / range | ACF lag1 (95% 带 ±0.196) | AR(1) φ / R² | Chow (t=50) p | sup-F 扫描 min p | 判定 |
|------|---------------------|--------------------------|--------------|---------------|------------------|------|
| smooth (seed=11) | 1.0858 / 0.0056 / [1.0714, 1.1032] | **-0.0944** | -0.0945 / **0.0091** | 1.60e-01 | 9.25e-02 (t=59) | 无显著断点, 近似白噪声 |
| skewed (seed=23) | -0.7921 / 0.2515 / [-1.3064, 0.0944] | **-0.2263** | -0.2263 / **0.0514** | 9.92e-01 | 3.53e-01 (t=24) | 无断点; 弱负自相关 (均值回复) |
| ar_low (seed=22) | 0.9865 / 0.2890 / [0.0621, 1.6954] | 0.0334 | 0.0338 / **0.0012** | 8.33e-01 | 5.17e-02 (t=10) | 无显著断点 |

说明: sup-F 为扫描 10 ≤ t ≤ 90 的最小 p 值, **未做多重检验修正**, 因此实际显著性更弱; 三个面板的 Chow p 均 > 0.05.

**关键观察**: λ 的逐日变化**不是持续性 regime**, 而是估计噪声 —— AR(1) R² 最高仅 0.0514. 若用事件驱动重估, 在这些面板上**没有 regime 可供触发**.

#### 3.2.5 C 的收益来自"水平估计"而非"regime 跟踪"

同一探针比较三种 λ 预测器的 RMSE (t ≥ 20):

| 面板 | 扩展窗口均值 (因果) | 固定 λ=1 | 全样本均值 (前视参照) |
|------|-------------------|---------|---------------------|
| smooth | 0.0055 | 0.0860 | 0.0055 |
| skewed | 0.2506 | **1.8183** | 0.2471 |
| ar_low | 0.2760 | **0.2710** | 0.2714 |

两个结论:

1. **因果的扩展窗口几乎不损失精度**: 扩展窗口均值 RMSE 与全样本均值 RMSE 几乎相同 (0.0055/0.0055, 0.2506/0.2471, 0.2760/0.2714). 这支撑 C 的可行性, 也说明"用历史估计水平"本身是低成本的.
2. **固定 λ=1 的相对表现取决于先验偏离**: skewed 面板上固定 λ=1 比扩展窗口差 7.3 倍; ar_low 面板上反而略好 (0.2710 < 0.2760), 因为其真 λ 均值 0.9865 本就接近 1.

由此得到可操作判据:

```
信噪比 ρ = |λ_prior - λ̄_t| / std(λ_s, s ≤ t)    (全部量在 t 时刻可观测)
```

ρ ≫ 1 → 先验偏离远大于估计噪声, 扩展窗口估计有实质收益 (smooth ρ≈15, skewed ρ≈7);
ρ ≲ 1 → 先验已足够好, 固定参数更稳 (ar_low ρ≈0.05).

**因此设计文档不必先回答"有没有 regime", 而应先测 ρ.** ρ 低时 C 无收益; ρ 高时 C 的收益来自"估计参数水平", 不需要任何 regime 判别器.

#### 3.2.6 适用性错配声明

- 上述 regime 文献的研究对象是**收益/波动率**的结构变化; C 需要的是**因子值截面分布形态** (偏度/峰度) 的变化. 两者不是同一随机过程, 不可直接外推.
- **没有找到**以"变换 λ 的 regime 切换"为研究对象的文献. 截面矩可作监测指标 (如 arXiv:2602.07066 用截面标准差/偏度/峰度构造市场压力指标), 但那是风险监测, 不是变换参数重估的依据.
- 本项目实测 (§3.2.4) 在三类合成面板上均未检出 regime, 进一步削弱"以 regime 触发 C"的动机.

### 3.3 方案 A 与 B 的取舍: 同族参数还是不同族

§3.1 只比较了 A/B 与 C, 未拆解 A/B 之间. 本节补齐三处缺口: A 的内部子选项、A/B 的恒等关系、端到端影响.

#### 3.3.1 关键恒等式: A1 是 B 的特例, A2 不是

固定 λ 的 Yeo-Johnson 定义为:

```
x ≥ 0:  ((x+1)^λ − 1) / λ      (λ ≠ 0);   log(1+x)      (λ = 0)
x < 0:  −((1−x)^(2−λ) − 1)/(2−λ)  (λ ≠ 2);   −log(1−x)  (λ = 2)
```

数值验证 (10000 个含负值随机点, `pl02_probe9.py`):

| 恒等式 | `max_abs_diff` | 结论 |
|--------|---------------|------|
| YJ λ=1 vs identity | **8.882e-16** | 浮点精度内**完全恒等** |
| YJ λ=0 vs `signed_log1p` | **6.882e+01** | **不等价** |
| YJ λ=2 负半轴 vs `−log(1−x)` | 0.000e+00 | 恒等 |

第二行是一次推导纠错: YJ 的 **λ=0 特殊分支只作用于正半轴**; 负半轴仍走 `−(1−x)^(2−λ)` 通式 (= `−((1−x)²−1)/2`), 只有 **λ=2** 才取 `−log(1−x)`. 因此 `signed_log1p` 等价于"正半轴取 λ=0、负半轴取 λ=2"的**混合**, 不能由单一 λ 表示.

推论:

- **A1 (`identity`) 就是 B 在 λ=1 处的取值.** 二者在因果性、可复现性、拟合成本上完全相同, 差异为零. 因此"A1 vs B"是**伪对立**.
- **A2 (`signed_log1p`) 属于 YJ 族之外的另一个变换族**, 与任何单一 λ 都不等价. 因此"A2 vs B"是**真对立**, 但对立面是"是否离开 YJ 族", 而非"是否有参数".

#### 3.3.2 管线位置决定了变换的作用空间

| 管线 | 顺序 | 变换的输入/输出环境 |
|------|------|-------------------|
| Static | imputer → **缩尾 (1%/99%)** → 中性化 → **变换** → **逐日 z-score** | 输入端厚尾已被截断; 输出端被 z-score 线性重缩放 |
| Mixed | imputer → **缩尾 (mean±3σ)** → **变换** → 中性化 → **z-score** | 输入端已缩尾; 变换结果进入中性化回归 |

z-score 只做平移与尺度变换, **无法恢复非线性变换改变的相对间距**; 因此变换并非冗余, 其残余作用集中在"截面相对间距 → 中性化杠杆点 → 残差".

#### 3.3.3 端到端影响实测

在 Static 的 `neutralize` 中间量 (缩尾+中性化之后、变换之前) 上逐一施加固定变换, 再按原管线做逐日 z-score, 与 `identity` 比较 (`pl02_probe9.py`):

| 变体 | smooth (mid skew=0.0050) | skewed (mid skew=4.5788) |
|------|-------------------------|--------------------------|
| A1 `identity` (= YJ λ=1) | 0 | 0 |
| A2 `signed_log1p` | 3.348e-01 | 1.774e+00 |
| B λ=0.5 | 4.739e-01 | 2.601e+00 |
| B λ=0.25 | 6.781e-01 | 3.420e+00 |
| B λ=1.5 | 5.217e-01 | 1.020e+00 |
| 当前 `auto` 管线 (基线) | **1.209e-02** | **2.356e+00** |

两点观察:

1. **截面 skew 小的时候, 所有选择的差异都有限**: smooth 面板 (skew=0.005) 上 auto 与 identity 只差 1.2e-02, 因为 auto 选出的 λ≈1.0855 本就接近 1. 这意味着在该类因子上"修 PL-02"对输出几乎无扰动.
2. **截面 skew 大时, 选择变得实质**: skewed 面板 (skew=4.58) 上非 identity 变体与 identity 差 1.0–3.4, 量级与 PL-06 的缩尾缺陷相当. 此时 λ 的取值必须论证, 不能默认.

注: 该合成面板的 skew=4.58 曾被假设为极端情形. **真实 A 股复测 (§3.3.6) 推翻该假设**: 规模/流动性类因子缩尾后 |skew| 中位数 2.80–6.21, 不低于合成值; 收益类 0.87–1.02. 因此 λ 的选择在真实数据上是实质性的, 不是边缘情形.

#### 3.3.4 A 的三个子选项必须分开讨论

| 子选项 | 定义 | 与 B 的关系 | 信息损失 | 适用 |
|--------|------|------------|---------|------|
| A1 `identity` | 恒等 | = B 的 λ=1 | 无 | 截面已近似对称 (\|skew\| 小) |
| A2 `signed_log1p` | `sign(x)·log1p(abs(x))` | YJ 族外 | 压缩极端值, 保号 | 需要固定压缩但拒绝估计 λ |
| A3 rank 映射 | 截面内转分位 (GKX 式, 映射到 (-1,1)) | 与 B 完全不同的族 | **丢弃量纲**, 仅保留位序 | 下游为排序/机器学习输入 |

A3 是 §3 原表中被合并进 A 的一支, 但性质不同: 它是**参数无关的形状校正**, 且比任何固定 λ 更彻底; 代价是丢失量纲, 使下游 OLS 中性化的解释变为"对分位数回归". GKX 的实践 (A 级, §4.3) 正是 A3 路线. 设计文档需要显式回答: 本管线的下游是否允许丢失量纲.

#### 3.3.5 领域惯例: 支持 A 类而非 Box-Cox/YJ

- GKX (2020) 用 rank 映射 + 逐月截面中位数填补 (A 级, 已核原文).
- 检索 (Crossref / WebSearch) **未找到**把 Box-Cox / Yeo-Johnson 用作资产定价因子截面变换的文献; 主流描述为 winsorize + z-score 或 rank (B 级二手总结, 未逐篇核验).
- 这与 §3.3.2 的结构一致: 管线已有缩尾与 z-score, 幂变换在资产定价流程中属非常规组件.

#### 3.3.6 真实 A 股数据复测: 截面 skew 分布

**数据源**: `E:\Ashare_data` (日频, 2020-01-02 – 2026-01-23, T=1470, 截面中位 5064 只, 最少 3741 只). 因子由原始行情与市值构造 (`pl02_probe10.py`), 未做任何前视处理.

| 因子 | 构造 | 缩尾前 \|skew\| 中位 | 缩尾后 \|skew\| 中位 | 缩尾后 p90 | 缩尾后 >1 占比 |
|------|------|---------------------|---------------------|-----------|---------------|
| `market_value` | 总市值 | 16.37 | **4.76** | 5.12 | 100% |
| `log_market_value` | log(市值) | 1.09 | **0.94** | 1.02 | 23.6% |
| `amount` | 成交额 | 7.93 | **3.67** | 4.08 | 100% |
| `turnover_proxy` | 成交额/市值 | 4.21 | **2.80** | 3.24 | 100% |
| `ret_1d` | 日收益 | 3.25 | **1.02** | 1.62 | 51.8% |
| `ret_20d` | 20 日累计收益 | 2.86 | **0.87** | 1.45 | 39.9% |
| `amihud` | \|收益\|/成交额 | 43.26 | **6.21** | 8.40 | 100% |

缩尾口径与 Static 管线一致 (逐日截面 1%/99%). 判定阈值与 `_select_optimal_transform` 相同 (|skew| > 0.5 判为偏斜).

**三个结论**:

1. **真实 skew 不低于合成面板**: 规模与流动性类 (market_value / amount / turnover / amihud) 缩尾后 |skew| 中位 2.80–6.21, **高于** §3.3.3 合成面板的 4.58 水平; 收益类 0.87–1.02. 因此 §3.3.3 的端到端差异 (1.0–3.4) 在真实数据上**是可达到的, 不是极端情形**.
2. **1%/99% 缩尾不足以消除 skew**: market_value 从 16.37 降至 4.76 后仍然强右偏 —— 缩尾只截断尾部, 不改变长尾形状. 这意味着**变换并非可选项**: 在真实数据上, identity 会把 |skew|≈4.8 的输入直接送入中性化.
3. **单一 λ 无法覆盖所有因子族**: log 把市值 skew 从 4.76 压到 0.94 (有效), 但收益类本身已接近对称 (1.02), log 无收益; 若对收益施加 λ=0, 负值会走 YJ 的另一个分支, 语义改变. 因此"全局统一 λ"必然对某族次优.

**设计含义**:

- A1 (`identity`) 在真实数据上**不足**: 四个规模/流动性因子的 |skew| 中位均 >2.5.
- B 的单一先验 λ 也会**按族失配**: 市值类需要 λ≈0, 收益类需要 λ≈1.
- **A3 (rank 映射) 是唯一跨因子族统一的参数无关方案**, 且与 GKX 实践一致; 代价是量纲损失.
- 或者采用"按因子族配置 λ"(B 的分族版本), 但这需要为每个因子族提供先验论证.

**数据质量警告**: `stock_return` 原始范围为 [-96.44, 200400.0], 存在明显脏值 (停牌/复权异常). 上表已用 1%/99% 缩尾; 但脏值的存在意味着真实 skew 中有一部分**来自数据错误而非分布形状**, 设计文档不应把该 skew 全部归因于因子的经济属性. 数据清洗属独立缺陷范围, 不在 PL-02 内.

#### 3.3.7 综合结论: A/B 不是二选一

| 决策层 | 问题 | 证据 | 倾向 |
|--------|------|------|------|
| 1 | A1 (`identity`, =λ=1) 是否足够 | 真实数据: 规模/流动性类缩尾后 \|skew\| 中位 2.80–6.21, 100% 日期 >1 | **不足** |
| 2 | B 的单一先验 λ 是否可行 | log 对市值有效 (4.76→0.94), 对收益类无收益 (1.02→1.02) | **按族失配** |
| 3 | 是否离开 YJ 族 (A2) | `signed_log1p` 与任何单一 λ 不等价; 语义需独立定义 | 可选, 非必要 |
| 4 | A3 (`rank`) 是否纳入 | 跨族统一、参数无关; GKX 实践; 代价是丢量纲 | **最强候选** |

**核心判断**: 在真实因子分布上, "A1 vs B" 的答案不是二选一, 而是**两个都不充分**:

- A1 对规模/流动性族不足 (skew 4.8 直接进入中性化).
- B 的单一 λ 无法同时适配右偏的规模族与近似对称的收益族.

真正的候选是 **A3 (rank)** 或 **B 的分族版本 (按因子族配置 λ)**. 前者参数无关、跨族统一, 但有量纲损失; 后者保留量纲, 但需要为每个因子族提供先验并承担配置维护.

### 3.4 rank 变换: 数学推导与收益分析

§3.3.7 把 A3 (rank) 列为最强候选, 本节给出其数学性质与实测收益.

#### 3.4.1 定义

对 t 日截面 `{x_{i,t}}` (有效值 `N_t` 个), 定义升序秩 (并列取平均秩):

```
R_{i,t} = #{ j : x_{j,t} ≤ x_{i,t} }        R ∈ {1, ..., N_t}
```

取线性映射使值域对称且有界:

```
u_{i,t} = (2·R_{i,t} − N_t − 1) / N_t       u ∈ {−1 + 1/N_t, ..., 1 − 1/N_t}
```

等价写法 `u = 2(R − 0.5)/N − 1`. 端点取 `±(1 − 1/N)` 而非 `±1`, 避免边界点被后续 winsorize/z-score 特殊对待.

**关于 GKX 的公式**: 原文只写 "We cross-sectionally rank all stock characteristics period-by-period and **map these ranks into the [-1,1] interval**" (A 级, 已核), 并注明 "following Kelly, Pruitt, and Su (2019) and Freyberger, Neuhierl, and Weber (2020)", **未给出显式映射公式**. 因此上式是本项目可验证的形式, 不应表述为 "GKX 的公式".

#### 3.4.2 精确矩 (与输入分布无关)

无并列且 X 连续时, 秩均匀分布: `P(R = k) = 1/N`.

```
E[R] = (N+1)/2,        Var(R) = (N²−1)/12
```

代入 `u = (2/N)R − (N+1)/N`:

```
E[u]     = 0                                    (恒等, 任意 N)
Var(u)   = (4/N²)·(N²−1)/12 = (N²−1)/(3N²)
std(u)   = sqrt((N²−1)/(3N²)) → 1/√3 ≈ 0.5774   (N → ∞)
skew(u)  = 0                                    (分布对称, 精确)
κ_ex(u)  = −6(N²+1) / (5(N²−1)) → −6/5 = −1.2    (超额峰度)
```

数值对照:

| N | std(u) | κ_ex(u) |
|---|--------|---------|
| 30 | 0.57703 | −1.20267 |
| 5064 | 0.57735 | ≈ −1.2000 |
| ∞ | 0.57735 | −1.2000 |

**这是 rank 与 YJ/Box-Cox 的本质差别**: u 的前两阶矩 (偏度) 与四阶矩 (峰度) **由构造决定, 不由数据决定**; 而 YJ 的 skew 是 λ 与输入分布的函数, 只能近似为 0.

#### 3.4.3 概率积分变换 (PIT) 解释

`R/N` 是经验 CDF `F̂_N(x)`, 故:

```
u = 2·F̂_N(x) − 1
```

当 N → ∞ 且 X 连续, `F̂_N → F` (Glivenko–Cantelli), 于是 `u` 依分布收敛到 `U(−1, 1)`. 这使 rank 成为 **PIT 的非参数版本**: 用样本自身的经验分布替代理论分布, 目标分布是**均匀**, 而非正态.

| 维度 | YJ / Box-Cox | rank |
|------|-------------|------|
| 目标分布 | 正态 (近似) | 均匀 (极限精确) |
| 参数 | λ (1 个) | 无 |
| 估计方式 | MLE, 依赖样本 | 无估计 |
| 前视风险 | λ 依赖样本 (PL-02 根源) | 结构性为零 |
| 极端值 | 压缩但不消除 | 有界 (\|u\| < 1) |
| 并列敏感 | 否 | 是 (依赖平均秩) |
| 计算 | 迭代优化 | O(N log N) 排序 |

#### 3.4.4 实测: 矩与信息损失

真实 A 股 (T=1470, N 中位 5064, `pl02_probe11.py`):

| 因子 | raw skew / κ_ex | winsor(1/99) | log | **rank** |
|------|-----------------|--------------|-----|----------|
| `market_value` | 16.37 / 357.1 | 4.76 / 25.2 | 1.09 / 1.79 | **0.0000 / −1.2000** |
| `amount` | 7.93 / 97.6 | 3.67 / 15.5 | −0.67 / 2.98 | **0.0000 / −1.2000** |
| `ret_1d` | 3.25 / 65.5 | 1.02 / 3.29 | — | **0.0000 / −1.2000** |
| `ret_20d` | 2.86 / 32.7 | 0.87 / 1.95 | — | **0.0000 / −1.2000** |

rank 在所有四个因子上给出**完全相同**的矩, 与理论值逐位吻合. log 只能部分校正, 且对 `amount` 过度校正 (skew 由正转负).

**信息损失** (逐日截面相关, 中位):

| 因子 | rank vs raw | rank vs winsor | rank vs log |
|------|------------|----------------|-------------|
| `market_value` | P=0.3013, S=1.0000 | P=0.5509, S=1.0000 | P=0.9344, S=1.0000 |
| `amount` | P=0.5268, S=1.0000 | P=0.6602, S=1.0000 | P=0.9356, S=1.0000 |
| `ret_1d` | P=0.7926, S=1.0000 | P=0.8938, S=1.0000 | — |
| `ret_20d` | P=0.8315, S=1.0000 | P=0.9255, S=1.0000 | — |

三个读数:

1. **Spearman 恒为 1.0000**: rank 对排序零损失, 因此 IC / Rank IC **完全不受影响** (§1.2.6 的单调性事实在这里表现为恒等).
2. **Pearson 0.30–0.83**: 线性信息损失显著, 规模类最大 (0.30). 若下游依赖"每单位变化"的线性解释, 这是实质代价.
3. **rank vs log 的 Pearson 0.93**: 对右偏因子, rank 与 log 在值域上高度接近 —— 说明 rank 的"线性化"效果与对数变换同向, 但无需选 λ.

#### 3.4.5 两种目标分布: 均匀 vs 正态

rank 只固定了"序", 目标分布仍可选. 正态版有三种标准偏移, 官方文档一致:

| 名称 | 公式 | 来源 |
|------|------|------|
| van der Waerden | `Φ⁻¹(R/(N+1))` | NIST Dataplot / NAG g01dhc / IBM SPSS |
| **Blom** | `Φ⁻¹((R − 3/8)/(N + 1/4))` | SAS PROC RANK / IBM SPSS / RNOmni 默认 `k=0.375` |
| Tukey | `Φ⁻¹((R − 1/3)/(N + 1/3))` | SAS PROC RANK / IBM SPSS |

均匀版: `u = 2(R − 0.5)/N − 1`.

**v1.6 命名勘误**: 上一版把 `Φ⁻¹((R − 0.5)/N)` 标为 "van der Waerden", 这是错误的 —— 该式是 mid-rank 变体, 与任何标准命名都不对应. 标准 van der Waerden 是 `R/(N+1)`, Blom 是 `(R−3/8)/(N+1/4)`. 三个公式在 N=5064 时的数值差异约 2e-4 量级, 不影响 §3.4.4 的矩结论, 但命名必须准确.

实测 (market_value, `pl02_probe12.py`; 该探针的"正态"版用的是 **mid-rank 变体** `Φ⁻¹((R−0.5)/N)`, 非 Blom):

| 变体 | skew | κ_ex | p0.5 / p99.5 | 截面 std |
|------|------|------|--------------|---------|
| raw | 16.3746 | 357.14 | 63,459 / 38,090,514 | — |
| rank→均匀 | 0.0000 | **−1.2000** | −0.9898 / 0.9902 | 0.5774 (= 1/√3) |
| rank→正态 (mid-rank) | 0.0000 | **−0.0059** | −2.5766 / 2.5766 | — |

mid-rank 正态版的超额峰度 −0.0059 ≈ 0, 分位点精确落在 `Φ⁻¹(0.005) = −2.576`; 两种变体的截面 Pearson 相关 0.9773. 选择依据:

- 下游 OLS 中性化假设残差近正态 → **rank→正态** 更匹配;
- 下游需要严格有界 (防杠杆点) → **rank→均匀**;
- 两者排序完全相同, 差异只在值域尺度与尾部形态.

#### 3.4.6 收益 (量化)

| 收益 | 证据 |
|------|------|
| 矩精确可控, 与输入分布无关 | 4 个真实因子 rank 后恒为 skew=0 / κ_ex=−1.2 (§3.4.4) |
| 极端值完全免疫 | \|u\| < 1 (均匀) 或 \|u\| ≤ Φ⁻¹(1−1/(2N)) ≈ 3.9 (正态); raw 的 p99.5 达 3.8e7 |
| 结构因果, 零前视 | 只用当日截面, 无跨期参数 (§3.4.3) |
| 完全可复现 | 无随机子采样, 无 MLE 收敛路径差异 |
| 零估计误差 | 无参数, 消除 §1.2.3 的 \|Δλ\| 漂移 |
| 跨因子族统一 | 规模/流动性/收益四族全部归零; 单一 λ 做不到 (§3.3.6 结论 3) |
| 成本低 | O(N log N); 单次全 panel YJ 拟合实测 17 ms/5.5 ms 级别, rank 同量级或更低 |
| 排序零损失 | Spearman 恒 1.0000, IC/RankIC 不变 |

#### 3.4.7 代价 (量化)

| 代价 | 证据 / 说明 |
|------|------------|
| 线性信息损失 | 截面 Pearson 0.30–0.83; 规模因子损失最大 (0.30) |
| **并列退化** | `ret_1d` 的逐日 ties 比例中位 **12.27%** (`market_value` 0.07%, `amount` 0.02%, `ret_20d` 0.07%). 大量并列时平均秩使 u 的分布偏离均匀, skew 不再精确为 0 |
| 中性化语义变化 | OLS(y ~ rank(x)) 变为"对分位的回归", 系数不再有"每单位 x"的解释 |
| 尺度变化 | 均匀版 std=0.577, 下游 z-score 会把输出放大约 1/0.577 ≈ 1.73 倍; 需同步检查下游阈值 |
| 无法表达差距 | 两个相差 10 倍的值若秩相邻, 位距相同; 下游若依赖幅度则信息不足 |
| 与 z-score 的叠加 | rank 后 z-score 仍是均匀 (或正态) 形状, 不会"变回"原始分布 |

**并列的定量含义**: 若并列比例 p, 有效秩数约为 `N(1−p)`, 均匀性的偏离随 p 增大. `ret_1d` 的 12.27% 主要来自停牌、涨跌停与价格异常, 属数据质量问题的投影 (§3.3.6 已警告脏值). 对这类因子, rank 与 winsor 应组合使用, 或先清洗再 rank.

#### 3.4.8 与 PL-02 修复的关系

- rank 是**参数无关**变换, 因此天然满足 §6.1 的 T3 (截断不变式) 与 T5 (可复现性), 不需要 λ 调度或重估频率.
- 若采用 rank, `_select_optimal_transform` / `_fit_*` / `auto_optimize` 三条路径可整体移除, 而不是"改造成因果版本".
- 仍需处理: `enabled=False` 契约 (§1.4 第 3 条)、缓存代际 bump (§6.2)、Mixed 的 fit/transform 口径 (§1.4 第 4 条).
- 若采用 rank, A/B/C/D 的讨论在本项目内**大部分失效** —— 这是 rank 作为候选的最强论据, 也是它需要被单独评估的原因.

### 3.5 rank 对中性化语义的影响

§3.4.7 只把"中性化语义变化"列为一行代价. 本节给出其机制、数学形式与实测幅度.

#### 3.5.1 影响范围由管线顺序决定

| 管线 | 顺序 | rank 是否影响中性化 |
|------|------|-------------------|
| Static | imputer → 缩尾 → **中性化** → **变换(rank)** → z-score | **否**. rank 在中性化之后, 中性化输入仍是原始值; 但 z-score 前的值已变 |
| Mixed | imputer → 缩尾 → **变换(rank)** → **中性化** → z-score | **是**. rank 改变中性化输入, 语义随之改变 |

因此下述分析只适用于 **Mixed**, 以及任何"先变换后中性化"的自定义顺序. Static 的中性化不受 rank 影响, 但下游 z-score 与组合权重仍受影响.

#### 3.5.2 数学形式: 行业中性化即组内去均值

当中性化器使用 one-hot 行业哑变量 `D` 时, OLS 残差有闭式解 (Frisch–Waugh–Lovell / 组内估计量):

```
ε_i = x_i − x̄_{g(i)},        x̄_g = (1/|g|)·Σ_{j∈g} x_j
```

因此:

| 输入 | 中性化残差 | 减去的量 |
|------|-----------|---------|
| identity | `ε^x_i = x_i − x̄_{g(i)}` | 行业内**算术均值** (元) |
| rank | `ε^u_i = u_i − ū_{g(i)}` | 行业内**平均秩** (无量纲) |

两者都是"组内中心化", 但中心化的对象不同.

#### 3.5.3 三个层次的语义差异

**(1) 减去的是排名, 不是水平.** `ε^x` 的单位是原始单位 (元), 可直接解释为"行业超额市值"; `ε^u` 的单位是秩位, 只能解释为"行业超额排名".

**(2) 行业间差异被先压缩再消除.** rank 先把跨行业量级差异压到有界区间, 再减去行业均值. 这等价于隐含了一次更激进的行业中性化.

**(3) 残差分布形状被替换.** identity 残差继承原始分布 (强右偏厚尾); rank 残差是有界均匀分布的组内中心化 (近似对称, 峰度接近均匀).

#### 3.5.4 数值例子: 为什么 rank 中性化更激进

设两个行业各有 3 只股票:

```
行业 A: {1, 2, 3}          行业 B: {100, 200, 300}
```

identity 中性化 (组内去均值):

```
A: {−1, 0, 1}              B: {−100, 0, 100}
```

行业内量级差异被完整保留 (A 的跨度 2, B 的跨度 200).

rank 中性化 (全体 6 值排序 → u = {−1, −0.6, −0.2, 0.2, 0.6, 1}):

```
A: u = {−1, −0.6, −0.2},  ū_A = −0.6  →  ε^u = {−0.4, 0, 0.4}
B: u = { 0.2, 0.6, 1 },   ū_B =  0.6  →  ε^u = {−0.4, 0, 0.4}
```

**两个行业的残差完全相同.** 因为 rank 已把"行业间量级差异"编码为"秩的平移", 组内去均值再把该平移消掉. 最终只剩"行业内的相对位置".

这意味着: 对市值这类**行业间量级差异本身有经济含义**的因子, rank 中性化会消除一部分真实信号.

#### 3.5.5 实测 (真实 A 股, Mixed 顺序)

样本: 100 个交易日 (2020-01-02 – 2023-04-11, 受 `stock_ind.pkl` 覆盖限制), 截面中位 4440 只, 31 个行业 (`pl02_probe13.py`).

| 指标 | identity | rank |
|------|----------|------|
| 行业均值离散度 (行业均值的 std) | **4.418e+06** (元) | **0.2703** (秩位) |
| 中性化残差 skew (中位) | **14.4091** | **−0.0188** |
| 中性化残差超额峰度 (中位) | **314.2181** | **−0.9211** |
| 残差标准差 (中位) | 7.185e+06 | 0.5398 |

补充读数:

- **行业解释的秩方差比例** `η² = 1 − (0.5398/0.5774)² = 0.126`: 行业维度解释约 **12.6%** 的 rank 方差. 这说明 rank 之后行业暴露仍然存在且可被中性化, 但强度远低于原始尺度.
- **中性化残差的排序一致性** `Spearman(ε^x, ε^u) = 0.7160` (中位, p5–p95 = 0.6953–0.7471): **约 28% 的排序发生改变**.

最后一行是关键: rank 本身对排序零损失 (§3.4.4 Spearman=1.0), 但 **"rank + 中性化" 的复合操作不是保序的** —— 因为减去的组均值不同. 这直接反驳"rank 只是换个尺度, 排序不变"的直觉.

#### 3.5.6 对因子研究的具体影响

| 影响面 | 说明 |
|--------|------|
| IC / Rank IC | rank 单独使用时不变; 但若 IC 在中性化**之后**计算, 排序一致性 0.716 意味着 IC 会改变 |
| 分组回测 | 中性化后的排序改变 → 分组归属改变; 影响方向取决于因子与行业的交互 |
| 行业中性化力度 | rank 隐含更强的行业中性化: 不仅消除水平差异, 还压缩量级差异 (§3.5.4) |
| 可解释性 | 残差从"行业超额水平"变为"行业超额排名", 研究报告的解释框架需同步修改 |
| 与缩尾的交互 | 缩尾把越界值 clip 到同一端点, **产生并列**, 从而改变 rank. Mixed 中缩尾在 rank 之前, 该交互必须验证 |
| 现有测试 | "残差组均值为 0" 的线性性质对 rank 仍成立, 该类断言不会失败; 但数值断言 (具体残差值) 会失败 |

#### 3.5.7 设计建议

1. **若采用 rank 且保留 Mixed 的 transform→neutralize 顺序**, 必须在文档与代码注释中明确: 中性化语义已从"行业超额水平"变为"行业超额排名", 并重新验证 IC/分组结果.
2. **若希望保持原有中性化语义**, 可把 rank 移到中性化之后 (即采用 Static 的顺序), 或对 rank 后的值不做行业中性化.
3. **对市值等"行业间量级有经济含义"的因子**, rank + 中性化会消除真实信号 (§3.5.4); 这类因子应慎用 rank, 或改用 log 保持量纲.
4. **必须新增测试**: 至少一条断言 `Spearman(ε^identity, ε^rank) < 1`, 以固化"rank 改变中性化结果"这一事实, 防止未来有人误以为两者等价.

### 3.6 决策: 默认变换 = rank→正态 (Blom) + I-INT 顺序

#### 3.6.1 决策

| 项 | 决定 |
|----|------|
| 默认变换 | **rank → 正态 (Blom 偏移)** |
| 映射公式 | `u = Φ⁻¹((R − 3/8) / (N + 1/4))` |
| 并列处理 | `method='average'` (与 RNOmni 默认一致) |
| 执行顺序 | **I-INT**: 先中性化 (取行业残差), 再对残差 rank, 最后 z-score |
| Static | 顺序已符合 (neutralize → transform → z-score), 仅替换变换方法 |
| Mixed | **需把 transform 移到 neutralize 之后** (由 D-INT 改为 I-INT) |
| 保留项 | `identity` 作为 opt-out (需要保留量纲的因子族) |

#### 3.6.2 证据链

| 步骤 | 证据 | 等级 |
|------|------|------|
| INT 优于未变换 | "INT-based tests robustly control the type I error... when the residual distribution exhibits excess skew or kurtosis"; "outperform standard linear regression in terms of power" (RNOmni 官方文档) | A |
| D-INT vs I-INT 无普适最优 | "the relative powers of D-INT and I-INT depend on the underlying data generating process" (McCaw et al., *Biometrics*, DOI 10.1111/biom.13214) | A (preprint 摘要) |
| 本场景匹配 I-INT | "I-INT is most powerful when the phenotype is linear in covariates, but the residual distribution is skewed or kurtotic" (RNOmni vignette); 本项目实测 identity 中性化残差 skew=14.41 / κ_ex=314 (§3.5.5) | A + C |
| Blom 是事实标准 | SAS / SPSS / RNOmni 默认 `k=0.375` | A |
| ties 需谨慎 | "when the underlying distribution is not continuous, the OLS estimator may be highly sensitive to the way in which ties are handled" (arXiv:2310.15512) | A (摘要) |

#### 3.6.3 为什么这个组合消除了 §3.5 的语义冲突

§3.5 的问题是: rank 在**中性化之前**时, 中性化残差从"行业超额水平"变为"行业超额排名", 与 identity 的排序一致性仅 0.716.

选择 I-INT 后, rank 作用于**中性化残差**, 因此:

- 行业暴露已在 rank 之前被剥离;
- rank 只改变残差的边缘分布形状 (使其正态), 不再改变"减去的量";
- §3.5 代价表中"中性化语义变化"一项**不再适用**;
- 但"量纲损失"与"ties 敏感"仍然存在 (它们与顺序无关).

#### 3.6.4 影响面 (实施文档需覆盖)

| 面 | 影响 |
|----|------|
| **Mixed 步骤顺序** | transform 从第 3 步移到第 4 步之后; 所有 Mixed 历史输出改变, 需重新验收 |
| **Static** | 顺序不变, 只替换变换实现; 输出仍改变 (λ→rank) |
| **缓存** | 输出数值改变 → `CODE_VERSION` 必须 bump (§6.2) |
| **可删除代码** | `_select_optimal_transform` / `_fit_yeojohnson` / `_fit_boxcox` / `_fit_quantile` / `_fit_power` / `_fit_log` / `auto_optimize` 的自动选型路径 |
| **配置契约** | `TransformationConfig.method` 需新增 `rank` (输出分布由 `target_distribution` 决定); 名称映射 (T6) 同步更新 |
| **测试** | 移除 PL-02 / PL-04 xfail (T8); 新增 ties 告警测试; 新增 `Spearman(ε^identity, ε^rank) < 1` 不再适用的说明 (因顺序已变) |
| **`enabled=False`** | transformation 仍强制启用 (§1.4 第 3 条); 若需 opt-out, 改用 `method='identity'` |
| **z-score 冗余** | rank→正态后已近似 N(0,1), z-score 几乎无作用; 保留但需注明 |

#### 3.6.5 遗留项 (不阻塞决策, 但需在设计/实施中处理)

1. **ties 告警阈值**: `ret_1d` 实测 ties 12.27%; 建议对 ties > 5% 的因子记录 warning, 不作为硬失败.
2. **脏值**: `stock_return` 存在 200400% 级异常 (§3.3.6); rank 对极端值免疫, 但 ties 会因 clip/停牌增加. 数据清洗属独立缺陷.
3. **N 很小时的稳定性**: 截面股票数 < 30 时, Blom 的最极端值可达 `Φ⁻¹(0.625/30.25) ≈ −2.04`, 尚可; 但更小的 N 需设下限或跳过.
4. **`identity` opt-out 的配置形态**: 是因子级 (`TransformationConfig` 按因子) 还是管线级 (`method='identity'`)? 取决于后续是否接入因子级配置.

**与 ADR-027 的关系**: ADR-027 已决定"所有 `auto` → 固定方法", 但实现层从未落实 (`auto_optimize` 仍覆盖显式方法). PL-02 与 PL-01 一样, 同时是**前视缺陷**与 **ADR-027 实施缺口**. 设计文档需要明确: "固定方法"是否意味着"固定参数", 还是允许因果的参数调度.

### 3.7 实现范围: 宿主与配置面

#### 3.7.1 前提纠正: 旧 transform 路径是逐列 (按股票时序) 的

`X` 是 `pd.DataFrame`, index=日期, columns=股票. 两项直接证据:

- outlier 截面路径用 `X.quantile(..., axis=1)`, 即按行 (日期) 聚合 — [adapters.py L600-L604](../../adapters.py#L600-L604);
- 截面 z-score 用 `result.mean(axis=1)` / `result.std(axis=1)` — [adapters.py L542-L545](../../adapters.py#L542-L545).

但 transformation 的 `transform` 走的是 else 分支:

```python
for col in X.columns:
    col_data = X[col].dropna()
    transformed = self._processor.transform(col_data)
```

[adapters.py L563-L575](../../adapters.py#L563-L575) — 即**按股票列 (时间序列)** 逐列套用.

对 YJ / boxcox / quantile 这类**逐元素**映射, "逐列"与"全 panel"的 apply 结果相同 (参数在 `fit` 阶段已全局确定), 因此该维度错误在 §1.2 的实测矩阵中**不可见** — 它是一个**潜伏缺陷**. rank 是第一个非逐元素方法: 逐列应用会把"截面排秩"变成"每只股票在自己历史上排秩", 语义完全改变.

> 注意区分: §1.2 中 `quantile` 的隔离差值最大 (2.064510e+00), 原因在 **fit**: `n_quantiles = min(1000, n)` 的经验分位网格对全样本敏感, 与 §3.7.1 的 transform 维度无关.

**结论**: rank 不能复用现有 transform 分支, 必须新增截面路径.

#### 3.7.2 三处现存 rank 实现: 登记但不采用

| 位置 | 做法 | 不可用原因 |
|------|------|-----------|
| `AdaptiveTransformer._fit_quantile` (L701) / `_apply_quantile` (L820) ([transformers.py](../../modules/factor_adaptive_winsor/core/transformers.py#L701)) | sklearn `QuantileTransformer(output_distribution=target_distribution, n_quantiles=min(1000, n), random_state=42)` | 全样本 fit (前视, §1.2 差值 2.064510e+00); `n_quantiles` 上限 1000 合并 ties; 逐元素映射, 无截面语义 (与 rank 不同, 维度错误不影响它) |
| `EnhancedRankPreservingScaler._robust_rank_normalize_transform` ([enhanced_transformers.py L446-L469](../../modules/factor_adaptive_winsor/core/enhanced_transformers.py#L446-L469)) | `(rank − 0.5)/n → Φ⁻¹`, 再乘回原始 std、加原始 mean | 输出是"正态形状 + 原始量纲", 非标准正态; 且 method 会被全样本 skewness 自动改写为该方法 ([L355-L357](../../modules/factor_adaptive_winsor/core/enhanced_transformers.py#L355-L357)), 属 PL-02 根因同型 |
| `EnhancedRankPreservingScaler._continuous_rank_normalize_transform` ([enhanced_transformers.py L885-L930](../../modules/factor_adaptive_winsor/core/enhanced_transformers.py#L885-L930)) | KDE + 插值 + `clip(0.01, 0.99)` + 还原原始量纲 | 前视最严重 (KDE 用全样本); `clip` 到 0.99 等于人为设置 `±2.33` 的尾部上限 |

其中后两处所在类 `EnhancedRankPreservingScaler` **从未被任何 pipeline 实例化**; `StandardizationConfig.method='rank'` ([config_v2.py L84](../../config_v2.py#L84)) 同样从未被实例化, 且若实例化会在 `AdaptiveStandardizer.fit` 抛 `ValueError: 未知的标准化方法: rank` ([transformers.py L896-L905](../../modules/factor_adaptive_winsor/core/transformers.py#L896-L905)). 三者均为死代码/死配置.

**决策**: 本次只登记, 不清理 (清理属独立重构, 混入 PL-02 会扩大 review 面并干扰截断不变性的因果归因). 设计文档需在"范围边界"中显式声明它们不属于 PL-02 的修复对象.

#### 3.7.3 实现范围决策

| 项 | 决定 | 理由 |
|----|------|------|
| **实现层** | **transformation 层** (`AdaptiveTransformer`) | 与 §3.6 的 I-INT 一致 (neutralize → transform → z-score); rank 属 PIT / rank-based INT, 是分布变换而非 scale 归一; z-score 保留以精确归一 |
| **method 名** | **`rank`** (单一枚举值) | 不引入 `rank_normal` / `rank_uniform` 两个方法名, 避免配置面与测试矩阵翻倍 |
| **输出分布** | **复用 `target_distribution`** (`normal` / `uniform`) | 该参数已存在于 `AdaptiveTransformer.__init__` ([L501](../../modules/factor_adaptive_winsor/core/transformers.py#L501)), 现仅传给 `_fit_quantile` 的 `QuantileTransformer` ([L716](../../modules/factor_adaptive_winsor/core/transformers.py#L716)); 语义正好是 PIT 目标分布, 对 `quantile` 与 `rank` 同构 |
| **截面路径** | 新增 `ProcessingAdapter._cross_sectional_rank` 分支 | 与 PL-01 的 `_cross_sectional_outlier` ([L379-L380](../../adapters.py#L379-L380)) 及 P0-3 的 `_cross_sectional_zscore` ([L375-L377](../../adapters.py#L375-L377)) 同构; 绕开 §3.7.1 的逐列路径 |
| **rank 状态性** | **无状态**: `fit` 不产生任何参数 | 截断不变性在结构上成立 (逐日截面只依赖当日成员), 不依赖测试兜底 |
| **正态分数** | Blom `Φ⁻¹((R − 3/8)/(N + 1/4))`, 硬编码 | R `rankNorm` / RNOmni 默认 `k=0.375`; 该式下 `mean(u) = 0.5` 精确成立; 三种标准式 (van der Waerden / Blom / mid-rank) 在 N > 100 时端点差异 < 0.2 (相对 ±3.6 约 5%), 且同序, 故不暴露参数 |
| **均匀输出** | `(2R − N − 1)/N`, 即归一化秩 | 与 §3.4.1 的矩推导一致 (`E[u]=0`, `std→1/√3`); 端点 `±(N−1)/N`; 该式在 N=1 时取 0, 无除零风险 |
| **ties** | `method='average'` | 与 scipy / scikit-learn 默认一致, 保序, 不引入伪结构; `ret_1d` 实测 ties 12.27% (§3.6.5 第 1 条) |
| **N 下限** | N < 30 时该日回落截面 z-score, 并 `warning` | Blom 在 N=30 时端点 `Φ⁻¹(0.625/30.25) ≈ −2.04`, 尚可; 更小 N 无意义 |
| **`identity` opt-out** | 维持**管线级** (`method='identity'`) | 不开因子级配置; 与 §6.1 T1 的"显式方法必须生效"同向 |
| **Mixed 顺序** | 按 I-INT 直接切换为 neutralize → transform, **不保留旧路径开关** | 决策已固化 (§3.6.1); 两套顺序长期共存会让 Mixed 的输出口径无法归一, 且与 ADR-027 的"固定方法"方向冲突 |
| **死代码** | 本次不动, 仅登记 (§3.7.2) | 控制 diff 范围与归因清晰度 |

#### 3.7.4 为什么 rank 的截断不变性是结构性的

PL-01 对 outlier 的论证可直接复用: 逐日截面操作**不保存任何跨日统计量**, 因此 `fit` 阶段无参数可泄漏; `transform(t)` 只读取第 `t` 行的值.

rank 更强一层: 连"当日参数"都没有 (排名是纯函数). 形式化地, 令 `A_t` 为第 `t` 日有效样本集合, 则

```
z_i(t) = Φ⁻¹( (rank_i(t) − 3/8) / (|A_t| + 1/4) ),   i ∈ A_t
```

`rank_i(t)` 与 `|A_t|` 都只依赖 `{x_j(t) : j ∈ A_t}`. 因此对任意 `t`,

```
F([0,t] 数据)[t] ≡ F(全样本)[t]
```

恒成立, 无需测试验证 (测试只用于防止未来有人把截面路径改回全局路径).

#### 3.7.5 `target_distribution` 的语义扩展与向后一致性

本次把 `target_distribution` 从"仅 quantile 的输出分布"扩展为"所有 PIT 类变换的输出分布":

| method | `target_distribution='normal'` | `target_distribution='uniform'` |
|--------|-------------------------------|---------------------------------|
| `rank` | Blom 正态分数 | 归一化秩 |
| `quantile` | sklearn `output_distribution='normal'` | sklearn `output_distribution='uniform'` |

两者语义同构 (经验 CDF 的目标分布), 因此复用不产生歧义. 默认值 `'normal'` 保持不变, 现有 `quantile` 行为不变.

**数值对照** (N=4424, 经逐日截面 z-score 后):

- `uniform`: 端点 `±(N−1)/N × √3 ≈ ±1.7317`
- `normal`: 端点 `±3.6324`

与附录 A 中 probe14 实测的 `min_u = −1.7315` / `min_n = −3.6324` 吻合 (uniform 侧经 z-score 放大 `√3` 倍, normal 侧 std 已 ≈ 1, z-score 近似幂等). 两者排序完全相同 (Spearman `= 1.0000`), 差异仅在下游线性合成时可见. 默认 `normal`.

#### 3.7.6 待设计文档确认

1. `rank` 的 `training` 期语义: `fit` 是否需要校验输入为 DataFrame (截面路径依赖 index/columns 语义)? 建议与 PL-01 一致, 强制 `pd.DataFrame`.
2. `N < 30` 的回落目标是截面 z-score 还是 `identity`? 前者保量纲可比, 后者不改变输入; 需与"下游期望 std=1"的契约对齐.
3. ties 告警: 是否在 `fit` 期按日统计 ties 比例并汇总? `fit` 无状态, 告警只能来自 `transform`, 需确定日志频率 (每日一次会刷屏).
4. `TransformationConfig` 是否接入管线 (当前 `PipelineV2Config.transformation` 未传入 Static/Mixed 构造器, §6.2). 若不接入, `method='rank'` 只能通过构造参数设置.

### 3.8 条件性变换: 学术与社区实践证据

**问题**: 是否应按截面分布 (skewness / kurtosis / 正态性检验) **逐期决定**"变换 vs 不变换"?

#### 3.8.1 结论

没有检索到任何学术或开源实践支持"逐期根据分布检验决定是否变换". 所有命中来源都是**固定方法 + 固定参数 + 逐截面应用**, 选型 (若有) 发生在**建模前的一次性决策**中, 且选定后不在预测阶段重选.

#### 3.8.2 证据表

| 来源 | 做法/陈述 | 等级 |
|------|----------|------|
| Peterson & Cavanaugh (2019), *Ordered quantile normalization: a semiparametric transformation built for the cross-validation era*, J. Applied Statistics 47(13-15):2312-2327, DOI 10.1080/02664763.2019.1630372 | ORQ (rank→正态) 是"designed to consistently and effectively transform a vector of arbitrary distribution into a normal distribution"; "In the absence of ties, ORQ normalization is guaranteed to produce normally distributed transformed data"; "we find [it is] the only method that works effectively, regardless of the underlying [distribution]" | **A** (OpenAlex 摘要原文) |
| `bestNormalize` vignette (Peterson) | 选型是一次性建模决策: `bestNormalize(x)` 对整列选一个变换, 之后 `predict(obj, newdata)` 应用到新数据, **预测阶段不重选**; ORQ 在 "left/right skewed data, multimodal data, and even data generated from a Cauchy distribution" 上表现一致 | **A** (官方 vignette 原文) |
| Qlib 文档, `CSRankNorm` | processor 链中**无条件**调用截面 rank 归一化 (`CSRankNorm` 无分布检验分支); 同类 `CSZScoreNorm` 亦无条件 | **A** (官方文档) |
| Gu, Kelly & Xiu (2020) | 固定映射到 `(-1,1)` 区间, 逐月截面, 无条件 | **A** (§4.3 已核) |
| Leeb & Pötscher (2006), *Can one estimate the conditional distribution of post-model-selection estimators?*, Annals of Statistics 34(5):2554-2591, DOI 10.1214/009053606000000821 | 基于同一数据集先选择模型 (AIC 或假设检验) 再估计参数, 其条件分布"impossible to estimate ... with reasonable accuracy even asymptotically"; "no [estimator] can be uniformly consistent (not even locally)" | **A** (OpenAlex 摘要原文) |
| Leeb & Pötscher (2008), *Can one estimate the unconditional distribution of post-model-selection estimators?*, Econometric Theory 24(2):338-376, DOI 10.1017/s0266466608080158 | 无条件分布同样不可一致估计 | **B** (标题 + Crossref 元数据; 未读摘要全文) |

#### 3.8.3 为什么在线条件切换在本场景特别有害

1. **输出是 mixture 分布**: t 日 `identity`、t+1 日 `rank`, 输出边缘分布是两段的混合, 不再有稳定的形状.
2. **日间不可比**: 相邻日期的因子值来自不同变换; 逐日 z-score 只能统一一阶矩, 不能统一形状.
3. **下游统计量分布非标准**: pre-test / post-selection estimator 的分布不可一致估计 (Leeb-Pötscher 2006/2008); rank 化后 IC / Sharpe 的抽样分布会依赖"当日是否触发变换"这一随机事件.
4. **对 rank 而言判断本身无意义**: rank 在无 ties 时**保证**输出正态, 且对 Cauchy 级重尾仍有效 (§3.8.2 前两条). "是否需要变换"的答案恒为"是", 检验只增加噪声.

#### 3.8.4 对本项目的含义

Mixed 的 `conditional_transform` 有三种处置:

| 方案 | 语义 | 代价 |
|------|------|------|
| A 删除 | Mixed 永远 `rank` | 破坏 `mixed.conditional_transform` / `skew_threshold` / `kurt_threshold` 配置契约与 `test_fix2_config_unification` |
| B 保留字段, 语义改为"是否启用 rank" | `True` = `rank`, `False` = `identity`; 删除阈值参数 | 参数名 (`conditional_transform`) 与语义不符; 配置契约保留 |
| C 逐日诊断 | 每日按 skew/kurt 决定 `rank` 或 `identity` | 无任何实践支持; 输出为 mixture; 下游分布非标准 |

**建议**: 若要在 Mixed 保留"关注分布"的设计意图, 应把诊断从**在线决策**降级为**离线审计** — `get_stats()` 输出逐日 skew/kurt 分布供事后检查, 变换本身固定为 `rank`. 这样既不改配置契约, 也不产生 mixture.

**已决策 (2026-10-22)**: 采用**方案 D** — 删除 `conditional_transform` / `skew_threshold` / `kurt_threshold` 三个字段, 改由 `transformation.method` 统一控制 (Static 与 Mixed 共用; 默认 `rank`, `identity` 作为 opt-out). 选择理由: 保留 opt-out 能力, 同时把两条管线收敛为一套配置. 详见 [设计文档](PL02_TRANSFORM_LOOKAHEAD_DESIGN.md) §3 D5 / §4.4.

---

## §4 学术证据

### 4.1 变换参数是样本统计量

| 文献 | 陈述 | 证据 |
|------|------|------|
| Box & Cox (1964), *An Analysis of Transformations*, JRSS B 26(2):211–243, DOI 10.1111/j.2517-6161.1964.tb00553.x | λ 通过似然函数/后验分布推断, 是**样本依赖**的参数; 摘要原文: "Inferences about the transformation and about the parameters of the linear model are made by computing the likelihood function and the relevant posterior distribution." | **A** (Crossref 摘要原文; 页码按 Crossref 元数据, 部分文献引作 211–252) |
| Yeo & Johnson (2000), *A new family of power transformations to improve normality or symmetry*, Biometrika 87(4):954–959, DOI 10.1093/biomet/87.4.954 | 支持负值的幂变换族; λ 同样由样本估计 | **A** (Crossref 元数据) / **B** (内容概括) |
| Hyndman & Athanasopoulos (2021), *Forecasting: Principles and Practice* (3rd ed.), §3.1 | Box-Cox 的 λ "a good value of λ is one which makes the size of the seasonal variation about the same across the whole series"; λ 由数据选择 | **A** (官方在线版原文) |
| scikit-learn, `PowerTransformer` 文档 | "The optimal parameter for stabilizing variance and minimizing skewness is estimated through maximum likelihood." | **A** (官方文档原文) |

### 4.2 泄漏与训练/测试隔离

| 文献/文档 | 陈述 | 证据 |
|-----------|------|------|
| Kaufman, Rosset, Perlich & Stitelman (2012), *Leakage in Data Mining*, ACM TKDD, DOI 10.1145/2382577.2382579 | 泄漏是引入"不应合法可用于挖掘"的信息; 提出 learn-predict separation | **A** (摘要原文, 已在 PL-01 核验) |
| Kapoor & Narayanan (2023), *Leakage and the reproducibility crisis in machine-learning-based science*, Patterns, DOI 10.1016/j.patter.2023.100804 | L1 要求: "the test set does not interact with training data during any of the preprocessing, modeling or evaluation steps to ensure a clean train-test separation" | **A** (arXiv:2207.07048 预印本原文; 正式版 DOI 已核) |
| Hyndman & Athanasopoulos (2021), §5.10 | 时间序列 CV 的训练集 "consists only of observations that occurred prior to the observation that forms the test set. Thus, no future observations can be used in constructing the forecast"; 全样本拟合的 residuals "are based on a model fitted to the entire data set, rather than being true forecasts" | **A** (官方在线版原文) |
| scikit-learn, *Common pitfalls*, §12.2 (Data leakage) | "Always split the data into train and test subsets first, particularly before any preprocessing steps"; "Never include test data when using the fit and fit_transform methods. Using all the data, e.g., fit(X), can result in overly optimistic scores." | **A** (官方文档原文) |
| Arnott, Harvey & Markowitz (2019), *A Backtesting Protocol in the Era of Machine Learning*, JFDS, DOI 10.3905/jfds.2019.1.064 | 回测流程需要信息隔离, 避免研究决策使用未来信息 | **A** (Crossref 元数据; 摘要为 SSRN 版, 已在 PL-01 核验) |
| Lopez de Prado (2018), *Advances in Financial Machine Learning*, Wiley | Purged K-Fold / 时序交叉验证; 预处理须在训练折内完成 | **B** (保守引用, 未逐章核验) |

### 4.3 资产定价中的截面预处理实践

| 文献 | 陈述 | 证据 |
|------|------|------|
| Gu, Kelly & Xiu (2020), *Empirical Asset Pricing via Machine Learning*, RFS 33(5):2223–2273, DOI 10.1093/rfs/hhaa009 | "Another issue is missing characteristics, which we replace with the cross-sectional median at each month for each stock, respectively."; "Our data transformation normalizes characteristics to the (-1,1) interval." | **A** (论文 PDF 原文) |
| 同上 | 训练/验证/测试按时间顺序切分: "we divide our sample into three disjoint time periods that maintain the temporal ordering of the data... the parameters are estimated from the training data alone" | **A** (论文 PDF 原文) |

GKX 的做法说明: 资产定价中的常见预处理是**逐月截面**的缺失填补与固定映射 (rank 到 (-1,1)), 而不是在整块 T×N 面板上估计一个全局变换参数. 这与 PL-01 的"逐日截面缩尾"、ADR-029 的"逐日截面 Z-Score"同构.

### 4.4 流式/增量变换

| 文献 | 陈述 | 证据 |
|------|------|------|
| Tieppo, Barddal & Nievola (2022), *Improving Data Stream Classification using Incremental Yeo-Johnson Power Transformation*, IEEE SMC 2022, pp. 3286–3292, DOI 10.1109/SMC53654.2022.9945302 | 流式场景需要处理无限连续数据流; 提出增量 YJ 变换, "supports streaming data via statistical sampling and hypothesis testing", 且达到与批量版本相同的正态性 | **B** (作者主页摘要; Crossref 元数据已核) |

该文提供的是"增量/在线拟合"的技术可行性证据, 不等同于金融面板的因果性证明; 但它支持方案 C 的工程形态.

---

## §5 社区与工程实践

| 来源 | 做法/陈述 | 证据 |
|------|----------|------|
| Stack Overflow Q68342378, *How to do Yeo Johnson feature normalization on test data?* | 回答: "`fit_transform()` is performed on the train set and compute the lambda and scaling function. Once they are computed, you can use the `transform()` function to apply this transformation on the test set." | **A** (API 全文) |
| Stack Overflow Q56707471, *How do I correctly use a Scaler while using GridSearchCV with TimeSeriesSplit* | 回答: 使用 `Pipeline([('scale', StandardScaler()), ('clf', SVR())])` 放进 `GridSearchCV`, 让缩放器在每折训练集内拟合 | **A** (API 全文) |
| Quant SE Q85733, *Is there existing work on detecting look-ahead bias by perturbing future data and re-running the feature pipeline?* | 回答确认该检验 "catches temporal leakage inside your feature construction"; 与本项目截断不变式测试同构 | **A** (API 全文) |
| scikit-learn, *Common pitfalls*, §12.2 | 数据泄漏定义 + 预处理泄漏示例 + 只在训练集 `fit` | **A** (官方文档原文) |
| scikit-learn, `PowerTransformer` | λ 由最大似然估计; `fit` 学习参数, `transform` 应用参数 | **A** (官方文档原文) |

**工业含义**: 主流实现 (sklearn) 把变换参数视为"训练集估计、全数据应用"的对象; 在时间序列/面板场景中, "训练集"必须替换为"t 时刻及以前的历史". 当前实现的 `fit` 把整个 panel 当作训练集, 与这一原则冲突.

---

## §6 对设计/实施的约束

### 6.1 必须新增/修改的测试契约

| 编号 | 契约 | 说明 |
|------|------|------|
| T1 | 显式 `method` 必须生效 | `auto_optimize=True` 不得覆盖非 `auto` 的显式方法; 覆盖行为要么删除, 要么改为显式 opt-in |
| T2 | `auto` 的解析必须在构造期固定或因果化 | 不得在 `fit` 时依赖全样本特征做方法选择 |
| T3 | 每种方法的截断不变式 | identity / log / YJ / boxcox / power / quantile / rank 分别验证 `n_diff=0` (或明确登记已知差异). rank 的成立是**结构性**的 (无状态 + 逐日截面), 测试只用于防止回归到全局路径 (§3.7.4) |
| T4 | 参数调度因果性 | 若采用扩展/滚动 λ, 验证 `λ_t` 只使用 `[0,t]`; 截断前后每个日期的 λ 相同 |
| T5 | 可复现性 | 同一输入多次 `fit` 必须选出同一方法; Shapiro 子采样必须设固定 seed 或改为确定性检验 |
| T6 | 配置名映射 | `box_cox` / `yeo_johnson` / `none` 必须映射到实现层名称, 或在配置层拒绝; 新增 `rank` 时两侧使用同一名称 (§3.7.3) |
| T7 | Mixed 的 fit/transform 口径 | 诊断、拟合、变换必须使用同一缩尾口径 (与 PL-06 联动) |
| T8 | 端到端 | PL-02 修复后移除 `test_pipeline_truncation_invariance.py` 的 PL-02 与 PL-04 xfail; PL-06/PL-07 保持登记 |

### 6.2 需要同步的兼容面

- **缓存**: 输出数值改变 → `CODE_VERSION` 必须 bump, 否则旧缓存会被当作有效 (参见 PL-01 的缓存代际修复).
- **测试**: [test_adaptive_transformer_identity.py](../../tests/unit/test_adaptive_transformer_identity.py) 现有断言围绕 `auto` 选型; 若改变 `auto_optimize` 语义, 需同步.
- **`enabled=False` 契约**: [test_module_enabled.py L79-120](../../tests/test_adapters/test_module_enabled.py#L79-L120) 固化"transformation 不可消融"; 若设计允许关闭, 需显式修改.
- **配置接线**: `PipelineV2Config.transformation` 目前未传入 Static/Mixed 构造器; 设计需要决定是否接线.
- **性能预算**: 若采用 C, 重估频率 (月/季/年) 必须写入设计; 若采用 D, 需给出 N 的下限与大 N 性能基准.

### 6.3 范围边界

| 项 | 是否在 PL-02 内 | 说明 |
|----|----------------|------|
| Static 端到端残留 (PL-04) | 是 (应随 PL-02 关闭) | 登记值 4.720e-05, 仅由变换构成 |
| Mixed 全样本缩尾 (PL-06) | 否 | `_compute_winsorize_params` 独立缺陷; 关闭缩尾后 Mixed 差异从 2.906e-01 降至 2.082e-02 |
| Mixed `_diagnose_transform_need` 全样本 | 否 | 属 PL-06 的触发条件; 但会与 PL-02 叠加 |
| Dynamic AR 样本内 `fitted_values` (PL-05) | 否 | 独立缺陷 |
| 顶层指纹路由依赖全样本 (PL-07) | 否 | 路由决策本身是前视源 |
| 标准化 `robust/min_max/quantile` | 否 | 已知未登记, 无生产路径使用 (见 PL-03/ADR-029) |

---

## §7 未决问题 (留给设计文档)

1. **固定方法 vs 自适应**: Static / Mixed 是否接受"固定方法 + 固定参数"? 若接受, 选哪个方法 (identity / log / YJ)? 若需要自适应, 是否采用扩展窗口 λ 调度? 证据见 §3.1: 无直接对照实验; FPP3 的 λ 不敏感性支持 B, De Gaetano (2018) 的"常量参数假设被拒"说明存在 B 失效的因子族. 注意 B 的 λ 必须是先验给定, 不能由本数据集估计后冻结. **A1 (identity) 与 B 的 λ=1 完全等价 (实测 8.9e-16), 故该问题应改写为"λ 取什么"而非"A 还是 B"; 真实 A 股复测表明 A1 与单一 λ 均不充分, 见 §3.3.7**.
2. **重估频率**: 若采用 C, 月/季/年重估的统计依据与成本预算是多少? 早期样本不足时回退到 identity 还是跳过变换? 窗口选择可引 §3.2.3 (Pesaran-Timmermann 2007; Inoue-Jin-Rossi 2017; Hännikäinen 2016 支持扩展窗口); 触发条件建议先测 §3.2.5 的信噪比 ρ, 而非引入 regime 判别器.
3. **逐日截面 λ (D)**: 是否需要作为可选项保留? 若保留, 只在 N≥某阈值时启用?
4. **Mixed 的触发条件**: `_diagnose_transform_need` 是否改为逐日/扩展窗口? 与 PL-06 的缩尾修复如何排序?
5. **配置契约**: `TransformationConfig` 的方法名如何统一? 是否允许 `none` 关闭变换? `enabled=False` 是否仍然无效? **部分已决策 (见 §3.7.3): 新增 `method='rank'`, 输出分布复用 `target_distribution`; `identity` 维持管线级 opt-out. 名称映射 (T6) 与 `enabled=False` 契约仍待设计文档处理.**
6. **缓存代际**: 采用不同方案时输出变化幅度不同, 但都需要 bump; 具体版本号在实施文档确定.
7. **API 形态**: 若采用 C/D, `fit/transform` 的批量 API 是否保持? 需要在 `fit` 内生成调度表, 还是新增 `fit_transform` 的时序路径?
8. **因子族差异化**: 真实数据 (§3.3.6) 表明规模/流动性因子需 λ≈0、收益类需 λ≈1; 是采用 A3 (rank, 跨族统一但丢量纲), 还是按因子族配置 λ (保留量纲但需逐族先验)? 前者见 §3.4: 矩精确归一 (skew=0 / κ_ex=−1.2), 但截面 Pearson 损失 0.30–0.83, 且 `ret_1d` ties 达 12.27%. **已决策 (见 §3.6): 默认 rank→正态 (Blom), `identity` 作为 opt-out.**
9. **rank 与中性化的顺序**: 若采用 rank, 必须决定它在中性化之前还是之后. Mixed 当前是 transform→neutralize, 实测中性化残差排序与 identity 仅 0.716 一致 (§3.5.5) → 语义已变为"行业超额排名". **已决策 (见 §3.6): 采用 I-INT (先中性化再 rank), Mixed 需调整步骤顺序.**

---

## §8 参考文献

| # | 文献 | 标识 | 用途 | 证据 |
|---|------|------|------|------|
| 1 | Box, G. E. P. & Cox, D. R. (1964). An Analysis of Transformations. *JRSS B* 26(2):211–243. | DOI 10.1111/j.2517-6161.1964.tb00553.x | λ 的似然估计与样本依赖性 | A |
| 2 | Yeo, I.-K. & Johnson, R. A. (2000). A new family of power transformations to improve normality or symmetry. *Biometrika* 87(4):954–959. | DOI 10.1093/biomet/87.4.954 | 支持负值的幂变换 | A/B |
| 3 | Hyndman, R. J. & Athanasopoulos, G. (2021). *Forecasting: Principles and Practice* (3rd ed.). | otexts.com/fpp3 | Box-Cox λ 选择; §5.10 时序 CV | A |
| 4 | Gu, S., Kelly, B. & Xiu, D. (2020). Empirical Asset Pricing via Machine Learning. *RFS* 33(5):2223–2273. | DOI 10.1093/rfs/hhaa009 | 逐月截面缺失填补与 (-1,1) 归一化; 时序训练/验证/测试 | A |
| 5 | Kaufman, S., Rosset, S., Perlich, C. & Stitelman, O. (2012). Leakage in Data Mining. *ACM TKDD*. | DOI 10.1145/2382577.2382579 | 泄漏定义 | A |
| 6 | Kapoor, S. & Narayanan, A. (2023). Leakage and the reproducibility crisis in machine-learning-based science. *Patterns*. | DOI 10.1016/j.patter.2023.100804 | L1 预处理隔离 | A |
| 7 | Arnott, R., Harvey, C. R. & Markowitz, H. (2019). A Backtesting Protocol in the Era of Machine Learning. *JFDS*. | DOI 10.3905/jfds.2019.1.064 | 回测信息隔离 | A |
| 8 | Tieppo, E., Barddal, J. P. & Nievola, J. C. (2022). Improving Data Stream Classification using Incremental Yeo-Johnson Power Transformation. *IEEE SMC 2022*:3286–3292. | DOI 10.1109/SMC53654.2022.9945302 | 增量/在线 YJ | B |
| 9 | Lopez de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley. | 书目信息 (未逐章核验) | Purged CV / 预处理隔离 | B |
| 10 | scikit-learn. `PowerTransformer`; *Common pitfalls* §12. | scikit-learn.org/stable | λ 的 MLE; 预处理只能在训练集 fit; 无 `partial_fit` | A |
| 11 | Guerrero, V. M. (1993). Time-series analysis supported by power transformations. *Journal of Forecasting* 12(1):37–48. | DOI 10.1002/for.3980120104 | 方差稳定化变换选择 (FPP3 的 `guerrero` 实现对整序列选一个 λ) | A |
| 12 | Zanotti, M. (2025). On the retraining frequency of global models in retail demand forecasting. *Machine Learning with Applications* 22:100769. | DOI 10.1016/j.mlwa.2025.100769; arXiv:2505.00356 | 重估频率的精度-成本权衡 | A |
| 13 | De Gaetano, D. (2018). Forecast Combinations in the Presence of Structural Breaks: Evidence from U.S. Equity Markets. *Mathematics* 6(3):34. | DOI 10.3390/math6030034 | 常量参数假设被拒; 扩展窗口劣于近期加权 | A |
| 14 | Artemova, M., Blasques, F., Koopman, S. J. & Zhang, Z. (2021). On the Use of Flexible Rolling-Window Estimation for Macroeconomic Forecasting. SSRN. | DOI 10.2139/ssrn.3766336 | 滚动窗口在误设/突变下改善预测 | B |
| 15 | Hamilton, J. D. (1989). A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle. *Econometrica* 57(2), 起始页 357. | DOI 10.2307/1912559 | Markov switching 与滤波推断 | B (Crossref 元数据; 页码仅起始页) |
| 16 | Bai, J. & Perron, P. (1998). Estimating and Testing Linear Models with Multiple Structural Changes. *Econometrica* 66(1), 起始页 47. | DOI 10.2307/2998540 | 多结构突变估计与检验 (离线) | B (Crossref 元数据) |
| 17 | Chu, C.-S. J., Stinchcombe, M. & White, H. (1996). Monitoring Structural Change. *Econometrica* 64(5), 起始页 1045. | DOI 10.2307/2171955 | 在线监测结构变化的奠基文献 | B (Crossref 元数据) |
| 18 | Pesaran, M. H. & Timmermann, A. (2007). Selection of estimation window in the presence of breaks. *J. Econometrics* 137(1):134–161. | DOI 10.1016/j.jeconom.2006.03.010 | 断点下估计窗口的偏差-方差权衡 | A (Crossref 元数据) |
| 19 | Inoue, A., Jin, L. & Rossi, B. (2017). Rolling window selection for out-of-sample forecasting with time-varying parameters. *J. Econometrics* 196(1):55–67. | DOI 10.1016/j.jeconom.2016.03.006 | 时变参数下的窗口选择 | A (Crossref 元数据) |
| 20 | Hännikäinen, J. (2016). Selection of an Estimation Window in the Presence of Data Revisions and Recent Structural Breaks. *J. Econometric Methods* 6(1). | DOI 10.1515/jem-2015-0021 | 断点后扩展窗口往往最准 | A (Crossref 摘要) |
| 21 | Rodriguez-Rondon, G. (2024). Underlying Core Inflation with Multiple Regimes. | arXiv:2411.12845 | 结构突变离线 vs Markov switching 实时 | A (摘要原文) |
| 22 | Horvath, L., Trapani, L. & Wang, S. (2024). Sequential monitoring for explosive volatility regimes. | arXiv:2404.17885 | 在线监测的检测延迟分布 | A (摘要原文) |
| 23 | *Algorithmic Monitoring: Measuring Market Stress with Machine Learning* (作者未核). | arXiv:2602.07066 | 截面标准差/偏度/峰度作为市场压力监测指标 | B (搜索摘要, 未读原文) |
| 24 | McCaw, Z. R., Lane, J. M., Saxena, R., Redline, S. & Lin, X. Operating characteristics of the rank-based inverse normal transformation for quantitative trait analysis in genome-wide association studies. *Biometrics*. | DOI 10.1111/biom.13214; 预印本 10.1101/635706 | D-INT / I-INT / O-INT 的定义与相对功效 | A (预印本摘要原文 + 正式版 DOI) |
| 25 | McCaw, Z. R. *RNOmni: Rank Normal Transformation Omnibus Test* (CRAN, v1.0.1.2). | cran.r-universe.dev/RNOmni | INT 定义、`k=0.375` (Blom) 默认、`ties.method='average'` | A (官方包文档原文) |
| 26 | *Inference for Rank-Rank Regressions*. | arXiv:2310.15512 | 秩回归对 ties 处理高度敏感 | A (摘要原文) |
| 27 | Peterson, R. A. & Cavanaugh, J. E. (2019). Ordered quantile normalization: a semiparametric transformation built for the cross-validation era. *Journal of Applied Statistics* 47(13-15):2312–2327. | DOI 10.1080/02664763.2019.1630372 | ORQ (rank→正态) 对任意分布有效; 无 ties 时保证输出正态 | A (OpenAlex 摘要原文) |
| 28 | Peterson, R. A. (2021). Finding Optimal Normalizing Transformations via bestNormalize. *The R Journal*. | RJ-2021-041 | 选型为一次性建模决策, 预测阶段不重选; ORQ 在 skew/multimodal/Cauchy 上表现一致 | A (官方 PDF/vignette 原文) |
| 29 | Leeb, H. & Pötscher, B. M. (2006). Can one estimate the conditional distribution of post-model-selection estimators? *Annals of Statistics* 34(5):2554–2591. | DOI 10.1214/009053606000000821 | 先选模型再估计, 条件分布不可一致估计 | A (OpenAlex 摘要原文) |
| 30 | Leeb, H. & Pötscher, B. M. (2008). Can one estimate the unconditional distribution of post-model-selection estimators? *Econometric Theory* 24(2):338–376. | DOI 10.1017/s0266466608080158 | 无条件分布同样不可一致估计 | B (标题 + Crossref 元数据) |
| 31 | Microsoft Qlib 文档, `CSRankNorm` / `CSZScoreNorm`. | qlib.readthedocs.io/en/stable/component/data.html | 截面 rank 归一化无条件执行, 无分布检验分支 | A (官方文档) |

---

## 附录 A: 探针脚本与原始输出

探针脚本均位于 `C:\Users\Peng\AppData\Local\Temp\` (不进入仓库):

| 脚本 | 用途 |
|------|------|
| `pl02_probe.py` | 选型/λ 基线; 显式方法覆盖; 方法翻转 (偏移/厚尾) |
| `pl02_probe2.py` | 逐方法泄漏; 200 面板 λ 漂移; Mixed 诊断 |
| `pl02_probe3.py` | 未来最小值导致的 log/boxcox offset 泄漏 |
| `pl02_probe4.py` | 逐日截面 λ 稳定性与成本 |
| `pl02_probe5.py` | Spearman/Pearson 敏感性 |
| `pl02_probe6.py` | Mixed 端到端中缩尾与变换的贡献拆分 |
| `pl02_probe7.py` | Shapiro 子采样导致的选型不可复现 |
| `pl02_probe8.py` | 逐日 λ 序列的 regime 持续性 (ACF / AR(1) / Chow / sup-F) 与三种 λ 预测器的 RMSE |
| `pl02_probe9.py` | YJ 恒等式验证 (λ=1≡identity, λ=0≠signed_log1p); A 子选项 vs B 固定 λ 在 Static 上的端到端差异 |
| `pl02_probe10.py` | 真实 A 股 (`E:\Ashare_data`) 7 个因子的逐日截面 skew 分布, 缩尾前/后 |
| `pl02_probe11.py` | rank 变换的矩 (skew / 超额峰度) 与相对 raw/winsor/log 的截面相关; ties 比例 |
| `pl02_probe12.py` | rank→均匀 vs rank→正态 (van der Waerden) 的矩与分位对比 |
| `pl02_probe13.py` | rank 对行业中性化语义的影响: 行业均值离散度、残差矩、残差排序一致性 |

关键原始输出 (节选):

```
[A] seed=11 smooth: full=yeojohnson lam=[1.08547326] | trunc=yeojohnson lam=[1.08620139]
    n_diff=1798/1800 max=8.506103e-04

[B] identity: n_diff=0; log: 0; yeojohnson: 1798 max=8.506e-04;
    boxcox: 1800 max=2.319e-02; power: 1800 max=1.576e-02; quantile: 1799 max=2.065e+00

[C] regime shift: full=yeojohnson (lam=0.5416), trunc=identity, max=1.736441
    heavy-tail future: full=yeojohnson (lam=0.8736), trunc=identity, max=3.916e-01
    200 panels: flips=0/200; |Δλ| median=5.09e-02 p95=2.666e-01 max=4.681e-01

[D] Mixed default max=2.905632e-01; winsorizer off max=2.082468e-02

[E] log offset 13.6611 vs 3.2514 -> max=2.076e+01; boxcox -> 9.094e+00;
    yeojohnson lam 1.6369 vs 0.9514 -> 2.401e+00

[F] 10000-point same input, 20 fits (unseeded Shapiro subsample -> counts vary per run):
    run1: 8 yeojohnson / 12 identity; p in [0.00064, 0.83563]
    rerun (review): 12 yeojohnson / 8 identity; p in [0.00087, 0.47083]

[G] regime persistence of per-day lambda (T=100, N=30):
    smooth seed=11: lam std=0.0056  ACF1=-0.0944  AR1 R2=0.0091  Chow p=1.60e-01  supF min p=9.25e-02
    skewed seed=23: lam std=0.2515  ACF1=-0.2263  AR1 R2=0.0514  Chow p=9.92e-01  supF min p=3.53e-01
    ar_low seed=22: lam std=0.2890  ACF1= 0.0334  AR1 R2=0.0012  Chow p=8.33e-01  supF min p=5.17e-02
    predict lam_t RMSE (expand-mean | fixed lam=1 | full-sample mean):
      smooth 0.0055 | 0.0860 | 0.0055
      skewed 0.2506 | 1.8183 | 0.2471
      ar_low 0.2760 | 0.2710 | 0.2714

[H] A/B identity checks (10000 points incl. negatives):
    YJ lam=1 vs identity     max|diff| = 8.882e-16
    YJ lam=0 vs signed_log1p max|diff| = 6.882e+01   (NOT equivalent)
    YJ lam=2 neg-branch vs -log(1-x) max|diff| = 0.000e+00

[H] Static end-to-end vs identity (mid skew: smooth 0.0050 / skewed 4.5788):
    signed_log1p 3.348e-01 | 1.774e+00
    lam=0.5      4.739e-01 | 2.601e+00
    lam=0.25     6.781e-01 | 3.420e+00
    lam=1.5      5.217e-01 | 1.020e+00
    auto (baseline) 1.209e-02 | 2.356e+00

[I] real A-share daily cross-sectional |skew| (T=1470, N median 5064, 2020-01-02..2026-01-23)
    factor              raw|skew|med  winsor(1/99)|skew|med  winsor>1 share
    market_value        16.3746       4.7621                 1.000
    log_market_value     1.0926       0.9365                 0.236
    amount               7.9330       3.6688                 1.000
    turnover_proxy       4.2122       2.7960                 1.000
    ret_1d               3.2485       1.0247                 0.518
    ret_20d              2.8634       0.8717                 0.399
    amihud              43.2631       6.2094                 1.000
    note: stock_return raw range [-96.44, 200400.0] -> contains dirty values

[J] rank moments + information loss (real A-share, T=1470, N median 5064)
    factor          variant   |skew|med  skew_med  exkurt_med
    market_value    raw        16.3746   16.3746    357.1395
    market_value    winsor      4.7621    4.7621     25.2292
    market_value    log         1.0926    1.0926      1.7894
    market_value    rank        0.0000    0.0000     -1.2000
    amount          raw         7.9330    7.9330     97.6362
    amount          winsor      3.6688    3.6688     15.4603
    amount          log         0.6703   -0.6663      2.9822
    amount          rank        0.0000   -0.0000     -1.2000
    ret_1d          raw         3.2485    3.0874     65.4870
    ret_1d          winsor      1.0247    1.0181      3.2900
    ret_1d          rank        0.0000   -0.0000     -1.2000
    ret_20d         raw         2.8634    2.8634     32.7362
    ret_20d         winsor      0.8717    0.8717      1.9482
    ret_20d         rank        0.0000    0.0000     -1.2000
    cross-sectional corr (median): rank vs raw / winsor / log
      market_value  P=0.3013 S=1.0000 | P=0.5509 S=1.0000 | P=0.9344 S=1.0000
      amount        P=0.5268 S=1.0000 | P=0.6602 S=1.0000 | P=0.9356 S=1.0000
      ret_1d        P=0.7926 S=1.0000 | P=0.8938 S=1.0000 | -
      ret_20d       P=0.8315 S=1.0000 | P=0.9255 S=1.0000 | -
    ties ratio (median): market_value 0.0007 | amount 0.0002 | ret_1d 0.1227 | ret_20d 0.0007

[K] rank -> uniform vs rank -> normal (market_value, T=1470)
    raw            |skew|med=16.3746 exkurt=357.1395  p0.5=63458.8      p99.5=38090514.0
    rank_uniform   |skew|med= 0.0000 exkurt=-1.2000   p0.5=-0.9898      p99.5=0.9902   std=0.5774
    rank_normal    |skew|med= 0.0000 exkurt=-0.0059   p0.5=-2.5766      p99.5=2.5766
    uniform vs normal cross-sectional Pearson median = 0.9773

[L] rank effect on industry neutralization (real A-share, 100 days, 31 industries)
    ind_disp_x (std of industry means, raw)   = 4.418e+06  [p5 3.851e+06, p95 5.411e+06]
    ind_disp_u (std of industry means, rank)  = 0.2703     [p5 0.2642,    p95 0.2788]
    skew(eps_identity) = 14.4091 | skew(eps_rank) = -0.0188
    kurt(eps_identity) = 314.2181 | kurt(eps_rank) = -0.9211
    Spearman(eps_identity, eps_rank) = 0.7160 [p5 0.6953, p95 0.7471]
    resid_std: identity 7.185e+06 | rank 0.5398  -> eta^2 = 1-(0.5398/0.5774)^2 = 0.126
```

## 附录 B: MCP 检索记录与失败说明

| 工具 | 查询 | 结果 |
|------|------|------|
| `mcp_stackexchange_search_questions` | 复合查询 (stats) | 多次返回 0; 改用简单查询后命中 time-series Box-Cox 相关问题 |
| `mcp_stackexchange_search_questions` | `PowerTransformer leakage` (stackoverflow) | 命中 Q68342378 |
| `mcp_stackexchange_search_questions` | `data leakage train test split transform` | 命中 Q56707471 |
| `mcp_stackexchange_search_questions` | `look ahead bias preprocessing` (quant) | 命中 Q85733 / Q60503 |
| `mcp_paper-search_search_crossref` | Box & Cox / Yeo-Johnson / GKX | 元数据命中; Box & Cox 页码以 Crossref 为准 |
| `mcp_paper-search_search_semantic` | 多个查询 | 部分返回空; 不作为唯一证据源 |
| `mcp_paper-search_read_semantic_paper` | ARXIV:1807.00357 | **映射错误**: 返回 CrI3 物理论文; 已放弃该路径, 改用标题检索 + DOI + PDF 原文 |
| `WebFetch` | FPP3 §5.10 / sklearn Common pitfalls / sklearn PowerTransformer | 官方原文命中 |
| `WebFetch` + `pypdf` | GKX PDF / Kapoor 预印本 | 原文段落命中 |
| `mcp_paper-search_search_semantic` | "Box-Cox transformation" 等 4 次 (v1.2 追加 §3.1) | **全部返回空**; 未作为证据源 |
| `mcp_stackexchange_search_questions` | `Box-Cox lambda` (stats) | 返回 15 条, 但 `quota_remaining: -1`; 结果与重估频率无关 |
| `WebFetch` + StackExchange REST | `q=box cox time series lambda` (stats); `q=refit preprocessing parameters walk forward` (stats); `q=rolling normalization time series lookahead` (quant) | 后者 0 条; 前两者无相关问题 |
| `WebFetch` + OpenAlex | Box-Cox lambda estimation uncertainty | 命中 825 篇, 无重估频率对照实验; 未作为论据 |
| `WebFetch` + arXiv API | `all:"power transformation" AND all:"time series"` | 11 条, 无重估频率研究 |
| `WebSearch` | retraining frequency / expanding vs fixed window / point-in-time feature engineering | 定位 Zanotti (2025) 与 De Gaetano (2018); 其余为博客与厂商页 (B/C 级, 未采用) |
| `WebFetch` (Crossref DOI) | 10.1002/for.3980120104 / 10.1016/j.mlwa.2025.100769 / 10.3390/math6030034 / 10.2139/ssrn.3766336 | 摘要原文命中, 用于 §3.1 的 A/B 级判定 |
| `mcp_paper-search_search_crossref` | Bai & Perron / Pesaran & Timmermann / Inoue-Jin-Rossi / Chu-Stinchcombe-White | 元数据与卷期命中 (§3.2.3) |
| `WebFetch` (Crossref DOI) | 10.2307/1912559 / 10.2307/2998540 / 10.2307/2171955 / 10.1016/j.jeconom.2006.03.010 / 10.1016/j.jeconom.2016.03.006 / 10.1515/jem-2015-0021 | 元数据命中; 三篇 Econometrica 旧文 Crossref 仅提供起始页 |
| `WebFetch` (arXiv) | 2411.12845 / 2404.17885 | 摘要原文命中 (离线 vs 实时; 检测延迟分布) |
| `WebSearch` | real-time structural break / regime detection delay / cross-sectional moments regime | 定位 2411.12845 / 2404.17885 / 2602.07066; 其余为博客与 R 包文档 (B/C 级, 未采用) |
| 本项目探针 | `pl02_probe8.py` | 三类面板均未检出显著 regime; λ 序列 AR(1) R² ≤ 0.0514 |
| `WebSearch` (v1.4 §3.3) | asset pricing factor preprocessing winsorize z-score rank | 主流为 winsorize + z-score 或 rank; 未找到 Box-Cox/YJ 用于因子截面变换 (B 级二手, 未逐篇核验) |
| `mcp_paper-search_search_crossref` (v1.4) | cross-sectional normalization of firm characteristics / Box-Cox financial ratios | 无直接相关的因子预处理规范文献; 未作为论据 |
| 本项目探针 | `pl02_probe9.py` | YJ λ=1 ≡ identity (8.9e-16); YJ λ=0 ≠ signed_log1p (6.9e+01); A/B 端到端差异 |
| 真实数据源 (v1.5) | `E:\Ashare_data`: `market_data/market_value.csv`, `stock_return.pkl`, `stock_amount.pkl` | CSV 与两个 pkl 可读; `price_volume_factors/UTR_turnover.pkl` 因 pandas StringDtype 版本不兼容**不可读**, 未使用 |
| 本项目探针 | `pl02_probe10.py` | 7 个真实因子缩尾后 \|skew\| 中位 0.87–6.21; 详见附录 A [I] |
| 本项目探针 | `pl02_probe11.py` | rank 后 4 个因子恒为 skew=0 / κ_ex=−1.2; 截面 Pearson 0.30–0.83, Spearman 恒 1.0; ties 0.02%–12.27% |
| 本项目探针 | `pl02_probe12.py` | rank→均匀 κ_ex=−1.2000 vs rank→正态 κ_ex=−0.0059; 两者截面 Pearson 0.9773 |
| `WebFetch` + `pypdf` (GKX) | 检索 "rank" 上下文 | 原文仅 "map these ranks into the [-1,1] interval", 未给显式公式; 引 Kelly-Pruitt-Su (2019) / Freyberger-Neuhierl-Weber (2020) |
| 真实数据源 (v1.7) | `E:\Ashare_data\market_data\stock_ind.pkl` | 可读: 3510 日 × 5344 股, 日频行业分类; 覆盖 2009-01-05 起, 与 market_value 交集至 2023-04-11 |
| 本项目探针 | `pl02_probe13.py` | rank 中性化残差与 identity 中性化残差 Spearman 0.7160; 行业解释 rank 方差 12.6% |
| `mcp_paper-search_search_crossref` (v1.8) | rank-based inverse normal transformation effect size bias | 命中 McCaw et al. (2019) INT 研究 (10.1101/635706) |
| `WebFetch` (CRAN) | RNOmni 官方文档与 vignette | D-INT/I-INT 定义、`k=0.375`、`ties.method='average'` 原文命中 |
| `WebSearch` (v1.8) | van der Waerden / Blom / Tukey normal scores formula | IBM SPSS / SAS / NAG / NIST 官方公式一致; 确认 v1.6 的 van der Waerden 命名错误 |
| `WebSearch` (v1.8) | D-INT I-INT direct indirect | 命中 RNOmni vignette 与 Genetic Epidemiology (10.1002/gepi.70013, 未完整核验, 未引用) |
| `WebFetch` + StackExchange REST (v1.8) | `q=rank transformation before regression` (stats) | 无直接相关高质量问答; 未作为证据 |

**说明**: MCP 的 Semantic Scholar 检索与 arXiv 读取存在不稳定; 本文所有关键学术论断均以 Crossref 元数据 + 官方文档/论文 PDF 原文复核, 不以搜索摘要单独作为 A 级证据.
