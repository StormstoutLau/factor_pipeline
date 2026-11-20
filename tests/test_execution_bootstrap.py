# -*- coding: utf-8 -*-
"""v3.8.0 E0 — 自动块长（T380-35 ~ T380-40）。

红形态：``ModuleNotFoundError: backtest.execution.core.bootstrap``。
"""
import numpy as np


def _ar1(n, rho, seed=0):
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    for t in range(1, n):
        x[t] = rho * x[t - 1] + rng.normal(0.0, 1.0)
    return x


def test_near_iid_block_one():
    """T380-35: rho≈0 -> b=1。"""
    from backtest.execution.core.bootstrap import auto_block_size
    x = np.random.default_rng(1).normal(0.0, 1.0, 500)
    assert auto_block_size(x) == 1


def test_block_grows_with_rho():
    """T380-36: b(rho=0.6) > b(rho=0.2)。"""
    from backtest.execution.core.bootstrap import auto_block_size
    x_hi = _ar1(500, 0.6, seed=2)
    x_lo = _ar1(500, 0.2, seed=2)
    assert auto_block_size(x_hi) > auto_block_size(x_lo)


def test_block_upper_bound():
    """T380-37: b <= n//3。"""
    from backtest.execution.core.bootstrap import auto_block_size
    x = _ar1(30, 0.9, seed=3)
    b = auto_block_size(x)
    assert b <= max(1, x.size // 3)


def test_block_lower_bound():
    """T380-38: b >= 1。"""
    from backtest.execution.core.bootstrap import auto_block_size
    for rho in (0.0, 0.3, 0.7, 0.95):
        assert auto_block_size(_ar1(200, rho, seed=4)) >= 1


def test_block_vs_sqrt_same_order():
    """T380-39: 与 sqrt(T) 同量级（比值 ∈ [0.2, 5]）。"""
    from backtest.execution.core.bootstrap import auto_block_size
    x = _ar1(400, 0.5, seed=5)
    b = auto_block_size(x)
    ratio = b / np.sqrt(x.size)
    assert 0.2 <= ratio <= 5.0


def test_block_deterministic():
    """T380-40: 同输入两次调用逐位一致。"""
    from backtest.execution.core.bootstrap import auto_block_size
    x = _ar1(300, 0.4, seed=6)
    assert auto_block_size(x) == auto_block_size(x)
