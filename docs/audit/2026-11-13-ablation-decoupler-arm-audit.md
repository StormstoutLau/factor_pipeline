# 审计报告 — v3.4.4 AblationRunner decoupler 消融臂

> **日期**: 2026-11-13
> **版本**: v3.4.4
> **审查对象**: `backtest/ablation_runner.py` + `tests/test_backtest/test_ablation_decoupler_arm.py` + 版本锚点
> **上游 spec**: [RESEARCH](../research/RESEARCH_ABLATION_DECOUPLER_ARM.md) v1.0 / [DESIGN](../private/DESIGN_ABLATION_DECOUPLER_ARM.md) v1.0 / [EXECUTION](../EXECUTION_V3.4.4_ABLATION_DECOUPLER_ARM.md) v1.0 / ADR-036 / ADR-042 / ADR-045（实现补充）
> **方法**: audit-driven-development 5 阶段（Detection → Repair），人类可读基线

---

## Phase 0 — Spec 质量门

| 维度 | 判定 | 证据 |
|------|------|------|
| 可测试约束 | ✅ | 两臂命名/`routing_mode='dynamic'`/`module_enabled` 精确值/`run_l1` 6 臂/ρ 5 键/报告 5 列 |
| 模块映射 | ✅ | 单模块 `ablation_runner.py`，对应 EXECUTION §3/§4 |
| 接口契约 | ✅ | `run_l1_decoupler` 全签名、`DYNAMIC_L1_MODULES`、复用语义明确 |
| 修正项 | ✅ | R-1（`market_cap_data` 两处断链） |
| 跨模块契约 | ✅ | ADR-042（dynamic_ab 唯一入口）、ADR-045（decoupler 开关）、ADR-036（消融层） |

**Tier**: A（5/5）→ 执行完整审计。

---

## Phase 1 — Spec 盘点

| 维度 | 代码 | Spec |
|------|------|------|
| 消融臂接口 | `ablation_runner.py` `run_l1_decoupler` | EXECUTION §3.1-§3.3 |
| 消融臂执行路径 | `_run_pipeline` / DynamicFactorPipeline | EXECUTION §4.2；RESEARCH A3-A5 |
| ρ_step 采集 | `_collect_rho_steps` | EXECUTION §4.3；DESIGN §4 |
| 报告 | `generate_report` §6 | EXECUTION §4.5 |
| 兼容性修复 | `run_l1` / `run_single` | EXECUTION §4.4；RESEARCH A9 |
| 版本/文档 | 6 锚点 + 文档 | EXECUTION §5 |

---

## Phase 2 — 多维度审查

### 2.1 签名一致性 ✅

- `run_l1_decoupler(factor_data, fwd_returns, industry_data=None, market_cap_data=None, dynamic_ref_result=None)` 与 EXECUTION §3.1 一致；
- 两臂 `AblationConfig` 字段与 §3.2 一致（`layer='L1'`、`routing_mode='dynamic'`、`baseline_level='B3'`、`_is_trivial=False`）。

### 2.2 行为一致性 ✅

| 检查 | 结果 |
|------|------|
| 两臂均注入 `pipeline_mode='dynamic_ab'` | ✅ D4 捕获两次构造 |
| 仅实验臂 `module_enabled={'decoupler': False}` | ✅ D5 |
| 参照复用（identity + 只跑 1 次） | ✅ D6 |
| `decoupler` ρ 仅在 `decoupling` 中间数据存在时输出 | ✅ D7/D8 |
| 报告列条件追加 | ✅ D9 |
| `run_l1` 仅非 None 时转发市值 | ✅ D10 |
| 端到端两臂可运行 | ✅ D11 |

### 2.3 修正项落实 ✅

- R-1 两处断链均已修：`run_l1` 入口 → `run_single`；`run_single` B3 → `_run_pipeline`；
- 既有 monkeypatch 测试（114 例）零回归，证明"仅非 None 注入"的兼容策略有效。

### 2.4 测试盲区

| 盲区 | 判定 | 处置 |
|------|------|------|
| 未在 runner 层直接断言 `_ar_decoupler is None` | P3 | 接受：v3.4.3 `test_dynamic_component_separability.py` T3/T10 已覆盖开关→组件映射，runner 层断言 config 传播即可 |
| D11 未断言两臂输出必然不同 | P3 | 接受：AR 贡献是否显著应由实测数据判定，不应在单测中强制；D11 只做冒烟 |
| 断言恒真式 | 无 | D2/D3 断具体值；D7 断 `<0.5`；D8 断精确键集合 |

### 2.5 跨模块契约 ✅

- ADR-042：`decoupler` 只在 `dynamic_ab` 存在 → 两臂均 `routing_mode='dynamic'`；
- ADR-045：`module_enabled['decoupler']` 映射 `CompositeDecoupler(enable_ar=False)`（由 v3.4.3 测试背书）；
- ADR-036：结果 `layer='L1'`，进入既有报告 L1 表，不新增层。

### 2.6 构建配置 / 版本 ✅

- 6 处版本锚点 = `3.4.4`；`verify_fix3_manual.py` 5/5 通过；
- 缓存代际仍为 `v2.3.0-cache`（无中间产物数值变更）。

---

## Phase 3 — 问题分级与修复矩阵

| 编号 | 级别 | 描述 | 状态 |
|------|------|------|------|
| P0 | — | 无 | — |
| P1 | — | 无 | — |
| P2-1 | Major | EXECUTION §4.2 代码片段在 `run_l1_decoupler` 中无条件传 `market_cap_data`，与实现的"仅非 None 注入"不一致 | ✅ 已修复（文档同步为 `extra_kwargs`） |
| P2-2 | Major | 报告 ρ_step 新增 `decoupler` 列后，未说明该列含"中性化 + AR"合并变化，易被误读为纯 AR 贡献 | ✅ 已修复（报告加注脚 + D9 断言） |
| P3-1 | Minor | `run_l2` 入口仍未转发 `market_cap_data` | ⏸ 接受：已在 RESEARCH A10 / CHANGELOG 登记，另行评估 |
| P3-2 | Minor | runner 层未直接断言 `_ar_decoupler is None` | ⏸ 接受：O2 模块/管线测试已覆盖 |
| P3-3 | Minor | RESEARCH 中部分行号引用会随文件编辑漂移 | ⏸ 接受：证据以"文件+符号/section"为主，行号仅辅助 |

**Phase 3.5 幻觉防护**: 全部 findings 均经源码核对（L1 文件存在、L2 行号有效、L3 关键词匹配、L4 结构性一致），无幻觉项；P2-1/P2-2 修复后已回归。

---

## Phase 4 — 修复基线与验证

| 编号 | 严重度 | 描述 | 状态 | 验证 |
|------|--------|------|------|------|
| P2-1 | Major | 实施文档片段与代码一致化 | ✅ 已修复 | 文档 diff + 代码核对 |
| P2-2 | Major | 报告 decoupler ρ 语义注脚 | ✅ 已修复 | D9 `合并排序` 断言 + 报告回归 |

**测试基线**:

| 阶段 | 结果 |
|------|------|
| Red | `test_ablation_decoupler_arm.py` → 10 failed / 1 passed |
| Green | 同上 → **11 passed** |
| 定向回归 | ablation_runner + decoupler 臂 + O2 组件开关 + 版本统一 → **121 passed**（18.36s） |
| 手工版本校验 | 6/6 锚点 + 缓存独立 + 顶层导入 → **5/5** |
| 全量回归 | `pytest -q` → **1705 passed / 15 skipped / 0 failed** (1063.50s) |

---

## Phase 5 — 结论

- **P0/P1 = 0**；P2×2 已在本轮修复；P3×3 已登记接受。
- 数值评分：`100 − (0×20 + 0×8 + 2×3 + 3×1) = 91` → **A**。
- 设计承诺核对：within-mode 两臂、ρ 条件采集、报告条件列、`run_l1` 6 臂契约、市值两处转发，全部落地。
- 残余风险：Dynamic 臂在小样本上的 AR 拟合质量依赖 ADR-040/041 既有降级路径；D11 仅做冒烟，真实贡献需用真实面板运行 `run_l1_decoupler` 后再解读。

**审计判定**: PASS（无阻断项）。
