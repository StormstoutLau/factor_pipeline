# -*- coding: utf-8 -*-
"""Fix 7 补充: 导入顺序约束固化测试

验证 backtest/__init__.py 的导入顺序约束:
  - Fix 7 修复后, data_bridge 不再注册 core 命名空间
  - health_bridge 加载完 core.fingerprint/health 后清理 sys.modules['core']
  - 因此导入顺序不再敏感, 任意顺序都应正确

测试场景:
  1. __init__.py 导入顺序记录 (当前顺序, 非强制约束)
  2. data_bridge 单独加载, 不破坏 core 命名空间
  3. health_bridge 单独加载, 加载后清理 core
  4. 任意顺序加载后, Factor_DB/core 仍可访问
  5. reload 幂等性
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_PROJECT_PARENT = Path(__file__).resolve().parent.parent.parent  # F:\Coding
_FACTOR_DB_PATH = _PROJECT_PARENT / "Factor_DB"

if str(_PROJECT_PARENT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_PARENT))
if str(_FACTOR_DB_PATH) not in sys.path:
    sys.path.insert(0, str(_FACTOR_DB_PATH))


# =============================================================================
# Test 1: __init__.py 导入顺序记录
# =============================================================================

class TestInitImportOrder:
    """__init__.py 导入顺序记录 (非强制约束, 但记录当前状态)"""

    def test_init_imports_both_modules(self):
        """__init__.py 导入了 data_bridge 和 health_bridge"""
        init_path = _PROJECT_PARENT / "factor_pipeline" / "backtest" / "__init__.py"
        content = init_path.read_text(encoding='utf-8')
        assert "from .data_bridge import" in content, "未导入 data_bridge"
        assert "from .health_bridge import" in content, "未导入 health_bridge"

    def test_data_bridge_does_not_register_core(self):
        """data_bridge 模块名不含 'core' 前缀, 不注册 core 命名空间"""
        db_path = _PROJECT_PARENT / "factor_pipeline" / "backtest" / "data_bridge.py"
        content = db_path.read_text(encoding='utf-8')
        # TD-1.4: 应使用 Factor_Trading_v3_0.core.data_v3 直接导入 (子包化后命名空间隔离)
        assert "from Factor_Trading_v3_0.core.data_v3 import" in content, (
            "data_bridge 应使用 'from Factor_Trading_v3_0.core.data_v3 import' 直接导入"
        )
        # 不应使用 bare 'from core.' 导入 (会注册 sys.modules['core'])
        assert "from core.data_v3 import" not in content, (
            "data_bridge 不应使用 bare 'from core.data_v3 import' (会注册 core 命名空间)"
        )
        # 不应残留 importlib 动态加载 hack
        assert "spec_from_file_location" not in content, (
            "data_bridge 不应残留 importlib spec_from_file_location hack"
        )

    def test_health_bridge_cleans_core_after_load(self):
        """P1.2 后: health_bridge 不再操纵 core 命名空间 (直接导入 Factor_Fingerprint)"""
        hb_path = _PROJECT_PARENT / "factor_pipeline" / "backtest" / "health_bridge.py"
        content = hb_path.read_text(encoding='utf-8')
        # P1.2: 应使用直接导入, 不应有 sys.modules['core'] 操作
        assert "from factor_pipeline.modules.factor_fingerprint.core.health import" in content, (
            "health_bridge 应使用 from factor_pipeline.modules.factor_fingerprint.core.health import"
        )
        assert "sys.modules['core']" not in content, (
            "P1.2 后 health_bridge 不应操作 sys.modules['core']"
        )


# =============================================================================
# Test 2: data_bridge 单独加载不破坏 core 命名空间
# =============================================================================

class TestDataBridgeIsolation:
    """data_bridge 单独加载不应注册或破坏 core 命名空间"""

    def test_data_bridge_no_core_in_sys_modules(self):
        """加载 data_bridge 后, sys.modules 中无 'core' 键 (除非已存在)"""
        # 记录加载前状态
        core_before = sys.modules.get('core')
        # data_bridge 已通过 backtest 导入, 这里直接检查
        from factor_pipeline.backtest import data_bridge
        # TD-1.4: data_bridge 不应在 sys.modules 注册 bare 'core'
        # (它用 Factor_Trading_v3_0.core.data_v3 命名空间, 不碰 bare core)
        assert 'core.data_v3' not in sys.modules, (
            "data_bridge 不应注册 bare 'core.data_v3'"
        )

    def test_data_bridge_functional(self):
        """data_bridge 功能正常

        P1.2 重构后: DataLoaderV3 改为 lazy import, 通过 _ensure_dataloader 获取.
        - 未安装 Factor_Trading_v3_0: 跳过此测试
        - 已安装: 验证 lazy import 机制工作正常
        """
        # 可选依赖: Factor_Trading_v3_0 (pyproject.toml [backtest] extra)
        pytest.importorskip("Factor_Trading_v3_0")
        from Factor_Trading_v3_0.core.data_v3 import DataLoaderV3

        from factor_pipeline.backtest.data_bridge import DataBridge
        assert DataBridge is not None
        assert DataLoaderV3 is not None
        bridge = DataBridge()
        assert bridge is not None
        # lazy import 架构: 实例化时 _DataLoaderV3 应为 None
        assert bridge._DataLoaderV3 is None
        # _ensure_dataloader 应能成功 lazy load DataLoaderV3
        loaded = bridge._ensure_dataloader()
        assert loaded is DataLoaderV3


# =============================================================================
# Test 3: health_bridge 加载后清理 core
# =============================================================================

class TestHealthBridgeCleanup:
    """health_bridge 加载后应清理 sys.modules['core']"""

    def test_health_bridge_functional(self):
        """health_bridge 功能正常"""
        from factor_pipeline.backtest.health_bridge import (
            HealthMonitorAdapter, FactorHealthMonitor,
        )
        assert HealthMonitorAdapter is not None
        assert FactorHealthMonitor is not None

    def test_core_fingerprint_and_health_in_modules(self):
        """P1.2: factor_pipeline.modules.factor_fingerprint.core.health 在 sys.modules 中 (health_bridge 依赖)"""
        import factor_pipeline.backtest  # noqa: F401
        # v2.4.0 (ADR-019): 内化后路径从 Factor_Fingerprint.core.health 改为
        # factor_pipeline.modules.factor_fingerprint.core.health
        assert 'factor_pipeline.modules.factor_fingerprint.core.health' in sys.modules, (
            "factor_pipeline.modules.factor_fingerprint.core.health 未加载"
        )

    def test_core_not_pointing_to_fingerprint_after_load(self):
        """加载后 sys.modules['core'] 不应指向 Factor_Fingerprint/core"""
        import factor_pipeline.backtest  # noqa: F401
        # 若 sys.modules['core'] 存在, 其 __path__ 不应是 Factor_Fingerprint/core
        core_mod = sys.modules.get('core')
        if core_mod is not None:
            core_path = getattr(core_mod, '__path__', None)
            if core_path:
                for p in core_path:
                    assert 'Factor_Fingerprint' not in p, (
                        f"sys.modules['core'] 仍指向 Factor_Fingerprint/core: {p}"
                    )


# =============================================================================
# Test 4: 任意顺序加载后 Factor_DB/core 可访问
# =============================================================================

class TestArbitraryOrderAccess:
    """任意顺序加载后, Factor_DB/core 仍可访问"""

    def test_factor_db_core_after_backtest(self):
        """导入 backtest 后, Factor_DB.core 可访问"""
        import factor_pipeline.backtest  # noqa: F401
        from Factor_DB.core.connection import DuckDBConnection  # noqa: F401

    def test_factor_db_query_after_backtest(self):
        """导入 backtest 后, Factor_DB.query 可访问"""
        import factor_pipeline.backtest  # noqa: F401
        from Factor_DB.query.factor_query import FactorQuery  # noqa: F401
        from Factor_DB.query.base import BaseQuery  # noqa: F401

    def test_factor_db_core_path_correct(self):
        """P1.2 后: backtest 不再注册 core 命名空间, 直接通过 Factor_DB.core 访问"""
        import factor_pipeline.backtest  # noqa: F401
        from Factor_DB.core.connection import DuckDBConnection  # noqa: F401
        # P1.2: 不再使用 bare 'core', 验证 Factor_DB.core 已正确加载
        import Factor_DB.core as fdb_core
        assert fdb_core is not None, "Factor_DB.core 模块未加载"
        core_path = getattr(fdb_core, '__path__', None)
        assert core_path is not None, "Factor_DB.core 模块无 __path__"
        assert any('Factor_DB' in p for p in core_path), (
            f"Factor_DB.core __path__ 不指向 Factor_DB: {core_path}"
        )


# =============================================================================
# Test 5: reload 幂等性
# =============================================================================

class TestReloadIdempotent:
    """reload backtest 不产生副作用"""

    def test_reload_preserves_core_modules(self):
        """reload backtest 后, core 相关模块不丢失"""
        import factor_pipeline.backtest as bt

        # 记录 reload 前 core 相关键
        core_keys_before = set(k for k in sys.modules if k.startswith('core'))
        bt_keys_before = set(k for k in sys.modules if 'factor_pipeline.backtest' in k)

        # reload
        importlib.reload(bt)

        core_keys_after = set(k for k in sys.modules if k.startswith('core'))
        bt_keys_after = set(k for k in sys.modules if 'factor_pipeline.backtest' in k)

        # core 相关模块不应丢失
        lost_core = core_keys_before - core_keys_after
        assert not lost_core, f"reload 后 core 模块丢失: {lost_core}"

        # backtest 模块数应保持稳定
        assert len(bt_keys_after) >= len(bt_keys_before), (
            f"reload 后 backtest 模块数减少: {len(bt_keys_before)} → {len(bt_keys_after)}"
        )

    def test_reload_preserves_functionality(self):
        """reload 后功能仍正常"""
        import factor_pipeline.backtest as bt
        importlib.reload(bt)
        # 核心类仍可访问
        assert bt.FactorBacktestEngine is not None
        assert bt.DataBridge is not None
        assert bt.HealthMonitorAdapter is not None
        # Factor_DB/core 仍可访问
        from Factor_DB.core.connection import DuckDBConnection  # noqa: F401

    def test_multiple_reloads_stable(self):
        """多次 reload 后仍稳定"""
        import factor_pipeline.backtest as bt
        for i in range(3):
            importlib.reload(bt)
            assert bt.FactorBacktestEngine is not None
        # 最后一次 reload 后 Factor_DB.core 仍可访问
        from Factor_DB.core.connection import DuckDBConnection  # noqa: F401


# =============================================================================
# Test 6: 反向加载场景 (data_bridge 先, health_bridge 后 — 当前 __init__.py 顺序)
# =============================================================================

class TestCurrentOrderWorks:
    """当前 __init__.py 顺序 (data_bridge 先, health_bridge 后) 工作正常"""

    def test_current_order_factor_db_accessible(self):
        """当前顺序下 Factor_DB.core 可访问"""
        # backtest 已导入 (data_bridge 先, health_bridge 后)
        import factor_pipeline.backtest  # noqa: F401
        from Factor_DB.core.connection import DuckDBConnection  # noqa: F401
        from Factor_DB.query.factor_query import FactorQuery  # noqa: F401
