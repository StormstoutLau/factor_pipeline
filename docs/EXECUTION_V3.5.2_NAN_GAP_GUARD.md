# EXECUTION V3.5.2 — 多断点路径 NaN 间隙守卫

> **版本**: v3.5.2 (2026-11-17)
> **状态**: 已实施
> **上游**: [RESEARCH](research/RESEARCH_V3.5.2_NAN_GAP_GUARD.md) / ADR-048 / ADR-046 / ADR-047
> **设计**: private (`docs/private/DESIGN_V3.5.2_NAN_GAP_GUARD.md`, 未提交)

---

## §1 目标

在 v3.5.1 多断点标签路径上补一层**连续性守卫**:

- 断点边界跨越 ≥ `multi_break_gap_min_run`（默认 2）期 NaN 时，
  不宣称 `ES`/`ES+TD`，降级为 `suspect`；
- `detect_multiple` 暴露 NaN 连续性描述键；
- 默认 `single` 模式标签与旧键逐位不变。

---

## §2 变更清单

| 文件 | 变更 | 规模 |
|------|------|------|
| `modules/factor_health/__init__.py` | `BreakpointDetector._gap_runs` / `_gap_missing_at`（静态辅助）；`detect_multiple` +5 键；`FactorHealthDiagnoser.__init__` +1 参数；`_resolve_breakpoints` 间隙判定；`_multi_break_materiality` 返回 `driver_k`；`_classify_premium_health` 插入 gap 分支；`diagnose` +6 键 | ~+110 行 |
| `tests/unit/test_layer3_factor_health.py` | 新增 `TestMultipleBreakpointGapGuard` G1-G9 | +183 行 |
| 版本锚点 6 处 | 3.5.1 → 3.5.2 | — |
| 文档 | RESEARCH / EXECUTION / 审计 / ADR-048 / CHANGELOG / README / PROJECT_STATUS / DEV_PROGRESS / CODE_WIKI | — |

---

## §3 API 与契约

### §3.1 构造参数

```python
FactorHealthDiagnoser(..., multi_break_gap_min_run: int = 2)
```

- `< 1` → `ValueError`；
- 仅在 `breakpoint_mode='multiple'` 生效。

### §3.2 `detect_multiple` 输出（13 → 18 键）

新增:

| 键 | 类型 | 语义 |
|----|------|------|
| `n_nan` | int | NaN 总数 |
| `n_gaps` | int | NaN 连续段数 |
| `max_gap_run` | int | 最长 NaN 连续段 |
| `breakpoints_gap_missing` | list[int] | 每个 BIC 断点跨越的缺失期数 |
| `gap_missing_at_bp` | int/None | 首个断点跨越的缺失期数 |

### §3.3 `diagnose` 输出（22 → 28 键）

在 §3.2 的 5 键基础上增加 `breakpoint_gap_risk: bool`。

- `single` 模式: `breakpoint_gap_risk=False`；其余 5 键按单断点计算；
- `multiple` 模式: 按 §3.4 规则计算。

### §3.4 判定规则

```
confirmed → gap_risk = gap_missing(sup-F 断点) >= min_run
!confirmed & material → gap_risk = gap_missing(最大位移 BIC 边界) >= min_run
其余 → False
```

分类树:

```
has_bp & confirmed & !gap_risk → ES / ES+TD
has_td                         → TD
gap_risk                       → suspect
has_bp                         → suspect
FM t 路径                      → stable / suspect
```

- `has_breakpoint` 语义不变（`confirmed or material`）；
- `breakpoint_idx` / `breakpoints` / `segment_means` 仍为描述值；
- `pre_mean` / `post_mean` 仍仅在 `has_bp=True` 时非 NaN。

---

## §4 实现要点

1. **连续性统计**: `_gap_runs` 用布尔差分定位 NaN 连续段，全 NaN → `n_gaps=1`；
2. **跨越缺失数**: `_gap_missing_at(idx_map, pos) = idx_map[pos] - idx_map[pos-1] - 1`，
   其中 `pos` 为断点在有效点序列中的位置；
3. **主断点**: `n_breaks>0` 用 `breakpoints[0]`；`n_breaks==0 & confirmed` 用 sup-F 断点；
4. **材料性驱动边界**: `_multi_break_materiality` 返回最大位移边界序号 `driver_k`，
   由 `segment_bounds[driver_k+1][0]` 映射回原序列；
5. **守卫关闭**: `single` 模式固定 `breakpoint_gap_risk=False`，不改变既有标签。

---

## §5 测试

### §5.1 新增 G1-G9

| # | 场景 | 结果 |
|---|------|------|
| G1 | `detect_multiple` 无 NaN → 连续性键全零 | PASS |
| G2 | 断点处 g=5 缺失 → `n_gaps=1` / `max_gap_run=5` / 断点跨越 ≥2 | PASS |
| G3 | confirmed + 断点跨 g=5 → `gap_risk=True`，ES → suspect | PASS |
| G4 | 断点跨孤立 1 点 NaN（gmin=2）→ 不降级，ES 保留 | PASS |
| G5 | 间隙远离断点 → 不降级，ES 保留 | PASS |
| G6 | 未确认 + material 驱动边界跨间隙 → `gap_risk=True`，suspect | PASS |
| G7 | 默认 `single` 模式 → 守卫关闭，标签不变，描述键存在 | PASS |
| G8 | 全 NaN → 不抛异常，`n_gaps=1` / `max_gap_run=200`，risk False | PASS |
| G9 | `multi_break_gap_min_run=0` → `ValueError` | PASS |

### §5.2 定向回归

- `tests/unit/test_layer3_factor_health.py`: **49 passed**（原 40 + 新增 9）；
- 版本统一: **7 passed** + 手工校验 **5/5**（六锚点 3.5.2，缓存 `v2.3.0-cache` 不变）。

### §5.3 端到端探针

T=120 / N=80，premium 0.10 → -0.10，断点 60 前后 5 期前向收益置 NaN：

| 模式 | health | confirmed | n_breaks | bp | gap_at_bp | gap_risk |
|------|--------|-----------|----------|----|-----------|----------|
| `single` | ES | True | 1 | 63 | 5 | False |
| `multiple` | suspect | True | 1 | 63 | 5 | True |

结论: 守卫仅作用于 opt-in 多断点路径，默认单断点标签保持不变。

---

## §6 兼容性

- `detect_multiple` 原 13 键保留且逐位不变（E1-E8 回归通过）；
- `diagnose` 原 22 键保留；新增 6 键为增量；
- `single` 模式标签、`breakpoint_idx`、`pre/post` 零变更（F1/G7）；
- 缓存代际 `v2.3.0-cache` 不变。

---

## §7 全量回归

> **全仓 `pytest` (2026-11-17, v3.5.2)**: **1786 passed / 15 skipped / 0 failed**
> (1160.73s, exit 0)。基线演进: v3.5.1 = 1777 → v3.5.2 = 1786 (+9, G1-G9)。
> 外部数据测试默认跳过 (`RUN_DUCKDB_INTEGRATION=1` 需 DB 非空;
> `verify_integration_real_data.py` 为手动脚本)。

---

## §8 已知限制

- 守卫只在**边界跨越间隙**时触发；真实断点恰好落在间隙边缘时约 17-22%
  会被降级为 suspect（P2），这是"时点不可观测"的保守代价；
- sup-F 在自相关下的过度拒绝与间隙无关（P4: φ=0.5 无间隙 48.7% vs
  有间隙 45.3%），本守卫不处理该问题；
- 不做插值/加权 SSR，避免制造伪数据。
