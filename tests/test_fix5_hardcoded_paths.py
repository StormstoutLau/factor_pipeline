# -*- coding: utf-8 -*-
"""
修复 5: 硬编码路径改为配置项 — TDD 测试

问题: 3 处硬编码路径散落于 backtest/ 模块中
  - data_bridge.py:31      Path("F:/Coding/Factor_Trading_v3.0")
  - cached_data_loader.py:64  Path("F:/Coding/Factor_DB")
  - health_bridge.py:39    Path("F:/Coding/Factor_Fingerprint")

修复方案:
  1. BacktestConfig 新增 3 个路径字段 (文档+可发现性)
  2. 模块级用 os.environ.get() 替代硬编码, 保留原默认值
  3. 环境变量可在部署时覆盖, 无需改代码

测试原则:
  - 验证默认值与原硬编码一致 (向后兼容)
  - 验证环境变量可覆盖
  - 验证 BacktestConfig 字段存在且可配置
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


class TestHardcodedPathsConfigurable(unittest.TestCase):
    """测试硬编码路径改为环境变量配置"""

    # ── 原硬编码值 (向后兼容基准) ──────────────────────
    ORIGINAL_FACTOR_TRADING = "F:/Coding/Factor_Trading_v3.0"
    ORIGINAL_FACTOR_DB = "F:/Coding/Factor_DB"
    ORIGINAL_FINGERPRINT = "F:/Coding/Factor_Fingerprint"

    # ==================================================================
    # 测试 1: BacktestConfig 包含外部路径字段
    # ==================================================================

    def test_01_backtest_config_has_path_fields(self):
        """[Red-01] BacktestConfig 新增 factor_trading_path / factor_db_path / fingerprint_path

        手工验证:
          - 3 个字段存在
          - 默认值与原硬编码一致
          - 可自定义
        """
        from factor_pipeline.config_v2 import BacktestConfig

        config = BacktestConfig()

        # 字段存在
        self.assertTrue(hasattr(config, 'factor_trading_path'),
                        "BacktestConfig 应有 factor_trading_path 字段")
        self.assertTrue(hasattr(config, 'factor_db_path'),
                        "BacktestConfig 应有 factor_db_path 字段")
        self.assertTrue(hasattr(config, 'fingerprint_path'),
                        "BacktestConfig 应有 fingerprint_path 字段")

        # 默认值与原硬编码一致
        self.assertEqual(str(config.factor_trading_path), self.ORIGINAL_FACTOR_TRADING)
        self.assertEqual(str(config.factor_db_path), self.ORIGINAL_FACTOR_DB)
        self.assertEqual(str(config.fingerprint_path), self.ORIGINAL_FINGERPRINT)

        # 可自定义
        custom = BacktestConfig(
            factor_trading_path="/custom/trading",
            factor_db_path="/custom/db",
            fingerprint_path="/custom/fp",
        )
        self.assertEqual(str(custom.factor_trading_path), "/custom/trading")
        self.assertEqual(str(custom.factor_db_path), "/custom/db")
        self.assertEqual(str(custom.fingerprint_path), "/custom/fp")

        print("[PASS] BacktestConfig 路径字段存在, 默认值正确, 可自定义")

    # ==================================================================
    # 测试 2: data_bridge.py 使用环境变量
    # ==================================================================

    def test_02_data_bridge_uses_env_var(self):
        """TD-1.4 (ADR-016): data_bridge.py 直接导入 DataLoaderV3, 不再用环境变量

        手工验证:
          - data_bridge 模块不再有 _FACTOR_TRADING_PATH 属性 (已删除)
          - DataLoaderV3 通过 from Factor_Trading_v3_0.core.data_v3 import 直接获取
        """
        from backtest import data_bridge

        # TD-1.4: _FACTOR_TRADING_PATH 已删除 (子包化后不再需要)
        self.assertFalse(
            hasattr(data_bridge, '_FACTOR_TRADING_PATH'),
            "TD-1.4 后 data_bridge 不应有 _FACTOR_TRADING_PATH 属性 (已子包化)"
        )

        # DataLoaderV3 应可通过直接导入获取
        self.assertTrue(
            hasattr(data_bridge, 'DataLoaderV3'),
            "data_bridge 应通过直接导入提供 DataLoaderV3"
        )

        print(f"[PASS] data_bridge 直接导入 DataLoaderV3 (TD-1.4, ADR-016)")

    # ==================================================================
    # 测试 3: data_bridge 环境变量覆盖 (子进程)
    # ==================================================================

    def test_03_data_bridge_env_var_override(self):
        """TD-1.4 (ADR-016): data_bridge.py 源码用直接导入替代 importlib hack

        手工验证:
          - 源码含 from Factor_Trading_v3_0.core.data_v3 import
          - 源码不再含 importlib.util.spec_from_file_location
        """
        import inspect
        from backtest import data_bridge

        src = inspect.getsource(data_bridge)
        self.assertIn('from Factor_Trading_v3_0.core.data_v3 import', src,
                        "data_bridge.py 应使用直接导入 DataLoaderV3")
        self.assertNotIn('spec_from_file_location', src,
                         "data_bridge.py 不应再使用 importlib.util.spec_from_file_location hack")

        print("[PASS] data_bridge.py 直接导入 DataLoaderV3 (TD-1.4, ADR-016)")

    # ==================================================================
    # 测试 4: cached_data_loader.py 使用环境变量
    # ==================================================================

    def test_04_cached_data_loader_uses_env_var(self):
        """P1.2 后: cached_data_loader.py 直接导入 Factor_DB, 无需环境变量

        手工验证:
          - _default_price_query_factory 使用 from Factor_DB.query.price_query import
          - 不再含 sys.path.insert / os.environ.get 等黑魔法
        """
        import subprocess

        result = subprocess.run(
            [
                sys.executable, "-c",
                f"""
import sys
sys.path.insert(0, r'{_PROJECT_ROOT}')
from backtest import cached_data_loader
import inspect
src = inspect.getsource(cached_data_loader._default_price_query_factory)
# P1.2: 应使用直接导入
print('from Factor_DB.query.price_query import PriceQuery' in src)
                """
            ],
            capture_output=True, text=True, timeout=30,
        )
        output = result.stdout.strip()
        self.assertEqual(output, 'True',
                         f"_default_price_query_factory 应使用直接导入, src检查: {output}\n"
                         f"stderr: {result.stderr[:500]}")

        print("[PASS] cached_data_loader 使用直接导入 (P1.2)")

    # ==================================================================
    # 测试 5: health_bridge.py 直接导入 (P1.2 后)
    # ==================================================================

    def test_05_health_bridge_uses_env_var(self):
        """P1.2 后: health_bridge.py 直接导入 Factor_Fingerprint, 无需环境变量

        手工验证:
          - 模块使用 from factor_pipeline.modules.factor_fingerprint.core.health import
          - 不再有 _FINGERPRINT_PATH 模块常量
        """
        from backtest import health_bridge

        # P1.2: 不应有 _FINGERPRINT_PATH 属性 (已删除)
        self.assertFalse(
            hasattr(health_bridge, '_FINGERPRINT_PATH'),
            "P1.2 后 health_bridge 不应有 _FINGERPRINT_PATH 属性"
        )

        # 应能直接导入 FactorHealthMonitor
        self.assertTrue(
            hasattr(health_bridge, 'FactorHealthMonitor'),
            "health_bridge 应通过直接导入提供 FactorHealthMonitor"
        )

        print(f"[PASS] health_bridge 使用直接导入 (P1.2)")

    # ==================================================================
    # 测试 6: 无残留硬编码 (源码检查)
    # ==================================================================

    def test_06_no_hardcoded_paths_in_source(self):
        """[Red-06] 3 个文件中不应再有直接硬编码路径字面量

        手工验证:
          - data_bridge.py 不含 Path("F:/Coding/Factor_Trading_v3.0") 字面量
          - cached_data_loader.py 不含 Path("F:/Coding/Factor_DB") 字面量
          - health_bridge.py 不含 Path("F:/Coding/Factor_Fingerprint") 字面量
        """
        import inspect
        from backtest import data_bridge, cached_data_loader, health_bridge

        # data_bridge.py 源码
        src_db = inspect.getsource(data_bridge)
        # 不应直接出现硬编码 (应通过 os.environ.get 引用)
        self.assertNotIn(
            'Path("F:/Coding/Factor_Trading_v3.0")',
            src_db,
            "data_bridge.py 不应直接硬编码 Factor_Trading_v3.0 路径"
        )

        # cached_data_loader.py 源码
        src_cdl = inspect.getsource(cached_data_loader)
        self.assertNotIn(
            'Path("F:/Coding/Factor_DB")',
            src_cdl,
            "cached_data_loader.py 不应直接硬编码 Factor_DB 路径"
        )

        # health_bridge.py 源码
        src_hb = inspect.getsource(health_bridge)
        self.assertNotIn(
            'Path("F:/Coding/Factor_Fingerprint")',
            src_hb,
            "health_bridge.py 不应直接硬编码 Factor_Fingerprint 路径"
        )

        print("[PASS] 3 个文件均无直接硬编码路径字面量")


if __name__ == '__main__':
    unittest.main(verbosity=2)
