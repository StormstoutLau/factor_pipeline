# -*- coding: utf-8 -*-
"""P-021：标准数据根 loader → TradabilityInputs（IO 与纯构建器分离）。

依据：spec/p021-tradability-production-enablement/DESIGN.md §4.5
      spec/p021-tradability-production-enablement/IMPLEMENTATION.md §3.3
"""
import gc
import logging
import os
from collections import Counter
from dataclasses import dataclass, field, replace
from typing import Optional

import numpy as np
import pandas as pd

from .tradability import TradabilityPolicy, board_of
from .tradability_inputs import (
    build_tradability_inputs,
    _norm_code,
    _suspend_mask,
)

__all__ = ["TradabilitySpec", "TradabilityPlan", "TradabilityChunk",
           "ChunkResult", "build_name_compact_payload",
           "load_name_compact", "write_name_compact", "load_stk_limit"]

logger = logging.getLogger(__name__)

# (data_root, panel_dir, name) → _PanelRecord；每进程只读一次
_PANEL_CACHE = {}


class _PanelRecord(object):
    """面板缓存记录：float/raw 存 DataFrame；name 存 float32 码；suspend 存 bool。"""

    __slots__ = ("kind", "index", "columns", "data", "aux")

    def __init__(self, kind, index, columns, data, aux=None):
        if kind not in ("float", "name", "suspend", "raw"):
            raise ValueError("未知 _PanelRecord.kind: %r" % (kind,))
        self.kind = kind
        self.index = index
        self.columns = columns
        self.data = data
        self.aux = aux


def _has_bool_columns(frame):
    return any(pd.api.types.is_bool_dtype(dt) for dt in frame.dtypes)


def _normalize_index(frame):
    """真实数据根面板 index 为字符串日期（object）→ DatetimeIndex。"""
    if not isinstance(frame.index, pd.DatetimeIndex):
        try:
            frame.index = pd.to_datetime(frame.index)
        except (ValueError, TypeError):
            pass
    return frame


def _take_codes(arr, src_index, src_cols, index, columns):
    """按行列标签取 float32 码；缺失行列填 NaN。"""
    ri = src_index.get_indexer(index)
    ci = src_cols.get_indexer(columns)
    out = np.full((len(index), len(columns)), np.nan, dtype=np.float32)
    r_pos = np.flatnonzero(ri >= 0)
    c_pos = np.flatnonzero(ci >= 0)
    if r_pos.size and c_pos.size:
        out[np.ix_(r_pos, c_pos)] = arr[np.ix_(ri[r_pos], ci[c_pos])]
    return out


def _take_bool(arr, src_index, src_cols, index, columns, fill):
    ri = src_index.get_indexer(index)
    ci = src_cols.get_indexer(columns)
    out = np.full((len(index), len(columns)), bool(fill), dtype=bool)
    r_pos = np.flatnonzero(ri >= 0)
    c_pos = np.flatnonzero(ci >= 0)
    if r_pos.size and c_pos.size:
        out[np.ix_(r_pos, c_pos)] = arr[np.ix_(ri[r_pos], ci[c_pos])]
    return out


def has_pyarrow():
    """本地探测 pyarrow（不产生跨包依赖）。"""
    try:
        import pyarrow  # noqa: F401
        return True
    except ImportError:
        return False


# ── P-023：离线 name 紧凑缓存（npz，无 pickle）──────────────────────
NAME_COMPACT_FORMAT_VERSION = 1
NAME_COMPACT_NAME = "stock_name_compact.npz"
NAME_COMPACT_KEYS = ("format_version", "codes", "index", "columns",
                     "uniques", "st_lut", "del_lut",
                     "source_mtime", "source_size")


def build_name_compact_payload(frame):
    """object name DataFrame → npz payload（codes/index/columns/uniques/LUT）。"""
    index, columns = frame.index, frame.columns
    arr = frame.to_numpy(dtype=object)
    codes, uniques = pd.factorize(arr.ravel(), sort=False)
    if len(uniques) > 2 ** 24:
        raise ValueError("name 唯一值 %d 超过 float32 精确上限"
                         % len(uniques))
    st_lut = np.array(["ST" in str(u) for u in uniques], dtype=bool)
    del_lut = np.array(["退" in str(u) for u in uniques], dtype=bool)
    codes_f = codes.astype(np.float32)
    codes_f[codes < 0] = np.nan
    codes_f = codes_f.reshape(frame.shape)
    del arr, codes
    return {
        "format_version": np.asarray(NAME_COMPACT_FORMAT_VERSION,
                                     dtype=np.int32),
        "codes": codes_f,
        "index": np.asarray([str(x) for x in index], dtype=str),
        "columns": np.asarray([str(x) for x in columns], dtype=str),
        "uniques": np.asarray([str(x) for x in uniques], dtype=str),
        "st_lut": st_lut,
        "del_lut": del_lut,
    }


def write_name_compact(path, frame, source_path):
    """原子写：同目录临时文件 → round-trip 校验 → os.replace。

    失败时删除临时文件并抛出；从不修改源 pkl。
    """
    st = os.stat(source_path)
    payload = build_name_compact_payload(frame)
    payload["source_mtime"] = np.asarray(st.st_mtime, dtype=np.float64)
    payload["source_size"] = np.asarray(st.st_size, dtype=np.int64)
    tmp = "%s.tmp-%d" % (path, os.getpid())
    try:
        with open(tmp, "wb") as fh:
            np.savez(fh, **payload)
        with np.load(tmp, allow_pickle=False) as z:
            missing = [k for k in NAME_COMPACT_KEYS if k not in z.files]
            if missing:
                raise ValueError("round-trip 缺键: %r" % (missing,))
            version = int(np.asarray(z["format_version"]).reshape(-1)[0])
            if version != NAME_COMPACT_FORMAT_VERSION:
                raise ValueError("round-trip 版本不符: %r" % (version,))
            if np.asarray(z["codes"]).shape != frame.shape:
                raise ValueError("round-trip codes 形状不符")
            if not np.array_equal(np.asarray(z["codes"]), payload["codes"],
                                  equal_nan=True):
                raise ValueError("round-trip codes 不一致")
            for key in ("index", "columns", "uniques"):
                if [str(x) for x in z[key]] != [str(x) for x in payload[key]]:
                    raise ValueError("round-trip %s 不一致" % key)
            for key in ("st_lut", "del_lut"):
                if not np.array_equal(np.asarray(z[key]), payload[key]):
                    raise ValueError("round-trip %s 不一致" % key)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return {
        "path": path,
        "bytes": int(os.path.getsize(path)),
        "shape": [int(x) for x in frame.shape],
        "uniques": int(len(payload["uniques"])),
        "source_size": int(st.st_size),
        "source_mtime": float(st.st_mtime),
    }


def load_name_compact(path, pkl_path=None):
    """读取并校验 npz；失败返回 None（调用方回退 pkl）。"""
    if not path or not os.path.exists(path):
        return None
    try:
        with np.load(path, allow_pickle=False) as z:
            missing = [k for k in NAME_COMPACT_KEYS if k not in z.files]
            if missing:
                raise ValueError("缺键: %r" % (missing,))
            version = int(np.asarray(z["format_version"]).reshape(-1)[0])
            if version != NAME_COMPACT_FORMAT_VERSION:
                raise ValueError("format_version=%r" % (version,))
            codes = np.asarray(z["codes"]).copy()
            if codes.dtype != np.float32 or codes.ndim != 2:
                raise ValueError("codes 必须为二维 float32")
            index = pd.DatetimeIndex(
                pd.to_datetime([str(x) for x in z["index"]]))
            columns = pd.Index([str(x) for x in z["columns"]])
            uniques = tuple(str(x) for x in z["uniques"])
            st_lut = np.asarray(z["st_lut"]).copy()
            del_lut = np.asarray(z["del_lut"]).copy()
            source_mtime = float(np.asarray(z["source_mtime"]).reshape(-1)[0])
            source_size = int(np.asarray(z["source_size"]).reshape(-1)[0])
        if codes.shape != (len(index), len(columns)):
            raise ValueError("codes 与 index/columns 长度不符")
        if st_lut.dtype != bool or del_lut.dtype != bool:
            raise ValueError("st_lut/del_lut 必须为 bool")
        if (st_lut.ndim != 1 or del_lut.ndim != 1
                or len(st_lut) != len(uniques)
                or len(del_lut) != len(uniques)):
            raise ValueError("LUT 长度与 uniques 不符")
        finite = np.isfinite(codes)
        if finite.any():
            lo = float(codes[finite].min())
            hi = float(codes[finite].max())
            if lo < 0.0 or hi >= len(uniques):
                raise ValueError("codes 越界 [%r, %r]" % (lo, hi))
        if pkl_path and os.path.exists(pkl_path):
            st = os.stat(pkl_path)
            if (int(st.st_size) != source_size
                    or abs(st.st_mtime - source_mtime) > 1e-3):
                raise ValueError("源 pkl 已变化（mtime/size）")
        return _PanelRecord("name", index, columns, codes,
                            (uniques, st_lut, del_lut))
    except Exception as exc:      # 含 OSError / zipfile 损坏
        logger.warning("name_compact_fallback: %s (%s)", path, exc)
        return None


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
    name_compact_path: Optional[str] = None
    max_dates_per_chunk: Optional[int] = 60

    def _name_pkl_path(self):
        return os.path.join(self.data_root, self.panel_dir, "stock_name.pkl")

    def _name_compact_path(self):
        if self.name_compact_path:
            return self.name_compact_path
        return os.path.join(self.data_root, self.panel_dir, NAME_COMPACT_NAME)

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

        # 首次加载顺序：name/suspend 先紧凑化，避免 object 面板与 float 面板叠加
        name_rec = self._read_panel("name")
        suspend_rec = self._read_panel("suspend")
        close_rec = self._read_panel("close")
        if close_rec is None:
            raise ValueError("TradabilitySpec: 缺少面板 close")
        close_panel = self._panel_df(close_rec)
        panel_codes = set(map(str, close_panel.columns))
        codes_found = [c for c in codes if c in panel_codes]
        codes_not_found = [c for c in codes if c not in panel_codes][:20]
        if not codes_found:
            raise ValueError("TradabilitySpec: 请求代码均不在 stock_close 面板")

        panels = {}
        for name in ("high", "low", "open", "volume", "adj", "list_date"):
            rec = self._read_panel(name)
            if rec is not None:
                panels[name] = rec
        close, _ = self._slice(close_rec, index, codes)

        # ── name / suspend 切片（紧凑或 raw 回退）─────────────────────
        name = None
        name_codes = name_st_lut = name_del_lut = None
        if name_rec is not None:
            name_data, name_aux = self._slice(name_rec, index, codes)
            if name_rec.kind == "name":
                name_codes = name_data
                name_st_lut, name_del_lut = name_aux[1], name_aux[2]
            else:
                name = name_data

        suspend = None
        suspend_mask = suspend_missing = None
        susp_a = None
        if suspend_rec is not None:
            suspend_data, _ = self._slice(suspend_rec, index, codes)
            if suspend_rec.kind == "suspend":
                suspend_mask, suspend_missing = suspend_data
                susp_a = suspend_mask
            else:
                suspend = suspend_data
                susp_a, _ = _suspend_mask(suspend, index, codes)

        # ── 覆盖率（eligible = isfinite(close) & ~suspend）──────────────
        high, _ = self._slice(panels.get("high"), index, codes)
        low, _ = self._slice(panels.get("low"), index, codes)
        open_, _ = self._slice(panels.get("open"), index, codes)
        close_a = close.to_numpy(dtype=float)
        if susp_a is None:
            susp_a = np.zeros(close_a.shape, dtype=bool)
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

        adj_df = None
        if "adj" in panels:
            adj_df, _ = self._slice(panels["adj"], index, codes)
        ref = None
        adj_source_override = None
        if adj_df is None:
            # 完全缺 adj：ref=prev（D1），price_basis=raw_close
            prev = np.full(close_a.shape, np.nan)
            if len(index) > 1:
                prev[1:] = close_a[:-1]
            ref = prev
            adj_source_override = "none"

        volume, _ = self._slice(panels.get("volume"), index, codes)
        ld_frame = self._panel_df(panels.get("list_date"))
        kwargs = dict(
            close=close, high=high, low=low, open_=open_, volume=volume,
            suspend=suspend, name=name, adj=adj_df,
            list_date=self._list_date(ld_frame, codes), policy=policy,
            limit_up=limit_up, limit_down=limit_down, ref=ref)
        if name_codes is not None:
            kwargs.update(name=None, name_codes=name_codes,
                          name_st_lut=name_st_lut, name_del_lut=name_del_lut)
        if suspend_mask is not None:
            kwargs.update(suspend=None, suspend_mask=suspend_mask,
                          suspend_missing=suspend_missing)
        inputs, meta = build_tradability_inputs(**kwargs)

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

    def build_plan(self, dates, codes):
        """P-023：返回 TradabilityPlan（逐块读面板，不缓存 float 面板）。"""
        requested = self.mode
        if requested not in ("auto", "full", "execution_only_open", "off"):
            raise ValueError("TradabilitySpec.mode 非法: %r" % (requested,))
        date_strs = [pd.Timestamp(d).strftime("%Y-%m-%d") for d in dates]
        index = pd.DatetimeIndex(pd.to_datetime(date_strs))
        codes = [str(c) for c in codes]
        if not codes:
            raise ValueError("TradabilitySpec.build_plan 需要非空 codes")
        chunk_days = self.max_dates_per_chunk
        if chunk_days is None:
            chunk_days = max(1, len(index))
        if not isinstance(chunk_days, (int, np.integer)):
            raise ValueError("max_dates_per_chunk 必须为整数或 None")
        chunk_days = int(chunk_days)
        if chunk_days < 1:
            raise ValueError("max_dates_per_chunk 必须 >=1")
        name_rec = self._read_panel("name")
        suspend_rec = self._read_panel("suspend")
        list_date = self._list_date(
            self._panel_df(self._read_panel("list_date")), codes)
        if self.stk_limit_path:
            limit_up, limit_down, limit_diag = load_stk_limit(
                self.stk_limit_path, index, codes)
        else:
            limit_up = limit_down = None
            limit_diag = {}
        plan = TradabilityPlan(
            spec=self, index=index, codes=codes, chunk_days=chunk_days,
            name_rec=name_rec, suspend_rec=suspend_rec,
            list_date=list_date, limit_up=limit_up,
            limit_down=limit_down, limit_diag=limit_diag,
            requested=requested)
        plan._prepare()
        return plan

    # ── 内部 ─────────────────────────────────────────────────────────
    def _read_panel(self, name):
        key = (self.data_root, self.panel_dir, name)
        rec = _PANEL_CACHE.get(key)
        if rec is not None:
            return rec
        if name == "name":
            rec = load_name_compact(self._name_compact_path(),
                                    self._name_pkl_path())
            if rec is not None:
                _PANEL_CACHE[key] = rec
                return rec
        path = os.path.join(self.data_root, self.panel_dir,
                            "stock_%s.pkl" % name)
        if not os.path.exists(path):
            return None
        frame = _normalize_index(pd.read_pickle(path))
        rec = self._compact_panel(name, frame)
        _PANEL_CACHE[key] = rec
        return rec

    @staticmethod
    def _compact_panel(name, frame):
        """name → float32 码；suspend → bool mask/missing；其余保持原样。"""
        index, columns = frame.index, frame.columns
        if name == "name" and not _has_bool_columns(frame):
            arr = frame.to_numpy(dtype=object)
            flat = arr.ravel()
            codes, uniques = pd.factorize(flat, sort=False)
            if len(uniques) > 2 ** 24:
                logger.warning("name 唯一值 %d 超过 float32 精确上限，回退 raw",
                               len(uniques))
                return _PanelRecord("raw", index, columns, frame)
            st_lut = np.array(["ST" in str(u) for u in uniques], dtype=bool)
            del_lut = np.array(["退" in str(u) for u in uniques], dtype=bool)
            codes_f = codes.astype(np.float32)
            codes_f[codes < 0] = np.nan
            codes_f = codes_f.reshape(frame.shape)
            del arr, flat, codes, frame
            gc.collect()
            return _PanelRecord("name", index, columns, codes_f,
                                (tuple(uniques), st_lut, del_lut))
        if name == "suspend" and not _has_bool_columns(frame):
            mask = frame.astype(object).eq("S").to_numpy(dtype=bool)
            missing = frame.isna().to_numpy(dtype=bool)
            del frame
            gc.collect()
            return _PanelRecord("suspend", index, columns, (mask, missing))
        kind = ("float" if name in ("close", "high", "low", "open", "volume",
                                    "adj") else "raw")
        return _PanelRecord(kind, index, columns, frame)

    @staticmethod
    def _panel_df(rec):
        if rec is None:
            return None
        if rec.kind in ("float", "raw"):
            return rec.data
        if rec.kind == "name":
            return pd.DataFrame(rec.data, index=rec.index, columns=rec.columns,
                                copy=False)
        raise ValueError("suspend 记录不是 DataFrame")

    @staticmethod
    def _slice(rec, index, codes):
        """统一返回 (data, aux)；full 命中尽量复用同对象。"""
        if rec is None:
            return None, None
        idx = pd.Index(codes)
        full = rec.index.equals(index) and rec.columns.equals(idx)
        if rec.kind in ("float", "raw"):
            return (rec.data if full
                    else rec.data.reindex(index=index, columns=idx)), None
        if rec.kind == "name":
            arr = (rec.data if full
                   else _take_codes(rec.data, rec.index, rec.columns,
                                    index, idx))
            return (pd.DataFrame(arr, index=index, columns=idx, copy=False),
                    rec.aux)
        if rec.kind == "suspend":
            mask, missing = rec.data
            if full:
                return (mask, missing), None
            return (_take_bool(mask, rec.index, rec.columns, index, idx, False),
                    _take_bool(missing, rec.index, rec.columns, index, idx,
                               True)), None
        raise ValueError("未知 _PanelRecord.kind: %r" % (rec.kind,))

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


@dataclass(frozen=True)
class TradabilityChunk(object):
    """一个日期分块 [start, stop)。"""
    start: int
    stop: int
    index: pd.DatetimeIndex


@dataclass
class ChunkResult(object):
    """build_chunk 返回值：块 inputs + counts + 下一块关键帧。"""
    inputs: object
    counts: dict
    prev_close0: Optional[np.ndarray]
    close_last: np.ndarray
    name_last: np.ndarray


class TradabilityPlan(object):
    """P-023 分块计划：全局解析 + 逐块读面板（不写 float 面板缓存）。"""

    COUNT_KEYS = (
        "name_missing_cells", "name_missing_days",
        "suspend_missing_cells", "suspend_missing_days",
        "ref_fallback_cells", "ref_fallback_days",
        "rule_gap_cells", "rule_gap_days", "rule_gap_bse_cells",
        "one_word_up", "one_word_down",
        "limit_table_missing_cells", "st_date_unverified",
        "no_limit_cells", "st_stock_days", "delisting_stock_days",
        "adj_missing_days",
    )

    def __init__(self, spec, index, codes, chunk_days, name_rec,
                 suspend_rec, list_date, limit_up, limit_down, limit_diag,
                 requested):
        self.spec = spec
        self.index = index
        self.codes = codes
        self.chunk_days = int(chunk_days)
        self.name_rec = name_rec
        self.suspend_rec = suspend_rec
        self.list_date = list_date
        self.limit_up = limit_up
        self.limit_down = limit_down
        self.limit_diag = dict(limit_diag or {})
        self.requested = requested
        self.mode = None
        self.policy = None
        self.coverage = None
        self.meta = None
        self.diagnostics = None
        self._agg = {}
        self._cov_counts = {}
        self._next_start = 0
        self._last_close = None
        self._last_adj = None
        self._last_name = None
        self._panel_codes = None
        self._codes_not_found = []
        self._degrade_reason = None
        self._no_limit_global = None
        self._no_limit_source = "delisting_only"
        self._adj_path = os.path.join(spec.data_root, spec.panel_dir,
                                      "stock_adj.pkl")
        self._has_adj = os.path.exists(self._adj_path)
        boards = np.array([board_of(c) for c in codes])
        self._board_counts = dict(Counter(boards.tolist()))
        self._unknown_codes = [str(c) for c, b in zip(codes, boards)
                              if b == "unknown"][:20]

    # ── 区间与面板读取 ───────────────────────────────────────────────
    def _spans(self):
        T = len(self.index)
        for s in range(0, T, self.chunk_days):
            yield s, min(s + self.chunk_days, T)

    def _read_panel_chunk(self, name, idx, codes):
        path = os.path.join(self.spec.data_root, self.spec.panel_dir,
                            "stock_%s.pkl" % name)
        if not os.path.exists(path):
            return None, None
        frame = _normalize_index(pd.read_pickle(path))
        src_cols = frame.columns
        out = frame.reindex(index=idx, columns=pd.Index(codes))
        del frame
        return out, src_cols

    def _chunk_suspend(self, idx):
        rec = self.suspend_rec
        if rec is None:
            return np.zeros((len(idx), len(self.codes)), dtype=bool)
        data, _ = self.spec._slice(rec, idx, self.codes)
        if rec.kind == "suspend":
            return np.asarray(data[0], dtype=bool)
        mask, _ = _suspend_mask(data, idx, pd.Index(self.codes))
        return mask

    def _chunk_name(self, idx, carry):
        """返回 (ffill 后名称码/名称, is_delisting)；无 name 面板 → (None, 0)。"""
        rec = self.name_rec
        N = len(self.codes)
        if rec is None:
            return None, np.zeros((len(idx), N), dtype=bool)
        data, aux = self.spec._slice(rec, idx, self.codes)
        if rec.kind == "name":
            arr = data.to_numpy(dtype=np.float32, copy=True)
            if carry is not None and len(idx):
                c = np.asarray(carry, dtype=np.float32)
                if c.shape != (N,):
                    raise ValueError("name_carry 形状应为 (%d,) (实际 %r)"
                                     % (N, c.shape))
                invalid = ~np.isfinite(arr[0])
                arr[0, invalid] = c[invalid]
            filled = pd.DataFrame(arr, index=idx,
                                  columns=pd.Index(self.codes)) \
                .ffill().to_numpy(dtype=np.float32)
            del arr
            valid = np.isfinite(filled)
            idxs = np.where(valid, filled, 0).astype(np.int32)
            is_del = np.zeros(valid.shape, dtype=bool)
            if valid.any():
                del_lut = np.asarray(aux[2])
                if int(idxs[valid].max()) >= len(del_lut):
                    raise ValueError("name_del_lut 长度不足")
                is_del[valid] = del_lut[idxs[valid]]
            return filled, is_del
        arr = data.to_numpy(dtype=object, copy=True)
        if carry is not None and len(idx):
            c = np.asarray(carry, dtype=object)
            if c.shape != (N,):
                raise ValueError("name_carry 形状应为 (%d,) (实际 %r)"
                                 % (N, c.shape))
            invalid = pd.isna(arr[0])
            arr[0, invalid] = c[invalid]
        filled = pd.DataFrame(arr, index=idx,
                              columns=pd.Index(self.codes)) \
            .ffill().fillna("").to_numpy(dtype=object)
        del arr
        is_del = np.zeros(filled.shape, dtype=bool)
        for j in range(N):
            is_del[:, j] = np.fromiter(
                ("退" in str(v) for v in filled[:, j]), dtype=bool,
                count=len(idx))
        return filled, is_del

    # ── 全局解析（覆盖率 / mode / no_limit）───────────────────────────
    def _prepare(self):
        T, N = len(self.index), len(self.codes)
        cov = {"eligible_cells": 0, "high_low_covered": 0,
               "open_covered": 0, "prev_eligible": 0, "prev_covered": 0}
        no_limit = np.zeros((T, N), dtype=bool)
        if self.list_date is not None:
            ld = pd.Series(self.list_date)
            norm = {}
            for k, v in ld.items():
                norm.setdefault(_norm_code(k), v)
            used = False
            for j, code in enumerate(self.codes):
                if code in ld.index:
                    value = ld.loc[code]
                else:
                    nk = _norm_code(code)
                    if nk not in norm:
                        continue
                    value = norm[nk]
                if pd.isna(value):
                    continue
                used = True
                pos = np.flatnonzero(self.index >= pd.Timestamp(value))
                no_limit[pos[:5], j] = True
            if used:
                self._no_limit_source = "list_date"
        first_del = np.full(N, -1, dtype=int)
        carry = None
        last_close = None
        for s, e in self._spans():
            idx = self.index[s:e]
            close_df, src_cols = self._read_panel_chunk(
                "close", idx, self.codes)
            if close_df is None:
                raise ValueError("TradabilityPlan: 缺少面板 close")
            if self._panel_codes is None:
                self._panel_codes = set(map(str, src_cols))
                if not any(c in self._panel_codes for c in self.codes):
                    raise ValueError(
                        "TradabilitySpec: 请求代码均不在 stock_close 面板")
                self._codes_not_found = [
                    c for c in self.codes if c not in self._panel_codes][:20]
            high_df, _ = self._read_panel_chunk("high", idx, self.codes)
            low_df, _ = self._read_panel_chunk("low", idx, self.codes)
            open_df, _ = self._read_panel_chunk("open", idx, self.codes)
            susp = self._chunk_suspend(idx)
            close_a = close_df.to_numpy(dtype=float)
            eligible = np.isfinite(close_a) & ~susp
            cov["eligible_cells"] += int(np.count_nonzero(eligible))
            if high_df is not None and low_df is not None:
                cov["high_low_covered"] += int(np.count_nonzero(
                    np.isfinite(high_df.to_numpy(dtype=float))
                    & np.isfinite(low_df.to_numpy(dtype=float))
                    & eligible))
            if open_df is not None:
                cov["open_covered"] += int(np.count_nonzero(
                    np.isfinite(open_df.to_numpy(dtype=float)) & eligible))
            prev = np.full_like(close_a, np.nan)
            if len(idx) > 1:
                prev[1:] = close_a[:-1]
            if s > 0:
                if last_close is not None:
                    prev[0] = last_close
                elig_prev = eligible
            else:
                elig_prev = eligible.copy()
                if len(idx):
                    elig_prev[0] = False
            cov["prev_eligible"] += int(np.count_nonzero(elig_prev))
            cov["prev_covered"] += int(np.count_nonzero(
                np.isfinite(prev) & elig_prev))
            if len(close_a):
                last_close = close_a[-1].copy()
            filled, is_del = self._chunk_name(idx, carry)
            if filled is not None and len(idx):
                carry = filled[-1].copy()
            for j in range(N):
                if first_del[j] >= 0 or not len(idx):
                    continue
                hits = np.flatnonzero(is_del[:, j])
                if hits.size:
                    first_del[j] = s + int(hits[0])
                    no_limit[first_del[j], j] = True
            no_limit[s:e] &= ~susp
            del close_df, high_df, low_df, open_df, close_a, elig_prev

        denom = cov["eligible_cells"]
        self._cov_counts = cov
        self.coverage = {
            "high_low": (float(cov["high_low_covered"]) / denom
                         if denom else 0.0),
            "open": (float(cov["open_covered"]) / denom if denom else 0.0),
            "prev": (float(cov["prev_covered"]) / cov["prev_eligible"]
                     if cov["prev_eligible"] else 0.0),
            "eligible_cells": int(denom),
        }
        resolved, reason = self.spec._resolve_mode(
            self.requested, self.coverage["high_low"], self.coverage["open"],
            self.coverage["prev"], has_adj=self._has_adj)
        self._degrade_reason = reason
        if resolved == "off":
            self.mode = "off"
            self.meta = {"mode": "off", "mode_requested": self.requested,
                         "degrade_reason": reason, "coverage": self.coverage}
            self.diagnostics = None
            return
        self.mode = resolved
        self.policy = replace(self.spec.policy, mode=resolved,
                              execute_at="next_open")
        self._no_limit_global = no_limit

    # ── 分块构建 ─────────────────────────────────────────────────────
    def iter_chunks(self):
        """顺序迭代块；每次调用重置跨块 carry 与聚合器。"""
        self._next_start = 0
        self._last_close = None
        self._last_adj = None
        self._last_name = None
        self._agg = {}
        if self.mode != "off":
            self.meta = None
            self.diagnostics = None
        for s, e in self._spans():
            yield TradabilityChunk(s, e, self.index[s:e])

    def build_chunk(self, chunk):
        if self.mode == "off":
            raise ValueError("plan.mode='off' 不构造 TradabilityInputs")
        if chunk.start != self._next_start:
            raise ValueError("build_chunk 必须按 iter_chunks 顺序调用")
        s, e = chunk.start, chunk.stop
        idx = chunk.index
        close_df, _ = self._read_panel_chunk("close", idx, self.codes)
        if close_df is None:
            raise ValueError("TradabilityPlan: 缺少面板 close")
        high_df, _ = self._read_panel_chunk("high", idx, self.codes)
        low_df, _ = self._read_panel_chunk("low", idx, self.codes)
        open_df, _ = self._read_panel_chunk("open", idx, self.codes)
        adj_df = (self._read_panel_chunk("adj", idx, self.codes)[0]
                  if self._has_adj else None)
        close_a = close_df.to_numpy(dtype=float)
        prev_close0 = self._last_close if s > 0 else None
        adj_prev0 = (self._last_adj
                     if (s > 0 and adj_df is not None) else None)
        name_carry = self._last_name if s > 0 else None
        kwargs = dict(
            close=close_df, high=high_df, low=low_df, open_=open_df,
            volume=None, suspend=None, name=None, adj=adj_df,
            list_date=self.list_date, policy=self.policy,
            limit_up=(None if self.limit_up is None
                      else self.limit_up[s:e]),
            limit_down=(None if self.limit_down is None
                        else self.limit_down[s:e]),
            prev_close0=prev_close0, adj_prev0=adj_prev0,
            name_carry=name_carry,
            no_limit_override=self._no_limit_global[s:e],
            return_counts=True)
        if self.name_rec is not None:
            name_data, aux = self.spec._slice(
                self.name_rec, idx, self.codes)
            if self.name_rec.kind == "name":
                kwargs.update(name=None, name_codes=name_data,
                              name_st_lut=aux[1], name_del_lut=aux[2])
            else:
                kwargs.update(name=name_data)
        if self.suspend_rec is not None:
            susp_data, _ = self.spec._slice(
                self.suspend_rec, idx, self.codes)
            if self.suspend_rec.kind == "suspend":
                kwargs.update(suspend=None, suspend_mask=susp_data[0],
                              suspend_missing=susp_data[1])
            else:
                kwargs.update(suspend=susp_data)
        if adj_df is None:
            prev = np.full_like(close_a, np.nan)
            if len(idx) > 1:
                prev[1:] = close_a[:-1]
            if prev_close0 is not None and len(idx):
                prev[0] = prev_close0
            kwargs.update(ref=prev)
        inputs, counts = build_tradability_inputs(**kwargs)
        for key, value in counts.items():
            if key == "last_filled_name":
                continue
            if key in ("eligible_cells", "high_low_covered",
                       "open_covered"):
                continue
            self._agg[key] = self._agg.get(key, 0) + int(value)
        close_last = (close_a[-1].copy() if len(close_a)
                      else np.full(len(self.codes), np.nan))
        adj_last = (adj_df.to_numpy(dtype=float)[-1].copy()
                    if adj_df is not None and len(idx) else None)
        self._last_close = close_last
        self._last_adj = adj_last
        self._last_name = counts["last_filled_name"]
        self._next_start = e
        return ChunkResult(inputs=inputs, counts=counts,
                           prev_close0=prev_close0,
                           close_last=close_last,
                           name_last=self._last_name)

    # ── 聚合 ─────────────────────────────────────────────────────────
    def finalize(self):
        """汇总 meta（13 键）与 diagnostics；幂等。"""
        if self.mode == "off":
            return self.meta
        if self.meta is not None:
            return self.meta
        agg = {k: int(self._agg.get(k, 0)) for k in self.COUNT_KEYS}
        cov = self._cov_counts
        denom = cov.get("eligible_cells", 0)
        high_low = (float(cov.get("high_low_covered", 0)) / denom
                    if denom else 0.0)
        open_cov = (float(cov.get("open_covered", 0)) / denom
                    if denom else 0.0)
        prev_den = cov.get("prev_eligible", 0)
        prev_cov = (float(cov.get("prev_covered", 0)) / prev_den
                    if prev_den else 0.0)
        adj_source = "adj" if self._has_adj else "none"
        tiers = []
        if not self._has_adj or agg["ref_fallback_cells"] > 0:
            tiers.append(1)
        if agg["name_missing_cells"] > 0:
            tiers.append(2)
        if agg["suspend_missing_cells"] > 0:
            tiers.append(3)
        if (self.list_date is None
                or self._no_limit_source != "list_date"):
            tiers.append(4)
        tier = min(tiers) if tiers else 0
        data_tier = "D%d" % tier
        if tier == 0:
            bias_direction = "none"
        elif tier <= 3:
            bias_direction = "optimistic"
        else:
            bias_direction = "conservative"
        missing_fields = []
        if not self._has_adj:
            missing_fields.append("adj")
        if agg["name_missing_cells"] > 0 or self.name_rec is None:
            missing_fields.append("name")
        if (agg["suspend_missing_cells"] > 0
                or self.suspend_rec is None):
            missing_fields.append("suspend")
        if self.list_date is None:
            missing_fields.append("list_date")
        if high_low < 1.0 or open_cov < 1.0:
            missing_fields.append("ohlc")
        if not self._has_adj:
            price_basis_detail = "raw_close"
        elif agg["ref_fallback_cells"] > 0:
            price_basis_detail = "raw_adj_ref_with_fallback"
        else:
            price_basis_detail = "raw_adj_ref_full"
        if agg["rule_gap_bse_cells"] > 0:
            rule_gap_reason = "neeq_pre_select"
        elif agg["rule_gap_cells"] > 0:
            rule_gap_reason = "unknown_board"
        else:
            rule_gap_reason = None
        if self.limit_up is not None:
            limit_missing = agg["limit_table_missing_cells"]
            limit_source = ("stk_limit_partial" if limit_missing
                            else "stk_limit")
        else:
            limit_missing = 0
            limit_source = "self_computed"
        self.meta = {
            "board_counts": self._board_counts,
            "unknown_codes": self._unknown_codes,
            "st_stock_days": agg["st_stock_days"],
            "delisting_stock_days": agg["delisting_stock_days"],
            "no_limit_cells": agg["no_limit_cells"],
            "no_limit_source": self._no_limit_source,
            "adj_missing_days": agg["adj_missing_days"],
            "one_word_up_cells": agg["one_word_up"],
            "one_word_down_cells": agg["one_word_down"],
            "st_date_unverified": agg["st_date_unverified"],
            "st_calibration_source": "none",
            "price_basis": ("raw_close" if not self._has_adj
                            else "raw_adj_ref"),
            "rounding_basis": (
                "inferred_half_up" if self._board_counts.get("bse", 0)
                else "exchange_half_up"),
        }
        diag = {
            "schema_version": 2,
            "mode": self.mode,
            "one_word_disabled": self.mode == "execution_only_open",
            "high_low_coverage": high_low,
            "open_coverage": open_cov,
            "prev_close_coverage": prev_cov,
            "adj_source": adj_source,
            "data_tier": data_tier,
            "missing_fields": missing_fields,
            "bias_direction": bias_direction,
            "price_basis_detail": price_basis_detail,
            "unknown_policy": self.policy.unknown_policy,
            "ref_fallback_cells": agg["ref_fallback_cells"],
            "ref_fallback_days": agg["ref_fallback_days"],
            "name_missing_cells": agg["name_missing_cells"],
            "name_missing_days": agg["name_missing_days"],
            "suspend_missing_cells": agg["suspend_missing_cells"],
            "suspend_missing_days": agg["suspend_missing_days"],
            "rule_gap_cells": agg["rule_gap_cells"],
            "rule_gap_days": agg["rule_gap_days"],
            "rule_gap_reason": rule_gap_reason,
            "limit_table_source": limit_source,
            "limit_table_missing_cells": limit_missing,
            "mode_requested": self.requested,
            "degrade_reason": self._degrade_reason,
            "codes_not_found": self._codes_not_found,
            "coverage": self.coverage,
        }
        if self.limit_up is not None:
            diag["limit_table_duplicate_rows"] = int(
                self.limit_diag.get("limit_table_duplicate_rows", 0))
        self.diagnostics = diag
        return self.meta


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
