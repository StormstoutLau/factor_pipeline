# -*- coding: utf-8 -*-
"""E7 研究入口前置数据契约 — contract_gate 集成用例 (v3.6.0).

覆盖 EXECUTION_V3.6.0_GOVERNANCE_BASE.md §1 E7 / §2.8：
  - `market_fields()` 将默认字段路径适配到 `<data_root>/market_data/`
  - `run_contract_gate()` 在合成数据根上返回 PASS，并落盘 JSON/Markdown
  - 样本末缺省时从 `stock_close.pkl` 末行推导
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from contract_gate import market_fields, run_contract_gate  # noqa: E402


def _build_data_root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    market = root / "market_data"
    market.mkdir(parents=True)

    dates = pd.date_range("2024-01-01", periods=5, freq="B")
    stocks = ["000001", "000002"]
    values = np.arange(len(dates) * len(stocks), dtype=float).reshape(
        len(dates), len(stocks)) + 10.0

    panel = pd.DataFrame(values, index=dates, columns=stocks)
    # 真实数据布局：pkl 面板索引为字符串日期
    panel.index = dates.strftime("%Y-%m-%d")
    panel.to_pickle(market / "stock_close.pkl")
    adj = pd.DataFrame(np.ones_like(values), index=panel.index, columns=stocks)
    adj.to_pickle(market / "stock_adj.pkl")
    amount = pd.DataFrame(
        values * 100.0, index=panel.index, columns=stocks)
    amount.to_pickle(market / "stock_amount.pkl")
    (panel * 1e8).to_csv(market / "market_value.csv")

    pd.DataFrame(
        {"list_date": pd.to_datetime(["2020-01-01", "2020-01-02"])},
        index=stocks,
    ).to_pickle(market / "list_date_df.pkl")
    pd.Series(list(map(str, dates.strftime("%Y-%m-%d")))).to_pickle(
        market / "all_dates.pkl")
    return root


def test_e7_market_fields_uses_market_data_prefix():
    specs = {spec.name: spec.file for spec in market_fields()}
    assert specs["price"] == "market_data/stock_close.pkl"
    assert specs["mv"] == "market_data/market_value.csv"
    assert specs["industry"] is None
    assert "list_date" not in specs
    assert "calendar" not in specs
    assert "barra" not in specs


def test_e7_contract_gate_persists_report(tmp_path):
    root = _build_data_root(tmp_path)
    json_path = tmp_path / "reports" / "contract.json"
    md_path = tmp_path / "reports" / "contract.md"

    report = run_contract_gate(
        root, prefix="e7", json_path=json_path, markdown_path=md_path,
    )

    assert report.passed is True
    assert report.calendar_source == "injected"
    assert report.snapshot.sample_end == "2024-01-05"

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert payload["calendar_source"] == "injected"
    assert payload["sample_end"] == "2024-01-05"
    assert payload["checks"]
    assert payload["data_snapshot_hash"]

    markdown = md_path.read_text(encoding="utf-8")
    assert "数据契约报告" in markdown
    assert "结论: **PASS**" in markdown
