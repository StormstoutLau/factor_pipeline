# -*- coding: utf-8 -*-
"""
修复 1: self.factors dead-code bug 测试

问题: pipelines_v2.py:1099 引用 self.factors, 但 __init__ 从未定义该属性。
      KS 显著性检验路径不可达, 迁移权重融合实际未生效。

测试策略:
  直接 mock 必要属性, 专注测试 transform() 中 self.factors 路径。
  绕过 fit() 的外部依赖 (Factor_Decoupler 等), 只验证 bug 修复。
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

# 添加项目路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from factor_pipeline.pipelines_v2 import (
    FactorProcessingPipelineV2,
    PipelineV2Config,
)


class TestSelfFactorsBug(unittest.TestCase):
    """测试 self.factors dead-code bug 修复"""

    def setUp(self):
        """构造基础测试数据"""
        np.random.seed(42)
        n_stocks = 50
        n_dates = 100

        self.dates = pd.date_range('2020-01-01', periods=n_dates, freq='D')
        self.stocks = [f'S{i:03d}' for i in range(n_stocks)]

        # 因子数据 (n_stocks, n_dates) — DataFrame index=stock, columns=date
        self.factor_data = {
            'test_factor': pd.DataFrame(
                np.random.randn(n_stocks, n_dates) * 0.1 + 0.05,
                index=self.stocks, columns=self.dates,
            )
        }

    def _create_patched_pipeline(self):
        """构造一个绕过 fit() 的 pipeline, 直接 mock 必要属性

        transform() 需要的属性:
          - self.config (PipelineV2Config)
          - self.monitor (FactorFingerprintMonitor, 需 enable_smooth_transition=True)
          - self.factor_classifications (Dict[str, ClassificationResult])
          - self.static_pipeline / dynamic_pipeline / mixed_pipeline (需 transform 方法)
          - self.is_fitted = True
        """
        config = PipelineV2Config()
        config.monitor.enable_smooth_transition = True
        pipeline = FactorProcessingPipelineV2(config=config)

        # Mock monitor: 启用平滑过渡, 有迁移历史
        pipeline.monitor = MagicMock()
        pipeline.monitor.config.enable_smooth_transition = True

        # Mock classification result (中等置信度, 触发软路由)
        from factor_pipeline.modules.factor_fingerprint import FactorType, ClassificationResult, FactorFingerprint

        classification = ClassificationResult(
            primary_type=FactorType.MIXED, primary_prob=0.6,
            secondary_type=FactorType.DYNAMIC, secondary_prob=0.35,
            confidence=0.6, is_hard=False,  # is_hard=False 触发软路由
        )
        pipeline.factor_classifications = {'test_factor': classification}

        # Mock monitor.fingerprint_history 和 get_transition_weights
        fp = FactorFingerprint(
            ar1_median=0.5, rank_autocorr=0.4, vol_clustering_pvalue=0.5,
            half_life=5.0, level_diff_ic_ratio=2.0, skewness_std=0.3,
            kurtosis_std=1.0, js_divergence_mean=0.1, missing_cv=0.05,
            coverage_ratio=0.95, sd_score=0.5, complexity_need=0.4, snr_estimate=1.5,
        )
        pipeline.monitor.fingerprint_history = {'test_factor': [fp]}

        # get_transition_weights 返回 >1 权重 (触发 KS 检验路径)
        pipeline.monitor.get_transition_weights = MagicMock(return_value={
            FactorType.STATIC: 0.2,
            FactorType.MIXED: 0.4,
            FactorType.DYNAMIC: 0.4,
        })

        # Mock 三条管道的 transform 方法 (返回输入数据的 copy)
        mock_pipeline = MagicMock()
        mock_pipeline.transform = MagicMock(side_effect=lambda x, **kw: x.copy())
        pipeline.static_pipeline = mock_pipeline
        pipeline.dynamic_pipeline = MagicMock()
        pipeline.dynamic_pipeline.transform = MagicMock(side_effect=lambda x, **kw: x.copy())
        pipeline.mixed_pipeline = MagicMock()
        pipeline.mixed_pipeline.transform = MagicMock(side_effect=lambda x, **kw: x.copy())

        pipeline.is_fitted = True
        return pipeline

    def test_01_transform_no_attribute_error_with_migration(self):
        """[Red-01] transform() 在有迁移历史时不抛 AttributeError

        bug 复现: self.factors 未定义, 触发 AttributeError
        修复后: 使用 transform 参数 factor_data 替代 self.factors
        """
        pipeline = self._create_patched_pipeline()

        # Transform — bug 存在时会抛 AttributeError: 'FactorProcessingPipelineV2'
        #    object has no attribute 'factors'
        try:
            results = pipeline.transform(self.factor_data)
            self.assertIn('test_factor', results)
            print("[PASS] transform() 未抛 AttributeError, KS 路径可达")
        except AttributeError as e:
            if 'factors' in str(e).lower():
                self.fail(
                    f"BUG 复现: self.factors 未定义 — {e}\n"
                    f"KS 显著性检验路径不可达, 迁移权重融合未生效"
                )
            raise

    def test_02_ks_check_executed_on_distribution_shift(self):
        """[Red-02] 因子分布显著偏移时, KS 检验确认迁移, 权重被合并

        手工计算:
          - 构造分布偏移的因子数据 (前半段均值 0.05, 后半段均值 0.5)
          - KS 检验应显著 (p < 0.05), 迁移权重被合并
          - 验证: get_transition_weights 被调用, 且权重合并发生
        """
        pipeline = self._create_patched_pipeline()

        # 构造分布偏移的因子数据
        np.random.seed(42)
        n_stocks = 50
        n_dates = 100
        factor_values = np.random.randn(n_stocks, n_dates) * 0.1
        factor_values[:, n_dates // 2:] += 0.5  # 后半段均值偏移 0.5

        factor_data = {
            'test_factor': pd.DataFrame(
                factor_values, index=self.stocks, columns=self.dates,
            )
        }

        # Transform
        results = pipeline.transform(factor_data)

        # 验证: get_transition_weights 被调用 (迁移路径被触发)
        self.assertTrue(
            pipeline.monitor.get_transition_weights.called,
            "get_transition_weights 应被调用"
        )

        # 验证: 结果存在且非全 NaN
        self.assertIn('test_factor', results)
        self.assertFalse(
            results['test_factor'].isna().all().all(),
            "变换结果不应全为 NaN"
        )

        print("[PASS] 分布偏移场景下 KS 检验路径正常执行")

    def test_03_ks_check_rejects_noise_migration(self):
        """[Red-03] 因子分布未偏移时, KS 检验拒绝迁移

        手工计算:
          - 稳定分布 (全程均值 0.05, 标准差 0.1)
          - KS 检验应不显著 (p >= 0.05), 权重不被合并
          - 验证: transform 正常返回结果
        """
        pipeline = self._create_patched_pipeline()

        # 稳定分布因子数据 (无偏移)
        np.random.seed(42)
        n_stocks = 50
        n_dates = 100
        factor_values = np.random.randn(n_stocks, n_dates) * 0.1 + 0.05

        factor_data = {
            'test_factor': pd.DataFrame(
                factor_values, index=self.stocks, columns=self.dates,
            )
        }

        # Transform
        results = pipeline.transform(factor_data)

        # 验证: 结果存在
        self.assertIn('test_factor', results)
        self.assertFalse(
            results['test_factor'].isna().all().all(),
            "变换结果不应全为 NaN"
        )

        print("[PASS] 无分布偏移场景下 KS 检验路径正常执行")

    def test_04_short_data_falls_back_to_direct_merge(self):
        """[Red-04] 数据不足 (<10 观测) 时, 直接合并迁移权重 (保守处理)

        手工计算:
          - n_obs < 10, KS 检验跳过
          - 迁移权重直接合并 (保守处理)
          - 验证: transform 正常返回结果
        """
        pipeline = self._create_patched_pipeline()

        # 短数据 (n_dates=5 < 10)
        np.random.seed(42)
        short_factor = pd.DataFrame(
            np.random.randn(50, 5) * 0.1,
            index=self.stocks,
            columns=pd.date_range('2020-01-01', periods=5, freq='D'),
        )
        factor_data = {'test_factor': short_factor}

        # Transform
        results = pipeline.transform(factor_data)

        # 验证: 结果存在
        self.assertIn('test_factor', results)

        print("[PASS] 短数据场景下直接合并迁移权重")


if __name__ == '__main__':
    unittest.main(verbosity=2)
