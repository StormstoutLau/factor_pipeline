# v3.3.3 PL-01 去极值因果性修复 — 审查验收 Checklist

**版本**: v1.1 (已执行)
**日期**: 2026-10-22
**实施文档**: [EXECUTION_V3.3.3_PL01_OUTLIER_CAUSALITY.md](EXECUTION_V3.3.3_PL01_OUTLIER_CAUSALITY.md)
**设计文档**: [analysis/PL01_OUTLIER_LOOKAHEAD_DESIGN.md](analysis/PL01_OUTLIER_LOOKAHEAD_DESIGN.md)
**判定规则**: 任一 "必须" 项未通过 → 本阶段不通过; 允许的 known-xfail 仅限 PL-02/04/05/06/07。

---

## §0 使用方式

1. 按 Gate 顺序执行; 每项填写 `实际` 与 `证据`。
2. 命令统一在 `F:\Coding` 下运行, 解释器为
   `C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe`。
3. 涉及行号的位置仅作导航, 以函数名/测试名为准 (行号会随编辑漂移)。
4. 未实测的数字不得写入文档结论; 以命令输出为准。

---

## Gate 0: 前置与基线

| # | 检查项 | 必须 | 命令/方法 | 期望 | 实际 | 证据 |
|---|--------|------|-----------|------|------|------|
| G0-1 | 解释器可用 | 是 | `python.exe -m pytest --version` | pytest 9.x | **pytest 9.0.3** | 命令输出 |
| G0-2 | 工作树状态已知 | 是 | `git status --short` | 无未知的本次变更 | 通过: 变更前已存在未提交改动与调试文件; 本次新增/修改文件与清单一致 | `git status --short` |
| G0-3 | 基线集成测试 | 是 | `pytest factor_pipeline/tests/integration/test_pipeline_truncation_invariance.py -q` | 12 项, 6 passed / 6 xfailed (含 PL-01) | **6 passed / 6 xfailed** (修复前) | 基线记录 |
| G0-4 | 基线适配器测试 | 是 | `pytest factor_pipeline/tests/unit/test_adapters_mock.py factor_pipeline/tests/test_adapters/test_module_enabled.py -q` | 38 passed, 2 skipped, 0 failed | **38 passed / 2 skipped** | 输出尾部 |
| G0-5 | 记录 PL-01 基线数值 | 是 | `pytest ... -q -s` 的 `test_diagnostic_report` | outlier 行非 0 | **187 格 / max 1.68e-01** | 登记表 |

**失败处理**: 若基线本身不绿, 先停止; 不得把既有失败混入本次验收。

---

## Gate 1: Red — 新测试先失败

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G1-1 | 新测试文件存在 | 是 | `tests/unit/test_outlier_cross_sectional.py` | 存在 | **存在** | 文件 |
| G1-2 | 15 项测试已定义 | 是 | `pytest --collect-only -q <file>` | 15 项 | **15 个测试函数 (参数化后 30 例)** | 收集结果 |
| G1-3 | 未实现前失败 | 是 | `pytest <file> -q` | 失败 | **27 failed / 3 passed** (符合 Red) | Red 输出 |
| G1-4 | 测试覆盖验收映射 | 是 | 对照实施文档 §4.1 表 | 15/15 有断言 | **15/15** | 测试文件 |

**失败处理**: 若测试在未实现前通过, 说明测试未命中契约, 必须加严断言。

---

## Gate 2: Green — 单元测试

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G2-1 | `auto` 解析 | 是 | 测试 1 | `method='percentile'`, `requested_method='auto'` | 通过 | `TestMethodResolution` |
| G2-2 | 显式方法保留 | 是 | 测试 2 (7 方法) | 全部一致 | 7/7 通过 | 参数化 |
| G2-3 | percentile 边界 | 是 | 测试 3 | `atol=1e-12` | 通过 | `TestCausality` |
| G2-4 | percentile 截断不变式 | 是 | 测试 4 | `n_diff=0`, `max=0` | 通过 | `TestCausality` |
| G2-5 | NaN/元数据 | 是 | 测试 5 | 模式/index/columns 不变 | 通过 | `TestEdgeCases` |
| G2-6 | 小样本/零离散度 | 是 | 测试 6/7 | 原样, 无警告 | 通过 | `TestEdgeCases` |
| G2-7 | MAD/全方法不变式 | 是 | 测试 8/9 | 6/6 通过 | 通过 | `TestCausality` |
| G2-8 | 非法输入 fail loud | 是 | 测试 10/11/12 | 对应 ValueError/TypeError | 通过 | `TestMethodResolution` |
| G2-9 | enabled=False identity | 是 | 测试 13 | 原样, `_processor_class is None` | 通过 | `TestEdgeCases` |
| G2-10 | fit no-op | 是 | 测试 14 | `_processor is None` | 通过 | `TestCausality` |
| G2-11 | get_stats | 是 | 测试 15 | 3 个新字段 | 通过 | `TestEdgeCases` |
| G2-12 | 文件全绿 | 是 | `pytest <file> -q` | 15 passed | **30 passed** (15 函数参数化) | 输出尾部 |

---

## Gate 3: 集成 — 截断不变式

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G3-1 | PL-01 xfail 已移除 | 是 | 检查测试装饰器 | 无 `xfail` 于 `test_outlier_percentile_is_causal` | 已移除 | 测试源码 |
| G3-2 | PL-01 通过 | 是 | `pytest ... -q` | passed | **passed** | 输出 |
| G3-3 | 诊断矩阵 outlier 行 | 是 | `pytest ... -q -s` | `n_diff_cells=0`, `max_abs_diff=0` | **0 / 0** | 诊断表 |
| G3-4 | Static 行下降 | 是 | 同上 | 降至 PL-02 量级 (记录实测) | **1800 格 / 4.72e-05** | 诊断表 |
| G3-5 | 登记表与实测一致 | 是 | 模块 docstring + xfail reason | 数字来自本次输出 | 已更新 (PL-02/04/05/06/07) | diff |
| G3-6 | 无 unexpected xpass | 是 | `pytest ... -q` | 0 xpassed | **7 passed / 5 xfailed** | 输出 |

**诊断矩阵实测**:

```
step       imputer ffill_ts         PASS          0       0    0.000e+00
step       outlier percentile       PASS          0       0    0.000e+00
step       neutralize               PASS          0       0    0.000e+00
step       transform auto           FAIL       1800       0    8.506e-04
step       standardize 'auto'       PASS          0       0    0.000e+00
step       standardize 'z_score'    PASS          0       0    0.000e+00
pipeline   Static                   FAIL       1800       0    4.720e-05
pipeline   Dynamic                  FAIL       1653       8    8.045e-01
pipeline   Mixed                    FAIL       1800       0    2.906e-01
违反 4 / 满足 5 / 合计 9
```

**失败处理**: 若 PL-01 仍失败, 先用 `test_diagnostic_report` 定位是 percentile 还是逐行路径; 不得用放宽 `atol` 的方式通过。

---

## Gate 4: 回归靶向

```powershell
C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe -m pytest `
  factor_pipeline/tests/unit/test_outlier_cross_sectional.py `
  factor_pipeline/tests/integration/test_pipeline_truncation_invariance.py `
  factor_pipeline/tests/unit/test_adapters_mock.py `
  factor_pipeline/tests/test_adapters/test_module_enabled.py `
  factor_pipeline/tests/test_pipelines_v2.py `
  factor_pipeline/tests/unit/test_step1_winsorizer_percentile.py `
  factor_pipeline/tests/unit/test_config_v2.py `
  factor_pipeline/tests/unit/test_reporting.py -q
```

| # | 检查项 | 必须 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|
| G4-1 | 回归全绿 | 是 | 0 failed | **126 passed / 2 skipped / 5 xfailed / 0 failed** | 输出尾部 |
| G4-2 | 仅允许 known-xfail | 是 | 仅 PL-02/04/05/06/07 | 5 项, 符合 | `-rx` |
| G4-3 | `test_transform_outlier` | 是 | passed (逐行 MAD 压缩 50→≈2.85) | passed | `test_adapters_mock.py` |
| G4-4 | `enabled=False` 契约 | 是 | passed | passed | `test_module_enabled.py` |
| G4-5 | Mixed 2σ 测试 | 是 | passed (PL-06 未动) | passed | `test_pipelines_v2.py` |

**补充回归** (更宽范围): `tests/unit` + `tests/test_adapters` + `tests/integration` +
`test_pipelines_v2.py` + 版本/修复测试 = **348 passed / 2 skipped / 5 xfailed / 0 failed**。

**环境阻断 (非本次变更, 已排除)**: `test_pipelines_v2_cusum.py` 7 failed
(`cusum_drift_monitor` 模块不存在); `test_e2e_cached_pipeline.py` 4 failed
(DuckDB 文件被其它进程占用); `test_integration_real_data.py` 在收集期因同一 DB 锁退出。

---

## Gate 5: 性能

| # | 检查项 | 必须 | 方法 | 门限 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G5-1 | percentile 快速路径 | 是 | 临时基准 T=2500/N=3000 | ≤0.5s | **0.226s** | 临时脚本输出 |
| G5-2 | MAD 逐行路径 | 是 | 同上 | ≤5s | **2.888s** | 临时脚本输出 |
| G5-3 | 无临时脚本入库 | 是 | `git status --short` | 无 probe/bench 文件 | 临时脚本置于 `%TEMP%` 并已删除 | `git status` |

---

## Gate 6: 版本与缓存

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G6-1 | pyproject | 是 | 读取 | `3.3.3` | 3.3.3 | 文件 |
| G6-2 | `__version__` | 是 | 读取 | `3.3.3` | 3.3.3 | 文件 |
| G6-3 | config_v2 | 是 | 读取 | `3.3.3` | 3.3.3 | 文件 |
| G6-4 | reporting | 是 | 读取 | `3.3.3` | 3.3.3 | 文件 |
| G6-5 | 测试锚点 | 是 | `EXPECTED_VERSION` | `3.3.3` | 3.3.3 | 文件 |
| G6-6 | 版本测试 | 是 | `pytest tests/test_fix3_version_unification.py tests/unit/test_config_v2.py tests/unit/test_reporting.py -q` | 0 failed | **41 passed** | 输出 |
| G6-7 | 缓存 CODE_VERSION | 是 | 读取 `cache_manager.py` | `v2.2.1-cache` | v2.2.1-cache | 文件 |
| G6-8 | 4 个缓存默认值 | 是 | 读取 4 文件 | 均引用 `CODE_VERSION` | 4/4 引用同一常量 | 文件 |
| G6-9 | 缓存版本测试 | 是 | `pytest tests/test_fix3_version_unification.py -q` | passed (2.2.1-cache) | **7 passed** | 输出 |
| G6-10 | 手工校验 | 是 | `python tests/test_backtest/verify_fix3_manual.py` | 5/5 + 缓存独立 | **5/5, 缓存 v2.2.1-cache 独立** | 输出 |
| G6-11 | 子包版本未误改 | 是 | `git diff` | `modules/*/__version__` 不变 | 无 `__version__` 变更 | `git diff -- modules` |
| G6-12 | 缓存代际实际失效 | 是 | `pytest tests/test_backtest/test_cache_manager.py::TestCodeVersionGeneration -q` | 写入 v2.2.0 → 读取 v2.2.1: MISS + 旧文件删除; verify 报 mismatch | **3 passed** | 输出 |

---

## Gate 7: 文档

| # | 检查项 | 必须 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|
| G7-1 | ADR-037 已写入 | 是 | 背景/决策/备选/后果/测试契约/不覆盖/回滚 | 已写入, 含 D1-D7 / 备选 / 回滚 | `DECISIONS.md` |
| G7-2 | ADR 占用表 | 是 | `ADR-037` 已占用; `ADR-038 起` 未占用 | 一致 | `DECISIONS.md` |
| G7-3 | CHANGELOG v3.3.3 | 是 | 概览/根因/修复/行为变更/测试/遗留/文档 | 已写入 | `CHANGELOG.md` |
| G7-4 | 勘误注 (审计文档) | 是 | 日期化, 不改写历史原文 | 两份文档顶部已加 2026-10-22 勘误 | `docs/analysis/*` |
| G7-5 | 研究与设计文档状态 | 是 | 均标 "已实施 (v3.3.3)" | 均标 v1.1 / 已实施 | 文件头 |
| G7-6 | DEV_PROGRESS | 是 | 当前标记 v3.3.3 | 已更新 | 文件 |
| G7-7 | ARCHITECTURE | 是 | 基线 v3.3.3; outlier 标逐日截面 | 已更新 | 文件 |
| G7-8 | WORKFLOW_METHODOLOGY | 是 | `至 ADR-037` | 已更新 | 文件 |
| G7-9 | 文档链接 | 是 | 相对链接全部存在 | 本次文档 133 链接; 新增链接全部有效; 3 处缺失为历史遗留/`file://` 误判 | 临时检查脚本 |
| G7-10 | 无未实测数字写成结论 | 是 | 抽查 CHANGELOG/ADR | 抽查通过 (均来自本次输出) | 人工核对 |

---

## Gate 8: 最终交付

| # | 检查项 | 必须 | 方法 | 期望 | 实际 |
|---|--------|------|------|------|------|
| G8-1 | `git diff --check` | 是 | 命令 | 无 whitespace error | 本次文件范围 **clean**; 全局存在 1 处历史文件 trailing whitespace (非本次) |
| G8-2 | 无临时/调试文件 | 是 | `git status --short` | 无 probe/test_results 等新增 | 本次未新增; 既有调试文件保持原状 |
| G8-3 | 变更范围 | 是 | `git diff --stat` | 仅本次列出的文件 | 本次范围含 `cache_manager.py` 读取校验 + 2 个测试文件; 工作树另含此前会话的未提交改动 |
| G8-4 | 回滚方案可用 | 是 | 文档 | §8.2 存在且具体 | ADR-037 / 实施文档均有回滚步骤 |
| G8-5 | 已知遗留已登记 | 是 | CHANGELOG | PL-02/05/06/07 + 后续任务 | 已登记 |

---

## §1 验收签署

| 角色 | 结论 | 日期 | 备注 |
|------|------|------|------|
| 实施 | 通过 (自动化验收) | 2026-10-22 | Gate 0-8 必须项通过; 环境阻断项已排除并记录 |
| 审查 | 通过 (自动化 review) | 2026-10-22 | 发现并修复: 初版缓存 bump 只改常量、读取未校验 `code_version`, 旧缓存仍会命中; 已补读取校验 + 自愈删除 + 3 项单测 + 五处一致性测试 |
| 最终验收 | 待用户签署 | | 建议重点复核 ADR-037 评审修订与 `CacheManager` 代际校验 |

**通过条件**: Gate 0-8 所有 "必须" 项为通过; 若有条件通过, 必须在备注中列出未闭环项与责任人。

---

## §2 附: 失败模式速查

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| `test_outlier_percentile_is_causal` unexpectedly passing | xfail 未移除 | 删除装饰器 |
| outlier 行仍有差异 | `fit` 仍走 flatten / percentile 未命中快速路径 | 检查 `_cross_sectional_outlier` 与 `self.method` |
| 显式 `mad` 结果与旧版一致但不同轴 | 行循环未启用 / 仍用 `_processor` | 检查 transform 分支顺序 |
| `TypeError: SmartOutlierDetector __init__ unexpected threshold` | 未过滤 detector kwargs | 检查 `_outlier_detector_kwargs` |
| 性能超门限 | percentile 走了逐行路径 | 检查 `self.method == 'percentile'` |
| 版本测试失败 | 缓存版本断言未更新 / 锚点遗漏 | 检查 5 处声明 + 测试 |
| 缓存仍命中旧值 | CODE_VERSION 未 bump 或 loader 显式传旧值 | 检查 5 处缓存版本 |
| 极端值未被裁剪 | 分位单位误用 (0-1) | 构造期应已 ValueError |
