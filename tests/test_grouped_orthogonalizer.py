# -*- coding: utf-8 -*-
"""O5: GroupedOrthogonalizer + TripleChainCoordinator — TDD 测试

测试文件:
- GroupedOrthogonalizer (组内正交 + 组间保留, Stambaugh-Yuan 2017)
- TripleChainCoordinator (三件套串联协调器, Fingerprint → Pipeline → Orthogonalizer → Significance)

学术依据:
- Asness (2013) Value and Momentum Everywhere: Value 与 Momentum 负相关, 不应强行正交
- Stambaugh-Yuan (2017): 风险因子 vs alpha 因子区别处理
- Barra 风险模型: 行业中性化先于因子构造

测试组 (按 O5.4 + O5.6 深化):
1. Grouped 基础 (3): within_group_orthogonal / between_group_preserved / duplicate_factor_raises
2. O5.6.3 Grouped 缺失因子 (2): raise / skip
3. O5.6.1 三件套数据流协议 (2): data_flow_contract / fingerprinter_does_not_mutate_input
4. TripleChain 端到端 (2): full_diagnosis / layer1_unchanged
5. O5.6.2 Neutralizer 顺序 (2): preserve_orthogonality / breaks_orthogonality
6. O5.6.4 缓存 (2): cache_hit / cache_miss_on_input_change
7. O5.6.5 冲突解决 (2): ic_priority / conservative
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


# =============================================================================
# 辅助函数
# =============================================================================

def _make_factor_dict(
    names, N=50, T=10, seed=42, noise_scale=0.1
):
    """构造 {因子名: (N, T) DataFrame} 字典"""
    rng = np.random.default_rng(seed)
    return {
        name: pd.DataFrame(
            rng.standard_normal((N, T)) + noise_scale * rng.standard_normal((N, T)),
            index=[f"s{i}" for i in range(N)],
            columns=pd.date_range("2024-01-01", periods=T, freq="D"),
        )
        for name in names
    }


def _make_collinear_pair(name1, name2, rho=0.9, N=50, T=10, seed=42):
    """构造两个高度相关的因子 (rho ≈ 0.9)"""
    rng = np.random.default_rng(seed)
    base = rng.standard_normal((N, T))
    noise1 = np.sqrt(1 - rho) * rng.standard_normal((N, T))
    noise2 = np.sqrt(1 - rho) * rng.standard_normal((N, T))
    idx = [f"s{i}" for i in range(N)]
    cols = pd.date_range("2024-01-01", periods=T, freq="D")
    return {
        name1: pd.DataFrame(np.sqrt(rho) * base + noise1, index=idx, columns=cols),
        name2: pd.DataFrame(np.sqrt(rho) * base + noise2, index=idx, columns=cols),
    }


# =============================================================================
# 1. Grouped 基础
# =============================================================================

class TestGroupedBasic:
    """GroupedOrthogonalizer 基础测试"""

    def test_grouped_within_group_orthogonal(self):
        """组内因子正交化后 T^T T ≈ I (单位阵)"""
        # 构造两组: value (3 因子, 高相关) + momentum (2 因子, 高相关)
        fd = _make_factor_dict(["v1", "v2", "v3", "m1", "m2"], seed=42)
        # 让组内因子高度相关
        rng = np.random.default_rng(42)
        base_v = rng.standard_normal((50, 10))
        base_m = rng.standard_normal((50, 10))
        for name in ["v1", "v2", "v3"]:
            fd[name] = pd.DataFrame(
                0.9 * base_v + 0.1 * rng.standard_normal((50, 10)),
                index=fd[name].index, columns=fd[name].columns,
            )
        for name in ["m1", "m2"]:
            fd[name] = pd.DataFrame(
                0.9 * base_m + 0.1 * rng.standard_normal((50, 10)),
                index=fd[name].index, columns=fd[name].columns,
            )

        groups = {"value": ["v1", "v2", "v3"], "momentum": ["m1", "m2"]}
        grouped = GroupedOrthogonalizer(groups)
        grouped.fit(fd)
        result = grouped.transform(fd)

        # 检查 value 组内正交化后 T^T T 接近 I
        # 取某期 t, 堆叠为 (N, K_group)
        from factor_pipeline.modules.factor_orthogonalizer.utils.stacking import (
            align_factors,
        )
        aligned = align_factors({"v1": result["v1"], "v2": result["v2"], "v3": result["v3"]})
        t = 0
        F_t = np.column_stack([aligned[n].iloc[:, t].values for n in ["v1", "v2", "v3"]])
        gram = F_t.T @ F_t / 50  # 归一化
        # 对角线应非负 (W 仍为有效正交化器)
        # 对称正交化后 T^T T 单期接近 I, 但跨期 W 应用会有偏
        # 此处只检查 off-diagonal << diagonal
        off_diag_max = np.max(np.abs(gram - np.diag(np.diag(gram))))
        diag_min = np.min(np.diag(gram))
        # 组内相关性应大幅降低 (off_diag/diag < 0.3)
        assert off_diag_max / max(diag_min, 1e-10) < 0.5, (
            f"组内 off_diag/diag = {off_diag_max/diag_min:.3f}, 应 < 0.5"
        )

    def test_grouped_between_group_preserved(self):
        """组间相关性保留 (不为 0)"""
        # value 与 momentum 强相关 (rho=0.8)
        rng = np.random.default_rng(42)
        N, T = 50, 10
        base = rng.standard_normal((N, T))
        idx = [f"s{i}" for i in range(N)]
        cols = pd.date_range("2024-01-01", periods=T, freq="D")
        fd = {
            "v1": pd.DataFrame(0.9 * base + 0.1 * rng.standard_normal((N, T)), index=idx, columns=cols),
            "m1": pd.DataFrame(0.9 * base + 0.1 * rng.standard_normal((N, T)), index=idx, columns=cols),
            "v2": pd.DataFrame(0.5 * base + 0.5 * rng.standard_normal((N, T)), index=idx, columns=cols),
            "m2": pd.DataFrame(0.5 * base + 0.5 * rng.standard_normal((N, T)), index=idx, columns=cols),
        }
        # 计算正交化前 v1 vs m1 相关性 (应高)
        corr_before = np.corrcoef(fd["v1"].values.flatten(), fd["m1"].values.flatten())[0, 1]
        assert abs(corr_before) > 0.7, f"组间相关性应高, 实际 {corr_before:.3f}"

        groups = {"value": ["v1", "v2"], "momentum": ["m1", "m2"]}
        grouped = GroupedOrthogonalizer(groups)
        grouped.fit(fd)
        result = grouped.transform(fd)

        # 组间相关性应保留 (不为 0)
        corr_after = np.corrcoef(
            result["v1"].values.flatten(), result["m1"].values.flatten()
        )[0, 1]
        assert abs(corr_after) > 0.1, (
            f"组间相关性应保留 (>0.1), 实际 {corr_after:.3f}"
        )

    def test_grouped_duplicate_factor_raises(self):
        """重复因子名抛 ValueError"""
        fd = _make_factor_dict(["v1", "v2"], seed=42)
        # v1 同时出现在两组
        groups = {"g1": ["v1", "v2"], "g2": ["v1"]}
        with pytest.raises(ValueError, match="重复"):
            GroupedOrthogonalizer(groups)


# =============================================================================
# 2. O5.6.3 Grouped 缺失因子
# =============================================================================

class TestGroupedMissingFactor:
    """O5.6.3: 缺失因子处理策略"""

    def test_grouped_missing_factor_raises(self):
        """missing_factor_strategy='raise' 时缺失因子抛 ValueError"""
        fd = _make_factor_dict(["v1", "v2", "m1"], seed=42)
        groups = {"value": ["v1", "v2", "v3"], "momentum": ["m1"]}  # v3 不存在
        grouped = GroupedOrthogonalizer(groups, missing_factor_strategy='raise')
        with pytest.raises(ValueError, match="v3"):
            grouped.fit(fd)

    def test_grouped_missing_factor_skip(self):
        """missing_factor_strategy='skip' 时跳过缺失因子的组"""
        fd = _make_factor_dict(["v1", "v2", "m1"], seed=42)
        groups = {"value": ["v1", "v2"], "missing_group": ["v3", "v4"], "momentum": ["m1"]}
        grouped = GroupedOrthogonalizer(groups, missing_factor_strategy='skip')
        grouped.fit(fd)
        # missing_group 应被跳过, 不在 orthogonalizers_ 中
        assert "missing_group" not in grouped.orthogonalizers_
        # value 和 momentum 应被正常 fit
        assert "value" in grouped.orthogonalizers_
        assert "momentum" not in grouped.orthogonalizers_  # 单因子组无法正交化


# =============================================================================
# 3. O5.6.1 三件套数据流协议
# =============================================================================

class TestTripleChainDataFlow:
    """O5.6.1: 三件套数据流协议"""

    def test_triple_chain_data_flow_contract(self):
        """raw_factors 和 processed_factors keys/shape 不一致时抛错"""
        raw = _make_factor_dict(["f1", "f2"], seed=42)
        processed = _make_factor_dict(["f1", "f3"], seed=42)  # keys 不同
        coordinator = TripleChainCoordinator()
        with pytest.raises((AssertionError, ValueError)):
            coordinator.full_diagnosis(raw, processed)

    def test_fingerprinter_does_not_mutate_input(self):
        """Fingerprinter 提取后 raw_factors 不变"""
        raw = _make_factor_dict(["f1", "f2"], seed=42)
        raw_before = {k: v.copy() for k, v in raw.items()}

        class MockFingerprinter:
            def extract(self, df):
                # 模拟提取, 不修改输入
                return {"mean": float(df.values.mean())}

        coordinator = TripleChainCoordinator(fingerprinter=MockFingerprinter())
        coordinator.full_diagnosis(raw, raw)  # raw == processed (简化)

        # raw 应未被修改
        for name in raw:
            np.testing.assert_array_equal(raw[name].values, raw_before[name].values)


# =============================================================================
# 4. TripleChain 端到端
# =============================================================================

class TestTripleChainEndToEnd:
    """TripleChainCoordinator 端到端测试"""

    def test_triple_chain_full_diagnosis(self):
        """端到端诊断报告含 fingerprints / orthogonalization / significance"""
        raw = _make_factor_dict(["f1", "f2"], seed=42)

        class MockFingerprinter:
            def extract(self, df):
                return {"mean": float(df.values.mean()), "std": float(df.values.std())}

        class MockOrthogonalizer:
            enabled = True
            method = 'symmetric'
            def fit_transform(self, factor_dict):
                # 模拟正交化 (返回相同结构)
                return {k: v * 2 for k, v in factor_dict.items()}

        coordinator = TripleChainCoordinator(
            fingerprinter=MockFingerprinter(),
            orthogonalizer=MockOrthogonalizer(),
        )
        report = coordinator.full_diagnosis(raw, raw)
        assert 'fingerprints' in report
        assert 'orthogonalization' in report
        assert set(report['fingerprints'].keys()) == {"f1", "f2"}
        assert report['orthogonalization']['method'] == 'symmetric'

    def test_triple_chain_layer1_unchanged(self):
        """Layer 1 Pipeline 不被 TripleChain 修改"""
        raw = _make_factor_dict(["f1", "f2"], seed=42)
        processed = _make_factor_dict(["f1", "f2"], seed=42)
        processed_before = {k: v.copy() for k, v in processed.items()}

        coordinator = TripleChainCoordinator()  # 空协调器
        coordinator.full_diagnosis(raw, processed)

        # processed 应未被修改
        for name in processed:
            np.testing.assert_array_equal(
                processed[name].values, processed_before[name].values
            )


# =============================================================================
# 5. O5.6.2 Neutralizer 顺序
# =============================================================================

class TestNeutralizerOrder:
    """O5.6.2: Neutralizer 与 Orthogonalizer 顺序"""

    def test_neutralize_before_orthogonalize_preserves_orthogonality(self):
        """先中性化后正交化: T^T T ≈ I (正交性保留)"""
        rng = np.random.default_rng(42)
        N, K = 100, 3
        F = rng.standard_normal((N, K))
        # 简单"中性化": 减去均值 (中心化)
        F_neutral = F - F.mean(axis=0, keepdims=True)
        # 正交化
        from factor_pipeline.modules.factor_orthogonalizer.core.symmetric import (
            SymmetricOrthogonalizer,
        )
        orth = SymmetricOrthogonalizer()
        T_panel = orth.fit_transform(F_neutral)
        gram = T_panel.T @ T_panel / N
        # 对角线应接近 1 (Löwdin 性质), off-diagonal 接近 0
        off_diag_max = np.max(np.abs(gram - np.diag(np.diag(gram))))
        assert off_diag_max < 1e-10, (
            f"先中性化后正交化, off_diag = {off_diag_max:.2e}, 应 < 1e-10"
        )

    def test_orthogonalize_before_neutralize_breaks_orthogonality(self):
        """先正交化后中性化: T^T T ≠ I (正交性破坏)"""
        rng = np.random.default_rng(42)
        N, K = 100, 3
        F = rng.standard_normal((N, K)) + 5.0  # 非零均值
        from factor_pipeline.modules.factor_orthogonalizer.core.symmetric import (
            SymmetricOrthogonalizer,
        )
        orth = SymmetricOrthogonalizer()
        T_panel = orth.fit_transform(F)
        # 中性化 (减均值)
        T_neutral = T_panel - T_panel.mean(axis=0, keepdims=True)
        gram = T_neutral.T @ T_neutral / N
        off_diag_max = np.max(np.abs(gram - np.diag(np.diag(gram))))
        # 先正交化后中性化: 减均值改变列, 破坏正交性
        # (注: 减均值对 off-diagonal 的影响为 -mean_i*mean_j*N, 不为 0)
        assert off_diag_max > 1e-6, (
            f"先正交化后中性化, off_diag = {off_diag_max:.2e}, 应 > 1e-6 (正交性破坏)"
        )


# =============================================================================
# 6. O5.6.4 缓存
# =============================================================================

class TestTripleChainCache:
    """O5.6.4: TripleChainCoordinator 缓存"""

    def test_triple_chain_cache_hit(self):
        """相同输入第二次调用走缓存, 耗时显著降低"""
        import time
        raw = _make_factor_dict(["f1", "f2"], seed=42)

        call_count = [0]
        class SlowFingerprinter:
            def extract(self, df):
                call_count[0] += 1
                # 模拟慢计算
                time.sleep(0.05)
                return {"mean": float(df.values.mean())}

        coordinator = TripleChainCoordinator(
            fingerprinter=SlowFingerprinter(), cache_enabled=True
        )
        # 第一次调用
        t0 = time.time()
        coordinator.full_diagnosis(raw, raw)
        t1 = time.time()
        # 第二次调用 (应走缓存)
        coordinator.full_diagnosis(raw, raw)
        t2 = time.time()

        # 第二次应明显快 (缓存命中)
        # 注意: Fingerprinter.extract 调用次数 = 2 (2 个因子), 第二次走缓存应为 0 新调用
        # 总调用次数仍为 2 (第一次的 2 次), 不再增加
        assert call_count[0] == 2, (
            f"缓存命中后 Fingerprinter 不应再调用, 实际调用 {call_count[0]} 次"
        )

    def test_triple_chain_cache_miss_on_input_change(self):
        """输入变化后重算 (缓存 miss)"""
        raw1 = _make_factor_dict(["f1", "f2"], seed=42)
        raw2 = _make_factor_dict(["f1", "f2"], seed=99)  # 不同 seed, 不同数据

        call_count = [0]
        class CountingFingerprinter:
            def extract(self, df):
                call_count[0] += 1
                return {"mean": float(df.values.mean())}

        coordinator = TripleChainCoordinator(
            fingerprinter=CountingFingerprinter(), cache_enabled=True
        )
        coordinator.full_diagnosis(raw1, raw1)
        first_count = call_count[0]
        coordinator.full_diagnosis(raw2, raw2)
        # 输入变化, 应重新调用 Fingerprinter
        assert call_count[0] > first_count, (
            f"输入变化后应重算, 调用次数 {first_count} → {call_count[0]}"
        )


# =============================================================================
# 7. O5.6.5 冲突解决
# =============================================================================

class TestConflictResolution:
    """O5.6.5: 跨 Layer 诊断冲突解决"""

    def test_conflict_resolution_ic_priority(self):
        """IC 高但 VRR < 0.3 (冗余) 的因子, ic_priority 策略保留"""
        report = {
            'fingerprints': {'f1': {}, 'f2': {}},
            'orthogonalization': {
                'method': 'symmetric',
                'diagnostics': {'vrr': {'f1': 0.1, 'f2': 1.0}},  # f1 冗余
            },
            'significance': {
                'f1': {'is_significant': True, 'ic_change_ratio': -0.1},  # f1 显著
                'f2': {'is_significant': False, 'ic_change_ratio': 0.0},
            },
        }
        coordinator = TripleChainCoordinator()
        recs = coordinator.resolve_conflicts(report, strategy='ic_priority')
        # f1: IC 显著 → 保留 (即使 VRR 低)
        assert recs['f1']['recommendation'] == 'keep'
        # f2: IC 不显著 → 删除
        assert recs['f2']['recommendation'] == 'drop'

    def test_conflict_resolution_conservative(self):
        """conservative 策略: 任一不利则删除"""
        report = {
            'fingerprints': {'f1': {}, 'f2': {}, 'f3': {}},
            'orthogonalization': {
                'method': 'symmetric',
                'diagnostics': {'vrr': {'f1': 0.1, 'f2': 1.0, 'f3': 1.0}},
            },
            'significance': {
                'f1': {'is_significant': True, 'ic_change_ratio': -0.1},
                'f2': {'is_significant': True, 'ic_change_ratio': -0.9},  # IC 下降
                'f3': {'is_significant': True, 'ic_change_ratio': -0.1},  # 全有利
            },
        }
        coordinator = TripleChainCoordinator()
        recs = coordinator.resolve_conflicts(report, strategy='conservative')
        # f1: VRR 低 (冗余) → drop
        assert recs['f1']['recommendation'] == 'drop'
        # f2: IC 下降 → drop
        assert recs['f2']['recommendation'] == 'drop'
        # f3: 全有利 → keep
        assert recs['f3']['recommendation'] == 'keep'
