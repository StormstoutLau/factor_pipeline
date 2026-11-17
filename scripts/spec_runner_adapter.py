#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Spec_Runner 接入壳（factor_pipeline）。

配置区之外无自定义逻辑：只做命令装配与 exit 透传，不复制 runner 语义。
RUNNER 指向 Spec_Workflow 内置最新版（v1.11.0+）；外仓 F:\\Spec_Runner
自 P-019 起冻结为历史存档，不再使用。

用法：
  python scripts/spec_runner_adapter.py gates
  python scripts/spec_runner_adapter.py probe
  python scripts/spec_runner_adapter.py gate unit-tests
  python scripts/spec_runner_adapter.py gate tests-fast --session factorpipe-govbase-step5
  python scripts/spec_runner_adapter.py status --session <sid>
  python scripts/spec_runner_adapter.py replay --session <sid>
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ============================================================
# 配置区
# ============================================================

RUNNER = r"F:\Spec_Workflow\tools\spec_runner\spec_runner.py"
PREFIX = "factorpipe"
CWD = r"f:\Coding\factor_pipeline"

# 项目开发环境：Python 3.12（factor_pipeline 已 editable 安装于此）
PY = r"C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe"

GATES = {
    "probe": "echo Spec_Runner OK",
    "unit-tests": f'"{PY}" -m pytest tests -q --tb=short',
    "tests-fast": (
        f'"{PY}" -m pytest '
        "tests/test_backtest/test_multiple_testing.py "
        "tests/test_fix3_version_unification.py -q --tb=short"
    ),
    "version-consistency": (
        f'"{PY}" -m pytest tests/test_fix3_version_unification.py -q --tb=short'
    ),
    # E1 GR-1 治理记录（步骤 9 起可用）
    "tests-e1": (
        f'"{PY}" -m pytest tests/test_backtest/test_governance.py -q --tb=short'
    ),
    # E2 GR-2 数据契约
    "tests-e2": (
        f'"{PY}" -m pytest tests/test_backtest/test_data_contract.py -q --tb=short'
    ),
    # E3 GR-3 Golden master
    "tests-e3": (
        f'"{PY}" -m pytest tests/test_backtest/test_golden_master.py -q --tb=short'
    ),
    # E4 GR-4 多重检验台账
    "tests-e4": (
        f'"{PY}" -m pytest tests/test_backtest/test_multiple_testing_ledger.py -q --tb=short'
    ),
    # E5 Stata 对拍 + E6 hook/T33-T35 补充用例
    "tests-e5": (
        f'"{PY}" -m pytest '
        "tests/test_backtest/test_pipelines_hook.py "
        "tests/test_backtest/test_govbase_supplement.py -q --tb=short"
    ),
    "stata-e5": (
        f'"{PY}" benchmarks/stata_econ_crosscheck.py --case all'
    ),
    "import-smoke": (
        f'"{PY}" -c "import factor_pipeline; '
        "import factor_pipeline.backtest.multiple_testing as mt; print('import OK')\""
    ),
    # 治理底座实施后启用（当前文件尚不存在，显式调用会失败——这是预期）
    # "tests-governance": f'"{PY}" -m pytest tests/test_backtest/test_governance.py '
    #                     'tests/test_backtest/test_data_contract.py '
    #                     'tests/test_backtest/test_golden_master.py '
    #                     'tests/test_backtest/test_multiple_testing_ledger.py -q',
}

# ============================================================
# 以下无需修改
# ============================================================


def _runner_cmd():
    return [sys.executable, RUNNER]


def _session_for(name):
    return f"{PREFIX}-{name}-{datetime.now():%Y%m%d}"


def _gate_cmd(name, session):
    if name not in GATES:
        print(f"gate: unknown '{name}'——可用: {', '.join(GATES)}", file=sys.stderr)
        sys.exit(2)
    return [
        *_runner_cmd(), "gate",
        "--name", name,
        "--cmd", GATES[name],
        "--session", session or _session_for(name),
        "--cwd", CWD,
    ]


def _exec(cmd):
    print("+", " ".join(cmd))
    return subprocess.run(cmd, cwd=CWD).returncode


def main(argv=None):
    p = argparse.ArgumentParser(prog="spec_runner_adapter")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gate", help="执行 GATES 表中的门禁（exit 透传）")
    g.add_argument("name")
    g.add_argument("--session")

    sub.add_parser("gates", help="列出可用门禁")
    sub.add_parser("probe", help="接入自检（echo 探针）")

    for name in ("status", "replay", "fork"):
        s = sub.add_parser(name, help=f"透传 Spec_Runner {name}")
        s.add_argument("--session")
        if name == "fork":
            s.add_argument("--seq", type=int, required=True, dest="seq_from")
            s.add_argument("--new", required=True)

    d = sub.add_parser("dry-run", help="打印将执行的命令，不实际运行")
    d.add_argument("inner", nargs=argparse.REMAINDER)

    args = p.parse_args(argv)

    if args.cmd == "gates":
        print("\n".join(f"{k:20s} {v}" for k, v in GATES.items()))
        return 0
    if args.cmd == "probe":
        return _exec(_gate_cmd("probe", None))
    if args.cmd == "gate":
        return _exec(_gate_cmd(args.name, args.session))
    if args.cmd == "dry-run":
        inner = [a for a in (args.inner or []) if a != "--"]
        ns = p.parse_args(inner or ["gates"])
        if ns.cmd == "gate":
            print("DRY-RUN:", " ".join(_gate_cmd(ns.name, ns.session)))
        elif ns.cmd == "probe":
            print("DRY-RUN:", " ".join(_gate_cmd("probe", None)))
        else:
            print("DRY-RUN:", ns.cmd)
        return 0

    cmd = [*_runner_cmd(), args.cmd]
    for flag, val in (("--session", getattr(args, "session", None)),
                      ("--seq", getattr(args, "seq_from", None)),
                      ("--new", getattr(args, "new", None))):
        if val is not None:
            cmd += [flag, str(val)]
    return _exec(cmd)


if __name__ == "__main__":
    sys.exit(main())
