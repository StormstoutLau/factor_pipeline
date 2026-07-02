# -*- coding: utf-8 -*-
"""
配置系统单元测试

测试 PipelineConfig、StepConfig 的创建、序列化和验证。
"""

import pytest
import json
from dataclasses import asdict

from factor_pipeline.config import PipelineConfig, StepConfig, StepType


class TestStepConfig:
    """步骤配置测试"""
    
    def test_default_creation(self):
        """测试默认创建"""
        config = StepConfig(step_type=StepType.IMPUTATION)
        assert config.step_type == StepType.IMPUTATION
        assert config.enabled is True
        assert config.params == {}
    
    def test_creation_with_params(self):
        """测试带参数创建"""
        config = StepConfig(
            step_type=StepType.OUTLIER_DETECTION,
            params={'method': 'mad', 'threshold': 3.0}
        )
        assert config.params['method'] == 'mad'
        assert config.params['threshold'] == 3.0
    
    def test_disabled_step(self):
        """测试禁用步骤"""
        config = StepConfig(
            step_type=StepType.TRANSFORMATION,
            enabled=False
        )
        assert config.enabled is False
    
    def test_to_dict(self):
        """测试转换为字典"""
        config = StepConfig(
            step_type=StepType.STANDARDIZATION,
            params={'method': 'z_score'}
        )
        d = asdict(config)
        assert d['step_type'] == StepType.STANDARDIZATION
        assert d['params']['method'] == 'z_score'


class TestPipelineConfig:
    """流水线配置测试"""
    
    def test_default_creation(self):
        """测试默认创建"""
        config = PipelineConfig()
        assert config.name == "factor_processing_pipeline"
        assert config.description == ""
        assert config.strict_order is True
    
    def test_creation_with_steps(self):
        """测试带步骤创建"""
        steps = [
            StepConfig(step_type=StepType.IMPUTATION),
            StepConfig(step_type=StepType.OUTLIER_DETECTION),
            StepConfig(step_type=StepType.STANDARDIZATION),
        ]
        config = PipelineConfig(steps=steps)
        assert len(config.steps) == 3
    
    def test_default_config(self):
        """测试默认配置工厂方法"""
        config = PipelineConfig.default_config()
        assert len(config.steps) == 5
        
        step_types = [s.step_type for s in config.steps]
        assert StepType.IMPUTATION in step_types
        assert StepType.OUTLIER_DETECTION in step_types
        assert StepType.TRANSFORMATION in step_types
        assert StepType.STANDARDIZATION in step_types
        assert StepType.NEUTRALIZATION in step_types
    
    def test_from_dict(self):
        """测试从字典创建"""
        data = {
            'name': 'test_pipeline',
            'description': '测试流水线',
            'steps': [
                {
                    'step_type': 'imputation',
                    'params': {'strategy': 'median'}
                },
                {
                    'step_type': 'standardization',
                    'params': {'method': 'z_score'}
                }
            ]
        }
        config = PipelineConfig.from_dict(data)
        assert config.name == 'test_pipeline'
        assert len(config.steps) == 2
        assert config.steps[0].params['strategy'] == 'median'
    
    def test_to_dict(self):
        """测试转换为字典"""
        config = PipelineConfig.default_config()
        d = config.to_dict()
        assert d['name'] == 'default_factor_pipeline'
        assert 'steps' in d
        assert len(d['steps']) == 5
    
    def test_serialization_roundtrip(self):
        """测试序列化往返"""
        original = PipelineConfig.default_config()
        d = original.to_dict()
        restored = PipelineConfig.from_dict(d)
        
        assert restored.name == original.name
        assert len(restored.steps) == len(original.steps)
        for i, step in enumerate(restored.steps):
            assert step.step_type == original.steps[i].step_type
            assert step.enabled == original.steps[i].enabled


class TestStepType:
    """步骤类型枚举测试"""
    
    def test_all_types_exist(self):
        """测试所有类型存在"""
        # 实际值是 'outlier' 而非 'outlier_detection'
        expected = ['imputation', 'outlier', 'transformation', 
                    'standardization', 'neutralization']
        actual = [s.value for s in StepType]
        for e in expected:
            assert e in actual
    
    def test_type_values(self):
        """测试类型值"""
        assert StepType.IMPUTATION.value == 'imputation'
        assert StepType.OUTLIER_DETECTION.value == 'outlier'
        assert StepType.TRANSFORMATION.value == 'transformation'
        assert StepType.STANDARDIZATION.value == 'standardization'
        assert StepType.NEUTRALIZATION.value == 'neutralization'
