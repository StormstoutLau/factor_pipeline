# 审计报告 — v3.4.6 AblationRunner L3/L4 市值口径对齐

> **日期**: 2026-11-13
> **版本**: v3.4.6
> **审查对象**: `backtest/ablation_runner.py` (`run_l3` / `run_l4_oat`) + `tests/test_backtest/test_ablation_mktcap_alignment.py`
> **上游 spec**: [RESEARCH](../research/RESEARCH_ABLATION_MKTCAP_ALIGNMENT.md) v1.0 / `docs/private/DESIGN_ABLATION_MKTCAP_ALIGNMENT.md` v1.0 / [EXECUTION](../EXECUTION_V3.4.6_ABLATION_MKTCAP_ALIGNMENT.md) v1.0
> **方法**: audit-driven-development 5 阶段 (Detection → Repair)

---

## Phase 0 — Spec 质量门

| 维度 | 判定 | 证据 |
|------|------|------|
| 可测试约束 | ✅ | 注入臂数量 (25 / 20)、`industry` 臂不带关键字、默认臂名与 `_is_trivial` 精确值 |
| 模块映射 | ✅ | 单模块 `ablation_runner.py`, 对应 EXECUTION §4.1/§4.2 |
| 接口契约 | ✅ | 两个方法全签名、参数插入位置、`extra_kwargs` / `arm_kwargs` 语义 |
| 修正项 | ✅ | 跨层口径不一致 (RESEARCH Q1-Q5) |
| 跨模块契约 | ✅ | `pipelines_v2._build_neutralizer_params` 自动切换 (F6)、`NeutralizerAdapter` 双条件 (F7) |

**Tier**: A (5/5) → 执行完整审计。

---

## Phase 1 — Spec 盘点

| 维度 | 代码 | Spec |
|------|------|------|
| `run_l3` 签名与转发 | `ablation_runner.py:1177-1299` | EXECUTION §4.2 |
| `run_l4_oat` 签名与转发 | `ablation_runner.py:1085-1175` | EXECUTION §4.1 |
| L4 默认口径切换 | `defaults['neutralization']` | RESEARCH Q4 / DESIGN §3 |
| 测试 | `test_ablation_mktcap_alignment.py` E1-E7 | EXECUTION §3 |
| 版本/文档 | 6 锚点 + 4 份文档 | EXECUTION §5 |

---

## Phase 2 — 多维度审查

### 2.1 签名一致性 ✅

- `run_l3(factor_data, fwd_returns, industry_data=None, market_cap_data=None, b3_full_result=None)`；
- `run_l4_oat(...)` 同上；
- 插入位置与 `run_l1` (`:893`) 完全一致，且全仓无 `b3_full_result` 位置传参 (RESEARCH F10)，兼容。

### 2.2 行为一致性 ✅

| 检查 | 结果 |
|------|------|
| `run_l3` 25 次 `run_single` 全部带市值 | ✅ E1 |
| `run_l3` 不传市值时零关键字 | ✅ E2 |
| `run_l4_oat` 16 个非中性化臂带市值 | ✅ E3 |
| `run_l4_oat` `industry` 臂不带; `none` / `industry+mktcap` 带 | ✅ E4 |
| 传市值时 `industry+mktcap` 为 trivial, `industry` 非 trivial | ✅ E5 |
| 不传市值时 `industry` 为 trivial (v3.4.5 行为不变) | ✅ E6 + 既有 `test_l4_oat_trivial_marking` |
| 两者 B3 参照均带市值 | ✅ E7a / E7b |

### 2.3 语义正确性 (关键)

- L4 的 `neutralization` 自由度**就是**中性化口径, 因此 `industry` 臂必须不传市值
  (否则管线自动切 `industry_marketcap`, RESEARCH F6/F8) —— 实现以 `arm_kwargs = {}` 显式表达,
  并附注释, 避免后续被"统一注入"式重构抹平;
- 默认口径随数据可用性切换, 保证 trivial 臂与 B3 同口径 (平凡比较成立), 这是本版最易错的点,
  已由 E5/E6 双向锁定。

### 2.4 测试盲区

| 盲区 | 判定 | 处置 |
|------|------|------|
| 未在 runner 层断言真实数值差异 (市值是否影响 IC) | P3 | 接受: 数值差异由 `pipelines_v2` / `adapters` 既有测试背书, runner 只负责转发契约 |
| 未覆盖"调用方传入含市值 B3 结果"的场景 | P3 | 接受: EXECUTION R2 已登记, 不在 runner 内强校验 |
| 断言恒真式 | 无 | E1/E2 断言调用次数与 `has_key`, E4/E5 断言精确臂名 |

### 2.5 跨模块契约 ✅

- ADR-036: 结果 `layer='L3' / 'L4'` 不变, 报告结构不变;
- ADR-042: 统一横截面秩管道不受影响 (仅中性化输入变化);
- 缓存代际 `v2.3.0-cache` 不变 (无中间产物结构变更)。

### 2.6 构建配置 / 版本 ✅

- 6 处版本锚点 = `3.4.6`; 无新增依赖; Python 3.13.5 下通过。

---

## Phase 3 — 问题分级与修复矩阵

| 编号 | 级别 | 描述 | 状态 |
|------|------|------|------|
| P0 | — | 无 | — |
| P1 | — | 无 | — |
| P2-1 | Major | EXECUTION §1 原写「L4 19 个臂统一注入」, 与实现 (B3 + 18 臂, `industry` 跳过) 不符 | ✅ 已修复 (改为 B3 + 18 臂并列举) |
| P2-2 | Major | RESEARCH §2 的 F1-F8 是修复前快照, 未标注会导致后续读者误判当前签名 | ✅ 已修复 (加「快照口径」说明) |
| P3-1 | Minor | L3/L4 其余自由度开关空转 (`_l3_*` / `_l4_*` 无消费者) 未在本任务修复 | ⏸ 接受: RESEARCH O1, EXECUTION R3, 单独立项 |
| P3-2 | Minor | `b3_full_result` 由调用方提供时不校验口径 | ⏸ 接受: RESEARCH O3, EXECUTION R2 |

**Phase 3.5 幻觉防护**: 全部 findings 经源码核对 (文件存在 / 行号有效 / 符号匹配), P2-1/P2-2 已同步修复。

---

## Phase 4 — 修复基线与验证

| 编号 | 严重度 | 描述 | 状态 | 验证 |
|------|--------|------|------|------|
| P2-1 | Major | 实施文档臂数口径 | ✅ 已修复 | 文档 diff |
| P2-2 | Major | 调研文档快照标注 | ✅ 已修复 | 文档 diff |

**测试基线**:

| 阶段 | 结果 |
|------|------|
| Red | `test_ablation_mktcap_alignment.py` → **6 failed / 2 passed** (`TypeError: unexpected keyword argument 'market_cap_data'`) |
| Green | 同上 → **8 passed** (0.14s) |
| 定向回归 | ablation_runner + decoupler 臂 + 本文件 → **113 passed** (18.14s) |
| 全量回归 | `pytest -q` → **1715 passed / 15 skipped / 0 failed** (2525.38s) |

---

## Phase 5 — 结论

- **P0/P1 = 0**; P2×2 已在本轮修复; P3×2 已登记接受。
- 数值评分: `100 − (0×20 + 0×8 + 2×3 + 2×1) = 92` → **A**。
- 设计承诺核对: L3 统一注入、L4 按选项选择性注入、默认口径随数据切换、未传市值路径逐位不变, 全部落地。
- 残余风险: 传市值后 L3/L4 数值会变化 (预期修复); L3/L4 多数旋钮仍空转 (RESEARCH O1), 跨层对比时需注意报表中 Δ≈0 的臂不代表"无效应"。

**审计判定**: PASS (无阻断项)。
