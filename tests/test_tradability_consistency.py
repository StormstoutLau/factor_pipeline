# -*- coding: utf-8 -*-
"""P-021 C 批：规则边界 + 内部一致性 + mock 限价表扰动（合成数据，RULE-3）。"""
import numpy as np
import pandas as pd
import pytest

from backtest.tradability import (
    _ref_from_adj,
    compute_limits,
    limit_price,
    rule_pct,
)


# ---------------------------------------------------------------------------
# 规则边界（C 批回归锁）
# ---------------------------------------------------------------------------

def test_p021_consistency_gem_reform_boundary():
    """gem 2020-08-24 前后：10% → 20%。"""
    assert rule_pct("gem", False, "2020-08-21") == pytest.approx(0.10)
    assert rule_pct("gem", False, "2020-08-24") == pytest.approx(0.20)


def test_p021_consistency_st_reform_boundary():
    """主板 ST 2026-07-06 起：5% → 10%。"""
    assert rule_pct("main", True, "2026-07-03") == pytest.approx(0.05)
    assert rule_pct("main", True, "2026-07-06") == pytest.approx(0.10)


def test_p021_consistency_low_price_st():
    """低价 ST（prev<0.1 元）：±1 分。"""
    prev = np.array([0.09])
    up, down, unk = compute_limits(prev, np.array([0.05]),
                                   is_st=np.array([True]))
    assert not unk.any()
    assert up[0] == pytest.approx(0.10)
    assert down[0] == pytest.approx(0.08)


def test_p021_consistency_half_up_to_cent():
    """整数分 ROUND_HALF_UP：10.005 → 10.01 基准，涨停 11.01。"""
    assert limit_price(10.005, 0.10, "up") == pytest.approx(11.01)
    assert limit_price(10.005, 0.10, "down") == pytest.approx(9.01)


# ---------------------------------------------------------------------------
# 内部一致性：ref_adj vs ref_ret（合成，公式层对拍）
# ---------------------------------------------------------------------------

def test_p021_consistency_ref_formula():
    """除权参考价 = prev × adj[t-1]/adj[t]，half-up 到分。"""
    prev = np.array([[np.nan], [10.0], [11.0]])
    adj = np.array([[2.0], [2.0], [2.2]])       # t=2 除权（ratio=2/2.2）
    ref = _ref_from_adj(prev, adj)
    assert np.isnan(ref[0, 0])
    assert ref[1, 0] == pytest.approx(10.0)      # ratio=1 → 原昨收
    assert ref[2, 0] == pytest.approx(10.0)      # 11 × (2.0/2.2) = 10.00


# ---------------------------------------------------------------------------
# mock 限价表（Tushare 格式）扰动：需 loader（A4 落地后转绿）
# ---------------------------------------------------------------------------

def _mock_limit_csv(tmp_path, rows, name="stk_limit.csv"):
    path = tmp_path / name
    pd.DataFrame(rows, columns=["ts_code", "trade_date",
                                "up_limit", "down_limit"]).to_csv(
        path, index=False, encoding="utf-8")
    return str(path)


def _spec_with_limit(tmp_path, limit_path):
    from backtest.tradability_loader import TradabilitySpec
    return TradabilitySpec(data_root=str(tmp_path), stk_limit_path=limit_path)


def _write_panels(tmp_path, dates, codes, close_val=10.0):
    """写最小面板（close/high/low/open/volume/adj/suspend/name）。"""
    md = tmp_path / "market_data"
    md.mkdir(parents=True, exist_ok=True)
    idx = pd.DatetimeIndex(dates)
    close = pd.DataFrame(close_val, index=idx, columns=codes)
    panels = {
        "close": close,
        "high": close * 1.01,
        "low": close * 0.99,
        "open": close.copy(),
        "volume": pd.DataFrame(1e6, index=idx, columns=codes),
        "adj": pd.DataFrame(1.0, index=idx, columns=codes),
        "suspend": pd.DataFrame(np.nan, index=idx, columns=codes, dtype=object),
        "name": pd.DataFrame("普通", index=idx, columns=codes),
    }
    for key, frame in panels.items():
        frame.to_pickle(md / ("stock_%s.pkl" % key))


def test_p021_limit_table_pair_required(tmp_path):
    """E-6：limit_up/down 不成对 → ValueError（构建器与 apply 双入口）。"""
    dates = pd.date_range("2024-01-02", periods=3, freq="B")
    codes = ["600000.SH"]
    close = pd.DataFrame(10.0, index=dates, columns=codes)
    up = pd.DataFrame(11.0, index=dates, columns=codes)
    frame = dict(close=close, high=close * 1.001, low=close * 0.999,
                 open_=close.copy(),
                 volume=pd.DataFrame(1e6, index=dates, columns=codes),
                 suspend=pd.DataFrame(False, index=dates, columns=codes),
                 name=pd.DataFrame("普通", index=dates, columns=codes),
                 adj=pd.DataFrame(1.0, index=dates, columns=codes))
    from backtest.tradability_inputs import build_tradability_inputs
    with pytest.raises(ValueError):
        build_tradability_inputs(limit_up=up, **frame)

    from backtest.tradability import apply_tradability
    with pytest.raises(ValueError):
        apply_tradability(
            np.zeros((3, 1)), np.full((3, 1), 10.0), np.full((3, 1), 10.0),
            np.full((3, 1), 10.0), np.full((3, 1), 10.0),
            np.full((3, 1), 10.0), np.full((3, 1), 1e6),
            np.zeros((3, 1), dtype=bool), np.array(["main"]),
            np.zeros(1, dtype=bool),
            np.array(["2024-01-02", "2024-01-03", "2024-01-04"]),
            limit_up=up.to_numpy())


def test_p021_mock_stk_limit_perturb(tmp_path):
    """18 行 mock：18/18 命中；错价/缺行/多代码/重复键各 1/1 检出。"""
    from backtest.tradability_loader import load_stk_limit

    dates = pd.date_range("2024-01-02", periods=3, freq="B")
    codes = ["600000.SH", "000001.SZ", "600001.SH",
             "600002.SH", "600003.SH", "600004.SH"]
    rows = []
    for code in codes:
        for d in dates:
            rows.append((code, d.strftime("%Y%m%d"), 11.0, 9.0))
    path = _mock_limit_csv(tmp_path, rows)

    up, down, diag = load_stk_limit(path, dates, codes)
    assert np.isfinite(up).all() and np.isfinite(down).all()
    assert diag["limit_table_duplicate_rows"] == 0
    assert diag["limit_table_missing_cells"] == 0
    assert diag["limit_table_source"] == "stk_limit"

    # 重复键：同一 (code, date) 再插一行（keep=last 胜出）
    dup = rows + [("600000.SH", dates[0].strftime("%Y%m%d"), 12.0, 8.0)]
    up2, down2, diag2 = load_stk_limit(_mock_limit_csv(
        tmp_path, dup, "dup.csv"), dates, codes)
    assert diag2["limit_table_duplicate_rows"] == 1
    assert up2[0, 0] == pytest.approx(12.0)
    assert down2[0, 0] == pytest.approx(8.0)

    # 缺格：少一行 → 1 格（up/down 同缺），回退标记
    short = rows[:-1]
    up3, _, diag3 = load_stk_limit(_mock_limit_csv(
        tmp_path, short, "short.csv"), dates, codes)
    assert diag3["limit_table_missing_cells"] == 1
    assert diag3["limit_table_source"] == "stk_limit_partial"

    # 多代码：表含面板外代码 → 不报错、被对齐丢弃
    extra = rows + [("999999.SH", dates[0].strftime("%Y%m%d"), 5.0, 4.0)]
    _, _, diag4 = load_stk_limit(_mock_limit_csv(
        tmp_path, extra, "extra.csv"), dates, codes)
    assert diag4["limit_table_missing_cells"] == 0

    # 错价：up < down → ValueError
    bad = rows[:-1] + [("600000.SH", dates[-1].strftime("%Y%m%d"), 1.0, 2.0)]
    with pytest.raises(ValueError):
        load_stk_limit(_mock_limit_csv(tmp_path, bad, "bad.csv"),
                       dates, codes)


def test_p021_mock_stk_limit_end_to_end(tmp_path):
    """mock 18 行 → spec.build 逐格采用外部限价。"""
    dates = pd.date_range("2024-01-02", periods=3, freq="B")
    codes = ["600000.SH", "000001.SZ", "600001.SH"]
    _write_panels(tmp_path, dates, codes)
    rows = [(code, d.strftime("%Y%m%d"), 11.0, 9.0)
            for code in codes for d in dates]
    path = _mock_limit_csv(tmp_path, rows)
    inputs, meta = _spec_with_limit(tmp_path, path).build(dates, codes)
    assert inputs is not None
    assert inputs.limit_up is not None
    assert np.allclose(inputs.limit_up, 11.0)
    assert inputs.diagnostics["limit_table_source"] == "stk_limit"
