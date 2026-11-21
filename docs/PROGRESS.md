# PROGRESS 待办登记

> 依据 SPEC_PROCESS 约定建立（每步完成后更新）。状态词表: `pending / in-progress / blocked / done`——值域与派生规则见 [SPEC_COMPLIANCE.md](SPEC_COMPLIANCE.md) §6-§7（对齐 `F:\Spec_Workflow\spec\doc-contract\PLAN.md` **DC2.1**）。
> 登记日期: 2026-11-20
> **登记时点纪律**: **立项即登记**——新批次开工前先写 P 行（状态 = `pending`；等外部条件则 `blocked`），未登记不得进入步骤 1。
> **编号口径**: **P 号 = 工作项登记**（含待开工）；观察项与跨仓等对方项不占号，记入所在批次文档。编号单调、不复用；语义变更新建 P 行并在旧行注明 `superseded by P-xxx`。
> **档位口径**: 批次档位（T1/T3）在批次 DESIGN 登记，本表不单列，避免双写。
> **存量豁免**: 本文件建于 2026-11-20（治理批 P-001），此前历史待办不回改，只登记现存项。

## 待办事项

| ID | 事项 | 依据 | 状态 | 优先级 | 验收标准 |
|----|------|------|------|--------|---------|
| P-001 | 规范治理批：`spec/` 骨架 + 四模板 + v3.9.2 四件套迁移 + front-matter + PROGRESS + ADOPTION + dev-log | 2026-11-20 合规审计（6 项硬差距） | done | P0 | ① `spec/templates/` 四模板到位；② `spec/v392-calibration-unit-fix/` 六文档含 DC1 front-matter；③ `docs/PROGRESS.md` 接管待办；④ `docs/SPEC_COMPLIANCE.md` 登记偏差与豁免；⑤ 旧路径引用清零；⑥ E-TODO 出口门禁写入 `SPEC_COMPLIANCE.md` §7 |
| P-002 | v3.9.3 alpha 衰减模型选择：`rho` 改由 IC / alpha 期限结构估计；复核 DESIGN §7「组合收益序列」选项（FO-1） | [RESEARCH.md](../spec/v393-alpha-decay-model/RESEARCH.md)（Step 1-2 + §9 补充调研 + §11 异构复审，v1.3 verified）/ [DESIGN.md](../spec/v393-alpha-decay-model/DESIGN.md)（Step 3-4，v1.1 verified）/ [IMPLEMENTATION.md](../spec/v393-alpha-decay-model/IMPLEMENTATION.md)（Step 5-6，v1.1 verified，§8 复审 PASS_WITH_FIXES；§9 Step 9 实测读数：phi=1.0、m(5)=0.382、m(10)=0.395、net(10)=+0.91M、net(20)=+18.1M、verdict 双 flat）/ [CHECKLIST.md](../spec/v393-alpha-decay-model/CHECKLIST.md)（Step 7-10，**accepted**，70/70 通过）/ [AUDIT.md](../spec/v393-alpha-decay-model/AUDIT.md)（Step 10 独立子代理审计，PASS 有条件：2×P2 + 4×P3 → P-012，无 P1） | done | P0 | ① 39 月校准 `net(h)>0` 对 h∈{5,10,20} 至少一点成立且可复现 ✅（net(10)=+905,290 / net(20)=+18,115,106，曲线工件 SHA 两次逐位一致）；② rho 估计入选口径写入 DESIGN 并有 E1 证据 ✅（alpha0_anchored=A(20)=0.00220065 vs alpha0_calendar=0.00262866，−16.3%）；③ 默认 SHA 不变 ✅（`82728CE1…` 三方一致） |
| P-012 | v3.9.3 审计遗留修复包：F-1 bootstrap 回退 net lo/hi 补 (h_m/h) 因子 + 独立单测（`n_bootstrap=50` 即可触发，无需 monkeypatch，见 v3.9.4 RESEARCH §3.1）；F-2 IMPLEMENTATION §5 通过线勘误；F-3 DESIGN `phi_status` 枚举同步（"prior"）；F-4 `DecayCurve` 死类型裁决；F-5 D5 plateau 落点裁决；F-6 退化态 `m_sensitivity` 守卫 | [AUDIT.md](../spec/v393-alpha-decay-model/AUDIT.md) §5（Step 10 独立子代理审计，D-002 整改口径：审计不写代码）/ [RESEARCH.md](../spec/v394-audit-coverage-fix/RESEARCH.md)（Step 1-2，v1.1 verified）/ [DESIGN.md](../spec/v394-audit-coverage-fix/DESIGN.md)（Step 3-4，v1.1 verified，异构复审 PASS_WITH_FIXES 已修复）/ [IMPLEMENTATION.md](../spec/v394-audit-coverage-fix/IMPLEMENTATION.md)（Step 5-6，v1.1 verified，§10 复审 PASS_WITH_FIXES 已修复）/ [CHECKLIST.md](../spec/v394-audit-coverage-fix/CHECKLIST.md)（Step 7-10，**accepted**：70/70，Step 10 审计 PASS） | done | P1 | ① F-1 修复后 point∈[lo,hi] 恒成立且有独立单测；② F-2/F-3 文档勘误落地；③ F-4/F-5 逐项裁决留痕（保留/接线/删除）；④ F-6 退化态口径一致；⑤ 默认 SHA 不变 |
| P-013 | v3.9.3 E3 锚点重绑：AUDIT/CHECKLIST 中「工作区未提交，以文件+行号登记」改为绑定 commit `a0cf914` | v3.9.3 [CHECKLIST.md](../spec/v393-alpha-decay-model/CHECKLIST.md) §12（触发条件「`backtest/execution/` 提交后」已由 `a0cf914` 满足）；[AUDIT.md](../spec/v393-alpha-decay-model/AUDIT.md) §7/§8 | done | P1 | ① AUDIT §7 / CHECKLIST §12 两处 E3 声明改为 commit 锚点 ✅；② 行号抽查仍指向正确代码 ✅（v3.9.4 调研复核 8 处锚点） |
| P-014 | Chen & Velikov 元数据订正（RFS → JFQA） | [RESEARCH_V3.8.0_EXECUTION_CAPACITY.md](../docs/research/RESEARCH_V3.8.0_EXECUTION_CAPACITY.md) L699/L860；v3.9.3 [CHECKLIST.md](../spec/v393-alpha-decay-model/CHECKLIST.md) §12 | pending | P2 | ① 两处期刊名与卷期订正；② 引文核验留痕（按 SPEC_PROCESS 引用核验四步） |
| P-015 | v3.9.4 Step 10 审计遗留 3×P3：① `decay.plateau()` 补 core 直接契约单测（max−sd 边界，现仅 T394-4 间接覆盖且半同义反复）；② script md 标题版本号参数化（硬编码「v3.9.3」致 v3.9.4 工件标题滞留）；③ `--force-coverage` 真实低覆盖数据 E2E | v3.9.4 [CHECKLIST.md](../spec/v394-audit-coverage-fix/CHECKLIST.md) §8.2（Step 10 独立子代理审计 PASS：0×P1 + 0×P2 + 3×P3） | pending | P3 | ① core 单测绿（含 max−sd 边界）；② 生成工件标题随包版本；③ E2E exit 0 + `coverage_gate_forced:` 留痕断言 |
| P-016 | P-003 Step 10 审计遗留：2×P2（① INV-6 买卖共享重抽样索引补 monkeypatch 断言「仅调用 1 次且两读数取同一 idx」；② 脚本层截面 demean 补形成日截面均值≈0 断言）+ 3×P3（③ 删除 T3100_3 恒真断言、改为断言 demean 幅度；④ T3100_9 补已知分位断言（常数输入 lo=hi=point）；⑤ `reversal_counts` 补「15 键字面量集合」整体断言） | v3100 [CHECKLIST.md](../spec/v3100-reversal-evidence/CHECKLIST.md) §8.2（Step 10 独立子代理审计 PASS_WITH_FIXES：0×P1 + 2×P2 + 6×P3，其中 3×P3 文档类已就地关闭） | pending | P2 | ① 两条 P2 单测绿且能区分「各抽各的索引」；② 三条 P3 断言非恒真；③ 全量 pytest 0 failed；④ 默认 SHA / `panel_hash` 不变 |
| P-003 | 截面 T+1 reversal 真实现：`reversal_bps = −s·(P_{t+1}−P_t)/P_t`，替代 `temporary_share` 的组合 AR(1) 代理。**口径裁决（2026-11-21，用户）：走口径 A——仅证据层真实现，不进 `cost_by_h`，`net(h)` / 容量读数不变**（证据见 [RESEARCH_P003_P007_DECISIONS.md](research/RESEARCH_P003_P007_DECISIONS.md) §2） | [RESEARCH.md](../spec/v392-calibration-unit-fix/RESEARCH.md) §6 U6 / §7 B11 ／ [RESEARCH_P003_P007_DECISIONS.md](research/RESEARCH_P003_P007_DECISIONS.md) §2 ／ [v3100 RESEARCH.md](../spec/v3100-reversal-evidence/RESEARCH.md)（Step 1-2 + Step 9 回填，**v1.3 verified**：§3.5 已用 C1/C2 × 新旧对照表替换「待 E1」）／ [v3100 DESIGN.md](../spec/v3100-reversal-evidence/DESIGN.md)（Step 3-4，**v1.3 verified**：D1-D12 + 6 个被拒备选；§12.4 勘误 E-2、锚点刷新、Step 10 审计留痕）／ [v3100 IMPLEMENTATION.md](../spec/v3100-reversal-evidence/IMPLEMENTATION.md)（Step 5-6，**v1.2 verified**：6 模块 + 4 接口 + T3100-1~10 + §11 增 E-2/E-3 与 Step 9 实测摘要）／ [v3100 CHECKLIST.md](../spec/v3100-reversal-evidence/CHECKLIST.md)（Step 7-10，**v1.2 verified，有条件通过**：81 项 = 80 通过 / 0 失败 / 1 待办；Step 10 独立审计 **PASS_WITH_FIXES**（4.60/5，A；0×P1、2×P2、6×P3 → P-016）） | done | P1 | ① 输入契约（交易方向 + 截面价格）落 DESIGN ✅（§2.1 D1/D3、§3.3）；② 代理与真实现差异对照表 ✅（RESEARCH §3.5 双列）；③ 单测覆盖符号/停牌/涨跌停边界 ✅（T3100-1~10 + runner，子集 11 passed）；④ 口径 A 硬不变式 ✅（默认 SHA `82728CE1…`、`panel_hash dfcc4e1d…`、`cost_by_h`/`net`/容量逐位不变）；⑤ 实测：C1 `reversal_bps` **−2.842**〔−14.974,+10.366〕、C2 **−2.420**〔−11.810,+5.938〕，相对差 14.8%/12.9%/13.5%（≤50% → U-1 自动通过）；73 形成月/72 聚类；全量 **2076 passed / 15 skipped / 0 failed** |
| P-004 | 覆盖度 `universe_ratio` 可 >1 → 改交集口径（`|M∩U|/|U|`，保留 `ratio_raw` 披露；门禁阈值定标见 v3.9.4 RESEARCH U-1） | v3.8.1 审计观察（A-7）/ [RESEARCH.md](../spec/v394-audit-coverage-fix/RESEARCH.md) §3.3（v1.1 verified，层位约束：仅 ratio 层交集）/ [DESIGN.md](../spec/v394-audit-coverage-fix/DESIGN.md) §4.2（D8/D10/D11）/ [CHECKLIST.md](../spec/v394-audit-coverage-fix/CHECKLIST.md) §2.1 + §4 INV-3（Step 7-10：39 月实测 `universe_ratio` ∈ [0.9815, 0.9997] 全部 ≤1、`ratio_raw` 完整复现旧值（审计 B1 逐位核验）、`panel_hash` 逐位不变；Step 10 审计 PASS） | done | P1 | ① 39 月 `universe_ratio ≤ 1` 恒成立；② **`panel_hash` 逐位不变**（研究结论 B-2，原「哈希变更登记」前提不成立，已修正）；③ 覆盖率读数（README / PROJECT_STATUS）同步 |
| P-005 | `--force-coverage` 警告写入 `evidence_warnings` | v3.8.1 审计观察 / [DESIGN.md](../spec/v394-audit-coverage-fix/DESIGN.md) §4.3（D9：token 化 `coverage_gate_forced`）/ [CHECKLIST.md](../spec/v394-audit-coverage-fix/CHECKLIST.md) §2.3（Step 7-10：接线级证据 + T394-6；Step 10 审计补齐三端静态闭环 script→`attach_panel_meta`→report，裁决可接受；真实低覆盖 E2E 并入 P-015） | done | P1 | ① 强制放行时 `evidence_warnings` 含固定文案；② 端到端用例断言 exit 0 + 留痕 |
| P-006 | `tradability` 模块接入回测引擎（当前为独立函数）＋**并入 P-007 限价取整口径**：判定侧取四舍五入 half-up 或直接读数据源 `limit_up/limit_down`；成交价假设独立取值（见 [调研 §1.6](research/RESEARCH_P003_P007_DECISIONS.md)） | v3.9.0 已知限制 ／ 2026-11-19 任务分析 B1（P-007 并入）／ [RESEARCH_P003_P007_DECISIONS.md](research/RESEARCH_P003_P007_DECISIONS.md) §1 | pending | P2 | ① 引擎路径调用限价规则；② 默认路径输出不变（SHA 或逐位复算）；③ 回归用例；④ 限价取整裁决记录落 DESIGN（tie / 除权日 / 板块切换日用例） |
| P-007 | ~~限价取整口径裁决~~ **已并入 P-006（2026-11-21，用户裁决）**，本行关闭、不再单列 | 2026-11-19 任务分析 B1 ／ [调研 §1.6](research/RESEARCH_P003_P007_DECISIONS.md)（superseded by P-006） | done | P2 | ① 范围已转移至 P-006（取整口径 + 影响面）；② 影响面实核结论已留痕（仅自算限价路径受影响，容量主路径用 `detect_limit_lock` 不受影响） |
| P-008 | 数据行数对齐（分钟 / 日频覆盖核对） | 2026-11-19 任务分析 C1 | pending | P2 | ① 39 月逐月行数差异表；② 差异 >5% 的月份有归因说明 |
| P-009 | 内生性-溢价诊断交互 | PROJECT_STATUS §1 路线图 v3.5.x 远期 | pending | P3 | ① 交互矩阵 DESIGN 通过步骤 4 复审；② 诊断输出新增键有回归 |
| P-010 | 股票×日 vs 股票×月粒度偏差 — 量化偏差并决定是否按股票×月重采样 | [RESEARCH.md](../spec/v392-calibration-unit-fix/RESEARCH.md) §7 B9 / [DESIGN.md](../spec/v392-calibration-unit-fix/DESIGN.md) §1.2 | pending | P2 | ① 39 月股票×月重采样对照表；② 偏差量化（系数/CI 变化）；③ 若采纳，`panel_hash` 与成本口径变更说明 |
| P-011 | DEV_PROGRESS §4 存量待办复核（11 条：冻结模型实证回测、流式处理、Anderson-Rubin、MissingTypeDiagnoser 因果版、`types.py` 重命名等） | [DEV_PROGRESS.md](DEV_PROGRESS.md) §4（已冻结） | pending | P2 | ① 逐条裁决为「关闭 / 转 P / 不修复」并留证据；② 裁决结果回填本表，DEV_PROGRESS 不再承载待办 |

## 优先级口径

| 优先级 | 定义 | 当前 |
|--------|------|------|
| P0 | 阻塞结论或发布 | （无——P-002 已 done） |
| P1 | 证据完整性 / 口径缺口 | P-003 |
| P2 | 工程化与存量复核 | P-006 / P-008 / P-010 / P-011 / P-014 |
| P3 | 远期能力 | P-009 / P-015 |

## 更新规则

1. 每步完成后更新对应行状态；`done` 行保留，不删除（历史可追溯）。
2. `done` 必须附证据链接（IMPL/AUDIT/用例）；`blocked` 必须写触发条件（HTML 注释 `<!-- todo: trigger=… -->`）。
3. 每批收尾执行 **E-TODO 出口门禁**（[SPEC_COMPLIANCE.md](SPEC_COMPLIANCE.md) §7），映射率不足 100% 不得置 CHECKLIST 为 `accepted`。
