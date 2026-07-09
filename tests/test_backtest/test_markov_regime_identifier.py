# -*- coding: utf-8 -*-
"""MarkovRegimeIdentifier 测试 (RESEARCH_NOTES E7 §3.1)

Markov 两状态体制转换识别 (Hamilton 1989).
用 statsmodels MarkovRegression 拟合, 不收敛时降级为硬阈值.

TDD Red 阶段: 测试先于实现.
"""
import pytest
import numpy as np
import pandas as pd
from unittest.mock import patch


# ============================================================
# 辅助函数
# ============================================================

def make_regime_state_data(n_obs: int = 300, seed: int = 42) -> pd.DataFrame:
    """生成含明显体制结构的合成状态数据

    前半段: 低换手率 (bear), 后半段: 高换手率 (bull).
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range('2020-01-01', periods=n_obs, freq='B')
    regime = np.zeros(n_obs, dtype=int)
    regime[n_obs // 2:] = 1
    # Clear mean shift so MarkovRegression can identify two regimes
    turnover = np.where(regime == 0, 0.5, 2.0) + rng.normal(0, 0.15, n_obs)
    data = pd.DataFrame({
        'market_turnover': turnover,
        'amihud_illiquidity': rng.normal(0, 1, n_obs),
    }, index=dates)
    return data


# ============================================================
# TestMarkovRegimeIdentifier
# ============================================================

class TestMarkovRegimeIdentifier:
    """MarkovRegimeIdentifier 测试 (RESEARCH_NOTES E7 §3.1.8)"""

    def test_01_fit_returns_self(self):
        """fit 返回 self"""
        from backtest.markov_regime_identifier import MarkovRegimeIdentifier
        state_data = make_regime_state_data(n_obs=300)
        ident = MarkovRegimeIdentifier(
            n_regimes=2, min_observations=100, enable=True,
        )
        result = ident.fit(state_data, target_variable='market_turnover')
        assert result is ident
        assert isinstance(result, MarkovRegimeIdentifier)

    def test_02_predict_returns_int_array(self):
        """predict 返回 int 数组, 值在 {0, 1}"""
        from backtest.markov_regime_identifier import MarkovRegimeIdentifier
        state_data = make_regime_state_data(n_obs=300)
        ident = MarkovRegimeIdentifier(
            n_regimes=2, min_observations=100, enable=True,
        )
        ident.fit(state_data, target_variable='market_turnover')
        labels = ident.predict(state_data)
        assert isinstance(labels, np.ndarray)
        assert labels.dtype in (np.int64, np.int32, int)
        unique = set(np.unique(labels).tolist())
        assert unique.issubset({0, 1}), f"unexpected labels: {unique}"

    def test_03_predict_proba_sums_to_one(self):
        """概率行和为 1"""
        from backtest.markov_regime_identifier import MarkovRegimeIdentifier
        state_data = make_regime_state_data(n_obs=300)
        ident = MarkovRegimeIdentifier(
            n_regimes=2, min_observations=100, enable=True,
        )
        ident.fit(state_data, target_variable='market_turnover')
        probs = ident.predict_proba(state_data)
        assert isinstance(probs, np.ndarray)
        assert probs.ndim == 2
        assert probs.shape[1] == 2
        assert probs.shape[0] == len(state_data)
        np.testing.assert_allclose(
            probs.sum(axis=1), 1.0, atol=1e-6,
        )

    def test_04_transition_matrix_shape(self):
        """转移矩阵形状 (2, 2)"""
        from backtest.markov_regime_identifier import MarkovRegimeIdentifier
        state_data = make_regime_state_data(n_obs=300)
        ident = MarkovRegimeIdentifier(
            n_regimes=2, min_observations=100, enable=True,
        )
        ident.fit(state_data, target_variable='market_turnover')
        tm = ident.get_transition_matrix()
        assert isinstance(tm, np.ndarray)
        assert tm.shape == (2, 2)

    def test_05_regime_persistence_positive(self):
        """持续期 > 0"""
        from backtest.markov_regime_identifier import MarkovRegimeIdentifier
        state_data = make_regime_state_data(n_obs=300)
        ident = MarkovRegimeIdentifier(
            n_regimes=2, min_observations=100, enable=True,
        )
        ident.fit(state_data, target_variable='market_turnover')
        persistence = ident.get_regime_persistence()
        assert persistence > 0
        assert np.isfinite(persistence)

    def test_06_fallback_on_non_convergence(self):
        """Markov 不收敛时降级为硬阈值"""
        from backtest.markov_regime_identifier import MarkovRegimeIdentifier
        state_data = make_regime_state_data(n_obs=300)
        ident = MarkovRegimeIdentifier(
            n_regimes=2, min_observations=100, enable=True,
        )
        # Mock MarkovRegression to raise exception, triggering fallback
        with patch(
            'statsmodels.tsa.regime_switching.markov_regression.MarkovRegression',
        ) as mock_mr:
            mock_mr.side_effect = Exception("mocked fit failure")
            ident.fit(state_data, target_variable='market_turnover')
        # Fallback should be used
        diag = ident.get_diagnostics()
        assert diag['fallback_used'] is True
        assert diag['converged'] is False
        # Should still return valid predictions
        labels = ident.predict(state_data)
        assert len(labels) == len(state_data)
        probs = ident.predict_proba(state_data)
        np.testing.assert_allclose(probs.sum(axis=1), 1.0, atol=1e-6)

    def test_07_get_diagnostics_fields(self):
        """诊断含 converged/loglikelihood/aic/bic"""
        from backtest.markov_regime_identifier import MarkovRegimeIdentifier
        state_data = make_regime_state_data(n_obs=300)
        ident = MarkovRegimeIdentifier(
            n_regimes=2, min_observations=100, enable=True,
        )
        ident.fit(state_data, target_variable='market_turnover')
        diag = ident.get_diagnostics()
        assert isinstance(diag, dict)
        for key in ('converged', 'fallback_used', 'loglikelihood',
                    'aic', 'bic', 'n_regimes', 'regime_persistence'):
            assert key in diag, f"missing key: {key}"

    def test_08_min_observations_enforced(self):
        """观测不足报错"""
        from backtest.markov_regime_identifier import MarkovRegimeIdentifier
        state_data = make_regime_state_data(n_obs=50)  # < min_observations
        ident = MarkovRegimeIdentifier(
            n_regimes=2, min_observations=252, enable=True,
        )
        with pytest.raises(ValueError):
            ident.fit(state_data, target_variable='market_turnover')

    def test_09_disabled_no_op(self):
        """enable=False 时 fit 是 no-op"""
        from backtest.markov_regime_identifier import MarkovRegimeIdentifier
        state_data = make_regime_state_data(n_obs=300)
        ident = MarkovRegimeIdentifier(
            n_regimes=2, min_observations=100, enable=False,
        )
        result = ident.fit(state_data, target_variable='market_turnover')
        assert result is ident
        # predict/predict_proba should handle disabled gracefully
        labels = ident.predict(state_data)
        assert isinstance(labels, np.ndarray)
        diag = ident.get_diagnostics()
        assert diag['enabled'] is False
