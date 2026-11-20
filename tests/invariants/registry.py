# -*- coding: utf-8 -*-
"""v3.9.0 不变量注册表（DESIGN §5）。

注册在模块导入期完成；`run_all` 结果缓存（面板与断言均只读）。
"""
from dataclasses import dataclass
from typing import Callable, List, Tuple

from tests.synthetic import SCENARIOS, SyntheticPanel, build_panel

_KINDS = ("bound", "monotonic", "invariant", "equivalence")

__all__ = ["Invariant", "INVARIANTS", "register", "run_all", "get_panel"]


@dataclass(frozen=True)
class Invariant(object):
    name: str
    module: str
    kind: str
    scenario: str
    check: Callable[[SyntheticPanel], Tuple[bool, str]]


INVARIANTS = []  # type: List[Invariant]

_PANEL_CACHE = {}
_RESULT_CACHE = None


def register(inv):
    """注册一条不变量；重名/未知 kind/未知 scenario → ValueError。"""
    if not isinstance(inv, Invariant):
        raise TypeError("register 仅接受 Invariant (实际 %r)" % (type(inv),))
    if inv.name in {item.name for item in INVARIANTS}:
        raise ValueError("重复的不变量名: %s" % inv.name)
    if inv.kind not in _KINDS:
        raise ValueError("未知 kind=%r（允许 %r）" % (inv.kind, _KINDS))
    if inv.scenario not in SCENARIOS:
        raise ValueError("未知 scenario=%r（允许 %r）"
                         % (inv.scenario, tuple(SCENARIOS)))
    INVARIANTS.append(inv)
    return inv


def get_panel(name):
    """按场景名缓存面板（frozen dataclass + 只读约定）。"""
    if name not in _PANEL_CACHE:
        _PANEL_CACHE[name] = build_panel(SCENARIOS[name])
    return _PANEL_CACHE[name]


def run_all(panel_factory=None):
    """逐条执行全部不变量，返回 [(name, ok, detail)]（结果缓存）。"""
    global _RESULT_CACHE
    if _RESULT_CACHE is None:
        results = []
        for inv in INVARIANTS:
            try:
                panel = (panel_factory(inv.scenario) if panel_factory
                         else get_panel(inv.scenario))
                ok, detail = inv.check(panel)
                ok = bool(ok)
            except Exception as exc:  # noqa: BLE001 - 不变量失败需可定位
                ok, detail = False, "%s: %s" % (type(exc).__name__, exc)
            results.append((inv.name, ok, detail))
        _RESULT_CACHE = results
    return _RESULT_CACHE
