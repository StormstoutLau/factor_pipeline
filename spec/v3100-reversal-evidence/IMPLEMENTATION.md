# 实施文档：截面 T+1 reversal 真实现（P-003，口径 A）

---
id: v3100-reversal-evidence-IMPLEMENTATION
type: design
version: 1.2
status: verified
date: 2026-11-21
depends: [v3100-reversal-evidence-DESIGN, v3100-reversal-evidence-RESEARCH]
upstream: null
---

> **Feature**: P-003「截面 T+1 reversal 真实现」——事件级「交易方向 × 截面价格」已实现反转替代 `temporary_share` 组合 AR(1) 代理。
> **创建日期**: 2026-11-21
> **状态**: v1.2 verified（v1.1 Step 6 复审 PASS_WITH_FIXES；**v1.2 = Step 9 实测回填**：§11 增 E-2/E-3 与实测读数摘要）
> **Spec 步骤**: Step 5-6
> **基于设计**: [DESIGN.md](./DESIGN.md) **v1.2 verified**
> **基于调研**: [RESEARCH.md](./RESEARCH.md) **v1.3 verified**
> **包版本**: 3.9.5（patch）｜**档位**: T1｜**代码基线**: `9b09f8c`

---

## 1. 实施概述

实施分三层推进，**自底向上**：`core/impact.py` 新增纯 numpy 统计量 → 脚本层构造事件样本与日频过滤字段 → 装配层/执行层接线 + 兼容回退。

**改动原则**：

1. **新增优先于修改**：`cross_section_reversal` 为全新函数；`panels` / `runner` 的旧路径用分支保留，原字符串/语义零改动；
2. **数据下沉**：日频过滤字段一次性在 `build_panels` 落 `P['impl_daily']` / `P['open_adj']`，不在装配层做 IO；
3. **先红后绿**：T3100-1~10 先写失败断言（core 函数不存在 / 键缺失），再实现；
4. **不动成本链**：`cost_by_h` / `net` / `rho` / `alpha0` / `core/decay.py` 一行不改。

**实施顺序**（§10 展开）：core 函数 → `limit_down` 镜像 → 日频字段注入 → 事件构造 → panels 装配 → runner 透传 → 版本号 → 测试。

## 2. 工程细节

### 2.1 技术栈

| 组件 | 技术 | 版本 | 验证状态 |
|------|------|------|---------|
| 语言 | Python | 3.9（目标） | ✅ 与批次基线一致 |
| 数值 | numpy / pandas | 现有锁定版本 | ✅ 仓内已用 |
| bootstrap | `backtest.effect_size.stationary_bootstrap_indices` | 现成 | ✅ 实核签名（L128-133） |
| 新增依赖 | **无** | — | ✅ 零新增 |

### 2.2 依赖版本验证

本批**不引入任何新依赖**，故无需 PyPI 查询。复用的唯一外部函数 `stationary_bootstrap_indices(n, n_bootstrap=1000, block_size=None, seed=0)` 为仓内实现（[effect_size.py L128-133](file:///f:/Coding/factor_pipeline/backtest/effect_size.py#L128-L133)），`n_bootstrap ≥ 100` 由默认 1000 满足。

### 2.3 文件结构（改动白名单）

```
backtest/execution/core/impact.py          # + cross_section_reversal + _degraded_reversal
scripts/verify_long_side_research.py       # + limit_down 镜像；返回 dict 增键
scripts/verify_capacity_impact.py          # + open_adj / impl_daily / build_reversal_events
backtest/execution/shell/panels.py         # build_daily_panels：真实现装配 + 回退
backtest/execution/shell/runner.py         # 真/旧分支 + reversal_bps 输出
tests/test_execution_capacity.py           # T3100-1~9（core + runner）
tests/test_minute_panels.py                # T3100-10 + 计数键
config_v2.py / __init__.py / reporting.py  # 版本 3.9.5（3 处）
tests/test_fix3_version_unification.py     # 版本断言
tests/test_backtest/verify_fix3_manual.py  # 版本断言
```

## 3. 模块实施

### 3.1 `core/impact.py::cross_section_reversal`（新增）

**职责**：事件加权反转统计量 + 按月聚类 bootstrap；纯数组入、dict 出，无 IO、无 pandas。

**接口签名**（与 DESIGN §4.1 一致）：

```python
def cross_section_reversal(rt, rt1, side, weight, month,
                           n_bootstrap=1000, seed=20261121):
    ...
```

**实施要点**：

1. 入参全部 `_as_1d` 归一（复用现有私有工具，实存于 [impact.py L34](file:///f:/Coding/factor_pipeline/backtest/execution/core/impact.py#L34)）；
2. 五数组长度不一致或 `n == 0` → 返回退化结构（`degraded=True`），**不抛异常**（DESIGN §4.1 `Raises: 无`；长度不一致已在 panels 层拦截，见 DESIGN §7 F-5）；
3. `x = side * rt`、`y = side * rt1`；仅保留 `isfinite(rt/rt1/weight)` 且 `weight > 0` 的事件；
4. 月度充分统计量用 `np.bincount(month, weights=...)`，`minlength=n_months`；
5. bootstrap 复用 `stationary_bootstrap_indices(n_months, n_bootstrap=n_bootstrap, block_size=1, seed=seed)`；分侧（buy/sell）共用同一组索引（INV-6 扩展）；
6. 端点夹逼 `min(lo, point)` / `max(hi, point)`（与 [impact.py L227](file:///f:/Coding/factor_pipeline/backtest/execution/core/impact.py#L227) 同款）。

**低效操作排除**：

| 潜在低效 | 排除措施 |
|---|---|
| 事件级重采样（`O(B×n_events)`） | 月度聚合后只重采样 39 个 cluster，`O(B×39)` |
| 每次重抽样重算 `x/y` | `x/y` 只算一次，bootstrap 只做加权求和 |
| DataFrame 往返 | 纯 numpy |

### 3.2 `scripts/verify_long_side_research.py::load_implementability`（扩展）

**职责**：新增 `limit_down` 镜像标记，与 `limit_up` 对称。

**实施要点**：

1. 读 `stock_low.pkl`（已实核存在），`reindex` 到 `close` 网格；
2. `is_ld = (raw_ret <= -(thr - 0.3)) & (close <= low * 1.001)`——与 L114 涨停 `raw_ret >= thr - 0.3 & close >= high * 0.999` 严格镜像；
3. 返回 dict 增 `'limit_down': is_ld`；**不改** `limit_up` / `suspend` / `st` / `ind`；
4. 读取失败（文件缺失/列不齐）→ `is_ld = None`，由调用方置 `n_limit_down_unavailable=True`（U-2 退化披露）。

**低效操作排除**：`low` 只读一次、只做一次 `reindex`；不复制 `high` 逻辑。

### 3.3 `scripts/verify_capacity_impact.py::build_panels`（扩展）

**职责**：把日频字段一次性挂到 `P`，供事件构造使用。

**实施要点**：

1. 读 `stock_open.pkl` 并 `reindex(index=close.index, columns=close.columns)`；
2. `P['open_adj'] = open_raw * adj`（与 L89-90 的 `adj_price = close * adj` 同口径）；
3. `P['impl_daily'] = {k: impl[k] for k in ('suspend', 'st', 'limit_up', 'limit_down')}`（`limit_down` 为 `None` 时保留 `None`）；
4. **不塞 `P['facts']`**——`facts` 是形成日快照且参与 `tradable` 选股（L111），塞入日频会污染选股语义（DESIGN D6）；
5. 返回 dict 只增两个键，其余键名/含义不变。

### 3.4 `scripts/verify_capacity_impact.py::build_reversal_events`（新增）

**职责**：构造事件样本 `{rt, rt1, side, weight, month, price_basis}`。

**接口签名**：

```python
def build_reversal_events(P, w, price_basis='adj_close_to_close_cs'):
    """形成日 Δw × 截面收益 → 事件样本；无事件返回 None。"""
```

**实施要点**：

1. `dw = w - w.shift(1).fillna(0.0)`；`side = sign(dw)`；`weight = |dw|`；
2. 收益矩阵：
   - C1：`r = P['adj_price'].pct_change(fill_method=None)`；
   - C2：`r = (P['adj_price'] / P['open_adj'] - 1.0)`（同日复权因子相消，≡ `close/open_raw - 1`；`inf` → `nan`。Step 9 实测勘误 E-3：原写 `P['close'] / P['open_adj']`，会把 `adj` 重复乘一次）；
3. 截面 demean（与 [daily_portfolio_excess L160-162](file:///f:/Coding/factor_pipeline/scripts/verify_capacity_impact.py#L160-L162) 同范式）：`ub = P['mask'].ffill` → `r_tilde = r - r.where(ub).mean(axis=1)`；
4. `t = w.index[i]`、`t+1 = close.index[pos+1]`（`searchsorted` 位置前移，**禁用自然日偏移**）；
5. 过滤按 DESIGN §4.3 九步顺序执行，逐步累计 `counts`；counts 键与九步对应：步骤 1→`n_tiny`、3→`n_first_period`（打标）、4→`n_suspended_t`、5→`n_limit_up_t`/`n_limit_down_t`、6→`n_st`、7→`n_suspended_t1`/`n_missing`、8→`n_limit_t1`、9→`n_extreme`；步骤 2 为断言不计数（Step 6 复审 F-6 补全映射）；
6. 返回 `np.ndarray`（`side` int8、`month` int32），`price_basis` 原样透传；
7. 全部向量化：外层仅循环 39 个形成日，内层整行 numpy。

### 3.5 `shell/panels.py::build_daily_panels`（改造 temporary 装配）

**职责**：真实现/回退两分支。

**实施要点**：

1. 新增私有 `_has_reversal_events(portfolio) -> bool`：五键齐备且等长；
2. 真实现分支：`out['temporary'] = {'rt','rt1','side','weight','month','price_basis'}`（list 化）、`out['temporary_basis'] = 'cross_section_t1'`、warning 改为「截面 T+1 反转，证据层，不进入容量」；
3. 旧代理三元组：`out['temporary_proxy_ar1'] = [point, lo, hi]`（可算时才算）、`out['temporary_proxy_basis'] = 'portfolio_ar1_proxy'`；
4. `out['reversal_counts'] = portfolio.get('reversal_counts') or {}`；
5. 回退分支：**逐字保留** `"temporary_share 为组合日超额 AR(1) 代理，非 T+1 反转，不进入容量"`（Step 9 后位于 L589）；
6. `cost_by_h` 及其后所有逻辑**零改动**。

### 3.6 `shell/runner.py`（真/旧分支 + 输出）

**职责**：选择真实现/回退路径，输出新键。

**实施要点**：

1. `temp = panels.get('temporary') or {}`；
2. 真实现判定 `{'rt','rt1','side','weight','month'} ⊆ temp.keys()`；
3. 真实现：`res = cross_section_reversal(...)`；`ts = list(res['temporary_share'])`；`rev = {**res['reversal_bps'], 'buy': res['buy'], 'sell': res['sell'], 'n': res['n'], 'n_months': res['n_months'], 'price_basis': temp.get('price_basis')}`；
4. 回退：原 `temporary_share(temp['r1'], temp['rev1'])` 路径**逐字保留**；
5. `result` 增 `"reversal_bps": rev`、`"reversal_price_basis": temp.get('price_basis')`（仅真实现；回退时为 `None`）；
6. `ts` / `reversal_bps` 均进 `_jsonable`；**NaN 行为已确认（Step 6 复审 F-5）**：[runner.py L187-188](file:///f:/Coding/factor_pipeline/backtest/execution/shell/runner.py#L187-L188) 对非有限 float 返回 `None`（JSON `null`），退化态三值 NaN 落盘安全；T3100-8 断言函数层 NaN + JSON 层 `null`。

## 4. 接口实施

### 4.1 `cross_section_reversal` 实现骨架

```python
def cross_section_reversal(rt, rt1, side, weight, month,
                           n_bootstrap=1000, seed=20261121):
    a, b = _as_1d(rt), _as_1d(rt1)
    s = np.asarray(side, dtype=float).ravel()
    w = _as_1d(weight)
    m = np.asarray(month, dtype=np.int64).ravel()
    n = a.size
    if not (b.size == s.size == w.size == m.size == n) or n == 0:
        return _degraded_reversal()

    ok = np.isfinite(a) & np.isfinite(b) & np.isfinite(w) & (w > 0.0)
    x, y = s * a, s * b
    n_months = int(m.max()) + 1

    def _agg(mask):
        sel = ok & mask
        return (np.bincount(m[sel], weights=w[sel], minlength=n_months),
                np.bincount(m[sel], weights=w[sel] * x[sel] ** 2, minlength=n_months),
                np.bincount(m[sel], weights=w[sel] * x[sel] * y[sel], minlength=n_months),
                np.bincount(m[sel], weights=w[sel] * y[sel], minlength=n_months))

    S = _agg(np.ones(n, dtype=bool))
    B = _agg(s > 0)
    L = _agg(s < 0)

    def _point(agg):
        sa, sax2, saxy, say = agg
        share = 0.0 if sax2.sum() <= 0 else float(np.clip(-saxy.sum() / sax2.sum(), 0, 1))
        bps = np.nan if sa.sum() <= 0 else float(-(say.sum() / sa.sum()) * 1e4)
        return share, bps

    if n_months < 3 or S[1].sum() <= 0:
        return _degraded_reversal(n=n, n_months=n_months)

    share_pt, bps_pt = _point(S)
    idx = stationary_bootstrap_indices(n_months, n_bootstrap=n_bootstrap,
                                       block_size=1, seed=seed)
    reps = np.array([_point(tuple(v[row].sum() for v in S)) for row in idx])
    ...
    return {
        'temporary_share': [share_pt, lo, hi],          # 端点夹逼后
        'reversal_bps': {'point': bps_pt, 'lo': ..., 'hi': ...},
        'buy':  {'point': ..., 'lo': ..., 'hi': ..., 'n': int},   # 扁平四键
        'sell': {'point': ..., 'lo': ..., 'hi': ..., 'n': int},   # 与 DESIGN §4.1 v1.1 一致
        'n': int, 'n_months': int, 'degraded': False,
    }
```

**签名一致性**：与 DESIGN §4.1 一致 ✅（返回 `temporary_share` 三元组 + `reversal_bps` 三键 + `buy/sell` 扁平四键 + `n/n_months/degraded`）。

### 4.2 `build_reversal_events` 实现骨架

```python
def build_reversal_events(P, w, price_basis='adj_close_to_close_cs'):
    if price_basis == 'adj_intraday_open_close':
        r = (P['adj_price'] / P['open_adj'] - 1.0)   # E-3：复权因子相消
        r = r.replace([np.inf, -np.inf], np.nan)
    else:
        r = P['adj_price'].pct_change(fill_method=None)
    ub = P['mask'].fillna(False).reindex(r.index, method='ffill')
    ub = ub.reindex(columns=r.columns).fillna(False)
    r_t = r - r.where(ub).mean(axis=1)          # 截面 demean（C1/C2 共用）
    pos = P['close'].index.searchsorted(w.index, side='right') - 1
    ...
```

### 4.3 `panels._has_reversal_events`

```python
def _has_reversal_events(portfolio):
    ev = (portfolio or {}).get('reversal') or {}
    keys = ('rt', 'rt1', 'side', 'weight', 'month')
    if not all(k in ev for k in keys):
        return False
    return len({len(ev[k]) for k in keys}) == 1
```

**签名一致性**：与 DESIGN §4.2 判定规则一致 ✅。

## 5. 兼容性

### 5.1 Python 版本兼容

| 版本 | 支持 | 说明 |
|------|------|------|
| 3.9 | ✅ | 目标；无 `match` / `\|` 类型联合 / 海象外新语法 |
| 3.10+ | ✅ | 向后兼容 |

### 5.2 依赖兼容

零新增依赖；仅复用 `numpy` / `pandas` / 仓内 `effect_size`。

### 5.3 向后兼容

| 消费者 | 兼容策略 |
|---|---|
| 最小测试面板（无 `w`/事件） | `_has_reversal_events=False` → 回退旧代理，warning 逐字不变 |
| `temporary_share` 消费方 | 仍为 `[point, lo, hi]`，语义与长度不变 |
| 校准工件读者 | 新增键只增不改；默认路径不含 `reversal_bps` |
| `cost_by_h` / `net` | 不读取新键（INV-3） |

## 6. 错误处理实施

| 错误场景（DESIGN §7） | 处理代码位置 | 测试 |
|---|---|---|
| 事件 < 3 / `Σ a x² = 0` | `cross_section_reversal` 退化分支 | T3100-8 |
| `n_months < 3` | 同上 | T3100-8 |
| 五键长度不一致 | `_has_reversal_events` → 回退 | T3100-10 |
| 长度不一致到达 core | 返回退化（不抛） | T3100-8 变体 |
| `stock_low.pkl` 缺失 | `limit_down=None` → `n_limit_down_unavailable=True` | T3100-5 退化断言 |
| `t+1` 超出末端 | 剔除 + `n_missing` | T3100-4 |
| `temporary` 空 | `ts=None`（今日行为） | 既有用例 |

## 7. 不变式实施

| 不变式（DESIGN §8） | 实施位置 | 验证方式 |
|---|---|---|
| INV-1 默认 SHA 不变 | 不改默认路径 | Step 9 `sha256sum` 三方对比 |
| INV-2 `panel_hash` 不变 | `_panel_hash` payload 未触碰（L424-440） | Step 9 before/after |
| INV-3 成本/容量不变 | `panels` L684-689 与 `runner` net 段零改动 | JSON 子对象逐位对比 |
| INV-4 `core/decay.py` 零改动 | 不进入白名单 | `git diff` + `__all__` 5 项 |
| INV-5 `point ∈ [lo, hi]` | 端点夹逼 | T3100-9 |
| INV-6 两读数共享重抽样 | 同一次 `reversal` 结果派生 | 代码读（单 `idx` 共享）；**独立断言待补（Step 10 审计 P2）** |
| INV-7 事件数组不落盘 | `attach_panel_meta` 白名单未增键 | 工件大小 + 键扫描（静态核验） |
| INV-8 回退 warning 逐字 | L589 字符串冻结 | T3100-10 |
| INV-9 零新增依赖 / 3.9 | 只用现有 import | AST 扫描 + `pip` 无变更 |
| INV-10 固定 seed 可复现 | `seed` 参数透传 | T3100-9 双跑 |

## 8. 测试策略

### 8.1 单元测试（T3100-1~10）

| ID | 用例 | 文件 | 类型 |
|---|---|---|---|
| T3100-1 | 买入 + 次日跌 → `reversal_bps > 0`；次日涨 → `< 0` | test_execution_capacity.py | core |
| T3100-2 | 卖出 + 次日涨 → `> 0`；跌 → `< 0` | 同上 | core |
| T3100-3 | 全体 t+1 收益平移 +c → `reversal_bps` 不变 | 同上 | core（demean 前置） |
| T3100-4 | `suspend_t` / `suspend_t1` 剔除 + 计数 | 同上 | 事件构造 |
| T3100-5 | 涨停买入 / 跌停卖出 / t+1 涨跌停剔除；`limit_down` 缺失退化 | 同上 | 事件构造 |
| T3100-6 | 首期建仓 `first_period` 标记 | 同上 | 事件构造 |
| T3100-7 | 除权日 `adj_price` 连续、无假反转 | 同上 | 事件构造 |
| T3100-8 | `Σ a x² = 0` / `n < 3` → `share=0` + `degraded` | 同上 | core 退化 |
| T3100-9 | 聚类 bootstrap：`point ∈ [lo,hi]`、固定 seed 双跑一致 | 同上 | core |
| T3100-10 | 无事件字段 → 回退旧代理（warning 逐字、`basis=portfolio_ar1_proxy`） | test_minute_panels.py | panels |

**通过线**：`2065 + N passed / 15 skipped / 0 failed`（N 以实际收集数为准，不预设）。

### 8.2 集成测试

- 校准路径（有 `portfolio['reversal']`）：`build_daily_panels` → `runner` 端到端产出 `reversal_bps`；
- 默认路径：现有全量回归必须 0 failed（INV-1/3）。

### 8.3 属性测试（轻量）

- `point ∈ [lo, hi]` 对随机合成事件恒成立（T3100-9 内嵌 20 组随机参数）。

## 9. 幻觉抑制审查（Step 6 Review）

### 9.1 依赖版本验证

- [x] 零新增依赖，无需 PyPI 查询；
- [x] 无虚构库/函数：`stationary_bootstrap_indices` 实核存在（L128-133）；
- [x] 版本兼容：Python 3.9 语法。

### 9.2 接口签名验证

- [x] `cross_section_reversal` 与 DESIGN §4.1 一致；
- [x] `build_reversal_events` / `_has_reversal_events` 为新增/私有，无类型不可能组合；
- [x] `panels` / `runner` 分支保持旧签名。

### 9.3 实施与设计对齐

- [x] 6 个模块 ↔ DESIGN §3.2 六行；
- [x] 4 个接口 ↔ DESIGN §4.1-§4.4；
- [x] 无设计未覆盖的实施（`_degraded_reversal` 为 §4.1 退化分支的内部实现）。

### 9.4 低效操作排除

- [x] 无 `O(n²)`：bootstrap 为 `O(B×n_months)`；
- [x] 无额外 IO：日频字段在 `build_panels` 一次读取；
- [x] 无重复计算：`x/y`、聚合量各算一次。

## 10. 实施步骤

### Step 1：先红（测试先行）

- 文件：`tests/test_execution_capacity.py`、`tests/test_minute_panels.py`
- 内容：写入 T3100-1~10 断言；预期 **10 failed**（`ImportError` / 键缺失）
- 留痕：红阶段 pytest 输出摘要

### Step 2：core 统计量

- 文件：`backtest/execution/core/impact.py`
- 内容：`cross_section_reversal` + `_degraded_reversal`
- 测试：T3100-1/2/3/8/9 转绿

### Step 3：`limit_down` 镜像

- 文件：`scripts/verify_long_side_research.py`
- 内容：读 `stock_low.pkl`，`is_ld` 镜像公式，返回 dict 增键
- 测试：T3100-5（部分）

### Step 4：日频字段注入

- 文件：`scripts/verify_capacity_impact.py::build_panels`
- 内容：`open_adj` / `impl_daily`
- 测试：T3100-4/5/6/7

### Step 5：事件构造

- 文件：`scripts/verify_capacity_impact.py::build_reversal_events` + `build_portfolio_panels` 增 `reversal` / `reversal_counts`
- 测试：T3100-4/5/6/7 全绿

### Step 6：panels 装配

- 文件：`backtest/execution/shell/panels.py`
- 内容：`_has_reversal_events` + 两分支 + `temporary_proxy_ar1` / `reversal_counts`
- 测试：T3100-10

### Step 7：runner 透传

- 文件：`backtest/execution/shell/runner.py`
- 内容：真/旧分支 + `reversal_bps` / `reversal_price_basis`
- 测试：全量回归

### Step 8：版本号

- 文件：`config_v2.py` L371 / `__init__.py` L58 / `reporting.py` L40 → `"3.9.5"`；`tests/test_fix3_version_unification.py` L34 / `tests/test_backtest/verify_fix3_manual.py` L21 → `EXPECTED_VERSION = "3.9.5"`
- 测试：版本用例

### Step 9：实测与不变式核验

- 39 月校准：C1/C2 双口径对照 + 新旧读数对照（替换 RESEARCH §3.5「待 E1」）
- 默认 SHA / `panel_hash` before/after 三方核验
- 全量 `pytest -q` 通过线

### Step 10：文档回填

- 本文件 §11 实测读数；CHECKLIST（Step 7-10）；AUDIT（Step 10）

## 11. 设计勘误登记（Step 5 发现）

| # | 勘误 | 依据 | 处置 |
|---|---|---|---|
| E-1 | DESIGN §10.1 写「版本 4 处 + 2 处测试断言（`config_v2.py` / `__init__.py` / `reporting.py` / 测试断言）」——实际代码落点为 **3 处**（config_v2 L371 / __init__ L58 / reporting L40），测试断言 **2 处**（test_fix3_version_unification.py L34 / test_backtest/verify_fix3_manual.py L21），合计 **5 处** | 主会话 grep `3\.9\.4` 实核（9 处命中中 4 处为注释/历史标记） | 本文件 §2.3 / §10 Step 8 按 5 处执行；**已同步回写 DESIGN v1.2 §10.1 + §12.3** |
| E-2 | 文档称「39 月」，实测证据层覆盖 **73 个形成月 / 72 个有效聚类**（39 为分钟层覆盖，非证据层口径） | `out/v3100_calibration.json` 的 `reversal_counts.n_months=73`、`reversal_bps.n_months=72` | 不改代码；RESEARCH §3.5 / CHECKLIST §2.4 登记口径勘误，读数与旧代理同域可比 |
| E-3 | C2 公式原写 `P['close'] / P['open_adj']`，会把复权因子重复乘一次（`close/open_adj = (close/open)/adj`；`adj` 最高 181 → 中位日内收益 −61%、`n_extreme=36 445`、buy +773.9 bps） | 首轮 C2 校准读数异常；`close/open_raw-1` 分布正常（中位 0、`|r|>0.5` 仅 211） | 改为 `P['adj_price'] / P['open_adj'] - 1.0`（同日复权因子相消，≡ `close/open_raw-1`）；T3100_7 增 ×137 相消回归断言；修正后 C2 读数 point −2.420、`n_extreme=0` |

### 11.1 Step 9 实测摘要（2026-11-21）

- **全量测试**：`pytest -q` → **2076 passed / 15 skipped / 0 failed**（861.28 s；基线 2065 + 新增 11）。
- **C1（主口径）**：`temporary_share=[0, 0, 0.038326]`；`reversal_bps` point **−2.842**、CI `[−14.974, +10.366]`；buy **+11.878**（n=76 420）、sell **−18.637**（n=175 258）；n=251 678、n_months=72。
- **C2（稳健性）**：`temporary_share=[0.044918, 0.013728, 0.075428]`；point **−2.420**、CI `[−11.810, +5.938]`；buy **+10.344**（n=76 452）、sell **−16.115**（n=175 292）；n=251 744、n_months=72。与 C1 相对差 14.8% / 12.9% / 13.5%（U-1 自动通过）。
- **不变式**：默认工件 SHA `82728CE1…` 逐位不变；`panel_hash=dfcc4e1d…` 三方一致；`panels/capacity/decay/models/impact_curve/impact_samples/config_hash` 与 v3.9.4 基线全部相等；C1 双跑 JSON 逐键相等。
- **性能**：39 月校准 **16 min 06 s**（基线 ≈14.5 min，+11%，≤20%）；日频矩阵增量 **96.0 MB**（<100 MB）；bootstrap 2.4 ms/次。
- **敏感性**：U-3 share 端点极差 lo 0.000000 / hi 0.005508（≤0.01 通过）；U-5 外部基准（全市场 vs 可投资域）相对差 **0.2%**（≤10% 通过）；**事件样本等权为自指基准**，相对差 33.3%（见 CHECKLIST §11 偏差登记）。

## 12. Step 6 复审记录（v1.1 增补，2026-11-21）

> **复审方式**：独立上下文只读子代理（GLM-5.3 基座）通读本文件与 DESIGN v1.2，重放代码锚点；主会话对每项发现逐条实证核实后裁决。
> **独立性声明（RULE-4/5）**：撰写者（本文件 v1.0，DeepSeek 基座）与复审者（GLM-5.3 基座）**不同基座**，构成**真异构复审**。
> **改判说明**：复审子代理原始结论为 **FAIL**；主会话核实后认定其中 3 项属**步骤错位/误报**（将「实施蓝图」当「已实施代码」评审，与 RESEARCH 复审 F-1 同类），按项目纪律（v3.9.3/v3.9.4 先例）改判 **PASS_WITH_FIXES**，全部处置留痕如下。

**最终结论**：**PASS_WITH_FIXES**（复审 6 项发现：3 项误报/步骤错位驳回 + 3 项采纳修正；无 P1）。

**门禁改判**：

- **(a) 对齐：过** —— 六模块↔DESIGN §3.2、四接口↔§4.1-§4.4、不变式 10/10、实施序↔白名单 8 文件 + 版本 5 处（E-1 勘误后口径）全部对齐；「九步过滤未逐项」经 F-6 处置后闭合；
- **(b) 代码现实：过** —— `_as_1d` 实存（impact.py L34）、`stationary_bootstrap_indices` 签名兼容（effect_size.py L128-133）、warning 逐字文案实核（panels.py L557-558）、`_jsonable` NaN→None 实核（runner.py L187-188）；复审所称「runner 未接入 reversal_bps / build_portfolio_panels 无 reversal 数组」为**预期现状**（Step 5 产出蓝图而非代码，实施序 Step 5-7 才落码）；
- **(c) 可执行：过** —— 「直接按蓝图跑测试会 fail」正是先红后绿的**设计意图**（§10 Step 1：预期 10 failed）；测试落位与现有文件结构匹配（test_execution_capacity.py 承载 core/事件用例、test_minute_panels.py 承载 panels 用例，与 v3.9.4 分工一致）；
- **(d) 幻觉抑制：过** —— 两项「待核」声称（`_as_1d` 复用、`_jsonable` NaN）已由主会话实证关闭并补锚点。

**发现与处置**：

| # | 复审级别 | 发现 | 主会话裁决 | 处置 |
|---|---|---|---|---|
| R-1 | P2 | §4.1 骨架 `return {...}` 未完整展示，buy/sell 结构需与 DESIGN §4.1 核对 | **部分采纳**（骨架简写对蓝图可接受，但补全可消除歧义） | §4.1 return 补全：`buy/sell` 扁平四键 `{'point','lo','hi','n'}` + `degraded` 键，与 DESIGN §4.1 v1.1 显式一致 |
| R-2 | P2 | 旧 warning 文案与真实现文案混淆 | **误报驳回**：§3.5 要点 2（真实现新文案「截面 T+1 反转，证据层，不进入容量」）与要点 5（回退分支逐字保留旧文案）**已明确区分两分支**；复审者未区分 | 不改；本行即为留痕 |
| R-3 | P2 | runner 仍走旧 `temporary_share` 路径、未输出 `reversal_bps` | **步骤错位驳回**：Step 5 产出实施蓝图，代码现状本应走旧路径；蓝图 §3.6/§10 Step 7 已规划接线 | 不改；同上 |
| R-4 | P3 | `_as_1d` 复用声称未实核 | **误报驳回**：主会话实核 `def _as_1d(values)` 实存于 impact.py L34（复审者仅见文件片段未及私有工具区） | §3.1 要点 1 补锚点 L34 |
| R-5 | P3 | `_jsonable`/NaN 处理未确认（文档自述「需确认」） | **采纳**（本文件诚实登记的待核项，复审正确指出） | 主会话实核 runner.py L187-188：非有限 float → `None`（JSON null）；§3.6 要点 6 改为已确认 + 锚点 + T3100-8 断言口径（函数层 NaN + JSON 层 null） |
| R-6 | P3 | 九步过滤与 counts 键未逐项映射 | **部分采纳**（引用 DESIGN §4.3 可避免重复，但映射表有助于实施） | §3.4 要点 5 补九步↔counts 键映射（步骤 2 断言不计数） |

**锚点重放**：`_as_1d`（impact.py L34）一致；`temporary_share` 现实现（L193-227）一致；`stationary_bootstrap_indices` 签名（effect_size.py L128-133）一致；旧 warning 逐字文案（panels.py L557-558）一致；`cost_by_h`（L647-652）与 `_panel_hash` payload（L424-440）未触碰一致；`daily_portfolio_excess` demean 范式（verify_capacity_impact.py L153-163）一致；涨停公式（verify_long_side_research.py L114）一致；版本 5 处落点（config_v2 L371 / __init__ L58 / reporting L40 / 两测试文件）一致；`_jsonable` NaN→None（runner.py L187-188）一致。

**v1.1 结论**：复审改判通过（PASS_WITH_FIXES，6 项全部裁决闭合），允许进入 **Step 7（实施执行：按 §10 十步序落码 + 先红后绿）**。Step 7 必须遵守：§2.3 白名单、INV-1~INV-10、§3.5 回退分支逐字文案、§10 Step 1 红阶段留痕。

---

**Review 签字**: _________ 日期: _________
