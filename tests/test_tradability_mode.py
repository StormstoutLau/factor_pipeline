# -*- coding: utf-8 -*-
"""P-021 A3/A4：D6 模式解析（auto/full/execution_only_open/off）。"""
import logging

import numpy as np
import pandas as pd
import pytest

from backtest.tradability_loader import TradabilitySpec


def _write(tmp_path, with_high_low=True, with_open=True, with_adj=True, n=3):
    md = tmp_path / "market_data"
    md.mkdir(parents=True, exist_ok=True)
    dates = pd.date_range("2024-01-02", periods=n, freq="B")
    codes = ["600000.SH", "000001.SZ"]
    close = pd.DataFrame(10.0, index=dates, columns=codes)
    close.to_pickle(md / "stock_close.pkl")
    if with_high_low:
        (close * 1.001).to_pickle(md / "stock_high.pkl")
        (close * 0.999).to_pickle(md / "stock_low.pkl")
    if with_open:
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


def test_p021_mode_auto_full(tmp_path):
    """auto + 全量数据 → full；mode_requested=auto。"""
    dates, codes = _write(tmp_path)
    inputs, meta = TradabilitySpec(data_root=str(tmp_path)).build(dates, codes)
    assert inputs is not None
    diag = inputs.diagnostics
    assert diag["mode"] == "full"
    assert diag["mode_requested"] == "auto"
    assert diag["degrade_reason"] is None
    assert diag["one_word_disabled"] is False


def test_p021_mode_degrade(tmp_path):
    """full + 缺 high/low → execution_only_open + degrade_reason。"""
    dates, codes = _write(tmp_path, with_high_low=False)
    spec = TradabilitySpec(data_root=str(tmp_path), mode="full")
    inputs, meta = spec.build(dates, codes)
    assert inputs is not None
    diag = inputs.diagnostics
    assert diag["mode"] == "execution_only_open"
    assert diag["mode_requested"] == "full"
    assert diag["degrade_reason"] == "high_low_or_adj_insufficient"
    assert diag["one_word_disabled"] is True
    assert meta["one_word_up_cells"] == 0
    assert meta["one_word_down_cells"] == 0


def test_p021_mode_auto_degrade(tmp_path):
    """auto + 缺 high/low → execution_only_open。"""
    dates, codes = _write(tmp_path, with_high_low=False)
    inputs, _ = TradabilitySpec(data_root=str(tmp_path)).build(dates, codes)
    assert inputs.diagnostics["mode"] == "execution_only_open"


def test_p021_mode_explicit_execution_only(tmp_path):
    """请求 execution_only_open：直接采用，degrade_reason=None。"""
    dates, codes = _write(tmp_path)
    spec = TradabilitySpec(data_root=str(tmp_path),
                           mode="execution_only_open")
    inputs, _ = spec.build(dates, codes)
    assert inputs.diagnostics["mode"] == "execution_only_open"
    assert inputs.diagnostics["mode_requested"] == "execution_only_open"
    assert inputs.diagnostics["degrade_reason"] is None


def test_p021_mode_off_requested(tmp_path, caplog):
    """请求 off：返回 None + warning（不挂块）。"""
    dates, codes = _write(tmp_path)
    spec = TradabilitySpec(data_root=str(tmp_path), mode="off")
    with caplog.at_level(logging.WARNING):
        inputs, meta = spec.build(dates, codes)
    assert inputs is None
    assert meta["mode"] == "off"
    assert meta["mode_requested"] == "off"
    assert "TradabilitySpec 关闭" in caplog.text


def test_p021_mode_off_open_missing(tmp_path, caplog):
    """缺 open → open 覆盖 0 → off + degrade_reason。"""
    dates, codes = _write(tmp_path, with_open=False)
    spec = TradabilitySpec(data_root=str(tmp_path), mode="auto")
    with caplog.at_level(logging.WARNING):
        inputs, meta = spec.build(dates, codes)
    assert inputs is None
    assert meta["degrade_reason"] == "open_or_prev_unavailable"
    assert "open_or_prev_unavailable" in caplog.text


def test_p021_mode_t1_off(tmp_path, caplog):
    """T=1：prev 覆盖 0.0 → off（分母排除 t=0 边界）。"""
    dates, codes = _write(tmp_path, n=1)
    with caplog.at_level(logging.WARNING):
        inputs, meta = TradabilitySpec(data_root=str(tmp_path)).build(
            dates, codes)
    assert inputs is None
    assert meta["mode"] == "off"


def test_p021_mode_invalid(tmp_path):
    dates, codes = _write(tmp_path)
    with pytest.raises(ValueError):
        TradabilitySpec(data_root=str(tmp_path), mode="bogus").build(
            dates, codes)


def test_p021_loader_missing_close(tmp_path):
    """缺 close 面板 → ValueError（fail-closed）。"""
    dates = pd.date_range("2024-01-02", periods=3, freq="B")
    with pytest.raises(ValueError):
        TradabilitySpec(data_root=str(tmp_path)).build(dates, ["600000.SH"])


def test_p021_loader_codes_not_found(tmp_path):
    """请求代码全不在面板 → ValueError；部分缺失 → codes_not_found。"""
    dates, codes = _write(tmp_path)
    spec = TradabilitySpec(data_root=str(tmp_path))
    with pytest.raises(ValueError):
        spec.build(dates, ["999999.SH"])
    inputs, _ = spec.build(dates, codes + ["999999.SH"])
    assert inputs is not None
    assert "999999.SH" in inputs.diagnostics["codes_not_found"]
