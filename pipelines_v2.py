# -*- coding: utf-8 -*-
"""
因子处理流水线 v2.0 - 带指纹分类的增强版

在原有 Pipeline 基础上，增加因子指纹前置层，实现：
1. 先诊断分类（静态/动态/混合）
2. 再分流处理（三条差异化管道）
3. 持续监测迁移

设计哲学（与项目保持一致）：
- 数据驱动自适应：因子管道由指纹自动决定
- 类型感知路由：三种类型对应三条管道
- 学术级顺序校验：每条管道内部仍遵循五步法
- sklearn风格接口：fit/transform/fit_transform
- 中间状态追踪：指纹、分类、处理全流程可追溯
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
import pandas as pd
import numpy as np
import logging

# =============================================================================
# 常量定义
# =============================================================================

# 混合因子温和缩尾的 σ 倍数
MIXED_WINSORIZE_SIGMA = 3.0

from .pipeline import FactorProcessingPipeline, PipelineResult
from .adapters import ImputerAdapter, ProcessingAdapter, NeutralizerAdapter, GarchWhiteningAdapter
from Factor_Fingerprint import (
    FactorFingerprinter, FactorFingerprint, FactorType,
    FingerprintConfig,
    AdaptiveFactorClassifier, ClassificationConfig, ClassificationResult,
    FactorFingerprintMonitor, MonitorConfig,
    SemanticStatisticalFusion, SemanticPrior, ArbitratedResult,
)
# 引入因子解耦模块
from Factor_Decoupler import (
    CompositeDecoupler,
    DecouplerConfig
)

logger = logging.getLogger(__name__)


@dataclass
class PipelineV2Config:
    """Pipeline v2.0 配置"""
    fingerprint: FingerprintConfig = field(default_factory=FingerprintConfig)
    classification: ClassificationConfig = field(default_factory=ClassificationConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    # 动态因子解耦强度 [0, 1]，0=不解耦，1=完全AR残差
    dynamic_decorrelation_strength: float = 1.0
    # 动态因子最大AR阶数
    dynamic_max_ar_order: int = 5
    # 动态因子AR阶数选择准则
    dynamic_ar_criterion: str = 'aic'
    # 混合因子是否条件性变换
    mixed_conditional_transform: bool = True
    # 混合因子变换阈值
    mixed_skew_threshold: float = 2.0
    mixed_kurt_threshold: float = 5.0
    # 静态因子是否启用GARCH白化（默认关闭）
    static_enable_garch: bool = False
    # GARCH白化参数
    static_garch_p: int = 1
    static_garch_q: int = 1
    static_garch_vol: str = 'Garch'
    static_garch_min_obs: int = 50


class _BaseFactorPipeline:
    """因子管道基类，提供通用的 fit/transform/fit_transform 接口"""

    def __init__(self):
        self.is_fitted = False

    def fit(self, X: pd.DataFrame, **kwargs) -> '_BaseFactorPipeline':
        raise NotImplementedError

    def transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        if not self.is_fitted:
            raise ValueError("Pipeline未拟合")
        # 基类只做 is_fitted 检查，实际 transform 由子类实现
        return X

    def fit_transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        return self.fit(X, **kwargs).transform(X, **kwargs)


class StaticFactorPipeline(_BaseFactorPipeline):
    """
    静态因子处理管道

    适用条件：ar1_median > 0.80 且 rank_autocorr > 0.70
    典型代表：市净率（PB）、市盈率（PE）、股息率

    处理流程：
        缺失插补 → 自适应非线性变换 → (可选)GARCH白化 → 中性化 → 线性Z-Score

    为何这样处理：
        静态因子的价值在截面排序，非线性变换可有效驯服厚尾和偏态。
        高自相关性意味着GARCH预白化可能有必要。
    """

    def __init__(self,
                 neutralizer_params: Optional[Dict] = None,
                 enable_garch: bool = False,
                 garch_params: Optional[Dict] = None):
        super().__init__()
        self.steps = [
            ('imputer', ImputerAdapter(strategy='auto')),
            ('outlier', ProcessingAdapter(process_type='outlier', method='auto')),
            ('transform', ProcessingAdapter(process_type='transformation', method='auto')),
        ]

        # 可选：GARCH白化（默认关闭）
        if enable_garch:
            garch_kwargs = garch_params or {}
            self.steps.append(('garch_whiten', GarchWhiteningAdapter(**garch_kwargs)))

        self.steps.extend([
            ('neutralize', NeutralizerAdapter(**(neutralizer_params or {}))),
            ('standardize', ProcessingAdapter(process_type='standardization', method='auto')),
        ])

    def fit(self, X: pd.DataFrame, **kwargs) -> 'StaticFactorPipeline':
        for name, step in self.steps:
            logger.info(f"[StaticPipeline] Fitting {name}...")
            step.fit(X, **kwargs)
            X = step.transform(X, **kwargs)
        self.is_fitted = True
        return self

    def transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        super().transform(X, **kwargs)  # 检查 is_fitted
        for name, step in self.steps:
            logger.info(f"[StaticPipeline] Transforming {name}...")
            X = step.transform(X, **kwargs)
        return X


class DynamicFactorPipeline(_BaseFactorPipeline):
    """
    动态因子处理管道

    适用条件：ar1_median < 0.40
    典型代表：短期反转、换手率变化、波动率变化

    处理流程（符合设计要求）：
        缺失插补 → 原始值双重中性化 → AR建模 → AR残差中性化 → 线性Z-Score

    为何这样处理：
        动态因子的价值在时序变化，禁止非线性变换以保护时序信号。
        中性化必须在原始值阶段进行以剥离内生性暴露（第一重中性化）。
        AR建模后再进行第二重中性化以剥离残差中的行业/市值暴露。
        绝对禁止GARCH白化，因为已接近白噪声的序列再做波动率标准化会引入新噪声。
    """

    def __init__(self,
                 decorrelation_strength: float = 1.0,
                 max_ar_order: int = 5,
                 ar_criterion: str = 'aic',
                 neutralizer_params: Optional[Dict] = None):
        super().__init__()
        self.decorrelation_strength = decorrelation_strength
        self.max_ar_order = max_ar_order
        self.ar_criterion = ar_criterion
        self.neutralizer_params = neutralizer_params or {}

        # 提取行业和市值数据用于解耦器
        self.industry_data = self.neutralizer_params.get('industry_data', None)
        self.market_cap_data = self.neutralizer_params.get('market_cap_data', None)

        # 核心组件：插补器 + 解耦器 + 标准化器（延迟初始化）
        self._imputer: Optional[ImputerAdapter] = None
        self._decoupler: Optional[CompositeDecoupler] = None
        self._standardizer: Optional[ProcessingAdapter] = None

    def fit(self, X: pd.DataFrame, **kwargs) -> 'DynamicFactorPipeline':
        logger.info("[DynamicPipeline] Fitting (三重中性化流程)...")

        # Step 1: 插补
        logger.info("[DynamicPipeline] Step 1: 缺失值插补")
        self._imputer = ImputerAdapter(strategy='auto')
        self._imputer.fit(X, **kwargs)
        X_imputed = self._imputer.transform(X, **kwargs)
        
        # Step 2: 初始化并拟合组合解耦器（三重中性化核心）
        logger.info("[DynamicPipeline] Step 2: 拟合三重中性化解耦器")
        self._decoupler = CompositeDecoupler(
            industry_data=self.industry_data,
            market_cap_data=self.market_cap_data,
            max_ar_order=self.max_ar_order,
            ar_criterion=self.ar_criterion,
            decorrelation_strength=self.decorrelation_strength
        )
        self._decoupler.fit(X_imputed, **kwargs)
        
        # Step 3: 应用解耦得到残差，用于拟合标准化器
        logger.info("[DynamicPipeline] Step 3: 拟合标准化器")
        X_decoupled = self._decoupler.transform(X_imputed, **kwargs)
        self._standardizer = ProcessingAdapter(process_type='standardization', method='z_score')
        self._standardizer.fit(X_decoupled, **kwargs)
        
        self.is_fitted = True
        logger.info("[DynamicPipeline] Fit complete")
        return self

    def transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        super().transform(X, **kwargs)  # 检查 is_fitted

        logger.info("[DynamicPipeline] Transforming (三重中性化流程)...")

        # Step 1: 插补
        logger.info("[DynamicPipeline] Step 1: 插补")
        X = self._imputer.transform(X, **kwargs)

        # Step 2: 三重中性化解耦（原始值中性化 → AR建模 → AR残差中性化）
        logger.info("[DynamicPipeline] Step 2: 三重中性化解耦")
        X = self._decoupler.transform(X, **kwargs)

        # Step 3: 标准化
        logger.info("[DynamicPipeline] Step 3: 标准化")
        X = self._standardizer.transform(X, **kwargs)

        logger.info("[DynamicPipeline] Transform complete")
        return X
    
    def get_decoupling_summary(self) -> Dict[str, Any]:
        """获取解耦流程摘要信息"""
        if self._decoupler is None:
            return {}
        return self._decoupler.get_summary()


class MixedFactorPipeline(_BaseFactorPipeline):
    """
    混合因子处理管道

    适用条件：0.40 <= ar1_median <= 0.80
    典型代表：1个月动量、3个月动量

    处理流程：
        缺失插补 → 温和去极值(3σ缩尾) → 条件性非线性变换 → 原始值中性化 → 线性Z-Score

    为何这样处理：
        这类因子介于两者之间，最保守的策略是降级处理。
        只做温和缩尾和中性化，条件性做非线性变换。
        宁可保留一些原始噪声，也不冒险破坏其信号结构。
    """

    def __init__(self,
                 conditional_transform: bool = True,
                 skew_threshold: float = 2.0,
                 kurt_threshold: float = 5.0,
                 neutralizer_params: Optional[Dict] = None):
        super().__init__()
        self.conditional_transform = conditional_transform
        self.skew_threshold = skew_threshold
        self.kurt_threshold = kurt_threshold
        self.neutralizer_params = neutralizer_params or {}
        self._needs_transform = False  # 是否需要进行非线性变换
        self._transformer = None  # 显式初始化，避免状态不一致

    def fit(self, X: pd.DataFrame, **kwargs) -> 'MixedFactorPipeline':
        # Step 1: 插补
        logger.info("[MixedPipeline] Fitting imputer...")
        self._imputer = ImputerAdapter(strategy='auto')
        self._imputer.fit(X, **kwargs)
        X = self._imputer.transform(X, **kwargs)

        # Step 2: 温和去极值（3σ缩尾）
        logger.info("[MixedPipeline] Applying gentle winsorization...")
        self._winsorize_params = self._compute_winsorize_params(X)

        # Step 3: 诊断是否需要非线性变换
        if self.conditional_transform:
            self._needs_transform = self._diagnose_transform_need(X)
            if self._needs_transform:
                logger.info("[MixedPipeline] Distribution extreme, will apply gentle transform")
                self._transformer = ProcessingAdapter(process_type='transformation', method='yeo_johnson')
                self._transformer.fit(X, **kwargs)
            else:
                logger.info("[MixedPipeline] Distribution normal, skipping transform")
        else:
            self._needs_transform = False

        # Step 4: 中性化
        logger.info("[MixedPipeline] Fitting neutralizer...")
        self._neutralizer = NeutralizerAdapter(**self.neutralizer_params)
        self._neutralizer.fit(X, **kwargs)

        # Step 5: 标准化
        logger.info("[MixedPipeline] Fitting standardizer...")
        self._standardizer = ProcessingAdapter(process_type='standardization', method='z_score')
        X_neutral = self._neutralizer.transform(X, **kwargs)
        self._standardizer.fit(X_neutral, **kwargs)

        self.is_fitted = True
        return self

    def transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        super().transform(X, **kwargs)  # 检查 is_fitted

        # Step 1: 插补
        X = self._imputer.transform(X, **kwargs)

        # Step 2: 温和缩尾
        X = self._apply_winsorize(X)

        # Step 3: 条件性变换
        if self._needs_transform:
            X = self._transformer.transform(X, **kwargs)

        # Step 4: 中性化
        X = self._neutralizer.transform(X, **kwargs)

        # Step 5: 标准化
        X = self._standardizer.transform(X, **kwargs)

        return X

    def _compute_winsorize_params(self, X: pd.DataFrame) -> Dict:
        """计算温和缩尾参数"""
        means = X.mean()
        stds = X.std()
        return {
            'lower': means - MIXED_WINSORIZE_SIGMA * stds,
            'upper': means + MIXED_WINSORIZE_SIGMA * stds,
        }

    def _apply_winsorize(self, X: pd.DataFrame) -> pd.DataFrame:
        """应用3σ缩尾"""
        return X.clip(lower=self._winsorize_params['lower'],
                      upper=self._winsorize_params['upper'],
                      axis=1)

    def _diagnose_transform_need(self, X: pd.DataFrame) -> bool:
        """诊断是否需要进行非线性变换"""
        skew = X.skew().median()
        kurt = X.kurtosis().median()
        return abs(skew) > self.skew_threshold or kurt > self.kurt_threshold


class FactorProcessingPipelineV2:
    """
    增强版因子处理流水线 v2.0

    集成指纹分类层，实现"先诊断分类，再分流处理"。

    Usage:
        config = PipelineV2Config()
        pipeline = FactorProcessingPipelineV2(config)

        # 拟合
        pipeline.fit(factor_dict, industry_data=industry_series)

        # 变换
        results = pipeline.transform(factor_dict)

        # 查看分类结果
        print(pipeline.get_classification_summary())
    """

    def __init__(self, config: Optional[PipelineV2Config] = None, strict_mode: bool = False):
        self.config = config or PipelineV2Config()
        self.strict_mode = strict_mode

        # 前置智能层
        self.fingerprinter = FactorFingerprinter(self.config.fingerprint)
        self.classifier = AdaptiveFactorClassifier(self.config.classification)
        self.semantic_fusion = SemanticStatisticalFusion()

        # 三条处理管道
        self.static_pipeline: Optional[StaticFactorPipeline] = None
        self.dynamic_pipeline: Optional[DynamicFactorPipeline] = None
        self.mixed_pipeline: Optional[MixedFactorPipeline] = None

        # 监测器
        self.monitor = FactorFingerprintMonitor(self.config.monitor)

        # 状态追踪
        self.factor_classifications: Dict[str, ClassificationResult] = {}
        self.factor_pipelines: Dict[str, Any] = {}
        self.is_fitted = False

        logger.info("FactorProcessingPipelineV2 initialized")

    def fit(self,
            factor_data: Dict[str, pd.DataFrame],
            industry_data: Optional[pd.Series] = None,
            descriptions: Optional[Dict[str, str]] = None,
            **kwargs) -> 'FactorProcessingPipelineV2':
        """
        拟合整个流水线

        Parameters
        ----------
        factor_data : Dict[str, pd.DataFrame]
            因子名字到数据的映射
        industry_data : pd.Series, optional
            行业数据，用于中性化
        descriptions : Dict[str, str], optional
            因子名字到构造描述的映射（用于语义-统计融合）
        """
        logger.info(f"=== FactorProcessingPipelineV2.fit() ===")
        logger.info(f"Factors: {list(factor_data.keys())}")

        # 输入验证：检查空数据
        if not factor_data:
            raise ValueError("因子数据字典不能为空")

        # 检查所有因子数据是否为空
        empty_factors = [name for name, df in factor_data.items()
                        if df is None or (isinstance(df, pd.DataFrame) and df.empty)]
        if empty_factors:
            logger.warning(f"以下因子数据为空: {empty_factors}")

        # Step 1: 为每个因子提取指纹（带异常处理）
        logger.info("Step 1: Extracting fingerprints...")
        try:
            fingerprints = self.fingerprinter.batch_extract(factor_data)
        except Exception as e:
            logger.error(f"指纹提取失败: {e}")
            raise RuntimeError(f"指纹提取失败，请检查数据格式: {e}") from e

        # Step 2: 分类（支持语义-统计融合）
        logger.info("Step 2: Classifying factors...")
        if descriptions:
            # 使用语义-统计融合
            logger.info("Using semantic-statistical fusion...")
            data_months = kwargs.get('data_months', {})
            classifications = {}
            for name in factor_data:
                desc = descriptions.get(name, "")
                fp = fingerprints.get(name, FactorFingerprint())
                months = data_months.get(name, 0) if isinstance(data_months, dict) else 0
                
                if desc:
                    result = self.semantic_fusion.classify(desc, fp, months)
                else:
                    result = self.classifier.classify(fp)
                classifications[name] = result
                
                if hasattr(result, 'conflict_reason') and result.conflict_reason:
                    logger.warning(
                        f"Factor {name}: semantic-statistical conflict - "
                        f"{result.conflict_reason}"
                    )
        else:
            # 纯统计分类
            classifications = self.classifier.batch_classify(fingerprints)

        # Step 3: 初始化三条管道
        logger.info("Step 3: Initializing pipelines...")
        neutralizer_params = {'industry_data': industry_data} if industry_data is not None else {}

        self.static_pipeline = StaticFactorPipeline(
            neutralizer_params=neutralizer_params,
            enable_garch=self.config.static_enable_garch,
            garch_params={
                'p': self.config.static_garch_p,
                'q': self.config.static_garch_q,
                'vol': self.config.static_garch_vol,
                'min_obs': self.config.static_garch_min_obs,
            } if self.config.static_enable_garch else None
        )
        self.dynamic_pipeline = DynamicFactorPipeline(
            decorrelation_strength=self.config.dynamic_decorrelation_strength,
            max_ar_order=self.config.dynamic_max_ar_order,
            ar_criterion=self.config.dynamic_ar_criterion,
            neutralizer_params=neutralizer_params
        )
        self.mixed_pipeline = MixedFactorPipeline(
            conditional_transform=self.config.mixed_conditional_transform,
            skew_threshold=self.config.mixed_skew_threshold,
            kurt_threshold=self.config.mixed_kurt_threshold,
            neutralizer_params=neutralizer_params
        )

        # Step 4: 按类型分组拟合
        logger.info("Step 4: Fitting pipelines by factor type...")
        static_factors = []
        dynamic_factors = []
        mixed_factors = []

        for name, classification in classifications.items():
            self.factor_classifications[name] = classification

            if classification.primary_type == FactorType.STATIC:
                static_factors.append(name)
            elif classification.primary_type == FactorType.DYNAMIC:
                dynamic_factors.append(name)
            else:
                mixed_factors.append(name)

        # 合并同类型因子数据拟合管道
        if static_factors:
            logger.info(f"Static factors ({len(static_factors)}): {static_factors}")
            static_data = pd.concat([factor_data[name] for name in static_factors], axis=1)
            self.static_pipeline.fit(static_data, **kwargs)

        if dynamic_factors:
            logger.info(f"Dynamic factors ({len(dynamic_factors)}): {dynamic_factors}")
            dynamic_data = pd.concat([factor_data[name] for name in dynamic_factors], axis=1)
            self.dynamic_pipeline.fit(dynamic_data, **kwargs)

        if mixed_factors:
            logger.info(f"Mixed factors ({len(mixed_factors)}): {mixed_factors}")
            mixed_data = pd.concat([factor_data[name] for name in mixed_factors], axis=1)
            self.mixed_pipeline.fit(mixed_data, **kwargs)

        # Step 5: 记录到监测器
        logger.info("Step 5: Recording to monitor...")
        for name, fp in fingerprints.items():
            self.monitor.add_fingerprint(name, fp)

        self.is_fitted = True
        logger.info("=== Fit complete ===")
        return self

    def transform(self,
                  factor_data: Dict[str, pd.DataFrame],
                  **kwargs) -> Dict[str, pd.DataFrame]:
        """
        应用流水线

        Parameters
        ----------
        factor_data : Dict[str, pd.DataFrame]
            因子名字到数据的映射

        Returns
        -------
        Dict[str, pd.DataFrame]
            处理后的因子数据
        """
        if not self.is_fitted:
            raise ValueError("Pipeline未拟合，请先调用 fit()")

        results = {}

        for name, data in factor_data.items():
            if data is None or (isinstance(data, pd.DataFrame) and data.empty):
                logger.warning(f"因子 {name} 数据为空，跳过")
                continue

            classification = self.factor_classifications.get(name)
            if classification is None:
                logger.warning(f"因子 {name} 未分类，跳过")
                if self.strict_mode:
                    raise ValueError(f"因子 {name} 未在 fit 阶段分类，请在 strict_mode=False 时使用或重新拟合")
                continue

            # 路由到对应管道
            pipeline = self._get_pipeline(classification.primary_type)
            if pipeline is None:
                logger.warning(f"因子 {name} 类型 {classification.primary_type.value} 无对应管道")
                continue

            logger.info(f"Transforming {name} with {classification.primary_type.value} pipeline")
            results[name] = pipeline.transform(data, **kwargs)

        return results

    def fit_transform(self,
                      factor_data: Dict[str, pd.DataFrame],
                      industry_data: Optional[pd.Series] = None,
                      **kwargs) -> Dict[str, pd.DataFrame]:
        """拟合并变换"""
        return self.fit(factor_data, industry_data=industry_data, **kwargs).transform(factor_data, **kwargs)

    def _get_pipeline(self, factor_type: FactorType):
        """根据因子类型获取对应管道"""
        return {
            FactorType.STATIC: self.static_pipeline,
            FactorType.DYNAMIC: self.dynamic_pipeline,
            FactorType.MIXED: self.mixed_pipeline,
        }.get(factor_type)

    def get_classification_summary(self) -> pd.DataFrame:
        """获取分类汇总表"""
        return self.classifier.get_classification_summary(self.factor_classifications)

    def get_fingerprint_summary(self) -> pd.DataFrame:
        """获取指纹汇总表"""
        data = []
        for name, fp in self.monitor.fingerprint_history.items():
            if fp:
                latest = fp[-1]
                data.append({
                    'factor_name': name,
                    'ar1_median': latest.ar1_median,
                    'rank_autocorr': latest.rank_autocorr,
                    'sd_score': latest.sd_score,
                    'complexity_need': latest.complexity_need,
                    'snr_estimate': latest.snr_estimate,
                })
        return pd.DataFrame(data)

    def check_migrations(self,
                         factor_data: Dict[str, pd.DataFrame]
                         ) -> Dict[str, List[Any]]:
        """检查所有因子的类型迁移"""
        alerts = {}

        for name, data in factor_data.items():
            fp = self.fingerprinter.extract_fingerprint(data)
            migration_alerts = self.monitor.check_type_migration(name, fp)
            if migration_alerts:
                alerts[name] = migration_alerts

        return alerts

    def get_execution_summary(self) -> str:
        """获取执行摘要"""
        lines = ["=" * 60]
        lines.append("FactorProcessingPipelineV2 执行摘要")
        lines.append("=" * 60)

        # 分类结果
        lines.append("\n[因子分类结果]")
        summary = self.get_classification_summary()
        if not summary.empty:
            for _, row in summary.iterrows():
                lines.append(f"  {row['factor_name']}: {row['primary_type']} "
                           f"(prob={row['primary_prob']:.2f}, confidence={row['confidence']:.2f})")

        # 指纹摘要
        lines.append("\n[因子指纹摘要]")
        fp_summary = self.get_fingerprint_summary()
        if not fp_summary.empty:
            for _, row in fp_summary.iterrows():
                lines.append(f"  {row['factor_name']}: AR(1)={row['ar1_median']:.4f}, "
                           f"SD_Score={row['sd_score']:.4f}, SNR={row['snr_estimate']:.4f}")

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)
