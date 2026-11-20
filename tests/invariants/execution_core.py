# -*- coding: utf-8 -*-
"""I8-I11：一字板真值 / 冲击单调 / 半衰期恒等 / 块长界。"""
import numpy as np

from backtest.execution.core.bootstrap import auto_block_size
from backtest.execution.core.classification import detect_limit_lock
from backtest.execution.core.decay import half_life
from backtest.execution.core.impact import SqrtImpact

from .registry import Invariant, register


def check_i8(panel):
    got = detect_limit_lock(panel.high, panel.low, panel.close,
                            panel.open, panel.volume).reshape(panel.close.shape)
    expected = (panel.true_limit_hit != 0) | panel.true_suspend
    bad = np.argwhere(got != expected)
    if bad.size:
        t, i = int(bad[0][0]), int(bad[0][1])
        return False, "首个不等 (t,i)=(%d,%d) got=%r expected=%r" % (
            t, i, bool(got[t, i]), bool(expected[t, i]))
    # 防空断言：手工停牌 bar 必须命中、普通 bar 不得命中
    h = np.array([[1.0]])
    if not detect_limit_lock(h, h, h, h, np.array([[0.0]]))[0]:
        return False, "手工停牌 bar 未命中"
    if detect_limit_lock(np.array([[1.0]]), np.array([[0.9]]),
                         np.array([[0.96]]), np.array([[0.95]]),
                         np.array([[1e5]]))[0]:
        return False, "普通 bar 被误判"
    return True, "detect_limit_lock 与真值逐位一致"


def check_i9(panel):
    model = SqrtImpact()
    p = np.array([0.001, 0.005, 0.01, 0.02, 0.05])
    sigma = np.full(p.size, 0.02)
    y = model.predict(p, sigma, {"c": 0.5})
    if np.any(np.diff(y) < 0.0):
        return False, "关于 p 非单调: %r" % (np.diff(y),)
    sigma2 = np.array([0.005, 0.01, 0.02, 0.05, 0.10])
    y2 = model.predict(np.full(sigma2.size, 0.01), sigma2, {"c": 0.5})
    if np.any(np.diff(y2) < 0.0):
        return False, "关于 sigma 非单调: %r" % (np.diff(y2),)
    return True, "SqrtImpact 关于 p/sigma 单调不减"


def check_i10(panel):
    rho = 0.9
    got = float(half_life(rho))
    want = float(np.log(0.5) / np.log(rho))
    if not np.isclose(got, want, rtol=1e-12, atol=0.0):
        return False, "half_life=%r vs 解析=%r" % (got, want)
    return True, "half_life(0.9)=%.6f（rtol=1e-12）" % got


def check_i11(panel):
    rng = np.random.default_rng(11)
    x = np.cumsum(rng.normal(size=200))
    b = auto_block_size(x)
    if not isinstance(b, int):
        return False, "b 非 int: %r" % (type(b),)
    if not (1 <= b <= len(x) // 3):
        return False, "b=%r 越界 [1, %d]" % (b, len(x) // 3)
    return True, "auto_block_size=%d ∈ [1, %d]" % (b, len(x) // 3)


register(Invariant("I8_limit_lock_truth", "backtest.execution.core.classification",
                   "invariant", "limit_heavy", check_i8))
register(Invariant("I9_impact_monotonic", "backtest.execution.core.impact",
                   "monotonic", "clean", check_i9))
register(Invariant("I10_half_life_identity", "backtest.execution.core.decay",
                   "equivalence", "clean", check_i10))
register(Invariant("I11_block_size_bound", "backtest.execution.core.bootstrap",
                   "bound", "clean", check_i11))
