# -*- coding: utf-8 -*-
"""v3.8.0 成交方向分类（BVC）与一字板识别。

设计依据：DESIGN §6.3；实施依据：EXECUTION §2.7。
"""
import math

import numpy as np

__all__ = ["normal_cdf", "BVC", "detect_limit_lock", "rolling_sigma"]


def normal_cdf(x):
    """标准正态 CDF（math.erf 向量化，不依赖 scipy）。"""
    arr = np.asarray(x, dtype=float)
    flat = arr.ravel()
    out = np.empty(flat.size, dtype=float)
    inv_sqrt2 = 1.0 / math.sqrt(2.0)
    for i, value in enumerate(flat):
        out[i] = 0.5 * (1.0 + math.erf(float(value) * inv_sqrt2))
    return out.reshape(arr.shape)


def rolling_sigma(ret, window):
    """过去 ``window`` 个 bar（含当前）的样本标准差；无前视。"""
    arr = np.asarray(ret, dtype=float).ravel()
    n = arr.size
    out = np.full(n, np.nan)
    if window is None or int(window) < 2:
        return out
    w = int(window)
    for t in range(w - 1, n):
        seg = arr[t - w + 1:t + 1]
        out[t] = np.std(seg, ddof=1)
    return out


class BVC(object):
    """Bulk Volume Classification：买入量占比 Φ(r / sigma)。"""

    name = "bvc"

    def classify(self, ret, volume, sigma):
        r = np.asarray(ret, dtype=float).ravel()
        s = np.asarray(sigma, dtype=float).ravel()
        if s.size != r.size:
            raise ValueError("ret 与 sigma 长度不一致")
        frac = np.full(r.size, 0.5)
        ok = np.isfinite(r) & np.isfinite(s) & (s > 0.0)
        if ok.any():
            frac[ok] = normal_cdf(r[ok] / s[ok])
        zero = (~np.isfinite(r)) | (r == 0.0)
        frac[zero] = 0.5
        return np.clip(frac, 0.0, 1.0)


def detect_limit_lock(high, low, close, open_, volume):
    """一字板：high==low，或 开=收=高=低 且 成交量为 0。"""
    h = np.asarray(high, dtype=float).ravel()
    l = np.asarray(low, dtype=float).ravel()
    c = np.asarray(close, dtype=float).ravel()
    o = np.asarray(open_, dtype=float).ravel()
    v = np.asarray(volume, dtype=float).ravel()
    flat = (h == l)
    frozen = (v == 0.0) & (o == c) & (c == h) & (c == l)
    return np.asarray(flat | frozen, dtype=bool)
