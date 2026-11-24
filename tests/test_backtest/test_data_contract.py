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
    default_fields,
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


# ============================================================
# T49 known_gaps 码与 §5.7.4 词汇表对齐（barra_stale / industry_stale）
# ============================================================

def test_t49_known_gap_codes_match_design_vocabulary(tmp_path):
    close = _panel(pd.bdate_range("2026-01-26", "2026-01-30"),
                   ["000001", "000002"])
    _write_pickle(tmp_path, "close.pkl", close)

    fields = [
        FieldSpec("price", "close.pkl", max_lag=0),
        FieldSpec("barra", "barra.pkl", max_lag=None, required=False,
                  missing_semantics="known_gap"),
        FieldSpec("industry", None, reader="industry", max_lag=None,
                  required=False, missing_semantics="known_gap"),
        FieldSpec("volume", "volume.pkl", required=False,
                  missing_semantics="warn"),
    ]
    calendar = pd.bdate_range("2026-01-26", "2026-01-30")
    report = check_data_contract(
        str(tmp_path), sample_end="2026-01-30",
        fields=fields, trading_calendar=calendar,
    )

    assert report.passed is True
    codes = {gap.code for gap in report.known_gaps}
    assert "barra_stale" in codes, codes
    assert "industry_stale" in codes, codes
    assert all(c.severity != "block" for c in report.blocking())


# ============================================================
# T50 adj_alignment 严重度随 mode（research=warn / production=block）
# ============================================================

def test_t50_adj_alignment_severity_follows_mode(tmp_path):
    dates = pd.bdate_range("2026-01-26", "2026-01-30")
    close = _panel(dates, ["000001", "000002"])
    adj = _panel(dates[:3], ["000001", "000002"], value=1.0)
    _write_pickle(tmp_path, "close.pkl", close)
    _write_pickle(tmp_path, "adj.pkl", adj)

    fields = [
        FieldSpec("price", "close.pkl", max_lag=0),
        FieldSpec("adj", "adj.pkl", semantic_type="adj_factor",
                  max_lag=5, required=False),
    ]
    calendar = dates

    default = check_data_contract(
        str(tmp_path), sample_end="2026-01-30",
        fields=fields, trading_calendar=calendar,
    )
    research = check_data_contract(
        str(tmp_path), sample_end="2026-01-30",
        fields=fields, trading_calendar=calendar, mode="research",
    )
    production = check_data_contract(
        str(tmp_path), sample_end="2026-01-30",
        fields=fields, trading_calendar=calendar, mode="production",
    )

    assert default.passed is True
    assert research.passed is True
    assert any(
        c.check == "adj_alignment" and c.severity == "warn"
        for c in research.checks
    )

    assert production.passed is False
    blocking = [c for c in production.blocking() if c.check == "adj_alignment"]
    assert blocking, "production 下 adj_alignment 未升级为 block"
    assert all(c.severity == "block" for c in blocking)

    with pytest.raises(ValueError):
        check_data_contract(
            str(tmp_path), sample_end="2026-01-30",
            fields=fields, trading_calendar=calendar, mode="magic",
        )


# ============================================================
# T53 known_gap 码名集中映射（修复包 F3 / 复审 R3）
# ============================================================

def test_t53_gap_code_mapping_centralized(tmp_path):
    from factor_pipeline.backtest.data_contract import GAP_CODE_BY_FIELD

    assert GAP_CODE_BY_FIELD["barra"] == "barra_stale"
    assert GAP_CODE_BY_FIELD["industry"] == "industry_stale"

    # 映射外字段回退 <name>_missing（兜底语义不变）
    close = _panel(pd.bdate_range("2026-01-26", "2026-01-30"), ["000001"])
    _write_pickle(tmp_path, "close.pkl", close)
    fields = [
        FieldSpec("price", "close.pkl", max_lag=0),
        FieldSpec("delist", "delist.pkl", required=False,
                  missing_semantics="known_gap"),
    ]
    report = check_data_contract(
        str(tmp_path), sample_end="2026-01-30",
        fields=fields,
        trading_calendar=pd.bdate_range("2026-01-26", "2026-01-30"),
    )
    codes = {gap.code for gap in report.known_gaps}
    assert "delist_missing" in codes, codes
    assert report.passed is True


# ============================================================
# T16-T19 return 单位口径（P-025）
# ============================================================

def _consistency_checks(report):
    return [c for c in report.checks if c.check == "consistency"]


def _return_report(tmp_path, values, unit):
    dates = pd.bdate_range("2026-01-01", periods=len(values))
    frame = pd.DataFrame({"s": values}, index=dates)
    _write_pickle(tmp_path, "return.pkl", frame)
    fields = [FieldSpec(
        "return", "return.pkl", max_lag=1, required=False,
        semantic_type="return", unit=unit, expected_missing_tail=1,
    )]
    return check_data_contract(
        str(tmp_path), sample_end=dates[-1], fields=fields,
        trading_calendar=dates,
    )


def test_t16_return_percent_normal_values_pass(tmp_path):
    values = [
        -30.0, -20.0, -10.0, -5.0, 0.0, 5.0,
        10.0, 20.0, 30.0, 100.0, -100.0, 1000.0,
    ]
    report = _return_report(tmp_path, values, unit="%")

    checks = _consistency_checks(report)
    assert checks, "consistency 检查缺失"
    assert all(c.passed for c in checks), [c.message for c in checks]


def test_t17_return_percent_dirty_value_warns(tmp_path):
    report = _return_report(tmp_path, [20.0, -20.0, 200400.0], unit="%")

    failed = [c for c in _consistency_checks(report) if not c.passed]
    assert len(failed) == 1
    assert failed[0].severity == "warn"
    assert "越界" in failed[0].message
    assert failed[0].details.get("unit") == "%"
    assert failed[0].details.get("bounds") == [-100.0, 1000.0]


@pytest.mark.parametrize("unit", [None, "decimal"])
def test_t18_return_decimal_behavior_unchanged(tmp_path, unit):
    report = _return_report(tmp_path, [0.2, -0.2, 20.0], unit=unit)

    failed = [c for c in _consistency_checks(report) if not c.passed]
    assert len(failed) == 1, [c.message for c in _consistency_checks(report)]
    assert "越界" in failed[0].message
    assert failed[0].details.get("bounds") == [-1.0, 10.0]


def test_t19_default_return_unit_and_unknown_fallback(tmp_path):
    returns = [s for s in default_fields() if s.name == "return"]
    assert returns, "default_fields 缺少 return"
    assert returns[0].unit == "%"

    report = _return_report(tmp_path, [20.0, 19.0, 18.0], unit="ratio")
    failed = [c for c in _consistency_checks(report) if not c.passed]
    assert len(failed) == 1
    assert "越界" in failed[0].message
    assert failed[0].details.get("unit") == "ratio"
    assert failed[0].details.get("bounds") == [-1.0, 10.0]
