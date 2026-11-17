# -*- coding: utf-8 -*-
"""E7 研究入口前置数据契约（GR-2 组合层，v3.6.0）。

容量 / 多头端研究脚本在加载面板前显式调用本模块；默认不启用，
仅在传入 ``--contract`` / ``--contract-only`` 时运行，因此既有研究口径零变更。

设计依据：``docs/private/DESIGN_GOVERNANCE_BASE.md`` §5.6 / §10.4；
实施依据：``docs/EXECUTION_V3.6.0_GOVERNANCE_BASE.md`` §2.8。
"""
import json
import sys
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from factor_pipeline.backtest.data_contract import (  # noqa: E402
    ContractReport,
    check_data_contract,
    default_fields,
)


def market_fields():
    """`default_fields()` 适配真实目录：原始字段位于 ``<data_root>/market_data/``。

    - ``list_date`` / ``calendar`` 是非日期轴参考表，由参数注入；
    - ``barra`` 是 MongoDB 导出的 dict-Series（非面板），按 known_gap 处理。
    """
    fields = []
    for spec in default_fields():
        if spec.name in ("list_date", "calendar", "barra"):
            continue
        file = spec.file
        if file and not file.startswith("market_data/"):
            file = "market_data/%s" % file
        fields.append(replace(spec, file=file))
    return tuple(fields)


class _PanelPickleReader:
    """真实数据中的 pkl 面板索引为字符串日期；读入后统一转 ``DatetimeIndex``。"""

    def read(self, root, spec):
        frame = pd.read_pickle(Path(root) / spec.file)
        if isinstance(frame, pd.DataFrame):
            frame = frame.copy()
            frame.index = pd.to_datetime(frame.index)
        return frame


def load_list_date(data_root):
    """读取 ``market_data/list_date_df.pkl['list_date']``；缺失返回 None。"""
    path = Path(data_root) / "market_data" / "list_date_df.pkl"
    if not path.exists():
        return None
    return pd.read_pickle(path)["list_date"]


def _load_calendar(market_dir: Path):
    path = market_dir / "all_dates.pkl"
    if not path.exists():
        return None
    obj = pd.read_pickle(path)
    index = obj.index if isinstance(obj, pd.DataFrame) else obj
    return pd.DatetimeIndex(pd.to_datetime(index))


def run_contract_gate(
    data_root,
    *,
    sample_end=None,
    prefix="research",
    json_path=None,
    markdown_path=None,
) -> ContractReport:
    """运行数据契约并落盘 JSON/Markdown 报告；不抛错，由调用方决定退出码。"""
    root = Path(data_root)
    market = root / "market_data"
    if sample_end is None:
        close = pd.read_pickle(market / "stock_close.pkl")
        sample_end = pd.to_datetime(close.index).max()

    report = check_data_contract(
        root, sample_end, market_fields(),
        trading_calendar=_load_calendar(market),
        list_date=load_list_date(root),
        readers={"pickle": _PanelPickleReader()},
    )

    json_target = Path(json_path) if json_path else (
        ROOT / "out" / ("%s_contract.json" % prefix))
    md_target = Path(markdown_path) if markdown_path else (
        ROOT / "out" / ("%s_contract.md" % prefix))
    json_target.parent.mkdir(parents=True, exist_ok=True)
    md_target.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "passed": report.passed,
        "policy_version": report.policy_version,
        "sample_end": report.snapshot.sample_end,
        "as_of": report.snapshot.as_of,
        "calendar_source": report.calendar_source,
        "data_snapshot_hash": report.snapshot.stable_hash(),
        "checks": [asdict(check) for check in report.checks],
        "known_gaps": [asdict(gap) for gap in report.known_gaps],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    json_target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    md_target.write_text(report.to_markdown(), encoding="utf-8")

    print("[contract] %s -> json=%s, md=%s" % (
        "PASS" if report.passed else "FAIL", json_target, md_target))
    for check in report.checks:
        if not check.passed:
            print("  [%s] %s: %s" % (
                check.severity.upper(), check.check, check.message))
    return report
