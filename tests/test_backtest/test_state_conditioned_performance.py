# -*- coding: utf-8 -*-
"""StateConditionedAnalyzer 测试 (RESEARCH_NOTES E8 §3.1)

状态条件性能矩阵 + R_factor/IC 双轨回归.

双轨:
- Track 1 (R_factor): R_factor,t = α + β' × S_{t-1} + ε_t  (Ferson 2003)
- Track 2 (IC):       IC_t = α + β' × S_{t-1} + ν_t

Newey-West HAC 标准误, BH-FDR 多重检验校正.

TDD Red 阶段: 测试先于实现.
"""
import pytest
import numpy as np
import pandas as pd


# ============================================================
# 辅助函数: 合成数据生成
# ============================================================

def make_e8_data(n_obs: int = 300, n_stocks: int = 100, seed: int = 42):
    """生成 E8 测试合成数据

    Returns:
        factor_returns: Dict[str, pd.DataFrame] — {factor_name: (N_stocks, T_dates)}
        state_data: pd.DataFrame — (T, 12) 状态变量
        regime_labels: np.ndarray — (T,) 体制标签
        fwd_returns: pd.DataFrame — (T, N_stocks) 前向收益
    """
    from backtest.state_data_loader import StateDataLoader
    rng = np.random.default_rng(seed)
    dates = pd.date_range('2020-01-01', periods=n_obs, freq='B')
    stocks = [f'S{i:03d}' for i in range(n_stocks)]

    # State data: 12 variables
    state_dict = {}
    for var in StateDataLoader.ALL_VARIABLES:
        state_dict[var] = rng.normal(0, 1, n_obs)
    state_data = pd.DataFrame(state_dict, index=dates)

    # Regime labels: first half regime 0, second half regime 1
    regime_labels = np.zeros(n_obs, dtype=int)
    regime_labels[n_obs // 2:] = 1

    # Factor values: 2 factors, random cross-sectional
    factor_returns = {}
    for fname in ['factor_1', 'factor_2']:
        vals = rng.normal(0, 1, (n_stocks, n_obs))
        factor_returns[fname] = pd.DataFrame(vals, index=stocks, columns=dates)

    # Forward returns: constructed so factor_1 has IC
    # r_{i,t} = 0.3 * f_{i,t} + noise  (IC > 0 for factor_1)
    fwd_vals = np.zeros((n_obs, n_stocks))
    f1 = factor_returns['factor_1'].values.T  # (T, N)
    fwd_vals = 0.3 * f1 + rng.normal(0, 0.5, (n_obs, n_stocks))
    fwd_returns = pd.DataFrame(fwd_vals, index=dates, columns=stocks)

    return factor_returns, state_data, regime_labels, fwd_returns


def make_state_dependent_data(n_obs: int = 300, n_stocks: int = 100, seed: int = 42):
    """生成已知状态依赖数据: R_factor 依赖于 market_turnover

    r_{i,t} = beta * market_turnover[t] * f_{i,t} + noise
    => R_factor ∝ market_turnover, 回归 beta 应显著
    """
    from backtest.state_data_loader import StateDataLoader
    rng = np.random.default_rng(seed)
    dates = pd.date_range('2020-01-01', periods=n_obs, freq='B')
    stocks = [f'S{i:03d}' for i in range(n_stocks)]

    # State data with market_turnover having a clear trend
    state_dict = {}
    for var in StateDataLoader.ALL_VARIABLES:
        state_dict[var] = rng.normal(0, 1, n_obs)
    # Make market_turnover have a strong signal
    state_dict['market_turnover'] = np.linspace(-2, 2, n_obs) + rng.normal(0, 0.1, n_obs)
    state_data = pd.DataFrame(state_dict, index=dates)

    regime_labels = np.zeros(n_obs, dtype=int)
    regime_labels[n_obs // 2:] = 1

    # Factor values
    f_vals = rng.normal(0, 1, (n_stocks, n_obs))
    factor_returns = {'factor_dep': pd.DataFrame(f_vals, index=stocks, columns=dates)}

    # Forward returns: r = beta * market_turnover * f + noise
    beta = 0.5
    mt = state_data['market_turnover'].values  # (T,)
    fwd_vals = beta * np.outer(mt, np.ones(n_stocks)) * f_vals.T + rng.normal(0, 0.3, (n_obs, n_stocks))
    fwd_returns = pd.DataFrame(fwd_vals, index=dates, columns=stocks)

    return factor_returns, state_data, regime_labels, fwd_returns


# ============================================================
# TestStateConditionedAnalyzer
# ============================================================

class TestStateConditionedAnalyzer:
    """StateConditionedAnalyzer 测试 (RESEARCH_NOTES E8 §3.1.17)"""

    def test_01_fit_returns_self(self):
        """fit 返回 self"""
        from backtest.state_conditioned_performance import StateConditionedAnalyzer
        fr, sd, rl, fwd = make_e8_data()
        analyzer = StateConditionedAnalyzer(enable=True, alpha=0.05)
        result = analyzer.fit(fr, sd, rl, fwd)
        assert result is analyzer
        assert isinstance(result, StateConditionedAnalyzer)

    def test_02_compute_performance_matrix_shape(self):
        """性能矩阵形状 == (n_factors, n_regimes)"""
        from backtest.state_conditioned_performance import StateConditionedAnalyzer
        fr, sd, rl, fwd = make_e8_data()
        analyzer = StateConditionedAnalyzer(enable=True)
        analyzer.fit(fr, sd, rl, fwd)
        matrix = analyzer.compute_performance_matrix(metric='ic')
        assert isinstance(matrix, pd.DataFrame)
        assert matrix.shape[0] == 2  # 2 factors
        assert matrix.shape[1] == 2  # 2 regimes

    def test_03_compute_performance_matrix_ic_metric(self):
        """IC 指标在 [-1, 1]"""
        from backtest.state_conditioned_performance import StateConditionedAnalyzer
        fr, sd, rl, fwd = make_e8_data()
        analyzer = StateConditionedAnalyzer(enable=True, min_obs_per_cell=30)
        analyzer.fit(fr, sd, rl, fwd)
        matrix = analyzer.compute_performance_matrix(metric='ic')
        valid = matrix.dropna()
        for val in valid.values.flatten():
            assert -1.0 <= val <= 1.0, f"IC {val} not in [-1, 1]"

    def test_04_compute_performance_matrix_min_obs(self):
        """观测不足的格为 NaN"""
        from backtest.state_conditioned_performance import StateConditionedAnalyzer
        fr, sd, rl, fwd = make_e8_data()
        # Set min_obs_per_cell higher than any regime's count
        analyzer = StateConditionedAnalyzer(enable=True, min_obs_per_cell=10000)
        analyzer.fit(fr, sd, rl, fwd)
        matrix = analyzer.compute_performance_matrix(metric='ic')
        # All cells should be NaN since min_obs is too high
        assert matrix.isna().all().all()

    def test_05_factor_return_regression_fields(self):
        """R_factor 回归含必要字段: alpha/betas/r_squared"""
        from backtest.state_conditioned_performance import StateConditionedAnalyzer
        fr, sd, rl, fwd = make_e8_data()
        analyzer = StateConditionedAnalyzer(enable=True, min_obs_per_cell=30)
        analyzer.fit(fr, sd, rl, fwd)
        result = analyzer.factor_return_regression('factor_1')
        assert isinstance(result, dict)
        assert 'alpha' in result
        assert 'betas' in result
        assert 'r_squared' in result
        assert 'alpha_pvalue' in result
        assert 'n_observations' in result

    def test_06_ic_on_state_regression_fields(self):
        """IC 回归含必要字段: alpha_ic/gammas/r_squared"""
        from backtest.state_conditioned_performance import StateConditionedAnalyzer
        fr, sd, rl, fwd = make_e8_data()
        analyzer = StateConditionedAnalyzer(enable=True, min_obs_per_cell=30)
        analyzer.fit(fr, sd, rl, fwd)
        result = analyzer.ic_on_state_regression('factor_1')
        assert isinstance(result, dict)
        assert 'alpha_ic' in result
        assert 'gammas' in result
        assert 'r_squared' in result
        assert 'n_observations' in result

    def test_07_newey_west_lags_applied(self):
        """Newey-West 滞后应用"""
        from backtest.state_conditioned_performance import StateConditionedAnalyzer
        fr, sd, rl, fwd = make_e8_data()
        analyzer = StateConditionedAnalyzer(enable=True, min_obs_per_cell=30, n_lags=5)
        analyzer.fit(fr, sd, rl, fwd)
        result = analyzer.factor_return_regression('factor_1')
        assert result.get('n_lags') == 5

    def test_08_test_all_factors_returns_dict(self):
        """test_all_factors 返回字典"""
        from backtest.state_conditioned_performance import StateConditionedAnalyzer
        fr, sd, rl, fwd = make_e8_data()
        analyzer = StateConditionedAnalyzer(enable=True, min_obs_per_cell=30)
        analyzer.fit(fr, sd, rl, fwd)
        results = analyzer.test_all_factors()
        assert isinstance(results, dict)
        # Each factor should have both tracks
        for fname in ['factor_1', 'factor_2']:
            assert fname in results
            assert 'R_factor_on_state' in results[fname]
            assert 'IC_on_state' in results[fname]

    def test_09_bh_fdr_correction_applied(self):
        """BH-FDR 校正应用"""
        from backtest.state_conditioned_performance import StateConditionedAnalyzer
        fr, sd, rl, fwd = make_e8_data()
        analyzer = StateConditionedAnalyzer(
            enable=True, min_obs_per_cell=30,
            correction='benjamini_hochberg',
        )
        analyzer.fit(fr, sd, rl, fwd)
        results = analyzer.test_all_factors()
        assert '_global_correction' in results
        gc = results['_global_correction']
        assert gc['method'] == 'benjamini_hochberg'
        assert gc['n_tests'] > 0

    def test_10_get_diagnostics_fields(self):
        """诊断含 n_factors/n_state_variables"""
        from backtest.state_conditioned_performance import StateConditionedAnalyzer
        fr, sd, rl, fwd = make_e8_data()
        analyzer = StateConditionedAnalyzer(enable=True, min_obs_per_cell=30)
        analyzer.fit(fr, sd, rl, fwd)
        diag = analyzer.get_diagnostics()
        assert isinstance(diag, dict)
        assert 'n_factors' in diag
        assert 'n_state_variables' in diag
        assert 'n_regimes' in diag
        assert diag['n_factors'] == 2
        assert diag['n_state_variables'] == 12

    def test_11_disabled_no_op(self):
        """enable=False 时返回空"""
        from backtest.state_conditioned_performance import StateConditionedAnalyzer
        fr, sd, rl, fwd = make_e8_data()
        analyzer = StateConditionedAnalyzer(enable=False)
        analyzer.fit(fr, sd, rl, fwd)
        matrix = analyzer.compute_performance_matrix(metric='ic')
        assert matrix.empty
        diag = analyzer.get_diagnostics()
        assert diag['enabled'] is False

    def test_12_known_state_dependency(self):
        """构造已知状态依赖, beta 应显著非零"""
        from backtest.state_conditioned_performance import StateConditionedAnalyzer
        fr, sd, rl, fwd = make_state_dependent_data(n_obs=300, n_stocks=100)
        analyzer = StateConditionedAnalyzer(enable=True, min_obs_per_cell=30, n_lags=3)
        analyzer.fit(fr, sd, rl, fwd)
        result = analyzer.factor_return_regression('factor_dep')
        # market_turnover beta should be significant (p < 0.05)
        assert 'betas' in result
        assert 'market_turnover' in result['betas']
        beta = result['betas']['market_turnover']
        pval = result['beta_pvalues']['market_turnover']
        assert abs(beta) > 0.01, f"beta too small: {beta}"
        assert pval < 0.10, f"p-value not significant: {pval}"
