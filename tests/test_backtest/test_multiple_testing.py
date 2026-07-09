# -*- coding: utf-8 -*-
"""多重检验校正模块测试 (v3.0.0 T3.5)

测试 BH-FDR (Benjamini-Hochberg 1995) 校正算法的正确性.

T3.5 提取 BH 核心逻辑为独立低级函数, 供 unified_drift / pipelines_v2 /
factor_significance 共享调用.

学术依据:
- Benjamini, Y. & Hochberg, Y. (1995). "Controlling the False Discovery Rate."
  Journal of the Royal Statistical Society. Series B 57(1):289-300.

TDD Red 阶段: 测试先于实现.

E2 扩展 (RESEARCH_NOTES §1.4 第二块补强): Romano-Wolf (2005) k-FWER Bootstrap
E3 扩展 (RESEARCH_NOTES §1.4 第三块补强): White Reality Check + Hansen SPA
"""
import pytest
import numpy as np
import pandas as pd

from backtest.multiple_testing import (
    apply_bh_fdr,
    apply_bonferroni,
    apply_no_correction,
    apply_romano_wolf,
    _generate_bootstrap_p_values_for_ks,
    apply_white_reality_check,
    apply_hansen_spa,
    WhiteRealityCheck,
    HansenSPA,
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


# ============================================================
# 6. Romano-Wolf (2005) k-FWER Bootstrap 校正 (E2)
# ============================================================

class TestRomanoWolf:
    """Romano-Wolf (2005) k-FWER Bootstrap 校正

    学术依据: Romano & Wolf (2005) "Stepwise Multiple Testing as Formalized
    Data Snooping"

    关键性质:
    - k-FWER 控制: P(|{i ∈ I0: reject H_i}| ≥ k) ≤ α
    - k=1 时等价强 FWER 控制
    - Stepdown 比 single-step 更有检测力 (拒绝更多)
    - 通过 bootstrap 估计 p 值相依结构, 不依赖 PRDS 假设
    """

    def _generate_null_bootstrap(self, m, B, seed=0):
        """生成 H0 下的 bootstrap p 值矩阵 (B, m), 每行 i.i.d. U(0,1)"""
        rng = np.random.default_rng(seed)
        return rng.uniform(0.0, 1.0, size=(B, m))

    def test_romano_wolf_k1_fwer_control(self):
        """k=1 时 FWER ≤ α + 0.03 (Monte Carlo 误差容忍带)

        在 H0 全真下重复 1000 次实验, 经验 FWER ≤ 0.08
        """
        rng = np.random.default_rng(2024)
        m = 20
        B = 200
        n_trials = 300
        alpha = 0.05
        n_any_reject = 0
        for t in range(n_trials):
            # H0 全真: p 值 i.i.d. U(0,1)
            p_vals = rng.uniform(0.0, 1.0, size=m).tolist()
            # bootstrap 也在 H0 下 (i.i.d. U(0,1))
            boot_p = rng.uniform(0.0, 1.0, size=(B, m))
            _, rejected = apply_romano_wolf(
                p_vals, boot_p, alpha=alpha, k=1, method="stepdown"
            )
            if any(rejected):
                n_any_reject += 1
        fwer = n_any_reject / n_trials
        assert fwer <= alpha + 0.03, f"Romano-Wolf k=1 FWER 失控: {fwer:.4f} > 0.08"

    def test_romano_wolf_stepdown_more_powerful(self):
        """stepdown 拒绝数 >= single_step 拒绝数"""
        rng = np.random.default_rng(42)
        m = 50
        B = 500
        # 构造部分真实备择: 一半 p 值很小
        p_vals = np.concatenate([
            rng.uniform(0.0, 0.01, size=20),  # 强信号
            rng.uniform(0.0, 1.0, size=30),   # 噪声
        ]).tolist()
        # 打乱顺序避免位置偏置
        rng.shuffle(p_vals)
        boot_p = self._generate_null_bootstrap(m, B, seed=100)
        _, rej_stepdown = apply_romano_wolf(
            p_vals, boot_p, alpha=0.05, k=1, method="stepdown"
        )
        _, rej_single = apply_romano_wolf(
            p_vals, boot_p, alpha=0.05, k=1, method="single_step"
        )
        assert sum(rej_stepdown) >= sum(rej_single), (
            f"stepdown ({sum(rej_stepdown)}) < single_step ({sum(rej_single)})"
        )

    def test_romano_wolf_single_step(self):
        """single_step 模式可运行且返回正确长度"""
        m = 10
        B = 100
        p_vals = np.linspace(0.001, 0.5, m).tolist()
        boot_p = self._generate_null_bootstrap(m, B, seed=7)
        adj_p, rejected = apply_romano_wolf(
            p_vals, boot_p, alpha=0.05, k=1, method="single_step"
        )
        assert len(adj_p) == m
        assert len(rejected) == m
        # 调整后 p 值在 [0, 1]
        assert all(0.0 <= p <= 1.0 for p in adj_p)
        # 最小 p 值应被拒绝
        assert rejected[0] is True

    def test_romano_wolf_rejected_subset(self):
        """RW 拒绝数 ≤ 无校正拒绝数 (k=1 等价 FWER, 应比无校正更保守)"""
        rng = np.random.default_rng(33)
        m = 30
        B = 300
        p_vals = rng.uniform(0.0, 1.0, size=m).tolist()
        boot_p = self._generate_null_bootstrap(m, B, seed=200)
        _, rej_rw = apply_romano_wolf(
            p_vals, boot_p, alpha=0.05, k=1, method="stepdown"
        )
        n_rej_raw = sum(1 for p in p_vals if p < 0.05)
        assert sum(rej_rw) <= n_rej_raw, (
            f"RW ({sum(rej_rw)}) > raw ({n_rej_raw})"
        )

    def test_generate_bootstrap_p_values_shape(self):
        """_generate_bootstrap_p_values_for_ks 输出形状 = (n_bootstrap, K)"""
        rng = np.random.default_rng(11)
        n_hist, n_recent, K = 60, 40, 5
        hist_df = pd.DataFrame(
            rng.standard_normal((n_hist, K)), columns=[f"f{i}" for i in range(K)]
        )
        recent_df = pd.DataFrame(
            rng.standard_normal((n_recent, K)), columns=[f"f{i}" for i in range(K)]
        )
        n_boot = 50
        boot_p = _generate_bootstrap_p_values_for_ks(
            hist_df, recent_df, n_bootstrap=n_boot, random_state=2024
        )
        assert boot_p.shape == (n_boot, K), (
            f"期望 ({n_boot}, {K}), 实际 {boot_p.shape}"
        )
        # 所有 p 值在 [0, 1]
        assert np.all(boot_p >= 0.0) and np.all(boot_p <= 1.0)

    def test_romano_wolf_reproducibility(self):
        """相同 random_state 重新生成 bootstrap → 结果一致 (非纯函数恒真).

        加强: 原测试对相同输入调用两次确定性函数, 断言一致 (恒真).
        改为: 用相同 random_state 重新生成 bootstrap 矩阵, 验证随机种子可复现性.
        同时验证 k 参数确实影响结果 (非平凡).
        """
        rng = np.random.default_rng(55)
        m = 25
        B = 200
        p_vals = rng.uniform(0.0, 1.0, size=m).tolist()
        # 用相同 random_state 生成两次 bootstrap (验证种子可复现, 非函数确定性)
        boot_p1 = self._generate_null_bootstrap(m, B, seed=123)
        boot_p2 = self._generate_null_bootstrap(m, B, seed=123)
        adj1, rej1 = apply_romano_wolf(p_vals, boot_p1, alpha=0.05, k=1)
        adj2, rej2 = apply_romano_wolf(p_vals, boot_p2, alpha=0.05, k=1)
        np.testing.assert_allclose(adj1, adj2)
        assert rej1 == rej2
        # 非平凡: 不同 random_state 应产生不同 bootstrap (极大概率)
        boot_p_diff = self._generate_null_bootstrap(m, B, seed=999)
        adj_diff, _ = apply_romano_wolf(p_vals, boot_p_diff, alpha=0.05, k=1)
        # 不同 bootstrap 矩阵应产生不同调整 p 值 (验证测试非恒真)
        assert not np.allclose(adj1, adj_diff), (
            "不同 random_state 的 bootstrap 应产生不同结果, 否则测试恒真"
        )

    def test_romano_wolf_k3_more_permissive_than_k1(self):
        """k=3 比 k=1 更宽松 (允许更多假拒绝, 因此拒绝数 >= k=1)"""
        rng = np.random.default_rng(77)
        m = 50
        B = 300
        # 部分真备择
        p_vals = np.concatenate([
            rng.uniform(0.0, 0.01, size=15),
            rng.uniform(0.0, 1.0, size=35),
        ]).tolist()
        rng.shuffle(p_vals)
        boot_p = self._generate_null_bootstrap(m, B, seed=300)
        _, rej_k1 = apply_romano_wolf(p_vals, boot_p, alpha=0.05, k=1)
        _, rej_k3 = apply_romano_wolf(p_vals, boot_p, alpha=0.05, k=3)
        assert sum(rej_k3) >= sum(rej_k1), (
            f"k=3 ({sum(rej_k3)}) < k=1 ({sum(rej_k1)})"
        )


# ============================================================
# 7. White Reality Check (2000) — E3
# ============================================================

class TestWhiteRealityCheck:
    """White (2000) Reality Check — 策略回测 data snooping 校正

    学术依据: White (2000) "A Reality Check for Data Snooping"
    Bootstrap: Politis & Romano (1994) stationary bootstrap

    函数式接口: apply_white_reality_check(strategy_returns, benchmark_return, ...)
        返回 (p_value, is_significant)
    """

    def test_white_reality_check_null_rejected_correctly(self):
        """全部策略等价基准时 RC p > α (不拒绝 H0)"""
        rng = np.random.default_rng(2024)
        T, K = 200, 10
        # 所有策略与基准同分布 → 无真正优秀策略
        benchmark = rng.standard_normal(T)
        # 策略收益 = 基准 + 微小噪声 (均值 ≈ 0)
        noise = rng.standard_normal((T, K)) * 0.01
        strategy_returns = benchmark[:, None] + noise
        p_value, is_sig = apply_white_reality_check(
            strategy_returns, benchmark, n_bootstrap=300, alpha=0.05,
            block_size=5, random_state=42,
        )
        assert 0.0 <= p_value <= 1.0
        # H0 下应不显著 (允许数值噪声: p_value > 0.05 即可)
        assert p_value > 0.05, f"null 下 RC p_value={p_value:.4f} < 0.05, 误拒"
        assert is_sig is False

    def test_white_reality_check_superior_strategy(self):
        """存在真正优秀策略时 RC p < 0.20 (放宽, RC 较保守)"""
        rng = np.random.default_rng(2024)
        T, K = 300, 20
        benchmark = rng.standard_normal(T) * 0.1
        # 19 个策略 ≈ 基准, 1 个策略显著优于基准 (+0.05 持续超额)
        strategy_returns = np.zeros((T, K))
        for k in range(K - 1):
            strategy_returns[:, k] = benchmark + rng.standard_normal(T) * 0.01
        # 第 K 个: 持续超额
        strategy_returns[:, K - 1] = benchmark + 0.05 + rng.standard_normal(T) * 0.01
        p_value, is_sig = apply_white_reality_check(
            strategy_returns, benchmark, n_bootstrap=500, alpha=0.20,
            block_size=5, random_state=123,
        )
        # RC 以 max stat 校正, 较保守, 放宽到 0.20
        assert p_value < 0.20, (
            f"superior strategy 下 RC p_value={p_value:.4f} > 0.20, 检测力不足"
        )

    def test_white_reality_check_returns_tuple(self):
        """返回类型为 (float, bool)"""
        rng = np.random.default_rng(0)
        T, K = 100, 5
        benchmark = rng.standard_normal(T)
        strategy_returns = rng.standard_normal((T, K))
        result = apply_white_reality_check(
            strategy_returns, benchmark, n_bootstrap=50, random_state=0,
        )
        assert isinstance(result, tuple) and len(result) == 2
        p_value, is_sig = result
        assert isinstance(p_value, float)
        assert isinstance(is_sig, bool)


# ============================================================
# 8. Hansen SPA (2005) — E3
# ============================================================

class TestHansenSPA:
    """Hansen (2005) Superior Predictive Ability — White RC 的改进版

    学术依据: Hansen (2005) "A Test for Superior Predictive Ability"

    关键改进:
    - 重新中心化 (recentering): 剔除"太差"的模型, 避免拉高临界值
    - 阈值基于 Law of the Iterated Logarithm (LIL):
        若 √n f_bar_k / ω_k ≤ -√(2 log log n), 模型被判为"太差"
    - 三区域 partitioning: lower / consistent / upper p 值
    - SPA 比 White RC 更有检测力 (lower p-values for genuinely superior strategies)

    函数式接口: apply_hansen_spa(strategy_returns, benchmark_return, ...)
        返回 (p_value, is_significant) — p_value 为 consistent SPA p 值
    """

    def test_hansen_spa_null(self):
        """全部策略等价基准时 SPA p > α"""
        rng = np.random.default_rng(2024)
        T, K = 200, 10
        benchmark = rng.standard_normal(T)
        noise = rng.standard_normal((T, K)) * 0.01
        strategy_returns = benchmark[:, None] + noise
        p_value, is_sig = apply_hansen_spa(
            strategy_returns, benchmark, n_bootstrap=300, alpha=0.05,
            block_size=5, random_state=42,
        )
        assert 0.0 <= p_value <= 1.0
        assert p_value > 0.05, f"null 下 SPA p_value={p_value:.4f} < 0.05, 误拒"
        assert is_sig is False

    def test_hansen_spa_superior(self):
        """存在真正优秀策略时 SPA p ≤ White RC p (检测力优势)"""
        rng = np.random.default_rng(2024)
        T, K = 300, 20
        benchmark = rng.standard_normal(T) * 0.1
        strategy_returns = np.zeros((T, K))
        for k in range(K - 1):
            strategy_returns[:, k] = benchmark + rng.standard_normal(T) * 0.01
        strategy_returns[:, K - 1] = benchmark + 0.05 + rng.standard_normal(T) * 0.01
        p_spa, _ = apply_hansen_spa(
            strategy_returns, benchmark, n_bootstrap=500, alpha=0.05,
            block_size=5, random_state=123,
        )
        p_rc, _ = apply_white_reality_check(
            strategy_returns, benchmark, n_bootstrap=500, alpha=0.05,
            block_size=5, random_state=123,
        )
        # SPA p ≤ RC p + 容忍带 (Monte Carlo 噪声)
        assert p_spa <= p_rc + 0.10, (
            f"SPA p ({p_spa:.4f}) > RC p ({p_rc:.4f}) + 0.10, SPA 未体现检测力优势"
        )
        # 同时 SPA 应能识别出 superior (放宽到 0.20)
        assert p_spa < 0.20, f"superior 下 SPA p={p_spa:.4f} > 0.20"

    def test_hansen_spa_returns_tuple(self):
        """返回类型为 (float, bool)"""
        rng = np.random.default_rng(0)
        T, K = 100, 5
        benchmark = rng.standard_normal(T)
        strategy_returns = rng.standard_normal((T, K))
        result = apply_hansen_spa(
            strategy_returns, benchmark, n_bootstrap=50, random_state=0,
        )
        assert isinstance(result, tuple) and len(result) == 2
        p_value, is_sig = result
        assert isinstance(p_value, float)
        assert isinstance(is_sig, bool)


# ============================================================
# 9. Bootstrap block_size + 可复现性 — E3
# ============================================================

class TestBootstrapBlockSizeAndReproducibility:
    """E3: bootstrap 块大小自动估计 + 可复现性"""

    def test_bootstrap_block_size(self):
        """block_size=None 时按 T^(1/3) 自动估计, 块大小 ≥ 1"""
        rng = np.random.default_rng(0)
        T, K = 100, 5
        benchmark = rng.standard_normal(T)
        strategy_returns = rng.standard_normal((T, K))
        # 不传 block_size, 应自动估计 (内部用 max(1, int(T**(1/3))))
        p_value, _ = apply_white_reality_check(
            strategy_returns, benchmark, n_bootstrap=50, random_state=0,
        )
        assert 0.0 <= p_value <= 1.0
        # 自动估计的 block_size 应为 max(1, int(100**(1/3))) = max(1, 4) = 4
        # 这里只验证可运行且 p 值合法
        # 再测试 Hansen SPA 同样行为
        p_spa, _ = apply_hansen_spa(
            strategy_returns, benchmark, n_bootstrap=50, random_state=0,
        )
        assert 0.0 <= p_spa <= 1.0

    def test_reproducibility(self):
        """相同 random_state 两次调用结果一致"""
        rng = np.random.default_rng(0)
        T, K = 150, 8
        benchmark = rng.standard_normal(T)
        strategy_returns = rng.standard_normal((T, K))
        p1, sig1 = apply_white_reality_check(
            strategy_returns, benchmark, n_bootstrap=200, block_size=5, random_state=99,
        )
        p2, sig2 = apply_white_reality_check(
            strategy_returns, benchmark, n_bootstrap=200, block_size=5, random_state=99,
        )
        assert p1 == p2, f"White RC 不可复现: {p1} vs {p2}"
        assert sig1 == sig2

        s1, sig1s = apply_hansen_spa(
            strategy_returns, benchmark, n_bootstrap=200, block_size=5, random_state=99,
        )
        s2, sig2s = apply_hansen_spa(
            strategy_returns, benchmark, n_bootstrap=200, block_size=5, random_state=99,
        )
        assert s1 == s2, f"Hansen SPA 不可复现: {s1} vs {s2}"
        assert sig1s == sig2s


# ============================================================
# 10. E3 类接口: WhiteRealityCheck + HansenSPA
# RESEARCH_NOTES §1.4 第三块补强 (spec L566-569)
# ============================================================

class TestWhiteRealityCheckClass:
    """WhiteRealityCheck 类接口测试 (spec L566-567)

    类接口返回 Dict 含 7 字段:
        rc_p_value, rc_rejected, max_statistic, bootstrap_max_stats,
        individual_p_values, n_strategies, block_size
    """

    def test_wrc_class_interface(self):
        """类接口返回 Dict 含 7 个必要字段, 类型正确"""
        rng = np.random.default_rng(2024)
        T, K = 150, 8
        # 构造 returns_matrix: 第 0 列为基准, 其余 K 列为策略
        benchmark = rng.standard_normal(T)
        strategies = benchmark[:, None] + rng.standard_normal((T, K)) * 0.01
        returns_matrix = np.column_stack([benchmark, strategies])  # (T, K+1)

        wrc = WhiteRealityCheck(
            n_bootstrap=200, block_size=5, method='stationary', random_state=42,
        )
        result = wrc.test(returns_matrix, benchmark_index=0, alpha=0.05)

        # 验证返回 Dict 含 7 字段
        expected_keys = {
            'rc_p_value', 'rc_rejected', 'max_statistic',
            'bootstrap_max_stats', 'individual_p_values',
            'n_strategies', 'block_size',
        }
        assert set(result.keys()) == expected_keys, (
            f"字段不匹配: {set(result.keys())} != {expected_keys}"
        )
        # 类型验证
        assert isinstance(result['rc_p_value'], float)
        assert 0.0 <= result['rc_p_value'] <= 1.0
        assert isinstance(result['rc_rejected'], list)
        assert len(result['rc_rejected']) == K
        assert all(isinstance(r, bool) for r in result['rc_rejected'])
        assert isinstance(result['max_statistic'], float)
        assert isinstance(result['bootstrap_max_stats'], np.ndarray)
        assert len(result['bootstrap_max_stats']) == 200
        assert isinstance(result['individual_p_values'], list)
        assert len(result['individual_p_values']) == K
        assert result['n_strategies'] == K
        assert isinstance(result['block_size'], float)

    def test_wrc_individual_p_values(self):
        """individual_p_values 字段: 各策略单独 p 值在 [0, 1], 长度 = K"""
        rng = np.random.default_rng(7)
        T, K = 120, 6
        benchmark = rng.standard_normal(T)
        strategies = benchmark[:, None] + rng.standard_normal((T, K)) * 0.02
        returns_matrix = np.column_stack([benchmark, strategies])

        wrc = WhiteRealityCheck(
            n_bootstrap=150, block_size=4, random_state=11,
        )
        result = wrc.test(returns_matrix, benchmark_index=0)

        individual = result['individual_p_values']
        assert len(individual) == K
        for p in individual:
            assert isinstance(p, float)
            assert 0.0 <= p <= 1.0, f"individual p 值越界: {p}"

    def test_wrc_class_reproducibility(self):
        """相同 random_state 的类实例结果一致"""
        rng = np.random.default_rng(0)
        T, K = 100, 5
        returns_matrix = rng.standard_normal((T, K + 1))

        wrc1 = WhiteRealityCheck(n_bootstrap=100, block_size=5, random_state=77)
        wrc2 = WhiteRealityCheck(n_bootstrap=100, block_size=5, random_state=77)
        r1 = wrc1.test(returns_matrix, benchmark_index=0)
        r2 = wrc2.test(returns_matrix, benchmark_index=0)
        assert r1['rc_p_value'] == r2['rc_p_value']
        np.testing.assert_array_equal(
            r1['bootstrap_max_stats'], r2['bootstrap_max_stats']
        )


class TestHansenSPAClass:
    """HansenSPA 类接口测试 (spec L568-569)

    类接口返回 Dict 含 8 字段:
        spa_p_value, spa_lc_p_value, spa_uc_p_value, rejected,
        h1_set, h0_set, max_statistic, block_size
    """

    def test_spa_class_interface(self):
        """类接口返回 Dict 含 8 个必要字段, 类型正确"""
        rng = np.random.default_rng(2024)
        T, K = 150, 8
        benchmark = rng.standard_normal(T)
        strategies = benchmark[:, None] + rng.standard_normal((T, K)) * 0.01
        returns_matrix = np.column_stack([benchmark, strategies])

        spa = HansenSPA(
            n_bootstrap=200, block_size=5, method='stationary', random_state=42,
        )
        result = spa.test(returns_matrix, benchmark_index=0, alpha=0.05)

        # 验证返回 Dict 含 8 字段
        expected_keys = {
            'spa_p_value', 'spa_lc_p_value', 'spa_uc_p_value', 'rejected',
            'h1_set', 'h0_set', 'max_statistic', 'block_size',
        }
        assert set(result.keys()) == expected_keys, (
            f"字段不匹配: {set(result.keys())} != {expected_keys}"
        )
        # 类型验证
        assert isinstance(result['spa_p_value'], float)
        assert isinstance(result['spa_lc_p_value'], float)
        assert isinstance(result['spa_uc_p_value'], float)
        assert 0.0 <= result['spa_p_value'] <= 1.0
        assert 0.0 <= result['spa_lc_p_value'] <= 1.0
        assert 0.0 <= result['spa_uc_p_value'] <= 1.0
        assert isinstance(result['rejected'], list)
        assert len(result['rejected']) == K
        assert isinstance(result['h1_set'], list)
        assert isinstance(result['h0_set'], list)
        assert isinstance(result['max_statistic'], float)
        assert isinstance(result['block_size'], float)

    def test_spa_h1_h0_separation(self):
        """h1_set 与 h0_set 互斥且并集 = 全部策略索引"""
        rng = np.random.default_rng(2024)
        T, K = 300, 20
        benchmark = rng.standard_normal(T) * 0.1
        strategies = np.zeros((T, K))
        # 19 个策略 ≈ 基准 (可能进入 H1 或 H0 边界)
        for k in range(K - 1):
            strategies[:, k] = benchmark + rng.standard_normal(T) * 0.01
        # 第 K 个策略: 显著劣于基准 (太差 → 应进入 H0)
        strategies[:, K - 1] = benchmark - 0.5 + rng.standard_normal(T) * 0.01
        returns_matrix = np.column_stack([benchmark, strategies])

        spa = HansenSPA(n_bootstrap=200, block_size=5, random_state=42)
        result = spa.test(returns_matrix, benchmark_index=0)

        h1 = set(result['h1_set'])
        h0 = set(result['h0_set'])
        # 互斥
        assert h1.isdisjoint(h0), f"h1 与 h0 有重叠: h1={h1}, h0={h0}"
        # 并集 = 全部策略索引 {0, 1, ..., K-1}
        assert h1 | h0 == set(range(K)), (
            f"h1 ∪ h0 ≠ 全集: h1={h1}, h0={h0}, K={K}"
        )
        # 显著劣于基准的策略应进入 H0 (太差集合)
        assert (K - 1) in h0, (
            f"显著劣于基准的策略 {K - 1} 应在 h0_set 中, h0={h0}"
        )

    def test_spa_lc_uc_consistency(self):
        """单调性: p_lc ≥ p ≥ p_uc (lower 最保守, upper 最宽松)"""
        rng = np.random.default_rng(2024)
        T, K = 300, 20
        benchmark = rng.standard_normal(T) * 0.1
        strategies = np.zeros((T, K))
        for k in range(K - 1):
            strategies[:, k] = benchmark + rng.standard_normal(T) * 0.01
        # 一个显著优于基准的策略
        strategies[:, K - 1] = benchmark + 0.05 + rng.standard_normal(T) * 0.01
        returns_matrix = np.column_stack([benchmark, strategies])

        spa = HansenSPA(n_bootstrap=300, block_size=5, random_state=123)
        result = spa.test(returns_matrix, benchmark_index=0)

        p = result['spa_p_value']
        p_lc = result['spa_lc_p_value']
        p_uc = result['spa_uc_p_value']
        assert p_lc >= p - 1e-9, (
            f"单调性违反: p_lc ({p_lc:.4f}) < p ({p:.4f})"
        )
        assert p >= p_uc - 1e-9, (
            f"单调性违反: p ({p:.4f}) < p_uc ({p_uc:.4f})"
        )

    def test_spa_more_powerful_than_wrc_class(self):
        """类接口: SPA p ≤ White RC p (检测力优势)"""
        rng = np.random.default_rng(2024)
        T, K = 300, 20
        benchmark = rng.standard_normal(T) * 0.1
        strategies = np.zeros((T, K))
        for k in range(K - 1):
            strategies[:, k] = benchmark + rng.standard_normal(T) * 0.01
        strategies[:, K - 1] = benchmark + 0.05 + rng.standard_normal(T) * 0.01
        returns_matrix = np.column_stack([benchmark, strategies])

        wrc = WhiteRealityCheck(n_bootstrap=300, block_size=5, random_state=123)
        spa = HansenSPA(n_bootstrap=300, block_size=5, random_state=123)
        r_wrc = wrc.test(returns_matrix, benchmark_index=0)
        r_spa = spa.test(returns_matrix, benchmark_index=0)
        # SPA p ≤ RC p + 容忍带 (Monte Carlo 噪声)
        assert r_spa['spa_p_value'] <= r_wrc['rc_p_value'] + 0.10, (
            f"SPA p ({r_spa['spa_p_value']:.4f}) > RC p ({r_wrc['rc_p_value']:.4f}) + 0.10"
        )


class TestBootstrapMethods:
    """bootstrap 方法测试: circular block bootstrap + auto block size (含 rho)"""

    def test_circular_block_bootstrap(self):
        """circular block bootstrap: 输出长度 = 输入长度, 值来自输入"""
        wrc = WhiteRealityCheck(n_bootstrap=10, block_size=5, random_state=42)
        T = 100
        x = np.arange(T, dtype=float)  # 0, 1, ..., 99
        boot = wrc._circular_block_bootstrap(x, block_size=7)
        # 长度保持
        assert len(boot) == T, f"长度不匹配: {len(boot)} != {T}"
        # 值来自输入 (索引环绕后取 x[idx], 值 ∈ {0, ..., 99})
        assert boot.min() >= 0 and boot.max() <= 99
        # 多次调用长度稳定
        for _ in range(5):
            b = wrc._circular_block_bootstrap(x, block_size=3)
            assert len(b) == T

    def test_circular_block_bootstrap_small_block(self):
        """circular block bootstrap: 块大小 1 时仍长度保持"""
        wrc = WhiteRealityCheck(n_bootstrap=10, random_state=1)
        x = np.linspace(0, 1, 50)
        boot = wrc._circular_block_bootstrap(x, block_size=1)
        assert len(boot) == 50

    def test_stationary_block_bootstrap_length(self):
        """stationary block bootstrap: 输出长度 = 输入长度"""
        wrc = WhiteRealityCheck(n_bootstrap=10, block_size=5, random_state=42)
        x = np.arange(80, dtype=float)
        boot = wrc._stationary_block_bootstrap(x, block_size=6.0)
        assert len(boot) == 80

    def test_auto_block_size_with_rho(self):
        """_auto_block_size 含 rho 公式: B = (2T)^(1/3) * rho^(2/3)"""
        wrc = WhiteRealityCheck(n_bootstrap=10, random_state=42)
        # 构造 AR(1) 序列: x[t] = rho_true * x[t-1] + noise, 含正自相关
        rng = np.random.default_rng(2024)
        T = 500
        rho_true = 0.8
        x = np.zeros(T)
        for t in range(1, T):
            x[t] = rho_true * x[t - 1] + rng.standard_normal() * 0.5

        B = wrc._auto_block_size(x)
        # 用样本自相关系数复算期望值
        rho_sample = float(np.corrcoef(x[:-1], x[1:])[0, 1])
        expected = float(np.ceil((2 * T) ** (1.0 / 3.0) * rho_sample ** (2.0 / 3.0)))
        assert B == expected, (
            f"auto_block_size 含 rho 公式不符: B={B}, expected={expected}, "
            f"rho_sample={rho_sample:.4f}"
        )
        # B >= 1
        assert B >= 1.0

    def test_auto_block_size_rho_nonpositive(self):
        """rho <= 0 时返回 2.0 (退化情况)"""
        wrc = WhiteRealityCheck(n_bootstrap=10, random_state=42)
        # 无自相关的白噪声 (样本 rho ≈ 0, 可能略负)
        rng = np.random.default_rng(0)
        x = rng.standard_normal(1000)
        # 多次尝试, 至少有一次 rho <= 0 返回 2.0
        results = []
        for seed in range(20):
            rng_i = np.random.default_rng(seed)
            xi = rng_i.standard_normal(500)
            results.append(wrc._auto_block_size(xi))
        # 退化情况返回 2.0
        assert 2.0 in results, "rho <= 0 时应返回 2.0"

    def test_method_circular_runs(self):
        """method='circular' 可正常运行并返回合法 p 值"""
        rng = np.random.default_rng(2024)
        T, K = 100, 5
        returns_matrix = rng.standard_normal((T, K + 1))
        wrc = WhiteRealityCheck(
            n_bootstrap=100, block_size=5, method='circular', random_state=42,
        )
        result = wrc.test(returns_matrix, benchmark_index=0)
        assert 0.0 <= result['rc_p_value'] <= 1.0

    def test_method_invalid_raises(self):
        """非法 method 抛出 ValueError"""
        with pytest.raises(ValueError, match="method"):
            WhiteRealityCheck(method='invalid')

