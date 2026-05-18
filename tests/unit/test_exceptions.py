# -*- coding: utf-8 -*-
"""
异常体系单元测试

测试自定义异常的创建、序列化和信息完整性。
"""

import pytest
import json
from factor_pipeline.exceptions import (
    PipelineError,
    OrderValidationError,
    StepExecutionError,
    AdapterImportError,
    ConfigurationError,
    FactorTypeError,
    NeutralizationError,
    GarchFittingError,
    MigrationAlertError,
)


class TestPipelineError:
    """基础异常测试"""
    
    def test_basic_creation(self):
        """测试基本创建"""
        err = PipelineError("测试错误")
        assert err.message == "测试错误"
        assert err.step_name is None
        assert err.factor_name is None
        assert err.context == {}
    
    def test_full_creation(self):
        """测试完整参数创建"""
        err = PipelineError(
            message="步骤失败",
            step_name="imputation",
            factor_name="pb_factor",
            context={"input_shape": (100, 50)}
        )
        assert err.step_name == "imputation"
        assert err.factor_name == "pb_factor"
        assert err.context["input_shape"] == (100, 50)
    
    def test_to_dict(self):
        """测试字典序列化"""
        err = PipelineError(
            message="测试",
            step_name="test_step",
            context={"key": "value"}
        )
        d = err.to_dict()
        assert d["error_type"] == "PipelineError"
        assert d["message"] == "测试"
        assert d["step_name"] == "test_step"
        assert d["context"]["key"] == "value"
    
    def test_str_representation(self):
        """测试字符串表示"""
        err = PipelineError("错误信息", step_name="step1")
        s = str(err)
        assert "PipelineError" in s
        assert "错误信息" in s
        assert "step1" in s


class TestOrderValidationError:
    """顺序校验异常测试"""
    
    def test_creation(self):
        """测试创建"""
        err = OrderValidationError(
            message="顺序错误",
            context={
                "errors": ["去极值必须在插补之后"],
                "suggested_order": ["imputation", "outlier", "standardization"],
            }
        )
        assert err.to_dict()["error_type"] == "OrderValidationError"
        assert "errors" in err.context


class TestStepExecutionError:
    """步骤执行异常测试"""
    
    def test_with_original_error(self):
        """测试携带原始异常"""
        original = ValueError("原始错误")
        err = StepExecutionError(
            message="步骤失败",
            step_name="neutralization",
            context={"input_shape": (100, 50)},
            original_error=original
        )
        d = err.to_dict()
        assert "original_error" in d
        assert "ValueError" in d["original_error"]
    
    def test_without_original_error(self):
        """测试无原始异常"""
        err = StepExecutionError("步骤失败", step_name="imputation")
        d = err.to_dict()
        assert "original_error" not in d


class TestAdapterImportError:
    """适配器导入异常测试"""
    
    def test_creation(self):
        """测试创建"""
        err = AdapterImportError(
            message="无法导入模块",
            module_path="Factor_Imputer_v2.0",
            class_name="HierarchicalImputer"
        )
        d = err.to_dict()
        assert d["module_path"] == "Factor_Imputer_v2.0"
        assert d["class_name"] == "HierarchicalImputer"


class TestConfigurationError:
    """配置异常测试"""
    
    def test_creation(self):
        """测试创建"""
        err = ConfigurationError(
            message="配置错误",
            context={"invalid_param": "value"}
        )
        assert "配置错误" in str(err)


class TestMigrationAlertError:
    """迁移告警异常测试"""
    
    def test_full_creation(self):
        """测试完整创建"""
        err = MigrationAlertError(
            message="因子类型迁移",
            factor_name="momentum_factor",
            old_type="dynamic",
            new_type="mixed",
            confidence=0.85,
            context={"window": 24}
        )
        d = err.to_dict()
        assert d["old_type"] == "dynamic"
        assert d["new_type"] == "mixed"
        assert d["confidence"] == 0.85
        assert d["factor_name"] == "momentum_factor"


class TestExceptionHierarchy:
    """异常层次结构测试"""
    
    def test_all_inherit_pipeline_error(self):
        """测试所有异常继承 PipelineError"""
        exceptions = [
            OrderValidationError("test"),
            StepExecutionError("test"),
            AdapterImportError("test"),
            ConfigurationError("test"),
            FactorTypeError("test"),
            NeutralizationError("test"),
            GarchFittingError("test"),
            MigrationAlertError("test"),
        ]
        for exc in exceptions:
            assert isinstance(exc, PipelineError)
    
    def test_catch_all_with_base(self):
        """测试用基类捕获所有异常"""
        try:
            raise OrderValidationError("顺序错误")
        except PipelineError as e:
            assert "顺序错误" in str(e)
        
        try:
            raise StepExecutionError("执行错误")
        except PipelineError as e:
            assert "执行错误" in str(e)
