# DESIGN v3.9.3 — alpha 衰减模型选择（FO-1）

---
id: v393-alpha-decay-model-DESIGN
type: design
version: 1.1
status: verified
date: 2026-11-20
depends: [v393-alpha-decay-model-RESEARCH]
upstream: null
---

> **版本**: v1.1（2026-11-20；Step 3 产出 + Step 4 异构复审通过，见 §12）
> **批次**: v3.9.3（P-002，P0）
> **批次档位**: **T1**（改动路径命中 `backtest/`、`scripts/`、`tests/` → Layer-1）
> **基于调研**: [RESEARCH.md](./RESEARCH.md) **v1.3 verified**（§9 补充调研 + §11 异构复审 PASS_WITH_FIXES）
> **采纳裁决**: RESEARCH §9.5 三条建议裁决（U-1 / U-2 / U-5）全部写死，见 §2
> **上游约束**: [DESIGN_EXECUTION_CAPACITY_V3.8.0.md](../../docs/private/DESIGN_EXECUTION_CAPACITY_V3.8.0.md) §7 / §10.2；[AUDIT.md](../v392-calibration-unit-fix/AUDIT.md) §5（FO-1）
> **实施归**: Step 9（TDD，先红后绿）

---

## 1. 设计目标

### 1.1 目标

| # | 目标 | 对应调研裁决 |
|---|------|-------------|
| G1 | 把衰减的**估计对象**从「组合日超额 AR(1)」改为「形成后累计 alpha 曲线 `A(h)`」，消除对象错配 | RESEARCH §3.1.3 / §9.3.1 |
| G2 | 用**单位时间 alpha 之比**定义乘子 `m(h)=A(h)/[A(h_m)·h/h_m]`，使 `m(h_m)=1` 为构造性归一，无衰减时 `m≡1` | RESEARCH §9.3.1 |
| G3 | 用**单参数累计比** `m(h;φ)=(h_m/h)(1−φ^h)/(1−φ^{h_m})` 作为参数形式，禁止 `exp(λ(h_m−h))` | RESEARCH §9.4.1 |
| G4 | 按形成期做 **stationary bootstrap** 得 `m(h)` 与 `net(h)` 的 95% CI，三态判定规则预注册 | RESEARCH §9.3.3 / §9.4.2 |
| G5 | 月长口径统一：固定 `h_m=20`，`alpha0 := mean A(20)`，`cost(h)` 沿用 `(20/h)` | RESEARCH §9.3.2（方案 B） |
| G6 | 默认 `out/capacity_impact.json` SHA256 逐位不变；新估计只进校准/诊断路径 | RESEARCH §6.2 #2 |

### 1.2 非目标（明确不做）

- 不改 `DecayModel.retention(horizons)` 端口契约（[ports.py L57-L64](../../backtest/execution/ports.py#L57-L64)）；
- 不改默认路径 `out/capacity_impact.json` 的任何既有键与数值；
- 不改 `cost(h)` 的费率、参与率上限、冲击模型选择；
- 不实现截面 T+1 reversal（P-003）、不做股票×月重采样（P-010）；
- 不把 h>20 的外推读数纳入验收；
- 不依据本批结论修改 P-002 验收原文（RESEARCH §9.4.4 仅提出推论，改动需用户裁决）；
- 不实现 S2 月频 IC 佐证（RESEARCH §6.1 S2 / `compute_ic_decay`）——它只作方向一致性检查、非验收路径，显式延后为校准报告的可选增强（v1.1 复审 S1）。

---

## 2. 关键决策（采纳 RESEARCH §9.5 建议裁决）

### D1（U-1）估计对象与乘子定义 — **采纳**

**决策**：对每个形成期 `t0`（月末），以**形成时权重、之后不再调整**计算 `h=1..60` 日累计超额 `A_{t0}(h)`；对 39 期取均值得 `A(h)`（中位数并列展示）。乘子定义为

```
m(h) = A(h) / [A(h_m) · h / h_m] = [A(h)/h] / [A(h_m)/h_m]
```

- 经济含义：每 `h` 日调仓一次的**单位时间毛 alpha** ÷ 月持有基准的**单位时间毛 alpha**。
- `R(h)=A(h)/A(h_m)`（累计保留率）**仅作展示**，不乘月 alpha——它随 h 单调增，会把「时间累积」误当「保留率」（RESEARCH §9.3.1 候选表）。
- **声明**：`m(h)` 的归一化式形是**本仓约定（E3 代数）**；GP 2013 / Northfield 只支撑「衰减 = 信号均值回归速度、衰减与成本联合决定最优换手」这一方向，文献**未给出**该归一化式（RESEARCH §9.3.1 / §11 H1）。

**CI 构造**（预注册）：39 个形成期是独立单元，期内日频重叠不产生独立样本 →
按形成期 stationary bootstrap（Politis & Romano 1994）：期望块长 `b=3`，敏感性 `b=1`（近似 iid）/ `b=6`，重采 1000 次，取 2.5%/97.5% 百分位。

### D2（U-2）函数形式与判定规则 — **采纳**

**决策**：参数形式写死为累计比

```
m(h;φ) = (h_m/h) · (1−φ^h)/(1−φ^{h_m}),   0 < φ ≤ 1
半衰期 = ln2 / ln(1/φ)
```

- `φ=1` → `m≡1`；`φ→0⁺` → `m=h_m/h`（alpha 全部集中在第 1 日）。
- `φ` 估计：在 `h∈{1,…,h_m}` 上对非参 `m̂(h)` 做非线性最小二乘（网格初始化 `φ∈[0.01,1]`，步长 0.001，再局部精化），**预注册**并只在 Step 9 实施一次。
- **禁止** `exp(λ(h_m−h))`：它不是累计量的映射，φ=0.95 时 h=5 高估 53%、h=1 高估 70%（RESEARCH §9.4.1）。
- 双曲 / 非参曲线只作敏感性附表，不作主口径。

**判定规则（预注册，实施阶段不得改）**：

| 观测（h=5 / h=10） | 结论表述 | 容量取用 |
|------|----------|----------|
| `m` 的 95% CI **上界 < 1** | 后置衰减成立 | 用 point 或 CI 上界 |
| CI **覆盖 1** | 未检出衰减 | `m=1` 作**零衰减基准情景**；保守容量用 **CI 下界** |
| CI **下界 > 1** | 前置 alpha 成立 | 用 CI 下界（保守） |

- **`m=1` 不是上界**：`net(h)=aum·alpha0·m(h)−cost(h)` 对 `m` 单调递增；前置时 `m>1`（容量被低估）、后置时 `m<1`（容量被高估）（RESEARCH §9.4.2）。
- **表述纪律**：禁止写「无衰减」「alpha 不衰减」；只能写「未检出衰减」（Altman & Bland 1995；Wasserstein & Lazar 2016）。
- `m(h_m)=1` **不参与检验**（构造性）。

### D3（U-5）月长约定与 `alpha0` 基准 — **采纳方案 B**

**决策**：固定 `h_m = 20`（交易日），`alpha0 := mean_{t0} A_{t0}(20)`。

| 量 | 定义 | 单位 | 来源 |
|----|------|------|------|
| `A(h)` | 形成后 h 日累计超额（形成时权重冻结） | 收益（小数，h 日累计） | 日频 `excess_d` + 权重 |
| `h_m` | 月长约定常量 | 交易日 = 20 | 本设计写死 |
| `alpha0` | `mean A(20)` | 每 20 交易日收益 | 39 期均值 |
| `m(h)` | `A(h)/[A(20)·h/20]` | 无量纲 | 派生 |
| `cost(h)` | `(20/h)·aum·turnover_m·2·(FEE_BPS+impact_bps)/1e4` | 元 / 月 | [panels.py L609-L613](../../backtest/execution/shell/panels.py#L609-L613) |
| `net(h)` | `aum·alpha0·m(h) − cost(h)` | 元 / 月 | 派生 |

- **派生产物（必须登记）**：`alpha0` 由 `ex_m.mean()=0.002629` 改为 `mean A(20)`，**E1 数值基线在 Step 9 重算**；旧日历月均值保留为对照字段 `alpha0_calendar`（仅诊断，不参与 net）。
- 方案 A（实际 `days_by_month`）与方案 C（混用）的否决理由见 §5.4。

### D4（U-4）接口与默认 SHA — **采纳最小侵入**

**决策**：

1. `DecayModel` Protocol **不变**；新增两个实现类（§4.2）：
   - `AnchoredDecay(phi, h_m=20)`：`retention(h)` 返回 `m(h;φ)`；
   - `EmpiricalDecay(curve)`：直接返回非参 `m̂(h)`（缺失 h 线性插值，`h_m` 处强制 1）。
2. **默认路径**（不带校准开关）继续使用 `ExponentialDecay(rho)` 与 `alpha0 = ex_m.mean()`，**不写任何新键** → `out/capacity_impact.json` SHA 逐位不变。
3. **校准路径**新增独立工件 `out/v393_decay_curve.json` + `out/v393_decay_curve.md`，不覆盖 `out/v392_calibration.*`、不覆盖默认 JSON。
4. 新键命名一律带 `decay_` / `alpha0_anchored` 前缀，避免与既有报告键冲突。

### D5（U-3）`net(h)` 报告形态 — **采纳**

**决策**：所有 h 输出 `{"point","lo","hi"}` 三值（由 bootstrap 重采样 `A` 曲线后重算）；`plateau` 用 `net` 的 bootstrap 标准差；h=5/10/20 全部报告，`h*` 仅作摘要，禁止只报使 `net>0` 的 h。

---

## 3. 架构设计

### 3.1 整体数据流

```
日频 excess_d + 形成期权重(冻结)
        │
        ├─► A_by_period[t0][h]  (h=1..60)
        │        │
        │        ├─► A(h)=mean_t0 A_t0(h) ──► m̂(h)=A(h)/[A(20)·h/20]  (非参)
        │        │                                    │
        │        │                                    ├─► EmpiricalDecay(curve)
        │        │                                    └─► fit φ ─► AnchoredDecay(φ)
        │        │
        │        └─► stationary bootstrap(b=3, 1000) ──► m_lo/m_hi, net_lo/net_hi
        │
        ├─► alpha0_anchored = mean A(20)
        └─► cost(h)（沿用 panels 口径）

net(h) = aum · alpha0_anchored · m(h) − cost(h)   →  point / lo / hi
```

### 3.2 模块划分

| 模块 | 职责 | 输入 | 输出 | 依赖 |
|------|------|------|------|------|
| `core/decay.py`（扩展） | 纯函数：`decay_multiplier` / `fit_phi` / `AnchoredDecay` / `EmpiricalDecay` / `net_point` / `net_ci` | `A` 曲线、φ、成本表、bootstrap 样本 | `m(h)`、φ、net 三值 | numpy（既有） |
| `effect_size.py`（**复用，不新增**） | `stationary_bootstrap_indices(n, n_bootstrap, block_size, seed)` 已实现 Politis-Romano 索引矩阵；百分位 CI 用 `np.quantile` | 期数、块长、重复数、seed | 索引矩阵 | numpy（既有） |
| `shell/panels.py`（扩展） | 组装 `A_by_period` 与 `alpha0_anchored`，只在校准分支写新键 | `portfolio` 的日频超额与权重 | `decay_*` 字段 | 上述两模块 |
| `shell/runner.py`（扩展） | 校准分支装配 `DecayCurve` 与 net 三值；默认分支零改动 | panels 输出 | 校准工件 | 上述模块 |
| `scripts/verify_capacity_impact.py`（扩展） | 保留形成期权重并输出 `A_by_period` | 原始日频数据 | `A_by_period` | 既有 loader |

### 3.3 控制流

`--calibrate` 分支：panels 产出 `decay_a_by_period` → runner 计算 `A(h)`/`m̂(h)`/`φ`/bootstrap CI → 写 `out/v393_decay_curve.json|md`。默认分支：不进入上述任何计算，输出与 v3.9.2 逐位一致。

---

## 4. 接口定义

### 4.1 纯函数（`backtest/execution/core/decay.py`）

```python
def decay_multiplier(curve, h_m=20):
    """非参乘子 m(h)=A(h)/[A(h_m)·h/h_m]；返回 {h: m}，强制 m[h_m]=1。"""

def anchored_multiplier(phi, horizons, h_m=20):
    """参数乘子 m(h;φ)=(h_m/h)(1−φ^h)/(1−φ^{h_m})；φ==1 → 全 1。"""

def fit_phi(curve, h_m=20, grid=(0.01, 1.0), step=0.001):
    """在 h∈{1..h_m} 上对非参 m̂(h) 做最小二乘，返回 (phi, sse)。"""

def net_point(alpha0, aum, m_by_h, cost_by_h):
    """net(h)=aum·alpha0·m(h)−cost(h)；点估计 {h: float}（未重采曲线）。"""

def net_ci(a_boot, m_boot, aum, cost_by_h):
    """由 bootstrap 样本算 {h: {"point","lo","hi"}}；a_boot/m_boot 为 (reps,) 样本，
    point 取原始（未重采）曲线（v1.1 复审 S2：CI 需要分布入参，点估计接口不足以产出 lo/hi）。"""
```

### 4.2 端口实现（同一模块）

```python
class AnchoredDecay(object):
    name = "anchored"
    def __init__(self, phi, h_m=20): ...
    def retention(self, horizons): ...   # 返回 m(h;φ)

class EmpiricalDecay(object):
    name = "empirical"
    def __init__(self, curve, h_m=20): ...
    def retention(self, horizons): ...   # 线性插值；h_m 强制 1
```

### 4.3 bootstrap（**复用** `backtest/effect_size.py`，不新增模块）

```python
# 已存在：[effect_size.py L128-L160](../../backtest/effect_size.py#L128-L160)
stationary_bootstrap_indices(n, n_bootstrap=1000, block_size=None, seed=0) -> np.ndarray

# 调用约定（预注册）
idx = stationary_bootstrap_indices(39, n_bootstrap=1000, block_size=3, seed=0)
# 以 idx 重采 39 个形成期的 A_t0(·) → 重算 A(h)/m(h)/net(h)
lo, hi = np.quantile(samples, [0.025, 0.975])   # 百分位 CI，不新增函数
```

- 敏感性：`block_size=1`（近似 iid）/ `block_size=6`；`seed` 固定为 0 以保证可复现。
- 该函数已支持 `block_size=1` 退化为 iid 抽样（L151-L152），无需另写分支。

### 4.4 校准工件（`out/v393_decay_curve.json`）

```json
{
  "h_m": 20,
  "n_periods": 39,
  "alpha0_anchored": 0.0,
  "alpha0_calendar": 0.002629,
  "phi": 1.0,
  "phi_status": "fitted | unidentified",
  "decay_source": "empirical | prior",
  "horizons": [5, 10, 20],
  "m": {"5": {"point": 0, "lo": 0, "hi": 0}, "10": {}, "20": {}},
  "a": {"5": {"point": 0, "lo": 0, "hi": 0}, "10": {}, "20": {}},
  "net": {"5": {"point": 0, "lo": 0, "hi": 0}, "10": {}, "20": {}},
  "boot": {"block": 3, "reps": 1000, "sensitivity": [1, 6], "seed": 0},
  "verdict": {"5": "posterior | flat | anterior", "10": "..."},
  "evidence_warnings": []
}
```

> **verdict 术语映射（v1.1 复审 S5）**：`posterior` = 后置衰减（`m<1`，CI 上界<1）｜`flat` = 未检出衰减（CI 覆盖 1）｜`anterior` = 前置 alpha（`m>1`，CI 下界>1）——对应 RESEARCH §9.4.2 判定表；`posterior` 在统计语境另有「后验」义，本工件中仅取「后置」。

---

## 5. 替代方案

### 5.1 方案 A：累计 alpha 曲线 + 单参数累计比（**选择**）

- 描述：`A(h)` 非参曲线 + `m(h;φ)` 参数化 + 按形成期 block bootstrap。
- 优点：对象正确（信号剩余价值）、量纲自洽（`m(20)=1` 构造性）、不确定性按真实独立单元计、参数量最少（1 个 φ）。
- 缺点：依赖形成期权重冻结的实现；39 期 CI 可能偏宽。
- 选择理由：同时满足 RESEARCH §6.2 的八条约束，且不违反零新增依赖。

### 5.2 方案 B：`m(h)=exp(λ(h_m−h))` 直接拟合（**否决**）

- 描述：对 `m̂(h)` 拟合指数衰减。
- 否决理由：**数学错误**——它把「单期保留率」的指数式误用于「累计量之比」，与 `m(h_m)=1` 仅在 h=h_m 处巧合通过；φ=0.95 时 h=5 高估 **53%**（2.158 vs 1.411）、h=1 高估 **70%**（2.650 vs 1.559）（RESEARCH §9.4.1，已 FALSIFIED 并登记 RESEARCH §5.3）。

### 5.3 方案 C：沿用组合日收益 AR(1) 的 `rho**h`（**否决**）

- 描述：保持现状，仅调 `rho` 的估计窗口。
- 否决理由：**对象错配**——`rho` 衡量日频反转/噪声，不是 alpha 的期限结构；实测 `rho=0.1142` → 半衰期 0.32 交易日 → `rho^20≈1.4e-19`，低于 h=20 门槛 0.148 达 18 个数量级，`net` 恒 ≈ `−cost`（FO-1 本体，RESEARCH §3.1.2 / §3.0-D4）。

### 5.4 月长方案 A / C（**否决**）

| 方案 | 否决理由 |
|------|----------|
| A 实际月长 `days_by_month(t)` | 量纲严格但 h 网格随月变化，接口与回归面扩大；且 `days_by_month` 目前仅用于面板覆盖（[panels.py L183/L193](../../backtest/execution/shell/panels.py#L183-L193)），引入会改变成本口径与缓存代际，超出本批最小范围 |
| C 混用（`h_m=20` + 日历月 `alpha0`） | `m(20)≠1`，构造性归一被破坏，量纲不一致——**必须拒绝** |

---

## 6. 数据结构

```python
@dataclass(frozen=True)
class DecayCurve:
    h_m: int
    horizons: Tuple[int, ...]
    a_mean: Mapping[int, float]      # A(h) 非参
    m_point: Mapping[int, float]     # m̂(h)
    m_lo: Mapping[int, float]
    m_hi: Mapping[int, float]
    phi: float
    phi_status: str                  # "fitted" | "unidentified"
    n_periods: int
    boot: Mapping[str, object]
```

---

## 7. 错误处理

| 错误场景 | 处理方式 | 用户可见信息 |
|---------|---------|------------|
| `A_by_period` 期数 <10 | 走 S3 文献先验：半衰期 6/12 个月 ≈ 126/252 交易日，`φ_prior = 2^(−1/HL)`（HL 为先验半衰期交易日数；v1.1 复审 S4），`decay_source="prior"` | `evidence_warnings: decay_prior_fallback` |
| 期数 10 ≤ n < 39 | 正常估计，但低于预注册样本量 39，不作豁免解释（v1.1 复审 S3） | `evidence_warnings: decay_small_sample` |
| `A(h)` 出现 NaN / 符号翻转（`A(20)<=0`） | 不估 φ，`phi_status="unidentified"`，`m` 输出 NaN 并标注 | `decay_curve_unidentified` |
| φ 拟合失败（网格无有限 SSE） | `phi=1.0` + `phi_status="unidentified"` | `decay_phi_fit_failed` |
| bootstrap 重采异常 | 回退解析近似（按 39 期 `t` 分布），标注方式 | `decay_ci_analytic_fallback` |
| 默认路径 | 不进入任何新计算 | 无（SHA 不变） |

---

## 8. 不变式（Invariants）

1. **构造性归一**：`m(h_m) == 1`（容差 1e-12），对所有实现与所有 CI 重采样。
2. **平坦极限**：`φ=1` ⇒ `m(h)=1`，∀h。
3. **退化极限**：`φ→0⁺` ⇒ `m(h)=h_m/h`。
4. **单调性**：`0<φ<1` 时 `m(h)` 对 h 严格递减，且 `h<h_m` 时 `m>1`。
5. **默认零影响**：不带校准开关时，`out/capacity_impact.json` 的键集合与数值逐位不变。
6. **无前视**：`A_{t0}(h)` 只用 `t0` 之后的收益；权重在 `t0` 已知；不得用全样本均值回填历史。
7. **单位单一**：`alpha0`、`A`、`cost`、`net` 同处「元 / 月」或「收益 / 期」，见 §2 D3 量纲表。
8. **样本诚实**：CI 只按 39 个形成期重采样，禁止按日计独立样本。

---

## 9. 幻觉抑制审查（Step 4 Review）

> 本节为 Step 4 复审入口；Step 3 产出时保持未勾选状态。**已于 2026-11-20 由 Step 4 异构复审逐项核验通过（见 §12，结论 PASS_WITH_FIXES）**。

### 9.1 设计基于已验证的调研结论

- [x] 所有设计决策可追溯到 RESEARCH v1.3（D1→§9.3、D2→§9.4、D3→§9.3.2、D4→§6.2/§9.5、D5→§6.4 U-3）
- [x] 无未经验证的假设（`m(h)` 式形已声明为本仓代数，不冒充文献结论）
- [x] 无论证驱动的归因扭曲（`exp` 形式已标 FALSIFIED、`m=1` 已改称基准情景）

### 9.2 替代方案审查

- [x] 至少列 2 个替代方案（已列 B/C 及月长 A/C）
- [x] 每个替代方案有明确的否决理由

### 9.3 职责边界审查

- [x] 职责边界清晰：只换衰减估计对象与口径，不动冲击模型、成本费率、端口契约
- [x] 不越界吞并 P-003 / P-010 等其他批次范围

### 9.4 预注册审查（Nosek 2018）

- [x] 估计量、φ 模型类、判定三态、bootstrap 参数、报告字段均已写死（§2 / §4.4）
- [x] 实施期改动须登记 deviation 并重跑全部读数

---

## 10. 对实施的输入

### 10.1 关键工程约束

1. Python 3.9 语法、零新增依赖（仅 numpy/pandas 既有栈）；`__all__` 只增不改（v3.9.2 A-3 教训）。
2. 新增函数必须为纯函数（无 IO、无全局状态），bootstrap 支持 `seed` 以保证可复现。
3. 默认分支零改动：不得在默认路径写 `decay_*` / `alpha0_anchored` 键。
4. `scripts/verify_capacity_impact.py` 需**保留形成期权重**（当前 L179-L233 未保留，RESEARCH §3.1.4）——这是本批唯一的取数改造点。
5. 校准工件独立文件：`out/v393_decay_curve.json|md`，不覆盖既有工件。
6. Step 9 须重算 E1 基线（`alpha0` 口径变化），并在实现文档登记新旧对照。

### 10.2 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| 39 期样本小，CI 过宽覆盖 1 | 预注册三态表述；同时报非参与拟合与敏感性 b=1/6；不把「未检出」写成「无衰减」 |
| 结果被成本主导（h=5 需 `m≥0.592`） | 同时报 `net/cost` 比与 CI；不承诺容量 |
| 事后挑选函数形式/窗口 | §2 预注册；敏感性附表全公开；改动须登记 deviation |
| 形成期权重未保留导致无法算 `A(h)` | §10.1 #4 列为实施首项；Step 9 红测先行 |
| `alpha0` 口径变化破坏可比性 | 保留 `alpha0_calendar` 对照；实现文档登记新旧值 |
| 默认 SHA 被新增键污染 | 测试断言默认路径 JSON 键集合与 SHA 逐位不变 |

### 10.3 验收①推论（必须随实施披露）

正确口径下 `m(20)=1` 为构造性 ⇒ `net(20)=aum·alpha0−cost(20)=26.29M−3.89M≈+22.4M>0`（E1 输入 + E3 代数）。**P-002 验收① 在修正口径下几乎恒成立**，真正的判别力在 h=5 / h=10 的 `m(h)` 与 CI，以及是否出现 `m<1`（后置）。本设计**不改 P-002 原文**，仅要求实施文档与 CHECKLIST 显式披露该推论（RESEARCH §9.4.4）。

---

## 11. 未决项登记（四元块）

- **U-1 `m(h)` 定义与量纲** — **本设计已关闭**
  - 判据：`A(h)`/`m(h)`/`R(h)` 关系与单位写死，`m(h_m)=1` 构造性，量纲表（§2 D3）通过 Step 4 Review。
  - 当前结论：D1 + D3；证据 E3 + E1 + T1。
  - 重审触发：若 Step 9 发现 `A_by_period` 不可得（形成期权重无法保留）→ 转 S3 先验并新开未决项。

- **U-2 函数形式与「不显著」处置** — **本设计已关闭**
  - 判据：三条预注册（累计比形式、三态判定、禁止「无衰减」）全部写入 §2 D2。
  - 当前结论：φ 单参数累计比 + 非参并列；`m=1` 仅称基准情景。
  - 重审触发：实施期若需改判定规则 → 必须登记 deviation 并重跑（视为新批次）。

- **U-3 `net(h)` 报告形态** — 保留观察（E4）
  - 判据：`net` 输出 point/lo/hi，CHECKLIST 有对应验收项。
  - 当前倾向：D5。
  - 证据等级：E4（方法判断，待 Step 9 验证）。

- **U-4 接口与兼容性** — 保留观察（E3）
  - 判据：`DecayModel.retention` 可满足；默认 SHA 不变；`__all__` 不越界。
  - 当前倾向：D4。
  - 证据等级：E3（读码）。

- **U-5 月长约定** — **本设计已关闭**
  - 判据：`h_m`、`alpha0` 定义、三处成本/alpha 同口径写死。
  - 当前结论：方案 B（`h_m=20`，`alpha0 := mean A(20)`）；`alpha0` 基线变化登记为派生产物（§2 D3 / §10.1 #6）。
  - 重审触发：若需与日历月口径严格可比 → 新开方案 A 批次。

**11.2 决策矩阵**：不启用。U-5 的 A/B/C 为可逆（Type-2）选择，已在 §5.4 直接裁决；D2 的 φ 形式由代数证明排除替代项（非并列权衡）。

---

## 12. v1.1 Step 4 复审记录（异构基座 pass，2026-11-20）

> **异构声明**: DESIGN §1-§11 由撰写会话产出，本 pass 在独立新会话中由**不同模型基座**执行复审（RULE-5 异构；基座家族信息以会话记录为准，复审方不自证撰写方基座）。
> **单向权限**: 复审只作标记（§12.2 发现表）；修正为标记后的最小修复落盘，D1-D5 与验收①推论的实质结论未被复审方改写。
> **复审对象**: DESIGN v1.0 全文（§1-§11）。
> **执行方式**: 全文重读 + D1-D5/G1-G6 逐条回溯 RESEARCH v1.3 对应章节 + 公式/数值独立复算 + 接口可行性对照仓内代码（`effect_size.py` / `ports.py` / `decay.py` / `panels.py` 锚点复用本批 Step 1-2 已核验结果）+ 门禁 a-d。
> **结论: PASS_WITH_FIXES** —— 7 项发现（S1-S7）全部 P3 级，均已最小修复；无 P2 及以上；无遗留阻断项。

### 12.1 视角 × 探针矩阵（沿用 v3.8.0 §19 形态）

| 视角 | 探针 | 结果 | 说明 |
|------|------|------|------|
| V1 公式与计量正确性 | P1 独立复算 | PASS | `m(h)`/`m(h;φ)` 与 RESEARCH §9.3.1/§9.4.1 一致；φ=0.95 时 exp 形 h=5 高估 53.0%、h=1 高估 70.0%；`m(20)=1` 构造性（分子分母同式，浮点精确成立）；φ→0⁺ → m=h_m/h、φ→1 → m≡1；单调性由 `e^(−ah)(1+ah)<1 (h>0, a=\|lnφ\|)` 解析成立 → 不变式 4 成立；`rho^20=1.423e-19` vs 门槛 0.148 = 18.0 个数量级；net(20)=26.29−3.891=+22.399M |
| V2 可追溯性 | P2 D1-D5/G1-G6 回溯 RESEARCH v1.3 | PASS（1 修复 → S1） | 全部决策可回溯至 RESEARCH 对应章节；唯一缺口：RESEARCH §6.1 S2（月频 IC 佐证）被静默省略 → 已在 §1.2 显式延后 |
| V3 接口可行性 | P3 对照仓内代码 | PASS（1 修复 → S2） | `stationary_bootstrap_indices` 签名/位置/iid 退化（L128-L160、L151-L152）✓；`AnchoredDecay`/`EmpiricalDecay` 满足 `DecayModel` 协议（name + retention）✓；缺陷：`net_curve_ci` 只有点估计入参，无法产出 lo/hi，与 D5 承诺不匹配 → 拆为 `net_point` + `net_ci` |
| V4 一致性与边界 | P4 错误处理/量纲/范围/交叉引用 | PASS（4 修复 → S3/S4/S6/S7） | 量纲表自洽（cost「元/月」vs alpha0「每 20 交易日」的 ~0-5% 近似为方案 B 已声明折衷，RESEARCH §9.3.2）；缺口：10≤n<39 无样本提示（S3）、prior 半衰期无交易日换算（S4）、D3 错引 §5.3（S6）、§5.2/§5.3 跨文档引用未限定与 DESIGN 自身同名章节混淆（S7）→ 均已补 |
| V5 预注册与决策效度 | P5 预注册完备性 + 判定方向 | PASS（1 修复 → S5） | 估计量/模型类/三态判定/bootstrap 参数（b=3、1000 次、seed=0、敏感性 1/6）/报告字段全部写死；deviation 条款到位；verdict 术语补映射（S5）；判定方向与 RESEARCH §9.4.2 一致且偏保守（保守容量取 CI 下界） |

### 12.2 发现清单

| ID | 级别 | 章节 | 缺陷 | 处置 |
|----|------|------|------|------|
| S1 | P3 | §1.2 | RESEARCH §6.1 S2（月频 IC 佐证）被静默省略，未纳入也未声明延后 | 已修复：非目标显式登记延后（非验收路径） |
| S2 | P3 | §4.1 / §3.2 | `net_curve_ci(alpha0, aum, m_by_h, cost_by_h)` 输入只有点估计，无法产出 lo/hi，与 D5 承诺不匹配 | 已修复：拆为 `net_point` + `net_ci(a_boot, m_boot, …)`，§3.2 同步 |
| S3 | P3 | §7 | 期数 10≤n<39 时静默缩样本，无警告 | 已修复：补 `decay_small_sample` 警告行 |
| S4 | P3 | §7 | prior 半衰期「6/12 月」无交易日换算与 φ_prior 推导，Step 9 无法直接实施 | 已修复：补 126/252 交易日 + `φ_prior = 2^(−1/HL)` |
| S5 | P3 | §4.4 | verdict 术语 `posterior/flat/anterior` 与 RESEARCH 判定表的中文映射未注明（`posterior` 易与「后验」混淆） | 已修复：JSON 下补映射注释 |
| S6 | P3 | §2 D3 | 「否决理由见 §5.3」系笔误，月长方案 A/C 在 §5.4 | 已修复：改指 §5.4 |
| S7 | P3 | §5.2 / §5.3 | 「登记 §5.3」「RESEARCH §3.1.2 / D4」跨文档引用未限定，与 DESIGN 自身 §5.3/D4 同名混淆 | 已修复：限定为「RESEARCH §5.3」「RESEARCH §3.1.2 / §3.0-D4」 |

### 12.3 门禁 a-d（与 RESEARCH §8/§11 同款）

- **(a) FALSIFIED 重写**：`exp(λ(h_m−h))` 于 §2 D2/§5.2 禁止并给出复算依据（53%/70%）；「`m=1` 上界」改为「零衰减基准情景」（§2 D2 表）——通过。
- **(b) 冲突裁决**：RESEARCH §3.1.5「IC 序列**或**组合收益序列」由 D1 单一裁决为 `A(h)` 曲线口径，无残留「或」——通过。
- **(c) 阻断性断言双源**：D1（E3 代数 + E1 实测 + T1 方向支撑）、D2（E3 复算）、D4（E3 读码）——通过。
- **(d) 假设带入**：U-3/U-4 四元块保留 + §7 降级链 + deviation 条款——通过。

### 12.4 复审边界

- 未执行任何仓内脚本（工作区 untrusted）；复算为独立数值验证；
- `A_by_period` 的可实施性依赖 Step 9 的形成期权重改造（§10.1 #4），本 pass 只核验设计层可行性；
- E1 新基线（`alpha0 = mean A(20)`）数值在 Step 9 产出前未知，本 pass 不预填；
- U-3（D5 报告形态）/ U-4（接口）维持「保留观察」，在 Step 9 / CHECKLIST 关闭。

---

**Review 签字**: 异构复审 pass（RULE-5 · 独立新会话 · 见 §12）｜Step 4 复审 2026-11-20｜结论: PASS_WITH_FIXES → `verified`
