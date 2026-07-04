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
# 回测配置
# =============================================================================

class BacktestConfig(BaseModel):
    """回测引擎配置"""
    
    # IC 计算方法
    ic_method: Literal['rank', 'pearson'] = Field(
        default='rank', description="IC 计算方法"
    )
    
    # 多空组合
    top_n: float = Field(
        default=0.2, ge=0.05, le=0.5,
        description="多空选股比例（float 表示比例，int 表示固定数量）"
    )
    ls_method: Literal['top_n', 'equal_weight'] = Field(
        default='top_n', description="多空组合构建方法"
    )
    
    # IC Decay
    max_lag: int = Field(
        default=12, ge=1, le=24,
        description="IC Decay 最大滞后"
    )
    
    # 漂移检测
    enable_drift_detection: bool = Field(
        default=True, description="启用漂移检测"
    )
    drift_warning_threshold: float = Field(
        default=30.0, ge=0.0, le=100.0,
        description="漂移预警阈值"
    )
    drift_detect_threshold: float = Field(
        default=50.0, ge=0.0, le=100.0,
        description="漂移确认阈值"
    )
    drift_severe_threshold: float = Field(
        default=70.0, ge=0.0, le=100.0,
        description="严重漂移阈值"
    )
    
    # 健康度评估
    enable_health_check: bool = Field(
        default=True, description="启用健康度评估"
    )

    # 外部模块路径 (可通过环境变量覆盖)
    factor_trading_path: str = Field(
        default="F:/Coding/Factor_Trading_v3.0",
        description="Factor_Trading_v3.0 模块路径 (环境变量: FACTOR_TRADING_PATH)"
    )
    factor_db_path: str = Field(
        default="F:/Coding/Factor_DB",
        description="Factor_DB 模块路径 (环境变量: FACTOR_DB_PATH)"
    )
    fingerprint_path: str = Field(
        default="F:/Coding/Factor_Fingerprint",
        description="Factor_Fingerprint 模块路径 (环境变量: FINGERPRINT_PATH)"
    )

    model_config = {"validate_assignment": True}


# =============================================================================
# v2.5.0 正交化配置 (Layer 2, ADR-020)
# =============================================================================

class OrthogonalizationConfig(BaseModel):
    """正交化配置 (Layer 2, v2.5.0)

    默认关闭 (enabled=False), 不影响基线.
    启用后作为 Pipeline.transform() 的 post_transform_hook 应用.

    学术依据: Löwdin (1950) 对称正交化, Ledoit-Wolf (2004) 收缩, Kahan (1966) 二次投影
    """

    enabled: bool = Field(
        default=False,
        description="启用正交化 (默认关闭, 保护基线)"
    )
    method: Literal['symmetric', 'gram_schmidt', 'pca', 'cholesky', 'ridge'] = Field(
        default='symmetric',
        description="正交化方法: symmetric (默认, Löwdin) / gram_schmidt / pca / cholesky / ridge"
    )
    window_mode: Literal['full_sample', 'rolling'] = Field(
        default='full_sample',
        description="窗口模式: full_sample (研究用, 单一 W) / rolling (回测用, 每期 W)"
    )
    window_size: int = Field(
        default=252,
        ge=20,
        description="滚动窗口大小 (日), 仅 window_mode=rolling 时生效"
    )
    min_obs: int = Field(
        default=60,
        ge=10,
        description="最小样本数, 不足时跳过正交化"
    )
    shrinkage: bool = Field(
        default=True,
        description="启用 Ledoit-Wolf 收缩预处理 (病态矩阵保护)"
    )
    vrr_threshold: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="VRR 冗余阈值, VRR < threshold 的因子标记为冗余"
    )
    groups: Optional[dict] = Field(
        default=None,
        description="分组正交化: {组名: [因子名]}, 组内正交 + 组间保留 (O5 阶段)"
    )
    use_gpu: bool = Field(
        default=False,
        description="启用 GPU 加速 (需 CuPy, HAS_CUPY 标记)"
    )
    align_mode: Literal['intersection', 'union_nan', 'raise_on_mismatch'] = Field(
        default='intersection',
        description=(
            "因子对齐策略 (O2.8.1): "
            "'intersection' (默认, 取交集) / "
            "'union_nan' (取并集, 缺失填 NaN) / "
            "'raise_on_mismatch' (不匹配时抛错)"
        )
    )

    # 方法特定参数
    ridge_lambda: float = Field(
        default=1.0,
        gt=0.0,
        description="Ridge λ (仅 method=ridge)"
    )
    ridge_lambda_selection: Literal['fixed', 'cv', 'ledoit_wolf'] = Field(
        default='fixed',
        description="Ridge λ 选择方式 (仅 method=ridge)"
    )
    pca_variance_threshold: float = Field(
        default=0.95,
        gt=0.0,
        le=1.0,
        description="PCA 方差保留阈值 (仅 method=pca)"
    )
    pca_center: bool = Field(
        default=True,
        description="PCA 中心化 (仅 method=pca)"
    )
    gs_order: Optional[list] = Field(
        default=None,
        description="GS 正交化顺序 (仅 method=gram_schmidt)"
    )
    gs_reorthogonalize: bool = Field(
        default=False,
        description="GS 二次投影 (Kahan 1966, κ>100 时启用)"
    )
    # 注: O1.12.1 threshold_mode (relative/absolute/auto) 是算法层参数,
    # 不在 Layer 2 配置中暴露 (使用 O1 默认 'auto'), 保持配置简洁.

    model_config = {"validate_assignment": True}


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
    version: str = Field(default="2.5.0", description="版本")
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
    
    # v2.1 端到端阈值搜索新增配置 (P3 Phase 1)
    hard_routing_prob: float = Field(
        default=0.90, ge=0.5, le=1.0,
        description="硬路由概率阈值（软路由中超过此值直接硬路由）"
    )
    merge_alpha: float = Field(
        default=0.50, ge=0.0, le=1.0,
        description="迁移权重与分类权重的融合系数（0=纯分类，1=纯迁移）"
    )
    ks_alpha: float = Field(
        default=0.05, ge=0.001, le=0.5,
        description="KS 迁移显著性检验的显著性水平"
    )
    mixed_winsor_sigma: float = Field(
        default=3.0, ge=1.0, le=10.0,
        description="混合管道缩尾阈值（sigma 倍数）"
    )
    transform_aggressiveness: float = Field(
        default=1.0, ge=0.3, le=5.0,
        description="变换激进程度系数（<1 保守，>1 激进）"
    )
    
    # 回测配置 (P6 - Backtest 集成)
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)

    # v2.5.0 正交化配置 (Layer 2, ADR-020) — 默认关闭, 不影响基线
    orthogonalization: OrthogonalizationConfig = Field(
        default_factory=OrthogonalizationConfig,
        description="Layer 2 正交化配置 (默认关闭)"
    )

    model_config = {
        "validate_assignment": True,
        "extra": "ignore",  # O2.8.5: 向后兼容旧 JSON (忽略未知字段)
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

    def to_pipeline_v2_config(self):
        """转换为 v2.0 PipelineV2Config (dataclass) — 桥接层 (Fix 2)

        PipelineV2ConfigUnified (Pydantic, 配置持久化/加载/回测集成) 与
        PipelineV2Config (dataclass, optimizer/pipeline 运行时) 之间的转换桥接。

        字段映射:
          - 4 共享字段直接复制: hard_routing_prob, merge_alpha, ks_alpha, mixed_winsor_sigma
          - 概念对应:
              classification_threshold_static  → classification.static_ar1_threshold
              classification_threshold_dynamic → classification.dynamic_ar1_threshold
              migration_threshold              → migration_threshold (v2.6.0 E2 修正: 直接传递,
                                                 字段位于 PipelineV2Config 本身, 不再尝试
                                                 设置到 MonitorConfig)
          - 嵌套 → 扁平:
              static.garch.enabled/p/q/vol/min_obs → static_enable_garch/static_garch_p/q/vol/min_obs
              dynamic.decorrelation_strength/max_ar_order/ar_criterion → dynamic_*
              mixed.conditional_transform                  → mixed_conditional_transform
              mixed.transformation.skew_threshold/kurt_threshold → mixed_skew_threshold/mixed_kurt_threshold

        Returns:
            PipelineV2Config (dataclass) — 可被 optimizer 和 pipeline 运行时消费
        """
        # 延迟导入避免循环依赖 (pipelines_v2 依赖 Factor_Fingerprint/Factor_Decoupler)
        from .pipelines_v2 import PipelineV2Config
        from factor_pipeline.modules.factor_fingerprint import (
            FingerprintConfig, ClassificationConfig, MonitorConfig,
        )

        # 构造 ClassificationConfig (概念对应字段)
        classification = ClassificationConfig(
            static_ar1_threshold=self.classification_threshold_static,
            dynamic_ar1_threshold=self.classification_threshold_dynamic,
        )

        # 构造 MonitorConfig
        # v2.6.0 E2 修正: Unified.migration_threshold 不再尝试映射到 MonitorConfig
        #     (MonitorConfig 有 short/medium/long_threshold 三个窗口阈值, 无 migration_threshold).
        #     字段直接传递到 PipelineV2Config.migration_threshold (config 本身).
        #     Unified.enable_monitoring → monitor.enable_smooth_transition 概念对应
        monitor = MonitorConfig(
            enable_smooth_transition=self.enable_monitoring,
        )

        return PipelineV2Config(
            fingerprint=FingerprintConfig(),
            classification=classification,
            monitor=monitor,
            # 动态管道字段 (嵌套 → 扁平)
            dynamic_decorrelation_strength=self.dynamic.decorrelation_strength,
            dynamic_max_ar_order=self.dynamic.max_ar_order,
            dynamic_ar_criterion=self.dynamic.ar_criterion,
            # 混合管道字段 (嵌套 → 扁平)
            mixed_conditional_transform=self.mixed.conditional_transform,
            mixed_skew_threshold=self.mixed.transformation.skew_threshold,
            mixed_kurt_threshold=self.mixed.transformation.kurt_threshold,
            # 静态管道 GARCH 字段 (嵌套 → 扁平)
            static_enable_garch=self.static.garch.enabled,
            static_garch_p=self.static.garch.p,
            static_garch_q=self.static.garch.q,
            static_garch_vol=self.static.garch.vol,
            static_garch_min_obs=self.static.garch.min_obs,
            # 4 个共享字段 (直接复制)
            hard_routing_prob=self.hard_routing_prob,
            merge_alpha=self.merge_alpha,
            ks_alpha=self.ks_alpha,
            mixed_winsor_sigma=self.mixed_winsor_sigma,
            # v2.6.0 E2: migration_threshold 字段直接传递 (字段位于 config 本身)
            migration_threshold=self.migration_threshold,
            # v2.5.0 正交化配置 (整对象透传, dataclass 字段为 Optional[Any])
            orthogonalization=self.orthogonalization,
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
