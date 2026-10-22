# EXECUTION v3.3.1 — 插补模块 P2 完成

> **版本**: v3.3.1
> **日期**: 2026-07-27
> **范围**: 插补模块 (factor_imputer) P2 任务全量完成 + 3 项学术引用修正
> **前置文档**: [analysis/IMPUTER_LOOKAHEAD_FIX_PLAN.md](analysis/IMPUTER_LOOKAHEAD_FIX_PLAN.md) v2.3
> **关联文档**: [ARCHITECTURE.md](ARCHITECTURE.md) §6.3 | [DEV_PROGRESS.md](DEV_PROGRESS.md) §3 | [../CHANGELOG.md](../CHANGELOG.md)

---

## §1 概览

v3.3.0 完成后,对插补模块进行 P2 阶段收尾,包含 3 项学术引用修正 + 3 项 P2 任务 (向量化 + e2e 测试 + 消融实验)。

**核心产出**:
- 3 项学术引用修正 (Little & Rubin 术语 / Breiman 2001 多输出 RF / Lopez de Prado 章号)
- P2-1: `_transform_rf_shared` 向量化 (1 次 predict 替代 N 次循环)
- P2-3: 9 项端到端测试 (含静态扫描 + 严格因果性)
- P2-4: 10 项消融实验 (含 IC 范围 + 严格因果性消融)
- 全量回归: 803 passed / 10 skipped / 0 regressions

---

## §2 任务详情

### §2.1 修正 1: Little & Rubin §4.3 术语错误

**问题**: 原引用使用 "因果填充原则" 作为 Little & Rubin (2002) §4.3 的术语,但该术语非 Little & Rubin 标准术语。

**修正**: 改为 "fill within-unit first, then across-units" + 标注非标准术语,并说明全书核心是 MAR/ignorability/MI 框架。

**变更位置**: [tests/unit/test_imputer_lookahead_fix.py:11-13](../tests/unit/test_imputer_lookahead_fix.py#L11-L13)

```python
# 修正前
- Little & Rubin (2002) §4.3: 因果填充原则

# 修正后
- Little & Rubin (2002) §4.3: fill within-unit first, then across-units
  (注: 原术语"因果填充原则"非 Little & Rubin 标准术语, 此处按 CHANGELOG.md
   核实后的实际内容修正; 全书核心是 MAR/ignorability/MI 框架)
```

### §2.2 修正 2: Breiman 2001 多输出 RF 补专门文献

**问题**: Breiman (2001) "Random Forests" 是 RF 奠基论文,但未明确讨论 multi-output RF,作为共享 RF 方案的唯一引用不严谨。

**修正**: 新增 Segal & Xiao (2011) WIREs DMKD (多输出 RF 方法论奠基) + van der Westhuizen et al. (2023) Geoderma (MRF 与单变量 RF 精度相当的实证证据)。

**变更位置**: [docs/analysis/IMPUTER_LOOKAHEAD_FIX_PLAN.md:520-521](analysis/IMPUTER_LOOKAHEAD_FIX_PLAN.md#L520-L521)

```python
# 修正后
学术支撑: Segal & Xiao (2011) WIREs DMKD — 多输出 RF 方法论奠基;
          van der Westhuizen et al. (2023) Geoderma — MRF 与单变量 RF 精度相当的实证证据
```

### §2.3 修正 3: Lopez de Prado §7 章号核实

**问题**: 原引用标注 Lopez de Prado (2018) §7 "Purged K-Fold Cross-Validation",但 §7 章号未能从数据库逐章核验。

**修正**: 改为 "Chapter on Cross-Validation Methods in Finance" 保守引用方式 (附 ISBN 978-1-119-44811-0 证明书存在)。

**变更位置**: [tests/unit/test_imputer_lookahead_fix.py:15-18](../tests/unit/test_imputer_lookahead_fix.py#L15-L18)

```python
# 修正前
- Lopez de Prado (2018) §7: Purged K-Fold 信息泄漏

# 修正后
- Lopez de Prado (2018), Chapter on Cross-Validation Methods in Finance:
  Purged K-Fold 信息泄漏
  (注: §7 章号未能从数据库逐章核验, 改用保守引用方式;
   书本身存在, ISBN 978-1-119-44811-0)
```

### §2.4 P2-1: 向量化剩余 for 循环

**目标**: 向量化 `_transform_rf_shared` 中的 `for t in missing_rows` 循环。

**实现**: [modules/factor_imputer/core/imputers.py:587-645](../modules/factor_imputer/core/imputers.py#L587-L645)

**关键改动**:
- 原: 对每个 missing row 单独构造特征 + 单独 scaler.transform + 单独 model.predict (N 次调用)
- 新: 一次性构造所有 missing rows 的特征 + 一次 scaler.transform + 一次 model.predict (1 次调用)
- 用 `missing_mask` 一次性填充 (不覆盖已有值)

**等价性验证**: 新增 `test_shared_model_batch_equivalent_to_per_row` 测试,验证批量 predict 与逐行 predict 数值一致 (1e-12 精度)。

**决策: 保留 for 循环的位置**:
1. **KNN walk_forward** (`_transform_knn_walk_forward`): 因果算法本质,每个 (asset, t) 用不同训练集 [0, t-1],**不能向量化**
2. **FactorSpecificImputer missing indicator** (`transform` L687-690): 单列赋值已是 O(T),pd.concat 整批添加反而引入 DataFrame 拷贝 (实测无收益)

### §2.5 P2-3: 端到端测试 全管线无前视

**目标**: 通过 ImputerAdapter (生产路径) 完整跑 fit + transform,验证因果性。

**新增测试**: [tests/integration/test_imputer_e2e_causal.py](../tests/integration/test_imputer_e2e_causal.py)

| 测试类 | 测试数 | 验证内容 |
|--------|--------|---------|
| `TestE2ECausalProperty` | 2 | ffill_ts 截断不变性 + 无未来异常值泄漏 |
| `TestE2ELookaheadSafeOnOff` | 2 | lookahead_safe=True/False 两条路径都跑通 |
| `TestE2EAllStrategiesCausal` | 1 | cross_sectional 因果性 (参数化) |
| `TestE2ESourceScan` (新增) | 2 | 静态扫描 adapters.py / imputers.py 无 .bfill() |
| `TestE2EStrictCausality` (新增) | 2 | 严格因果: 截断任意时间点历史不变 + 修改未来数据历史不变 |

**关键测试** (严格因果性):

```python
def test_ffill_ts_no_future_dependency(self, e2e_panel):
    """ffill_ts: 修改未来数据 (t > t_check), 历史 [0, t_check] 应不变."""
    df_modified = df.copy()
    df_modified.iloc[10, :] = 9999.0   # 修改未来数据
    df_modified.iloc[11, :] = -9999.0
    t_check = 8

    # 两次 fit+transform, 对比 [0, t_check-1]
    np.testing.assert_allclose(
        r_orig.iloc[:t_check].values,
        r_mod.iloc[:t_check].values,
        rtol=1e-10, atol=1e-10,
    )
```

### §2.6 P2-4: 消融实验 lookahead_safe ON vs OFF

**目标**: 验证 lookahead_safe 切换对插补结果的影响。

**新增测试**: [tests/integration/test_imputer_ablation_lookahead.py](../tests/integration/test_imputer_ablation_lookahead.py)

| 测试类 | 测试数 | 验证内容 |
|--------|--------|---------|
| `TestAblationLookaheadSafe` | 3 | ON/OFF 跑通 + 前期填充值不同 + KNN walk_forward vs legacy 差异 |
| `TestAblationAdapterLevel` | 3 | lookahead_safe 透传 + ON/OFF 结果不同 |
| `TestAblationICRange` (新增) | 2 | IC ∈ [-1, 1] (cross_sectional + KNN walk_forward) |
| `TestAblationStrictCausality` (新增) | 2 | ON 满足截断不变性 + OFF 不满足 (验证切换确实改变语义) |

**关键测试** (严格因果性消融):

```python
def test_off_path_not_strictly_causal(self):
    """lookahead_safe=False: legacy 路径不满足严格因果 (含未来信息).

    legacy 路径用全样本 median, 截断后 median 会变 → 历史填充值会变.
    """
    # 全样本 fit+transform vs 截断 fit+transform
    # 若历史填充值相同 → legacy 路径竟满足因果性 (预期: 应不同)
    if r_full.iloc[:t_trunc].equals(r_trunc.iloc[:t_trunc]):
        nan_count_in_history = df_full.iloc[:t_trunc].isnull().sum().sum()
        if nan_count_in_history > 0:
            pytest.fail("lookahead_safe=False legacy 路径竟满足因果性")
```

---

## §3 测试结果

### §3.1 插补相关测试 (52 项)

```
============================= 52 passed in 5.21s =============================
```

| 测试文件 | 通过 / 总数 |
|---------|------------|
| `test_imputer_lookahead_fix.py` | 33 / 33 |
| `test_imputer_e2e_causal.py` | 9 / 9 |
| `test_imputer_ablation_lookahead.py` | 10 / 10 |

### §3.2 全量回归

```
803 passed, 10 skipped, 0 failed, 0 regressions in 391.33s
```

---

## §4 排除幻觉验证

### §4.1 静态扫描

| 文件 | 扫描项 | 结果 |
|------|--------|------|
| `modules/factor_imputer/core/imputers.py` | `.bfill()` 调用 | 0 处残留 ✅ |
| `adapters.py` | `.bfill()` 调用 | 0 处残留 ✅ |

### §4.2 等价性验证

| 测试 | 验证内容 | 精度 |
|------|---------|------|
| `test_shared_model_batch_equivalent_to_per_row` | 批量 predict vs 逐行 predict | 1e-12 |

### §4.3 文档一致性

- `IMPUTER_LOOKAHEAD_FIX_PLAN.md` v2.2 → v2.3: §0.1 状态总览 + §8.3 P2 全部 ✅
- `ARCHITECTURE.md` §6.3 ImputerAdapter 契约与代码一致
- `DEV_PROGRESS.md` §3 v3.3.1 任务清单与实际变更一致

---

## §5 风险评估

| 风险 | 严重度 | 缓解 |
|------|--------|------|
| 批量 predict 浮点误差累积 | 低 | 1e-12 等价性测试覆盖 |
| KNN walk_forward 性能瓶颈 | 中 | 因果算法本质, 保留 for 循环; 长期可改用 rolling window 训练 |
| missing indicator for 循环 | 极低 | 单列赋值 O(T), 实测无收益向量化 |

---

## §6 后续待办

| # | 任务 | 优先级 | 来源 |
|---|------|--------|------|
| 1 | MissingTypeDiagnoser 因果版本 (expanding EM) | P3 | IMPUTER_LOOKAHEAD_FIX_PLAN §8.4 |
| 2 | 删除非生产路径死代码 (HierarchicalImputer) | P3 | IMPUTER_LOOKAHEAD_FIX_PLAN §8.4 |
| 3 | `types.py` 重命名 (避免遮蔽标准库) | P3 | ARCHITECTURE.md §9.1 |

---

## §7 验收 Checklist

- [x] 3 项学术引用修正全部落实 (源码 + 文档)
- [x] P2-1 向量化完成 (含等价性测试)
- [x] P2-3 端到端测试 9 项全部通过
- [x] P2-4 消融实验 10 项全部通过
- [x] 静态扫描无 .bfill() 残留
- [x] 全量回归 803 passed / 0 regressions
- [x] 文档同步: IMPUTER_LOOKAHEAD_FIX_PLAN v2.3 + ARCHITECTURE + DEV_PROGRESS
- [x] CHANGELOG 新增 v3.3.1 条目
