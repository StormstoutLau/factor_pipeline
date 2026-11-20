# -*- coding: utf-8 -*-
"""v3.8.0 E2 — 冲击模型（T380-01 ~ T380-10）。

红形态：``ModuleNotFoundError: backtest.execution.core.impact``。
"""
import numpy as np
import pytest


@pytest.fixture()
def synthetic_impact():
    p = np.array([0.001, 0.005, 0.01, 0.02, 0.05])
    sigma = np.full_like(p, 0.02)
    impact = 0.5 * sigma * np.sqrt(p)
    return p, impact, sigma


def _models():
    from backtest.execution.core.impact import (
        LinearImpact, LogImpact, PowerImpact, SqrtImpact)
    return [SqrtImpact(), LinearImpact(), LogImpact(), PowerImpact()]


def test_sqrt_monotonic():
    """T380-01: p 递增 -> sqrt 冲击严格递增。"""
    from backtest.execution.core.impact import SqrtImpact
    p = np.linspace(0.001, 0.05, 25)
    out = SqrtImpact().predict(p, np.full_like(p, 0.02), {"c": 0.5})
    assert np.all(np.diff(out) > 0.0)


def test_sqrt_fixed_point():
    """T380-02: p=0.01, sigma=0.02, c=0.5 -> 1e-3（10bp）。"""
    from backtest.execution.core.impact import SqrtImpact
    out = SqrtImpact().predict(
        np.array([0.01]), np.array([0.02]), {"c": 0.5})
    assert np.isclose(out[0], 1e-3, rtol=1e-12)


def test_linear_fixed_point():
    """T380-03: p=0.01, k=0.025 -> 2.5e-4（2.5bp）。"""
    from backtest.execution.core.impact import LinearImpact
    out = LinearImpact().predict(
        np.array([0.01]), np.array([0.02]), {"k": 0.025})
    assert np.isclose(out[0], 2.5e-4, rtol=1e-12)


def test_linear_monotonic():
    """T380-04: p 递增 -> linear 冲击递增。"""
    from backtest.execution.core.impact import LinearImpact
    p = np.linspace(0.001, 0.05, 25)
    out = LinearImpact().predict(p, np.full_like(p, 0.02), {"k": 0.025})
    assert np.all(np.diff(out) > 0.0)


def test_log_monotonic():
    """T380-05: 正参数区 p 递增 -> log 冲击递增。"""
    from backtest.execution.core.impact import LogImpact
    p = np.linspace(0.001, 0.05, 25)
    out = LogImpact().predict(p, np.full_like(p, 0.02),
                              {"a": 0.1, "b": 0.01})
    assert np.all(out > 0.0)
    assert np.all(np.diff(out) > 0.0)


def test_log_invalid_excluded(synthetic_impact):
    """T380-06: a + b*ln(p_min) <= 0 -> 拟合报错并被选型排除。"""
    from backtest.execution.core.impact import (
        LinearImpact, LogImpact, PowerImpact, SqrtImpact,
        cross_val_rmse, select_models)
    p, _, sigma = synthetic_impact
    # 构造负斜率且截距非正的样本 -> log 在 p_min 处非正
    impact_bad = -0.1 - 0.002 * np.log(p)
    with pytest.raises(ValueError):
        LogImpact().fit(p, impact_bad, sigma)
    cv = cross_val_rmse(
        [SqrtImpact(), LinearImpact(), LogImpact(), PowerImpact()],
        p, impact_bad, sigma, n_folds=5)
    assert not np.isfinite(cv["log"])
    primary, tied = select_models(cv)
    assert "log" not in tied
    assert primary != "log"


def test_power_monotonic():
    """T380-07: b>0 时 power 冲击递增。"""
    from backtest.execution.core.impact import PowerImpact
    p = np.linspace(0.001, 0.05, 25)
    out = PowerImpact().predict(p, np.full_like(p, 0.02),
                                {"a": 0.002, "b": 0.6})
    assert np.all(np.diff(out) > 0.0)


def test_p_zero_raises(synthetic_impact):
    """T380-08: p=0 时 4 个模型的 fit / predict 均抛 ValueError。"""
    p, impact, sigma = synthetic_impact
    p0 = np.array([0.0, 0.01, 0.02])
    imp0 = np.array([1e-4, 1e-3, 2e-3])
    for model in _models():
        params = {"c": 0.5, "k": 0.025, "a": 0.1, "b": 0.6}
        with pytest.raises(ValueError):
            model.predict(np.array([0.0]), np.array([0.02]), params)
        with pytest.raises(ValueError):
            model.fit(p0, imp0, np.full(3, 0.02))


def test_constant_series_raises(synthetic_impact):
    """T380-09: np.ptp(impact)==0 -> ValueError（v3.7.0 H1 惯例）。"""
    p, _, sigma = synthetic_impact
    const = np.full_like(p, 1e-3)
    for model in _models():
        with pytest.raises(ValueError):
            model.fit(p, const, sigma)


def test_select_models_tolerance():
    """T380-10: CV 差 5% -> 并列 2 项；差 20% -> 仅 1 项。"""
    from backtest.execution.core.impact import select_models
    primary, tied = select_models({"sqrt": 1.00, "linear": 1.05,
                                   "log": 1.20, "power": 1.40})
    assert primary == "sqrt"
    assert set(tied) == {"sqrt", "linear"}
    primary2, tied2 = select_models({"sqrt": 1.00, "linear": 1.20})
    assert primary2 == "sqrt"
    assert tied2 == ["sqrt"]
