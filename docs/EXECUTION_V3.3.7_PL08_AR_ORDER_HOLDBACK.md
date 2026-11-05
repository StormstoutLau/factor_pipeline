# v3.3.7 PL-08 AR 阶数选择 hold_back 可比性修复 — 实施文档

**文档版本**: v1.2 (2026-11-04; v1.0 = 步骤 5 初稿; v1.1 = 步骤 6 review 修订, 见附录 C; v1.2 = 步骤 8 一致性 review 修订, 见附录 D)
**日期**: 2026-11-04
**缺陷**: DEFECT-PL-08
**设计依据**: [PL08_AR_ORDER_AIC_COMPARABILITY_DESIGN.md](analysis/PL08_AR_ORDER_AIC_COMPARABILITY_DESIGN.md) v1.2 (方案 C 选定)
**调研依据**: [PL08_AR_ORDER_AIC_COMPARABILITY_RESEARCH.md](analysis/PL08_AR_ORDER_AIC_COMPARABILITY_RESEARCH.md) v1.2 (唯一学术/工业依据源, 映射见 §0.3)
**目标版本**: **v3.3.7**; 缓存 **`v2.2.5-cache`**
**变更性质**: 数值行为变更 (AR 阶数/系数/残差索引) + 无接口变更
**实施方式**: 严格 TDD (Red → Green → 回归 → 版本/文档)
**规范依据**: [WORKFLOW_METHODOLOGY.md](WORKFLOW_METHODOLOGY.md) v1.3 §13.5 — 工程细节 / 版本 / 依赖 / 兼容 / 接口 / 签名 / 排除低效操作
**spec 位置**: 步骤 5-10 全部完成 (6 review 附录 C / 7 checklist / 8 一致性附录 D / 9 TDD §7.2 / 10 审计 PASS)
**行号说明**: 文中行号仅作导航, 以类名/函数名/测试名为准 (编辑后会漂移)

---

## §0 实施摘要

| 项 | 内容 |
|---|------|
| 核心改动 | `AROrderSelector._fit_ar` 对所有阶数统一 `hold_back = self.max_order`; 增加有效样本守卫 `n_obs <= order+5 → ValueError`; `residuals`/`fitted_values` 索引从 `series.index[order:]` 改为 `series.index[H:]` |
| 不改 | `AROrderSelector._fit_best` / `fit` / `batch_fit`; `ARDecoupler` 全部方法 (含 `transform` 三段式与 `early`); 配置面 / optimizer; 公共签名 |
| 代码文件 | `modules/factor_decoupler/core/ar_model.py` (仅 `_fit_ar` + 注释) |
| 测试文件 | 新增 `tests/unit/test_ar_order_holdback.py` (10 个函数 / 22 个 pytest 用例); 修改版本/缓存字面量测试 (2 文件) |
| 版本同步 | 4 处版本声明 + 缓存 `CODE_VERSION` + 2 处版本测试锚点 + README |
| 文档 | **ADR-041** / CHANGELOG v3.3.7 / PROJECT_STATUS / DEV_PROGRESS |
| 验收关键 | `n_obs` 全等; 与 statsmodels `hold_back` 逐项一致; AR(1) 选阶均值 ≤ 2.0; 11 个截断点 0/0; 既有行为测试无新增失败 |

### 0.1 E 任务清单

| E | 目标 | 主要文件 | 复杂度 | 依赖 | 验收 |
|---|------|---------|-------|------|------|
| E1 | `_fit_ar` 统一 `hold_back` + 有效样本守卫 + 索引对齐 | `ar_model.py` | `O(n_obs·p²)` 不变 | 无 | T1–T4 通过; 与 statsmodels 逐项一致 |
| E2 | 新增 `tests/unit/test_ar_order_holdback.py` (T1–T10) | 新测试文件 | — | pytest / statsmodels | **Red 预演 13 failed / 9 passed** → Green 预演 **22 passed** |
| E3 | 版本 / 缓存 / ADR-041 / CHANGELOG / 状态文档 | 13 个文件 | — | E1/E2 | `test_fix3` 7 passed; `verify_fix3_manual` 通过 |
| E4 | 回归 + 性能 + 输出偏移复测 | 无代码 | — | E1 | 靶向 72 passed / 1 env-fail; 输出偏移与调研一致 |

### 0.2 规模、依赖与版本

| 项 | 值 |
|----|-----|
| 新增测试函数 | **10** (`test_ar_order_holdback.py`) |
| 新增 pytest 用例 | **22** (T1 1 + T2 5 + T3 3 + T4 1 + T5 1 + T6 1 + T7 1 + T8 3 + T9 1 + T10 5) |
| 修改测试文件 | **2** (`test_fix3_version_unification.py` / `verify_fix3_manual.py`) |
| 新增依赖 | **无** (statsmodels 已是 `pyproject.toml` 必需依赖, 仅测试使用) |
| 删除依赖 | 无 |
| 新增公开参数 | **无** |
| 新增配置字段 | **无** |
| 代码净变更 | 约 **+25 / −11 行** (`ar_model.py` `_fit_ar` + 注释) |
| 目标版本 / 缓存代际 | **v3.3.7** / **`v2.2.5-cache`** |

### 0.3 调研 / 设计依据映射

| 实施声明 | 调研文档 | 设计文档 |
|---------|---------|---------|
| 缺陷根因 (`n_obs = n-order`; 样本因子 ≈2.84 > AIC 罚 2) | RESEARCH §0 / §6.1 | DESIGN §0 / §2.1 |
| 修复口径 (`hold_back=max_order`; statsmodels 语义) | RESEARCH §3.1 / §3.4 | DESIGN §3.1 / D1 |
| 守卫 `n_obs > order+5` (消除 `σ²=0`; 322.68 退化) | RESEARCH §5.4 / §6.5 | DESIGN §3.2 / D2 |
| `transform` 不改 (`early=min_order+6`) | RESEARCH §6.4 / §6.5 | DESIGN §3.3 / D3 |
| 索引 `series.index[H:]`; TemporalDecoupler NaN | RESEARCH §7.1 | DESIGN §5.3 / D4 |
| 默认 AIC; 不加 AICc | RESEARCH §2.2 / §6.2 / §6.3 | DESIGN §0 / D5 |
| 阶数分布 (4.8→1.2–1.6; AR(2)/AR(3) 恢复) | RESEARCH §6.2 | DESIGN §3.6 |
| 输出偏移 (93.0% / 96.1%) | RESEARCH §6.3 | DESIGN §3.6 / §5.1 |
| 固定阶数兼容性 (fit 等价; warm-up 平移) | RESEARCH §0 结论 7 / §5.5 | DESIGN §5.2 |
| 既有测试预演 (72 passed / 1 env-fail) | — (设计期新增) | DESIGN §6.2 |
| 版本 / 缓存 / ADR-041 | RESEARCH §7.2 | DESIGN §5.4 / D8 |

**不实施**: A (仅 hold_back 无守卫)、B (守卫 `order+2`)、D (+AICc)、E (默认 BIC)、`OptimizedARDecoupler` / `TemporalDecoupler` 修复、配置面/optimizer 改动.

---

## §1 前置条件与基线

### 1.1 环境、版本与依赖 (spec §13.5)

| 项 | 值 | 来源 |
|---|-----|------|
| 解释器 (实测) | **3.13.5** | `python -c` |
| 项目 Python 约束 | `>=3.9` | `pyproject.toml` L10 |
| numpy 约束 / 实测 | `>=1.22.0` / **2.1.3** | `pyproject.toml` L27 / `python -c` |
| pandas 约束 / 实测 | `>=2.0.0` / **2.2.3** | `pyproject.toml` L28 / `python -c` |
| statsmodels 约束 / 实测 | `>=0.13.0` / **0.14.4** | `pyproject.toml` L33 / `python -c` |
| duckdb 约束 / 实测 | `>=0.10.0` / **未安装** | `pyproject.toml` L32 / `python -c` 失败 |
| 工作目录 | `F:\Coding\factor_pipeline` | 仓库根 |
| Git HEAD | `34c2713` | `git log -1` |
| 新增依赖 | **无** | 静态核对 |
| 新增测试依赖 | **无** (`statsmodels` 已声明) | `pyproject.toml` L33 |

> **环境漂移说明 (非本任务引入)**: PL-05 文档记录的解释器为 `Python312\python.exe` (3.12.10, numpy 2.4.6); 本任务全部实测 (基线 72/1、Red 13/9、Green 22/22、探针数据) 使用上表 Anaconda 环境 (3.13.5, numpy 2.1.3)。两套环境的差异不影响本任务结论 (纯 numpy/pandas 数值运算, 无版本敏感 API); 后续步骤 9-10 的实测以本表环境为准。

> **环境说明 (非本次引入)**: `duckdb` 在 `pyproject.toml` 声明但本机未安装, 导致 `test_E10_bridge_init_params_exist` 在基线与实施后均失败。该失败**不纳入 PL-08 验收**, 但需在 §7 记录为环境排除项。

### 1.2 基线 (实施前, 2026-11-04 实测)

**靶向套件**:

| 套件 | 结果 |
|------|------|
| `tests/unit/test_ar_decoupler_causality.py` | passed |
| `tests/test_factor_decoupler/test_hidden_effect.py` | passed |
| `tests/test_pipelines_v2.py` | 除 1 项环境失败外通过 |
| `tests/integration/test_pipeline_truncation_invariance.py` | passed |
| **合计** | **72 passed / 1 failed (17.58s)** |

**当前实现基线 (探针实测)**:

| 指标 | 值 |
|------|-----|
| `n_obs` (T=100, AR(1..5)) | 99/98/97/96/95 |
| 阶数均值 (AR(1) T=100/N=30 seed=22) | AIC 4.800 / BIC 2.200 / HQIC 3.867 |
| 阶数均值 (AR(1) T=500, 拟合窗口 120) | AIC 4.867 |
| 阶数均值 (AR(2) T=120/N=30 seed=11) | 4.87 |
| 阶数均值 (AR(3) T=120/N=30 seed=5) | 4.97 |
| AR 性能 (2500×300) | 2.76s (单次) |
| 尾部一步 MSE (T=500/N=30 seed=42, t≥120) | 1.067782 |
| 截断不变式 (PL-05 既有 7 点) | 0/0 (已满足) |

### 1.3 实施后预期

| 指标 | 目标 |
|------|------|
| `n_obs` (AR(1..5)) | **95/95/95/95/95** (n=100, H=5) |
| 阶数均值 (AR(1) T=100) | AIC **1.233** / BIC **1.000** / HQIC **1.000** |
| 阶数均值 (AR(1) T=500, 窗口 120) | AIC **1.600** |
| 阶数均值 (AR(2) T=120) | **2.53** |
| 阶数均值 (AR(3) T=120) | **3.23** |
| 输出偏移 (T=100/N=30 seed=22) | **2790/3000 (93.0%)**, `max_abs=6.9968` |
| 输出偏移 (T=500/N=30 seed=42) | **14410/15000 (96.1%)**, `max_abs=4.6718` |
| 尾部一步 MSE | **1.048759** |
| 截断不变式 (11 点) | **0 格 / 0 NaN** |
| AR 性能 (2500×300) | **2.72s** (上限 3.1s) |
| 靶向套件 | **72 passed / 1 env-fail (无新增失败)** |

> 上表数值来自调研 v1.2 的方案 C 探针 (与本文 §3.1 实现逐行等价); 步骤 9 需复测确认并回填 §7.2。

---

## §2 E 任务与变更清单

### 2.1 E 任务定义

#### E1: `_fit_ar` 统一样本 + 守卫 + 索引

**目标**: 让 AIC/BIC/HQIC 在同一 `n_obs` 上可比, 并排除不可估阶。

**接口 (不变)**:

```python
def _fit_ar(self, series: pd.Series, order: int) -> ARModelResult
```

**输入契约**:
- `series` 已 `dropna` (所有内部调用方满足);
- `order ∈ [min_order, max_order]`。

**输出契约**:
- `ARModelResult` 字段不变;
- `residuals` / `fitted_values` 长度 `n - max_order`, 索引从 `series.index[max_order]` 开始;
- `aic` / `bic` / `hqic` 使用同一 `n_obs = n - max_order`。

**实现**: 见 §3.1。

**验收**: T1–T4 Green; 与 statsmodels 逐项一致。

#### E2: 新增单元测试

**文件**: `tests/unit/test_ar_order_holdback.py` (新文件, 10 函数 / 22 用例)。

**覆盖**:
1. 有效样本一致 (T1);
2. statsmodels 语义对齐 (T2, 5 参数);
3. 守卫边界 (T3, 3 参数);
4. 索引契约 (T4);
5. AR(1)/AR(2)/AR(3) 选阶 (T5–T7);
6. 固定阶数 `fit` 等价 (T8, 3 参数);
7. warm-up 无退化 + early identity (T9);
8. 早期截断不变式 (T10, 5 参数)。

**Red 预期**: **13 failed / 9 passed** (详见 §4.2; 步骤 9 实测回填)。

#### E3: 版本 / 缓存 / ADR / 文档

**版本**: 4 处声明 + 2 处测试锚点 + README → §5.1。
**缓存**: `v2.2.4-cache` → `v2.2.5-cache` → §5.2。
**ADR-041**: 新增 → §5.3。
**CHANGELOG**: v3.3.7 条目 → §5.4 (实测值待步骤 9 回填)。
**状态文档**: PROJECT_STATUS / DEV_PROGRESS → §5.5。

#### E4: 回归 / 性能 / 偏移复测

| 项 | 命令/方法 | 通过标准 |
|----|----------|---------|
| 靶向回归 | §4.4 | 72 passed / 1 env-fail, 无新增失败 |
| 性能 | 2500×300 单次 `fit_transform` | ≤ 3.1s |
| 输出偏移 | T=100 / T=500 面板 | 与 §1.3 预期一致 (±5% 格数) |
| 截断不变式 | 11 点 | 0/0 |
| 退化警告 | T=80, warmup=40 | 无 `divide by zero` / `invalid value` |

### 2.2 文件变更清单

**必改**:

| 文件 | 变更 |
|------|------|
| `modules/factor_decoupler/core/ar_model.py` | `_fit_ar` 的 `hold_back` / 守卫 / 索引; 方法 docstring + PL-08 注释 |
| `tests/unit/test_ar_order_holdback.py` | **新增** (10 函数 / 22 用例) |
| `pyproject.toml` | `version = "3.3.7"` (L7) |
| `__init__.py` | `__version__ = "3.3.7"` (L58) |
| `config_v2.py` | `version: str = Field(default="3.3.7")` (L371) |
| `reporting.py` | `pipeline_version = "3.3.7"` (L40) |
| `backtest/cache_manager.py` | `CODE_VERSION = "v2.2.5-cache"` (L58) |
| `tests/test_fix3_version_unification.py` | `EXPECTED_VERSION="3.3.7"` (L33); 缓存字面量 (L96/L112); docstring |
| `tests/test_backtest/verify_fix3_manual.py` | `EXPECTED_VERSION="3.3.7"` (L21); docstring L5 "5 个预期位置的版本号均为 3.3.7" |
| `DECISIONS.md` | 占用表 L43-L44 + ADR-041 正文 |
| `CHANGELOG.md` | v3.3.7 条目 |
| `README.md` | 版本信息 (L1029) / 测试基线 (L1032) / 状态 (L1035) / 版本历史 (L1059 后追加) |
| `docs/PROJECT_STATUS.md` / `docs/DEV_PROGRESS.md` / `docs/ARCHITECTURE.md` | 版本基线 / 下一任务 / L17 因果性描述追加 hold_back + L20 基线追加 v3.3.7 |

**不改**:

| 文件/对象 | 理由 |
|-----------|------|
| `AROrderSelector._fit_best` / `fit` / `batch_fit` | 有效样本判定在 `_fit_ar`; 默认配置总长守卫不触发 |
| `ARDecoupler.__init__` / `fit` / `transform` / `_predict_one_step` | 无签名/结构变更 |
| `modules/factor_decoupler/core/optimized.py` | 独立副本, 非生产路径 |
| `modules/factor_decoupler/core/unified_decoupler.py` | 非生产路径; 仅被动变化 |
| `modules/factor_decoupler/core/dual_neutralizer.py` | Stage 2 通过 `ARDecoupler` 被动变化 |
| `pipelines_v2.py` / `config_v2.py` 字段集合 / `optimizer.py` | 配置面不变 |

### 2.3 代码净变更

```
modules/factor_decoupler/core/ar_model.py
  _fit_ar: 约 +25 / −11 行 (hold_back + 守卫 + 索引 + docstring; 步骤 9 实测)
```

无新增文件 (测试文件除外); 无删除代码.

---

## §3 代码实施

### 3.1 `_fit_ar` 新实现 (完整)

```python
def _fit_ar(self, series: pd.Series, order: int) -> ARModelResult:
    """拟合指定阶数的 AR 模型 (v3.3.7 / ADR-041: 所有阶数统一 hold_back 样本).

    ``hold_back = max_order`` 使 AR(1)..AR(max_order) 的响应向量与估计样本
    完全一致, 满足 statsmodels ``AutoReg(hold_back=maxlag)`` 的可比性语义;
    AIC/BIC/HQIC 因此可在同一 ``n_obs`` 上比较。

    前置条件: ``series`` 已 dropna; ``order <= self.max_order``。
    """
    y = series.values
    n = len(y)
    hold_back = self.max_order              # 所有阶数共享的估计样本起点

    y_trimmed = y[hold_back:]
    n_obs = len(y_trimmed)                   # 所有阶数相同; 也 == len(residuals)
    if n_obs <= order + 5:                  # 有效样本守卫 (ADR-041)
        raise ValueError(
            f"AR({order}) 有效样本不足: n_obs={n_obs} <= order+5={order + 5} "
            f"(n={n}, hold_back={hold_back})"
        )

    # 滞后矩阵: 所有列长度均为 n_obs
    X = np.column_stack([
        y[hold_back - i:n - i] for i in range(1, order + 1)
    ])
    X = np.column_stack([np.ones(n_obs), X])

    # OLS估计
    try:
        beta = np.linalg.lstsq(X, y_trimmed, rcond=None)[0]
    except np.linalg.LinAlgError:
        raise ValueError("OLS估计失败")

    coefficients = beta
    fitted = X @ beta
    residuals = y_trimmed - fitted

    # 统计量计算
    k = len(coefficients)                    # = order + 1
    sigma2 = np.var(residuals, ddof=0)
    log_likelihood = -n_obs / 2 * (np.log(2 * np.pi * sigma2) + 1)
    r_squared = 1 - np.var(residuals) / np.var(y_trimmed) if np.var(y_trimmed) > 0 else 0

    # 信息准则 (公式不变; 仅 n_obs 口径统一)
    aic = -2 * log_likelihood + 2 * k
    bic = -2 * log_likelihood + k * np.log(n_obs)
    hqic = -2 * log_likelihood + 2 * k * np.log(np.log(n_obs))

    return ARModelResult(
        order=order,
        coefficients=coefficients,
        residuals=pd.Series(residuals, index=series.index[hold_back:]),
        fitted_values=pd.Series(fitted, index=series.index[hold_back:]),
        aic=aic,
        bic=bic,
        hqic=hqic,
        r_squared=r_squared,
        sigma2=sigma2,
        log_likelihood=log_likelihood
    )
```

### 3.2 与现状 diff (逐行)

| 行 | 现状 | 修复后 |
|----|------|--------|
| `hold_back` | 无 | `hold_back = self.max_order` |
| `y_trimmed` | `y[order:]` | `y[hold_back:]` |
| `n_obs` | `len(residuals)` (隐含 `n-order`) | `len(y_trimmed)` (= `n-hold_back`); 守卫后不再重算 |
| 滞后列 | `y[order-i : None if i==0 else -i]` | `y[hold_back-i : n-i]` |
| 守卫 | 无 | `n_obs <= order+5 → ValueError` |
| 残差索引 | `series.index[order:]` | `series.index[hold_back:]` |
| 拟合值索引 | `series.index[order:]` | `series.index[hold_back:]` |
| OLS try/except | `LinAlgError → ValueError("OLS估计失败")` | **保留不变** (设计 §3.1 伪代码省略此段; 实施保留既有错误处理) |
| AIC/BIC/HQIC 公式 | — | **不变** |

**数学等价性 (固定阶数)**: `min_order == max_order == p` 时 `hold_back = p`, 与现状 `y[p:]` / `y[p-i:n-i]` 逐元素相同; 系数、`llf`、`σ²`、准则完全相同 (T8 锁定)。

### 3.3 守卫与调用方行为

| 调用方 | 代码位置 | 守卫触发时行为 |
|--------|---------|---------------|
| `_fit_best` 选阶循环 | `ar_model.py` L112-L127 | `try/except Exception` → `logger.debug` → `continue` (跳过该阶) |
| `_fit_best` AR(1) 回退 | L129-L133 | **不在 try 内** → 抛错; `batch_fit` 捕获后跳过该列 |
| `transform` 短前缀 | L374-L388 | `try/except Exception` → `logger.debug` → `continue` → 该行保持 identity |
| `batch_fit` | L199-L225 | 捕获异常 → `logger.debug` → 跳过该列 |

**默认配置**: `min_obs=20, max_order=5, warmup_obs=120`; 拟合路径 `n_obs >= 15 > 10` (order=5), 守卫不触发; 仅在 warm-up `t=7..11` 触发 (n_obs=2..6)。

### 3.4 docstring / 注释

| 位置 | 变更 |
|------|------|
| `_fit_ar` docstring | 增加 hold_back 语义、前置条件、索引契约 (见 §3.1) |
| 模块顶部注释 (可选) | 增加 `# v3.3.7 (ADR-041): 跨阶 hold_back 可比性` 一行 |
| `AROrderSelector` 类 docstring | 不改 (选阶语义不变) |
| `ARDecoupler` 类 docstring | 不改 (transform 三段式不变) |

### 3.5 边界语义

与设计 §3.4 一致, 摘要:

| 场景 | 行为 |
|------|------|
| `n < H` / `n = H` | `n_obs <= order+5` → `ValueError` |
| `n_obs <= order+5` | 该阶不可估 → `ValueError` |
| `n_obs > order+5` | 正常拟合; `df_resid >= 5` |
| `order = max_order` | 与现状 `y[order:]` 等价 |
| `min_order == max_order` | `fit` 冻结模型逐值相同; warm-up 段因守卫时点平移 |
| `t < early` | identity (冷启动, 不变) |
| `early <= t < H+min_order+6` | identity (守卫新增) |
| 滞后值 NaN | 该行输出 NaN (不变) |
| 常数序列 (`σ²=0`) | 既有边界, 本次不修 (§8 R7) |

### 3.6 接口与签名核对 (以源代码为准)

| 接口 | 现状签名 | 本任务 |
|------|---------|--------|
| `AROrderSelector.__init__` | `(max_order=5, min_order=1, criterion='aic', min_obs=20)` | 不变 |
| `AROrderSelector.fit` | `(series: pd.Series) -> ARModelResult` | 不变 |
| `AROrderSelector._fit_best` | `(series: pd.Series) -> ARModelResult` | 不变 |
| `AROrderSelector._fit_ar` | `(series: pd.Series, order: int) -> ARModelResult` | **签名不变, 实现变更** |
| `AROrderSelector.batch_fit` | `(data: pd.DataFrame) -> Dict[str, ARModelResult]` | 不变 |
| `ARDecoupler.__init__` | `(max_order=5, min_order=1, criterion='aic', strength=1.0, min_obs=20, warmup_obs=120)` | 不变 |
| `ARDecoupler.fit/transform/fit_transform` | 现状 | 不变 |
| `ARModelResult` | 10 字段 | 不变 |

**调用点核对**:
- `_fit_ar`: L117 (选阶循环) / L132 (回退) / L379 (transform 短前缀); 全部同模块私有调用.
- `ARDecoupler(`: 生产 1 处 (`dual_neutralizer.py` L413, 关键字); 测试若干; 无位置参数破坏.

### 3.7 低效操作排除与复杂度 (spec §13.5)

| 项 | 现状 | 本任务 |
|----|------|--------|
| 每阶 OLS | `np.linalg.lstsq(X, y_trimmed)` | 不变 |
| 矩阵规模 | `(n-order) × (order+1)` | `(n-H) × (order+1)`; 元素数差 ≤ `H×p`, 可忽略 |
| 复杂度 | `O(n_obs·p²)` / 阶 | 不变 (`n_obs = n-H`) |
| 全样本重复构造 | 无 | 无 |
| 新增循环 / 递归 | 无 | 无 |
| 新增依赖 | 无 | 无 |
| 内存 | `O(n_obs·p)` | 同阶 |

**结论**: 无低效操作; 2500×300 单次性能 2.72s vs 基线 2.76s (噪声级, 调研 §6.7)。

### 3.8 兼容性判定 (spec §13.5)

| 维度 | 判定 |
|------|------|
| API / 签名 | **兼容** (无 Public 变更) |
| 配置字段 | **兼容** (无新增/删除) |
| 数值输出 | **不兼容** (93%–96% 格子变化; 需重建缓存) |
| `ARModelResult` 字段 | **兼容** (索引起点/长度变) |
| NaN 模式 | **兼容** (AR 输出无新增 NaN; 索引消费端 `TemporalDecoupler` 可能多 NaN) |
| 固定阶数 `fit` | **等价** (逐值相同) |
| 固定阶数 `transform` | **warm-up 段变化** (冻结段相同; 见设计 §5.2) |
| Python 版本 | 兼容 (无新语法; `>=3.9` 不变) |
| 依赖 | 兼容 (无新增) |

### 3.9 不做的事

- 不修改 AIC 公式 (不补偿 statsmodels 的 -2 偏移)。
- 不新增 AICc / 不切换默认准则。
- 不修改 `_fit_best` 的总长守卫 / 搜索上界 / `min_obs` 默认值。
- 不修改 `transform` 的 `early` / `_WARMUP_REFIT_STRIDE` / `warmup_obs`。
- 不修 `optimized.py` / `unified_decoupler.py`。
- 不增加构造参数校验 (`min_obs` vs `max_order`); 仅在文档写明约束。

---

## §4 TDD 测试

### 4.1 Red: `tests/unit/test_ar_order_holdback.py`

```python
# -*- coding: utf-8 -*-
"""PL-08 / ADR-041: AR 阶数选择 hold_back 可比性测试.

覆盖: 有效样本一致 / statsmodels 语义对齐 / 守卫边界 / 索引契约 /
AR(1)-AR(3) 选阶恢复 / 固定阶数 fit 等价 / warm-up 无退化 /
早期截断不变式.
"""
import warnings

import numpy as np
import pandas as pd
import pytest
from statsmodels.tsa.ar_model import AutoReg

from factor_pipeline.modules.factor_decoupler.core.ar_model import (
    ARDecoupler,
    AROrderSelector,
)


def _ar_panel(n_periods, n_stocks, seed, phis):
    """AR(p) 面板; phis = [phi_1, ..., phi_p]."""
    rng = np.random.default_rng(seed)
    p = len(phis)
    arr = np.zeros((n_periods, n_stocks))
    for t in range(p):
        arr[t] = rng.standard_normal(n_stocks)
    for t in range(p, n_periods):
        arr[t] = sum(phis[i] * arr[t - 1 - i] for i in range(p)) \
            + rng.standard_normal(n_stocks)
    return pd.DataFrame(
        arr, index=pd.date_range('2020-01-31', periods=n_periods, freq='ME'),
        columns=[f'S{i:03d}' for i in range(n_stocks)],
    )


def _series(n, seed, phi=0.7):
    rng = np.random.default_rng(seed)
    y = np.zeros(n)
    y[0] = rng.standard_normal()
    for t in range(1, n):
        y[t] = phi * y[t - 1] + rng.standard_normal()
    return pd.Series(y, index=pd.date_range('2020-01-31', periods=n, freq='ME'))


def test_common_effective_sample():
    """T1: 所有阶数的估计样本长度相同 = n - max_order."""
    s = _series(100, 22)
    sel = AROrderSelector(max_order=5)
    lengths = {p: len(sel._fit_ar(s, p).residuals) for p in range(1, 6)}
    assert set(lengths.values()) == {95}, lengths


@pytest.mark.parametrize('p', [1, 2, 3, 4, 5])
def test_matches_statsmodels_hold_back(p):
    """T2: 系数 / llf / sigma2 / n_obs 与 AutoReg(hold_back=H) 一致."""
    s = _series(100, 22)
    sel = AROrderSelector(max_order=5)
    r = sel._fit_ar(s, p)
    m = AutoReg(s.values, lags=p, hold_back=5, trend='c').fit()

    np.testing.assert_allclose(r.coefficients, m.params, atol=1e-10, rtol=0)
    assert r.log_likelihood == pytest.approx(m.llf, abs=1e-10)
    assert r.sigma2 == pytest.approx(m.sigma2, abs=1e-10)
    assert len(r.residuals) == int(m.nobs)
    assert r.aic - m.aic == pytest.approx(-2.0, abs=1e-10)


@pytest.mark.parametrize('order', [1, 3, 5])
def test_guard_rejects_insufficient_effective_sample(order):
    """T3: n_obs = order+5 抛错; order+6 通过."""
    H = 5
    sel = AROrderSelector(max_order=5)
    with pytest.raises(ValueError, match='有效样本不足'):
        sel._fit_ar(_series(H + order + 5, 3), order)
    r = sel._fit_ar(_series(H + order + 6, 3), order)
    assert len(r.residuals) == order + 6


def test_residual_index_starts_at_hold_back():
    """T4: residuals / fitted_values 索引从 H 开始."""
    s = _series(100, 22)
    sel = AROrderSelector(max_order=5)
    r = sel._fit_ar(s, 3)

    assert r.residuals.index[0] == s.index[5]
    assert r.fitted_values.index[0] == s.index[5]
    assert len(r.residuals) == len(s) - 5
    assert len(r.fitted_values) == len(s) - 5


def test_order_selection_low_on_ar1():
    """T5: AR(1) 真值面板选阶均值 <= 2.0."""
    df = _ar_panel(100, 30, 22, [0.7])
    res = AROrderSelector(max_order=5).batch_fit(df)
    orders = np.array([r.order for r in res.values()])
    assert len(res) == 30
    assert orders.mean() <= 2.0


def test_order_selection_recovers_ar2():
    """T6: AR(2) 真值面板选阶均值 ∈ [1.8, 3.2]."""
    df = _ar_panel(120, 30, 11, [0.6, 0.3])
    res = AROrderSelector(max_order=5).batch_fit(df)
    orders = np.array([r.order for r in res.values()])
    assert 1.8 <= orders.mean() <= 3.2


def test_order_selection_recovers_ar3():
    """T7: AR(3) 真值面板选阶均值 ∈ [2.4, 3.8]."""
    df = _ar_panel(120, 30, 5, [0.5, 0.3, 0.2])
    res = AROrderSelector(max_order=5).batch_fit(df)
    orders = np.array([r.order for r in res.values()])
    assert 2.4 <= orders.mean() <= 3.8


@pytest.mark.parametrize('p', [1, 2, 3])
def test_fixed_order_fit_matches_current_formula(p):
    """T8: 固定阶数时 hold_back=p 与旧公式 y[p:] 逐值相同."""
    s = _series(100, 11)
    fit_s = s.iloc[:40]                     # fit 只用前 warmup_obs=40 行
    d = ARDecoupler(max_order=p, min_order=p, warmup_obs=40).fit(
        fit_s.to_frame('S'))
    r = d._results['S']

    y = fit_s.values
    X = np.column_stack([y[p - i:len(y) - i] for i in range(1, p + 1)])
    X = np.column_stack([np.ones(len(y) - p), X])
    beta = np.linalg.lstsq(X, y[p:], rcond=None)[0]

    np.testing.assert_allclose(r.coefficients, beta, atol=0, rtol=0)


def test_no_zero_variance_fit_in_warmup():
    """T9: warm-up 早期无 sigma2=0 / ln(0); t<12 保持 identity."""
    df = _ar_panel(80, 3, 5, [0.7])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        out = ARDecoupler(max_order=5, warmup_obs=40).fit_transform(df)

    bad = [w for w in caught
           if 'divide by zero' in str(w.message)
           or 'invalid value' in str(w.message)]
    assert not bad, [str(w.message) for w in bad]
    assert np.isfinite(out.to_numpy(dtype=float)).all()
    np.testing.assert_array_equal(
        out.iloc[:12].to_numpy(dtype=float),
        df.iloc[:12].to_numpy(dtype=float),
    )


@pytest.mark.parametrize('t', [7, 8, 9, 10, 12])
def test_warmup_early_truncation_invariant(t):
    """T10: 早期截断点仍满足前缀不变式."""
    df = _ar_panel(100, 10, 22, [0.7])
    full = ARDecoupler(max_order=3, warmup_obs=40).fit_transform(df)
    trunc = ARDecoupler(max_order=3, warmup_obs=40).fit_transform(df.iloc[:t])

    a = full.to_numpy(dtype=float)[:t]
    b = trunc.to_numpy(dtype=float)
    assert np.array_equal(np.isnan(a), np.isnan(b))
    both = ~np.isnan(a) & ~np.isnan(b)
    np.testing.assert_allclose(a[both], b[both], atol=1e-12, rtol=0)
```

### 4.2 Red 实测 (步骤 5 预演)

**方法**: 将 §4.1 原样保存为临时测试文件 (`%TEMP%\test_ar_order_holdback.py`), 直接运行于**当前未修改**的实现:

```text
13 failed, 9 passed in 3.15s
```

| 测试 | 用例 | Red 实测 | 原因 |
|------|------|---------|------|
| T1 | 1 | **fail** | `n_obs` 99/98/97/96/95 不等 |
| T2 | 5 | **4 fail / 1 pass** | p=1..4 样本不同; p=5 当前 `y[5:]` 恰好等于 hold_back=5 |
| T3 | 3 | **3 fail** | 无守卫, 短样本可拟合不抛错 |
| T4 | 1 | **fail** | 索引从 `order` 开始, 非 `H` |
| T5 | 1 | **fail** | 当前均值 4.800 > 2.0 |
| T6 | 1 | **fail** | 当前均值 4.87 不在 [1.8,3.2] |
| T7 | 1 | **fail** | 当前均值 4.97 不在 [2.4,3.8] |
| T8 | 3 | **3 pass** | 固定阶数时旧公式与 hold_back 数学等价 |
| T9 | 1 | **fail** | 当前 `t=7..11` 已解耦, 非 identity |
| T10 | 5 | **5 pass** | PL-05 已保证截断不变式 |
| **合计** | **22** | **13 failed / 9 passed** | — |

> 该结果与静态推演完全一致。步骤 9 正式落库复测同为 **13 failed / 9 passed (0.65s)**。

### 4.3 Green: 代码实现

按 §3.1 修改 `_fit_ar`; 不改其他生产代码。

**步骤 5 预演**: 用与 §3.1 逐行等价的临时 patch (`%TEMP%\pl08_patch.py`, 含中文异常文案), 运行同一测试文件:

```text
22 passed in 0.34s
```

> 正式实施后以仓库内测试文件的 Green 结果为准, 回填 §7.2。

### 4.4 既有测试回归

```powershell
python -m pytest `
  tests/unit/test_ar_decoupler_causality.py `
  tests/test_factor_decoupler/test_hidden_effect.py `
  tests/test_pipelines_v2.py `
  tests/integration/test_pipeline_truncation_invariance.py -q
```

| 项 | 基线 | 实施后目标 |
|----|------|-----------|
| passed | 72 | **72** (新增测试不计入该命令) |
| failed | 1 (duckdb 环境) | **1 (同一环境项)** |
| 新增失败 | — | **0** |

**预演证据**: 设计 §6.2 用运行时 patch 已实测两组均为 72 passed / 1 failed (17.58s / 20.64s)。

### 4.5 性能验证 (手工, 不入 CI)

```python
# 2500×300, 单次 fit_transform
import time, numpy as np, pandas as pd
from factor_pipeline.modules.factor_decoupler.core.ar_model import ARDecoupler
rng = np.random.default_rng(7)
T, N = 2500, 300
a = np.zeros((T, N)); a[0] = rng.standard_normal(N)
for t in range(1, T):
    a[t] = 0.7 * a[t - 1] + rng.standard_normal(N)
df = pd.DataFrame(a, index=pd.date_range('2010-01-31', periods=T, freq='ME'))
t0 = time.perf_counter(); ARDecoupler(max_order=5).fit_transform(df)
print(time.perf_counter() - t0)
```

**通过标准**: ≤ 3.1s (基线 2.76s, 预期 2.72s)。

### 4.6 输出偏移复测 (手工)

| 面板 | 指标 | 预期 |
|------|------|------|
| T=100/N=30 seed=22 | 变化格子 / `max_abs` / `mean_abs` | 2790/3000 (93.0%) / 6.9968 / 0.3295 |
| T=500/N=30 seed=42 | 变化格子 / `max_abs` / `mean_abs` / MSE | 14410/15000 (96.1%) / 4.6718 / 0.1337 / 1.048759 |

允许 ±5% 格数、±0.02 `max_abs` 的浮动 (浮点/环境差异); 若超出, 检查是否误改了 `transform`。

---

## §5 版本、缓存与文档

### 5.1 版本 → v3.3.7

| # | 文件 | 行 | 现状 | 改为 |
|---|------|----|------|------|
| 1 | `pyproject.toml` | L7 | `version = "3.3.6"` | `"3.3.7"` |
| 2 | `__init__.py` | L58 | `__version__ = "3.3.6"` | `"3.3.7"` |
| 3 | `config_v2.py` | L371 | `version: str = Field(default="3.3.6")` | `"3.3.7"` |
| 4 | `reporting.py` | L40 | `pipeline_version: str = "3.3.6"` | `"3.3.7"` |
| 5 | `tests/test_fix3_version_unification.py` | L33 | `EXPECTED_VERSION = "3.3.6"` | `"3.3.7"` |
| 6 | 同上 | L12/L40/L48/L57 | docstring 中的 3.3.6 | 同步为 3.3.7 (保留 v3.3.6 历史行) |
| 7 | `tests/test_backtest/verify_fix3_manual.py` | L21 | `EXPECTED_VERSION = "3.3.6"` | `"3.3.7"` |
| 7b | 同上 | L5 | docstring "5 个预期位置的版本号均为 3.3.6" | 同步为 3.3.7 |
| 8 | `README.md` | L1029/L1032/L1035/L1059 | 版本信息 / 测试基线 / 状态 / 历史表 | 3.3.7 + 历史追加 v3.3.7 行 (测试基线数字以步骤 9 实测为准) |
| 9 | `docs/ARCHITECTURE.md` | L17/L20 | AR 因果描述 / 版本基线止于 v3.3.6 | L17 追加 "自 v3.3.7 起阶数选择统一 hold_back 样本"; L20 追加 v3.3.7 节点 |

### 5.2 缓存 → `v2.2.5-cache`

| # | 文件 | 行 | 现状 | 改为 |
|---|------|----|------|------|
| 1 | `backtest/cache_manager.py` | L58 | `CODE_VERSION = "v2.2.4-cache"` | `"v2.2.5-cache"` |
| 2 | `tests/test_fix3_version_unification.py` | L96 | 断言 `"v2.2.4-cache"` | `"v2.2.5-cache"` |
| 3 | 同上 | L97 | 断言失败消息中的 `'v2.2.4-cache'` | 同步为 `'v2.2.5-cache'` (v1.2 补列, 避免消息与断言值不一致) |
| 4 | 同上 | L112 | `expected = "v2.2.4-cache"` | `"v2.2.5-cache"` |
| 5 | 同上 | L14 | docstring 当前统一目标行 `= "v2.2.4-cache"` | 改值为 `"v2.2.5-cache"` (v1.2 勘误: 该行为当前目标描述, 非历史) |
| 6 | 同上 | L80/L87 | docstring 历史 (test_05/test_07) | 追加 v3.3.7 行, 保留 `v2.2.3→v2.2.4` 历史 |

### 5.3 ADR-041 (写入 `DECISIONS.md`)

**占用表变更**:

```markdown
| ADR-041 | AR 阶数选择统一 hold_back 样本 (信息准则可比性) | v3.3.7, 2026-11-04 |
| ADR-042 起 | 未占用 | — |
```

**正文**:

```markdown
## ADR-041: AR 阶数选择统一 hold_back 样本 (信息准则可比性)

**日期**: 2026-11-04
**状态**: 待实施 (步骤 9 TDD 完成后改为「已实施」)
**优先级**: P1
**关联缺陷**: DEFECT-PL-08
**关联测试**: `tests/unit/test_ar_order_holdback.py`
**调研/设计**: [PL08_AR_ORDER_AIC_COMPARABILITY_RESEARCH.md](docs/analysis/PL08_AR_ORDER_AIC_COMPARABILITY_RESEARCH.md) /
[PL08_AR_ORDER_AIC_COMPARABILITY_DESIGN.md](docs/analysis/PL08_AR_ORDER_AIC_COMPARABILITY_DESIGN.md)

### 背景

`AROrderSelector._fit_ar` 对每个阶数 `p` 使用 `y[p:]` 作为响应向量，使
`n_obs = n - p`。AIC/BIC/HQIC 的似然项 `-n_obs/2(ln(2πσ²)+1)` 因此建立在
不同样本上：每多一阶少 1 个观测，样本因子约降 `ln(2πσ²)+1 ≈ 2.84`，大于
AIC 的参数罚 `2`，导致阶数被系统性推向 `max_order`。

实测 (`T=100, N=30, seed=22`, AR(1) φ=0.7): AIC 均值 **4.800**、
BIC **2.200**、HQIC **3.867**（上限 5）。

### 决策

1. `_fit_ar` 统一 `hold_back = self.max_order`；所有阶数使用 `y[H:]` 与
   `x[H:]`，满足 statsmodels `AutoReg(hold_back=maxlag)` 的可比性语义。
2. 增加有效样本守卫：`n_obs <= order + 5 → ValueError`；保证
   `df_resid >= 5`，并排除 `n_obs = k` 的精确拟合（`σ²=0` / `ln(0)`）。
3. `residuals` / `fitted_values` 索引统一为 `series.index[H:]`。
4. `transform` 不改（`early = min_order + 6`）；守卫使 warm-up `t=7..11`
   自然保持 identity。
5. 默认准则保持 `aic`；不新增 AICc、不切换 BIC/HQIC 默认。

### 备选方案 (拒绝/延后)

- **A 仅 hold_back**：`t=7..11` 出现 `σ²=0` / `ln(0)`，`max_abs=322.68`。
- **B 守卫 `order+2`**：消除 `σ²=0`，但早期仍用 4–6 个观测（`max_abs=5.3131`）。
- **D +AICc**：生产窗口 `n_obs=115` 下与 AIC 分布几乎相同，MSE 无改善。
- **E 默认 BIC**：AR(3) 真值面板均值 2.53（低估）；超出缺陷范围。

### 代码证据

| 组件 | 位置 |
|------|------|
| 统一 hold_back + 守卫 + 索引 | `modules/factor_decoupler/core/ar_model.py` `AROrderSelector._fit_ar` |
| 选阶调用方（不改） | 同文件 `_fit_best` / `ARDecoupler.transform` |
| 新单测 | `tests/unit/test_ar_order_holdback.py` |

### 实测证据（方案 C 探针）

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| `n_obs` (AR(1..5), n=100) | 99/98/97/96/95 | **95/95/95/95/95** |
| 阶数均值 (AR(1), T=100) | AIC 4.800 / BIC 2.200 / HQIC 3.867 | **1.233 / 1.000 / 1.000** |
| 阶数均值 (AR(2), T=120) | 4.87 | **2.53** |
| 阶数均值 (AR(3), T=120) | 4.97 | **3.23** |
| 输出偏移 (T=100/N=30) | — | **2790/3000 (93.0%)**, `max_abs=6.9968` |
| 输出偏移 (T=500/N=30) | — | **14410/15000 (96.1%)**, `max_abs=4.6718` |
| 尾部一步 MSE (T=500) | 1.067782 | **1.048759** |
| 截断不变式 (11 点) | 0/0 | **0/0** |
| AR 性能 (2500×300) | 2.76s | **2.72s** |

### 测试契约

- T1 `n_obs` 全等；T2 statsmodels 逐项一致（参数/`llf`/`σ²`/`nobs`，AIC 差 -2）；
  T3 守卫边界；T4 索引契约；T5–T7 阶数恢复；T8 固定阶数 `fit` 等价；
  T9 warm-up 无退化 + early identity；T10 早期截断不变式。
- 既有行为测试不改；靶向套件 72 passed / 1 env-fail（duckdb）。

### 不覆盖

- `OptimizedARDecoupler._fit_ar_order`（独立副本，非生产路径）。
- `TemporalDecoupler` 的 AR 方法（共用选择器，阶数被动变化）。
- AIC 的不一致性（固定概率过选阶；本 ADR 只修可比性）。
- 常数序列的既有 `σ²=0` 边界。
- 配置面 / optimizer / `min_obs` 参数校验。

### 后果

- **正面**：信息准则跨阶可比；阶数分布回到合理区间；AR(2)/AR(3) 仍可识别；
  消除 warm-up 早期退化拟合。
- **负面/破坏性**：存量 AR/Dynamic 输出 93%–96% 格子变化；历史 IC/Sharpe 需重算；
  缓存代际 bump。
- **风险**：固定阶数时 warm-up 段仍变化（冻结模型等价）；极端
  `min_obs`/`max_order` 配置可能整列不可估（既有降级：跳过该列）。

### 学术与工业依据

- statsmodels `AutoReg` 官方文档 / 源码：`hold_back` 默认 `maxlag`，
  `hold_back >= maxlag`，`y=y[hold_back:]`、`x=x[hold_back:]`（A）。
- Cross Validated Q94718 接受答案：不同样本量的模型不能用任何信息准则比较（A）。
- Shibata (1976, Biometrika 63:117–126)：AIC 有正概率渐近过选阶；
  BIC/HQIC 强一致（A 元数据 / B 转述）。
- Hurvich & Tsai (1989, Biometrika 76:297–307)：AICc 小样本修正；
  Hurvich NYU 讲义给出修正因子（A）。
- Ing & Wei (2005, Ann. Statist.)：AIC 对一步预测渐近有效（A 摘要）。

### 回滚方案

恢复 `_fit_ar` 的 `y[order:]` / 滞后列 / `n_obs=n-order` / 索引 `index[order:]`；
删除守卫；版本回 v3.3.6、缓存回 `v2.2.4-cache`；删除并重建缓存。
```

### 5.4 CHANGELOG v3.3.7 (模板, 实测值待步骤 9 回填)

```markdown
## v3.3.7 — PL-08 AR 阶数选择 hold_back 可比性修复 (已实施, 2026-11-04)

### 概览

修复 DEFECT-PL-08: `AROrderSelector._fit_ar` 对每个阶数使用 `y[order:]`，
使 AIC/BIC/HQIC 的似然项建立在不同样本上，阶数被系统性推向 `max_order`。

**核心产出**:
- `_fit_ar` 统一 `hold_back = max_order`，所有阶数使用同一估计样本
- 增加有效样本守卫 `n_obs <= order+5 → ValueError`，消除 warm-up `σ²=0`
- `residuals` / `fitted_values` 索引统一为 `series.index[H:]`
- 新增 10 个单测函数 / 22 个 pytest 用例
- 新增 **ADR-041**；项目版本 **3.3.7**；缓存 `CODE_VERSION` **v2.2.5-cache**

### 缺陷根因

| # | 根因 | 证据 |
|---|------|------|
| 1 | `y_trimmed = y[order:]` | 各阶 `n_obs = n-order` 不同 |
| 2 | 似然项随 `n_obs` 缩短 | 每阶样本因子约降 2.84 > AIC 罚 2 |
| 3 | 无有效样本守卫 | warm-up `t=7` 仅 2 个观测，`σ²=0` / `ln(0)` |

### 实测矩阵 (待步骤 9 回填实测值)

| 层级 | 对象 | 修复前 | 修复后 |
|------|------|--------|--------|
| unit | `n_obs` (AR(1..5)) | 99/98/97/96/95 | **95×5** |
| unit | AR(1) 选阶均值 | 4.800 | **1.233** |
| unit | AR(2) 选阶均值 | 4.87 | **2.53** |
| unit | AR(3) 选阶均值 | 4.97 | **3.23** |
| output | T=100/N=30 | — | **2790/3000 (93.0%)**, `max_abs=6.9968` |
| output | T=500/N=30 | — | **14410/15000 (96.1%)**, `max_abs=4.6718` |
| quality | 尾部一步 MSE | 1.067782 | **1.048759** |
| invariant | 截断不变式 (11 点) | 0/0 | **0/0** |
| perf | AR 2500×300 | 2.76s | **2.72s** |

### 变更文件

| 文件 | 变更 |
|------|------|
| `modules/factor_decoupler/core/ar_model.py` | `_fit_ar` hold_back + 守卫 + 索引 + docstring |
| `tests/unit/test_ar_order_holdback.py` | **新增** 10 函数 / 22 用例 |
| `pyproject.toml` / `__init__.py` / `config_v2.py` / `reporting.py` | 3.3.7 |
| `backtest/cache_manager.py` | `v2.2.5-cache` |
| `tests/test_fix3_version_unification.py` / `tests/test_backtest/verify_fix3_manual.py` | 版本/缓存字面量 |
| `DECISIONS.md` / `CHANGELOG.md` / `README.md` / `docs/PROJECT_STATUS.md` / `docs/DEV_PROGRESS.md` | ADR-041 / v3.3.7 |

### 兼容性

- **不兼容**: AR/Dynamic 输出 93%–96% 格子变化；需重建缓存。
- **兼容**: 公共 API / 签名 / 配置字段 / `ARModelResult` 字段不变。
- **固定阶数**: `fit` 冻结模型逐值相同；`transform` warm-up 段变化，冻结段相同。

### 已知遗留

- `OptimizedARDecoupler` / `TemporalDecoupler` 同类缺陷未修（非生产路径）。
- AIC 不一致性未修（方法学性质；本版本只修可比性）。
- 常数序列 `σ²=0` 既有边界未修。
```

### 5.5 状态文档

| 文件 | 变更 |
|------|------|
| `docs/PROJECT_STATUS.md` | 版本路标到 v3.3.7; 执行历史追加 v3.3.7; P1 下一任务更新 |
| `docs/DEV_PROGRESS.md` | §4 待办勾选 PL-08; 文档索引补 v3.3.7 |
| `docs/ARCHITECTURE.md` | L17 因果性描述追加 hold_back; L20 版本基线追加 v3.3.7 |
| `README.md` | 版本信息 3.3.7; 版本历史追加 v3.3.7 |

---

## §6 执行顺序与 spec 步骤映射

### 6.1 spec 10 步映射

| 步 | 状态 | 工件 |
|----|------|------|
| 1 调研 | ✅ | `PL08_..._RESEARCH.md` v1.2 |
| 2 调研 review | ✅ | 同文档 §修订记录 v1.1 (步骤 3 回注为 v1.2) |
| 3 设计 | ✅ | `PL08_..._DESIGN.md` v1.2 (v1.0 初稿 → 步骤 4 review v1.1 → 步骤 8 勘误 v1.2) |
| 4 设计 review | ✅ | 同文档 §12, v1.1 |
| 5 实施文档 | ✅ | 本文档 v1.2 (v1.0 初稿 → 步骤 6 review v1.1 → 步骤 8 一致性 v1.2) |
| 6 实施文档 review | ✅ | 附录 C (C1-C11 通过, F1-F5 修复) |
| 7 验收 checklist | ✅ | `docs/audit/CHECKLIST_V3.3.7_PL08.md` v1.1 |
| 8 文档一致性 review | ✅ | `docs/audit/CONSISTENCY_REVIEW_V3.3.7.md` (M1-M4 已修复) |
| 9 TDD 实现 | ✅ | 代码 + 测试 + §7.2 回填 (2026-11-04) |
| 10 审查验收 | ✅ | `docs/audit/2026-11-04-code-quality-audit.md` v1.2 续篇 (**PASS**, 2026-11-05) |

### 6.2 执行顺序 (含检查点)

| 序 | 动作 | 检查点 |
|----|------|--------|
| 1 | 写 Red 测试 (T1–T10) | 步骤 5 预演 13 failed / 9 passed; 正式落库复测回填 |
| 2 | 改 `_fit_ar` | Green 22 passed |
| 3 | 跑靶向套件 | 72 passed / 1 env-fail, 无新增失败 |
| 4 | 性能 + 偏移复测 | ≤3.1s; 偏移与 §1.3 一致 |
| 5 | 版本 / 缓存 / ADR / CHANGELOG | `test_fix3` 7 passed |
| 6 | 步骤 7 checklist / 8 一致性 / 10 审计 | 文档签署 |

---

## §7 验收记录

### 7.1 基线 (实施前, 2026-11-04 实测)

| 项 | 值 |
|----|-----|
| 靶向套件 | **72 passed / 1 failed (17.58s)**; 失败 = duckdb 环境 |
| `n_obs` | 99/98/97/96/95 |
| 阶数均值 (AR(1) T=100) | AIC 4.800 / BIC 2.200 / HQIC 3.867 |
| 阶数均值 (AR(2)/AR(3) T=120) | 4.87 / 4.97 |
| 尾部 MSE | 1.067782 |
| AR 性能 | 2.76s |

### 7.2 实施后 (步骤 9 实测, 2026-11-04)

**正式落库实测** (仓库内测试文件 + 已合入的 `_fit_ar`): Red **13 failed / 9 passed (0.65s)**; Green **22 passed (0.29s)**。

| 项 | 目标 | 实测 | 状态 |
|----|------|------|------|
| Red | 13 failed / 9 passed | **13 failed / 9 passed (0.65s)** | ✅ |
| Green | 22 passed | **22 passed (0.29s)** | ✅ |
| 靶向套件 | 72 passed / 1 env-fail | **72 passed / 1 env-fail (43.01s)** | ✅ |
| `n_obs` | 95×5 | **95/95/95/95/95** | ✅ |
| 阶数均值 (AR(1)/AR(2)/AR(3)) | 1.233 / 2.53 / 3.23 | **1.233 / 2.533 / 3.233**, BIC/HQIC 1.000 | ✅ |
| 输出偏移 T=100 | 2790/3000, 6.9968 | **2790/3000 (93.0%), max_abs 6.9968, mean_abs 0.3295** | ✅ |
| 输出偏移 T=500 | 14410/15000, 4.6718 | **14410/15000 (96.1%), max_abs 4.6718, mean_abs 0.1337** | ✅ |
| 尾部 MSE | 1.048759 | **1.048759** (旧 1.067782) | ✅ |
| 截断不变式 (11 点) | 0/0 | **0/0** (既有 7 点 + T10 5 点) | ✅ |
| 性能 | ≤3.1s | **2.64s** | ✅ |
| 版本/缓存测试 | `test_fix3` 7 passed | **合并靶向运行 7 passed**; 隔离运行 6 passed / 1 env-fail (duckdb 阻断 `backtest` 包导入) | ⚠️ 环境条件项 |
| 固定阶数兼容性 | 系数逐值相同; warm-up 99/96/93 格; 冻结段 0 | **coef_identical=True; 99/96/93 格; max 2.694613/5.251495/5.973263; first=7/8/9; last=39** | ✅ |

> 环境例外: `duckdb` 未安装导致 `test_E10_bridge_init_params_exist` 与 `test_fix3::test_05` (隔离运行时) 失败; 二者在基线/实施后同源同量, 不计入 PL-08 验收 (详见 checklist §1 签署区)。

---

## §8 风险、回滚与后续

### 8.1 风险

| # | 风险 | 处置 |
|---|------|------|
| R1 | 输出 93%–96% 变化, 历史 IC/Sharpe 不可比 | CHANGELOG 明示; 缓存 bump; 重算 |
| R2 | AIC 仍不一致 | 文档写明"可比性修复"; 非目标 |
| R3 | 固定阶数 warm-up 段变化 (93–99/300 格) | 文档写明"冻结模型等价"; 测试不断言 warm-up 逐值 |
| R4 | `TemporalDecoupler` 被动变化 | 非生产路径; 登记; 不纳入验收 |
| R5 | 极端 `min_obs`/`max_order` 整列不可估 | 既有降级 (跳过该列); 文档写明 `min_obs > 2*max_order+5` |
| R6 | `_fit_ar` 前置 `series` 已 dropna | 所有内部调用方满足; docstring 写明 |
| R7 | 常数序列 `σ²=0` 既有边界 | 不在本次范围; 另立任务 |
| R8 | 性能回退 | 实测 2.72s; 验收 ≤3.1s |

### 8.2 回滚

1. 恢复 `_fit_ar` 四处改动 (hold_back / 滞后列 / `n_obs` / 索引);
2. 删除守卫;
3. 版本回 3.3.6、缓存回 `v2.2.4-cache`;
4. 删除并重建缓存。

### 8.3 后续任务

| 任务 | 说明 |
|------|------|
| `OptimizedARDecoupler` / `TemporalDecoupler` 治理 | 非生产路径, 独立任务 |
| v3.3.6 冻结模型实证回测 | ADR-040 风险段 |
| 真实因子 IC/Sharpe 对比 | 本版输出变更后的下游验证 |
| 常数序列 `σ²=0` | 既有边界, 独立任务 |

---

## §9 交付物

| 类型 | 文件 |
|------|------|
| 代码 | `modules/factor_decoupler/core/ar_model.py` |
| 测试 | `tests/unit/test_ar_order_holdback.py` (新) |
| 版本 | `pyproject.toml` / `__init__.py` / `config_v2.py` / `reporting.py` / `backtest/cache_manager.py` |
| 测试锚点 | `tests/test_fix3_version_unification.py` / `tests/test_backtest/verify_fix3_manual.py` |
| 决策 | `DECISIONS.md` (ADR-041) |
| 日志 | `CHANGELOG.md` (v3.3.7) |
| 状态 | `README.md` / `docs/PROJECT_STATUS.md` / `docs/DEV_PROGRESS.md` |
| 流程 | `docs/audit/CHECKLIST_V3.3.7_PL08.md` / `docs/audit/CONSISTENCY_REVIEW_V3.3.7.md` (步骤 7/8) |

---

## 附录 A: 全仓 grep 检查清单

```powershell
# 1. ar_model.py 不再有跨阶不同样本
git grep -n "y\[order" -- modules/factor_decoupler/core/ar_model.py
# 期望: 0 命中

# 2. 残差索引不再从 order 开始
git grep -n "series.index\[order:\]" -- modules/factor_decoupler/core/ar_model.py
# 期望: 0 命中

# 3. hold_back 出现位置
git grep -n "hold_back" -- modules/factor_decoupler/core/ar_model.py
# 期望: _fit_ar 内 >=3 处 (赋值 / 切片 / 索引)

# 4. 仅 optimized.py 保留同类写法 (白名单)
git grep -n "y\[order" -- modules/
# 期望: 仅 modules/factor_decoupler/core/optimized.py:221-222

# 5. 版本锚点
git grep -n "3\.3\.6" -- pyproject.toml __init__.py config_v2.py reporting.py
# 期望: 0 命中

# 6. 缓存旧代号
git grep -n "v2\.2\.4-cache" -- backtest/cache_manager.py tests/test_fix3_version_unification.py
# 期望: 仅历史注释 (若有); 默认值/断言 0 命中

# 7. 新增测试文件
git status --short tests/unit/test_ar_order_holdback.py
# 期望: ?? (新文件)
```

---

## 附录 B: 待实施后回填清单

| # | 位置 | 回填内容 |
|---|------|---------|
| 1 | §4.2 | Red 正式实测计数 **13/9 (0.65s)** (已回填) |
| 2 | §7.2 | Green **22 passed (0.29s)** (已回填) |
| 3 | §7.2 | 靶向套件实测 **72/1 (43.01s)** (已回填) |
| 4 | §7.2 | 阶数分布 / 输出偏移 / MSE / 性能实测 (已回填) |
| 5 | §7.2 | `test_fix3` 合并运行 7 passed; `verify_fix3_manual` [1][2] 通过, [3] 环境阻断 (已回填) |
| 6 | §5.3 ADR-041 | 状态「待实施」→「已实施」 (已写入 DECISIONS.md) |
| 7 | §5.4 CHANGELOG | 实测矩阵最终值 (已写入 CHANGELOG.md) |
| 8 | 附录 C | 步骤 6 review 记录 (已存在) |
| 9 | `docs/audit/CHECKLIST_V3.3.7_PL08.md` | Gate 逐项状态 (已回填 Gate 0–7) |
| 10 | `docs/audit/CONSISTENCY_REVIEW_V3.3.7.md` | 四文档一致性 (已完成, 步骤 8) |

---

## 附录 C: 步骤 6 review 记录 (幻觉排查与代码/接口对齐)

**方法**: 实施文档逐项回源 (接口签名/调用点/版本与缓存字面量行号/测试锚点/既有文件 grep 实测), TDD 用例静态对账 + 步骤 5 预演实证, ADR-041 数字与调研 v1.2 逐项比对。

### C.1 核对通过项

| # | 检查项 | 方法 | 结果 |
|---|--------|------|------|
| C1 | `_fit_ar` 签名 `(self, series: pd.Series, order: int) -> ARModelResult` | 读源码 L139 | **一致** |
| C2 | 调用点: 生产 `dual_neutralizer.py` L413-L417 (关键字, 无位置参数); `_fit_ar` 调用全集 L117/L132/L379 | grep | **一致** (§3.6 声明成立) |
| C3 | 版本字面量: pyproject L7 / `__init__` L58 / config_v2 L371 / reporting L40 / test_fix3 L33+L96+L112+L12+L40+L48+L57 / verify_fix3 L21 | grep | **全部吻合**; 另发现 L5 漏项 (F2) |
| C4 | 测试用例计数: 10 函数 = 1+1+1+1+1+1+1+1+1+1; 22 用例 = 1+5+3+1+1+1+1+3+1+5 | 对账 §4.1 | **一致**; 预演 Red 13/9、Green 22/22 实证 |
| C5 | 既有锚点: `test_truncation_invariant_multi_cut` 7 点 / `_panel(100,10,seed=22)` phi=0.7 / `test_ar_order_holdback.py` 不存在 | 读码 + Test-Path | **T10 配置成立; 无命名冲突** |
| C6 | 复杂度: `n_obs = n-H` 与 `n-order` 同阶; 矩阵元素差 ≤ H×p; 无新增循环/依赖 | 静态 | **无低效操作** |
| C7 | 兼容性: `ARModelResult` 10 字段不变; TemporalDecoupler NaN 影响与调研 §7.1 一致; duckdb 基线失败两轮相同 | 读码 + 实测 | **判定成立** |
| C8 | ADR-041 数字: 4.800/2.200/3.867 → 1.233/1.000/1.000; 2.53/3.23; 2790 与 14410; 6.9968/4.6718; 1.067782→1.048759; 2.76→2.72; Shibata 63:117-126; Hurvich 76:297-307 | 逐项比对调研 v1.2 | **全部一致** |
| C9 | §0.3 映射表 10 条调研/设计 §编号 | 逐条打开 | **全部有效** |
| C10 | statsmodels API 声明: `AutoReg(lags=p, hold_back=5, trend='c')` | T2 预演通过 | **实证** (阶段 5 工程核实) |
| C11 | 附录 A grep 可行性: 4 个版本文件各仅 1 处 `3.3.6` (修改后 0 命中成立) | grep 实测 | **成立** |

### C.2 发现并已修复的问题

| # | 严重度 | 问题 | 修复 |
|---|--------|------|------|
| F1 | MINOR | §1.1 环境表 (3.13.5/numpy 2.1.3) 与 PL-05 文档记录 (3.12.10/numpy 2.4.6) 存在漂移, 未注明 | 已加"环境漂移说明": 本任务实测以本表环境为准, 差异不影响结论 |
| F2 | MINOR | §5.1 漏 `verify_fix3_manual.py` L5 docstring 的 "3.3.6" 字样 (grep 实测 L5+L21 两处) | 已补 7b 行 |
| F3 | MINOR | §3.1 保留既有 `LinAlgError → ValueError` 路径, 但设计 §3.1 伪代码省略; §3.2 diff 表未注明 | diff 表已补"OLS try/except 保留不变"行 |
| F4 | MINOR | 头部"变更性质…无数值接口变更"措辞歧义 | 已改为"无接口变更" |
| F5 | MINOR | 漏列 `docs/ARCHITECTURE.md` (L17 因果性描述 / L20 版本基线); README 版本位置未精确化 (实测 4 处: L1029/L1032/L1035/L1059); E3 文件数 12 应为 13 | 必改清单补 ARCHITECTURE 行; §5.1 第 8/9 行精确化; E3 改 13 个文件; §5.5 同步 |

### C.3 结论

- 无幻觉级错误: 接口/签名/调用点/字面量位置/测试锚点/ADR 数字全部可回源; TDD 用例经预演实证 (Red 13/9 → Green 22/22)。
- 5 处 MINOR 已全部修复; 实施文档升为 **v1.1**。
- 实施文档与设计 v1.1、调研 v1.2、源码现状、既有测试锚点四方一致, 可进入步骤 7 (验收 checklist)。

---

## 附录 D: 步骤 8 一致性 review 修订 (v1.2)

**方法**: 四方文档 (调研 v1.2 / 设计 v1.1 / 实施 v1.1 / checklist v1.0) 交叉对账 + 源码/测试/版本锚点逐项回源, 详见 [CONSISTENCY_REVIEW_V3.3.7.md](audit/CONSISTENCY_REVIEW_V3.3.7.md) (CRITICAL 0 / MAJOR 0 / MINOR 4, 全部已修复)。

| # | 严重度 | 问题 | 修复 |
|---|--------|------|------|
| M1 | MINOR | §5.2 漏列 test_fix3 **L97** 断言失败消息中的 `'v2.2.4-cache'` 字面量; 漏改导致消息与断言值不一致 + checklist G4-2 grep 判定歧义 | §5.2 补第 3 行 (L97 随 L96 同步) |
| M2 | MINOR | §5.2 row 4 将 **L14** (当前统一目标行) 与 L80/L87 (历史行) 合并为"追加历史"; L14 若只追加不改值则残留旧代号 | 拆为 row 5 (L14 改值) / row 6 (L80/L87 追加) |
| M4 | MINOR | §6.1 步骤映射表第 3 行设计版本写 v1.0 (初稿), 与第 1 行引用最终版 v1.2 的口径不一致 | 改为 v1.2 (含修订链) |

> M3 针对设计文档 §2.1 行号锚点, 在设计文档 v1.2 中修复; checklist 同步修订升 v1.1。

---

**实施文档完成**: 2026-11-04 (v1.2); 步骤 9 TDD 实现与步骤 10 审计 **PASS** 已完成 (2026-11-05, 审计见 `docs/audit/2026-11-04-code-quality-audit.md` v1.2 续篇); 待用户指令后原子提交。
