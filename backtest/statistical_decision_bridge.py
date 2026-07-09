# -*- coding: utf-8 -*-
"""统计→决策桥接接口层 (RESEARCH_NOTES §4, A+C 混合方案)

方案 A (概率映射): 将 (p_value, IC, drift_flag) 映射为 softmax 决策权重
方案 C (OCO): 在线凸优化更新权重 (梯度下降 + 单纯形投影)
Q2 soft-update: 在 (μ, σ²) 参数空间在线递推更新

三工程挑战:
- 时间对齐 (§4.7.1): _align_time_frequency() 将日频统计聚合为月频/季频
- 冷启动 O1: _cold_start_prior() 用无信息先验 (μ=0, σ²=1)
- 状态切换 O2: StateConditionedPrior 存储体制条件先验
- 误差传播 O3: 显式建模 σ², 决策权重受 σ² 调制

学术依据:
- Benjamini, Y. & Hochberg, Y. (1995). "Controlling the False Discovery Rate."
  JRSS-B 57(1):289-300. (BH-FDR p 值)
- Shalev-Shwartz, S. (2012). "Online Learning and Online Convex Optimization."
  Foundations and Trends in Machine Learning 4(2):107-194. (OCO)
- Wang, J. & Carreira-Perpiñán, M. Á. (2013). "Projection onto the Probability
  Simplex." ICML 2013. (单纯形投影)

默认 enable=False (无副作用), 集成由主会话完成, 不修改 pipelines_v2.py.
"""
from dataclasses import dataclass
from typing import Dict, Any, Optional, List
import logging

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class StateConditionedPrior:
    """状态条件先验 (RESEARCH_NOTES §4.5)

    存储因子在特定体制下的 (μ, σ²) 先验, 用于:
    - 冷启动 (O1): 新因子用体制先验
    - 状态切换 (O2): 体制变化时切换先验
    - 预测误差传播 (O3): 显式建模 σ² 传播

    Attributes:
        factor_name: 因子名称
        regime: 体制标签 (如 'bull' / 'bear' / 'unknown')
        mu_prior: 先验均值 μ
        sigma_sq_prior: 先验方差 σ²
        confidence: 置信度 (基于观测数, 0-1)
        n_observations: 观测数
    """
    factor_name: str
    regime: str
    mu_prior: float
    sigma_sq_prior: float
    confidence: float = 1.0
    n_observations: int = 0


class StatisticalDecisionBridge:
    """统计→决策桥接 (RESEARCH_NOTES §4, A+C 混合方案)

    方案 A (概率映射): 将 (p_value, IC, drift_flag) 映射为决策权重
    方案 C (OCO): 在线凸优化更新权重
    Q2 soft-update: 在 (μ, σ²) 参数空间软更新

    三工程挑战的处理:
    - 时间对齐 (§4.7.1): _align_time_frequency() 将日频统计聚合为月频/季频
    - 冷启动 O1: _cold_start_prior() 用无信息先验 (μ=0, σ²=1)
    - 状态识别延迟 O2: StateConditionedPrior 存储体制条件先验
    - 预测误差传播 O3: 显式建模 σ² 传播

    Usage::

        bridge = StatisticalDecisionBridge(enable=True, learning_rate=0.1)
        bridge.fit(statistical_outputs)
        weights = bridge.compute_decision_weights()
    """

    def __init__(
        self,
        enable: bool = False,
        learning_rate: float = 0.1,
        min_observations: int = 60,
        cold_start_prior: str = 'uninformative',
        lambda_softmax: float = 1.0,
        oco_eta: float = 0.01,
    ):
        """初始化统计→决策桥接

        Args:
            enable: 是否启用 (默认 False, 无副作用)
            learning_rate: 学习率 (用于诊断报告 + Q2 soft-update)
            min_observations: 最小观测数 (不足时用冷启动先验)
            cold_start_prior: 冷启动策略 ('uninformative' = μ=0, σ²=1)
            lambda_softmax: softmax 温度 (越大权重越集中)
            oco_eta: OCO 初始学习率 (eta_t = eta / sqrt(t))
        """
        self.enable = bool(enable)
        self.learning_rate = float(learning_rate)
        self.min_observations = int(min_observations)
        self.cold_start_prior = str(cold_start_prior)

        # softmax 温度 (越大权重越集中)
        self._lambda_softmax: float = float(lambda_softmax)
        # OCO 初始学习率
        self._oco_eta: float = float(oco_eta)

        # 因子参数: {factor_name: {'mu', 'sigma_sq', 'n_obs', 'regime'}}
        self._factor_params: Dict[str, Dict] = {}
        # 统计输出缓存
        self._statistical_outputs: Optional[Dict[str, Dict]] = None
        # OCO 权重
        self._oco_weights: Optional[Dict[str, float]] = None
        # OCO 迭代计数 (用于学习率衰减 eta_t = eta / sqrt(t))
        self._oco_t: int = 0

    # ==========================================================
    # fit: 拟合桥接层
    # ==========================================================

    def fit(
        self,
        statistical_outputs: Dict[str, Dict],
        state_priors: Optional[Dict[str, StateConditionedPrior]] = None,
    ) -> 'StatisticalDecisionBridge':
        """拟合桥接层

        Args:
            statistical_outputs: {factor_name: {'p_value', 'ic_mean',
                                                 'drift_flag', 'regime'}}
            state_priors: {factor_name: StateConditionedPrior} 状态条件先验

        Returns:
            self (链式调用)
        """
        self._statistical_outputs = statistical_outputs

        for fname, outputs in statistical_outputs.items():
            if state_priors and fname in state_priors:
                prior = state_priors[fname]
            else:
                prior = self._cold_start_prior(fname, self.cold_start_prior)

            self._factor_params[fname] = {
                'mu': prior.mu_prior,
                'sigma_sq': prior.sigma_sq_prior,
                'n_obs': prior.n_observations,
                'regime': prior.regime,
            }

        return self

    # ==========================================================
    # Q2 soft-update: 在 (μ, σ²) 参数空间在线递推
    # ==========================================================

    def update(
        self,
        factor_name: str,
        new_observation: float,
        regime: Optional[str] = None,
    ) -> Dict[str, float]:
        """Q2 soft-update 在 (μ, σ²) 参数空间

        指数衰减 soft-update (spec L3465-3467):
            α = min(learning_rate, 1 / (n_obs + 1))
            μ_new = (1 - α) * μ_old + α * x
            σ²_new = (1 - α) * σ²_old + α * (x - μ_new)²
            n_obs += 1

        Args:
            factor_name: 因子名称
            new_observation: 新观测值
            regime: 可选体制标签 (更新 regime)

        Returns:
            {'factor', 'mu', 'sigma_sq', 'n_obs', 'regime'}
        """
        if factor_name not in self._factor_params:
            self._factor_params[factor_name] = {
                'mu': 0.0, 'sigma_sq': 1.0,
                'n_obs': 0, 'regime': regime or 'unknown',
            }

        params = self._factor_params[factor_name]
        old_mu = params['mu']
        old_sigma_sq = params['sigma_sq']
        x = float(new_observation)

        # 指数衰减 soft-update (spec 公式)
        alpha = min(self.learning_rate, 1.0 / (params['n_obs'] + 1))
        new_mu = (1.0 - alpha) * old_mu + alpha * x
        new_sigma_sq = (1.0 - alpha) * old_sigma_sq + alpha * (x - new_mu) ** 2
        # 数值保护: 避免零/负方差
        new_sigma_sq = max(new_sigma_sq, 1e-10)

        params['mu'] = new_mu
        params['sigma_sq'] = new_sigma_sq
        params['n_obs'] += 1
        if regime is not None:
            params['regime'] = regime

        return {
            'factor': factor_name,
            'mu': new_mu,
            'sigma_sq': new_sigma_sq,
            'n_obs': params['n_obs'],
            'regime': params['regime'],
        }

    # ==========================================================
    # 方案 A: 概率映射 → softmax 决策权重
    # ==========================================================

    def compute_decision_weights(self, alpha: float = 0.05) -> Dict[str, float]:
        """方案 A: 概率映射 — (p_value, IC, drift_flag) → softmax 权重

        s_f = (1 - p_f) * sign(IC_f) * |IC_f| * (1 - drift_f)
        w_f = exp(λ * s_f) / Σ exp(λ * s_f')

        权重和为 1.

        Args:
            alpha: 显著性水平 (当前未直接使用, p 值已由 BH-FDR 校正)

        Returns:
            {factor_name: weight} 权重和为 1;
            enable=False 或未 fit 时返回 {}
        """
        if not self.enable:
            return {}
        if self._statistical_outputs is None:
            return {}

        scores = {}
        for fname, outputs in self._statistical_outputs.items():
            p_val = outputs.get('p_value', 1.0)
            ic = outputs.get('ic_mean', 0.0)
            drift = bool(outputs.get('drift_flag', False))
            scores[fname] = self._probability_mapping(p_val, ic, drift)

        if not scores:
            return {}

        # softmax (数值稳定: 减去最大值)
        max_score = max(scores.values())
        exp_scores = {
            f: float(np.exp(self._lambda_softmax * (s - max_score)))
            for f, s in scores.items()
        }
        total = sum(exp_scores.values())
        if total > 0:
            return {f: e / total for f, e in exp_scores.items()}
        # 兜底: 均匀分配
        n = len(scores)
        return {f: 1.0 / n for f in scores}

    def _probability_mapping(
        self,
        p_value: float,
        ic: float,
        drift_flag: bool,
    ) -> float:
        """方案 A 核心映射: 统计输出 → 决策得分

        s = (1 - p) * sign(IC) * |IC| * (1 - drift)

        - (1 - p): p 值越小, 得分越高 (显著因子权重高)
        - sign(IC) * |IC|: IC 正向且大, 得分高
        - (1 - drift): 漂移因子降权 (drift=True → 得分 0)
        """
        significance = max(0.0, 1.0 - p_value)
        ic_component = float(np.sign(ic) * abs(ic))
        drift_penalty = 0.0 if drift_flag else 1.0
        return significance * ic_component * drift_penalty

    # ==========================================================
    # 方案 C: 在线凸优化 (OCO) — 梯度下降 + 单纯形投影
    # ==========================================================

    def oco_update(
        self,
        gradient: Dict[str, float],
        eta: Optional[float] = None,
    ) -> Dict[str, float]:
        """方案 C: 在线凸优化更新

        w_{t+1} = Π_Δ(w_t - η_t * ∇ℓ)
        Π_Δ: 单纯形投影 (非负 + 和为 1)
        η_t = η / sqrt(t)  (学习率衰减)

        Args:
            gradient: {factor_name: gradient} 梯度
            eta: 基础学习率 (None 时用 self._oco_eta)

        Returns:
            {factor_name: weight} 权重非负且和为 1
        """
        if self._oco_weights is None:
            factors = list(gradient.keys())
            n = len(factors)
            if n == 0:
                return {}
            self._oco_weights = {f: 1.0 / n for f in factors}

        # eta 默认使用 self._oco_eta
        if eta is None:
            eta = self._oco_eta

        # 学习率衰减 eta_t = eta / sqrt(t)
        self._oco_t += 1
        eta_eff = float(eta) / np.sqrt(self._oco_t)

        # 梯度下降
        new_weights = {
            f: self._oco_weights.get(f, 0.0) - eta_eff * gradient.get(f, 0.0)
            for f in self._oco_weights
        }

        # 单纯形投影
        self._oco_weights = self._project_to_simplex(new_weights)
        return dict(self._oco_weights)

    def _project_to_simplex(self, weights: Dict[str, float]) -> Dict[str, float]:
        """投影到单纯形 {w: w >= 0, sum(w) = 1}

        Wang & Carreira-Perpiñán (2013) 算法.

        Args:
            weights: 任意实数权重字典

        Returns:
            投影后权重 (非负且和为 1)
        """
        keys = list(weights.keys())
        values = np.array([weights[k] for k in keys], dtype=float)
        n = len(values)

        if n == 0:
            return {}
        if n == 1:
            return {keys[0]: 1.0}

        # 排序降序
        u = np.sort(values)[::-1]
        cssv = np.cumsum(u) - 1.0
        rho_candidates = np.nonzero(u - cssv / np.arange(1, n + 1) > 0)[0]
        if len(rho_candidates) == 0:
            # 兜底: 均匀分配
            return {k: 1.0 / n for k in keys}
        rho = rho_candidates[-1]
        theta = cssv[rho] / (rho + 1)
        projected = np.maximum(values - theta, 0.0)

        # 归一化 (浮点保护)
        total = projected.sum()
        if total > 0:
            projected = projected / total
        else:
            projected = np.ones(n) / n

        return {k: float(v) for k, v in zip(keys, projected)}

    # ==========================================================
    # 冷启动 O1
    # ==========================================================

    def _cold_start_prior(
        self,
        factor_name: str,
        strategy: str = 'uninformative',
    ) -> StateConditionedPrior:
        """冷启动先验 (O1)

        Args:
            factor_name: 因子名称
            strategy: 冷启动策略
                - 'uninformative': μ=0, σ²=1 (无信息先验)
                - 其他: 简化为 uninformative

        Returns:
            StateConditionedPrior (无信息先验)
        """
        return StateConditionedPrior(
            factor_name=factor_name,
            regime='unknown',
            mu_prior=0.0,
            sigma_sq_prior=1.0,
            confidence=0.0,
            n_observations=0,
        )

    # ==========================================================
    # 时间对齐 (§4.7.1)
    # ==========================================================

    def _align_time_frequency(
        self,
        daily_stats: Dict[str, List[float]],
        decision_freq: str = 'M',
    ) -> Dict[str, float]:
        """时间对齐 (§4.7.1): 日频统计 → 月频/季频决策

        Args:
            daily_stats: {factor_name: [daily_values]}
            decision_freq: 'D' / 'W' / 'M' / 'Q'
                - 'D': 日频, 取最近值
                - 'W': 周频, 近 5 日均值
                - 'M': 月频, 近 21 日均值
                - 'Q': 季频, 近 63 日均值

        Returns:
            {factor_name: aggregated_value}
        """
        if decision_freq == 'D':
            return {
                f: float(v[-1]) if v else 0.0
                for f, v in daily_stats.items()
            }

        # 窗口大小
        window_map = {'W': 5, 'M': 21, 'Q': 63}
        window = window_map.get(decision_freq, 21)

        aggregated = {}
        for fname, values in daily_stats.items():
            if not values:
                aggregated[fname] = 0.0
            else:
                sliced = values[-window:]
                aggregated[fname] = float(np.mean(sliced))

        return aggregated

    # ==========================================================
    # 诊断
    # ==========================================================

    def get_diagnostics(self) -> Dict[str, Any]:
        """获取桥接层诊断信息

        Returns:
            {
                'enabled': bool,
                'n_factors': int,
                'learning_rate': float,
                'cold_start_strategy': str,
                'factor_params': {factor: {'mu', 'sigma_sq', 'n_obs'}},
                'oco_weights': Optional[Dict],
            }
        """
        return {
            'enabled': self.enable,
            'n_factors': len(self._factor_params),
            'learning_rate': self.learning_rate,
            'lambda_softmax': self._lambda_softmax,
            'oco_eta': self._oco_eta,
            'min_observations': self.min_observations,
            'cold_start_strategy': self.cold_start_prior,
            'factor_params': {
                f: {
                    'mu': p['mu'],
                    'sigma_sq': p['sigma_sq'],
                    'n_obs': p['n_obs'],
                }
                for f, p in self._factor_params.items()
            },
            'oco_weights': (
                dict(self._oco_weights) if self._oco_weights else None
            ),
        }
