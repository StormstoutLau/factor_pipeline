# CHECKLIST v3.6.0 修复包 — 复审 R1-R4

> **对照工件**: [EXECUTION_V3.6.0_FIX_PACK.md](../EXECUTION_V3.6.0_FIX_PACK.md) v1.0
> **上游证据**: [ADD 审计 P2-5 / P3-5~P3-7](2026-11-18-v3.6.0-governance-base-audit.md#L162) / EXECUTION §9.9
> **时点**: 2026-11-18 开批（状态列在实施后回填）
> **判定规则**: 每项须有可复现命令或文件行号；红读数未捕获不得标绿（F5）

---

## §1 修复项验收（F1-F4）

| # | DoD | 验收方式 | 状态 |
|---|-----|---------|------|
| F1 | 省略与显式默认（`price_convention`、`gate_policy_version`）→ 同 `record_id`；字段值一致 | T51 + `governance.py` 读码 | 通过（红 `record_id` 分裂 → 绿；`ID_DEFAULTS` 注入于 `compute_record_id` 前） |
| F2 | G4(`passed=False`) + qfq 允许；G4(`passed=True`) + qfq 拒绝；production + qfq 仍拒绝 | T52 | 通过（红 误拒 → 绿；`golden = G4 存在且 passed`，拒绝用 `match="qfq"` 锚定来源） |
| F3 | `GAP_CODE_BY_FIELD` 集中映射；`barra_stale`/`industry_stale` 不变；映射外回退 `_missing` | T53 | 通过（红 ImportError → 绿；T49/T53 同跑） |
| F4 | `OLD_VERSIONS` 含 3.5.3；`verify_fix3_manual.py` exit 0、无残留 | T54 + 脚本运行 | 通过（红 缺 3.5.3 → 绿；脚本 5/5、exit 0、0 残留） |

## §2 TDD 双读数（F5）

| 测试 | 红（命令 + 非零退出 + 关键失败行） | 绿（命令 + 退出 0 + 用例数） |
|------|----------------------------------|---------------------------|
| T51 | `4 failed in 0.55s`：`record_id` 分裂（`7d90...` vs `6d04...`） | `34 passed in 3.81s`（三文件联合） |
| T52 | 同上命令：`ValidationError: qfq 禁止用于 production/golden` | 同上 |
| T53 | 同上命令：`ImportError: cannot import name 'GAP_CODE_BY_FIELD'` | 同上 |
| T54 | 同上命令：`'3.5.3' not found in ['2.0.0', '2.1.0']` | 同上 |

> 红命令与绿命令全文见 [EXECUTION §5](../EXECUTION_V3.6.0_FIX_PACK.md)；
> 中间读数（T52 首版构造缺陷修正）已如实登记于 EXECUTION §5。

## §3 兼容性与零变更

| 项 | DoD | 状态 |
|----|-----|------|
| 无存量迁移 | 仓库根无 `*.duckdb`；`record_id` 变化仅影响省略默认值的调用 | 通过（2026-11-18 复核，仓库根无 duckdb 文件） |
| 版本号 / 缓存代际 | 6 锚点仍 3.6.0；缓存仍 `v2.3.0-cache`；`gate version-consistency` pass | 通过（gate `verdict=pass exit=0`；脚本 5/5） |
| 语法下限 | AST 扫描 0 违规（Python 3.9） | 通过（`py39_violations=[]`，两改动模块） |
| 全量回归 | **1925 passed / 7 skipped**（1920 + 5 新例：T51/T52/T53/T54a/T54b），0 失败 0 新增 skip；耗时比 0.59（≤1.2 预算） | 通过（gate unit-tests seq 30，exit 0；898.75s；+5 说明见 FIX_PACK §5） |
| golden 零变更 | T31 `max_abs_diff<=1e-10` 不受影响 | 通过（全量 gate 内 0 失败；F1/F2 均不触 golden 数值路径） |

## §4 文档同步

| 项 | DoD | 状态 |
|----|-----|------|
| 主 EXECUTION | §9.9 R1-R4 处置列更新为「已修复（本批）」+ 回填红绿读数 | 完成（R1-R4 → 已修复 F1-F4，链接 FIX_PACK §5） |
| 审计报告 | Phase 8 P2-5 / P3-5~P3-7 状态更新；Phase 9 修复复核 | 完成（P2-5/P3-5~P3-7 → **已修复**，T51-T54 红→绿） |
| PROJECT_STATUS | P1-A 块补修复包结果 | 完成（含 1925/7 读数） |
| CHANGELOG | v3.6.0「复审修复包」段 + 5 例、全量 1925 | 完成 |
| 一致性 review | [CONSISTENCY_REVIEW_V3.6.0_FIX_PACK.md](CONSISTENCY_REVIEW_V3.6.0_FIX_PACK.md) 实施后复核 | 完成（§5 C1-C5 全勾） |

## §5 证据出口

| 范围 | 证据 | 等级 |
|------|------|------|
| 修复正确性 | T51-T54 红→绿读数（§2） | E1 |
| 复审来源 | `out/review_v360_t46_e8_results.txt`（R1-R4） | E2 |
| 零变更 | `gate unit-tests`（seq 30）+ `gate version-consistency`（seq 29）事件流 | E1 |
| 代码行号 | `Lxxx@WORKTREE`，提交后回填 | E3（P3-1 沿用） |

## §6 汇总（实施后）

| 分项 | 通过 | 失败 | 阻塞 |
|------|------|------|------|
| 修复项（4） | 4（F1-F4） | 0 | 0 |
| TDD 双读数（4 红 + 5 绿） | 4 红 / 5 绿（T54b 表征先绿） | 0 | 0 |
| 兼容性（5） | 5 | 0 | 0 |
| 文档同步（5） | 5 | 0 | 0 |

> 汇总只能由逐行状态计数，禁止推算（RULE-2）。E5 级证据不得进入结论。
> **验收结论：通过** —— 修复包 F1-F4 全部落地并经双读数验证；P2-5（MAJOR）清零。
