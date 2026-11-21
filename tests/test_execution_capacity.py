# -*- coding: utf-8 -*-
"""v3.8.0 E5/E6/E2 — 容量复用、regime、AveW、λ 与 c 三档（T380-41 ~ T380-50）。

红形态：``ImportError: cannot import name 'run_calibration'``。
"""
import dataclasses
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
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


# ---------------------------------------------------------------- v3.9.4
def test_force_coverage_warning_contract():
    """T394-6: 留痕文案 token 化 + 脚本 force 分支已接线（源码文本断言）。"""
    from backtest.execution.shell.panels import force_coverage_warning

    assert force_coverage_warning(["a", "b"]) == "coverage_gate_forced: a; b"
    src = (Path(__file__).resolve().parent.parent
           / "scripts" / "verify_capacity_impact.py").read_text(encoding="utf-8")
    assert "force_coverage_warning(messages)" in src


# ---------------------------------------------------------------- v3.9.5 P-003
def _csr_arrays(rt1_value=-0.01, side_value=1.0):
    """4 个月各 2 个事件；rt=+2%，rt1 默认 -1% → 反转 bps=+100。"""
    months = np.array([0, 0, 1, 1, 2, 2, 3, 3], dtype=np.int64)
    rt = np.full(months.size, 0.02)
    rt1 = np.full(months.size, rt1_value)
    side = np.full(months.size, side_value)
    weight = np.full(months.size, 0.5)
    return rt, rt1, side, weight, months


def test_T3100_1_buy_reversal_positive():
    """T3100-1: 买入 + 次日跌 → reversal_bps > 0；次日涨 → < 0。"""
    from backtest.execution.core.impact import cross_section_reversal

    out = cross_section_reversal(*_csr_arrays())
    assert out["reversal_bps"]["point"] == pytest.approx(100.0)
    assert out["buy"]["point"] == pytest.approx(100.0)
    assert out["buy"]["n"] == 8
    assert out["temporary_share"][0] == pytest.approx(0.5)
    rev = cross_section_reversal(*_csr_arrays(rt1_value=0.01))
    assert rev["reversal_bps"]["point"] < 0.0


def test_T3100_2_sell_reversal_positive():
    """T3100-2: 卖出 + 次日涨 → 正反转；次日跌 → 负。"""
    from backtest.execution.core.impact import cross_section_reversal

    out = cross_section_reversal(*_csr_arrays(rt1_value=0.01, side_value=-1.0))
    assert out["reversal_bps"]["point"] == pytest.approx(100.0)
    assert out["sell"]["point"] == pytest.approx(100.0)
    rev = cross_section_reversal(*_csr_arrays(rt1_value=-0.01,
                                              side_value=-1.0))
    assert rev["reversal_bps"]["point"] < 0.0


def test_T3100_3_shift_invariance_after_demean():
    """T3100-3: 未 demean 的平移对照非恒真（demean 本身由 T396_2 在脚本层覆盖）。"""
    from backtest.execution.core.impact import cross_section_reversal

    rng = np.random.default_rng(7)
    n = 60
    rt = rng.normal(0.0, 0.02, n)
    raw = rng.normal(0.001, 0.02, n)
    weight = np.full(n, 0.1)
    month = np.repeat(np.arange(4), n // 4)

    # v3.9.7 P-017①：demean 幅度类断言由定义恒真（base = raw - raw.mean()），
    # 无判别力，已删除；保留下列对实现的非恒真平移对照。
    # 非恒真对照：未 demean 且买卖不平衡时，平移会改变读数
    n_unbal = n - 1
    c = cross_section_reversal(rt[:n_unbal], raw[:n_unbal],
                               np.ones(n_unbal), weight[:n_unbal],
                               month[:n_unbal])
    d = cross_section_reversal(rt[:n_unbal], raw[:n_unbal] + 0.5,
                               np.ones(n_unbal), weight[:n_unbal],
                               month[:n_unbal])
    assert abs(c["reversal_bps"]["point"]
               - d["reversal_bps"]["point"]) > 1.0


def test_T3100_8_degraded_no_raise():
    """T3100-8: Σax²=0 / n_months<3 / 长度不一致 → 退化且不抛。"""
    from backtest.execution.core.impact import cross_section_reversal

    zeros = cross_section_reversal(np.zeros(8), np.full(8, -0.01),
                                   np.ones(8), np.full(8, 0.5),
                                   np.array([0, 0, 1, 1, 2, 2, 3, 3]))
    assert zeros["temporary_share"] == [0.0, 0.0, 0.0]
    assert zeros["degraded"] is True
    for key in ("point", "lo", "hi"):
        assert np.isnan(zeros["reversal_bps"][key])

    two = cross_section_reversal(np.full(4, 0.02), np.full(4, -0.01),
                                 np.ones(4), np.full(4, 0.5),
                                 np.array([0, 0, 1, 1]))
    assert two["degraded"] is True
    assert two["n_months"] == 2

    bad = cross_section_reversal(np.full(4, 0.02), np.full(3, -0.01),
                                 np.ones(4), np.full(4, 0.5), np.zeros(4))
    assert bad["degraded"] is True
    empty = cross_section_reversal([], [], [], [], [])
    assert empty["degraded"] is True


def test_T3100_9_bootstrap_endpoint_and_reproducible():
    """T3100-9: point ∈ [lo,hi]；固定 seed 双跑逐位一致。"""
    from backtest.execution.core.impact import cross_section_reversal

    rng = np.random.default_rng(21)
    n = 120
    rt = rng.normal(0.0, 0.02, n)
    rt1 = -0.4 * rt + rng.normal(0.0, 0.01, n)
    side = rng.choice([-1.0, 1.0], n)
    weight = rng.uniform(0.01, 0.1, n)
    month = np.repeat(np.arange(6), n // 6)

    a = cross_section_reversal(rt, rt1, side, weight, month)
    b = cross_section_reversal(rt, rt1, side, weight, month)
    assert a == b
    lo, hi = a["temporary_share"][1], a["temporary_share"][2]
    assert lo <= a["temporary_share"][0] <= hi
    for key in ("reversal_bps", "buy", "sell"):
        assert a[key]["lo"] <= a[key]["point"] <= a[key]["hi"]
    other = cross_section_reversal(rt, rt1, side, weight, month, seed=1)
    assert other["temporary_share"][1:] != a["temporary_share"][1:]

    # v3.9.6 P-016④：常数输入 → 分位退化，lo == point == hi == 100.0
    # （rt 必须非零，否则 Σa·x²=0 走退化分支返回 NaN）
    const = cross_section_reversal(np.full(8, 0.02), np.full(8, -0.01),
                                   np.ones(8), np.full(8, 0.5),
                                   np.array([0, 0, 1, 1, 2, 2, 3, 3]))
    assert const["degraded"] is False
    assert const["reversal_bps"]["point"] == pytest.approx(100.0)
    assert const["reversal_bps"]["lo"] == pytest.approx(100.0)
    assert const["reversal_bps"]["hi"] == pytest.approx(100.0)


def _vci():
    root = Path(__file__).resolve().parent.parent
    for p in (str(root), str(root / "scripts")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import verify_capacity_impact as vci
    return vci


def _event_panel():
    """4 个形成日 × 4 只股票；构造已知的 t / t+1 日收益与 Δw。"""
    vci = _vci()
    dates = pd.bdate_range("2020-01-01", "2020-08-31")
    codes = ["000001", "000002", "000003", "000004"]
    form_dates = pd.DatetimeIndex(
        [dates[dates.month == m].max() for m in (1, 2, 3, 4)])
    ret_t = {"000001": 0.02, "000002": 0.01,
             "000003": 0.03, "000004": 0.00}
    ret_t1 = {"000001": -0.03, "000002": 0.02,
              "000003": -0.01, "000004": 0.01}
    ret_map = pd.DataFrame(0.0, index=dates, columns=codes)
    for fd in form_dates:
        pos = int(dates.get_loc(fd))
        for code in codes:
            ret_map.loc[fd, code] = ret_t[code]
            if pos + 1 < len(dates):
                ret_map.iloc[pos + 1, ret_map.columns.get_loc(code)] = (
                    ret_t1[code])
    price = (1.0 + ret_map).cumprod() * 10.0
    mask = pd.DataFrame(True, index=form_dates, columns=codes)
    w = pd.DataFrame(0.0, index=form_dates, columns=codes)
    w.iloc[0] = [0.5, 0.5, 0.0, 0.0]
    w.iloc[1] = [0.0, 0.5, 0.5, 0.0]
    w.iloc[2] = [0.0, 0.0, 0.5, 0.5]
    w.iloc[3] = [0.5, 0.0, 0.0, 0.5]
    impl = {
        "suspend": pd.DataFrame(False, index=dates, columns=codes),
        "st": pd.DataFrame(False, index=dates, columns=codes),
        "limit_up": pd.DataFrame(False, index=dates, columns=codes),
        "limit_down": pd.DataFrame(False, index=dates, columns=codes),
    }
    P = {"close": price.copy(), "adj_price": price.copy(),
         "open_adj": price * 0.995, "mask": mask, "facts": {},
         "impl_daily": impl}
    return vci, P, w, dates, form_dates


def _next_day(dates, day):
    return dates[int(dates.get_loc(day)) + 1]


def test_T3100_4_suspension_filters():
    """T3100-4: 停牌 t / t+1 事件剔除并计数。"""
    vci, P, w, dates, form_dates = _event_panel()
    base = vci.build_reversal_events(P, w)
    assert base["counts"]["n_events"] == 8

    P["impl_daily"]["suspend"].loc[form_dates[1], "000003"] = True
    out = vci.build_reversal_events(P, w)
    assert out["counts"]["n_suspended_t"] == 1
    assert out["counts"]["n_events"] == 7

    P["impl_daily"]["suspend"].loc[
        _next_day(dates, form_dates[2]), "000004"] = True
    out2 = vci.build_reversal_events(P, w)
    assert out2["counts"]["n_suspended_t1"] == 1
    assert out2["counts"]["n_events"] == 6


def test_T3100_5_limit_filters_and_degrade():
    """T3100-5: 买入涨停 / 卖出跌停 / t+1 涨跌停剔除；缺 low 时退化披露。"""
    vci, P, w, dates, form_dates = _event_panel()
    P["impl_daily"]["limit_up"].loc[form_dates[1], "000003"] = True
    P["impl_daily"]["limit_down"].loc[form_dates[2], "000002"] = True
    P["impl_daily"]["limit_up"].loc[
        _next_day(dates, form_dates[0]), "000001"] = True
    out = vci.build_reversal_events(P, w)
    assert out["counts"]["n_limit_up_t"] == 1
    assert out["counts"]["n_limit_down_t"] == 1
    assert out["counts"]["n_limit_t1"] == 1
    assert out["counts"]["n_events"] == 5
    assert out["counts"]["n_limit_down_unavailable"] is False

    P["impl_daily"]["limit_down"] = None
    out2 = vci.build_reversal_events(P, w)
    assert out2["counts"]["n_limit_down_unavailable"] is True
    assert out2["counts"]["n_limit_down_t"] == 0
    assert out2["counts"]["n_events"] == 6


def test_T3100_6_first_period_marked_not_dropped():
    """T3100-6: 首期建仓打标且不剔除。"""
    vci, P, w, _, _ = _event_panel()
    out = vci.build_reversal_events(P, w)
    assert out["counts"]["n_first_period"] == 2
    assert out["counts"]["n_events"] == 8
    assert out["counts"]["n_months"] == 4


def test_T3100_7_exrights_no_fake_reversal():
    """T3100-7: 除权日 close 跳空不影响 adj_price 口径的读数；C2 同口径。"""
    vci, P, w, dates, form_dates = _event_panel()
    base = vci.build_reversal_events(P, w)
    t1 = _next_day(dates, form_dates[0])
    P["close"].loc[t1, "000001"] *= 0.5      # 原始价除权式跳空
    out = vci.build_reversal_events(P, w)
    for key in ("rt", "rt1", "side", "weight", "month"):
        assert np.array_equal(np.asarray(base[key]), np.asarray(out[key]))
    assert abs(out["counts"]["n_extreme"]) == 0

    # C2 回归：复权因子须在 close/open 间相消，不得被重复乘
    P2 = dict(P)
    P2["adj_price"] = P["adj_price"] * 137.0
    P2["open_adj"] = P["open_adj"] * 137.0
    c2 = vci.build_reversal_events(P2, w,
                                   price_basis="adj_intraday_open_close")
    assert c2["price_basis"] == "adj_intraday_open_close"
    assert float(np.abs(c2["rt"]).max()) < 0.5
    assert float(np.abs(c2["rt1"]).max()) < 0.5
    assert c2["counts"]["n_extreme"] == 0


def test_runner_reversal_branch(cfg):
    """T3100 补充: runner 真实现分支输出 reversal_bps 且不污染成本链。"""
    from backtest.execution.shell.runner import run_calibration

    rt, rt1, side, weight, month = _csr_arrays()
    panels = _panels()
    panels["temporary"] = {
        "rt": rt.tolist(), "rt1": rt1.tolist(), "side": side.tolist(),
        "weight": weight.tolist(), "month": month.tolist(),
        "price_basis": "adj_close_to_close_cs"}
    panels["temporary_basis"] = "cross_section_t1"
    out = run_calibration(
        cfg, capacity_fn=lambda p95, ref, cap: float(cap) / float(p95),
        panels=panels)
    assert out["temporary_basis"] == "cross_section_t1"
    assert out["temporary_share"][0] == pytest.approx(0.5)
    assert out["reversal_bps"]["point"] == pytest.approx(100.0)
    assert out["reversal_bps"]["price_basis"] == "adj_close_to_close_cs"
    assert out["reversal_price_basis"] == "adj_close_to_close_cs"

    panels["temporary"] = {"r1": [0.01, -0.01] * 20,
                           "rev1": [-0.005, 0.005] * 20}
    panels["temporary_basis"] = "portfolio_ar1_proxy"
    fallback = run_calibration(
        cfg, capacity_fn=lambda p95, ref, cap: float(cap) / float(p95),
        panels=panels)
    assert fallback["reversal_bps"] is None
    assert fallback["reversal_price_basis"] is None


# ---------------------------------------------------------------- v3.9.6 P-016
def test_T396_1_bootstrap_shared_index(monkeypatch):
    """T396-1: bootstrap 只抽 1 次，buy/sell 共用同一索引（n_months=4 绕开退化分支）。"""
    import backtest.effect_size as es
    from backtest.execution.core.impact import cross_section_reversal

    n_boot, n_months = 50, 4
    calls = []
    plan = [np.ones((n_boot, n_months), dtype=np.int64),
            np.zeros((n_boot, n_months), dtype=np.int64)]

    def spy(n, n_bootstrap=1000, block_size=1, seed=None):
        calls.append(1)
        return plan[len(calls) - 1]

    monkeypatch.setattr(es, "stationary_bootstrap_indices", spy)

    rt = np.full(5, 0.02)
    rt1 = np.array([-0.02, -0.02, 0.03, -0.02, -0.02])
    side = np.array([1.0, 1.0, -1.0, 1.0, 1.0])
    weight = np.full(5, 0.5)
    month = np.array([0, 1, 1, 2, 3], dtype=np.int64)

    out = cross_section_reversal(rt, rt1, side, weight, month, n_bootstrap=50)
    assert len(calls) == 1                    # 共享 ⇔ 只抽一次
    assert out["degraded"] is False
    assert out["buy"]["point"] == pytest.approx(200.0)
    assert out["buy"]["lo"] == pytest.approx(200.0)
    assert out["buy"]["hi"] == pytest.approx(200.0)
    assert out["sell"]["point"] == pytest.approx(300.0)
    assert out["sell"]["lo"] == pytest.approx(300.0)
    assert out["sell"]["hi"] == pytest.approx(300.0)


def test_T396_2_script_demean_zero_mean():
    """T396-2: 形成日截面 demean 后 Σrt≈0，且逐值等于 ret − mean(ret)。"""
    vci, P, w0, _dates, form_dates = _event_panel()
    w = pd.DataFrame(0.25, index=form_dates, columns=w0.columns)
    out = vci.build_reversal_events(P, w)
    raw = np.array([0.02, 0.01, 0.03, 0.00])
    expected = raw - raw.mean()
    assert out["counts"]["n_events"] == 4
    assert np.allclose(np.sort(out["rt"]), np.sort(expected))
    assert abs(float(np.sum(out["rt"]))) < 1e-12


def test_T396_5_reversal_counts_key_set():
    """T396-5: counts 键集恰为 15 键字面量，n_months 与权重期数一致。"""
    vci, P, w, _dates, _form_dates = _event_panel()
    out = vci.build_reversal_events(P, w)
    expected = {"n_events", "n_months", "n_buy", "n_sell",
                "n_first_period", "n_suspended_t", "n_suspended_t1",
                "n_limit_up_t", "n_limit_down_t", "n_limit_t1",
                "n_st", "n_tiny", "n_extreme", "n_missing",
                "n_limit_down_unavailable"}
    assert set(out["counts"]) == expected
    assert out["counts"]["n_months"] == len(w.index)
