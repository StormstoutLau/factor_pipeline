# 实施文档：P-010 月聚类 CI + 粒度披露

---
id: p010-granularity-bias-IMPLEMENTATION
type: design
version: 1.3
status: verified
date: 2026-11-22
depends: [p010-granularity-bias-DESIGN, p010-granularity-bias-RESEARCH]
upstream: [v392-calibration-unit-fix-IMPLEMENTATION]
---

> **Feature**: 标定系数 `c` / `b` 的 bootstrap 推断口径由 iid 行抽样改为月聚类整块重采样，并披露粒度、簇数与少簇敏感性
> **创建日期**: 2026-11-22
> **状态**: verified（Step 5-6 完成；v1.3 = Step 9 红→绿实施记录 + 实测读数，见 §14；Step 6 复审见 §13）
> **Spec 步骤**: Step 5-6
> **基于设计**: [DESIGN.md](./DESIGN.md) **v1.1 verified**
> **基于调研**: [RESEARCH.md](./RESEARCH.md) **v1.2 verified**
> **档位**: T1 ｜ **包版本**: 3.9.7 → 3.9.8 ｜ **新依赖**: 无（仅 numpy，已在 `requirements`）

---

## 1. 实施概述

本实施分 7 步、触及 4 个源文件 + 2 个测试文件 + CHANGELOG：

1. `panels.py`：把已在样本元组第 5 位的 `ym` 提升为输出数组 `impact_samples["month"]`，全局 cap 改为**四数组同索引切片**并删除只会丢标签的 `_stratified_sample`；`impact_samples_meta` 增 `cluster/n_clusters/ci` 三键。
2. `runner.py`：`_bootstrap_ci` 增可选 `clusters` 参数（`None` 走原代码路径，逐位不变）；新增 `_cluster_blocks`、`_cluster_labels`、`_wild_sqrt_ci`；`c_info` 增 10 个披露字段；`b` 的 CI 同步聚类。
3. `report.py`：在「c 三档」表后按字段存在性追加 2-3 行口径披露，旧 payload 不报错。
4. 版本 3.9.8 落 7 处 + CHANGELOG 条目。

全程不触碰 `core/impact.py`、`panel_hash` payload、默认（非 `--calibrate`）路径与容量公式。

## 2. 工程细节

### 2.1 技术栈

| 组件 | 技术 | 版本 | 验证状态 |
|------|------|------|---------|
| 语言 | Python | 3.9+（`requires-python >=3.9`） | ✅ 仓内现有约束 |
| 数值 | numpy | 现有锁定版本（`np.random.default_rng` / `np.percentile`） | ✅ 现有依赖 |
| 测试 | pytest | 现有版本（`pytest.mark.skipif`） | ✅ 仓内现有用法 |
| 新增依赖 | **无** | — | ✅ |

### 2.2 依赖版本验证

| 依赖 | 声明版本 | 使用 API | 兼容性 | 验证方式 |
|------|---------|---------|--------|---------|
| numpy | 现有锁定 | `default_rng.integers` / `flatnonzero` / `percentile` / `unique` | ✅ | 仓内既有调用（runner L161-L176） |
| pytest | 现有锁定 | `skipif` / `approx` | ✅ | `tests/test_minute_panels.py` L30 既有标记 |

**无新增第三方依赖**，不涉及 PyPI 版本核对。

### 2.3 文件结构（改动面）

```
backtest/execution/shell/
├── panels.py        # 改：全局 cap（L636-L641）+ 输出（L663-L666）；删 _stratified_sample（L154-L157）
├── runner.py        # 改：_bootstrap_ci（L161-L176）+ 新增 3 个函数 + c_info 组装（L459-L514）
└── report.py        # 改：c 表后披露行（L54-L59 之间）
tests/
├── test_execution_capacity.py   # 增：TP10-1~9（合成面板）
└── test_minute_panels.py        # 增：TP10-5 的 build() meta 断言（needs_minutes）
CHANGELOG.md                     # 增：3.9.8 条目
docs/EXECUTION_V3.8.1_MINUTE_PANEL_WIRING.md
                                 # D-10-4：L494-L507 观测样本分层段改写（函数已删、等距抽样内联，F-6）
spec/v392-calibration-unit-fix/DESIGN.md
                                 # D-10-5：§1.2 L38 非目标加 P-010 勘误指针
spec/v392-calibration-unit-fix/RESEARCH.md
                                 # D-10-5：§2 L50 悬空引用加勘误（F-9-1）
```

### 2.4 算法与源码级证据锚点（2026-11-22 抓取验证）

> 验证方式：学术条目用 Crossref REST `api.crossref.org/works/<DOI>` 解析；源码用 GitHub raw 抓取原文；官方/实现文档用 WebFetch 抓取原文。全部为本次实际抓取，非记忆引用。

| # | 层级 | 锚点（原文要点） | 对应实施方案 | 验证状态 |
|---|---|---|---|---|
| A1 | 学术·算法 | Cameron, Gelbach & Miller (2008) *Bootstrap-Based Improvements for Inference with Clustered Errors*, **REStat 90(3):414-427**, DOI `10.1162/rest.90.3.414`。pairs cluster bootstrap 的规范来源：重采样单位是**簇**、每轮抽 G 个簇、用重抽分布做百分位推断 | `_cluster_blocks` + `_bootstrap_ci(clusters=...)` 的整块重采样 | ✅ Crossref 解析（vol 90 / issue 3 / 414-427 / 2008-08 / cites 4178）；另有 NBER WP 13052 `10.3386/t0344`（2007-09） |
| A2 | 源码 | `linearmodels/shared/covariance.py::group_debias_coefficient` 原文：`return (ngroups / (ngroups - 1)) * ((n - 1) / n)`，docstring 公式 `g/(g−1)·(n−1)/n`；同文件 `cov_cluster` 在 `num_clusters < 2` 时 `raise ValueError("A clustered covariance requires at least two clusters...")` | `c_ci_debias_*` 的 factor；`too_few` 回退阈值取 2 | ✅ GitHub raw 抓取（main 分支，2026-11-22） |
| A3 | 源码 | `statsmodels/stats/sandwich_covariance.py` 模块 docstring：cluster sandwich 先按簇聚合再取外积 `S = sum_g(x·u)' dot sum_g(x·u)`；`cov_cluster(..., use_correction=True, crv_type='cluster')` 为 CRV1 + 小样本修正；Notes「same result as Stata ... same as Peterson」 | `_wild_sqrt_ci` 的簇得分聚合顺序（先簇内求和、再簇间加权）；`use_t` / t(38) 的 G−1 口径 | ✅ GitHub raw + statsmodels API 文档抓取（2026-11-22） |
| A4 | 源码 | R `sandwich::vcovCL` / `meatCL`：`cadjust = TRUE`（簇调整默认开启）、`type` 对 `lm` 默认 `"HC1"`、支持多向聚类 | group_debias 敏感性的独立实现佐证（R 生态默认做簇调整） | ✅ rdrr.io CRAN 文档抓取（2026-11-22） |
| A5 | 实现 | `fwildclusterboot::boottest`：Rademacher / Webb / Mammen 权重、`seed` 参数保证可复现、fast wild 算法源自 Roodman et al. (2019)；同页列出 Stata `boottest` / Julia `WildBootTests.jl` / Python `wildboottest` 实现 | `_wild_sqrt_ci` 的 Rademacher 权重 + 固定 seed + 200 次重抽 | ✅ rdrr.io CRAN 文档抓取（2026-11-22） |
| A6 | API·算法 | `numpy.percentile` 默认 `method='linear'`（NumPy ≥1.22 由 `interpolation` 更名；Hyndman & Fan 1996 类型 7），固定分位插值算法 | `_bootstrap_ci` / `_wild_sqrt_ci` 的 5%/95% 端点计算，保证跨版本可重放 | ✅ numpy 官方文档抓取（2026-11-22） |

**核验纠错记录（幻觉抑制实例）**：初拟引用 A1 曾按记忆写作 `10.1162/rest.91.3.414`，Crossref 解析返回 **404**；改用 `query.bibliographic` 检索后确认正确 DOI 为 `10.1162/rest.90.3.414`（卷 90 而非 91）。已按验证值登记，并保留此记录说明「不凭记忆写引用」。

**算法对照（实现伪码 ↔ 锚点）**：

| 实现行 | 算法动作 | 锚点 |
|---|---|---|
| `blocks = _cluster_blocks(labels)` | 按簇切块、簇内保持原序 | A1（重采样单位=簇） |
| `pick = rng.integers(0, g, size=g)` | 每轮有放回抽 G 个簇（簇数固定） | A1 |
| `idx = np.concatenate([blocks[k] for k in pick])` | 整块拼接为一次重抽样本 | A1 + C1 |
| `np.percentile(reps, [5, 95])` | 百分位 CI（线性插值） | A6 |
| `factor = sqrt(g/(g-1) * (n-1)/n)` | 小样本簇调整（仅敏感性） | A2 + A4 |
| `w = rng.integers(0,2)*2-1` | Rademacher wild 权重 | A5 |
| `if g < 2: return None, None` | 少于 2 簇不可聚类 | A2（源码同款守卫） |

### 2.5 社区案例（T3，仅作实现风险提示，不升级为设计依据）

| # | 案例 | 关键内容（抓取原文） | 对本实施的含义 |
|---|---|---|---|
| C1 | Cross Validated **Q46821**「Bootstrapping hierarchical/multilevel data (resampling clusters)」，score 12，accepted answer 10 分 | 「Resampling the whole clusters has been known in survey statistics ... so it is a well established method」 | 佐证「整块重采样」而非行抽样；与 `_cluster_blocks` 一致 |
| C2 | Cross Validated **Q202916**「Cluster Bootstrap with Unequally Sized Clusters」，score 8，accepted answer | 簇大小不等时按同大小块分组、各自有放回重抽；**重复抽中的簇应视为不同簇**（尤其模型含簇维度固定效应时） | 我方 39 个月样本量不等（1.677 行/股票×月），按簇等概率重抽属标准 pairs bootstrap；估计量为比值 `Σxy/Σx²`、**无簇固定效应**，重复块直接作为重复行参与点积即可，无需额外合并——登记为已考虑项 |
| C3 | Cross Validated **Q205036**（RESEARCH §3.6 已引） | 少簇 + 簇内相关时普通 bootstrap 失真 | 与 group_debias / wild 两档敏感性对应 |
| C4 | Stack Overflow 两次检索均 **0 命中** | 宽词「statsmodels cluster robust standard errors groups df_correction」→ 0；窄词「bootstrap clustered standard errors python implementation」→ 0 | 按 F3 降级链如实登记，不凑数；社区证据以 Cross Validated 为主 |

> 引用可解析性：C1 `https://stats.stackexchange.com/questions/46821`、C2 `.../202916`、C3 `.../205036`；直接抓取页面被 Cloudflare 拦截，改由 StackExchange API（`mcp_stackexchange_get_answers`）取得 accepted answer 原文，属异构通道。

## 3. 模块实施

### 3.1 `panels.py`（月标签与 meta）

#### 职责

保证 `impact_samples["month"]` 与 `p/impact/sigma` 严格同索引、同序，且 `panel_hash` 输入零改动。

#### 接口签名

```python
# 删除（唯一调用点改造后不再需要）
# def _stratified_sample(p, impact, sigma, cap, seed=None): ...

def build(self):  # 既有方法，仅改尾部
    ...
```

#### 实施要点

- 在 L636-L638 三数组构造后增加：

```python
month = np.asarray([s[4] for s in self._samples], dtype=object)
if p.size > SAMPLE_CAP:
    idx = _sample_indices(p, sigma, SAMPLE_CAP)
    p, impact, sigma, month = (p[idx], impact[idx], sigma[idx], month[idx])
```

- `_sample_indices` 在 `p.size <= cap` 时返回 `arange`，故 `month` 在无截断时也必然生成；
- 输出 L663 改为 `"impact_samples": {"p": p, "impact": impact, "sigma": sigma, "month": month}`；
- meta L664-L666 增 `"cluster": "month"`、`"n_clusters": int(np.unique(month).size)`、`"ci": "month_cluster_pairs"`；`granularity` **保持 `"daily"`**；
- 删除 `_stratified_sample`（grep 确认仅 L640 一处调用、无测试导入、不在 `__all__`）；
- `panel_hash` 调用（L658）**不传** `month`，payload 与算法零改动。

#### 低效操作排除

| 潜在低效 | 排除措施 |
|---|---|
| 为取 `ym` 再遍历一次全部样本 | 一次列表推导 `[s[4] for s in self._samples]`，O(n) 且复用已有循环产物 |
| 全局 cap 二次 `argsort` | 复用现有 `_sample_indices`（`lexsort` 一次，O(n log n)） |
| 无截断时也做索引复制 | 保留 `if p.size > SAMPLE_CAP` 门控 |

### 3.2 `runner.py`（聚类 bootstrap 与敏感性）

#### 职责

提供月聚类 pairs bootstrap（主口径）、iid 对照、group_debias 缩放与 wild cluster 分位；不改变点估计。

#### 接口签名

```python
def _cluster_blocks(clusters):            # List[np.ndarray]
def _cluster_labels(samples, n_rows):     # (labels | None, reason | None)
def _bootstrap_ci(fit_fn, p, impact, sigma, seed, n_boot=200, clusters=None):
def _wild_sqrt_ci(p, impact, sigma, clusters, seed, n_boot=200):  # (lo, hi) | (None, None)
```

#### 实施要点

- `_cluster_blocks`：`order = np.argsort(labels, kind="stable")`，用 `flatnonzero(sorted[1:] != sorted[:-1]) + 1` 切块，返回索引块列表（簇内保持原行序）；
- `_bootstrap_ci`：`clusters is None` 时**逐字保留**现有循环（`rng.integers(0, n, size=n)`）→ INV-2；有簇时每轮 `pick = rng.integers(0, g, size=g)` + `np.concatenate([blocks[k] for k in pick])`，其余（`fit_fn` 调用、`ValueError` 跳过、`<20` 返回 `None`）完全复用；
- `_cluster_labels` 返回 `(labels, None)` 或 `(None, reason)`，`reason ∈ {"missing", "length_mismatch", "too_few"}`；**判定在调用方**，`_bootstrap_ci` 保持二元组契约（DESIGN F-7）；
- `_wild_sqrt_ci`：`x = sigma * sqrt(min(p, 1.0))`（与 `SqrtImpact.predict` 的 clip 一致）；`c = Σxy/Σx²`；`resid = y − c·x`；簇得分 `s_g = Σ_{i∈g} x_i·resid_i`；每轮 `w_g ∈ {−1,+1}`（`rng.integers(0,2)*2-1`），`c* = c + Σ w_g s_g / Σx²`；取 5%/95% 分位；`g<2` 或 `n_boot<20` 返回 `(None, None)`；
- `c_info` 组装（L492-L499 处扩展）：

```python
lower_iid, upper_iid = _bootstrap_ci(..., cfg.seed, clusters=None)
lower, upper = _bootstrap_ci(..., cfg.seed, clusters=labels)   # labels 可 None
c_info = c_triplet(point, lower, upper)
c_info.update({
    "c_ci_method": "month_cluster_pairs" if labels is not None else "iid_fallback",
    "c_ci_n_clusters": (int(np.unique(labels).size)
                        if labels is not None else None),  # 回退不报簇数（F-2）
    "c_calib_lower_iid": lower_iid, "c_calib_upper_iid": upper_iid,
})
if labels is not None:
    g, n = int(np.unique(labels).size), int(p.size)
    factor = float(np.sqrt((g / (g - 1.0)) * ((n - 1.0) / n)))
    half = 0.5 * (upper - lower)
    c_info["c_ci_debias_lower"] = point - half * factor
    c_info["c_ci_debias_upper"] = point + half * factor
    w_lo, w_hi = _wild_sqrt_ci(p, impact, sigma, labels, cfg.seed + 2)
    c_info["c_ci_wild_lower"], c_info["c_ci_wild_upper"] = w_lo, w_hi
```

- `b` 分支（L509-L511）传入同一 `labels`；`b_info` 结构不变；
- warning 文案（DESIGN §7）：`c_ci_fallback_iid: 样本缺少月簇标签` / `...长度不一致` / `...簇数 < 2`；wild 为 `None` 时 `c_ci_wild_unavailable`；
- 两处 CI 的 `n_boot` 默认 200、seed 语义不变；新增 iid 对照与 wild 各 200 次重抽样，单次 fit 为 O(n) 点积，39 月 200k 样本下增量约 1-2 s，可接受。

#### 低效操作排除

| 潜在低效 | 排除措施 |
|---|---|
| 每轮重抽时重新分组 | `_cluster_blocks` 只算一次，循环内仅 `concatenate` |
| 每轮复制全量样本再 `fit` | 与现状一致（`p[idx]` 花式索引），量级不变 |
| 簇内样本被重复扫描求得分 | wild 的簇得分一次 `np.add.reduceat`/循环求完（39 次） |
| 每次都算 wild/debias | 仅在 `labels is not None` 时计算，合成面板零额外开销 |

### 3.3 `report.py`（披露）

#### 职责

让读者在报告里看到「CI 用的是月聚类、簇数多少、iid 对照与少簇敏感性」，旧 payload 不渲染。

#### 实施要点

在 L54-L59 的 c 表循环后插入（条件渲染）：

```python
if c.get("c_ci_method"):
    lines.append("")
    if c.get("c_ci_method") == "month_cluster_pairs":
        lines.append("- c CI 口径: `month_cluster_pairs`，簇数 %s"
                     % c.get("c_ci_n_clusters"))
    else:
        lines.append("- c CI 口径: `iid_fallback`（样本缺少月簇标签或簇数不足）")
    if c.get("c_calib_lower_iid") is not None:
        lines.append("- iid 对照 CI: [%s, %s]"
                     % (c.get("c_calib_lower_iid"), c.get("c_calib_upper_iid")))
    if c.get("c_ci_debias_lower") is not None:
        width = float(c["c_calib_upper"]) - float(c["c_calib_lower"])
        dwidth = float(c["c_ci_debias_upper"]) - float(c["c_ci_debias_lower"])
        factor = (dwidth / width) if width else None
        lines.append("- 少簇敏感性: group_debias 宽度 ×%s；wild cluster CI [%s, %s]"
                     % (_num(factor, "%.4f"),
                        c.get("c_ci_wild_lower"), c.get("c_ci_wild_upper")))
```

复算 `factor` 不新增字段（避免契约膨胀，D-10-2）；簇数仅在聚类口径下打印（F-2）。

### 3.4 版本落点（D7）

| # | 文件 | 位置 | 现值 → 新值 |
|---|---|---|---|
| 1 | `pyproject.toml` | L7 | `3.9.7` → `3.9.8` |
| 2 | `backtest/execution/__init__.py` | L58 | 同上 |
| 3 | `backtest/execution/config_v2.py` | L371 | 同上 |
| 4 | `backtest/execution/reporting.py` | L40 | 同上 |
| 5 | `tests/test_fix3_version_unification.py` | L34 | 同上（期望值） |
| 6 | `tests/test_backtest/verify_fix3_manual.py` | L21 | 同上（期望值） |
| 7 | `CHANGELOG.md` | 顶部 | 新增 3.9.8 条目 |

## 4. 接口实施

### 4.1 `_bootstrap_ci`

```python
def _bootstrap_ci(fit_fn, p, impact, sigma, seed, n_boot=200, clusters=None):
    """对样本行做 bootstrap，返回 5% / 95% 分位。

    clusters is None：iid 行抽样（v3.9.7 行为，逐位不变）；
    clusters 非 None：按簇整块重采样（月聚类 pairs bootstrap）。
    有效重抽样 < 20 次返回 (None, None)。
    """
    rng = np.random.default_rng(int(seed))
    n = int(p.size)
    blocks = None if clusters is None else _cluster_blocks(clusters)
    reps = []
    for _ in range(int(n_boot)):
        if blocks is None:
            idx = rng.integers(0, n, size=n)
        else:
            pick = rng.integers(0, len(blocks), size=len(blocks))
            idx = np.concatenate([blocks[k] for k in pick])
        try:
            value = fit_fn(p[idx], impact[idx], sigma[idx])
        except ValueError:
            continue
        reps.append(value)
    if len(reps) < 20:
        return None, None
    return (float(np.percentile(reps, 5.0)),
            float(np.percentile(reps, 95.0)))
```

**签名一致性**: 与 DESIGN §4.1 一致 ✅（新增参数置于末尾、默认 `None`）

### 4.2 `_cluster_blocks` / `_cluster_labels`

```python
def _cluster_blocks(clusters):
    """把逐行簇标签切成索引块（簇内保持原行序，块按首现顺序）。"""
    labels = np.asarray(clusters, dtype=object).ravel()
    order = np.argsort(labels, kind="stable")
    sorted_labels = labels[order]
    cuts = np.flatnonzero(sorted_labels[1:] != sorted_labels[:-1]) + 1
    bounds = np.concatenate(([0], cuts, [order.size]))
    return [order[bounds[i]:bounds[i + 1]] for i in range(bounds.size - 1)]


def _cluster_labels(samples, n_rows):
    """校验 month 标签；返回 (labels, None) 或 (None, reason)。"""
    month = samples.get("month")
    if month is None:
        return None, "missing"
    arr = np.asarray(month, dtype=object).ravel()
    if arr.size != int(n_rows):
        return None, "length_mismatch"
    if np.unique(arr).size < 2:
        return None, "too_few"
    return arr, None
```

### 4.3 `_wild_sqrt_ci`

```python
def _wild_sqrt_ci(p, impact, sigma, clusters, seed, n_boot=200):
    """Rademacher wild cluster bootstrap（仅 sqrt c）；少簇敏感性附表。"""
    p_arr = np.asarray(p, dtype=float).ravel()
    y = np.asarray(impact, dtype=float).ravel()
    s = np.asarray(sigma, dtype=float).ravel()
    try:
        c = float(SqrtImpact().fit(p_arr, y, s)["c"])  # 与点估计同口径（F-3）
    except ValueError:
        return None, None
    x = s * np.sqrt(p_arr)                              # 与 fit 的设计矩阵同式（不 clip）
    denom = float(np.dot(x, x))
    if denom <= 0.0 or int(n_boot) < 20:
        return None, None
    resid = y - c * x
    blocks = _cluster_blocks(clusters)
    if len(blocks) < 2:
        return None, None
    scores = np.asarray([float(np.sum(x[b] * resid[b])) for b in blocks])
    rng = np.random.default_rng(int(seed))
    reps = []
    for _ in range(int(n_boot)):
        w = rng.integers(0, 2, size=scores.size) * 2 - 1
        reps.append(c + float(np.dot(w, scores)) / denom)
    return (float(np.percentile(reps, 5.0)),
            float(np.percentile(reps, 95.0)))
```

**签名一致性**: 与 DESIGN §4.2 一致 ✅（参数不变；c 改由 `SqrtImpact().fit` 求得，消除与点估计的 clip 口径分歧，F-3；runner 已 import `SqrtImpact`，无新增依赖）

## 5. 兼容性

### 5.1 Python 版本兼容

| Python 版本 | 支持 | 说明 |
|---|---|---|
| 3.9+ | ✅ | 仅用 `np.argsort(kind="stable")` / f-string 以外既有语法 |
| 3.8 | ❌ | 仓内 `requires-python >=3.9` 既有约束，未新增限制 |

### 5.2 依赖兼容

无新增依赖；`numpy` API 均为长期稳定接口（`default_rng` 自 1.17 起）。

### 5.3 向后兼容

- `run_calibration` 输入：无 `month` 键的合成面板 → iid 回退 + warning，不抛异常（`tests/test_execution_capacity.py` 的 `_panels()` 无需改动）；
- 输出：只增键；`c_default`/`c_calib_point`/`c_calib_stress` 公式与语义不变；
- `c_calib_lower/upper` 语义变更（iid → 月聚类）以 `c_ci_method` + `c_calib_lower_iid/upper_iid` 显式标注；
- 报告：旧 payload（无新键）不渲染披露行，输出逐字不变；
- `_stratified_sample` 为私有函数（不在 `__all__`、无外部导入），删除安全；`EXECUTION_V3.8.1_MINUTE_PANEL_WIRING.md` L497 的引用由 D-10-4 在 Step 8 同步。

## 6. 错误处理实施

| 错误场景（DESIGN §7） | 异常类型 | 处理代码 | 测试 |
|---|---|---|---|
| `month` 缺失 | 无（不抛） | `_cluster_labels` → `"missing"` → 传 `clusters=None` + warning | TP10-2 |
| `month` 长度不一致 | 无（不抛） | `_cluster_labels` → `"length_mismatch"` | TP10-2（参数化） |
| 簇数 < 2 | 无（不抛） | `_cluster_labels` → `"too_few"` | TP10-2（参数化） |
| 有效重抽样 < 20 | 无（不抛） | `_bootstrap_ci` 既有分支 → `(None, None)` → `point, point` + warning | 既有用例 |
| wild 不可用 | 无（不抛） | `_wild_sqrt_ci` 返回 `(None, None)` + warning | TP10-8 |
| `denom <= 0`（p/sigma 退化） | 无（不抛） | `_wild_sqrt_ci` 直接 `(None, None)` | TP10-8 参数化 |

## 7. 不变式实施

| 不变式（DESIGN §8） | 实施位置 | 验证方式 |
|---|---|---|
| INV-1 默认 SHA `82728CE1…` | 未改默认分支；`scripts/verify_capacity_impact.py` 默认路径零 diff | TP10-6（跑前/跑后 SHA） |
| INV-2 `clusters=None` 逐位一致 | `_bootstrap_ci` 保留原 `rng.integers(0,n,size=n)` 路径 | TP10-2 + 既有 `test_same_params_same_result` |
| INV-3 四数组等长且 `month ⊆ panel.months` | panels L636-L641 同索引切片 | TP10-5 |
| INV-4 `granularity == "daily"` 且 hash 不变 | panels L664-L666 + `_panel_hash` 未改 | TP10-5 + TP10-10（hash 与 v3.9.7 一致） |
| INV-5 `c_ci_n_clusters == len(unique(month))` | runner `c_info` 组装 | TP10-4 |
| INV-6 `c` 块只增不改 | `c_triplet` 未改，`update` 追加 | TP10-9 + 既有 `test_c_triplet` |

## 8. 测试策略

### 8.1 单元测试（`tests/test_execution_capacity.py`，TP10-1~9）

| # | 测试函数 | 构造 | 断言 |
|---|---|---|---|
| TP10-1 | `test_bootstrap_cluster_wider_than_iid` | 10 簇 × 20 行，簇内 `impact = 簇均值 + 噪声` | 同 seed 下聚类 CI 宽度 > iid 宽度 |
| TP10-2 | `test_ci_fallback_without_month`（3 参数化） | `_panels()` 无 `month` / 长度错 / 单簇 | `c_ci_method=="iid_fallback"`；`c_ci_n_clusters is None`；CI 与 v3.9.7 期望逐位一致；`c_calib_lower_iid == c_calib_lower`；warning 含 `c_ci_fallback_iid` |
| TP10-3 | `test_bootstrap_cluster_reproducible` | 两次 `run_calibration` | `json.dumps(sort_keys=True)` 相等 |
| TP10-4 | `test_ci_n_clusters` | 39 个合成月标签 | `c_ci_n_clusters == 39` |
| TP10-5 | `test_build_meta_cluster`（`test_minute_panels.py`，`needs_minutes`）+ 合成 builder 单测 | 真实 39 月 / 合成 | `month` 与 `p` 等长；`cluster=="month"`；`ci=="month_cluster_pairs"`；`granularity=="daily"` |
| TP10-6 | `test_default_path_sha_unchanged` | 跑前落盘 `out/capacity_impact.json` → 跑默认脚本 → SHA 比对 | 与跑前基线全等（`hexdigest` 小写；若用前缀断言须 `.upper().startswith("82728CE1")`，F-4） |
| TP10-7 | `test_debias_width_scaling` | 从输出反算 | `(debias_w)/(cluster_w) ≈ sqrt(g/(g−1)·(n−1)/n)`，容差 1e-12 |
| TP10-8 | `test_wild_ci_bounds` | 39 簇合成；再加单簇用例 | 有限且含点估计；单簇 → `None` |
| TP10-9 | `test_report_disclosure` | 新 payload / 旧 payload 各一次 | 新含 `month_cluster_pairs` + 簇数；旧输出逐字不变 |

### 8.2 集成测试（TP10-10，`needs_minutes`）

`--calibrate` 全链路（39 月）：新字段齐全、`c_ci_n_clusters==39`、聚类宽度/iid 宽度 ≥ 1.5（E1 为 1.838）、`panel_hash` 与 v3.9.7 基线 `dfcc4e1d…`（P-008 Step 9 记录）一致、`data_alignment` 无变化。

### 8.3 属性测试

不新增 hypothesis 依赖；TP10-3/TP10-7 作为确定性属性断言覆盖。

### 8.4 回归基线

- `tests/test_execution_capacity.py` 全量保持通过（实测 **30** 个 test 函数；参数化展开数以 pytest collect 为准，F-5）；
- `tests/test_minute_panels.py` 既有用例保持通过（实测 **40** 个 test 函数；P-008 记录的「42 passed」为当时两文件合计历史值，不可转用；`_stratified_sample` 删除不影响，grep 无导入）；
- 版本一致性测试 2 项随版本号更新。

## 9. 幻觉抑制审查（Step 6 Review 自检）

### 9.1 依赖版本验证

- [x] 无新增依赖，不涉及 PyPI 查询
- [x] 无虚构库或函数（全部 numpy 既有 API，仓内已有同款调用）
- [x] 兼容性：`requires-python >=3.9` 未变

### 9.2 接口签名验证

- [x] `_bootstrap_ci` 新参数 `clusters=None` 与 DESIGN §4.1 一致，默认值保持旧行为
- [x] `_wild_sqrt_ci` 与 DESIGN §4.2 一致，返回值二元组
- [x] `c_info` 字段逐条对应 DESIGN §4.4 表（10 项；`c_ci_debias_factor` 不入字段，D-10-2）

### 9.3 实施与设计对齐

- [x] 4 个模块对应 DESIGN §3.2 的 4 行
- [x] 无设计未覆盖的实施（版本落点属 D7；测试属 §12 预注册）
- [x] F-1 已吸收：文档/CHANGELOG 明确「容量读数不变，仅 `c_calib_stress` 报告值上升」

### 9.4 低效操作排除

- [x] 分组一次 O(n log n)，循环内无重排
- [x] 无新增 I/O；`month` 仅在内存中传递，不写入 `capacity_impact.json`
- [x] wild/debias 仅在簇标签可用时计算

### 9.5 引用与算法锚点核查

- [x] 学术锚点经 Crossref REST 解析（A1；含 1 次 DOI 404 → 检索订正记录）
- [x] 源码锚点经 GitHub raw 抓取原文（A2/A3；含函数名与关键行原文引用）
- [x] 官方/实现文档经 WebFetch 抓取（A4/A5/A6）
- [x] 社区案例经 StackExchange API 取得 accepted answer 原文（C1/C2/C3），未命中项如实登记（C4）
- [x] 算法对照表逐行可追溯到锚点（§2.4 第二张表）
- [x] Step 6 独立复审复核本条（PASS_WITH_FIXES，见 §13）

> 本表为实施者自检；Step 6 独立复审结论见 §13（PASS_WITH_FIXES，已闭环）。

## 10. 实施步骤（Step 9 TDD 顺序）

| 步 | 文件 | 内容 | 对应测试 |
|---|---|---|---|
| S1 | `panels.py` | 月标签数组 + 四数组同索引切片 + meta 三键 + 删 `_stratified_sample` | TP10-5 |
| S2 | `runner.py` | `_cluster_blocks` / `_cluster_labels` / `_bootstrap_ci(clusters)` | TP10-1/2/3/4 |
| S3 | `runner.py` | `_wild_sqrt_ci` + debias 缩放 | TP10-7/8 |
| S4 | `runner.py` | `c_info` 组装 + warning + `b` 聚类 | TP10-2/4 |
| S5 | `report.py` | 披露 3 行（条件渲染） | TP10-9 |
| S6 | 版本 7 落点 + CHANGELOG | 3.9.8 | 版本一致性测试 |
| S7 | 实测 | 默认 SHA（TP10-6）+ 39 月校准（TP10-10） | 集成 |

**红→绿约定**：先落 TP10-1~9（预期 `KeyError: 'month'` / `TypeError: unexpected keyword 'clusters'` 等），再按 S1-S6 逐个转绿；S7 为实测步骤，读数回填 §11。

## 11. 验证矩阵与预期读数

| # | 验证项 | 命令/方式 | 预期 |
|---|---|---|---|
| V1 | 合成面板聚类宽度 | TP10-1 | 聚类宽度 > iid 宽度（构造保证） |
| V2 | iid 回退逐位 | TP10-2 + 既有 `test_same_params_same_result` | 与 v3.9.7 输出一致 |
| V3 | 默认路径 SHA | 默认脚本跑前/跑后 | `82728CE1…` 逐位一致 |
| V4 | 39 月校准 | `python scripts/verify_capacity_impact.py --calibrate`（`needs_minutes`） | `c_calib_point ≈ 2.9100`（容差 0.5%）；`c_ci_n_clusters == 39`；聚类/iid 宽度比 ≈ 1.84（≥1.5）；`granularity=="daily"` |
| V5 | `panel_hash` 不变 | 与 P-008 Step 9 基线 `dfcc4e1d…` 比对 | 逐字一致 |
| V6 | debias 因子 | TP10-7 | 1.01307（g=39、n≈200k） |
| V7 | 报告渲染 | TP10-9 | 含 `month_cluster_pairs` / `39` / `iid 对照` |

> 注意：生产样本经全局 cap 后 n≈200,000（E1 探针为 200,031，未做全局 cap），故 V4 的 `c` 与 CI 端点允许 ≤0.5% 偏差；若超出 → 停止并按 DESIGN U-3 触发条件复审聚类实现。

## 12. 衍生需求

| # | 需求 | 来源 | 处置 |
|---|---|---|---|
| D-10-1 | 报告对缺失新键容错（旧 payload 不报错） | DESIGN §4.5 向后兼容 | S5 条件渲染 + TP10-9 |
| D-10-2 | 不新增 `c_ci_debias_factor` 字段，报告按宽度比推导 | 契约最小化（DESIGN F-4 教训） | S5 |
| D-10-3 | `b` 只给聚类 CI，不增 iid 对照 | 字段最小化 | S4 |
| D-10-4 | 改写 `docs/EXECUTION_V3.8.1_MINUTE_PANEL_WIRING.md` L494-L507 观测样本分层段：函数已删除、排序等距抽样内联于 `build()`（该段 docstring「十分位×五分位」与现行实现本已漂移，F-6） | 删除函数后文档漂移 | Step 8 一致性检查 |
| D-10-5 | v392 DESIGN §1.2（L38）非目标加 P-010 勘误指针；v392 RESEARCH §2 的悬空引用（`DESIGN §5.2 L237-243`）加勘误（Step 9 发现 F-9-1） | DESIGN D6 | Step 9 已执行 |
| D-10-6 | 生产 `n_clusters` 若非 39（窗口变化）不阻断，报告实际值 | DESIGN §8 INV-5 | S4 动态取值 |

## 13. Step 6 独立复审记录（2026-11-22）

**复审方式**：双视角异构——视角 A 锚点核查（IMPLEMENTATION 引用的行号/签名/测试计数对仓内现状 Grep/Read 复验，外部锚点抽验前轮抓取证据）；视角 B 可实施性与口径一致性（伪码对真实签名、wild 与点估计口径、回退语义）。

### 13.1 视角 A：锚点核查（8/8 PASS）

| # | 锚点 | 复验结果 |
|---|---|---|
| B1 | report.py `_num` 定义 | ✅ L14-L23（`None`/NaN/Inf → `"n/a"`）——§3.3 `_num(factor, "%.4f")` 可用 |
| B2 | WIRING L494-L507 | ✅ 实核为 `_stratified_sample` 代码块；且该文档版实现（「十分位×五分位」docstring、seed 形参未用）与 panels 现行（排序等距）**本已漂移**（F-6） |
| B3 | 测试计数 | ✅ 实测 `def test_` 计数：test_execution_capacity.py **30**、test_minute_panels.py **40**——§8.4 原文「27 项左右」「既有 42 项」均不准确（F-5） |
| B4 | 既有引用测试 | ✅ `test_same_params_same_result`（L47）、c_triplet 断言用例（L131-L136）、`needs_minutes` 不在 capacity 文件（TP10-5 落 minute_panels 正确） |
| B5 | `_stratified_sample` 删除安全性 | ✅ 不在 `__all__`、无测试导入、唯一调用点 panels L640 |
| B6 | `SqrtImpact` 在 runner 可用 | ✅ L487 lambda 已使用——F-3 修正后无需新增 import |
| B7 | 外部锚点抽验 | ✅ Crossref `10.1162/rest.90.3.414`（REStat 90(3):414-427，cites 4178）与 linearmodels `group_debias_coefficient` 源码公式均有 2026-11-22 抓取证据在案 |
| B8 | `np.argsort(object, kind="stable")` 可行性 | ✅ object 数组 stable sort 走 Python 比较，n=200k 一次 O(n log n) 可接受；`np.unique(object)` 同 |

### 13.2 视角 B：发现与修正（2×P2 + 4×P3，均已落 v1.2）

| # | 级别 | 发现 | 修正 |
|---|---|---|---|
| F-1 | P2 | §2.3 文件结构图把文档勘误对象写成 `spec/p010-granularity-bias/DESIGN.md`（本批设计文档无需改动）且编号挂错 | 图修正为 `docs/EXECUTION_V3.8.1_MINUTE_PANEL_WIRING.md`（D-10-4）+ `spec/v392-calibration-unit-fix/DESIGN.md`（D-10-5），与 §12 表一致 |
| F-2 | P2 | 回退路径 `c_ci_n_clusters=1` 语义误导：iid_fallback 并未聚类，报「1 簇」会让工件读者误读，report 会打印「簇数 1」 | 回退改 `None`（JSON null）；TP10-2 增断言 `c_ci_n_clusters is None` 且 `c_calib_lower_iid == c_calib_lower`；report 簇数仅在 `month_cluster_pairs` 时打印；DESIGN §4.4 该行同步注明 null |
| F-3 | P3 | §4.3 `_wild_sqrt_ci` 对 p 做 `np.minimum(p, 1.0)` 而 `SqrtImpact.fit` 不 clip——样本 p 已被 panels clip ≤1 时幂等，但两处口径表述分歧 | c 改由 `SqrtImpact().fit(...)` 求得（与点估计严格同口径），x 按 fit 同式重建；runner 调用点已有 try/except ValueError 路径 |
| F-4 | P3 | TP10-6 SHA 断言未注明大小写：`hexdigest` 为小写、文档习惯 `82728CE1…` 大写 | 断言写明与跑前基线全等，或 `.upper().startswith("82728CE1")` |
| F-5 | P3 | §8.4 计数模糊且跨批转用（「27 项左右」「既有 42 项」——后者为 P-008 两文件合计历史值） | 落实测值 30 / 40，注明参数化展开数以 pytest collect 为准 |
| F-6 | P3 | WIRING L494-L507 文档版实现与 panels 现行实现本已漂移（docstring 称分层、实现为排序等距），删除函数时若仅替换函数名会保留错误描述 | D-10-4 明确整段改写为「函数已删除、排序等距抽样内联于 `build()`」 |

### 13.3 结论

**PASS_WITH_FIXES（已闭环）**——视角 A 锚点 8/8；视角 B 6 项发现（2×P2 + 4×P3）全部修正。伪码与既有签名逐一对齐（`_bootstrap_ci` 二元组契约不变、`c_triplet` 未动、`_jsonable` 兼容 None）；wild/debias 与点估计口径统一；算法/源码/社区锚点（§2.4/§2.5）经抽验成立。进入 Step 7（CHECKLIST）。

## 14. Step 9 实施记录（TDD 红→绿，2026-11-23）

### 14.1 红态

新增 13 例（TP10-1~5/7/8/9 + C-I5~I8 分块/标签 + C-I10/E6 wild 退化 + C-E4/E5 重抽不足与 wild 告警 + C-E7 sqrt 拟合失败）。首轮定向：

```
8 failed, 1 passed, 30 deselected
```

失败形态：`KeyError: 'c_ci_method'`（5 例）、`c_ci_n_clusters`、`c_ci_debias_upper`、`c_ci_wild_lower`、报告无披露行。TP10-3（可重放）在旧实现天然通过，保留为守卫。

### 14.2 绿态

| 套件 | 结果 |
|---|---|
| `tests/test_execution_capacity.py` | **43 passed**（原 30 → 43） |
| `tests/test_minute_panels.py` | **41 passed**（原 40 → 41，含真实数据用例） |
| `tests/test_fix3_version_unification.py` | **9 passed** |
| 合计 | **93 passed / 0 failed** |

### 14.3 实测读数（V1-V7）

| # | 项 | 实测 | 判定 |
|---|---|---|---|
| V1 | 合成聚类 CI 宽度 | 构造 10 簇强组内相关，聚类/iid ≈ **3.6×** | ✅ >2× |
| V2 | iid 回退逐位 | `c_calib_*` 与 `c_calib_*_iid` 完全相等；确定性测试通过 | ✅ |
| V3 | 默认路径 SHA | `82728ce103d49af211dd12de87d9784040fc909c83fb7a88d521af30a89b2548`（跑前跑后全等） | ✅ INV-1 |
| V4 | 39 月校准 | `c=2.910690`（E1 2.910035，**+0.0225%**）；`n_clusters=39`；聚类 CI `[2.888499, 2.935933]`；iid `[2.895859, 2.922073]`；宽度比 **1.8095（+80.95%）**；`stress=2.935933` | ✅ 容差 0.5% / ≥1.5 |
| V5 | `panel_hash` | `dfcc4e1dea9e4b4f82b73137b75ce8d59620a0d655d265780f8e52a935f85e3f`（与 P-008 基线一致） | ✅ |
| V6 | debias 因子 | 报告 `×1.0131`；区间 `[2.886663, 2.934717]` | ✅ |
| V7 | 报告披露 | md 三行：口径 + 簇数 39 / iid 对照 / group_debias + wild `[2.887234, 2.933494]` | ✅ |

**样本量**：生产 `n=200000`（39×5129=200031 经全局 cap 截断），与 §11 注记预测一致。

**性能**：n=200031、g=39、200 次重抽——iid 1.222 s、聚类 1.016 s；新增 iid 对照 + wild 后 `c` 总增量 ≈ **1.05 s < 3 s**。运行环境 Python 3.13.5 / Windows。

**容量影响**：`c=2.91 > C_RANGE(2.0)` → `c_identifiable=False`（v3.9.2 既有守卫，非本批引入），`c_effective=0.5`，容量读数不变；报告仅 `c_calib_stress` 由 2.9213 升至 2.9359。

### 14.4 Step 9 发现

| # | 级别 | 发现 | 处置 |
|---|---|---|---|
| F-9-1 | P2 | **跨批悬空引用**：v392 RESEARCH §2 引「DESIGN §5.2（L237-243）」在仓内不存在；v392 DESIGN §1.2 L38 实为**非目标**，执行计划 `EXECUTION_V3.8.0` L219 docstring 才写「股票×月」 | 已订正：P-010 RESEARCH v1.3 §3.1 勘误、DESIGN §5.2 优点表述、IMPLEMENTATION D-10-5；v392 DESIGN L38 加 P-010 指针、v392 RESEARCH L50 加勘误标记。教训：Step 8 应抽验**跨批**锚点，不能只查本批四文档 |
| F-9-2 | P3 | 生产宽度比 +80.95% vs E1 +83.84%（−2.9pp） | 主因 `n=200000` vs E1 200031 + 全局 cap 等距重抽；方向一致、远超 1.5 门槛，登记不修 |
| F-9-3 | P3 | 生产 `c` 与 E1 差 +0.0225% | 同上，远小于 0.5% 容差，登记不修 |
| F-9-4 | P3 | `c_identifiable=False`（c>2.0）使 `c_effective=0.5`、容量不随 CI 变化 | 属 v3.9.2 既有守卫，本批不改；已在 CHANGELOG 明确「口径修正非模型变更」 |

---

## 15. Step 10 ADD 审计记录（2026-11-23，独立只读子代理）

**判定**：**PASS_WITH_FIXES（已闭环）**——0×P1 / 1×P2 / 2×P3；质量门初评 **4.65/5 档位 A**（可测试约束 0.75 / 模块映射 1.0 / 接口契约 1.0 / 修正项 1.0 / 跨模块契约 0.9），修复后复评 **4.8/5 档位 A**（可测试约束 0.75→0.90：INV-3 边界已补测；SHA/hash 维持人工实测口径为登记决策）。Iron Law 四类盲区全 PASS。审计复跑 `tests/test_execution_capacity.py` 43 passed。

| # | 级别 | 发现 | 处置 |
|---|---|---|---|
| A-1 | P2 | INV-3 真子集边界无测试：CHECKLIST C-V3 声称的「构造缺月样本」不存在，既有 ⊆ 断言跑在等值场景（fixture 4 码×3 月全有 ADV） | 已补 `test_month_true_subset_when_adv_missing`（minute_panels）：2023-02 行 ADV 置 NaN → `set(month) < set(coverage.months)` 且 build 不报错（`usable` 门控仅看文件数，ADV 缺月整月零样本） |
| A-2 | P3 | TP10-6 / TP10-10 默认 SHA 与 `panel_hash` 断言未落为自动化测试，仅人工实测（V3/V5） | 登记披露：SHA/hash 属 E2E 级验证，人工实测读数见 §14.3（跑前跑后全等 + P-008 基线比对）；不补 E2E 守卫测试 |
| A-3 | P3 | `length_mismatch` 回退 warning 未含具体长度差（DESIGN §7 要求「含长度差」），仅含 reason token | 已修复：runner warning 附实值 `month=N/样本=M`；`test_ci_fallback_without_month[mismatch]` 加强断言 `month=195`/`样本=200`（非恒真） |

**修复后回归**：容量 + 版本定向 **52 passed**（43 + 9）；分钟面板全文件 **42 passed**（41 → 42，含 A-1 新例）。修复注记：A-3 初版 `len(samples.get("month") or ())` 对 numpy object 数组触发歧义真值 `ValueError`（红 1 failed），改显式判空后绿——构成一次小型红→绿。`panel_hash` / 默认 SHA 不受影响（A-3 仅改 fallback warning 文案，生产路径 cluster_reason 为 None 不触发）。

---

**Review 签字**: _________ 日期: _________
