# -*- coding: utf-8 -*-
"""
健康度桥接模块 — 回测引擎 → FactorHealthMonitor 适配器

将回测引擎的预计算指标注入 FactorHealthMonitor，构建健康度报告。
不改动外部 FactorHealthMonitor 的代码。

核心职责:
  - 接收回测引擎结果 (engine.py 输出)
  - 将引擎指标映射到 HealthMonitor 的五维指标体系
  - 构建 FactorHealthReport（包含五官维度得分和警报）

设计原则:
  - 不改动外部 FactorHealthMonitor 代码
  - 使用 engine 的预计算指标，不重复计算
  - 缺失维度使用中性值 (50.0)，不阻塞流程
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ── 引入外部 FactorHealthMonitor ──────────────────────────────────
# P1.2: Factor_Fingerprint 已 pip install -e ., 直接导入替代 importlib hack
from factor_pipeline.modules.factor_fingerprint.core.health import (
    FactorHealthMonitor,
    FactorHealthReport,
    HealthConfig,
    HealthAlertLevel,
    HealthAlert,
)


class HealthMonitorAdapter:
    """回测引擎 → FactorHealthMonitor 适配器。

    将 engine.py 的预计算指标注入 FactorHealthMonitor，
    构建健康度报告。不改动外部模块代码。

    Usage:
        adapter = HealthMonitorAdapter()
        report = adapter.build_report_from_engine('PB', engine_results['PB'])
        reports = adapter.build_batch_reports(engine_results)
    """

    def __init__(
        self,
        health_monitor: Optional[FactorHealthMonitor] = None,
        config: Optional[HealthConfig] = None,
    ):
        """初始化适配器。

        Args:
            health_monitor: 已有的 FactorHealthMonitor 实例（可选）
            config: HealthConfig 配置（可选）
        """
        if health_monitor is not None:
            self.health_monitor = health_monitor
            self.config = health_monitor.config
        else:
            self.config = config or HealthConfig()
            self.health_monitor = FactorHealthMonitor(self.config)

        logger.info(f"HealthMonitorAdapter 初始化完成")

    # ── 指标映射 ──────────────────────────────────

    def _map_efficacy_metrics(self, engine_result: Dict[str, Any]) -> Dict[str, float]:
        """将引擎结果映射到效能指标字典。

        Args:
            engine_result: 单个因子的引擎评估结果

        Returns:
            {ic_ir, ic_win_rate, rolling_ic_mean, ic_autocorr}
        """
        metrics = {}

        # IC IR
        metrics['ic_ir'] = float(engine_result.get('rank_icir', np.nan))

        # IC 胜率
        metrics['ic_win_rate'] = float(engine_result.get('hit_rate', np.nan))

        # 滚动 IC 均值
        ic_series = engine_result.get('rank_ic_series', np.array([]))
        ic_clean = ic_series[~np.isnan(ic_series)] if len(ic_series) > 0 else np.array([])
        window = min(self.config.efficacy_rolling_ic_window, len(ic_clean))
        if window >= 3:
            metrics['rolling_ic_mean'] = float(np.mean(ic_clean[-window:]))
        else:
            metrics['rolling_ic_mean'] = float(np.nanmean(ic_clean)) if len(ic_clean) > 0 else np.nan

        # IC 自相关
        if len(ic_clean) >= 5:
            ic_pd = __import__('pandas').Series(ic_clean)
            metrics['ic_autocorr'] = float(ic_pd.autocorr(1))
        else:
            metrics['ic_autocorr'] = np.nan

        return metrics

    def _map_crowding_metrics(self, engine_result: Dict[str, Any]) -> Dict[str, float]:
        """将引擎结果映射到拥挤度指标字典。

        Args:
            engine_result: 单个因子的引擎评估结果

        Returns:
            {turnover, ...}
        """
        metrics = {}

        # 换手率
        turnover = engine_result.get('turnover', np.array([]))
        if len(turnover) > 0:
            metrics['turnover'] = float(np.nanmean(turnover))
        else:
            metrics['turnover'] = np.nan

        return metrics

    def _map_decay_metrics(self, engine_result: Dict[str, Any]) -> Dict[str, float]:
        """将引擎结果映射到衰减指标字典。

        Args:
            engine_result: 单个因子的引擎评估结果

        Returns:
            {long_short_decay_ratio, ic_decay_mean, ...}
        """
        metrics = {}

        # 多空收益衰减比
        ls_returns = engine_result.get('long_short_returns', np.array([]))
        if len(ls_returns) >= self.config.decay_lookback_long:
            short_window = min(self.config.decay_lookback_short, len(ls_returns))
            long_window = min(self.config.decay_lookback_long, len(ls_returns))

            ret_short = np.nanmean(ls_returns[-short_window:])
            ret_long = np.nanmean(ls_returns[-long_window:])

            if abs(ret_long) > 1e-10:
                metrics['long_short_decay_ratio'] = float(ret_short / ret_long)
            else:
                metrics['long_short_decay_ratio'] = np.nan
        else:
            metrics['long_short_decay_ratio'] = np.nan

        # IC 衰减均值
        ic_decay = engine_result.get('ic_decay', np.array([]))
        if len(ic_decay) > 0:
            metrics['ic_decay_mean'] = float(np.nanmean(ic_decay))
        else:
            metrics['ic_decay_mean'] = np.nan

        return metrics

    # ── 五维得分计算 ──────────────────────────────────

    def _compute_efficacy_score(self, efficacy_metrics: Dict[str, float]) -> float:
        """基于预计算指标计算效能得分 [0-100]。

        使用 HealthMonitor 的评分逻辑：ic_ir 和 ic_win_rate 的归一化均值。
        """
        scores = []
        if 'ic_ir' in efficacy_metrics and not np.isnan(efficacy_metrics['ic_ir']):
            scores.append(self.health_monitor._normalize_score(
                efficacy_metrics['ic_ir'], 1.0, 0.0))
        if 'ic_win_rate' in efficacy_metrics and not np.isnan(efficacy_metrics['ic_win_rate']):
            scores.append(self.health_monitor._normalize_score(
                efficacy_metrics['ic_win_rate'], 0.70, 0.45))
        if not scores:
            return 50.0
        return float(np.mean(scores))

    def _compute_crowding_score(self, crowding_metrics: Dict[str, float]) -> float:
        """基于预计算指标计算拥挤度得分 [0-100]。
        """
        scores = []
        if 'turnover' in crowding_metrics and not np.isnan(crowding_metrics['turnover']):
            # 换手率越低越好
            scores.append(self.health_monitor._normalize_score(
                crowding_metrics['turnover'], 0.0, 1.0))
        if not scores:
            return 50.0
        return float(np.mean(scores))

    def _compute_decay_score(self, decay_metrics: Dict[str, float]) -> float:
        """基于预计算指标计算衰减得分 [0-100]。
        """
        scores = []
        if 'long_short_decay_ratio' in decay_metrics and not np.isnan(decay_metrics['long_short_decay_ratio']):
            # 衰减比越高越好（>=1 意味着近期收益不低于长期）
            scores.append(self.health_monitor._normalize_score(
                decay_metrics['long_short_decay_ratio'], 1.5, 0.3))
        if not scores:
            return 50.0
        return float(np.mean(scores))

    # ── 构建报告 ──────────────────────────────────

    def build_report_from_engine(
        self,
        factor_name: str,
        engine_results: Dict[str, Any],
    ) -> FactorHealthReport:
        """从引擎结果构建单个因子的健康度报告。

        Args:
            factor_name: 因子名称
            engine_results: 单个因子的引擎评估结果

        Returns:
            FactorHealthReport 实例
        """
        # 如果引擎结果为空，返回中性报告
        if not engine_results:
            return FactorHealthReport(
                factor_name=factor_name,
                timestamp=datetime.now(),
                health_score=50.0,
                health_level=HealthAlertLevel.WATCH,
                crowding_score=50.0,
                efficacy_score=50.0,
                capacity_score=50.0,
                decay_score=50.0,
                regime_score=50.0,
            )

        # 1. 映射指标
        efficacy_metrics = self._map_efficacy_metrics(engine_results)
        crowding_metrics = self._map_crowding_metrics(engine_results)
        decay_metrics = self._map_decay_metrics(engine_results)

        # 2. 计算各维度得分
        efficacy_score = self._compute_efficacy_score(efficacy_metrics)
        crowding_score = self._compute_crowding_score(crowding_metrics)
        decay_score = self._compute_decay_score(decay_metrics)
        # 容量和体制敏感性无引擎数据，使用中性值
        capacity_score = 50.0
        regime_score = 50.0

        # 3. 生成警报
        alerts = self._generate_alerts(
            factor_name, efficacy_metrics, crowding_metrics, decay_metrics
        )

        # 4. 综合评分
        dim_scores = {
            'crowding': crowding_score,
            'efficacy': efficacy_score,
            'capacity': capacity_score,
            'decay': decay_score,
            'regime': regime_score,
        }
        health_score, health_level = self.health_monitor._compute_health_score(
            dim_scores, alerts
        )

        # 5. 构建报告
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
            capacity_metrics={},
            decay_metrics=decay_metrics,
            regime_metrics={},
            alerts=alerts,
        )

        logger.info(
            f"Health report for {factor_name}: "
            f"score={health_score:.1f}, level={health_level.value}"
        )

        return report

    def build_batch_reports(
        self,
        engine_results: Dict[str, Dict[str, Any]],
    ) -> Dict[str, FactorHealthReport]:
        """批量构建多个因子的健康度报告。

        Args:
            engine_results: {factor_name: {metric: value, ...}, ...}

        Returns:
            {factor_name: FactorHealthReport, ...}
        """
        reports = {}
        for name, result in engine_results.items():
            logger.info(f"Building health report for {name}...")
            reports[name] = self.build_report_from_engine(name, result)
        return reports

    # ── 警报生成 ──────────────────────────────────

    def _generate_alerts(
        self,
        factor_name: str,
        efficacy_metrics: Dict[str, float],
        crowding_metrics: Dict[str, float],
        decay_metrics: Dict[str, float],
    ) -> List[HealthAlert]:
        """基于预计算指标生成警报列表。

        Args:
            factor_name: 因子名称
            efficacy_metrics: 效能指标
            crowding_metrics: 拥挤度指标
            decay_metrics: 衰减指标

        Returns:
            警报列表
        """
        alerts = []

        # 效能警报
        ic_ir = efficacy_metrics.get('ic_ir', np.nan)
        if not np.isnan(ic_ir) and ic_ir < self.config.efficacy_icir_threshold:
            alerts.append(HealthAlert(
                metric_name='ic_ir',
                metric_value=ic_ir,
                threshold=self.config.efficacy_icir_threshold,
                direction='below',
                level=HealthAlertLevel.WARNING,
                category='efficacy',
                timestamp=datetime.now(),
                recommendation=f'IC IR {ic_ir:.3f} 低于阈值 {self.config.efficacy_icir_threshold}，因子预测能力不足',
            ))

        ic_win_rate = efficacy_metrics.get('ic_win_rate', np.nan)
        if not np.isnan(ic_win_rate) and ic_win_rate < self.config.efficacy_ic_win_rate_threshold:
            alerts.append(HealthAlert(
                metric_name='ic_win_rate',
                metric_value=ic_win_rate,
                threshold=self.config.efficacy_ic_win_rate_threshold,
                direction='below',
                level=HealthAlertLevel.WARNING,
                category='efficacy',
                timestamp=datetime.now(),
                recommendation=f'IC胜率 {ic_win_rate:.1%} 低于阈值 {self.config.efficacy_ic_win_rate_threshold:.0%}',
            ))

        # 拥挤度警报
        turnover = crowding_metrics.get('turnover', np.nan)
        if not np.isnan(turnover) and turnover > self.config.crowding_turnover_threshold:
            alerts.append(HealthAlert(
                metric_name='turnover',
                metric_value=turnover,
                threshold=self.config.crowding_turnover_threshold,
                direction='above',
                level=HealthAlertLevel.WARNING,
                category='crowding',
                timestamp=datetime.now(),
                recommendation=f'年化换手率 {turnover:.1%} 超过阈值 {self.config.crowding_turnover_threshold:.0%}',
            ))

        # 衰减警报
        decay_ratio = decay_metrics.get('long_short_decay_ratio', np.nan)
        if not np.isnan(decay_ratio) and decay_ratio < self.config.decay_long_short_ratio_threshold:
            alerts.append(HealthAlert(
                metric_name='long_short_decay_ratio',
                metric_value=decay_ratio,
                threshold=self.config.decay_long_short_ratio_threshold,
                direction='below',
                level=HealthAlertLevel.WARNING,
                category='decay',
                timestamp=datetime.now(),
                recommendation=f'多空收益衰减比 {decay_ratio:.2f} 低于阈值 {self.config.decay_long_short_ratio_threshold}',
            ))

        return alerts