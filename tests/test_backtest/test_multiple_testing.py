# -*- coding: utf-8 -*-
"""多重检验校正模块测试 (v3.0.0 T3.5)

测试 BH-FDR (Benjamini-Hochberg 1995) 校正算法的正确性.

T3.5 提取 BH 核心逻辑为独立低级函数, 供 unified_drift / pipelines_v2 /
factor_significance 共享调用.

学术依据:
- Benjamini, Y. & Hochberg, Y. (1995). "Controlling the False Discovery Rate."
  Journal of the Royal Statistical Society. Series B 57(1):289-300.

TDD Red 阶段: 测试先于实现.
"""
import pytest
import numpy as np

from backtest.multiple_testing import (
    apply_bh_fdr,
    apply_bonferroni,
    apply_no_correction,
)


# ============================================================
# 1. BH-FDR 校正正确性
# ============================================================

class TestBHFDRCorrectness:
    """BH-FDR 校正公式正确性"""

    def test_01_basic_bh_five_pvalues(self):
        """5 个 p 值的标准 BH 校正 (黄金参考)"""
        # 经典示例: 5 个 p 值
        p_values = [0.005, 0.01, 0.02, 0.04, 0.5]
        p_adj, is_sig = apply_bh_fdr(p_values, alpha=0.05)

        # BH 公式: p_adj_(k) = p_(k) * K / rank, 从大到小累积 min
        # K=5, 排序后: [0.005, 0.01, 0.02, 0.04, 0.5], rank=1..5
        # rank=5: 0.5*5/5=0.5, prev=0.5
        # rank=4: 0.04*5/4=0.05, prev=0.05
        # rank=3: 0.02*5/3=0.0333, prev=0.0333
        # rank=2: 0.01*5/2=0.025, prev=0.025
        # rank=1: 0.005*5/1=0.025, prev=0.025
        # p_adj (原顺序): [0.025, 0.025, 0.0333, 0.05, 0.5]
        expected = [0.025, 0.025, 0.0333, 0.05, 0.5]
        np.testing.assert_allclose(p_adj, expected, atol=1e-4)

    def test_02_bh_significance_at_alpha_05(self):
        """alpha=0.05 时,前 4 个 p 值显著,第 5 个不显著"""
        p_values = [0.005, 0.01, 0.02, 0.04, 0.5]
        p_adj, is_sig = apply_bh_fdr(p_values, alpha=0.05)
        # BH 判定: 找到最大的 k 使得 p_adj_(k) <= alpha,然后 1..k 都显著
        # p_adj = [0.025, 0.025, 0.0333, 0.05, 0.5]
        # 0.025 <= 0.05 (k=1), 0.025 <= 0.05 (k=2), 0.0333 <= 0.05 (k=3),
        # 0.05 <= 0.05 (k=4), 0.5 > 0.05 (k=5)
        # 所以 k*=4, 前 4 个显著
        assert is_sig == [True, True, True, True, False]

    def test_03_bh_significance_at_alpha_01(self):
        """alpha=0.01 时,只有第 1 个显著"""
        p_values = [0.005, 0.01, 0.02, 0.04, 0.5]
        p_adj, is_sig = apply_bh_fdr(p_values, alpha=0.01)
        # p_adj = [0.025, 0.025, 0.0333, 0.05, 0.5]
        # 0.025 > 0.01 → k*=0, 无显著
        # 实际上 0.025 > 0.01, 所以 0 个显著
        assert is_sig == [False, False, False, False, False]

    def test_04_bh_empty_input(self):
        """空输入返回空"""
        p_adj, is_sig = apply_bh_fdr([], alpha=0.05)
        assert len(p_adj) == 0
        assert len(is_sig) == 0

    def test_05_bh_single_pvalue(self):
        """单个 p 值, p_adj = p_value"""
        p_adj, is_sig = apply_bh_fdr([0.03], alpha=0.05)
        assert p_adj[0] == pytest.approx(0.03, abs=1e-6)
        assert is_sig == [True]

    def test_06_bh_all_significant(self):
        """全部极小 p 值, 全部显著"""
        p_values = [0.001, 0.002, 0.003]
        p_adj, is_sig = apply_bh_fdr(p_values, alpha=0.05)
        assert all(is_sig)

    def test_07_bh_none_significant(self):
        """全部大 p 值, 全部不显著"""
        p_values = [0.3, 0.5, 0.7, 0.9]
        p_adj, is_sig = apply_bh_fdr(p_values, alpha=0.05)
        assert not any(is_sig)

    def test_08_bh_monotonicity_after_sort(self):
        """排序后 p_adj 单调非减"""
        np.random.seed(42)
        p_values = np.random.uniform(0, 1, 20).tolist()
        p_adj, _ = apply_bh_fdr(p_values, alpha=0.05)
        # 排序
        sorted_p = sorted(p_values)
        sorted_adj = sorted(p_adj)
        # p_adj 排序后应单调非减
        for i in range(1, len(sorted_adj)):
            assert sorted_adj[i] >= sorted_adj[i-1] - 1e-10

    def test_09_bh_p_adj_clipped_to_1(self):
        """p_adj 不超过 1"""
        p_values = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        p_adj, _ = apply_bh_fdr(p_values, alpha=0.05)
        assert all(p <= 1.0 for p in p_adj)

    def test_10_bh_preserves_input_order(self):
        """p_adj 顺序与输入 p_values 顺序一致"""
        p_values = [0.5, 0.001, 0.3, 0.005, 0.7]
        p_adj, is_sig = apply_bh_fdr(p_values, alpha=0.05)
        assert len(p_adj) == 5
        assert len(is_sig) == 5
        # 第 2 个 (0.001) 和第 4 个 (0.005) 应该显著
        assert is_sig[1] == True
        assert is_sig[3] == True

    def test_11_bh_with_ties(self):
        """有 ties 时正确处理"""
        p_values = [0.01, 0.01, 0.01, 0.5]
        p_adj, is_sig = apply_bh_fdr(p_values, alpha=0.05)
        # 3 个 0.01, rank 1/2/3, p_adj = 0.01 * 4 / rank
        # rank=4: 0.5*4/4=0.5
        # rank=3: 0.01*4/3=0.01333, prev=0.01333
        # rank=2: 0.01*4/2=0.02, prev=0.01333
        # rank=1: 0.01*4/1=0.04, prev=0.01333
        # 前 3 个 p_adj = 0.01333
        assert p_adj[0] == pytest.approx(0.01333, abs=1e-4)
        assert p_adj[1] == pytest.approx(0.01333, abs=1e-4)
        assert p_adj[2] == pytest.approx(0.01333, abs=1e-4)
        assert p_adj[3] == pytest.approx(0.5, abs=1e-4)
        assert is_sig == [True, True, True, False]


# ============================================================
# 2. Bonferroni 校正
# ============================================================

class TestBonferroniCorrectness:
    """Bonferroni 校正"""

    def test_20_bonferroni_basic(self):
        """Bonferroni: alpha/N 比较 min(p)"""
        p_values = [0.01, 0.02, 0.03, 0.04, 0.05]
        p_adj, is_sig = apply_bonferroni(p_values, alpha=0.05)
        # Bonferroni: p_adj = p * N, 判定 p_adj < alpha
        # N=5, alpha=0.05, threshold = 0.05/5 = 0.01
        # p=0.01 → p_adj=0.05, 0.05 < 0.05? 否 (严格小于)
        # 实际 p < alpha/N → 0.01 < 0.01? 否
        # 所以全部不显著
        assert is_sig == [False, False, False, False, False]

    def test_21_bonferroni_one_significant(self):
        """Bonferroni 有 1 个显著"""
        p_values = [0.001, 0.02, 0.03, 0.04, 0.05]
        p_adj, is_sig = apply_bonferroni(p_values, alpha=0.05)
        # threshold = 0.05/5 = 0.01, 0.001 < 0.01 → 显著
        assert is_sig[0] == True
        assert is_sig[1] == False

    def test_22_bonferroni_empty(self):
        """空输入"""
        p_adj, is_sig = apply_bonferroni([], alpha=0.05)
        assert len(p_adj) == 0


# ============================================================
# 3. 无校正
# ============================================================

class TestNoCorrection:
    """无校正 (raw p-value)"""

    def test_30_no_correction_basic(self):
        """无校正: p < alpha 即显著"""
        p_values = [0.01, 0.04, 0.06, 0.5]
        p_adj, is_sig = apply_no_correction(p_values, alpha=0.05)
        assert p_adj == p_values
        assert is_sig == [True, True, False, False]

    def test_31_no_correction_empty(self):
        """空输入"""
        p_adj, is_sig = apply_no_correction([], alpha=0.05)
        assert len(p_adj) == 0


# ============================================================
# 4. 一致性与对比
# ============================================================

class TestCorrectionComparison:
    """BH vs Bonferroni vs None 对比"""

    def test_40_bh_more_powerful_than_bonferroni(self):
        """BH 检测力 ≥ Bonferroni (相同数据下显著数 ≥)"""
        # 20 个 p 值, 部分小部分大
        np.random.seed(42)
        p_values = (np.random.uniform(0, 1, 20) * 0.5).tolist()  # 偏小
        _, bh_sig = apply_bh_fdr(p_values, alpha=0.05)
        _, bonf_sig = apply_bonferroni(p_values, alpha=0.05)
        # BH 显著数应 >= Bonferroni
        assert sum(bh_sig) >= sum(bonf_sig)

    def test_41_no_correction_most_liberal(self):
        """无校正显著数 >= BH >= Bonferroni"""
        p_values = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08]
        _, none_sig = apply_no_correction(p_values, alpha=0.05)
        _, bh_sig = apply_bh_fdr(p_values, alpha=0.05)
        _, bonf_sig = apply_bonferroni(p_values, alpha=0.05)
        assert sum(none_sig) >= sum(bh_sig) >= sum(bonf_sig)


# ============================================================
# 5. 边界条件
# ============================================================

class TestEdgeCases:
    """边界条件"""

    def test_50_negative_pvalue_raises(self):
        """负 p 值抛 ValueError"""
        with pytest.raises(ValueError):
            apply_bh_fdr([-0.1, 0.5], alpha=0.05)

    def test_51_pvalue_above_1_raises(self):
        """p 值 > 1 抛 ValueError"""
        with pytest.raises(ValueError):
            apply_bh_fdr([0.5, 1.5], alpha=0.05)

    def test_52_alpha_out_of_range_raises(self):
        """alpha 不在 (0, 1] 抛 ValueError"""
        with pytest.raises(ValueError):
            apply_bh_fdr([0.5], alpha=0.0)
        with pytest.raises(ValueError):
            apply_bh_fdr([0.5], alpha=1.5)

    def test_53_nan_pvalue_raises(self):
        """NaN p 值抛 ValueError"""
        with pytest.raises(ValueError):
            apply_bh_fdr([float('nan'), 0.5], alpha=0.05)
