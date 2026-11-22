# 实施文档：P-008 数据行数对齐 —— 四项裁决落地

---
id: v399-p008-data-row-alignment-IMPLEMENTATION
type: design
version: 1.1
status: verified
date: 2026-11-22
depends: [v399-p008-data-row-alignment-DESIGN, v399-p008-data-row-alignment-RESEARCH]
upstream: null
---

> **Feature**: 把 DESIGN v1.1 的 D1-D8（U-1~U-4 裁决）落成可运行代码：运行时 counts-only 对齐证据 + 离线三方分解审计
> **创建日期**: 2026-11-22
> **状态**: verified（v1.1，2026-11-22：Step 6 独立复审 PASS_WITH_FIXES——2×P2 + 3×P3 已处置，见 §12；§9 九项勾选已复核）
> **Spec 步骤**: Step 5-6
> **基于设计**: [DESIGN.md](./DESIGN.md) **v1.1 verified**（Step 4 复审 PASS_WITH_FIXES，§12）
> **基于调研**: [RESEARCH.md](./RESEARCH.md) **v1.5 verified**（v1.5 = Step 8 P3-1 舍入订正）
> **档位**: **T1**（改动 `backtest/execution/shell/` + `scripts/` + `tests/`）

---

## 1. 实施概述

实施分两条独立链路，互不耦合：

1. **运行时证据层**（`panels.py` + `scripts/verify_capacity_impact.py` + `report.py`）：`build()` 在既有月循环内，从**已加载的** `MinuteDayAggregate` 计算逐日唯一码数、逐月匹配日差异与零成交计数，产出 `data_alignment` 块与 3 类非阻断 warning；**不改变** λ / σ / impact / coverage / `panel_hash` 任何数值。
2. **离线审计**（新增 `shell/alignment.py` + `--alignment-audit`）：按需读取分钟文件两列，产出 39 月 A/B/C/D 三方分解与双口径恒等式，写 `out/data_alignment.json/.md`。

代码按「先运行时、后审计、再报告」顺序实施；每步先写会失败的测试（T398-1~8），红→绿记录留 Step 9。

## 2. 工程细节

### 2.1 技术栈

| 组件 | 技术 | 版本 | 验证状态 |
|------|------|------|---------|
| 语言 | Python | `>=3.9`（pyproject.toml L10） | ✅ 本批不使用 3.10+ 语法 |
| 数据帧 | pandas | `>=2.0.0`（pyproject L28） | ✅ 既有依赖 |
| 数值 | numpy | `>=1.22.0`（pyproject L27） | ✅ 既有依赖 |
| 分钟读取 | pyarrow | `>=14.0.0`（optional `[calib]`，pyproject L51） | ✅ 既有依赖，`has_pyarrow()` 守卫 |
| 新增依赖 | 无 | — | ✅ 零新增 |

### 2.2 依赖版本验证

**N/A**——本批不新增、不升级任何三方依赖，也不引入新的标准库 API。仅复用 `json` / `pathlib` / `typing`（均为 3.9 可用）与既有 `pandas` / `numpy` / `pyarrow`。无需 PyPI 查询。

### 2.3 文件结构

```
backtest/execution/shell/
├── panels.py          # 改：DailyRef 两字段 + _align_month/_finalize_alignment/_alignment_warnings + build 接线
├── alignment.py       # 新：audit_alignment + write_alignment_report
└── report.py          # 改：校准 md 增「数据行数对齐」节
scripts/
└── verify_capacity_impact.py   # 改：daily_ref 注入 + attach_panel_meta 透传 + --alignment-audit 分支
tests/
├── test_minute_panels.py       # 改：T398-1~5、T398-8
└── test_data_alignment.py      # 新：T398-6、T398-7
out/
├── data_alignment.json         # 新产物（按需生成，不入库）
└── data_alignment.md           # 同上
```

## 3. 模块实施

### 3.1 运行时对齐（`panels.py`，DESIGN D1/D2/D3/D7）

#### 职责

在 `build()` 既有月循环内完成 counts-only 对齐：逐日唯一码数、匹配日口径月差、日级 >5% 异常、缺日命名、零成交计数；输出 `data_alignment` 与 warning。来自 DESIGN §3.2。

#### 接口签名

```python
@dataclass
class DailyRef(object):
    ...
    rows_by_day: Optional[Dict[str, int]] = None
    dates_by_month: Optional[Dict[str, List[str]]] = None


def _align_month(self, ym, agg):
    """单月 counts-only 对齐；不读盘、不复制 agg。

    Returns:
        dict: month/minute/daily/diff_pct/minute_days/daily_days/
              zero_amount + 私有键 _outliers/_missing/_unmatched
    """


def _finalize_alignment(self, rows, unmatched_minute):
    """汇总月行 → data_alignment（DESIGN §4.2 schema）。"""


def _alignment_warnings(align):
    """纯函数：由 data_alignment 生成 token 化 warning（D-398-2）。"""
```

#### 实施要点

- 逐日计数：`pd.DataFrame({"d": [str(x) for x in agg.date], "c": agg.stock_code}).groupby("d")["c"].nunique()`；不构造逐日集合。
- `matched = [d for d in day_counts.index if d in rows_by_day]`；`minute_sd = int(day_counts.loc[matched].sum())`；`daily_sd = sum(rows_by_day[d] for d in matched)`。
- 差异率：`(minute_sd - daily_sd) / daily_sd * 100`，保留 2 位；`daily_sd == 0` 时记 `None`。
- `outlier`：仅 matched 且 `abs(diff_pct) > 5`；缺日不进 outlier。
- 缺日：`dates_by_month[ym]` 中不在 `day_counts.index` 的日期 → `{"date", "daily"}`；`dates_by_month` 缺失时该月跳过缺日命名（不新增 warning）。
- 零成交：`int((np.asarray(agg.amount_day, dtype=float) == 0.0).sum())`，**不参与** λ / σ / 样本构造。
- `data_alignment` 计算发生在 `_fit_impact` / `_coverage` / `_panel_hash` **之前或之后均可**，但不得修改这些函数的输入；推荐在月循环结束后、`_coverage` 之前组装。
- 所有 numpy 标量显式 `int()` / `float()` 转换（D-398-4）。
- `build()` 返回 dict 追加 `"data_alignment": align`；`warnings.extend(_alignment_warnings(align))`。

#### 低效操作排除

| 潜在低效 | 排除措施 |
|---|---|
| 为对齐二次读取 786 个 feather | 复用月循环已加载的 `agg`（INV-7） |
| 保留 39 月逐日代码集合 | 只保留每月计数与少量异常行 |
| 每次 build 重新推导日频逐日行数 | `daily_ref()` 一次性注入 `rows_by_day`（787 个 int） |
| 逐日 `pivot` / 笛卡尔积 | `groupby(...).nunique()` 单遍聚合 |

### 3.2 离线审计（`shell/alignment.py`，DESIGN D4/D6）

#### 职责

39 月三方分解：`both / minute_only(B) / daily_only(A/C/D)` + 双口径恒等式；只读、按需。来自 DESIGN §3.2/§4.3。

#### 接口签名

```python
def audit_alignment(cfg, loader, close, start=None, end=None):
    """39 月分钟↔日频行数三方分解（只读）。

    Returns:
        dict: window / scope / totals / code_universe / identity /
              months / outlier_days / missing_minute_days
    """


def write_alignment_report(payload, json_path):
    """写 JSON + 同名 .md；返回落盘路径列表。"""
```

#### 实施要点

- 窗口：`lo_m = (start or cfg.minute_start)[:7]`、`hi_m = (end or cfg.minute_end)[:7]`；**按月份判定**（与 `MinuteLoader.available_months()` 同口径），不得按日期截断——否则 `minute_start="2020-01-31"` 会漏掉 2020-01-02~01-30（Step 9 E2 实测发现，D-398-8）。
- 日频日期：`close.index` 归一为 `YYYY-MM-DD`（`str(d)[:10]`），窗口内为 `daily_dates`；日频码集逐日由 `row.notna()` 取列名 `int()`。
- 分钟逐日：`pyarrow.feather.read_table(path, columns=["stock_code", "amount"])`；`_keep_mask` 过滤；`np.unique(codes).astype(np.int32)` 存数组；零成交码 = `groupby("stock_code")["amount"].sum() == 0`（审计口径，允许较慢）。
- 全局码域：分钟 = 全部逐日数组并集；日频 = 窗口 `daily_dates` 非空列并集（**不得**用 `close.shape[1]`，DESIGN F-4）。
- 拆分规则（DESIGN F-7，码级）：
  - `A = daily_only_code ∉ minute_universe`（全部日期）；
  - `C = daily_only_code ∈ minute_universe ∧ 该日 matched`（自动识别截断日，实测 02-26/27 各 1,000）；
  - `D = daily_only_code ∈ minute_universe ∧ 该日 missing`（实测 03-31 的 4,941）。
- 恒等式：`A_matched + C − B = daily_matched − minute`；`A_full + C + D − B = daily_full − minute`；任一残差非 0 → `identity.residual` 记非 0，`main()` 返回 2。
- 输出顺序：`months` 按月份升序；`outlier_days` / `missing_minute_days` 按日期升序；`daily_only_prefix` 按键排序。
- 所有计数/比率在组装 payload 时显式转 Python `int` / `float`（D-398-4），保证 `json.dumps` 可直接落盘。
- `write_alignment_report` 的 md **只从 payload 渲染**，不重新计算（D-398-5）。

#### 低效操作排除

| 潜在低效 | 排除措施 |
|---|---|
| 读取整表 8 列 OHLCV | 列投影仅 `stock_code` / `amount` |
| 计算 σ / pct_change / 锁定 | 审计不做这些计算（与校准链路解耦） |
| 跨月 `concat` 后 groupby | 逐日处理，单日数组落地即释放 DataFrame |
| Python 逐日集合常驻内存 | 逐日码存 `int32` 数组（约 12-14 MB）；集合运算按日临时构造 |

### 3.3 脚本入口（`scripts/verify_capacity_impact.py`，DESIGN D6/D7）

#### 职责

注入日频逐日行数；把 `data_alignment` 透传到校准产物；提供 `--alignment-audit` 按需分支。

#### 实施要点

- `daily_ref()` 追加：

```python
close = P["close"]
rows = close.notna().sum(axis=1)
rows_by_day = dict((str(d)[:10], int(v)) for d, v in rows.items())
dates_by_month = {}
for d in close.index:
    dates_by_month.setdefault(str(d)[:7], []).append(str(d)[:10])
```

- `attach_panel_meta()` 的 `result['panels'].update({...})` 追加 `'data_alignment': minute.get('data_alignment')`。
- `main()` 在 `--calibrate` 分支**之前**新增：

```python
if args.alignment_audit:
    from backtest.execution.config import CalibrationConfig
    from backtest.execution.ports import CalibrationUnavailable
    from backtest.execution.shell.alignment import (audit_alignment,
                                                    write_alignment_report)
    from backtest.execution.shell.loaders import MinuteLoader

    overrides = {'minute_root': args.minute_root} if args.minute_root else {}
    cfg = CalibrationConfig(data_root=args.data_root, **overrides)
    market = build_panels(args.data_root)
    loader = MinuteLoader(cfg.minute_root, sigma_bars=cfg.bvc_sigma_bars)
    try:
        payload = audit_alignment(cfg, loader, market["close"])
    except CalibrationUnavailable as exc:
        print("[alignment] %s" % exc)
        return 2
    target = args.alignment_json or str(SCRIPTS.parent / "out"
                                        / "data_alignment.json")
    written = write_alignment_report(payload, target)
    print("对齐审计: %s" % ", ".join(written))
    return 2 if (payload.get("identity") or {}).get("residual") else 0
```

- 新增参数：`--alignment-audit`（store_true）、`--alignment-json`（默认 `out/data_alignment.json`）。
- 默认路径（无任何 flag）：不 import `alignment`、不构造 `DailyRef` 新字段、不新增输出键（INV-1/INV-9）。
- 审计分支同样受 `has_pyarrow()` 守卫：缺失时抛 `CalibrationUnavailable("pyarrow 未安装…")`，与既有 `--calibrate` 语义一致。

### 3.4 报告渲染（`report.py`，DESIGN D7）

#### 职责

校准 md 增加「数据行数对齐」节；缺键整段跳过（与既有 `coverage` / `lambda_stats` 同风格）。

#### 实施要点

```python
align = panels.get("data_alignment") or {}
if align:
    total = align.get("total") or {}
    lines += ["## 数据行数对齐（P-008 证据层）", "",
              "- 口径: %s；匹配日 / 日频交易日: %s / %s"
              % (align.get("scope"), _num(align.get("matched_days"), "%.0f"),
                 _num(align.get("daily_days"), "%.0f")),
              "- 分钟 / 日频股票×日: %s / %s（%s；全窗口 %s）"
              % (_num(total.get("minute"), "%.0f"),
                 _num(total.get("daily"), "%.0f"),
                 _num(total.get("diff_pct"), "%+.2f%%"),
                 _num(total.get("diff_full_pct"), "%+.2f%%")),
              ...]
```

- 数字统一走 `_num(...)`（`matched_days` 在部分模式下为 `None`，显示 `n/a`）；
- 只读 `panels.data_alignment`，不改 `payload` 其他键；
- 该节位于「面板覆盖度」之后、「λ 显著性与填充」之前。

## 4. 接口实施

### 4.1 `_align_month`（panels.py）

```python
def _align_month(self, ym, agg):
    dates = [str(x) for x in np.asarray(agg.date, dtype=object)]
    frame = pd.DataFrame({"d": dates,
                          "c": np.asarray(agg.stock_code, dtype=np.int64)})
    day_counts = frame.groupby("d", sort=True)["c"].nunique()
    has_daily = self.daily is not None and self.daily.rows_by_day is not None
    rows_by_day = (self.daily.rows_by_day or {}) if self.daily else {}
    month_dates = ((self.daily.dates_by_month or {}).get(ym, [])
                   if self.daily else [])
    days_by_month = (self.daily.days_by_month or {}) if self.daily else {}
    matched = ([d for d in day_counts.index if d in rows_by_day]
               if has_daily else list(day_counts.index))
    minute_sd = int(day_counts.loc[matched].sum()) if matched else 0
    daily_sd = int(sum(int(rows_by_day[d]) for d in matched)) if has_daily else 0
    diff = ((minute_sd - daily_sd) / float(daily_sd) * 100.0
            if daily_sd else None)
    outliers = []
    for d in matched:
        n = rows_by_day.get(d, 0)
        if not n:
            continue
        dev = (int(day_counts.loc[d]) - int(n)) / float(n) * 100.0
        if abs(dev) > 5.0:
            outliers.append({"date": d, "minute": int(day_counts.loc[d]),
                             "daily": int(n), "diff_pct": round(dev, 2)})
    missing = ([{"date": d, "daily": int(rows_by_day[d])}
                for d in month_dates
                if d in rows_by_day and d not in day_counts.index]
               if has_daily else [])
    return {"month": ym, "minute": minute_sd, "daily": daily_sd,
            "diff_pct": (round(diff, 2) if diff is not None else None),
            "minute_days": int(day_counts.size),
            "daily_days": int(len(month_dates)) if month_dates
            else int(days_by_month.get(ym, day_counts.size)),
            "zero_amount": int((np.asarray(agg.amount_day, dtype=float)
                                == 0.0).sum()),
            "_outliers": outliers, "_missing": missing,
            "_unmatched": int(sum(1 for d in day_counts.index
                                  if d not in rows_by_day)) if has_daily else 0}
```

**部分模式（`has_daily=False`）**：`minute` 仍按全部分钟日累计，`daily=0`、`diff_pct=None`、`missing=[]`，`daily_rows_available=false`；`matched_days` / 顶层 `daily_days` 在 `_finalize_alignment` 记 `None`（复审 F-3），不伪造日频读数；月行 `daily_days` 回退为 `days_by_month` 值或分钟日数，仅供诊断、不进合计。

**签名一致性**：与 DESIGN §3.2 模块表「单月 counts-only 对齐」一致 ✅；`_outliers` / `_missing` / `_unmatched` 为私有键，`_finalize_alignment` 消费后**不得**进入公开 schema（T398-8）。

### 4.2 `_finalize_alignment`（panels.py）

```python
def _finalize_alignment(self, rows, unmatched_minute):
    has = bool(self.daily is not None and self.daily.rows_by_day is not None)
    public = [dict((k, v) for k, v in r.items() if not k.startswith("_"))
              for r in rows]
    total_minute = int(sum(r["minute"] for r in rows))
    total_daily = int(sum(r["daily"] for r in rows))
    missing = [m for r in rows for m in r["_missing"]]
    daily_full = int(total_daily + sum(m["daily"] for m in missing))
    zero = int(sum(r["zero_amount"] for r in rows))
    peak = max(rows, key=lambda r: (r["zero_amount"] / float(r["minute"])
                                    if r["minute"] else 0.0),
               default=None)
    return {
        "scope": "matched_days",
        "window": [self.cfg.minute_start[:7], self.cfg.minute_end[:7]],
        "months": len(rows),
        "matched_days": (int(sum(r["minute_days"] for r in rows)
                             - unmatched_minute) if has else None),
        "daily_days": (int(sum(r["daily_days"] for r in rows))
                       if has else None),   # 复审 F-3：部分模式不伪造日频交易日数
        "total": {"minute": total_minute,
                  "daily": total_daily if has else None,
                  "diff_pct": _pct(total_minute, total_daily) if has else None,
                  "daily_full": daily_full if has else None,
                  "diff_full_pct": (_pct(total_minute, daily_full)
                                    if has else None)},
        "monthly": public,
        "outlier_days": sorted([o for r in rows for o in r["_outliers"]],
                               key=lambda x: x["date"]),
        "missing_minute_days": sorted(missing, key=lambda x: x["date"]),
        "unmatched_minute_days": int(unmatched_minute),
        "daily_rows_available": has,
        "zero_amount": {"pairs": zero,
                        "share_pct": round(zero / float(total_minute) * 100.0, 4)
                        if total_minute else 0.0,
                        "peak_month": (peak["month"]
                                       if peak and peak["minute"] and zero > 0
                                       else None),   # 复审 F-4：零成交为 0 时不报峰值月
                        "peak_share_pct": round(
                            peak["zero_amount"] / float(peak["minute"]) * 100.0, 4)
                        if peak and peak["minute"] and zero > 0 else 0.0},
        "thresholds": {"outlier_abs_pct": 5.0},
    }
```

`_pct(a, b)` 为模块内纯函数：`round((a - b) / float(b) * 100.0, 2)`，`b <= 0` 返回 `None`。

**`build()` 接线**（其余逻辑零改动）：

```python
# 月循环前
align_rows, align_unmatched = [], 0
...
# 月循环内，agg, cached = self._load_month(ym) 之后
row = self._align_month(ym, agg)
align_rows.append(row)
align_unmatched += int(row["_unmatched"])
...
# 月循环后、_coverage 之前
alignment = self._finalize_alignment(align_rows, align_unmatched)
warnings.extend(_alignment_warnings(alignment))
...
return {..., "data_alignment": alignment, "evidence_warnings": warnings}
```

**`_alignment_warnings` 实现**（模块级纯函数）：

```python
def _alignment_warnings(align):
    out = []
    if not align.get("daily_rows_available"):
        out.append("data_alignment_partial: 缺少日频逐日行数，仅记录分钟侧")
        return out
    outliers = align.get("outlier_days") or []
    if outliers:
        out.append("data_alignment_truncation: " + "; ".join(
            "%s (%+.2f%%)" % (o["date"], o["diff_pct"]) for o in outliers))
    missing = align.get("missing_minute_days") or []
    if missing:
        out.append("data_alignment_missing_day: " + "; ".join(
            "%s (daily=%d)" % (m["date"], m["daily"]) for m in missing))
    return out
```

### 4.3 `audit_alignment`（alignment.py）

模块导入（固定最小集）：

```python
import json
from pathlib import Path

import numpy as np

from ..ports import CalibrationUnavailable
from .loaders import _keep_mask, has_pyarrow
```

```python
def audit_alignment(cfg, loader, close, start=None, end=None):
    if not has_pyarrow():
        raise CalibrationUnavailable("pyarrow 未安装（pip install .[calib]）")
    lo = _dstr(start or cfg.minute_start)[:7]
    hi = _dstr(end or cfg.minute_end)[:7]
    daily_dates, daily_codes = _daily_side(close, lo, hi)
    minute_by_day, zero_by_day = _minute_side(loader, lo, hi)
    ...
    return {"window": [lo, hi], "scope": {...}, "totals": {...},
            "code_universe": {...}, "identity": {...},
            "months": [...], "outlier_days": [...],
            "missing_minute_days": [...]}
```

**签名一致性**：与 DESIGN §4.3 一致 ✅（`start` / `end` 默认取 cfg）。

关键内部函数（模块私有）：

| 函数 | 职责 |
|---|---|
| `_dstr(value)` | `str(value)[:10]` 归一（D-398-6） |
| `_daily_side(close, lo, hi)` | 日频日期列表 + **逐日非空码 int32 数组**（非 Python set：787 日 × ~4.5k 码 ≈ 14 MB；集合运算用 `np.intersect1d` / `np.setdiff1d`，或单日临时 set——复审 F-1，禁止持久化 787 个 Python set，否则与 DESIGN §5.7 方案 G 的否决理由自相矛盾） + 码域并集 |
| `_minute_side(loader, lo, hi)` | 逐日唯一码数组（int32）+ 零成交码集 |
| `_decompose(dates, daily, minute, zero)` | both/B/daily_only + A/C/D |
| `_identity(totals)` | 双口径恒等式与残差 |
| `_prefix_counts(codes)` | 日频独有码首位分布 |

### 4.4 `write_alignment_report`（alignment.py）

```python
def write_alignment_report(payload, json_path):
    target = Path(json_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    md = target.with_suffix(".md")
    md.write_text(_render_alignment_md(payload), encoding="utf-8")
    return [str(target), str(md)]
```

**签名一致性**：与 DESIGN §4.3 一致 ✅。`_render_alignment_md` 只读 payload（D-398-5）。

### 4.5 报告节（report.py）

见 §3.4；与 DESIGN §3.1「校准 md + 数据行数对齐节」一致 ✅。

## 5. 兼容性

### 5.1 Python 版本兼容

| Python 版本 | 支持 | 说明 |
|---|---|---|
| 3.9 | ✅ | 不使用 `match` / PEP 604 联合类型 / 内建泛型注解；沿用 `Dict/List/Optional` |
| 3.10+ | ✅ | 向后兼容 |

### 5.2 依赖兼容

| 依赖组合 | 兼容性 | 验证 |
|---|---|---|
| pandas 2.x + numpy 1.22+ | ✅ | 既有代码已使用 `groupby(...).nunique()` / `np.unique` |
| pyarrow 14+（optional） | ✅ | 审计分支复用 `has_pyarrow()` 守卫语义；缺失时按 `CalibrationUnavailable` 处理 |

### 5.3 向后兼容

- `DailyRef` 新字段位于末尾且默认 `None` → 既有 3 处构造（tests L86 / L799 / L814）零改动；
- `build()` 返回值新增键，不删不改既有键 → `assemble_panels`（整字典合并）与 `attach_panel_meta`（选择性读取）均兼容；
- 校准 md 新增节有 `if align:` 守卫 → 旧 payload 渲染结果不变；
- 默认 CLI 路径无新参数时行为与字节输出不变（INV-1）。

## 6. 错误处理实施

| 错误场景（DESIGN §7） | 实施处理 | 验证方式 |
|---|---|---|
| `rows_by_day` 未注入 | `daily_rows_available=false` + `data_alignment_partial` warning；继续构建 | T398-5 |
| `dates_by_month` 缺失 | 该月不产生 `missing_minute_days`；不新增 warning | T398-2（提供时命中） |
| 分钟独有日 | 不计入 matched；`unmatched_minute_days` 计数 | T398-8 键集 + E2 |
| 日频某日 0 行 | `diff_pct=None`，不进 outlier | 单测边界（T398-1 变体） |
| 单月 `agg` 为空 | 既有「整月剔除 / partial」路径不变 | 既有 T397-2 |
| 审计分钟根缺失 | `CalibrationUnavailable` → 打印 `[alignment] ...` → exit 2 | CLI 冒烟（T398-6 附带） |
| 审计恒等式残差 ≠ 0 | `_identity_failed(totals)` 独立守卫 → payload 注入 `alignment_identity_failed` + md 顶部警示行 + `main()` exit 2（双口径 + 标记三重检查，Step 10 P2-1/P2-2/P3-1 处置） | T398-9（守卫四态 / md 两态 / CLI exit 2 + exit 0） |

## 7. 不变式实施

| 不变式（DESIGN §8） | 实施位置 | 验证方式 |
|---|---|---|
| INV-1 默认 SHA 不变 | 默认 `main()` 分支零改动 | Step 9/10 跑前备份 / 跑后 / 复跑三方比对 |
| INV-2 `panel_hash` 不变 | `_panel_hash`（L424-L440）不读 `data_alignment` | T398-4（注入/不注入对照） |
| INV-3 39 月窗口不变 | `build()` 的 `target` / `usable` 逻辑零改动 | 既有覆盖度测试 + E2 |
| INV-4 零成交 bar 保留 | `_align_month` 只计数，不改 `agg` | T398-3（λ/σ 逐位相同） |
| INV-5 告警非阻断 | 无新门禁；`coverage_gate` 零改动；`--calibrate` 退出码不变 | grep + 既有覆盖度测试 |
| INV-6 恒等式残差 0 | `_identity(...)` + 落盘前断言 | T398-6 |
| INV-7 校准零额外分钟 IO | `_align_month` 入参为已加载 `agg` | 代码评审 + 运行计时 |
| INV-8 `DailyRef` 向后兼容 | 新字段默认 None | 既有 3 处构造回归 |
| INV-9 审计按需 | `alignment` 仅在 `--alignment-audit` 分支 import | CLI 无 flag 冒烟 |

## 8. 测试策略

### 8.1 单元测试

| 编号 | 文件 | 断言 | 红态来源 |
|---|---|---|---|
| T398-1 | `test_minute_panels.py` | 注入 `rows_by_day` 构造 −80% 日 → `outlier_days` 命中 + `data_alignment_truncation` warning | 现无 `data_alignment` 键 |
| T398-2 | `test_minute_panels.py` | `dates_by_month` 多 1 日 → `missing_minute_days` + warning | 现无缺日命名 |
| T398-3 | `test_minute_panels.py` | 3 行 `amount_day=0` → `zero_amount.pairs=3`；λ/σ/`panel_hash` 与基线逐位相同 | 现无该统计 |
| T398-4 | `test_minute_panels.py` | 注入/不注入 `rows_by_day` 两次 build → `panel_hash` 逐位相同 | 新字段未实现，对照不可构造 |
| T398-5 | `test_minute_panels.py` | `DailyRef(days_by_month={})` → `data_alignment_partial`，不抛 | 无该 warning |
| T398-6 | `test_data_alignment.py` | 4 日小样本（含 1 截断日 + 1 缺日）→ A/B/C/D 精确值 + 双口径残差 0；且 `write_alignment_report` 落盘的 `.md` 含恒等式行与 `residual = 0`（复审 F-2：md 渲染面纳入红→绿） | 模块不存在 |
| T398-7 | `test_data_alignment.py` | `render_markdown` 含/不含 `data_alignment` 的两态 | 现无该节 |
| T398-8 | `test_minute_panels.py` | `monthly` 每行键集固定（7 键）；无 `_outliers` 等私有键 | 现无该块 |

### 8.2 集成 / E2 实跑

| 检查 | 命令 | 期望 |
|---|---|---|
| 校准重建 | `python scripts/verify_capacity_impact.py --calibrate --panel-cache` | `data_alignment.total.minute=3,442,081`、`daily=3,523,738`、`daily_full=3,528,865`；`zero_amount.pairs=7,917`；warning 含 02-26/27、03-31 |
| 审计重建 | `python scripts/verify_capacity_impact.py --alignment-audit` | `A_matched=87,574`、`A_full=87,760`、`C=2,000`、`D=4,941`、`B=7,917`；残差 0 |
| 默认路径 | `python scripts/verify_capacity_impact.py` | SHA256 前 8 = `82728CE1`（与复审基线一致） |

> **Step 9 实测（2026-11-22）**：`--alignment-audit` exit 0（82 s，含 `build_panels`）；`totals` minute 3,442,081 / daily_matched 3,523,738 / daily_full 3,528,865；A_matched 87,574 / A_full 87,760 / B 7,917 / C 2,000 / D 4,941；`identity.residual = residual_full = 0`；码域 5,029 / 5,273 / 244 / 0，前缀 {9:239, 8:3, 3:1, 6:1}；逐月 39 行合计与总计逐位一致。窗口按月份判定（D-398-8）修复了首轮按日期过滤漏 2020-01 的问题（首轮 matched 770/771）。
>
> **校准重建实测（2026-11-22）**：`--calibrate --panel-cache` exit 0；`panels.data_alignment.total` = 3,442,081 / 3,523,738（−2.32%）/ 3,528,865（−2.46%）；`monthly` 39 行 × 7 键、私有键 0；`outlier_days` 2 条（02-26 −27.55 / 02-27 −27.68）；`missing_minute_days` 1 条（2023-03-31，daily 5127）；`zero_amount` = 7,917 / 0.23% / 2022-05 / 1.0843%；两条 warning 入 `evidence_warnings`；`coverage.months` 39；`panel_hash` 前 8 = `dfcc4e1d`（与 P-003 基线一致）。

### 8.3 属性/护栏测试

- T398-4 兼具属性测试性质：`data_alignment` 的注入状态不影响 `panel_hash`；
- T398-8 为 schema 护栏：公开 `monthly` 键集固定，防止私有键泄漏。

### 8.4 Step 9 红→绿记录（F5）

**红（实现前，2026-11-22）**：

```
python -m pytest tests/test_minute_panels.py -k "T398" tests/test_data_alignment.py -q
8 failed, 34 deselected in 1.32s   (exit 1)
```

失败形态：T398-1~5/8 = `KeyError: 'data_alignment'`；T398-6 = `ModuleNotFoundError: backtest.execution.shell.alignment`；T398-7 = 报告无「数据行数对齐」节。

**绿（实现后，同一命令、同一断言集未改）**：

```
python -m pytest tests/test_minute_panels.py -k "T398" tests/test_data_alignment.py -q
8 passed, 34 deselected in 0.20s   (exit 0)
```

**最终代码回归（2026-11-22）**：

```
python -m pytest tests/test_minute_panels.py tests/test_data_alignment.py -q
42 passed, 5 warnings in 186.34s   (exit 0)
```

全量套件（并行后台，启动于 D-398-8 修复前）：`2100 passed, 15 skipped, 172 warnings in 1078.65s`（exit 0），作为回归基线；P-008 两测试文件已在最终代码上复跑全绿。

**Step 10 ADD 修复红→绿（2026-11-22，T398-9）**：

```
python -m pytest tests/test_data_alignment.py -q
红（实现前）：1 failed, 2 passed in 0.46s   (exit 1)   # AttributeError: _identity_failed
绿（实现后）：3 passed in 0.33s             (exit 0)
```

ADD 修复落盘：`alignment.py`（`_identity_failed` 守卫 + payload 注入 + md 警示行）、`scripts/verify_capacity_impact.py`（exit 2 三重检查）。

**Step 10 修复后最终回归（2026-11-22）**：

```
python -m pytest tests/test_minute_panels.py tests/test_data_alignment.py -q
43 passed, 5 warnings in 175.94s   (exit 0)
```

**实现落盘**：`backtest/execution/shell/panels.py`（DailyRef + `_align_month` / `_finalize_alignment` / `_alignment_warnings` / `_pct` + build 接线）、`backtest/execution/shell/alignment.py`（新增）、`backtest/execution/shell/report.py`（对齐节）、`scripts/verify_capacity_impact.py`（`daily_ref` 注入 / `attach_panel_meta` 透传 / `--alignment-audit` 分支）。

## 9. 幻觉抑制审查（Step 6 Review，已于 2026-11-22 执行）

### 9.1 依赖版本验证

- [x] 所有依赖版本已查询 PyPI 确认存在 —— **N/A（零新增依赖）**；numpy/pandas/scipy/pyarrow 均为既有 `pyproject.toml` 声明（L27/L28/L29/L51），本批不升版
- [x] 无虚构的库或函数 —— 逐项核对：`_keep_mask` / `has_pyarrow`（loaders.py L28/L34）、`render_markdown`（report.py L46）、`MinuteDayAggregate`（loaders.py L65）、`FakeLoader.load_month_regression`（tests L51）均真实存在
- [x] 版本兼容性已验证 —— Python 3.9 语法面：`max(default=)`（3.4+）、`json.dumps(ensure_ascii=False)`、`pathlib.with_suffix`、`typing.Dict/List/Optional`；pandas 2.x：`Series.items` / `groupby.nunique`；pyarrow：`read_table(columns=)`（E1 实测签名，见 §12.3）

### 9.2 接口签名验证

- [x] 所有接口签名与 DESIGN §4 一致 —— `DailyRef` 两字段（§4.1）、`audit_alignment(cfg, loader, close, start, end)`（§4.3）、`write_alignment_report(payload, json_path)`（§4.3）、`data_alignment` schema 13 键（§4.2）逐项对照
- [x] 所有签名可实现 —— 无不可能的类型组合；`_align_month` 入参为既有 `MinuteDayAggregate`

### 9.3 实施与设计对齐

- [x] 每个模块对应 DESIGN §3.2 的一个模块 —— 5/5（DailyRef / _align_month / audit_alignment / report 渲染 / script 入口）
- [x] 每个接口对应 DESIGN §4 的一个接口 —— 4/4（§4.1-§4.4 ↔ §4.5）
- [x] 无设计未覆盖的实施 —— 衍生需求 D-398-1~7 已登记（§11）

### 9.4 低效操作排除

- [x] 无 O(n²) 可优化操作 —— 审计逐日 O(日 × 码)，运行时单遍 groupby
- [x] 无不必要 I/O —— 运行时零额外读取（INV-7）；审计仅 2 列投影
- [x] 无重复计算 —— 审计 md 只渲染 payload（D-398-5）

> 说明：§9 各项已于 Step 6 独立 pass（异构基座第二视角）逐项核验后勾选（RULE-1：勾选发生在正文完稿之后的独立审查轮）。

## 10. 实施步骤

### Step 1：运行时对齐（`panels.py`）

- 文件：`backtest/execution/shell/panels.py`
- 内容：`DailyRef` 两字段；`_align_month` / `_finalize_alignment` / `_alignment_warnings` / `_pct`；`build()` 月循环接线与返回键。
- 测试：T398-1~5、T398-8（先红）。

### Step 2：离线审计（`alignment.py`）

- 文件：`backtest/execution/shell/alignment.py`（新）
- 内容：六个私有 helper + `audit_alignment` + `write_alignment_report`。
- 测试：T398-6（先红，4 日小样本，含 `.md` 落盘断言）。

### Step 3：报告节（`report.py`）

- 文件：`backtest/execution/shell/report.py`
- 内容：`panels.data_alignment` 守卫渲染。
- 测试：T398-7（先红）。

### Step 4：脚本入口（`verify_capacity_impact.py`）

- 文件：`scripts/verify_capacity_impact.py`
- 内容：`daily_ref` 注入、`attach_panel_meta` 透传、CLI 两参数与审计分支。
- 测试：CLI 冒烟（无 flag 默认路径）+ E2 实跑。

### Step 5：回归与实跑

- 全量 `pytest`；默认 SHA 三方比对；39 月校准与审计重建；
- 回写 PROGRESS / CHECKLIST（Step 7-10）。

## 11. 衍生需求登记（Step 8 复核）

| 编号 | 衍生需求 | 来源 | 验收 |
|---|---|---|---|
| D-398-1 | `rows_by_day` / `dates_by_month` 仅由脚本注入，`panels.py` 不读盘 | DESIGN §3.2 职责边界 | 静态读码：`panels.py` 无 `read_pickle` / `read_feather` |
| D-398-2 | warning 文案由纯函数 `_alignment_warnings` 生成，不在 `build()` 内散落字符串 | DESIGN §4.4 token 契约 | T398-1/2/5 断言 token 前缀 |
| D-398-3 | C/D 的日期集不硬编码：C = matched 且 rest>0；D = missing；实测恰为 02-26/27 与 03-31 | DESIGN §3.3 F-7 的码级规则 | T398-6 + E2 数字（2,000 / 4,941） |
| D-398-4 | 所有对外计数/比率显式转 Python `int` / `float` | DESIGN §4.2 尾注 | 校准 JSON `json.dumps` 成功 |
| D-398-5 | 审计 md 只从 payload 渲染，不重算 | DESIGN §4.3 | 静态读码：`_render_alignment_md` 无 `close` / `loader` 参数 |
| D-398-6 | 日期字符串在两侧入口统一 `str(value)[:10]` | DESIGN F-4/F-7 的日期键一致性 | T398-6 小样本用 `Timestamp` 索引仍命中 |
| D-398-7 | 对齐装配拆为三个纯函数（`_align_month` / `_finalize_alignment` / `_alignment_warnings`），`build()` 只做接线；`_pct` 为模块内唯一比率 helper | DESIGN §3.2 模块表 + §4.4 token 契约（复审 F-5 登记） | T398-8 键集 + 静态读码：`build()` 内无 warning 字符串字面量 |
| D-398-8 | 审计窗口按**月份**判定（`[lo[:7], hi[:7]]`），不按日期截断；与 `MinuteLoader.available_months()` 同口径 | Step 9 E2 实测：按日期过滤漏 2020-01-02~01-30（matched 770 而非 786） | T398-6 月中起点断言 + E2 786/787、3,442,081 |
| D-398-9 | 恒等式失败可见化：`_identity_failed(totals)` 独立守卫（重算五项口径，不复用分解循环中间量）→ payload 顶层注入 `alignment_identity_failed` + md 顶部警示行 | Step 10 ADD 审计 P2-1（DESIGN §7 L319 契约未实现） | T398-9（守卫四态 / md 两态含非恒真对照 / CLI exit 2+0） |
| D-398-10 | CLI exit 2 条件升级为 `residual or residual_full or alignment_identity_failed` 三重检查 | Step 10 ADD 审计 P2-2（残差≠0 分支零测试）+ P3-1（原仅查匹配日口径） | T398-9 第 4 段（exit 2 + exit 0 进程内 CLI） |
| D-398-11 | 已知口径边界登记（不修）：① 运行时 `_align_month` 只统计 usable 月（整月剔除后），审计侧统计窗口内全部 feather——本仓 39 月无整月剔除故两口径一致，出现整月剔除时将系统性分歧（ADD P3-2）；② `_pct` 在 panels（b<=0→None）与 alignment（not b→None，负 b 反号）边界不同，当前调用点 b 恒为正计数无实际影响（ADD P3-3） | Step 10 ADD 审计 P3-2 / P3-3 | 静态读码 + E2 双路径数字互证（3,442,081 逐位一致） |

---

## 12. 异构复审记录（Step 6，2026-11-22）

### 12.1 复审方式与输入

- **异构性（RULE-5）**：复审会话与 IMPLEMENTATION v1.0 撰写会话属**不同模型基座**；reviewer 只标记（单向权限），修复按 F 编号落盘后升 v1.1；
- **审查输入**：IMPLEMENTATION v1.0 draft 全文 + DESIGN v1.1 verified + RESEARCH v1.4 verified + 源码只读核对（`panels.py` / `loaders.py` / `report.py` / `tests/test_minute_panels.py` / `pyproject.toml`）+ 运行时 API 签名实测。

### 12.2 维度矩阵

| 维度 | 结论 | 关键依据 |
|------|------|---------|
| V1 签名与 DESIGN 一致性 | PASS | `DailyRef` / `audit_alignment` / `write_alignment_report` / `data_alignment` 13 键 schema 逐项一致；3 个 warning token 与 DESIGN §4.4 示例文案一致 |
| V2 接口可实现性 | PASS_WITH_FIXES | **F-1**（`_daily_side` 逐日 Python set 与 DESIGN §5.7 否决理由矛盾）修复后闭合 |
| V3 依赖与 stdlib 兼容 | PASS | E1 实测（§12.3）；Python 3.9 面、pandas 2.x、pyarrow 14 全部可用；零新增依赖 |
| V4 测试清单可执行性 | PASS_WITH_FIXES | **F-2**（`_render_alignment_md` 零测试覆盖）修复后闭合；测试缝（FakeLoader / `_write_day` / `render_markdown`）锚点全部核实 |
| V5 不变式与衍生需求可核性 | PASS_WITH_FIXES | **F-3 / F-4**（部分模式语义、零成交峰值边界）修复后闭合；**F-5** 补登记 D-398-7 |

### 12.3 机械取证（E1，复审轮新增）

| 取证手段 | 结果 |
|---|---|
| `inspect.signature(pyarrow.feather.read_table)` 含 `columns` | ✅（列投影可实现） |
| `pd.Series.items` / `DataFrame.groupby.nunique` 存在（pandas 2.2.3） | ✅ |
| `max(..., default=None)` / stdlib `json` / `pathlib` / `typing` / `dataclasses` | ✅ 全部 3.9+ 可用 |
| `_keep_mask`（loaders.py L28）/ `has_pyarrow`（L34）/ `render_markdown`（report.py L46）/ `FakeLoader.load_month_regression`（tests L51） | ✅ 锚点全部真实 |
| `pyproject.toml`：`requires-python = ">=3.9"`（L10）、依赖行 L27/L28/L29/L51 | ✅ 与 §2.1 一致 |

### 12.4 发现与处置（全部已落盘至 v1.1）

| 编号 | 级别 | 位置 | 发现 | 处置 |
|------|------|------|------|------|
| F-1 | **P2 内存矛盾** | §4.3 helper 表 | `_daily_side` 返回「逐日码集」= 持久化 787 个 Python set（约数百 MB），与 DESIGN §5.7 方案 G 的否决理由及本文 §3.2 低效排除表自相矛盾 | 改为逐日非空码 int32 数组（≈14 MB），集合运算用 `np.intersect1d`/`np.setdiff1d` 或单日临时 set |
| F-2 | **P2 测试缺口** | §8.1 / §10 Step 2 | `write_alignment_report` 的 md 渲染（`_render_alignment_md`）无任何红→绿覆盖——唯一未验证的产出面 | T398-6 扩展：断言 `.md` 落盘且含恒等式行与 `residual = 0` |
| F-3 | P3 语义 | §4.1/§4.2 | 部分模式顶层 `daily_days` 回退为分钟日计数，易误读为日频交易日数 | 部分模式改 `None`；月行回退仅诊断用，加注 |
| F-4 | P3 边界 | §4.2 | `zero_amount.pairs == 0` 时 `peak_month` 仍取首月（share=0 的伪峰值） | `zero == 0` 时 `peak_month=None` |
| F-5 | P3 登记 | §11 | `_finalize_alignment` / `_pct` 纯函数拆分未登记衍生需求 | 补 D-398-7 |

### 12.5 结论

**PASS_WITH_FIXES**：2×P2 + 3×P3，全部修复已落盘至本版（v1.1）；V1-V5 无未闭合项；9 项勾选与实际一致。实施文档可进入 Step 7（CHECKLIST）与 Step 9（TDD 实现）。

---

**Review 签字**: Step 6 独立复审（异构基座第二视角，RULE-5；五维矩阵 + E1 API 签名实测；F-1/F-2 P2 与 F-3/F-4/F-5 P3 已处置）日期: 2026-11-22
