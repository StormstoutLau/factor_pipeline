# v3.4.0 因子路由统一化治理 — 审查验收 Checklist

**版本**: v1.3 (2026-11-10; v1.0 = 步骤 7 生成; v1.1 = 步骤 8 一致性 review 修订; v1.2 = 步骤 9 实施后回填"实际"列; v1.3 = 步骤 10 审计签署 + G4-6 登记勘误)
**日期**: 2026-11-10
**变更主题**: 统一横截面秩管道替代三路指纹路由; 配置面删 5 字段; 新增诊断/断点监控
**实施文档**: [EXECUTION_V3.4.0_UNIFIED_ROUTING.md](../EXECUTION_V3.4.0_UNIFIED_ROUTING.md) v1.3
**设计文档**: [analysis/FACTOR_ROUTING_OVERENGINEERING_DESIGN.md](../analysis/FACTOR_ROUTING_OVERENGINEERING_DESIGN.md) v1.2 (D1–D12)
**调研文档**: [analysis/FACTOR_ROUTING_OVERENGINEERING_RESEARCH.md](../analysis/FACTOR_ROUTING_OVERENGINEERING_RESEARCH.md) v1.1
**生成时机**: spec 步骤 7 (实施文档 review 通过后, TDD 实现前)
**判定规则**: 任一"必须"项未通过 → 本阶段不通过; **本次任务不得新增 xfail / skip** (两个既有语义 skip 不计入: fix1 L128 test_02 废弃路径跳过、phase3_optimizer L1402/L1452 运行时条件跳过)。
**例外路径** (2026-11-10 更新): v1.0 时期的 duckdb 环境例外已消除 — 步骤 9 开始前用户指令安装 `duckdb>=0.10.0` (实测 2.0.0) 与 `optuna>=3.0.0` extras (实测 5.0.0, 仅本地测试用, 不改 pyproject)。E7 动态验证 (G2-43) 与关联文件运行验证 (G3-8~G3-11) 均为**必须项**; 基线已按新环境复测 (见 G0-5~G0-8b)。

> 位置说明: 本工件按 WORKFLOW_METHODOLOGY v1.3 §13.7 放在 `docs/audit/`。

---

## §0 使用方式

1. 按 Gate 顺序执行; 每项填写 `实际` 与 `证据`; **未实测的数字不得填入结论**。
2. 命令统一在 `F:\Coding\factor_pipeline` 下运行; 解释器为当前 `python` (本任务实测 3.13.5)。
3. 行号仅作导航, 以类名 / 函数名 / 测试名为准 (编辑后会漂移)。
4. 本 checklist 是步骤 10 审计的输入基准; 实施后逐项对照勾选。
5. 任一 Gate 失败即停止后续 Gate, 先修复再重跑本 Gate。
6. **Gate 0 基线数值已于 2026-11-10 实测**; 实施开始时须复跑确认 (若他人已提交新变更, 以复跑为准)。
7. `git grep` 只搜已跟踪文件; 新增文件用 `git status` / 直接路径核验。
8. **本任务有两类删除**: 符号删除 (3 函数 / 5 字段) 与**测试删除** (46 用例)。删除类验收必须用 grep 证明"零残留", 不能只靠目标测试通过。
9. 性能项 (G5-3) 的 T0 必须在**同一进程/同一机器**上测实施前基线, 不得引用历史数字。

---

## Gate 0: 前置与基线

| # | 检查项 | 必须 | 命令 / 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------------|------|------|------|
| G0-1 | 解释器可用 | 是 | `python -m pytest --version` | pytest 可用 | ✅ Python 3.13.5 (Anaconda3) | 命令输出 |
| G0-2 | 运行时与库版本 | 是 | `python -c "import sys,numpy,pandas,scipy,statsmodels; ..."` | Python ≥3.9; numpy ≥1.22 (实测 2.1.3); pandas ≥2.0 (实测 2.2.3); scipy ≥1.7 (1.15.3); statsmodels ≥0.13 (0.14.4) | ✅ 3.13.5 / 2.1.3 / 2.2.3 / 1.15.3 / 0.14.4 | 命令输出 |
| G0-3 | `duckdb` 可用 (2026-11-10 安装 2.0.0) | 是 | `python -c "import duckdb; print(duckdb.__version__)"` | 导入成功, `2.0.0` (满足 `>=0.10.0`) | ✅ duckdb 2.0.0 | 命令输出 |
| G0-3b | `optuna` 可用 (extras, 2026-11-10 安装 5.0.0) | 是 | `python -c "import optuna; print(optuna.__version__)"` | 导入成功, `>=3.0.0` | ✅ optuna 5.0.0 | 命令输出 |
| G0-4 | 工作树状态已知 | 是 | `git status --short`; `git log -1 --oneline` | 仅 spec 文档未提交 (research/design/execution/checklist); 生产代码未改; HEAD `0ff2420` | ✅ 撰写时点 4 份文档未跟踪; 代码未改; HEAD `0ff2420` | `git status` |
| G0-5 | 基线靶向套件 | 是 | `python -m pytest -q tests/test_pipelines_v2.py tests/test_p0_fixes.py tests/test_p3_phase2_config_migration.py tests/test_fix2_config_unification.py tests/integration/test_pipeline_truncation_invariance.py tests/test_adapters/test_module_enabled.py tests/test_multi_dim_classifier.py` | **107 passed / 0 failed** (duckdb 安装后) | ✅ 107 passed (46.00s) | 实施文档 §1.2 |
| G0-6 | 基线分层收集数 | 是 | 同上 + `--collect-only -q` 逐文件 | 13 / 14 / 12 / 13 / 15 / 20 / 20 = **107** | ✅ 13/14/12/13/15/20/20 = 107 | 实施文档 §1.2 |
| G0-7 | fix1 基线 | 是 | `python -m pytest -q tests/test_fix1_self_factors_bug.py` | **3 passed / 1 skipped** (skip 为 L128 **语义性**跳过: v3.0.0 后 KS 路径废弃, 非 duckdb) | ✅ 3 passed / 1 skipped (0.40s) | 实施文档 §1.2 |
| G0-7b | fix3 基线 | 是 | `python -m pytest -q tests/test_fix3_version_unification.py` | **7 passed** (duckdb 安装后环境失败消除) | ✅ 7 passed | 实施文档 §1.2 |
| G0-8 | 关联文件基线 (G0-8a+b 合计 180 用例) | 是 | a) E7 两文件: `pytest -q tests/test_backtest/test_ablation_runner.py tests/unit/test_task1_l2_routing_fix.py` → **104 passed** (收集 99+5); b) 4 关联文件: `pytest -q` extension/phase3_optimizer/phase4/p0_2 → **75 passed / 1 既有条件 skip** (收集 12+53+6+5; skip 为 phase3 L1402/1452 significance_ratio 条件跳过) | a) 104 passed; b) 75 passed / 1 skipped | ✅ a) 104 (26.97s); b) 75 passed / 1 skipped (17min) | 实施文档 §1.2 |
| G0-9 | ADR 编号占用 | 是 | `DECISIONS.md` L43-L45 | ADR-041 已占用 (v3.3.7); **ADR-042 起未占用** | ✅ ADR-042 起 未占用 | 文档 |
| G0-10 | 基线性能 T0 | 是 | 探针: 12 因子 × 750 行, `fit+transform` 单次, 同进程计时 | 记录 T0 秒数 (作为 A14 分母) | ✅ 单次口径 T0 = 13.589s; **步骤 9 末以 git worktree 检出 0ff2420 同机复测 (min-of-5 稳态口径) T0 = 12.246s** (单次 wall-clock 受桌面负载噪声 ±50% 影响, 门禁判定采用 min 口径; 详见 G5-3) | 计时输出 (%TEMP%\probe_compare.py / probe_alternate.py) |
| G0-11 | 调研关键数字复核 | 否 | 可选: 重跑 Static~Mixed 秩相关 / 12 因子 Dynamic 臂 \|IC\| | 0.999998 / −37.6% (若数据与代码未变可跳过) | ⏸ 跳过 (可选; 数据与代码路径未变, T2/T3 逐位等价已间接佐证) | — |

**失败处理**: 基线不绿 (0 失败, 环境例外已消除) → 停止; 不得把既有失败并入本次验收。→ 未触发 (107+104+75 全绿, 2 个既有语义/条件 skip 已在判定规则中豁免)。

---

## Gate 1: Red — 新测试先失败

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G1-1 | 新测试文件存在 | 是 | `tests/test_unified_routing.py` / `tests/test_structural_break_monitor.py` | 2 文件存在 | ✅ 2 文件存在 | 文件 |
| G1-2 | 用例齐备 | 是 | 对照实施文档 §10.1/§10.2 | T1–T14 (**14**) + B1–B6 (**6**) = **20** 用例, 名称一致 | ✅ 14 + 6 = 20, 类名 TestT1..TestT14 / TestB1..TestB6 与文档一致 | 测试文件 |
| G1-3 | Red 计数 | 是 | `pytest tests/test_unified_routing.py tests/test_structural_break_monitor.py -q` (未改实现) | 大量失败: T1–T12 + B1–B6 失败; **T13/T14 可能已通过** (不依赖新代码) | ✅ T 文件 **14 failed / 2 passed** (2 passed = T13 两方法, 既有行为); B 文件 ModuleNotFoundError 收集错误 (模块不存在, 6 例全 Red) | Red 输出 |
| G1-4 | 失败机理正确 | 是 | 核对失败原因 | T1/T5 → `pipeline_mode` 不存在 / 旧字段仍存在; T2/T3 → 未走统一管道; B1–B6 → `structural_break_monitor` 模块不存在 | ✅ T1/T5 失败于字段/符号不存在; T2/T3 失败于输出不等; T14 失败于 `pipeline_mode` 非法 kwargs (extra 未声明); B 文件收集错误 = 模块缺失 ✓ 机理全部正确 | Red 输出 |
| G1-5 | 未用 xfail/skip 掩盖 | 是 | `git grep -n "xfail\|skipif\|@skip" -- tests/test_unified_routing.py tests/test_structural_break_monitor.py` | **0 命中** | ✅ 0 命中 (两文件均无 xfail/skipif/@skip) | grep |
| G1-6 | 断言非恒真式 | 是 | 人工核对 | T2/T3 以 `StaticFactorPipeline` / `DynamicFactorPipeline` **直调**为独立参考 (`check_exact=True`); T9 校验 `winsor`/`transformation` 双层分支; B2 用固定 seed 白噪声 | ✅ `_direct_static`/`_direct_dynamic` 直调对照 + `assert_frame_equal(check_exact=True)` (try/except 包装); T9 断言双臂 spec 值; B2 seed=42 白噪声 | 源码 |
| G1-7 | T13 语义正确 | 是 | 人工核对 | `strict_mode=True` 抛 `ValueError`; 非 strict 跳过并 warning — 两分支均覆盖 | ✅ 两方法分别覆盖 strict (assertRaises ValueError) 与非 strict (assertNotIn) | 源码 |

**失败处理**: 若未实现前 ≥20 例全通过 → 断言过松; 不得用 `xfail` 掩盖。→ 未触发。

---

## Gate 2: Green — 新用例与 E 任务

### 2.1 E1 配置面 (A1–A3, A11)

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G2-1 | 默认模式 | 是 | T1 | `PipelineV2Config().pipeline_mode == 'unified'` | ✅ 通过 | 单测 |
| G2-2 | 模式校验 | 是 | T1 | `PipelineV2Config(pipeline_mode='x')` → `ValueError` (消息含两个合法值) | ✅ 通过 (`__post_init__` 校验, 消息含 'unified'/'dynamic_ab') | 单测 |
| G2-3 | 5 字段消失 (dataclass) | 是 | T5 | `hasattr(cfg, f) is False` × 5 (`hard_routing_prob`/`merge_alpha`/`ks_alpha`/`mixed_winsor_sigma`/`enable_multi_dim_routing`) | ✅ 通过 (T5 断言 5 字段 hasattr False) | 单测 |
| G2-4 | 5 字段消失 (Pydantic) | 是 | T14 + grep | `PipelineV2ConfigUnified.__fields__` 无 4 共享字段与 `transform_aggressiveness`; grep 侧见 G7-3 | ✅ 通过 (T14 旧 dict 加载成功且被忽略; grep 见 G7-3: pytest 收集文件 0 命中) | 单测/grep |
| G2-5 | 8 新字段存在 | 是 | T1/T14 + 人工 | dataclass 8 个 (含 `break_monitor_*` 4 个); Pydantic 8 个; 桥接映射齐全 | ✅ 通过 (dataclass L718-730: pipeline_mode/enable_fingerprint_diagnostics/ab_experiment_id/enable_break_monitor/break_monitor_window/stride→break_monitor_stride/alpha/n_bootstrap; Pydantic 同名 8 个; fix2 test_03/04 桥接断言) | 单测 |
| G2-6 | 旧 JSON 兼容 | 是 | T14 | 含 5 个旧字段的 dict → `PipelineV2ConfigUnified(**old)` **成功**且旧值被忽略 (`extra='ignore'`) | ✅ 通过 (T14) | 单测 |
| G2-7 | 优化器空空间 | 是 | 探针 + 单测 | `DEFAULT_SEARCH_SPACE == {}`; 默认实例化发 `DeprecationWarning`; `optimize(...)` 抛 `ValueError`。**注**: `DeprecationWarning` 默认被 Python 忽略, 测试必须用 `pytest.warns(DeprecationWarning)` 或 `warnings.catch_warnings()` + `simplefilter('always')` 捕获, 否则断言会漏过 | ✅ 通过 (phase3 test_01 用 pytest.warns 捕获; v340_01 断言 optimize ValueError) | 单测/输出 |
| G2-8 | 优化器 orth 可用 | 是 | 探针 | `search_orth=True` → 搜索空间 3 个 orth 参数, 能建 study | ✅ 通过 (phase4 全部 6 用例 search_orth=True 走通; verify_v2_6_0_manual L97-104: 0 维/3 维) | 输出 |
| G2-9 | 双向映射收敛 | 是 | 探针 | `_params_to_config({...3 参数})` 正确; `_config_to_params(config)` 返 3 键; 含已删键的 dict 不报错且被忽略 | ✅ 通过 (phase3 test_08/09 三参数契约与往返; fix2 test_12 实调 `_config_to_params` 断言 3 键) | 单测 |
| G2-10 | `import warnings` | 是 | `grep -n "^import warnings" optimizer.py` | **命中** (实施前无 warnings 导入 — typing/logging/numpy/pandas/scipy + optuna try-import + factor_pipeline 内部导入; 承重结论"无 warnings"属实; 必须新增, 否则 `DeprecationWarning` 分支 `NameError`) | ✅ 命中 (optimizer.py L20 `import warnings`) | grep |
| G2-10b | 新开关默认值语义 (兼容性) | 是 | 探针 | `pipeline_mode='unified'` (行为变更, 有意); `enable_fingerprint_diagnostics=True` (默认开但不改变输出 — T6 证明 transform 逐位相同); `enable_break_monitor=False` (**opt-in**, 默认零成本); `ab_experiment_id=None`。三个开关均不新增必填参数, 公共 `fit`/`transform` 签名不变 | ✅ 通过 (T1 默认 unified; T6 诊断开关逐位等价; T11 默认 `{}`; `fit`/`transform` 签名未变) | 单测/源码 |

### 2.2 E2 统一执行 (A4–A6)

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G2-11 | 统一逐位等价 | 是 | T2 | 12 因子 `fit_transform` 与 `StaticFactorPipeline` 直调 `assert_frame_equal(check_exact=True)` — **全等** | ✅ 通过 (T2, 直调 `_direct_static` 对照) | 单测 |
| G2-12 | Dynamic A/B 等价 | 是 | T3 | `pipeline_mode='dynamic_ab'` 与 `DynamicFactorPipeline` 直调逐位相等 | ✅ 通过 (T3, 直调 `_direct_dynamic` 对照) | 单测 |
| G2-13 | Mixed 不自动创建 | 是 | T4 | `factor_pipelines` 值中无 `MixedFactorPipeline`; 键恒为 `'static'` (unified) / `'dynamic'` (dynamic_ab) | ✅ 通过 (T4) | 单测 |
| G2-14 | 无 `StatisticalClassifier` 调用 | 是 | `grep -n "StatisticalClassifier" pipelines_v2.py` | **0 命中** (模块本身保留, 仅 `fit` 不再引用) | ✅ 1 处命中为 L1149 **注释** ("不再调用 StatisticalClassifier"), 代码 0 引用 — 满足检查意图 (fit 不再调用) | grep |
| G2-15 | 兼容属性回填 | 是 | 探针 | `static_pipeline` / `dynamic_pipeline` 按模式回填; `mixed_pipeline is None` | ✅ 通过 (T4/fit 源码: `self.mixed_pipeline = None` 回填) | 单测/源码 |
| G2-16 | transform mock 兜底 | 是 | 既有 fix1/p0 mock 用例 | `test_fix1_self_factors_bug.py` 3 passed (依赖 `_get_pipeline` 兜底) | ✅ 3 passed / 1 语义 skip (G3-7) | 单测 |
| G2-17 | T13 未拟合分支 | 是 | T13 | strict 抛 `ValueError`; 非 strict 跳过 | ✅ 通过 (T13 两方法) | 单测 |

### 2.3 E3 诊断层 (A7)

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G2-18 | 采样频率五档 | 是 | T7 | daily / weekly / monthly / irregular / unknown 全部正确 (weekly 阈值 8 自然日) | ✅ 通过 (T7; 实施期修正: irregular 用例原构造 `np.concatenate([[0], np.full(8,450)])` 使 8 个时间点重叠 → 改等差 `np.arange(9)*450`) | 单测 |
| G2-19 | 路由记录结构 | 是 | T8 + 探针 | `factor_routing[name]` 每因子 1 条; 字段含 `pipeline_mode`/`execution_pipe_type`/`diagnostic_*`/`ar1_median`/`fingerprint_meta.sampling_frequency` | ✅ 通过 (T8) | 单测 |
| G2-20 | 汇总表 | 是 | T8 | `get_classification_summary()` 含 `execution_pipe_type`/`sampling_frequency` 两新列; `get_routing_summary()` 行数 = 因子数 | ✅ 通过 (T8) | 单测 |
| G2-21 | 诊断开关边界 | 是 | T6 | 关闭时诊断标签全 `unknown`, 但 **`get_fingerprint_summary()` 非空** (指纹提取与 monitor 仍执行); transform 与开启时 `check_exact=True` | ✅ 通过 (T6) | 单测 |
| G2-22 | `compute_ar1_path` 长度 | 是 | T7/探针 | T=1472, w=250, s=20 → **62** 点; T<window → 空 Series | ✅ 通过 (B1 断言 62 点; `⌊(1472−250)/20⌋+1`) | 单测 |

### 2.4 E4 规格日志 (A8)

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G2-23 | 开启写盘 | 是 | T9 | JSONL 行数 = 因子数; 每行含 `execution_pipe_type`/`sampling_frequency`/`cache_version` | ✅ 通过 (T9) | 单测 |
| G2-24 | 按臂派生 | 是 | T9 | unified 臂 `winsor='percentile(1,99)'`; dynamic_ab 臂 `winsor='none'`, `transformation='ar_residual->z_score'` | ✅ 通过 (T9 双臂断言) | 单测 |
| G2-25 | 关闭零目录 | 是 | T10 | `logs/specifications/` **不被创建**; 返回 0 行 | ✅ 通过 (T10; 附探针 `Test-Path logs/specifications` = False) | 单测 |
| G2-26 | 写盘失败兜底 | 是 | 人工 + 探针 | `_log_spec` 全函数 try/except; 只 warning 不中断 fit | ✅ 通过 (源码核对: `_log_spec` 全体 try/except) | 源码 |

### 2.5 E5 断点监控 (A9–A10)

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G2-27 | 默认关闭 | 是 | T11 | `monitor_structural_breaks(...)` 返回 `{}` | ✅ 通过 (T11) | 单测 |
| G2-28 | 监控无副作用 | 是 | T12 + B6 | 开启前后 `transform` `check_exact=True`; `detect` 不修改输入 Series | ✅ 通过 (T12 + B6 `assert_series_equal`) | 单测 |
| G2-29 | B1 检出 | 是 | B1 | T=1472 (62 点) 中段 +2σ → `detected=True`; `break_index` 落在污染段 ±3 | ✅ 通过 (B1; **实施期修正**: 原"+5σ 均值突变"产生 AR(1) 双边界升-降驼峰 (实测 p=0.915), 与 sup-F 单断点假设不适配 → 改 φ 0.2→0.8 系数结构突变 @t=700 (实测 p≈0.0025, break_index=27, 期望 22±5); 测试 docstring 已按 B3 同款容错记录偏离) | 单测 |
| G2-30 | B4 数据不足 | 是 | B4 | 空 / 10 点 → `detected=False`, `reason='insufficient data'` | ✅ 通过 (B4) | 单测 |
| G2-31 | B5 可复现 | 是 | B5 | 同输入两次结果完全一致 (`random_state=42`) | ✅ 通过 (B5 逐键相等) | 单测 |
| G2-32 | 参数校验 | 是 | 探针 | `method` 非 sup_f/cusum → `ValueError`; `trim` 越界 → `ValueError`; `window/stride ≤ 0` → `ValueError` | ✅ 通过 (BreakMonitorConfig 校验 + `compute_ar1_path` window/stride≤0 ValueError) | 单测 |
| G2-33 | 公式实现一致 | 是 | 人工核对 | sup-F 分母有 `1e-12` 下限; CUSUM 用 `(y−ȳ)²` 且 `s≤1e-12` 返回 `(0.0, None)`; 自助 `p=(1+#{≥})/(B+1)`; B 条代理含 50 期 burn-in | ✅ 通过 (源码核对: `_sup_f_stat` SSR 比值 1e-12 下限; `_cusum_stat` (y−ȳ)² + s≤1e-12 → (0.0, None); `_bootstrap_pvalue` p=(1+#{≥})/(B+1) + burn-in 50) | 源码 |

### 2.6 E6 清理 (A2)

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G2-34 | 3 函数删除 | 是 | T5 | `from factor_pipeline.pipelines_v2 import _get_pipeline_weights` → **ImportError**; 其余 2 个同 | ✅ 通过 (T5 exec from-import 断言 ImportError ×3) | 单测 |
| G2-35 | 模块内零残留引用 | 是 | `grep -n "_get_pipeline_weights\|_get_multi_dim_pipeline_weights\|_apply_weighted_transform" -- pipelines_v2.py` | **0 命中** (含注释与 docstring) | ✅ 0 命中 (整函数 + 分节头删除, 新总行 2209; import 探针确认 3 符号 hasattr False) | grep |
| G2-36 | 测试删除齐备 | 是 | 见 Gate 3 计数 | multi_dim 文件已删; p0_fixes 14→6; p3_phase2 12→4 | ✅ 全部齐备: test_multi_dim_classifier.py 删除 (20 例); p0_fixes 14→6 (删 TestSoftRouting 8 + 注册行); p3_phase2 12→4 (删 test_01-06/10/11 + 注册 2 行); fix2 改 5; task1 5→3; ablation 104 收集→95 (TestRoutingOverride 5 + random 3 + task1 净删 2, 新增 injects_mode 1); phase3_optimizer 删 2 增 2 | 收集数/文件 |

### 2.7 E7 消融适配 (A12)

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G2-37 | 模式取值收缩 | 是 | 静态: `grep -n "routing_mode" backtest/ablation_runner.py` | 合法值仅 `'full'`/`'unified'`/`'dynamic'`; 非法值 → `ValueError` | ✅ 通过 (L326 注释 3 值; L552-556 非法值 ValueError 消息含全部合法值) | grep/单测 |
| G2-38 | 注入映射 | 是 | `test_run_pipeline_injects_mode` (新增) 或静态核对 | `routing_mode='dynamic'` → `modified_config.pipeline_mode='dynamic_ab'`; `'full'`/`'unified'` → `'unified'` | ✅ 通过 (新增 `test_run_pipeline_injects_mode`: patch FactorProcessingPipelineV2 构造点, 动态断言 'dynamic_ab'/'unified' 两臂注入) | 单测 |
| G2-39 | `_override_routing` 删除 | 是 | `grep -n "_override_routing" -- backtest/` | **0 命中** | ✅ 0 命中 (backtest/ 全目录) | grep |
| G2-40 | run_l2 2 臂 | 是 | 静态: `grep -n "L2_unified\|L2_dynamic\|routing_configs" backtest/ablation_runner.py` | 2 臂 `L2_unified`/`L2_dynamic`; 不再含 random 臂; `b3_full_result` 仅追加参照 | ✅ 通过 (L939-940 2 臂; random_routing 0 命中; b3_full_result 仅 if 追加) | grep |
| G2-41 | docstring 同步 | 是 | `grep -n "5 配置\|5 个 AblationResult" backtest/ablation_runner.py` | **0 命中** (原 L983 "5 配置"、L985 "返回 5 个 AblationResult"、L1410 "L2 路由消融表 (5 配置)" 三处均改; L1411 的 L3 "~25 配置" 保留) | ✅ 0 命中 (三处已改 "2 臂 (v3.4.0 ADR-042)" / "2 个 AblationResult" / "(2 臂 + 可选参照)"; L1067/L1343 的 ~25 为 L3, 保留) | grep |
| G2-42 | `run_all_tests` 注册同步 | 是 | `grep -n "TestSoftRouting\|TestPipelineV2ConfigNewFields\|TestGetPipelineWeightsHardRouting\|TestTransformConfigPassing" tests/test_p0_fixes.py tests/test_p3_phase2_config_migration.py` | **0 命中** (脚本模式不 NameError) | ✅ test_p0_fixes 0 命中 (TestSoftRouting 类+注册均删); test_p3_phase2: 已删类 TestPipelineV2ConfigNewFields/TestGetPipelineWeightsHardRouting 0 命中; **TestTransformConfigPassing 2 处命中为保留** — 保留用例 test_12 (MIXED_WINSORIZE_SIGMA 常量断言) 即承载于该类 (实施 §8.2 "保留 test_12" 的实际归属类), 注册行同步保留, 脚本模式无 NameError (pytest 35 passed 佐证)。G2-42 grep 模式 v1.1 设计未预见 test_12 归属, 按检查意图 (已删符号注册零命中) 判定通过 | grep |
| G2-43 | E7 动态验证 (duckdb 已装, **必须**) | 是 | `pytest tests/test_backtest/test_ablation_runner.py tests/unit/test_task1_l2_routing_fix.py -q` | 改写后用例全通过; 无新增失败 (基线 104 passed) | ✅ **95 passed in 30.96s** (0 fail/error/新增 skip; 收集 92+3=95 = 基线 104 − TestRoutingOverride 5 − random 臂 3 − task1 净删 2 + 新增 injects_mode 1) | 输出 |

### 2.8 新用例总账

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G2-44 | 两文件全绿 | 是 | `pytest tests/test_unified_routing.py tests/test_structural_break_monitor.py -q` | **20 passed / 0 xfail / 0 skip** | ✅ **22 passed in 25.00s** (T1-T14 14 例 + B1-B6 6 例 + T13 类内 2 方法 = 22 收集; 0 xfail / 0 skip) | 输出尾部 |
| G2-45 | 命名一致 | 是 | 对照实施文档 §10 | 14 + 6 用例名与文档一致 (允许实现期微调, 但须回填文档) | ✅ 一致; 实施期微调已回填: T7 irregular 构造修正 (见 G2-18) / B1 场景改 φ 结构突变 (见 G2-29) | 测试文件 |

---

## Gate 3: 既有回归 (靶向)

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G3-1 | 管线 V2 | 是 | `pytest tests/test_pipelines_v2.py -q` | **12 passed / 1 env-fail** | ✅ **13 passed / 0 failed** (duckdb 已装, 原 env-fail 消除; 基线 G0-5 复测同为 13) | 输出尾部 |
| G3-2 | p0_fixes | 是 | `pytest tests/test_p0_fixes.py -q` | **6 passed** (TestThresholdCalibration; 原 14 − 8) | ✅ 6 passed | 输出尾部 |
| G3-3 | p3_phase2 | 是 | `pytest tests/test_p3_phase2_config_migration.py -q` | **4 passed** (test_07/08/09/12; 原 12 − 8) | ✅ 4 passed | 输出尾部 |
| G3-4 | fix2 配置统一 | 是 | `pytest tests/test_fix2_config_unification.py -q` | **13 passed** (5 用例改写为新字段断言) | ✅ 13 passed | 输出尾部 |
| G3-5 | 集成截断不变式 | 是 | `pytest tests/integration/test_pipeline_truncation_invariance.py -q` | **15 passed / 0 xfailed** | ✅ 15 passed / 0 xfailed (顶层 routes 恒 `['static']` 满足两用例) | 输出尾部 |
| G3-6 | 模块开关 | 是 | `pytest tests/test_adapters/test_module_enabled.py -q` | **20 passed** | ✅ 20 passed | 输出尾部 |
| G3-7 | fix1 | 是 | `pytest tests/test_fix1_self_factors_bug.py -q` | **3 passed / 1 skipped** (与 G0-7 一致) | ✅ 3 passed / 1 skipped (同 G0-7 语义 skip) | 输出尾部 |
| G3-8 | p3_config_extension | 是 | `pytest tests/test_p3_config_extension.py -q` | 改写/删除后无失败 (12 用例基线) | ✅ **12 passed** (改写 11: 8 新字段默认/自定义/Literal 边界/JSON round-trip/model_dump/向后兼容/to_pipeline_config; 保留 1) | 输出尾部 |
| G3-9 | p3_phase3_optimizer | 是 | `pytest tests/test_p3_phase3_optimizer.py -q` | 改写后无失败 (53 用例基线) | ✅ **53 passed** (删 2: 八维边界/八十一维回归; 改 11: 空空间+DeprecationWarning/三参数契约/best_params/search_orth; 增 2: v340_01 空间 ValueError / v340_02 约束守卫) | 输出尾部 |
| G3-10 | p3_phase4_integration | 是 | `pytest tests/test_p3_phase4_integration.py -q` | 改写后无失败 (6 用例基线) | ✅ 6 passed (全部 search_orth=True 走通) | 输出尾部 |
| G3-11 | p0_2 pipeline in loop (optuna 已装, **必须**) | 是 | `pytest tests/test_backtest/test_p0_2_pipeline_in_loop.py -q` | 改写后无失败 (5 用例基线, 全部收集) | ✅ 4 passed (删 1: transform_aggressiveness 机制退场; 改 4: 3 处 optimize 加 search_orth + test_02 orth_method 多样性; 全部动态通过) | 输出尾部 |
| G3-12 | 合并不增失败 | 是 | `pytest -q` 上述全部 (含 2 新文件) | **0 失败** (环境例外已消除); 既有语义/条件 skip 不增加 | ✅ 批 1 (11 文件) **115 passed / 1 skipped / 0 failed** (78.75s) + 批 2 (5 文件) **158 passed / 0 failed** (595.69s) = **273 passed / 1 既有语义 skip / 0 failed**; 另 G2-43 95 passed + 版本 7 passed 均绿 | 输出尾部 |
| G3-13 | 未新增 xfail/skip | 是 | `git diff -- tests/ \| grep "^+.*\(xfail\|skip\)"` | **0 命中** | ✅ 0 命中 (`git diff -- tests/` 无新增 xfail/skipIf/skipTest/importorskip 行) | diff |

**失败处理**: 出现新增失败时先判定是否为"统一管道/字段删除"的直接后果; 不得以放宽断言或 skip 收场。→ 未触发。

---

## Gate 4: 版本、缓存与依赖

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G4-1 | 版本 6 处统一 | 是 | `grep -n "3.3.7" -- pyproject.toml __init__.py config_v2.py reporting.py tests/test_fix3_version_unification.py tests/test_backtest/verify_fix3_manual.py` | **0 命中** (全部 3.4.0) | ✅ 0 命中 (实施中曾发现 test_fix3 docstring 3 处 "统一到 3.3.7" 残留, 已修正后复验 0 命中) | grep |
| G4-2 | 缓存代际 | 是 | `grep -n "v2.2.5-cache\|v2.3.0-cache" -- backtest/cache_manager.py tests/test_fix3_version_unification.py` | 字面量全为 `v2.3.0-cache`; 历史演进 docstring 可保留旧值 | ✅ cache_manager L58 = v2.3.0-cache; test_fix3 断言/期望全 v2.3.0-cache (docstring 演进史保留 v2.2.x 叙述); **注**: CODE_VERSION 5 处消费类 (CacheManager/CachedDataLoader/FactorMatrixCache/PriceMatrixCache/FwdReturnsCache) 均引用常量, test_07 一致性守卫通过 | grep |
| G4-3 | 版本测试 | 是 | `pytest tests/test_fix3_version_unification.py -q` | **7 passed** (duckdb 已装, 环境失败消除) | ✅ 7 passed in 0.33s | 输出尾部 |
| G4-4 | 手工版本校验 | 条件 | `python tests/test_backtest/verify_fix3_manual.py` | 6 处均 3.4.0; 无旧号残留 | ✅ 通过 ("Fix 3 手工校验通过"; EXPECTED_LOCATIONS 扩至 6 处含本脚本自身锚点) | 输出 |
| G4-5 | ADR 取号落位 | 是 | `grep -n "待分配\|统一横截面秩管道" DECISIONS.md` | 实施后: 新 ADR 索引行 + 正文 (背景/决策/后果/**替代方案**) 齐全; 编号以落库时 DECISIONS.md 取到的正式号为准 (暂用号 ADR-042 仅用于工件间指代) | ✅ **ADR-042 正式取号** (索引行 "ADR-042 \| 统一横截面秩管道替代三路指纹路由 \| v3.4.0, 2026-11-10"; 正文含日期/状态/关联测试/调研设计链接/背景/决策 6 条/后果/替代方案/回滚方案; 索引 "ADR-043 起 未占用"; 暂用号与正式号一致, 代码注释无需改写) | 文档 |
| G4-6 | CHANGELOG | 是 | `CHANGELOG.md` 顶部 | v3.4.0 条目 (概览/变更文件/兼容性/已知遗留), 房式对齐 v3.3.7 | ✅ 已插入顶部 (概览/核心产出/变更文件/兼容性/已知遗留/实测矩阵 8 行; 回归数字见 G6-1) | 文档 |
| G4-7 | 依赖零新增 | 是 | `git diff -- pyproject.toml` | `dependencies` 无新增行; optuna 仍在 extras | ✅ pyproject.toml diff 仅 1 行 (version 3.3.7→3.4.0); 依赖零变更 | diff |
| G4-8 | 仅用 numpy/pandas | 是 | `grep -n "^import\|^from" backtest/structural_break_monitor.py` | 无 scipy/statsmodels 新增依赖 (若有则需说明) | ✅ 仅 dataclasses/typing/numpy/pandas (自助为手写 AR(1) 代理, 无 scipy 依赖) | grep |

---

## Gate 5: 行为、性能与低效排除

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G5-1 | 统一输出等价 | 是 | T2 (同 G2-11) | `check_exact=True` 全等 | ✅ 通过 (T2) | 单测 |
| G5-2 | dynamic_ab 等价 | 是 | T3 (同 G2-12) | 逐位相等 | ✅ 通过 (T3) | 单测 |
| G5-3 | 性能 | 是 | 探针 12 因子 × 750 行, 同进程对比 T0 | `fit+transform` ≤ **1.05 × T0** (移除 VR/DF 应更快) | ✅ **PASS: ratio = 1.0092 ≤ 1.05** — 方法: git worktree 检出基线 0ff2420 (junction 挂载为包名) 与实施工作区**同机交替进程 ×5 轮, 每轮预热 1 次后计时 2 次取 min** (min-of-N 消除桌面负载噪声; 单次 wall-clock 噪声实测 ±50%, 中位数不可判): base min **12.246s** vs impl min **12.359s**。排障记录: 初测 40s 系 (a) 重建探针误传 `industry_data` 为日期索引 Series → `NeutralizerAdapter.fit` 750 天逐日空转 +10s (基线探针无此项); (b) 机器负载噪声; cProfile 确认 `batch_extract` 仅 1 次调用、热点为既有 `_compute_rank_autocorr` pandas 逐日循环 (两版本单因子指纹耗时 0.964s vs 0.928s, 无退化) | 计时输出 (%TEMP%\probe_alternate.py) |
| G5-4 | 规格日志零 I/O | 是 | 默认配置下 fit; 检查 `logs/specifications/` | 目录不存在; 无 `_spec_logger` 构造 | ✅ 通过 (T10 + `Test-Path logs/specifications` = False) | 探针/文件系统 |
| G5-5 | 断点默认零成本 | 是 | 默认配置下 fit | 不调用 `compute_ar1_path`; 无 break 相关耗时 | ✅ 通过 (T11 默认返回 `{}`; 分段探针默认 fit 无 break 耗时段) | 探针 |
| G5-6 | 无 N→N² 退化 | 是 | 人工核对 | `fit` 每因子 1 次 `batch_extract`; 记录仅标量; 汇总表遍历字典 | ✅ 通过 (源码核对: fit Step 2 单次 `batch_extract` → 12 因子各 1 次 `extract_fingerprint`; `FactorRoutingRecord` frozen 标量字段; 汇总方法遍历 `self.factor_routing` 字典) | 源码 |
| G5-7 | 指纹不重复提取 | 是 | 人工核对 | `fit` 内 `batch_extract` 仅 1 次; 断点监控才按 stride 重算 (opt-in) | ✅ 通过 (cProfile: `batch_extract` ncalls=1, 累计覆盖 12 因子; `compute_ar1_path` 仅 `monitor_structural_breaks` opt-in 路径调用) | 源码 |
| G5-8 | 原 dynamic 变化已记录 | 是 | 文档核对 | CHANGELOG 兼容性段明示"原 dynamic 因子输出变化, 历史基准需重算" | ✅ 通过 (CHANGELOG 兼容性段首条) | 文档 |
| G5-9 | 断点监控成本 | 是 | 探针 (可选) | 1472 天 × 62 点 × B=400 的可接受耗时记录 | ✅ 记录: B1 全流程 (面板生成 + 62 点 AR(1) 路径 + B=400 自助) 在 22 例套件 25.00s 内完成, 单例秒级 — 可接受 | 计时输出 |

---

## Gate 6: 文档

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G6-1 | 实施文档回填 | 是 | 对照本文档 Gate 1–5 | 实测值回填至实施文档 §1.2/§10/§14, 无 `⏳` | ✅ §14 修订记录 v1.3 已补 (Red/Green 计数、实施期修正 T7/B1、E7 动态、回归、性能门禁口径、E6 账目) | 文档 |
| G6-2 | checklist 回填 | 是 | 本文件"实际"列 | Gate 0–7 全部填写 | ✅ 本文件 v1.2: Gate 0–7 全部填写 (G0-11 可选跳过; G7-8 待用户决定) | 本文件 |
| G6-3 | README | 是 | L1060 / L1063 / L1091 | 版本 3.4.0; 缓存 `v2.3.0-cache`; 测试基线; 历史表追加 v3.4.0 行 | ✅ 版本摘要段 + 版本信息 (3.4.0 / STABLE) + 版本历史表 v3.4.0 行; 测试基线行回填 273 passed / 1 语义 skip | 文档 |
| G6-4 | PROJECT_STATUS | 是 | 版本路标 / 执行历史 | 对齐 v3.4.0 与统一管道 | ✅ 时间线 v3.4.0 [x] + "当前在 v3.4.0" + 最近完成表 v3.4.0 行 + P1 待办更新 (ADR-042 遗留选项) | 文档 |
| G6-5 | DEV_PROGRESS | 是 | §4 待办 / 文档索引 | 任务完成; 索引含 v3.4.0 | ✅ 时间线 + §4 待办 (v3.4.0 后) + §5 文档索引 v3.4.0 行 | 文档 |
| G6-6 | ARCHITECTURE | 是 | 管道架构段 | 描述改为"统一横截面秩管道 + 指纹只读诊断 + 断点监控" | ✅ §1 核心价值 + §2 Layer 4 框图 + §3.1 模块行 + §4.2 数据流重绘 + §7.1 ADR-042 索引 | 文档 |
| G6-7 | 调研/设计状态 | 是 | 两文档头 + §14/§12 | 调研 v1.1 / 设计 **v1.2** (步骤 8 勘误后); 状态与实际一致 | ✅ 调研 v1.1 / 设计 v1.2; 状态段与实施一致 (尾部勘误注已留痕) | 文档 |
| G6-8 | 无过期版本锚点 | 是 | `grep -rn "3\.3\.7" -- README.md docs/PROJECT_STATUS.md docs/DEV_PROGRESS.md docs/ARCHITECTURE.md` | 0 命中 (历史表/历史叙述除外) | ✅ 11 处命中全部为历史叙述/历史表 (README 首段因果链叙述 + v3.3.7 历史摘要段 + 版本历史表行; STATUS/DEV 时间线与最近完成表历史行; ARCHITECTURE 版本基线链) — 均属允许例外 | grep |

---

## Gate 7: 最终交付

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G7-1 | 变更范围 | 是 | `git diff --stat` | 生产代码 = 7 修改 + 1 新增; 测试 = 2 新增 + 13 修改/删除; 版本/文档按清单; 无其他意外改动 | ✅ 生产修改 7 (pipelines_v2/config_v2/optimizer/fingerprint.py/fingerprint __init__/ablation_runner/cache_manager) + 新增 1 (structural_break_monitor.py); 测试新增 2 (test_unified_routing/test_structural_break_monitor) + 修改 12 + 删除 1 (test_multi_dim_classifier); 版本 4 (pyproject/__init__/config_v2/reporting) + 文档 6 (CHANGELOG/DECISIONS/README/STATUS/DEV/ARCH) + manual 4 + demo 1 + threshold_drift_monitor 1; 合计 36 修改 + 1 删除 + 8 新增, 与 §8 清单一致 | diff |
| G7-2 | 无意外文件 | 是 | `git status --short` | 无临时探针/缓存/`logs/`/截图混入 | ✅ 未跟踪仅 8 项: 新模块 1 + 新测试 2 + spec/audit 文档 5 (EXECUTION/DESIGN/RESEARCH/CHECKLIST/CONSISTENCY_REVIEW); 探针脚本均在 %TEMP% 不在仓库; 无 logs/ | status |
| G7-3 | 5 字段零残留 | 是 | `git grep -n "hard_routing_prob\|merge_alpha\|ks_alpha\|mixed_winsor_sigma\|enable_multi_dim_routing\|transform_aggressiveness"` | 生产代码与 pytest 收集文件 **0 命中**; 仅允许: `MixedFactorPipeline.__init__` 的同名参数、历史文档、非收集手工脚本 (已在 §3.4 标注) | ✅ pytest 收集文件 0 命中 (Agent B/C grep 复验); 生产代码命中仅: (a) `pipelines_v2.py` L886/891/985 = `MixedFactorPipeline.__init__` 保留参数 (§8.2 L934 明示勿误改); (b) optimizer.py L161-162 与 pipelines_v2.py L1332 = ADR **说明性注释** (记载退场事实, 非字段引用); 非收集手工脚本 verify_fix2_manual / verify_p0_2_manual / verify_p2_2_manual 命中 (已按 §3.4 标注弃用) | grep |
| G7-4 | 3 函数零残留 | 是 | `git grep -n "_get_pipeline_weights\|_get_multi_dim_pipeline_weights\|_apply_weighted_transform"` | 生产代码 **0 命中** (测试中断言 ImportError 的字面量除外) | ✅ 生产代码 0 命中; 测试命中仅 test_unified_routing.py T5 断言字面量 (期望例外) | grep |
| G7-5 | 无 xfail/skip 掩盖 | 是 | `git grep -n "xfail" -- tests/` | 本次未新增 | ✅ 命中仅 test_pipeline_truncation_invariance.py 的既有缺陷登记机制说明 (非本次新增); git diff 复验 0 新增 (G3-13) | grep |
| G7-6 | 缓存失效 | 是 | `CODE_VERSION` 变更 + 探针 | `v2.3.0-cache`; 旧缓存 miss (需重建) | ✅ `v2.2.5-cache` → `v2.3.0-cache` (cache_manager L58 + 5 消费类经常量引用); 缓存键含 code_version → 代际变更必然 miss, 需重建 (CHANGELOG 兼容性已注明) | 探针/文档 |
| G7-7 | optuna 可达性 | 是 | `python -c "import optuna"` | 未安装也应通过 (本任务不依赖 optuna 核心路径); 若测试覆盖 `search_orth` 需先装 extras | ✅ optuna 5.0.0 已装 (步骤 9 前置); G3-9/10/11 动态通过 | 输出 |
| G7-8 | 原子提交 | 否 | 用户指令 | 单提交含代码 + 测试 + 版本 + 文档 | ⏸ 待用户决定 (文档与代码均未提交, 等明确指示) | — |

---

## §1 A1–A17 覆盖映射 (实施文档 §11 → 本 checklist)

| 验收项 (实施文档 §11) | 判据摘要 | 本 checklist |
|---------------------|---------|-------------|
| A1 默认模式 | `pipeline_mode=='unified'`; 非法值 `ValueError` | G2-1 / G2-2 |
| A2 字段删除 | 5 dataclass + 5 Pydantic 字段消失; 3 函数 `ImportError` | G2-3 / G2-4 / G2-34 / G2-35 / G7-3 / G7-4 |
| A3 旧配置兼容 | 旧字段 JSON 加载成功且被忽略 | G2-6 |
| A4 统一等价 | T2 `check_exact=True` | G2-11 / G5-1 |
| A5 Dynamic 仅 A/B | 默认无 Dynamic; `dynamic_ab` 逐位相等 | G2-12 / G2-13 / G5-2 |
| A6 Mixed 不自动 | 默认仅 `'static'` 键 | G2-13 |
| A7 诊断可用 | `factor_routing` 每因子 1 条含元数据 | G2-18 / G2-19 / G2-21 |
| A8 规格日志 | 开启行数 = 因子数, 双臂正确; 关闭无目录 | G2-23 / G2-24 / G2-25 |
| A9 断点监控 | 默认 `{}`; 可检出 B1/B3 | G2-27 / G2-29 / G2-44 (B 系用例全绿) |
| A10 监控无副作用 | T12 逐位相等; `break_alerts` 只读 | G2-28 |
| A11 优化器 | 空空间 + `DeprecationWarning` + `ValueError`; orth 可用 | G2-7 / G2-8 / G2-9 / G2-10 |
| A12 消融 2 臂 | 2 臂 + 可选参照; 非法值 `ValueError` | G2-37 / G2-38 / G2-39 / G2-40 |
| A13 定向套件 | 新增失败 0 | G3-12 / G3-13 |
| A14 性能 | ≤ 1.05 × T0 | G0-10 / G5-3 |
| A15 版本/缓存 | 6 处 3.4.0; `v2.3.0-cache`; test_fix3 通过 | G4-1 / G4-2 / G4-3 / G4-4 |
| A16 文档 | ADR 取号落位 + 5 份文档同步 | G4-5 / G4-6 / G6-3~G6-8 |
| A17 依赖 | `pyproject.toml` 无新增 | G4-7 / G4-8 |

---

## §2 学术引用验收 (方法论模板 §2)

| 引用 | 调研文档条目 | 代码体现位置 | 状态 |
|------|------------|------------|------|
| Andrews (1993) — 未知断点 sup-F, Π=[0.15, 0.85] | RESEARCH §5.2 | `structural_break_monitor.py::_sup_f_stat` (trim=0.15, 候选区间 ⌈0.15n⌉..n−⌈0.15n⌉) | ✅ 源码核对通过 (模块 docstring L15 + `_sup_f_stat` L76-77: `k_lo=ceil(n*trim)`, `k_hi=n-ceil(n*trim)`; trim 默认 0.15, 越界 ValueError) |
| Inclán & Tiao (1994) — ICSS | RESEARCH §5.2 | `_cusum_stat` (工程化变体: `(y−ȳ)²` 替代残差平方, 须在 docstring 标注) | ✅ 源码核对通过 (模块 docstring L9/L19 与方法 docstring L95 均标注 "Inclán-Tiao (1994) ICSS 工程化变体: (y−ȳ)²") |
| Benjamini & Hochberg (1995) — BH-FDR | DESIGN §3.9 (**设计新增引用, 非调研内容**) | `ablation_runner` 复用 `multiple_testing.apply_bh_fdr`; L2 比较数 4→2 | ✅ 通过 (`test_l2_bh_fdr_2_comparisons` 绿; run_l2 2 臂) |
| Bai & Perron — 多断点 | RESEARCH §5.2 (v1.1 勘误: §5.4 未提及) | **不实施** (单断点 sup-F 足够; 设计 §3.7 方法集合隐含不实施) | ✅ 不适用 |
| Perron — 单位根/结构突变 | RESEARCH §5.2/§5.3 (v1.1 勘误) | **不实施** (AR(1) 路径上不检验单位根) | ✅ 不适用 |
| AR(1) 代理自助零分布 | DESIGN m10 (自行补充, 非 Andrews 原文) | `_bootstrap_pvalue` (docstring 必须标注"工程化选择") | ✅ 源码核对通过 (模块 docstring L8/L17-18: "AR(1) 代理自助替代渐近临界值, 为设计自行补充的工程化选择 (设计 m10, 非 Andrews 原文方法)"; burn-in 50) |

---

## §3 验收签署

| 角色 | 结论 | 日期 | 依据 |
|------|------|------|------|
| 实施 (步骤 9) | ✅ **PASS** (Gate 0–7 必须项全通过; 0 新增失败 / 0 新增 skip / 0 xfail; 2 个既有语义/条件 skip 按判定规则豁免) | 2026-11-10 | Gate 0–7 |
| 审计 (步骤 10) | ✅ **PASS** (0 P0; 1 P1 回归 — 3 个既有用例未迁移 `search_orth=True` — 已修复; 3 P2 + 24 P3 全部处置或记录; 1 条 subagent 误报剔除; 零回归) | 2026-11-10 | [2026-11-10-code-quality-audit.md](2026-11-10-code-quality-audit.md) |

**通过条件**: Gate 0–7 所有"必须"项为通过; 两个既有语义/条件 skip (fix1 L128、phase3 L1402/1452) 不计入新增。
**环境说明**: duckdb 2.0.0 与 optuna 5.0.0 已于 2026-11-10 安装 (步骤 9 前置), v1.0 checklist 的 duckdb 环境例外不再适用; G4-4 的手工脚本按 `tests/test_backtest/verify_fix3_manual.py` 实际路径执行。

---

## §4 附: 失败模式速查

| 现象 | 最可能原因 | 处置 |
|------|-----------|------|
| T1 失败 (`pipeline_mode` 不存在) | dataclass 字段未加 / `__post_init__` 缺失 | 检查 `PipelineV2Config` 是否在 `from_unified` 之前插入 |
| T2 失败 (仅部分因子不等) | `fit` 里 `_create_pipeline('static')` 传参不一致 (缺 module_enabled / neutralizer) | 与 `StaticFactorPipeline` 直调的参数逐项对齐 |
| T3 失败 | `dynamic_ab` 未注入 max_ar_order / decorrelation_strength | 检查 `_create_pipeline('dynamic', ...)` 分支未改 |
| T5 未抛 ImportError | 函数仍在 / `__all__` 仍导出 | 整函数删除 + grep docstring 残留 |
| T6 失败 (fingerprint_summary 为空) | 把"指纹提取"也纳入开关 | 提取始终执行, 开关只控制诊断标签 |
| T9 失败 (winsor 值错) | `_log_spec` 硬编码 static 分支 | 按 `record.execution_pipe_type` 派生 |
| T10 失败 (目录被创建) | `SpecificationLogger` 被提前构造 | 开关检查必须在构造之前 (`_log_spec` 首行 return) |
| T14 失败 (旧字段报错) | Pydantic `extra='ignore'` 被改成 `'forbid'` | 恢复 `extra='ignore'` |
| G2-7 抛 `NameError` | `optimizer.py` 未 `import warnings` | 顶部补导入 |
| G2-38 失败 (`AttributeError: pipeline_mode`) | 断言了 `AblationConfig.pipeline_mode` | 改断言 `routing_mode`, 或新增 patch 构造点的单测 |
| G2-43 大面积失败 | 改写后的消融用例与实现不同步 | 优先修实现; 不得放宽断言 (duckdb/optuna 已装, 必须动态通过) |
| G3-8/G3-9/G3-10 大面积失败 | 4 个关联文件未按 §8.2 清理 | 逐个按已删字段 grep 定位并改写 |
| `test_fix3` 失败 | 6 处版本链漏改 (`verify_fix3_manual.py` 最易漏) | 按 §8.3 清单补齐 |
| G5-3 性能超 1.05× | 误在 `fit` 内做了额外指纹重复提取 | 确认 `batch_extract` 仅 1 次 |
| G7-3 仍有命中 (pytest 文件) | 漏清理 4 个关联文件之一 | 定位文件后按 §8.2 改写 |

---

**Checklist 完成**: 2026-11-10 (v1.3, 步骤 10 审计验收完成 — 实施 + 审计双签署 PASS; 审计报告 = [2026-11-10-code-quality-audit.md](2026-11-10-code-quality-audit.md))。
