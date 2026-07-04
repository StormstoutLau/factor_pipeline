# v3.0.0 T4 执行方案 — Benjamini-Hochberg FDR 替代 Bonferroni

> **版本**: v1.1 (2026-07-04)
> **范围**: v3.0.0 T4 (P0) — KS 迁移检测校正方法 Bonferroni → BH
> **基础**: ANALYSIS_V3.0.0.md v1.1 §4 (T4 方案分析)
> **前置**: v2.6.0 E1-E9 全部完成 (918 passed + 6 skipped + 11 subtests)
> **方法**: 与 v2.6.0 EXECUTION 同样的 TDD 流程 — Red → Green → Refactor, 每阶段严格 review
> **v1.1 修订**: 根据 review (1 CRITICAL + 3 MAJOR + 5 MINOR + 4 NIT) 系统性修订, 详见末尾修订日志

---

## 0. 摘要

T4 是 v3.0.0 4 项任务中优先级最高 (P0)、改动最小、风险最低的任务。核心改动仅 1 个函数 (`_ks_migration_significance`), 将 KS 迁移检测的多重比较校正从保守的 Bonferroni 迁移到 Benjamini-Hochberg FDR。

### 0.1 改动边界 (基于调研)

| 文件 | 是否在 T4 范围 | 改动内容 | 行数估算 |
|------|---------------|---------|---------|
| [pipelines_v2.py](file:///f:/Coding/factor_pipeline/pipelines_v2.py) L332-346 | ✅ 是 | Bonferroni 公式 → BH 公式 | ~25 行 |
| [tests/test_backtest/verify_fix1_manual.py](file:///f:/Coding/factor_pipeline/tests/test_backtest/verify_fix1_manual.py) L97, L116-118, L125-140 | ✅ 是 | 手工校验断言公式同步改 BH | ~20 行 |
| [tests/manual/test_factor_significance_manual.py](file:///f:/Coding/factor_pipeline/tests/manual/test_factor_significance_manual.py) (新增类) | ✅ 是 | 新增 KS 迁移 BH 测试 | ~40 行 |
| [DECISIONS.md](file:///f:/Coding/factor_pipeline/DECISIONS.md) L86 后, L1547 | ✅ 是 | 追加 ADR-002a, 勾选 TODO | ~30 行 |
| [CHANGELOG.md](file:///f:/Coding/factor_pipeline/CHANGELOG.md) | ✅ 是 | 新增 v2.7.0 / T4 条目 | ~15 行 |
| [README.md](file:///f:/Coding/factor_pipeline/README.md) L239 | ✅ 是 | "Bonferroni 校正" → "BH FDR 校正" | ~3 行 |
| [README.en.md](file:///f:/Coding/factor_pipeline/README.en.md) L181 | ✅ 是 | "Bonferroni correction" → "BH FDR correction" (m1 补充) | ~1 行 |
| [CODE_WIKI.md](file:///f:/Coding/factor_pipeline/CODE_WIKI.md) | ✅ 是 | KS 迁移路径描述更新 (L135/L1462/L1509/L1512 至少 4 处) | ~5 行 |
| [optimizer.py](file:///f:/Coding/factor_pipeline/optimizer.py) | ❌ 否 | E7 已用 BH, 无需改动 | 0 |
| [tests/verify_objective_function.py](file:///f:/Coding/factor_pipeline/tests/verify_objective_function.py) L154-155 | ❌ 否 (调用方仅取 p_val, 行为语义变化但不破坏, m3 补充) | 调用 `_ks_migration_significance(raw, proc, alpha=0.05)`, 需在 CHANGELOG 注明行为变化 | 0 |
| [backtest/unified_drift.py](file:///f:/Coding/factor_pipeline/backtest/unified_drift.py) L147-152 | ❌ 否 (后续任务 T5/ADR-002b) | 滚动窗口多次 KS 无校正, 独立多重检验问题 | 0 |
| [backtest/factor_significance.py](file:///f:/Coding/factor_pipeline/backtest/factor_significance.py) | ❌ 否 | 已完整支持 BH, 仅作为参考实现 | 0 |
| **总计** | | | **~142 行** |

### 0.2 关键设计决策 (与 ANALYSIS v1.1 一致)

1. **追加 ADR-002a, 不修改 ADR-002**: ADR-002 已"已实施", 修改破坏历史可追溯性; ADR-002a 显式标注 "supersede ADR-002 的校正方法"
2. **unified_drift.py 不纳入 T4**: 滚动窗口多次 KS 是独立多重检验问题 (T5/ADR-002b 候选), 避免 T4 范围蔓延
3. **接口扩展新增 `correction_method: str` 参数**: 现有函数签名仅有 `alpha: float`, 不存在 `bonferroni_correction` 形参 (M3 修正); `bonferroni_correction: True` 仅是 details 字典中的字段, BH 路径下替换为 `correction_method: 'benjamini_hochberg'`, Bonferroni 路径下保留原字段
4. **判定逻辑**: `min(p_adj) < alpha` (与 factor_significance.py 一致)
5. **不引入新依赖**: BH 校正纯 numpy 实现 (参考 factor_significance.py:433-443), scipy.stats.ks_2samp 已是 REQUIRED 依赖

### 0.3 执行阶段总览

| 阶段 | 任务 | 优先级 | 依赖 | 测试数 | 关键文件 |
|------|------|--------|------|--------|---------|
| E1 | KS 迁移 BH 校正核心改动 + ADR-002a | P0 | 无 | ~6 个测试 (E1-T1~T6, 每个经 Red→Green 循环) | pipelines_v2.py, DECISIONS.md |
| E2 | 测试更新 (verify_fix1 + significance_manual) | P0 | E1 | ~4 新增 pytest (E2-T1~T4), 另有 verify_fix1_manual.py 3 处校验脚本修改不计入 pytest 数 (M2 修正) | verify_fix1_manual.py, test_factor_significance_manual.py |
| E3 | 文档同步 + 全量回归 + 手工校验 | P1 | E1, E2 | 0 (验证) | README, CHANGELOG, CODE_WIKI |

**推荐执行顺序**: E1 → E2 → E3 (串行, 严格依赖)
**估算**: 3 个 E 阶段, 比 v2.6.0 E2 (单字段位置修正) 略大, 比 v2.6.0 E7 (Layer 3 显著性) 小

---

## 1. E1: KS 迁移 BH 校正核心改动 + ADR-002a

### 1.1 目标

将 `_ks_migration_significance` 的多重比较校正从 Bonferroni 迁移到 BH, 并新增 ADR-002a 记录决策。

### 1.2 当前代码 (Red 阶段起点)

[pipelines_v2.py:332-346](file:///f:/Coding/factor_pipeline/pipelines_v2.py)

```python
min_p_value = float(np.min(p_values))
# Bonferroni 校正: 多重比较时调整显著性阈值
n_tests = len(p_values)
alpha_corrected = alpha / max(n_tests, 1)
is_significant = (min_p_value < alpha_corrected)

details = {
    'per_column': per_column,
    'n_columns': len(per_column),
    'min_p_value': min_p_value,
    'alpha': alpha,
    'alpha_corrected': alpha_corrected,
    'bonferroni_correction': True,
    'method': 'ks_2samp',
}
```

### 1.3 目标代码 (Green 阶段)

```python
# BH (Benjamini-Hochberg) FDR 校正: 排序后 p_(k) * K / rank, 取累积最小
n_tests = len(p_values)
p_values_arr = np.asarray(p_values)
order = np.argsort(p_values_arr)
p_adj = np.empty_like(p_values_arr)
prev = 1.0
for i in range(n_tests - 1, -1, -1):
    rank = i + 1
    idx = order[i]
    bh = p_values_arr[idx] * n_tests / rank
    prev = min(prev, bh)
    p_adj[idx] = min(prev, 1.0)

min_p_value = float(np.min(p_values_arr))
min_p_adj = float(np.min(p_adj))
is_significant = (min_p_adj < alpha)

# 回填 per_column 的 p_value_adjusted
for col_result, p_a in zip(per_column, p_adj):
    col_result['p_value_adjusted'] = float(p_a)

details = {
    'per_column': per_column,
    'n_columns': len(per_column),
    'min_p_value': min_p_value,
    'min_p_value_adjusted': min_p_adj,
    'alpha': alpha,
    'correction_method': 'benjamini_hochberg',
    'method': 'ks_2samp',
}
```

### 1.4 接口扩展 (向后兼容)

**函数签名** (L236-240) 保持不变, 但新增可选参数:

```python
def _ks_migration_significance(
    historical_data: 'pd.DataFrame | pd.Series',
    recent_data: 'pd.DataFrame | pd.Series',
    alpha: float = 0.05,
    correction_method: str = 'benjamini_hochberg',  # 新增: 'bonferroni' / 'benjamini_hochberg' / 'none'
) -> Tuple[bool, float, Dict[str, Any]]:
```

**向后兼容策略**:
- `correction_method='bonferroni'` 时走旧路径 (保留 `alpha_corrected` 和 `bonferroni_correction: True` 字段)
- `correction_method='benjamini_hochberg'` (默认) 走新路径
- `correction_method='none'` 不校正, 仅 `min_p < alpha`
- 调用方 `FactorProcessingPipelineV2.transform` (pipelines_v2.py L1111) 不传 `correction_method`, 默认走 BH; 另一处调用 `tests/verify_objective_function.py:154-155` 仅取 `p_val`, 行为语义变化但不破坏 (M1 修正)

**details 字典结构 (三条路径对比, n1 补充)**:

| 路径 | 字段 |
|------|------|
| `'benjamini_hochberg'` (默认) | `per_column` (含 `p_value_adjusted`), `n_columns`, `min_p_value`, `min_p_value_adjusted`, `alpha`, `correction_method: 'benjamini_hochberg'`, `method: 'ks_2samp'` |
| `'bonferroni'` (向后兼容) | `per_column` (无 `p_value_adjusted`), `n_columns`, `min_p_value`, `alpha`, `alpha_corrected`, `bonferroni_correction: True`, `method: 'ks_2samp'` |
| `'none'` | `per_column` (无 `p_value_adjusted`), `n_columns`, `min_p_value`, `alpha`, `correction_method: 'none'`, `method: 'ks_2samp'` |

### 1.5 TDD 测试用例 (Red 阶段先写)

**新增测试文件**: `tests/test_pipelines_v2/test_ks_migration_bh.py` (或合并到现有 test_pipelines_v2 文件)

| 测试 ID | 描述 | 输入 | 期望输出 |
|---------|------|------|---------|
| E1-T1 | BH 校正与手工计算一致 (5 列, p=[0.01, 0.04, 0.03, 0.20, 0.50]) | 构造历史/近期数据使 KS 返回指定 p | p_adj=[0.05, 0.0667, 0.0667, 0.25, 0.50] (atol=1e-4), min_p_adj=0.05 |
| E1-T2 | Bonferroni 路径向后兼容 (correction_method='bonferroni') | 同上 | alpha_corrected=0.01, bonferroni_correction=True |
| E1-T3 | none 路径 (correction_method='none') | 同上 | is_significant = (min_p < 0.05), 无 alpha_corrected |
| E1-T4 | 空数据 / 无公共列 / 数据不足 保护路径不变 | 空数据 | (False, 1.0, {warning: ...}) |
| E1-T5 | BH 校正下迁移率 >= Bonferroni (宽松性验证) | 100 列随机数据, 注入 10 列真实迁移 | BH 确认迁移数 >= Bonferroni 确认迁移数 |
| E1-T6 | details 字段结构验证 | 5 列正常数据 | 包含 'correction_method', 'min_p_value_adjusted', 不含 'bonferroni_correction' (BH 路径) |

### 1.6 ADR-002a 决策记录

**位置**: [DECISIONS.md](file:///f:/Coding/factor_pipeline/DECISIONS.md) L86 后 (ADR-002 之后, ADR-003 之前)

```markdown
## ADR-002a: KS 迁移检测校正方法迁移 Bonferroni → Benjamini-Hochberg

**日期**: 2026-07-04
**状态**: 已实施 (T4 E1)
**优先级**: P0
**Supersedes**: ADR-002 的校正方法 (ADR-002 整体不废止, 仅校正方法部分被取代)

### 背景

ADR-002 采用 Bonferroni 校正 KS 迁移检测的多重比较。Bonferroni 控制族错误率 (FWER), 过于保守, 在因子列数多时 (如 K=20) 显著性阈值被压缩到 alpha/K=0.0025, 导致 Type II 误差增加 (漏报真实迁移)。

v2.6.0 E7 (optimizer.py 的 _validate_significance) 和 factor_significance.py 已默认使用 BH FDR 校正, KS 迁移路径是仓库中最后一处仍用 Bonferroni 的默认生效路径。

### 决策

**采用 Benjamini-Hochberg FDR 校正**, 替代 Bonferroni。

具体方案:
- `_ks_migration_significance` 新增 `correction_method: str = 'benjamini_hochberg'` 参数
- BH 步骤: 排序 p 值, `p_adj_(k) = p_(k) * K / rank`, 从大到小取累积最小, clip 到 [0,1]
- 判定: `min(p_adj) < alpha`
- 保留 `correction_method='bonferroni'` 作为向后兼容选项

### 备选方案

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| A: 保持 Bonferroni | 保守, FWER 严格控制 | Type II 误差高, 与 E7/factor_significance 不一致 | ❌ |
| B: BH FDR | 与 E7 一致, 检测力提升, 控制 FDR | FDR 比 FWER 宽松 | ✅ |
| C: Holm 逐步 | 介于 A/B 之间 | 实现复杂, 与 factor_significance 选项一致但非默认 | ❌ |
| D: 无校正 | 最敏感 | 假阳性失控 | ❌ |

### 后果

- **正面**: KS 迁移检测敏感度提升 (迁移率上升), 与 v2.6.0 E7 和 factor_significance.py 校正方法一致, 减少认知负担
- **负面**: FDR 控制比 FWER 宽松, 假阳性率可能上升 (从 ~alpha/K 到 ~alpha*FDR)
- **风险**: Q3 验证集迁移率可能上升, 需回归测试确认在可接受范围

### 学术依据

- Benjamini-Hochberg (1995) Controlling the False Discovery Rate: A Practical and Powerful Approach to Multiple Testing
- Harvey-Liu-Zhu (2016) … and the Cross-Section of Expected Returns (多重检验在金融)
- Bonferroni (1936) — 保守性参考 (KS 迁移默认路径不再使用, 但作为可选 `correction_method='bonferroni'` 保留, n4 修正)
```

### 1.7 E1 验收标准

- [ ] E1-T1 ~ E1-T6 测试全部 Red → Green
- [ ] `_ks_migration_significance` 默认走 BH 路径
- [ ] `correction_method='bonferroni'` 向后兼容, 旧测试不破坏
- [ ] ADR-002a 写入 DECISIONS.md
- [ ] 全量回归 918 passed 不变 (新测试额外 +6)

---

## 2. E2: 测试更新 (verify_fix1 + significance_manual)

### 2.1 目标

更新手工校验脚本和 manual 测试, 覆盖 KS 迁移路径的 BH 校正。

### 2.2 verify_fix1_manual.py 改动

**文件**: [tests/test_backtest/verify_fix1_manual.py](file:///f:/Coding/factor_pipeline/tests/test_backtest/verify_fix1_manual.py)

**当前代码** (L97, L116-118, L125-140):
```python
# L97 (校验 1)
manual_alpha_corrected = manual_alpha / manual_n_tests

# L116-118 (校验 2)
assert actual_corrected == pytest.approx(expected_corrected, abs=1e-10)

# L125-126 (校验 3 标题)
"Bonferroni 校正公式校验"

# L130
expected_corrected = alpha / n_cols

# L138-140
assert abs(actual_corrected - expected_corrected) < 1e-10
```

**目标代码** (BH 公式):
```python
# L97 (校验 1) — BH 手工计算
# BH: 排序 p, p_adj_(k) = p_(k) * K / rank, 累积 min
manual_p_sorted = np.sort(manual_p_values)
manual_p_adj = np.empty_like(manual_p_sorted)
prev = 1.0
for i in range(manual_n_tests - 1, -1, -1):
    rank = i + 1
    bh = manual_p_sorted[i] * manual_n_tests / rank
    prev = min(prev, bh)
    manual_p_adj[i] = min(prev, 1.0)
manual_min_p_adj = float(np.min(manual_p_adj))

# L125-126 (校验 3 标题)
"BH (Benjamini-Hochberg) FDR 校正公式校验"

# L130 — BH 期望值
expected_min_p_adj = manual_min_p_adj  # 与手工计算一致

# L138-140
assert abs(actual_min_p_adj - expected_min_p_adj) < 1e-10
```

**新增校验 (校验 4, n2 明确不纳入 T4 范围)**:
- 构造 5 列数据, p=[0.01, 0.04, 0.03, 0.20, 0.50], 期望 p_adj=[0.05, 0.0667, 0.0667, 0.25, 0.50]
- 验证 BH 公式数值正确性 (与 factor_significance.py 对照)
- **决策**: 此校验作为 E3 阶段 `verify_v3_0_0_t4_manual.py` 的 T4-V1 实现, 不在 E2 范围内, 不影响 §0.1 verify_fix1_manual.py 行数估算 (~20 行)

### 2.3 test_factor_significance_manual.py 改动

**文件**: [tests/manual/test_factor_significance_manual.py](file:///f:/Coding/factor_pipeline/tests/manual/test_factor_significance_manual.py)

**新增测试类**: `TestKSMigrationBHCorrection` (放在 `TestBHCorrection` 之后, L385 后)

> **注**: 既有 `TestBHCorrection.test_bonferroni_correction_matches_manual` (L369-385) 测的是 `factor_significance.py` 的 Bonferroni 路径, 与 KS 迁移无关, 保留不动; 新增 `TestKSMigrationBHCorrection` 类独立 (m5 补充)。

| 测试 ID | 描述 | 验证点 |
|---------|------|--------|
| E2-T1 | KS 迁移 BH 与 factor_significance BH 数值一致 | 同样 p 值输入, 两路径 p_adj 精度 < 1e-10 |
| E2-T2 | KS 迁移 BH 与手工排序一致 | 构造 5 列已知 p, 验证 p_adj |
| E2-T3 | KS 迁移 correction_method='bonferroni' 向后兼容 | 旧路径字段 (alpha_corrected, bonferroni_correction: True) 仍存在 |
| E2-T4 | KS 迁移 correction_method='none' 无校正 | is_significant = (min_p < alpha), 无 p_adj |

### 2.4 E2 验收标准

- [ ] verify_fix1_manual.py 校验 1/2/3 公式改为 BH, 手工校验通过
- [ ] test_factor_significance_manual.py 新增 4 个测试全部 Green
- [ ] BH 数值与 factor_significance.py 路径精度 < 1e-10 (跨路径一致性)
- [ ] 旧 Bonferroni 路径测试 (向后兼容) 仍通过

---

## 3. E3: 文档同步 + 全量回归 + 手工校验

### 3.1 目标

同步所有相关文档, 执行全量回归确认零回归, 手工校验 BH 公式数值正确性。

### 3.2 文档同步清单

| 文件 | 改动内容 | 行数 |
|------|---------|------|
| [DECISIONS.md](file:///f:/Coding/factor_pipeline/DECISIONS.md) L1547 | `[ ] T4 BH-FDR` → `[x] T4 BH-FDR` | 1 |
| [CHANGELOG.md](file:///f:/Coding/factor_pipeline/CHANGELOG.md) | 新增 v2.7.0 或 v3.0.0-T4 条目 | ~15 |
| [README.md](file:///f:/Coding/factor_pipeline/README.md) L239 | "Bonferroni 校正" → "BH FDR 校正" | 1 |
| [README.en.md](file:///f:/Coding/factor_pipeline/README.en.md) L181 | "Bonferroni correction" → "BH FDR correction" | 1 |
| [CODE_WIKI.md](file:///f:/Coding/factor_pipeline/CODE_WIKI.md) | KS 迁移路径描述更新 (Bonferroni → BH) | ~3 |
| [docs/ANALYSIS_V3.0.0.md](file:///f:/Coding/factor_pipeline/docs/ANALYSIS_V3.0.0.md) | T4 状态更新 (已实施) | ~2 |

### 3.3 全量回归

```powershell
python -m pytest --tb=short -q 2>&1 | Out-File -FilePath pytest_t4.log -Encoding utf8
Get-Content pytest_t4.log -Tail 50
```

**期望**: 918 + 6 (E1) + 4 (E2) = **928 passed + 6 skipped + 11 subtests** (零回归)

### 3.4 手工校验脚本

**新增文件**: `tests/manual/verify_v3_0_0_t4_manual.py`

| 校验 ID | 描述 | 方法 |
|---------|------|------|
| T4-V1 | BH 公式数值正确性 | 构造 p=[0.01, 0.04, 0.03, 0.20, 0.50], 期望 p_adj=[0.05, 0.0667, 0.0667, 0.25, 0.50] (atol=1e-4) |
| T4-V2 | BH 与 factor_significance.py 跨路径一致 | 同样输入, 两路径 min_p_adj 差 < 1e-10 |
| T4-V3 | Bonferroni 向后兼容 | correction_method='bonferroni' 仍返回 alpha_corrected, bonferroni_correction=True |
| T4-V4 | 默认走 BH | 不传 correction_method 时 details['correction_method']=='benjamini_hochberg' |
| T4-V5 | 迁移率宽松性 | 100 列随机数据 + 10 列真实迁移, BH 确认迁移数 >= Bonferroni |
| T4-V6 | ADR-002a 已写入 | DECISIONS.md 包含 "ADR-002a" 标题 |

### 3.5 E3 验收标准

- [ ] 全量回归 928 passed + 6 skipped + 11 subtests (零回归)
- [ ] 手工校验 6/6 通过
- [ ] 所有文档同步 (DECISIONS/CHANGELOG/README/CODE_WIKI/ANALYSIS)
- [ ] TODO 勾选 `[x] T4 BH-FDR`

---

## 4. 风险评估与回退方案

### 4.1 风险

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| BH 比 Bonferroni 宽松, Q3 验证集迁移率上升超预期 | 中 | E3 全量回归监控迁移率, 若 > 20% 上升需评估是否回退 |
| 接口扩展破坏向后兼容 (调用方传 bonferroni_correction=True) | 低 | 调用方 `_merge_transition_weights` 不传此参数, 默认走 BH; 旧参数保留为 deprecated alias |
| BH 公式实现 bug (排序/累积 min 顺序错误) | 中 | E1-T1 与 factor_significance.py 跨路径一致性校验 (E2-T1) 双重验证 |
| 文档与代码状态脱节 (v2.6.0 教训) | 低 | E3 强制对照代码状态, DECISIONS.md ADR-002a 与代码同步 |

### 4.2 回退方案

若 E3 全量回归出现回归或 Q3 迁移率上升超预期:
1. `_ks_migration_significance` 默认改回 `correction_method='bonferroni'`
2. ADR-002a 状态改为 "已回退"
3. 保留 BH 实现代码 (不删除), 作为可选项

---

## 5. 学术依据

| 主题 | 引用 | 状态 |
|------|------|------|
| FDR 控制 | Benjamini-Hochberg (1995) Controlling the False Discovery Rate: A Practical and Powerful Approach to Multiple Testing | 待引入 ADR-002a |
| 多重检验在金融 | Harvey-Liu-Zhu (2016) … and the Cross-Section of Expected Returns | 已引入 (v2.5.0) |
| Bonferroni 保守性 | Bonferroni (1936) Teoria statistica delle classi e calcolo delle probabilità | 已引入 (将被取代) |
| BH 实现参考 | factor_significance.py:433-443 (v2.5.0 Layer 3) | 已实现, T4 复用逻辑 |

---

## 6. 与 v2.6.0 的衔接

v2.6.0 完成的相关基础设施:
- **E7 (Layer 3 显著性)**: optimizer.py 已用 BH, 为 T4 提供实现参考和一致性目标
- **factor_significance.py**: 完整 BH 实现 (L410-458), T4 复用其算法逻辑
- **ADR-002 (L85)**: 明确标注 "远期可考虑 BH", T4 正是执行此远期规划

T4 完成后, 仓库中将无默认生效的 Bonferroni 路径 (仅 deprecated alias 和测试选项保留)。

---

## 7. 待确认事项

1. **版本号**: T4 作为 v2.7.0 (独立小版本) 还是 v3.0.0-t4 (预发布)? 推荐 v2.7.0 (改动小, 可独立发布)
2. **E1-T5 迁移率宽松性测试**: 是否需要构造 Q3 验证集? 或用随机数据 + 注入迁移? 推荐后者 (Q3 验证集不在 T4 范围)
3. **unified_drift.py 滚动 KS 是否纳入 T4**: 不纳入 (ANALYSIS v1.1 M3 已明确为后续独立任务 T5/ADR-002b 候选)
4. **ADR-002a 编号**: ADR-002a vs ADR-024? 推荐 ADR-002a (显式承接 ADR-002, 避免编号跳跃)

---

## 附录 A: 关键文件路径速查

### T4 改动文件
- [pipelines_v2.py:236-359](file:///f:/Coding/factor_pipeline/pipelines_v2.py) — `_ks_migration_significance` (核心改动 L332-346)
- [tests/test_backtest/verify_fix1_manual.py](file:///f:/Coding/factor_pipeline/tests/test_backtest/verify_fix1_manual.py) — 手工校验 (L97, L116-118, L125-140)
- [tests/manual/test_factor_significance_manual.py](file:///f:/Coding/factor_pipeline/tests/manual/test_factor_significance_manual.py) — 新增 KS 迁移 BH 测试类
- [DECISIONS.md](file:///f:/Coding/factor_pipeline/DECISIONS.md) — ADR-002a (L86 后), TODO 勾选 (L1547)

### T4 参考文件 (不改动)
- [backtest/factor_significance.py:410-458](file:///f:/Coding/factor_pipeline/backtest/factor_significance.py) — BH 实现参考
- [optimizer.py:834-931](file:///f:/Coding/factor_pipeline/optimizer.py) — E7 已用 BH, 一致性参考
- [backtest/unified_drift.py:109-157](file:///f:/Coding/factor_pipeline/backtest/unified_drift.py) — 后续任务 T5 候选 (不在 T4 范围)

---

## 附录 B: BH 公式手工计算示例 (E1-T1 测试用例)

**输入**: p_values = [0.01, 0.04, 0.03, 0.20, 0.50], K=5, alpha=0.05

**步骤 1: 排序** (升序)
```
sorted_p = [0.01, 0.03, 0.04, 0.20, 0.50]
rank     = [ 1,    2,    3,    4,    5  ]
```

**步骤 2: 计算原始 BH 值** (p * K / rank)
```
bh_raw = [0.01*5/1, 0.03*5/2, 0.04*5/3, 0.20*5/4, 0.50*5/5]
       = [0.05,    0.075,    0.0667,   0.25,      0.50]
       (注: 0.04*5/3 = 0.0666... 循环小数, 此处保留 4 位小数 0.0667, n3 精度注明)
```

**步骤 3: 累积 min** (从大到小, i=K-1 → 0)
```
i=4: bh=0.50, prev=min(1.0, 0.50)=0.50, p_adj[4]=0.50
i=3: bh=0.25, prev=min(0.50, 0.25)=0.25, p_adj[3]=0.25
i=2: bh=0.0667, prev=min(0.25, 0.0667)=0.0667, p_adj[2]=0.0667
i=1: bh=0.075, prev=min(0.0667, 0.075)=0.0667, p_adj[1]=0.0667  ← 注意: 累积 min 不递增
i=0: bh=0.05, prev=min(0.0667, 0.05)=0.05, p_adj[0]=0.05
```

**步骤 4: 还原原始顺序**
```
原索引: 0.01→idx0, 0.04→idx1, 0.03→idx2, 0.20→idx3, 0.50→idx4
p_adj = [0.05, 0.0667, 0.0667, 0.25, 0.50]
```

**期望输出**:
- `min_p_value = 0.01`
- `min_p_value_adjusted = 0.05`
- `is_significant = (0.05 < 0.05) = False` (边界情况, 严格小于)
- 若 alpha=0.06: `is_significant = (0.05 < 0.06) = True`

**注意**: 此手工计算示例将作为 E1-T1 和 T4-V1 的黄金参考。

---

**文档版本**: v1.1
**完成日期**: 2026-07-04
**v1.0 → v1.1 修订**: 根据 review (1 CRITICAL + 3 MAJOR + 5 MINOR + 4 NIT) 系统性修订

---

## 附录 C: v1.0 → v1.1 修订日志

### CRITICAL 修订 (1 项)

| 编号 | 问题 | 修订位置 | 修订内容 |
|------|------|---------|---------|
| C1 | E1-T1 / T4-V1 期望 p_adj 数值错误 ([0.05, 0.10, 0.10, 0.25, 0.50] 与附录 B 手工计算 [0.05, 0.0667, 0.0667, 0.25, 0.50] 矛盾) | §1.5 E1-T1 表格, §3.4 T4-V1 表格, §2.2 校验 4 | 统一改为 `[0.05, 0.0667, 0.0667, 0.25, 0.50] (atol=1e-4)` (与附录 B 一致) |

### MAJOR 修订 (3 项)

| 编号 | 问题 | 修订位置 | 修订内容 |
|------|------|---------|---------|
| M1 | §1.4 调用方位置标注错误 (L366 `_merge_transition_weights` 不调用 `_ks_migration_significance`, 真正调用方是 L1111 `transform`) | §1.4 向后兼容策略 | 改为 "L1111 `FactorProcessingPipelineV2.transform`", 补充 `tests/verify_objective_function.py:154-155` 另一处调用 |
| M2 | §0.3 测试数与 §2.3/§3.3 不一致 (E2: ~8 vs 实际 4) | §0.3 执行阶段总览表 | E2 改为 "~4 新增 pytest (E2-T1~T4), 另有 verify_fix1_manual.py 3 处校验脚本修改不计入 pytest 数" |
| M3 | §0.2 决策 3 "deprecated alias" 语义不清 (bonferroni_correction 是字段非形参) | §0.2 决策 3 | 改为 "现有函数签名仅有 `alpha: float`, 不存在 `bonferroni_correction` 形参; `bonferroni_correction: True` 仅是 details 字典中的字段" |

### MINOR 修订 (5 项)

| 编号 | 问题 | 修订内容 |
|------|------|---------|
| m1 | §3.2 多出 README.en.md, §0.1 未列出 | §0.1 改动边界表补充 README.en.md L181 行 |
| m2 | §0.1 与 §3.2 CODE_WIKI.md 改动行数不一致 (~5 vs ~3) | 统一为 ~5 行, 标注 4 处需改 (L135/L1462/L1509/L1512) |
| m3 | 遗漏 tests/verify_objective_function.py:154-155 调用 | §0.1 改动边界表补充一行, 标注 "❌ 否 (调用方仅取 p_val, 行为语义变化但不破坏)" |
| m4 | §0.3 "Red 3 + Green 3" 表述不当 (TDD 中 Red/Green 是同测试两阶段) | 改为 "~6 个测试 (E1-T1~T6, 每个经 Red→Green 循环)" |
| m5 | TestBHCorrection 既有 Bonferroni 测试与新测试类关系未说明 | §2.3 补充说明 "既有 TestBHCorrection.test_bonferroni_correction_matches_manual 测的是 factor_significance.py 路径, 与 KS 迁移无关, 保留不动" |

### NIT 修订 (4 项)

| 编号 | 问题 | 修订内容 |
|------|------|---------|
| n1 | §1.4 'none'/'bonferroni' 路径 details 结构缺失 | §1.4 补充三条路径 details 字典结构对比表 |
| n2 | §2.2 "校验 4 可选" 与 §0.1 行数估算不匹配 | 明确校验 4 不在 E2 范围内, 作为 E3 阶段 T4-V1 实现 |
| n3 | 附录 B 0.0667 循环小数精度未注明 | 步骤 2 补充 "0.04*5/3 = 0.0666... 循环小数, 保留 4 位小数 0.0667" |
| n4 | ADR-002a "Bonferroni 将被取代" 措辞不准确 | 改为 "KS 迁移默认路径不再使用, 但作为可选 correction_method='bonferroni' 保留" |

### 修订统计

- **CRITICAL 修复**: 1/1 (C1)
- **MAJOR 修复**: 3/3 (M1, M2, M3)
- **MINOR 修复**: 5/5 (m1, m2, m3, m4, m5)
- **NIT 修复**: 4/4 (n1, n2, n3, n4)
- **总修订位置**: ~15 处文档行

### v1.1 与 v1.0 一致性

- 三阶段划分 (E1/E2/E3) 不变
- 核心改动文件 (pipelines_v2.py L332-346) 不变
- BH 公式实现 (§1.3) 不变 (仅修正期望值, 公式本身正确)
- ADR-002a 决策方向不变
- 推荐执行顺序 (E1 → E2 → E3 串行) 不变
- v1.1 仅修正表述准确性、行号精确化、期望值纠正, 未改变任何方案决策

**下一步**: v3.0.0 T4 EXECUTION v1.1 完成, 可进入 E1 Red 阶段 (TDD 实施起点)
