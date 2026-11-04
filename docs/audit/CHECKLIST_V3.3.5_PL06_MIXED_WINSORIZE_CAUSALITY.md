# v3.3.5 PL-06 Mixed 缩尾因果性修复 — 审查验收 Checklist

**版本**: v1.1 (已执行, 2026-11-04)
**日期**: 2026-11-04
**缺陷**: DEFECT-PL-06
**实施文档**: [EXECUTION_V3.3.5_PL06_MIXED_WINSORIZE_CAUSALITY.md](../EXECUTION_V3.3.5_PL06_MIXED_WINSORIZE_CAUSALITY.md) v1.3
**设计文档**: [analysis/PL06_MIXED_WINSORIZE_LOOKAHEAD_DESIGN.md](../analysis/PL06_MIXED_WINSORIZE_LOOKAHEAD_DESIGN.md) v1.1 (A 选定)
**调研文档**: [analysis/PL06_MIXED_WINSORIZE_LOOKAHEAD_RESEARCH.md](../analysis/PL06_MIXED_WINSORIZE_LOOKAHEAD_RESEARCH.md) v1.0
**生成时机**: spec 步骤 7 (实施文档 review 通过后, TDD 实现前)
**判定规则**: 任一 "必须" 项未通过 → 本阶段不通过; 允许的 known-xfail 仅限 **PL-05 / PL-07** (PL-06 必须摘除)。

> 位置说明: 本工件按 WORKFLOW_METHODOLOGY v1.3 §13.7 放在 `docs/audit/`。PL-01 的 checklist 位于 `docs/` 根目录, 属 v1.3 整合前的历史位置, 不迁移。

---

## §0 使用方式

1. 按 Gate 顺序执行; 每项填写 `实际` 与 `证据`, **未实测的数字不得填入结论**。
2. 命令统一在 `F:\Coding` 下运行, 解释器为
   `C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe`。
3. 行号仅作导航, 以类名 / 函数名 / 测试名为准 (编辑后会漂移)。
4. 本 checklist 是步骤 10 审计的输入基准; 实施后逐项对照勾选。
5. 任一 Gate 失败即停止后续 Gate, 先修复再重跑本 Gate。

---

## Gate 0: 前置与基线

| # | 检查项 | 必须 | 命令 / 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------------|------|------|------|
| G0-1 | 解释器可用 | 是 | `python.exe -m pytest --version` | pytest 可用 | ✅ pytest 可用 | 命令输出 |
| G0-2 | pandas 版本满足测试别名 | 是 | `python.exe -c "import pandas; print(pandas.__version__)"` | `>=2.2` (`freq='ME'`) | ✅ 2.2.3 | 命令输出 |
| G0-3 | 工作树状态已知 | 是 | `git status --short` | 仅 PL-06 相关文档未提交 (research / design / execution / checklist); 生产代码未改 | ✅ 实施前仅 3 份 PL-06 文档; 实施后新增 6 文件 + 14 修改 (与 §9 清单一致) | `git status` |
| G0-4 | 基线集成 | 是 | `pytest .../test_pipeline_truncation_invariance.py -q` | 9 passed / 3 xfailed (6.91s) | ✅ **9 passed / 3 xfailed (7.97s)** | 输出尾部 |
| G0-5 | 基线靶向 | 是 | `pytest test_pipelines_v2.py test_module_enabled.py -q` | 33 passed (4.82s) | ✅ **33 passed** (合并跑 52 passed 含配置迁移+版本) | 输出尾部 |
| G0-6 | 基线配置迁移 | 是 | `pytest test_p3_phase2_config_migration.py -q` | 12 passed (0.63s) | ✅ **12 passed** | 输出尾部 |
| G0-7 | 基线版本统一 | 是 | `pytest test_fix3_version_unification.py -q` | 7 passed (0.36s) | ✅ **7 passed** | 输出尾部 |
| G0-8 | 基线性能 | 是 | 执行文档 §4.6 脚本, 3 次中位 | 当前实现 `0.281s` | ✅ **0.281s** (实施前 2026-11-04 实测) | 临时脚本输出 (已删) |
| G0-9 | PL-06 基线数值 | 是 | `test_diagnostic_report` 的 Mixed 行 | 若干格差异 + `max_abs≈6.98e-01` | ✅ **257/1800 格, 6.984e-01, 首个发散日 2020-01-31** | 调研 §1.2 / 集成登记表 |

**失败处理**: 基线不绿 → 停止; 不得把既有失败并入本次验收。→ **未触发**

---

## Gate 1: Red — 新测试先失败

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G1-1 | 新测试文件存在 | 是 | `tests/unit/test_mixed_winsorize_cross_sectional.py` | 存在, 11 个函数 | ✅ 存在, 11 函数 | 文件 |
| G1-2 | 公共 7 例齐备 | 是 | 对照实施文档 §4.1 | 7/7 | ✅ 7/7 | 测试文件 |
| G1-3 | A 专属 4 例齐备 | 是 | 对照实施文档 §4.1 | 4/4 | ✅ 4/4 | 测试文件 |
| G1-4 | Unimplemented 状态失败 | 是 | `pytest <file> -q` | **10 failed / 1 passed** | ✅ **10 failed / 1 passed (1.86s)** | Red 输出 |
| G1-5 | 唯一通过项为 winsorizer disabled | 是 | 同上 | `test_winsorizer_disabled_skips_clip` 通过 | ✅ 通过 (其余 10 例: 1 例 dict 断言失败 + 7 例 AttributeError + 2 例截断差异) | Red 输出 |
| G1-6 | 未用 xfail 掩盖 | 是 | 检查装饰器 | 新文件无 `xfail` | ✅ 无 | 源码 |
| G1-7 | 断言非恒真式 | 是 | 人工核对 | bounds 例用 numpy 独立路径 | ✅ `np.nanmean/nanstd/np.clip` 独立重建 | 源码 |

**失败处理**: 若未实现前有 >1 例通过 → 该例未命中契约, 必须加严断言; 不得用 `xfail` 掩盖。→ **未触发**

---

## Gate 2: Green — 单元测试

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G2-1 | `fit` 无跨期参数 | 是 | `test_fit_does_not_store_cross_period_params` | `_winsorize_params is None` | ✅ passed | 单测 |
| G2-2 | 截断不变式 (合成面板) | 是 | `test_truncation_invariant_on_synthetic_panel` | 前 t 期逐元素相等 (atol=1e-12) | ✅ passed | 单测 |
| G2-3 | 未来值不影响过去行 | 是 | `test_future_value_does_not_change_past_rows` | 前 T-1 行相等 | ✅ passed | 单测 |
| G2-4 | NaN / N=1 / 零离散度行原样 | 是 | `test_nan_rows_unchanged` | 逐元素相等 | ✅ passed | 单测 |
| G2-5 | 不新增 NaN | 是 | `test_no_new_nan` | NaN 模式一致 | ✅ passed | 单测 |
| G2-6 | winsorizer 关闭跳过缩尾 | 是 | `test_winsorizer_disabled_skips_clip` | `outlier == imputation` | ✅ passed | 单测 |
| G2-7 | index / columns 保留 | 是 | `test_metadata_preserved` | 完全一致 | ✅ passed | 单测 |
| G2-8 | sigma 单调性 | 是 | `test_sigma_monotonicity` | `count(2) ≥ count(3) ≥ count(4)` | ✅ passed | 单测 |
| G2-9 | `N≤10` no-op | 是 | `test_n_le_10_is_noop` | N=2/5/10 原样 | ✅ passed | 单测 |
| G2-10 | 边界 = 行均值 ± σ·行标准差 | 是 | `test_bounds_are_row_mean_plus_minus_sigma_std` | 与 numpy 独立路径一致 | ✅ passed | 单测 |
| G2-11 | `N=11` 可触发截断 | 是 | `test_n11_can_clip` | 至少 1 个值改变 | ✅ passed | 单测 |
| G2-12 | 文件全绿 | 是 | `pytest <file> -q` | **11 passed** | ✅ **11 passed (0.99s)** | 输出尾部 |

---

## Gate 3: 集成 — 截断不变式

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G3-1 | PL-06 `xfail` 已移除 | 是 | 检查 `test_mixed_pipeline_is_truncation_invariant` 装饰器 | 无 `xfail` | ✅ 已移除, docstring 更新 | 测试源码 |
| G3-2 | Mixed 端到端通过 | 是 | `pytest <integration> -q` | passed | ✅ passed | 输出 |
| G3-3 | 诊断矩阵 Mixed 行归零 | 是 | `pytest <integration> -q -s` | `n_diff_cells=0`, `max_abs_diff=0`, NaN 歧义 0 | ✅ **Mixed PASS 0 / 0 / 0** | 诊断表 |
| G3-4 | 套件计数 | 是 | 同上 | **10 passed / 2 xfailed**, 0 xpassed | ✅ **10 passed / 2 xfailed (6.15s)**, 0 xpassed | 输出尾部 |
| G3-5 | 缺陷登记表更新 | 是 | 模块 docstring | 移除 PL-06 行; "已修复" 追加 PL-06 (257/1800 → 0) | ✅ 已更新 | diff |
| G3-6 | PL-07 reason 更新 | 是 | xfail reason | 归因由 "PL-05/06" 改为 "PL-05"; 数值复测后填写 | ✅ 改为 "PL-05"; 实测复跑仍 1.84e+00 (1650 格), 数值不变 | 源码 + `--runxfail` 复测 |
| G3-7 | PL-05 reason 未误改 | 是 | xfail reason | 仍为 PL-05 自身描述, 8.05e-01 / 8 NaN | ✅ 未改 | 源码 |
| G3-8 | `unit_variance` 测试仍通过 | 是 | 该测试 | passed (逐日 std 中位 ≈1) | ✅ passed (含于 10 passed) | 输出 |
| G3-9 | 其余管线数值符合预期 | 是 | 诊断表 | Static 仍 0/0; Dynamic 仍 PL-05 量级 | ✅ Static PASS 0/0; Dynamic FAIL 1653/8/8.045e-01 (不变) | 诊断表 |

**若 PL-07 意外转绿**: 复测后未转绿 (仍 xfail, 1.84e+00 / 1650 格), 无需处理。→ **未触发**

**诊断矩阵实测 (实施后)**:

```
pipeline   Static                   PASS          0       0    0.000e+00  -
pipeline   Dynamic                  FAIL       1653       8    8.045e-01  2020-04-30
pipeline   Mixed                    PASS          0       0    0.000e+00  -
违反不变式 1 项 / 满足 8 项 / 合计 9 项   (实施前为 4 / 5 / 9)
```

---

## Gate 4: 回归靶向

```powershell
cd F:\Coding
C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe -m pytest `
  factor_pipeline/tests/unit/test_mixed_winsorize_cross_sectional.py `
  factor_pipeline/tests/test_p3_phase2_config_migration.py `
  factor_pipeline/tests/test_pipelines_v2.py `
  factor_pipeline/tests/test_adapters/test_module_enabled.py `
  factor_pipeline/tests/test_fix3_version_unification.py `
  factor_pipeline/tests/integration/test_pipeline_truncation_invariance.py -q
```

| # | 检查项 | 必须 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|
| G4-1 | 靶向全绿 | 是 | 0 failed | ✅ **73 passed / 2 xfailed (9.58s / 终验 10.76s)** | 输出尾部 |
| G4-2 | 配置迁移 12 passed | 是 | `TestMixedWinsorSigma` 重写后仍 12 项 | ✅ **12 passed (0.51s)** | 输出 |
| G4-3 | 旧 per-column 断言已消失 | 是 | 无 `_compute_winsorize_params` 调用 | ✅ 全仓 grep 仅剩 `_winsorize_params = None` (2 处) + 新测试的 `is None` 断言 (2 处) | grep |
| G4-4 | 管线 + 模块 33 passed | 是 | 与基线同量 | ✅ passed (含于 73) | 输出 |
| G4-5 | 版本 7 passed | 是 | v3.3.5 锚点 | ✅ **7 passed (0.32s)** | 输出 |
| G4-6 | 仅允许 PL-05 / PL-07 xfail | 是 | 2 项, 无 PL-06 | ✅ 仅 PL-05 / PL-07 | `-rx` |
| G4-7 | 无 unexpected xpass | 是 | 0 | ✅ 0 | 输出 |

---

## Gate 5: 性能

| # | 检查项 | 必须 | 方法 | 门限 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G5-1 | 单次缩尾耗时 | 是 | `_apply_winsorize` 2500×3000, 3 次中位 | **≤0.281s** (基线) | ✅ **0.184s** (0.175 / 0.184 / 0.193) | 临时脚本 (已删) |
| G5-2 | 无逐行 Python 循环 | 是 | 代码核对 | `mean/std/clip` 向量化 | ✅ 全向量化 | 源码 |
| G5-3 | 无临时脚本入库 | 是 | `git status --short` | 无 probe / bench 文件 | ✅ 3 个临时探针均已从 `%TEMP%` 删除 | `git status` |

---

## Gate 6: 版本与缓存

| # | 检查项 | 必须 | 方法 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|------|
| G6-1 | pyproject | 是 | 读取 L7 | `3.3.5` | ✅ 3.3.5 | 文件 |
| G6-2 | `__version__` | 是 | 读取 `__init__.py` | `3.3.5` | ✅ 3.3.5 | 文件 |
| G6-3 | config_v2 | 是 | L371 | `3.3.5` | ✅ 3.3.5 | 文件 |
| G6-4 | reporting | 是 | L40 | `3.3.5` | ✅ 3.3.5 | 文件 |
| G6-5 | test_fix3 锚点 | 是 | `EXPECTED_VERSION` + 4 处 docstring | `3.3.5`; L12 日期 `2026-11-04` | ✅ 全部 3.3.5; 日期 2026-11-04 | 文件 |
| G6-6 | verify_fix3_manual 锚点 | 是 | `EXPECTED_VERSION` + L5 docstring | `3.3.5` | ✅ 3.3.5 | 文件 |
| G6-7 | 版本套件 | 是 | `pytest tests/test_fix3_version_unification.py -q` | 7 passed | ✅ **7 passed (0.32s)** | 输出 |
| G6-8 | 缓存常量 | 是 | `cache_manager.py` | `v2.2.3-cache` | ✅ v2.2.3-cache | 文件 |
| G6-9 | 缓存字面量 | 是 | `test_fix3` L14/79/83/92/93/108 | 6 处均为 `v2.2.3-cache`; L83 保留 PL-02 历史并追加 PL-06 bump | ✅ 6 处更新; L83 为 "故 v2.2.1-cache → v2.2.2-cache; PL-06 ... → v2.2.3-cache" | 文件 |
| G6-10 | 5 个缓存类默认值 | 是 | `test_07` (5 类) | 全部继承同一 `CODE_VERSION` | ✅ passed (含于 7 passed) | 输出 |
| G6-11 | 手工校验脚本 | 是 | `python tests/test_backtest/verify_fix3_manual.py` | 5/5 + 缓存独立于项目版本 | ✅ **5/5, 缓存 v2.2.3-cache 独立** | 输出 |
| G6-12 | 子包版本未误改 | 是 | `git diff -- modules` | 无 `__version__` 变更 | ✅ diff 为空 | `git diff` |
| G6-13 | 缓存代际失效 | 是 | `TestCodeVersionGeneration` | 旧代 MISS + 自愈删除 | ✅ **3 passed (0.57s)** | 输出 |

---

## Gate 7: 文档

| # | 检查项 | 必须 | 期望 | 实际 | 证据 |
|---|--------|------|------|------|------|
| G7-1 | ADR-039 已写入 | 是 | 背景 / 决策 / 备选 / 代码证据 / 实测证据 / 测试契约 / 不覆盖 / 后果 / 学术依据 / 回滚 | ✅ 全部章节齐备 | `DECISIONS.md` |
| G7-2 | ADR 占用表 | 是 | `ADR-039` 已占用; `ADR-040 起` 未占用 | ✅ 一致 | `DECISIONS.md` |
| G7-3 | ADR 实测表已回填 | 是 | 无 "待实测"; 数值与输出一致 | ✅ grep "待实测" 为 0; 0/1800、561/3000、77/3000、0.184s 均实测 | `DECISIONS.md` |
| G7-4 | CHANGELOG v3.3.5 | 是 | 概览 / 根因 / 实测矩阵 / 核心产出 / 兼容性 / 遗留 | ✅ 已写入 (置顶) | `CHANGELOG.md` |
| G7-5 | ARCHITECTURE 基线 | 是 | 追加 v3.3.5 条目 | ✅ 已追加 | `docs/ARCHITECTURE.md` |
| G7-6 | DEV_PROGRESS | 是 | 追加 v3.3.5 行并移动 "当前" 箭头 | ✅ 箭头移至 v3.3.5 | `docs/DEV_PROGRESS.md` |
| G7-7 | 设计文档状态 | 是 | 头部标注 "已实施 (v3.3.5)" + 指向实施文档 §7 | ✅ 已标注 | 文件头 |
| G7-8 | 调研文档状态 | 是 | "后续" 行更新为已实施 | ✅ 已标注 | 文件头 |
| G7-9 | 实施文档 §7.2 回填 | 是 | 全部 "待实测" 替换为实测值 | ✅ v1.3 已回填 | 实施文档 |
| G7-10 | 无未实测数字写成结论 | 是 | 抽查 CHANGELOG / ADR / 实施文档 | ✅ 抽查通过 (257/1800、561/3000、77/3000、0.184s、73 passed 均来自本次输出) | 人工核对 |

---

## Gate 8: 最终交付

| # | 检查项 | 必须 | 方法 | 期望 | 实际 |
|---|--------|------|------|------|------|
| G8-1 | `git diff --check` | 是 | 命令 | 本次文件范围无 whitespace error | ✅ clean (仅 LF→CRLF 提示, 非 error) |
| G8-2 | 无临时/调试文件 | 是 | `git status --short` | 无 probe / test_results 等新增 | ✅ 无 |
| G8-3 | 变更范围 | 是 | `git diff --stat` | 仅实施文档 §9 列出的文件 | ✅ 14 修改 + 6 新增, 与 §9 一致 (optimizer.py / config_v2.py 配置面未动, diff 仅版本号) |
| G8-4 | 无残留调用 | 是 | `git grep -n "_compute_winsorize_params\|_winsorize_params"` | 仅历史文档 / CHANGELOG 叙述 | ✅ py 内仅 `_winsorize_params = None` (2 处) + 新测试断言 (2 处); `_compute_winsorize_params` 定义/调用为 0 |
| G8-5 | 回滚方案可用 | 是 | 文档 | 实施文档 §8.2 与 ADR-039 回滚段存在且可执行 | ✅ 均存在 |
| G8-6 | 已知遗留已登记 | 是 | CHANGELOG / ADR | PL-05 / PL-07 / B 未实施 / Mixed 3σ 与 Static percentile 差异 | ✅ 均登记 |

---

## §1 验收签署

| 角色 | 结论 | 日期 | 备注 |
|------|------|------|------|
| 实施 | **通过** | 2026-11-04 | Gate 0-8 全部 "必须" 项通过; 1 项 P2 发现 (文档 test_09 代码缺形状广播) 实施中已修复并回写文档 |
| 审查 | **通过** | 2026-11-04 | 见 [2026-11-04-code-quality-audit.md](2026-11-04-code-quality-audit.md): 评分 PASS, 4 类测试盲区无遗留, 代码 vs 实施文档对齐 |
| 最终验收 | 待用户签署 | | 建议重点复核: ADR-039 实测表、PL-07 reason 的 1.84e+00 数值未变 (上游 PL-05 主导)、缓存 v2.2.3-cache 一次性失效 |

**通过条件**: Gate 0-8 所有 "必须" 项为通过; 若有条件通过, 必须在备注中列出未闭环项与责任人。

---

## §2 附: 失败模式速查

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| Red 阶段 >1 例通过 | 断言未命中契约 (如只断言无异常) | 加严断言, 不得用 xfail |
| `test_winsorizer_disabled_skips_clip` 在 Red 阶段失败 | `module_enabled` 未传到 Mixed 构造器 | 检查 `_pipe(module_enabled=...)` 与 `MixedFactorPipeline.__init__` |
| Green 后 Mixed 仍有差异 | `fit` 仍调用 `_compute_winsorize_params` | 检查 Step 2 与全仓 grep |
| `AttributeError: _winsorize_params` | 直接调用 `_apply_winsorize` 但实现仍读旧参数 | 确认新实现不读取 `self._winsorize_params` |
| `N=11` 未截断 | `ddof` 或 `sigma` 取错 / 用了 `axis=0` | 核对 `std(axis=1, ddof=1)` 与 `clip(axis=0)` |
| 边界测试 1e-12 不过 | pandas 与 numpy 数值路径差异 | 先确认 `np.nanstd(..., ddof=1)`; 超差需记录而非放宽 |
| PL-07 unexpectedly passing | strict xfail 在 PL-06 修复后转绿 | 按 §4.3 复测并摘除, 另立任务补面板 |
| 性能超过 0.281s | 误用 `apply` / 逐行循环 / 重复 copy | 回到向量化实现 |
| 版本测试失败 | 6 处缓存字面量或 4 处 docstring 遗漏 | 逐处核对 §5.1 / §5.2 清单 |
| 缓存仍命中旧值 | 只 bump 常量但某 loader 显式传旧值 | 核对 5 个缓存类默认值 |
