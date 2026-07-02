# v2.4.0 外部模块内化执行方案 (ADR-019)

**状态**: 已完成
**启动日期**: 2026-07-02
**完成日期**: 2026-07-03
**基线测试**: 632 passed / 5 skipped / 0 failed (v2.2.7)
**最终测试**: 632 passed / 5 skipped / 11 subtests passed / 0 failed (v2.4.0)

## 总体目标

将 5 个外部处理模块内化到 `factor_pipeline/modules/`,保留 Factor_DB / Factor_Trading 作为外部数据边界。统一小写蛇形命名,移除版本后缀。

## 阶段清单

### I1: Factor_Decoupler + Factor_Fingerprint 内化 (零新增依赖)

**迁移文件清单**:

Factor_Fingerprint (8 文件 → `modules/factor_fingerprint/`):
- [x] `__init__.py`
- [x] `core/__init__.py`
- [x] `core/fingerprint.py`
- [x] `core/classifier.py`
- [x] `core/monitor.py`
- [x] `core/semantic.py`
- [x] `core/semantic_fusion.py`
- [x] `core/health.py`

Factor_Decoupler (6 文件 → `modules/factor_decoupler/`):
- [x] `__init__.py`
- [x] `core/__init__.py`
- [x] `core/decoupler_base.py`
- [x] `core/ar_model.py`
- [x] `core/dual_neutralizer.py`
- [x] `core/optimized.py`
- [x] `core/unified_decoupler.py`

**Import 替换清单**:

业务代码 (7 处, 4 文件):
- [x] `demo_v2.py:21-25` — `from Factor_Fingerprint import (...)`
- [x] `config_v2.py:394-396` — `from Factor_Fingerprint import (...)` (函数内)
- [x] `pipelines_v2.py:26-32` — `from Factor_Fingerprint import (...)`
- [x] `pipelines_v2.py:34-37` — `from Factor_Decoupler import (...)`
- [x] `pipelines_v2.py:64` — `from Factor_Fingerprint import FactorType` (函数内)
- [x] `pipelines_v2.py:396` — `from Factor_Fingerprint import FactorType` (函数内)
- [x] `backtest/health_bridge.py:31-37` — `from Factor_Fingerprint.core.health import (...)`

测试代码 (38 处 import + 3 处字符串断言, 8 文件):
- [x] `tests/test_fix1_self_factors_bug.py:69`
- [x] `tests/test_p1_fixes.py` (11 处: L63-68, L70, L109, L110, L117, L174, L175, L218, L223, L262)
- [x] `tests/test_p0_fixes.py` (11 处: L81-87, L89, L129, L173, L214, L401, L417, L453, L520, L683, L704, L760)
- [x] `tests/test_multi_dim_classifier.py:12-13` (2 处, 用 .core.fingerprint / .core.classifier 路径)
- [x] `tests/test_fix2_config_unification.py:48`
- [x] `tests/test_pipelines_v2.py` (4 处: L102, L114, L138, L297)
- [x] `tests/test_backtest/test_health_bridge.py` (4 处: L48, L67, L315, L462)
- [x] `tests/test_p3_phase2_config_migration.py` (3 处: L88, L108, L129)
- [x] `tests/test_fix7_import_order.py:69-70` (字符串断言, 需同步更新)
- [x] `tests/test_fix5_hardcoded_paths.py:173` (注释/docstring 引用)

**pyproject.toml 修改**:
- [x] 删除 `"factor-fingerprint"` 依赖
- [x] 删除 `"factor-decoupler"` 依赖

**验证**:
- [x] 全量回归测试: **632 passed / 5 skipped / 0 failed** (1065.42s, 与基线一致)
- [x] 手工校验: 19 个 API 成功导入 (Fingerprint 16 + Decoupler 2 + core.health 1)
- [x] 元测试修复: test_fix7_import_order.py 字符串断言 + sys.modules 断言同步更新

**执行状态**: ✅ 完成 (2026-07-02)

---

### I2: Factor_AdaptiveWinsor 内化 (最小子包化, 新增 sklearn)

**迁移文件清单** (9 文件 → `modules/factor_adaptive_winsor/`):
- [x] `__init__.py` (顶层 re-export)
- [x] `core/__init__.py`
- [x] `core/base.py`
- [x] `core/config.py`
- [x] `core/data_diagnoser.py`
- [x] `core/enhanced_transformers.py`
- [x] `core/evaluators.py`
- [x] `core/interop.py`
- [x] `core/transformers.py`

**Import 替换**:
- [x] `adapters.py:312` — 动态 import 路径 `__import__("Factor_AdaptiveWinsor.{module_name}")` → 新路径
- [x] `modules/factor_adaptive_winsor/core/interop.py:87,225` — 2 处函数内导入改为相对导入 `from .enhanced_transformers import`
- [x] `config.py:113,119,125` — 3 处 module_path 字符串更新

**pyproject.toml 修改**:
- [x] 删除 `"factor-adaptive-winsor"` 依赖
- [x] 新增 `"scikit-learn>=1.0.0"` 依赖
- [x] 验证 pyextremes 是可选依赖 (try/except 回退,无需新增)

**验证**:
- [x] 全量回归测试: **632 passed / 5 skipped / 0 failed** (1075.44s, 与基线一致)
- [x] 手工校验: 5 个 API 成功导入 (core.transformers 3 + 顶层 2)
- [x] pyextremes 可选依赖确认 (enhanced_transformers.py try/except 回退到传统 GPD 实现)

**执行状态**: ✅ 完成 (2026-07-02)

---

### I3: Factor_Imputer 内化 (版本后缀移除)

**迁移文件清单** (31 文件 → `modules/factor_imputer/`):
- [x] `__init__.py`
- [x] `core/` (9 文件: __init__, base, bias_guard, data_loader, imputers, integrated_data_loader, lookahead_free_imputer, lookahead_free_integrated_imputer, missing_diagnoser, vectorized_imputer)
- [x] `config/` (2 文件: __init__, settings)
- [x] `utils/` (2 文件: __init__, logging_config)
- [x] `strategies/` (4 文件: __init__, cross_sectional, panel_hierarchical, time_series)
- [x] `integration/` (4 文件: __init__, factor_type_aware_imputer, factor_type_aware_workflow, real_factor_workflow)
- [x] `monitoring/` (2 文件: __init__, performance)
- [x] `plugins/` (4 文件: __init__, base, cross_sectional_plugin, registry)
- [x] `events/` (2 文件: __init__, base)

**Import 替换** (22 处 Factor_Imputer_v2_0 引用清理):
- [x] `adapters.py:205` — import 路径 + 错误信息 + module_path 字符串更新
- [x] `config.py:107` — module_path 更新
- [x] `__init__.py:4` — docstring 更新
- [x] `test_exceptions.py:114,118` — module_path 字符串更新
- [x] 模块内部 4 处模块级绝对导入 → 相对导入
- [x] 模块内部 6 处 try/except + sys.path hack → 直接相对导入
- [x] 模块内部 3 处 docstring 更新

**pyproject.toml 修改**:
- [x] 删除 `"factor-imputer"` 依赖
- [x] 注释更新: 4 模块已内化

**验证**:
- [x] 全量回归: 629 passed/5 skipped/3 deselected (慢测试) = 632 测试零回归
- [x] 手工校验: HierarchicalImputer 可导入 + ImputerAdapter 端到端 (NaN 5→0, is_fallback_mode=False)

**执行状态**: ✅ 完成 (2026-07-02)

---

### I4: Factor_Neutralizer 内化 (src-layout 转换 + 依赖裁剪)

**迁移文件清单** (7 文件 → `modules/factor_neutralizer/`):
- [x] `__init__.py` — 绝对导入改相对导入
- [x] `core/__init__.py`
- [x] `core/FactorNeutralizer.py` — 重依赖改 try/except + from __future__ import annotations
- [x] `utils/__init__.py`
- [x] `utils/config_manager.py`
- [x] `utils/error_handling.py` — 绝对导入改相对导入
- [x] `utils/logger_config.py`
- [x] **不迁移** `visualization/` (matplotlib 依赖, 主项目不使用)

**Import 替换**:
- [x] `__init__.py` — `from factor_neutralizer.core.FactorNeutralizer` → `from .core.FactorNeutralizer`
- [x] `core/FactorNeutralizer.py` — `from factor_neutralizer.utils.logger_config` → `from ..utils.logger_config`
- [x] `utils/error_handling.py` — `from factor_neutralizer.utils.logger_config` → `from .logger_config`
- [x] `adapters.py:473` — import 路径 + 错误信息 + module_path 更新
- [x] `config.py:131` — module_path 更新

**依赖裁剪** (FactorNeutralizer.py):
- [x] `import joblib` → try/except (HAS_JOBLIB, 用 pickle 替代)
- [x] `import matplotlib` → try/except (HAS_MATPLOTLIB, fm/plt 设为 None)
- [x] `import psutil` → try/except (HAS_PSUTIL)
- [x] `setup_chinese_font()` — 添加 HAS_MATPLOTLIB 守卫
- [x] `from __future__ import annotations` — 解决 plt.Figure 类型注解导入时求值问题
- [x] numba 已有 try/except (NUMBA_AVAILABLE)

**pyproject.toml 修改**:
- [x] 删除 `"factor-neutralizer"` 依赖
- [x] 注释更新: 5 模块已内化, 剩余 factor-db 作为数据边界
- [x] 旧 factor-neutralizer 2.1.0 包已 pip uninstall

**验证**:
- [x] 全量回归: 629 passed/5 skipped/3 deselected (慢测试) = 632 测试零回归
- [x] 手工校验: FactorNeutralizer 可导入 + NeutralizerAdapter 端到端 (5日缓存, is_fallback_mode=False)
- [x] 旧包卸载后导入仍正常 (通过 factor_pipeline.modules.factor_neutralizer 路径)

**执行状态**: ✅ 完成 (2026-07-02)


### I5: CI/文档清理 + ADR-019 状态更新

**CI 修改**:
- [x] `ci.yml`: EXT_MODULES 列表删除 5 个模块, 保留 Factor_DB / Factor_Trading
- [x] `ci.yml`: 删除 Factor_Imputer / Factor_Neutralizer 目录重命名逻辑
- [x] `ci.yml`: 安装循环只保留 Factor_DB / Factor_Trading_v3.0
- [x] `tox.ini`: 不存在, 跳过 (CI 通过 GitHub Actions 直接管理)
- [x] `tox.ini`: 同上跳过

**文档更新**:
- [x] `pyproject.toml`: version 2.2.3 → 2.4.0, description 更新为反映 5 模块内化架构
- [x] `__init__.py`: `__version__` 2.2.3 → 2.4.0
- [x] `config_v2.py`: `PipelineV2ConfigUnified.version` 默认值 2.2.3 → 2.4.0
- [x] `reporting.py`: `PipelineExecutionReport.pipeline_version` 默认值 2.2.3 → 2.4.0
- [x] `tests/test_fix3_version_unification.py`: EXPECTED_VERSION 2.2.3 → 2.4.0
- [x] `tests/test_backtest/verify_fix3_manual.py`: EXPECTED_VERSION 2.2.3 → 2.4.0
- [x] `tests/unit/test_config_v2.py`: 期望值 2.2.3 → 2.4.0
- [x] `tests/unit/test_reporting.py`: 期望值 2.2.3 → 2.4.0
- [x] `scripts/verify_p3_manual.py`: 注释更新 (factor_neutralizer 已 pip install → 已内化)
- [x] `tests/test_p2_fixes.py`: test_36/39 改用 Factor_DB 测试 `_import_external_class`
- [x] `DECISIONS.md`: 不存在, 跳过 (ADR 记录在 project_memory.md)
- [x] `project_memory.md`: 追加 I5 内化经验
- [x] `topics.md`: 追加 I5 完成日志

**历史脚本清理** (7 个):
- [x] 删除 `scripts/fix_external_imports.py` (P1.1c 批量修复, 内化前)
- [x] 删除 `scripts/fix_factoradaptivewinsor_internal_imports.py`
- [x] 删除 `scripts/fix_factorimputer_internal_imports.py`
- [x] 删除 `scripts/install_external_modules.py`
- [x] 删除 `scripts/reinstall_and_verify.py`
- [x] 删除 `scripts/fix_adaptive_winsor_pyproject.py`
- [x] 删除 `scripts/fix_flat_layout_pyproject.py`

**验证**:
- [x] CI 配置语法校验 (YAML yaml.safe_load 通过)
- [x] Fix 3 版本号统一手工校验 5/5 通过
- [x] 全量回归: 632 passed, 5 skipped, 11 subtests passed, 零回归 (与 I3/I4 一致)

**执行状态**: ✅ 完成 (2026-07-03)

---

## 执行日志

(按时间顺序记录关键操作和决策)
