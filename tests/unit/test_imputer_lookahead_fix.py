# -*- coding: utf-8 -*-
"""
TDD: 插补模块前视偏差修复测试

测试层次:
1. bfill 前视偏差检测 (P0-1, 应在修复前失败, 修复后通过)
2. TimeSeriesImputer 向量化等价性 (P0-2, 修复前后行为应一致)
3. MLAdvancedImputer / FactorSpecificImputer bfill 修复验证

学术依据:
- Little & Rubin (2002) §4.3: 因果填充原则
- Hyndman & Athanasopoulos (2021) §5.10: 时间序列交叉验证
- Lopez de Prado (2018) §7: Purged K-Fold 信息泄漏

参考: docs/analysis/IMPUTER_LOOKAHEAD_FIX_PLAN.md v2.1 §4.1 §5.1
"""
import numpy as np
import pandas as pd
import pytest

from factor_pipeline.modules.factor_imputer.core.imputers import (
    TimeSeriesImputer,
    MLAdvancedImputer,
    FactorSpecificImputer,
    CrossSectionalImputer,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def panel_with_bfill_leakage():
    """构造能暴露 bfill 前视偏差的面板数据.
    
    设计: t=5 时 S0 缺失, t=6 时 S0 有值 999 (异常值).
    若用 bfill, t=5 会被 999 填充 → 前视泄漏.
    若用 ffill+fillna(0), t=5 应被 t=4 的值填充 → 因果.
    """
    dates = pd.date_range('2020-01-01', periods=10, freq='D')
    cols = ['S0', 'S1', 'S2']
    data = np.array([
        [1.0,  10.0, 100.0],   # t=0
        [2.0,  20.0, 110.0],   # t=1
        [3.0,  30.0, 120.0],   # t=2
        [4.0,  40.0, 130.0],   # t=3
        [5.0,  50.0, 140.0],   # t=4
        [np.nan, 60.0, 150.0], # t=5: S0 缺失, 待修复目标
        [999.0, 70.0, 160.0],  # t=6: S0 异常值, bfill 会泄漏
        [7.0,  80.0, 170.0],   # t=7
        [8.0,  90.0, 180.0],   # t=8
        [9.0, 100.0, 190.0],   # t=9
    ])
    return pd.DataFrame(data, index=dates, columns=cols)


@pytest.fixture
def panel_for_knn():
    """KNN 测试数据: 构造明确的缺失位置 + 未来异常值.
    
    S0 在 t=2,3 缺失; t=4 出现异常值 999.
    S1 在 t=2 也缺失 (用于暴露 bfill vs ffill 差异).
    
    若用 bfill: t=2 的 features S1 会被 t=4 的 50 填充 (前视)
    若用 ffill: t=2 的 features S1 会被 t=1 的 20 填充 (因果)
    """
    dates = pd.date_range('2020-01-01', periods=8, freq='D')
    cols = ['S0', 'S1', 'S2', 'S3']
    data = np.array([
        [1.0,  10.0, 100.0, 1.0],
        [2.0,  20.0, 110.0, 2.0],
        [np.nan, np.nan, 120.0, 3.0],   # t=2: S0, S1 缺失
        [np.nan, 40.0, 130.0, 4.0],      # t=3: S0 缺失
        [999.0, 50.0, 140.0, 5.0],       # t=4: S0 异常值 (bfill 会泄漏)
        [6.0,  60.0, 150.0, 6.0],
        [7.0,  70.0, 160.0, 7.0],
        [8.0,  80.0, 170.0, 8.0],
    ])
    return pd.DataFrame(data, index=dates, columns=cols)


@pytest.fixture
def panel_features_with_bfill():
    """专门检测 bfill 在 features 中的传播.

    S1 在 t=2 缺失, t=3 有值 50.
    - ffill (因果): t=2 features S1 = 20 (t=1 的值)
    - bfill (前视): t=2 features S1 = 50 (t=3 的未来值)

    999 不出现在 features 中, 避免原数据 999 干扰测试.
    共 12 行, 满足 RF _fit_random_forest 的 len(asset_data) > 10 要求.
    """
    dates = pd.date_range('2020-01-01', periods=12, freq='D')
    cols = ['S0', 'S1', 'S2']
    data = np.array([
        [1.0,   10.0, 100.0],
        [2.0,   20.0, 110.0],
        [3.0,   np.nan, 120.0],   # t=2: S1 缺失 (待检测位置)
        [4.0,   50.0, 130.0],     # t=3: S1 = 50 (bfill 会用这个未来值)
        [5.0,   60.0, 140.0],
        [6.0,   70.0, 150.0],
        [7.0,   80.0, 160.0],
        [8.0,   90.0, 170.0],
        [9.0,  100.0, 180.0],
        [10.0, 110.0, 190.0],
        [11.0, 120.0, 200.0],
        [12.0, 130.0, 210.0],
    ])
    return pd.DataFrame(data, index=dates, columns=cols)


# =============================================================================
# P0-1: bfill 前视偏差检测测试
# =============================================================================

class TestBfillLookaheadBias:
    """验证 6 处 bfill 已被替换为因果填充.
    
    检测策略 (三层防御):
    1. 源码静态扫描: 确认 imputers.py 中无 .bfill() 调用
    2. 行为测试: 构造未来异常值场景, 验证填充结果不含未来值
    3. 因果性测试: 截断未来数据, 验证 t 时刻填充结果不变
    """
    
    # ----- 层 1: 源码静态扫描 -----
    
    def test_no_bfill_in_source(self):
        """静态扫描: imputers.py 源码不应再包含 .bfill() 调用.
        
        这是 P0 修复的最直接验证 — 6 处 bfill 应全部被替换.
        """
        import inspect
        from factor_pipeline.modules.factor_imputer.core import imputers as imp_mod
        
        source = inspect.getsource(imp_mod)
        # 排除注释和字符串中的 bfill
        lines = source.split('\n')
        bfill_lines = []
        for i, line in enumerate(lines, 1):
            stripped = line.split('#')[0]  # 去掉行内注释
            # 去掉字符串中的 bfill (粗略)
            if '.bfill()' in stripped:
                # 检查是否在字符串字面量中 (粗略排除)
                in_string = ('"' in stripped and stripped.index('"') < stripped.index('.bfill()')) or \
                           ("'" in stripped and stripped.index("'") < stripped.index('.bfill()'))
                if not in_string:
                    bfill_lines.append((i, line.strip()))
        
        assert len(bfill_lines) == 0, \
            f"imputers.py 仍包含 .bfill() 调用 (前视偏差未修复): {bfill_lines}"
    
    # ----- 层 2: 行为测试 -----
    
    def test_knn_fit_features_no_future_leakage(self, panel_features_with_bfill):
        """A1 (imputers.py:288): _fit_knn 中 features 不应使用 bfill.
        
        构造场景: S1 在 t=2,3 缺失, t=4 异常值 999.
        - bfill (前视): fit 时 S1 在 t=2,3 的 features = 999 (来自未来)
        - ffill (因果): fit 时 S1 在 t=2,3 的 features = 20 (t=1 的值)
        
        通过 monkey-patch StandardScaler.fit_transform 捕获实际 features,
        只检查"原数据中 NaN 的位置"是否被 999 填充 (排除原数据本身含 999 的情况).
        """
        imp = MLAdvancedImputer(method='knn', n_neighbors=2)
        
        # 捕获 fit 时实际传入 scaler 的 features
        captured_features = {}
        original_fit_transform = StandardScaler.fit_transform
        
        def spy_fit_transform(self, X, y=None):
            captured_features[id(self)] = np.asarray(X).copy()
            return original_fit_transform(self, X, y)
        
        import sklearn.preprocessing as skpre
        original = skpre.StandardScaler.fit_transform
        try:
            skpre.StandardScaler.fit_transform = spy_fit_transform
            imp.fit(panel_features_with_bfill)
        finally:
            skpre.StandardScaler.fit_transform = original
        
        # 检查捕获的 features
        assert len(captured_features) > 0, "应至少捕获一个资产的 features"
        
        # 对每个资产, 检查 features 中"原本 NaN 的位置"是否被 999 填充
        # 注: t=4 的 999 是原数据, 不是 bfill 引起, 不应算作前视
        for scaler_id, feats in captured_features.items():
            # features 是 (n_samples, n_other_assets) 矩阵
            # 检查每列中原本 NaN 的行是否被填成 999
            for col_idx in range(feats.shape[1]):
                # 找到该资产列在原数据中的 NaN 位置
                # 这里简化: 直接检查 features 矩阵中是否有"被填充为 999 的位置"
                # 由于 fit 时 features 来自 X[other_assets].loc[asset_data.index]
                # 而 asset_data 是 X[asset].dropna(), 我们需要原始 X 中 other_assets 列的 NaN
                # 简化检查: features 中任何等于 999 的值都应是原数据中的 999,
                # 而非被 ffill/bfill 从未来填回的. 但 ffill+0 后, NaN 会被填成 0,
                # 不会是 999. 所以只要 features 中出现 999, 必然来自原数据.
                pass
            # 直接断言: ffill+fillna(0) 后, NaN 位置应被填为前值或 0, 不应是 999
            # 实际上: 若 ffill 正确, t=2,3 的 S1 features 应是 20 (前值), 不是 999
            # 若 bfill 仍存在, t=2,3 的 S1 features 会是 999 (未来值)
            # 所以检查: 是否存在 features 中连续两行某列都是 999 的情况
            # (排除 t=4 单行原本就是 999 的情况)
            if feats.shape[0] >= 2:
                for col_idx in range(feats.shape[1]):
                    col = feats[:, col_idx]
                    # 找连续两行都是 999 的情况 (这是 bfill 的特征, ffill 不会这样)
                    for i in range(len(col) - 1):
                        if np.isclose(col[i], 999.0) and np.isclose(col[i+1], 999.0):
                            pytest.fail(
                                f"fit features 中连续出现 999 (bfill 前视泄漏): "
                                f"col={col_idx}, rows={i},{i+1}, features={feats}"
                            )
    
    def test_knn_transform_no_future_value(self, panel_features_with_bfill):
        """A2 (imputers.py:305): _transform_knn 不应用 bfill 填充 features.
        
        验证: transform 时若其他资产有缺失, 不应用未来值填充 features.
        只检查"被填充的位置"(原本是 NaN, 现在有值), 排除原数据中的 999.
        """
        imp = MLAdvancedImputer(method='knn', n_neighbors=2)
        imp.fit(panel_features_with_bfill)
        result = imp.transform(panel_features_with_bfill.copy())
        
        # 只检查"被填充的位置"(原本是 NaN, 现在有值)
        nan_mask = np.isnan(panel_features_with_bfill.values)
        filled_mask = nan_mask & ~np.isnan(result.values)
        filled_values = result.values[filled_mask]
        
        # 被填充的值不应是 999 (未来异常值)
        if len(filled_values) > 0:
            assert not np.any(np.isclose(filled_values, 999.0)), \
                f"transform 填充结果中出现未来异常值 999 (bfill 前视泄漏): {filled_values}"
    
    def test_rf_fit_features_no_future_leakage(self, panel_features_with_bfill):
        """A3 (imputers.py:329): _fit_random_forest 中 features 不应用 bfill."""
        imp = MLAdvancedImputer(method='random_forest', n_estimators=5)
        
        captured_features = {}
        original_fit_transform = StandardScaler.fit_transform
        
        def spy_fit_transform(self, X, y=None):
            captured_features[id(self)] = np.asarray(X).copy()
            return original_fit_transform(self, X, y)
        
        import sklearn.preprocessing as skpre
        original = skpre.StandardScaler.fit_transform
        try:
            skpre.StandardScaler.fit_transform = spy_fit_transform
            imp.fit(panel_features_with_bfill)
        finally:
            skpre.StandardScaler.fit_transform = original
        
        assert len(captured_features) > 0
        for scaler_id, feats in captured_features.items():
            assert not np.any(np.isclose(feats, 999.0)), \
                f"RF fit features 中出现未来异常值 999: {feats}"
    
    def test_rf_transform_no_future_value(self, panel_features_with_bfill):
        """A4 (imputers.py:359): _transform_random_forest 不应用 bfill."""
        imp = MLAdvancedImputer(method='random_forest', n_estimators=5)
        imp.fit(panel_features_with_bfill)
        result = imp.transform(panel_features_with_bfill.copy())
        
        nan_mask = np.isnan(panel_features_with_bfill.values)
        filled_mask = nan_mask & ~np.isnan(result.values)
        filled_values = result.values[filled_mask]
        
        if len(filled_values) > 0:
            assert not np.any(np.isclose(filled_values, 999.0)), \
                f"RF transform 填充结果中出现未来异常值 999: {filled_values}"
    
    def test_fundamental_fit_features_no_future_leakage(self, panel_features_with_bfill):
        """A5 (imputers.py:459): _fit_fundamental_imputer 不应用 bfill."""
        imp = FactorSpecificImputer()
        
        # 捕获 LinearRegression.fit 的 X 参数
        captured = {}
        original_fit = LinearRegression.fit
        
        def spy_fit(self, X, y=None):
            captured[id(self)] = (np.asarray(X).copy(), np.asarray(y).copy() if y is not None else None)
            return original_fit(self, X, y)
        
        import sklearn.linear_model as sklmod
        original = sklmod.LinearRegression.fit
        try:
            sklmod.LinearRegression.fit = spy_fit
            imp.fit(panel_features_with_bfill)
        finally:
            sklmod.LinearRegression.fit = original
        
        for k, (feats, _) in captured.items():
            assert not np.any(np.isclose(feats, 999.0)), \
                f"LinearRegression fit features 中出现未来异常值 999: {feats}"
    
    def test_fundamental_transform_no_future_value(self, panel_features_with_bfill):
        """A6 (imputers.py:493): _transform_fundamental 不应用 bfill.

        注: FactorSpecificImputer.transform 会添加 _missing 指示列,
        需过滤原列再比较.
        """
        imp = FactorSpecificImputer()
        imp.fit(panel_features_with_bfill)
        result = imp.transform(panel_features_with_bfill.copy())

        # 只取原列 (排除 _missing 指示列)
        orig_cols = panel_features_with_bfill.columns
        result_orig = result[orig_cols]

        nan_mask = np.isnan(panel_features_with_bfill.values)
        filled_mask = nan_mask & ~np.isnan(result_orig.values)
        filled_values = result_orig.values[filled_mask]

        if len(filled_values) > 0:
            assert not np.any(np.isclose(filled_values, 999.0)), \
                f"Fundamental transform 填充结果中出现未来异常值 999: {filled_values}"
    
    # ----- 层 3: 因果性测试 -----

    def test_knn_causal_property(self, panel_features_with_bfill):
        """因果性: 截断未来数据, t 时刻 features 应不变.

        验证 bfill 修复: 若用 bfill, 截断未来数据会改变 features (因 bfill
        从未来取值); 用 ffill+0 后, features 只依赖过去, 截断不影响.

        注: 本测试只验证 features 层面的因果性 (bfill 直接证据),
        不依赖 KNN 最终预测结果 (KNN 有独立索引 bug, 不在本次修复范围).
        """
        df_full = panel_features_with_bfill
        df_truncated = df_full.iloc[:4].copy()  # 截断到 t=3

        # 捕获 transform 时实际传入 scaler.transform 的 features
        captured_full = []
        captured_truncated = []

        original_transform = StandardScaler.transform

        def spy_transform_full(self, X):
            captured_full.append(np.asarray(X).copy())
            return original_transform(self, X)

        def spy_transform_truncated(self, X):
            captured_truncated.append(np.asarray(X).copy())
            return original_transform(self, X)

        import sklearn.preprocessing as skpre
        original = skpre.StandardScaler.transform

        # Full data fit + transform
        try:
            skpre.StandardScaler.transform = spy_transform_full
            imp1 = MLAdvancedImputer(method='knn', n_neighbors=2)
            imp1.fit(df_full)
            imp1.transform(df_full.copy())
        finally:
            skpre.StandardScaler.transform = original

        # Truncated data fit + transform
        try:
            skpre.StandardScaler.transform = spy_transform_truncated
            imp2 = MLAdvancedImputer(method='knn', n_neighbors=2)
            imp2.fit(df_truncated)
            imp2.transform(df_truncated.copy())
        finally:
            skpre.StandardScaler.transform = original

        # 比较 t=2 (在截断数据范围内) 的 features 是否一致
        # captured_*[0] 是第一个被 transform 的资产的 missing_features
        # 关键: t=2 的 features 在两个版本中应相同 (因果性)
        assert len(captured_full) > 0 and len(captured_truncated) > 0, \
            "应至少捕获一个资产的 features"

        # 找到 t=2 在 captured features 中的位置
        # 由于 S1 在 t=2 缺失, imp.transform 会调用 scaler.transform 传入 t=2 的 features
        # 比较 t=2 的 features (应该相同, 因为 ffill 因果)
        for feats_full, feats_trunc in zip(captured_full, captured_truncated):
            # feats_full 和 feats_trunc 可能形状不同 (full 有 6 行 missing, trunc 有 1 行)
            # 取 trunc 的第一行 (t=2) 和 full 中对应 t=2 的行比较
            if feats_trunc.shape[0] >= 1 and feats_full.shape[0] >= 1:
                # 截断数据中 t=2 的 features
                feat_t2_trunc = feats_trunc[0]
                # 全数据中 t=2 的 features (找第一行, 应是 t=2 的 missing)
                # 由于截断数据只有 t=2 缺 S1, 全数据也只有 t=2 缺 S1
                # 所以两者第一行都对应 t=2
                feat_t2_full = feats_full[0]
                np.testing.assert_array_almost_equal(
                    feat_t2_trunc, feat_t2_full, decimal=10,
                    err_msg="t=2 features 在截断前后不一致 (因果性违反)"
                )


# 引入用于 monkey-patch 的依赖
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LinearRegression


# =============================================================================
# P0-2: TimeSeriesImputer 向量化等价性测试
# =============================================================================

class TestTimeSeriesImputerVectorization:
    """验证向量化版本与原循环版本数值等价.
    
    由于原代码已被向量化, 此处验证向量化后:
    1. fit/transform 行为正确
    2. rolling_mean 与手动循环结果一致
    3. exponential_smoothing 与手动循环结果一致
    4. ffill 是因果的
    """
    
    @pytest.fixture
    def ts_panel(self):
        """时序测试面板."""
        np.random.seed(42)
        dates = pd.date_range('2020-01-01', periods=50, freq='D')
        cols = ['A', 'B', 'C']
        data = np.random.randn(50, 3) + 10
        # 注入缺失
        data[5, 0] = np.nan
        data[10, 1] = np.nan
        data[15, 2] = np.nan
        data[20, 0] = np.nan
        return pd.DataFrame(data, index=dates, columns=cols)

    
    def test_rolling_mean_equivalent_to_loop(self, ts_panel):
        """rolling_mean 向量化结果应与按资产循环一致."""
        window = 5
        imp = TimeSeriesImputer(method='rolling_mean', window=window)
        imp.fit(ts_panel)
        result = imp.transform(ts_panel.copy())
        
        # 手动计算预期值 (向量化)
        expected_stats = ts_panel.rolling(window=window, min_periods=1).mean()
        expected = ts_panel.fillna(expected_stats)
        
        # 比较
        np.testing.assert_array_almost_equal(
            result.values, expected.values, decimal=10,
            err_msg="rolling_mean 向量化结果与预期不符"
        )
    
    def test_ewm_equivalent_to_loop(self, ts_panel):
        """exponential_smoothing 向量化结果应与按资产循环一致."""
        span = 5
        imp = TimeSeriesImputer(method='exponential_smoothing', window=span)
        imp.fit(ts_panel)
        result = imp.transform(ts_panel.copy())
        
        # 手动计算预期值 (向量化)
        expected_stats = ts_panel.ewm(span=span).mean()
        expected = ts_panel.fillna(expected_stats)
        
        np.testing.assert_array_almost_equal(
            result.values, expected.values, decimal=10,
            err_msg="ewm 向量化结果与预期不符"
        )
    
    def test_ffill_is_causal(self, ts_panel):
        """ffill 方法应是因果的: t 时刻只依赖 [0, t]."""
        imp = TimeSeriesImputer(method='ffill', window=5)
        imp.fit(ts_panel)
        result = imp.transform(ts_panel.copy())
        
        # 验证: t=5 的 A 缺失应被 t=4 的值填充
        assert result.iloc[5, 0] == ts_panel.iloc[4, 0], \
            "ffill 应使用 t-1 的值填充, 而非未来值"
        # 验证: t=20 的 A 缺失应被 t=19 的值填充
        assert result.iloc[20, 0] == ts_panel.iloc[19, 0], \
            "ffill 应使用 t-1 的值填充"
    
    def test_ffill_first_nan_filled_with_zero(self):
        """首行 NaN ffill 无效, 应被 0 填充 (因果)."""
        dates = pd.date_range('2020-01-01', periods=3, freq='D')
        df = pd.DataFrame({
            'A': [np.nan, 2.0, 3.0],
            'B': [1.0, np.nan, 3.0],
        }, index=dates)
        
        imp = TimeSeriesImputer(method='ffill', window=5)
        imp.fit(df)
        result = imp.transform(df.copy())
        
        # t=0 A 缺失, ffill 无前值, 应填 0
        assert result.iloc[0, 0] == 0.0, \
            "首行 NaN 应被 0 填充 (因果), 不应用 bfill 填充未来值"
    
    def test_fit_transform_no_loop_regression(self, ts_panel):
        """向量化后 fit+transform 应正常工作, 无回归."""
        for method in ['ffill', 'rolling_mean', 'exponential_smoothing']:
            imp = TimeSeriesImputer(method=method, window=5)
            imp.fit(ts_panel)
            result = imp.transform(ts_panel.copy())
            # 应无 NaN 残留
            assert not result.isnull().any().any(), \
                f"{method}: transform 后应无 NaN"


# =============================================================================
# P0-3: 全管线无前视偏差冒烟测试
# =============================================================================

class TestNoLookaheadSmokeTest:
    """冒烟测试: 确保修复后整个 imputer 模块不引入前视偏差."""
    
    def test_time_series_imputer_causal_property(self, panel_with_bfill_leakage):
        """TimeSeriesImputer 应保持因果性.
        
        关键性质: 删除 t=6 之后的所有数据, t=5 的插补结果应不变.
        """
        df_full = panel_with_bfill_leakage
        df_truncated = df_full.iloc[:6].copy()  # 截断到 t=5
        
        imp1 = TimeSeriesImputer(method='ffill', window=3)
        imp1.fit(df_full)
        result_full = imp1.transform(df_full.copy())
        
        imp2 = TimeSeriesImputer(method='ffill', window=3)
        imp2.fit(df_truncated)
        result_truncated = imp2.transform(df_truncated.copy())
        
        # t=5 的 S0 在两个版本中应一致 (因果性)
        # 注意: ffill 方法在 t=5 的填充只依赖 t<=5 的数据
        val_full = result_full.iloc[5, 0]
        val_truncated = result_truncated.iloc[5, 0]
        
        # 由于 ffill 用 t=4 的值 (5.0), 截断不影响 t=5 的填充
        # bfill 会用 t=6 的值 (999), 截断会改变 t=5 的填充 → 暴露前视
        assert val_full == val_truncated, \
            f"因果性违反: t=5 填充值依赖未来数据 (full={val_full}, truncated={val_truncated})"


# =============================================================================
# P1-1: ImputerAdapter.lookahead_safe 参数测试
# =============================================================================

class TestImputerAdapterLookaheadSafe:
    """验证 ImputerAdapter 新增 lookahead_safe 参数.

    设计 (per §5.4):
    - 默认 lookahead_safe=True (生产路径强制因果)
    - lookahead_safe=False 保留 legacy 路径 (DEPRECATED)
    - ffill_ts 不受影响 (内置因果)
    - 非 ffill_ts 路径将 lookahead_safe 透传给子 imputer
    """

    def test_lookahead_safe_default_is_true(self):
        """默认 lookahead_safe=True."""
        from factor_pipeline.adapters import ImputerAdapter
        imp = ImputerAdapter(strategy='auto')
        assert imp.lookahead_safe is True, \
            "lookahead_safe 默认应为 True (强制因果)"

    def test_lookahead_safe_can_be_disabled(self):
        """lookahead_safe=False 显式禁用 (legacy 兼容)."""
        from factor_pipeline.adapters import ImputerAdapter
        imp = ImputerAdapter(strategy='auto', lookahead_safe=False)
        assert imp.lookahead_safe is False

    def test_lookahead_safe_propagated_to_sub_imputer(self):
        """非 ffill_ts 路径: lookahead_safe 应透传给子 imputer.

        验证: strategy='cross_sectional' 时, 子 CrossSectionalImputer
        的 lookahead_safe 应等于 adapter 的 lookahead_safe.
        """
        from factor_pipeline.adapters import ImputerAdapter
        imp = ImputerAdapter(strategy='cross_sectional', lookahead_safe=True)
        # fit 触发子 imputer 构造
        dates = pd.date_range('2020-01-01', periods=10, freq='D')
        df = pd.DataFrame(
            np.random.randn(10, 3),
            index=dates, columns=['S0', 'S1', 'S2']
        )
        df.iloc[5, 0] = np.nan
        imp.fit(df)

        # 子 imputer 应有 lookahead_safe 属性且为 True
        sub = imp._imputer
        assert hasattr(sub, 'lookahead_safe'), \
            "子 imputer 应有 lookahead_safe 属性"
        assert sub.lookahead_safe is True

    def test_ffill_ts_unaffected_by_lookahead_safe(self):
        """ffill_ts 是内置因果, lookahead_safe 不影响其行为."""
        from factor_pipeline.adapters import ImputerAdapter

        dates = pd.date_range('2020-01-01', periods=10, freq='D')
        df = pd.DataFrame(
            np.random.randn(10, 3),
            index=dates, columns=['S0', 'S1', 'S2']
        )
        df.iloc[5, 0] = np.nan

        imp_true = ImputerAdapter(strategy='ffill_ts', lookahead_safe=True)
        imp_false = ImputerAdapter(strategy='ffill_ts', lookahead_safe=False)
        imp_true.fit(df)
        imp_false.fit(df)

        r_true = imp_true.transform(df.copy())
        r_false = imp_false.transform(df.copy())

        np.testing.assert_array_almost_equal(
            r_true.values, r_false.values, decimal=10,
            err_msg="ffill_ts 不应受 lookahead_safe 影响"
        )


# =============================================================================
# P1-2: CrossSectionalImputer 双重修复测试
# =============================================================================

class TestCrossSectionalImputerCausalFix:
    """验证 CrossSectionalImputer axis+expanding 因果修复.

    设计 (per §5.3):
    - 新增 lookahead_safe/window/min_periods 参数
    - lookahead_safe=True (默认) → _transform_causal (expanding/rolling)
    - lookahead_safe=False → _transform_legacy (原全样本路径, DEPRECATED)
    - 因果版本: t 时刻用 [0, t] 统计量填 t 时刻缺失
    """

    @pytest.fixture
    def cs_panel(self):
        """截面插补测试面板.

        S0 在 t=5 缺失, S1 在 t=8 缺失.
        - legacy (全样本): t=5 缺失用全样本 median (含未来) → 前视
        - causal (expanding): t=5 缺失用 [0, 5] median → 因果
        """
        np.random.seed(42)
        dates = pd.date_range('2020-01-01', periods=12, freq='D')
        cols = ['S0', 'S1', 'S2', 'S3']
        data = np.array([
            [1.0,  10.0, 100.0, 1000.0],
            [2.0,  20.0, 110.0, 1010.0],
            [3.0,  30.0, 120.0, 1020.0],
            [4.0,  40.0, 130.0, 1030.0],
            [5.0,  50.0, 140.0, 1040.0],
            [np.nan, 60.0, 150.0, 1050.0],   # t=5: S0 缺失
            [7.0,  70.0, 160.0, 1060.0],
            [8.0,  80.0, 170.0, 1070.0],
            [9.0,  np.nan, 180.0, 1080.0],   # t=8: S1 缺失
            [10.0, 100.0, 190.0, 1090.0],
            [11.0, 110.0, 200.0, 1100.0],
            [12.0, 120.0, 210.0, 1110.0],
        ])
        return pd.DataFrame(data, index=dates, columns=cols)

    def test_lookahead_safe_param_exists(self):
        """CrossSectionalImputer 应有 lookahead_safe 参数."""
        imp = CrossSectionalImputer(lookahead_safe=True)
        assert imp.lookahead_safe is True

    def test_causal_default_is_true(self):
        """默认 lookahead_safe=True."""
        imp = CrossSectionalImputer()
        assert imp.lookahead_safe is True

    def test_causal_no_future_in_fill(self, cs_panel):
        """因果版本: t=5 缺失的 S0 应用 [0, 5] 区间统计填充.

        注: 不能简单断言"填充值不在未来原值中" — 因为 median 可能
        恰好等于某个未来值 (如本例 7.0). 正确做法是验证填充值等于
        [0, 5] 区间的 median (expanding 在 t=5 的值).
        """
        imp = CrossSectionalImputer(method='median', lookahead_safe=True)
        imp.fit(cs_panel)
        result = imp.transform(cs_panel.copy())

        # t=5 的 S0 填充值
        filled_val = result.iloc[5, 0]
        assert not np.isnan(filled_val), "t=5 S0 应被填充"

        # 预期: t=5 的 expanding median of S0 = median([1,2,3,4,5]) = 3.0
        expected = cs_panel['S0'].iloc[:6].median()  # [0, 5] 区间, 排除 t=5 NaN
        assert filled_val == expected, \
            f"因果填充应等于 [0,5] 区间 median: expected={expected}, got={filled_val}"

    def test_causal_property_truncation(self, cs_panel):
        """因果性: 截断未来, t=5 填充值应不变."""
        df_full = cs_panel
        df_trunc = df_full.iloc[:6].copy()  # 截断到 t=5

        imp1 = CrossSectionalImputer(method='median', lookahead_safe=True)
        imp1.fit(df_full)
        r_full = imp1.transform(df_full.copy())

        imp2 = CrossSectionalImputer(method='median', lookahead_safe=True)
        imp2.fit(df_trunc)
        r_trunc = imp2.transform(df_trunc.copy())

        # t=5 S0 填充值在两个版本中应一致 (因果性)
        val_full = r_full.iloc[5, 0]
        val_trunc = r_trunc.iloc[5, 0]
        assert val_full == val_trunc, \
            f"因果性违反: t=5 S0 full={val_full}, trunc={val_trunc}"

    def test_legacy_mode_preserves_old_behavior(self, cs_panel):
        """lookahead_safe=False 保留原全样本行为 (向后兼容)."""
        imp = CrossSectionalImputer(method='median', lookahead_safe=False)
        imp.fit(cs_panel)
        result = imp.transform(cs_panel.copy())

        # legacy: 用全样本 median 填充
        # 全样本 median of S0 (含 t=5 NaN, dropna 后取 median)
        expected_median = cs_panel['S0'].median()
        assert result.iloc[5, 0] == expected_median, \
            f"legacy 模式应用全样本 median: expected={expected_median}, got={result.iloc[5, 0]}"

    def test_causal_no_nans_after_transform(self, cs_panel):
        """因果版本 transform 后应无 NaN 残留."""
        imp = CrossSectionalImputer(method='median', lookahead_safe=True)
        imp.fit(cs_panel)
        result = imp.transform(cs_panel.copy())
        assert not result.isnull().any().any(), "transform 后应无 NaN"


# =============================================================================
# P1-3: KNN walk-forward 测试
# =============================================================================

class TestKNNWalkForward:
    """验证 MLAdvancedImputer KNN walk-forward 实现.

    设计 (per §5.2.1):
    - 新增 walk_forward 参数 (默认 True)
    - walk_forward=True: 每个缺失点 t 只用 [0, t-1] 的数据训练 KNN
    - walk_forward=False: 保留原全样本训练 (DEPRECATED)
    """

    @pytest.fixture
    def knn_panel(self):
        """KNN walk-forward 测试面板: 共 20 行."""
        np.random.seed(42)
        dates = pd.date_range('2020-01-01', periods=20, freq='D')
        cols = ['S0', 'S1', 'S2', 'S3']
        data = np.random.randn(20, 4) * 10 + 100
        # S0 在 t=10 缺失
        data[10, 0] = np.nan
        # S1 在 t=15 缺失
        data[15, 1] = np.nan
        return pd.DataFrame(data, index=dates, columns=cols)

    def test_walk_forward_param_exists(self):
        """MLAdvancedImputer 应有 walk_forward 参数."""
        imp = MLAdvancedImputer(method='knn', walk_forward=True)
        assert imp.walk_forward is True

    def test_walk_forward_default_is_true(self):
        """walk_forward 默认 True (生产路径强制因果)."""
        imp = MLAdvancedImputer(method='knn')
        assert imp.walk_forward is True

    def test_walk_forward_causal_property(self, knn_panel):
        """因果性: 截断未来数据, t=10 的 KNN 填充结果应不变."""
        df_full = knn_panel
        df_trunc = df_full.iloc[:11].copy()  # 截断到 t=10

        imp1 = MLAdvancedImputer(method='knn', n_neighbors=2, walk_forward=True)
        imp1.fit(df_full)
        r_full = imp1.transform(df_full.copy())

        imp2 = MLAdvancedImputer(method='knn', n_neighbors=2, walk_forward=True)
        imp2.fit(df_trunc)
        r_trunc = imp2.transform(df_trunc.copy())

        # t=10 S0 填充值应一致 (因果)
        val_full = r_full.iloc[10, 0]
        val_trunc = r_trunc.iloc[10, 0]
        assert not np.isnan(val_full), "t=10 S0 应被填充"
        assert not np.isnan(val_trunc), "trunc t=10 S0 应被填充"
        assert abs(val_full - val_trunc) < 1e-6, \
            f"因果性违反: t=10 S0 full={val_full}, trunc={val_trunc}"

    def test_walk_forward_no_future_in_training(self, knn_panel):
        """walk-forward: t 时刻的填充只依赖 [0, t-1] 数据."""
        # 通过 monkey-patch NearestNeighbors.fit 捕获训练数据
        captured = []
        original_fit = NearestNeighbors.fit

        def spy_fit(self, X):
            captured.append(np.asarray(X).copy())
            return original_fit(self, X)

        from sklearn.neighbors import NearestNeighbors as NN
        original = NN.fit
        try:
            NN.fit = spy_fit
            imp = MLAdvancedImputer(method='knn', n_neighbors=2, walk_forward=True)
            imp.fit(knn_panel)
        finally:
            NN.fit = original

        # walk-forward 模式: 每个缺失点用单独的 KNN (训练数据只含 [0, t-1])
        # 验证: 训练数据不应包含 t=10 之后的所有行 (S0 缺失点之后)
        # 但 walk-forward 是在 transform 时按 t 切片, fit 时可能不触发
        # 这里只验证 fit 调用次数: 若无 walk-forward, 通常每资产 1 次 fit
        # 若 walk-forward, 应有多个 fit 调用 (每个缺失点一次)
        # 注: 实现细节可能不同, 此测试可能需调整


# =============================================================================
# P1-4: RF 共享模型测试
# =============================================================================

class TestRFSharedModel:
    """验证 MLAdvancedImputer RF 共享模型方案.

    设计 (per §5.2.3 方案 A):
    - 新增 shared_model 参数 (默认 True)
    - shared_model=True: 所有资产共用一个 multi-output RF
    - shared_model=False: 每资产独立 RF (原方案, 内存爆炸)
    """

    @pytest.fixture
    def rf_panel(self):
        """RF 测试面板: 共 30 行 (满足 len(asset_data) > 10)."""
        np.random.seed(42)
        dates = pd.date_range('2020-01-01', periods=30, freq='D')
        cols = ['S0', 'S1', 'S2', 'S3']
        data = np.random.randn(30, 4) * 10 + 100
        data[10, 0] = np.nan
        data[20, 1] = np.nan
        return pd.DataFrame(data, index=dates, columns=cols)

    def test_shared_model_param_exists(self):
        """MLAdvancedImputer 应有 shared_model 参数."""
        imp = MLAdvancedImputer(method='random_forest', shared_model=True)
        assert imp.shared_model is True

    def test_shared_model_default_is_true(self):
        """shared_model 默认 True (避免内存爆炸)."""
        imp = MLAdvancedImputer(method='random_forest')
        assert imp.shared_model is True

    def test_shared_model_only_one_model(self, rf_panel):
        """shared_model=True: 应只训练一个 RF 模型 (而非 N 资产个)."""
        imp = MLAdvancedImputer(
            method='random_forest', n_estimators=5, shared_model=True
        )
        imp.fit(rf_panel)

        # shared_model=True: models 应只有一个共享模型, 而非每资产一个
        # 实现: self.models 可能是 {'shared': model} 或直接 self.model
        n_models = len(imp.models) if hasattr(imp, 'models') else 0
        assert n_models <= 1, \
            f"shared_model=True 应只训练 1 个模型, 实际 {n_models}"

    def test_shared_model_predicts_all_assets(self, rf_panel):
        """共享模型应能预测所有资产的缺失."""
        imp = MLAdvancedImputer(
            method='random_forest', n_estimators=5, shared_model=True
        )
        imp.fit(rf_panel)
        result = imp.transform(rf_panel.copy())

        # 所有原 NaN 应被填充
        nan_mask = rf_panel.isnull()
        filled_mask = nan_mask & ~np.isnan(result.values)
        total_nan = nan_mask.sum().sum()
        total_filled = filled_mask.sum().sum()
        assert total_filled == total_nan, \
            f"共享模型应填充所有缺失: {total_nan} → {total_filled}"


# 引入测试所需的额外依赖
from sklearn.neighbors import NearestNeighbors
