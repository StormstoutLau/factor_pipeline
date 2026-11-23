# -*- coding: utf-8 -*-
"""P-021 A4：TradabilitySpec 契约、缓存、切片一致性、pickle。"""
import pickle

import numpy as np
import pandas as pd

from backtest.tradability import apply_tradability
from backtest.tradability_loader import TradabilitySpec


def _write(tmp_path, n=6):
    md = tmp_path / "market_data"
    md.mkdir(parents=True, exist_ok=True)
    dates = pd.date_range("2024-01-02", periods=n, freq="B")
    codes = ["600000.SH", "000001.SZ", "300001.SZ"]
    close = pd.DataFrame(10.0, index=dates, columns=codes)
    close.to_pickle(md / "stock_close.pkl")
    (close * 1.001).to_pickle(md / "stock_high.pkl")
    (close * 0.999).to_pickle(md / "stock_low.pkl")
    close.to_pickle(md / "stock_open.pkl")
    pd.DataFrame(1e6, index=dates, columns=codes).to_pickle(
        md / "stock_volume.pkl")
    pd.DataFrame(np.nan, index=dates, columns=codes,
                 dtype=object).to_pickle(md / "stock_suspend.pkl")
    pd.DataFrame("普通", index=dates, columns=codes).to_pickle(
        md / "stock_name.pkl")
    pd.DataFrame(1.0, index=dates, columns=codes).to_pickle(
        md / "stock_adj.pkl")
    return dates, codes


def test_p021_loader_signature(tmp_path):
    """I-8：字段齐备、frozen、build 返回 (inputs, meta)。"""
    spec = TradabilitySpec(data_root=str(tmp_path))
    for field in ("data_root", "panel_dir", "policy", "mode", "auto_degrade",
                  "min_coverage", "stk_limit_path"):
        assert hasattr(spec, field)
    assert spec.mode == "auto" and spec.min_coverage == 0.99
    dates, codes = _write(tmp_path)
    inputs, meta = spec.build(dates, codes)
    assert inputs is not None and isinstance(meta, dict)
    assert inputs.diagnostics["schema_version"] == 2


def test_p021_spec_pickle(tmp_path):
    """I-8：spec 可 pickle（Windows spawn），恢复后可 build。"""
    dates, codes = _write(tmp_path)
    spec = TradabilitySpec(data_root=str(tmp_path))
    restored = pickle.loads(pickle.dumps(spec))
    inputs, _ = restored.build(dates, codes)
    assert inputs is not None


def test_p021_loader_cache(tmp_path, monkeypatch):
    """P-5：同进程第二次 build 不重复读 pickle。"""
    dates, codes = _write(tmp_path)
    calls = {"n": 0}
    real = pd.read_pickle

    def _counting(path, *args, **kwargs):
        calls["n"] += 1
        return real(path, *args, **kwargs)

    monkeypatch.setattr(pd, "read_pickle", _counting)
    spec = TradabilitySpec(data_root=str(tmp_path))
    spec.build(dates, codes)
    first = calls["n"]
    spec.build(dates, codes)
    assert first > 0
    assert calls["n"] == first


def test_p021_loader_str_index_panels(tmp_path):
    """真实数据根面板 index 为字符串日期（object）→ build 仍命中（审计 P1-①）。"""
    dates, codes = _write(tmp_path)
    md = tmp_path / "market_data"
    for name in ("close", "high", "low", "open", "volume", "suspend",
                 "name", "adj"):
        path = md / ("stock_%s.pkl" % name)
        frame = pd.read_pickle(path)
        frame.index = [d.strftime("%Y-%m-%d") for d in frame.index]
        frame.to_pickle(path)
    inputs, meta = TradabilitySpec(data_root=str(tmp_path)).build(dates, codes)
    assert inputs is not None
    assert np.isfinite(inputs.close).all()
    assert inputs.diagnostics["coverage"]["eligible_cells"] > 0


def test_p021_loader_list_date_panel(tmp_path):
    """观察项 #9：list_date 单行 DataFrame 形态 → IPO 前 5 日豁免接线。"""
    dates, codes = _write(tmp_path, n=8)
    md = tmp_path / "market_data"
    ld = pd.DataFrame([["2024-01-03", "2020-01-01", "2020-01-01"]],
                      index=["list_date"], columns=codes)
    ld.to_pickle(md / "stock_list_date.pkl")
    inputs, _ = TradabilitySpec(data_root=str(tmp_path)).build(dates, codes)
    assert inputs is not None
    # 600000.SH 于 dates[1]（2024-01-03）上市 → pos=flatnonzero(date>=ld)[:5]
    assert inputs.no_limit[0, 0] == 0          # 上市前不豁免
    assert inputs.no_limit[2, 0] != 0          # 上市后 5 个面板日内豁免
    assert inputs.no_limit[7, 0] == 0          # 窗口外不豁免
    # 老股（list_date 早于面板起点）：pos[:5]=t0..t4 全豁免（既有 pos[:5] 语义）
    assert inputs.no_limit[0, 1] != 0


def test_p021_parallel_slice_equal(tmp_path):
    """INV-12：切片 build 与全量 build 在同 (dates, codes) 上逐位一致。"""
    dates, codes = _write(tmp_path)
    spec = TradabilitySpec(data_root=str(tmp_path))
    full, _ = spec.build(dates, codes)
    part, _ = spec.build(dates[:3], codes[:2])
    sub_rows = [0, 1, 2]          # 与全量前 3 行同序
    for name in ("close", "high", "low", "open_", "volume", "suspended",
                 "ref", "limit_up", "limit_down"):
        a = getattr(full, name)
        b = getattr(part, name)
        if a is None:
            assert b is None
            continue
        assert np.allclose(a[sub_rows][:, :2], b, equal_nan=True)
    # report 直接对比（审计 P3-#7：切片 build report ↔ 全量子块 report）
    target = np.zeros((3, 2))
    target[1, 0] = 0.5

    sub = {n: getattr(full, n)[sub_rows][:, :2]
           for n in ("close", "high", "low", "open_", "volume", "suspended",
                     "ref")}
    r1 = apply_tradability(
        target.copy(), np.full((3, 2), np.nan), part.high, part.low,
        part.close, part.open_, part.volume, part.suspended, part.board,
        np.zeros(2, dtype=bool), part.dates, policy=part.policy,
        adj=None, ref=part.ref)[1]
    r2 = apply_tradability(
        target.copy(), np.full((3, 2), np.nan), sub["high"], sub["low"],
        sub["close"], sub["open_"], sub["volume"], sub["suspended"],
        full.board[:2], np.zeros(2, dtype=bool), full.dates[sub_rows],
        policy=full.policy, adj=None, ref=sub["ref"])[1]
    assert r1 == r2
