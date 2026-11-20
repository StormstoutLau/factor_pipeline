# -*- coding: utf-8 -*-
"""v3.9.0 E5（S6）：验证聚合验收（T390-36 ~ T390-38）。"""
import importlib.util
import json
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_all.py"
_SPEC = importlib.util.spec_from_file_location("verify_all_v390", _PATH)
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)

collect = _MOD.collect
merge_status = _MOD.merge_status
main = _MOD.main


def _report(tool, ok=True, status=None, artifacts=None):
    payload = {
        "tool": tool,
        "generated_at": "2026-11-19T00:00:00",
        "checks": [{"id": "c1", "ok": ok}],
        "artifacts": artifacts or [],
    }
    if status:
        payload["status"] = status
    return payload


def _write(directory, payload, name=None):
    path = directory / (name or ("%s.json" % payload["tool"]))
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_t390_36_aggregate(tmp_path):
    _write(tmp_path, _report("verify_capacity_impact", artifacts=[
        {"path": "a.json", "sha256": "82728ce1" + "0" * 56}]))
    _write(tmp_path, _report("verify_stat_evidence"))
    _write(tmp_path, _report("verify_portfolio_backtest"))
    out = tmp_path / "summary.json"
    code = main(["--reports-dir", str(tmp_path), "--out", str(out)])
    assert code == 0
    summary = json.loads(out.read_text(encoding="utf-8"))
    assert summary["overall"] == "pass"
    assert len(summary["tools"]) == 3
    assert sum(item["n_checks"] for item in summary["tools"]) == 3
    assert summary["tools"][0]["sha8"] == ["82728ce1"]
    assert summary["missing"] == ["contract_gate"]


def test_t390_37_missing_tolerance(tmp_path):
    _write(tmp_path, _report("verify_capacity_impact"))
    _write(tmp_path, _report("verify_stat_evidence"))
    out = tmp_path / "summary.json"
    code = main(["--reports-dir", str(tmp_path), "--out", str(out)])
    assert code == 0
    summary = json.loads(out.read_text(encoding="utf-8"))
    assert summary["overall"] == "pass"
    assert set(summary["missing"]) == {"verify_portfolio_backtest", "contract_gate"}
    assert [item["tool"] for item in summary["tools"]] == [
        "verify_capacity_impact", "verify_stat_evidence"]


def test_t390_38_exit_codes(tmp_path):
    reports = collect(tmp_path)
    assert merge_status(reports) == "pass"

    _write(tmp_path, _report("verify_capacity_impact", ok=False))
    out = tmp_path / "summary.json"
    assert main(["--reports-dir", str(tmp_path), "--out", str(out)]) == 1

    # 恢复为通过，strict 下缺失 → 1
    _write(tmp_path, _report("verify_capacity_impact", ok=True))
    assert main(["--reports-dir", str(tmp_path), "--out", str(out),
                 "--strict"]) == 1
    # 非 strict 缺失 → 0
    assert main(["--reports-dir", str(tmp_path), "--out", str(out)]) == 0


def test_t390_41_collect_skips_non_dict(tmp_path):
    """审计 H3 回归：顶层非 dict 的合法 JSON 必须跳过而非 crash。"""
    # 非法 payload（str/list 顶层）不经 _write（其按 payload["tool"] 命名），直写
    (tmp_path / "junk1.json").write_text(
        json.dumps("junk-string"), encoding="utf-8")
    (tmp_path / "junk2.json").write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    _write(tmp_path, _report("verify_capacity_impact", ok=True))
    reports = collect(tmp_path)
    assert set(reports) == {"verify_capacity_impact"}
