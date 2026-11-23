# 验收清单：P-020 tradability 小口径收尾 + 台账同步

---
id: p020-tradability-cleanup-and-ledger-CHECKLIST
type: design
version: 1.1
status: accepted
date: 2026-11-23
depends: [p020-tradability-cleanup-and-ledger-IMPLEMENTATION, p020-tradability-cleanup-and-ledger-DESIGN]
upstream: null
---

> **Feature**: P-020（A 台账同步 + B 三项小口径收尾）
> **Spec 步骤**: Step 7-8（+§10 Step 9/10 回填）
> **档位**: **T1** ｜ **包版本**: 3.9.9 → 3.9.10 ｜ **新依赖**: 无

---

## 1. 文档一致性（Step 8）

| # | 检查对 | 判据（DoD） | 结果 |
|---|---|---|---|
| C-1 | RESEARCH → DESIGN | 每条 F-1-1~F-4-3 至少被一条 D 引用；无悬空发现 | ✅ F-1-x→D1、F-2-x→D3/D4、F-3-x→D2、F-4-x→D6 |
| C-2 | DESIGN → IMPLEMENTATION | D1-D6 全部有实施落点；INV-1~6 全部进 CHECKLIST §4 | ✅ D1/D2 §3.2，D3/D4 §3.3，D5 §5.1，D6 §5.3 |
| C-3 | IMPLEMENTATION → CHECKLIST | T020-1a/1b/2/3/4/5/6 全部在本清单 §2 有对应项 | ✅ F-1~F-6、F-8 |
| C-4 | 术语一致 | 「精确优先」「归一化回退」「eps 单源」三词在 DESIGN/IMPLEMENTATION/CHANGELOG 用法一致 | ✅ 三处逐词核对一致 |
| C-5 | 版本一致 | DESIGN §5.5 / IMPLEMENTATION §5.1 / CHANGELOG 均为 **3.9.10** | ✅ 三处均 3.9.10 |

**机械校验**：`Grep "3\.9\.9"`（排除 `spec/`）→ 命中仅 CHANGELOG 历史条目 / PROJECT_STATUS、PROGRESS 历史行（非版本字段）；6 个版本锚点全为 `3.9.10` → **通过**。

## 2. 功能验收

> 每项 DoR = 前置条件；DoD = 可观察通过条件。

| # | 项 | DoR | DoD | 结果 |
|---|---|---|---|---|
| F-1 | D1 eps 单源 | 实施完成 | `TradabilityPolicy(eps=0.0)` 构建时 `meta.one_word_up_cells==0`，默认构建 `==1`（T020-3 绿） | ✅ 红（`==1` 与 `==0` 同时失败）→ 绿 |
| F-2 | D2 归一化回退 | 实施完成 | 裸列名 × 带后缀键 → `no_limit_source=="list_date"`，列 0 `no_limit[2:7]` 全真、列 1 `no_limit[3:8]` 全真（T020-4 绿） | ✅ 红（source 仍 `delisting_only`）→ 绿 |
| F-3 | D2 精确优先 | 实施完成 | 双键共存时取精确键日期（T020-5 绿） | ✅ 绿（构造具判别力：错误实现取 dates[3] 即失败） |
| F-4 | 一字板正向计数（上） | 实施完成 | 单事件一字涨停 → `one_word_up==1`、`down==0`（T020-1a 绿） | ✅ 绿 |
| F-5 | 一字板正向计数（下） | 实施完成 | 单事件一字跌停 → `one_word_down==1`、`up==0`（T020-1b 绿） | ✅ 绿 |
| F-6 | `ref=` 直传 | 实施完成 | `adj=None` + `ref` 矩阵 → `blocked_buy==1`、`limit_unknown==0`（T020-2 绿） | ✅ 绿 |
| F-7 | A 台账同步 | 文档改完 | PROJECT_STATUS §1 有 v3.9.9 与 v3.9.10 两行、指针在 v3.9.10；§2 优先级视图为 P2 无 / P3 = P-009 / P-018（P-020 已 done，不列入待办集） | ✅ 两文件已核对一致 |
| F-8 | 归一化「首见优先」+ 整数键 | 实施完成 | 整数列名 `600000` + 双键 dict → 取首见键 dates[2]，`no_limit[2:7]` 全真（T020-6 绿） | ✅ 绿 |

## 3. 接口验收

| # | 项 | DoD | 结果 |
|---|---|---|---|
| I-1 | `_norm_code` 存在且为私有 | `backtest.tradability_inputs._norm_code` 可导入，`__all__` 仍仅 `["build_tradability_inputs"]` | ✅ |
| I-2 | `build_tradability_inputs` 签名不变 | 8 个位置参数 + 3 个关键字参数逐字一致 | ✅ |
| I-3 | meta 键集合不变 | 仍为 13 键（`test_meta_keys_and_price_basis` 绿） | ✅ |
| I-4 | `st_overrides` 行为等价 | 既有 `test_st_overrides_calibration` 三断言绿 | ✅ |
| I-5 | `TradabilityInputs.policy` 不被改写 | 传 `policy=None` 时 `inputs.policy is None` | ✅ 代码未回写 |
| I-6 | `apply_tradability` 零改动 | `git diff` 不含 `backtest/tradability.py` | ✅ diff 清单 12 文件，无该文件 |

## 4. 不变式验收（INV-1~6）

| # | 不变式 | 核验方式 | 结果 |
|---|---|---|---|
| N-1 | INV-1 默认引擎路径逐位不变 | `test_tp6_11_default_baseline_unchanged` 绿（TP6-11 五指标 + turnover 11 项字面量） | ✅ 定向套件 49 passed 含该例 |
| N-2 | INV-2 默认构建 meta 逐值不变 | 既有 `test_one_word_counts` / `test_meta_keys_and_price_basis` / `test_ipo_no_limit_and_source` 绿 | ✅ |
| N-3 | INV-3 eps 同源 | T020-3 红→绿（同一 policy 下构建器与推进期用同一 eps） | ✅ |
| N-4 | INV-4 精确命中行为不变 | T020-5 绿 | ✅ |
| N-5 | INV-5 算法层零改动 | `git diff --stat` 不含 `tradability.py` / `engine.py` | ✅ |
| N-6 | INV-6 容量工件不变 | `git status` 无 `out/capacity_impact.json` 变更 | ✅ 未写盘 |

## 5. 错误处理验收

| # | 场景 | DoD | 结果 |
|---|---|---|---|
| E-1 | `adj=None` | 仍抛 `ValueError`（`test_adj_required` 绿） | ✅ |
| E-2 | `list_date` 未命中 | 静默跳过（与 v3.9.9 一致；归一回退后命中面增大，不新增异常） | ✅ 代码 `continue` 分支保留 |
| E-3 | `list_date` 值为 `NaN` | `pd.isna` 分支跳过，`used` 不变 | ✅ 分支未改 |

## 6. 性能验收

| # | 项 | 预算 | 结果 |
|---|---|---|---|
| P-1 | 构建器耗时 | ≤ 1.1× v3.9.9（新增 O(K) 字典 + O(N) 键归一） | ✅ 结构性论证：与旧实现的逐列循环同阶，仅多一次 O(K) 建表（无实测基线可对拍） |
| P-2 | 新增内存 | ≤ 1 MB（归一化映射 K 键） | ✅ K = 列数级，远小于 1 MB |

## 7. 兼容性验收

| # | 项 | DoD | 结果 |
|---|---|---|---|
| K-1 | Python 3.9 | 无 3.10+ 专属语法；pytest 收集期导入成功 | ✅ |
| K-2 | 零新增依赖 | `pyproject.toml` diff 仅 version 行 | ✅ |
| K-3 | 测试锚点 | `EXPECTED_VERSION` 两处为 3.9.10，版本测试绿 | ✅ |

## 8. ADD 审计（Step 10）

| # | 项 | DoD | 结果 |
|---|---|---|---|
| A-1 | Iron Law 四类 | 恒真断言 PASS / 生产路径 PASS / 覆盖缺口已补（T020-6）/ 文档漂移已修 | ✅ |
| A-2 | 审计独立性 | 独立只读子代理裁决 **PASS_WITH_FIXES**（0×P1 / 2×P2 / 4×P3） | ✅ 2×P2 + 4×P3 全部就地处置 |
| A-3 | 取证矩阵 | 每条 P 项有证据位置；无证据不标 ✅ | ✅ 见 §8.1 |
| A-4 | 台账闭环 | PROGRESS P-020 → done；CHANGELOG v3.9.10 含三要点 | ✅ |

### 8.1 Step 10 审计处置表

| # | 级别 | 审计发现 | 处置 |
|---|---|---|---|
| 1 | P2 | CHECKLIST 未回填即把 P-020 标 done | 本文件 §1-§8 全部回填（本节即处置） |
| 2 | P2 | PROJECT_STATUS §2 同句既列 P-020 待办又标其已完成 | 已改为 `P3 = P-009 / P-018（P-020 已于 v3.9.10 完成）` |
| 3 | P3 | DESIGN §5.6 写「指针移到 v3.9.9」 | 已改为 v3.9.10 |
| 4 | P3 | DESIGN §5.3 仍是单例「不串扰」表述 | 已同步为 T020-1a/1b 双单事件用例 |
| 5 | P3 | IMPLEMENTATION T020-4 判据写 `no_limit[:5]`，与实测 dates[2]/dates[3] 不符 | 已改为 `[2:7]` / `[3:8]`；T020-3 判据 `>=1` → `==1` |
| 6 | P3 | 覆盖缺口：归一化「首见优先」与整数键无用例 | 新增 T020-6（红→绿不适用，直接绿；构造具判别力） |

## 9. DoR / DoD 汇总

- **DoR（开工前）**：RESEARCH verified；DESIGN verified（Step 4 复审 PASS_WITH_FIXES 已处置）；IMPLEMENTATION 接口 + 回退点齐备。
- **DoD（收尾）**：§1-§8 全部 `通过`；全量回归 **0 failed**；默认 SHA 不变；四件套 status 全 `verified/accepted`。
- **禁止**：任何未运行测试的 ✅；任何「绿」但无命令 + 计数的登记。

## 10. 执行记录

### 10.1 Step 9 TDD 读数（F5）

- **红**（测试先行、未改生产代码）：`python -m pytest -q tests/test_tradability.py tests/test_tradability_inputs.py -k t020` → **2 failed / 4 passed / 32 deselected**（失败 = T020-3 eps 不受 policy 影响、T020-4 `no_limit_source` 仍 `delisting_only`）。
- **绿**（改 `backtest/tradability_inputs.py` 后）：同命令 **7 passed / 32 deselected**（含审计后补测的 T020-6；补测前读数为 6 passed）；定向套件 **49 passed, 3.77 s**（含 TP6-11 基线 + 版本测试）。
- 注：T020-6 为审计后补测，直接绿（覆盖补强，非红→绿）。

### 10.2 全量回归

- 命令：`$env:PYTHONPATH='f:\Coding'; python -m pytest -q --basetemp=f:\Coding\factor_pipeline\.pytest_tmp`（cwd = `f:\Coding\factor_pipeline`）
- 读数：**2151 passed / 34 skipped / 0 failed / 181 warnings，890.69 s（14:50）**
- 本批新增 7 例（T020-1a/1b/2/3/4/5/6）；`34 skipped` 为 `Factor_Trading_v3_0` 未安装的既有跳过。

### 10.3 Step 10 审计

- 独立只读子代理裁决：**PASS_WITH_FIXES**（0×P1 / 2×P2 / 4×P3）→ 全部就地处置（§8.1）。
- 质量门：Iron Law 恒真断言 PASS；生产路径 PASS；覆盖缺口已补；文档漂移已修；默认路径等价 PASS。
- 版本落点 6 锚点均 3.9.10，代码/配置无 3.9.9 残留。

## 11. 异构复审记录（双视角，2026-11-23）

> 双视角独立子代理审查（均只读、互不知晓对方结论）：**视角 A = 对抗式 E1 锚点核查 + 证据重放**（允许重放 pytest 小命令）；**视角 B = 过程合规 / 裁决逻辑 / 账本一致性**。

### 11.1 视角 A：对抗式锚点核查 + 证据重放

- 结论：**PASS_WITH_FIXES**。8 组锚点：6 PASS / 2 DRIFT / 0 FAIL。
- 绿读数重放：`-k t020` → **7 passed / 32 deselected**；定向套件 → **49 passed**（与 §10.1/§10.2 记载一致，T020-6 补测后计数已回写）。
- 版本锚点 6 处全 3.9.10；`git status` 恰 12 M + 1 spec 目录，无 tradability.py / engine.py；台账三件相互一致。

### 11.2 视角 B：过程合规 / 裁决逻辑 / 账本一致性

- 结论：三维度全 PASS（DC1 front-matter / F4 引用无误标 / F3 降级链 / 被拒方案 / 签名+回退点 / DoR-DoD / F5 红→绿 / T1 判档）；三处复审审计「发现→处置→签字」闭环完整，§8.1 六条逐条可查落地；账本无陈旧表述、无相互矛盾。

### 11.3 异构复审发现处置表

| # | 级别 | 发现 | 处置 |
|---|---|---|---|
| 1 | P2 | 绿读数记「6 passed」不可重放（T020-6 补测后同命令实为 7 passed / 32 deselected），未随补测回写 | §10.1 与 IMPLEMENTATION §7 均改为「7 passed / 32 deselected（含 T020-6；补测前 6 passed）」 |
| 2 | P3 | RESEARCH F-2-5 引用定位错（D-6-7 在 P-006 IMPLEMENTATION §14，非 DESIGN §14）；F-2-6 审计编号映射错（实际 P3-② = eps 源、P3-③ = 覆盖缺口合并条、P3-④ = list_date） | 两行已按 P-006 CHECKLIST §8.2（L271-273）原始登记订正并互链 F-1-3 / F-3-1 |

### 11.4 复审结论

- **批次验收维持 accepted**：视角 A 的 1×P2 + 1×P3 均为文档级、已就地处置；视角 B 无发现；生产代码与测试零改动需求。

**异构复审签字**: 视角 A（对抗式锚点核查 + 证据重放）＋ 视角 B（过程合规 / 裁决逻辑 / 账本一致性），2026-11-23
