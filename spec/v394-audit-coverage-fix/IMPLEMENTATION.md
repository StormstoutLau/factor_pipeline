# 实施文档：v3.9.4 审计遗留修复 + 覆盖度口径收口（批次 A）

---
id: v394-audit-coverage-fix-IMPLEMENTATION
type: design
version: 1.1
status: verified
date: 2026-11-20
depends: [v394-audit-coverage-fix-DESIGN, v394-audit-coverage-fix-RESEARCH]
upstream: null
---

> **Feature**: 批次 A「口径收口包」——P-012（F-1~F-6）+ P-004（覆盖度交集口径）+ P-005（强制放行留痕）
> **创建日期**: 2026-11-20
> **状态**: verified（Step 6 异构复审 PASS_WITH_FIXES；F1-F9 修复已落盘，见 §10）
> **Spec 步骤**: Step 5-6
> **基于设计**: [DESIGN.md](./DESIGN.md) **v1.1 verified**
> **基于调研**: [RESEARCH.md](./RESEARCH.md) **v1.1 verified**
> **代码基线**: `a0cf914`（行号均以该 commit 为准）
> **执行方式**: TDD 先红后绿；Python 3.9 语法；零新增依赖；默认 `out/capacity_impact.json` SHA 逐位不变

---

## 1. 实施概述

本批共 12 处源码编辑块（`panels.py` × 5、`runner.py` × 5、script × 2）+ 1 处文档勘误（§3.4，F-2）+ 8 条测试。全部改动落在**校准分支**与**覆盖度装配**，默认回测路径不进入任何新代码：

- `panels.py`：`_coverage` 由「分钟 uniq 码数 / 日频域计数」改为「|分钟码 ∩ 域码| / |域码|」，同时用新字段 `ratio_raw` 披露旧式分子，`counts` 语义冻结（D11）；
- `runner.py`：回退分支 net 区间由 `aum·A(h)` 改为 m 形式 `aum·A(h_m)·(m ∓ t·m_se)`（与 point 同一条代数路径），并补 `net[h].sd`、顶层 `plateau`、退化态 `m_sensitivity={}`、`DecayCurve` 内部接线；
- `scripts/verify_capacity_impact.py`：`--force-coverage` 放行时把门禁文案 token 化写入 `minute["evidence_warnings"]`。

**硬约束**（贯穿全批）：

| 约束 | 落地方式 |
|------|---------|
| Python 3.9 语法 | 不用 `X \| Y` 类型、不用 `match`、不用 `dict \| dict` |
| 零新增依赖 | 只用既有 `numpy` / `pandas` / 标准库 |
| `core/decay.py` 零改动 | 仅在 `runner.py` 显式 import 既有符号（`DecayCurve` / `plateau`） |
| 默认 SHA 不变 | `assemble_decay_curve` 仅被 `--decay-curve-json` 路径调用 |
| `panel_hash` 逐位不变 | hash payload（panels.py L403-419）不含 `counts` / `ratio`，本批不触碰 |

---

## 2. 变更白名单

| 文件 | 动作 | 对应设计 |
|------|------|---------|
| `backtest/execution/shell/panels.py` | `PanelCoverage.ratio_raw` + `as_dict` 增键；`_universe_codes` 新增；`_universe_count` 改薄封装；`_coverage` 交集口径；`force_coverage_warning` 新增 + `__all__` 增项 | DESIGN §4.2 / §4.3 / §6.1（D8/D9/D11） |
| `backtest/execution/shell/runner.py` | F-1 回退区间；F-6 退化守卫；F-5 `net[h].sd` + 顶层 `plateau`；F-4 `DecayCurve` 接线 | DESIGN §4.1 / §4.4（D1/D5/D6/D7） |
| `scripts/verify_capacity_impact.py` | 懒加载 import 增 `force_coverage_warning`；force 分支追加 token 警告 | DESIGN §4.3（D9） |
| `tests/test_execution_decay.py` | T394-1 ~ T394-4 | DESIGN §10.2 |
| `tests/test_minute_panels.py` | T394-5、T394-7、T394-8（+ T381-17 期望复核；T394-7 因夹具落位迁入，复审 F9） | DESIGN §10.2 |
| `tests/test_execution_capacity.py` | T394-6（+ 补 `Path` import） | DESIGN §10.2 |
| `spec/v393-alpha-decay-model/IMPLEMENTATION.md` | §5 通过线勘误（F-2，L460） | DESIGN §2.1 D3 |
| `CHANGELOG.md` / `README*.md` / `docs/PROJECT_STATUS.md` / `docs/PROGRESS.md` | Step 9 同步 | — |

**不在白名单**：`backtest/execution/core/decay.py`（零改动）、`backtest/execution/core/impact.py`、`shell/report.py`、`shell/loaders.py`、`ports.py`、`out/*`、`config*.py`、`pyproject.toml`（版本号由 Step 9 统一处理，见 §8.3）。

---

## 3. 代码级变更

> **实施口径声明（Step 8 F-D）**：本节代码块为唯一实施口径；DESIGN §4 的引用式代码块与之语义恒等（引号风格 / `float(aum)` 显式化等差异以本文件为准）。

### 3.1 `backtest/execution/shell/panels.py`

#### 3.1.1 导入与 `__all__`（L10 / L26-28）

```python
from dataclasses import dataclass, field          # L10：增 field
```

```python
__all__ = ["DailyRef", "PanelCoverage", "MinutePanelBuilder",
           "build_daily_panels", "assemble_panels", "coverage_gate",
           "force_coverage_warning",
           "PARTIAL_MIN_DAYS", "SAMPLE_CAP", "FEE_BPS", "COST_HORIZONS"]
```

- 仅新增 `force_coverage_warning`；shell 模块无 core 的 5 项上限（`test_core_all_bounded` 只扫 `core/`）。

#### 3.1.2 `PanelCoverage`（L50-71 替换）

```python
@dataclass
class PanelCoverage(object):
    """覆盖度门禁工件（W6）。"""

    window: tuple
    months: list
    partial_months: list
    missing_months: list
    stock_median: float
    universe_ratio: dict
    limit_lock_ratio: float
    board_counts: dict
    ratio_raw: dict = field(default_factory=dict)   # v3.9.4：原式披露（可 >1）

    def as_dict(self):
        return {"window": list(self.window),
                "months": list(self.months),
                "partial_months": list(self.partial_months),
                "missing_months": list(self.missing_months),
                "stock_median": float(self.stock_median),
                "universe_ratio": dict(self.universe_ratio),
                "ratio_raw": dict(self.ratio_raw),
                "limit_lock_ratio": float(self.limit_lock_ratio),
                "board_counts": dict(self.board_counts)}
```

- **非 frozen**（与 L50 现状一致）、**`as_dict`**（非 `to_dict`）——DESIGN v1.1 已勘误；
- 新字段置末尾且带默认值 → 既有构造点（`panel.build()`、`tests/test_minute_panels.py` L303-309）零改动；
- `ratio_raw` 为**末位字段**（代码块口径：置于 `board_counts` 之后）；「universe_ratio 之后」仅指 `as_dict` 输出键序。dataclass 规则：带默认值字段若插在无默认值的 `limit_lock_ratio` / `board_counts` 之前会直接 TypeError——代码块口径为唯一实施口径（复审 F1）。`coverage_gate` 只读 `universe_ratio`，不受影响。

#### 3.1.3 `_universe_codes` 新增 + `_universe_count` 改薄封装（L232-239 替换）

```python
    def _universe_codes(self, ym):
        """日频可投资域码集（int 归一，与 _adv_lookup 同款）。"""
        if self.daily is None or self.daily.universe is None:
            return set()
        row = self._month_row(self.daily.universe, ym)
        if row is None:
            return set()
        keep = np.asarray(row.fillna(False).to_numpy(), dtype=bool)
        codes = set()
        for key in row.index[keep]:
            try:
                codes.add(int(str(key)))
            except (TypeError, ValueError):
                continue
        return codes

    def _universe_count(self, ym):
        return len(self._universe_codes(ym))
```

- `keep` 的 bool 归一与现行 L238-239 逐字同款（`np.asarray(..., dtype=bool)`）；
- `_month_row` 为既有 staticmethod（L197-210），月截断语义不变；
- `_universe_count` 保留为薄封装（DESIGN §4.2 指定）：`_coverage` 改用 `_universe_codes` 后其内部无调用方，但保留可避免私有契约断裂，且成本为 0（不参与热路径）。

#### 3.1.4 `_coverage` 交集口径（L382-401 替换）

```python
    def _coverage(self, usable, partial, missing, counts, locks):
        ratio, raw = {}, {}
        for ym in usable:
            universe = self._universe_codes(ym)
            denom = len(universe)
            if denom <= 0:
                ratio[ym] = None
                raw[ym] = None
                continue
            codes = set(int(c) for c in self._month_codes.get(ym, ()))
            ratio[ym] = float(len(codes & universe)) / float(denom)
            raw[ym] = float(counts[ym]) / float(denom)
        boards = {"沪主板": 0, "深主板": 0, "创业板": 0, "科创板": 0, "其他": 0}
        for ym in usable:
            for code in self._month_codes.get(ym, []):
                boards[_board(str(int(code)).zfill(6))] += 1
        values = [float(v) for v in counts.values() if v]
        lock_values = [locks[m] for m in usable if m in locks]
        return PanelCoverage(
            window=(self.cfg.minute_start[:7], self.cfg.minute_end[:7]),
            months=list(usable), partial_months=list(partial),
            missing_months=list(missing),
            stock_median=float(np.median(values)) if values else 0.0,
            universe_ratio=ratio,
            ratio_raw=raw,
            limit_lock_ratio=(float(np.mean(lock_values))
                              if lock_values else 0.0),
            board_counts=boards)
```

- `_month_codes[ym]` 是 `np.unique(agg.stock_code)`（L467-468，int64 ndarray），`set(int(c) ...)` 兼容；
- `stock_median` 仍取 `counts.values()`（INV-4 不变）；
- `counts` 语义冻结为「分钟 uniq 码数」（D11），本批不改 L469。

#### 3.1.5 `force_coverage_warning`（新增，置于 `coverage_gate` 之前）

```python
def force_coverage_warning(messages):
    """--force-coverage 放行留痕文案（token 化，便于 grep 与断言）。"""
    return "coverage_gate_forced: " + "; ".join(str(m) for m in messages)
```

- 纯函数、无 I/O；`coverage_gate`（L649-671）**零改动**（ADR-0002 职责边界）。

### 3.2 `backtest/execution/shell/runner.py`

#### 3.2.1 懒加载 import（L200）

```python
    from ..core.decay import (DecayCurve, decay_multiplier, fit_phi, net_ci,
                              net_point, plateau)
```

- `plateau` / `DecayCurve` 均已在 `core/decay.py` 定义（L92-98 / L258-268），**不修改该文件**、不进 `__all__`。

#### 3.2.2 F-1 回退区间（L316-321 替换）

```python
            base_net = aum * float(a_mean[hm])
            net_out[str(h)] = {
                "point": float(point[h]),
                "lo": float(base_net * (m_point[h] - t_crit * m_se)
                            - cost_by_h[h]),
                "hi": float(base_net * (m_point[h] + t_crit * m_se)
                            - cost_by_h[h])}
```

- 代数等价：`base_net · m(h) = aum·A(h_m)·A(h)/(A(h_m)·h/h_m) = aum·A(h)·h_m/h`，即补足缺失的 `(h_m/h)` 因子；
- `m_se` 非有限 → `lo/hi` 为 NaN（与 `m_out` L324-326 的处理一致），不再产出伪区间；
- 与 `point` 共用 `m_point` / `m_se` / `base_net`，消除第二条代数路径（F-1 根因）。

#### 3.2.3 F-5 `net[h].sd` 与顶层 `plateau`（插在 net 三值之后，L330 后）

```python
    net_sd = dict((int(h), float("nan")) for h in horizons)
    if not degenerate and a_boot is not None:
        base_rep = np.asarray(a_boot[hm], dtype=float)
        for h in horizons:
            if h not in cost_by_h:
                continue
            values = (aum * base_rep * np.asarray(m_boot[h], dtype=float)
                      - cost_by_h[h])
            values = values[np.isfinite(values)]
            net_sd[int(h)] = (float(np.std(values, ddof=1))
                              if values.size > 1 else float("nan"))
    for key, item in net_out.items():
        item["sd"] = net_sd.get(int(key), float("nan"))
```

```python
    point_map = dict((int(k), float(v["point"])) for k, v in net_out.items()
                     if int(k) in horizons
                     and np.isfinite(float(v["point"])))
    plateau_h = []
    if point_map:
        h_star = max(point_map, key=lambda key: point_map[key])
        sd_star = net_sd.get(int(h_star), float("nan"))
        if np.isfinite(sd_star):
            plateau_h = plateau(point_map, sd_star)
```

- `sd` 与 `net_ci` 用同一代数（`aum·A_rep(h_m)·m_rep(h) − cost`），仅取样本标准差（ddof=1）；
- 回退 / 退化 → NaN → `plateau=[]`（不伪造区间）；
- `plateau()` 契约不变（收标量 sd、返回有序 int 集），默认路径的 rho 口径调用不受影响；
- 键顺序 `point/lo/hi/sd`，仅增键不改既有键值。

#### 3.2.4 F-6 退化守卫（L354-365 加 `if not degenerate`）

```python
    m_sensitivity = {}
    if not degenerate:
        for block in (1, 6):
            try:
                _, m_b = _boot(block)
            except Exception:
                m_sensitivity[str(block)] = {}
                continue
            item = {}
            for h in horizons:
                lo, hi = _quantiles(m_b[h])
                item[str(h)] = {"lo": lo, "hi": hi}
            m_sensitivity[str(block)] = item
```

- 退化态输出 `{}`，不再产生 `{"1": {}, "6": {}}` 的空壳循环（F-6）；
- 非退化态逐字不变。

#### 3.2.5 F-4 `DecayCurve` 接线（插在 phi 判定块之后 L352 后）

```python
    curve = DecayCurve(
        h_m=hm,
        horizons=tuple(horizons),
        a_mean=dict(a_mean),
        m_point=dict(m_point),
        m_lo=dict((h, float(m_out[str(h)]["lo"])) for h in horizons),
        m_hi=dict((h, float(m_out[str(h)]["hi"])) for h in horizons),
        phi=float(phi),
        phi_status=phi_status,
        n_periods=n_periods,
        boot={"block": int(block_size), "reps": int(n_bootstrap),
              "sensitivity": [1, 6], "seed": int(seed)})
```

返回值改为从 `curve` 字段取值（其余键逐字保留）：

```python
    m_payload = dict((str(h), {"point": float(curve.m_point[h]),
                               "lo": float(curve.m_lo[h]),
                               "hi": float(curve.m_hi[h])})
                     for h in curve.horizons)
    return {
        "h_m": curve.h_m,
        "n_periods": curve.n_periods,
        ...
        "phi": curve.phi,
        "phi_status": curve.phi_status,
        ...
        "m": m_payload,
        "a": a_out,
        "net": net_out,
        "plateau": plateau_h,
        "boot": dict(curve.boot),
        ...
    }
```

- `m` 的键序与取值与旧 `m_out` 逐位相同（同 `horizons` 顺序、同 float 转换）；
- `verdict` 仍读 `m_out`（L367-378）保持不变，避免行为漂移；
- 构造点唯一（T394-3 以 1 次调用断言），兑现 v3.9.3 DESIGN §3.2 契约。

### 3.3 `scripts/verify_capacity_impact.py`

#### 3.3.1 懒加载 import（L578-581）

```python
        from backtest.execution.shell.panels import (MinutePanelBuilder,
                                                     assemble_panels,
                                                     build_daily_panels,
                                                     coverage_gate,
                                                     force_coverage_warning)
```

#### 3.3.2 force 分支留痕（L610-616）

```python
            ok, messages = coverage_gate(minute.get('coverage') or {})
            if not ok:
                for message in messages:
                    print('[coverage] %s' % message)
                if not args.force_coverage:
                    return 2
                minute.setdefault('evidence_warnings', []).append(
                    force_coverage_warning(messages))
                print('[coverage] --force-coverage：门禁失败放行（留痕）')
```

- 复用既有合并通道：`attach_panel_meta`（script L271 定义、L628 调用）把 `minute["evidence_warnings"]` 并入 `result`，校准报告警告节（report.py L137-139「## 证据警告」）原样打印 → 无需改 report（复审 F4：原锚点 L639-646 / L506-508 为 decay-curve md 侧，已更正；主会话已复核 script L271 与 report.py L137-141）；
- `--force-coverage` 之外的分支（未 force 直接 `return 2`）零改动。

### 3.4 文档勘误（F-2；F-3 已于 Step 3-4 落地）

`spec/v393-alpha-decay-model/IMPLEMENTATION.md` L460 替换：

```markdown
- 全量 ≥ **2057** passed / 15 skipped / **0 failed**（恒等式：`2065 collected + 7 模块级 skip = 2072 = 2057 passed + 15 skipped`；T393-1~T393-10 为 pytest 用例、T393-11 命令级不计入〔I-3 注记保留〕；旧文「2065 passed」为 collected 数误用，AUDIT F-2）
```

- `spec/v393-alpha-decay-model/DESIGN.md` 已在 Step 3 升 **v1.2**（`phi_status` 枚举补 `prior`、D5 plateau 注记、§7 同步、§13 勘误记录），本批不再改。

---

## 4. 测试实施（先红后绿）

### 4.1 `tests/test_execution_decay.py`（T394-1 ~ T394-4）

公共夹具：

```python
def _net_panels(rows, h_max=60):
    return {"decay_a_by_period": rows, "decay_h_max": h_max,
            "alpha0": 0.002629, "aum_ref": 1e10,
            "cost_by_h": {5: 1e6, 10: 2e6, 20: 4e6}}


def _varied_rows(n=20, h_max=60):
    base = np.arange(1, h_max + 1, dtype=float) * 1e-3
    noise = np.linspace(-2e-3, 2e-3, n)[:, None]
    return (base[None, :] + noise).tolist()
```

**T394-1 回退区间（红：现行 lo/hi 缺因子）**

```python
def test_fallback_net_interval_m_form():
    """T394-1: n_bootstrap=50 → 回退分支；lo/hi 与 m 形式独立复算一致。"""
    from backtest.execution.shell.runner import assemble_decay_curve
    rows = _varied_rows()
    payload = assemble_decay_curve(_net_panels(rows), n_bootstrap=50)
    assert "decay_ci_analytic_fallback" in payload["evidence_warnings"]
    aum, hm = 1e10, 20
    a_hm = payload["a"][str(hm)]["point"]
    nu = len(rows) - 1
    z = 1.959963984540054
    t_crit = (z + (z ** 3 + z) / (4.0 * nu)
              + (5 * z ** 5 + 16 * z ** 3 + 3 * z) / (96.0 * nu ** 2))
    mat = np.asarray(rows, dtype=float)
    for h, cost in ((5, 1e6), (10, 2e6), (20, 4e6)):
        col = mat[:, h - 1]
        ok = np.isfinite(col)
        se_a = float(np.std(col[ok], ddof=1) / np.sqrt(ok.sum()))
        m_se = se_a / (a_hm * float(h) / float(hm))
        m = payload["m"][str(h)]["point"]
        base_net = aum * a_hm
        item = payload["net"][str(h)]
        assert item["lo"] == pytest.approx(
            base_net * (m - t_crit * m_se) - cost, rel=1e-9, abs=1e-6)
        assert item["hi"] == pytest.approx(
            base_net * (m + t_crit * m_se) - cost, rel=1e-9, abs=1e-6)
        assert item["lo"] <= item["point"] <= item["hi"]
```

**T394-2 退化守卫（红：现行输出空壳敏感性）**

```python
def test_degenerate_skips_sensitivity():
    """T394-2: A(h_m)<0 → m_sensitivity == {}、不抛异常。"""
    from backtest.execution.shell.runner import assemble_decay_curve
    rows = np.full((20, 60), -1e-3).tolist()
    payload = assemble_decay_curve(_net_panels(rows), n_bootstrap=50)
    assert payload["m_sensitivity"] == {}
    assert "decay_curve_unidentified" in payload["evidence_warnings"]
```

**T394-3 `DecayCurve` 接线（红：现行 0 次构造）**

```python
def test_decay_curve_constructed(monkeypatch):
    """T394-3: assemble_decay_curve 构造 DecayCurve 恰好 1 次。"""
    from backtest.execution.core import decay as decay_mod
    from backtest.execution.shell.runner import assemble_decay_curve
    calls = []
    real = decay_mod.DecayCurve

    def spy(*args, **kwargs):
        calls.append(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(decay_mod, "DecayCurve", spy)
    payload = assemble_decay_curve(_net_panels(_varied_rows()))
    assert len(calls) == 1
    assert payload["phi_status"] == "fitted"
```

**T394-4 `sd` / `plateau`（红：现行 KeyError）**

```python
def test_net_sd_and_plateau():
    """T394-4: 主路径 net[h].sd 有限、plateau 含 argmax 且 ⊆ horizons。"""
    from backtest.execution.shell.runner import assemble_decay_curve
    payload = assemble_decay_curve(_net_panels(_varied_rows()))
    for h in ("5", "10", "20"):
        assert np.isfinite(payload["net"][h]["sd"])
        assert payload["net"][h]["sd"] >= 0.0
    assert set(payload["plateau"]) <= {5, 10, 20}
    nets = payload["net"]
    h_star = max(nets, key=lambda k: nets[k]["point"])
    assert int(h_star) in payload["plateau"]
```

### 4.2 `tests/test_minute_panels.py`（T394-5、T394-7、T394-8；T381-17 复核）

**T394-5 交集口径（红：现 `ratio=1.5` 且无 `ratio_raw`；算例为 DESIGN §10.2「3 分钟码 / 2 域」的等价替换——4 域码 + `counts=6`，0.5 / 1.5 / 6.0 三项结论一致，复审 F7）**

```python
def test_coverage_intersection(cfg, daily_ref):
    """T394-5: 交集比值 + 原式披露；stock_median 仍取 counts。"""
    from backtest.execution.shell.panels import MinutePanelBuilder
    builder = MinutePanelBuilder(cfg, loader=FakeLoader({}), daily=daily_ref)
    builder._month_codes = {"2023-01": np.asarray([1, 2, 999999])}
    cov = builder._coverage(["2023-01"], [], [], {"2023-01": 6},
                            {"2023-01": 0.0})
    assert cov.universe_ratio["2023-01"] == 0.5       # |{1,2}| / 4
    assert cov.ratio_raw["2023-01"] == 1.5            # 6 / 4（旧式分子）
    assert cov.stock_median == 6.0                    # INV-4
    assert cov.as_dict()["ratio_raw"]["2023-01"] == 1.5
```

**T394-8 向后兼容（红：现无该字段）**

```python
def test_panel_coverage_ratio_raw_default():
    """T394-8: 旧构造（不传 ratio_raw）可用；as_dict 含空 dict。"""
    from backtest.execution.shell.panels import PanelCoverage
    cov = PanelCoverage(window=("2023-01", "2023-01"), months=["2023-01"],
                        partial_months=[], missing_months=[],
                        stock_median=1.0,
                        universe_ratio={"2023-01": 0.5},
                        limit_lock_ratio=0.0, board_counts={"深主板": 1})
    assert cov.ratio_raw == {}
    assert cov.as_dict()["ratio_raw"] == {}
```

**T381-17 复核（不新增用例，Step 9 实跑确认）**：现行断言 `cov["universe_ratio"]["2023-03"] >= 0.90` 在**分钟码 ⊆ 日频域**时与旧口径数值恒等（`|M∩U|/|U| = |M|/|U|`）；若实跑低于 0.90，按 D10 留痕上报 + 登记 U-6，**不得静默放宽断言**。L297/L307 的 stub 直接构造 ratio dict，不受交集改动影响。

> **偏离声明（Step 8 F-C）**：DESIGN §10.1 行 5「更新 T381-17 期望」按「复核、不更新断言」实施——M⊆U 时新旧口径数值恒等，无需改期望；此为有意偏离。

### 4.3 `tests/test_execution_capacity.py`（T394-6）+ `tests/test_minute_panels.py`（T394-7，复审 F9 落位）

```python
def test_force_coverage_warning_contract():
    """T394-6: 留痕文案 token 化 + 脚本 force 分支已接线（源码文本断言）。"""
    from backtest.execution.shell.panels import force_coverage_warning
    assert force_coverage_warning(["a", "b"]) == "coverage_gate_forced: a; b"
    src = (Path(__file__).resolve().parent.parent
           / "scripts" / "verify_capacity_impact.py").read_text(encoding="utf-8")
    assert "force_coverage_warning(messages)" in src


def test_panel_hash_stable(cfg, daily_ref):
    """T394-7: 同一输入两次 _panel_hash 相同；payload 无 coverage 键（回归护栏，非红）。"""
    import inspect
    from backtest.execution.shell.panels import MinutePanelBuilder
    b1 = MinutePanelBuilder(cfg, loader=FakeLoader({}), daily=daily_ref)
    b2 = MinutePanelBuilder(cfg, loader=FakeLoader({}), daily=daily_ref)
    assert b1._panel_hash(["2023-01"], 3, 100) == b2._panel_hash(
        ["2023-01"], 3, 100)
    # INV-2/D8：hash payload 不含覆盖度键（复审 F2，以源码文本断言补齐）
    src = inspect.getsource(MinutePanelBuilder._panel_hash)
    assert "coverage" not in src
```

- T394-6 依赖 `Path`：该文件若未导入 `pathlib.Path` 需补一行 import；
- **落位裁决（复审 F9）**：`test_execution_capacity.py` 无 `cfg` / `daily_ref` / `FakeLoader`（复审已核），故 **T394-7 定位 `tests/test_minute_panels.py`**（夹具齐备），T394-6 留 `test_execution_capacity.py`（无夹具依赖）；
- **对 DESIGN §10.2 的偏离声明（复审 F2）**：DESIGN 要求「两次 `builder.build()`」，但 `FakeLoader({})` 下 `build()` 因窗口内无可用月份抛 `CalibrationUnavailable`（panels.py L452-453）——故改为直接调用 `_panel_hash` 两次；DESIGN 的「hash payload 无 coverage 键」护栏以 `inspect.getsource` 文本断言补齐，不丢失。

---

## 5. 兼容性与约束

| 项 | 结论 | 依据 |
|----|------|------|
| Python 3.9 | 兼容（无新语法） | §1 约束表 |
| 零新增依赖 | 是（只用 numpy / 标准库） | `numpy.std` / `np.asarray` |
| `core/decay.py` | 零改动，`__all__` 仍 5 项 | 只 import `DecayCurve` / `plateau` |
| 旧 `PanelCoverage(...)` 构造 | 兼容（新字段有默认值） | T394-8 |
| 旧 `ratio` 消费方 | 兼容：`coverage_gate` 仅读 `universe_ratio`；`ratio_raw` 为新增键 | panels.py L656 |
| md 报告 | 不渲染新键（§4.4 逐键取 point/lo/hi，script L483-488） | T394-6 同文件 |
| 默认 `out/capacity_impact.json` | 不经过改动路径 → SHA 不变 | `assemble_decay_curve` 仅在 `--decay-curve-json` 分支调用（script L639-644） |
| `out/v393_decay_curve.json` | **会变**（新增 `net[h].sd`、`plateau`）——预期内，非 SHA 锚定 | DESIGN §4.4 |

**性能**：`_universe_codes` 每月执行一次（39 次），单次为布尔掩码 + 列名遍历（≈5000 列），与既有 `_universe_count` 同量级；无 O(n²) 新增。

---

## 6. 不变式映射

| 不变式 | 实施位置 | 验证 |
|--------|---------|------|
| INV-1 默认 SHA 逐位不变 | 无改动路径 | Step 9 跑前/跑后/复跑三方 SHA |
| INV-2 `panel_hash` 前后相同 | 不触碰 L403-419 | Step 9 改码前备份 39 月 hash → 改码后对比（E1 第二源） |
| INV-3 `universe_ratio ≤ 1` 且 `≤ ratio_raw` | `_coverage`（交集/同分母） | T394-5；39 月读数表 |
| INV-4 `stock_median` 基于 `counts` | `_coverage` L391-397 未改 | T394-5 |
| INV-5 `net.point ∈ [lo, hi]` | F-1 同路径代数 | T394-1（回退分支，对称区间构造性含 point）；主路径为分位 CI、代数不保证，依托 v3.9.3 实测读数（复审 F8） |
| INV-6 退化态全部空/NaN | F-6 守卫 + 既有 NaN 分支 | T394-2 |
| INV-7 `sd` 有限 ⟹ 主路径可用 | §3.2.3 `if not degenerate and a_boot is not None` | T394-4；退化用例断言 NaN |
| INV-8 零依赖 / 3.9 / decay 零改动 | §5 | T393-7 既有用例继续通过 |

---

## 7. 错误处理映射

| 场景（DESIGN §7） | 实施 | 用户可见 |
|------------------|------|---------|
| 域为空 / 全部列键不可归一 | `denom <= 0` → `ratio=raw=None` | 门禁「覆盖度未产出」 |
| 个别列键不可归一 | `try/except` 跳过（分母收窄，有意） | 无（U-5 抽样） |
| 回退分支（`n_bootstrap<100`） | 既有 `except Exception` → `a_boot=None` | `decay_ci_analytic_fallback` |
| 回退分支 `m_se` 非有限 | `lo/hi=NaN` | 同左 |
| 退化态 | `net.*` / `sd` / `plateau` / `m_sensitivity` 全空或 NaN | `decay_curve_unidentified` |
| gate 失败且未 force | 原样 `return 2` | 既有 messages |
| gate 失败且 force | 追加 `coverage_gate_forced: …` | 校准工件 §6 节可见 |

---

## 8. Step 9 执行顺序与验收

### 8.1 实施顺序（TDD）

| 步 | 动作 | 预期 |
|----|------|------|
| 1 | 写 T394-1~T394-8 | 8 条全红 |
| 2 | `panels.py` §3.1.2 ~ §3.1.5 | T394-5/6/8 转绿 |
| 3 | `runner.py` §3.2.2（F-1） | T394-1 转绿 |
| 4 | `runner.py` §3.2.4（F-6） | T394-2 转绿 |
| 5 | `runner.py` §3.2.3（F-5） | T394-4 转绿 |
| 6 | `runner.py` §3.2.5（F-4） | T394-3 转绿 |
| 7 | script §3.3 | 全绿（T394-6 已含源码断言） |
| 8 | 文档 §3.4（F-2） | — |

### 8.2 通过线

- 全量 `2057 + 8 = 2065 passed / 15 skipped / 0 failed`
  （与 v3.9.3 的「collected 2065」数值巧合但含义不同，报告时须写明）；
- 默认 `out/capacity_impact.json` SHA = `82728CE103D49AF211DD12DE87D9784040FC909C83FB7A88D521AF30A89B2548`，跑前备份 / 跑后 / 复跑三方一致；
- `panel_hash` 39 月逐月对比一致（INV-2 第二源）；
- 39 月校准重跑：输出 `universe_ratio` 中位/最差、`ratio_raw` 对照表、门禁结果；若失败 → `--force-coverage` 跑一次并确认工件 §6 节含 `coverage_gate_forced:`；
- `out/v393_decay_curve.json`：`net[h].sd` 三键有限、顶层 `plateau` 非空（主路径）。

### 8.3 收尾同步（Step 9）

- 包版本 3.9.3 → 3.9.4：`pyproject.toml` / `__init__.py` / `config_v2.py` / `reporting.py` / 版本一致性测试；
- `CHANGELOG.md` / `README*.md` / `docs/PROJECT_STATUS.md` / `docs/PROGRESS.md`（P-012 / P-004 / P-005 → done，附实测读数）；
- `spec/v394-audit-coverage-fix/CHECKLIST.md`（Step 7 产出）。

---

## 9. 幻觉抑制审查（Step 6 待复审）

### 9.1 依赖与符号真实性

- [x] 零新增依赖，无虚构库；
- [x] 引用的 `DecayCurve`（decay.py L258-268）、`plateau`（L92-98）、`_month_row`（panels.py L197-210）、`as_dict`（L63-71）均已行号级核对；
- [x] `_month_codes` 类型已核实为 `np.unique` 输出（int64 ndarray），非 list。

### 9.2 接口与设计一致性

- [x] 与 DESIGN §4.1/§4.2/§4.3/§4.4 逐条对应；
- [x] `PanelCoverage` 非 frozen + `as_dict`（DESIGN v1.1 S1 勘误后一致）；
- [x] `coverage_gate` / `core/decay.py` 零改动（白名单外文件未触碰）。

### 9.3 实施与设计对齐

- [x] 每个编辑点可映射到 DESIGN 的一条决策（D1/D5/D6/D7/D8/D9/D11）；
- [x] 无设计未覆盖的实施（`__all__` 增项为 §4.3 新增函数的显式导出附带项）。

### 9.4 低效操作排除

- [x] `_universe_codes` 每 ym 一次，不重复计算；
- [x] `net_sd` 复用 `a_boot` / `m_boot`，不额外 bootstrap；
- [x] 无新增 I/O；测试无真实数据依赖（T381-17 除外，沿用既有 skip 标记）。

---

## 10. 异构复审记录（Step 6）

### 10.1 复审方式与输入

- 独立子代理（RULE-5），只读审查；输入 IMPLEMENTATION v1.0 draft + DESIGN v1.1 verified + RESEARCH v1.1 verified + 全量源码锚点清单；代码基线 `a0cf914`；工作区不可信，未执行任何脚本。

### 10.2 结论

**PASS_WITH_FIXES**：P1×0、P2×3、P3×6；维度 V3 PASS，V1/V2/V4/V5 PASS_WITH_FIXES；门禁 a-d 全 pass（b 的 8 条红前置逐一推演成立，含六项强制抽查）。全部修复已落盘至本版（v1.1）。

### 10.3 维度矩阵

| 维度 | 结论 | 关键依据 |
|------|------|---------|
| V1 行号锚点真实性 | PASS_WITH_FIXES | panels / runner / decay / effect_size / tests / v393 侧全部一致；script 侧 2 处错位（F4/F5）修复后闭合 |
| V2 设计对齐 | PASS_WITH_FIXES | 编辑点逐一映射 D1/D5/D6/D7/D8/D9/D11；§3.1.2 自相矛盾（F1）修复后对齐 |
| V3 硬约束 | PASS | 3.9 语法 / 仅 numpy / 默认路径不经过任何编辑点 / hash payload（L403-419）不触碰 |
| V4 测试可执行性 | PASS_WITH_FIXES | 8 条红前置全部成立；T394-7 弱化（F2）修复后可执行 |
| V5 兼容性与白名单 | PASS_WITH_FIXES | `_universe_count` 无其他调用方、`test_core_all_bounded` 仅扫 core/、DecayCurve kwargs 与 L258-268 逐项匹配；F3 注记损失修复后闭合 |

### 10.4 发现与处置（全部已落盘至 v1.1）

| ID | 级别 | 位置 | 缺陷 | 处置 |
|----|------|------|------|------|
| F1 | P2 | §3.1.2 | bullet「插在 universe_ratio 之后」与代码块「置末尾」矛盾——按 bullet 误读则带默认值字段先于无默认值字段，dataclass 直接 TypeError | bullet 改写：末位字段为唯一实施口径 |
| F2 | P2 | §4.3 T394-7 | 相对 DESIGN §10.2 弱化：删「payload 无 coverage 键」护栏且未声明偏离 | 补 `inspect.getsource` 文本断言 + 偏离声明（`FakeLoader({})` 下 `build()` 抛 `CalibrationUnavailable`，panels.py L452-453） |
| F3 | P2 | §3.4 | 替换文本丢失 v393 L460 原括号内 I-3 注记（计数口径信息净损失） | 注记保留 |
| F4 | P3 | §3.3.2 | `attach_panel_meta` 实为 script L271 定义、L628 调用；警告渲染节在 report.py L137-139——原锚点 L639-646 / L506-508 为 decay-curve md 侧 | 锚点更正（主会话已复核 script L271 与 report.py L137-141） |
| F5 | P3 | §3.3.2 | 替换块起点实为 L610（`coverage_gate` 调用行） | 标题改 L610-616 |
| F6 | P3 | §1 | 「5 处编辑点」与正文 12 个编辑块自相矛盾 | 改 12 块（panels ×5、runner ×5、script ×2）+ 1 处文档勘误 |
| F7 | P3 | §4.2 T394-5 | 算例形态偏离 DESIGN §10.2（4 域码 + counts=6 vs 3 分钟码 / 2 域），结论一致但偏差未声明 | 标题注明等价替换 |
| F8 | P3 | §6 INV-5 | 验证列仅 T394-1（回退分支对称区间构造性含 point）；主路径为分位 CI、代数不保证 | 注明主路径依托 v3.9.3 实测读数 |
| F9 | P3 | §2/§4.3 | T394-7 落点二义（§2 定 test_execution_capacity.py，§4.3 又给兜底） | 落位裁决：T394-7 定 test_minute_panels.py（夹具齐备）；T394-6 留原文件 |

### 10.5 门禁

- a. 白名单 ↔ 决策一一对应：**pass**（F9 记 P3 不破坏对应性）；
- b. 全部测试有真实红前置（T394-7 显式标非红）：**pass**——T394-1 现行 lo 缺 `h_m/h` 因子（h=5 处差 4 倍）、T394-2 现行退化态输出含 NaN 的非空 dict、T394-3 现 0 次构造、T394-4 现 KeyError、T394-5 现 `ratio=1.5` 且无 `ratio_raw`、T394-6 符号与调用点均不存在、T394-8 现无字段 AttributeError；六项强制抽查全过（t_crit nu=19 与 runner L302-315 逐字一致、monkeypatch 对函数内延迟 import 有效、夹具核验）；
- c. 无双向过强 / 无未溯源声明：**pass**（SHA 常量与 v393 L461 一致、2057+8=2065 算术自洽）；
- d. 硬约束贯穿（3.9 / 零依赖 / core/decay.py 零改动 / 默认 SHA）：**pass**。

### 10.6 边界声明

- 复审未执行任何测试/脚本（工作区不可信）：2057 / 2065 / 7 恒等式的实测计数与默认 SHA 实值未复核，仅核算术自洽与锚点——并入 Step 9 实跑核验（INV-1 三方 SHA、§8.2 通过线）；
- report.py 仅抽查警告渲染节；RESEARCH.md 未全文精读（以 DESIGN v1.1 为对齐主依据）；
- T394-4 的 plateau 成员集合依 decay.py L92-98 契约与数据形态推演（h*=5 必在集合内），未做数值仿真。

---

**Review 签字**: _________ 日期: _________
