# -*- coding: utf-8 -*-
"""P-006 Step 9：`build_tradability_inputs` 验收（TP6-4/7 构建器侧、TP6-8 派生侧）。"""
import numpy as np
import pandas as pd
import pytest

from backtest.tradability import compute_limits
from backtest.tradability_inputs import build_tradability_inputs


_META_KEYS = {
    "board_counts", "unknown_codes", "st_stock_days", "delisting_stock_days",
    "no_limit_cells", "no_limit_source", "adj_missing_days",
    "one_word_up_cells", "one_word_down_cells", "st_date_unverified",
    "st_calibration_source", "price_basis", "rounding_basis",
}


def _panels(n_dates=8):
    dates = pd.date_range("2024-01-02", periods=n_dates, freq="B")
    codes = ["600000.SH", "000001.SZ", "302132.SZ", "689009.SH",
             "920001.BJ", "900001"]
    close = pd.DataFrame(10.0, index=dates, columns=codes)
    high = close * 1.005
    low = close * 0.995
    open_ = close.copy()
    volume = pd.DataFrame(1e6, index=dates, columns=codes)
    suspend = pd.DataFrame(False, index=dates, columns=codes)
    name = pd.DataFrame("普通", index=dates, columns=codes)
    name.iloc[:, 0] = "ST测试"
    name.iloc[4:, 1] = "退市测试"
    adj = pd.DataFrame(1.0, index=dates, columns=codes)

    # 一字涨停：302132（gem 20%）prev=10 → up=12（t=6，避开 IPO 前 5 日）
    close.iloc[6, 2] = 12.0
    high.iloc[6, 2] = 12.0
    low.iloc[6, 2] = 12.0

    # adj 单侧缺失：t=3 的 adj 为 NaN（t=2 有限）
    adj.iloc[3, 0] = np.nan

    return dict(close=close, high=high, low=low, open_=open_, volume=volume,
                suspend=suspend, name=name, adj=adj, dates=dates, codes=codes)


def _build(**overrides):
    p = _panels()
    kwargs = dict(close=p["close"], high=p["high"], low=p["low"],
                  open_=p["open_"], volume=p["volume"], suspend=p["suspend"],
                  name=p["name"], adj=p["adj"],
                  list_date=pd.Series({
                      "600000.SH": p["dates"][0], "000001.SZ": p["dates"][2],
                      "302132.SZ": p["dates"][0], "689009.SH": p["dates"][1],
                      "920001.BJ": p["dates"][0]}))
    kwargs.update(overrides)
    return build_tradability_inputs(**kwargs), p


def test_meta_keys_and_price_basis():
    (inputs, meta), p = _build()
    assert set(meta) == _META_KEYS
    assert meta["price_basis"] == "raw_adj_ref"
    assert meta["rounding_basis"] == "inferred_half_up"      # 含 bse
    assert inputs.close.shape == (len(p["dates"]), len(p["codes"]))
    assert inputs.board.shape == (len(p["codes"]),)
    assert meta["board_counts"].get("unknown", 0) == 1
    assert "900001" in meta["unknown_codes"]


def test_tp6_4_bse_half_up_inferred():
    """TP6-4：BSE 30% 取整 + 无明文假设披露。"""
    up, down, _ = compute_limits(10.0, 0.30)
    assert up == pytest.approx(13.00)
    assert down == pytest.approx(7.00)
    (_, meta), _ = _build()
    assert meta["rounding_basis"] == "inferred_half_up"

    # 不含 bse → exchange_half_up
    dates = pd.date_range("2024-01-02", periods=3, freq="B")
    codes = ["600000.SH", "000001.SZ"]
    close = pd.DataFrame(10.0, index=dates, columns=codes)
    frame = dict(close=close, high=close * 1.01, low=close * 0.99,
                 open_=close.copy(), volume=pd.DataFrame(1e6, index=dates,
                                                         columns=codes),
                 suspend=pd.DataFrame(False, index=dates, columns=codes),
                 name=pd.DataFrame("普通", index=dates, columns=codes),
                 adj=pd.DataFrame(1.0, index=dates, columns=codes))
    _, meta_main = build_tradability_inputs(**frame)
    assert meta_main["rounding_basis"] == "exchange_half_up"


def test_tp6_7_meta_single_side_missing():
    """TP6-7（meta 侧）：单侧 adj 缺失日期计数 >0。"""
    (_, meta), _ = _build()
    assert meta["adj_missing_days"] > 0


def test_tp6_8_derived_state():
    """TP6-8（派生侧）：ST 不含退；退市含退；退市整理首日 no_limit。"""
    (inputs, meta), p = _build()
    codes = p["codes"]
    j_st = codes.index("600000.SH")
    j_del = codes.index("000001.SZ")
    assert inputs.is_st[:, j_st].all()
    assert not inputs.is_delisting[:, j_st].any()
    assert not inputs.is_st[:, j_del].any()
    assert inputs.is_delisting[4:, j_del].all()
    assert inputs.no_limit[4, j_del]
    assert meta["st_stock_days"] == int(inputs.is_st.sum())
    assert meta["delisting_stock_days"] == int(inputs.is_delisting.sum())


def test_ipo_no_limit_and_source():
    (inputs, meta), p = _build()
    j = p["codes"].index("600000.SH")
    assert inputs.no_limit[:5, j].all()
    assert not inputs.no_limit[5, j]
    # list_date = dates[2] 的股票：t=2..6
    j2 = p["codes"].index("000001.SZ")
    assert inputs.no_limit[2:7, j2].all()
    assert not inputs.no_limit[7, j2]
    assert meta["no_limit_source"] == "list_date"
    assert meta["no_limit_cells"] == int(inputs.no_limit.sum())


def test_no_limit_source_delisting_only():
    (inputs, meta), p = _build(list_date=None)
    assert meta["no_limit_source"] == "delisting_only"
    j = p["codes"].index("000001.SZ")
    assert inputs.no_limit[4, j]
    assert int(inputs.no_limit.sum()) == 1


def test_st_overrides_calibration():
    (_, meta0), p = _build()
    assert meta0["st_date_unverified"] == 0
    assert meta0["st_calibration_source"] == "none"

    ov = pd.DataFrame({"code": ["600000.SH"], "effective_date": [p["dates"][0]]})
    (_, meta1), _ = _build(st_overrides=ov)
    assert meta1["st_calibration_source"] == "coverage_table"
    assert meta1["st_date_unverified"] == 0

    ov_bad = pd.DataFrame({"code": ["600000.SH"],
                           "effective_date": [p["dates"][3]]})
    (_, meta2), _ = _build(st_overrides=ov_bad)
    assert meta2["st_date_unverified"] == 1


def test_one_word_counts():
    (_, meta), _ = _build()
    assert meta["one_word_up_cells"] >= 1
    assert meta["one_word_down_cells"] == 0


def test_grid_alignment():
    p = _panels()
    high = p["high"].copy()
    high["600001.SH"] = 99.0                    # 多余列 → 应被丢弃
    high = high.drop(index=high.index[0])       # 缺一行 → 填 NaN
    (inputs, _), _ = _build(high=high)
    assert inputs.high.shape == (len(p["dates"]), len(p["codes"]))
    assert np.isnan(inputs.high[0, 0])


def test_adj_required():
    p = _panels()
    with pytest.raises(ValueError):
        build_tradability_inputs(p["close"], p["high"], p["low"], p["open_"],
                                 p["volume"], p["suspend"], p["name"], None)
