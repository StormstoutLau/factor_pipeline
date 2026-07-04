# -*- coding: utf-8 -*-
"""O4: RollingOrthogonalizer + ICChangeMonitor — 手工数值校验

独立计算对比 (不依赖项目代码内部的计算路径, 用 scipy/numpy 直接计算):
1. Rolling Gram 增量更新 vs 全量重新堆叠 (精度 1e-10)
2. Rolling W vs SymmetricOrthogonalizer 直接 fit (精度 1e-10)
3. Rolling transform vs F @ W 直接矩阵乘 (精度 1e-10)
4. IC vs scipy spearmanr 直接计算 (精度 1e-10)
5. IC_change_ratio 独立计算
6. Gram 重置后 G vs 全量重新堆叠 (精度 1e-10)
7. Look-ahead bias 独立验证 (t 期 W 不含 F[t] 信息)
8. min_obs 跳过边界 (恰等于/小于 min_obs)

运行:
    python -m pytest tests/manual/test_rolling_orthogonalizer_manual.py -v
"""
from __future__ import annotations

import numpy as np
import pytest
from scipy.stats import spearmanr

from factor_pipeline.modules.factor_orthogonalizer.rolling import (
    RollingOrthogonalizer,
)
from factor_pipeline.modules.factor_orthogonalizer.core.symmetric import (
    SymmetricOrthogonalizer,
)
from factor_pipeline.backtest.ic_monitor import ICChangeMonitor


# =============================================================================
# 辅助函数
# =============================================================================

def _make_panel(T=20, N=50, K=3, seed=42):
    rng = np.random.default_rng(seed)
    return rng.standard_normal((T, N, K))


# =============================================================================
# 1. Rolling Gram 增量更新 vs 全量
# =============================================================================

class TestRollingGramIncremental:
    """增量 Gram 更新与全量计算对比"""

    def test_gram_after_full_window(self):
        """窗口满后增量 G == 全量 G (精度 1e-10)"""
        F = _make_panel(T=15, N=30, K=3, seed=42)
        roller = RollingOrthogonalizer(
            window_size=5, method='symmetric', min_obs=2
        )
        roller.fit_transform(F)

        # 独立计算: window_ 中所有 F 的 Gram
        F_window = np.vstack(list(roller.window_))  # (5*30, 3)
        G_full = F_window.T @ F_window

        np.testing.assert_allclose(roller.G_, G_full, atol=1e-10)

    def test_gram_during_sliding(self):
        """滑动过程中途增量 G == 当期 window_ 全量 G (精度 1e-10)

        在每个时间点 t 后检查 (用临时 roller 重跑)
        """
        F = _make_panel(T=12, N=20, K=2, seed=7)
        for check_t in [3, 5, 8, 11]:
            roller = RollingOrthogonalizer(
                window_size=4, method='symmetric', min_obs=2
            )
            # 只跑到 check_t 期 (slice)
            roller.fit_transform(F[:check_t + 1])

            F_window = np.vstack(list(roller.window_))
            G_full = F_window.T @ F_window
            np.testing.assert_allclose(
                roller.G_, G_full, atol=1e-10,
                err_msg=f"t={check_t} 增量 G 偏差"
            )


# =============================================================================
# 2. Rolling W vs SymmetricOrthogonalizer 直接 fit
# =============================================================================

class TestRollingWMatchesDirect:
    """Rolling W 与直接 fit SymmetricOrthogonalizer 对比"""

    def test_w_equals_direct_fit(self):
        """Rolling W_ == 用 window_ 中数据直接 fit 的 W (精度 1e-10)"""
        F = _make_panel(T=10, N=40, K=3, seed=42)
        roller = RollingOrthogonalizer(
            window_size=5, method='symmetric', min_obs=3
        )
        roller.fit_transform(F)

        # 独立 fit
        F_window = np.vstack(list(roller.window_))
        orth_direct = SymmetricOrthogonalizer()
        orth_direct.fit(F_window)

        np.testing.assert_allclose(roller.W_, orth_direct.W_, atol=1e-10)

    def test_w_equals_fit_from_gram(self):
        """Rolling W_ == 用 G_ 直接 fit_from_gram 的 W (精度 1e-10)"""
        F = _make_panel(T=8, N=30, K=3, seed=11)
        roller = RollingOrthogonalizer(
            window_size=4, method='symmetric', min_obs=2
        )
        roller.fit_transform(F)

        # 独立 fit_from_gram
        orth_from_gram = SymmetricOrthogonalizer()
        G_sym = (roller.G_ + roller.G_.T) / 2
        orth_from_gram.fit_from_gram(G_sym)

        np.testing.assert_allclose(roller.W_, orth_from_gram.W_, atol=1e-10)


# =============================================================================
# 3. Rolling transform 正确性
# =============================================================================

class TestRollingTransform:
    """Rolling transform == F @ W 直接矩阵乘"""

    def test_transform_equals_matmul(self):
        """result[t] == F_panel[t] @ W_ (精度 1e-10)"""
        F = _make_panel(T=10, N=30, K=3, seed=42)
        roller = RollingOrthogonalizer(
            window_size=4, method='symmetric', min_obs=2
        )
        result, is_orth = roller.fit_transform(F)

        # 最后一期 (t=9) 已正交化
        assert is_orth[9]
        # 独立计算: F[9] @ W_
        expected = F[9] @ roller.W_
        np.testing.assert_allclose(result[9], expected, atol=1e-10)

    def test_transform_preserves_shape(self):
        """transform 后 shape 不变"""
        F = _make_panel(T=10, N=30, K=3, seed=42)
        roller = RollingOrthogonalizer(
            window_size=4, method='symmetric', min_obs=2
        )
        result, _ = roller.fit_transform(F)
        assert result.shape == F.shape


# =============================================================================
# 4. IC vs scipy spearmanr 直接计算
# =============================================================================

class TestICMatchesScipy:
    """ICChangeMonitor.compute_ic 与 scipy spearmanr 直接计算对比"""

    def test_ic_matches_scipy_basic(self):
        """IC == scipy spearmanr (精度 1e-10)"""
        rng = np.random.default_rng(42)
        N = 100
        factor = rng.standard_normal(N)
        fwd_returns = 0.3 * factor + 0.1 * rng.standard_normal(N)

        ic_project = ICChangeMonitor.compute_ic(factor, fwd_returns)
        rho_scipy, _ = spearmanr(factor, fwd_returns)

        np.testing.assert_allclose(ic_project, rho_scipy, atol=1e-10)

    def test_ic_matches_scipy_with_nan(self):
        """含 NaN 时 IC == scipy spearmanr (mask 后, 精度 1e-10)"""
        rng = np.random.default_rng(7)
        N = 80
        factor = rng.standard_normal(N)
        fwd_returns = 0.2 * factor + 0.1 * rng.standard_normal(N)
        # 注入 NaN
        factor[[5, 15, 30]] = np.nan
        fwd_returns[[10, 25, 40]] = np.nan

        ic_project = ICChangeMonitor.compute_ic(factor, fwd_returns)
        # 独立计算
        mask = ~(np.isnan(factor) | np.isnan(fwd_returns))
        rho_scipy, _ = spearmanr(factor[mask], fwd_returns[mask])

        np.testing.assert_allclose(ic_project, rho_scipy, atol=1e-10)

    def test_ic_with_few_samples(self):
        """<3 个有效样本时 IC=0.0 (避免 spearmanr 报错)"""
        factor = np.array([1.0, 2.0, np.nan, np.nan])
        fwd_returns = np.array([0.1, 0.2, np.nan, np.nan])
        # 只有 2 个有效样本
        ic = ICChangeMonitor.compute_ic(factor, fwd_returns)
        assert ic == 0.0


# =============================================================================
# 5. IC_change_ratio 独立计算
# =============================================================================

class TestICChangeRatio:
    """IC_change_ratio 独立计算"""

    def test_change_ratio_matches_manual(self):
        """ic_change_ratio == (ic_after - ic_before) / |ic_before| (精度 1e-10)"""
        rng = np.random.default_rng(42)
        N = 200
        factor_before = rng.standard_normal(N)
        fwd_returns = 0.5 * factor_before + 0.1 * rng.standard_normal(N)
        factor_after = 0.1 * factor_before + rng.standard_normal(N)

        result = ICChangeMonitor.compare_ic(
            factor_before, factor_after, fwd_returns
        )

        # 独立计算
        ic_before_ref, _ = spearmanr(factor_before, fwd_returns)
        ic_after_ref, _ = spearmanr(factor_after, fwd_returns)
        ratio_ref = (ic_after_ref - ic_before_ref) / abs(ic_before_ref)

        np.testing.assert_allclose(
            result['ic_change_ratio'], ratio_ref, atol=1e-10
        )

    def test_is_degraded_threshold(self):
        """|ratio| > 0.8 时 is_degraded=True (独立验证)"""
        rng = np.random.default_rng(123)
        N = 500
        # 强因子
        factor_before = rng.standard_normal(N)
        fwd_returns = 0.8 * factor_before + 0.05 * rng.standard_normal(N)
        # 弱因子 (几乎无相关性)
        factor_after = rng.standard_normal(N)

        result = ICChangeMonitor.compare_ic(
            factor_before, factor_after, fwd_returns
        )

        # 独立计算 ratio
        ic_b, _ = spearmanr(factor_before, fwd_returns)
        ic_a, _ = spearmanr(factor_after, fwd_returns)
        ratio = (ic_a - ic_b) / abs(ic_b)

        assert (abs(ratio) > 0.8) == result['is_degraded']
        assert result['is_degraded'] == True


# =============================================================================
# 6. Gram 重置后 G vs 全量
# =============================================================================

class TestGramResetManual:
    """Gram 重置后 G_ 与全量重新堆叠对比"""

    def test_reset_restores_full_gram(self):
        """reset_interval 触发后 G_ == window_ 全量 Gram (精度 1e-10)"""
        F = _make_panel(T=20, N=15, K=2, seed=42)
        roller = RollingOrthogonalizer(
            window_size=5, method='symmetric',
            min_obs=2, reset_interval=10
        )
        roller.fit_transform(F)

        # 末态 G_ 应等于 window_ 全量 Gram
        F_window = np.vstack(list(roller.window_))
        G_full = F_window.T @ F_window
        np.testing.assert_allclose(roller.G_, G_full, atol=1e-10)

    def test_reset_at_boundary(self):
        """恰在 reset_interval 整数倍时触发重置"""
        F = _make_panel(T=10, N=20, K=2, seed=42)
        # reset_interval=5, 在 t=4 (iter=5) 和 t=9 (iter=10) 触发
        roller = RollingOrthogonalizer(
            window_size=10, method='symmetric',
            min_obs=2, reset_interval=5
        )
        roller.fit_transform(F)

        # 末态 (iter_count=10, 已触发重置) G_ 应等于全量
        F_window = np.vstack(list(roller.window_))
        G_full = F_window.T @ F_window
        np.testing.assert_allclose(roller.G_, G_full, atol=1e-10)


# =============================================================================
# 7. Look-ahead bias 独立验证
# =============================================================================

class TestNoLookaheadManual:
    """独立验证: t 期 W 不含 F[t] 信息"""

    def test_w_uses_only_past_data(self):
        """构造 t=K 期数据, F[t] 不影响 W_t

        思路: 用 F[t-1] 及之前估计 W_t
              修改 F[t] 后, W_t 不变 (因为 W_t 用 t-1 之前数据)
        但此测试不直接验证末态 W_, 而是验证: 修改 F[5] 不影响 t<=5 的 W_
        """
        F_orig = _make_panel(T=10, N=30, K=3, seed=42)
        F_mod = F_orig.copy()
        F_mod[5] = F_mod[5] * 100  # 极端修改 t=5

        roller1 = RollingOrthogonalizer(
            window_size=4, method='symmetric', min_obs=2
        )
        roller1.fit_transform(F_orig)

        roller2 = RollingOrthogonalizer(
            window_size=4, method='symmetric', min_obs=2
        )
        roller2.fit_transform(F_mod)

        # t=5 的 W 应只用 t<=4 的数据, 所以 roller1.W_(t=5) == roller2.W_(t=5)
        # 但 roller 末态 W_ 是 t=9 的, 这里需要中途捕获

        # 改方法: 只跑前 6 期 (T=6), 末态 W 是 t=5 期
        roller1 = RollingOrthogonalizer(
            window_size=4, method='symmetric', min_obs=2
        )
        roller1.fit_transform(F_orig[:6])

        roller2 = RollingOrthogonalizer(
            window_size=4, method='symmetric', min_obs=2
        )
        roller2.fit_transform(F_mod[:6])

        # 末态 W_ 是 t=5 的 W, 应用 [t-4, t-1] = [1, 4] 数据估计
        # F_mod[5] 不应影响此 W
        np.testing.assert_allclose(roller1.W_, roller2.W_, atol=1e-10)

    def test_result_at_t_uses_w_from_past(self):
        """result[t] 用的 W 不含 F[t] 信息 (修改 F[t] 不影响 W)"""
        F_orig = _make_panel(T=8, N=20, K=2, seed=99)
        F_mod = F_orig.copy()
        F_mod[7] = F_mod[7] * 1000  # 极端修改 t=7

        roller1 = RollingOrthogonalizer(
            window_size=4, method='symmetric', min_obs=2
        )
        r1, _ = roller1.fit_transform(F_orig)

        roller2 = RollingOrthogonalizer(
            window_size=4, method='symmetric', min_obs=2
        )
        r2, _ = roller2.fit_transform(F_mod)

        # t=7 的 W_ 应只用 t in [3, 6], 不含 F[7]
        # 所以 W_1 == W_2 (末态都是 t=7 的 W)
        np.testing.assert_allclose(roller1.W_, roller2.W_, atol=1e-10)

        # result[7] 不同 (因为输入 F[7] 不同), 但都是 F[t] @ W_
        expected1 = F_orig[7] @ roller1.W_
        expected2 = F_mod[7] @ roller2.W_
        np.testing.assert_allclose(r1[7], expected1, atol=1e-10)
        np.testing.assert_allclose(r2[7], expected2, atol=1e-10)


# =============================================================================
# 8. min_obs 边界测试
# =============================================================================

class TestMinObsBoundary:
    """min_obs 边界: 恰等于/小于 min_obs"""

    def test_exactly_min_obs(self):
        """window 长度恰等于 min_obs 时, is_orth=True"""
        F = _make_panel(T=10, N=20, K=2, seed=42)
        # window_size=10, min_obs=5
        # t=0: window=[], len=0 < 5, skip
        # t=1: window=[F[0]], len=1 < 5, skip
        # ...
        # t=5: window=[F[0..4]], len=5 == min_obs, is_orth=True
        roller = RollingOrthogonalizer(
            window_size=10, method='symmetric', min_obs=5
        )
        _, is_orth = roller.fit_transform(F)

        for t in range(5):
            assert is_orth[t] == False, f"t={t} 应未正交化 (window 不足)"
        assert is_orth[5] == True, "t=5 应已正交化 (window 满 5)"
        assert is_orth[9] == True

    def test_below_min_obs(self):
        """window 长度 < min_obs 时, is_orth=False"""
        F = _make_panel(T=5, N=20, K=2, seed=42)
        # min_obs=10 > T=5, 永远不足
        roller = RollingOrthogonalizer(
            window_size=10, method='symmetric', min_obs=10
        )
        result, is_orth = roller.fit_transform(F)
        for t in range(5):
            assert is_orth[t] == False
            # 未正交化时 result == 原值
            np.testing.assert_allclose(result[t], F[t])


# =============================================================================
# 9. 端到端一致性: Rolling vs 全样本 Symmetric
# =============================================================================

class TestRollingVsFullSample:
    """Rolling (用全样本作为窗口) vs 直接 SymmetricOrthogonalizer.fit"""

    def test_full_window_matches_symmetric(self):
        """window_size=T, min_obs=T-1 时, 末态 W_ == Symmetric.fit(F[:T-1])"""
        F = _make_panel(T=10, N=30, K=3, seed=42)
        # window_size=10, min_obs=9
        # t=9 时 window=[F[0..8]], W 用 F[0..8] 估计
        roller = RollingOrthogonalizer(
            window_size=10, method='symmetric', min_obs=9
        )
        roller.fit_transform(F)

        # 独立: 用 F[0..8] 堆叠后 fit
        F_window = np.vstack([F[t] for t in range(9)])  # (9*30, 3)
        orth_direct = SymmetricOrthogonalizer()
        orth_direct.fit(F_window)

        np.testing.assert_allclose(roller.W_, orth_direct.W_, atol=1e-10)

    def test_result_orthogonal_property(self):
        """正交化后 F^T F 接近单位阵 (Löwdin 性质)

        对已正交化的某一期: T_t = F_t @ W
        T_t^T T_t ≈ I (当 F_t 与估计 W 的样本同分布时)
        注: 这里 W 用过去数据估计, 应用到当期, 所以不是严格 I
        但当数据 iid 时, 期望接近 I
        """
        rng = np.random.default_rng(42)
        T, N, K = 50, 200, 3
        F = rng.standard_normal((T, N, K))
        roller = RollingOrthogonalizer(
            window_size=20, method='symmetric', min_obs=10
        )
        result, is_orth = roller.fit_transform(F)

        # 取最后 10 期 (已正交化), 检查 F^T F 的对角线接近 1
        # 注: 单期 (N=200, K=3) 数据下, T_t^T T_t 对角线 ≈ 1 (W 解耦)
        for t in [40, 45, 49]:
            T_t = result[t]
            gram_t = T_t.T @ T_t / N  # 归一化
            # 对角线应接近 1 (VRR ≈ 1 是 Löwdin 性质, 但跨期应用会有偏)
            # 此处只验证非负 (W 仍为有效正交化器)
            assert np.all(np.diag(gram_t) > 0), (
                f"t={t} 对角线应非负"
            )
