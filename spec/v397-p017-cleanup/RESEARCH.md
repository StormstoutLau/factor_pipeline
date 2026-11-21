# 调研：v3.9.7 P-017 审计遗留清尾（测试有效性与文档一致性）

---
id: v397-p017-cleanup-RESEARCH
type: research
version: 1.2
status: verified（Step 1 调研 + 补充调研 + Step 2 复审双 pass 完成；U-1/U-2/U-3 已裁决）
date: 2026-11-21
depends: [v396-audit-backlog-cleanup-CHECKLIST, v394-audit-coverage-fix-CHECKLIST, v3100-reversal-evidence-CHECKLIST]
upstream: null
---

> **Feature**: 关闭 P-017（v3.9.6 Step 10 审计遗留 1×P2 + 3×P3）——① T3100_3 恒真断言与误导注释；② T396_9 `_find_key` 精确键路径；③ INV-4 持久断言；④ DESIGN §6.2 用例矩阵同步 + §7 error-path 补测。
> **创建日期**: 2026-11-21
> **状态**: draft（Step 1 调研完成）
> **Spec 步骤**: Step 1-2
> **包版本**: **3.9.7**（patch；预期零生产逻辑变更，仅测试与文档）
> **硬约束**: 默认 `out/capacity_impact.json` SHA `82728CE1…`、`panel_hash dfcc4e1d…` 逐位不变；`backtest/execution/core/` 与 `shell/panels.py` 零改动；零新增依赖；Python 3.9。

---

## 1. 调研目标

**核心问题**：
1. 四项遗留（1×P2 + 3×P3）的**当前实现与文档现状**分别是什么？能否用「改前红、改后绿」的最小测试闭合？
2. 是否存在**零生产改动**即可闭合全部四项的路径？若某项必须改生产代码，边界与替代口径是什么？
3. 新增测试的**运行成本**是否可接受（不引入 `slow` 标记、不重跑 39 月校准）？

## 2. 现状核查

### 2.1 P-017①（P2）T3100_3 恒真断言与误导注释

- 位置：[tests/test_execution_capacity.py L293-320](file:///f:/Coding/factor_pipeline/tests/test_execution_capacity.py#L293-L320)。
- 实测：`base = raw - raw.mean()`（L304）与两条断言（L307-309）**均为测试本地 numpy 运算**，不调用 `cross_section_reversal`：`base.mean()==0` 与 `max|base-raw|==|raw.mean()|` 由「标量广播 + 均值定义」数学恒成立 → 实现若把 demean 公式改成 median，这两条仍然绿。
- L306 注释「误用 median 等公式漂移会被捕获」**不成立**；L311-320 的全买侧 `raw` vs `raw+0.5` 对照（Δbps=5000>1.0）才是有效判别力来源。
- 结论：**删除 L307-309，注释改为如实描述**，保留 L311-320；同步勘误 [v396 DESIGN D3](../v396-audit-backlog-cleanup/DESIGN.md) 与 v396 CHECKLIST §2.1-③ 的「幅度断言」表述。

### 2.2 P-017②（P3）T396_9 `_find_key` 取首个同名键

- 位置：[_find_key L721-735](file:///f:/Coding/factor_pipeline/tests/test_minute_panels.py#L721-L735)，调用 L778-780。
- 现状缺陷：递归返回嵌套 JSON 中**首个** `universe_ratio`；未来 payload 增加同名键（如 `diagnostics.universe_ratio`）会静默锚错对象。
- 精确路径已实证：`attach_panel_meta` 写 `result['panels']['coverage'] = cov.as_dict()`（[script L404-413](file:///f:/Coding/factor_pipeline/scripts/verify_capacity_impact.py#L404-L413)），`PanelCoverage.as_dict()` 含 `universe_ratio`（[panels.py L65-79](file:///f:/Coding/factor_pipeline/backtest/execution/shell/panels.py#L65-L79)）。
- 结论：改为 `payload["panels"]["coverage"]["universe_ratio"]`，同时**删除 `_find_key` 辅助函数**（无其它调用点）。

### 2.3 P-017③（P3）INV-4 无持久断言

- 现状：T396_8（[L738-746](file:///f:/Coding/factor_pipeline/tests/test_minute_panels.py#L738-L746)）只断言 `--help` 含参 + `CalibrationConfig().minute_root` 默认值；「不传参时零行为变更」仅由 v3.9.6 Step 9 手工自测支撑。
- 可持久化的低成本口径已实证：`CalibrationConfig` 为 frozen dataclass 且提供 `config_hash()`（[config.py L19-47](file:///f:/Coding/factor_pipeline/backtest/execution/config.py#L19-L47)）；`CalibrationConfig(data_root=X) == CalibrationConfig(data_root=X, **{})` 且 `config_hash()` 相同，即可锁定「`overrides=={}` 不改变配置」。
- 结论：新增 T397-3（配置等价 + hash 相等）；不引入 CLI 级重跑（默认路径需读全量日频，成本高且与 INV-1 重复）。

### 2.4 P-017④（P3）DESIGN §6.2 漂移 + §7 error-path

#### (a) §6.2 用例矩阵漂移

- 设计表 [DESIGN L273-281](../v396-audit-backlog-cleanup/DESIGN.md#L273-L281) 的 6 例数值与 [T396_6 L292-304](file:///f:/Coding/factor_pipeline/tests/test_execution_decay.py#L292-L304) 实际 6 例**逐例不同**（如设计 `{5:1.0,10:1.0,20:0.5}, sd=0 → [5,10]`；实测 `{20:1.0,5:1.0,10:0.5}, sd=0 → [5,20]`）。语义类别（空 / sd=0 / ≥ 边界 / 边界外 / 并列排序 / 单点）一一对应，覆盖等价。
- 结论：以**实现侧（已审计通过的 T396_6）为真值**，勘误 DESIGN §6.2 表格（文档级，不改测试）。

#### (b) §7 error-path 与实现不符（**调研新发现**）

- 设计 [§7 L292-299](../v396-audit-backlog-cleanup/DESIGN.md#L292-L299) 声称：`--minute-root` 空目录/不存在 → 「无面板 → 门禁失败 → 无 force 则 exit 2」（L298-299 两行）。
- 实测代码路径：`MinuteLoader.available_months()` 对空/不存在目录均返回 `[]`（[loaders.py L85-94](file:///f:/Coding/factor_pipeline/backtest/execution/shell/loaders.py#L85-L94)）→ `MinutePanelBuilder.build()` 在 `usable` 为空时**抛 `CalibrationUnavailable("分钟窗口内无可用月份")`**（[panels.py L442-474](file:///f:/Coding/factor_pipeline/backtest/execution/shell/panels.py#L442-L474)）→ 脚本调用点 [L757](file:///f:/Coding/factor_pipeline/scripts/verify_capacity_impact.py#L757) **无 try/except**，`__main__` 仅 `raise SystemExit(main())`（[L1043-1044](file:///f:/Coding/factor_pipeline/scripts/verify_capacity_impact.py#L1043-L1044)）→ 实际行为是 **traceback + 进程退出码 1**，**不是 exit 2**。门禁分支（L758-763）仅在 `build()` 成功返回后可达。
- 影响：v3.9.6 [CHECKLIST](../v396-audit-backlog-cleanup/CHECKLIST.md) §5「空根 → exit 2」表述**失真**（本次调研据实登记）。T396_9 的 exit 2 来自「有可用月份但覆盖度低」，与该 error-path 不是同一分支。
- 结论：两条可选口径，见 §6.3 **U-1**。**裁决（2026-11-21，用户按建议确认）：选 B**——script 捕获 `CalibrationUnavailable` → 一行提示 → `return 2`；插入点为 main() 分钟层获取段 [L749-757](file:///f:/Coding/factor_pipeline/scripts/verify_capacity_impact.py#L749-L757)（`build_panels` + `builder.build()`），覆盖 build() 的三个抛出点（[panels.py L445/L447/L474](file:///f:/Coding/factor_pipeline/backtest/execution/shell/panels.py#L445-L474)：日频缺失 / pyarrow 缺失 / 无可用月份）。

#### (c) `factor_pipeline` 导入失败

- `_decay_curve_md` 内联导入（[script L565-567](file:///f:/Coding/factor_pipeline/scripts/verify_capacity_impact.py#L565-L567)）无 try/except，`ImportError` 直接上抛；可在进程内用 `monkeypatch.setitem(sys.modules, "factor_pipeline", None)` 复现（Python 3.9 会抛 `ImportError: import of factor_pipeline halted; None in sys.modules`），无需子进程。
- 结论：新增 T397-5 进程内断言 ImportError（不吞）。

### 2.5 影响面与不变式

| 项 | 是否触碰生产代码 | 说明 |
|---|---|---|
| ① 删恒真断言 | 否 | 仅测试文件 |
| ② 精确键路径 | 否 | 仅测试文件 |
| ③ INV-4 断言 | 否 | 仅测试文件（读配置） |
| ④(a) DESIGN 勘误 | 否 | 仅文档 |
| ④(b) error-path | **取决于 U-1** | 口径 B 需改 script 一处 try/except |
| ④(c) 导入失败 | 否 | 仅测试文件 |

不变式（与 v3.9.6 同口径）：INV-1 默认 SHA `82728CE1…`；INV-2 `panel_hash dfcc4e1d…`；INV-3 `core/` 与 `shell/panels.py` 零 diff；INV-4 `CalibrationConfig` 等价 + `config_hash` 相同；INV-5 零新增依赖；INV-6 版本 6 处一致（3.9.7）。

## 3. 方案与裁决（建议）

| 项 | 方案 | 理由 |
|---|---|---|
| ① | **A（采纳）**：删除 L307-309 + 改写注释；保留 L311-320 | 恒真断言无判别力；对照已覆盖语义 |
| ① | B（否决）：改断言为「调用实现后 demean 幅度」 | 实现函数不做 demean（demean 在脚本层），该断言仍无法在 core 单测内成立 |
| ② | **A（采纳）**：精确路径 + 删 `_find_key` | 路径已实证；删死代码 |
| ③ | **A（采纳）**：配置对象等价 + `config_hash()` 相等 | 直接对应 INV-4 语义，成本 <1 ms |
| ④(a) | **A（采纳）**：勘误 DESIGN §6.2 表 → 对齐 T396_6 | 测试已通过 Step 10 审计，以实现为真值 |
| ④(b) | **B（采纳，用户裁决 2026-11-21）**：script L749-757 捕获 `CalibrationUnavailable` → 提示 + `return 2` | 与仓内 3 处 gate `return 2` 一致（contract L712 / coverage L763 / long_side L388）、兑现 v3.9.6 §7 承诺、消除 traceback（§8.1/§8.2）；原 v3.8.1 计划 L796-803 本有 catch 原型，现实现属实施漂移 |
| ④(b) | A（备选）：勘误 DESIGN §7 为「未捕获 → traceback + 退出码 1」；C（备选）：按 v3.8.1 计划降级 + exit 0 | A 零生产改动但保留差 UX；C 静默降级与证据门禁定位冲突 |
| ④(c) | **A（采纳）**：进程内 monkeypatch 断言 ImportError | 快、无子进程 |

## 4. 测试清单（草案）

| 编号 | 文件 | 内容 | 预估 |
|---|---|---|---|
| T3100_3（改写） | test_execution_capacity.py | 删两条恒真断言 + 注释如实；保留非恒真对照 | <0.1 s |
| T396_9（改） | test_minute_panels.py | `payload["panels"]["coverage"]["universe_ratio"]` | 0（随原 E2E 85 s） |
| T397_1 | test_minute_panels.py | 不传参配置等价：`C(data_root=X) == C(data_root=X, **{})` 且 hash 相同 | <0.1 s |
| T397_2 | test_minute_panels.py | 空根 → `MinutePanelBuilder.build()` 抛 `CalibrationUnavailable`（三抛出点 L445/L447/L474 中的 L474 路径；需 pyarrow + 注入非 None daily） | <0.1 s |
| T397_3 | test_execution_decay.py | `_decay_curve_md` 在 `sys.modules["factor_pipeline"]=None` 下抛 ImportError | <0.1 s |
| T397_4 | test_minute_panels.py | 进程内 CLI：`main()` 无 argv 参数（[script L661/L704](file:///f:/Coding/factor_pipeline/scripts/verify_capacity_impact.py#L661-L704)）→ monkeypatch `sys.argv` + stub 模块级 `build_panels`（main 经模块 globals 解析，可打桩）→ 抛 `CalibrationUnavailable` → 断言返回 2 + 提示文案 | <0.1 s |

## 5. 幻觉抑制审查（Step 2 Review）

### 5.1 代码锚点验证

| 声明 | 锚点 | 验证状态 |
|---|---|---|
| T3100_3 两条断言为本地 numpy 恒等式 | tests/test_execution_capacity.py L304-309 | ✅ 逐行读取 |
| 精确路径 `panels.coverage.universe_ratio` | script L404-413 + panels.py L65-79 `as_dict` | ✅ 双端读取 |
| `config_hash()` 存在且为方法 | config.py L42-47 | ✅ |
| 空/不存在根 → `CalibrationUnavailable` | loaders.py L85-94 + panels.py L442-474 | ✅ |
| 脚本无顶层捕获 → 退出码 1 | script L757、L1043-1044 | ✅ |
| `_decay_curve_md` 导入无 try/except | script L565-567 | ✅ |
| 仓内退出码先例：3 处 gate → 2 | script L706-712/L758-763 + `verify_long_side_research.py` L382-388 | ✅ 三处逐一读取 |
| 原计划 catch 原型（实施漂移） | [EXECUTION_V3.8.1_MINUTE_PANEL_WIRING.md L796-803](file:///f:/Coding/factor_pipeline/docs/EXECUTION_V3.8.1_MINUTE_PANEL_WIRING.md#L796-L803) | ✅ 逐行读取 |

#### 5.1.1 第二遍复核（双 pass，2026-11-21）

| 锚点 | 复核结果 |
|---|---|
| T3100_3 全函数 [L293-320](file:///f:/Coding/factor_pipeline/tests/test_execution_capacity.py#L293-L320) | ✅ 结构与申报一致；**新发现 F-1**：docstring L294「demean 幅度可断言（非恒真）」亦失真 |
| `_find_key` 定义 [L721-735](file:///f:/Coding/factor_pipeline/tests/test_minute_panels.py#L721-L735)、唯一调用 L778 | ✅ 无其它引用，可安全删除 |
| T396_8 [L738-746](file:///f:/Coding/factor_pipeline/tests/test_minute_panels.py#L738-L746)、T396_9 [L752-780](file:///f:/Coding/factor_pipeline/tests/test_minute_panels.py#L752-L780) | ✅ 精确路径替换点 = L778 |
| `build()` 三抛出点 [L445/L447/L474](file:///f:/Coding/factor_pipeline/backtest/execution/shell/panels.py#L442-L474) | ✅ 日频缺失 / pyarrow 缺失 / 无可用月份；T397_2 走 L474 路径需注入非 None daily |
| contract gate [L706-712](file:///f:/Coding/factor_pipeline/scripts/verify_capacity_impact.py#L706-L712)（`return 2` @ L712）、coverage gate [L758-766](file:///f:/Coding/factor_pipeline/scripts/verify_capacity_impact.py#L758-L766)（`return 2` @ L763） | ✅ B 的提示/返回值样式与两处 gate 一致 |
| `main()` 无 argv 参数（L661）、`parse_args()`（L704）、`__main__`（L1043-1044） | ✅ T397_4 需 monkeypatch `sys.argv`；未捕获异常 → traceback + 退出码 1 |
| 分钟层获取段 [L749-757](file:///f:/Coding/factor_pipeline/scripts/verify_capacity_impact.py#L749-L757) | ✅ B 插入点；`build_panels`/`daily_ref` 经模块 globals 解析，进程内可打桩 |

### 5.2 待修正项（本批范围）

- [ ] v396 DESIGN §7 空根行（`exit 2`）机制措辞：随 U-1=B 改为「无可用月份 → 一行提示 → exit 2」（结果不变，机制更正）
- [ ] v396 DESIGN §6.2 用例数值表 → 勘误对齐 T396_6（以实现为真值）
- [ ] v3.9.6 CHECKLIST §5 空根行「走同一分支」→ 措辞随 U-1=B 修订
- [ ] **F-1（双 pass 新发现）**：T3100_3 docstring L294「demean 幅度可断言（非恒真）」失真 → 并入 P-017① 改写范围
- [x] PROGRESS P-017 行补本文件链接（v1.1 时已完成）

## 6. 对设计的输入

### 6.1 关键约束

1. **生产改动唯一一处（U-1=B 裁决）**：script main() 分钟层获取段 L749-757 包 `try/except CalibrationUnavailable` → `print('[minute] %s' % exc)` + `return 2`（约 5 行）；`core/`、`shell/panels.py` 零改动。
2. 不改任何既有测试语义（T3100_3 除外：删除恒真段属本批授权范围）。
3. 新增用例不依赖外部数据；仅 T396_9 保留 `needs_*` 门禁。
4. 版本 3.9.7，6 处锚点同步。

### 6.2 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| ④(b) 选 B 引入生产改动 | 违反「仅测试/文档」批次定位 | 默认 A；B 需用户裁决 |
| 删除 `_find_key` 后其它测试引用 | 收集期 NameError | 全仓 Grep 确认仅 T396_9 使用 |
| monkeypatch `sys.modules` 影响同进程其它用例 | 顺序相关失败 | monkeypatch 自动回滚；断言后不再导入 |

### 6.3 未决项登记（四元块）

- **U-1 空 `--minute-root` 的 CLI 语义：文档勘误还是改实现？**
  - **判据**：DESIGN §7 空根行与代码行为一致，且有持久测试锁定该行为。
  - **触发条件**：Step 3-4 设计定稿前必须裁决（阻塞 ④(b) 的实施方案）。→ **已解除**
  - **裁决（2026-11-21，用户按建议确认）：B**——script L749-757 捕获 `CalibrationUnavailable` → 一行提示 → `return 2`；依据 §8.1/§8.2（外部规范不强制、仓内 3 处 gate=2、v3.8.1 计划本有 catch 原型）。
  - **证据等级**：**E2**（Python/GNU/sysexits 规范 + 仓内 4 处退出码先例 + v3.8.1 计划文档的 catch 原型；仍未实跑空根子进程）。

- **U-2 是否补 CLI 级空根 E2E？**
  - **判据**：error-path 行为有端到端证据（退出码 + stderr）；或明确接受进程内 CLI 级证据。
  - **触发条件**：Step 5-6 实施前，取决于 U-1 结论与运行预算。→ **已解除**
  - **裁决（2026-11-21，用户按建议确认）：不补子进程 E2E，改 T397_4 进程内 CLI 测试**（monkeypatch `sys.argv` + stub 模块级 `build_panels`，覆盖 argparse→cfg→catch→返回值，<0.1 s）；T396_9 子进程 E2E 继续覆盖正常链路 + 门禁。
  - **证据等级**：**E2**（测试金字塔 + pytest monkeypatch 文档 + main() 打桩可行性实证）。

- **U-3 版本号**
  - **判据**：pyproject / `__init__` / config_v2 / reporting + 两处测试锚点均为同一值。
  - **触发条件**：Step 3-4 设计定稿前。→ **已解除**
  - **裁决（2026-11-21，用户按建议确认）：3.9.7**（patch；SemVer §7：向下兼容 bug fix → PATCH）。
  - **证据等级**：**E2**（既有 6 处锚点已核 + SemVer §7）。

## 7. 参考文献（内部）

1. v3.9.6 [CHECKLIST.md](../v396-audit-backlog-cleanup/CHECKLIST.md) §8.2/§8.4（P-017 登记源，Step 10 独立审计 PASS_WITH_FIXES 4.75/5）。
2. v3.9.6 [DESIGN.md](../v396-audit-backlog-cleanup/DESIGN.md) §6.2/§7（本批勘误对象）。
3. v3.9.4 [CHECKLIST.md](../v394-audit-coverage-fix/CHECKLIST.md) §8.2（P-015 来源，已关闭）。
4. v3100 [CHECKLIST.md](../v3100-reversal-evidence/CHECKLIST.md) §8.2（P-016 来源，已关闭）。
5. `docs/PROGRESS.md` P-017 行（待办真值源）。

---

## 8. 补充调研：外部锚点（U-1/U-2/U-3）

> 目的：为三项待裁决提供**仓外可引用依据**，避免仅凭内部偏好裁决。证据等级口径：E1 源码/静态推演、E2 权威文档 + 仓内先例、E3 实测运行。

### 8.1 U-1 外部锚点：CLI 退出码语义

| 来源 | 关键内容 | 对 U-1 的含义 |
|---|---|---|
| POSIX / glibc《Exit Status》[1] | 「最常见约定是 0 成功、1 失败」；比较类程序用 1=不匹配、2=**无法比较**；128+ 保留给信号 | 大于 1 的码**并无跨工具强制语义**，仓库可自定 |
| GNU Coding Standards §4.2 [2] | 不得把「错误个数」当退出码（8 位上限）；未强制要求用 2 表示用法错误 | 只有 0/非 0 是可移植契约 |
| Python `argparse` 文档 [3] | 参数非法时 `parse_args()` 打印用法并以**状态码 2** 退出 | 本 CLI 内 2 已被「参数错误」占用；若再用 2 表示数据缺失，属**语义叠加**（非新增冲突） |
| BSD `sysexits(3)` [4] | `EX_USAGE=64`、`EX_DATAERR=65`、`EX_NOINPUT=66`、`EX_UNAVAILABLE=69`；但 OpenBSD 手册明确「non-portable…**Do not use them**」 | 66/69 语义最贴合「分钟根缺失」，但**不可移植且被官方劝阻**，不宜引入 |

**推论**：外部规范**不支持**为此场景引入新码（64-78 不可移植），也**不禁止**沿用内部码。因此决策应由「仓内一致性 + UX」主导，而非外部标准强制。

### 8.2 U-1 内部锚点（强于外部规范）

| 锚点 | 证据 | 含义 |
|---|---|---|
| 契约门禁失败 → 2 | `scripts/verify_capacity_impact.py` L706-712 | 仓内「前置条件不满足」= 2 |
| 覆盖度门禁失败 → 2 | 同文件 L758-763 | 同一脚本内第二处 2 |
| 同构脚本同构语义 | `scripts/verify_long_side_research.py` L382-388 | 跨脚本一致的 2 |
| **v3.8.1 计划文档的靠接原型** | [EXECUTION_V3.8.1_MINUTE_PANEL_WIRING.md L796-803](file:///f:/Coding/factor_pipeline/docs/EXECUTION_V3.8.1_MINUTE_PANEL_WIRING.md#L796-L803)：`try: build() except CalibrationUnavailable as exc: minute = {'evidence_warnings': [...]}` | 现实现的「未捕获」是**实施漂移**；原计划是「降级」而非崩溃 |

**口径对照**：

| 口径 | 行为 | 与 v3.9.6 DESIGN §7 | 与 v3.8.1 计划 | 生产改动 |
|---|---|---|---|---|
| A 文档勘误 | traceback + 退出码 1 | 改文档（机制与结果都改） | 否定 | 0 |
| **B 捕获 + 提示 + `return 2`** | stderr 一行提示 + 2 | 结果一致（仅机制措辞改） | 部分一致（不降级） | ~5 行 |
| C 捕获 + 降级 + exit 0 | warning + 继续出降级报告 | 冲突 | 一致 | ~5 行 |

**建议 B**：理由依次为 ①消除 traceback（可运维性）；②结果与 v3.9.6 §7 承诺一致，文档只需改机制措辞；③与仓内 3 处 gate=2 自洽；④C 的静默降级会让 `evidence_level` 降级但退出 0，容易被 CI 误判为成功，与「证据门禁」定位冲突。**风险**：2 与 argparse 用法错误同码（本轮不新增，属既有叠加）；如需严格区分，可选 D（`return 1` + 提示），但需同步改 §7 的「exit 2」。

### 8.3 U-2 外部锚点：测试层级选择

| 来源 | 关键内容 | 对 U-2 的含义 |
|---|---|---|
| Martin Fowler《Test Pyramid》[5] | 端到端测试**脆弱、编写昂贵、运行慢**；应以大量快速单元/集成测试为主 | 空根 error-path 不值得再付一次 30-60 s 子进程成本 |
| pytest `monkeypatch` 文档 [6] | 提供 `setattr/setitem/delitem/syspath_prepend`，**测试结束自动回滚** | 可安全替换 `build_panels`/`daily_ref`，并模拟模块缺失 |
| pytest 测试套件自身用法 [7] | `with pytest.raises(ImportError)` + `syspath_prepend` 控制导入环境 | ImportError 用例可进程内完成（T397_3） |

**结论**：U-2 不补慢速子进程 E2E；改为 T397_4 进程内 CLI 测试（覆盖 argparse→cfg→`minute_root`→loader→catch→返回值），已有 T396_9 子进程 E2E 继续覆盖「正常链路 + 门禁」。两者合计覆盖 CLI 全分支，成本增量 <0.1 s。

### 8.4 U-3 外部锚点：版本号

| 来源 | 关键内容 | 含义 |
|---|---|---|
| SemVer 2.0.0 §7 [8] | PATCH（Z）在「仅引入向下兼容的 bug 修复」时递增；bug fix 定义为**修正不正确行为的内部修改** | 本批修的是「文档与测试不正确行为」，无 API 变化 → **3.9.7** |

### 8.5 外部锚点小结与裁决结论

**裁决记录（2026-11-21，用户按建议确认）**：U-1 = **B**、U-2 = **进程内 CLI 测试（T397_4）**、U-3 = **3.9.7**。三项四元块已关闭（见 §6.3）。

| 待裁决 | 裁决 | 证据等级 | 升级点 |
|---|---|---|---|
| U-1 | **B**（捕获 → 提示 → `return 2`），DESIGN §7 仅改机制措辞 | **E2** | 新增 4 条外部规范 + 1 条内部历史计划锚点 |
| U-2 | **不补子进程 E2E**，改 T397_4 进程内 CLI 测试 | **E2** | 金字塔 + pytest 官方文档 |
| U-3 | **3.9.7** | **E2** | SemVer §7 明文 |

**若采纳 B 的连带影响**：①生产改动 1 处（script L757 附近）；②新增 T397_4；③v396 DESIGN §7 与 v396 CHECKLIST §5 两处措辞勘误；④INV 声明需增「默认路径 SHA 不变」仍成立（catch 仅在异常路径触发）。

### 8.6 参考文献（外部）

1. The GNU C Library — [Exit Status](https://ftp.gnu.org/old-gnu/Manuals/glibc/html_node/Exit-Status.html)
2. GNU Coding Standards — [4.2 Writing Robust Programs](https://www.gnu.org/prep/standards/standards.html)
3. Python 文档 — [argparse: exit_on_error](https://docs.python.org/3/library/argparse.html)
4. OpenBSD 手册 — [sysexits(3)](https://man.openbsd.org/sysexits)
5. Martin Fowler — [Test Pyramid](https://martinfowler.com/articles/practical-test-pyramid.html)
6. pytest 文档 — [Monkeypatching/mocking modules and environments](https://docs.pytest.org/en/stable/how-to/monkeypatch.html)
7. pytest 源码/测试 — [test_monkeypatch.py](https://github.com/pytest-dev/pytest/blob/main/testing/test_monkeypatch.py)
8. Semantic Versioning — [SemVer 2.0.0](https://semver.org/#semantic-versioning-200)

---

**Review 签字**: _________ 日期: _________
