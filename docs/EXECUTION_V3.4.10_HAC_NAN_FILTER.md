# EXECUTION — HAC 检验 NaN 过滤 (v3.4.10)

> **版本**: v1.0 (2026-11-16)
> **上游**: [RESEARCH v1.0](../research/RESEARCH_HAC_NAN_FILTER.md) /
> [DESIGN v1.0](private/DESIGN_HAC_NAN_FILTER.md)
> **流程**: `docs/WORKFLOW_METHODOLOGY.md` §13.8 步骤 5-6

## §1 目标

1. `ledoit_wolf_hac_test` 对两条收益序列做**联合** `isfinite` 掩码 (成对 complete-case);
2. 带宽 `q` 与归一化基数改用清洗后样本量 `n`;
3. 有效配对 `n < 3` 返回 `(0.0, 1.0)`, 消除静默 NaN;
4. 其余函数 (`compare` / `compare_all` / `circular_block_bootstrap`) 零改动。

## §2 版本与缓存

| 项 | 值 |
|---|---|
| 项目版本 | **3.4.10** (6 处锚点) |
| 缓存代际 | **`v2.3.0-cache`** (不变) |
| 生产管线 | `pipelines_v2.py` / `adapters.py` **零改动** |
| 公开签名 | 不变 |

## §3 代码变更 (`backtest/ablation_runner.py::ledoit_wolf_hac_test`)

### 3.1 入口清洗 (替换 L68-L77)

变更前:

```python
    returns_a = np.asarray(returns_a, dtype=float)
    returns_b = np.asarray(returns_b, dtype=float)

    # 对齐长度
    T = min(len(returns_a), len(returns_b))
    returns_a = returns_a[:T]
    returns_b = returns_b[:T]

    # Newey-West 自动带宽
    q = max(1, int(4 * (T / 100) ** (2 / 9)))
```

变更后:

```python
    returns_a = np.asarray(returns_a, dtype=float)
    returns_b = np.asarray(returns_b, dtype=float)

    # 对齐长度
    T = min(len(returns_a), len(returns_b))
    returns_a = returns_a[:T]
    returns_b = returns_b[:T]

    # v3.4.10: 成对 complete-case — 联合丢弃非有限值 (NaN/±Inf).
    # 不能逐序列独立删除: Cov(SR_a, SR_b) 的交叉矩条件要求同一时刻配对.
    # 口径等价于 Datta & Du (2012) 的 Equal Spacing 估计量.
    finite_mask = np.isfinite(returns_a) & np.isfinite(returns_b)
    n_valid = int(finite_mask.sum())
    if n_valid < T:
        logger.debug(
            "ledoit_wolf_hac_test: 丢弃 %d 个非有限配对 (原始 T=%d, 有效 n=%d)",
            T - n_valid, T, n_valid,
        )
    if n_valid < 3:
        return 0.0, 1.0
    returns_a = returns_a[finite_mask]
    returns_b = returns_b[finite_mask]
    T = n_valid  # 带宽与归一化均基于清洗后样本

    # Newey-West 自动带宽
    q = max(1, int(4 * (T / 100) ** (2 / 9)))
```

### 3.2 docstring 增补 (Returns 段之后)

```python
    缺失值口径 (v3.4.10):
        两条序列按**成对联合**掩码丢弃 NaN/±Inf (等价于 Datta & Du 2012
        的 Equal Spacing 估计量), 带宽与归一化均基于清洗后样本; 有效配对
        < 3 时返回 (0.0, 1.0) = 无证据. 注意: 删除缺失会压缩时间轴,
        缺失点之后的滞后对应关系会前移; 缺失比例很低时可忽略.
```

### 3.3 复杂度

入口掩码 O(T); 核估计 O(T·q) 不变。无新增依赖 / 无新增循环。

## §4 测试计划 (`tests/test_backtest/test_ablation_runner.py::TestLedoitWolfHAC`)

| # | 用例 | 断言 |
|---|------|------|
| E1 | `test_nan_same_positions_equivalence` | 同位置 NaN 结果 = 显式删除这些时点后的干净序列 (rel=1e-12); p 有限 |
| E2 | `test_nan_different_positions_pairwise` | 结果 = 手工「截断→联合掩码→原式」值; 且 ≠ 逐序列独立删除结果 |
| E3 | `test_insufficient_valid_pairs_returns_no_evidence` | 2 个有效配对 → `(0.0, 1.0)` |
| E4 | `test_all_nan_series_returns_no_evidence` | 全 NaN → `(0.0, 1.0)` |
| E5 | `test_inf_treated_as_missing` | inf 与 NaN 等价; 结果有限 |
| E6 | `test_compare_hac_finite_with_nan_ls` | `compare.p_value_hac` 有限且 ∈[0,1]; 等于直接调用清洗后序列 |
| E7 | 既有 5 用例 | 全绿 (无缺失输入零影响) |

## §5 验收记录

| 项 | 实测 | 状态 |
|---|------|------|
| E1-E6 Red 阶段 | `TestLedoitWolfHAC` **6 failed / 5 passed** (失败项 = E1-E6) | ✅ |
| E1-E6 Green 阶段 | `TestLedoitWolfHAC` **11 passed** (既有 5 + 新增 6) | ✅ |
| E7 既有 5 用例 | 全绿 (含在 11 passed 内) | ✅ |
| 定向回归 `tests/test_backtest/test_ablation_runner.py` | **89 passed** (4.95s) | ✅ |
| 定向回归 `tests/test_backtest` | **594 passed / 8 skipped** (664.96s; v3.4.9 基线 588 → +6) | ✅ |
| 全量回归 | **1741 passed / 15 skipped / 0 failed** (1437.31s; v3.4.9 基线 1735 → +6) | ✅ |
| 版本统一 | **7 passed** + 手工校验 **6/6** | ✅ |

## §6 步骤 6 review 记录 (幻觉消除 #2)

| # | 检查项 | 结论 |
|---|--------|------|
| X1 | 变更前代码片段与工作区 L68-L77 逐字一致 | ✅ 一致 |
| X2 | 变更后代码使用的 `logger` 已在模块顶部定义 | ✅ 一致 (`logger = logging.getLogger(__name__)`) |
| X3 | `np.isfinite` / `np.ndarray` 布尔索引均为 NumPy 原生能力, 无版本假设 | ✅ 无新依赖 |
| X4 | 后续所有 `/ T` 与 `q` 均读取重赋值后的 `T`, 无残留旧基数 | ✅ 覆盖 L93-L138 |
| X5 | `n_valid < 3` 分支位于 `q` 计算之前, 不会访问空数组 | ✅ 提前返回 |
| X6 | E2 的「逐序列独立删除」对照不依赖未实现接口 | ✅ 测试内手工实现 |
| X7 | 未误改 `mean_diff_hac_statsmodels` / `compare` / bootstrap | ✅ 范围一致 |

**review 结论**: PASS, 无幻觉项。
