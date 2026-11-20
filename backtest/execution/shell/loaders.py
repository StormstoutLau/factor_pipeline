# -*- coding: utf-8 -*-
"""v3.8.1 Shell 加载器（分钟 / 日频 / 能力探测）。

设计依据：DESIGN §8 §15；实施依据：EXECUTION §2.2。
pyarrow 只在 ``MinuteLoader.load_month`` / ``load_month_regression``
内部延迟 import；缺失时抛 ``CalibrationUnavailable``，由调用方降级 L1。
v3.8.1：分钟 ``stock_code`` 为整数（000001 -> 1），过滤下界修正为 1。
"""
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import numpy as np

from ..ports import CalibrationUnavailable
from ..core.classification import detect_limit_lock, normal_cdf

__all__ = ["has_pyarrow", "MinuteAggregate", "MinuteDayAggregate",
           "MinuteLoader", "DailyLoader", "resolve_evidence_level",
           "MIN_STOCK_CODE", "MAX_STOCK_CODE", "EXCLUDE_CODE"]

MIN_STOCK_CODE = 1          # 分钟 stock_code 为整数（000001 -> 1），下界不得写 100000
MAX_STOCK_CODE = 1000000    # 上界排斥 6 位
EXCLUDE_CODE = (390000, 400000)   # 指数/特殊代码段


def _keep_mask(codes):
    """分钟代码过滤（W5）：保留 1..999999，剔除 390000-399999。"""
    return ((codes >= MIN_STOCK_CODE) & (codes < MAX_STOCK_CODE)
            & ~((codes >= EXCLUDE_CODE[0]) & (codes < EXCLUDE_CODE[1])))


def has_pyarrow():
    """能力探测：pyarrow 是否可用（不触发 import，拦截导入钩子）。"""
    try:
        return importlib.util.find_spec("pyarrow") is not None
    except (ImportError, ValueError):
        return False


def _code_time_sorted(codes, times):
    """是否已按 (stock_code, time) 升序排列（用于跳过全量拷贝排序）。"""
    if codes.size < 2:
        return True
    same = codes[1:] == codes[:-1]
    return bool(np.all(np.where(same, times[1:] >= times[:-1],
                                codes[1:] > codes[:-1])))


@dataclass
class MinuteAggregate(object):
    """单月分钟聚合结果（按股票一行）。"""

    stock_code: np.ndarray
    signed_amount: np.ndarray
    total_amount: np.ndarray
    sigma: np.ndarray
    n_bars: np.ndarray
    limit_lock: np.ndarray
    evidence_level: str = "minutes"


@dataclass
class MinuteDayAggregate(object):
    """单月「股票×日」聚合（逐行 = 一只股票的一个交易日）。"""

    date: np.ndarray          # 'YYYY-MM-DD'（object）
    stock_code: np.ndarray    # int64
    signed_day: np.ndarray    # 元；锁定 bar 的 s_t 记 0（W2 裁决）
    amount_day: np.ndarray    # 元；全量保留（含锁定 bar）
    ret_day: np.ndarray       # close_last / open_first - 1
    sigma: np.ndarray         # 每股月度 σ（同股票所有行相同）
    n_bars: np.ndarray        # 当日 bar 数
    limit_lock: np.ndarray    # 当日 lock 占比 >= 0.5


class MinuteLoader(object):
    """``root/YYYY-MM-DD.feather`` 形态的分钟数据加载器。"""

    def __init__(self, root, sigma_bars=20):
        self.root = Path(root)
        self.sigma_bars = int(sigma_bars)

    def available_months(self):
        """可用月份 'YYYY-MM'（去重升序）。"""
        if not self.root.is_dir():
            return []
        months = set()
        for path in self.root.glob("*.feather"):
            stem = path.stem
            if len(stem) >= 7 and stem[4] == "-":
                months.add(stem[:7])
        return sorted(months)

    def load_month(self, ym):
        """加载单月；数据/依赖缺失抛 CalibrationUnavailable。"""
        if not has_pyarrow():
            raise CalibrationUnavailable("pyarrow 未安装（pip install .[calib]）")
        import pyarrow.feather as feather
        import pandas as pd

        files = sorted(self.root.glob("%s-*.feather" % ym))
        if not files:
            raise CalibrationUnavailable("分钟数据缺失: %s" % ym)
        # 逐日流式聚合，避免整月 concat 导致峰值内存超预算（EXECUTION §6）
        acc = {}  # type: Dict[int, list]
        for path in files:
            table = feather.read_table(path)
            cols = [c for c in ("time", "stock_code", "open", "high", "low",
                                "close", "volume", "amount")
                    if c in table.column_names]
            df = table.select(cols).to_pandas()
            keep = _keep_mask(df["stock_code"].to_numpy())
            df = df.loc[keep].sort_values(["stock_code", "time"],
                                          kind="mergesort")
            if df.empty:
                continue
            ret = df.groupby("stock_code")["close"].pct_change()
            sigma_roll = ret.groupby(df["stock_code"]).transform(
                lambda s: s.rolling(self.sigma_bars, min_periods=2).std(ddof=1))
            with np.errstate(divide="ignore", invalid="ignore"):
                ratio = ret.to_numpy() / sigma_roll.to_numpy()
            phi = normal_cdf(np.where(np.isfinite(ratio), ratio, 0.0))
            tmp = pd.DataFrame({
                "stock_code": df["stock_code"].to_numpy(),
                "signed": df["amount"].to_numpy() * (2.0 * phi - 1.0),
                "amount": df["amount"].to_numpy(),
                "ret": ret.to_numpy(),
                "locked": detect_limit_lock(
                    df["high"].to_numpy(), df["low"].to_numpy(),
                    df["close"].to_numpy(), df["open"].to_numpy(),
                    df["volume"].to_numpy()).astype(float),
            })
            day = tmp.groupby("stock_code", sort=True).agg(
                signed=("signed", "sum"),
                amount=("amount", "sum"),
                rsum=("ret", "sum"),
                r2sum=("ret", lambda s: float(np.nansum(s.to_numpy() ** 2))),
                n=("amount", "size"),
                lock=("locked", "sum"))
            for code, row in zip(day.index.to_numpy(dtype=np.int64),
                                 day.to_numpy(dtype=float)):
                cur = acc.get(int(code))
                if cur is None:
                    acc[int(code)] = [float(row[0]), float(row[1]),
                                      float(row[2]), float(row[3]),
                                      int(row[4]), float(row[5])]
                else:
                    cur[0] += float(row[0])
                    cur[1] += float(row[1])
                    cur[2] += float(row[2])
                    cur[3] += float(row[3])
                    cur[4] += int(row[4])
                    cur[5] += float(row[5])
        if not acc:
            raise CalibrationUnavailable("过滤后无有效股票: %s" % ym)

        codes = np.array(sorted(acc.keys()), dtype=np.int64)
        mat = np.array([acc[int(c)] for c in codes], dtype=float)
        n = mat[:, 4]
        var = (mat[:, 3] - mat[:, 2] ** 2 / n) / np.maximum(n - 1.0, 1.0)
        return MinuteAggregate(
            stock_code=codes,
            signed_amount=mat[:, 0],
            total_amount=mat[:, 1],
            sigma=np.sqrt(np.maximum(var, 0.0)),
            n_bars=n.astype(np.int64),
            limit_lock=(mat[:, 5] / n) >= 0.5)

    def load_month_regression(self, ym):
        """逐日流式 -> 「股票×日」聚合（W2）；缺失抛 CalibrationUnavailable。"""
        if not has_pyarrow():
            raise CalibrationUnavailable("pyarrow 未安装（pip install .[calib]）")
        import pyarrow.feather as feather
        import pandas as pd

        files = sorted(self.root.glob("%s-*.feather" % ym))
        if not files:
            raise CalibrationUnavailable("分钟数据缺失: %s" % ym)

        rows = []          # type: list
        acc = {}           # type: Dict[int, list]  code -> [rsum, r2sum, n]
        for path in files:
            date = path.stem[:10]
            table = feather.read_table(path)
            cols = [c for c in ("time", "stock_code", "open", "high", "low",
                                "close", "volume", "amount")
                    if c in table.column_names]
            df = table.select(cols).to_pandas()
            del table
            df = df.loc[_keep_mask(df["stock_code"].to_numpy())]
            if df.empty:
                continue
            if not _code_time_sorted(df["stock_code"].to_numpy(),
                                     df["time"].to_numpy()):
                df = df.sort_values(["stock_code", "time"], kind="mergesort")
            codes_v = df["stock_code"].to_numpy()
            close_v = df["close"].to_numpy()
            amount_v = df["amount"].to_numpy()
            open_v = df["open"].to_numpy()
            high_v = df["high"].to_numpy()
            low_v = df["low"].to_numpy()
            vol_v = df["volume"].to_numpy()
            del df
            ret = pd.Series(close_v).groupby(codes_v).pct_change()
            sigma_roll = ret.groupby(codes_v).transform(
                lambda s: s.rolling(self.sigma_bars, min_periods=2).std(ddof=1))
            with np.errstate(divide="ignore", invalid="ignore"):
                ratio = ret.to_numpy() / sigma_roll.to_numpy()
            phi = normal_cdf(np.where(np.isfinite(ratio), ratio, 0.0))
            lock = detect_limit_lock(high_v, low_v, close_v, open_v, vol_v)
            signed = np.where(lock, 0.0, amount_v * (2.0 * phi - 1.0))
            ret_v = ret.to_numpy()
            del ret, sigma_roll, ratio, phi, high_v, low_v, vol_v
            tmp = pd.DataFrame({
                "stock_code": codes_v,
                "signed": signed,
                "amount": amount_v,
                "ret": ret_v,
                "r2": ret_v ** 2,
                "lock": lock.astype(float),
                "n": 1.0,
                "open0": open_v,
                "close1": close_v,
            })
            day = tmp.groupby("stock_code", sort=True).agg(
                signed=("signed", "sum"),
                amount=("amount", "sum"),
                rsum=("ret", "sum"),
                r2sum=("r2", "sum"),
                n=("n", "sum"),
                lock=("lock", "sum"),
                open0=("open0", "first"),
                close1=("close1", "last"))
            for code, row in zip(day.index.to_numpy(dtype=np.int64),
                                 day.to_numpy(dtype=float)):
                open0, close1 = float(row[6]), float(row[7])
                if not np.isfinite(open0) or open0 <= 0.0:
                    continue
                nbar = int(row[4])
                rows.append((
                    date, int(code), float(row[0]), float(row[1]),
                    close1 / open0 - 1.0, nbar,
                    bool(nbar > 0 and row[5] / nbar >= 0.5)))
                cur = acc.get(int(code))
                if cur is None:
                    acc[int(code)] = [float(row[2]), float(row[3]), nbar]
                else:
                    cur[0] += float(row[2])
                    cur[1] += float(row[3])
                    cur[2] += nbar
        if not rows:
            raise CalibrationUnavailable("过滤后无有效股票: %s" % ym)

        sigma = {}
        for code, (rsum, r2sum, n) in acc.items():
            if n <= 0:
                sigma[code] = 0.0
                continue
            var = (r2sum - rsum * rsum / n) / max(n - 1.0, 1.0)
            sigma[code] = float(np.sqrt(max(var, 0.0)))
        return MinuteDayAggregate(
            date=np.asarray([r[0] for r in rows], dtype=object),
            stock_code=np.asarray([r[1] for r in rows], dtype=np.int64),
            signed_day=np.asarray([r[2] for r in rows], dtype=float),
            amount_day=np.asarray([r[3] for r in rows], dtype=float),
            ret_day=np.asarray([r[4] for r in rows], dtype=float),
            sigma=np.asarray([sigma[r[1]] for r in rows], dtype=float),
            n_bars=np.asarray([r[5] for r in rows], dtype=np.int64),
            limit_lock=np.asarray([r[6] for r in rows], dtype=bool))


class DailyLoader(object):
    """``market_data/stock_*.pkl`` 形态的日频加载器。"""

    def __init__(self, root):
        self.root = Path(root)

    def _read(self, name):
        import pandas as pd
        path = self.root / "market_data" / ("stock_%s.pkl" % name)
        if not path.exists():
            return None
        return pd.read_pickle(path)

    def load_ohlc(self, start, end):
        """返回 open/high/low/close/volume/amount 的区间切片。"""
        out = {}  # type: Dict[str, object]
        for name in ("open", "high", "low", "close", "volume", "amount"):
            frame = self._read(name)
            if frame is not None:
                out[name] = frame.loc[start:end]
        return out

    def load_adj_jumps(self, start, end):
        """除权跳变日（|adj_factor 变化| > 1e-6）。"""
        import pandas as pd
        path = self.root / "market_data" / "stock_adj.pkl"
        if not path.exists():
            return pd.DataFrame()
        adj = pd.read_pickle(path).loc[start:end]
        jumps = adj.pct_change()
        return jumps.abs() > 1e-6


def resolve_evidence_level(cfg):
    """三级降级：'minutes' | 'ohlc' | 'daily'（不回写任何默认口径）。"""
    minute_root = getattr(cfg, "minute_root", None)
    if minute_root and Path(minute_root).is_dir() and has_pyarrow():
        return "minutes"
    if Path(getattr(cfg, "data_root", "")).is_dir():
        return "ohlc"
    return "daily"
