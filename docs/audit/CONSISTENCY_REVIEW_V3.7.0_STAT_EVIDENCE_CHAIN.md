# CONSISTENCY REVIEW v3.7.0 统计证据链 — 步骤 8 一致性审查

> **版本**: v1.0 (2026-11-18) — 步骤 8 产出
> **审查对象**: [EXECUTION_V3.7.0_STAT_EVIDENCE_CHAIN.md](../EXECUTION_V3.7.0_STAT_EVIDENCE_CHAIN.md) v1.1
> **上游**: `docs/private/DESIGN_STAT_EVIDENCE_CHAIN.md` v1.2（§21 步骤 4 复审、§22 步骤 6 补口、§23 本步对齐）
> **再上游**: [RESEARCH_STAT_EVIDENCE_CHAIN.md](../research/RESEARCH_STAT_EVIDENCE_CHAIN.md) v1.2 / [MULTIFACTOR_GOVERNANCE_ROADMAP.md](../analysis/MULTIFACTOR_GOVERNANCE_ROADMAP.md) §5 P1 / §6 G2
> **下游**: [CHECKLIST_V3.7.0_STAT_EVIDENCE_CHAIN.md](CHECKLIST_V3.7.0_STAT_EVIDENCE_CHAIN.md) v1.0
> **方法**: 逐节映射 + 关键断言逐字比对 + 上游代码锚点引用链复核（步骤 6 已做一手实证，本步不重复全量重放，只核对引用链是否仍指向既有行）
> **判定词**: `一致` / `偏差（已修）` / `偏差（接受，附理由）` / `缺口`

---

## §1 结论

**PASS_WITH_FIXES → 修正后 PASS。**

- 发现 **7 项偏差（F1-F7）**，全部为文档级：2 项版本/路径引用错误、2 项命令与表格可执行性、3 项措辞与来源标注。**无设计语义变更、无接口变更、无代码影响。**
- 设计侧仅 append 追加 §23 与 §15 标题修正（不改 D1-D14 任何锁定决策）。
- 无阻断项；EXECUTION 可继续作为步骤 9 的实施依据。

---

## §2 一致性矩阵（上游 → 下游）

| # | 维度 | 上游 | 下游 | 判定 | 证据 |
|---|------|------|------|------|------|
| 1 | 锁定决策覆盖 | 设计 §0 D1-D14 | EXECUTION §0.4 实施落点 | 一致 | 14/14 行一一对应，无漏项、无新增决策 |
| 2 | 路线图范围覆盖 | 路线图 §5 P1-①~⑥ + §6 G2 | EXECUTION §0.3 | 一致 | 7 行（6 项 + G2），每行有工件与测试编号 |
| 3 | 公共符号 | 设计 §11.1（6 组） | EXECUTION §2.1-2.6 签名 | 一致 | `cross_validation` 6 / `overfitting` 4 / `effect_size` 5 / spec logger 2 / ledger 2 / governance 2，无符号漂移 |
| 4 | 测试编号与总数 | 设计 §14 + §14.7 | EXECUTION §4（52 项） + CHECKLIST §3 | 一致 | 16+12+8+8+8=52；b 项 6 个（T12b/T14b/T32b/T40b/T41b/T45b）全部落位 |
| 5 | 性能预算 | 设计 §13（7 行） | EXECUTION §6（7 行） + CHECKLIST §5 | 一致 | 逐行同规模、同预算（DSR `<5ms` … holdout lock `<50ms`） |
| 6 | 兼容约束 | 设计 §12（8 条） | EXECUTION §7（10 项） + CHECKLIST §4（11 项） | 一致 | 10 项为 8 条展开；第 11 项「无新增依赖」取自 §5.2 门禁（F5 已加注） |
| 7 | 风险 | 设计 §16 R1-R10 | EXECUTION §8 X1-X9 | 偏差（接受） | 非一一映射，逐条落点见 §4；R5（中性化 curve）明确不在本批，X4/X5/X9 为实施新增 |
| 8 | ADR | 设计 §17 ADR-055~058 | EXECUTION §0.1 + CHECKLIST §7 | 一致 | 四条 ADR 标题与内容要点无冲突 |
| 9 | 样本映射 | 研究 §13（dev=58） / 设计 D13 | EXECUTION §0.4 D13 + §4 T13/T24 | 一致 | 58/56/54；2024-12 边界 purge；PBO 起点 2020-04、CPCV 起点 2020-06 |
| 10 | 版本锚点 | 设计 §12 缓存不变 | EXECUTION §3 + §8 X9 + CHECKLIST E8 | 偏差（已修） | 4 处代码/配置 + 2 个测试文件（含 `verify_fix3_manual.py` L21/L22）：F1 |
| 11 | 默认零变更 | 设计 D11 / §3.3 | EXECUTION §5.2 + §7 + §8 X1-X9 | 一致 | 不改 `backtest/__init__.py`、不改 `get_specification_curve` 5 键、不新增依赖 |
| 12 | 非目标未被偷偷实装 | 设计 §1.2 | EXECUTION §0.1 交付表 | 一致 | 无 GLX / 无自动调参 / 无新依赖 / 无自动阻断 |

---

## §3 偏差与处置

| # | 级别 | 位置 | 问题 | 处置 | 状态 |
|---|------|------|------|------|------|
| F1 | P2 | EXECUTION 头部 L4、§9 L600 | 仍引设计 **v1.1**，而设计已升 v1.2（§14.7/§22 已存在） | 头部改「v1.2（§21 / §14.7 / §22 / §23）」；§9 表同步 v1.2 | 已修 |
| F2 | P2 | CHECKLIST §5 G1/G2 | 门禁命令第二项起省略 `tests/test_backtest/` 前缀，照抄会 `file or directory not found` | 改为 5 / 3 个完整路径（与 EXECUTION §5.2 逐字一致） | 已修 |
| F3 | P2 | 设计 §15 标题 | 标题写「对应 E1-E10」，但表内实为 P1-P8，且 EXECUTION 阶段为 E0-E8 → 三套编号对不上 | 标题改「P1-P8；对应 EXECUTION E1-E8」，表后补阶段映射行（P1→E1 … P8→E8；E0 为实施新增） | 已修（设计 §23.1） |
| F4 | P3 | 设计 §15 各阶段测试列 | 阶段表区间未含 b 项（P3 缺 T32b、P4 缺 T40b、P6 缺 T41b/T45b） | 不改表体（历史保留），在映射行注明「测试编号以 §14 与 §14.7 为准，b 项随所属阶段交付」 | 已修（设计 §23.2） |
| F5 | P3 | CHECKLIST §4 | 兼容性 11 项比 EXECUTION §7 多 1 项且未标来源，审计易误判为「下游自行加约束」 | 表前加注：1-10 对应 EXECUTION §7，第 11 项取自 §5.2 门禁 | 已修 |
| F6 | P3 | CHECKLIST §3.5 T45b | 只写「缺 `n_periods`」，设计 §14.7 要求四键（`metric`/`value`/`n_periods`/`same_sign`）任一缺失即报错 | 补全四键与「类型错」 | 已修 |
| F7 | P3 | 设计 §14.3 T30 | 「`alpha` 合法」表述歧义（未说明非法时的行为） | 不改原文（append-only），§23.3 注记「以 EXECUTION §4.3 为准：`alpha` 非法 → `ValueError`」；同条覆盖 T17/T19 的展开式差异 | 已修（设计 §23.3） |

**偏差分级说明**：P2 = 会误导实施或产生不可执行命令；P3 = 表述/来源层面的可读性问题。无 P1。

---

## §4 风险映射明细（设计 §16 → EXECUTION §8）

| 设计 | 内容摘要 | EXECUTION 落点 | 判定 |
|------|---------|----------------|------|
| R1 | 回顾性不可追认 | D14 + T14b + `assert_locked_before` | 一致 |
| R2 | stationary vs 原文 iid | X6 | 一致 |
| R3 | T=58 检验力低 → 预期 downgrade | X3 | 一致 |
| R4 | dev=58 导致 PBO/CPCV 裁切 | D13 + T24 + §6 性能规模 | 一致 |
| R5 | Barra 断档、中性化样本短 | 不在本批（路线图后续）；EXECUTION 未列 | 偏差（接受）：属范围外，非遗漏 |
| R6 | 双 DuckDB 文件 | X1 | 一致 |
| R7 | 旧 8 位 `commit_hash` 长期存在 | §7 #1/#2/#5 | 一致 |
| R8 | stage 不入指纹 | X7 + T46 + `test_family_stage_idempotent` | 一致 |
| R9 | G2 误用 | X8 | 一致 |
| R10 | 并发写 registry | X2 | 一致 |
| — | （实施新增）MC 随机失败 / 矩阵长度不一致 / 版本锚点遗漏 | X4 / X5 / X9 | 偏差（接受）：合理补充 |

---

## §5 编号与术语一致性

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 阶段编号 | 一致（修正后） | 设计 P1-P8 ↔ EXECUTION E0-E8；E0 为实施新增的基线冻结，设计无对应（F3 已注） |
| 测试总数 | 一致 | 52；分节 16/12/8/8/8；`§4.6` 8 个扩展用例不计入 52 |
| b 后缀项 | 一致 | 6 项，全部有归属节与红形态（设计 §14.7 = EXECUTION §0.5 C1-C3） |
| 补口编号 C1-C3 | 一致 | C1→T32b、C2→T41b、C3→T45b；EXECUTION §0.5 与设计 §14.7 双向可查 |
| 方法名常量 | 一致 | `governance._FDR_METHODS/_FWER_METHODS` ↔ `CorrectionMethod` 七值，由 T41b 锚定 |
| `check` 返回键 | 一致 | 9 键定案（§2.1 规则行 + T09），设计未规定键集，无冲突 |
| 阶段读数列 | 一致 | EXECUTION §5.3 八行（E1-E8）+ E0 基线在 §5.1，CHECKLIST §2 对应 |
| 证据等级 | 一致 | CHECKLIST §1 E1-E5 与仓内既有清单一致 |

---

## §6 缺口检查（过度设计 / 欠设计）

| 方向 | 检查 | 结论 |
|------|------|------|
| 过度设计 | 每个新增公共符号都有 ≥1 个测试锚定；无「预留但未用」参数；无新增依赖（AST/`git diff pyproject.toml` 可验） | 无 |
| 欠设计 | P1 六项 + G2 全部有工件与测试；D1-D14 全部有落点；四条 ADR 有要点 | 无 |
| 范围外遗留 | U1（AFML 页码）、U3（GLX 细节）、R5（中性化 grid）、因子层 PBO | 已明确标注为后续/可选，不阻塞本批 |
| 禁止事项可检验性 | §1「禁止」3 条均可用 `git diff` 或测试断言验证（不改 `__init__.py`；不改 5 键；不提前 E6） | 可检验 |

---

## §7 审查通过的不变量（步骤 9 不得破坏）

| # | 不变量 | 验证方式 |
|---|--------|---------|
| 1 | `log_run` 返回 8 字符 `commit_hash` | `test_log_run_returns_hash` |
| 2 | `get_specification_curve` 恰好 5 键 | T35 + 既有测试 |
| 3 | `test_specification_logger.py` 既有 19 项不改 | 该文件既有用例计数 |
| 4 | `FamilySpec.fingerprint()` 不含 `stage`、值不变 | T46 + 扩展用例 |
| 5 | `holdout_checker=None` 时旧行为逐位一致 | §7 #4 |
| 6 | `GovernanceRecord` 不传新字段仍可构造 | `test_governance.py` |
| 7 | Python 3.9 语法（无 PEP 604） | AST 扫描 |
| 8 | 缓存代际 `v2.3.0-cache` 不变 | 版本测试 + `git diff` |
| 9 | golden master 同环境 `rtol=1e-10` 零差异 | `test_golden_master.py` |
| 10 | `evaluate_g2` 纯函数、不写库、不自动阻断 | 代码评审 + 无 DuckDB 写入调用 |
| 11 | DSR `N=1` 退化禁止（显式 `ValueError`，不返回 DSR=1） | T18 |
| 12 | PBO 严格整除（`T%S!=0` 报错，不用不等长块） | T24 |

---

## §8 对步骤 9 的约束（本审查的衍生命令）

1. 52 项测试必须逐项登记红→绿双读数（红形态见 EXECUTION §4）；红读数缺失的用例不得标绿。
2. §4.6 的 8 个扩展用例同样要红→绿（其中 `test_legacy_record_read` 等表征类可先绿，须注明「表征测试，先绿」）。
3. 性能实测超预算只披露，不降 `B`、不换 bootstrap 类型、不改统计口径（EXECUTION §6）。
4. MC 用例（T22/T38）换 seed 时必须在 EXECUTION §5.3 与 CHECKLIST §3 双登记。
5. 步骤 9 完成后回填：EXECUTION §0.1 状态列、§5.3、§6；CHECKLIST 全表状态；本文件不改（历史审查记录）。

---

## §9 汇总

| 分项 | 项数 | 一致 | 偏差（已修） | 偏差（接受） | 缺口 |
|------|------|------|-------------|-------------|------|
| 一致性矩阵 | 12 | 10 | 1（F1） | 1（风险映射） | 0 |
| 偏差处置 | 7 | — | 7 | 0 | 0 |
| 风险映射 | 10 | 9 | — | 1（R5 范围外） | 0 |
| 不变量 | 12 | 12 | — | — | 0 |

> 计数由逐行状态得出（RULE-2）；「偏差（接受）」不计为通过项，但在结论中单独披露。
> **审查结论：PASS（修正后）** —— F1-F7 全部闭环，EXECUTION v1.1 可进入步骤 9 TDD 实施。

---

## §10 复审附记（2026-11-18，异构复审后追加）

本文件 §3-§9 为**计划期**审查记录，按 §8.5 约定正文不改。异构复审发现唯一 P2 真实缺陷 H1
（常数序列浮点假阳绕过零方差守卫），修复后补 3 例回归测试（T26b/T33b/T40c），故终态为
**55 项 = 52 计划 + 复审修正 3**，全量回归 1929 passed。凡本文与终态口径不一致处
（如 §3#4「16+12+8+8+8=52」、§8.1「52 项」），以
[EXECUTION §4](../EXECUTION_V3.7.0_STAT_EVIDENCE_CHAIN.md)（55 项）与
[审计报告](2026-11-18-v3.7.0-stat-evidence-chain-audit.md)（PASS_WITH_FIXES）为准。
