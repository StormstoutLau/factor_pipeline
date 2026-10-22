# -*- coding: utf-8 -*-
"""
Fix 3: 版本号统一 — TDD 测试

问题 (历史): 项目版本号曾散落于多处且不一致
  - __init__.py:        __version__ = "2.0.0"
  - config_v2.py:       version = "2.1.0"
  - reporting.py:       pipeline_version = "2.0.0"
  - test_config_v2.py:  期望 '2.0.0' (历史失败)
  - test_reporting.py:  期望 "2.0.0"

统一目标 (v3.3.3, 2026-10-22): 四处声明保持一致
  - __init__.py / config_v2.py / reporting.py / pyproject.toml
  - 缓存 code_version = "v2.2.1-cache" (缓存语义版本, 非项目版本;
    因 PL-01 去极值算法变更需失效旧缓存而 bump, 仍不跟随项目版本)
  - 本文件的 EXPECTED_VERSION 是唯一绝对锚点; 其余字段级测试比对本值而非字面量,
    避免每处各存一个字面量 (上一轮 2.5.0 就是这样漂移的)
"""

import unittest
import sys
from pathlib import Path

_PROJECT_PARENT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_PARENT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_PARENT))
for ext in ["F:/Coding/Factor_Fingerprint", "F:/Coding/Factor_Decoupler"]:
    if ext not in sys.path:
        sys.path.insert(0, ext)

# 期望的统一版本号
EXPECTED_VERSION = "3.3.3"


class TestFix3VersionUnification(unittest.TestCase):
    """Fix 3: 版本号统一测试"""

    def test_01_project_version_is_unified(self):
        """test_01: 项目主版本号 __version__ 统一到 3.3.3"""
        import factor_pipeline
        self.assertEqual(
            factor_pipeline.__version__, EXPECTED_VERSION,
            f"__version__ 应为 {EXPECTED_VERSION}, 实际为 {factor_pipeline.__version__}"
        )

    def test_02_unified_config_version_default(self):
        """test_02: PipelineV2ConfigUnified.version 默认值为 3.3.3"""
        from factor_pipeline.config_v2 import PipelineV2ConfigUnified
        config = PipelineV2ConfigUnified()
        self.assertEqual(
            config.version, EXPECTED_VERSION,
            f"PipelineV2ConfigUnified.version 默认值应为 {EXPECTED_VERSION}, 实际为 {config.version}"
        )

    def test_03_reporting_pipeline_version_default(self):
        """test_03: PipelineExecutionReport.pipeline_version 默认值为 3.3.3"""
        from factor_pipeline.reporting import PipelineExecutionReport
        report = PipelineExecutionReport()
        self.assertEqual(
            report.pipeline_version, EXPECTED_VERSION,
            f"pipeline_version 默认值应为 {EXPECTED_VERSION}, 实际为 {report.pipeline_version}"
        )

    def test_04_all_versions_consistent(self):
        """test_04: 所有三处版本号一致"""
        import factor_pipeline
        from factor_pipeline.config_v2 import PipelineV2ConfigUnified
        from factor_pipeline.reporting import PipelineExecutionReport

        v1 = factor_pipeline.__version__
        v2 = PipelineV2ConfigUnified().version
        v3 = PipelineExecutionReport().pipeline_version

        self.assertEqual(v1, v2, f"__version__({v1}) != Unified.version({v2})")
        self.assertEqual(v2, v3, f"Unified.version({v2}) != pipeline_version({v3})")
        self.assertEqual(v1, EXPECTED_VERSION, f"统一版本号应为 {EXPECTED_VERSION}")

    def test_05_cache_code_version_independent(self):
        """test_05: 缓存 code_version 为 'v2.2.1-cache' (缓存语义版本)

        缓存 code_version 用于缓存失效, 不跟随项目版本号变化.
        仅当缓存格式/计算逻辑变更时 bump: PL-01 将去极值从全 panel
        改为逐日截面, 旧缓存数值失效, 故 v2.2.0-cache → v2.2.1-cache.
        """
        from factor_pipeline.backtest.cached_data_loader import CachedDataLoader
        import inspect

        # 检查默认参数值 (不实例化, 避免依赖外部模块)
        sig = inspect.signature(CachedDataLoader.__init__)
        code_version_default = sig.parameters['code_version'].default
        self.assertEqual(
            code_version_default, "v2.2.1-cache",
            f"缓存 code_version 应为 'v2.2.1-cache', 实际为 {code_version_default!r}"
        )

    def test_07_all_cache_code_versions_consistent(self):
        """test_07: 5 处缓存 code_version 默认值必须一致

        防止只 bump 其中一部分: 任一遗漏都会让旧代缓存继续命中.
        """
        import inspect
        from factor_pipeline.backtest.cache_manager import CacheManager, CODE_VERSION
        from factor_pipeline.backtest.cached_data_loader import CachedDataLoader
        from factor_pipeline.backtest.factor_cache import FactorMatrixCache
        from factor_pipeline.backtest.price_cache import PriceMatrixCache
        from factor_pipeline.backtest.fwd_returns_cache import FwdReturnsCache

        expected = "v2.2.1-cache"
        self.assertEqual(CODE_VERSION, expected, "cache_manager.CODE_VERSION 不一致")

        for cls in (CacheManager, CachedDataLoader, FactorMatrixCache,
                    PriceMatrixCache, FwdReturnsCache):
            default = inspect.signature(cls.__init__).parameters['code_version'].default
            self.assertEqual(
                default, expected,
                f"{cls.__name__}.__init__ 的 code_version 默认值为 {default!r}, 应为 {expected!r}"
            )

    def test_06_pyproject_version_matches_package(self):
        """test_06: pyproject.toml 的 project.version 与 __version__ 一致.

        pyproject 是唯一无法通过 import 校验的声明点 (静态元数据), 也正是历史上
        长期停在 2.5.0 而 CHANGELOG 已到 3.3.x 的那个缺口. 此测试消除该类漂移.

        用正则解析而非 tomllib: requires-python >= 3.9, 而 tomllib 需 3.11+.
        """
        import re
        import factor_pipeline

        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        self.assertTrue(pyproject.exists(), f"未找到 pyproject.toml: {pyproject}")

        text = pyproject.read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        self.assertIsNotNone(match, "pyproject.toml 未找到 version 字段")

        declared = match.group(1)
        self.assertEqual(
            declared, factor_pipeline.__version__,
            f"pyproject.toml version({declared}) != __version__({factor_pipeline.__version__})"
        )
        self.assertEqual(declared, EXPECTED_VERSION)


if __name__ == '__main__':
    unittest.main(verbosity=2)
