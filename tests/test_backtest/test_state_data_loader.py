# -*- coding: utf-8 -*-
"""StateDataLoader 测试 (RESEARCH_NOTES E7 §3.1)

12 个 A 股状态变量加载器, 5 类 (市场微观结构/宏观/资金面/情绪/风险).

TDD Red 阶段: 测试先于实现.

设计:
- akshare 是可选依赖, 不可用时降级为合成数据
- 测试不依赖真实 akshare 网络请求, 用 source='synthetic' 或 mock
"""
import sys
import pytest
import numpy as np
import pandas as pd
from contextlib import ExitStack
from unittest.mock import patch, MagicMock


# ============================================================
# 辅助函数
# ============================================================

def make_synthetic_state_df(n_obs: int = 300, seed: int = 42) -> pd.DataFrame:
    """生成 12 列合成状态变量 DataFrame (用于 MarkovRegimeIdentifier 测试)"""
    from factor_pipeline.backtest.state_data_loader import StateDataLoader
    rng = np.random.default_rng(seed)
    dates = pd.date_range('2020-01-01', periods=n_obs, freq='B')
    data = {}
    for var in StateDataLoader.ALL_VARIABLES:
        data[var] = rng.normal(0, 1, n_obs)
    return pd.DataFrame(data, index=dates)


# ============================================================
# TestStateDataLoader
# ============================================================

class TestStateDataLoader:
    """StateDataLoader 测试 (RESEARCH_NOTES E7 §3.1.8)"""

    def test_01_disabled_no_op(self):
        """enable=False 时 fit 是 no-op, load 返回空 DataFrame"""
        from factor_pipeline.backtest.state_data_loader import StateDataLoader
        loader = StateDataLoader(enable=False)
        result = loader.fit('2020-01-01', '2020-12-31')
        assert result is loader  # fit returns self
        data = loader.load_12_state_variables()
        assert isinstance(data, pd.DataFrame)
        assert data.empty  # empty when disabled
        # diagnostics should reflect disabled state
        diag = loader.get_diagnostics()
        assert diag['enabled'] is False

    def test_02_variable_categories_complete(self):
        """5 类共 12 变量"""
        from factor_pipeline.backtest.state_data_loader import StateDataLoader
        assert len(StateDataLoader.ALL_VARIABLES) == 12
        assert len(StateDataLoader.VARIABLE_CATEGORIES) == 5
        expected_cats = {
            'liquidity', 'sentiment', 'capital_flow',
            'macro_regime', 'style_regime',
        }
        assert set(StateDataLoader.VARIABLE_CATEGORIES.keys()) == expected_cats
        total = sum(len(vs) for vs in StateDataLoader.VARIABLE_CATEGORIES.values())
        assert total == 12

    def test_03_get_variable_metadata_structure(self):
        """元数据含 category/definition/source"""
        from factor_pipeline.backtest.state_data_loader import StateDataLoader
        loader = StateDataLoader(
            enable=True, source='synthetic', min_observations=100,
        )
        loader.fit('2020-01-01', '2020-12-31')
        meta = loader.get_variable_metadata()
        assert isinstance(meta, dict)
        assert len(meta) == 12
        for var, info in meta.items():
            assert 'category' in info, f"{var} missing 'category'"
            assert 'definition' in info, f"{var} missing 'definition'"
            assert 'source' in info, f"{var} missing 'source'"

    def test_04_missing_rate_threshold(self):
        """缺失率 > 5% 标记为不可靠"""
        from factor_pipeline.backtest.state_data_loader import StateDataLoader
        loader = StateDataLoader(
            enable=True, source='synthetic',
            min_observations=100, max_missing_rate=0.05,
        )
        loader.fit('2020-01-01', '2020-12-31')
        # Inject high missing rate into one variable (use .loc to avoid CoW issue)
        n = len(loader._data)
        cut = int(n * 0.15)
        loader._data.loc[loader._data.index[:cut], 'market_turnover'] = np.nan
        diag = loader.get_diagnostics()
        assert 'unreliable_variables' in diag
        assert 'market_turnover' in diag['unreliable_variables']
        assert diag['missing_rates']['market_turnover'] > 0.05

    def test_05_get_diagnostics_structure(self):
        """诊断含 n_observations/missing_rates/unreliable_variables"""
        from factor_pipeline.backtest.state_data_loader import StateDataLoader
        loader = StateDataLoader(
            enable=True, source='synthetic', min_observations=100,
        )
        loader.fit('2020-01-01', '2020-12-31')
        diag = loader.get_diagnostics()
        assert isinstance(diag, dict)
        assert diag['enabled'] is True
        assert diag['loaded'] is True
        assert 'n_observations' in diag
        assert 'n_variables' in diag
        assert 'missing_rates' in diag
        assert 'unreliable_variables' in diag
        assert 'source' in diag
        assert diag['n_variables'] == 12

    def test_06_min_observations_enforced(self):
        """观测不足时报错 (min_observations 太大)"""
        from factor_pipeline.backtest.state_data_loader import StateDataLoader
        loader = StateDataLoader(
            enable=True, source='synthetic',
            min_observations=10000,  # far exceeds synthetic data length
        )
        with pytest.raises(ValueError):
            loader.fit('2020-01-01', '2020-06-30')

    def test_07_akshare_unavailable_fallback(self):
        """akshare 不可用时降级为合成数据"""
        from factor_pipeline.backtest.state_data_loader import StateDataLoader
        loader = StateDataLoader(
            enable=True, source='akshare', min_observations=100,
        )
        # Mock akshare to be unavailable (sys.modules[name] = None raises ImportError)
        with patch.dict(sys.modules, {'akshare': None}):
            result = loader.fit('2020-01-01', '2020-12-31')
            assert result is loader
            data = loader.load_12_state_variables()
            assert isinstance(data, pd.DataFrame)
            assert len(data.columns) == 12
            diag = loader.get_diagnostics()
            assert diag['loaded'] is True
            # Should indicate fallback was used
            assert diag.get('fallback_used', False) is True

    # ============================================================
    # akshare 真实接口测试 (mock, 不依赖真实网络)
    # ============================================================

    def test_08_akshare_import_error_fallback(self):
        """akshare import 失败时降级合成, _fallback_used=True, 12 列完整

        验证:
        - import 失败 → 走 _generate_synthetic 路径
        - _fallback_used 为 True
        - 数据完整 (12 列, 无 NaN, 因为合成数据本身就是完整的)
        """
        from factor_pipeline.backtest.state_data_loader import StateDataLoader
        loader = StateDataLoader(
            enable=True, source='akshare', min_observations=100,
        )
        # sys.modules['akshare'] = None 会让 `import akshare` 抛 ImportError
        with patch.dict(sys.modules, {'akshare': None}):
            loader.fit('2020-01-01', '2020-12-31')

        diag = loader.get_diagnostics()
        assert diag['loaded'] is True
        assert diag['fallback_used'] is True
        data = loader.load_12_state_variables()
        # 12 列完整
        assert len(data.columns) == 12
        # 列顺序 = ALL_VARIABLES
        assert list(data.columns) == StateDataLoader.ALL_VARIABLES
        # 合成数据无 NaN
        assert not data.isna().any().any()

    def test_09_akshare_partial_success(self):
        """akshare 可用且部分 API 成功: 混合真实+合成数据, _fallback_used=False

        验证:
        - 3 个变量成功 (返回真实 Series) → 列含真实数据
        - 9 个变量失败 (抛 Exception) → 列用合成数据填充
        - _fallback_used 为 False (因为至少 1 个成功)
        - 12 列完整, 无全 NaN 列
        """
        from factor_pipeline.backtest.state_data_loader import StateDataLoader

        fake_ak = MagicMock()
        dates = pd.bdate_range('2020-01-01', '2020-12-31')
        # 用常数 42.0 标记真实数据, 便于断言
        real_series = pd.Series(42.0, index=dates)

        # 成功变量: 3 个, 覆盖 3 个不同类别
        success_vars = {
            'market_turnover',     # liquidity
            'northbound_flow',     # capital_flow
            'cpi_surprise',        # macro_regime
        }

        with patch.dict(sys.modules, {'akshare': fake_ak}):
            loader = StateDataLoader(
                enable=True, source='akshare', min_observations=100,
            )
            # 批量 patch 所有 12 个 _load_<var> 方法
            with ExitStack() as stack:
                for var in StateDataLoader.ALL_VARIABLES:
                    method_name = f'_load_{var}'
                    if var in success_vars:
                        stack.enter_context(patch.object(
                            loader, method_name,
                            return_value=real_series.copy(),
                        ))
                    else:
                        stack.enter_context(patch.object(
                            loader, method_name,
                            side_effect=Exception("API failed"),
                        ))
                loader.fit('2020-01-01', '2020-12-31')

        diag = loader.get_diagnostics()
        # 至少 1 个变量成功, _fallback_used 必须为 False
        assert diag['fallback_used'] is False
        data = loader.load_12_state_variables()
        # 12 列完整
        assert len(data.columns) == 12
        # 成功列含真实数据 (值 == 42.0)
        for var in success_vars:
            assert not data[var].isna().all(), f"{var} 应有真实数据"
            # 真实数据值应等于 42.0 (允许少量 NaN 来自 reindex, 但合成填充列不会是 42)
            non_nan = data[var].dropna()
            assert (non_nan == 42.0).all(), (
                f"{var} 应为真实数据 (42.0), 实际: {non_nan.unique()[:5]}"
            )
        # 失败列应有合成数据 (非 NaN, 且不等于 42.0)
        for var in StateDataLoader.ALL_VARIABLES:
            if var in success_vars:
                continue
            assert not data[var].isna().all(), f"{var} 应有合成数据"
            # 合成数据 ~ N(0,1), 不应全等于 42.0
            non_nan = data[var].dropna()
            assert not (non_nan == 42.0).all(), (
                f"{var} 不应为真实数据 (42.0)"
            )

    def test_10_fallback_flag_false_when_akshare_succeeds(self):
        """akshare 全部 12 个 API 成功: _fallback_used=False, 全为真实数据

        验证:
        - 所有 12 个 _load_<var> 返回真实 Series
        - _fallback_used 为 False
        - 12 列完整, 全为真实数据 (== 42.0)
        """
        from factor_pipeline.backtest.state_data_loader import StateDataLoader

        fake_ak = MagicMock()
        dates = pd.bdate_range('2020-01-01', '2020-12-31')
        # 用常数 42.0 标记真实数据
        real_series = pd.Series(42.0, index=dates)

        with patch.dict(sys.modules, {'akshare': fake_ak}):
            loader = StateDataLoader(
                enable=True, source='akshare', min_observations=100,
            )
            # patch 所有 12 个 _load_<var> 都成功
            with ExitStack() as stack:
                for var in StateDataLoader.ALL_VARIABLES:
                    method_name = f'_load_{var}'
                    stack.enter_context(patch.object(
                        loader, method_name,
                        return_value=real_series.copy(),
                    ))
                loader.fit('2020-01-01', '2020-12-31')

        diag = loader.get_diagnostics()
        assert diag['fallback_used'] is False
        data = loader.load_12_state_variables()
        assert len(data.columns) == 12
        # 所有列应为真实数据 (42.0)
        for var in StateDataLoader.ALL_VARIABLES:
            non_nan = data[var].dropna()
            assert not non_nan.empty, f"{var} 不应为空"
            assert (non_nan == 42.0).all(), (
                f"{var} 应为真实数据 (42.0), 实际: {non_nan.unique()[:5]}"
            )

    def test_11_akshare_all_api_fail_fallback(self):
        """akshare 可用但全部 API 调用失败: 降级合成, _fallback_used=True

        验证:
        - 所有 12 个 _load_<var> 抛 Exception
        - _fallback_used 为 True (因为没有任何成功列)
        - 12 列合成数据完整
        """
        from factor_pipeline.backtest.state_data_loader import StateDataLoader

        fake_ak = MagicMock()

        with patch.dict(sys.modules, {'akshare': fake_ak}):
            loader = StateDataLoader(
                enable=True, source='akshare', min_observations=100,
            )
            # patch 所有 12 个 _load_<var> 都抛异常
            with ExitStack() as stack:
                for var in StateDataLoader.ALL_VARIABLES:
                    method_name = f'_load_{var}'
                    stack.enter_context(patch.object(
                        loader, method_name,
                        side_effect=Exception("API failed"),
                    ))
                loader.fit('2020-01-01', '2020-12-31')

        diag = loader.get_diagnostics()
        # 全部失败 → 降级合成
        assert diag['fallback_used'] is True
        data = loader.load_12_state_variables()
        assert len(data.columns) == 12
        # 合成数据无 NaN
        assert not data.isna().any().any()
