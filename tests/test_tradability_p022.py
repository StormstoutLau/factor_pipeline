# -*- coding: utf-8 -*-
"""P-022：紧凑缓存 / 零拷贝 / 逐位一致 / worker 载荷。"""
import hashlib
import json
import os

import numpy as np
import pandas as pd
import pytest

from backtest.engine import FactorBacktestEngine
from backtest.factor_metrics import compute_turnover
from backtest.parallel_runner import (ParallelFactorRunner, _run_worker,
                                      run_parallel)
from backtest.tradability import (TradabilityInputs, TradabilityPolicy,
                                  _pct_matrix, _pct_row,
                                  apply_tradability_with_diagnostics)
from backtest.tradability_inputs import _frame, build_tradability_inputs
from backtest.tradability_loader import (TradabilitySpec, _PANEL_CACHE,
                                         _PanelRecord)

DATES = pd.date_range("2024-01-02", periods=8, freq="B")
CODES = ["600000.SH", "000001.SZ", "300001.SZ", "600001.SH"]
POLICY = TradabilityPolicy(execute_at="next_open",
                           unknown_policy="fallback_raw", mode="full")
GOLDEN = os.path.join(os.path.dirname(__file__), "golden",
                      "p022_baseline.json")


class _FakeDL(object):
    def __init__(self, factor, close):
        self.n_dates, self.n_stocks = close.shape
        self.price_data = {"close": close}
        self.factor_data = {"f1": factor}


@pytest.fixture(autouse=True)
def _clear_panel_cache():
    _PANEL_CACHE.clear()
    yield
    _PANEL_CACHE.clear()


def _panels(T=8, N=4):
    close = pd.DataFrame(
        10.0 + np.arange(T)[:, None] * 0.1 + np.arange(N)[None, :],
        index=DATES[:T], columns=CODES[:N])
    ones = pd.DataFrame(1.0, index=DATES[:T], columns=CODES[:N])
    return {
        "close": close, "high": close * 1.01, "low": close * 0.99,
        "open_": close, "volume": ones * 1e6, "adj": ones,
        "suspend": pd.DataFrame(np.nan, index=DATES[:T], columns=CODES[:N],
                                dtype=object),
        "name": pd.DataFrame("普通", index=DATES[:T], columns=CODES[:N],
                             dtype=object),
    }


def _engine_block(inputs, close, factor=None):
    if factor is None:
        factor = np.linspace(-1, 1, close.size).reshape(close.shape)
    res = FactorBacktestEngine(
        _FakeDL(factor, close),
        config={"top_n": 0.5, "ic_method": "rank"},
        tradability_inputs=inputs).run()["f1"]
    blk = res["tradability"]
    return {
        "report": blk["report"], "meta": blk["meta"],
        "diagnostics": blk["diagnostics"],
        "turnover": [float(x) for x in np.asarray(res["turnover"])],
        "price_basis": blk["price_basis"], "leg_scope": blk["leg_scope"],
        "short_leg_unmodeled": blk["short_leg_unmodeled"],
        "turnover_basis": blk["turnover_basis"],
    }


def _fixtures():
    """与 tests/golden/p022_baseline.json 的 B0 抓取完全同构。"""
    out = {}
    p = _panels()
    inputs, _ = build_tradability_inputs(**p, policy=POLICY)
    out["F1_basic"] = _engine_block(inputs, p["close"].to_numpy(float))

    p = _panels()
    name = p["name"].copy()
    name.iloc[0, :] = np.nan
    name.iloc[1:3, 0] = "ST测试"
    name.iloc[1:, 1:] = "普通"
    p["name"] = name
    inputs, _ = build_tradability_inputs(**p, policy=POLICY)
    out["F2_st"] = _engine_block(inputs, p["close"].to_numpy(float))

    p = _panels()
    sus = p["suspend"].copy()
    sus.iloc[1, 0] = "S"
    sus.iloc[2, 1] = "R"
    sus.iloc[3, 2] = None
    sus.iloc[4, 3] = "S"
    p["suspend"] = sus
    inputs, _ = build_tradability_inputs(**p, policy=POLICY)
    out["F3_suspend"] = _engine_block(
        inputs, p["close"].to_numpy(float),
        np.tile(np.array([10.0, 5.0, 0.0, -5.0]), (8, 1)))

    T, N = 6, 3
    d4 = pd.date_range("2020-07-24", periods=T, freq="B")
    close = np.full((T, N), 10.0)
    close[:, 1] = 20.0
    close[:, 2] = 5.0
    ones = np.ones((T, N))
    up = close * 1.1
    down = close * 0.9
    up[1, 0] = np.nan
    down[1, 0] = np.nan
    open4 = close.copy()
    open4[1:, 1] = up[1:, 1]
    open4[2:, 0] = up[2:, 0]
    inputs = TradabilityInputs(
        close=close, high=close * 1.01, low=close * 0.99, open_=open4,
        volume=ones * 1e6, suspended=np.zeros((T, N), bool),
        dates=np.array([d.strftime("%Y-%m-%d") for d in d4]),
        board=np.array(["bse", "main", "unknown"]),
        is_st=np.zeros((T, N), bool), adj=ones,
        is_delisting=np.zeros((T, N), bool),
        no_limit=np.zeros((T, N), bool), policy=POLICY,
        meta={"price_basis": "raw_adj_ref", "board_counts": {"bse": 1}},
        ref=close.copy(), limit_up=up, limit_down=down,
        codes=np.array(CODES[:N]),
        diagnostics={"schema_version": 2,
                     "limit_table_source": "stk_limit_partial",
                     "limit_table_missing_cells": 1})
    out["F4_limit_bse"] = _engine_block(
        inputs, close, np.tile(np.array([5.0, 10.0, 0.0]), (T, 1)))
    return out


def _write_root(tmp_path, T=6):
    md = tmp_path / "market_data"
    md.mkdir(parents=True, exist_ok=True)
    dates = pd.date_range("2024-01-02", periods=T, freq="B")
    codes = ["600000.SH", "000001.SZ", "300001.SZ"]
    close = pd.DataFrame(10.0, index=dates, columns=codes)
    close.to_pickle(md / "stock_close.pkl")
    (close * 1.001).to_pickle(md / "stock_high.pkl")
    (close * 0.999).to_pickle(md / "stock_low.pkl")
    close.to_pickle(md / "stock_open.pkl")
    pd.DataFrame(1e6, index=dates, columns=codes).to_pickle(
        md / "stock_volume.pkl")
    pd.DataFrame("N", index=dates, columns=codes,
                 dtype=object).to_pickle(md / "stock_suspend.pkl")
    pd.DataFrame("普通", index=dates, columns=codes,
                 dtype=object).to_pickle(md / "stock_name.pkl")
    pd.DataFrame(1.0, index=dates, columns=codes).to_pickle(md / "stock_adj.pkl")
    return dates, codes


# ── 紧凑缓存 / 零拷贝 ──────────────────────────────────────────────


def test_p022_cache_compact(tmp_path):
    dates, codes = _write_root(tmp_path)
    spec = TradabilitySpec(data_root=str(tmp_path))
    spec.build(dates, codes)
    key = lambda n: (str(tmp_path), "market_data", n)
    name = _PANEL_CACHE[key("name")]
    sus = _PANEL_CACHE[key("suspend")]
    assert name.kind == "name" and name.data.dtype == np.float32
    assert sus.kind == "suspend" and sus.data[0].dtype == bool
    assert sus.data[1].dtype == bool


def test_p022_slice_identity():
    close = _panels()["close"]
    rec = TradabilitySpec._compact_panel("close", close)
    data, _ = TradabilitySpec._slice(rec, close.index, list(close.columns))
    assert data is rec.data

    name_rec = TradabilitySpec._compact_panel("name", _panels()["name"])
    data, aux = TradabilitySpec._slice(name_rec, name_rec.index,
                                       list(name_rec.columns))
    assert np.shares_memory(data.to_numpy(), name_rec.data)

    sus_rec = TradabilitySpec._compact_panel("suspend", _panels()["suspend"])
    (mask, missing), _ = TradabilitySpec._slice(
        sus_rec, sus_rec.index, list(sus_rec.columns))
    assert mask is sus_rec.data[0] and missing is sus_rec.data[1]


def test_p022_slice_contract():
    name_rec = TradabilitySpec._compact_panel("name", _panels()["name"])
    idx = DATES[:4]
    cols = CODES[:2] + ["999999.SH"]
    data, _ = TradabilitySpec._slice(name_rec, idx, cols)
    assert np.isnan(data.loc[:, "999999.SH"]).all()
    sus_rec = TradabilitySpec._compact_panel("suspend", _panels()["suspend"])
    (mask, missing), _ = TradabilitySpec._slice(sus_rec, idx, cols)
    assert not mask[:, -1].any() and missing[:, -1].all()


def test_p022_name_codes_equiv():
    p = _panels()
    name = p["name"].copy()
    name.iloc[0, :] = np.nan
    name.iloc[1:3, 0] = "ST测试"
    name.iloc[3:, 0] = "退市"
    p["name"] = name
    obj_inputs, _ = build_tradability_inputs(**p, policy=POLICY)

    rec = TradabilitySpec._compact_panel("name", name)
    codes_df, aux = TradabilitySpec._slice(rec, name.index, list(name.columns))
    p2 = dict(p)
    p2["name"] = None
    cmp_inputs, _ = build_tradability_inputs(
        **p2, policy=POLICY, name_codes=codes_df,
        name_st_lut=aux[1], name_del_lut=aux[2])
    np.testing.assert_array_equal(obj_inputs.is_st, cmp_inputs.is_st)
    np.testing.assert_array_equal(obj_inputs.is_delisting,
                                  cmp_inputs.is_delisting)
    assert (obj_inputs.diagnostics["name_missing_cells"]
            == cmp_inputs.diagnostics["name_missing_cells"])


def test_p022_name_window_carry():
    p = _panels()
    name = p["name"].copy()
    name.iloc[0:2, 0] = "ST测试"
    name.iloc[2:, 0] = "普通"
    idx = DATES[2:6]
    obj, _ = build_tradability_inputs(
        close=p["close"].loc[idx], high=p["high"].loc[idx],
        low=p["low"].loc[idx], open_=p["open_"].loc[idx],
        volume=p["volume"].loc[idx], suspend=p["suspend"].loc[idx],
        name=name.loc[idx], adj=p["adj"].loc[idx], policy=POLICY)
    rec = TradabilitySpec._compact_panel("name", name)
    codes_df, aux = TradabilitySpec._slice(rec, idx, list(name.columns))
    cmp_, _ = build_tradability_inputs(
        close=p["close"].loc[idx], high=p["high"].loc[idx],
        low=p["low"].loc[idx], open_=p["open_"].loc[idx],
        volume=p["volume"].loc[idx], suspend=p["suspend"].loc[idx],
        name=None, adj=p["adj"].loc[idx], policy=POLICY,
        name_codes=codes_df, name_st_lut=aux[1], name_del_lut=aux[2])
    np.testing.assert_array_equal(obj.is_st, cmp_.is_st)
    assert not cmp_.is_st[0].any()          # 窗口首日不继承窗口外 ST


def test_p022_suspend_state_equiv():
    p = _panels()
    sus = p["suspend"].copy()
    sus.iloc[1, 0] = "S"
    sus.iloc[2, 1] = "R"
    p["suspend"] = sus
    obj, _ = build_tradability_inputs(**p, policy=POLICY)

    rec = TradabilitySpec._compact_panel("suspend", sus)
    (mask, missing), _ = TradabilitySpec._slice(
        rec, sus.index, list(sus.columns))
    p2 = dict(p)
    p2["suspend"] = None
    cmp_, _ = build_tradability_inputs(
        **p2, policy=POLICY, suspend_mask=mask, suspend_missing=missing)
    np.testing.assert_array_equal(obj.suspended, cmp_.suspended)
    assert (obj.diagnostics["suspend_missing_cells"]
            == cmp_.diagnostics["suspend_missing_cells"])


def test_p022_suspend_bool_path_unchanged():
    frame = pd.DataFrame(False, index=DATES[:3], columns=CODES[:1])
    frame.iloc[1, 0] = True
    rec = TradabilitySpec._compact_panel("suspend", frame)
    assert rec.kind == "raw"


def test_p022_name_unique_fallback(monkeypatch):
    """E-5：唯一值 >2^24 → 回退 raw（不构建 LUT）。"""
    frame = _panels()["name"]
    monkeypatch.setattr(
        pd, "factorize",
        lambda *a, **k: (np.zeros(frame.size, dtype=np.int64),
                         range(2 ** 24 + 1)))
    rec = TradabilitySpec._compact_panel("name", frame)
    assert rec.kind == "raw"


def test_p022_frame_no_copy():
    p = _panels()
    inputs, _ = build_tradability_inputs(**p, policy=POLICY)
    assert np.shares_memory(inputs.close, p["close"].to_numpy(float))
    assert np.shares_memory(inputs.high, p["high"].to_numpy(float))


def test_p022_frame_fastpath_negative():
    close = _panels()["close"]
    assert _frame(close, close.index, close.columns, 0.0, float) is not close
    as_int = close.astype(int)
    assert _frame(as_int, as_int.index, as_int.columns,
                  np.nan, float) is not as_int


def test_p022_inputs_immutable(tmp_path):
    dates, codes = _write_root(tmp_path)
    spec = TradabilitySpec(data_root=str(tmp_path))
    spec.build(dates, codes)
    key = (str(tmp_path), "market_data", "name")
    before = hashlib.sha256(_PANEL_CACHE[key].data.tobytes()).hexdigest()
    spec.build(dates, codes)
    after = hashlib.sha256(_PANEL_CACHE[key].data.tobytes()).hexdigest()
    assert before == after


# ── 逐位一致 ──────────────────────────────────────────────────────


def test_p022_report_meta_bitwise():
    with open(GOLDEN, "r", encoding="utf-8") as fh:
        golden = json.load(fh)
    got = _fixtures()
    assert set(got) == set(golden)
    for key in golden:
        assert json.dumps(got[key], sort_keys=True) == json.dumps(
            golden[key], sort_keys=True), key


def test_p022_turnover_bitwise():
    rng = np.random.RandomState(7)
    for dtype in (np.float64, np.float32):
        pos = rng.randn(9, 5).astype(dtype) * 0.1
        pos[2, 3] = np.nan
        pos[5, 1] = np.inf
        old = 0.5 * np.sum(np.abs(np.diff(pos, axis=0)), axis=1)
        new = compute_turnover(pos)
        assert new.dtype == old.dtype
        np.testing.assert_array_equal(new, old)
    assert compute_turnover(np.zeros((1, 3))).size == 0
    one = rng.randn(4, 1)
    np.testing.assert_array_equal(
        compute_turnover(one),
        0.5 * np.sum(np.abs(np.diff(one, axis=0)), axis=1))


def test_p022_turnover_int_input():
    """非浮点入参：逐位对齐旧实现（0.5*sum 升为 float64）。"""
    pos = np.array([[1, 2], [2, 3], [0, 5]], dtype=np.int64)
    old = 0.5 * np.sum(np.abs(np.diff(pos, axis=0)), axis=1)
    new = compute_turnover(pos)
    assert old.dtype == np.float64
    assert new.dtype == np.float64
    np.testing.assert_array_equal(new, old)


def test_p022_pct_row_bitwise():
    rng = np.random.RandomState(11)
    T, N = 6, 7
    boards = np.array(["main", "gem", "star", "bse", "unknown", "main",
                       "gem"])
    st = rng.rand(T, N) > 0.7
    dl = rng.rand(T, N) > 0.92
    dates = [d.strftime("%Y-%m-%d") for d in
             pd.date_range("2020-07-24", periods=T, freq="B")]
    pct, gaps = _pct_matrix(boards, st, dl, dates, return_gaps=True)
    from backtest.tradability import _BOARD_CODES
    codes = np.array([_BOARD_CODES.get(str(b), -1) for b in boards],
                     dtype=int)
    pct2 = np.empty_like(pct)
    gaps2 = np.empty_like(gaps)
    for t in range(T):
        pct2[t], gaps2[t] = _pct_row(codes, st[t], dl[t], dates[t])
    np.testing.assert_array_equal(pct, pct2)
    np.testing.assert_array_equal(gaps, gaps2)


def test_p022_pct_row_independent():
    """旧口径逐格复核：rule_pct_or_nan(board, st&~del, date)。"""
    from backtest.tradability import rule_pct_or_nan
    rng = np.random.RandomState(13)
    T, N = 5, 6
    boards = np.array(["main", "gem", "star", "bse", "unknown", "main"])
    st = rng.rand(T, N) > 0.6
    dl = rng.rand(T, N) > 0.85
    dates = [d.strftime("%Y-%m-%d") for d in
             pd.date_range("2020-07-24", periods=T, freq="B")]
    pct, gaps = _pct_matrix(boards, st, dl, dates, return_gaps=True)
    exp_pct = np.full((T, N), np.nan)
    exp_gaps = np.zeros((T, N), bool)
    for t in range(T):
        for n in range(N):
            board = str(boards[n])
            if board not in ("main", "star", "gem", "bse"):
                exp_gaps[t, n] = True
                continue
            value = rule_pct_or_nan(
                board, bool(st[t, n] and not dl[t, n]), dates[t])
            if np.isfinite(value):
                exp_pct[t, n] = value
            else:
                exp_gaps[t, n] = True
    np.testing.assert_array_equal(pct, exp_pct)
    np.testing.assert_array_equal(gaps, exp_gaps)


def test_p022_pct_limit_table_branch(monkeypatch):
    import backtest.tradability as tr
    T, N = 3, 2
    base = np.full((T, N), 10.0)
    up = np.full((T, N), 11.0)
    down = np.full((T, N), 9.0)
    monkeypatch.setattr(tr, "_pct_row", lambda *a, **k: pytest.fail("pct 不应计算"))
    eff, rep, diag = apply_tradability_with_diagnostics(
        np.full((T, N), 0.5), base, base * 1.01, base * 0.99, base, base,
        np.ones((T, N)), np.zeros((T, N), bool), np.array(["main"] * N),
        np.zeros((T, N), bool), np.array(
            [d.strftime("%Y-%m-%d") for d in DATES[:T]]),
        policy=POLICY, ref=base, limit_up=up, limit_down=down)
    assert eff.shape == (T, N)
    assert diag["limit_table_source"] == "stk_limit"


# ── 载荷 / 接口 / 错误 ────────────────────────────────────────────


def test_p022_parallel_payload_subset(monkeypatch):
    runner = ParallelFactorRunner(n_workers=2)
    captured = {}

    def _fake(args_list, n_workers):
        captured["args"] = args_list
        return {}

    monkeypatch.setattr(runner, "_run_with_processes", _fake)
    factors = {n: pd.DataFrame(np.zeros((3, 4))) for n in ("a", "b", "c")}
    price = pd.DataFrame(np.ones((3, 4)))
    runner._run_group(["a", "b", "c"], factors, price, None, {})
    keys = [set(a[0]) for a in captured["args"]]
    assert keys == [{"a", "b"}, {"c"}]
    assert all(a[0] is not factors for a in captured["args"])


def _parallel_inputs():
    rng = np.random.RandomState(17)
    dates = pd.date_range("2024-01-02", periods=12, freq="B")
    codes = ["600000.SH", "000001.SZ", "300001.SZ", "600001.SH"]
    price = pd.DataFrame(100.0 + rng.rand(len(codes), len(dates)),
                         index=codes, columns=dates)
    factors = {name: pd.DataFrame(rng.randn(len(codes), len(dates)),
                                  index=codes, columns=dates)
               for name in ("pa", "pb")}
    return factors, price


class _DLStub(object):
    """最小 DataLoader 替身：面板转置为 (T, N)，供 `_run_worker` 使用。"""

    def __init__(self, factors, price):
        self.n_dates = price.shape[1]
        self.n_stocks = price.shape[0]
        self.price_data = {"close": price.to_numpy(float).T}
        self.factor_data = {k: v.to_numpy(float).T
                            for k, v in factors.items()}


class _BridgeStub(object):
    @staticmethod
    def create_dataloader(factors, price):
        return _DLStub(factors, price)


def test_p022_worker_payload_summary_equal(monkeypatch):
    """D3：worker 只拿本 chunk 因子，summary 与全量载荷逐位相等。"""
    import factor_pipeline.backtest.data_bridge as dbmod
    monkeypatch.setattr(dbmod, "DataBridge", _BridgeStub)
    factors, price = _parallel_inputs()
    runner = ParallelFactorRunner(n_workers=1)
    fwd = runner._compute_fwd_for_group("pa", factors, price)
    full = _run_worker((list(factors), factors, price, fwd, None, None))
    sub = _run_worker((["pa"], {"pa": factors["pa"]}, price, fwd, None,
                       None))
    assert set(sub) == {"pa"}
    assert json.dumps(sub["pa"], sort_keys=True) == json.dumps(
        full["pa"], sort_keys=True)


def test_p022_parallel_serial_equal():
    """串行（单因子 `_run_worker`）vs 进程池（`run_parallel`）summary 逐位。"""
    pytest.importorskip("Factor_Trading_v3_0")   # 同 test_p0_parallel 惯例
    factors, price = _parallel_inputs()
    serial = {fn: _run_worker(([fn], {fn: factors[fn]}, price, None, None,
                               None))[fn] for fn in factors}
    parallel = run_parallel(factors, price, n_workers=1)
    assert set(parallel) == set(serial)
    for fn in serial:
        assert json.dumps(serial[fn], sort_keys=True) == json.dumps(
            parallel[fn], sort_keys=True), fn


def test_p022_builder_legacy_positional():
    p = _panels()
    kwargs_inputs, _ = build_tradability_inputs(**p, policy=POLICY)
    args = [p["close"], p["high"], p["low"], p["open_"], p["volume"],
            p["suspend"], p["name"], p["adj"], None, POLICY, None, None,
            None, None]
    pos_inputs, _ = build_tradability_inputs(*args)
    np.testing.assert_array_equal(kwargs_inputs.is_st, pos_inputs.is_st)
    np.testing.assert_array_equal(kwargs_inputs.close, pos_inputs.close)


def test_p022_builder_errors():
    p = _panels()
    codes_df = pd.DataFrame(0.0, index=DATES[:2], columns=CODES[:4])
    with pytest.raises(ValueError):
        build_tradability_inputs(**p, policy=POLICY, name_codes=codes_df,
                                 name_st_lut=np.zeros(1, bool),
                                 name_del_lut=np.zeros(1, bool))
    with pytest.raises(ValueError):
        build_tradability_inputs(**p, policy=POLICY, suspend_mask=np.zeros(
            (8, 4), bool))
    with pytest.raises(ValueError):
        _PanelRecord("bad", DATES, CODES, None)
    bad = pd.DataFrame(5.0, index=DATES, columns=CODES)
    with pytest.raises(ValueError):
        build_tradability_inputs(**p, policy=POLICY, name_codes=bad,
                                 name_st_lut=np.zeros(1, bool),
                                 name_del_lut=np.zeros(1, bool))
    with pytest.raises(ValueError):      # LUT 非一维
        build_tradability_inputs(**p, policy=POLICY, name_codes=bad,
                                 name_st_lut=np.zeros((1, 1), bool),
                                 name_del_lut=np.zeros(1, bool))
    with pytest.raises(ValueError):      # suspend_missing 无 mask
        build_tradability_inputs(**p, policy=POLICY,
                                 suspend_missing=np.zeros((8, 4), bool))


def test_p022_missing_fields_compact(tmp_path):
    dates, codes = _write_root(tmp_path)
    spec = TradabilitySpec(data_root=str(tmp_path))
    inputs, _ = spec.build(dates, codes)
    assert inputs is not None
    fields = inputs.diagnostics["missing_fields"]
    assert "name" not in fields
    assert "suspend" not in fields


def test_p022_script_schema(tmp_path):
    import importlib.util
    dates, codes = _write_root(tmp_path)
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        "scripts", "verify_tradability_closeout.py")
    spec = importlib.util.spec_from_file_location("p022_closeout", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    report = mod.build_report(str(tmp_path), only=["u7", "u8"])
    assert set(report) == {"u7", "u8"}
    assert set(report["u7"]) == {"months", "worst", "below_099", "modes"}
    assert report["u7"]["below_099"] == {"high_low": [], "open": [],
                                          "prev": []}
    assert report["u8"]["cells_total"] == len(dates) * len(codes)
    assert report["u8"]["mismatch_cells"] == 0
