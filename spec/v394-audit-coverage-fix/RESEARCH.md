# v3.9.4 调研 — 审计遗留修复 + 覆盖度口径收口（批次 A）

---
id: v394-audit-coverage-fix-RESEARCH
type: design
version: 1.1
status: verified
date: 2026-11-20
depends: [v393-alpha-decay-model-AUDIT, v393-alpha-decay-model-DESIGN, v393-alpha-decay-model-IMPLEMENTATION]
upstream: null
---

> **Feature**: 批次 A「口径收口包」——P-012（F-1~F-6 审计遗留）+ P-004（覆盖度交集口径）+ P-005（强制放行留痕）+ P-013（E3 锚点重绑）
> **创建日期**: 2026-11-20
> **状态**: verified（Step 2 复审 PASS，见 §8；B-2 标 [单源-待二核]，Step 9 二核）
> **Spec 步骤**: Step 1-2
> **包版本**: 3.9.4（patch 级，与 v3.9.2 口径修复批同级）
> **档位**: 预计 T1（最终以本批 DESIGN 登记为准，PROGRESS 不单列）
> **执行约束（上游既定）**: Python 3.9 语法；零新增依赖；默认路径 `out/capacity_impact.json` SHA 必须保持 `82728CE103D49AF211DD12DE87D9784040FC909C83FB7A88D521AF30A89B2548`；`core/decay.py` 的 `__all__` 保持 5 项

---

## 1. 调研目标

本批不引入新方法，核心是**把已登记的 6 项审计缺陷与 2 项口径缺口收敛为可实施的最小修复式**。需回答：

1. **Q1**：F-1 回退分支的 `net` 区间正确闭式是什么？与现有 `point`、`m` 三值如何保持同一代数路径？F-6 退化态敏感性口径如何统一？
2. **Q2**：覆盖度 `universe_ratio` 的正确定义是什么（改分子 / 改分母 / 双口径）？改口径后**门禁阈值 0.95 / 0.90 是否仍成立**？对 `panel_hash` 与缓存代际有无影响？
3. **Q3**：`--force-coverage` 的留痕文案形态（自由文本 vs token 化）与写入落点（哪一层 `evidence_warnings`），怎样既进校准工件又不污染默认路径？

F-2（判据算术）、F-3（枚举同步）、F-4（`DecayCurve` 处置）、F-5（D5 plateau 落点）为**文档/裁决类**，随本调研一并取证，供 Step 3 决策。

---

## 2. 调研方法

### 2.1 使用的工具与降级声明

| 工具 | 用途 | 查询/范围 |
|------|------|----------|
| 仓内代码检索（Grep / Read / Glob） | 定位缺陷锚点、数据流、调用方 | `runner.py` / `panels.py` / `decay.py` / `verify_capacity_impact.py` / `loaders.py` / `effect_size.py` |
| 既有工件（E1） | 读数与键域核对 | `out/v393_decay_curve.json|md`、`out/v393_calibration.json`、默认 `out/capacity_impact.json` |
| 上游 spec（E1/E3） | 判据与枚举基线 | v3.9.3 DESIGN / IMPLEMENTATION / CHECKLIST / AUDIT；v3.8.1 审计观察 A-7 |
| 外部文献检索 | **降级未调用** | 见 §3.6 说明 |

**降级理由（诚实声明）**：本批 6 项修复中 5 项为**实现与自身设计文档的不一致**（F-1~F-6），1 项为**统计口径定义问题**（P-004），均属仓内可判定的口径一致性，无外部方法选择需求。按 SPEC_PROCESS「来源三层阶梯」的第二层（仓内事实 + 既有 verified 调研）即可闭合；**不虚构文献**。P-004 中「投资域定义」的理论背景已在 v3.8.1 调研中引用过，本批不重复。

### 2.2 调研范围

- **代码**：v3.9.3 白名单 5 文件 + 其直接依赖（`effect_size.py`、`loaders.py`）；
- **工件**：默认路径快照、v3.9.2/v3.9.3 校准工件；
- **文档**：v3.9.3 四件套 + AUDIT；v3.8.1 审计观察；
- **排除**：P-003（截面 T+1 reversal 真实现）、P-010（粒度重采样）——均为结论级口径变更，属后续批次；P-014（引文元数据）单列。

---

## 3. 调研发现

### 3.0 发现总表

| 编号 | 发现 | 证据等级 | 位置 |
|------|------|---------|------|
| F-1 | 回退分支 net lo/hi 与 point 不同代数路径（缺 `h_m/h` 因子） | E3 + E2 推导 | [runner.py L306](file:///f:/Coding/factor_pipeline/backtest/execution/shell/runner.py#L306)、[L314-321](file:///f:/Coding/factor_pipeline/backtest/execution/shell/runner.py#L314-L321) |
| F-1′ | 回退分支**可直接触发**：`n_bootstrap < 100` 抛 `ValueError`，无需 monkeypatch | E3 | [effect_size.py L138-139](file:///f:/Coding/factor_pipeline/backtest/effect_size.py#L138-L139) |
| F-2 | 通过线 2065 为 collected 数，passed 上限 2057 | E1 恒等式 | [IMPLEMENTATION.md L460](file:///f:/Coding/factor_pipeline/spec/v393-alpha-decay-model/IMPLEMENTATION.md#L460) |
| F-3 | `phi_status` 实现含 `prior`，DESIGN 枚举缺 | E3 双读 | [DESIGN.md L222](file:///f:/Coding/factor_pipeline/spec/v393-alpha-decay-model/DESIGN.md#L222)、[L278](file:///f:/Coding/factor_pipeline/spec/v393-alpha-decay-model/DESIGN.md#L278)、[runner.py L332-350](file:///f:/Coding/factor_pipeline/backtest/execution/shell/runner.py#L332-L350)（prior 分支 L338-342） |
| F-4 | `DecayCurve` 全仓零调用方（仅定义 + 测试符号表） | E3 全仓检索 | [decay.py L258](file:///f:/Coding/factor_pipeline/backtest/execution/core/decay.py#L258)、[test_execution_decay.py L11](file:///f:/Coding/factor_pipeline/tests/test_execution_decay.py#L11) |
| F-5 | D5「plateau 用 net 的 bootstrap 标准差」无落点；默认 `plateau` 仍走 rho | E3 双读 | [DESIGN.md L120](file:///f:/Coding/factor_pipeline/spec/v393-alpha-decay-model/DESIGN.md#L120)、[decay.py L92-98](file:///f:/Coding/factor_pipeline/backtest/execution/core/decay.py#L92-L98) |
| F-6 | 退化态仍执行 `_boot` 敏感性循环 | E3 | [runner.py L354-365](file:///f:/Coding/factor_pipeline/backtest/execution/shell/runner.py#L354-L365) |
| P-004 | 覆盖度分子/分母来自不同筛选；**`panel_hash` 不含计数 → 修复不改哈希** | E3 读码 | [panels.py L382-386](file:///f:/Coding/factor_pipeline/backtest/execution/shell/panels.py#L382-L386)、[L403-419](file:///f:/Coding/factor_pipeline/backtest/execution/shell/panels.py#L403-L419) |
| P-005 | 强制放行仅 stdout，不入 `evidence_warnings`；但合并通道已存在 | E3 | [verify_capacity_impact.py L610-616](file:///f:/Coding/factor_pipeline/scripts/verify_capacity_impact.py#L610-L616)、[L301-306](file:///f:/Coding/factor_pipeline/scripts/verify_capacity_impact.py#L301-L306) |
| P-013 | E3 锚点可零成本绑定 `a0cf914` | E1 | 本批提交记录 |

### 3.1 F-1：回退区间闭式（代数推导）

现实现三条口径：

- `point`：`net_point(a_mean[h_m], aum, m_point, cost)` → 展开 = `aum·A(h)·(h_m/h) − cost(h)`（[L306](file:///f:/Coding/factor_pipeline/backtest/execution/shell/runner.py#L306)）；
- `m` 区间：`m_se = se_a / scale`，`scale = A(h_m)·h/h_m`（[L314-315](file:///f:/Coding/factor_pipeline/backtest/execution/shell/runner.py#L314-L315)）——**正确**；
- `net` 区间：`aum·(a_mean[h] ± t·se_a) − cost(h)`（[L318-321](file:///f:/Coding/factor_pipeline/backtest/execution/shell/runner.py#L318-L321)）——**缺 `h_m/h`**。

**正确闭式（推导）**：

```
net(h) = aum·A(h_m)·m(h) − cost(h)，  m(h) = A(h)/(A(h_m)·h/h_m)
       = aum·A(h)·(h_m/h) − cost(h)

∂net/∂A(h) = aum·h_m/h
⟹ net_lo/hi = aum·(A(h) ± t·se_a)·(h_m/h) − cost(h)
```

等价写法（复用 `m_se`，推荐）：

```
net_lo/hi = aum·A(h_m)·(m(h) ∓ t·m_se(h)) − cost(h)
          = aum·A(h_m)·m(h) ∓ aum·A(h_m)·t·m_se(h) − cost(h)
其中 aum·A(h_m)·t·m_se = aum·t·se_a·(h_m/h)
```

两种写法代数恒等（`A(h_m)·m_se = se_a·h_m/h`）。**推荐用 m 形式**：与 §3.1 已正确缩放的 `m` 三值共享同一 `scale` 与 `m_se`，消除第二条代数路径——F-1 的根因正是回退分支自建了第二条路径。

**可测性**：`_boot` 抛错条件在 `stationary_bootstrap_indices`（`n_bootstrap` 必须 ≥100，[effect_size.py L138-139](file:///f:/Coding/factor_pipeline/backtest/effect_size.py#L138-L139)）；`assemble_decay_curve(panels, n_bootstrap=50)` 即可稳定进入回退分支，**无需 monkeypatch**（审计原判「monkeypatch」为本调研的改进结论）。副作用：敏感性循环同样抛错 → `m_sensitivity={}`（现有 `except` 已处理）。

### 3.2 F-2 ~ F-6 事实

| 编号 | 事实 | 处置方向（供 Step 3） |
|------|------|---------------------|
| F-2 | 2065 = collected 节点；7 个模块级 skip 文件运行期各产 1 个 skipped → 2072 = 2057+15。通过线应为 **≥2057 passed** | 修订 [IMPLEMENTATION.md L460](file:///f:/Coding/factor_pipeline/spec/v393-alpha-decay-model/IMPLEMENTATION.md#L460)，补恒等式注记 |
| F-3 | `decay_source` 枚举在 DESIGN 已有（`empirical \| prior`，L223），仅 `phi_status` 缺 `prior`；§7 错误表 L289 只提 `decay_source` | 同步 L222/L278 枚举 + §7 行补 `phi_status=\"prior\"` |
| F-4 | `DecayCurve` 定义于 decay.py，`assemble_decay_curve` 直接返回 dict；DESIGN §3.2（L153）与 §6（L270）称 runner「装配 DecayCurve」 | 三选项见 §6.1 |
| F-5 | D5（L120）要求 plateau 用 net 的 bootstrap sd；payload 无 `sd`/`plateau` 键；`plateau()` 仅服务默认 rho 路径 | 两选项见 §6.1 |
| F-6 | 退化态（`A(h_m)<=0` 或 NaN）主 CI 置 NaN、verdict=`unidentified`，但敏感性循环仍跑 `_boot` | 加 `if not degenerate` 守卫，与主口径一致 |

### 3.3 P-004：覆盖度口径根因链

```
分子：counts[ym] = |unique(agg.stock_code)|        （分钟层实际有数据的股票，int 化）
分母：_universe_count(ym) = |P['mask'] & ret.notna()|（日频可投资域）
ratio = 分子 / 分母                                 （两集合无交集约束 → 可 >1）
```

- 观测：v3.8.1 覆盖度中位 **1.097**、最差 **1.050**（全部 >1，读数源：[PROJECT_STATUS.md](../../docs/PROJECT_STATUS.md) v3.8.1 状态块，E1-文档）→ 分子里存在不在日频域内的代码；
- 门禁：`IMPL_MIN=0.95` / `MONTH_MIN=0.90`（[panels.py L34-35](file:///f:/Coding/factor_pipeline/backtest/execution/shell/panels.py#L34-L35)）以该 ratio 判定（[L649-671](file:///f:/Coding/factor_pipeline/backtest/execution/shell/panels.py#L649-L671)），另含第三条件「深主板>0」（[L668-670](file:///f:/Coding/factor_pipeline/backtest/execution/shell/panels.py#L668-L670)）——不属本批阈值定标范围（复审 R-4）。
- `stock_median` 同源（复审 R-1）：`PanelCoverage.stock_median`（[L391/L397](file:///f:/Coding/factor_pipeline/backtest/execution/shell/panels.py#L391-L397)）同样消费 `counts.values()` → 修复必须**只在 ratio 层交集**、counts 保持原值，否则该读数连带漂移。

**关键发现（修正上一轮复审的过度推断）**：`_panel_hash` 的 payload（[L403-419](file:///f:/Coding/factor_pipeline/backtest/execution/shell/panels.py#L403-L419)）只含 `adv_window_days / code_range / granularity / lambda_min_days / minute_window / months / n_lambda / n_samples / sigma_clip / windows`，**不含 counts 或 ratio**；λ 面板与 impact 样本亦不按日频域过滤（[L461-503](file:///f:/Coding/factor_pipeline/backtest/execution/shell/panels.py#L461-L503)）。因此：

1. **交集口径修复不改 `panel_hash`，不使缓存失效，不改任何校准读数**（`c` / `rho` / `alpha0` / `cost_by_h` 均不依赖 ratio）；
2. 变更面仅限**覆盖度报告值与门禁判定**；
3. P-004 原验收标准②「`panel_hash` 变更说明与缓存代际登记」**前提不成立**，应改为「确认 `panel_hash` 不变并留证据」。

**同源风险**：ratio 由 >1 降到 ≤1 后，读数整体下移，(0.95, 0.90) 阈值可能首次触发失败 → 校准路径 `return 2`。这不是缺陷而是**阈值是否仍与真实覆盖率匹配**的定标问题，须实测定标（见 U-1）。

**代码归一化约束**：分钟 `stock_code` 为整数（000001→1，[loaders.py L7/L23](file:///f:/Coding/factor_pipeline/backtest/execution/shell/loaders.py#L7-L23)）；日频域列键须按 `_adv_lookup` 同款 `int(str(key))` 归一（[L219-223](file:///f:/Coding/factor_pipeline/backtest/execution/shell/panels.py#L219-L223)），不可直接对列名做 `int()`。

### 3.4 P-005：警告落点链路

```
coverage_gate(...) → ok, messages
  ├─ 失败且未 force → return 2
  └─ force → print('[coverage] --force-coverage：门禁失败放行（留痕）')   # 仅 stdout
minute['evidence_warnings'] → assemble_panels 合并 → attach_panel_meta（L301-306，去重保序）→ result['evidence_warnings']
```

结论：**落点已存在**，只需在 gate 放行处把 token 化文案追加进 `minute['evidence_warnings']`；无需改 `attach_panel_meta`、无需触碰默认路径。文案建议固定前缀 `coverage_gate_forced`（与 `decay_*` token 风格一致，便于 grep 与断言），后接现有中文 message（`; ` 连接）。

### 3.5 P-013：E3 锚点重绑

v3.9.3 AUDIT §7 与 CHECKLIST §12 的「工作区未提交，以文件+行号登记」已因 `a0cf914`（98 文件，含 `backtest/execution/` 全部）提交而满足触发条件。行号自审计以来未变（本批调研仍需改动，故应**先重绑、后改码**，否则新行号会让旧锚点再次漂移；建议在 Step 9 改码前落盘）。

### 3.6 外部文献

本批无新增外部文献（降级理由见 §2.1）。所有结论以仓内代码（E3）与既有工件（E1）为依据；P-004 涉及的投资域定义沿用 v3.8.1 调研已引文献，不重复引用、不新增未核验题录。

---

## 4. 综合分析

### 4.1 关键发现总结

1. F-1 与 F-6 同源：回退/敏感性分支自建了与主路径不同的代数或状态判定，修复应**复用 `scale`/`m_se` 与 `degenerate`**，而不是再补一条平行公式。[置信度 ★★★★★，E3+E2]
2. P-004 修复是**纯报告口径变更**：不改 `panel_hash`、不改缓存、不改校准读数——变更面比上一轮复审预估小得多。[★★★★★，E3 读码]
3. 但 P-004 会**下移 ratio 并可能触发门禁失败**，阈值需实测定标。[★★★★☆，E3 推理，待 E1]
4. F-1 缺陷可在**无 monkeypatch** 条件下稳定复现（`n_bootstrap=50`），修复具备可执行单测。[★★★★★，E3]
5. F-2/F-3 属文档同步（低风险）；F-4/F-5 是**设计-实现范围错位**，需在 Step 3 明确裁决而非默认补齐。[★★★★☆，E3]

### 4.2 技术 landscape（P-004 三方案）

| 方案 | 定义 | 优点 | 代价/风险 |
|------|------|------|----------|
| A 只改分子（交集） | `|M∩U| / |U|` | 语义正确、保证 ≤1、无缓存影响 | 读数整体下移，阈值可能失效 |
| B 改分母（并集） | `|M∪U|` 或 `|M|` | 读数不下移 | 语义不成立（覆盖率可任意）；否决 |
| C 双口径报告 | 同时输出 `ratio_raw` 与 `ratio_intersect`，门禁用交集 | 变更可追溯、便于定标 | payload 增键；md/报告需同步 |

倾向 **A + 保留 `ratio_raw` 作为披露键**（等价于 C 的轻量形态，但门禁只用交集值）。

### 4.3 研究空白（必须实测）

- 39 月交集 ratio 的真实分布（中位/最差）→ 决定阈值是否调整（U-1）；
- 门禁失败是否会在默认校准命令下真实发生（需一次 39 月重跑，缓存命中时开销低）。

---

## 5. 幻觉抑制审查（Step 2 Review 前置自审）

### 5.1 文献验证

| 引用 | 状态 |
|------|------|
| （无新增外部文献） | — 本批未引入题录，无需核验 |

### 5.2 技术声明验证

| 声明 | 来源 | 状态 |
|------|------|------|
| 回退分支 lo/hi 缺 `h_m/h` | runner.py L306 vs L318-321 逐行对照 | ✅ 已验证 |
| `n_bootstrap<100` 抛错 → 回退可达 | effect_size.py L138-139 | ✅ 已验证 |
| `panel_hash` 不含 counts/ratio | panels.py L403-419 键域逐项 | ✅ 已验证 |
| ratio 分子为分钟 uniq 码数 | panels.py L467-469 | ✅ 已验证 |
| 域列键可 `int(str(key))` 归一 | panels.py L219-223 + loaders.py L7/L23 | ✅ 已验证（列格式未逐一采样，见 U-5） |
| 强制放行不入 evidence_warnings | script L610-616 | ✅ 已验证 |
| `--force-coverage` help 已承诺「留痕 warning」 | script L558-559 | ✅ 已验证（CLI 契约与实现不符，佐证 P-005，复审 R-3） |
| 合并通道已存在（去重保序） | script L301-306 | ✅ 已验证 |
| `DecayCurve` 零调用方 | 全仓 grep 命中仅定义/文档/测试符号表 | ✅ 已验证 |
| plateau 仍走 rho | decay.py L92-98 + payload 无相关键 | ✅ 已验证 |

### 5.3 待修正项

- [x] **自我更正**：上一轮复审称「P-004 → `panel_hash` 变更、缓存全量失效、39 月重建」——经 §3.3 读码证伪，已在 §3.3 显式更正；本批不再以「缓存失效」为风险评估前提。
- [ ] U-5：日频域列键格式需在 Step 9 首次重跑时抽样确认（含 `.SZ` 后缀等）。

---

## 6. 对设计的输入

### 6.1 可用的技术方案（建议排序）

| 项 | 方案 | 说明 |
|----|------|------|
| F-1 | **m 形式复用**（推荐） | `net_lo/hi = aum·A(h_m)·(m ∓ t·m_se) − cost`；备选：A 形式乘 `h_m/h` |
| F-2 | 修订判据 + 恒等式注记 | `≥2057 passed / 15 skipped / 0 failed`；注明 collected 2065 |
| F-3 | DESIGN 枚举同步 | `phi_status: "fitted" \| "unidentified" \| "prior"`；§7 行补 |
| F-4 | ① 接线（内部构造 `DecayCurve` → payload，推荐）；② 删除符号（需改 T393-7）；③ 保留 + DESIGN 标注为外部消费类型 | 三者均需在 DESIGN 记录被拒方案与代价 |
| F-5 | ① payload 增 `net[h].sd` + `plateau`（推荐，校准路径限定）；② 修订 D5 措辞承认 plateau 属默认 rho 路径 | ① 与 D5 原文一致，改动局部 |
| F-6 | 加 `degenerate` 守卫，敏感性输出 `{}` | 与主口径统一 |
| P-004 | 交集口径（**仅 ratio 层**，counts 保持原值 → `stock_median` 不变）+ 披露 `ratio_raw` | 见 §4.2 方案 A/C；层位约束见 §3.3（复审 R-1） |
| P-005 | token 化文案 `coverage_gate_forced: …` 追加进 `minute['evidence_warnings']` | 复用既有合并通道 |
| P-013 | 先重绑锚点再改码 | 文档两处 |

### 6.2 关键约束

1. 默认路径 SHA `82728CE1…` 逐位不变（P-004/P-005 仅校准分支；F-1~F-6 仅校准 payload）；
2. `core/decay.py` 的 `__all__` 保持 5 项；
3. Python 3.9、零新增依赖；
4. **不重写 v3.9.3 verified 文档**：F-2/F-3/F-5 的文档修订采用「v394 DESIGN 记录修订 + v393 对应 3 处就地勘误并升 v1.2」的双轨，避免整篇重写（载体见 U-4）；
5. 测试基线：本批新增用例后应为 `2057 + N` passed / 15 skipped / 0 failed。

### 6.3 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| 交集后门禁失败 | 校准命令 `exit 2` | U-1 定标；必要时 `--force-coverage` 留痕（P-005 修复后可见） |
| 覆盖率读数变化 | README / PROJECT_STATUS 记录值（1.097 / 1.050）过期 | Step 9 重跑后同步文档 |
| F-4 接线引入无谓间接层 | 可读性下降 | 仅内部构造，不改 payload 形态；备选②删除 |
| 旧锚点漂移 | E3 证据失真 | P-013 先于改码执行 |

### 6.4 未决项登记（四元块）

- **U-1 交集口径下的门禁阈值定标**
  - **判据**：39 月交集 ratio 的中位/最差实测值与 (0.95, 0.90) 的关系明确，且「维持 / 调整 / 降级为提示」三选一有书面裁决
  - **触发条件**：`coverage_gate` 在交集口径下产出非空 messages（机械可识别）
  - **当前倾向**：先实测；若中位仍 ≥0.95 则维持阈值，否则按实测分布下调并在 v394 DESIGN 记录依据
  - **证据等级**：待核（需 E1 重跑）

- **U-2 F-4 `DecayCurve` 处置**
  - **判据**：三选项之一落盘，且在 v394 DESIGN 写明被拒方案与代价
  - **触发条件**：Step 3 决策时
  - **当前倾向**：① 内部接线（`assemble_decay_curve` 构造 `DecayCurve` 后组装 payload）
  - **证据等级**：E3

- **U-3 F-5 plateau 落点**
  - **判据**：D5 原文与实现一致，或 D5 被显式修订
  - **触发条件**：Step 3 决策时
  - **当前倾向**：① payload 增 `net[h].sd` 与 `plateau` 列表（仅校准工件）
  - **证据等级**：E3

- **U-4 文档修订载体**
  - **判据**：v3.9.3 DESIGN 的 3 处勘误（L222/L278 枚举、L289 §7 行、L120 D5 注）有明确落盘方式且版本记录可追溯
  - **触发条件**：Step 3 起草 DESIGN 时
  - **当前倾向**：v3.9.3 DESIGN 升 **v1.2（增量勘误节）** + v394 DESIGN 引用，不整篇重写
  - **证据等级**：E3

- **U-5 日频域列键格式抽样**
  - **判据**：首次重跑时抽样确认列键可经 `int(str(key))` 归一（无 `.SZ` 等后缀）
  - **触发条件**：Step 9 首次校准重跑
  - **当前倾向**：按 `_adv_lookup` 同款归一，不可归一则跳过并计入 `unplanned` 计数留痕
  - **证据等级**：待核

### 6.5 阻断性断言（B 类，Step 9 必须验证）

- **B-1** 默认 `out/capacity_impact.json` SHA `82728CE1…` 逐位不变；
- **B-2** `panel_hash` 在 P-004 修复前后**逐位相同**（研究结论，需实测确认 §3.3）；
- **B-3** 修复后回退分支 `point ∈ [lo, hi]` 对 h∈{5,10,20} 恒成立（`n_bootstrap=50` 用例）；
- **B-4** 交集口径 `universe_ratio ≤ 1` 在 39 月恒成立；`ratio_raw` 保留原值；
- **B-5** `core/decay.py` `__all__` 仍 5 项；全量 passed = 2057 + 新增数，0 failed。

---

## 7. 参考文献（仓内）

1. [v3.9.3 AUDIT.md](file:///f:/Coding/factor_pipeline/spec/v393-alpha-decay-model/AUDIT.md)（F-1~F-6 原始发现，取证矩阵 §7）
2. [v3.9.3 DESIGN.md](file:///f:/Coding/factor_pipeline/spec/v393-alpha-decay-model/DESIGN.md)（D5 / §4.4 schema / §7 错误处理表）
3. [v3.9.3 IMPLEMENTATION.md](file:///f:/Coding/factor_pipeline/spec/v393-alpha-decay-model/IMPLEMENTATION.md)（§5 通过线 / §9 实测读数）
4. [v3.9.3 CHECKLIST.md](file:///f:/Coding/factor_pipeline/spec/v393-alpha-decay-model/CHECKLIST.md)（§12 遗留）
5. v3.8.1 审计报告（覆盖度观察 A-7）：`docs/audit/2026-11-20-v3.8.1-minute-panel-wiring-audit.md`
6. 代码锚点：`backtest/execution/shell/runner.py`、`shell/panels.py`、`core/decay.py`、`scripts/verify_capacity_impact.py`、`backtest/effect_size.py`、`shell/loaders.py`

---

## 8. 步骤 2 复审记录

> **审查方式**：全文重读（独立 pass）+ 全部 E3 锚点逐条重放代码 + 门禁 a-d 判定 + 契约 F1-F5 出具检查。
> **独立性声明（RULE-4）**：**自查（单视角）**——审查者与撰写者同 agent 同基座，无对抗制衡；按 T1 批惯例，Step 8 一致性复审将由独立上下文执行（v3.9.3 RESEARCH §11 先例），本节结论以该次异构复审为最终把关。
> **E3 锚点基线**：代码文件自 `a0cf914` 后未变更（工作区当前仅 spec/docs 变更），锚点按 `L<行号>@a0cf914` 绑定。

### 8.1 复核结果（声明 ↔ 代码锚点逐条重放）

| # | RESEARCH 声明 | 重放锚点（@a0cf914） | 结果 |
|---|---|---|---|
| 1 | 回退分支 net lo/hi 缺 `h_m/h` | runner.py L318-321：`aum*(a_mean[h] ± t_crit*se_a) − cost`；对照 L322-326 m 三值已经 `m_se` 正确缩放 | ✅ 缺陷坐实 |
| 2 | point 与 m 的代数路径 | runner.py L306（`net_point`）+ L314-315（`scale`/`m_se`） | ✅ |
| 3 | 回退可达（`n_bootstrap<100` 抛错） | effect_size.py L138-139 | ✅ |
| 4 | F-2 判据 2065 | IMPLEMENTATION.md L458-462 | ✅ |
| 5 | F-3 枚举缺 `prior` | DESIGN L222 / L278 / §7 L289；runner.py L332-350（prior 分支 L338-342） | ✅（锚点精化为 L332-350） |
| 6 | F-4 `DecayCurve` 零调用方 | 全仓 grep：定义 decay.py L257-268 + 测试 NEW_SYMBOLS L11 + 文档；零运行时调用 | ✅ |
| 7 | F-5 plateau 无落点 | DESIGN L120（D5）+ decay.py L92-98（独立函数，默认 rho 路径）+ payload 无 `sd`/`plateau` 键 | ✅ |
| 8 | F-6 敏感性无守卫 | runner.py L354-357：循环无条件执行 `_boot` | ✅ |
| 9 | ratio 分子/分母异源 | panels.py L467-469（`counts=np.unique(agg.stock_code)`）+ L232-239（`_universe_count` 日频域）+ L383-386（ratio 装配） | ✅ |
| 10 | `panel_hash` 不含 counts/ratio | panels.py L403-419 payload 键域逐项 | ✅ |
| 11 | 域列键 `int(str(key))` 归一 | panels.py L219-223（`_adv_lookup` 同款）+ loaders.py L7/L23 | ✅ |
| 12 | 强制放行仅 stdout；合并通道已存在 | script L610-616 + L301-306（去重保序） | ✅ |
| 13 | P-013 commit 锚点 | `git log --oneline -1 a0cf914`（E1） | ✅ |

### 8.2 复审发现（4 项，均已回写正文 → v1.1）

| # | 级别 | 发现 | 处置 |
|---|---|---|---|
| R-1 | P3（设计输入精化） | `PanelCoverage.stock_median`（panels.py L391/L397）同样消费 `counts.values()`——若 P-004 在 **counts 层**做交集，`stock_median` 连带变化；修复必须**只在 ratio 层交集**、counts 保持原值 | §3.3 补 bullet + §6.1 P-004 行补层位约束 |
| R-2 | P3（锚点精化） | F-3 的 `phi_status` 赋值全集为 runner.py L332-350（prior 分支 L338-342），原锚点偏窄 | §3.0 锚点精化 |
| R-3 | P3（佐证） | `--force-coverage` 的 argparse help（script L558-559）已承诺「留痕 warning」——CLI 契约与实现不符，P-005 修复同时是对既有 help 声明的兑现 | §5.2 补行 |
| R-4 | P3（完备性） | `coverage_gate` 第三条件「深主板>0」（panels.py L668-670）原稿未列；U-1 阈值定标仅涉 ratio 两条件，不涉该条 | §3.3 门禁 bullet 补注 |

### 8.3 契约取证字段（F1-F5）出具状态

| 字段 | 状态 | 说明 |
|---|---|---|
| F1 来源日期 | N/A + 理由 | 全部来源为仓内文件（以 F2 版本+行号替代）；无外部来源 |
| F2 来源版本 | 出具 | spec 文档标版本 + 行号；代码标行号 @a0cf914；commit E1 |
| F3 降级链 | 出具（无降级） | 外部检索未调用的理由见 §2.1；无通道失败 |
| F4 引用验证表 | N/A + 理由 | 外部引用 0 条（<3 无需建表；亦无可解析标识符） |
| F5 先失败记录 | N/A + 理由 | Step 9 触发（届时红→绿双读数留痕） |

### 8.4 Step 2 Review 清单 + 门禁 a-d

**清单**：
- [x] 所有 arXiv 编号已验证 — **N/A**（无外部引用，无编号可验）
- [x] 所有作者、年份、标题已验证 — **N/A**（同上）
- [x] 所有技术声明有文献支撑 — 改判为「有 T1 代码/工件支撑」：13 条声明全部绑定代码锚点或 E1 工件（§8.1）
- [x] 无未标注的推测 — 推断处（门禁触发可能性）均标「待 E1」并落 U-1 四元块
- [x] 置信度标注完整 — §4.1 五条均有 ★ 级

**门禁**：
- [x] **(a)** FALSIFIED 断言已改写并记入修订记录 — §5.3（`panel_hash` 前提证伪）+ PROGRESS P-004 验收②同步改写
- [x] **(b)** CONFLICT / STEP_GAP_OPEN 已仲裁 — 无 OPEN 项；F-3/F-5 属已登记的设计-实现落差，经 U-2/U-3/U-4 四元块显式携带进 Step 3
- [x] **(c)** 阻断性断言双源满足 — B-1（SHA）：v3.9.3 三次 E1 + Step 9 复验；B-2（`panel_hash` 不变）：**[单源-待二核]** 当前仅 E3 静态读码，第二源 = Step 9 修复前后 hash 对比（E1）；B-3/B-4 同理于 Step 9 出双源；B-5 双源（架构测试 + 计数）
- [x] **(d)** 假设区条目已显式携带 — U-1~U-5 四元块齐备，判据/触发条件均机械可识别

### 8.5 结论

**PASS** —— RESEARCH 升级 v1.1 verified；门禁 a-d 全过。唯一保留项：B-2 标注 [单源-待二核]（二核动作已排定于 Step 9，不阻断 Step 3）。可进入 Step 3（DESIGN）。
