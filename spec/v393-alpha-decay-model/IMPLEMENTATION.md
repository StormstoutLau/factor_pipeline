# IMPLEMENTATION v3.9.3 — alpha 衰减模型选择（FO-1）

---
id: v393-alpha-decay-model-IMPLEMENTATION
type: design
version: 1.1
status: verified
date: 2026-11-20
depends: [v393-alpha-decay-model-DESIGN, v393-alpha-decay-model-RESEARCH]
upstream: null
---

> **版本**: v1.1（2026-11-20；Step 5 产出 + Step 6 异构复审通过（2×P2 + 5×P3 已修复，见 §8））
> **对应设计**: [DESIGN.md](./DESIGN.md) **v1.1 verified**
> **对应调研**: [RESEARCH.md](./RESEARCH.md) **v1.3 verified**
> **批次**: v3.9.3（包版本 3.9.2 → 3.9.3）
> **执行方式**: TDD 先红后绿；Python 3.9 语法；零新增依赖；默认输出 SHA 不变

---

## §0 变更白名单

| 文件 | 动作 |
|------|------|
| `backtest/execution/core/decay.py` | 新增 `DecayCurve`（frozen dataclass）、`decay_multiplier`、`anchored_multiplier`、`fit_phi`、`net_point`、`net_ci`、`AnchoredDecay`、`EmpiricalDecay`；`__all__` **保持 5 项不变**（DR-3） |
| `scripts/verify_capacity_impact.py` | 新增 `formation_decay_curve`（保留形成期权重 → `A_by_period`）、`write_decay_curve`、`--decay-curve-json`；`build_portfolio_panels` 返回值增 `a_by_period` |
| `backtest/execution/shell/panels.py` | `build_daily_panels` 增 `decay_a_by_period` / `decay_h_max` / `alpha0_anchored`（校准分支专用，默认不写） |
| `backtest/execution/shell/runner.py` | 新增 `assemble_decay_curve(panels, h_m=20)` → §4.4 JSON payload；默认分支零改动 |
| `tests/test_execution_decay.py` | 新增 T393-1 ~ T393-8 |
| `tests/test_execution_capacity.py` | 新增 T393-9（`assemble_decay_curve` 集成） |
| `tests/test_minute_panels.py` | 新增 T393-10（panels 新键） |
| `pyproject.toml` / `__init__.py` / `config_v2.py` / `reporting.py` / `tests/test_fix3_version_unification.py` / `tests/test_backtest/verify_fix3_manual.py` | 版本 3.9.3 |
| `CHANGELOG.md` / `docs/PROJECT_STATUS.md` / `README.md` / `docs/PROGRESS.md` | 版本与批次同步 |

**不在白名单**：`ports.py`（`DecayModel` 协议不改）、`effect_size.py`（只复用）、`core/impact.py`、`loaders.py`、`out/capacity_impact.json`、`out/v392_calibration.*`、配置字段。

---

## §1 代码级变更

### 1.1 `core/decay.py`（纯函数 + 端口实现）

**关键约束（DR-3）**：`tests/test_execution_architecture.py::test_core_all_bounded` 要求每个 core 模块
`__all__` **≤ 5 项**；当前 `decay.py` 恰为 5 项。故新增符号**不进入 `__all__`**，由调用方显式
`from ..core.decay import ...` 导入（与 v3.9.2 `core/impact.py` A-3 先例一致）。`__all__` 逐字不改。

```python
from dataclasses import dataclass

_TOL = 1e-12


def _curve_dict(curve, h_m=None):
    """曲线映射归一到 {int h: float}；h_m 缺失即报错。"""
    out = {}
    for key, value in dict(curve).items():
        h = int(key)
        if float(key) != float(h):
            raise ValueError("curve 的 h 必须是整数: %r" % (key,))
        out[h] = float(value)
    if h_m is not None and int(h_m) not in out:
        raise ValueError("curve 缺少 h_m=%d" % int(h_m))
    return out


def decay_multiplier(curve, h_m=20):
    """非参乘子 m(h)=A(h)/[A(h_m)·h/h_m]；返回 {h: m}，强制 m[h_m]=1。

    A(h_m) 非有限或 <=0 时返回全 NaN（由调用方标 unidentified，DESIGN §7）。
    """
    a = _curve_dict(curve, h_m)
    hm = int(h_m)
    base = float(a[hm])
    if not np.isfinite(base) or base <= 0.0:
        return dict((h, float("nan")) for h in a)
    out = {}
    for h, value in a.items():
        if h == hm:
            out[h] = 1.0
            continue
        scale = base * float(h) / float(hm)
        ok = bool(np.isfinite(value)) and scale > 0.0
        out[h] = float(value / scale) if ok else float("nan")
    return out


def anchored_multiplier(phi, horizons, h_m=20):
    """参数乘子 m(h;φ)=(h_m/h)(1−φ^h)/(1−φ^{h_m})；φ==1 → 全 1。"""
    phi = float(phi)
    hm = int(h_m)
    if not (0.0 < phi <= 1.0):
        raise ValueError("phi 必须在 (0, 1] 内")
    if hm <= 0:
        raise ValueError("h_m 必须 > 0")
    hs = [int(h) for h in horizons]
    if phi == 1.0:
        return dict((h, 1.0) for h in hs)
    denom = 1.0 - phi ** hm
    out = {}
    for h in hs:
        if h == hm:
            out[h] = 1.0
            continue
        if h <= 0:
            raise ValueError("horizon 必须 > 0: %r" % (h,))
        out[h] = float((float(hm) / float(h)) * (1.0 - phi ** h) / denom)
    return out


def fit_phi(curve, h_m=20, grid=(0.01, 1.0), step=0.001, refine=10):
    """h∈{1..h_m} 上等权 SSE 拟合 φ（网格 → 局部精化）；返回 (phi, sse)。

    预注册（DESIGN §2 D2）：网格 [0.01, 1.0] 步长 0.001，最优网格点 ±step 内以
    step/refine 再细分一次；等权、不按 h 加权。可拟合 h 少于 2 个即 ValueError。
    """
    m_hat = decay_multiplier(curve, h_m)
    hs = [h for h in sorted(m_hat)
          if 1 <= h <= int(h_m) and np.isfinite(m_hat[h])]
    if len(hs) < 2:
        raise ValueError("可用于拟合的 h 不足 2 个")
    target = np.array([m_hat[h] for h in hs], dtype=float)
    lo, hi = float(grid[0]), float(grid[1])
    if not (0.0 < lo < hi <= 1.0):
        raise ValueError("grid 必须满足 0 < lo < hi <= 1")
    step = float(step)
    if step <= 0.0:
        raise ValueError("step 必须 > 0")

    def _sse(phi):
        pred = anchored_multiplier(phi, hs, h_m)
        fitted = np.array([pred[h] for h in hs], dtype=float)
        resid = target - fitted
        return float(np.dot(resid, resid))

    best_phi, best_sse, best_arg = 1.0, float("inf"), hi
    for value in np.arange(lo, hi + step * 0.5, step):
        phi = float(min(float(value), hi))
        sse = _sse(phi)
        if sse < best_sse:
            best_phi, best_sse, best_arg = phi, sse, phi
    span = step / float(refine)
    start, stop = max(lo, best_arg - step), min(hi, best_arg + step)
    for value in np.arange(start, stop + span * 0.5, span):
        sse = _sse(float(value))
        if sse < best_sse:
            best_phi, best_sse = float(value), sse
    return best_phi, best_sse


def net_point(alpha0, aum, m_by_h, cost_by_h):
    """net(h)=aum·alpha0·m(h)−cost(h)；点估计 {h: float}（未重采曲线）。"""
    out = {}
    for h, m in dict(m_by_h).items():
        h = int(h)
        if h not in cost_by_h:
            continue
        out[h] = float(aum) * float(alpha0) * float(m) - float(cost_by_h[h])
    return out


def net_ci(a_boot, m_boot, aum, cost_by_h, a_point, h_m=20, alpha=0.05):
    """{h: {"point","lo","hi"}}；point 取原始曲线，lo/hi 取重采样分位。

    a_boot / m_boot: ``{h: (reps,) 数组}``；a_point 为原始（未重采）A 曲线（DR-1）。
    """
    ...
```

`net_ci` 主体：

```python
    hm = int(h_m)
    if hm not in a_boot or hm not in m_boot:
        raise ValueError("a_boot/m_boot 缺少 h_m=%d" % hm)
    if not (0.0 < float(alpha) < 1.0):
        raise ValueError("alpha 必须在 (0, 1) 内")
    alpha_boot = np.asarray(a_boot[hm], dtype=float)
    point = net_point(float(dict(a_point)[hm]), aum,
                      decay_multiplier(a_point, hm), cost_by_h)
    out = {}
    for h in sorted(set(int(k) for k in m_boot) & set(int(k) for k in cost_by_h)):
        m_rep = np.asarray(m_boot[h], dtype=float)
        if m_rep.size != alpha_boot.size:
            raise ValueError("重采样样本长度不一致: h=%d" % h)
        values = float(aum) * alpha_boot * m_rep - float(cost_by_h[h])
        values = values[np.isfinite(values)]
        base = float(point.get(h, float("nan")))
        if values.size == 0:
            out[h] = {"point": base, "lo": float("nan"), "hi": float("nan")}
            continue
        lo, hi = np.quantile(values, [float(alpha) / 2.0, 1.0 - float(alpha) / 2.0])
        out[h] = {"point": base, "lo": float(lo), "hi": float(hi)}
    return out
```

数据结构与端口：

```python
@dataclass(frozen=True)
class DecayCurve:
    h_m: int
    horizons: Tuple[int, ...]
    a_mean: Mapping[int, float]
    m_point: Mapping[int, float]
    m_lo: Mapping[int, float]
    m_hi: Mapping[int, float]
    phi: float
    phi_status: str
    n_periods: int
    boot: Mapping[str, object]


class AnchoredDecay(object):
    """DecayModel 实现：retention(h) = m(h;φ)。"""
    name = "anchored"

    def __init__(self, phi, h_m=20):
        self.phi = float(phi)
        self.h_m = int(h_m)

    def retention(self, horizons):
        hs = [int(h) for h in horizons]
        values = anchored_multiplier(self.phi, hs, self.h_m)
        return np.array([values[h] for h in hs], dtype=float)


class EmpiricalDecay(object):
    """DecayModel 实现：直接返回非参 m̂(h)；缺失 h 线性插值，h_m 强制 1。"""
    name = "empirical"

    def __init__(self, curve, h_m=20):
        self.h_m = int(h_m)
        self.curve = dict((int(h), float(v)) for h, v in dict(curve).items())
        self.curve[self.h_m] = 1.0

    def retention(self, horizons):
        hs = [int(h) for h in horizons]
        known = sorted(self.curve)
        return np.interp(hs, known, [self.curve[k] for k in known])
```

> **入参口径易错点**：`decay_multiplier` / `fit_phi` / `net_point` / `net_ci` 收 **A 曲线**；
> `EmpiricalDecay` 收 **m̂ 映射**（已是乘子）。二者不得混用，测试 T393-1 显式覆盖。

### 1.2 `scripts/verify_capacity_impact.py`

**(a) 保留形成期权重（DESIGN §10.1 #4，本批唯一取数改造点）**

```python
def formation_decay_curve(P, w, h_max=60):
    """形成期 t0 冻结权重的后验累计超额 A_{t0}(h)，h=1..h_max。

    权重取 t0 快照后在**整个 h 窗口内不再调整**（DESIGN §2 D1「之后不再调整」）。
    不得复用 daily_portfolio_excess 的前向填充序列——它在下一形成日切换为新月
    权重，h 超过单月交易日数（约 21 日）后混入后续月权重，违反冻结语义（复审 I-1）。
    基准 rb（可投资域等权）与权重无关，全局计算一次；NaN 日按
    daily_portfolio_excess 同一 dropna 口径剔除（不计入 h 计数）。
    形成日 t0 当日的收益不计入（无前视，side="right"）。
    样本末端不足 h 日的形成期以 NaN 补齐（不缩短窗口、不用部分和）。
    """
    price = P['adj_price']
    r = price.pct_change(fill_method=None)
    ub = P['mask'].fillna(False).reindex(r.index, method='ffill')
    ub = ub.reindex(columns=r.columns).fillna(False)
    rb = r.where(ub).mean(axis=1)
    r0 = r.fillna(0.0)
    index = r.index
    rows = []
    for t0 in w.index:
        start = int(index.searchsorted(t0, side="right"))
        seg = r0.iloc[start:start + int(h_max)]
        wv = w.loc[t0].reindex(seg.columns).fillna(0.0)   # 冻结快照
        rp = seg.mul(wv, axis=1).sum(axis=1)
        ex = (rp - rb.reindex(seg.index)).dropna()
        row = np.full(int(h_max), np.nan)
        vals = ex.to_numpy()
        if vals.size:
            row[:vals.size] = np.cumsum(vals)
        rows.append(row)
    return rows
```

`build_portfolio_panels` 返回值新增：

```python
        'a_by_period': formation_decay_curve(P, w),
        'a_h_max': 60,
```

**(b) 独立工件写出（DESIGN §2 D4-3）**

```python
def write_decay_curve(path, payload):
    """写 out/v393_decay_curve.json + 同名 .md；payload 为 None 时跳过。"""
    if not payload:
        return []
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                      encoding='utf-8')
    md = target.with_suffix('.md')
    md.write_text(_decay_curve_md(payload), encoding='utf-8')
    return [str(target), str(md)]
```

`_decay_curve_md` 输出六节：口径（`h_m` / 期数 / `alpha0_anchored` vs `alpha0_calendar`）、
`m` 三值（含 `m_sensitivity` 附表）、`net` 三值、`verdict`、bootstrap 参数、`evidence_warnings`；
并固定写入「`m(20)=1` 为构造性归一 → 验收① 在修正口径下几乎恒成立（DESIGN §10.3）」一行；
`verdict` 节固定携带 DESIGN §4.4 术语映射（posterior=后置衰减 / flat=未检出衰减 /
anterior=前置 alpha）与「未检出衰减 ≠ 无衰减」表述纪律（I-7）。

**(c) CLI（唯一新增开关）**

```python
    ap.add_argument('--decay-curve-json', default=None,
                    help='校准路径额外写出 alpha 衰减曲线工件（默认不写）')
```

校准分支 `write_report(...)` 之后：

```python
        if args.decay_curve_json:
            from backtest.execution.shell.runner import assemble_decay_curve
            written_curve = write_decay_curve(
                args.decay_curve_json, assemble_decay_curve(panels))
            if written_curve:
                print('衰减曲线: %s' % ', '.join(written_curve))
```

### 1.3 `panels.build_daily_panels`

在 `out["alpha0"] = float(ex_m.mean())`（**不动**）之后追加：

```python
    rows = portfolio.get('a_by_period')
    if rows:
        mat = np.asarray(rows, dtype=float)
        if mat.ndim == 2 and mat.shape[0] and mat.shape[1]:
            out["decay_a_by_period"] = [
                [None if not np.isfinite(v) else float(v) for v in row]
                for row in mat]
            out["decay_h_max"] = int(mat.shape[1])
            if mat.shape[1] >= 20:
                col = mat[:, 19]
                ok = np.isfinite(col)
                out["alpha0_anchored"] = (float(col[ok].mean())
                                          if ok.any() else None)
            else:
                out["alpha0_anchored"] = None
```

- `out["alpha0"]`（日历月均值）保留 → 报告为 `alpha0_calendar` 对照（DESIGN §2 D3）。
- `build_daily_panels` 仅在 `--calibrate` / `--diagnose-window` 分支被调用（脚本 L473-L475），
  默认路径（L510 起）不经过此处 → G6 默认零影响成立。

### 1.4 `runner.assemble_decay_curve`

```python
def assemble_decay_curve(panels, h_m=20, n_bootstrap=1000, block_size=3, seed=0):
    """按 DESIGN §3/§4.4 装配衰减曲线 payload；无 A 矩阵时返回 None。"""
```

实现分七步（全部在函数内完成，无 IO）：

1. **取矩阵**：`mat = np.asarray(panels["decay_a_by_period"], float)`，`h_max = min(panel 声明, mat.shape[1])`；空/不足返回 `None`。
2. **A(h) 与 n_h**：逐列 `ok = np.isfinite(col)`，`a_mean[h] = col[ok].mean()`，`a_median[h] = np.median(col[ok])`（DESIGN §2 D1 中位数并列，I-6），`n_by_h[h] = int(ok.sum())`（DR-2：样品末端不足 h 日的形成期不计入该 h）。
3. **非参乘子**：`m_point = decay_multiplier(a_mean, h_m)`。
4. **bootstrap**：`idx = stationary_bootstrap_indices(n_periods, n_bootstrap, block_size, seed)`（**复用** `backtest/effect_size.py`，`from ...effect_size import stationary_bootstrap_indices`；函数内导入，沿用 `estimate_rho` 的延迟导入风格）；对每 h：`sample = col[idx]`，`A_b(h) = nanmean`，`m_b(h) = A_b(h) / (A_b(h_m)·h/h_m)`（`h==h_m` 且 `A_b(h_m)` 有限时强制 1.0，`A_b(h_m)<=0` 置 NaN）；`m_lo/m_hi = np.quantile(samples, [0.025, 0.975])`。
4b. **敏感性（预注册，I-2）**：对 `block_size ∈ {1, 6}` 各以同 `n_bootstrap`/`seed` 重跑上步 m 重采样（复用同一 A 列，仅换 `idx`），得各 h 的 `{lo, hi}` → payload `m_sensitivity: {"1": {h: {lo, hi}}, "6": {...}}`，md 附表并列（DESIGN §2 D1 / §10.2 预注册）。主 CI 仍取 b=3。
5. **φ**：`n_by_h[h_m] >= 10` → `fit_phi(a_mean, h_m)`，`phi_status="fitted"`；`< 10` → 先验 `phi = 2 ** (-1.0 / 126.0)`（半衰期 6 个月 = 126 交易日，保守主值；md 并列报 252 日值），`phi_status="prior"`，`decay_source="prior"`（DR-4）。
6. **net 三值**：`net_ci(a_boot, m_boot, aum, cost_by_h, a_mean, h_m)`，`aum = float(panels.get("aum", panels.get("aum_ref", 1e10)))`。
7. **verdict**：`hi < 1` → `"posterior"`；`lo > 1` → `"anterior"`；否则 `"flat"`；`lo/hi` 非有限 → `"unidentified"`（DR-5）。verdict 仅 `{5, 10}` 两键（对齐 DESIGN §4.4 schema，I-4）；`m`/`a`/`net` 仍对 `horizons = [5, 10, 20]` 输出，`h=20` 仅展示不参与判定。
8. **payload 组装细则（I-5）**：`alpha0_anchored = a_mean[h_m]`、`alpha0_calendar = panels.get("alpha0")`（ex_m 日历月均值，D3 对照字段）；所有标量经 `int()`/`float()` 转 Python 原生再入 payload（`ok.sum()` 产出 `np.int64`，`json.dumps` 不认）；`alpha0_anchored` 为 None 或 `A(h_m) <= 0`（`phi_status="unidentified"`）时，`m`/`a`/`net` 的 lo/hi 一律 NaN、verdict 全 `unidentified`，不抛异常；`a_mean` 入 `net_ci` 前经 `_curve_dict` 校验（缺 `h_m` 即 `ValueError`）。

告警：`n_by_h[h_m] < 10` → `decay_prior_fallback`；`10 <= n < 39` → `decay_small_sample`；`A(h_m) <= 0` → `decay_curve_unidentified`；`fit_phi` 抛 `ValueError` → `phi=1.0`、`phi_status="unidentified"`、`decay_phi_fit_failed`；bootstrap 抛异常 → 39 期 t 分布解析近似、`decay_ci_analytic_fallback`。

payload 字段与 [DESIGN §4.4](./DESIGN.md#44-校准工件outv393_decay_curvejson) 逐键一致（`h_m` / `n_periods` / `alpha0_anchored` / `alpha0_calendar` / `phi` / `phi_status` / `decay_source` / `horizons` / `m` / `a` / `net` / `boot` / `verdict` / `evidence_warnings`），另加 `n_by_h`（DR-2 披露）、`m_sensitivity` 与 `a[h].median`（DR-7 披露，I-2/I-6）。

### 1.5 低效操作排除

| 项 | 处置 |
|----|------|
| 39 期 × 60 日 A 矩阵 | 单次 `cumsum` 切片，O(39·60)，无循环 IO |
| bootstrap 1000 × 39 | 一次 `idx` 矩阵 + 向量化 `nanmean`，60 列共 ~2.3M 元素，内存 < 20 MB |
| 重复读盘 | `formation_decay_curve` 内 `r`/`rb` 各计算一次（`rb` 与权重无关，全局一次）；不复用 ffilled 序列是为 D1 冻结权重语义（I-1）——面板已在内存，向量化 `pct_change` 重复一次可接受 |
| core 依赖 | 不引入 pandas / pathlib；`np.interp` 代替手写插值 |
| 默认路径 | 不进入任何新计算（`build_daily_panels` 仅校准分支调用） |

---

## §2 派生需求登记（Step 8 追溯用）

| ID | 派生需求 | 出处 | 验收方式 |
|----|----------|------|----------|
| DR-1 | `net_ci` 需原始曲线入参 `a_point` 才能给 `point`（DESIGN §4.1 签名 `(a_boot, m_boot, aum, cost_by_h)` 只有分布） | DESIGN §2 D5「point 取原始曲线」 | T393-4 断言 `point == net_point(A(20), aum, m̂, cost)` |
| DR-2 | 样本末端形成期不满 h 日 → 该 h 的有效期数 `n_h < 39`；`A(h)` 只对完整窗口期取均值，JSON 报 `n_by_h` | DESIGN §3.1「39 期取均值」隐含完整窗口 | T393-9 断言 `n_by_h[60] <= n_by_h[5] <= 39` 且 md 披露 |
| DR-3 | core `__all__` 上限 5 与 DESIGN §10.1「`__all__` 只增不改」冲突 → 保持 5 项，新符号走显式 import | `tests/test_execution_architecture.py::test_core_all_bounded` | 该测试保持绿 |
| DR-4 | 先验半衰期取 126 交易日为**主值**（252 日仅在 md 并列） | DESIGN §7「6/12 个月 ≈ 126/252 交易日」未指定唯一值 | T393-8 断言 `phi == 2**(-1/126)` |
| DR-5 | verdict 增 `unidentified`（lo/hi 非有限时） | DESIGN §4.4 只列 posterior/flat/anterior | T393-8 |
| DR-6 | 新增 CLI `--decay-curve-json`（默认关闭）作为独立工件的唯一入口 | DESIGN §2 D4-3「新增独立工件」未指定开关 | T393-11 断言不传时不写文件 |
| DR-7 | payload 相对 DESIGN §4.4 schema 增设 `m_sensitivity`（b=1/6 敏感性 CI）与 `a[h].median`（中位数并列）——均为 schema 外追加披露键，不改既有键 | DESIGN §2 D1 / §10.2 有要求但 §4.4 schema 未设字段（I-2/I-6） | T393-9 断言两键存在；md 附表展示 |

---

## §3 测试（先红）

| # | 文件 | 用例 | 红阶段断言 |
|---|------|------|-----------|
| T393-1 | test_execution_decay | `test_decay_multiplier_anchors` | `m[h_m]==1`（1e-12）；`A(h)=c·h` → `m≡1`；`A(h_m)<=0` → 全 NaN |
| T393-2 | test_execution_decay | `test_anchored_multiplier_limits` | `φ=1 → 1`；`φ=0.01` 时 `m(1) = h_m(1−φ)/(1−φ^{h_m}) ≈ 19.8`（容差 0.1，I-3 连带）；`0<φ<1` 严格递减且 `h<h_m` 时 `m>1` |
| T393-3 | test_execution_decay | `test_fit_phi_recovers` | 以 `φ*=0.95` 生成 `A(h)=c(1−φ^h)/(1−φ)` → `|φ̂−φ*| ≤ 5e-3`、`sse < 1e-10` |
| T393-4 | test_execution_decay | `test_net_point_and_ci` | `net_point` 恒等式；`net_ci` 的 `point` 等于原始曲线读数；`lo <= point <= hi`（有限时） |
| T393-5 | test_execution_decay | `test_decay_ports_protocol` | `AnchoredDecay(1.0).retention([1,5,20])==1`；`EmpiricalDecay` 缺 h 线性插值、`h_m` 强制 1；`name` 属性存在 |
| T393-6 | test_execution_decay | `test_invariants_flat_and_degenerate` | 不变式 2/3/4 逐条 |
| T393-7 | test_execution_decay | `test_architecture_all_unchanged` | `decay.__all__` 仍 5 项且不含新符号 |
| T393-8 | test_execution_decay | `test_assemble_degradations` | 期数 9 → `decay_source="prior"`、`phi==2**(-1/126)`；`A(20)<=0` → `phi_status="unidentified"`、`m` 全 NaN、verdict `unidentified` |
| T393-9 | test_execution_capacity | `test_assemble_decay_curve_payload` | 合成 39×60：键集合齐全、`m["20"]["point"]==1`、`n_by_h` 单调、`net` 三值有限、`m_sensitivity`/`a[h].median` 存在、`json.dumps(payload)` 成功（无 numpy 标量，I-5） |
| T393-10 | test_minute_panels | `test_daily_panels_emit_decay_matrix` | `decay_a_by_period`/`decay_h_max`/`alpha0_anchored` 存在且与 `a_by_period` 一致；无 `a_by_period` 时不写新键 |
| T393-11 | 命令级 | 默认路径 SHA + 不写曲线 | SHA `82728CE1…` 不变；不带 `--decay-curve-json` 时 `out/v393_decay_curve.json` 不存在 |

> 先红：T393-1~T393-10 在未改实现时因 `ImportError` / 键缺失失败。
> T393-11 仅在 Step 9 末执行。

---

## §4 版本与文档同步

1. `pyproject.toml` L7、`__init__.py` L58、`config_v2.py` L371、`reporting.py` L40 → `3.9.3`；
2. `tests/test_fix3_version_unification.py` L34、`tests/test_backtest/verify_fix3_manual.py` L21 → `EXPECTED_VERSION = "3.9.3"`；
3. `CHANGELOG.md` 顶部：

```markdown
## v3.9.3 — alpha 衰减模型选择（对应路线图批次 v3.9.3）(已实施, 2026-11-20)
```

4. `docs/PROJECT_STATUS.md` §1 增 `v3.9.3` 行、进度条与 §2 待办；
5. `README.md` L9/L1241/L1244/L1246/L1247/L1293 版本句与实测读数；
6. `docs/PROGRESS.md` P-002 依据列追加「IMPLEMENTATION（Step 5-6）」并更新状态。

---

## §5 门禁命令

```powershell
# 1) 新增用例（先红）
python -m pytest tests/test_execution_decay.py tests/test_minute_panels.py tests/test_execution_capacity.py -q
# 2) 架构耦合（DR-3 / __all__ 上限）
python -m pytest tests/test_execution_architecture.py -q
# 3) 全量
python -m pytest -q
# 4) 默认路径 SHA（必须逐位不变）
python scripts/verify_capacity_impact.py
(Get-FileHash out/capacity_impact.json -Algorithm SHA256).Hash
# 5) 校准路径 + 衰减曲线工件（独立文件，不覆盖 v392 工件）
python scripts/verify_capacity_impact.py --calibrate --calibration-json out/v393_calibration.json --decay-curve-json out/v393_decay_curve.json
```

**通过线**：

- 全量 ≥ **2055 + 10 = 2065** passed / 15 skipped / **0 failed**（T393-1~T393-10 为 pytest 用例；T393-11 命令级不计入，I-3）；
- 默认 `out/capacity_impact.json` SHA = `82728CE103D49AF211DD12DE87D9784040FC909C83FB7A88D521AF30A89B2548`；
- `out/v393_decay_curve.json` 含 `m`/`a`/`net` 三值，`m["20"]["point"] == 1.0`（1e-12），`verdict` 两键（`5`/`10`，I-4）齐全。

---

## §6 回填

- CHECKLIST：T393-1 ~ T393-11 逐项证据 + DR-1 ~ DR-7 单项验收；
- IMPLEMENTATION §9：实测读数（`phi`、`alpha0_anchored` vs `alpha0_calendar`、`m(5/10/20)` 三值、`net` 三值、`n_by_h`、verdict）；
- CHANGELOG「实测读数」小节；PROJECT_STATUS/README 版本与基线；
- PROGRESS P-002 状态与验收①②③判读（含 DESIGN §10.3 验收①推论披露）。

---

## §7 风险

| # | 风险 | 处置 |
|---|------|------|
| R1 | 样本末端形成期不足 60 日 → 长 h 期数递减，`A(60)` 波动大 | DR-2 报 `n_by_h`；验收只看 5/10/20 |
| R2 | `A(20) <= 0`（符号翻转）→ φ 不可估 | 按 DESIGN §7 标 `unidentified`，不伪造衰减 |
| R3 | 39 期 CI 偏宽覆盖 1 → 无法判后置 | 预注册「未检出衰减」表述；不写「无衰减」 |
| R4 | 新增符号撞 core `__all__` 上限 5 | DR-3：`__all__` 不动，显式 import |
| R5 | 新键污染默认 JSON | `build_daily_panels` 仅校准分支；命令级 SHA 断言 |
| R6 | 版本同步漏点（6 处代码 + 6 处文档） | §4 清单逐项勾验，`test_fix3_version_unification` 兜底 |
| R7 | `--decay-curve-json` 覆盖既有工件 | 文件名独立（`v393_*`），不触碰 `v392_calibration.*` 与 `capacity_impact.json` |

---

## §8 步骤 6 复审记录（v1.0 → v1.1，2026-11-20）

> **异构声明**: 本文档 §0-§7 由 Step 5 撰写会话产出；本 pass 在独立新会话中由**不同模型基座**执行复审（RULE-5 异构，满足基座异质要求；基座家族信息以会话记录为准，复审方不自证撰写方基座）。
> **单向权限**: 复审只作标记（§8.2 发现表）；修正为标记后的最小修复落盘，§0 白名单边界与 DR-1~DR-6 同 DESIGN D1-D5 的绑定关系未被复审方改写。
> **复审对象**: IMPLEMENTATION v1.0 全文（§0-§7）。
> **执行方式**: 全文重读 + DR-1~DR-6 与 DESIGN §2/§4/§7/§10 逐条对照 + 函数体可实现性静态推演（Python 3.9 / 零新增依赖 / stdlib 下限核对）+ 锚点实测（`pyproject.toml` L7 / `__init__.py` L58 / `config_v2.py` L371 / `reporting.py` L40 / `test_fix3_version_unification.py` L34 / `verify_fix3_manual.py` L21 / `panels.py` L522-L617 / `runner.py` L292-L310 / `effect_size.py` L128-L160 / `decay.py` 全文 107 行 / 脚本 L153-L233、L428-L508）+ SHA 串机器比对 + 门禁 a-d。
> **结论: PASS_WITH_FIXES** —— 7 项发现（**2×P2 + 5×P3**），全部最小修复；无 P1/P0；无遗留阻断项。

### 8.1 视角 × 探针矩阵

| 视角 | 探针 | 结果 | 说明 |
|---|---|---|---|
| V1 公式与计量正确性 | P1 独立复算 | PASS | net 代数自洽：`net_point(alpha0=A(h_m), m̂)` 展开为 `aum·A(h)·h_m/h − cost(h)`，与 `cost(h)=(20/h)·…` 月频口径一致；`m(20)=1` → `net(20)=aum·alpha0−cost(20)` 与 DESIGN §10.3 一致；`anchored_multiplier`/`decay_multiplier` 与 DESIGN §4.1 逐式一致；`fit_phi` 网格（0.001）+ 精化（1e-4）对 φ*=0.95 可恢复，T393-3 断言可行 |
| V2 可追溯性 | P2 DR-1~DR-6 回溯 DESIGN | PASS（2 修复 → I-2/I-6） | 白名单/接口/测试均可在 DESIGN 找到出处；DR-1~DR-6 登记诚实；缺口：DESIGN D1/§10.2 预注册的敏感性 b=1/6 与 A(h) 中位数并列在 §1.4 实现步骤中缺失 |
| V3 接口可行性 | P3 对照仓内代码 | PASS（1 修复 → I-1） | 新符号不进 `__all__` → `test_core_all_bounded` 兼容（DR-3）；`stationary_bootstrap_indices(n, n_bootstrap, block_size, seed)` 签名与 b=1 退化实测一致；10 处版本/行号锚点全部命中；**缺陷**：`formation_decay_curve` 复用 ffilled 日超额序列——该序列在下一形成日切换权重，`A_{t0}(h)` 在 h≳21 后混入后续月权重（h=60 严重），违反 DESIGN D1「形成时权重、之后不再调整」，docstring「冻结」与「前向填充」自相矛盾 |
| V4 一致性与边界 | P4 计数/键域/序列化/退化 | PASS（3 修复 → I-3/I-4/I-5） | 通过线「2055+11」计数错误（pytest 新增仅 T393-1~T393-10 共 10 项）；verdict 键域「[5,10,20] 输出」与 DESIGN §4.4 schema（仅 5/10 两键）冲突；payload 含 `np.int64`（`ok.sum()`）时 `json.dumps` 抛 TypeError；`alpha0_calendar` 来源、`alpha0_anchored` None 时 net 路径 `float(None)` 崩溃未写明 |
| V5 预注册与决策效度 | P5 预注册完整性 | PASS（1 修复 → I-7） | 预注册参数全部保留（b=3/1000 次/seed=0/网格 0.001/三态判定/horizons）；md 报告未要求携带 verdict 术语映射与「未检出衰减 ≠ 无衰减」表述纪律（DESIGN §4.4 注） |

### 8.2 发现清单

| ID | 级别 | 章节 | 缺陷 | 处置 |
|---|---|---|---|---|
| I-1 | P2 | §1.2(a) | `formation_decay_curve` 复用 `daily_portfolio_excess` 前向填充序列：下一形成日起权重切换，`A_{t0}(h)` 在 h≳21 后混入后续月权重，违反 DESIGN §2 D1「形成时权重、之后不再调整」与 §10.1 #4「保留形成期权重」的本意；docstring 自相矛盾 | 已修复：重写为 t0 权重快照全程冻结（`rb` 与权重无关全局一次）；§1.5 低效排除行同步 |
| I-2 | P2 | §1.4 | DESIGN §2 D1/§10.2 预注册的敏感性 bootstrap（b=1 / b=6）在实现七步中缺失，照实施将静默丢弃预注册稳健性检查 | 已修复：增 step 4b（同 reps/seed 换块长）+ payload `m_sensitivity` + md 附表 + DR-7 |
| I-3 | P3 | §3/§5 | 通过线「2055 + 11」计数错误（pytest 新增仅 10 项）；T393-2 的 `m(1)≈h_m` 断言不精确（φ=0.01 时实际 ≈19.8） | 已修复：改 ≥ 2065 passed；断言改闭式 `≈19.8`（容差 0.1） |
| I-4 | P3 | §1.4 step7 / §5 | verdict 说「对 [5,10,20] 输出」与 DESIGN §4.4 schema（仅 5/10 两键）不一致；§5 通过线「verdict 三键」同病 | 已修复：verdict 键域 = `{5, 10}`；`m`/`a`/`net` 仍报 5/10/20 |
| I-5 | P3 | §1.4 | payload 组装细则缺失：`ok.sum()` 为 `np.int64`（`json.dumps` 抛 TypeError）、`alpha0_calendar` 来源未写、`alpha0_anchored` None / `A(h_m)<=0` 时 net 路径 `float(None)` 崩溃、`a_point` 无校验 | 已修复：增 step 8 组装细则（原生标量转换 / 来源显式 / 退化 NaN 化不抛异常 / `_curve_dict` 校验）；T393-9 增 `json.dumps` 断言 |
| I-6 | P3 | §1.4 step2 | DESIGN §2 D1「对 39 期取均值（**中位数并列展示**）」的中位数在实现与 payload 中缺失 | 已修复：step 2 增 `a_median`，payload `a[h].median`（DR-7） |
| I-7 | P3 | §1.2(b) | `_decay_curve_md` 六节未要求 verdict 节携带 DESIGN §4.4 术语映射与「未检出衰减 ≠ 无衰减」表述纪律 | 已修复：md 要求补两句固定文案 |

### 8.3 门禁 a-d

- **(a) FALSIFIED 不复活**：`exp(λ(h_m−h))` 未出现在任何实现代码；「m=1 为上界」表述未回潮（md 固定行为「构造性归一」）——通过。
- **(b) 冲突裁决**：DR-3（core `__all__` ≤5 vs DESIGN §10.1「只增不改」）显式裁决为「保持 5 项 + 显式 import」，与 v3.9.2 `core/impact.py` A-3 先例一致；DR-7（payload 扩展 vs §4.4 schema）裁决为「schema 外追加披露键、不改既有键」——通过。
- **(c) 阻断性断言双源**：锚点类全部实测（10 处版本/行号 + `decay.py` 107 行 + `effect_size.py` 签名 + SHA 串四文件机器比对逐字一致）；代数类独立复算（net 展开、φ 恢复界）——通过。
- **(d) 假设带入**：DR-1~DR-7 全部登记并入 §3 测试 / §5 通过线 / §6 回填，无静默假设——通过。

### 8.4 复审边界

- 工作区 untrusted：未执行任何仓内脚本/测试；可实现性为静态推演 + v3.9.2 同型先例（`core/impact.py` 扩展）佐证；
- SHA 基线为四文件文档串逐字比对一致（v393 IMPLEMENTATION §5 / v392 CHECKLIST L19 / v392 IMPLEMENTATION L227 / v392 AUDIT L42）；最终以 Step 9 `Get-FileHash` 实测为准；
- E1 数值（`alpha0_anchored`、`m`、`net`、verdict 判读）在 Step 9 产出前未知，本 pass 不预填；
- U-3（D5 报告形态）/ U-4（接口）维持「保留观察」，Step 9 / CHECKLIST 关闭。

**Review 签字**: 异构复审 pass（RULE-5 · 独立新会话）｜Step 6 复审 2026-11-20｜结论: PASS_WITH_FIXES → `verified`

---

## §9 Step 9 实测读数（2026-11-20）

> 命令：`python scripts/verify_capacity_impact.py --calibrate --calibration-json out/v393_calibration.json --decay-curve-json out/v393_decay_curve.json`（exit 0；`evidence_level=minutes`）。
> 工件：[v393_decay_curve.json](../../out/v393_decay_curve.json)（SHA256 `D06225DF0BBC78584B55E6930E5B3A9B4524A749FFDEB72B8E8AE009FC9E78A4`，seed=0）/ [v393_decay_curve.md](../../out/v393_decay_curve.md)。

| 项 | 实测 | 备注 |
|----|------|------|
| 形成期数 `n_periods` | **73** | 价格面板月频形成期；分钟数据覆盖 39 月（观察项 D-1） |
| `alpha0_anchored = A(20)` | **0.00220065** | 主值（锚定口径） |
| `alpha0_calendar` | **0.00262866** | 旧值对照（日历月均值），相对差 **−16.3%** |
| `phi` / `phi_status` / `decay_source` | **0.9999999999999992** / `fitted` / `empirical` | n=71 ≥ 10，未走先验；拟合结果≈1（平直） |
| `m(5)` point / lo / hi | **0.3820** / −3.8529 / 1.8477 | CI 覆盖 1 |
| `m(10)` point / lo / hi | **0.3948** / −3.3612 / 1.1484 | CI 覆盖 1 |
| `m(20)` | **1.0** / 1.0 / 1.0 | 构造性归一（INV-1） |
| `a(5)` point / median | 0.000210 / 0.000371 | 72 期 |
| `a(10)` point / median | 0.000434 / 0.000726 | 72 期 |
| `a(20)` point / median | 0.002201 / 0.001613 | 71 期 |
| `net(5)` point / lo / hi | **−7,159,077** / −45,211,215 / +34,351,319 | 元/期；AUM=面板 `aum_ref` |
| `net(10)` point / lo / hi | **+905,290** / −28,260,925 / +28,341,407 | ≥1 点 >0（P-002①） |
| `net(20)` point / lo / hi | **+18,115,106** / +1,684,760 / +34,258,624 | 构造性口径，判别力有限 |
| `verdict` | `{5: flat, 10: flat}` | 未检出衰减 ≠ 无衰减（I-7） |
| `n_by_h` | 5→72；20→71；60→**28** | 样本末端截断，长 h 递减（DR-2） |
| `evidence_warnings` | `[]` | 无降级触发 |
| `m_sensitivity` b=1 / b=6（h=5 hi） | 1.6244 / 1.7070 | 与主 CI 同向（覆盖 1） |
| 装配性能 | 0.100 s / 峰值 4.4 MB（73×60，reps=1000，3 轮块长） | 目标 <20 MB |
| 默认 `out/capacity_impact.json` SHA | `82728CE103D49AF211DD12DE87D9784040FC909C83FB7A88D521AF30A89B2548` | 逐位不变 |
| 全量测试 | 2057 passed / 15 skipped / 0 failed（796.71 s、825.00 s 两次一致） | 计数差观察项 D-3 |
| 同 seed 复跑工件 | SHA `D06225DF0BBC78584B55E6930E5B3A9B4524A749FFDEB72B8E8AE009FC9E78A4`（两次独立运行逐位一致） | 可复现性成立（P-002①） |

**判读**：`m(5)`/`m(10)` 点估计 <1 但 95% CI 宽覆盖 1，按预注册判 `flat`；不得表述为「无衰减」。`net(20)>0` 主要由 `m(20)=1` 构造性保证（DESIGN §10.3 已披露），`net(10)` 点为正、CI 覆盖 0。


---

**状态**: v1.1 verified — Step 6 异构复审通过（PASS_WITH_FIXES，I-1~I-7 已修复，见 §8）
