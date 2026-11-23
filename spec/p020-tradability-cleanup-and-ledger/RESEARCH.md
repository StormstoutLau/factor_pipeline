# 调研文档：P-020 tradability 小口径收尾 + 台账同步

---
id: p020-tradability-cleanup-and-ledger-RESEARCH
type: design
version: 1.1
status: verified
date: 2026-11-23
depends: [p006-tradability-engine-integration]
upstream: null
---

> **Feature**: P-020（A 台账同步 + B 三项小口径收尾）
> **创建日期**: 2026-11-23
> **状态**: verified（Step 1-2 完成）
> **Spec 步骤**: Step 1-2
> **批次档位**: **T1**（触及 `backtest/` 运行时与 `tests/`；判档规则见 `spec/SPEC_PROCESS.md`「批次档位与裁剪理由」§判档规则第 1 条）
> **裁剪理由**: 不降档。「小批次」指范围小（3 项 + 台账），不指证据强度可减；三项中 ①③ 改变启用态行为，需完整四件套 + TDD。

---

## 1. 调研目标

**核心问题**:
1. P-006 Step 10 审计登记的 P3-②③④ 三项是否都能**在不改动默认路径**的前提下闭合？
2. 三项各自的「正确口径」在本仓已有实现里有无可复用的单一真源（避免再造第二套约定）？
3. A（台账）滞后项的精确定位与改法边界。

## 2. 调研方法

### 2.1 使用的工具

| 工具 | 用途 | 查询 |
|------|------|------|
| Grep / Read | 本仓代码事实（E1） | `_EPS`、`policy.eps`、`list_date`、`st_overrides`、`one_word` |
| Read | P-006 四件套既有裁决（D-6-7 / §8.2） | `spec/p006-tradability-engine-integration/` |
| 无外部通道 | 本批关键结论均为**仓内代码事实**，外部规则仅作背景锚点沿用 P-006 | — |

### 2.2 调研范围

- 版本基线：包版本 **3.9.9**（`pyproject.toml:7`）。
- 领域：A 股涨跌停判定（eps 容差）、证券代码键归一化、台账一致性。
- 排除：不重开 P-006 的取整/板块/除权裁决；不触碰容量主路径（`execution/`）。

## 3. 调研发现（全部 E1，逐条带版本 + 行号）

### 3.1 项① eps 双源

| # | 位置 | 事实 | 版本 |
|---|---|---|---|
| F-1-1 | [tradability.py](file:///f:/Coding/factor_pipeline/backtest/tradability.py#L16) | 模块常量 `_EPS = 1e-8`；`TradabilityPolicy.eps` 默认值即取它（L199） | v3.9.9 |
| F-1-2 | [tradability.py](file:///f:/Coding/factor_pipeline/backtest/tradability.py#L385-L397) | `apply_tradability` 的一字板/可成交判定统一用 `policy.eps` | v3.9.9 |
| F-1-3 | [tradability_inputs.py](file:///f:/Coding/factor_pipeline/backtest/tradability_inputs.py#L117-L126) | 构建器 meta 的 `one_word_up_cells/one_word_down_cells` 用**常量 `_EPS`**，不看 `policy` | v3.9.9 |
| F-1-4 | [tradability_inputs.py](file:///f:/Coding/factor_pipeline/backtest/tradability_inputs.py#L150) | 构建器把 `policy` 原样装入 `TradabilityInputs`，引擎 L299 又把它传给 `apply_tradability` | v3.9.9 |

**结论 C-1**：同一批输入下，`meta.one_word_*_cells`（构建期）与 `results[factor]['tradability']['report']['one_word_*']`（推进期）在**自定义 `policy.eps`** 时口径不一致；默认 `policy=None` 时两者恰好相等（均 1e-8），因此该缺陷在默认路径不可见，属**静默不一致**。

### 3.2 项② 覆盖缺口

| # | 位置 | 事实 | 版本 |
|---|---|---|---|
| F-2-1 | [test_tradability.py](file:///f:/Coding/factor_pipeline/tests/test_tradability.py#L150-L158) | 仅断言 report **键集合**含 `one_word_up/down` | v3.9.9 |
| F-2-2 | 同上（全文） | 无任何用例断言 `one_word_up`/`one_word_down` **正向计数 >0** | v3.9.9 |
| F-2-3 | [test_tradability.py](file:///f:/Coding/factor_pipeline/tests/test_tradability.py#L238-L266) | `test_tp6_6` 只覆盖**经 adj 派生 ref**（`_ref_from_adj`）路径 | v3.9.9 |
| F-2-4 | [engine.py](file:///f:/Coding/factor_pipeline/backtest/engine.py#L295-L301) | 引擎调用不传 `ref=`，一律走 adj | v3.9.9 |
| F-2-5 | [IMPLEMENTATION.md](file:///f:/Coding/factor_pipeline/spec/p006-tradability-engine-integration/IMPLEMENTATION.md#L466) §14（D-6-7） | `apply_tradability(ref=...)` 直传是**公开签名**的一部分，允许调用方直接给参考价 | v1.3 |
| F-2-6 | [CHECKLIST.md](file:///f:/Coding/factor_pipeline/spec/p006-tradability-engine-integration/CHECKLIST.md#L272) §8.2 | 审计登记 **P3-③ = 覆盖缺口**（`one_word_up/down` 正向计数断言缺失 + `ref=` 直传未测 + TP6-10 本地重算非恒真，合并一条）；配套 P3-② = eps 源不一致（→ F-1-3）、P3-④ = `list_date` 键未归一（→ F-3-1） | v1.4 |

**结论 C-2**：报告键存在但无人验证其**取值**；`ref=` 直传分支（不带 adj）在生产调用图之外，属公开契约但零覆盖。

### 3.3 项③ list_date 键归一化

| # | 位置 | 事实 | 版本 |
|---|---|---|---|
| F-3-1 | [tradability_inputs.py](file:///f:/Coding/factor_pipeline/backtest/tradability_inputs.py#L71-L85) | `list_date` 查找：`key = code if code in ld.index else str(code)`，**不做后缀剥离 / zfill** | v3.9.9 |
| F-3-2 | [tradability_inputs.py](file:///f:/Coding/factor_pipeline/backtest/tradability_inputs.py#L98-L102) | `st_overrides` 侧已用 `str(c).split(".")[0].zfill(6)` 双向归一 | v3.9.9 |
| F-3-3 | [tradability_inputs.py](file:///f:/Coding/factor_pipeline/backtest/tradability_inputs.py#L76-L77) | 不匹配 → `continue`，**静默跳过**，`no_limit_source` 仍可能是 `delisting_only` | v3.9.9 |
| F-3-4 | [data_contract.py](file:///f:/Coding/factor_pipeline/backtest/data_contract.py#L238-L239) | 仓内 `list_date` 真值源是 `list_date_df.pkl['list_date']`，索引形态**未在契约中固定** | v3.9.9 |
| F-3-5 | [test_tradability_inputs.py](file:///f:/Coding/factor_pipeline/tests/test_tradability_inputs.py#L46-L56) | 现有测试的列名与 `list_date` 键**完全同形**（均带后缀），因此从未暴露该缺口 | v3.9.9 |

**结论 C-3**：同一函数内两套键归一化惯例并存；裸代码列（如 int `600000` 或 `"600000"`）× 带后缀键（`"600000.SH"`）会让 IPO 前 5 日豁免**静默失效**，且无任何 warning 或 meta 计数可发现。

### 3.4 A 台账滞后

| # | 位置 | 事实 |
|---|---|---|
| F-4-1 | [PROJECT_STATUS.md](file:///f:/Coding/factor_pipeline/docs/PROJECT_STATUS.md#L71-L72) | 路线图末行为 v3.9.8，且「当前在 v3.9.8」指针未随 P-006（v3.9.9）前进 |
| F-4-2 | 同上 L129 | 优先级视图仍写「P2 = P-006；P3 = P-009 / P-018」，P-006 已 done、P-020 未列 |
| F-4-3 | [PROGRESS.md](file:///f:/Coding/factor_pipeline/docs/PROGRESS.md#L25) | P-006 已 done 且行内证据完整；P-020 已登记 pending / P3（L33） |

## 4. 综合分析

### 4.1 关键发现总结

1. 三项**互不耦合**，可独立落地；①③ 共享同一「单一真源」主题——都属「同一函数内第二套约定」。 [置信度: ★★★★★，E1 逐行]
2. ① 的正确解法不是「把 `_EPS` 改成 `policy.eps` 的字面复制」，而是让构建器**实例化默认 policy**，使未来默认值变更自动跟随。 [★★★★☆]
3. ③ 的解法应**保留精确匹配优先**，再加归一化回退——这样现有行为零变更，只补盲区。 [★★★★☆]
4. 默认路径（`policy=None`、键同形）在 ①③ 修复后读数必须**逐位不变**，这是本批最强的可机械核验不变式。 [★★★★★]

### 4.2 技术 landscape

- 仓内已有归一化惯例：`st_overrides` 的 `split(".")/zfill(6)`；`loaders.MIN_STOCK_CODE` 用数值域过滤。
- 一字板判定容差在券商/开源栈中普遍为 `1e-6`~`1e-8` 量级（沿用 P-006 已核锚点，见 §5.2）；关键不是数值本身，而是**判定与统计必须同源**。

### 4.3 研究空白

- 无外部研究空白；本批为工程一致性收尾。

## 5. 幻觉抑制审查（Step 2 Review）

### 5.1 文献验证

外部引用 **2 条（<3）** → 按 F4 内联出具，每条带 ID + 状态：

| 外部引用 | ID / 定位 | 状态 |
|---|---|---|
| Tushare 日线行情代码格式 `600000.SH` | Tushare Pro `daily` 接口文档（沿用 P-006 IMPLEMENTATION §3 锚点） | ⚠️ **未重验**（本批未重抓，仅作背景） |
| 涨跌停价取整规则（上交所 3.3.17 / 深交所 3.3.19） | 交易所交易规则原文（P-006 RESEARCH §5 已核） | ⚠️ **未重验**（沿用 P-006） |

**F4 判定**：外部引用 <3，允许内联；无一条标 ✅。

### 5.2 技术声明验证

| 声明 | 来源 | 状态 |
|---|---|---|
| 默认 `policy=None` 时两处 eps 均为 `1e-8` | F-1-1 + F-1-2 + F-1-3 | ✅ E1 逐行 |
| `st_overrides` 已归一化而 `list_date` 未归一化 | F-3-1 + F-3-2 | ✅ E1 逐行 |
| `ref=` 直传在生产调用图之外 | F-2-4 + F-2-5 | ✅ E1 逐行 |
| `one_word_*` 无取值断言 | F-2-1 + F-2-2 | ✅ E1 全文检索 |

### 5.3 待修正项

- 无（Step 2 复核未发现需订正条目）。

### 5.4 降级链（F3）

无降级：本批关键结论全部走**仓内检索**通道，未发起外部检索，故无失败通道。

## 6. 对设计的输入

### 6.1 可用的技术方案

- S-1：构建器内 `policy if policy is not None else TradabilityPolicy()` 取 eps（单源、跟随默认值）。
- S-2：抽出 `_norm_code(x)` 私有助手，`list_date` 与 `st_overrides` 共用。
- S-3：只加测试不动生产代码（仅适用于 ②）。

### 6.2 关键约束

- **INV-0（P-006 INV-1 延续）**：默认路径（`tradability_inputs=None`）零变更；TP6-11 六项基线字面量逐位锁定。
- **INV-0'**：`build_tradability_inputs` 在 `policy=None` + 键同形输入下，meta 13 键逐键、逐值不变。
- 不改 `TradabilityInputs` 字段与 `apply_tradability` 签名。
- 不引入新依赖；Python 3.9 语法。

### 6.3 风险

- R-1：③ 若把「精确匹配」整体替换为归一化映射，可能改变重复键/异常键行为 → 采用「精确优先 + 归一化回退」。
- R-2：① 若把 `inputs.policy` 从 `None` 改为实例化对象，会改变下游语义 → 不动 `inputs.policy`，只取 eps。
- R-3：② 的一字跌停用例易被「已跌停不可卖」逻辑干扰计数 → 用例需构造 high==low==down 且方向可判。

## 7. 参考文献

1. `backtest/tradability.py` v3.9.9（L16 / L194-199 / L385-397）
2. `backtest/tradability_inputs.py` v3.9.9（L12 / L71-85 / L95-110 / L117-126 / L150）
3. `tests/test_tradability.py` v3.9.9（L150-158 / L238-266 / L387）
4. `tests/test_tradability_inputs.py` v3.9.9（L46-56 / L113-131 / L150-153）
5. `spec/p006-tradability-engine-integration/DESIGN.md` v1.3 §14 D-6-7
6. `spec/p006-tradability-engine-integration/CHECKLIST.md` v1.4 §8.2

---

**Review 签字**: Step 2 内联复核（本文档作者，逐条 E1 重读） 日期: 2026-11-23
