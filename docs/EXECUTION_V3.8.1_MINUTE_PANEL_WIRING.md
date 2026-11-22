# EXECUTION — v3.8.1 真实分钟面板编排接线

> **版本**: v1.3（2026-11-20；v1.2→v1.3：步骤 10 审计裁决落地——§3.5 行业缺失行改与实现对齐（A-4）、覆盖度门禁行补留痕口径（A-3），见 [2026-11-20-v3.8.1-minute-panel-wiring-audit.md](audit/2026-11-20-v3.8.1-minute-panel-wiring-audit.md)；v1.1→v1.2：步骤 8 一致性 review 修正 M2/M3/M6/M7/M8/M11，见 [CONSISTENCY_REVIEW_V3.8.1_MINUTE_PANEL_WIRING.md](audit/CONSISTENCY_REVIEW_V3.8.1_MINUTE_PANEL_WIRING.md)；v1.0→v1.1：步骤 6 复审修正 F1-F10，见 §10）　**日期**: 2026-11-19 产出 / 2026-11-20 复审
> **对应设计**: [DESIGN_V3.8.1_MINUTE_PANEL_WIRING.md](private/DESIGN_V3.8.1_MINUTE_PANEL_WIRING.md) **v1.1**（§13 步骤 4 复审 PASS_WITH_FIXES；R2 勘误 2026-11-20）
> **对应调研**: [RESEARCH_V3.8.1_MINUTE_PANEL_WIRING.md](research/RESEARCH_V3.8.1_MINUTE_PANEL_WIRING.md) **v1.2**（§9 步骤 2 复审）
> **实施基线**: [EXECUTION_V3.8.0_EXECUTION_CAPACITY.md](EXECUTION_V3.8.0_EXECUTION_CAPACITY.md) §2.5（校准纪律）
> **默认路径纪律**: `python scripts/verify_capacity_impact.py`（无参数）输出与当前逐位一致，`out/capacity_impact.json` SHA256 `82728CE1…` 不变
> **测试基线**: 2026 passed / 15 skipped / 0 failed（v3.9.0 终态）
> **目标**: 2026 + 21 = **2047 passed** / 15 skipped / 0 failed（T381-22 为门禁本身，不计用例；实测 2047/15/0）

---

## §0 摘要、工件状态与落点

### 0.1 交付内容

| 编号 | 交付 | 形态 |
|------|------|------|
| E0 | 配置字段（19）+ 分钟 loader 过滤修复 + `load_month_regression` + 日级聚合数据结构 | 改 `backtest/execution/config.py`、`backtest/execution/shell/loaders.py` |
| E1 | 日频层面板（容量 / 衰减 / 执行 / temporary / 成本） | `shell/panels.py::build_daily_panels` |
| E2 | 分钟层面板（λ 回归 / 填充 / 观测样本 / 覆盖度） | `shell/panels.py::MinutePanelBuilder` |
| E3 | 编排微调（κ 情景接线 + `block_size_mode` 校验） | 改 `shell/runner.py`（2 处，默认逐位不变） |
| E4 | 脚本接线（组合面板、CLI、覆盖率门禁、结果后处理） | 改 `scripts/verify_capacity_impact.py` |
| E5 | 报告四段扩展 | 改 `shell/report.py` |
| E6 | 22 例测试 + 性能与验收 | 新增 `tests/test_minute_panels.py`；追加 `tests/test_execution_capacity.py` |

### 0.2 工件状态

| 工件 | 状态 |
|------|------|
| 调研文档 | v1.2（B1-B18 / U1-U14 / 22 例；§9 复审闭环） |
| 设计文档 | v1.1（W1-W10；§13 复审闭环 F1-F6 + Q1-Q4 + R1-R5；R2 勘误 2026-11-20） |
| 实施文档 | 本文件 **v1.2**（步骤 5 产出；步骤 6 复审修正 F1-F10 见 §10：5 P2 + 5 P3 全修，PASS_WITH_FIXES；步骤 8 一致性修正 M2/M3/M6/M7/M8/M11 见 CONSISTENCY_REVIEW_V3.8.1） |
| Checklist | [CHECKLIST_V3.8.1_MINUTE_PANEL_WIRING.md](audit/CHECKLIST_V3.8.1_MINUTE_PANEL_WIRING.md) v1.1（步骤 7 产出 84 项；步骤 8 一致性修正 10 处；步骤 9/10 回填） |
| 代码 | **已实施**（步骤 9 TDD，2026-11-20；8 文件白名单 + 21 例 + 全量门禁） |

### 0.3 与路线图的映射

对应 [PROJECT_STATUS.md](PROJECT_STATUS.md) 路线图条目 `v3.8.1 (候选) 真实分钟面板编排接线 — λ 面板 + lambda_fill_ratio + partial_month`。
本批只给 `--calibrate` 分支接线，不改默认路径、不改任何默认容量口径（设计 §0.3 不变量 1/4）。

### 0.4 W1-W10 实施落点

| 决策 | 落点（文件 : 符号） | 对应任务 |
|------|--------------------|----------|
| W1 分层窗口 | `config.py`（`minute_start/minute_end`）；`panels.py::MinutePanelBuilder.months` | E0 / E2 |
| W2 日频聚合 λ | `loaders.py::MinuteLoader.load_month_regression`；`panels.py::_month_lambda` | E0 / E2 |
| W3 观测样本 | `panels.py::_impact_samples` → `impact_samples` | E2 |
| W4 筛选/填充/降级 | `panels.py::_fill_lambda` → `lambda_stats` | E2 |
| W5 单位与代码 | `loaders.py::MIN_STOCK_CODE` / 过滤；`panels.py::_adv_lookup`（`zfill(6)`） | E0 / E2 |
| W6 覆盖度门禁 | `panels.py::PanelCoverage` / `coverage_gate`；脚本 `exit 2` | E2 / E4 |
| W7 regime / 窗口容量 | 脚本 `build_portfolio_panels`；`panels.py::build_daily_panels` 透传 | E1 / E4 |
| W8 衰减链与 cost(h) | `panels.py::build_daily_panels` | E1 |
| W9 配置旋钮 | `config.py`（16→19）；`runner.py`（κ + `block_size_mode`） | E0 / E3 |
| W10 报告与 CLI | `report.py::render_markdown`；脚本 `--no-minute/--panel-cache` | E4 / E5 |

### 0.5 实施级细化（对设计 §2 的落地补丁；步骤 6 已裁决采纳 B/C/D/E，见 §10.4）

设计 v1.1 已冻结口径与决策，但以下 4 点在设计层未写死到「可直接编码」的粒度，本文件给出实施方案。**均不改变任何 W 决策的结论**：

| # | 问题 | 实施方案 | 影响 |
|---|------|----------|------|
| S1 | **G1：`cost_by_h` 循环依赖**——成本需要校准后的 `c`，而 `c` 在 `run_calibration` 内部拟合 | 分钟层先建（产出 `impact_fit = {primary, params, sigma_median}`），脚本把它作为可选参数注入 `build_daily_panels(cfg, daily, portfolio, impact_fit=None)`。`impact_fit` 与 runner 用**同一观测样本、同一 `fit` 实现**，拟合确定性 ⇒ `c` 逐位相等；T381-12 断言 `impact_fit.params == result.models[primary].params`。`impact_fit=None` 时 `cost_by_h` 仅含费率项并写 warning `cost_impact_unavailable` | 设计 §4 数据流顺序调整为「分钟层 → 日频层」；`build_daily_panels` 增加 1 个带默认值的参数 |
| S2 | `MinutePanelBuilder` 需要 ADV / 行业 / 规模 / 交易日数，设计只写了「日频 ADV 月末快照对齐」 | 新增 `DailyRef` 轻量容器，由脚本从既有 `build_panels` 产出构造后注入；`panels.py` 不读盘、不 import `scripts` | 设计 §2.1 构造函数补 `daily=` 参数 |
| S3 | runner 输出的 `result` 是固定键集，`lambda_stats` / `panels.coverage` 无处安放 | 脚本在 `write_report` 前做**结果后处理**（`attach_panel_meta`），把 `panels` / `lambda_stats` / `impact_samples` / `impact_curve` 挂到 `result` | runner 零改动，满足不变量 4 |
| S4 | 设计 §2.4 说 `build_portfolio_panels` 负责「regime→窗口→日收益→temporary→rho/alpha/cost」，但纯统计部分放入脚本会破坏「panels 纯函数可测」 | 拆分：脚本 `build_portfolio_panels` 只做**市场数据装配**（权重、交易额、参与者率、regime、窗口容量、日/月超额、turnover）；`build_daily_panels` 只做**统计映射**（`temporary`/`rho_series`/`alpha0`/`cost_by_h`/`plateau_sd`） | 职责边界写入 §2.3 / §2.6；总代码量不变 |

**R2 勘误**（设计 §13.4 注记）：设计称「`load_month` 现状 L85 跨日 `pct_change` 需按日重置」——实际 [loaders.py L71-121](file:///f:/Coding/factor_pipeline/backtest/execution/shell/loaders.py#L71-L121) 是**逐文件（逐日）循环**，`pct_change` 天然按日重置，且每分组首 bar 为 NaN。**本批无需任何修复动作**；新增 `load_month_regression` 沿用同一逐日框架即可。实施文档记录此勘误，步骤 6 复审可回改设计 R2 表述。

---

## §1 任务分解（E0-E6）

```
E0 ──┬── E2（分钟面板）── E1（日频面板，消费 impact_fit）── E4 ── E6
     ├── E3（runner 微调，与面板无耦合）
     └── E5（report 扩展，只依赖 payload 键集）
```

| 任务 | 前置 | 产出 | 验收出口 |
|------|------|------|---------|
| E0 | — | `CalibrationConfig` 19 字段；`MIN_STOCK_CODE` 与过滤修复；`MinuteDayAggregate` + `load_month_regression` | `pytest tests/test_minute_panels.py -k "loader"`（T381-01/02/03/04/05） |
| E1 | E0 | `panels.py::build_daily_panels`（temporary / rho / alpha / cost / plateau_sd） | `pytest tests/test_minute_panels.py -k "daily"` |
| E2 | E0 | `panels.py::MinutePanelBuilder`（λ / 填充 / 观测样本 / 覆盖度 / panel_hash） | `pytest tests/test_minute_panels.py -k "minute"` |
| E3 | — | `runner.py`：κ 情景接 `cfg.kappa`；`block_size_mode` 校验 | `pytest tests/test_execution_capacity.py` |
| E4 | E1,E2 | 脚本 `--calibrate` 真实装配 + `--no-minute` / `--panel-cache` / 覆盖率门禁 | `python scripts/verify_capacity_impact.py --calibrate --no-minute` |
| E5 | E4 | `render_markdown` 四段（覆盖度 / λ / 窗口容量 / 净收益） | `pytest tests/test_minute_panels.py -k "report"` |
| E6 | E1-E5 | 22 例全绿 + 性能 + SHA 门禁 | 全量 `pytest -q`；见 §7 |

**关键路径**：E0 → E2 → E1 → E4 → E6。E3/E5 可与 E1/E2 并行。

---

## §2 逐文件接口签名与回退点

### 2.1 `backtest/execution/config.py`（E0）

改 [config.py L19-34](file:///f:/Coding/factor_pipeline/backtest/execution/config.py#L19-L34)：删 `tau_max_minutes`，新增 4 字段，16 → 19。

```python
@dataclass(frozen=True)
class CalibrationConfig(object):
    """校准全参数；构建后用 ``dataclasses.replace`` 生成变体。"""

    data_root: str = r"E:\Ashare_data"
    minute_root: Optional[str] = r"E:\Level 1 Data"
    sample_start: str = "2020-01-31"
    sample_end: str = "2026-01-31"
    minute_start: str = "2020-01-31"       # v3.8.1：分钟层起点
    minute_end: str = "2023-03-31"         # v3.8.1：分钟层终点（实际数据止 2023-03-30）
    participation_grid: Tuple[float, ...] = (0.001, 0.005, 0.01, 0.02, 0.05)
    sigma_clip: Tuple[float, float] = (0.005, 0.20)
    bvc_sigma_bars: int = 20
    block_size_mode: str = "auto"          # auto | sqrt | iid（v3.8.1 仅 auto 可用）
    windows: Tuple[int, ...] = (24, 36, 48, 60)
    kappa: float = 1.5
    p_cap: float = 0.10
    d_max: int = 5
    default_horizon: int = 20
    lambda_min_days: int = 10              # v3.8.1：每股×月最小有效日数
    adv_window_days: int = 21              # v3.8.1：ADV 均值窗（与脚本 rolling(21) 对齐）
    lambda_p_threshold: float = 0.05
    seed: int = 20261118
```

- `config_hash()` 不改；字段变化只影响校准工件，默认路径不构造 `CalibrationConfig`，SHA 不受影响。
- 模块 docstring 版本标注 `v3.8.1`（原为 v3.8.0）。

### 2.2 `backtest/execution/shell/loaders.py`（E0）

#### 2.2.1 过滤修复（W5，B13）

改 [loaders.py L79-80](file:///f:/Coding/factor_pipeline/backtest/execution/shell/loaders.py#L79-L80)，并在 `__all__` 前加常量：

```python
MIN_STOCK_CODE = 1          # 分钟 stock_code 为整数（000001 -> 1），下界不得写 100000
MAX_STOCK_CODE = 1000000    # 上界排斥 6 位
EXCLUDE_CODE = (390000, 400000)   # 指数/特殊代码段
```

```python
keep = (df["stock_code"] >= MIN_STOCK_CODE) & (df["stock_code"] < MAX_STOCK_CODE)
keep &= ~((df["stock_code"] >= EXCLUDE_CODE[0]) & (df["stock_code"] < EXCLUDE_CODE[1]))
```

同一表达式在 `load_month` 与 `load_month_regression` 中**只允许出现一次**——抽成模块级私有函数：

```python
def _keep_mask(codes):
    """分钟代码过滤（W5）：保留 1..999999，剔除 390000-399999。"""
    return ((codes >= MIN_STOCK_CODE) & (codes < MAX_STOCK_CODE)
            & ~((codes >= EXCLUDE_CODE[0]) & (codes < EXCLUDE_CODE[1])))
```

#### 2.2.2 新增日级聚合结构与 `load_month_regression`（W2）

```python
@dataclass
class MinuteDayAggregate(object):
    """单月「股票×日」聚合（逐行 = 一只股票的一个交易日）。"""

    date: np.ndarray          # 'YYYY-MM-DD'（object）
    stock_code: np.ndarray    # int64
    signed_day: np.ndarray    # 元；锁定 bar 的 s_t 记 0（W2 裁决）
    amount_day: np.ndarray    # 元；全量保留（含锁定 bar）
    ret_day: np.ndarray       # close_last / open_first - 1
    sigma: np.ndarray         # 每股月度 σ（同股票所有行相同）
    n_bars: np.ndarray        # 当日 bar 数
    limit_lock: np.ndarray    # 当日 lock 占比 >= 0.5


class MinuteLoader(object):
    # ... __init__ / available_months / load_month 不动 ...

    def load_month_regression(self, ym):
        """逐日流式 → 「股票×日」聚合（W2）；缺失抛 CalibrationUnavailable。"""
        if not has_pyarrow():
            raise CalibrationUnavailable("pyarrow 未安装（pip install .[calib]）")
        import pyarrow.feather as feather
        import pandas as pd

        files = sorted(self.root.glob("%s-*.feather" % ym))
        if not files:
            raise CalibrationUnavailable("分钟数据缺失: %s" % ym)
        rows = []          # type: list
        month = {}         # type: Dict[int, list]  code -> [rsum, r2sum, n]
        for path in files:
            date = path.stem[:10]
            table = feather.read_table(path)
            cols = [c for c in ("time", "stock_code", "open", "high", "low",
                                "close", "volume", "amount")
                    if c in table.column_names]
            df = table.select(cols).to_pandas()
            df = df.loc[_keep_mask(df["stock_code"].to_numpy())]
            df = df.sort_values(["stock_code", "time"], kind="mergesort")
            if df.empty:
                continue
            codes = df["stock_code"].to_numpy()
            ret = df.groupby("stock_code")["close"].pct_change()
            sigma_roll = ret.groupby(df["stock_code"]).transform(
                lambda s: s.rolling(self.sigma_bars, min_periods=2).std(ddof=1))
            with np.errstate(divide="ignore", invalid="ignore"):
                ratio = ret.to_numpy() / sigma_roll.to_numpy()
            phi = normal_cdf(np.where(np.isfinite(ratio), ratio, 0.0))
            locked = detect_limit_lock(
                df["high"].to_numpy(), df["low"].to_numpy(),
                df["close"].to_numpy(), df["open"].to_numpy(),
                df["volume"].to_numpy()).astype(bool)
            score = np.where(locked, 0.0, df["amount"].to_numpy() * (2.0 * phi - 1.0))
            tmp = pd.DataFrame({
                "stock_code": codes,
                "score": score,
                "amount": df["amount"].to_numpy(),
                "ret": ret.to_numpy(),
                "open": df["open"].to_numpy(),
                "close": df["close"].to_numpy(),
                "locked": locked.astype(float),
                "one": 1.0,
            })
            day = tmp.groupby("stock_code", sort=True).agg(
                signed=("score", "sum"),
                amount=("amount", "sum"),
                rsum=("ret", lambda s: float(np.nansum(s.to_numpy()))),
                r2sum=("ret", lambda s: float(np.nansum(s.to_numpy() ** 2))),
                n=("one", "sum"),
                lock=("locked", "sum"),
                open_first=("open", "first"),
                close_last=("close", "last"))
            day_codes = day.index.to_numpy(dtype=np.int64)
            for code, row in zip(day_codes, day.to_numpy(dtype=float)):
                cur = month.get(int(code))
                if cur is None:
                    month[int(code)] = [row[2], row[3], row[4]]
                else:
                    cur[0] += row[2]
                    cur[1] += row[3]
                    cur[2] += row[4]
            rows.append((date, day_codes, day.to_numpy(dtype=float)))
        if not rows:
            raise CalibrationUnavailable("过滤后无有效股票: %s" % ym)

        # 月度 σ（与 load_month 同口径：r2sum 方差）
        sigma_map = {}
        for code, (rsum, r2sum, n) in month.items():
            n = max(float(n), 1.0)
            var = (r2sum - rsum ** 2 / n) / max(n - 1.0, 1.0)
            sigma_map[code] = float(np.sqrt(max(var, 0.0)))

        # day 聚合列序（named agg 依声明顺序）：0 signed, 1 amount, 2 rsum,
        # 3 r2sum, 4 n, 5 lock, 6 open_first, 7 close_last（F1 修正）
        out_date, out_code, out_signed = [], [], []
        out_amount, out_ret, out_n, out_lock = [], [], [], []
        for date, day_codes, mat in rows:
            open_first, close_last = mat[:, 6], mat[:, 7]
            with np.errstate(divide="ignore", invalid="ignore"):
                ret_day = np.where(open_first > 0.0, close_last / open_first - 1.0, np.nan)
            out_date.extend([date] * day_codes.size)
            out_code.append(day_codes)
            out_signed.append(mat[:, 0])
            out_amount.append(mat[:, 1])
            out_ret.append(ret_day)
            out_n.append(mat[:, 4])
            out_lock.append(mat[:, 5] / np.maximum(mat[:, 4], 1.0) >= 0.5)
        codes = np.concatenate(out_code)
        return MinuteDayAggregate(
            date=np.asarray(out_date, dtype=object),
            stock_code=codes,
            signed_day=np.concatenate(out_signed),
            amount_day=np.concatenate(out_amount),
            ret_day=np.concatenate(out_ret),
            sigma=np.asarray([sigma_map[int(c)] for c in codes], dtype=float),
            n_bars=np.concatenate(out_n).astype(np.int64),
            limit_lock=np.concatenate(out_lock))
```

要点（实施时必须逐条满足）：

1. 逐文件（=逐日）循环，`pct_change` 天然按日重置（R2 勘误，无需额外处理）；
2. 锁定 bar 的 `score` 记 0，`amount` 全量累加（W2 / B9 裁决）；
3. `open_first` / `close_last` 依赖 `sort_values(["stock_code","time"])` 的稳定排序；
4. `sigma` 用**月度** `rsum/r2sum/n`（与 `load_month` 同式），不写 `sigma_clip`（截断在 `panels.py`，设计 §2.2 注）；
5. `load_month` 保留不动（覆盖度与既有测试仍用它）。

### 2.3 新增 `backtest/execution/shell/panels.py`（E1/E2）

文件头与常量：

```python
# -*- coding: utf-8 -*-
"""v3.8.1 面板装配：分钟层 λ / 观测样本 + 日频层容量 / 衰减。

设计依据：DESIGN_V3.8.1 §2；实施依据：EXECUTION_V3.8.1 §2.3。
不变量：本模块不得 import ``scripts``；日频组合面板由脚本注入。
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Dict, List, Mapping, Optional

import numpy as np
import pandas as pd

from ..core.decay import estimate_rho
from ..core.impact import (LinearImpact, LogImpact, PowerImpact, SqrtImpact,
                           cross_val_rmse, select_models, temporary_share)
from ..ports import CalibrationUnavailable
from .loaders import MinuteLoader, has_pyarrow
from .runner import fit_lambda_hac

__all__ = ["PanelCoverage", "DailyRef", "MinutePanelBuilder",
           "build_daily_panels", "assemble_panels", "coverage_gate"]

IMPL_MIN = 0.95          # W6 中位覆盖度下限
MONTH_MIN = 0.90         # W6 最差月下限
PARTIAL_MIN_DAYS = 20    # W6 partial_month 下限
SAMPLE_CAP = 200000      # W3 观测样本上限
FEE_BPS = 10             # W8 费率（与脚本 FEE_BPS 一致）
COST_HORIZONS = (5, 10, 20)
MODELS = (SqrtImpact(), LinearImpact(), LogImpact(), PowerImpact())
```

#### 2.3.1 `PanelCoverage` 与 `DailyRef`

```python
@dataclass
class PanelCoverage(object):
    window: tuple                 # ("2020-01", "2023-03")
    months: list                  # 实际参与月份
    partial_months: list          # 文件数 < 交易日数（且 >= 20 日）
    missing_months: list          # 无文件的月份
    stock_median: float           # 逐月股票数中位数
    universe_ratio: dict          # {month: 面板股票数 / 日频当月非空股数}
    limit_lock_ratio: float       # 锁定股票占比（月均）
    board_counts: dict            # {"沪主板": n, "深主板": n, "创业板": n, "科创板": n}

    def as_dict(self):
        return {"window": list(self.window), "months": list(self.months),
                "partial_months": list(self.partial_months),
                "missing_months": list(self.missing_months),
                "stock_median": float(self.stock_median),
                "universe_ratio": {str(k): float(v)
                                   for k, v in self.universe_ratio.items()},
                "limit_lock_ratio": float(self.limit_lock_ratio),
                "board_counts": dict(self.board_counts)}


@dataclass
class DailyRef(object):
    """分钟层对齐日频所需的只读参考（脚本构造，panels 不读盘）。"""

    adv: pd.DataFrame        # 月末 ADV（元），index=月末 Timestamp，列=6 位代码
    universe: pd.DataFrame   # 月末非空布尔（mask & ret.notna()）
    industry: pd.DataFrame   # 月末一级行业（字符串，NaN 允许）
    mv_rank: pd.DataFrame    # 月末 mv 五分位（1..5，NaN 允许）
    days_by_month: dict      # {ym: 交易日数}（用于 partial_month 判定）
```

#### 2.3.2 `MinutePanelBuilder`（E2）

```python
class MinutePanelBuilder(object):
    """分钟层：λ 回归 / 显著性填充 / 观测样本 / 覆盖度。"""

    def __init__(self, cfg, loader=None, daily=None, cache_dir=None):
        self.cfg = cfg
        self.daily = daily
        self.loader = loader or MinuteLoader(
            cfg.minute_root, sigma_bars=cfg.bvc_sigma_bars)
        self.cache_dir = Path(cache_dir) if cache_dir else None

    def months(self):
        """cfg.minute_start/minute_end 与可用月份求交（W1）。"""
        lo, hi = self.cfg.minute_start[:7], self.cfg.minute_end[:7]
        return [m for m in self.loader.available_months() if lo <= m <= hi]

    def build(self, months=None):
        """返回 dict：lambda_pvalues / lambda_stats /
        impact_samples（{p,impact,sigma} 数组，供 runner 消费）/
        impact_samples_meta（{n,cap,granularity,sampling}，供报告 W10）/
        impact_fit / coverage / panel_hash / evidence_level。
        依赖缺失抛 CalibrationUnavailable（由脚本捕获降级）。"""
        if self.daily is None:
            raise CalibrationUnavailable("缺少日频参考面板（ADV/行业/规模）")
        if not has_pyarrow():
            raise CalibrationUnavailable("pyarrow 未安装（pip install .[calib]）")
        months = list(months or self.months())
        if not months:
            raise CalibrationUnavailable("分钟窗口内无可用月份")
        ...
```

`build()` 内部 6 步（顺序固定）：

| 步 | 动作 | 关键约束 |
|----|------|----------|
| 1 | 月份清单 + `partial_months`/`missing_months` | 文件数 < `days_by_month[ym]` 且 ≥20 → partial（保留并记录）；<20 → 剔除 + warning |
| 2 | 逐月 `loader.load_month_regression(ym)` → 每股×日 `(s_d, r_d, σ_m, n_days)` | `x_d = s_d / ADV`；`ADV` 取 `daily.adv` 当月行、列名 `"%06d" % code` |
| 3 | 逐股 `fit_lambda_hac(x, r)` → λ、p | 有效观测 `n_days >= cfg.lambda_min_days`；σ 先 `clip(*cfg.sigma_clip)` |
| 4 | 筛选 + 缩尾 + 行业×规模填充（W4） | `p < cfg.lambda_p_threshold` 且 `λ > 0` 才纳入；组内 1%/99% 缩尾；`fill_ratio > 0.30` → `c_interval_only=True` + warning |
| 5 | 观测样本（W3）与 `impact_fit`（S1） | `p=|s_d|/ADV`（clip 1e-6..1）、`impact=|r_d|`、`σ` 截断；按月分层抽样（`cfg.seed`），总量 ≤ `SAMPLE_CAP`；4 模型 fit + `cross_val_rmse` + `select_models` |
| 6 | `coverage` 与 `panel_hash` | `panel_hash` 见 §3.4；覆盖度只用**修复后**面板股票数 |

关键实现片段：

```python
    def _adv_lookup(self, ym):
        """{int code: ADV 元}；缺失/非正记 NaN（不填 0）。

        按 'YYYY-MM' 标签对齐（月末交易日不固定，禁止用 Timestamp 精确匹配）。
        """
        labels = [str(i)[:7] for i in self.daily.adv.index]
        if ym not in labels:
            return {}
        row = self.daily.adv.iloc[labels.index(ym)]
        out = {}
        for code, value in row.items():
            try:
                key = int(str(code))
            except (TypeError, ValueError):
                continue
            out[key] = float(value) if np.isfinite(value) and value > 0 else np.nan
        return out

    def _month_row(self, frame, ym):
        """取某一月的月末截面（行业 / mv 五分位用）；无该月返回 None。"""
        labels = [str(i)[:7] for i in frame.index]
        return frame.iloc[labels.index(ym)] if ym in labels else None

    def _month_lambda(self, ym, agg):
        """逐股 λ/p（W2/W4）；返回 (pvalues, rows)。"""
        adv = self._adv_lookup(ym)
        lo, hi = float(self.cfg.sigma_clip[0]), float(self.cfg.sigma_clip[1])
        sigma = np.clip(agg.sigma, lo, hi)
        ind_row = self._month_row(self.daily.industry, ym)   # W4 分组填充输入（F10）
        mv_row = self._month_row(self.daily.mv_rank, ym)
        pvalues, rows = [], []
        for code in np.unique(agg.stock_code):
            m = agg.stock_code == code
            a = adv.get(int(code))
            if not np.isfinite(a):
                continue
            if int(m.sum()) < int(self.cfg.lambda_min_days):
                continue
            x = agg.signed_day[m] / a
            r = agg.ret_day[m]
            ok = np.isfinite(x) & np.isfinite(r)
            if int(ok.sum()) < int(self.cfg.lambda_min_days):
                continue
            try:
                fit = fit_lambda_hac(x[ok], r[ok])
            except ValueError:
                continue
            pvalues.append(float(fit["p"]))
            key6 = str(int(code)).zfill(6)
            rows.append({"code": int(code), "month": ym, "lambda": float(fit["lambda"]),
                         "p": float(fit["p"]), "n_days": int(ok.sum()),
                         "industry": None if ind_row is None else ind_row.get(key6),
                         "mv_bucket": None if mv_row is None else mv_row.get(key6)})
            for xi, ri, si in zip(x[ok], r[ok], sigma[m][ok]):
                self._samples.append((
                    float(np.clip(abs(xi), 1e-6, 1.0)),   # p（参与率绝对值）
                    float(abs(ri)),                       # impact（已实现收益绝对值）
                    float(si), int(code), ym))            # sigma / 代码 / 月份
        return pvalues, rows
```

> `self._samples` 在 `build()` 开始时初始化为空列表，每月 `_month_lambda` 结束后立刻按月度配额下采样（§3.6），避免 4.3M 行常驻内存。
>
> 性能注记（F10）：逐股分组索引应一次构建（`np.argsort(agg.stock_code, kind="mergesort")` 后切片，或 pandas `groupby().indices`），禁止逐股循环内做全表布尔掩码（O(N·K)，约 74k×3400）。

填充（W4）：

```python
    def _fill_lambda(self, rows):
        """显著性+符号筛选 → 组内缩尾 → 行业×mv 五分位中位数填充。"""
        sig = [r for r in rows if r["p"] < self.cfg.lambda_p_threshold and r["lambda"] > 0.0]
        n_total = len(rows)
        n_sig = len(sig)
        n_neg = sum(1 for r in rows if r["lambda"] <= 0.0)
        # 组内 1%/99% 缩尾（先按 (month, industry, mv_bucket) 分组）
        # 填充：组内 λ 中位数；组内无有效值 → 当月全样本中位数 → 全样本中位数
        ...
        fill_ratio = 1.0 - (n_sig / float(n_total)) if n_total else 1.0
        return {"lambda_stats": {
                    "n_total": n_total, "n_sig": n_sig, "n_neg": n_neg,
                    "fill_ratio": float(fill_ratio),
                    "median_lambda": float(np.median([r["lambda"] for r in sig])) if sig else None,
                    "c_interval_only": bool(fill_ratio > 0.30),
                    "by_group": {...}},
                "panel": {r["code"]: float(r["lambda"]) for r in sig}}
```

观测样本分层（W3；v3.9.8 P-010 后改写）：

```python
def _sample_indices(p, sigma, cap):
    """按 (p, sigma) 排序后等距取索引；不引入 np.random 状态。"""
    if p.size <= cap:
        return np.arange(p.size)
    order = np.lexsort((sigma, p))
    take = np.linspace(0, order.size - 1, int(cap)).astype(np.int64)
    return order[np.unique(take)]
```

`build()` 末尾对 `p/impact/sigma/month` 四个数组使用同一 `idx` 切片
（`p, impact, sigma, month = p[idx], impact[idx], sigma[idx], month[idx]`），
保证月聚类标签与样本逐行对齐。原 `_stratified_sample` 只提取三个数组、
会丢弃 `code/ym`，已于 v3.9.8 删除（P-010 D1）。

> 设计写「分层抽样」，实现为「排序后等距」，保证同 seed 双跑逐位一致且覆盖全分位区间；不引入 `np.random` 额外状态。

`impact_fit`（S1）：

```python
        cv = cross_val_rmse(list(MODELS), p, impact, sigma)
        primary, tied = select_models(cv)
        fitted = {}
        for model in MODELS:
            try:
                fitted[model.name] = model.fit(p, impact, sigma)
            except ValueError:
                fitted[model.name] = None
        impact_fit = {"primary": primary,
                      "params": fitted.get(primary),
                      "sigma_median": float(np.median(sigma)),
                      "cv_rmse": {k: (None if not np.isfinite(v) else float(v))
                                  for k, v in cv.items()}}
```

#### 2.3.3 `build_daily_panels`（E1，S4 拆分后的统计侧）

```python
def build_daily_panels(cfg, daily, portfolio, impact_fit=None):
    """日频层统计映射（纯函数）。

    输入 ``portfolio`` 由脚本 ``build_portfolio_panels`` 产出：
      aum_ref / excess_m / excess_d / turnover_m / regime_p95 /
      window_capacity / notional / adv / p_cost / sigma_port
    ``impact_fit`` 为分钟层预拟合结果（S1）；None 时成本仅含费率项。
    """
    aum_ref = float(portfolio.get("aum_ref", 1e10))
    warnings = []
    ex_m = pd.Series(portfolio["excess_m"], dtype=float).dropna()
    ex_d = pd.Series(portfolio["excess_d"], dtype=float).dropna()
    out = {"aum_ref": aum_ref, "cap": float(cfg.p_cap),
           "regime_p95": {str(k): (None if v is None else float(v))
                          for k, v in portfolio["regime_p95"].items()},
           "window_capacity": {str(k): (None if v is None else float(v))
                               for k, v in portfolio["window_capacity"].items()},
           "notional": np.asarray(portfolio["notional"], dtype=float),
           "adv": np.asarray(portfolio["adv"], dtype=float)}
    if ex_m.size < 24:
        warnings.append("月超额序列仅 %d 期（<24），rho 与 net(h) 仅供参考" % ex_m.size)
    rho = 1.0
    try:
        rho, _lo, _hi = estimate_rho(ex_m.to_numpy())
    except ValueError as exc:
        warnings.append("rho 无法估计（%s），按 1.0 处理" % exc)
    out["rho_series"] = [float(v) for v in ex_m.to_numpy()]
    out["alpha0"] = float(ex_m.mean()) if ex_m.size else None
    out["plateau_sd"] = float(aum_ref * ex_m.std(ddof=1)) if ex_m.size > 2 else 0.0
    # W8：std(rho_series)=月超额波动；与 net(h) 同为月尺度元单位（F3 修正）
    out["temporary"] = ({"r1": ex_d.to_numpy()[:-1], "rev1": ex_d.to_numpy()[1:]}
                        if ex_d.size > 2 else None)
    turnover_m = float(pd.Series(portfolio["turnover_m"], dtype=float).dropna().mean())
    impact_bps = 0.0
    if impact_fit and impact_fit.get("params") and portfolio.get("p_cost"):
        model = {m.name: m for m in MODELS}[impact_fit["primary"]]
        frac = float(model.predict(
            np.asarray([float(portfolio["p_cost"])]),
            np.asarray([float(portfolio.get("sigma_port") or 0.02)]),
            impact_fit["params"])[0])
        impact_bps = max(0.0, frac * 1e4)
    else:
        warnings.append("cost_impact_unavailable: 成本仅含费率项 %dbp" % FEE_BPS)
    out["cost_by_h"] = {
        int(h): float((20.0 / h) * aum_ref * turnover_m * 2.0
                      * (FEE_BPS + impact_bps) / 1e4)
        for h in COST_HORIZONS}
    out["evidence_warnings"] = warnings
    return out
```

口径核对（W8）：`h=20 → (20/20)·AUM·turnover·2·(fee+impact)/1e4`，fee=10bp；与脚本 `base_net = ex - 2·t·fee/1e4` 的单边乘 2 一致。`plateau_sd` 与 `net(h)` 同为元单位（月尺度，F3）。

> `daily` 参数当前统计侧未消费，保留以对齐设计 §2.1 签名（R10）。

#### 2.3.4 `assemble_panels` 与 `coverage_gate`

```python
def assemble_panels(minute_panels, daily_panels, evidence_level):
    """分钟层 + 日频层合并；键冲突以后者为准并记 warning（防御性）。"""
    out, warnings = {}, []
    for part in (minute_panels or {}, daily_panels or {}):
        for key, value in part.items():
            if key == "evidence_warnings":
                warnings.extend(value or [])
                continue
            if key in out:
                warnings.append("面板键冲突: %s（后者覆盖）" % key)
            out[key] = value
    out["evidence_level"] = evidence_level
    out["evidence_warnings"] = warnings
    return out


def coverage_gate(coverage, min_median=IMPL_MIN, min_month=MONTH_MIN):
    """W6 硬门禁；接受 PanelCoverage 或 dict；返回 (ok, messages)。"""
    cov = (coverage.as_dict() if hasattr(coverage, "as_dict")
           else dict(coverage or {}))
    ratio = dict(cov.get("universe_ratio") or {})
    vals = [float(v) for v in ratio.values() if v is not None and np.isfinite(v)]
    msgs = []
    if not vals:
        return False, ["覆盖度为空（分钟层未产出有效月份）"]
    med, worst = float(np.median(vals)), float(min(vals))
    ok = med >= min_median and worst >= min_month
    if med < min_median:
        msgs.append("覆盖度中位 %.3f < %.2f" % (med, min_median))
    if worst < min_month:
        msgs.append("最差月覆盖度 %.3f < %.2f" % (worst, min_month))
    if not int((cov.get("board_counts") or {}).get("深主板", 0)):
        ok = False
        msgs.append("深市主板股票数为 0（过滤回归，W6 板块断言）")
    return ok, msgs
```

### 2.4 `backtest/execution/shell/runner.py`（E3）

只改 2 处，默认输出逐位不变：

**(a) `block_size_mode` 校验**（函数入口，约 L191 之后、`panels = dict(...)` 之前）：

```python
    if str(cfg.block_size_mode) != "auto":
        raise ValueError(
            "block_size_mode=%r 未实现（v3.8.1 仅支持 'auto'）"
            % (cfg.block_size_mode,))
```

**(b) κ 情景接线**（[runner.py L269-271](file:///f:/Coding/factor_pipeline/backtest/execution/shell/runner.py#L269-L271)）：

```python
        levels = sorted({1.0, float(cfg.kappa), 2.0})
        scenarios = {("%.1f" % k): apply_kappa(
            max(regime_p95.values()), aum_ref, cap, k, capacity_fn)
            for k in levels}
```

> `cfg.kappa=1.5` 时键集与顺序 `("1.0","1.5","2.0")` 与现状完全一致。R5（`kappa=1.0` → 两键）为合理行为，报告按实际键渲染。
> 其余（`impact_samples`/`lambda_pvalues`/`temporary`/`regime_p95`/`window_capacity`/`rho_series`/`cost_by_h`/`notional`/`adv`）**零改动**。

### 2.5 `backtest/execution/shell/report.py`（E5）

`write_json` 不变；`render_markdown(payload)` 签名不变，新增 4 段（键缺失即整段跳过，`--no-minute` 不报错），保留 `evidence_level` 必填校验（[report.py L22-27](file:///f:/Coding/factor_pipeline/backtest/execution/shell/report.py#L22-L27)）。

| 段 | 数据源键 | 内容 |
|----|----------|------|
| 面板覆盖度 | `payload["panels"]["coverage"]` | window / 月数 / partial / 股票数中位 / 覆盖度中位与最差 / 板块计数 |
| λ 显著性与填充 | `payload["lambda_stats"]` | n_total / n_sig / n_neg / fill_ratio / median_lambda / `c_interval_only` |
| 窗长容量 | `payload["capacity"]["avew"]` + `payload["panels"]["window_median"]` | 逐 W 容量（`payload["panels"]["window_capacity"]`）/ spread / degraded / primary |
| 持有期净收益 | `payload["decay"]` | `rho`(+CI) / `alpha0` / `cost_by_h` / `net(h)` / `plateau` / `default_horizon` |

「报告限制」追加 3 条：

```python
              "- λ 为月内日频聚合估计（每股·月 ≤22 个观测），非分钟级 OLS（W2）。",
              "- 2023-04 之后的 c 为 `[代理推断]`（无分钟数据）。",
              "- net(h) 仅含提供成本口径的持有期；h=5/10 为月换手按 20/h 放大的近似。", ""
```

渲染实现约束：全部数值用 `%.4g` / `%.3f` 显式格式化，`None` 渲染为 `n/a`；禁止 `str(dict)` 直出。

### 2.6 `scripts/verify_capacity_impact.py`（E4）

#### 2.6.1 `build_panels` 增补键（默认路径不消费）

[build_panels L87-128](file:///f:/Coding/factor_pipeline/scripts/verify_capacity_impact.py#L87-L128) 的返回字典追加 2 个键：

```python
    return dict(
        close=close, factor=factor, ret=ret, mask=mask, tradable=tradable,
        mv_m=mv_m, amt_m=amt_m, amt_rank=amt_rank, sig_m=sig_m,
        facts=facts,
        adj_price=adj_price,          # v3.8.1：日频组合收益（--calibrate 使用）
    )
```

新增键为**加法**，默认路径不读取，输出 JSON 不受影响（已核对：`build_panels` 无外部测试断言键集）。

#### 2.6.2 新增 `build_portfolio_panels`（市场数据装配，约 45 行）

```python
def build_portfolio_panels(P, cfg, kind='exQ1_EW_tradable', aum_ref=1e10):
    """参考组合的市场数据装配（W7/W8）：权重→交易额→参与率→regime→窗口。"""
    spec = {name: (k, kw, tr) for name, k, kw, tr in VARIANTS}[kind]
    w = make_weights(P, spec[0], spec[1], spec[2])
    universe = P['mask'] & P['tradable'] if spec[2] else P['mask']
    ev = evaluate(w, P, universe)
    traded = month_trades(w)
    adv = P['amt_m']
    part = (traded * aum_ref) / adv.where(adv > 0)
    part = part.where(part > 0)

    amt_total = adv.sum(axis=1).dropna()
    bucket = pd.qcut(amt_total.rank(method='first'), 5,
                     labels=['Q1', 'Q2', 'Q3', 'Q4', 'Q5'])
    regime_p95 = {}
    for name in ('Q1', 'Q2', 'Q3', 'Q4', 'Q5'):
        rows = bucket.index[bucket == name]
        vals = part.reindex(rows).to_numpy().ravel()
        vals = vals[np.isfinite(vals)]
        regime_p95[name] = float(np.percentile(vals, 95)) if vals.size else None

    window_capacity, months = {}, list(part.index)
    for W in cfg.windows:
        caps = []
        for i in range(max(0, len(months) - W + 1)):
            vals = part.iloc[i:i + W].to_numpy().ravel()
            vals = vals[np.isfinite(vals)]
            if vals.size:
                caps.append(capacity_from_p95(
                    float(np.percentile(vals, 95)), aum_ref, cfg.p_cap))
        window_capacity[int(W)] = float(np.mean(caps)) if caps else None

    traded_v = traded.to_numpy()
    adv_v = adv.reindex_like(traded).to_numpy()
    ok = np.isfinite(traded_v) & (traded_v > 0) & np.isfinite(adv_v) & (adv_v > 0)
    p_all = part.to_numpy()
    p_all = p_all[np.isfinite(p_all)]
    return dict(
        aum_ref=aum_ref,
        excess_m=ev['series']['ex'],
        excess_d=daily_portfolio_excess(P, w),
        turnover_m=ev['series']['t'],
        regime_p95=regime_p95,
        window_capacity=window_capacity,
        notional=(traded_v * aum_ref)[ok],
        adv=adv_v[ok],
        p_cost=float(np.percentile(p_all, 95)) if p_all.size else None,
        sigma_port=float(np.nanmedian(P['sig_m'].reindex_like(traded).to_numpy())),
    )
```

配套 2 个小函数（脚本内，各 ~10 行）：

```python
def daily_portfolio_excess(P, w):
    """日频组合超额（W8 temporary 与日收益链用）：权重月末定、日内持有。"""
    px = P['adj_price']
    r = px.pct_change(fill_method=None)
    wd = w.reindex(r.index, method='ffill').reindex(columns=r.columns).fillna(0.0)
    rp = (wd * r.fillna(0.0)).sum(axis=1)
    ub = (P['mask'].fillna(False)).reindex(r.index, method='ffill').fillna(False)
    rb = r.where(ub).mean(axis=1)
    return (rp - rb).dropna()


def daily_ref(P, cfg):
    """构造 panels.DailyRef（ADV / 非空 / 行业 / 规模 / 交易日数）。"""
    from backtest.execution.shell.panels import DailyRef
    mv_rank = np.ceil(P['mv_m'].rank(axis=1, pct=True) * 5.0).clip(1, 5)
    days = P['close'].groupby(P['close'].index.strftime('%Y-%m')).size()
    return DailyRef(adv=P['amt_m'],
                    universe=P['mask'].fillna(False) & P['ret'].notna(),
                    industry=P['facts']['ind'],
                    mv_rank=mv_rank,
                    days_by_month={str(k): int(v) for k, v in days.items()})
```

#### 2.6.3 `--calibrate` 分支重写（[L290-322](file:///f:/Coding/factor_pipeline/scripts/verify_capacity_impact.py#L290-L322)）

```python
    if args.calibrate or args.diagnose_window:
        if str(SCRIPTS.parent) not in sys.path:
            sys.path.insert(0, str(SCRIPTS.parent))
        from backtest.execution.config import CalibrationConfig
        from backtest.execution.core.impact import (
            LinearImpact, LogImpact, PowerImpact, SqrtImpact)   # F9
        from backtest.execution.ports import CalibrationUnavailable
        from backtest.execution.shell.loaders import resolve_evidence_level
        from backtest.execution.shell.panels import (
            MinutePanelBuilder, assemble_panels, build_daily_panels,
            coverage_gate)
        from backtest.execution.shell.report import write_report
        from backtest.execution.shell.runner import run_calibration

        cfg = CalibrationConfig(data_root=args.data_root)
        if args.diagnose_window:
            print('诊断: 解析证据等级 = %s' % resolve_evidence_level(cfg))
            print('诊断: 候选窗长 = %s（IJR 自动窗长仅诊断，不参与主值）'
                  % (list(cfg.windows),))
            if not args.calibrate:
                return 0

        P = build_panels(args.data_root)
        portfolio = build_portfolio_panels(P, cfg)
        minute = {}
        if not args.no_minute:
            try:
                minute = MinutePanelBuilder(
                    cfg, daily=daily_ref(P, cfg),
                    cache_dir=((SCRIPTS.parent / 'out' / 'panel_cache')
                               if args.panel_cache else None)).build()
            except CalibrationUnavailable as exc:
                minute = {'evidence_warnings': ['分钟层降级: %s' % exc]}
            else:
                ok, msgs = coverage_gate(minute.get('coverage') or {})
                if not ok:
                    minute.setdefault('evidence_warnings', []).extend(msgs)  # F7
                if not ok and not args.force_coverage:
                    print('覆盖度门禁失败:\n  ' + '\n  '.join(msgs))
                    return 2
        daily_panels = build_daily_panels(
            cfg, P, portfolio, impact_fit=minute.get('impact_fit'))
        evidence = ('minutes' if minute.get('panel_hash')       # F6
                    else resolve_evidence_level(cfg))
        panels = assemble_panels(minute, daily_panels, evidence)
        if args.evidence_level != 'auto':
            panels['evidence_level'] = args.evidence_level

        result = run_calibration(cfg, capacity_fn=capacity_from_p95,
                                 breakeven_fn=breakeven_aum, panels=panels)
        result = attach_panel_meta(result, minute, daily_panels, cfg)

        json_path = args.calibration_json or str(
            SCRIPTS.parent / 'out' / 'capacity_calibration.json')
        md_path = str(Path(json_path).with_suffix('.md'))
        written = write_report(result, json_path, md_path)
        print('evidence_level = %s' % result['evidence_level'])
        print('校准报告: %s' % ', '.join(written))
        if args.report_json:
            checks = [{'id': 'calibrate', 'ok': True},
                      {'id': 'evidence_level', 'ok': True}]
            if minute.get('coverage'):
                cov = minute['coverage']
                ratio = list((cov.get('universe_ratio') or {}).values())
                checks.append({'id': 'coverage',
                               'ok': bool(ratio) and min(ratio) >= 0.90,
                               'median': float(np.median(ratio)) if ratio else None})
            _write_report_json(args.report_json, 'verify_capacity_impact',
                               checks, [{'path': str(json_path)}])
        return 0
```

#### 2.6.4 `attach_panel_meta`（S3，结果后处理）

```python
def attach_panel_meta(result, minute, daily_panels, cfg):
    """把面板元数据挂到 runner 结果（runner 零改动，不变量 4）。"""
    cov = minute.get('coverage')
    cov = cov.as_dict() if hasattr(cov, 'as_dict') else cov
    wc = {str(k): (None if v is None else float(v))
          for k, v in (daily_panels.get('window_capacity') or {}).items()}
    vals = [v for v in wc.values() if v is not None]
    result['panels'] = {
        'minute_window': [cfg.minute_start[:7], cfg.minute_end[:7]],
        'daily_window': [cfg.sample_start[:7], cfg.sample_end[:7]],
        'panel_hash': minute.get('panel_hash'),
        'coverage': cov,
        'window_capacity': wc,
        'window_median': (float(np.median(vals)) if vals else None),
    }
    result['lambda_stats'] = minute.get('lambda_stats')
    result['impact_samples'] = minute.get('impact_samples_meta')
    # F4：runner 不消费 panels['evidence_warnings']（L197 仅收内部事件），此处并入证据链
    merged = (list(minute.get('evidence_warnings') or [])
              + list(daily_panels.get('evidence_warnings') or []))
    result['evidence_warnings'] = list(
        result.get('evidence_warnings') or []) + merged
    # F5：报告「持有期净收益」段所需的 alpha0 / cost_by_h 注入 decay
    decay = result.setdefault('decay', {})
    decay.setdefault('alpha0', daily_panels.get('alpha0'))
    decay.setdefault('cost_by_h', daily_panels.get('cost_by_h'))
    primary = (result.get('selection') or {}).get('primary')
    params = ((result.get('models') or {}).get(primary) or {}).get('params')
    if primary and params:
        model = {'sqrt': SqrtImpact(), 'linear': LinearImpact(),
                 'log': LogImpact(), 'power': PowerImpact()}[primary]
        grid = np.asarray(cfg.participation_grid, dtype=float)
        sigma = np.full(grid.shape, float(minute.get('sigma_median') or 0.02))
        result['impact_curve'] = [float(v) for v in
                                  model.predict(grid, sigma, params)]
    return result
```

> `window_capacity` 的逐 W 单值来自 `build_daily_panels`（§2.3.3），`window_median` 为 panels 层诊断（W7）；两者都不回写 `result["capacity"]["avew"]`。

#### 2.6.5 新增 CLI 参数（[L266-277](file:///f:/Coding/factor_pipeline/scripts/verify_capacity_impact.py#L266-L277)）

```python
    ap.add_argument('--no-minute', action='store_true',
                    help='只跑日频层（容量/衰减/执行），分钟层跳过')
    ap.add_argument('--panel-cache', action='store_true',
                    help='启用月度面板缓存 out/panel_cache/（默认关）')
    ap.add_argument('--force-coverage', action='store_true',
                    help='覆盖度门禁失败时不返回 2（仅诊断用，报告仍标 warning）')
    # 设计 W10 的 --no-panel-cache 以单旗标 --panel-cache（默认关）等价实现，不设冗余开关（R12）
```

### 2.7 `tests/test_minute_panels.py`（E6，新增）

头部与公共 fixture：

```python
# -*- coding: utf-8 -*-
"""v3.8.1 分钟面板编排（T381-01 ~ T381-22）。

红形态：``ImportError: cannot import name 'MinutePanelBuilder'``。
"""
import numpy as np
import pytest


@pytest.fixture()
def cfg():
    from backtest.execution.config import CalibrationConfig
    return CalibrationConfig(minute_root=None)


class FakeLoader(object):
    """测试缝：直接返回构造好的 MinuteDayAggregate。"""

    def __init__(self, by_month):
        self.by_month = by_month

    def available_months(self):
        return sorted(self.by_month)

    def load_month_regression(self, ym):
        return self.by_month[ym]
```

真实数据用例（T381-17/18/20）统一 `pytest.mark.skipif(not Path(r"E:\Level 1 Data").is_dir())`，与仓库既有真实数据用例一致；其中 T381-20 另需 `E:\Ashare_data` 可读（skipif 条件叠加，缺任一即 skip）。

---

## §3 工程细节

### 3.1 版本锚点（5 处代码锚点 + CHANGELOG，共 6 处）

| # | 位置 | 现值 |
|---|------|------|
| 1 | [pyproject.toml L7](file:///f:/Coding/factor_pipeline/pyproject.toml#L7) | `version = "3.9.0"` |
| 2 | [__init__.py L58](file:///f:/Coding/factor_pipeline/__init__.py#L58) | `__version__ = "3.9.0"` |
| 3 | [config_v2.py L371](file:///f:/Coding/factor_pipeline/config_v2.py#L371) | `Field(default="3.9.0")` |
| 4 | [verify_fix3_manual.py L21](file:///f:/Coding/factor_pipeline/tests/test_backtest/verify_fix3_manual.py#L21) | `EXPECTED_VERSION = "3.9.0"` |
| 5 | [test_fix3_version_unification.py L34](file:///f:/Coding/factor_pipeline/tests/test_fix3_version_unification.py#L34) | `EXPECTED_VERSION = "3.9.0"` |
| 6 | [CHANGELOG.md L3](file:///f:/Coding/factor_pipeline/CHANGELOG.md#L3) | 新增条目（不改历史） |

**待决（§7.4-A）**：包版本是升 `3.9.1` 还是保持 `3.9.0`。批次命名 `v3.8.1` 与已发布版本 `3.9.0` 存在语义版本倒挂，实施前必须由步骤 6 review 裁决，**不得由实施者自行决定**。

### 3.2 依赖与版本

- **零新增核心依赖**：`numpy`/`pandas` 均已在 `dependencies`；`pyarrow` 仍走 `calib` extra，缺失时 `MinutePanelBuilder.build` 抛 `CalibrationUnavailable` 由脚本降级（§2.3.2）。
- 不得在 `panels.py` 顶层 `import pyarrow`（只在 `loaders.py` 内部延迟 import）。

### 3.3 Python 3.9 兼容

- 只用 `typing.Optional/Dict/List/Tuple`，禁止 `X | Y` 注解与 `list[str]`；
- 不用 `match`、不用 `dataclass(slots=True)`；
- f-string、`functools`、`np.percentile` 均可用。

### 3.4 序列化与哈希

`panel_hash` 的 canonical payload（排序键、无时间戳、无浮点权重）：

```python
{"adv_window_days": cfg.adv_window_days,
 "code_range": [1, 1000000],
 "granularity": "daily",
 "lambda_min_days": cfg.lambda_min_days,
 "minute_window": [cfg.minute_start[:7], cfg.minute_end[:7]],
 "months": months,
 "n_lambda": len(rows),
 "n_samples": int(p.size),
 "sigma_clip": list(cfg.sigma_clip),
 "windows": list(cfg.windows)}
```

`sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")))`。含 `windows` 以满足 T381-13「改窗长即变」；权重无关（W3/§8）。

缓存（`--panel-cache`）：`out/panel_cache/{ym}.npz`（数组）+ `{ym}.meta.json`（`{"config_hash": cfg.config_hash(), "panel_version": "v381"}`）。命中条件：两文件都在且 `config_hash` 相符；写入用 `os.replace` 原子替换。缓存目录必须加入 `.gitignore` 之外的工作区 `out/`（已有先例）。

### 3.5 错误类型与降级

| 场景 | 行为 |
|------|------|
| pyarrow 缺失 / 月份无文件 / 过滤后空 | `loaders` 抛 `CalibrationUnavailable`；脚本捕获 → `evidence_warnings`，继续跑日频层 |
| 单股 λ 拟合失败（样本不足/常数） | 跳过该股（不写 0），计入 `fill_ratio` |
| 行业缺失 | 行业缺失股票独立成填充组 `(月份, None 行业, mv 五分位)` 取组内中位数；组内无显著样本则保留缺失（不填充）；无静默填 0。**步骤 10 审计裁决**：原两级退化链（mv-only → 当月中位 + warning）未实现；填充值仅展示用（`by_group` / `lambda_filled` 无下游数值消费，`panel` 用原始显著 λ），口径改与实现对齐（见审计报告 A-4） |
| 覆盖度门禁失败 | 脚本 `return 2`（`--force-coverage` 可绕过：stdout 打印留痕、`--report-json` 的 `checks.coverage` 记 `ok=False`；门禁消息不进 `evidence_warnings`，步骤 10 审计观察 A-3） |
| `cost_by_h` 无 `impact_fit` | 仅费率项 + warning `cost_impact_unavailable` |
| `block_size_mode != auto` | `run_calibration` 抛 `ValueError`（不静默） |

### 3.6 并发与 IO

- 单进程顺序执行（39 月 × 逐日流式）；本批**不引入**多进程（`pyarrow` 表对象跨进程序列化成本高于收益）。
- 分钟层内存策略：每月 λ 计算完成后立即把该月样本下采样到 `ceil(SAMPLE_CAP/月数)` 行，全局再封顶 `SAMPLE_CAP`（§6）。
- 不写 `$env:TEMP` 之外的中转文件；证据工件写 `out/`。

### 3.7 文件布局

| 动作 | 文件 |
|------|------|
| 新增 | `backtest/execution/shell/panels.py`、`tests/test_minute_panels.py` |
| 修改 | `backtest/execution/config.py`、`backtest/execution/shell/loaders.py`、`backtest/execution/shell/runner.py`、`backtest/execution/shell/report.py`、`scripts/verify_capacity_impact.py` |
| 追加 | `tests/test_execution_capacity.py`（T381-19/21 回归型用例） |
| 文档 | 本文件；`CHANGELOG.md`；`docs/PROJECT_STATUS.md`；`docs/private/DESIGN_V3.8.1...` R2 勘误（步骤 6）；`docs/audit/CHECKLIST_V3.8.1...`（步骤 7）；`docs/audit/CONSISTENCY_REVIEW_V3.8.1...`（步骤 8） |

---

## §4 不做什么（低效操作排除）

| 不做 | 理由 |
|------|------|
| 不 import `scripts` 进 `backtest.execution` | 不变量 3；日频组合面板由脚本注入 |
| 不改 `impact.py` 任何模型或 `temporary_share` 签名 | F2 裁决：`block_size_mode` 走校验型 |
| 不改 `runner` 的 `average_capacity` / `regime_capacity` / `net_curve` 算法 | W7/F3：主值回归 v3.8.0 现口径，默认逐位不变 |
| 不改 `cfg.windows`、不回移分钟起点到 2015 | W1：市值数据起点 2020-01 |
| 不实现 `block_size_mode ∈ {sqrt, iid}` | F2：留待后续批次 |
| 不新增依赖、不引入 numba/多进程 | 零新增核心依赖 |
| 不动 `out/capacity_impact.json` 默认路径 | 不变量 1 |
| 不做分钟级 OLS 全序列留存 | W2：内存冲突 |

---

## §5 TDD 用例与红→绿计划（22 例）

### 5.1 用例映射

| ID | 文件 | 断言要点 |
|----|------|----------|
| T381-01 | test_minute_panels | `_keep_mask` 保留 `1`（平安银行）与 `600000`，剔除 `390001`、`1000000` |
| T381-02 | test_minute_panels | `"%06d" % 1 == "000001"`，与日频列名可对齐；`_adv_lookup` 取到值 |
| T381-03 | test_minute_panels | 合成 1 bar/日，分钟 amount 与日频 amount×1e3 比值 = 1000（对账口径） |
| T381-04 | test_minute_panels | 合成已知 `r_t/σ`，`s_t` 符号与 `2Φ−1` 一致；锁定 bar 的 `s_t=0` 而 `amount_day` 全量 |
| T381-05 | test_minute_panels | `ret_day == close_last/open_first − 1`（含跨日不串月） |
| T381-06 | test_minute_panels | 合成 `r_d = λ x_d`，`fit_lambda_hac` 估回 λ（rtol 1e-8） |
| T381-07 | test_minute_panels | AR(1) 正残差下 HAC 的 p > iid 的 p |
| T381-08 | test_minute_panels | `lambda_stats.fill_ratio == 1 − n_sig/n_total` |
| T381-09 | test_minute_panels | `fill_ratio>0.30` → `c_interval_only=True` 且 warning 出现 |
| T381-10 | test_minute_panels | 22 文件 / 23 交易日 → 进入 `partial_months`；19 日 → 整月剔除 |
| T381-11 | test_minute_panels | 覆盖度 0.671 → `coverage_gate` 返回 False 且含「深市主板为 0」或中位不达标信息 |
| T381-12 | test_minute_panels | `assemble_panels` → `run_calibration`：`regime_p95`/`avew.primary`/`decay.net`/`execution` 均非空；`impact_fit.params == result.models[primary].params`（S1） |
| T381-13 | test_minute_panels | 同输入双跑 `panel_hash` 相等；改 `windows` 即变 |
| T381-14 | test_minute_panels | FakeLoader 缺 1 月 → `missing_months` 记录，`build` 不抛 |
| T381-15 | test_minute_panels | monkeypatch `has_pyarrow=False` → `CalibrationUnavailable`；`resolve_evidence_level` 回 `ohlc` |
| T381-16 | test_minute_panels | 缓存写入→命中（读回数组逐位相等）；改 `config_hash` → 未命中 |
| T381-17 | test_minute_panels（skipif 无数据） | 2023-03 单月 `build(months=["2023-03"])`：覆盖度 ≥0.90，深主板 >0，耗时记录 |
| T381-18 | test_minute_panels（skipif 无数据） | 报告 md 含「面板覆盖度 / λ 显著性 / 窗长容量 / 持有期净收益」四段 |
| T381-19 | test_execution_capacity | 默认路径快照：`build_panels` 增键不影响既有断言；默认 `run_calibration` 输出与改前逐位相等（κ 键集） |
| T381-20 | test_minute_panels（skipif 无数据） | `--calibrate --report-json` 的 `checks` 含 `calibrate`/`evidence_level`/`coverage` 且 `status` 可判定 |
| T381-21 | test_execution_capacity | `run_calibration` 缺 `evidence_level` 时 `render_markdown` 仍抛 `ValueError` |
| T381-22 | —（G4 全量） | `python -m pytest -q`：2026 + 21 = **2047 passed**（0 failed）；门禁本身不计用例 |

### 5.2 红→绿记录形态（步骤 9 填写）

| 批次 | 顺序 | 红形态 | 绿判据 |
|------|------|--------|--------|
| R1 | T381-01/02/05（E0） | `ImportError: MIN_STOCK_CODE` / `AttributeError: load_month_regression` | 3 绿 |
| R2 | T381-03/04/06/07（E0/E2） | `ImportError: MinuteDayAggregate` | 4 绿 |
| R3 | T381-08/09/10/11（E2） | `ImportError: MinutePanelBuilder` | 4 绿 |
| R4 | T381-12/13/14/15/16（E1/E2） | `ImportError: build_daily_panels` | 5 绿 |
| R5 | T381-17/18（E4/E5） | 报告缺段 / 覆盖度失败 | 2 绿 |
| R6 | T381-19/20/21 + 全量（E3/E6） | 默认输出漂移 | 4 绿 + 2047 passed |

**步骤 9 实测读数（2026-11-20 回填）**：

| 批次 | 实测（红 → 绿） |
|------|----------------|
| R1 | `ImportError: cannot import name 'EXCLUDE_CODE'` / `AttributeError: 'MinuteLoader' object has no attribute 'load_month_regression'` → 01/02/05 全绿 |
| R2 | `AttributeError: load_month_regression`（03/04）；06 首跑即绿（`fit_lambda_hac` v3.8.0 已存在，回归守卫）；07 首跑 `AssertionError: 0.0 > 0.0`（完美拟合 p 下溢，改 AR(1) 噪声后真红）→ 全绿 |
| R3 | `ModuleNotFoundError: backtest.execution.shell.panels`（`MinutePanelBuilder`/`coverage_gate` 不存在）→ 08/09/10/11 全绿 |
| R4 | `ModuleNotFoundError: backtest.execution.shell.panels`（`build_daily_panels`/`DailyRef` 不存在）→ 12/13/14/15/16 全绿 |
| R5 | 17 首跑绿（31.3 s，`out/v381_minute_202303.json`）；18 首跑 `AttributeError: module 'verify_capacity_impact' has no attribute 'run_calibration'`（脚本内局部 import）→ 改直连 runner 后二跑 `ValueError: sigma 与 participation 长度不一致`（`attach_panel_meta` 未广播 sigma）→ 修后 54.35 s 绿 |
| R6 | 19 `AssertionError: scenarios 键集`；20 subprocess `returncode 2`（argparse 无 `--no-minute`）；21 首跑即绿（`ValueError` 已存在，回归守卫）→ 全绿；全量见 §7 |
| 补 | G6 首跑（15.29 min）`AttributeError: 'PanelCoverage' object has no attribute 'get'`（`coverage_gate` 只吃 dict，离线用例未覆盖对象入参）→ T381-11 扩断言（先红后绿）→ 修 `coverage_gate` 归一化 → 重跑 G6 |

### 5.3 Fixture 清单

| Fixture | 用途 |
|---------|------|
| `cfg`（`minute_root=None`） | 单元测试（不触 IO） |
| `FakeLoader` | 控制月份集合与缺失场景（T381-10/14） |
| `synthetic_daily_ref` | `DailyRef` 的 3 月 × 4 股合成（ADV/行业/mv/交易日数） |
| `synthetic_minute_days` | 已知 `s_t`/`r_d` 的 22 日 × 4 股矩阵（T381-03/04/05/06） |
| `tiny_panels` | `regime_p95`/`window_capacity`/`notional`/`adv` 最小合法集（T381-12） |

> `tiny_panels` 复用 [tests/test_execution_capacity.py L18-28](file:///f:/Coding/factor_pipeline/tests/test_execution_capacity.py#L18-L28) 的构造风格，避免重复定义。
>
> 合成 feather 用例（T381-03/04/05/10）统一加 `@pytest.mark.skipif(not has_pyarrow(), reason="calib extra 未安装")`（R11）。

---

## §6 性能验证

| 场景 | 命令 | 预算 | 实测（2026-11-20） |
|------|------|------|------|
| 分钟单月 | `python scripts/verify_capacity_impact.py --calibrate --no-minute` 后单独跑 `build(months=["2023-03"])` 探针 | ≤ 60 s | **27.37 s**（无 trace）/ 31.26 s（pytest 内） |
| 分钟 39 月 | 同上全量（`--calibrate`） | ≤ 30 min | **14.52 min**（G6 exit 0） |
| 日频 73 月 | `--calibrate --no-minute` | ≤ 3 min | **3.2 s**（G5 exit 0） |
| 峰值内存 | 探针内 `tracemalloc.get_traced_memory()` 于单月循环中记录 | ≤ 300 MB | **296.6 MB**（RSS 增量 478.4 MB，含 pyarrow 未追踪缓冲，仅记录） |
| 观测样本量 | 报告 `impact_samples.n` | ≤ 200,000 | **200,000**（cap 命中，`sampling=equal_distance`） |

> 内存优化过程（步骤 9 实测）：初版 337.6 MB → 拆分 `table/df` 生命周期并跳过已排序文件的全量 `sort_values` 拷贝 → 296.6 MB；`panel_hash=ccdede8858f8…` 前后一致，证明数值逐位等价。

探针脚本写 `$env:TEMP\\v381_perf_probe.py`，输出 `out/v381_perf_probe.json`（单月耗时、峰值内存、样本量、每月股票数）。

超预算处置（设计 §6）：先测单月；`>60 s` 则降 `lambda_min_days` 至 8 或启用 `--panel-cache`；**不得**改窗口或减少月份。

---

## §7 验收命令与证据出口

### 7.1 门禁命令

```bash
# R1 单元层
python -m pytest tests/test_minute_panels.py -q

# R2 既有执行层零回归
python -m pytest tests/test_execution_capacity.py tests/test_execution_architecture.py \
                 tests/test_execution_import_smoke.py tests/test_execution_report.py -q

# R3 默认路径 SHA 门禁（改前留底 → 改后比对）
python -c "import hashlib,pathlib;print(hashlib.sha256(pathlib.Path('out/capacity_impact.json').read_bytes()).hexdigest())"
python scripts/verify_capacity_impact.py

# R4 日频层冒烟（不依赖分钟数据）
python scripts/verify_capacity_impact.py --calibrate --no-minute \
       --calibration-json out/v381_calibration_daily.json

# R5 全量
python -m pytest -q
```

### 7.2 证据出口

| 证据 | 路径 |
|------|------|
| 默认路径 SHA | `out/capacity_impact.json`（须仍为 `82728CE1…`） |
| 日频层校准 | `out/v381_calibration_daily.json` / `.md` |
| 全量校准 | `out/v381_calibration.json` / `.md` |
| 覆盖度与性能 | `out/v381_perf_probe.json` |
| 单月实测明细 | `out/v381_minute_202303.json`（T381-17 产出） |
| 全量测试日志 | `$env:TEMP\\v381_pytest.log`（保留首错上下文） |

### 7.3 验收 10 条 ↔ 测试映射

| 设计 §7 | 判据 | 用例 |
|---------|------|------|
| 1 | `min_regime` 与 `c_calib_point` 非空 | T381-12 / T381-17 |
| 2 | `fill_ratio` 与 `c_interval_only` 成对 | T381-08/09 |
| 3 | 覆盖度 ≥0.95 中位 / ≥0.90 最差 / 深主板 >0 | T381-11（门禁）+ T381-17（实测） |
| 4 | 单位对账 ∈ [0.999,1.001] | T381-03 |
| 5 | `panel_hash` 双跑一致、改窗即变 | T381-13 |
| 6 | 默认 SHA 不变 | §7.1 R3 |
| 7 | 全量零新增失败 | T381-22 |
| 8 | 单月 ≤60 s、峰值 ≤300 MB | §6 |
| 9 | `evidence_level` 必填、缺键不填 0 | T381-21 / T381-15 |
| 10 | 报告四段齐全 | T381-18（真实数据）/ T381-20 |

### 7.4 待决项（步骤 6 已裁决，见 §10.4）

| # | 待决 | 选项 | 建议 |
|---|------|------|------|
| A | 包版本 | A1 升 `3.9.1`（5 处代码锚点 + CHANGELOG，共 6 处）；A2 保持 `3.9.0`，仅记 CHANGELOG 未发版条目 | **A1**：延续历史「每批升版本」惯例，避免 `v3.8.1 < 3.9.0` 的倒挂；批次别名在 CHANGELOG 标题注明「对应路线图 v3.8.1 条目」 |
| B | S1 `impact_fit` 注入（§0.5） | 采纳 / 改为 runner 支持 callable `cost_by_h` | 采纳：runner 零改动优先；`c` 确定性重拟合 + T381-12 断言 |
| C | S4 职责拆分（§0.5） | 采纳 / 按设计原文全放脚本 | 采纳：panels 纯函数可测 |
| D | R2 注记勘误（§0.5） | 回改设计 R2 / 仅记录 | 回改设计 R2 表述（步骤 6 执行） |
| E | `--force-coverage` 是否保留 | 保留（诊断）/ 删除 | 保留：覆盖度门禁为硬门禁，但实测调参需要入口 |

---

## §8 回滚与风险

### 8.1 回滚点

1. 新增 `shell/panels.py` + `tests/test_minute_panels.py` 删除即回滚；
2. 脚本改动全部位于 `--calibrate` 分支与 3 个新参数，`build_panels` 仅增键；
3. `runner.py` 2 处改动：回退 κ 行为 `for k in (1.0, 1.5, 2.0)`、删校验行；
4. `config.py` 字段变化只影响校准工件；
5. 兜底：默认路径 SHA 门禁（§7.1 R3）。

### 8.2 风险

| 风险 | 概率 | 处置 |
|------|------|------|
| 修复过滤后股票数跳增，`fill_ratio > 30%` | 中 | 先跑 2023-03；超阈值按 `[区间]` 报告（`c_interval_only`），**不回退过滤** |
| 39 月全量超 30 min | 中 | 开 `--panel-cache`；单月优化后再全量；不改窗口 |
| `excess_d` 基准口径（EW 全市场）与容量组合不一致 | 低 | 报告标注 `temporary` 基准；同组合口径在 §2.6.2 显式写入 |
| 行业表 `facts['ind']` 月末缺失 | 中 | 填充组退化链（§3.5）；worst case 保留缺失 + warning |
| 缓存目录被误提交 | 低 | 写 `out/panel_cache/`；PR checklist 核对 |
| 非默认 `kappa` 导致键集变化，报告硬编码 `"1.5"` | 低 | 报告按 `capacity.scenarios` 实际键遍历（R5） |

---

## §9 进度勾选表（步骤 9/10 回填）

### 9.1 任务

- [x] E0 配置 19 字段 + 过滤修复 + `load_month_regression`
- [x] E1 `build_daily_panels`（temporary/rho/alpha/cost/plateau_sd）
- [x] E2 `MinutePanelBuilder`（λ/填充/样本/覆盖度/hash/缓存）
- [x] E3 `runner` κ 接线 + `block_size_mode` 校验
- [x] E4 脚本装配 + 3 个新 CLI + 门禁 + 后处理
- [x] E5 `render_markdown` 四段
- [x] E6 21 例全绿 + 性能 + SHA 门禁

### 9.2 文件

- [x] `backtest/execution/config.py`
- [x] `backtest/execution/shell/loaders.py`
- [x] `backtest/execution/shell/panels.py`（新增）
- [x] `backtest/execution/shell/runner.py`
- [x] `backtest/execution/shell/report.py`
- [x] `scripts/verify_capacity_impact.py`
- [x] `tests/test_minute_panels.py`（新增）
- [x] `tests/test_execution_capacity.py`（追加）
- [x] `CHANGELOG.md` / `docs/PROJECT_STATUS.md`

### 9.3 门禁

- [x] 默认 `out/capacity_impact.json` SHA256 `82728CE1…` 逐位不变（双跑 + 改前备份三方一致）
- [x] 全量 `pytest -q` = **2047 passed / 15 skipped / 0 failed**（808.70 s；基线 2026 + 新增 21；文档原写 2048 含门禁 T381-22 自身）
- [x] 22 项逐条勾选（16 例离线断言 + 3 例真实数据 + 2 例执行层 + 1 项全量门禁；对照 §5.1/CHECKLIST §3）

---

## §10 步骤 6 review 记录（v1.0 → v1.1，2026-11-20）

复审口径：接口签名与源码逐行对齐（config / loaders / runner / report / impact / decay / 脚本）、panels 键 ↔ runner 消费 13 键、算术与单位链、22 例可测性与 fixture 可构造性、默认路径零漂移、待决项 A-E 裁决。

### 10.1 核对通过项

- **panels 键 ↔ runner 消费契约**：assemble 产物逐键核对 runner L191-339——`impact_samples{p,impact,sigma}`（L206-245，与 impact_fit 同样本同实现，S1 逐位等价成立）、`lambda_pvalues`（L246-252）、`temporary{r1,rev1}` 等长（`ex_d[:-1]`/`ex_d[1:]`，L254-259）、`aum_ref`/`cap`（L261-262）、`regime_p95`（L263-272，str 键）、`window_capacity`（L273-275，str 键 → `average_capacity`）、`rho_series`（L277-281）、`cost_by_h`+`alpha0`（L284-288，h∈{5,10,20} 与 net_curve horizons 交集正确，h=1/60 自动跳过）、`notional`+`adv`（L292-304，元/元）、不产 `"aum"` 键（R3）；runner 结果键与 §2.5 / §2.6.4 数据源映射闭合；
- **行号锚点复核**：config L19-34（16 字段）、loaders L79-80 / L71-121、runner L269-271 / L254-259 / L284-288、impact L132 / L158 / L174-199、decay L15-43 / L78-86、report L22-57、脚本 L87-128 / L266-277 / L290-322——与源码逐处一致；
- **算术与单位链**：cost(h)=(20/h)·AUM·turnover·2·(fee+impact)/1e4，h=20 退化与脚本 base_net 单边×2 一致；窗口点 73−W+1；κ 键集 kappa=1.5 时与现状逐位等价；19 字段=16−1+4；panel_hash 含 windows（T381-13 可满足）；
- **默认路径零漂移**：`build_panels` 仅加键（tests 无键集断言，grep 核对）；runner 2 处改动在 kappa=1.5 下逐位等价；3 个新 CLI 参数均默认关闭；
- **测试计数**：22 例映射连续（R1-R6 批次合计 22）；2026+22=2048 与 §0 / §5.1 / §9.3 一致；
- **导入无环**：panels → runner/loaders/core，runner 不依赖 panels，脚本注入组合面板（不变量 3）。

### 10.2 发现与修正（F1-F10，均已在 v1.1 落地）

| # | 位置 | 发现 | 定级 | 修正 |
|---|------|------|------|------|
| F1 | §2.2.2 | `load_month_regression` 输出段列索引错位：agg 实际列序为 signed/amount/rsum/r2sum/n/lock/open_first/close_last（0-7），原文取 `mat[:,7]/mat[:,8]`（越界 IndexError）、`out_n` 取到 lock 列、`out_lock` 用 open_first/lock | **P2** | 修正为 open_first=6 / close_last=7、n=4、lock 占比=lock/n；补列序注释 |
| F2 | §2.3.4 | `coverage_gate` 对 `PanelCoverage` dataclass 调 `.get` → AttributeError；脚本传入的正是 dataclass | **P2** | 入口归一化：`hasattr(as_dict)` 分支 |
| F3 | §2.3.3 | `plateau_sd` 用日超额 std（ex_d），违背 W8「AUM×std(rho_series)（月超额波动）」，与 net(h) 月尺度错配（量级缩小 ~√21） | **P2** | 改 `ex_m.std(ddof=1)`，注释标 W8 依据 |
| F4 | §2.6.4 | runner 不消费 `panels['evidence_warnings']`（L197 warnings 仅由内部事件填充）→ 降级/门禁原因全部丢失，违背不变量 5 | **P2** | `attach_panel_meta` 显式合并 minute+daily 警告进 `result['evidence_warnings']` |
| F5 | §2.5/§2.6.4 | 报告「持有期净收益」段要读 `payload['decay']['alpha0']/['cost_by_h']`，但 runner `decay_out` 不含这两键 → 段落静默缺失 | **P2** | `attach_panel_meta` 以 `setdefault` 注入两键 |
| F6 | §2.6.3 | `evidence_level` 取 `resolve_evidence_level(cfg)`，分钟层实际失败（窗口无月/过滤后空）时误标 minutes | P3 | 改按 `minute.get('panel_hash')` 判定，回退 resolve |
| F7 | §2.6.3 | 门禁失败但 `--force-coverage` 放行时 msgs 丢失，与 CLI help「报告仍标 warning」矛盾 | P3 | `minute['evidence_warnings'].extend(msgs)`（配合 F4 进结果） |
| F8 | §2.3.2 | `build` 返回键清单缺 `impact_samples_meta`（§2.6.4 读取；W10 JSON 需要 {n,cap,granularity}） | P3 | 键清单补齐（含 sampling 披露） |
| F9 | §2.6.3 | `attach_panel_meta` 引用 4 个 impact 模型，导入清单未列 | P3 | 补 `from backtest.execution.core.impact import ...` |
| F10 | §2.3.2 | `_month_lambda` 的 rows 缺 `industry`/`mv_bucket`，`_fill_lambda`（W4 分组填充）无输入；且逐股全表布尔掩码为 O(N·K) | P3 | `_month_row` 月截面一次取行并按 `zfill(6)` 回填两字段；补「分组索引一次构建」性能注记 |

### 10.3 实施注记（R6-R12，不改正文）

- **R6**：`window_capacity[W]` 对滑窗容量取**均值**（设计未指明逐 W 聚合方式）；与 runner `average_capacity` 构成两层平均，`window_median` 为 4 档诊断；
- **R7**：`impact_bps` 不随 h 变化——W8 写 `impact_bps(h)` 但未定义 h 依赖；实现取 p95 参与率单点求值（h 间恒定），报告披露；
- **R8**：W3 的「seed=cfg.seed 分层抽样」由**确定性等距抽样**替代（lexsort 后 linspace 取样，覆盖 p×σ 分位全域、无 RNG 状态）；`impact_samples_meta.sampling="equal_distance"` 披露；
- **R9**：`daily_portfolio_excess` 日频基准用 `mask` 全域 EW（tradable 为月末快照、无日频口径），与月频 `evaluate` 的 universe 存在口径差异 → 报告披露；
- **R10**：`build_daily_panels(cfg, daily, ...)` 的 `daily` 参数当前统计侧未消费（保留对齐设计签名）；`daily_ref(P, cfg)` 的 `cfg` 同理；
- **R11**：合成 feather 用例（T381-03/04/05/10）需 `skipif(not has_pyarrow())`（已在 §5.3 标注）。
- **R12**：设计 W10 的 `--no-panel-cache` 未单独实现——`--panel-cache` 单旗标默认关，语义等价；CLI 面无冗余开关（§2.6.5 args 注，步骤 8 M7）。

### 10.4 待决项裁决（§7.4 A-E）

| # | 裁决 | 理由 |
|---|------|------|
| A | **采纳 A1：包版本升 3.9.1**（5 处代码锚点 + CHANGELOG，共 6 处） | 延续「每批升版本」惯例，消除 `v3.8.1 < 3.9.0` 倒挂；CHANGELOG 标题注明「对应路线图批次 v3.8.1」 |
| B | **采纳 S1**（impact_fit 注入） | runner 零改动优先；同样本同实现 ⇒ c 逐位相等，T381-12 断言兜底 |
| C | **采纳 S4**（脚本装配 / panels 统计拆分） | panels 纯函数可测，总代码量不变 |
| D | **采纳**：设计 §13.4 R2 勘误已回改（2026-11-20） | loaders L71-121 逐文件（=逐日）循环，pct_change 现状已按日重置，不构成实施动作 |
| E | **保留 `--force-coverage`** | 硬门禁保留（默认 exit 2）；配合 F7 使放行路径留痕于 evidence_warnings |

### 10.5 复审结论

**PASS_WITH_FIXES**：10 项发现（5 P2 + 5 P3）全部为文档级修正——其中 F1 为实现级索引幻觉（按原文编码将在首个真实月份 IndexError）、F4 为证据链断裂（违背不变量 5）；无需推翻任何 E0-E6 / S1-S4 决策。修正后本文件 v1.1 可进入步骤 7（checklist）。复审人：Trae Agent（同会话，步骤 6）；日期：2026-11-20。
