# -*- coding: utf-8 -*-
"""
v2.0 配置系统单元测试（Pydantic）

测试配置验证、序列化和类型安全。
"""

import pytest
import json
import tempfile
import os

from factor_pipeline.config_v2 import (
    StepConfigV2,
    ImputationConfig,
    OutlierConfig,
    TransformationConfig,
    StandardizationConfig,
    NeutralizationConfig,
    GarchConfig,
    StaticPipelineConfig,
    DynamicPipelineConfig,
    MixedPipelineConfig,
    PipelineV2ConfigUnified,
    save_config_to_json,
    load_config_from_json,
)


class TestStepConfigV2:
    """步骤配置测试"""
    
    def test_default_creation(self):
        """测试默认创建"""
        config = StepConfigV2(step_type='imputation')
        assert config.step_type == 'imputation'
        assert config.enabled is True
        assert config.params == {}
    
    def test_with_params(self):
        """测试带参数"""
        config = StepConfigV2(
            step_type='outlier',
            params={'method': 'mad'}
        )
        assert config.params['method'] == 'mad'


class TestImputationConfig:
    """插补配置测试"""
    
    def test_default(self):
        """测试默认值"""
        config = ImputationConfig()
        assert config.strategy == 'auto'
        assert config.max_missing_ratio == 0.5
    
    def test_invalid_max_missing_ratio(self):
        """测试无效缺失比例"""
        with pytest.raises(ValueError):
            ImputationConfig(max_missing_ratio=1.5)


class TestOutlierConfig:
    """去极值配置测试"""
    
    def test_default(self):
        """测试默认值"""
        config = OutlierConfig()
        assert config.method == 'auto'
        assert config.threshold == 3.0
    
    def test_invalid_threshold(self):
        """测试无效阈值"""
        with pytest.raises(ValueError):
            OutlierConfig(threshold=0.5)
    
    def test_percentile_validation(self):
        """测试分位数验证"""
        # 有效：lower < upper
        config = OutlierConfig(lower_percentile=0.05, upper_percentile=0.95)
        assert config.lower_percentile == 0.05
        assert config.upper_percentile == 0.95
    
    def test_invalid_percentile(self):
        """测试无效分位数"""
        with pytest.raises(ValueError):
            OutlierConfig(lower_percentile=0.6, upper_percentile=0.4)


class TestGarchConfig:
    """GARCH 配置测试"""
    
    def test_default(self):
        """测试默认值"""
        config = GarchConfig()
        assert config.enabled is False
        assert config.p == 1
        assert config.q == 1
    
    def test_invalid_orders(self):
        """测试无效阶数"""
        with pytest.raises(ValueError):
            GarchConfig(p=0, q=0)
    
    def test_valid_orders(self):
        """测试有效阶数"""
        config = GarchConfig(p=2, q=1)
        assert config.p == 2
        assert config.q == 1


class TestStaticPipelineConfig:
    """静态管道配置测试"""
    
    def test_default(self):
        """测试默认值"""
        config = StaticPipelineConfig()
        assert config.name == 'static_pipeline'
        assert config.garch.enabled is False
        assert config.neutralize_before_standardize is True
    
    def test_enable_garch(self):
        """测试启用 GARCH"""
        config = StaticPipelineConfig(garch=GarchConfig(enabled=True))
        assert config.garch.enabled is True


class TestDynamicPipelineConfig:
    """动态管道配置测试"""
    
    def test_default(self):
        """测试默认值"""
        config = DynamicPipelineConfig()
        assert config.name == 'dynamic_pipeline'
        assert config.enable_transformation is False
        assert config.enable_garch is False
        assert config.decorrelation_strength == 1.0
    
    def test_invalid_decorrelation(self):
        """测试无效解耦强度"""
        with pytest.raises(ValueError):
            DynamicPipelineConfig(decorrelation_strength=1.5)


class TestPipelineV2ConfigUnified:
    """统一配置测试"""
    
    def test_default(self):
        """测试默认值"""
        config = PipelineV2ConfigUnified()
        assert config.name == 'factor_pipeline_v2'
        assert config.version == '2.0.0'
        assert config.strict_order is True
        assert config.parallel is False
    
    def test_custom_config(self):
        """测试自定义配置"""
        config = PipelineV2ConfigUnified(
            name='my_pipeline',
            parallel=True,
            max_workers=8
        )
        assert config.name == 'my_pipeline'
        assert config.parallel is True
        assert config.max_workers == 8
    
    def test_invalid_max_workers(self):
        """测试无效工作进程数"""
        with pytest.raises(ValueError):
            PipelineV2ConfigUnified(max_workers=0)
        with pytest.raises(ValueError):
            PipelineV2ConfigUnified(max_workers=20)
    
    def test_serialization(self):
        """测试序列化"""
        config = PipelineV2ConfigUnified(
            name='test',
            static=StaticPipelineConfig(garch=GarchConfig(enabled=True))
        )
        
        data = config.model_dump()
        assert data['name'] == 'test'
        assert data['static']['garch']['enabled'] is True
    
    def test_json_roundtrip(self):
        """测试 JSON 往返"""
        original = PipelineV2ConfigUnified(
            name='test',
            static=StaticPipelineConfig(garch=GarchConfig(enabled=True))
        )
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            path = f.name
        
        try:
            save_config_to_json(original, path)
            restored = load_config_from_json(path)
            
            assert restored.name == original.name
            assert restored.static.garch.enabled == original.static.garch.enabled
        finally:
            os.unlink(path)


class TestConfigValidation:
    """配置验证测试"""
    
    def test_assignment_validation(self):
        """测试赋值验证"""
        config = PipelineV2ConfigUnified()
        
        # 有效赋值
        config.max_workers = 8
        assert config.max_workers == 8
        
        # 无效赋值应该抛出异常
        with pytest.raises(ValueError):
            config.max_workers = 0
