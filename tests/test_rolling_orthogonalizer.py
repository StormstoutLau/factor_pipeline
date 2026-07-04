# -*- coding: utf-8 -*-
"""O4: RollingOrthogonalizer + ICChangeMonitor — TDD 测试

测试文件:
- RollingOrthogonalizer (滚动窗口正交化, 避免 look-ahead bias)
- ICChangeMonitor (正交化前后 IC 对比, 监控预测力损失)

学术依据:
- Rolling: 量化研究实践共识 (回测必须避免 look-ahead bias)
- IC Monitor: Spearman 秩相关 (截面 IC 标准定义)

测试组 (按 O4.5 + O4.11 深化):
1. Rolling 基础 (4): no_lookahead / min_obs_skip / window_slide / gram_incremental_update
2. O4.11.1 Gram 重置 (2): reset_restores_symmetry / reset_no_lookahead
3. O4.11.2 fit_from_gram 对称化 (1): asymmetric_input
4. O4.11.3 is_orthogonalized 标记 (1): marked_correctly
5. O4.11.5 NaN 处理 (1): nan_handled_not_propagated
6. IC 监控 (2): before_after / degradation_detected
"""
from __future__ import annotations

import numpy as np
import pytest

from factor_pipeline.modules.factor_orthogonalizer.rolling import (
    RollingOrthogonalizer,
)
from factor_pipeline.backtest.ic_monitor import ICChangeMonitor


# =============================================================================
# 辅助函数
# =============================================================================

def _make_panel(T=20, N=50, K=3, seed=42):
    """构造 (T, N, K) 因子面板"""
    rng = np.random.default_rng(seed)
    return rng.standard_normal((T, N, K))


def _make_panel_with_nan(T=20, N=50, K=3, seed=42, nan_ratio=0.1):
    """构造含 NaN 的因子面板"""
    rng = np.random.default_rng(seed)
    F = rng.standard_normal((T, N, K))
    mask = rng.random((T, N, K)) < nan_ratio
    F[mask] = np.nan
    return F


# =============================================================================
# 1. Rolling 基础
# =============================================================================

class TestRollingBasic:
    """RollingOrthogonalizer 基础测试"""

    def test_rolling_no_lookahead(self):
        """t 期 W 仅用 t-1 及之前数据 (无 look-ahead bias)"""
        F = _make_panel(T=20, N=50, K=3, seed=42)
        roller = RollingOrthogonalizer(
            window_size=10, method='symmetric', min_obs=3
        )
        result, is_orth = roller.fit_transform(F)

        # t=0 时 window 为空, 未正交化 (返回原值)
        np.testing.assert_allclose(result[0], F[0])
        assert is_orth[0] == False

        # t=1 时 window 有 1 期 (t=0), 不足 min_obs=3, 未正交化
        np.testing.assert_allclose(result[1], F[1])
        assert is_orth[1] == False

        # t=3 时 window 有 3 期 (t=0,1,2), 达到 min_obs, 已正交化
        # 正交化后 result[3] != F[3] (除非 W=I, 但随机数据 W≠I)
        assert is_orth[3] == True
        assert not np.allclose(result[3], F[3], atol=1e-10), (
            "t=3 应已正交化, result 不应等于原值"
        )

    def test_rolling_min_obs_skip(self):
        """样本不足时返回原值 (is_orthogonalized=False)"""
        F = _make_panel(T=10, N=30, K=2, seed=42)
        roller = RollingOrthogonalizer(
            window_size=5, method='symmetric', min_obs=60
        )
        result, is_orth = roller.fit_transform(F)

        # min_obs=60 > T=10, 所有期都未正交化
        for t in range(10):
            np.testing.assert_allclose(result[t], F[t])
            assert is_orth[t] == False

    def test_rolling_window_slide(self):
        """窗口滑动正确 (deque maxlen, 移除最旧)"""
        F = _make_panel(T=15, N=20, K=2, seed=42)
        roller = RollingOrthogonalizer(
            window_size=5, method='symmetric', min_obs=2
        )
        roller.fit_transform(F)

        # 处理完后 window_ 应有 window_size=5 期 (最后 5 期的 t-1)
        # 即 F[9], F[10], F[11], F[12], F[13] (t=14 时加入 F[13])
        assert len(roller.window_) == 5
        np.testing.assert_allclose(roller.window_[0], F[9])
        np.testing.assert_allclose(roller.window_[-1], F[13])

    def test_rolling_gram_incremental_update(self):
        """增量 Gram 更新正确 (与全量重新计算对比)"""
        F = _make_panel(T=10, N=30, K=3, seed=42)
        roller = RollingOrthogonalizer(
            window_size=5, method='symmetric', min_obs=2
        )
        roller.fit_transform(F)

        # 增量 G_ 应等于 window_ 中所有 F 的 Gram
        F_window = np.vstack(list(roller.window_))  # (5*30, 3)
        G_full = F_window.T @ F_window
        np.testing.assert_allclose(roller.G_, G_full, atol=1e-10)


# =============================================================================
# 2. O4.11.1 Gram 重置
# =============================================================================

class TestGramReset:
    """O4.11.1: 增量 Gram 数值漂移与定期重置"""

    def test_gram_reset_restores_symmetry(self):
        """滑动 1000 期后, 重置消除 G 的不对称"""
        # 构造大面板模拟长期滑动
        F = _make_panel(T=100, N=20, K=4, seed=42)
        roller = RollingOrthogonalizer(
            window_size=10, method='symmetric',
            min_obs=2, reset_interval=50
        )
        roller.fit_transform(F)

        # reset_interval=50, 100 期会触发 2 次重置
        # 重置后 G_ 应高度对称
        asymmetry = np.linalg.norm(roller.G_ - roller.G_.T)
        assert asymmetry < 1e-12, (
            f"重置后 G 对称性偏差 {asymmetry} 应 < 1e-12"
        )

    def test_gram_reset_no_lookahead(self):
        """重置只用 window_ 数据, 不引入未来信息"""
        F = _make_panel(T=20, N=15, K=2, seed=42)
        roller = RollingOrthogonalizer(
            window_size=5, method='symmetric',
            min_obs=2, reset_interval=10
        )
        roller.fit_transform(F)

        # 重置后 G_ 应等于 window_ 的全量 Gram (不含未来数据)
        F_window = np.vstack(list(roller.window_))
        G_expected = F_window.T @ F_window
        np.testing.assert_allclose(roller.G_, G_expected, atol=1e-10)


# =============================================================================
# 3. O4.11.2 fit_from_gram 对称化
# =============================================================================

class TestFitFromGramSymmetric:
    """O4.11.2: fit_from_gram 对不对称 G 的处理"""

    def test_fit_from_gram_with_asymmetric_input(self):
        """不对称 G (G[0,1] += 1e-10) 经对称化后 W 正确"""
        from factor_pipeline.modules.factor_orthogonalizer.core.symmetric import (
            SymmetricOrthogonalizer,
        )
        rng = np.random.default_rng(42)
        F = rng.standard_normal((50, 3))
        G = F.T @ F
        # 故意破坏对称性
        G[0, 1] += 1e-10
        assert G[0, 1] != G[1, 0]  # 确认不对称

        orth = SymmetricOrthogonalizer()
        orth.fit_from_gram(G)
        # W 应正确 (与对称输入一致)
        G_sym = (G + G.T) / 2
        orth_ref = SymmetricOrthogonalizer()
        orth_ref.fit_from_gram(G_sym)
        np.testing.assert_allclose(orth.W_, orth_ref.W_, atol=1e-12)


# =============================================================================
# 4. O4.11.3 is_orthogonalized 标记
# =============================================================================

class TestIsOrthogonalizedMark:
    """O4.11.3: is_orthogonalized 标记数组"""

    def test_is_orthogonalized_marked_correctly(self):
        """min_obs=60, 前 60 期 is_orth=False, 之后 True"""
        F = _make_panel(T=70, N=20, K=2, seed=42)
        roller = RollingOrthogonalizer(
            window_size=60, method='symmetric', min_obs=60
        )
        result, is_orth = roller.fit_transform(F)

        # 前 60 期 (t=0..59) window 不足 60, is_orth=False
        # t=60 时 window 有 60 期 (t=0..59), is_orth=True
        for t in range(60):
            assert is_orth[t] == False, f"t={t} 应未正交化"
        assert is_orth[60] == True, "t=60 应已正交化"
        assert is_orth[69] == True, "t=69 应已正交化"


# =============================================================================
# 5. O4.11.5 NaN 处理
# =============================================================================

class TestRollingNaN:
    """O4.11.5: 滚动窗口的 NaN 处理"""

    def test_rolling_nan_handled_not_propagated(self):
        """F_panel 含 10% NaN, G 无 NaN 传播"""
        F = _make_panel_with_nan(T=15, N=30, K=3, seed=42, nan_ratio=0.1)
        roller = RollingOrthogonalizer(
            window_size=5, method='symmetric', min_obs=2
        )
        result, is_orth = roller.fit_transform(F)

        # G_ 无 NaN (NaN 已被处理)
        assert not np.any(np.isnan(roller.G_)), "G_ 不应含 NaN"

        # result 中原始 NaN 行可保留或填 0, 但不应全 NaN
        for t in range(15):
            if is_orth[t]:
                # 已正交化期: NaN 行可能保留 NaN 或填 0
                nan_rows = np.any(np.isnan(result[t]), axis=1)
                # 不应整期全 NaN
                assert not np.all(nan_rows), f"t={t} 不应全 NaN"


# =============================================================================
# 6. IC 监控
# =============================================================================

class TestICMonitor:
    """ICChangeMonitor 测试"""

    def test_ic_monitor_before_after(self):
        """正交化前后 IC 计算正确 (与 scipy spearmanr 对比)"""
        from scipy.stats import spearmanr
        rng = np.random.default_rng(42)
        N = 100
        factor_before = rng.standard_normal(N)
        fwd_returns = 0.3 * factor_before + 0.1 * rng.standard_normal(N)
        # 正交化后因子 (模拟, 加噪声)
        factor_after = factor_before + 0.5 * rng.standard_normal(N)

        result = ICChangeMonitor.compare_ic(
            factor_before, factor_after, fwd_returns
        )

        # 与 scipy 直接计算对比
        ic_before_ref, _ = spearmanr(factor_before, fwd_returns)
        ic_after_ref, _ = spearmanr(factor_after, fwd_returns)

        np.testing.assert_allclose(
            result['ic_before'], ic_before_ref, atol=1e-10
        )
        np.testing.assert_allclose(
            result['ic_after'], ic_after_ref, atol=1e-10
        )
        # ic_change = ic_after - ic_before
        np.testing.assert_allclose(
            result['ic_change'], ic_after_ref - ic_before_ref, atol=1e-10
        )

    def test_ic_monitor_degradation_detected(self):
        """IC 下降 > 80% 时 is_degraded=True"""
        rng = np.random.default_rng(42)
        N = 200
        # before: 强因子 (IC ~ 0.5)
        factor_before = rng.standard_normal(N)
        fwd_returns = 0.5 * factor_before + 0.1 * rng.standard_normal(N)
        # after: 弱因子 (IC ~ 0.05, 下降 90%)
        factor_after = 0.1 * factor_before + rng.standard_normal(N)

        result = ICChangeMonitor.compare_ic(
            factor_before, factor_after, fwd_returns
        )
        assert result['is_degraded'] == True, (
            f"IC 下降 {abs(result['ic_change_ratio'])*100:.1f}% 应触发 is_degraded"
        )
        assert abs(result['ic_change_ratio']) > 0.8
