# 设计文档：P-008 数据行数对齐（分钟 / 日频覆盖核对）—— 四项裁决采纳

---
id: v399-p008-data-row-alignment-DESIGN
type: design
version: 1.1
status: verified
date: 2026-11-22
depends: [v399-p008-data-row-alignment-RESEARCH]
upstream: null
---

> **Feature**: 把 P-008 的 U-1~U-4 四项裁决落成**可实施、可验收的证据层方案**（运行时对齐观测 + 离线三方分解审计）
> **创建日期**: 2026-11-22
> **状态**: verified（v1.1，2026-11-22：Step 4 独立复审 PASS_WITH_FIXES——1×P2 + 4×P3 已处置，INV-1~9 全达成，见 §12）
> **Spec 步骤**: Step 3-4
> **基于调研**: [RESEARCH.md](./RESEARCH.md) **v1.5 verified**（U-1~U-4 已关闭，§6.4/§6.5；v1.5 = Step 8 P3-1 舍入订正）
> **批次档位**: **T1**（本设计含 Layer-1 变更面：`backtest/execution/shell/` + `scripts/` + `tests/`；Step 1-2 的文档批到此升级）

---

## 1. 设计目标

把四项裁决从「调研结论」变成两类可复核产物：

1. **运行时证据层**：校准路径在**不改变任何现有数值**（`c` / `λ` / `σ` / 覆盖度 / `panel_hash`）的前提下，逐月记录分钟↔日频行数对齐读数，并对截断日、缺日发出非阻断 warning；
2. **离线审计入口**：按需生成 39 月三方分解报告（A/B/C/D + 双口径恒等式），作为 P-008 验收 ①/② 的稳定复现出口。

**不解决**：补齐数据源、改窗口、改门禁、改冲击模型、重估 `c`（见 §2.3）。

## 2. 设计依据

### 2.1 调研结论 → 设计决策

| 调研发现 | 设计决策 | 引用 |
|---|---|---|
| U-1：剔除 2020-02-26/27 对全窗口 `c` 仅 **+0.098%**，但月成交额必降 **9.29%**；现有 partial 门禁（文件数 20=20）**不识别截断** | **D1** 不剔除、保留月度口径；新增「逐日行数偏差 >5%」观测与 `data_alignment_truncation` warning | RESEARCH §6.4 U-1 / §6.5 |
| U-2：过滤 `amount==0` 对全窗口 `c` 仅 **+0.428%**，codes 不变（5,029），`n_bars` 不进入下游 | **D2** 保留供应商原始零成交 bar；零成交股票×日只作证据统计（7,917 / 0.230%，峰值 2022-05 1.084%） | RESEARCH §6.4 U-2 / §6.5 |
| U-3：源止于 2023-03-30；7 个数据目录无 03-31，无归档 | **D3** 不补、不合成；缺日显式命名披露，39 月窗口不变 | RESEARCH §6.4 U-3 / §6.5 |
| U-4：交集口径把 A 按构造消除，残差只度量 B（2022-05 峰值 1.084%）；三方分解残差为 0 | **D4** 三方分解为审计主口径；交集残差只作 B 指标；匹配日与全窗口双口径全量披露 | RESEARCH §6.4 U-4 / §6.5 |
| 归因需要日频逐日代码集，运行时全量保留会显著增内存 | **D5** 运行时只做 **counts-only** 对齐（逐日行数），代码集归因放到离线审计 | RESEARCH §6.5「三方分解」/ 本设计 §3.2 |
| 生产入口已有 `--contract` / `--calibrate` 分支模式 | **D6** 新增 `--alignment-audit` 按需入口，产物 `out/data_alignment.json/.md`；默认路径不触发 | 本设计 §3.4 / §4.3 |
| 默认 `out/capacity_impact.json` SHA 与 `panel_hash` 是既有不变式 | **D7** `data_alignment` 只进校准工件与校准 md；不进 `panel_hash`、不进默认输出 | `panels.py` L424-L440 / §8 |
| 覆盖度门禁已有独立判据，P-008 不改变门禁语义 | **D8** 对齐告警**非阻断**：不新增门禁、不改 exit code、不参与 `coverage_gate` | §7 / §8 INV-5 |

### 2.2 相关 ADR / 规范条款

| 条款 | 决策 | 对本设计的影响 |
|-----|------|--------------|
| [ADR-0010 三问（内联）](file:///f:/Coding/factor_pipeline/spec/SPEC_PROCESS.md#L486-L491) | 新增面须答「放哪层 / 激活条件 / 未激活副作用」 | §3.5 对 `data_alignment` 块、审计入口、新模块逐项作答 |
| [ADR-0008 门禁（内联）](file:///f:/Coding/factor_pipeline/spec/SPEC_PROCESS.md#L296-L301) | Step 2 门禁已通过，Step 3 引用状态须延续 | 所有决策可回溯到 RESEARCH v1.4；U 项已关闭，无 OPEN 状态漂移 |
| [ADR-0002 职责边界（内联）](file:///f:/Coding/factor_pipeline/spec/SPEC_PROCESS.md#L309-L318) | 区分职责外 / 能力边界 | §2.3 |

### 2.3 职责边界

**职责内**：分钟↔日频逐月/逐日行数对齐的**观测、归因、披露**；四项裁决的落地形态；审计产物与校准证据块。

**职责外（不回答）**：
- 数据供应商截断的**修复**（属于采购/数据治理，不在本仓）；
- 2023-03-31 分钟源的补采或合成（U-3 已裁决不可得）；
- 冲击模型 / `c` 可识别性改进（`c≈2.91 > 2.0` 的 fallback 已由生产处理，见 RESEARCH §6.5 残余风险）；
- 覆盖度门禁阈值定标（v3.9.4 P-004 范围）。

**能力边界（回答不了）**：
- 无法判断供应商内部为何截断，只能按代码域/截断/缺日三分类归因；
- 无法证明「未观测到的缺失不存在」；只能声明本次 39 月窗口内的读数与检索范围（RESEARCH §6.5 U-3）。

## 3. 架构设计

### 3.1 变更面

```
backtest/execution/shell/panels.py
  ├─ DailyRef            + rows_by_day / dates_by_month（可选，默认 None）
  ├─ build()             + 逐月 counts-only 对齐累加 → "data_alignment" 块
  └─ （λ / σ / impact / coverage / panel_hash 路径零改动）

backtest/execution/shell/alignment.py（新增：审计 + 落盘两个公开函数）
  └─ audit_alignment(...) → 三方分解 dict（A/B/C/D + 双口径）

scripts/verify_capacity_impact.py
  ├─ daily_ref()         + 注入 rows_by_day / dates_by_month
  ├─ attach_panel_meta() + 透传 panels["data_alignment"]
  └─ main()              + --alignment-audit 分支（默认不触发）

backtest/execution/shell/report.py
  └─ 校准 md             + 「数据行数对齐」节（仅当 data_alignment 存在）

tests/test_minute_panels.py / tests/test_data_alignment.py
  └─ T398-1 ~ T398-8
```

### 3.2 模块划分

| 模块 | 职责 | 输入 | 输出 | 依赖 |
|---|---|---|---|---|
| `DailyRef`（扩展） | 携带日频逐日行数与交易日列表 | `market['close']` | `rows_by_day` / `dates_by_month` | 无 |
| `MinutePanelBuilder._align_month` | 单月 counts-only 对齐 | 单月 `MinuteDayAggregate` + `DailyRef` | 月行 + 日级异常 + 零成交计数 | `_load_month` 结果（零额外 IO） |
| `alignment.audit_alignment` | 39 月三方分解 | `cfg` / `MinuteLoader` / `close` | 审计 dict | `loaders._keep_mask`（单一真源）+ pyarrow 列投影 |
| `report.py` 渲染 | 校准 md 增量节 | `panels.data_alignment` | md 文本 | 无 |
| `verify_capacity_impact.py` | 入口与透传 | CLI 参数 | JSON/MD 落盘 | 上述模块 |

### 3.3 数据流

**运行时（`--calibrate`）**

1. `daily_ref()` 从 `P['close']` 生成 `rows_by_day`（`YYYY-MM-DD → 非空股票数`）与 `dates_by_month`；
2. `build()` 在既有月循环内，对已加载的 `agg` 计算 `day_counts = 每日唯一 stock_code 数`、`zero = (amount_day == 0)`；
3. 与 `rows_by_day` 比对：匹配日口径 `minute_sd / daily_sd / diff_pct`；`|diff_pct| > 5%` 进 `outlier_days`；日频有而分钟无的日期进 `missing_minute_days`；
4. 汇总为 `data_alignment`（schema 见 §4.2）挂到分钟层返回 dict；
5. `attach_panel_meta` 透传到 `result['panels']['data_alignment']`；`report.py` 渲染；
6. warning 追加到 `minute['evidence_warnings']`（经既有合并通道进入校准产物）。

**离线（`--alignment-audit`）**

1. 逐日只读 `stock_code` / `amount` 两列（pyarrow 列投影），复用 `loaders._keep_mask`（单一真源），**不触发 σ/λ 计算**；每日唯一码存 `int32` 数组（单月驻留，约 12 MB/39 月）；
2. 全局码域：分钟 = 窗口内出现过的唯一码（5,029）；日频 = **窗口交易日 `close` 非空列的并集**（5,273；注意 `close` 全历史有 5,688 列，须按窗口内非空取并集，不得直接取列数）→ A 集 = 日频独有 244 码；
3. 逐日集合运算：`both / minute_only(B) / daily_only`；`daily_only` 按**码级规则**三拆（与 RESEARCH §3.3 数字对齐的关键，复审 F-7）：**A = 码 ∉ 分钟域**（全部日期，含截断日的 58/65 与 03-31 的 186）；**C = 码 ∈ 分钟域 ∧ 日期 ∈ {2020-02-26, 2020-02-27}**（各 1,000，合计 2,000）；**D = 码 ∈ 分钟域 ∧ 日期 ∈ 缺日集**（03-31 的 4,941）。若误按「整日归 C」实现会得 C=2,116 / A 少 123——恒等式仍为 0 但与 RESEARCH §3.3 数字不符；
4. 输出 `out/data_alignment.json` + `.md`；恒等式残差必须为 0（§8 INV-6）。

### 3.4 控制流

```
--contract? ──► 既有契约分支（不变）
--alignment-audit? ──► audit_alignment → 写 out/data_alignment.json/.md → exit 0
--calibrate? ──► build()（含 data_alignment）→ coverage_gate（不变）→ run_calibration
                 → attach_panel_meta → write_report（含对齐节）
默认（无 flag）──► 既有 capacity_impact 路径，零新增 IO / 零新增键
```

### 3.5 ADR-0010 三问（新增面）

| 新增面 | ① 放哪层 | ② 激活条件 | ③ 未激活副作用 |
|---|---|---|---|
| `data_alignment` 块 | Layer-1（运行时证据） | `--calibrate` | 默认路径不构造；`panel_hash` 不含该键 |
| `--alignment-audit` | Layer-1（离线工具入口） | 显式 flag | 不 import `alignment` 模块、不读额外文件 |
| `alignment.py` | Layer-1 | 仅被审计分支 import | 生产链路零引用 |

## 4. 接口定义

### 4.1 `DailyRef` 增量（panels.py L40-L48）

```python
@dataclass
class DailyRef(object):
    adv: Optional[pd.DataFrame] = None
    universe: Optional[pd.DataFrame] = None
    industry: Optional[pd.DataFrame] = None
    mv_rank: Optional[pd.DataFrame] = None
    days_by_month: Optional[Dict[str, int]] = None
    # v399 P-008（D1/D3）：逐日行数与交易日列表；默认 None 保持向后兼容
    rows_by_day: Optional[Dict[str, int]] = None
    dates_by_month: Optional[Dict[str, List[str]]] = None
```

### 4.2 `data_alignment` 块（`build()` 返回）

```python
{
  "scope": "matched_days",              # 主口径：分钟与日频都有的交易日
  "window": ["2020-01", "2023-03"],
  "months": 39,
  "matched_days": 786,
  "daily_days": 787,
  "total": {"minute": 3442081, "daily": 3523738, "diff_pct": -2.32,
            "daily_full": 3528865, "diff_full_pct": -2.46},
  "monthly": [
      {"month": "2020-01", "minute": 60111, "daily": 60861,
       "diff_pct": -1.23, "minute_days": 16, "daily_days": 16,
       "zero_amount": 181},
      ...
  ],
  "outlier_days": [
      {"date": "2020-02-26", "minute": 2782, "daily": 3840, "diff_pct": -27.55},
      {"date": "2020-02-27", "minute": 2782, "daily": 3847, "diff_pct": -27.68},
  ],
  "missing_minute_days": [{"date": "2023-03-31", "daily": 5127}],
  "unmatched_minute_days": 0,
  "daily_rows_available": true,
  "zero_amount": {"pairs": 7917, "share_pct": 0.23,
                  "peak_month": "2022-05", "peak_share_pct": 1.0843},
  "thresholds": {"outlier_abs_pct": 5.0}
}
```

- `monthly[*].daily` 与 `total.daily` 均为**匹配日口径**（与 RESEARCH §3.1 一致）；
- `total.daily_full` / `diff_full_pct` 为含未匹配日的全窗口披露（3,528,865 / −2.46%），满足 U-4「双口径全量披露」；月表仍按匹配日，2023-03 的全口径 −7.61% 由 `missing_minute_days` 定位；
- `daily_days` 为日频窗口交易日数（787），`matched_days` 为两侧都有的交易日（786）；
- 缺日不计入 `outlier_days`（避免 −100% 噪声），单列 `missing_minute_days`；
- `unmatched_minute_days`：分钟有、日频无的交易日数（本仓实测 0），非零时 `diff_pct` 只按匹配日计；
- `zero_amount.pairs` 由 `amount_day == 0` 直接计数（无额外 IO；实测 7,917，见 RESEARCH §3.3）；
- 全部计数/比率转成 Python `int` / `float` 后返回，禁止直接塞 numpy 标量（保证 `json.dumps` 可用）。

### 4.3 审计函数（`alignment.py`）

```python
def audit_alignment(cfg, loader, close, start=None, end=None):
    """39 月分钟↔日频行数三方分解（只读）。

    Args:
        cfg: CalibrationConfig（取窗口/σ 等口径）
        loader: MinuteLoader（提供 root / available_months）
        close: 日频收盘矩阵（index=交易日，columns=股票代码）
        start/end: 可选窗口覆盖（默认 cfg.minute_start / minute_end）

    Returns:
        dict：totals / code_universe / months / outlier_days /
              missing_minute_days / identity
    """
```

```python
def write_alignment_report(payload, json_path):
    """写 JSON + 同名 .md；返回落盘路径列表。"""
```

### 4.4 warning token（追加到 `minute["evidence_warnings"]`）

| token | 触发 | 示例 |
|---|---|---|
| `data_alignment_truncation` | 匹配日 `|diff_pct| > 5` | `data_alignment_truncation: 2020-02-26 (-27.55%); 2020-02-27 (-27.68%)` |
| `data_alignment_missing_day` | 日频有、分钟无 | `data_alignment_missing_day: 2023-03-31 (daily=5127)` |
| `data_alignment_partial` | `rows_by_day` 未注入 | `data_alignment_partial: 缺少日频逐日行数，仅记录分钟侧` |

## 5. 替代方案

### 5.1 方案 A：运行时 counts-only + 离线三方分解（选择）

- 优点：校准路径零额外 IO、内存增量 O(39)；归因能力完整且只在按需审计时付出代价；默认输出与 `panel_hash` 零变化；
- 缺点：两处实现（运行时 counts / 离线 sets）需保持一致口径；
- 选择理由：同时满足 U-1/U-3 的「必须告警」与 U-4 的「必须三方分解」，且不触碰生产数值链路。

### 5.2 方案 B（否决）：剔除 2020-02 整月或 02-26/27 两日

- 优点：消除截断噪声；
- 否决理由：月成交额必降 **9.29%**，全窗口 `c` 仅变 **+0.098%**；并破坏 39 月窗口与既有形成期计数（RESEARCH §6.4 U-1）；
- 代价：窗口不完整，下游 `panel_hash` / 覆盖度 / 衰减曲线全部需要重算。

### 5.3 方案 C（否决）：上游过滤 `amount==0` bar

- 优点：停牌日不进入 σ/λ；
- 否决理由：全窗口 `c` 仅变 **+0.428%**、codes 不变（5,029）、λ 样本 −91；`n_bars` 不进入下游（RESEARCH §6.4 U-2）；
- 代价：改写 bar 级口径，`panel_hash` 输入（`n_lambda`/`n_samples`）与既有基线需重建。

### 5.4 方案 D（否决）：用日频数据合成 2023-03-31 分钟 bar

- 优点：补齐 787/787；
- 否决理由：无盘中路径/成交量分布，合成即伪造；该日占 3 月成交额 **4.46%**（RESEARCH §6.4 U-3）；
- 代价：不可逆的数据污染，且违反 E1 取证原则。

### 5.5 方案 E（否决）：只报交集口径单一指标

- 优点：表最简单；
- 否决理由：交集把 A 按构造消除，残差只度量 B（2022-05 峰值 **1.084%**），**不能确认 A 是主因**（RESEARCH §6.4 U-4）；
- 代价：归因结论失真，P-008 验收 ② 无法闭合。

### 5.6 方案 F（否决）：把 5% 偏差做成硬门禁

- 优点：可机械阻断坏数据；
- 否决理由：代码域基线常年 −1%~−3%，2020-02 达 −3.90%，阈值附近误报风险高；且**新增门禁属 Layer-1 不可逆变更**，超出 P-008 裁决范围（本设计 D8 只告警）；
- 代价：门禁误杀会让 39 月校准不可运行，需回退门禁并重跑基线。

### 5.7 方案 G（否决）：运行时保留日频逐日代码集做全量归因

- 优点：一次加载即可输出 A/B/C/D；
- 否决理由：787 日 × ~4.5k 码的 Python 集合常驻内存约数百 MB（E4 数量级估算：~4,500 码/日 × 787 日 × ~90 B/项 ≈ 0.3 GB，复审 F-6），且每次校准都要付出；归因并非常规校准的必需输出（D5）；
- 代价：校准内存峰值上升、运行时间增加，收益仅为省一次离线审计。

## 6. 数据结构

### 6.1 `data_alignment`（运行时）

见 §4.2。字段扩展规则：
- 新增字段只能**追加**，不得改名；`scope` 固定 `"matched_days"`；
- `monthly` 行数 = 可用月份数（本仓 39）；
- 所有百分比保留 2 位小数（`diff_pct`）、零成交占比保留 4 位（`share_pct`）。

### 6.2 审计 JSON（`out/data_alignment.json`）

```json
{
  "window": ["2020-01", "2023-03"],
  "scope": {"matched_days": 786, "daily_days": 787},
  "totals": {
    "minute": 3442081, "daily_full": 3528865, "daily_matched": 3523738,
    "both": 3434164, "minute_only": 7917,
    "daily_only_full": 94701, "daily_only_matched": 89574,
    "A_matched": 87574, "A_full": 87760, "C": 2000, "D": 4941
  },
  "code_universe": {
    "minute": 5029, "daily": 5273,
    "daily_only": 244, "minute_only": 0,
    "daily_only_prefix": {"9": 239, "8": 3, "3": 1, "6": 1}
  },
  "identity": {
    "matched": "87574 + 2000 - 7917 = 81657",
    "full": "87760 + 2000 + 4941 - 7917 = 86784",
    "residual": 0
  },
  "months": [{"month": "2020-01", "...": "..."}],
  "outlier_days": [{"date": "2020-02-26", "minute": 2782, "daily": 3840,
                    "diff_pct": -27.55}],
  "missing_minute_days": [{"date": "2023-03-31", "daily": 5127}]
}
```

- A/C/D 拆分按 §3.3 的**码级规则**执行，输出必须与 RESEARCH §3.3 的 87,760 / 2,000 / 4,941 逐数一致（复审 F-7）。

## 7. 错误处理

| 错误场景 | 处理方式 | 用户可见信息 |
|---|---|---|
| `rows_by_day` 未注入（`DailyRef()` 旧构造） | 跳过逐日比对，`data_alignment.daily_rows_available=false` | `data_alignment_partial` warning |
| `dates_by_month` 缺失 | 只报文件数缺口（既有 partial 语义），不命名缺日 | 无新增 warning |
| 分钟某日无对应日频行（分钟独有日） | 该日不计入匹配日；计入分钟侧总量 | `data_alignment` 内 `unmatched_minute_days` 计数 |
| 日频某日行数为 0 / 全部 NaN | 该日不进日均值；`diff_pct=null` | 无 |
| 单月 `agg` 为空 | 沿用既有「整月剔除 / partial」路径 | 既有 warning |
| `--alignment-audit` 但分钟根缺失 | 抛 `CalibrationUnavailable`，打印一行 | 退出码 2（与 `--calibrate` 同） |
| 审计恒等式残差 ≠ 0 | **不落盘成功态**：`identity.residual` 非 0 时写 JSON 并在 md 顶部标红 | `alignment_identity_failed`（json 字段）+ **退出码 2**（复审 F-3；D8 的「不改退出码」仅约束 `--calibrate` 路径） |

## 8. 不变式（Invariants）

1. **INV-1** 默认 `out/capacity_impact.json` SHA 逐位不变（`82728CE1…`）；
2. **INV-2** `panel_hash` 逐位不变：hash payload（`panels.py` L425-L438）**不含** `data_alignment`；
3. **INV-3** 39 月窗口不变：不删除、不新增月份（`2020-01 ~ 2023-03`）；
4. **INV-4** 零成交 bar 全部保留：λ / σ / impact 链路零改动（`amount==0` 不参与任何过滤）；
5. **INV-5** 对齐告警**非阻断**：不新增门禁、不改 `coverage_gate`、不改退出码；
6. **INV-6** 审计恒等式残差恒为 0：匹配日 `A+C−B = daily_matched−minute`；全窗口 `A+C+D−B = daily_full−minute`；
7. **INV-7** 校准路径零额外分钟 IO：`data_alignment` 只用 `build()` 已加载的 `agg`；
8. **INV-8** `DailyRef` 向后兼容：新字段默认 `None`，`DailyRef(days_by_month={})` 等旧构造仍可运行；
9. **INV-9** 审计入口按需：无 `--alignment-audit` 时不 import `alignment.py`、不读额外文件。

## 9. 幻觉抑制审查（Step 4 Review，已于 2026-11-22 执行）

### 9.1 设计基于已验证的调研结论

- [x] 所有设计决策可追溯到 RESEARCH.md（Step 4 逐条复核：D1-D8 锚点均存在于 RESEARCH v1.4 §3.1/§3.2/§6.4/§6.5，数字逐数一致）
- [x] 无未经验证的假设（§5.7 内存估算已标 E4；zero_amount 逐月读数经缓存实测复核）
- [x] 无论证驱动的归因扭曲（D1-D4 均引用裁决原文的 Δc 敏感性，未为论证强度裁剪「c 不可识别→生产回退 0.5」这一反面事实）

### 9.2 替代方案审查

- [x] 至少列 2 个替代方案（§5.2-§5.7 共 6 个否决方案）
- [x] 每个替代方案有明确的否决理由与代价

### 9.3 职责边界审查

- [x] 职责边界清晰（§2.3）
- [x] 不越界吞并数据治理 / 门禁定标 / 冲击模型改进

> 说明：§9.1 三项已于 Step 4 独立 pass（异构基座第二视角）逐条核验后勾选（RULE-1：勾选发生在正文完稿之后的独立审查轮，非并发自查）。

## 10. 对实施的输入

### 10.1 变更白名单

| 文件 | 动作 |
|------|------|
| `backtest/execution/shell/panels.py` | `DailyRef` 两字段；`build()` 内 `_align_month` 累加；返回 `data_alignment` |
| `backtest/execution/shell/alignment.py` | 新增：`audit_alignment` + `write_alignment_report` |
| `scripts/verify_capacity_impact.py` | `daily_ref` 注入逐日行数；`attach_panel_meta` 透传；`--alignment-audit` 分支 |
| `backtest/execution/shell/report.py` | 校准 md 增「数据行数对齐」节（guard） |
| `tests/test_minute_panels.py` | T398-1 ~ T398-5、T398-8（builder 侧） |
| `tests/test_data_alignment.py` | 新增：T398-6（审计恒等式）、T398-7（报告渲染） |
| `docs/PROGRESS.md` | Step 3 / 4 状态回填 |

**不在白名单**：`loaders.py`（分钟加载口径）、`core/impact.py`、`config.py`、`out/capacity_impact.json`、`out/panel_cache/*`、覆盖度门禁阈值。

### 10.2 测试清单（先红后绿）

| 编号 | 断言 | 前置（红） |
|---|---|---|
| T398-1 | stub `DailyRef.rows_by_day` 构造 1 个 −27% 日 → `outlier_days` 含该日 + `data_alignment_truncation` warning | 现无 `data_alignment` 键 → KeyError |
| T398-2 | stub `dates_by_month` 含 1 个分钟无文件的日 → `missing_minute_days` + warning | 现无缺日命名 |
| T398-3 | `agg.amount_day` 含 3 行 0 → `zero_amount.pairs=3`，且 λ/σ 结果与基线逐位相同 | 现无零成交统计 |
| T398-4 | 同一输入两次 `build()` → `panel_hash` 相同；且**注入 `rows_by_day` 与不注入**两次 `build()` → `panel_hash` 逐位相同（INV-2 的行为化断言；复审 F-2：原「payload 键集不含 data_alignment」不可直接观测，payload 为 `_panel_hash` 局部变量） | 实现前无 `rows_by_day` 字段，注入对照不可构造 |
| T398-5 | `DailyRef()`（无逐日行数）→ `data_alignment_partial` warning，不抛异常 | 现实现会跳过；未定义 warning |
| T398-6 | 合成 4 日小样本 → 审计 `A/C/D/B` 与恒等式残差 0（双口径） | 现无 `alignment.py` |
| T398-7 | 校准 payload 含 `panels.data_alignment` → `render_markdown` 出现「数据行数对齐」节；不含则无该节 | 现报告无该节 |
| T398-8 | builder 护栏：`monthly` 每行键集固定为 `{month, minute, daily, diff_pct, minute_days, daily_days, zero_amount}`；39 月实跑断言（E2）见 §10.3 | 现无该块 |

### 10.3 基线与验收

- 全量：`≥2057 passed / 15 skipped / 0 failed`（N = 新增数）；
- 默认 SHA `82728CE1…` 三方一致（跑前备份 / 跑后 / 复跑）；
- `--calibrate` 重跑：`data_alignment.total` 与 RESEARCH §3.1 逐数一致；warning 含 `2020-02-26` / `2020-02-27` / `2023-03-31`；
- `panel_hash` 与改码前备份逐位相同（INV-2 第二源）；
- `--alignment-audit` 实跑：恒等式残差 0、A/B/C/D 与 RESEARCH §6.5 一致；
- `coverage_gate` 源码零改动、退出码行为不变。

## 11. 未决项登记（四元块）与决策矩阵

**11.1 未决项登记**：

- **U-1 运行时 5% 阈值的误报面**
  - **判据**：39 月实跑 `outlier_days` 仅含 2020-02-26/27（与 RESEARCH §3.2 一致）；若新增误报，逐日复核归因
  - **触发条件**：实跑 `outlier_days` 出现非 02-26/27 日期，或分钟源/代码域变更
  - **当前倾向**：维持 5%（P-008 验收口径），仅告警不阻断
  - **证据等级**：E1（Step 9 实跑读数）

- **U-2 审计扫描耗时**
  - **判据**：`--alignment-audit` 单次 ≤ 3 分钟（列投影口径；RESEARCH 探针实测 45.3 s）
  - **触发条件**：实测 > 3 分钟，或审计被要求纳入默认路径
  - **当前倾向**：按需执行，不纳入默认路径（D6）
  - **证据等级**：E1（Step 9 计时）

**11.2 决策矩阵**：不启用。本批变更均可回退（Type-2）：新增键/新入口/新 warning，均有回退点（移除 flag、删除块）；无真值源或契约级不可逆变更。

---

## 12. 异构复审记录（Step 4，2026-11-22）

### 12.1 复审方式与输入

- **异构性（RULE-5）**：复审会话与 DESIGN v1.0 撰写会话属**不同模型基座**；reviewer 只标记发现（单向权限），修复在记录之后按 F 编号由实现侧执行并升 v1.1；
- **审查输入**：DESIGN v1.0 draft 全文 + RESEARCH v1.4 verified + 源码只读核对（`panels.py` / `loaders.py` / `report.py` / `verify_capacity_impact.py` / `tests/`）+ 运行时取证（`out/panel_cache/*.npz` 零成交计数、`out/capacity_impact.json` SHA）。

### 12.2 维度矩阵

| 维度 | 结论 | 关键依据 |
|------|------|---------|
| V1 决策与调研一致性 | PASS_WITH_FIXES | D1-D8 锚点齐、数字逐数一致；**F-7**（A/C/D 分类规则歧义）修复后闭合 |
| V2 架构与职责边界 | PASS | counts-only/离线分层成立；ADR-0010 三问齐；职责外/能力边界清晰；§5.7 内存估算标 E4（F-6） |
| V3 接口可实现性 | PASS_WITH_FIXES | DailyRef 向后兼容核实（tests L86/L799/L814 旧构造全兼容）；**F-4**（日频码域定义）修复后闭合 |
| V4 测试清单可执行性 | PASS_WITH_FIXES | `render_markdown`（report.py L46）锚点核实；warning 断言全为 substring 风格（13 处，新增 token 不破坏）；**F-2**（T398-4 观测性）修复后闭合 |
| V5 不变式与验收可核性 | PASS_WITH_FIXES | **INV-1 基线经 E1 核实**：`out/capacity_impact.json` 当前 SHA 前 8 = `82728CE1` 与设计引用一致；**F-3**（审计失败退出码）修复后闭合 |

### 12.3 机械取证（E1/E2，复审轮新增）

| 取证手段 | 结果 |
|---|---|
| `Get-FileHash out/capacity_impact.json`（E1） | SHA256 前 8 = `82728CE1`，INV-1 基线有效 |
| `out/panel_cache/*.npz` 全 39 月 `amount_day==0` 计数（E2） | 总 7,917 / 3,442,081 = 0.230%；峰值 2022-05 = 972（1.0843%）；2020-01 = 181、2020-02 = 64、2023-03 = 146 —— 与 §4.2 示例值逐数一致 |
| 源码锚点核对（E3，本批文档） | `DailyRef` L40-48、`_panel_hash` L424-440、`render_markdown` L46、`coverage_gate` L712 均有效 |
| tests 断言风格扫描（E1） | 13 处 `evidence_warnings` 断言均为 `any(...in w...)` 子串式，新增 alignment token 不破坏既有用例 |

### 12.4 发现与处置（全部已落盘至 v1.1）

| 编号 | 级别 | 位置 | 发现 | 处置 |
|------|------|------|------|------|
| F-7 | **P2 规则歧义（可致数字错）** | §3.3 离线步骤 3 | 「C（窗口内有、当日无）」歧义：02-26 的 daily_only=1,058 = 1,000（码∈分钟域→C）+ 58（码∉分钟域→A）。按「整日归 C」实现会得 C=2,116 / A 少 123——恒等式仍为 0 但与 RESEARCH §3.3（87,760/2,000/4,941）不符 | 改为码级规则三拆（A=码∉分钟域；C=码∈域∧截断日；D=码∈域∧缺日），§6.2 加对齐要求 |
| F-2 | P3 可测性 | §10.2 T398-4 | 「payload 键集不含 data_alignment」不可直接观测（payload 为 `_panel_hash` 局部变量） | 改行为化断言：注入/不注入 `rows_by_day` 两次 build，`panel_hash` 逐位相同 |
| F-3 | P3 可核性 | §7 | 审计恒等式失败未定义退出码，不可机械判定 | 补退出码 2，并注明 D8 仅约束 `--calibrate` 路径 |
| F-4 | P3 定义精度 | §3.3 步骤 2 / §4.3 | 日频码域未写「窗口内非空并集」；`close` 全历史 5,688 列，直接取列数会错 | 补定义与反例警示 |
| F-6 | P3 证据等级 | §5.7 | 「约数百 MB」为数量级估算未标级 | 标 E4 并附估算式（≈0.3 GB） |

### 12.5 结论

**PASS_WITH_FIXES**：1×P2 + 4×P3，全部修复已落盘至本版（v1.1）；V1-V5 无未闭合项；INV-1~9 全达成（INV-1 基线经 E1 复核）。设计可进入 Step 5（IMPLEMENTATION.md）。

---

**Review 签字**: Step 4 独立复审（异构基座第二视角，RULE-5；五维矩阵 + E1/E2 机械取证；F-7 P2 + F-2/F-3/F-4/F-6 P3 已处置）日期: 2026-11-22
