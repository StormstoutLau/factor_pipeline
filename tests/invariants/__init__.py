# -*- coding: utf-8 -*-
"""v3.9.0 不变量包：导入即注册（副作用），避免 pytest 收集顺序依赖。"""
from .registry import INVARIANTS, Invariant, get_panel, register, run_all
from . import backtest_engine  # noqa: F401,E402
from . import factor_metrics  # noqa: F401,E402
from . import data_bridge  # noqa: F401,E402
from . import execution_core  # noqa: F401,E402
from . import winsor  # noqa: F401,E402

__all__ = ["INVARIANTS", "Invariant", "register", "run_all", "get_panel"]
