# 2026-11-10 代码质量审计 — v3.4.0 因子路由统一化治理

**审计版本**: v1.0
**日期**: 2026-11-10
**审计对象**: v3.4.0 `E1–E7` 实施 (ADR-042 统一横截面秩管道)
**审计基准**: [CHECKLIST_V3.4.0_UNIFIED_ROUTING.md](CHECKLIST_V3.4.0_UNIFIED_ROUTING.md) v1.3 (Gate 0–7 已回填)
**对齐文档**: [EXECUTION_V3.4.0_UNIFIED_ROUTING.md](../EXECUTION_V3.4.0_UNIFIED_ROUTING.md) v1.3 / [DESIGN](../analysis/FACTOR_ROUTING_OVERENGINEERING_DESIGN.md) v1.2 / [RESEARCH](../analysis/FACTOR_ROUTING_OVERENGINEERING_RESEARCH.md) v1.1 / [ADR-042](../../DECISIONS.md) / [CONSISTENCY_REVIEW_V3.4.0.md](CONSISTENCY_REVIEW_V3.4.0.md) v1.0
**审计方式**: audit-driven-development Phase 0–4; Phase 0 判定 **Tier A → Full Audit**; Phase 2 派发 5 个并行 subagent (维度 A–E) + 主会话 Phase 3.5 源码逐条核实
**代码基线**: HEAD `0ff2420` + v3.4.0 未提交工作区
**总评**: **PASS** (0 P0 / 0 P1; 3 P2 + 24 P3 全部处置或记录)

---

## Phase 0: Spec Quality Gate

| # | 维度 | 判定 | 证据 |
|---|------|------|------|
| 1 | 可测试约束 | ✅ 1 | A1–A17 验收 + Gate 0–7 共 100+ 条"必须"项与数值阈值 |
| 2 | 模块映射 | ✅ 1 | E1–E7 与 EXECUTION §3–§9 一一对应 |
| 3 | 接口契约 | ✅ 1 | `Config` 8 字段、`FingerprintMeta`/`FactorRoutingRecord`、`infer_sampling_frequency`、`compute_ar1_path`、`BreakMonitorConfig`/`detect`、`_log_spec` 均有签名 |
| 4 | 修正项 | ✅ 1 | §4.6 两新列、§5.3 `m3`/`M3`/`M5`、§8.2 删除/改写账目 |
| 5 | 跨模块契约 | ✅ 1 | ADR-042 决策 1–6 + "不改"清单 |

**结论**: 5/5 → **Tier A (Full Audit)**。

---

## Phase 1: Spec Inventory

| 工件 | 内容 | 审查维度 |
|------|------|---------|
| EXECUTION v1.3 §3 | E1 配置面 (加 8 删 5 / 桥接 / 优化器收缩) | 每字段 vs 代码落地 |
| EXECUTION v1.3 §4–§5 | E2 统一执行 / E3 诊断层 | `fit`/`transform` 行为、记录结构、频率推断 |
| EXECUTION v1.3 §6–§7 | E4 规格日志 / E5 断点监控 | 按臂派生、开关边界、统计量与自助 |
| EXECUTION v1.3 §8–§9 | E6 清理 / E7 消融适配 | 3 函数 5 字段消失、2 臂口径 |
| EXECUTION v1.3 §10–§11 | 测试计划 / A1–A17 | 测试契约 |
| ADR-042 | 决策 1–6 + 后果 + 替代 + 回滚 | 决策与代码一致性 |
| CHECKLIST v1.3 | Gate 0–7 + C1–C15 修正项 | 逐项确认 |
| DESIGN v1.2 / RESEARCH v1.1 | D1–D12 / 学术锚点 | 设计-调研-实施三方一致 |
| CHANGELOG / README / PROJECT_STATUS / DEV_PROGRESS / ARCHITECTURE | v3.4.0 同步 | 版本与登记一致性 |

---

## Phase 2: Multi-Dimensional Audit

### 2.1 E 任务 vs 代码对齐

| E 任务 | 实施文档声明 | 代码实测 | 结论 |
|--------|-------------|---------|------|
| E1 配置面 | dataclass 加 8 删 5; Pydantic 加 8 删 5 (4 共享 + `transform_aggressiveness`); 桥接 8 字段; 优化器空空间 | [pipelines_v2.py](../../pipelines_v2.py) L492-504 8 字段/默认值逐项一致; `pipeline_mode` 非法值 `__post_init__` ValueError; [config_v2.py](../../config_v2.py) `Literal['unified','dynamic_ab']` + `ge/gt/lt` 边界一致; 桥接 8 字段齐全; [optimizer.py](../../optimizer.py) `DEFAULT_SEARCH_SPACE = {}` + 弃用警告 + 空空间 `optimize` ValueError | ✅ |
| E2 统一执行 | `fit` 单次 `batch_extract` → 诊断 → 单管道; `transform` 优先 `factor_pipelines` | [pipelines_v2.py](../../pipelines_v2.py) 诊断仅 1 次提取; `pipe_type = 'static' if pipeline_mode=='unified' else 'dynamic'`; 每因子 1 条 `FactorRoutingRecord`; `transform` 走 `factor_pipelines` 实例 (身份已断言) | ✅ |
| E3 诊断层 | `infer_sampling_frequency` 9 档; `compute_ar1_path` `⌊(T−w)/s⌋+1` | [fingerprint.py](../../modules/factor_fingerprint/core/fingerprint.py) L117-155 阈值链 <1/≤2/≤8/≤20/≤45/≤135/≤400; L320-344 长度与 `window/stride≤0` 校验一致; `__init__.py` 导出 | ✅ |
| E4 规格日志 | 按臂派生 + 关闭零目录 | [pipelines_v2.py](../../pipelines_v2.py) `_log_spec` 开关检查在 `try`/构造之前; winsor/transformation 按 `is_static` 派生; `cache_version` 写入 | ✅ |
| E5 断点监控 | sup-F (trim=0.15/1e-12) + CUSUM ICSS + AR(1) 代理自助 (B=400, burn-in 50) | [structural_break_monitor.py](../../backtest/structural_break_monitor.py) 公式逐项符合; `detect` 只读; 候选区间闭区间 (审计 F-D-01 修复后) | ✅ |
| E6 清理/版本 | 3 函数 + 5 字段消失; 6 处版本 + `CODE_VERSION` | 3 函数生产代码 0 命中; pytest 收集文件 5 字段 0 命中; 版本 6 处 3.4.0; `v2.3.0-cache` | ✅ |
| E7 消融适配 | `routing_mode` 3 值; 注入在 L3/L4 之后; 2 臂 | [ablation_runner.py](../../backtest/ablation_runner.py) L326/L551-560 一致; `_override_routing` 已删; `run_l2` 2 臂 + 可选参照 | ✅ |

### 2.2 跨模块契约 / ADR-042 不变式

| 契约 | 验证 | 结论 |
|------|------|------|
| 生产路径无 `StatisticalClassifier` 调用 | 全文件仅 1 处说明性注释; 调用 0 | ✅ |
| 指纹只提取一次 | `batch_extract` 全模块 1 处调用 | ✅ |
| Dynamic 仅 A/B 可达 | `pipeline_mode='dynamic_ab'` 才建 Dynamic 管道 | ✅ |
| 三条底层管道类内部不改 | `MixedFactorPipeline.__init__` 签名保留 (§8.2 明示豁免) | ✅ |
| 指纹 21 维契约不改 | 新元数据独立于数值指纹 (`FingerprintMeta`) | ✅ |
| `monitor_structural_breaks` 只读 | `detect` 不修改输入; 前后 `transform` 逐位一致 | ✅ |
| 消融消费结构兼容 | `ablation_runner` 仍消费 dict-of-dicts | ✅ |
| 新模块依赖 | 仅 numpy/pandas (无 scipy/statsmodels) | ✅ |
| 删除符号无残留 | 3 函数 0 命中; `_override_routing` 0 命中 | ✅ |

### 2.3 接口签名核对 (代码 vs 文档)

- `PipelineV2Config.pipeline_mode / enable_fingerprint_diagnostics / ab_experiment_id / enable_break_monitor / break_monitor_{window,stride,alpha,n_bootstrap}` — 与 EXEC §3.1 一致 ✅
- `PipelineV2ConfigUnified.pipeline_mode: Literal['unified','dynamic_ab']` — 一致 ✅
- `FingerprintMeta(sampling_frequency, n_obs, n_columns, start, end)` / `FactorRoutingRecord` 8 字段 `frozen=True` — 与 §4.1 一致 ✅
- `infer_sampling_frequency(index) -> str` / `compute_ar1_path(self, factor_data, window=250, stride=20)` — 一致 ✅
- `get_routing_summary()` 12 列 / `get_classification_summary()` +2 列 — 与 §4.6 一致 ✅
- `BreakMonitorConfig` 8 字段 / `detect(path) -> Dict` 9 键 — 与 §7.1 一致 ✅
- `_log_spec(record) -> Optional[str]` — 一致 ✅
- 公共 `fit` / `transform` 签名未变 ✅

### 2.4 测试盲区识别 (4 类)

| 盲区类型 | 检查结果 | 处置 |
|---------|---------|------|
| 1 断言恒真式 | `test_fix2_config_unification.py` `test_10` 以 `from_unified` 自比 (`from_unified` 即 `to_pipeline_v2_config` 转发), 8 项断言恒真 | ✅ 改为逐字段显式默认值 (F-A-01) |
| 2 单文件检查盲区 | T2/T3 只比对数值; Static 各步近似无状态, 即使 `transform` 误走兜底也可能通过; `_direct_static` 恒传 `garch_params=None` 而注释称"参数一致" | ✅ 增实例身份断言 (`_RecordingPipe`) + 补齐 garch_params (F-B-03/F-B-06) |
| 3 设计约束无测试 | 频率 9 档仅测 5 档; `BreakMonitorConfig` 4 条 + `compute_ar1_path` 2 条 ValueError 分支无单测; T4 未断言 `mixed_pipeline is None`; T14 未断言 5 个 Pydantic 字段消失; T9 未断言 `cache_version` | ✅ 全部补齐 (F-C-01/C-02/C-04, F-D-03, F-B-04, F-A-04) |
| 4 修正项无测试 | §5.3 `m3` 守卫 (显式 0 透传) 已由源码核对 + 参数校验单测覆盖; §8.2 豁免项由 grep 零残留覆盖 | ✅ |

### 2.5 数值与登记一致性

| 数值/登记 | 代码/测试 | 文档 | 结论 |
|-----------|----------|------|------|
| 版本 6 处 | 全部 3.4.0 | EXEC/CHECKLIST/CHANGELOG/README | ✅ |
| 缓存代际 | `v2.3.0-cache` (5 消费类引用常量) | 同上 | ✅ |
| `compute_ar1_path` 点数 | T=1472/w=250/s=20 → 62 | G2-22 = 62 | ✅ |
| B1 断点位置 | 27 (容差 17–27) | G2-29 = 22±5 | ✅ |
| 消融 2 臂 | `run_l2` 2 结果 + 可选参照 | §9.2/§9.5 | ✅ |
| 删除用例账目 | 实测收集与 §0.2 一致 (本轮全量重跑为准) | §0.2 / §8.2 | ✅ |
| EXECUTION 版本头 | 文件头 v1.3 | §14 已有 v1.3 行 | ✅ (F-E-03 修复) |
| CHANGELOG 实测矩阵 | 8 行 | G4-6/G6-1 | ✅ (F-E-06 修复) |

### 2.6 审计覆盖与校准

- 5 个 subagent 均按"无 evidence / 无 spec_ref 不报"输出, 维度 A–E 全部给出 pass/fail 判定。
- 校准抽检: 主会话对 **全部 P2** 与 **高风险 P3** 逐条回读源码 (≥10% 要求)。
- **误报 1 条**: A-03 声称 `test_v340_02` "从未断言 `trial.value == -1.0`" — 实测 [test_p3_phase3_optimizer.py](../../tests/test_p3_phase3_optimizer.py) L936-939 存在该断言, 否决。
- **降级 2 条**: C-05 (`_fmt_ts` NaT) 与 D-02 (`break_index` 语义) 由 P2 降 P3 — 前者仅影响异常索引元数据, 后者文档已注明 `y.index[k]` 对应关系, 仅措辞歧义。

---

## Phase 3: Fix Priority Matrix

| 级别 | 数量 | 含义 |
|------|------|------|
| P0 Blocker | 0 | — |
| P1 Critical | 1 | **R-01 既有套件回归**: 3 个既有用例 (`test_p3_phase3_threshold_drift_monitor` 1 + `test_p2_2_optimizer_cv` 2) 仍以空搜索空间调用 `optimize()`, v3.4.0 后必失败 — Phase 4 全量复跑发现, 已修复 |
| P2 Major | 3 | 断言恒真式 / 实例身份缺失 / 文档版本头不一致 |
| P3 Minor | 24 | 文档措辞、登记过期、覆盖率与注释 |

**Tier 1**: R-01 (阻断零回归交付)。
**Tier 2**: 3 项 P2 + 1 行类 P3 (文档/注释/单行守卫)。
**Tier 3**: 剩余 P3 (测试覆盖补强), 本轮全部处理, 仅 2 项记录性接受。

**排序说明**: R-01 为"修正项未落实"类 (步骤 9 迁移遗漏), 优先于所有新增项; 3 项 P2 均为 1–10 行修复。

---

## Phase 3.5: P0 幻觉防护 (4 级源码验证)

本轮 **无 P0**, 硬门按规则记为 N/A; 主会话自愿对所有 P2 执行同等核实:

| Finding | L1 文件 | L2 行号 | L3 关键词 | L4 结构 | 结论 |
|---------|--------|--------|----------|--------|------|
| A-01 | ✅ | ✅ | ✅ `from_unified` 转发 | ✅ 恒真式成立 | verified |
| B-03 | ✅ | ✅ | ✅ T2/T3 无数值外断言 | ✅ 盲区成立 | verified |
| E-03 | ✅ | ✅ | ✅ 头 v1.2 / §14 v1.3 | ✅ 不一致成立 | verified |
| A-03 | ✅ | ✅ | ❌ 声称"无断言"但 L936-939 有 | ❌ | **unverified → 移出基线 (幻觉)** |

**Hallucination log**: 1 条 (A-03)。FP 率 = 1/28 ≈ 3.6%; 该 subagent 其余 4 条发现经核实均成立, 输出整体保持 high confidence。

---

## Phase 4: Fix Baseline + Tracking

| 编号 | 严重度 | 类别 | 描述 | 证据 | 状态 |
|------|--------|------|------|------|------|
| R-01 | P1 | corrective | 3 个既有用例未迁移 `search_orth=True`, v3.4.0 后 `optimize()` 抛"No parameter to search" | [threshold_drift_monitor L262](../../tests/test_p3_phase3_threshold_drift_monitor.py#L262) / [optimizer_cv L341,L367](../../tests/test_backtest/test_p2_2_optimizer_cv.py#L341-L370) | ✅ 已修复 |
| A-01 | P2 | blind_spot | `test_10` 用 `from_unified` 自比 → 8 项恒真断言 | [test_fix2 L234-250](../../tests/test_fix2_config_unification.py#L234-L250) | ✅ 已修复 (逐字段默认值) |
| B-03 | P2 | blind_spot | T2/T3 无实例身份断言, 兜底路径误用不会被发现 | [test_unified_routing L125-178](../../tests/test_unified_routing.py#L125-L178) | ✅ 已修复 (`_RecordingPipe`) |
| E-03 | P2 | contract | EXECUTION 文件头/README 标 v1.2, §14 已有 v1.3 | [EXECUTION L3](../EXECUTION_V3.4.0_UNIFIED_ROUTING.md#L3) / [README L51](../../README.md#L51) | ✅ 已修复 |
| A-02 | P3 | blind_spot | T1 仅断言 `ValueError`, 未校验消息含两合法值 (G2-2 证据不足) | [test_unified_routing L109-119](../../tests/test_unified_routing.py#L109-L119) | ✅ 已修复 |
| A-04 | P3 | blind_spot | T14 未断言 5 个 Pydantic 字段已删除 | [test_unified_routing L454-458](../../tests/test_unified_routing.py#L454-L458) | ✅ 已修复 |
| A-05 | P3 | blind_spot | `test_08` docstring 称"其他键被忽略"但未传入其他键 | [test_p3_phase3_optimizer L474-480](../../tests/test_p3_phase3_optimizer.py#L474-L480) | ✅ 已修复 (docstring) |
| B-01 | P3 | behavior | `transform` docstring 仍描述"概率加权软路由" | [pipelines_v2 L1209-1216](../../pipelines_v2.py#L1209-L1216) | ✅ 已修复 |
| B-02 | P3 | behavior | strict 分支先 `logger.warning` 再抛错, 与规格"先抛错"相反 | [pipelines_v2 L1248-1252](../../pipelines_v2.py#L1248-L1252) | ✅ 已修复 |
| B-04 | P3 | blind_spot | T4 未断言 `mixed_pipeline is None` 兼容回填 | [test_unified_routing L189-191](../../tests/test_unified_routing.py#L189-L191) | ✅ 已修复 |
| B-05 | P3 | blind_spot | T8 只断言两新列存在, 未校验取值; 未覆盖 dynamic 键 | [test_unified_routing L295-316](../../tests/test_unified_routing.py#L295-L316) | ✅ 已修复 |
| B-06 | P3 | blind_spot | `_direct_static` 恒传 `garch_params=None`, 注释称"参数一致" | [test_unified_routing L63-80](../../tests/test_unified_routing.py#L63-L80) | ✅ 已修复 |
| C-01 | P3 | blind_spot | T7 仅覆盖 5/9 频率档 | [test_unified_routing L262-281](../../tests/test_unified_routing.py#L262-L281) | ✅ 已修复 (9 档) |
| C-02 | P3 | blind_spot | T9 未断言 `cache_version` (G2-23 证据不足) | [test_unified_routing L339-347](../../tests/test_unified_routing.py#L339-L347) | ✅ 已修复 |
| C-03 | P3 | blind_spot | `_log_spec` 写盘失败无注入测试 | [pipelines_v2 L1431-1472](../../pipelines_v2.py#L1431-L1472) | ⏸ 记录 (全函数 try/except + warning; 源码核对足够) |
| C-04 | P3 | blind_spot | `compute_ar1_path` window/stride≤0 无单测 (G2-32 证据列"单测"名不副实) | [test_structural_break_monitor L178-195](../../tests/test_structural_break_monitor.py#L178-L195) | ✅ 已修复 |
| C-05 | P3 | behavior | `pd.Timestamp(NaT).isoformat()` 返回 `'NaT'`, 兜底不生效 | [pipelines_v2 L1422-1429](../../pipelines_v2.py#L1422-L1429) | ✅ 已修复 (`pd.isna` 守卫) |
| D-01 | P3 | behavior | sup-F 候选区间闭区间, 代码漏掉上端点 | [structural_break_monitor L84-85](../../backtest/structural_break_monitor.py#L84-L85) | ✅ 已修复 (`k_hi + 1`) |
| D-02 | P3 | behavior | `break_index` 为清洗后位置, 文档"原始路径位置"歧义 | [EXECUTION L846](../EXECUTION_V3.4.0_UNIFIED_ROUTING.md#L846) | ✅ 已修复 (文档) |
| D-03 | P3 | blind_spot | `BreakMonitorConfig` 4 条 ValueError 无单测 | [test_structural_break_monitor L155-175](../../tests/test_structural_break_monitor.py#L155-L175) | ✅ 已修复 |
| D-04 | P3 | contract | 文档称逐因子无条件 `detect`, 代码对空因子 `continue` | [EXECUTION L883-885](../EXECUTION_V3.4.0_UNIFIED_ROUTING.md#L883-L885) | ✅ 已修复 (文档) |
| D-05 | P3 | behavior | 代理自助未截断 φ, φ≥1 时递归发散、漏报 (low confidence) | [structural_break_monitor L128-131](../../backtest/structural_break_monitor.py#L128-L131) | ✅ 已修复 (`clip(-0.99, 0.99)`) |
| E-01 | P3 | blind_spot | 注入映射仅覆盖 unified/dynamic, `full→unified` 与非法值无测试 | [test_ablation_runner L1146-1156](../../tests/test_backtest/test_ablation_runner.py#L1146-L1156) | ✅ 已修复 |
| E-02 | P3 | blind_spot | 报告测试仅断言两臂名存在, 未断言行数=2 | [test_ablation_runner L1191-1194](../../tests/test_backtest/test_ablation_runner.py#L1191-L1194) | ⏸ 记录 (2 臂口径已由 `test_run_l2_returns_2_results` 覆盖) |
| E-04 | P3 | contract | DEV_PROGRESS §2.4 列头仍"v3.4.0 (计划)" | [DEV_PROGRESS L77](../DEV_PROGRESS.md#L77) | ✅ 已修复 |
| E-05 | P3 | contract | `verify_fix3_manual` 分母硬编码 5 (实际 6 处) | [verify_fix3_manual L153](../../tests/test_backtest/verify_fix3_manual.py#L153) | ✅ 已修复 |
| E-06 | P3 | contract | checklist G4-6 实际列称"实测矩阵待回归", 但 CHANGELOG 已回填 | [CHECKLIST L190](CHECKLIST_V3.4.0_UNIFIED_ROUTING.md#L190) | ✅ 已修复 |
| E-07 | P3 | contract | §10 patch 目标写 `ablation_runner.FactorProcessingPipelineV2` (局部导入, 应 patch 源模块) | [EXECUTION L1019](../EXECUTION_V3.4.0_UNIFIED_ROUTING.md#L1019) | ✅ 已修复 |

### 回归验证

| 批次 | 范围 | 结果 |
|------|------|------|
| 合并靶向回归 (R-01 修复后) | 15 个受影响测试文件 (配置/路由/诊断/断点/消融/优化器/CV/集成) | **250 passed / 1 skipped / 0 failed / 0 xfail** (430.80s) |
| 分项复跑 (修复后) | `test_unified_routing` + `test_structural_break_monitor` + `test_fix2_config_unification` | 41 passed (21.78s) |
| 分项复跑 (修复后) | `test_p3_phase3_optimizer` | 53 passed (7.55s) |
| 分项复跑 (修复后) | `test_backtest/test_ablation_runner` | 92 passed (14.74s) |
| 单项复跑 (R-01 定点) | `test_p3_phase3_threshold_drift_monitor` + `test_backtest/test_p2_2_optimizer_cv` | 19 passed (1.22s) |
| 手工校验 | `tests/test_backtest/verify_fix3_manual.py` | 通过 (预期位置 6/6) |

**零回归结论**: R-01 修复前 1 failed (`test_e8_10_integration_with_optimizer`); 修复后合并靶向 250 passed / 1 skipped / 0 failed。1 skip 为既有语义/条件 skip (按 checklist 判定规则豁免), 无新增失败、新增 skip 或 xfail。

---

## 评分

| 项 | 值 |
|----|-----|
| 修复前计数 | P0=0, P1=1, P2=3, P3=24 |
| 修复前数值分 | `100 − (0×20 + 1×8 + 3×3 + 24×1) = 59` → **C+** |
| 修复前字母级 (skill 表) | 0 P0, 1 P1 → **B+** |
| 修复后计数 | P0=0, P1=0, P2=0, P3=2 (C-03/E-02 记录性接受), 幻觉 1 条已剔除 |
| 修复后数值分 | `100 − 2 = 98` → **A+** |
| 提升 | **C+ → A+** (数值) / B+ → A+ (字母) |

> 说明: 修复前字母级与数值分不一致, 源于 skill 的双轨评分 — 字母表只看 P0/P1/P2, 数值公式对 P3 密集项敏感。本报告同时列出, 以数值分作为趋势追踪口径。

---

## 遗留与后续

| 项 | 归属 |
|----|------|
| C-03 `_log_spec` 写盘失败注入测试 | 可选测试补强 (低优先) |
| E-02 报告层 2 臂行数断言 | 可选测试补强 (口径已由 `test_run_l2_returns_2_results` 覆盖) |
| `verify_p2_2_manual.py` / `verify_p0_2_manual.py` | 已标 `.. deprecated:: v3.4.0 ADR-042`; 场景随字段删除失效, 不修 |
| A-03 误报 | 已记入幻觉日志; 该 subagent 其余发现均成立 |
| G7-8 提交 | 待用户明确指示 (本轮未提交) |

---

## 审计签署

| 项 | 值 |
|----|-----|
| 审计结论 | **PASS** (0 P0; 1 P1 回归已修复; 3 P2 + 24 P3 全部处置或记录; 1 条 subagent 误报剔除) |
| 阻塞交付 | 无 |
| 交付建议 | 可提交; 建议单原子 commit (代码 + 测试 + 版本 + 文档), 提交前 `git diff --cached --check` |
| 审计工件 | 本文件 + Phase 3.5 幻觉日志 (§Phase 3.5 表) + checklist v1.3 签署 |
