# -*- coding: utf-8 -*-
"""
pytest 共享配置和 fixtures

为 factor_pipeline 测试提供统一的测试数据和 mock 对象。
"""

import pytest
import pandas as pd
import numpy as np
from typing import Dict, Any


# =============================================================================
# 基础 Fixtures
# =============================================================================

@pytest.fixture
def sample_factor_data() -> pd.DataFrame:
    """标准因子数据 fixture"""
    np.random.seed(42)
    dates = pd.date_range('2020-01-01', periods=100, freq='D')
    stocks = [f'STOCK_{i:03d}' for i in range(50)]
    
    data = np.random.randn(100, 50)
    # 添加一些缺失值
    mask = np.random.random((100, 50)) < 0.05
    data[mask] = np.nan
    
    # 添加一些极值
    data[10, 5] = 10.0
    data[20, 15] = -8.0
    
    return pd.DataFrame(data, index=dates, columns=stocks)


@pytest.fixture
def sample_industry_data() -> pd.Series:
    """行业分类数据 fixture"""
    stocks = [f'STOCK_{i:03d}' for i in range(50)]
    industries = np.random.choice(
        ['银行', '医药', '科技', '消费', '能源', '地产'],
        size=50
    )
    return pd.Series(industries, index=stocks)


@pytest.fixture
def sample_market_cap() -> pd.DataFrame:
    """市值数据 fixture"""
    np.random.seed(42)
    dates = pd.date_range('2020-01-01', periods=100, freq='D')
    stocks = [f'STOCK_{i:03d}' for i in range(50)]
    
    data = np.random.lognormal(20, 1.5, (100, 50))
    return pd.DataFrame(data, index=dates, columns=stocks)


@pytest.fixture
def clean_factor_data() -> pd.DataFrame:
    """无缺失、无极值的干净数据 fixture"""
    np.random.seed(42)
    dates = pd.date_range('2020-01-01', periods=50, freq='D')
    stocks = [f'STOCK_{i:03d}' for i in range(20)]
    data = np.random.randn(50, 20)
    return pd.DataFrame(data, index=dates, columns=stocks)


@pytest.fixture
def high_missing_data() -> pd.DataFrame:
    """高缺失率数据 fixture（>30%）"""
    np.random.seed(42)
    dates = pd.date_range('2020-01-01', periods=50, freq='D')
    stocks = [f'STOCK_{i:03d}' for i in range(20)]
    
    data = np.random.randn(50, 20)
    mask = np.random.random((50, 20)) < 0.35
    data[mask] = np.nan
    
    return pd.DataFrame(data, index=dates, columns=stocks)


@pytest.fixture
def extreme_outlier_data() -> pd.DataFrame:
    """含极端异常值数据 fixture"""
    np.random.seed(42)
    dates = pd.date_range('2020-01-01', periods=50, freq='D')
    stocks = [f'STOCK_{i:03d}' for i in range(20)]
    
    data = np.random.randn(50, 20)
    # 添加多个极端值
    data[5, 3] = 50.0
    data[10, 7] = -40.0
    data[15, 12] = 30.0
    data[25, 18] = -35.0
    
    return pd.DataFrame(data, index=dates, columns=stocks)


# =============================================================================
# Mock Fixtures
# =============================================================================

@pytest.fixture
def mock_imputer():
    """Mock 插补器"""
    from unittest.mock import Mock
    imputer = Mock()
    imputer.name = 'mock_imputer'
    imputer.step_type = 'imputation'
    imputer.is_fitted = False
    
    def mock_fit(X, **kwargs):
        imputer.is_fitted = True
        return imputer
    
    def mock_transform(X, **kwargs):
        return X.fillna(X.median())
    
    def mock_fit_transform(X, **kwargs):
        imputer.fit(X, **kwargs)
        return imputer.transform(X, **kwargs)
    
    def mock_get_stats():
        return {'strategy': 'median'}
    
    imputer.fit = mock_fit
    imputer.transform = mock_transform
    imputer.fit_transform = mock_fit_transform
    imputer.get_stats = mock_get_stats
    
    return imputer


@pytest.fixture
def mock_step():
    """Mock 通用步骤"""
    from unittest.mock import Mock
    
    def create_mock_step(name: str, step_type: str):
        step = Mock()
        step.name = name
        step.step_type = step_type
        step.is_fitted = False
        
        def mock_fit(X, **kwargs):
            step.is_fitted = True
            return step
        
        def mock_transform(X, **kwargs):
            return X
        
        def mock_get_stats():
            return {}
        
        step.fit = mock_fit
        step.transform = mock_transform
        step.get_stats = mock_get_stats
        
        return step
    
    return create_mock_step


# =============================================================================
# pytest 配置
# =============================================================================

def pytest_configure(config):
    """pytest 全局配置"""
    config.addinivalue_line(
        "markers", "unit: 单元测试（无外部依赖）"
    )
    config.addinivalue_line(
        "markers", "integration: 集成测试（需要子模块）"
    )
    config.addinivalue_line(
        "markers", "slow: 慢速测试（性能测试等）"
    )
