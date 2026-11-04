# v3.3.6 PL-05 Dynamic AR 因果性修复 — 审查验收 Checklist

**版本**: v1.2 (步骤 9 TDD 完成后回填"实际"列; v1.1 为步骤 8 一致性 review 修订)
**日期**: 2026-11-04
**缺陷**: DEFECT-PL-05
**实施文档**: [EXECUTION_V3.3.6_PL05_DYNAMIC_AR_CAUSALITY.md](../EXECUTION_V3.3.6_PL05_DYNAMIC_AR_CAUSALITY.md) v1.3
**设计文档**: [analysis/PL05_DYNAMIC_AR_LOOKAHEAD_DESIGN.md](../analysis/PL05_DYNAMIC_AR_LOOKAHEAD_DESIGN.md) v1.2 (B'' 选定)
**调研文档**: [analysis/PL05_DYNAMIC_AR_LOOKAHEAD_RESEARCH.md](../analysis/PL05_DYNAMIC_AR_LOOKAHEAD_RESEARCH.md) v1.4
**生成时机**: spec 步骤 7 (实施文档 review 通过后, TDD 实现前)
**判定规则**: 任一 "必须" 项未通过 → 本阶段不通过; **允许的 known-xfail = 0** (PL-05 与 PL-07 均须摘除)。
**例外路径**: 若某 `(seed, kind)` 的顶层路由在截断后不一致 → 该 seed 移出参数化, 并登记 PL-07 (需在 §1 签署区说明); 不得静默 skip 或改断言。

> 位置说明: 本工件按 WORKFLOW_METHODOLOGY v1.3 §13.7 放在 `docs/audit/`。

---

## §0 使用方式

1. 按 Gate 顺序执行; 每项填写 `实际` 与 `证据`; **未实测的数字不得填入结论**。
2. 命令统一在 `F:\Coding\factor_pipeline` 下运行, 解释器为
   `C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe`。
3. 行号仅作导航, 以类名 / 函数名 / 测试名为准 (编辑后会漂移)。
4. 本 checklist 是步骤 10 审计的输入基准; 实施后逐项对照勾选。
5. 任一 Gate 失败即停止后续 Gate, 先修复再重跑本 Gate。
6. **Gate 0 的基线数值已于 2026-11-04 在本会话实测**; 实施开始时须复跑确认 (若他人已提交新变更, 以复跑为准)。
7. 仓库根 = `F:\Coding\factor_pipeline` (包根即仓库根); 命令按仓库根相对路径执行; `git grep` 只搜已跟踪文件。

---

## Gate 0: 前置与基线

| # | 检查项 | 必须 | 命令 / 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------------|------|------|------|
| G0-1 | 解释器可用 | 是 | `python.exe -m pytest --version` | pytest 可用 | ✅ 可用 (3.12.10) | 命令输出 |
| G0-2 | 运行时与库版本 | 是 | `python.exe -c "import sys,pandas,numpy; ..."` | Python 3.12.x; pandas ≥2.2 (`freq='ME'`); numpy ≥1.22 | ✅ 3.12.10 / pandas 2.2.3 / numpy 2.4.6 | 命令输出 |
| G0-3 | 工作树状态已知 | 是 | `git status --short` | 仅 PL-05 文档未提交 (research/design/execution/checklist/consistency review); 生产代码未改 | ✅ 实施前 5 份文档未提交、生产代码未改; 实施后另含 ar_model + 2 测试 + 版本/ADR/CHANGELOG | `git status` |
| G0-4 | 基线集成 | 是 | `pytest tests/integration/test_pipeline_truncation_invariance.py -q` | **10 passed / 2 xfailed** | ✅ 10 passed / 2 xfailed (13.12s) | 输出尾部 |
| G0-5 | 基线 decoupler | 是 | `pytest tests/test_factor_decoupler -q` | 29 passed | ✅ 29 passed (2.50s) | 输出尾部 |
| G0-6 | 基线管线 | 是 | `pytest tests/test_pipelines_v2.py -q` | 13 passed | ✅ 13 passed (3.52s) | 输出尾部 |
| G0-7 | 基线版本统一 | 是 | `pytest tests/test_fix3_version_unification.py -q` | 7 passed (v3.3.5 锚点) | ✅ 7 passed (0.17s) | 输出尾部 |
| G0-8 | 基线模块开关 | 是 | `pytest tests/test_adapters/test_module_enabled.py -q` | 20 passed | ✅ 20 passed (0.54s) | 输出尾部 |
| G0-9 | 基线性能 | 是 | 临时探针, 2500×300, AR 3 次 / 管线 1 次 | AR 0.48s; Dynamic 33.19s | ✅ AR 0.48s (0.48/0.49); 管线 33.19s | 探针输出 |
| G0-10 | PL-05 基线数值 | 是 | 集成测试精确数据集, `--runxfail` | Dynamic 1653 格 / 8 NaN / 8.045e-01 (seed=22, ar_low, t=60) | ✅ 1653 / 8 / 8.045313632310727e-01 | 调研 §1.2 / 探针 10 |
| G0-11 | PL-07 基线数值 | 是 | 同上 | 顶层 1650 格 / 1.8397 (seed=31, skewed, t=60) | ✅ 1650 / 1.8397305724759783 | 探针 10 |
| G0-12 | 路由基线 | 是 | 3 组 `(seed, kind)` 全样本 vs 截断 | 全部一致 | ✅ dynamic / dynamic / static, 三组均一致 | 探针输出 |

**失败处理**: 基线不绿 → 停止; 不得把既有失败并入本次验收。→ **未触发**

---

## Gate 1: Red — 新测试先失败

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G1-1 | 新测试文件存在 | 是 | `tests/unit/test_ar_decoupler_causality.py` | 存在, **10 个函数** (含 1 个 7 参数化) | ✅ 存在, 10 个函数 | 文件 |
| G1-2 | 用例齐备 | 是 | 对照实施文档 §4.1 | 10/10 函数名一致 | ✅ 10/10 一致 (7 参数展开 → 16 用例) | 测试文件 |
| G1-3 | Red 计数 | 是 | `pytest <file> -q` (v3.3.5 旧实现) | **14 failed / 2 passed** (16 用例; 8/10 函数失败) — 步骤 8 预测 | ✅ **15 failed / 1 passed** (0.44s; 9/10 函数失败; 偏差已回注 EXECUTION §4.1) | Red 输出 |
| G1-4 | 失败机理正确 | 是 | 核对失败原因 | 6 个函数 `TypeError` + 2 个函数断言失败 + 2 个通过 — 步骤 8 预测 | ✅ 7 个函数 `TypeError` (multi_cut 展开 7 例 → 13 用例) + 2 个断言失败; 第 7 个是 `metadata_preserved` (预测偏差) | Red 输出 |
| G1-5 | 通过项符合预期 | 是 | 同上 | `test_strength_soft_mix` / `test_metadata_preserved` | ✅ 仅 `test_strength_soft_mix` (metadata 因传 `warmup_obs=40` 在未实现前 TypeError) | Red 输出 |
| G1-6 | 未用 xfail 掩盖 | 是 | 检查装饰器 | 新文件无 `xfail` / `skip` | ✅ 无 | 源码 |
| G1-7 | 断言非恒真式 | 是 | 人工核对 | 手算对照用独立算式; N4 构造有效观测 `min_order+2 ≤ m < min_obs`; mock spy 断言 `max(lengths) ≤ 40` 且 `min < 40` | ✅ 符合 (手算/index/NaN 模式/调用长度) | 源码 |

**失败处理**: 若未实现前 >2 例通过 → 该例未命中契约, 必须加严断言; 不得用 `xfail` 掩盖。→ **未触发** (仅 1 例通过)

---

## Gate 2: Green — 单元测试

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G2-1 | `fit` 只读前缀 | 是 | `test_fit_uses_only_prefix` | 改变 K 之后数据, `_results` 的 order/coeff 不变 | ✅ passed | 单测 |
| G2-2 | 多截断点不变式 | 是 | `test_truncation_invariant_multi_cut` (t=10/15/25/30/45/60/80) | 7 参数全部 0 差, NaN 模式一致 | ✅ 7 参数全 passed | 单测 |
| G2-3 | 一步预测公式 | 是 | `test_one_step_prediction_matches_hand_calc` | 冻结期 `res == series - (c0+Σc_i·y_{t-i})` | ✅ passed | 单测 |
| G2-4 | 冷启动 identity | 是 | `test_cold_start_is_identity` | `t<7` 输出 == 输入 | ✅ passed | 单测 |
| G2-5 | 不新增 NaN | 是 | `test_fitted_columns_add_no_nan` | 无 NaN 输入 → 无 NaN 输出 | ✅ passed | 单测 |
| G2-6 | 列门控已移除 | 是 | `test_missing_results_column_not_blanket_identity` | `t=12` 解耦; `t≥40` identity | ✅ passed | 单测 |
| G2-7 | 参数校验 | 是 | `test_warmup_must_exceed_min_obs` | `ValueError` 匹配 `warmup_obs` | ✅ passed | 单测 |
| G2-8 | 软混合语义 | 是 | `test_strength_soft_mix` | `out(0.5) == 0.5·series + 0.5·out(1.0)` | ✅ passed | 单测 |
| G2-9 | 拟合只用前缀 | 是 | `test_warmup_refit_uses_only_prefix` | mock 记录长度: `max ≤ 40`, `min < 40` | ✅ passed | 单测 |
| G2-10 | 元数据保留 | 是 | `test_metadata_preserved` | index / columns 一致 | ✅ passed | 单测 |
| G2-11 | 文件全绿 | 是 | `pytest <file> -q` | **16 passed** (10 个函数) | ✅ 16 passed (0.38s) | 输出尾部 |

---

## Gate 3: 集成 — 截断不变式

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G3-1 | PL-05 `xfail` 已移除 | 是 | `test_dynamic_pipeline_is_truncation_invariant` 装饰器 | 无 `xfail` | ✅ 已移除 | 源码 |
| G3-2 | PL-07 `xfail` 已移除 | 是 | `test_v2_pipeline_is_truncation_invariant` 装饰器 | 无 `xfail`; 内部 routes 断言已移除 | ✅ 已移除 | 源码 |
| G3-3 | Dynamic 端到端 | 是 | `pytest <integration> -q` | **0 格 / 0 NaN / 0** | ✅ 0 / 0 / 0 | 输出 / 诊断表 |
| G3-4 | 顶层端到端 | 是 | 同上 | **0 / 0 / 0** | ✅ 0 / 0 / 0 | 输出 |
| G3-5 | 路由因果性 | 是 | `test_v2_pipeline_routing_is_causal` | 3 参数全 passed; `routes_full == routes_trunc` | ✅ 3 参数全 passed | 输出 |
| G3-6 | 套件计数 | 是 | 同上 | **15 passed / 0 xfailed**, 0 xpassed | ✅ 15 passed / 0 xfailed (16.82s) | 输出尾部 |
| G3-7 | 缺陷登记表 | 是 | 模块 docstring | 移除 PL-05/PL-07; "已修复" 追加两条; 备注 PL-08-candidate 未登记 | ✅ 已更新 | diff |
| G3-8 | 诊断报告 | 是 | `pytest <integration> -q -s` | Dynamic 行 PASS 0/0/0; Static/Mixed 仍 PASS; 违反项 1→0 | ✅ 0 违反 / 9 满足 | 诊断表 |
| G3-9 | `T=60` 软解耦强度 | 是 | `test_soft_decoupling_strength` | passed (strength 1.0 ≠ 0.5 的中间方差) | ✅ passed | 输出 |
| G3-10 | 信息损失诊断 | 是 | `test_information_loss_signal_lost` | `interpretation == 'signal_lost'` (两段 warm-up 生效) | ✅ passed, `signal_lost` | 输出 |
| G3-11 | 其他管线未退化 | 是 | 诊断表 | Static 0/0; Mixed 0/0 (PL-06 修复保持不变) | ✅ Static/Mixed 均 PASS 0/0 | 诊断表 |

**若某 seed 路由不一致**: 该 seed 移出参数化并登记 PL-07; 其余 seed 仍需通过。→ **未触发** (3 组均一致)

**诊断矩阵期望 (实施后)**:

```
pipeline   Static                   PASS          0       0    0.000e+00  -
pipeline   Dynamic                  PASS          0       0    0.000e+00  -
pipeline   Mixed                    PASS          0       0    0.000e+00  -
违反不变式 0 项 / 满足 9 项 / 合计 9 项   (实施前为 1 / 8 / 9: 仅 Dynamic FAIL, Static/Mixed PASS)
```

---

## Gate 4: 回归靶向

```powershell
C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe -m pytest `
  tests/unit/test_ar_decoupler_causality.py `
  tests/integration/test_pipeline_truncation_invariance.py `
  tests/test_factor_decoupler `
  tests/test_pipelines_v2.py `
  tests/test_adapters/test_module_enabled.py `
  tests/test_endogeneity_regularizer `
  tests/test_fix3_version_unification.py -q
```

| # | 检查项 | 必须 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|
| G4-1 | 靶向全绿 | 是 | 0 failed | ✅ 110 passed / 0 failed (35.25s, 6 套件; 版本 bump 后合并复跑含 fix3 = **117 passed**, 29.57s) | 输出尾部 |
| G4-2 | 新单测 16 passed (10 函数) | 是 | 与 G2-11 一致 | ✅ 16 passed | 输出 |
| G4-3 | 集成 15 passed / 0 xfailed | 是 | 与 G3-6 一致 | ✅ 15 passed / 0 xfailed | 输出 |
| G4-4 | decoupler 29 passed | 是 | 含 2 处容差/区间修改 | ✅ 29 passed (2.77s) | 输出 |
| G4-5 | 管线 13 passed | 是 | 含 `T=60` 两个 Dynamic 用例 | ✅ 13 passed | 输出 |
| G4-6 | 模块开关 20 passed | 是 | 与基线同量 | ✅ 20 passed | 输出 |
| G4-7 | 内生性正则化套件 | 是 | 全 passed (诊断链不退化) | ✅ 17 passed | 输出 |
| G4-8 | 版本 7 passed | 是 | v3.3.6 锚点 | ✅ 7 passed (0.67s) | 输出 |
| G4-9 | 无 unexpected xpass | 是 | 0 | ✅ 0 (`0 xfailed`) | `-rx` |

---

## Gate 5: 性能与输出偏移

| # | 检查项 | 必须 | 方法 | 门限 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G5-1 | AR 单步耗时 | 是 | `ARDecoupler.fit_transform`, 2500×300, 3 次 min | **≤6s** (基线 0.48s; 调研预测 2.11–5.76s) | ✅ 2.10–5.23s (6 次, 中位 ≈2.24s; 单次负载离群 6.25s) | 临时脚本 |
| G5-2 | Dynamic 全管线 | 是 | `DynamicFactorPipeline.fit_transform`, 2500×300, 1 次 | **≤45s** (基线 33.19s; 预测 42.50s) | ✅ 39.29s (+18.4%) | 临时脚本 |
| G5-3 | 输出偏移 | 是 | T=100/N=30, 新旧对比 | **2851–2855 / 3000 格**; `max_abs` 2.1–4.2; `mean_abs` 0.23–0.35 | ✅ 2851–2855; 2.1038–4.1873; 0.2287–0.3486 | 临时脚本 |
| G5-4 | NaN | 是 | 同上 | **146 → 0** | ✅ AR 146/149 → 0; Dynamic 145/148 → 0 | 临时脚本 |
| G5-5 | 残差白化 | 是 | AR(1) φ=0.7, T=500, N=30, 统计起点第 60 行 | `mean_ar1` ≈ 0.03 (当前样本内 ≈0, 非 OOS) | ✅ 0.0302 (旧 0.0029) | 临时脚本 |
| G5-6 | 无逐行 pandas 写入 | 是 | 代码核对 | 每列转 numpy, 一次性回写 | ✅ 符合 | 源码 |
| G5-7 | 无滞后矩阵构造 | 是 | 代码核对 | 冻结分支仅 `p` 次移位累加 | ✅ 符合 | 源码 |
| G5-8 | 无临时脚本入库 | 是 | `git status --short` | 无 probe/bench 文件 | ✅ 探针仅在 `%TEMP%` | `git status` |

---

## Gate 6: 版本与缓存

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G6-1 | pyproject | 是 | L7 | `3.3.6` | ✅ 3.3.6 | 文件 |
| G6-2 | `__version__` | 是 | `__init__.py` L58 | `3.3.6` | ✅ 3.3.6 | 文件 |
| G6-3 | config_v2 | 是 | L371 | `3.3.6` | ✅ 3.3.6 | 文件 |
| G6-4 | reporting | 是 | L40 | `3.3.6` | ✅ 3.3.6 | 文件 |
| G6-5 | test_fix3 锚点 | 是 | L32 `EXPECTED_VERSION` + L12/L39/L47/L56 docstring | `3.3.6` (无残留 3.3.5) | ✅ 已全部更新 | 文件 |
| G6-6 | verify_fix3_manual 锚点 | 是 | L5 注释 / L21 | `3.3.6` | ✅ 3.3.6 | 文件 |
| G6-7 | 版本套件 | 是 | `pytest tests/test_fix3_version_unification.py -q` | 7 passed | ✅ 7 passed (0.67s) | 输出 |
| G6-8 | 缓存常量 | 是 | `cache_manager.py` L58 | `v2.2.4-cache` | ✅ v2.2.4-cache | 文件 |
| G6-9 | 缓存字面量分布 | 是 | `git grep -n "v2.2.3-cache" -- '*.py'` | 仅 `test_fix3` L84 (PL-06 历史) + 新增 L85 (PL-05 历史); 其余 0 命中 | ✅ 命中仅 2 行 (grep 见 §7.2 证据) | grep |
| G6-10 | 4 个 cache 类零改动 | 是 | `git diff -- backtest/cached_data_loader.py backtest/factor_cache.py backtest/price_cache.py backtest/fwd_returns_cache.py` | **diff 为空** (默认值引用 `CODE_VERSION`) | ✅ diff 为空 | `git diff` |
| G6-11 | 5 个类默认值一致 | 是 | `test_07` | passed | ✅ passed | 输出 |
| G6-12 | 手工校验脚本 | 是 | `python tests/test_backtest/verify_fix3_manual.py` | 全部 PASS; 缓存 ≠ 项目版本 | ✅ 5/5 PASS; 缓存 v2.2.4-cache ≠ 3.3.6 | 输出 |
| G6-13 | 子包版本未误改 | 是 | `git diff -- modules` | 无 `__version__` 变更 | ✅ 仅 ar_model.py 变更, 无版本字段 | `git diff` |
| G6-14 | 缓存代际失效 | 是 | `pytest tests/test_backtest/test_cache_manager.py::TestCodeVersionGeneration -q` | 旧代 MISS + 自愈删除 passed | ✅ passed (与 fix3 合计 10 passed) | 输出 |

---

## Gate 7: 文档

| # | 检查项 | 必须 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|
| G7-1 | ADR-040 已写入 | 是 | 背景 / 决策 / 备选 / 实测 / 契约 / 不覆盖 / 后果 / 依据 / 回滚 齐备 | ✅ 9 节齐备 | `DECISIONS.md` |
| G7-2 | ADR 状态 | 是 | 实施后为 "已实施" (步骤 9 完成时更新) | ✅ 已实施 | `DECISIONS.md` |
| G7-3 | ADR 占用表 | 是 | `ADR-040` 已占用; `ADR-041 起` 未占用 | ✅ 已登记 | `DECISIONS.md` |
| G7-4 | ADR 数值已回填 | 是 | 无 "待实测"; 数值与 G3/G5 一致 | ✅ 无 "待实测" | grep |
| G7-5 | CHANGELOG v3.3.6 | 是 | 根因 / 方案 / 实测矩阵 / 兼容性 / 遗留 / NaN 语义变更 | ✅ 齐备 | `CHANGELOG.md` |
| G7-6 | ARCHITECTURE | 是 | 追加 v3.3.6 + Dynamic AR 因果三段式描述 | ✅ 已追加 | `docs/ARCHITECTURE.md` |
| G7-7 | DEV_PROGRESS | 是 | 追加 v3.3.6 行并移动 "当前" 箭头 | ✅ 已追加 | `docs/DEV_PROGRESS.md` |
| G7-8 | 设计文档状态 | 是 | 头部标注 "已实施 (v3.3.6)" + 指向实施文档 | ✅ 已标注 | DESIGN 头部 |
| G7-9 | 调研文档状态 | 是 | 头部标注已实施 + 实测链接 | ✅ 已标注 | RESEARCH 头部 |
| G7-10 | 实施文档 §7.2 回填 | 是 | 全部"待回填"替换为实测值; 升 v1.3+ | ✅ 已回填, 升 v1.3 | EXECUTION §7.2 |
| G7-11 | 无未实测数字写成结论 | 是 | 抽查 CHANGELOG / ADR / 实施文档 | ✅ 抽查无占位 | 人工核对 |

---

## Gate 8: 最终交付

| # | 检查项 | 必须 | 方法 | 期望 | 实际 |
|---|--------|------|------|------|------|
| G8-1 | `git diff --check` | 是 | 命令 | 本次文件范围无 whitespace error | ✅ 无输出 | 命令 |
| G8-2 | 无临时/调试文件 | 是 | `git status --short` | 无 probe / test_results 新增 | ✅ 无 | `git status` |
| G8-3 | 变更范围 | 是 | `git diff --stat` | 仅实施文档 §2.2 列出的 15 个文件 + §5.6 的 2 份上游文档头部 | ✅ 14 modified + 6 new (§2.2 的 15 文件 + 5 份 PL-05 工件; 无额外改动) | 命令 |
| G8-4 | `fitted_values.reindex` 清零 | 是 | `git grep -n "fitted_values\.reindex" -- '*.py'` | 0 命中 | ✅ 0 命中 | grep |
| G8-5 | `warmup_obs` 作用域 | 是 | `git grep -n "warmup_obs" -- modules/` | 仅 `ar_model.py` (测试文件另含引用) | ✅ 仅 ar_model.py | grep |
| G8-6 | `_WARMUP_REFIT_STRIDE` 作用域 | 是 | `git grep -n "_WARMUP_REFIT_STRIDE" -- modules/` | 仅 `ar_model.py` | ✅ 仅 ar_model.py | grep |
| G8-7 | 回滚方案可用 | 是 | 文档 | 实施文档 §8.2 与 ADR-040 回滚段存在且可执行 | ✅ 两处均存在 | 文档 |
| G8-8 | 已知遗留已登记 | 是 | CHANGELOG / ADR | `OptimizedARDecoupler` / `TemporalDecoupler` / `PL-08-candidate` / 非因果标准化方法 | ✅ 已登记 | 文档 |

---

## §1 验收签署

| 角色 | 结论 | 日期 | 备注 |
|------|------|------|------|
| 实施 | 完成 (Gate 0-8 全通过) | 2026-11-04 | Gate 0-8; 见 §7.2 实测值 |
| 审查 | 完成 (**PASS**) | 2026-11-04 | 步骤 10 审计: [2026-11-04-code-quality-audit.md](2026-11-04-code-quality-audit.md) 续篇 (1 P2 + 1 P3 文档项已修复闭环, 3 项记录性遗留) |
| 最终验收 | 待用户签署 | | 建议重点复核: Dynamic/顶层 0/0/0、输出偏移区间、AR 性能 2.10–5.23s、缓存一次性失效 |

**通过条件**: Gate 0-8 所有 "必须" 项为通过; 若有条件通过, 必须在备注中列出未闭环项与责任人。

---

## §2 附: 失败模式速查

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| Red 阶段 >2 例通过 | 断言未命中契约 (如只断言无异常) | 加严断言, 不得用 xfail |
| `TypeError: unexpected keyword 'warmup_obs'` 在 Green 后仍出现 | `__init__` 未加参数或签名为位置参数 | 核对 §3.2 签名, 追加到末尾 |
| 截断不变式 t=10/15 仍失败 | `transform` 仍以 `_results` 过滤列 | 核对 §3.4 的 `for col in data.columns` 与 `.get(col)` |
| 截断不变式 t≤K 失败 | 冻结分支被误用 (`n > warmup_obs` 判断错) | 冻结仅在 `n > warmup_obs` 时执行 |
| 手算对照失败 | 预测用了 `vals[t-i]` 之外的量 / 系数索引错位 | 核对 `coefficients=[intercept, φ_1..φ_p]` |
| 冷启动仍出现 NaN | `res` 未用 `vals.copy()` 初始化 | 核对 §3.4 首行 |
| `test_information_loss_signal_lost` 变 `ambiguous` | warm-up 起点被改为 `min_obs` (丢掉 `[early,min_obs)` 段) | 恢复两段 warm-up |
| `test_soft_decoupling_strength` 失败 | 短面板 (`T=60`) 整列 identity | 检查 warm-up 是否覆盖 `[early, min(warmup, n))` |
| φ 布局钉子失败 | 容差未放宽或 `_results` 仍为全样本 | 核对 §4.4 与 `fit` 前缀窗口 |
| 路由 XPASS (strict) | 摘 xfail 后未同步新路由测试 | 按 §4.3 拆分 |
| 性能 >6s | warm-up 未按 stride 重估 / 每列重复构造 DataFrame | 核对 `_WARMUP_REFIT_STRIDE` 与 numpy 路径 |
| 版本测试失败 | 4 处声明或 test_fix3 断言遗漏 | 逐处核对 §5.1 / §5.2 |
| 缓存仍命中旧值 | 只改注释未改 `CODE_VERSION` | 核对 `cache_manager.py` L58 |
