# CONSISTENCY REVIEW V3.3.6 — PL-05 Dynamic AR 因果性修复

**版本**: v1.2 (步骤 9 回注 Red 实测计数; v1.1 含用户指令触发的二次复核, §6 F22-F26 为第二轮独立核验新增)
**日期**: 2026-11-04
**review 时机**: spec 步骤 8 (checklist 完成后, TDD 实现前)
**review 对象**:
- 调研: [PL05_DYNAMIC_AR_LOOKAHEAD_RESEARCH.md](../analysis/PL05_DYNAMIC_AR_LOOKAHEAD_RESEARCH.md) v1.4
- 设计: [PL05_DYNAMIC_AR_LOOKAHEAD_DESIGN.md](../analysis/PL05_DYNAMIC_AR_LOOKAHEAD_DESIGN.md) v1.2
- 实施: [EXECUTION_V3.3.6_PL05_DYNAMIC_AR_CAUSALITY.md](../EXECUTION_V3.3.6_PL05_DYNAMIC_AR_CAUSALITY.md) v1.2
- 验收: [CHECKLIST_V3.3.6_PL05_DYNAMIC_AR_CAUSALITY.md](CHECKLIST_V3.3.6_PL05_DYNAMIC_AR_CAUSALITY.md) v1.1
- 决策: ADR-040 模板 (实施文档 §5.3) + `DECISIONS.md` 占用表
**结论**: **通过** — 无 CRITICAL; 3 项 MAJOR + 17 项 MINOR + 6 项 INFO (共 26 项) 已修复; 可进入步骤 9 (TDD)。

---

## §0 范围与方法

按 WORKFLOW_METHODOLOGY v1.3 §13.3 工件 C, 检查五类一致性:

1. 引用一致性: 学术/工业引用的结论与证据等级。
2. 接口签名一致性: 设计声明 ↔ 实施声明 ↔ 源代码。
3. 验收标准一致性: 实施 §4/§7 ↔ checklist Gate。
4. 决策记录对齐: D1-D10 ↔ ADR-040 ↔ 占用表。
5. 数值一致性: 同一实测值在各文档中的表述。

方法: 逐项读取四份文档原文 + 对照源代码/测试/`DECISIONS.md`/实际 grep 与 pytest, 不做记忆推断。

### 0.1 本次实测证据 (2026-11-04)

| 项 | 命令 / 方法 | 结果 |
|----|------------|------|
| 工作树 | `git status --short` | 4 份 PL-05 文档未跟踪 (review 创建前; 现 5 份); 生产代码无改动 |
| 缓存字面量 | `git grep -n "v2.2.3-cache" -- '*.py'` | **7 行**: `backtest/cache_manager.py` L58 + `test_fix3` L14/79/84/93/94/109 |
| `fitted_values.reindex` | `git grep -n "fitted_values\.reindex" -- '*.py'` | **2 行**: `ar_model.py` L325 + 集成测试 L317 (PL-05 xfail reason) |
| 版本套件 | `pytest tests/test_fix3_version_unification.py -q` | 7 passed (0.16s), 当前锚点 v3.3.5 |
| 手工校验 | `python tests/test_backtest/verify_fix3_manual.py` | 5/5, 缓存 `v2.2.3-cache` 独立于项目版本 |
| `ARDecoupler` 调用点 | `grep -n "ARDecoupler("` | 5 处 (生产 `dual_neutralizer.py` L413 + 测试 4 处), 全部关键字传参 |
| `ARModelResult` 字段 | 读 `ar_model.py` L32-L44 | **10 个**字段 |
| 行号 | 读 `ar_model.py` | `AROrderSelector.fit` L80-L129; `_fit_ar` L131-L176; `ARDecoupler.__init__` L235-L254; `fit` L256-L272; `transform` L298-L331 |
| ADR 占用 | 读 `DECISIONS.md` L42-L43 | ADR-039 已占用; **ADR-040 起 未占用** |
| 单元测试文件数 | `tests/unit/*.py` | 25 个 (新文件路径有效) |

---

## §1 引用一致性

| 引用 | 调研 | 设计 | 实施 / ADR-040 | checklist | 状态 |
|------|------|------|----------------|-----------|------|
| FPP3 §5.10 (warm-up / 先验观测) | §4 A / §10.1 E1 / §11 | §0 / §10 要点 6 | ADR 学术依据 | — | ✅ 一致 (A) |
| tsibble `stretch_tsibble(.init, .step)` | §10.1 E2 | §0 / §10 | ADR 学术依据 | — | ✅ 一致 (A) |
| sktime `ExpandingWindowSplitter` | §10.1 E3 / §11 I8 | §0 / §10 | ADR 学术依据 | — | ✅ 一致 (B, 调研已标注文档摘要) |
| skforecast `refit=n` / 成本表 | §10.1 E4-E5 | §0 / §3.5 / R2 | ADR 备选 / 学术依据 | — | ✅ 一致 (A) |
| statsmodels `AutoReg.predict(dynamic=False)` / `apply(refit=False)` | §11 I1-I2 | §0 / §10 | ADR 学术依据 | — | ✅ 一致 (A) |
| Marriott & Pope (1954) / Kendall (1954) | §10.2 / §8 #6-7 | §4.2 / R6 | §4.4 容差注释 | G4-4 | ✅ 一致 (A) |
| Varma & Simon (2006) | §10.3 E8 / §8 #8 | §4.2 / R7 | ADR 学术依据 | G3-5 | ✅ 一致 (A) |
| Cawley & Talbot (2010) / Bergmeir & Benítez (2012) | §10.3 E9-E10 / §8 #9-10 | §4.2 | ADR 学术依据 | — | ✅ 一致 (A 摘要) |
| Bayğın et al. (2026) / Yates et al. (2022) | §10.3 E13-E14 / §8 #23-24 | §4.2 | — | — | ✅ 一致 (A 摘要 / B) |
| ADR-027 / ADR-030 / ADR-037 / ADR-038 / ADR-039 | §1.4 / §5.1 / §8 #5 | §1.2 / §3.4 / §6.1 | ADR 关联 | Gate 7 | ✅ 一致 (C) |

**说明**:

1. 调研 §4 已明确"未读原文不作为强论据"; 设计/实施/ADR 沿用该等级, 无升格。
2. 调研 §9 R3 曾把 FPP3 标为 B (步骤 2 时点), 与 §4 / 附录 C 的 A 冲突; 已在 §9 R3 加注"步骤 2b 已 WebFetch 原文, 升为 A"。
3. Marriott-Pope 的解析偏差 `-(1+3φ)/n = -0.0258` 与 2000 次模拟均值 `-0.0283` 是**两种口径**, 调研 §10.2 已分列标题 ("解析锚点" / "数值验证"), 不构成数值冲突。

---

## §2 接口签名一致性

| 接口 | 设计 (§2.3 / §3.2 / §3.7) | 实施 (§3.2-§3.7 / E1) | 源代码 | 状态 |
|------|---------------------------|----------------------|--------|------|
| `ARDecoupler.__init__(max_order=5, min_order=1, criterion='aic', strength=1.0, min_obs=20, warmup_obs=120)` | 追加末尾 | 同 | L235-L254 (5 个既有参数) | ✅ |
| `ARDecoupler.fit(self, data) -> 'ARDecoupler'` | 不变 | 不变 | L256-L272 | ✅ |
| `ARDecoupler.transform(self, data) -> pd.DataFrame` | 不变 | 不变 | L298-L331 | ✅ |
| `ARDecoupler._predict_one_step(vals, t, coef, p) -> float` | 新增 staticmethod | 同 | 不存在 (待实现) | ✅ |
| `AROrderSelector.fit(self, series) -> ARModelResult` | 签名不变; 改为 `_fit_best` 包装 + INFO 日志 | 同 | L80-L129 | ✅ (步骤 8 已把设计改为 `_fit_best`) |
| `AROrderSelector._fit_best(self, series) -> ARModelResult` | 新增私有 | 新增私有 | 不存在 (待实现) | ✅ (步骤 8 补入设计) |
| `AROrderSelector._fit_ar(self, series, order)` | 复用 (早期固定低阶) | 同 | L131-L176 | ✅ |
| `ARModelResult` 字段 | 不变 | 不变 | 10 个 (L32-L44) | ✅ (实施原写 11, 已改 10) |
| `CompositeDecoupler.fit/transform` | 不变 | 不变 | `dual_neutralizer.py` L384 / L444 | ✅ |
| 模块常量 `_WARMUP_REFIT_STRIDE = 10` | 私有 | 私有 | 不存在 (待实现) | ✅ |

**结论**: 无签名漂移。步骤 8 修复了一处设计 ↔ 实施漂移 (`self._selector.fit(ser)` → `_fit_best(ser)`) 与一处字段计数错误 (11 → 10)。

---

## §3 验收标准一致性

| 验收项 | 设计 | 实施 | checklist | 状态 |
|--------|------|------|-----------|------|
| Dynamic 截断 0/0/0 | §5 V1 | §1.3 / §4.3 | G3-3 | ✅ |
| 顶层截断 0/0/0 + 路由一致 | §5 V2 | §1.3 / §4.3 | G3-4 / G3-5 | ✅ |
| 摘除 2 个 strict xfail | §4.2 / §7 | §4.3 | G3-1 / G3-2 | ✅ |
| 新增单测 10 函数 / **16 用例** | V4 / §7 | §0.1 E5 / §4.1 / §4.2 | G1-1 / G2-11 | ✅ (步骤 8 统一为用例口径) |
| Red **15 failed / 1 passed** (实测) | §7 步 1 | §4.1 | G1-3 | ✅ (步骤 8 预测 14/2, 步骤 9 实测更正) |
| Green **16 passed** | §7 步 2 | §4.2 | G2-11 / G4-2 | ✅ (步骤 8 修正) |
| 集成 **10/2 → 15/0** | §4.3 | §1.2 / §1.3 / §4.5 | G0-4 / G3-6 | ✅ |
| 多截断点 7 参数全 0 | V5 | §4.1 | G2-2 | ✅ |
| φ 容差 0.05 → 0.15 + 区间 | §4.2 / R6 | §4.4 | G4-4 | ✅ |
| 性能 AR ≤ 6s / 管线 ≤ 45s | V9 | §4.6 | G5-1 / G5-2 | ✅ |
| 输出偏移 2851–2855 | V10 | §4.6 | G5-3 | ✅ |
| NaN 146 → 0 | §3.3 / V6 | §4.6 | G5-4 | ✅ |
| 版本 / 缓存 / ADR 同步 | V11 / §6 | §5 | Gate 6 / Gate 7 | ✅ |
| `fitted_values.reindex` 清零 | V12 | 附录 A | G8-4 | ✅ (命令改为 `-- '*.py'`) |

**测试计数核对 (关键)**:

- 新单测 = 10 个函数; `test_truncation_invariant_multi_cut` 参数化 `[10,15,25,30,45,60,80]` 展开 7 例 → **16 个 pytest 用例**。步骤 8 预测 6 个函数 TypeError + 2 个断言失败 + 2 个通过 → 14/2; **步骤 9 实测更正为 15 failed / 1 passed**: 7 个函数 TypeError (multi_cut 展开 7 例 → 13 用例; `metadata_preserved` 也传 `warmup_obs=40` 故未通过) + 2 个函数断言失败 (`cold_start_is_identity` / `fitted_columns_add_no_nan`); 仅 `test_strength_soft_mix` 通过。实现后 **16 passed**。
- 集成文件 = 12 个测试函数 (无参数化); 基线 10 passed + 2 xfailed; 摘 2 个 xfail 后 12 passed; 新增路由测试 3 参数 → **15 passed / 0 xfailed**。

---

## §4 决策记录对齐

| 决策 | 设计 | 实施 / ADR-040 | checklist | 状态 |
|------|------|----------------|-----------|------|
| D1 `fit` 只用前 K 行 | §0 / §3.1 | §3.3 / ADR 决策 1 | G2-1 / G3-3 | ✅ |
| D2 三段式因果一步预测 | §0 / §3.2 | §3.4 / ADR 决策 2 | Gate 2 / Gate 3 | ✅ |
| D3 移除 `_results` 门控 | §0 / D3 | §3.4 / ADR 决策 3 | G2-6 | ✅ |
| D4 删除 `fitted_values.reindex().ffill()` | §0 / D4 | §3.4 / ADR 决策 3 | G8-4 | ✅ |
| D5 `warmup_obs=120` 公开 / stride 私有 / `ValueError` | §0 / §2.3 | §3.2 / ADR 决策 4 | G2-7 | ✅ |
| D6 φ 容差 0.15 + 覆盖率注释 | §0 / D6 | §4.4 | G4-4 | ✅ |
| D7 PL-07 拆为输出不变式 + 3-seed 路由 | §0 / §4.2 | §4.3 | G3-2 / G3-5 | ✅ |
| D8 v3.3.6 / `v2.2.4-cache` / ADR-040 | §0 / §6.1 | §5 | Gate 6 / Gate 7 | ✅ |
| D9 范围仅 `ARDecoupler` | §1.2 / §9.3 | §8.3 / ADR 不覆盖 | G8-8 | ✅ |
| D10 `hold_back` 不纳入 → PL-08-candidate | §1.2 / D10 | §4.3 / ADR 不覆盖 | G3-7 / G8-8 | ✅ |
| ADR 占用表 | "ADR-040, ADR-041 起未占用" | §5.3 模板 | G7-3 | ✅ (DECISIONS L42-L43 实测吻合) |
| ADR-040 状态 | — | "待实施 (步骤 9 完成后更新)" | G7-2 | ✅ (与步骤 8 时点一致) |

**说明**: `_fit_best` 拆分是**实现细节** (消除 warm-up 的 N×12 条 INFO 日志), 不构成新的方法学决策, 因此不新增 D11; 已在 DESIGN §3.2 / §9.1 与 EXECUTION E1 双向登记。

---

## §5 数值一致性

| 数值 | 调研 | 设计 | 实施 | checklist | 状态 |
|------|------|------|------|-----------|------|
| AR 单步基线 | 1652/1800, 8.788e-01, NaN 7, 56/60, 2020-05-31 | §3.6 同 | 未单列 | G0-10 (Dynamic) | ✅ |
| Dynamic 基线 | 1653/1800, 8.045313632310727e-01, NaN 8, 57/60, 2020-04-30 | 1653, 8.045e-01 | 1653 / 8 / 8.0453e-01, 57/60 | 8.045313632310727e-01 | ✅ |
| 顶层基线 | 1650/1800, 1.8397305724759783 | 1650, 1.8397 | 1650, 1.8397 | 1.8397305724759783 | ✅ |
| AR 输出 NaN | 146/3000 | 146 → 0 | 146 → 0 | 146 → 0 | ✅ |
| 输出偏移 | 2851–2855/3000, max 2.1038–4.1873, mean 0.2287–0.3486 | 2851–2855, max 2.1–4.2 | 2851–2855, max 2.1–4.2, mean 0.23–0.35 | 2851–2855, 2.1–4.2, 0.23–0.35 | ✅ |
| AR 性能 | 0.48 → 2.11–5.76s | 0.48 → 2.11–5.76s | 0.48 → 2.11–5.76s | 基线 0.48, 预测 2.11–5.76 | ✅ |
| Dynamic 全管线 | 33.19 → 42.50s (+28%) | 同 | 同 | 33.19 → 42.50 | ✅ |
| `mean_ar1` (起点 60) | 0.0029 → 0.0302 | 0.0029 → 0.0302 (步骤 8 注明起点) | 0.0029 → 0.0302 (ADR 注明起点) | ≈0.03, 起点 60 | ✅ (步骤 8 消除口径歧义) |
| `mean_ar1` (起点 6, 另一口径) | 0.0647 (附录 C: 起点 20 → 0.0482) | 未引用 | 未引用 | 未引用 | ✅ (仅调研陈述, 已标起点) |
| K 质量曲线 | 40/60/80/100/120/160/200/300 = 0.1255/0.0998/0.0772/0.0359/**0.0302**/0.0303/0.0236/0.0228 | 仅用"拐点 120" | ADR 用 0.0302 | G5-5 ≈0.03 | ✅ |
| φ 覆盖率 (n=120) | P(<0.05)=50.30%, P(<0.15)=94.75% | "约 50%" → 0.15 | R6 50.3%→94.8% | — | ✅ |
| φ 解析偏差 / sd | -0.0258 / 0.0652 | 未引用 | §4.4 注释 | — | ✅ (与模拟 -0.0283/0.0699 分列) |
| 阶数一致率 | 89.00%; mean 4.850 vs 4.937 | 89.00% | — | — | ✅ |
| warm-up 重估次数 | **12** (t=7,17,…,117; 步骤 8 修正) | `N×12` | 12 次 / 3600 条 | mock max ≤ 40 | ✅ |
| 缓存字面量 | test_fix3 6 行 (步骤 8 修正) | L83-84 / L85 | 7 个命中 = cache_manager L58 + test_fix3 6 行; 其中 **6 处更新** (cache_manager + test_fix3 5 行), L84 保留 | L84 + L85 白名单 | ✅ |
| `ARModelResult` 字段 | — | — | **10** (步骤 8 修正) | — | ✅ |

---

## §6 不一致项与修复

| # | 级别 | 位置 | 问题 | 修复 |
|---|------|------|------|------|
| F1 | **MAJOR** | 实施 §0.1 E5/§1.3/§4.1/§4.2/§6.2/§7.2; 设计 V4/§7; checklist G1-3/G2-11/G4-2 | Red/Green 计数按**测试函数** (8 failed/2 passed; 10 passed) 写, 但 `pytest -q` 按**用例**计数; multi_cut 参数化 7 例 → 14/2 为步骤 8 预测, **步骤 9 实测 15/1**、Green **16** | 全部改为用例口径, 并注明 10 函数/16 用例; 步骤 9 回注实测计数 |
| F2 | **MAJOR** | 设计 §3.2/§3.2 说明 1/§9.1 vs 实施 E1/§3.1 | 设计伪代码调用 `self._selector.fit(ser)` 会为每列 12 次重估打印 INFO; 实施新增 `_fit_best` 但设计未登记该接口与必改项 | 设计改为 `_fit_best`; 说明 1 改为两类私有调用; §9.1 补 `AROrderSelector.fit` 拆分 |
| F3 | **MAJOR** | 实施 §5.2/附录 A/附录 C F5; 设计 §4.2; 调研 §5.3; checklist G6-9 | `v2.2.3-cache` 在 test_fix3 实为 **6 行** (L14/79/84/93/94/109), 非 7 行 (L83 是 PL-02 历史, 不含 v2.2.3); 白名单应为 L84 + 新增 L85 | 统一为 6 行; 明确 6 处更新; 白名单 L84 + L85 |
| F4 | MINOR | 实施 §3.7 | `ARModelResult` 写 11 字段, 实为 **10** | 改 10 |
| F5 | MINOR | 实施 E1 vs §3.1 | 搬移范围 E1 写 L94-L129、§3.1 写 L98-L129; 实际为 L94-L126 + L129 return, L127 INFO 留在 `fit` | 两处统一为 L94-L126 (+L129) |
| F6 | MINOR | 实施 §4.1 Red 表 | `test_fitted_columns_add_no_nan` 写"当前 146 NaN" — 该测试面板 N=6, 146 是 N=30 面板的数 | 改为"当前存在前导 NaN" |
| F7 | MINOR | 设计 §3.6; 实施 ADR; checklist G5-5 | `mean_ar1` 未注明统计起点; 调研 §3.4 用起点 6 (0.0647), 设计/实施用起点 60 (0.0302), 易被读成矛盾 | 三处均注明"统计起点第 60 行"; 调研附录 C 已记起点敏感性 |
| F8 | MINOR | 调研 §3.4 | "重估次数由 100 降到 10" 与实施 12 次 (t=7..117) 不一致 | 改为"由 ~100 降到 12 (t=7,17,…,117)" |
| F9 | MINOR | 调研 §3.6 | B'' 性能写 `2.11s` (与全文 2.11–5.76s 不符); 配置面写 `K + stride` (stride 实为私有) | 改为 `2.11–5.76s`; `K` (公开) + `stride` (私有常量) |
| F10 | MINOR | 实施 §6.1 | spec 映射仍写步骤 6/7/8 "待执行"、本文档 v1.0, 与 v1.1/附录 C/checklist 实际状态矛盾 | 更新为步骤 5-8 完成, 工件版本指向 v1.1/v1.2/v1.1/v1.0 |
| F11 | MINOR | 实施 §4.3 item 3 | 称 `routes_*` 未使用需改名; 实际仍被 L392-L394 的产出断言消息使用 | 删除改名建议, 保留原名 |
| F12 | MINOR | 实施 §2.2/§5.1; checklist G6-5 | `test_fix3` 的 3.3.5 docstring 只列 L12-14, 漏 L39/L47/L56 | 补入变更清单与检查项 |
| F13 | MINOR | 实施附录 A; checklist G6-9/G8-4/G8-5/G8-6/G6-10 | grep 命令用了仓库根不存在的 `factor_pipeline/` 路径; `git grep "warmup_obs"` 未限定路径会命中新单测; G6-10 后 3 个路径缺 `backtest/` 前缀 | 改为仓库根 + `-- '*.py'` / `-- modules/`; 补全 `backtest/` 前缀 |
| F14 | MINOR | 设计 §4.3; §11 F1 | "12 个既有测试摘 xfail 转正" 实际只有 2 个摘 xfail, 12 是既有用例总数 | 改为"12 个既有测试全部通过 (含 2 个摘 xfail) + 3 个新参数 = 15" |
| F15 | MINOR | 设计 §4.1 | mock 测试声称"断言所有调用长度 ≤ 当前 t", 实施只断言 `max ≤ warmup_obs` 且 `min < warmup_obs` | 设计改为与实施一致, 并注明证明目标 (逐步扩展且不越界) |
| F16 | MINOR | 调研 §9 R3 | FPP3 证据等级仍写 B, 与 §4/附录 C 的 A 冲突 | 加注"步骤 2b 已 WebFetch 原文, 升为 A" |
| F17 | MINOR | 调研 §5.3; 设计 §4.2/§11 P14 | 历史行号写 "L83", 实际 PL-06 历史在 L84, 追加位置 L85 | 统一为 L83-84 历史, L85 追加 |
| F18 | INFO | 实施 §0.1 E7 | "10 个文件" 与实际变更面 (11 文件 + 2 上游文档状态) 不符 | 改为 11 (+2) |
| F19 | INFO | 调研 §3.4/§7 | "候选值, 待设计文档定稿" 与 §7 未决问题在 v1.4 时已全部定稿 | 改为"设计已定稿"; §7 加状态说明 |
| F20 | INFO | checklist G0-3/G6-10 | 工作树未提交文档未含 consistency review; G6-10 路径不完整 | 补 consistency review; 补全路径 |
| F21 | MINOR | 设计 §3.2; 实施 §3.4 | 设计伪代码调用 `_predict_one_step(...)` 未加 `self.` — staticmethod 不在模块命名空间, 照抄会 `NameError` | 设计改为 `self._predict_one_step(...)`; 实施代码块加注"类内方法, 缩进省略" |
| F22 | MINOR | 调研 §3.8 | 门控代码链接写 `#L317-L320`, 实际门控块为 L317-L319 (L320 是 `ar_result = ...`) | 改为 L317-L319 |
| F23 | MINOR | 调研 §6.2 item 6 | 验收草案仍写"诊断报告 Dynamic / **顶层行**由 FAIL 转 PASS" — 该报告实测仅 6 step + 3 pipeline 行, **无顶层行** (与实施步骤 6 F8 同类残留) | 改为"Dynamic 行转 PASS + 无顶层行说明, 顶层由摘 xfail 后的集成测试直接断言" |
| F24 | INFO | 设计 §4.1 | `test_one_step_prediction_matches_hand_calc` 描述写 AR(1) 特例 `c0 + c1·vals[t-1]`, 实现是 AR(p) 通式 (`max_order=2` 循环求和) | 改为通式 `c0 + Σ c_i·vals[t-1-i]` 并注明实现阶数 |
| F25 | INFO | 设计 §4.1 | N4 构造示例"如仅 8 个有效值"与实现 (17 个, `iloc[3:20]`) 不一致 — 示例值失真 | 改为"实现取 17 个: iloc[3:20]" |
| F26 | INFO | checklist G8-3 | 变更范围只提 §2.2 的文件, 未含 §5.6 要求的 2 份上游文档 (调研/设计头部) 状态更新 | 期望改为"§2.2 列出的 15 个文件 + §5.6 的 2 份上游文档头部" |

**修复验证**: 上述 26 项已直接修改四份文档与 checklist; 修改未改变任何契约、决策或实测数值, 仅校正计数口径、接口登记、行号与命令作用域。F22-F26 来自用户指令触发的**第二轮独立核验** (2026-11-04): 全部源码行号 / 测试锚点 / 版本锚点重新对源实测, 未沿用第一轮结论。

---

## §7 结论与放行

| 维度 | 结果 |
|------|------|
| 引用一致性 | 通过 (10 组; 无虚构/无等级升格; R3 历史标注已修) |
| 接口签名一致性 | 通过 (10/10; `_fit_best` 已双向登记; 字段数已改 10) |
| 验收标准一致性 | 通过 (14/14 映射; 测试计数已统一为用例口径) |
| 决策对齐 | 通过 (D1-D10 + ADR 占用表; ADR-040 状态与步骤 8 时点一致) |
| 数值一致性 | 通过 (16 组; 无跨文档漂移; `mean_ar1` 口径已注明) |
| 发现不一致 | **26 项 (3 MAJOR + 17 MINOR + 6 INFO)**, 全部已修复 (含第二轮独立核验新增 5 项) |
| 阻塞项 | 无 |

**放行**: 可进入 spec 步骤 9 (TDD 实现)。

- 实现以 [EXECUTION v1.2](../EXECUTION_V3.3.6_PL05_DYNAMIC_AR_CAUSALITY.md) 为准; checklist 以 [v1.1](CHECKLIST_V3.3.6_PL05_DYNAMIC_AR_CAUSALITY.md) 为执行基准。
- 步骤 9 完成后: 回填 checklist "实际"列 (升 v1.2)、回填 EXECUTION §7.2 (升 v1.3)、更新 ADR-040 状态为"已实施"。
- 步骤 10 审计对照 checklist Gate 0-8 逐项确认。
