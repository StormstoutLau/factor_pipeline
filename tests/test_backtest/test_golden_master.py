# -*- coding: utf-8 -*-
"""GR-3 Golden master — T16-T20 (v3.6.0 E3).

先于 backtest/golden_master.py 落地；首次运行应为红
（ModuleNotFoundError: No module named 'factor_pipeline.backtest.golden_master'）。

覆盖 EXECUTION_V3.6.0_GOVERNANCE_BASE.md §5.1：
  T16 完全相同 PASS / T17 容差边界 / T18 参数变更 FAIL
  T19 缺股/多股 missing-extra / T20 capture 不覆盖 + force 审计
"""
import numpy as np
import pandas as pd
import pytest

from factor_pipeline.backtest.golden_master import GoldenMaster


# ============================================================
# helpers
# ============================================================

def _outputs(scale: float = 1.0) -> dict:
    dates = pd.date_range("2020-01-31", periods=3, freq="ME")
    stocks = ["a", "b"]
    base = np.arange(6, dtype=float).reshape(3, 2) + 1.0
    return {
        "f1": pd.DataFrame(base * scale, index=dates, columns=stocks),
        "f2": pd.DataFrame((base + 0.5) * scale, index=dates, columns=stocks),
    }


def _manifest() -> dict:
    return {"pipeline_version": "3.6.0", "generator": "test_golden_master"}


# ============================================================
# T16 完全相同 → PASS
# ============================================================

def test_t16_identical_outputs_pass(tmp_path):
    master = GoldenMaster(root=str(tmp_path / "golden"))
    outputs = _outputs()
    master.capture("base", outputs, _manifest())

    report = master.compare("base", outputs)
    assert report.verdict == "PASS"
    assert report.n_mismatch == 0
    assert report.n_missing == 0
    assert report.n_extra == 0
    assert report.max_abs_diff == 0.0
    assert report.n_common == 12


# ============================================================
# T17 容差边界
# ============================================================

def test_t17_tolerance_boundary(tmp_path):
    master = GoldenMaster(root=str(tmp_path / "golden"))
    outputs = _outputs()
    master.capture("base", outputs, _manifest())

    tiny = {k: v + 1e-11 for k, v in outputs.items()}
    assert master.compare("base", tiny).verdict == "PASS"

    big = {k: v + 1e-8 for k, v in outputs.items()}
    report = master.compare("base", big)
    assert report.verdict == "FAIL"
    assert report.n_mismatch == 12


# ============================================================
# T18 参数变更（percentile 1/99 → 2/98）→ FAIL
# ============================================================

def test_t18_parameter_change_fails(tmp_path):
    master = GoldenMaster(root=str(tmp_path / "golden"))
    master.capture("base", _outputs(scale=1.0), _manifest())

    changed = _outputs(scale=2.0)  # 模拟分位点变更后的输出
    report = master.compare("base", changed)
    assert report.verdict == "FAIL"
    assert report.n_mismatch > 0


# ============================================================
# T19 缺股 / 多股
# ============================================================

def test_t19_missing_and_extra_keys(tmp_path):
    master = GoldenMaster(root=str(tmp_path / "golden"))
    baseline = _outputs()
    master.capture("base", baseline, _manifest())

    actual = {
        "f1": baseline["f1"].drop(columns=["b"]),
        "f2": baseline["f2"].assign(c=baseline["f2"]["a"]),
    }
    report = master.compare("base", actual)
    assert report.verdict == "FAIL"
    assert report.n_missing == 3   # f1 缺 b，3 个日期
    assert report.n_extra == 3     # f2 多 c，3 个日期


# ============================================================
# T20 capture 不覆盖 / force 审计
# ============================================================

def test_t20_capture_no_overwrite_and_force_audit(tmp_path):
    master = GoldenMaster(root=str(tmp_path / "golden"))
    master.capture("base", _outputs(), _manifest())

    with pytest.raises(FileExistsError):
        master.capture("base", _outputs(), _manifest())

    with pytest.raises(ValueError):
        master.capture("base", _outputs(), _manifest(), force=True)

    master.capture(
        "base", _outputs(scale=1.5), _manifest(),
        force=True, reason="percentile 1/99 -> 2/98", reviewer="alice",
    )
    manifest, values = master.load("base")
    assert manifest.reviewer == "alice"
    assert manifest.reason == "percentile 1/99 -> 2/98"
    assert len(values) == 12
