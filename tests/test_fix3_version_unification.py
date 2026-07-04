# -*- coding: utf-8 -*-
"""
Fix 3: 版本号统一 — TDD 测试

问题: 项目版本号散落于多处且不一致
  - __init__.py:        __version__ = "2.0.0"
  - config_v2.py:       version = "2.1.0"
  - reporting.py:       pipeline_version = "2.0.0"
  - test_config_v2.py:  期望 '2.0.0' (历史失败)
  - test_reporting.py:  期望 "2.0.0"

修复: 统一到 "2.5.0" (v2.5.0 ADR-020 多因子正交化模块版本)
  - 缓存 code_version = "v2.2.0-cache" 保持不变 (缓存语义版本, 非项目版本)
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
EXPECTED_VERSION = "2.5.0"


class TestFix3VersionUnification(unittest.TestCase):
    """Fix 3: 版本号统一测试"""

    def test_01_project_version_is_unified(self):
        """test_01: 项目主版本号 __version__ 统一到 2.5.0"""
        import factor_pipeline
        self.assertEqual(
            factor_pipeline.__version__, EXPECTED_VERSION,
            f"__version__ 应为 {EXPECTED_VERSION}, 实际为 {factor_pipeline.__version__}"
        )

    def test_02_unified_config_version_default(self):
        """test_02: PipelineV2ConfigUnified.version 默认值为 2.5.0"""
        from factor_pipeline.config_v2 import PipelineV2ConfigUnified
        config = PipelineV2ConfigUnified()
        self.assertEqual(
            config.version, EXPECTED_VERSION,
            f"PipelineV2ConfigUnified.version 默认值应为 {EXPECTED_VERSION}, 实际为 {config.version}"
        )

    def test_03_reporting_pipeline_version_default(self):
        """test_03: PipelineExecutionReport.pipeline_version 默认值为 2.5.0"""
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

    def test_05_cache_code_version_unchanged(self):
        """test_05: 缓存 code_version 保持 'v2.2.0-cache' 不变 (缓存语义版本)

        缓存 code_version 用于缓存失效, 不应跟随项目版本号变化.
        只有当缓存格式/逻辑发生破坏性变更时才应更新.
        """
        from factor_pipeline.backtest.cached_data_loader import CachedDataLoader
        import inspect

        # 检查默认参数值 (不实例化, 避免依赖外部模块)
        sig = inspect.signature(CachedDataLoader.__init__)
        code_version_default = sig.parameters['code_version'].default
        self.assertEqual(
            code_version_default, "v2.2.0-cache",
            f"缓存 code_version 应保持 'v2.2.0-cache', 实际为 {code_version_default!r}"
        )


if __name__ == '__main__':
    unittest.main(verbosity=2)
