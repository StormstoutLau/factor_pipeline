# -*- coding: utf-8 -*-
"""CUSUM 漂移监测器测试 (v3.0.0 T3)

测试 Page (1954) CUSUM 累积和算法的检测能力.

学术依据:
- Page, E. S. (1954). "Continuous Inspection Schemes." Biometrika 41(1/2):100-115.
- Brown, Durbin & Evans (1975). "Techniques for Testing the Constancy of Regression Relationships over Time." JRSS-B 37(2):149-192.

TDD Red 阶段: 测试用例先于实现, 确保接口设计与检测能力要求一致.
"""
import pytest
import numpy as np

from factor_pipeline.backtest.cusum_drift_monitor import CUSUMDriftMonitor


# ============================================================
# 1. 基础功能测试
# ============================================================

class TestCUSUMDriftMonitorBasic:
    """基础功能: 接口、构造、单期更新"""

    def test_01_construction_default_params(self):
        """默认参数构造 (k=0.5σ, h=5σ)"""
        monitor = CUSUMDriftMonitor(baseline_mean=0.0, baseline_std=1.0)
        assert monitor.baseline_mean == 0.0
        assert monitor.baseline_std == 1.0
        assert monitor.k == 0.5  # slack = 0.5σ
        assert monitor.h == 5.0  # trigger = 5σ
        assert monitor.two_sided is True
        assert len(monitor.score_history) == 0

    def test_02_construction_custom_params(self):
        """自定义参数构造"""
        monitor = CUSUMDriftMonitor(
            baseline_mean=0.05, baseline_std=0.02,
            k=0.3, h=4.0, two_sided=False
        )
        assert monitor.baseline_mean == 0.05
        assert monitor.baseline_std == 0.02
        assert monitor.k == 0.3
        assert monitor.h == 4.0
        assert monitor.two_sided is False

    def test_03_update_returns_dict(self):
        """update 返回正确结构的 dict"""
        monitor = CUSUMDriftMonitor(baseline_mean=0.0, baseline_std=1.0)
        result = monitor.update(0.5)
        assert isinstance(result, dict)
        assert 'detected' in result
        assert 'direction' in result
        assert 'S_pos' in result
        assert 'S_neg' in result
        assert 'n_observations' in result

    def test_04_single_update_no_trigger(self):
        """单期更新不应触发 (累积和不足)"""
        monitor = CUSUMDriftMonitor(baseline_mean=0.0, baseline_std=1.0)
        result = monitor.update(3.0)  # 3σ 偏离,但单期累积和 = 3-0-0.5 = 2.5 < 5
        assert result['detected'] is False
        assert result['direction'] is None
        assert result['S_pos'] == pytest.approx(2.5, abs=1e-6)

    def test_05_min_observations_respected(self):
        """min_observations 不足时不判定"""
        monitor = CUSUMDriftMonitor(
            baseline_mean=0.0, baseline_std=1.0, min_observations=5
        )
        for x in [10.0, 10.0, 10.0]:  # 极大值,但观测数不足
            result = monitor.update(x)
            assert result['detected'] is False


# ============================================================
# 2. 检测能力测试 (合成数据 + 已知变点)
# ============================================================

class TestCUSUMDriftMonitorDetection:
    """检测能力: 无漂移 / 上侧 / 下侧 / 阶跃 / 缓慢漂移"""

    def test_10_no_drift_no_false_alarm(self):
        """无漂移数据不应触发 (误报率控制)"""
        np.random.seed(42)
        data = np.random.normal(0, 1, 500)
        monitor = CUSUMDriftMonitor(baseline_mean=0.0, baseline_std=1.0)
        detections = []
        for x in data:
            result = monitor.update(x)
            if result['detected']:
                detections.append(result)
        # 无漂移 500 期,误报次数应 ≤ 1 (h=5σ 时 ARL≈930)
        assert len(detections) <= 1, f"无漂移数据误报 {len(detections)} 次,应 ≤ 1"

    def test_11_upward_drift_detected(self):
        """上侧漂移 (1σ) 应被检测,direction='up'"""
        np.random.seed(42)
        data = np.concatenate([
            np.random.normal(0, 1, 100),  # 前 100 期无漂移
            np.random.normal(1, 1, 100),  # 后 100 期上侧漂移 1σ
        ])
        monitor = CUSUMDriftMonitor(baseline_mean=0.0, baseline_std=1.0)
        detection_result = None
        for i, x in enumerate(data):
            result = monitor.update(x)
            if result['detected']:
                detection_result = result
                detection_idx = i
                break
        assert detection_result is not None, "上侧漂移应被检测"
        assert detection_result['direction'] == 'up'
        assert detection_idx >= 100, f"检测应在变点后,实际 {detection_idx}"
        # 1σ 漂移,k=0.5,h=5 时 ARL≈10,检测延迟应 < 40 (4x ARL)
        delay = detection_idx - 100
        assert delay < 40, f"检测延迟 {delay} 应 < 40"

    def test_12_downward_drift_detected(self):
        """下侧漂移 (-1σ) 应被检测,direction='down'"""
        np.random.seed(42)
        data = np.concatenate([
            np.random.normal(0, 1, 100),
            np.random.normal(-1, 1, 100),  # 下侧漂移 -1σ
        ])
        monitor = CUSUMDriftMonitor(baseline_mean=0.0, baseline_std=1.0)
        detection_result = None
        for i, x in enumerate(data):
            result = monitor.update(x)
            if result['detected']:
                detection_result = result
                detection_idx = i
                break
        assert detection_result is not None, "下侧漂移应被检测"
        assert detection_result['direction'] == 'down'
        assert detection_idx >= 100
        delay = detection_idx - 100
        assert delay < 40

    def test_13_large_step_drift_fast_detection(self):
        """大漂移 (3σ) 应快速检测 (延迟 < 5)"""
        np.random.seed(42)
        data = np.concatenate([
            np.random.normal(0, 1, 100),
            np.random.normal(3, 1, 100),  # 大漂移 3σ
        ])
        monitor = CUSUMDriftMonitor(baseline_mean=0.0, baseline_std=1.0)
        detection_idx = None
        for i, x in enumerate(data):
            result = monitor.update(x)
            if result['detected']:
                detection_idx = i
                break
        assert detection_idx is not None, "大漂移应被检测"
        delay = detection_idx - 100
        assert delay < 5, f"大漂移检测延迟 {delay} 应 < 5"

    def test_14_small_drift_eventually_detected(self):
        """小漂移 (0.3σ) 应最终被检测 (延迟可较长)"""
        np.random.seed(42)
        data = np.concatenate([
            np.random.normal(0, 1, 100),
            np.random.normal(0.3, 1, 200),  # 小漂移 0.3σ,200 期
        ])
        monitor = CUSUMDriftMonitor(baseline_mean=0.0, baseline_std=1.0)
        detection_idx = None
        for i, x in enumerate(data):
            result = monitor.update(x)
            if result['detected']:
                detection_idx = i
                break
        assert detection_idx is not None, "小漂移 0.3σ 应在 200 期内被检测"
        delay = detection_idx - 100
        # 0.3σ 漂移,k=0.5 时有效信号 = 0.3-0.5 < 0,理论 ARL 极长
        # 但实际数据波动可能触发,这里宽松要求 < 200
        assert delay < 200, f"小漂移检测延迟 {delay} 应 < 200"

    def test_15_one_sided_only_upward(self):
        """one_sided=False (仅上侧) 不应检测下侧漂移"""
        np.random.seed(42)
        data = np.concatenate([
            np.random.normal(0, 1, 100),
            np.random.normal(-1, 1, 100),  # 下侧漂移
        ])
        monitor = CUSUMDriftMonitor(
            baseline_mean=0.0, baseline_std=1.0, two_sided=False
        )
        detections = []
        for x in data:
            result = monitor.update(x)
            if result['detected']:
                detections.append(result)
        # one_sided=False 仅检测上侧,下侧漂移不应触发
        assert len(detections) == 0, "one_sided=False 不应检测下侧漂移"


# ============================================================
# 3. 在线更新与状态管理
# ============================================================

class TestCUSUMDriftMonitorOnline:
    """在线更新: 逐期 update 与批处理一致,reset,get_history"""

    def test_20_online_matches_batch(self):
        """逐期 update 的累积和与批处理公式一致"""
        np.random.seed(42)
        data = np.random.normal(0.5, 1, 50)  # 0.5σ 漂移
        monitor = CUSUMDriftMonitor(baseline_mean=0.0, baseline_std=1.0)
        online_S_pos = []
        for x in data:
            result = monitor.update(x)
            online_S_pos.append(result['S_pos'])
        # 批处理公式验证
        k = 0.5
        S = 0.0
        batch_S_pos = []
        for x in data:
            S = max(0, S + (x - 0.0 - k))
            batch_S_pos.append(S)
        np.testing.assert_allclose(
            online_S_pos, batch_S_pos, atol=1e-6,
            err_msg="逐期 update 与批处理公式不一致"
        )

    def test_21_reset_clears_state(self):
        """reset() 清零累积和与历史"""
        monitor = CUSUMDriftMonitor(baseline_mean=0.0, baseline_std=1.0)
        # 用不触发的输入 (S_pos 累积但 < h_sigma=5)
        for x in [1.0, 1.5, 1.2]:
            monitor.update(x)
        assert len(monitor.score_history) == 3
        assert monitor.S_pos > 0  # 累积和 > 0 但未触发
        monitor.reset()
        assert monitor.S_pos == 0.0
        assert monitor.S_neg == 0.0
        assert len(monitor.score_history) == 0

    def test_22_post_detection_reset(self):
        """触发后自动重置累积和 (持续检测)"""
        np.random.seed(42)
        # 两次漂移:第 50 期上侧 2σ,第 150 期再次上侧 2σ
        data = np.concatenate([
            np.random.normal(0, 1, 50),
            np.random.normal(2, 1, 50),
            np.random.normal(0, 1, 50),
            np.random.normal(2, 1, 50),
        ])
        monitor = CUSUMDriftMonitor(baseline_mean=0.0, baseline_std=1.0)
        detection_count = 0
        for x in data:
            result = monitor.update(x)
            if result['detected']:
                detection_count += 1
        assert detection_count >= 2, f"应检测到 ≥2 次漂移,实际 {detection_count}"

    def test_23_get_history(self):
        """get_history 返回正确的历史记录"""
        monitor = CUSUMDriftMonitor(baseline_mean=0.0, baseline_std=1.0)
        for x in [1.0, 2.0, 3.0]:
            monitor.update(x)
        history = monitor.get_history()
        assert 'S_pos' in history
        assert 'S_neg' in history
        assert 'detected' in history
        assert len(history['S_pos']) == 3
        # 返回副本,修改不影响内部
        history['S_pos'].append(999)
        assert len(monitor.score_history) == 3


# ============================================================
# 4. 与 EWMA 对比 (Page 1954 理论保证)
# ============================================================

class TestCUSUMDriftMonitorComparison:
    """CUSUM vs EWMA: 小漂移下 CUSUM 检测延迟应 ≤ EWMA"""

    def test_30_cusum_faster_than_ewma_small_drift(self):
        """0.5σ 漂移下 CUSUM 检测延迟应 ≤ EWMA (Page 1954)"""
        np.random.seed(42)
        # 多次试验取平均延迟
        n_trials = 20
        cusum_delays = []
        ewma_delays = []
        for trial in range(n_trials):
            np.random.seed(42 + trial)
            data = np.concatenate([
                np.random.normal(0, 1, 50),
                np.random.normal(0.5, 1, 150),  # 0.5σ 漂移
            ])
            # CUSUM
            monitor_c = CUSUMDriftMonitor(baseline_mean=0.0, baseline_std=1.0)
            cusum_idx = None
            for i, x in enumerate(data):
                r = monitor_c.update(x)
                if r['detected']:
                    cusum_idx = i
                    break
            if cusum_idx is not None:
                cusum_delays.append(cusum_idx - 50)
            # EWMA (简化:EWMA 超过 3σ 触发)
            alpha = 1 - np.exp(-np.log(2) / 10)  # halflife=10
            ewma = 0.0
            ewma_idx = None
            for i, x in enumerate(data):
                ewma = alpha * x + (1 - alpha) * ewma
                if abs(ewma) > 3.0 and i >= 50:  # 3σ 控制限
                    ewma_idx = i
                    break
            if ewma_idx is not None:
                ewma_delays.append(ewma_idx - 50)
        # CUSUM 平均延迟应 ≤ EWMA 平均延迟
        if cusum_delays and ewma_delays:
            avg_cusum = np.mean(cusum_delays)
            avg_ewma = np.mean(ewma_delays)
            assert avg_cusum <= avg_ewma, (
                f"CUSUM 平均延迟 {avg_cusum} 应 ≤ EWMA {avg_ewma}"
            )


# ============================================================
# 5. 边界条件与数值稳定性
# ============================================================

class TestCUSUMDriftMonitorEdgeCases:
    """边界条件: NaN, 常数序列, 极大值"""

    def test_40_nan_input_handled(self):
        """NaN 输入应被处理 (跳过或填 0)"""
        monitor = CUSUMDriftMonitor(baseline_mean=0.0, baseline_std=1.0)
        result = monitor.update(float('nan'))
        # 不应崩溃,detected 应为 False
        assert result['detected'] is False

    def test_41_constant_sequence_no_trigger(self):
        """常数序列 (等于 baseline_mean) 不应触发"""
        monitor = CUSUMDriftMonitor(baseline_mean=0.0, baseline_std=1.0)
        for _ in range(100):
            result = monitor.update(0.0)
            assert result['detected'] is False
            assert result['S_pos'] == pytest.approx(0.0, abs=1e-10)

    def test_42_extreme_value_single_no_trigger(self):
        """单期极大值 (10σ) 但累积和不足 h=5σ 时...实际 10-0-0.5=9.5>5 应触发"""
        monitor = CUSUMDriftMonitor(baseline_mean=0.0, baseline_std=1.0)
        result = monitor.update(10.0)  # 10σ 偏离
        # S_pos = max(0, 0 + 10 - 0 - 0.5) = 9.5 > 5,应触发
        assert result['detected'] is True
        assert result['direction'] == 'up'

    def test_43_zero_std_raises(self):
        """baseline_std=0 应抛 ValueError (无法标准化)"""
        with pytest.raises(ValueError, match="baseline_std.*must.*positive"):
            CUSUMDriftMonitor(baseline_mean=0.0, baseline_std=0.0)

    def test_44_negative_h_raises(self):
        """h<0 应抛 ValueError"""
        with pytest.raises(ValueError, match="h.*must.*non-negative"):
            CUSUMDriftMonitor(baseline_mean=0.0, baseline_std=1.0, h=-1.0)

    def test_45_negative_k_raises(self):
        """k<0 应抛 ValueError"""
        with pytest.raises(ValueError, match="k.*must.*non-negative"):
            CUSUMDriftMonitor(baseline_mean=0.0, baseline_std=1.0, k=-0.5)
