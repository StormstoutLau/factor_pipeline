# -*- coding: utf-8 -*-
"""v3.8.0 校准编排（唯一装配点）。

设计依据：DESIGN §9 §10 §11 §12；实施依据：EXECUTION §2.10。
容量函数只能经 ``capacity_fn`` / ``breakeven_fn`` 注入，
本包内不得 import ``scripts``（T380-41 / T380-54）。
"""
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from ..core.classification import normal_cdf
from ..core.decay import (ExponentialDecay, estimate_rho, execution_days,
                          half_life, net_curve, plateau, retention)
from ..core.impact import (C_R2_MIN, C_RANGE, LinearImpact, LogImpact,
                           PowerImpact, SqrtImpact, cross_val_rmse, fit_r2,
                           select_models, temporary_share)
from ..core.spread import AbdiRanaldo, Amihud, CorwinSchultz
from ..registry import ModelRegistry
from .loaders import resolve_evidence_level

__all__ = ["build_pipeline", "run_calibration", "fit_lambda",
           "fit_lambda_hac", "c_triplet", "average_capacity",
           "regime_capacity", "apply_kappa", "ratio_diagnostics"]


def build_pipeline(cfg):
    """装配 4 端口实现；``isinstance`` 只在此处各做一次。"""
    from ..ports import DecayModel, ImpactModel, SpreadEstimator, VolumeClassifier
    from ..core.classification import BVC

    registry = ModelRegistry()
    impacts = {}  # type: Dict[str, object]
    for model in (SqrtImpact(), LinearImpact(), LogImpact(), PowerImpact()):
        registry.register(model)
        assert isinstance(model, ImpactModel)
        impacts[model.name] = model
    spreads = {}  # type: Dict[str, object]
    for est in (CorwinSchultz(), AbdiRanaldo(), Amihud()):
        assert isinstance(est, SpreadEstimator)
        spreads[est.name] = est
    classifier = BVC()
    assert isinstance(classifier, VolumeClassifier)
    decay = ExponentialDecay(1.0)
    assert isinstance(decay, DecayModel)
    return {"impact": impacts, "spread": spreads, "classifier": classifier,
            "decay": decay, "registry": registry}


def fit_lambda(x, r):
    """λ = Σ x r / Σ x²（过原点）。"""
    xa = np.asarray(x, dtype=float).ravel()
    ra = np.asarray(r, dtype=float).ravel()
    if xa.size != ra.size:
        raise ValueError("x 与 r 长度不一致")
    if xa.size < 3:
        raise ValueError("样本不足 3")
    denom = float(np.dot(xa, xa))
    if denom <= 0.0:
        raise ValueError("x 方差为 0")
    return float(np.dot(xa, ra) / denom)


def fit_lambda_hac(x, r):
    """λ 的 HAC 标准误与 iid 对照（复用 ``newey_west_se``）。"""
    from ...effect_size import newey_west_se

    xa = np.asarray(x, dtype=float).ravel()
    ra = np.asarray(r, dtype=float).ravel()
    lam = fit_lambda(xa, ra)
    n = int(xa.size)
    denom = float(np.dot(xa, xa))
    resid = ra - lam * xa
    dof = max(1, n - 1)
    se_iid = float(np.sqrt(np.dot(resid, resid) / dof / denom))
    score = xa * resid
    se_hac = se_iid
    if float(np.ptp(score)) > 0.0:
        try:
            nw = newey_west_se(score)
            se_hac = float(nw["se"]) * n / denom
        except ValueError:
            se_hac = se_iid
    t_stat = lam / se_hac if se_hac > 0.0 else float("nan")
    p_value = float(2.0 * (1.0 - normal_cdf(
        np.array([abs(t_stat)]))[0])) if np.isfinite(t_stat) else 1.0
    return {"lambda": lam, "se_hac": se_hac, "se_iid": se_iid,
            "t": float(t_stat), "p": p_value, "n": n}


def c_triplet(point, lower, upper):
    """c 三档：默认 0.5 / 校准点 / 压力档 = max(0.5, CI 上界)。"""
    stress = max(0.5, float(upper))
    return {"c_default": 0.5,
            "c_calib_point": float(point),
            "c_calib_lower": float(lower),
            "c_calib_upper": float(upper),
            "c_calib_stress": stress}


def regime_capacity(values):
    """4 regime 容量：主值取 min，同时报 median。"""
    finite = [float(v) for v in values.values() if np.isfinite(float(v))]
    out = {"regimes": {k: float(v) for k, v in values.items()},
           "min_regime": None, "median": None}
    if finite:
        out["min_regime"] = float(min(finite))
        out["median"] = float(np.median(finite))
    return out


def average_capacity(values):
    """4 窗长对**预测容量**等权平均；漂移 > 0.30 降级为最差窗。"""
    arr = np.asarray(list(values), dtype=float)
    if arr.size == 0:
        return {"avew": None, "weights": [], "spread": None,
                "degraded": False, "primary": None,
                "evidence_warnings": ["无窗长容量"]}
    n = int(arr.size)
    avew = float(arr.mean())
    median = float(np.median(arr))
    spread = float((arr.max() - arr.min()) / abs(median)) if median != 0.0 else float("inf")
    degraded = bool(spread > 0.30)
    warnings = []
    if degraded:
        warnings.append("窗长漂移 spread=%.3f > 0.30，主值降级为最差窗" % spread)
    return {"avew": avew, "weights": [1.0 / n] * n, "spread": spread,
            "degraded": degraded,
            "primary": float(arr.min()) if degraded else avew,
            "evidence_warnings": warnings}


def apply_kappa(p95, aum_ref, cap, kappa, capacity_fn):
    """co-impact 情景：有效参与率按 kappa 放大后重算容量。"""
    return float(capacity_fn(float(p95) * float(kappa), aum_ref, cap))


RATIO_GRID = (0.001, 0.005, 0.01, 0.02, 0.05)


def ratio_diagnostics(c_default=0.5, k_default=0.025, sigma=0.02,
                      grid=RATIO_GRID, c_calib=None):
    """design §9.5：默认 sqrt(c=0.5) 与 linear(k=0.025) 的口径比值。

    仅作诊断输出，不修改任一默认常数（D2）。
    """
    p = np.asarray(grid, dtype=float)
    s = np.full(p.shape, float(sigma))
    sqrt_imp = SqrtImpact().predict(p, s, {"c": float(c_default)})
    linear_imp = LinearImpact().predict(p, s, {"k": float(k_default)})
    out = {"sigma": float(sigma),
           "p": [float(v) for v in p],
           "ratio_sqrt_over_linear": [float(v) for v in sqrt_imp / linear_imp]}
    if c_calib is not None:
        calib_imp = SqrtImpact().predict(p, s, {"c": float(c_calib)})
        out["ratio_calib_over_linear"] = [float(v) for v in calib_imp / linear_imp]
    return out


def _bootstrap_ci(fit_fn, p, impact, sigma, seed, n_boot=200):
    """对样本行做 iid bootstrap，返回 5% / 95% 分位。"""
    rng = np.random.default_rng(int(seed))
    n = int(p.size)
    reps = []
    for _ in range(int(n_boot)):
        idx = rng.integers(0, n, size=n)
        try:
            value = fit_fn(p[idx], impact[idx], sigma[idx])
        except ValueError:
            continue
        reps.append(value)
    if len(reps) < 20:
        return None, None
    return (float(np.percentile(reps, 5.0)),
            float(np.percentile(reps, 95.0)))


def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    return value


def assemble_decay_curve(panels, h_m=20, n_bootstrap=1000, block_size=3,
                         seed=0):
    """按 DESIGN §3/§4.4 装配衰减曲线 payload；无 A 矩阵时返回 None。

    A 矩阵来自 ``panels["decay_a_by_period"]``（形成期 t0 冻结权重的累计超额）。
    CI 只按形成期重采（INV-8），主 CI 取 ``block_size=3``，b=1/6 作敏感性附表。
    """
    from ...effect_size import stationary_bootstrap_indices
    from ..core.decay import decay_multiplier, fit_phi, net_ci, net_point

    rows = panels.get("decay_a_by_period")
    if not rows:
        return None
    mat = np.asarray(rows, dtype=float)
    if mat.ndim != 2 or not mat.shape[0] or not mat.shape[1]:
        return None
    h_max = mat.shape[1]
    if panels.get("decay_h_max") is not None:
        h_max = min(int(panels["decay_h_max"]), h_max)
    hm = int(h_m)
    if hm <= 0 or h_max < hm:
        return None
    mat = mat[:, :h_max]
    n_periods = int(mat.shape[0])
    horizons = [5, 10, 20]
    warnings = []  # type: List[str]

    a_mean = {}  # type: Dict[int, float]
    a_median = {}  # type: Dict[int, float]
    n_by_h = {}  # type: Dict[int, int]
    for h in range(1, h_max + 1):
        col = mat[:, h - 1]
        ok = np.isfinite(col)
        n_by_h[h] = int(ok.sum())
        a_mean[h] = float(col[ok].mean()) if ok.any() else float("nan")
        a_median[h] = float(np.median(col[ok])) if ok.any() else float("nan")
    m_point = decay_multiplier(a_mean, hm)
    degenerate = not np.isfinite(a_mean[hm]) or a_mean[hm] <= 0.0

    def _nanmean_rows(block):
        valid = np.isfinite(block)
        counts = valid.sum(axis=1)
        sums = np.where(valid, block, 0.0).sum(axis=1)
        out = np.full(block.shape[0], float("nan"))
        good = counts > 0
        out[good] = sums[good] / counts[good]
        return out

    def _boot(block):
        idx = stationary_bootstrap_indices(
            n_periods, n_bootstrap, block, seed)
        a_b = dict((h, _nanmean_rows(mat[:, h - 1][idx]))
                   for h in range(1, h_max + 1))
        base = a_b[hm]
        good = np.isfinite(base) & (base > 0.0)
        m_b = {}
        for h in range(1, h_max + 1):
            if h == hm:
                m_b[h] = np.where(good, 1.0, float("nan"))
            else:
                with np.errstate(divide="ignore", invalid="ignore"):
                    vals = a_b[h] / (base * float(h) / float(hm))
                m_b[h] = np.where(good, vals, float("nan"))
        return a_b, m_b

    def _quantiles(values):
        vals = np.asarray(values, dtype=float)
        vals = vals[np.isfinite(vals)]
        if vals.size == 0:
            return float("nan"), float("nan")
        lo, hi = np.quantile(vals, [0.025, 0.975])
        return float(lo), float(hi)

    a_boot = None  # type: Optional[Dict[int, np.ndarray]]
    m_boot = None
    if not degenerate:
        try:
            a_boot, m_boot = _boot(block_size)
        except Exception:
            a_boot, m_boot = None, None
            warnings.append("decay_ci_analytic_fallback")

    a_out = {}
    m_out = {}
    net_out = {}
    for h in horizons:
        if a_boot is not None:
            a_lo, a_hi = _quantiles(a_boot[h])
            m_lo, m_hi = _quantiles(m_boot[h])
        else:
            a_lo = a_hi = m_lo = m_hi = float("nan")
        a_out[str(h)] = {"point": float(a_mean[h]),
                         "median": float(a_median[h]),
                         "lo": a_lo, "hi": a_hi}
        m_out[str(h)] = {"point": float(m_point[h]),
                         "lo": m_lo, "hi": m_hi}

    aum = panels.get("aum")
    if aum is None:
        aum = panels.get("aum_ref", 1e10)
    aum = float(aum)
    cost_by_h = dict((int(k), float(v))
                     for k, v in (panels.get("cost_by_h") or {}).items())

    if not degenerate and a_boot is not None:
        net_out = net_ci(a_boot, m_boot, aum, cost_by_h, a_mean, hm)
        net_out = dict((str(h), dict((k, float(v)) for k, v in item.items()))
                       for h, item in net_out.items())
    elif not degenerate:
        # bootstrap 异常 → 按形成期 t 分布解析近似（39 期 t≈2.02）
        nu = max(int(n_by_h.get(hm, 0)) - 1, 1)
        z = 1.959963984540054
        t_crit = (z + (z ** 3 + z) / (4.0 * nu)
                  + (5 * z ** 5 + 16 * z ** 3 + 3 * z) / (96.0 * nu ** 2))
        point = net_point(a_mean[hm], aum, m_point, cost_by_h)
        for h in horizons:
            if h not in cost_by_h:
                continue
            col = mat[:, h - 1]
            ok = np.isfinite(col)
            se_a = (float(np.std(col[ok], ddof=1) / np.sqrt(ok.sum()))
                    if ok.sum() > 1 else float("nan"))
            scale = a_mean[hm] * float(h) / float(hm)
            m_se = se_a / scale if np.isfinite(se_a) and scale > 0 else float("nan")
            net_out[str(h)] = {
                "point": float(point[h]),
                "lo": float(aum * (a_mean[h] - t_crit * se_a)
                            - cost_by_h[h]),
                "hi": float(aum * (a_mean[h] + t_crit * se_a)
                            - cost_by_h[h])}
            m_out[str(h)]["lo"] = float(m_point[h] - t_crit * m_se)
            m_out[str(h)]["hi"] = float(m_point[h] + t_crit * m_se)
            if not np.isfinite(m_se):
                m_out[str(h)]["lo"] = float("nan")
                m_out[str(h)]["hi"] = float("nan")
    else:
        for h in horizons:
            net_out[str(h)] = {"point": float("nan"), "lo": float("nan"),
                               "hi": float("nan")}

    phi_status = "unidentified"
    decay_source = "empirical"
    phi = 1.0
    n_anchor = int(n_by_h.get(hm, 0))
    if degenerate:
        warnings.append("decay_curve_unidentified")
    elif n_anchor < 10:
        phi = float(2 ** (-1.0 / 126.0))
        phi_status = "prior"
        decay_source = "prior"
        warnings.append("decay_prior_fallback")
    else:
        try:
            phi, _ = fit_phi(a_mean, hm)
            phi_status = "fitted"
        except ValueError:
            phi = 1.0
            phi_status = "unidentified"
            warnings.append("decay_phi_fit_failed")
    if 10 <= n_anchor < 39:
        warnings.append("decay_small_sample")

    m_sensitivity = {}
    for block in (1, 6):
        try:
            _, m_b = _boot(block)
        except Exception:
            m_sensitivity[str(block)] = {}
            continue
        item = {}
        for h in horizons:
            lo, hi = _quantiles(m_b[h])
            item[str(h)] = {"lo": lo, "hi": hi}
        m_sensitivity[str(block)] = item

    verdict = {}
    for h in (5, 10):
        lo = m_out[str(h)]["lo"]
        hi = m_out[str(h)]["hi"]
        if degenerate or not (np.isfinite(lo) and np.isfinite(hi)):
            verdict[str(h)] = "unidentified"
        elif hi < 1.0:
            verdict[str(h)] = "posterior"
        elif lo > 1.0:
            verdict[str(h)] = "anterior"
        else:
            verdict[str(h)] = "flat"

    alpha0 = a_mean[hm]
    return {
        "h_m": hm,
        "n_periods": n_periods,
        "alpha0_anchored": float(alpha0) if np.isfinite(alpha0) else None,
        "alpha0_calendar": panels.get("alpha0"),
        "phi": float(phi),
        "phi_status": phi_status,
        "decay_source": decay_source,
        "horizons": horizons,
        "m": m_out,
        "a": a_out,
        "net": net_out,
        "boot": {"block": int(block_size), "reps": int(n_bootstrap),
                 "sensitivity": [1, 6], "seed": int(seed)},
        "verdict": verdict,
        "evidence_warnings": warnings,
        "n_by_h": dict((str(h), int(v)) for h, v in n_by_h.items()),
        "m_sensitivity": m_sensitivity,
    }


def run_calibration(cfg, capacity_fn=None, breakeven_fn=None, panels=None):
    """编排 E1-E6；``panels`` 为可注入的合成面板（测试缝）。"""
    if str(getattr(cfg, "block_size_mode", "auto")) != "auto":
        raise ValueError("block_size_mode 仅支持 'auto'（v3.8.1）")
    panels = dict(panels or {})
    pipeline = build_pipeline(cfg)
    evidence_level = (panels.get("evidence_level")
                      or resolve_evidence_level(cfg))
    warnings = []  # type: List[str]

    models_out = {}  # type: Dict[str, dict]
    selection = {"primary": None, "tied": []}
    c_info = {"c_default": 0.5, "c_calib_point": None,
              "c_calib_lower": None, "c_calib_upper": None,
              "c_calib_stress": 0.5}
    b_info = {"b_hat": None, "ci": [None, None]}

    samples = panels.get("impact_samples")
    if samples:
        p = np.asarray(samples["p"], dtype=float)
        impact = np.asarray(samples["impact"], dtype=float)
        sigma = np.asarray(samples["sigma"], dtype=float)
        for name, model in pipeline["impact"].items():
            try:
                params = model.fit(p, impact, sigma)
            except ValueError:
                params = None
            models_out[name] = {"params": _jsonable(params), "cv_rmse": None,
                                "r2": None}
        cv = cross_val_rmse(list(pipeline["impact"].values()),
                            p, impact, sigma)
        for name, value in cv.items():
            models_out[name]["cv_rmse"] = (
                None if not np.isfinite(value) else float(value))
        primary, tied = select_models(cv)
        selection = {"primary": primary, "tied": list(tied)}
        sqrt_params = models_out["sqrt"]["params"]
        if sqrt_params:
            point = float(sqrt_params["c"])
            lower, upper = _bootstrap_ci(
                lambda a, b, c: SqrtImpact().fit(a, b, c)["c"],
                p, impact, sigma, cfg.seed)
            if lower is None:
                lower, upper = point, point
                warnings.append("c 的 bootstrap CI 不足 20 次有效重抽样")
            c_info = c_triplet(point, lower, upper)
            r2 = float(fit_r2(
                SqrtImpact().predict(p, sigma, sqrt_params), impact))
            ident = bool(r2 >= C_R2_MIN
                         and C_RANGE[0] <= point <= C_RANGE[1])
            models_out["sqrt"]["r2"] = r2
            c_info.update({"c_r2": r2, "c_identifiable": ident,
                           "c_effective": point if ident else 0.5})
            if not ident:
                warnings.append(
                    "c 不可识别（r2<%.2f 或超出 %s），容量按默认 0.5"
                    % (C_R2_MIN, C_RANGE))
        else:
            warnings.append("sqrt 模型拟合失败，c 不可校准")
        power_params = models_out["power"]["params"]
        if power_params:
            b_point = float(power_params["b"])
            b_lo, b_hi = _bootstrap_ci(
                lambda a, b, c: PowerImpact().fit(a, b, c)["b"],
                p, impact, sigma, cfg.seed + 1)
            b_info = {"b_hat": b_point,
                      "ci": [b_lo if b_lo is not None else b_point,
                             b_hi if b_hi is not None else b_point]}

    lam_ratio = None
    pvalues = panels.get("lambda_pvalues")
    if pvalues is not None:
        arr = np.asarray(pvalues, dtype=float)
        arr = arr[np.isfinite(arr)]
        if arr.size:
            lam_ratio = float(np.mean(arr < cfg.lambda_p_threshold))

    ts = None
    temp = panels.get("temporary")
    if temp:
        ts = list(temporary_share(
            np.asarray(temp["r1"], dtype=float),
            np.asarray(temp["rev1"], dtype=float)))

    aum_ref = float(panels.get("aum_ref", 1e10))
    cap = float(panels.get("cap", cfg.p_cap))
    regime_p95 = panels.get("regime_p95") or {}
    regimes = {}
    scenarios = {}
    if capacity_fn and regime_p95:
        regimes = {k: float(capacity_fn(float(v), aum_ref, cap))
                   for k, v in sorted(regime_p95.items())}
        scenarios = {("%.1f" % k): apply_kappa(
            max(regime_p95.values()), aum_ref, cap, k, capacity_fn)
            for k in sorted(set((1.0, float(cfg.kappa), 2.0)))}
    reg = regime_capacity(regimes)
    window_capacity = panels.get("window_capacity") or {}
    avew = average_capacity(list(window_capacity.values()))
    warnings.extend(avew["evidence_warnings"])

    rho = 1.0
    rho_lo, rho_hi = 1.0, 1.0
    series = panels.get("rho_series")
    if series is not None:
        try:
            rho, rho_lo, rho_hi = estimate_rho(np.asarray(series, dtype=float))
        except ValueError as exc:
            warnings.append("decay: rho 不可估（%s），按 1.0" % exc)
        if float(rho) <= 0.0:
            rho, rho_lo, rho_hi = 1.0, 1.0, 1.0
            warnings.append("decay: rho<=0（无正持续性），按无衰减处理")
    net = {}
    plat = []  # type: List[int]
    if panels.get("cost_by_h") and panels.get("alpha0") is not None:
        net = net_curve(float(panels["alpha0"]),
                        float(panels.get("aum", aum_ref)), rho,
                        panels["cost_by_h"])
        plat = plateau(net, float(panels.get("plateau_sd", 0.0)))
        warnings.append("net(h) 仅含提供成本口径的持有期")

    hl = half_life(rho)
    exec_info = None
    if panels.get("notional") is not None and panels.get("adv") is not None:
        days = execution_days(
            np.asarray(panels["notional"], dtype=float),
            np.asarray(panels["adv"], dtype=float),
            p_cap=cfg.p_cap, d_max=cfg.d_max)
        exec_info = {
            "days": [None if not np.isfinite(v) else float(v) for v in days],
            "d_max": cfg.d_max,
            "p_cap": cfg.p_cap,
            "trigger_rate": float(np.mean(~np.isfinite(days))),
            "n": int(days.size),
        }
    decay_out = {
        "rho": float(rho), "rho_ci": [float(rho_lo), float(rho_hi)],
        "half_life": None if not np.isfinite(hl) else float(hl),
        "retention": {str(h): float(v) for h, v in zip(
            (1, 5, 20), retention((1, 5, 20), rho))},
        "net": {str(h): float(v) for h, v in net.items()},
        "plateau": list(plat),
        "execution": exec_info,
    }

    result = {
        "evidence_level": evidence_level,
        "config_hash": cfg.config_hash(),
        "models": models_out,
        "selection": selection,
        "c": c_info,
        "power_b": b_info,
        "lambda_significant_ratio": lam_ratio,
        "temporary_share": ts,
        "temporary_basis": panels.get("temporary_basis"),
        "kappa": float(cfg.kappa),
        "capacity": {
            "regimes": reg["regimes"],
            "min_regime": reg["min_regime"],
            "median": reg["median"],
            "scenarios": scenarios,
            "avew": {"avew": avew["avew"], "weights": avew["weights"],
                     "spread": avew["spread"],
                     "degraded": avew["degraded"],
                     "primary": avew["primary"]},
        },
        "decay": decay_out,
        "ratio_diagnostics": ratio_diagnostics(
            c_calib=c_info.get("c_calib_point")),
        "evidence_warnings": warnings,
    }
    return _jsonable(result)
