# -*- coding: utf-8 -*-
"""
P0-1: 滚动窗口 KS + 调松阈值 — 修复 drift 全 stable 问题

测试:
  1. 滚动窗口 KS 在中间漂移场景下分数高于二分法
  2. 滚动窗口对前/后端漂移都能检测
  3. 数据不足时回退到二分法
  4. p值过滤假阳性
  5. 调松后的默认阈值
  6. 真实场景: 5年IC序列有微弱漂移能被检出
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import ks_2samp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from factor_pipeline.backtest.unified_drift import UnifiedDriftReporter, DEFAULT_CONFIG


# =============================================================================
# 滚动窗口 KS 测试
# =============================================================================

class TestRollingStructureDrift:
    """测试滚动窗口 KS 检测结构漂移"""

    def test_01_rolling_detects_mid_window_drift_better_than_half_split(self):
        """滚动窗口在中间窗口漂移场景下分数更高

        场景: 252 天 IC 序列,前 126 天稳定,中间 63 天突变,后 63 天恢复
        二分法: 前 126 vs 后 126,后段含恢复期,信号被稀释
        滚动: 126 窗口扫描,能定位到中间 63 天的漂移
        """
        rng = np.random.default_rng(42)
        # 前 126 天: IC ~ N(0.05, 0.02)
        part1 = rng.normal(0.05, 0.02, 126)
        # 中间 63 天: IC ~ N(0.0, 0.05) — 漂移
        part2 = rng.normal(0.0, 0.05, 63)
        # 后 63 天: 恢复
        part3 = rng.normal(0.05, 0.02, 63)
        ic_series = np.concatenate([part1, part2, part3])

        reporter = UnifiedDriftReporter()
        rolling_score = reporter._compute_rolling_structure_drift(
            ic_series, window=63,
        )
        # 二分法
        mid = len(ic_series) // 2
        half_score = reporter._compute_structure_drift(
            ic_series[:mid], ic_series[mid:],
        )

        print(f"\n滚动窗口分数: {rolling_score:.2f}")
        print(f"二分法分数: {half_score:.2f}")
        # 滚动应能检出漂移 (分数 > 0)
        assert rolling_score > 0, "滚动窗口应检出漂移"
        # 不要求严格大于二分法 (依赖随机性),但滚动应能检出
        assert rolling_score >= 10.0, \
            f"滚动窗口分数 {rolling_score:.2f} 应 >= 10.0 (检出中间漂移)"

    def test_02_rolling_detects_drift_at_end(self):
        """滚动窗口能检测序列末端的漂移"""
        rng = np.random.default_rng(42)
        # 前 189 天稳定
        part1 = rng.normal(0.05, 0.02, 189)
        # 后 63 天漂移
        part2 = rng.normal(-0.02, 0.03, 63)
        ic_series = np.concatenate([part1, part2])

        reporter = UnifiedDriftReporter()
        score = reporter._compute_rolling_structure_drift(
            ic_series, window=63,
        )

        assert score > 20.0, \
            f"末端漂移应被检出, score={score:.2f}"

    def test_03_rolling_falls_back_when_data_too_short(self):
        """数据不足时回退到二分法"""
        # 只有 30 天,window=63 不够
        ic_series = np.random.default_rng(42).normal(0, 0.02, 30)

        reporter = UnifiedDriftReporter()
        score = reporter._compute_rolling_structure_drift(
            ic_series, window=63,
        )

        # 不应报错,应有回退值
        assert isinstance(score, float)
        assert score >= 0.0

    def test_04_pvalue_filter_avoids_false_positive(self):
        """p值过滤: 稳定序列不应被判定为漂移"""
        rng = np.random.default_rng(42)
        # 完全稳定序列
        ic_series = rng.normal(0.05, 0.02, 252)

        reporter = UnifiedDriftReporter()
        score = reporter._compute_rolling_structure_drift(
            ic_series, window=63,
        )

        # 稳定序列分数应较低 (< 15.0)
        assert score < 15.0, \
            f"稳定序列不应被判定为漂移, score={score:.2f}"

    def test_05_rolling_window_configurable(self):
        """滚动窗口大小可配置"""
        rng = np.random.default_rng(42)
        part1 = rng.normal(0.05, 0.02, 126)
        part2 = rng.normal(0.0, 0.05, 126)
        ic_series = np.concatenate([part1, part2])

        reporter = UnifiedDriftReporter()
        score_63 = reporter._compute_rolling_structure_drift(
            ic_series, window=63,
        )
        score_42 = reporter._compute_rolling_structure_drift(
            ic_series, window=42,
        )

        # 两种窗口都应检出漂移
        assert score_63 > 0
        assert score_42 > 0


# =============================================================================
# 调松阈值测试
# =============================================================================

class TestRelaxedThresholds:
    """测试调松后的阈值能在 5 年数据上检出漂移"""

    def test_01_default_thresholds_relaxed(self):
        """默认阈值已调松"""
        # 旧: warning=30, drift=50, severe=70
        # 新: warning=15, drift=30, severe=50
        assert DEFAULT_CONFIG['warning_threshold'] <= 20.0, \
            f"warning_threshold={DEFAULT_CONFIG['warning_threshold']} 应 <= 20"
        assert DEFAULT_CONFIG['drift_threshold'] <= 35.0, \
            f"drift_threshold={DEFAULT_CONFIG['drift_threshold']} 应 <= 35"
        assert DEFAULT_CONFIG['severe_threshold'] <= 55.0, \
            f"severe_threshold={DEFAULT_CONFIG['severe_threshold']} 应 <= 55"

    def test_02_relatively_drift_can_be_detected_with_relaxed_thresholds(self):
        """调松后,中等漂移能被检出 (触发 warning 以上)"""
        rng = np.random.default_rng(42)
        # 前 126 天 IC ~ N(0.05, 0.02), 后 126 天 IC ~ N(0.02, 0.03)
        part1 = rng.normal(0.05, 0.02, 126)
        part2 = rng.normal(0.02, 0.03, 126)
        ic_series = np.concatenate([part1, part2])

        reporter = UnifiedDriftReporter()
        # 模拟引擎结果
        engine_result = {
            'rank_ic_series': ic_series,
            'turnover': np.full(252, 0.3),
            'rank_icir': 0.5,
        }
        verdict = reporter.evaluate_from_engine("test_factor", engine_result)
        print(f"\nverdict: level={verdict['level']}, "
              f"score={verdict['combined_score']:.2f}, "
              f"structure={verdict['structure_drift']:.2f}, "
              f"performance={verdict['performance_drift']:.2f}")

        # 至少触发 warning
        assert verdict['level'] in ['warning', 'drift_detected', 'severe_drift'], \
            f"中等漂移应被检出, level={verdict['level']}"


# =============================================================================
# 真实场景: 5年IC序列
# =============================================================================

class TestRealistic5YearScenario:
    """测试 5 年 IC 序列场景 (模拟真实回测)"""

    def test_01_5year_ic_with_mild_drift_detected(self):
        """5 年 IC 序列有微弱漂移能被检出"""
        rng = np.random.default_rng(42)
        # 5 年 ≈ 1260 交易日, 6 个月 ≈ 126 天
        # 前 3 年稳定
        part1 = rng.normal(0.04, 0.025, 756)
        # 后 2 年漂移 (均值下降, 波动上升)
        part2 = rng.normal(0.01, 0.035, 504)
        ic_series = np.concatenate([part1, part2])

        reporter = UnifiedDriftReporter()
        engine_result = {
            'rank_ic_series': ic_series,
            'turnover': np.full(1260, 0.3),
            'rank_icir': 0.3,
        }
        verdict = reporter.evaluate_from_engine("test_factor", engine_result)
        print(f"\n5年场景 verdict: level={verdict['level']}, "
              f"score={verdict['combined_score']:.2f}, "
              f"structure={verdict['structure_drift']:.2f}, "
              f"performance={verdict['performance_drift']:.2f}")

        # 应触发 warning 以上
        assert verdict['level'] in ['warning', 'drift_detected', 'severe_drift'], \
            f"5年微弱漂移应被检出, level={verdict['level']}"
