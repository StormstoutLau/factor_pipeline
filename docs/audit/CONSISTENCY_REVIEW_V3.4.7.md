# 跨文档一致性审查 — v3.4.7 AblationRunner L3/L4 旋钮接线

> **日期**: 2026-11-15
> **审查对象**: RESEARCH / DESIGN / EXECUTION / CHECKLIST 四份文档

## 1. 数字一致性

| 项目 | RESEARCH | DESIGN | EXECUTION | CHECKLIST | 结论 |
|------|----------|--------|-----------|-----------|------|
| L4 结果数 | 20 (现状) | 9 | 9 | 9 | ✅ |
| L4 臂数 | 19 非 B3 | 8 | 8 | 8 | ✅ |
| L3 结果数 | 25 (现状) | 7 | 7 | 7 | ✅ |
| L3 臂数 | 24 非 B3 | 6 | 6 | 6 | ✅ |
| L4 trivial | 6 (错误口径) | 2 | 2 | 2 | ✅ |
| 可接线臂 | 10 | 仅 outlier 4 | 仅 outlier 4 | 仅 outlier 4 | ✅ (DESIGN 已说明取舍) |

## 2. 符号一致性

| 符号 | 定义处 | 使用处 | 结论 |
|------|--------|--------|------|
| `static_outlier_method` | DESIGN §3.1 / EXECUTION §4.1 | `_create_pipeline` / `_apply_l4_overrides` | ✅ |
| `static_outlier_percentile_lower/upper` | 同上 | 同上 | ✅ |
| `outlier_method` (构造参数) | EXECUTION §4.2 | `StaticFactorPipeline` | ✅ |
| `L4_OUTLIER_MAP` | EXECUTION §4.5 | `_apply_l4_overrides` | ✅ |
| `_wiring_status` | DESIGN §4.3 / EXECUTION §4.4 | `run_l3` / `generate_report` | ✅ |
| `Wiring` (报告列) | EXECUTION §4.8 | CHECKLIST B11 | ✅ |

## 3. 语义一致性

| 检查 | 结论 |
|------|------|
| 「默认值 = 现状」在三份文档中口径一致 | ✅ DESIGN §3.4 / EXECUTION §4.2 / CHECKLIST A6 |
| trivial 定义与实跑口径一致 | ✅ L4 `winsorize_1pct` = percentile 1/99; 中性化默认随市值切换 |
| CUSUM 为何 trivial | ✅ 三份文档均引 RESEARCH F13/F14 |
| 删除项是否与「不做的事」冲突 | ✅ 删除 = 不提供臂; 不做 = 不新增能力, 语义一致 |

## 4. 行号/引用抽查

| 引用 | 验证 | 结论 |
|------|------|------|
| RESEARCH F4-F11 → `pipelines_v2.py:470-471, 708-738, 1415-1423` | 已核对 | ✅ |
| RESEARCH F12-F14 → `ablation_runner.py:614-619`, `pipelines_v2.py:1082-1106` | 已核对 | ✅ |
| RESEARCH F19 → `ablation_runner.py:1408-1423` (compare_all) | 已核对 | ✅ |
| EXECUTION §4.6 臂集合 → `run_l4_oat:1085-1175` | 已核对 | ✅ |
| EXECUTION §4.7 臂集合 → `run_l3:1177-1298` | 已核对 | ✅ |

## 5. 结论

- 四份文档在数字、符号、语义、引用四个维度一致;
- 唯一「表面差异」: RESEARCH 的 10 个可接线臂 vs 本版只接 4 个, 已在 DESIGN §2 方案对比中显式解释
  (其余可接线项与 ADR-040 冲突或会改写历史数值), 不构成不一致。

**判定**: PASS。
