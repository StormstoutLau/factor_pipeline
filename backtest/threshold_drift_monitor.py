# -*- coding: utf-8 -*-
"""阈值漂移监测器 (v2.6.0 P3-12' / E8)

监测最优阈值组合的 IC 衰减, 触发重新搜索.
区别于 UnifiedDriftReporter (监测因子漂移), 本类监测阈值有效性.

学术依据:
- Bailey & López de Prado (2014) "The Deflated Sharpe Ratio" JPM 40(5):94-107
- Sullivan, Timmermann & White (1999) "Data-Snooping" JF 54(5):1647-1691
- McLean & Pontiff (2016) "Does Academic Research Destroy Stock Return Predictability?" JF 71(1):5-32
"""
from typing import Dict, List, Optional
import logging
import numpy as np

logger = logging.getLogger(__name__)


class ThresholdDriftMonitor:
    """阈值漂移监测器

    监测最优阈值组合的 IC 衰减, 触发重新搜索.

    区别于 UnifiedDriftReporter (监测因子漂移), 本类监测阈值有效性:
    - UnifiedDriftReporter: 监测因子本身的漂移 (IC 分布 / ICIR / 换手率)
    - ThresholdDriftMonitor: 监测阈值组合的有效性 (best_score 衰减)

    Usage:
        monitor = ThresholdDriftMonitor(best_score=0.05, best_params={...})
        verdict = monitor.update(current_score=0.035)
        if verdict['needs_research']:
            # 触发重新搜索
            optimizer.optimize(...)
    """

    def __init__(
        self,
        best_score: float,
        best_params: Dict[str, float],
        halflife: int = 63,
        decay_threshold: float = 0.2,
        min_observations: int = 5,
    ):
        """初始化阈值漂移监测器

        Args:
            best_score: 优化器搜索出的最优分数
            best_params: 最优参数字典
            halflife: EWMA 半衰期 (日频默认 63)
            decay_threshold: 衰减阈值 (默认 0.2 = 20%)
            min_observations: 最小观测数 (默认 5, 不足时不判定)
        """
        self.best_score = best_score
        self.best_params = best_params
        self.halflife = halflife
        self.decay_threshold = decay_threshold
        self.min_observations = min_observations
        self.score_history: List[float] = []

        logger.info(
            f"ThresholdDriftMonitor initialized: "
            f"best_score={best_score:.6f}, halflife={halflife}"
        )

    def update(self, current_score: float) -> Dict:
        """更新当前评分, 返回是否需要重新搜索

        Args:
            current_score: 当前周期的评分 (用 best_params 计算)

        Returns:
            {
                'needs_research': bool,
                'decay_ratio': float,  # EWMA(current) / best_score
                'best_score': float,
                'current_score': float,
                'ewma_score': float,
                'n_observations': int,
            }
        """
        self.score_history.append(current_score)

        if len(self.score_history) < self.min_observations:
            return {
                'needs_research': False,
                'decay_ratio': 1.0,
                'best_score': self.best_score,
                'current_score': current_score,
                'ewma_score': current_score,
                'n_observations': len(self.score_history),
                'reason': f'观测数不足 ({len(self.score_history)} < {self.min_observations})',
            }

        # EWMA 加权评分
        ewma_score = self._compute_ewma()

        # 衰减比例
        if abs(self.best_score) < 1e-10:
            decay_ratio = 1.0
        else:
            decay_ratio = ewma_score / self.best_score

        # 触发条件: EWMA 衰减 > decay_threshold (默认 20%)
        needs_research = decay_ratio < (1.0 - self.decay_threshold)

        result = {
            'needs_research': needs_research,
            'decay_ratio': float(decay_ratio),
            'best_score': self.best_score,
            'current_score': current_score,
            'ewma_score': float(ewma_score),
            'n_observations': len(self.score_history),
        }

        if needs_research:
            result['reason'] = (
                f'EWMA 衰减 {1 - decay_ratio:.1%} > 阈值 {self.decay_threshold:.1%}'
            )
            logger.warning(
                f"ThresholdDriftMonitor: 需要重新搜索. "
                f"decay_ratio={decay_ratio:.4f}, ewma_score={ewma_score:.6f}"
            )

        return result

    def _compute_ewma(self) -> float:
        """计算 EWMA 加权评分

        EWMA: s[t] = alpha * x[t] + (1-alpha) * s[t-1]
        alpha = 1 - exp(-ln2/halflife)
        """
        if not self.score_history:
            return 0.0

        alpha = 1.0 - np.exp(-np.log(2.0) / max(self.halflife, 1))
        ewma = self.score_history[0]
        for score in self.score_history[1:]:
            ewma = alpha * score + (1 - alpha) * ewma
        return float(ewma)

    def get_history(self) -> List[float]:
        """获取评分历史 (返回副本, 修改不影响内部)"""
        return self.score_history.copy()

    def reset(self, best_score: float, best_params: Dict[str, float]):
        """重置监测器 (重新搜索后调用)

        Args:
            best_score: 新的最优分数
            best_params: 新的最优参数
        """
        self.best_score = best_score
        self.best_params = best_params
        self.score_history = []
        logger.info(f"ThresholdDriftMonitor reset: best_score={best_score:.6f}")
