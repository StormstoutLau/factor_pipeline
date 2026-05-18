# -*- coding: utf-8 -*-
"""
因子处理统一流水线核心
实现顺序校验、步骤执行、状态追踪
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import pandas as pd
import numpy as np
import time
import logging
from collections import OrderedDict

from .config import StepType, PipelineConfig, StepConfig, VALID_STEP_ORDERS
from .adapters import PipelineStep, ImputerAdapter, ProcessingAdapter, NeutralizerAdapter
from .exceptions import OrderValidationError, StepExecutionError, FactorTypeError

logger = logging.getLogger(__name__)


class PipelineOrderValidator:
    """
    流水线顺序校验器
    
    核心规则（基于学术理论与业界实践）:
    1. IMPUTATION 必须是第一步
       - 原因: 去极值(MAD/分位数)需要完整数据计算统计量
       - 缺失数据会导致阈值计算有偏
    
    2. OUTLIER_DETECTION 必须在 TRANSFORMATION/STANDARDIZATION 之前
       - 原因: 极值会扭曲变换参数(如Box-Cox的lambda估计)
       - 极值会显著影响标准化后的均值和方差
    
    3. NEUTRALIZATION 必须是最后一步
       - 原因: 中性化后的残差不应再进行分布变换
       - 中性化基于原始尺度的回归，变换会破坏线性关系
    
    4. 不允许的顺序示例:
       - OUTLIER → IMPUTATION (x)  去极值基于不完整数据
       - STANDARDIZATION → OUTLIER (x)  标准化后极值定义改变
       - NEUTRALIZATION → TRANSFORMATION (x) 破坏中性化效果
    """
    
    # 步骤间的依赖关系: {步骤: [必须在它之前的步骤]}
    DEPENDENCIES = {
        StepType.OUTLIER_DETECTION: [StepType.IMPUTATION],
        StepType.TRANSFORMATION: [StepType.IMPUTATION, StepType.OUTLIER_DETECTION],
        StepType.STANDARDIZATION: [StepType.IMPUTATION, StepType.OUTLIER_DETECTION],
        StepType.NEUTRALIZATION: [StepType.IMPUTATION],
    }
    
    # 步骤间的互斥关系（某些步骤不能连续出现）
    EXCLUSIONS = [
        # [StepType.STANDARDIZATION, StepType.OUTLIER_DETECTION],  # 标准化后不应再去极值
    ]
    
    @classmethod
    def validate(cls, steps: List[StepType], strict: bool = True) -> Tuple[bool, List[str]]:
        """
        验证步骤顺序是否合法
        
        Parameters:
        -----------
        steps : List[StepType]
            步骤类型列表
        strict : bool
            是否严格模式（False时只检查关键依赖）
        
        Returns:
        --------
        is_valid : bool
            是否通过验证
        errors : List[str]
            错误信息列表
        """
        errors = []
        
        if not steps:
            errors.append("步骤列表为空")
            return False, errors
        
        # 1. 检查第一步必须是插补（如果存在缺失值处理需求）
        if StepType.IMPUTATION in steps and steps[0] != StepType.IMPUTATION:
            errors.append(
                f"顺序错误: 第一步必须是插补(IMPUTATION)，当前第一步是 {steps[0].value}\n"
                f"原因: 去极值和标准化需要基于完整数据计算统计量，"
                f"缺失数据会导致阈值/参数估计有偏。"
            )
        
        # 2. 检查依赖关系
        for i, step in enumerate(steps):
            required_before = cls.DEPENDENCIES.get(step, [])
            for req in required_before:
                if req in steps:
                    req_idx = steps.index(req)
                    if req_idx > i:
                        errors.append(
                            f"顺序错误: {step.value} 必须在 {req.value} 之后\n"
                            f"原因: {cls._get_reason(step, req)}"
                        )
        
        # 3. 检查互斥关系
        for j in range(len(steps) - 1):
            pair = [steps[j], steps[j + 1]]
            for exclusion in cls.EXCLUSIONS:
                if pair == list(exclusion):
                    errors.append(
                        f"顺序错误: {steps[j].value} 后不能直接接 {steps[j+1].value}\n"
                        f"原因: 这两个步骤连续执行会产生矛盾效果"
                    )
        
        # 4. 严格模式: 检查是否在预定义的有效顺序列表中
        if strict:
            is_valid_order = any(
                cls._is_subsequence(steps, valid_order) 
                for valid_order in VALID_STEP_ORDERS
            )
            if not is_valid_order and len(errors) == 0:
                errors.append(
                    f"顺序警告: 当前顺序 {' → '.join(s.value for s in steps)} "
                    f"不在预定义的标准顺序列表中\n"
                    f"标准顺序示例: imputation → outlier → transformation → standardization → neutralization"
                )
        
        return len(errors) == 0, errors
    
    @classmethod
    def _is_subsequence(cls, sub: List[StepType], full: List[StepType]) -> bool:
        """检查 sub 是否是 full 的子序列（保持相对顺序）"""
        it = iter(full)
        return all(step in it for step in sub)
    
    @classmethod
    def _get_reason(cls, step: StepType, required: StepType) -> str:
        """获取顺序要求的原因说明"""
        reasons = {
            (StepType.OUTLIER_DETECTION, StepType.IMPUTATION): 
                "去极值(MAD/分位数)需要完整数据计算统计量，缺失值会导致阈值估计有偏",
            (StepType.TRANSFORMATION, StepType.IMPUTATION): 
                "变换参数(如Box-Cox lambda)需要基于完整数据估计",
            (StepType.TRANSFORMATION, StepType.OUTLIER_DETECTION): 
                "极值会严重扭曲变换参数估计，应先去除极值",
            (StepType.STANDARDIZATION, StepType.IMPUTATION): 
                "标准化需要完整数据计算均值和标准差",
            (StepType.STANDARDIZATION, StepType.OUTLIER_DETECTION): 
                "极值会显著影响标准化后的分布，应先去除",
            (StepType.NEUTRALIZATION, StepType.IMPUTATION): 
                "中性化回归需要完整数据，缺失值会导致回归系数有偏",
        }
        return reasons.get((step, required), "必须保持此顺序以确保统计正确性")
    
    @classmethod
    def suggest_correction(cls, steps: List[StepType]) -> List[StepType]:
        """
        建议修正后的顺序
        
        算法:
        1. 确保 IMPUTATION 在最前面
        2. OUTLIER_DETECTION 在 TRANSFORMATION/STANDARDIZATION 之前
        3. NEUTRALIZATION 在最后
        """
        # 按优先级排序
        priority = {
            StepType.IMPUTATION: 0,
            StepType.OUTLIER_DETECTION: 1,
            StepType.TRANSFORMATION: 2,
            StepType.STANDARDIZATION: 3,
            StepType.NEUTRALIZATION: 4,
        }
        return sorted(steps, key=lambda s: priority.get(s, 99))


@dataclass
class StepResult:
    """单步执行结果"""
    step_name: str
    step_type: str
    input_shape: Tuple[int, ...]
    output_shape: Tuple[int, ...]
    execution_time: float
    missing_count_before: int
    missing_count_after: int
    stats: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class PipelineResult:
    """流水线完整执行结果"""
    success: bool
    final_data: Optional[pd.DataFrame] = None
    step_results: List[StepResult] = field(default_factory=list)
    total_time: float = 0.0
    errors: List[str] = field(default_factory=list)
    config: Optional[PipelineConfig] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'success': self.success,
            'total_time': self.total_time,
            'errors': self.errors,
            'steps': [
                {
                    'step_name': r.step_name,
                    'step_type': r.step_type,
                    'input_shape': r.input_shape,
                    'output_shape': r.output_shape,
                    'execution_time': r.execution_time,
                    'missing_before': r.missing_count_before,
                    'missing_after': r.missing_count_after,
                }
                for r in self.step_results
            ]
        }


class FactorProcessingPipeline:
    """
    因子处理统一流水线
    
    将三个 v2.0 模块整合为统一的处理流程，
    内置顺序校验确保学术正确性。
    
    Usage:
        # 方式1: 使用默认配置
        pipeline = FactorProcessingPipeline.default_pipeline()
        result = pipeline.fit_transform(factor_data)
        
        # 方式2: 自定义步骤
        pipeline = FactorProcessingPipeline([
            ImputerAdapter(strategy='auto'),
            ProcessingAdapter(process_type='outlier', method='mad'),
            ProcessingAdapter(process_type='standardization', method='z_score'),
            NeutralizerAdapter(industry_data=industry_series),
        ])
        result = pipeline.fit_transform(factor_data)
    """
    
    def __init__(self, 
                 steps: Optional[List[PipelineStep]] = None,
                 config: Optional[PipelineConfig] = None,
                 strict_order: bool = True):
        """
        初始化流水线
        
        Parameters:
        -----------
        steps : List[PipelineStep], optional
            自定义步骤列表
        config : PipelineConfig, optional
            配置对象
        strict_order : bool
            是否启用严格顺序校验
        """
        self.strict_order = strict_order
        self.steps: OrderedDict[str, PipelineStep] = OrderedDict()
        self.step_results: List[StepResult] = []
        self.is_fitted = False
        
        if steps:
            self._add_steps(steps)
        elif config:
            self._build_from_config(config)
    
    @classmethod
    def default_pipeline(cls, **kwargs) -> 'FactorProcessingPipeline':
        """创建默认的标准五步法流水线"""
        config = PipelineConfig.default_config()
        return cls(config=config, **kwargs)
    
    def _add_steps(self, steps: List[PipelineStep]):
        """添加步骤并进行顺序校验"""
        step_types = []
        for step in steps:
            self.steps[step.name] = step
            try:
                step_types.append(StepType(step.step_type))
            except ValueError:
                raise ValueError(f"无效的步骤类型: '{step.step_type}'，有效值为: {[e.value for e in StepType]}")
        
        # 顺序校验
        if self.strict_order:
            is_valid, errors = PipelineOrderValidator.validate(step_types)
            if not is_valid:
                suggested = PipelineOrderValidator.suggest_correction(step_types)
                error_msg = "\n".join(errors)
                suggest_msg = " → ".join(s.value for s in suggested)
                raise OrderValidationError(
                    message=f"流水线顺序校验失败:\n{error_msg}\n\n"
                            f"建议顺序: {suggest_msg}",
                    context={
                        'errors': errors,
                        'suggested_order': [s.value for s in suggested],
                        'academic_basis': (
                            "插补必须在去极值之前，因为去极值的统计量(MAD/分位数)"
                            "需要基于完整数据计算；中性化必须在最后，因为中性化基于回归残差，"
                            "后续变换会破坏中性化效果。"
                        )
                    }
                )
    
    def _build_from_config(self, config: PipelineConfig):
        """从配置构建流水线"""
        steps = []
        for step_config in config.steps:
            if not step_config.enabled:
                continue
            
            step = self._create_step(step_config)
            if step:
                steps.append(step)
        
        self._add_steps(steps)
        self.config = config
    
    def _create_step(self, step_config: StepConfig) -> Optional[PipelineStep]:
        """根据配置创建步骤实例"""
        step_type = step_config.step_type
        params = step_config.params
        
        if step_type == StepType.IMPUTATION:
            return ImputerAdapter(**params)
        elif step_type in (StepType.OUTLIER_DETECTION, StepType.TRANSFORMATION, StepType.STANDARDIZATION):
            process_type = {
                StepType.OUTLIER_DETECTION: 'outlier',
                StepType.TRANSFORMATION: 'transformation',
                StepType.STANDARDIZATION: 'standardization',
            }[step_type]
            return ProcessingAdapter(process_type=process_type, **params)
        elif step_type == StepType.NEUTRALIZATION:
            return NeutralizerAdapter(**params)
        
        logger.warning(f"未知的步骤类型: {step_type}")
        return None
    
    def fit(self, X: pd.DataFrame, **kwargs) -> 'FactorProcessingPipeline':
        """拟合整个流水线"""
        logger.info(f"开始拟合流水线，共 {len(self.steps)} 个步骤")
        
        current_data = X.copy()
        
        for name, step in self.steps.items():
            logger.info(f"拟合步骤: {name} ({step.step_type})")
            step.fit(current_data, **kwargs)
            # 更新数据供下一步拟合使用
            if step.step_type != StepType.NEUTRALIZATION.value:
                current_data = step.transform(current_data, **kwargs)
        
        self.is_fitted = True
        logger.info("流水线拟合完成")
        return self
    
    def transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """应用整个流水线"""
        if not self.is_fitted:
            raise ValueError("流水线未拟合，请先调用 fit()")
        
        return self._execute(X, **kwargs).final_data
    
    def fit_transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """拟合并应用整个流水线"""
        return self.fit(X, **kwargs).transform(X, **kwargs)
    
    def _execute(self, X: pd.DataFrame, **kwargs) -> PipelineResult:
        """执行流水线并追踪状态"""
        start_time = time.time()
        result = PipelineResult(success=True, config=getattr(self, 'config', None))
        
        current_data = X.copy()
        
        for name, step in self.steps.items():
            step_start = time.time()
            missing_before = current_data.isnull().sum().sum()
            input_shape = current_data.shape
            
            try:
                logger.info(f"执行步骤: {name}")
                current_data = step.transform(current_data, **kwargs)
                
                missing_after = current_data.isnull().sum().sum()
                step_time = time.time() - step_start
                
                step_result = StepResult(
                    step_name=name,
                    step_type=step.step_type,
                    input_shape=input_shape,
                    output_shape=current_data.shape,
                    execution_time=step_time,
                    missing_count_before=missing_before,
                    missing_count_after=missing_after,
                    stats=step.get_stats()
                )
                result.step_results.append(step_result)
                
                logger.info(
                    f"步骤 {name} 完成: "
                    f"形状 {input_shape} -> {current_data.shape}, "
                    f"缺失 {missing_before} -> {missing_after}, "
                    f"耗时 {step_time:.3f}s"
                )
                
            except (ValueError, TypeError, RuntimeError, KeyError, IndexError) as e:
                error_msg = f"步骤 {name} 执行失败: {str(e)}"
                logger.error(error_msg)
                result.errors.append(error_msg)
                result.success = False

                # 使用结构化异常
                step_error = StepExecutionError(
                    message=str(e),
                    step_name=name,
                    context={
                        'input_shape': input_shape,
                        'missing_rate_before': missing_before / (input_shape[0] * input_shape[1]) if input_shape[0] * input_shape[1] > 0 else 0,
                        'execution_time': time.time() - step_start,
                        'original_error_type': type(e).__name__,
                    },
                    original_error=e
                )
                
                step_result = StepResult(
                    step_name=name,
                    step_type=step.step_type,
                    input_shape=input_shape,
                    output_shape=input_shape,
                    execution_time=time.time() - step_start,
                    missing_count_before=missing_before,
                    missing_count_after=missing_before,
                    error=str(step_error)
                )
                result.step_results.append(step_result)
                
                if self.strict_order:
                    break  # 严格模式下，出错即停止
        
        result.final_data = current_data
        result.total_time = time.time() - start_time
        
        if result.success:
            logger.info(f"流水线执行完成，总耗时: {result.total_time:.3f}s")
        else:
            logger.error(f"流水线执行失败，错误: {result.errors}")
        
        self.step_results = result.step_results
        return result
    
    def get_execution_summary(self) -> str:
        """获取执行摘要"""
        if not self.step_results:
            return "流水线尚未执行"
        
        lines = ["=" * 60]
        lines.append("因子处理流水线执行摘要")
        lines.append("=" * 60)
        
        total_time = sum(r.execution_time for r in self.step_results)
        
        for i, result in enumerate(self.step_results, 1):
            lines.append(f"\n步骤 {i}: {result.step_name} ({result.step_type})")
            lines.append(f"  输入形状: {result.input_shape}")
            lines.append(f"  输出形状: {result.output_shape}")
            lines.append(f"  缺失值: {result.missing_count_before} -> {result.missing_count_after}")
            lines.append(f"  执行时间: {result.execution_time:.3f}s")
            if result.error:
                lines.append(f"  错误: {result.error}")
        
        lines.append(f"\n总执行时间: {total_time:.3f}s")
        lines.append("=" * 60)
        
        return "\n".join(lines)
    
    def __repr__(self) -> str:
        steps_str = " → ".join(f"{name}({step.step_type})" for name, step in self.steps.items())
        return f"FactorProcessingPipeline([{steps_str}])"
