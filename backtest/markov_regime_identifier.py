# -*- coding: utf-8 -*-
"""Markov 两状态体制识别器 (RESEARCH_NOTES E7 §3.1)

Hamilton (1989) Markov 体制转换模型, 用 statsmodels MarkovRegression 拟合.
不收敛时降级为硬阈值 (复用 T1 health.py 模式).

设计原则:
- 默认 enable=False (opt-in)
- 不收敛时降级为硬阈值 (基于 target_variable 的分位数)
- 提供 predict_proba() 输出体制概率, 供 E8/E10 使用
"""
from typing import Dict, Any, Optional
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class MarkovRegimeIdentifier:
    """Markov 两状态体制识别器 (RESEARCH_NOTES §2B.3 + Hamilton 1989)

    用 statsmodels MarkovRegression 拟合两状态体制转换模型,
    识别 bull/bear 体制. 不收敛时降级为硬阈值 (复用 T1 health.py 模式).

    设计原则:
    - 默认 enable=False (opt-in)
    - 不收敛时降级为硬阈值 (基于 target_variable 的分位数)
    - 提供 predict_proba() 输出体制概率, 供 E8/E10 使用
    """

    def __init__(
        self,
        n_regimes: int = 2,
        min_observations: int = 252,
        max_iter: int = 100,
        tolerance: float = 1e-6,
        enable: bool = False,
    ):
        self.n_regimes = n_regimes
        self.min_observations = min_observations
        self.max_iter = max_iter
        self.tolerance = tolerance
        self.enable = enable
        self._model = None
        self._converged = False
        self._loglikelihood: Optional[float] = None
        self._aic: Optional[float] = None
        self._bic: Optional[float] = None
        self._transition_matrix: Optional[np.ndarray] = None
        self._regime_means: Optional[list] = None
        self._regime_stds: Optional[list] = None
        self._fallback_used = False
        self._target_variable: str = 'market_turnover'
        self._fitted_data: Optional[pd.Series] = None

    def fit(
        self,
        state_data: pd.DataFrame,
        target_variable: str = 'market_turnover',
    ) -> 'MarkovRegimeIdentifier':
        """拟合 Markov 体制转换模型

        Args:
            state_data: StateDataLoader.load_12_state_variables() 返回的 DataFrame
            target_variable: 用于体制识别的目标变量 (默认 market_turnover)

        Returns:
            self (链式调用)

        Raises:
            ValueError: target_variable 不在列中 / 观测数不足
        """
        if not self.enable:
            return self

        if target_variable not in state_data.columns:
            raise ValueError(
                f"target_variable {target_variable} 不在 state_data 列中"
            )

        self._target_variable = target_variable
        y = state_data[target_variable].dropna()

        if len(y) < self.min_observations:
            raise ValueError(
                f"观测数 {len(y)} < 最小要求 {self.min_observations}"
            )

        self._fitted_data = y

        try:
            from statsmodels.tsa.regime_switching.markov_regression import (
                MarkovRegression,
            )
            self._model = MarkovRegression(
                y, k_regimes=self.n_regimes, trend='c',
            ).fit(maxiter=self.max_iter, tol=self.tolerance)

            self._converged = bool(
                self._model.mle_retvals.get('converged', False)
            )
            self._loglikelihood = float(self._model.llf)
            self._aic = float(self._model.aic)
            self._bic = float(self._model.bic)

            # 转移矩阵: regime_transition 返回 (n_regimes, n_regimes, 1), squeeze 到 2D
            tm = self._model.regime_transition
            if tm.ndim == 3:
                tm = tm.squeeze(axis=-1)
            self._transition_matrix = np.asarray(tm)

            # 体制均值与标准差
            params = self._model.params
            self._regime_means = [
                float(params[f'const[{i}]']) for i in range(self.n_regimes)
            ]
            self._regime_stds = [
                float(params[f'sigma2[{i}]']) ** 0.5
                for i in range(self.n_regimes)
            ]
            self._fallback_used = False
        except Exception as e:
            # 降级: 硬阈值
            logger.warning(
                f"MarkovRegression 拟合失败 ({e}), 降级为硬阈值"
            )
            self._fallback_used = True
            self._converged = False
            self._model = None
            self._loglikelihood = None
            self._aic = None
            self._bic = None
            self._regime_means = [
                float(y.quantile(0.25)), float(y.quantile(0.75)),
            ]
            self._regime_stds = [float(y.std())] * self.n_regimes
            self._transition_matrix = np.array(
                [[0.95, 0.05], [0.05, 0.95]]
            )

        return self

    def predict(self, state_data: pd.DataFrame) -> np.ndarray:
        """预测体制标签 (0=bull, 1=bear)

        Args:
            state_data: 状态变量 DataFrame

        Returns:
            np.ndarray: 体制标签, 值在 {0, 1, ..., n_regimes-1}
        """
        if not self.enable:
            return np.array([], dtype=int)

        if self._model is not None and not self._fallback_used:
            probs = self._model.smoothed_marginal_probabilities
            return np.argmax(probs, axis=1).astype(int)

        return self._fallback_hard_threshold(
            state_data, self._target_variable,
        )

    def predict_proba(self, state_data: pd.DataFrame) -> np.ndarray:
        """预测体制概率 (N, n_regimes)

        Args:
            state_data: 状态变量 DataFrame

        Returns:
            np.ndarray: 形状 (N, n_regimes), 行和为 1
        """
        if self._model is not None and not self._fallback_used:
            return np.asarray(self._model.smoothed_marginal_probabilities)

        # 降级: 硬阈值的软版本 (sigmoid)
        target = self._target_variable
        if target not in state_data.columns:
            # 用 fitted_data 的长度返回均匀概率
            n = len(self._fitted_data) if self._fitted_data is not None else 0
            return np.full((n, self.n_regimes), 1.0 / self.n_regimes)

        y = state_data[target].values
        threshold = np.nanmedian(y) if not np.all(np.isnan(y)) else 0.0
        # sigmoid 软概率
        prob_high = 1.0 / (1.0 + np.exp(-(y - threshold) * 10))
        prob_high = np.nan_to_num(prob_high, nan=0.5)
        return np.column_stack([1 - prob_high, prob_high])

    def _fallback_hard_threshold(
        self,
        state_data: pd.DataFrame,
        target_variable: str,
    ) -> np.ndarray:
        """降级: 硬阈值划分 (复用 T1 health.py 的 _split_bull_bear 模式)

        Args:
            state_data: 状态变量 DataFrame
            target_variable: 目标变量名

        Returns:
            np.ndarray: 体制标签 (0 或 1)
        """
        if target_variable not in state_data.columns:
            n = len(state_data)
            return np.zeros(n, dtype=int)

        y = state_data[target_variable].values
        threshold = np.nanmedian(y) if not np.all(np.isnan(y)) else 0.0
        labels = (y < threshold).astype(int)
        return np.nan_to_num(labels, nan=0).astype(int)

    def get_transition_matrix(self) -> np.ndarray:
        """返回转移矩阵 (n_regimes, n_regimes)"""
        return self._transition_matrix

    def get_regime_persistence(self) -> float:
        """体制平均持续期 = 1 / (1 - p_stay)

        Returns:
            float: 平均持续期. p_stay >= 1 时返回 inf.
        """
        if self._transition_matrix is None:
            return float('nan')
        p_stay = float(np.diag(self._transition_matrix).mean())
        if p_stay >= 1.0:
            return float('inf')
        return float(1.0 / (1.0 - p_stay))

    def get_diagnostics(self) -> Dict[str, Any]:
        """返回诊断信息

        Returns:
            Dict 含 enabled/converged/fallback_used/n_regimes/
            loglikelihood/aic/bic/regime_means/regime_stds/
            regime_persistence/transition_matrix
        """
        return {
            'enabled': self.enable,
            'converged': self._converged,
            'fallback_used': self._fallback_used,
            'n_regimes': self.n_regimes,
            'loglikelihood': self._loglikelihood,
            'aic': self._aic,
            'bic': self._bic,
            'regime_means': self._regime_means,
            'regime_stds': self._regime_stds,
            'regime_persistence': self.get_regime_persistence(),
            'transition_matrix': (
                self._transition_matrix.tolist()
                if self._transition_matrix is not None
                else None
            ),
        }
