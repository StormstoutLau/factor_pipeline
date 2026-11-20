# -*- coding: utf-8 -*-
"""v3.8.1 分钟面板编排（E1 日频层 / E2 分钟层）。

设计依据：DESIGN_V3.8.1 W1-W10；实施依据：EXECUTION_V3.8.1 §2.3。
禁止边：本模块不 import ``scripts``；日频组合面板由脚本注入。
"""
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ..core.decay import estimate_rho
from ..core.impact import (C_R2_MIN, C_RANGE, LinearImpact, LogImpact,
                           PowerImpact, SqrtImpact, cross_val_rmse, fit_r2,
                           select_models)
from ..ports import CalibrationUnavailable
from .loaders import (MAX_STOCK_CODE, MIN_STOCK_CODE, MinuteDayAggregate,
                      MinuteLoader, has_pyarrow)
from .runner import fit_lambda_hac

__all__ = ["DailyRef", "PanelCoverage", "MinutePanelBuilder",
           "build_daily_panels", "assemble_panels", "coverage_gate",
           "force_coverage_warning",
           "PARTIAL_MIN_DAYS", "SAMPLE_CAP", "FEE_BPS", "COST_HORIZONS"]

PARTIAL_MIN_DAYS = 20          # 文件数 < 交易日数但 >= 20 -> partial
SAMPLE_CAP = 200000            # 观测样本上限
FEE_BPS = 10.0                 # 双边费率近似（bps/边）
COST_HORIZONS = (5, 10, 20)    # cost(h) 输出口径（与报告一致）
IMPL_MIN = 0.95                # 覆盖度门禁：月中位
MONTH_MIN = 0.90               # 覆盖度门禁：单月最差
MODELS = (SqrtImpact(), LinearImpact(), LogImpact(), PowerImpact())


@dataclass
class DailyRef(object):
    """日频参考（由脚本注入；panels 不读盘）。"""

    adv: Optional[pd.DataFrame] = None            # 月频 ADV（元）
    universe: Optional[pd.DataFrame] = None       # 月频非空股票
    industry: Optional[pd.DataFrame] = None       # 月频行业
    mv_rank: Optional[pd.DataFrame] = None        # 月频规模五分位 1..5
    days_by_month: Optional[Dict[str, int]] = None


@dataclass
class PanelCoverage(object):
    """覆盖度门禁工件（W6）。"""

    window: tuple
    months: list
    partial_months: list
    missing_months: list
    stock_median: float
    universe_ratio: dict
    limit_lock_ratio: float
    board_counts: dict
    ratio_raw: dict = field(default_factory=dict)   # v3.9.4：原式披露（可 >1）

    def as_dict(self):
        return {"window": list(self.window),
                "months": list(self.months),
                "partial_months": list(self.partial_months),
                "missing_months": list(self.missing_months),
                "stock_median": float(self.stock_median),
                "universe_ratio": dict(self.universe_ratio),
                "ratio_raw": dict(self.ratio_raw),
                "limit_lock_ratio": float(self.limit_lock_ratio),
                "board_counts": dict(self.board_counts)}


def _month_range(lo, hi):
    y, m = int(lo[:4]), int(lo[5:7])
    ey, em = int(hi[:4]), int(hi[5:7])
    out = []
    while (y, m) <= (ey, em):
        out.append("%04d-%02d" % (y, m))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def _board(code6):
    if code6.startswith(("600", "601", "603", "605")):
        return "沪主板"
    if code6.startswith(("000", "001", "002", "003")):
        return "深主板"
    if code6.startswith(("300", "301")):
        return "创业板"
    if code6.startswith("688"):
        return "科创板"
    return "其他"


def _cell(row, key):
    if row is None:
        return None
    try:
        value = row.get(key)
    except AttributeError:
        return None
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _sample_indices(p, sigma, cap):
    if p.size <= cap:
        return np.arange(p.size)
    order = np.lexsort((sigma, p))
    take = np.linspace(0, order.size - 1, int(cap)).astype(np.int64)
    return order[np.unique(take)]


def _stratified_sample(p, impact, sigma, cap, seed=None):
    idx = _sample_indices(p, sigma, cap)
    return p[idx], impact[idx], sigma[idx]


def _fit_impact(p, impact, sigma):
    """与 runner 同一观测样本、同一 ``fit`` 实现（S1）。"""
    cv = cross_val_rmse(list(MODELS), p, impact, sigma)
    primary, tied = select_models(cv)
    fitted = {}
    for model in MODELS:
        try:
            fitted[model.name] = model.fit(p, impact, sigma)
        except ValueError:
            fitted[model.name] = None
    model = dict((m.name, m) for m in MODELS).get(primary)
    params = fitted.get(primary)
    r2 = None
    ident = True
    if primary == "sqrt" and params and model is not None:
        try:
            pred = model.predict(p, sigma, params)
            r2 = float(fit_r2(pred, impact))
            c_val = float(params["c"])
            ident = bool(r2 >= C_R2_MIN
                         and C_RANGE[0] <= c_val <= C_RANGE[1])
        except (ValueError, TypeError, KeyError):
            r2, ident = None, False
    return {"primary": primary,
            "params": params,
            "r2": r2,
            "identifiable": ident,
            "sigma_median": float(np.median(sigma)),
            "cv_rmse": {k: (None if not np.isfinite(v) else float(v))
                        for k, v in cv.items()},
            "tied": list(tied)}


class MinutePanelBuilder(object):
    """分钟层面板构建（λ 回归 / 填充 / 观测样本 / 覆盖度 / panel_hash）。"""

    def __init__(self, cfg, loader=None, daily=None, cache_dir=None):
        self.cfg = cfg
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if loader is None:
            if not getattr(cfg, "minute_root", None):
                raise CalibrationUnavailable("minute_root 未配置")
            loader = MinuteLoader(cfg.minute_root,
                                  sigma_bars=cfg.bvc_sigma_bars)
        self.loader = loader
        self.daily = daily
        self._samples = []  # type: List[tuple]

    # ------------------------------------------------------------ 窗口
    def months(self):
        lo, hi = self.cfg.minute_start[:7], self.cfg.minute_end[:7]
        return [m for m in self.loader.available_months() if lo <= m <= hi]

    def _expected_months(self):
        lo, hi = self.cfg.minute_start[:7], self.cfg.minute_end[:7]
        days = self.daily.days_by_month if self.daily is not None else None
        if days:
            return sorted(m for m in days if lo <= m <= hi)
        return _month_range(lo, hi)

    def _file_count(self, ym):
        root = getattr(self.loader, "root", None)
        if root is None:
            want = None
            if self.daily is not None:
                want = (self.daily.days_by_month or {}).get(ym)
            return int(want) if want else PARTIAL_MIN_DAYS
        return len(list(Path(root).glob("%s-*.feather" % ym)))

    @staticmethod
    def _month_row(frame, ym):
        if frame is None or frame.empty:
            return None
        labels = [str(i)[:7] for i in frame.index]
        selected = None
        for i, label in enumerate(labels):
            if label <= ym:
                selected = i
            else:
                break
        if selected is None:
            return None
        return frame.iloc[selected]

    def _adv_lookup(self, ym):
        if self.daily is None or self.daily.adv is None:
            return {}
        row = self._month_row(self.daily.adv, ym)
        if row is None:
            return {}
        out = {}
        for key, value in row.items():
            try:
                code = int(str(key))
            except (TypeError, ValueError):
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if np.isfinite(number):
                out[code] = number
        return out

    def _universe_codes(self, ym):
        """日频可投资域码集（int 归一，与 _adv_lookup 同款）。"""
        if self.daily is None or self.daily.universe is None:
            return set()
        row = self._month_row(self.daily.universe, ym)
        if row is None:
            return set()
        keep = np.asarray(row.fillna(False).to_numpy(), dtype=bool)
        codes = set()
        for key in row.index[keep]:
            try:
                codes.add(int(str(key)))
            except (TypeError, ValueError):
                continue
        return codes

    def _universe_count(self, ym):
        return len(self._universe_codes(ym))

    # ------------------------------------------------------------ 缓存
    def _read_cache(self, ym):
        if self.cache_dir is None:
            return None
        npz = self.cache_dir / ("%s.npz" % ym)
        meta = self.cache_dir / ("%s.meta.json" % ym)
        if not (npz.exists() and meta.exists()):
            return None
        try:
            info = json.loads(meta.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None
        if info.get("config_hash") != self.cfg.config_hash():
            return None
        try:
            with np.load(str(npz), allow_pickle=True) as data:
                return MinuteDayAggregate(
                    date=data["date"].astype(object),
                    stock_code=data["stock_code"].astype(np.int64),
                    signed_day=data["signed_day"].astype(float),
                    amount_day=data["amount_day"].astype(float),
                    ret_day=data["ret_day"].astype(float),
                    sigma=data["sigma"].astype(float),
                    n_bars=data["n_bars"].astype(np.int64),
                    limit_lock=data["limit_lock"].astype(bool))
        except (OSError, KeyError, ValueError):
            return None

    def _write_cache(self, ym, agg):
        if self.cache_dir is None:
            return
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            npz = self.cache_dir / ("%s.npz" % ym)
            tmp = self.cache_dir / ("%s.tmp.npz" % ym)
            np.savez(str(tmp), date=agg.date, stock_code=agg.stock_code,
                     signed_day=agg.signed_day, amount_day=agg.amount_day,
                     ret_day=agg.ret_day, sigma=agg.sigma,
                     n_bars=agg.n_bars, limit_lock=agg.limit_lock)
            os.replace(str(tmp), str(npz))
            meta = self.cache_dir / ("%s.meta.json" % ym)
            tmp_meta = self.cache_dir / ("%s.tmp.meta.json" % ym)
            tmp_meta.write_text(json.dumps(
                {"config_hash": self.cfg.config_hash(),
                 "panel_version": "v381"}, sort_keys=True), encoding="utf-8")
            os.replace(str(tmp_meta), str(meta))
        except OSError:
            return

    def _load_month(self, ym):
        cached = self._read_cache(ym)
        if cached is not None:
            return cached, True
        agg = self.loader.load_month_regression(ym)
        self._write_cache(ym, agg)
        return agg, False

    # ------------------------------------------------------------ λ
    def _month_lambda(self, ym, agg):
        adv = self._adv_lookup(ym)
        lo, hi = float(self.cfg.sigma_clip[0]), float(self.cfg.sigma_clip[1])
        ind_row = (self._month_row(self.daily.industry, ym)
                   if self.daily is not None else None)
        mv_row = (self._month_row(self.daily.mv_rank, ym)
                  if self.daily is not None else None)
        pvalues = []
        rows = []
        signed = np.asarray(agg.signed_day, dtype=float)
        ret_day = np.asarray(agg.ret_day, dtype=float)
        grouped = pd.Series(np.arange(agg.stock_code.size)).groupby(
            agg.stock_code).indices
        for code, pos in grouped.items():
            pos = np.asarray(pos, dtype=np.int64)
            amount = adv.get(int(code))
            if amount is None or not np.isfinite(amount):
                continue
            if pos.size < int(self.cfg.lambda_min_days):
                continue
            x = signed[pos] / amount
            r = ret_day[pos]
            ok = np.isfinite(x) & np.isfinite(r)
            if int(ok.sum()) < int(self.cfg.lambda_min_days):
                continue
            try:
                fit = fit_lambda_hac(x[ok], r[ok])
            except ValueError:
                continue
            pvalues.append(float(fit["p"]))
            key6 = str(int(code)).zfill(6)
            rows.append({"code": int(code), "month": ym,
                         "lambda": float(fit["lambda"]),
                         "p": float(fit["p"]), "n_days": int(ok.sum()),
                         "industry": _cell(ind_row, key6),
                         "mv_bucket": _cell(mv_row, key6)})
            sd = float(np.std(r[ok], ddof=1)) if int(ok.sum()) >= 2 else 0.0
            if not np.isfinite(sd) or sd <= 0.0:
                sd = lo
            sigma_d = float(np.clip(sd, lo, hi))
            for xi, ri in zip(x[ok], r[ok]):
                self._samples.append((float(np.clip(abs(xi), 1e-6, 1.0)),
                                      float(abs(ri)), sigma_d,
                                      int(code), ym))
        return pvalues, rows

    def _fill_lambda(self, rows):
        sig = [r for r in rows
               if r["p"] < self.cfg.lambda_p_threshold and r["lambda"] > 0.0]
        n_total = len(rows)
        n_sig = len(sig)
        n_neg = sum(1 for r in rows if r["lambda"] <= 0.0)
        groups = {}  # type: Dict[tuple, list]
        for r in sig:
            key = (r["month"], r["industry"], r["mv_bucket"])
            groups.setdefault(key, []).append(r)
        by_group = {}
        for key, items in groups.items():
            vals = np.asarray([it["lambda"] for it in items], dtype=float)
            if vals.size > 1:
                low, high = np.percentile(vals, 1.0), np.percentile(vals, 99.0)
                vals = np.clip(vals, low, high)
            median = float(np.median(vals))
            by_group["%s|%s|%s" % (key[0], key[1], key[2])] = median
            for item in items:
                item["lambda_filled"] = median
        fill_ratio = 1.0 - (n_sig / float(n_total)) if n_total else 1.0
        warnings = []
        c_interval_only = bool(fill_ratio > 0.30)
        if c_interval_only:
            warnings.append("lambda_fill_ratio=%.3f > 0.30，c 仅报区间（[区间]）"
                            % fill_ratio)
        stats = {"n_total": n_total, "n_sig": n_sig, "n_neg": n_neg,
                 "fill_ratio": float(fill_ratio),
                 "median_lambda": (float(np.median(
                     [r["lambda"] for r in sig])) if sig else None),
                 "c_interval_only": c_interval_only,
                 "by_group": by_group}
        panel = dict((int(r["code"]), float(r["lambda"])) for r in sig)
        return {"lambda_stats": stats, "panel": panel,
                "evidence_warnings": warnings}

    # ------------------------------------------------------------ 组装
    def _coverage(self, usable, partial, missing, counts, locks):
        ratio, raw = {}, {}
        for ym in usable:
            universe = self._universe_codes(ym)
            denom = len(universe)
            if denom <= 0:
                ratio[ym] = None
                raw[ym] = None
                continue
            codes = set(int(c) for c in self._month_codes.get(ym, ()))
            ratio[ym] = float(len(codes & universe)) / float(denom)
            raw[ym] = float(counts[ym]) / float(denom)
        boards = {"沪主板": 0, "深主板": 0, "创业板": 0, "科创板": 0, "其他": 0}
        for ym in usable:
            for code in self._month_codes.get(ym, []):
                boards[_board(str(int(code)).zfill(6))] += 1
        values = [float(v) for v in counts.values() if v]
        lock_values = [locks[m] for m in usable if m in locks]
        return PanelCoverage(
            window=(self.cfg.minute_start[:7], self.cfg.minute_end[:7]),
            months=list(usable), partial_months=list(partial),
            missing_months=list(missing),
            stock_median=float(np.median(values)) if values else 0.0,
            universe_ratio=ratio,
            ratio_raw=raw,
            limit_lock_ratio=(float(np.mean(lock_values))
                              if lock_values else 0.0),
            board_counts=boards)

    def _panel_hash(self, usable, n_lambda, n_samples):
        payload = {
            "adv_window_days": int(self.cfg.adv_window_days),
            "code_range": [MIN_STOCK_CODE, MAX_STOCK_CODE],
            "granularity": "daily",
            "lambda_min_days": int(self.cfg.lambda_min_days),
            "minute_window": [self.cfg.minute_start[:7],
                              self.cfg.minute_end[:7]],
            "months": list(usable),
            "n_lambda": int(n_lambda),
            "n_samples": int(n_samples),
            "sigma_clip": [float(self.cfg.sigma_clip[0]),
                           float(self.cfg.sigma_clip[1])],
            "windows": [int(w) for w in self.cfg.windows],
        }
        text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def build(self, months=None):
        """构建分钟层；窗口内无可用月份抛 ``CalibrationUnavailable``。"""
        if self.daily is None:
            raise CalibrationUnavailable("缺少日频参考面板（ADV/行业/规模）")
        if not has_pyarrow():
            raise CalibrationUnavailable("pyarrow 未安装（pip install .[calib]）")
        warnings = []  # type: List[str]
        avail = set(self.loader.available_months())
        if months is None:
            expected = self._expected_months()
            target = [m for m in expected if m in avail]
            missing = [m for m in expected if m not in avail]
        else:
            target = [m for m in months if m in avail]
            missing = [m for m in months if m not in avail]

        usable, partial = [], []
        for ym in target:
            n_files = self._file_count(ym)
            want = None
            if self.daily is not None:
                want = (self.daily.days_by_month or {}).get(ym)
            if want and n_files < int(want):
                if n_files >= PARTIAL_MIN_DAYS:
                    partial.append(ym)
                else:
                    warnings.append(
                        "月份 %s 仅 %d 个文件（< %d），整月剔除"
                        % (ym, n_files, PARTIAL_MIN_DAYS))
                    continue
            usable.append(ym)
        if not usable:
            raise CalibrationUnavailable("分钟窗口内无可用月份")

        self._samples = []
        self._month_codes = {}
        pvalues, rows = [], []
        counts, locks = {}, {}
        hits = misses = 0
        cap_month = int(np.ceil(SAMPLE_CAP / float(max(len(usable), 1))))
        for ym in usable:
            agg, cached = self._load_month(ym)
            if cached:
                hits += 1
            else:
                misses += 1
            codes = np.unique(agg.stock_code)
            self._month_codes[ym] = codes
            counts[ym] = int(codes.size)
            locks[ym] = (float(np.mean(agg.limit_lock))
                         if agg.limit_lock.size else 0.0)
            start = len(self._samples)
            pv, mr = self._month_lambda(ym, agg)
            pvalues.extend(pv)
            rows.extend(mr)
            chunk = self._samples[start:]
            if len(chunk) > cap_month:
                idx = _sample_indices(
                    np.asarray([c[0] for c in chunk], dtype=float),
                    np.asarray([c[2] for c in chunk], dtype=float), cap_month)
                self._samples[start:] = [chunk[int(i)] for i in idx]

        p = np.asarray([s[0] for s in self._samples], dtype=float)
        impact = np.asarray([s[1] for s in self._samples], dtype=float)
        sigma = np.asarray([s[2] for s in self._samples], dtype=float)
        if p.size > SAMPLE_CAP:
            p, impact, sigma = _stratified_sample(
                p, impact, sigma, SAMPLE_CAP, self.cfg.seed)
        if p.size < 3 or float(np.ptp(impact)) == 0.0:
            warnings.append("impact_samples 不足（n=%d），c 沿用默认" % p.size)

        filled = self._fill_lambda(rows)
        warnings.extend(filled["evidence_warnings"])

        impact_fit = None
        if p.size >= 3 and float(np.ptp(impact)) > 0.0:
            try:
                impact_fit = _fit_impact(p, impact, sigma)
            except ValueError as exc:
                warnings.append("impact_fit 不可用: %s" % exc)

        coverage = self._coverage(usable, partial, missing, counts, locks)
        panel_hash = self._panel_hash(usable, len(rows), p.size)
        return {
            "lambda_pvalues": pvalues,
            "lambda_stats": filled["lambda_stats"],
            "panel": filled["panel"],
            "impact_samples": {"p": p, "impact": impact, "sigma": sigma},
            "impact_samples_meta": {"n": int(p.size), "cap": int(SAMPLE_CAP),
                                    "granularity": "daily",
                                    "sampling": "equal_distance"},
            "impact_fit": impact_fit,
            "sigma_median": (float(np.median(sigma)) if sigma.size else None),
            "coverage": coverage,
            "panel_hash": panel_hash,
            "evidence_level": "minutes",
            "evidence_warnings": warnings,
            "cache": {"hits": hits, "misses": misses},
        }


def build_daily_panels(cfg, daily, portfolio, impact_fit=None):
    """日频层统计映射（E1）：temporary / rho / alpha0 / cost(h) / plateau_sd。"""
    out = {"evidence_warnings": []}
    aum_ref = float(portfolio.get("aum_ref", 1e10))
    ex_m = pd.Series(portfolio.get("excess_m", []), dtype=float).dropna()
    ex_d = pd.Series(portfolio.get("excess_d", []), dtype=float).dropna()

    r1 = ex_d.to_numpy()[:-1]
    rev1 = ex_d.to_numpy()[1:]
    out["temporary"] = ({"r1": [float(v) for v in r1],
                         "rev1": [float(v) for v in rev1]}
                        if r1.size else {})
    out["temporary_basis"] = "portfolio_ar1_proxy"
    if r1.size:
        out["evidence_warnings"].append(
            "temporary_share 为组合日超额 AR(1) 代理，非 T+1 反转，不进入容量")

    rho, lo, hi = 1.0, 1.0, 1.0
    if ex_d.size >= 3:
        try:
            rho, lo, hi = estimate_rho(ex_d.to_numpy())
        except ValueError as exc:
            out["evidence_warnings"].append("rho 不可估（%s），按 1.0" % exc)
    if float(rho) <= 0.0:
        rho, lo, hi = 1.0, 1.0, 1.0
        out["evidence_warnings"].append("rho<=0（无正持续性），按无衰减处理")
    out["rho"] = float(rho)
    out["rho_series"] = [float(v) for v in ex_d.to_numpy()]
    out["rho_freq"] = "daily"
    out["rho_n"] = int(ex_d.size)
    out["alpha0"] = float(ex_m.mean()) if ex_m.size else None

    # v3.9.3 衰减曲线（FO-1）：仅校准分支由 build_portfolio_panels 提供 A 矩阵
    rows = portfolio.get('a_by_period')
    if rows:
        mat = np.asarray(rows, dtype=float)
        if mat.ndim == 2 and mat.shape[0] and mat.shape[1]:
            out["decay_a_by_period"] = [
                [None if not np.isfinite(v) else float(v) for v in row]
                for row in mat]
            out["decay_h_max"] = int(mat.shape[1])
            if mat.shape[1] >= 20:
                col = mat[:, 19]
                ok = np.isfinite(col)
                out["alpha0_anchored"] = (float(col[ok].mean())
                                          if ok.any() else None)
            else:
                out["alpha0_anchored"] = None

    turnover = pd.Series(portfolio.get("turnover_m", []), dtype=float).dropna()
    turnover_m = float(turnover.mean()) if turnover.size else 0.0
    if not np.isfinite(turnover_m):
        turnover_m = 0.0
        out["evidence_warnings"].append("月换手缺失，cost(h) 按 0 处理")
    out["turnover_m"] = turnover_m
    out["regime_p95"] = dict(portfolio.get("regime_p95") or {})
    out["window_capacity"] = dict(portfolio.get("window_capacity") or {})
    out["aum_ref"] = aum_ref
    if portfolio.get("notional") is not None:
        out["notional"] = np.asarray(portfolio["notional"], dtype=float)
    if portfolio.get("adv") is not None:
        out["adv"] = np.asarray(portfolio["adv"], dtype=float)

    sigma_port = portfolio.get("sigma_port")
    try:
        sigma_port = float(sigma_port)
    except (TypeError, ValueError):
        sigma_port = None
    if sigma_port is None or not np.isfinite(sigma_port) or sigma_port <= 0:
        sigma_port = 0.02
    p_cost = portfolio.get("p_cost")
    try:
        p_cost = float(p_cost)
    except (TypeError, ValueError):
        p_cost = None
    if p_cost is None or not np.isfinite(p_cost) or p_cost <= 0:
        p_cost = 0.01

    impact_bps = 0.0
    out["impact_bps_source"] = "calibrated"
    params = impact_fit.get("params") if impact_fit else None
    primary = impact_fit.get("primary") if impact_fit else None
    if params and primary == "sqrt" and not impact_fit.get("identifiable",
                                                           True):
        out["impact_bps_source"] = "default_fallback"
        out["evidence_warnings"].append(
            "c 不可识别（r2<%.2f 或超出 %s），成本回退 c=0.5"
            % (C_R2_MIN, C_RANGE))
        params = {"c": 0.5}
    if params:
        model = dict((m.name, m) for m in MODELS).get(primary)
        if model is not None:
            try:
                prediction = model.predict(np.array([p_cost]), sigma_port,
                                           params)
                value = float(np.asarray(prediction, dtype=float).ravel()[0])
                if np.isfinite(value):
                    impact_bps = abs(value) * 1e4
            except (ValueError, TypeError, IndexError):
                impact_bps = 0.0
    else:
        out["impact_bps_source"] = "unavailable"
        out["evidence_warnings"].append("cost_impact_unavailable")

    cost_by_h = {}
    for h in COST_HORIZONS:
        cost_by_h[int(h)] = float(
            (20.0 / float(h)) * aum_ref * turnover_m * 2.0
            * (FEE_BPS + impact_bps) / 1e4)
    out["cost_by_h"] = cost_by_h
    out["plateau_sd"] = (float(aum_ref * float(ex_m.std(ddof=1)))
                         if ex_m.size > 1 else 0.0)
    return out


def assemble_panels(minute, daily_panels, evidence_level):
    """合并分钟层 + 日频层为 runner 消费的面板（S3）。"""
    merged = dict(daily_panels or {})
    for key, value in (minute or {}).items():
        if key == "evidence_warnings":
            merged.setdefault("evidence_warnings", []).extend(value or [])
        else:
            merged[key] = value
    merged["evidence_level"] = evidence_level
    return merged


def force_coverage_warning(messages):
    """--force-coverage 放行留痕文案（token 化，便于 grep 与断言）。"""
    return "coverage_gate_forced: " + "; ".join(str(m) for m in messages)


def coverage_gate(cov):
    """覆盖度门禁（W6）：月中位 >= 0.95、最差 >= 0.90、深主板 > 0。"""
    if hasattr(cov, "as_dict"):
        cov = cov.as_dict()
    cov = dict(cov or {})
    if not cov:
        return False, ["覆盖度工件缺失"]
    ratio = cov.get("universe_ratio") or {}
    values = [float(v) for v in ratio.values() if v is not None]
    messages = []
    if values:
        median = float(np.median(values))
        worst = float(min(values))
        if median < IMPL_MIN:
            messages.append("覆盖度中位 %.3f < %.2f" % (median, IMPL_MIN))
        if worst < MONTH_MIN:
            messages.append("覆盖度最差 %.3f < %.2f" % (worst, MONTH_MIN))
    else:
        messages.append("覆盖度未产出（universe_ratio 为空）")
    boards = cov.get("board_counts") or {}
    if int(boards.get("深主板", 0)) <= 0:
        messages.append("深市主板股票数为 0")
    return (len(messages) == 0), messages
