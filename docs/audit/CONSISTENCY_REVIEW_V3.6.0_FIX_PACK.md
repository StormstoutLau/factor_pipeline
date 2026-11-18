# CONSISTENCY REVIEW — v3.6.0 修复包（复审 R1-R4）

> **审查对象**: [EXECUTION_V3.6.0_FIX_PACK.md](../EXECUTION_V3.6.0_FIX_PACK.md) v1.0 ↔
> [CHECKLIST_V3.6.0_FIX_PACK.md](CHECKLIST_V3.6.0_FIX_PACK.md) v1.0
> **上游基线**: ADD 审计 P2-5 / P3-5~P3-7（`2026-11-18-v3.6.0-governance-base-audit.md`）
> **时点**: 2026-11-18 开批（步骤 8 初版；实施后按 §5 复核）

---

## §1 反向引用矩阵（问题 → 任务 → 测试 → 验收）

| 上游问题 | 修复任务 | 设计决策 | 测试 | 验收项 |
|---------|---------|---------|------|--------|
| R1 / P2-5（MAJOR） | F1 | DR-F1 | T51 | CHECKLIST §1 F1 |
| R2 / P3-5 | F2 | DR-F2 | T52 | CHECKLIST §1 F2 |
| R3 / P3-6 | F3 | DR-F3 | T53 | CHECKLIST §1 F3 |
| R4 / P3-7 | F4 | DR-F4 | T54 | CHECKLIST §1 F4 |
| P2-1 性能债 | 不在本批 | — | — | EXECUTION §8 U1 |
| P3-1 E3 行号 | 提交后动作 | — | — | EXECUTION §8 U2 |

> 覆盖读数：4/4 修复项有「来源 → 任务 → 决策 → 测试 → 验收」完整链；2 项明确排除并登记 §8。

## §2 事实 ↔ 变更点对齐

| 事实（EXECUTION §2） | 变更点（§4） | 一致 |
|---------------------|-------------|------|
| F1 `price_convention` 未注入 | 4.1 `ID_DEFAULTS` + `setdefault` | 是 |
| F2 `gate_policy_version` 同模式 | 4.1 同一映射 | 是 |
| F3 golden 用键存在 | 4.1 validator 改 `payload.passed` | 是 |
| F4 known_gap 白名单 | 4.2 `GAP_CODE_BY_FIELD` | 是 |
| F5 扫描只匹配代码赋值 | 4.3 仅改 `OLD_VERSIONS` | 是 |
| F6 无存量库 | §6 零迁移声明 | 是 |
| F7 无硬编码 id | §6 兼容性说明 | 是 |
| F8 `_gate(passed)` 可用 | 4.4 T52 断言 | 是 |

## §3 计数与版本

| 检查 | 读数 |
|------|------|
| 修复任务 | 4（F1-F4），0 未映射 |
| 测试 | 4（T51-T54），编号接续 T50 |
| 变更文件 | 3 代码/脚本 + 3 测试文件（governance/data_contract/verify_fix3_manual；governance/data_contract/test_fix3_version_unification） |
| 版本锚点 | 不 bump（3.6.0）；缓存 `v2.3.0-cache` 不变 |
| 新增依赖 | 0 |
| 预期全量 | 1924 passed / 7 skipped（+4） |

## §4 冲突检查

| 潜在冲突 | 判定 |
|---------|------|
| 改 `record_id` 是否破坏 T1/T2/T3 | 否：断言确定性/敏感性，不依赖字面值；F7 无硬编码 |
| 改 golden 语义是否破坏 T47 | 否：T47 的 golden 用例为 `passed=True`，仍拒绝 |
| `GAP_CODE_BY_FIELD` 是否改变对外码名 | 否：`barra_stale`/`industry_stale` 不变（T49 应继续绿） |
| 追加 3.5.3 是否引起脚本误报 | 否：F9 代码级残留 0；T54 子进程 exit 0 兜底 |
| 是否需新 ADR | 否：均为 ADR-050 与设计 §5.7 的实现对齐（EXECUTION §8 U4） |

## §5 实施后复核清单

| # | 复核项 | 状态 |
|---|-------|------|
| C1 | 四项红读数已捕获并回填（F5） | 完成（`4 failed in 0.55s`：T51 id 分裂 / T52 qfq 误拒 / T53 ImportError / T54 缺 3.5.3；EXECUTION §5 含 T52 中间修正登记） |
| C2 | 全量 1924 / 7 skipped，0 失败 | 完成（**1925** / 7 skipped，seq 30 exit 0；+5 而非 +4 —— T54 实现为 test_08/test_09 两例，见 FIX_PACK §5 +5 说明） |
| C3 | `gate version-consistency` pass；6 锚点未变 | 完成（seq 29 `verdict=pass exit=0`；脚本 5/5、`py39_violations=[]`） |
| C4 | 主 EXECUTION §9.9 / ADD 审计 Phase 8 / PROJECT_STATUS / CHANGELOG 同步 | 完成（R1-R4 → 已修复 F1-F4；CHANGELOG 增修复包段） |
| C5 | 本文件 §1-§3 读数与实施后实际一致 | 完成（4/4 链闭合；变更文件 = 3 实现 + 3 测试，与 §3 声明一致） |

**结论（实施后）**：通过 —— C1/C3/C4/C5 完成；C2 待全量回归 gate 回填。
