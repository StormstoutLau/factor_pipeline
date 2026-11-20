# v3.8.1 调研 — 真实分钟面板编排接线（λ 面板 / lambda_fill_ratio / partial_month）

> **版本**: v1.2 (2026-11-19；v1.0→v1.1：补测 U1/U2 + 复核面板可行性，新增 B12-B18；v1.1→v1.2：步骤 2 复审修正 5 类锚点/计数错误，见 §9)
> **批次**: v3.8.1（候选，`PROJECT_STATUS.md` 路线图已登记）
> **上游依据**: [RESEARCH_V3.8.0_EXECUTION_CAPACITY.md](RESEARCH_V3.8.0_EXECUTION_CAPACITY.md)（§3.1 平方根律 / §4.1 λ 回归口径 / §4.4 regime 定义，均经 §19 复审）、
> [DESIGN_EXECUTION_CAPACITY_V3.8.0.md](../private/DESIGN_EXECUTION_CAPACITY_V3.8.0.md) v1.2（§20-Q3 面板接线裁决）、
> [EXECUTION_V3.8.0_EXECUTION_CAPACITY.md](../EXECUTION_V3.8.0_EXECUTION_CAPACITY.md) §2.5 校准纪律、
> [CHECKLIST_V3.8.0_EXECUTION_CAPACITY.md](../audit/CHECKLIST_V3.8.0_EXECUTION_CAPACITY.md) X9（`partial_month` 判「不适用，随 v3.8.1 落地」）
> **调研工具**: 仓库代码与数据实测盘点（Read / Grep / Glob，2026-11-19）+ 本地数据补测（Python/pyarrow 直读 E: 盘，2026-11-19）；
> **不新增外部学术检索**——本批是接线工程，不引入新模型或新学术主张，全部模型口径沿用 v3.8.0 已复审调研（理由与引用映射见 §2）
> **实测证据**: [out/v381_research_probe.json](../../out/v381_research_probe.json)（U1/U2/覆盖度/板块分布/过滤缺陷，可复跑）
> **范围**: `run_calibration` 所需的 `panels` 契约在真实数据上如何生产；分钟数据可得性/口径/性能；降级路径与报告字段
> **产出定位**: 事实盘点 + 盲区清单 + 可操作落地方案（**不实施**；实施归步骤 9）

---

## §1 调研问题清单

| # | 问题 | 结论落点 |
|---|------|---------|
| Q1 | 「真实分钟面板编排」的准确缺口是什么？ | §3.1 / §3.3 / B1 |
| Q2 | 分钟数据范围、字段、覆盖与完整性如何？ | §3.4 / U1 / U2 |
| Q3 | λ 面板的构造口径与 `impact_samples` 语义是否有歧义？ | §3.2 / B3 / D1 |
| Q4 | λ 显著性过滤、中位数填充、`lambda_fill_ratio` 在哪层实现？ | §3.3 / B3 / §5.3 |
| Q5 | `regime_p95` / `window_capacity` 能否不依赖分钟数据生产？ | §5.5 / B2 |
| Q6 | `rho_series` / `cost_by_h` / `alpha0` / `notional` / `adv` 的来源与口径？ | §5.5 / U3-U5 |
| Q7 | `partial_month` 应落在哪个字段？2023-03 实际情况？ | §5.4 / U2 |
| Q8 | 面板区间如何取（窗口可行性）？逐月处理的性能与内存预算？ | §5.6 / B15 |
| Q9 | 默认路径零变更如何保证？面板本身可复现吗？ | §5.7 / §5.8 / B10 |
| Q10 | `ohlc` / `daily` 降级路径当前是否可用？ | §3.3 / B2 |
| Q11 | 分钟数据是否覆盖全市场？loader 的股票过滤是否丢样本？ | §3.4 / B13 |
| Q12 | 分钟聚合粒度能否直接支撑设计要求的分钟级 λ 回归？ | §3.2 / B12 |

---

## §2 学术与口径依据（复用，不重复检索）

本批不产生新的学术结论；下列口径全部来自 v3.8.0 已复审调研，实施时必须逐条引用其原文：

| 口径 | 原文位置 | 本批用法 |
|------|----------|---------|
| 冲击对参与率幂律 `impact ∝ p^b`，b 经验区间 0.4–0.7；Cont 等指出平方根关系可能是聚合伪影 | RESEARCH_V3.8.0 §3.1 | 四模型并列 + CV 选型，禁止预设 sqrt |
| 线性响应：`r_t = λ_{i,m}·(signed_amount_t / ADV_amount_{i,m}) + ε`，映射 `impact_bps = λ·p·1e4` | RESEARCH_V3.8.0 §4.1 ② | λ 面板主口径 |
| 幂律回归：`log|r_t| = a + b·log|signed_t/ADV| + d·log σ_d + ε`，`impact(p)=exp(a)·p^b·σ_d^d` | RESEARCH_V3.8.0 §4.1 ① | `impact_samples` 候选口径（见 D1） |
| **口径纪律**：回归自变量与映射式必须同口径，禁止 `λ·p·ADV/Price` 与 `r=λ·signed/ADV` 混用 | RESEARCH_V3.8.0 §4.1 ③ | 单位对账硬约束（B6） |
| regime 四维：成交额 5 分位（当月均值）/ 波动 5 分位 / 涨跌停比例 / 极端月；主值取 min | RESEARCH_V3.8.0 §4.4 | `regime_p95` 与报告主值 |
| 稳健性协议 R1-R8（多估计量交叉 / 层级敏感 / bootstrap CI / 敏感性 / 历时稳定 / 跨源一致 / 最差情形优先） | RESEARCH_V3.8.0 §5（L234-244） | 验收判据来源 |

> 说明：WORKFLOW_METHODOLOGY §13 要求步骤 1 使用多种 MCP 工具检索。本批为**接线工程**，
> 无新学术主张；重复检索只会引入与已复审文档的版本分叉。若步骤 2 review 认为需要，
> 可针对「panel/ADV 口径」「BVC 代理偏差」两个点补检并升 v1.1。

---

## §3 工程现状调研

### 3.1 `run_calibration` 的 `panels` 契约（唯一消费方）

[runner.py](../../backtest/execution/shell/runner.py#L191-L339) 中 `run_calibration(cfg, capacity_fn, breakeven_fn, panels)` 的全部输入键：

| 键 | 形状 / 类型 | 消费者（行号） | 缺失时结果 |
|----|-------------|----------------|-----------|
| `impact_samples` | `{"p","impact","sigma"}` 三个 1 维 float 数组 | L206-245 | 四模型全空、`selection.primary=None`、`c_*` 全 None |
| `lambda_pvalues` | 1 维 float（每股×月 p 值） | L246-252 | `lambda_significant_ratio=None` |
| `temporary` | `{"r1","rev1"}` 等长序列 | L254-259 | `temporary_share=None` |
| `regime_p95` | `{regime: p95 参与率}` | L263-272 | `regimes={}`、`min_regime=None` |
| `window_capacity` | `{窗长: 预测容量}` | L273-275 | `avew.evidence_warnings=["无窗长容量"]` |
| `rho_series` | 1 维序列 | L277-281 | `rho=1.0` |
| `cost_by_h` + `alpha0` + `aum` | dict + 标量 | L282-289 | `net={}`、`plateau=[]` |
| `notional` + `adv` | 等长数组 | L292-304 | `execution=None` |
| `aum_ref` / `cap` / `evidence_level` / `plateau_sd` | 标量 | L261-262、L288、L195 | 默认 `1e10` / `cfg.p_cap` / 由 `resolve_evidence_level` 推断 |

### 3.2 已具备但未被编排消费的能力

| 能力 | 位置 | 现状 |
|------|------|------|
| 分钟按月流式聚合（股票×月：净买入额、总额、月 σ、bar 数、一字板占比） | [loaders.py](../../backtest/execution/shell/loaders.py#L43-L135) | 已实现；单月峰值 184 MB / 23.5 s（v3.8.0 实测） |
| **分钟级 λ 回归输入**（每股×月逐分钟的 `signed_t` / `r_t` 序列，或等价的 `Σs·r` / `Σs²` + HAC score 序列） | 无 | **未实现**：`load_month` 只保留月度累加量（`Σsigned`、`Σamount`、`Σr`、`Σr²`、`n`），每股×月仅 1 行，无法反推回归量与 HAC 标准误（B12） |
| `fit_lambda` / `fit_lambda_hac`（含 HAC SE、t、p） | [runner.py](../../backtest/execution/shell/runner.py#L49-L87) | **仅测试引用**，编排路径零调用 |
| 日频 OHLC/amount 读取、除权跳变日 | [loaders.py](../../backtest/execution/shell/loaders.py#L138-L168) | 已实现；无行业、无 mv、无 ADV |
| `temporary_share` / `execution_days` / `net_curve` | [impact.py L174-199](../../backtest/execution/core/impact.py#L174-L199)、[decay.py L62-95](../../backtest/execution/core/decay.py#L62-L95) | 已实现，等待输入 |
| 证据等级推断 | loaders.py L171-178 | 只返回标签，无对应面板构造器 |

### 3.3 空跑证据（缺口的直接证明）

[verify_capacity_impact.py](../../scripts/verify_capacity_impact.py#L290-L322) 的 `--calibrate` 分支固定传 `panels={}`（或仅含 `evidence_level`），
因此落盘 [capacity_calibration.md](../../out/capacity_calibration.md) 全部为空：
`c_calib_point=None`、`min_regime=None`、`median=None`，`evidence_warnings` 仅「无窗长容量」。
注意报告首行仍写 `evidence_level: minutes`——**级别是推断出来的，与实际消费数据无关**（B2）。

### 3.4 数据盘点（2026-11-19 实测，证据 [v381_research_probe.json](../../out/v381_research_probe.json)）

**分钟数据**（`E:\Level 1 Data\YYYY-MM-DD.feather`）：
- 覆盖：**2250 个文件**，最早 `2014-01-02`，**止于 `2023-03-30`**（无 2023-04 及以后）；2014-01…2023-03 共 **111 个自然月**；
- 2023-03：交易日历 **23 天**，文件 **22 个**，仅缺 `2023-03-31`，无多余文件（U2 定案）；
- 2023-02：20 个文件 = 20 个交易日；
- 字段：`time / stock_code / open / high / low / close / volume / amount`（与 loader 白名单一致）；
- **代码存储为整数**：深市 000/001/002 存为 `1…3816`（如 `code=1` 即 000001 平安银行，2023-03-01 有 241 根 bar，close `14.17` 与日频一致）；
- 股票过滤现状：`100000 ≤ code < 1000000` 且剔除 `390000-399999`（[loaders.py L79-80](../../backtest/execution/shell/loaders.py#L79-L80)）——**该条件把全部 `000/001/002` 深市主板股票滤掉**（B13）。

**U1 单位定案（已核实，不再待定）**：2023-03-01 分钟 `amount` 与日频 `stock_amount` 逐股比值 **中位数 1000.0000、p05 999.999994、p95 1000.000004**（3415 对匹配）→ **分钟 amount 单位为元，日频为千元**；分钟 `volume` 为股、日频为手（比值 100）；分钟 close 与日频 close 比值 1.0。即 `分钟额(元) = 日频额(千元) × 1000`。

**覆盖度实测（2023-03-01）**：

| 口径 | 数量 | 说明 |
|------|------|------|
| 分钟原始 unique code | 5276 | 含深市主板整数代码与指数 |
| 当前 loader 保留 | **3419** | 仅创业板 1239 / 沪主板 1673 / 科创板 507，**深市主板 0** |
| 日频 close 非空 | 5095 | 当日可交易全集 |
| 与日频交集 | 3415 | 即当前面板可匹配的股票 |
| 日频有、分钟面板无 | **1680** | 全部为深市主板，占日频全集 **33.0%** |
| 分钟有、日频无 | 4 | 停牌/退市边界，需在设计阶段定规则 |

板块覆盖在多个日期一致（2014-01-02 / 2018-01-02 / 2020-01-02 / 2023-02-01 / 2023-03-30），沪主板与创业板齐全、科创板自 2020 年起出现，**深市主板始终为 0**——是过滤缺陷而非数据缺失。

> 更正：v1.0 引用的「2023-03-01 实测 5276 只」是**过滤前原始 unique**（v3.9.0 探针 P5-5f 亦按此计数），实际进入面板的只有 3419 只。P5-5f 的「股票=5276」不构成覆盖率证据。

**日频数据**（`E:\Ashare_data\market_data\`）：
- `stock_{open,high,low,close,volume,amount,adj,suspend,name,return}.pkl`、`list_date_df.pkl`、`all_dates.pkl`；
- 列名为**零填充 6 位字符串**（`"000001"`、`"000002"`…），与分钟整数代码需 `zfill(6)` 对齐（B14）；
- `stock_ind.pkl`（行业）实测覆盖 2009-01-05 → **2023-06-13**，完整覆盖 λ 面板窗口；
- `market_value.csv` 位于 `market_data/` 下（非根目录），末端 2026-01-23；
- 单位：`stock_amount` 千元、`market_value` 万元（[verify_capacity_impact.py L57-58](../../scripts/verify_capacity_impact.py#L57-L58)）。

### 3.5 配置与报告现状

- `CalibrationConfig` 声明 **16 个字段**（[config.py L19-34](../../backtest/execution/config.py#L19-L34)），`--calibrate` 路径实际消费的只有
  `p_cap / d_max / seed / lambda_p_threshold`（`kappa` 仅在 runner L324 回显为结果字段，κ 情景 `(1.0, 1.5, 2.0)` 硬编码于
  [runner L269-271](../../backtest/execution/shell/runner.py#L269-L271)）；`participation_grid`、`sigma_clip`、`bvc_sigma_bars`、
  `block_size_mode`、`tau_max_minutes`、`windows`、`default_horizon` **共 7 个未接线**（`windows` 仅在 `--diagnose-window` 被打印）；
- `render_markdown`（[report.py L22-57](../../backtest/execution/shell/report.py#L22-L57)）只渲染 `c / capacity / ratio_diagnostics / evidence_warnings`，
  无覆盖率、λ 显著比例、`lambda_fill_ratio`、`partial_month`、面板 hash 字段。

### 3.6 依赖与默认路径纪律

- 零新增依赖：pyarrow 走 `calib` extra + `has_pyarrow()` 能力探测；面板中间产物建议用 json/npz（stdlib+numpy）；
- 默认路径（无 `--calibrate`）必须逐位不变：`out/capacity_impact.json` SHA256 `82728CE1…`；
- 包内不得 import `scripts`（T380-41 / T380-54），日频组合面板只能由脚本侧算好后注入。

---

## §4 盲区清单

| # | 盲区 | 证据 | 严重度 | 本批处置建议 |
|---|------|------|--------|-------------|
| B1 | 面板编排层完全缺失：`--calibrate` 空跑 | §3.3 | **P1** | 新增 `shell/panels.py` + 脚本接线 |
| B2 | `evidence_level` 名义降级：`ohlc`/`daily` 无构造器，报告仍写 `minutes` | §3.3 / §3.2 | **P1** | 实际级别写入报告；无分钟时只做容量路径并显式 warning |
| B3 | λ 显著性填充纪律未实现：runner 只算 `lambda_significant_ratio`，不做行业×规模中位数填充、无 `lambda_fill_ratio`、无 >30% 降级 | runner L246-252；EXECUTION §2.5 | **P1** | 填充前移到面板构造器（§5.3） |
| B4 | `impact_samples` 语义未定义：若按 `λ·p` 直接造样本，线性模型自证，CV 选型失去意义 | RESEARCH §4.1 ①②；runner L206-245 | **P1** | 设计阶段显式裁决（D1） |
| B5 | `partial_month` 无落点：JSON/MD 均无字段 | CHECKLIST X9；report.py | P2 | 面板层检测 + 报告字段（§5.4） |
| B6 | ADV 口径未定：λ 的分母 `ADV_i,m` 与 regime 参与率分母是否同一（21 日均额 / 当月日均 / 月末快照）；单位已定案（分钟元、日频千元） | §3.4 / U1 | P2 | 设计裁决并写入 `panel_hash`（U11） |
| B7 | 性能与缓存：逐月重复处理无缓存；实际开销含 λ 回归与 HAC，不能按 23.5 s 线性外推 | v3.8.0 实测 | P2 | 先做单月基准再定预算（§5.6） |
| B8 | 2023-03 完整性：**已定案** 23 交易日 / 22 文件 / 缺 03-31；DESIGN §20-Q3 的「21 个交易日」为笔误 | §3.4 / U2 | P2 | 设计文档勘误 + `partial_month` 判据（U2 已核实） |
| B9 | 一字板/停牌未定义是否剔除：loader 已给 `limit_lock` 占比但无使用规则 | loaders L135 | P3 | 设计裁决（建议：锁定 bar 不参与 λ 回归，股票保留） |
| B10 | 可复现性：`config_hash` 不覆盖面板口径（ADV 窗长、分箱、填充规则） | config.py | P3 | 新增 `panel_hash` 写入报告 |
| B11 | 配置旋钮未消费：7 个参数声明但无实现（`kappa` 仅回显、情景硬编码） | §3.5 / runner L269-271 | P3 | 接线时全部消费或删除（设计裁决） |
| B12 | **分钟聚合粒度不足以支撑 λ 回归**：`load_month` 只留月度累加量，每股×月 1 行；设计要求分钟级 OLS，HAC 还需 score 序列 | §3.2 / runner L63-87 | **P1** | 新增逐分钟/逐日累加器（§5.3） |
| B13 | **loader 过滤丢弃深市主板**：`stock_code >= 100000` 把整数存储的 000/001/002 全部滤掉，2023-03-01 少 1680 只（日频全集 33%） | §3.4 / loaders L79-80 | **P1** | 修过滤为 `1 ≤ code < 1000000` 且剔 `390000-399999`，并加回归测试 |
| B14 | 代码对齐键：日频列是零填充字符串，分钟是整数，需 `zfill(6)` 映射；当前无任何对齐代码 | §3.4 | P2 | 面板构造器统一 `code → "000001"` |
| B15 | **`window_capacity` 与样本跨度冲突**：`windows=(24,36,48,60)`，若面板取 2020-01…2023-03（39 月），48/60 月窗不可得 | config L27 / §5.6 | **P1** | 前移面板起点至 2015-01（分钟可得）或窗口降档，设计裁决 |
| B16 | `regime_p95` 定义缺口：缺参考 AUM、p95 统计集合（股票×月交易 / 月）、与 AUM 的缩放关系 | runner L261-271 | P2 | 设计裁决并写入报告字段（§5.2） |
| B17 | `temporary` 的 `r1`/`rev1` 语义：跨月截断丢样本；未说明组合层还是截面层 | core/impact.py L174-199 | P2 | 设计裁决（U12） |
| B18 | 样本窗口不一致：`cfg.sample_start/end = 2020-01-31 / 2026-01-31`，分钟止于 2023-03-30 | config L21-22 | P2 | 面板窗口取 `min(config, 数据可得)` 并写 coverage |

---

## §5 方案要点（供步骤 3 设计，不在本步实施）

### 5.1 新增模块与建议签名

```python
# backtest/execution/shell/panels.py（新）
@dataclass
class PanelCoverage:
    months: list            # 实际参与月份
    partial_months: list    # 文件数 < 交易日数的月份
    stock_median: float
    universe_ratio: float   # 面板股票数 / 日频当日非空数
    missing_month_rate: float
    limit_lock_ratio: float

class MinutePanelBuilder(object):
    def __init__(self, cfg, loader=None): ...          # loader 注入为测试缝
    def build(self, start="2015-01", end="2023-03") -> dict
    # 返回 run_calibration 可直接消费的 panels 子集 + coverage + panel_hash

def build_daily_panels(cfg, daily, portfolio) -> dict  # 纯函数；portfolio 由脚本侧注入
def assemble_panels(minute_panels, daily_panels, evidence_level) -> dict
```

`MinutePanelBuilder` 内部需要两种聚合，**不能复用现有 `load_month` 的月度汇总**：
1. `monthly_stats`：现有口径（BVC σ、一字板占比）；
2. `regression_inputs`：每股×月的 `(x_t, r_t)` 观测——点估计只需流式累加 `Σx·r`、`Σx²`；HAC 标准误需要 score 序列 `x_t·resid_t`。存储量：单日 ≈ 1.27M float（约 10 MB），但**整月按股保留 ≈ 28M float（float64 224 MB / float32 112 MB）**，与 300 MB 峰值预算冲突。三个候选（U14 裁决）：
   - (a) 分钟级回归 + 整月 score 序列（float32 + 预算上调）；
   - (b) 分钟级回归 + 跨日 HAC 的环形缓冲（只留最近 L 日 score，复杂但省内存）；
   - (c) **日级聚合回归**（`x_d = Σs_t/ADV`、`r_d = Σr_t`，每股×月 22 个观测）——与线性模型同口径且可加，内存降到 KB 级，代价是 HAC 有效样本变少、需在设计文档声明粒度。

约束：`panels.py` 不 import `scripts`；日频组合面板（权重/交易额/ADV/σ）由脚本算好后传入。

### 5.2 `panels` 键 → 生产者映射

| 键 | 生产者 | 口径要点 |
|----|--------|---------|
| `impact_samples` | `MinutePanelBuilder` | D1 裁决后确定：幂律回归 ① 或 λ 线性映射 ②（见 §5.3） |
| `lambda_pvalues` | `MinutePanelBuilder` | 每股×月 HAC p 值（`fit_lambda_hac`） |
| `temporary` | `build_daily_panels` | `r1`=当月日收益、`rev1`=次日收益；跨月样本处理与层级（组合/截面）待 U12 裁决 |
| `regime_p95` | `build_daily_panels` | 全市场日成交额月均 5 分位分桶；**必须同时声明**：参考 AUM（建议 `aum_ref`）、p95 覆盖集合（股票×月交易观测）、`participation = notional/(AUM·ADV)` 的线性缩放（B16） |
| `window_capacity` | `build_daily_panels` | `cfg.windows` 各窗长滚动 p95 → `capacity_fn`；**需先裁决窗口与样本跨度**（B15） |
| `rho_series` | `build_daily_panels` | U3 待设计裁决（建议：组合月超额序列 AR(1)） |
| `cost_by_h` / `alpha0` | `build_daily_panels` | U4/U5；`net_curve` 要求同单位（元 vs 收益率） |
| `notional` / `adv` | 脚本侧 `P` | 复用 `build_panels` 的 `amt_m`；**ADV 口径（21 日均额 / 当月日均）与单位（千元→元 ×1000）需固定**（B6/U11） |

### 5.3 λ 面板与显著性填充（B3）

1. 每股×月、逐分钟：`s_t = amount_t·(2Φ(r_t/σ_t) − 1)`（**元**，BVC 代理）、`x_t = s_t / ADV_{i,m}`（无量纲）、`r_t` = 分钟内收益；`fit_lambda_hac(x, r)` → λ、SE、p；
   - 单位链：分钟 `amount` 元 → 日频 `stock_amount` 千元 ×1e3 = 元；ADV 与分子同为金额口径；回归与映射式必须同口径（RESEARCH_V3.8.0 §4.1 ③）；
   - 代码对齐：分钟整数 code → `zfill(6)` 字符串 ↔ 日频列名（B14）；过滤修为 `1 ≤ code < 1000000` 且剔 `390000-399999`（B13）；
   - 最小观测：建议每股×月 `n_bars ≥ 30` 且剔除一字板 bar（B9），不足则记缺失（阈值设计裁决）；
   - **回归粒度**：分钟级（设计原文）或日级聚合（U14），二者变量定义同口径、可加；若选日级，需在设计与报告显式声明「λ 为日频聚合口径」；
2. `p < cfg.lambda_p_threshold` 纳入；其余按「行业 × 规模分位」λ 中位数填充（行业=`stock_ind.pkl`，规模=`mv` 分位 5 组）；λ<0 与极端值的处置需裁决（U13）；
3. 输出 `lambda_fill_ratio`；**> 30% → 结果降级 `[区间]` 并写 `evidence_warnings`**（EXECUTION §2.5 硬约束）；
4. `lambda_pvalues` 只作为诊断序列传给 runner（保持既有语义）。

### 5.4 覆盖度与 `partial_month`（B5/B8）

按交易日历（`stock_close.index` 或 `all_dates.pkl`）逐月比对 feather 文件数：
- 缺月 → `missing_month_rate`，该月不参与面板；
- 缺日但 ≥ 20 日 → 保留并写 `partial_month=YYYY-MM`（**2023-03：22/23，缺 03-31，必然命中**）；
- 缺日 < 20 → 整月剔除并写 warning。

阈值 20 为调研建议值，**非设计原文**，需在设计与 `partial_month` 判据一并裁决（B8）。同时按 §3.4 口径输出 `stock_median` 与 `universe_ratio`（面板股票数 / 日频当日非空数），作为面板覆盖度的硬指标：修复 B13 后该比值应接近 1（当前 3419/5095 ≈ 0.671）。

### 5.5 降级路径（B2）

| 级别 | 可用内容 | 报告 |
|------|----------|------|
| `minutes` | 全量（λ / c / b / regime / window / decay） | `evidence_level=minutes` |
| `ohlc` / `daily` | **仅** regime / window / decay / execution（无 λ、无 c） | `evidence_level=ohlc|daily` + `c_*=None` + warning「无分钟数据，c 不可校准」 |

这使 P1 #5（regime 真实复算）不必等待分钟面板即可交付；#4 的 exQ1 口径复算仍需 minutes。

### 5.6 性能、窗口可行性与缓存（B7/B15）

**窗口可行性（必须先裁决）**：`cfg.windows=(24,36,48,60)`，而不同面板起点的可用月数不同：

| 方案 | 面板区间 | 月数 | 24 月 | 36 月 | 48 月 | 60 月 | 备注 |
|------|----------|------|-------|-------|-------|-------|------|
| A（v1.0 默认） | 2020-01…2023-03 | 39 | 可用 | 仅 1 点 | **不可得** | **不可得** | 需窗口降档或声明不适用 |
| B（建议） | 2015-01…2023-03 | 99 | 可用 | 可用 | 可用 | 可用 | 分钟数据自 2014-01 起，可行 |
| C | 2014-01…2023-03 | 111 | 可用 | 可用 | 可用 | 可用 | 边际收益低、成本最高 |

选择 B/C 会把逐月处理量从 39 月提到 99/111 月，配合新增的分钟级 λ 回归，**原「39 月 < 25 min」预算失效**。建议改为分级预算：单月基准先测（含 λ 回归与 HAC），再按实测定总上限；同时给出「只算容量路径（无 λ）」的快速档。

**内存与缓存**：
- 峰值内存 < 300 MB（逐日流式已保证 184 MB）；但若选分钟级回归并整月保留 score 序列，峰值约 +112~224 MB，**会突破预算** → 需按 U14 选择 float32 并上调预算、环形缓冲，或日级回归；
- 月度缓存 `out/calibration_cache/<YYYY-MM>.json`（约 5000 行 × 6 列），`--no-cache` 可关；缓存文件不入默认路径。

### 5.7 默认路径与可复现（Q9/B10）

- 无 `--calibrate` 时零改动；`out/capacity_impact.json` SHA 断言纳入门禁；
- `panel_hash = sha256(canonical(λ 面板 + coverage + config_hash))` 写入 JSON/MD；双跑一致。

### 5.8 验收判据（可执行）

1. `--calibrate` 后 `out/capacity_calibration.md` 的 `c_calib_point` / `min_regime` 非 None（分钟可得时）；
2. `evidence_level` 与实际消费数据一致；无 pyarrow 时降级且 exit 0（或按设计 exit 2）；
3. `lambda_fill_ratio` 落盘；>30% 时 `[区间]` 降级可见；
4. `partial_month=2023-03` 出现在报告中；
5. 双跑 `panel_hash` 与 JSON 全字段一致（除时间戳，若有则显式剔除）；
6. 默认路径 SHA256 `82728CE1…` 不变；全量回归零新增失败；
7. 性能：单月基准先测再定总上限（含 λ 回归 + HAC），峰值 < 300 MB；
8. **覆盖度硬门禁**：面板股票数 / 日频当日非空数 ≥ 0.95（修复 B13 后；当前 0.671 即不合格）；
9. **单位硬门禁**：分钟 `amount` 与日频 `stock_amount` 的月度汇总比值 ∈ [0.999, 1.001] × 1e3，超界即停；
10. `coverage`（含 `partial_months`、`universe_ratio`）与 `panel_hash` 落盘。

### 5.9 测试矩阵（预计 22 例）

| 组 | 例数 | 内容 |
|----|------|------|
| 单元 | 11 | λ 回归对拍（合成已知斜率）、HAC p、填充中位数、fill_ratio 计算、>30% 降级、partial_month 判定、单位对账（×1e3）、coverage、**代码过滤保留 000xxx / 剔除 390xxx**、**整数→`zfill(6)` 对齐**、最小观测与一字板剔除 |
| 集成 | 5 | 合成 3 月面板 → `run_calibration` 全字段非空；双跑 panel_hash 一致；缺月/缺日降级；无 pyarrow 降级；缓存命中/失效 |
| 端到端 | 2 | 真实 1 月（2023-03）冒烟；报告字段齐全（含 coverage / partial_month / lambda_fill_ratio） |
| 回归 | 4 | 默认路径 SHA；`--report-json` 兼容；G1 新增测试全绿；**覆盖率门禁 ≥ 0.95** |

### 5.10 风险与回滚

| 风险 | 处置 |
|------|------|
| **过滤器缺陷未修**（B13）：面板仅覆盖 67% 市场，λ 与容量结论有偏 | 覆盖率硬门禁 ≥ 0.95 + 板块分布断言（深市主板 > 0），不达标即停 |
| **窗口与样本跨度不匹配**（B15）：48/60 月窗不可得 | 设计阶段先裁决方案 A/B/C，再定性能预算 |
| 分钟 `amount` 单位误判 | 已定案为元（U1），仍保留月度对账断言（验收 #9） |
| `impact_samples` 口径自证线性（D1） | 设计阶段裁决并写入设计文档；两种口径都留敏感性 |
| 39/99 月运行超预算 | 单月基准先测 + 缓存 + 分月可中断；快速档可跳过 λ |
| 面板污染默认输出 | 全部写 `out/calibration_*`，默认路径零改动 + SHA 门禁 |

---

## §6 未核实项

| # | 项 | 影响 | 核实方式 |
|---|----|------|---------|
| U1 | ~~分钟 `amount` 单位~~ | — | **已核实（2026-11-19）**：元；分钟/日频比值 1000.0000（p05-p95 999.999994–1000.000004）；`volume` 股 vs 手（×100）；证据 `out/v381_research_probe.json` |
| U2 | ~~2023-03 交易日数~~ | — | **已核实（2026-11-19）**：23 交易日、22 文件、仅缺 03-31；DESIGN §20-Q3「21 个交易日」为笔误，需勘误 |
| U3 | `rho_series` 定义（组合超额 / 因子 IC / 其他） | E4 衰减与 `net(h)` | 设计 §10 原文核对；建议组合月超额 AR(1) |
| U4 | `cost_by_h` 构造（执行成本 vs 持有成本，单位元/收益率） | `net_curve` 量纲 | 设计 §10.2 与 `net_curve` docstring 对齐 |
| U5 | `alpha0` 来源与单位（年化超额？单期？） | 同上 | 由 exQ1 报告口径注入，设计裁决 |
| U6 | 行业×规模分箱定义（行业级别、规模分位组数） | B3 填充 | 设计裁决；建议一级行业 × mv 五分位 |
| U7 | BVC `signed_amount`（`2φ-1` 乘 amount）与设计 `signed_vol` 的价量差异 | λ 口径 | 设计说明；`signed_amount/ADV_amount` 已同口径（金额对金额），可解释 |
| U8 | regime 5 分位分界点（分位计算样本：全样本 vs 滚动） | E5 主值 | 设计裁决；建议全样本月均成交额分位，报告同时给滚动敏感性 |
| U9 | 极端月 2024-02 无分钟数据 | E5「极端月」维度 | 仅可用于日频容量压力，不参与 λ 校准；报告需声明 |
| U10 | 面板起点与 `windows` 取舍（方案 A/B/C） | `window_capacity` 是否可得 | 设计裁决（§5.6，B15） |
| U11 | ADV 定义：21 日均额 / 当月日均 / 月末快照；与 regime 参与率分母是否同源 | λ 与容量口径一致性 | 设计裁决（B6） |
| U12 | `temporary` 层级（组合/截面）与跨月样本处理 | T+1 reversal 估计 | 设计裁决（B17） |
| U13 | λ<0 与极端值处置（缩尾 / 剔除 / 保留） | 填充中位数与 `lambda_fill_ratio` | 设计裁决（§5.3） |
| U14 | 回归粒度：分钟级（含 score 序列的内存方案 a/b）vs 日级聚合（c） | λ 估计与内存峰值（112~224 MB） | 设计裁决（§5.1/§5.3） |

---

## §7 锚点索引

| 类型 | 位置 |
|------|------|
| 编排消费方 | [runner.py](../../backtest/execution/shell/runner.py#L191-L339) |
| 分钟加载器 | [loaders.py](../../backtest/execution/shell/loaders.py#L43-L135) |
| 证据等级解析 | [loaders.py](../../backtest/execution/shell/loaders.py#L171-L178) |
| 配置 | [config.py](../../backtest/execution/config.py#L15-L34) |
| 报告渲染 | [report.py](../../backtest/execution/shell/report.py#L22-L57) |
| 脚本接线点 | [verify_capacity_impact.py](../../scripts/verify_capacity_impact.py#L290-L322) |
| 空跑产物 | [capacity_calibration.md](../../out/capacity_calibration.md) |
| v3.8.0 未达点 | [CHECKLIST_V3.8.0 X9](../audit/CHECKLIST_V3.8.0_EXECUTION_CAPACITY.md#L267) / [DESIGN §20-Q3](../private/DESIGN_EXECUTION_CAPACITY_V3.8.0.md#L827-L831) |
| 学术口径 | [RESEARCH_V3.8.0 §3.1（L74）/ §4.1 ①②③（L165-172）/ §4.4（L206-217）/ §5 R1-R8（L234-244）](RESEARCH_V3.8.0_EXECUTION_CAPACITY.md#L74) |
| 真实单日复核 | [review_v390_results.txt](../../out/review_v390_results.txt) P5-5f 行（注意：其「5276」为过滤前原始 unique，非面板覆盖） |
| **v1.1 实测证据** | [v381_research_probe.json](../../out/v381_research_probe.json)（U1 单位 / U2 日历 / 覆盖度 / 板块分布 / 过滤缺陷） |
| **λ 回归所需累加器** | `loaders.py` L101-135（现有月度汇总，不足）；`runner.py` L49-87（`fit_lambda*` 期望逐观测序列） |

---

## §8 版本记录

| 版本 | 日期 | 内容 |
|------|------|------|
| v1.0 | 2026-11-19 | 步骤 1 首版：契约盘点、数据实测、11 项盲区、方案要点与 18 例测试矩阵、9 项未核实 |
| v1.1 | 2026-11-19 | 补测定案：U1 分钟 amount=元（比值 1000）、U2 2023-03 为 23 交易日/22 文件；新增 B12（聚合粒度不足）、B13（loader 丢深市主板 33%）、B14（代码对齐）、B15（窗口×跨度）、B16（regime_p95 定义）、B17（temporary 语义）、B18（样本窗口不一致）；新增 U10-U14（窗口取舍 / ADV / temporary 层级 / λ 负值 / 回归粒度）；覆盖面补 `universe_ratio`、验收 7→10 条、测试矩阵 18→22 例、性能与内存预算改为先测后定；证据 `out/v381_research_probe.json` |
| v1.2 | 2026-11-19 | **步骤 2 复审**：修正 5 类发现（F1 λ 口径位置 §3.3→§4.1 共 7 处 / F2 参数 13→16、未接线 6→7 / F3 kappa 仅回显+情景硬编码 / F4 B15·B18 config 行号 / F5 R1-R7→R1-R8 §5）；核对通过项与裁决详见 §9；B1-B18、方案、验收、测试矩阵结论不变 |

---

## §9 步骤 2 复审记录（v1.1 → v1.2，2026-11-19）

复审口径：阶段 3 快速 Review（代码锚点逐条核对 + 数据事实复测 + 内部一致性）；本批无外部学术检索，故无阶段 4。

### 9.1 核对通过项（抽样列举）

- `runner.py` 全部消费锚点（L191/L195/L206-245/L246-252/L254-259/L261-262/L263-272/L273-275/L277-281/L282-289/L288/L292-304/L324）逐一与源码对齐；
- `loaders.py` L43-135/L79-80/L101-135/L138-168/L171-178；`decay.py` L62-95（execution_days L62-75 / net_curve L78-86 / plateau L89-95）；`impact.py` L174-199；`report.py` L22-57；`config.py` L16-34；脚本 L290-322（含 `panels={}` L299、`windows` 仅 L305 打印）；
- CHECKLIST X9=L267、DESIGN §20-Q3=L827-831、RESEARCH_V3.8.0 §19 复审=L870；
- `fit_lambda`/`fit_lambda_hac` 仅 tests/test_execution_capacity.py L103-121 引用，编排路径零调用；
- 数据事实与 [v381_research_probe.json](../../out/v381_research_probe.json) 逐项一致（2250 文件 / 111 月 / 23-22-缺 03-31 / 5276·3419·5095·3415·1680·4 / 比值 1000 / 241 bar / 14.17）；复测 stock_ind（2009-01-05→2023-06-13）、market_value.csv（末端 2026-01-23）、all_dates/list_date_df 存在；
- 算术复核：0.671=3419/5095、33.0%=1680/5095、3415+4=3419、39/99/111 月、28M float=22×1.27M（224/112 MB float64/float32）、22=11+5+2+4、P1 计数 7（B1/B2/B3/B4/B12/B13/B15）、B1-B18 与 U1-U14 编号连续。

### 9.2 发现与修正（F1-F5，均已在 v1.2 落地）

| # | 发现 | 修正 |
|---|------|------|
| F1 | λ 回归口径 ①②③ 实际位于 RESEARCH_V3.8.0 **§4.1 路径 A 步骤 3（L165-172）**，非 §3.3（§3.3 为 OHLC 价差代理，L96-106）；头部 / §2 表×3 / B4 / §5.3 / §7 共 7 处错引 | 全部改为 §4.1 ①②③；§7 锚点改为 §3.1（L74）/ §4.1（L165-172）/ §4.4（L206-217） |
| F2 | `CalibrationConfig` 实为 **16 个字段**（config.py L19-34），非「13 个参数」；未接线实为 **7 个**（原文漏 `default_horizon`） | §3.5 与 B11 计数修正 |
| F3 | `cfg.kappa` 仅在 runner L324 回显为结果字段；κ 情景 `(1.0, 1.5, 2.0)` 硬编码于 runner L269-271——「实际消费 kappa」说法过强 | §3.5 措辞修正 + B11 证据补充 |
| F4 | B15 证据行号 config L24（实为 sigma_clip）→ `windows` 在 L27；B18 证据 config L19-20（实为 data_root/minute_root）→ sample_start/end 在 L21-22 | 两处行号修正 |
| F5 | §2 表「三角验证 R1-R7 / §4.x」：实际为 **R1-R8、§5 稳健性与鲁棒性协议（L234-244）** | §2 表与 §7 锚点修正 |

### 9.3 复审裁决

1. **外部学术补检：不需要**。§2 预留的「若步骤 2 review 认为需要补检」裁决为否——本批全部模型口径（§4.1 ①②③、§4.4、§5 R1-R8）均已在 v3.8.0 经 §19 异构复审，本批不引入新学术主张；补检只会制造版本分叉。
2. **发现项定级**：F1-F5 均为「引用与计数错误」，不影响结论方向，但影响实施时按图索骥（尤其 F1 的口径引用是 §5.3 单位链的权威出处）。无新增盲区、无结论变更——B1-B18、方案 §5、验收 §5.8、测试矩阵 §5.9 全部维持。
3. **DESIGN §20-Q3「21 个交易日」勘误**：已由 U2 实测定案（23 交易日 / 22 文件 / 缺 03-31），勘误动作移交步骤 3 设计文档（§3.4/B8 已声明）。
4. **下一步**：步骤 3 设计。设计输入 = 本文档 v1.2 + U3-U14 待裁决 + D1（impact_samples 口径）+ U10 方案 A/B/C + U14 回归粒度。
