# -*- coding: utf-8 -*-
"""
自适应因子分类器 (Adaptive Factor Classifier)

基于因子指纹，自动将因子分类为静态/动态/混合三类。
支持硬分类和软分类两种模式。

硬分类：基于阈值直接判断类别
软分类：基于sigmoid概率加权，避免硬切换
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import numpy as np
import pandas as pd
import logging

from .fingerprint import FactorFingerprint, FactorType

logger = logging.getLogger(__name__)


@dataclass
class ClassificationConfig:
    """分类器配置"""
    static_ar1_threshold: float = 0.80       # AR(1) > 0.80 → 静态
    dynamic_ar1_threshold: float = 0.40      # AR(1) < 0.40 → 动态
    soft_boundary: bool = True               # 是否使用软边界
    sigmoid_steepness: float = 10.0          # sigmoid陡峭度
    mixed_zone_width: float = 0.10           # 混合区半宽


@dataclass
class ClassificationResult:
    """分类结果（兼容旧版接口）"""
    primary_type: FactorType
    primary_prob: float
    secondary_type: Optional[FactorType] = None
    secondary_prob: float = 0.0
    confidence: float = 0.0
    is_hard: bool = True


class AdaptiveFactorClassifier:
    """
    自适应因子分类器

    基于因子指纹的AR(1)中位数，将因子分类为静态/动态/混合三类。
    支持硬分类和软分类两种模式。

    Usage:
        classifier = AdaptiveFactorClassifier()
        classification = classifier.classify(fingerprint)
        print(f"因子类型: {classification['hard_class']}")
        print(f"静态概率: {classification['soft_prob']['static']:.2%}")
    """

    def __init__(self, config: Optional[ClassificationConfig] = None):
        self.config = config or ClassificationConfig()
        logger.info(f"AdaptiveFactorClassifier initialized with config: {self.config}")

    def classify(self, fingerprint: FactorFingerprint) -> ClassificationResult:
        """
        对单个因子进行分类

        Parameters
        ----------
        fingerprint : FactorFingerprint
            因子指纹

        Returns
        -------
        ClassificationResult
            分类结果，包含主类型、概率、置信度等
        """
        ar1 = fingerprint.ar1_median

        if np.isnan(ar1):
            return ClassificationResult(
                primary_type=FactorType.UNKNOWN,
                primary_prob=0.0,
                confidence=0.0
            )

        # 硬分类
        hard_class = self._hard_classify(ar1)

        # 软分类
        if self.config.soft_boundary:
            soft_prob = self._soft_classify(ar1)
        else:
            soft_prob = self._hard_to_soft(hard_class)

        # 置信度
        confidence = self._compute_confidence(ar1, hard_class)

        # 确定主次类型
        sorted_probs = sorted(
            [(FactorType.STATIC, soft_prob['static']),
             (FactorType.MIXED, soft_prob['mixed']),
             (FactorType.DYNAMIC, soft_prob['dynamic'])],
            key=lambda x: x[1],
            reverse=True
        )

        primary_type, primary_prob = sorted_probs[0]
        secondary_type, secondary_prob = sorted_probs[1] if len(sorted_probs) > 1 else (None, 0.0)

        # 如果次类型概率为0，则不设置
        if secondary_prob <= 0:
            secondary_type = None
            secondary_prob = 0.0

        return ClassificationResult(
            primary_type=primary_type,
            primary_prob=primary_prob,
            secondary_type=secondary_type,
            secondary_prob=secondary_prob,
            confidence=confidence,
            is_hard=(confidence > 0.8)
        )

    def _hard_classify(self, ar1: float) -> FactorType:
        """硬分类"""
        if ar1 > self.config.static_ar1_threshold:
            return FactorType.STATIC
        elif ar1 < self.config.dynamic_ar1_threshold:
            return FactorType.DYNAMIC
        else:
            return FactorType.MIXED

    def _soft_classify(self, ar1: float) -> Dict[str, float]:
        """
        软分类：使用sigmoid概率加权

        避免硬切换，在边界区域给出平滑的概率分布。
        """
        k = self.config.sigmoid_steepness
        s_threshold = self.config.static_ar1_threshold
        d_threshold = self.config.dynamic_ar1_threshold

        # 静态概率：AR(1)越高，静态概率越高
        p_static = 1 / (1 + np.exp(-k * (ar1 - s_threshold)))

        # 动态概率：AR(1)越低，动态概率越高
        p_dynamic = 1 / (1 + np.exp(k * (ar1 - d_threshold)))

        # 混合概率：剩余概率
        p_mixed = 1 - p_static - p_dynamic

        # 确保概率非负
        p_mixed = max(p_mixed, 0.0)

        # 归一化
        total = p_static + p_mixed + p_dynamic
        if total > 0:
            p_static /= total
            p_mixed /= total
            p_dynamic /= total

        return {
            'static': float(p_static),
            'mixed': float(p_mixed),
            'dynamic': float(p_dynamic)
        }

    def _hard_to_soft(self, hard_class: FactorType) -> Dict[str, float]:
        """硬分类转软概率"""
        prob = {'static': 0.0, 'mixed': 0.0, 'dynamic': 0.0}
        prob[hard_class.value] = 1.0
        return prob

    def _compute_confidence(self, ar1: float, hard_class: FactorType) -> float:
        """计算分类置信度"""
        s_threshold = self.config.static_ar1_threshold
        d_threshold = self.config.dynamic_ar1_threshold

        if hard_class == FactorType.STATIC:
            distance = ar1 - s_threshold
        elif hard_class == FactorType.DYNAMIC:
            distance = d_threshold - ar1
        else:
            # 混合因子：距离边界越远，置信度越低
            distance_to_static = s_threshold - ar1
            distance_to_dynamic = ar1 - d_threshold
            distance = min(distance_to_static, distance_to_dynamic)

        # 归一化到[0, 1]
        confidence = min(abs(distance) / 0.2, 1.0)
        return float(confidence)

    def _is_in_boundary_zone(self, ar1: float) -> bool:
        """检查是否在边界区域"""
        s_threshold = self.config.static_ar1_threshold
        d_threshold = self.config.dynamic_ar1_threshold
        width = self.config.mixed_zone_width

        return (
            abs(ar1 - s_threshold) < width or
            abs(ar1 - d_threshold) < width
        )

    def batch_classify(self,
                       fingerprints: Dict[str, FactorFingerprint]
                       ) -> Dict[str, ClassificationResult]:
        """
        批量分类

        Parameters
        ----------
        fingerprints : Dict[str, FactorFingerprint]
            因子名字到指纹的映射

        Returns
        -------
        Dict[str, ClassificationResult]
            因子名字到分类结果的映射
        """
        return {name: self.classify(fp) for name, fp in fingerprints.items()}

    def get_classification_summary(self,
                                    classifications: Dict[str, ClassificationResult]
                                    ) -> pd.DataFrame:
        """获取分类汇总表"""
        data = []
        for name, result in classifications.items():
            data.append({
                'factor_name': name,
                'primary_type': result.primary_type.value,
                'primary_prob': result.primary_prob,
                'secondary_type': result.secondary_type.value if result.secondary_type else None,
                'secondary_prob': result.secondary_prob,
                'confidence': result.confidence,
                'is_hard': result.is_hard
            })
        return pd.DataFrame(data)

    def get_summary(self, df: pd.DataFrame) -> Dict[str, Any]:
        """获取分类汇总统计"""
        return {
            'total_factors': len(df),
            'static_count': (df['hard_class'] == 'static').sum(),
            'dynamic_count': (df['hard_class'] == 'dynamic').sum(),
            'mixed_count': (df['hard_class'] == 'mixed').sum(),
            'boundary_count': df['is_boundary'].sum(),
            'avg_confidence': df['confidence'].mean(),
            'avg_ar1': df['ar1_median'].mean()
        }
