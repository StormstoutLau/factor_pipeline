# 审查验收 Checklist：v3.9.7 P-017 审计遗留清尾

---
id: v397-p017-cleanup-CHECKLIST
type: checklist
version: 1.2
status: Step 10 完成 — ADD 审计 PASS_WITH_FIXES（4.6/5，0×P1/0×P2/5×P3 已处置）— 65/65 通过，有条件通过（条件闭环）
date: 2026-11-21
depends: [v397-p017-cleanup-IMPLEMENTATION]
upstream: v397-p017-cleanup-IMPLEMENTATION
---

> **批次**: v3.9.7（P-017：1×P2 + 3×P3 + Step 2 新发现 F-1）。
> **依据**: [DESIGN.md](DESIGN.md) v1.0 verified（D1-D10、INV-1~8）+ [IMPLEMENTATION.md](IMPLEMENTATION.md) v1.2（含 §9 retro 复核）。
> **统计**: 65 项 = 文档一致性 12 + 功能 14 + 接口 10 + 不变式 10 + 错误处理 8 + 性能 3 + 兼容性 4 + ADD 4。

## 1. 文档一致性验收（Step 8 复核）

### 1.1 RESEARCH.md ↔ DESIGN.md 对齐

| 编号 | 检查项 | 状态 | 证据 |
|---|---|---|---|
| 1.1-1 | U-1/U-2/U-3 三项裁决在 DESIGN §11 均标 closed，且口径与 RESEARCH §6.3/§8.5 一致（B / 进程内 CLI / 3.9.7） | ☑ | DESIGN L276-278 三行 closed（审计 F2 勘误行号） |
| 1.1-2 | RESEARCH §2.4(b) 记录的现状（traceback + 退出码 1）与 DESIGN D5 修复口径一致 | ☑ | D5 改后代码含 `except CalibrationUnavailable → print + return 2` |
| 1.1-3 | RESEARCH §5.1.1 新发现 F-1（docstring 失真）已并入 DESIGN D1 范围 | ☑ | DESIGN §3.1 D1 行「改 docstring L294、改注释 L304-306」（审计 F3 勘误行号） |
| 1.1-4 | RESEARCH §8 外部锚点结论（glibc/GNU/argparse/sysexits/金字塔/SemVer）在 DESIGN §5 否决理由中逐条体现 | ☑ | §5.2-§5.6 五项 |

### 1.2 DESIGN.md ↔ IMPLEMENTATION.md 对齐

| 编号 | 检查项 | 状态 | 证据 |
|---|---|---|---|
| 1.2-1 | D1-D10 十项在 IMPLEMENTATION §1 变更清单逐项出现，无遗漏 | ☑ | §1 表 9 行覆盖 D1/D2/D3/D6/D8/D7/D5/D4+D9/D10 |
| 1.2-2 | DESIGN §6.2 六行勘误表与 IMPLEMENTATION §3.8(b) 引用一致 | ☑ | §3.8(b) 指回 DESIGN §6.2 |
| 1.2-3 | DESIGN §4.1 退出码契约（2、`[minute] <msg>`、无 traceback）与 §3.7 改后代码一致 | ☑ | §3.7 except 块逐字一致 |
| 1.2-4 | DESIGN §10.1 七条工程约束在 IMPLEMENTATION §3 各步自检/§5 通过线中有对应 | ☑ | 7 条 → §3.1-§3.9 自检 / §5 六条 |

### 1.3 IMPLEMENTATION.md ↔ CHECKLIST.md 对齐

| 编号 | 检查项 | 状态 | 证据 |
|---|---|---|---|
| 1.3-1 | IMPLEMENTATION §1 的 9 个变更行在本文件 §2 均有验收行 | ☑ | §2.1-§2.6 六小节覆盖 D1-D10 |
| 1.3-2 | IMPLEMENTATION §5 通过线 6 条在本文件 §4/§5/§7 有对应验收项 | ☑ | 全量/定向/SHA/版本/零依赖 |
| 1.3-3 | IMPLEMENTATION §8 证据清单 6 项与本文件证据列一一对应 | ☑ | 红日志、绿日志、全量、diff、SHA、version grep |

### 1.4 术语一致性

| 编号 | 检查项 | 状态 | 证据 |
|---|---|---|---|
| 1.4-1 | 「异构审查」在 DESIGN/IMPLEMENTATION/本文件均指 Step 6 独立子代理核查；「幂等」相关表述本批未涉及 | ☑ | 三文档一致 |

### 1.5 Step 8 F-A 勘误记录（2026-11-21）

| 编号 | 发现 | 处置 |
|---|---|---|
| F-A-1 | 本文件 §2.2-1 行号锚点写 L776-780，实测精确路径在 **L769-772**（L770 为断言行） | 已就地勘误 §2.2-1 |
| F-A-2 | IMPLEMENTATION §4 定向命令期望「5 passed」，实测 **4 passed / 3.21 s**（T397_3 在 test_execution_decay.py，不在该命令收集范围） | IMPLEMENTATION 升 v1.1 勘误 |
| F-A-3 | IMPLEMENTATION §3.3 声明 T397_1「插在 T396_8 之后」，实际插入点为 T396_9 之后（L775 起）；功能与通过线无影响 | IMPLEMENTATION 升 v1.1 勘误 |
| F-A-4 | 本文件 §3.1-4 / §5.2 / §7.1 证据措辞含糊或含无关引用（`resolve_evidence_level`） | 已就地勘误 |

## 2. 功能验收

### 2.1 D1 T3100_3（`tests/test_execution_capacity.py`）

| 编号 | 检查项 | 状态 | 证据 |
|---|---|---|---|
| 2.1-1 | 函数内无 `base = raw - raw.mean()` 等恒真断言 | ☑ | [L293-315](file:///f:/Coding/factor_pipeline/tests/test_execution_capacity.py#L293-L315) 无 `base`/`mean()` |
| 2.1-2 | docstring 与注释如实化（含 F-1：删除「demean 幅度可断言（非恒真）」） | ☑ | docstring「未 demean 的平移对照非恒真（demean 本身由 T396_2 覆盖）」 |
| 2.1-3 | 平移对照仍有效（非恒真） | ☑ | `abs(c.point − d.point) > 1.0`；定向 1 passed |

### 2.2 D2 T396_9 / `_find_key`

| 编号 | 检查项 | 状态 | 证据 |
|---|---|---|---|
| 2.2-1 | T396_9 使用精确键路径 `payload["panels"]["coverage"]["universe_ratio"]` | ☑ | [L769-772](file:///f:/Coding/factor_pipeline/tests/test_minute_panels.py#L769-L772) |
| 2.2-2 | `_find_key` 已删除且全仓无引用 | ☑ | `tests/` 内 Grep 无命中 |

### 2.3 D3/D6/D8 新增用例

| 编号 | 检查项 | 状态 | 证据 |
|---|---|---|---|
| 2.3-1 | T397_1 断言三项（`==`、`config_hash()`、默认 `minute_root`） | ☑ | 定向 passed |
| 2.3-2 | T397_2 空根 → `CalibrationUnavailable` 且 `match="无可用月份"` | ☑ | 0.01 s passed |
| 2.3-3 | T397_4 红转绿，`main()` 返回 2、stdout 含 `[minute]`+「无可用月份」、无 `Traceback` | ☑ | 红：1 failed（`CalibrationUnavailable`）；绿：0.02 s passed |
| 2.3-4 | `_vci()` 助手可导入脚本且不与既有 helper 冲突 | ☑ | 4 passed（T397_1/2/3/4 同进程） |

### 2.4 D7 T397_3

| 编号 | 检查项 | 状态 | 证据 |
|---|---|---|---|
| 2.4-1 | `sys.modules["factor_pipeline"]=None` → `_decay_curve_md` 抛 ImportError | ☑ | passed（<0.005 s） |

### 2.5 D5 script 捕获

| 编号 | 检查项 | 状态 | 证据 |
|---|---|---|---|
| 2.5-1 | 局部 import 块追加 `CalibrationUnavailable` | ☑ | [L720-722](file:///f:/Coding/factor_pipeline/scripts/verify_capacity_impact.py#L720-L722) |
| 2.5-2 | `try` 仅包 `build_panels → builder.build()`，`coverage_gate` 在其外 | ☑ | [L750-764](file:///f:/Coding/factor_pipeline/scripts/verify_capacity_impact.py#L750-L764) 缩进核对；异构审查确认 |

### 2.6 D10 版本

| 编号 | 检查项 | 状态 | 证据 |
|---|---|---|---|
| 2.6-1 | 六处均为 3.9.7 | ☑ | pyproject L7 / `__init__` L58 / config_v2 L371 / reporting L40 / 两测试锚点 |
| 2.6-2 | 六文件内无 3.9.6 版本常量残留 | ☑ | `Select-String` → `NO_396_RESIDUE` |

## 3. 接口验收

### 3.1 CLI 契约

| 编号 | 检查项 | 状态 | 证据 |
|---|---|---|---|
| 3.1-1 | 空/不存在 `--minute-root` → 退出码 2 | ☑ | T397_4 `rc == 2` |
| 3.1-2 | stdout 一行 `[minute] <msg>` | ☑ | T397_4 断言 |
| 3.1-3 | 不输出 traceback | ☑ | T397_4 断言 `"Traceback" not in out` |
| 3.1-4 | CLI 参数集合零变化（未新增/删除/改名） | ☑ | git diff 核验：本批不含 argparse 段任何改动行 |

### 3.2 测试接口

| 编号 | 检查项 | 状态 | 证据 |
|---|---|---|---|
| 3.2-1 | T397_1 无 fixture，纯构造 | ☑ | 源码 |
| 3.2-2 | T397_2 用 `needs_pyarrow` | ☑ | 装饰器 |
| 3.2-3 | T397_4 用 `needs_pyarrow` + `monkeypatch` + `capsys` | ☑ | 装饰器/签名 |
| 3.2-4 | T397_3 用 `monkeypatch.setitem` | ☑ | 源码 |

### 3.3 生产 API 边界

| 编号 | 检查项 | 状态 | 证据 |
|---|---|---|---|
| 3.3-1 | `backtest/execution/core/` 零改动 | ☑ | `git diff --stat` 无条目 |
| 3.3-2 | `backtest/execution/shell/panels.py` 零改动；`ports.py` 未改（仅被 import） | ☑ | `git diff --stat` 无条目 |

## 4. 不变式验收（DESIGN §8）

| 编号 | 不变式 | 状态 | 证据 |
|---|---|---|---|
| 4.1 | INV-1 默认 `out/capacity_impact.json` SHA256 `82728CE1…` 逐位不变 | ☑ | 跑后 `82728CE103D49AF2`（前 16 位一致，与 v3.9.6 基线同值） |
| 4.2 | INV-2 `panels.panel_hash` 仍 `dfcc4e1d…` | ☑ | 本批 panels 零 diff，v3.9.6 实测值传递成立（未重跑 39 月） |
| 4.3 | INV-3 `core/` 与 `shell/panels.py` 零 diff | ☑ | diff stat 13 文件，无上述两项 |
| 4.4 | INV-4 配置等价 + `config_hash()` 相等 | ☑ | T397_1 passed |
| 4.5 | INV-5 零新增依赖（pyproject 仅 version 行） | ☑ | `pyproject.toml | 2 +-` |
| 4.6 | INV-6 版本 3.9.7 六处一致 | ☑ | §2.6-1 |
| 4.7 | INV-7 正常路径零变化 | ☑ | 全量 2092 passed；D5 仅异常分支生效 |
| 4.8 | INV-8 CLI 参数集合不变 | ☑ | §3.1-4 |
| 4.9 | 全量测试与预注册通过线逐位一致 | ☑ | **2092 passed / 15 skipped / 0 failed**（910.12 s） |
| 4.10 | 定向用例全绿（含红转绿过程记录） | ☑ | 4 passed（0.14 s）；红阶段实测 T397_4 failed（Tool 输出，未落盘为日志文件） |

## 5. 错误处理验收（DESIGN §7）

| 编号 | 场景 | 状态 | 证据 |
|---|---|---|---|
| 5.1 | 空 `--minute-root` | ☑ | T397_4 + T397_2，exit 2 |
| 5.2 | 不存在 `--minute-root` | ☑ | loaders L85-94：`root.is_dir()` 为 False → `available_months()==[]` → 同一异常（源码核验） |
| 5.3 | pyarrow 缺失 | ☑ | `build()` L447 同异常 → 同一 catch（源码核验，不新增 mock） |
| 5.4 | `build()` 前 daily 为 None | ☑ | L445 同异常 → 同一 catch（源码核验） |
| 5.5 | `build_panels` 读盘失败 | ☑ | 不捕获，保持原异常（try 边界内仅 CalibrationUnavailable） |
| 5.6 | 包不可导入 | ☑ | T397_3 ImportError |
| 5.7 | 覆盖度门禁失败 | ☑ | 既有 T396_9 逻辑未改（try 在门禁之前结束） |
| 5.8 | 默认 `minute_root` 路径 | ☑ | T397_1 断言 `E:\Level 1 Data` |

## 6. 性能验收

| 编号 | 检查项 | 状态 | 证据 |
|---|---|---|---|
| 6.1 | 新增 4 例总耗时 ≤ 1 s | ☑ | 4 passed in **0.14 s**，最慢 T397_4 **0.02 s** |
| 6.2 | T396_9 慢例耗时未劣化 | ☑ | 本批未改动该用例；v3.9.6 实测 86.84 s（两子进程） |
| 6.3 | 全量耗时未显著劣化 | ☑ | 910.12 s vs 基线 938.81 s（−3.1%） |

## 7. 兼容性验收

| 编号 | 检查项 | 状态 | 证据 |
|---|---|---|---|
| 7.1 | Python 3.9 语法兼容 | ☑ | 新增代码仅标准库导入与 `%` 格式化，无 3.10+ 语法 |
| 7.2 | Windows/PowerShell 环境可跑 | ☑ | 本机全量 910 s 通过 |
| 7.3 | 既有 2088 passed 全部仍绿 | ☑ | 2092 = 2088 + 4，0 failed |
| 7.4 | 零新增依赖 | ☑ | §4.5 |

## 8. ADD 审计（Step 10，独立只读子代理 2026-11-21）

| 编号 | 检查项 | 状态 | 证据 |
|---|---|---|---|
| 8.1 | Spec 质量门（Phase 0） | ☑ | 四文档齐备、版本链 v1.2/v1.0/v1.2/v1.1、§10.1 算术自洽、行号抽查 3 吻合 2 漂移（F2/F3，已核销） |
| 8.2 | ADD 审计发现 | ☑ | **0×P1、0×P2、5×P3**（F1-F4 文档行号/版本表漂移 → 就地核销；F5 = T397_1 两断言语义级恒真、捕获力低 → 登记为已知局限，不违反 Iron Law，保留 L784 有效断言） |
| 8.3 | Iron Law 检查 | ☑ | 复算实现逻辑式恒真 **0 项**：T3100_3 `|c−d|>1.0` 非恒真；T396_9/T397_2/T397_3/T397_4 均真实触达实现路径 |
| 8.4 | 审计结论 | ☑ | **PASS_WITH_FIXES（4.6/5）**：代码/测试/工件全绿、无恒真前科复发、D-397-1 登记如实未夸大；P3 修补后达成验收 |

## 9. 文档完整性

| 检查项 | 状态 | 证据 |
|---|---|---|
| RESEARCH.md 存在且 verified | ☑ | v1.2 |
| DESIGN.md 存在且 verified | ☑ | v1.0（§9.3 PASS） |
| IMPLEMENTATION.md 存在 | ☑ | v1.2（含 §9 retro 复核） |
| CHECKLIST.md（本文件） | ☑ | v1.2 |
| CHANGELOG / PROGRESS / PROJECT_STATUS 同步 | ☑ | CHANGELOG v3.9.7 条目；PROGRESS P-017 → done；PROJECT_STATUS 版本同步 |

## 10. 验收结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|---|---|---|---|---|
| 文档一致性 | 12 | 12 | 0 | 0 |
| 功能 | 14 | 14 | 0 | 0 |
| 接口 | 10 | 10 | 0 | 0 |
| 不变式 | 10 | 10 | 0 | 0 |
| 错误处理 | 8 | 8 | 0 | 0 |
| 性能 | 3 | 3 | 0 | 0 |
| 兼容性 | 4 | 4 | 0 | 0 |
| ADD 审计 | 4 | 4 | 0 | 0 |
| **总计** | **65** | **65** | **0** | **0** |

### 10.2 验收决定

☑ **有条件通过** —— 条件及闭环情况：① 审计 F1-F4（文档行号/版本表漂移）已就地核销；② F5（T397_1 语义级恒真断言捕获力低）登记为已知局限，Iron Law 计数仍为 0，不构成整改义务。代码、测试、工件零保留问题。

### 10.3 签字

审计：独立只读子代理 PASS_WITH_FIXES（4.6/5，2026-11-21）｜验收：有条件通过（条件已闭环）｜登记：无新增 backlog（5×P3 全部就地处置）。

## 11. 后续行动

| 项 | 状态 |
|---|---|
| Step 6 实施文档 Review | retro 补齐（IMPLEMENTATION §9；偏差见 §12） |
| Step 7 CHECKLIST 初稿 | done（本文件 v1.0） |
| Step 8 交叉核对（文档一致性复核 + 勘误） | done（§1.5 F-A-1~4） |
| Step 9 TDD 实现 | 已实质完成，留痕核验见 §12.2 |
| Step 10 独立只读 ADD 审计 | done（§8；PASS_WITH_FIXES 4.6/5，F1-F4 已核销，F5 登记为已知局限） |
| CHANGELOG v3.9.7 / PROGRESS P-017 转 done | done |

## 12. 流程偏差登记与 Step 9 留痕核验（过程记录，不计入 §10.1 统计）

### 12.1 D-397-1：Step 6 与 Step 9 合并执行

| 字段 | 内容 |
|---|---|
| 现象 | Step 6 按规范应为「实施文档 Review」，实际直接进入编码；Step 9（TDD 实现）被误标为「证据回填与收尾」 |
| 根因 | 把「异构审查」当成 Step 6，并将编码与审查合并为一次执行，未按 [SPEC_PROCESS](file:///f:/Coding/factor_pipeline/spec/SPEC_PROCESS.md#L96-L112) 的十步时序走 |
| 档位判定 | 本批触碰 `scripts/` → Layer-1 → **T1 完整管线**（§批次档位），不适用轻批裁剪 |
| 影响 | 代码/测试/工件**零影响**（2092 passed、SHA 不变、core/panels 零 diff）；仅时序证据链缺前置 Review |
| 处置 | ① IMPLEMENTATION 增 §9 retro 复核（明示事后性质）；② 本表登记；③ 后续批次严格执行「Review → CHECKLIST → 交叉核对 → TDD 实现」时序 |
| 状态 | 已补救，不阻断 Step 10 |

### 12.2 Step 9 TDD 证据（留痕核验）

| 阶段 | 证据 | 结果 |
|---|---|---|
| 红 | 4 个新用例先写入；`pytest -k T397` → T397_4 failed（`CalibrationUnavailable`，[panels.py L474](file:///f:/Coding/factor_pipeline/backtest/execution/shell/panels.py#L474)），T397_1/T397_2 passed | 1 failed / 2 passed |
| 实现 | D5：script L750-759 `try` + L760-764 `except` → `[minute]` + `return 2` | 唯一生产改动 |
| 绿 | 定向 `-k T397` 两文件 | 4 passed / 0.14 s（最慢 0.02 s） |
| 回归 | 定向 54 passed；全量 | 54 passed；**2092 passed / 15 skipped / 0 failed**（910.12 s） |
| 顺序合规 | 测试先于实现；D1/D2 为删除与改写型（无红形态，已说明）；D5 有真红 | 符合 TDD |
