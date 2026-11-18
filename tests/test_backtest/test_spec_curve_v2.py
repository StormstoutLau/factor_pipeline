# -*- coding: utf-8 -*-
"""v3.7.0 E4 — 规格曲线 v2 测试（T34-T40b，8 项）。

对应 ``docs/EXECUTION_V3.7.0_STAT_EVIDENCE_CHAIN.md`` §4.4 与
``docs/private/DESIGN_STAT_EVIDENCE_CHAIN.md`` §7。
"""
import json
import os
from datetime import datetime

import numpy as np
import pytest

import factor_pipeline.backtest.specification_logger.pre_registration as prereg_mod
from factor_pipeline.backtest.specification_logger import (
    PreRegistration,
    SpecificationLogger,
    joint_inference,
)


def _read_records(tmp_path):
    path = os.path.join(str(tmp_path), "specifications.jsonl")
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_t34_log_run_v2_schema(tmp_path):
    logger = SpecificationLogger(log_dir=str(tmp_path))
    commit_hash = logger.log_run(
        {"lag": 5}, {"ic": 0.04}, factor_name="momentum",
        spec_id="spec_a", values=[0.01, 0.02, 0.03],
        value_type="returns", parent_run_id="parent_1",
        spec={"lag": 5, "neutralize": "industry"},
    )
    assert len(commit_hash) == 8
    rec = _read_records(tmp_path)[0]
    assert rec["schema_version"] == "2"
    assert rec["spec_id"] == "spec_a"
    assert rec["values"] == [0.01, 0.02, 0.03]
    assert rec["value_type"] == "returns"
    assert rec["parent_run_id"] == "parent_1"
    assert len(rec["content_hash"]) == 64
    assert len(rec["commit_hash"]) == 8

    with pytest.raises(ValueError):
        logger.log_run({"lag": 1}, {"ic": 0.1}, spec_id="x",
                       values=[0.1], value_type="unknown")
    with pytest.raises(ValueError):
        logger.log_run({"lag": 1}, {"ic": 0.1}, spec_id="x",
                       values=[0.1, np.nan], value_type="returns")


def test_t35_legacy_record_compatible(tmp_path):
    logger = SpecificationLogger(log_dir=str(tmp_path))
    legacy = {
        "timestamp": "2026-01-01T00:00:00",
        "run_type": "exploratory",
        "factor_name": "legacy",
        "config": {"lag": 3},
        "result": {"ic": 0.02, "p_value": 0.04},
        "commit_hash": "abcd1234",
    }
    path = os.path.join(str(tmp_path), "specifications.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(legacy) + "\n")

    curve = logger.get_specification_curve(factor_name="legacy")
    assert set(curve.keys()) == {
        "specifications", "results", "p_values",
        "median_effect", "consistency",
    }
    matrix = logger.get_specification_matrix(factor_name="legacy")
    assert matrix["values"].shape == (0, 0)
    assert matrix["n_specs"] == 0


def test_t36_matrix_extraction(tmp_path):
    logger = SpecificationLogger(log_dir=str(tmp_path))
    values = list(np.linspace(-0.1, 0.1, 58))
    logger.log_run({"lag": 1}, {"ic": 0.01}, factor_name="f1",
                   spec_id="s1", values=values, value_type="returns")
    logger.log_run({"lag": 2}, {"ic": 0.02}, factor_name="f1",
                   spec_id="s2", values=values, value_type="returns")
    matrix = logger.get_specification_matrix(factor_name="f1")
    assert matrix["values"].shape == (58, 2)
    assert matrix["spec_ids"] == ["s1", "s2"]
    assert matrix["n_periods"] == 58
    assert matrix["n_specs"] == 2
    assert matrix["truncated"] is False

    # 缺 values + strict=True → ValueError（带行号与 spec_id）
    logger.log_run({"lag": 3}, {"ic": 0.03}, factor_name="f2",
                   spec_id="ghost", value_type="returns")
    with pytest.raises(ValueError) as excinfo:
        logger.get_specification_matrix(factor_name="f2", strict=True)
    assert "ghost" in str(excinfo.value)


def test_t37_matrix_truncation(tmp_path):
    logger = SpecificationLogger(log_dir=str(tmp_path))
    long_values = list(np.arange(60, dtype=float))
    short_values = [float(v) + 100.0 for v in np.arange(58)]
    logger.log_run({}, {}, factor_name="f1", spec_id="long",
                   values=long_values, value_type="returns")
    logger.log_run({}, {}, factor_name="f1", spec_id="short",
                   values=short_values, value_type="returns")
    with pytest.raises(ValueError):
        logger.get_specification_matrix(factor_name="f1", strict=True)

    matrix = logger.get_specification_matrix(factor_name="f1", strict=False)
    assert matrix["truncated"] is True
    assert matrix["n_periods"] == 58
    assert matrix["values"].shape == (58, 2)
    assert matrix["values"][:, 0].tolist() == [float(v) for v in long_values[-58:]]
    assert matrix["values"][:, 1].tolist() == [float(v) for v in short_values]


def test_t38_joint_inference_null_effect():
    rng = np.random.default_rng(20261118)
    values = rng.normal(0.0, 0.05, size=(58, 8))
    out = joint_inference(values, effect="mean", n_bootstrap=300, seed=7)
    assert out["method"] == "null_imposed_bootstrap"
    assert len(out["statistics"]) == 3
    for stat in out["statistics"]:
        assert set(stat.keys()) == {
            "name", "estimate", "null_lower", "null_upper",
            "p_value", "n_specs",
        }
        assert stat["p_value"] > 0.05
    names = [s["name"] for s in out["statistics"]]
    assert names == ["median", "share_significant", "aggregated_z"]


def test_t39_joint_inference_strong_effect():
    rng = np.random.default_rng(20261118)
    values = rng.normal(0.0, 0.05, size=(58, 8)) + 0.06
    out = joint_inference(values, effect="mean", n_bootstrap=300, seed=7)
    by_name = {s["name"]: s for s in out["statistics"]}
    assert by_name["median"]["p_value"] < 0.05
    assert by_name["aggregated_z"]["p_value"] < 0.05
    assert by_name["share_significant"]["estimate"] >= 0.5


def test_t40_joint_inference_deterministic():
    rng = np.random.default_rng(31)
    values = rng.normal(0.02, 0.05, size=(58, 5))
    first = joint_inference(values, n_bootstrap=200, seed=11)
    second = joint_inference(values, n_bootstrap=200, seed=11)
    assert first["statistics"] == second["statistics"]
    assert first["block_size"] == second["block_size"]
    for mode in ("stationary", "iid"):
        out = joint_inference(values, n_bootstrap=200, seed=11,
                              resampling=mode)
        assert out["resampling"] == mode
        assert len(out["statistics"]) == 3
    with pytest.raises(ValueError):
        joint_inference(values, n_bootstrap=50)
    with pytest.raises(ValueError):
        joint_inference(values, effect="median")
    with pytest.raises(ValueError):
        joint_inference(np.zeros((10, 2)), n_bootstrap=100)


def test_t40c_constant_column_fp_slip_raises():
    """v3.7.0 复审 H1：常数列因均值舍入 std≈1e-19>0，须显式拒绝。"""
    matrix = np.column_stack(
        [np.full(58, 0.01), np.random.default_rng(41).normal(size=58)])
    assert matrix[:, 0].std(ddof=1) > 0.0  # 复现浮点假阳性前提
    with pytest.raises(ValueError):
        joint_inference(matrix, n_bootstrap=100)


def test_t40b_preregistration_v2(tmp_path, monkeypatch):
    stamps = iter([
        datetime(2026, 1, 1, 0, 0, 0),
        datetime(2026, 2, 1, 0, 0, 0),
    ])

    class FakeDateTime:
        @staticmethod
        def now():
            return next(stamps)

    monkeypatch.setattr(prereg_mod, "datetime", FakeDateTime)
    pre = PreRegistration(log_dir=str(tmp_path))
    spec = {"lag": 5, "neutralize": "industry"}
    hash_a = pre.commit(spec, researcher="scott")
    hash_b = pre.commit(spec, researcher="scott")
    assert len(hash_a) == 8 and len(hash_b) == 8
    assert hash_a != hash_b  # timestamp 进入 8 位 legacy hash

    records = []
    with open(pre.prereg_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    assert records[0]["content_hash"] == records[1]["content_hash"]
    assert records[0]["hash_algo"] == "sha256"
    assert len(records[0]["content_hash"]) == 64

    # 先按 content_hash 命中
    by_content = pre.verify_compliance(
        {"lag": 5, "neutralize": "industry"},
        records[0]["content_hash"],
    )
    assert by_content["matched_by"] == "content_hash"
    assert by_content["is_compliant"] is True

    # 回退按 8 位 commit_hash 命中
    by_commit = pre.verify_compliance(
        {"lag": 5, "neutralize": "industry"}, hash_a)
    assert by_commit["matched_by"] == "commit_hash"
    assert by_commit["is_compliant"] is True
