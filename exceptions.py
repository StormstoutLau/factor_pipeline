# -*- coding: utf-8 -*-
"""
自定义异常体系

为 factor_pipeline 提供结构化、可追踪的异常处理机制。
所有异常均包含上下文信息，便于调试和日志记录。
"""

from typing import Any, Optional


class PipelineError(Exception):
    """流水线基础异常
    
    所有流水线异常的基类，提供统一的上下文信息格式。
    
    Attributes
    ----------
    message : str
        错误描述
    step_name : str | None
        发生错误的步骤名
    factor_name : str | None
        发生错误的因子名
    context : dict
        附加上下文信息（如输入形状、缺失率等）
    """
    
    def __init__(
        self,
        message: str,
        step_name: Optional[str] = None,
        factor_name: Optional[str] = None,
        context: Optional[dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.step_name = step_name
        self.factor_name = factor_name
        self.context = context or {}
    
    def to_dict(self) -> dict[str, Any]:
        """将异常转换为字典格式（便于 JSON 序列化）"""
        return {
            'error_type': self.__class__.__name__,
            'message': self.message,
            'step_name': self.step_name,
            'factor_name': self.factor_name,
            'context': self.context,
        }
    
    def __str__(self) -> str:
        parts = [f"[{self.__class__.__name__}] {self.message}"]
        if self.step_name:
            parts.append(f"Step: {self.step_name}")
        if self.factor_name:
            parts.append(f"Factor: {self.factor_name}")
        if self.context:
            parts.append(f"Context: {self.context}")
        return " | ".join(parts)


class OrderValidationError(PipelineError):
    """处理顺序校验失败
    
    当流水线步骤顺序违反学术规则时抛出。
    
    Examples
    --------
    >>> raise OrderValidationError(
    ...     "去极值必须在插补之后",
    ...     step_name="outlier_detection",
    ...     context={"violated_rule": "IMPUTATION_BEFORE_OUTLIER"}
    ... )
    """
    pass


class StepExecutionError(PipelineError):
    """步骤执行失败
    
    当某个处理步骤执行过程中发生错误时抛出。
    自动捕获输入数据的统计信息以便调试。
    """
    
    def __init__(
        self,
        message: str,
        step_name: Optional[str] = None,
        factor_name: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
        original_error: Optional[Exception] = None
    ):
        super().__init__(message, step_name, factor_name, context)
        self.original_error = original_error
    
    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        if self.original_error:
            result['original_error'] = f"{type(self.original_error).__name__}: {self.original_error}"
        return result


class AdapterImportError(PipelineError):
    """适配器导入失败（子模块缺失）
    
    当外部子模块（如 Factor_Imputer_v2.0）无法导入时抛出。
    提示用户安装缺失的依赖或检查路径配置。
    """
    
    def __init__(
        self,
        message: str,
        module_path: Optional[str] = None,
        class_name: Optional[str] = None,
        context: Optional[dict[str, Any]] = None
    ):
        super().__init__(message, context=context)
        self.module_path = module_path
        self.class_name = class_name
    
    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result['module_path'] = self.module_path
        result['class_name'] = self.class_name
        return result


class ConfigurationError(PipelineError):
    """配置错误
    
    当流水线配置参数非法或不一致时抛出。
    在初始化阶段即捕获错误，避免运行时失败。
    """
    pass


class FactorTypeError(PipelineError):
    """因子类型错误
    
    当因子数据格式不符合要求时抛出
    （如空 DataFrame、非数值类型、索引不匹配等）。
    """
    pass


class NeutralizationError(PipelineError):
    """中性化失败
    
    当中性化步骤失败时抛出（如行业数据缺失、回归奇异等）。
    """
    pass


class GarchFittingError(PipelineError):
    """GARCH 模型拟合失败
    
    当 GARCH 模型无法收敛或数据不满足条件时抛出。
    """
    pass


class MigrationAlertError(PipelineError):
    """因子迁移告警
    
    当因子类型发生显著漂移时抛出（非致命错误，用于告警）。
    """
    
    def __init__(
        self,
        message: str,
        factor_name: Optional[str] = None,
        old_type: Optional[str] = None,
        new_type: Optional[str] = None,
        confidence: Optional[float] = None,
        context: Optional[dict[str, Any]] = None
    ):
        super().__init__(message, factor_name=factor_name, context=context)
        self.old_type = old_type
        self.new_type = new_type
        self.confidence = confidence
    
    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result['old_type'] = self.old_type
        result['new_type'] = self.new_type
        result['confidence'] = self.confidence
        return result
