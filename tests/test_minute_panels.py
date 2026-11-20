# -*- coding: utf-8 -*-
"""v3.8.1 分钟面板编排（T381-01 ~ T381-20）。

红形态：``ImportError: cannot import name 'MinutePanelBuilder'``。
设计依据：DESIGN_V3.8.1；实施依据：EXECUTION_V3.8.1 §2.7 / §5。
"""
import dataclasses
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
MINUTE_ROOT = Path(r"E:\Level 1 Data")
DATA_ROOT = Path(r"E:\Ashare_data")


def has_pyarrow():
    from backtest.execution.shell.loaders import has_pyarrow as probe
    return bool(probe())


needs_pyarrow = pytest.mark.skipif(not has_pyarrow(),
                                   reason="calib extra（pyarrow）未安装")
needs_minutes = pytest.mark.skipif(not MINUTE_ROOT.is_dir(),
                                   reason="分钟数据缺失 E:\\Level 1 Data")
needs_daily = pytest.mark.skipif(not DATA_ROOT.is_dir(),
                                 reason="日频数据缺失 E:\\Ashare_data")


@pytest.fixture()
def cfg():
    from backtest.execution.config import CalibrationConfig
    return CalibrationConfig(minute_root=None)


class FakeLoader(object):
    """测试缝：直接返回构造好的 MinuteDayAggregate。"""

    def __init__(self, by_month):
        self.by_month = by_month

    def available_months(self):
        return sorted(self.by_month)

    def load_month_regression(self, ym):
        return self.by_month[ym]


def _agg(ym, codes=(1, 2, 600000, 600001), days=20, lam=2.5):
    """已知 λ 的合成「股票×日」聚合：x=0.01，r=λx。"""
    from backtest.execution.shell.loaders import MinuteDayAggregate
    codes = [int(c) for c in codes]
    n = len(codes) * int(days)
    date = []
    stock = []
    for d in range(int(days)):
        for c in codes:
            date.append("%s-%02d" % (ym, d + 1))
            stock.append(c)
    x = 0.01
    return MinuteDayAggregate(
        date=np.asarray(date, dtype=object),
        stock_code=np.asarray(stock, dtype=np.int64),
        signed_day=np.full(n, 1e9 * x, dtype=float),
        amount_day=np.full(n, 1e9, dtype=float),
        ret_day=np.full(n, float(lam) * x, dtype=float),
        sigma=np.full(n, 0.02, dtype=float),
        n_bars=np.full(n, 240, dtype=np.int64),
        limit_lock=np.zeros(n, dtype=bool))


def _daily_ref(days=None):
    from backtest.execution.shell.panels import DailyRef
    idx = pd.to_datetime(["2023-01-31", "2023-02-28", "2023-03-31"])
    cols = ["000001", "000002", "600000", "600001"]
    adv = pd.DataFrame(1e9, index=idx, columns=cols)
    universe = pd.DataFrame(True, index=idx, columns=cols)
    industry = pd.DataFrame("银行", index=idx, columns=cols)
    mv_rank = pd.DataFrame(3, index=idx, columns=cols)
    return DailyRef(adv=adv, universe=universe, industry=industry,
                    mv_rank=mv_rank,
                    days_by_month=dict(days or {"2023-01": 20, "2023-02": 20,
                                                "2023-03": 23}))


@pytest.fixture()
def daily_ref():
    return _daily_ref()


def _cfg_window(cfg, start="2023-01-01", end="2023-03-31"):
    return dataclasses.replace(cfg, minute_start=start, minute_end=end)


def _write_day(path, records):
    import pyarrow as pa
    import pyarrow.feather as feather
    columns = {}
    for key in ("time", "stock_code", "open", "high", "low", "close",
                "volume", "amount"):
        columns[key] = [rec[key] for rec in records]
    feather.write_feather(pa.table(columns), str(path))


def _rising(base=10.0, amount=1e6):
    return [
        dict(time=930, stock_code=1, open=base, high=base * 1.002,
             low=base * 0.998, close=base * 1.001, volume=100.0,
             amount=amount),
        dict(time=931, stock_code=1, open=base * 1.001, high=base * 1.004,
             low=base * 0.999, close=base * 1.003, volume=100.0,
             amount=amount),
    ]


# ---------------------------------------------------------------- R1（E0）
def test_keep_mask_bounds():
    """T381-01: 分钟代码过滤下界为 1，剔除 390000-399999。"""
    from backtest.execution.shell.loaders import (EXCLUDE_CODE, MAX_STOCK_CODE,
                                                  MIN_STOCK_CODE, _keep_mask)
    assert MIN_STOCK_CODE == 1
    assert MAX_STOCK_CODE == 1000000
    assert EXCLUDE_CODE == (390000, 400000)
    codes = np.array([1, 600000, 390001, 1000000, 0, 399999, 400000])
    assert _keep_mask(codes).tolist() == [True, True, False, False, False,
                                          False, True]


def test_code_alignment_zfill(cfg, daily_ref):
    """T381-02: 整数代码 -> 6 位字符串，_adv_lookup 可取到当月值。"""
    from backtest.execution.shell.panels import MinutePanelBuilder
    builder = MinutePanelBuilder(cfg, loader=FakeLoader({}), daily=daily_ref)
    assert "%06d" % 1 == "000001"
    adv = builder._adv_lookup("2023-01")
    assert adv[1] == pytest.approx(1e9)
    assert np.isfinite(adv[600000])


@needs_pyarrow
def test_intraday_return(tmp_path):
    """T381-05: ret_day == close_last/open_first - 1；跨月不串。"""
    from backtest.execution.shell.loaders import MinuteLoader
    root = tmp_path / "min"
    root.mkdir()
    day1 = [
        dict(time=930, stock_code=1, open=10.0, high=10.2, low=9.9,
             close=10.1, volume=1.0, amount=1e6),
        dict(time=931, stock_code=1, open=10.1, high=11.2, low=10.0,
             close=11.0, volume=1.0, amount=1e6)]
    day2 = [
        dict(time=930, stock_code=1, open=20.0, high=20.2, low=18.9,
             close=19.5, volume=1.0, amount=1e6),
        dict(time=931, stock_code=1, open=19.5, high=19.8, low=18.8,
             close=19.0, volume=1.0, amount=1e6)]
    _write_day(root / "2023-01-03.feather", day1)
    _write_day(root / "2023-01-04.feather", day2)
    _write_day(root / "2023-02-01.feather", _rising())
    agg = MinuteLoader(root).load_month_regression("2023-01")
    assert agg.ret_day.size == 2
    assert agg.ret_day[0] == pytest.approx(11.0 / 10.0 - 1.0)
    assert agg.ret_day[1] == pytest.approx(19.0 / 20.0 - 1.0)


# ---------------------------------------------------------------- R2
@needs_pyarrow
def test_minute_amount_reconcile(tmp_path):
    """T381-03: Σ分钟 amount / (Σ日频 amount×1e3) ∈ [0.999, 1.001]。"""
    from backtest.execution.shell.loaders import MinuteLoader
    root = tmp_path / "min"
    root.mkdir()
    _write_day(root / "2023-01-03.feather", [
        dict(time=t, stock_code=1, open=10.0, high=10.5, low=9.8,
             close=10.2, volume=100.0, amount=123456.0)
        for t in (930, 931)])
    _write_day(root / "2023-01-04.feather", [
        dict(time=t, stock_code=1, open=10.2, high=10.6, low=10.0,
             close=10.4, volume=100.0, amount=23456.0)
        for t in (930, 931)])
    agg = MinuteLoader(root).load_month_regression("2023-01")
    minute_sum = 2 * 123456.0 + 2 * 23456.0
    daily_k = minute_sum / 1e3          # 日频 amount 单位为千元
    ratio = float(agg.amount_day.sum()) / (daily_k * 1e3)
    assert 0.999 <= ratio <= 1.001


@needs_pyarrow
def test_bvc_signed_and_limit_lock(tmp_path):
    """T381-04: s_t 符号随 2Φ(r/σ)−1；锁定 bar 的 s_t=0 而 amount 全量。"""
    from backtest.execution.shell.loaders import MinuteLoader
    root = tmp_path / "min"
    root.mkdir()
    _write_day(root / "2023-01-03.feather", [
        dict(time=930, stock_code=1, open=10.0, high=10.05, low=9.95,
             close=10.0, volume=100.0, amount=1e6),
        dict(time=931, stock_code=1, open=10.0, high=10.15, low=10.0,
             close=10.1, volume=100.0, amount=1e6),
        dict(time=932, stock_code=1, open=10.1, high=10.35, low=10.1,
             close=10.3, volume=100.0, amount=1e6),
        dict(time=933, stock_code=1, open=10.3, high=10.65, low=10.3,
             close=10.6, volume=100.0, amount=1e6)])
    _write_day(root / "2023-01-04.feather", [
        dict(time=930, stock_code=1, open=10.3, high=10.3, low=10.3,
             close=10.3, volume=0.0, amount=3e6)])
    agg = MinuteLoader(root).load_month_regression("2023-01")
    assert agg.signed_day[0] > 0.0
    assert agg.limit_lock[1] is np.True_ or bool(agg.limit_lock[1])
    assert agg.signed_day[1] == 0.0
    assert agg.amount_day[1] == pytest.approx(3e6)


def test_lambda_recovery():
    """T381-06: r_d = λx_d -> fit_lambda_hac 估回 λ（rtol 1e-8）。"""
    from backtest.execution.shell.runner import fit_lambda_hac
    rng = np.random.default_rng(12)
    x = rng.uniform(1e-3, 0.05, 400)
    out = fit_lambda_hac(x, 2.5 * x)
    assert abs(out["lambda"] - 2.5) < 1e-8


def test_hac_vs_iid_p():
    """T381-07: AR(1) 正残差下 HAC 的 p 大于 iid 的 p。"""
    from backtest.execution.core.classification import normal_cdf
    from backtest.execution.shell.runner import fit_lambda_hac
    rng = np.random.default_rng(13)
    n = 400
    x = np.zeros(n)
    eps = np.zeros(n)
    for t in range(1, n):
        x[t] = 0.6 * x[t - 1] + rng.normal(0.0, 0.01)
        eps[t] = 0.6 * eps[t - 1] + rng.normal(0.0, 0.40)
    out = fit_lambda_hac(x, 2.0 * x + eps)
    t_iid = abs(out["lambda"]) / out["se_iid"]
    p_iid = float(2.0 * (1.0 - normal_cdf(np.array([t_iid]))[0]))
    assert 0.0 < out["p"] < 1.0
    assert out["p"] > p_iid


# ---------------------------------------------------------------- R3
def test_fill_ratio_definition(cfg, daily_ref):
    """T381-08: fill_ratio == 1 − n_sig/n_total。"""
    from backtest.execution.shell.panels import MinutePanelBuilder
    builder = MinutePanelBuilder(cfg, loader=FakeLoader({}), daily=daily_ref)
    rows = [{"code": i, "month": "2023-01",
             "lambda": 1.0 if i < 3 else 0.5,
             "p": 0.01 if i < 3 else 0.5, "n_days": 20,
             "industry": "银行", "mv_bucket": 3} for i in range(10)]
    out = builder._fill_lambda(rows)
    assert out["lambda_stats"]["n_sig"] == 3
    assert out["lambda_stats"]["n_total"] == 10
    assert out["lambda_stats"]["fill_ratio"] == pytest.approx(0.7)


def test_fill_ratio_degrade(cfg, daily_ref):
    """T381-09: fill_ratio>0.30 -> c_interval_only=True 且写 warning。"""
    from backtest.execution.shell.panels import MinutePanelBuilder
    builder = MinutePanelBuilder(cfg, loader=FakeLoader({}), daily=daily_ref)
    rows = [{"code": i, "month": "2023-01", "lambda": 1.0, "p": 0.5,
             "n_days": 20, "industry": "银行", "mv_bucket": 3}
            for i in range(10)]
    out = builder._fill_lambda(rows)
    assert out["lambda_stats"]["fill_ratio"] == pytest.approx(1.0)
    assert out["lambda_stats"]["c_interval_only"] is True
    assert any("lambda_fill_ratio" in w for w in out["evidence_warnings"])


@needs_pyarrow
def test_partial_month(tmp_path, cfg):
    """T381-10: 22 文件/23 日 -> partial；19 日 -> 整月剔除。"""
    from backtest.execution.shell.loaders import MinuteLoader
    from backtest.execution.shell.panels import MinutePanelBuilder
    root = tmp_path / "min"
    root.mkdir()
    for d in range(1, 23):
        _write_day(root / ("2023-01-%02d.feather" % d), _rising())
    for d in range(1, 20):
        _write_day(root / ("2023-02-%02d.feather" % d), _rising())
    cfg2 = dataclasses.replace(cfg, minute_start="2023-01-01",
                               minute_end="2023-02-28", lambda_min_days=5)
    daily = _daily_ref({"2023-01": 23, "2023-02": 23})
    out = MinutePanelBuilder(cfg2, loader=MinuteLoader(root),
                             daily=daily).build()
    cov = out["coverage"]
    assert "2023-01" in cov.partial_months
    assert "2023-02" not in cov.months
    assert any("2023-02" in w for w in out["evidence_warnings"])


def test_coverage_gate():
    """T381-11: 覆盖度 0.671 -> (False, msgs)；PanelCoverage 对象同参可入。"""
    from backtest.execution.shell.panels import PanelCoverage, coverage_gate
    cov = {"universe_ratio": {"2023-01": 0.671, "2023-02": 0.68},
           "board_counts": {"沪主板": 100, "深主板": 0}}
    ok, msgs = coverage_gate(cov)
    assert ok is False
    assert msgs
    assert any("深市主板" in m or "中位" in m for m in msgs)
    obj = PanelCoverage(
        window=("2020-01", "2023-03"), months=["2023-01", "2023-02"],
        partial_months=[], missing_months=[],
        stock_median=4900.0,
        universe_ratio={"2023-01": 0.671, "2023-02": 0.68},
        limit_lock_ratio=0.05,
        board_counts={"沪主板": 100, "深主板": 0})
    ok_obj, msgs_obj = coverage_gate(obj)
    assert ok_obj is False
    assert msgs_obj == msgs


# ---------------------------------------------------------------- R4
def _impact_fit(p, impact, sigma):
    from backtest.execution.core.impact import (LinearImpact, LogImpact,
                                                PowerImpact, SqrtImpact,
                                                cross_val_rmse, select_models)
    models = (SqrtImpact(), LinearImpact(), LogImpact(), PowerImpact())
    cv = cross_val_rmse(list(models), p, impact, sigma)
    primary, _tied = select_models(cv)
    fitted = {}
    for model in models:
        try:
            fitted[model.name] = model.fit(p, impact, sigma)
        except ValueError:
            fitted[model.name] = None
    return {"primary": primary, "params": fitted.get(primary),
            "sigma_median": float(np.median(sigma)),
            "cv_rmse": {k: (None if not np.isfinite(v) else float(v))
                        for k, v in cv.items()}}


def test_assemble_and_run_calibration(cfg):
    """T381-12: 装配 -> run_calibration；impact_fit.params == models[primary]。"""
    from backtest.execution.shell.panels import (assemble_panels,
                                                 build_daily_panels)
    from backtest.execution.shell.runner import run_calibration
    rng = np.random.default_rng(7)
    n = 60
    p = rng.uniform(1e-3, 0.05, n)
    sigma = np.full(n, 0.02)
    impact = 0.5 * sigma * np.sqrt(p) + rng.normal(0.0, 1e-4, n)
    fit = _impact_fit(p, impact, sigma)
    minute = {"impact_samples": {"p": p, "impact": impact, "sigma": sigma},
              "evidence_warnings": []}
    ex_m = pd.Series(rng.normal(0.01, 0.02, 30),
                     index=pd.date_range("2020-01-31", periods=30, freq="ME"))
    portfolio = {
        "aum_ref": 1e10,
        "excess_m": ex_m,
        "excess_d": pd.Series(rng.normal(0.0005, 0.01, 100)),
        "turnover_m": pd.Series([0.2] * 30),
        "regime_p95": {"calm": 0.005, "vol": 0.01},
        "window_capacity": {"24": 12e9, "36": 11e9, "48": 10e9, "60": 9e9},
        "notional": np.array([1e6, 2e6]),
        "adv": np.array([1e9, 2e9]),
        "p_cost": 0.01,
        "sigma_port": 0.02,
    }
    daily = build_daily_panels(cfg, None, portfolio, impact_fit=fit)
    panels = assemble_panels(minute, daily, "minutes")
    out = run_calibration(
        cfg, capacity_fn=lambda p95, ref, cap: float(cap) / float(p95),
        panels=panels)
    assert out["capacity"]["regimes"]
    assert out["capacity"]["avew"]["primary"] is not None
    assert out["decay"]["net"]
    assert out["decay"]["execution"] is not None
    primary = out["selection"]["primary"]
    assert fit["params"] == out["models"][primary]["params"]


def test_panel_hash_stability(cfg, daily_ref):
    """T381-13: 同输入双跑相等；改 windows 即变。"""
    from backtest.execution.shell.panels import MinutePanelBuilder
    cfg2 = _cfg_window(cfg)
    by_month = {"2023-01": _agg("2023-01"), "2023-02": _agg("2023-02"),
                "2023-03": _agg("2023-03")}
    h1 = MinutePanelBuilder(cfg2, loader=FakeLoader(by_month),
                            daily=daily_ref).build()["panel_hash"]
    h2 = MinutePanelBuilder(cfg2, loader=FakeLoader(by_month),
                            daily=daily_ref).build()["panel_hash"]
    assert h1 == h2
    cfg3 = dataclasses.replace(cfg2, windows=(24, 36))
    h3 = MinutePanelBuilder(cfg3, loader=FakeLoader(by_month),
                            daily=daily_ref).build()["panel_hash"]
    assert h3 != h1


def test_missing_months(cfg, daily_ref):
    """T381-14: FakeLoader 缺 1 月 -> missing_months 记录且 build 不抛。"""
    from backtest.execution.shell.panels import MinutePanelBuilder
    cfg2 = _cfg_window(cfg)
    by_month = {"2023-01": _agg("2023-01"), "2023-02": _agg("2023-02")}
    out = MinutePanelBuilder(cfg2, loader=FakeLoader(by_month),
                             daily=daily_ref).build()
    assert "2023-03" in out["coverage"].missing_months
    assert "2023-01" in out["coverage"].months


def test_no_pyarrow_degrade(monkeypatch, cfg, tmp_path, daily_ref):
    """T381-15: has_pyarrow=False -> CalibrationUnavailable；evidence 回 ohlc。"""
    from backtest.execution.ports import CalibrationUnavailable
    from backtest.execution.shell import panels
    from backtest.execution.shell.loaders import resolve_evidence_level
    monkeypatch.setattr(panels, "has_pyarrow", lambda: False)
    cfg2 = dataclasses.replace(cfg, data_root=str(tmp_path))
    builder = panels.MinutePanelBuilder(cfg2, loader=FakeLoader({}),
                                        daily=daily_ref)
    with pytest.raises(CalibrationUnavailable):
        builder.build()
    assert resolve_evidence_level(cfg2) == "ohlc"


def test_panel_cache(tmp_path, cfg, daily_ref):
    """T381-16: 缓存写入 -> 命中；改 config_hash -> 未命中。"""
    from backtest.execution.shell.panels import MinutePanelBuilder
    cfg2 = _cfg_window(cfg)
    by_month = {"2023-01": _agg("2023-01"), "2023-02": _agg("2023-02"),
                "2023-03": _agg("2023-03")}
    out1 = MinutePanelBuilder(cfg2, loader=FakeLoader(by_month),
                              daily=daily_ref, cache_dir=tmp_path).build()
    out2 = MinutePanelBuilder(cfg2, loader=FakeLoader(by_month),
                              daily=daily_ref, cache_dir=tmp_path).build()
    assert out2["cache"]["hits"] >= 3
    assert out2["panel_hash"] == out1["panel_hash"]
    cfg3 = dataclasses.replace(cfg2, windows=(24, 36))
    out3 = MinutePanelBuilder(cfg3, loader=FakeLoader(by_month),
                              daily=daily_ref, cache_dir=tmp_path).build()
    assert out3["cache"]["hits"] == 0


# ---------------------------------------------------------------- R5（真实数据）
@pytest.fixture(scope="module")
def real_context():
    if not (MINUTE_ROOT.is_dir() and DATA_ROOT.is_dir()):
        pytest.skip("真实数据缺失（分钟/日频）")
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "scripts"))
    import verify_capacity_impact as vci
    return vci, vci.build_panels(str(DATA_ROOT))


@pytest.fixture(scope="module")
def real_month(real_context):
    vci, panels = real_context
    from backtest.execution.config import CalibrationConfig
    from backtest.execution.shell.panels import MinutePanelBuilder
    config = CalibrationConfig()
    builder = MinutePanelBuilder(config, daily=vci.daily_ref(panels, config))
    t0 = time.time()
    out = builder.build(months=["2023-03"])
    return vci, panels, config, out, time.time() - t0


@needs_minutes
@needs_daily
def test_real_month_panel(real_month):
    """T381-17: 2023-03 单月覆盖度 >= 0.90、深主板 > 0。"""
    _vci, _panels, _cfg, out, elapsed = real_month
    cov = out["coverage"].as_dict()
    assert cov["universe_ratio"]["2023-03"] >= 0.90
    assert cov["board_counts"]["深主板"] > 0
    target = ROOT / "out" / "v381_minute_202303.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "elapsed_s": elapsed, "coverage": cov,
        "lambda_stats": out["lambda_stats"],
        "impact_samples": out["impact_samples_meta"]},
        ensure_ascii=False, indent=2), encoding="utf-8")


@needs_minutes
@needs_daily
def test_report_four_sections(real_month):
    """T381-18: md 含面板覆盖度 / λ / 窗长容量 / 持有期净收益。"""
    from backtest.execution.shell.panels import (assemble_panels,
                                                 build_daily_panels)
    from backtest.execution.shell.report import render_markdown
    from backtest.execution.shell.runner import run_calibration
    vci, panels, config, minute_out, _elapsed = real_month
    portfolio = vci.build_portfolio_panels(panels, config)
    daily = build_daily_panels(config, panels, portfolio,
                               impact_fit=minute_out["impact_fit"])
    merged = assemble_panels(minute_out, daily, "minutes")
    result = run_calibration(
        config, capacity_fn=vci.capacity_from_p95,
        breakeven_fn=vci.breakeven_aum, panels=merged)
    result = vci.attach_panel_meta(result, minute_out, daily, config)
    md = render_markdown(result)
    for heading in ("面板覆盖度", "λ 显著性与填充", "窗长容量", "持有期净收益"):
        assert heading in md


# ---------------------------------------------------------------- R6
@needs_minutes
@needs_daily
def test_report_json_checks(tmp_path):
    """T381-20: --calibrate --report-json 的 checks 含三项且 status 可判定。"""
    script = ROOT / "scripts" / "verify_capacity_impact.py"
    report = tmp_path / "report.json"
    calib = tmp_path / "calib.json"
    proc = subprocess.run(
        [sys.executable, str(script), "--calibrate", "--no-minute",
         "--calibration-json", str(calib), "--report-json", str(report)],
        capture_output=True, text=True, timeout=1800)
    assert proc.returncode == 0, proc.stderr[-2000:]
    payload = json.loads(report.read_text(encoding="utf-8"))
    ids = [c["id"] for c in payload["checks"]]
    assert {"calibrate", "evidence_level", "coverage"} <= set(ids)
    assert payload["status"] in ("pass", "fail")


# ---------------------------------------------------------------- v3.9.2 口径修复
def _agg_varying(ym):
    """v3.9.2 T1：ret_day 日间变化、分钟 sigma 固定 0.02 的合成聚合。"""
    from backtest.execution.shell.loaders import MinuteDayAggregate
    days = 12
    ret = np.tile(np.array([0.02, -0.01, 0.005, 0.03, -0.02,
                            0.01, 0.0, 0.015, -0.005, 0.025, -0.015, 0.008]), 2)
    signed = np.tile(np.array([1.0, 1.6, 1.2, 2.0, 0.8, 1.4,
                               1.1, 1.8, 0.9, 1.3, 1.5, 0.7]) * 1e8, 2)
    n = ret.size
    return MinuteDayAggregate(
        date=np.asarray(["%s-%02d" % (ym, i % days + 1) for i in range(n)],
                        dtype=object),
        stock_code=np.repeat(np.array([1, 600000], dtype=np.int64), days),
        signed_day=signed, amount_day=np.full(n, 1e9),
        ret_day=ret, sigma=np.full(n, 0.02),
        n_bars=np.full(n, 240, dtype=np.int64),
        limit_lock=np.zeros(n, dtype=bool))


def test_impact_sigma_is_daily_scale(cfg, daily_ref):
    """T1（v3.9.2）：冲击样本 sigma 取日收益 std，不再用分钟 bar sigma。"""
    from backtest.execution.shell.panels import MinutePanelBuilder
    builder = MinutePanelBuilder(cfg, loader=FakeLoader({}), daily=daily_ref)
    agg = _agg_varying("2023-01")
    builder._month_lambda("2023-01", agg)
    expected = float(np.std(np.asarray(agg.ret_day)[:12], ddof=1))
    assert builder._samples
    for row in builder._samples:
        assert abs(row[2] - expected) < 1e-12
        assert abs(row[2] - 0.02) > 1e-9


def _panel_portfolio(ex_d):
    return {"aum_ref": 1e10,
            "excess_m": pd.Series([0.01, 0.02, 0.015]),
            "excess_d": pd.Series(ex_d),
            "turnover_m": pd.Series([0.2, 0.2, 0.2]),
            "p_cost": 0.01, "sigma_port": 0.02}


def test_c_gate_falls_back_on_noise(cfg):
    """T2（v3.9.2）：c 标不可识别时，成本回退 c=0.5。"""
    from backtest.execution.shell.panels import build_daily_panels
    fit = {"primary": "sqrt", "params": {"c": 15.0},
           "sigma_median": 0.005, "identifiable": False,
           "cv_rmse": {}, "tied": ["sqrt"]}
    daily = build_daily_panels(cfg, None, _panel_portfolio([0.01, -0.01] * 50),
                               impact_fit=fit)
    assert daily["impact_bps_source"] == "default_fallback"
    assert daily["cost_by_h"][20] == pytest.approx(8e6)
    assert any("c 不可识别" in w for w in daily["evidence_warnings"])


def test_rho_uses_daily_series(cfg):
    """T4（v3.9.2）：rho 来自日频序列，并带频率元数据。"""
    from backtest.execution.shell.panels import build_daily_panels
    ex_d = list(np.random.default_rng(3).normal(0.0005, 0.01, 120))
    daily = build_daily_panels(cfg, None, _panel_portfolio(ex_d))
    assert daily["rho_freq"] == "daily"
    assert daily["rho_n"] == len(ex_d)
    assert daily["rho_series"] == [float(v) for v in ex_d]


def test_rho_nonpositive_falls_back(cfg):
    """T5（v3.9.2）：rho<=0 回退 1.0，retention 不再符号翻转。"""
    from backtest.execution.shell.panels import build_daily_panels
    daily = build_daily_panels(cfg, None, _panel_portfolio([0.01, -0.01] * 50))
    assert daily["rho"] == 1.0
    assert any("无衰减" in w for w in daily["evidence_warnings"])


def test_temporary_basis_flagged(cfg):
    """T6（v3.9.2）：temporary 标注为组合 AR(1) 代理，不进入容量。"""
    from backtest.execution.shell.panels import build_daily_panels
    daily = build_daily_panels(cfg, None, _panel_portfolio([0.01, -0.01] * 50))
    assert daily["temporary_basis"] == "portfolio_ar1_proxy"
    assert any("非 T+1" in w for w in daily["evidence_warnings"])


def test_daily_panels_emit_decay_matrix(cfg):
    """T393-10: 校准分支输出衰减 A 矩阵；无 a_by_period 时不写新键。"""
    from backtest.execution.shell.panels import build_daily_panels
    portfolio = _panel_portfolio([0.01, -0.01] * 50)
    rows = [[float(h) * 1e-3 for h in range(1, 61)],
            [float(h) * 2e-3 for h in range(1, 61)],
            [np.nan] * 60]
    portfolio["a_by_period"] = rows
    daily = build_daily_panels(cfg, None, portfolio)
    assert daily["decay_h_max"] == 60
    assert daily["decay_a_by_period"][0][:3] == [1e-3, 2e-3, 3e-3]
    assert daily["decay_a_by_period"][2][0] is None
    assert daily["alpha0_anchored"] == pytest.approx(0.03)

    plain = build_daily_panels(cfg, None,
                               _panel_portfolio([0.01, -0.01] * 50))
    for key in ("decay_a_by_period", "decay_h_max", "alpha0_anchored"):
        assert key not in plain
