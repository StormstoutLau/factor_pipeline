# 调研：v3.9.8 P-011 DEV_PROGRESS §4 存量待办逐条裁决

---
id: v398-p011-dev-backlog-triage-RESEARCH
type: research
version: 1.3
status: verified
date: 2026-11-22
depends: [v397-p017-cleanup-CHECKLIST]
upstream: null
---

> **Feature**: 关闭 P-011 —— 对 `DEV_PROGRESS.md` §4 冻结的 11 条存量待办逐条裁决（关闭 / 转 P / 不修复）并留 E1 证据，使 DEV_PROGRESS 不再承载待办。
> **创建日期**: 2026-11-21（v1.1 补外部锚点 + 用户裁决回填；v1.2 补门禁声明 / F5 N/A / P-018 设计输入；v1.3 2026-11-22 异构复审修复 5×P2 + 5×P3，Step 2 完成）
> **状态**: verified（U-1/U-2/U-3 已由用户裁决；外部引用已逐条解析；v1.2 缺口补研完成）
> **Spec 步骤**: Step 1-2
> **包版本**: **3.9.8**（候选 patch；本批零生产代码改动，Step 9 仅改文档账本）
> **硬约束**: 默认 `out/capacity_impact.json` SHA `82728CE1…` 与 `panel_hash dfcc4e1d…` 逐位不变；本批不改 `backtest/`、`modules/`、`scripts/`、`tests/`；零新增依赖；Python 3.9。
> **档位**: **T3 轻批**（Layer-0 纯文档 / 账本裁决，零代码 / 零门禁）。任何实施型动作（真流式 / 真删类 / 真重命名）另立 P 批次并转 T1。

---

## 1. 调研目标

**核心问题**：

1. `DEV_PROGRESS.md` §4 的 11 条存量待办，**逐条在当前仓库中处于什么状态**（仍存在 / 已交付 / 已转移 / 前提已过时）？能否用文件 + 行号或 commit 给出 E1 证据？
2. 每条应裁决为 **关闭 / 转 P / 不修复** 中的哪一类，理由与影响面是什么？外部学术 / 官方文档 / 社区案例能否提供独立佐证或反例？
3. 若维持「零生产改动」的 T3 轻批，哪些账本需要同步，才能避免多头账本继续漂移？

## 2. 调研方法与证据口径

### 2.1 通道与降级链

| 能力 | 实际通道 | 结果 |
|------|---------|------|
| 本仓检索 | Grep / Read / Glob | 全部仓内结论落到文件 + 行号（E1） |
| 学术检索 | `mcp_paper-search`（Crossref DOI / 标题检索） | 10 条文献逐条解析（见 §5.1） |
| 官方文档 / 标准 | `WebFetch`（python.org / peps.python.org / semver.org / scikit-learn / PyPA / statsmodels / riverml） | 8 个页面读到原文（见 §5.2） |
| 社区案例 | `mcp_stackexchange` + `WebSearch` | 3 条 Stack Overflow 案例（见 §5.3）；`WebSearch` 两次零结果 |

**降级链（F3）**：

1. `WebSearch`（英文查询 3 次）→ **0 结果** → 切 `mcp_stackexchange` → 读到 3 条可用案例。
2. `get_crossref_paper_by_doi("10.1109/TSP.2009.2013925")` → `{}` → 切 Crossref **标题检索** → 命中 `10.1111/j.1467-9868.2009.00698.x`（JRSS-B 2009）。
3. `get_crossref_paper_by_doi` 对 Leys 2013 / Bergmeir 2012 直接 DOI → `{}` → 切 **标题检索** → 命中同一 DOI（两次通道差异，元数据一致）。
4. `mcp_stackexchange` 返回 `quota_remaining=-1`（配额字段不可读）但检索可用；按「通道可用、配额未取证」记录。

**证据等级**：仓内结论 E1；外部学术 T1（DOI 解析命中）；官方文档 T1；社区案例 T3（仅用于反例 / 工程陷阱，不作最佳实践唯一依据）。

### 2.2 仓内来源清单（读取日 2026-11-21/22）

| # | 来源 | 版本锚点 | 行号区间 | 用途 |
|---|------|---------|---------|------|
| S1 | [DEV_PROGRESS.md](file:///f:/Coding/factor_pipeline/docs/DEV_PROGRESS.md) | v1.5（2026-11-17） | L188-L204 | 11 条原文与既有处置 |
| S2 | [PROGRESS.md](file:///f:/Coding/factor_pipeline/docs/PROGRESS.md) | 2026-11-22 版 | L25-L31 | P-006~P-011 状态与 P-018 立项 |
| S3 | [PROJECT_STATUS.md](file:///f:/Coding/factor_pipeline/docs/PROJECT_STATUS.md) | 2026-11-22 版 | L170-L185, L277-L322 | 已完成实证 / T2 路线图 |
| S4 | [ANALYSIS_V3.0.0.md](file:///f:/Coding/factor_pipeline/docs/ANALYSIS_V3.0.0.md) | v3.0.0 | L19, L109-L170, L464-L487, L540, L773-L786 | 流式 T2 工作量 / 阶段拆解 / 就绪度 |
| S5 | [IMPUTER_LOOKAHEAD_FIX_PLAN.md](file:///f:/Coding/factor_pipeline/docs/analysis/IMPUTER_LOOKAHEAD_FIX_PLAN.md) | v2.3 | L320-L324, L1110-L1113 | 诊断因果版 / 删类的原始依据 |
| S6 | [EXECUTION_V3.3.1_IMPUTER_P2.md](file:///f:/Coding/factor_pipeline/docs/EXECUTION_V3.3.1_IMPUTER_P2.md) | v3.3.1 | L216-L218 | 两条 P3 遗留的登记来源 |
| S7 | [adapters.py](file:///f:/Coding/factor_pipeline/adapters.py) | 3.9.7 | L182-L262, L1013-L1060, L1240-L1421, L1488 | Imputer 适配器 / AR 监控 / 正交化适配器（`window_mode`） |
| S8 | [pipelines_v2.py](file:///f:/Coding/factor_pipeline/pipelines_v2.py) | 3.9.7 | L667-L675, L744, L839, L946, L1031-L1410 | 生产管线插补策略 / Pipeline API 面（无流式入口） |
| S9 | [config.py](file:///f:/Coding/factor_pipeline/config.py) | 3.9.7 | L104-L110 | 默认配置引用 HierarchicalImputer |
| S10 | [default_pipeline_config.json](file:///f:/Coding/factor_pipeline/default_pipeline_config.json) | 3.9.7 | L1-L13 | JSON 默认配置 |
| S11 | [missing_diagnoser.py](file:///f:/Coding/factor_pipeline/modules/factor_imputer/core/missing_diagnoser.py) | 3.9.7 | L29-L79 | 全样本诊断实现 |
| S12 | [missingness_checker.py](file:///f:/Coding/factor_pipeline/modules/endogeneity_check/core/missingness_checker.py) | 3.9.7 | L18-L83 | S1 诊断包装（仅诊断） |
| S13 | [types.py](file:///f:/Coding/factor_pipeline/types.py) | 3.9.7 | L1-L30 | 类型系统文件本体 |
| S14 | [ARCHITECTURE.md](file:///f:/Coding/factor_pipeline/docs/ARCHITECTURE.md) | 2026-11-19 版 | L402, L414-L431 | types.py 遮蔽 / 已知限制 / 流式条目 |
| S15 | [DECISIONS.md](file:///f:/Coding/factor_pipeline/DECISIONS.md) | 2026-11-22 版 | L46-L49, L977, L1050, L1123, L2980, L3175, L3896, L4059 | ADR-016/019/043/046 与遗留清单 |
| S16 | [tox.ini](file:///f:/Coding/factor_pipeline/tox.ini) / [ci.yml](file:///f:/Coding/factor_pipeline/.github/workflows/ci.yml) | 3.9.7 | tox L25/L55；ci L98 | types.py 遮蔽的规避口径 |
| S17 | [imputers.py](file:///f:/Coding/factor_pipeline/modules/factor_imputer/core/imputers.py) | 3.9.7 | L819-L830 | `HierarchicalImputer.impute()` 无诊断时调用全样本诊断 |
| S18 | [pipeline.py](file:///f:/Coding/factor_pipeline/pipeline.py) / [demo.py](file:///f:/Coding/factor_pipeline/demo.py) | 3.9.7 | pipeline L188/L283；demo L69/L102/L115 | `ImputerAdapter` 构造点 |
| S19 | [loaders.py](file:///f:/Coding/factor_pipeline/backtest/execution/shell/loaders.py) | 3.9.7 | L78-L140 | `MinuteLoader` 逐日流式聚合（有界内存先例） |
| S20 | [rolling.py](file:///f:/Coding/factor_pipeline/modules/factor_orthogonalizer/rolling.py) | 3.9.7 | L27-L120 | `deque(maxlen)` 窗口 + 增量 Gram（就绪 3/5） |
| S21 | [cached_data_loader.py](file:///f:/Coding/factor_pipeline/backtest/cached_data_loader.py) | 3.9.7 | L128-L151 | `get_pivoted_factors()` 返回全量 `{factor: DataFrame}` |
| S22 | [panels.py](file:///f:/Coding/factor_pipeline/backtest/execution/shell/panels.py) | 3.9.7 | L424-L536 | `panel_hash` canonical sha256（等价性工件） |

### 2.3 Step 2 门禁声明（(a)-(d)，2026-11-22 补）

| 门禁项 | 结论 | 证据 |
|---|---|---|
| (a) FALSIFIED 断言已改写并记入修订记录 | **1 处已改写** | §3.4 原称 `pipeline.py` L283「显式 `strategy='auto'`」不成立（实际按配置传参，默认配置指向 `HierarchicalImputer`）；已在 §3.4 就地改写并记入 §9（变更记录）；其余 0 处 |
| (b) CONFLICT / STEP_GAP_OPEN 已仲裁 | **1 处 CONFLICT 已仲裁：转移 P-018 并四元登记（U-6）** | `ANALYSIS_V3.0.0.md` §2.2（L130-L151，T2.1-T2.5）与 §9.1.4（L781-L786，T2.1-T2.4）编号冲突；不属 P-011 裁决面 → 登记为 P-018 **U-6**（§6.5.6）；P-011 内 0 处 |
| (c) 阻断性断言双源满足 | **11/11 满足（口径：事实前提双源，复审 B-1 修正）** | 每条裁决的**事实前提**均有 ≥2 个独立来源（可为两个仓内 T1：诉求源 + 状态 / 交付源）；外部锚点仅作方法学佐证、不充当第二事实源（第 1 条 A10/A11 佐证方法学；第 4 条外部佐证为「—」，事实源 = S1 L201 + S2 L28 + PROJECT_STATUS L267「暂缓」三处仓内） |
| (d) 假设区条目已转 A/B 或 `[待定]` 下行 | **0 条未决假设** | U-1/U-2/U-3 已裁决；新增 U-4/U-5/U-6 均 `[待定]` 且仅属 P-018，不参与 P-011 裁决 |

## 3. 11 条逐条实证与最终裁决

> 裁决状态：**已裁决（2026-11-22，用户确认 U-1/U-2/U-3）**。

| # | §4 原条目 | 现状判定 | 最终裁决 | 置信度 | 关键 E1 证据 | 外部佐证 |
|---|-----------|---------|---------|--------|-------------|---------|
| 1 | v3.3.6 冻结模型实证回测 | 已交付 | **关闭** | ★★★★☆ | S3 L174（v3.4.0 A/B → v3.4.12 → 12 因子×三分段 → 组合层 SR 0.77-1.05 / 容量压力测试） | A10（statsmodels 一步预测语义）、A11（walk-forward 评估） |
| 2 | 非生产路径治理 | 已关闭 | **关闭** | ★★★★★ | S1 L196；S15 L46 / L2980（ADR-043） | O2（PEP 387 兼容策略） |
| 3 | v3.4.0 遗留 MAD 缩尾 (O1) | 已关闭 | **关闭** | ★★★★★ | S1 L197；S3 L175（结论不切换默认，保留可选）；`docs/analysis/MAD_WINSORIZE_O1_EXPERIMENT.md` | A9（MAD 稳健性依据） |
| 4 | 内生性-溢价交互 | 已转移 | **转 P（P-009）** | ★★★★★ | S1 L201；S2 L28（P-009 `pending`，P3）；PROJECT_STATUS L267（暂缓） | — |
| 5 | 多断点支持 (Bai-Perron) | 已交付 | **关闭** | ★★★★★ | S1 L202；S15 L49 / L3175（ADR-046）；`factor_health/__init__.py` L377 | A2/A3（Bai-Perron 1998/2003） |
| 6 | 面板 HAC 稳健估计 | 已交付 | **关闭** | ★★★★★ | S1 L203；`factor_health/__init__.py` L65（v3.4.12） | A4（Newey-West 1987） |
| 7 | 流式处理（v3.0.0 T2） | 未实现（能力缺口） | **转 P-018（P3 远期）** | ★★★★★ | S3 L277 / L311-L322；S4 L19/L476/L540；代码零匹配（复审锚点 21/22 独立复核） | A8（Welford）、O6（sklearn partial_fit）、O8（River）、C1 |
| 8 | Anderson-Rubin 后验检验 | 已交付 | **关闭** | ★★★★★ | S7 L1013-L1043；`tests/unit/test_step8_ar_posterior_check.py` L1；S3 L278；S15 L3896 | A1（Anderson-Rubin 1949） |
| 9 | MissingTypeDiagnoser 因果版 | 未实现（仅诊断面，P3） | **不修复 + 触发条件** | ★★★★☆ | S5 L320-L324、L1112；S6 L216-L218（登记来源）；S11 L29-L79；S12 L30-L83；S8 L744 | A5/A6/A7（EM / 缺失数据 / 在线 EM） |
| 10 | 删除 HierarchicalImputer | 前提已过时（非死代码） | **不修复** | ★★★★★ | S5 L1113（条件句）；S6 L216-L218（登记来源）；S9 L104-L110；S10 L5-L13；`pipeline.py` L188；`demo.py` L69；S15 L1123 | O2（PEP 387）、O3（SemVer） |
| 11 | `types.py` 重命名 | 接受技术债 | **不修复** | ★★★★★ | S14 L402/L420；S16；S15 L977/L1050；仅 2 处相对导入 | O1（Python -m）、O4（types 标准库）、O5（src layout）、C2/C3 |

**计数**：关闭 6 条（1/2/3/5/6/8）＋ 已转移 1 条（4）＋ 转 P 1 条（7→P-018）＋ 不修复 2 条（10/11）＋ 不修复+触发条件 1 条（9）＝ 11 条。

### 3.1 第 1 条：冻结模型实证回测（关闭）

- 原始诉求（`docs/audit/2026-11-04-code-quality-audit.md` L402；`docs/analysis/PL08_AR_ORDER_AIC_COMPARABILITY_RESEARCH.md` L419）是「用真实因子做 IC/Sharpe 回测，检验 v3.3.6 冻结 AR 模型是否失配」。
- 交付链已在 S3 L174 逐级留痕：v3.4.0 A/B（2 因子 / 2023）→ v3.4.12 HAC 验证（4 因子 / 2020-2026）→ 12 因子 × 三分段 + Barra 中性化 40 月 → 组合层 4 因子 + 复合 × 2 池 × 4 费率 → 容量压力测试。
- **外部佐证**：statsmodels 官方文档明确 `dynamic=False` 时「true endogenous values will be used for prediction」（A10），即一步预测用真实滞后值而非拟合值；Bergmeir & Benítez (2012) 系统讨论时间序列评估中避免未来信息泄漏的口径（A11）。
- **残留边界（诚实声明）**：「非平稳因子专项失配」没有被单独命名成一项实验，但已由 12 因子三分段（含 S2 样本外）间接覆盖；无证据表明需要单独立项。

### 3.2 第 7 条：流式处理（转 P-018）

- 现状：`partial_fit` / `iter_periods` / `transform_streaming` 在**代码中零匹配**（仅文档提及），确认 T2.1-T2.5 全部未实现（S4 L476；2026-11-21 复核同样为零）。
- 范围：这是「接口层性能/内存能力」，不是功能缺陷；S4 L540 明示「非功能阻塞」。
- **外部佐证**：
  - scikit-learn 官方「out-of-core / incremental learning」文档指出：只有实现 `partial_fit` 的估计器才可增量学习，且预处理列表中仅 `StandardScaler` / `MinMaxScaler` / `MaxAbsScaler` 等原生支持（O6）；本仓自研 6 个 Imputer / Winsorizer 不在其列 → 必须自建增量统计。
  - River 0.26.1 是成熟的在线机器学习库（O8），但其 API 与因子处理语义不直接匹配 → 「引依赖」不能替代本仓 `partial_fit` 设计。
  - Welford (1962) 给出在线均值 / 协方差的数值稳定递推（A8），可作为增量标准化与增量 Winsor 的算法基础。
  - 社区案例 C1（Stack Overflow 17931865）显示：把 `partial_fit` 接进 Pipeline 并非开箱即用，需逐步适配。
- 成本：~1500+ 行、8+ 文件、流式 vs 批量等价性测试（S3 L322）。
- 具体文件面（v3.9.7 复核）：`pipelines_v2.py`、`cached_data_loader.py`、`imputers.py`（6 类）、`factor_neutralizer`、`enhanced_transformers.py`、`rolling.py`、`adapters.py`、`threshold_drift_monitor.py`。
- **裁决**：**转 P-018（P3 远期）**，保留路线图意图但清空 DEV_PROGRESS 待办形态。
- **设计输入**：本轮补研见 §6.5（能力现状 / 接口契约候选 / 等价性判据 / 内存基线 / 待裁 U-4~U-6）。

### 3.3 第 9 条：MissingTypeDiagnoser 因果版（不修复 + 触发条件）

- 现状：`MissingTypeDiagnoser.diagnose()`（S11 L29-L79）在**全样本**上做 Little's MCAR / 相关性 / 时序结构分析；`HierarchicalImputer.impute()` 在无外部 diagnosis 时调用它（同仓 `imputers.py` L824-L830）。
- 影响面：生产管线固定 `strategy='ffill_ts'`（S8 L744 / L839 / L946），该路径**不调用** `HierarchicalImputer`，诊断结果不影响插补值（S5 L324）。仅当 `strategy='auto'` 进入生产时，全样本诊断会间接影响插补路径选择。
- 另一调用方 `MissingnessMechanismChecker`（S12）只输出机制标签与 `mnar_risk_prior`，不进入变换路径。
- **入口定位澄清（复审 B-5）**：`pipeline.py` / `demo.py` 属脚本 / 演示入口，非生产编排（生产为 `pipelines_v2.py`，固定 `strategy='ffill_ts'`，S8）；故「`strategy='auto'` 进入生产」的触发条件**尚未满足**。
- **登记来源（复审 B-7）**：本条与第 10 条同源于 v3.3.1 两条 P3 遗留（S6 L216-L218）。
- **外部佐证**：
  - Dempster, Laird & Rubin (1977) 的 EM 原始框架（A5）与 Little & Rubin (2019) 的缺失数据分析体系（A6）说明：全样本 EM 是标准做法，但因果化需要显式改用 expanding / online 版本。
  - Cappé & Moulines (2009) 给出在线 EM 的通用算法与收敛率（A7）→ 技术上可行，但对「仅诊断标签」的场景成本/收益不匹配。
- **裁决**：**不修复**，并在 DEV_PROGRESS 登记触发条件：**`strategy='auto'`（或任何调用 `HierarchicalImputer` 的路径）进入生产，或诊断输出被用于交易 / 风控决策时，自动重开**。

### 3.4 第 10 条：删除 HierarchicalImputer（不修复）

- 原始依据是条件句：「**若决定永远只用 `ffill_ts`**，直接删除 `HierarchicalImputer`」（S5 L1113）。
- 该条件未成立：
  - `config.py` 默认五步法仍写 `class_name="HierarchicalImputer"`（S9 L104-L110）；`default_pipeline_config.json` 同样引用（S10 L5-L13）。
  - `pipeline.py` L188 与 `demo.py` L69/L102/L115 **显式**以 `strategy='auto'` 构造 `ImputerAdapter`；`pipeline.py` L283 按配置参数构造（默认配置 `config.py` L104-L110 仍指向 `HierarchicalImputer`）。
  - v2.4.0（ADR-019）后该类已内化为仓内模块（S15 L1123），不再是「外部死代码」。
- **入口定位澄清（复审 B-5）**：`pipeline.py` L188 与 `demo.py` 的显式 `strategy='auto'` 为脚本 / 演示入口，非生产编排（见 §3.3）；生产管线固定 `ffill_ts`。
- **登记来源（复审 B-7）**：本条与第 9 条同源于 v3.3.1 两条 P3 遗留（S6 L216-L218）。
- **外部佐证**：PEP 387 要求删除公开 API 前走弃用周期（O2）；SemVer 2.0.0 规定不兼容 API 变更须升 MAJOR（O3）。本仓当前为 3.x patch 批次，删除公开类不可接受。
- **裁决**：**不修复**（删除收益低于兼容性代价）。

### 3.5 第 11 条：`types.py` 重命名（不修复）

- 现状：顶层 `types.py` 仅在「以项目根为 cwd 运行 `python -m`」时遮蔽标准库。
- **外部佐证**：
  - Python 3.9 官方文档明确：`-m` 与 `-c` 一样会把**当前目录加到 `sys.path` 开头**（O1）→ 与仓内 `types.py` 同名即遮蔽 `types` 标准库（O4）。
  - PyPA 官方文档说明同一机制，并指出 src layout 可避免「当前目录同名包覆盖已安装包」（O5）。
  - 社区案例 C2（Stack Overflow 38793579）与 C3（79672369，调试器因 `queue.py` 同名跳过断点）是同类命名冲突的工程陷阱（T3，仅作反例）。
- 仓内引用极少：`factor_pipeline/__init__.py` L16 与 `reporting.py` L13 的相对导入；CI/tox 已用 `changedir` 从父目录规避（S16）。
- ADR-016 已将其登记为**接受的技术债**（S15 L977 / L1050；S14 L420「长期: 重命名」）。
- **裁决**：**不修复**；触发条件：未来引入 `src/` 布局，或要求「项目根直接 `python -m`」不再受约束时重审。

## 4. 关键发现总结

1. 11 条中 **7 条已实质解决或已转移**（6 关闭 + 1 转 P-009），剩余 4 条：1 条转 P-018、2 条不修复、1 条不修复+触发条件。[置信度: ★★★★★，全部 E1]
2. DEV_PROGRESS §4 的「11 条未裁决」是账本冻结后的状态快照，与仓库现状存在明显漂移（第 1/2/3/5/6/8 条均已交付）。[★★★★★]
3. 流式处理是唯一仍具工程不确定性、且值得保留路线图意图的条目；以 P-018（P3）承接而非在 P-011 内实施。[★★★★★]
4. 「删除 HierarchicalImputer」的前提从未成立，且该类已内化并被默认配置引用；应作为过时条目关闭。[★★★★★]
5. 外部锚点与仓内结论一致：官方文档支持「遮蔽机制 / 增量学习边界 / API 兼容性」三类判断；学术文献支持「EM / 在线 EM / 多断点 / HAC / AR」的方法学来源；社区案例只用于反例，不改变裁决。[★★★★☆]

## 5. 外部引用核验（F4）

> 外部引用 **21 条**（文献 / 官方 API 11 + 官方文档 / 标准 8 + 社区 3；其中 A10 与 O7 为同一 statsmodels 页面，去重后 21），≥3 条 → 按 F4 建表。
> 验证方式：DOI / URL 解析 + 标题 / 作者 / 年 / 卷期至少两项比对；状态词仅用「已验证 / 元数据差异 / 未验证」。**读取日：本节全部条目（A1-A11 / O1-O8 / C1-C3）均为 2026-11-22 同日核验。**

### 5.1 学术文献（Crossref）

| 引用 | ID | 验证方式 | 状态 | 命中或差异 |
|------|----|---------|------|-----------|
| A1 Anderson & Rubin (1949), *Estimation of the Parameters of a Single Equation in a Complete System of Stochastic Equations* | DOI 10.1214/aoms/1177730090 | Crossref DOI 解析 | ✅ 已验证 | 标题 / 作者 / 年 1949 / 卷 20(1):46-63 全部命中 |
| A2 Bai & Perron (1998), *Estimating and Testing Linear Models with Multiple Structural Changes* | DOI 10.2307/2998540 | Crossref DOI 解析 | ✅ 已验证（页码差异） | 标题 / 作者 / 年 1998 / Econometrica 66(1) 命中；Crossref 仅返回起始页 `47`（末页 78 未返回） |
| A3 Bai & Perron (2003), *Computation and analysis of multiple structural change models* | DOI 10.1002/jae.659 | Crossref DOI 解析 | ✅ 已验证（日期差异） | 标题 / 作者 / 卷 18(1):1-22 命中；Crossref `published_date=2002-10-08`（online first），卷期年份为 2003 |
| A4 Newey & West (1987), *A Simple, Positive Semi-Definite, Heteroskedasticity and Autocorrelation Consistent Covariance Matrix* | DOI 10.2307/1913610 | Crossref DOI 解析 | ✅ 已验证（页码差异） | 标题 / 作者 / 年 1987 / Econometrica 55(3) 命中；Crossref 仅返回起始页 `703`（末页 708 未返回） |
| A5 Dempster, Laird & Rubin (1977), *Maximum Likelihood from Incomplete Data Via the EM Algorithm* | DOI 10.1111/j.2517-6161.1977.tb01600.x | Crossref DOI 解析 | ✅ 已验证 | 标题 / 作者 / 年 1977 / JRSS-B 39(1):1-22 命中 |
| A6 Little & Rubin (2019), *Statistical Analysis with Missing Data* (3rd ed.) | DOI 10.1002/9781119482260 | Crossref DOI 解析 | ✅ 已验证 | 标题 / 作者 / 年 2019 / Wiley 专著命中 |
| A7 Cappé & Moulines (2009), *On-Line Expectation–Maximization Algorithm for Latent Data Models* | DOI 10.1111/j.1467-9868.2009.00698.x | 先 DOI `10.1109/TSP.2009.2013925`（返回空）→ 标题检索 | ✅ 已验证（通道降级） | 标题 / 作者 / 年 2009 / JRSS-B 71(3):593-613 命中 |
| A8 Welford (1962), *Note on a Method for Calculating Corrected Sums of Squares and Products* | DOI 10.1080/00401706.1962.10490022 | Crossref DOI 解析 | ✅ 已验证 | 标题 / 作者 / 年 1962 / Technometrics 4(3):419-420 命中 |
| A9 Leys et al. (2013), *Detecting outliers: Do not use standard deviation around the mean, use absolute deviation around the median* | DOI 10.1016/j.jesp.2013.03.013 | 先 DOI（返回空）→ 标题检索 | ✅ 已验证（通道降级） | 标题 / 作者 / 年 2013 / JESP 49(4):764-766 命中 |
| A10 statsmodels, *AutoReg.predict*（`dynamic=False`） | URL https://www.statsmodels.org/stable/generated/statsmodels.tsa.ar_model.AutoReg.predict.html | WebFetch 原文 | ✅ 已验证 | 原文：「Prior to this observation, true endogenous values will be used for prediction」 |
| A11 Bergmeir & Benítez (2012), *On the use of cross-validation for time series predictor evaluation* | DOI 10.1016/j.ins.2011.12.028 | 先 DOI（返回空）→ 标题检索 | ✅ 已验证（通道降级） | 标题 / 作者 / 年 2012 / Information Sciences 191:192-213 命中 |

### 5.2 官方文档 / 标准

| 引用 | ID / URL | 版本 | 日期 | 状态 | 关键原文 |
|------|----------|------|------|------|---------|
| O1 Python 3.9 docs, *Command line and environment* (`-m`) | https://docs.python.org/3.9/using/cmdline.html#cmdoption-m | Python 3.9 | 发布日未标注；读取 2026-11-22 | ✅ 已读 | 「As with the -c option, the current directory will be added to the start of sys.path」 |
| O2 PEP 387, *Backwards Compatibility Policy* | https://peps.python.org/pep-0387/ | Status: Active | Created 2009-06-18；读取 2026-11-22 | ✅ 已读 | 删除公开 API 前须走弃用 / 兼容周期 |
| O3 Semantic Versioning 2.0.0 | https://semver.org/ | 2.0.0 | 发布日未标注；读取 2026-11-22 | ✅ 已读 | MAJOR = 不兼容 API 变更；MINOR = 向后兼容新增；PATCH = 向后兼容修复 |
| O4 Python 3.9 docs, *types — Dynamic type creation and names for built-in types* | https://docs.python.org/3.9/library/types.html | Python 3.9 | 发布日未标注；读取 2026-11-22 | ✅ 已读 | 标准库 `types` 模块存在且为常用顶层模块 |
| O5 PyPA, *src layout vs flat layout* | https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/ | latest（未标注） | 发布日未标注；读取 2026-11-22 | ✅ 已读 | 「the current directory as the first item on the import path … variant from the current working directory will be used」 |
| O6 scikit-learn, *Strategies to scale computationally: bigger data* | https://scikit-learn.org/stable/computing/scaling_strategies.html | stable（未标注） | 发布日未标注；读取 2026-11-22 | ✅ 已读 | 仅实现 `partial_fit` 的估计器可增量学习；预处理仅列 `StandardScaler` / `MinMaxScaler` / `MaxAbsScaler` 等 |
| O7 statsmodels 文档（同 A10，合并引用） | 见 A10 | — | — | ✅ 已验证 | — |
| O8 River 0.26.1, *Online Machine Learning in Python* | https://riverml.xyz/latest/ | 0.26.1 | 发布日未标注；读取 2026-11-22 | ✅ 已读 | 在线学习库与其 API 范围（不能直接替代本仓因子处理语义） |

### 5.3 社区案例（T3，仅作反例 / 工程陷阱）

| 引用 | ID / URL | 发布日（API） | 状态 | 用途 / 局限 |
|------|----------|--------------|------|------------|
| C1 *Using partial_fit with Scikit Pipeline* | Stack Overflow 17931865（score 22，4 answers） | 2013-07-29 | ✅ 已解析（T3） | 说明 `partial_fit` 接入 Pipeline 需逐步适配；**不得**作为最佳实践唯一依据 |
| C2 *python module names with same name as existing modules* | Stack Overflow 38793579（score 8，1 answer） | 2016-08-05 | ✅ 已解析（T3） | 同名模块冲突的工程陷阱；与本仓 `types.py` 同型 |
| C3 *Python debugger skips breakpoint when module name conflicts with standard library (queue.py)* | Stack Overflow 79672369（score 2，未答） | 2025-06-19 | ⚠️ 已解析但未验证答案 | 近期同类症状的单例记录；**未验证**其结论，仅作反例线索 |

### 5.4 待修正项

- [x] U-1/U-2/U-3 已由用户裁决并回填（见 §6.4）。
- [x] 外部引用逐条解析并建表（§5.1-§5.3）。
- [x] 最小同步已执行（DEV_PROGRESS §4 / PROJECT_STATUS / PROGRESS / P-018）。
- [x] v1.2 补齐：S17-S22 来源行（§2.2）、Step 2 门禁声明（§2.3）、F1-F5 核对含 F5 N/A（§5.5）、P-018 设计输入（§6.5）。
- [x] v1.3 异构复审修复：5×P2 + 5×P3 全部就地处置（§9.2 处置表）；视角 A 锚点核查 22/22 PASS（§9.1）；**Step 2 宣布完成**。

### 5.5 F1-F5 出具核对（v1.2 补充）

| 字段 | 状态 | 出具位置 / 说明 |
|---|---|---|
| F1 来源日期 | ✅ | 外部来源：§5.1-§5.3 统一注记读取日 2026-11-22（复审 B-2 修正指针）；仓内来源：§2.2 表头标注读取日 2026-11-21/22 |
| F2 来源版本 | ✅ | 每条含版本 + 行号；v1.2 补 S17-S22 |
| F3 降级链 | ✅ | §2.1 四条三段式 |
| F4 引用验证表 | ✅ | §5.1-§5.3 共 21 条（去重后） |
| F5 先失败记录 | **N/A** | **理由**：本批零代码 / 零 fixture 改动，无「红→绿」序列；按 [SPEC_PROCESS.md](file:///f:/Coding/factor_pipeline/spec/SPEC_PROCESS.md#L598) 「不适用写 N/A + 理由」 |

## 6. 对设计的输入

### 6.1 最终裁决矩阵

| 裁决 | 条目 | 回填动作 |
|------|------|---------|
| 关闭 | 1/2/3/5/6/8 | DEV_PROGRESS §4 逐行标注「关闭 + 证据」；PROGRESS P-011 汇总 |
| 转 P | 4（P-009）、7（P-018） | PROGRESS 新增 P-018；DEV_PROGRESS 标注「→ P-xxx」 |
| 不修复 | 10、11 | DEV_PROGRESS 标注「不修复 + 理由」 |
| 不修复 + 触发条件 | 9 | DEV_PROGRESS 标注「不修复 + 触发条件」 |

### 6.2 关键约束

- 零生产代码改动；默认 SHA 与 `panel_hash` 不变。
- 本批不触碰 `scripts/` / `tests/` / 门禁 → Layer-0，T3。
- 裁决必须有 E1 证据（文件 + 行号），外部引用必须可解析（DOI / URL）。

### 6.3 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| 关闭「流式」被理解为取消路线图 | 丢失远期意图 | 转 P-018（P3）并在 PROJECT_STATUS §3 标注「移交 P-018」 |
| 「不修复」缺少触发条件 | 未来重开无依据 | 第 9 条写明触发条件；第 11 条写明重审条件 |
| 多账本同步遗漏 | 账本互相矛盾 | 已执行最小同步；Step 8 再做一致性核对 |

### 6.4 未决项登记（四元块，已裁决）

- **U-1 流式处理（v3.0.0 T2）的最终处置** —— **已裁决：转 P-018（P3 远期）**
  - **判据**：PROGRESS 中存在 P-018 行且 DEV_PROGRESS §4 不再以待办形态保留该项。
  - **触发条件**：P-018 启动时；若出现「全量面板无法一次性装入内存 / 需要分钟级在线更新」的实际需求则优先。
  - **当前倾向**：已落地为 P-018；备选「不修复」未采纳。
  - **证据等级**：E1（S3 L311-L322；S4 L19/L476/L540；代码零匹配）＋ O6/O8/A8/C1。

- **U-2 MissingTypeDiagnoser 因果版的最终处置** —— **已裁决：不修复 + 登记触发条件**
  - **判据**：DEV_PROGRESS 该项有「不修复 + 触发条件」；PROGRESS P-011 依据列可见。
  - **触发条件**：`strategy='auto'`（或任何调用 `HierarchicalImputer` 的路径）进入生产，或诊断输出被用于交易 / 风控决策时，自动重开。
  - **当前倾向**：不修复；实现 expanding EM 的成本与收益不匹配。
  - **证据等级**：E1（S5 L320-L324、L1112；S8 L744；S11 L29-L79；S12 L30-L83）＋ A5/A6/A7。

- **U-3 关闭项的多账本同步范围** —— **已裁决：最小同步集，并已执行**
  - **判据**：Step 8 一致性核对时，PROGRESS / DEV_PROGRESS / PROJECT_STATUS 对同一条目无相反表述。
  - **触发条件**：已完成；后续若新增同名条目需重审。
  - **当前倾向**：DEV_PROGRESS §4 逐行标注 + PROGRESS（P-011 收口 / P-018 立项）+ PROJECT_STATUS 仅「流式 / AR」两行加注。
  - **证据等级**：E1（S2/S3 + 本次同步 diff）。

### 6.5 P-018 设计输入（v1.2 补充调研）

> 定位：只补**设计所需事实与待裁项**，不替 P-018 做设计决策。P-018 = v3.0.0 T2 流式承接批次（P3），下列锚点均为 v3.9.7 当前代码。

#### 6.5.1 能力现状（E1，2026-11-22 复核）

| 层 | 现状 | 锚点 |
|---|---|---|
| Pipeline API | 仅 `fit/transform/fit_transform`，无 `transform_streaming` / `partial_fit` | S8（`pipelines_v2.py` L667-L675、L1031、L1191、L1319、L1396） |
| 数据加载 | `get_pivoted_factors()` 返回全量 `{factor: DataFrame(stock_code × trade_date)}`，无 `iter_periods` | S21 L128-L151 |
| Imputer（6 类） | 全部仅 `fit/transform` | `imputers.py`（S17；ANALYSIS L470） |
| 正交化 | `RollingOrthogonalizer` 已有 `deque(maxlen)` + 增量 Gram，但只接受全量 `(T,N,K)` | S20 L59、L84-L120 |
| 适配器 | `OrthogonalizerAdapter` docstring 仍称「滚动委托」（L1368），`fit()` 始终全样本堆叠（L1380-L1421），`window_mode` 仅赋值（L1268）并进 `get_stats()`（L1488） | S7（复审锚点 5 精化） |
| 既有流式先例 | `MinuteLoader.load_month()` 逐日读文件 → 聚合 → 丢弃，有界内存 | S19 L106-L140 |
| 测试 | `tests/` 对 `streaming` / `partial_fit` / `iter_periods` 零匹配 | Grep（2026-11-22） |

#### 6.5.2 接口契约候选（研究级，未裁决）

- `iter_periods(...)`：ANALYSIS 给的签名是 `def iter_periods(self, factor_names, start_date, end_date, step='D') -> Iterator[Dict[str, pd.DataFrame]]`（S4 L133），**未说明 DataFrame 方向**。仓内实际方向为「股票 × 日期」（S21 L146，docstring 口径，未做运行时验证——复审锚点 16 备注），因此 `step` 切的是**列（日期）**而非行——P-018 Step 1 必须先钉死方向，否则切片语义会错。
- `partial_fit`：组件级最小契约候选 = `partial_fit(X_t) -> self` + `transform(X_t)`；批量 `fit` 保留为默认路径。
- `transform_streaming`：`FactorProcessingPipelineV2.transform_streaming(period_iter)`，默认关闭（opt-in）；批量路径逐位不变（S4 L157/L161）。
- 编号：ANALYSIS §2.2（L130-L151）为 T2.1-T2.5（T2.5 = CUSUM 协同），§9.1.4（L781-L786）为 T2.1-T2.4（T2.4 = 适配器文档修正，无 CUSUM）——**两套编号并存**，见 U-6。

#### 6.5.3 等价性判据候选

| 层 | 候选判据 | 依据 |
|---|---|---|
| 确定性变换（排序 / 切片 / 分位） | `panel_hash` 逐位不变（canonical JSON sha256） | S22 L424-L536；v3.8.1 内存优化即以单月 `panel_hash` 不变证明数值等价（EXECUTION_V3.8.1 L1103） |
| 浮点归约顺序敏感（Welford vs 批量均值/方差） | 绝对 / 相对误差 `< 1e-10` | ANALYSIS §2.3 L158 已给出该阈值 |
| 边界 | NaN 分布、停牌 / 涨跌停、空截面、单期窗口 | 当前无现成矩阵；需 P-018 Step 1 补齐 |

> 建议（不裁决）：确定性层用 `panel_hash` 逐位，归约顺序敏感层用 `1e-10`，避免统一容差掩盖真实差异。

#### 6.5.4 内存基线读数（可复用）

| 场景 | 峰值 | 来源 |
|---|---|---|
| 分钟面板单月装配（优化后） | 296.6 MB（tracemalloc；RSS 增量 478.4 MB，仅记录） | EXECUTION_V3.8.1 L1100/L1103 |
| 容量回测单月（v3.8.0） | 183.9 MB | EXECUTION_V3.8.0 L529 |
| 日频全量 `build_panels`（v3.9.5） | 2942.8 MB | PROJECT_STATUS L110 |
| v3.8.1 单月预算 | ≤300 MB | EXECUTION_V3.8.1 L1100 |

#### 6.5.5 可复用资产 / 被拒备选

- **可复用**：`RollingOrthogonalizer` 增量 Gram + 定期 reset（S20 L84-L110）；`MinuteLoader` 的「读一天、聚合、丢弃」模式（S19 L106-L140）；`panel_hash` 工件（S22）；Welford 递推（A8）；`ThresholdDriftMonitor.update()` 既有流式接口（据 ANALYSIS L184 转引，**P-018 Step 1 需独立复核行号**）。
- **被拒备选（研究级）**：① 引入 River（O8）——API 语义不匹配且违反零新增依赖；② 先整段物化再切片——不解决峰值内存；③ 只改 docstring 不改实现——不产生流式能力。

#### 6.5.6 P-018 待裁项（四元块，交 P-018 Step 1）

- **U-4 范围**：全链路 T2.1-T2.5 vs 仅正交化层最小可行版 —— **`[待定]`**
  - **判据**：P-018 启动时以「是否存在单月 / 全量内存超预算的实际场景」裁决。
  - **触发条件**：P-018 立项。
  - **当前倾向**：未定；ANALYSIS L356 已把「仅正交化层」列为最小可行版。
  - **证据等级**：E1（ANALYSIS L356；§6.5.1）+ O6/O8/A8。

- **U-5 等价性判据**：`panel_hash` 逐位 vs `1e-10` 容差 —— **`[待定]`**
  - **判据**：按变换层是否改变浮点归约顺序分层。
  - **触发条件**：P-018 Step 1 定接口时。
  - **当前倾向**：分层（§6.5.3）。
  - **证据等级**：E1（S22 L424-L536；ANALYSIS L158）。

- **U-6 编号口径**：T2.1-T2.5（§2.2）vs T2.1-T2.4（§9.1.4）—— **`[待定]`**
  - **判据**：P-018 DESIGN 引用时只允许一套编号，另一套标注 `superseded`。
  - **触发条件**：P-018 DESIGN 撰写。
  - **当前倾向**：以 §2.2 五阶段为准，把 §9.1.4 的「适配器修正」并入 T2.3/T2.4。
  - **证据等级**：E1（ANALYSIS L130-L151 vs L781-L786）。

### 6.6 P-009 设计输入现状（范围外声明）

- P-009「内生性-溢价诊断交互」在 P-011 中只做**转移裁决**（PROGRESS L28，`pending` / P3），本轮**未**补充其接口契约、交互矩阵或口径输入。
- 结论：**P-009 不得直接进入 Step 3**——启动时须先补 Step 1（诊断输出键清单 + 溢价消费面 + 交互矩阵候选），再按 T1/T2 走设计。
- 证据等级：E1（PROGRESS L28；S3 路线图 v3.5.x 远期）。

## 7. 参考文献 / 证据清单

### 7.1 仓内

1. `docs/DEV_PROGRESS.md` §4（v1.5，2026-11-17）L188-L204 —— 裁决前快照；本轮改写后 §4 为 L188-L209（已含裁决列）。
2. `docs/PROGRESS.md`（2026-11-22）L25-L30。
3. `docs/PROJECT_STATUS.md`（2026-11-22）L170-L185、L277-L322。
4. `docs/ANALYSIS_V3.0.0.md` L19、L109-L170、L464-L487、L540、L773-L786。
5. `docs/analysis/IMPUTER_LOOKAHEAD_FIX_PLAN.md` L320-L324、L1110-L1113。
6. `docs/EXECUTION_V3.3.1_IMPUTER_P2.md` L216-L218。
7. `adapters.py` L182-L262、L1013-L1060；`pipelines_v2.py` L744、L839、L946。
8. `config.py` L104-L110；`default_pipeline_config.json` L1-L13；`pipeline.py` L188/L283；`demo.py` L69/L102/L115。
9. `modules/factor_imputer/core/missing_diagnoser.py` L29-L79；`modules/endogeneity_check/core/missingness_checker.py` L30-L83；`modules/factor_imputer/core/imputers.py` L819-L830；`pipeline.py` L188/L283；`demo.py` L69/L102/L115。
10. `types.py` L1-L30；`docs/ARCHITECTURE.md` L402、L420；`tox.ini` L25/L55；`.github/workflows/ci.yml` L98。
11. `DECISIONS.md` L46-L49、L977、L1050、L1123、L2980、L3175、L3896、L4059。
12. `CHANGELOG.md` L389；`docs/EXECUTION_V3.8.1_MINUTE_PANEL_WIRING.md` L176。
13. `backtest/execution/shell/loaders.py` L78-L140；`backtest/cached_data_loader.py` L128-L151；`modules/factor_orthogonalizer/rolling.py` L27-L120；`backtest/execution/shell/panels.py` L424-L536。
14. `adapters.py` L1240-L1421、L1488；`pipelines_v2.py` L667-L675、L1031-L1410。
15. 内存读数：`docs/EXECUTION_V3.8.1_MINUTE_PANEL_WIRING.md` L1100/L1103；`docs/EXECUTION_V3.8.0_EXECUTION_CAPACITY.md` L529；`docs/PROJECT_STATUS.md` L110。

### 7.2 外部（按 §5 编号）

- A1-A11：学术文献 / 官方 API 文档（Crossref DOI 或官方 URL，见 §5.1）。
- O1-O8：官方文档 / 标准（见 §5.2）。
- C1-C3：社区案例（Stack Overflow，见 §5.3）。

---

## 8. 异构复审（Step 2 收尾，2026-11-22）

> 双视角独立子代理审查（均只读、互不知晓对方结论）：**视角 A = 对抗式 E1 锚点核查**；**视角 B = 过程合规 / 裁决逻辑 / 账本一致性审查**。

### 8.1 视角 A：E1 锚点核查（对抗式）

- 抽样设计：22 组锚点，覆盖 §2.2 全部 22 个来源行的代表性断言 + 2 项全仓 Grep（生产代码流式 API 零匹配 / `tests/` 零匹配）。
- 结果：**22 PASS / 0 DRIFT / 0 FAIL**——全部行号与内容与本文档所述一致，E1 锚点可信。
- 两处微备注（不构成漂移，已并入 v1.3）：① §6.5.1 中 L1268 为 `window_mode` 赋值行，docstring「滚动」字样仅 L1368 一处；② §6.5.2 的「股票 × 日期」方向为 docstring 口径（S21 L146），未做运行时验证。

### 8.2 视角 B：过程合规 / 裁决逻辑 / 账本一致性

- Step 2 判据逐项核对：F2/F3/F4/F5、门禁 (a)/(d)、T3 档位、账本一致性（三账本无相反表述）均满足；总体结论「修复后可完成」（0×P1）。
- 发现 5×P2 + 5×P3，全部在 v1.3 就地处置：

| # | 级别 | 问题 | 修复 |
|---|---|---|---|
| B-1 | P2 | §2.3(c)「11/11 ≥2 独立来源」表述过强（第 1 条外部佐证为方法学、第 4 条外部佐证为「—」） | 门禁 (c) 改口径「事实前提双源（可为两个仓内 T1）」；第 4 条补 PROJECT_STATUS L267 第三事实源（§3 表 + §2.3） |
| B-2 | P2 | §5.1 无逐行读取日；§5.5 F1 证据指针错指 §2.2 | §5 表头统一注记读取日 2026-11-22；F1 指针改指 §5.1-§5.3 |
| B-3 | P2 | PROGRESS P-011 已 done 但 §6.3 称 Step 8 再核对（时序倒挂） | 本轮复审已覆盖账本一致性维度；PROGRESS 依据列注明「一致性核对由复审覆盖，剩余收尾为提交」 |
| B-4 | P2 | 第 11 条触发条件仅存本文档，未回填账本（与第 9 条不对称） | DEV_PROGRESS 第 11 条行补触发条件 |
| B-5 | P2 | 第 9 条触发「`strategy='auto'` 进入生产」与 `pipeline.py` L188 显式 auto 并存，未澄清定位 | §3.3/§3.4 补注：`pipeline.py`/`demo.py` 为脚本 / 演示入口，非生产编排；触发条件尚未满足 |
| B-6 | P3 | S2 行号区间未覆盖 P-018 行 | L25-L30 → L25-L31 |
| B-7 | P3 | S6 声明用途但正文未引用 | §3.3/§3.4 补引 S6（v3.3.1 登记来源） |
| B-8 | P3 | §3 表逐条无置信度 | 表增「置信度」列（第 1/9 条间接证据 ★★★★☆，其余 ★★★★★） |
| B-9 | P3 | PROJECT_STATUS L267 内生性行无 P-009 指针 | 补「→ P-009」注记 |
| B-10 | P3 | §2.3(b)「已仲裁」与「延迟至 P-018」措辞不对应 | 改「已仲裁：转移 P-018 并四元登记」 |

### 8.3 复审结论

- **Step 2 宣布完成（2026-11-22）**：门禁 (a)-(d) 在修正口径后成立；11 条裁决 E1 证据经独立对抗核查 22/22 PASS；账本一致性经独立复核无相反表述。
- P-011 剩余收尾：git 提交（待用户指令）；Step 8 全仓一致性核对中的账本维度已由 B-3 覆盖。

## 9. 变更记录

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0 | 2026-11-21 | Step 1 初稿：11 条逐条 E1 实证 + 建议裁决 + U-1/U-2/U-3 |
| 1.1 | 2026-11-22 | 补外部锚点（文献 / API 11、官方文档 / 标准 8、社区 3，去重 21）；U-1 转 P-018、U-2 不修复+触发条件、U-3 最小同步；执行账本回填 |
| 1.2 | 2026-11-22 | 缺口补研：补 S17-S22 来源行；新增 §2.3 Step 2 门禁声明（含 1 处 FALSIFIED 改写 / 1 处 CONFLICT 延迟裁决）；§5.5 F5「N/A + 理由」；新增 §6.5 P-018 设计输入（能力现状 / 接口候选 / 等价性判据 / 内存基线 / U-4~U-6）；修正 §3.4 `pipeline.py` L283 表述 |
| 1.3 | 2026-11-22 | **异构复审（视角 A 锚点核查 22/22 PASS；视角 B 0×P1 + 5×P2 + 5×P3）**：门禁 (b)/(c) 措辞修正；§5 读取日注记 + F1 指针修正；§3 表增置信度列 + 第 4 条补第三事实源；§3.3/§3.4 补入口定位澄清与 S6 引用；§6.5.1/§6.5.2 精化；新增 §8 异构复审记录；账本三处同步（DEV_PROGRESS 第 11 条触发条件、PROGRESS 依据注记、PROJECT_STATUS L267 → P-009）；**Step 2 宣布完成** |

**Review 签字**: 用户（2026-11-22 裁决 U-1/U-2/U-3）＋ 异构复审双视角（2026-11-22，见 §8） 日期: 2026-11-22
