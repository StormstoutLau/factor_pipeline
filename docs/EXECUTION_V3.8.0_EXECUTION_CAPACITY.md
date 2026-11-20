# EXECUTION v3.8.0 — 多日执行模型 + Regime 容量压力测试

> **日期**: 2026-11-19
> **对应设计**: [DESIGN_EXECUTION_CAPACITY_V3.8.0.md](private/DESIGN_EXECUTION_CAPACITY_V3.8.0.md) v1.2（§22 幻觉消除 review #1 + 步骤 6 对齐修订）
> **对应调研**: [RESEARCH_V3.8.0_EXECUTION_CAPACITY.md](research/RESEARCH_V3.8.0_EXECUTION_CAPACITY.md)（三轮 + §19 复审）
> **默认路径纪律**: `python scripts/verify_capacity_impact.py`（无参数）输出与 v3.7.0 逐位一致
> **基线**: 1929 passed / 15 skipped（v3.7.0）
> **目标**: 1929 + 56 = 1985 passed / 15 skipped / 0 failed（步骤 10 审计修复后终态：1929 + 57 = **1986 passed**，见 §0.2）

---

## §0 摘要、档位与工件状态

### 0.1 交付内容

| 编号 | 交付 | 形态 |
|------|------|------|
| E0 | 骨架 + 端口 + 配置 + 分钟/日频加载器 + 价差代理（CS/AR/Amihud 纯函数） + 新鲜度守卫默认化 | `backtest/execution/` 新包（含 `core/spread.py`，E2 才消费）；`pyproject` 新增 `calib` extra |
| E1 | BVC + 分钟级冲击面板（λ 与 b） | `core/classification.py` + `shell/loaders.py`（分钟聚合） |
| E2 | 4 模型拟合 + 三角验证 + c 三档 | `core/impact.py` |
| E3 | T+1 reversal 永久/临时分离 | `core/impact.py::temporary_share` |
| E4 | 衰减核 + `net(h)` + 执行天数 | `core/decay.py` |
| E5 | regime 压力 + co-impact κ | `shell/runner.py` + `core/impact.py` |
| E6 | 滚动 AveW + 漂移诊断 | `shell/runner.py`（AveW / 漂移诊断，无独立 rolling 模块） |
| E7 | 脚本接入 `--calibrate` + 文档 + 一致性 | `scripts/verify_capacity_impact.py` |

### 0.2 工件状态

| 工件 | 状态 |
|------|------|
| 调研文档 | v1.0（§19 复审 PASS_WITH_FIXES 已闭环） |
| 设计文档 | v1.2（§22 review #1 闭环 2 P1 / 2 P2 / 5 P3；§7.1 / §16.2 步骤 6 对齐修订） |
| 实施文档 | 本文件（步骤 5 产出 + 步骤 6 review 修订，见 §9：3 P2 / 7 P3 全修） |
| Checklist | 步骤 7 生成；步骤 9 回填（56/56 通过）；步骤 10 审计回填（57/57 通过 + T380-25b） |
| 代码 | 已实施（步骤 9 TDD：14 模块 + 9 测试文件 56 例；先红后绿，见 §5.2/§6；步骤 10 审计修复 H2 并新增 T380-25b → 57 例） |
| 步骤 10 审计 | 异构复审 **PASS_WITH_FIXES**（[2026-11-19-v3.8.0-execution-capacity-audit.md](audit/2026-11-19-v3.8.0-execution-capacity-audit.md)）：5 视角 × 48 探针 48 PASS / 4 P3 披露 / 探针勘误 9 项留档；唯一真实缺陷 H2（`detect_limit_lock` 零量分支缺 `c==l`，spec §2.7 偏离、真实数据零影响）已修复；探针留档 `out/review_v380_results.txt` |

### 0.3 与路线图的映射

对应 [MULTIFACTOR_GOVERNANCE_ROADMAP.md](analysis/MULTIFACTOR_GOVERNANCE_ROADMAP.md) 治理路线图 P2 的
「组合/容量未成为上线门禁」与「冲击模型为 stylized」两项；本批不改任何默认容量口径（D2），
只新增证据层与压力档。

### 0.4 D1-D4 实施落点

| 决策 | 内容（design §0） | 落点 |
|------|------------------|------|
| D1 | pyarrow → `calib` extra + `find_spec` 能力探测，不进核心依赖 | §2.3（`has_pyarrow`）/ §3.2 / T380-56 |
| D2 | 不替换默认 `c=0.5`；`c_stress = max(0.5, c_ci_upper)` 只进压力档，不回写 | §4（不回写默认 c）/ T380-50 |
| D3 | AveW 对 4 窗长**预测**等权平均；IJR 自动窗长仅诊断 | §2.8 / T380-45~47 |
| D4 | `net(h)` 曲线 + 平坦区判定，默认持有档 h=20 | §2.8（`net_curve`/`plateau`）/ T380-30~32 |

---

## §1 任务分解（E0-E7）

```
E0 ──┬── E1 ──┬── E2 ──┬── E4
     │        │        ├── E5 ── E6 ── E7
     │        └── E3 ──┘
     └───────────────────────────（E0 的加载器为所有下游前置）
```

| 任务 | 前置 | 产出 | 验收出口 |
|------|------|------|---------|
| E0 | — | 包骨架、4 端口、配置、加载器、价差代理纯函数、能力探测、导入冒烟 | `pytest tests/test_execution_architecture.py tests/test_execution_import_smoke.py` |
| E1 | E0 | `MinuteAggregate`、BVC、λ 面板、一字板识别 | `pytest tests/test_execution_classification.py` + 面板覆盖报告 |
| E2 | E1 | 4 模型 fit/predict、CV-RMSE 选型、c 三档 | `pytest tests/test_execution_impact.py` + 校准 JSON |
| E3 | E1 | `temporary_share`（T+1 reversal） | 同上 |
| E4 | E2 | `rho`/`retention`/`net(h)`/`plateau`/`execution_days` | `pytest tests/test_execution_decay.py` |
| E5 | E2 | regime 分桶 + κ 情景 + 主值三元 | `pytest tests/test_execution_capacity.py` |
| E6 | E5 | 4 窗长 AveW + 漂移诊断 | 同上 |
| E7 | E6 | `--calibrate` 分支 + 文档同步 + 一致性 | 默认路径快照 + 全量 |

---

## §2 接口签名与回退点

### 2.1 `backtest/execution/ports.py`（E0）

```python
# -*- coding: utf-8 -*-
"""v3.8.0 执行/容量模块端口契约（纯契约，无实现、无 IO）。"""
from typing import Mapping, Protocol, Sequence, runtime_checkable
import numpy as np


class CalibrationUnavailable(RuntimeError):
    """分钟级校准所需的可选依赖或数据缺失。"""


@runtime_checkable
class ImpactModel(Protocol):
    name: str
    def predict(self, participation: np.ndarray, sigma: np.ndarray,
                params: Mapping[str, float]) -> np.ndarray: ...
    def fit(self, participation: np.ndarray, impact: np.ndarray,
            sigma: np.ndarray) -> Mapping[str, float]: ...


@runtime_checkable
class SpreadEstimator(Protocol):
    name: str
    def estimate(self, high: np.ndarray, low: np.ndarray,
                 close: np.ndarray) -> np.ndarray: ...


@runtime_checkable
class VolumeClassifier(Protocol):
    name: str
    def classify(self, ret: np.ndarray, volume: np.ndarray,
                 sigma: np.ndarray) -> np.ndarray: ...


@runtime_checkable
class DecayModel(Protocol):
    name: str
    def retention(self, horizons: Sequence[int]) -> np.ndarray: ...
```

**回退点**：端口仅 4 个；若 E2 需要额外输入（如 `tau`），以参数传入而非扩端口（保持契约稳定）。

### 2.2 `backtest/execution/config.py`（E0）

```python
@dataclass(frozen=True)
class CalibrationConfig(object):
    data_root: str = r"E:\Ashare_data"
    minute_root: Optional[str] = r"E:\Level 1 Data"
    sample_start: str = "2020-01-31"
    sample_end: str = "2026-01-31"
    participation_grid: Tuple[float, ...] = (0.001, 0.005, 0.01, 0.02, 0.05)
    sigma_clip: Tuple[float, float] = (0.005, 0.20)
    bvc_sigma_bars: int = 20
    block_size_mode: str = "auto"          # auto | sqrt | iid
    windows: Tuple[int, ...] = (24, 36, 48, 60)
    kappa: float = 1.5
    p_cap: float = 0.10
    d_max: int = 5
    default_horizon: int = 20
    tau_max_minutes: int = 240
    lambda_p_threshold: float = 0.05
    seed: int = 20261118

    def config_hash(self) -> str:
        """sha256(canonical_json(asdict(self)))；排序键 + 不含时间戳。"""
```

**回退点**：`dataclasses.replace` 生成变体，禁止原地修改（frozen 已保证）。

### 2.3 `backtest/execution/registry.py`（E0）

```python
class ModelRegistry(object):
    def register(self, model: object) -> None: ...
    def get(self, name: str) -> object: ...
    def names(self) -> List[str]: ...
```

**回退点**：重名 `register` 抛 `ValueError`（不静默覆盖）。

### 2.4 `backtest/execution/shell/loaders.py`（E0）

```python
def has_pyarrow() -> bool: ...

@dataclass
class MinuteAggregate(object):
    stock_code: np.ndarray        # (n,)
    signed_amount: np.ndarray     # (n,) 元
    total_amount: np.ndarray      # (n,) 元
    sigma: np.ndarray             # (n,) 日内收益标准差
    n_bars: np.ndarray            # (n,) int
    limit_lock: np.ndarray        # (n,) bool
    evidence_level: str = "minutes"

class MinuteLoader(object):
    def __init__(self, root: str, sigma_bars: int = 20): ...
    def available_months(self) -> List[str]: ...        # 'YYYY-MM'
    def load_month(self, ym: str) -> MinuteAggregate: ...  # 缺失抛 CalibrationUnavailable

class DailyLoader(object):
    def load_ohlc(self, start: str, end: str) -> Dict[str, "pd.DataFrame"]: ...
    def load_adj_jumps(self, start: str, end: str) -> "pd.DataFrame": ...

def resolve_evidence_level(cfg: CalibrationConfig) -> str:
    """返回 'minutes' | 'ohlc' | 'daily'，并写 evidence_warnings。"""
```

**回退点**：`MinuteLoader.load_month` 不做缓存（v1）；E1 若单月 > 60s 再加月级缓存。
pyarrow 只在 `load_month` 内部延迟 import。

### 2.5 `backtest/execution/core/impact.py`（E2/E3/E5）

```python
class SqrtImpact(object):
    name = "sqrt"
    def predict(self, p, sigma, params): return params["c"] * sigma * np.sqrt(p)
    def fit(self, p, impact, sigma): ...        # OLS on impact/sigma vs sqrt(p)

class LinearImpact(object):
    name = "linear"
    def predict(self, p, sigma, params): return params["k"] * p
    def fit(self, p, impact, sigma): ...

class LogImpact(object):
    name = "log"
    def predict(self, p, sigma, params):
        return np.maximum(0.0, params["a"] + params["b"] * np.log(p))
    def fit(self, p, impact, sigma): ...        # level ~ log(p)，校验 a + b·ln(p_min) > 0

class PowerImpact(object):
    name = "power"
    def predict(self, p, sigma, params): return params["a"] * p ** params["b"]
    def fit(self, p, impact, sigma): ...


def cross_val_rmse(models, p, impact, sigma, n_folds=5) -> Dict[str, float]:
    """按『股票×月』聚类、按时间切折；返回每个模型的 CV-RMSE。"""


def select_models(cv: Dict[str, float], tol: float = 0.10) -> Tuple[str, List[str]]:
    """主模型 + 并列集合（CV <= (1+tol) * min）。"""


def temporary_share(r1: np.ndarray, rev1: np.ndarray) -> Tuple[float, float, float]:
    """T+1 reversal 分离；返回 (share, ci_lo, ci_hi)，bootstrap 用 auto_block_size。"""
```

**回退点**：`predict` 对 `p <= 0` 抛 `ValueError`；`LogImpact` 越界由 `select_models` 排除，
不在 `predict` 内静默 clip。

**校准纪律（design §9.3，实施必须落地）**：每个「股票×月」λ 带 HAC SE，仅 `p < 0.05`
（`lambda_p_threshold`）纳入容量；不显著者按行业×规模分位 λ 中位数填充并报告
`lambda_fill_ratio`；填充占比 > 30% → 路径 A 结果降级 `[区间]` 并写 `evidence_warnings`。

### 2.6 `backtest/execution/core/spread.py`（E0/E2）

```python
class CorwinSchultz(object):
    name = "corwin_schultz"
    def estimate(self, high, low, close) -> np.ndarray: ...   # 两日修正版
    def zero_ratio(self, high, low) -> float: ...

class AbdiRanaldo(object):
    name = "abdi_ranaldo"
    def estimate(self, high, low, close) -> np.ndarray:
        # S^2 = 4 * E[(c_t - eta_t) * (c_t - eta_{t+1})]，c=ln(close), eta=(lnH+lnL)/2
        ...

class Amihud(object):
    name = "amihud"
    def estimate(self, ret, amount) -> np.ndarray: ...        # |r| / amount，仅排序用
```

**回退点**：`estimate` 长度不足 3 时返回全 NaN（不抛错），由调用方丢弃。

### 2.7 `backtest/execution/core/classification.py`（E1）

```python
def normal_cdf(x: np.ndarray) -> np.ndarray:      # math.erf 向量化，不依赖 scipy

class BVC(object):
    name = "bvc"
    def classify(self, ret, volume, sigma) -> np.ndarray:
        """返回买入量占比 ∈ [0,1]；sigma<=0 的位置返回 0.5。"""


def detect_limit_lock(high, low, close, open_, volume) -> np.ndarray:
    """high==low，或 开=收=高=低 且 volume==0。"""
```

### 2.8 `backtest/execution/core/decay.py`（E4）

```python
def estimate_rho(series: np.ndarray) -> Tuple[float, float, float]:
    """AR(1) + HAC SE；若 95% CI 覆盖 1.0 返回 (1.0, lo, hi)。"""

def retention(horizons: Sequence[int], rho: float) -> np.ndarray: ...

def half_life(rho: float) -> float: ...        # rho>=1 -> float('inf')

def execution_days(notional, adv, p_cap=0.10, d_max=5) -> np.ndarray: ...

def net_curve(alpha0, aum, rho, cost_by_h, horizons=(1, 5, 10, 20, 60)) -> Dict[int, float]:
    """仅对 cost_by_h 提供成本的 h 输出 net（design §10.2：h=1/60 无成本口径，仅 retention）。"""

def plateau(net: Mapping[int, float], sd: float) -> List[int]: ...

class ExponentialDecay(object):
    """DecayModel 端口（§2.1）的唯一具体实现；build_pipeline 装配为 'decay'。"""
    name = "exponential"
    def __init__(self, rho: float) -> None: ...
    def retention(self, horizons: Sequence[int]) -> np.ndarray: ...   # rho ** h
```

### 2.9 `backtest/execution/core/bootstrap.py`（E0）

```python
def auto_block_size(x: np.ndarray, max_lag: int = 10) -> int: ...
```

### 2.10 `backtest/execution/shell/runner.py`（E1-E6 编排）

```python
def build_pipeline(cfg: CalibrationConfig) -> Dict[str, object]:
    """全仓唯一装配点：返回 {'impact': {...}, 'spread': {...},
    'classifier': BVC(), 'decay': ExponentialDecay(rho), 'registry': ModelRegistry()}。"""

def run_calibration(cfg: CalibrationConfig,
                    capacity_fn=None, breakeven_fn=None) -> Dict[str, object]:
    """编排 E1-E6，返回可直接 json.dumps 的 dict（含 config_hash / evidence_level）。

    capacity_fn / breakeven_fn：脚本侧注入的容量函数（依赖注入）。
    design §3.1 禁止 Shell→scripts 边，容量复用只能经注入而非 import；
    传 None 时 capacity 字段为 null（仅诊断模式）。"""
```

**复用机制**：脚本 `--calibrate` 分支懒 `import backtest.execution` 后以
`run_calibration(cfg, capacity_fn=capacity_from_p95, breakeven_fn=breakeven_aum)`
注入脚本内 `:192`/`:199` 函数；T380-41 经 monkeypatch 该函数并断言校准输出随动，
证明两路径调用同一实现（无第二套容量算法）。

### 2.11 `scripts/verify_capacity_impact.py` 改动（E7）

```python
# 仅新增分支；无参数路径不进入新代码
ap.add_argument("--calibrate", action="store_true")
ap.add_argument("--evidence-level", choices=["minutes", "ohlc", "daily"], default=None)
ap.add_argument("--diagnose-window", action="store_true")
```

**回退点**：新分支产物写 `out/capacity_calibration.json`；默认产物
`out/capacity_impact.json` 的键集合与数值逐位不变。

### 2.12 `backtest/execution/shell/report.py`（E5/E7，对应 design §3.3）

```python
def write_calibration_json(payload: Dict[str, object], path: str) -> None: ...

def write_calibration_markdown(payload: Dict[str, object], path: str) -> None:
    """校准 Markdown 报告；页脚写入 config_hash 与 evidence_level（design §14）。"""
```

**回退点**：仅落盘，不做计算；`payload` 由 `run_calibration` 产出，本模块不二次编排。

---

## §3 工程细节

### 3.1 版本锚点（6 处，机械同步）

| 文件 | 位置 |
|------|------|
| `CHANGELOG.md` | 顶部新增 `## v3.8.0 — …` |
| `pyproject.toml` | `version = "3.7.0"` → `"3.8.0"`（L7；对齐 v3.7.0 批次先例） |
| `README.md` | 版本徽标 / 能力清单 |
| `docs/PROJECT_STATUS.md` | 当前版本 + P2 完成项 |
| `docs/audit/CHECKLIST_V3.8.0_EXECUTION_CAPACITY.md` | 步骤 7 新建 |
| `docs/audit/CONSISTENCY_REVIEW_V3.8.0_*.md` | 步骤 8 新建 |

### 3.2 依赖与版本

- 核心：`numpy` / `pandas`（既有，不新增）；
- 可选：`pyarrow>=14.0.0` → 新增 extra `calib`，并追加进 `all`（`pyproject.toml:56`）；
- **不进入 core**：`scipy`（虽已是核心依赖 `pyproject.toml:29`，但 core 层零第三方纪律仅允许
  `numpy`，erf 用 A&S 近似或 `math.erf` 向量化）、`statsmodels`（HAC 复用 `effect_size.newey_west_se`）。

### 3.3 Python 3.9 兼容

- 禁 `X | Y`、禁 `list[str]` 泛型下标；用 `Optional` / `Union` / `Tuple` / `Dict` / `List`；
- `Protocol` 与 `runtime_checkable` 均自 3.8 可用；
- PEP 562 模块级 `__getattr__` 自 3.7 可用。

### 3.4 序列化与哈希

- `config_hash`：`sha256(canonical_json(asdict(cfg)))`，键排序、`separators=(",", ":")`、
  `ensure_ascii=False`；不含时间戳与路径以外的运行时信息；
- 输出 JSON 用 `json.dump(..., ensure_ascii=False, sort_keys=True)`；
- `numpy` 标量统一 `.item()` 转换，NaN → `null`（与 `data_contract._jsonable` 口径一致）。

### 3.5 错误类型

| 异常 | 定义处 | 语义 |
|------|--------|------|
| `CalibrationUnavailable` | `ports.py` | 可选依赖/数据缺失 → 可降级 |
| `ValueError` | 内置 | 输入非法（`p<=0`、长度不足）→ 中止该统计块 |
| `DataContractError` | 既有 `data_contract.py` | 数据不达标 → 中止（不降级） |

**纪律**：`ports.py` 不 import 任何 `backtest.*`，避免与父包形成环。

### 3.6 并发与锁

本批**不加**并发：单月分钟加载为顺序流式，39 月串行；若 E1 实测 > 40 min 再评估
`concurrent.futures.ThreadPoolExecutor`（IO 密集，2-4 线程），并保持结果确定性排序。

### 3.7 文件布局（净新增 14 个模块文件，含 2 个包 `__init__`；另 9 个测试文件）

```
backtest/execution/__init__.py
backtest/execution/ports.py
backtest/execution/config.py
backtest/execution/registry.py
backtest/execution/core/__init__.py
backtest/execution/core/impact.py
backtest/execution/core/spread.py
backtest/execution/core/classification.py
backtest/execution/core/decay.py
backtest/execution/core/bootstrap.py
backtest/execution/shell/__init__.py
backtest/execution/shell/loaders.py
backtest/execution/shell/runner.py
backtest/execution/shell/report.py
tests/test_execution_*.py（9 个）
```

---

## §4 低效操作排除表（不做什么）

| 诱惑 | 决定 | 理由 |
|------|------|------|
| 给 `MinuteLoader` 加 LRU 缓存 | **不做** | 单月聚合后仅数万行，重复读盘的收益低于复杂度 |
| 用 `scipy.stats.norm.cdf` | **不做** | scipy 虽为核心依赖，但 core 层零第三方纪律（T380-53 风格）仅允许 numpy |
| 用 `statsmodels` 做 HAC | **不做** | `newey_west_se` 已存在且经 v3.7.0 审计 |
| 把 4 个冲击模型做成配置文件驱动 | **不做** | 4 个类 + 注册表已足够，配置化会削弱可读性 |
| 多进程并行月份 | **不做（v1）** | 结果需确定性排序；且 IO 为主，收益有限 |
| 为 `--calibrate` 造第二个容量算法 | **不做** | 必须复用 `capacity_from_p95` / `breakeven_aum` |
| 校准结果回写默认 `c` | **不做** | D2 裁决：只进压力档 |

---

## §5 TDD 用例与红→绿计划（56 例；步骤 10 审计新增 T380-25b → 57 例）

### 5.1 用例映射

| ID | 文件 | 用例 | 断言要点 | 阶段 |
|----|------|------|---------|------|
| T380-01 | `test_execution_impact.py` | sqrt 单调 | `p` 递增 → 冲击递增 | E2 |
| T380-02 | 同上 | sqrt 定点 | `p=0.01, σ=0.02, c=0.5` → `1e-3`（10bp） | E2 |
| T380-03 | 同上 | linear 定点 | `p=0.01, k=0.025` → `2.5e-4`（2.5bp） | E2 |
| T380-04 | 同上 | linear 单调 | 同上 | E2 |
| T380-05 | 同上 | log 单调 | `p` 递增 → 递增 | E2 |
| T380-06 | 同上 | log 越界判无效 | `a + b·ln(p_min) <= 0` → 被 `select_models` 排除 | E2 |
| T380-07 | 同上 | power 单调 | `b>0` 时递增 | E2 |
| T380-08 | 同上 | `p=0` 抛错 | 4 个模型均 `ValueError` | E2 |
| T380-09 | 同上 | 常数序列抛错 | `np.ptp(impact)==0` → `ValueError` | E2 |
| T380-10 | 同上 | 选型容差 | CV 差 5% → 并列；差 20% → 单选 | E2 |
| T380-11 | `test_execution_spread.py` | CS 零区间平移 | `h==l` 不产生 NaN/丢弃 | E0 |
| T380-12 | 同上 | CS 负值截断 | 输出 ≥ 0 | E0 |
| T380-13 | 同上 | CS 两日 vs 单日 | 两日估计方差更小（合成数据） | E0 |
| T380-14 | 同上 | CS `zero_ratio` | 全零区间 → 1.0 | E0 |
| T380-15 | 同上 | AR 乘积型 | 用已知 `c,η` 构造 → `S` 反解误差 < 1e-8 | E0 |
| T380-16 | 同上 | AR 负值截断 | `S2<0` → 0 | E0 |
| T380-17 | 同上 | Amihud 量纲 | `|r|=0.01, amount=1e8` → `1e-10` | E0 |
| T380-18 | 同上 | 长度不足 | `n<3` → 全 NaN | E0 |
| T380-19 | `test_execution_classification.py` | `normal_cdf` | `Φ(0)=0.5`、`Φ(1.96)≈0.975` | E1 |
| T380-20 | 同上 | `Φ` 单调 | 严格递增 | E1 |
| T380-21 | 同上 | BVC `r=0` | 返回 0.5 | E1 |
| T380-22 | 同上 | BVC `σ<=0` | 返回 0.5，不产生 inf | E1 |
| T380-23 | 同上 | BVC 占比界 | 输出 ∈ [0,1] | E1 |
| T380-24 | 同上 | 无前视 | 扰动未来 bar，历史 `sigma` 不变 | E1 |
| T380-25 | 同上 | 一字板识别 | `h==l` 命中 | E1 |
| T380-26 | 同上 | 零量识别 | `volume==0 且 o=c=h=l` 命中 | E1 |
| T380-27 | `test_execution_decay.py` | `rho=1` | `retention≡1`、`half_life=inf` | E4 |
| T380-28 | 同上 | `rho=0.9` | `half_life≈6.58` | E4 |
| T380-29 | 同上 | `rho` CI 覆盖 1 | 返回 1.0 | E4 |
| T380-30 | 同上 | `net` 单调 | 成本上升 → net 下降 | E4 |
| T380-31 | 同上 | plateau 含 h* | `h* ∈ plateau` | E4 |
| T380-32 | 同上 | 平坦区退化 | `sd=0` → 仅 `h*` | E4 |
| T380-33 | 同上 | `execution_days` | `notional/(p_cap·adv)` 上取整；≤`d_max` | E4 |
| T380-34 | 同上 | 超限处理 | 超过 `d_max` 标未成交 | E4 |
| T380-35 | `test_execution_bootstrap.py` | 近 iid | `rho≈0` → `b=1` | E0 |
| T380-36 | 同上 | 随 `rho` 增 | `b(ρ=0.6) > b(ρ=0.2)` | E0 |
| T380-37 | 同上 | 上界 | `b <= n//3` | E0 |
| T380-38 | 同上 | 下界 | `b >= 1` | E0 |
| T380-39 | 同上 | 与 `sqrt(T)` 对照 | 同量级（比值 ∈ [0.2, 5]） | E0 |
| T380-40 | 同上 | 确定性 | 同输入两次调用同输出 | E0 |
| T380-41 | `test_execution_capacity.py` | 复用同一函数 | `--calibrate` 与默认路径调用同一 `capacity_from_p95` | E5 |
| T380-42 | 同上 | 同参同果 | 同参数下结果逐位相同 | E5 |
| T380-43 | 同上 | κ 单调 | κ 增大 → 容量减小 | E5 |
| T380-44 | 同上 | 主值取最差 regime | `min` 而非均值 | E5 |
| T380-45 | 同上 | AveW 取预测平均 | 与「参数平均」结果不同（构造反例） | E6 |
| T380-46 | 同上 | AveW 等权 | 4 窗长权重各 0.25 | E6 |
| T380-47 | 同上 | 漂移降级 | `spread>0.30` → 取最差窗 + 警告 | E6 |
| T380-48 | 同上 | λ 反解 | 合成 `r=λx` → 误差 < 1e-6 | E2 |
| T380-49 | 同上 | HAC 生效 | 自相关序列的 SE 大于 iid SE | E2 |
| T380-50 | 同上 | c 三档方向 | `c_stress == max(0.5, c_ci_upper)`（design §9.4，非 point） | E2 |
| T380-51 | `test_execution_default_snapshot.py` | 键集合 | 与 v3.7.0 完全一致 | E7 |
| T380-52 | 同上 | 数值 | 容量关键值容差 0 | E7 |
| T380-53 | `test_execution_architecture.py` | Core 无 IO | AST 无 `os/pathlib/logging/pyarrow/duckdb/pandas/open(` | E0 |
| T380-54 | 同上 | 无反向依赖 | `core/` 不含 `from ..shell` | E0 |
| T380-55 | 同上 | `__all__` 约束 | ≤5 且无 `"*"` | E0 |
| T380-56 | `test_execution_import_smoke.py` | 无 pyarrow 可导入 | 阻断 `pyarrow` 后 `import backtest.execution.core.impact` 成功 **且** `has_pyarrow() is False`（design §16.5） | E0 |

### 5.2 红→绿记录形态（步骤 9 填写）

| ID | 红灯症状（实际报错） | 绿灯证据 | 时间 |
|----|---------------------|---------|------|
| T380-01~10 | `ModuleNotFoundError: No module named 'backtest.execution.core.impact'` | `test_execution_impact.py` 10 passed | 2026-11-19 |
| T380-11~18 | `ModuleNotFoundError: No module named 'backtest.execution.core.spread'` | `test_execution_spread.py` 8 passed | 2026-11-19 |
| T380-19~26 | `ModuleNotFoundError: No module named 'backtest.execution.core.classification'` | `test_execution_classification.py` 8 passed | 2026-11-19 |
| T380-27~34 | `ModuleNotFoundError: No module named 'backtest.execution.core.decay'` | `test_execution_decay.py` 8 passed | 2026-11-19 |
| T380-35~40 | `ModuleNotFoundError: No module named 'backtest.execution.core.bootstrap'` | `test_execution_bootstrap.py` 6 passed | 2026-11-19 |
| T380-41~50 | `ModuleNotFoundError: No module named 'backtest.execution.shell.runner'`（`cfg` fixture error） | `test_execution_capacity.py` 10 passed | 2026-11-19 |
| T380-51~52 | 无红：默认路径未改，基线在盘，首轮即 PASS（E2 证据） | `test_execution_default_snapshot.py` 2 passed | 2026-11-19 |
| T380-53~55 | `AssertionError: core 目录不存在` | `test_execution_architecture.py` 3 passed | 2026-11-19 |
| T380-56 | 子进程 `ModuleNotFoundError: backtest.execution`（`SMOKE_OK` 缺失） | `test_execution_import_smoke.py` 1 passed | 2026-11-19 |

### 5.3 Fixture 清单

| Fixture | 内容 | 用途 |
|---------|------|------|
| `synthetic_impact` | 4 组 `(p, impact, sigma)`，已知 `c`/`k`/`(a,b)` | T380-01~10、48~50 |
| `synthetic_ohlc` | 含零区间日、一字板、负估计的 OHLC 序列 | T380-11~18、25~26 |
| `synthetic_minute_month` | 3 只股票 × 1 日 × 241 bar | T380-19~24 |
| `snapshot_ref` | v3.7.0 `out/capacity_impact.json` 的键与关键值 | T380-51~52 |
| `no_pyarrow_env` | 子进程 + `MetaPathFinder` 阻断 | T380-56 |

---

## §6 性能验证

| 指标 | 预算 | 测量命令 | 实测（2026-11-19） |
|------|------|---------|------------------|
| 单月分钟加载+聚合 | < 60 s | `MinuteLoader.load_month('2023-03')`（TEMP 驱动） | **25.46 s / 23.52 s** 两次（22 文件 / 347 MB / 3437 只 / 18,168,990 bar） |
| 39 月分钟处理 | < 40 min | `python scripts/verify_capacity_impact.py --calibrate` 计时 | 未实跑；单月 ×39 ≈ 15.3 min（E5 外推，v3.8.0 未接线全量分钟编排） |
| 全量 L1 校准 | < 5 min | `--calibrate --evidence-level ohlc` | **3.78 s**（exit 0） |
| 峰值内存 | < 2 GB | `tracemalloc` 峰值打印 | **183.9 MB**（2023-03 单月；含追踪开销时总耗时 73.78 s） |
| 默认路径 | 与 v3.7.0 同量级 | 默认运行计时对照 | **34.3 s / 30.8 s** 两次，`out/capacity_impact.json` SHA256 `82728CE1…` 与 v3.7.0 基线逐位一致 |

超预算处置：先降级证据等级（`minutes → ohlc`），再考虑并发；**不得**为性能牺牲确定性排序。

---

## §7 验收命令与证据出口

### 7.1 门禁命令

```bash
# 快速（每次提交）
python -m pytest tests/test_execution_architecture.py tests/test_execution_import_smoke.py -q

# 单元（E0-E4 完成后；显式枚举——pytest 8.3.4 不展开位置参数通配，PowerShell 5 亦不展开）
python -m pytest tests/test_execution_impact.py tests/test_execution_spread.py tests/test_execution_classification.py tests/test_execution_decay.py tests/test_execution_bootstrap.py tests/test_execution_capacity.py tests/test_execution_default_snapshot.py tests/test_execution_architecture.py tests/test_execution_import_smoke.py -q

# 默认路径守护（必须有 out/capacity_impact.json 基线）
python -m pytest tests/test_execution_default_snapshot.py -q

# 全量（E7 完成后）
python -m pytest tests/ -q
```

### 7.2 证据出口

| 证据 | 路径 |
|------|------|
| 校准 JSON | `out/capacity_calibration.json` |
| 校准 Markdown | `out/capacity_calibration.md` |
| 默认容量 JSON（不变） | `out/capacity_impact.json` |
| 测试输出 | 控制台 + CI 日志 |
| 一致性 review | `docs/audit/CONSISTENCY_REVIEW_V3.8.0_*.md`（步骤 8） |

### 7.3 不达标处置

| 情形 | 处置 |
|------|------|
| 新增测试 skip | **不允许**（除 E 盘/out 基线不可用的环境性 skip，须显式标原因） |
| 默认快照差异 | 阻断合并，定位到具体字段 |
| 覆盖率 `evidence_level` 缺失 | 阻断合并（S5 硬约束） |
| 性能超预算 | 降级证据等级，记录 `evidence_warnings` |

---

## §8 回滚与风险

### 8.1 回滚点

| 回滚点 | 操作 | 影响 |
|--------|------|------|
| R1 | 删除 `--calibrate` / `--evidence-level` / `--diagnose-window` 分支 | 默认路径不受影响 |
| R2 | 删除 `backtest/execution/` 整个包 | 无外部引用 |
| R3 | 移除 `pyproject` 的 `calib` extra 与 `all` 中的 pyarrow | 安装面复原 |
| R4 | 删除 9 个测试文件 | 测试数回到 1929 |

### 8.2 风险

| # | 风险 | 缓解 |
|---|------|------|
| 1 | 父包重导入导致无 pyarrow 环境失败（DESIGN Q1） | T380-56 前置判定；失败改独立顶层包 |
| 2 | AR 常数/`c_t` 定义未核（R-D1 后续） | E2 验证记录；未核前该估计量标 `[待核]` |
| 3 | 39 个 OOS 点功效不足 | 不选窗（D3），IJR 仅诊断 |
| 4 | 分钟数据无逐笔方向 | 结论全 `[区间]`，BVC 偏差写入限制表 |
| 5 | 2023-04 后无分钟数据 | c 时间外推标 `[代理推断]` |
| 6 | 校准把风险改小 | `c_stress = max(0.5, upper)`（T380-50 守护） |
| 7 | 默认口径 4 倍不一致被误读 | §9.5 诊断量随报告输出 |
| 8 | ST 股 5% 涨跌幅规则文本未核实（design §20-Q2） | 不进代码硬编码；涨跌停判定仅用 h==l/零量（§2.7），规则文本在报告标注 `[未核实]` |
| 9 | 2023-03 为不完整月（止于 03-30，design §20-Q3） | 按裁决**保留但标记**：21 个交易日计入 λ 面板，`evidence_warnings` 记 `partial_month=2023-03` |

---

## §9 步骤 6 review 记录（实施文档幻觉消除）

> **日期**: 2026-11-19
> **对象**: 本文件 v1.0（步骤 5 产出）→ 修订后为 v1.1
> **方法**: ① 全文逐节对照源代码锚点（脚本/`effect_size`/`data_contract`/`backtest/__init__`/`pyproject`）
> 逐位核验；② 与设计 v1.1 条款级对账（§3/§4/§7/§9/§10/§11/§13/§16/§18/§20）；
> ③ 计数与算术复算（56 例分组、定点值、半衰期）；④ 工程声明核实（pytest 8.3.4 安装源码
> `_pytest/main.py` 通配符行为，等价方法论阶段 5 轨道 B）。学术引用均继承步骤 4 核实结果，
> 本文件无新增学术声明。

### 9.1 发现与处置（3 P2 + 7 P3，无 P1）

| ID | 级别 | 发现 | 处置 |
|----|------|------|------|
| R-E1 | P2 | **容量复用机制空洞**：§2.10 `run_calibration(cfg)` 无法在不违反 design §3.1「禁止 Shell→scripts」与 §2.11「默认路径不进入新代码」的前提下复用脚本内 `capacity_from_p95`/`breakeven_aum`（script `:192`/`:199`）；T380-41「同一函数」无实现路径 | §2.10 签名改 `run_calibration(cfg, capacity_fn=None, breakeven_fn=None)` 依赖注入；脚本 `--calibrate` 分支懒 import 后注入；T380-41 断言改 monkeypatch 随动 |
| R-E2 | P2 | **DecayModel 端口无具体实现类**：§2.10 `build_pipeline` 返回 `'decay': ...` 无所指（design §4 亦仅 Protocol）；§2.8 只有模块级函数 `retention(horizons, rho)` 不满足端口签名 | §2.8 补 `ExponentialDecay(rho)` 具体类；§2.10 装配为 `'decay': ExponentialDecay(rho)`；design §7.1 同步（v1.2） |
| R-E3 | P2 | **验收命令在目标环境不可用**：§7.1 `pytest tests/test_execution_*.py` — pytest 8.3.4 `_pytest/main.py` 对位置参数无 glob 展开（仅 `--ignore-glob`/norecursedirs 用 fnmatch），PowerShell 5 亦不为外部命令展开通配 → 报 file not found | 改为 9 个测试文件显式枚举，并注明原因 |
| R-E4 | P3 | §4「引入重依赖只为 erf」失实：`scipy>=1.7.0` 已是核心依赖（`pyproject.toml:29`），不构成"引入" | 改为真实理由：core 层零第三方纪律（仅 numpy）；§3.2 措辞同步（"不进入 core"） |
| R-E5 | P3 | T380-50 断言弱于 D2：design §9.4 为 `c_stress = max(0.5, c_ci_upper)`，原文写 `>= max(0.5, c_point)`（point ≤ upper 恒成立，断言过弱放过退化实现） | 改等值断言 `c_stress == max(0.5, c_ci_upper)` |
| R-E6 | P3 | T380-56 缺 design §16.5 的 `has_pyarrow() is False` 断言 | 已补 |
| R-E7 | P3 | design §16.2 与本文 §5.1 组成不一致：设计"容量复用 4 / λ 3"未列 κ 单调、主值 min、c 三档；本文"复用 2 / λ 2 / κ 1 / 主值 1 / c 1"；两组总数均 10（总 56 不变） | design §16.2 重写为 2+3+2+3 并注明对齐来源（v1.2） |
| R-E8 | P3 | design §20 开放问题 Q2（ST 5% 规则未核实）/ Q3（2023-03 尾月）未带入 §8.2 | §8.2 增风险 8/9：ST 规则不硬编码、尾月保留但标 `partial_month` |
| R-E9 | P3 | `shell/report.py` 在 §3.7 布局与 design §3.3 中均有，但本文 §2 无接口定义；Markdown 页脚（config_hash/evidence_level，design §14）未显式 | 新增 §2.12 接口（仅落盘不计算） |
| R-E10 | P3 | design §9.3 校准纪律（λ `p<0.05` 纳入、中位数填充、`lambda_fill_ratio>30%` → 降级 `[区间]`）未在本文出现；`net_curve` 未注明 h=1/60 无成本口径（design §10.2） | §2.5 补"校准纪律"段；`net_curve` 补 docstring |

### 9.2 核实通过项（抽样列示，全部逐位核对）

| 项 | 结果 |
|----|------|
| 脚本行锚点 `SQRT_C:60` / `LINEAR_K:61` / `CAP_LEVELS:62` / `sig_m.clip(0.005,0.20):121` / `impact_panel:143` / `p_eff:151` / sqrt `:154` / linear `:157` / `capacity_from_p95:192` / `breakeven_aum:199` / argparse 变量 `ap:237` / 默认输出 `out/capacity_impact.json:240` | PASS |
| 既有符号 `DataContractError:50` / `FieldReader:219` / `_jsonable:272` / `_freshness_check:543` / `check_data_contract:926` / `newey_west_se:70`（effect_size.py，import scipy 但 scipy 为核心依赖，不在 core 内使用） | PASS |
| `backtest/__init__.py` 恰 13 处 from-import（`:16-56`）；全 `backtest/` 无 pyarrow 实引用（仅 docstring 提及）→ Q1 父包重导入风险实测面收窄，仍由 T380-56 判定 | PASS |
| `pyproject.toml:56` 为 `all` 行（追加 pyarrow 目标正确）；`scipy`/`statsmodels` 均已在核心 dependencies（"不新增"表述成立） | PASS |
| 定点算术：T380-02 `0.5·0.02·√0.01=1e-3`(10bp)、T380-03 `0.025·0.01=2.5e-4`(2.5bp)、T380-17 `0.01/1e8=1e-10`、T380-19 `Φ(1.96)≈0.975`、T380-28 `ln0.5/ln0.9≈6.579` | PASS |
| 公式继承：AR 乘积型 `S²=4·E[(c_t−η_t)(c_t−η_{t+1})]`、`c_t=ln(close)`（R-D1 修复未回退）；块长简化式 docstring 诚实化（R-D5 修复未回退）；量纲纪律 `impact_bps=λ·p·1e4` | PASS |
| 计数：§5.1 分组 10+8+8+8+6+10+2+3+1=56；§3.7 布局 14 文件与 design §3.3 一致；1929+56=1985 | PASS |
| 配置一致性：`sigma_clip(0.005,0.20)`、`windows(24,36,48,60)`、`kappa=1.5`（κ∈{1.0,1.5,2.0} 主值）、`p_cap=0.10`/`d_max=5`、`lambda_p_threshold=0.05`、`horizons(1,5,10,20,60)`、`spread>0.30` 降级、plateau 定义 — 均与 design §10-§12/脚本一致 | PASS |
| 架构测试口径：T380-53/54/55 与 design §16.4 逐字一致 | PASS |
| 测试文件名无冲突：`tests/` 下现无任何 `test_execution_*`（9 个全为新文件） | PASS |
| T380-51/52 快照守护与脚本现有确定性输出（无随机源、`payload` 键 `meta/results`）兼容 | PASS |

### 9.3 结论

**PASS_WITH_FIXES**：无 P1（无公式幻觉、无不可归因引文、无接口与源码冲突）；
3 项 P2 全部为**机制/契约缺口**（非事实错误），已按处置列修复完毕；
7 项 P3 为理由失实/断言强度/文档对齐。修复后实施文档与源代码、设计文档 v1.2
三方一致，可进入步骤 7（checklist）。

**遗留至实施确认**：design §20-Q1（父包重导入，T380-56 判定）、Q2（ST 规则文本，
仅报告标注）、Q3（2023-03 尾月标记，§8.2 风险 9）。
