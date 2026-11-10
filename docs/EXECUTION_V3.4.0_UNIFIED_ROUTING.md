# v3.4.0 因子路由统一化治理 — 实施文档

**文档版本**: v1.3 (2026-11-10; v1.0 = 步骤 5 初稿; v1.1 = 步骤 6 幻觉消除 review 修订; v1.2 = 步骤 8 一致性 review 勘误; v1.3 = 步骤 9 落库回填, 见 §14)
**日期**: 2026-11-10
**设计依据**: [FACTOR_ROUTING_OVERENGINEERING_DESIGN.md](analysis/FACTOR_ROUTING_OVERENGINEERING_DESIGN.md) v1.2 (D1–D12 锁定; v1.2 = 步骤 8 勘误)
**调研依据**: [FACTOR_ROUTING_OVERENGINEERING_RESEARCH.md](analysis/FACTOR_ROUTING_OVERENGINEERING_RESEARCH.md) v1.1 (唯一学术/工业依据源, 映射见 §0.3)
**目标版本**: **v3.4.0**; 缓存 **`v2.3.0-cache`**
**变更性质**: 行为变更 (原 dynamic 因子改走统一管道) + 配置面破坏性变更 (删 5 字段) + 新增诊断/监控模块
**实施方式**: 严格 TDD (Red → Green → 回归 → 版本/文档)
**规范依据**: [WORKFLOW_METHODOLOGY.md](WORKFLOW_METHODOLOGY.md) v1.3 §13.5 — 工程细节 / 版本 / 依赖 / 兼容 / 接口 / 签名 / 排除低效操作
**后续工件**: 步骤 6 实施 review ✅ → 步骤 7 checklist ✅ → 步骤 8 一致性 review ✅ (见 docs/audit/CONSISTENCY_REVIEW_V3.4.0.md) → 步骤 9 TDD
**行号说明**: 行号仅作导航, 以类名/函数名/测试名为准 (编辑后会漂移)

---

## §0 实施摘要

| 项 | 内容 |
|---|------|
| 核心改动 | `PipelineV2Config.pipeline_mode` 默认 `'unified'`; `fit` 不再调用 `StatisticalClassifier`, 所有因子走 `StaticFactorPipeline`; 删除 3 个路由函数与 5 个配置字段; 新增 `FactorRoutingRecord`/`FingerprintMeta`/`infer_sampling_frequency`/`compute_ar1_path`; 规格日志按臂记录; 新增 `StructuralBreakMonitor` |
| 不改 | 三条管道类的内部实现; 中性化/插补/标准化/AR 解耦; `monitor_cusum_drift`; `_ks_migration_significance`; `StatisticalClassifier` 模块; 21 维指纹契约; DuckDB schema; 公共 `fit`/`transform` 签名 |
| 代码文件 | `pipelines_v2.py` / `config_v2.py` / `optimizer.py` / `modules/factor_fingerprint/core/fingerprint.py` / `modules/factor_fingerprint/__init__.py` / `backtest/ablation_runner.py` / `reporting.py` (仅版本) / **新增** `backtest/structural_break_monitor.py` |
| 测试文件 | **新增** `tests/test_unified_routing.py` (14) / `tests/test_structural_break_monitor.py` (6); 修改 13 个既有测试/手工脚本 (见 §2/§8.2); 删除 `tests/test_multi_dim_classifier.py` (20) |
| 版本同步 | 6 处版本声明 (`__init__.py` / `pyproject.toml` / `config_v2.py` / `reporting.py` / `test_fix3` / `verify_fix3_manual.py`) + `CODE_VERSION` + README + CHANGELOG |
| 文档 | **ADR 编号待分配** (DECISIONS.md 登记规则 2: 规划文档不得预留编号; 当前空闲号 ADR-042, 全文暂以其指代, 实施落库时回 DECISIONS.md 取号) / CHANGELOG v3.4.0 / PROJECT_STATUS / DEV_PROGRESS / ARCHITECTURE |
| 验收关键 | 统一管道与 `StaticFactorPipeline` 逐位等价; Dynamic 仅 A/B 可达; 5 个字段/3 个函数彻底消失; 旧 JSON 可加载; 定向套件无新增失败 (基线 107 passed / 0 failed, duckdb 安装后复测) |

### 0.1 E 任务清单

| E | 目标 | 主要文件 | 复杂度 | 依赖 | 验收 |
|---|------|---------|-------|------|------|
| **E1** | 配置面: 加 8 删 5 + 桥接 + 优化器收缩 | `pipelines_v2.py` / `config_v2.py` / `optimizer.py` | O(1) | 无 | A1–A3, A11 |
| **E2** | 统一执行: `fit`/`transform` 重构 + 记录 + 汇总表 | `pipelines_v2.py` | O(1) 额外开销 | E1 | A4–A7 |
| **E3** | 诊断层: 频率推断 + AR(1) 路径 + 记录结构 | `fingerprint.py` / `__init__.py` / `pipelines_v2.py` | O(T/stride) 仅显式调用 | E2 | A7, T7 |
| **E4** | 规格日志: `_log_spec` 按臂记录 | `pipelines_v2.py` | 每因子 1 次写盘 (opt-in) | E2/E3 | A8 |
| **E5** | 断点监控: 新模块 + 管道方法 | `backtest/structural_break_monitor.py` / `pipelines_v2.py` | O((T−w)/s × N) 仅显式调用 | E3 | A9–A10 |
| **E6** | 清理/测试/版本/文档 | 3 个函数 + 9 个既有测试/脚本 + 2 个新测试文件 | — | E1–E5 | A2, A13–A17 |
| **E7** | 消融适配: 模式映射 + 2 臂 | `backtest/ablation_runner.py` + 2 测试文件 | — | E2 | A12 |

### 0.2 规模、依赖与版本

| 项 | 值 |
|----|-----|
| 新增代码文件 | **1** (`backtest/structural_break_monitor.py`, 约 180 行) |
| 修改代码文件 | **7** (`pipelines_v2.py` / `config_v2.py` / `optimizer.py` / `fingerprint.py` / `factor_fingerprint/__init__.py` / `ablation_runner.py` / `reporting.py` 仅版本) |
| 新增测试文件 | **2** (`test_unified_routing.py` / `test_structural_break_monitor.py`) |
| 新增 pytest 用例 | **20** (T1–T14 + B1–B6) |
| 删除 pytest 用例 | **46** = multi_dim 20 + p0_fixes TestSoftRouting 8 + p3_phase2 8 (test_01/02/03 + test_04/05/06 + test_10/11) + ablation 8 (TestRoutingOverride 5 + random 臂 3) + task1 净删 2 (5 → 3) |
| 改写 pytest 用例 | **17** = ablation 9 (static/dynamic/full_vs_static/bh_fdr/routing_table/b3_full_result/returns_5→2/config_routing_mode + 新增直接注入单测 `test_run_pipeline_injects_mode`) + task1 3 + fix2 5; 另 4 个关联测试文件 (p3_config_extension 12 / p3_phase3_optimizer 53 / p3_phase4_integration 6 / p0_2_pipeline_in_loop 5, 合计 76 用例) 含已删字段引用, 受影响用例按 §8.2 改写或删除, 精确账目 E6 执行时以 pytest 结果锁定 |
| 新增依赖 | **无** (断点监控只用 numpy/pandas; statsmodels 在核心依赖, optuna 在 optional extras 非核心依赖 — 本实施不引入) |
| 新增配置字段 | **8** (`pipeline_mode` / `enable_fingerprint_diagnostics` / `ab_experiment_id` / `enable_break_monitor` / `break_monitor_window` / `break_monitor_stride` / `break_monitor_alpha` / `break_monitor_n_bootstrap`) |
| 删除配置字段 | **5** (`hard_routing_prob` / `merge_alpha` / `ks_alpha` / `mixed_winsor_sigma` / `enable_multi_dim_routing`) |
| 删除 Pydantic 字段 | **5** (上述 4 共享字段 + `transform_aggressiveness`; Unified 无 `enable_multi_dim_routing`) |
| 目标版本 / 缓存代际 | **v3.4.0** / **`v2.3.0-cache`** |

### 0.3 调研 / 设计依据映射

| 实施声明 | 调研文档 | 设计文档 |
|---------|---------|---------|
| 软路由/多维树/混合器零生产调用 | RESEARCH A1/A2 | DESIGN D4 / §2.1 |
| Static≈Mixed (ρ=0.999998) | RESEARCH §4.3 | DESIGN D3 / §3.2 |
| Static↔Dynamic 是换信号 (ρ=0.308) | RESEARCH §4.3 | DESIGN D2 / §2.2 |
| 12 因子 Dynamic 臂 \|IC\| −37.6% | RESEARCH §6.3 | DESIGN §2.2 |
| 标签一致率 49.5% | RESEARCH §4.4 | DESIGN D5 |
| 频率改变标签 | RESEARCH §4.5 | DESIGN D6 / §3.5 |
| 2σ 突变污染 AR(1) | RESEARCH §5.3 | DESIGN D8 / §3.7 |
| 统一横截面秩管道 | RESEARCH §7.1/§7.3 | DESIGN §3.2 |
| 规格日志 / 选择留痕 | RESEARCH §8.3 | DESIGN D7 / §3.6 |
| 断点方法 (Andrews/Bai-Perron/Inclán-Tiao/Perron) | RESEARCH §5.2/§5.4 | DESIGN §3.7 |
| A/B 需 OOS + BH-FDR + DSR | RESEARCH §6.6 (OOS/DSR; BH-FDR 为 DESIGN 新增引用 BH 1995, 非调研内容) | DESIGN §3.9 |

**不实施**: MAD 缩尾 (O1)、Dynamic 组件解耦 (O2)、`migration_threshold` 清理 (O3)、KS 工具接线 (O4)、DuckDB schema 迁移 (O5)、断点调度 (O6)、`routing_threshold_scale` 清理 (O7)。

---

## §1 前置条件与基线

### 1.1 环境与依赖 (spec §13.5)

| 项 | 值 | 来源 |
|---|-----|------|
| 解释器 (实测) | **Python 3.13.5** (Anaconda3) | `python -V` |
| 项目 Python 约束 | `>=3.9` | `pyproject.toml` L10 |
| numpy 约束 / 实测 | `>=1.22.0` / **2.1.3** | `pyproject.toml` L27 / `python -c` |
| pandas 约束 / 实测 | `>=2.0.0` / **2.2.3** | `pyproject.toml` L28 / `python -c` |
| scipy 约束 / 实测 | `>=1.7.0` / **1.15.3** | `pyproject.toml` L29 / `python -c` |
| statsmodels 约束 / 实测 | `>=0.13.0` / **0.14.4** | `pyproject.toml` L33 / `python -c` |
| duckdb 约束 / 实测 | `>=0.10.0` / **2.0.0** (2026-11-10 步骤 9 前置安装, 用户指令) | `pyproject.toml` L32 / `python -c` |
| optuna 约束 / 实测 | `>=3.0.0` (extras `optimizer`) / **5.0.0** (2026-11-10 前置安装, 仅本地测试用, 不改核心依赖) | `pyproject.toml` L49 / `python -c` |
| 工作目录 | `F:\Coding\factor_pipeline` | 仓库根 |
| Git HEAD | `0ff2420` | `git log -1` |
| 新增依赖 | **无** (断点监控只用 numpy/pandas; duckdb/optuna 为本地环境安装, 不改 pyproject) | 静态核对 |

> **环境说明 (2026-11-10 更新)**: 步骤 9 开始前用户指令安装 `duckdb>=0.10.0` (装到 2.0.0) 与 `optuna>=3.0.0` (装到 5.0.0, extras 依赖)。
> 原 v1.0/v1.1 时期的 duckdb 环境排除项 (test_E10 失败 / test_ablation_runner 与 test_task1 无法收集) **已消除**;
> E7 的动态验证 (G2-43) 与 4 个关联文件的运行验证 (G3-8~G3-11) 现在均可执行。
> test_fix1 的 1 个 skipped 为**语义性跳过** (L128: v3.0.0 后 KS 迁移路径废弃, test_02 跳过), 与 duckdb 无关 — v1.1 时期文档将其误归因为 duckdb 环境, 此处更正。

### 1.2 基线 (实施前, 2026-11-10 实测)

命令:

```powershell
python -m pytest -q tests/test_pipelines_v2.py tests/test_p0_fixes.py `
  tests/test_p3_phase2_config_migration.py tests/test_fix2_config_unification.py `
  tests/integration/test_pipeline_truncation_invariance.py `
  tests/test_adapters/test_module_enabled.py tests/test_multi_dim_classifier.py
```

结果 (2026-11-10, duckdb/optuna 安装后复测): **107 passed / 0 failed (46.00s)** — duckdb 安装消除了 v1.0/v1.1 时期的唯一失败项 test_E10。

逐文件收集数 (基线):

| 文件 | 用例数 |
|------|--------|
| `tests/test_pipelines_v2.py` | 13 |
| `tests/test_p0_fixes.py` | 14 |
| `tests/test_p3_phase2_config_migration.py` | 12 |
| `tests/test_fix2_config_unification.py` | 13 |
| `tests/integration/test_pipeline_truncation_invariance.py` | 15 |
| `tests/test_adapters/test_module_enabled.py` | 20 |
| `tests/test_multi_dim_classifier.py` | 20 |
| **合计** | **107** (全部 passed) |

补充基线 (2026-11-10, duckdb/optuna 安装后实测):

| 范围 | 命令 | 结果 |
|------|------|------|
| fix1 | `pytest -q tests/test_fix1_self_factors_bug.py` | **3 passed / 1 skipped** (0.40s; skip 为 L128 语义性跳过 — v3.0.0 后 KS 迁移路径废弃, test_02 跳过, **非 duckdb 环境**) |
| fix3 | `pytest -q tests/test_fix3_version_unification.py` | **7 passed** (duckdb 安装后环境失败消除) |
| E7 两文件 | `pytest -q tests/test_backtest/test_ablation_runner.py tests/unit/test_task1_l2_routing_fix.py` | **104 passed (26.97s)**; 分文件收集: ablation_runner **99** / task1 **5** |
| G0-8 四文件 | `pytest -q tests/test_p3_config_extension.py tests/test_p3_phase3_optimizer.py tests/test_p3_phase4_integration.py tests/test_backtest/test_p0_2_pipeline_in_loop.py` | **75 passed / 1 skipped (17min)**; 分文件收集: extension **12** / phase3_optimizer **53** / phase4 **6** / p0_2 **5**; skip 为 phase3 L1402/L1452 的**运行时条件跳过** (significance_ratio 判定, 既有行为) |
| 性能 T0 (G0-10) | 探针 (%TEMP%\probe_t0.py): 12 因子 × 750 行, `fit+transform` 同进程单次 | **T0 = 13.589s** → A14 门禁 = ≤ **14.27s** (1.05 × T0) |

> 注: phase3_optimizer / phase4 / p0_2 三文件带模块级 `pytest.importorskip("optuna")` (L19/L18/L28), optuna 安装后才能收集 — 未安装时该三文件整模块跳过 (v1.2 §8.2 的 53/6/5 计数即 optuna 可用时的收集数)。

### 1.3 实施后预期

| 指标 | 目标 |
|------|------|
| 新增用例 | 20 (T1–T14 + B1–B6) 全绿 |
| 删除用例 | 46 (multi_dim 20 + p0_fixes 8 + p3_phase2 8 + ablation 8 + task1 净删 2) |
| 改写用例 | 17 (ablation 9 + task1 3 + fix2 5); 另 4 个关联测试文件受影响用例按 §8.2 改写 (账目 E6 锁定) |
| 定向套件新增失败 | **0** |
| 性能 (12 因子 × 750 行) | `fit+transform` ≤ 1.05 × T0 (移除 VR/DF 应更快) |

---

## §2 文件变更清单

| 文件 | 变更类型 | 内容 |
|------|---------|------|
| `pipelines_v2.py` | 修改 | 配置 8 加 5 删; `__post_init__`; 2 个 dataclass; `fit`/`transform` 重构; `_create_pipeline`/`_get_pipeline`; 5 个私有方法; 3 个汇总方法; `monitor_structural_breaks`; 删 3 个模块函数 |
| `config_v2.py` | 修改 | Pydantic 5 删 8 加; 桥接映射; `version` 默认值 |
| `optimizer.py` | 修改 | 搜索空间清空; 弃用警告; `optimize` 守卫; 双向映射收敛 |
| `modules/factor_fingerprint/core/fingerprint.py` | 修改 | `infer_sampling_frequency`; `FactorFingerprinter.compute_ar1_path` |
| `modules/factor_fingerprint/__init__.py` | 修改 | 导出 2 个新符号 |
| `backtest/structural_break_monitor.py` | **新增** | `BreakMonitorConfig` / `StructuralBreakMonitor` |
| `backtest/ablation_runner.py` | 修改 | `routing_mode` 值收缩; `_run_pipeline` 注入模式; 删 `_override_routing`; `run_l2` 2 臂 |
| `reporting.py` | 修改 | `pipeline_version` 默认值 |
| `__init__.py` / `pyproject.toml` / `backtest/cache_manager.py` | 修改 | 版本 / 缓存代际 |
| `tests/test_unified_routing.py` | **新增** | T1–T14 |
| `tests/test_structural_break_monitor.py` | **新增** | B1–B6 |
| `tests/test_multi_dim_classifier.py` | **删除** | 20 用例 |
| `tests/test_p0_fixes.py` | 修改 | 删 `TestSoftRouting` (8) |
| `tests/test_p3_phase2_config_migration.py` | 修改 | 删 8, 保留 4 |
| `tests/test_fix2_config_unification.py` | 修改 | 4 共享字段断言改新字段 |
| `tests/unit/test_task1_l2_routing_fix.py` | 修改/删除 | 5 用例改 2 臂映射 |
| `tests/test_backtest/test_ablation_runner.py` | 修改 | 路由臂用例改写 (TestL2Ablation 9 方法处置, 见 §9.5); `run_all_tests()` 注册同步 |
| `tests/test_p3_config_extension.py` / `tests/test_p3_phase3_optimizer.py` / `tests/test_p3_phase4_integration.py` / `tests/test_backtest/test_p0_2_pipeline_in_loop.py` | 修改 | 已删字段引用清理 (明细见 §8.2); test_p3_phase3_threshold_drift_monitor.py 仅语义残留可选清理 |
| `tests/manual/verify_v2_6_0_manual.py` / `verify_v2_6_0_e7_manual.py` (tests/manual/) 与 `tests/test_backtest/verify_fix3_manual.py` | 修改 | 搜索空间/参数 / 版本第 6 处; 另 4 个 verify_* 手工脚本语义清理 (见 §3.4; 注意 verify_fix3_manual.py 位于 tests/test_backtest/ 而非 tests/manual/) |
| `notebooks/demo_v3_1_0.py` | 修改 | 删除已删函数 import |
| `docs/*` / `DECISIONS.md` / `README.md` / `CHANGELOG.md` | 修改 | ADR-042 + 版本链 + 变更说明 |

---

## §3 E1: 配置面

### 3.1 `PipelineV2Config` (`pipelines_v2.py`)

**新增** (建议插在 `enable_cusum_drift_monitor` 之前, 与"路由/监控"语义相邻):

```python
    # v3.4.0 ADR-042: 统一管道模式 ('unified' | 'dynamic_ab')
    pipeline_mode: str = 'unified'
    # 指纹诊断标签开关 (只读, 不参与路由; 指纹提取本身不受此开关影响)
    enable_fingerprint_diagnostics: bool = True
    # A/B 实验标识 (写入规格日志; 非 A/B 为 None)
    ab_experiment_id: Optional[str] = None

    # v3.4.0 ADR-042: 结构突变监控 (opt-in, 只告警)
    enable_break_monitor: bool = False
    break_monitor_window: int = 250
    break_monitor_stride: int = 20
    break_monitor_alpha: float = 0.05
    break_monitor_n_bootstrap: int = 400
```

**删除**:

| 字段 | 原位置 | 备注 |
|------|--------|------|
| `hard_routing_prob: float = 0.90` | L706 | 唯一消费者 `_get_pipeline_weights` 已删 |
| `merge_alpha: float = 0.50` | L707 | 无消费者 |
| `ks_alpha: float = 0.05` | L708 | 无消费者 |
| `mixed_winsor_sigma: float = 3.0` | L709 | 改由 `MixedFactorPipeline` 默认值 |
| `enable_multi_dim_routing: bool = False` | L724 | 零读取点 |

同时删除 L705 注释 `# v2.1 端到端阈值搜索新增配置 (P3 Phase 2)` 与 L721-L723 的 `enable_multi_dim_routing` 注释块。

**新增 `__post_init__`** (放在 `from_unified` classmethod 之前):

```python
    def __post_init__(self):
        if self.pipeline_mode not in ('unified', 'dynamic_ab'):
            raise ValueError(
                f"pipeline_mode 必须为 'unified' 或 'dynamic_ab', "
                f"实际: {self.pipeline_mode!r}"
            )
```

**验收**: `PipelineV2Config()` 默认 `'unified'`; `PipelineV2Config(pipeline_mode='x')` → `ValueError`; `hasattr(config, 'hard_routing_prob') is False`。

### 3.2 `PipelineV2ConfigUnified` (`config_v2.py`)

**删除 5 个 Pydantic 字段** (L405-L424):

```python
hard_routing_prob / merge_alpha / ks_alpha / mixed_winsor_sigma / transform_aggressiveness
```

**新增字段** (建议放在 `migration_threshold` 之后):

```python
    pipeline_mode: Literal['unified', 'dynamic_ab'] = Field(
        default='unified',
        description="管道模式: unified(统一横截面秩管道) / dynamic_ab(显式 A/B 臂)",
    )
    enable_fingerprint_diagnostics: bool = Field(
        default=True,
        description="是否计算指纹诊断标签 (不影响指纹提取与监控)",
    )
    ab_experiment_id: Optional[str] = Field(
        default=None,
        description="A/B 实验标识 (写入规格日志)",
    )
    enable_break_monitor: bool = Field(
        default=False,
        description="启用结构突变监控 (只告警)",
    )
    break_monitor_window: int = Field(default=250, ge=60)
    break_monitor_stride: int = Field(default=20, ge=1)
    break_monitor_alpha: float = Field(default=0.05, gt=0.0, lt=0.5)
    break_monitor_n_bootstrap: int = Field(default=400, ge=50)
```

> `Literal` 已在 `config_v2.py` 顶部导入; `Optional` 同。

**桥接** `to_pipeline_v2_config` (L467-L539):

- 删除 4 个共享字段的 4 行传参 (L531-L534);
- 新增:

```python
            pipeline_mode=self.pipeline_mode,
            enable_fingerprint_diagnostics=self.enable_fingerprint_diagnostics,
            ab_experiment_id=self.ab_experiment_id,
            enable_break_monitor=self.enable_break_monitor,
            break_monitor_window=self.break_monitor_window,
            break_monitor_stride=self.break_monitor_stride,
            break_monitor_alpha=self.break_monitor_alpha,
            break_monitor_n_bootstrap=self.break_monitor_n_bootstrap,
```

- 更新方法 docstring 的字段映射清单 (L473-L486)。

**版本**: `version: str = Field(default="3.3.7", ...)` L371 → `"3.4.0"`。

**验收**: `PipelineV2ConfigUnified(**{'hard_routing_prob': 0.8}).to_pipeline_v2_config()` 成功 (`extra='ignore'`); 新字段正确映射。

### 3.3 `optimizer.py`

1. **搜索空间** (L47-L56):

```python
# v3.4.0 ADR-042: 路由阈值随统一管道退场, 默认无可搜参数
DEFAULT_SEARCH_SPACE = {}
```

2. **`__init__`** (L143 之后):

```python
        if not self.search_space:
            warnings.warn(
                "EndToEndThresholdOptimizer 默认搜索空间为空 (路由阈值已随 v3.4.0 "
                "统一管道退场); 如需正交化搜索请传 search_orth=True",
                DeprecationWarning,
                stacklevel=2,
            )
```

> 需在文件顶部 `import warnings` (若未导入)。

3. **`optimize`** (L784 之后):

```python
        if not self.search_space:
            raise ValueError(
                "无参数可搜索: 路由阈值已随统一管道退场; "
                "如需正交化搜索请传 search_orth=True"
            )
```

4. **约束检查** (L813-L816) 加字段存在性守卫:

```python
            if ('classification_threshold_static' in params
                    and 'classification_threshold_dynamic' in params
                    and params['classification_threshold_static']
                    <= params['classification_threshold_dynamic']):
                return -1.0
```

5. **`_params_to_config`** (L156-L211) 收敛为:

```python
        config = PipelineV2Config()

        if 'classification_threshold_static' in params:
            config.classification.static_ar1_threshold = params['classification_threshold_static']
        if 'classification_threshold_dynamic' in params:
            config.classification.dynamic_ar1_threshold = params['classification_threshold_dynamic']
        if 'migration_threshold' in params:
            config.migration_threshold = params['migration_threshold']
            config.monitor.enable_smooth_transition = True
```

删除 `transform_aggressiveness` 分支 (L173-L180) 与 4 个共享字段构造参数 (L161-L164)。

6. **`_config_to_params`** (L213-L224) 收敛为:

```python
        return {
            'classification_threshold_static': config.classification.static_ar1_threshold,
            'classification_threshold_dynamic': config.classification.dynamic_ar1_threshold,
            'migration_threshold': getattr(config, 'migration_threshold', 0.10),
        }
```

**验收**: `DEFAULT_SEARCH_SPACE == {}`; 默认实例化发 `DeprecationWarning`; `optimize(...)` 抛 `ValueError`; `search_orth=True` 时搜索空间为 3 个 orth 参数且可建 study。

### 3.4 手工脚本同批清理

| 文件 | 行 | 改动 |
|------|----|------|
| `tests/manual/verify_v2_6_0_manual.py` | L97 | `len(...) == 8` → `== 0` |
| 同上 | L101 | `len(...) == 11` → `== 3` |
| 同上 | L197-L198 | 删除 5 个已删参数 |
| `tests/manual/verify_v2_6_0_e7_manual.py` | L47/L75/L99/L167 | 删除 5 个已删参数 |
| `tests/test_backtest/verify_fix3_manual.py` | L21 | `EXPECTED_VERSION = "3.3.7"` → `"3.4.0"` (版本链第 6 处; 注意该文件在 tests/test_backtest/ 下, 非 tests/manual/); 内部"5 个预期位置"清单同步补第 6 处 |
| `tests/verify_objective_function.py` (tests/ 根, 非 pytest 收集) | — | 引用已删字段 7 处; 手工脚本语义清理或顶部标注弃用 |
| `tests/test_backtest/verify_fix2_manual.py` / `verify_p0_2_manual.py` / `verify_p2_2_manual.py` (均非 pytest 收集) | — | 引用已删字段 20/24/25 处; 手工脚本语义清理或标注弃用 |

---

## §4 E2: 统一执行

### 4.1 新增数据类 (`pipelines_v2.py`, 配置类之后)

```python
@dataclass(frozen=True)
class FingerprintMeta:
    """指纹采集元数据 — 不进入 21 维数值指纹契约."""
    sampling_frequency: str = 'unknown'
    n_obs: int = 0
    n_columns: int = 0
    start: Optional[str] = None
    end: Optional[str] = None


@dataclass(frozen=True)
class FactorRoutingRecord:
    """单因子的执行事实 + 诊断标签 (唯一可信来源)."""
    factor_name: str
    pipeline_mode: str
    execution_pipe_type: str
    diagnostic_type: str
    diagnostic_prob: float
    diagnostic_confidence: float
    ar1_median: float
    fingerprint_meta: FingerprintMeta
```

### 4.2 `__init__` 新增状态

在 `self.factor_classifications` / `self.factor_pipelines` 附近:

```python
        self.factor_routing: Dict[str, FactorRoutingRecord] = {}
        self.break_alerts: Dict[str, Dict] = {}
```

### 4.3 `fit` 重构 (核心)

**删除**:

```python
        from factor_pipeline.modules.statistical_classifier import StatisticalClassifier
        stat_clf = StatisticalClassifier(alpha=0.05, vr_q=5)
        pipe_type = stat_clf.classify(factor_data[name])
```

**新流程** (保留既有输入校验与异常包装):

```python
        # Step 1: 指纹提取 (始终执行, 供 monitor/迁移/记录)
        try:
            fingerprints = self.fingerprinter.batch_extract(factor_data)
        except Exception as e:
            logger.error(f"指纹提取失败: {e}")
            raise RuntimeError(f"指纹提取失败，请检查数据格式: {e}") from e

        # Step 2: 诊断标签 (受开关控制)
        classifications = {}
        if self.config.enable_fingerprint_diagnostics:
            classifications = self._classify_diagnostics(
                fingerprints, descriptions, kwargs)

        # Step 3: 执行管道由模式唯一决定
        pipe_type = 'static' if self.config.pipeline_mode == 'unified' else 'dynamic'
        neutralizer_params = self._build_neutralizer_params(
            industry_data, market_cap_data)

        # Step 4: 逐因子拟合
        for name, df in factor_data.items():
            pipe = self._create_pipeline(
                pipe_type, neutralizer_params, self.config.module_enabled)
            pipe.fit(df, **kwargs)
            self.factor_pipelines[name] = {pipe_type: pipe}

            fp = fingerprints.get(name, FactorFingerprint())
            cls = classifications.get(name, self._unknown_classification())
            self.factor_classifications[name] = cls

            self.factor_routing[name] = FactorRoutingRecord(
                factor_name=name,
                pipeline_mode=self.config.pipeline_mode,
                execution_pipe_type=pipe_type,
                diagnostic_type=cls.primary_type.value,
                diagnostic_prob=cls.primary_prob,
                diagnostic_confidence=cls.confidence,
                ar1_median=fp.ar1_median,
                fingerprint_meta=FingerprintMeta(
                    sampling_frequency=infer_sampling_frequency(df.index),
                    n_obs=int(df.shape[0]),
                    n_columns=int(df.shape[1]),
                    start=self._fmt_ts(df.index.min()) if len(df.index) else None,
                    end=self._fmt_ts(df.index.max()) if len(df.index) else None,
                ),
            )
            self._log_spec(self.factor_routing[name])

        # Step 5: 兼容属性
        if self.factor_pipelines:
            first_pipes = next(iter(self.factor_pipelines.values()))
            self.static_pipeline = first_pipes.get('static')
            self.dynamic_pipeline = first_pipes.get('dynamic')
            self.mixed_pipeline = None

        # Step 6: 监测器 (始终执行)
        for name, fp in fingerprints.items():
            self.monitor.add_fingerprint(name, fp)

        self.is_fitted = True
        return self
```

**新增私有方法**:

```python
    def _classify_diagnostics(
        self,
        fingerprints: Dict[str, FactorFingerprint],
        descriptions: Optional[Dict[str, str]],
        kwargs: dict,
    ) -> Dict[str, ClassificationResult]:
        """只产诊断标签, 不选管道. 逻辑与 v3.3.7 fit Step 2 一致."""
        if not descriptions:
            return self.classifier.batch_classify(fingerprints)

        data_months = kwargs.get('data_months', {})
        out = {}
        for name, fp in fingerprints.items():
            desc = descriptions.get(name, "")
            months = data_months.get(name, 0) if isinstance(data_months, dict) else 0
            if desc:
                result = self.semantic_fusion.classify(desc, fp, months)
            else:
                result = self.classifier.classify(fp)
            out[name] = result
            if hasattr(result, 'conflict_reason') and result.conflict_reason:
                logger.warning(
                    f"Factor {name}: semantic-statistical conflict - "
                    f"{result.conflict_reason}"
                )
        return out

    @staticmethod
    def _build_neutralizer_params(industry_data, market_cap_data) -> dict:
        params = {}
        if industry_data is not None:
            params['industry_data'] = industry_data
        if market_cap_data is not None:
            params['market_cap_data'] = market_cap_data
            params['neutralization_type'] = 'industry_marketcap'
        return params

    @staticmethod
    def _unknown_classification() -> ClassificationResult:
        return ClassificationResult(
            primary_type=FactorType.UNKNOWN, primary_prob=0.0, confidence=0.0)

    @staticmethod
    def _fmt_ts(ts) -> Optional[str]:
        try:
            return pd.Timestamp(ts).isoformat()
        except Exception:
            return None
```

### 4.4 `transform`

将 L1431-L1436 的"未分类则跳过"替换为"未拟合则跳过", 并**保留 mock 兜底** (既有测试直接注入扁平属性):

```python
            pipes = self.factor_pipelines.get(name)
            if pipes:
                pipe_type = next(iter(pipes))
                pipe = pipes[pipe_type]
            else:
                # 兜底 (mock/旧调用): 按诊断类型取扁平属性; 仅当 fit 未填
                # factor_pipelines 时可达, 生产路径不会进入
                classification = self.factor_classifications.get(name)
                if classification is None:
                    if self.strict_mode:
                        raise ValueError(f"因子 {name} 未在 fit 阶段分类/拟合")
                    logger.warning(f"因子 {name} 未拟合，跳过")
                    continue
                pipe = self._get_pipeline(classification.primary_type)
                if pipe is None:
                    logger.warning(f"因子 {name} 无可用管线，跳过")
                    continue
```

保留 `_intermediate_data` 提升与 `post_transform_hooks` 循环不变。

### 4.5 工厂与兼容

`_create_pipeline`:

- `static` / `dynamic` 分支不变;
- `mixed` 分支删除 `mixed_winsor_sigma=self.config.mixed_winsor_sigma`, 其余不变 (依赖 `MixedFactorPipeline.__init__` 默认 3.0)。

`_get_pipeline` (mock/旧调用兜底; 生产路径不调用):

```python
    def _get_pipeline(self, factor_type: FactorType):
        # 兼容 mock: 优先按类型取扁平属性 (既有测试直接注入三条管道)
        pipe = {
            FactorType.STATIC: self.static_pipeline,
            FactorType.DYNAMIC: self.dynamic_pipeline,
            FactorType.MIXED: self.mixed_pipeline,
        }.get(factor_type)
        if pipe is not None:
            return pipe
        # 模式兜底
        if self.config.pipeline_mode == 'dynamic_ab':
            return self.dynamic_pipeline
        return self.static_pipeline
```

> `test_fix1_self_factors_bug.py` / `test_p0_fixes.py` 的 mock 场景依赖该兜底; 生产 `fit` 总会填充 `factor_pipelines`, 因此不改变实际执行。

### 4.6 汇总方法

1. `get_classification_summary()` 保留旧列并追加 2 列:

```python
    def get_classification_summary(self) -> pd.DataFrame:
        rows = []
        for name, cls in self.factor_classifications.items():
            rec = self.factor_routing.get(name)
            rows.append({
                'factor_name': name,
                'primary_type': cls.primary_type.value,
                'primary_prob': cls.primary_prob,
                'secondary_type': cls.secondary_type.value if cls.secondary_type else None,
                'secondary_prob': cls.secondary_prob,
                'confidence': cls.confidence,
                'is_hard': cls.is_hard,
                'execution_pipe_type': rec.execution_pipe_type if rec else None,
                'sampling_frequency': (
                    rec.fingerprint_meta.sampling_frequency if rec else None),
            })
        return pd.DataFrame(rows)
```

2. 新增 `get_routing_summary()`:

```python
    def get_routing_summary(self) -> pd.DataFrame:
        rows = []
        for name, r in self.factor_routing.items():
            rows.append({
                'factor_name': name,
                'pipeline_mode': r.pipeline_mode,
                'execution_pipe_type': r.execution_pipe_type,
                'diagnostic_type': r.diagnostic_type,
                'diagnostic_prob': r.diagnostic_prob,
                'diagnostic_confidence': r.diagnostic_confidence,
                'ar1_median': r.ar1_median,
                'sampling_frequency': r.fingerprint_meta.sampling_frequency,
                'n_obs': r.fingerprint_meta.n_obs,
                'n_columns': r.fingerprint_meta.n_columns,
                'start': r.fingerprint_meta.start,
                'end': r.fingerprint_meta.end,
            })
        return pd.DataFrame(rows)
```

3. `get_execution_summary()` 改为"执行管道 + 指纹诊断"两段 (不再把诊断标签写成执行结果)。

**验收**: `factor_pipelines[name]` 键恒为 `'static'` 或 `'dynamic'`; 默认无 `MixedFactorPipeline`; `get_routing_summary()` 行数 = 因子数。

---

## §5 E3: 诊断层

### 5.1 `infer_sampling_frequency` (`fingerprint.py` 模块级)

```python
def infer_sampling_frequency(index: pd.Index) -> str:
    """按索引相邻间隔中位数判定采样频率 (自然日).

    <1 intraday / ≤2 daily / ≤8 weekly / ≤20 biweekly /
    ≤45 monthly / ≤135 quarterly / ≤400 annual / 其他 irregular.
    非 DatetimeIndex 或有效间隔 <2 → 'unknown'.
    """
    if not isinstance(index, pd.DatetimeIndex) or len(index) < 3:
        return 'unknown'
    deltas = (
        pd.Series(index.sort_values())
        .diff().dt.total_seconds().div(86400.0).dropna()
    )
    deltas = deltas[deltas > 0]
    if len(deltas) < 2:
        return 'unknown'
    med = float(deltas.median())
    if med < 1:
        return 'intraday'
    if med <= 2:
        return 'daily'
    if med <= 8:
        return 'weekly'
    if med <= 20:
        return 'biweekly'
    if med <= 45:
        return 'monthly'
    if med <= 135:
        return 'quarterly'
    if med <= 400:
        return 'annual'
    return 'irregular'
```

### 5.2 `FactorFingerprinter.compute_ar1_path`

```python
    def compute_ar1_path(self, factor_data: pd.DataFrame,
                         window: int = 250, stride: int = 20) -> pd.Series:
        """逐窗口计算 AR(1) 中位数路径 (与指纹同一口径)."""
        if window <= 0 or stride <= 0:
            raise ValueError("window/stride 必须为正整数")
        if factor_data is None or factor_data.empty or len(factor_data) < window:
            return pd.Series(dtype=float)
        dates, values = [], []
        for end in range(window, len(factor_data) + 1, stride):
            sub = factor_data.iloc[end - window:end]
            dates.append(factor_data.index[end - 1])
            values.append(self._compute_ar1_median(sub))
        return pd.Series(values, index=pd.Index(dates, name='date'), dtype=float)
```

### 5.3 导出

`modules/factor_fingerprint/__init__.py`:

- `from .core.fingerprint import ..., infer_sampling_frequency`
- `__all__` 追加 `'infer_sampling_frequency'`

`pipelines_v2.py` 顶部现有导入块:

```python
from factor_pipeline.modules.factor_fingerprint import (
    FactorFingerprinter, FactorFingerprint, FactorType,
    FingerprintConfig,
    AdaptiveFactorClassifier, ClassificationConfig, ClassificationResult,
    FactorFingerprintMonitor, MonitorConfig,
    SemanticStatisticalFusion, SemanticPrior, ArbitratedResult,
)
```

追加 `infer_sampling_frequency` (E2/E3 任一提交内完成, 否则 `fit` 引用未定义符号)。

**验收**: T7 (日频/周频/月频/不规则/非日期); `compute_ar1_path` 长度 = `⌊(T−w)/s⌋+1` (1472/250/20 → 62)。

---

## §6 E4: 规格日志

`_log_spec` (私有方法, 全函数 `try/except` 包裹, 失败仅 warning):

```python
    def _log_spec(self, record: FactorRoutingRecord) -> Optional[str]:
        if not getattr(self.config, 'enable_specification_logger', False):
            return None
        try:
            if self._spec_logger is None:
                from backtest.specification_logger import SpecificationLogger
                self._spec_logger = SpecificationLogger(
                    log_dir=self.config.spec_log_dir)
            try:
                from backtest.cache_manager import CODE_VERSION as _CACHE_VERSION
            except Exception:
                _CACHE_VERSION = 'unknown'
            is_static = record.execution_pipe_type == 'static'
            return self._spec_logger.log_run(
                config={
                    'pipeline_mode': record.pipeline_mode,
                    'execution_pipe_type': record.execution_pipe_type,
                    'diagnostic_type': record.diagnostic_type,
                    'diagnostic_prob': record.diagnostic_prob,
                    'ar1_median': record.ar1_median,
                    'sampling_frequency': record.fingerprint_meta.sampling_frequency,
                    'n_obs': record.fingerprint_meta.n_obs,
                    'n_columns': record.fingerprint_meta.n_columns,
                    'winsor': 'percentile(1,99)' if is_static else 'none',
                    'transformation': (
                        f"{self.config.static_transformation_method}"
                        f"->{self.config.static_target_distribution}"
                        if is_static else 'ar_residual->z_score'),
                    'ab_experiment_id': self.config.ab_experiment_id,
                    'cache_version': _CACHE_VERSION,
                },
                result={'n_columns': record.fingerprint_meta.n_columns},
                run_type=('validation' if self.config.ab_experiment_id
                          else 'exploratory'),
                factor_name=record.factor_name,
            )
        except Exception as e:
            logger.warning(f"规格日志写入失败 (不影响拟合): {e}")
            return None
```

**验收**: 开启时 JSONL 行数 = 因子数, 每行含 `execution_pipe_type`/`sampling_frequency`; 默认关闭时 `logs/specifications/` 不被创建 — 注意懒初始化的是**管道侧** `self._spec_logger` (仅首次 `_log_spec` 通过开关检查后才构造 `SpecificationLogger`); `SpecificationLogger.__init__` 本身在构造时即 `os.makedirs` (非懒, spec_log.py L32-34), 因此"目录不创建"由"构造从未发生"保证, 而非 logger 自身懒建目录。

---

## §7 E5: 结构突变监控

### 7.1 新模块 `backtest/structural_break_monitor.py`

```python
# -*- coding: utf-8 -*-
"""结构突变监控 (v3.4.0 ADR-042).

输入: AR(1) 中位数路径 (FactorFingerprinter.compute_ar1_path).
输出: 只读告警字典; 不参与路由/不修改因子值.

方法:
- 'sup_f': 未知断点 sup-F 型统计量 (Andrews 1993), 零分布用 AR(1) 代理自助.
- 'cusum': Inclán-Tiao (1994) ICSS 思路的工程化变体, 同一自助框架.
"""
```

数据类与接口:

```python
@dataclass
class BreakMonitorConfig:
    method: str = 'sup_f'
    window: int = 250
    stride: int = 20
    min_points: int = 20
    trim: float = 0.15
    alpha: float = 0.05
    n_bootstrap: int = 400
    random_state: int = 42


class StructuralBreakMonitor:
    def __init__(self, config: Optional[BreakMonitorConfig] = None):
        self.config = config or BreakMonitorConfig()
        if self.config.method not in ('sup_f', 'cusum'):
            raise ValueError(...)
        if not (0.0 < self.config.trim < 0.5):
            raise ValueError(...)

    def detect(self, path: pd.Series) -> Dict[str, Any]:
        ...
```

`detect` 返回:

```python
{
    'detected': bool,
    'method': str,
    'stat': float,
    'p_value': float,
    'break_index': Optional[int],
    'break_date': Optional[str],
    'n_points': int,
    'alpha': float,
    # 数据不足时:
    # 'reason': 'insufficient data'
}
```

实现要点:

1. 清洗: `y = path.dropna()`; `n < min_points` → `detected=False, reason`。
2. `_sup_f_stat(y, trim)`:
   - 候选断点 `k ∈ [ceil(n*trim), n−ceil(n*trim)]`;
   - 两段均值模型的 `SSR1(k)`; 零模型 `SSR0`;
   - 统计量 `max_k (SSR0−SSR1(k))/max(SSR1(k), 1e-12)`;
   - 返回 `(stat, argmax_k)`。
3. `_cusum_stat(y)`:
   - `z = (y − mean(y))**2`; `s = z.sum()`; `s <= 1e-12` → 返回 `(0.0, None)`;
   - `d = cumsum(z)/s`;
   - `stat = max_k |d_k − (k+1)/n| * sqrt(n)`; 返回 `(stat, argmax_k)`。
4. `_bootstrap_pvalue(y, observed_stat)`:
   - OLS 拟合 `y_t = c + φ y_{t−1} + e_t`; 残差去中心;
   - 用 `np.random.default_rng(random_state)` 生成 B 条代理路径 (含 50 期 burn-in);
   - 对每条重算同方法统计量; `p = (1 + #{stat_b >= observed}) / (B + 1)`。
5. `break_index` = 清洗后有效路径位置 (`y = path.dropna()` 上的 `argmax_k`; 前导 NaN 会使其小于原始行号); `break_date` = `y.index[argmax_k]` 的字符串。

**方法学注记** (设计 §3.7 / m10, 实现时不得省略):

- 统计量只报 SSR 比值, **省略 F 自由度归一化** — p 值完全由自助零分布提供, 不依赖渐近 F 分布, 故无需 df 校正;
- 分母下限 `1e-12` 防近常数段 (`SSR1(k)≈0`) 比值爆炸产生虚假 sup;
- `trim=0.15` → 候选 `k ∈ [⌈0.15n⌉, n−⌈0.15n⌉]`, 符合 Andrews (1993) Π=[0.15, 0.85] 截断惯例 (k 取 0/n 端点被排除, 保证两段各有观测);
- **AR(1) 代理自助替代渐近临界值, 为设计自行补充的工程化选择 (设计 m10, 非 Andrews 原文方法)**: IC 路径强自相关使标准 sup-F 渐近零分布失效, 代理自助以 preserving 自相关的 φ-AR(1) 重生成零路径。

### 7.2 管道方法

```python
    def monitor_structural_breaks(
        self,
        factor_data: Dict[str, pd.DataFrame],
        *,
        method: str = 'sup_f',
        window: Optional[int] = None,
        stride: Optional[int] = None,
    ) -> Dict[str, Dict]:
        if not getattr(self.config, 'enable_break_monitor', False):
            return {}
        from backtest.structural_break_monitor import (
            BreakMonitorConfig, StructuralBreakMonitor,
        )
        cfg = BreakMonitorConfig(
            method=method,
            window=window if window is not None else self.config.break_monitor_window,
            stride=stride if stride is not None else self.config.break_monitor_stride,
            alpha=self.config.break_monitor_alpha,
            n_bootstrap=self.config.break_monitor_n_bootstrap,
        )
        # 注: 用 `is not None` 而非 `or` — 显式传 0 时应交给
        # compute_ar1_path 抛 ValueError("window/stride 必须为正整数"),
        # 而不是被 or 当作 falsy 吞掉回退默认值。
        monitor = StructuralBreakMonitor(cfg)
        out = {}
        for name, df in factor_data.items():
            if df is None or df.empty:      # 空因子无路径可算 → 跳过 (不写键)
                continue
            path = self.fingerprinter.compute_ar1_path(
                df, cfg.window, cfg.stride)
            res = monitor.detect(path)
            out[name] = res
            if res.get('detected'):
                self.break_alerts[name] = res
                logger.warning(
                    f"结构突变告警: {name} ({res['method']}), "
                    f"p={res['p_value']:.4f}, date={res.get('break_date')}")
        return out
```

**验收**: 默认关闭返回 `{}`; 开启前后 `transform` 结果 `check_exact=True`; B1–B6 通过。

---

## §8 E6: 清理、测试与发布

### 8.1 删除的代码

| 符号 | 位置 | 处理 |
|------|------|------|
| `_get_pipeline_weights` | `pipelines_v2.py` L54-L97 | 整函数删除 |
| `_get_multi_dim_pipeline_weights` | L104-L225 | 整函数删除 |
| `_apply_weighted_transform` | L228-L271 | 整函数删除 |

> 删除后确认模块内无残留引用 (`grep`), 且 `import` 抛 `ImportError`。

### 8.2 测试文件处置

| 文件 | 动作 | 明细 |
|------|------|------|
| `tests/test_multi_dim_classifier.py` | **删除** | 20 用例 (test_01–test_20) |
| `tests/test_p0_fixes.py` | 删除 `TestSoftRouting` | 8 用例 (test_01–test_08, 含加权混合 test_04/05; test_06 为单管道路由); 保留 `TestThresholdCalibration` 6 用例 |
| `tests/test_p3_phase2_config_migration.py` | 删除 8 用例 | `TestPipelineV2ConfigNewFields` test_01/02/03; `TestGetPipelineWeightsHardRouting` test_04/05/06; `TestTransformConfigPassing` test_10/11; 保留 `TestMixedWinsorSigma` test_07/08/09 + test_12 |
| `tests/test_fix2_config_unification.py` | 改写 5 用例 | test_03/04 改为断言 `pipeline_mode`/`enable_fingerprint_diagnostics` 默认/自定义; test_10/11 round-trip 改为新字段; test_12 改为 `_config_to_params` 新返回 |
| `tests/test_pipelines_v2.py` | 微调 | 集成测试打印列可用 `execution_pipe_type`; 其余不改 |
| `tests/integration/test_pipeline_truncation_invariance.py` | 不改 | 三管道类仍存在; 顶层 routes 恒 `['static']` 仍满足两用例 |
| `tests/test_adapters/test_module_enabled.py` | 不改 | `_create_pipeline('mixed', {}, me)` 分支保留 |
| `tests/unit/test_task1_l2_routing_fix.py` | 改写/删除 | 5 用例 (L38/52/66/80/94) → 3 用例 (2 臂映射 + 1 个 `run_l2` 计数), 净删 2 |
| `tests/test_backtest/test_ablation_runner.py` | 改写/删除 | `TestL2Ablation` **9 方法** (L1094/1106/1118/1131/1146/1161/1176/1198/1214): 改写 6 (static→unified L1094 / dynamic→dynamic_ab L1106 / full_vs_static→unified vs dynamic L1161 / bh_fdr 4→2 L1176 / routing_table 表名断言 L1198 / b3_full_result len 3 & call 2 L1214), 删 3 (random 臂 L1118/1131/1146); `test_run_l2_returns_5_results` (L620 → 2); `test_l2_config_routing_mode` (L419); `TestRoutingOverride` (5, L1833-1910) 删除; `run_all_tests()`/suite 注册同步 (见下行) |
| `tests/test_p0_fixes.py` + `tests/test_p3_phase2_config_migration.py` 的 `run_all_tests()` 注册 | 微调 | `test_p0_fixes.py` L808 删除 `TestSoftRouting` 的 `suite.addTests` 行; `test_p3_phase2_config_migration.py` L281-282 删除已删测试类的注册行 (否则脚本模式直接 NameError) |
| `tests/test_p3_config_extension.py` | 改写/删除 | 12 用例, 已删字段引用 141 处; 受影响用例改为新字段断言或删除 (与 test_p3_phase2 同批处理) |
| `tests/test_p3_phase3_optimizer.py` | 改写 | 53 用例, 已删字段引用 63 处 (含 `DEFAULT_SEARCH_SPACE`/`_params_to_config` 共 88 处); 搜索空间/参数映射相关用例按 §3.3 新契约改写 (空空间警告 / 3 参数契约 / optimize 抛 ValueError) |
| `tests/test_p3_phase4_integration.py` | 改写 | 6 用例; L121-138 test_03 与 L140+ test_04 依赖 `optimize` 产出 4 个已删字段, 且空默认搜索空间下 `optimize` 抛 `ValueError` → 改 `search_orth=True` 或改断言 `ValueError` |
| `tests/test_backtest/test_p0_2_pipeline_in_loop.py` | 改写 | 5 用例; L189-236 `_params_to_config` 8 参数映射与 `transform_aggressiveness` 用例按 §3.3 收敛后契约改写 |
| `tests/test_p3_phase3_threshold_drift_monitor.py` | 不改 (语义残留) | L29/L36 `best_params={'hard_routing_prob': 0.9}` 为 mock 字典, 删字段后仍通过; 建议同批改为新字段 (可选) |
| `tests/manual/*` | 改参数 | 见 §3.4 (含 verify_fix3_manual 版本第 6 处与 3 个 verify_* 手工脚本) |
| `notebooks/demo_v3_1_0.py` | 改 import | 删除 `_get_pipeline_weights` 导入与演示段 |

> 注: `tests/unit/test_mixed_winsorize_cross_sectional.py` L37 的 `mixed_winsor_sigma=sigma` 是 `MixedFactorPipeline.__init__` 参数 (保留), **不受本次删除影响**, 勿误改。

### 8.3 版本 / 缓存 / 文档

| 文件 | 位置 | 改动 |
|------|------|------|
| `__init__.py` | L58 | `__version__ = "3.4.0"` |
| `pyproject.toml` | L7 | `version = "3.4.0"` |
| `config_v2.py` | L371 | `version` 默认 `"3.4.0"` |
| `reporting.py` | L40 | `pipeline_version = "3.4.0"` |
| `tests/test_fix3_version_unification.py` | L33 | `EXPECTED_VERSION = "3.4.0"` |
| `tests/test_backtest/verify_fix3_manual.py` | L21 | `EXPECTED_VERSION = "3.4.0"` (版本链第 6 处, 见 §3.4; 位于 tests/test_backtest/) |
| `backtest/cache_manager.py` | L58 | `CODE_VERSION = "v2.3.0-cache"` |
| `README.md` | L52 / 版本表 | 3.4.0 / `v2.3.0-cache` + v3.4.0 行 |
| `CHANGELOG.md` | 顶部 | v3.4.0 条目 (见附录 C) |
| `DECISIONS.md` | ADR 索引 + 正文 | ADR 编号待分配 (当前空闲 ADR-042, 落库时取号; 见附录 B) |
| `docs/PROJECT_STATUS.md` / `docs/DEV_PROGRESS.md` / `docs/ARCHITECTURE.md` | 版本/状态 | 同步 v3.4.0 与统一管道架构描述 |

---

## §9 E7: 消融框架适配

### 9.1 `AblationConfig`

`routing_mode` 允许值收缩:

```python
    # v3.4.0 ADR-042: 'full'(默认) | 'unified' | 'dynamic'
    routing_mode: str = 'full'
```

`random_seed` 字段保留 (无消费者, 但避免破坏外部构造); 或在同一提交删除并清理 `test_l2_config_routing_mode`。**本实施选择保留字段、删除语义** (减少兼容面)。

### 9.2 `_run_pipeline`

在 `_apply_l3_overrides` / `_apply_l4_overrides` 之后、管道实例化之前注入:

```python
        if config.routing_mode not in ('full', 'unified', 'dynamic'):
            raise ValueError(
                f"未知 routing_mode={config.routing_mode!r}; "
                f"合法值: 'full' | 'unified' | 'dynamic'"
            )
        if config.routing_mode == 'dynamic':
            modified_config.pipeline_mode = 'dynamic_ab'
        else:
            modified_config.pipeline_mode = 'unified'
```

删除 fit 后的 `if config.routing_mode != 'full': self._override_routing(...)` 调用 (L558-559, 含其上方的 P0-2 注释)。

### 9.3 删除 `_override_routing`

整方法删除 (L575-L630)。

### 9.4 `run_l2` 收缩为 2 臂

```python
        routing_configs = [
            ('L2_unified', 'unified'),
            ('L2_dynamic', 'dynamic'),
        ]
```

`b3_full_result` 提供时追加为参照; 不提供时返回 2 个结果 (不再跑 `routing_mode='full'` 的重复臂)。同步更新 docstring 的过时字样, 共 **3 处**: `run_l2` docstring 的"5 配置" (L983) 与"返回 5 个 AblationResult" (L985), `generate_report` 的"4. L2 路由消融表 (5 配置)" (L1410 → "(2 臂 + 可选参照)"; L1411 的 L3 "~25 配置" 与本任务无关, 不改); 以及 `test_l2_report_has_routing_table` 的表名断言 (若表名含 "5 配置" 字样)。

### 9.5 测试改写对照

> **捕获基建约束 (步骤 6 review C1)**: `_capture_pipeline_configs` (L871-893) monkeypatch 的是 `_run_pipeline`, 其 `captured['config']` 为 **`AblationConfig`** — 该类没有 `pipeline_mode` 字段 (`pipeline_mode` 注入发生在 `_run_pipeline` 内部的 `modified_config` 上, 而 stub 场景下原 `_run_pipeline` 根本不执行)。因此模式断言的对象是 **`captured['config'].routing_mode`** (run_l2 构造臂配置时已写入), 不得断言 `captured['config'].pipeline_mode` (会 `AttributeError`)。若需直接观测注入的 `pipeline_mode`, 见下方新增的直接单测。

| 原用例 | 新用例 |
|--------|--------|
| `TestL2Ablation::test_all_static_uses_static_pipeline` (L1094) | `test_unified_sets_routing_mode`: 断言 `captured['config'].routing_mode == 'unified'` |
| `test_all_dynamic_uses_dynamic_pipeline` (L1106) | `test_dynamic_sets_routing_mode`: 断言 `captured['config'].routing_mode == 'dynamic'` |
| `test_random_routing_reproducible` / `test_random_routing_different_from_full` / `test_full_vs_random_significant_or_not` (L1118/1131/1146) | 删除 (random 臂退场) |
| `test_full_vs_static` (L1161) | 改写为 `test_unified_vs_dynamic_comparison`: unified 臂 vs dynamic 臂的显著性对比 (保留对比路径覆盖, 臂数 2) |
| `test_run_l2_returns_5_results` (L620) | `test_run_l2_returns_2_results` |
| `test_run_l2_accepts_b3_full_result` (L1214) | `len == 3` / `call_count == 2` |
| `test_l2_bh_fdr_4_comparisons` (L1176) | `test_l2_bh_fdr_2_comparisons` |
| `test_l2_report_has_routing_table` (L1198) | 保留, 表名/行数断言改为 2 臂口径 |
| `TestRoutingOverride` (5, L1833-1910) | 删除 (方法已删) |
| `test_l2_config_routing_mode` (L419) | 断言 `routing_mode='unified'` 可构造 |
| `test_task1` 5 用例 (L38/52/66/80/94) | 2 个模式映射 + 1 个 `run_l2` 计数 (净删 2) |
| (新增) `test_run_pipeline_injects_mode` | **直接单测注入逻辑**: patch `factor_pipeline.pipelines_v2.FactorProcessingPipelineV2` (构造点 L552; `_run_pipeline` 内局部导入, 故 patch 源模块而非 `ablation_runner` 命名空间) 捕获构造参数, 对 `runner._run_pipeline(AblationConfig(routing_mode='dynamic'))` 断言捕获的 `config.pipeline_mode == 'dynamic_ab'`; `'unified'`/`'full'`(→unified) 与非法值 ValueError 同理 — 该用例观测的是真实注入路径, 补上 stub 方案的盲区 |

---

## §10 测试计划 (TDD)

### 10.1 新增 `tests/test_unified_routing.py` (T1–T14)

| # | 用例 | 关键断言 |
|---|------|---------|
| T1 | 默认模式与校验 | `PipelineV2Config().pipeline_mode == 'unified'`; 非法值 `ValueError` |
| T2 | 统一输出逐位等价 | 12 因子; 与 `StaticFactorPipeline(...).fit_transform` `assert_frame_equal(check_exact=True)` |
| T3 | Dynamic A/B 逐位等价 | `pipeline_mode='dynamic_ab'` 与 `DynamicFactorPipeline(...)` 完全一致 |
| T4 | Mixed 不再自动创建 | `factor_pipelines` 值中无 `MixedFactorPipeline` |
| T5 | 删除符号 | `_get_pipeline_weights` 等 `ImportError`; 5 字段 `AttributeError` |
| T6 | 诊断开关 | 关闭时标签全 `unknown`; transform 与开启时 `check_exact=True`; `get_fingerprint_summary()` 非空 |
| T7 | 采样频率 | daily/weekly/monthly/irregular/unknown 五档 |
| T8 | 汇总表 | `get_classification_summary` 含 2 新列; `get_routing_summary` 行数 = 因子数 |
| T9 | 规格日志(开) | 行数 = 因子数; unified 臂 `winsor=percentile(1,99)`; dynamic 臂 `none` |
| T10 | 规格日志(关) | 目录不创建; 行数 0 |
| T11 | 断点监控默认关 | `monitor_structural_breaks(...) == {}` |
| T12 | 断点监控不改输出 | 开启前后 `transform` `check_exact=True` |
| T13 | 未拟合因子 | strict 抛错 / 非 strict 跳过 |
| T14 | 旧 JSON 兼容 | 含 5 个旧字段的 dict → `PipelineV2ConfigUnified(**old)` 成功 |

> T2/T3 的 12 因子沿用调研 §6.2 名单; 若数据不可得, 用固定种子合成面板 (财务型高 AR1 + 价量型低 AR1), 仍满足"逐位等价"。

### 10.2 新增 `tests/test_structural_break_monitor.py` (B1–B6)

| # | 用例 | 关键断言 |
|---|------|---------|
| B1 | 真实滚动路径断点 | **合成面板 T=1472** (window=250, stride=20 → ⌊(1472−250)/20⌋+1 = **62** 点; φ=0.2, 中段 +2σ 均值突变) → `compute_ar1_path` 62 点; `detected=True`; `break_index` 落在污染段 ±3。注: 62 点账目只对本合成面板成立 — 调研 §5.3 场景为 T=750 (仅 26 点), 二者不可混引。另注: AR(1) 对均值突变的响应是**驼峰** (先升后衰减) 而非阶跃, `break_index` 定位的是驼峰峰值而非突变起点, ±3 容差按驼峰机制解释 (断言落在污染段内即可) |
| B2 | 无断点 | 白噪声路径 (seed 固定) `detected=False` |
| B3 | 方差突变 | 后半段方差 **×4**, `cusum` 方法 `detected=True` (×2 在 B=400 自助下可能低于 alpha — 边缘风险; seed 固定下若未检出则加强突变强度并在用例注释注明) |
| B4 | 数据不足 | 空/10 点路径 → `detected=False`, `reason='insufficient data'` |
| B5 | 可复现 | 同输入两次结果完全一致 |
| B6 | 无副作用 | `detect` 不修改输入 Series |

### 10.3 Red / Green 预期

| 阶段 | 预期 |
|------|------|
| Red | T1–T12 / B1–B6 失败 (配置字段不存在/行为仍旧/模块不存在); T13/T14 可能已通过 |
| Green (E1–E5 后) | T1–T4 / T6–T12 通过; T5 待 E6 (符号删除后) |
| Green (E6 后) | T1–T14 + B1–B6 全通过 |
| 回归 | 定向套件新增失败 **0**; 基线 duckdb 失败仍为 1 (环境排除) |

### 10.4 回归命令

```powershell
python -m pytest -q tests/test_unified_routing.py tests/test_structural_break_monitor.py `
  tests/test_pipelines_v2.py tests/test_p0_fixes.py `
  tests/test_p3_phase2_config_migration.py tests/test_fix2_config_unification.py `
  tests/integration/test_pipeline_truncation_invariance.py `
  tests/test_adapters/test_module_enabled.py tests/test_fix1_self_factors_bug.py `
  tests/test_p3_config_extension.py tests/test_p3_phase3_optimizer.py `
  tests/test_p3_phase4_integration.py tests/test_backtest/test_p0_2_pipeline_in_loop.py
```

---

## §11 验收标准 (checklist 输入)

| # | 验收项 | 判据 |
|---|--------|------|
| A1 | 默认模式 | `PipelineV2Config().pipeline_mode == 'unified'`; 非法值 `ValueError` |
| A2 | 字段删除 | 5 个 dataclass 字段 + 5 个 Pydantic 字段 `hasattr` 为 `False`; 3 个函数 `ImportError` |
| A3 | 旧配置兼容 | 含旧字段 JSON → `PipelineV2ConfigUnified` 加载成功且值被忽略 |
| A4 | 统一等价 | T2 逐位相等 (`check_exact=True`) |
| A5 | Dynamic 仅 A/B | 默认不出现 `DynamicFactorPipeline`; `dynamic_ab` 下与直调逐位相等 |
| A6 | Mixed 不自动 | 默认 `factor_pipelines` 仅 `'static'` |
| A7 | 诊断可用 | `factor_routing` 每因子 1 条, 含 `sampling_frequency`/`n_obs`/`ar1_median` |
| A8 | 规格日志 | 开启 → 行数 = 因子数, 双臂 `winsor/transformation` 正确; 关闭 → 无目录 |
| A9 | 断点监控 | 默认 `{}`; 开启可检出 B1/B3 突变 |
| A10 | 监控无副作用 | T12 逐位相等; `break_alerts` 只读 |
| A11 | 优化器 | 默认 `DEFAULT_SEARCH_SPACE == {}`; `optimize` 抛 `ValueError`; `search_orth=True` 可用 |
| A12 | 消融 2 臂 | `run_l2` 2 臂 + 可选参照; 非法 `routing_mode` 抛 `ValueError` |
| A13 | 定向套件 | 新增失败 0; duckdb 环境失败数不增加 |
| A14 | 性能 | 12 因子 × 750 行 `fit+transform` ≤ 1.05 × T0 |
| A15 | 版本/缓存 | 6 处版本 = 3.4.0 (含 `verify_fix3_manual.py`); `CODE_VERSION = v2.3.0-cache`; `test_fix3` 通过 |
| A16 | 文档 | ADR 取号落位 (编号待分配, 落库时回 DECISIONS.md 取号); CHANGELOG/README/PROJECT_STATUS/DEV_PROGRESS/ARCHITECTURE 同步 |
| A17 | 依赖 | `pyproject.toml` 依赖无新增 |

---

## §12 风险、回滚与低效操作排除

### 12.1 风险 (与设计 §7 对齐)

| 风险 | 缓解 |
|------|------|
| 原 dynamic 因子输出变化 | 固定规则后不再随标签漂移; `dynamic_ab` 可复现旧臂 |
| 删除字段破坏外部调用 | 同批清理仓库内全部调用点; CHANGELOG 迁移表 |
| 删除 46 用例导致覆盖下降 | 新增 20 用例覆盖替代路径; 删除的是已删行为 |
| 规格日志写盘失败 | `_log_spec` 全函数兜底 |
| 断点监控成本 | 默认关闭; 62 次/因子 (1472 天) 显式付出 |
| 频率推断误判 | 非 DatetimeIndex → `unknown` |

### 12.2 回滚

无运行时"恢复旧路由"开关 (有意)。回滚 = `git revert` 本次提交; 配置面回滚需同时恢复 5 个字段与 3 个函数。

### 12.3 低效操作排除 (spec §13.5)

| 检查项 | 结论 |
|--------|------|
| 指纹重复提取 | 每因子一次 `batch_extract`; 无逐窗口重算 (断点监控才按 stride 重算) |
| DataFrame 复制 | `fit`/`transform` 未新增全表 copy; 记录仅存标量 |
| 规格日志 I/O | opt-in; 关闭时零 I/O、零目录创建 |
| 断点监控 | opt-in; `O((T−w)/s × N)` 显式调用 |
| 汇总表 | 仅遍历记录字典, 无面板运算 |
| 优化器 | 空搜索空间直接抛错, 不建 study |
| 兼容属性 | 仅从首个因子回填, 无循环复制 |

---

## §13 附录

### 13.1 设计决策映射

| 决策 | 实施位置 |
|------|---------|
| D1 `pipeline_mode` | §3.1 / §3.2 |
| D2 统一 Static | §4.3 / §4.5 |
| D3 1%/99% 统一缩尾 | §4.5 (mixed 分支删 sigma 传参) |
| D4 删 3 函数/4 字段 | §8.1 / §3.1 |
| D5 指纹降级诊断 | §4.3 |
| D6 `FactorRoutingRecord`/`FingerprintMeta` | §4.1 / §5 |
| D7 规格日志 | §6 |
| D8 断点监控 | §7 |
| D9 Mixed/Dynamic 保留 | §4.5 / §9 |
| D10 优化器收缩 | §3.3 |
| D11 版本/缓存/ADR | §8.3 / 附录 B/C |
| D12 无新依赖 | §1.1 / §7.1 |

### 13.2 ADR 正文 (编号待分配 — DECISIONS.md 登记规则 2: 规划文档不得预留编号; 当前空闲号 ADR-042, 暂以其指代, 落库时回 DECISIONS.md 取号)

```markdown
## ADR-042 (暂用号, 落库时取正式编号): 统一横截面秩管道替代三路指纹路由 (v3.4.0)

**背景**: 调研 (docs/analysis/FACTOR_ROUTING_OVERENGINEERING_RESEARCH.md v1.1) 证实:
软路由/五步多维树/线性混合器零生产调用; 默认 sigmoid 下 static/mixed 硬路由不可达;
Static 与 Mixed 输出秩相关 0.999998; 指纹与 VR/DF 标签一致率 49.5%;
12 因子改走 Dynamic 平均 |IC| −37.6%; 路由链无结构突变检测,
而 AR(1) 本身会被 2σ 均值突变污染。

**决策**:
1. `PipelineV2Config.pipeline_mode` 默认 `'unified'`, 所有因子走同一条
   横截面秩管道 (imputer → 1%/99% 缩尾 → 中性化 → CSRankNorm → z);
2. 删除 `_get_pipeline_weights` / `_get_multi_dim_pipeline_weights` /
   `_apply_weighted_transform` 及 5 个只服务路由的配置字段;
3. 指纹降级为只读诊断, 采样频率写入 `FingerprintMeta`;
4. 管道选择/采样频率进入 `SpecificationLogger` (opt-in);
5. 结构突变检测下沉到 `StructuralBreakMonitor`, 只告警;
6. Dynamic 仅作为整臂 `'dynamic_ab'` 显式实验保留。

**后果**:
- 原 static/mixed 因子输出逐位不变; 原 dynamic 因子改走统一管道 (基准稳定化);
- 配置面缩小, 优化器默认搜索空间清空;
- 缓存代际 `v2.2.5-cache` → `v2.3.0-cache`。

**替代方案** (设计 §11):
- 保留三管道但默认 static — 否决: 分类仍在跑, 标签仍会漂移;
- 统一 AR 残差化 — 否决: 实测 |IC| 下降;
- MAD 缩尾 — 延后为独立实验 (O1)。
```

### 13.3 CHANGELOG v3.4.0 草稿

> 房式对齐仓库现有 CHANGELOG (中文条目, `## vX.Y.Z — 标题 (状态, 日期)` + 概览/变更文件/兼容性 分节); 实施落库后按 v3.3.7 条目先例补"实测矩阵"分节。草稿中的 "ADR-042" 为暂用号, 落库时以 DECISIONS.md 取到的正式编号为准。

```markdown
## v3.4.0 — 因子路由统一化治理 (待实施, 2026-11-10)

### 概览

统一横截面秩管道替代三路指纹路由 (**ADR-042**): 默认 `pipeline_mode='unified'`,
所有因子走同一条管道 (ffill → 1%/99% 缩尾 → 中性化 → rank→normal → z-score),
不再按 VR/DF 分类逐因子选管道; 指纹降级为只读诊断;
`DynamicFactorPipeline` 仅经 `pipeline_mode='dynamic_ab'` 整臂保留。

**核心产出**:
- 删除 3 个路由函数: `_get_pipeline_weights` / `_get_multi_dim_pipeline_weights` /
  `_apply_weighted_transform`
- 配置面: dataclass 删 5 字段 (`hard_routing_prob` / `merge_alpha` / `ks_alpha` /
  `mixed_winsor_sigma` / `enable_multi_dim_routing`), Pydantic 删 5 字段
  (上述 4 共享字段 + `transform_aggressiveness`); 新增 8 字段
  (`pipeline_mode` / `enable_fingerprint_diagnostics` / `ab_experiment_id` /
  `enable_break_monitor` / `break_monitor_window` / `break_monitor_stride` /
  `break_monitor_alpha` / `break_monitor_n_bootstrap`)
- 优化器 (ADR-042 联动): `DEFAULT_SEARCH_SPACE` 清空 — 默认实例化发
  `DeprecationWarning`, `optimize` 空空间抛 `ValueError`; `_params_to_config`/
  `_config_to_params` 收敛为 3 参数契约
- 消融适配: `AblationConfig.routing_mode` 收缩为 'full'/'unified'/'dynamic';
  `run_l2` 5 配置 → 2 臂 + 可选参照; 删 `_override_routing`
- Mixed 管道不再自动创建; `mixed_winsor_sigma` 改由 `MixedFactorPipeline`
  默认值 3.0 承担; D9: Mixed/Dynamic 类保留 (仅供显式 A/B 与直调)
- 新增 `get_routing_summary()` / `monitor_structural_breaks()` 管道方法;
  管道选择与采样频率写入 `SpecificationLogger` (opt-in)
- 项目版本 **3.4.0**; 缓存 `CODE_VERSION` **v2.3.0-cache**

### 变更文件

| 文件 | 变更 |
|------|------|
| `pipelines_v2.py` | 配置 8 加 5 删; `fit`/`transform` 统一路由; 删 3 个路由函数; 新增 `FactorRoutingRecord`/`FingerprintMeta` |
| `config_v2.py` | Pydantic 5 删 8 加; 桥接映射; 版本 |
| `optimizer.py` | 搜索空间清空 + 弃用警告 + `optimize` 守卫 |
| `backtest/ablation_runner.py` | `routing_mode` 收缩 3 值; `run_l2` 2 臂; 删 `_override_routing` |
| `backtest/structural_break_monitor.py` | **新增** sup-F / CUSUM 断点监控 (自助 p 值, 只告警) |
| `modules/factor_fingerprint/` | `infer_sampling_frequency` / `compute_ar1_path` |
| `backtest/cache_manager.py` | `v2.3.0-cache` |
| 版本链 6 处 / 文档 6 份 | 3.4.0 / ADR-042 |

### 兼容性

- **不兼容**: 原 dynamic 因子输出变化 (改走统一管道, 历史基准需重算);
  配置面删字段; 需重建缓存 (`v2.2.5-cache` → `v2.3.0-cache`)。
- **兼容**: 旧配置 JSON 可加载 (`extra='ignore'` 忽略已删字段); 三管道类保留;
  公共 `fit`/`transform` 签名不变。
- **迁移**: 依赖 `hard_routing_prob` 等已删字段的代码需删除;
  依赖路由阈值的优化器调用改 `search_orth=True` 或迁移到统一管道语义。

### 已知遗留

- 断点监控为 opt-in 只告警, 未接入调度 (O6);
- MAD 缩尾 / Dynamic 组件解耦 / DuckDB schema 迁移延后 (O1/O2/O5)。

(实施落库后补: 实测矩阵 / 回归结果)
```

### 13.4 复现命令

```powershell
# 基线
python -m pytest -q tests/test_pipelines_v2.py tests/test_p0_fixes.py `
  tests/test_p3_phase2_config_migration.py tests/test_fix2_config_unification.py `
  tests/integration/test_pipeline_truncation_invariance.py `
  tests/test_adapters/test_module_enabled.py tests/test_multi_dim_classifier.py

# 实施后
python -m pytest -q tests/test_unified_routing.py tests/test_structural_break_monitor.py `
  tests/test_pipelines_v2.py tests/test_p0_fixes.py `
  tests/test_p3_phase2_config_migration.py tests/test_fix2_config_unification.py `
  tests/integration/test_pipeline_truncation_invariance.py `
  tests/test_adapters/test_module_enabled.py tests/test_fix1_self_factors_bug.py `
  tests/test_p3_config_extension.py tests/test_p3_phase3_optimizer.py `
  tests/test_p3_phase4_integration.py tests/test_backtest/test_p0_2_pipeline_in_loop.py

# 版本一致性
python -m pytest -q tests/test_fix3_version_unification.py
```

---

## §14 修订记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-11-10 | 步骤 5 初稿: E1–E7 任务分解; 20 个新用例; 31 个删除用例 (初稿口径; 同版 §0.2 计 36, v1.1 m4 勘至 46); 基线 106 passed / 1 duckdb env-fail |
| v1.1 | 2026-11-10 | 步骤 6 幻觉消除 review 修订 (CRITICAL 2 / MAJOR 8 / MINOR 12, 全部修复, 见下方实施 review 结论)。C1 §9.5 捕获基建约束: 断言对象改 `captured['config'].routing_mode` (`AblationConfig` 无 `pipeline_mode` 字段), 补新增直接注入单测 `test_run_pipeline_injects_mode` (patch 构造点 L552); C2 B1 显式声明合成面板 T=1472 (62 点账目仅对此成立, 调研 §5.3 T=750 为 26 点, 不可混引) + 驼峰机制注记。M1 §8.2 清理清单补 4 个 pytest 收集文件: test_p3_config_extension (12 用例/141 处引用) / test_p3_phase3_optimizer (53/63) / test_p3_phase4_integration (6; test_03/04 需 search_orth 或断言 ValueError) / test_p0_2_pipeline_in_loop (5; L189-236); M2 TestL2Ablation 账目 5→**9 方法** (L1094-1214), 补 test_full_vs_static (L1161) 处置 (改写为 unified vs dynamic 对比); M3 §9.4 补 `generate_report` docstring 第二处"5 配置" (L1410); M4 补两文件 `run_all_tests()` 注册清理 (test_p0_fixes L808 / test_p3_phase2 L281-282); M5 §6 验收表述更正: 懒初始化的是管道侧 `_spec_logger`, `SpecificationLogger.__init__` 构造即 `os.makedirs`; M6 §1.2 补 fix1 基线 (3 passed / 1 skipped, 已实测); M7 §13.2 ADR-042 补"替代方案"段 (对齐设计 §11); M8 §13.3 CHANGELOG 重写为仓库中文房式并补 6 类漏项 (优化器行为变更 / 消融适配 / transform_aggressiveness / get_routing_summary+monitor_structural_breaks / 8 新字段 / D9 Mixed 说明)。m1 版本链补第 6 处 `verify_fix3_manual.py` L21 (§0/§3.4/§8.3/A15 同步 5→6 处); m2 §3.4 手工脚本补 `tests/verify_objective_function.py` 与 3 个 verify_* 脚本 (共 76 处引用, 非 pytest 收集); m3 §7.2 `window/stride` 改 `is not None` 守卫 (传 0 交给 compute_ar1_path 抛 ValueError, 不被 or 吞掉); m4 §0.2/§1.3 用例账目精确化 (删 36→46: 补 TestRoutingOverride 5 + random 3 + task1 净删 2; 改写约 14→17); m5 §0.3 BH-FDR 归属更正 (BH 1995 为设计新增引用); m6 §0.2 optuna 精确为 optional extras; m7 §7.1 补 AR(1) 代理自助 = 设计 m10 工程化选择标注; m8 §7.1 补 sup-F 三点注记 (df 归一化省略 / 1e-12 下限 / trim 端点约定); m9 B3 方差突变 ×2→×4 (B=400 下 ×2 边缘风险); m10 §8.2 注明 test_mixed_winsorize_cross_sectional.py L37 为 `MixedFactorPipeline.__init__` 参数不受影响、test_p3_phase3_threshold_drift_monitor.py L29/36 mock 字典仍通过 (语义残留可选清理); m11 §10.4 回归命令补 4 个关联测试文件 |
| v1.2 | 2026-11-10 | 步骤 8 跨文档一致性 review 勘误 (MAJOR 1 / MINOR 5 落在本文件, 全部修复; 详见 docs/audit/CONSISTENCY_REVIEW_V3.4.0.md)。C-1 版本链第 6 处路径勘误: `tests/manual/verify_fix3_manual.py` → **`tests/test_backtest/verify_fix3_manual.py`** (§2/§3.4/§8.3, checklist G4-1/G4-4 同步); C-4 ADR 编号治理: DECISIONS.md 登记规则 2 禁止规划文档预留编号, §0/§8.3/§11-A16/§13.2/§13.3 改为"ADR 编号待分配 (暂用号 ADR-042, 落库时取号)"; m-7 §9.4 docstring 过时字样 2 处→3 处 (补 L985 "返回 5 个 AblationResult"); m-9 §8.2 加权混合用例表述更正 (test_04/05 为加权混合, test_06 为单管道路由); m-5 §14 v1.0 行删除用例数加口径注 (31 初稿 → §0.2 36 → m4 勘 46); m-6 §14 结论补"m 编号≠发现数"口径; §14 v1.0 行同步注记。头/尾版本流转更新 (设计 v1.2 / checklist v1.1 / CONSISTENCY_REVIEW_V3.4.0.md) |
| v1.3 | 2026-11-10 | **步骤 9 TDD 实施落库回填**。(1) Red: T 文件 14 failed / 2 passed (T13 两方法既有行为通过, 机理全部正确); B 文件 ModuleNotFoundError 收集错误 = 模块不存在。(2) Green: E1–E7 全部落盘; 首轮 19P/3F → 修复 2 个真实失败后 **T1–T14 + B1–B6 = 22 passed**。实施期修正 2 处: **T7** irregular 用例原构造 `np.concatenate([[0], np.full(8,450)])` 使 8 个时间点重叠于同一天 (有效间隔仅 1 → unknown), 改等差 `np.arange(9)*450` (8 个间隔全 450 → med>400 → irregular), 属测试构造错误非实现缺陷; **B1** 原"+5σ 均值突变 [700,750)" 使 AR(1) 产生双边界升-降驼峰 (0.2→0.82→0.2, sup-F 单断点模型 p=0.915 无法检出), 且面板 N=6 < FingerprintConfig.min_stocks=10 致路径全 NaN — 改为 φ 0.2→0.8 系数结构突变 @t=700 (路径呈"基线→爬升→平台 0.8"真单断点, 实测 p≈0.0025, break_index=27 ∈ 期望 22±5), N 增至 12; 测试 docstring 已按 B3 同款容错记录偏离。(3) E6/E7: 3 路由函数删 (模块 2209 行, import 探针 hasattr False); 46 用例处置完成 (multi_dim 整文件删 20 / p0_fixes 删 8 / p3_phase2 删 8 / fix2 改 5 / task1 5→3 / ablation 104→95 收集含新增 injects_mode / config_extension 改 11 保 1 / phase3_optimizer 删 2 改 11 增 2 / phase4 6 全改 search_orth / p0_2 删 1 改 4); 4 manual 脚本清理或弃用标注; demo Cell 3 改纯分类诊断。(4) 回归: 靶向 16 文件 **273 passed / 1 既有语义 skip / 0 failed** (批 1 115P/78.75s + 批 2 158P/595.69s); E7 动态 **95 passed** (G2-43); 版本 7 passed; G4-1 复验时修正 test_fix3 docstring 3 处 3.3.7 残留。(5) 版本/文档: 6 处版本 3.4.0 + CODE_VERSION v2.3.0-cache (5 消费类经常量, test_07 守卫通过); **ADR-042 正式取号落库** DECISIONS.md (暂用号恰同正式号); CHANGELOG/README/PROJECT_STATUS/DEV_PROGRESS/ARCHITECTURE 同步。(6) 性能门禁 G5-3 **PASS: ratio=1.0092 ≤ 1.05** — 方法升级: 单次 wall-clock 受桌面负载噪声 ±50% (中位数不可判), 改 **git worktree 检出 0ff2420 同机交替进程 ×5 轮取 min** (base 12.246s vs impl 12.359s); 排障确认初测 40s 系重建探针误传 industry_data (日期索引 Series → NeutralizerAdapter.fit 750 天逐日空转 +10s, 基线探针无此项) + 负载噪声; cProfile 确认 batch_extract 仅 1 次、单因子指纹两版本 0.964s vs 0.928s 无退化。(7) checklist v1.2: Gate 0–7 实际列全填写, 实施签署 PASS; G2-42 按检查意图判定 (TestTransformConfigPassing 类承载保留用例 test_12); G2-14 命中 1 处说明性注释 (fit 不再调用, 代码 0 引用) |

**实施 review 结论** (步骤 6, 2026-11-10): 双轨幻觉消除 review 均为 **PASS with fixes**。
- **轨道 1 (接口/工程核实)**: 约 40 处行号/签名/测试类名抽查全部命中 (pipelines_v2/config_v2/optimizer/ablation_runner/spec_log 及 7 个测试文件); `@dataclass` 非 frozen 支持 deepcopy 后注入 `pipeline_mode`; `PipelineV2ConfigUnified` 桥接/`extra='ignore'` 行为核实; 算术账目自洽 (20 新增 / 107 基线 / 62 滚动点 / 1472−250 窗口账)。发现 CRITICAL 2 / MAJOR 6 / MINOR 4, 已全部修复 (见 v1.1 修订行 C1/C2/M1-M6/m1-m4; 修订行 m10 为顺带落盘项 — m 编号是修订条目号, 不等于各轨道 MINOR 发现数)。
- **轨道 2 (公式/跨文档一致性核实)**: §7.1 四公式 (sup-F / CUSUM-ICSS 变体 / AR(1) 代理自助 / 自助 p 值) 可实现且方法学正确 — sup-F 候选区间恰为 Andrews (1993) [0.15, 0.85] 惯例 (网络核实), CUSUM 与 Inclán-Tiao (1994) ICSS 原式同构 ((y−ȳ)² 工程化变体已标注), 自助 p 值 (1+#{≥})/(B+1) 为标准保守形式; §0.3 十一行映射逐行对齐 (BH-FDR 归属勘误); 依赖 6 项约束/实测值全对; 性能声明 (移除 VR/DF 更快) 站得住。发现 MAJOR 2 / MINOR 8, 已全部修复 (M7/M8/m5-m9/m11)。
- **判定**: 实施文档主体 (统一执行流程 / 配置面 / 清理清单 / 测试计划 / 验收标准) 无需推翻, 全部修复为清单补全、账目精确化与表述更正。**可进入步骤 7 (编写验收 checklist)**。
