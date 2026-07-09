# -*- coding: utf-8 -*-
"""
ABLATION E2: AblationRunner 核心引擎 (v3.0.0)

实现消融实验框架, 包含:
1. Ledoit-Wolf (2008) HAC Sharpe 差检验 (手工实现, 唯一主路径)
2. Circular Block Bootstrap (Politis & Romano 1992)
3. ρ_step 排序保持性 (Spearman 秩相关)
4. AblationConfig / AblationResult / AblationComparison dataclass
5. AblationRunner: 单次/批量消融实验 + 显著性比较 + BH-FDR 校正

学术依据:
- Ledoit, O. & Wolf, M. (2008). "Robust performance hypothesis testing
  with the Sharpe ratio." J. Empirical Finance 15(5):850-859.
- Politis, D. & Romano, J. (1992). "A Circular Block Resampling Procedure
  for Stationary Data." In Exploring the Limits of Bootstrap, 263-270.
- Benjamini, Y. & Hochberg, Y. (1995). "Controlling the False Discovery
  Rate." JRSS-B 57(1):289-300.

架构: 事后诊断/评估工具, 不侵入 fit/transform 循环.
复用: factor_metrics.py (IC/ICIR/Sharpe) + multiple_testing.py (BH-FDR)
"""

import copy
import time
import logging
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

from scipy import stats as sp_stats
from scipy.stats import spearmanr

# 复用共享模块
from .multiple_testing import apply_bh_fdr
from . import factor_metrics

logger = logging.getLogger(__name__)


# =============================================================================
# E2-T1: Ledoit-Wolf (2008) HAC 标准误 — Sharpe 差检验 (手工实现, 唯一主路径)
# =============================================================================

def ledoit_wolf_hac_test(
    returns_a: np.ndarray,
    returns_b: np.ndarray,
    alpha: float = 0.05,
) -> Tuple[float, float]:
    """Ledoit-Wolf (2008) HAC 检验: H0: SR_a = SR_b

    手工实现 Sharpe 差检验, 基于 delta method + Newey-West HAC.
    这是 Sharpe 差检验的唯一主路径.

    Args:
        returns_a: 策略 a 的收益序列 (T,)
        returns_b: 策略 b 的收益序列 (T,)
        alpha: 显著性水平

    Returns:
        (t_stat, p_value): HAC t 统计量 + 双侧 p 值

    Reference:
        Ledoit, O. & Wolf, M. (2008). "Robust performance hypothesis testing
        with the Sharpe ratio." J. Empirical Finance 15(5):850-859.
    """
    returns_a = np.asarray(returns_a, dtype=float)
    returns_b = np.asarray(returns_b, dtype=float)

    # 对齐长度
    T = min(len(returns_a), len(returns_b))
    returns_a = returns_a[:T]
    returns_b = returns_b[:T]

    # Newey-West 自动带宽
    q = max(1, int(4 * (T / 100) ** (2 / 9)))

    def _sr_gradient_and_cov(r: np.ndarray):
        """计算 SR 梯度 + HAC 协方差矩阵 + SR 值"""
        mu = np.mean(r)
        sigma = np.std(r, ddof=1)
        if sigma < 1e-12:
            return np.array([0.0, 0.0]), np.zeros((2, 2)), 0.0

        # 矩条件 h_t = (r_t - mu, (r_t - mu)^2 - sigma^2)
        h = np.column_stack([
            r - mu,
            (r - mu) ** 2 - sigma ** 2,
        ])  # shape (T, 2)

        # Newey-West HAC 协方差 (Bartlett 核)
        S = h.T @ h / T
        for ell in range(1, q + 1):
            omega = 1 - ell / (q + 1)
            cross = h[ell:].T @ h[:-ell] / T
            S += omega * (cross + cross.T)

        # SR 梯度 (对 (μ, σ²) 参数化)
        # ∂SR/∂μ = 1/σ;  ∂SR/∂σ² = -μ/(2σ³)
        grad = np.array([1.0 / sigma, -mu / (2.0 * sigma ** 3)])

        sr = mu / sigma
        return grad, S, sr

    grad_a, S_a, sr_a = _sr_gradient_and_cov(returns_a)
    grad_b, S_b, sr_b = _sr_gradient_and_cov(returns_b)

    # 协方差 Cov(SR_a, SR_b) = grad_a^T S_ab grad_b
    mu_a, mu_b = np.mean(returns_a), np.mean(returns_b)
    sig_a, sig_b = np.std(returns_a, ddof=1), np.std(returns_b, ddof=1)

    if sig_a < 1e-12 or sig_b < 1e-12:
        return 0.0, 1.0

    h_a = np.column_stack([returns_a - mu_a, (returns_a - mu_a) ** 2 - sig_a ** 2])
    h_b = np.column_stack([returns_b - mu_b, (returns_b - mu_b) ** 2 - sig_b ** 2])

    S_ab = h_a.T @ h_b / T
    for ell in range(1, q + 1):
        omega = 1 - ell / (q + 1)
        S_ab += omega * (
            h_a[ell:].T @ h_b[:-ell] / T
            + h_a[:-ell].T @ h_b[ell:] / T
        )

    # Delta method: Var(SR_hat) = (1/T) * ∇g^T S ∇g
    # (G = -I 对 just-identified GMM, Var(θ_hat) = (1/T) S)
    cov_sr = grad_a @ S_ab @ grad_b / T
    var_a = grad_a @ S_a @ grad_a / T
    var_b = grad_b @ S_b @ grad_b / T

    var_delta = var_a + var_b - 2 * cov_sr
    if var_delta < 1e-15:
        return 0.0, 1.0

    delta_sr = sr_a - sr_b
    t_stat = delta_sr / np.sqrt(var_delta)
    p_value = 2 * (1 - sp_stats.norm.cdf(abs(t_stat)))  # 双侧

    return float(t_stat), float(p_value)


def mean_diff_hac_statsmodels(
    returns_a: np.ndarray,
    returns_b: np.ndarray,
    maxlags: Optional[int] = None,
) -> Tuple[float, float]:
    """均值差 HAC 参考检验: H0: E[r_a - r_b] = 0  (Δμ, 非 ΔSR)

    重要: 此函数检验均值差 Δμ, 不是 Ledoit-Wolf (2008) 的 Sharpe 差 ΔSR.
    Sharpe 差检验必须用 ledoit_wolf_hac_test (手工实现), 两者不可互换.
    statsmodels 路径仅作为均值差参考检验 (reference test).

    Args:
        returns_a: 策略 a 的收益序列 (T,)
        returns_b: 策略 b 的收益序列 (T,)
        maxlags: HAC 最大滞后阶数 (None = 自动)

    Returns:
        (t_stat, p_value): 均值差 HAC t 统计量 + p 值
    """
    from statsmodels.regression.linear_model import OLS

    returns_a = np.asarray(returns_a, dtype=float)
    returns_b = np.asarray(returns_b, dtype=float)
    T = min(len(returns_a), len(returns_b))
    returns_a = returns_a[:T]
    returns_b = returns_b[:T]

    if maxlags is None:
        maxlags = max(1, int(4 * (T / 100) ** (2 / 9)))

    diff = returns_a - returns_b
    X = np.ones((T, 1))  # 仅截距
    model = OLS(diff, X).fit(cov_type='HAC', cov_kwds={'maxlags': maxlags})
    t_stat = model.tvalues[0]
    p_value = model.pvalues[0]
    return float(t_stat), float(p_value)


# =============================================================================
# E2-T2: Circular Block Bootstrap (Politis & Romano 1992)
# =============================================================================

def circular_block_bootstrap(
    series_a: np.ndarray,
    series_b: np.ndarray,
    statistic: str = 'mean',
    n_bootstrap: int = 1000,
    block_size: Optional[int] = None,
    seed: Optional[int] = None,
) -> Tuple[float, np.ndarray]:
    """Circular block bootstrap for Δstat(a) - Δstat(b) (Politis & Romano 1992)

    固定块长 circular block bootstrap, 保留时序依赖.
    块大小默认 max(1, int(T**(1/3))) (简化版 Politis & White 2004).

    双侧 p 值 (中心化版本, Hall & Wilson 1991):
        p = fraction(|Δ* - mean(Δ*)| ≥ |Δ_obs|)
    其中 Δ* 为 bootstrap 重采样差值分布, Δ_obs 为观测差值.
    中心化版本比 naive p = fraction(|Δ*| ≥ |Δ_obs|) 更稳健:
    bootstrap 分布中心可能偏离 0, 中心化消除此偏倚.

    Args:
        series_a: 策略 a 的 IC/收益序列 (T,)
        series_b: 策略 b 的 IC/收益序列 (T,)
        statistic: 'mean' (ΔIC) 或 'sharpe' (ΔSharpe)
        n_bootstrap: bootstrap 次数 (默认 1000)
        block_size: 块大小 (None = auto, T^(1/3))
        seed: 随机种子 (None = 不固定)

    Returns:
        (p_value, bootstrap_stats): 双侧 p 值 + bootstrap 差值数组
    """
    series_a = np.asarray(series_a, dtype=float)
    series_b = np.asarray(series_b, dtype=float)
    T = min(len(series_a), len(series_b))
    series_a = series_a[:T]
    series_b = series_b[:T]

    if block_size is None:
        block_size = max(1, int(T ** (1 / 3)))

    rng = np.random.default_rng(seed)

    def _stat(s: np.ndarray) -> float:
        s_clean = s[~np.isnan(s)]
        if len(s_clean) < 3:
            return np.nan
        if statistic == 'sharpe':
            std = np.std(s_clean, ddof=1)
            return np.mean(s_clean) / std if std > 1e-12 else 0.0
        return np.mean(s_clean)

    # 观测差值
    delta_obs = _stat(series_a) - _stat(series_b)

    # Circular block bootstrap
    n_blocks = int(np.ceil(T / block_size))
    deltas_boot = np.empty(n_bootstrap)
    deltas_boot.fill(np.nan)

    for b in range(n_bootstrap):
        # 随机起始点, 环形采样
        starts = rng.integers(0, T, size=n_blocks)
        idx = np.concatenate([
            (np.arange(block_size) + s) % T for s in starts
        ])[:T]

        boot_a = series_a[idx]
        boot_b = series_b[idx]
        deltas_boot[b] = _stat(boot_a) - _stat(boot_b)

    # 过滤 NaN
    valid_mask = ~np.isnan(deltas_boot)
    deltas_boot = deltas_boot[valid_mask]

    if len(deltas_boot) < 10:
        return 1.0, deltas_boot

    # p 值: fraction(|delta_boot - mean(delta_boot)| >= |delta_obs|)
    p_value = float(np.mean(
        np.abs(deltas_boot - np.mean(deltas_boot)) >= np.abs(delta_obs)
    ))

    return p_value, deltas_boot


# =============================================================================
# E2-T3: ρ_step 排序保持性 (Spearman 秩相关)
# =============================================================================

def compute_rho_step(
    factor_before: pd.DataFrame,
    factor_after: pd.DataFrame,
) -> float:
    """计算单步骤的排序保持性 ρ_step

    对每列 (截面), 计算 Spearman(before, after), 然后时间平均.

    Args:
        factor_before: 步骤前的因子值 (n_entities, n_periods)
        factor_after: 步骤后的因子值 (n_entities, n_periods)

    Returns:
        ρ_step: 时间平均的 Spearman 秩相关系数 [-1, 1]
    """
    # 对齐
    common = factor_before.index.intersection(factor_after.index)
    cols = factor_before.columns.intersection(factor_after.columns)
    fb = factor_before.loc[common, cols]
    fa = factor_after.loc[common, cols]

    rhos = []
    for col in cols:
        b = fb[col].dropna()
        a = fa.loc[b.index, col].dropna()
        common_idx = a.index.intersection(b.index)
        if len(common_idx) < 3:
            continue
        rho, _ = spearmanr(b.loc[common_idx], a.loc[common_idx])
        if not np.isnan(rho):
            rhos.append(rho)

    return float(np.mean(rhos)) if rhos else float('nan')


# =============================================================================
# E2-T4: Dataclass 定义
# =============================================================================

@dataclass
class AblationConfig:
    """消融实验配置 — 定义一次消融实验的全部开关"""

    # ── 标识 ──
    name: str = "baseline"
    layer: str = "baseline"             # 'L1' | 'L2' | 'L3' | 'L4' | 'baseline'

    # ── L1 组件开关 ──
    module_enabled: Optional[Dict[str, bool]] = None
    # None = 全启用; {'imputer': False, ...} = 指定关闭

    # ── L2 路由模式 ──
    routing_mode: str = 'full'          # 'static' | 'dynamic' | 'mixed' | 'random' | 'full'
    random_seed: Optional[int] = None   # routing_mode='random' 时的 seed

    # ── L3 参数覆盖 ──
    cusum_k: Optional[float] = None
    cusum_h: Optional[float] = None
    correction_method: Optional[str] = None
    winsorize_ratio: Optional[float] = None
    ewma_halflife: Optional[int] = None
    ewma_alpha: Optional[float] = None
    routing_threshold_scale: Optional[float] = None

    # ── L4 前置处理 OAT ──
    outlier_method: Optional[str] = None
    scaler_method: Optional[str] = None
    missing_method: Optional[str] = None
    neutralization: Optional[str] = None
    time_align: Optional[str] = None
    data_window: Optional[Tuple[str, str]] = None

    # ── L1 ortho 开关 ──
    ortho_enabled: Optional[bool] = None

    # ── Baseline ──
    baseline_level: Optional[str] = None    # 'B0' | 'B1' | 'B2' | 'B3'

    # ── M5 修正: 平凡比较标记 ──
    # True = 此配置与 baseline 相同 (默认选项), 比较结果 trivial, 不参与 BH-FDR
    _is_trivial: bool = False


@dataclass
class AblationResult:
    """单次消融实验结果"""
    config: AblationConfig
    metrics: Dict[str, float]
    ic_series: np.ndarray
    ls_return_series: np.ndarray
    rho_step: Dict[str, float]
    ortho_diagnostics: Dict[str, float]
    n_factors: int
    n_periods: int
    runtime_sec: float


@dataclass
class AblationComparison:
    """两个 AblationResult 的显著性比较"""
    experiment: str
    reference: str
    delta_ic: float
    delta_sharpe: float
    t_stat_hac: float
    p_value_hac: float
    bootstrap_ci_low: float
    bootstrap_ci_high: float
    p_value_bootstrap: float
    is_significant: bool
    sharpe_bootstrap_ci_low: float = float('nan')
    sharpe_bootstrap_ci_high: float = float('nan')
    p_value_bootstrap_sharpe: float = float('nan')
    # M5 修正: trivial 标记从 experiment config 传播而来, 不参与 BH-FDR
    _is_trivial: bool = False


# =============================================================================
# E2-T5 ~ E2-T8: AblationRunner 核心引擎
# =============================================================================

class AblationRunner:
    """消融实验运行器 — 独立于 fit/transform 循环

    架构: 与 CUSUMDriftMonitor 一致, 作为事后诊断/评估工具, 不侵入管线.
    复用: factor_metrics.py (IC/ICIR/Sharpe) + multiple_testing.py (BH-FDR)

    Usage:
        runner = AblationRunner(base_config=PipelineV2Config())
        results = runner.run_l1(factor_data, fwd_returns, industry_data)
        comparison = runner.compare(results[0], reference=results[-1])
    """

    # 5 个可消融模块
    L1_MODULES = ['imputer', 'winsorizer', 'scaler', 'neutralizer', 'orthogonalizer']

    # ρ_step 参照值
    RHO_REF = {
        'identity': 1.0, 'imputer': 0.99, 'winsorizer': 0.95,
        'scaler': 0.99, 'neutralizer': 0.85, 'orthogonalizer': 0.70,
    }

    def __init__(
        self,
        base_config: Any,
        alpha: float = 0.05,
        n_bootstrap: int = 1000,
        block_size: Optional[int] = None,
        n_jobs: int = 1,
        random_seed: int = 42,
    ):
        self.base_config = base_config
        self.alpha = alpha
        self.n_bootstrap = n_bootstrap
        self.block_size = block_size
        self.n_jobs = n_jobs
        self.random_seed = random_seed
        self._results: List[AblationResult] = []

    # -------------------------------------------------------------------------
    # run_single: 单次消融实验
    # -------------------------------------------------------------------------

    def run_single(
        self,
        config: AblationConfig,
        factor_data: Dict[str, pd.DataFrame],
        fwd_returns: pd.DataFrame,
        industry_data: Optional[pd.Series] = None,
    ) -> AblationResult:
        """运行单次消融实验

        流程:
        1. 从 base_config 构建消融后的 config (覆盖 module_enabled/routing/参数)
        2. B0: 无管线, dropna; B3: 完整管线; 其他: 按配置运行
        3. 计算指标 (IC/ICIR/Sharpe/turnover/drawdown/ρ_step/ortho)
        4. 返回 AblationResult
        """
        start_time = time.time()

        baseline_level = config.baseline_level

        if baseline_level == 'B0':
            # B0: 原始因子 + dropna (最小处理, 无管线)
            processed_data = {name: df.dropna() for name, df in factor_data.items()}
            rho_step = {step: 1.0 for step in self.L1_MODULES}
            ortho_diagnostics = {'condition_number': float('nan'), 'vrr_mean': float('nan')}
        elif baseline_level == 'B1':
            # B1: 仅 imputer
            processed_data, rho_step, ortho_diagnostics = self._run_pipeline(
                config, factor_data, fwd_returns, industry_data,
                module_override={'imputer': True, 'winsorizer': False,
                                 'scaler': False, 'neutralizer': False},
                ortho_enabled=False,
            )
        elif baseline_level == 'B2':
            # B2: imputer + Z-score (scaler)
            processed_data, rho_step, ortho_diagnostics = self._run_pipeline(
                config, factor_data, fwd_returns, industry_data,
                module_override={'imputer': True, 'winsorizer': False,
                                 'scaler': True, 'neutralizer': False},
                ortho_enabled=False,
            )
        else:
            # B3 / 默认: 完整管线
            processed_data, rho_step, ortho_diagnostics = self._run_pipeline(
                config, factor_data, fwd_returns, industry_data,
            )

        # 计算指标
        metrics, ic_series, ls_returns = self._compute_metrics(
            processed_data, fwd_returns,
        )

        runtime = time.time() - start_time

        # 推断 n_periods
        n_periods = 0
        for df in factor_data.values():
            n_periods = max(n_periods, len(df))
            break

        result = AblationResult(
            config=config,
            metrics=metrics,
            ic_series=ic_series,
            ls_return_series=ls_returns,
            rho_step=rho_step,
            ortho_diagnostics=ortho_diagnostics,
            n_factors=len(processed_data),
            n_periods=n_periods,
            runtime_sec=runtime,
        )
        self._results.append(result)
        return result

    def _run_pipeline(
        self,
        config: AblationConfig,
        factor_data: Dict[str, pd.DataFrame],
        fwd_returns: pd.DataFrame,
        industry_data: Optional[pd.Series] = None,
        module_override: Optional[Dict[str, bool]] = None,
        ortho_enabled: Optional[bool] = None,
    ) -> Tuple[Dict[str, pd.DataFrame], Dict[str, float], Dict[str, float]]:
        """运行 FactorProcessingPipelineV2 并收集诊断

        Returns:
            (processed_data, rho_step, ortho_diagnostics)
        """
        from factor_pipeline.pipelines_v2 import (
            PipelineV2Config, FactorProcessingPipelineV2,
        )

        # 构建修改后的 config
        modified_config = copy.deepcopy(self.base_config)

        # 应用 module_enabled
        module_enabled = config.module_enabled or module_override
        if module_enabled is not None:
            modified_config.module_enabled = module_enabled

        # 应用 ortho_enabled
        effective_ortho = ortho_enabled if ortho_enabled is not None else config.ortho_enabled
        if effective_ortho is False and modified_config.orthogonalization is not None:
            try:
                modified_config.orthogonalization.enabled = False
            except (AttributeError, TypeError):
                pass  # Pydantic model 可能需要不同处理

        # P0-3/P0-4 (spec §6.4/§5.4): 实例化管线前注入 L3/L4 参数
        # (config 必须在 pipeline 构造前就绪, 因 Adapter 在 __init__ 读 config)
        self._apply_l3_overrides(modified_config, config)
        self._apply_l4_overrides(modified_config, config)

        # 运行管线
        pipeline = FactorProcessingPipelineV2(modified_config)
        pipeline.fit(factor_data, industry_data=industry_data)

        # P0-2 (spec §2.5/§4.3): fit 后、transform 前覆盖路由分类
        # (分类在 fit 阶段确定, 故必须在 fit 后覆盖)
        if config.routing_mode != 'full':
            self._override_routing(pipeline, config.routing_mode, config.random_seed)

        processed_data = pipeline.transform(factor_data)

        # 收集 ρ_step
        rho_step = self._collect_rho_steps(pipeline, factor_data, processed_data)

        # 收集正交化诊断
        ortho_diagnostics = self._collect_ortho_diagnostics(pipeline)

        return processed_data, rho_step, ortho_diagnostics

    # -------------------------------------------------------------------------
    # P0-2/P0-3/P0-4: 参数注入方法 (audit 修复)
    # -------------------------------------------------------------------------

    def _override_routing(
        self,
        pipeline: Any,
        routing_mode: str,
        random_seed: Optional[int] = None,
    ) -> None:
        """P0-2: fit 后覆盖 factor_classifications, 强制单一类型或随机路由.

        Spec §2.5/§4.3. 在 pipeline.fit() 后、pipeline.transform() 前调用,
        因为分类结果在 fit 阶段由指纹驱动产生, 必须在 fit 后才能覆盖.

        Args:
            pipeline: FactorProcessingPipelineV2 实例 (已 fit)
            routing_mode: 'static' | 'dynamic' | 'mixed' | 'random' | 'full'
            random_seed: routing_mode='random' 时的种子 (None → 42)

        Behavior:
            - 'full': 不修改 (保留指纹驱动路由)
            - 'static'/'dynamic'/'mixed': 所有因子分类强制为单一类型,
              is_hard=True, primary_prob=1.0
            - 'random': 用 random_seed 固定 RNG, 对每个因子随机分配
              STATIC/DYNAMIC/MIXED (E2 修正: 控制组, 排除路由 vs 不路由混淆)
        """
        if routing_mode == 'full':
            return  # 不修改, 保留指纹驱动路由

        from factor_pipeline.modules.factor_fingerprint import (
            FactorType, ClassificationResult,
        )

        factor_names = list(pipeline.factor_classifications.keys())

        if routing_mode in ('static', 'dynamic', 'mixed'):
            force_type = FactorType[routing_mode.upper()]
            for name in factor_names:
                pipeline.factor_classifications[name] = ClassificationResult(
                    primary_type=force_type,
                    primary_prob=1.0,
                    secondary_type=None,
                    secondary_prob=0.0,
                    is_hard=True,
                )
        elif routing_mode == 'random':
            rng = np.random.default_rng(
                random_seed if random_seed is not None else 42
            )
            types = [FactorType.STATIC, FactorType.DYNAMIC, FactorType.MIXED]
            for name in factor_names:
                idx = int(rng.integers(0, len(types)))
                pipeline.factor_classifications[name] = ClassificationResult(
                    primary_type=types[idx],
                    primary_prob=1.0,
                    secondary_type=None,
                    secondary_prob=0.0,
                    is_hard=True,
                )

    def _apply_l3_overrides(
        self,
        modified_config: Any,
        ablation_config: AblationConfig,
    ) -> None:
        """P0-3: L3 参数覆盖, 注入 modified_config (spec §6.4).

        在实例化 pipeline 前调用 (config 必须在构造前就绪).

        字段映射 (PipelineV2Config 实际字段):
            直接字段 (PipelineV2Config 已有):
              - cusum_k → modified_config.cusum_k (并 enable_cusum_drift_monitor=True)
              - cusum_h → modified_config.cusum_h (并 enable_cusum_drift_monitor=True)
            间接字段 (PipelineV2Config 无直接字段, 使用 _l3_* 前缀属性,
                      由下游模块按需读取):
              - ewma_halflife → modified_config._l3_ewma_halflife
              - ewma_alpha → modified_config._l3_ewma_alpha
              - routing_threshold_scale → modified_config._l3_routing_threshold_scale
              - winsorize_ratio → modified_config._l3_winsorize_ratio
              - correction_method → modified_config._l3_correction_method

        None 值跳过 (不覆盖).
        """
        # 直接字段: cusum_k / cusum_h (PipelineV2Config 已有, spec §6.4)
        if ablation_config.cusum_k is not None:
            modified_config.cusum_k = ablation_config.cusum_k
            modified_config.enable_cusum_drift_monitor = True
        if ablation_config.cusum_h is not None:
            modified_config.cusum_h = ablation_config.cusum_h
            modified_config.enable_cusum_drift_monitor = True

        # 间接字段: PipelineV2Config 无直接字段, 使用 _l3_* 前缀属性 (spec §6.4)
        if ablation_config.ewma_halflife is not None:
            modified_config._l3_ewma_halflife = ablation_config.ewma_halflife
        if ablation_config.ewma_alpha is not None:
            modified_config._l3_ewma_alpha = ablation_config.ewma_alpha
        if ablation_config.routing_threshold_scale is not None:
            modified_config._l3_routing_threshold_scale = (
                ablation_config.routing_threshold_scale
            )
        if ablation_config.winsorize_ratio is not None:
            modified_config._l3_winsorize_ratio = ablation_config.winsorize_ratio
        if ablation_config.correction_method is not None:
            modified_config._l3_correction_method = ablation_config.correction_method

    def _apply_l4_overrides(
        self,
        modified_config: Any,
        ablation_config: AblationConfig,
    ) -> None:
        """P0-4: L4 OAT 参数覆盖, 注入 modified_config (spec §5.4).

        在实例化 pipeline 前调用.

        字段映射 (PipelineV2Config 实际字段):
            间接字段 (PipelineV2Config 无直接字段):
              - outlier_method → modified_config._l4_outlier_method
              - scaler_method → modified_config._l4_scaler_method
              - missing_method:
                  'drop' → module_enabled['imputer']=False (关闭 imputer, 保留 NaN)
                  'median'/'knn' → modified_config._l4_imputer_strategy
              - neutralization:
                  'none' → module_enabled['neutralizer']=False (关闭中性化)
                  其他 → modified_config._l4_neutralization
              - time_align → modified_config._l4_time_align
              - data_window → modified_config._l4_data_window

        None 值跳过 (不覆盖).
        """
        if ablation_config.outlier_method is not None:
            modified_config._l4_outlier_method = ablation_config.outlier_method
        if ablation_config.scaler_method is not None:
            modified_config._l4_scaler_method = ablation_config.scaler_method

        if ablation_config.missing_method is not None:
            if ablation_config.missing_method == 'drop':
                # spec §5.4: 'drop' → 关闭 imputer (保留 NaN, IC 计算时 dropna)
                if modified_config.module_enabled is None:
                    modified_config.module_enabled = {}
                modified_config.module_enabled['imputer'] = False
            else:
                # 'median' / 'knn' → 设置 imputer 策略
                modified_config._l4_imputer_strategy = (
                    ablation_config.missing_method
                )

        if ablation_config.neutralization is not None:
            if ablation_config.neutralization == 'none':
                # spec §5.4: 'none' → 关闭 neutralizer
                if modified_config.module_enabled is None:
                    modified_config.module_enabled = {}
                modified_config.module_enabled['neutralizer'] = False
            else:
                modified_config._l4_neutralization = ablation_config.neutralization

        if ablation_config.time_align is not None:
            modified_config._l4_time_align = ablation_config.time_align
        if ablation_config.data_window is not None:
            modified_config._l4_data_window = ablation_config.data_window

    def _collect_rho_steps(
        self,
        pipeline: Any,
        original_data: Dict[str, pd.DataFrame],
        processed_data: Dict[str, pd.DataFrame],
    ) -> Dict[str, float]:
        """收集 5 个步骤的 ρ_step 排序保持性"""
        rho_step = {}

        # 尝试从管线的中间数据获取
        intermediate = {}
        if hasattr(pipeline, 'factor_pipelines'):
            for name, pipes in pipeline.factor_pipelines.items():
                for pipe_type, pipe in pipes.items():
                    if hasattr(pipe, 'get_intermediate_data'):
                        try:
                            intermediate[name] = pipe.get_intermediate_data()
                            break
                        except Exception:
                            pass

        # 5 个步骤
        for step in self.L1_MODULES:
            try:
                if step == 'imputer':
                    # imputer 前 = original, 后 = intermediate['imputation'] or processed
                    before = next(iter(original_data.values()))
                    after = self._get_intermediate(intermediate, 'imputation', before)
                elif step == 'winsorizer':
                    before = self._get_intermediate(intermediate, 'imputation', None)
                    after = self._get_intermediate(intermediate, 'outlier', before)
                elif step == 'scaler':
                    before = self._get_intermediate(intermediate, 'outlier', None)
                    after = self._get_intermediate(intermediate, 'standardization', before)
                elif step == 'neutralizer':
                    before = self._get_intermediate(intermediate, 'standardization', None)
                    after = self._get_intermediate(intermediate, 'neutralization', before)
                elif step == 'orthogonalizer':
                    # P1-8 修复: before = 正交化前 (neutralization 输出),
                    # after = 正交化后 (processed_data). 原 bug: before==after
                    # 都用 processed_data, 导致 Spearman 恒为 1.0.
                    before = self._get_intermediate(intermediate, 'neutralization', None)
                    after = next(iter(processed_data.values()))
                else:
                    rho_step[step] = 1.0
                    continue

                if before is not None and after is not None:
                    rho = compute_rho_step(before, after)
                    rho_step[step] = rho if not np.isnan(rho) else 1.0
                else:
                    rho_step[step] = 1.0
            except Exception:
                rho_step[step] = 1.0

        return rho_step

    def _get_intermediate(
        self,
        intermediate: Dict[str, Dict],
        key: str,
        fallback: Any,
    ) -> Any:
        """从中间数据中获取指定步骤的数据"""
        for name, data in intermediate.items():
            if key in data:
                return data[key]
        return fallback

    def _collect_ortho_diagnostics(self, pipeline: Any) -> Dict[str, float]:
        """收集正交化诊断: condition_number + VRR

        复用 OrthogonalizerAdapter.get_diagnostics() (v2.5.0 ADR-020)
        """
        for hook in getattr(pipeline, 'post_transform_hooks', []):
            if hasattr(hook, 'get_diagnostics'):
                diag = hook.get_diagnostics()
                if 'F_stacked' in diag and 'T_stacked' in diag:
                    F = diag['F_stacked']
                    T = diag['T_stacked']
                    # condition_number: Gram 矩阵的条件数
                    try:
                        gram = F.T @ F / max(F.shape[0], 1)
                        cond = float(np.linalg.cond(gram))
                    except (np.linalg.LinAlgError, ValueError):
                        cond = float('nan')
                    # VRR: Variance Retention Ratio
                    try:
                        var_f = np.var(F, axis=0, ddof=1)
                        var_t = np.var(T, axis=0, ddof=1)
                        mask = var_f > 1e-12
                        vrr = float(np.mean(var_t[mask] / var_f[mask])) if mask.any() else float('nan')
                    except (ValueError, IndexError):
                        vrr = float('nan')
                    return {'condition_number': cond, 'vrr_mean': vrr}

        return {'condition_number': float('nan'), 'vrr_mean': float('nan')}

    def _compute_metrics(
        self,
        processed_data: Dict[str, pd.DataFrame],
        fwd_returns: pd.DataFrame,
    ) -> Tuple[Dict[str, float], np.ndarray, np.ndarray]:
        """计算聚合指标 (复用 factor_metrics.py)

        Returns:
            (metrics, ic_series, ls_return_series)
        """
        all_ic_series = []
        all_ls_returns = []

        for name, factor_df in processed_data.items():
            # 对齐 fwd_returns 与 factor_df
            common_dates = factor_df.index.intersection(fwd_returns.index)
            common_stocks = factor_df.columns.intersection(fwd_returns.columns)
            if len(common_dates) < 3 or len(common_stocks) < 3:
                continue

            f_aligned = factor_df.loc[common_dates, common_stocks]
            r_aligned = fwd_returns.loc[common_dates, common_stocks]

            # factor_metrics 期望 (n_stocks, n_periods)
            factor_arr = f_aligned.values.T  # (n_stocks, n_periods)
            returns_arr = r_aligned.values.T

            # IC 序列
            ic_series = factor_metrics.compute_ic_series(
                factor_arr, returns_arr, method='rank',
            )
            all_ic_series.append(ic_series)

            # 多空收益
            ls_returns = factor_metrics.compute_long_short_returns(
                factor_arr, returns_arr,
            )
            all_ls_returns.append(ls_returns)

        if not all_ic_series:
            # 无有效数据
            nan_metrics = {
                'ic_mean': float('nan'), 'ic_std': float('nan'),
                'icir': float('nan'), 'sharpe_ls': float('nan'),
                'sharpe_lo': float('nan'), 'turnover_mean': float('nan'),
                'max_drawdown': float('nan'), 'hit_rate': float('nan'),
            }
            return nan_metrics, np.array([]), np.array([])

        # 对齐长度并平均
        min_len_ic = min(len(s) for s in all_ic_series)
        ic_stack = np.column_stack([s[:min_len_ic] for s in all_ic_series])
        avg_ic = np.nanmean(ic_stack, axis=1)

        min_len_ls = min(len(s) for s in all_ls_returns)
        ls_stack = np.column_stack([s[:min_len_ls] for s in all_ls_returns])
        avg_ls = np.nanmean(ls_stack, axis=1)

        # 计算聚合指标
        clean_ic = avg_ic[~np.isnan(avg_ic)]
        clean_ls = avg_ls[~np.isnan(avg_ls)]

        ic_mean = float(np.mean(clean_ic)) if len(clean_ic) > 0 else float('nan')
        ic_std = float(np.std(clean_ic, ddof=1)) if len(clean_ic) > 1 else float('nan')
        icir = factor_metrics.compute_icir(avg_ic)
        sharpe_ls = factor_metrics.compute_spread(avg_ls)
        hit_rate = factor_metrics.compute_hit_rate(avg_ic)

        # max_drawdown (多空收益的累积收益最大回撤)
        if len(clean_ls) > 0:
            cum = np.cumsum(clean_ls)
            running_max = np.maximum.accumulate(cum)
            drawdown = cum - running_max
            max_dd = float(np.min(drawdown)) if len(drawdown) > 0 else float('nan')
        else:
            max_dd = float('nan')

        metrics = {
            'ic_mean': ic_mean,
            'ic_std': ic_std,
            'icir': icir,
            'sharpe_ls': sharpe_ls,
            'sharpe_lo': float('nan'),  # long-only Sharpe (未计算)
            'turnover_mean': float('nan'),  # 未计算 (需持仓数据)
            'max_drawdown': max_dd,
            'hit_rate': hit_rate,
        }

        return metrics, avg_ic, avg_ls

    # -------------------------------------------------------------------------
    # 批量运行方法
    # -------------------------------------------------------------------------

    def run_l1(
        self,
        factor_data: Dict[str, pd.DataFrame],
        fwd_returns: pd.DataFrame,
        industry_data: Optional[pd.Series] = None,
        b3_full_result: Optional[AblationResult] = None,
    ) -> List[AblationResult]:
        """L1 组件消融: 5 模块逐个关闭 + B3 完整管线参照

        返回 6 个 AblationResult:
        - B3_full (全部启用, 参照; 若 b3_full_result 提供, 引用复用)
        - L1_imputer_off
        - L1_winsorizer_off
        - L1_scaler_off
        - L1_neutralizer_off
        - L1_orthogonalizer_off (M3 修正: 走 ortho_enabled, 不走 module_enabled)
        """
        results = []

        # B3_full 参照
        if b3_full_result is not None:
            results.append(b3_full_result)
        else:
            b3_config = AblationConfig(name='B3_full', layer='baseline', baseline_level='B3')
            results.append(self.run_single(b3_config, factor_data, fwd_returns, industry_data))

        # 4 个模块逐个关闭 (走 module_enabled)
        # M3 修正: orthogonalizer 不走 module_enabled, 单独通过 ortho_enabled 控制
        for module in ['imputer', 'winsorizer', 'scaler', 'neutralizer']:
            config = AblationConfig(
                name=f'L1_{module}_off',
                layer='L1',
                module_enabled={module: False},
                baseline_level='B3',  # 基于 B3 管线
            )
            results.append(self.run_single(config, factor_data, fwd_returns, industry_data))

        # ortho 关闭: M3 修正 — OrthogonalizerAdapter 读 OrthogonalizationConfig.enabled,
        # 不走 module_enabled['orthogonalizer'] (adapters.py:796, ADR-020).
        # 通过 ortho_enabled=False 在 run_single/_run_pipeline 中关闭正交化.
        ortho_config = AblationConfig(
            name='L1_orthogonalizer_off',
            layer='L1',
            ortho_enabled=False,
            baseline_level='B3',
        )
        results.append(self.run_single(ortho_config, factor_data, fwd_returns, industry_data))

        return results

    def run_l2(
        self,
        factor_data: Dict[str, pd.DataFrame],
        fwd_returns: pd.DataFrame,
        industry_data: Optional[pd.Series] = None,
        b3_full_result: Optional[AblationResult] = None,
    ) -> List[AblationResult]:
        """L2 路由消融: 5 配置

        返回 5 个 AblationResult:
        - L2_all_static (全 static 管道)
        - L2_all_dynamic (全 dynamic 管道)
        - L2_all_mixed (全 mixed 管道)
        - L2_random_routing (随机路由, seed=42)
        - L2_full_routing (完整 5 叉路由, 参照; M6 修正: 若 b3_full_result
          提供, 引用复用, 不重复 run_single)
        """
        results = []
        routing_configs = [
            ('L2_all_static', 'static'),
            ('L2_all_dynamic', 'dynamic'),
            ('L2_all_mixed', 'mixed'),
            ('L2_random_routing', 'random'),
        ]

        for name, mode in routing_configs:
            config = AblationConfig(
                name=name,
                layer='L2',
                routing_mode=mode,
                random_seed=42 if mode == 'random' else None,
                baseline_level='B3',
            )
            results.append(self.run_single(config, factor_data, fwd_returns, industry_data))

        # L2_full_routing (参照): M6 修正 — 引用复用 B3_full, 不重复 run_single
        # (默认配置 = 完整路由, 与 B3_full 运行层面等价, 见 §7.2 M6 修正)
        if b3_full_result is not None:
            results.append(b3_full_result)
        else:
            full_config = AblationConfig(
                name='L2_full_routing',
                layer='L2',
                routing_mode='full',
                baseline_level='B3',
            )
            results.append(self.run_single(full_config, factor_data, fwd_returns, industry_data))

        return results

    def run_baselines(
        self,
        factor_data: Dict[str, pd.DataFrame],
        fwd_returns: pd.DataFrame,
        industry_data: Optional[pd.Series] = None,
    ) -> List[AblationResult]:
        """B0-B3 Baseline 阶梯

        - B0: 原始因子 + dropna (最小处理)
        - B1: 仅 imputer
        - B2: imputer + Z-score
        - B3: 完整管线 (默认配置, 参照)
        """
        results = []
        for level in ['B0', 'B1', 'B2', 'B3']:
            config = AblationConfig(
                name=f'{level}_baseline',
                layer='baseline',
                baseline_level=level,
            )
            results.append(self.run_single(config, factor_data, fwd_returns, industry_data))
        return results

    def run_l4_oat(
        self,
        factor_data: Dict[str, pd.DataFrame],
        fwd_returns: pd.DataFrame,
        industry_data: Optional[pd.Series] = None,
        b3_full_result: Optional[AblationResult] = None,
    ) -> List[AblationResult]:
        """L4 前置处理 OAT 单维消融: 6 自由度

        每个自由度单独消融, 其余固定为默认.
        返回 ≥20 个 AblationResult (6 DOF × 3-4 选项 + 1 baseline)
        """
        results = []

        # B3_full 参照
        if b3_full_result is not None:
            results.append(b3_full_result)
        else:
            b3_config = AblationConfig(name='B3_full', layer='baseline', baseline_level='B3')
            results.append(self.run_single(b3_config, factor_data, fwd_returns, industry_data))

        # 6 个自由度的 OAT 选项
        oat_specs = [
            ('outlier_method', [
                '3sigma', 'mad', 'winsorize_1pct', 'winsorize_5pct',
            ]),
            ('scaler_method', [
                'zscore', 'rank', 'minmax',
            ]),
            ('missing_method', [
                'drop', 'median', 'knn',
            ]),
            ('neutralization', [
                'none', 'industry', 'industry+mktcap',
            ]),
            ('time_align', [
                't+1', 't+5', 'week_ahead',
            ]),
            ('data_window', [
                ('2010-01-01', '2015-12-31'),
                ('2015-01-01', '2020-12-31'),
                ('2010-01-01', '2020-12-31'),
            ]),
        ]

        # M5 修正: 各自由度的默认选项 (与 baseline 相同, 标记为 trivial)
        # spec §5.2: 默认选项构成平凡比较, 不参与 BH-FDR 校正
        defaults = {
            'outlier_method': 'mad',
            'scaler_method': 'zscore',
            'missing_method': 'median',
            'neutralization': 'industry',
            'time_align': 't+1',
            'data_window': ('2010-01-01', '2020-12-31'),
        }

        for param_name, options in oat_specs:
            for option in options:
                is_trivial = (option == defaults[param_name])
                config = AblationConfig(
                    name=f'L4_{param_name}_{option}',
                    layer='L4',
                    baseline_level='B3',
                    _is_trivial=is_trivial,
                    **{param_name: option},
                )
                results.append(self.run_single(config, factor_data, fwd_returns, industry_data))

        return results

    def run_l3(
        self,
        factor_data: Dict[str, pd.DataFrame],
        fwd_returns: pd.DataFrame,
        industry_data: Optional[pd.Series] = None,
        b3_full_result: Optional[AblationResult] = None,
    ) -> List[AblationResult]:
        """L3 参数消融 (依赖 T3 CUSUM 已完成)

        参数组 (spec §6.2):
        - CUSUM k/h (OAT: 3 k + 3 h = 6 配置, P1-4 修正)
        - EWMA halflife (3) + alpha 5 分叉 (5)
        - 5 叉阈值缩放 (3)
        - winsorize 比例 (3) + MAD 3σ (1) = 4 配置 (P1-5 修正)
        - correction_method (3: bh/bonferroni/none, P1-3 修正)
        返回 ~25 个 AblationResult (1 baseline + 24 消融)
        """
        results = []

        # B3_full 参照
        if b3_full_result is not None:
            results.append(b3_full_result)
        else:
            b3_config = AblationConfig(name='B3_full', layer='baseline', baseline_level='B3')
            results.append(self.run_single(b3_config, factor_data, fwd_returns, industry_data))

        # CUSUM k 参数 (OAT: h 固定 5.5, P1-4 修正 — 原组合对改为 OAT)
        # spec §6.2: k ∈ {0.25, 0.5, 0.75}, h=5.5 fixed
        # 命名 L3_cusum_oat_k{k} 以区分 k-OAT 与 h-OAT (避免测试过滤混淆)
        for k in [0.25, 0.5, 0.75]:
            config = AblationConfig(
                name=f'L3_cusum_oat_k{k}',
                layer='L3', baseline_level='B3', cusum_k=k, cusum_h=5.5,
            )
            results.append(self.run_single(config, factor_data, fwd_returns, industry_data))

        # CUSUM h 参数 (OAT: k 固定 0.5, P1-4 修正)
        # spec §6.2: h ∈ {4.0, 5.5, 7.0}, k=0.5 fixed
        # 命名 L3_cusum_oat_h{h} 以区分 h-OAT 与 k-OAT
        for h in [4.0, 5.5, 7.0]:
            config = AblationConfig(
                name=f'L3_cusum_oat_h{h}',
                layer='L3', baseline_level='B3', cusum_k=0.5, cusum_h=h,
            )
            results.append(self.run_single(config, factor_data, fwd_returns, industry_data))

        # EWMA halflife (M4 修正)
        for hl in [6, 12, 24]:
            config = AblationConfig(
                name=f'L3_ewma_halflife_{hl}',
                layer='L3', baseline_level='B3', ewma_halflife=hl,
            )
            results.append(self.run_single(config, factor_data, fwd_returns, industry_data))

        # EWMA alpha (5 分叉, M4 修正)
        for alpha in [0.1, 0.3, 0.5, 0.7, 0.9]:
            config = AblationConfig(
                name=f'L3_ewma_alpha_{alpha}',
                layer='L3', baseline_level='B3', ewma_alpha=alpha,
            )
            results.append(self.run_single(config, factor_data, fwd_returns, industry_data))

        # 5 叉阈值缩放 (M4 修正)
        for scale in [1.0, 1.2, 1.5]:
            config = AblationConfig(
                name=f'L3_threshold_scale_{scale}',
                layer='L3', baseline_level='B3', routing_threshold_scale=scale,
            )
            results.append(self.run_single(config, factor_data, fwd_returns, industry_data))

        # winsorize 比例 (P1-5: 含 MAD 3σ, 共 4 选项)
        # spec §6.2: 1% / 3% / 5% / MAD 3σ
        for ratio in [0.01, 0.03, 0.05]:
            config = AblationConfig(
                name=f'L3_winsorize_{ratio}',
                layer='L3', baseline_level='B3', winsorize_ratio=ratio,
            )
            results.append(self.run_single(config, factor_data, fwd_returns, industry_data))
        # MAD 3σ: winsorize_ratio 为 float 无法表示 MAD, 用 outlier_method='mad' (P1-5 修正)
        mad_config = AblationConfig(
            name='L3_winsorize_mad',
            layer='L3', baseline_level='B3', outlier_method='mad',
        )
        results.append(self.run_single(mad_config, factor_data, fwd_returns, industry_data))

        # 多重比较校正方法 (P1-3 修正: 原缺失, 补充 3 配置)
        # spec §6.2: correction_method ∈ {benjamini_hochberg, bonferroni, none}
        for method in ['benjamini_hochberg', 'bonferroni', 'none']:
            config = AblationConfig(
                name=f'L3_correction_{method}',
                layer='L3', baseline_level='B3', correction_method=method,
            )
            results.append(self.run_single(config, factor_data, fwd_returns, industry_data))

        return results

    # -------------------------------------------------------------------------
    # 比较与 BH-FDR
    # -------------------------------------------------------------------------

    def compare(
        self,
        experiment: AblationResult,
        reference: AblationResult,
    ) -> AblationComparison:
        """Ledoit-Wolf HAC + bootstrap 双侧显著性比较

        Sharpe 差: HAC 检验 (主路径) + bootstrap 验证 (辅助).
        IC 差: bootstrap 检验 (主路径).
        综合判定: HAC 显著 AND bootstrap(IC) 显著 → is_significant=True
        """
        # ΔIC 和 ΔSharpe
        delta_ic = (
            experiment.metrics.get('ic_mean', float('nan'))
            - reference.metrics.get('ic_mean', float('nan'))
        )
        delta_sharpe = (
            experiment.metrics.get('sharpe_ls', float('nan'))
            - reference.metrics.get('sharpe_ls', float('nan'))
        )

        # Ledoit-Wolf HAC: Sharpe 差检验 (唯一主路径)
        exp_ls = experiment.ls_return_series
        ref_ls = reference.ls_return_series
        if len(exp_ls) > 0 and len(ref_ls) > 0:
            t_stat_hac, p_value_hac = ledoit_wolf_hac_test(exp_ls, ref_ls, self.alpha)
        else:
            t_stat_hac, p_value_hac = 0.0, 1.0

        # Circular block bootstrap: IC 序列差
        exp_ic = experiment.ic_series
        ref_ic = reference.ic_series
        if len(exp_ic) > 0 and len(ref_ic) > 0:
            p_value_boot, boot_stats = circular_block_bootstrap(
                exp_ic, ref_ic,
                statistic='mean',
                n_bootstrap=self.n_bootstrap,
                block_size=self.block_size,
                seed=self.random_seed,
            )
            if len(boot_stats) > 0:
                ci_low = float(np.percentile(boot_stats, 2.5))
                ci_high = float(np.percentile(boot_stats, 97.5))
            else:
                ci_low, ci_high = float('nan'), float('nan')
        else:
            p_value_boot = 1.0
            ci_low, ci_high = float('nan'), float('nan')

        # Circular block bootstrap: Sharpe 序列差 (P2-2 补全)
        if len(exp_ls) > 0 and len(ref_ls) > 0:
            p_sharpe_boot, sharpe_boot_stats = circular_block_bootstrap(
                exp_ls, ref_ls,
                statistic='sharpe',
                n_bootstrap=self.n_bootstrap,
                block_size=self.block_size,
                seed=self.random_seed,
            )
            if len(sharpe_boot_stats) > 0:
                sharpe_ci_low = float(np.percentile(sharpe_boot_stats, 2.5))
                sharpe_ci_high = float(np.percentile(sharpe_boot_stats, 97.5))
            else:
                sharpe_ci_low, sharpe_ci_high = float('nan'), float('nan')
        else:
            p_sharpe_boot = float('nan')
            sharpe_ci_low, sharpe_ci_high = float('nan'), float('nan')

        # 综合判定: 双侧 p < alpha (P0-1 audit fix: HAC NaN 时仅用 bootstrap)
        # 原逻辑: is_significant = (p_hac < α) AND (p_boot < α)
        # 问题: p_hac=NaN 时 NaN<α=False → 否决 → 全 false
        # 修复: p_hac NaN → 仅用 bootstrap; 两侧都 NaN → False
        hac_ok = (not np.isnan(p_value_hac)) and (p_value_hac < self.alpha)
        boot_ok = (not np.isnan(p_value_boot)) and (p_value_boot < self.alpha)
        if np.isnan(p_value_hac):
            is_significant = boot_ok
        else:
            is_significant = hac_ok and boot_ok

        return AblationComparison(
            experiment=experiment.config.name,
            reference=reference.config.name,
            delta_ic=float(delta_ic) if not np.isnan(delta_ic) else 0.0,
            delta_sharpe=float(delta_sharpe) if not np.isnan(delta_sharpe) else 0.0,
            t_stat_hac=t_stat_hac,
            p_value_hac=p_value_hac,
            bootstrap_ci_low=ci_low,
            bootstrap_ci_high=ci_high,
            p_value_bootstrap=p_value_boot,
            sharpe_bootstrap_ci_low=sharpe_ci_low,
            sharpe_bootstrap_ci_high=sharpe_ci_high,
            p_value_bootstrap_sharpe=p_sharpe_boot,
            is_significant=is_significant,
            # M5 修正: 从 experiment config 传播 trivial 标记
            _is_trivial=getattr(experiment.config, '_is_trivial', False),
        )

    def compare_all(
        self,
        results: List[AblationResult],
        reference: AblationResult,
    ) -> List[AblationComparison]:
        """批量比较 + BH-FDR 校正

        对所有 results vs reference 做 compare, 然后对 p 值列表做 BH-FDR 校正.
        复用 backtest/multiple_testing.py apply_bh_fdr.

        M5 修正: _is_trivial=True 的比较 (默认选项, 与 baseline 相同)
        不参与 BH-FDR 校正, 但仍保留在结果列表中用于完整性报告.
        """
        comparisons = [self.compare(r, reference) for r in results]

        # M5 修正: BH-FDR 仅校正非平凡比较 (排除 _is_trivial)
        non_trivial_indices = [i for i, c in enumerate(comparisons)
                               if not getattr(c, '_is_trivial', False)]
        non_trivial_p_values = []
        for i in non_trivial_indices:
            p = comparisons[i].p_value_bootstrap
            non_trivial_p_values.append(p if not np.isnan(p) else 1.0)

        _, is_sig_bh_non_trivial = apply_bh_fdr(non_trivial_p_values, self.alpha)

        # 更新 is_significant: HAC 显著 AND BH-FDR 校正后 bootstrap 显著
        # trivial 比较的 is_significant 强制为 False (与 baseline 相同, 无显著差异)
        for i, c in enumerate(comparisons):
            if getattr(c, '_is_trivial', False):
                c.is_significant = False
            else:
                nt_idx = non_trivial_indices.index(i)
                sig_bh = is_sig_bh_non_trivial[nt_idx]
                c.is_significant = (c.p_value_hac < self.alpha) and sig_bh

        return comparisons

    # -------------------------------------------------------------------------
    # 诊断与报告
    # -------------------------------------------------------------------------

    def get_diagnostics(self) -> Dict[str, Any]:
        """获取诊断信息

        Returns:
            {
                'n_experiments': int,
                'total_runtime_sec': float,
                'base_config': dict,
                'alpha': float,
                'n_bootstrap': int,
                'block_size': int,
                'results_summary': List[dict],
            }
        """
        total_runtime = sum(r.runtime_sec for r in self._results)

        results_summary = []
        for r in self._results:
            results_summary.append({
                'name': r.config.name,
                'layer': r.config.layer,
                'ic_mean': r.metrics.get('ic_mean', float('nan')),
                'icir': r.metrics.get('icir', float('nan')),
                'sharpe_ls': r.metrics.get('sharpe_ls', float('nan')),
                'runtime_sec': r.runtime_sec,
            })

        return {
            'n_experiments': len(self._results),
            'total_runtime_sec': total_runtime,
            'base_config': str(self.base_config),
            'alpha': self.alpha,
            'n_bootstrap': self.n_bootstrap,
            'block_size': self.block_size,
            'results_summary': results_summary,
        }

    def generate_report(
        self,
        results: List[AblationResult],
        comparisons: List[AblationComparison],
    ) -> str:
        """生成 Markdown 消融报告

        报告结构 (规格 §7.4):
        1. 标题 + 元信息 (alpha, n_bootstrap, 实验数)
        2. Baseline 阶梯表 (B0-B3 + IC/ICIR/Sharpe/MaxDD/HitRate)
        3. L1 组件消融表 (5 模块 + ΔIC + ΔSharpe + p_HAC + p_Boot + 显著性)
        4. L2 路由消融表 (5 配置)
        5. L3 参数消融表 (~25 配置)
        6. L4 前置处理 OAT 表 (~20 配置)
        7. 排序保持性 ρ_step 表 (5 步骤)
        8. 正交化诊断表 (condition_number + VRR)
        9. 诚实立场声明
        10. 学术依据
        """
        from datetime import datetime

        lines: List[str] = []
        lines.append("# Ablation Study Report")
        lines.append("")
        lines.append(f"> **生成时间**: {datetime.now().isoformat()}")
        lines.append(f"> **alpha**: {self.alpha}, **n_bootstrap**: {self.n_bootstrap}")
        lines.append(f"> **Experiments**: {len(results)}, **Comparisons**: {len(comparisons)}")
        lines.append("")

        # 比较结果按实验名索引
        comp_by_exp: Dict[str, AblationComparison] = {
            c.experiment: c for c in comparisons
        }

        def _fmt(val: Any, prec: int = 4) -> str:
            """格式化浮点数, 处理 NaN/None"""
            if val is None:
                return "N/A"
            try:
                f = float(val)
            except (TypeError, ValueError):
                return "N/A"
            if np.isnan(f):
                return "N/A"
            return f"{f:.{prec}f}"

        def _sig_mark(c: Optional[AblationComparison]) -> str:
            """显著性标记 (BH-FDR 校正后)"""
            if c is None:
                return ""
            return "✓" if c.is_significant else "✗"

        # ── 1. Baseline 阶梯 ──
        baseline_results = [r for r in results if r.config.layer == 'baseline']
        if baseline_results:
            lines.append("## 1. Baseline 阶梯 (B0-B3)")
            lines.append("")
            lines.append("| Name | IC Mean | ICIR | Sharpe | MaxDD | HitRate |")
            lines.append("|------|---------|------|--------|-------|---------|")
            for r in baseline_results:
                m = r.metrics
                lines.append(
                    f"| {r.config.name} | {_fmt(m.get('ic_mean'))} | "
                    f"{_fmt(m.get('icir'), 3)} | {_fmt(m.get('sharpe_ls'), 3)} | "
                    f"{_fmt(m.get('max_drawdown'), 3)} | {_fmt(m.get('hit_rate'), 3)} |"
                )
            lines.append("")

        # ── 2-5. L1-L4 消融表 ──
        layer_titles = {
            'L1': '2. L1 组件消融',
            'L2': '3. L2 路由消融',
            'L3': '4. L3 参数消融',
            'L4': '5. L4 前置处理 OAT',
        }
        for layer, title in layer_titles.items():
            layer_results = [r for r in results if r.config.layer == layer]
            if not layer_results:
                continue
            lines.append(f"## {title}")
            lines.append("")
            lines.append(
                "| Name | IC Mean | ICIR | Sharpe | "
                "ΔIC | ΔSharpe | p_HAC | p_Boot | Sig |"
            )
            lines.append(
                "|------|---------|------|--------|"
                "-----|---------|-------|--------|-----|"
            )
            for r in layer_results:
                m = r.metrics
                c = comp_by_exp.get(r.config.name)
                lines.append(
                    f"| {r.config.name} | {_fmt(m.get('ic_mean'))} | "
                    f"{_fmt(m.get('icir'), 3)} | {_fmt(m.get('sharpe_ls'), 3)} | "
                    f"{_fmt(c.delta_ic) if c else 'N/A'} | "
                    f"{_fmt(c.delta_sharpe) if c else 'N/A'} | "
                    f"{_fmt(c.p_value_hac) if c else 'N/A'} | "
                    f"{_fmt(c.p_value_bootstrap) if c else 'N/A'} | "
                    f"{_sig_mark(c)} |"
                )
            lines.append("")

        # ── 6. 排序保持性 ρ_step ──
        lines.append("## 6. 排序保持性 ρ_step")
        lines.append("")
        lines.append(
            "| Experiment | imputer | winsorizer | scaler | "
            "neutralizer | orthogonalizer |"
        )
        lines.append(
            "|------------|---------|------------|--------|"
            "-------------|----------------|"
        )
        for r in results:
            rho = r.rho_step
            lines.append(
                f"| {r.config.name} | "
                f"{_fmt(rho.get('imputer', float('nan')), 3)} | "
                f"{_fmt(rho.get('winsorizer', float('nan')), 3)} | "
                f"{_fmt(rho.get('scaler', float('nan')), 3)} | "
                f"{_fmt(rho.get('neutralizer', float('nan')), 3)} | "
                f"{_fmt(rho.get('orthogonalizer', float('nan')), 3)} |"
            )
        lines.append("")

        # ── 7. 正交化诊断 ──
        lines.append("## 7. 正交化诊断")
        lines.append("")
        lines.append("| Experiment | condition_number | VRR |")
        lines.append("|------------|-----------------|-----|")
        for r in results:
            diag = r.ortho_diagnostics
            lines.append(
                f"| {r.config.name} | "
                f"{_fmt(diag.get('condition_number', float('nan')), 3)} | "
                f"{_fmt(diag.get('vrr_mean', float('nan')), 3)} |"
            )
        lines.append("")

        # ── 8. 诚实立场声明 ──
        lines.append("## 8. 诚实立场声明")
        lines.append("")
        lines.append("- 消融可能暴露负面结果 (路由无效/模块无贡献/参数不敏感)")
        lines.append("- 若消融发现模块无贡献, §6.4.2 评定将诚实降级")
        lines.append("- 若消融发现模块有正贡献, §6.4.2 评定将升级")
        lines.append("- BH-FDR 校正已应用于多重比较, 控制假发现率 (FDR)")
        lines.append("")

        # ── 9. 学术依据 ──
        lines.append("## 9. 学术依据")
        lines.append("")
        lines.append(
            "- Ledoit, O. & Wolf, M. (2008). Robust performance hypothesis "
            "testing with the Sharpe ratio. J. Empirical Finance 15(5):850-859."
        )
        lines.append(
            "- Politis, D. & Romano, J. (1992). A Circular Block Resampling "
            "Procedure for Stationary Data."
        )
        lines.append(
            "- Benjamini, Y. & Hochberg, Y. (1995). Controlling the False "
            "Discovery Rate. JRSS-B 57(1):289-300."
        )

        return '\n'.join(lines)
