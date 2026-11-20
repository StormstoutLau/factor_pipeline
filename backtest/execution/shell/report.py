# -*- coding: utf-8 -*-
"""v3.8.1 校准报告落盘（JSON / Markdown，携带 evidence_level）。

实施依据：EXECUTION §2.11 §7.3；每份输出必须含 ``evidence_level``。
v3.8.1：新增面板覆盖度 / λ 显著性与填充 / 窗长容量 / 持有期净收益四段；
缺键整段跳过，不抛 ``KeyError``。
"""
import json
from pathlib import Path

__all__ = ["write_json", "render_markdown", "write_report"]


def _num(value, fmt="%.4g"):
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number != number or number in (float("inf"), float("-inf")):
        return "n/a"
    return fmt % number


def _median(values):
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return 0.5 * (ordered[mid - 1] + ordered[mid])


def write_json(payload, path):
    """写出规范化 JSON（排序键 + UTF-8 + 2 空格缩进）。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    return target


def render_markdown(payload):
    """极简 Markdown 摘要；缺失 evidence_level 直接报错（S5）。"""
    level = payload.get("evidence_level")
    if not level:
        raise ValueError("输出缺少 evidence_level（S5 硬约束）")
    lines = ["# v3.8.0 执行/容量校准报告", "",
             "- evidence_level: `%s`" % level,
             "- config_hash: `%s`" % payload.get("config_hash", ""), ""]
    c = payload.get("c") or {}
    lines += ["## c 三档", "",
              "| 档位 | 数值 |", "|------|------|"]
    for key in ("c_default", "c_calib_point", "c_calib_lower",
                "c_calib_upper", "c_calib_stress"):
        lines.append("| %s | %s |" % (key, c.get(key)))
    capacity = payload.get("capacity") or {}
    lines += ["", "## 容量（regime 主值取 min）", "",
              "- min_regime: %s" % capacity.get("min_regime"),
              "- median: %s" % capacity.get("median"), ""]
    panels = payload.get("panels") or {}
    cov = panels.get("coverage") or {}
    if cov:
        ratio = cov.get("universe_ratio") or {}
        vals = [float(v) for v in ratio.values() if v is not None]
        window = list(cov.get("window") or ["?", "?"])
        while len(window) < 2:
            window.append("?")
        boards = cov.get("board_counts") or {}
        lines += ["## 面板覆盖度", "",
                  "- 窗口: `%s` ~ `%s`" % (window[0], window[1]),
                  "- 月份: 共 %d（partial %d / missing %d）"
                  % (len(cov.get("months") or []),
                     len(cov.get("partial_months") or []),
                     len(cov.get("missing_months") or [])),
                  "- 股票数中位: %s" % _num(cov.get("stock_median"), "%.1f"),
                  "- 覆盖度中位/最差: %s / %s"
                  % (_num(_median(vals), "%.3f"),
                     _num(min(vals) if vals else None, "%.3f")),
                  "- 一字板占比: %s" % _num(cov.get("limit_lock_ratio"), "%.4f"),
                  "- 板块: %s" % (", ".join("%s=%d" % (k, int(v))
                                            for k, v in sorted(boards.items()))
                                  or "n/a"),
                  ""]
    lam = payload.get("lambda_stats") or {}
    if lam:
        lines += ["## λ 显著性与填充", "",
                  "- n_total / n_sig / n_neg: %d / %d / %d"
                  % (int(lam.get("n_total") or 0), int(lam.get("n_sig") or 0),
                     int(lam.get("n_neg") or 0)),
                  "- fill_ratio: %s" % _num(lam.get("fill_ratio"), "%.3f"),
                  "- median_lambda: %s" % _num(lam.get("median_lambda")),
                  "- c_interval_only: `%s`" % bool(lam.get("c_interval_only")),
                  ""]
    window_capacity = panels.get("window_capacity") or {}
    avew = capacity.get("avew") or {}
    if window_capacity and avew:
        lines += ["## 窗长容量", "", "| W | 容量（元） |", "|----|------|"]
        for w in sorted(window_capacity, key=lambda x: int(x)):
            lines.append("| %s | %s |"
                         % (w, _num(window_capacity[w], "%.4g")))
        lines += ["", "- AveW primary: %s / spread: %s / degraded: `%s`"
                  % (_num(avew.get("primary"), "%.4g"),
                     _num(avew.get("spread"), "%.3f"),
                     bool(avew.get("degraded"))), ""]
    decay = payload.get("decay") or {}
    cost = decay.get("cost_by_h") or {}
    if cost and decay.get("alpha0") is not None:
        net = decay.get("net") or {}
        rho_ci = list(decay.get("rho_ci") or [None, None])
        while len(rho_ci) < 2:
            rho_ci.append(None)
        lines += ["## 持有期净收益", "",
                  "- rho: %s（95%% CI %s ~ %s）"
                  % (_num(decay.get("rho"), "%.4f"),
                     _num(rho_ci[0], "%.4f"), _num(rho_ci[1], "%.4f")),
                  "- alpha0: %s" % _num(decay.get("alpha0"), "%.4g"),
                  "", "| h | cost | net |", "|---|------|-----|"]
        for h in sorted(cost, key=lambda x: int(x)):
            lines.append("| %s | %s | %s |"
                         % (h, _num(cost[h], "%.4g"),
                            _num(net.get(str(h)), "%.4g")))
        lines += ["", "- plateau: %s"
                  % (", ".join(str(h) for h in (decay.get("plateau") or []))
                     or "n/a"), ""]
    ratio = payload.get("ratio_diagnostics") or {}
    if ratio:
        lines += ["## 默认口径不一致诊断 ratio(p)（design §9.5）", "",
                  "| p | sqrt(c=0.5) / linear(k=0.025) |", "|------|------|"]
        for p, r in zip(ratio.get("p") or [],
                        ratio.get("ratio_sqrt_over_linear") or []):
            lines.append("| %.3f%% | %.2f |" % (float(p) * 100.0, float(r)))
        lines.append("")
    warnings = payload.get("evidence_warnings") or []
    if warnings:
        lines += ["## 证据警告", ""]
        lines += ["- %s" % w for w in warnings]
        lines.append("")
    lines += ["## 报告限制", "",
              "- 冲击/容量结论按 `[区间]` 报告：分钟数据无逐笔方向，BVC 为代理。",
              "- 2023-04 之后的 `c` 为 `[代理推断]`（无分钟数据）。",
              "- 涨跌停/ST 规则文本 `[未核实]`；一字板仅用 `h==l` 或零量判定。",
              "- λ 为月内日频聚合估计（每股·月 ≤ 交易日数），非分钟级 OLS（W2）。",
              "- net(h) 仅含提供成本口径的持有期；h=5/10 为月换手按 20/h 放大的近似。",
              "- `impact_bps` 按 p95 参与率单点求值，不随持有期 h 变化（R7）。",
              "- `temporary` 超额基准为日频全市场等权，与容量组合可投资域（tradable 为月末快照、无日频口径）存在差异（R9）。",
              ""]
    return "\n".join(lines)


def write_report(payload, json_path, md_path=None):
    """JSON + 可选 Markdown；返回实际落盘路径列表。"""
    written = [str(write_json(payload, json_path))]
    if md_path is not None:
        target = Path(md_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_markdown(payload), encoding="utf-8")
        written.append(str(target))
    return written
