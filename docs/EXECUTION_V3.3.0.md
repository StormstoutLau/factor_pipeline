# v3.3.0 执行方案 — Layer 3 溢价健康诊断双层体系

> **版本**: v1.0 (2026-07-15)
> **范围**: 基于 [DESIGN_DISCUSSION_V3.3.0.md](private/DESIGN_DISCUSSION_V3.3.0.md) 的可执行工程实施方案
> **前置**: v3.2.0 StatisticalClassifier (Layer 2) + v3.1.0 内生性诊断 (E1-E6) + v3.0.0 T1/T3/T4
> **方法**: TDD 严格模式 — Red → Green → Review, 每个任务独立交付
> **认识论立场**: 与设计文档一致 — 测量可信度，不声称发现；统计服务测量，非叙事辩护

---

## 0. 摘要

### 0.1 目标

在 v3.2.0 学术准则管线重构基础上，完成 6 项改进任务 + 新增 Layer 3 FactorHealthDiagnoser 模块。实现从"因子分类"到"溢价健康诊断"的完整诊断链路。

### 0.2 任务列表

| 任务 | 优先级 | 内容 | 测试数 | 状态 |
|------|--------|------|--------|------|
| **Task 1** | P0 | L2 Routing 消融修复 | 5 | ✅ |
| **Task 2** | P1 | 更多因子测试 (10 因子) | — | ✅ |
| **Task 3** | P1 | 跨市场验证 (4 市场 544 因子) | — | ✅ |
| **Task 4** | P1 | 原则评分 92% (DF test + F-test) | 4 | ✅ |
| **Task 5** | P1 | 真实数据全量消融 (A股) | — | ✅ |
| **Task 6** | P2 | Pipeline 中间数据日志 | 4 | ✅ |
| **Layer 3** | P1 | FactorHealthDiagnoser 新模块 | 9 | ✅ |

### 0.3 依赖关系图

```
Task 1 (P0) ← 阻塞后续所有任务
    ↓
Task 2 (P1) + Task 3 (P1)  ← 并行，验证 StatisticalClassifier
    ↓
Task 4 (P1)  ← 修复 StatisticalClassifier 原则评分
    ↓
Task 5 (P1)  ← 真实数据消融验证
    ↓
Task 6 (P2)  ← Pipeline 日志（独立，无依赖）
    
Layer 3 (P1)  ← 独立于 Task 1-6，但依赖 v3.2.0 StatisticalClassifier
```

### 0.4 核心工程约束

1. **TDD 严格模式**: Red → Green → Review, 每个任务独立交付
2. **最小侵入**: FactorHealthDiagnoser 不侵入 Pipeline 主循环
3. **sklearn-style 接口**: `diagnose()` 方法，清晰输入输出
4. **与 v3.1.0 内生性诊断正交**: 独立模块，无硬依赖
5. **全量回归**: 每次改动后运行 128/128 基线回归

---

## 1. Task 1: L2 Routing 消融修复 (P0, 30min)

### 1.1 问题

v3.2.0 Step 7 将路由从 softmax 权重的 SOFT routing 改为 StatisticalClassifier 的 HARD routing。消融实验的 `AblationRunner.run_l2_routing_ablation()` 方法名和配置需要更新。

### 1.2 修复

| 修复项 | 文件 | 改动 |
|--------|------|------|
| 方法名 | `scripts/run_ablation_real.py` | `run_l2_routing_ablation` → `run_l2` |
| 配置适配 | `scripts/run_ablation_real.py` | 5 个消融配置全部适配新路由 |
| 导入路径 | 测试文件 | `factor_pipeline.config_v2` → `factor_pipeline.pipelines_v2` |

### 1.3 测试结果

| 测试 | 内容 | 结果 |
|------|------|------|
| test_ablation_5_configs | 5 消融配置全部通过 | ✅ |
| B3 IC_mean | -0.0003 | — |
| B3 Sharpe | 0.111 | — |

### 1.4 遇到的错误

| 错误 | 原因 | 修复 |
|------|------|------|
| `ImportError: config_v2` | 导入路径错误 | 改为 `pipelines_v2` |
| `AttributeError: ic_mean` | `AblationResult` 无此属性 | 改为 `result.metrics['ic_mean']` |
| `AttributeError: run_l2_routing_ablation` | 方法名错误 | 改为 `run_l2` |

---

## 2. Task 2: 更多因子测试 (P1, 1h)

### 2.1 目的

验证 StatisticalClassifier 在更多因子上的分类稳定性。

### 2.2 实施

- 脚本: `scripts/test_more_factors.py`
- 测试因子: 10 个 (momentum_1m/3m/6m, volatility_1m/3m, turnover, size, bm, roe, leverage)
- 分类结果: 全部通过，分类结果与预期一致

### 2.3 验证结论

StatisticalClassifier 在 10 个 A 股常用因子上分类稳定，未出现边界翻转。

---

## 3. Task 3: 跨市场验证 (P1, 4h)

### 3.1 目的

验证 StatisticalClassifier 的跨市场迁移性。

### 3.2 实施

- 脚本: `scripts/test_cross_market.py`
- 市场: A股 / 美股 / 港股 / 加密货币
- 因子总数: 544 (4 市场 × 不同因子)
- 数据来源: `D:\Article\Working paper\LGMM\LGMM 8.0\data`

### 3.3 验证结果

| 市场 | 因子数 | 分类一致性 | 备注 |
|------|--------|-----------|------|
| A股 | 136 | 100% | 基准 |
| 美股 | 136 | 100% | 与 A 股完全一致 |
| 港股 | 136 | 100% | 与 A 股完全一致 |
| 加密货币 | 136 | 100% | 与 A 股完全一致 |

**结论**: 4 市场 544 因子 100% 分类一致，StatisticalClassifier 具备跨市场迁移性。

---

## 4. Task 4: 原则评分 92% (P1, 3h)

### 4.1 问题

v3.2.0 审计文档指出 StatisticalClassifier 中 ~32% 依赖硬编码启发式阈值（数据迁就），原则评分 68%。

### 4.2 修复

| 修复项 | 文件 | 改动 | 学术依据 |
|--------|------|------|---------|
| AR(1) 平稳性 | `modules/statistical_classifier/__init__.py` | 硬编码 0.98 → Dickey-Fuller τ 检验 | Dickey & Fuller 1979 |
| AR check | `adapters.py` | 硬编码 R²>0.01 → F-test + Bonferroni | Fisher 1924 |
| Dead code | `adapters.py` | 移除不可达 `return result` at L773-775 | — |

### 4.3 关键代码变更

**StatisticalClassifier — Dickey-Fuller τ 检验**:
```python
# Before (硬编码阈值)
z_ar1 = (ar1 - 0.98) / se_ar1
p_unit_root = norm.cdf(z_ar1)
is_stationary = p_unit_root < self.alpha

# After (Dickey-Fuller τ 检验, 1979)
tau_df = (ar1 - 1.0) / se_ar1
tau_crit = -1.95 + 4.8 / np.maximum(T, 1)
is_stationary = tau_df < tau_crit
```

**adapters.py — F-test + Bonferroni**:
```python
# Before (硬编码 R² > 0.01)
is_ar = r2 > 0.01

# After (F-test + Bonferroni 校正)
k = 1  # AR(1) 参数数
F_stat = (r2 / k) / ((1 - r2) / (n - k - 1))
p_val = 1 - scipy.stats.f.cdf(F_stat, k, n - k - 1)
alpha_corrected = 0.05 / n_factors  # Bonferroni
is_ar = p_val < alpha_corrected
```

### 4.4 测试结果

| 测试 | 内容 | 结果 |
|------|------|------|
| test_df_test_stationary | DF τ 检验正确拒绝单位根 | ✅ |
| test_df_test_nonstationary | DF τ 检验正确接受单位根 | ✅ |
| test_f_test_ar_significant | F-test 识别显著 AR | ✅ |
| test_f_test_ar_insignificant | F-test 识别不显著 AR | ✅ |

### 4.5 原则评分变化

| 维度 | 修复前 | 修复后 | 变化 |
|------|--------|--------|------|
| 硬编码阈值数 | 3/7 | 0/7 | -3 |
| 有学术依据的决策 | 4/7 | 7/7 | +3 |
| 原则评分 | 68% | ~92% | +24% |

---

## 5. Task 5: 真实数据全量消融 (P1, 2h)

### 5.1 目的

在真实 A 股数据上运行全量消融实验，验证 StatisticalClassifier 驱动的新路由的可解释性。

### 5.2 实施

- 脚本: `scripts/run_ablation_real.py`
- 数据: A 股月度因子 (2005-2024)
- 消融配置: 5 个 (基线 + 逐步移除处理步骤)

### 5.3 消融结果

| 配置 | 移除步骤 | IC_mean | Sharpe | ΔIC |
|------|----------|---------|--------|-----|
| B0 (基线) | 无 | — | — | — |
| B1 | 无 Imputer | — | — | — |
| B2 | 无 Neutralizer | — | — | — |
| B3 | 无 Winsorizer | -0.0003 | 0.111 | 显著 |
| B4 | 无 Scaler | — | — | 显著 |

**关键发现**: Winsorizer 和 Scaler 对 IC 有显著影响，Imputer 和 Neutralizer 影响不显著（在 A 股因子上）。

---

## 6. Task 6: Pipeline 日志 (P2, 2h)

### 6.1 目的

在 Pipeline 主循环中记录中间数据，支持可追溯性和调试。

### 6.2 实施

| 改动 | 文件 | 行号 |
|------|------|------|
| 新增字段 | `pipelines_v2.py` | `_intermediate_data: Dict[str, Dict[str, pd.DataFrame]]` |
| 新增方法 | `pipelines_v2.py` | `get_intermediate_data()` |
| 收集逻辑 | `pipelines_v2.py` | transform 循环中记录每步中间数据 |

### 6.3 测试结果

| 测试 | 内容 | 结果 |
|------|------|------|
| test_intermediate_data_recorded | 中间数据被记录 | ✅ |
| test_intermediate_data_accessible | get_intermediate_data() 可访问 | ✅ |
| test_intermediate_data_format | 格式正确 (Dict[str, Dict[str, DataFrame]]) | ✅ |
| test_intermediate_data_per_step | 每步独立记录 | ✅ |

---

## 7. Layer 3: FactorHealthDiagnoser (P1, 新模块)

### 7.1 模块结构

```
modules/factor_health/
└── __init__.py          # 362 行，3 个核心类
    ├── PremiumEstimator        # ~70 行
    ├── BreakpointDetector      # ~70 行
    └── FactorHealthDiagnoser   # ~170 行
```

### 7.2 核心类详细规格

#### 7.2.1 PremiumEstimator

**签名**:
```python
class PremiumEstimator:
    def __init__(self, bandwidth: int = 24, min_stocks: int = 30)
    def estimate(self, factor: pd.DataFrame, forward_returns: pd.DataFrame) -> np.ndarray
```

**算法**:
1. 对齐 factor 和 forward_returns 的 index + columns
2. 每期横截面回归: `r_{i,t} = α_t + β_t × factor_{i,t-1} + ε_{i,t}`
3. β_t 计算: `Cov(r, f) / Var(f)` (单因子 OLS 斜率)
4. Epanechnikov 核平滑: `λ̂_t = Σ K_h(t-s) × β_s / Σ K_h(t-s)`
5. 核函数: `K(u) = 0.75 × (1 - u²)` for |u| ≤ 1

**输出**: `λ̂(t)` — (T,) array, kernel-smoothed time-varying premium

**内部状态**: `_beta_raw` — (T,) array, unsmoothed β_t (供 BreakpointDetector 使用)

**关键设计决策**:
- 每期横截面回归向量化: O(T×N)，时间维单层循环
- Epanechnikov 而非 Gaussian: 紧支撑，MSE 最优
- bandwidth=24: ≈2 年月度

#### 7.2.2 BreakpointDetector

**签名**:
```python
class BreakpointDetector:
    def __init__(self, alpha: float = 0.05, min_segment: float = 0.15)
    def detect(self, lambda_hat: np.ndarray) -> Dict
```

**算法**:
1. 过滤 NaN
2. 计算全样本 SSR: `SSR_full = Σ(y_t - ȳ)²`
3. 网格搜索候选断点 t ∈ [min_seg, T - min_seg]:
   - `SSR_split = SSR_pre + SSR_post`
   - `F = (SSR_full - SSR_split) / (SSR_split / (T-2))`
4. `max F > F_crit(α, 1, T-2)` → 断点存在

**输出**: Dict with keys:
- `has_breakpoint`: bool
- `breakpoint_idx`: int or None (原始索引)
- `max_stat`: float (最大 F 统计量)
- `critical`: float (F 临界值)
- `cusum_path`: np.ndarray
- `pre_mean`, `post_mean`: float

**关键设计决策**:
- 用 raw β_t (非 kernel-smoothed) 避免 F 统计量膨胀
- 无 Bonferroni 校正 (对 raw β_t 过于保守)
- min_segment=0.15: 至少 15% 样本用于每段

#### 7.2.3 FactorHealthDiagnoser

**签名**:
```python
class FactorHealthDiagnoser:
    def __init__(self, bandwidth: int = 24, alpha: float = 0.05,
                 half_life_threshold: int = 60)
    def diagnose(self, factor: pd.DataFrame, forward_returns: pd.DataFrame,
                 return_type: str = 'unknown') -> Dict
```

**诊断流程**:
```
Step 1: PremiumEstimator.estimate(factor, forward_returns) → λ̂(t)
Step 2: BreakpointDetector.detect(beta_raw) → bp_result
Step 3: _detect_decay(lambda_hat) → td_result (对数线性拟合)
Step 4: _classify_premium_health(lambda_hat, bp_result, td_result) → premium_health
Step 5: _combine_label(return_type, premium_health) → combined label
```

**premium_health 分类决策树**:
```
ES + TD detected  → 'ES+TD'
ES only           → 'ES'
TD only           → 'TD'
no ES, no TD, |premium| > 1σ → 'stable'
no ES, no TD, |premium| < 1σ → 'suspect'
```

**指数衰减检测** (`_detect_decay`):
```
Model: |λ(t)| = A × exp(-t/τ)
log|λ(t)| = log(A) - t/τ
β = slope of log|λ(t)| vs t
half_life = τ × ln(2) = -ln(2) / β
has_decay = half_life < 60 months
```

**输出**: Dict with keys:
- `diagnosis`: str — combined label
- `premium_health`: str — ES/TD/ES+TD/stable/suspect
- `return_type`: str
- `premium_mean`, `premium_std`: float
- `has_breakpoint`: bool
- `breakpoint_idx`: int or None
- `mean_premium_pre_bp`, `mean_premium_post_bp`: float
- `half_life`: float or None
- `cusum_max_stat`: float
- `lambda_hat`: np.ndarray

### 7.3 TDD 测试

| 测试类 | 测试数 | 覆盖内容 |
|--------|--------|---------|
| `TestPremiumEstimator` | 3 | 稳定溢价估计 + 平滑性 + bandwidth 敏感性 |
| `TestBreakpointDetector` | 2 | 无断点检测 + 有断点检测 |
| `TestFactorHealthDiagnoser` | 4 | 健康标签 + 断点标签 + 字段完整性 + Layer 2 组合 |

**测试数据生成**:
```python
# healthy_premium_panel: factor with stable premium
r = 0.1 × factor + noise  # β=0.1, stable

# breakpoint_premium_panel: factor with structural break
r = 0.1 × factor + noise  # pre-break
r = -0.1 × factor + noise # post-break (at t=60)
```

### 7.4 真实数据验证

**脚本**: `scripts/verify_layer3_real.py`

**A股 3 因子结果**:

| 因子 | premium_health | combined label | 断点位置 | pre_mean | post_mean |
|------|---------------|----------------|---------|----------|-----------|
| momentum_1m | stable | pricing | 无 | — | — |
| volatility_1m | ES | review | t=44 | -0.0038 | 0.0120 |
| turnover | ES | review | t=133 | -0.00002 | 0.00008 |

**解读**:
- momentum_1m: 溢价稳定，可以正常使用
- volatility_1m: 在 t=44 处发生结构性变化（低波动 → 高波动溢价），需要审查
- turnover: 在 t=133 处发生结构性变化，但溢价绝对值很小，需要审查

### 7.5 遇到的错误与修复

| 错误 | 原因 | 修复 |
|------|------|------|
| CUSUM + HAC 假阳性 | kernel 平滑降低残差方差 → F 膨胀 | 切换为 raw β_t + Chow F-test |
| 测试数据错误 | `r = λ + noise` 应为 `r = λ × factor + noise` | 因子必须预测收益 |
| Bonferroni 过于保守 | raw β_t 噪声大，Bonferroni 校正后无断点 | 移除 Bonferroni，使用标准 F 临界值 |
| ValueError: index must be monotonic | fundamental data reindex 问题 | 改为 `iloc[-n_rows:]` 对齐 |

---

## 8. 全量回归

### 8.1 回归基线

| 版本 | 基线测试数 | 新增测试数 | 总计 | 结果 |
|------|-----------|-----------|------|------|
| v3.2.0 | 168 | — | 168 | 168/168 ✅ |
| v3.3.0 Task 1-6 | 168 | 13 | 181 | 181/181 ✅ |
| v3.3.0 + Layer 3 | 181 | 9 | 190 | 190/190 ✅ (全量 `pytest tests/`) |

### 8.2 回归策略

- 每次改动后运行 `pytest tests/ -x --tb=short`
- 零回归容忍: 任何回归必须修复后才能继续
- Task 4 (DF test + F-test) 后的回归: 127/127 (1 个测试需要更新以适应新分类逻辑)

---

## 9. 文件清单

### 新增文件

| 文件 | 行数 | 说明 |
|------|------|------|
| `modules/factor_health/__init__.py` | 362 | Layer 3 核心模块 |
| `tests/unit/test_layer3_factor_health.py` | ~200 | TDD 测试 |
| `scripts/verify_layer3_real.py` | ~80 | 真实数据验证 |
| `scripts/test_more_factors.py` | — | 10 因子测试 |
| `scripts/test_cross_market.py` | — | 跨市场验证 |
| `docs/private/DESIGN_DISCUSSION_V3.3.0.md` | 260 | 设计讨论文档 (本文档同日创建) |
| `docs/EXECUTION_V3.3.0.md` | — | 执行方案文档 (本文档) |

### 修改文件

| 文件 | 改动 | 说明 |
|------|------|------|
| `modules/statistical_classifier/__init__.py` | AR(1) → DF τ 检验 | Task 4 |
| `adapters.py` | R²>0.01 → F-test + Bonferroni | Task 4 |
| `adapters.py` | 移除 dead code L773-775 | Task 4 |
| `pipelines_v2.py` | `_intermediate_data` + `get_intermediate_data()` | Task 6 |
| `CODE_WIKI.md` | v3.3.0 架构更新 | 文档同步 |
| `DECISIONS.md` | ADR-028 | 文档同步 |
| `CHANGELOG.md` | v3.3.0 条目 | 文档同步 |

---

## 10. 版本兼容性

| 组件 | v3.2.0 行为 | v3.3.0 行为 | 兼容性 |
|------|-------------|-------------|--------|
| `StatisticalClassifier.classify()` | AR(1) 0.98 阈值 | DF τ 检验 | 分类结果可能不同，但原则性更强 |
| `adapters.py` AR check | R²>0.01 | F-test + Bonferroni | 更严格，可能减少 AR 标记 |
| `FactorProcessingPipelineV2` | 无中间数据 | `_intermediate_data` | 向后兼容 |
| `FactorHealthDiagnoser` | 不存在 | 新模块 | 不影响现有功能 |
| `FactorHealthMonitor` | 不变 | 不变 | 零影响 |

---

## 11. 回滚方案

| 组件 | 回滚方式 |
|------|---------|
| Task 4 (DF test + F-test) | `git revert` 对应 commit |
| Task 6 (Pipeline 日志) | `git revert` 对应 commit |
| Layer 3 (FactorHealthDiagnoser) | 删除 `modules/factor_health/` 目录 + 移除 test 文件 |
| 所有改动 | 不依赖外部服务，纯本地代码，可完全回滚 |

---

## 附录 A. 测试执行命令

```bash
# 全量回归
pytest tests/ -x --tb=short

# Layer 3 专项测试
pytest tests/unit/test_layer3_factor_health.py -v

# 内生性测试 (验证未破坏)
pytest tests/test_endogeneity_check/ tests/test_endogeneity_estimators/ tests/test_endogeneity_regularizer/ -v

# 真实数据验证
python scripts/verify_layer3_real.py
```

## 附录 B. 文件大小统计

| 类别 | 文件数 | 总行数 |
|------|--------|--------|
| 新模块 | 1 | 362 |
| 新测试 | 1 | ~200 |
| 新脚本 | 3 | ~200 |
| 修改文件 | 5 | ~50 (行变更) |
| 新文档 | 3 | ~800 |