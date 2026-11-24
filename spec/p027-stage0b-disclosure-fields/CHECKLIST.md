# P-027 Stage 0b — 披露字段登记（CHECKLIST）

---
id: p027-stage0b-disclosure-CHECKLIST
type: checklist
version: 1.1
status: accepted
date: 2026-11-24
depends: [p027-stage0b-disclosure-IMPLEMENTATION]
upstream: null
---

> **总体状态：accepted（2026-11-24）**
> 代码与测试已落盘并执行；T-1~T-8 全部回填。包版本 **3.11.1 → 3.11.2**。

## §1 文档一致性

| # | 项 | 状态 | 证据 |
|---|---|---|---|
| D-1 | RESEARCH 事实 F-1~F-8 与代码一致 | ✅ | RESEARCH §2 |
| D-2 | DESIGN 字段名与实现一致 | ✅ | DESIGN §2 / IMPLEMENTATION §1 |
| D-3 | 默认不变声明与代码一致 | ✅ | IMPLEMENTATION §2 |

## §2 功能

| # | 项 | 状态 | 证据 |
|---|---|---|---|
| F-1 | `weights_version='v1'` 顶层 + S2/S3/S4 + final | ✅ | `pipelines_v2.py` L1877-L1954；C2/C3 |
| F-2 | `effective_weights` 仅启用方法、归一化 | ✅ | `threat_assessor.py` L42-L57；C2 |
| F-3 | S2 `input_stage='imputed'`；S3 `'neutralized'` | ✅ | L1917 / L1930；C3 |
| F-4 | S4 `s4_input_stage` / `stage_fallback` | ✅ | L1932-L1954；C3/C4 |
| F-5 | E5 `experimental/heuristic/weights_version/effective_weights` | ✅ | L2158-L2167；E5-T18/T19 |

## §3 不变式

| # | 项 | 状态 | 证据 |
|---|---|---|---|
| I-1 | 默认数值零变更 | ✅ | E3/E5 默认关闭；只追加键；全量回归 2274 passed / 0 failed |
| I-2 | 有效权重和=1（非空） | ✅ | `get_effective_weights`；C2 |
| I-3 | 未知方法不进分母 | ✅ | 同上；C2 `['oster_delta','unknown'] → {oster_delta:1.0}` |
| I-4 | 未传 decoupled → fallback 标记 | ✅ | L1933-L1934；C3 |
| I-5 | E5 `experimental=True` | ✅ | L2163；E5-T18 |
| I-6 | 零新增依赖 | ✅ | 仅标准库/现有模块 |

## §4 测试与回归

| # | 项 | 状态 | 证据 |
|---|---|---|---|
| T-1 | C2 权重版本/有效权重 | ✅ 3 passed（C2/C3/C4） | `pytest tests/test_endogeneity_check/test_endogeneity.py -k "C2 or C3 or C4"` |
| T-2 | C3 fallback 标记 | ✅ 同上 | C3 |
| T-3 | C4 decoupled 标记 | ✅ 同上 | C4 |
| T-4 | E5-T18 元数据 | ✅ 2 passed（T18/T19） | `pytest tests/test_endogeneity_regularizer/test_regularizer.py -k "T18 or T19"` |
| T-5 | E5-T19 E3→E5 继承 | ✅ 同上 | 同上 |
| T-6 | 定向回归 | ✅ 55 passed | `pytest tests/test_endogeneity_check tests/test_endogeneity_regularizer` |
| T-7 | 全量回归 | ✅ 2274 passed / 36 skipped / 0 failed（1051.62 s；bump 前状态）+ bump 后复跑 9 + 55 passed | `pytest tests -q`；较 v3.11.1 基线 2269 +5 例；bump 仅改版本字符串 |
| T-8 | 版本号 | ✅ 3.11.1 → **3.11.2**（6 锚点 + CHANGELOG） | `test_fix3_version_unification.py` 9 passed |

## §5 结论

Stage 0b 收口（2026-11-24）：披露字段与测试通过，全量回归 0 failed，版本 3.11.2 落盘。P-027 三阶段门（Stage 0a/1/2）+ Stage 0b 全部完成，P-027 转 `done`。
