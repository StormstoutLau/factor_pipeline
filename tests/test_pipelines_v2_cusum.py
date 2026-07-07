# -*- coding: utf-8 -*-
"""CUSUM 管线集成测试 (v3.0.0 T3.4)

测试 CUSUMDriftMonitor 集成到 FactorProcessingPipelineV2.

T3.4 设计 (经第十六轮审查修正):
- CUSUM 作为事后诊断工具, 不侵入 fit/transform 循环
- 监测对象: 因子值矩阵的横截面统计量 (均值/标准差), 非 IC
  (IC 需 forward returns, 管线内部不计算)
- 两个 CUSUM (均值+标准差) 独立监测, 不做 BH-FDR (序贯检验)
- 用更高 h (5.5σ) 补偿误报率叠加
- enable_cusum_drift_monitor=False 默认关, 向后兼容

TDD Red 阶段.
"""
import pytest
import numpy as np
import pandas as pd

from factor_pipeline.pipelines_v2 import FactorProcessingPipelineV2, PipelineV2Config


# ============================================================
# 1. 配置开关测试
# ============================================================

class TestCUSUMConfigSwitch:
    """配置开关: enable_cusum_drift_monitor"""

    def test_01_default_disabled(self):
        """默认 enable_cusum_drift_monitor=False (向后兼容)"""
        config = PipelineV2Config()
        assert hasattr(config, 'enable_cusum_drift_monitor')
        assert config.enable_cusum_drift_monitor is False

    def test_02_enable_cusum(self):
        """可启用 enable_cusum_drift_monitor=True"""
        config = PipelineV2Config(enable_cusum_drift_monitor=True)
        assert config.enable_cusum_drift_monitor is True

    def test_03_cusum_params_default(self):
        """CUSUM 参数默认值: k=0.5, h=5.5"""
        config = PipelineV2Config()
        assert config.cusum_k == 0.5
        assert config.cusum_h == 5.5  # 两个 CUSUM 叠加, h=5.5 补偿

    def test_04_cusum_params_custom(self):
        """自定义 CUSUM 参数"""
        config = PipelineV2Config(
            enable_cusum_drift_monitor=True,
            cusum_k=0.3, cusum_h=4.0
        )
        assert config.cusum_k == 0.3
        assert config.cusum_h == 4.0


# ============================================================
# 2. 监测器初始化测试
# ============================================================

class TestCUSUMMonitorInit:
    """监测器初始化: 启用/禁用"""

    def test_10_disabled_no_monitors(self):
        """enable_cusum_drift_monitor=False 时无 CUSUM 监测器"""
        config = PipelineV2Config(enable_cusum_drift_monitor=False)
        pipeline = FactorProcessingPipelineV2(config)
        assert not hasattr(pipeline, 'cusum_monitors') or not pipeline.cusum_monitors

    def test_11_enabled_creates_monitors(self):
        """enable_cusum_drift_monitor=True 时创建 CUSUM 监测器"""
        config = PipelineV2Config(enable_cusum_drift_monitor=True)
        pipeline = FactorProcessingPipelineV2(config)
        assert hasattr(pipeline, 'cusum_monitors')
        # 两个监测器: 'mean' 和 'std'
        assert 'mean' in pipeline.cusum_monitors
        assert 'std' in pipeline.cusum_monitors

    def test_12_monitors_use_config_params(self):
        """监测器使用配置参数"""
        config = PipelineV2Config(
            enable_cusum_drift_monitor=True,
            cusum_k=0.3, cusum_h=4.0
        )
        pipeline = FactorProcessingPipelineV2(config)
        mean_monitor = pipeline.cusum_monitors['mean']
        assert mean_monitor.k == 0.3
        assert mean_monitor.h == 4.0


# ============================================================
# 3. 事后诊断测试 (monitor_cusum_drift 方法)
# ============================================================

class TestCUSUMPostDiagnosis:
    """事后诊断: monitor_cusum_drift(factor_data) 方法"""

    def test_20_disabled_returns_empty(self):
        """enable_cusum_drift_monitor=False 时返回空 dict"""
        config = PipelineV2Config(enable_cusum_drift_monitor=False)
        pipeline = FactorProcessingPipelineV2(config)
        # 合成因子数据
        np.random.seed(42)
        factor_data = {
            'f1': pd.DataFrame(np.random.normal(0, 1, (100, 50))),
        }
        result = pipeline.monitor_cusum_drift(factor_data)
        assert result == {} or result is None

    def test_21_enabled_returns_dict(self):
        """enable_cusum_drift_monitor=True 时返回 dict"""
        config = PipelineV2Config(enable_cusum_drift_monitor=True)
        pipeline = FactorProcessingPipelineV2(config)
        np.random.seed(42)
        factor_data = {
            'f1': pd.DataFrame(np.random.normal(0, 1, (100, 50))),
        }
        result = pipeline.monitor_cusum_drift(factor_data)
        assert isinstance(result, dict)
        # 应包含 'mean' 和 'std' 键
        assert 'mean' in result
        assert 'std' in result

    def test_22_drift_detected_in_mean(self):
        """均值漂移应被 mean CUSUM 检测"""
        config = PipelineV2Config(
            enable_cusum_drift_monitor=True,
            cusum_k=0.5, cusum_h=5.0
        )
        pipeline = FactorProcessingPipelineV2(config)
        np.random.seed(42)
        # 前 100 期 N(0,1), 后 100 期 N(3,1) — 均值漂移 3σ
        data = np.concatenate([
            np.random.normal(0, 1, (100, 50)),
            np.random.normal(3, 1, (100, 50)),
        ], axis=0)
        factor_data = {'f1': pd.DataFrame(data)}
        result = pipeline.monitor_cusum_drift(factor_data)
        # mean CUSUM 应检测到漂移
        assert result['mean']['detected'] is True
        assert result['mean']['direction'] == 'up'

    def test_23_volatility_drift_detected(self):
        """波动率漂移 (std 增大) 应被 std CUSUM 检测"""
        config = PipelineV2Config(
            enable_cusum_drift_monitor=True,
            cusum_k=0.5, cusum_h=5.0
        )
        pipeline = FactorProcessingPipelineV2(config)
        np.random.seed(42)
        # 前 100 期 N(0,1), 后 100 期 N(0,3) — 波动率漂移
        data = np.concatenate([
            np.random.normal(0, 1, (100, 50)),
            np.random.normal(0, 3, (100, 50)),
        ], axis=0)
        factor_data = {'f1': pd.DataFrame(data)}
        result = pipeline.monitor_cusum_drift(factor_data)
        # std CUSUM 应检测到漂移
        assert result['std']['detected'] is True

    def test_24_no_drift_no_detection(self):
        """无漂移数据不应触发"""
        config = PipelineV2Config(
            enable_cusum_drift_monitor=True,
            cusum_k=0.5, cusum_h=5.0
        )
        pipeline = FactorProcessingPipelineV2(config)
        np.random.seed(42)
        # 无漂移数据
        data = np.random.normal(0, 1, (200, 50))
        factor_data = {'f1': pd.DataFrame(data)}
        result = pipeline.monitor_cusum_drift(factor_data)
        # 无漂移, 应不触发 (h=5σ, ARL₀≈930, 200 期大概率不触发)
        assert result['mean']['detected'] is False
        assert result['std']['detected'] is False


# ============================================================
# 4. drift_alerts 集成测试
# ============================================================

class TestDriftAlertsIntegration:
    """drift_alerts: CUSUM 触发后标记"""

    def test_30_drift_alerts_populated(self):
        """CUSUM 触发后 drift_alerts 字典被填充"""
        config = PipelineV2Config(
            enable_cusum_drift_monitor=True,
            cusum_k=0.5, cusum_h=5.0
        )
        pipeline = FactorProcessingPipelineV2(config)
        np.random.seed(42)
        data = np.concatenate([
            np.random.normal(0, 1, (100, 50)),
            np.random.normal(3, 1, (100, 50)),
        ], axis=0)
        factor_data = {'f1': pd.DataFrame(data)}
        pipeline.monitor_cusum_drift(factor_data)
        # drift_alerts 应有记录
        assert hasattr(pipeline, 'drift_alerts')
        assert len(pipeline.drift_alerts) > 0
        # 应标记 'cusum_mean' 或 'cusum_std'
        alert_keys = list(pipeline.drift_alerts.keys())
        assert any('cusum' in k for k in alert_keys)

    def test_31_no_drift_no_alerts(self):
        """无漂移时 drift_alerts 为空"""
        config = PipelineV2Config(
            enable_cusum_drift_monitor=True,
            cusum_k=0.5, cusum_h=5.0
        )
        pipeline = FactorProcessingPipelineV2(config)
        np.random.seed(42)
        data = np.random.normal(0, 1, (200, 50))
        factor_data = {'f1': pd.DataFrame(data)}
        pipeline.monitor_cusum_drift(factor_data)
        assert len(pipeline.drift_alerts) == 0


# ============================================================
# 5. 向后兼容测试
# ============================================================

class TestBackwardCompatibility:
    """向后兼容: enable_cusum_drift_monitor=False 不影响现有功能"""

    def test_40_disabled_fit_transform_unchanged(self):
        """禁用 CUSUM 时 fit/transform 行为不变"""
        config = PipelineV2Config(enable_cusum_drift_monitor=False)
        pipeline = FactorProcessingPipelineV2(config)
        # 应无 cusum_monitors 属性或为空
        assert not getattr(pipeline, 'cusum_monitors', {})

    def test_41_disabled_monitor_returns_empty(self):
        """禁用时 monitor_cusum_drift 返回空"""
        config = PipelineV2Config(enable_cusum_drift_monitor=False)
        pipeline = FactorProcessingPipelineV2(config)
        result = pipeline.monitor_cusum_drift({'f1': pd.DataFrame(np.random.randn(10, 5))})
        assert result == {} or result is None
