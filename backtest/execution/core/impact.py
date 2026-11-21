# -*- coding: utf-8 -*-
"""v3.8.0 冲击模型（sqrt / linear / log / power）与选型。

设计依据：DESIGN §5；实施依据：EXECUTION §2.5。
``p`` 为参与率比例；输出为价格比率（非 bps）。
"""
from typing import Dict, List, Mapping, Sequence, Tuple

import numpy as np

__all__ = ["SqrtImpact", "LinearImpact", "LogImpact", "PowerImpact",
           "select_models"]

C_R2_MIN = 0.05
C_RANGE = (0.1, 2.0)


def fit_r2(pred, y):
    """过原点拟合 R² = 1 - SSE/SST；非有限或 SST==0 -> 0.0。"""
    p = np.asarray(pred, dtype=float).ravel()
    t = np.asarray(y, dtype=float).ravel()
    if p.size != t.size or p.size == 0:
        return 0.0
    ok = np.isfinite(p) & np.isfinite(t)
    if not np.any(ok):
        return 0.0
    sse = float(np.sum((t[ok] - p[ok]) ** 2))
    sst = float(np.sum((t[ok] - t[ok].mean()) ** 2))
    if sst <= 0.0:
        return 0.0
    return float(1.0 - sse / sst)


def _as_1d(values):
    return np.asarray(values, dtype=float).ravel()


def _validate_p(p):
    arr = _as_1d(p)
    if arr.size == 0:
        raise ValueError("参与率不能为空")
    if not np.all(np.isfinite(arr)):
        raise ValueError("参与率含 NaN/Inf")
    if np.any(arr <= 0.0):
        raise ValueError("参与率必须 > 0（log/power 无定义）")
    return arr


def _validate_fit(p, impact, sigma):
    arr_p = _validate_p(p)
    arr_i = _as_1d(impact)
    arr_s = _as_1d(sigma)
    if not (arr_p.size == arr_i.size == arr_s.size):
        raise ValueError("p / impact / sigma 长度不一致")
    if not np.all(np.isfinite(arr_i)):
        raise ValueError("impact 含 NaN/Inf")
    if float(np.ptp(arr_i)) == 0.0:
        raise ValueError("impact 为常数序列，无法拟合（H1 惯例）")
    return arr_p, arr_i, arr_s


def _clip_p(p):
    return np.minimum(_validate_p(p), 1.0)


class SqrtImpact(object):
    """frac = c * sigma * sqrt(p)（现行中央口径）。"""

    name = "sqrt"

    def predict(self, participation, sigma, params):
        p = _clip_p(participation)
        s = _as_1d(sigma)
        if s.size != p.size:
            raise ValueError("sigma 与 participation 长度不一致")
        return float(params["c"]) * s * np.sqrt(p)

    def fit(self, participation, impact, sigma):
        p, y, s = _validate_fit(participation, impact, sigma)
        if np.any(s <= 0.0):
            raise ValueError("sqrt 拟合需要 sigma > 0")
        x = s * np.sqrt(p)
        denom = float(np.dot(x, x))
        if denom <= 0.0:
            raise ValueError("设计矩阵退化")
        return {"c": float(np.dot(x, y) / denom)}


class LinearImpact(object):
    """frac = k * p（现行对照口径）。"""

    name = "linear"

    def predict(self, participation, sigma, params):
        p = _clip_p(participation)
        return float(params["k"]) * p

    def fit(self, participation, impact, sigma):
        p, y, _ = _validate_fit(participation, impact, sigma)
        denom = float(np.dot(p, p))
        if denom <= 0.0:
            raise ValueError("设计矩阵退化")
        return {"k": float(np.dot(p, y) / denom)}


class LogImpact(object):
    """frac = max(0, a + b ln p)（level 对 log，非 log-log）。"""

    name = "log"

    def predict(self, participation, sigma, params):
        p = _clip_p(participation)
        return np.maximum(0.0, float(params["a"]) + float(params["b"]) * np.log(p))

    def fit(self, participation, impact, sigma):
        p, y, _ = _validate_fit(participation, impact, sigma)
        logp = np.log(p)
        if np.unique(np.round(logp, 12)).size < 2:
            raise ValueError("log 拟合需要至少两个参与率档")
        design = np.column_stack([np.ones_like(logp), logp])
        coef, _, _, _ = np.linalg.lstsq(design, y, rcond=None)
        a, b = float(coef[0]), float(coef[1])
        if a + b * float(np.min(logp)) <= 0.0:
            raise ValueError("log 模型在 p_min 处非正，标记 invalid")
        return {"a": a, "b": b}


class PowerImpact(object):
    """frac = a * p^b（b 自由）。"""

    name = "power"

    def predict(self, participation, sigma, params):
        p = _clip_p(participation)
        return float(params["a"]) * np.power(p, float(params["b"]))

    def fit(self, participation, impact, sigma):
        p, y, _ = _validate_fit(participation, impact, sigma)
        if np.any(y <= 0.0):
            raise ValueError("power 拟合需要 impact > 0（log-log）")
        logp = np.log(p)
        logy = np.log(y)
        if np.unique(np.round(logp, 12)).size < 2:
            raise ValueError("power 拟合需要至少两个参与率档")
        b = float(np.dot(logp - logp.mean(), logy - logy.mean())
                  / np.dot(logp - logp.mean(), logp - logp.mean()))
        a = float(np.exp(logy.mean() - b * logp.mean()))
        return {"a": a, "b": b}


def cross_val_rmse(models, participation, impact, sigma, n_folds=5):
    """按时间顺序切折的 CV-RMSE；拟合失败模型记 ``inf``。"""
    p = _validate_p(participation)
    y = _as_1d(impact)
    s = _as_1d(sigma)
    if not (p.size == y.size == s.size):
        raise ValueError("p / impact / sigma 长度不一致")
    n = int(p.size)
    folds = max(2, min(int(n_folds), n))
    blocks = np.array_split(np.arange(n), folds)
    out = {}  # type: Dict[str, float]
    for model in models:
        errs = []
        try:
            for block in blocks:
                mask = np.ones(n, dtype=bool)
                mask[block] = False
                params = model.fit(p[mask], y[mask], s[mask])
                pred = model.predict(p[block], s[block], params)
                errs.append(float(np.sum((pred - y[block]) ** 2)))
            out[model.name] = float(np.sqrt(np.mean(errs)))
        except (ValueError, FloatingPointError):
            out[model.name] = float("inf")
    return out


def select_models(cv, tol=0.10):
    """主模型 = argmin CV；并列 = CV <= (1+tol)*min。"""
    finite = {k: float(v) for k, v in cv.items() if np.isfinite(v)}
    if not finite:
        raise ValueError("无可用模型（CV 全部非有限）")
    best = min(finite.values())
    primary = min((k for k, v in finite.items() if v == best),
                  key=lambda k: list(cv).index(k))
    threshold = (1.0 + float(tol)) * best
    tied = [k for k, v in cv.items()
            if np.isfinite(v) and float(v) <= threshold]
    order = {name: i for i, name in enumerate(cv)}
    tied.sort(key=lambda k: order[k])
    return primary, tied


def temporary_share(r1, rev1):
    """T+1 reversal 分离；返回 (share, ci_lo, ci_hi)。

    share = clip(-cov(r1, rev1) / var(r1), 0, 1)；
    CI 用 stationary bootstrap（块长 auto_block_size，seed 固定）。
    """
    from .bootstrap import auto_block_size

    a = _as_1d(r1)
    b = _as_1d(rev1)
    if a.size != b.size:
        raise ValueError("r1 与 rev1 长度不一致")
    if a.size < 3:
        raise ValueError("样本不足 3")
    if float(np.ptp(a)) == 0.0:
        raise ValueError("r1 为常数序列（H1 惯例）")

    def _share(x, y):
        xc = x - x.mean()
        yc = y - y.mean()
        denom = float(np.dot(xc, xc))
        if denom <= 0.0:
            return 0.0
        return float(np.clip(-np.dot(xc, yc) / denom, 0.0, 1.0))

    point = _share(a, b)
    from ...effect_size import stationary_bootstrap_indices

    block = auto_block_size(a)
    idx = stationary_bootstrap_indices(
        a.size, n_bootstrap=1000, block_size=block, seed=20261118)
    reps = np.array([_share(a[row], b[row]) for row in idx])
    lo = float(np.clip(np.percentile(reps, 2.5), 0.0, 1.0))
    hi = float(np.clip(np.percentile(reps, 97.5), 0.0, 1.0))
    return point, min(lo, point), max(hi, point)


def _degraded_reversal(n=0, n_months=0):
    """退化结构：share=0、bps 三值 NaN、degraded=True（不抛异常）。"""
    nan = float("nan")
    return {
        "temporary_share": [0.0, 0.0, 0.0],
        "reversal_bps": {"point": nan, "lo": nan, "hi": nan},
        "buy": {"point": nan, "lo": nan, "hi": nan, "n": 0},
        "sell": {"point": nan, "lo": nan, "hi": nan, "n": 0},
        "n": int(n),
        "n_months": int(n_months),
        "degraded": True,
    }


def _interval(values, point, lower=None, upper=None):
    """2.5/97.5 百分位区间；端点夹逼 point，空样本回退 point。"""
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0 or not np.isfinite(point):
        return point, point
    lo = float(np.percentile(arr, 2.5))
    hi = float(np.percentile(arr, 97.5))
    if lower is not None:
        lo = max(float(lower), lo)
        hi = max(float(lower), hi)
    if upper is not None:
        lo = min(float(upper), lo)
        hi = min(float(upper), hi)
    return min(lo, point), max(hi, point)


def cross_section_reversal(rt, rt1, side, weight, month,
                           n_bootstrap=1000, seed=20261121):
    """事件加权截面 T+1 反转统计量（纯 numpy，无 IO）。

    x = side·rt、y = side·rt1；share = clip(-Σa·x·y/Σa·x², 0, 1)；
    reversal_bps = -(Σa·y/Σa)×1e4（>0 = 交易后不利回落）。
    月度充分统计量聚合后按形成月聚类重采样，买/卖共用同一组索引。
    """
    from ...effect_size import stationary_bootstrap_indices

    a = _as_1d(rt)
    b = _as_1d(rt1)
    s = np.asarray(side, dtype=float).ravel()
    w = _as_1d(weight)
    m = np.asarray(month, dtype=np.int64).ravel()
    n = a.size
    if not (b.size == s.size == w.size == m.size == n) or n == 0:
        return _degraded_reversal()

    ok = np.isfinite(a) & np.isfinite(b) & np.isfinite(w) & (w > 0.0)
    n_ok = int(ok.sum())
    if n_ok == 0 or int(m[ok].min()) < 0:
        return _degraded_reversal(n=n_ok)
    n_months = int(m[ok].max()) + 1
    x, y = s * a, s * b

    def _agg(mask):
        sel = ok & mask
        mm = m[sel]
        return (
            np.bincount(mm, weights=w[sel], minlength=n_months),
            np.bincount(mm, weights=w[sel] * x[sel] ** 2,
                        minlength=n_months),
            np.bincount(mm, weights=w[sel] * x[sel] * y[sel],
                        minlength=n_months),
            np.bincount(mm, weights=w[sel] * y[sel], minlength=n_months))

    groups = {"all": _agg(np.ones(n, dtype=bool)),
              "buy": _agg(s > 0),
              "sell": _agg(s < 0)}

    def _point(agg):
        sa, sax2, saxy, say = (float(v.sum()) for v in agg)
        share = (0.0 if sax2 <= 0.0
                 else float(np.clip(-saxy / sax2, 0.0, 1.0)))
        bps = np.nan if sa <= 0.0 else float(-(say / sa) * 1e4)
        return share, bps

    if n_months < 3 or float(groups["all"][1].sum()) <= 0.0:
        return _degraded_reversal(n=n_ok, n_months=n_months)

    share_pt, bps_pt = _point(groups["all"])
    idx = stationary_bootstrap_indices(n_months, n_bootstrap=n_bootstrap,
                                       block_size=1, seed=seed)
    reps = {}
    for key, agg in groups.items():
        sa, sax2, saxy, say = (v[idx].sum(axis=1) for v in agg)
        with np.errstate(divide="ignore", invalid="ignore"):
            share = np.where(sax2 > 0.0, np.clip(-saxy / sax2, 0.0, 1.0), 0.0)
            bps = np.where(sa > 0.0, -(say / sa) * 1e4, np.nan)
        reps[key] = (share, bps)

    share_lo, share_hi = _interval(reps["all"][0], share_pt, 0.0, 1.0)
    bps_lo, bps_hi = _interval(reps["all"][1], bps_pt)
    out = {
        "temporary_share": [share_pt, share_lo, share_hi],
        "reversal_bps": {"point": bps_pt, "lo": bps_lo, "hi": bps_hi},
        "n": n_ok,
        "n_months": n_months,
        "degraded": False,
    }
    for key in ("buy", "sell"):
        point = _point(groups[key])[1]
        lo, hi = _interval(reps[key][1], point)
        out[key] = {"point": point, "lo": lo, "hi": hi,
                    "n": int((ok & (s > 0 if key == "buy" else s < 0)).sum())}
    return out
