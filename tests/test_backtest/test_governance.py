# -*- coding: utf-8 -*-
"""GR-1 治理记录与存储 — T1-T10 (v3.6.0 E1).

TDD 顺序：本文件先于 backtest/governance.py 落地；首次运行应为红
（ModuleNotFoundError: No module named 'factor_pipeline.backtest.governance'）。

覆盖 EXECUTION_V3.6.0_GOVERNANCE_BASE.md §5.1：
  T1 record_id 确定性 / T2 身份敏感性 / T3 易变字段不影响
  T4 stage 必填 / T5 production 门禁 / T6 roundtrip
  T7 幂等 / T8 冲突 / T9 query-latest / T10 JSONL fallback
"""
import sys

import pytest
from pydantic import ValidationError

from factor_pipeline.backtest.governance import (
    GovernanceRecord,
    GovernanceStore,
    ReproducibilityConflictError,
    Stage,
    compute_payload_hash,
    compute_record_id,
    ID_FIELDS,
)


# ============================================================
# fixtures
# ============================================================

def _gate(name: str = "G0", passed: bool = True) -> dict:
    return {
        "passed": passed,
        "reasons": [] if passed else ["synthetic"],
        "action": "allow" if passed else "block",
        "evidence_refs": [],
        "evaluated_by": "script",
    }


def base_fields(**overrides) -> dict:
    """合法的 S1 记录字段（research）。"""
    fields = dict(
        batch_id="batch_20261117_00000001",
        experiment_id="exp_20261117_00000001",
        factor_id="turnover_1m",
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
    fields.update(overrides)
    return fields


def s3_fields(**overrides) -> dict:
    """合法的 S3 记录字段（含效应量/CI/三分母）。"""
    fields = base_fields(
        stage="S3",
        effect_metric="lambda_mean",
        effect_size=0.01,
        ci=(0.0, 0.02),
        n_trials=3,
        n_testable=3,
        n_hypotheses=2,
        test_family="fam_a",
        correction_method="benjamini_hochberg",
        p_value=0.01,
        q_value=0.02,
    )
    fields.update(overrides)
    return fields


def _all_gates() -> dict:
    return {
        name: _gate(name)
        for name in ("G0", "G1", "G2", "G3", "G3.5", "G4", "G5")
    }


# ============================================================
# T1-T3 record_id
# ============================================================

def test_t1_record_id_deterministic():
    id_fields = {k: "v_%s" % k for k in ID_FIELDS}
    ids = {compute_record_id(id_fields) for _ in range(1000)}
    assert len(ids) == 1

    r1 = GovernanceRecord.build(**base_fields())
    r2 = GovernanceRecord.build(**base_fields())
    assert r1.record_id == r2.record_id


def test_t2_record_id_sensitive_to_every_identity_field():
    id_fields = {k: "v_%s" % k for k in ID_FIELDS}
    baseline = compute_record_id(id_fields)
    for key in ID_FIELDS:
        mutated = dict(id_fields)
        mutated[key] = "__mutated__"
        assert compute_record_id(mutated) != baseline, "字段未参与 record_id: %s" % key


def test_t3_volatile_fields_do_not_change_id_or_payload_hash():
    r1 = GovernanceRecord.build(
        **base_fields(),
        timestamp="2026-01-01T00:00:00+00:00",
        reviewer="alice",
        notes="first",
        env_fingerprint={"python": "3.12.10"},
    )
    r2 = GovernanceRecord.build(
        **base_fields(),
        timestamp="2026-02-02T00:00:00+00:00",
        reviewer="bob",
        notes="second",
        env_fingerprint={"python": "3.13.5"},
    )
    assert r1.record_id == r2.record_id
    assert compute_payload_hash(r1.model_dump(mode="json")) == compute_payload_hash(
        r2.model_dump(mode="json")
    )

    # 结果字段改 → id 同、payload_hash 变
    r3 = GovernanceRecord.build(**s3_fields(q_value=0.5))
    r4 = GovernanceRecord.build(**s3_fields(q_value=0.9))
    assert r3.record_id == r4.record_id
    assert compute_payload_hash(r3.model_dump(mode="json")) != compute_payload_hash(
        r4.model_dump(mode="json")
    )


# ============================================================
# T4-T5 stage / mode 条件校验
# ============================================================

def test_t4_stage_required_fields():
    bad_s3 = s3_fields()
    bad_s3.pop("ci")
    with pytest.raises(ValidationError):
        GovernanceRecord.build(**bad_s3)

    bad_s3_ci = s3_fields(ci=(0.5, 0.1))
    with pytest.raises(ValidationError):
        GovernanceRecord.build(**bad_s3_ci)

    bad_s0 = base_fields(stage="S0", test_family="fam_a")
    with pytest.raises(ValidationError):
        GovernanceRecord.build(**bad_s0)


def test_t5_production_requires_all_gates_and_research_rejects_s5():
    partial = base_fields(
        stage="S5",
        mode="production",
        status="active",
        reviewer="alice",
        gate_status={k: _gate(k) for k in ("G0", "G1", "G2", "G3", "G3.5")},
    )
    with pytest.raises(ValidationError):
        GovernanceRecord.build(**partial)

    with pytest.raises(ValidationError):
        GovernanceRecord.build(**base_fields(stage="S5", mode="research"))

    ok = base_fields(
        stage="S5",
        mode="production",
        status="active",
        reviewer="alice",
        gate_status=_all_gates(),
    )
    rec = GovernanceRecord.build(**ok)
    assert rec.stage == Stage.S5
    assert rec.mode.value == "production"


# ============================================================
# T6 roundtrip
# ============================================================

def test_t6_record_roundtrip():
    rec = GovernanceRecord.build(**s3_fields())
    payload = rec.model_dump(mode="json")
    again = GovernanceRecord.model_validate(payload)
    assert again == rec


# ============================================================
# T7-T10 store
# ============================================================

def test_t7_store_idempotent(tmp_path):
    store = GovernanceStore(db_path=str(tmp_path / "gov.duckdb"))
    try:
        r1 = GovernanceRecord.build(**base_fields())
        r2 = GovernanceRecord.build(**base_fields())
        assert store.append(r1) is True
        assert store.append(r2) is False
        assert len(store.query()) == 1
        assert store.get(r1.record_id) == r1
    finally:
        store.close()


def test_t7b_append_many_batch(tmp_path):
    """批量写入只走 INSERT ... SELECT；批内重复保留首条。"""
    store = GovernanceStore(db_path=str(tmp_path / "gov.duckdb"))
    try:
        r1 = GovernanceRecord.build(**base_fields(factor_id="alpha"))
        r2 = GovernanceRecord.build(**s3_fields(factor_id="beta"))
        assert store.append_many([r1, r2, r1]) == 2
        assert len(store.query()) == 2
        assert store.append_many([r1, r2]) == 0
    finally:
        store.close()


def test_t8_store_conflict_and_keep_first(tmp_path):
    db = str(tmp_path / "gov.duckdb")
    store = GovernanceStore(db_path=db)
    try:
        r1 = GovernanceRecord.build(**s3_fields(q_value=0.02))
        r2 = GovernanceRecord.build(**s3_fields(q_value=0.90))
        assert r1.record_id == r2.record_id
        assert store.append(r1) is True
        with pytest.raises(ReproducibilityConflictError):
            store.append(r2)
        assert len(store.query()) == 1
    finally:
        store.close()

    keep = GovernanceStore(db_path=db, on_conflict="keep_first")
    try:
        assert keep.append(GovernanceRecord.build(**s3_fields(q_value=0.90))) is False
        assert len(keep.query()) == 1
    finally:
        keep.close()


def test_t9_query_and_latest(tmp_path):
    store = GovernanceStore(db_path=str(tmp_path / "gov.duckdb"))
    try:
        a1 = GovernanceRecord.build(
            **base_fields(factor_id="alpha", timestamp="2026-01-01T00:00:00+00:00")
        )
        a3 = GovernanceRecord.build(
            **s3_fields(factor_id="alpha", timestamp="2026-01-03T00:00:00+00:00")
        )
        b1 = GovernanceRecord.build(
            **base_fields(factor_id="beta", timestamp="2026-01-02T00:00:00+00:00")
        )
        for r in (a1, a3, b1):
            assert store.append(r) is True

        assert len(store.query(factor_id="alpha")) == 2
        assert len(store.query(factor_id="beta")) == 1
        assert len(store.query_records(factor_id="alpha", stage=Stage.S1)) == 1

        latest_alpha = store.latest("alpha")
        assert latest_alpha is not None
        assert latest_alpha.record_id == a3.record_id
        latest_s1 = store.latest("alpha", Stage.S1)
        assert latest_s1 is not None
        assert latest_s1.record_id == a1.record_id
        assert store.latest("missing") is None
    finally:
        store.close()


def test_t10_jsonl_fallback_semantics(tmp_path, monkeypatch):
    path = str(tmp_path / "gov.jsonl")
    store = GovernanceStore(db_path=path, backend="jsonl")
    try:
        r1 = GovernanceRecord.build(**base_fields())
        r3 = GovernanceRecord.build(**s3_fields())
        assert store.append(r1) is True
        assert store.append(r3) is True
        assert store.append(r1) is False  # 幂等
        assert len(store.query()) == 2
        assert store.get(r1.record_id) == r1
        assert {r.record_id for r in store.query_records()} == {r1.record_id, r3.record_id}
    finally:
        store.close()

    # 无 duckdb 环境下 JSONL backend 仍可用（lazy import）
    monkeypatch.setitem(sys.modules, "duckdb", None)
    store2 = GovernanceStore(db_path=path, backend="jsonl")
    try:
        assert len(store2.query()) == 2
    finally:
        store2.close()
