# -*- coding: utf-8 -*-
"""v3.9.0 E3（S4）：步骤级追溯验收（T390-21 ~ T390-26）。"""
import json

import numpy as np
import pandas as pd
import pytest

from backtest.trace import PipelineTrace, content_hash, find_first_divergence


def _write(path, tamper_seq=None):
    trace = PipelineTrace(path=str(path), enabled=True, code_version="3.9.0")
    with trace.step("load.factor", seed=1) as step:
        step.add_input("x", np.arange(6.0).reshape(2, 3))
        step.add_output("y", np.arange(6.0))
    with trace.step("align.trade_date", lag=0) as step:
        step.add_input("y", np.arange(6.0))
        step.add_output("z", {"a": 1, "b": [1.0, 2.0]})
    return str(path)


def _tamper(path, seq=2):
    lines = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if record["seq"] == seq:
                record["outputs"][0]["hash"] = "sha256:" + "0" * 64
            lines.append(json.dumps(record, ensure_ascii=False,
                                    sort_keys=True, separators=(",", ":")))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def test_t390_21_disabled_zero_io(tmp_path):
    path = tmp_path / "nested" / "trace.jsonl"
    trace = PipelineTrace(path=str(path), enabled=False)
    with trace.step("load.factor", seed=1) as step:
        step.add_input("x", np.arange(3.0))
        step.add_output("y", np.arange(3.0))
    assert not path.exists()
    assert not path.parent.exists()


def test_t390_22_jsonl_readable(tmp_path):
    path = _write(tmp_path / "trace.jsonl")
    with open(path, encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle if line.strip()]
    assert len(records) == 2
    required = ("trace_version", "code_version", "run_id", "step", "seq",
                "started_at", "params_hash", "inputs", "outputs",
                "diagnostics", "status")
    for record in records:
        for key in required:
            assert key in record, "缺少字段 %s" % key
    assert [r["seq"] for r in records] == [1, 2]
    assert records[0]["run_id"] == records[1]["run_id"]


def test_t390_23_deterministic(tmp_path):
    a = _write(tmp_path / "a.jsonl")
    b = _write(tmp_path / "b.jsonl")
    assert find_first_divergence(a, b) is None


def test_t390_24_tamper_locating(tmp_path):
    a = _write(tmp_path / "a.jsonl")
    b = tmp_path / "b.jsonl"
    b.write_text(open(a, encoding="utf-8").read(), encoding="utf-8")
    _tamper(str(b), seq=2)
    found = find_first_divergence(a, str(b))
    assert found is not None
    assert found["seq"] == 2
    assert found["field"] == "outputs[0].hash"
    # DataFrame 中段篡改（抽样行之外）也必须被 content_hash 捕获（M-3）
    frame = pd.DataFrame(np.arange(5000.0).reshape(50, 100))
    base = content_hash(frame)
    changed = frame.copy()
    changed.iloc[15, 50] += 1000.0  # 行 15 不在「首 8 / 中 ±4 / 尾 8」抽样范围
    assert content_hash(changed) != base


def test_t390_25_exception_status(tmp_path):
    path = str(tmp_path / "trace.jsonl")
    trace = PipelineTrace(path=path, enabled=True)
    with pytest.raises(RuntimeError):
        with trace.step("calib.models", n=3) as step:
            step.add_input("x", np.arange(3.0))
            raise RuntimeError("boom")
    with open(path, encoding="utf-8") as handle:
        record = json.loads(handle.readline())
    assert record["status"] == "error"
    assert "RuntimeError" in record["error"]
    assert record["outputs"] == []


def test_t390_26_content_hash_deterministic():
    array = np.array([[1.0, np.nan], [3.0, 4.0]])
    assert content_hash(array) == content_hash(array)
    assert content_hash(array) == content_hash(np.array([[1.0, np.nan], [3.0, 4.0]]))
    mapping = {"b": 1, "a": [1.5, 2.5]}
    assert content_hash(mapping) == content_hash({"a": [1.5, 2.5], "b": 1})
    frame = pd.DataFrame({"a": [1.0, np.nan], "b": [2.0, 3.0]})
    assert content_hash(frame) == content_hash(frame.copy())
    with pytest.raises(TypeError):
        content_hash(object())


def test_t390_39_content_hash_inf_distinct():
    """审计 H1 回归：±inf 不得折叠为 0.0（hash 冲突会漏检追溯分歧）。"""
    assert content_hash(np.array([np.inf])) != content_hash(np.array([0.0]))
    assert content_hash(np.array([-np.inf])) != content_hash(np.array([0.0]))
    assert content_hash(np.array([np.inf])) != content_hash(np.array([-np.inf]))
    assert content_hash(np.array([1.0, np.nan])) != content_hash(
        np.array([1.0, 0.0]))
