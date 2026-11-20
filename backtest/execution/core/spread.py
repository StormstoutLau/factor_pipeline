# -*- coding: utf-8 -*-
"""v3.8.0 价差 / 非流动性代理（CS / AR / Amihud）。

设计依据：DESIGN §6；实施依据：EXECUTION §2.6。
"""
import numpy as np

__all__ = ["CorwinSchultz", "AbdiRanaldo", "Amihud"]

_DEN = 3.0 - 2.0 * np.sqrt(2.0)


def _fill_zero_range(high, low):
    """零区间日按 CS 原文用前一日 h/l 平移（无前日时用后一日）。"""
    h = np.array(high, dtype=float, copy=True)
    l = np.array(low, dtype=float, copy=True)
    n = h.size
    zero = (h == l)
    if not zero.any() or zero.all():
        return h, l
    idx = np.flatnonzero(zero)
    for i in idx:
        j = i - 1
        while j >= 0 and zero[j]:
            j -= 1
        if j >= 0:
            h[i], l[i] = h[j], l[j]
            continue
        k = i + 1
        while k < n and zero[k]:
            k += 1
        if k < n:
            h[i], l[i] = h[k], l[k]
    return h, l


class CorwinSchultz(object):
    """两日修正版 Corwin-Schultz（按日序列输出，长度同为 n）。"""

    name = "corwin_schultz"

    def estimate(self, high, low, close):
        h = np.asarray(high, dtype=float).ravel()
        l = np.asarray(low, dtype=float).ravel()
        n = h.size
        if n < 3:
            return np.full(n, np.nan)
        h, l = _fill_zero_range(h, l)
        h0, l0 = h[:-1], l[:-1]
        h1, l1 = h[1:], l[1:]
        beta = np.log(h0 / l0) ** 2 + np.log(h1 / l1) ** 2
        gamma = np.log(np.maximum(h0, h1) / np.minimum(l0, l1)) ** 2
        alpha = ((np.sqrt(2.0 * beta) - np.sqrt(beta)) / _DEN
                 - np.sqrt(gamma / _DEN))
        spread = 2.0 * (np.exp(alpha) - 1.0) / (1.0 + np.exp(alpha))
        spread = np.maximum(spread, 0.0)
        out = np.empty(n, dtype=float)
        out[:-1] = spread
        out[-1] = spread[-1]
        return out

    def zero_ratio(self, high, low):
        """零区间日占比（用于损耗守卫）。"""
        h = np.asarray(high, dtype=float).ravel()
        l = np.asarray(low, dtype=float).ravel()
        if h.size == 0:
            return 0.0
        return float(np.mean(h == l))


class AbdiRanaldo(object):
    """CHL 乘积型：S^2 = 4 E[(c_t - eta_t)(c_t - eta_{t+1})]。"""

    name = "abdi_ranaldo"

    def estimate(self, high, low, close):
        h = np.asarray(high, dtype=float).ravel()
        l = np.asarray(low, dtype=float).ravel()
        c = np.asarray(close, dtype=float).ravel()
        n = c.size
        if n < 3 or h.size != n or l.size != n:
            return np.full(n, np.nan)
        with np.errstate(divide="ignore", invalid="ignore"):
            lc = np.log(c)
            eta = 0.5 * (np.log(h) + np.log(l))
        prod = (lc[:-1] - eta[:-1]) * (lc[:-1] - eta[1:])
        vals = np.sqrt(np.maximum(4.0 * prod, 0.0))
        out = np.empty(n, dtype=float)
        out[:-1] = vals
        out[-1] = np.nan
        return out


class Amihud(object):
    """|r| / amount（仅排序用，非价差估计）。"""

    name = "amihud"

    def estimate(self, ret, amount):
        r = np.asarray(ret, dtype=float).ravel()
        a = np.asarray(amount, dtype=float).ravel()
        n = r.size
        if n < 3 or a.size != n:
            return np.full(n, np.nan)
        out = np.full(n, np.nan)
        ok = np.isfinite(r) & np.isfinite(a) & (a > 0.0)
        out[ok] = np.abs(r[ok]) / a[ok]
        return out
