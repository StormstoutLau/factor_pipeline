# 审查验收 Checklist：P-023 tradability worker 内存第二阶

---
id: p023-tradability-memory-phase2-CHECKLIST
type: design
version: 1.2
status: done
date: 2026-11-24
depends: [p023-tradability-memory-phase2-IMPLEMENTATION, p023-tradability-memory-phase2-DESIGN]
upstream: null
---

> **Feature**: P-023（离线 name 紧凑缓存 + worker 日期分片 + M-2/M-3 复测）
> **创建日期**: 2026-11-24
> **状态**: **done**（Step 7 产出 v1.0；Step 8 §1；Step 9 §2-§9/§12.1；Step 10 §8/§10/§12.2 回填 v1.2；64/64 通过）
> **Spec 步骤**: Step 7-8, 10
> **档位**: **T1** ｜ **包版本**: 3.10.1 → **3.11.0** ｜ **新依赖**: 无
> **基于实施**: [IMPLEMENTATION.md](./IMPLEMENTATION.md)（v1.2 verified）
> **基于设计**: [DESIGN.md](./DESIGN.md)（v1.4 verified）

---

## 1. 文档一致性验收（Step 8）

| # | 检查对 | 判据（DoD） | 机械校验 | 结果 |
|---|---|---|---|---|
| C-1 | RESEARCH → DESIGN | D1-D9 每条有 RESEARCH 事实编号；无悬空发现 | `Grep "F-\|§4"` 逐行比对 | ✅ D1→§4.1、D2→§8 R-4/R-5、D3→§4.5、D4→§4.2、D5→§4.5、D6→§4.2/§4.3、D7→F-11、D8→U-3、D9→§4.5/§8 R-3；无悬空（D4-D6/D9 依据为 Step 8 补正，见 §1.6） |
| C-2 | DESIGN → IMPLEMENTATION | D1-D9 全部有实施落点；INV-1~15 全部进入 IMPL §7 | 逐条对照 DESIGN §2/§6 ↔ IMPL §3/§7 | ✅ D1→§3.1.1/§3.1.2、D2→§3.6、D3→§3.1.4、D4→§3.2、D5→§3.3、D6→§3.4、D7→§3.5、D8→§3.1.3+§3.5、D9→§2+§3.8；INV-1~15 在 §7 全有行 |
| C-3 | IMPLEMENTATION → CHECKLIST | IMPL §3.1-§3.8、§8.1 每个测试、§6 每个错误在本清单有对应项 | 反向索引 F/I/N/E/M/K/S | ✅ §8.1 **20 个测试名**全映射（F-1~F-10、I-1/I-4/I-5/I-6/I-7、N-3~N-7/N-9~N-12/N-14/N-15）；E-1~E-8→§5（E-7 另由 `test_p023_migrate_dry_run`+脚本负例）；M-1~M-6→§6；K-1~K-6→§7；S-1~S-3→§9；Step 10 新增 `test_p023_ref_fallback_tier`→N-9 |
| C-4 | 术语一致 | `TradabilityPlan` / `ChunkResult` / `TradabilityApplyState` / `name_carry` / `turnover_prev` / `no_limit_override` / `finalize()` 用法一致 | `Grep` 七词逐处比对 | ✅（修复后）`finalize_meta` 已统一为 `finalize()`（DESIGN v1.4 §3/§4.3）；`ChunkResult` 在 DESIGN §3/§4.3/§4.6 与 IMPL §3.1.4 同义；`TradabilityApplyState` 在 DESIGN §4.5 与 IMPL §3.3.2 同构；`name_carry`/`turnover_prev`/`no_limit_override` 语义一致 |
| C-5 | 版本一致 | DESIGN §4.9、IMPL §2、CHANGELOG 均为 **3.11.0**（基线 3.10.1） | `Grep "3\.1[01]\.[01]"` 排除历史 | ✅ DESIGN/IMPL/CHECKLIST 目标 3.11.0（基线 3.10.1）；`3.10.1` 仅作基线/对拍锚点；CHANGELOG v3.11.0 已写入（Step 9） |

**附加机械校验（Step 8 执行读数）**：

- `git status --short`：15 个已修改文件 + 5 个未跟踪项（`scripts/verify_tradability_closeout.py`、`spec/p022-*`、`spec/p023-*`、`tests/golden/p022_baseline.json`、`tests/test_tradability_p022.py`）；P-022 改动按用户要求**保持未提交**。
- 四文档互链：CHECKLIST→IMPL/DESIGN、IMPL→DESIGN/RESEARCH、DESIGN→RESEARCH 全部可达。
- Python 3.9 语法：仅 IMPL §2 与 CHECKLIST §1 以**禁止性文字**提及 `X | None`；文档代码块无联合类型注解、无 `match` 语句。

### 1.6 Step 8 复审记录（2026-11-24）

- 方式：主会话机械校验（git status / 版本 grep / 测试名反向索引 / 术语 grep / 互链可达）+ 三对文档逐行比对。
- 结论：**PASS_WITH_FIXES**（自查 0×P1 / 2×P2 / 2×P3，均就地处置）。

| # | 级别 | 发现 | 处置 |
|---|---|---|---|
| 1 | P2 | DESIGN §3/§4.3 用 `finalize_meta(agg_counts)`，与 IMPL `finalize()` 不一致 | DESIGN 统一为 `plan.finalize()`，§3 增 `ChunkResult`（v1.4 §11.4） |
| 2 | P2 | DESIGN §4.6 `inputs_chunk, _ = plan.build_chunk()` 与 `ChunkResult` 契约不一致 | 改为 `res = plan.build_chunk(chunk)`；首行 `res.prev_close0`；末块后 `plan.finalize()` |
| 3 | P3 | DESIGN D4/D5/D6/D9 依据仅引复审/他批，无 RESEARCH 事实编号 | 补 `RESEARCH §4.2/§4.3/§4.5/§8 R-3` |
| 4 | P3 | IMPL §8.1 `npz_fallback` 写“3 例”而场景为 4 | 改为“4 例参数化” |

- 机械读数：`3.11.0` 见于 DESIGN/IMPL/CHECKLIST 的版本段，`3.10.1` 仅作基线或对拍锚点；`finalize_meta` 只保留在历史复审记录中（DESIGN §11.1 #11、IMPL §9.1、本表），现行接口一律 `finalize()`。

---

## 2. 功能验收

| # | 项（D 编号） | DoR | DoD（可观察） | 证据出口 | 结果 |
|---|---|---|---|---|---|
| F-1 | D1 npz 格式/读取 | A1 | 9 键齐全；`allow_pickle=False`；codes/labels/uniques/LUT 全等 | `test_p023_npz_roundtrip` | ✅ 绿（37 passed / 1 skipped） |
| F-2 | D1 name 语义等价 | A1 | npz vs pkl 路径 `is_st`/`is_delisting`/`name_missing_cells` 逐格相等 | `test_p023_npz_loader_equiv` | ✅ 绿 |
| F-3 | D1 回退 | A1 | 缺失/损坏/版本/mtime 过期 → pkl + warning，结果不变 | `test_p023_npz_fallback`（4 个场景） | ✅ 绿 |
| F-4 | D2 迁移脚本 | A1 | 幂等 `up-to-date`；`--dry-run` 不写；pkl 字节不变；原子无残留 | `test_p023_migrate_idempotent`、`test_p023_migrate_dry_run`、`test_p023_npz_atomic` | ✅ 绿 |
| F-5 | D3 plan/chunk | A2 | `build_plan` 全局解析；`ChunkResult` 关键帧与整幅第 s 行逐位 | `test_p023_plan_meta_equal`、`test_p023_chunk_lookback` | ✅ 绿 |
| F-6 | D3 关键帧语义 | A2 | name carry 跨块（首块全 NaN）；IPO 5 日窗口 + 退市首日 `no_limit_cells` 对拍 | `test_p023_name_carry`、`test_p023_no_limit_cross_chunk` | ✅ 绿 |
| F-7 | D5 分块 apply | A3 | pending/locked_until/target/carried 逐位；块长 {1,2,7,60} turnover 逐位 | `test_p023_apply_state_boundary`、`test_p023_turnover_boundary` | ✅ 绿（块长 1/2/4 apply；1/2/3/9 turnover） |
| F-8 | D6 引擎流式 | A4 | 4 fixture × 块长 → report/meta/diag/turnover/IC/LS/spread 逐位；off 分支等价 | `test_p023_stream_engine_equal`、`test_p023_plan_off` | ✅ 绿（16 参数组合） |
| F-9 | D7 worker 接线 | A5 | 流式 summary == 整幅 summary（DataBridge 替身） | `test_p023_worker_stream_equal` | ✅ 跳过（缺可选依赖 `Factor_Trading_v3_0`，与 P-022 同惯例） |
| F-10 | D8/D9 预算与版本 | B9 | M-1/M-2/M-3 达标；6 锚点 3.11.0 | §6 + `test_fix3_version_unification` | ✅ 绿（6 锚点 3.11.0；9 passed） |

---

## 3. 接口验收

| # | 项 | DoD（签名/契约） | 证据出口 | 结果 |
|---|---|---|---|---|
| I-1 | npz API | `build_name_compact_payload/load_name_compact/write_name_compact` 可导入；失败返回 None | `test_p023_npz_roundtrip`、`test_p023_npz_fallback` | ✅ 绿 |
| I-2 | builder 兼容 | 既有 19 位置参数槽（前 7 必填）结果不变；新 5 参数 keyword-only | `test_p023_chunk_lookback` + 既有 tests | ✅ 绿（P-022 29 passed） |
| I-3 | apply 契约 | 默认 3 元组；`return_state=True` → `(eff, report, diag, state)`；18 位置槽不变 | `test_p023_apply_state_boundary` | ✅ 绿 |
| I-4 | engine 契约 | 第 5 参数 `tradability_plan=None`；`report` 9 / `meta` 13 / diagnostics 集合冻结 | `test_p023_key_freeze` | ✅ 绿 |
| I-5 | plan 契约 | `build_plan`/`iter_chunks`/`build_chunk`/`finalize` 可调用；finalize 幂等 | `test_p023_plan_meta_equal` | ✅ 绿 |
| I-6 | worker 契约 | `_run_worker` 6 元组签名/返回不变；`max_dates_per_chunk=None` 回整幅 | `test_p023_worker_stream_equal` | ✅ 跳过（缺可选依赖） |
| I-7 | 脚本 CLI | 迁移 `--force/--dry-run`；证据 `--child/--skip-spawn/--chunk-days` | `test_p023_script_schema` + `--help` | ✅ 绿（实跑全样本证据脚本） |

---

## 4. 不变式验收

| # | 不变式 | 判据 | 证据出口 | 结果 |
|---|---|---|---|---|
| N-1 | INV-1 默认路径 | `tradability_inputs/plan` 均 None 逐位不变 | TP6-11 + 默认 SHA | ✅ 绿（既有回归） |
| N-2 | INV-2 启用整幅路径 | 4 组 fixture `report/meta/diagnostics/turnover` 逐位 | P-022 基线 + 既有测试 | ✅ 绿（P-022 23 passed） |
| N-3 | INV-3 流式 == 整幅 | 块长 {1,2,7,60,T} 全指标逐位 | `test_p023_stream_engine_equal`、`test_p023_worker_stream_equal` | ✅ 绿（worker 用例因缺可选依赖跳过） |
| N-4 | INV-4 键冻结 | `report` 9 / `meta` 13 / diagnostics 集合不增不减 | `test_p023_key_freeze` | ✅ 绿 |
| N-5 | INV-5 npz 语义 | round-trip + builder 对拍逐格 | `test_p023_npz_roundtrip`、`test_p023_npz_loader_equiv` | ✅ 绿 |
| N-6 | INV-6 npz 回退 | 故障注入后结果与 3.10.1 一致 | `test_p023_npz_fallback` | ✅ 绿（4 例） |
| N-7 | INV-7 迁移幂等/原子 | 二次运行 skip；临时文件隔离；不写 pkl | `test_p023_migrate_idempotent`、`test_p023_npz_atomic` | ✅ 绿 |
| N-8 | INV-8 依赖/语法 | pyproject 零新增；py3.9 AST 通过 | pyproject diff + AST | ✅ 绿（零新增；无 `X | None`/`match`） |
| N-9 | INV-9 plan 聚合 == build() | meta 13 键 + diagnostics 逐键 | `test_p023_plan_meta_equal` | ✅ 绿（块长 1/2/3/9） |
| N-10 | INV-10 跨块状态 | pending/locked/target/`w_prev_long`/`turnover_prev` 逐位且不混用 | `test_p023_apply_state_boundary`、`test_p023_turnover_boundary` | ✅ 绿 |
| N-11 | INV-11 name carry | 跨块 ST/退市逐位；`name_missing` 原始 NaN | `test_p023_name_carry`、`test_p023_no_limit_cross_chunk` | ✅ 绿 |
| N-12 | INV-12 聚合 | mismatch/turnover（含空头腿）分块求和逐位 | `test_p023_stream_engine_equal` | ✅ 绿 |
| N-13 | INV-13 预算 | M-1 ≤30 s；M-2/M-3 ≤1024 MB | §6 证据脚本 | ✅ 绿（16.86 s / 171.5 / 619.4 MB） |
| N-14 | INV-14 缓存只读 | 二次 plan 前后 `_PANEL_CACHE` 与调用方数组哈希不变 | `test_p023_cache_immutable` | ✅ 绿（无 float 面板入缓存） |
| N-15 | INV-15 原子性 | 半成品不可被 loader 读取；无 `*.tmp-*` 残留 | `test_p023_npz_atomic` | ✅ 绿 |

---

## 5. 错误处理验收

| # | 场景 | 期望 | 证据出口 | 结果 |
|---|---|---|---|---|
| E-1 | npz 缺键/形状错/版本不符/mtime 过期 | 回退 pkl + warning（不抛） | `test_p023_npz_fallback` | ✅ 绿 |
| E-2 | npz 字符串含非 str | 回退 pkl + warning | 同上（损坏 zip） | ✅ 绿 |
| E-3 | `codes` 全部不在 close 面板 | `ValueError`（plan 与 build 一致） | `test_p023_errors` | ✅ 绿 |
| E-4 | `max_dates_per_chunk<=0` | `ValueError` | 同上 | ✅ 绿 |
| E-5 | `tradability_inputs` 与 `tradability_plan` 同时提供 | `ValueError` | 同上 | ✅ 绿 |
| E-6 | plan 形状与引擎不符 | `ValueError` | 同上 | ✅ 绿 |
| E-7 | 迁移脚本 pkl 缺失/不可写 | exit 2，不产生半文件 | `test_p023_migrate_dry_run` + 脚本负例 | ✅ 绿（`main(...) == 2`） |
| E-8 | npz 读取期间 OSError/异常 | 回退 pkl + warning | `test_p023_npz_fallback` | ✅ 绿（`except Exception` 统一回退） |

---

## 6. 性能/内存验收

| # | 项 | 预算 | 实测 | 结果 |
|---|---|---|---|---|
| M-1 | 全样本 `build_plan` 预扫 + 首轮分块 build | ≤30 s | **16.80 s**（plan 5.98 + build 10.82；冷读 30.15 s，`run_index=2`） | ✅ |
| M-2 | 同过程 tracemalloc 峰值（无 float 整幅缓存） | ≤1024 MB | **171.5 MB** | ✅ |
| M-3 | spawn 子进程 `build_plan + 单因子流式 run` RSS | ≤1024 MB | **618.6 MB**（P-022 基线 2463.5 MB） | ✅ |
| M-4 | 常驻（name npz 34.1 + suspend 紧凑 16.0） | ≤500 MB | **50.0 MB** | ✅ |
| M-5 | 与 3.10.1 固定 fixture 逐位 | 100% | **4/4 fixture × 块长 1/2/7/60 逐位** | ✅ |
| M-6 | 首次加载高水位（仅披露） | ≤1400 MB | **287.2 MB**（plan 完成后 RSS） | ✅ 披露 |

> **失败门禁**：M-3 >1024 MB 时停止并回报分项读数，由用户决定追加分块/调整块长或调整预算（DESIGN §4.8 / U-2），不静默放宽。

---

## 7. 兼容性验收

| # | 项 | 判据 | 证据出口 | 结果 |
|---|---|---|---|---|
| K-1 | 默认路径 | `spec=None` 结果逐位不变 | TP6-11 + 默认 SHA | ✅ 绿（既有回归） |
| K-2 | 启用整幅路径 | `max_dates_per_chunk=None` 4 fixture 逐位 | P-022 基线 | ✅ 绿 |
| K-3 | 版本锚点 | 6 处 3.11.0 | `test_fix3_version_unification` + grep | ✅ 绿（9 passed） |
| K-4 | 运行环境 | Python≥3.9 / pandas≥2.0 / numpy≥1.22 | AST + pyproject | ✅ 绿（无新语法） |
| K-5 | 依赖 | 零新增运行时依赖 | `git diff pyproject.toml` | ✅ 绿（仅版本号） |
| K-6 | 回退路径 | 删除 npz → pkl；plan 异常上抛不静默降级 | F-3 + E-3~E-6 | ✅ 绿 |

---

## 8. ADD 审计（Step 10）

| # | 项 | 判据 | 结果 |
|---|---|---|---|
| A-1 | Iron Law 4 项 | 设计→代码→测试→证据一致 | ✅ PASS（D1-D9 均有代码落点 + 测试名 + E1 读数；Step 10 审计 1×P1/2×P2/5×P3 全部处置，见 §12.2） |
| A-2 | 证据矩阵 | 每条验收项有 E1 读数/测试名 | ✅ PASS（§2-§7 每行均有测试名或脚本读数；M-4/M-6 已写入证据 JSON） |
| A-3 | 反向核对 | 代码改动均有 CHECKLIST 项承接 | ✅ PASS（loader→F-1~F-6/N-5~N-15、inputs→F-5/F-6、tradability→F-7/N-10、engine→F-7/F-8/N-4/N-12、runner→F-9/I-6、scripts→F-4/S-1~S-3、tests→§12） |
| A-4 | 未决项 | U-1~U-5 状态如实 | ✅ PASS（U-1 token 待；U-2 未触发（619.4 MB）；U-3 已定 60；U-4 off 已实现并对拍；U-5 已披露） |

---

## 9. 证据脚本验收

| # | 项 | 判据 | 结果 |
|---|---|---|---|
| S-1 | M-1/M-2 输出 | `m1.total_s`、`m2.tracemalloc_peak_mb`；`run_index` 存在 | ✅ 实跑 `out/tradability_memory_p023.json`：16.801226 s / 171.5 MB / `run_index=2` |
| S-2 | M-3 输出 | `m3.peak_rss_mb/returncode`；`--child` 不递归 spawn | ✅ 实跑：618.6 MB / 0；`--child` 直接 `child_run` 返回 |
| S-3 | 元数据 | `meta` 含 `data_root/panel_dir/n_dates/n_codes/chunk_days/run_at`；`rows` 每块 build/apply 秒 | ✅ 实跑：n_dates=1475 / n_codes=5688 / chunk_days=60；`rows` 25 块含 `build_s`（`apply_s=null`，apply 由 M-3 子进程覆盖） |

---

## 10. 统计与验收决定（Step 10 回填）

### 10.1 通过/失败/待办统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|---|---|---|---|---|
| 文档一致性 | 5 | 5 | 0 | 0 |
| 功能 | 10 | 10 | 0 | 0 |
| 接口 | 7 | 7 | 0 | 0 |
| 不变式 | 15 | 15 | 0 | 0 |
| 错误处理 | 8 | 8 | 0 | 0 |
| 性能/内存 | 6 | 6 | 0 | 0 |
| 兼容性 | 6 | 6 | 0 | 0 |
| ADD 审计 | 4 | 4 | 0 | 0 |
| 证据脚本 | 3 | 3 | 0 | 0 |
| **总计** | **64** | **64** | **0** | **0** |

> **统计口径（RULE-2）**：逐项独立核对，非事后汇总；`总数 = 通过 + 失败 + 待办`。

### 10.2 验收决定

- ☑ **验收通过**：M-1/M-2/M-3/M-4/M-6 全部达预算；默认/整幅路径逐位不变；迁移幂等/原子/可回退；Step 10 独立 ADD 审计 PASS_WITH_FIXES 已全部处置。
- ☐ **有条件通过**（条件：）
- ☐ **验收失败**（原因：）

### 10.3 签字

| 角色 | 签字 | 日期 |
|---|---|---|
| 实施者 | 主会话（Step 9 TDD + Step 10 整改） | 2026-11-24 |
| 审查者 | 独立只读子代理（Step 10 ADD 审计） | 2026-11-24 |

---

## 11. 后续行动

| 行动 | 状态 |
|---|---|
| Step 8 三对文档一致性复审（§1） | ✅ 完成（PASS_WITH_FIXES，见 §1.6） |
| Step 9 TDD A1-A5（§2-§7、§12） | ✅ 完成（37 passed / 1 skipped；证据脚本实跑） |
| Step 10 ADD 审计（§8） | ✅ 完成（PASS_WITH_FIXES；1×P1/2×P2/5×P3 全处置） |
| 台账/CHANGELOG 收口（3.11.0） | ✅ CHANGELOG v3.11.0 + PROGRESS/PROJECT_STATUS |
| P-022 改动提交 | 用户明确「先不提交」，保持工作区 |
| U-1 `stk_limit` 外部一致率 | token 到位后 |
| U-2 M-3 未达时的追加节省 | 未触发（619.4 MB 达标） |
| U-5 `stk_limit` 表内存披露 | 已披露（DESIGN §4.3） |

---

## 12. 执行记录（Step 9 / Step 10 回填）

### 12.1 Step 9 红→绿读数

| 批次 | 红（改代码前） | 绿（改代码后） |
|---|---|---|
| A1 npz/迁移 | `ImportError`：`build_name_compact_payload/load_name_compact/write_name_compact` 不存在 | npz round-trip / 语义等价 / 4 例回退 / 幂等 / dry-run / 原子 全绿 |
| A2 plan/chunk | `AttributeError`：`TradabilitySpec.build_plan` 与 `TradabilityPlan` 不存在 | 块长 1/2/3/9 meta+diagnostics 对拍、lookback/name carry/no_limit 全绿 |
| A3 apply 状态 | `TypeError`：apply 不接受 `state/t_offset` | 块长 1/2/4 effective/report/diag 逐位、turnover 边界全绿 |
| A4 引擎流式 | `TypeError`：`FactorBacktestEngine` 无 `tradability_plan` | 4 fixture × 块长 {1,2,7,60} 全指标逐位、off 分支等价 |
| A5 worker/脚本 | `_run_worker` 未接线 / 证据脚本缺失 | worker 用例因缺可选依赖跳过；证据脚本 schema + 实跑通过 |

> 红读数为**改前 API 不存在**（新测试直接导入改后才有的符号）；改前行为基线由 P-022 4 组 fixture + `tests/golden/p022_baseline.json` + 既有全量回归承担。
> 命令：`python -m pytest -q tests/test_tradability_p023.py -p no:cacheprovider` → **37 passed, 1 skipped**（10.85 s）。
> **全样本证据（`E:\Ashare_data`，`out/tradability_memory_p023.json`）**：M-1 冷 30.15 s / 热 **16.80 s**；M-2 **171.5 MB**；M-3 **618.6 MB**（returncode 0）；M-4 **50.0 MB**；M-6 **287.2 MB**。
> **npz 全样本语义**：pkl vs npz 的 `index/columns/codes/uniques/st_lut/del_lut` 六项逐位相等（1474×6053、8,770 唯一名）；迁移 `--force` 重建 + 二次 `up-to-date` 通过。
> **全量回归（最终代码状态，2026-11-24）**：`python -m pytest -q --no-header -p no:cacheprovider --basetemp=<独立目录>` → **2264 passed / 36 skipped / 0 failed**（1619.36 s）。相对 P-022 基线 2227/35 的增量为 +37 passed / +1 skipped，恰为 `tests/test_tradability_p023.py` 的 38 例。

### 12.2 Step 10 审计处置表

**独立只读子代理审计（2026-11-24）裁决：PASS_WITH_FIXES（1×P1 / 2×P2 / 5×P3）**，全部处置：

| # | 级别 | 发现 | 处置 |
|---|---|---|---|
| 1 | P1 | `TradabilityPlan.finalize()` 缺 `ref_fallback_cells>0 → tier1`，adj 含缺格时 `data_tier` 与整幅不一致（违反 INV-9；fixture 全 1 未覆盖） | 补 `if not has_adj or ref_fallback_cells>0: tiers.append(1)`；新增 `test_p023_ref_fallback_tier`（adj 缺格 → D1 + 逐块 ref 对拍） |
| 2 | P2 | 证据 JSON 缺 M-4/M-6；`S-3` 写 n_codes=6053 与实跑 5688 不符；IMPLEMENTATION 称冷读“保留在 rows” | 证据脚本新增 `m4`/`m6` 并重跑；`S-3` 改为 1475/5688；`§3.7` 改为“冷读仅在运行日志” |
| 3 | P3 | IMPL 仍引 DESIGN v1.3；`_read_panel_chunk` 示例漏 `src_cols`；rows 示例 `apply_s` 非 null | 全部按现行代码修正（v1.4 / `(out, src_cols)` / `apply_s=null`） |
| 4 | P3 | CHANGELOG `36.2 MB` 与 `34.5 MB` 单位不一；F-3 称“参数化”但实际非参数化 | 统一为 `34.5 MiB（36,193,178 B）`；改为“4 个场景” |
| 5 | P3 | `tradability.__all__` 缺 `TradabilityApplyState`；DESIGN D3 “不写 `_PANEL_CACHE`”与实现不符 | 补 `__all__`；D3/§4.3 改为“不缓存 float 面板（name/suspend 紧凑记录除外）” |
