# 审查验收 Checklist：P-021 tradability 生产启用

---
id: p021-tradability-production-enablement-CHECKLIST
type: design
version: 1.3
status: done
date: 2026-11-23
depends: [p021-tradability-production-enablement-IMPLEMENTATION, p021-tradability-production-enablement-DESIGN]
upstream: null
---

> **Feature**: P-021 tradability 生产启用（C 内部对拍 + A 证据层）
> **创建日期**: 2026-11-23
> **状态**: 待验收（Step 7 产出；§1 于 Step 8 回填，见 §1.6；**§2-§7 / §9 / §10.1 / §12.1 于 Step 9 回填（v1.2）**；§8 / §10.2-§10.3 待 Step 10）
> **Spec 步骤**: Step 7-8, 10
> **档位**: **T1** ｜ **包版本**: 3.9.10 → **3.10.0** ｜ **新依赖**: 无
> **基于实施**: [IMPLEMENTATION.md](./IMPLEMENTATION.md)（v1.5 verified）
> **基于设计**: [DESIGN.md](./DESIGN.md)（v1.4 verified）

---

## 1. 文档一致性验收（Step 8）

> 判据 = 机械可核对；本节在 Step 8 执行并贴读数，Step 7 不预填 ✅。

| # | 检查对 | 判据（DoD） | 机械校验 | 结果 |
|---|---|---|---|---|
| C-1 | RESEARCH → DESIGN | DESIGN §2.1 十条「调研发现 → 决策」逐行引用 `R-/O-/U-` 编号；D1-D6 均可追溯，无悬空发现 | `Grep "R-\|O-\|U-" DESIGN.md` 行行有编号 | ✅ 十条逐行有编号（R-1/R-2/R-5/R-10/O-9/O-8/T-9/O-2/U-2/O-1/T-4/O-7/T-10/D0-D5）；D6 行原为 §5.10 自引用 → 已补「RESEARCH §4.2 D5 收窄注记 + D6 用户确认」（Step 8 P3-①） |
| C-2 | DESIGN → IMPLEMENTATION | D1-D6 全部有实施落点（§3.1-§3.5）；INV-1~15 全部进入本清单 §4 | 逐条对照 DESIGN §5/§8 ↔ IMPL §3/§7 | ✅ D1→§3.1.2/3.1.4、D2→§3.2.4、D3→§3.1.1/3.2.5、D4→§3.2.6、D5→§3.2.6/3.3(5)、D6→§3.3(4)/3.1.4；INV-1~15 §7 全有行；diagnostics 逐键比对发现 `limit_table_duplicate_rows` 未回写 → DESIGN §4.6/§6.1 已补（Step 8 P1-②） |
| C-3 | IMPLEMENTATION → CHECKLIST | IMPL §3.1-§3.6 每个功能点、§8.1 每个测试组、§6 每个错误场景在本清单有对应项 | 反向逐行索引 F/I/N/E | ✅（修复后）§6 错误表 13/13→E-1~E-12+F-17、§7 15/15→N-1~N-15、§8.1 十文件行全覆盖；C 批缺口（规则边界/mock 扰动/脚本）→ F-19/F-20/F-21 已补（Step 8 P1-①） |
| C-4 | 术语一致 | `same_close` / `next_open` / `fallback_raw` / `execution_only_open` / `mode_requested` / `degrade_reason` / `one_word_disabled` / `effective_long_only` 在 RESEARCH/DESIGN/IMPL/本清单用法一致 | `Grep` 八个词，逐处比对语义 | ✅ `same_close` 恒=「库默认+逐位一致+high/low 判定」、`next_open` 恒=「后移 1 日+open 成交」；`limit_table_source` 三值枚举一致（`self_computed` 赋值点已补 §3.2.6，P3-③）；词表补 `same_close`（P3-④） |
| C-5 | 版本一致 | DESIGN §5.9/§10.1、IMPL §2.1/§10、CHANGELOG 均为 **3.10.0**（实施后） | `Grep "3\.9\.10\|3\.10\.0"` 排除 `spec/` 历史 | ✅ 三文档目标 3.10.0 / 基线 3.9.10 一致；`3.9.11/3.11.0/3.9.9/3.10.1` 全仓零命中；CHANGELOG 属 A5 落点（K-7/A-4 追踪），无矛盾；RESEARCH L439 过期「v1.1」引用已勘误（P2-①） |

**附加机械校验（Step 8 执行读数，2026-11-23）**：
- `git status --short`：✅ 仅 `docs/PROGRESS.md`、`docs/PROJECT_STATUS.md` 修改 + `spec/p021-tradability-production-enablement/` 与 5 份研究文档未跟踪；无 `out/` 工件变更。
- 四文档双向引用：✅ 8 处 `./` 相对链全部可达（CHECKLIST→IMPL/DESIGN、IMPL→DESIGN/RESEARCH、DESIGN→RESEARCH、RESEARCH→DESIGN/代码锚点）。
- Python 3.9 语法：✅ 四文档代码块无 `X | None` 运行时注解、无 `match`（IMPL §5.1 表中为文字说明非代码）。

### 1.6 Step 8 复审记录（独立只读子代理，2026-11-23）

- **结论**：PASS_WITH_FIXES（**2×P1 / 2×P2 / 6×P3**），全部处置；主会话机械校验先行（版本 grep / 术语计数 / INV 与用例组 grep / 链接可达 / git status）。

| # | 级别 | 发现 | 处置 |
|---|---|---|---|
| 1 | P1 | C 批验收项在 CHECKLIST 零对应（规则边界 4 项 + mock 扰动 4 类 + 一致性脚本；DESIGN §10.3 两组、IMPL §8.4 C 行） | §2 增 F-19/F-20/F-21；§10.1 功能 18→21、总计 78→81 |
| 2 | P1 | IMPL §3.3(5) `limit_table_duplicate_rows` 未回写 DESIGN §6.1/§4.6 | DESIGN 两处补行；DESIGN 升 **v1.3** |
| 3 | P2 | RESEARCH L439 写「DESIGN v1.1 verified」过期 | 就地勘误为 v1.3（仅前向引用指针，RESEARCH 不改版） |
| 4 | P2 | IMPL §3.6/§8.1 未逐项列 C 批规则边界、缺 `tests/test_tradability_consistency.py` 文件行 | IMPL §3.6 补 gem/ST/低价/half-up 四项；§8.1 补文件行（IMPL 升 **v1.3**，§9.7 记录） |
| 5 | P3 | DESIGN §2.1 D6 行自引用 | 引用列改「RESEARCH §4.2 D5 收窄注记 + D6 用户确认」 |
| 6 | P3 | DESIGN §7「execution_only_open 下 high/low 缺失」IMPL §6 无行 | IMPL §6 补行 → `test_p021_mode_execution_only_open`（Step 9 实测名） |
| 7 | P3 | `self_computed` 无赋值点 | IMPL §3.2.6 补默认赋值；F-12/N-10 补场景 |
| 8 | P3 | CHECKLIST C-4 词表缺 `same_close` | 补齐（与 IMPL §9.6 七词口径一致） |
| 9 | P3 | 4 个测试名 IMPL 未登记（`test_error_table_contracts`/`test_p021_mode_t1_off`/`test_p021_loader_stk_limit_datefmt`/`test_p021_loader_signature`·`test_p021_spec_pickle`） | IMPL §8.1 相应行补名 |
| 10 | P3 | IMPL §3.2.7「写入 §6.1」歧义 | 改「写入 DESIGN §6.1」 |

- 复审确认 PASS：D1-D6 十条逐行可追溯；INV-1~15 双向齐备；术语语义一致；版本无第三种混入；本清单 §10.1 形态/算术合规。

## 2. 功能验收

> DoR = 前置条件；DoD = 可观察通过条件（须给出测试名/读数，禁止未运行 ✅）。

| # | 项（D 编号） | DoR | DoD（可观察） | 证据出口 | 结果 |
|---|---|---|---|---|---|
| F-1 | D1 目标后移 | A2 实施完成 | `target_all[1:]=target_w[:-1]`；首日目标 0；末信号丢弃；`carried` 对后移目标 | `test_p021_d1_signal_shifted` | ✅ 3 例（后移/末信号/谓词）绿 |
| F-2 | D1 执行价谓词 | A2 | `next_open` 用 `open_` 判买/卖；`same_close` 仍用 `high/low`（分模式断言） | `test_p021_d1_open_predicate` | ✅ 绿（open 涨停拦截；仅 high 触及不拦） |
| F-3 | D1 执行价缺失阻塞 | A2 | 仅 `next_open`：`open` 非有限 → 该格不可买卖且 `exec_price_missing_cells` 增 1；`same_close` 下 high/low NaN 仍 `blocked_buy==0`（既有契约不回归） | `test_p021_d1_open_nan_blocks` + `test_error_table_contracts` | ✅ 绿（两路径分别断言） |
| F-4 | D1 turnover 口径 | A2 | 启用态 `turnover` 由有效多头仓位（后移后）计算，`turnover_basis=="effective_long_only"`；空头腿原样透传 | `test_p021_pipeline_passthrough`、`test_tp6_9_engine_calls_tradability` | ✅ 绿（块口径键 + turnover 变化） |
| F-5 | D2 `fallback_raw` 回退 | A3 | `prev` 有限 → `ref` 有限；`ref_fallback_cells/days` 与构造缺口逐格相等；`data_tier=="D1"`、`bias_direction=="optimistic"` | `test_p021_d2_fallback_raw` | ✅ 绿（cells=1/days=1、D1、optimistic） |
| F-6 | D2 `pass` legacy | A3 | `unknown_policy=="pass"` → 不回退，`ref` 保持 NaN、`ref_fallback_cells==0`、`limit_unknown` 计真不可判定格 | `test_p021_d2_pass_legacy` | ✅ 绿 |
| F-7 | D2 loader 缺 `adj` | A3/A4 | 完全缺 `adj` → `ref=prev`、`adj_source=="none"`、`price_basis=="raw_close"`、`adj_missing_days==T`；`full` + `auto_degrade=False` → `ValueError` | `test_p021_d2_loader_no_adj`、`test_p021_mode_full_no_degrade` | ✅ 绿（含 fail-closed 负例） |
| F-8 | D3 BSE 规则前移 | A1 | 2020-07-27 起 `bse` 30% 档生效（`compute_limits(10, 0.30)==(13.00, 7.00)` 同口径）；2020-01-02 不再落 `unknown_board` | `test_p021_d3_bse_effective` | ✅ 绿（2020-07-27=0.30；07-24 仍 ValueError） |
| F-9 | D3 早期 gap 不抛错 | A1 | ① 直调 `_pct_matrix(board=["bse"], dates=2020-01-06/07, return_gaps=True)` → 不抛错且 `gap_mask` 全真；② apply 侧 nonzero `target_w` → `report["limit_unknown"]>=1`（9 键冻结、无 gap 键） | `test_p021_d3_bse_gap`、`test_p021_d3_bse_gap_apply` + 改写 `test_error_table_contracts` | ✅ 绿（双路径） |
| F-10 | D3 未知板块 | A1 | `board="mainx"` → 不抛错；`limit_unknown>0` 且 `meta["unknown_codes"]` 含该代码 | `test_p021_d3_unknown_board`、`test_meta_keys_and_price_basis` | ✅ 绿 |
| F-11 | D4 一字/触板只披露 | A2 | 单事件一字涨停 → `one_word_up==1`、`one_word_down==0`；`exec_up_touch_cells`/`exec_down_touch_cells`/`high_up_touch_cells`/`low_down_touch_cells` 与构造逐格相等；一字不改变成交谓词 | `test_t020_1a_one_word_up_count`、`test_t020_1b_one_word_down_count`、`test_p021_d1_open_predicate` | ✅ 绿（正向计数 + exec/high 触板） |
| F-12 | D5 `stk_limit` 覆盖 | A4 | 提供表 → `limit_table_source=="stk_limit"`、逐格优先；缺格 → `"stk_limit_partial"` + `limit_table_missing_cells>0` + 自算回退；未提供表 → `"self_computed"`（Step 8 P3-③）；CSV `trade_date="20240102"` 归一后仍命中（P1 修复回归） | `test_p021_mock_stk_limit_perturb`、`test_p021_mock_stk_limit_end_to_end` | ✅ 绿（重复/缺格/多代码/错价 + 18/18 逐格采用；日期归一隐式覆盖） |
| F-13 | D5 停牌语义双路径 | A1 | object 面板：`'S'` 停牌，`'R'`/None/NaN 可交易且计 D3；bool 面板：`True` 停牌；**bool 面板经 `reindex` 补列（整帧升型 object）后 `True` 仍停牌**（P2-B2 回归） | `test_p021_d5_suspend_s_only`、`test_p021_d5_suspend_bool_compat`、`test_p021_d5_suspend_reindex_dtype` | ✅ 绿（含 missing_cells==3） |
| F-14 | D6 `auto` → `full` | A3 | 覆盖达标且 `adj` 存在 → `diagnostics.mode=="full"`、`mode_requested=="auto"`、`degrade_reason is None` | `test_p021_mode_auto_full` | ✅ 绿 |
| F-15 | D6 `full` → `execution_only_open` | A3 | `high/low` 不足 + `auto_degrade=True` → `mode=="execution_only_open"`、`mode_requested=="full"`、`degrade_reason=="high_low_or_adj_insufficient"`、`one_word_disabled==True`、`one_word_*==0` | `test_p021_mode_degrade`、`test_p021_mode_auto_degrade` | ✅ 绿 |
| F-16 | D6 覆盖不足 → `off` | A3/A4 | `open/prev` 覆盖 < `min_coverage`（含 T≤1 时 `prev_close_coverage==0.0`）→ 返回 `inputs=None`；`logger.warning` 含 `mode_requested/degrade_reason/coverage`；引擎不挂块 | `test_p021_mode_off_requested`、`test_p021_mode_off_open_missing`、`test_p021_mode_t1_off` | ✅ 绿（三入口 + warning） |
| F-17 | D6 降级成交语义 | A2/A3 | `execution_only_open` 目标后移与 `open` 判定与 `next_open` 同构（逐位）；缺 `high/low` 不阻塞成交；缺 `open` 逐格阻塞 + 计数 | `test_p021_mode_execution_only_open` | ✅ 绿 |
| F-18 | 引擎块 v2 + 管道/并行 | A2/A4 | 启用时 `result["tradability"]` 含 `report/meta/diagnostics` + 4 口径键；`json.dumps` 成功；`close_mismatch_cells` 存在；管道 `tradability_spec` 透传生效；并行 summary **不含**块（契约冻结）；`spec=None` 逐位不变 | `test_p021_pipeline_passthrough`、`test_p021_engine_mode_off_gate`、`test_p021_parallel_summary_contract` | ✅ 绿（含 INV-11 json.dumps） |
| F-19 | C 批一致性脚本（Step 8 P1-①） | C 实施完成 | 脚本以 `--data-root` 运行产出 JSON：逐板块一致率 + mismatch 样例 + BSE 2020-07-27 边界读数；`ref_ret = close/(1+stock_return/100)` vs `ref_adj = _ref_from_adj(prev, adj)` 公式实现与 IMPL §3.6 一致 | `scripts/verify_tradability_consistency.py` 运行读数 | ✅ 实跑 E1：**1394 日 × 5688 只 / 6,784,896 有限格 / 一致率 95.82%**（rtol 1e-3, atol 0.005）；BSE 2020-07-27=0.30、07-24 null；产物 `out/tradability_consistency.json`（公式级内部对拍，非外部准确率） |
| F-20 | C 批规则边界（Step 8 P1-①） | C | gem 2020-08-24 前后 10%→20%、ST 2026-07-06 起 5%→10%、低价 ST（`prev<0.1` → ±0.01 元）、half-up 到分，四项断言绿 | `test_p021_consistency_gem_reform_boundary`、`test_p021_consistency_st_reform_boundary`、`test_p021_consistency_low_price_st`、`test_p021_consistency_half_up_to_cent`、`test_p021_consistency_ref_formula` | ✅ 绿（5 例） |
| F-21 | C 批 mock 限价表扰动（Step 8 P1-①） | C | 18/18 一致；错价/缺行/多代码/重复键各 1/1 检出；`limit_table_duplicate_rows>0`（Step 8 P1-② 键） | `test_p021_mock_stk_limit_perturb` | ✅ 绿（重复键 1、缺格 1、多代码 0 误报、up<down 抛出） |

## 3. 接口验收

| # | 项 | DoD（签名/契约） | 证据出口 | 结果 |
|---|---|---|---|---|
| I-1 | `TradabilityPolicy` 字段与校验 | 新增 `unknown_policy`（`pass/fallback_raw/block`）与 `mode`（`full/execution_only_open/off`）；非法值 `ValueError`；`mode=="execution_only_open"` 且 `execute_at!="next_open"` → `ValueError`；库默认 `same_close/pass/full` | `test_p021_policy_validation` | ✅ 4 种非法组合逐一 ValueError |
| I-2 | `TradabilityInputs` 追加 | 既有 14 字段顺序不变；末尾追加 `ref/limit_up/limit_down/codes/diagnostics` 默认 `None`；`frozen`/`eq=False` 不变 | 读码 + `test_tp6_9`（不传新字段可运行） | ✅ 字段序未动；既有构造零改 |
| I-3 | `apply_tradability` 兼容签名 | 返回 2 元组；`policy` 仍为第 12 位；`adj/is_delisting/no_limit` 位置不变；新增 `ref/limit_up/limit_down` 追加末尾 | `test_p021_wrapper_two_tuple_unchanged` + 既有 19 处调用 | ✅ 既有测试零改值 |
| I-4 | `apply_tradability_with_diagnostics` | 返回 3 元组 `(effective_w, report, diagnostics)`；`report` 九键恒 `int` | `test_p021_apply_three_tuple_contract` | ✅ 9 键全 `int` |
| I-5 | `build_tradability_inputs` 完整签名 | `(close, high, low, open_, volume, suspend, name, adj=None, list_date=None, policy=None, st_overrides=None, limit_up=None, limit_down=None, ref=None)`；返回 `(inputs, meta)`；`adj/ref` 都 None → `ValueError` | `test_adj_required` + 签名逐字核对 | ✅ |
| I-6 | `_pct_matrix` / `rule_pct` 契约 | `return_gaps` 默认 `False`（既有调用不变）；`rule_pct` 直调仍 `ValueError`；`rule_pct_or_nan` 为私有 helper | `test_p021_d3_bse_effective`、`test_p021_d3_bse_gap` | ✅ 默认返回 pct；直调 fail-closed |
| I-7 | `_suspend_mask` 私有且共用 | builder 与 loader 均调用同一实现；bool/object 双路径；不在 `__all__` | `Grep "_suspend_mask"` | ✅ 两处命中（inputs / loader） |
| I-8 | `TradabilitySpec` 契约 | 模块级 `frozen` dataclass；字段 `data_root/panel_dir/policy/mode/auto_degrade/min_coverage/stk_limit_path`；`build(dates, codes) -> (inputs 或 None, meta)`；可 `pickle.dumps`（Windows spawn） | `test_p021_loader_signature`、`test_p021_spec_pickle` | ✅ |
| I-9 | 引擎校验 | `adj is None and ref is None` → `ValueError`；`limit_up/down` 成对；`codes` 长度/唯一（不比列序）；`mode=="off"` 视同 `None` | `test_tp6_9`（形状/adj 负例）、`test_p021_limit_table_pair_required`、`test_p021_engine_mode_off_gate` | ✅ 三入口齐 |
| I-10 | 单进程管道签名 | `PipelineBacktestRunner(config=None, tradability_spec=None)`；`run()` 内 `spec.build(price_data.columns, price_data.index)` | `test_p021_pipeline_passthrough` | ✅ |
| I-11 | 并行签名 | `ParallelFactorRunner(n_workers=None, tradability_spec=None)`、`run_parallel(..., tradability_spec=None)`；spec 进 args tuple；worker 返回契约不变 | `test_p021_parallel_summary_contract`、`test_p021_parallel_signature_passthrough` | ✅ |
| I-12 | 报告键集合冻结 | `report` 9 键、`meta` 13 键集合不变；`diagnostics` 为唯一新增子块；`schema_version==2` | `_META_KEYS` 锁 + `test_p021_apply_three_tuple_contract` | ✅ |

## 4. 不变式验收（INV-1~15）

| # | 不变式 | 核验方式 | 结果 |
|---|---|---|---|
| N-1 | INV-1 默认路径逐位不变 | `tradability_inputs=None` → TP6-11 五指标 + turnover 11 项字面量；默认工件 SHA `82728CE1…` 不变 | ✅ TP6-9/9b/10/11 定向 4 passed；SHA 见 K-5 |
| N-2 | INV-2 IC/收益不变 | 启用态 `rank_icir/pearson_icir/hit_rate/spread/long_short_returns` 与关闭态逐位比较 | ✅ `test_p021_parallel_summary_contract`（summary 标量逐位相等） |
| N-3 | INV-3 `report` 9 键且全 `int` | `set(report)==9 键`；`all(type(v) is int)` | ✅ `test_p021_apply_three_tuple_contract` |
| N-4 | INV-4 `meta` 13 键 | `_META_KEYS` 集合相等；新披露仅见 `diagnostics` | ✅ `test_meta_keys_and_price_basis`、`test_tp6_9` |
| N-5 | INV-5 `same_close` 逐位一致 | 既有 19 处调用零改值；NaN high/low 仍放行（`blocked_buy==0`） | ✅ `test_p021_d1_same_close_nan_not_blocked`、`test_error_table_contracts` |
| N-6 | INV-6 `next_open` 语义 | 目标后移 1 日、首日 0、末信号丢弃、执行价 `open`、`carried` 对后移目标 | ✅ `test_p021_d1_signal_shifted`、`test_p021_d1_last_signal_dropped` |
| N-7 | INV-7 `fallback_raw` 无残留 NaN | `prev` 有限 ⇒ `ref` 有限；`limit_unknown` 不含已回退格 | ✅ `test_p021_d2_fallback_raw`、`test_p021_d2_pass_legacy` |
| N-8 | INV-8 BSE 早期不抛错 | `_pct_matrix` gap 化；gap 计数 ≥ 对应 `limit_unknown` 的必要条件可核 | ✅ `test_p021_d3_bse_gap`、`test_p021_d3_bse_gap_apply` |
| N-9 | INV-9 `'S'` 才停牌 | `'R'`/缺失可交易并计 D3；bool `True` 兼容 | ✅ `test_p021_d5_suspend_s_only`、`test_p021_d5_suspend_bool_compat` |
| N-10 | INV-10 限价表优先 | 逐格优先；`limit_table_source` 与实际来源一致（含 partial 与 `self_computed` 默认——Step 8 P3-③） | ✅ `test_p021_mock_stk_limit_perturb`、`test_p021_mock_stk_limit_end_to_end` |
| N-11 | INV-11 JSON 可序列化 | `json.dumps(result["tradability"])` 成功；无 numpy 标量 | ✅ `test_p021_pipeline_passthrough`（`json.dumps(block)`） |
| N-12 | INV-12 并行切片一致 | 同一 `(dates, codes)` 上切片 build 与全量 build 数组 + `report` 逐位；`meta/diagnostics` 按切片重算 | ✅ `test_p021_parallel_slice_equal` |
| N-13 | INV-13 `off` 旧路径 | 不挂块；`turnover` 与旧路径逐位一致 | ✅ `test_p021_mode_off_noop`、`test_p021_engine_mode_off_gate` |
| N-14 | INV-14 `execution_only_open` 同构 | 后移/`open` 判定与 `next_open` 逐位；`one_word_*==0` 且 `one_word_disabled==True`；缺 `open` 阻塞 + 计数 | ✅ `test_p021_mode_execution_only_open` |
| N-15 | INV-15 降级不静默 | `execution_only_open` → `diagnostics` 含 `mode/mode_requested/degrade_reason`；`off` → loader `logger.warning` 含三字段 + coverage | ✅ `test_p021_mode_degrade`、`test_p021_mode_off_requested`、`test_p021_mode_off_open_missing` |

## 5. 错误处理验收

| # | 场景 | 触发方式 | 预期行为 | 结果 |
|---|---|---|---|---|
| E-1 | 数据根/必需面板缺失 | `TradabilitySpec(data_root=tmp 空目录)` | `ValueError`「缺少面板 <name>」 | ✅ `test_p021_loader_missing_close`（缺 close → ValueError）；空数据根同路径（`tradability_loader.py` L62-64）；E-12 亦以空根触发 |
| E-2 | `adj/ref` 都缺（直接构建器） | `build_tradability_inputs(..., adj=None)` | `ValueError`（既有 `test_adj_required` 保留） | ✅ `tests/test_tradability_inputs.py::test_adj_required` 绿（零改值） |
| E-3 | 完全缺 `adj`（loader） | loader 无 adj 面板 | `ref=prev` + D1 披露；`full`+`auto_degrade=False` → `ValueError` | ✅ `test_p021_d2_loader_no_adj`（`adj_source=="none"`、`data_tier=="D1"`、`price_basis=="raw_close"`）+ `test_p021_mode_full_no_degrade`（fail-closed） |
| E-4 | `open/prev` 覆盖不足 | 构造 open 全 NaN 或 T=1 | 解析 `off` + warning；不挂块 | ✅ `test_p021_mode_off_open_missing`（`degrade_reason=="open_or_prev_unavailable"` + caplog）、`test_p021_mode_t1_off`（`prev_close_coverage==0.0`）、`test_p021_engine_mode_off_gate`（不挂块） |
| E-5 | `full` 条件不足 + `auto_degrade` | high/low 缺格 >1% | 降级 `execution_only_open` + 三字段诊断 | ✅ `test_p021_mode_degrade`（`mode=execution_only_open` / `mode_requested=full` / `degrade_reason=high_low_or_adj_insufficient`、`one_word_*==0`） |
| E-6 | `limit_up`/`limit_down` 不成对 | 只传一侧 | `ValueError`（apply 与 engine 双入口） | ✅ `test_p021_limit_table_pair_required`（构建器 + `apply_tradability` 双入口各抛 1 次；engine 侧同校验读码 `engine.py::_validate_tradability_inputs`） |
| E-7 | 未知板块 | `board="mainx"` | 不抛错；`limit_unknown` + `unknown_codes` | ✅ `test_p021_d3_unknown_board`；实跑复核：`999999.SH` → `meta["unknown_codes"]==['999999.SH']`、`rule_gap_reason=="unknown_board"`、`rule_gap_cells==2` |
| E-8 | BSE 2020-07-27 前 | `dates=2020-01-06/07` | 不抛错；gap + `limit_unknown`；`rule_gap_reason=="neeq_pre_select"` | ✅ `test_p021_d3_bse_gap`、`test_p021_d3_bse_gap_apply`；实跑复核（`430047.BJ`）：`rule_gap_cells=2`、`rule_gap_days=2`、`rule_gap_reason=="neeq_pre_select"`、不抛错 |
| E-9 | 执行价 `open` 非有限 | 单格 open=NaN（next_open） | 该格阻塞 + `exec_price_missing_cells` 增 1（同格不双计） | ✅ `test_p021_d1_open_nan_blocks`（`blocked_buy==1` 且 `exec_price_missing_cells==1`；计数分支 pending/delta 互斥，读码 `tradability.py` L505/L537） |
| E-10 | 停牌面板缺列 | 只给 3 列 | 缺列视为非停牌 + `suspend_missing_cells>0` | ✅ `test_p021_d5_suspend_reindex_dtype`（`suspend_missing_cells==3`，bool 面板 reindex 升型后 `True` 仍停牌） |
| E-11 | 限价表缺格 | mock 表少 1 行（1 格；up/down 同格同缺） | 自算回退 + `limit_table_missing_cells==1`；源标 `stk_limit_partial` | ✅ `test_p021_mock_stk_limit_perturb`（缺行 → 1 格、`limit_table_source=="stk_limit_partial"`） |
| E-12 | 并行 worker 构建失败 | 数据根指向空目录 | 异常上抛（不静默降级、不返回部分结果） | ✅ `test_p021_parallel_worker_error`（`pytest.raises(ValueError)` 于 `_run_worker` 内） |

## 6. 性能验收

| # | 项 | 预算 | 实测 | 结果 |
|---|---|---|---|---|
| P-1 | `spec.build` 全样本 | ≤30 s（V-7） | **15.90 s**（真实数据根 E1，1394×5688，`min_coverage=0` 强制完整构建路径；Step 10 实测） | ✅ |
| P-2 | 并行每 worker 峰值 | ≤1 GB（V-7 / U-2） | **worker RSS 3348 MB / build tracemalloc 1775 MB**（全样本 full 路径，psutil 0.2 s 采样）——**超预算**；缓解：并行 worker 数按内存预算配置；优化方向（面板缓存切片化 / 中间数组 float32 / 分块）登记后续批次 | ☐ 待办（U-2） |
| P-3 | `apply` 全样本 | 与 v3.9.10 同阶（O(T) 日循环） | 结构未变：单层 `for t in range(T)`（`tradability.py` L456），日内全向量化；定向 97 passed / 20 skipped 无超时（1.30 s） | ✅ 结构性通过 |
| P-4 | 新增复杂度 | 无新增 O(T×N) Python 循环（静态读码 + 基准） | 诊断计数全为 `np.count_nonzero` 向量化（L480-537）；`next_open` 后移为 O(T×N) 一次数组赋值；构建器 gap/覆盖率同 | ✅ 结构性通过 |
| P-5 | 面板缓存 | 同进程第二次 `build` 不重复读 pickle（IO 计数/`mtime` 断言） | `test_p021_loader_cache`：monkeypatch `pd.read_pickle` 计数，第二次 `build` 计数不增 | ✅ |

## 7. 兼容性验收

| # | 项 | 判据 | 结果 |
|---|---|---|---|
| K-1 | Python 3.9 | 无 `X \| None` 运行时注解、无 `match`、无 `dict \| dict`；3.9 AST 扫描通过 | ✅ 15 个改动/新增文件 `ast.parse(feature_version=(3,9))` 全通过（Step 10 复跑：files=15 ok=15 bad=0） |
| K-2 | pandas 2.0/2.1 | 只用 `reindex/ffill/eq/pivot/drop_duplicates`；不用 2.2 新增 `limit_area` | ✅ 全仓 `limit_area` 0 命中；`tradability_loader.py` 仅用 `reindex/pivot/drop_duplicates/to_datetime/strftime`（L259-274） |
| K-3 | numpy 1.22 | 只用 `isfinite/count_nonzero/isclose/where`；计数 `int(...)` | ✅ 读码：新增诊断计数均 `int(np.count_nonzero(...))`；`next_open` 只用 `np.zeros_like`/切片赋值 |
| K-4 | pyarrow 缺失 | Parquet 入口 `has_pyarrow()` → `ValueError` 提示 CSV；CSV 路径不受影响 | ✅ `tradability_loader.py` L244-246（`has_pyarrow()` False → `ValueError("... 请改用 CSV")`）；CSV 路径 `test_p021_mock_stk_limit_perturb` 全绿 |
| K-5 | 默认路径 | `tradability_inputs=None` / `tradability_spec=None` 下默认工件 SHA `82728CE1…` 逐位不变 | ✅ 默认工件重跑（`python scripts/verify_capacity_impact.py --json` 至临时路径）SHA256 `82728CE103D4…B2548` 与既有工件逐位一致；`spec=None` 行为面由 TP6-9/9b/10/11 定向 4 passed + `test_p021_pipeline_passthrough` 覆盖 |
| K-6 | 既有测试改写面 | 仅 `test_tradability.py:448-452` 按 §8.3 改写；其余零改值（TP6-9/9b/10/11 断言不动） | ✅ `git diff tests/test_tradability.py` = 新增 `_pct_matrix` 导入 + L448-456 bse 断言块改写，无其他 hunk；`test_backtest/` 仅版本锚点 2 行 |
| K-7 | 版本落点 | 3.10.0 覆盖 `pyproject.toml` / `__init__.py` / `config_v2.py` / `reporting.py` / CHANGELOG / 版本测试断言，共 6 类锚点一致 | ✅ 实读：`pyproject.toml:7`、`__init__.py:58`、`config_v2.py:371`、`reporting.py:40`、`test_fix3_version_unification.py:34`、`tests/test_backtest/verify_fix3_manual.py:21` 全为 3.10.0；CHANGELOG v3.10.0 条目在册 |

## 8. ADD 审计（Step 10）

| # | 项 | DoD | 结果 |
|---|---|---|---|
| A-1 | Iron Law 四类 | 恒真断言 PASS / 生产路径 PASS / 设计独有约束有测试 / 修正阻断性项有测试 | ✅ 审计 §4：①恒真断言 PASS（逐审 51 例无 tautology；1 处弱断言 #7 已加强）；②生产路径 PASS（六条主路径有直接测试；缺口 #1/#9 已补测）；③设计独有约束有测试 PASS；④修正阻断性项有测试 PASS |
| A-2 | 审计独立性 | 独立只读子代理（异构基座）裁决并留 P1/P2/P3 计数；发现项有处置表 | ✅ 独立只读子代理（异构基座，3 组定向重放 57 例全绿 + 2 次 python -c 只读验证 + 静态读码；审计不写码）→ **PASS_WITH_FIXES，4.3/5 档位 A，1×P1 / 2×P2 / 5×P3 + 1 观察项**；处置表见 §12.2 |
| A-3 | 取证矩阵 | 每条 ✅ 绑测试名/命令/读数；无证据不标 ✅（RULE-2） | ✅ 审计取证抽查 8 组重放全部与声明一致（57 例绿；K-6 行号、K-7 六锚点逐字命中）；§2-§8 每项绑测试名/读数；Step 10 修复项全部红→绿留痕 |
| A-4 | 台账闭环 | PROGRESS P-021 状态更新 + CHANGELOG v3.10.0 三要点 + PROJECT_STATUS 优先级视图同步 | ✅ PROGRESS P-021 → done；CHANGELOG v3.10.0 验证节含全量读数（2201 基线 + 2204 复跑）；PROJECT_STATUS §1 当前版本 v3.10.0 + §2 优先级视图同步 |

## 9. 文档完整性

| 文档 | 存在 | 与实现一致 |
|---|---|---|
| [RESEARCH.md](./RESEARCH.md)（v1.1 verified） | ☑ | ☑ 结论/决策输入未变；D1-D6 均按 RESEARCH 结论落地（追溯见 C-1/C-2） |
| [DESIGN.md](./DESIGN.md)（v1.4 verified） | ☑ | ☑ 契约实读一致：`apply_tradability_with_diagnostics` 3 元组（tradability.py L329）、diagnostics 键表与 §6.1 对齐（含 Step 10 补登记 `coverage`） |
| [IMPLEMENTATION.md](./IMPLEMENTATION.md)（v1.5 verified） | ☑ | ☑ 签名/字段/模式解析一致；§8.1 已同步 Step 9+10 实测数（53 例，IMPL §9.8/§9.9） |
| CHECKLIST.md（本文件，v1.3） | ☑ | ☑ §2-§9/§10.1/§12 按实测回填，无未证 ✅ |
| 相关 ADR（ADR-0002 / 0004 / 0010，无需新增） | ☑ | ☑ D1-D6 未触发新 ADR（T+1 语义在 ADR-0002、键集合冻结在 ADR-0004、Layer 判定在 ADR-0010 既有语义内） |
| 开发日志（Step 9 红→绿记录，§12 回填） | ☑ | ☑ CHANGELOG v3.10.0 已记录变更/行为影响/版本/验证；红→绿读数见 §12.1 |

## 10. 验收结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|---|---|---|---|---|
| 文档一致性 | 5 | 5 | 0 | 0 |
| 功能 | 21 | 21 | 0 | 0 |
| 接口 | 12 | 12 | 0 | 0 |
| 不变式 | 15 | 15 | 0 | 0 |
| 错误处理 | 12 | 12 | 0 | 0 |
| 性能 | 5 | 4 | 0 | 1 |
| 兼容性 | 7 | 7 | 0 | 0 |
| ADD 审计 | 4 | 4 | 0 | 0 |
| **总计** | 81 | 80 | 0 | 1 |

> **统计口径（RULE-2）**：上表来自本文件逐项核对（每项独立复选框），非事后汇总推算；`总数 = 通过 + 失败 + 待办` = 80 + 0 + 1 = 81。
> **1 项待办**：P-2（并行 worker 内存超预算 3348 MB > 1 GB；优化登记后续批次，见 §6）。

### 10.2 验收决定

- ☐ **验收通过**：所有 P1 项通过，无阻塞性问题
- ☑ **有条件通过**：条件 = ① P-2（并行 worker 内存 3348 MB > 1 GB 预算）登记后续性能优化批次（面板缓存切片化 / float32 / 分块），并在并行生产使用时按内存预算配置 worker 数；② U-1（`stk_limit` 外部一致率）待 token 到位后补 V-8。其余 80/81 全过、0 失败；Step 10 独立审计 PASS_WITH_FIXES（1×P1/2×P2/5×P3）全部处置。
- ☐ **验收失败**：<原因>

### 10.3 签字

| 角色 | 签字 | 日期 |
|------|------|------|
| 实施者 | | |
| 审查者 | | |

## 11. 后续行动

| 行动 | 责任人 | 期限 | 状态 |
|---|---|---|---|
| Step 8 三对文档一致性复审（回填 §1） | — | — | ✅ 已回填（PASS_WITH_FIXES，见 §1.6） |
| Step 9 TDD C→A1~A5（回填 §2-§7 + §12 红→绿） | — | — | ✅ 已回填（§2-§7/§9/§10.1/§12.1） |
| Step 10 ADD 审计（回填 §8） | — | — | ✅ 已回填（PASS_WITH_FIXES 全处置，见 §12.2） |
| 更新 PROGRESS.md / PROJECT_STATUS.md（P-021 → done） | — | — | ✅ 已同步 |
| 记录开发日志（CHANGELOG v3.10.0） | — | — | ✅ v3.10.0 条目已落 |
| P-2 并行 worker 内存优化（3348 MB → ≤1 GB） | — | 后续批次 | ☐ 登记（§6；缓存切片化 / float32 / 分块） |
| U-1 `stk_limit` 外部一致率（V-8） | — | token 到位后 | ☐ 登记 |

## 12. 执行记录（Step 9 / Step 10 回填）

### 12.1 Step 9 红→绿读数（F5）

| 批次 | 红（改代码前） | 绿（改代码后） |
|---|---|---|
| C / A1 | `python -m pytest -q` 首跑 **exit 1：6 failed / 8 passed**；关键失败行：`TypeError: _pct_matrix() got an unexpected keyword argument 'return_gaps'`；BSE `ValueError`（2020-01-06/07）；`test_p021_d5_suspend_s_only` 失败（`'S'` 未识别）；`test_error_table_contracts` 旧 bse 断言失败；`ModuleNotFoundError: No module named 'backtest.tradability_loader'`（mock 限价表用例） | `python -m pytest -q tests/test_tradability_consistency.py tests/test_tradability_bse.py` **exit 0：15 passed**（consistency 8 + bse 7） |
| A2 | 测试先行：`ImportError: cannot import name 'apply_tradability_with_diagnostics'` | `test_tradability_next_open.py` **11 passed** |
| A3 | 测试先行：`ref` 未回退 / `diagnostics` 未产出 → `AttributeError`/`KeyError` | fallback **5 passed** + mode **10 passed** |
| A4 | 测试先行：`ModuleNotFoundError: No module named 'backtest.tradability_loader'` | loader **4 passed** + pipeline **5 passed** |
| A5（全量） | —（版本/文档批：不新增测试；版本锚点一致性由 K-7 承接） | 定向 TP6 基线（`-k "tp6_11 or tp6_9 or tp6_10"`）**4 passed**；P-021 新增文件 `-k "p021"` **50 passed / 6 skipped**（2179 deselected）；tradability 相关 9 文件 **89 passed**；全量回归 `python -m pytest -q --no-header` → **2201 passed / 34 skipped / 0 failed**（1581.31 s，exit 0） |

> **红→绿口径（F5）**：红 = pytest 非零退出 + 关键失败行；绿 = 退出 0 + 用例计数。
> **Step 10 修复后复跑**：定向 tradability 10 文件 **97 passed / 20 skipped**；`-k "p021"` → **53 passed / 6 skipped**；全量回归（生产代码修复后重跑）`python -m pytest -q --no-header` → **2204 passed / 34 skipped / 0 failed**（1274.65 s，exit 0；+3 = Step 10 新增测试）；K-5 SHA 复现 ✅、P-1 15.90 s ✅（见 §6/§7）。
> **绿阶段修正记录（测试期望或实现）**：① `data_tier` 由 `max` 改 `min`（D1 最差，DESIGN §6.2）；② `test_p021_d1_signal_shifted` 末目标期望由 0.5 改 0.0（后移语义）；③ `test_p021_d1_last_signal_dropped` 的 `carried` 期望由 1 改 0（对后移目标计数）；④ `unknown_policy="pass"` 下未知限价放行，断言改为 `limit_unknown>=1` + `eff==0.5`。

### 12.2 Step 10 审计处置表

> 审计：独立只读子代理（异构基座），裁决 **PASS_WITH_FIXES**（质量门 **4.3/5 档位 A**；**1×P1 / 2×P2 / 5×P3** + 1 观察项）。全部处置如下；修复均红→绿留痕，定向回归 97 passed / 20 skipped。

| # | 级别 | 审计发现 | 处置 |
|---|---|---|---|
| 1 | P1 | 引擎 `diag.update(apply_diag)` 使 apply 无条件写的 `"stk_limit"` 覆盖 builder 的 `"stk_limit_partial"` → INV-10 块级失真且无测试（engine.py L332-333 / tradability.py L415-416） | 修复：`engine.py` 合并后 `limit_table_missing_cells>0` → 强制恢复 `stk_limit_partial`（DR-15）；新增 `test_p021_partial_limit_source_block` 红（`'stk_limit' != 'stk_limit_partial'`）→ 绿；DESIGN §6.1 `limit_table_source` 行补恢复规则 |
| 2 | P2 | off no-op diagnostics 实现 10 键，偏离 DESIGN §4.2 锁定的 2 键契约 | 实现收窄：`tradability.py` off 分支返回 `{"mode","schema_version"}`（DR-14）；`test_p021_mode_off_noop` 补强键集合断言（DESIGN 文本不变） |
| 3 | P2 | Step 9 后审计修复（loader index 归一化）未登记、IMPL §8.1 计数 4≠5、§9.8 50 例过期、CHECKLIST §12.2 空（A-3/RULE-2 缺口） | 登记：IMPL §11.1 DR-13 + §8.1（loader 6 / pipeline 6 / 合计 53）+ §9.9；CHECKLIST §12.2 本表；IMPL 升 v1.5、DESIGN 升 v1.4、CHECKLIST 升 v1.3 |
| 4 | P3 | 块 diagnostics 含未登记嵌套键 `coverage`（loader 注入，DESIGN §6.1 无此项） | DESIGN §6.1 补键行（类型/来源/说明）；行为保留（json 可序列化已核） |
| 5 | P3 | `meta_off` 实际 4 键（含 `coverage`），IMPL DR-4 只登记 3 键 | DR-4 补第 4 键（INV-15 warning 含 coverage 语义不变） |
| 6 | P3 | `limit_table_duplicate_rows` 来源列写「构建器」，实际仅 loader 写入 | DESIGN §6.1 来源列勘正为「loader」（含勘正理由） |
| 7 | P3 | INV-12 report 断言弱（同参确定性检查，非全量↔切片对比） | `test_p021_parallel_slice_equal` 加强：r2 改用全量 build 的子块数组直接调用 apply，断言 `r1 == r2`（真实对比） |
| 8 | P3 | `_run_worker` docstring 仍写 5 元组（实参 6 元） | docstring 同步 6 元组 |
| 9 | 观察（未定级） | loader `_list_date` 多行分支与 list_date 面板形态无测试；真实数据根无 `stock_list_date.pkl` | 补 `test_p021_loader_list_date_panel`（单行 DataFrame 形态 → IPO 前 5 日 `no_limit` 接线 + 老股既有 `pos[:5]` 语义）；生产缺面板走 D4 披露不变 |
| 10 | 主会话先行（与 #3 互证） | **真实数据根全部面板 index 为字符串日期**（object）→ loader `DatetimeIndex` reindex 全 miss → `eligible_cells=0` → 默认 spec 恒 `off`（生产数据根上静默失效，P1 级功能阻断） | 修复：`_read_panel` 归一化 `pd.to_datetime(frame.index)`（非日期索引面板容错跳过，保 list_date 元数据表）；红→绿 `test_p021_loader_str_index_panels`；修复后真实数据根 `mode=full`、eligible 7,203,655 格、tier=D1（缺 name/suspend/list_date → §6.2 组合取最差） |
| 11 | Step 10 补证 | P-2 并行 worker 内存实测 3348 MB > 1 GB 预算 | §6 P-2 登记待办（U-2）；缓解措施与优化方向留痕；不影响功能/正确性验收 |
