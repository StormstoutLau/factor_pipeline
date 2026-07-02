# -*- coding: utf-8 -*-
"""
Fix 4: backtest/__init__.py 补全导出 — TDD 测试

问题: backtest/__init__.py 为空, 用户无法 from backtest import XxxClass
      必须写 from backtest.engine import FactorBacktestEngine 等长路径

修复: 在 __init__.py 导出关键公开 API
"""

import unittest
import sys
from pathlib import Path

# F:\Coding — 使 factor_pipeline 可作为包导入 (pytest 从 F:\Coding 运行时已自动添加)
_PROJECT_PARENT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_PARENT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_PARENT))
# F:\Coding\factor_pipeline — 使 backtest 子包可直接导入 (与 test_fix5 模式一致)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
for ext in ["F:/Coding/Factor_Fingerprint", "F:/Coding/Factor_Decoupler"]:
    if ext not in sys.path:
        sys.path.insert(0, ext)


class TestFix4BacktestInitExports(unittest.TestCase):
    """Fix 4: backtest/__init__.py 补全导出测试"""

    def test_01_cache_classes_importable(self):
        """test_01: 缓存相关类可从 backtest 包直接导入"""
        from backtest import (
            CachedDataLoader,
            FactorMatrixCache,
            PriceMatrixCache,
            FwdReturnsCache,
            CacheManager,
        )
        self.assertIsNotNone(CachedDataLoader)
        self.assertIsNotNone(FactorMatrixCache)
        self.assertIsNotNone(PriceMatrixCache)
        self.assertIsNotNone(FwdReturnsCache)
        self.assertIsNotNone(CacheManager)

    def test_02_engine_and_bridge_importable(self):
        """test_02: 引擎与桥接类可从 backtest 包直接导入"""
        from backtest import (
            FactorBacktestEngine,
            DataBridge,
            FactorPivotAdapter,
            HealthMonitorAdapter,
            UnifiedDriftReporter,
        )
        self.assertIsNotNone(FactorBacktestEngine)
        self.assertIsNotNone(DataBridge)
        self.assertIsNotNone(FactorPivotAdapter)
        self.assertIsNotNone(HealthMonitorAdapter)
        self.assertIsNotNone(UnifiedDriftReporter)

    def test_03_runner_classes_importable(self):
        """test_03: 并行与集成运行器可从 backtest 包直接导入"""
        from backtest import (
            ParallelFactorRunner,
            PipelineBacktestRunner,
            run_parallel,
        )
        self.assertIsNotNone(ParallelFactorRunner)
        self.assertIsNotNone(PipelineBacktestRunner)
        self.assertIsNotNone(run_parallel)

    def test_04_factor_metrics_functions_importable(self):
        """test_04: 因子指标函数可从 backtest 包直接导入"""
        from backtest import (
            compute_rank_ic,
            compute_pearson_ic,
            compute_ic_series,
            compute_icir,
            compute_ic_decay,
            compute_turnover,
            compute_long_short_returns,
            compute_spread,
            compute_hit_rate,
        )
        for fn in [compute_rank_ic, compute_pearson_ic, compute_ic_series,
                   compute_icir, compute_ic_decay, compute_turnover,
                   compute_long_short_returns, compute_spread, compute_hit_rate]:
            self.assertTrue(callable(fn), f"{fn} 应为可调用对象")

    def test_05_all_list_defined(self):
        """test_05: __all__ 列表已定义且包含关键 API"""
        import backtest
        self.assertTrue(hasattr(backtest, '__all__'), "__all__ 应已定义")
        expected = [
            'CachedDataLoader', 'FactorMatrixCache', 'PriceMatrixCache',
            'FwdReturnsCache', 'CacheManager', 'FactorBacktestEngine',
            'DataBridge', 'FactorPivotAdapter', 'HealthMonitorAdapter',
            'UnifiedDriftReporter', 'ParallelFactorRunner',
            'PipelineBacktestRunner', 'run_parallel',
            'compute_rank_ic', 'compute_pearson_ic', 'compute_ic_series',
            'compute_icir', 'compute_ic_decay', 'compute_turnover',
            'compute_long_short_returns', 'compute_spread', 'compute_hit_rate',
        ]
        for name in expected:
            self.assertIn(name, backtest.__all__, f"{name} 应在 __all__ 中")


if __name__ == '__main__':
    unittest.main(verbosity=2)
