# -*- coding: utf-8 -*-
"""v3.9.3 alpha 衰减模型（FO-1）— T393-1 ~ T393-8。

红形态：``ImportError: cannot import name 'decay_multiplier'``。
"""
import math

import numpy as np
import pytest

NEW_SYMBOLS = ("DecayCurve", "decay_multiplier", "anchored_multiplier",
               "fit_phi", "net_point", "net_ci", "AnchoredDecay",
               "EmpiricalDecay")


def test_decay_multiplier_anchors():
    """T393-1: m(h_m)=1；A(h)=c·h 平直；A(h_m)<=0 全 NaN；非法入参抛错。"""
    from backtest.execution.core.decay import decay_multiplier

    m = decay_multiplier({1: 0.05, 5: 0.25, 10: 0.5, 20: 1.0, 60: 3.0}, 20)
    assert abs(m[20] - 1.0) <= 1e-12
    assert m[5] == pytest.approx(1.0, abs=1e-12)
    assert m[10] == pytest.approx(1.0, abs=1e-12)

    lin = dict((h, 2.0 * h) for h in (1, 5, 10, 20, 60))
    for value in decay_multiplier(lin, 20).values():
        assert abs(value - 1.0) <= 1e-12

    bad = {1: -0.1, 5: -0.2, 20: 0.0}
    for value in decay_multiplier(bad, 20).values():
        assert math.isnan(value)

    with pytest.raises(ValueError):
        decay_multiplier({1: 1.0}, 20)
    with pytest.raises(ValueError):
        decay_multiplier({1.5: 1.0, 20: 2.0}, 20)


def test_anchored_multiplier_limits():
    """T393-2: φ=1 全 1；φ=0.01 时 m(1)≈19.8；严格递减且 h<h_m 时 m>1。"""
    from backtest.execution.core.decay import anchored_multiplier

    hs = [1, 5, 10, 20]
    flat = anchored_multiplier(1.0, hs, 20)
    assert all(abs(v - 1.0) <= 1e-12 for v in flat.values())

    near = anchored_multiplier(0.01, hs, 20)
    assert near[1] == pytest.approx(19.8, abs=0.1)
    assert abs(near[20] - 1.0) <= 1e-12
    seq = [near[h] for h in hs]
    assert all(a > b for a, b in zip(seq, seq[1:]))
    assert all(near[h] > 1.0 for h in (1, 5, 10))

    with pytest.raises(ValueError):
        anchored_multiplier(0.0, hs, 20)
    with pytest.raises(ValueError):
        anchored_multiplier(1.5, hs, 20)


def test_fit_phi_recovers():
    """T393-3: φ*=0.95 生成数据 → |φ̂−φ*|≤5e-3、sse<1e-10。"""
    from backtest.execution.core.decay import fit_phi

    phi_star, c = 0.95, 0.1
    curve = dict((h, c * (1.0 - phi_star ** h) / (1.0 - phi_star))
                 for h in range(1, 21))
    phi, sse = fit_phi(curve, 20)
    assert abs(phi - phi_star) <= 5e-3
    assert sse < 1e-10

    with pytest.raises(ValueError):
        fit_phi({20: 1.0}, 20)


def test_net_point_and_ci():
    """T393-4: net_point 恒等式；net_ci point 取原始曲线；lo<=point<=hi。"""
    from backtest.execution.core.decay import (decay_multiplier, net_ci,
                                               net_point)

    a_point = {1: 0.05, 5: 0.25, 10: 0.45, 20: 0.8, 60: 1.2}
    cost = {5: 1e5, 10: 2e5, 20: 4e5}
    aum = 1e9
    m_point = decay_multiplier(a_point, 20)
    net = net_point(0.04, aum, m_point, cost)
    assert net[20] == pytest.approx(aum * 0.04 * 1.0 - 4e5)
    assert set(net) == set(cost)

    reps = 200
    rng = np.random.default_rng(0)
    a_boot = dict((h, v * (1.0 + 0.05 * rng.standard_normal(reps)))
                  for h, v in a_point.items())
    base = a_boot[20]
    m_boot = {}
    for h in a_point:
        if h == 20:
            m_boot[h] = np.ones(reps)
        else:
            m_boot[h] = a_boot[h] / (base * h / 20.0)

    out = net_ci(a_boot, m_boot, aum, cost, a_point, 20)
    expected = net_point(a_point[20], aum, m_point, cost)
    assert set(out) == set(cost)
    for h, item in out.items():
        assert item["point"] == pytest.approx(expected[h])
        assert np.isfinite(item["lo"]) and np.isfinite(item["hi"])
        assert item["lo"] <= item["point"] <= item["hi"]

    with pytest.raises(ValueError):
        net_ci({5: a_boot[5]}, {5: m_boot[5]}, aum, cost, a_point, 20)


def test_decay_ports_protocol():
    """T393-5: 两端口 retention 长度/取值/name；EmpiricalDecay 插值与 h_m 归一。"""
    from backtest.execution.core.decay import AnchoredDecay, EmpiricalDecay

    anchored = AnchoredDecay(1.0)
    arr = anchored.retention([1, 5, 20])
    assert isinstance(arr, np.ndarray)
    assert arr.shape == (3,)
    assert np.allclose(arr, 1.0, atol=0.0)
    assert anchored.name == "anchored"

    empirical = EmpiricalDecay({5: 1.2, 20: 1.5})
    out = empirical.retention([1, 5, 10, 20])
    assert out.shape == (4,)
    assert out[1] == pytest.approx(1.2)
    assert out[2] == pytest.approx(1.2 + (1.0 - 1.2) * (5.0 / 15.0))
    assert out[3] == pytest.approx(1.0)
    assert empirical.name == "empirical"


def test_invariants_flat_and_degenerate():
    """T393-6: 不变式 2/3/4 逐条。"""
    from backtest.execution.core.decay import anchored_multiplier

    hs = list(range(1, 21))
    assert all(abs(v - 1.0) <= 1e-12
               for v in anchored_multiplier(1.0, hs, 20).values())

    tiny = anchored_multiplier(1e-9, hs, 20)
    for h in hs:
        assert tiny[h] == pytest.approx(20.0 / h, abs=1e-6)

    decay = anchored_multiplier(0.9, hs, 20)
    seq = [decay[h] for h in hs]
    assert all(a > b for a, b in zip(seq, seq[1:]))
    assert all(decay[h] > 1.0 for h in hs[:-1])
    assert abs(decay[20] - 1.0) <= 1e-12


def test_architecture_all_unchanged():
    """T393-7: decay.__all__ 仍 5 项且不含新符号（DR-3）。"""
    from backtest.execution.core import decay

    assert len(decay.__all__) == 5
    for name in NEW_SYMBOLS:
        assert name not in decay.__all__
        assert hasattr(decay, name)


def _panels(rows, h_max=60):
    return {
        "decay_a_by_period": rows,
        "decay_h_max": h_max,
        "alpha0": 0.002629,
        "aum_ref": 1e10,
        "cost_by_h": {5: 1e6, 10: 2e6, 20: 4e6},
    }


def test_assemble_degradations():
    """T393-8: 期数 9 → prior；10<=n<39 → small_sample；A(20)<=0 → unidentified。"""
    from backtest.execution.shell.runner import assemble_decay_curve

    small = np.tile(np.arange(1, 61, dtype=float) * 1e-3, (9, 1))
    payload = assemble_decay_curve(_panels(small.tolist()))
    assert payload["decay_source"] == "prior"
    assert payload["phi"] == pytest.approx(2 ** (-1.0 / 126.0))
    assert "decay_prior_fallback" in payload["evidence_warnings"]

    mid = np.tile(np.arange(1, 61, dtype=float) * 1e-3, (12, 1))
    payload_mid = assemble_decay_curve(_panels(mid.tolist()))
    assert payload_mid["decay_source"] == "empirical"
    assert "decay_small_sample" in payload_mid["evidence_warnings"]

    negative = -np.tile(np.arange(1, 61, dtype=float) * 1e-3, (12, 1))
    payload_neg = assemble_decay_curve(_panels(negative.tolist()))
    assert payload_neg["phi_status"] == "unidentified"
    for h in ("5", "10", "20"):
        assert math.isnan(payload_neg["m"][h]["point"])
    assert payload_neg["verdict"]["5"] == "unidentified"
    assert payload_neg["verdict"]["10"] == "unidentified"
    assert "decay_curve_unidentified" in payload_neg["evidence_warnings"]


# ---------------------------------------------------------------- v3.9.4
def _net_panels(rows, h_max=60):
    return {"decay_a_by_period": rows, "decay_h_max": h_max,
            "alpha0": 0.002629, "aum_ref": 1e10,
            "cost_by_h": {5: 1e6, 10: 2e6, 20: 4e6}}


def _varied_rows(n=20, h_max=60):
    base = np.arange(1, h_max + 1, dtype=float) * 1e-3
    noise = np.linspace(-2e-3, 2e-3, n)[:, None]
    return (base[None, :] + noise).tolist()


def test_fallback_net_interval_m_form():
    """T394-1: n_bootstrap=50 → 回退分支；lo/hi 与 m 形式独立复算一致。"""
    from backtest.execution.shell.runner import assemble_decay_curve

    rows = _varied_rows()
    payload = assemble_decay_curve(_net_panels(rows), n_bootstrap=50)
    assert "decay_ci_analytic_fallback" in payload["evidence_warnings"]
    aum, hm = 1e10, 20
    a_hm = payload["a"][str(hm)]["point"]
    nu = len(rows) - 1
    z = 1.959963984540054
    t_crit = (z + (z ** 3 + z) / (4.0 * nu)
              + (5 * z ** 5 + 16 * z ** 3 + 3 * z) / (96.0 * nu ** 2))
    mat = np.asarray(rows, dtype=float)
    for h, cost in ((5, 1e6), (10, 2e6), (20, 4e6)):
        col = mat[:, h - 1]
        ok = np.isfinite(col)
        se_a = float(np.std(col[ok], ddof=1) / np.sqrt(ok.sum()))
        m_se = se_a / (a_hm * float(h) / float(hm))
        m = payload["m"][str(h)]["point"]
        base_net = aum * a_hm
        item = payload["net"][str(h)]
        assert item["lo"] == pytest.approx(
            base_net * (m - t_crit * m_se) - cost, rel=1e-9, abs=1e-6)
        assert item["hi"] == pytest.approx(
            base_net * (m + t_crit * m_se) - cost, rel=1e-9, abs=1e-6)
        assert item["lo"] <= item["point"] <= item["hi"]


def test_degenerate_skips_sensitivity():
    """T394-2: A(h_m)<0 → m_sensitivity == {}、不抛异常。"""
    from backtest.execution.shell.runner import assemble_decay_curve

    rows = np.full((20, 60), -1e-3).tolist()
    payload = assemble_decay_curve(_net_panels(rows), n_bootstrap=50)
    assert payload["m_sensitivity"] == {}
    assert "decay_curve_unidentified" in payload["evidence_warnings"]


def test_decay_curve_constructed(monkeypatch):
    """T394-3: assemble_decay_curve 构造 DecayCurve 恰好 1 次。"""
    from backtest.execution.core import decay as decay_mod
    from backtest.execution.shell.runner import assemble_decay_curve

    calls = []
    real = decay_mod.DecayCurve

    def spy(*args, **kwargs):
        calls.append(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(decay_mod, "DecayCurve", spy)
    payload = assemble_decay_curve(_net_panels(_varied_rows()))
    assert len(calls) == 1
    assert payload["phi_status"] == "fitted"


def test_net_sd_and_plateau():
    """T394-4: 主路径 net[h].sd 有限、plateau 含 argmax 且 ⊆ horizons。"""
    from backtest.execution.shell.runner import assemble_decay_curve

    payload = assemble_decay_curve(_net_panels(_varied_rows()))
    for h in ("5", "10", "20"):
        assert np.isfinite(payload["net"][h]["sd"])
        assert payload["net"][h]["sd"] >= 0.0
    assert set(payload["plateau"]) <= {5, 10, 20}
    nets = payload["net"]
    h_star = max(nets, key=lambda k: nets[k]["point"])
    assert int(h_star) in payload["plateau"]


# ---------------------------------------------------------------- v3.9.6 P-015
def _vci_script():
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    for p in (str(root), str(root / "scripts")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import verify_capacity_impact as vci
    return vci


@pytest.mark.parametrize("net,sd,expected", [
    ({}, 0.0, []),                                   # 空 → []
    ({5: 2.0, 10: 1.0, 20: 0.5}, 0.0, [5]),          # sd=0 只留 argmax
    ({20: 1.0, 5: 1.0, 10: 0.5}, 0.0, [5, 20]),      # 并列 + 排序
    ({5: 1.0, 10: 0.9}, 0.1, [5, 10]),               # >= 边界包含
    ({5: 1.0, 10: 0.89}, 0.1, [5]),                  # 边界外剔除
    ({20: 3.0}, 100.0, [20]),                        # 单点
])
def test_T396_6_plateau_contract(net, sd, expected):
    """T396-6: plateau(net, sd) 契约 6 例（P-015①）。"""
    from backtest.execution.core.decay import plateau
    got = plateau(net, sd)
    assert got == expected
    if net:
        assert max(net, key=lambda h: net[h]) in got


def test_T396_7_decay_curve_md_title_uses_package_version():
    """T396-7: 衰减曲线 md 首行标题跟随包版本（不硬编码）。"""
    import factor_pipeline
    from backtest.execution.shell.runner import assemble_decay_curve

    rows = np.arange(1, 61, dtype=float)[None, :] * 1e-3
    mat = np.repeat(rows, 39, axis=0)
    panels = {
        "decay_a_by_period": mat.tolist(),
        "decay_h_max": 60,
        "alpha0": 0.002629,
        "aum_ref": 1e10,
        "cost_by_h": {5: 1e6, 10: 2e6, 20: 4e6},
    }
    payload = assemble_decay_curve(panels)
    md = _vci_script()._decay_curve_md(payload)
    expected = "# v%s alpha 衰减曲线（FO-1）" % factor_pipeline.__version__
    assert md.splitlines()[0] == expected
    assert "v3.9.3 alpha" not in md
