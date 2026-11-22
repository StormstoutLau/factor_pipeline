# 实施文档：v3.9.8 P-011 DEV_PROGRESS §4 存量待办逐条裁决

---
id: v398-p011-dev-backlog-triage-IMPLEMENTATION
type: design
version: 1.1
status: verified
date: 2026-11-22
depends: [v398-p011-dev-backlog-triage-DESIGN, v398-p011-dev-backlog-triage-RESEARCH]
upstream: null
---

> **Feature**: P-011 文档级裁决与三账本同步
> **创建日期**: 2026-11-22
> **状态**: verified（v1.1：Step 9 补 §8.4 红→绿；Step 6 独立复审 PASS_WITH_FIXES，0×P1 / 0×P2 / 2×P3 已修复；V1-V6 独立复跑全 PASS；§9 已升级 [已复核]）
> **Spec 步骤**: Step 5-6, 9
> **基于设计**: [DESIGN.md](./DESIGN.md)（v1.0 verified，Step 4 双视角 PASS_WITH_FIXES）
> **基于调研**: [RESEARCH.md](./RESEARCH.md)（v1.3 verified）
> **档位**: T3 轻批（Layer-0）。**本批零生产代码、零测试、零新依赖**。

---

## 1. 实施概述

本批的实施对象是**文档与账本**，不是运行时：把 11 条裁决写入 DEV_PROGRESS §4，把待办真值源收敛到 PROGRESS，把 PROJECT_STATUS 改为指针，并在 RESEARCH 留下两轮复审记录。

**时序如实声明**：D1（裁决表回填）与 D5（三账本同步）已在 Step 1-2 / Step 3 期间执行完毕（RESEARCH §6.4/§8.2 有记录）；本文档是**实施记录 + 可复现步骤 + 验证口径**。Step 1-6 期间未走 TDD（研究阶段 F5 = N/A，RESEARCH §5.5）；Step 9 以**临时文档契约检查器**补出真实红→绿（§8.4），脚本不入库。

## 2. 工程细节

### 2.1 技术栈

| 组件 | 技术 | 版本 | 验证状态 |
|------|------|------|---------|
| 语言 | Python | 3.9（`requires-python = ">=3.9"`，pyproject.toml L10） | ✅ 未新增语法 |
| 依赖管理 | pyproject.toml | 包版本 3.9.7（pyproject L7 / `__init__.py` L58） | ✅ 本批不改 |
| 文档格式 | Markdown + Git | — | ✅ |
| 新增依赖 | 无 | — | ✅ 零新增 |

### 2.2 依赖版本验证

**N/A**——本批不新增、不升级任何三方依赖，也不引用新的标准库 API；因此无需 PyPI 查询。包版本保持 **3.9.7**，`3.9.8` 仅为下个发版批次的候选号（见 D-398-1）。

### 2.3 文件结构

```
spec/v398-p011-dev-backlog-triage/
├── RESEARCH.md          # Step 2（v1.3，含 §8 两轮复审）
├── DESIGN.md            # Step 3-4（v1.0 verified）
└── IMPLEMENTATION.md    # Step 5-6（本文档）
docs/
├── DEV_PROGRESS.md      # §4 冻结表（L188-L209）
├── PROGRESS.md          # 待办真值源（P-011 L30 / P-018 L31 / P-009 L28）
└── PROJECT_STATUS.md    # 指针层（L267 / L277 / L278 / L314）
```

## 3. 模块实施

### 3.1 裁决矩阵（DESIGN D1）

#### 职责

把 11 条原条目逐行映射为「现状 / 裁决 / 置信度 / 证据」。来源为 RESEARCH §3。

#### 实施位置

| 文件 | 锚点 | 内容 |
|---|---|---|
| `docs/DEV_PROGRESS.md` | L188 标题；L194 / L200 两表头；L196-L198（P1 候选 3 条）；L202-L209（远期 8 条） | 三列：原条目 / P-011 裁决（2026-11-22）/ 证据 |
| `spec/v398-p011-dev-backlog-triage/RESEARCH.md` | §3 表（含置信度列，v1.3） | 裁决依据与 E1 锚点 |

#### 实施要点

- 行数恒为 **3 + 8 = 11**；裁决词四值封闭。
- 标题保持「已裁决，本表冻结」，表前声明指向 PROGRESS 为真值源（L190-L192）。
- 第 9 条触发条件不在本模块，落 3.4。

#### 低效操作排除

| 潜在低效 | 排除措施 |
|---|---|
| 三处复制裁决理由 | 只在 DEV_PROGRESS 写一次；PROJECT_STATUS 仅指针（D5） |
| 每次复审重扫全仓 | 锚点带版本 + 行号，抽样核查（D7） |

### 3.2 真值源（DESIGN D5）

#### 职责

PROGRESS 是待办状态的唯一出口；P-011 / P-018 / P-009 的状态与验收只在此定义。

#### 实施位置

| 行 | 内容 |
|---|---|
| [PROGRESS.md L30](../../docs/PROGRESS.md#L30) | P-011：依据列含 RESEARCH v1.3 + DESIGN v1.0 + T3 裁剪理由；验收 ①②③（+④ 流程项，复审 P3-2 对齐） |
| [PROGRESS.md L31](../../docs/PROGRESS.md#L31) | P-018：`pending` / P3；验收四条（等价性 / SHA / 内存峰值 / T2.1→T2.5 分批） |
| [PROGRESS.md L28](../../docs/PROGRESS.md#L28) | P-009：保持原有 `pending` / P3，不重复裁决文本 |

#### 实施要点

- P-011 的状态随阶段推进：Step 5-6 期间为 `in-progress`（仅追加文档，不改 T3 验收结论）。
- 新批次编号单调，不复用；P-018 为本次新增。

### 3.3 指针层（DESIGN D5）

#### 职责

PROJECT_STATUS 只加去向与裁决日期，不复述理由或行号。

#### 实施位置

| 行 | 改动 | 现状 |
|---|---|---|
| L277 | 流式行状态加「→ **P-018**（P3 远期）」 | ✅ |
| L278 | Anderson-Rubin 行依据加「P-011 裁决：关闭」 | ✅ |
| L267 | 内生性行加「→ P-009」（复审 B-9 补） | ✅ |
| L314 | T2 节声明「已移交 P-018，保留为能力规格」 | ✅ |

> 注记（复审 B-2）：B-2 指出裁决词实际落在状态列而非设计预期的「依据列」。经核对未违反「禁止复述理由 / 行号」条款，按契约允许形态登记，不改账本。

### 3.4 触发条件登记（DESIGN D3/D4）

#### 职责

第 9、11 条的重开条件必须落在账本、可 Grep，不能只存 RESEARCH。

#### 实施位置与原文

| 条目 | 锚点 | 原文（可 Grep） |
|---|---|---|
| 第 9 条 | [DEV_PROGRESS.md L207](../../docs/DEV_PROGRESS.md#L207) | `触发条件：strategy='auto'`（或任何调用 `HierarchicalImputer` 的路径）进入生产，或诊断输出用于交易 / 风控决策时重开 |
| 第 11 条 | [DEV_PROGRESS.md L209](../../docs/DEV_PROGRESS.md#L209) | `重审条件：` 未来引入 `src/` 布局，或「项目根直接 `python -m`」不再受约束 |

#### 实施要点

- 第 10 条为**纯不修复**（删类前提不成立），不设触发条件——与第 9 条不对称是设计意图（复审 A-2）。
- 关键词固定为「触发条件」「重审条件」，供机械核查（INV-6）。

## 4. 契约实施

### 4.1 DEV_PROGRESS §4 表契约

**契约一致性**：与 DESIGN §4.1 一致 ✅（分表形态由复审 B-1 登记为允许形态）。

```text
表头：原条目 | P-011 裁决（2026-11-22） | 证据
行数：3（原 §4.0 P1 候选）+ 8（原 §4.1/§4.2 远期）= 11
裁决词：关闭 | 转 P | 不修复 | 不修复 + 触发条件
```

### 4.2 PROGRESS 行契约

**契约一致性**：与 DESIGN §4.2 一致 ✅。

```text
P-011：依据列 = RESEARCH 链接 + DESIGN 链接 + 档位 + 一句裁剪理由；验收 ①②③（+④ 流程项）
P-018：status=pending；priority=P3；验收 ①②③④ 非空
P-009：status=pending；priority=P3；不复制裁决文本
```

### 4.3 PROJECT_STATUS 指针契约

**契约一致性**：与 DESIGN §4.3 一致 ✅（落位列偏差见 3.3 注记）。

```text
允许改动：状态列加去向（→ P-018 / → P-009）；依据列加「P-011 裁决 2026-11-22」
禁止：复述裁决理由、证据行号、账本表格
```

### 4.4 触发条件文本契约

**契约一致性**：与 DESIGN §4.4 一致 ✅。

```text
第 9 条关键词：触发条件 + strategy='auto' + HierarchicalImputer + 交易 / 风控
第 11 条关键词：重审条件 + src/ 布局 + python -m
可核查：Grep '触发条件：|重审条件：' docs/DEV_PROGRESS.md → 命中 L207/L209
```

## 5. 兼容性

### 5.1 Python 版本兼容

| Python 版本 | 支持 | 说明 |
|---|---|---|
| 3.9 | ✅ | 本批无代码，不受影响 |
| 3.10+ | ✅ | 同上 |

### 5.2 依赖兼容

**N/A**——零依赖变更。

### 5.3 向后兼容

- 文档链接：三账本既有相对链接未改动，新增链接均指向仓内已存在文件。
- 账本语义：DEV_PROGRESS §4 原文保留（冻结备查）；新增列不删除历史诉求。
- 包版本：不升版，`3.9.8` 仅为候选号（D-398-1）。

## 6. 错误处理实施

| 错误场景（DESIGN §7） | 实施处理 | 验证方式 |
|---|---|---|
| 账本漂移 | 以 PROGRESS 为准，改指针层；复审 B-3 覆盖 | 三处交叉核对（Step 4 视角 B） |
| 触发条件只存 RESEARCH | 回填 DEV_PROGRESS L207/L209 | Grep 双命中 |
| 锚点行号漂移 | 复审抽样，DRIFT 即更新 | RESEARCH §8.1（22/22 PASS） |
| 外部锚点当第二事实源 | 门禁 (c) 口径改为「事实前提双源」 | RESEARCH §2.3(c) |
| 下游误入本批范围 | §2.3 职责外 + 移交行 | RESEARCH §6.5/§6.6 |

## 7. 不变式实施

| 不变式（DESIGN §8） | 实施位置 | 验证方式 | 状态 |
|---|---|---|---|
| INV-1 零代码 diff | 全批 | `git status --short` 仅 3 账本 M + spec 未跟踪 | ✅ |
| INV-2 默认 SHA 不变 | 不触碰 `out/` | `git status` 无 `out/` 条目 | ✅ |
| INV-3 §4 恒 11 行 | DEV_PROGRESS L188-L209 | 3 + 8 = 11 | ✅ |
| INV-4 双源无单源 | RESEARCH §3 / §2.3(c) | 本批目录内 Grep `单源-待二核` 仅命中定义行与引用行（复审 P3-1 限定口径；全 spec/ 的其他命中属历史批次遗留标记，不在本批范围） | ✅ |
| INV-5 三账本无相反表述 | 三账本 | Step 4 视角 B 交叉核对 | ✅ |
| INV-6 触发条件可 Grep | DEV_PROGRESS L207/L209 | `Grep '触发条件：|重审条件：'` | ✅ |
| INV-7 下游验收可核查 | PROGRESS L28/L31 | status 非空 + 验收列非空 | ✅ |

## 8. 测试策略

### 8.1 单元测试

**N/A**——零代码、零测试文件改动。按 SPEC_PROCESS RULE-1 补·纯登记型批次口径：核查范围 = 锚点存在 + 章节真实 + session 状态一致；无 diff 为合法态。

### 8.2 集成测试

**N/A**。

### 8.3 验证矩阵（静态可复现）

| # | 检查 | 命令 | 期望 | 实测（2026-11-22） |
|---|---|---|---|---|
| V1 | 空白/冲突标记 | `git diff --check` | exit 0，无输出 | ✅ exit 0 |
| V2 | 改动边界 | `git status --short` | 仅 3 账本 + spec 目录 | ✅ 与期望一致 |
| V3 | §4 行数 | 人工/脚本数两表数据行 | 11 | ✅ 3+8 |
| V4 | 触发条件 | `Grep "触发条件：|重审条件：" docs/DEV_PROGRESS.md` | 命中 2 行 | ✅ L207/L209 |
| V5 | 下游验收 | 查 PROGRESS L28/L31 | status + 验收非空 | ✅ |
| V6 | 外链可达 | 抽查 DESIGN §2.2 四个 ADR 锚点 | 标题匹配 | ✅ L917/L1123/L2980/L3175 |

### 8.4 Step 9 TDD 补强：文档契约检查器（红→绿）

**适用性声明**：T3 轻批不要求 Step 9（SPEC_PROCESS L556：证据出口为「代码测试，如有」）。本批按用户指令补强，采用**临时文档契约检查器**，放在 `%TEMP%`、**不入库**——若放入 `tests/` 会触发 Layer-1 判档（SPEC_PROCESS L561），与零代码档位冲突。

**断言来源**：CHECKLIST §2/§4 + PROGRESS / PROJECT_STATUS 契约，共 8 条（R1 §4 冻结声明；R2 裁决行数 = 11；R3 第 9 条触发条件；R4 第 11 条重审条件；R5 P-018 立项行；R6 P-011 真值源行；R7 PROJECT_STATUS 指针；R8 CHECKLIST 统计 63）。

**红→绿记录（同一脚本、同一断言集）**：

| 阶段 | 命令 | 读数 | 退出码 |
|---|---|---|---|
| 红（变更前基线 `git HEAD`） | `python %TEMP%\p011_step9_check.py HEAD` | `passed=0 failed=8`（R1-R8 全 FAIL） | 1 |
| 绿（当前工作区） | `python %TEMP%\p011_step9_check.py WORKTREE` | `passed=8 failed=0` | 0 |

**结论**：满足 F5 形态（先失败、后通过、断言未改）。红态来自 HEAD 的真实旧账本，非人为构造；脚本未写入仓库，不改变 INV-1 的零代码边界。

## 9. 幻觉抑制审查（Step 6 Review）

> **[已复核]**（Step 6 独立复审，2026-11-22）：原 [自查·并发] 勾选经独立只读 pass 逐项复核后升级。复审结论 **PASS_WITH_FIXES**（0×P1 / 0×P2 / 2×P3，均已就地修复）；§9.1-§9.5 勾选与实际一致；V1-V6 独立复跑全 PASS；锚点文档/章节 100% 真实、零代码无 diff 为合法态（RULE-1 纯登记型口径）。2×P3：P3-1 INV-4 验证方式限定本批目录（已改 §7）；P3-2 P-011 验收计数对齐 ①②③+④（已改 §3.2/§4.2）。

### 9.1 依赖版本验证

- [x] 所有依赖版本已查询 PyPI 确认存在 —— **N/A（零新增依赖）**
- [x] 无虚构的库或函数 —— 未引用新库；仅引用仓内文件
- [x] 版本兼容性已验证 —— Python 3.9 无代码影响

### 9.2 接口签名验证

- [x] 所有接口签名与 DESIGN.md §4 一致 —— 四类契约逐一对照（§4.1-§4.4）
- [x] 所有签名可实现 —— 文档契约无类型组合问题

### 9.3 实施与设计对齐

- [x] 每个模块对应 DESIGN.md §3.2 的一个模块 —— 4/4（裁决矩阵 / 真值源 / 指针层 / 触发登记）
- [x] 每个接口对应 DESIGN.md §4 的一个接口 —— 4/4
- [x] 无设计未覆盖的实施 —— D-398-2（分表形态）、D-398-3（落位列）已在 §11 登记

### 9.4 低效操作排除

- [x] 无 O(n²) 可优化为 O(n log n) 的操作 —— 无代码
- [x] 无不必要的 I/O —— 无运行时
- [x] 无重复计算 —— 裁决文本单点存储

### 9.5 标准库下限检查（Step 6 v1.1）

- [x] 未引用任何标准库 API，N/A。

## 10. 实施步骤

### Step 1: 裁决回填

- 文件: `docs/DEV_PROGRESS.md` §4
- 内容: 11 行裁决 + 证据列 + 第 9/11 条触发条件（L207/L209）
- 验证: INV-3 / INV-6

### Step 2: 真值源与指针

- 文件: `docs/PROGRESS.md`、`docs/PROJECT_STATUS.md`
- 内容: P-011 done / P-018 pending / P-009 指针；PROJECT_STATUS 四处注记
- 验证: INV-5 / INV-7

### Step 3: 调研与设计定稿

- 文件: `spec/v398-p011-dev-backlog-triage/RESEARCH.md`（v1.3）、`DESIGN.md`（v1.0 verified）
- 内容: 两轮双视角复审 + 8×P3 处置
- 验证: RESEARCH §8、DESIGN §9

### Step 4: 本文档

- 文件: `spec/v398-p011-dev-backlog-triage/IMPLEMENTATION.md`
- 内容: 实施记录 + 验证矩阵 + Step 6 自查
- 验证: `git diff --check`；Step 6 独立复审

### Step 5: Step 9 TDD 补强

- 文件: `%TEMP%\p011_step9_check.py`（**不入库**，避免 Layer-1 判档）
- 内容: 8 条文档契约断言（R1-R8），同一脚本跑 `HEAD` 与 `WORKTREE`
- 验证: 红 `passed=0 failed=8` / exit 1 → 绿 `passed=8 failed=0` / exit 0（§8.4）

## 11. 衍生需求登记（Step 8 追溯要求）

| ID | 衍生决策 | 来源 | 验收 |
|---|---|---|---|
| D-398-1 | 包版本**不**随纯文档批次升号；`3.9.8` 仅为下一发版候选 | DESIGN §10.1 + pyproject L7 / `__init__.py` L58 实测 3.9.7 | 本批 `__init__.py` / `pyproject.toml` 零 diff |
| D-398-2 | DEV_PROGRESS §4 允许两张分表（P1 候选 / 远期），合计 11 行 | 复审 B-1 | 行数 = 3 + 8 |
| D-398-3 | PROJECT_STATUS 裁决注记落状态列而非依据列，属允许形态 | 复审 B-2 | 未复述理由 / 行号 |
| D-398-4 | T3 批次在用户要求下追加 Step 3-6 文档，但代码仍为零 | 用户指令 2026-11-22 | INV-1 零代码 diff |
| D-398-5 | INV-4 验证口径收窄至本批目录（Step 6 P3-1 修复），较 DESIGN §8 无范围限定为更严口径 | Step 8 复审 P3-4 | IMPL §7 与 §9 自洽说明 |
| D-398-6 | Step 9 以临时文档契约检查器补强红→绿（0/8 → 8/8），脚本置于 `%TEMP%` 不入库，避免触发 Layer-1 判档 | 用户指令 2026-11-22 + SPEC_PROCESS L556/L561 | 仓库内无 `.py` 新增（INV-1） |

## 12. 回退方案

| 场景 | 回退动作 | 影响面 |
|---|---|---|
| 账本措辞需撤回 | `git checkout -- docs/DEV_PROGRESS.md docs/PROGRESS.md docs/PROJECT_STATUS.md` | 仅账本；无运行时状态 |
| 设计/实施文档需撤回 | 删除 `spec/v398-p011-dev-backlog-triage/` 下对应文件 | 仅文档 |
| 下游批次误启动 | 回退 PROGRESS P-018/P-009 行即可，无代码副作用 | 待办表 |

> 回退点：本批**不产生**任何运行时状态、缓存或 `out/` 工件；`out/capacity_impact.json` 与 `panel_hash` 全程未被触碰（INV-2）。

---

**Review 签字**: _________ 日期: _________
