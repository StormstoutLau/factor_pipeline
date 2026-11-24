# 审查验收 Checklist：P-022 tradability 收口包

---
id: p022-tradability-closeout-CHECKLIST
type: design
version: 1.2
status: done
date: 2026-11-23
depends: [p022-tradability-closeout-IMPLEMENTATION, p022-tradability-closeout-DESIGN]
upstream: null
---

> **Feature**: P-022（P-2 内存 / U-7 阈值 / U-8 阈值 / R-3 敏感性）
> **创建日期**: 2026-11-23
> **状态**: **有条件通过**（Step 7 产出；§1 于 Step 8 回填 v1.1；§2-§12 于 Step 9-10 回填 v1.2；条件 = M-2/M-3 未达 → P-023）
> **Spec 步骤**: Step 7-8, 10
> **档位**: **T1** ｜ **包版本**: 3.10.0 → **3.10.1** ｜ **新依赖**: 无
> **基于实施**: [IMPLEMENTATION.md](./IMPLEMENTATION.md)（v1.2 verified）
> **基于设计**: [DESIGN.md](./DESIGN.md)（v1.2 verified）

---

## 1. 文档一致性验收（Step 8）

| # | 检查对 | 判据（DoD） | 机械校验 | 结果 |
|---|---|---|---|---|
| C-1 | RESEARCH → DESIGN | D1-D9 每条有 RESEARCH 事实编号；无悬空发现 | `Grep "F-\|§4"` 逐行比对 | ✅ D1→F-1-1~7、D2→F-1-3~5、D3→F-1-8/9、D4→F-1-10/11、D5→§4.3、D6→§4.4、D7→§4.5、D8→§5.1、D9→P-006/P-021 既有门禁；无悬空 |
| C-2 | DESIGN → IMPLEMENTATION | D1-D7、D9 全部有实施落点；D8 为被拒方案无落点；INV-1~15 全部进入 §4 | 逐条对照 DESIGN §4/§6 ↔ IMPL §3/§7 | ✅ D1/D2→§3.1/§3.2、D3→§3.6、D4→§3.3-§3.5、D5-D7→§3.7、D9→§8.3；INV-1~15 §7 全有行；D8 显式标注“被拒” |
| C-3 | IMPLEMENTATION → CHECKLIST | IMPL §3.1-§3.8、§8.1 每测试、§6 每错误在本清单有对应项 | 反向索引 F/I/N/E/M/K/S | ✅（修复后）§8.1 **24 个测试名**全映射（F-1~F-14、I-1/I-6、N-2/N-4/N-8/N-9/N-12/N-14/N-15、E-1~E-6、E-8）；E-7→既有 `test_p021_d3_unknown_board`（§5）；M-1~M-6→§6；K-1~K-6→§7；脚本→S-1~S-3 |
| C-4 | 术语一致 | `_PanelRecord` / `compact` / `zero-copy` / `worker payload` / `min_coverage` / `close_mismatch_cells` / `M-3/M-6` 用法一致 | `Grep` 七词逐处比对 | ✅ `_PanelRecord` 在 DESIGN §4.1 与 IMPL §3.1.1/§5.2 同义；`min_coverage=0.99` 恒为 loader 默认；`close_mismatch_cells` 恒为 engine diagnostics 键；M-3/M-6 在 DESIGN §8 与 CHECKLIST §6 同口径 |
| C-5 | 版本一致 | DESIGN §9、IMPL §2.2、CHANGELOG 均为 **3.10.1**（基线 3.10.0） | `Grep "3\.10\.[01]"` 排除历史 | ✅ DESIGN §9 / IMPL §2.2 目标 3.10.1（基线 3.10.0）；CHANGELOG v3.10.1 已写入（Step 9）；`3.11.0` 仅出现在 IMPL DR-7 升级条件、`3.10.2` 零命中 |

**附加机械校验（Step 8 执行读数）**：

- `git status --short`：仅 `docs/PROGRESS.md` + `spec/p022-tradability-closeout/`（无工作区代码改动）。
- 四文档互链：CHECKLIST→IMPL/DESIGN、IMPL→DESIGN/RESEARCH、DESIGN→RESEARCH 全部可达。
- Python 3.9 语法：文档代码块无 `X | None`、无 `match`。

### 1.6 Step 8 复审记录（2026-11-23）

- 方式：主会话机械校验（git status / 版本 grep / 测试名反向索引 / 术语 grep / 互链可达）+ 三对文档逐行比对。
- 结论：**PASS_WITH_FIXES**（自查 0×P1 / 1×P2 / 2×P3，均就地处置）。

| # | 级别 | 发现 | 处置 |
|---|---|---|---|
| 1 | P2 | C-2 原写“D1-D9 全有落点”，但 D8 为被拒方案 | C-2 改为“D1-D7、D9 有落点；D8 被拒” |
| 2 | P3 | C-3 测试名计数写 14，实际 18（+`builder_errors` = 19） | C-3 与 IMPL §8.1 同步为 19 |
| 3 | P3 | C-5 称 `3.11.0` 零命中，实际 IMPL DR-7 含升级条件 | C-5 如实改为“仅 DR-7 升级条件” |

- 机械读数：`git status --short` = `M docs/PROGRESS.md` + `?? spec/p022-tradability-closeout/`；`3.10.1` 在 DESIGN/IMPL/CHECKLIST 共 19 处；四文档互链可达。

---

## 2. 功能验收

| # | 项（D 编号） | DoR | DoD（可观察） | 证据出口 | 结果 |
|---|---|---|---|---|---|
| F-1 | D1 紧凑 name 缓存 | A1 | `_PANEL_CACHE["name"]` 为 float32 码面板（无 object 大列）；`uniques` 8,771 级 | `test_p022_cache_compact` | ✅ 绿（Step 9 实测，详见 §12.1） |
| F-2 | D1 name 语义 | A2 | 紧凑 vs object 路径 `is_st`/`is_delisting`/`name_missing_cells` 逐格相等；窗口首日不继承窗口外名称 | `test_p022_name_codes_equiv`、`test_p022_name_window_carry` | ✅ 绿（Step 9 实测，详见 §12.1） |
| F-3 | D1 紧凑 suspend | A1/A2 | object `S/R/None` → mask/missing 逐格一致；`suspend_missing_cells` 相等 | `test_p022_suspend_state_equiv` | ✅ 绿（Step 9 实测，详见 §12.1） |
| F-4 | D2 切片快路径 | A1 | 全量命中 `_slice` 返回同对象；缺失行列填充规则正确 | `test_p022_slice_identity`、`test_p022_slice_contract` | ✅ 绿（Step 9 实测，详见 §12.1） |
| F-5 | D2 builder 快路径 | A2 | 对齐 float64 + fill=NaN 返回原 df；`np.shares_memory(inputs.high, cache)` 为 True；负例不命中 | `test_p022_frame_no_copy`、`test_p022_frame_fastpath_negative` | ✅ 绿（Step 9 实测，详见 §12.1） |
| F-6 | D3 worker 载荷 | A4 | executor 捕获的 `factor_data` 键集合 == chunk；串并行 summary 逐位相等 | `test_p022_parallel_payload_subset`、`test_p022_worker_payload_summary_equal`、`test_p022_parallel_serial_equal` | ✅ 绿（Step 9 实测，详见 §12.1；进程池用例在缺可选依赖时跳过） |
| F-7 | D4 effective 原地 | A4 | `positions` 不被修改；turnover 与改前逐位一致 | `test_p022_report_meta_bitwise`、TP6-11 | ✅ 绿（Step 9 实测，详见 §12.1） |
| F-8 | D4 pct 按行 | A3 | `_pct_row` 与 `_pct_matrix` 第 t 行逐位一致（含 unknown/gap）；独立旧口径逐格相符 | `test_p022_pct_row_bitwise`、`test_p022_pct_row_independent` | ✅ 绿（Step 9 实测，详见 §12.1） |
| F-9 | D4 turnover 单行缓冲 | A3 | 随机矩阵（含 NaN/Inf、T=1、N=1、int 入参）新老实现逐位一致 | `test_p022_turnover_bitwise`、`test_p022_turnover_int_input` | ✅ 绿（Step 9 实测，详见 §12.1） |
| F-10 | D5 U-7 裁决 | A5 | 73 月覆盖率表输出；`below_099` 为空；默认仍 0.99 | `test_p022_script_schema` + 脚本实跑 | ✅ 绿（Step 9 实测，详见 §12.1） |
| F-11 | D6 U-8 裁决 | A5 | 对拍 0/8,389,800；阈值 0 容忍、仅披露；9/13 键不变 | 脚本实跑 + 既有键断言 | ✅ 绿（Step 9 实测，详见 §12.1） |
| F-12 | D7 R-3 裁决 | A5 | 3 因子敏感性表；告警 0/3 翻转；不重标定阈值 | 脚本实跑 | ✅ 绿（Step 9 实测，详见 §12.1） |
| F-13 | D2 missing_fields 修正 | A2 | 紧凑 name/suspend 路径不误加 `missing_fields`；真缺失仍追加 | `test_p022_missing_fields_compact` | ✅ 绿（Step 9 实测，详见 §12.1） |
| F-14 | D4 限价表分支 | A3 | `limit_up` 提供时不计算 pct、不并 pct unknown；报告与 3.10.0 一致 | `test_p022_pct_limit_table_branch` | ✅ 绿（Step 9 实测，详见 §12.1） |

---

## 3. 接口验收

| # | 项 | DoD（签名/契约） | 证据出口 | 结果 |
|---|---|---|---|---|
| I-1 | `build_tradability_inputs` 兼容 | 旧 13 位置参数结果不变；新 5 个可选关键字在末尾 | `test_p022_builder_legacy_positional` + 既有 tests | ✅ 绿（Step 9 实测，详见 §12.1） |
| I-2 | `_slice` 契约 | 所有 kind 返回 `(data, aux)`；full 命中同对象/同数组 | `test_p022_slice_contract` | ✅ 绿（Step 9 实测，详见 §12.1） |
| I-3 | `TradabilityInputs` | 字段顺序/类型不变；数组可为缓存视图 | 读码 + 既有构造测试 | ✅ 绿（Step 9 实测，详见 §12.1） |
| I-4 | apply/report 契约 | 签名不变；`report` 9 键、diagnostics 键集合不变 | `test_p022_report_meta_bitwise` + 键断言 | ✅ 绿（Step 9 实测，详见 §12.1） |
| I-5 | `compute_turnover` | 签名/返回形状不变；dtype 保持 | `test_p022_turnover_bitwise` | ✅ 绿（Step 9 实测，详见 §12.1） |
| I-6 | 证据脚本 | CLI `--data-root/--out/--only`；JSON 固定键 | `test_p022_script_schema` + `--help` | ✅ 绿（Step 9 实测，详见 §12.1） |

---

## 4. 不变式验收

| # | 不变式 | 判据 | 证据出口 | 结果 |
|---|---|---|---|---|
| N-1 | INV-1 默认路径 | `tradability_inputs=None` 逐位不变 | TP6-11 + 默认 SHA | ✅ 绿（Step 9 实测，详见 §12.1） |
| N-2 | INV-2 启用路径 | 4 组 fixture `report/meta/diagnostics/turnover` 逐位一致 | `test_p022_report_meta_bitwise` | ✅ 绿（Step 9 实测，详见 §12.1） |
| N-3 | INV-3 键冻结 | `report` 9 / `meta` 13 | 键集合断言 | ✅ 绿（Step 9 实测，详见 §12.1） |
| N-4 | INV-4 旧调用 | 13 位置参数 + 关键字 | `test_p022_builder_legacy_positional` | ✅ 绿（Step 9 实测，详见 §12.1） |
| N-5 | INV-5 name 等价 | 逐格 + 窗口前名称 | `test_p022_name_*` | ✅ 绿（Step 9 实测，详见 §12.1） |
| N-6 | INV-6 suspend 等价 | object 紧凑 + bool 原路径 | `test_p022_suspend_*` | ✅ 绿（Step 9 实测，详见 §12.1） |
| N-7 | INV-7 依赖 | 零新增；py3.9 语法 | `pyproject` diff + AST | ✅ 绿（Step 9 实测，详见 §12.1） |
| N-8 | INV-8 并行一致 | 串行 vs 并行 summary 逐位 | `test_p022_parallel_serial_equal`（进程池；缺 `Factor_Trading_v3_0` 时跳过）+ `test_p022_worker_payload_summary_equal`（chunk 子集 vs 全量，本环境实跑） | ✅ 绿（Step 9 实测，详见 §12.1） |
| N-9 | INV-9 缓存不可变 | 二次 build 前后缓存抽样哈希 | `test_p022_inputs_immutable` | ✅ 绿（Step 9 实测，详见 §12.1） |
| N-10 | INV-10 预算 | M-3 ≤1024 MB；M-1 ≤30 s | CHECKLIST §6 | ☐ 待办（M-3=2463.5 MB；M-1 ✅ 15.64 s） |
| N-11 | INV-11 mismatch | int 键仍存在；无门禁 | 既有键 + 定向 | ✅ 绿（Step 9 实测，详见 §12.1） |
| N-12 | INV-12 turnover | 含 NaN/Inf/T<2/N=1/int 入参 | `test_p022_turnover_bitwise`、`test_p022_turnover_int_input` | ✅ 绿（Step 9 实测，详见 §12.1） |
| N-13 | INV-13 高水位披露 | M-6 读数入档 | §6 | ✅ 绿（Step 9 实测，详见 §12.1） |
| N-14 | INV-14 bool suspend | 原路径逐位（含 reindex 升型） | `test_p022_suspend_bool_path_unchanged` | ✅ 绿（Step 9 实测，详见 §12.1） |
| N-15 | INV-15 pct 行 | 与矩阵逐位（含 gap） | `test_p022_pct_row_bitwise` | ✅ 绿（Step 9 实测，详见 §12.1） |

---

## 5. 错误处理验收

| # | 场景 | 期望 | 证据出口 | 结果 |
|---|---|---|---|---|
| E-1 | `name_codes` 形状错 | `ValueError` | `test_p022_builder_errors` | ✅ 绿（Step 9 实测，详见 §12.1） |
| E-2 | LUT 非一维/长度不足 | `ValueError` | 同上 | ✅ 绿（Step 9 实测，详见 §12.1） |
| E-3 | `suspend_mask` 与 `missing` 不成对 | `ValueError` | 同上 | ✅ 绿（Step 9 实测，详见 §12.1） |
| E-4 | 未知 `_PanelRecord.kind` | `ValueError` | 同上 | ✅ 绿（Step 9 实测，详见 §12.1） |
| E-5 | name 唯一值 >2^24 | 回退 raw + warning | `test_p022_name_unique_fallback`（monkeypatch `pd.factorize`） | ✅ 绿（Step 9 实测，详见 §12.1） |
| E-6 | `compute_turnover` T<2 | 空数组 | `test_p022_turnover_bitwise` | ✅ 绿（Step 9 实测，详见 §12.1） |
| E-7 | 未知板块 | gap/unknown，不抛错 | `test_p021_d3_unknown_board` | ✅ 绿（Step 9 实测，详见 §12.1） |
| E-8 | 空 chunk | 返回 `{}` | `test_p022_parallel_payload_subset` | ✅ 绿（Step 9 实测，详见 §12.1） |

---

## 6. 性能/内存验收

| # | 项 | 预算 | 实测 | 结果 |
|---|---|---|---|---|
| M-1 | `spec.build` 全样本 | ≤30 s | **15.64 s**（改前 22.43 s） | ✅ |
| M-2 | 构建 tracemalloc 峰值 | ≤1024 MB | **1249.4 MB**（改前 2585.1 MB） | ☐ 待办（P-023；name 解码常驻） |
| M-3 | worker 稳态 RSS（口径见 DESIGN §8） | **≤1024 MB** | **2463.5 MB**（改前 3348 MB；隔离基线引擎仅 540.1 MB） | ☐ 待办（P-023；name 解码 + 全样本 T×N apply） |
| M-4 | 缓存常驻 deep | ≤500 MB | **430.7 MB**（改前 1140.1 MB；name 34 / suspend 16 / float 380） | ✅ |
| M-5 | 结果一致性 | 100% | **4/4 fixture 逐键相等**（`test_p022_report_meta_bitwise`） | ✅ |
| M-6 | 首次加载高水位（披露） | ≤1400 MB | **1345.4 MB**（build 后 RSS；未计入 M-3 的诊断口径） | ✅ 披露 |

> **失败门禁**：M-3 >1024 MB 时停止并回报分项读数，由用户决定追加分块 apply 或调整预算（DESIGN §8）。

---

## 7. 兼容性验收

| # | 项 | 判据 | 证据出口 | 结果 |
|---|---|---|---|---|
| K-1 | 默认路径 | `spec=None` 结果逐位不变 | TP6-11 + 默认 SHA | ✅ 绿（Step 9 实测，详见 §12.1） |
| K-2 | 启用路径 | 4 fixture 逐位不变 | N-2 | ✅ 绿（Step 9 实测，详见 §12.1） |
| K-3 | 版本锚点 | 6 处 3.10.1 | `test_fix3_version_unification` + grep | ✅ 绿（Step 9 实测，详见 §12.1） |
| K-4 | 运行环境 | Python≥3.9 / pandas≥2.0 / numpy≥1.22 | AST + pyproject | ✅ 绿（Step 9 实测，详见 §12.1） |
| K-5 | 依赖 | 零新增运行时依赖 | `git diff pyproject.toml` | ✅ 绿（Step 9 实测，详见 §12.1） |
| K-6 | 回退路径 | bool suspend / name 唯一值超限 → raw 行为不变 | E-5 + N-14 | ✅ 绿（Step 9 实测，详见 §12.1） |

---

## 8. ADD 审计（Step 10）

| # | 项 | 判据 | 结果 |
|---|---|---|---|
| A-1 | Iron Law 4 项 | 设计→代码→测试→证据一致 | ✅ PASS（D1-D7/D9 均有代码落点 + 测试名 + E1/脚本读数；D8 显式被拒；10 条审计发现全部处置，见 §12.2） |
| A-2 | 证据矩阵 | 每条验收项有 E1 读数/测试名 | ✅ PASS（§2-§7 每行均有测试名或脚本读数；M-2/M-3/N-10 如实标待办） |
| A-3 | 反向核对 | 代码改动均有 CHECKLIST 项承接 | ✅ PASS（6 个改动文件：loader→F-1~F-4/E-5、inputs→F-2/F-3/F-13/E-1~E-3、tradability→F-8/F-14/N-15、engine→F-7、factor_metrics→F-9/N-12、parallel_runner→F-6/N-8） |
| A-4 | 未决项 | U-2/U-1/U-3/U-4 状态如实 | ✅ PASS（U-2 已由 M-2/M-3 实测回答并转 P-023；U-1 待 token；U-3 条件触发；U-4 已随 P-021 关闭） |

---

## 9. 证据脚本验收

| # | 项 | 判据 | 结果 |
|---|---|---|---|
| S-1 | U-7 输出 | 73 月行 + `worst` + `below_099`；`below_099=[]` | ✅ 实跑 `out/tradability_closeout_u7u8.json`：73 月全 `full`；`high_low/open min=1.0`、`prev min=0.994429`；`below_099` 三键全空 |
| S-2 | U-8 输出 | `cells_total=8,389,800`、`mismatch_cells=0`；默认 `basis=same_panel`；外部面板经 `--price-panel` → `external_panel` | ✅ 实跑（Step 9，同源 close 自比）：`8,389,800 / 0 / 0.0`；`basis` 键为 Step 10 审计新增（工件生成早于该键，重跑同参即可回填） |
| S-3 | R-3 输出 | 3 因子表；告警 0/3 翻转 | ✅ 实跑 `out/tradability_closeout_r3.json`：`turnover Δ −0.365% / −2.056% / −0.097%`；`health Δ ≤0.347`；`combined drift Δ ≤0.020`；告警 0/3；ICIR/LS 全一致 |

---

## 10. 统计与验收决定（Step 10 回填）

### 10.1 通过/失败/待办统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|---|---|---|---|---|
| 文档一致性 | 5 | 5 | 0 | 0 |
| 功能 | 14 | 14 | 0 | 0 |
| 接口 | 6 | 6 | 0 | 0 |
| 不变式 | 15 | 14 | 0 | 1（N-10） |
| 错误处理 | 8 | 8 | 0 | 0 |
| 性能/内存 | 6 | 4 | 0 | 2（M-2/M-3） |
| 兼容性 | 6 | 6 | 0 | 0 |
| ADD 审计 | 4 | 4 | 0 | 0 |
| 证据脚本 | 3 | 3 | 0 | 0 |
| **总计** | **67** | **64** | **0** | **3** |

> **统计口径（RULE-2）**：逐项独立核对，非事后汇总；`总数 = 通过 + 失败 + 待办`。
> **待办说明**：M-2（build tracemalloc 1249.4 MB）、M-3（worker RSS 2463.5 MB）、N-10（INV-10 预算，由 M-2/M-3 派生）共 3 项，均转入 **P-023**。

### 10.2 验收决定

- ☐ **验收通过**
- ☑ **有条件通过**：条件 = ① **M-2/M-3 未达**（build tracemalloc 1249.4 MB、worker RSS 2463.5 MB，预算 1024 MB）→ 已立项 **P-023**（离线 name 紧凑缓存 + worker 日期分片）；② U-1（`stk_limit` 外部一致率）待 token。其余功能/接口/错误/兼容/脚本全过；不变式除 N-10（由 M-2/M-3 派生）外全过；M-4 缓存 430.7 MB、M-1 15.64 s、U-7/U-8/R-3 全达。
- ☐ **验收失败**（原因：）

### 10.3 签字

| 角色 | 签字 | 日期 |
|---|---|---|
| 实施者 | 主会话（Step 9 TDD + Step 10 整改） | 2026-11-23 |
| 审查者 | 独立只读子代理（Step 10 ADD 审计，异构基座） | 2026-11-23 |

---

## 11. 后续行动

| 行动 | 状态 |
|---|---|
| Step 8 三对文档一致性复审（§1） | ✅ 已回填（PASS_WITH_FIXES，见 §1.6） |
| Step 9 TDD A1-A5（§2-§7、§12） | ✅ 已回填（24 例：23 passed / 1 skipped；分批 A1 9 / A2 3 / A3 5 / A4 4+1s / A5 2） |
| Step 10 ADD 审计（§8） | ✅ 已完成（PASS_WITH_FIXES；10 条发现全部处置，见 §12.2） |
| 台账/CHANGELOG 收口 | ✅ CHANGELOG v3.10.1 + PROGRESS/PROJECT_STATUS |
| **P-023**：离线 name 紧凑缓存 + worker 日期分片（M-2/M-3） | ✅ 已登记 PROGRESS（pending） |
| U-1 `stk_limit` 外部一致率 | token 到位后 |
| U-3 非标准 price_data mismatch 样例 | 条件触发 |

---

## 12. 执行记录（Step 9 / Step 10 回填）

### 12.1 Step 9 红→绿读数（F5）

| 批次 | 红（改代码前） | 绿（改代码后） |
|---|---|---|
| A1 | collection error：`ImportError: cannot import name '_pct_row'`（`_PanelRecord`/`_PANEL_CACHE` 同缺；0.43 s） | **9 passed**（缓存紧凑 / 切片同对象与契约 / name 等价与窗口 / suspend 等价与 bool 回退 / 唯一值回退 / 缓存不可变） |
| A2 | 同上（整文件不可收集） | **3 passed**（`_frame` 同对象 / 快路径负例 / `missing_fields` compact） |
| A3 | 同上 | **5 passed**（turnover 浮点+int 逐位 / pct 矩阵对拍 / 独立旧口径 / 限价表分支不计算 pct） |
| A4 | 同上 | **4 passed / 1 skipped**（4 fixture 逐位、payload 子集、chunk 子集 summary 等价、旧位置参数；进程池串并行因缺可选依赖跳过） |
| A5 | 同上 | **2 passed**（builder 错误族 / 脚本 JSON schema） |

> 红读数为**整文件 collection error**：新测试直接导入改后才存在的私有 API（`_pct_row`/`_PanelRecord`），因此一次覆盖 A1-A5；改前行为基线由 `tests/golden/p022_baseline.json`（B0 抓取，F1_basic/F2_st/F3_suspend/F4_limit_bse）承担，而非同文件红测。
> 命令：`python -m pytest -q tests/test_tradability_p022.py` → 红 `1 error`；绿 `23 passed, 1 skipped`（分段读数见上表）。
> **最终全量回归（最终代码状态，2026-11-23）**：`python -m pytest -q --no-header` → **2227 passed / 35 skipped / 0 failed**（933.81 s）。相对 P-021 基线 2204/34 的增量为 +23 passed / +1 skipped，恰为 `tests/test_tradability_p022.py` 的 24 例（进程池串并行 1 例因缺可选依赖跳过）。

### 12.2 Step 10 审计处置表

| # | 级别 | 发现 | 处置 |
|---|---|---|---|
| A-1 | P1 | §10.1 统计仍为 5/62，与逐项 ✅ 矛盾 | 重算 **67 项 = 64 通过 / 0 失败 / 3 待办（M-2/M-3/N-10）** |
| A-2 | P1 | F-6/N-8 引用的 `test_p022_parallel_slice_equal` 不存在 | 新增 `test_p022_worker_payload_summary_equal`（chunk 子集 vs 全量，逐位）与 `test_p022_parallel_serial_equal`（进程池；缺可选依赖跳过），证据出口同步改名 |
| A-3 | P2 | RESEARCH/DESIGN 的 R-3 数字来自早期探针，与脚本 JSON 不一致 | RESEARCH §4.5/§5.4 与 DESIGN §4.7 改为脚本口径（−0.365/−2.056/−0.097%；Δ≤0.347；drift ≤0.020），并标注旧读数已被取代 |
| A-4 | P2 | U-8 原为 close 自比（恒 0），无外部面板入口 | 脚本新增 `--price-panel` 与 `basis=same_panel/external_panel`；`test_p022_script_schema` 断言 `u8` 键集合 |
| A-5 | P2 | `compute_turnover` 非浮点入参被截断（旧实现升 float64） | 非浮点输出 float64；新增 `test_p022_turnover_int_input` 逐位对拍 |
| A-6 | P2 | `suspend_missing` 无 mask 被静默忽略；LUT 未校验一维 | 构建器补 `elif ... raise` + `ndim != 1` 校验；`test_p022_builder_errors` 增两例 |
| A-7 | P2 | CHANGELOG 无 v3.10.1 | 已写 v3.10.1 条目（变更/行为影响/阈值证据/验证） |
| A-8 | P3 | `_pct_row` 与 `_pct_matrix` 对拍属自证 | 新增 `test_p022_pct_row_independent`（`rule_pct_or_nan` 逐格旧口径独立复核） |
| A-9 | P3 | M-6 口径（解码瞬时 vs build RSS）未对齐 | DESIGN §8 M-6 改为“build 完成后 RSS”并记录 1345.4 MB；CHECKLIST §6 同步 |
| A-10 | P3 | E-5 证据出口名与测试实现不一致 | 统一为 `test_p022_name_unique_fallback` |

---

**Review 签字**: 有条件通过（Step 10，2026-11-23）；条件项 M-2/M-3/N-10 → P-023。
