# -*- coding: utf-8 -*-
"""Fix 7: core 命名空间碰撞 — TDD 测试

复现并验证修复:
  - data_bridge.py 用 spec_from_file_location("core.data_v3", ...) 注册了
    "core" 命名空间包, 指向 Factor_Trading_v3.0/core
  - 这会遮蔽 Factor_DB/core, 导致 from core.connection import DuckDBConnection 失败
  - 全量回归测试时, 其他测试先触发 backtest 导入, 再跑 test_p0_duckdb_pivot.py
    就会 ModuleNotFoundError: No module named 'core.connection'

修复方案: 将模块名改为 "_factor_trading_data_v3", 避免注册 "core" 命名空间。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ── sys.path 准备 ─────────────────────────────────────────────
_PROJECT_PARENT = Path(__file__).resolve().parent.parent.parent  # F:\Coding
_FACTOR_DB_PATH = _PROJECT_PARENT / "Factor_DB"

if str(_PROJECT_PARENT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_PARENT))
if str(_FACTOR_DB_PATH) not in sys.path:
    sys.path.insert(0, str(_FACTOR_DB_PATH))


# =============================================================================
# Test 1: 导入 backtest 不应遮蔽 Factor_DB/core
# =============================================================================

class TestCoreNamespaceIsolation:
    """验证 backtest 导入后, Factor_DB 的 core 仍可访问"""

    def test_factor_db_core_connection_importable_after_backtest(self):
        """P1.2 后: 导入 backtest 后, Factor_DB.core.connection 仍可用"""
        # 触发 backtest 导入 (P1.2 后不再操纵 core 命名空间)
        import factor_pipeline.backtest  # noqa: F401

        # 现在 Factor_DB.core.connection 必须仍可导入
        from Factor_DB.core.connection import DuckDBConnection  # noqa: F401

    def test_data_bridge_module_name_not_core_prefixed(self):
        """data_bridge.py 注册的模块名不应以 'core' 开头"""
        import importlib
        # 清理可能存在的旧注册
        for key in list(sys.modules.keys()):
            if key.startswith("core.data_v3") or key == "_factor_trading_data_v3":
                # 先不删除, 仅检查
                pass

        # 重新触发 data_bridge 导入 (已导入则直接取)
        from factor_pipeline.backtest import data_bridge

        # 检查 sys.modules 中不应有 "core.data_v3" 这个注册
        # (因为 data_bridge 应该用 _factor_trading_data_v3 注册)
        assert "core.data_v3" not in sys.modules, (
            "data_bridge.py 仍用 'core.data_v3' 注册模块, 会遮蔽 Factor_DB/core"
        )


# =============================================================================
# Test 2: DataLoaderV3 仍可正常加载
# =============================================================================

class TestDataLoaderV3StillWorks:
    """修复后 DataLoaderV3 仍能正常导入和使用"""

    def test_data_loader_v3_class_available(self):
        """DataLoaderV3 通过 lazy import 可用 (需安装 Factor_Trading_v3_0)"""
        # 可选依赖: Factor_Trading_v3_0 (pyproject.toml [backtest] extra)
        # 未安装时跳过此测试, 仅在已安装环境下验证 DataLoaderV3 类可用性.
        pytest.importorskip("Factor_Trading_v3_0")
        from Factor_Trading_v3_0.core.data_v3 import DataLoaderV3
        assert DataLoaderV3 is not None
        assert hasattr(DataLoaderV3, "from_pandas_dataframes")

    def test_data_bridge_class_available(self):
        """DataBridge 类可正常导入"""
        from factor_pipeline.backtest.data_bridge import DataBridge
        assert DataBridge is not None
        bridge = DataBridge()
        assert bridge is not None


# =============================================================================
# Test 3: 全量回归场景 — Factor_DB 查询可用
# =============================================================================

class TestFactorDBQueryStillWorks:
    """全量回归场景下, Factor_DB 的查询接口仍可用"""

    def test_factor_query_importable_after_backtest(self):
        """导入 backtest 后, Factor_DB 的 FactorQuery 仍可用"""
        import factor_pipeline.backtest  # noqa: F401
        from Factor_DB.query.factor_query import FactorQuery  # noqa: F401

    def test_base_query_importable(self):
        """Factor_DB/query/base.py 的导入链不破坏"""
        import factor_pipeline.backtest  # noqa: F401
        from Factor_DB.query.base import BaseQuery  # noqa: F401
