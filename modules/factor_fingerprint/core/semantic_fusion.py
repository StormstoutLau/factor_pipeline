# -*- coding: utf-8 -*-
"""
语义-统计融合模块

实现"先验引导，后验校准"的混合决策体系。
核心组件：
- SemanticPrior: 语义先验，将语义分析结果转换为统计先验分布
- BayesianFactorClassifier: 贝叶斯分类器，支持语义先验的融合分类
- ConflictArbitrator: 冲突仲裁引擎，处理语义与统计不一致的情况
- SemanticStatisticalFusion: 端到端融合接口

设计哲学：
- 冷启动信任语义：数据不足时，语义是唯一可靠依据
- 数据充足信任统计：统计指纹是因子本质的反映
- 冲突时保守降级：不一致时采用最保守的混合管道
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import numpy as np
import logging

from .fingerprint import FactorFingerprint, FactorType
from .classifier import ClassificationResult, AdaptiveFactorClassifier, ClassificationConfig
from .semantic import ExtractedRule, FactorSemanticUnderstanding

logger = logging.getLogger(__name__)


# =============================================================================
# 冲突诊断类型
# =============================================================================

class ConflictDiagnosis(Enum):
    """冲突诊断类型"""
    DESCRIPTION_ERROR = "description_error"
    MARKET_REGIME_CHANGE = "regime_change"
    CONSTRUCTION_IMPURITY = "impurity"
    STATISTICAL_NOISE = "noise"
    HUMAN_REVIEW = "human_review"


# =============================================================================
# 语义先验
# =============================================================================

@dataclass
class SemanticPrior:
    """
    语义先验：将语义分析结果转换为统计分类器可理解的先验分布
    
    Attributes
    ----------
    expected_type : FactorType
        语义推断的因子类型
    prior_strength : float
        先验强度 [0, 1]，0=无先验，1=完全信任先验
    confidence : float
        语义分析的置信度
    """
    expected_type: FactorType
    prior_strength: float = 0.7
    confidence: float = 0.7
    
    # 类别到类型的映射
    CATEGORY_TO_TYPE = {
        'value': FactorType.STATIC,
        'quality': FactorType.STATIC,
        'size': FactorType.STATIC,
        'momentum': FactorType.MIXED,
        'growth': FactorType.MIXED,
        'reversal': FactorType.DYNAMIC,
        'liquidity': FactorType.DYNAMIC,
        'sentiment': FactorType.DYNAMIC,
    }
    
    # 稳定性到类型的映射
    STABILITY_TO_TYPE = {
        'static': FactorType.STATIC,
        'dynamic': FactorType.DYNAMIC,
        'mixed': FactorType.MIXED,
    }
    
    # AR(1) 先验分布参数 (均值, 标准差)
    AR1_PRIOR_MAP = {
        FactorType.STATIC: (0.85, 0.10),
        FactorType.MIXED: (0.60, 0.15),
        FactorType.DYNAMIC: (0.20, 0.10),
        FactorType.UNKNOWN: (0.50, 0.25),
    }
    
    def to_ar1_prior(self) -> Tuple[float, float]:
        """
        将语义类型转换为 AR(1) 的高斯先验分布
        
        Returns
        -------
        Tuple[float, float]
            (均值, 标准差)
        """
        return self.AR1_PRIOR_MAP.get(self.expected_type, (0.50, 0.25))
    
    @classmethod
    def from_extracted_rule(cls, rule: ExtractedRule) -> 'SemanticPrior':
        """
        从 ExtractedRule 创建 SemanticPrior
        
        Parameters
        ----------
        rule : ExtractedRule
            语义分析提取的规则
            
        Returns
        -------
        SemanticPrior
            语义先验对象
        """
        # 确定因子类型
        factor_type = FactorType.UNKNOWN
        
        # 优先使用 category 映射
        if rule.category and rule.category in cls.CATEGORY_TO_TYPE:
            factor_type = cls.CATEGORY_TO_TYPE[rule.category]
        
        # 计算先验强度
        prior_strength = rule.category_confidence * 0.8
        prior_strength += rule.overall_confidence * 0.2
        prior_strength = min(prior_strength, 1.0)
        
        return cls(
            expected_type=factor_type,
            prior_strength=prior_strength,
            confidence=rule.overall_confidence
        )
    
    @classmethod
    def from_description(cls, description: str) -> 'SemanticPrior':
        """
        从自然语言描述直接创建 SemanticPrior
        
        Parameters
        ----------
        description : str
            因子构造描述
            
        Returns
        -------
        SemanticPrior
            语义先验对象
        """
        analyzer = FactorSemanticUnderstanding()
        rule = analyzer.understand(description)
        return cls.from_extracted_rule(rule)


# =============================================================================
# 贝叶斯分类器
# =============================================================================

class BayesianFactorClassifier(AdaptiveFactorClassifier):
    """
    贝叶斯因子分类器
    
    在统计分类基础上，支持语义先验的贝叶斯融合。
    当语义与统计一致时提升置信度，冲突时标记为软分类。
    """
    
    def __init__(self, config: Optional[ClassificationConfig] = None):
        super().__init__(config)
        logger.info("BayesianFactorClassifier initialized")
    
    def classify_with_prior(self,
                           fingerprint: FactorFingerprint,
                           prior: Optional[SemanticPrior] = None
                           ) -> ClassificationResult:
        """
        支持语义先验的分类
        
        Parameters
        ----------
        fingerprint : FactorFingerprint
            因子指纹（统计证据）
        prior : SemanticPrior, optional
            语义先验
            
        Returns
        -------
        ClassificationResult
            融合后的分类结果
        """
        # 纯统计分类（基准）
        statistical = self.classify(fingerprint)
        
        # 无先验：退化为纯统计
        if prior is None or prior.prior_strength <= 0:
            return statistical
        
        # 数据无效（NaN）但语义先验存在：信任语义
        if np.isnan(fingerprint.ar1_median):
            return ClassificationResult(
                primary_type=prior.expected_type,
                primary_prob=prior.confidence,
                confidence=prior.confidence * 0.7,
                is_hard=False
            )
        
        # 一致：提升置信度
        if statistical.primary_type == prior.expected_type:
            boosted_confidence = min(
                statistical.confidence * (1 + prior.prior_strength * 0.3),
                1.0
            )
            return ClassificationResult(
                primary_type=statistical.primary_type,
                primary_prob=statistical.primary_prob,
                secondary_type=statistical.secondary_type,
                secondary_prob=statistical.secondary_prob,
                confidence=boosted_confidence,
                is_hard=(boosted_confidence > 0.8)
            )
        
        # 冲突：数据充足时信任统计，但标记为软分类
        # 计算后验概率（简化版贝叶斯更新）
        prior_prob = prior.prior_strength
        likelihood_prob = statistical.primary_prob
        
        # 数据充足度影响权重
        data_weight = self._estimate_data_weight(fingerprint)
        
        if data_weight > 0.7:
            # 数据充足：统计主导
            return ClassificationResult(
                primary_type=statistical.primary_type,
                primary_prob=statistical.primary_prob,
                secondary_type=prior.expected_type,
                secondary_prob=prior.confidence * (1 - data_weight),
                confidence=statistical.confidence * 0.7,
                is_hard=False
            )
        else:
            # 数据不足：语义主导
            return ClassificationResult(
                primary_type=prior.expected_type,
                primary_prob=prior.confidence,
                secondary_type=statistical.primary_type,
                secondary_prob=statistical.primary_prob * data_weight,
                confidence=prior.confidence * 0.7,
                is_hard=False
            )
    
    def _estimate_data_weight(self, fingerprint: FactorFingerprint) -> float:
        """
        估计数据充足度权重
        
        基于指纹的可靠性指标。
        """
        # 简化：基于 AR(1) 的置信度
        if np.isnan(fingerprint.ar1_median):
            return 0.0
        
        # AR(1) 越远离边界，数据越可靠
        ar1 = fingerprint.ar1_median
        distance_to_boundary = min(
            abs(ar1 - self.config.static_ar1_threshold),
            abs(ar1 - self.config.dynamic_ar1_threshold)
        )
        
        return min(distance_to_boundary * 5, 1.0)


# =============================================================================
# 冲突仲裁引擎
# =============================================================================

@dataclass
class ArbitratedResult(ClassificationResult):
    """仲裁结果，扩展 ClassificationResult 增加冲突信息"""
    conflict_reason: Optional[str] = None
    diagnosis: Optional[ConflictDiagnosis] = None


class ConflictArbitrator:
    """
    语义-统计冲突仲裁引擎
    
    当语义先验与统计结果不一致时，根据数据充足度进行仲裁。
    """
    
    def __init__(self):
        self.conflict_history: List[Dict] = []
        logger.info("ConflictArbitrator initialized")
    
    def arbitrate(self,
                  semantic_result: SemanticPrior,
                  statistical_result: ClassificationResult,
                  data_sufficiency: float
                  ) -> ArbitratedResult:
        """
        仲裁语义与统计的冲突
        
        Parameters
        ----------
        semantic_result : SemanticPrior
            语义先验
        statistical_result : ClassificationResult
            统计分类结果
        data_sufficiency : float
            数据充足度 [0, 1]
            
        Returns
        -------
        ArbitratedResult
            仲裁结果
        """
        # 情况A：一致 → 高置信度锁定
        if semantic_result.expected_type == statistical_result.primary_type:
            return self._high_confidence_lock(statistical_result)
        
        # 情况B：不一致 → 分阶段处理
        if data_sufficiency < 0.3:
            # 初始期：信任语义
            return self._semantic_override(
                semantic_result, statistical_result,
                reason="insufficient_data"
            )
        elif data_sufficiency < 0.7:
            # 观察期：降级到混合
            return self._fallback_to_mixed(
                semantic_result, statistical_result,
                reason="observation_period"
            )
        else:
            # 数据充足：触发人工审查
            return self._alert_human_review(
                semantic_result, statistical_result,
                reason="persistent_conflict"
            )
    
    def _high_confidence_lock(self,
                               statistical: ClassificationResult
                               ) -> ArbitratedResult:
        """高置信度锁定"""
        return ArbitratedResult(
            primary_type=statistical.primary_type,
            primary_prob=statistical.primary_prob,
            secondary_type=statistical.secondary_type,
            secondary_prob=statistical.secondary_prob,
            confidence=min(statistical.confidence * 1.1, 1.0),
            is_hard=True,
            conflict_reason=None,
            diagnosis=None
        )
    
    def _semantic_override(self,
                           semantic: SemanticPrior,
                           statistical: ClassificationResult,
                           reason: str
                           ) -> ArbitratedResult:
        """语义覆盖（数据不足时）"""
        return ArbitratedResult(
            primary_type=semantic.expected_type,
            primary_prob=semantic.confidence,
            secondary_type=statistical.primary_type,
            secondary_prob=statistical.primary_prob,
            confidence=semantic.confidence * 0.7,
            is_hard=False,
            conflict_reason=reason,
            diagnosis=ConflictDiagnosis.DESCRIPTION_ERROR
        )
    
    def _fallback_to_mixed(self,
                           semantic: SemanticPrior,
                           statistical: ClassificationResult,
                           reason: str
                           ) -> ArbitratedResult:
        """降级到混合管道（观察期）"""
        return ArbitratedResult(
            primary_type=FactorType.MIXED,
            primary_prob=0.5,
            secondary_type=semantic.expected_type,
            secondary_prob=semantic.confidence * 0.3,
            confidence=0.5,
            is_hard=False,
            conflict_reason=reason,
            diagnosis=ConflictDiagnosis.STATISTICAL_NOISE
        )
    
    def _alert_human_review(self,
                            semantic: SemanticPrior,
                            statistical: ClassificationResult,
                            reason: str
                            ) -> ArbitratedResult:
        """触发人工审查（持续冲突）"""
        # 记录冲突
        self.conflict_history.append({
            'semantic_type': semantic.expected_type.value,
            'statistical_type': statistical.primary_type.value,
            'reason': reason
        })
        
        # 数据充足时信任统计，但标记需要审查
        return ArbitratedResult(
            primary_type=statistical.primary_type,
            primary_prob=statistical.primary_prob,
            secondary_type=semantic.expected_type,
            secondary_prob=semantic.confidence,
            confidence=statistical.confidence * 0.6,
            is_hard=False,
            conflict_reason=f"{reason}:human_review",
            diagnosis=ConflictDiagnosis.HUMAN_REVIEW
        )


# =============================================================================
# 端到端融合接口
# =============================================================================

class SemanticStatisticalFusion:
    """
    语义-统计端到端融合接口
    
    整合语义分析、统计指纹、贝叶斯分类和冲突仲裁的完整流程。
    
    Usage:
        fusion = SemanticStatisticalFusion()
        result = fusion.classify(
            description="市盈率因子",
            fingerprint=fp,
            data_months=36
        )
    """
    
    def __init__(self):
        self.semantic_analyzer = FactorSemanticUnderstanding()
        self.classifier = BayesianFactorClassifier()
        self.arbitrator = ConflictArbitrator()
        logger.info("SemanticStatisticalFusion initialized")
    
    def classify(self,
                 description: str,
                 fingerprint: FactorFingerprint,
                 data_months: int = 0
                 ) -> ArbitratedResult:
        """
        融合分类
        
        Parameters
        ----------
        description : str
            因子构造描述
        fingerprint : FactorFingerprint
            因子指纹
        data_months : int
            数据历史月数
            
        Returns
        -------
        ArbitratedResult
            融合分类结果
        """
        # Step 1: 语义分析
        semantic_prior = SemanticPrior.from_description(description)
        logger.info(f"Semantic analysis: {semantic_prior.expected_type.value}, "
                   f"confidence={semantic_prior.confidence:.2f}")
        
        # Step 2: 统计分类（带先验）
        statistical_result = self.classifier.classify_with_prior(
            fingerprint, semantic_prior
        )
        logger.info(f"Statistical classification: {statistical_result.primary_type.value}, "
                   f"confidence={statistical_result.confidence:.2f}")
        
        # Step 3: 计算数据充足度
        data_sufficiency = self._compute_data_sufficiency(data_months, fingerprint)
        
        # Step 4: 冲突仲裁
        if semantic_prior.expected_type == statistical_result.primary_type:
            # 一致：直接返回
            return self.arbitrator._high_confidence_lock(statistical_result)
        
        return self.arbitrator.arbitrate(
            semantic_prior, statistical_result, data_sufficiency
        )
    
    def classify_batch(self,
                       descriptions: Dict[str, str],
                       fingerprints: Dict[str, FactorFingerprint],
                       data_months: Dict[str, int] = None
                       ) -> Dict[str, ArbitratedResult]:
        """
        批量融合分类
        
        Parameters
        ----------
        descriptions : Dict[str, str]
            因子名字到描述的映射
        fingerprints : Dict[str, FactorFingerprint]
            因子名字到指纹的映射
        data_months : Dict[str, int], optional
            因子名字到数据月数的映射
            
        Returns
        -------
        Dict[str, ArbitratedResult]
            融合分类结果
        """
        results = {}
        for name in descriptions:
            fp = fingerprints.get(name, FactorFingerprint())
            months = data_months.get(name, 0) if data_months else 0
            results[name] = self.classify(descriptions[name], fp, months)
        return results
    
    def _compute_data_sufficiency(self,
                                   data_months: int,
                                   fingerprint: FactorFingerprint
                                   ) -> float:
        """
        计算数据充足度
        
        综合考虑数据长度和指纹质量。
        """
        # 基础充足度：基于数据长度
        length_score = min(data_months / 24, 1.0)
        
        # 质量分数：基于指纹有效性
        quality_score = 0.0
        if not np.isnan(fingerprint.ar1_median):
            quality_score += 0.5
        if not np.isnan(fingerprint.rank_autocorr):
            quality_score += 0.3
        if not np.isnan(fingerprint.sd_score):
            quality_score += 0.2
        
        return length_score * 0.6 + quality_score * 0.4
