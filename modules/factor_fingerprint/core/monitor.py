# -*- coding: utf-8 -*-
"""
因子指纹迁移监测器 (Factor Fingerprint Monitor)

持续监测因子指纹的漂移，当因子类型发生迁移时触发警报。
支持多时间尺度监测（快速/标准/长期）。

设计哲学（与项目保持一致）：
- 中间状态追踪：指纹历史可追溯
- C¹连续性保持：类型迁移时平滑过渡
- 前瞻偏差防护：基于历史指纹判断，无未来信息
"""

from typing import Dict, Any, List, Optional, NamedTuple
from dataclasses import dataclass
from datetime import datetime
import numpy as np
import pandas as pd
import logging

from .fingerprint import FactorFingerprint, FactorType
from .classifier import ClassificationResult, AdaptiveFactorClassifier

logger = logging.getLogger(__name__)


class MigrationAlert(NamedTuple):
    """迁移警报"""
    factor_name: str
    from_type: FactorType
    to_type: FactorType
    level: str          # 'WARNING', 'INFO', 'CRITICAL'
    window: int         # 监测窗口长度
    timestamp: datetime
    recommendation: str
    fingerprint_distance: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            'factor_name': self.factor_name,
            'from_type': self.from_type.value,
            'to_type': self.to_type.value,
            'level': self.level,
            'window': self.window,
            'timestamp': self.timestamp.isoformat(),
            'recommendation': self.recommendation,
            'fingerprint_distance': self.fingerprint_distance,
        }


@dataclass
class MonitorConfig:
    """监测器配置"""
    short_window: int = 1           # 快速监测窗口（期数）
    medium_window: int = 3          # 标准监测窗口（期数）
    long_window: int = 6            # 长期监测窗口（期数）
    short_threshold: float = 0.3    # 快速警报阈值（指纹距离）
    medium_threshold: float = 0.2   # 标准警报阈值
    long_threshold: float = 0.15    # 长期警报阈值
    migration_consecutive: int = 3  # 连续几期变化才触发迁移
    enable_smooth_transition: bool = True  # 是否启用平滑过渡


class FactorFingerprintMonitor:
    """
    因子指纹迁移监测器

    持续监测因子指纹的漂移，当因子类型发生迁移时触发警报。
    支持多时间尺度监测和软过渡策略。

    Usage:
        monitor = FactorFingerprintMonitor()
        monitor.add_fingerprint('PB', fingerprint_t1)
        monitor.add_fingerprint('PB', fingerprint_t2)
        alerts = monitor.check_type_migration('PB', current_fingerprint)
    """

    def __init__(self, config: Optional[MonitorConfig] = None):
        self.config = config or MonitorConfig()
        self.classifier = AdaptiveFactorClassifier()
        # 指纹历史: {因子名: [FactorFingerprint, ...]}
        self.fingerprint_history: Dict[str, List[FactorFingerprint]] = {}
        # 分类历史: {因子名: [ClassificationResult, ...]}
        self.classification_history: Dict[str, List[ClassificationResult]] = {}
        # 警报历史
        self.alert_history: List[MigrationAlert] = []

        logger.info(f"FactorFingerprintMonitor initialized with config: {self.config}")

    def add_fingerprint(self,
                        factor_name: str,
                        fingerprint: FactorFingerprint):
        """
        添加新的指纹到历史记录

        Parameters
        ----------
        factor_name : str
            因子名称
        fingerprint : FactorFingerprint
            当期指纹
        """
        if factor_name not in self.fingerprint_history:
            self.fingerprint_history[factor_name] = []
            self.classification_history[factor_name] = []

        self.fingerprint_history[factor_name].append(fingerprint)

        # 同步分类
        classification = self.classifier.classify(fingerprint)
        self.classification_history[factor_name].append(classification)

        logger.debug(f"Added fingerprint for {factor_name}: "
                    f"AR(1)={fingerprint.ar1_median:.4f}, "
                    f"Type={classification.primary_type.value}")

    def check_type_migration(self,
                             factor_name: str,
                             current_fingerprint: FactorFingerprint
                             ) -> List[MigrationAlert]:
        """
        检查因子类型是否发生迁移

        Parameters
        ----------
        factor_name : str
            因子名称
        current_fingerprint : FactorFingerprint
            当前期指纹

        Returns
        -------
        List[MigrationAlert]
            触发的警报列表（可能为空）
        """
        alerts = []

        # 先添加当前指纹
        self.add_fingerprint(factor_name, current_fingerprint)

        history = self.fingerprint_history.get(factor_name, [])
        class_history = self.classification_history.get(factor_name, [])

        if len(history) < 2:
            return alerts

        current_class = class_history[-1]

        # 1. 快速警报：单期剧烈变化
        if len(history) >= self.config.short_window + 1:
            short_alert = self._check_short_migration(
                factor_name, history, class_history
            )
            if short_alert:
                alerts.append(short_alert)

        # 2. 标准警报：3期趋势变化
        if len(history) >= self.config.medium_window:
            medium_alert = self._check_medium_migration(
                factor_name, history, class_history
            )
            if medium_alert:
                alerts.append(medium_alert)

        # 3. 长期警报：6期结构性漂移
        if len(history) >= self.config.long_window:
            long_alert = self._check_long_migration(
                factor_name, history, class_history
            )
            if long_alert:
                alerts.append(long_alert)

        # 记录警报
        self.alert_history.extend(alerts)

        return alerts

    def _check_short_migration(self,
                                factor_name: str,
                                history: List[FactorFingerprint],
                                class_history: List[ClassificationResult]
                                ) -> Optional[MigrationAlert]:
        """快速监测：单期剧烈变化"""
        current_fp = history[-1]
        prev_fp = history[-2]

        distance = self._compute_fingerprint_distance(current_fp, prev_fp)

        if distance > self.config.short_threshold:
            current_type = class_history[-1].primary_type
            prev_type = class_history[-2].primary_type

            if current_type != prev_type:
                return MigrationAlert(
                    factor_name=factor_name,
                    from_type=prev_type,
                    to_type=current_type,
                    level='WARNING',
                    window=self.config.short_window,
                    timestamp=datetime.now(),
                    recommendation="单期剧烈类型变化，建议复核数据质量",
                    fingerprint_distance=distance
                )

        return None

    def _check_medium_migration(self,
                                 factor_name: str,
                                 history: List[FactorFingerprint],
                                 class_history: List[ClassificationResult]
                                 ) -> Optional[MigrationAlert]:
        """标准监测：3期趋势变化"""
        recent_classes = [c.primary_type for c in class_history[-self.config.medium_window:]]
        current_type = recent_classes[-1]

        # 检查是否连续变化
        if all(t != current_type for t in recent_classes[:-1]):
            # 连续变化，但检查是否都在边界附近
            recent_fps = history[-self.config.medium_window:]
            avg_distance = self._compute_average_distance(recent_fps)

            if avg_distance > self.config.medium_threshold:
                prev_type = recent_classes[-2]
                return MigrationAlert(
                    factor_name=factor_name,
                    from_type=prev_type,
                    to_type=current_type,
                    level='INFO',
                    window=self.config.medium_window,
                    timestamp=datetime.now(),
                    recommendation="连续3期类型变化，建议采用平滑过渡策略",
                    fingerprint_distance=avg_distance
                )

        return None

    def _check_long_migration(self,
                               factor_name: str,
                               history: List[FactorFingerprint],
                               class_history: List[ClassificationResult]
                               ) -> Optional[MigrationAlert]:
        """长期监测：6期结构性漂移"""
        recent_classes = [c.primary_type for c in class_history[-self.config.long_window:]]

        # 检查长期趋势
        type_counts = {}
        for t in recent_classes:
            type_counts[t] = type_counts.get(t, 0) + 1

        current_type = recent_classes[-1]
        current_count = type_counts.get(current_type, 0)

        # 如果当前类型在最近6期中占主导（>50%），且与6期前不同
        if current_count >= self.config.long_window // 2:
            old_type = class_history[-self.config.long_window].primary_type
            if old_type != current_type:
                recent_fps = history[-self.config.long_window:]
                avg_distance = self._compute_average_distance(recent_fps)

                if avg_distance > self.config.long_threshold:
                    return MigrationAlert(
                        factor_name=factor_name,
                        from_type=old_type,
                        to_type=current_type,
                        level='INFO',
                        window=self.config.long_window,
                        timestamp=datetime.now(),
                        recommendation="长期结构性漂移确认，可永久调整分类",
                        fingerprint_distance=avg_distance
                    )

        return None

    def get_transition_weights(self,
                               factor_name: str,
                               current_fingerprint: FactorFingerprint
                               ) -> Dict[FactorType, float]:
        """
        获取类型迁移时的过渡权重

        当因子处于类型迁移期时，返回新旧管道的混合权重。
        采用指数衰减平滑，避免硬切换。

        Parameters
        ----------
        factor_name : str
            因子名称
        current_fingerprint : FactorFingerprint
            当前指纹

        Returns
        -------
        Dict[FactorType, float]
            各类型对应的权重
        """
        class_history = self.classification_history.get(factor_name, [])

        if len(class_history) < 2 or not self.config.enable_smooth_transition:
            # 无历史或禁用平滑，直接返回当前类型
            current = class_history[-1] if class_history else \
                self.classifier.classify(current_fingerprint)
            return {current.primary_type: 1.0}

        current = class_history[-1]

        # 检查最近是否有迁移
        recent_types = [c.primary_type for c in class_history[-3:]]
        if len(set(recent_types)) == 1:
            # 最近3期类型一致，无迁移
            return {current.primary_type: 1.0}

        # 有迁移，计算过渡权重
        # 使用指数衰减：越近的类型权重越高
        weights = {}
        decay = 0.7  # 衰减因子

        for i, cls in enumerate(class_history[-5:]):
            w = decay ** (4 - i)
            t = cls.primary_type
            weights[t] = weights.get(t, 0) + w

        # 归一化
        total = sum(weights.values())
        return {t: w / total for t, w in weights.items()}

    def _compute_fingerprint_distance(self,
                                      fp1: FactorFingerprint,
                                      fp2: FactorFingerprint) -> float:
        """
        计算两个指纹之间的欧氏距离

        使用归一化后的关键指标计算。
        """
        # 选择关键指标
        keys = ['ar1_median', 'rank_autocorr', 'skewness_std', 'kurtosis_std']

        vec1 = []
        vec2 = []

        for key in keys:
            v1 = getattr(fp1, key)
            v2 = getattr(fp2, key)

            if not np.isnan(v1) and not np.isnan(v2):
                vec1.append(v1)
                vec2.append(v2)

        if not vec1:
            return 0.0

        vec1 = np.array(vec1)
        vec2 = np.array(vec2)

        return float(np.linalg.norm(vec1 - vec2) / np.sqrt(len(vec1)))

    def _compute_average_distance(self,
                                   fingerprints: List[FactorFingerprint]) -> float:
        """计算指纹列表的平均 pairwise 距离"""
        if len(fingerprints) < 2:
            return 0.0

        distances = []
        for i in range(len(fingerprints)):
            for j in range(i + 1, len(fingerprints)):
                d = self._compute_fingerprint_distance(fingerprints[i], fingerprints[j])
                distances.append(d)

        return float(np.mean(distances)) if distances else 0.0

    def get_migration_summary(self,
                              factor_name: Optional[str] = None
                              ) -> pd.DataFrame:
        """
        获取迁移摘要

        Parameters
        ----------
        factor_name : str, optional
            指定因子名，None则返回所有因子的摘要

        Returns
        -------
        pd.DataFrame
            迁移摘要表
        """
        alerts = self.alert_history
        if factor_name:
            alerts = [a for a in alerts if a.factor_name == factor_name]

        if not alerts:
            return pd.DataFrame()

        data = [a.to_dict() for a in alerts]
        return pd.DataFrame(data)

    def get_factor_stability_score(self, factor_name: str) -> float:
        """
        获取因子的稳定性得分

        基于分类历史的类型一致性计算。
        得分越高，因子类型越稳定。

        Parameters
        ----------
        factor_name : str
            因子名称

        Returns
        -------
        float
            稳定性得分 [0, 1]
        """
        class_history = self.classification_history.get(factor_name, [])

        if len(class_history) < 3:
            return 0.5  # 数据不足，返回中性值

        recent_types = [c.primary_type for c in class_history[-6:]]

        # 计算类型一致性
        type_counts = {}
        for t in recent_types:
            type_counts[t] = type_counts.get(t, 0) + 1

        max_count = max(type_counts.values())
        stability = max_count / len(recent_types)

        return float(stability)
