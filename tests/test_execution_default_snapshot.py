# -*- coding: utf-8 -*-
"""v3.8.0 E7 — 默认路径快照守护（T380-51 ~ T380-52）。

默认路径不进入新代码，故本文件在实施前即可通过（无红形态）；
``out/capacity_impact.json`` 或数据目录缺失时显式 skip（不得静默 PASS）。
"""
import json
import os
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_SNAPSHOT = _REPO / "out" / "capacity_impact.json"

_EXPECTED_META_KEYS = {
    "fee_bps", "aum_grid", "sqrt_c", "linear_k", "cap_levels",
    "amount_unit", "mv_unit", "sample_start", "sample_end",
    "n_months", "recon_warnings",
}
_EXPECTED_VARIANT_KEYS = {
    "base", "rows", "breakeven", "capacity", "tiers", "segments",
    "n_hold", "universe",
}


def _load():
    if not _SNAPSHOT.exists():
        pytest.skip("环境性 skip: out/capacity_impact.json 基线缺失")
    if not os.path.isdir(r"E:\Ashare_data"):
        pytest.skip("环境性 skip: E:\\Ashare_data 不可用（design §16.3 注）")
    with open(_SNAPSHOT, "r", encoding="utf-8") as fh:
        return json.load(fh)


def test_default_snapshot_keys():
    """T380-51: 键集合与 v3.7.0 基线完全一致。"""
    payload = _load()
    assert set(payload.keys()) == {"meta", "results"}
    assert set(payload["meta"].keys()) == _EXPECTED_META_KEYS
    assert set(payload["results"].keys()) == {
        "Q5_EW", "Q5_EW_tradable", "exQ1_EW", "exQ1_EW_tradable"}
    for name, block in payload["results"].items():
        assert set(block.keys()) == _EXPECTED_VARIANT_KEYS, name


def test_default_snapshot_values():
    """T380-52: exQ1 203亿 / Q5 11亿，容差 0。"""
    payload = _load()
    ex_q1 = payload["results"]["exQ1_EW"]["capacity"]["0.10"]["p95"]
    q5 = payload["results"]["Q5_EW"]["capacity"]["0.10"]["p95"]
    assert ex_q1 == 20274864098.520184
    assert q5 == 1062272040.4456166
    assert round(ex_q1 / 1e8) == 203
    assert round(q5 / 1e8) == 11
