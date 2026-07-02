# -*- coding: utf-8 -*-
"""
P2: 漂移检测假阳性控制测试

改进:
  A. 滚动窗口替代二分分割
  B. p 值阈值替代固定 KS 统计量阈值
  C. EWMA 平滑组合分数
  D. 双信号显著性要求 — 只有结构 + 性能同时显著才确认漂移
"""

import numpy as np
import pytest
from factor_pipeline.backtest.unified_drift import UnifiedDriftReporter


# =============================================================================
# 辅助: 构造引擎结果
# =============================================================================

def _make_engine_result(ic_series, turnover=None, icir=None):
    """构造引擎结果"""
    result = {
        'rank_ic_series': np.asarray(ic_series, dtype=float),
        'rank_icir': icir if icir is not None else np.nan,
    }
    if turnover is not None:
        result['turnover'] = np.asarray(turnover, dtype=float)
    return result


# =============================================================================
# 测试类 1: 滚动窗口替代二分
# =============================================================================

class TestRollingWindow:
    """测试滚动窗口提取漂移数据"""

    def test_01_rolling_window_not_binary_split(self):
        """滚动窗口使用连续滑动窗口，而非一次性二分"""
        # 构造 60 期 IC 序列，前 40 期有正 IC，后 20 期有负 IC
        np.random.seed(42)
        ic_series = np.concatenate([
            np.random.normal(0.05, 0.1, 40),  # 前段: 正 IC
            np.random.normal(-0.03, 0.1, 20),  # 后段: 负 IC
        ])
        engine = _make_engine_result(ic_series)

        reporter = UnifiedDriftReporter()
        drift_data = reporter._extract_drift_data(engine)

        # 滚动窗口应检测到负 IC 段的漂移
        assert drift_data['structure_drift'] > 0, \
            "分散在整个序列中，滚动窗口应该能捕捉到漂移信号"

    def test_02_stable_series_no_drift(self):
        """稳定序列不应触发漂移"""
        np.random.seed(42)
        ic_series = np.random.normal(0.05, 0.1, 60)
        engine = _make_engine_result(ic_series)

        reporter = UnifiedDriftReporter()
        drift_data = reporter._extract_drift_data(engine)

        # 稳定序列的结构漂移应该很低
        assert drift_data['structure_drift'] < 30, \
            f"稳定序列不应触发高漂移: {drift_data['structure_drift']}"

    def test_03_short_series_returns_zero(self):
        """序列太短 → 返回零漂移"""
        ic_series = np.random.normal(0.05, 0.1, 15)  # < min_series_length(20)
        engine = _make_engine_result(ic_series)

        reporter = UnifiedDriftReporter()
        drift_data = reporter._extract_drift_data(engine)

        assert drift_data['structure_drift'] == 0.0
        assert drift_data['performance_drift'] == 0.0


# =============================================================================
# 测试类 2: p 值阈值替代固定 KS 统计量
# =============================================================================

class TestPValueThreshold:
    """测试 p 值驱动的结构漂移判定"""

    def test_04_identical_distribution_not_significant(self):
        """相同分布 → p 值大 → 不显著"""
        np.random.seed(42)
        # 两个相同分布的样本
        ic_early = np.random.normal(0.05, 0.1, 100)
        ic_late = np.random.normal(0.05, 0.1, 100)

        reporter = UnifiedDriftReporter()
        drift = reporter._compute_structure_drift(ic_early, ic_late)

        # 相同分布 → 结构漂移应该很低
        assert drift < 30, f"相同分布不应触发高漂移: {drift}"

    def test_05_mean_shift_significant(self):
        """均值显著偏移 → 结构漂移高"""
        np.random.seed(42)
        ic_early = np.random.normal(0.05, 0.1, 100)
        ic_late = np.random.normal(-0.05, 0.1, 100)  # 均值偏移 0.10

        reporter = UnifiedDriftReporter()
        drift = reporter._compute_structure_drift(ic_early, ic_late)

        # 均值显著偏移 → 结构漂移应该高
        assert drift > 30, f"均值显著偏移应触发漂移: {drift}"

    def test_06_small_sample_p_value_adaptive(self):
        """小样本时 p 值更保守，避免假阳性"""
        np.random.seed(42)
        ic_early = np.random.normal(0.05, 0.1, 20)
        ic_late = np.random.normal(0.03, 0.1, 20)  # 微小偏移

        reporter = UnifiedDriftReporter()
        drift = reporter._compute_structure_drift(ic_early, ic_late)

        # 小样本 + 微小偏移 → 不应触发高漂移
        assert drift < 50, \
            f"小样本 + 微小偏移不应触发严重漂移: {drift}"


# =============================================================================
# 测试类 3: EWMA 平滑
# =============================================================================

class TestEWMASmoothing:
    """测试 EWMA 平滑降低假阳性"""

    def test_07_ewma_smoothing_reduces_spike(self):
        """单次尖峰经过 EWMA 平滑后降低"""
        # 构造分数序列: 大部分稳定，中间有一次尖峰
        scores = [10, 12, 11, 9, 13, 60, 11, 10, 12, 14]  # 第 6 个是尖峰

        reporter = UnifiedDriftReporter()
        smoothed = reporter._ewma_smooth(np.array(scores, dtype=float))

        # 平滑后的尖峰应该低于原始值
        assert smoothed[5] < scores[5], \
            f"EWMA 应降低尖峰: original={scores[5]}, smoothed={smoothed[5]}"

        # 平滑后的值应该都 > 0
        assert all(s >= 0 for s in smoothed)

    def test_08_ewma_converges_to_sustained_level(self):
        """持续高位 → EWMA 逐步收敛到真实水平"""
        scores = [10, 50, 55, 52, 53, 54, 51, 55, 53, 52]  # 从第 2 期开始持续高位

        reporter = UnifiedDriftReporter()
        smoothed = reporter._ewma_smooth(np.array(scores, dtype=float))

        # 持续高位 → 平滑后也应持续高位
        assert smoothed[-1] > 40, f"持续高位平滑后应保持高位: {smoothed[-1]}"

    def test_09_ewma_single_value(self):
        """单值 → 不崩溃"""
        reporter = UnifiedDriftReporter()
        smoothed = reporter._ewma_smooth(np.array([50.0]))
        assert len(smoothed) == 1
        assert smoothed[0] == 50.0


# =============================================================================
# 测试类 4: 双信号显著性要求
# =============================================================================

class TestCombinedSignificance:
    """测试双信号同时显著才确认漂移 (AND 模式)"""

    def test_10_only_structure_drift_no_drift(self):
        """仅结构漂移（如风格切换） → AND 模式下不应判定为漂移"""
        # 结构漂移高（分布变了），但性能漂移低（ICIR 没变）
        # P2-1 更新: 显式用 'and' 模式测试旧行为 (默认已是 'max' 模式)
        drift_data = {
            'structure_drift': 60.0,
            'performance_drift': 5.0,
            'turnover_drift': 10.0,
        }
        reporter = UnifiedDriftReporter(config={'signal_fusion_mode': 'and'})
        combined = drift_data['structure_drift'] * 0.45 + \
                   drift_data['performance_drift'] * 0.35 + \
                   drift_data['turnover_drift'] * 0.20
        # 纯组合分数: 60*0.45 + 5*0.35 + 10*0.20 = 27 + 1.75 + 2 = 30.75
        # 组合分数在 warning_threshold(15) 以上，但性能漂移不显著
        # AND 双信号要求 → 应降级为 warning

        verdict = reporter.evaluate(
            drift_data['structure_drift'],
            drift_data['performance_drift'],
            drift_data['turnover_drift'],
        )
        # AND 模式: 不应判定为 drift_detected 或 severe
        assert verdict['level'] in ('stable', 'warning'), \
            f"AND 模式仅结构漂移不应判定为 drift: {verdict['level']}"

    def test_11_only_performance_drift_no_drift(self):
        """仅性能漂移（单期 ICIR 波动） → AND 模式下不应判定为漂移"""
        # P2-1 更新: 显式用 'and' 模式测试旧行为
        drift_data = {
            'structure_drift': 10.0,
            'performance_drift': 55.0,
            'turnover_drift': 5.0,
        }
        reporter = UnifiedDriftReporter(config={'signal_fusion_mode': 'and'})
        verdict = reporter.evaluate(
            drift_data['structure_drift'],
            drift_data['performance_drift'],
            drift_data['turnover_drift'],
        )
        assert verdict['level'] in ('stable', 'warning'), \
            f"AND 模式仅性能漂移不应判定为 drift: {verdict['level']}"

    def test_12_both_significant_drift_confirmed(self):
        """结构 + 性能同时漂移 → 确认漂移"""
        drift_data = {
            'structure_drift': 60.0,
            'performance_drift': 55.0,
            'turnover_drift': 20.0,
        }
        reporter = UnifiedDriftReporter()
        verdict = reporter.evaluate(
            drift_data['structure_drift'],
            drift_data['performance_drift'],
            drift_data['turnover_drift'],
        )
        assert verdict['level'] in ('drift_detected', 'severe_drift'), \
            f"双信号显著应确认漂移: {verdict['level']}"

    def test_13_both_low_stable(self):
        """两个信号都低 → stable"""
        drift_data = {
            'structure_drift': 5.0,
            'performance_drift': 3.0,
            'turnover_drift': 2.0,
        }
        reporter = UnifiedDriftReporter()
        verdict = reporter.evaluate(
            drift_data['structure_drift'],
            drift_data['performance_drift'],
            drift_data['turnover_drift'],
        )
        assert verdict['level'] == 'stable', \
            f"双信号都低应为 stable: {verdict['level']}"


# =============================================================================
# 测试类 5: 端到端集成
# =============================================================================

class TestEndToEnd:
    """测试端到端漂移检测流程"""

    def test_14_engine_integration_stable(self):
        """稳定因子 → 端到端不触发漂移"""
        np.random.seed(42)
        ic_series = np.random.normal(0.05, 0.1, 60)
        engine = _make_engine_result(ic_series, icir=0.5)

        reporter = UnifiedDriftReporter()
        verdict = reporter.evaluate_from_engine('stable_factor', engine)

        assert verdict['level'] in ('stable', 'warning'), \
            f"稳定因子不应触发漂移: {verdict['level']}"

    def test_15_engine_integration_drifted(self):
        """漂移因子 → 端到端应检测到漂移"""
        np.random.seed(42)
        ic_series = np.concatenate([
            np.random.normal(0.10, 0.1, 30),  # 前 30 期高 IC
            np.random.normal(-0.05, 0.15, 30),  # 后 30 期负 IC + 高波动
        ])
        engine = _make_engine_result(ic_series, icir=0.3)

        reporter = UnifiedDriftReporter()
        verdict = reporter.evaluate_from_engine('drifted_factor', engine)

        assert verdict['level'] in ('drift_detected', 'severe_drift'), \
            f"漂移因子应被检测到: {verdict['level']}"