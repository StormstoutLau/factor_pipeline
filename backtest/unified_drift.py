# -*- coding: utf-8 -*-
"""
统一漂移判定模块 — UnifiedDriftReporter

融合双轨漂移信号:
  - 结构漂移 (来自 Fingerprint): 因子 IC 分布的体制变化
  - 性能漂移 (来自 Backtest): 因子预测能力的衰退

输出统一的漂移判定: stable / warning / drift_detected / severe_drift

设计原则:
  - 三信号加权融合: structure + performance + turnover
  - 可配置阈值和权重
  - 支持单个因子和批量评估
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
from scipy.stats import ks_2samp

logger = logging.getLogger(__name__)

# 默认配置 (P0-1 调松: 5 年数据漂移信号未累积, 阈值过高导致全 stable)
DEFAULT_CONFIG = {
    'structure_weight': 0.45,     # 结构漂移权重
    'performance_weight': 0.35,   # 性能漂移权重
    'turnover_weight': 0.20,      # 换手率漂移权重
    'warning_threshold': 15.0,    # 预警阈值 (30 → 15)
    'drift_threshold': 30.0,      # 漂移确认阈值 (50 → 30)
    'severe_threshold': 50.0,     # 严重漂移阈值 (70 → 50)
    'min_series_length': 20,      # 最小序列长度（置信度要求）
    'icir_improvement_bonus': 0,  # ICIR 提升是否计入漂移（0=不计入）
    # P2 改进: 假阳性控制
    'ewma_alpha': 0.3,            # EWMA 平滑系数 [0, 1]
    'dual_signal_required': True,  # 向后兼容: 旧布尔开关 (被 signal_fusion_mode 取代)
    'structure_sig_threshold': 20.0,  # 结构漂移显著阈值 (30 → 20)
    'performance_sig_threshold': 20.0,  # 性能漂移显著阈值 (30 → 20)
    # P0-1 改进: 滚动窗口 KS
    'rolling_window': 126,        # 滚动窗口大小 (交易日, ≈6个月)
    'rolling_pvalue': 0.05,       # KS 检验 p 值阈值 (低于此值才计入漂移)
    # P2-1 改进: 双信号融合模式 (替代 dual_signal_required 布尔逻辑)
    #   'and': 两信号都显著才确认 (保守, 易漏报)
    #   'or':  任一显著即确认 (激进, 易误报)
    #   'max': 取主信号与主阈值比较, 主信号显著即用主信号分数判定等级 (平衡, 推荐)
    'signal_fusion_mode': 'max',
}

# 漂移等级
DRIFT_LEVELS = ['stable', 'warning', 'drift_detected', 'severe_drift']


class UnifiedDriftReporter:
    """双轨融合漂移判定器。

    融合结构漂移和性能漂移两个维度的信号，
    输出统一的漂移判定。

    Usage:
        reporter = UnifiedDriftReporter()
        verdict = reporter.evaluate_from_engine('PB', engine_results['PB'])
        verdicts = reporter.batch_evaluate(engine_results)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        user_config = dict(config or {})
        # P2-1 向后兼容: 用户传 dual_signal_required 但未传 signal_fusion_mode 时,
        # 从 dual_signal_required 推断 fusion_mode (覆盖默认 'max')
        if 'dual_signal_required' in user_config and 'signal_fusion_mode' not in user_config:
            if user_config['dual_signal_required']:
                user_config['signal_fusion_mode'] = 'and'
            else:
                user_config['signal_fusion_mode'] = 'or'
        self.config = {**DEFAULT_CONFIG, **user_config}

    # ── 漂移信号计算 ──────────────────────────────────

    def _compute_structure_drift(
        self,
        ic_early: np.ndarray,
        ic_late: np.ndarray,
    ) -> float:
        """计算结构漂移分数（基于 KS 检验）。

        将 IC 序列分为前后两段，计算 KS 距离。
        KS 统计量越大，说明分布变化越显著。

        Args:
            ic_early: 前段 IC 序列
            ic_late: 后段 IC 序列

        Returns:
            漂移分数 [0, 100]
        """
        early = ic_early[~np.isnan(ic_early)]
        late = ic_late[~np.isnan(ic_late)]

        if len(early) < 5 or len(late) < 5:
            return 0.0

        ks_stat, _ = ks_2samp(early, late)
        return float(ks_stat * 100)

    def _compute_rolling_structure_drift(
        self,
        ic_series: np.ndarray,
        window: Optional[int] = None,
    ) -> float:
        """滚动窗口 KS 检测结构漂移。

        用固定窗口大小在 IC 序列上滑动,对每个位置的前后两段做 KS 检验,
        取最大漂移分数 (经 p 值过滤)。

        相比二分法的优势:
        - 能定位漂移发生的时间点
        - 不会因前后段过长而平均掉局部漂移信号
        - p 值过滤避免假阳性

        Args:
            ic_series: 完整 IC 序列
            window: 滚动窗口大小 (默认使用 config['rolling_window'])

        Returns:
            最大漂移分数 [0, 100], 经 p 值过滤
        """
        if window is None:
            window = self.config.get('rolling_window', 126)

        p_threshold = self.config.get('rolling_pvalue', 0.05)

        clean = ic_series[~np.isnan(ic_series)]
        n = len(clean)

        # 数据不足: 回退到二分法
        if n < 2 * window:
            if n < 10:
                return 0.0
            mid = n // 2
            return self._compute_structure_drift(clean[:mid], clean[mid:])

        max_score = 0.0
        for i in range(window, n - window + 1):
            early = clean[i - window:i]
            late = clean[i:i + window]
            ks_stat, p_value = ks_2samp(early, late)
            # p 值过滤: 只有统计显著的才计入
            if p_value < p_threshold:
                score = float(ks_stat * 100)
                if score > max_score:
                    max_score = score

        return max_score

    def _compute_performance_drift(
        self,
        icir_early: float,
        icir_late: float,
    ) -> float:
        """计算性能漂移分数（基于 ICIR 变化率）。

        drift = max(0, (1 - icir_late / icir_early)) * 100

        ICIR 下降越多，漂移分数越高。
        ICIR 提升不计入漂移（除非配置 icir_improvement_bonus）。

        Args:
            icir_early: 前段 ICIR
            icir_late: 后段 ICIR

        Returns:
            漂移分数 [0, 100]
        """
        if np.isnan(icir_early) or np.isnan(icir_late):
            return 0.0
        if abs(icir_early) < 1e-10:
            return 0.0

        ratio = icir_late / icir_early
        if ratio >= 1.0:
            # ICIR 提升
            if self.config.get('icir_improvement_bonus', 0):
                return float(max(0, (1 - ratio)) * 100)
            return 0.0

        return float(max(0, (1 - ratio)) * 100)

    def _compute_turnover_drift(
        self,
        turnover_early: float,
        turnover_late: float,
    ) -> float:
        """计算换手率漂移分数。

        drift = max(0, (turnover_late / turnover_early - 1)) * 100

        换手率增加越多，漂移分数越高。

        Args:
            turnover_early: 前段平均换手率
            turnover_late: 后段平均换手率

        Returns:
            漂移分数 [0, 100]
        """
        if np.isnan(turnover_early) or np.isnan(turnover_late):
            return 0.0
        if abs(turnover_early) < 1e-10:
            return 0.0

        ratio = turnover_late / turnover_early
        return float(max(0, (ratio - 1)) * 100)

    # ── 引擎数据提取 ──────────────────────────────────

    def _extract_drift_data(self, engine_result: Dict[str, Any]) -> Dict[str, float]:
        """从引擎结果中提取漂移数据。

        将 IC 序列和换手率序列分为前后两段，
        分别计算结构漂移、性能漂移、换手率漂移。

        Args:
            engine_result: 单个因子的引擎评估结果

        Returns:
            {structure_drift, performance_drift, turnover_drift}
        """
        ic_series = engine_result.get('rank_ic_series', np.array([]))
        turnover = engine_result.get('turnover', np.array([]))
        icir = engine_result.get('rank_icir', np.nan)

        # 序列太短，置信度不足
        min_len = self.config.get('min_series_length', 20)
        if len(ic_series) < min_len:
            return {
                'structure_drift': 0.0,
                'performance_drift': 0.0,
                'turnover_drift': 0.0,
            }

        # 前后段分割 (用于性能漂移的 ICIR 计算)
        mid = len(ic_series) // 2
        ic_early = ic_series[:mid]
        ic_late = ic_series[mid:]

        # 1. 结构漂移: 滚动窗口 KS (P0-1 改进)
        structure_drift = self._compute_rolling_structure_drift(ic_series)

        # 2. 性能漂移: ICIR 变化
        icir_early = self._compute_icir_safe(ic_early)
        icir_late = self._compute_icir_safe(ic_late)
        performance_drift = self._compute_performance_drift(icir_early, icir_late)

        # 3. 换手率漂移
        if len(turnover) >= min_len:
            t_mid = len(turnover) // 2
            to_early = np.nanmean(turnover[:t_mid])
            to_late = np.nanmean(turnover[t_mid:])
            turnover_drift = self._compute_turnover_drift(to_early, to_late)
        else:
            turnover_drift = 0.0

        return {
            'structure_drift': structure_drift,
            'performance_drift': performance_drift,
            'turnover_drift': turnover_drift,
        }

    # ── 安全 ICIR ──────────────────────────────────

    def _compute_icir_safe(self, ic_series: np.ndarray) -> float:
        """安全计算 ICIR（避免 NaN 传播）。

        Args:
            ic_series: IC 序列

        Returns:
            ICIR 或 NaN
        """
        clean = ic_series[~np.isnan(ic_series)]
        if len(clean) < 3:
            return np.nan
        mean_ic = np.mean(clean)
        std_ic = np.std(clean, ddof=1)
        if abs(std_ic) < 1e-12:
            return np.nan
        return float(mean_ic / std_ic)

    # ── 融合判定 ──────────────────────────────────

    def _ewma_smooth(
        self,
        scores: np.ndarray,
        alpha: Optional[float] = None,
    ) -> np.ndarray:
        """指数加权移动平均平滑，过滤单次噪声。

        EWMA 公式: s[t] = alpha * x[t] + (1-alpha) * s[t-1]

        Args:
            scores: 输入分数序列
            alpha: 平滑系数，默认使用配置中的 ewma_alpha

        Returns:
            平滑后的序列
        """
        if alpha is None:
            alpha = self.config.get('ewma_alpha', 0.3)

        if len(scores) == 0:
            return np.array([])
        if len(scores) == 1:
            return scores.copy()

        smoothed = np.zeros_like(scores, dtype=float)
        smoothed[0] = scores[0]
        for i in range(1, len(scores)):
            smoothed[i] = alpha * scores[i] + (1 - alpha) * smoothed[i - 1]

        return smoothed

    def evaluate(
        self,
        structure_drift: float,
        performance_drift: float,
        turnover_drift: float,
    ) -> Dict[str, Any]:
        """融合三个漂移信号，输出统一判定。

        P2-1 改进: 支持 three 融合模式 (signal_fusion_mode):
          - 'and': 两信号都显著才确认 (保守, 旧默认)
          - 'or':  任一显著即确认 (激进)
          - 'max': 主信号显著即用主信号分数判定等级 (平衡, 新默认)

        向后兼容: 若未设置 signal_fusion_mode 但设置了 dual_signal_required,
          True → 'and', False → 'or' (跳过双信号检查)

        Args:
            structure_drift: 结构漂移分数 [0, 100]
            performance_drift: 性能漂移分数 [0, 100]
            turnover_drift: 换手率漂移分数 [0, 100]

        Returns:
            判定结果字典
        """
        w_s = self.config['structure_weight']
        w_p = self.config['performance_weight']
        w_t = self.config['turnover_weight']

        combined = w_s * structure_drift + w_p * performance_drift + w_t * turnover_drift

        # 确定融合模式 (向后兼容: 优先用 signal_fusion_mode, 否则从 dual_signal_required 推断)
        fusion_mode = self.config.get('signal_fusion_mode')
        if fusion_mode is None:
            if self.config.get('dual_signal_required', True):
                fusion_mode = 'and'
            else:
                fusion_mode = 'or'

        struct_threshold = self.config.get('structure_sig_threshold', 30.0)
        perf_threshold = self.config.get('performance_sig_threshold', 30.0)

        struct_sig = structure_drift >= struct_threshold
        perf_sig = performance_drift >= perf_threshold

        # ── 根据融合模式判定等级 ──────────────────────────────────
        if fusion_mode == 'max':
            # max 模式: 取主信号与主阈值比较, 主信号显著则用主信号分数判定等级
            dominant_signal = max(structure_drift, performance_drift)
            dominant_threshold = max(struct_threshold, perf_threshold)
            if dominant_signal >= dominant_threshold:
                # 主信号显著: 等级由主信号分数决定
                if dominant_signal >= self.config['severe_threshold']:
                    level = 'severe_drift'
                elif dominant_signal >= self.config['drift_threshold']:
                    level = 'drift_detected'
                elif dominant_signal >= self.config['warning_threshold']:
                    level = 'warning'
                else:
                    level = 'stable'
            else:
                # 主信号未达阈值: 用 combined 判定 warning/stable
                if combined >= self.config['warning_threshold']:
                    level = 'warning'
                else:
                    level = 'stable'
        else:
            # and / or 模式: 计算 both_significant, 用 combined 判定等级
            if fusion_mode == 'and':
                both_significant = struct_sig and perf_sig
            else:  # 'or' 或未知模式
                both_significant = struct_sig or perf_sig

            if combined >= self.config['severe_threshold'] and both_significant:
                level = 'severe_drift'
            elif combined >= self.config['drift_threshold'] and both_significant:
                level = 'drift_detected'
            elif combined >= self.config['warning_threshold']:
                level = 'warning'
            else:
                level = 'stable'

        return {
            'combined_score': float(combined),
            'level': level,
            'structure_drift': structure_drift,
            'performance_drift': performance_drift,
            'turnover_drift': turnover_drift,
            'signal_fusion_mode': fusion_mode,
            'timestamp': datetime.now(),
        }

    # ── 从引擎结果评估 ──────────────────────────────────

    def evaluate_from_engine(
        self,
        factor_name: str,
        engine_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """从引擎结果直接评估漂移。

        Args:
            factor_name: 因子名称
            engine_result: 单个因子的引擎评估结果

        Returns:
            判定结果字典（含 factor_name）
        """
        drift_data = self._extract_drift_data(engine_result)

        verdict = self.evaluate(
            structure_drift=drift_data['structure_drift'],
            performance_drift=drift_data['performance_drift'],
            turnover_drift=drift_data['turnover_drift'],
        )

        verdict['factor_name'] = factor_name

        logger.info(
            f"Drift verdict for {factor_name}: "
            f"level={verdict['level']}, score={verdict['combined_score']:.1f}"
        )

        return verdict

    # ── 批量评估 ──────────────────────────────────

    def batch_evaluate(
        self,
        engine_results: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """批量评估多个因子的漂移。

        Args:
            engine_results: {factor_name: {metric: value, ...}, ...}

        Returns:
            {factor_name: verdict, ...}
        """
        verdicts = {}
        for name, result in engine_results.items():
            verdicts[name] = self.evaluate_from_engine(name, result)
        return verdicts

    # ── 摘要报告 ──────────────────────────────────

    def summary_report(
        self,
        engine_results: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """生成漂移摘要报告。

        Args:
            engine_results: {factor_name: {metric: value, ...}, ...}

        Returns:
            摘要字典
        """
        verdicts = self.batch_evaluate(engine_results)

        total = len(verdicts)
        level_counts = Counter(v['level'] for v in verdicts.values())

        scores = [v['combined_score'] for v in verdicts.values()]
        avg_score = np.mean(scores) if scores else 0.0

        # 最高漂移因子
        if scores:
            top_idx = np.argmax(scores)
            top_name = list(verdicts.keys())[top_idx]
            top_score = scores[top_idx]
        else:
            top_name = None
            top_score = 0.0

        return {
            'total_factors': total,
            'level_distribution': dict(level_counts),
            'top_drift_factor': top_name,
            'top_drift_score': top_score,
            'average_drift_score': float(avg_score),
            'timestamp': datetime.now(),
        }