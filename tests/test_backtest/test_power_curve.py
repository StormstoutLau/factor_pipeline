# -*- coding: utf-8 -*-
"""PowerCurveAnalyzer 测试 (RESEARCH_NOTES E1)

Monte Carlo 检测力曲线分析器的 TDD 测试.

TDD Red 阶段: 测试先于实现. 这些测试在 PowerCurveAnalyzer 实现前应当全部失败
(ImportError 或 AttributeError).

学术依据:
- Cohen, J. (1988). "Statistical Power Analysis for the Behavioral Sciences."
- Benjamini, Y. & Hochberg, Y. (1995). "Controlling the False Discovery Rate."
- Bonferroni, C. E. (1936). "Teoria statistica delle classi e calcolo delle
  probabilità."
"""
import matplotlib

matplotlib.use("Agg")  # 非交互后端, 避免 display 问题
import matplotlib.figure as mfigure
import numpy as np
import pytest
from scipy import stats as sps

from backtest.multiple_testing import PowerCurveAnalyzer


# ============================================================
# 1. _simulate_p_values 内部方法
# ============================================================

class TestPowerCurveAnalyzer:
    """PowerCurveAnalyzer Monte Carlo 检测力曲线分析器"""

    # ------------------------------------------------------------
    # 1.1 _simulate_p_values
    # ------------------------------------------------------------
    def test_simulate_p_values_h0_only(self):
        """effect_size=0 时所有 p 值 ~ U(0, 1)

        验证点: KS 检验不拒绝均匀分布假设 (p > 0.05)
        """
        analyzer = PowerCurveAnalyzer(n_simulations=1, alpha=0.05, random_state=42)
        # true_alt_fraction=0 → 全部 H0; effect_size=0 不会进入 H1 分支
        p_vals, is_alt = analyzer._simulate_p_values(
            effect_size=0.0,
            n_samples=50,
            n_hypotheses=200,
            true_alt_fraction=0.0,
        )
        assert len(p_vals) == 200
        assert is_alt.sum() == 0
        # KS 检验 p 值均匀性
        ks_stat, ks_p = sps.kstest(p_vals, "uniform")
        assert ks_p > 0.05, f"H0 p 值非均匀: KS p={ks_p:.4f}"

    def test_simulate_p_values_h1_distribution(self):
        """effect_size=0.5 时 H1 组 p 值偏小

        验证点: H1 组 p 均值 < H0 组 p 均值
        """
        analyzer = PowerCurveAnalyzer(n_simulations=1, alpha=0.05, random_state=2024)
        p_vals, is_alt = analyzer._simulate_p_values(
            effect_size=0.5,
            n_samples=80,
            n_hypotheses=100,
            true_alt_fraction=0.5,
        )
        p_alt = p_vals[is_alt]
        p_null = p_vals[~is_alt]
        assert p_alt.mean() < p_null.mean(), (
            f"H1 组 p 均值 ({p_alt.mean():.4f}) 应小于 H0 组 ({p_null.mean():.4f})"
        )

    # ------------------------------------------------------------
    # 1.2 compute_power_curve
    # ------------------------------------------------------------
    def test_compute_power_curve_monotonicity(self):
        """检测力随 effect_size 单调递增 (允许数值噪声)"""
        analyzer = PowerCurveAnalyzer(n_simulations=200, alpha=0.05, random_state=7)
        effect_sizes = np.array([0.0, 0.2, 0.4, 0.6, 0.8])
        power = analyzer.compute_power_curve(
            effect_sizes=effect_sizes,
            n_samples=80,
            n_hypotheses=50,
            true_alt_fraction=0.4,
            methods=["benjamini_hochberg"],
        )
        bh_power = power["benjamini_hochberg"]
        # 允许小幅数值噪声 (0.03); 整体趋势应单调非减
        for i in range(1, len(bh_power)):
            assert bh_power[i] >= bh_power[i - 1] - 0.03, (
                f"非单调: power[{i-1}]={bh_power[i-1]:.4f} > power[{i}]={bh_power[i]:.4f}"
            )

    def test_bonferroni_more_conservative_than_bh(self):
        """同参数下 Bonferroni 检测力 <= BH 检测力 (含容忍带)"""
        analyzer = PowerCurveAnalyzer(n_simulations=300, alpha=0.05, random_state=11)
        effect_sizes = np.array([0.3, 0.5, 0.7])
        power = analyzer.compute_power_curve(
            effect_sizes=effect_sizes,
            n_samples=80,
            n_hypotheses=50,
            true_alt_fraction=0.3,
            methods=["bonferroni", "benjamini_hochberg"],
        )
        # Bonferroni 不应明显高于 BH (容许 0.05 数值噪声)
        assert np.all(
            power["bonferroni"] <= power["benjamini_hochberg"] + 0.05
        ), (
            f"Bonferroni={power['bonferroni']}, BH={power['benjamini_hochberg']}"
        )

    def test_bh_fdr_control(self):
        """BH 经验 FDR <= alpha + 0.03 (Monte Carlo 误差容忍带)

        通过 compute_fdr_vs_power 同时获取 power + empirical FDR
        """
        analyzer = PowerCurveAnalyzer(n_simulations=400, alpha=0.05, random_state=99)
        effect_sizes = np.array([0.3])  # 中等效应, 既有真拒绝也有假拒绝
        result = analyzer.compute_fdr_vs_power(
            effect_sizes=effect_sizes,
            n_samples=80,
            n_hypotheses=60,
            true_alt_fraction=0.3,
            methods=["benjamini_hochberg"],
        )
        fdr_bh = result["fdr"]["benjamini_hochberg"][0]
        assert fdr_bh <= 0.05 + 0.03, f"BH FDR 失控: {fdr_bh:.4f} > 0.08"

    def test_bonferroni_fwer_control(self):
        """Bonferroni 经验 FWER <= alpha + 0.03

        FWER = P(至少一个 H0 被错误拒绝). 我们以 H0 全真场景验证.
        """
        analyzer = PowerCurveAnalyzer(n_simulations=400, alpha=0.05, random_state=33)
        # true_alt_fraction=0 → 全部 H0, 任何拒绝都是假拒绝
        # FWER = 至少一次拒绝的比例 ≈ 经验 FDR (n_true_null = n_hypotheses)
        effect_sizes = np.array([0.0])
        result = analyzer.compute_fdr_vs_power(
            effect_sizes=effect_sizes,
            n_samples=80,
            n_hypotheses=30,
            true_alt_fraction=0.0,
            methods=["bonferroni"],
        )
        # 全 H0 时, "FDR" (假拒绝/总拒绝) 在有拒绝时为 1, 无拒绝时为 0
        # 平均下来 ≈ 至少一次拒绝的频率 = FWER
        fwer_bonf = result["fdr"]["bonferroni"][0]
        assert fwer_bonf <= 0.05 + 0.03, f"Bonferroni FWER 失控: {fwer_bonf:.4f} > 0.08"

    def test_no_correction_highest_power(self):
        """无校正检测力最高: none_power >= bh_power >= bonf_power"""
        analyzer = PowerCurveAnalyzer(n_simulations=300, alpha=0.05, random_state=55)
        effect_sizes = np.array([0.4, 0.6])
        power = analyzer.compute_power_curve(
            effect_sizes=effect_sizes,
            n_samples=80,
            n_hypotheses=40,
            true_alt_fraction=0.4,
            methods=["none", "benjamini_hochberg", "bonferroni"],
        )
        for i in range(len(effect_sizes)):
            none_p = power["none"][i]
            bh_p = power["benjamini_hochberg"][i]
            bonf_p = power["bonferroni"][i]
            # 允许 0.05 数值噪声
            assert none_p + 0.05 >= bh_p, (
                f"none ({none_p:.4f}) < BH ({bh_p:.4f}) at i={i}"
            )
            assert bh_p + 0.05 >= bonf_p, (
                f"BH ({bh_p:.4f}) < Bonferroni ({bonf_p:.4f}) at i={i}"
            )

    def test_random_state_reproducibility(self):
        """相同 random_state 两次运行结果一致"""
        a1 = PowerCurveAnalyzer(n_simulations=100, alpha=0.05, random_state=123)
        a2 = PowerCurveAnalyzer(n_simulations=100, alpha=0.05, random_state=123)
        effect_sizes = np.array([0.2, 0.5, 0.8])
        r1 = a1.compute_power_curve(
            effect_sizes=effect_sizes,
            n_samples=60,
            n_hypotheses=40,
            true_alt_fraction=0.3,
            methods=["benjamini_hochberg", "bonferroni", "none"],
        )
        r2 = a2.compute_power_curve(
            effect_sizes=effect_sizes,
            n_samples=60,
            n_hypotheses=40,
            true_alt_fraction=0.3,
            methods=["benjamini_hochberg", "bonferroni", "none"],
        )
        for m in r1:
            np.testing.assert_allclose(r1[m], r2[m], err_msg=f"方法 {m} 不可复现")

    # ------------------------------------------------------------
    # 1.3 plot_power_curve
    # ------------------------------------------------------------
    def test_plot_power_curve_returns_figure(self):
        """plot_power_curve 返回 matplotlib.figure.Figure 对象"""
        analyzer = PowerCurveAnalyzer(n_simulations=50, alpha=0.05, random_state=8)
        effect_sizes = np.array([0.0, 0.3, 0.6, 1.0])
        power = analyzer.compute_power_curve(
            effect_sizes=effect_sizes,
            n_samples=60,
            n_hypotheses=30,
            true_alt_fraction=0.3,
            methods=["benjamini_hochberg", "bonferroni", "none"],
        )
        fig = analyzer.plot_power_curve(power)
        assert isinstance(fig, mfigure.Figure), (
            f"期望 matplotlib.figure.Figure, 实际 {type(fig)}"
        )

    # ------------------------------------------------------------
    # 1.4 边界条件
    # ------------------------------------------------------------
    def test_edge_case_zero_true_alt(self):
        """true_alt_fraction=0 时无 H1, 检测力 ≈ 0"""
        analyzer = PowerCurveAnalyzer(n_simulations=200, alpha=0.05, random_state=2)
        effect_sizes = np.array([0.3, 0.6, 1.0])
        power = analyzer.compute_power_curve(
            effect_sizes=effect_sizes,
            n_samples=80,
            n_hypotheses=40,
            true_alt_fraction=0.0,
            methods=["benjamini_hochberg", "bonferroni", "none"],
        )
        for m, arr in power.items():
            # 全 H0 时, "真备择" 数 = 0, power 应为 0
            np.testing.assert_allclose(
                arr, 0.0, atol=1e-9, err_msg=f"true_alt_fraction=0 时 {m} power 应为 0"
            )

    def test_compute_fdr_vs_power_returns_both(self):
        """compute_fdr_vs_power 返回字典同时含 power 和 fdr 两个键"""
        analyzer = PowerCurveAnalyzer(n_simulations=50, alpha=0.05, random_state=4)
        effect_sizes = np.array([0.0, 0.5])
        result = analyzer.compute_fdr_vs_power(
            effect_sizes=effect_sizes,
            n_samples=60,
            n_hypotheses=30,
            true_alt_fraction=0.3,
            methods=["benjamini_hochberg"],
        )
        assert "power" in result
        assert "fdr" in result
        assert "benjamini_hochberg" in result["power"]
        assert "benjamini_hochberg" in result["fdr"]
        # power 与 fdr 形状一致
        np.testing.assert_array_equal(
            result["power"]["benjamini_hochberg"].shape,
            result["fdr"]["benjamini_hochberg"].shape,
        )
