# -*- coding: utf-8 -*-
"""v3.9.0 验证聚合（只读）：扫描各脚本 --report-json 产物，输出统一 summary。

依据：DESIGN_SYNTHETIC_VALIDATION_TRACEABILITY.md §8（v1.3）。
退出码：pass=0、warn=0、fail=1；--strict 时缺失=1。
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

__all__ = ["TOOLS", "collect", "merge_status", "main"]

TOOLS = ("verify_capacity_impact", "verify_stat_evidence",
         "verify_portfolio_backtest", "contract_gate")


def collect(reports_dir):
    """按 tool 取最新报告；非法/缺 tool 的文件跳过。"""
    root = Path(reports_dir)
    found = {}
    if not root.exists():
        return found
    for path in sorted(root.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if not isinstance(payload, dict):
            # 顶层为标量/数组/字符串的合法 JSON 同属结构非法（审计 H3）
            continue
        tool = payload.get("tool")
        if not tool:
            continue
        payload["_path"] = str(path)
        payload["_mtime"] = path.stat().st_mtime_ns
        if tool not in found or payload["_mtime"] >= found[tool]["_mtime"]:
            found[tool] = payload
    return found


def _status(payload):
    declared = payload.get("status")
    if declared in ("pass", "warn", "fail"):
        return declared
    checks = payload.get("checks", [])
    return "pass" if all(item.get("ok") for item in checks) else "fail"


def merge_status(reports):
    statuses = [_status(payload) for payload in reports.values()]
    if any(item == "fail" for item in statuses):
        return "fail"
    if any(item == "warn" for item in statuses):
        return "warn"
    return "pass"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="verify_all")
    parser.add_argument("--reports-dir", default="out/verification")
    parser.add_argument("--out", default=None)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.reports_dir)
    if not root.is_absolute():
        root = Path(__file__).resolve().parent.parent / root
    out = Path(args.out) if args.out else root / "summary.json"
    if not out.is_absolute():
        out = Path(__file__).resolve().parent.parent / out

    reports = collect(root)
    overall = merge_status(reports)
    missing = [tool for tool in TOOLS if tool not in reports]

    tools = []
    for tool in TOOLS:
        payload = reports.get(tool)
        if payload is None:
            continue
        artifacts = payload.get("artifacts", [])
        sha8 = []
        for item in artifacts:
            digest = item.get("sha256") if isinstance(item, dict) else None
            if digest:
                sha8.append(str(digest)[:8])
        tools.append({
            "tool": tool,
            "status": _status(payload),
            "n_checks": len(payload.get("checks", [])),
            "n_artifacts": len(artifacts),
            "sha8": sha8,
        })

    summary = {
        "generated_at": datetime.now().isoformat(),
        "overall": overall,
        "tools": tools,
        "missing": missing,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                   encoding="utf-8")

    for row in tools:
        print("%-28s %-5s checks=%-3d artifacts=%-2d %s" % (
            row["tool"], row["status"], row["n_checks"],
            row["n_artifacts"], ",".join(row["sha8"])))
    if missing:
        print("missing: %s" % ", ".join(missing))
    print("summary: %s" % out)

    if overall == "fail":
        return 1
    if args.strict and missing:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
