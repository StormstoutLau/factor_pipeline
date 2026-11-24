# -*- coding: utf-8 -*-
"""P-023：离线 name npz / 分块 plan / 分块 apply / 流式引擎逐位。"""
import hashlib
import importlib.util
import os

import numpy as np
import pandas as pd
import pytest

import backtest.tradability_loader as L
from backtest.engine import FactorBacktestEngine
from backtest.factor_metrics import compute_turnover
from backtest.parallel_runner import _run_worker
from backtest.tradability import (TradabilityApplyState, TradabilityPolicy,
                                  apply_tradability_with_diagnostics)
from backtest.tradability_inputs import build_tradability_inputs
from backtest.tradability_loader import (NAME_COMPACT_KEYS, TradabilitySpec,
                                         _PANEL_CACHE, load_name_compact,
                                         write_name_compact)

DATES = pd.date_range("2024-01-02", periods=9, freq="B")
CODES = ["600000.SH", "000001.SZ", "300001.SZ", "600001.SH"]
POLICY = TradabilityPolicy(execute_at="next_open",
                           unknown_policy="fallback_raw", mode="full")


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


def _panels(T=9, N=4):
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


def _write_root(tmp_path, panels=None, list_date=None, with_adj=True,
                T=9, N=4):
    md = tmp_path / "market_data"
    md.mkdir(parents=True, exist_ok=True)
    p = _panels(T, N) if panels is None else panels
    p["close"].to_pickle(md / "stock_close.pkl")
    p["high"].to_pickle(md / "stock_high.pkl")
    p["low"].to_pickle(md / "stock_low.pkl")
    p["open_"].to_pickle(md / "stock_open.pkl")
    p["volume"].to_pickle(md / "stock_volume.pkl")
    p["suspend"].to_pickle(md / "stock_suspend.pkl")
    p["name"].to_pickle(md / "stock_name.pkl")
    if with_adj:
        p["adj"].to_pickle(md / "stock_adj.pkl")
    if list_date is not None:
        pd.DataFrame([list_date], columns=list(p["close"].columns)) \
            .to_pickle(md / "stock_list_date.pkl")
    return tmp_path


def _spec(root, chunk_days=3, mode="auto", **kwargs):
    return TradabilitySpec(data_root=str(root), max_dates_per_chunk=chunk_days,
                           mode=mode, **kwargs)


def _factor(close):
    return np.linspace(-1, 1, close.size).reshape(close.shape)


def _block(result):
    blk = result["tradability"]
    return {
        "report": dict(blk["report"]),
        "meta": dict(blk["meta"]),
        "diagnostics": dict(blk["diagnostics"]),
        "turnover": np.asarray(result["turnover"]),
        "rank_ic_series": np.asarray(result["rank_ic_series"]),
        "pearson_ic_series": np.asarray(result["pearson_ic_series"]),
        "long_short_returns": np.asarray(result["long_short_returns"]),
        "spread": float(result["spread"]),
        "hit_rate": float(result["hit_rate"]),
    }


def _run_whole(root, chunk_days=3, **spec_kwargs):
    spec = _spec(root, chunk_days, **spec_kwargs)
    close = pd.read_pickle(os.path.join(str(root), "market_data",
                                        "stock_close.pkl"))
    close_a = close.to_numpy(dtype=float)
    inputs, meta = spec.build(close.index, close.columns)
    assert inputs is not None
    engine = FactorBacktestEngine(
        _FakeDL(_factor(close_a), close_a),
        config={"top_n": 0.5}, tradability_inputs=inputs)
    return _block(engine.run()["f1"]), inputs


def _run_stream(root, chunk_days=3, **spec_kwargs):
    spec = _spec(root, chunk_days, **spec_kwargs)
    close = pd.read_pickle(os.path.join(str(root), "market_data",
                                        "stock_close.pkl"))
    close_a = close.to_numpy(dtype=float)
    plan = spec.build_plan(close.index, close.columns)
    engine = FactorBacktestEngine(
        _FakeDL(_factor(close_a), close_a),
        config={"top_n": 0.5}, tradability_plan=plan)
    return _block(engine.run()["f1"]), plan


def _assert_equal(a, b, tol=0.0, path="root"):
    if isinstance(a, dict):
        assert isinstance(b, dict), path
        assert set(a) == set(b), "%s keys %r != %r" % (path, set(a), set(b))
        for k in a:
            _assert_equal(a[k], b[k], tol, "%s.%s" % (path, k))
        return
    if isinstance(a, (list, tuple)):
        assert len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b)):
            _assert_equal(x, y, tol, "%s[%d]" % (path, i))
        return
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        a = np.asarray(a)
        b = np.asarray(b)
        assert a.shape == b.shape, "%s shape %r != %r" % (path, a.shape,
                                                          b.shape)
        if a.dtype.kind in "USO" or b.dtype.kind in "USO":
            assert np.array_equal(a, b), "%s array mismatch" % path
            return
        a = a.astype(float)
        b = b.astype(float)
        if tol == 0.0:
            assert np.array_equal(a, b, equal_nan=True), \
                "%s array mismatch" % path
        else:
            assert np.allclose(a, b, rtol=0, atol=tol, equal_nan=True), \
                "%s array mismatch" % path
        return
    assert a == b, "%s: %r != %r" % (path, a, b)


def _fixtures(tmp_path):
    """4 组 fixture：basic / ST / suspend / 退市+IPO。"""
    out = {}

    p = _panels()
    out["F1_basic"] = _write_root(tmp_path / "f1", p)

    p = _panels()
    name = p["name"].copy()
    name.iloc[0, :] = np.nan
    name.iloc[1:3, 0] = "ST测试"
    name.iloc[4, 2] = "ST另一"
    p["name"] = name
    out["F2_st"] = _write_root(tmp_path / "f2", p)

    p = _panels()
    sus = p["suspend"].copy()
    sus.iloc[1, 0] = "S"
    sus.iloc[2, 1] = "R"
    sus.iloc[3, 2] = None
    sus.iloc[4, 3] = "S"
    p["suspend"] = sus
    out["F3_suspend"] = _write_root(tmp_path / "f3", p)

    p = _panels()
    name = p["name"].copy()
    name.iloc[0, 1:] = np.nan
    name.iloc[6:, 3] = "退市"
    p["name"] = name
    ld = ["2024-01-04", "2024-01-03", "2024-01-02", "2024-01-02"]
    out["F4_delist_ipo"] = _write_root(tmp_path / "f4", p, list_date=ld)
    return out


# ── npz 格式 / 回退 / 迁移 ─────────────────────────────────────────


def test_p023_npz_roundtrip(tmp_path):
    p = _panels()
    root = _write_root(tmp_path, p)
    src = os.path.join(str(root), "market_data", "stock_name.pkl")
    dst = os.path.join(str(root), "market_data", "stock_name_compact.npz")
    stats = write_name_compact(dst, p["name"], src)
    assert stats["uniques"] == 1
    rec = load_name_compact(dst, src)
    assert rec is not None
    assert rec.kind == "name"
    assert rec.index.equals(p["name"].index)
    assert rec.columns.equals(p["name"].columns)
    with np.load(dst, allow_pickle=False) as z:
        assert set(NAME_COMPACT_KEYS).issubset(set(z.files))
        assert z["codes"].dtype == np.float32
        assert z["format_version"] == L.NAME_COMPACT_FORMAT_VERSION


def _name_semantics(root):
    spec = _spec(root, chunk_days=9)
    close = pd.read_pickle(os.path.join(str(root), "market_data",
                                        "stock_close.pkl"))
    inputs, meta = spec.build(close.index, close.columns)
    return {
        "is_st": np.asarray(inputs.is_st),
        "is_delisting": np.asarray(inputs.is_delisting),
        "name_missing_cells": meta["name_missing_cells"]
        if "name_missing_cells" in meta else None,
        "diag": dict(inputs.diagnostics),
    }


def test_p023_npz_loader_equiv(tmp_path):
    p = _panels()
    name = p["name"].copy()
    name.iloc[0, :] = np.nan
    name.iloc[1:4, 0] = "ST测试"
    name.iloc[5:, 3] = "退市"
    p["name"] = name
    root = _write_root(tmp_path, p)
    _PANEL_CACHE.clear()
    base = _name_semantics(root)
    md = os.path.join(str(root), "market_data")
    write_name_compact(os.path.join(md, "stock_name_compact.npz"), name,
                       os.path.join(md, "stock_name.pkl"))
    _PANEL_CACHE.clear()
    compact = _name_semantics(root)
    assert np.array_equal(base["is_st"], compact["is_st"])
    assert np.array_equal(base["is_delisting"], compact["is_delisting"])
    assert base["diag"] == compact["diag"]


def test_p023_npz_fallback(tmp_path, caplog):
    name = pd.DataFrame("普通", index=DATES[:6], columns=CODES,
                        dtype=object)
    p = _panels(6, 4)
    p["name"] = name
    root = _write_root(tmp_path, p, T=6)
    md = os.path.join(str(root), "market_data")
    src = os.path.join(md, "stock_name.pkl")
    dst = os.path.join(md, "stock_name_compact.npz")

    # 缺失 → 直接 pkl（不告警）
    _PANEL_CACHE.clear()
    baseline = _name_semantics(root)

    # 损坏
    with open(dst, "wb") as fh:
        fh.write(b"not a zip")
    assert load_name_compact(dst, src) is None
    _PANEL_CACHE.clear()
    assert np.array_equal(baseline["is_st"],
                          _name_semantics(root)["is_st"])
    assert "name_compact_fallback" in caplog.text

    # 版本不符
    write_name_compact(dst, name, src)
    payload = dict(np.load(dst, allow_pickle=False))
    payload["format_version"] = np.asarray(999, dtype=np.int32)
    np.savez(dst, **payload)
    assert load_name_compact(dst, src) is None
    _PANEL_CACHE.clear()
    assert np.array_equal(baseline["is_delisting"],
                          _name_semantics(root)["is_delisting"])

    # mtime 过期
    write_name_compact(dst, name, src)
    st = os.stat(src)
    os.utime(src, (st.st_atime, st.st_mtime + 10))
    assert load_name_compact(dst, src) is None
    _PANEL_CACHE.clear()
    assert np.array_equal(baseline["is_st"], _name_semantics(root)["is_st"])


def test_p023_migrate_idempotent(tmp_path):
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        "scripts", "build_name_compact_cache.py")
    spec = importlib.util.spec_from_file_location("p023_migrate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    root = _write_root(tmp_path, _panels())
    pkl = os.path.join(str(root), "market_data", "stock_name.pkl")
    before = hashlib.sha256(open(pkl, "rb").read()).hexdigest()
    first = mod.migrate(str(root))
    assert first["status"] == "written"
    second = mod.migrate(str(root))
    assert second["status"] == "up-to-date"
    assert hashlib.sha256(open(pkl, "rb").read()).hexdigest() == before


def test_p023_migrate_dry_run(tmp_path):
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        "scripts", "build_name_compact_cache.py")
    spec = importlib.util.spec_from_file_location("p023_migrate2", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    root = _write_root(tmp_path, _panels())
    out = mod.migrate(str(root), dry_run=True)
    assert out["status"] == "dry-run"
    assert not os.path.exists(os.path.join(str(root), "market_data",
                                           "stock_name_compact.npz"))
    assert mod.main(["--data-root", os.path.join(str(tmp_path), "nope")]) == 2


def test_p023_npz_atomic(tmp_path, monkeypatch):
    p = _panels()
    root = _write_root(tmp_path, p)
    md = os.path.join(str(root), "market_data")
    src = os.path.join(md, "stock_name.pkl")
    dst = os.path.join(md, "stock_name_compact.npz")

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(L.np, "savez", boom)
    with pytest.raises(OSError):
        write_name_compact(dst, p["name"], src)
    assert not os.path.exists(dst)
    assert not [f for f in os.listdir(md) if ".tmp-" in f]


# ── plan / chunk ──────────────────────────────────────────────────


def _plan_all(root, chunk_days):
    spec = _spec(root, chunk_days)
    close = pd.read_pickle(os.path.join(str(root), "market_data",
                                        "stock_close.pkl"))
    plan = spec.build_plan(close.index, close.columns)
    results = []
    for chunk in plan.iter_chunks():
        results.append((chunk, plan.build_chunk(chunk)))
    plan.finalize()
    assert plan.mode == "full"
    return plan, results


def _compare_inputs(whole, chunk_inputs, sl, path):
    for field in ("close", "high", "low", "open_", "suspended", "is_st",
                  "adj", "is_delisting", "no_limit", "ref"):
        _assert_equal(np.asarray(getattr(whole, field))[sl],
                      np.asarray(getattr(chunk_inputs, field)), 0.0,
                      "%s.%s" % (path, field))
    assert np.array_equal(np.asarray(whole.dates)[sl],
                          np.asarray(chunk_inputs.dates))
    assert np.array_equal(np.asarray(whole.board),
                          np.asarray(chunk_inputs.board))
    assert np.all(np.isnan(np.asarray(chunk_inputs.volume)))


@pytest.mark.parametrize("chunk_days", [1, 2, 3, 9])
def test_p023_plan_meta_equal(tmp_path, chunk_days):
    root = _write_root(tmp_path, **{})
    plan, results = _plan_all(root, chunk_days)
    whole, inputs = _run_whole(root, chunk_days=9)
    assert plan.meta == whole["meta"]
    assert plan.diagnostics == inputs.diagnostics
    assert len(results) == int(np.ceil(9 / chunk_days))
    for chunk, res in results:
        _compare_inputs(inputs, res.inputs,
                        slice(chunk.start, chunk.stop),
                        "chunk[%d]" % chunk.start)


def test_p023_ref_fallback_tier(tmp_path):
    """adj 存在但含缺格 → ref fallback，plan 的 data_tier 必须与整幅一致。"""
    p = _panels()
    adj = p["adj"].copy()
    adj.iloc[2:4, 0] = np.nan
    p["adj"] = adj
    root = _write_root(tmp_path, p)
    plan, results = _plan_all(root, 2)
    close = pd.read_pickle(os.path.join(str(root), "market_data",
                                        "stock_close.pkl"))
    whole_inputs, whole_meta = _spec(root, 9).build(close.index,
                                                    close.columns)
    assert plan.meta == whole_meta
    assert plan.diagnostics == whole_inputs.diagnostics
    assert plan.diagnostics["data_tier"] == "D1"
    assert plan.diagnostics["ref_fallback_cells"] > 0
    for chunk, res in results:
        _assert_equal(np.asarray(whole_inputs.ref)[chunk.start:chunk.stop],
                      res.inputs.ref, 0.0, "ref@%d" % chunk.start)


def test_p023_chunk_lookback(tmp_path):
    p = _panels()
    p["adj"] = pd.DataFrame(
        np.tile(1.0 + np.arange(9)[:, None] * 0.01, (1, 4)),
        index=DATES, columns=CODES)
    root = _write_root(tmp_path, p)
    plan, results = _plan_all(root, 2)
    close = pd.read_pickle(os.path.join(str(root), "market_data",
                                        "stock_close.pkl"))
    spec = _spec(root, 2)
    whole, _ = spec.build(close.index, close.columns)
    for chunk, res in results:
        if chunk.start == 0:
            assert res.prev_close0 is None
            continue
        assert np.array_equal(res.prev_close0,
                              close.to_numpy(float)[chunk.start - 1])
        _assert_equal(np.asarray(whole.ref)[chunk.start],
                      res.inputs.ref[0], 0.0,
                      "ref[%d]" % chunk.start)
        assert np.array_equal(res.inputs.close[0],
                              close.to_numpy(float)[chunk.start])


def test_p023_name_carry(tmp_path):
    p = _panels()
    name = p["name"].copy()
    name.iloc[0:3, 0] = np.nan
    name.iloc[3, 0] = "ST测试"
    p["name"] = name
    root = _write_root(tmp_path, p)
    plan, results = _plan_all(root, 2)
    whole, inputs = _run_whole(root, chunk_days=9)
    assert plan.meta == whole["meta"]
    for chunk, res in results:
        _assert_equal(inputs.is_st[chunk.start:chunk.stop],
                      res.inputs.is_st, 0.0, "is_st@%d" % chunk.start)
    # 首块全 NaN 列不继承窗口外名称
    assert not results[0][1].inputs.is_st[0:2, 0].any()


def test_p023_no_limit_cross_chunk(tmp_path):
    p = _panels()
    name = p["name"].copy()
    name.iloc[7:, 3] = "退市"
    p["name"] = name
    ld = ["2024-01-05", "2024-01-02", "2024-01-03", "2024-01-04"]
    root = _write_root(tmp_path, p, list_date=ld)
    plan, results = _plan_all(root, 2)
    whole, inputs = _run_whole(root, chunk_days=9)
    assert plan.meta["no_limit_cells"] == whole["meta"]["no_limit_cells"]
    assert plan.meta["no_limit_source"] == "list_date"
    for chunk, res in results:
        _assert_equal(inputs.no_limit[chunk.start:chunk.stop],
                      res.inputs.no_limit, 0.0, "no_limit@%d" % chunk.start)


# ── apply 状态 / turnover ─────────────────────────────────────────


def _apply_arrays(tmp_path):
    p = _panels()
    sus = p["suspend"].copy()
    sus.iloc[3, 1] = "S"
    p["suspend"] = sus
    root = _write_root(tmp_path, p)
    close = pd.read_pickle(os.path.join(str(root), "market_data",
                                        "stock_close.pkl"))
    spec = _spec(root, 9)
    inputs, _ = spec.build(close.index, close.columns)
    target = np.tile(np.array([0.5, 0.3, -0.2, 0.0]), (9, 1))
    prev_close = np.full((9, 4), np.nan)
    prev_close[1:] = inputs.close[:-1]
    return inputs, target, prev_close


def test_p023_apply_state_boundary(tmp_path):
    inputs, target, prev_close = _apply_arrays(tmp_path)
    target = np.clip(target, 0.0, None)      # 与引擎一致：apply 只处理多头
    full_eff, full_report, full_diag = apply_tradability_with_diagnostics(
        target, prev_close, inputs.high, inputs.low, inputs.close,
        inputs.open_, inputs.volume, inputs.suspended, inputs.board,
        inputs.is_st, inputs.dates, policy=inputs.policy, adj=inputs.adj,
        is_delisting=inputs.is_delisting, no_limit=inputs.no_limit,
        ref=inputs.ref)
    for chunk_days in (1, 2, 4):
        state = TradabilityApplyState(
            np.zeros(4), np.full(4, -1, dtype=int), np.zeros(4))
        eff_parts, report_total, diag_total = [], None, {}
        for s in range(0, 9, chunk_days):
            e = min(s + chunk_days, 9)
            chunk_prev = np.full((e - s, 4), np.nan)
            if e - s > 1:
                chunk_prev[1:] = prev_close[s + 1:e]
            chunk_prev[0] = prev_close[s]
            target_prev = None if s == 0 else target[s - 1].copy()
            eff, rep, diag, state = apply_tradability_with_diagnostics(
                target[s:e], chunk_prev, inputs.high[s:e], inputs.low[s:e],
                inputs.close[s:e], inputs.open_[s:e], inputs.volume[s:e],
                inputs.suspended[s:e], inputs.board, inputs.is_st[s:e],
                inputs.dates[s:e], policy=inputs.policy,
                adj=None if inputs.adj is None else inputs.adj[s:e],
                is_delisting=inputs.is_delisting[s:e],
                no_limit=inputs.no_limit[s:e],
                ref=None if inputs.ref is None else inputs.ref[s:e],
                state=state, target_prev=target_prev, t_offset=s,
                is_last_chunk=(e == 9), return_state=True)
            eff_parts.append(eff)
            if report_total is None:
                report_total = dict(rep)
            else:
                for k in report_total:
                    report_total[k] += rep[k]
            for k, v in diag.items():
                if k.endswith("_cells") and not isinstance(v, bool):
                    diag_total[k] = diag_total.get(k, 0) + int(v)
                else:
                    diag_total[k] = v
        _assert_equal(full_eff, np.vstack(eff_parts), 0.0,
                      "apply_eff@%d" % chunk_days)
        assert full_report == report_total, chunk_days
        assert full_diag == diag_total, chunk_days
    with pytest.raises(ValueError):
        apply_tradability_with_diagnostics(
            target, prev_close, inputs.high, inputs.low, inputs.close,
            inputs.open_, inputs.volume, inputs.suspended, inputs.board,
            inputs.is_st, inputs.dates, policy=inputs.policy,
            adj=inputs.adj, ref=inputs.ref, t_offset=-1)


def test_p023_turnover_boundary(tmp_path):
    root = _write_root(tmp_path, **{})
    for chunk_days in (1, 2, 3, 9):
        _PANEL_CACHE.clear()
        stream, _ = _run_stream(root, chunk_days)
        _PANEL_CACHE.clear()
        whole, _ = _run_whole(root, chunk_days=9)
        _assert_equal(whole["turnover"], stream["turnover"], 0.0,
                      "turnover@%d" % chunk_days)
        assert stream["turnover"].shape == (8,)


# ── 引擎 / worker 流式逐位 ────────────────────────────────────────


@pytest.mark.parametrize("name", ["F1_basic", "F2_st", "F3_suspend",
                                 "F4_delist_ipo"])
@pytest.mark.parametrize("chunk_days", [1, 2, 7, 60])
def test_p023_stream_engine_equal(tmp_path, name, chunk_days):
    roots = _fixtures(tmp_path / name)
    root = roots[name]
    _PANEL_CACHE.clear()
    stream, _ = _run_stream(root, chunk_days)
    _PANEL_CACHE.clear()
    whole, _ = _run_whole(root, chunk_days=9)
    _assert_equal(whole, stream, 0.0, "%s@%d" % (name, chunk_days))


def test_p023_plan_off(tmp_path):
    root = _write_root(tmp_path, **{})
    spec = _spec(root, 3, mode="off")
    close = pd.read_pickle(os.path.join(str(root), "market_data",
                                        "stock_close.pkl"))
    plan = spec.build_plan(close.index, close.columns)
    assert plan.mode == "off"
    assert set(plan.finalize()) == {"mode", "mode_requested",
                                    "degrade_reason", "coverage"}
    with pytest.raises(ValueError):
        for chunk in plan.iter_chunks():
            plan.build_chunk(chunk)
    close_a = close.to_numpy(float)
    factor = _factor(close_a)
    off = FactorBacktestEngine(_FakeDL(factor, close_a),
                               config={"top_n": 0.5},
                               tradability_plan=plan).run()["f1"]
    raw = FactorBacktestEngine(_FakeDL(factor, close_a),
                               config={"top_n": 0.5}).run()["f1"]
    assert "tradability" not in off
    assert np.array_equal(np.asarray(off["turnover"]),
                          np.asarray(raw["turnover"]), equal_nan=True)


def test_p023_worker_stream_equal(tmp_path):
    pytest.importorskip("Factor_Trading_v3_0")
    root = _write_root(tmp_path, **{})
    close = pd.read_pickle(os.path.join(str(root), "market_data",
                                        "stock_close.pkl"))
    price = close.copy()
    factor = pd.DataFrame(_factor(close.to_numpy(float)),
                          index=close.index, columns=close.columns)
    spec = _spec(root, chunk_days=2)
    summary = _run_worker((["f1"], {"f1": factor}, price, None,
                           {"top_n": 0.5}, spec))["f1"]
    close_a = close.to_numpy(float)
    inputs, _ = spec.build(close.index, close.columns)
    whole_engine = FactorBacktestEngine(
        _FakeDL(_factor(close_a), close_a), config={"top_n": 0.5},
        tradability_inputs=inputs)
    expected = whole_engine.summary()["f1"]
    assert set(summary) == set(expected)
    for key in summary:
        assert np.isclose(summary[key], expected[key], rtol=0, atol=1e-12,
                          equal_nan=True), key


def test_p023_errors(tmp_path):
    root = _write_root(tmp_path, **{})
    close = pd.read_pickle(os.path.join(str(root), "market_data",
                                        "stock_close.pkl"))
    spec = _spec(root, 2)
    with pytest.raises(ValueError):
        spec.build_plan(close.index, ["999999.SH"])
    with pytest.raises(ValueError):
        _spec(root, 0).build_plan(close.index, close.columns)
    plan = spec.build_plan(close.index, close.columns)
    inputs, _ = spec.build(close.index, close.columns)
    close_a = close.to_numpy(float)
    with pytest.raises(ValueError):
        FactorBacktestEngine(_FakeDL(_factor(close_a), close_a),
                             tradability_inputs=inputs,
                             tradability_plan=plan)
    small = close_a[:5, :2]
    with pytest.raises(ValueError):
        FactorBacktestEngine(_FakeDL(_factor(small), small),
                             tradability_plan=plan)


# ── 键冻结 / 缓存只读 / 脚本 ──────────────────────────────────────


def test_p023_key_freeze(tmp_path):
    root = _write_root(tmp_path, **{})
    _PANEL_CACHE.clear()
    stream, _ = _run_stream(root, 2)
    _PANEL_CACHE.clear()
    whole, _ = _run_whole(root, 9)
    assert len(whole["report"]) == 9
    assert len(whole["meta"]) == 13
    assert set(stream["report"]) == set(whole["report"])
    assert set(stream["meta"]) == set(whole["meta"])
    assert set(stream["diagnostics"]) == set(whole["diagnostics"])


def _cache_hash():
    digest = hashlib.sha256()
    for key in sorted(_PANEL_CACHE):
        rec = _PANEL_CACHE[key]
        digest.update(repr(key).encode())
        if rec.kind == "name":
            digest.update(np.ascontiguousarray(rec.data).tobytes())
        elif rec.kind == "suspend":
            digest.update(np.ascontiguousarray(rec.data[0]).tobytes())
            digest.update(np.ascontiguousarray(rec.data[1]).tobytes())
        elif rec.kind in ("float", "raw"):
            digest.update(np.ascontiguousarray(
                rec.data.to_numpy()).tobytes())
    return digest.hexdigest()


def test_p023_cache_immutable(tmp_path):
    root = _write_root(tmp_path, **{})
    plan, first = _plan_all(root, 2)
    h1 = _cache_hash()
    hashes = [hashlib.sha256(np.ascontiguousarray(res.inputs.close).tobytes())
              .hexdigest() for _, res in first]
    # 二次迭代不改变缓存/面板数组，且结果一致
    second = []
    for chunk in plan.iter_chunks():
        second.append(plan.build_chunk(chunk))
    h2 = _cache_hash()
    assert h1 == h2
    for (_, a), b in zip(first, second):
        assert hashlib.sha256(
            np.ascontiguousarray(a.inputs.close).tobytes()).hexdigest() == \
            hashlib.sha256(
                np.ascontiguousarray(b.inputs.close).tobytes()).hexdigest()
    float_keys = [k for k in _PANEL_CACHE
                  if k[2] in ("close", "high", "low", "open", "adj",
                              "volume")]
    assert not float_keys


def test_p023_script_schema(tmp_path):
    root = _write_root(tmp_path, **{})
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        "scripts", "verify_tradability_memory.py")
    spec = importlib.util.spec_from_file_location("p023_memory", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    report = mod.build_report(str(root), chunk_days=2, run_index=2)
    assert set(report) == {"meta", "m1", "m2", "m3", "m4", "m6", "rows"}
    assert set(report["meta"]) >= {"data_root", "panel_dir", "n_dates",
                                   "n_codes", "chunk_days", "run_index",
                                   "run_at"}
    assert set(report["m1"]) == {"plan_s", "build_all_chunks_s", "total_s"}
    assert set(report["m2"]) == {"tracemalloc_peak_mb"}
    assert set(report["m4"]) == {"name_mb", "suspend_mb", "total_mb"}
    assert set(report["m6"]) == {"rss_after_mb"}
    assert report["m3"] is None
    assert len(report["rows"]) == int(np.ceil(9 / 2))
    assert set(report["rows"][0]) == {"chunk", "dates", "build_s",
                                      "apply_s"}
    assert mod.main(["--data-root", str(tmp_path / "nope")]) == 2
