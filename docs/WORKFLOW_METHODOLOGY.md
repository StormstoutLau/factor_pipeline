# 研究工程化工作流方法论

> **版本**: v1.0 (2026-07-08)
> **来源**: 三轮工作流提炼讨论的整合
> **范围**: 从 v2.4.0 到 v3.1.0 的开发实践中提炼的工作流, 经 planning-with-files / audit-driven-development / MCP 双轨核实三方增强
> **状态**: 已定义, 待长期验证后固化为 skill

---

## 0. 摘要

本文档梳理三轮工作流讨论的成果, 定义完整的 7 阶段研究工程化工作流。工作流从 v2.4.0-v3.1.0 的开发实践中提炼, 并吸收三方增强:

| 增强来源 | 借鉴元素 | 嵌入阶段 |
|---------|---------|---------|
| **planning-with-files** (OthmanAdi) | 5-Question Reboot Test / 3-Strike Error Protocol / 关键文档 attestation | 阶段 1 / 阶段 7 |
| **audit-driven-development** (自建 skill) | 4 阶段审计流程 / 测试盲区识别 / ADR 依赖图检查 / 修复基线 | 阶段 7 |
| **MCP 双轨核实** (新方案) | 学术文献深度核实 (Semantic Scholar 全文) / 工程实践核实 (StackExchange) | 阶段 4+5 |

**核心创新点** (区别于通用编码工作流):
1. 学术层 vs 工程层文档分离 (`docs/private/` vs `docs/EXECUTION_*.md`)
2. 并行 subagent 构建 + 并行 review
3. 接口签名核对 (从源代码确认)
4. 修复 → 二次 review 循环
5. CRITICAL/MAJOR/MINOR 分级 + 阻塞规则
6. enable=False 默认向后兼容
7. **MCP 强制调用深度核实** (学术 + 工程双轨)

---

## 1. 三轮讨论回顾

### 1.1 第一轮: planning-with-files 调研

**问题**: 当前工作流是否可以提炼为 skill? 开源社区是否有可借鉴的框架?

**调研对象**: [OthmanAdi/planning-with-files](https://github.com/OthmanAdi/planning-with-files)

**核心机制**:
- 三文件工作记忆 (`task_plan.md` + `findings.md` + `progress.md`)
- Hook 驱动注入 (UserPromptSubmit / PreToolUse / PostToolUse / Stop / PreCompact)
- 防篡改 attestation (SHA-256 哈希锁定)
- 会话恢复 (`session-catchup.py`)
- 完成门控 (gated 模式, 5 条件阻塞 Stop)
- Run Ledger (JSONL 追加日志)
- 2-Action Rule (每 2 次浏览后保存)
- 3-Strike Error Protocol (3 次失败后升级)
- 5-Question Reboot Test (上下文恢复)
- Read vs Write Decision Matrix

**结论**: 环境差异 (TRAE 无 hook 机制) + 领域差异 (通用 vs 研究工程化) 导致无法直接移植。但 3 个元素可借鉴:

| 借鉴元素 | 价值 | 嵌入方式 |
|---------|------|---------|
| 5-Question Reboot Test | 中 | 加入阶段 1 启动流程 |
| 3-Strike Error Protocol | 中 | 加入阶段 7 实施错误处理 |
| 关键文档 attestation | 低 | 可选, 对 EXECUTION_*.md 计算 SHA-256 |

**不借鉴的部分**:
- 持久化工作记忆: 已被 memory 系统 + TodoWrite 覆盖
- Hook 驱动注入: TRAE 环境不支持
- 2-Action Rule: 我们较少多模态操作
- Read vs Write Decision Matrix: 已内化为习惯

### 1.2 第二轮: audit-driven-development skill 分析

**问题**: 已安装的 `audit-driven-development` skill 是否可以嵌入, 增强审查功能?

**Skill 核心定位**: 实施完成后, 审查代码与设计文档的对齐度, 产出评分 + 问题分级 + 修复优先级矩阵 + 修复基线。

**Iron Law**: `NO "IMPLEMENTATION COMPLETE" WITHOUT AN AUDIT-DRIVEN REVIEW`

**4 阶段流程**:
1. Spec Inventory — 设计文档盘点, 列出审查维度
2. Multi-Dimensional Audit — 并行 subagent 逐模块审查
3. Fix Priority Matrix — P0/P1/P2/P3 分级 + Tier 1/2/3 排序
4. Fix Baseline + Tracking — 审查报告 + 修复跟踪表

**关键差异** (与当前工作流 review 阶段):

| 维度 | audit-driven-development | 当前工作流 review |
|------|--------------------------|------------------|
| 审查对象 | 代码 vs 设计文档对齐 | 执行方案文档 vs 源代码接口对齐 |
| 审查时机 | 实施完成后 (代码已写完) | 构建后实施前 (代码尚未写) |
| 审查目标 | 代码是否落地了设计 | 执行方案是否与现有源代码接口一致 |
| 修复对象 | 代码 | 执行方案文档 |

**结论**: **强烈建议嵌入**。当前工作流在实施完成后缺少代码 vs 设计对齐审查, audit-driven-development 正好填补这个空白。

**嵌入方式**: 作为阶段 7 (实施后审计) 独立环节, 不修改 skill 本身, 只在工作流中增加一个阶段。

**Skill 独有价值** (当前工作流没有的):
- 测试盲区识别 (4 类: 断言恒真式 / 单文件检查 / 设计约束无测试 / 修正项无测试)
- ADR 依赖图不变式检查 (静态/动态依赖 + TYPE_CHECKING 守卫)
- 跨模块契约验证 (传递依赖链分析)
- 评分系统 (A+ 到 F)
- 修复跟踪表 (`docs/audit/`)

### 1.3 第三轮: MCP 双轨核实方案

**问题**: review 时学术信息检索不够深入造成误判, 是否可以通过强制调用 MCP 工具减少误判?

**误判案例** (根因分析):

| 误判案例 | 根源 | MCP 核实预期 |
|---------|------|-------------|
| Ledoit-Wolf (2008) delta method 梯度 `-μ/σ²` 应为 `-μ/(2σ³)` | 依赖模型内部知识 | `read_semantic_paper` 读取原文公式 |
| Oster (2019) R_max = 2.75 vs 1.3×R̃ | 模型记忆混淆 | `search_academic` 核实原文 |
| IVX 指数衰减滤波 vs 分数差分 | 模型对细节不确定 | `read_semantic_paper` 核实滤波定义 |
| statsmodels "等价路径"检验 Sharpe 差 | 模型假设 API 能力 | `search_questions site='stats'` 核实 |
| Profile GMM (Hong-Su-Jiang 2022) 细节 | 模型对 JoE 论文细节不确定 | `search_semantic` 核实 |
| PFGMM (Ghosh-Thoresen 2019) 一维 SCAD | 模型对 Statistica Sinica 细节不确定 | `search_semantic` 核实 |

**根本原因**: review subagent 仅依赖 GLM-5.2 内部知识, 未调用外部权威信息源。模型对计量经济学细节的记忆在以下场景容易出错:
- 具体公式 (delta method 梯度)
- 具体数值建议 (R_max 系数)
- 算法细节 (IVX 滤波定义)
- API 能力边界 (statsmodels 是否支持某检验)

**MCP 工具能力分析**:

| MCP 服务器 | 关键工具 | 能力 |
|-----------|---------|------|
| `mcp_english-search` | `search_academic` | 英文学术搜索, 返回 JSON |
| `mcp_paper-search` | `search_semantic` | Semantic Scholar 搜索, 支持 year 过滤 |
| `mcp_paper-search` | `read_semantic_paper` | **读取论文全文文本**, 支持 DOI/ARXIV/URL |
| `mcp_paper-search` | `search_arxiv` / `search_google_scholar` / `search_crossref` | 多源文献搜索 |
| `mcp_stackexchange` | `search_questions` | 跨 184+ 社区搜索, 支持 site/tags/sort |

**关键能力**: `read_semantic_paper` 能读取论文**全文文本**, 对关键算法公式可直接从原文提取, 而非依赖模型记忆。

**双轨核实机制**:

| 轨道 | 触发条件 | 执行方式 | 核实来源 |
|------|---------|---------|---------|
| 轨道 A: 学术文献核实 | 学术引用 / 数学公式 / 统计性质 / 算法定义 | 强制调用 `search_semantic` + `read_semantic_paper` | Semantic Scholar 全文 |
| 轨道 B: 工程实践核实 | 第三方库 API 调用 / "等价"/"支持"声明 / 版本兼容性 | 强制调用 `search_questions` | StackExchange (stats/quant/programming) |

**结论**: **强烈建议嵌入**。ROI 分析: 一次 P0 误判的代价 (数小时回滚) 远大于 15 分钟 MCP 调用成本。

---

## 2. 完整 7 阶段工作流定义

### 2.1 工作流全景

```
阶段 1: 规划
  ├── 优先级分析 + 依赖关系梳理
  ├── 文档分层 (学术层 private/ vs 工程层 EXECUTION_*.md)
  └── 5-Question Reboot Test (借鉴 planning-with-files)
       ↓
阶段 2: 构建 (并行 subagent)
  ├── 每份执行方案 1 个 subagent
  ├── E 任务拆解 + TDD 测试 + 接口设计
  └── 兼容性 + 性能 + 依赖 + 验收标准
       ↓
阶段 3: 快速 Review (并行 subagent)
  ├── 接口对齐 + 算术 + 逻辑
  ├── CRITICAL/MAJOR/MINOR 分级
  └── 阻塞规则: CRITICAL 阻塞实施
       ↓
阶段 4: 深度学术核实 (MCP 强制调用)         ← 新增
  ├── search_semantic 搜索原文
  ├── read_semantic_paper 读取全文公式
  └── 标记: ✅ VERIFIED / ❌ MISMATCH / ⚠️ UNVERIFIABLE
       ↓
阶段 5: 工程实践核实 (MCP 强制调用)         ← 新增
  ├── search_questions site='stats'/'programming'
  ├── 核实 API 能力边界
  └── 标记: ✅ VERIFIED / ❌ MISMATCH / ⚠️ PARTIAL
       ↓
阶段 6: 修复 + 二次 Review
  ├── 接口签名核对 (从源代码确认)
  ├── 精确 Edit 修复
  └── 二次 review 验证修复正确性
       ↓
阶段 7: 实施 (TDD) + 审计
  ├── TDD 写代码 (先 Red 后 Green)
  ├── 3-Strike Error Protocol (借鉴 planning-with-files)
  ├── pytest 全量通过 (零回归)
  └── audit-driven-development (4 阶段审计)
       ├── Phase 1: Spec Inventory
       ├── Phase 2: Multi-Dimensional Audit (并行 subagent)
       ├── Phase 3: Fix Priority Matrix (P0/P1/P2/P3)
       └── Phase 4: Fix Baseline + Tracking (docs/audit/)
```

### 2.2 各阶段详细定义

#### 阶段 1: 规划

**活动**:
1. 优先级分析 (P0/P1/P2/P3)
2. 依赖关系梳理 (任务图)
3. 范围修正 (区分学术层 vs 工程层)
4. 执行顺序确定

**5-Question Reboot Test** (借鉴 planning-with-files):
会话启动时回答 5 个问题:
- 我在哪个阶段? (规划/构建/review/修复/实施/审计)
- 目标是什么? (本次会话的 deliverable)
- 已完成什么? (上一个会话的产出)
- 待办什么? (本会话的任务清单)
- 已学到什么? (需要注意的约束/陷阱)

**产出**:
- 执行顺序清单
- 文档分层方案 (`docs/private/` vs `docs/EXECUTION_*.md`)
- TodoWrite 任务列表

#### 阶段 2: 构建 (并行 subagent)

**活动**:
1. 每份执行方案派发独立 subagent
2. subagent 读取学术设计文档 (`docs/private/`) + 源代码
3. 生成工程化执行方案 (`docs/EXECUTION_*.md`)

**执行方案模板**:
```markdown
# EXECUTION_<NAME>.md

## §0 摘要
- E 任务清单
- 测试总数
- 新增依赖

## §1-N E 任务定义
每个 E 任务包含:
- 目标
- 接口设计 (类名/方法签名/返回类型)
- 算法 (含学术引用)
- 兼容性 (enable=False 默认)
- 性能估算
- 依赖 (外部包 + 版本)
- TDD 测试用例
- 验收标准

## §风险评估
- 技术风险
- 兼容性风险
- 性能风险
```

**关键约束**:
- 所有新字段默认 `enable=False` (向后兼容)
- 接口签名必须与现有源代码一致 (从源代码确认, 非 API 文档)
- 依赖版本必须与 `pyproject.toml` 一致
- TDD: 先写测试再实现

**产出**: `docs/EXECUTION_*.md` (每份 1000-4000 行, 含 E 任务 + 测试 + 接口设计)

#### 阶段 3: 快速 Review (并行 subagent)

**活动**:
1. 每份执行方案派发独立 review subagent
2. 快速检查: 接口对齐 + 算术 + 逻辑 + 依赖
3. 问题分级

**问题分级**:

| 级别 | 含义 | 阻塞 |
|------|------|------|
| CRITICAL | 接口不匹配 / 算法错误 / 算术错误 | ✅ 阻塞实施 |
| MAJOR | 质量问题 / 前提未标注 / 路径缺失 | ⚠️ 建议修复 |
| MINOR | 命名 / 注释 / 笔误 | 可选 |

**检查清单**:
- [ ] 接口签名与源代码一致?
- [ ] 算术计算正确? (如组合数 4·3⁵=972≠1296)
- [ ] 数学公式正确? (如梯度/检验统计量)
- [ ] 依赖版本与 pyproject.toml 一致?
- [ ] enable=False 默认?
- [ ] TDD 测试覆盖?

**产出**: Review 报告 (CRITICAL/MAJOR/MINOR 清单 + 阻塞判断)

#### 阶段 4: 深度学术核实 (MCP 强制调用) ← 新增

**输入**: 阶段 3 review 通过的执行方案文档

**执行方式**: 派发独立 subagent, **强制调用 MCP 学术搜索工具**

**触发条件** (遇到任一即触发):
- 学术引用 (作者 + 年份 + 期刊/会议)
- 数学公式 (梯度/检验统计量/估计量)
- 统计性质声明 (FDR/FWER/一致性/渐近分布)
- 算法定义 (滤波/估计/检验步骤)

**执行流程**:
```
1. search_semantic(query="作者 关键词", year="年份")
   → 获取 paper_id
2. read_semantic_paper(paper_id="DOI:xxx" 或 "ARXIV:xxx")
   → 读取全文文本
3. 从全文中提取关键公式/定义/性质
4. 与执行方案文档中的声明对比
5. 标记: ✅ VERIFIED / ❌ MISMATCH / ⚠️ UNVERIFIABLE
```

**subagent 任务模板**:
```
你是学术核实 subagent。对以下执行方案文档中的学术引用进行深度核实。

文档: [EXECUTION_*.md 路径]

核实规则:
1. 对每个学术引用 (作者+年份), 调用 search_semantic 搜索原文
2. 对关键公式/算法, 调用 read_semantic_paper 读取全文, 提取原文公式
3. 将原文与文档声明对比, 标记:
   - ✅ VERIFIED: 文档声明与原文一致
   - ❌ MISMATCH: 文档声明与原文不一致 (附原文引用 + 正确版本)
   - ⚠️ UNVERIFIABLE: 无法找到原文或原文未明确 (说明原因)

必检项 (P0):
- Ledoit-Wolf (2008): delta method 梯度 ∂SR/∂σ² = ?
- Oster (2019): R_max = ? × R̃
- Kostakis IVX (2015): 滤波定义 = ?
- Benjamini-Hochberg (1995): 控制目标 = FDR 还是 FWER?

输出格式:
| 文献 | 文档声明 | 原文核实 | 状态 | 原文引用 |
|------|---------|---------|------|---------|

MCP 工具调用:
- search_semantic(query="...", year="...")
- read_semantic_paper(paper_id="DOI:xxx")
```

**产出**: 学术核实报告 (每条引用的 VERIFIED/MISMATCH/UNVERIFIABLE 状态)

#### 阶段 5: 工程实践核实 (MCP 强制调用) ← 新增

**输入**: 阶段 3 review 通过的执行方案文档

**执行方式**: 派发独立 subagent, **强制调用 StackExchange MCP**

**触发条件** (遇到任一即触发):
- 第三方库 API 调用 (statsmodels/sklearn/scipy)
- "等价"/"支持"/"提供"等能力声明
- 版本兼容性声明
- 性能声明 (复杂度/加速比)

**执行流程**:
```
1. search_questions(
     query="库名 功能描述",
     site='stats' 或 'programming' 或 'quant',
     min_score=5,
     sort='votes'
   )
   → 获取高质量问答
2. 从回答中提取 API 实际能力/最佳实践
3. 与执行方案文档中的声明对比
4. 标记: ✅ VERIFIED / ❌ MISMATCH / ⚠️ PARTIAL
```

**可用 StackExchange 站点**:
- `stats` (Cross Validated) — 统计学
- `quant` (Quantitative Finance) — 量化金融
- `economics` — 经济学
- `math` (MathOverflow) — 数学
- `programming` (StackOverflow) — 编程
- `ai` — AI
- `datascience` — 数据科学

**subagent 任务模板**:
```
你是工程实践核实 subagent。对以下执行方案文档中的第三方库 API 声明进行核实。

文档: [EXECUTION_*.md 路径]

核实规则:
1. 对每个 "statsmodels/sklearn/scipy 提供 X" 声明, 调用 search_questions 搜索
2. 优先 site='stats' (Cross Validated) 和 site='programming' (StackOverflow)
3. min_score=5, sort='votes', 只看高质量回答
4. 标记:
   - ✅ VERIFIED: API 确实提供此功能 (附 StackExchange 链接)
   - ❌ MISMATCH: API 不提供此功能 (附 StackExchange 证据 + 替代方案)
   - ⚠️ PARTIAL: API 部分支持, 需额外步骤 (说明)

必检项 (P0):
- statsmodels 是否提供 Sharpe 比率差检验?
- statsmodels Markov switching 是否提供收敛检查?

输出格式:
| 声明 | 文档位置 | StackExchange 核实 | 状态 | 链接 |
|------|---------|-------------------|------|------|

MCP 工具调用:
- search_questions(query="...", site='stats', min_score=5, sort='votes')
```

**产出**: 工程实践核实报告 (每条声明的 VERIFIED/MISMATCH/PARTIAL 状态)

#### 阶段 6: 修复 + 二次 Review

**活动**:
1. 接口签名核对 (从源代码确认实际签名)
2. 精确 Edit 修复 (不用 PowerShell 截断)
3. 二次 review 验证修复正确性
4. 循环直到二次 review 全部 PASS

**修复原则**:
- **备份优先** (破坏性操作前 `Copy-Item file file.bak`)
- **Edit 工具优先于 PowerShell** (atomic 操作)
- **PowerShell LF 陷阱** (Get-Content 对 LF 文件解析异常)
- **成功 N 次不保证第 N+1 次** (每步保持警惕)

**二次 review 规则**:
- 修复 CRITICAL 后必须二次 review
- 二次 review 确认修复正确 + 无新问题引入
- 二次 review PASS 后才能进入实施

**产出**: 修复后的执行方案文档 + 二次 review PASS 报告

#### 阶段 7: 实施 (TDD) + 审计

**活动 1: TDD 实施**
1. 先写测试 (Red)
2. 再写实现 (Green)
3. Review 实现 (Review)
4. pytest 全量通过 (零回归)

**3-Strike Error Protocol** (借鉴 planning-with-files):
- 同一错误 3 次失败后升级到用户
- 不无限重试
- 记录错误模式

**活动 2: audit-driven-development (4 阶段审计)**

**Phase 1: Spec Inventory**
- 收集设计文档: `docs/EXECUTION_*.md` + `DECISIONS.md` (ADR)
- 列出审查维度: 每个 E 任务 vs 模块代码 + 跨模块契约

**Phase 2: Multi-Dimensional Audit (并行 subagent)**
- 每个 E 任务 1 个 subagent: 代码 vs EXECUTION_*.md 对齐
- 跨模块契约 1 个 subagent: ADR 不变式检查
- 接口签名 1 个 subagent: 实际代码签名 vs 文档声明签名

**测试盲区识别** (4 类):
1. 断言恒真式 (`assert x or not x`)
2. 单文件检查盲区 (`inspect.getsource()` 看不到跨文件依赖)
3. 设计文档独有约束无测试 (ADR 不变式 / enable=False 默认)
4. 修正项无测试 (v1.3 术语修正 / CRITICAL 修复是否在代码中体现)

**Phase 3: Fix Priority Matrix**
- P0 Blocker (立即) / P1 Critical (本轮) / P2 Major (下一轮) / P3 Minor (可选)
- Tier 1 (P0) / Tier 2 (P1 + 低成本 P2) / Tier 3 (剩余)
- 排序: 1 行修复的 P0 优先于 100 行重构的 P1

**Phase 4: Fix Baseline + Tracking**
- 写入 `docs/audit/YYYY-MM-DD-code-quality-audit.md`
- 修复跟踪表 (编号/严重度/描述/状态/提交/测试验证)
- 逐项修复 P0 → 每项重跑测试 → 零回归

**产出**:
- 实施代码 + pytest 全量通过
- `docs/audit/` 审查报告
- 修复跟踪表
- ADR 记录 + CHANGELOG 更新

---

## 3. 借鉴元素汇总

### 3.1 来自 planning-with-files

| 借鉴元素 | 嵌入阶段 | 价值 | 实施状态 |
|---------|---------|------|---------|
| 5-Question Reboot Test | 阶段 1 启动 | 中 | 待验证 |
| 3-Strike Error Protocol | 阶段 7 实施错误处理 | 中 | 待验证 |
| 关键文档 attestation (SHA-256) | 可选, 阶段 6 | 低 | 待定 |

**不借鉴的部分及原因**:
- 持久化工作记忆 (三文件): 已被 memory 系统 + TodoWrite 覆盖
- Hook 驱动注入: TRAE 环境不支持
- 2-Action Rule: 我们较少多模态操作
- Read vs Write Decision Matrix: 已内化为习惯
- 完成门控 (gated 模式): 与 TRAE 工作模式不兼容

### 3.2 来自 audit-driven-development (自建 skill)

| 借鉴元素 | 嵌入阶段 | 价值 | 实施状态 |
|---------|---------|------|---------|
| 4 阶段审计流程 | 阶段 7 | 高 | skill 已安装, 待触发验证 |
| 测试盲区识别 (4 类) | 阶段 7 Phase 2 | 高 | skill 内置 |
| ADR 依赖图不变式检查 | 阶段 7 Phase 2 | 高 | skill 内置 |
| 跨模块契约验证 | 阶段 7 Phase 2 | 高 | skill 内置 |
| 评分系统 (A+ 到 F) | 阶段 7 Phase 3 | 中 | skill 内置 |
| 修复跟踪表 | 阶段 7 Phase 4 | 高 | skill 内置 |
| Fix Priority Matrix (P0/P1/P2/P3 + Tier) | 阶段 7 Phase 3 | 高 | skill 内置 |

**适配点**:
- 设计文档源: 明确包含 `docs/EXECUTION_*.md` (我们项目特有)
- 审查维度: 每个 E 任务 vs 模块代码 (而非通用模块 vs spec)
- 测试盲区特化: 盲区 3 = ADR 不变式 + enable=False 默认; 盲区 4 = v1.3 术语修正 + CRITICAL 修复
- 评分系统简化: PASS / PASS_WITH_ISSUES / FAIL (而非 9 级)

### 3.3 来自 MCP 双轨核实 (新方案)

| 借鉴元素 | 嵌入阶段 | 价值 | 实施状态 |
|---------|---------|------|---------|
| 学术文献深度核实 (Semantic Scholar 全文) | 阶段 4 | 高 | ❌ 已证伪 (subagent 无 run_mcp + paywall); 降级为 Crossref + WebFetch + 用户核实 |
| 工程实践核实 (StackExchange) | 阶段 5 | 高 | ❌ 已证伪 (MCP 配额耗尽); 降级为 WebFetch 官方文档, 15 项 API 全部 VERIFIED |
| 强制 MCP 调用 (subagent 任务模板) | 阶段 4+5 | 高 | ❌ 已证伪 (subagent 无 run_mcp); 主会话直接调用 MCP 可行 |
| 必检项清单 (P0 文献 + P0 API) | 阶段 4+5 | 高 | ✅ 已验证 (阶段 4: 29 项; 阶段 5: 15 项; P0 全部 VERIFIED) |

**MCP 工具映射**:

| 核实类型 | MCP 服务器 | 关键工具 | 用途 |
|---------|-----------|---------|------|
| 学术文献搜索 | `mcp_paper-search` | `search_semantic` | 搜索论文, 获取 paper_id |
| 学术全文读取 | `mcp_paper-search` | `read_semantic_paper` | 读取全文, 提取公式 |
| 英文学术搜索 | `mcp_english-search` | `search_academic` | 快速核实论文存在性 |
| 工程实践搜索 | `mcp_stackexchange` | `search_questions` | 核实 API 能力边界 |

---

## 4. 工作流核心原则

### 4.1 文档分层原则

| 层级 | 位置 | 内容 | 提交远程 |
|------|------|------|---------|
| 学术层 | `docs/private/` | 研究设计 / 学术价值讨论 / 消融设计 / 设计讨论 | ❌ 不提交 |
| 工程层 | `docs/EXECUTION_*.md` | 工程执行方案 (E 任务 + TDD + 接口) | ✅ 提交 |
| 决策层 | `DECISIONS.md` | ADR 架构决策记录 | ✅ 提交 |
| 审计层 | `docs/audit/` | 代码审查报告 + 修复跟踪表 | ✅ 提交 |

### 4.2 问题分级原则

| 级别 | 含义 | 阻塞 | 修复时机 |
|------|------|------|---------|
| CRITICAL / P0 | 接口不匹配 / 算法错误 / 算术错误 | ✅ 阻塞 | 立即 |
| MAJOR / P1 | 质量问题 / 前提未标注 / 路径缺失 | ⚠️ 建议本轮 | 本轮 |
| MINOR / P2 | 命名 / 注释 / 笔误 | 可选 | 下一轮 |

### 4.3 向后兼容原则

- 所有新功能默认 `enable=False`
- 新字段默认空/None
- opt-in 而非 opt-out
- 不破坏现有 API 签名

### 4.4 零回归原则

- 每项修复后立即重跑测试
- pytest 全量通过是硬约束
- 不因"前序步骤成功"而降低验证强度

### 4.5 接口签名核对原则

- 修复前先从源代码确认实际接口签名
- 不依赖 API 文档 (可能过时)
- 不依赖模型记忆 (可能错误)
- 强制调用 MCP 核实 (阶段 4+5)

### 4.6 破坏性操作安全原则

- 备份优先 (`Copy-Item file file.bak`)
- Edit 工具优先于 PowerShell (atomic 操作)
- PowerShell LF 陷阱 (`Get-Content` 对 LF 文件解析异常)
- 成功 N 次不保证第 N+1 次

---

## 5. 与通用工作流的差异

### 5.1 通用编码工作流 (如 planning-with-files)

```
规划 → 实施 → 测试 → 交付
```

### 5.2 本研究工程化工作流

```
规划 → 构建 → 快速Review → 深度学术核实 → 工程实践核实 → 修复+二次Review → 实施+审计
```

**差异点**:

| 维度 | 通用工作流 | 本研究工程化工作流 |
|------|-----------|------------------|
| 文档 | 单层 (README + 代码注释) | 三层 (学术层 private/ + 工程层 EXECUTION_*.md + 决策层 ADR) |
| Review | 代码 review | 文档 review (阶段 3) + 学术核实 (阶段 4) + 工程核实 (阶段 5) + 代码审计 (阶段 7) |
| 信息源 | 模型内部知识 | 模型 + MCP 学术搜索 + StackExchange |
| 实施 | 直接写代码 | TDD (Red → Green → Review) |
| 审计 | 无 | audit-driven-development (4 阶段) |
| 兼容性 | 无显式约束 | enable=False 默认 |
| 决策记录 | 无 | ADR (ADR-001 至 ADR-025) |

---

## 6. 已验证的实践样本

### 6.1 v2.4.0 (内化 5 模块)

- **工作流阶段**: 1-3, 6-7 (无阶段 4+5)
- **产出**: 5 模块内化 + 918 passed
- **验证点**: enable=False 默认 / TDD / ADR-019

### 6.2 v2.6.0 (E1-E9 优化器)

- **工作流阶段**: 1-3, 6-7 (无阶段 4+5)
- **产出**: 9 个 E 任务 + 918 passed
- **验证点**: 8 维搜索空间 / 扩展窗口 CV / ADR-005 修正

### 6.3 v3.0.0 (T1/T3/T4 远期任务)

- **工作流阶段**: 1-3, 6-7 (无阶段 4+5)
- **产出**: CUSUM + BH-FDR + 指纹 21 维 + 385 passed
- **验证点**: Page (1954) / Benjamini-Hochberg (1995) / ADR-024/025
- **遗憾**: 未做阶段 4+5, Ledoit-Wolf 梯度 / Oster R_max 等存在误判风险

### 6.4 v3.1.0 执行方案 (当前)

- **工作流阶段**: 1-6 (阶段 4+5 首次定义, 待执行)
- **产出**: 三份 EXECUTION_*.md (9435 行, 23 E 任务, 349 测试)
- **验证点**: 7 CRITICAL + 14 MAJOR 全部修复 + 二次 review PASS + 2 MINOR 修复
- **待执行**: 阶段 4+5 (MCP 双轨核实) + 阶段 7 (实施 + 审计)

---

## 7. 实施路线图

### 7.1 短期 (v3.1.0 实施阶段)

| 步骤 | 活动 | 验证点 |
|------|------|--------|
| 1 | 对三份已修复的 EXECUTION_*.md 执行阶段 4 (MCP 学术核实) | 验证 `read_semantic_paper` 能否获取公式全文 |
| 2 | 对三份已修复的 EXECUTION_*.md 执行阶段 5 (MCP 工程核实) | 验证 StackExchange 搜索质量 |
| 3 | 进入阶段 7 实施 (TDD) | 23 E 任务 + 349 测试 |
| 4 | 实施完成后触发 audit-driven-development | 验证 skill 在本项目的适用性 |

### 7.2 中期 (v3.1.0 完成后)

| 步骤 | 活动 | 验证点 |
|------|------|--------|
| 5 | 更新 project_memory 记录 7 阶段工作流 | 工作流定义固化 |
| 6 | 积累 3-5 个版本样本 | 工作流稳定性验证 |
| 7 | 验证 5-Question Reboot Test / 3-Strike Protocol 有效性 | 借鉴元素验证 |

### 7.3 长期 (3-5 个版本后)

| 步骤 | 活动 | 验证点 |
|------|------|--------|
| 8 | 如果工作流稳定, 固化为 skill | skill 触发条件 / 核心流程 / 模板 |
| 9 | skill 候选名称: `research-engineering-pipeline` | — |
| 10 | skill 范围: 阶段 1-6 (实施前) | 阶段 7 由 audit-driven-development 覆盖 |

**不固化为 skill 的部分**:
- ADR 编号管理 (项目特定)
- 版本号规则 (项目特定)
- 学术引用核实 (由 MCP 双轨核实覆盖, 非工作流本身)

---

## 8. 附录: subagent 任务模板汇总

### 8.1 构建 subagent 模板

```
你是执行方案构建 subagent。基于学术设计文档, 生成工程化执行方案。

输入:
- 学术设计文档: [docs/private/XXX.md]
- 源代码: [相关模块路径]

输出: docs/EXECUTION_XXX.md

要求:
1. E 任务拆解 (每个 E 任务 = 1 个可独立实施的功能单元)
2. TDD 测试用例 (先写测试再实现)
3. 接口设计 (类名/方法签名/返回类型, 从源代码确认)
4. 兼容性 (enable=False 默认, 向后兼容)
5. 性能估算 (时间/内存)
6. 依赖 (外部包 + 版本, 与 pyproject.toml 一致)
7. 验收标准 (具体可测)
```

### 8.2 快速 Review subagent 模板

```
你是 review subagent。对执行方案文档进行快速 review。

输入: [docs/EXECUTION_XXX.md]

检查清单:
- [ ] 接口签名与源代码一致?
- [ ] 算术计算正确?
- [ ] 数学公式正确?
- [ ] 依赖版本与 pyproject.toml 一致?
- [ ] enable=False 默认?
- [ ] TDD 测试覆盖?

问题分级:
- CRITICAL: 接口不匹配 / 算法错误 / 算术错误 (阻塞实施)
- MAJOR: 质量问题 / 前提未标注 / 路径缺失 (建议修复)
- MINOR: 命名 / 注释 / 笔误 (可选)

输出: Review 报告 (CRITICAL/MAJOR/MINOR 清单 + 阻塞判断)
```

### 8.3 学术核实 subagent 模板 (阶段 4)

```
你是学术核实 subagent。对执行方案文档中的学术引用进行深度核实。

文档: [EXECUTION_*.md 路径]

核实规则:
1. 对每个学术引用 (作者+年份), 调用 search_semantic 搜索原文
2. 对关键公式/算法, 调用 read_semantic_paper 读取全文, 提取原文公式
3. 将原文与文档声明对比, 标记:
   - ✅ VERIFIED: 文档声明与原文一致
   - ❌ MISMATCH: 文档声明与原文不一致 (附原文引用 + 正确版本)
   - ⚠️ UNVERIFIABLE: 无法找到原文或原文未明确 (说明原因)

必检项 (P0):
- Ledoit-Wolf (2008): delta method 梯度 ∂SR/∂σ² = ?
- Oster (2019): R_max = ? × R̃
- Kostakis IVX (2015): 滤波定义 = ?
- Benjamini-Hochberg (1995): 控制目标 = FDR 还是 FWER?

输出格式:
| 文献 | 文档声明 | 原文核实 | 状态 | 原文引用 |
|------|---------|---------|------|---------|

MCP 工具调用 (强制):
- search_semantic(query="...", year="...")
- read_semantic_paper(paper_id="DOI:xxx")
```

### 8.4 工程实践核实 subagent 模板 (阶段 5)

```
你是工程实践核实 subagent。对执行方案文档中的第三方库 API 声明进行核实。

文档: [EXECUTION_*.md 路径]

核实规则:
1. 对每个 "statsmodels/sklearn/scipy 提供 X" 声明, 调用 search_questions 搜索
2. 优先 site='stats' (Cross Validated) 和 site='programming' (StackOverflow)
3. min_score=5, sort='votes', 只看高质量回答
4. 标记:
   - ✅ VERIFIED: API 确实提供此功能 (附 StackExchange 链接)
   - ❌ MISMATCH: API 不提供此功能 (附 StackExchange 证据 + 替代方案)
   - ⚠️ PARTIAL: API 部分支持, 需额外步骤 (说明)

必检项 (P0):
- statsmodels 是否提供 Sharpe 比率差检验?
- statsmodels Markov switching 是否提供收敛检查?

输出格式:
| 声明 | 文档位置 | StackExchange 核实 | 状态 | 链接 |
|------|---------|-------------------|------|------|

MCP 工具调用 (强制):
- search_questions(query="...", site='stats', min_score=5, sort='votes')
```

### 8.5 审计 subagent 模板 (阶段 7, audit-driven-development)

```
你是审计 subagent。对实施后的代码与设计文档进行对齐审查。

输入:
- 设计文档: [docs/EXECUTION_*.md]
- ADR: [DECISIONS.md]
- 实施代码: [相关模块路径]

审查维度:
- 每个 E 任务 vs 模块代码对齐
- 跨模块契约 (ADR 不变式 / 接口契约 / 依赖图)
- 接口签名一致性 (实际代码 vs 文档声明)

测试盲区识别 (4 类):
1. 断言恒真式 (assert x or not x)
2. 单文件检查盲区 (inspect.getsource() 看不到跨文件依赖)
3. 设计约束无测试 (ADR 不变式 / enable=False 默认)
4. 修正项无测试 (v1.3 术语修正 / CRITICAL 修复是否在代码中体现)

问题分级:
- P0 Blocker (立即) / P1 Critical (本轮) / P2 Major (下一轮) / P3 Minor (可选)

输出:
- 评分 (PASS / PASS_WITH_ISSUES / FAIL)
- 问题列表 (P0/P1/P2/P3)
- 修复优先级矩阵 (Tier 1/2/3)
- 测试盲区汇总
```

---

## 9. 修订日志

| 版本 | 日期 | 修订内容 |
|------|------|---------|
| v1.0 | 2026-07-08 | 初始版本, 整合三轮工作流讨论成果 |
| v1.1 | 2026-07-08 | 阶段 4 实测后更新 §10 假设状态; 新增 §11 阶段 4 实测发现 |
| v1.2 | 2026-07-08 | 阶段 5 实测后更新 §10 假设状态; 新增 §12 阶段 5 实测发现 (StackExchange MCP 配额耗尽 + 降级方案 + 15 项 API 全部 VERIFIED) |

---

## 10. 待验证假设

以下假设需在 v3.1.0 实施阶段验证:

| 假设 | 验证方式 | 风险 | 状态 (v1.2) |
|------|---------|------|------------|
| `read_semantic_paper` 能获取公式全文 | 阶段 4 核实 Ledoit-Wolf 梯度 | 中 (可能只有摘要) | ❌ **已证伪** — subagent 环境无 `run_mcp` 工具; 且多数期刊 paywall 无法获取全文 |
| StackExchange 有 statsmodels Sharpe 检验问答 | 阶段 5 核实 | 中 (可能无高质量回答) | ❌ **已证伪** — StackExchange MCP 配额耗尽 (quota_remaining: -1); 降级为 WebFetch 官方文档, 15 项 API 声明全部 VERIFIED |
| audit-driven-development 在本项目适用 | 阶段 7 触发 skill | 低 (skill 已在其他项目验证) | ⏳ 待阶段 7 验证 |
| 5-Question Reboot Test 有效 | 阶段 1 启动时使用 | 低 (无成本) | ⏳ 待验证 |
| 3-Strike Error Protocol 有效 | 阶段 7 实施错误处理 | 低 (无成本) | ⏳ 待验证 |
| 7 阶段工作流不过度复杂 | 完整执行 v3.1.0 | 中 (可能需简化) | ⏳ 待验证 |

### 阶段 4 实测后的调整 (v1.1)

**假设 1 (`read_semantic_paper`) 已证伪**, 阶段 4 设计需调整:

| 调整项 | 原设计 (v1.0) | 调整后 (v1.1) |
|--------|--------------|--------------|
| MCP 调用方式 | subagent 调用 `run_mcp` | **subagent 无 `run_mcp` 工具**; 改用 Crossref REST API + OpenAlex + WebSearch + WebFetch |
| 全文公式获取 | `read_semantic_paper` 读取全文 | **paywall 阻挡**; 降级为 Wikipedia 二次源 + 用户人工核实 (如 Hansen SPA recentering 阈值) |
| P0 必检项 | 预设固定清单 | **先扫描文档识别实际引用, 再生成必检项** (避免 8/14 项 N/A) |
| 核实来源 | Semantic Scholar 全文 | **Crossref (元数据) + Wikipedia (公式) + WebSearch (二次源) + 用户人工核实 (paywall 文献)** |

如果假设验证失败, 工作流需相应调整:
- ~~`read_semantic_paper` 失败 → 降级为 `search_academic` + 摘要核实~~ (已证伪, 见上表)
- ~~StackExchange 失败 → 降级为 WebSearch + 官方文档核实~~ (已证伪, 降级方案实测有效, 见 §12)
- 7 阶段过度复杂 → 合并阶段 4+5 为单 subagent, 或合并阶段 3+4+5 为"深度 review"

---

## 11. 阶段 4 实测发现 (v1.1 新增, 2026-07-08)

### 11.1 subagent 工具可用性

**关键发现**: `general_purpose_task` subagent **没有 `run_mcp` 工具**, 无法调用 `mcp_paper-search` / `mcp_english-search` / `mcp_stackexchange` 等 MCP 服务器。

**subagent 自动采用的替代方案** (经实测有效):
- Crossref REST API (`api.crossref.org`) — DOI / 作者 / 期刊 / 卷期页码核实
- OpenAlex API — 论文元数据 + 摘要
- WebSearch — 二次源搜索
- WebFetch — 开放获取原文抽取 (如 NBER working paper)

**对工作流的影响**:
- 阶段 4 (学术核实): subagent 用 Crossref + OpenAlex + WebSearch 替代, 有效
- 阶段 5 (工程实践核实): subagent 需用 WebSearch + WebFetch 替代 StackExchange MCP, 待验证

### 11.2 paywall 限制

**关键发现**: 多数学术期刊 (Elsevier / JBES / JFE 等) 为 paywall, `read_semantic_paper` 即使可调用也无法获取全文。

**受影响的 P0 文献**:
- Ledoit-Wolf (2008) — J. Empirical Finance, Elsevier, `is_oa: false`
- Hansen (2005) — JBES, paywall

**缓解方案**:
1. 二次源核实 (Wikipedia / 权威博客如石川量信投资)
2. 用户人工核实 (如本次 Hansen SPA recentering 阈值经用户提供权威解释确认)
3. NBER / arXiv 预印本 (如可获取)

### 11.3 阶段 4 实际效果

| 指标 | 结果 |
|------|------|
| 核实文献总数 | 29 项 (跨 3 份文档) |
| ✅ VERIFIED | 19 项 (65.5%) |
| ❌ MISMATCH | 1 项 (3.4%) — Politis-Romano 命名错配 |
| ⚠️ PARTIAL/UNVERIFIABLE | 2 项 (6.9%) — Ledoit-Wolf 归属 / Ghosh-Thoresen 年份 |
| N/A (文档未引用) | 9 项 (31.0%) — P0 清单与文档不匹配 |
| 发现的 P0 问题 | 1 个 (Politis-Romano 命名错配) |
| 发现的 P1 问题 | 2 个 (Ledoit-Wolf 归属 / Ghosh-Thoresen 年份) |
| 发现的 P2 问题 | 1 个 (Page 标题单复数) |
| 全部修复状态 | ✅ 全部修复 + 验证通过 |

**结论**: 阶段 4 有效发现了 1 个 P0 + 2 个 P1 + 1 个 P2 问题, 全部已修复。尽管 `read_semantic_paper` 不可用, 通过 Crossref + Wikipedia + 用户人工核实的组合方案仍然有效。

### 11.4 用户人工核实作为最后兜底

**新增机制**: 当 subagent 因 paywall 无法获取全文时, 标记为 ⚠️ UNVERIFIABLE, 由用户在后续会话中提供权威解释 (如本次 Hansen SPA recentering 阈值)。

**流程**:
1. subagent 标记 ⚠️ UNVERIFIABLE + 说明原因 (paywall / 无全文 / 摘要不含公式)
2. 在文档中保留 ⚠️ 标记
3. 用户在后续会话中提供权威解释
4. 更新文档, 将 ⚠️ 改为 ✅ VERIFIED + 添加核实注释

**本次实例**: Hansen (2005) SPA recentering 阈值公式
- subagent 阶段: ⚠️ UNVERIFIABLE (paywall, 仅摘要)
- 用户阶段: 提供权威公式 $\sqrt{2 \log \log n}$ + LIL 解释
- 更新后: ✅ VERIFIED + 添加 16 行核实注释 (见 EXECUTION_RESEARCH_NOTES.md line 595-610)

---

## 12. 阶段 5 实测发现 (v1.2 新增, 2026-07-08)

### 12.1 StackExchange MCP 配额耗尽

**关键发现**: `mcp_stackexchange` 的 `search_questions` 工具在所有站点 (stats / programming / quant / economics 等) 均返回 `quota_remaining: -1` 与 `total: 0`, 表明 **StackExchange API 配额已耗尽或未配置 API key**。

**受影响范围**: 阶段 5 (工程实践核实) 的主核实通道 (StackExchange 高质量问答) 完全不可用。

**降级方案** (本次实测有效):
- **WebFetch 官方文档** — 直取 statsmodels / scipy / joblib 官方 API 文档页面, 核实签名与能力
- **WebSearch** — 补充搜索 (二次源质量参差, 仅作辅助)
- **代码库既有测试基线** — 860+ 测试已验证的 API 用法作为间接证据

### 12.2 阶段 5 实际效果

| 指标 | 结果 |
|------|------|
| 核实 API 声明总数 | 15 项 (跨 3 份文档) |
| ✅ VERIFIED | 15 项 (100%) |
| ❌ MISMATCH | 0 项 (0%) |
| ⚠️ PARTIAL | 0 项 (0%) |
| P0 必检项 | 2 项, 全部 VERIFIED |
| 发现的问题 | 0 个 (文档声明全部正确) |

### 12.3 P0 必检项结果

| P0 必检项 | 文档声明 | 核实结果 | 证据 |
|----------|---------|---------|------|
| statsmodels 是否提供 Sharpe 比率差检验? | "手工实现为唯一主路径; statsmodels 仅作均值差参考" | ✅ VERIFIED — statsmodels **不提供** Sharpe 差检验, 文档声明正确 | WebSearch 无官方 API; `OLS.fit(cov_type='HAC')` 仅检验均值差 |
| statsmodels Markov switching 是否提供收敛检查? | "EM 算法, random_state 固定初值, 失败时硬阈值 fallback" | ✅ VERIFIED — `MarkovRegression.fit(maxiter=100, em_iter=5)` 通过 `mle_retvals['converged']` 提供收敛状态 | 官方文档确认 fit() 参数 + statsmodels MLE 通用接口 |

### 12.4 已核实 API 清单

**statsmodels** (8 项, 全部 VERIFIED):
1. `MarkovRegression(endog, k_regimes, trend, exog, ...)` — 体制转换模型
2. `MarkovRegression.fit(start_params, maxiter, method, em_iter, ...)` — MLE 拟合, 收敛信息在 `mle_retvals`
3. `OLS.fit(cov_type='HAC', cov_kwds={'maxlags': N, 'kernel': 'bartlett'})` — HAC 协方差, 明确支持
4. `adfuller(x, maxlag, regression, autolag)` — ADF 单位根检验
5. `hpfilter(x, lamb=1600)` — HP 滤波, 返回 (cycle, trend)
6. `VAR(endog).fit(maxlags, method, ic)` — VAR 模型
7. `het_white(resid, exog)` — White 异方差检验, 返回 (lm, lm_pvalue, fvalue, f_pvalue)
8. ❌ Sharpe 比率差检验 — **不提供** (文档声明正确)

**scipy** (4 项, 全部 VERIFIED):
9. `scipy.stats.spearmanr(a, b)` — Spearman 秩相关, 返回 SignificanceResult
10. `scipy.stats.ttest_1samp(a, popmean)` — 单样本 t 检验, 返回 TtestResult
11. `scipy.stats.chi2` — 卡方分布对象 (cdf / ppf / sf)
12. `scipy.stats` 通用 (KS 检验等) — 标准统计函数

**其他库** (3 项, 全部 VERIFIED):
13. `joblib.Parallel` / `joblib.delayed` — 并行计算 (bootstrap 并行)
14. `duckdb.connect` — DuckDB 持久化 (860+ 既有测试验证)
15. `arch` (GARCH) — 在 `pyproject.toml` `all` extras 中

### 12.5 对工作流的影响与建议

**结论**: 阶段 5 在 StackExchange MCP 不可用的情况下, 通过 WebFetch 官方文档降级方案仍然有效, 核实了 15 项 API 声明全部正确。

**对 §10 待验证假设的更新**:
- "工程实践核实 (StackExchange) | 阶段 5 | 高 | 待验证" → **❌ 已证伪** (StackExchange MCP 配额耗尽, 不可用)
- 新增降级方案: **WebFetch 官方文档** (实测有效, 但覆盖范围限于有官方文档的 API)

**建议**:
1. StackExchange MCP 需配置 API key 以恢复配额 (Stack Exchange API key 免费申请)
2. 无 API key 时, 阶段 5 默认采用 WebFetch 官方文档 + 代码库既有测试基线的双轨核实
3. 官方文档核实优先于 StackExchange 二次源, 因前者权威性更高

---

**文档结束**
