# PL-02 变换步骤前视缺陷调研

**文档版本**: v1.3 (调研完成, 未实施; v1.1 = review 修正: 代码行号 2 处、probe4 计时标注、probe7 无种子计数标注、数量级表述收紧; v1.2 = 追加 §3.1 方案 A/B vs C 的证据基础 + 参考文献 4 条 + 附录 B 检索记录; v1.3 = 追加 §3.2 regime 判别方法与实测 + 参考文献 8 条 + probe8)
**日期**: 2026-10-22
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

**与 ADR-027 的关系**: ADR-027 已决定"所有 `auto` → 固定方法", 但实现层从未落实 (`auto_optimize` 仍覆盖显式方法). PL-02 与 PL-01 一样, 同时是**前视缺陷**与 **ADR-027 实施缺口**. 设计文档需要明确: "固定方法"是否意味着"固定参数", 还是允许因果的参数调度.

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
| T3 | 每种方法的截断不变式 | identity / log / YJ / boxcox / power / quantile 分别验证 `n_diff=0` (或明确登记已知差异) |
| T4 | 参数调度因果性 | 若采用扩展/滚动 λ, 验证 `λ_t` 只使用 `[0,t]`; 截断前后每个日期的 λ 相同 |
| T5 | 可复现性 | 同一输入多次 `fit` 必须选出同一方法; Shapiro 子采样必须设固定 seed 或改为确定性检验 |
| T6 | 配置名映射 | `box_cox` / `yeo_johnson` / `none` 必须映射到实现层名称, 或在配置层拒绝 |
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

1. **固定方法 vs 自适应**: Static / Mixed 是否接受"固定方法 + 固定参数"? 若接受, 选哪个方法 (identity / log / YJ)? 若需要自适应, 是否采用扩展窗口 λ 调度? 证据见 §3.1: 无直接对照实验; FPP3 的 λ 不敏感性支持 B, De Gaetano (2018) 的"常量参数假设被拒"说明存在 B 失效的因子族. 注意 B 的 λ 必须是先验给定, 不能由本数据集估计后冻结.
2. **重估频率**: 若采用 C, 月/季/年重估的统计依据与成本预算是多少? 早期样本不足时回退到 identity 还是跳过变换? 窗口选择可引 §3.2.3 (Pesaran-Timmermann 2007; Inoue-Jin-Rossi 2017; Hännikäinen 2016 支持扩展窗口); 触发条件建议先测 §3.2.5 的信噪比 ρ, 而非引入 regime 判别器.
3. **逐日截面 λ (D)**: 是否需要作为可选项保留? 若保留, 只在 N≥某阈值时启用?
4. **Mixed 的触发条件**: `_diagnose_transform_need` 是否改为逐日/扩展窗口? 与 PL-06 的缩尾修复如何排序?
5. **配置契约**: `TransformationConfig` 的方法名如何统一? 是否允许 `none` 关闭变换? `enabled=False` 是否仍然无效?
6. **缓存代际**: 采用不同方案时输出变化幅度不同, 但都需要 bump; 具体版本号在实施文档确定.
7. **API 形态**: 若采用 C/D, `fit/transform` 的批量 API 是否保持? 需要在 `fit` 内生成调度表, 还是新增 `fit_transform` 的时序路径?

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

**说明**: MCP 的 Semantic Scholar 检索与 arXiv 读取存在不稳定; 本文所有关键学术论断均以 Crossref 元数据 + 官方文档/论文 PDF 原文复核, 不以搜索摘要单独作为 A 级证据.
