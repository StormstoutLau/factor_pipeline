# -*- coding: utf-8 -*-
"""治理底座补充用例 — T33-T45 (v3.6.0).

覆盖 EXECUTION_V3.6.0_GOVERNANCE_BASE.md §5.2：
  T33 模块隔离（AST 扫描，四模块互不 import）
  T34 旧 schema 读取（更旧补默认 + legacy=True；更新原样 dict + warning）
  T35 content_digest（mtime 不变、内容敏感）
  T36 缓存防陈旧（copy2 保留 mtime 仍按头部摘要识别内容）
  T37 expected_missing_tail（forward return 末行缺失不算 freshness 缺口）
  T38 NaN 率守卫（actual 比 baseline 多 2% → FAIL）
  T41 ancestors（循环 → 异常；断链 → broken_link 条目）
  T42 gate_status 未知键 → 拒绝
  T43 时间字段均为带时区 UTC ISO
  T44 jsonl lock_path 获取/释放 + 并发线程无交错
  T45 bootstrap 注入点签名默认 None
"""
import ast
import inspect
import json
import logging
import os
import shutil
import threading
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from factor_pipeline.backtest.data_contract import (
    ContractCache,
    FieldSpec,
    build_snapshot,
    check_data_contract,
)
from factor_pipeline.backtest.golden_master import GoldenMaster
from factor_pipeline.backtest.governance import (
    GovernanceError,
    GovernanceRecord,
    GovernanceStore,
    canonical_json,
)
from factor_pipeline.backtest.multiple_testing import (
    HansenSPA,
    WhiteRealityCheck,
)
from factor_pipeline.backtest.multiple_testing_ledger import (
    MultipleTestingLedger,
)


# ============================================================
# T33 模块隔离
# ============================================================

_MODULES = (
    "governance",
    "data_contract",
    "golden_master",
    "multiple_testing_ledger",
)


def _import_strings(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                yield node.module
            for alias in node.names:
                target = alias.name if not node.module else "%s.%s" % (
                    node.module, alias.name)
                yield target


def test_t33_module_isolation():
    root = Path(__file__).resolve().parents[2] / "backtest"
    for name in _MODULES:
        path = root / ("%s.py" % name)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for target in _import_strings(tree):
            parts = target.split(".")
            for other in _MODULES:
                if other == name:
                    continue
                assert other not in parts, (
                    "%s.py 不得 import %s（D1 模块隔离）: %s"
                    % (name, other, target)
                )


# ============================================================
# T34 旧 schema 读取
# ============================================================

def _gate(name: str = "G0") -> dict:
    return {
        "passed": True,
        "reasons": [],
        "action": "allow",
        "evidence_refs": [],
        "evaluated_by": "script",
    }


def _base_fields(factor_id: str) -> dict:
    return dict(
        batch_id="batch_20261117_00000001",
        experiment_id="exp_20261117_00000001",
        factor_id=factor_id,
        stage="S1",
        mode="research",
        pipeline_version="3.6.0",
        config_hash="cfg_hash",
        construction_code_hash="code_hash",
        data_snapshot={"as_of": "2026-11-17T00:00:00+00:00", "fields": {}},
        data_snapshot_hash="snap_hash",
        sample_window={"start": "2020-01-31", "end": "2025-12-31"},
        benchmark_id="csi300",
        return_convention="close_to_close",
        tradable_convention={"exclude_st": True},
        cost_model={"bps": 10.0},
        sign_convention="positive",
        gate_status={"G0": _gate()},
    )


def test_t34_legacy_schema_read(tmp_path, caplog):
    old_record = GovernanceRecord.build(**_base_fields("legacy_factor"))
    old_payload = old_record.model_dump(mode="json")
    old_payload["schema_version"] = "0.9.0"
    old_payload.pop("gate_policy_version", None)
    old_payload.pop("construction_version_known", None)
    old_payload["legacy_note"] = "kept"

    new_record = GovernanceRecord.build(**_base_fields("future_factor"))
    new_payload = new_record.model_dump(mode="json")
    new_payload["schema_version"] = "9.9.9"
    new_payload["future_field"] = {"x": 1}

    path = tmp_path / "governance.jsonl"
    path.write_text(
        canonical_json(old_payload) + "\n" + canonical_json(new_payload) + "\n",
        encoding="utf-8",
    )
    store = GovernanceStore(db_path=str(path), backend="jsonl")

    with caplog.at_level(logging.WARNING):
        got_old = store.get(old_payload["record_id"])
        got_new = store.get(new_payload["record_id"])

    assert isinstance(got_old, GovernanceRecord)
    assert got_old.factor_id == "legacy_factor"
    assert getattr(got_old, "legacy", False) is True
    assert got_old.model_extra.get("legacy_note") == "kept"

    assert isinstance(got_new, dict)
    assert got_new["schema_version"] == "9.9.9"
    assert got_new["future_field"] == {"x": 1}
    assert any("9.9.9" in message for message in caplog.messages)


# ============================================================
# T35 content_digest
# ============================================================

def _write_panel(path: Path, frame: pd.DataFrame) -> None:
    frame.to_csv(path)


def test_t35_content_digest_mtime_insensitive(tmp_path):
    dates = pd.date_range("2024-01-31", periods=12, freq="ME")
    frame = pd.DataFrame(
        {"S1": np.arange(12, dtype=float)},
        index=dates,
    )
    first = tmp_path / "a.csv"
    second = tmp_path / "b.csv"
    _write_panel(first, frame)
    _write_panel(second, frame)
    os.utime(first, (1_600_000_000, 1_600_000_000))
    os.utime(second, (1_700_000_000, 1_700_000_000))

    calendar = pd.DatetimeIndex(dates)
    snap_a = build_snapshot(
        tmp_path, "2024-12-31",
        fields=[FieldSpec(name="price", file="a.csv", reader="csv")],
        trading_calendar=calendar,
    )
    snap_b = build_snapshot(
        tmp_path, "2024-12-31",
        fields=[FieldSpec(name="price", file="b.csv", reader="csv")],
        trading_calendar=calendar,
    )
    assert (snap_a.fields["price"].content_digest
            == snap_b.fields["price"].content_digest)

    changed = frame.copy()
    changed.iloc[0, 0] += 1.0
    _write_panel(second, changed)
    snap_c = build_snapshot(
        tmp_path, "2024-12-31",
        fields=[FieldSpec(name="price", file="b.csv", reader="csv")],
        trading_calendar=calendar,
    )
    assert (snap_c.fields["price"].content_digest
            != snap_a.fields["price"].content_digest)


# ============================================================
# T36 缓存防陈旧（copy2 保留 mtime）
# ============================================================

class _CountingReader:
    def __init__(self):
        self.calls = 0

    def read(self, root, spec):
        self.calls += 1
        return pd.read_csv(root / spec.file, index_col=0, parse_dates=True)


def test_t36_cache_head_digest_guards_copy2(tmp_path):
    dates = pd.date_range("2024-01-31", periods=12, freq="ME")
    calendar = pd.DatetimeIndex(dates)
    frame = pd.DataFrame({"S1": np.arange(1.0, 13.0)}, index=dates)
    target = tmp_path / "price.csv"
    backup = tmp_path / "price_backup.csv"
    frame.to_csv(target)
    shutil.copy2(target, backup)

    cache = ContractCache()
    reader = _CountingReader()
    spec = FieldSpec(name="price", file="price.csv", reader="csv", max_lag=0)
    first = check_data_contract(
        tmp_path, "2024-12-31", fields=[spec], cache=cache,
        trading_calendar=calendar, readers={"csv": reader},
    )
    assert reader.calls == 1
    first_digest = first.snapshot.fields["price"].content_digest

    # copy2 恢复原文件（内容 + mtime 均保留）→ 同一 key，缓存命中
    shutil.copy2(backup, target)
    second = check_data_contract(
        tmp_path, "2024-12-31", fields=[spec], cache=cache,
        trading_calendar=calendar, readers={"csv": reader},
    )
    assert reader.calls == 1
    assert second.snapshot.fields["price"].content_digest == first_digest

    # 同 size、同 mtime，仅首 64KB 内容变化 → 头部摘要识别，缓存失效
    original = target.stat()
    stale = frame.copy()
    stale.iloc[0, 0] = 9.0
    stale_path = tmp_path / "price_stale.csv"
    stale.to_csv(stale_path)
    assert stale_path.stat().st_size == original.st_size
    os.utime(stale_path, ns=(original.st_atime_ns, original.st_mtime_ns))
    shutil.copy2(stale_path, target)
    os.utime(target, ns=(original.st_atime_ns, original.st_mtime_ns))
    assert target.stat().st_mtime_ns == original.st_mtime_ns
    assert target.stat().st_size == original.st_size

    third = check_data_contract(
        tmp_path, "2024-12-31", fields=[spec], cache=cache,
        trading_calendar=calendar, readers={"csv": reader},
    )
    assert reader.calls == 2
    assert third.snapshot.fields["price"].content_digest != first_digest


# ============================================================
# T37 expected_missing_tail
# ============================================================

def test_t37_expected_missing_tail_not_freshness_gap(tmp_path):
    dates = pd.date_range("2024-01-31", periods=12, freq="ME")
    calendar = pd.DatetimeIndex(dates)
    frame = pd.DataFrame({"S1": np.arange(12, dtype=float)}, index=dates)
    frame.iloc[-1, 0] = np.nan
    frame.to_csv(tmp_path / "fwd.csv")

    def _freshness(expected_tail):
        spec = FieldSpec(
            name="fwd_return", file="fwd.csv", reader="csv",
            max_lag=0, required=False,
            expected_missing_tail=expected_tail,
        )
        report = check_data_contract(
            tmp_path, "2024-12-31", fields=[spec],
            trading_calendar=calendar,
        )
        return [c for c in report.checks if c.check == "freshness"][0]

    with_tail = _freshness(1)
    assert with_tail.passed is True
    assert with_tail.details["lag"] == 0
    assert with_tail.details["raw_lag"] == 1

    without_tail = _freshness(0)
    assert without_tail.passed is False
    assert without_tail.details["lag"] == 1


# ============================================================
# T38 NaN 率守卫
# ============================================================

def test_t38_nan_rate_guard(tmp_path):
    dates = pd.date_range("2024-01-31", periods=12, freq="ME")
    columns = ["S%02d" % i for i in range(10)]
    baseline = pd.DataFrame(
        np.arange(120, dtype=float).reshape(12, 10),
        index=dates, columns=columns,
    )
    master = GoldenMaster(root=str(tmp_path / "golden"))
    master.capture(
        "nan_guard", {"f1": baseline},
        {"pipeline_version": "3.6.0", "generator": "test_t38"},
    )

    actual = baseline.copy()
    actual.iloc[0, 0] = np.nan
    actual.iloc[0, 1] = np.nan
    actual.iloc[0, 2] = np.nan
    report = master.compare("nan_guard", {"f1": actual})
    assert report.nan_rate_guard_triggered is True
    assert report.verdict == "FAIL"
    assert report.n_actual_nan > report.n_baseline_nan


# ============================================================
# T41 ancestors：断链 broken_link / 循环异常
# ============================================================

def test_t41_ancestors_broken_link_and_cycle(tmp_path):
    path = tmp_path / "governance.jsonl"
    store = GovernanceStore(db_path=str(path), backend="jsonl")

    root = GovernanceRecord.build(**_base_fields("root_factor"))
    child = GovernanceRecord.build(
        **{**_base_fields("child_factor"), "parent_id": root.record_id})
    store.append(root)
    store.append(child)

    entries = store.ancestors(child.record_id)
    assert [getattr(e, "record_id", None) for e in entries] == [
        child.record_id, root.record_id,
    ]
    assert all(e.broken_link is False for e in entries)
    assert all(e.record is not None for e in entries)

    missing_parent = "0" * 64
    orphan = GovernanceRecord.build(
        **{**_base_fields("orphan_factor"), "parent_id": missing_parent})
    store.append(orphan)

    orphan_entries = store.ancestors(orphan.record_id)
    assert len(orphan_entries) == 2
    assert orphan_entries[0].broken_link is False
    assert orphan_entries[-1].record_id == missing_parent
    assert orphan_entries[-1].record is None
    assert orphan_entries[-1].broken_link is True
    assert orphan_entries[-1].reason == "missing"

    # 循环：A → B → A；用 model_copy 构造互指 parent（仅测循环检测）
    a0 = GovernanceRecord.build(**_base_fields("cycle_a"))
    b0 = GovernanceRecord.build(**_base_fields("cycle_b"))
    a = a0.model_copy(update={"parent_id": b0.record_id})
    b = b0.model_copy(update={"parent_id": a0.record_id})
    mapping = {a.record_id: a, b.record_id: b}
    store.get = lambda rid: mapping.get(rid)  # type: ignore[assignment]
    with pytest.raises(GovernanceError):
        store.ancestors(a.record_id)


# ============================================================
# T42 gate_status 未知键拒绝
# ============================================================

def test_t42_unknown_gate_key_rejected():
    with pytest.raises(ValidationError):
        GovernanceRecord.build(
            **{**_base_fields("bad_gate"), "gate_status": {"G9": _gate()}},
        )


# ============================================================
# T43 时间字段带时区 UTC ISO
# ============================================================

def test_t43_time_fields_utc_iso():
    naive = GovernanceRecord.build(
        **_base_fields("tz_naive"),
        holdout_locked_at="2024-01-31 08:00:00",
    )
    assert naive.timestamp.endswith("+00:00")
    assert naive.holdout_locked_at == "2024-01-31T08:00:00+00:00"

    shanghai = GovernanceRecord.build(
        **_base_fields("tz_sh"),
        holdout_locked_at="2024-01-31T08:00:00+08:00",
    )
    assert shanghai.holdout_locked_at == "2024-01-31T00:00:00+00:00"
    payload = shanghai.model_dump(mode="json")
    assert payload["timestamp"].endswith("+00:00")
    assert payload["holdout_locked_at"].endswith("+00:00")


# ============================================================
# T44 jsonl lock_path：并发线程无交错
# ============================================================

def test_t44_jsonl_lock_path_concurrent_append(tmp_path):
    path = tmp_path / "governance.jsonl"
    lock_path = tmp_path / "locks" / "governance.lock"
    store = GovernanceStore(
        db_path=str(path), backend="jsonl", lock_path=str(lock_path))

    records = [
        GovernanceRecord.build(**_base_fields("lock_factor_%02d" % i))
        for i in range(40)
    ]

    def _worker(chunk):
        for record in chunk:
            store.append(record)

    threads = [
        threading.Thread(target=_worker, args=(records[i::4],))
        for i in range(4)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert lock_path.exists()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(records)

    seen = set()
    for line in lines:
        payload = json.loads(line)
        assert payload["record_id"] not in seen
        seen.add(payload["record_id"])
    assert seen == {record.record_id for record in records}


# ============================================================
# T45 bootstrap 注入点签名默认 None（零变更）
# ============================================================

def test_t45_bootstrap_injection_defaults_none():
    for method in (WhiteRealityCheck.test, HansenSPA.test):
        signature = inspect.signature(method)
        assert signature.parameters["bootstrap_indices"].default is None

    signature = inspect.signature(MultipleTestingLedger.apply)
    for name in ("bootstrap_p_values", "returns_matrix", "bootstrap_indices"):
        assert signature.parameters[name].default is None
