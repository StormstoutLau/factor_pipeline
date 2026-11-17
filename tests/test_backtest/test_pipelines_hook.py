# -*- coding: utf-8 -*-
"""E6 管线治理 hook — T31/T32 (v3.6.0).

TDD 顺序：本文件先于 pipelines_v2.py 的 hook 落地；首次运行应为红
（AttributeError: 'FactorProcessingPipelineV2' object has no attribute
'set_governance_hook'）。

覆盖 EXECUTION_V3.6.0_GOVERNANCE_BASE.md §2.6 / §5.1：
  T31 未设 hook 零变更
  T32 hook 事件字段齐全 + 异常不吞
"""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from factor_pipeline.backtest.golden_master import GoldenMaster
from factor_pipeline.pipelines_v2 import (
    FactorProcessingPipelineV2,
    PipelineV2Config,
)


def _factor_data(n_periods: int = 36, n_stocks: int = 8,
                 n_factors: int = 2, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2022-01-31", periods=n_periods, freq="ME")
    columns = ["S%02d" % i for i in range(n_stocks)]
    return {
        "f%d" % f: pd.DataFrame(
            rng.normal(size=(n_periods, n_stocks)),
            index=dates, columns=columns,
        )
        for f in range(n_factors)
    }


def _fit_transform(pipeline, data):
    pipeline.fit(data)
    return pipeline.transform(data)


# ============================================================
# T31 未设 hook 零变更
# ============================================================

def test_t31_no_hook_zero_change():
    data = _factor_data()

    baseline = FactorProcessingPipelineV2(PipelineV2Config())
    out_baseline = _fit_transform(baseline, data)

    explicit_none = FactorProcessingPipelineV2(PipelineV2Config())
    assert explicit_none.set_governance_hook(None) is None
    assert explicit_none._governance_hook is None
    out_none = _fit_transform(explicit_none, data)

    for name in data:
        a = out_baseline[name].to_numpy(dtype=float)
        b = out_none[name].to_numpy(dtype=float)
        assert np.allclose(a, b, rtol=1e-10, atol=1e-12, equal_nan=True), name


def _load_make_baseline():
    root = Path(__file__).resolve().parents[2]
    path = root / "tests" / "golden" / "govbase_v1_synth" / "make_baseline.py"
    spec = importlib.util.spec_from_file_location(
        "govbase_make_baseline", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return root, module


def test_t31_no_hook_matches_golden():
    root, module = _load_make_baseline()
    outputs = module.build_outputs()
    master = GoldenMaster(root=str(root / "tests" / "golden"))
    report = master.compare(
        "govbase_v1_synth", outputs, rtol=1e-10, atol=1e-12,
    )
    assert report.verdict in ("PASS", "PASS_WITH_ENV_DIFF")
    assert report.max_abs_diff <= 1e-10


# ============================================================
# T32 事件字段 + 异常传播
# ============================================================

def test_t32_hook_emits_event():
    data = _factor_data()
    events = []

    pipeline = FactorProcessingPipelineV2(PipelineV2Config())
    pipeline.set_governance_hook(events.append)
    pipeline.fit(data)
    pipeline.transform(data)

    assert len(events) == len(data)
    expected = {
        "event", "factor_id", "stage", "arm", "pipeline_version",
        "config_hash", "routing", "sample_window", "env_fingerprint",
    }
    for event in events:
        assert expected <= set(event)
        assert event["event"] == "pipeline_fit"
        assert event["factor_id"] in data
        assert event["stage"] == "S2"
        assert isinstance(event["routing"], dict)
        assert event["routing"]["factor_name"] == event["factor_id"]
        assert set(event["sample_window"]) == {"start", "end"}
        assert isinstance(event["config_hash"], str)
        assert len(event["config_hash"]) == 64
        assert isinstance(event["env_fingerprint"], dict)


def test_t32_hook_exception_propagates():
    data = _factor_data()
    pipeline = FactorProcessingPipelineV2(PipelineV2Config())

    def boom(_event):
        raise RuntimeError("hook boom")

    pipeline.set_governance_hook(boom)
    with pytest.raises(RuntimeError, match="hook boom"):
        pipeline.fit(data)
