# -*- coding: utf-8 -*-
"""O5: GroupedOrthogonalizer + TripleChainCoordinator — 手工数值校验

独立计算对比:
1. Grouped 组内 W vs SymmetricOrthogonalizer 直接 fit (精度 1e-10)
2. Grouped 组内正交化后 T^T T ≈ I (单期)
3. Grouped 组间相关性 vs 全局正交化后组间相关性 (组间保留更高)
4. 缓存 hash 一致性 (相同输入 → 相同 hash)
5. resolve_conflicts: 三策略手工验证
6. 数据流契约: shape 不一致抛错
7. TripleChain 端到端: fingerprints 与独立 Fingerprinter.extract 对比

运行:
    python -m pytest tests/manual/test_grouped_orthogonalizer_manual.py -v
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from factor_pipeline.modules.factor_orthogonalizer.grouped import (
    GroupedOrthogonalizer,
)
from factor_pipeline.modules.factor_orthogonalizer.triple_chain import (
    TripleChainCoordinator,
)
from factor_pipeline.modules.factor_orthogonalizer.core.symmetric import (
    SymmetricOrthogonalizer,
)
from factor_pipeline.modules.factor_orthogonalizer.utils.stacking import (
    stack_factors_cross_section,
)


# =============================================================================
# 辅助函数
# =============================================================================

def _make_factor_dict(names, N=50, T=10, seed=42):
    rng = np.random.default_rng(seed)
    idx = [f"s{i}" for i in range(N)]
    cols = pd.date_range("2024-01-01", periods=T, freq="D")
    return {
        name: pd.DataFrame(rng.standard_normal((N, T)), index=idx, columns=cols)
        for name in names
    }


def _make_collinear_group(names, rho=0.9, N=50, T=10, seed=42):
    """构造高度相关的同组因子"""
    rng = np.random.default_rng(seed)
    base = rng.standard_normal((N, T))
    idx = [f"s{i}" for i in range(N)]
    cols = pd.date_range("2024-01-01", periods=T, freq="D")
    return {
        name: pd.DataFrame(
            np.sqrt(rho) * base + np.sqrt(1 - rho) * rng.standard_normal((N, T)),
            index=idx, columns=cols,
        )
        for name in names
    }


# =============================================================================
# 1. Grouped 组内 W vs Symmetric 直接 fit
# =============================================================================

class TestGroupedWMatchesDirect:
    """组内 W 与 SymmetricOrthogonalizer 直接 fit 对比"""

    def test_group_w_matches_direct_fit(self):
        """单组 3 因子, Grouped.W_ == Symmetric.fit(F_stacked) (精度 1e-10)"""
        fd = _make_collinear_group(["v1", "v2", "v3"], rho=0.9, seed=42)
        groups = {"value": ["v1", "v2", "v3"]}
        grouped = GroupedOrthogonalizer(groups)
        grouped.fit(fd)

        # 独立 fit
        F_stacked, _, _, _ = stack_factors_cross_section(fd)
        orth_direct = SymmetricOrthogonalizer()
        orth_direct.fit(F_stacked)

        np.testing.assert_allclose(
            grouped.orthogonalizers_["value"].W_,
            orth_direct.W_,
            atol=1e-10,
        )

    def test_multi_group_w_independent(self):
        """多组各自独立估计 W (组间互不影响)"""
        fd_v = _make_collinear_group(["v1", "v2"], rho=0.95, seed=42)
        fd_m = _make_collinear_group(["m1", "m2"], rho=0.95, seed=99)
        fd = {**fd_v, **fd_m}

        groups = {"value": ["v1", "v2"], "momentum": ["m1", "m2"]}
        grouped = GroupedOrthogonalizer(groups)
        grouped.fit(fd)

        # 独立 fit value 组
        F_v, _, _, _ = stack_factors_cross_section(fd_v)
        orth_v = SymmetricOrthogonalizer()
        orth_v.fit(F_v)

        # 独立 fit momentum 组
        F_m, _, _, _ = stack_factors_cross_section(fd_m)
        orth_m = SymmetricOrthogonalizer()
        orth_m.fit(F_m)

        np.testing.assert_allclose(
            grouped.orthogonalizers_["value"].W_, orth_v.W_, atol=1e-10
        )
        np.testing.assert_allclose(
            grouped.orthogonalizers_["momentum"].W_, orth_m.W_, atol=1e-10
        )


# =============================================================================
# 2. Grouped 组内正交化后 T^T T ≈ I
# =============================================================================

class TestGroupedWithinOrthogonality:
    """组内正交化后 T^T T 接近单位阵"""

    def test_within_group_orthogonal_property(self):
        """组内正交化后, 全样本 T^T T 接近单位阵

        注: W 基于全样本估计, 应用到每期, 单期 T_t^T T_t 不严格 = I,
        但全样本 (N·T, K) 堆叠后 T^T T 应接近 I (Löwdin 性质)
        """
        fd = _make_collinear_group(["v1", "v2", "v3"], rho=0.9, seed=42)
        groups = {"value": ["v1", "v2", "v3"]}
        grouped = GroupedOrthogonalizer(groups)
        result = grouped.fit_transform(fd)

        # 全样本堆叠 (N·T, K)
        F_stacked, _, _, _ = stack_factors_cross_section(result)
        gram = F_stacked.T @ F_stacked  # (K, K)
        # 归一化 (除以 N·T)
        gram_norm = gram / F_stacked.shape[0]
        # 对角线应接近 1, off-diagonal 接近 0
        diag = np.diag(gram_norm)
        off_diag = gram_norm - np.diag(diag)
        # off-diagonal 应接近 0 (相对对角线)
        ratio = np.max(np.abs(off_diag)) / np.max(np.abs(diag))
        assert ratio < 1e-10, (
            f"全样本 off/diag = {ratio:.2e}, 应 < 1e-10 (Löwdin 性质)"
        )

    def test_within_group_correlation_reduced(self):
        """组内相关性显著降低"""
        fd = _make_collinear_group(["v1", "v2"], rho=0.9, seed=42)
        # 原始相关性
        corr_before = np.corrcoef(
            fd["v1"].values.flatten(), fd["v2"].values.flatten()
        )[0, 1]
        assert abs(corr_before) > 0.7, f"原始相关性应高, 实际 {corr_before:.3f}"

        groups = {"value": ["v1", "v2"]}
        grouped = GroupedOrthogonalizer(groups)
        result = grouped.fit_transform(fd)
        # 正交化后相关性
        corr_after = np.corrcoef(
            result["v1"].values.flatten(), result["v2"].values.flatten()
        )[0, 1]
        # 相关性应大幅降低
        assert abs(corr_after) < 0.2, (
            f"正交化后相关性 {corr_after:.3f} 应 < 0.2"
        )


# =============================================================================
# 3. Grouped 组间相关性 vs 全局正交化
# =============================================================================

class TestGroupedVsGlobal:
    """分组 vs 全局正交化: 组间相关性保留对比"""

    def test_between_group_corr_preserved_vs_global(self):
        """Grouped 组间相关性 > 全局正交化后组间相关性"""
        # 构造: value 和 momentum 强相关
        rng = np.random.default_rng(42)
        N, T = 100, 20
        base = rng.standard_normal((N, T))
        idx = [f"s{i}" for i in range(N)]
        cols = pd.date_range("2024-01-01", periods=T, freq="D")
        fd = {
            "v1": pd.DataFrame(0.9 * base + 0.1 * rng.standard_normal((N, T)),
                               index=idx, columns=cols),
            "m1": pd.DataFrame(0.9 * base + 0.1 * rng.standard_normal((N, T)),
                               index=idx, columns=cols),
            "v2": pd.DataFrame(0.7 * base + 0.3 * rng.standard_normal((N, T)),
                               index=idx, columns=cols),
            "m2": pd.DataFrame(0.7 * base + 0.3 * rng.standard_normal((N, T)),
                               index=idx, columns=cols),
        }

        # (a) Grouped: value=[v1,v2], momentum=[m1,m2]
        groups = {"value": ["v1", "v2"], "momentum": ["m1", "m2"]}
        grouped = GroupedOrthogonalizer(groups)
        result_grouped = grouped.fit_transform(fd)
        corr_grouped = abs(np.corrcoef(
            result_grouped["v1"].values.flatten(),
            result_grouped["m1"].values.flatten(),
        )[0, 1])

        # (b) 全局正交化: 4 个因子一起 fit
        F_stacked, _, _, _ = stack_factors_cross_section(fd)
        orth_global = SymmetricOrthogonalizer()
        orth_global.fit(F_stacked)
        # 应用到每期
        from factor_pipeline.modules.factor_orthogonalizer.cross_sectional import (
            CrossSectionalOrthogonalizer,
        )
        cs = CrossSectionalOrthogonalizer(orth_global)
        result_global = cs.transform(fd)
        corr_global = abs(np.corrcoef(
            result_global["v1"].values.flatten(),
            result_global["m1"].values.flatten(),
        )[0, 1])

        # Grouped 组间相关性应保留更高 (不强行正交)
        assert corr_grouped > corr_global, (
            f"Grouped 组间相关性 {corr_grouped:.3f} 应 > "
            f"全局正交化 {corr_global:.3f}"
        )


# =============================================================================
# 4. 缓存 hash 一致性
# =============================================================================

class TestCacheHashConsistency:
    """缓存 hash 一致性手工校验"""

    def test_same_input_same_hash(self):
        """相同输入 → 相同 hash"""
        fd = _make_factor_dict(["f1", "f2"], seed=42)
        fd2 = {k: v.copy() for k, v in fd.items()}
        h1 = TripleChainCoordinator._hash_factor_dict(fd)
        h2 = TripleChainCoordinator._hash_factor_dict(fd2)
        assert h1 == h2, f"相同输入应生成相同 hash: {h1} vs {h2}"

    def test_different_input_different_hash(self):
        """不同输入 → 不同 hash"""
        fd1 = _make_factor_dict(["f1", "f2"], seed=42)
        fd2 = _make_factor_dict(["f1", "f2"], seed=99)
        h1 = TripleChainCoordinator._hash_factor_dict(fd1)
        h2 = TripleChainCoordinator._hash_factor_dict(fd2)
        assert h1 != h2, f"不同输入应生成不同 hash: {h1} vs {h2}"

    def test_different_keys_different_hash(self):
        """不同 keys → 不同 hash"""
        fd1 = _make_factor_dict(["f1", "f2"], seed=42)
        fd2 = _make_factor_dict(["f1", "f3"], seed=42)  # 不同因子名
        h1 = TripleChainCoordinator._hash_factor_dict(fd1)
        h2 = TripleChainCoordinator._hash_factor_dict(fd2)
        assert h1 != h2

    def test_different_shape_different_hash(self):
        """不同 shape → 不同 hash"""
        fd1 = _make_factor_dict(["f1"], N=50, T=10, seed=42)
        fd2 = _make_factor_dict(["f1"], N=60, T=10, seed=42)  # 不同 N
        h1 = TripleChainCoordinator._hash_factor_dict(fd1)
        h2 = TripleChainCoordinator._hash_factor_dict(fd2)
        assert h1 != h2


# =============================================================================
# 5. resolve_conflicts 三策略手工验证
# =============================================================================

class TestResolveConflictsManual:
    """resolve_conflicts 三策略手工验证"""

    def _make_report(self, vrr_f1, sig_f1, ic_ratio_f1):
        """构造测试报告"""
        return {
            'fingerprints': {'f1': {}, 'f2': {}},
            'orthogonalization': {
                'method': 'symmetric',
                'diagnostics': {'vrr': {'f1': vrr_f1, 'f2': 1.0}},
            },
            'significance': {
                'f1': {
                    'is_significant': sig_f1,
                    'ic_change_ratio': ic_ratio_f1,
                },
                'f2': {
                    'is_significant': True,
                    'ic_change_ratio': -0.1,
                },
            },
        }

    def test_conservative_drop_on_any_unfavorable(self):
        """conservative: 任一不利则 drop"""
        # f1: 显著但 VRR 低 (冗余)
        report = self._make_report(vrr_f1=0.1, sig_f1=True, ic_ratio_f1=-0.1)
        recs = TripleChainCoordinator().resolve_conflicts(
            report, strategy='conservative'
        )
        assert recs['f1']['recommendation'] == 'drop'  # VRR 低 → drop
        assert recs['f2']['recommendation'] == 'keep'  # 全有利

    def test_aggressive_keep_on_any_favorable(self):
        """aggressive: 任一有利则 keep"""
        # f1: 显著但 VRR 低
        report = self._make_report(vrr_f1=0.1, sig_f1=True, ic_ratio_f1=-0.1)
        recs = TripleChainCoordinator().resolve_conflicts(
            report, strategy='aggressive'
        )
        # f1: is_significant=True → keep (即使 VRR 低)
        assert recs['f1']['recommendation'] == 'keep'

    def test_ic_priority_ignores_vrr(self):
        """ic_priority: 只看 IC"""
        # f1: VRR 极低 (强冗余) 但 IC 显著
        report = self._make_report(vrr_f1=0.05, sig_f1=True, ic_ratio_f1=-0.1)
        recs = TripleChainCoordinator().resolve_conflicts(
            report, strategy='ic_priority'
        )
        assert recs['f1']['recommendation'] == 'keep'

    def test_ic_priority_drops_insignificant(self):
        """ic_priority: IC 不显著 → drop (即使 VRR=1)"""
        # f1: VRR=1 (无冗余) 但 IC 不显著
        report = self._make_report(vrr_f1=1.0, sig_f1=False, ic_ratio_f1=0.0)
        recs = TripleChainCoordinator().resolve_conflicts(
            report, strategy='ic_priority'
        )
        assert recs['f1']['recommendation'] == 'drop'


# =============================================================================
# 6. 数据流契约: shape 不一致抛错
# =============================================================================

class TestDataFlowContract:
    """O5.6.1: 数据流契约校验"""

    def test_shape_mismatch_raises(self):
        """raw 和 processed shape 不一致抛 ValueError"""
        raw = _make_factor_dict(["f1", "f2"], N=50, T=10, seed=42)
        processed = _make_factor_dict(["f1", "f2"], N=60, T=10, seed=42)  # 不同 N
        coordinator = TripleChainCoordinator()
        with pytest.raises(ValueError, match="shape"):
            coordinator.full_diagnosis(raw, processed)

    def test_keys_mismatch_raises(self):
        """raw 和 processed keys 不一致抛 ValueError"""
        raw = _make_factor_dict(["f1", "f2"], seed=42)
        processed = _make_factor_dict(["f1", "f3"], seed=42)  # f3 != f2
        coordinator = TripleChainCoordinator()
        with pytest.raises(ValueError, match="keys"):
            coordinator.full_diagnosis(raw, processed)


# =============================================================================
# 7. TripleChain 端到端: fingerprints 独立计算对比
# =============================================================================

class TestTripleChainFingerprints:
    """TripleChain 端到端: fingerprints 与独立 Fingerprinter.extract 对比"""

    def test_fingerprints_match_independent_call(self):
        """TripleChain 调用的 fingerprints 与独立调用 Fingerprinter.extract 一致"""
        raw = _make_factor_dict(["f1", "f2"], seed=42)

        class SimpleFingerprinter:
            """简单 Fingerprinter: 返回 mean/std"""
            def extract(self, df):
                return {
                    'mean': float(df.values.mean()),
                    'std': float(df.values.std()),
                    'shape': df.shape,
                }

        fp = SimpleFingerprinter()
        coordinator = TripleChainCoordinator(fingerprinter=fp, cache_enabled=False)
        report = coordinator.full_diagnosis(raw, raw)

        # 独立调用
        expected_f1 = fp.extract(raw['f1'])
        expected_f2 = fp.extract(raw['f2'])

        np.testing.assert_allclose(
            report['fingerprints']['f1']['mean'],
            expected_f1['mean'],
            atol=1e-10,
        )
        np.testing.assert_allclose(
            report['fingerprints']['f2']['std'],
            expected_f2['std'],
            atol=1e-10,
        )
        assert report['fingerprints']['f1']['shape'] == expected_f1['shape']

    def test_cache_disabled_no_caching(self):
        """cache_enabled=False 时每次都重算"""
        raw = _make_factor_dict(["f1"], seed=42)
        call_count = [0]

        class CountingFP:
            def extract(self, df):
                call_count[0] += 1
                return {'mean': float(df.values.mean())}

        coordinator = TripleChainCoordinator(
            fingerprinter=CountingFP(), cache_enabled=False
        )
        coordinator.full_diagnosis(raw, raw)
        coordinator.full_diagnosis(raw, raw)
        # 缓存禁用, 应调用 2 次 (每次 1 个因子)
        assert call_count[0] == 2, (
            f"cache 禁用应每次重算, 实际调用 {call_count[0]} 次"
        )
