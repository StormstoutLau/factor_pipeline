# RESEARCH ABLATION DECOUPLER ARM

> **版本**: v1.0 (2026-11-13)
> **任务**: v3.4.4 — AblationRunner `decoupler` 消融臂（承接 ADR-036 / ADR-045）
> **调研工具**: mcp_paper-search (CrossRef) + 本地源码核对 + 既有已核实调研文档
> **范围**: 仅在 `dynamic_ab` 模式下生效的 AR 解耦组件，如何在四层消融框架中获得可归因、可复现的 L1 消融臂

---

## §1 调研问题清单

- **Q1**: `decoupler` 只在 `pipeline_mode='dynamic_ab'` 的 `DynamicFactorPipeline` 中存在，L1 消融应如何度量它？
- **Q2**: 该消融臂的参照系应选 B3（默认 unified）还是 `dynamic_ab` 完整臂？为什么？
- **Q3**: `module_enabled['decoupler']` 从 `AblationConfig` 到 `CompositeDecoupler` 的传递链路是否完整？
- **Q4**: ρ_step 是否应扩展到 `decoupler` 步骤？现有中间数据键是否支持？
- **Q5**: 兼容性边界是什么（哪些既有接口/结果数量/报告结构必须不变）？

---

## §2 学术文献调研

| 引用 | MCP 工具 | DOI / 标识 | 关键结论 | 状态 |
|------|---------|-----------|---------|------|
| Meyes, Lu, Waubert de Puiseau & Meisen (2019), *Ablation Studies in Artificial Neural Networks*, arXiv:1901.08644 | 本仓库 v3.4.3 调研已用 WebFetch(arXiv abs) 核实；本次沿用 | arXiv:1901.08644 / DOI: 10.48550/arXiv.1901.08644 | 消融通过**移除单个组件**考察其贡献；组件边界不清或同时移除多个组件时无法归因 | ✅ VERIFIED（前序文档 §2，CrossRef 未收录） |
| Athey & Imbens (2017), *The State of Applied Econometrics: Causality and Policy Evaluation*, J. Economic Perspectives 31(2):3-32 | search_crossref（本次） | 10.1257/jep.31.2.3 | 因果/贡献归因要求**控制组与处理组仅目标变量不同**，其余环境保持一致；补充分析（placebo/robustness）用于增强可信度 | ✅ VERIFIED（本次 Crossref 元数据） |
| Ledoit & Wolf (2008), *Robust performance hypothesis testing with the Sharpe ratio*, J. Empirical Finance 15(5):850-859 | 本仓库既有实现与文档 | — | Sharpe 差的 HAC 检验；消融比较的推断工具，本次不改变 | ✅ 已实现（`ledoit_wolf_hac_test`） |
| Politis & Romano (1992), *A Circular Block Resampling Procedure for Stationary Data* | 本仓库既有实现与文档 | — | 块自助保留时序依赖；消融比较的推断工具，本次不改变 | ✅ 已实现（`circular_block_bootstrap`） |

**Q1 结论**: 消融臂必须让**目标组件是唯一差异**。由于 `decoupler` 仅在 `dynamic_ab` 下存在，臂与参照都必须运行 `dynamic_ab`；否则"关闭 decoupler"在 unified 中是无操作（no-op），观测差异无法归因。

**Q2 结论**: 参照系必须是 **`dynamic_ab` 完整臂**（中性化 + AR 均开启），而不是默认 unified 的 B3。Athey & Imbens 的"仅目标变量不同"原则与 Meyes 的组件移除原则共同要求参照与实验臂处于同一执行模式；跨模式比较会把"Dynamic 管道差异"混入"AR 解耦贡献"。

---

## §3 本地代码事实核实

| # | 事实 | 证据（源码位置） | 状态 |
|---|------|----------------|------|
| A1 | L1 当前登记 5 个可消融模块，不含 `decoupler` | `backtest/ablation_runner.py:408` `L1_MODULES = ['imputer', 'winsorizer', 'scaler', 'neutralizer', 'orthogonalizer']` | ✅ |
| A2 | `run_l1` 的 4 个模块臂均使用默认 `routing_mode='full'`，`baseline_level='B3'` | `ablation_runner.py:901-908` | ✅ |
| A3 | `routing_mode='full'` 在 `_run_pipeline` 中被映射为 `pipeline_mode='unified'` | `ablation_runner.py:551-560` | ✅ |
| A4 | 因此默认 `run_l1` 的所有臂都走 Static 统一管道，`decoupler` 键不会生效 | A2 + A3 + `pipelines_v2.py:1164`（unified → `pipe_type='static'`） | ✅ |
| A5 | `DynamicFactorPipeline` 读取 `module_enabled['decoupler']`（默认 True） | `pipelines_v2.py:792` | ✅ |
| A6 | Dynamic 的 `get_intermediate_data()` 含 `'imputation'` 与 `'decoupling'` 两个键 | `pipelines_v2.py:813`、`pipelines_v2.py:837` | ✅ |
| A7 | `_collect_rho_steps` 只遍历 `L1_MODULES`，且仅实现 5 个步骤分支 | `ablation_runner.py:702-725` | ✅ |
| A8 | B0 的 `rho_step` 同样由 `L1_MODULES` 初始化 | `ablation_runner.py:460` | ✅ |
| A9 | `run_l1` 接受 `market_cap_data` 参数，但调用 `run_single` 时未转发；且 `run_single` 的 B3 分支也未把它传给 `_run_pipeline`（两处断链） | `ablation_runner.py:877`（签名） vs `897/908/919`（调用）; `run_single` B3 分支 v3.4.4 前仅传 `industry_data` | ✅ |
| A10 | `run_l2` 存在同样的 `market_cap_data` 未转发问题（`run_single` 修好后其 B3 分支自动受益，但 `run_l2` 自身仍未转发） | `ablation_runner.py:928` vs `950` | ✅（v3.4.4 登记为观察项；v3.4.5 已修复 `run_l2` 与 `run_baselines`） |
| A11 | 报告 ρ_step 表固定 5 列，未包含 `decoupler` | `ablation_runner.py:1434-1454` | ✅ |
| A12 | `RHO_REF` 常量当前无任何消费者 | 全仓 grep 仅定义处 `ablation_runner.py:411-414` | ✅ |
| A13 | `CompositeDecoupler(enable_ar=False)` 不构建 `ARDecoupler`，中性化保留 | `modules/factor_decoupler/core/dual_neutralizer.py`（v3.4.3 O2 实现） | ✅ |
| A14 | `run_l1`/`run_l2` 的既有测试通过 monkeypatch `run_single` 断言调用次数与臂名 | `tests/test_backtest/test_ablation_runner.py:593-640` | ✅ |

**Q3 结论**: 链路本身完整：`AblationConfig.module_enabled → _run_pipeline → modified_config.module_enabled → DynamicFactorPipeline._decoupler_enabled → CompositeDecoupler(enable_ar=...)`（A3–A5 + A13）。缺的是**入口参数**：没有任何批量方法把 `routing_mode='dynamic'` 与 `{'decoupler': False}` 组合起来。

**Q4 结论**: 可扩展。Dynamic 的中间数据已记录 `'imputation'`（解耦前）与 `'decoupling'`（解耦后），可直接计算 `ρ_step['decoupler'] = Spearman(imputation, decoupling)`；无需改动管线。unified 结果不含 `'decoupling'` 键，应按"不可测"处理（不输出该键），避免伪造 1.0。

**Q5 结论**: 兼容边界：
1. `run_l1` 的返回数量（默认 6）与臂名不得变化；
2. `rho_step` 在 unified/B0 下仍为原 5 键；
3. 报告既有 5 列在无 decoupler 数据时保持原样；
4. 新增能力通过独立方法提供，不改变既有调用方（`scripts/run_ablation*.py`）。

---

## §4 待核实项（⚠️ UNVERIFIABLE）

- CrossRef 未收录 Meyes et al. (2019) 的 arXiv 预印本条目（本次检索返回其 2022 年 Springer 专著章节）；该引用沿用 v3.4.3 已核实的 arXiv abs 页面，不额外推断页码。
- 项目未提供 `decoupler` 的 ρ_step 经验参照值；本次**不新增** `RHO_REF['decoupler']`（A12 表明该常量无消费者，避免引入无依据数字）。
- `run_l2` 的 `market_cap_data` 未转发（A10）真实影响尚未用真实数据量化；v3.4.4 仅登记，v3.4.5 已修复代码（数值影响仍未量化）。

---

## §5 调研结论与设计含义

**可直接引用**:
- 消融必须只改变目标组件，参照与实验臂环境一致（Meyes 2019；Athey & Imbens 2017）。
- `decoupler` 仅在 `dynamic_ab` 生效（A4/A5），因此其消融臂与参照都必须是 `dynamic_ab`。
- 现有 `module_enabled['decoupler']` 链路完整（A5/A13），无需改动管线代码。

**设计含义**:
1. 新增独立批量方法 `run_l1_decoupler()`，返回 2 个结果：`L1_dynamic_ref`（AR 开）与 `L1_decoupler_off`（AR 关），两者 `routing_mode='dynamic'`、`layer='L1'`、`baseline_level='B3'`。
2. 不修改 `run_l1` 的臂集合与返回数量（Q5 兼容边界）；默认 L1 仍为 unified 口径。
3. `_collect_rho_steps` 仅在检测到 `'decoupling'` 中间数据时追加 `decoupler` 步骤，unified/B0 保持 5 键。
4. 报告按需追加 `decoupler` 列（仅当任一结果含该键）。
5. 顺带修复 `run_l1` 的 `market_cap_data` 转发（A9），仅在调用方提供时转发，避免破坏既有 monkeypatch 测试（A14）。
6. `RHO_REF` 不新增键（§4）。

**不可引用**: 无（未采用未核实来源）。

---

## §6 Review 记录（步骤 2）

| 级别 | 检查项 | 结果 | 修正 |
|------|--------|------|------|
| L1 引用 | Athey & Imbens DOI/卷期页码与 Crossref 元数据一致 | ✅ 10.1257/jep.31.2.3, JEP 31(2):3-32 | — |
| L1 引用 | Meyes arXiv 编号与前序调研一致 | ✅ arXiv:1901.08644 | 标注 CrossRef 未收录 |
| L2 行号 | A1–A14 全部与当前源码一致 | ✅ 逐条 grep 复核 | 初稿将 `run_l1` 签名与调用行混写, 已拆为 A9 两处 |
| L3 语义 | "unified 中 decoupler 为 no-op" 的推断 | ✅ 由 A3/A4 与 `pipelines_v2.py:1164` 共同支持 | — |
| L4 数字 | 未给出无依据的 ρ 参照值/性能数字 | ✅ | 明确不新增 `RHO_REF` |
| L5 范围 | 未把 `run_l2` 修复纳入本任务 | ✅ | 登记为观察项 A10，v3.4.5 已补 |
