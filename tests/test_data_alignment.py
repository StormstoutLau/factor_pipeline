# -*- coding: utf-8 -*-
"""P-008 数据行数对齐（T398-6 / T398-7 / T398-9）。"""
import dataclasses
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtest.execution.shell.loaders import has_pyarrow

needs_pyarrow = pytest.mark.skipif(not has_pyarrow(),
                                   reason="calib extra（pyarrow）未安装")


def _write_min(path, codes, amounts):
    import pyarrow as pa
    import pyarrow.feather as feather
    feather.write_feather(pa.table({"stock_code": list(codes),
                                    "amount": list(amounts)}), str(path))


def _vci():
    """导入 scripts/verify_capacity_impact.py（进程内 CLI 测试用）。"""
    for path in (str(Path(__file__).resolve().parent.parent),
                 str(Path(__file__).resolve().parent.parent / "scripts")):
        if path not in sys.path:
            sys.path.insert(0, path)
    import verify_capacity_impact as vci
    return vci


@needs_pyarrow
def test_T398_6_audit_identity_and_md(tmp_path):
    """T398-6: 4 日小样本 → A/B/C/D 精确、双口径残差 0、md 落盘。"""
    from backtest.execution.config import CalibrationConfig
    from backtest.execution.shell.alignment import (audit_alignment,
                                                    write_alignment_report)
    from backtest.execution.shell.loaders import MinuteLoader

    root = tmp_path / "min"
    root.mkdir()
    _write_min(root / "2023-01-02.feather", [1, 2, 3], [1e6, 1e6, 0.0])
    _write_min(root / "2023-01-03.feather", [1, 2], [1e6, 1e6])
    _write_min(root / "2023-01-04.feather", [1, 2, 3], [1e6, 1e6, 1e6])

    close = pd.DataFrame(
        [[10.0, 11.0, 12.0, 13.0],
         [10.0, 11.0, np.nan, 13.0],
         [10.0, 11.0, np.nan, 13.0],
         [10.0, 11.0, 12.0, 13.0]],
        index=pd.to_datetime(["2023-01-02", "2023-01-03",
                              "2023-01-04", "2023-01-05"]),
        columns=["000001", "000002", "000003", "000004"])
    cfg = CalibrationConfig(minute_root=str(root),
                            minute_start="2023-01-01",
                            minute_end="2023-01-05")
    payload = audit_alignment(cfg, MinuteLoader(str(root)), close)

    totals = payload["totals"]
    assert totals["minute"] == 8
    assert totals["daily_full"] == 14
    assert totals["daily_matched"] == 10
    assert totals["both"] == 7
    assert totals["minute_only"] == 1
    assert totals["A_matched"] == 3
    assert totals["A_full"] == 4
    assert totals["C"] == 0
    assert totals["D"] == 3
    assert payload["identity"]["residual"] == 0
    assert payload["identity"]["residual_full"] == 0
    assert payload["code_universe"]["minute"] == 3
    assert payload["code_universe"]["daily"] == 4
    assert payload["code_universe"]["daily_only_prefix"] == {"4": 1}
    assert payload["missing_minute_days"] == [
        {"date": "2023-01-05", "daily": 4}]

    # 窗口按月份解释：起点/终点落在月中不得截掉同月其余交易日
    cfg_mid = dataclasses.replace(cfg, minute_start="2023-01-04",
                                  minute_end="2023-01-04")
    mid = audit_alignment(cfg_mid, MinuteLoader(str(root)), close)
    assert mid["totals"] == payload["totals"]
    assert mid["identity"] == payload["identity"]
    assert mid["window"] == ["2023-01", "2023-01"]

    out = tmp_path / "out" / "data_alignment.json"
    written = write_alignment_report(payload, out)
    assert len(written) == 2
    md = Path(written[1]).read_text(encoding="utf-8")
    assert "残差" in md and "0" in md
    assert "A_matched" in md or "A（匹配日）" in md


def test_T398_7_report_section_guard():
    """T398-7: 有 data_alignment 才渲染「数据行数对齐」节。"""
    from backtest.execution.shell.report import render_markdown

    align = {
        "scope": "matched_days", "matched_days": 786, "daily_days": 787,
        "total": {"minute": 3442081, "daily": 3523738, "diff_pct": -2.32,
                  "daily_full": 3528865, "diff_full_pct": -2.46},
        "outlier_days": [{"date": "2020-02-26", "diff_pct": -27.55},
                         {"date": "2020-02-27", "diff_pct": -27.68}],
        "missing_minute_days": [{"date": "2023-03-31", "daily": 5127}],
        "zero_amount": {"pairs": 7917, "share_pct": 0.23,
                        "peak_month": "2022-05", "peak_share_pct": 1.0843},
    }
    text = render_markdown({"evidence_level": "minutes",
                            "panels": {"data_alignment": align}})
    assert "数据行数对齐" in text
    assert "3,442,081" in text or "3442081" in text
    assert "2023-03-31" in text

    plain = render_markdown({"evidence_level": "minutes", "panels": {}})
    assert "数据行数对齐" not in plain


def _failed_payload():
    """残差非 0 的最小 payload（Step 10 P2-1 负向用例）。"""
    return {
        "window": ["2023-01", "2023-01"],
        "scope": {"matched_days": 1, "daily_days": 2, "minute_days": 1},
        "totals": {"minute": 8, "daily_full": 14, "daily_matched": 10,
                   "both": 7, "minute_only": 1, "daily_only_full": 7,
                   "daily_only_matched": 3, "A_matched": 3, "A_full": 4,
                   "C": 0, "D": 3, "zero_pairs": 1},
        "code_universe": {"minute": 3, "daily": 4, "daily_only": 1,
                          "minute_only": 0, "daily_only_prefix": {"4": 1}},
        "identity": {"matched": "3 + 0 - 1 = 2", "full": "4 + 0 + 3 - 1 = 6",
                     "residual": 5, "residual_full": 5},
        "months": [], "outlier_days": [], "missing_minute_days": [],
        "alignment_identity_failed": True,
    }


def test_T398_9_identity_failed_guard_md_exit2(tmp_path, monkeypatch, capsys):
    """T398-9: 恒等式失败 → 守卫标记 + md 警示行 + CLI exit 2（Step 10 ADD P2-1/P2-2/P3-1）。"""
    from backtest.execution.shell import alignment as al
    from backtest.execution.shell.alignment import audit_alignment
    from backtest.execution.shell.loaders import MinuteLoader
    from backtest.execution.config import CalibrationConfig

    # 1) 守卫纯函数：自洽 totals → False；篡改任一口径 → True
    good = {"A_matched": 3, "C": 0, "D": 3, "minute_only": 1,
            "A_full": 4, "daily_matched": 10, "daily_full": 14, "minute": 8}
    assert al._identity_failed(good) is False
    assert al._identity_failed(dict(good, daily_matched=11)) is True
    assert al._identity_failed(dict(good, daily_full=15)) is True
    assert al._identity_failed(dict(good, minute=9)) is True

    # 2) 正常审计路径（真实数据）：无失败标记、残差 0（负对照）
    root = tmp_path / "min9"
    root.mkdir()
    _write_min(root / "2023-01-02.feather", [1, 2, 3], [1e6, 1e6, 0.0])
    _write_min(root / "2023-01-03.feather", [1, 2], [1e6, 1e6])
    close = pd.DataFrame(
        [[10.0, 11.0, 12.0, 13.0],
         [10.0, 11.0, np.nan, 13.0],
         [10.0, 11.0, 12.0, 13.0]],
        index=pd.to_datetime(["2023-01-02", "2023-01-03", "2023-01-04"]),
        columns=["000001", "000002", "000003", "000004"])
    cfg = CalibrationConfig(minute_root=str(root),
                            minute_start="2023-01-01",
                            minute_end="2023-01-05")
    normal = audit_alignment(cfg, MinuteLoader(str(root)), close)
    assert "alignment_identity_failed" not in normal
    assert normal["identity"]["residual"] == 0
    assert normal["identity"]["residual_full"] == 0

    # 3) md 渲染：带标记 → 顶部警示行；去掉标记 → 无警示（非恒真对照）
    bad_md = al._render_alignment_md(_failed_payload())
    assert "恒等式校验失败" in bad_md
    assert "alignment_identity_failed" in bad_md
    clean = {k: v for k, v in _failed_payload().items()
             if k != "alignment_identity_failed"}
    assert "恒等式校验失败" not in al._render_alignment_md(clean)

    # 4) CLI：failed payload → exit 2 且落盘 md 含警示；正常 payload → exit 0
    vci = _vci()
    monkeypatch.setattr(vci, "build_panels", lambda root: {"close": close})
    monkeypatch.setattr(sys, "argv", [
        "verify_capacity_impact.py", "--alignment-audit",
        "--alignment-json", str(tmp_path / "bad.json")])
    monkeypatch.setattr(al, "audit_alignment",
                        lambda *a, **k: _failed_payload())
    rc = vci.main()
    out = capsys.readouterr().out
    assert rc == 2, out[-2000:]
    assert "恒等式校验失败" in (tmp_path / "bad.md").read_text(
        encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "verify_capacity_impact.py", "--alignment-audit",
        "--alignment-json", str(tmp_path / "good.json")])
    monkeypatch.setattr(al, "audit_alignment",
                        lambda *a, **k: normal)
    assert vci.main() == 0
