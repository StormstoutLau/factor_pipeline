# EXECUTION — 技术债小包 (v3.4.11)

> **版本**: v1.0 (2026-11-16)
> **流程**: `docs/WORKFLOW_METHODOLOGY.md` §13.8 小任务裁剪 (步骤 5-6-9-10; 调研/设计内联)
> **范围**: 三项独立技术债 + 一项明确不修复

## §1 任务清单

| # | 任务 | 来源 | 结论 |
|---|------|------|------|
| T1 | `ledoit_wolf_hac_test` 移除未使用的 `alpha` 参数 | v3.4.10 审计 D2 | 实施 |
| T2 | `mean_diff_hac_statsmodels` 增加成对 complete-case | v3.4.10 RESEARCH O2 | 实施 |
| T3 | MAD 阈值参数化 (`adaptive_threshold` / `max_outlier_frac` 透传) | MAD 实验 §6 O2 | 实施 |
| T4 | 非生产路径解耦器数值修复 | PROJECT_STATUS 路演候选 | **不实施** (ADR-043 已弃用, 零生产调用) |

## §2 工程事实

| # | 事实 | 证据 |
|---|------|------|
| F1 | `ledoit_wolf_hac_test(returns_a, returns_b, alpha=0.05)` 的 `alpha` 在函数体内从未被读取 | [ablation_runner.py L46-L160](../../backtest/ablation_runner.py#L46-L160) |
| F2 | 唯一生产调用点在 `compare`, 传入 `self.alpha`; `alpha` 的判定仍在 `compare` 内完成 | [ablation_runner.py L1343](../../backtest/ablation_runner.py#L1343), L1389-L1394 |
| F3 | `mean_diff_hac_statsmodels` 未做 NaN/Inf 过滤, 仅测试引用 | [ablation_runner.py L144-L180](../../backtest/ablation_runner.py#L144-L180) |
| F4 | `ProcessingAdapter` 已接收 `max_outlier_frac` / `adaptive_threshold` (`_OUTLIER_DETECTOR_PARAM_KEYS`) | [adapters.py L53-L55](../../adapters.py#L53-L55), L423-L427 |
| F5 | `StaticFactorPipeline` 只透传 `outlier_method` / 两个分位点; 非分位方法不传 detector 参数 | [pipelines_v2.py L709-L732](../../pipelines_v2.py#L709-L732) |
| F6 | `PipelineV2Config` 已有 v3.4.7 三字段 `static_outlier_*` | [pipelines_v2.py L472-L475](../../pipelines_v2.py#L472-L475) |
| F7 | `_create_pipeline('static')` 从 config 注入三字段 | [pipelines_v2.py L1331-L1349](../../pipelines_v2.py#L1331-L1349) |
| F8 | `SmartOutlierDetector` 默认 `adaptive_threshold=True` / `max_outlier_frac=0.05`; 关闭后 MAD 阈值固定 3.0 | [transformers.py L30-L41](../../modules/factor_adaptive_winsor/core/transformers.py#L30-L41), L232-L249 |
| F9 | ADR-043 已弃用 `OptimizedARDecoupler` / `OptimizedCompositeDecoupler` / `TemporalDecoupler` | [DECISIONS.md L2967-L2981](../../DECISIONS.md#L2967-L2981) |

## §3 代码变更

### 3.1 T1 — 移除未使用参数 (`backtest/ablation_runner.py`)

```python
# 变更前
def ledoit_wolf_hac_test(
    returns_a: np.ndarray,
    returns_b: np.ndarray,
    alpha: float = 0.05,
) -> Tuple[float, float]:
...
            t_stat_hac, p_value_hac = ledoit_wolf_hac_test(exp_ls, ref_ls, self.alpha)

# 变更后
def ledoit_wolf_hac_test(
    returns_a: np.ndarray,
    returns_b: np.ndarray,
) -> Tuple[float, float]:
...
            t_stat_hac, p_value_hac = ledoit_wolf_hac_test(exp_ls, ref_ls)
```

docstring 的 `alpha: 显著性水平` Args 行同步删除。`compare` 的 `self.alpha` 判定逻辑不动。

### 3.2 T2 — `mean_diff_hac_statsmodels` 成对过滤

与 v3.4.10 主检验同口径:

```python
    returns_a = np.asarray(returns_a, dtype=float)
    returns_b = np.asarray(returns_b, dtype=float)
    T = min(len(returns_a), len(returns_b))
    returns_a = returns_a[:T]
    returns_b = returns_b[:T]

    # v3.4.11: 成对 complete-case, 与 ledoit_wolf_hac_test 同口径
    finite_mask = np.isfinite(returns_a) & np.isfinite(returns_b)
    n_valid = int(finite_mask.sum())
    if n_valid < 3:
        return 0.0, 1.0
    returns_a = returns_a[finite_mask]
    returns_b = returns_b[finite_mask]
    T = n_valid

    if maxlags is None:
        maxlags = max(1, int(4 * (T / 100) ** (2 / 9)))
```

### 3.3 T3 — MAD 阈值参数化

**(a) `pipelines_v2.py` `PipelineV2Config`** (L475 之后):

```python
    # v3.4.11: MAD/自适应类 detector 参数 (默认 = SmartOutlierDetector 默认, 零行为变更)
    static_outlier_adaptive_threshold: bool = True
    static_outlier_max_outlier_frac: float = 0.05
```

**(b) `StaticFactorPipeline.__init__`** (L711 之后):

```python
                 outlier_adaptive_threshold: bool = True,
                 outlier_max_outlier_frac: float = 0.05):
```

`outlier_kwargs` 构造改为:

```python
        if outlier_method in ('percentile', 'quantile'):
            outlier_kwargs = {
                'percentile_lower': outlier_percentile_lower,
                'percentile_upper': outlier_percentile_upper,
            }
        else:
            # v3.4.11: 非分位方法透传 detector 自适应参数
            outlier_kwargs = {
                'adaptive_threshold': outlier_adaptive_threshold,
                'max_outlier_frac': outlier_max_outlier_frac,
            }
```

**(c) `_create_pipeline('static')`** 增加两行转发:

```python
                outlier_adaptive_threshold=self.config.static_outlier_adaptive_threshold,
                outlier_max_outlier_frac=self.config.static_outlier_max_outlier_frac,
```

**口径**: `adaptive_threshold=False` → MAD 固定 3.0; `max_outlier_frac` 仅在
`adaptive_threshold=True` 时决定 `P95(|x−median|/MAD)` 的分位点。
默认值与原 detector 默认一致 → 输出逐位不变。

## §4 测试计划

| # | 用例 | 断言 |
|---|------|------|
| E1 | `test_mean_diff_hac_nan_pairwise` | a/b 不同位置 NaN → 结果等于联合掩码后调用; 有限 |
| E2 | `test_mean_diff_hac_insufficient_returns_no_evidence` | 有效配对 <3 → `(0.0, 1.0)` |
| E3 | `test_pipeline_default_detector_params` | config / adapter kwargs 默认 `True` / `0.05` |
| E4 | `test_pipeline_mad_adaptive_threshold_forwarded` | `adaptive_threshold=False` 传到 adapter kwargs |
| E5 | `test_create_pipeline_injects_detector_params` | `_create_pipeline('static')` 转发非默认值 |
| E6 | 既有套件 | T1/T2/T3 改动零回归 |

### 4.1 验收记录

| 项 | 实测 | 状态 |
|---|------|------|
| E1-E5 Red | 5 failed / 3 passed (既有 3 例通过) | ✅ |
| E1-E5 Green | **8 passed** (新增 5 + 既有 3) | ✅ |
| 定向 `test_ablation_runner.py` + `test_ablation_knob_wiring.py` | **123 passed** (6.35s) | ✅ |
| 定向 `test_pipelines_v2.py` + `test_adapters` + `test_ablation_decoupler_arm.py` | **46 passed** (5.73s) | ✅ |
| `tests/test_backtest` | **599 passed / 8 skipped** (573.34s; 基线 594 → +5) | ✅ |
| 全量 `tests/` | **1746 passed / 15 skipped / 0 failed** (1176.01s; 基线 1741 → +5) | ✅ |
| 版本统一 | **7 passed** + 手工 **6/6** | ✅ |

## §5 版本与兼容性

| 项 | 值 |
|---|---|
| 项目版本 | **3.4.11** (6 处锚点) |
| 缓存代际 | **`v2.3.0-cache`** (不变) |
| API 变更 | `ledoit_wolf_hac_test` 移除未使用的 `alpha` (仓内唯一调用点已同步) |
| 默认行为 | T2 仅影响含 NaN 输入; T3 默认值与 detector 一致 → 零变更 |
| 生产管线 | 仅新增可选配置字段 |

## §6 明确不实施

**T4 非生产路径解耦器数值修复**: `OptimizedARDecoupler` / `OptimizedCompositeDecoupler` /
`TemporalDecoupler` 已于 v3.4.1 (ADR-043) 弃用 — 保留导入 + 构造 `DeprecationWarning`,
零生产调用、零测试覆盖。对其做数值修复与「弃用」决策冲突, 且无任何下游收益。
PROJECT_STATUS 路标将该候选标注为「不修复」。

## §7 步骤 6 review 记录

| # | 检查项 | 结论 |
|---|--------|------|
| X1 | F1-F9 行号与 v3.4.10 工作区一致 | ✅ |
| X2 | 移除 `alpha` 后仓内无其他调用点 | ✅ grep 仅 `compare` + 测试 (2 参数) |
| X3 | T2 与 v3.4.10 主检验共用同一掩码语义 | ✅ |
| X4 | T3 默认值与 `SmartOutlierDetector.__init__` 默认逐值一致 | ✅ `True` / `0.05` |
| X5 | 非分位方法才透传, percentile 路径不受影响 | ✅ |
| X6 | 未新增依赖 / 未改缓存代际 / 未改生产默认 | ✅ |

**review 结论**: PASS。
