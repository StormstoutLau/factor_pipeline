# -*- coding: utf-8 -*-
"""TDD Red: RESEARCH_NOTES E1 — PowerCurveAnalyzer 检测力曲线

规格: docs/EXECUTION_RESEARCH_NOTES.md §1.2.1-1.2.9

验收:
- Monte Carlo 模拟生成 p 值 (H0: U(0,1), H1: Welch t-test)
- 检测力曲线: Bonferroni < BH < none
- BH FDR 控制: 经验 FDR ≤ alpha + 0.03
- 可复现性: 相同 random_state 结果一致
"""
import pytest
import numpy as np
from backtest.multiple_testing import PowerCurveAnalyzer


class TestPowerCurveAnalyzer:
    """E1 PowerCurveAnalyzer TDD"""

    def test_simulate_p_values_h0_only(self):
        analyzer = PowerCurveAnalyzer(n_simulations=1000, random_state=42)
        p_vals, is_alt = analyzer._simulate_p_values(
            effect_size=0.0, n_samples=100, n_hypotheses=50, true_alt_fraction=0.0
        )
        assert len(p_vals) == 50
        assert is_alt.sum() == 0
        # H0 下 p 值应近似均匀
        from scipy import stats
        _, ks_p = stats.kstest(p_vals, 'uniform')
        assert ks_p > 0.01, f"KS p={ks_p:.4f}, H0 p值应近似均匀"

    def test_simulate_p_values_h1_biased(self):
        analyzer = PowerCurveAnalyzer(n_simulations=1000, random_state=42)
        p_vals, is_alt = analyzer._simulate_p_values(
            effect_size=0.5, n_samples=100, n_hypotheses=50, true_alt_fraction=0.5
        )
        n_true_alt = is_alt.sum()
        assert 0 < n_true_alt < 50
        p_h1 = p_vals[is_alt]
        p_h0 = p_vals[~is_alt]
        if len(p_h1) > 0 and len(p_h0) > 0:
            assert np.mean(p_h1) < np.mean(p_h0), (
                f"H1 组 p 均值 {np.mean(p_h1):.3f} 应小于 H0 组 {np.mean(p_h0):.3f}"
            )

    def test_compute_power_curve_monotonicity(self):
        analyzer = PowerCurveAnalyzer(n_simulations=200, random_state=42)
        effect_sizes = np.linspace(0.0, 0.8, 5)
        power = analyzer.compute_power_curve(
            effect_sizes=effect_sizes, n_samples=60, n_hypotheses=20,
            true_alt_fraction=0.3,
        )
        for method in ['benjamini_hochberg', 'bonferroni', 'none']:
            pwr = power[method]
            for i in range(len(pwr) - 1):
                assert pwr[i + 1] >= pwr[i] - 0.03, (
                    f"{method} [{i}]={pwr[i]:.3f} > [{i+1}]={pwr[i+1]:.3f} 应单调递增"
                )

    def test_bonferroni_more_conservative_than_bh(self):
        analyzer = PowerCurveAnalyzer(n_simulations=200, random_state=42)
        power = analyzer.compute_power_curve(
            effect_sizes=np.array([0.3, 0.5, 0.7]), n_samples=60,
            n_hypotheses=20, true_alt_fraction=0.3,
        )
        bonf = power['bonferroni']
        bh = power['benjamini_hochberg']
        for i in range(len(bonf)):
            assert bonf[i] <= bh[i] + 0.05, (
                f"Bonferroni[{i}]={bonf[i]:.3f} 应 ≤ BH[{i}]={bh[i]:.3f}"
            )

    def test_none_correction_highest_power(self):
        analyzer = PowerCurveAnalyzer(n_simulations=200, random_state=42)
        power = analyzer.compute_power_curve(
            effect_sizes=np.array([0.3, 0.6]), n_samples=60,
            n_hypotheses=20, true_alt_fraction=0.3,
        )
        for i in range(2):
            assert power['none'][i] >= power['benjamini_hochberg'][i] - 0.02, (
                f"none[{i}]={power['none'][i]:.3f} 应 ≥ BH[{i}]={power['benjamini_hochberg'][i]:.3f}"
            )
            assert power['benjamini_hochberg'][i] >= power['bonferroni'][i] - 0.02

    def test_bh_fdr_control(self):
        analyzer = PowerCurveAnalyzer(n_simulations=300, alpha=0.05, random_state=42)
        power = analyzer.compute_power_curve(
            effect_sizes=np.array([0.3]), n_samples=60, n_hypotheses=50,
            true_alt_fraction=0.3,
        )
        fdr_curves = analyzer._last_fdr_curves_
        fdr_bh = fdr_curves['benjamini_hochberg'][0]
        assert fdr_bh <= 0.05 + 0.03, f"BH 经验 FDR {fdr_bh:.3f} 应 ≤ 0.08"

    def test_random_state_reproducibility(self):
        power1 = PowerCurveAnalyzer(n_simulations=100, random_state=42).compute_power_curve(
            effect_sizes=np.array([0.3, 0.5]), n_samples=60, n_hypotheses=10,
            true_alt_fraction=0.3,
        )
        power2 = PowerCurveAnalyzer(n_simulations=100, random_state=42).compute_power_curve(
            effect_sizes=np.array([0.3, 0.5]), n_samples=60, n_hypotheses=10,
            true_alt_fraction=0.3,
        )
        for method in ['bonferroni', 'benjamini_hochberg', 'none']:
            assert np.allclose(power1[method], power2[method]), f"{method} 不可复现"

    def test_plot_power_curve_returns_figure(self):
        analyzer = PowerCurveAnalyzer(n_simulations=50, random_state=42)
        power = analyzer.compute_power_curve(
            effect_sizes=np.array([0.0, 0.3, 0.6]), n_samples=60,
            n_hypotheses=10, true_alt_fraction=0.3,
        )
        fig = analyzer.plot_power_curve(power)
        from matplotlib.figure import Figure
        assert isinstance(fig, Figure)

    def test_edge_case_zero_true_alt(self):
        analyzer = PowerCurveAnalyzer(n_simulations=100, random_state=42)
        power = analyzer.compute_power_curve(
            effect_sizes=np.array([0.1, 0.5]), n_samples=60, n_hypotheses=20,
            true_alt_fraction=0.0,
        )
        for method in power:
            assert power[method][0] <= 0.15, (
                f"{method} true_alt=0 时 power={power[method][0]:.3f} 应≈0"
            )

    def test_compute_fdr_vs_power(self):
        analyzer = PowerCurveAnalyzer(n_simulations=100, random_state=42)
        result = analyzer.compute_fdr_vs_power(
            effect_sizes=np.array([0.3]), n_samples=60, n_hypotheses=20,
            true_alt_fraction=0.3,
            methods=['bonferroni', 'benjamini_hochberg', 'none'],
        )
        assert 'power' in result
        assert 'fdr' in result
        for key in ['power', 'fdr']:
            for m in ['bonferroni', 'benjamini_hochberg', 'none']:
                assert m in result[key]
