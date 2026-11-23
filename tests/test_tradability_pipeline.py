# -*- coding: utf-8 -*-
"""P-021 A4：管道/并行接线（spec 透传、默认 None、并行 summary 契约）。

外部 `factor-trading-v3` 缺失时以替身 DataLoader 验证接线（RULE-3：
不依赖环境安装状态；引擎仅消费 n_dates/n_stocks/price_data/factor_data）。
"""
from types import SimpleNamespace

import numpy as np
import pandas as pd

from backtest.data_bridge import DataBridge
from backtest.parallel_runner import ParallelFactorRunner, _run_worker, run_parallel
from backtest.pipeline_integration import PipelineBacktestRunner


class _FakeDL(object):
    def __init__(self, factors, price):
        self.n_dates, self.n_stocks = price.shape[1], price.shape[0]
        self.price_data = {"close": price.to_numpy(dtype=float).T}
        self.factor_data = {k: v.to_numpy(dtype=float).T
                            for k, v in factors.items()}


def _patch_bridge(monkeypatch):
    """同时替换两种模块路径下的 DataBridge（flat layout 双身份）。"""
    classes = {DataBridge}
    try:
        from factor_pipeline.backtest.data_bridge import DataBridge as DB2
        classes.add(DB2)
    except ImportError:
        pass
    for cls in classes:
        monkeypatch.setattr(cls, "validate_shapes",
                            lambda self, f, p: (True, ""))
        monkeypatch.setattr(cls, "create_dataloader",
                            lambda self, f, p: _FakeDL(f, p))


def _fixture(tmp_path, n_dates=8, n_stocks=4):
    md = tmp_path / "market_data"
    md.mkdir(parents=True, exist_ok=True)
    dates = pd.date_range("2024-01-02", periods=n_dates, freq="B")
    codes = ["600000.SH", "000001.SZ", "300001.SZ", "600001.SH"][:n_stocks]
    close = pd.DataFrame(10.0, index=dates, columns=codes)
    close.to_pickle(md / "stock_close.pkl")
    (close * 1.005).to_pickle(md / "stock_high.pkl")
    (close * 0.995).to_pickle(md / "stock_low.pkl")
    close.to_pickle(md / "stock_open.pkl")
    pd.DataFrame(1e6, index=dates, columns=codes).to_pickle(
        md / "stock_volume.pkl")
    pd.DataFrame(np.nan, index=dates, columns=codes,
                 dtype=object).to_pickle(md / "stock_suspend.pkl")
    pd.DataFrame("普通", index=dates, columns=codes).to_pickle(
        md / "stock_name.pkl")
    pd.DataFrame(1.0, index=dates, columns=codes).to_pickle(
        md / "stock_adj.pkl")

    rng = np.random.RandomState(7)
    price = pd.DataFrame(rng.randn(n_stocks, n_dates).cumsum(axis=1) * 0.1
                         + 10.0, index=codes, columns=dates)
    factors = {"f1": pd.DataFrame(
        rng.randn(n_stocks, n_dates), index=codes, columns=dates)}
    return dates, codes, price, factors


def _config():
    return SimpleNamespace(ic_method="rank", top_n=0.5, ls_method="top_n",
                           max_lag=12, enable_health_check=False,
                           enable_drift_detection=False)


def test_p021_pipeline_passthrough(tmp_path, monkeypatch):
    """管道：spec 生效 → 挂块；spec=None → 旧结果不含块。"""
    from backtest.tradability_loader import TradabilitySpec

    _patch_bridge(monkeypatch)
    dates, codes, price, factors = _fixture(tmp_path)
    base = PipelineBacktestRunner(config=_config()).run(
        factors, price)["engine_results"]["f1"]
    assert "tradability" not in base

    spec = TradabilitySpec(data_root=str(tmp_path))
    res = PipelineBacktestRunner(
        config=_config(), tradability_spec=spec).run(
        factors, price)["engine_results"]["f1"]
    block = res["tradability"]
    assert block["diagnostics"]["schema_version"] == 2
    assert block["turnover_basis"] == "effective_long_only"
    assert "close_mismatch_cells" in block["diagnostics"]
    # INV-11：整块可 JSON 序列化（无 numpy 标量）
    import json
    json.dumps(block)


def test_p021_engine_mode_off_gate(tmp_path, monkeypatch):
    """INV-13：policy.mode=off 的 inputs 视同未启用（不挂块、turnover 不变）。"""
    from backtest.engine import FactorBacktestEngine
    from backtest.tradability import TradabilityInputs, TradabilityPolicy

    _patch_bridge(monkeypatch)
    dates, codes, price, factors = _fixture(tmp_path)
    dl = _FakeDL(factors, price)
    base = FactorBacktestEngine(dl, config={"top_n": 0.5}).run()["f1"]

    T, N = dl.n_dates, dl.n_stocks
    inputs = TradabilityInputs(
        close=dl.price_data["close"].copy(),
        high=dl.price_data["close"] * 1.01,
        low=dl.price_data["close"] * 0.99,
        open_=dl.price_data["close"].copy(),
        volume=np.full((T, N), 1e6),
        suspended=np.zeros((T, N), dtype=bool),
        dates=np.array([d.strftime("%Y-%m-%d") for d in dates]),
        board=np.array(["main"] * N),
        is_st=np.zeros((T, N), dtype=bool),
        adj=np.ones((T, N)),
        policy=TradabilityPolicy(mode="off"))
    off = FactorBacktestEngine(
        dl, config={"top_n": 0.5}, tradability_inputs=inputs).run()["f1"]
    assert "tradability" not in off
    np.testing.assert_allclose(np.asarray(off["turnover"], dtype=float),
                               np.asarray(base["turnover"], dtype=float))


def test_p021_partial_limit_source_block(tmp_path, monkeypatch):
    """INV-10（审计 P1-①）：partial 限价表标记在引擎块中不得被覆盖。"""
    from backtest.engine import FactorBacktestEngine
    from backtest.tradability import TradabilityInputs

    _patch_bridge(monkeypatch)
    dates, codes, price, factors = _fixture(tmp_path, n_dates=4, n_stocks=1)
    dl = _FakeDL(factors, price)
    T, N = dl.n_dates, dl.n_stocks
    ones = np.ones((T, N))
    limit_up = np.full((T, N), 11.0)
    limit_down = np.full((T, N), 9.0)
    limit_up[1, 0] = np.nan            # 缺 1 格 → partial
    limit_down[1, 0] = np.nan
    inputs = TradabilityInputs(
        close=dl.price_data["close"].copy(), high=dl.price_data["close"] * 1.01,
        low=dl.price_data["close"] * 0.99,
        open_=dl.price_data["close"].copy(),
        volume=np.full((T, N), 1e6), suspended=np.zeros((T, N), dtype=bool),
        dates=np.array([d.strftime("%Y-%m-%d") for d in dates]),
        board=np.array(["main"] * N), is_st=np.zeros((T, N), dtype=bool),
        adj=ones, policy=None, meta={"price_basis": "raw_adj_ref"},
        limit_up=limit_up, limit_down=limit_down,
        diagnostics={"schema_version": 2,
                     "limit_table_source": "stk_limit_partial",
                     "limit_table_missing_cells": 1})
    block = FactorBacktestEngine(
        dl, config={"top_n": 0.5}, tradability_inputs=inputs).run()["f1"][
            "tradability"]
    assert block["diagnostics"]["limit_table_source"] == "stk_limit_partial"
    assert block["diagnostics"]["limit_table_missing_cells"] == 1


def test_p021_parallel_summary_contract(tmp_path, monkeypatch):
    """并行 worker：spec 内部生效；summary 不含块（契约冻结）。"""
    from backtest.tradability_loader import TradabilitySpec

    _patch_bridge(monkeypatch)
    dates, codes, price, factors = _fixture(tmp_path)
    spec = TradabilitySpec(data_root=str(tmp_path))
    out = _run_worker((["f1"], factors, price, None, None, spec))
    assert set(out) == {"f1"}
    assert "tradability" not in out["f1"]
    assert set(out["f1"]) <= {"rank_icir", "pearson_icir", "hit_rate",
                              "spread", "mean_rank_ic"}

    out_none = _run_worker((["f1"], factors, price, None, None, None))
    assert "tradability" not in out_none["f1"]
    # INV-2：启用 spec 不改变 summary 的 IC/spread 标量
    for key in out_none["f1"]:
        assert out["f1"][key] == out_none["f1"][key] or (
            np.isnan(out["f1"][key]) and np.isnan(out_none["f1"][key]))


def test_p021_parallel_worker_error(tmp_path, monkeypatch):
    """E-12：worker 内构建失败 → 异常上抛（不静默降级）。"""
    import pytest

    from backtest.tradability_loader import TradabilitySpec

    _patch_bridge(monkeypatch)
    dates, codes, price, factors = _fixture(tmp_path)
    bad = TradabilitySpec(data_root=str(tmp_path / "missing"))
    with pytest.raises(ValueError):
        _run_worker((["f1"], factors, price, None, None, bad))


def test_p021_parallel_signature_passthrough(tmp_path):
    """签名：runner 与便捷函数均接受 tradability_spec（None 默认）。"""
    import inspect

    from backtest.tradability_loader import TradabilitySpec

    sig = inspect.signature(ParallelFactorRunner.__init__)
    assert "tradability_spec" in sig.parameters
    assert sig.parameters["tradability_spec"].default is None
    sig2 = inspect.signature(run_parallel)
    assert "tradability_spec" in sig2.parameters
    spec = TradabilitySpec(data_root=str(tmp_path))
    assert ParallelFactorRunner(
        n_workers=1, tradability_spec=spec).tradability_spec is spec
