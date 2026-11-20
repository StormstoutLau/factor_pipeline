# CONSISTENCY REVIEW v3.8.0 多日执行模型 + Regime 容量压力测试 — 步骤 8 一致性审查

> **版本**: v1.0 (2026-11-19) — 步骤 8 产出
> **审查对象**: [EXECUTION_V3.8.0_EXECUTION_CAPACITY.md](../EXECUTION_V3.8.0_EXECUTION_CAPACITY.md) v1.1（§9 步骤 6 review PASS_WITH_FIXES）
> **上游**: [DESIGN_EXECUTION_CAPACITY_V3.8.0.md](../private/DESIGN_EXECUTION_CAPACITY_V3.8.0.md) v1.2（§22 步骤 4 复审、§7.1/§16.2 步骤 6 对齐、§23 本步对齐）
> **再上游**: [RESEARCH_V3.8.0_EXECUTION_CAPACITY.md](../research/RESEARCH_V3.8.0_EXECUTION_CAPACITY.md) v1.0（三轮 + §19 异构复审；§16 D1-D4 锚点、§17 S1-S7 架构契约）
> **下游**: [CHECKLIST_V3.8.0_EXECUTION_CAPACITY.md](CHECKLIST_V3.8.0_EXECUTION_CAPACITY.md) v1.0
> **方法**: 逐节映射 + 关键断言逐字比对 + 源代码锚点引用链复核（步骤 5/6 已做一手实证：脚本 12 处行锚点、`effect_size`/`data_contract`/`backtest/__init__`/`pyproject` 全部逐位核对，本步不重复重放，只核对引用链是否仍指向既有行）
> **判定词**: `一致` / `偏差（已修）` / `偏差（接受，附理由）` / `缺口`

---

## §1 结论

**PASS_WITH_FIXES → 修正后 PASS。**

- 发现 **10 项偏差（F1-F10）**：3 项 P2（设计内部分支数自相矛盾、版本锚点缺 pyproject 版本号、EXECUTION 缺 D1-D4 落点表）、7 项 P3（交付形态文件名漂移 ×2、调研契约修订未注记 ×3、清单公式笔误、清单 E4 验收缺项）。**全部已修或在设计 §23 注记闭环。**
- 无设计语义变更：D1-D4、S1-S7 契约、L0/L1/L2 降级、D2 守卫、量纲纪律均未被触碰；调研 S2/S4/S6 的三处修订均为步骤 3 设计期已发生、本步补注记。
- 无阻断项；EXECUTION 可继续作为步骤 9 TDD 的实施依据。

---

## §2 一致性矩阵（上游 → 下游）

| # | 维度 | 上游 | 下游 | 判定 | 证据 |
|---|------|------|------|------|------|
| 1 | 锁定决策覆盖 | 设计 §0 D1-D4（含 §0.3 口径发现） | EXECUTION §0.4 实施落点 | 偏差（已修） | EXECUTION 原无 D1-D4 汇总表（仅散落 D2/D3）→ 新增 §0.4 四行表；F3 |
| 2 | 路线图范围覆盖 | 路线图 P2 两项 | EXECUTION §0.3 | 一致 | 「组合/容量未成为上线门禁」「冲击模型 stylized」均有本批对应（证据层 + 压力档） |
| 3 | 公共符号/端口 | 调研 §17.2 S2 → 设计 §4 → EXECUTION §2.1/§2.5 | CHECKLIST §3 | 偏差（接受） | `ImpactModel.predict` 调研 4 参（含 `adv`）/bps → 设计/EXECUTION 3 参/率：F6 注记（设计 §23.1）；`SpreadEstimator`/`VolumeClassifier`/`DecayModel` 三端口逐字一致 |
| 4 | 测试编号与总数 | 设计 §16.1-16.5 | EXECUTION §5.1（56 项） + CHECKLIST §3 | 一致 | 10+8+8+8+6+10+2+3+1=56；步骤 6 R-E7 后设计 §16.2 与 EXECUTION §5.1 组成逐一对齐；`ExponentialDecay` 断言并入 T380-27/28（R-E2） |
| 5 | 性能预算 | 设计 §17（5 行） | EXECUTION §6（5 行） + CHECKLIST §5.2 | 一致 | 单月 <60s / 39 月 <40min / L1 全量 <5min / 峰值 <2GB / 默认路径同量级，三处逐行同值 |
| 6 | 兼容约束 | 设计 §13.2/§18.2 | EXECUTION §3/§8.1（R1-R4） + CHECKLIST §4（13 项） | 一致 | 13 项为设计五条纪律 + 快照/空 diff/extra 细则展开；pyproject 版本锚点 F2 已修 |
| 7 | 风险 | 设计 §20（Q1-Q3 + 7 风险） | EXECUTION §8.2（9 行） + CHECKLIST §6（X1-X9） | 一致 | Q2/Q3 已由步骤 6 R-E8 带入（X8/X9）；Q1→X1；7 风险逐一对应 |
| 8 | 架构契约 | 调研 §17 S1-S7 | 设计 §3/§4 → EXECUTION §3.7/§2 → CHECKLIST §3.8/3.9 | 偏差（接受） | S3 registry 形状 / S5 三级降级 / S6 四条机械检查 / S7 边界 逐条落位；S2/S4/S6 三处修订见设计 §23.1（F6/F7/F8）；S1 Core 只依赖 numpy 与 `math`（stdlib）不冲突 |
| 9 | 证据等级 | 调研 §17.5 S5（L0/L1/L2） | 设计 §8 → EXECUTION §2.4/§7.3 → CHECKLIST §1 规则 6 | 一致 | `minutes/ohlc/daily` 三值；「每行必带 evidence_level」「L1/L2 禁称已校准」两处硬约束均落 checklist 状态规则 |
| 10 | 版本锚点 | EXECUTION §3.1 | CHECKLIST §7 | 偏差（已修） | 原 5 处缺 `pyproject.toml` 版本号（v3.7.0 先例有）→ 改 6 处；CHECKLIST E7/§7 同步；F2 |
| 11 | 默认零变更 | 设计 §0.5 第 5 条 | EXECUTION §0 头部纪律/§2.11/§8.1 + CHECKLIST §4#1/§5 G3 | 偏差（已修） | 设计三处写「2 分支」与 §11/§13.3 的 3 分支自相矛盾 → 统一 3 分支；F1 |
| 12 | 非目标未被偷偷实装 | 设计 §1 / EXECUTION §4 排除表 | — | 一致 | 无点估计 c 入报告 / 无参数自动调优 / 无 entry_points / 校准不回写默认 c（D2）；§4 scipy 行理由已按步骤 6 R-E4 修正 |

---

## §3 偏差与处置

| # | 级别 | 位置 | 问题 | 处置 | 状态 |
|---|------|------|------|------|------|
| F1 | P2 | 设计 §0.5 第 5 条 / §18.2 / §20 回滚 | 三处写「脚本只加 2 个分支（约 40 行）」，与 §11、§13.3 及 EXECUTION 的 **3 分支**（含 `--diagnose-window`）自相矛盾 | 三处统一为「+3 分支（约 60 行）」 | 已修 |
| F2 | P2 | EXECUTION §3.1 / CHECKLIST §7 | 版本锚点 5 处缺 `pyproject.toml` `version` 升级（3.7.0→3.8.0，L7）；v3.7.0 批次先例有此项，漏掉会版本号与 CHANGELOG 脱节 | §3.1 改 6 处并加行；CHECKLIST §7 注销预警、E7 改「6 处」 | 已修 |
| F3 | P2 | EXECUTION §0 | 缺 D1-D4 实施落点表（v3.7.0 有 §0.4 先例；仅散落 D2/D3，D1/D4 无下游索引） | 新增 EXECUTION §0.4 四行表（D1→§2.3/§3.2/T380-56；D2→§4/T380-50；D3→§2.8/T380-45~47；D4→§2.8/T380-30~32） | 已修 |
| F4 | P3 | EXECUTION §0.1 E0/E1 + §1 E0 | E0 交付缺 `core/spread.py`（设计 §19 E0 已含，步骤 5 曾专门对齐）；E1 形态写 `shell/aggs`（§3.7 布局无此文件） | E0 形态补 spread.py；E1 改 `shell/loaders.py`（分钟聚合）；§1 E0 产出补价差代理 | 已修 |
| F5 | P3 | EXECUTION §0.1 E6 | 形态写 `shell/rolling.py`，十四文件布局无此模块（AveW/漂移诊断在 runner） | 改 `shell/runner.py` 并注明「无独立 rolling 模块」 | 已修 |
| F6 | P3 | 调研 §17.2 vs 设计 §4 | S2 契约 `predict(participation, sigma, adv, params)` 返回 bps；设计/实施为 3 参（无 `adv`）返回**率**——步骤 3 设计期的有意修订但无注记 | 设计 §23.1 注记：`adv` 冗余（participation 已是参与率）；单位遵循 §12.5 量纲纪律（内部率、报告 ×1e4） | 已注记（偏差接受） |
| F7 | P3 | 调研 §17.4 S4 vs 设计 §3.3 | S4 装配点写扁平 `backtest/execution/runner.py`；设计/实施为 `shell/runner.py` | 设计 §23.1 注记：S1 分层要求编排归 Shell；唯一装配点性质不变 | 已注记（偏差接受） |
| F8 | P3 | 调研 §17.1/17.6 vs EXECUTION T380-53 | S6 Core 禁表无 `pandas`；EXECUTION 额外禁 `pandas`（更严） | 设计 §23.1 注记：与「端口不接受 DataFrame」契约一致 | 已注记（偏差接受，加严） |
| F9 | P3 | CHECKLIST §3.2 T380-15 | 展开式写 `S = 2√(4·E[(c−η)(c−η₊₁)])`，多乘一个 2（正确为 `S = √(4·E[(c_t−η_t)(c_t−η_{t+1})])`，即 `2√E[(c_t−η_t)(c_t−η_{t+1})]`） | 改为正确展开式；`c_t = ln(close)` 同步 | 已修 |
| F10 | P3 | CHECKLIST §2 E4 | DoD 缺设计 §19（R-D8 修复项）要求的「`D_i` 分布与 `p_cap` 触发率」诊断输出 | DoD 补「校准 JSON 含 `D_i` 分布与 `p_cap` 触发率」 | 已修 |

**分级说明**：P2 = 会误导实施或造成版本/决策脱链；P3 = 表述/注记层面。无 P1。

---

## §4 风险映射明细（设计 §20 → EXECUTION §8.2 → CHECKLIST §6）

| 设计 | 内容摘要 | EXECUTION | CHECKLIST | 判定 |
|------|---------|-----------|-----------|------|
| Q1 | 父包重导入副作用 | §8.2 风险 1 | X1（T380-56 前置判定） | 一致 |
| 风险 2 | AR 常数/`c_t` 未核 | §8.2 风险 2 | X2（`[待核]` 标注） | 一致 |
| 风险 3 | 39 个 OOS 点功效不足 | §8.2 风险 3 | X3（D3 不选窗） | 一致 |
| 风险 4 | 分钟无逐笔方向 | §8.2 风险 4 | X4（c 一律 `[区间]`） | 一致 |
| 风险 5 | 2023-04 后无分钟 | §8.2 风险 5 | X5（`[代理推断]`） | 一致 |
| 风险 6 | 校准把风险改小 | §8.2 风险 6 | X6（`max(0.5, upper)`） | 一致 |
| 风险 7 | 默认口径 4 倍不一致 | §8.2 风险 7 | X7（ratio(p) 诊断） | 一致 |
| Q2 | ST 5% 规则未核实 | §8.2 风险 8（R-E8 补） | X8 | 一致 |
| Q3 | 2023-03 尾月 | §8.2 风险 9（R-E8 补） | X9（`partial_month` 标记） | 一致 |
| — | 回滚（EXECUTION §8.1） | R1-R4 | CHECKLIST §6 回滚表 | 一致（v3.7.0 无此先例，本批为实施新增，合理） |

---

## §5 编号与术语一致性

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 阶段编号 | 一致 | 设计 §19 E0-E7 ↔ EXECUTION §0.1/§1 ↔ CHECKLIST §2，八行一一对应；E0 含 spread.py（F4 修后） |
| 测试总数 | 一致 | 56；分节 10/8/8/8/6/10/2/3/1；设计 §16.2（2+3+2+3=10）与 EXECUTION capacity 文件逐项对齐（R-E7） |
| T380 编号 | 一致 | T380-01…56 连续无跳号；CHECKLIST §3 红形态列与 EXECUTION §5.1 同源 |
| 分支口径 | 一致（修正后） | 3 分支：设计 §0.5/§11/§13.3/§18.2/§20 ↔ EXECUTION §2.11/§7.1（G5-G7）↔ CHECKLIST G5-G7 |
| 版本锚点 | 一致（修正后） | 6 处：EXECUTION §3.1 ↔ CHECKLIST §7（F2） |
| 文件布局 | 一致（修正后） | 14 文件：EXECUTION §3.7 ↔ 设计 §3.3；§0.1 形态列不再引用布局外文件（F4/F5） |
| `evidence_level` | 一致 | 三值枚举 + 每行必带 + L1/L2 禁「已校准」，四处同文 |
| 配置常量 | 一致 | `sigma_clip(0.005,0.20)` / `windows(24,36,48,60)` / `kappa=1.5` / `p_cap=0.10` / `d_max=5` / `lambda_p_threshold=0.05` / `seed=20261118` / `spread>0.30` / `bvc_sigma_bars=20`，EXECUTION §2.2 与设计 §14/§10-§12 同值 |
| 目标计数 | 一致 | 1929 + 56 = 1985：EXECUTION 头部/§7 ↔ CHECKLIST G4 ↔ 设计 §19（≈1985） |

---

## §6 缺口检查（过度设计 / 欠设计）

| 方向 | 检查 | 结论 |
|------|------|------|
| 过度设计 | 每个新公共符号有 ≥1 测试锚定（`ExponentialDecay`→T380-27/28）；无「预留未用」参数；依赖零新增（`calib` extra 为可选，核心 `dependencies` 不动） | 无 |
| 欠设计 | D1-D4 全落点（F3）；S1-S7 全落位（§23.1 注记三处）；Q1-Q3 全带入（X1/X8/X9）；E0-E7 全有验收出口 | 无 |
| 范围外遗留 | Q2 规则文本、Q4 起的研究性结论（c 数值本身）、α 衰减与 CPCV 联动 | 均标注为报告层/后续，不阻塞本批 |
| 禁止事项可检验性 | 不改 `backtest/__init__.py`（空 diff）/ 不回写默认 c（`:60` 唯一赋值点）/ 默认路径逐位一致（T380-51/52）/ Shell→scripts 禁边（T380-41 注入机制）——四条均可用 `git diff` 或测试断言验证 | 可检验 |

---

## §7 审查通过的不变量（步骤 9 不得破坏）

| # | 不变量 | 验证方式 |
|---|--------|---------|
| 1 | 无参数默认路径输出与 v3.7.0 逐位一致 | T380-51/52 + CHECKLIST §4#1 双跑比对 |
| 2 | `backtest/__init__.py` 空 diff（13 处 from-import 不动） | `git diff` |
| 3 | `SQRT_C` / `LINEAR_K` / `CAP_LEVELS` 三元组逐位不变（`:60-62`） | `git diff` + CHECKLIST §4#12 |
| 4 | 校准不回写默认 c；`SQRT_C` 赋值点全仓唯一 | CHECKLIST §4#13（D2） |
| 5 | `c_stress == max(0.5, c_ci_upper)` 等值语义 | T380-50 |
| 6 | 每行输出携带 `evidence_level`；L1/L2 禁称「已校准」 | §7.3 + CHECKLIST §1 规则 6（S5） |
| 7 | Core AST 禁表（含 pandas）+ `__all__ ≤ 5` | T380-53/55（S6） |
| 8 | `backtest/execution/**` 无 `import scripts`；容量函数经 `capacity_fn` 注入 | T380-41（design §3.1 禁边） |
| 9 | 4 模型 CV-RMSE 全报告；只报 sqrt 视为无效输出 | 设计 §5.2 / §11.2 |
| 10 | `log` 模型越界判 `invalid` 排除，不静默 clip | T380-06 |
| 11 | `rho` CI 覆盖 1 → `retention ≡ 1`、`half_life = inf` | T380-27/29 |
| 12 | `p > 5%` 的容量结论标 `[外推]` 不进主值 | 设计 §5.2 硬约束 |
| 13 | IJR 自动窗长仅诊断输出，不参与主值 | T380-45~47（D3） |
| 14 | Python 3.9 语法（无 PEP 604 联合类型、无内置泛型下标） | CHECKLIST §4#5 AST 扫描 |
| 15 | 无 pyarrow 环境可 `import backtest.execution.core.impact` 且 `has_pyarrow()` 为 False | T380-56（Q1 判定） |

---

## §8 对步骤 9 的约束（本审查的衍生命令）

1. 56 项测试逐项登记红→绿双读数（红形态见 EXECUTION §5.1 / CHECKLIST §3）；红读数缺失不得标绿；`ExponentialDecay` 端口断言随 T380-27/28 登记，不另立编号。
2. E0→E1→E2 顺序不可跳；E3/E4/E5 并行时各自独立红→绿；E7 在 E1-E6 全绿后接入（CHECKLIST §2 阶段纪律）。
3. 性能实测超预算只披露并降证据等级（minutes→ohlc），不得改统计口径换速度（EXECUTION §6）。
4. 默认路径快照（T380-51/52）任何漂移即为 CRITICAL，禁止用容差放过（数值容差 0）。
5. 版本锚点 6 处（EXECUTION §3.1）在 E7 一次性机械同步，禁止只改 CHANGELOG。
6. 步骤 9 完成后回填：EXECUTION §0.2 状态列 / §5.2 红→绿 / §6 性能实测；CHECKLIST 全表状态 + §3.10 回填位 + §8 重算汇总；设计 §20 Q1-Q3 结论回写；本文件不改（历史审查记录）。

---

## §9 汇总

| 分项 | 项数 | 一致 | 偏差（已修/已注记） | 缺口 |
|------|------|------|--------------------|------|
| 一致性矩阵 | 12 | 7 | 5（F1/F2/F3 已修；F6/F7/F8 接受注记归并至矩阵行 3/8） | 0 |
| 偏差处置 | 10 | — | 10（7 已修 + 3 已注记） | 0 |
| 风险映射 | 10 | 10 | — | 0 |
| 不变量 | 15 | 15 | — | 0 |

> 计数由逐行状态得出（RULE-2）；「偏差（接受）」不计为通过项，但在 §1/§3 单独披露。
> **审查结论：PASS（修正后）** —— F1-F10 全部闭环，EXECUTION v1.1 可进入步骤 9 TDD 实施。

---

## §10 工件链终态（本步结束时）

| 工件 | 版本 | 状态 |
|------|------|------|
| [调研 RESEARCH](../research/RESEARCH_V3.8.0_EXECUTION_CAPACITY.md) | v1.0 | 三轮 + §19 复审闭环；§12.2 乘积型公式已修（R-D1/R-D4） |
| [设计 DESIGN](../private/DESIGN_EXECUTION_CAPACITY_V3.8.0.md) | v1.2 | §22 review #1（2P1/2P2/5P3）+ §7.1/§16.2 对齐 + §23 本步附记 |
| [实施 EXECUTION](../EXECUTION_V3.8.0_EXECUTION_CAPACITY.md) | v1.1 | §9 review #2（3P2/7P3）+ 本步 §0.4/§0.1/§1/§3.1 修订 |
| [清单 CHECKLIST](CHECKLIST_V3.8.0_EXECUTION_CAPACITY.md) | v1.0 | 114 行待验证；本步修 T380-15 公式、E4/E7 DoD |
| 代码 | — | 未开始（步骤 9 TDD，基线 1929 passed） |
