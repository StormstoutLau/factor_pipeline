# -*- coding: utf-8 -*-
"""
因子健康度监测器 (Factor Health Monitor)

综合评估因子的拥挤度、效能、容量、衰减趋势和体制敏感性，
生成健康度综合报告和分级警报。

设计哲学（与项目保持一致）：
- 数据驱动自适应：健康评分由统计指标自动计算
- 前瞻偏差防护：所有滚动指标仅使用历史数据
- 中间状态追踪：健康度历史可追溯
- 多维度正交评估：五维指标独立计算，加权融合
"""

from typing import Dict, Any, List, Optional, Tuple, NamedTuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import numpy as np
import pandas as pd
from scipy import stats
import logging

from .fingerprint import FactorFingerprint, FactorType
from .classifier import ClassificationResult, AdaptiveFactorClassifier
from .fingerprint import FactorFingerprinter

logger = logging.getLogger(__name__)


class HealthAlertLevel(Enum):
    """健康度警报等级"""
    HEALTHY = "healthy"       # 健康: 所有指标正常
    WATCH = "watch"           # 关注: 1-2个指标接近阈值
    WARNING = "warning"       # 警告: 1-2个指标超阈值
    CRITICAL = "critical"     # 危急: 多个指标超阈值 + 衰减趋势


class HealthAlert(NamedTuple):
    """健康度单项警报"""
    metric_name: str              # 指标名称
    metric_value: float           # 当前值
    threshold: float              # 预警阈值
    direction: str                # 'above' 或 'below' (超阈值方向)
    level: HealthAlertLevel       # 警报等级
    category: str                 # 'crowding'/'efficacy'/'capacity'/'decay'/'regime'
    timestamp: datetime
    recommendation: str           # 建议措施

    def to_dict(self) -> Dict[str, Any]:
        return {
            'metric_name': self.metric_name,
            'metric_value': self.metric_value,
            'threshold': self.threshold,
            'direction': self.direction,
            'level': self.level.value,
            'category': self.category,
            'timestamp': self.timestamp.isoformat(),
            'recommendation': self.recommendation,
        }


@dataclass
class HealthConfig:
    """健康度监测配置"""
    # ---- 拥挤度 ----
    crowding_corr_threshold: float = 0.40        # 配对相关性集中度阈值
    crowding_hhi_threshold: float = 0.10         # 持仓集中度HHI阈值
    crowding_turnover_threshold: float = 0.80    # 年化换手率阈值
    crowding_reversal_threshold: float = -0.10   # 收益反转阈值

    # ---- 效能 ----
    efficacy_icir_threshold: float = 0.30        # IC IR阈值
    efficacy_ic_win_rate_threshold: float = 0.55 # IC胜率阈值
    efficacy_rolling_ic_window: int = 12         # 滚动IC窗口

    # ---- 容量 ----
    capacity_effective_n_threshold: int = 20     # 有效持仓数阈值
    capacity_top5_concentration_threshold: float = 0.40  # Top5集中度阈值

    # ---- 衰减 ----
    decay_mk_trend_pvalue: float = 0.05          # Mann-Kendall趋势p值
    decay_long_short_ratio_threshold: float = 0.50  # 多空收益衰减比
    decay_lookback_long: int = 36                # 长期回看窗口
    decay_lookback_short: int = 12               # 短期回看窗口

    # ---- 体制敏感性 ----
    regime_bull_bear_ratio_threshold: float = 2.0    # 牛熊IC比上限(>2.0 → 体制依赖)
    regime_bull_bear_ratio_lower: float = 0.5        # 牛熊IC比下限(<0.5 → 体制依赖)
    regime_vol_corr_threshold: float = 0.30          # 波动率IC相关性阈值

    # ---- 综合 ----
    health_score_weights: Dict[str, float] = field(default_factory=lambda: {
        'efficacy': 0.35,     # 效能权重最高: "有效"是因子存在的前提
        'crowding': 0.25,
        'capacity': 0.15,
        'decay': 0.15,
        'regime': 0.10,
    })
    rolling_window: int = 12               # 默认滚动窗口
    min_data_months: int = 12              # 最少数据月数


@dataclass
class FactorHealthReport:
    """因子健康度综合报告"""
    factor_name: str
    timestamp: datetime

    # 综合评分
    health_score: float                  # 0-100 综合健康分
    health_level: HealthAlertLevel

    # 分维度得分 (0-100, 越高越好)
    crowding_score: float                # 拥挤度得分 (高=不拥挤)
    efficacy_score: float                # 效能得分
    capacity_score: float                # 容量得分
    decay_score: float                   # 衰减得分 (高=衰减慢)
    regime_score: float                  # 体制稳健性得分

    # 详细指标字典
    crowding_metrics: Dict[str, float] = field(default_factory=dict)
    efficacy_metrics: Dict[str, float] = field(default_factory=dict)
    capacity_metrics: Dict[str, float] = field(default_factory=dict)
    decay_metrics: Dict[str, float] = field(default_factory=dict)
    regime_metrics: Dict[str, float] = field(default_factory=dict)

    # 警报
    alerts: List[HealthAlert] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            'factor_name': self.factor_name,
            'timestamp': self.timestamp.isoformat(),
            'health_score': self.health_score,
            'health_level': self.health_level.value,
            'crowding_score': self.crowding_score,
            'efficacy_score': self.efficacy_score,
            'capacity_score': self.capacity_score,
            'decay_score': self.decay_score,
            'regime_score': self.regime_score,
            'crowding_metrics': self.crowding_metrics,
            'efficacy_metrics': self.efficacy_metrics,
            'capacity_metrics': self.capacity_metrics,
            'decay_metrics': self.decay_metrics,
            'regime_metrics': self.regime_metrics,
            'alerts': [a.to_dict() for a in self.alerts],
        }


class FactorHealthMonitor:
    """
    因子健康度监测器

    综合评估因子的拥挤度、效能、容量、衰减趋势和体制敏感性，
    生成健康度综合报告和分级警报。

    设计哲学（与项目保持一致）：
    - 数据驱动自适应：健康评分由统计指标自动计算
    - 前瞻偏差防护：所有滚动指标仅使用历史数据
    - 中间状态追踪：健康度历史可追溯
    - 多维度正交评估：五维指标独立计算，加权融合

    Usage:
        monitor = FactorHealthMonitor()
        report = monitor.evaluate_health(
            factor_name='PB',
            factor_data=factor_df,       # T×N 因子面板
            returns_data=returns_df,     # T×N 收益面板 (可选)
            market_cap_data=mcap_df,     # T×N 市值面板 (可选)
        )
        print(f"健康分: {report.health_score:.0f}/100")
        print(f"等级: {report.health_level.value}")
    """

    def __init__(self, config: Optional[HealthConfig] = None):
        self.config = config or HealthConfig()
        self.fingerprinter = FactorFingerprinter()
        self.classifier = AdaptiveFactorClassifier()
        # 健康度历史: {因子名: [FactorHealthReport, ...]}
        self.health_history: Dict[str, List[FactorHealthReport]] = {}
        # 警报历史
        self.alert_history: List[HealthAlert] = []
        logger.info(f"FactorHealthMonitor initialized with config: {self.config}")

    # ==================== 公共 API ====================

    def evaluate_health(self,
                        factor_name: str,
                        factor_data: pd.DataFrame,
                        returns_data: Optional[pd.DataFrame] = None,
                        market_cap_data: Optional[pd.DataFrame] = None,
                        volume_data: Optional[pd.DataFrame] = None,
                        ) -> FactorHealthReport:
        """
        评估因子健康度

        五维评估：拥挤度 → 效能 → 容量 → 衰减 → 体制敏感性

        Parameters
        ----------
        factor_name : str
            因子名称
        factor_data : pd.DataFrame, shape (T, N)
            因子面板数据
        returns_data : pd.DataFrame, optional
            收益面板数据，用于IC计算和收益反转
        market_cap_data : pd.DataFrame, optional
            市值面板数据，用于容量计算
        volume_data : pd.DataFrame, optional
            成交量面板数据，用于流动性计算

        Returns
        -------
        FactorHealthReport
            健康度综合报告
        """
        # 检查数据充足性
        sufficient, msg = self._check_data_sufficiency(factor_data, returns_data)
        if not sufficient:
            logger.warning(msg)
            return FactorHealthReport(
                factor_name=factor_name,
                timestamp=datetime.now(),
                health_score=0.0,
                health_level=HealthAlertLevel.WATCH,
                crowding_score=0.0,
                efficacy_score=0.0,
                capacity_score=0.0,
                decay_score=0.0,
                regime_score=0.0,
            )

        # 1. 拥挤度
        crowding_score, crowding_metrics, crowding_alerts = self._evaluate_crowding(
            factor_data, returns_data
        )

        # 2. 效能
        efficacy_score, efficacy_metrics, efficacy_alerts = self._evaluate_efficacy(
            factor_data, returns_data
        )

        # 3. 容量
        capacity_score, capacity_metrics, capacity_alerts = self._evaluate_capacity(
            factor_data, market_cap_data
        )

        # 4. 衰减
        decay_score, decay_metrics, decay_alerts = self._evaluate_decay(
            factor_data, returns_data
        )

        # 5. 体制敏感性
        regime_score, regime_metrics, regime_alerts = self._evaluate_regime(
            factor_data, returns_data
        )

        # 综合评分
        dim_scores = {
            'crowding': crowding_score,
            'efficacy': efficacy_score,
            'capacity': capacity_score,
            'decay': decay_score,
            'regime': regime_score,
        }
        health_score, health_level = self._compute_health_score(
            dim_scores,
            crowding_alerts + efficacy_alerts + capacity_alerts + decay_alerts + regime_alerts
        )

        all_alerts = crowding_alerts + efficacy_alerts + capacity_alerts + decay_alerts + regime_alerts

        report = FactorHealthReport(
            factor_name=factor_name,
            timestamp=datetime.now(),
            health_score=health_score,
            health_level=health_level,
            crowding_score=crowding_score,
            efficacy_score=efficacy_score,
            capacity_score=capacity_score,
            decay_score=decay_score,
            regime_score=regime_score,
            crowding_metrics=crowding_metrics,
            efficacy_metrics=efficacy_metrics,
            capacity_metrics=capacity_metrics,
            decay_metrics=decay_metrics,
            regime_metrics=regime_metrics,
            alerts=all_alerts,
        )

        # 记录历史
        if factor_name not in self.health_history:
            self.health_history[factor_name] = []
        self.health_history[factor_name].append(report)
        self.alert_history.extend(all_alerts)

        logger.info(f"Health evaluated for {factor_name}: score={health_score:.1f}, level={health_level.value}")
        return report

    def evaluate_health_batch(self,
                              factor_dict: Dict[str, pd.DataFrame],
                              returns_data: Optional[pd.DataFrame] = None,
                              market_cap_data: Optional[pd.DataFrame] = None,
                              volume_data: Optional[pd.DataFrame] = None,
                              ) -> Dict[str, FactorHealthReport]:
        """
        批量评估多个因子的健康度

        Parameters
        ----------
        factor_dict : Dict[str, pd.DataFrame]
            因子名字到数据的映射
        returns_data : pd.DataFrame, optional
            收益面板数据
        market_cap_data : pd.DataFrame, optional
            市值面板数据
        volume_data : pd.DataFrame, optional
            成交量面板数据

        Returns
        -------
        Dict[str, FactorHealthReport]
            因子名字到健康度报告的映射
        """
        results = {}
        for name, data in factor_dict.items():
            logger.info(f"Evaluating health for {name}...")
            results[name] = self.evaluate_health(
                name, data, returns_data, market_cap_data, volume_data
            )
        return results

    def get_health_summary(self,
                           factor_name: Optional[str] = None
                           ) -> pd.DataFrame:
        """
        获取健康度摘要表

        Parameters
        ----------
        factor_name : str, optional
            指定因子名，None则返回所有因子的摘要

        Returns
        -------
        pd.DataFrame
            健康度摘要表
        """
        reports = []
        if factor_name:
            history = self.health_history.get(factor_name, [])
            reports = history[-1:] if history else []
        else:
            for name, history in self.health_history.items():
                if history:
                    reports.append(history[-1])

        if not reports:
            return pd.DataFrame()

        data = [r.to_dict() for r in reports]
        return pd.DataFrame(data)

    def get_health_trend(self,
                         factor_name: str,
                         lookback: int = 12
                         ) -> pd.DataFrame:
        """
        获取健康度趋势（最近N期）

        Parameters
        ----------
        factor_name : str
            因子名称
        lookback : int
            回看期数

        Returns
        -------
        pd.DataFrame
            健康度趋势表
        """
        history = self.health_history.get(factor_name, [])
        if not history:
            return pd.DataFrame()

        recent = history[-lookback:]
        data = [r.to_dict() for r in recent]
        return pd.DataFrame(data)

    # ==================== 综合评分 ====================

    def _compute_health_score(self,
                              dim_scores: Dict[str, float],
                              alerts: List[HealthAlert] = None,
                              ) -> Tuple[float, HealthAlertLevel]:
        """
        加权合成健康分 + 等级判定

        Parameters
        ----------
        dim_scores : Dict[str, float]
            五维得分 {crowding, efficacy, capacity, decay, regime}
        alerts : List[HealthAlert], optional
            警报列表

        Returns
        -------
        Tuple[float, HealthAlertLevel]
            (健康分 [0-100], 健康等级)
        """
        if alerts is None:
            alerts = []

        weights = self.config.health_score_weights
        score = sum(dim_scores.get(k, 0.0) * w for k, w in weights.items())
        score = float(np.clip(score, 0.0, 100.0))
        level = self._determine_health_level(score, alerts)
        return score, level

    def _determine_health_level(self,
                                score: float,
                                alerts: List[HealthAlert],
                                ) -> HealthAlertLevel:
        """
        判定健康等级

        CRITICAL: 多个维度超阈值 (>=3个维度) 或 存在衰减趋势警报
        WARNING:  1-2个维度超阈值
        WATCH:    接近阈值但未超标 (得分 < 60)
        HEALTHY:  所有指标正常 (得分 >= 60 且无警报)

        Parameters
        ----------
        score : float
            综合健康分
        alerts : List[HealthAlert]
            警报列表

        Returns
        -------
        HealthAlertLevel
        """
        warning_alerts = [a for a in alerts if a.level in (HealthAlertLevel.WARNING, HealthAlertLevel.CRITICAL)]
        n_warning_dims = len(set(a.category for a in warning_alerts))

        if n_warning_dims >= 3:
            return HealthAlertLevel.CRITICAL
        elif n_warning_dims >= 1:
            return HealthAlertLevel.WARNING
        elif score < 60.0:
            return HealthAlertLevel.WATCH
        else:
            return HealthAlertLevel.HEALTHY

    def _normalize_score(self,
                         value: float,
                         best: float,
                         worst: float,
                         ) -> float:
        """
        将指标值映射到 [0, 100] 得分

        线性映射: value 越接近 best, 得分越高

        Parameters
        ----------
        value : float
            当前值
        best : float
            最优值 (得100分)
        worst : float
            最差值 (得0分)

        Returns
        -------
        float
            [0, 100] 得分
        """
        if np.isnan(value):
            return 50.0  # NaN → 中性
        if abs(best - worst) < 1e-10:
            return 50.0

        normalized = (value - worst) / (best - worst)
        return float(np.clip(normalized * 100.0, 0.0, 100.0) + 0.0)  # +0.0 消除 -0.0

    # ==================== 拥挤度 (Crowding) ====================

    def _evaluate_crowding(self,
                           factor_data: pd.DataFrame,
                           returns_data: Optional[pd.DataFrame] = None,
                           ) -> Tuple[float, Dict[str, float], List[HealthAlert]]:
        """
        评估因子拥挤度

        指标:
        1. 配对相关性集中度 (pairwise_corr_concentration)
        2. 持仓集中度HHI (position_hhi)
        3. 因子换手率 (turnover)
        4. 收益反转风险 (return_reversal, 需要returns_data)

        Returns
        -------
        Tuple[float, Dict[str, float], List[HealthAlert]]
            (拥挤度得分 [0-100], 指标字典, 警报列表)
        """
        metrics = {}
        alerts = []

        # 1. 配对相关性集中度
        corr_conc = self._compute_pairwise_corr_concentration(factor_data)
        metrics['pairwise_corr_concentration'] = corr_conc

        if not np.isnan(corr_conc) and corr_conc > self.config.crowding_corr_threshold:
            alerts.append(self._create_alert(
                'pairwise_corr_concentration', corr_conc,
                self.config.crowding_corr_threshold, 'above',
                HealthAlertLevel.WARNING, 'crowding',
                f'配对相关性 {corr_conc:.3f} 超过阈值 {self.config.crowding_corr_threshold}，因子可能拥挤'
            ))

        # 2. 持仓集中度
        hhi = self._compute_position_hhi(factor_data)
        metrics['position_hhi'] = hhi

        if not np.isnan(hhi) and hhi > self.config.crowding_hhi_threshold:
            alerts.append(self._create_alert(
                'position_hhi', hhi,
                self.config.crowding_hhi_threshold, 'above',
                HealthAlertLevel.WARNING, 'crowding',
                f'持仓集中度HHI {hhi:.4f} 超过阈值 {self.config.crowding_hhi_threshold}，持仓过于集中'
            ))

        # 3. 换手率
        turnover = self._compute_turnover(factor_data)
        metrics['turnover'] = turnover

        if not np.isnan(turnover) and turnover > self.config.crowding_turnover_threshold:
            alerts.append(self._create_alert(
                'turnover', turnover,
                self.config.crowding_turnover_threshold, 'above',
                HealthAlertLevel.WARNING, 'crowding',
                f'年化换手率 {turnover:.1%} 超过阈值 {self.config.crowding_turnover_threshold:.0%}'
            ))

        # 4. 收益反转（需要收益数据）
        if returns_data is not None:
            reversal = self._compute_return_reversal(factor_data, returns_data)
            metrics['return_reversal'] = reversal

            if not np.isnan(reversal) and reversal < self.config.crowding_reversal_threshold:
                alerts.append(self._create_alert(
                    'return_reversal', reversal,
                    self.config.crowding_reversal_threshold, 'below',
                    HealthAlertLevel.WARNING, 'crowding',
                    f'收益反转 {reversal:.3f} 低于阈值 {self.config.crowding_reversal_threshold}，过度拥挤迹象'
                ))

        # 综合得分
        score = self._crowding_score(metrics)
        return score, metrics, alerts

    def _crowding_score(self, metrics: Dict[str, float]) -> float:
        """拥挤度综合得分: 各指标映射到 [0,100] 后等权平均"""
        scores = []
        if 'pairwise_corr_concentration' in metrics and not np.isnan(metrics['pairwise_corr_concentration']):
            scores.append(self._normalize_score(metrics['pairwise_corr_concentration'], 0.0, 0.60))
        if 'return_reversal' in metrics and not np.isnan(metrics['return_reversal']):
            scores.append(self._normalize_score(metrics['return_reversal'], 0.10, -0.20))
        if not scores:
            return 50.0
        return float(np.mean(scores))

    def _compute_pairwise_corr_concentration(self,
                                             factor_data: pd.DataFrame,
                                             top_quantile: float = 0.2
                                             ) -> float:
        """
        配对相关性集中度: 多头组合内股票的平均两两相关性

        使用最近一期截面数据，计算top_quantile分位股票的相关性矩阵均值。

        Parameters
        ----------
        factor_data : pd.DataFrame
            因子面板数据
        top_quantile : float
            多头分位比例

        Returns
        -------
        float
            平均配对相关性
        """
        if factor_data.shape[0] < self.config.min_data_months:
            return np.nan

        # 使用最近一期
        latest = factor_data.iloc[-1].dropna()
        if len(latest) < 10:
            return np.nan

        # 取top_quantile分位的股票
        threshold = latest.quantile(1 - top_quantile)
        top_stocks = latest[latest >= threshold].index

        if len(top_stocks) < 5:
            return np.nan

        # 计算这些股票在历史数据上的相关性矩阵
        n_stocks = min(len(top_stocks), 30)  # 限制最大股票数避免计算爆炸
        top_stocks = top_stocks[:n_stocks]
        top_data = factor_data[top_stocks].dropna(axis=1, how='all')

        if top_data.shape[1] < 5:
            return np.nan

        corr_matrix = top_data.corr()
        # 取下三角（不含对角线）
        mask = np.tril(np.ones_like(corr_matrix, dtype=bool), k=-1)
        pairwise_corrs = corr_matrix.values[mask]
        pairwise_corrs = pairwise_corrs[~np.isnan(pairwise_corrs)]

        if len(pairwise_corrs) == 0:
            return np.nan

        return float(np.mean(pairwise_corrs))

    def _compute_position_hhi(self,
                              factor_data: pd.DataFrame,
                              ) -> float:
        """
        持仓集中度: 等权多头的 Herfindahl-Hirschman Index

        HHI = Σ(weight_i²), 在等权情况下 = 1/N

        Parameters
        ----------
        factor_data : pd.DataFrame
            因子面板数据

        Returns
        -------
        float
            HHI值
        """
        if factor_data.shape[0] < self.config.min_data_months:
            return np.nan

        latest = factor_data.iloc[-1].dropna()
        n_valid = len(latest)

        if n_valid < 5:
            return np.nan

        # 等权HHI = 1/N
        return 1.0 / n_valid

    def _compute_turnover(self,
                          factor_data: pd.DataFrame,
                          ) -> float:
        """
        因子换手率: mean(|rank_t - rank_{t-1}|) / N

        计算相邻两期截面排序变化的平均幅度。

        Parameters
        ----------
        factor_data : pd.DataFrame
            因子面板数据

        Returns
        -------
        float
            换手率 [0, 1]
        """
        if factor_data.shape[0] < 2:
            return np.nan

        turnovers = []
        for t in range(1, len(factor_data)):
            prev = factor_data.iloc[t - 1].dropna()
            curr = factor_data.iloc[t].dropna()

            common = prev.index.intersection(curr.index)
            if len(common) < self.config.capacity_effective_n_threshold:
                continue

            prev_rank = prev[common].rank(pct=True)
            curr_rank = curr[common].rank(pct=True)

            # 排序变化
            rank_change = (prev_rank - curr_rank).abs().mean()
            turnovers.append(rank_change)

        if len(turnovers) < 2:
            return np.nan

        return float(np.mean(turnovers))

    def _compute_return_reversal(self,
                                 factor_data: pd.DataFrame,
                                 returns_data: pd.DataFrame,
                                 top_quantile: float = 0.2
                                 ) -> float:
        """
        收益反转: 因子多头组合收益的1阶自相关

        负自相关意味着过度拥挤后的均值回归。

        Parameters
        ----------
        factor_data : pd.DataFrame
            因子面板数据
        returns_data : pd.DataFrame
            收益面板数据
        top_quantile : float
            多头分位比例

        Returns
        -------
        float
            多头组合收益的1阶自相关
        """
        if factor_data.shape[0] < self.config.min_data_months:
            return np.nan

        # 计算每期多头组合的等权收益
        long_returns = []
        for t in range(len(factor_data) - 1):
            factor_t = factor_data.iloc[t].dropna()
            ret_t1 = returns_data.iloc[t + 1].dropna()

            common = factor_t.index.intersection(ret_t1.index)
            if len(common) < 10:
                continue

            threshold = factor_t[common].quantile(1 - top_quantile)
            long_stocks = factor_t[common][factor_t[common] >= threshold].index

            if len(long_stocks) < 5:
                continue

            long_ret = ret_t1[long_stocks].mean()
            long_returns.append(long_ret)

        if len(long_returns) < 5:
            return np.nan

        long_series = pd.Series(long_returns)
        return float(long_series.autocorr(1))

    # ==================== 效能 (Efficacy) ====================

    def _evaluate_efficacy(self,
                           factor_data: pd.DataFrame,
                           returns_data: Optional[pd.DataFrame] = None,
                           ) -> Tuple[float, Dict[str, float], List[HealthAlert]]:
        """
        评估因子效能

        指标:
        1. IC信息比 (ic_ir)
        2. 滚动IC均值 (rolling_ic_mean)
        3. IC胜率 (ic_win_rate)
        4. IC自相关 (ic_autocorr)

        Returns
        -------
        Tuple[float, Dict[str, float], List[HealthAlert]]
            (效能得分 [0-100], 指标字典, 警报列表)
        """
        metrics = {}
        alerts = []

        if returns_data is None:
            return 50.0, metrics, alerts

        ic_series = self._compute_ic_series(factor_data, returns_data)
        if len(ic_series) < 3:
            return 50.0, metrics, alerts

        # 1. IC IR
        ic_ir = self._compute_ic_ir(ic_series)
        metrics['ic_ir'] = ic_ir

        if not np.isnan(ic_ir) and ic_ir < self.config.efficacy_icir_threshold:
            alerts.append(self._create_alert(
                'ic_ir', ic_ir,
                self.config.efficacy_icir_threshold, 'below',
                HealthAlertLevel.WARNING, 'efficacy',
                f'IC IR {ic_ir:.3f} 低于阈值 {self.config.efficacy_icir_threshold}，因子预测能力不足'
            ))

        # 2. 滚动IC均值
        rolling_ic_mean = self._compute_rolling_ic_mean(ic_series)
        metrics['rolling_ic_mean'] = rolling_ic_mean

        # 3. IC胜率
        ic_win_rate = self._compute_ic_win_rate(ic_series)
        metrics['ic_win_rate'] = ic_win_rate

        if not np.isnan(ic_win_rate) and ic_win_rate < self.config.efficacy_ic_win_rate_threshold:
            alerts.append(self._create_alert(
                'ic_win_rate', ic_win_rate,
                self.config.efficacy_ic_win_rate_threshold, 'below',
                HealthAlertLevel.WARNING, 'efficacy',
                f'IC胜率 {ic_win_rate:.1%} 低于阈值 {self.config.efficacy_ic_win_rate_threshold:.0%}'
            ))

        # 4. IC自相关
        ic_autocorr = self._compute_ic_autocorr(ic_series)
        metrics['ic_autocorr'] = ic_autocorr

        # 综合得分
        score = self._efficacy_score(metrics)
        return score, metrics, alerts

    def _efficacy_score(self, metrics: Dict[str, float]) -> float:
        """效能综合得分"""
        scores = []
        if 'ic_ir' in metrics and not np.isnan(metrics['ic_ir']):
            scores.append(self._normalize_score(metrics['ic_ir'], 1.0, 0.0))
        if 'ic_win_rate' in metrics and not np.isnan(metrics['ic_win_rate']):
            scores.append(self._normalize_score(metrics['ic_win_rate'], 0.70, 0.45))
        if not scores:
            return 50.0
        return float(np.mean(scores))

    def _compute_ic_series(self,
                           factor_data: pd.DataFrame,
                           returns_data: pd.DataFrame,
                           ) -> np.ndarray:
        """
        计算 Rank IC 序列

        每期截面因子值与下期收益的Spearman秩相关系数。

        Parameters
        ----------
        factor_data : pd.DataFrame, shape (T, N)
            因子面板数据
        returns_data : pd.DataFrame, shape (T, N)
            收益面板数据

        Returns
        -------
        np.ndarray, shape (T-1,)
            Rank IC 序列
        """
        ic_values = []
        for t in range(len(factor_data) - 1):
            rank_ic = self._compute_rank_ic(
                factor_data.iloc[t],
                returns_data.iloc[t + 1]
            )
            if not np.isnan(rank_ic):
                ic_values.append(rank_ic)

        return np.array(ic_values)

    def _compute_rank_ic(self,
                         factor_t: pd.Series,
                         returns_t1: pd.Series,
                         ) -> float:
        """
        单期 Rank IC 计算

        Parameters
        ----------
        factor_t : pd.Series
            当期因子值
        returns_t1 : pd.Series
            下期收益

        Returns
        -------
        float
            Spearman秩相关系数
        """
        factor_clean = factor_t.dropna()
        ret_clean = returns_t1.dropna()

        common = factor_clean.index.intersection(ret_clean.index)
        if len(common) < 10:
            return np.nan

        factor_rank = factor_clean[common].rank()
        ret_rank = ret_clean[common].rank()

        if factor_rank.nunique() <= 1 or ret_rank.nunique() <= 1:
            return np.nan

        corr, _ = stats.spearmanr(factor_rank, ret_rank)
        return float(corr) if not np.isnan(corr) else np.nan

    def _compute_ic_ir(self, ic_series: np.ndarray) -> float:
        """
        IC信息比

        IC IR = mean(IC) / std(IC)

        Parameters
        ----------
        ic_series : np.ndarray
            IC序列

        Returns
        -------
        float
            IC IR
        """
        ic_clean = ic_series[~np.isnan(ic_series)]
        if len(ic_clean) < 3:
            return np.nan

        mu = np.mean(ic_clean)
        sigma = np.std(ic_clean, ddof=1)

        if sigma < 1e-10:
            return np.nan

        return float(mu / sigma)

    def _compute_rolling_ic_mean(self, ic_series: np.ndarray) -> float:
        """
        滚动IC均值

        使用最近rolling_window期的IC均值。

        Parameters
        ----------
        ic_series : np.ndarray
            IC序列

        Returns
        -------
        float
            滚动IC均值
        """
        ic_clean = ic_series[~np.isnan(ic_series)]
        window = min(self.config.efficacy_rolling_ic_window, len(ic_clean))
        if window < 3:
            return np.nan
        return float(np.mean(ic_clean[-window:]))

    def _compute_ic_win_rate(self, ic_series: np.ndarray) -> float:
        """
        IC胜率

        P(IC > 0) = 正IC占比

        Parameters
        ----------
        ic_series : np.ndarray
            IC序列

        Returns
        -------
        float
            IC胜率 [0, 1]
        """
        ic_clean = ic_series[~np.isnan(ic_series)]
        if len(ic_clean) < 3:
            return np.nan
        return float(np.mean(ic_clean > 0))

    def _compute_ic_autocorr(self, ic_series: np.ndarray) -> float:
        """
        IC自相关

        corr(IC_t, IC_{t-1})

        Parameters
        ----------
        ic_series : np.ndarray
            IC序列

        Returns
        -------
        float
            IC 1阶自相关
        """
        ic_clean = ic_series[~np.isnan(ic_series)]
        if len(ic_clean) < 5:
            return np.nan

        ic_pd = pd.Series(ic_clean)
        return float(ic_pd.autocorr(1))

    # ==================== 容量 (Capacity) ====================

    def _evaluate_capacity(self,
                           factor_data: pd.DataFrame,
                           market_cap_data: Optional[pd.DataFrame] = None,
                           ) -> Tuple[float, Dict[str, float], List[HealthAlert]]:
        """
        评估因子容量

        指标:
        1. 有效持仓数 (effective_n)
        2. Top5集中度 (top5_concentration)
        3. 市值加权集中度 (cap_weighted_concentration, 需要market_cap_data)

        Returns
        -------
        Tuple[float, Dict[str, float], List[HealthAlert]]
            (容量得分 [0-100], 指标字典, 警报列表)
        """
        metrics = {}
        alerts = []

        # 1. 有效持仓数
        effective_n = self._compute_effective_n(factor_data)
        metrics['effective_n'] = effective_n

        if not np.isnan(effective_n) and effective_n < self.config.capacity_effective_n_threshold:
            alerts.append(self._create_alert(
                'effective_n', effective_n,
                float(self.config.capacity_effective_n_threshold), 'below',
                HealthAlertLevel.WARNING, 'capacity',
                f'有效持仓数 {effective_n:.0f} 低于阈值 {self.config.capacity_effective_n_threshold}'
            ))

        # 2. Top5集中度
        top5_conc = self._compute_top5_concentration(factor_data)
        metrics['top5_concentration'] = top5_conc

        if not np.isnan(top5_conc) and top5_conc > self.config.capacity_top5_concentration_threshold:
            alerts.append(self._create_alert(
                'top5_concentration', top5_conc,
                self.config.capacity_top5_concentration_threshold, 'above',
                HealthAlertLevel.WARNING, 'capacity',
                f'Top5集中度 {top5_conc:.1%} 超过阈值 {self.config.capacity_top5_concentration_threshold:.0%}'
            ))

        # 3. 市值加权集中度
        if market_cap_data is not None:
            cap_conc = self._compute_cap_weighted_concentration(factor_data, market_cap_data)
            metrics['cap_weighted_concentration'] = cap_conc

        # 综合得分
        score = self._capacity_score(metrics)
        return score, metrics, alerts

    def _capacity_score(self, metrics: Dict[str, float]) -> float:
        """容量综合得分"""
        scores = []
        if 'effective_n' in metrics and not np.isnan(metrics['effective_n']):
            scores.append(self._normalize_score(metrics['effective_n'], 100.0, 10.0))
        if 'top5_concentration' in metrics and not np.isnan(metrics['top5_concentration']):
            scores.append(self._normalize_score(metrics['top5_concentration'], 0.05, 0.50))
        if not scores:
            return 50.0
        return float(np.mean(scores))

    def _compute_effective_n(self,
                             factor_data: pd.DataFrame,
                             ) -> float:
        """
        有效持仓数: 1 / Σ(weight_i²)

        在等权情况下 EN = N。

        Parameters
        ----------
        factor_data : pd.DataFrame
            因子面板数据

        Returns
        -------
        float
            有效持仓数
        """
        if factor_data.shape[0] < self.config.min_data_months:
            return np.nan

        latest = factor_data.iloc[-1].dropna()
        n_valid = len(latest)

        if n_valid < 5:
            return np.nan

        # 等权 HHI = 1/N, EN = 1/HHI = N
        return float(n_valid)

    def _compute_top5_concentration(self,
                                    factor_data: pd.DataFrame,
                                    ) -> float:
        """
        Top5集中度: 前5大持仓占比

        在等权下 = 5/N。

        Parameters
        ----------
        factor_data : pd.DataFrame
            因子面板数据

        Returns
        -------
        float
            Top5集中度 [0, 1]
        """
        if factor_data.shape[0] < self.config.min_data_months:
            return np.nan

        latest = factor_data.iloc[-1].dropna()
        n_valid = len(latest)

        if n_valid < 5:
            return np.nan

        return 5.0 / n_valid

    def _compute_cap_weighted_concentration(self,
                                            factor_data: pd.DataFrame,
                                            market_cap_data: pd.DataFrame,
                                            ) -> float:
        """
        市值加权集中度

        在因子多头组合中，按市值加权后的HHI。

        Parameters
        ----------
        factor_data : pd.DataFrame
            因子面板数据
        market_cap_data : pd.DataFrame
            市值面板数据

        Returns
        -------
        float
            市值加权HHI
        """
        if factor_data.shape[0] < self.config.min_data_months:
            return np.nan

        latest_factor = factor_data.iloc[-1].dropna()
        latest_mcap = market_cap_data.iloc[-1].dropna()

        common = latest_factor.index.intersection(latest_mcap.index)
        if len(common) < 10:
            return np.nan

        mcap = latest_mcap[common]
        weights = mcap / mcap.sum()

        return float(np.sum(weights ** 2))

    # ==================== 衰减 (Decay) ====================

    def _evaluate_decay(self,
                        factor_data: pd.DataFrame,
                        returns_data: Optional[pd.DataFrame] = None,
                        ) -> Tuple[float, Dict[str, float], List[HealthAlert]]:
        """
        评估因子衰减

        指标:
        1. Mann-Kendall IC趋势检验 (mk_trend_pvalue)
        2. 多空收益衰减比 (long_short_decay_ratio)
        3. 滚动IC斜率 (rolling_ic_slope)

        Returns
        -------
        Tuple[float, Dict[str, float], List[HealthAlert]]
            (衰减得分 [0-100], 指标字典, 警报列表)
        """
        metrics = {}
        alerts = []

        if returns_data is None:
            return 50.0, metrics, alerts

        ic_series = self._compute_ic_series(factor_data, returns_data)
        if len(ic_series) < 6:
            return 50.0, metrics, alerts

        # 1. Mann-Kendall趋势检验
        tau, p_value = self._compute_mann_kendall(ic_series)
        metrics['mk_tau'] = tau
        metrics['mk_trend_pvalue'] = p_value

        if not np.isnan(p_value) and p_value < self.config.decay_mk_trend_pvalue and tau < 0:
            alerts.append(self._create_alert(
                'mk_trend_pvalue', p_value,
                self.config.decay_mk_trend_pvalue, 'below',
                HealthAlertLevel.WARNING, 'decay',
                f'IC呈显著下降趋势 (Mann-Kendall tau={tau:.3f}, p={p_value:.4f})'
            ))

        # 2. 多空收益衰减比
        decay_ratio = self._compute_long_short_decay(factor_data, returns_data)
        metrics['long_short_decay_ratio'] = decay_ratio

        if not np.isnan(decay_ratio) and decay_ratio < self.config.decay_long_short_ratio_threshold:
            alerts.append(self._create_alert(
                'long_short_decay_ratio', decay_ratio,
                self.config.decay_long_short_ratio_threshold, 'below',
                HealthAlertLevel.WARNING, 'decay',
                f'多空收益衰减比 {decay_ratio:.2f} 低于阈值 {self.config.decay_long_short_ratio_threshold}'
            ))

        # 3. 滚动IC斜率
        ic_slope = self._compute_rolling_ic_slope(ic_series)
        metrics['rolling_ic_slope'] = ic_slope

        if not np.isnan(ic_slope) and ic_slope < -0.01:
            alerts.append(self._create_alert(
                'rolling_ic_slope', ic_slope,
                -0.01, 'below',
                HealthAlertLevel.WATCH, 'decay',
                f'滚动IC斜率 {ic_slope:.4f}/月，因子正在衰减'
            ))

        # 综合得分
        score = self._decay_score(metrics)
        return score, metrics, alerts

    def _decay_score(self, metrics: Dict[str, float]) -> float:
        """衰减综合得分"""
        scores = []
        if 'mk_trend_pvalue' in metrics and not np.isnan(metrics['mk_trend_pvalue']):
            # p值越大越好(越没有显著下降趋势)
            scores.append(self._normalize_score(metrics['mk_trend_pvalue'], 1.0, 0.0))
        if 'long_short_decay_ratio' in metrics and not np.isnan(metrics['long_short_decay_ratio']):
            scores.append(self._normalize_score(metrics['long_short_decay_ratio'], 1.5, 0.3))
        if not scores:
            return 50.0
        return float(np.mean(scores))

    def _compute_mann_kendall(self, series: np.ndarray) -> Tuple[float, float]:
        """
        Mann-Kendall 趋势检验

        非参数检验，检测序列是否存在单调趋势。

        Parameters
        ----------
        series : np.ndarray
            待检验序列

        Returns
        -------
        Tuple[float, float]
            (tau统计量, p值)
        """
        series_clean = series[~np.isnan(series)]
        n = len(series_clean)

        if n < 10:
            return np.nan, np.nan

        # 计算 S 统计量
        s = 0
        for i in range(n - 1):
            for j in range(i + 1, n):
                s += np.sign(series_clean[j] - series_clean[i])

        # 计算 tau
        tau = s / (n * (n - 1) / 2)

        # 计算方差 (考虑 ties)
        # 简化版: 假设无ties
        var_s = n * (n - 1) * (2 * n + 5) / 18

        if var_s > 0:
            z = (s - np.sign(s)) / np.sqrt(var_s)
        else:
            z = 0.0

        # 双侧p值
        p_value = 2 * (1 - stats.norm.cdf(abs(z)))

        return float(tau), float(p_value)

    def _compute_long_short_decay(self,
                                  factor_data: pd.DataFrame,
                                  returns_data: pd.DataFrame,
                                  ) -> float:
        """
        多空收益衰减比

        ret_short(最近N期) / ret_long(更长N期)
        < 1 说明近期收益在衰减。

        Parameters
        ----------
        factor_data : pd.DataFrame
            因子面板数据
        returns_data : pd.DataFrame
            收益面板数据

        Returns
        -------
        float
            衰减比
        """
        # 计算每期多空收益
        long_short_rets = []
        for t in range(len(factor_data) - 1):
            factor_t = factor_data.iloc[t].dropna()
            ret_t1 = returns_data.iloc[t + 1].dropna()

            common = factor_t.index.intersection(ret_t1.index)
            if len(common) < 20:
                continue

            top_n = max(5, len(common) // 5)
            sorted_idx = factor_t[common].sort_values()
            short_stocks = sorted_idx.index[:top_n]
            long_stocks = sorted_idx.index[-top_n:]

            ls_ret = ret_t1[long_stocks].mean() - ret_t1[short_stocks].mean()
            long_short_rets.append(ls_ret)

        if len(long_short_rets) < self.config.decay_lookback_long:
            return np.nan

        short_window = min(self.config.decay_lookback_short, len(long_short_rets))
        long_window = min(self.config.decay_lookback_long, len(long_short_rets))

        ret_short = np.mean(long_short_rets[-short_window:])
        ret_long = np.mean(long_short_rets[-long_window:])

        if abs(ret_long) < 1e-10:
            return float('inf') if ret_short > 0 else float('-inf')

        return float(ret_short / ret_long)

    def _compute_rolling_ic_slope(self,
                                  ic_series: np.ndarray,
                                  ) -> float:
        """
        滚动IC斜率

        对最近N期IC做线性回归，返回斜率。

        Parameters
        ----------
        ic_series : np.ndarray
            IC序列

        Returns
        -------
        float
            IC斜率 (每期变化)
        """
        ic_clean = ic_series[~np.isnan(ic_series)]
        window = min(self.config.rolling_window, len(ic_clean))

        if window < 5:
            return np.nan

        recent = ic_clean[-window:]
        x = np.arange(len(recent))
        y = recent

        # 线性回归
        x_mean = np.mean(x)
        y_mean = np.mean(y)
        slope = np.sum((x - x_mean) * (y - y_mean)) / np.sum((x - x_mean) ** 2)

        return float(slope)

    # ==================== 体制敏感性 (Regime Sensitivity) ====================

    def _evaluate_regime(self,
                         factor_data: pd.DataFrame,
                         returns_data: Optional[pd.DataFrame] = None,
                         ) -> Tuple[float, Dict[str, float], List[HealthAlert]]:
        """
        评估体制敏感性

        指标:
        1. 牛熊IC比 (bull_bear_ic_ratio)
        2. 波动率条件IC (vol_conditional_ic_corr)

        Returns
        -------
        Tuple[float, Dict[str, float], List[HealthAlert]]
            (体制稳健性得分 [0-100], 指标字典, 警报列表)
        """
        metrics = {}
        alerts = []

        if returns_data is None:
            return 50.0, metrics, alerts

        ic_series = self._compute_ic_series(factor_data, returns_data)
        if len(ic_series) < 12:
            return 50.0, metrics, alerts

        # 市场收益序列
        market_returns = returns_data.mean(axis=1).values

        # 1. 牛熊IC比
        bull_bear_ratio = self._compute_bull_bear_ic_ratio(ic_series, market_returns)
        metrics['bull_bear_ic_ratio'] = bull_bear_ratio

        if not np.isnan(bull_bear_ratio):
            if bull_bear_ratio > self.config.regime_bull_bear_ratio_threshold:
                alerts.append(self._create_alert(
                    'bull_bear_ic_ratio', bull_bear_ratio,
                    self.config.regime_bull_bear_ratio_threshold, 'above',
                    HealthAlertLevel.WARNING, 'regime',
                    f'牛熊IC比 {bull_bear_ratio:.2f} > {self.config.regime_bull_bear_ratio_threshold}，因子在牛市中显著更有效'
                ))
            elif bull_bear_ratio < self.config.regime_bull_bear_ratio_lower:
                alerts.append(self._create_alert(
                    'bull_bear_ic_ratio', bull_bear_ratio,
                    self.config.regime_bull_bear_ratio_lower, 'below',
                    HealthAlertLevel.WARNING, 'regime',
                    f'牛熊IC比 {bull_bear_ratio:.2f} < {self.config.regime_bull_bear_ratio_lower}，因子在熊市中显著更有效'
                ))

        # 2. 波动率条件IC
        vol_corr = self._compute_vol_conditional_ic_corr(ic_series, returns_data)
        metrics['vol_conditional_ic_corr'] = vol_corr

        if not np.isnan(vol_corr) and abs(vol_corr) > self.config.regime_vol_corr_threshold:
            alerts.append(self._create_alert(
                'vol_conditional_ic_corr', vol_corr,
                self.config.regime_vol_corr_threshold, 'above',
                HealthAlertLevel.WATCH, 'regime',
                f'波动率条件IC相关性 {vol_corr:.3f}，因子对市场波动敏感'
            ))

        # 综合得分
        score = self._regime_score(metrics)
        return score, metrics, alerts

    def _regime_score(self, metrics: Dict[str, float]) -> float:
        """体制稳健性综合得分"""
        scores = []
        if 'bull_bear_ic_ratio' in metrics and not np.isnan(metrics['bull_bear_ic_ratio']):
            # 越接近1.0越好（牛熊一致）
            deviation = abs(metrics['bull_bear_ic_ratio'] - 1.0)
            scores.append(self._normalize_score(deviation, 0.0, 2.0))
        if 'vol_conditional_ic_corr' in metrics and not np.isnan(metrics['vol_conditional_ic_corr']):
            # 越接近0越好（不对波动率敏感）
            scores.append(self._normalize_score(abs(metrics['vol_conditional_ic_corr']), 0.0, 0.50))
        if not scores:
            return 50.0
        return float(np.mean(scores))

    def _split_bull_bear(self,
                         returns_data: pd.DataFrame,
                         ) -> Tuple[np.ndarray, np.ndarray]:
        """
        基于市场收益正负划分牛熊期

        Parameters
        ----------
        returns_data : pd.DataFrame
            收益面板数据

        Returns
        -------
        Tuple[np.ndarray, np.ndarray]
            (牛市期索引, 熊市期索引)
        """
        market_ret = returns_data.mean(axis=1)
        bull_idx = np.where(market_ret.values >= 0)[0]
        bear_idx = np.where(market_ret.values < 0)[0]
        return bull_idx, bear_idx

    def _compute_bull_bear_ic_ratio(self,
                                    ic_series: np.ndarray,
                                    market_returns: np.ndarray,
                                    ) -> float:
        """
        牛熊IC比

        ratio = mean(IC|bull) / mean(IC|bear)

        Parameters
        ----------
        ic_series : np.ndarray, shape (T-1,)
            IC序列
        market_returns : np.ndarray, shape (T,)
            市场收益序列

        Returns
        -------
        float
            牛熊IC比
        """
        # IC对应的是 t→t+1 的预测，市场收益用 t 期
        n = len(ic_series)
        bull_slice = market_returns[:n] >= 0
        bear_slice = market_returns[:n] < 0

        ic_bull = ic_series[bull_slice]
        ic_bear = ic_series[bear_slice]

        if len(ic_bull) < 3 or len(ic_bear) < 3:
            return np.nan

        mean_bull = np.mean(ic_bull)
        mean_bear = np.mean(ic_bear)

        if abs(mean_bear) < 1e-10:
            return np.nan if mean_bull < 0 else float('inf')

        return float(mean_bull / mean_bear)

    def _compute_vol_conditional_ic_corr(self,
                                         ic_series: np.ndarray,
                                         returns_data: pd.DataFrame,
                                         vol_window: int = 3
                                         ) -> float:
        """
        波动率条件IC

        corr(IC_t, VIX_proxy_t), VIX_proxy = 市场收益的滚动标准差

        Parameters
        ----------
        ic_series : np.ndarray, shape (T-1,)
            IC序列
        returns_data : pd.DataFrame
            收益面板数据
        vol_window : int
            波动率计算窗口

        Returns
        -------
        float
            IC与波动率的相关系数
        """
        # 市场收益序列
        market_ret = returns_data.mean(axis=1).values

        # 滚动波动率
        vol_series = pd.Series(market_ret).rolling(vol_window).std().values

        # 对齐: IC[t] 对应 vol[t] (t时刻的波动率)
        n = min(len(ic_series), len(vol_series))
        vol_aligned = vol_series[:n]

        valid = ~np.isnan(vol_aligned)
        ic_valid = ic_series[valid]
        vol_valid = vol_aligned[valid]

        if len(ic_valid) < 5:
            return np.nan

        if np.std(ic_valid) < 1e-10 or np.std(vol_valid) < 1e-10:
            return np.nan

        corr = np.corrcoef(ic_valid, vol_valid)[0, 1]
        return float(corr) if not np.isnan(corr) else np.nan

    # ==================== 工具方法 ====================

    def _check_data_sufficiency(self,
                                factor_data: pd.DataFrame,
                                returns_data: Optional[pd.DataFrame],
                                ) -> Tuple[bool, str]:
        """
        检查数据是否足够进行评估

        Parameters
        ----------
        factor_data : pd.DataFrame
            因子面板数据
        returns_data : pd.DataFrame, optional
            收益面板数据

        Returns
        -------
        Tuple[bool, str]
            (是否充足, 消息)
        """
        if factor_data.shape[0] < self.config.min_data_months:
            return False, f"因子数据长度 {factor_data.shape[0]} < 最小要求 {self.config.min_data_months}"

        if factor_data.shape[1] < 10:
            return False, f"股票数量 {factor_data.shape[1]} < 最小要求 10"

        if returns_data is not None:
            if returns_data.shape[0] < self.config.min_data_months:
                return False, f"收益数据长度 {returns_data.shape[0]} < 最小要求 {self.config.min_data_months}"

        return True, ""

    def _create_alert(self,
                      metric_name: str,
                      value: float,
                      threshold: float,
                      direction: str,
                      level: HealthAlertLevel,
                      category: str,
                      recommendation: str,
                      ) -> HealthAlert:
        """创建警报的工厂方法"""
        return HealthAlert(
            metric_name=metric_name,
            metric_value=value,
            threshold=threshold,
            direction=direction,
            level=level,
            category=category,
            timestamp=datetime.now(),
            recommendation=recommendation,
        )