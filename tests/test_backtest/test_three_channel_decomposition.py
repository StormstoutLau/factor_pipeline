# -*- coding: utf-8 -*-
"""ThreeChannelDecomposition 测试 (RESEARCH_NOTES E9 §3.1)

三通道分解: log|R_factor| ≈ log|IC| + log(σ_factor) + log(σ_R)

五个通道输出 (4 原始 + 4 对数 + 1 残差 = 9 序列):
  R_factor, IC, sigma_factor, sigma_R,
  log_R, log_IC, log_sigma_factor, log_sigma_R, log_residual

五种发散模式:
  A 一致 / B 放大 / C 仅 R (Moreira-Muir) / D 仅 IC (Lewellen-Nagel-Shanken) / E 符号翻转

异方差检验: White (1980).

TDD Red 阶段: 测试先于实现.
"""
import pytest
import numpy as np
import pandas as pd
from unittest.mock import patch


# ============================================================
# 辅助函数
# ============================================================

def make_e9_data(n_obs: int = 200, n_stocks: int = 100, seed: int = 42):
    """生成 E9 测试合成数据

    Returns:
        factor_returns: Dict[str, pd.DataFrame] — {factor_name: (N_stocks, T_dates)}
        fwd_returns: pd.DataFrame — (T, N_stocks) 前向收益
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range('2020-01-01', periods=n_obs, freq='B')
    stocks = [f'S{i:03d}' for i in range(n_stocks)]

    # Factor values: random cross-sectional
    f_vals = rng.normal(0, 1, (n_stocks, n_obs))
    factor_returns = {'factor_1': pd.DataFrame(f_vals, index=stocks, columns=dates)}

    # Forward returns: r = 0.3 * f + noise (IC > 0)
    fwd_vals = 0.3 * f_vals.T + rng.normal(0, 0.5, (n_obs, n_stocks))
    fwd_returns = pd.DataFrame(fwd_vals, index=dates, columns=stocks)

    return factor_returns, fwd_returns


def make_trending_channel_series(
    r_trend: float = 0.0,
    ic_trend: float = 0.0,
    sf_trend: float = 0.0,
    sr_trend: float = 0.0,
    n: int = 200,
    seed: int = 42,
):
    """构造带特定趋势的 (R, IC, σ_f, σ_R) 四通道序列

    用于测试发散模式分类逻辑. 各通道的归一化趋势由参数控制:
    - > 0.1 → 上升趋势 (up)
    - < -0.1 → 下降趋势 (down)
    - 其他 → 平稳 (flat)
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n, dtype=float)

    def _make_series(target_trend: float, base: float = 1.0):
        # target_trend is the desired normalized slope (slope / std)
        # Generate series with given slope and noise
        noise = rng.normal(0, 0.1, n)
        slope = target_trend * 0.1  # scale to get desired normalized trend
        series = base + slope * t + noise
        return pd.Series(series)

    r = _make_series(r_trend, base=0.05)
    ic = _make_series(ic_trend, base=0.3)
    sf = _make_series(sf_trend, base=1.0)
    sr = _make_series(sr_trend, base=1.0)
    return r, ic, sf, sr


# ============================================================
# TestThreeChannelDecomposition
# ============================================================

class TestThreeChannelDecomposition:
    """ThreeChannelDecomposition 测试 (RESEARCH_NOTES E9 §3.1.26)"""

    def test_01_fit_returns_self(self):
        """fit 返回 self"""
        from factor_pipeline.backtest.three_channel_decomposition import ThreeChannelDecomposition
        fr, fwd = make_e9_data()
        decomposer = ThreeChannelDecomposition(enable=True)
        result = decomposer.fit(fr, fwd)
        assert result is decomposer
        assert isinstance(result, ThreeChannelDecomposition)

    def test_02_compute_channel_series_length(self):
        """四通道序列长度一致"""
        from factor_pipeline.backtest.three_channel_decomposition import ThreeChannelDecomposition
        fr, fwd = make_e9_data()
        decomposer = ThreeChannelDecomposition(enable=True)
        decomposer.fit(fr, fwd)
        r, ic, sf, sr = decomposer._compute_channel_series('factor_1')
        assert len(r) == len(ic)
        assert len(ic) == len(sf)
        assert len(sf) == len(sr)
        assert len(r) > 0

    def test_03_decompose_returns_all_channels(self):
        """decompose 返回 9 个序列 (4 原始 + 4 对数 + 1 残差)"""
        from factor_pipeline.backtest.three_channel_decomposition import ThreeChannelDecomposition
        fr, fwd = make_e9_data()
        decomposer = ThreeChannelDecomposition(enable=True)
        decomposer.fit(fr, fwd)
        result = decomposer.decompose('factor_1')
        assert isinstance(result, dict)
        expected_keys = {
            'R_factor', 'IC', 'sigma_factor', 'sigma_R',
            'log_R', 'log_IC', 'log_sigma_factor', 'log_sigma_R',
            'log_residual',
        }
        assert set(result.keys()) == expected_keys

    def test_04_decompose_log_linearity(self):
        """log|R| = log|IC| + log(σ_f) + log(σ_R) + residual, 残差均值 ≈ 0

        用构造的精确乘法关系 R = IC * σ_f * σ_R 验证 log 线性化数学.
        """
        from factor_pipeline.backtest.three_channel_decomposition import ThreeChannelDecomposition
        fr, fwd = make_e9_data()
        decomposer = ThreeChannelDecomposition(enable=True)
        decomposer.fit(fr, fwd)
        # Construct channels with exact multiplicative relationship
        n = 200
        ic = pd.Series(np.linspace(0.2, 0.4, n))
        sf = pd.Series(np.linspace(0.8, 1.2, n))
        sr = pd.Series(np.linspace(0.5, 0.7, n))
        r = ic * sf * sr  # exact: |R| = |IC| * σ_f * σ_R
        with patch.object(
            decomposer, '_compute_channel_series', return_value=(r, ic, sf, sr),
        ):
            result = decomposer.decompose('factor_1')
        residual = result['log_residual']
        # log|R| - log|IC| - log(σ_f) - log(σ_R) should be ≈ 0
        assert abs(residual.mean()) < 0.1, f"residual mean {residual.mean()} too far from 0"

    def test_05_classify_pattern_A_consistent(self):
        """构造一致模式 (R↑, IC↑, σ_f↑, σ_R↑) → pattern A"""
        from factor_pipeline.backtest.three_channel_decomposition import ThreeChannelDecomposition
        fr, fwd = make_e9_data()
        decomposer = ThreeChannelDecomposition(enable=True)
        decomposer.fit(fr, fwd)
        # Patch channel series with all-up trends
        r, ic, sf, sr = make_trending_channel_series(
            r_trend=2.0, ic_trend=2.0, sf_trend=2.0, sr_trend=2.0,
        )
        with patch.object(
            decomposer, '_compute_channel_series', return_value=(r, ic, sf, sr),
        ):
            result = decomposer.classify_divergence_pattern('factor_1')
        assert result['pattern'] == 'A'

    def test_06_classify_pattern_B_amplified(self):
        """构造放大模式 (R↑, IC→, σ_f↑) → pattern B"""
        from factor_pipeline.backtest.three_channel_decomposition import ThreeChannelDecomposition
        fr, fwd = make_e9_data()
        decomposer = ThreeChannelDecomposition(enable=True)
        decomposer.fit(fr, fwd)
        r, ic, sf, sr = make_trending_channel_series(
            r_trend=2.0, ic_trend=0.0, sf_trend=2.0, sr_trend=0.0,
        )
        with patch.object(
            decomposer, '_compute_channel_series', return_value=(r, ic, sf, sr),
        ):
            result = decomposer.classify_divergence_pattern('factor_1')
        assert result['pattern'] == 'B'

    def test_07_classify_pattern_C_R_only(self):
        """构造仅 R 模式 (R↑, IC→, σ_f→, σ_R↑) → pattern C (Moreira-Muir)"""
        from factor_pipeline.backtest.three_channel_decomposition import ThreeChannelDecomposition
        fr, fwd = make_e9_data()
        decomposer = ThreeChannelDecomposition(enable=True)
        decomposer.fit(fr, fwd)
        r, ic, sf, sr = make_trending_channel_series(
            r_trend=2.0, ic_trend=0.0, sf_trend=0.0, sr_trend=2.0,
        )
        with patch.object(
            decomposer, '_compute_channel_series', return_value=(r, ic, sf, sr),
        ):
            result = decomposer.classify_divergence_pattern('factor_1')
        assert result['pattern'] == 'C'

    def test_08_classify_pattern_D_IC_only(self):
        """构造仅 IC 模式 (R→, IC↑, σ_f↓) → pattern D (Lewellen-Nagel-Shanken)"""
        from factor_pipeline.backtest.three_channel_decomposition import ThreeChannelDecomposition
        fr, fwd = make_e9_data()
        decomposer = ThreeChannelDecomposition(enable=True)
        decomposer.fit(fr, fwd)
        r, ic, sf, sr = make_trending_channel_series(
            r_trend=0.0, ic_trend=2.0, sf_trend=-2.0, sr_trend=0.0,
        )
        with patch.object(
            decomposer, '_compute_channel_series', return_value=(r, ic, sf, sr),
        ):
            result = decomposer.classify_divergence_pattern('factor_1')
        assert result['pattern'] == 'D'

    def test_09_classify_pattern_E_sign_flip(self):
        """构造符号翻转 (R↑, IC↓) → pattern E (Lewellen-Nagel)"""
        from factor_pipeline.backtest.three_channel_decomposition import ThreeChannelDecomposition
        fr, fwd = make_e9_data()
        decomposer = ThreeChannelDecomposition(enable=True)
        decomposer.fit(fr, fwd)
        r, ic, sf, sr = make_trending_channel_series(
            r_trend=2.0, ic_trend=-2.0, sf_trend=0.0, sr_trend=0.0,
        )
        with patch.object(
            decomposer, '_compute_channel_series', return_value=(r, ic, sf, sr),
        ):
            result = decomposer.classify_divergence_pattern('factor_1')
        assert result['pattern'] == 'E'

    def test_10_test_heteroskedasticity_returns_pvalue(self):
        """异方差检验返回 p 值 ∈ [0, 1]"""
        from factor_pipeline.backtest.three_channel_decomposition import ThreeChannelDecomposition
        fr, fwd = make_e9_data()
        decomposer = ThreeChannelDecomposition(enable=True)
        decomposer.fit(fr, fwd)
        result = decomposer.test_heteroskedasticity('factor_1')
        assert isinstance(result, dict)
        assert 'white_pvalue' in result
        assert 0.0 <= result['white_pvalue'] <= 1.0
        assert 'is_heteroskedastic' in result

    def test_11_get_diagnostics_fields(self):
        """诊断含 n_factors/n_decompositions"""
        from factor_pipeline.backtest.three_channel_decomposition import ThreeChannelDecomposition
        fr, fwd = make_e9_data()
        decomposer = ThreeChannelDecomposition(enable=True)
        decomposer.fit(fr, fwd)
        diag = decomposer.get_diagnostics()
        assert isinstance(diag, dict)
        assert 'n_factors' in diag
        assert 'n_decompositions' in diag
        assert 'heteroskedasticity_test' in diag

    def test_12_disabled_no_op(self):
        """enable=False 时 decompose 返回空"""
        from factor_pipeline.backtest.three_channel_decomposition import ThreeChannelDecomposition
        fr, fwd = make_e9_data()
        decomposer = ThreeChannelDecomposition(enable=False)
        decomposer.fit(fr, fwd)
        result = decomposer.decompose('factor_1')
        assert result == {} or result is None or len(result) == 0
        diag = decomposer.get_diagnostics()
        assert diag['enabled'] is False
