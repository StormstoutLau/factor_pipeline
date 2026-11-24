# P-027 Stage 0b — 披露字段登记（IMPLEMENTATION）

---
id: p027-stage0b-disclosure-IMPLEMENTATION
type: implementation
version: 1.1
status: verified
date: 2026-11-24
depends: [p027-stage0b-disclosure-DESIGN]
upstream: null
---

## §1 实施清单

| 文件 | 位置 | 改动 |
|---|---|---|
| `modules/endogeneity_check/core/threat_assessor.py` | L13-L17 / L42-L62 | 新增 `TAU_WEIGHTS_VERSION='v1'`、`get_effective_weights()`、`get_weights_version()` |
| `modules/endogeneity_check/core/diagnostic_orchestrator.py` | L73-L79 | 委托 `get_weights_version()` / `get_effective_weights()` |
| `pipelines_v2.py` | L1877-L1896 | `check_endogeneity` 顶层披露字段 + `_attach_stage_meta` |
| `pipelines_v2.py` | L1917 / L1930 | S2 `input_stage='imputed'`；S3 `input_stage='neutralized'` |
| `pipelines_v2.py` | L1932-L1954 | S4 `s4_input_stage` / `stage_fallback`；`final_assessment` 同步 |
| `pipelines_v2.py` | L2144-L2167 | E5 输出 `experimental/heuristic/weights_version/effective_weights` |
| `tests/test_endogeneity_check/test_endogeneity.py` | C2-C4 | 权重版本/有效权重/阶段回退测试 |
| `tests/test_endogeneity_regularizer/test_regularizer.py` | E5-T18/T19 | E5 元数据与 E3 继承测试 |

## §2 默认行为不变

- 不修改任何 `final_threat_tau`、`component_taus`、L1/L2/L3 数值。
- 只追加键；现有键与顺序不变。
- E3/E5 默认仍为 `False`；不启用时不创建 orchestrator。
- 零新增运行时依赖。

## §3 测试计划

```bash
pytest tests/test_endogeneity_check/test_endogeneity.py -k "C2 or C3 or C4"
pytest tests/test_endogeneity_regularizer/test_regularizer.py -k "T18 or T19"
```

预期：5 passed（C2/C3/C4 + E5-T18/E5-T19）。

## §4 验证状态（2026-11-24 已执行）

- 定向：C2/C3/C4 **3 passed**；E5-T18/T19 **2 passed**。
- 模块回归：`tests/test_endogeneity_check` + `tests/test_endogeneity_regularizer` **55 passed**。
- 全量回归：**2274 passed / 36 skipped / 0 failed**（1051.62 s；较 v3.11.1 基线 2269 +5 例，均为本批新增）。
- 版本：包版本 **3.11.2** 落 6 锚点 + CHANGELOG；`tests/test_fix3_version_unification.py` **9 passed**。

## §5 回退

- 回退 = 还原上述 4 个源文件 + 2 个测试文件 + 6 个版本锚点 + CHANGELOG 条目；无数据迁移。
- 包版本 **3.11.1 → 3.11.2**（patch：只读披露字段，默认行为零变更）。
