"""Step 3 TDD: Imputer ffill_ts 固定策略"""
import numpy as np
import pandas as pd
import pytest
from factor_pipeline.adapters import ImputerAdapter


@pytest.fixture
def panel_with_nans():
    dates = pd.date_range('2020-01-01', periods=10, freq='ME')
    stocks = ['S00', 'S01', 'S02', 'S03', 'S04']
    data = np.random.randn(10, 5) + 10
    df = pd.DataFrame(data, index=dates, columns=stocks)
    # Inject NaN: S00 has NaN at t=2, S02 at t=0
    df.iloc[2, 0] = np.nan
    df.iloc[0, 2] = np.nan
    df.iloc[5, 3] = np.nan
    return df


class TestImputerFfillTs:
    """ffill_ts: per-stock ffill → cross-sectional median for remaining NaN"""

    def test_ffill_ts_per_stock_forward_fill(self, panel_with_nans):
        """每列 (stock) 沿时间方向 ffill"""
        imp = ImputerAdapter(strategy='ffill_ts')
        imp.fit(panel_with_nans)
        result = imp.transform(panel_with_nans)

        # S00 t=2 NaN → filled by t=1
        assert not np.isnan(result.iloc[2, 0]), "t=2 S00 should be filled by ffill"
        assert result.iloc[2, 0] == panel_with_nans.iloc[1, 0]

    def test_ffill_ts_first_row_na_filled_by_cross_median(self, panel_with_nans):
        """第一行的 NaN ffill 无效 → 截面中位数填充"""
        imp = ImputerAdapter(strategy='ffill_ts')
        imp.fit(panel_with_nans)
        result = imp.transform(panel_with_nans)

        # S02 t=0 is NaN — ffill can't fill because it's the first row
        assert not np.isnan(result.iloc[0, 2]), "t=0 S02 should be filled by cross-median"
        row_median = np.nanmedian(panel_with_nans.iloc[0].values)
        expected = row_median if not np.isnan(row_median) else 0
        assert result.iloc[0, 2] == pytest.approx(expected, abs=1e-6)

    def test_ffill_ts_no_nans_after_transform(self, panel_with_nans):
        """transform 后应无 NaN"""
        imp = ImputerAdapter(strategy='ffill_ts')
        imp.fit(panel_with_nans)
        result = imp.transform(panel_with_nans)
        assert not result.isnull().any().any(), "no NaN after ffill_ts"

    def test_ffill_ts_preserves_clean_values(self, panel_with_nans):
        """非 NaN 值不变 (跨列 ffill 传播不影响非 NaN 单元)"""
        imp = ImputerAdapter(strategy='ffill_ts')
        imp.fit(panel_with_nans)
        result = imp.transform(panel_with_nans)
        # 所有非 NaN 原值应保持
        mask = panel_with_nans.notna()
        diff = (result[mask].values - panel_with_nans[mask].values).ravel()
        diff = diff[~np.isnan(diff)]
        max_abs_diff = np.max(np.abs(diff)) if len(diff) > 0 else 0
        assert max_abs_diff < 1e-10, \
            f"non-NaN values should be unchanged, max diff={max_abs_diff}"
