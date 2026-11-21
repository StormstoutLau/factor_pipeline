# 设计文档：v3.9.7 P-017 审计遗留清尾（测试有效性与文档一致性）

---
id: v397-p017-cleanup-DESIGN
type: design
version: 1.0
status: verified（Step 4 复审完成：9.1 十项声明全部 ✅，门禁 a-d 通过）
date: 2026-11-21
depends: [v397-p017-cleanup-RESEARCH]
upstream: v397-p017-cleanup-RESEARCH
---

> **Feature**: 关闭 P-017（1×P2 + 3×P3），并顺带修复 Step 2 双 pass 新发现 F-1。
> **输入**: [RESEARCH.md](RESEARCH.md) **v1.2 verified**（U-1=B / U-2=进程内 CLI 测试 / U-3=3.9.7 已裁决）。
> **包版本**: **3.9.7**。**生产改动仅 1 处**（script 捕获 `CalibrationUnavailable`），`core/` 与 `shell/panels.py` 零改动。

## 1. 设计目标

1. **消除无判别力断言**：T3100_3 删除恒真段与失真 docstring/注释，保留真正的平移敏感性对照。
2. **消除脆弱断言**：T396_9 由递归取首键改为精确键路径。
3. **闭合 INV-4 缺口**：`overrides=={}` 零变更由一次性手工自测升级为持久断言。
4. **修复 error-path 漂移**：空/不可用 `--minute-root` 由「traceback + 退出码 1」改为「一行提示 + exit 2」。
5. **文档对齐实现**：DESIGN §6.2 用例矩阵、§7 机制措辞、v396 CHECKLIST §5 措辞同步。

**非目标**：不改任何数值口径、不改 `cost_by_h`/`net(h)`/容量读数、不新增 CLI 参数、不引入新依赖。

## 2. 设计依据

### 2.1 调研结论 → 设计决策

| 调研结论（RESEARCH §） | 设计决策 |
|---|---|
| §2.1 T3100_3 L304-309 为本地 numpy 恒等式；L311-320 有效 | **D1** 删 L304-309 + 改 docstring/注释，保留 L311-320 |
| §2.2 `_find_key` 仅 1 处调用，精确路径 `panels.coverage.universe_ratio` 已实证 | **D2** 改精确路径 + 删 `_find_key` |
| §2.3 `CalibrationConfig` frozen + `config_hash()` | **D3** 配置等价 + hash 相等断言（T397_1） |
| §2.4(a) DESIGN §6.2 与 T396_6 数值逐例不同、语义等价 | **D4** 以测试为真值勘误 §6.2 |
| §2.4(b) 空根抛 `CalibrationUnavailable`、脚本未捕获 → 退出码 1；U-1=B | **D5** script 捕获 → 提示 → `return 2`；**D9** 文档机制措辞勘误 |
| §2.4(c) `_decay_curve_md` 内联导入无捕获 | **D7** ImportError 上抛断言（T397_3） |
| §5.1.1 F-1 T3100_3 docstring 亦失真 | 并入 **D1** |
| §8.3 测试金字塔；main() 可打桩 | **D6** 单元级 `CalibrationUnavailable`（T397_2）；**D8** 进程内 CLI（T397_4） |
| §8.4 SemVer §7 | **D10** 版本 3.9.7 六处同步 |

### 2.2 相关 ADR

| ADR | 决定 | 本批关系 |
|---|---|---|
| D-002（审计口径） | 审计只登记不修复 | P-017 整批即该口径的整改落地 |
| v3.9.6 D3（demean 幅度断言） | 曾裁定「幅度断言」 | **被本批 D1 取代**（该断言被证实恒真） |
| v3.9.6 D9（`--minute-root`） | 新增参数、`default=None` | 本批不改参数，仅补 error-path |
| v3.9.4 D9（force 留痕） | `coverage_gate_forced` token | 本批不动 |

### 2.3 职责边界

| 层 | 本批是否改动 | 说明 |
|---|---|---|
| `backtest/execution/core/` | **否** | 零 diff（INV-3） |
| `backtest/execution/shell/panels.py` | **否** | 零 diff（INV-3） |
| `backtest/execution/ports.py` | 否 | 仅被 script import `CalibrationUnavailable` |
| `scripts/verify_capacity_impact.py` | **是（1 处）** | D5 catch；D10 版本无关代码 |
| `tests/` | 是 | D1/D2/D3/D6/D7/D8 |
| `spec/` + `docs/` | 是 | D4/D9 勘误 |

## 3. 架构设计

### 3.1 变更面

| 编号 | 文件 | 位置 | 改动 | 类型 |
|---|---|---|---|---|
| D1 | tests/test_execution_capacity.py | L293-320 | 删 L304-309（含 `base`）、改 docstring L294、改注释 L304-306 | 测试 |
| D2 | tests/test_minute_panels.py | L778 + L721-735 | 精确键路径；删 `_find_key` | 测试 |
| D3 | tests/test_minute_panels.py | T396_8 后 | 新增 T397_1 | 测试 |
| D4 | spec/v396-audit-backlog-cleanup/DESIGN.md | §6.2 L273-282 | 用例矩阵对齐 T396_6 | 文档 |
| D5 | scripts/verify_capacity_impact.py | L749-757 | `try/except CalibrationUnavailable` → 提示 + `return 2` | **生产** |
| D6 | tests/test_minute_panels.py | 新增 | T397_2 空根 → `CalibrationUnavailable` | 测试 |
| D7 | tests/test_execution_decay.py | 新增 | T397_3 导入失败 → ImportError | 测试 |
| D8 | tests/test_minute_panels.py | 新增 | T397_4 进程内 CLI → `return 2` | 测试 |
| D9 | spec/v396-audit-backlog-cleanup/DESIGN.md + CHECKLIST.md | §7、§5 | 机制措辞勘误 | 文档 |
| D10 | 6 处版本锚点 | — | 3.9.6 → 3.9.7 | 配置/测试 |

### 3.2 模块划分

```text
scripts/verify_capacity_impact.py  main()
  └─ calibrate 分支
       ├─ build_panels(data_root)                      ← 数据缺失抛非 CalibrationUnavailable（不捕获）
       ├─ MinutePanelBuilder(...).build()               ← 抛 CalibrationUnavailable（3 个抛出点）
       │     ├─ daily is None      → "缺少日频参考面板…"
       │     ├─ not has_pyarrow()  → "pyarrow 未安装…"
       │     └─ not usable         → "分钟窗口内无可用月份"
       └─ 【D5 新增】except CalibrationUnavailable → print('[minute] %s') + return 2
```

### 3.3 数据流

异常路径（D5）：
`args.minute_root` → `cfg.minute_root` → `MinuteLoader.available_months()==[]` → `builder.build()` 抛 `CalibrationUnavailable` → **捕获** → stdout 一行 `[minute] <msg>` → 进程退出码 **2**（无 traceback、不写任何工件）。

### 3.4 控制流

正常路径**零改动**：`build()` 成功 → `coverage_gate` → （可选 force 留痕）→ `build_portfolio_panels` → … → `run_calibration`。D5 的 try 块只包住分钟面板获取段，**不包**门禁与后续装配。

## 4. 接口定义

### 4.1 CLI 契约（D5，不新增参数）

| 输入 | 退出码 | stdout | stderr |
|---|---|---|---|
| 空/不存在 `--minute-root`（calibrate 分支） | **2** | `[minute] 分钟窗口内无可用月份` | 空（无 traceback） |
| 正常但覆盖度不足，无 force | 2（不变） | `[coverage] …` | 空 |
| 正常但覆盖度不足 + `--force-coverage` | 0（不变） | 含「门禁失败放行」 | 空 |
| `--no-minute` | 0（不变） | `[minute] --no-minute：…` | 空 |

- 提示行前缀统一为 `[minute]`，与既有 `[coverage]`/`[minute] --no-minute` 风格一致。
- 捕获范围仅 `CalibrationUnavailable`；其它异常（`FileNotFoundError` 等）不吞。

### 4.2 测试契约

| 编号 | 签名 | 断言 |
|---|---|---|
| T3100_3（改） | `test_T3100_3_shift_invariance_after_demean()` | 仅保留 `abs(c.point − d.point) > 1.0`；函数内**不再出现** `base`/`mean()` 恒真断言 |
| T396_9（改） | 不变 | `ratio = payload["panels"]["coverage"]["universe_ratio"]`；`min(ratio.values()) < 0.90` |
| T397_1 | `test_T397_1_empty_overrides_equivalence()` | `C(data_root=X) == C(data_root=X, **{})`；`config_hash()` 相等 |
| T397_2 | `test_T397_2_empty_minute_root_raises(tmp_path)` | `pytest.raises(CalibrationUnavailable, match="无可用月份")` |
| T397_3 | `test_T397_3_decay_md_import_failure(monkeypatch)` | `monkeypatch.setitem(sys.modules, "factor_pipeline", None)` → `pytest.raises(ImportError)` |
| T397_4 | `test_T397_4_minute_unavailable_exit2(tmp_path, monkeypatch, capsys)` | `main() == 2`；stdout 含 `[minute]` 与「无可用月份」；不含 `Traceback` |

## 5. 替代方案

### 5.1 方案 A（选择）：catch + 一行提示 + `return 2`

- 与仓内 3 处 gate（contract/coverage/long_side）退出码一致；消除 traceback；兑现 v3.9.6 §7 的 exit 2 结果。
- 成本：1 处生产改动（约 5 行）+ 1 个进程内 CLI 测试。

### 5.2 方案 B（否决）：仅文档勘误（记录 traceback + 退出码 1）

- 零生产改动，但把「崩溃」写进规范；运维侧需解析 traceback 才能区分原因，且与仓内 gate 语义不一致。

### 5.3 方案 C（否决）：按 v3.8.1 计划降级为 `evidence_warnings` + exit 0

- 与 v3.9.6 §7「无面板即失败」冲突；静默降级会让 CI 把空数据误判为成功（`evidence_level` 降级但仍退出 0）。

### 5.4 方案 D（否决）：catch + `return 1`

- GNU 通用失败码可用，但与仓内 3 处 gate=2 分裂；且需同步改 §7 的「exit 2」承诺。

### 5.5 方案 E（否决）：保留 `_find_key`，再加一条精确路径断言

- 留下死代码与「首键」歧义；审计已明确建议替换。

### 5.6 方案 F（否决）：把 `return 2` 写进 `build()`

- 违反分层（shell 层不应决定进程退出码）；且破坏 `CalibrationUnavailable` 在其它调用方（long_side/测试）的语义。

## 6. 数据结构

### 6.1 精确键路径（D2）

```text
payload
└── panels            (script attach_panel_meta, L413)
    └── coverage      (PanelCoverage.as_dict())
        ├── universe_ratio : {ym: float}     ← 断言目标
        ├── ratio_raw      : {ym: float}
        └── …（window/months/partial…）
```

- 断言：`min(payload["panels"]["coverage"]["universe_ratio"].values()) < 0.90`。
- 删除 `_find_key`（L721-735），全仓无其它引用。

### 6.2 DESIGN §6.2 用例矩阵勘误（D4，以实现为真值）

| 用例 | net | sd | 期望 | 覆盖语义 |
|---|---|---|---|---|
| 空 | `{}` | 0.0 | `[]` | 空输入 |
| sd=0 只留 argmax | `{5:2.0, 10:1.0, 20:0.5}` | 0.0 | `[5]` | 阈值 = argmax |
| 并列 + 排序 | `{20:1.0, 5:1.0, 10:0.5}` | 0.0 | `[5, 20]` | `>=` 含并列、输出升序 |
| ≥ 边界包含 | `{5:1.0, 10:0.9}` | 0.1 | `[5, 10]` | `v >= max−sd` 取等 |
| 边界外剔除 | `{5:1.0, 10:0.89}` | 0.1 | `[5]` | 严格小于被排除 |
| 单点 | `{20:3.0}` | 100.0 | `[20]` | `h*` 恒含 |

- 勘误标记：v396 DESIGN §6.2 表（v1.3→v1.4 由 v3.9.7 批次勘误注记）。

### 6.3 退出码与提示文案（D5）

| 常量 | 值 |
|---|---|
| 退出码 | `2` |
| 提示前缀 | `[minute] ` |
| 示例 | `[minute] 分钟窗口内无可用月份` |

## 7. 错误处理

| 场景 | 处理 | 退出码 | 测试/证据 |
|---|---|---|---|
| 空/不存在 `--minute-root` | `CalibrationUnavailable("分钟窗口内无可用月份")` → catch | 2 | T397_4（进程内 CLI）+ T397_2（单元） |
| pyarrow 缺失 | `CalibrationUnavailable("pyarrow 未安装…")` → catch | 2 | 源码 L447 核验（不新增 mock 用例） |
| `build()` 前 daily 为 None | `CalibrationUnavailable("缺少日频参考面板…")` → catch | 2 | 源码 L445 核验 |
| `build_panels` 读盘失败 | **不捕获**，保持原异常 | 1 | 设计边界（不扩大捕获面） |
| `_decay_curve_md` 时包缺失 | `ImportError` 上抛 | 1 | T397_3 |
| 覆盖度门禁失败 | 不变（`return 2` / force 放行） | 2 / 0 | T396_9 既有 |

## 8. 不变式（Invariants）

| 编号 | 不变式 | 验证方式 |
|---|---|---|
| INV-1 | 默认 `out/capacity_impact.json` SHA256 `82728CE1…` 逐位不变 | 跑前/跑后 `Get-FileHash` |
| INV-2 | `out/v394_calibration.json` 的 `panel_hash` 仍为 `dfcc4e1d…` | 读 JSON |
| INV-3 | `backtest/execution/core/` 与 `shell/panels.py` 零 diff | `git diff --stat` |
| INV-4 | `CalibrationConfig(data_root=X) == CalibrationConfig(data_root=X, **{})` 且 `config_hash()` 相等 | T397_1 |
| INV-5 | 零新增依赖（`pyproject.toml` 仅 version 行变化） | `git diff` |
| INV-6 | 版本 3.9.7 六处一致（pyproject/`__init__`/config_v2/reporting + 2 测试锚点） | `grep 3.9.7` |
| INV-7 | 正常路径（无异常）行为零变化：D5 的 try 不改变成功分支控制流 | 全量 pytest + INV-1 |
| INV-8 | CLI 参数集合零变化（无新增/删除/改名） | `--help` 文本对比 |

## 9. 幻觉抑制审查（Step 4 Review）

> 本节在 Step 4 由复审回填；以下为 Step 3 预填的待核声明。

### 9.1 待核声明（E1）— Step 4 复核结果

| # | 声明 | 锚点 | 状态 |
|---|---|---|---|
| 1 | `CalibrationUnavailable` 可由 `backtest.execution.ports` 导入 | [ports.py L16](file:///f:/Coding/factor_pipeline/backtest/execution/ports.py#L16) `class CalibrationUnavailable(RuntimeError)` | ✅ |
| 2 | 三抛出点文案逐字 | [panels.py L445/L447/L474](file:///f:/Coding/factor_pipeline/backtest/execution/shell/panels.py#L445-L474)：`缺少日频参考面板…` / `pyarrow 未安装…` / `分钟窗口内无可用月份` | ✅ 逐字核对 |
| 3 | `main()` 无 argv 参数、`parse_args()` 读 `sys.argv` | script L661 `def main():`、L704 `args = ap.parse_args()` | ✅ |
| 4 | `build_panels`/`daily_ref` 经模块 globals 解析（可 monkeypatch） | script L749 `market = build_panels(args.data_root)`、L755 `daily=daily_ref(market, cfg)`，均在 main() 内裸名调用 | ✅ |
| 5 | `payload["panels"]["coverage"]` 由 `attach_panel_meta` 写入 | 定义 [L404](file:///f:/Coding/factor_pipeline/scripts/verify_capacity_impact.py#L404)、`coverage` 键 [L413](file:///f:/Coding/factor_pipeline/scripts/verify_capacity_impact.py#L413)、**调用点 L779**（门禁之后） | ✅ |
| 6 | `_find_key` 全仓仅 L778 一处调用 | 全仓 Grep：仅 tests/test_minute_panels.py L721(def)/L778(call)，其余命中均为本 spec 文档 | ✅ |
| 7 | `CalibrationConfig` frozen + `config_hash()` | [config.py L18-19](file:///f:/Coding/factor_pipeline/backtest/execution/config.py#L18-L19) `@dataclass(frozen=True)`、L42-47 `config_hash()` | ✅ |
| 8 | T396_6 六例与 §6.2 勘误表逐例一致 | test_execution_decay.py L292-298 六参数逐一比对 | ✅ |
| 9 | v396 DESIGN §7 原文断言「exit 2」 | [v396 DESIGN L298-299](../v396-audit-backlog-cleanup/DESIGN.md#L298-L299)：处理方式「无面板 → 门禁失败」、可见信息「`[coverage] …`；无 force 则 exit 2」 | ✅（D9 勘误对象确认） |
| 10 | 六处版本锚点当前均为 3.9.6 | pyproject L7 / config_v2 L371 / `__init__` L58 / reporting L40 / test_fix3 L34 / verify_fix3_manual L21 | ✅（其余 `3.9.6` 命中均为注释/历史，不在 D10 范围） |

### 9.2 门禁 a-d

- [x] a. 无未验证声明 — 9.1 十项全部 ✅（证据等级 E1：逐行/逐字锚点复核）
- [x] b. 无「实现不存在却按已存在设计」的引用 — ①②⑤⑥⑦⑧⑩ 均为既有实现直接引用；④③ 为行为实证
- [x] c. 替代方案均给出否决理由 — §5.2-§5.6 五项均含理由
- [x] d. 职责边界与既有分层一致 — exit 决策留在 script（§5.6 明确否决下沉 core/shell）；提示用 print 与既有 `[coverage]` 一致

### 9.3 复审结论

**PASS**（2026-11-21，Step 4）：

- 十项 E1 声明全部命中，无幻觉引用；§6.2 勘误表与 T396_6 六例逐例一致；
- 新增精度信息：`attach_panel_meta` 调用点为 **L779**（位于覆盖度门禁之后）→ T396_9 读取 forced 工件时 `panels.coverage` 必然存在；D5 捕获段（L749-757）不含 L779，两段互不重叠；
- v396 DESIGN §7 勘误对象精确定位：L298-299（处理方式 + 可见信息两列均需改）；v396 CHECKLIST §5 勘误对象精确定位：**L159**（「空根使全月份进 `missing_months` 走同一分支」表述失真——空根实际在 `build()` 抛 `CalibrationUnavailable`，不会到达门禁）；
- 设计无需修订，直接进入 Step 5（IMPLEMENTATION 撰写）。

## 10. 对实施的输入

### 10.1 关键工程约束

1. D5 的 `except` 只包 `build_panels`/`builder` 构造/`build()`，**不包**门禁与装配。
2. 提示用 `print`（stdout），与 `[coverage]` 一致；不打印 traceback。
3. D1 删除 `base` 变量后，函数内不得残留对 `base` 的引用。
4. T397_2/T397_4 需 `pytest.importorskip("pyarrow")` 或 `needs_pyarrow`（`build()` 在 avail 检查前先查 pyarrow）。
5. T397_4 需 monkeypatch `vci.build_panels` 与 `vci.daily_ref`，避免读盘。
6. 全部新增用例单次总耗时 ≤ 1 s（T396_9 除外）。
7. 版本 6 处同步，`grep -r "3\.9\.6"` 仅允许出现在历史 CHANGELOG/spec。

### 10.2 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| D5 缩进改动引入语法/控制流错误 | 正常路径行为变化 | 全量 pytest + INV-1 SHA 比对 |
| T397_4 打桩不完整（main 仍读盘） | 用例慢或失败 | stub `build_panels`+`daily_ref`；实测 0.02 s（Step 10 审计 F4 勘误：未加显式 elapsed 断言） |
| 删 `_find_key` 后遗漏引用 | 收集期 NameError | 实施后全仓 Grep `_find_key` |
| T397_3 的 `sys.modules=None` 污染同进程 | 顺序相关失败 | monkeypatch 自动回滚；用例内不再 import 包 |
| DESIGN §6.2 勘误与测试再次漂移 | P3 复发 | 勘误表逐例抄自 T396_6 L293-298 |

## 11. 未决项登记（四元块）与决策矩阵

| 项 | 状态 | 裁决 |
|---|---|---|
| U-1 空根语义 | **closed** | B：catch + 提示 + `return 2` |
| U-2 CLI 级证据 | **closed** | 进程内 CLI（T397_4），不补子进程 E2E |
| U-3 版本 | **closed** | 3.9.7 |

本批无新增未决项。
