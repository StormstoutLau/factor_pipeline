# -*- coding: utf-8 -*-
"""
Pipeline 集成模块 — 回测引擎与 Pipeline 的桥接

提供端到端流程:
  Pipeline 输出 → DataBridge → DataLoaderV3 → Engine → HealthMonitorAdapter → UnifiedDriftReporter

所有模块通过统一入口串联，输出结构化结果。

Usage:
    from factor_pipeline.backtest.pipeline_integration import PipelineBacktestRunner

    runner = PipelineBacktestRunner(config)
    results = runner.run(processed_factors, price_data)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from .data_bridge import DataBridge
from .engine import FactorBacktestEngine
from .health_bridge import HealthMonitorAdapter
from .unified_drift import UnifiedDriftReporter

logger = logging.getLogger(__name__)


class PipelineBacktestRunner:
    """Pipeline 回测运行器。

    串联整个回测流程:
      1. DataBridge: Pipeline 输出 → DataLoaderV3
      2. FactorBacktestEngine: 因子级指标计算
      3. HealthMonitorAdapter: 健康度评估
      4. UnifiedDriftReporter: 漂移检测

    Usage:
        runner = PipelineBacktestRunner(config)
        results = runner.run(processed_factors, price_data)
    """

    def __init__(self, config: Optional[Any] = None):
        """初始化运行器。

        Args:
            config: PipelineV2ConfigUnified 或 BacktestConfig 实例
        """
        self.config = config

        # 提取回测配置
        bt_config = self._extract_backtest_config(config)

        self.bridge = DataBridge()
        self.drift_reporter = UnifiedDriftReporter(config={
            'warning_threshold': bt_config.get('drift_warning_threshold', 30),
            'drift_threshold': bt_config.get('drift_detect_threshold', 50),
            'severe_threshold': bt_config.get('drift_severe_threshold', 70),
        })
        self.health_adapter = HealthMonitorAdapter()

        self._enable_drift = bt_config.get('enable_drift_detection', True)
        self._enable_health = bt_config.get('enable_health_check', True)

    def _extract_backtest_config(self, config: Optional[Any]) -> Dict[str, Any]:
        """从配置对象中提取回测参数。

        支持 PipelineV2ConfigUnified 和 BacktestConfig 两种类型。
        """
        if config is None:
            return {}

        # 如果是 PipelineV2ConfigUnified，提取 backtest 子配置
        if hasattr(config, 'backtest'):
            bt = config.backtest
            return {
                'ic_method': getattr(bt, 'ic_method', 'rank'),
                'top_n': getattr(bt, 'top_n', 0.2),
                'ls_method': getattr(bt, 'ls_method', 'top_n'),
                'max_lag': getattr(bt, 'max_lag', 12),
                'enable_drift_detection': getattr(bt, 'enable_drift_detection', True),
                'drift_warning_threshold': getattr(bt, 'drift_warning_threshold', 30),
                'drift_detect_threshold': getattr(bt, 'drift_detect_threshold', 50),
                'drift_severe_threshold': getattr(bt, 'drift_severe_threshold', 70),
                'enable_health_check': getattr(bt, 'enable_health_check', True),
            }

        # 如果是 BacktestConfig 实例
        if hasattr(config, 'ic_method'):
            return {
                'ic_method': getattr(config, 'ic_method', 'rank'),
                'top_n': getattr(config, 'top_n', 0.2),
                'ls_method': getattr(config, 'ls_method', 'top_n'),
                'max_lag': getattr(config, 'max_lag', 12),
                'enable_drift_detection': getattr(config, 'enable_drift_detection', True),
                'drift_warning_threshold': getattr(config, 'drift_warning_threshold', 30),
                'drift_detect_threshold': getattr(config, 'drift_detect_threshold', 50),
                'drift_severe_threshold': getattr(config, 'drift_severe_threshold', 70),
                'enable_health_check': getattr(config, 'enable_health_check', True),
            }

        return {}

    def run(
        self,
        processed_factors: Dict[str, pd.DataFrame],
        price_data: pd.DataFrame,
    ) -> Dict[str, Any]:
        """运行完整的回测评估流程。

        Args:
            processed_factors: Pipeline 处理后的因子数据
                {factor_name: DataFrame(index=stocks, columns=dates)}
            price_data: 价格数据 DataFrame(index=stocks, columns=dates)

        Returns:
            {
                'engine_results': {factor_name: {metric: value, ...}},
                'factor_ranking': [factor_name, ...],  # 按 ICIR 排序
                'health_reports': {factor_name: FactorHealthReport, ...},
                'drift_verdicts': {factor_name: verdict, ...},
                'drift_summary': {...},
            }
        """
        logger.info("PipelineBacktestRunner 开始运行...")

        # 1. 验证数据
        is_valid, msg = self.bridge.validate_shapes(processed_factors, price_data)
        if not is_valid:
            raise ValueError(f"数据验证失败: {msg}")

        # 2. 创建 DataLoaderV3
        dl = self.bridge.create_dataloader(processed_factors, price_data)

        # 3. 创建回测引擎并运行
        engine_config = self._extract_backtest_config(self.config)
        engine = FactorBacktestEngine(dl, config={
            'ic_method': engine_config.get('ic_method', 'rank'),
            'top_n': engine_config.get('top_n', 0.2),
            'ls_method': engine_config.get('ls_method', 'top_n'),
            'max_lag': engine_config.get('max_lag', 12),
        })
        engine_results = engine.run()

        # 4. 因子排序
        factor_ranking = engine.rank_by_icir()

        # 5. 健康度评估
        health_reports = {}
        if self._enable_health:
            health_reports = self.health_adapter.build_batch_reports(engine_results)

        # 6. 漂移检测
        drift_verdicts = {}
        drift_summary = {}
        if self._enable_drift:
            drift_verdicts = self.drift_reporter.batch_evaluate(engine_results)
            drift_summary = self.drift_reporter.summary_report(engine_results)

        logger.info(
            f"PipelineBacktestRunner 完成: "
            f"{len(engine_results)} 个因子, "
            f"排名第一: {factor_ranking[0] if factor_ranking else 'N/A'}"
        )

        return {
            'engine_results': engine_results,
            'factor_ranking': factor_ranking,
            'health_reports': health_reports,
            'drift_verdicts': drift_verdicts,
            'drift_summary': drift_summary,
        }

    def run_quick(
        self,
        processed_factors: Dict[str, pd.DataFrame],
        price_data: pd.DataFrame,
    ) -> Dict[str, Any]:
        """快速评估（仅引擎指标，跳过健康度和漂移）。

        Args:
            processed_factors: Pipeline 处理后的因子数据
            price_data: 价格数据

        Returns:
            {factor_name: {metric: value, ...}}
        """
        engine_config = self._extract_backtest_config(self.config)
        dl = self.bridge.create_dataloader(processed_factors, price_data)
        engine = FactorBacktestEngine(dl, config={
            'ic_method': engine_config.get('ic_method', 'rank'),
            'top_n': engine_config.get('top_n', 0.2),
            'ls_method': engine_config.get('ls_method', 'top_n'),
            'max_lag': engine_config.get('max_lag', 12),
        })
        return engine.run()

    def summary(self, results: Dict[str, Any]) -> str:
        """生成人类可读的评估摘要。

        Args:
            results: run() 的返回值

        Returns:
            格式化的摘要字符串
        """
        lines = ["=" * 60, "因子回测评估摘要", "=" * 60]

        engine_results = results.get('engine_results', {})
        factor_ranking = results.get('factor_ranking', [])
        drift_summary = results.get('drift_summary', {})

        lines.append(f"\n评估因子数: {len(engine_results)}")
        lines.append(f"因子排名 (按 ICIR):")

        for i, name in enumerate(factor_ranking[:10]):
            m = engine_results[name]
            rank_icir = m.get('rank_icir', float('nan'))
            hit_rate = m.get('hit_rate', float('nan'))
            lines.append(
                f"  [{i+1:2d}] {name:20s}  "
                f"ICIR={rank_icir:6.3f}  "
                f"HitRate={hit_rate:.1%}"
            )

        if drift_summary:
            lines.append(f"\n漂移摘要:")
            lines.append(f"  总因子数: {drift_summary.get('total_factors', 0)}")
            lines.append(f"  等级分布: {drift_summary.get('level_distribution', {})}")
            lines.append(f"  平均漂移: {drift_summary.get('average_drift_score', 0):.1f}")
            lines.append(f"  最高漂移: {drift_summary.get('top_drift_factor', 'N/A')} "
                         f"({drift_summary.get('top_drift_score', 0):.1f})")

        lines.append("=" * 60)
        return "\n".join(lines)