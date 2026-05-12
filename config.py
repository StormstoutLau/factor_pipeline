# -*- coding: utf-8 -*-
"""
流水线配置管理
支持 YAML/JSON/字典配置
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import json


class StepType(Enum):
    """流水线步骤类型"""
    IMPUTATION = "imputation"           # 缺失值插补
    OUTLIER_DETECTION = "outlier"       # 去极值
    TRANSFORMATION = "transformation"   # 自适应变换
    STANDARDIZATION = "standardization" # 标准化
    NEUTRALIZATION = "neutralization"   # 中性化


# 学术与业界验证的标准处理顺序
VALID_STEP_ORDERS = [
    [StepType.IMPUTATION, StepType.OUTLIER_DETECTION, StepType.TRANSFORMATION, StepType.STANDARDIZATION, StepType.NEUTRALIZATION],
    [StepType.IMPUTATION, StepType.OUTLIER_DETECTION, StepType.STANDARDIZATION, StepType.NEUTRALIZATION],
    [StepType.IMPUTATION, StepType.OUTLIER_DETECTION, StepType.NEUTRALIZATION],
    [StepType.IMPUTATION, StepType.STANDARDIZATION, StepType.NEUTRALIZATION],
]


@dataclass
class StepConfig:
    """单个步骤的配置"""
    step_type: StepType
    module_path: str = ""           # 模块路径，如 "Factor_Imputer_v2.0"
    class_name: str = ""            # 类名
    params: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'step_type': self.step_type.value,
            'module_path': self.module_path,
            'class_name': self.class_name,
            'params': self.params,
            'enabled': self.enabled
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StepConfig':
        return cls(
            step_type=StepType(data['step_type']),
            module_path=data.get('module_path', ''),
            class_name=data.get('class_name', ''),
            params=data.get('params', {}),
            enabled=data.get('enabled', True)
        )


@dataclass
class PipelineConfig:
    """流水线完整配置"""
    name: str = "factor_processing_pipeline"
    description: str = ""
    steps: List[StepConfig] = field(default_factory=list)
    strict_order: bool = True       # 是否严格校验顺序
    allow_skip: bool = True         # 是否允许跳过某些步骤
    track_intermediate: bool = True # 是否追踪中间状态
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'description': self.description,
            'steps': [s.to_dict() for s in self.steps],
            'strict_order': self.strict_order,
            'allow_skip': self.allow_skip,
            'track_intermediate': self.track_intermediate
        }
    
    def to_json(self, path: str):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PipelineConfig':
        return cls(
            name=data.get('name', 'factor_processing_pipeline'),
            description=data.get('description', ''),
            steps=[StepConfig.from_dict(s) for s in data.get('steps', [])],
            strict_order=data.get('strict_order', True),
            allow_skip=data.get('allow_skip', True),
            track_intermediate=data.get('track_intermediate', True)
        )
    
    @classmethod
    def from_json(cls, path: str) -> 'PipelineConfig':
        with open(path, 'r', encoding='utf-8') as f:
            return cls.from_dict(json.load(f))
    
    @classmethod
    def default_config(cls) -> 'PipelineConfig':
        """创建默认配置（标准五步法）"""
        return cls(
            name="default_factor_pipeline",
            description="标准因子处理流水线: 插补→去极值→变换→标准化→中性化",
            steps=[
                StepConfig(
                    step_type=StepType.IMPUTATION,
                    module_path="Factor_Imputer_v2.0",
                    class_name="HierarchicalImputer",
                    params={'strategy': 'auto'}
                ),
                StepConfig(
                    step_type=StepType.OUTLIER_DETECTION,
                    module_path="Factor_AdaptiveWinsor",
                    class_name="SmartOutlierDetector",
                    params={'method': 'auto', 'auto_select': True}
                ),
                StepConfig(
                    step_type=StepType.TRANSFORMATION,
                    module_path="Factor_AdaptiveWinsor",
                    class_name="AdaptiveTransformer",
                    params={'method': 'auto', 'auto_optimize': True}
                ),
                StepConfig(
                    step_type=StepType.STANDARDIZATION,
                    module_path="Factor_AdaptiveWinsor",
                    class_name="AdaptiveStandardizer",
                    params={'method': 'auto'}
                ),
                StepConfig(
                    step_type=StepType.NEUTRALIZATION,
                    module_path="Factor_Neutralizer_v2.0",
                    class_name="FactorNeutralizer",
                    params={'neutralization_type': 'industry', 'industry_method': 'regression'}
                ),
            ],
            strict_order=True,
            allow_skip=True,
            track_intermediate=True
        )
