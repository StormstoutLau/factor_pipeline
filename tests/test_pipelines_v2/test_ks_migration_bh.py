"""T4 E1: KS 迁移检测 Benjamini-Hochberg FDR 校正测试

测试用例 E1-T1 ~ E1-T6, 对应 EXECUTION_V3.0.0_T4.md v1.1 §1.5。

Red 阶段: 当前 _ks_migration_significance 仍用 Bonferroni, 期望 6 个测试失败。
Green 阶段: 迁移到 BH 后, 6 个测试应全部通过。

黄金参考 (附录 B):
    输入 p_values = [0.01, 0.04, 0.03, 0.20, 0.50], K=5
    排序后: [0.01, 0.03, 0.04, 0.20, 0.50], rank=[1,2,3,4,5]
    bh_raw = [0.05, 0.075, 0.0667, 0.25, 0.50]
    累积 min (从大到小):
        i=4: prev=0.50, p_adj[4]=0.50
        i=3: prev=0.25, p_adj[3]=0.25
        i=2: prev=0.0667, p_adj[2]=0.0667
        i=1: bh=0.075 > 0.0667, prev 保持 0.0667, p_adj[1]=0.0667
        i=0: prev=0.05, p_adj[0]=0.05
    还原原顺序: [0.05, 0.0667, 0.0667, 0.25, 0.50]
    min_p_adj = 0.05
"""
import numpy as np
import pandas as pd
import pytest


# ============================================================================
# 辅助函数: 手工实现 BH 校正 (作为独立参考实现, 不依赖被测代码)
# ============================================================================

def _manual_bh_correction(p_values):
    """手工 BH 校正, 返回 (p_adj, min_p_adj)

    p_adj_(k) = p_(k) * K / rank, 从大到小累积 min, clip [0,1]
    """
    p_arr = np.asarray(p_values, dtype=float)
    K = len(p_arr)
    order = np.argsort(p_arr)
    p_adj = np.empty_like(p_arr)
    prev = 1.0
    for i in range(K - 1, -1, -1):
        rank = i + 1
        idx = order[i]
        bh = p_arr[idx] * K / rank
        prev = min(prev, bh)
        p_adj[idx] = min(prev, 1.0)
    return p_adj, float(np.min(p_adj))


def _manual_bonferroni_correction(p_values, alpha):
    """手工 Bonferroni 校正, 返回 (alpha_corrected, is_significant)"""
    K = len(p_values)
    alpha_corrected = alpha / max(K, 1)
    min_p = float(np.min(p_values))
    return alpha_corrected, (min_p < alpha_corrected)


# ============================================================================
# 构造可控 p 值的测试数据
# ============================================================================

def _construct_data_with_target_p_values(target_p_values):
    """构造 (historical, recent) DataFrame, 使 KS 检验返回接近 target_p_values

    策略: 用均匀分布 + 偏移控制 KS 统计量, 但 KS p 值依赖样本量与统计量,
    精确控制困难。这里采用另一种策略: 直接 monkeypatch scipy.stats.ks_2samp
    返回指定的 (stat, p) 序列。
    """
    K = len(target_p_values)
    hist = pd.DataFrame(
        np.random.RandomState(42).randn(100, K),
        columns=[f'factor_{i}' for i in range(K)]
    )
    recent = pd.DataFrame(
        np.random.RandomState(43).randn(100, K),
        columns=[f'factor_{i}' for i in range(K)]
    )
    return hist, recent


@pytest.fixture
def mock_ks_2samp(monkeypatch):
    """monkeypatch scipy.stats.ks_2samp 返回指定 p 值序列

    返回一个 setter 函数, 调用 setter(p_values) 后, ks_2samp 将依次返回
    (stat=0.5, p=p_values[i])
    """
    import factor_pipeline.pipelines_v2 as pv2

    state = {'p_values': None, 'call_idx': 0}

    def fake_ks_2samp(a, b):
        if state['p_values'] is None:
            raise RuntimeError("setter 未调用")
        idx = state['call_idx'] % len(state['p_values'])
        p = state['p_values'][idx]
        state['call_idx'] += 1
        return 0.5, float(p)

    def setter(p_values):
        state['p_values'] = list(p_values)
        state['call_idx'] = 0

    monkeypatch.setattr(pv2._scipy_stats, 'ks_2samp', fake_ks_2samp)
    return setter


# ============================================================================
# E1-T1: BH 校正与手工计算一致 (黄金参考)
# ============================================================================

class TestE1T1BHGoldsEnSample:
    """E1-T1: BH 校正与手工计算一致 (p=[0.01, 0.04, 0.03, 0.20, 0.50])"""

    def test_bh_p_adj_matches_manual(self, mock_ks_2samp):
        """BH 路径: p_adj 与手工计算 [0.05, 0.0667, 0.0667, 0.25, 0.50] 一致"""
        from factor_pipeline.pipelines_v2 import _ks_migration_significance

        target_p = [0.01, 0.04, 0.03, 0.20, 0.50]
        mock_ks_2samp(target_p)
        hist, recent = _construct_data_with_target_p_values(target_p)

        # 默认 correction_method='benjamini_hochberg' (T4 后默认)
        is_sig, min_p, details = _ks_migration_significance(
            hist, recent, alpha=0.05
        )

        # 期望 p_adj (还原原顺序, atol=1e-4)
        expected_p_adj = [0.05, 0.0667, 0.0667, 0.25, 0.50]
        actual_p_adj = [c['p_value_adjusted'] for c in details['per_column']]

        assert len(actual_p_adj) == 5
        for actual, expected in zip(actual_p_adj, expected_p_adj):
            assert actual == pytest.approx(expected, abs=1e-4), (
                f"p_adj 不匹配: actual={actual}, expected={expected}"
            )

        # min_p_value_adjusted
        assert details['min_p_value_adjusted'] == pytest.approx(0.05, abs=1e-10)
        # min_p_value (原始, 未校正)
        assert min_p == pytest.approx(0.01, abs=1e-10)
        # is_significant: min_p_adj=0.05, alpha=0.05, 严格小于 → False
        assert is_sig is False

    def test_bh_correction_method_field(self, mock_ks_2samp):
        """details['correction_method'] == 'benjamini_hochberg'"""
        from factor_pipeline.pipelines_v2 import _ks_migration_significance

        target_p = [0.01, 0.04, 0.03, 0.20, 0.50]
        mock_ks_2samp(target_p)
        hist, recent = _construct_data_with_target_p_values(target_p)

        _, _, details = _ks_migration_significance(hist, recent, alpha=0.05)

        assert details['correction_method'] == 'benjamini_hochberg'
        # BH 路径不应包含 bonferroni_correction 字段
        assert 'bonferroni_correction' not in details
        # BH 路径不应包含 alpha_corrected 字段
        assert 'alpha_corrected' not in details


# ============================================================================
# E1-T2: Bonferroni 路径向后兼容
# ============================================================================

class TestE1T2BonferroniBackwardCompat:
    """E1-T2: correction_method='bonferroni' 走旧路径, 字段保留"""

    def test_bonferroni_path_fields(self, mock_ks_2samp):
        """Bonferroni 路径: alpha_corrected, bonferroni_correction=True 仍存在"""
        from factor_pipeline.pipelines_v2 import _ks_migration_significance

        target_p = [0.01, 0.04, 0.03, 0.20, 0.50]
        mock_ks_2samp(target_p)
        hist, recent = _construct_data_with_target_p_values(target_p)

        is_sig, min_p, details = _ks_migration_significance(
            hist, recent, alpha=0.05, correction_method='bonferroni'
        )

        # 旧字段保留
        assert 'alpha_corrected' in details
        assert details['alpha_corrected'] == pytest.approx(0.01, abs=1e-10)  # 0.05/5
        assert details['bonferroni_correction'] is True

        # 旧路径不返回 p_value_adjusted
        for c in details['per_column']:
            assert 'p_value_adjusted' not in c

        # 旧路径判定: min_p=0.01 < alpha_corrected=0.01 → False (严格小于)
        assert is_sig is False
        assert min_p == pytest.approx(0.01, abs=1e-10)

    def test_bonferroni_path_no_corruption(self, mock_ks_2samp):
        """Bonferroni 路径 details 不应混入 BH 字段"""
        from factor_pipeline.pipelines_v2 import _ks_migration_significance

        target_p = [0.01, 0.04, 0.03, 0.20, 0.50]
        mock_ks_2samp(target_p)
        hist, recent = _construct_data_with_target_p_values(target_p)

        _, _, details = _ks_migration_significance(
            hist, recent, alpha=0.05, correction_method='bonferroni'
        )

        # 不应出现 BH 专属字段
        assert 'correction_method' not in details or details.get('correction_method') != 'benjamini_hochberg'
        assert 'min_p_value_adjusted' not in details


# ============================================================================
# E1-T3: none 路径 (无校正)
# ============================================================================

class TestE1T3NonePath:
    """E1-T3: correction_method='none' 不做多重校正"""

    def test_none_path_no_correction(self, mock_ks_2samp):
        """none 路径: is_significant = (min_p < alpha), 无 p_adj"""
        from factor_pipeline.pipelines_v2 import _ks_migration_significance

        target_p = [0.01, 0.04, 0.03, 0.20, 0.50]
        mock_ks_2samp(target_p)
        hist, recent = _construct_data_with_target_p_values(target_p)

        is_sig, min_p, details = _ks_migration_significance(
            hist, recent, alpha=0.05, correction_method='none'
        )

        # 无校正: min_p=0.01 < alpha=0.05 → True
        assert is_sig is True
        assert min_p == pytest.approx(0.01, abs=1e-10)

        # 字段验证
        assert details.get('correction_method') == 'none'
        # none 路径不应有 alpha_corrected 或 min_p_value_adjusted
        assert 'alpha_corrected' not in details
        assert 'min_p_value_adjusted' not in details
        assert 'bonferroni_correction' not in details

        # per_column 不含 p_value_adjusted
        for c in details['per_column']:
            assert 'p_value_adjusted' not in c


# ============================================================================
# E1-T4: 空数据 / 无公共列 / 数据不足 保护路径不变
# ============================================================================

class TestE1T4ProtectionPaths:
    """E1-T4: 边界保护路径不因 BH 迁移破坏"""

    def test_empty_data(self):
        """空数据: 返回 (False, 1.0, {warning: 'empty data'})"""
        from factor_pipeline.pipelines_v2 import _ks_migration_significance

        empty = pd.DataFrame()
        is_sig, min_p, details = _ks_migration_significance(empty, empty, alpha=0.05)

        assert is_sig is False
        assert min_p == 1.0
        assert details['warning'] == 'empty data'
        assert details['n_columns'] == 0

    def test_no_common_columns(self):
        """无公共列: 返回 (False, 1.0, {warning: 'no common columns'})"""
        from factor_pipeline.pipelines_v2 import _ks_migration_significance

        hist = pd.DataFrame(np.random.randn(100, 3), columns=['a', 'b', 'c'])
        recent = pd.DataFrame(np.random.randn(100, 3), columns=['x', 'y', 'z'])

        is_sig, min_p, details = _ks_migration_significance(hist, recent, alpha=0.05)

        assert is_sig is False
        assert min_p == 1.0
        assert details['warning'] == 'no common columns'

    def test_insufficient_data(self):
        """数据不足 (<5 观测值): 返回 (False, 1.0, {warning: 'insufficient data'})"""
        from factor_pipeline.pipelines_v2 import _ks_migration_significance

        hist = pd.DataFrame(np.random.randn(3, 2), columns=['a', 'b'])
        recent = pd.DataFrame(np.random.randn(3, 2), columns=['a', 'b'])

        is_sig, min_p, details = _ks_migration_significance(hist, recent, alpha=0.05)

        assert is_sig is False
        assert min_p == 1.0
        assert details['warning'] == 'insufficient data'

    def test_series_input_still_works(self):
        """Series 输入仍可正常处理 (单列)"""
        from factor_pipeline.pipelines_v2 import _ks_migration_significance

        np.random.seed(42)
        hist = pd.Series(np.random.randn(100), name='factor')
        recent = pd.Series(np.random.randn(100) + 2.0, name='factor')

        is_sig, min_p, details = _ks_migration_significance(hist, recent, alpha=0.05)

        # 均值偏移 2.0, KS 应显著
        assert is_sig is True
        assert min_p < 0.05
        assert details['n_columns'] == 1


# ============================================================================
# E1-T5: BH 校正下迁移率 >= Bonferroni (宽松性验证)
# ============================================================================

class TestE1T5BHLessConservative:
    """E1-T5: BH 比 Bonferroni 宽松, 检测力 >= Bonferroni"""

    def test_bh_detects_more_or_equal_than_bonferroni(self, mock_ks_2samp):
        """构造 10 列, p=[0.001, 0.005, 0.01, 0.02, 0.03, 0.04, 0.05, 0.10, 0.30, 0.50]

        Bonferroni (alpha=0.05, K=10): alpha_corrected=0.005
            - 显著: p < 0.005 → 仅 p=0.001 (1 个)
        BH (alpha=0.05, K=10):
            - p_adj 排序后 [0.001, 0.005, 0.01, 0.02, 0.03, 0.04, 0.05, 0.10, 0.30, 0.50]
            - rank=[1..10], bh_raw=[0.01, 0.025, 0.0333, 0.05, 0.06, 0.0667, 0.0714, 0.125, 0.30, 0.50]
            - 累积 min (从大到小): prev=[0.50, 0.30, 0.125, 0.0714, 0.0667, 0.06, 0.05, 0.05, 0.025, 0.01]
            - p_adj (原顺序)=[0.01, 0.025, 0.0333, 0.05, 0.06, 0.0667, 0.0714, 0.125, 0.30, 0.50]
            - 显著: p_adj < 0.05 → p_adj=0.01, 0.025, 0.0333 (3 个)
            - BH 确认迁移数 (3) >= Bonferroni (1)
        """
        from factor_pipeline.pipelines_v2 import _ks_migration_significance

        target_p = [0.001, 0.005, 0.01, 0.02, 0.03, 0.04, 0.05, 0.10, 0.30, 0.50]

        # Bonferroni 路径
        mock_ks_2samp(target_p)
        hist, recent = _construct_data_with_target_p_values(target_p)
        is_sig_bonf, _, details_bonf = _ks_migration_significance(
            hist, recent, alpha=0.05, correction_method='bonferroni'
        )
        # Bonferroni 显著性: min_p=0.001 < 0.005 → True
        bonf_sig_count = sum(
            1 for c in details_bonf['per_column']
            if c['p_value'] < details_bonf['alpha_corrected']
        )

        # BH 路径 (重置 mock)
        mock_ks_2samp(target_p)
        hist2, recent2 = _construct_data_with_target_p_values(target_p)
        is_sig_bh, _, details_bh = _ks_migration_significance(
            hist2, recent2, alpha=0.05, correction_method='benjamini_hochberg'
        )
        bh_sig_count = sum(
            1 for c in details_bh['per_column']
            if c['p_value_adjusted'] < 0.05
        )

        # 宽松性验证: BH 检测数 >= Bonferroni
        assert bonf_sig_count == 1, f"Bonferroni 期望 1 个显著, 实际 {bonf_sig_count}"
        assert bh_sig_count == 3, f"BH 期望 3 个显著, 实际 {bh_sig_count}"
        assert bh_sig_count >= bonf_sig_count

        # 整体显著性: BH True (有 p_adj<0.05), Bonferroni True (min_p<0.005)
        assert is_sig_bh is True
        assert is_sig_bonf is True


# ============================================================================
# E1-T6: details 字段结构验证
# ============================================================================

class TestE1T6DetailsStructure:
    """E1-T6: 三条路径 details 字段结构验证"""

    def test_bh_details_structure(self, mock_ks_2samp):
        """BH 路径 details 字段完整且无 Bonferroni 残留"""
        from factor_pipeline.pipelines_v2 import _ks_migration_significance

        target_p = [0.01, 0.04, 0.03, 0.20, 0.50]
        mock_ks_2samp(target_p)
        hist, recent = _construct_data_with_target_p_values(target_p)

        _, _, details = _ks_migration_significance(hist, recent, alpha=0.05)

        # 必有字段
        required_fields = {
            'per_column', 'n_columns', 'min_p_value',
            'min_p_value_adjusted', 'alpha', 'correction_method', 'method'
        }
        assert required_fields.issubset(details.keys()), (
            f"缺少字段: {required_fields - details.keys()}"
        )

        # 禁有字段 (BH 路径)
        forbidden_fields = {'bonferroni_correction', 'alpha_corrected'}
        assert not (forbidden_fields & details.keys()), (
            f"不应存在的字段: {forbidden_fields & details.keys()}"
        )

        # 字段值验证
        assert details['correction_method'] == 'benjamini_hochberg'
        assert details['method'] == 'ks_2samp'
        assert details['alpha'] == 0.05
        assert details['n_columns'] == 5

        # per_column 每项含 p_value_adjusted
        for c in details['per_column']:
            assert 'p_value_adjusted' in c
            assert 'p_value' in c
            assert 'statistic' in c
            assert 'column' in c

    def test_bonferroni_details_structure(self, mock_ks_2samp):
        """Bonferroni 路径 details 字段完整 (向后兼容)"""
        from factor_pipeline.pipelines_v2 import _ks_migration_significance

        target_p = [0.01, 0.04, 0.03, 0.20, 0.50]
        mock_ks_2samp(target_p)
        hist, recent = _construct_data_with_target_p_values(target_p)

        _, _, details = _ks_migration_significance(
            hist, recent, alpha=0.05, correction_method='bonferroni'
        )

        # 必有字段
        required_fields = {
            'per_column', 'n_columns', 'min_p_value',
            'alpha', 'alpha_corrected', 'bonferroni_correction', 'method'
        }
        assert required_fields.issubset(details.keys())

        # 禁有字段 (Bonferroni 路径)
        forbidden_fields = {'min_p_value_adjusted', 'correction_method'}
        assert not (forbidden_fields & details.keys())

        assert details['bonferroni_correction'] is True
        assert details['method'] == 'ks_2samp'

    def test_none_details_structure(self, mock_ks_2samp):
        """none 路径 details 字段含 correction_method='none'"""
        from factor_pipeline.pipelines_v2 import _ks_migration_significance

        target_p = [0.01, 0.04, 0.03, 0.20, 0.50]
        mock_ks_2samp(target_p)
        hist, recent = _construct_data_with_target_p_values(target_p)

        _, _, details = _ks_migration_significance(
            hist, recent, alpha=0.05, correction_method='none'
        )

        # 必有字段
        required_fields = {'per_column', 'n_columns', 'min_p_value', 'alpha', 'correction_method', 'method'}
        assert required_fields.issubset(details.keys())

        # 禁有字段 (none 路径)
        forbidden_fields = {'alpha_corrected', 'bonferroni_correction', 'min_p_value_adjusted'}
        assert not (forbidden_fields & details.keys())

        assert details['correction_method'] == 'none'
        assert details['method'] == 'ks_2samp'
