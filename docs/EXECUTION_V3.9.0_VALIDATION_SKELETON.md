# EXECUTION — v3.9.0 模拟数据验证骨架与步骤级追溯

> **日期**: 2026-11-19
> **版本**: v1.5（v1.0 = 步骤 5 初稿；v1.1 = 步骤 6 幻觉消除 review 修复：1 CRITICAL / 4 MAJOR / 10 MINOR 全修，见 §9；v1.2 = 步骤 8 对齐：上游版本引用 + 风险 3 措辞 + 一致性 review 登记；v1.3 = 步骤 8 残留核实回填：规则表日期全部核实 + 过户费费率时点；v1.4 = 步骤 9 回填：§0.2 工件状态 / §5.2 红→绿 / §6.1 性能实测 / §6.2 B2 判据勘误；v1.5 = 步骤 10 异构审计登记：H1/H2/H3 修复 + T390-39~41 回归 3 例 + §0.2/§5.2 计数同步 37→40 例）
> **对应设计**: [DESIGN_SYNTHETIC_VALIDATION_TRACEABILITY.md](private/DESIGN_SYNTHETIC_VALIDATION_TRACEABILITY.md) v1.3（§18 review PASS + §17 步骤 6/8 勘误与残留核实）
> **对应调研**: [RESEARCH_SYNTHETIC_VALIDATION_TRACEABILITY.md](research/RESEARCH_SYNTHETIC_VALIDATION_TRACEABILITY.md) v1.3（§19 review PASS + §18 U3/U4/U5/U9-U12 已核实）
> **默认路径纪律**: 全部新增能力默认关闭或仅存在于 `tests/`；`python scripts/verify_capacity_impact.py`（无参数）SHA256 保持 `82728CE1…`
> **依赖纪律**: 零新增依赖（`numpy` / `pytest` / 标准库；pandas 为既有核心依赖）
> **基线**: tests=2001 / 1986 passed / 15 skipped（v3.8.0 审计终态）
> **目标**: tests=2041 / **2026 passed** / 15 skipped / 0 failed（步骤 10 复跑 757.4 s，junit `g4_junit_v390_rerun.xml`；步骤 9 基线 2038 / 2023 passed / 782.9 s）

---

## §0 摘要、交付与工件状态

### 0.1 交付内容

| 编号 | 交付 | 形态 | 设计对应 |
|------|------|------|---------|
| E0 | B2 修复：`_build_positions` 有效域收窄 | `backtest/engine.py` 4 行变更（1 新增 + 1 替换 + 2 改名）+ 临时红测试 | 设计 §9 |
| E1 | 合成场景库 | `tests/synthetic/{__init__,panel,scenarios}.py` + `tests/test_synthetic_panel.py` | 设计 §4 |
| E2 | 不变量注册与常驻 | `tests/invariants/`（8 个文件，12 条不变量 + 2 自检） | 设计 §5 |
| E3 | 步骤级追溯 | `backtest/trace.py` + `tests/test_trace.py` | 设计 §6 |
| E4 | 交易现实性层 | `backtest/tradability.py` + `tests/test_tradability.py`（独立函数供调用方，本批不改引擎；见 §8.3 P-1） | 设计 §7 |
| E5 | 验证聚合 | `scripts/verify_all.py` + 4 脚本 `--report-json` + `tests/test_verify_all.py` | 设计 §8 |

### 0.2 工件状态

| 工件 | 状态 |
|------|------|
| 调研文档 | v1.3（步骤 2 两轮 + §19 review PASS + 步骤 8 对齐与残留核实） |
| 设计文档 | v1.3（步骤 4 幻觉消除 review + 步骤 6/8 勘误与残留核实，见其 §17/§18） |
| 实施文档 | v1.5（步骤 5 产出 + 步骤 6 review 修复 + 步骤 8 对齐与残留核实 + 步骤 9 回填 + 步骤 10 审计登记） |
| Checklist | v1.4（步骤 7 产出 + 步骤 8 对齐与残留核实 + 步骤 9 回填 + 步骤 10 审计复核：[CHECKLIST_V3.9.0_VALIDATION_SKELETON.md](audit/CHECKLIST_V3.9.0_VALIDATION_SKELETON.md)，108 项） |
| 一致性 review | v1.1（步骤 8：[CONSISTENCY_REVIEW_V3.9.0_VALIDATION_SKELETON.md](audit/CONSISTENCY_REVIEW_V3.9.0_VALIDATION_SKELETON.md)，PASS_WITH_FIXES 1 MAJOR / 6 MINOR 全修 + 残留核实 5/5） |
| 代码 | 已完成（2026-11-19：E0-E5 全部落地，40 例新增测试全绿（37 例 TDD + 步骤 10 审计回归 3 例）；G1-G8 全部通过，全量读数见 §0.2 目标行与 CHECKLIST §6） |

### 0.3 D1-D6 实施落点

| 决策 | 内容（设计 §0） | 落点 |
|------|----------------|------|
| D1 | 合成库放 `tests/synthetic/`，生产包零新增 | §2.2/§2.3；生产侧仅 `trace.py`/`tradability.py` |
| D2 | 不引入 PBT 库，自实现确定性生成 + 手写不变量 | §2.2（seed 唯一随机源）、§2.4（INVARIANTS） |
| D3 | trace 轻量 JSONL + sha256，默认关闭 | §2.6（`enabled=False` 零 IO） |
| D4 | tradability 默认 None + 规则表版本化 | §2.7（`DEFAULT_LIMIT_RULES`）、§2.7.4（接入点） |
| D5 | B2 仅收窄 argsort 有效域 | §2.1（4 行变更：1 新增 + 1 替换 + 2 改名） |
| D6 | 聚合只读，`--report-json` 默认关闭 | §2.8/§2.9 |

### 0.4 版本升级裁决

**升 3.9.0**。理由：新增 2 个生产模块（`trace.py` / `tradability.py`）+ 1 处行为变更（B2 修复影响 turnover）+ 40 例新增测试（37 例 TDD + 步骤 10 审计回归 3 例）。
6 处版本锚点同步（§3.1），与 v3.8.0 先例一致。

---

## §1 任务分解与依赖

```
E0 (S1) B2 修复 ────────────────────────────── 独立
E1 (S2) 合成场景库 ──┬──→ E2 (S3) 不变量常驻
                      └──→ E4 (S5) 交易现实性
E3 (S4) 追溯 ─────────────────────────────── 独立
E5 (S6) 聚合 ─────────────────────────────── 独立（只读）
```

| E | 一句话目标 | 依赖 | 可回滚方式 |
|---|-----------|------|-----------|
| E0 | NaN 股票不再获得仓位 | — | 还原 `engine.py` 4 行 |
| E1 | 6 场景一键构造 A 股结构面板 + ground truth | — | 删 `tests/synthetic/` |
| E2 | 12 条不变量常驻回归（含 E0 的 I1） | E1 | 删 `tests/invariants/` |
| E3 | 每步 input/output/params hash 落 JSONL，可定位首个分歧 | — | 删 `backtest/trace.py` |
| E4 | 涨停禁买/跌停禁卖/停牌冻结/T+1/成本分项，默认关闭 | E1（场景） | 删 `tradability.py` |
| E5 | 4 脚本产统一 JSON，聚合器出 summary | — | 删 `verify_all.py` + 去掉新参数 |

---

## §2 接口签名与回退点

### 2.1 `backtest/engine.py`（E0）

**改动位置**：`_build_positions` 内（现状 :171-201）。

```python
# 现状（行号对照 3.8.0+H2fix）
f = factor[t]                                              # :171
valid = ~np.isnan(f)                                       # :172
...
n_valid = valid.sum()                                      # :173
...
if isinstance(top_n, float) and 0 < top_n <= 0.5:          # :187
    n_select = max(1, int(n_valid * top_n))
elif isinstance(top_n, int) and top_n > 0:                 # :189
    n_select = min(top_n, n_valid // 2)
else:
    n_select = max(1, int(n_valid * 0.2))                  # :192
if n_select < 1 or n_valid < n_select * 2:                 # :194
    continue
sorted_idx = np.argsort(f)                                 # :197  ← 替换
```

**变更（新增 1 行 + 替换 1 行 + 2 处改名）**：

```python
valid_idx = np.flatnonzero(valid)                          # 新增（紧随 :172 之后）
...
sorted_local = valid_idx[np.argsort(f[valid_idx])]          # 替换 :197
positions[t, sorted_local[:n_select]] = -1.0 / n_select     # 原 :199 改名
positions[t, sorted_local[-n_select:]] = 1.0 / n_select     # 原 :201 改名
```

**边界**：
- `valid_idx.size == 0` → 由既有 `n_valid < n_select*2` 守卫拦截（`n_valid=0` 必 `continue`）；
- `n_select` 计算保持原样（含 `int` / `float` 两分支与 `max(1, ...)`）；
- 域定义保持 `~np.isnan`（**不**改 `isfinite`）；
- `positions` 形状与 dtype（float64）不变。

**回退**：还原上述 4 行。

### 2.2 `tests/synthetic/panel.py`（E1）

```python
# -*- coding: utf-8 -*-
"""v3.9.0 合成面板生成器（测试侧，零生产依赖）。"""
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

__all__ = ["PanelSpec", "SyntheticPanel", "build_panel"]

ROUND2 = ...
BOARD_NAMES = ("main", "star", "gem", "bse")


@dataclass(frozen=True)
class PanelSpec(object):
    n_dates: int = 120
    n_stocks: int = 60
    start: str = "2022-01-04"
    seed: int = 20261119
    board_mix: Tuple[Tuple[str, float], ...] = (
        ("main", 0.60), ("star", 0.20), ("gem", 0.15), ("bse", 0.05))
    limit_up_ratio: float = 0.0
    limit_down_ratio: float = 0.0
    suspend_ratio: float = 0.0
    suspend_len: int = 5
    st_ratio: float = 0.0
    factor_missing: float = 0.0
    loaded_lag_days: int = 0
    adj_jump_days: Tuple[int, ...] = ()


@dataclass(frozen=True)
class SyntheticPanel(object):
    spec: PanelSpec
    dates: np.ndarray          # (T,) datetime64[D]
    codes: np.ndarray          # (N,) int64
    board: np.ndarray          # (N,) '<U4'
    is_st: np.ndarray          # (N,) bool
    open: np.ndarray           # (T, N) float64
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    amount: np.ndarray
    factor: np.ndarray
    loaded_at: np.ndarray      # (T, N) datetime64[D]
    industry: np.ndarray       # (N,) '<U8'
    mktcap: np.ndarray
    true_limit_hit: np.ndarray   # (T, N) int8
    true_suspend: np.ndarray     # (T, N) bool


def build_panel(spec: PanelSpec) -> SyntheticPanel:
    """按 design §4.2 九步生成；同 spec 两次调用逐位一致。"""
```

**实现要点**（逐条对应设计 §4.2）：

| 步 | 实现 | 校验 |
|----|------|------|
| 0 | `_validate(spec)`：`n_dates>=2`、`n_stocks>=4`、`board_mix` 和 ∈[0.99,1.01]、`limit_up+limit_down<=0.5`、`suspend_len<n_dates` | 违规 `ValueError`（消息含字段名） |
| 1 | `rng = np.random.default_rng(spec.seed)`；**全程只用此 rng** | grep 禁用 `np.random.` 全局函数 |
| 2 | `board_mix` → `int(round(ratio*N))`，余数补 main；`is_st` 在 main 内抽 `st_ratio` | `len(board)==N`、`board` 取值 ∈ BOARD_NAMES |
| 3 | `close[0]=rng.lognormal(0,0.3,N)`；`sigma_i~U(0.008,0.03)`，`r=rng.normal(0,sigma_i)`；普通日 `u,d=\|rng.normal(0,0.005)\|+max(0.002, 0.0155/close)`（**价格地板**，§9 C-1：保证 round2 后 `high-low>=0.02`）；`high=round2(close*(1+u))`、`low=round2(close*(1-d))`、`open=clip(round2(close*(1+rng.normal(0,0.003))), low, high)` | 普通日 round2 后 `high-low>=0.02`（逐元素，违规 `ValueError`） |
| 4 | 按 `limit_up_ratio`/`limit_down_ratio` 抽 (t,i)；`pct` 取模块内置 `_RULE_PCT` 数值副本（按 `board/is_st/date` 查表，与设计 §7.2 规则表数值一致；`tests/synthetic` 禁止 import `backtest.*`，副本漂移由 T390-04/T6 交叉验证捕获）；`px=round2(prev*(1±pct))`，`o=h=l=c=px`，`v=rng.uniform(1e5,1e6)`；`true_limit_hit=±1` | `limit_price(prev)==high` 逐位（E4 T6） |
| 5 | 按 `suspend_ratio` 抽起始日，连续 `suspend_len` 日 `o=h=l=c=prev`、`v=0`、`true_suspend=True` | 停牌段内每日均满足 |
| 6 | `adj_jump_days` 当日 `close*=0.5`，其余价格列同比缩放 | 跳变日收益 ≈ -50% |
| 7 | `fwd5[t,i]=(close[t+5]/close[t]-1)`；横截面 z-score（`nanmean/nanstd`）后 `+ rng.normal(0,0.5)`；按 `factor_missing` 置 NaN；停牌日必 NaN | 缺失率与 spec 差 < 1% |
| 8 | `loaded_at[t] = dates[t] + loaded_lag_days`（`np.timedelta64(L,'D')`） | `loaded_at >= dates` 全成立 |
| 9 | `industry` 抽 6 类；`mktcap = close * rng.lognormal(20,1,N)` | 形状一致 |

**性能**：120×60 全向量化（仅第 4/5 步按抽中的 (t,i) 循环，数量 ≤ 0.16×T×N），目标 < 50 ms。

**依赖**：仅 numpy + stdlib。**禁止** import `backtest.*`（避免测试侧反向依赖生产）。

### 2.3 `tests/synthetic/scenarios.py`（E1）

```python
SCENARIOS = {
    "clean": PanelSpec(),
    "limit_heavy": PanelSpec(limit_up_ratio=0.08, limit_down_ratio=0.08),
    "suspend_gap": PanelSpec(suspend_ratio=0.10, suspend_len=5),
    "st_mixed": PanelSpec(st_ratio=0.10),
    "stale_factor": PanelSpec(loaded_lag_days=5, factor_missing=0.05),
    "adj_jump": PanelSpec(adj_jump_days=(40, 41)),
}
```

`__init__.py` 导出 `PanelSpec / SyntheticPanel / build_panel / SCENARIOS`。

**注**：`st_mixed` 供 E4 T5 使用 `dataclasses.replace(SCENARIOS["st_mixed"], start="2026-06-01")` 覆盖新规前后。

### 2.4 `tests/invariants/registry.py`（E2）

```python
@dataclass(frozen=True)
class Invariant(object):
    name: str
    module: str
    kind: str          # bound | monotonic | invariant | equivalence
    scenario: str
    check: Callable[[SyntheticPanel], Tuple[bool, str]]


INVARIANTS = []        # type: List[Invariant]


def register(inv):
    """重名 ValueError；kind 越界 ValueError。返回 inv 便于串联。"""


def run_all(panel_factory=None):
    """按 scenario 缓存面板，逐条执行，返回 [(name, ok, detail)]。"""
```

**注册表自检 2 例**（`test_registry.py`）：
- `test_registry_rejects_duplicate`：同 name 二次注册 → `ValueError`；
- `test_registry_unique_and_nonempty`：`len(INVARIANTS) == 12`、name 唯一、scenario ∈ SCENARIOS。

**12 条实现要点**（每条独立文件，`register(Invariant(...))` 于模块导入时执行）：

| # | 实现要点 | 失败消息 |
|---|---------|---------|
| I1 | `eng=FactorBacktestEngine.__new__(...)`、`eng.config={'ls_method':'top_n','top_n':0.2}`；`f[:, :5]=np.nan`；`bad=np.argwhere(np.isnan(f)&(pos!=0))` | `first_bad=(t,i) expected=0 actual=<w>` |
| I2 | 基线 `fwd=eng.compute_fwd_returns()`；复制 `close` 改 `[t+1:]=close[t]*1.5` 后重算；比较 `fwd[:t]` 逐位 | `first_diff_t=<t>` |
| I3 | `tr=compute_turnover(eng._build_positions(panel.factor))`；`-1e-12 <= min`、`max <= 2+1e-9` | `min/max` 实际值 |
| I4 | `r2=r.copy(); r2[np.isnan(f)]=100.0`；`compute_long_short_returns` 两次比较 `array_equal(equal_nan=True)` | `first_diff_t` |
| I5 | `rank_ic=compute_ic_series(...)`；`nanmin>=-1-1e-9`、`nanmax<=1+1e-9` | 实际极值 |
| I6 | `DataBridge.__new__(DataBridge)._apply_loaded_at_lag(f_df, loaded_df, use_loaded_at=True, fill_missing='nan')`（真实签名 `data_bridge.py:203`，输入 stocks×dates DataFrame）；对每个 (stock, date)：`loaded_at > trade_date` 的位置必须 NaN | `first_bad=(stock,date)` |
| I7 | 同函数（I6）：无缺失输入下 `fill_missing='nan'` 与 `'ffill'` 结果 `array_equal(equal_nan=True)` | 首个不等位置 |
| I8 | `detect_limit_lock(...) == ((true_limit_hit!=0) \| true_suspend)`；同时断言 `true_suspend` 段确实命中（防空断言） | 首个不等 (t,i) |
| I9 | `SqrtImpact().predict(p_grid, σ, params)` 对 `p` 与 `σ` 分别 `np.diff>=0` | 首个下降点 |
| I10 | `half_life(rho)` vs `ln(0.5)/ln(rho)`，`np.isclose(rtol=1e-12)` | 两者数值 |
| I11 | `b=auto_block_size(x)`，`len(x)>=30`（n<3 时实现返回 1 而 `n//3=0`，界断言失效，见 `bootstrap.py:24-37`）；`1<=b<=len(x)//3`，且 `b` 为 int | 实际 b |
| I12 | `EnhancedRankPreservingScaler`（或 `modules/factor_adaptive_winsor` 入口）前 t 期在扰动未来后逐位一致 | 首个不等位置 |

**约束**：每条 `check` 内不得修改 `panel`（只读）；总耗时 < 5 s（同 scenario 面板由 `run_all` 缓存）。

### 2.5 `tests/invariants/` 文件布局（E2）

| 文件 | 内容 |
|------|------|
| `__init__.py` | `from .registry import INVARIANTS, Invariant, register` |
| `registry.py` | 数据结构 + register + run_all |
| `backtest_engine.py` | I1 / I2 / I3 |
| `factor_metrics.py` | I4 / I5 |
| `data_bridge.py` | I6 / I7 |
| `execution_core.py` | I8 / I9 / I10 / I11 |
| `winsor.py` | I12 |
| `test_registry.py` | 12 条参数化 + 2 条自检 |

**导入顺序陷阱**：`test_registry.py` 必须 `import tests.invariants.backtest_engine` 等模块以触发注册；
在 `tests/invariants/__init__.py` 末尾集中 import 五个模块（副作用注册），避免 pytest 收集顺序依赖。

### 2.6 `backtest/trace.py`（E3）

```python
# -*- coding: utf-8 -*-
"""v3.9.0 步骤级追溯（默认关闭，零 IO）。"""
__all__ = ["PipelineTrace", "content_hash", "find_first_divergence"]


class PipelineTrace(object):
    def __init__(self, path=None, enabled=False, code_version=None):
        """enabled=False 时全部方法为 no-op；path 为 None 且 enabled=True → ValueError。"""

    @property
    def run_id(self): ...

    def step(self, name, **params):
        """返回 TraceStep 上下文管理器（enabled=False 返回 _NullStep）。"""

    def close(self): ...


def content_hash(obj):
    """ndarray → b'nd:'+shape+dtype+bytes；DataFrame → b'df:'+_content_digest；
    Mapping → canonical json；Sequence → 逐项拼接；标量 → repr 规范化。
    返回 'sha256:' + hexdigest。"""


def find_first_divergence(trace_a, trace_b):
    """返回 {'seq','step','field','a','b'} 或 None。"""
```

**TraceStep 语义**：

| 钩子 | 行为 |
|------|------|
| `__enter__` | 记 `started_at`；返回 self |
| `add_input(name, obj, rows=None, cols=None)` | 计算并缓存 hash（enabled=False 不计算） |
| `add_output(name, obj, rows=None, cols=None)` | 同上 |
| `__exit__(exc)` | 写一行 JSONL（`status=ok/error` + `error`）；异常不吞（原样抛出） |

**content_hash 规范**：
- ndarray：`np.ascontiguousarray(np.asarray(obj, dtype=np.float64))`（非数值 dtype 保留原 dtype 字节）；
- NaN：`np.isnan` 掩码单独写入（避免 NaN bit 模式差异）；
- DataFrame：延迟 `import pandas`（仅在分支内），调用 `backtest.data_contract._content_digest`（只读调用，不改该文件），**并追加三项全局统计**（列 sum/mean/NaN 计数的 canonical json 一并入哈希；采纳设计 Q1 裁决——`_content_digest` 仅抽样首 8/中 ≤8/尾 8 行，中段篡改可漏检，T390-24 的篡改落在抽样行之外时也必须可定位）；
- 不可处理对象 → `TypeError("content_hash 不支持: %r" % type(obj))`；
- 空数组/空表 → 正常返回（不返回 None）。

**find_first_divergence 对齐规则**：
1. 两文件按 `seq` 升序读入；
2. 逐 `seq` 比较 `(step, params_hash, inputs[i].hash, outputs[i].hash)`；
3. 首个不等 → 返回该事件对；
4. 长度不等 → 返回短侧末尾之后的下一条（`field="length"`）。

**关闭语义验收**：`enabled=False` 时 `step()` 返回 `_NullStep`，其 `add_*` 为 `pass`，`__exit__` 不创建目录/文件。

### 2.7 `backtest/tradability.py`（E4）

```python
__all__ = ["LimitRule", "DEFAULT_LIMIT_RULES", "rule_pct", "limit_price",
           "TradabilityPolicy", "can_trade", "apply_tradability", "CostModel"]
```

#### 2.7.1 规则表与查表

```python
@dataclass(frozen=True)
class LimitRule(object):
    board: str
    is_st: bool
    pct: float
    effective_from: str
    effective_to: Optional[str] = None


DEFAULT_LIMIT_RULES = (...)   # 设计 §7.2 的 11 条（含 gem ST 前段）


def rule_pct(board, is_st, date):
    """返回 float pct；无命中/多命中 → ValueError（含 board/is_st/date）。"""
```

**边界**：`date` 接受 `str` 或 `np.datetime64`；统一转 `YYYY-MM-DD` 字符串比较（字典序即日期序）。
规则表重叠检测：实现内对 `(board, is_st)` 分组按 `effective_from` 排序，检查相邻区间 `to >= next.from` → `ValueError`（模块导入时执行一次）。

#### 2.7.2 限价与可成交性

```python
def limit_price(prev_close, pct, side="up"):
    """round(prev*(1±pct), 2)；side ∈ {up, down}，其他 → ValueError。"""


def can_trade(prev_close, high, low, volume, suspended, pct, policy):
    """返回 (can_buy, can_sell) 两个 (T,N) bool。
    can_buy  = ~suspended & ~(high >= up-eps)
    can_sell = ~suspended & ~(low <= down+eps)
    # T+1 不在本函数内判定（can_trade 无状态输入；设计 §7.4 第 5 步），
    # 由 apply_tradability 以 locked_until 状态并入
    """
```

**eps**：`1e-8`，模块常量 `_EPS`。**价格取整**：`np.round(prev*(1±pct), 2)`（design §7.3）。

#### 2.7.3 权重推进

```python
def apply_tradability(target_w, prev_close, high, low, close, open_, volume,
                      suspended, board, is_st, dates, policy):
    """返回 (effective_w, report)；report 六键均为 int。"""
```

实现顺序（严格按设计 §7.4 的 7 步 + pending 语义）：

```
pending = np.zeros(N)
locked_until = np.full(N, -1, dtype=int)
w_prev = np.zeros(N)
for t in range(T):
    target = target_w[t]
    can_buy, can_sell = can_trade(...)          # can_sell 需并 locked_until<=t
    # 1) 先补 pending（方向仍一致时）
    fill = np.where(pending > 0, np.minimum(pending, ...), 0)   # 逐股处理
    # 2) 再处理当日 delta = target - w_prev
    # 3) 被拦截 → w_eff = w_prev，pending += delta，计数
    # 4) 成交 → w_eff = w_prev + executed；buy 记 locked_until = t+1
    effective[t] = w_eff
    w_prev = w_eff
```

**计数口径**（事件级）：
- `blocked_buy` / `blocked_sell`：被拦截的 (t, i) 次数；
- `blocked_suspend`：停牌且存在目标变动的 (t, i) 次数；
- `t1_locked`：因 T+1 被拒绝的卖出 (t, i) 次数；
- `deferred`：pending 实际补成交的 (t, i) 次数；
- `carried`：期末 `|effective[-1] - target_w[-1]| > 1e-12` 的股票数。

**边界**：
- `policy.execute_at` 仅 `next_open` / `same_close`（后者仅测试对照）；
- `board` 含未知值 → `ValueError`；
- `is_st` 与 `board` 形状须为 `(N,)`，否则 `ValueError`；
- `suspended` 与 OHLC 形状一致，否则 `ValueError`。

#### 2.7.4 引擎接入点（v1.1 可选项，本批不实施）

`backtest/engine.py` 的可选接入示意（**本批不实施**，见 §8.3 P-1 裁决；默认 `None` 时不进入）：

```python
# _evaluate_factor 内，positions 生成后
policy = self.config.get("tradability_policy")
if policy is not None:
    eff, report = apply_tradability(positions, ...)   # 需 panel 数组，从 dl 取
    positions = eff
    result["tradability"] = report
```

> 实施说明：由于 `_evaluate_factor` 目前只持有 `self._close`，v1 的接入范围限定为
> **独立函数供调用方使用**（设计 Q3 裁决），引擎内接入作为 v1.1 可选项；
> 本批仅保证 `TradabilityPolicy` 可独立调用 + 9 例覆盖，**不改 `_evaluate_factor`**。
> 这与设计 §7.6 的「非 None → 生成 evaluate_w」存在偏差，已在 §8.3 P-1 登记（步骤 6 裁决：维持，合规）。

#### 2.7.5 成本模型

```python
@dataclass(frozen=True)
class CostModel(object):
    commission_bps: float = 2.5
    min_commission: float = 5.0
    stamp_tax_bps: float = 5.0
    transfer_fee_bps: float = 0.1
    slippage_bps: float = 0.0

    def cost(self, buy_notional, sell_notional):
        """返回 dict：commission/stamp_tax/transfer_fee/slippage/total。"""
```

计算口径：`commission = max(min_commission, buy*rate) + max(min_commission, sell*rate)`；
`stamp_tax = sell * stamp_tax_bps/1e4`；`transfer_fee = (buy+sell) * transfer_fee_bps/1e4`；
`slippage = (buy+sell) * slippage_bps/1e4`。负数/NaN notional → `ValueError`。
**费率时点（步骤 8 核实）**：`transfer_fee_bps=0.1` 为中国结算 2022-04-29 起现行费率（此前沪深 0.02‰、北 0.025‰）；
v1 不做费率版本化，报告须声明「成本口径为当前费率，历史回测用现值近似」（调研 §18 U13）。

### 2.8 `scripts/verify_all.py`（E5）

```python
def collect(reports_dir):    # -> Dict[str, dict]（按 tool 取最新）
def merge_status(reports):   # -> "pass" | "warn" | "fail"
def main(argv=None):         # argparse: --reports-dir / --out / --strict
```

- 默认 `--reports-dir out/verification`、`--out out/verification/summary.json`；
- 输出终端表：`tool / status / checks / artifacts / sha8`；
- 退出码：pass=0、warn=0、fail=1、`--strict` 时缺失=1；
- 无报告目录 → 输出空 summary + `missing` 全部 4 工具（exit 0，除非 `--strict`）。

**summary.json**：

```json
{
  "generated_at": "...",
  "overall": "pass",
  "tools": [{"tool": "...", "status": "pass", "n_checks": 10,
             "n_artifacts": 2, "sha8": ["82728ce1"]}],
  "missing": []
}
```

### 2.9 4 个脚本 `--report-json`（E5）

每个脚本新增 argparse 参数 `--report-json PATH`（默认 `None`），在既有断言流程后追加：

```python
if args.report_json:
    write_report_json(args.report_json, tool="verify_xxx", checks=[...], artifacts=[...])
```

**约束**：
- 不改变任何既有 print/落盘行为（新参数默认关闭）；
- `checks` 的 id 复用既有断言名（`verify_capacity_impact`/`verify_portfolio_backtest` 用既有 V1-Vn；`verify_stat_evidence` 用 section 名 dsr/pbo/curve/leakage；`contract_gate` 用 gate 检查名；无既有命名的脚本定义新短 id），`ok` 由断言结果决定；
- 写入前 `mkdir(parents=True, exist_ok=True)`；
- 任一断言失败时脚本仍按原逻辑 exit 非 0（`--report-json` 不改变退出码）；
- `write_report_json` 不设共享模块：各脚本内联私有 `_write_report_json(path, tool, checks, artifacts)`（约 20 行，schema 按设计 §8.1），避免 `scripts/` 跨文件 import（非包）且不改文件计数。

---

## §3 工程细节

### 3.1 版本锚点（6 处，机械同步）

| # | 位置 | 期望 |
|---|------|------|
| 1 | `pyproject.toml` `:7` `version` | `3.9.0` |
| 2 | 根包 `factor_pipeline/__init__.py` `:58` `__version__`（注意：`backtest/__init__.py` 无版本行且不修改） | `3.9.0` |
| 3 | `config_v2.py`（仓库根）`:371` 版本常量 | `3.9.0` |
| 4 | `reporting.py`（仓库根）`:40` `pipeline_version` | `3.9.0` |
| 5 | `tests/test_fix3_version_unification.py` `EXPECTED_VERSION` | `3.9.0` |
| 6 | `tests/test_backtest/verify_fix3_manual.py:21` `EXPECTED_VERSION` | `3.9.0` |

### 3.2 依赖与版本

| 依赖 | 用途 | 新增? |
|------|------|-------|
| numpy | 全部实现 | 否（既有核心） |
| pandas | trace 的 DataFrame 分支（延迟 import）、data_bridge | 否（既有核心） |
| pytest | 测试 | 否（既有 dev） |
| pyarrow | 不涉及 | — |

**Z6 解释**（设计 §11）：`trace.py` / `tradability.py` 顶层仅 stdlib + numpy；pandas 仅在 DataFrame 分支内延迟 import，不构成新增依赖。

### 3.3 Python 3.9 兼容

- 不用 PEP 604（`X | Y`）、不用内置泛型下标（`list[int]`）；
- 用 `typing.Optional/Tuple/List/Dict`；
- `dataclass(frozen=True)` + `object` 基类（对齐仓库风格）；
- AST 扫描门禁复用 v3.8.0 的 `scan_py39` 形态（脚本化验收）。

### 3.4 序列化与哈希

- JSONL：`json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",", ":"))`；
- `NaN/Inf` 在 diagnostics 中转为字符串 `"NaN"/"Infinity"`（避免非法 JSON）；
- `content_hash` 的 float64 字节使用本机小端（跨平台可比性由 `code_version` + 文档声明，不做跨端 bitwise 承诺）。

### 3.5 错误类型

| 场景 | 类型 | 消息要求 |
|------|------|---------|
| PanelSpec 参数越界 | `ValueError` | 含字段名与实际值 |
| board_mix 和越界 | `ValueError` | 含实际和 |
| 规则表无命中/重叠 | `ValueError` | 含 `board/is_st/date` |
| `execute_at` 非法 | `ValueError` | 含实际值 |
| 形状不一致 | `ValueError` | 含期望/实际 shape |
| content_hash 不支持类型 | `TypeError` | 含类型名 |

### 3.6 并发与资源

- 全部新模块**无全局状态**（`INVARIANTS` 为模块级只读列表，注册在 import 期完成）；
- trace 文件句柄：每 step 追加写后立即关闭（不长期持有）；
- `build_panel` 无文件 IO。

### 3.7 文件布局（新增 18 个文件，修改 11 个）

```
新增（16 个主体）：
  tests/synthetic/__init__.py
  tests/synthetic/panel.py
  tests/synthetic/scenarios.py
  tests/test_synthetic_panel.py
  tests/invariants/__init__.py
  tests/invariants/registry.py
  tests/invariants/backtest_engine.py
  tests/invariants/factor_metrics.py
  tests/invariants/data_bridge.py
  tests/invariants/execution_core.py
  tests/invariants/winsor.py
  tests/invariants/test_registry.py
  backtest/trace.py
  tests/test_trace.py
  backtest/tradability.py
  tests/test_tradability.py
新增（E5，2 个）：
  scripts/verify_all.py
  tests/test_verify_all.py
修改（11 个）：
  backtest/engine.py                   （E0 4 行）
  scripts/verify_capacity_impact.py    （--report-json）
  scripts/verify_stat_evidence.py      （--report-json）
  scripts/verify_portfolio_backtest.py （--report-json）
  scripts/contract_gate.py             （--report-json）
  pyproject.toml / factor_pipeline/__init__.py / config_v2.py / reporting.py   （版本锚点 4 处；config_v2.py 与 reporting.py 位于仓库根）
  tests/test_fix3_version_unification.py                      （版本锚点）
  tests/test_backtest/verify_fix3_manual.py                   （版本锚点）
```

> 计数：测试辅助 12（synthetic 3 + invariants 7 + 2 个测试文件）+ 生产 2 + 脚本 1 + 测试文件 3 = **18 个新文件**（含 `test_registry.py`）；修改 **11 个**（engine 1 + 脚本 4 + 版本锚点 6）。

---

## §4 低效操作排除表（不做什么）

| # | 不做 | 原因 |
|---|------|------|
| 1 | 不引入 Hypothesis / pandera / GE / OpenLineage / MLflow / DVC | 零依赖纪律；设计 D2/D3 已裁决 |
| 2 | 不为 trace 建 CLI 查询工具 | v1 只需 `find_first_divergence` 函数 |
| 3 | 不做 trace 可视化/HTML 报告 | 超出本批范围 |
| 4 | 不改 `backtest/__init__.py`（导入结构）与 `data_contract.py`；根包 `factor_pipeline/__init__.py` 仅 `__version__` 行同步 | 硬约束 |
| 5 | 不在 `_evaluate_factor` 内强制接入 tradability | 设计 Q3 裁决：独立函数优先 |
| 6 | 不做 `apply_tradability` 的向量化重写 | 120×N 逐日循环 < 100 ms，够用 |
| 7 | 不为不变量做「自动生成器组合」 | D2：手写 12 条 + 固定场景 |
| 8 | 不新增 `conftest.py` fixture | 避免影响既有 2001 项测试 |
| 9 | 不做跨环境 bitwise 承诺 | 沿用 v3.6.0 裁决 |
| 10 | 不新增配置文件（yaml/toml） | 常量内置 dataclass 默认值 |

---

## §5 TDD 用例与红→绿计划（37 例 + 步骤 10 审计追加 3 例）

### 5.1 用例映射

| ID | 文件 | 用例 | 断言要点 | 阶段 | 红形态 |
|----|------|------|---------|------|--------|
| T390-01 | `tests/test_engine_positions.py`（临时） | B2 有效域 | NaN 股票 `pos==0` | E0 | 断言失败 `first_bad=(0,0) w=0.0909` |
| T390-02 | `test_synthetic_panel.py` | 确定性 | 同 spec 两次 `array_equal(equal_nan=True)` | E1 | `ModuleNotFoundError: tests.synthetic` |
| T390-03 | 同上 | 真值比例 | `limit_heavy` 命中比例 ≈ spec（±1 只/期） | E1 | 同上 |
| T390-04 | 同上 | 一字板可识别 | `detect_limit_lock == ((true_limit_hit!=0)\|true_suspend)` | E1 | 同上 |
| T390-05 | 同上 | PIT 无未来 | `stale_factor` 经 `_apply_loaded_at_lag(fill_missing='nan')` 过滤后无 `loaded_at>date` 的有效值 | E1 | 同上 |
| T390-06 | 同上 | 停牌段锁定 | 停牌段 `volume==0 且 h==l==prev_close` | E1 | 同上 |
| T390-07 | `invariants/test_registry.py` | I1 positions 有效域 | 同 T390-01 | E2 | `ImportError: tests.invariants` |
| T390-08 | 同上 | I2 前向收益无前视 | 扰动未来 `fwd[:t]` 不变 | E2 | 同上 |
| T390-09 | 同上 | I3 换手界 | `0<=tr<=2` | E2 | 同上 |
| T390-10 | 同上 | I4 LS 有效对 | NaN 股票注入收益不改 LS | E2 | 同上 |
| T390-11 | 同上 | I5 RankIC 界 | ∈[-1,1] | E2 | 同上 |
| T390-12 | 同上 | I6 PIT 可见 | 同 T390-05（走 `_apply_loaded_at_lag`） | E2 | 同上 |
| T390-13 | 同上 | I7 ffill 等价 | 无缺失时两模式逐位一致 | E2 | 同上 |
| T390-14 | 同上 | I8 一字板真值 | 同 T390-04 | E2 | 同上 |
| T390-15 | 同上 | I9 冲击单调 | 关于 p / σ 单调不减 | E2 | 同上 |
| T390-16 | 同上 | I10 半衰期恒等 | `rtol=1e-12` | E2 | 同上 |
| T390-17 | 同上 | I11 块长界 | `1<=b<=n//3` | E2 | 同上 |
| T390-18 | 同上 | I12 winsor 截断不变 | 扰动未来前 t 期不变 | E2 | 同上 |
| T390-19 | 同上 | 注册表自检：重名 | `ValueError` | E2 | 同上 |
| T390-20 | 同上 | 注册表自检：唯一/非空 | 12 条、name 唯一、scenario 合法 | E2 | 同上 |
| T390-21 | `test_trace.py` | 关闭零 IO | 目录/文件均未创建 | E3 | `ModuleNotFoundError: backtest.trace` |
| T390-22 | 同上 | JSONL 可读 | 每行可 `json.loads`、字段齐全 | E3 | 同上 |
| T390-23 | 同上 | 确定性 | 同输入两次 `find_first_divergence is None` | E3 | 同上 |
| T390-24 | 同上 | 篡改定位 | 改一步 output → 定位到该 seq | E3 | 同上 |
| T390-25 | 同上 | 异常落 status | `with` 内抛错 → `status=error` + error 字段 | E3 | 同上 |
| T390-26 | 同上 | content_hash 确定性 | ndarray/df/dict 三次同值；NaN 不敏感于 bit | E3 | 同上 |
| T390-27 | `test_tradability.py` | 涨停禁买 | 涨停日买入侧 `effective==prev` | E4 | `ModuleNotFoundError: backtest.tradability` |
| T390-28 | 同上 | 跌停禁卖 | 跌停日卖出侧 `effective==prev` | E4 | 同上 |
| T390-29 | 同上 | 停牌冻结 | 停牌日 `effective==prev` 且 `blocked_suspend>0` | E4 | 同上 |
| T390-30 | 同上 | T+1 锁定 | 买入次日不可卖，`t1_locked>0` | E4 | 同上 |
| T390-31 | 同上 | 规则版本化 | 2026-07-03→5%、07-06→10%（主板 ST） | E4 | 同上 |
| T390-32 | 同上 | 限价取整 | `prev=10.00, pct=0.10` → 11.00 / 9.00 | E4 | 同上 |
| T390-33 | 同上 | 成本分离 | 卖出比买入多 `stamp_tax_bps` 对应额 | E4 | 同上 |
| T390-34 | 同上 | 顺延计数 | 连两日涨停后开板，`deferred` 与补成交一致 | E4 | 同上 |
| T390-35 | 同上 | 规则表无命中/重叠 | `ValueError`（含 board/is_st/date） | E4 | 同上 |
| T390-36 | `test_verify_all.py` | 聚合正确 | 3 份报告 → 总状态/计数正确 | E5 | `ModuleNotFoundError: scripts.verify_all` |
| T390-37 | 同上 | 缺失容错 | 缺 1 份 → `missing` 含之，overall 仍 pass | E5 | 同上 |
| T390-38 | 同上 | exit code | pass→0、fail→1、`--strict`+missing→1 | E5 | 同上 |

**计数**：编号 38 个，**终态 37 例**——T390-01 在 E2 完成后删除（其断言由 T390-07/I1 承接）。
**步骤 10 审计追加**：T390-39/40/41 三例（H1 content_hash ±inf 区分 / H2 adj_jump 网格校验次序 / H3 collect 顶层非 dict 容错）→ 终态 **40 例**。
分配：E1 5（02-06）+1（T390-40）、E2 14（07-20）、E3 6（21-26）+1（T390-39）、E4 9（27-35）、E5 3（36-38）+1（T390-41）。

### 5.2 红→绿记录形态（步骤 9 填写）

| ID | 红读数 | 绿读数 | 日期 |
|----|--------|--------|------|
| T390-01 | `AssertionError: first_bad=(0,0) w=0.090909…`（n_select=11，1/11） | `1 passed`（随后删除，I1 承接） | 2026-11-19 |
| T390-02~06 | `ModuleNotFoundError: No module named 'tests.synthetic'` | `5 passed` | 2026-11-19 |
| T390-07~20 | `ModuleNotFoundError: No module named 'tests.invariants'` | `14 passed`（`run_all` 0.42 s） | 2026-11-19 |
| T390-21~26 | `ModuleNotFoundError: No module named 'backtest.trace'` | `6 passed in 0.24s` | 2026-11-19 |
| T390-27~35 | `ModuleNotFoundError: No module named 'backtest.tradability'` | `9 passed in 0.13s` | 2026-11-19 |
| T390-36~38 | `FileNotFoundError: scripts/verify_all.py`（`spec_from_file_location` 红形态） | `3 passed` | 2026-11-19 |
| T390-39~41 | 探针首轮 FAIL（步骤 10 审计红读数）：P3-3c `inf vs 0 区分=False`（H1）；P1-1g0/P2-2g `ValueError: 普通日 round2 后 high-low<0.02 at (41,0)`（H2）；p3 crashed `'str' object has no attribute 'get'`（H3） | `40 passed in 1.28s`（G1 全集；受影响子集 `31 passed`） | 2026-11-19 |

### 5.3 Fixture 清单

| Fixture | 来源 | 用途 |
|---------|------|------|
| `SCENARIOS[name]` + `build_panel` | `tests/synthetic/` | 全部新增测试 |
| 真实单日面板 | `E:\Level 1 Data` 2023-03-01（可选，仅 B2 影响量化） | §6.2 |
| 既有 `conftest.sample_factor_data` | `tests/conftest.py` | B2 turnover 影响量化 |

---

## §6 性能验证

### 6.1 性能预算

| 项 | 命令 | 预算 | 实测（步骤 9 填） |
|----|------|------|------------------|
| `build_panel` | `pytest -q tests/test_synthetic_panel.py --durations=5` | < 50 ms/场景 | 5.7 ms/场景（120×60） |
| 12 条不变量 | `pytest -q tests/invariants` | < 5 s | 0.42 s（首次全量 415 ms） |
| `apply_tradability` | `test_tradability` durations | < 100 ms（120×60） | 9.5 ms |
| trace 单 step | `test_trace.py --durations` | < 20 ms | 0.4 ms |
| `verify_all` | 人工计时 | < 1 s | 90.8 ms |

### 6.2 B2 影响量化（E0 必做）

| 项 | 命令 | 判据 |
|----|------|------|
| 合成 turnover diff | TEMP 脚本：`sample_factor_data` 跑 `_evaluate_factor` 前后 | 记录数值；**判据勘误**：方向依数据（conftest 均值 +0.008979 / synth:stale −0.087217），不以「修复后不更高」为准 |
| 真实数据 | 2023-03-01 分钟线聚合日线，`close/open-1` + 5% NaN | NaN 股票仓位 271→0；权重 L1 差 0.541459（542 格） |
| 默认快照 | `python scripts/verify_capacity_impact.py` 双跑 | 通过：双跑 SHA256 `82728CE1…` 不变 |

---

## §7 验收命令与证据出口

### 7.1 门禁命令（5 个新增测试文件显式枚举，不用通配符）

```powershell
# G1 快速门禁（新增测试）
python -m pytest tests/test_synthetic_panel.py tests/invariants tests/test_trace.py tests/test_tradability.py tests/test_verify_all.py -q

# G2 默认快照
python -m pytest tests/test_execution_default_snapshot.py -q

# G3 默认路径 SHA
python scripts/verify_capacity_impact.py   # 双跑，比对 SHA256

# G4 全量
python -m pytest tests -q

# G5 B2 影响量化（TEMP 脚本）
python %TEMP%\audit_v390_turnover_diff.py

# G6 聚合入口
python scripts/verify_all.py --reports-dir out/verification

# G7 版本锚点
python %TEMP%\scan_version_anchors.py --expect 3.9.0

# G8 Python 3.9 AST
python %TEMP%\scan_py39.py
```

### 7.2 证据出口

| 证据 | 路径 | 判据 |
|------|------|------|
| 全量 junit | `%TEMP%\g4_junit_v390.xml`（步骤 10 复跑：`g4_junit_v390_rerun.xml`） | tests=2041 / failures=0 / errors=0 / skipped=15 |
| 默认容量快照 | `out/capacity_impact.json` | SHA256 `82728CE1…` |
| 聚合摘要 | `out/verification/summary.json` | overall=pass |
| B2 影响 | `out/v390_b2_impact.txt`（或 TEMP） | diff 数值 + 结论 |
| 红→绿记录 | `docs/CHECKLIST_V3.9.0_*.md` §3 | 每例双读数 |

### 7.3 不达标处置

- 性能超预算 → 先缩面板（60×30），**不得**放宽断言；
- 全量新增失败 → 3-Strike 协议定位；若为既有断言受 B2 影响，须在 CHANGELOG 声明并更新断言（属预期变更）；
- SHA 漂移 → CRITICAL，回滚 E0 并重查（`_build_positions` 不应在默认路径上）。

---

## §8 回滚与风险

### 8.1 回滚点

| # | 回滚操作 | 判据 |
|---|---------|------|
| R1 | 还原 `engine.py` 4 行 | T390-01/07 回到红；turnover 回到旧值 |
| R2 | 删 `tests/synthetic/` | 相关测试 ImportError（预期） |
| R3 | 删 `tests/invariants/` | 14 例消失 |
| R4 | 删 `backtest/trace.py` + `tests/test_trace.py` | 6 例消失 |
| R5 | 删 `backtest/tradability.py` + `tests/test_tradability.py` | 9 例消失 |
| R6 | 删 `scripts/verify_all.py` + 4 处 `--report-json` | 默认输出不变 |

### 8.2 风险

| # | 风险 | 处置 |
|---|------|------|
| 1 | B2 修复改变 turnover 历史读数 | 独立提交；CHANGELOG 声明；diff 量化（§6.2） |
| 2 | 合成面板过于理想 | 每场景真实数据回放对照（V3.8.0 先例） |
| 3 | 规则表待核日期 | 规则表日期已**全部核实**（调研 §18 U9-U12，步骤 8：star 2019-07-22 / main ST 1998-04-22 / gem 2009-10-30 / 注册制前 gem ST 5%）；仅「新股上市初期不设涨跌幅」为已知简化 |
| 4 | `run_all` 缓存导致测试间串扰 | 面板不可变（frozen dataclass + 只读约定），`check` 内禁止原地写 |
| 5 | trace JSONL 体积 | 仅 `enabled=True` 时写；单 step 一行；不做压缩 |
| 6 | I7 依赖 `_apply_loaded_at_lag` 的现有语义 | 先读该函数边界（`fill_missing` 两分支），再定断言 |

### 8.3 实施偏差登记（步骤 6 复核）

| # | 设计条目 | 实施偏差 | 理由 |
|---|---------|---------|------|
| P-1 | 设计 §7.6「非 None → `_evaluate_factor` 输出 `tradability` 键」 | 本批**不改** `_evaluate_factor`，仅提供独立函数 | `_evaluate_factor` 只持有 `self._close`，注入 full panel 需改构造函数签名，风险大于收益；设计 Q3 明确授权「默认仅独立函数，引擎集成作为可选项（步骤 5 定）」——**步骤 6 裁决：维持，合规** |
| P-2 | 设计 §2.6「`trace.py` 仅 numpy+stdlib」 | DataFrame 分支延迟 import pandas | **步骤 6 改判：非偏差**——设计 §3.1 依赖方向已写「`backtest/trace → (stdlib + numpy/pandas 可选)`」；实施约束 = 顶层无 `import pandas` 以通过 Z6 AST 扫描 |
| P-3 | 设计 §4.2 第 7 步因子 `H=5` | 实施时 `H=min(5, n_dates-1)` | 保证 `n_dates` 较小时不越界（默认 120 不受影响） |

---

## §9 步骤 6 幻觉消除 review 记录（已回填，v1.0 → v1.1）

> 日期：2026-11-19。方法：阶段 3 快速 review（接口/算术/逻辑/依赖）→ 阶段 4 外部锚点核实 →
> 阶段 5 工程核实 → 修复 → 二次复核。全部发现逐条对照源码核实（非记忆）。

### 9.1 发现与修复

| # | 级别 | 位置 | 问题 | 核实证据 | 修复 |
|---|------|------|------|---------|------|
| C-1 | CRITICAL | §2.2 步骤 3（沿袭设计 §4.2） | 「`u,d=\|N(0,0.005)\|+0.002` 保证 round2 后 `high-low>=0.02`」数学不成立：`close[0]~LogNormal(0,0.3)` 中位数 1 元，`close×0.004` 远小于 0.02（需 close≥7.5）；普通日可被误判一字板，I8/T390-04 偶发失败 | 逐项算术复核 | `u,d=\|N(0,0.005)\|+max(0.002, 0.0155/close)` 价格地板 + 校验升级为「round2 后 ≥0.02 逐元素」+ `open` 夹取 `[low,high]`；设计 §4.2 同步勘误（v1.2） |
| M-1 | MAJOR | §2.4 I6/I7、§5.1 T390-05/12 | `apply_loaded_at_filter(f, loaded, ...)` 为**杜撰签名**，代码库不存在（全仓 grep 仅命中文档） | `data_bridge.py:203` 真实为 `DataBridge._apply_loaded_at_lag(factor_data, loaded_at_data, use_loaded_at=True, fill_missing='ffill')`（stocks×dates DataFrame，私有方法） | 改写为真实签名 + `__new__` 调用 + `'nan'` 分支断言 |
| M-2 | MAJOR | §3.1 #2、§3.7、§4#4 | 版本锚点 #2 写「`__init__.py :58`」，`backtest/__init__.py:58` 实为 `__all__ = [`，且该文件属硬约束不改 | grep `^__version__\s*=`：唯一命中根包 `factor_pipeline/__init__.py:58` | 锚点 #2/修改列表/排除表明确为根包 `factor_pipeline/__init__.py` |
| M-3 | MAJOR | §2.6 | 未裁决设计 Q1：`_content_digest` 仅抽样（首8/中≤8/尾8 行），DataFrame 中段篡改可漏检 → T390-24 可能漏定位 | 设计 §15 Q1 + `data_contract.py:302-324` | content_hash(DataFrame) 追加列 sum/mean/NaN 计数三项全局统计并入哈希 |
| M-4 | MAJOR | §2.2 步骤 4 | synthetic 步骤 4 需按 §7.2 规则表查 `pct`，但依赖纪律禁止 `tests/synthetic` import `backtest.*`，pct 来源悬空 | 设计 §3.1 + §4.2 第 4 步 | `tests/synthetic` 内置 `_RULE_PCT` 数值副本，漂移由 T390-04/T6 交叉验证捕获 |
| m-1 | MINOR | §3.1 #3/#4 | `config_v2.py`/`reporting.py` 未标路径，易误读为 `backtest/` 下（该位置不存在） | grep：两文件位于仓库根，`:371`/`:40` 行号吻合 | 补「仓库根」注记 |
| m-2 | MINOR | §2.7.2 | `can_sell` docstring 含 `& t1_ok`，与设计 §7.4 矛盾（can_trade 无状态输入，T+1 属权重推进第 5 步） | 设计 §7.3/§7.4 对照 | docstring 去 `t1_ok`，注明由 apply_tradability 并入 |
| m-3 | MINOR | §2.7.4 | 标题与代码块误导为本批实施；`backend/engine.py` 错字 | P-1 裁决 + 包名核实 | 标注「本批不实施」；改 `backtest/engine.py` |
| m-4 | MINOR | §0.3 D5 | 「3 行 diff」与 §2.1「4 行变更」矛盾（设计 §9.5「还原 3 行」同错） | 设计 §9.2「1 新增 + 1 替换 + 2 改名」= 4 行 | 统一为 4 行；设计 §9.5/§14 S1 勘误 |
| m-5 | MINOR | §8.1 R6 | 「5 处 `--report-json`」应为 4 处 | §2.9 与设计 §8.3 均为 4 脚本 | 改 4 处 |
| m-6 | MINOR | §2.2 步骤 3 | `r=rng.normal(0,sigma)` 中 `sigma` 未定义来源 | 设计 §4.2 `sigma_i~U(0.008,0.03)` | 补全 |
| m-7 | MINOR | §2.4 I11 | `1<=b<=len(x)//3` 对 n<3 失效（实现返回 1，`n//3=0`） | `bootstrap.py:24-37`（upper=max(1,n//3)） | 补输入约束 `len(x)>=30` |
| m-8 | MINOR | §2.9 | 「id 复用既有断言名（V1-V10 等）」仅部分成立 | grep 4 脚本：capacity/portfolio 有 V 命名，stat_evidence 用 section 名，contract_gate 用 gate 名 | 措辞按脚本分类放宽 |
| m-9 | MINOR | §8.3 P-2 | P-2 登记为「偏差」不当：设计 §3.1 已允许 pandas（可选） | 设计 §3.1 原文 | 改判「非偏差」，保留顶层无 import 约束 |
| m-10 | MINOR | §2.9 | `write_report_json` 归属未定义（scripts 非包，跨脚本 import 不可靠） | 设计 §8.1 仅 schema | 各脚本内联 `_write_report_json` 私有函数 |

### 9.2 P-1/P-2/P-3 裁决

| # | 裁决 |
|---|------|
| P-1 | **维持**（合规）：设计 Q3 明确授权步骤 5 决定「默认仅独立函数」；§2.7.4 已标注为可选项 |
| P-2 | **改判非偏差**：设计 §3.1 允许 pandas 可选；实施约束 = 顶层无 `import pandas`（过 Z6 AST） |
| P-3 | **维持**（合理）：`H=min(5, n_dates-1)` 防 `fwd5` 越界，默认 120 期不受影响 |

### 9.3 各阶段结论

| 项 | 结论 |
|----|------|
| 接口与源码核对 | engine.py:171-201 行号逐行吻合；`auto_block_size`/`half_life`/`SqrtImpact`/`detect_limit_lock`/`EnhancedRankPreservingScaler`/`_content_digest`/`compute_long_short_returns`（valid 掩码 :330-351）/`sample_factor_data`/`test_execution_default_snapshot.py`/4 脚本全部存在；签名核对发现 M-1/m-2，已修 |
| 算术/计数复核 | 37 例分配 5+14+6+9+3 ✓；目标 2038/2023/15 ✓；新增 18 / 修改 11 ✓；T390-32 限价取整 11.00/9.00 ✓；B2 红读数 (0,0) w=1/11 ✓；m-4/m-5 计数矛盾已修；**C-1 算术幻觉（本 review 最重发现）已修** |
| 依赖与版本 | 零新增依赖成立（numpy/pytest/stdlib + 既有 pandas 延迟 import）；版本锚点 6 处：#1/#3/#5/#6 直接吻合，#2 指代纠偏（根包），#4 补路径注记；M-2/m-1 已修 |
| 引用一致性（设计 ↔ 实施） | §7.2 规则表 11 条 / §7.4 签名与 7 步 / §7.5 成本口径 / §8.2 聚合 / §13 计数 / §14 S1-S6 映射逐项一致；Q1 未落地（M-3）与步骤 4 pct 来源悬空（M-4）已补；上游勘误（§4.2 步骤 3、§9.5、§14 S1/S5）在设计 v1.2 同步 |
| 外部锚点（阶段 4） | 主板 ST 2026-07-06 5%→10%、gem 2020-08-24 20%、bse 2021-11-15 30%、印花税 5bp（卖出单边）、过户费 0.1bp（双向）、佣金 2.5bp ≤ 3‰ 上限 —— 均与调研 §10 已核实锚点一致，无幻觉 |
| 结论 | **PASS_WITH_FIXES**：1 CRITICAL / 4 MAJOR / 10 MINOR 全部修复，二次复核通过；本文件升 v1.1，设计文档升 v1.2（§4.2/§9.5/§14 勘误 + §17 修订记录） |
