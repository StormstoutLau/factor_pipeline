# EXECUTION — 面板 HAC / Premium 标准误 (v3.4.12)

> **版本**: v1.0 (2026-11-16)
> **流程**: `docs/WORKFLOW_METHODOLOGY.md` §13.8 步骤 5-6
> **上游**: [RESEARCH v1.0](research/RESEARCH_PREMIUM_HAC_SE.md) / DESIGN v1.0 (private)
> **目标**: 为 `PremiumEstimator` 的点估计补齐 HAC 标准误, 不改现有数值与标签。

## §1 任务范围与目标映射

| 目标 | 实施内容 | 验收 |
|------|---------|------|
| G1 | 新增 `PremiumEstimator.estimate_with_errors(factor, forward_returns, alpha=0.05, max_lag=None)` | E1 |
| G2 | 六个数组: `lambda_hat / lambda_se / lambda_ci_low / lambda_ci_high / beta_t / beta_se` | E1 |
| G3 | 四个标量: `premium_mean / premium_mean_se / premium_mean_ci_low / premium_mean_ci_high` | E2 |
| G4 | 四个元信息: `n_periods / n_valid / hac_lag / alpha` | E3 |
| G5 | `estimate()` 数值与签名不变 (共享 `_smooth_betas`) | E6 |
| G6 | 逐期 OLS SE: `sqrt(σ̂²_ε / Σ(f−f̄)²)` | E4 |
| G7 | λ̂(t) 的 HAC SE: `sqrt(Ω_t · Σw²)`, 局部 Newey-West | E1/E5 |
| G8 | 有效点不足 → 对应 SE=NaN, 不抛异常 | E5 |
| G9 | `diagnose()` / `BreakpointDetector` 零改动 | diff 检查 |

## §2 工程事实 (复核后)

| # | 事实 | 证据 |
|---|------|------|
| F1 | `estimate()` 只返回 `lambda_hat`, 未平滑 β_t 存入 `_beta_raw` | [factor_health/__init__.py L48-L78](../modules/factor_health/__init__.py#L48-L78) |
| F2 | `_cross_sectional_betas` 逐期 OLS 斜率, 不保留残差 | [L80-L108](../modules/factor_health/__init__.py#L80-L108) |
| F3 | `_epanechnikov` 返回归一化权重 | [L110-L115](../modules/factor_health/__init__.py#L110-L115) |
| F4 | 核平滑循环已被 `estimate` 内联, 需抽出才能复用 | [L64-L76](../modules/factor_health/__init__.py#L64-L76) |
| F5 | 模块内 `_newey_west_se` 的 bread 为单变量 OLS, 不可用于加权均值 | [L489-L523](../modules/factor_health/__init__.py#L489-L523) |
| F6 | `norm` 已在模块导入 | [L22](../modules/factor_health/__init__.py#L22) |
| F7 | 现有测试仅覆盖 `estimate()` | [test_layer3_factor_health.py L66-L107](../tests/unit/test_layer3_factor_health.py#L66-L107) |
| F8 | 有效股票 < `min_stocks` 时 β_t=NaN | [L94-L95](../modules/factor_health/__init__.py#L94-L95) |
| F9 | 无外部数据依赖, 合成面板可验证 | 测试夹具 L14-L63 |

## §3 代码变更 (`modules/factor_health/__init__.py`)

### 3.1 抽出 `_smooth_betas` (行为逐位不变)

`estimate()` 的核平滑循环原样搬入新方法, `estimate` 改为调用:

```python
        beta_t = self._cross_sectional_betas(F, R)
        self._beta_raw = beta_t.copy()
        lambda_hat = self._smooth_betas(beta_t)
        return lambda_hat

    def _smooth_betas(self, beta_t: np.ndarray) -> np.ndarray:
        """Epanechnikov kernel smoothing of β_t → λ̂(t)."""
        T = len(beta_t)
        lambda_hat = np.full(T, np.nan)
        h = self.bandwidth
        for t in range(T):
            lo = max(0, t - h)
            hi = min(T, t + h + 1)
            valid = ~np.isnan(beta_t[lo:hi])
            if valid.sum() < 3:
                continue
            dist = np.abs(np.arange(lo, hi) - t) / h
            weights = self._epanechnikov(dist)
            weights = weights[valid]
            lambda_hat[t] = np.average(beta_t[lo:hi][valid], weights=weights)
        return lambda_hat
```

### 3.2 `_cross_sectional_betas` 改为薄包装 + 新增带 SE 版本

`β_t` 的算式与循环顺序逐行保留, 仅追加残差与 `beta_se`:

```python
    def _cross_sectional_betas(self, F: np.ndarray, R: np.ndarray) -> np.ndarray:
        return self._cross_sectional_betas_and_se(F, R)[0]

    def _cross_sectional_betas_and_se(
        self, F: np.ndarray, R: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Per-period cross-sectional OLS slope and its (homoskedastic) SE.

        β_t = Σ(f−f̄)(r−r̄) / Σ(f−f̄)²
        SE(β_t) = sqrt(σ̂²_ε / Σ(f−f̄)²), σ̂²_ε = Σε̂²/(n−2)
        """
        T, N = F.shape
        beta_t = np.full(T, np.nan)
        beta_se = np.full(T, np.nan)

        for t in range(T):
            f = F[t]
            r = R[t]
            valid = ~np.isnan(f) & ~np.isnan(r)
            n_valid = int(valid.sum())
            if n_valid < self.min_stocks:
                continue

            f_valid = f[valid]
            r_valid = r[valid]

            f_demean = f_valid - np.mean(f_valid)
            r_demean = r_valid - np.mean(r_valid)
            var_f = np.dot(f_demean, f_demean)
            if var_f < 1e-12:
                continue

            beta = np.dot(f_demean, r_demean) / var_f
            resid = r_demean - beta * f_demean
            # v3.4.12 复审修正 F2: max(...,1) 守卫 min_stocks<=2 的配置 (精确拟合 → SE=0)
            sigma2 = np.dot(resid, resid) / max(n_valid - 2, 1)

            beta_t[t] = beta
            beta_se[t] = np.sqrt(max(sigma2, 0.0) / var_f)

        return beta_t, beta_se
```

### 3.3 `_hac_long_run_variance` (静态)

```python
    @staticmethod
    def _hac_long_run_variance(x: np.ndarray, max_lag: int) -> float:
        """Newey & West (1987) long-run variance, Bartlett kernel.

        Ω = γ0 + 2 Σ_{l=1}^{q} (1 − l/(q+1)) γ_l, γ_l = (1/n) Σ x̃_t x̃_{t−l}
        """
        x = np.asarray(x, dtype=float)
        x = x[np.isfinite(x)]
        n = len(x)
        if n < 3:
            return np.nan
        q = max(0, min(int(max_lag), n - 1))
        x_demean = x - np.mean(x)
        omega = float(np.dot(x_demean, x_demean) / n)
        for lag in range(1, q + 1):
            weight = 1.0 - lag / (q + 1.0)
            gamma_l = float(np.dot(x_demean[lag:], x_demean[:-lag]) / n)
            omega += 2.0 * weight * gamma_l
        return omega
```

### 3.4 `estimate_with_errors`

```python
    def estimate_with_errors(
        self, factor: pd.DataFrame, forward_returns: pd.DataFrame,
        alpha: float = 0.05, max_lag: Optional[int] = None,
    ) -> Dict:
        """Estimate λ̂(t) with Newey-West HAC standard errors.

        逐期: SE(λ̂_t) ≈ sqrt(Ω_t · Σ_s w_s²), Ω_t 为窗口内残差
        u_s = β_s − λ̂_s 的 HAC 长期方差 (局部常数核近似).
        均值: SE(λ̄) = sqrt(Ω_β / T_valid).
        噪声下限: 窗口或全序列有效点 <3 → 对应 SE=NaN (零方差序列 SE=0).
        """
        common_idx = factor.index.intersection(forward_returns.index)
        common_cols = factor.columns.intersection(forward_returns.columns)
        F = factor.loc[common_idx, common_cols].values
        R = forward_returns.loc[common_idx, common_cols].values

        beta_t, beta_se = self._cross_sectional_betas_and_se(F, R)
        self._beta_raw = beta_t.copy()
        lambda_hat = self._smooth_betas(beta_t)

        T = len(beta_t)
        z = float(norm.ppf(1.0 - alpha / 2.0))

        valid_beta = np.isfinite(beta_t)
        n_valid = int(valid_beta.sum())
        if max_lag is not None:
            q_global = max(1, int(max_lag))
        else:
            q_global = max(1, int(4 * (n_valid / 100) ** (2 / 9)))

        lambda_se = np.full(T, np.nan)
        h = self.bandwidth
        for t in range(T):
            if not np.isfinite(lambda_hat[t]):
                continue
            lo = max(0, t - h)
            hi = min(T, t + h + 1)
            beta_win = beta_t[lo:hi]
            lam_win = lambda_hat[lo:hi]
            valid = np.isfinite(beta_win) & np.isfinite(lam_win)
            n_win = int(valid.sum())
            if n_win < 3:
                continue
            dist = np.abs(np.arange(lo, hi) - t) / h
            weights = self._epanechnikov(dist)[valid]
            # v3.4.12 复审修正 F1: 与 np.average 的实际归一化一致 (设计口径 sum=1).
            # 窗口含 NaN β 时, 未再归一化的 Σw² 会把 SE 低估 ×W_v.
            weights = weights / weights.sum()
            resid = beta_win[valid] - lam_win[valid]
            q_local = q_global if max_lag is not None else max(
                1, int(4 * (n_win / 100) ** (2 / 9))
            )
            omega = self._hac_long_run_variance(resid, q_local)
            if np.isfinite(omega) and omega >= 0:
                lambda_se[t] = np.sqrt(omega * float(np.sum(weights ** 2)))

        if n_valid >= 3:
            beta_valid = beta_t[valid_beta]
            premium_mean = float(np.mean(beta_valid))
            omega_beta = self._hac_long_run_variance(beta_valid, q_global)
            premium_mean_se = (
                float(np.sqrt(omega_beta / n_valid))
                if np.isfinite(omega_beta) and omega_beta >= 0 else np.nan
            )
        else:
            premium_mean = np.nan
            premium_mean_se = np.nan

        return {
            'lambda_hat': lambda_hat,
            'lambda_se': lambda_se,
            'lambda_ci_low': lambda_hat - z * lambda_se,
            'lambda_ci_high': lambda_hat + z * lambda_se,
            'beta_t': beta_t,
            'beta_se': beta_se,
            'premium_mean': premium_mean,
            'premium_mean_se': premium_mean_se,
            'premium_mean_ci_low': premium_mean - z * premium_mean_se,
            'premium_mean_ci_high': premium_mean + z * premium_mean_se,
            'n_periods': T,
            'n_valid': n_valid,
            'hac_lag': int(q_global),
            'alpha': float(alpha),
        }
```

## §4 退化与边界口径

| 场景 | 行为 |
|------|------|
| 无共同日期 | `T=0` → 六个数组为空; 四个标量 NaN; `n_valid=0`, `hac_lag=1` |
| 无共同股票 | `T` 行全 NaN, `n_valid=0` (期数仍计) |
| 全期股票数 < `min_stocks` | `beta_t` 全 NaN → `lambda_hat` 全 NaN; 标量 NaN |
| 窗口有效点 <3 | `lambda_se=NaN` (λ̂ 仍可能有限, 与 `estimate` 门槛一致) |
| 全序列有效 β <3 | `premium_mean/se=NaN` |
| Ω<0 (小样本) | 对应 `SE=NaN`, 不截断为 0 |
| Ω=0 (常数序列) | `SE=0` → CI 退化为点 |
| σ̂²_ε=0 (逐期精确拟合) | `beta_se=0` |
| 输出数组含 NaN | `lambda_ci_*` 自然传播 NaN |

## §5 兼容性

| 维度 | 结论 |
|------|------|
| `estimate()` | 签名不变; 平滑循环原样迁入 `_smooth_betas`, 算式与顺序逐行相同 → 数值逐位不变 (E6) |
| `_beta_raw` | `estimate` / `estimate_with_errors` 均写入, 供 `BreakpointDetector` 使用 |
| `diagnose()` | 不调用新方法, 标签逻辑零改动 |
| 依赖 | 无新增 (`norm` / `Tuple` / `Dict` / `Optional` 已在模块) |
| 性能 | 新增 O(T·N) 残差 + O(T·h·q) HAC, T=500, h=24, q≤5 → 可忽略 |
| 缓存 | 不涉及 |

## §6 测试计划 (E1-E7, `tests/unit/test_layer3_factor_health.py`)

| # | 测试名 | 断言要点 |
|---|--------|---------|
| E1 | `test_returns_arrays_with_ci_consistent` | 六数组长度 T; `lambda_hat` 与 `estimate()` 全等; CI = λ̂ ± z·SE |
| E2 | `test_premium_mean_and_hac_se` | `premium_mean == nanmean(beta_t)`; `se>0`; CI 包含均值 |
| E3 | `test_metadata_and_default_lag` | `n_periods==T`; `n_valid==isfinite(beta_t).sum()`; `hac_lag==max(1,int(4·(n_valid/100)^(2/9)))`; `alpha` |
| E4 | `test_beta_se_matches_cross_sectional_ols` | β 有效期为有限正数; NaN 位置与 `beta_t` 一致; 单期手算 `sqrt(σ̂²/Σ(f−f̄)²)` 一致 |
| E5 | `test_missing_data_degenerate` | 注入 25/50 缺失 → 该期 β=NaN 且 SE=NaN; 全 NaN → 标量 NaN; 无共同列 → `n_periods=0` |
| E6 | `test_estimate_unchanged` | `estimate()` 返回 ndarray; 与 `lambda_hat` 全等; `_beta_raw` 一致 |
| E7 | `test_alpha_sensitivity` | `alpha=0.10` 与 `0.05` 的 CI 宽度比 = `z_0.10/z_0.05` |

## §7 步骤 6 review 记录 (幻觉消除 #2)

| # | 检查项 | 结论 |
|---|--------|------|
| A1 | F1-F9 行号与当前源码逐一核对 | ✅ 见 §2 |
| A2 | 3.1 平滑循环与 `estimate` 原实现 (L64-L76) 逐行一致 | ✅ 仅移位置, 无改写 |
| A3 | 3.2 的 β 算式与原 `_cross_sectional_betas` (L89-L106) 一致 | ✅ 同一算式与顺序, 追加残差/SE |
| A4 | `n_valid − 2` 分母安全 | ✅ `n_valid ≥ min_stocks(30) > 2` |
| A5 | `sqrt(ΩΣw²)` 与 RESEARCH §4.2 一致 | ✅ |
| A6 | 局部阈值 3 与 `estimate` 的 `valid.sum()<3` 一致 | ✅ (DESIGN §3.2 原写 ≥4, 已按此统一修订) |
| A7 | 未复用 `_newey_west_se` | ✅ 新增静态 HAC 长期方差 |
| A8 | 新增依赖 | ✅ 无 (`norm` 已在 L22 导入) |
| A9 | 返回值键名与 G2-G4 一一对应 | ✅ 14 键 |

**review 结论**: PASS, 无幻觉项。

## §8 范围外

- 横截面异方差/聚类稳健 SE;
- t 分布小样本修正;
- 把 CI 接入 `diagnose()` 标签;
- Bai-Perron 多断点。

## §9 独立复审修正与外部验证 (2026-11-16, 提交前)

### 9.1 复审发现与处置

| # | 发现 | 处置 | 验证 |
|---|------|------|------|
| F1 (P2) | `lambda_se` 的 Σw² 用未再归一化权重, 与 `np.average` 实际权重 (sum=1) 不一致 → 窗口含 NaN β 时 SE 低估 ×W_v (数值演示: W_v=0.563, 低估 44%) | SE 循环追加 `weights = weights / weights.sum()` (完整面板除以 1, 零影响) | 新增 E8 |
| F2 (P3) | `min_stocks≤2` 时 `n_valid−2≤0` → σ̂² 除零 → `beta_se` NaN | `/ max(n_valid − 2, 1)` 守卫 (精确拟合 → SE=0) | 新增 E9 |
| F3 (信息) | `max_lag=0` 被静默提升为 1; `hac_lag` 仅报告全局带宽 | 不改 (docstring 已注明) | — |

### 9.2 Stata 18 对拍 ([scripts/verify_hac_stata.py](../scripts/verify_hac_stata.py), StataMP 18)

| 层 | 验证目标 | 结果 |
|----|---------|------|
| L1 | `premium_mean` / `premium_mean_se` vs `newey beta, lag(4)` 截距 | 均值 EXACT (fp 内); SE 比值 = √(200/199) — Stata 默认 n/(n−k) 自由度修正, 本实现为 NW(1987) 渐近形式 (与仓内 `_newey_west_se` 同风格) |
| L2 | `beta_se` (200 期) vs `statsby by(t): regress r f` | EXACT (max dev 7e-8, CSV 往返精度内) |
| L3 | Ω_t vs `newey(u)` 的 SE²×n | 5 个窗口全部恰为 n/(n−1) 因子 — 与 L1 同一约定差; **Bartlett 核 / 1/n 归一化 / 去均值 / 滞后规则逐位一致** |
| L4 | λ̂ SE 语义 (Monte Carlo) | 固定 β 真实路径 (仅抽样误差, CI 的正确口径): premium SE/sd=2.11, λ̂ SE/sd=1.77 → **保守**; 随机 β 路径 (含参数漂移, 总波动口径): 0.90 / 0.81 — 该口径不用于覆盖解释 (见 §9.3) |

**结论**: HAC 引擎 (Bartlett + 1/n 归一化 + 去均值 + 自动滞后) 经 Stata 精确对拍确认;
唯一系统差为 Stata 的 df 修正约定; λ̂ 复合近似有效性由 MC 定量 (见 §9.3 口径自纠)。

### 9.3 Monte Carlo 口径自纠 (2026-11-16)

首版 L4 用「每轮重抽 β 真实路径」的经验 sd 作分母, 得到 SE/sd≈0.83 并记为「≈90% 覆盖」。
复审发现该口径混淆了两类变异:

- **横截面抽样误差** — CI 的目标;
- **参数漂移** — 时变溢价本身, 不是估计误差。

固定 β 真实路径后 (只重抽横截面噪声): `premium_mean` SE/sd=2.11, `lambda_hat` SE/sd=1.77
((N,h) ∈ {50,100}×{12,24,36} 六组扫描 1.47–2.74, 均 >1) → 当前 SE 对抽样误差是**保守**的。
结论: **不修改方差公式**; 修正验证口径与文档表述。保守意味着 CI 偏宽、检出力偏低, 属安全侧偏差。

机制说明: SE 的 `Ω_t` 取自残差 `u_s = β_s − λ̂_s` 的离散度, 除横截面抽样噪声外还包含
β 真实路径被平滑滤掉后的窗口内残余波动 (AR 路径 sd 0.0105 vs 逐期横截面抽样 sd ≈0.0071),
故系统性大于纯抽样长期方差 → 固定 β 口径下 SE/sd>1。若后续把参数漂移计入不确定性
(总波动口径), 则该 SE 偏小 (0.81); 两种口径的取舍属方法学决策, 当前按 CI 针对参数的定义取前者。
