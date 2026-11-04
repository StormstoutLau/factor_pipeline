# v3.3.5 PL-06 Mixed 缩尾因果性修复 — 实施文档

**文档版本**: v1.3 (实施完成: §7.2 回填实测; test_09 代码块补形状广播)
**日期**: 2026-11-04
**缺陷**: DEFECT-PL-06
**设计依据**: [docs/analysis/PL06_MIXED_WINSORIZE_LOOKAHEAD_DESIGN.md](analysis/PL06_MIXED_WINSORIZE_LOOKAHEAD_DESIGN.md) v1.1 (A 选定)
**调研依据**: [docs/analysis/PL06_MIXED_WINSORIZE_LOOKAHEAD_RESEARCH.md](analysis/PL06_MIXED_WINSORIZE_LOOKAHEAD_RESEARCH.md) v1.0 (唯一学术/工业依据源, 映射见 §0.3)
**目标版本**: v3.3.5
**变更性质**: 数值行为变更 (Mixed 缩尾估计轴与 fit 状态)
**实施方式**: 严格 TDD (Red → Green → 回归 → 版本/文档)
**规范依据**: [WORKFLOW_METHODOLOGY.md](WORKFLOW_METHODOLOGY.md) v1.3 §13.5 — 工程细节 / 版本 / 依赖 / 兼容 / 接口 / 签名 / 排除低效操作
**spec 位置**: 步骤 5-10 **全部完成** (实施文档 v1.3; 步骤 6 review 无阻塞; 步骤 7 checklist; 步骤 8 一致性 review 6 项修复; 步骤 9 TDD 73 passed; 步骤 10 审计 PASS)
**行号说明**: 文中行号仅作导航, 以类名/函数名/测试名为准 (编辑后会漂移)

---

## §0 实施摘要

| 项 | 内容 |
|---|------|
| 核心改动 | Mixed 缩尾从"按股票全历史 3σ + fit 保存参数"改为"逐日截面 3σ + fit no-op" |
| 代码文件 | `pipelines_v2.py` (`MixedFactorPipeline.fit` / `_apply_winsorize`; 删除 `_compute_winsorize_params`) |
| 测试文件 | 新增 `tests/unit/test_mixed_winsorize_cross_sectional.py`; 重写 `tests/test_p3_phase2_config_migration.py::TestMixedWinsorSigma` 的 test_07/08/09; 修改 `tests/integration/test_pipeline_truncation_invariance.py` |
| 版本同步 | 4 处声明 + 2 处测试/脚本锚点 + 缓存 `CODE_VERSION` |
| 文档 | ADR-039 / CHANGELOG v3.3.5 / ARCHITECTURE / DEV_PROGRESS |
| 验收关键 | PL-06 的 `xfail` 摘除后 `n_diff_cells=0`, `max_abs_diff=0`; 集成套件预期 10 passed / 2 xfailed |

### 0.1 E 任务清单

| E | 目标 | 主要文件 | 复杂度 | 依赖 | 验收 |
|---|------|---------|-------|------|------|
| E1 | `_apply_winsorize` 改为逐日截面 3σ | `pipelines_v2.py` | O(T·N) | 无 | 11 例单测; 截断 0/0 |
| E2 | `fit` Step 2 改为 no-op | `pipelines_v2.py` | O(T·N) | 无 | `_winsorize_params is None` |
| E3 | 删除 `_compute_winsorize_params` | `pipelines_v2.py` | — | 无 | grep 无残留 |
| E4 | 新增 11 例单测 | `tests/unit/test_mixed_winsorize_cross_sectional.py` | — | pytest 既有 | Red 10 失败 / 1 通过 |
| E5 | 重写 test_07/08/09 + 摘 PL-06 xfail | 2 个测试文件 | — | 无 | 12 passed; 集成 10+2 xfailed |
| E6 | 版本/缓存/ADR/CHANGELOG/架构 | 8 个文件 | — | 无 | `test_fix3` 7 passed |

### 0.2 规模、依赖与版本

| 项 | 值 |
|----|-----|
| 新增测试函数 | **11** (公共 7 + A 专属 4) |
| 重写测试 | **3** (`TestMixedWinsorSigma.test_07/08/09`) |
| 集成标记变更 | 摘除 **1** 个 `xfail` (PL-06) |
| 新增依赖 | **无** |
| 删除依赖 | 无 |
| 新增配置字段 | **无** |
| 删除配置字段 | 无 |
| 代码净变更 | 删除约 15 行方法 + 改写 2 处 (约 15 行) |
| 目标版本 / 缓存代际 | v3.3.5 / `v2.2.3-cache` |

### 0.3 调研 / 设计依据映射

| 实施声明 | 调研文档 | 设计文档 |
|---------|---------|---------|
| 缺陷基线 (257/1800, 6.984e-01) | RESEARCH §1.2 | DESIGN §0 / §2.1 |
| 数据契约 (index=日期, columns=股票) | RESEARCH §2.3 | DESIGN §2.2 |
| 小截面事实 (`N≤10` no-op) | RESEARCH §3.6 | DESIGN §3.1.3 |
| 方案 A 实现与实测 (77/3000, 561/3000) | RESEARCH §3.1 / §3.7 | DESIGN §3.2.2 |
| 方案 B 备选与迁移清单 (不实施) | RESEARCH §3.2 | DESIGN §3.3 |
| 配置 / optimizer 耦合 | RESEARCH §5.2 | DESIGN §2.1 / §3.2.3 |
| 既有测试现状 | RESEARCH §5.4 | DESIGN §2.3 |
| 学术 / 工业依据 | RESEARCH §4 / 附录 C | DESIGN §3.4 |
| 验收标准草案 | RESEARCH §6.2 | DESIGN §5 |

**不实施**: B (percentile 1,99)、方法选择器 (A+B 并存)、Mixed 统一走 `ProcessingAdapter(outlier)`、PL-05/PL-07、optimizer 重新调参、Mixed 与 Static 方法口径统一.

---

## §1 前置条件与基线

### 1.1 环境、版本与依赖 (spec §13.5)

| 项 | 值 | 来源 |
|---|-----|------|
| 解释器 (实测) | `C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe` (3.12.10) | `python -c` |
| 项目 Python 约束 | `>=3.9` | `pyproject.toml` L10 `requires-python` |
| pandas 约束 | `>=2.0.0` | `pyproject.toml` L28 `dependencies` |
| pandas 实测 | 2.2.3 | `python -c` |
| numpy 约束 | `>=1.22.0` | `pyproject.toml` L27 |
| 工作目录 | `F:\Coding` (父目录, 避免 `factor_pipeline/types.py` 遮蔽标准库 `types`) | 既有约定 |
| 新增依赖 | **无** (仅用 pandas `mean` / `std` / `clip`) | 静态核对 |
| 删除依赖 | 无 | — |
| 新增配置字段 | **无** | §3.7 / §3.9 |
| 新增测试依赖 | 无 (pytest 已在 `dev` extra) | `pyproject.toml` L51-L54 |

> **版本注意 (既有不一致, 非本次引入)**: 新增测试沿用 `freq='ME'` (与 `tests/integration/test_pipeline_truncation_invariance.py` L107 一致), 该别名需 pandas >= 2.2; 而 `pyproject.toml` 声明 `pandas>=2.0.0`. 这是仓库既有不一致。本任务**不修改**依赖声明, 记录为已知问题, 避免把缺陷修复扩大到依赖版本决策。

### 1.2 基线 (实施前, 2026-11-04 实测)

```powershell
cd F:\Coding
C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe -m pytest `
  factor_pipeline/tests/integration/test_pipeline_truncation_invariance.py -q
```

**实测: 9 passed / 3 xfailed, 6.91s** (PL-05/06/07 登记).

```powershell
C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe -m pytest `
  factor_pipeline/tests/test_pipelines_v2.py `
  factor_pipeline/tests/test_adapters/test_module_enabled.py -q
```

**实测: 33 passed, 4.82s**.

```powershell
C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe -m pytest `
  factor_pipeline/tests/test_p3_phase2_config_migration.py -q
```

**实测: 12 passed, 0.63s**. 其中 `TestMixedWinsorSigma.test_07/08/09` 直接调用 `_compute_winsorize_params`, 锁定的仍是旧 per-column 语义, 实施时必须同步重写.

```powershell
C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe -m pytest `
  factor_pipeline/tests/test_fix3_version_unification.py -q
```

**实测: 7 passed, 0.36s** (锚点 v3.3.4 / `v2.2.2-cache`).

**性能基线** (T=2500, N=3000, 3 次中位数, 2026-11-04 实测):

| 实现 | 中位耗时 | 三次原始值 |
|------|---------|-----------|
| 当前 `_compute_winsorize_params` + `_apply_winsorize` (per-column) | **0.281s** | 0.281 / 0.269 / 0.281 |
| 提案 `X.mean(axis=1)` + `X.std(axis=1, ddof=1)` + `clip(axis=0)` | **0.200s** | 0.200 / 0.209 / 0.193 |

> 调研文档附录的 0.512s / 0.268s 是另一测量口径 (探针内联 lambda). **验收基线为当前实现 0.281s, 目标是不慢于该值; 提案等价计算的 0.200s 仅作参考, 以实施后实际测量为准.**

**PL-06 缺陷基线** (T=100, N=30, seed=23, skewed, t=60, atol=1e-12):

| 指标 | 数值 |
|------|------|
| 差异格子 / 总格子 | **257 / 1800** |
| 有差异行 / 总行 | 31 / 60 |
| `max_abs_diff` | **6.984124662957469e-01** |
| NaN 模式不一致 | 0 |
| 首个发散日期 | **2020-01-31** (第 1 期) |

### 1.3 实施后预期

- 集成套件: **10 passed / 2 xfailed** (PL-05/PL-07; 若 PL-07 意外转绿见 §8 R1).
- Mixed 截断不变式: **0 格 / 0**.
- 新增单测: 11 个函数全部通过.
- 靶向套件全绿; 性能不慢于 0.281s.

---

## §2 E 任务与变更清单

### 2.1 E 任务定义 (spec 阶段 2 模板)

#### E1: `_apply_winsorize` 逐日截面 3σ

| 字段 | 内容 |
|------|------|
| 目标 | 缩尾边界只由当日行计算, 满足截断不变式 |
| 接口设计 | `_apply_winsorize(self, X: pd.DataFrame) -> pd.DataFrame` (签名不变, 见 §3.7) |
| 算法 | `mu = X.mean(axis=1)`; `sd = X.std(axis=1, ddof=1)`; `X.clip(mu-σ·sd, mu+σ·sd, axis=0)` (RESEARCH §3.1) |
| 兼容性 | 配置 / optimizer 契约不变; 输出数值变更 (§3.9) |
| 性能估算 | 时间 `O(T·N)`, 输出内存 `O(T·N)`; 实测 0.200s vs 基线 0.281s (§1.2) |
| 依赖 | 无新增; pandas `mean/std/clip` 在 `>=2.0.0` 可用 |
| TDD 测试 | `test_bounds_are_row_mean_plus_minus_sigma_std` / `test_sigma_monotonicity` / `test_n_le_10_is_noop` / `test_n11_can_clip` (§4.1) |
| 验收标准 | 11 例单测全绿; Mixed 截断不变式 0 格 / 0 (§7.2) |

#### E2: `fit` Step 2 改为 no-op

| 字段 | 内容 |
|------|------|
| 目标 | `fit` 不保存任何跨期缩尾参数 |
| 接口设计 | `fit(self, X: pd.DataFrame, **kwargs) -> 'MixedFactorPipeline'` 不变 |
| 算法 | Step 2 置 `self._winsorize_params = None`, 再调用 `_apply_winsorize` (边界在调用内现算) |
| 兼容性 | `get_intermediate_data()['outlier']` 仍返回缩尾后快照 |
| 性能估算 | `O(T·N)`, 与 E1 同一次调用, 无额外遍历 |
| 依赖 | 无 |
| TDD 测试 | `test_fit_does_not_store_cross_period_params` (§4.1) |
| 验收标准 | `fit` 后 `_winsorize_params is None` |

#### E3: 删除 `_compute_winsorize_params`

| 字段 | 内容 |
|------|------|
| 目标 | 移除 `axis=0` 全历史参数估计路径, 消除前视来源 |
| 接口设计 | 删除私有方法 (原签名 `(self, X: pd.DataFrame) -> Dict`) |
| 算法 | 边界估计职责并入 E1 |
| 兼容性 | 仓库内 3 处引用全部处理 (§3.3 引用检查表) |
| 性能估算 | 省去 `dict` + 2 个长度 N 的 Series 构造 |
| 依赖 | 无 |
| TDD 测试 | 全仓 grep 为空 (附录 B #1) |
| 验收标准 | 无残留定义 / 调用 |

#### E4: 新增 11 例单测

| 字段 | 内容 |
|------|------|
| 目标 | 直接锁定缩尾数值、小截面语义与无状态契约 |
| 接口设计 | 新文件 `tests/unit/test_mixed_winsorize_cross_sectional.py` (11 个函数) |
| 算法 | 公共 7 例 + A 专属 4 例 (§4.1 完整代码) |
| 兼容性 | 不改动既有测试; 复用 `MixedFactorPipeline` 公共构造 |
| 性能估算 | 小面板 3×10 ~ 60×30, 单文件 < 1s |
| 依赖 | pytest (既有 `dev` extra) |
| TDD 测试 | 自身即测试 |
| 验收标准 | Red: 10 失败 / 1 通过; Green: 11 passed |

#### E5: 重写旧语义测试 + 摘除集成 `xfail`

| 字段 | 内容 |
|------|------|
| 目标 | 旧 per-column 断言改为逐日截面语义; PL-06 不再登记为缺陷 |
| 接口设计 | `TestMixedWinsorSigma.test_07/08/09` 重写 (§4.4); `test_mixed_pipeline_is_truncation_invariant` 摘 `xfail` (§4.3) |
| 算法 | test_07/08 用 `1×30` (`[0]*29+[100]`); test_09 用 `5×30` 走 `fit` 取 `outlier` |
| 兼容性 | 测试文件其余用例不动 |
| 性能估算 | 集成套件 6.9s → 预期同量级 |
| 依赖 | 无 |
| TDD 测试 | 自身即测试 |
| 验收标准 | 配置迁移 12 passed; 集成 10 passed / 2 xfailed |

#### E6: 版本 / 缓存 / ADR / 文档

| 字段 | 内容 |
|------|------|
| 目标 | 版本、缓存代际与决策记录同步 |
| 接口设计 | 项目版本 v3.3.5 (4 处声明 + 2 锚点); `CODE_VERSION = "v2.2.3-cache"`; ADR-039 |
| 算法 | 纯文档/常量变更, 无算法改动 |
| 兼容性 | 旧缓存一次性失效; 旧输出不可比 (§3.9) |
| 性能估算 | 无运行时开销 |
| 依赖 | 无 |
| TDD 测试 | `test_fix3_version_unification.py` (7 passed) |
| 验收标准 | §5 全部条目落地; 附录 B 全通过 |

### 2.2 文件变更清单

| # | 文件 | 变更 | 风险 |
|---|------|------|------|
| 1 | `pipelines_v2.py` | `MixedFactorPipeline.fit` Step 2; `_apply_winsorize`; 删除 `_compute_winsorize_params`; 类/方法 docstring | 高 |
| 2 | `tests/unit/test_mixed_winsorize_cross_sectional.py` | **新增** 11 个测试 | 低 |
| 3 | `tests/test_p3_phase2_config_migration.py` | 重写 `TestMixedWinsorSigma.test_07/08/09` (旧 per-column → 逐日截面) | 中 |
| 4 | `tests/integration/test_pipeline_truncation_invariance.py` | 摘除 PL-06 `xfail`; 更新登记表; 更新 PL-07 reason (实测后) | 中 |
| 5 | `pyproject.toml` / `__init__.py` / `config_v2.py` / `reporting.py` | 版本 → 3.3.5 | 低 |
| 6 | `tests/test_fix3_version_unification.py` / `tests/test_backtest/verify_fix3_manual.py` | 锚点 → 3.3.5; 缓存字面量 → `v2.2.3-cache` | 低 |
| 7 | `backtest/cache_manager.py` | `CODE_VERSION` → `v2.2.3-cache` | 中 (一次性重建) |
| 8 | `DECISIONS.md` / `CHANGELOG.md` / `ARCHITECTURE.md` / `DEV_PROGRESS.md` | ADR-039 / v3.3.5 条目 / 版本基线 | 低 |
| 9 | `docs/analysis/PL06_*.md` | 实施状态标注 | 低 |

---

## §3 代码实施

### 3.1 `MixedFactorPipeline.fit` Step 2

**当前** ([pipelines_v2.py L1098-L1106](../pipelines_v2.py#L1098-L1106)):

```python
        # Step 2: 温和缩尾 (PL-06 未修, 仍为全样本参数)
        if self._winsorizer_enabled:
            logger.info("[MixedPipeline] Applying gentle winsorization...")
            self._winsorize_params = self._compute_winsorize_params(X)
            X = self._apply_winsorize(X)
        else:
            logger.info("[MixedPipeline] winsorizer disabled, 跳过去极值 (identity)")
            self._winsorize_params = None
        self._intermediate_data['outlier'] = X.copy()
```

**改为**:

```python
        # Step 2: 逐日截面 3σ 缩尾 (PL-06: fit no-op, 无跨期参数)
        if self._winsorizer_enabled:
            logger.info("[MixedPipeline] Applying cross-sectional winsorization...")
            self._winsorize_params = None   # 显式标记: 无跨期参数
            X = self._apply_winsorize(X)
        else:
            logger.info("[MixedPipeline] winsorizer disabled, 跳过去极值 (identity)")
            self._winsorize_params = None
        self._intermediate_data['outlier'] = X.copy()
```

### 3.2 `_apply_winsorize`

**当前** ([L1180-L1184](../pipelines_v2.py#L1180-L1184)):

```python
    def _apply_winsorize(self, X: pd.DataFrame) -> pd.DataFrame:
        """应用 sigma 倍数缩尾"""
        return X.clip(lower=self._winsorize_params['lower'],
                      upper=self._winsorize_params['upper'],
                      axis=1)
```

**改为**:

```python
    def _apply_winsorize(self, X: pd.DataFrame) -> pd.DataFrame:
        """逐日截面 3σ 缩尾: 边界只由当日行计算, 无跨期参数.

        mu = X.mean(axis=1); sd = X.std(axis=1, ddof=1)
        lower/upper 按 index (日期) 对齐, 因此 clip(axis=0).
        """
        sigma = self.mixed_winsor_sigma
        mu = X.mean(axis=1)
        sd = X.std(axis=1, ddof=1)
        return X.clip(lower=mu - sigma * sd,
                      upper=mu + sigma * sd,
                      axis=0)
```

### 3.3 删除 `_compute_winsorize_params`

删除 [L1164-L1178](../pipelines_v2.py#L1164-L1178) 的整个方法:

```python
    def _compute_winsorize_params(self, X: pd.DataFrame) -> Dict:
        """计算 sigma 倍数缩尾参数 (P3-Phase2: 消费 mixed_winsor_sigma 配置)
        ...
        """
        sigma = self.mixed_winsor_sigma
        mean = X.mean(axis=0)
        std = X.std(axis=0)
        lo = (mean - sigma * std)
        hi = (mean + sigma * std)
        return {
            'lower': lo,
            'upper': hi,
        }
```

**删除后的引用检查** (实施前已 grep, 仓库内两处测试调用需同步重写):

| 位置 | 处理 |
|------|------|
| `pipelines_v2.py` L1101 | 本任务改写 |
| `tests/test_p3_phase2_config_migration.py` L161 / L188 | §4.4 重写 (test_07/08 直接调用); test_09 经 `fit` 间接调用, 一并重写 |
| 其他 | 无 (CHANGELOG/DECISIONS 的历史叙述不改) |

### 3.4 docstring / 注释

| 位置 | 当前 | 改为 |
|------|------|------|
| 类 docstring [L1061-L1067](../pipelines_v2.py#L1061-L1067) | "缺失插补 → 温和去极值(3σ缩尾) → ..." | "缺失插补 → 逐日截面 3σ 缩尾 → ..." |
| 类 docstring "只做温和缩尾和中性化" | 旧描述 | "只做逐日截面 3σ 缩尾和中性化" |
| `fit` Step 2 注释 | "PL-06 未修, 仍为全样本参数" | "PL-06: fit no-op, 无跨期参数" |
| `_apply_winsorize` docstring | "应用 sigma 倍数缩尾" | 逐日截面语义 (见 §3.2) |

### 3.5 边界语义 (不改代码, 由 pandas 自然满足, 需测试锁定)

| 行状态 | 行为 | 原因 |
|--------|------|------|
| 全 NaN | 原样返回 | `mean/std` 为 NaN; `clip` 忽略 NaN 边界 |
| `N=1` | 原样返回 | `std(ddof=1)` 为 NaN; `clip` 忽略 NaN 边界 |
| 零离散度 | 原样返回 | 边界 = 均值, 所有值相等 |
| `N=2` | 原样返回 | 最大 `|z|=(N-1)/√N=0.707<3` |
| `N≤10` | 原样返回 | 最大 `|z|=(N-1)/√N<3` (N=10: 2.846; N=11: 3.015) |

**不引入** `N<10` 的 z-score 回落或条件分支: 3σ 在小截面上的 no-op 是数学性质, 不是数据触发的 pre-test.

### 3.6 配置面

**不改**:

- `PipelineV2Config.mixed_winsor_sigma`
- `PipelineV2ConfigUnified.mixed_winsor_sigma` / `.transform_aggressiveness`
- `optimizer.DEFAULT_SEARCH_SPACE['mixed_winsor_sigma']`
- `MixedFactorPipeline.__init__` 签名

### 3.7 接口与签名核对 (以源代码为准)

> spec §13.5: 类名 / 方法名 / 参数名 / 返回类型 / 默认值必须从源代码确认, 不依赖文档或记忆。下表全部由 `pipelines_v2.py` / `config_v2.py` / `optimizer.py` 实际读取。

| 接口 | 当前签名 (源代码) | 本次改动 | 破坏性 |
|------|------------------|---------|--------|
| `MixedFactorPipeline.__init__` (L1070-L1074) | `(self, mixed_winsor_sigma: float = 3.0, transformation_params: Optional[Dict] = None, neutralizer_params: Optional[Dict] = None, module_enabled: Optional[Dict[str, bool]] = None)` | 不变 | 无 |
| `MixedFactorPipeline.fit` (L1088) | `(self, X: pd.DataFrame, **kwargs) -> 'MixedFactorPipeline'` | 签名不变; Step 2 改 no-op | 无 |
| `MixedFactorPipeline.transform` (L1142) | `(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame` | 不变 (仍调用 `_apply_winsorize`) | 无 |
| `_apply_winsorize` (L1180) | `(self, X: pd.DataFrame) -> pd.DataFrame` | 签名不变; 实现改逐日截面 | 无 (私有) |
| `_compute_winsorize_params` (L1164) | `(self, X: pd.DataFrame) -> Dict` | **删除** | 仅 §3.3 所列调用点 |
| `_BaseFactorPipeline.fit_transform` (L847) | `(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame` | 不变 | 无 |
| `_BaseFactorPipeline.get_intermediate_data` (L850) | `(self) -> Dict[str, pd.DataFrame]` | 不变 | 无 |
| `PipelineV2Config.mixed_winsor_sigma` (L709) | `float = 3.0` | 不变 | 无 |
| `PipelineV2ConfigUnified.mixed_winsor_sigma` (config_v2 L417-L420) | `float = Field(default=3.0, ge=1.0, le=10.0)` | 不变 | 无 |
| `PipelineV2ConfigUnified.transform_aggressiveness` (config_v2 L421-L424) | `float = Field(default=1.0, ge=0.3, le=5.0)` | 不变 | 无 |
| `optimizer.DEFAULT_SEARCH_SPACE['mixed_winsor_sigma']` (L51) | `{'type': 'float', 'low': 1.0, 'high': 10.0}` | 不变 | 无 |
| `_create_pipeline` 传参 (L1537) | `mixed_winsor_sigma=self.config.mixed_winsor_sigma` | 不变 | 无 |

**核对结论**: 无公共 API 变更; 唯一移除的是私有方法 `_compute_winsorize_params`。

### 3.8 低效操作排除与复杂度 (spec §13.5)

| 检查项 | 结论 |
|--------|------|
| Python 层逐行循环 | 无。`mean(axis=1)` / `std(axis=1)` / `clip(axis=0)` 全为 pandas 向量化 |
| 重复 IO / 重复读盘 | 无。纯内存变换 |
| 重复全表扫描 | `fit` 不再构造 / 保存 `{'lower': Series, 'upper': Series}`; 参数估计与应用合并为一次统计 + 一次 clip |
| 不必要 copy | `X.clip(...)` 返回新对象 (必要, 保持入参不可变); `_intermediate_data['outlier'] = X.copy()` 为既有审计快照, 本任务不改 |
| 复杂度 | 时间 `O(T·N)`; 输出内存 `O(T·N)`; 行统计额外 `O(T)` |
| 等价性 | 向量化实现与逐行循环 `allclose=True` (RESEARCH 附录 A.2 4e) |
| 性能 | 真实方法实测 0.281s → 0.200s (2500×3000, 3 次中位), 见 §1.2 |

> 本任务不引入新的复杂度量级, 也不新增任何 N 次循环。

### 3.9 兼容性判定 (spec §13.5)

| 维度 | 判定 | 说明 |
|------|------|------|
| 公共 API | 不变 | `__init__` / `fit` / `transform` 签名不变 |
| 私有 API | 删除 1 个 | `_compute_winsorize_params`; 仓库内调用点见 §3.3 |
| 新增配置字段 | 无 | 因此 "新字段默认 `enable=False`" 原则 **N/A** |
| 配置迁移 | 无 | `mixed_winsor_sigma` / `transform_aggressiveness` 语义不变; 旧 JSON 无需迁移 |
| 模块开关 | 不变 | `module_enabled={'winsorizer': False}` 仍为 identity (跳过缩尾) |
| 输出数值 | **变更** | 所有 Mixed 结果需重算; 缓存代际 bump (§5.2) |
| 依赖 | 无新增 / 删除 | 仅用 pandas `mean/std/clip`, 在 `>=2.0.0` 可用 |
| Python 版本 | 不变 | `requires-python >=3.9`; 新测试无新语法 |

---

## §4 TDD 测试

### 4.1 Red: 新增 `tests/unit/test_mixed_winsorize_cross_sectional.py`

```python
# -*- coding: utf-8 -*-
"""PL-06: Mixed 缩尾逐日截面 3σ — TDD 测试.

契约:
- fit 不保存跨期参数 (`_winsorize_params is None`)
- 边界只由当日行计算: mu = X.mean(axis=1), sd = X.std(axis=1, ddof=1)
- 输出保留 index/columns/NaN; 单有效观测/零离散度/全 NaN 行原样返回
- N<=10 的 3σ 永不触发; N=11 起可触发
- 截断不变式: 全样本前 t 期输出 == [0,t] 独立跑出的输出
"""
import numpy as np
import pandas as pd

from factor_pipeline.pipelines_v2 import MixedFactorPipeline


def _panel(n_periods=60, n_stocks=30, seed=7):
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        rng.lognormal(mean=0.0, sigma=1.0, size=(n_periods, n_stocks)),
        index=pd.date_range('2020-01-31', periods=n_periods, freq='ME'),
        columns=[f'S{i:03d}' for i in range(n_stocks)],
    )


def _industry(n_stocks=30, n_industries=4):
    stocks = [f'S{i:03d}' for i in range(n_stocks)]
    labels = [f'IND_{i % n_industries}' for i in range(n_stocks)]
    return pd.Series(labels, index=stocks, name='industry')


def _pipe(sigma=3.0, module_enabled=None, with_industry=True):
    kwargs = {}
    if with_industry:
        kwargs['neutralizer_params'] = {'industry_data': _industry()}
    return MixedFactorPipeline(
        mixed_winsor_sigma=sigma,
        module_enabled=module_enabled,
        **kwargs,
    )


def _changed_cells(a: pd.DataFrame, b: pd.DataFrame) -> int:
    va = a.to_numpy(dtype=float)
    vb = b.to_numpy(dtype=float)
    with np.errstate(invalid='ignore'):
        diff = np.abs(va - vb)
    return int(np.sum(np.isfinite(diff) & (diff > 1e-12)))


# =============================================================================
# 公共用例
# =============================================================================

def test_fit_does_not_store_cross_period_params():
    X = _panel(n_periods=60, n_stocks=30, seed=7)
    pipe = _pipe()
    pipe.fit(X)
    assert pipe._winsorize_params is None


def test_truncation_invariant_on_synthetic_panel():
    X = _panel(n_periods=60, n_stocks=30, seed=11)
    t = 36
    out_full = _pipe().fit_transform(X)
    out_trunc = _pipe().fit_transform(X.iloc[:t])
    pd.testing.assert_frame_equal(
        out_full.iloc[:t], out_trunc, atol=1e-12, rtol=0,
    )


def test_future_value_does_not_change_past_rows():
    X = _panel(n_periods=20, n_stocks=30, seed=13)
    X2 = X.copy()
    X2.iloc[-1] = X2.iloc[-1] * 100.0
    pipe = _pipe(with_industry=False)
    out1 = pipe._apply_winsorize(X)
    out2 = pipe._apply_winsorize(X2)
    pd.testing.assert_frame_equal(
        out1.iloc[:-1], out2.iloc[:-1], atol=1e-12, rtol=0,
    )


def test_nan_rows_unchanged():
    idx = pd.date_range('2020-01-31', periods=3, freq='ME')
    cols = [f'S{i:03d}' for i in range(10)]
    X = pd.DataFrame(np.nan, index=idx, columns=cols)
    X.iloc[1, 0] = 5.0          # N=1
    X.iloc[2, :] = 1.0          # 零离散度
    pipe = _pipe(with_industry=False)
    out = pipe._apply_winsorize(X)
    pd.testing.assert_frame_equal(out, X, atol=1e-12, rtol=0)


def test_no_new_nan():
    X = _panel(n_periods=10, n_stocks=30, seed=17)
    X.iloc[2, 3] = np.nan
    X.iloc[5, :] = np.nan
    pipe = _pipe(with_industry=False)
    out = pipe._apply_winsorize(X)
    np.testing.assert_array_equal(
        out.isna().to_numpy(), X.isna().to_numpy(),
    )


def test_winsorizer_disabled_skips_clip():
    X = _panel(n_periods=60, n_stocks=30, seed=19)
    pipe = _pipe(module_enabled={'winsorizer': False})
    pipe.fit_transform(X)
    pd.testing.assert_frame_equal(
        pipe._intermediate_data['outlier'],
        pipe._intermediate_data['imputation'],
        atol=1e-12, rtol=0,
    )


def test_metadata_preserved():
    X = _panel(n_periods=10, n_stocks=30, seed=23)
    pipe = _pipe(with_industry=False)
    out = pipe._apply_winsorize(X)
    assert out.index.equals(X.index)
    assert out.columns.equals(X.columns)


# =============================================================================
# A 专属
# =============================================================================

def test_sigma_monotonicity():
    X = _panel(n_periods=20, n_stocks=30, seed=29)
    counts = []
    for sigma in (2.0, 3.0, 4.0):
        pipe = _pipe(sigma=sigma, with_industry=False)
        out = pipe._apply_winsorize(X)
        counts.append(_changed_cells(out, X))
    assert counts[0] >= counts[1] >= counts[2], counts


def test_n_le_10_is_noop():
    idx = pd.date_range('2020-01-31', periods=3, freq='ME')
    cols = [f'S{i:03d}' for i in range(10)]
    X = pd.DataFrame(np.nan, index=idx, columns=cols)
    X.iloc[0, :2] = [0.0, 100.0]                 # N=2
    X.iloc[1, :5] = [0.0, 0.0, 0.0, 0.0, 100.0]  # N=5
    X.iloc[2, :] = [0.0] * 9 + [100.0]           # N=10
    pipe = _pipe(with_industry=False)
    out = pipe._apply_winsorize(X)
    pd.testing.assert_frame_equal(out, X, atol=1e-12, rtol=0)


def test_bounds_are_row_mean_plus_minus_sigma_std():
    X = _panel(n_periods=15, n_stocks=30, seed=31)
    pipe = _pipe(sigma=3.0, with_industry=False)
    out = pipe._apply_winsorize(X)
    # 独立路径 (numpy) 重建边界, 避免用 pandas 同表达式自证
    arr = X.to_numpy(dtype=float)
    mu = np.nanmean(arr, axis=1)
    sd = np.nanstd(arr, axis=1, ddof=1)
    expected = np.clip(arr,
                       (mu - 3.0 * sd)[:, None],
                       (mu + 3.0 * sd)[:, None])
    pd.testing.assert_frame_equal(
        out, pd.DataFrame(expected, index=X.index, columns=X.columns),
        atol=1e-12, rtol=0,
    )


def test_n11_can_clip():
    idx = pd.date_range('2020-01-31', periods=1, freq='ME')
    cols = [f'S{i:03d}' for i in range(11)]
    X = pd.DataFrame([[0.0] * 10 + [100.0]], index=idx, columns=cols)
    pipe = _pipe(with_industry=False)
    out = pipe._apply_winsorize(X)
    assert not np.allclose(
        out.to_numpy(dtype=float), X.to_numpy(dtype=float),
        atol=1e-12, rtol=0,
    )
```

**Red 预期**: `test_winsorizer_disabled_skips_clip` 在当前代码上已通过 (winsorizer 关闭本就跳过缩尾, 该测试锁定的是现有 identity 语义); 其余 **10 个测试失败**——`test_fit_does_not_store_cross_period_params` 因 `_winsorize_params` 为 dict 失败, 直接调用 `_apply_winsorize` 的测试因 `_winsorize_params` 未设置而 `KeyError`/`AttributeError`, `test_truncation_invariant_on_synthetic_panel` 因 per-column 全样本参数而差异. 不得用 `xfail` 掩盖.

### 4.2 Green: 代码实现

按 §3 落地后跑:

```powershell
C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe -m pytest `
  factor_pipeline/tests/unit/test_mixed_winsorize_cross_sectional.py -q
```

预期: **11 passed**.

### 4.3 集成测试: 摘除 PL-06 `xfail`

`tests/integration/test_pipeline_truncation_invariance.py`:

1. 删除 `test_mixed_pipeline_is_truncation_invariant` 上的 `@pytest.mark.xfail` ([L329-L335](../tests/integration/test_pipeline_truncation_invariance.py#L329-L335)).
2. 测试 docstring 的 "Mixed: kind='skewed' 的厚尾数据 + 全样本缩尾参数" 改为 "Mixed: kind='skewed' 的厚尾数据; 缩尾已逐日截面化 (PL-06)".
3. 模块 docstring 缺陷登记表:
   - 移除 `DEFECT-PL-06` 行;
   - 在"已修复"条目追加 PL-06: 修复前 257/1800 格 / 6.98e-01 → 修复后 0/0;
   - PL-07 的 reason 从 "PL-05/06" 改为 "PL-05"; 数值按实施后复测更新 (不得预填).
4. 预期: **10 passed / 2 xfailed** (PL-05/PL-07).

**若 PL-07 意外通过** (strict xfail 会报 unexpected pass): 先复测 `routes_full == routes_trunc` 与输出; 若确实通过, 摘除 PL-07 的 `xfail` 并在登记表记录 "PL-06 修复后该测试数据不再复现路由差异", 同时另立任务补一个能触发路由翻转的面板; 不得保留会报错的 strict xfail, 也不得为了让套件变绿而放宽断言.

### 4.4 重写 `tests/test_p3_phase2_config_migration.py::TestMixedWinsorSigma`

删除方法后, 原 test_07/08/09 会 `AttributeError`; 重写为逐日截面语义:

```python
    def test_07_mixed_winsor_sigma_default(self):
        """[P3-Phase2-07] 默认 sigma=3.0: 逐日截面边界 = row_mean ± 3*row_std."""
        from factor_pipeline.pipelines_v2 import MixedFactorPipeline

        n = 30
        cols = [f'S{i:03d}' for i in range(n)]
        data = pd.DataFrame([[0.0] * (n - 1) + [100.0]], columns=cols)

        pipeline = MixedFactorPipeline(mixed_winsor_sigma=3.0)
        out = pipeline._apply_winsorize(data)

        mu = data.mean(axis=1)
        sd = data.std(axis=1, ddof=1)
        upper = (mu + 3.0 * sd).iloc[0]
        lower = (mu - 3.0 * sd).iloc[0]

        self.assertAlmostEqual(out.iloc[0].max(), upper, places=10)
        self.assertLessEqual(out.iloc[0].max(), upper + 1e-10)
        self.assertGreaterEqual(out.iloc[0].min(), lower - 1e-10)
        self.assertNotAlmostEqual(out.iloc[0].max(), data.iloc[0].max(), places=10)

    def test_08_custom_mixed_winsor_sigma(self):
        """[P3-Phase2-08] sigma=5.0: 边界随 sigma 改变, 极值仍被截断."""
        from factor_pipeline.pipelines_v2 import MixedFactorPipeline

        n = 30
        cols = [f'S{i:03d}' for i in range(n)]
        data = pd.DataFrame([[0.0] * (n - 1) + [100.0]], columns=cols)

        pipeline = MixedFactorPipeline(mixed_winsor_sigma=5.0)
        out = pipeline._apply_winsorize(data)

        mu = data.mean(axis=1)
        sd = data.std(axis=1, ddof=1)
        upper = (mu + 5.0 * sd).iloc[0]

        self.assertAlmostEqual(out.iloc[0].max(), upper, places=10)
        self.assertNotAlmostEqual(out.iloc[0].max(), data.iloc[0].max(), places=10)

    def test_09_mixed_winsor_sigma_applied_in_fit(self):
        """[P3-Phase2-09] sigma=2.0: fit 的 outlier 中间数据满足逐日截面边界."""
        from factor_pipeline.pipelines_v2 import MixedFactorPipeline

        n = 30
        cols = [f'S{i:03d}' for i in range(n)]
        data = pd.DataFrame([[0.0] * (n - 1) + [100.0] for _ in range(5)],
                            columns=cols)

        pipeline = MixedFactorPipeline(mixed_winsor_sigma=2.0)
        pipeline.fit(data)

        outlier_data = pipeline.get_intermediate_data()['outlier']
        mu = data.mean(axis=1)
        sd = data.std(axis=1, ddof=1)
        upper = (mu + 2.0 * sd).to_numpy(dtype=float)
        lower = (mu - 2.0 * sd).to_numpy(dtype=float)

        np.testing.assert_allclose(
            outlier_data.max(axis=1).to_numpy(dtype=float), upper, atol=1e-10,
        )
        np.testing.assert_array_less(
            np.broadcast_to(lower[:, None] - 1e-10, outlier_data.shape),
            outlier_data.to_numpy(dtype=float),
        )
```

> `test_09` 的 `pipeline.fit(data)` 不使用 industry_data, 与旧测试一致; 只校验 `outlier` 中间数据, 不受后续 rank/z-score 影响.

### 4.5 回归靶向

```powershell
C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe -m pytest `
  factor_pipeline/tests/unit/test_mixed_winsorize_cross_sectional.py `
  factor_pipeline/tests/test_p3_phase2_config_migration.py `
  factor_pipeline/tests/test_pipelines_v2.py `
  factor_pipeline/tests/test_adapters/test_module_enabled.py `
  factor_pipeline/tests/test_fix3_version_unification.py `
  factor_pipeline/tests/integration/test_pipeline_truncation_invariance.py -q
```

预期: 全绿; 集成 10 passed / 2 xfailed; 版本 7 passed.

### 4.6 性能验证 (手工, 不入 CI)

用与 §1.2 相同的 2500×3000 面板, 3 次重复:

```python
import time
import numpy as np
import pandas as pd
from factor_pipeline.pipelines_v2 import MixedFactorPipeline

X = pd.DataFrame(np.random.default_rng(0).standard_normal((2500, 3000)))
pipe = MixedFactorPipeline()
times = []
for _ in range(3):
    t0 = time.perf_counter()
    pipe._apply_winsorize(X)
    times.append(time.perf_counter() - t0)
print(times, np.median(times))
```

预期中位 **≈0.200s**, 不慢于基线 0.281s; 偏差 >20% 需记录原因.

---

## §5 版本、缓存与文档

### 5.1 版本 → v3.3.5

| # | 文件 | 位置 | 旧值 → 新值 |
|---|------|------|------------|
| 1 | `pyproject.toml` | `[project] version` | `3.3.4` → `3.3.5` |
| 2 | `__init__.py` | `__version__` | `3.3.4` → `3.3.5` |
| 3 | `config_v2.py` | `PipelineV2ConfigUnified.version` | `3.3.4` → `3.3.5` |
| 4 | `reporting.py` | `PipelineExecutionReport.pipeline_version` | `3.3.4` → `3.3.5` |
| 5 | `tests/test_fix3_version_unification.py` | `EXPECTED_VERSION` + 4 处 docstring | `3.3.4` → `3.3.5` |
| 6 | `tests/test_backtest/verify_fix3_manual.py` | `EXPECTED_VERSION` + 模块 docstring | `3.3.4` → `3.3.5` |

> 4 处声明 + 2 处测试/脚本锚点; `test_fix3_version_unification.py` 的 docstring 第 12/39/47/56 行也含 `3.3.4`, 一并更新; L12 的日期改为 `2026-11-04`.

### 5.2 缓存代际 → `v2.2.3-cache`

| 文件 | 变更 |
|------|------|
| `backtest/cache_manager.py` | `CODE_VERSION = "v2.2.2-cache"` → `"v2.2.3-cache"` |
| `tests/test_fix3_version_unification.py` | **6 处字面量** (模块 docstring L14、test_05 docstring L79/L83、断言 L92、消息 L93、test_07 `expected` L108) → `v2.2.3-cache`; L83 **保留 PL-02 的历史 bump 描述** 并追加 PL-06 的新 bump (`v2.2.2-cache → v2.2.3-cache`), 不得抹掉历史归因 |
| `tests/test_backtest/verify_fix3_manual.py` | 无需改字面量 (导入 `CODE_VERSION`); 只改版本锚点 |

**语义**: Mixed 缩尾输出数值改变 → 旧因子缓存必须失效; 读取时 `meta.code_version` 不一致即 MISS + 自愈删除 (PL-01 已实现, 本次只 bump 常量).

### 5.3 ADR-039

> 以下为**待写入** `DECISIONS.md` 的模板: 状态与"实测证据"在实施完成后回填; 步骤 8 review 已修正状态措辞 (原误写 "已实施")。

```markdown
## ADR-039: Mixed 缩尾统一为逐日截面 3σ (DEFECT-PL-06, v3.3.5)

**日期**: 2026-11-04
**状态**: 待实施 (v3.3.5 实施完成后改为 "已实施")
**优先级**: P0
**关联缺陷**: DEFECT-PL-06
**关联测试**: `tests/unit/test_mixed_winsorize_cross_sectional.py`,
`tests/test_p3_phase2_config_migration.py`,
`tests/integration/test_pipeline_truncation_invariance.py`
**调研/设计**: PL06_MIXED_WINSORIZE_LOOKAHEAD_RESEARCH.md /
PL06_MIXED_WINSORIZE_LOOKAHEAD_DESIGN.md

### 背景
`MixedFactorPipeline._compute_winsorize_params` 用 `X.mean(axis=0)` /
`X.std(axis=0)` 按股票全历史估计 3σ 边界; `fit` 保存, `transform` 复用。
前 t 期边界依赖 t 之后的数据。截断 60/100 期实测: **257/1800 格差异**,
`max_abs_diff=6.984e-01`, 首个发散日 = 2020-01-31 (第 1 期)。
PL-02 修复后该值取代 ADR-037 中记录的 2.91e-01。

### 决策
1. **逐日截面**: `mu=X.mean(axis=1)`, `sd=X.std(axis=1, ddof=1)`,
   `clip(lower=mu-sigma*sd, upper=mu+sigma*sd, axis=0)`。
2. **fit no-op**: `_winsorize_params=None`; 删除 `_compute_winsorize_params`。
3. **配置契约不变**: `mixed_winsor_sigma` / `transform_aggressiveness` /
   optimizer 搜索空间保留。
4. **小截面**: `N<=10` 时 3σ 永不触发 (最大 `|z|=(N-1)/√N<3`);
   `N=2` no-op; `N=1` / 全 NaN / 零离散度原样返回。不引入 pre-test。
5. **步骤顺序不变**: imputer → winsorize → neutralize → rank → z-score。

### 备选 (拒绝/延后)
- **B 逐日截面 percentile(1,99)**: 与 PL-01/ADR-037 同口径, 但需删除
  `mixed_winsor_sigma` / `transform_aggressiveness` 并同步约 10 个测试/脚本;
  `N<=200` 时每行必截 min/max, `N=2` 两值向内压缩。本次不实施。
- **C per-stock expanding/rolling**: 与项目截面口径不一致; ADR-037 已拒绝。
- **D 移除缩尾**: 非冗余 (移除 vs 当前 485/3000 格, max 1.7394); 放弃设计意图。
- **方法选择器 (A+B 并存)**: 新增配置面与双套测试, 与 ADR-027 收敛方向冲突;
  独立能力任务。
- **Mixed 统一走 `ProcessingAdapter(outlier)`**: 架构重构, 独立任务。

### 代码证据
| 组件 | 位置 |
|------|------|
| `fit` Step 2 no-op | `pipelines_v2.py` `MixedFactorPipeline.fit` |
| 逐日截面缩尾 | `pipelines_v2.py` `MixedFactorPipeline._apply_winsorize` |
| 删除全样本参数 | `pipelines_v2.py` (原 `_compute_winsorize_params`) |
| 新单测 | `tests/unit/test_mixed_winsorize_cross_sectional.py` |
| 旧语义测试重写 | `tests/test_p3_phase2_config_migration.py::TestMixedWinsorSigma` |

### 实测证据
`T=100, N=30, seed=23, kind='skewed', t=60, atol=1e-12`:

| 对象 | 修复前 | 实施后 |
|------|--------|--------|
| Mixed 端到端截断不变式 | 257/1800 格, 6.984e-01 | **待实测** (预期 0/1800, 0) |
| 相对旧实现的全样本输出差异 | — | **待实测** (调研探针等价实现: 561/3000 格, max 1.0446, Spearman 中位 0.999110 / 最小 0.942603) |
| 缩尾触发率 | 61/3000 (2.03%) | **待实测** (调研探针等价实现: 77/3000, 2.57%) |
| 性能 (2500×3000, 3 次中位) | 0.281s | **待实测** (提案等价计算: 0.200s) |

### 测试契约
新增 11 个单测 (公共 7 + A 专属 4); 集成套件 9/3 → 10/2;
`TestMixedWinsorSigma.test_07/08/09` 改为逐日截面语义;
既有 `test_pipelines_v2.py` / `test_module_enabled.py` 全绿。

### 不覆盖
PL-05 / PL-07; B (percentile); 方法选择器; `ProcessingAdapter(outlier)`
统一路径; Mixed 3σ 与 Static percentile 的方法口径统一; optimizer 重新调参。

### 后果
- **正面**: Mixed 缩尾结构上不再有跨期参数; 截断不变式预期归零;
  提案等价计算显示性能约提升 29% (0.281s → 0.200s, 实施后复测);
  配置/optimizer 契约不变。
- **负面/破坏性**: 所有 Mixed 输出数值变更; 历史 IC/Sharpe 需重算;
  缓存代际 bump 导致价格/收益缓存一次性失效; `N<=10` 时缩尾不动作。
- **已知遗留**: Mixed 3σ 与 Static percentile(1,99) 的方法差异;
  统一需另开任务。

### 学术与工业依据
- MSCI FaCS Methodology (Bonne et al., 2018): 稳健均值 ± 3 稳健标准差 (A)。
- Bali, Engle & Murray (2016): winsorization vs truncation (A);
  "cross-sectional distributions" 逐字引文未验证 (U), 不作强论据。
- Hampel (1974); Rousseeuw & Croux (1993): 稳健尺度 (A)。
- Banz & Breen (1986); Kaufman et al. (2012); Kapoor & Narayanan (2023);
  Arnott et al. (2019): 样本依赖/泄漏 (A)。
- Leeb & Pötscher (2006/2008): pre-test 估计量分布不可一致估计 (A/B)。

### 回滚
恢复 `_compute_winsorize_params` 与 per-column `_apply_winsorize`;
`CODE_VERSION` 回 `v2.2.2-cache`; 项目版本回 v3.3.4; 恢复 PL-06 的 `xfail`;
删除/重建缓存。
```

### 5.4 CHANGELOG v3.3.5

按现有格式 (概览 / 缺陷根因 / 实测矩阵 / 核心产出) 写入:

| 层级 | 对象 | 修复前 | 修复后 |
|------|------|--------|--------|
| pipeline | Mixed | 257/1800 格, 6.984e-01 | **待实测** (预期 0/1800, 0) |
| step | `_apply_winsorize` 单测 | 旧 per-column 语义 | **待实测** (预期 11 例全绿) |

**核心产出**:
- Mixed 缩尾改为逐日截面 3σ, `fit` 无跨期参数;
- 删除 `_compute_winsorize_params`;
- `mixed_winsor_sigma` / optimizer 契约不变;
- 新增 11 例单测; 重写 3 个旧语义测试;
- 集成套件由 `9 passed / 3 xfailed` 变为 `10 passed / 2 xfailed`;
- ADR-039; 项目版本 3.3.5; 缓存 `v2.2.3-cache`.

**兼容性**: 旧 Mixed 输出全部改变, 历史结果需重算; 配置无迁移;
`N<=10` 时缩尾不动作 (文档化).

**已知遗留**: B (percentile) 未实施; Mixed 3σ 与 Static percentile 的方法差异;
PL-05 / PL-07 仍登记为 xfail.

### 5.5 ARCHITECTURE / DEV_PROGRESS

- `ARCHITECTURE.md` 版本基线追加:
  `→ v3.3.5 (2026-11-04, PL-06 Mixed 缩尾逐日截面 3σ + ADR-039)`.
- `DEV_PROGRESS.md` §1 追加:
  `v3.3.5 (2026-11-04) PL-06 Mixed 缩尾逐日截面 3σ (ADR-039) + 缓存代际 v2.2.3-cache`,
  并把 "当前" 箭头移到 v3.3.5 行.

### 5.6 调研/设计文档状态

- `PL06_MIXED_WINSORIZE_LOOKAHEAD_RESEARCH.md` 头部 "后续" 改为:
  "设计 v1.1 选定 A; 已实施 (v3.3.5, 2026-11-04)".
- `PL06_MIXED_WINSORIZE_LOOKAHEAD_DESIGN.md` 头部加:
  "**实施状态**: 已实施 (v3.3.5, 2026-11-04); 验收记录见
  [EXECUTION_V3.3.5_PL06_MIXED_WINSORIZE_CAUSALITY.md](../EXECUTION_V3.3.5_PL06_MIXED_WINSORIZE_CAUSALITY.md) §7".

---

## §6 执行顺序与 spec 步骤映射

### 6.1 spec 10 步映射 (WORKFLOW_METHODOLOGY v1.3 §13.2)

| spec 步骤 | 状态 | 工件 |
|-----------|------|------|
| 1-2 调研 + review | **完成** | `PL06_..._RESEARCH.md` v1.0 |
| 3-4 设计 + review 排除幻觉 | **完成** | `PL06_..._DESIGN.md` v1.1 |
| 5 实施文档 | **本文档** | `EXECUTION_V3.3.5_...md` v1.3 |
| 6 review 实施文档排除幻觉 | **完成** (v1.2) | review 结论: 7 类幻觉核查通过; 修复 3 处交叉引用 (§3.4→§3.3); 无阻塞项 |
| 7 验收 checklist | **完成** | `docs/audit/CHECKLIST_V3.3.5_PL06_MIXED_WINSORIZE_CAUSALITY.md` (Gate 0-8) |
| 8 文档一致性 review | **完成** | `docs/audit/CONSISTENCY_REVIEW_V3.3.5.md` (2 MAJOR + 4 MINOR 已修复) |
| 9 TDD 实现 | **完成** | 代码 + 测试 (§4); 73 passed / 2 xfailed |
| 10 审查验收 | **完成** | `docs/audit/2026-11-04-code-quality-audit.md`: **PASS** (1 项 P2 已修复, 2 项 P3 记录性遗留, 零回归) |

> 本任务属小而明确的缺陷修复, 按 §13.8 裁剪规则 **不省略** 步骤 7-8: 因涉及版本/缓存/跨文档数值, 一致性风险高于普通小任务。

### 6.2 执行顺序 (含检查点)

| 步 | 动作 | 检查点 |
|----|------|--------|
| 0 | 跑 §1.2 基线, 记录实际值 | 基线写入本文档 §7.1 |
| 1 | 新增 `test_mixed_winsorize_cross_sectional.py` | **Red**: 10 个失败, 1 个 (winsorizer disabled) 已通过; 不得用 xfail |
| 2 | 改 `pipelines_v2.py` (§3.1-3.4) | 11 个单测转绿; §3.7 签名复核无漂移 |
| 3 | 重写 `TestMixedWinsorSigma.test_07/08/09` (§4.4) | `test_p3_phase2_config_migration.py` 12 passed |
| 4 | 摘 PL-06 `xfail` + 更新登记表 (§4.3) | 集成 10 passed / 2 xfailed; 若 PL-07 意外转绿按 §4.3 处理 |
| 5 | 回归 §4.5 + 性能 §4.6 | 全绿; 记录性能实测 (§7.2) |
| 6 | 版本/缓存/ADR-039/CHANGELOG/架构文档 (§5) | 版本 7 passed; 文档一致 |
| 7 | 全仓 grep `_compute_winsorize_params|_winsorize_params`; 最终 review | 无遗漏; 删除方法无残留调用; 附录 B 全通过 |

---

## §7 验收记录

### 7.1 基线 (实施前, 2026-11-04 实测)

| 组 | 命令 | 预期 | 实测 |
|----|------|------|------|
| 集成 | `test_pipeline_truncation_invariance.py` | 9 passed / 3 xfailed | **9 passed, 3 xfailed (6.91s)** |
| 管线+模块 | `test_pipelines_v2.py` + `test_module_enabled.py` | — | **33 passed (4.82s)** |
| 配置迁移 | `test_p3_phase2_config_migration.py` | — | **12 passed (0.63s)** |
| 版本统一 | `test_fix3_version_unification.py` | 7 passed | **7 passed (0.36s)** |
| 性能 | `_compute_winsorize_params` + `_apply_winsorize` | — | **0.281s** (0.281/0.269/0.281) |
| 性能 | 提案逐日截面等价计算 | — | **0.200s** (0.200/0.209/0.193) |

### 7.2 实施后 (2026-11-04 实测)

| 组 | 预期 | 实测 |
|----|------|------|
| 新单测 | 11 passed | **11 passed (0.99s)** |
| 配置迁移 | 12 passed | **12 passed (0.51s)** |
| 集成 | 10 passed / 2 xfailed | **10 passed / 2 xfailed (6.15s)**, 0 xpassed |
| 回归合计 (6 套件) | 全绿 | **73 passed / 2 xfailed (9.58s)** |
| Mixed 截断不变式 | 0 格 / 0 | **0 格 / 0** (诊断 Mixed 行 PASS) |
| 诊断违反项 | 1 项 (仅 PL-05) | **违反 1 / 满足 8 / 合计 9** |
| 输出变更 (本面板) | 561/3000 格, max 1.0446 | **561/3000 格, max 1.0446, 63/100 行** (Spearman 中位 0.999110 / 最小 0.942603) |
| 缩尾触发率 | 77/3000 (2.57%) | **77/3000 (2.57%)** (旧实现 61/3000) |
| 性能 | ≈0.200s | **0.184s** (0.175 / 0.184 / 0.193) |
| 版本统一 | 7 passed | **7 passed (0.32s)**; 手工脚本 5/5 |
| 接口签名 | 与 §3.7 表一致 | 一致 (公共签名未变, 仅删除私有方法) |
| 依赖 / 配置 | 无新增 / 无删除 | 无新增 / 无删除 |
| 低效操作 | 无 Python 行循环 | 无 (全向量化) |

---

## §8 风险、回滚与后续

### 8.1 风险

| # | 风险 | 处置 |
|---|------|------|
| R1 | PL-07 在 PL-06 修复后意外通过 (strict xfail 报错) | 复测路由与输出; 确实通过则摘除 xfail 并记录, 另立任务补路由翻转面板; 不放宽断言 |
| R2 | 旧测试 `TestMixedWinsorSigma` 调用已删除方法 | §4.4 同步重写 |
| R3 | `N<=10` 时缩尾 no-op, 小股票池"看起来没生效" | 文档化; 单测锁定; 不引入条件切换 |
| R4 | 输出变更导致历史 IC/Sharpe 不可比 | CHANGELOG 明示; 缓存 bump; 另行重算 |
| R5 | `_compute_winsorize_params` 是否有仓库外调用 | 仓库内 grep 已核对; 实施后再全仓 grep |
| R6 | optimizer 在输出变更后未重新调参 | 明确不在本任务; 后续单独评估 |
| R7 | Mixed 3σ 与 Static percentile 方法不一致 | ADR-039 登记为已知遗留; 统一另开任务 |

### 8.2 回滚

1. 恢复 `pipelines_v2.py` 的 `_compute_winsorize_params` 与 per-column `_apply_winsorize`;
2. 恢复 `CODE_VERSION = "v2.2.2-cache"` 与版本 v3.3.4;
3. 恢复 PL-06 的 `xfail` 登记;
4. 恢复 `TestMixedWinsorSigma.test_07/08/09` 的旧语义;
5. 删除/重建缓存.

### 8.3 后续任务

| 任务 | 内容 |
|------|------|
| PL-05 | Dynamic AR 系数 / `fitted_values` 的因果性 |
| PL-07 | 顶层指纹路由依赖全样本 |
| B (percentile) | 若需与 PL-01/ADR-037 统一方法, 另开任务评估配置迁移 |
| 方法选择器 | 若需 A+B 并存, 独立能力任务; 方法必须是构造期 `Literal`, 不进入 optimizer 搜索 |
| ProcessingAdapter 统一 | Mixed 缩尾走 `ProcessingAdapter(outlier)`, 架构重构 |

---

## §9 交付物

| 类型 | 文件 |
|------|------|
| 代码 | `pipelines_v2.py` |
| 单测 | `tests/unit/test_mixed_winsorize_cross_sectional.py` (新增 11 例) |
| 旧测试重写 | `tests/test_p3_phase2_config_migration.py` (test_07/08/09) |
| 集成测试 | `tests/integration/test_pipeline_truncation_invariance.py` (摘 PL-06 xfail) |
| 版本 | `pyproject.toml` / `__init__.py` / `config_v2.py` / `reporting.py` / 2 处测试锚点 |
| 缓存 | `backtest/cache_manager.py` → `v2.2.3-cache` |
| 决策 | `DECISIONS.md` ADR-039 |
| 日志 | `CHANGELOG.md` v3.3.5 |
| 架构/进度 | `ARCHITECTURE.md` / `DEV_PROGRESS.md` |
| 状态标注 | `docs/analysis/PL06_*.md` |
| 验收 checklist | `docs/audit/CHECKLIST_V3.3.5_PL06_MIXED_WINSORIZE_CAUSALITY.md` (Gate 0-8) |
| 一致性 review | `docs/audit/CONSISTENCY_REVIEW_V3.3.5.md` |

> 提交由用户明确要求后执行; 本实施文档不自动提交.

---

## 附录 A: 常用命令

```powershell
# 全量靶向
$env:PYTHONPATH='f:\Coding'
C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe -m pytest `
  factor_pipeline/tests/unit/test_mixed_winsorize_cross_sectional.py `
  factor_pipeline/tests/test_p3_phase2_config_migration.py `
  factor_pipeline/tests/test_pipelines_v2.py `
  factor_pipeline/tests/test_adapters/test_module_enabled.py `
  factor_pipeline/tests/test_fix3_version_unification.py `
  factor_pipeline/tests/integration/test_pipeline_truncation_invariance.py -q

# 仅集成
C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe -m pytest `
  factor_pipeline/tests/integration/test_pipeline_truncation_invariance.py -q

# 仅新单测
C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe -m pytest `
  factor_pipeline/tests/unit/test_mixed_winsorize_cross_sectional.py -q
```

---

## 附录 B: 实施自检

| # | 检查项 | 通过标准 |
|---|--------|---------|
| 1 | `pipelines_v2.py` 无 `_compute_winsorize_params` 定义/调用 | grep 为空 (历史文档除外) |
| 2 | `_apply_winsorize` 使用 `axis=0` + 行统计 | 代码核对 |
| 3 | `fit` 后 `_winsorize_params is None` | 单测 |
| 4 | `N<=10` / `N=2` / `N=1` / 零离散度原样返回 | 单测 |
| 5 | 截断不变式 0/0 | 集成 |
| 6 | 集成 10 passed / 2 xfailed | 套件 |
| 7 | 旧 `TestMixedWinsorSigma` 重写并通过 | 套件 |
| 8 | 版本 4 处声明 + 2 锚点 = 3.3.5 | `test_fix3` |
| 9 | 缓存 5 处默认值一致 = `v2.2.3-cache` | `test_07` |
| 10 | 性能不慢于 0.281s | 手工 |
| 11 | 文档/ADR/CHANGELOG 数值与实测一致 | 最终 review |
| 12 | 接口签名与 §3.7 表一致 | 源代码复核 (`inspect.signature`) |
| 13 | 无新增依赖 / 配置字段 | `git diff` + `pyproject.toml` |
| 14 | 无 Python 层 N 次循环 | 代码核对 (§3.8) |
| 15 | 调研 / 设计 / 实施三文档数值一致 | 一致性 review (spec 步骤 8) |

> **实施后自检 (2026-11-04)**: 1-15 全部通过。证据: §7.2 实测表、`docs/audit/CHECKLIST_V3.3.5_PL06_MIXED_WINSORIZE_CAUSALITY.md` Gate 0-8。
