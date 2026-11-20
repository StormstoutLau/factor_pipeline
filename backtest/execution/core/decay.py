# -*- coding: utf-8 -*-
"""v3.8.0 α 衰减 / net(h) / 执行天数。

设计依据：DESIGN §7 §10；实施依据：EXECUTION §2.8。
v3.9.3 追加累计 alpha 衰减模型（FO-1）：非参乘子 / 单参数累计比 / 两端口实现。
新符号不进入 ``__all__``（架构测试要求 <= 5 项，DR-3），由调用方显式导入。
"""
import math
from dataclasses import dataclass
from typing import Dict, List, Mapping, Sequence, Tuple

import numpy as np

__all__ = ["estimate_rho", "retention", "half_life", "execution_days",
           "net_curve"]


def estimate_rho(series):
    """AR(1) + HAC SE；95% CI 覆盖 1.0 时返回 (1.0, lo, hi)。"""
    from ...effect_size import newey_west_se

    x = np.asarray(series, dtype=float).ravel()
    if x.size < 3:
        raise ValueError("series 长度必须 >= 3")
    if float(np.ptp(x)) == 0.0:
        raise ValueError("series 为常数序列（H1 惯例）")
    x0 = x[:-1] - x[:-1].mean()
    x1 = x[1:] - x[1:].mean()
    denom = float(np.dot(x0, x0))
    if denom <= 0.0:
        raise ValueError("series 方差为 0")
    rho = float(np.clip(np.dot(x0, x1) / denom, -1.0, 1.0))
    resid = x1 - rho * x0
    score = x0 * resid
    se = 0.0
    if float(np.ptp(score)) > 0.0:
        try:
            nw = newey_west_se(score)
            se = float(nw["se"]) * score.size / denom
        except ValueError:
            se = 0.0
    lo = rho - 1.96 * se
    hi = rho + 1.96 * se
    if lo <= 1.0 <= hi:
        return 1.0, float(lo), float(hi)
    return rho, float(lo), float(hi)


def retention(horizons, rho):
    """alpha 保留率 rho ** h。"""
    hs = np.asarray(list(horizons), dtype=float)
    return np.power(float(rho), hs)


def half_life(rho):
    """半衰期 ln(0.5)/ln(rho)；rho>=1 -> inf，rho<=0 -> nan。"""
    r = float(rho)
    if r >= 1.0:
        return float("inf")
    if r <= 0.0:
        return float("nan")
    return float(math.log(0.5) / math.log(r))


def execution_days(notional, adv, p_cap=0.10, d_max=5):
    """D_i = ceil(notional / (p_cap * adv))；> d_max 记 NaN（未成交）。"""
    n = np.asarray(notional, dtype=float).ravel()
    a = np.asarray(adv, dtype=float).ravel()
    if n.size != a.size:
        raise ValueError("notional 与 adv 长度不一致")
    out = np.full(n.size, np.nan)
    if p_cap <= 0.0:
        raise ValueError("p_cap 必须 > 0")
    ok = np.isfinite(n) & np.isfinite(a) & (n > 0.0) & (a > 0.0)
    days = np.ceil(n[ok] / (float(p_cap) * a[ok]))
    days = np.where(days > float(d_max), np.nan, days)
    out[ok] = days
    return out


def net_curve(alpha0, aum, rho, cost_by_h, horizons=(1, 5, 10, 20, 60)):
    """net(h) = aum * alpha0 * rho**h - cost(h)；仅输出给定成本的 h。"""
    out = {}  # type: Dict[int, float]
    for h in horizons:
        if h not in cost_by_h:
            continue
        out[int(h)] = float(
            aum * alpha0 * (float(rho) ** int(h)) - float(cost_by_h[h]))
    return out


def plateau(net, sd):
    """净收益在 [max-sd, max] 内的持有期集合（含 h*）。"""
    if not net:
        return []
    h_star = max(net, key=lambda h: net[h])
    threshold = float(net[h_star]) - float(sd)
    return sorted(int(h) for h, v in net.items() if float(v) >= threshold)


class ExponentialDecay(object):
    """DecayModel 端口的唯一具体实现：retention(h) = rho ** h。"""

    name = "exponential"

    def __init__(self, rho):
        self.rho = float(rho)

    def retention(self, horizons):
        return retention(horizons, self.rho)


# ---- v3.9.3 累计 alpha 衰减（FO-1）------------------------------------
# 入参口径：除 EmpiricalDecay 收 m̂ 映射外，其余函数均收 A 曲线（累计超额）。

_TOL = 1e-12


def _curve_dict(curve, h_m=None):
    """曲线映射归一到 {int h: float}；h_m 缺失即报错。"""
    out = {}
    for key, value in dict(curve).items():
        h = int(key)
        if float(key) != float(h):
            raise ValueError("curve 的 h 必须是整数: %r" % (key,))
        out[h] = float(value)
    if h_m is not None and int(h_m) not in out:
        raise ValueError("curve 缺少 h_m=%d" % int(h_m))
    return out


def decay_multiplier(curve, h_m=20):
    """非参乘子 m(h)=A(h)/[A(h_m)·h/h_m]；返回 {h: m}，强制 m[h_m]=1。

    A(h_m) 非有限或 <=0 时返回全 NaN（由调用方标 unidentified，DESIGN §7）。
    """
    a = _curve_dict(curve, h_m)
    hm = int(h_m)
    base = float(a[hm])
    if not np.isfinite(base) or base <= 0.0:
        return dict((h, float("nan")) for h in a)
    out = {}
    for h, value in a.items():
        if h == hm:
            out[h] = 1.0
            continue
        scale = base * float(h) / float(hm)
        ok = bool(np.isfinite(value)) and scale > 0.0
        out[h] = float(value / scale) if ok else float("nan")
    return out


def anchored_multiplier(phi, horizons, h_m=20):
    """参数乘子 m(h;φ)=(h_m/h)(1−φ^h)/(1−φ^{h_m})；φ==1 → 全 1。"""
    phi = float(phi)
    hm = int(h_m)
    if not (0.0 < phi <= 1.0):
        raise ValueError("phi 必须在 (0, 1] 内")
    if hm <= 0:
        raise ValueError("h_m 必须 > 0")
    hs = [int(h) for h in horizons]
    if phi == 1.0:
        return dict((h, 1.0) for h in hs)
    denom = 1.0 - phi ** hm
    out = {}
    for h in hs:
        if h == hm:
            out[h] = 1.0
            continue
        if h <= 0:
            raise ValueError("horizon 必须 > 0: %r" % (h,))
        out[h] = float((float(hm) / float(h)) * (1.0 - phi ** h) / denom)
    return out


def fit_phi(curve, h_m=20, grid=(0.01, 1.0), step=0.001, refine=10):
    """h∈{1..h_m} 上等权 SSE 拟合 φ（网格 → 局部精化）；返回 (phi, sse)。

    预注册（DESIGN §2 D2）：网格 [0.01, 1.0] 步长 0.001，最优网格点 ±step 内以
    step/refine 再细分一次；等权、不按 h 加权。可拟合 h 少于 2 个即 ValueError。
    """
    m_hat = decay_multiplier(curve, h_m)
    hs = [h for h in sorted(m_hat)
          if 1 <= h <= int(h_m) and np.isfinite(m_hat[h])]
    if len(hs) < 2:
        raise ValueError("可用于拟合的 h 不足 2 个")
    target = np.array([m_hat[h] for h in hs], dtype=float)
    lo, hi = float(grid[0]), float(grid[1])
    if not (0.0 < lo < hi <= 1.0):
        raise ValueError("grid 必须满足 0 < lo < hi <= 1")
    step = float(step)
    if step <= 0.0:
        raise ValueError("step 必须 > 0")

    def _sse(phi):
        pred = anchored_multiplier(phi, hs, h_m)
        fitted = np.array([pred[h] for h in hs], dtype=float)
        resid = target - fitted
        return float(np.dot(resid, resid))

    best_phi, best_sse, best_arg = 1.0, float("inf"), hi
    for value in np.arange(lo, hi + step * 0.5, step):
        phi = float(min(float(value), hi))
        sse = _sse(phi)
        if sse < best_sse:
            best_phi, best_sse, best_arg = phi, sse, phi
    span = step / float(refine)
    start, stop = max(lo, best_arg - step), min(hi, best_arg + step)
    for value in np.arange(start, stop + span * 0.5, span):
        sse = _sse(float(value))
        if sse < best_sse:
            best_phi, best_sse = float(value), sse
    return best_phi, best_sse


def net_point(alpha0, aum, m_by_h, cost_by_h):
    """net(h)=aum·alpha0·m(h)−cost(h)；点估计 {h: float}（未重采曲线）。"""
    out = {}
    for h, m in dict(m_by_h).items():
        h = int(h)
        if h not in cost_by_h:
            continue
        out[h] = float(aum) * float(alpha0) * float(m) - float(cost_by_h[h])
    return out


def net_ci(a_boot, m_boot, aum, cost_by_h, a_point, h_m=20, alpha=0.05):
    """{h: {"point","lo","hi"}}；point 取原始曲线，lo/hi 取重采样分位。

    a_boot / m_boot: ``{h: (reps,) 数组}``；a_point 为原始（未重采）A 曲线（DR-1）。
    """
    hm = int(h_m)
    if hm not in a_boot or hm not in m_boot:
        raise ValueError("a_boot/m_boot 缺少 h_m=%d" % hm)
    if not (0.0 < float(alpha) < 1.0):
        raise ValueError("alpha 必须在 (0, 1) 内")
    alpha_boot = np.asarray(a_boot[hm], dtype=float)
    point = net_point(float(dict(a_point)[hm]), aum,
                      decay_multiplier(a_point, hm), cost_by_h)
    out = {}
    for h in sorted(set(int(k) for k in m_boot) & set(int(k) for k in cost_by_h)):
        m_rep = np.asarray(m_boot[h], dtype=float)
        if m_rep.size != alpha_boot.size:
            raise ValueError("重采样样本长度不一致: h=%d" % h)
        values = float(aum) * alpha_boot * m_rep - float(cost_by_h[h])
        values = values[np.isfinite(values)]
        base = float(point.get(h, float("nan")))
        if values.size == 0:
            out[h] = {"point": base, "lo": float("nan"), "hi": float("nan")}
            continue
        lo, hi = np.quantile(values, [float(alpha) / 2.0,
                                      1.0 - float(alpha) / 2.0])
        out[h] = {"point": base, "lo": float(lo), "hi": float(hi)}
    return out


@dataclass(frozen=True)
class DecayCurve:
    h_m: int
    horizons: Tuple[int, ...]
    a_mean: Mapping[int, float]
    m_point: Mapping[int, float]
    m_lo: Mapping[int, float]
    m_hi: Mapping[int, float]
    phi: float
    phi_status: str
    n_periods: int
    boot: Mapping[str, object]


class AnchoredDecay(object):
    """DecayModel 实现：retention(h) = m(h;φ)。"""

    name = "anchored"

    def __init__(self, phi, h_m=20):
        self.phi = float(phi)
        self.h_m = int(h_m)

    def retention(self, horizons):
        hs = [int(h) for h in horizons]
        values = anchored_multiplier(self.phi, hs, self.h_m)
        return np.array([values[h] for h in hs], dtype=float)


class EmpiricalDecay(object):
    """DecayModel 实现：直接返回非参 m̂(h)；缺失 h 线性插值，h_m 强制 1。"""

    name = "empirical"

    def __init__(self, curve, h_m=20):
        self.h_m = int(h_m)
        self.curve = dict((int(h), float(v)) for h, v in dict(curve).items())
        self.curve[self.h_m] = 1.0

    def retention(self, horizons):
        hs = [int(h) for h in horizons]
        known = sorted(self.curve)
        return np.interp(hs, known, [self.curve[k] for k in known])

