# -*- coding: utf-8 -*-
"""CUSUM 漂移监测器 (v3.0.0 T3)

Page (1954) CUSUM 累积和算法, 用于在线检测因子分布漂移.

区别于 ThresholdDriftMonitor (EWMA 监测 score 衰减):
- ThresholdDriftMonitor: 监测阈值组合有效性 (best_score 衰减), 用 EWMA
- CUSUMDriftMonitor: 监测因子分布本身漂移 (均值/统计量偏离), 用累积和

CUSUM 算法:
    上侧检测 (检测向上漂移):
        S_pos[t] = max(0, S_pos[t-1] + (x[t] - mu0 - k))
        触发: S_pos[t] > h
    下侧检测 (检测向下漂移):
        S_neg[t] = min(0, S_neg[t-1] + (x[t] - mu0 + k))
        触发: S_neg[t] < -h  (等价 |S_neg[t]| > h)

参数:
    mu0 (baseline_mean): 基线均值 (in-control mean)
    sigma (baseline_std): 基线标准差 (用于 k/h 的标准化)
    k: slack parameter, 单位 sigma, 通常 0.5 (检测半漂移)
    h: trigger threshold, 单位 sigma, 通常 4-5
       (h=5 时 in-control ARL ≈ 930, 误报率约 1/930)

学术依据:
- Page, E. S. (1954). "Continuous Inspection Schemes." Biometrika 41(1/2):100-115.
- Brown, R. L., Durbin, J. & Evans, J. M. (1975). "Techniques for Testing the
  Constancy of Regression Relationships over Time." JRSS-B 37(2):149-192.
- Csorgo, M. & Horvath, L. (1997). "Limit Theorems in Change-Point Analysis."
  Wiley.

ARL (Average Run Length) 校准:
- in-control ARL (无漂移时平均误报间隔): 由 h 主导, h=5sigma 时约 930
- out-of-control ARL (漂移后平均检测延迟): 由 k 和漂移大小主导
    * 1sigma 漂移, k=0.5: ARL ≈ 10
    * 0.5sigma 漂移, k=0.5: ARL ≈ 38
    * 3sigma 漂移, k=0.5: ARL ≈ 2
- 具体值需通过 Monte Carlo 或 Siegmund (1985) 近似公式校准
"""
from typing import Dict, List, Optional
import logging
import numpy as np

logger = logging.getLogger(__name__)


class CUSUMDriftMonitor:
    """CUSUM 累积和漂移监测器

    在线检测因子分布漂移, 基于 Page (1954) 累积和算法.

    Usage:
        # 假设因子 IC 基线 mean=0.03, std=0.05
        monitor = CUSUMDriftMonitor(
            baseline_mean=0.03, baseline_std=0.05,
            k=0.5, h=5.0
        )
        for ic in ic_series:
            result = monitor.update(ic)
            if result['detected']:
                print(f"漂移检测! direction={result['direction']}")
                # 触发重训练 / 漂移报告
    """

    def __init__(
        self,
        baseline_mean: float,
        baseline_std: float,
        k: float = 0.5,
        h: float = 5.0,
        min_observations: int = 1,
        two_sided: bool = True,
    ):
        """初始化 CUSUM 漂移监测器

        Args:
            baseline_mean: 基线均值 mu0 (in-control mean)
            baseline_std: 基线标准差 sigma (用于 k/h 标准化, 必须 > 0)
            k: slack parameter, 单位 sigma (通常 0.5, 检测半漂移)
            h: trigger threshold, 单位 sigma (通常 4-5)
            min_observations: 最小观测数 (不足时不判定)
            two_sided: True=双向检测 (上侧+下侧), False=仅上侧

        Raises:
            ValueError: baseline_std <= 0 或 k < 0 或 h < 0
        """
        if baseline_std <= 0:
            raise ValueError(
                f"baseline_std must be positive, got {baseline_std}"
            )
        if k < 0:
            raise ValueError(f"k must be non-negative, got {k}")
        if h < 0:
            raise ValueError(f"h must be non-negative, got {h}")

        self.baseline_mean = float(baseline_mean)
        self.baseline_std = float(baseline_std)
        self.k = float(k)
        self.h = float(h)
        self.min_observations = int(min_observations)
        self.two_sided = bool(two_sided)

        # 累积和 (内部状态)
        self.S_pos: float = 0.0  # 上侧累积和
        self.S_neg: float = 0.0  # 下侧累积和 (存储负值, |S_neg| 为其绝对值)

        # 历史
        self.score_history: List[float] = []
        self.S_pos_history: List[float] = []
        self.S_neg_history: List[float] = []
        self.detected_history: List[bool] = []

        logger.info(
            f"CUSUMDriftMonitor initialized: "
            f"mu0={baseline_mean}, sigma={baseline_std}, "
            f"k={k}sigma, h={h}sigma, two_sided={two_sided}"
        )

    def update(self, x: float) -> Dict:
        """单期更新累积和, 返回检测结果

        Args:
            x: 当期观测值 (如因子 IC / 因子均值 / 统计量)

        Returns:
            {
                'detected': bool,           # 是否触发
                'direction': 'up'|'down'|None,  # 漂移方向
                'S_pos': float,             # 上侧累积和
                'S_neg': float,             # 下侧累积和 (负值)
                'n_observations': int,      # 累计观测数
                'reason': str,              # 触发原因 (仅 detected=True 时)
            }
        """
        # NaN 处理: 跳过, 不更新累积和
        if np.isnan(x):
            self.score_history.append(x)
            self.S_pos_history.append(self.S_pos)
            self.S_neg_history.append(self.S_neg)
            self.detected_history.append(False)
            return {
                'detected': False,
                'direction': None,
                'S_pos': self.S_pos,
                'S_neg': self.S_neg,
                'n_observations': len(self.score_history),
                'reason': 'NaN input, skipped',
            }

        self.score_history.append(x)

        # 标准化 slack (k * sigma)
        k_sigma = self.k * self.baseline_std
        # 标准化 threshold (h * sigma)
        h_sigma = self.h * self.baseline_std

        # CUSUM 递推 (Page 1954)
        # 上侧: S_pos[t] = max(0, S_pos[t-1] + (x - mu0 - k_sigma))
        self.S_pos = max(0.0, self.S_pos + (x - self.baseline_mean - k_sigma))

        # 下侧: S_neg[t] = min(0, S_neg[t-1] + (x - mu0 + k_sigma))
        if self.two_sided:
            self.S_neg = min(0.0, self.S_neg + (x - self.baseline_mean + k_sigma))
        else:
            self.S_neg = 0.0

        # 触发判定
        detected = False
        direction: Optional[str] = None
        reason = ''

        # min_observations 检查
        n_obs = len([s for s in self.score_history if not np.isnan(s)])

        if n_obs >= self.min_observations:
            # 上侧触发
            if self.S_pos > h_sigma:
                detected = True
                direction = 'up'
                reason = f'S_pos={self.S_pos:.4f} > h_sigma={h_sigma:.4f}'
            # 下侧触发
            elif self.two_sided and self.S_neg < -h_sigma:
                detected = True
                direction = 'down'
                reason = f'S_neg={self.S_neg:.4f} < -h_sigma={-h_sigma:.4f}'

        # 记录历史
        self.S_pos_history.append(self.S_pos)
        self.S_neg_history.append(self.S_neg)
        self.detected_history.append(detected)

        result = {
            'detected': detected,
            'direction': direction,
            'S_pos': float(self.S_pos),
            'S_neg': float(self.S_neg),
            'n_observations': len(self.score_history),
        }
        if detected:
            result['reason'] = reason
            logger.warning(
                f"CUSUM 漂移检测: direction={direction}, "
                f"S_pos={self.S_pos:.4f}, S_neg={self.S_neg:.4f}, "
                f"x={x:.4f}, {reason}"
            )
            # 触发后自动重置累积和 (持续检测后续漂移)
            # 标准 CUSUM 实践: 触发后 S 重置为 0
            self.S_pos = 0.0
            self.S_neg = 0.0

        return result

    def reset(self) -> None:
        """重置累积和与历史 (重新开始监测)"""
        self.S_pos = 0.0
        self.S_neg = 0.0
        self.score_history = []
        self.S_pos_history = []
        self.S_neg_history = []
        self.detected_history = []
        logger.info("CUSUMDriftMonitor reset")

    def get_history(self) -> Dict[str, List]:
        """获取历史记录 (返回副本)

        Returns:
            {
                'S_pos': List[float],       # 上侧累积和时序
                'S_neg': List[float],       # 下侧累积和时序
                'detected': List[bool],     # 触发标记时序
                'scores': List[float],      # 原始观测值时序
            }
        """
        return {
            'S_pos': self.S_pos_history.copy(),
            'S_neg': self.S_neg_history.copy(),
            'detected': self.detected_history.copy(),
            'scores': self.score_history.copy(),
        }

    def get_stats(self) -> Dict:
        """获取当前状态统计"""
        return {
            'baseline_mean': self.baseline_mean,
            'baseline_std': self.baseline_std,
            'k': self.k,
            'h': self.h,
            'two_sided': self.two_sided,
            'current_S_pos': self.S_pos,
            'current_S_neg': self.S_neg,
            'n_observations': len(self.score_history),
            'n_detections': sum(self.detected_history),
        }
