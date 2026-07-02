# -*- coding: utf-8 -*-
"""
P3: look-ahead bias 修复测试

利用 Factor_DB 的 loaded_at 信息，确保只用发布时间 <= trade_date 的因子值
"""

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from factor_pipeline.backtest.data_bridge import DataBridge


# =============================================================================
# 测试: loaded_at 滞后处理
# =============================================================================

class TestLoadedAtLag:
    """测试 loaded_at 滞后处理，消除 look-ahead bias"""

    def test_01_basic_lag_correctness(self):
        """基本情况: 财报数据滞后发布，只在发布后才能使用"""
        # 构造测试数据: 因子数据 + loaded_at
        # 2020-01 财报，loaded_at = 2020-04 发布，所以 2020-01~2020-03 不能使用该值
        dates = pd.date_range('2020-01-01', '2020-06-01', freq='MS')
        stocks = ['AAPL', 'MSFT', 'GOOGL']

        # 因子数据 (n_stocks, n_dates) → 格式: 每个 (stock, date) 一个因子值
        factor_data = pd.DataFrame({
            '2020-01-01': [1.0, 2.0, 3.0],
            '2020-02-01': [1.1, 2.1, 3.1],
            '2020-03-01': [1.2, 2.2, 3.2],
            '2020-04-01': [1.3, 2.3, 3.3],
            '2020-05-01': [1.4, 2.4, 3.4],
            '2020-06-01': [1.5, 2.5, 3.5],
        }, index=stocks)
        factor_data.index.name = 'symbol'

        # loaded_at (每个 stock 发布日期)
        # AAPL: 2020-04-01 发布 2020-01 数据
        loaded_at_data = pd.DataFrame({
            '2020-01-01': ['2020-04-01', '2020-04-01', '2020-04-01'],
            '2020-02-01': ['2020-05-01', '2020-05-01', '2020-05-01'],
            '2020-03-01': ['2020-06-01', '2020-06-01', '2020-06-01'],
            '2020-04-01': ['2020-07-01', '2020-07-01', '2020-07-01'],
            '2020-05-01': ['2020-08-01', '2020-08-01', '2020-08-01'],
            '2020-06-01': ['2020-09-01', '2020-09-01', '2020-09-01'],
        }, index=stocks)

        # 转换 loaded_at 为 datetime
        for col in loaded_at_data.columns:
            loaded_at_data[col] = pd.to_datetime(loaded_at_data[col])

        bridge = DataBridge()
        factor_adjusted = bridge._apply_loaded_at_lag(
            factor_data, loaded_at_data, fill_missing='nan'
        )

        # 检查: loaded_at > trade_date 的因子值被剔除
        # 2020-01-01 (loaded_at=2020-04-01) → 只在 2020-04 及以后可用
        # 2020-02-01 (loaded_at=2020-05-01) → 只在 2020-05 及以后可用
        # 2020-03-01 (loaded_at=2020-06-01) → 只在 2020-06 及以后可用

        # 2020-01-01 ~ 2020-03-01: 所有因子值都还未发布 → NaN
        for date in ['2020-01-01', '2020-02-01', '2020-03-01']:
            for stock in stocks:
                assert pd.isna(factor_adjusted.loc[stock, date]), \
                    f"{stock} {date} 应该是 NaN，因为 loaded_at > trade_date"

        # 2020-04-01: 只有 2020-01 的数据已发布
        for stock in stocks:
            assert factor_adjusted.loc[stock, '2020-04-01'] == \
                   factor_data.loc[stock, '2020-01-01']

        # 2020-05-01: 2020-01 和 2020-02 的数据已发布，取最新 = 2020-02
        for stock in stocks:
            assert factor_adjusted.loc[stock, '2020-05-01'] == \
                   factor_data.loc[stock, '2020-02-01']

        # 2020-06-01: 2020-01 ~ 2020-03 的数据已发布，取最新 = 2020-03
        for stock in stocks:
            assert factor_adjusted.loc[stock, '2020-06-01'] == \
                   factor_data.loc[stock, '2020-03-01']

    def test_02_forward_fill_correct(self):
        """前向填充正确: 缺失值用最近的可见值填充"""
        dates = pd.date_range('2020-01-01', '2020-04-01', freq='MS')
        stocks = ['AAPL']

        factor_data = pd.DataFrame({
            '2020-01-01': [1.0],
            '2020-02-01': [2.0],
            '2020-03-01': [3.0],
            '2020-04-01': [4.0],
        }, index=stocks)

        loaded_at_data = pd.DataFrame({
            '2020-01-01': ['2020-03-01'],
            '2020-02-01': ['2020-04-01'],
            '2020-03-01': ['2020-05-01'],
            '2020-04-01': ['2020-06-01'],
        }, index=stocks)
        loaded_at_data = loaded_at_data.apply(pd.to_datetime)

        bridge = DataBridge()
        factor_adjusted = bridge._apply_loaded_at_lag(
            factor_data, loaded_at_data, fill_missing='ffill'
        )

        # 2020-01-01: loaded_at=2020-03-01 > trade_date → NaN → ffill 没有前值，还是 NaN
        assert pd.isna(factor_adjusted.loc['AAPL', '2020-01-01'])
        # 2020-02-01: loaded_at=2020-04-01 > trade_date → ffill 用 2020-01 仍不可见，还是 NaN
        assert pd.isna(factor_adjusted.loc['AAPL', '2020-02-01'])
        # 2020-03-01: 2020-01 数据现在可见 → 填充 1.0
        assert factor_adjusted.loc['AAPL', '2020-03-01'] == 1.0
        # 2020-04-01: 2020-02 数据现在可见 → 填充 2.0
        assert factor_adjusted.loc['AAPL', '2020-04-01'] == 2.0

    def test_03_no_lag_when_disabled(self):
        """use_loaded_at=False → 不调整，保持原始数据"""
        dates = pd.date_range('2020-01-01', '2020-03-01', freq='MS')
        stocks = ['AAPL', 'MSFT']

        factor_data = pd.DataFrame({
            '2020-01-01': [1.0, 2.0],
            '2020-02-01': [1.1, 2.1],
            '2020-03-01': [1.2, 2.2],
        }, index=stocks)

        loaded_at_data = pd.DataFrame({
            '2020-01-01': ['2020-04-01', '2020-04-01'],
            '2020-02-01': ['2020-05-01', '2020-05-01'],
            '2020-03-01': ['2020-06-01', '2020-06-01'],
        }, index=stocks)
        loaded_at_data = loaded_at_data.apply(pd.to_datetime)

        bridge = DataBridge()
        factor_original = factor_data.copy()
        factor_adjusted = bridge._apply_loaded_at_lag(
            factor_data, loaded_at_data, use_loaded_at=False
        )

        # 禁用 loaded_at → 完全不改变
        assert_frame_equal(factor_original, factor_adjusted)

    def test_04_missing_loaded_at_keeps_original(self):
        """部分 NaN loaded_at → 保持原始值"""
        dates = pd.date_range('2020-01-01', '2020-03-01', freq='MS')
        stocks = ['AAPL', 'MSFT']

        factor_data = pd.DataFrame({
            '2020-01-01': [1.0, 2.0],
            '2020-02-01': [1.1, 2.1],
            '2020-03-01': [1.2, 2.2],
        }, index=stocks)

        # AAPL 有 loaded_at，MSFT 没有 → MSFT 保持原始
        loaded_at_data = pd.DataFrame({
            '2020-01-01': ['2020-04-01', pd.NaT],
            '2020-02-01': ['2020-05-01', pd.NaT],
            '2020-03-01': ['2020-06-01', pd.NaT],
        }, index=stocks)

        bridge = DataBridge()
        factor_adjusted = bridge._apply_loaded_at_lag(factor_data, loaded_at_data)

        # MSFT 保持原始值
        for date_str in ['2020-01-01', '2020-02-01', '2020-03-01']:
            assert not pd.isna(factor_adjusted.loc['MSFT', date_str])
            assert factor_adjusted.loc['MSFT', date_str] == factor_data.loc['MSFT', date_str]

    def test_05_nan_loaded_at_no_crash(self):
        """全 NaN loaded_at → 不崩溃，保持原始数据"""
        dates = pd.date_range('2020-01-01', '2020-03-01', freq='MS')
        stocks = ['AAPL', 'MSFT']

        factor_data = pd.DataFrame({
            '2020-01-01': [1.0, 2.0],
            '2020-02-01': [1.1, 2.1],
            '2020-03-01': [1.2, 2.2],
        }, index=stocks)

        loaded_at_data = pd.DataFrame({
            '2020-01-01': [pd.NaT, pd.NaT],
            '2020-02-01': [pd.NaT, pd.NaT],
            '2020-03-01': [pd.NaT, pd.NaT],
        }, index=stocks)

        bridge = DataBridge()
        factor_adjusted = bridge._apply_loaded_at_lag(factor_data, loaded_at_data)

        # 不崩溃，形状不变
        assert factor_adjusted.shape == factor_data.shape
        # 所有值保持原始
        assert_frame_equal(factor_adjusted, factor_data)
