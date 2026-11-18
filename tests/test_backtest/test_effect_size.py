# -*- coding: utf-8 -*-
"""v3.7.0 E3 — 效应量与置信区间测试（T27-T33 + T32b，8 项）。

对应 ``docs/EXECUTION_V3.7.0_STAT_EVIDENCE_CHAIN.md`` §4.3 与
``docs/private/DESIGN_STAT_EVIDENCE_CHAIN.md`` §8。
"""
import math

import numpy as np
import pytest
import statsmodels.api as sm

from backtest.effect_size import (
    effect_summary,
    mean_ci,
    newey_west_se,
    sharpe_ci,
    stationary_bootstrap_indices,
)


def _ar1(n, rho, seed, sigma=1.0):
    rng = np.random.default_rng(seed)
    eps = rng.normal(scale=sigma, size=n)
    out = np.empty(n, dtype=float)
    out[0] = eps[0]
    for i in range(1, n):
        out[i] = rho * out[i - 1] + eps[i]
    return out


def test_t27_newey_west_iid_limit():
    rng = np.random.default_rng(31)
    values = rng.normal(0.05, 0.2, size=5000)
    out = newey_west_se(values)
    expected = float(values.std(ddof=1) / math.sqrt(values.size))
    assert abs(out["se"] - expected) / expected < 0.05
    assert out["mean"] == pytest.approx(float(values.mean()))
    assert out["n_periods"] == 5000


def test_t28_newey_west_matches_statsmodels():
    rng = np.random.default_rng(37)
    values = _ar1(240, rho=0.35, seed=37) + rng.normal(0.1, 0.5, 240)
    for lag in (0, 1, 3, 6):
        out = newey_west_se(values, max_lag=lag)
        X = np.ones((values.size, 1))
        model = sm.OLS(values, X).fit(
            cov_type="HAC",
            cov_kwds={"maxlags": lag, "use_correction": False},
        )
        expected = float(np.sqrt(model.cov_params()[0, 0]))
        assert out["se"] == pytest.approx(expected, abs=1e-10)
        assert out["lag"] == lag


def test_t29_newey_west_autocorrelation_inflates_se():
    values = _ar1(500, rho=0.6, seed=41)
    out = newey_west_se(values)
    iid = float(values.std(ddof=1) / math.sqrt(values.size))
    assert out["se"] > iid


def test_t30_mean_ci():
    rng = np.random.default_rng(43)
    values = rng.normal(0.08, 0.3, size=120)
    out = mean_ci(values, alpha=0.05)
    assert out["ci_low"] <= out["mean"] <= out["ci_high"]
    assert out["ci_low"] == pytest.approx(
        out["mean"] - out["critical_value"] * out["se"])
    assert out["ci_high"] == pytest.approx(
        out["mean"] + out["critical_value"] * out["se"])
    with pytest.raises(ValueError):
        mean_ci(values, alpha=0.0)
    with pytest.raises(ValueError):
        mean_ci(values, alpha=1.0)


def test_t31_stationary_bootstrap():
    idx_a = stationary_bootstrap_indices(60, n_bootstrap=200, seed=7)
    idx_b = stationary_bootstrap_indices(60, n_bootstrap=200, seed=7)
    assert np.array_equal(idx_a, idx_b)
    assert idx_a.shape == (200, 60)
    assert idx_a.min() >= 0 and idx_a.max() < 60

    # 块长 1 退化为 iid：循环延续概率 ~ 1/n（纯随机巧合）
    iid_idx = stationary_bootstrap_indices(
        60, n_bootstrap=200, block_size=1, seed=7)
    continuation = (iid_idx[:, 1:] == (iid_idx[:, :-1] + 1) % 60)
    assert continuation.mean() == pytest.approx(1.0 / 60.0, abs=0.01)

    # 块长 = T：几乎总是循环延续
    long_idx = stationary_bootstrap_indices(
        60, n_bootstrap=200, block_size=60, seed=7)
    continuation_long = (long_idx[:, 1:] == (long_idx[:, :-1] + 1) % 60)
    assert continuation_long.mean() > 0.9


def test_t32_sharpe_ci():
    rng = np.random.default_rng(47)
    returns = rng.normal(0.03, 0.08, size=120)
    out_a = sharpe_ci(returns, n_bootstrap=500, seed=11)
    out_b = sharpe_ci(returns, n_bootstrap=500, seed=11)
    assert out_a["ci_low"] == out_b["ci_low"]
    assert out_a["ci_high"] == out_b["ci_high"]
    assert out_a["sharpe"] == out_b["sharpe"]
    assert out_a["ci_low"] <= out_a["sharpe"] <= out_a["ci_high"]


def test_t32b_sharpe_consistency_across_modules():
    from backtest.overfitting import sharpe_ratio

    rng = np.random.default_rng(53)
    returns = rng.normal(0.02, 0.06, size=58)
    effect = effect_summary("sharpe", returns, n_bootstrap=200, seed=3)
    unique = sharpe_ratio(returns)
    assert abs(effect["effect_size"] - unique["sharpe"]) <= 1e-12
    assert abs(effect["sharpe_per_period"]
               - unique["sharpe_per_period"]) <= 1e-12

    # 模块边界：effect_size 不 import overfitting
    import backtest.effect_size as effect_mod
    assert not hasattr(effect_mod, "overfitting")
    assert "overfitting" not in effect_mod.__dict__


def test_t33_effect_summary_dispatch():
    rng = np.random.default_rng(59)
    values = rng.normal(0.05, 0.2, size=120)
    for metric in ("lambda_mean", "ic_mean"):
        out = effect_summary(metric, values, max_lag=2)
        assert out["metric"] == metric
        assert out["method"] == "newey_west"
        assert out["effect_size"] == pytest.approx(float(values.mean()))
        assert out["ci_low"] <= out["effect_size"] <= out["ci_high"]
    sharpe = effect_summary("sharpe", values, n_bootstrap=200, seed=5)
    assert sharpe["metric"] == "sharpe"
    assert sharpe["method"] == "stationary_bootstrap"
    assert sharpe["ci_low"] <= sharpe["effect_size"] <= sharpe["ci_high"]
    with pytest.raises(ValueError):
        effect_summary("t_stat", values)


def test_t33b_constant_fp_slip_raises():
    """v3.7.0 复审 H1：常数序列因均值舍入 std≈1e-19>0，须显式拒绝。"""
    constant_se = np.full(20, 0.01)
    assert constant_se.std(ddof=1) > 0.0  # 复现浮点假阳性前提
    with pytest.raises(ValueError):
        newey_west_se(constant_se)
    constant_sr = np.full(58, 0.02)
    with pytest.raises(ValueError):
        sharpe_ci(constant_sr, n_bootstrap=100)
