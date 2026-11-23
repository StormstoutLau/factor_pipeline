# -*- coding: utf-8 -*-
"""P-021：标准数据根 loader → TradabilityInputs（IO 与纯构建器分离）。

依据：spec/p021-tradability-production-enablement/DESIGN.md §4.5
      spec/p021-tradability-production-enablement/IMPLEMENTATION.md §3.3
"""
import logging
import os
from dataclasses import dataclass, field, replace
from typing import Optional

import numpy as np
import pandas as pd

from .tradability import TradabilityPolicy
from .tradability_inputs import (
    build_tradability_inputs,
    _norm_code,
    _suspend_mask,
)

__all__ = ["TradabilitySpec", "load_stk_limit"]

logger = logging.getLogger(__name__)

# (data_root, panel_dir, name) → DataFrame；每进程只读一次
_PANEL_CACHE = {}


def has_pyarrow():
    """本地探测 pyarrow（不产生跨包依赖）。"""
    try:
        import pyarrow  # noqa: F401
        return True
    except ImportError:
        return False


@dataclass(frozen=True)
class TradabilitySpec(object):
    data_root: str = r"E:\Ashare_data"
    panel_dir: str = "market_data"
    policy: TradabilityPolicy = field(default_factory=lambda: TradabilityPolicy(
        execute_at="next_open", unknown_policy="fallback_raw", mode="full"))
    mode: str = "auto"          # auto | full | execution_only_open | off
    auto_degrade: bool = True
    min_coverage: float = 0.99
    stk_limit_path: Optional[str] = None

    def build(self, dates, codes):
        """按给定日期/代码对齐读取面板，返回 (TradabilityInputs | None, meta)。"""
        requested = self.mode
        if requested not in ("auto", "full", "execution_only_open", "off"):
            raise ValueError("TradabilitySpec.mode 非法: %r" % (requested,))

        date_strs = [pd.Timestamp(d).strftime("%Y-%m-%d") for d in dates]
        index = pd.DatetimeIndex(pd.to_datetime(date_strs))
        codes = [str(c) for c in codes]
        if not codes:
            raise ValueError("TradabilitySpec.build 需要非空 codes")

        close_panel = self._read_panel("close")
        if close_panel is None:
            raise ValueError("TradabilitySpec: 缺少面板 close")
        panel_codes = set(map(str, close_panel.columns))
        codes_found = [c for c in codes if c in panel_codes]
        codes_not_found = [c for c in codes if c not in panel_codes][:20]
        if not codes_found:
            raise ValueError("TradabilitySpec: 请求代码均不在 stock_close 面板")

        panels = {}
        for name in ("high", "low", "open", "volume", "adj", "suspend",
                     "name", "list_date"):
            frame = self._read_panel(name)
            if frame is not None:
                panels[name] = frame
        close = self._slice(close_panel, index, codes)

        # ── 覆盖率（eligible = isfinite(close) & ~suspend）──────────────
        suspend = self._slice(panels.get("suspend"), index, codes)
        high = self._slice(panels.get("high"), index, codes)
        low = self._slice(panels.get("low"), index, codes)
        open_ = self._slice(panels.get("open"), index, codes)
        close_a = close.to_numpy(dtype=float)
        susp_a, _ = _suspend_mask(suspend, index, codes)
        eligible = np.isfinite(close_a) & ~susp_a
        denom = int(np.count_nonzero(eligible))
        high_a = self._to_numpy(high, close_a.shape)
        low_a = self._to_numpy(low, close_a.shape)
        open_a = self._to_numpy(open_, close_a.shape)
        high_low_cov = self._coverage(
            np.isfinite(high_a) & np.isfinite(low_a), eligible)
        open_cov = self._coverage(np.isfinite(open_a), eligible)
        if len(index) > 1:
            prev_eligible = eligible.copy()
            prev_eligible[0] = False
            prev = np.full(close_a.shape, np.nan)
            prev[1:] = close_a[:-1]
            prev_cov = self._coverage(np.isfinite(prev), prev_eligible)
        else:
            prev_cov = 0.0
        coverage = {"high_low": high_low_cov, "open": open_cov,
                    "prev": prev_cov, "eligible_cells": denom}

        # ── D6 模式解析 ───────────────────────────────────────────────
        resolved, degrade_reason = self._resolve_mode(
            requested, high_low_cov, open_cov, prev_cov,
            has_adj="adj" in panels)
        if resolved == "off":
            logger.warning(
                "TradabilitySpec 关闭：mode_requested=%s degrade_reason=%s "
                "coverage=%s", requested, degrade_reason, coverage)
            return None, {"mode": "off", "mode_requested": requested,
                          "degrade_reason": degrade_reason,
                          "coverage": coverage}

        policy = replace(self.policy, mode=resolved, execute_at="next_open")

        # ── 限价表（可选）─────────────────────────────────────────────
        limit_up = limit_down = None
        limit_diag = {}
        if self.stk_limit_path:
            limit_up, limit_down, limit_diag = load_stk_limit(
                self.stk_limit_path, index, codes)

        adj = panels.get("adj")
        ref = None
        adj_source_override = None
        if adj is None:
            # 完全缺 adj：ref=prev（D1），price_basis=raw_close
            prev = np.full(close_a.shape, np.nan)
            if len(index) > 1:
                prev[1:] = close_a[:-1]
            ref = prev
            adj_source_override = "none"

        inputs, meta = build_tradability_inputs(
            close=close,
            high=high, low=low, open_=open_,
            volume=self._slice(panels.get("volume"), index, codes),
            suspend=suspend,
            name=self._slice(panels.get("name"), index, codes),
            adj=self._slice(adj, index, codes) if adj is not None else None,
            list_date=self._list_date(panels.get("list_date"), codes),
            policy=policy,
            limit_up=limit_up, limit_down=limit_down, ref=ref)

        diag = inputs.diagnostics or {}
        diag["mode_requested"] = requested
        diag["degrade_reason"] = degrade_reason
        diag["codes_not_found"] = codes_not_found
        diag["coverage"] = coverage
        if adj_source_override is not None:
            diag["adj_source"] = adj_source_override
            diag["data_tier"] = "D1"
            if "adj" not in diag.get("missing_fields", []):
                diag.setdefault("missing_fields", []).append("adj")
        diag.update(limit_diag)
        if limit_up is not None:
            diag["limit_table_source"] = limit_diag.get(
                "limit_table_source", "stk_limit")
            diag["limit_table_missing_cells"] = limit_diag.get(
                "limit_table_missing_cells", 0)
            diag["limit_table_duplicate_rows"] = limit_diag.get(
                "limit_table_duplicate_rows", 0)
        return inputs, meta

    # ── 内部 ─────────────────────────────────────────────────────────
    def _read_panel(self, name):
        key = (self.data_root, self.panel_dir, name)
        if key in _PANEL_CACHE:
            return _PANEL_CACHE[key]
        path = os.path.join(self.data_root, self.panel_dir,
                            "stock_%s.pkl" % name)
        if not os.path.exists(path):
            return None
        frame = pd.read_pickle(path)
        # 真实数据根面板 index 为字符串日期（object）→ 归一化为 DatetimeIndex，
        # 否则 reindex 全 miss → eligible=0 → 恒 off（审计 P1-①）。
        # 非日期索引面板（如 list_date 元数据表）保留原 index。
        if not isinstance(frame.index, pd.DatetimeIndex):
            try:
                frame.index = pd.to_datetime(frame.index)
            except (ValueError, TypeError):
                pass
        _PANEL_CACHE[key] = frame
        return frame

    @staticmethod
    def _slice(frame, index, codes):
        if frame is None:
            return None
        return frame.reindex(index=index, columns=codes)

    @staticmethod
    def _coverage(mask, eligible):
        denom = int(np.count_nonzero(eligible))
        if denom <= 0:
            return 0.0
        return float(np.count_nonzero(mask & eligible) / denom)

    @staticmethod
    def _to_numpy(frame, shape):
        if frame is None:
            return np.full(shape, np.nan)
        return frame.to_numpy(dtype=float)

    def _resolve_mode(self, requested, high_low_cov, open_cov, prev_cov,
                      has_adj):
        if requested == "off":
            return "off", None
        if open_cov < self.min_coverage or prev_cov < self.min_coverage:
            return "off", "open_or_prev_unavailable"
        full_ok = high_low_cov >= self.min_coverage and has_adj
        if requested == "full":
            if full_ok:
                return "full", None
            if self.auto_degrade:
                return "execution_only_open", "high_low_or_adj_insufficient"
            raise ValueError(
                "TradabilitySpec: full 条件不满足且 auto_degrade=False "
                "(high_low_coverage=%.4f, has_adj=%s)"
                % (high_low_cov, has_adj))
        if requested == "execution_only_open":
            return "execution_only_open", None
        # auto
        if full_ok:
            return "full", None
        return "execution_only_open", "high_low_or_adj_insufficient"

    @staticmethod
    def _list_date(frame, codes):
        if frame is None:
            return None
        if isinstance(frame, pd.Series):
            return frame
        if isinstance(frame, pd.DataFrame):
            if frame.shape[0] == 1:
                return frame.iloc[0]
            column = "list_date" if "list_date" in frame.columns else frame.columns[0]
            return frame[column]
        return None


def load_stk_limit(path, dates, codes):
    """Tushare 格式限价表 → ((T,N) up, (T,N) down, diagnostics)。

    CSV 列：ts_code, trade_date, up_limit, down_limit；trade_date 支持
    YYYYMMDD / YYYY-MM-DD（统一归一为 %Y-%m-%d）；重复键 keep=last。
    """
    text = str(path)
    if text.lower().endswith((".parquet", ".pq")):
        if not has_pyarrow():
            raise ValueError("读取 Parquet 限价表需要 pyarrow；请改用 CSV")
        frame = pd.read_parquet(path)
    else:
        frame = pd.read_csv(path)

    required = {"ts_code", "trade_date", "up_limit", "down_limit"}
    missing_cols = required - set(frame.columns)
    if missing_cols:
        raise ValueError("限价表缺列: %r" % (sorted(missing_cols),))

    frame = frame.copy()
    frame["code"] = frame["ts_code"].astype(str).str.split(".").str[0] \
        .str.zfill(6)
    frame["trade_date"] = pd.to_datetime(
        frame["trade_date"].astype(str)).dt.strftime("%Y-%m-%d")
    before = len(frame)
    frame = frame.drop_duplicates(subset=["code", "trade_date"], keep="last")
    duplicate_rows = int(before - len(frame))

    date_strs = [pd.Timestamp(d).strftime("%Y-%m-%d") for d in dates]
    codes_norm = [_norm_code(c) for c in codes]

    def _pivot(value_col):
        return frame.pivot(index="trade_date", columns="code",
                           values=value_col).reindex(
            index=date_strs, columns=codes_norm)

    up = _pivot("up_limit").to_numpy(dtype=float)
    down = _pivot("down_limit").to_numpy(dtype=float)
    finite = np.isfinite(up) & np.isfinite(down)
    if np.any(finite & ((up <= 0.0) | (down <= 0.0))):
        raise ValueError("限价表含非正值")
    if np.any(finite & (up < down)):
        raise ValueError("限价表存在 up_limit < down_limit")
    missing_cells = int(np.count_nonzero(~finite))
    diagnostics = {
        "limit_table_source": ("stk_limit_partial" if missing_cells
                               else "stk_limit"),
        "limit_table_missing_cells": missing_cells,
        "limit_table_duplicate_rows": duplicate_rows,
    }
    return up, down, diagnostics
