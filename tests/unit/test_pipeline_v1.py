# -*- coding: utf-8 -*-
"""
FactorProcessingPipeline (v1.0) 单元测试

使用 Mock 步骤测试流水线核心逻辑。
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import Mock

from factor_pipeline.pipeline import FactorProcessingPipeline, PipelineResult
from factor_pipeline.config import StepType, PipelineConfig, StepConfig
from factor_pipeline.exceptions import OrderValidationError


class TestPipelineCreation:
    """流水线创建测试"""
    
    def test_default_pipeline(self):
        """测试默认流水线创建"""
        pipeline = FactorProcessingPipeline.default_pipeline()
        assert len(pipeline.steps) == 5
        assert pipeline.is_fitted is False
    
    def test_from_config(self):
        """测试从配置创建"""
        config = PipelineConfig.default_config()
        pipeline = FactorProcessingPipeline(config=config)
        assert len(pipeline.steps) == 5
    
    def test_empty_pipeline(self):
        """测试空流水线"""
        pipeline = FactorProcessingPipeline(steps=[])
        assert len(pipeline.steps) == 0


class TestPipelineExecution:
    """流水线执行测试"""
    
    def test_fit_transform(self, clean_factor_data, mock_step):
        """测试拟合变换"""
        step1 = mock_step('imputer', 'imputation')
        step2 = mock_step('standardizer', 'standardization')
        
        pipeline = FactorProcessingPipeline(steps=[step1, step2], strict_order=False)
        result = pipeline.fit_transform(clean_factor_data)
        
        assert isinstance(result, pd.DataFrame)
        assert result.shape == clean_factor_data.shape
        assert step1.is_fitted is True
        assert step2.is_fitted is True
    
    def test_transform_before_fit(self, clean_factor_data, mock_step):
        """测试未拟合就变换"""
        step = mock_step('imputer', 'imputation')
        pipeline = FactorProcessingPipeline(steps=[step], strict_order=False)
        
        with pytest.raises(ValueError, match="未拟合"):
            pipeline.transform(clean_factor_data)
    
    def test_step_execution_order(self, clean_factor_data, mock_step):
        """测试步骤执行顺序"""
        execution_order = []
        
        def make_tracking_step(name, step_type):
            step = mock_step(name, step_type)
            original_transform = step.transform
            
            def tracking_transform(X, **kwargs):
                execution_order.append(name)
                return original_transform(X, **kwargs)
            
            step.transform = tracking_transform
            return step
        
        step1 = make_tracking_step('imputer', 'imputation')
        step2 = make_tracking_step('standardizer', 'standardization')
        
        pipeline = FactorProcessingPipeline(steps=[step1, step2], strict_order=False)
        
        # fit 也会调用 transform（对于非中性化步骤）
        pipeline.fit(clean_factor_data)
        
        # fit 过程中会调用 transform，所以执行顺序可能包含 fit 和 transform
        # 这里只验证 transform 阶段的顺序
        execution_order.clear()
        pipeline.transform(clean_factor_data)
        
        assert execution_order == ['imputer', 'standardizer']


class TestPipelineResult:
    """流水线结果测试"""
    
    def test_result_structure(self, clean_factor_data, mock_step):
        """测试结果结构"""
        step = mock_step('imputer', 'imputation')
        pipeline = FactorProcessingPipeline(steps=[step], strict_order=False)
        
        result = pipeline._execute(clean_factor_data)
        
        assert isinstance(result, PipelineResult)
        assert result.success is True
        assert result.final_data is not None
        assert len(result.step_results) == 1
    
    def test_result_to_dict(self, clean_factor_data, mock_step):
        """测试结果字典转换"""
        step = mock_step('imputer', 'imputation')
        pipeline = FactorProcessingPipeline(steps=[step], strict_order=False)
        
        result = pipeline._execute(clean_factor_data)
        d = result.to_dict()
        
        assert 'success' in d
        assert 'steps' in d
        assert d['success'] is True


class TestExecutionSummary:
    """执行摘要测试"""
    
    def test_summary_before_execution(self):
        """测试执行前摘要"""
        pipeline = FactorProcessingPipeline.default_pipeline()
        summary = pipeline.get_execution_summary()
        assert "尚未执行" in summary
    
    def test_summary_after_execution(self, clean_factor_data, mock_step):
        """测试执行后摘要"""
        step = mock_step('imputer', 'imputation')
        pipeline = FactorProcessingPipeline(steps=[step], strict_order=False)
        pipeline.fit_transform(clean_factor_data)
        
        summary = pipeline.get_execution_summary()
        assert "执行摘要" in summary
        assert "imputer" in summary


class TestStrictMode:
    """严格模式测试"""
    
    def test_strict_mode_stops_on_error(self, clean_factor_data, mock_step):
        """测试严格模式出错即停止"""
        step1 = mock_step('imputer', 'imputation')
        step2 = mock_step('failing', 'standardization')
        
        # 让第二个步骤失败
        def fail_transform(X, **kwargs):
            raise ValueError("模拟错误")
        
        step2.transform = fail_transform
        
        pipeline = FactorProcessingPipeline(
            steps=[step1, step2],
            strict_order=False
        )
        
        result = pipeline._execute(clean_factor_data)
        assert result.success is False
        assert len(result.errors) == 1
        assert "模拟错误" in result.errors[0]
    
    def test_non_strict_mode_continues(self, clean_factor_data, mock_step):
        """测试非严格模式继续执行"""
        # 目前 strict_order 只控制顺序校验，不控制错误处理
        # 这个测试记录当前行为
        step = mock_step('imputer', 'imputation')
        pipeline = FactorProcessingPipeline(steps=[step], strict_order=False)
        result = pipeline.fit_transform(clean_factor_data)
        assert result is not None
