# v3.3.7 PL-08 AR 阶数选择 hold_back 可比性修复 — 审查验收 Checklist

**版本**: v1.1 (2026-11-04; v1.0 = 步骤 7 生成; v1.1 = 步骤 8 一致性 review 修订; 步骤 9 完成后回填"实际"列)
**日期**: 2026-11-04
**缺陷**: DEFECT-PL-08
**实施文档**: [EXECUTION_V3.3.7_PL08_AR_ORDER_HOLDBACK.md](../EXECUTION_V3.3.7_PL08_AR_ORDER_HOLDBACK.md) v1.2
**设计文档**: [analysis/PL08_AR_ORDER_AIC_COMPARABILITY_DESIGN.md](../analysis/PL08_AR_ORDER_AIC_COMPARABILITY_DESIGN.md) v1.2 (方案 C 选定)
**调研文档**: [analysis/PL08_AR_ORDER_AIC_COMPARABILITY_RESEARCH.md](../analysis/PL08_AR_ORDER_AIC_COMPARABILITY_RESEARCH.md) v1.2
**生成时机**: spec 步骤 7 (实施文档 review 通过后, TDD 实现前)
**判定规则**: 任一 "必须" 项未通过 → 本阶段不通过; **允许的 known-xfail / skip = 0**。
**例外路径**: 唯一环境例外 = `test_E10_bridge_init_params_exist` (`duckdb` 未安装); 该失败在基线与实施后**均存在**, 不计入本次验收, 但必须在 §1 签署区注明。

> 位置说明: 本工件按 WORKFLOW_METHODOLOGY v1.3 §13.7 放在 `docs/audit/`。

---

## §0 使用方式

1. 按 Gate 顺序执行; 每项填写 `实际` 与 `证据`; **未实测的数字不得填入结论**。
2. 命令统一在 `F:\Coding\factor_pipeline` 下运行; 解释器为当前 `python` (本任务实测 3.13.5)。
3. 行号仅作导航, 以类名 / 函数名 / 测试名为准 (编辑后会漂移)。
4. 本 checklist 是步骤 10 审计的输入基准; 实施后逐项对照勾选。
5. 任一 Gate 失败即停止后续 Gate, 先修复再重跑本 Gate。
6. **Gate 0 的基线数值已于 2026-11-04 实测**; 实施开始时须复跑确认 (若他人已提交新变更, 以复跑为准)。
7. `git grep` 只搜已跟踪文件; 新增测试文件用 `git status` / 直接路径核验。

---

## Gate 0: 前置与基线

| # | 检查项 | 必须 | 命令 / 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------------|------|------|------|
| G0-1 | 解释器可用 | 是 | `python -m pytest --version` | pytest 可用 | ✅ 可用 (Python 3.13.5) | 命令输出 |
| G0-2 | 运行时与库版本 | 是 | `python -c "import sys,numpy,pandas,statsmodels; ..."` | Python ≥3.9; pandas ≥2.0 (`freq='ME'` 需 ≥2.2); numpy ≥1.22; statsmodels ≥0.13 | ✅ 3.13.5 / numpy 2.1.3 / pandas 2.2.3 / statsmodels 0.14.4 | 命令输出 |
| G0-3 | `duckdb` 环境项 | 否 | `python -c "import duckdb"` | 失败 (已知环境缺包) | ✅ `ModuleNotFoundError` | 命令输出 |
| G0-4 | 工作树状态已知 | 是 | `git status --short` | 仅 PL-08 文档未提交 (research/design/execution/checklist); 生产代码未改 | ✅ 撰写时点 3 份文档未跟踪 (checklist 自身第 4 份); `ar_model.py` 未改; 步骤 9 复跑以 `git status` 为准 | `git status` |
| G0-5 | 基线靶向套件 | 是 | §Gate 3 的 4 文件命令 | **72 passed / 1 env-fail** | ✅ 72 passed / 1 failed (17.58s) | 输出尾部 |
| G0-6 | 基线分层计数 | 是 | `--collect-only -q` 逐文件 | causality 16 / hidden_effect 29 / pipelines_v2 13 / integration 15 = **73** | ✅ 16 / 29 / 13 / 15 = 73 | 命令输出 |
| G0-7 | 基线 `n_obs` | 是 | 探针: T=100, `_fit_ar` order 1..5 | 99/98/97/96/95 | ✅ 99/98/97/96/95 | 实施文档 §1.2 |
| G0-8 | 基线阶数分布 | 是 | 探针: T=100/N=30 seed=22 | AIC 4.800 / BIC 2.200 / HQIC 3.867; AR(2) 4.87; AR(3) 4.97 | ✅ 4.800 / 2.200 / 3.867; 4.87; 4.97 | 调研 §6.2 |
| G0-9 | 基线性能 | 是 | 探针 2500×300 单次 | 2.76s | ✅ 2.76s | 调研 §6.7 |
| G0-10 | 基线尾部 MSE | 是 | T=500/N=30 seed=42, t≥120 | 1.067782 | ✅ 1.067782 | 调研 §6.3 |
| G0-11 | 基线截断不变式 | 是 | `test_truncation_invariant_multi_cut` (7 点) | 0 格 / 0 NaN | ✅ 7 参数全 passed | 单测输出 |

**失败处理**: 基线不绿 (除 duckdb 环境项) → 停止; 不得把既有失败并入本次验收。→ **未触发**。

---

## Gate 1: Red — 新测试先失败

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G1-1 | 新测试文件存在 | 是 | `tests/unit/test_ar_order_holdback.py` | 存在, **10 个函数** | ✅ 存在, 10 个函数 | 文件 |
| G1-2 | 用例齐备 | 是 | 对照实施文档 §4.1 | 10/10 函数名一致; 参数展开后 **22 用例** | ✅ 22 用例 | 测试文件 |
| G1-3 | Red 计数 | 是 | `pytest <file> -q` (未改实现) | **13 failed / 9 passed** (步骤 5 预演实测) | ✅ **13 failed / 9 passed (0.65s)** | Red 输出 |
| G1-4 | 失败机理正确 | 是 | 核对失败原因 | T1/T4/T9 断言失败; T2 p=1..4 失败; T3 3 例未抛错; T5–T7 均值超界 | ✅ T2 p=1..4 样本不同; T3 3 例 DID NOT RAISE; T4 索引 2020-04-30 ≠ 2020-06-30; T5 4.800 / T6 4.867 / T7 4.967; T9 15/36 元素错位 | Red 输出 |
| G1-5 | 通过项符合预期 | 是 | 同上 | T2 p=5 (样本恰好相同) / T8 3 例 (固定阶数等价) / T10 5 例 (PL-05 已保证) | ✅ 9 passed = T2 p=5 + T8×3 + T10×5 | Red 输出 |
| G1-6 | 未用 xfail 掩盖 | 是 | 检查装饰器 | 新文件无 `xfail` / `skip` | ✅ 0 命中 | `git grep` |
| G1-7 | 断言非恒真式 | 是 | 人工核对 | T2 以 statsmodels 为独立参考; T8 手写旧公式; T9 显式 identity; T10 全样本 vs 截断 | ✅ 符合 | 源码 |

**失败处理**: 若未实现前 >9 例通过 → 断言过松, 必须加严; 不得用 `xfail` 掩盖。→ **未触发** (恰 9 例通过)

---

## Gate 2: Green — 单元测试

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G2-1 | 有效样本一致 | 是 | `test_common_effective_sample` | 5 阶 `len(residuals)` 全为 `n - max_order` (=95) | ✅ passed | 单测 |
| G2-2 | statsmodels 对齐 | 是 | `test_matches_statsmodels_hold_back` (5 参数) | 系数/`llf`/`σ²`/`nobs` 一致 (`atol=1e-10`); AIC 差 `-2` | ✅ 5/5 passed | 单测 |
| G2-3 | 守卫边界 | 是 | `test_guard_rejects_insufficient_effective_sample` (3 参数) | `n_obs=order+5` 抛 `ValueError('有效样本不足')`; `order+6` 通过 | ✅ 3/3 passed | 单测 |
| G2-4 | 索引契约 | 是 | `test_residual_index_starts_at_hold_back` | `index[0] == series.index[H]`; 长度 `n-H` | ✅ passed | 单测 |
| G2-5 | AR(1) 低阶 | 是 | `test_order_selection_low_on_ar1` | 30/30 拟合; 均值 ≤ 2.0 | ✅ passed (均值 1.233) | 单测 |
| G2-6 | AR(2) 恢复 | 是 | `test_order_selection_recovers_ar2` | 均值 ∈ [1.8, 3.2] | ✅ passed (2.533) | 单测 |
| G2-7 | AR(3) 恢复 | 是 | `test_order_selection_recovers_ar3` | 均值 ∈ [2.4, 3.8] | ✅ passed (3.233) | 单测 |
| G2-8 | 固定阶数等价 | 是 | `test_fixed_order_fit_matches_current_formula` (3 参数) | `_results` 系数与旧公式 `y[p:]` **逐值相同** (`atol=0`) | ✅ 3/3 passed | 单测 |
| G2-9 | warm-up 无退化 | 是 | `test_no_zero_variance_fit_in_warmup` | 无 `divide by zero` / `invalid value`; 输出全有限; `t<12` identity | ✅ passed | 单测 |
| G2-10 | 早期截断不变式 | 是 | `test_warmup_early_truncation_invariant` (5 参数: 7/8/9/10/12) | 全样本 vs 截断 `atol=1e-12`, NaN 模式一致 | ✅ 5/5 passed | 单测 |
| G2-11 | 文件全绿 | 是 | `pytest <file> -q` | **22 passed** (10 函数) | ✅ **22 passed (0.29s)** | 输出尾部 |

---

## Gate 3: 既有回归 (靶向)

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G3-1 | 因果性单测 | 是 | `pytest tests/unit/test_ar_decoupler_causality.py -q` | **16 passed** | ✅ 16 passed (0.50s) | 输出尾部 |
| G3-2 | 隐藏效应诊断 | 是 | `pytest tests/test_factor_decoupler/test_hidden_effect.py -q` | **29 passed** (含 φ 区间/容差断言) | ✅ 29 passed (3.40s) | 输出尾部 |
| G3-3 | 管线 V2 | 是 | `pytest tests/test_pipelines_v2.py -q` | **12 passed / 1 env-fail** (duckdb) | ✅ 12 passed / 1 failed (5.06s) | 输出尾部 |
| G3-4 | 集成截断不变式 | 是 | `pytest tests/integration/test_pipeline_truncation_invariance.py -q` | **15 passed / 0 xfailed** | ✅ 15 passed / 0 xfailed (12.12s) | 输出尾部 |
| G3-5 | 合计 | 是 | 4 文件合并 `-q` | **72 passed / 1 env-fail**; 0 新增失败 | ✅ **72 passed / 1 env-fail (43.01s)** | 输出尾部 |
| G3-6 | 软解耦强度 | 是 | `test_soft_decoupling_strength` | passed (strength 1.0 ≠ 0.5 的中间方差) | ✅ passed (合并 `-k` 运行 2 passed) | 输出 |
| G3-7 | 信息损失诊断 | 是 | `test_information_loss_signal_lost` | `interpretation == 'signal_lost'` | ✅ passed | 输出 |
| G3-8 | 未新增 xfail/skip | 是 | `git diff` 测试文件 | 无新增 `xfail` / `skip` | ✅ 0 新增 | diff |

**失败处理**: 若出现新增失败, 先判定是否为 `_fit_ar` 行为变更的直接后果; 不得以放宽断言或 skip 收场。→ **未触发** (唯一失败与基线同一 duckdb 环境项)

---

## Gate 4: 版本与缓存

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G4-1 | 版本统一 | 是 | `git grep -n "3.3.6" -- pyproject.toml __init__.py config_v2.py reporting.py` | **0 命中** (全部 3.3.7) | ✅ 0 命中 (4 文件均 3.3.7) | grep |
| G4-2 | 缓存代际 | 是 | `git grep -n "v2.2.4-cache" -- backtest/cache_manager.py tests/test_fix3_version_unification.py` | 默认值/断言/失败消息 **0 命中** (含 test_fix3 L97 消息, 实施文档 v1.2 §5.2 补列); 历史 docstring (L80/L87) 可保留 | ✅ 默认值/断言/消息 0 命中; 仅 L87/L88 历史演进说明保留 | grep |
| G4-3 | 版本测试 | 是 | `pytest tests/test_fix3_version_unification.py -q` | **7 passed** | ⚠️ 隔离运行 6 passed / 1 env-fail (duckdb 阻断 `backtest` 包导入); 合并靶向运行 **7 passed** | 输出尾部 |
| G4-4 | 手工版本校验 | 是 | `python tests/test_backtest/verify_fix3_manual.py` | 通过 (5 位置均 3.3.7) | ✅ [1] 5/5 均 3.3.7; [2] 无旧号残留; [3] 被 duckdb 阻断 (环境项) | 输出 |
| G4-5 | ADR 占用表 | 是 | `DECISIONS.md` L43-L44 | ADR-041 已占用; **ADR-042 起 未占用** | ✅ ADR-041 已占用; ADR-042 起 未占用 | 文档 |
| G4-6 | ADR-041 状态 | 是 | `DECISIONS.md` ADR-041 | 状态「已实施 (2026-11-04, v3.3.7)」 | ✅ 已实施 (2026-11-04, v3.3.7) | 文档 |
| G4-7 | CHANGELOG | 是 | `CHANGELOG.md` 顶部 | v3.3.7 条目 (根因/方案/实测/兼容/遗留) | ✅ 条目齐全, 实测矩阵已回填 | 文档 |
| G4-8 | 版本字面量漏项 | 是 | `git grep -n "3.3.6" -- tests/test_backtest/verify_fix3_manual.py` | **0 命中** (含 L5 docstring) | ✅ 0 命中 | grep |

---

## Gate 5: 性能与输出偏移

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G5-1 | `n_obs` 全等 | 是 | 探针 T=100 | **95 × 5** | ✅ 95/95/95/95/95 | 探针输出 |
| G5-2 | 阶数分布 | 是 | 探针 AR(1) T=100 | AIC **1.233** / BIC **1.000** / HQIC **1.000** | ✅ 1.233 / 1.000 / 1.000 (n=30) | 探针输出 |
| G5-3 | AR(2)/AR(3) | 是 | 探针 T=120 | 均值 **2.53 / 3.23** | ✅ 2.533 / 3.233 | 探针输出 |
| G5-4 | 输出偏移 T=100 | 是 | 新旧实现同进程对比 | **2790/3000 (93.0%)**, `max_abs≈6.9968` | ✅ 2790/3000 (93.0%), max_abs 6.9968, mean_abs 0.3295 | 探针输出 |
| G5-5 | 输出偏移 T=500 | 是 | 同上 | **14410/15000 (96.1%)**, `max_abs≈4.6718` | ✅ 14410/15000 (96.1%), max_abs 4.6718, mean_abs 0.1337 | 探针输出 |
| G5-6 | 尾部 MSE | 是 | T=500, t≥120 | **1.048759** | ✅ 新 1.048759 / 旧 1.067782 | 探针输出 |
| G5-7 | 截断不变式 11 点 | 是 | 既有 7 点 + 新 5 点 | **0 格 / 0 NaN** | ✅ 既有 7 点 15 passed; T10 5 点全 passed (并集 11 个不同点) | 单测输出 |
| G5-8 | 无退化警告 | 是 | T=80, warmup=40 | 无 `divide by zero` / `invalid value` | ✅ T9 passed (新实现无警告; 探针中警告来自旧实现对照分支) | 单测输出 |
| G5-9 | 性能 | 是 | 2500×300 单次 | **≤ 3.1s** (基线 2.76, 预期 2.72) | ✅ **2.64s** | 计时输出 |
| G5-10 | 固定阶数兼容性 | 是 | 探针 T=100/N=3 | `fit` 系数逐值相同; warm-up 段差异 ≤ 99/300 格; 冻结段 0 差异 | ✅ coef_identical=True; 99/96/93 格; max 2.694613/5.251495/5.973263; first=7/8/9; last=39 (冻结段无差异) | 探针输出 |

**说明**: G5-4/G5-5 允许 ±5% 格数、`max_abs` ±0.02 的环境浮动; 超出则检查是否误改 `transform`。G5-10 的 warm-up 差异是**已知且有意**的 (守卫时点平移), 不作为失败。

---

## Gate 6: 文档

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G6-1 | 实施文档 §7.2 回填 | 是 | 对照本文档 Gate 1–5 | 实测值全部回填, 无 `⏳` | ✅ 已回填 | 文档 |
| G6-2 | checklist 回填 | 是 | 本文件 "实际" 列 | Gate 0–7 全部填写 | ✅ Gate 0–7 已填 | 本文件 |
| G6-3 | README | 是 | L1029/L1032/L1035/L1059 | 版本 3.3.7; 测试基线; 历史追加 | ✅ 4 处已更新 + v3.3.7 历史行 | 文档 |
| G6-4 | PROJECT_STATUS | 是 | 版本路标 / 执行历史 / P1 | 对齐 v3.3.7 | ✅ 路标/完成链/P1/当前标记均对齐 | 文档 |
| G6-5 | DEV_PROGRESS | 是 | §4 待办 / 文档索引 | PL-08 完成; 索引含 v3.3.7 | ✅ §4 勾选 + 索引首行 | 文档 |
| G6-6 | ARCHITECTURE | 是 | L17 / L20 | 因果性描述追加 hold_back; 基线追加 v3.3.7 | ✅ L17/L20 已更新 | 文档 |
| G6-7 | 调研/设计状态 | 是 | 两份文档头部 | 调研 v1.2 / 设计 v1.2 (步骤 8 勘误后), 状态与实际一致 | ✅ v1.2 / v1.2 | 文档 |
| G6-8 | 无过期数字 | 是 | `git grep -n "3.3.6"` 版本锚点 | 0 命中 (历史表除外) | ✅ 版本文件 0 命中; 历史叙述保留于 CHANGELOG/版本历史 | grep |

---

## Gate 7: 最终交付

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G7-1 | 变更范围 | 是 | `git diff --stat` | 生产代码仅 `ar_model.py`; 新增 1 测试文件; 版本/文档按清单 | ✅ 14 文件修改 + 1 新测试文件; 生产代码仅 `ar_model.py` (**+25/−11**, 含 docstring) | diff |
| G7-2 | 无意外文件 | 是 | `git status --short` | 无临时探针/缓存/截图混入 | ✅ 探针在 `%TEMP%`; 工作树仅代码/测试/版本/文档 | status |
| G7-3 | V12 grep | 是 | `git grep -n "y\[order" -- modules/factor_decoupler/core/ar_model.py` | **0 命中** | ✅ 0 命中 | grep |
| G7-4 | 白名单 | 是 | `git grep -n "y\[order" -- modules/` | 仅 `optimized.py` L221-L222 | ✅ 仅 optimized.py L221-L222 | grep |
| G7-5 | 无 xfail/skip | 是 | `git grep -n "xfail\|skip" -- tests/unit/test_ar_order_holdback.py` | 0 命中 | ✅ 0 命中 | grep |
| G7-6 | 缓存失效 | 是 | 版本/缓存代际 | `v2.2.5-cache`; 旧缓存不可复用 (需重建) | ✅ 6 处字面量均为 `v2.2.5-cache` (stub 核验); 旧缓存 miss | 探针/文档 |
| G7-7 | 原子提交 | 否 | 用户指令 | 单提交含代码+测试+版本+文档 | ⏸ 未执行 (用户未要求提交) | — |

---

## §1 验收签署

| 角色 | 结论 | 日期 | 依据 |
|------|------|------|------|
| 实施 | ✅ 通过 (1 项条件项: G4-3 隔离运行受 duckdb 影响, 合并运行为 7 passed) | 2026-11-04 | Gate 0–7 |
| 审计 (步骤 10) | ✅ **PASS** (无 P0/P1/P2; F-B2 已修复闭环; F-B1/F-B3/F-B4 记录性) | 2026-11-05 | [2026-11-04-code-quality-audit.md](2026-11-04-code-quality-audit.md) v1.2 续篇 |

**通过条件**: Gate 0–7 所有 "必须" 项为通过; 若有条件通过, 必须在备注中列出未闭环项与责任人。
**已知环境例外**: `test_E10_bridge_init_params_exist` 因 `duckdb` 未安装失败; 基线与实施后均存在, 不计入 PL-08 验收。

---

## §2 附: 失败模式速查

| 现象 | 最可能原因 | 处置 |
|------|-----------|------|
| T1 失败 (`n_obs` 不等) | `hold_back` 未生效 / 仍用 `y[order:]` | 检查 `_fit_ar` 的 `y_trimmed` 与滞后列 |
| T2 失败 | 样本构造或 `n_obs` 口径错 | 对齐 statsmodels `y[hold_back:]` / `x[hold_back:]` |
| T3 失败 (未抛错) | 守卫缺失或文案不匹配 | 检查 `n_obs <= order+5` 与 `'有效样本不足'` |
| T4 失败 | 索引仍从 `order` 开始 | 改为 `series.index[hold_back:]` |
| T5–T7 失败 | 选阶仍被系统性抬高 | 确认所有阶数 `n_obs` 相同; 检查是否误改 `_fit_best` |
| T8 失败 | 固定阶数不再等价 | 检查 `H = max_order`; 固定阶数时 `H=p` |
| T9 失败 | 守卫未覆盖 warm-up / 早期仍拟合 | 检查 `_fit_ar` 守卫与 `transform` 的短前缀调用 |
| T10 失败 | `transform` 被误改 | 本任务不应改 `transform`; 回滚该文件 |
| 靶向套件新增失败 | 行为变更传导 (阶数/索引) | 逐项定位; 不得放宽断言 |
| `test_fix3` 失败 | 版本/缓存字面量漏改 | 按 §5.1/§5.2 清单补齐 |
| 性能 > 3.1s | 矩阵/循环意外扩大 | 检查是否引入额外 OLS 或全样本构造 |
| 输出偏移超 ±5% | 误改 `transform` / 选阶逻辑 | 回滚非 `_fit_ar` 改动, 重跑 |

---

**Checklist 完成**: 2026-11-04 (v1.1, 步骤 8 一致性 review 通过); 步骤 9 TDD 实现后 Gate 0–7 已回填; 步骤 10 审计 **PASS** (2026-11-05, 见 `2026-11-04-code-quality-audit.md` v1.2 续篇)。
