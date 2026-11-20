# -*- coding: utf-8 -*-
"""v3.8.0 E5/E6/E2 — 容量复用、regime、AveW、λ 与 c 三档（T380-41 ~ T380-50）。

红形态：``ImportError: cannot import name 'run_calibration'``。
"""
import dataclasses
import json

import numpy as np
import pytest


@pytest.fixture()
def cfg():
    from backtest.execution.config import CalibrationConfig
    return CalibrationConfig(minute_root=None)


def _panels(fake=False):
    p = np.array([0.001, 0.005, 0.01, 0.02, 0.05])
    sigma = np.full_like(p, 0.02)
    impact = 0.5 * sigma * np.sqrt(p)
    return {
        "regime_p95": {"calm": 0.05, "vol": 0.10, "extreme": 0.20},
        "aum_ref": 1e10,
        "cap": 0.10,
        "window_capacity": {"24": 12e9, "36": 11e9, "48": 10e9, "60": 9e9},
        "impact_samples": {"p": p, "impact": impact, "sigma": sigma},
    }


def test_capacity_fn_injected(cfg):
    """T380-41: capacity_fn 注入后校准输出随动（同一实现）。"""
    from backtest.execution.shell.runner import run_calibration
    out_a = run_calibration(
        cfg, capacity_fn=lambda p95, ref, cap: 42.0, panels=_panels())
    out_b = run_calibration(
        cfg, capacity_fn=lambda p95, ref, cap: 84.0, panels=_panels())
    assert out_a["capacity"]["regimes"]["calm"] == 42.0
    assert out_b["capacity"]["regimes"]["calm"] == 84.0
    assert "config_hash" in out_a


def test_same_params_same_result(cfg):
    """T380-42: 同参数下结果逐位相同。"""
    from backtest.execution.shell.runner import run_calibration
    fn = lambda p95, ref, cap: float(cap) / float(p95)
    a = run_calibration(cfg, capacity_fn=fn, panels=_panels())
    b = run_calibration(cfg, capacity_fn=fn, panels=_panels())
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_kappa_monotonic():
    """T380-43: kappa 增大 -> 容量减小。"""
    from backtest.execution.shell.runner import apply_kappa

    def cap_fn(p95, ref, cap):
        return float(cap) / float(p95)

    c1 = apply_kappa(0.10, 1e10, 0.10, 1.0, cap_fn)
    c2 = apply_kappa(0.10, 1e10, 0.10, 2.0, cap_fn)
    assert c2 < c1


def test_regime_primary_uses_min():
    """T380-44: 主值取 min 而非 mean。"""
    from backtest.execution.shell.runner import regime_capacity
    out = regime_capacity({"a": 10.0, "b": 3.0, "c": 7.0})
    assert out["min_regime"] == 3.0
    assert out["median"] == 7.0


def test_avew_prediction_average_not_param_average():
    """T380-45: 对预测（容量）取平均，与参数平均结果不同。"""
    from backtest.execution.shell.runner import average_capacity
    c_windows = np.array([0.4, 0.5, 0.6, 0.7])
    capacities = 1.0 / c_windows ** 2          # 容量 ∝ 1/c^2（非线性）
    out = average_capacity(capacities)
    param_avg = 1.0 / float(c_windows.mean()) ** 2
    assert np.isclose(out["avew"], float(capacities.mean()))
    assert abs(out["avew"] - param_avg) > 1e-6


def test_avew_equal_weights():
    """T380-46: 4 窗长权重各 0.25。"""
    from backtest.execution.shell.runner import average_capacity
    out = average_capacity(np.array([12e9, 11e9, 10e9, 9e9]))
    assert np.allclose(out["weights"], np.full(4, 0.25))
    assert np.isclose(sum(out["weights"]), 1.0)


def test_drift_downgrade():
    """T380-47: spread>0.30 -> 取最差窗 + 警告。"""
    from backtest.execution.shell.runner import average_capacity
    out = average_capacity(np.array([10.0, 10.0, 10.0, 4.0]))
    assert out["spread"] > 0.30
    assert out["degraded"] is True
    assert out["primary"] == 4.0
    assert len(out["evidence_warnings"]) > 0


def test_lambda_recovery():
    """T380-48: 合成 r=λx -> 反解误差 < 1e-6。"""
    from backtest.execution.shell.runner import fit_lambda
    rng = np.random.default_rng(12)
    x = rng.uniform(1e-3, 0.05, 400)
    r = 2.5 * x
    assert abs(fit_lambda(x, r) - 2.5) < 1e-6


def test_hac_se_larger_than_iid():
    """T380-49: 自相关序列的 HAC SE 大于 iid SE。"""
    from backtest.execution.shell.runner import fit_lambda_hac
    rng = np.random.default_rng(13)
    n = 400
    x = np.zeros(n)
    eps = np.zeros(n)
    for t in range(1, n):
        x[t] = 0.6 * x[t - 1] + rng.normal(0.0, 0.01)
        eps[t] = 0.6 * eps[t - 1] + rng.normal(0.0, 1e-4)
    r = 2.0 * x + eps
    out = fit_lambda_hac(x, r)
    assert out["se_hac"] > out["se_iid"]


def test_c_stress_direction():
    """T380-50: c_stress == max(0.5, c_ci_upper)（等值断言）。"""
    from backtest.execution.shell.runner import c_triplet
    out = c_triplet(point=0.41, lower=0.22, upper=0.78)
    assert out["c_default"] == 0.5
    assert out["c_calib_stress"] == max(0.5, 0.78)
    low = c_triplet(point=0.30, lower=0.10, upper=0.30)
    assert low["c_calib_stress"] == 0.5


def test_kappa_scenarios_keys(cfg):
    """T381-19: κ 情景键集由 cfg.kappa 决定；默认 1.5 三键、1.0 两键。"""
    from backtest.execution.shell.runner import run_calibration
    fn = lambda p95, ref, cap: float(cap) / float(p95)
    out = run_calibration(cfg, capacity_fn=fn, panels=_panels())
    assert set(out["capacity"]["scenarios"]) == {"1.0", "1.5", "2.0"}
    cfg1 = dataclasses.replace(cfg, kappa=1.0)
    out1 = run_calibration(cfg1, capacity_fn=fn, panels=_panels())
    assert set(out1["capacity"]["scenarios"]) == {"1.0", "2.0"}


def test_render_markdown_requires_evidence_level():
    """T381-21: 缺 evidence_level 时 render_markdown 抛 ValueError。"""
    from backtest.execution.shell.report import render_markdown
    with pytest.raises(ValueError):
        render_markdown({"config_hash": "deadbeef"})


# ---------------------------------------------------------------- v3.9.2 口径修复
def test_c_gate_strong_signal():
    """T3（v3.9.2）：强信号下 r2≈1、c 还原、常量符合设计。"""
    from backtest.execution.core.impact import (C_R2_MIN, C_RANGE, SqrtImpact,
                                                fit_r2)
    p = np.array([0.001, 0.005, 0.01, 0.02, 0.05])
    sigma = np.full_like(p, 0.02)
    y = 0.5 * sigma * np.sqrt(p)
    params = SqrtImpact().fit(p, y, sigma)
    r2 = fit_r2(SqrtImpact().predict(p, sigma, params), y)
    assert params["c"] == pytest.approx(0.5)
    assert r2 > 0.99
    assert C_R2_MIN == 0.05
    assert C_RANGE == (0.1, 2.0)


def test_runner_reports_c_gate(cfg):
    """T7（v3.9.2）：runner 输出门槛字段；rho<=0 回退 1.0。"""
    from backtest.execution.shell.runner import run_calibration
    rng = np.random.default_rng(11)
    n = 200
    panels = _panels()
    panels["impact_samples"] = {
        "p": rng.uniform(0.001, 0.05, n),
        "impact": rng.uniform(0.0, 0.05, n),
        "sigma": np.full(n, 0.02)}
    panels["rho_series"] = [0.01, -0.01] * 50
    panels["temporary_basis"] = "portfolio_ar1_proxy"
    out = run_calibration(
        cfg, capacity_fn=lambda p95, ref, cap: float(cap) / float(p95),
        panels=panels)
    assert "c_r2" in out["c"]
    assert out["c"]["c_identifiable"] is False
    assert out["c"]["c_effective"] == 0.5
    assert out["temporary_basis"] == "portfolio_ar1_proxy"
    assert out["decay"]["rho"] == 1.0


def test_runner_rho_short_series_falls_back(cfg):
    """T9（v3.9.2 审计补）：rho 序列不足 3 点或为常数时不崩，按 1.0。"""
    from backtest.execution.shell.runner import run_calibration
    fn = lambda p95, ref, cap: float(cap) / float(p95)
    for series in ([], [0.1, 0.2], [0.05] * 10):
        panels = _panels()
        panels["rho_series"] = series
        out = run_calibration(cfg, capacity_fn=fn, panels=panels)
        assert out["decay"]["rho"] == 1.0


def test_assemble_decay_curve_payload():
    """T393-9: 39×60 合成矩阵 → §4.4 键域 + DR-2/DR-7 追加键。"""
    from backtest.execution.shell.runner import assemble_decay_curve

    rows = np.arange(1, 61, dtype=float)[None, :] * 1e-3
    mat = np.repeat(rows, 39, axis=0)
    mat[0, 30:] = np.nan
    panels = {
        "decay_a_by_period": mat.tolist(),
        "decay_h_max": 60,
        "alpha0": 0.002629,
        "aum_ref": 1e10,
        "cost_by_h": {5: 1e6, 10: 2e6, 20: 4e6},
    }
    payload = assemble_decay_curve(panels)
    assert payload is not None
    expected = {"h_m", "n_periods", "alpha0_anchored", "alpha0_calendar",
                "phi", "phi_status", "decay_source", "horizons", "m", "a",
                "net", "boot", "verdict", "evidence_warnings", "n_by_h",
                "m_sensitivity"}
    assert expected <= set(payload)
    assert payload["h_m"] == 20
    assert payload["n_periods"] == 39
    assert payload["horizons"] == [5, 10, 20]
    assert payload["m"]["20"]["point"] == pytest.approx(1.0, abs=1e-12)
    assert set(payload["verdict"]) == {"5", "10"}
    assert payload["n_by_h"]["60"] <= payload["n_by_h"]["5"] <= 39
    assert payload["n_by_h"]["60"] == 38
    assert payload["n_by_h"]["5"] == 39
    for h in ("5", "10", "20"):
        item = payload["net"][h]
        assert np.isfinite(item["point"])
        assert np.isfinite(item["lo"]) and np.isfinite(item["hi"])
        assert "median" in payload["a"][h]
    assert set(payload["m_sensitivity"]) == {"1", "6"}
    assert "lo" in payload["m_sensitivity"]["1"]["5"]
    assert isinstance(payload["alpha0_anchored"], float)
    json.dumps(payload)
