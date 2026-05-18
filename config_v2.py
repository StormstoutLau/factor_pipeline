# -*- coding: utf-8 -*-
"""
v2.0 统一配置管理模块（基于 Pydantic）

提供类型安全、自动验证的配置系统，替代原有的 dataclass 配置。

Dependencies
------------
pydantic >= 2.0.0
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator


# =============================================================================
# 步骤配置
# =============================================================================

class StepConfigV2(BaseModel):
    """步骤配置（Pydantic 版本）"""
    
    step_type: str = Field(..., description="步骤类型")
    enabled: bool = Field(default=True, description="是否启用")
    params: dict = Field(default_factory=dict, description="步骤参数")
    
    model_config = {"validate_assignment": True}


class ImputationConfig(BaseModel):
    """插补步骤配置"""
    
    strategy: Literal['auto', 'mean', 'median', 'most_frequent', 'constant'] = \
        Field(default='auto', description="插补策略")
    fill_value: Optional[float] = Field(default=None, description="常数填充值")
    max_missing_ratio: float = Field(
        default=0.5, ge=0.0, le=1.0, 
        description="最大允许缺失比例"
    )


class OutlierConfig(BaseModel):
    """去极值步骤配置"""
    
    method: Literal['auto', 'mad', 'z_score', 'iqr', 'percentile', 'adaptive'] = \
        Field(default='auto', description="去极值方法")
    threshold: float = Field(default=3.0, ge=1.0, le=10.0, description="阈值倍数")
    lower_percentile: float = Field(
        default=0.01, ge=0.0, le=0.5, 
        description="下分位数"
    )
    upper_percentile: float = Field(
        default=0.99, ge=0.5, le=1.0, 
        description="上分位数"
    )
    
    @field_validator('upper_percentile')
    @classmethod
    def upper_gt_lower(cls, v: float, info) -> float:
        """上分位数必须大于下分位数"""
        if 'lower_percentile' in info.data and v <= info.data['lower_percentile']:
            raise ValueError('upper_percentile 必须大于 lower_percentile')
        return v


class TransformationConfig(BaseModel):
    """变换步骤配置"""
    
    method: Literal['auto', 'box_cox', 'yeo_johnson', 'quantile', 'log', 'none'] = \
        Field(default='auto', description="变换方法")
    skew_threshold: float = Field(
        default=2.0, ge=0.0, 
        description="偏度阈值（超过则变换）"
    )
    kurt_threshold: float = Field(
        default=5.0, ge=0.0, 
        description="峰度阈值（超过则变换）"
    )


class StandardizationConfig(BaseModel):
    """标准化步骤配置"""
    
    method: Literal['auto', 'z_score', 'rank', 'min_max', 'robust'] = \
        Field(default='auto', description="标准化方法")
    target_mean: float = Field(default=0.0, description="目标均值")
    target_std: float = Field(default=1.0, gt=0.0, description="目标标准差")


class NeutralizationConfig(BaseModel):
    """中性化步骤配置"""
    
    method: Literal['ols', 'wls', 'ridge'] = \
        Field(default='ols', description="回归方法")
    alpha: float = Field(
        default=1.0, ge=0.0, 
        description="Ridge 正则化强度"
    )
    neutralize_industry: bool = Field(default=True, description="行业中性化")
    neutralize_market_cap: bool = Field(default=True, description="市值中性化")


class GarchConfig(BaseModel):
    """GARCH 白化配置"""
    
    enabled: bool = Field(default=False, description="是否启用")
    p: int = Field(default=1, ge=0, le=5, description="ARCH 阶数")
    q: int = Field(default=1, ge=0, le=5, description="GARCH 阶数")
    vol: Literal['Garch', 'EGarch', 'GJR-Garch'] = \
        Field(default='Garch', description="波动率模型")
    min_obs: int = Field(default=50, ge=20, description="最小观测数")
    
    @field_validator('q')
    @classmethod
    def validate_orders(cls, v: int, info) -> int:
        """验证 GARCH 阶数"""
        if 'p' in info.data and v == 0 and info.data['p'] == 0:
            raise ValueError('p 和 q 不能同时为 0')
        return v


# =============================================================================
# 管道配置
# =============================================================================

class StaticPipelineConfig(BaseModel):
    """静态管道配置"""
    
    name: str = Field(default="static_pipeline", description="管道名称")
    imputation: ImputationConfig = Field(default_factory=ImputationConfig)
    outlier: OutlierConfig = Field(default_factory=OutlierConfig)
    transformation: TransformationConfig = Field(default_factory=TransformationConfig)
    standardization: StandardizationConfig = Field(default_factory=StandardizationConfig)
    neutralization: NeutralizationConfig = Field(default_factory=NeutralizationConfig)
    garch: GarchConfig = Field(default_factory=GarchConfig)
    
    # v2.0 调整：先中性化后标准化
    neutralize_before_standardize: bool = Field(
        default=True, 
        description="先中性化后标准化（v2.0 推荐）"
    )


class DynamicPipelineConfig(BaseModel):
    """动态管道配置"""
    
    name: str = Field(default="dynamic_pipeline", description="管道名称")
    imputation: ImputationConfig = Field(default_factory=ImputationConfig)
    neutralization: NeutralizationConfig = Field(default_factory=NeutralizationConfig)
    standardization: StandardizationConfig = Field(default_factory=StandardizationConfig)
    
    # 解耦参数
    decorrelation_strength: float = Field(
        default=1.0, ge=0.0, le=1.0,
        description="AR 残差提取强度"
    )
    max_ar_order: int = Field(
        default=5, ge=1, le=20,
        description="最大 AR 阶数"
    )
    ar_criterion: Literal['aic', 'bic', 'hqic'] = \
        Field(default='aic', description="AR 阶数选择准则")
    
    # 动态管道禁用变换和 GARCH
    enable_transformation: bool = Field(
        default=False, 
        description="动态管道禁用变换（保护时序信号）"
    )
    enable_garch: bool = Field(
        default=False, 
        description="动态管道禁用 GARCH（序列已接近白噪声）"
    )


class MixedPipelineConfig(BaseModel):
    """混合管道配置"""
    
    name: str = Field(default="mixed_pipeline", description="管道名称")
    imputation: ImputationConfig = Field(default_factory=ImputationConfig)
    outlier: OutlierConfig = Field(default_factory=OutlierConfig)
    transformation: TransformationConfig = Field(default_factory=TransformationConfig)
    standardization: StandardizationConfig = Field(default_factory=StandardizationConfig)
    neutralization: NeutralizationConfig = Field(default_factory=NeutralizationConfig)
    
    # 混合管道条件性参数
    conditional_transform: bool = Field(
        default=True,
        description="是否条件性变换（根据偏度/峰度判断）"
    )
    mild_winsorization: bool = Field(
        default=True,
        description="是否使用温和缩尾（3σ 而非 5σ）"
    )


# =============================================================================
# 统一配置
# =============================================================================

class PipelineV2ConfigUnified(BaseModel):
    """v2.0 统一流水线配置
    
    整合所有子配置，提供统一的配置入口。
    
    Examples
    --------
    >>> config = PipelineV2ConfigUnified(
    ...     name="my_pipeline",
    ...     static=StaticPipelineConfig(garch=GarchConfig(enabled=True))
    ... )
    >>> config.static.garch.enabled
    True
    """
    
    name: str = Field(default="factor_pipeline_v2", description="流水线名称")
    version: str = Field(default="2.0.0", description="版本")
    description: str = Field(default="", description="描述")
    
    # 全局设置
    strict_order: bool = Field(default=True, description="严格顺序校验")
    track_intermediate: bool = Field(default=True, description="追踪中间状态")
    parallel: bool = Field(default=False, description="并行处理")
    max_workers: int = Field(default=4, ge=1, le=16, description="最大工作进程")
    
    # 子管道配置
    static: StaticPipelineConfig = Field(default_factory=StaticPipelineConfig)
    dynamic: DynamicPipelineConfig = Field(default_factory=DynamicPipelineConfig)
    mixed: MixedPipelineConfig = Field(default_factory=MixedPipelineConfig)
    
    # 指纹和分类配置
    fingerprint_window: int = Field(default=24, ge=12, description="指纹计算窗口")
    classification_threshold_static: float = Field(
        default=0.80, ge=0.5, le=1.0,
        description="静态因子 AR(1) 阈值"
    )
    classification_threshold_dynamic: float = Field(
        default=0.40, ge=0.0, le=0.5,
        description="动态因子 AR(1) 阈值"
    )
    
    # 监控配置
    enable_monitoring: bool = Field(default=True, description="启用迁移监测")
    migration_window: int = Field(default=12, ge=6, description="迁移检测窗口")
    migration_threshold: float = Field(
        default=0.10, ge=0.0, le=1.0,
        description="迁移置信度阈值"
    )
    
    model_config = {
        "validate_assignment": True,
        "json_schema_extra": {
            "example": {
                "name": "my_pipeline",
                "static": {
                    "garch": {"enabled": True}
                }
            }
        }
    }
    
    def to_pipeline_config(self):
        """转换为旧版 PipelineConfig（兼容层）"""
        from .config import PipelineConfig, StepConfig, StepType
        
        steps = [
            StepConfig(step_type=StepType.IMPUTATION, params=self.static.imputation.model_dump()),
            StepConfig(step_type=StepType.OUTLIER_DETECTION, params=self.static.outlier.model_dump()),
            StepConfig(step_type=StepType.TRANSFORMATION, params=self.static.transformation.model_dump()),
            StepConfig(step_type=StepType.STANDARDIZATION, params=self.static.standardization.model_dump()),
            StepConfig(step_type=StepType.NEUTRALIZATION, params=self.static.neutralization.model_dump()),
        ]
        
        return PipelineConfig(
            name=self.name,
            description=self.description,
            steps=steps,
            strict_order=self.strict_order
        )


# =============================================================================
# 配置加载/保存工具
# =============================================================================

def load_config_from_json(path: str) -> PipelineV2ConfigUnified:
    """从 JSON 文件加载配置"""
    import json
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return PipelineV2ConfigUnified(**data)


def load_config_from_yaml(path: str) -> PipelineV2ConfigUnified:
    """从 YAML 文件加载配置"""
    try:
        import yaml
    except ImportError:
        raise ImportError("加载 YAML 配置需要 PyYAML: pip install pyyaml")
    
    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return PipelineV2ConfigUnified(**data)


def save_config_to_json(config: PipelineV2ConfigUnified, path: str) -> None:
    """保存配置到 JSON 文件"""
    import json
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(config.model_dump(), f, indent=2, ensure_ascii=False)


def save_config_to_yaml(config: PipelineV2ConfigUnified, path: str) -> None:
    """保存配置到 YAML 文件"""
    try:
        import yaml
    except ImportError:
        raise ImportError("保存 YAML 配置需要 PyYAML: pip install pyyaml")
    
    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump(config.model_dump(), f, allow_unicode=True, sort_keys=False)
