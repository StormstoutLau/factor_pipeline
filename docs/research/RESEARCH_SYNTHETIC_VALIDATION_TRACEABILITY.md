# RESEARCH — 模拟数据验证与问题链路追溯（盲区扫描）

> **版本**: v1.3（v1.0 = 2026-11-19 盲区扫描；v1.1 = 同日补充调研：细化 E1-E5 落地方案 + 外部依据 + 本地适配；v1.2 = 步骤 8 对齐：§18 U4/U5 状态升级为已核实，证据见 DESIGN §18；v1.3 = 步骤 8 残留核实：U3 与规则表四个日期 U9-U12 升级已核实，U13 登记费率版本化简化）
> **批次**: 步骤 2 调研（盲区扫描型，非新功能立项）
> **日期**: 2026-11-19
> **范围**: 全仓——`backtest/`（engine / factor_metrics / data_bridge / execution / governance / data_contract / golden_master / specification_logger）、`modules/`（10 模块）、`scripts/`（17 个入口）、`tests/`（约 2001 项）
> **输入问题**: 当前框架是否缺少模拟数据验证？计量与回测模块的计算准确性、意图实现准确性、涨跌停/调仓/买卖等边界处理是否有盲区？后续任何模块开发如何做到「每步可验证、问题可追溯」？此前调研批次是否已有类似机制、能否扩展？
> **产出定位**: 事实盘点 + 盲区清单 + 可操作落地方案（不实施；实施归后续版本）
> **补充调研锚点**: 官方规则 6 条、学术 5 条、工程实践/社区 10 条，逐条标注 URL 与核实状态（§10 总表）；无法核实的明确列为未核实（§18）

---

## §1 调研问题清单

| # | 问题 | 回答位置 |
|---|------|---------|
| Q1 | 已有多少「模拟数据验证」能力？分别覆盖哪一层？ | §2（M1-M9） |
| Q2 | 主回测链路（引擎/组合）的计算口径是否被独立验证过？ | §3.1 / §3.2 |
| Q3 | 「意图实现准确性」有无系统性检查手段？举实例 | §3.3（B2 实例） |
| Q4 | 涨跌停 / 停牌 / 调仓 / 买卖成本等交易现实性边界，实现与测试各覆盖到哪？ | §3.1（B1）/ §3.4 |
| Q5 | 每个处理步骤的中间产物能否追溯（输入→输出→参数）？ | §3.5（B5） |
| Q6 | 新增模块时，验证方式是否可复用、可自动化？ | §4 / §5 |
| Q7 | 之前调研批次的机制是「已有可扩展」还是「需另起」？ | §5（结论：扩展） |
| Q8 | 哪些盲区已知且已被文档披露、哪些是本次新发现？ | §3 表「状态」列 |

---

## §2 现状盘点——已有机制（9 项，逐项证据）

| # | 机制 | 覆盖层 | 证据（路径:行号） | 能力边界 |
|---|------|--------|------------------|---------|
| M1 | pytest 共享 fixture | 单元测试输入 | [tests/conftest.py:27-106](../../tests/conftest.py#L27-L106)：`sample_factor_data`（100×50，5% 随机 NaN）、`clean_factor_data`、`high_missing_data`（35% NaN）、`extreme_outlier_data` | 纯高斯随机 + 手工极值；**无 A 股结构**（涨跌停日、停牌缺口、板块、ST、复权跳变），无统一面板工厂 |
| M2 | Golden master 数值基线 | 管线因子输出 | [golden_master.py:34-70](../../backtest/golden_master.py#L34-L70)（manifest/report）、[:196-257](../../backtest/golden_master.py#L196-L257)（capture→parquet）；基线 `tests/golden/govbase_v1_synth`；测试 [test_golden_master.py](../../tests/test_backtest/test_golden_master.py)（T16-T20） | 只覆盖「因子输出」一个切面；**不含中间步骤产物**，无 step 级粒度 |
| M3 | 数据契约 | 数据层 | [data_contract.py:63-79](../../backtest/data_contract.py#L63-L79)（FieldSpec：freshness/PIT/coverage/nan_rate/value_range）、[:117-135](../../backtest/data_contract.py#L117-L135)（`DataSnapshot.stable_hash`）、[:302-324](../../backtest/data_contract.py#L302-L324)（`_content_digest`） | 校验「在场数据」的合法性与内容摘要；**无法感知应到而缺席**（幸存者偏差，已在 [RESEARCH_GOVERNANCE_BASE.md:92](RESEARCH_GOVERNANCE_BASE.md#L92) 披露） |
| M4 | 治理记录 + G2 门禁 | 决策/验收 | [governance.py:346-424](../../backtest/governance.py#L346-L424)（GovernanceRecord）、[:631-708](../../backtest/governance.py#L631-L708)（evaluate_g2）、[:876-943](../../backtest/governance.py#L876-L943)（DuckDB/JSONL + payload hash） | 记录「结论级」元数据；**不回写回测中间过程**，`data_snapshot_hash` 在 `backtest/*.py` 无调用点（grep 零命中） |
| M5 | 规格日志 content_hash | 研究规格 | [specification_logger/spec_log.py:130-150](../../backtest/specification_logger/spec_log.py#L130-L150)、[pre_registration.py:39-59](../../backtest/specification_logger/pre_registration.py#L39-L59) | 锁「规格文本」；不锁数据/中间产物 |
| M6 | execution 合成 fixture | 执行/容量层 | [EXECUTION_V3.8.0 §5.4](../EXECUTION_V3.8.0_EXECUTION_CAPACITY.md#L514-L516)：`synthetic_impact` / `synthetic_ohlc`（零区间日、一字板、负估计）/ `synthetic_minute_month`（3 股×1 日×241 bar） | **唯一**一组「按场景设计」的合成数据；仅 3 个文件内联，未抽公共工厂 |
| M7 | 异构复审探针框架 | 跨模块二次取证 | [2026-11-19-v3.8.0 审计报告](../audit/2026-11-19-v3.8.0-execution-capacity-audit.md) Phase 1（5 视角 × 48 探针）；v3.7.0 同构（89 探针） | 方法论成熟（独立重实现 / MC / 复放 / 文档交叉），但**探针脚本为一次性 TEMP 文件，审计后删除**，不可累积、不可回归 |
| M8 | 外部对拍 | 计量 | `scripts/verify_hac_stata.py`、`scripts/stata_breakpoint_crosscheck.py`、v3.7.0 NW vs statsmodels（`≤1e-10`） | 覆盖 HAC/断点；**回测收益链、成本、容量以外的模块无对拍** |
| M9 | 验证入口脚本 | 端到端 | `scripts/verify_capacity_impact.py`、`verify_stat_evidence.py`、`verify_portfolio_backtest.py`、`contract_gate.py` | 每个脚本自带 5-10 条断言（如 V1-V10），断言散落各脚本、**口径不统一、无公共断言库** |

**盘点结论**：验证能力「点多面广但不成体系」——数据层（M3）、输出层（M2）、记录层（M4/M5）、执行层（M6）、审计层（M7）各有机制，**层与层之间没有共享的合成数据源、没有统一的不变量登记、没有步骤级产物链**。

---

## §3 盲区扫描（10 项）

严重度口径：**P1** = 可能产出错误结论且无任何验证拦截；**P2** = 有验证缺口或已知口径偏差；**P3** = 已披露/影响有限。

### 3.1 B1 主回测链路完全没有交易现实性建模（P1，已部分披露）

| 事实 | 证据 |
|------|------|
| `backtest/` 全目录 grep `rebalance|佣金|印花税|滑点|trading_cost|cost_bps` → **零命中**（仅 `scripts/` 与 `docs/` 有） | 本次扫描 |
| 前向收益 = `close[t+1]/close[t]-1`，仅过滤 NaN/≤1e-10，无停牌处理 | [engine.py:130-152](../../backtest/engine.py#L130-L152) |
| 仓位构建每期独立生成，无换手成本、无持仓延续、无成交约束 | [engine.py:156-203](../../backtest/engine.py#L156-L203) |
| 涨跌停判定只存在于执行/容量证据层（`detect_limit_lock`），主回测**不调用** | [classification.py:57-66](../../backtest/execution/core/classification.py#L57-L66) 与 [loaders.py:96-99](../../backtest/execution/shell/loaders.py#L96-L99) 是唯一使用点 |
| 组合层成本只在研究脚本内：`cost = 2*turnover*fee_bps/1e4`，四档 0/10/20/30bp | [verify_portfolio_backtest.py:8](../../scripts/verify_portfolio_backtest.py#L8)、[:151-179](../../scripts/verify_portfolio_backtest.py#L151-L179) |
| 已披露：不做涨跌停/停牌逐笔可成交性建模；H7「月末调仓可成交性未建模，`stock_suspend` 留作后续」 | [RESEARCH_PORTFOLIO_BACKTEST.md:21](RESEARCH_PORTFOLIO_BACKTEST.md#L21)、[:126](RESEARCH_PORTFOLIO_BACKTEST.md#L126) |
| 已披露：费率统一 10bp/单边，未区分印花税/过户费（影响 <0.1%/年） | [PORTFOLIO_CAPACITY_IMPACT_STRESS.md:259](../analysis/PORTFOLIO_CAPACITY_IMPACT_STRESS.md#L259) |

**风险**：IC/ICIR 类指标不受影响（不涉及成交），但任何以组合收益/Sharpe 为结论的路径（研究脚本、报告）都隐含「完美成交」假设；若后续把研究脚本升级为模块，该假设会静默进入主链路。**测试侧**：`tests/` 中涨跌停仅 [test_execution_classification.py](../../tests/test_execution_classification.py) 3 例、停牌仅 [test_data_contract.py:82-89](../../tests/test_backtest/test_data_contract.py#L82-L89) 覆盖率 1 例，**回测链路零覆盖**。

### 3.2 B2 意图实现准确性缺陷实例：`_build_positions` 的 NaN 排序（P2，本次新发现，已实证）

```python
# backtest/engine.py:197-201
sorted_idx = np.argsort(f)
positions[t, sorted_idx[:n_select]] = -1.0 / n_select
positions[t, sorted_idx[-n_select:]] = 1.0 / n_select
```

`np.argsort` 升序把 NaN 排在**末尾**，而多头取 `[-n_select:]` → **NaN 股票被选为多头**。实证（本机 numpy）：

```
f = [1.0, 2.0, nan, 3.0, nan] → argsort = [0 1 3 2 4] → 多头 = 索引 [2, 4]（均为 NaN）
```

- **意图**：在「有效因子值」上取 top-N（对照 [factor_metrics.py:298-338](../../backtest/factor_metrics.py#L298-L338) 的 `compute_long_short_returns`，其正确使用 `_get_valid_mask(f, r)` 后再排序）。
- **实际影响面**：`positions` 仅用于 `compute_turnover`（[engine.py:245-246](../../backtest/engine.py#L245-L246)），多空收益走正确的 `compute_long_short_returns` → 影响限于**换手率指标失真**（停牌/缺失日越多偏差越大），不影响 IC/LS 收益。
- **为何长期未被发现**：现有测试无「高缺失 + 手工构造排序真值」用例；`conftest.py` 的 5% 随机 NaN 在 100×50 下很少达到 `n_select` 量级；且无「排序类函数的有效域不变量」断言。

### 3.3 B3 无统一合成面板工厂（P1，结构性缺口）

- 现有合成数据 4 处来源：conftest 高斯（M1）、execution 三组合成（M6）、golden 基线 parquet（M2）、各脚本内联随机（如 `verify_portfolio_backtest.py`）。
- **没有一个**能构造「A 股结构面板」的公共设施：可注入涨跌停日（按板块比例）、停牌区间、ST 标记、复权跳变、行业/市值分层、因子缺失与延迟披露（`loaded_at`）。
- 后果：① 每个模块各自造数据，场景覆盖不可比；② 无法做「同一场景跨模块一致性」测试（例如 imputer 输出 → neutralizer → backtest 的端到端契约）；③ 审计探针（M7）每次都要重写造数逻辑，用完即删。

### 3.4 B4 涨跌停判定不区分板块，且无「可成交性→回测」闭环（P2/P3）

- `detect_limit_lock` 仅 `h==l` 或 `v==0 且 o=c=h=l`，**不区分 ST 5% / 主板 10% / 科创创业板 20% / 北交所 30%**；已在 [report.py:53-56](../../backtest/execution/shell/report.py#L53-L56) 标 `[未核实]`（design Q2 决定不硬编码规则）。
- 判定结果只进容量证据层（`limit_lock` 汇总），**没有**「当日涨停 → 禁止买入 / 跌停 → 禁止卖出」的调仓约束实现。
- 停牌：`data_contract` 把 `suspend` 当普通字段做覆盖率校验，回测链路无停牌持仓处理（收益前值填充 vs 0 收益 vs 剔除，未定义）。

### 3.5 B5 无步骤级产物 hash 链（P1，追溯性核心缺口）

- `DataSnapshot.stable_hash`（[data_contract.py:117-135](../../backtest/data_contract.py#L117-L135)）可对**数据快照**生成稳定 hash，但 `backtest/*.py` 中 grep `data_snapshot_hash|provenance|lineage` **零命中** → 未接线到任何管线。
- `GovernanceRecord` 有 `data_snapshot_hash` 字段（M4），但记录的是「人工填写的结论上下文」，不是「每次运行的逐步产物」。
- 现状下定位「某次报告的数字为何偏了」只能靠人工重跑，无 per-step 输入/输出/参数指纹，无法二分定位问题步骤。

### 3.6 B6 模块级验证覆盖不均（P2）

- `modules/` 共 10 个模块（imputer / winsor / neutralizer / orthogonalizer / decoupler / fingerprint / endogeneity_check / endogeneity_estimators / adaptive_winsor / …），核心文件 55+。
- 已有针对性验证的只有少数：LR-06（`test_truncation_invariant_on_synthetic_panel`，[EXECUTION_V3.3.5:483](../EXECUTION_V3.3.5_PL06_MIXED_WINSORIZE_CAUSALITY.md#L483)）、imputer 无前视（`lookahead_free_imputer`）、正交化器（grouped/rolling 测试）。
- 大部分模块的测试是「样例断言」（给定输入→期望输出），**没有不变量/性质断言**（单调性、置换不变、尺度等变、无前视、边界钳制），这正是 B2 这类 bug 的温床。

### 3.7 B7 不变量只存在于文档，不可执行（P2）

- v3.8.0 有 15 条不变量（[CONSISTENCY_REVIEW §7](../audit/CONSISTENCY_REVIEW_V3.8.0_EXECUTION_CAPACITY.md#L107-L123)），v3.6.0/v3.7.0 同理；它们靠人写在 review 文档里，实施靠 checklist 逐行勾选。
- **没有**机器可读的模块级「不变量登记表」，也无法在每次全量回归中自动重跑；文档与代码漂移只能靠审计发现。

### 3.8 B8 数据契约无法覆盖「应到而缺席」（P3，已披露）

幸存者偏差（退市股缺失）不可由在场数据校验检测，已在 [RESEARCH_GOVERNANCE_BASE.md:92](RESEARCH_GOVERNANCE_BASE.md#L92) 披露，属方法论边界而非实现缺陷。

### 3.9 B9 审计探针用完即删（P3）

v3.7.0 89 探针、v3.8.0 48 探针均在审计后删除，只留 `out/review_*_results.txt` 文本。**探针代码本身不进入仓库** → 同类缺陷（如 B2 的排序有效域问题）在下一个模块重复出现时无法复用检查。

### 3.10 B10 验证入口脚本断言口径分散（P3）

17 个 `scripts/` 入口各自内联断言（V1-V10 等），无公共断言库/报告 schema，无法汇总成「一次运行看全部健康度」。

---

## §4 外部工程实践参考（4 条，含核实状态）

| # | 实践 | 与本仓的对应 | 核实状态 |
|---|------|-------------|---------|
| R1 | Property-based testing（Hypothesis）：声明「对所有输入都应成立的性质」，由框架随机搜索反例，包括边界/NaN/极值 | 对应 B2/B6/B7：把「不变量」写成可执行性质而非样例断言；科学计算领域已有专门实践（`Falsify your Software` 报告在 Numpy/Astropy 中发现真实 bug） | 已核实（Hypothesis 官方文档 + 科学计算 PBT 论文摘要） |
| R2 | Data lineage 标准（OpenLineage）：以 `run_id` + `job` + `dataset` 事件描述「哪次运行、哪一步、读写哪些数据」 | 对应 B5：步骤级追溯的最小事件模型 | 已核实（OpenLineage 对象模型与 getting-started） |
| R3 | Golden/approval testing：数值回归基线 + 显式 review 后重生成 | 已采用（M2），可扩展为 step 级 | 仓内已实现，无需外部核实 |
| R4 | 数据契约（schema + freshness + owner + 版本） | 已采用（M3），可扩展 synthetic 场景引用 | 仓内已实现；业界实践见 v3.6.0 调研 |

> 引用克制说明：本批调研以仓库内证据为主，外部引用 4 条均已在 §4 标注核实状态；未逐项核对页码/DOI 的条目不进入设计约束（E5 级）。

---

## §5 扩展方案——复用已有机制（结论：扩展，不另起）

### 5.1 判断

此前批次**已有**三类可扩展资产：数据契约（M3）、golden master（M2）、异构复审探针方法论（M7）。缺的是「统一合成场景」「不变量常驻化」「步骤级产物链」三块拼图，**不需要**引入外部框架（Hypothesis/OpenLineage 仅作设计参照，零新增核心依赖可满足需求）。

### 5.2 五项扩展（按依赖顺序）

| # | 扩展 | 落点（复用/新增） | 解决盲区 | 默认影响 |
|---|------|------------------|---------|---------|
| E1 | **合成场景库** `tests/synthetic/`：`PanelSpec`（涨跌停日/停牌区间/ST/板块/复权跳变/缺失模式/因子延迟）+ `build_panel()`，确定性 seed | 复用 conftest 风格；抽 M6 三组合成为通用构造器 | B3、B6 | 仅测试代码，生产零影响 |
| E2 | **不变量登记与常驻**：每模块一个 `INVARIANTS` 声明（名称/适用域/断言函数），pytest 参数化统一执行；把 M7 探针里的「独立重实现/边界真值表」沉淀为可回归用例 | 新增 `tests/invariants/`；探针骨架来自 M7 | B2、B7、B9 | 测试代码 |
| E3 | **步骤级追溯** `PipelineTrace`：每步记 `run_id / step / input_hash / params_hash / output_hash / diagnostics`，落 `out/trace/<run_id>.jsonl`；失败时输出首个 hash 断裂步骤 | 复用 M3 `_content_digest`、M4 `GovernanceStore` 的 hash/写入模式；`data_snapshot_hash` 接线 | B5 | **开关默认关闭**，关闭时零变更 |
| E4 | **回测交易现实性层** `backtest/tradability.py`：可成交性（涨停禁买/跌停禁卖/停牌不可交易）+ T+1 + 成本函数（佣金/印花税/过户费分离）；回测引擎以 `tradability_policy=None` 默认保持现状 | 复用 M6 `detect_limit_lock`；成本口径对齐研究脚本 | B1、B4 | 默认 None → 逐位不变 |
| E5 | **验证入口统一**：`scripts/verify_all.py`（聚合现有 verify_* 的健康度摘要 + 统一 JSON schema） | 复用 M9 各脚本，不重写其断言 | B10 | 只读汇总 |

### 5.3 设计约束（沿用本仓纪律）

1. 零新增核心依赖（E1/E2 用 numpy/pytest 即可；不引入 Hypothesis）。
2. 默认路径逐位不变：E3/E4 必须 `None`/`False` 默认关闭，并由 golden/快照测试锁定。
3. Python 3.9 语法；不修改 `backtest/__init__.py` 与 `backtest/data_contract.py`（如需字段扩展走新模块）。
4. 每个扩展须先有红测试（合成数据场景 → 断言失败 → 实现 → 转绿），与既有 TDD 纪律一致。

> **v1.1 补充**：E1-E5 的细化方案见 §11-§15（外部依据 / 本地适配 / 文件级落地 / 测试矩阵 / 验收），B2 的修复落地见 §16，实施顺序与风险见 §17。原 §5.2 表格保留为索引。

---

## §6 推荐分期（建议 v3.9.0 立项，非本批实施）

| 期 | 内容 | 验收（可观察） |
|----|------|--------------|
| Phase A | E1 + E2：合成场景库 + 不变量常驻；先覆盖 `backtest/engine.py`、`factor_metrics.py`、`modules/factor_imputer`、`modules/factor_orthogonalizer` | 每个模块 ≥5 条不变量；B2 类缺陷由常驻用例直接红；全量回归零新增失败 |
| Phase B | E3：PipelineTrace 骨架 + 与 golden/契约产物对齐 | 一次运行产出 `out/trace/*.jsonl`；人为注入一步错误可在 trace 中唯一定位到 step |
| Phase C | E4：交易现实性层（默认关闭）+ 成本分离口径 | 关闭时默认路径 SHA256 不变；开启时涨停禁买/跌停禁卖/停牌不可交易各有对应用例 |
| Phase D | E5：聚合入口 | 单命令输出全仓验证摘要 JSON |

---

## §7 明确不做

1. 不引入 Hypothesis / Great Expectations / OpenLineage 等外部框架（仅作设计参照）。
2. 不做跨环境 bitwise golden 断言（沿用 v3.6.0 裁决 [RESEARCH_GOVERNANCE_BASE.md:333](RESEARCH_GOVERNANCE_BASE.md#L333)）。
3. 不在本批修复 B1/B2（调研不实施；B2 修复可并入 Phase A 首个红用例）。
4. 不做实盘级撮合/逐笔成交仿真（与 [RESEARCH_PORTFOLIO_BACKTEST.md:21](RESEARCH_PORTFOLIO_BACKTEST.md#L21) 非目标一致）。

---

## §8 未核实项（E5 级，不得单独支撑结论）

| # | 项 | 状态 |
|---|----|------|
| U1 | ST 5% / 科创板 20% / 北交所 30% 的涨跌幅规则文本 | 未核（design Q2 已决定不硬编码） |
| U2 | 印花税/过户费 2026 年现行费率 | 未核（成本分离设计时再核） |
| U3 | OpenLineage 事件字段全集与本仓 trace 的映射细节 | 仅核对象模型层，字段级映射未核 |
| U4 | `modules/` 55+ 核心文件的逐文件不变量候选清单 | 仅抽查 4 模块，全量清单待 Phase A |

> **历史快照注记（v1.2，步骤 8）**：本表为 v1.0 盲区扫描时点的未核实项；v1.1 补充调研后，其中规则/费率类
> 已在 §18 重核（U1 → 已核 O2/O3；U2 → 已核 O4；U3 → 部分核 O5），U4（不变量候选清单）仍待 Phase A。
> 现行状态一律以 §18 为准（两处 U 编号双义见 §18 编号注记）。

---

## §9 与现有文档关系

| 本文 | 关系 |
|------|------|
| [RESEARCH_GOVERNANCE_BASE.md](RESEARCH_GOVERNANCE_BASE.md) | M3/M4/M2 的来源；本文 B8 与其 §2.5 幸存者偏差披露一致 |
| [RESEARCH_PORTFOLIO_BACKTEST.md](RESEARCH_PORTFOLIO_BACKTEST.md) | B1 的 H7「可成交性未建模」原始披露；本文 E4 是其后续落地候选 |
| [2026-11-19-v3.8.0 审计报告](../audit/2026-11-19-v3.8.0-execution-capacity-audit.md) | M6/M7 的来源；本文 E2 建议把其一次性探针常驻化 |
| [WORKFLOW_METHODOLOGY.md](../WORKFLOW_METHODOLOGY.md) §13.2 | 本文为步骤 2 产出；E1-E5 若立项，须补步骤 3 设计 + 步骤 4 review |

---

## §10 补充调研锚点总表（v1.1）

> 核实口径：**已核实** = 本轮实际检索到原文/官方页面并摘录关键读数；**部分核实** = 检索到二手转述或官方页面摘要，未见全文；**未核实** = 仅工程常识，不进设计约束。
> **F1 来源日期**：全部外部来源**读取日 = 2026-11-19**（本轮检索/抓取日）；文献发布日 = 年份 + 卷期页码（A1: 2021, 1(1): 217-232）；官方规则带发布/施行日期；内部文件写版本 + 行号区间。无「近期/最新」表述。
> **F3 降级链**：`mcp_paper-search（search_semantic/semantic 全部 0 命中）→ openalex/crossref 命中（A1/A2/O 组）；mcp_stackexchange（quant/scicomp 全部 0 命中、quota 耗尽）→ WebSearch 覆盖社区案例（C7-C11）；A1 表 2 数字经期刊站 EN 页二次抓取双核`。
> 本表 21 条中：官方规则 5 条（已核实 4 / 部分核实 1）、学术 4 条（已核实 3 / 部分核实 1）、工程与社区 12 条（已核实 10 / 部分核实 2）→ 合计**已核实 17 / 部分核实 4**（RULE-2 逐行计数）。

### 10.1 官方规则（决定 E4 的规则表设计）

| # | 锚点 | 关键事实 | 核实 |
|---|------|---------|------|
| O1 | [上交所交易规则（2026 修订）](http://big5.sse.com.cn/site/cht/www.sse.com.cn/lawandrules/sselawsrules2025/trade/universal/c/c_20260424_10816492.shtml) | 科创板涨跌幅限制比例 **20%**；IPO 上市后前 5 个交易日不设价格涨跌幅限制 | 已核实 |
| O2 | [CSRC 上海监管局：A股交易新规](https://www.csrc.gov.cn/shanghai/c105566/c7643909/content.shtml) | 2026-07-06 起：沪深主板风险警示股票（ST/*ST）涨跌幅由 **5% → 10%**；创业板/科创板风险警示股票维持 **20%**；北交所 **30%** | 已核实 |
| O3 | [新华网：A股交易新规落地](https://app.xinhuanet.com/news/article.html?articleId=202607064093623b870d43a8b442b994dace0b23) | 同上，涉及沪深主板风险警示个股 150+ 只 | 已核实 |
| O4 | [上交所股票投资费用说明](https://one.sse.com.cn/onething/gptz/) | 印花税：成交金额 **0.5‰，向出让方单边征收**；证管费 0.002% 双向；经手费 A 股 0.0341‰ 双向（规费合计 0.0541‰，含在佣金内） | 已核实 |
| O5 | [粤开证券费用表](http://www.ykzq.com/Article.html?id=879) / [准上市费用一览](https://www.zhunshangshi.com/k/234.html) / [新华网：中国结算过户费下调](https://www.news.cn/2022-04/28/c_1128605983.htm) | 过户费 **0.01‰ 双向**（2022-04-29 起；此前沪深 0.02‰、北 0.025‰）；佣金上限 3‰、买卖双向、每笔不足 5 元按 5 元收 | 已核实（过户费：中国结算通知经新华网/中证网转述；佣金上限仍为券商口径） |

> **对设计的直接影响**：涨跌幅规则**在 2026 年发生过变更**（主板 ST 5%→10%）。因此 E4 的规则表必须「**按生效日期版本化**」，不能常量硬编码——这一条从「设计偏好」升级为「事实约束」。

### 10.2 学术（决定 E2/E4 的验证方法）

| # | 锚点 | 关键事实 | 支撑 | 核实 |
|---|------|---------|------|------|
| A1 | [《计量经济学报》2021：基于反事实模拟的中国股市涨跌停板磁吸效应研究](https://cjoe.cjoe.ac.cn/EN/10.12012/2020-0008-16) | 股价变动达 ±9% 后，到达涨跌停板的**实际条件概率 69.7% vs 理论 56.7%，高 13.0%（1% 显著）**；摘要另证**跌停侧磁吸更强**（stronger near lower price limit） | E4：涨跌停临近时价格加速，「涨停可成交」假设会系统性高估成交率 | 已核实（双页核：正文表 2 检索片段 + 期刊页摘要/引言抓取；作者 Lu Chang/Liu Yang/Yang Xiaoguang，2021, 1(1): 217-232） |
| A2 | [The impacts of circuit breakers on China's stock market (Pacific-Basin Finance Journal, 2020)](https://doi.org/10.1016/j.pacfin.2020.101343) | 交易阻碍具有流动性效应；投资者行为加速价格触及限制；个股与指数存在显著**向下磁吸** | E4：跌停侧不可卖出的保守处理有实证基础 | 部分核实（摘要） |
| A3 | [Falsify your Software: validating scientific code with property-based testing](https://pdfs.semanticscholar.org/ee15/0432ac2a4ab0b0c98feb4da721c23482ede6.pdf) | 性质测试四类（界内、单调、不变、等价）在 Numpy/Astropy 中发现其他手段遗漏的真实 bug | E2：不变量断言的价值论证 | 已核实（摘要 + 四类性质） |
| A4 | [pandas 贡献指南：Using hypothesis](https://pandas.pydata.org/pandas-docs/version/2.3/_sources/development/contributing_codebase.rst.txt) / [Hypothesis 教程](https://hypothesis.readthedocs.io/en/latest/tutorial/introduction.html) | 描述全部合法输入 → 自动搜索失败样例 → **总是报告最小反例** | E2：不变量失败时可直接得到最小复现输入 | 已核实 |

### 10.3 工程与社区（决定 E1/E3/E5 的实现形态）

| # | 锚点 | 关键事实 | 支撑 | 核实 |
|---|------|---------|------|------|
| C1 | [pandera: Data Synthesis Strategies](https://pandera.readthedocs.io/en/v0.21.0/data_synthesis_strategies.html) | **由 schema 元数据自动生成合成数据**（底层 hypothesis），用于单测 | E1：`PanelSpec` → 面板的「schema 驱动生成」思想 | 已核实 |
| C2 | [DVC + MLflow 端到端 lineage](https://dvc.org/blog/end-to-end-lineage-with-dvc-and-amazon-sagemaker-ai-mlflow-apps/) | Git tag → DVC commit 恢复数据；MLflow run 记录 `data_git_commit_id` 关联数据版本 | E3：run 与数据版本的绑定方式 | 已核实 |
| C3 | [A Taxonomy of Tools for Reproducible ML Experiments](https://ceur-ws.org/Vol-3078/paper-81.pdf) | DVC 提供**完整 code/data provenance**，管线自动表示为 DAG，每个产物有历史 | E3：step 级 DAG + 产物 hash | 已核实（摘要） |
| C4 | [OpenLineage Object Model](https://openlineage.io/docs/next/spec/object-model/) | `run_id`（建议 UUIDv7）+ `job` + `dataset` 事件模型；实时 emit lineage | E3：trace 事件字段命名借鉴 | 已核实 |
| C5 | [wickra-proof（GitHub）](http://raw.githubusercontent.com/wickra-lib/wickra-proof/HEAD/ARCHITECTURE.md) | `report_hash = blake3(canonical_bytes)`，报告内嵌 `engine_version`（版本不同则 hash 不同、显式标注） | E3：hash 必须绑定版本，否则跨版本不可比 | 已核实 |
| C6 | [状态 hash 链实践](https://dredyson.com/how-i-built-and-optimized-a-steam-multiplayer-backtesting-pipeline-for-algorithmic-trading-a-quants-complete-step-by-step-guide-to-high-frequency-trading-infrastructure-python-for-finance-and-pr/) | 每 N 个事件对组合状态做 SHA-256；跨机器比对 hash 链，**链一致即确定性成立，分歧点即非确定性起点** | E3：失败定位算法（首个 hash 分歧步） | 部分核实（个人博客，工程经验） |
| C7 | [A 股回测改造清单](https://easyclaw.ijinshan.com/skills/stock-analysis-for-quant/a-share-backtest-rules.html) | 「把涨跌停当作**成交前置条件**，而不是事后修正」；顺延到下一可成交日或放弃信号，两种处理写进报告 | E4：接口应返回「可成交/不可成交+原因」，而非改收益 | 已核实 |
| C8 | [ZVT A 股数据避坑](https://easyclaw.ijinshan.com/skills/zvt/a-share-data-traps.html) | 盘中涨停=封板挂单排队 → **保守做法：触及涨停即视为不可买入**；严格做法需封单量/成交笔数（成本高） | E4：默认保守口径 + 可扩展钩子 | 已核实 |
| C9 | [T+1 与可成交性核对清单](https://www.zpyztech.com/a-share-t1-limit-up-tradability-constraints-deep-dive/) | 买入应在**信号收盘确认后的下一根开盘**；卖出日 ≥ 买入日后第一个可卖日；检查买入点是否落在连续涨停 | E4：T+1 与「信号日 vs 成交日」分离 | 已核实 |
| C10 | [One-bar ablation test](https://www.bigmovealgo.com/post/lookahead-bias-trading) | 把执行价整体前移一根 bar 重跑；若 Sharpe/收益崩塌 → 原结果含同 bar 成交（前视） | E2：无前视不变量的**可执行版本** | 已核实 |
| C11 | [PiT 单测（two-timestamp schema）](https://www.quantgenie.ai/blog/lookahead-bias) | 每个 feature 带 `available_at`；断言评估期不存在 `available_at > prediction_time` 的行 | E2：`data_bridge` 的 PIT 不变量 | 已核实 |
| C12 | [pytest-html-reporter](https://pypi.org/project/pytest-html-reporter/) / [junit-report-merger](https://www.npmjs.com/package/junit-report-merger) | 分片运行的 JUnit XML 可合并为单一总计；报告输出统一 schema | E5：聚合入口的形态 | 已核实 |

---

## §11 E1 细化——合成场景库（`tests/synthetic/`）

### 11.1 外部依据 → 本地映射

| 外部依据 | 直接可用的结论 | 本地落点 |
|---------|--------------|---------|
| C1 pandera schema 驱动生成 | 用「规格对象」生成数据，而非每次手写数组 | `PanelSpec` dataclass 作为唯一数据规格 |
| A3 PBT 四类性质 | 合成数据必须**携带真值**，才能断言「判定=真值」 | `SyntheticPanel` 同时返回 `true_limit_hit` / `true_suspend` 等 ground truth |
| C7/C8 社区避坑 | 关键场景是「涨停不可买、跌停不可卖、停牌、ST、复权跳变」 | `SCENARIOS` 六个内置场景 |

### 11.2 本地适配分析（与现有代码的关系）

| 现状 | 适配方式 |
|------|---------|
| `tests/conftest.py:27-106` 四个 DataFrame fixture，无字段语义 | 保留不动（既有 2001 项测试依赖）；`tests/synthetic/` 为**新增包**，不替换 conftest |
| `backtest/execution` 的三组合成 fixture 内联在测试文件内（M6） | 迁移为 `SCENARIOS["limit_heavy"]` 等场景的消费者；原测试可逐步改引用（非必须） |
| 数据契约 `FieldSpec`（[data_contract.py:63-79](../../backtest/data_contract.py#L63-L79)）已有字段元数据 | `SyntheticPanel` 的列名/单位对齐 `FieldSpec` 语义（price/volume/amount），可直接喂契约校验 |
| `detect_limit_lock` 只认 `h==l` / 零量平盘（不认 `limit_pct`） | 生成器必须让「涨停」同时表现为 `h==l`（一字板）或可辨识形态；`true_limit_hit` 另存，用于未来 E4 的规则化判定 |

### 11.3 落地文件与签名（Python 3.9，零新依赖）

```
tests/synthetic/__init__.py        # 导出 PanelSpec / SyntheticPanel / build_panel / SCENARIOS
tests/synthetic/panel.py           # 数据结构 + 生成器
tests/synthetic/scenarios.py       # 6 个内置场景（dict[str, PanelSpec]）
tests/test_synthetic_panel.py      # 生成器自身的不变量测试（先红后绿）
```

```python
@dataclass(frozen=True)
class PanelSpec:
    n_dates: int = 120
    n_stocks: int = 60
    start: str = "2022-01-04"
    seed: int = 20261119
    board_mix: Tuple[Tuple[str, float], ...] = (
        ("main", 0.60), ("star", 0.20), ("gem", 0.15), ("bse", 0.05))
    limit_up_ratio: float = 0.0      # 每期触及涨停的股票比例
    limit_down_ratio: float = 0.0
    suspend_ratio: float = 0.0
    suspend_len: int = 5             # 停牌连续交易日数
    st_ratio: float = 0.0
    factor_missing: float = 0.0      # 因子缺失率（不含停牌）
    loaded_lag_days: int = 0         # 因子披露延迟（写入 loaded_at）
    adj_jump_days: Tuple[int, ...] = ()   # 除权跳变日索引


@dataclass(frozen=True)
class SyntheticPanel:
    dates: np.ndarray                # (T,) datetime64[D]
    codes: np.ndarray                # (N,) int64
    board: np.ndarray                # (N,) '<U4'
    open: np.ndarray                 # (T, N)
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    amount: np.ndarray
    factor: np.ndarray               # (T, N)
    loaded_at: np.ndarray            # (T, N) datetime64[D]
    industry: np.ndarray             # (N,) '<U8'
    mktcap: np.ndarray               # (T, N)
    true_limit_hit: np.ndarray       # (T, N) int8：1=涨停, -1=跌停, 0=未触及
    true_suspend: np.ndarray         # (T, N) bool
    spec: PanelSpec


def build_panel(spec: PanelSpec) -> SyntheticPanel:
    """确定性生成：同 spec 两次调用逐位一致（np.random.default_rng(spec.seed)）。"""
```

### 11.4 场景库（6 个）

| 场景名 | 关键参数 | 验证目标 |
|--------|---------|---------|
| `clean` | 全 0 异常 | 基线：各模块在无异常面板上的行为 |
| `limit_heavy` | `limit_up_ratio=0.08, limit_down_ratio=0.08` | 一字板/涨跌停判定、可成交性（E4） |
| `suspend_gap` | `suspend_ratio=0.10, suspend_len=5` | 停牌期价格/收益/因子处理、`data_contract` 覆盖率 |
| `st_mixed` | `st_ratio=0.10` + 2026 前后两套 `limit_pct` | 板块规则版本化（E4） |
| `stale_factor` | `loaded_lag_days=5` | PIT 可见性（`_apply_loaded_at_lag`，勘误随 EXECUTION v1.1 §9 M-1） |
| `adj_jump` | `adj_jump_days=(40, 41)` | 复权跳变对前向收益与 σ 的影响 |

### 11.5 测试矩阵与验收

| 测试 | 断言 | 红形态（先写） |
|------|------|---------------|
| `test_synthetic_determinism` | 同 spec 两次 `build_panel` 所有数组逐位一致 | `ImportError: tests.synthetic` |
| `test_synthetic_ground_truth` | `limit_heavy` 下 `true_limit_hit` 比例与 spec 一致（±1 只） | 同上 |
| `test_limit_hit_recognized` | `detect_limit_lock(panel.high, panel.low, panel.close, panel.open, panel.volume)` 与 `true_limit_hit != 0`（一字板部分）逐元素一致 | 同上 |
| `test_pit_no_future` | `stale_factor` 下过滤后不存在 `loaded_at > trade_date` 的有效值（C11） | 同上 |
| `test_suspend_zero_return` | `suspend_gap` 停牌段收益应为 0 或 NaN（口径待 E4 定义，先锁定现状） | 同上 |

**验收判据**：① 6 场景全部可由 `SCENARIOS[name]` 一键构建；② `limit_heavy` 下判定函数与 ground truth 一致率 100%；③ 生成器自身 5 例全绿；④ 全量回归零新增失败。

**风险**：合成面板可能「过于干净」而给出虚假安全感 → 强制要求每个场景**同时**跑一次真实数据回放对照（复用 v3.8.0 已用过的 2023-03-01 单日分钟数据模式）。

---

## §12 E2 细化——不变量常驻（`tests/invariants/`）

### 12.1 外部依据 → 本地映射

| 外部依据 | 结论 | 本地落点 |
|---------|------|---------|
| A3 PBT 四类性质（界内/单调/不变/等价） | 不变量优先选这四类，避免写成第二个样例断言 | `INVARIANTS` 条目的 `kind` 字段限定四类 |
| A4 最小反例 | 失败时应输出最小输入（本仓零依赖 → 用「场景名 + 首个失败索引 + 实际/期望值」代替） | 断言消息强制含 `first_bad_index` |
| C10 one-bar ablation | 「把未来整体扰动/前移一根 bar，历史输出必须不变」是最强的无前视检查 | `no_lookahead` 类不变量统一用「扰动未来 + 逐位比较」 |
| C11 PiT 断言 | `available_at <= prediction_time` 全行成立 | `pit_visible` 类不变量 |

### 12.2 现状缺口（为什么必须有）

- v3.8.0 的 15 条不变量写在 [CONSISTENCY_REVIEW §7](../audit/CONSISTENCY_REVIEW_V3.8.0_EXECUTION_CAPACITY.md#L107-L123)，**不可执行**；v3.7.0/3.6.0 同构。
- 步骤 10 探针（M7）每次审计后删除，同类缺陷无法回归拦截 —— B2 就是典型：排序有效域问题在 `engine.py` 存在多年，无任何断言拦截。

### 12.3 落地文件与签名

```
tests/invariants/__init__.py       # INVARIANTS 注册表（list[Invariant]，frozen dataclass 直接构造）
tests/invariants/registry.py       # 注册函数 register() + 汇总执行
tests/invariants/test_registry.py  # 参数化执行：pytest.mark.parametrize("case", INVARIANTS)
tests/invariants/backtest_engine.py    # B2 及其它引擎不变量
tests/invariants/factor_metrics.py
tests/invariants/data_bridge.py
tests/invariants/execution_core.py     # 从 v3.8.0 探针沉淀（P1 8 项 + P4 15 项）
```

```python
@dataclass(frozen=True)
class Invariant:
    name: str            # "engine.positions_valid_domain"
    module: str          # "backtest.engine"
    kind: str            # "bound" | "monotonic" | "invariant" | "equivalence"
    scenario: str        # SCENARIOS 键
    check: Callable[[SyntheticPanel], Tuple[bool, str]]  # (ok, first_failure_detail)
```

### 12.4 首批不变量清单（12 条，按模块）

| # | 名称 | 类 | 断言 | 对应盲区 |
|---|------|----|------|---------|
| I1 | `engine.positions_valid_domain` | bound | 因子为 NaN 的股票在 positions 中权重必须为 0 | **B2（先红）** |
| I2 | `engine.fwd_return_no_lookahead` | invariant | 扰动 `close[t+1:]` 后 `fwd_ret[:t]` 逐位不变 | B1/B2 |
| I3 | `engine.turnover_range` | bound | `0 <= turnover <= 2` | B2 影响面 |
| I4 | `metrics.ls_returns_valid_pairs` | bound | LS 收益仅由 `valid=f∧r` 的股票决定（注入异常值到 NaN 股票不影响结果） | 意图准确性 |
| I5 | `metrics.rank_ic_bounds` | bound | Rank IC ∈ [-1, 1] | 计量准确性 |
| I6 | `bridge.pit_visible` | invariant | 过滤后不存在 `loaded_at > trade_date` 的有效值 | B5/C11 |
| I7 | `bridge.ffill_no_future` | equivalence | `fill_missing='nan'` 与 `'ffill'` 在无缺失输入上逐位一致 | 意图准确性 |
| I8 | `classify.limit_lock_truth` | equivalence | `detect_limit_lock(high, low, close, open_, volume)` 与 `true_limit_hit != 0`（一字板部分）一致 | B4 |
| I9 | `impact.monotonic_participation` | monotonic | 冲击随参与率单调不减、随 σ 单调不减 | v3.8.0 沉淀 |
| I10 | `decay.half_life_identity` | equivalence | `half_life(ρ)=ln0.5/lnρ`（rtol 1e-12） | v3.8.0 沉淀 |
| I11 | `bootstrap.block_bounds` | bound | `1 <= b <= n//3` | v3.8.0 沉淀 |
| I12 | `winsor.truncation_invariance` | invariant | 前 t 期在扰动未来后逐位不变 | 已有 LR-06 沉淀 |

### 12.5 验收

① B2 在 I1 下**先红**（`frozen` 观测 → 断言失败）；② 12 条不变量全部可在 `<5s` 内跑完（纯合成面板）；③ 每条失败消息含 `scenario / first_bad_index / expected / actual`；④ 全量回归零新增失败。

---

## §13 E3 细化——步骤级追溯（`backtest/trace.py`）

### 13.1 外部依据 → 本地映射

| 外部依据 | 结论 | 本地落点 |
|---------|------|---------|
| C4 OpenLineage | 事件三条核心：`run_id` / `job(step)` / `dataset(input,output)` | JSONL 事件字段命名 |
| C5 wickra-proof | hash 必须绑定 `engine_version`，跨版本不可比 | `trace_version` + `code_version` 写入每行 |
| C6 状态 hash 链 | 逐检查点 hash；链一致=确定性；**首个分歧点=非确定性起点** | `find_first_divergence(trace_a, trace_b)` |
| C2/C3 DVC | 每步记录依赖 hash + 产物 hash（dvc.lock 思维） | `input_hash` / `output_hash` / `params_hash` |
| 本仓 M3 | `_content_digest` 已实现「列名+shape+首尾/中间样本+NaN 计数」摘要 | 直接复用，不重写 |

### 13.2 本地适配分析

| 现状 | 适配方式 |
|------|---------|
| `DataSnapshot.stable_hash` 存在但零调用（B5） | trace 的 `input_hash` 即其首次接线点；不修改 `data_contract.py`，由 trace 调用 |
| 管线入口分散（`scripts/verify_*`、研究脚本） | trace 以**上下文管理器**方式接入，不要求管线重构：`with trace.step("load", inputs={...}) as st: ...`（与 §13.4 签名一致） |
| 默认路径必须逐位不变 | `PipelineTrace.enabled=False` 默认；关闭时 `TraceStep` 为 no-op（零 IO、零 hash 计算） |
| 已有 `out/*.json` 证据文件 | trace 落 `out/trace/<run_id>.jsonl`，不改动既有工件 |

### 13.3 事件 schema（JSONL，每行一个 step）

```json
{
  "trace_version": "1",
  "run_id": "20261119T101500-3f9a2c",
  "code_version": "3.9.0",
  "step": "load.factor",
  "seq": 3,
  "started_at": "2026-11-19T10:15:01.123456",
  "params_hash": "sha256:...",
  "inputs": [{"name": "factor.parquet", "hash": "sha256:...", "rows": 2500, "cols": 5000}],
  "outputs": [{"name": "factor_aligned", "hash": "sha256:...", "rows": 2500, "cols": 4800}],
  "diagnostics": {"nan_rate": 0.012, "warnings": []},
  "status": "ok"
}
```

### 13.4 落地文件与签名

```
backtest/trace.py                 # PipelineTrace / TraceStep / content_hash / find_first_divergence
tests/test_trace.py               # 6 例（确定性、链完整、关闭零影响、分歧定位、JSONL 可读、异常步骤落 status=error）
```

```python
class PipelineTrace(object):
    def __init__(self, path, enabled=False, code_version=None): ...
    def step(self, name, **params):  # 返回 TraceStep 上下文管理器
        ...

def content_hash(obj) -> str:
    """ndarray/DataFrame/dict/list → 'sha256:' + hex；canonical 序列化（排序键、float64 字节）。"""

def find_first_divergence(trace_a: Path, trace_b: Path) -> Optional[Dict]:
    """逐 seq 比较 (step, params_hash, inputs[].hash, outputs[].hash)，返回首个不一致事件。"""
```

### 13.5 失败定位算法（可操作）

1. 同 `run_id`/同输入重跑两次 → `find_first_divergence(t1, t2)` 必须为 `None`（确定性验收）。
2. 结果异常时，按 `seq` 从后往前找**第一个** `diagnostics` 越界（如 `nan_rate` 突增）或 `hash` 与基线 trace 不同的 step → 该 step 即问题起点。
3. 基线 trace 由 `out/trace/baseline_<version>.jsonl` 固化（与 golden master 同源，显式 review 后更新）。

### 13.6 验收

① `enabled=False` 时全量回归零差异（golden 快照逐位）；② `enabled=True` 跑一次 `scripts/verify_capacity_impact.py --calibrate` 产出完整 JSONL（≥10 step）；③ 人为在 `runner` 注入一步偏差，`find_first_divergence` 定位到该 step；④ `trace_version`/`code_version` 每行必填。

---

## §14 E4 细化——回测交易现实性层（`backtest/tradability.py`）

### 14.1 外部依据 → 本地映射

| 外部依据 | 直接可用的结论 | 本地落点 |
|---------|--------------|---------|
| O1/O2/O3（官方规则，2026-07-06 变更） | 涨跌幅 = f(板块, 是否 ST, 日期)；主板 ST 由 5%→10% | `LimitRule` 带 `effective_from/effective_to`，**规则表而非常量** |
| A1 磁吸效应（±9% 后到达涨跌停条件概率 69.7% vs 56.7%） | 价格越接近涨跌停越可能「封死」，「触及即可成交」会系统性高估成交率 | 默认「触及涨跌停 → 不可成交」，不做事后收益修正 |
| A2 向下磁吸 | 跌停侧同样存在加速与流动性枯竭 | 跌停禁卖与涨停禁买对称实现 |
| C7 成交前置条件 | 可成交性判定应发生在**权重生成之后、收益计算之前** | `apply_tradability(positions) -> (effective, report)` |
| C8 封板挂单排队 | 保守口径「触及即不可买」；严格口径需封单量（数据成本高） | 默认保守；`strict_hook` 预留但 v1 不实现 |
| C9 信号日 vs 成交日 | 买入在信号确认后的下一根 bar；卖出日 ≥ 买入日 + T+1 | `execute_at="next_open"` + `t_plus_1=True` |
| O4/O5 费用 | 印花税 0.5‰ **仅卖出**；过户费 0.01‰ 双向；佣金双边、最低 5 元 | `CostModel` 分项，禁止合并成单一 `fee_bps` |

### 14.2 本地适配分析

| 现状 | 适配方式 |
|------|---------|
| `detect_limit_lock`（[classification.py:57-66](../../backtest/execution/core/classification.py#L57-L66)）只认一字板/零量平盘 | **不替换**：它是一字板判定；E4 新增「触及涨跌停价」判定（`high >= limit_price` / `low <= limit_price`），二者组合覆盖「一字板」与「盘中触及」 |
| 回测引擎 `_build_positions` 逐期独立（[engine.py:156-203](../../backtest/engine.py#L156-L203)），无成交约束 | 在 positions 与收益之间插入 `apply_tradability`；引擎新增可选 `tradability_policy`，默认 `None` |
| 成本仅在 `scripts/verify_portfolio_backtest.py:151-179` 内联（`2*turnover*fee_bps/1e4`） | 抽出 `CostModel` 到模块；脚本保留原函数以保证既有输出逐位不变（脚本改为可选调用，v1 不动） |
| 无板块/ST 元数据 | `PanelSpec`（E1）已含 `board` 与 `st_ratio`；真实数据侧由 `data_contract` 字段扩展或外部注入（v1 仅合成） |
| T+1 完全未建模 | 以「权重变更日」为信号日，实际成交落在下一交易日开盘；T+1 通过「买入当日不可卖」的持仓锁定数组实现 |

### 14.3 落地文件与签名（Python 3.9，零新依赖）

```
backtest/tradability.py            # LimitRuleTable / limit_price / TradabilityPolicy / apply_tradability / CostModel
tests/test_tradability.py          # 9 例（见 14.5）
```

```python
@dataclass(frozen=True)
class LimitRule:
    board: str                 # main | star | gem | bse
    is_st: bool
    pct: float                 # 0.10 / 0.20 / 0.30
    effective_from: str        # "2020-01-01"
    effective_to: Optional[str] = None   # None = 至今


# 规则表（注释内必须引用 §10.1 的官方 URL 与日期）
DEFAULT_LIMIT_RULES: Tuple[LimitRule, ...] = (
    LimitRule("main", False, 0.10, "2020-01-01"),
    LimitRule("main", True, 0.05, "2020-01-01", "2026-07-05"),   # O2：新规前 5%
    LimitRule("main", True, 0.10, "2026-07-06"),                  # O2：新规后 10%
    LimitRule("star", False, 0.20, "2020-01-01"),                 # O1
    LimitRule("star", True, 0.20, "2020-01-01"),
    LimitRule("gem", False, 0.20, "2020-08-24"),                  # 创业板注册制改革
    LimitRule("gem", True, 0.20, "2020-08-24"),
    LimitRule("bse", False, 0.30, "2021-11-15"),
    LimitRule("bse", True, 0.30, "2021-11-15"),
)


def limit_price(prev_close: np.ndarray, rule_pct: np.ndarray,
                side: str = "up") -> np.ndarray:
    """涨/跌停价：round(prev_close * (1 ± pct), 2)（A 股价格最小变动 0.01）。"""


@dataclass(frozen=True)
class TradabilityPolicy(object):
    execute_at: str = "next_open"        # next_open | same_close（后者仅供对照）
    block_buy_on_limit_up: bool = True
    block_sell_on_limit_down: bool = True
    block_suspended: bool = True
    t_plus_1: bool = True
    rules: Tuple[LimitRule, ...] = DEFAULT_LIMIT_RULES


def apply_tradability(target_w: np.ndarray, prev_close: np.ndarray,
                      high: np.ndarray, low: np.ndarray,
                      suspended: np.ndarray, board: np.ndarray,
                      is_st: np.ndarray, policy: TradabilityPolicy,
                      trade_dates: np.ndarray) -> Tuple[np.ndarray, Dict]:
    """返回 (effective_w, report)。

    入参全部为显式数组（(T,N) 或 (N,)）——生产模块**不得**依赖 tests/synthetic
    的 SyntheticPanel 类型（依赖方向：tests → backtest，与 v3.8.0 不变量 #8
    「Core/生产层不 import 脚本/测试」同纪律）。board/is_st 为 (N,) 元数据，
    prev_close/high/low/suspended 为 (T,N)；limit 价由 prev_close + 规则表现算。

    report = {"blocked_buy": int, "blocked_sell": int, "blocked_suspend": int,
              "t1_locked": int, "carried": int, "deferred": int}
    """


@dataclass(frozen=True)
class CostModel(object):
    commission_bps: float = 2.5          # 双边
    min_commission: float = 5.0
    stamp_tax_bps: float = 5.0           # 卖出单边（0.5‰）
    transfer_fee_bps: float = 0.01       # 双向（0.01‰）
    slippage_bps: float = 0.0

    def cost(self, buy_notional: float, sell_notional: float) -> float:
        """买入：佣金 + 过户费 + 滑点；卖出：佣金 + 印花税 + 过户费 + 滑点。"""
```

### 14.4 处理口径（必须写进报告的三条）

1. **不可成交的处理**：默认「顺延到下一个可成交日」（`carried/deferred` 计数入 report）；不做「事后按收盘价强行成交」。
2. **触及即不可成交**：`high >= limit_price_up - 1e-8` → 当日买入不可成交；`low <= limit_price_down + 1e-8` → 当日卖出不可成交。一字板同样命中（`h==l` 自然满足）。
3. **T+1**：当日新增多头仓位锁定 1 个交易日，`t1_locked` 计数入 report；停牌期间持仓不变但计入 `blocked_suspend`。

### 14.5 测试矩阵（9 例，先红后绿）

| # | 用例 | 场景 | 断言 |
|---|------|------|------|
| T1 | 涨停禁买 | `limit_heavy` + `block_buy_on_limit_up` | 涨停日 `effective_w` 买入侧全 0，`blocked_buy > 0` |
| T2 | 跌停禁卖 | `limit_heavy` | 跌停日卖出侧全 0 |
| T3 | 停牌不可交易 | `suspend_gap` | 停牌日 `effective_w == prev_w`（持仓冻结） |
| T4 | T+1 锁定 | 构造单日换仓 | 买入次日不可卖，`t1_locked > 0` |
| T5 | 规则版本化 | `st_mixed` + 日期 2026-07-03 / 07-06 | 主板 ST 限价分别 5% / 10% |
| T6 | 跌停价取整 | 手工 `prev_close=10.00, pct=0.10` | 跌停价 9.00、涨停价 11.00（round 2 位） |
| T7 | 成本分离 | 买入 100 万、卖出 100 万 | 卖出成本比买入多 `stamp_tax_bps` 对应金额 |
| T8 | 默认策略 None | `tradability_policy=None` | 与既有 `_build_positions` 输出逐位一致 |
| T9 | 顺延计数 | 连续两日涨停后开板 | `deferred` 计数与第三日实际成交一致 |

**验收判据**：① 9 例全绿；② `policy=None` 时 golden/快照逐位不变；③ report 六项计数之和与 `blocked` 事件逐日可对账；④ 规则表每条带 `effective_from` 且被 T5 覆盖。

**风险与回滚**：默认 `None` → 生产零影响；规则表随监管变化需人工更新（注释强制带 URL 与日期）；无封单量数据 → 报告必须声明「保守口径，可能低估成交」。

---

## §15 E5 细化——验证入口聚合（`scripts/verify_all.py`）

### 15.1 外部依据 → 本地映射

| 外部依据 | 结论 | 本地落点 |
|---------|------|---------|
| C12 JUnit XML 可合并 | 多来源测试结果可聚合成单一总计 | 复用 `pytest --junitxml`（本仓已在用） |
| M9 现有 17 个 `scripts/` 入口 | 断言各自内联、口径不一 | 统一「检查项 JSON」schema，不重写断言 |
| 本仓 `out/*.json` 工件 | 已有可读证据文件 | 聚合并记录每个工件的 SHA256 |

### 15.2 落地文件与签名

```
scripts/verify_all.py              # 聚合入口（只读；不重跑重计算）
tests/test_verify_all.py           # 3 例（聚合正确、缺失容错、exit code 规则）
docs/VERIFICATION_SCHEMA.md        # 统一 schema（新文档，可选）
```

统一检查项 schema（各 `verify_*.py` 增加 `--report-json PATH`，默认行为不变）：

```json
{
  "tool": "verify_capacity_impact",
  "version": "3.9.0",
  "generated_at": "2026-11-19T10:15:00",
  "status": "pass",
  "checks": [{"id": "V1", "ok": true, "detail": "index aligned"}],
  "artifacts": [{"path": "out/capacity_impact.json", "sha256": "82728ce1..."}]
}
```

`verify_all.py` 行为：
1. 扫描 `out/verification/*.json`（各脚本新产出的报告），按 `tool` 去重取最新；
2. 任意 `status == "fail"` → 汇总 `fail`，exit 1；`warn` → exit 0 并列出；
3. 输出 `out/verification/summary.json` + 终端表格（工具 / 状态 / 检查项数 / 工件 hash 前 8 位）；
4. 缺失某个工具的 JSON → 标 `missing`（不算 fail，但列出）。

### 15.3 验收

① 现有 4 个 `verify_*.py` 增加 `--report-json` 后默认输出逐位不变；② `verify_all.py` 在全部 pass 时 exit 0、注入一个 fail 时 exit 1；③ `summary.json` 含全部工具与工件 SHA256；④ 全量回归零新增失败。

---

## §16 B2 修复落地设计（`_build_positions` 有效域）

### 16.1 红测试（先写，`tests/invariants/backtest_engine.py` I1）

```python
def check_positions_valid_domain(panel):
    factor = panel.factor.copy()
    factor[:, :5] = np.nan                      # 前 5 只永久缺失
    engine = _engine_with_factor(factor)        # 复用 E1 场景
    pos = engine._build_positions(factor)
    bad = np.argwhere(np.isnan(factor) & (pos != 0.0))
    return (len(bad) == 0,
            "first_bad=%s weight=%.4f" % (bad[0].tolist(), pos[tuple(bad[0])])
            if len(bad) else "")
```

辅助 `_engine_with_factor`：用 `FactorBacktestEngine.__new__` 跳过 `__init__`，仅注入
`config = {'ls_method': 'top_n', 'top_n': 0.2}`（`_build_positions` 读取
`self.config.get('ls_method'/'top_n')`，[engine.py:167-168](../../backtest/engine.py#L167-L168)），
不触发 `run()`，避免依赖 dataloader。

**预期红读数**（按默认 `PanelSpec`：n_stocks=60、top_n=0.2、5 列 NaN 推导）：
`n_valid = 55 → n_select = int(55×0.2) = 11 → 权重 = 1/11 ≈ 0.0909`；
NaN 列（0-4）被 `np.argsort` 排至末尾并整体落入多头侧 `[-11:]`，row-major 首个违例 =
`first_bad=[0, 0] weight=0.0909`（NaN 股票被赋予多头权重）。

### 16.2 修复（最小变更；标注「既有 / 新增」，防止重复插入）

```python
# backtest/engine.py::_build_positions（行号对照现状 :156-203）
f = factor[t]                              # 既有 :171
valid = ~np.isnan(f)                       # 既有 :172（域定义不变，不改 inf 语义）
valid_idx = np.flatnonzero(valid)          # 新增
...
if n_select < 1 or n_valid < n_select * 2:  # 既有 :194（勿重复插入）
    continue
sorted_local = valid_idx[np.argsort(f[valid_idx])]   # 新增（替换 :197 的 np.argsort(f)）
positions[t, sorted_local[:n_select]] = -1.0 / n_select    # 既有 :199（仅改名 sorted_idx→sorted_local）
positions[t, sorted_local[-n_select:]] = 1.0 / n_select    # 既有 :201（同上）
```

要点：① 仅把 `argsort` 的作用域从「全体列」收窄到 `valid_idx`（根治 NaN 排在末尾被选为多头）；
② 域定义沿用原 `~np.isnan`，**不**顺带把 inf 排除（避免行为扩散；inf 处理属独立议题）；
③ 两侧对称与 `1/n_select` 权重语义不变；④ 净 diff = 1 行新增 + 1 行替换 + 2 处改名。

### 16.3 影响量化（实施时必做）

| 步骤 | 方法 | 期望 |
|------|------|------|
| 修复前后 turnover 对比 | 用 `conftest.sample_factor_data`（5% NaN）跑 `_evaluate_factor` | 修复后 turnover **下降**（不再含 NaN 股票换手）；给出行情级 diff |
| 真实数据影响 | 用 2023-03-01 单日分钟面板（同 v3.8.0 先例）构造因子缺失 | 记录 diff 幅度，判断是否需要更新历史报告读数 |
| 既有测试 | 全量 `pytest tests -q` | 零新增失败；若有 turnover 相关断言需同步（属预期行为变更，须在 CHANGELOG 声明） |

### 16.4 兼容性声明

- 仅影响 `compute_turnover` 的输入（`positions`），不影响 IC/LS 收益/Sharpe（`compute_long_short_returns` 本就用 valid mask）。
- 不修改 `backtest/__init__.py`、`backtest/data_contract.py`。
- 默认路径（`scripts/verify_capacity_impact.py` 无参数）不经过 `_build_positions`，SHA256 应保持不变（实施时验证）。

---

## §17 落地顺序、依赖与风险

### 17.1 依赖图

```
E1 合成场景库 ──┬─→ E2 不变量常驻（消费场景，I1 先红→B2 修复）
                └─→ E4 交易现实性（消费场景 + ground truth）
E3 步骤级追溯（独立，可并行）
E5 聚合入口（依赖各 verify_* 加 --report-json，独立）
B2 修复（可独立先行；E2 的 I1 为其回归护栏）
```

### 17.2 推荐顺序（每步独立可验收）

| 步 | 内容 | 关键验收 |
|----|------|---------|
| S1 | B2 独立修复 + I1 红→绿（不依赖 E1/E2 全量） | 57→58 例全绿；turnover diff 留档；默认 SHA256 不变 |
| S2 | E1 场景库 + 5 例 | 6 场景可一键构建；确定性/真值一致 |
| S3 | E2 注册表 + 12 条不变量（含 I1 迁移） | 12 条 <5s；失败消息含 first_bad |
| S4 | E3 trace + 6 例 | 关闭零差异；分歧定位到 step |
| S5 | E4 tradability + 9 例 | None 默认逐位不变；9 例全绿 |
| S6 | E5 聚合 + 4 脚本 `--report-json` | 默认输出不变；summary 含 SHA256 |

### 17.3 风险登记

| # | 风险 | 缓解 |
|---|------|------|
| R1 | 合成面板「过于理想」→ 虚假安全感 | 每个场景强制真实数据回放对照（v3.8.0 先例） |
| R2 | E4 规则表随监管变化过期 | `effective_from/to` + 注释带官方 URL + 测试覆盖变更日 |
| R3 | E3 hash 跨平台/跨版本不可比 | 每行写 `trace_version`/`code_version`；float64 字节序固定 |
| R4 | B2 修复改变 turnover 历史读数 | 独立提交 + CHANGELOG 声明 + diff 量化留档 |
| R5 | 不变量写多后维护成本 | 每条绑定 `module` + `scenario`，失败自动指向责任模块；每版本 review 一次 |

---

## §18 未核实项与后续核实计划（v1.3 更新：步骤 8 残留核实完成）

| # | 项 | 状态 | 后续 |
|---|----|------|------|
| U1 | 主板 ST 2026-07-06 前为 5% 的具体起止日期 | 已核实（O2/O3：新规前后） | — |
| U2 | 印花税 0.5‰ 卖出单边 | 已核实（O4 上交所官方） | — |
| U3 | 过户费 0.01‰ 双向 | 已核实（步骤 8：中国结算 2022-04-28《关于降低股票交易过户费收费标准的通知》，自 2022-04-29 起沪深 A 股 0.02‰、北京市场 0.025‰ 统一下调为 **0.01‰ 双向**；新华网/中证网报道） | — |
| U4 | 创业板 20% 的生效日 2020-08-24 | 已核实（步骤 4 设计 review 升级：深交所 2020-08-21 发布会 + CSRC 答记者问，证据链接见 DESIGN §18；步骤 8 回写，调研 v1.2） | — |
| U5 | 北交所 30% 与开市日 2021-11-15 | 已核实（步骤 4 设计 review 升级：北交所官方报告 + 新华网，证据链接见 DESIGN §18；步骤 8 回写，调研 v1.2） | — |
| U6 | 封单量/成交笔数数据可得性 | 未核实 | 本仓无逐笔数据；v1 不做严格口径 |
| U7 | OpenLineage 字段级映射（仅核对象模型） | 部分核实 | E3 v1 只借鉴命名，不追求兼容 |
| U8 | 中国涨跌停磁吸效应的英文期刊版本 | 未核实（A1 为中文期刊，A2 为熔断） | 设计引用以 A1 中文原文为准 |
| U9 | 科创板开市日 2019-07-22 | 已核实（步骤 8：[上交所总经理工作报告](http://www.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20200423_5052375.shtml)：2019-06-13 开板、**07-22 首批 25 家集中上市**；证监会/央视/人民日报同源） | — |
| U10 | 创业板开市日 2009-10-30 | 已核实（步骤 8：[深交所上市公告](https://www.szse.cn/disclosure/notice/company/t20091026_500285.html)：28 家公司 **2009-10-30** 在创业板上市；深交所新闻同源） | — |
| U11 | ST 制度起始日 1998-04-22 | 已核实（步骤 8：沪深交易所 1998-04-22 宣布特别处理制度；上海证券报/中证网/中国经济网 + 学术论文；首家 ST「辽物资」1998-04-28，晚于制度宣布日） | — |
| U12 | 注册制前创业板 ST 涨跌幅 5% | 已核实（步骤 8：[深交所《关于创业板风险警示股票和退市整理期股票交易制度安排的通知》](https://www.szse.cn/lawrules/rule/repeal/rules/P020231230545303417288.pdf)：「《特别规定》实施前，创业板风险警示股票……价格涨跌幅限制比例为 **5%**」；[深交所投教 2020-08-07](https://investor.szse.cn/index/update/t20200807_580310.html) 同源） | — |
| U13 | 过户费费率历史版本（2022-04-29 前） | 已核实（此前沪深 0.02‰、北 0.025‰ 双向） | v1 **不做费率版本化**：`CostModel.transfer_fee_bps=0.1` 固定为现行费率，报告须声明「成本口径为当前费率，历史回测用现值近似」 |

> **编号注记（v1.2，步骤 8）**：本节 U1-U13 与 §8 的 U1-U4 编号重复但含义不同——§8 是 v1.0 盲区扫描时点的
> 未核实快照表，本节是现行状态表（v1.3 后规则/费率类全部收敛）；跨文档引用 U 编号一律以本节为准（§8 已加历史快照注记）。

---

**结论（v1.1）**：
1. **缺少的是骨架，不是验证点**：数据契约（M3）、golden（M2）、治理记录（M4）、探针方法论（M7）四类资产已在，缺共享合成场景、可执行不变量、步骤级 hash 链、回测交易现实性。
2. **五项扩展全部可操作落地**：E1（`tests/synthetic/`，6 场景 + ground truth）、E2（`tests/invariants/`，12 条不变量）、E3（`backtest/trace.py`，JSONL + 首个分歧定位）、E4（`backtest/tradability.py`，规则表版本化 + T+1 + 成本分项）、E5（`scripts/verify_all.py`，统一 schema 聚合）；均已给出文件级落点、函数签名、测试矩阵与验收判据。
3. **外部依据充分且已核实**：涨跌幅规则 2026-07-06 变更（O2）、印花税 0.5‰ 卖出单边（O4）、磁吸效应 ±9% 后到达涨跌停条件概率 69.7% vs 56.7%（A1）、PBT 最小反例（A4）、one-bar ablation（C10）、PiT 断言（C11）、DVC/OpenLineage/状态 hash 链（C2-C6）——全部指向「规则版本化 + 可执行不变量 + 步骤 hash 链」三个设计决定。
4. **首步建议**：先做 S1（B2 独立修复 + I1 红→绿），它以最小代价验证「不变量护栏」的有效性，再展开 E1/E2。

---

## §19 步骤 2 review 记录（2026-11-19，按 WORKFLOW_METHODOLOGY §2.1 阶段 3-6 执行）

### 19.1 阶段 3 — 快速 Review（接口对齐 / 算术 / 逻辑 / 依赖）

**代码锚点逐条核对（全部 PASS）**：`engine.py:130-152 / 156-203 / 167-168 / 245-246`、
`factor_metrics.py:298-338`、`classification.py:57-66`（H2 修复后含 `& (c == l)`）、
`loaders.py:96-99`、`report.py:53-56`、`data_contract.py:63-79 / 117-135 / 302-324`、
`governance.py:346 / 631 / 792 / 876`（payload_hash）、`golden_master.py:196-257`、
`conftest.py:27-106`、`verify_portfolio_backtest.py:8 / 151-179`——行号与签名逐一实读核对。
另核：`scripts/verify_capacity_impact.py` **不引用** `FactorBacktestEngine` / `_build_positions`
（grep 零命中）→ §16.4「B2 修复不影响默认路径」声明成立。

**算术复核（PASS）**：I2 无前视（`fwd_ret[k]=(close[k+1]-close[k])/close[k]`，扰动
`close[t+1:]` 不影响 `fwd_ret[:t]`）；I3 换手界 ≤2（多空各 1）；I10 `ln0.5/ln0.9=6.578813`
（与 v3.8.0 探针 1f 实测一致）；T6 `10.00×1.10=11.00 / ×0.90=9.00`；T7 印花税差
`100 万×5bp=500 元`；T5 日期边界（新规 2026-07-06 施行，07-05→5%、07-06→10%，与规则表
`effective_to="2026-07-05"` 一致）；CostModel 万 2.5 佣金 < O5 上限 3‰。

**发现与修复（3 MAJOR + 5 MINOR，全部已修）**：

| # | 级别 | 位置 | 问题 | 修复 |
|---|------|------|------|------|
| M-1 | MAJOR（算术） | §16.1 | 预期红读数 `first_bad=[0,4] weight=0.200000` 错误：按默认 PanelSpec（n_stocks=60、5 列 NaN）应 n_valid=55 → n_select=11 → 权重 1/11≈0.0909，且 NaN 列 0-4 整体落入多头侧，row-major 首违例为 [0,0] | 改为 `first_bad=[0,0] weight=0.0909` 并附推导 |
| M-2 | MAJOR（接口依赖方向） | §14.3 | `apply_tradability(..., panel, ...)` 使生产模块依赖 `tests/synthetic.SyntheticPanel`（反向依赖，违反 v3.8.0 不变量 #8 同纪律） | 改为显式数组入参（prev_close/high/low/suspended/board/is_st）并写明依赖方向约束 |
| M-3 | MAJOR（前提未标注） | §16.1 | `_engine_with_factor` 未说明需注入 `config={'ls_method','top_n'}`（`_build_positions` 读取 self.config），否则 AttributeError | 补辅助函数构造说明 + engine.py:167-168 锚点 |
| m-1 | MINOR | §16.2 | 代码块把既有行与新增行混排，易致实施者重复插入 :194 守卫 | 逐行标注「既有 :行号 / 新增」，净 diff 改为「1 新增 + 1 替换 + 2 改名」 |
| m-2 | MINOR | §13.2 vs §13.4 | `with TraceStep(trace, ...)` 与 `trace.step(name)` 两处接口不一致 | 统一为 `with trace.step(...)` |
| m-3 | MINOR | §12.3 | 「@invariant 装饰器」与 frozen dataclass 直接构造矛盾 | 统一为 `register()` + dataclass |
| m-4 | MINOR | §11.5 / §12.4 I8 | `detect_limit_lock(panel)` 不符真实签名 `(high, low, close, open_, volume)` | 按签名展开 + `true_limit_hit != 0` 对齐 int8 编码 |
| m-7 | MINOR | §10 头部 | 缺 F1 来源日期与 F3 降级链（SPEC_PROCESS 契约取证字段） | 补「读取日 = 2026-11-19」与降级链（paper-search semantic 0 → openalex/crossref；stackexchange 0 → WebSearch） |

### 19.2 阶段 4 — 深度学术核实（MCP/抓取双轨）

| 锚点 | 声明 | 状态 | 证据 |
|------|------|------|------|
| A1 磁吸效应 | ±9% 后 69.7% vs 56.7%（+13.0pp，1% 显著） | ✅ VERIFIED（双页核） | 期刊 EN 页正文表 2 检索片段 + 本轮 WebFetch 摘要/引言全文（DOI 10.12012/2020-0008-16，2021, 1(1): 217-232）；摘要另证「跌停侧磁吸更强」，与 A2 方向一致 |
| A2 熔断向下磁吸 | 个股与指数显著向下磁吸 | ⚠️ UNVERIFIABLE（付费墙，仅摘要） | 摘要与 A1 中文结论方向一致，仅作旁证不作独立依据 |
| A3 PBT 四类性质 | bounds/monotonic/invariant/equivalence，Numpy/Astropy 真实 bug | ✅ VERIFIED | Semantic Scholar PDF 摘要逐句命中 |
| A4 最小反例 | Hypothesis 总是报告单一最小反例 | ✅ VERIFIED | pandas 官方贡献指南 + Hypothesis 官方教程 |

> A1 制度背景段（论文写作时点）描述「ST 涨跌幅 5%」与 O2「2026-07-06 起 10%」**不构成文献冲突**：
> 前者为 2020-2021 写作时点的制度快照，后者为新规；规则表版本化设计（`effective_from/to`）正是为此仲裁。

### 19.3 阶段 5 — 工程实践核实

C1-C12 状态维持 §10.3 判定（10 VERIFIED / 2 PARTIAL：C6 个人博客经验、C12 依赖第三方插件形态）。
本轮补充核实：`verify_capacity_impact.py` 无 engine 依赖（上文），支撑 §16.4。

### 19.4 门禁对账（SPEC_PROCESS Step 2 (a)-(d)）

| 门禁 | 状态 | 证据 |
|------|------|------|
| (a) FALSIFIED/错误断言已改写并记入修订记录 | ✅ | 本节 M-1（红读数算术）、M-2（接口依赖方向）已修复并在原文处标注；无遗留 ❌ MISMATCH |
| (b) CONFLICT / STEP_GAP_OPEN 已仲裁 | ✅ 无 OPEN | A1 制度背景 5% vs O2 新规 10% 仲裁为「规则表版本化」（§19.2 注）；无 STEP_GAP_OPEN |
| (c) 阻断性断言双源 | ✅ | A1：表 2 片段 + 期刊页抓取（双源）；O2：CSRC + 新华网（双源）；O4 印花税为上交所官方单源 → 已在 §18 U3 登记实施前再核；单源项不支撑 CRITICAL 结论 |
| (d) 假设区已转 [待定]/U 编号 | ✅ | U1-U8 全部带状态与后续核实计划（§18） |

### 19.5 F1-F5 出具形态

| 字段 | 出具 |
|------|------|
| F1 来源日期 | 外部来源读取日 = **2026-11-19**（§10 头部）；内部文件写 `版本 + 行号`（如 `engine.py:156-203 @ 3.8.0+H2fix`）。无「近期/最新」表述 |
| F2 来源版本 | 文献：期刊卷期（A1: 2021, 1(1): 217-232）+ DOI；官方：规则修订版（上交所 2026 修订）/ 施行日（2026-07-06）；内部：3.8.0 + 行号 |
| F3 降级链 | `search_semantic 0 命中 → openalex/crossref 命中`；`mcp_stackexchange（quant/scicomp）0 命中 + quota 耗尽 → WebSearch`；`A2 付费墙 → 仅摘要标 ⚠️`（§10 头部） |
| F4 引用验证表 | §10 即验证表（21 条 × 5 列含核实状态）；逐行计数：**已核实 17 / 部分核实 4**（O5、A2、C6、C12），与 §10 头部合计一致（RULE-2） |
| F5 先失败记录 | N/A：本批为文档（Layer-0），无代码/fixture 改动；S1 实施时按 TDD 出具先失败记录 |

### 19.6 证据等级自评

| 结论 | 等级 | 说明 |
|------|------|------|
| 代码行号/签名/依赖方向（§19.1 锚点表） | E1 | 读码可原样重放（Read/Grep） |
| 官方规则数字（O1-O5） | E1 | 官方页面原文，带施行日期 |
| 学术读数（A1 表 2 / A3 四类） | E1 | 原文摘要/正文抓取，双页核 |
| 社区工程结论（C7-C11） | E4 | 判断陈述，仅作实现形态线索，不作方法学依据 |
| B2 缺陷与红读数推导（§16） | E2 | 本机 numpy 实证 argsort 行为 + 算术推导；红读数以实施时实际运行为准 |
| E1-E5 落地方案（§11-§15） | E3/E5 | 设计提案；接口签名已对齐源码（E3），规则表数字 E1，其余待实施验证 |

### 19.7 二次 Review 结论

修复后复核：M-1 推导链（55→11→0.0909、[-11:] 覆盖列 0-4、row-major [0,0]）自洽；M-2 新签名
数组维度在 docstring 标明且不引入 tests→backtest 反向依赖；m-1 行号对照与现状
`engine.py:156-203` 逐行一致。**二次 review PASS，无新问题引入** → 本文可进入步骤 3（设计文档）。
