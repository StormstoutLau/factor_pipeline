# P-027 Stage 0b — 披露字段登记（DESIGN）

---
id: p027-stage0b-disclosure-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [p027-stage0b-disclosure-RESEARCH]
upstream: null
---

## §1 决策

| # | 决策 | 内容 |
|---|---|---|
| D1 | 权重版本 | 新增模块常量 `TAU_WEIGHTS_VERSION='v1'`；assessor 暴露 `get_weights_version()` |
| D2 | 有效权重 | `get_effective_weights(methods)`：仅保留权重 >0 的启用方法，按和归一化；未知方法忽略；空集返回 `{}` |
| D3 | 阶段字段 | S2 `input_stage='imputed'`；S3 `input_stage='neutralized'`；S4 `s4_input_stage ∈ {'decoupled','imputed_fallback'}` + `stage_fallback: bool`；`final_assessment` 与 S4 一致 |
| D4 | E5 标注 | E5 输出追加 `experimental=True`、`heuristic=True`、`weights_version`、`effective_weights` |
| D5 | 默认不变 | 不改变任何 τ / premium / l1-l3 数值；只追加键；E3/E5 默认仍关闭 |
| D6 | 单一来源 | 权重版本只在 `threat_assessor.py` 定义；pipeline 不复制字面量（E5 fallback 用导入常量） |

## §2 接口

```python
# threat_assessor.py
TAU_WEIGHTS_VERSION = 'v1'
EndogeneityThreatAssessor.get_weights_version() -> str
EndogeneityThreatAssessor.get_effective_weights(methods: list[str]) -> dict[str, float]

# diagnostic_orchestrator.py
EndogeneityDiagnosticOrchestrator.get_weights_version() -> str
EndogeneityDiagnosticOrchestrator.get_effective_weights() -> dict[str, float]

# check_endogeneity(...) 返回追加:
#   report['weights_version'] / ['effective_weights'] / ['tau_is_heuristic']
#   report['s2']['input_stage']
#   report['s3']['input_stage']
#   report['s4']['s4_input_stage'] / ['stage_fallback']
#   report['final_assessment'] 同 S4

# apply_endogeneity_regularization(...) 返回追加:
#   'experimental': True, 'heuristic': True,
#   'weights_version': str, 'effective_weights': dict | None
```

## §3 不变式

- **INV-1**：默认数值输出零变更；只追加键。
- **INV-2**：`effective_weights` 之和为 1（非空时），仅含启用方法。
- **INV-3**：未知方法不进入分母。
- **INV-4**：未传 `decoupled_factor` 时 `stage_fallback=True` 且 `s4_input_stage='imputed_fallback'`。
- **INV-5**：E5 输出 `experimental is True`；手工 assessment 无披露字段时 `effective_weights=None`、`weights_version='v1'`。
- **INV-6**：零新增运行时依赖；E3/E5 默认关闭不变。

## §4 测试矩阵

| 用例 | 断言 |
|---|---|
| C2 | 版本 `v1`；`oster+aet` → 4/7、3/7；四方法 → 0.4/0.3/0.2/0.1；未知方法忽略 |
| C3 | 顶层字段；S2 `input_stage`；S4 fallback 标记；final 一致 |
| C4 | 传 `decoupled_factor` → `decoupled` / `False` |
| E5-T18 | 手工 assessment → `experimental/heuristic/weights_version`；`effective_weights=None` |
| E5-T19 | E3 → E5 继承 `weights_version/effective_weights` |

## §5 被拒方案

| 方案 | 拒绝理由 |
|---|---|
| 把权重做成 `PipelineV2Config` 字段 | 改变 τ 口径与默认行为；Stage 2 已判定 τ 仅展示，无需可配置 |
| 在 pipeline 复制权重字面量 | 双写漂移；违反 D6 |
| 用 `effective_weights` 替代 `weights_version` | 版本用于审计，权重用于解释；两者不可互替 |
