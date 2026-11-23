# -*- coding: utf-8 -*-
"""P-021 A3：D2 fallback_raw / pass legacy / loader 缺 adj。"""
import numpy as np
import pandas as pd
import pytest

from backtest.tradability import TradabilityPolicy
from backtest.tradability_inputs import build_tradability_inputs


def _panels(adj=None, n=3, codes=("600000.SH",)):
    dates = pd.date_range("2024-01-02", periods=n, freq="B")
    close = pd.DataFrame(10.0, index=dates, columns=list(codes))
    out = dict(close=close, high=close * 1.001, low=close * 0.999,
               open_=close.copy(),
               volume=pd.DataFrame(1e6, index=dates, columns=list(codes)),
               suspend=pd.DataFrame(False, index=dates, columns=list(codes)),
               name=pd.DataFrame("普通", index=dates, columns=list(codes)))
    if adj is not None:
        out["adj"] = adj
    return out


def test_p021_d2_fallback_raw():
    """fallback_raw：adj 单侧缺失 → ref=prev；计数 + D1 + 乐观方向。"""
    dates = pd.date_range("2024-01-02", periods=3, freq="B")
    adj = pd.DataFrame([[1.0], [1.0], [np.nan]], index=dates,
                       columns=["600000.SH"])
    inputs, meta = build_tradability_inputs(
        policy=TradabilityPolicy(unknown_policy="fallback_raw"),
        **_panels(adj=adj))
    assert np.isfinite(inputs.ref[1:]).all()     # t=0 为结构性 NaN（无昨收）
    diag = inputs.diagnostics
    assert diag["ref_fallback_cells"] == 1
    assert diag["ref_fallback_days"] == 1
    assert diag["data_tier"] == "D1"
    assert diag["bias_direction"] == "optimistic"
    assert diag["price_basis_detail"] == "raw_adj_ref_with_fallback"
    assert diag["adj_source"] == "adj"


def test_p021_d2_pass_legacy():
    """pass：不回退，ref 保持 NaN，回退计数 0。"""
    dates = pd.date_range("2024-01-02", periods=3, freq="B")
    adj = pd.DataFrame([[1.0], [1.0], [np.nan]], index=dates,
                       columns=["600000.SH"])
    inputs, _ = build_tradability_inputs(
        policy=TradabilityPolicy(unknown_policy="pass"), **_panels(adj=adj))
    assert np.isnan(inputs.ref[2, 0])
    assert inputs.diagnostics["ref_fallback_cells"] == 0
    assert inputs.diagnostics["data_tier"] != "D1"


def test_p021_d2_ref_direct():
    """ref 直传（无 adj）：price_basis=raw_close、adj_source=ref_fallback。"""
    dates = pd.date_range("2024-01-02", periods=3, freq="B")
    ref = pd.DataFrame(10.0, index=dates, columns=["600000.SH"])
    inputs, meta = build_tradability_inputs(
        policy=TradabilityPolicy(unknown_policy="fallback_raw"),
        ref=ref, **_panels(adj=None))
    assert inputs.adj is None
    assert np.isfinite(inputs.ref).all()
    assert meta["price_basis"] == "raw_close"
    assert inputs.diagnostics["adj_source"] == "ref_fallback"


def _write_panels(tmp_path, with_adj=True, with_ohlc=True):
    md = tmp_path / "market_data"
    md.mkdir(parents=True, exist_ok=True)
    dates = pd.date_range("2024-01-02", periods=3, freq="B")
    codes = ["600000.SH", "000001.SZ"]
    close = pd.DataFrame(10.0, index=dates, columns=codes)
    close.to_pickle(md / "stock_close.pkl")
    if with_ohlc:
        (close * 1.001).to_pickle(md / "stock_high.pkl")
        (close * 0.999).to_pickle(md / "stock_low.pkl")
        close.to_pickle(md / "stock_open.pkl")
    pd.DataFrame(1e6, index=dates, columns=codes).to_pickle(
        md / "stock_volume.pkl")
    pd.DataFrame(np.nan, index=dates, columns=codes,
                 dtype=object).to_pickle(md / "stock_suspend.pkl")
    pd.DataFrame("普通", index=dates, columns=codes).to_pickle(
        md / "stock_name.pkl")
    if with_adj:
        pd.DataFrame(1.0, index=dates, columns=codes).to_pickle(
            md / "stock_adj.pkl")
    return dates, codes


def test_p021_d2_loader_no_adj(tmp_path):
    """完全缺 adj：ref=prev + D1 + raw_close + adj_missing_days=T。"""
    from backtest.tradability_loader import TradabilitySpec

    dates, codes = _write_panels(tmp_path, with_adj=False)
    spec = TradabilitySpec(data_root=str(tmp_path))
    inputs, meta = spec.build(dates, codes)
    assert inputs is not None
    assert inputs.adj is None
    assert np.isfinite(inputs.ref[1:]).all()
    assert meta["price_basis"] == "raw_close"
    assert meta["adj_missing_days"] == len(dates)
    diag = inputs.diagnostics
    assert diag["adj_source"] == "none"
    assert diag["data_tier"] == "D1"
    assert diag["mode"] == "execution_only_open"     # auto_degrade


def test_p021_mode_full_no_degrade(tmp_path):
    """full + auto_degrade=False 且缺 adj → ValueError（fail-closed）。"""
    from backtest.tradability_loader import TradabilitySpec

    dates, codes = _write_panels(tmp_path, with_adj=False)
    spec = TradabilitySpec(data_root=str(tmp_path), mode="full",
                           auto_degrade=False)
    with pytest.raises(ValueError):
        spec.build(dates, codes)
