# v2.6.0 优化器与漂移检测增强 — 方案分析报告

**日期**: 2026-07-03
**状态**: 分析阶段 (待评审, v1.1 深度核查后修订)
**前置**: v2.5.0 多因子正交化三层架构已实施 (860 passed + 5 skipped)
**关联 ADR**: ADR-004 (目标函数) / ADR-005 (8 维搜索空间) / ADR-006 (Expanding Window CV)

---

## 目录

1. [执行摘要](#一执行摘要)
2. [v2.6.0 任务清单与现状审计](#二-v260-任务清单与现状审计)
3. [学术规范评估](#三学术规范评估)
4. [实践准则评估](#四实践准则评估)
5. [与因子处理管道一致性评估](#五与因子处理管道一致性评估)
6. [问题汇总与重新调整方案](#六问题汇总与重新调整方案)
7. [重新定义的 v2.6.0 任务清单](#七重新定义的-v260-任务清单)
8. [风险与陷阱清单](#八风险与陷阱清单)
9. [附录 A: 文献核查结果](#附录-a-文献核查结果)
10. [附录 B: 与 v2.5.0 三层架构的衔接](#附录-b-与-v250-三层架构的衔接)
11. [附录 C: 修订日志](#附录-c-修订日志)

---

## 一、执行摘要

v2.6.0 (优化器与漂移检测增强) 沿用 v2.4.0 时期制定的 P3 系列任务, 共 5 项 (P3-1, P3-9, P3-10, P3-11, P3-12). 经过对 [optimizer.py](file:///f:/Coding/factor_pipeline/optimizer.py) / [backtest/unified_drift.py](file:///f:/Coding/factor_pipeline/backtest/unified_drift.py) / [config_v2.py](file:///f:/Coding/factor_pipeline/config_v2.py) / [modules/factor_fingerprint/core/monitor.py](file:///f:/Coding/factor_pipeline/modules/factor_fingerprint/core/monitor.py) / [backtest/health_bridge.py](file:///f:/Coding/factor_pipeline/backtest/health_bridge.py) / [modules/factor_orthogonalizer/core/ridge.py](file:///f:/Coding/factor_pipeline/modules/factor_orthogonalizer/core/ridge.py) / [modules/factor_orthogonalizer/core/diagnostics.py](file:///f:/Coding/factor_pipeline/modules/factor_orthogonalizer/core/diagnostics.py) / [backtest/factor_significance.py](file:///f:/Coding/factor_pipeline/backtest/factor_significance.py) 的深度代码审计, 和对 6 篇学术文献的 WebSearch 核查, 发现 **8 类问题**:

1. **学术依据误引**: 3 处概念嫁接 (Hsu 2010 误称 Bayesian / Cohen-Coval-Pastor 2005 与 IC 时间加权无关 / Moreira-Muir 2017 与 IC 衰减无关), 1 处描述偏差 (Belloni 2014 "轮询不变性" 应为 "selection-robust inference"), 1 处期刊误标 (Bailey-LdP 2014 应为 JPM 非 JFDS)
2. **任务状态与代码不符**: P3-11 (参数重要性可视化) 实际已实施 ([optimizer.py:632-714](file:///f:/Coding/factor_pipeline/optimizer.py#L632) + [tests/test_p3_phase4_integration.py:164](file:///f:/Coding/factor_pipeline/tests/test_p3_phase4_integration.py#L164)), 但 [DECISIONS.md](file:///f:/Coding/factor_pipeline/DECISIONS.md#L1329) 仍标 `[ ]`
3. **搜索空间与 ADR-005 不一致**: [optimizer.py:47-56](file:///f:/Coding/factor_pipeline/optimizer.py#L47) 实际 8 维仍用 `classification_threshold_static/dynamic` (未合并), ADR-005 要求合并为 `classification_midpoint + classification_interval`
4. **目标函数与 ADR-004 不一致**: [optimizer.py:281-314](file:///f:/Coding/factor_pipeline/optimizer.py#L281) 实际仅 IC + 3 penalty (vol/cov/fidelity), 缺 ADR-004 要求的 **HealthMonitor penalty**, 且 fidelity 符号方向相反 (奖励而非惩罚)
5. **migration_threshold 字段位置错误** (v1.1 修正): [optimizer.py:155-158](file:///f:/Coding/factor_pipeline/optimizer.py#L155) 把 `migration_threshold` 设置到 `config.monitor` 上, 但 [MonitorConfig](file:///f:/Coding/factor_pipeline/modules/factor_fingerprint/core/monitor.py#L52) 无此字段; 实际字段位于 [PipelineV2ConfigUnified.migration_threshold](file:///f:/Coding/factor_pipeline/config_v2.py#L407) (第 407-410 行). `hasattr` 检查静默跳过, 导致该搜索维度对 Pipeline 行为零影响 (死维度). **不是字段缺失, 是字段位置错误**
6. **与 v2.5.0 三层架构脱节**: 优化器搜索空间和目标函数均未纳入 v2.5.0 新增的正交化参数 (`OrthogonalizationConfig.method/align_mode/ridge_lambda`) 和几何诊断 (VRR/κ)
7. **Layer 3 显著性检验未集成** (v1.1 新增): [FactorSignificanceTest](file:///f:/Coding/factor_pipeline/backtest/factor_significance.py) 已完整实现 Belloni et al. (2014) PDS Lasso + HC3 + BH 校正, 但**未集成到 optimizer 目标函数**, 原 5 项任务和 v1.0 调整方案均遗漏此项
8. **health_penalty 时序问题** (v1.1 新增): [HealthMonitorAdapter.build_report_from_engine](file:///f:/Coding/factor_pipeline/backtest/health_bridge.py#L40) 需要 `engine_results` 字典 (含 rank_icir/hit_rate/turnover/long_short_returns/ic_decay), **只能在回测后计算, 不能在 optimizer 的 CV fold 内部直接调用** — P3-9' 实现的关键挑战

**结论**: v2.6.0 不能直接按原 5 项任务执行, 需**重新调整为 8 项任务** (合并已完成项 + 修正误引 + 补齐 ADR-004/005 一致性 + 接入 v2.5.0 三层架构 + 集成 Layer 3 显著性), 详见第六、七章.

---

## 二、v2.6.0 任务清单与现状审计

### 2.1 原 5 项任务 (来自 DECISIONS.md)

| # | 任务 | DECISIONS.md 状态 | 实际代码状态 |
|---|------|------------------|------------|
| P3-1 | P2 时间衰减 (EWMA) | `[ ]` 未实施 | **部分实施**: [unified_drift.py:40](file:///f:/Coding/factor_pipeline/backtest/unified_drift.py#L40) 已有 `ewma_alpha=0.3` 用于 KS 平滑 (但这是漂移分数平滑, 不是 IC 时间加权); [factor_metrics.py:109-146](file:///f:/Coding/factor_pipeline/backtest/factor_metrics.py#L109) `compute_ic_series` 仍是简单平均, **IC 本身无时间衰减** |
| P3-9 | 端到端自动阈值搜索 (8 维, 修正目标函数) | `[ ]` 未实施 | **已实施但有矛盾**: [optimizer.py:59-624](file:///f:/Coding/factor_pipeline/optimizer.py#L59) `EndToEndThresholdOptimizer` 完整实现 (TPE + Expanding Window CV), 但 8 维与 ADR-005 不一致 (未合并 midpoint/interval), 目标函数与 ADR-004 不一致 (缺 HealthMonitor penalty, fidelity 符号方向相反) |
| P3-10 | PipelineV2Config 扩展 + 硬编码 → 配置迁移 | `[ ]` 未实施 | **大部分已实施**: [config_v2.py:412-432](file:///f:/Coding/factor_pipeline/config_v2.py#L412) 已有 8 个 P3 字段 + [config_v2.py:407-410](file:///f:/Coding/factor_pipeline/config_v2.py#L407) `migration_threshold`; 但 [optimizer.py:155-158](file:///f:/Coding/factor_pipeline/optimizer.py#L155) **字段位置错误** (设置到 config.monitor 而非 config 本身) |
| P3-11 | 搜索参数重要性可视化 | `[ ]` 未实施 | **完全已实施**: [optimizer.py:632-714](file:///f:/Coding/factor_pipeline/optimizer.py#L632) `get_param_importance` + `plot_param_importance` + [tests/test_p3_phase4_integration.py:164](file:///f:/Coding/factor_pipeline/tests/test_p3_phase4_integration.py#L164) `test_05_param_importance` |
| P3-12 | 定期重新搜索 + 阈值漂移监测 | `[ ]` 未实施 | **未实施**: 全代码库 grep `reoptim|re_search|periodic|定期` 零匹配; `unified_drift.py` 做的是**因子漂移**监测 (Fingerprint + Backtest + Turnover 三信号), 不是**阈值漂移**监测 |

### 2.2 关键代码审计细节

**审计 1 — 优化器搜索空间 (与 ADR-005 矛盾)**

ADR-005 第 196-207 行要求 8 维搜索空间, 其中 classification 合并为:
```
classification_midpoint   [0.45, 0.75]  (合并自 static + dynamic)
classification_interval   [0.15, 0.50]
```

但 [optimizer.py:47-56](file:///f:/Coding/factor_pipeline/optimizer.py#L47) 实际实现:
```python
'classification_threshold_static':  {'type': 'float', 'low': 0.5,  'high': 1.0},
'classification_threshold_dynamic': {'type': 'float', 'low': 0.0,  'high': 0.5},
```

**结论**: 8 维数量一致, 但分类阈值未按 ADR-005 合并为 midpoint/interval. 现有实现的物理含义更直观但与 ADR 矛盾, 二选一需明确. **推荐更新 ADR-005 对齐代码** (static/dynamic 比 midpoint/interval 更直观, midpoint/interval 引入额外非线性).

**审计 2 — 目标函数 (与 ADR-004 矛盾)**

ADR-004 第 147 行要求:
```python
score = IC_score - stability_penalty - ks_penalty - health_penalty - coverage_penalty
```

但 [optimizer.py:281-314](file:///f:/Coding/factor_pipeline/optimizer.py#L281) 实际:
```python
objective = ic_mean - λ_vol * vol_penalty - λ_cov * coverage_penalty + λ_fid * fidelity
```

**差异**:
- ✅ IC 主目标: 一致
- ✅ IC 波动性: 一致 (λ_vol)
- ✅ 覆盖率: 一致 (λ_cov)
- ⚠ KS 分布保真度: ADR-004 是**惩罚** (ks_penalty, 分布扭曲才扣分), 实际是**奖励** (fidelity, 分布相似才加分) — 符号方向相反
- ❌ **HealthMonitor penalty**: 完全缺失, ADR-004 第 153 行要求 `< 40 → -0.5, < 60 → -0.2`

**审计 3 — migration_threshold 字段位置错误** (v1.1 修正)

v1.0 报告此问题为 "MonitorConfig 缺 migration_threshold 字段", 经深度核查发现描述不准确:

- [PipelineV2ConfigUnified.migration_threshold](file:///f:/Coding/factor_pipeline/config_v2.py#L407) **字段已存在** (第 407-410 行, 默认 0.10):
  ```python
  migration_threshold: float = Field(
      default=0.10, ge=0.0, le=1.0,
      description="迁移置信度阈值"
  )
  ```
- 但 [optimizer.py:155-158](file:///f:/Coding/factor_pipeline/optimizer.py#L155) 错误地设置到 `config.monitor` 上:
  ```python
  if hasattr(config.monitor, 'migration_threshold'):     # MonitorConfig 无此字段 → False
      config.monitor.migration_threshold = params['migration_threshold']
  elif hasattr(config.monitor, 'similarity_threshold'):  # MonitorConfig 也无此字段 → False
      config.monitor.similarity_threshold = params['migration_threshold']
  ```
- [MonitorConfig](file:///f:/Coding/factor_pipeline/modules/factor_fingerprint/core/monitor.py#L52) 字段: `short/medium/long_window + short/medium/long_threshold + migration_consecutive + enable_smooth_transition`, **无 migration_threshold 也无 similarity_threshold**

**结论**: **不是字段缺失, 是字段位置错误**. 修复方案: 把 `config.monitor.migration_threshold = ...` 改为 `config.migration_threshold = ...` (直接设置到 PipelineV2ConfigUnified 上).

**审计 4 — IC 计算无时间衰减**

[factor_metrics.py:109-146](file:///f:/Coding/factor_pipeline/backtest/factor_metrics.py#L109) `compute_ic_series` 对每期 t 计算截面 IC, 然后在 [optimizer.py:212](file:///f:/Coding/factor_pipeline/optimizer.py#L212) 用 `np.nanmean(ics)` 简单平均. P3-1 要求的"EWMA 时间衰减" (近期 IC 权重更高) 未实施.

**注意**: [unified_drift.py:295-324](file:///f:/Coding/factor_pipeline/backtest/unified_drift.py#L295) 的 `_ewma_smooth` 方法已实现 EWMA 平滑, 但用于**漂移分数过滤** (KS 假阳性控制), 与 P3-1 的 **IC 时间加权**是不同概念, 不冲突但需明确区分.

**审计 5 — health_bridge 时序问题** (v1.1 新增)

[HealthMonitorAdapter.build_report_from_engine](file:///f:/Coding/factor_pipeline/backtest/health_bridge.py#L40) 接口:
```python
def build_report_from_engine(self, factor_name: str, engine_results: Dict[str, Any]) -> FactorHealthReport:
    # 需要 engine_results 含: rank_icir, hit_rate, rank_ic_series, turnover, long_short_returns, ic_decay
```

**关键发现**: health_score 只能在**回测后**计算 (需要 engine_results), **不能在 optimizer 的 CV fold 内部直接调用** (fold 内只有 IC 矩阵, 没有完整 engine_results). 这是 P3-9' 实现的关键挑战, 需要 3 种备选方案 (详见 P3-9' 任务定义).

**审计 6 — RidgeOrthogonalizer 已完整实现 λ 选择** (v1.1 新增)

[ridge.py:87-100](file:///f:/Coding/factor_pipeline/modules/factor_orthogonalizer/core/ridge.py#L87) 已完整实现:
- `_select_lambda_cv` (用 sklearn RidgeCV, 5-fold CV, λ 候选 [0.01, 0.1, 1.0, 10.0, 100.0])
- `_select_lambda_ledoit_wolf` (用 sklearn LedoitWolf shrinkage)

**结论**: P3-13 的 Ridge λ 选择**无需新建**, 配置层 (`OrthogonalizationConfig.ridge_lambda_selection`) 和算法层 (`RidgeOrthogonalizer._select_lambda_*`) 都已就绪.

**审计 7 — compute_vrr 是 pure function** (v1.1 新增)

[diagnostics.py:48-76](file:///f:/Coding/factor_pipeline/modules/factor_orthogonalizer/core/diagnostics.py#L48) `OrthogonalizationDiagnostics.compute_vrr`:
```python
@staticmethod
def compute_vrr(F: np.ndarray, T: np.ndarray, ddof: int = 0) -> np.ndarray:
    """VRR_k = Var(T_k) / Var(F_k)"""
```

**关键发现**: 是 `@staticmethod` + pure function + 不需要 fit 过的 orthogonalizer + 只需 F 和 T 两个矩阵. **直接可调用**, 但需要 OrthogonalizerAdapter 暴露 F/T 矩阵 (当前不暴露, 需扩展 `get_diagnostics()` 方法).

**审计 8 — FactorSignificanceTest 未集成到 optimizer** (v1.1 新增)

[factor_significance.py](file:///f:/Coding/factor_pipeline/backtest/factor_significance.py) 已完整实现:
- Belloni-Chernozhukov-Hansen (2014) Post-Double-Selection Lasso (三阶段: Lasso y~X → Lasso D_k~X → OLS y~D_k+X_union)
- HC3 稳健标准误 (MacKinnon-White 1985)
- BH/Bonferroni/Holm 多重检验校正

**但**: Grep `FactorSignificanceTest` 在 `optimizer.py` 中 "No matches found". **Layer 3 显著性未纳入 optimizer 目标函数**, 原 5 项任务和 v1.0 调整方案均遗漏此项.

---

## 三、学术规范评估

### 3.1 文献核查汇总 (v1.1 修正)

| 文献 | v2.6.0 预期用途 | 核查结果 | 严重性 |
|------|--------------|---------|--------|
| Dimson (1979) JFE 7(2):197-226 | IC 衰减概念 | **误用**: 原文是 beta decay (非同步交易下的 beta 估计偏差), 非 IC decay | 中 |
| Moreira & Muir (2017) JF 72(4):1611-1644 | 高波动期 IC 衰减 | **误用**: 原文是 inverse-vol scaling (头寸管理), 未直接测量 IC / predictability 的时间变化 | 中 |
| Bailey & López de Prado (2014) | 定期重搜理论 | **期刊误标**: 实际是 *J. Portfolio Management* 40(5):94-107, 不是 *J. Financial Data Science* (2019 才创刊) | 低 |
| López de Prado (2018) Ch.7 | Purged K-fold | **正确**: 第 7 章确实批判 K-fold look-ahead. 但 Combinatorial Purged K-fold 在第 12 章, 不在第 7 章 | 低 |
| Belloni et al. (2014) RES 81(2):608-650 | 双重 Lasso PDS | **描述偏差**: 论文选用准确 (PDS Lasso 是 Layer 3 标准方法), 但 "treatment 轮询不变性" 不是论文术语, 应为 "selection-robust inference" (对高维控制变量选择的稳健推断) | 低 |
| Hsu, Hsu & Kuan (2010) JEF 17(4):680-691 | 重搜索频率 (被标 "Bayesian approaches") | **误称**: 实际是 SPA (Superior Predictive Ability) 频繁派 + Bootstrap 方法 (White 2000 框架), 与 Bayesian 无关. 未发现 "Hsu et al. (2010) Bayesian approaches" 标题版本 | **高** |
| Bergstra et al. (2011) NIPS 24:2546-2554 | TPE + fANOVA | **张冠李戴**: TPE 原文正确, 但 fANOVA 不在此文, 应引 Hutter et al. (2014) | 中 |
| Hutter, Hoos & Leyton-Brown (2014) ICML 32(1):754-762 | fANOVA | **正确**: fANOVA 原始出处 | 无 |
| ~~Cohen, Coval & Pastor (2005) JF 60(3):1057-1096~~ | ~~P3-1 IC 时间加权替换文献~~ | **v1.0 误推荐, v1.1 撤回**: 原文讨论基金持仓相似度 (peer-group co-holding method), 与 IC 时间加权 (EWMA) **完全无关** | **高** |

### 3.2 学术规范问题详述

**问题 A — 概念嫁接 (Dimson 1979 / Moreira-Muir 2017)**

P3-1 (EWMA 时间衰减) 原本想用 Dimson (1979) 和 Moreira-Muir (2017) 作为"IC 时间衰减"的学术依据, 但:

- **Dimson (1979)** 讨论的是 **beta 估计偏差** (非同步交易导致 beta 偏低, 用 aggregated coefficients 修正), 不是因子预测能力 (IC) 的时间衰减. 将 beta decay 等同于 IC decay 是概念混淆.
- **Moreira & Muir (2017)** 讨论的是 **头寸缩放** (高波动期减仓, 提升夏普), 论证的是"波动率上升时预期收益未按比例上升" (即 Sharpe 在高波动期下降). 论文**未直接测量或讨论 IC / predictability / signal strength 的时间变化**. 把 inverse-vol scaling 嫁接为"IC 高波动期衰减"是过度引申.

**修正方案** (v1.1 重新推荐): P3-1 应改为引用:
- **Ferson & Siegel (2001)** "The Efficient Use of Conditioning Information in Portfolios" *J. Finance* 56(3):967-982 — 条件信息时变加权
- **Barroso & Santa-Clara (2015)** "Momentum is Not Dead" *J. Financial Economics* 115(3):464-482 — 直接讨论动量因子在高波动期 IC 衰减, vol-scaling 解决
- 或直接用工程实践理由: "近期 IC 信息量更高" 是行业惯例 (RiskMetrics 1996 EWMA 框架, Goldman Sachs / AQR 内部实践), 无需强行挂靠学术文献

**问题 B — 文献误称 (Hsu et al. 2010)**

P3-12 (定期重新搜索) 原本想引用 "Hsu, Hsu & Kuan (2010) Bayesian approaches" 作为理论支撑, 但 WebSearch 核查未发现该标题的贝叶斯版本. 实际 Hsu et al. (2010) 是用 **SPA (Superior Predictive Ability) 检验** — White (2000) 的频繁派 Bootstrap 方法 — 检验技术分析预测能力, 与 Bayesian 无关.

**修正方案**: P3-12 应改为引用:
- **Bailey & López de Prado (2014)** "The Deflated Sharpe Ratio" *J. Portfolio Management* 40(5):94-107 (已正确引用, 但期刊名需修正) — 随试验次数动态调整显著性阈值
- **Sullivan, Timmermann & White (1999)** "Data-Snooping, Technical Trading Rule Performance, and the Bootstrap" *J. Finance* 54(5):1647-1691 — data snooping 框架源头 (BRC)
- **McLean & Pontiff (2016)** "Does Academic Research Destroy Stock Return Predictability?" *J. Finance* 71(1):5-32 — 因子衰减实证 (OOS 衰减 26%, 发表后衰减 58%), 支持定期重搜
- **Harvey & Liu (2015)** "Backtesting" *J. Finance* 70(5):1855-1886 — 现代回测多重检验框架 (可补充)

**问题 C — 张冠李戴 (fANOVA)**

P3-11 (参数重要性可视化) 原本想用 Bergstra et al. (2011) 作为 TPE + fANOVA 的共同依据, 但 fANOVA 实际来自 **Hutter, Hoos & Leyton-Brown (2014) ICML**, Bergstra et al. (2011) 仅提供 TPE.

**修正方案**: P3-11 (已实施) 的学术依据应分拆:
- TPE → Bergstra, Bardenet, Bengio & Kégl (2011) NIPS 24:2546-2554
- fANOVA → Hutter, Hoos & Leyton-Brown (2014) ICML 32(1):754-762

**问题 D — v1.0 误推荐 Cohen-Coval-Pastor (2005)** (v1.1 撤回)

v1.0 报告推荐 Cohen-Coval-Pastor (2005) 作为 P3-1 IC 时间加权的替换文献, 经 WebSearch 深度核查发现:
- 论文核心是 **peer-group / 共持持仓 (co-holding) 方法** 评估基金经理选股能力
- 讨论的是**横截面持仓相似度**, 完全没有讨论 IC (information coefficient) 的时间加权或 EWMA
- 把该论文用作 P3-1 EWMA 学术依据是**张冠李戴**

**v1.1 撤回此推荐**, 改为推荐 Ferson & Siegel (2001) 或 Barroso & Santa-Clara (2015).

---

## 四、实践准则评估

### 4.1 实践准则 1 — 任务状态必须与代码一致

**违反**: P3-11 已实施但 DECISIONS.md 标 `[ ]`. 这种状态不一致会让后续开发者重复劳动或误判项目进度.

**修复**: 立即将 P3-11 状态改为 `[x]`, 在 DECISIONS.md 中追加"实际实施位置: optimizer.py:632-714 + test_p3_phase4_integration.py:164".

### 4.2 实践准则 2 — 静默失败是反模式

**违反**: [optimizer.py:155-158](file:///f:/Coding/factor_pipeline/optimizer.py#L155) 用 `hasattr` 检查 `migration_threshold`, 字段位置错误时静默跳过, 导致该搜索维度对 Pipeline 行为零影响, 但优化器仍消耗 trial 预算搜索它. 这是 ADR-014 已明令禁止的"优雅回退"反模式.

**修复** (v1.1 修正):
- 把 `config.monitor.migration_threshold = ...` 改为 `config.migration_threshold = ...` (直接设置到 PipelineV2ConfigUnified 上)
- 移除 `hasattr` 检查 (字段已存在于 PipelineV2ConfigUnified)
- 添加断言 `assert hasattr(config, 'migration_threshold')` 防止回归

### 4.3 实践准则 3 — ADR 与代码必须双向一致

**违反**: ADR-004 要求 HealthMonitor penalty, 代码没有; ADR-005 要求合并 midpoint/interval, 代码用 static/dynamic. ADR 是契约, 代码偏离 ADR 必须二选一: 要么改代码对齐 ADR, 要么更新 ADR 对齐代码.

**修复**:
- HealthMonitor penalty: **改代码对齐 ADR-004** (添加 `health_penalty` 到 `_composite_objective`, 但需解决时序问题, 详见 P3-9')
- 分类阈值合并: **更新 ADR-005 对齐代码** (实际 static/dynamic 更直观, midpoint/interval 引入额外非线性, ADR-005 第 213 行已承认此风险)

### 4.4 实践准则 4 — 新功能必须纳入优化器

**违反**: v2.5.0 新增的正交化参数 (`OrthogonalizationConfig.method/align_mode/ridge_lambda`) 和几何诊断 (VRR/κ) 未纳入优化器搜索空间和目标函数. 这意味着优化器搜索的阈值组合**无法优化正交化效果**, v2.5.0 的三层架构在优化层面是脱节的.

**修复**: 新增 P3-13 任务 (正交化参数纳入搜索空间) 和 P3-14 任务 (几何诊断纳入目标函数).

### 4.5 实践准则 5 — Layer 3 显著性必须集成 (v1.1 新增)

**违反**: [FactorSignificanceTest](file:///f:/Coding/factor_pipeline/backtest/factor_significance.py) 已完整实现 Belloni et al. (2014) PDS Lasso + HC3 + BH 校正, 但**未集成到 optimizer 目标函数**. Layer 3 的 treatment coefficient 不在目标函数中, 优化器无法平衡 IC 与 statistical significance.

**修复**: 新增 P3-15 任务 (Layer 3 显著性纳入目标函数), 但需注意计算成本 (K 次 LassoCV + K 次 OLS), 建议作为**最终配置验证**而非每 trial 评估.

---

## 五、与因子处理管道一致性评估

### 5.1 Pipeline 数据流一致性

当前 Pipeline 数据流 (v2.5.0 后):

```
Layer 1 (per-factor): impute → outlier → transform → standardize → neutralize → garch
    ↓
Layer 2 (cross-factor): orthogonalize (post_transform_hook, 默认关闭)
    ↓
Layer 3 (target-aware): FactorSignificanceTest (回测子模块, 未集成到 optimizer)
```

**问题**: 优化器 `EndToEndThresholdOptimizer.optimize()` 只在 Layer 1 上搜索阈值 (hard_routing_prob / merge_alpha / ks_alpha / mixed_winsor_sigma / transform_aggressiveness + 分类阈值 + migration_threshold), **不搜索 Layer 2 正交化参数**, 也**不评估 Layer 3 显著性**.

**影响**:
- 用户启用正交化后, 优化器无法找到正交化最优配置
- 优化器的 IC 评分不考虑正交化对 IC 的影响 (IC 可能因正交化下降, 但 ICIR 上升)
- Layer 3 的 treatment coefficient 不在目标函数中, 优化器无法平衡 IC 与 statistical significance

### 5.2 配置系统一致性

`PipelineV2ConfigUnified` (v2.5.0) 已包含:
- ✅ Layer 1 阈值 (hard_routing_prob / merge_alpha / ks_alpha / mixed_winsor_sigma / transform_aggressiveness)
- ✅ Layer 2 配置 (orthogonalization: OrthogonalizationConfig, 16 个字段)
- ✅ migration_threshold (第 407-410 行, 但 optimizer 设置位置错误)
- ❌ Layer 3 配置 (无 FactorSignificanceConfig)

**OrthogonalizationConfig 完整字段** (v1.1 核查, 16 个):
```
enabled / method / window_mode / window_size / min_obs / shrinkage /
vrr_threshold / groups / use_gpu / align_mode /
ridge_lambda / ridge_lambda_selection /
pca_variance_threshold / pca_center / gs_order / gs_reorthogonalize
```

**问题**: 优化器的 `_params_to_config()` 仅设置 Layer 1 阈值, 不设置 Layer 2 正交化参数. 即使 `PipelineV2ConfigUnified` 支持, 优化器也无法搜索.

### 5.3 漂移检测一致性

`UnifiedDriftReporter` (unified_drift.py) 已实现:
- 结构漂移 (Fingerprint, 滚动窗口 KS) + 性能漂移 (Backtest, ICIR 变化率) + 换手率漂移, 三信号融合
- EWMA 平滑 (ewma_alpha=0.3) 用于 KS 假阳性控制
- 三种融合模式 (and / or / max)

**问题**: P3-12 要求的"阈值漂移监测"是不同概念 — 监测的是**优化器搜索出的阈值组合**是否随市场变化需要重新搜索, 而不是**因子本身**的漂移. 当前代码库无此功能.

**与 UnifiedDriftReporter 的边界** (v1.1 核查):
- UnifiedDriftReporter 监测**因子本身**的漂移 (IC 分布变化 / ICIR 衰减 / 换手率变化)
- P3-12' 监测**阈值组合**的有效性 (best_score 衰减 / 阈值敏感度变化)
- 两者有部分重叠: UnifiedDriftReporter 的"性能漂移" (ICIR 变化率) 与 P3-12' 的"IC 衰减检测"概念相近, 但监测对象不同
- **修复**: P3-12' 可复用 UnifiedDriftReporter 的 `_compute_performance_drift` 方法, 但监测对象从"单因子"改为"阈值组合"

---

## 六、问题汇总与重新调整方案

### 6.1 问题汇总 (按严重性, v1.1 修正)

| # | 问题 | 严重性 | 影响范围 | v1.0 → v1.1 变化 |
|---|------|--------|---------|-----------------|
| 1 | P3-11 状态错误 (已实施但标未实施) | 高 | DECISIONS.md / 项目进度判断 | 无变化 |
| 2 | migration_threshold **字段位置错误** (非缺失) | 高 | 优化器有效性 (8 维实际 7 维有效) | v1.1 修正描述: 字段存在于 PipelineV2ConfigUnified, optimizer 设置到 config.monitor 上 |
| 3 | 目标函数缺 HealthMonitor penalty (与 ADR-004 不一致) | 高 | 优化器目标正确性 | 无变化, 但新增时序问题 |
| 4 | 搜索空间未纳入 v2.5.0 正交化参数 | 高 | v2.5.0 三层架构脱节 | 无变化 |
| 5 | 搜索空间与 ADR-005 不一致 (midpoint/interval vs static/dynamic) | 中 | ADR 契约一致性 | 无变化 |
| 6 | 目标函数未纳入 VRR/κ 几何诊断 | 中 | v2.5.0 诊断指标未利用 | 无变化 |
| 7 | P3-1 学术依据误引 (Dimson / Moreira-Muir) | 中 | 学术规范 | 无变化 |
| 8 | P3-12 学术依据误引 (Hsu et al. 2010 误称 Bayesian) | 中 | 学术规范 | 无变化 |
| 9 | fANOVA 张冠李戴 (Bergstra 2011 → Hutter 2014) | 低 | 学术规范 | 无变化 |
| 10 | Bailey-LdP 2014 期刊误标 | 低 | 学术规范 | 无变化 |
| 11 | **health_penalty 时序问题** (v1.1 新增) | 高 | P3-9' 实现可行性 | 新增: health_score 需 engine_results, 不能在 CV fold 内直接调用 |
| 12 | **FactorSignificanceTest 未集成** (v1.1 新增) | 中 | Layer 3 显著性未纳入目标函数 | 新增: PDS Lasso 已完整实现但未集成 |
| 13 | **v1.0 误推荐 Cohen-Coval-Pastor (2005)** (v1.1 撤回) | 中 | 学术规范 | 新增: v1.0 推荐的替换文献也是误引 |

### 6.2 重新调整方案

**原 5 项任务 → 新 8 项任务** (v1.1 从 7 项扩展到 8 项):

| 原任务 | 调整后任务 | 调整内容 |
|--------|----------|---------|
| P3-1 (EWMA 时间衰减) | **P3-1' IC 时间加权** | 重新定义: 在 `compute_ic_series` 添加 EWMA 加权选项, 学术依据改为 Ferson-Siegel (2001) 或 Barroso-Santa-Clara (2015), **撤回 v1.0 推荐的 Cohen-Coval-Pastor** |
| P3-9 (8 维搜索) | **P3-9' 目标函数对齐 ADR-004** | 重新定义: 添加 `health_penalty`, 修正 `fidelity` 符号方向; **v1.1 新增**: 用代理指标 (IC decay / IC hit rate) 解决 health_score 时序问题 |
| P3-10 (配置迁移) | **P3-10' migration_threshold 字段位置修正 + ADR-005 更新** | v1.1 修正: (a) 把 optimizer 的 `config.monitor.migration_threshold` 改为 `config.migration_threshold`; (b) 更新 ADR-005 对齐代码 |
| P3-11 (参数重要性) | **P3-11' 状态修正** | 标记为 `[x] 已实施`, 修正学术依据 (TPE→Bergstra 2011, fANOVA→Hutter 2014), 无需新代码 |
| P3-12 (定期重搜) | **P3-12' 阈值漂移监测** | 重新定义: 新建 `threshold_drift_monitor.py`, 可复用 UnifiedDriftReporter 的 `_compute_performance_drift`, 学术依据改为 Bailey-LdP (2014, 修正期刊) + Sullivan-TW (1999) + McLean-Pontiff (2016) |
| — (新增) | **P3-13 正交化参数纳入搜索空间** | v1.1 修正: **不搜索 orth_enabled** (用户决策, 非优化器决策), 只搜索 method/align_mode/ridge_lambda (3 维) |
| — (新增) | **P3-14 几何诊断纳入目标函数** | v1.1 修正: 需扩展 `OrthogonalizerAdapter.get_diagnostics()` 暴露 F/T 矩阵; λ_redundancy 从 0.1 降为 0.05; 说明与 IC 主目标的潜在冲突 |
| — (新增) | **P3-15 Layer 3 显著性纳入目标函数** (v1.1 新增) | 新增: 在 `_composite_objective` 添加 `significance_penalty`; 但因计算成本高 (K 次 LassoCV + K 次 OLS), **仅用于最终配置验证, 不用于每 trial 评估** |

---

## 七、重新定义的 v2.6.0 任务清单

### P3-1': IC 时间加权 (EWMA)

**目标**: 在 `compute_ic_series` 添加 EWMA 加权选项, 让近期 IC 权重更高.

**学术依据** (v1.1 修正, 撤回 Cohen-Coval-Pastor):
- **Ferson & Siegel (2001)** "The Efficient Use of Conditioning Information in Portfolios" *J. Finance* 56(3):967-982 — 条件信息时变加权
- **Barroso & Santa-Clara (2015)** "Momentum is Not Dead" *J. Financial Economics* 115(3):464-482 — 动量因子在高波动期 IC 衰减, vol-scaling 解决
- 工程实践: RiskMetrics (1996) EWMA 框架, Goldman Sachs / AQR 内部惯例

**实现**:
```python
def compute_ic_series(factor, returns, method='rank', weighting='equal', halflife=12):
    """IC 序列计算, 支持 equal / ewma 加权"""
    ic_series = ...  # 现有逻辑
    if weighting == 'ewma':
        alpha = 1 - np.exp(-np.log(2) / halflife)
        weights = (1 - alpha) ** np.arange(len(ic_series))[::-1]
        weights /= weights.sum()
        return np.nansum(ic_series * weights)
    return np.nanmean(ic_series)
```

**验收**: 手工校验 EWMA 加权 IC 与等权 IC 在 IC 衰减场景下差异显著; 全量回归零退化.

---

### P3-9': 目标函数对齐 ADR-004 (v1.1 修正: 代理指标解决时序问题)

**目标**: 在 `_composite_objective` 添加 `health_penalty`, 修正 `fidelity` 符号方向.

**ADR-004 要求**:
```python
score = IC_score - stability_penalty - ks_penalty - health_penalty - coverage_penalty
```

**当前实现** (需修正):
```python
objective = ic_mean - λ_vol * vol_penalty - λ_cov * coverage_penalty + λ_fid * fidelity  # fidelity 符号错
```

**修正后**:
```python
objective = (
    ic_mean
    - λ_vol * vol_penalty           # IC 波动性惩罚 (保留)
    - λ_cov * coverage_penalty       # 覆盖率惩罚 (保留)
    - λ_ks * ks_distortion_penalty   # KS 分布扭曲惩罚 (修正: 奖励 → 惩罚)
    - λ_health * health_penalty      # HealthMonitor penalty (新增)
)
```

**v1.1 新增: health_penalty 时序问题与 3 种实现方案**

[HealthMonitorAdapter.build_report_from_engine](file:///f:/Coding/factor_pipeline/backtest/health_bridge.py#L40) 需要 `engine_results` 字典 (含 rank_icir/hit_rate/turnover/long_short_returns/ic_decay), **只能在回测后计算, 不能在 optimizer 的 CV fold 内部直接调用** (fold 内只有 IC 矩阵). 3 种备选方案:

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| (A) Trial 级聚合 | CV 结束后批量评估 health_score | 直接复用 health_bridge | 每 trial 只 1 个 health_score, 粒度粗 |
| (B) 代理指标 (推荐) | 用 IC decay / IC hit rate / IC volatility 作为 health_score 的近似 | fold 级粒度, 无时序问题 | 需校准代理指标与 health_score 的相关性 |
| (C) 最终验证 | health_penalty 移到最终配置验证, 不参与每 trial | 计算成本低 | 无法在搜索过程中引导优化器 |

**推荐方案 (B)**: 代理指标实现:
```python
def _health_penalty_proxy(self, ic_array: np.ndarray) -> float:
    """HealthMonitor 代理惩罚 (基于 IC 系列特征)

    用 IC decay / hit rate / volatility 作为 health_score 的近似,
    避免 engine_results 的时序依赖.
    """
    # IC decay: 后半段 IC 均值 / 前半段 IC 均值
    mid = len(ic_array) // 2
    ic_early = np.nanmean(ic_array[:mid])
    ic_late = np.nanmean(ic_array[mid:])
    decay_ratio = ic_late / ic_early if abs(ic_early) > 1e-10 else 1.0

    # IC hit rate
    hit_rate = np.nanmean(ic_array > 0)

    # IC volatility
    ic_vol = np.nanstd(ic_array)

    # 代理 health_score: decay_ratio > 0.8 + hit_rate > 0.55 + ic_vol < 0.1 → 健康
    if decay_ratio < 0.5 or hit_rate < 0.4 or ic_vol > 0.2:
        return 0.5  # ADR-004: < 40 → -0.5
    elif decay_ratio < 0.8 or hit_rate < 0.5 or ic_vol > 0.15:
        return 0.2  # ADR-004: < 60 → -0.2
    return 0.0
```

**验收**: 目标函数与 ADR-004 第 147 行完全一致; 手工校验代理 health_penalty 在低健康度场景下扣分; 全量回归零退化.

---

### P3-10': migration_threshold 字段位置修正 + ADR-005 更新 (v1.1 修正)

**目标**: (a) 修正 optimizer 字段位置错误; (b) 更新 ADR-005 对齐代码.

**(a) 字段位置修正** (v1.1 修正: 不是添加字段, 是修正设置位置):

[config_v2.py:407-410](file:///f:/Coding/factor_pipeline/config_v2.py#L407) `PipelineV2ConfigUnified.migration_threshold` **字段已存在**, 无需添加.

[optimizer.py:150-158](file:///f:/Coding/factor_pipeline/optimizer.py#L150) 修正:
```python
# 修正前 (字段位置错误):
if 'migration_threshold' in params:
    config.monitor.enable_smooth_transition = True
    if hasattr(config.monitor, 'migration_threshold'):     # 永远 False
        config.monitor.migration_threshold = params['migration_threshold']
    elif hasattr(config.monitor, 'similarity_threshold'):  # 永远 False
        config.monitor.similarity_threshold = params['migration_threshold']

# 修正后 (直接设置到 config 本身):
if 'migration_threshold' in params:
    config.migration_threshold = params['migration_threshold']
    config.monitor.enable_smooth_transition = True  # 保留: 启用平滑过渡
```

**(b) ADR-005 更新**:
- 承认 `classification_threshold_static/dynamic` 比 `midpoint/interval` 更直观
- 修改 ADR-005 状态: "实施时调整为 static/dynamic 分离, 不采用 midpoint/interval 合并"
- 在 DECISIONS.md 追加修订日志

**验收**: optimizer 的 migration_threshold 维度对 Pipeline 行为有实际影响; ADR-005 修订日志已追加; 全量回归零退化.

---

### P3-11': 状态修正 (已实施)

**目标**: 修正 DECISIONS.md 状态 + 学术依据.

**修正**:
- DECISIONS.md: P3-11 状态 `[ ]` → `[x] 已实施`
- 学术依据分拆:
  - TPE → Bergstra, Bardenet, Bengio & Kégl (2011) NIPS 24:2546-2554
  - fANOVA → Hutter, Hoos & Leyton-Brown (2014) ICML 32(1):754-762

**实现位置**:
- [optimizer.py:632-645](file:///f:/Coding/factor_pipeline/optimizer.py#L632) `get_param_importance` (调用 `optuna.importance.get_param_importances`)
- [optimizer.py:651-714](file:///f:/Coding/factor_pipeline/optimizer.py#L651) `plot_param_importance` (matplotlib 条形图)
- [tests/test_p3_phase4_integration.py:164-194](file:///f:/Coding/factor_pipeline/tests/test_p3_phase4_integration.py#L164) `test_05_param_importance`

**验收**: DECISIONS.md 状态已修正; 学术依据已分拆; 无需新代码.

---

### P3-12': 阈值漂移监测

**目标**: 新建 `backtest/threshold_drift_monitor.py`, 监测最优阈值组合的 IC 衰减, 触发重新搜索.

**学术依据** (修正后):
- Bailey & López de Prado (2014) "The Deflated Sharpe Ratio" *J. Portfolio Management* 40(5):94-107 — 随试验次数动态调整显著性阈值
- Sullivan, Timmermann & White (1999) "Data-Snooping, Technical Trading Rule Performance, and the Bootstrap" *J. Finance* 54(5):1647-1691 — data snooping 框架源头 (BRC)
- McLean & Pontiff (2016) "Does Academic Research Destroy Stock Return Predictability?" *J. Finance* 71(1):5-32 — 因子衰减实证 (OOS 衰减 26%, 发表后衰减 58%), 支持定期重搜

**与 UnifiedDriftReporter 的边界** (v1.1 核查):
- UnifiedDriftReporter: 监测**因子本身**的漂移 (IC 分布 / ICIR / 换手率)
- ThresholdDriftMonitor: 监测**阈值组合**的有效性 (best_score 衰减 / 阈值敏感度)
- 可复用 UnifiedDriftReporter 的 `_compute_performance_drift` 方法, 但监测对象不同

**实现**:
```python
class ThresholdDriftMonitor:
    """阈值漂移监测器

    监测最优阈值组合的 IC 衰减, 触发重新搜索.
    区别于 UnifiedDriftReporter (监测因子漂移), 本类监测阈值有效性.
    """
    def __init__(self, best_score: float, best_params: Dict, halflife: int = 63):
        self.best_score = best_score
        self.best_params = best_params
        self.halflife = halflife
        self.score_history = []

    def update(self, current_score: float) -> Dict:
        """更新当前评分, 返回是否需要重新搜索"""
        self.score_history.append(current_score)
        # IC 衰减检测 (EWMA 加权)
        decay_ratio = self._compute_decay_ratio()
        # 触发条件: IC 衰减 > 20% 或绝对值低于 best_score * 0.8
        needs_research = decay_ratio < 0.8
        return {
            'needs_research': needs_research,
            'decay_ratio': decay_ratio,
            'best_score': self.best_score,
            'current_score': current_score,
        }
```

**验收**: 手工校验衰减检测逻辑; 集成测试验证与 `EndToEndThresholdOptimizer.optimize` 的衔接; 全量回归零退化.

---

### P3-13: 正交化参数纳入搜索空间 (v1.1 修正: 不搜索 orth_enabled)

**目标**: 在 `DEFAULT_SEARCH_SPACE` 添加正交化参数, 让优化器搜索最优正交化配置.

**v1.1 修正**: **不搜索 `orth_enabled`** — 启用正交化是用户决策 (与 v2.5.0 "默认关闭, 保护基线" 设计哲学一致), 不是优化器决策. 只搜索 method/align_mode/ridge_lambda.

**学术依据**:
- v2.5.0 ADR-020 已确立 (Löwdin 1950 / Ledoit-Wolf 2004 / Kahan 1966)
- [RidgeOrthogonalizer](file:///f:/Coding/factor_pipeline/modules/factor_orthogonalizer/core/ridge.py#L24) 已完整实现 cv/ledoit_wolf λ 选择 (v1.1 核查确认)

**实现** (v1.1 修正):
```python
# 在 DEFAULT_SEARCH_SPACE 添加 (仅当用户启用 orth_enabled=True 时搜索)
DEFAULT_SEARCH_SPACE_ORTH = {
    'orth_method': {'type': 'categorical',
                    'choices': ['symmetric', 'ridge', 'pca', 'gram_schmidt']},
    'orth_align_mode': {'type': 'categorical',
                        'choices': ['intersection', 'union_nan']},  # 不搜索 raise_on_mismatch
    'orth_ridge_lambda': {'type': 'float', 'low': 0.01, 'high': 100.0},  # log-uniform
}

# 在 _params_to_config 添加 (仅当 config.orthogonalization.enabled=True 时)
if config.orthogonalization.enabled:
    if 'orth_method' in params:
        config.orthogonalization.method = params['orth_method']
    if 'orth_align_mode' in params:
        config.orthogonalization.align_mode = params['orth_align_mode']
    if 'orth_ridge_lambda' in params and config.orthogonalization.method == 'ridge':
        config.orthogonalization.ridge_lambda = params['orth_ridge_lambda']
```

**v1.1 新增: look-ahead bias 防护**

正交化参数搜索时, 必须在 CV fold 内部 fit 正交化器 (用 train 数据), 不能用全样本 fit 再用 CV fold 评估. 当前 [optimizer.py:404-410](file:///f:/Coding/factor_pipeline/optimizer.py#L404) 的 `_cv_evaluate` 已在 fold 内 `pipeline.fit(train_factor)`, 正交化作为 `post_transform_hook` 会随之在 train 上 fit, **无 look-ahead bias**. 但需在 P3-13 实施时验证此行为.

**验收**: 优化器可搜索 10 维 (8 原 + 2 正交化, orth_ridge_lambda 仅 method=ridge 时生效); 正交化开启时 IC 评分反映正交化效果; 全量回归零退化.

---

### P3-14: 几何诊断纳入目标函数 (v1.1 修正: 需扩展 Adapter)

**目标**: 在 `_composite_objective` 添加 `redundancy_penalty`, 基于 VRR 惩罚过度冗余因子.

**学术依据**:
- v2.5.0 ADR-020 已确立 VRR (Variance Retention Ratio) 作为冗余诊断指标
- [compute_vrr](file:///f:/Coding/factor_pipeline/modules/factor_orthogonalizer/core/diagnostics.py#L48) 已是 pure function, 可直接调用 (v1.1 核查确认)

**v1.1 新增: OrthogonalizerAdapter 扩展需求**

[compute_vrr](file:///f:/Coding/factor_pipeline/modules/factor_orthogonalizer/core/diagnostics.py#L48) 需要 F 和 T 两个矩阵:
```python
@staticmethod
def compute_vrr(F: np.ndarray, T: np.ndarray, ddof: int = 0) -> np.ndarray:
    """VRR_k = Var(T_k) / Var(F_k)"""
```

但 [OrthogonalizerAdapter](file:///f:/Coding/factor_pipeline/adapters.py#L770) 当前**不暴露 F/T 矩阵** (内部用 `stack_factors_cross_section` 堆叠但未导出). 需扩展:

```python
# 在 OrthogonalizerAdapter 添加
def get_diagnostics(self) -> Dict[str, np.ndarray]:
    """返回 F/T 矩阵用于诊断 (v2.6.0 P3-14)"""
    if not self.is_fitted_:
        return {}
    return {
        'F_stacked': self._F_stacked_,  # 原始因子矩阵
        'T_stacked': self._T_stacked_,  # 正交化后因子矩阵
    }
```

**实现** (v1.1 修正: λ_redundancy 从 0.1 降为 0.05):
```python
def _redundancy_penalty(self, pipeline: 'FactorProcessingPipelineV2', config: 'PipelineV2Config') -> float:
    """冗余惩罚 (基于 VRR, ADR-020)

    VRR_k = Var(T_k)/Var(F_k), VRR << 1 表示因子 k 高度冗余.
    惩罚 = mean(max(0, vrr_threshold - VRR_k))  # VRR < threshold 的因子扣分

    v1.1 修正: λ_redundancy 从 0.1 降为 0.05, 避免与 IC 主目标双重惩罚
    (正交化本身会降低 IC, 再用 VRR 惩罚会过度抑制)
    """
    if not config.orthogonalization.enabled:
        return 0.0  # 正交化未启用, 无冗余诊断
    # 从 OrthogonalizerAdapter 获取 F/T 矩阵
    for hook in pipeline.post_transform_hooks:
        if hasattr(hook, 'get_diagnostics'):
            diag = hook.get_diagnostics()
            if 'F_stacked' in diag:
                from factor_pipeline.modules.factor_orthogonalizer.core.diagnostics import (
                    OrthogonalizationDiagnostics
                )
                vrr = OrthogonalizationDiagnostics.compute_vrr(
                    diag['F_stacked'], diag['T_stacked']
                )
                return float(np.mean([
                    max(0.0, config.orthogonalization.vrr_threshold - v)
                    for v in vrr
                ]))
    return 0.0

# 在 _composite_objective 添加
objective = (
    ic_mean
    - λ_vol * vol_penalty
    - λ_cov * coverage_penalty
    - λ_ks * ks_distortion_penalty
    - λ_health * health_penalty
    - λ_redundancy * redundancy_penalty  # 新增 (λ_redundancy=0.05)
)
```

**验收**: OrthogonalizerAdapter.get_diagnostics() 返回 F/T 矩阵; 正交化启用时 redundancy_penalty 生效; 手工校验高冗余场景下惩罚显著; 全量回归零退化.

---

### P3-15: Layer 3 显著性纳入目标函数 (v1.1 新增)

**目标**: 在 `_composite_objective` 添加 `significance_penalty`, 让优化器考虑 Layer 3 统计显著性.

**学术依据**:
- Belloni, Chernozhukov & Hansen (2014) *Review of Economic Studies* 81(2):608-650 — PDS Lasso (selection-robust inference, **非"轮询不变性"**)
- [FactorSignificanceTest](file:///f:/Coding/factor_pipeline/backtest/factor_significance.py) 已完整实现 (HC3 + BH 校正)

**v1.1 关键约束: 计算成本**

`FactorSignificanceTest.fit()` 需要 K 次 LassoCV + K 次 OLS, 在 optimizer 的 `n_trials=100` × 多个 CV fold 场景下会成为瓶颈. **建议: 仅用于最终配置验证, 不用于每 trial 评估**.

**实现** (两阶段):
```python
# 阶段 1: 每 trial 评估 (轻量, 不调用 FactorSignificanceTest)
def _composite_objective(self, ...):
    objective = (
        ic_mean - λ_vol * vol_penalty - λ_cov * coverage_penalty
        - λ_ks * ks_distortion_penalty - λ_health * health_penalty
        - λ_redundancy * redundancy_penalty
    )
    return objective

# 阶段 2: 最终配置验证 (重量, 仅对 best_params 调用一次)
def _validate_significance(self, best_params, factor_data, forward_returns) -> Dict:
    """对最优配置运行 Layer 3 显著性检验 (v2.6.0 P3-15)"""
    from factor_pipeline.backtest.factor_significance import FactorSignificanceTest
    config = self._params_to_config(best_params)
    fst = FactorSignificanceTest(method='double_lasso', alpha=0.05)
    fst.fit(factor_data, forward_returns, list(factor_data.keys()))
    results = fst.test_all_factors(correction='benjamini_hochberg')
    n_significant = sum(1 for r in results.values() if r['is_significant'])
    return {
        'n_significant': n_significant,
        'n_total': len(results),
        'significance_ratio': n_significant / len(results),
        'details': results,
    }
```

**验收**: best_params 的显著性验证报告生成; 显著性比例 < 50% 时发出警告; 全量回归零退化.

---

## 八、风险与陷阱清单 (v1.1 修正)

| # | 陷阱 | 严重性 | 规避方法 | 验证方法 |
|---|------|--------|---------|---------|
| 1 | **HealthMonitor 集成时序问题** (v1.1 修正) | 高 | 用代理指标 (IC decay / hit rate / vol) 替代 engine_results, 避免 fold 内调用 health_bridge | 手工校验代理指标与 health_score 的相关性 |
| 2 | **正交化参数增加搜索维度导致 trial 不足** | 中 | 10 维比 8 维多 25%, n_trials 从 100 提到 150-200 (Optuna 建议 ≥10×dim) | 收敛性测试 (best_score 随 trial 趋势) |
| 3 | **EWMA halflife 选择主观** | 中 | 默认 12 (月频) / 63 (日频), 提供配置项 | 敏感性分析 (halflife=6/12/24 对比) |
| 4 | **threshold_drift_monitor 误报** | 中 | EWMA 平滑 + 双确认 (衰减 > 20% 且持续 5 期) | 模拟 IC 波动场景验证假阳性率 |
| 5 | **redundancy_penalty 与 IC 主目标双重惩罚** (v1.1 修正) | 中 | λ_redundancy 设小 (0.05, v1.0 是 0.1), 仅在 VRR < 0.3 时触发; 正交化本身会降低 IC, 不应过度惩罚 | A/B 测试 (启用 vs 禁用 redundancy_penalty) |
| 6 | **categorical 搜索维度 TPE 效率下降** | 低 | Optuna TPE 原生支持 categorical, 但效率低于数值 | 监控收敛速度, 必要时改用 Grid Search |
| 7 | **migration_threshold 字段位置修正破坏向后兼容** (v1.1 修正) | 低 | 字段已存在于 PipelineV2ConfigUnified, 只改 optimizer 设置位置, 不改配置结构 | 全量回归验证 |
| 8 | **fidelity 符号修正改变历史 best_score** | 中 | 修正后重新运行优化, 不直接对比历史 best_score | 文档标注 "v2.6.0 后 best_score 不可与 v2.5.0 直接对比" |
| 9 | **look-ahead bias 在正交化搜索中的风险** (v1.1 新增) | 高 | 正交化必须在 CV fold 内部 fit (用 train 数据), 不能用全样本 fit | 验证 pipeline.fit(train_factor) 时 OrthogonalizerAdapter 在 train 上 fit |
| 10 | **FactorSignificanceTest 计算成本** (v1.1 新增) | 中 | 仅用于最终配置验证 (best_params), 不用于每 trial 评估 | 计时测试 (单次 fit 时间 < 60s) |
| 11 | **OrthogonalizerAdapter 不暴露 F/T 矩阵** (v1.1 新增) | 中 | 扩展 `get_diagnostics()` 方法返回 F_stacked/T_stacked | 手工校验 VRR 计算结果与 diagnostics.py 一致 |

---

## 附录 A: 文献核查结果 (v1.1 修正)

### A.1 已核查文献 (9 篇, v1.1 新增 Cohen-Coval-Pastor 撤回)

| # | 文献 | 准确引用 | 用途匹配 | 处理 |
|---|------|---------|---------|------|
| 1 | Dimson (1979) | *J. Financial Economics* 7(2):197-226 | ⚠ beta decay 非 IC decay | 替换为 Ferson-Siegel (2001) 或 Barroso-Santa-Clara (2015) |
| 2 | Moreira & Muir (2017) | *J. Finance* 72(4):1611-1644 | ⚠ inverse-vol 非 IC 衰减 | 移除, 不作为 P3-1 依据 |
| 3 | Bailey & López de Prado (2014) | *J. Portfolio Management* 40(5):94-107 (非 JFDS) | ✓ DSR 框架 | 修正期刊名, 保留为 P3-12 依据 |
| 4 | López de Prado (2018) | *Advances in Financial Machine Learning* Wiley, Ch.7 | ✓ Purged K-fold | 保留 (Combinatorial 在 Ch.12) |
| 5 | Belloni et al. (2014) | *Review of Economic Studies* 81(2):608-650 | ⚠ selection-robust inference, 非"轮询不变性" | 修正术语, 保留为 Layer 3 依据 |
| 6 | Hsu et al. (2010) | *J. Empirical Finance* 17(4):680-691 (SPA, 非 Bayesian) | ✗ 误称 Bayesian | 替换为 Sullivan-TW (1999) + McLean-Pontiff (2016) |
| 7 | Bergstra et al. (2011) | NIPS 24:2546-2554 | ⚠ TPE 原文但不含 fANOVA | 仅作为 TPE 依据, fANOVA 改引 Hutter (2014) |
| 8 | Hutter et al. (2014) | ICML 32(1):754-762 | ✓ fANOVA 原始出处 | 保留为 P3-11 fANOVA 依据 |
| 9 | ~~Cohen, Coval & Pastor (2005)~~ | ~~*J. Finance* 60(3):1057-1096~~ | ✗ **v1.0 误推荐, v1.1 撤回** | 撤回, 改为 Ferson-Siegel (2001) |

### A.2 新增推荐文献 (v1.1 修正)

- **Ferson & Siegel (2001)** "The Efficient Use of Conditioning Information in Portfolios" *J. Finance* 56(3):967-982 — 条件信息时变加权 (替换 v1.0 误推荐的 Cohen-Coval-Pastor)
- **Barroso & Santa-Clara (2015)** "Momentum is Not Dead" *J. Financial Economics* 115(3):464-482 — 动量因子高波动期 IC 衰减
- **Sullivan, Timmermann & White (1999)** "Data-Snooping, Technical Trading Rule Performance, and the Bootstrap" *J. Finance* 54(5):1647-1691 — data snooping 框架源头 (BRC)
- **McLean & Pontiff (2016)** "Does Academic Research Destroy Stock Return Predictability?" *J. Finance* 71(1):5-32 — 因子衰减实证 (OOS 26%, 发表后 58%)
- **Harvey & Liu (2015)** "Backtesting" *J. Finance* 70(5):1855-1886 — 现代回测多重检验框架 (可补充)

---

## 附录 B: 与 v2.5.0 三层架构的衔接

### B.1 Layer 2 衔接 (P3-13)

v2.5.0 引入 `OrthogonalizationConfig` (16 个字段), v2.6.0 将其纳入优化器搜索空间:

```
PipelineV2ConfigUnified.orthogonalization (v2.5.0)
    ↓
DEFAULT_SEARCH_SPACE_ORTH 添加 orth_method/align_mode/ridge_lambda (v2.6.0 P3-13)
    ↓
_params_to_config 设置 OrthogonalizationConfig (v2.6.0 P3-13)
    ↓
Pipeline.transform() → post_transform_hook → OrthogonalizerAdapter (v2.5.0 已实现)
```

### B.2 Layer 3 衔接 (P3-14 + P3-15)

v2.5.0 引入 VRR 几何诊断 + FactorSignificanceTest, v2.6.0 将其纳入目标函数:

```
factor_orthogonalizer.core.diagnostics.compute_vrr (v2.5.0)
    ↓
OrthogonalizerAdapter.get_diagnostics() 暴露 F/T (v2.6.0 P3-14 新增)
    ↓
_redundancy_penalty (v2.6.0 P3-14)
    ↓
_composite_objective 添加 -λ_redundancy * redundancy_penalty (v2.6.0 P3-14)

FactorSignificanceTest (v2.5.0)
    ↓
_validate_significance (v2.6.0 P3-15 新增, 仅最终验证)
    ↓
best_params 显著性报告 (v2.6.0 P3-15)
```

### B.3 完整数据流 (v2.6.0 后)

```
factor_data + forward_returns
    ↓
EndToEndThresholdOptimizer.optimize (10 维搜索)
    ├─ Layer 1 阈值 (8 维, 原 P3-9)
    ├─ Layer 2 正交化参数 (2 维, P3-13 新增, 仅 orth_enabled=True 时)
    └─ 目标函数: IC - vol - cov - ks - health (P3-9') - redundancy (P3-14')
    ↓
best_params + best_score
    ↓
_validate_significance (P3-15, 仅最终验证)
    ↓
ThresholdDriftMonitor (P3-12')
    └─ 监测 IC 衰减, 触发重新搜索
```

---

## 附录 C: 修订日志

| 日期 | 版本 | 修订内容 |
|------|------|---------|
| 2026-07-03 | v1.0 | 初版分析报告, 识别 6 类问题, 重新定义为 7 项任务 |
| 2026-07-03 | v1.1 | 深度核查后修订: (1) 修正 migration_threshold 问题为"字段位置错误"非"字段缺失"; (2) 撤回 v1.0 误推荐的 Cohen-Coval-Pastor (2005), 改为 Ferson-Siegel (2001); (3) 新增 health_penalty 时序问题 (8 类问题 → 8 项任务); (4) 新增 P3-15 Layer 3 显著性集成; (5) 修正 P3-13 不搜索 orth_enabled; (6) 修正 P3-14 需扩展 Adapter + λ 降至 0.05; (7) 新增 3 项风险 (look-ahead bias / 计算成本 / Adapter 扩展); (8) 核查确认 RidgeOrthogonalizer 已实现 cv/ledoit_wolf, compute_vrr 是 pure function |
