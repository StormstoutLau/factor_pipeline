# -*- coding: utf-8 -*-
"""GR-2 数据契约 — T11-T15 (v3.6.0 E2).

先于 backtest/data_contract.py 落地；首次运行应为红
（ModuleNotFoundError: No module named 'factor_pipeline.backtest.data_contract'）。

覆盖 EXECUTION_V3.6.0_GOVERNANCE_BASE.md §5.1：
  T11 mv 5 日缺口拦截 / T12 正常数据 0 block
  T13 PIT 违规 block、list_date 缺失 warn / T14 可选缺失 warn
  T15 缓存命中不重复读盘 + 内容摘要不受 mtime 影响
"""
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from factor_pipeline.backtest.data_contract import (
    ContractCache,
    FieldSpec,
    check_data_contract,
)


# ============================================================
# helpers
# ============================================================

def _panel(index, columns, value=1.0):
    return pd.DataFrame(
        np.full((len(index), len(columns)), value),
        index=pd.DatetimeIndex(index),
        columns=list(columns),
    )


def _write_pickle(root: Path, name: str, obj) -> Path:
    path = root / name
    pd.to_pickle(obj, path)
    return path


def _write_csv(root: Path, name: str, frame: pd.DataFrame) -> Path:
    path = root / name
    frame.to_csv(path)
    return path


# ============================================================
# T11 mv 5 日缺口拦截
# ============================================================

def test_t11_mv_gap_is_blocked(tmp_path):
    close = _panel(pd.bdate_range("2026-01-26", "2026-01-30"),
                   ["000001", "000002", "600000", "600001"])
    mv = _panel(pd.bdate_range("2026-01-19", "2026-01-23"),
                ["000001", "000002", "600000", "600001"], value=1e9)
    _write_pickle(tmp_path, "close.pkl", close)
    _write_csv(tmp_path, "mv.csv", mv)

    fields = [
        FieldSpec("price", "close.pkl", max_lag=0),
        FieldSpec("mv", "mv.csv", reader="csv", max_lag=1),
    ]
    calendar = pd.bdate_range("2026-01-19", "2026-01-30")
    report = check_data_contract(
        str(tmp_path), sample_end="2026-01-30",
        fields=fields, trading_calendar=calendar,
    )

    assert report.passed is False
    blocking = report.blocking()
    assert blocking, "mv 5 日缺口未被拦截"
    fresh = [c for c in blocking if c.check == "freshness"]
    assert fresh, "block 中缺少 freshness: %s" % [c.check for c in blocking]
    assert any("mv" in c.message for c in fresh)
    assert all(c.severity == "block" for c in blocking)


# ============================================================
# T12 正常数据通过（单股停牌不误判）
# ============================================================

def test_t12_normal_data_passes(tmp_path):
    stocks = ["s%02d" % i for i in range(20)]
    dates = pd.bdate_range("2026-01-26", "2026-01-30")
    close = _panel(dates, stocks)
    close.iloc[-1, 0] = np.nan  # 单股末日停牌 → 覆盖率 19/20 = 0.95
    mv = _panel(dates, stocks, value=1e9)
    _write_pickle(tmp_path, "close.pkl", close)
    _write_csv(tmp_path, "mv.csv", mv)

    fields = [
        FieldSpec("price", "close.pkl", max_lag=0, min_coverage=0.95),
        FieldSpec("mv", "mv.csv", reader="csv", max_lag=1),
    ]
    report = check_data_contract(
        str(tmp_path), sample_end="2026-01-30",
        fields=fields,
        trading_calendar=pd.bdate_range("2026-01-19", "2026-01-30"),
    )

    assert report.passed is True, report.to_markdown()
    assert report.blocking() == []


# ============================================================
# T13 PIT 违规 / list_date 缺失
# ============================================================

def test_t13_pit_violation_blocks_and_missing_list_date_warns(tmp_path):
    dates = pd.bdate_range("2026-01-01", "2026-01-05")
    close = _panel(dates, ["000001", "000002"])
    _write_pickle(tmp_path, "close.pkl", close)

    fields = [FieldSpec("price", "close.pkl", pit_required=True)]
    calendar = pd.bdate_range("2026-01-01", "2026-01-05")

    list_date = pd.Series(
        {"000001": pd.Timestamp("2026-01-03"),
         "000002": pd.Timestamp("2026-01-01")}
    )
    bad = check_data_contract(
        str(tmp_path), sample_end="2026-01-05", fields=fields,
        trading_calendar=calendar, list_date=list_date,
    )
    assert bad.passed is False
    assert any(c.check == "pit" and c.severity == "block" for c in bad.blocking())

    missing = check_data_contract(
        str(tmp_path), sample_end="2026-01-05", fields=fields,
        trading_calendar=calendar, list_date=None,
    )
    assert missing.passed is True
    assert any(
        c.check == "pit" and c.severity == "warn" for c in missing.checks
    )


# ============================================================
# T14 可选字段缺失 → warn 不 block
# ============================================================

def test_t14_optional_missing_warns_not_blocks(tmp_path):
    dates = pd.bdate_range("2026-01-26", "2026-01-30")
    _write_pickle(tmp_path, "close.pkl", _panel(dates, ["000001", "000002"]))

    fields = [
        FieldSpec("price", "close.pkl", max_lag=0),
        FieldSpec("volume", "volume.pkl", max_lag=0, required=False),
        FieldSpec("suspend", "suspend.pkl", max_lag=1, required=False),
    ]
    report = check_data_contract(
        str(tmp_path), sample_end="2026-01-30", fields=fields,
        trading_calendar=pd.bdate_range("2026-01-26", "2026-01-30"),
    )

    assert report.passed is True, report.to_markdown()
    assert report.blocking() == []
    warned = [c for c in report.warnings() if "不存在" in c.message]
    assert len(warned) >= 2
    assert {c.details.get("field") for c in warned} >= {"volume", "suspend"}


# ============================================================
# T15 缓存命中 / content_digest 对 mtime 不变
# ============================================================

class _CountingReader:
    def __init__(self):
        self.calls = 0

    def read(self, root, spec):
        self.calls += 1
        return pd.read_pickle(Path(root) / spec.file)


def test_t15_cache_hit_and_mtime_invariance(tmp_path):
    dates = pd.bdate_range("2026-01-26", "2026-01-30")
    path = _write_pickle(tmp_path, "close.pkl", _panel(dates, ["000001", "000002"]))
    fields = [FieldSpec("price", "close.pkl", reader="counting", max_lag=0)]
    calendar = pd.bdate_range("2026-01-26", "2026-01-30")
    reader = _CountingReader()
    cache = ContractCache()

    first = check_data_contract(
        str(tmp_path), sample_end="2026-01-30", fields=fields,
        trading_calendar=calendar, cache=cache, readers={"counting": reader},
    )
    assert reader.calls == 1
    digest = first.snapshot.fields["price"].content_digest
    stable = first.snapshot.stable_hash()

    second = check_data_contract(
        str(tmp_path), sample_end="2026-01-30", fields=fields,
        trading_calendar=calendar, cache=cache, readers={"counting": reader},
    )
    assert reader.calls == 1, "缓存未命中：reader 被重复调用"
    assert second.snapshot.fields["price"].content_digest == digest

    # mtime 变、内容不变 → 新缓存重读，但 digest 与 stable_hash 不变
    stat = os.stat(path)
    os.utime(path, (stat.st_atime + 10, stat.st_mtime + 10))
    third = check_data_contract(
        str(tmp_path), sample_end="2026-01-30", fields=fields,
        trading_calendar=calendar, cache=ContractCache(),
        readers={"counting": reader},
    )
    assert reader.calls == 2
    assert third.snapshot.fields["price"].content_digest == digest
    assert third.snapshot.stable_hash() == stable
