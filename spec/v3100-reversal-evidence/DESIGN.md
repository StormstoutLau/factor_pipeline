# 设计文档：截面 T+1 reversal 真实现（P-003，口径 A）

---
id: v3100-reversal-evidence-DESIGN
type: design
version: 1.3
status: verified
date: 2026-11-21
depends: [v3100-reversal-evidence-RESEARCH]
upstream: null
---

> **Feature**: P-003「截面 T+1 reversal 真实现」——用「交易方向 × 截面价格」的已实现反转替代 `temporary_share` 的组合日超额 AR(1) 代理。
> **创建日期**: 2026-11-21
> **状态**: v1.3 verified（Step 3 产出 v1.0；Step 4 异构复审 PASS_WITH_FIXES（3×P2 + 2×P3 已全部处置回写，见 §12.2）；v1.3 = Step 9/10 回填：勘误 E-2、锚点刷新、审计留痕见 §12.4）
> **Spec 步骤**: Step 3-4（v1.3 为 Step 9-10 回填）
> **基于调研**: [RESEARCH.md](./RESEARCH.md) **v1.3 verified**
> **批次档位**: **T1**（证据层读数替换 + 新输出键，不改成本/容量口径）
> **包版本**: **3.9.5**（patch；用户 2026-11-21 确认，见 §12.1；批次目录名 `v3100-reversal-evidence` 仅作批次代号保留）
> **口径裁决（不可推翻）**: 口径 A——仅证据层真实现，`cost_by_h` / `net(h)` / 容量读数不变，`core/decay.py` 零改动。

---

## 1. 设计目标

把 `temporary_share` 从「组合日超额序列的 AR(1) 代理」替换为**交易事件级的截面 T+1 反转读数**：

1. 事件 = 形成日权重变动 `Δw`（`s=sign(Δw)`、`a=|Δw|`），度量「刚被交易的股票在次日是否朝不利方向回落」；
2. 新增 `reversal_bps`（bps 单位，>0 = 交易后不利回落）与事件加权 `share`，替代旧代理的三元组语义；
3. 旧代理降级为 `temporary_proxy_ar1` 仅作对照，**不删除**；
4. 全部改动限于证据层，`cost_by_h` / `net(h)` / `panel_hash` / 默认 SHA 逐位不变。

## 2. 设计依据

### 2.1 调研结论 → 设计决策

| 调研发现（RESEARCH 锚点） | 设计决策 | 编号 |
|---|---|---|
| 现状代理样本单位错：组合日收益不是交易事件（§3.1/§4.1-1） | 改为事件级样本，事件来自 `w` 的月频差分 | D1 |
| C1（close-to-close + 截面 demean）与登记公式逐字一致；C2 为最强对照（§3.3.2） | C1 主口径、C2 稳健性对照、U-1 实测裁决 | D2 |
| 事件定义 `s/a`、过滤 `\|Δw\|≥1e-8`、`w≥0`（§3.3.1） | 事件构造在脚本层完成，`core` 只收数值数组 | D3 |
| 统计量 `reversal_bps` / `share`（§3.3.3） | 事件加权 + 按形成月聚类 bootstrap，月度充分统计量 | D4 |
| 同一形成日数千只股票高度相关（§3.3.3） | 禁止事件级重采样；聚类单位 = 形成月 | D4 |
| 输出契约 `rt/rt1/side/weight/month`（§3.3.4） | `panels.temporary` 承载事件数组（仅内存） | D5 |
| 日频 `t+1` 过滤字段未接入 `P`（§3.7/§5.3） | 新增 `P['impl_daily']` / `P['open_adj']`，**不塞 `P['facts']`** | D6 |
| `load_implementability` 无 `limit_down`（§3.4） | 镜像实现 + 退化披露双开关 | D7 |
| 无事件样本需回退旧代理（§3.3.4 兼容策略） | 按键存在性判定，保留旧 warning | D8 |
| 旧代理读数 `[0, 0, 0.004225]`（E1） | 仅对照，不作为新读数的先验 | D9 |
| 工件膨胀风险（§6.3） | 事件数组不落盘；`attach_panel_meta` 白名单不新增数组键 | D10 |
| 用户裁决口径 A（不可推翻） | 不接线 `cost_by_h`；`net` 消费链零改动 | D11 |
| 版本号惯例 v3.9.1~v3.9.4 均为 patch | **3.9.5**（用户确认） | D12 |

### 2.2 相关 ADR / 治理文件

| 文件 | 条款 | 对本设计的影响 |
|------|------|--------------|
| [SPEC_PROCESS.md](../SPEC_PROCESS.md) | Step 3-4 设计 + 幻觉抑制审查；未决项四元块 | §11 承接 U-1~U-5 |
| [SPEC_COMPLIANCE.md](../../docs/SPEC_COMPLIANCE.md) §6 | 同基座降级声明（D-001） | §12 复审独立性按实际基座声明 |
| [PROGRESS.md](../../docs/PROGRESS.md) P-003 | 口径 A 裁决 + 验收标准 ①②③ | §10.1 通过线 |
| [RESEARCH_P003_P007_DECISIONS.md](../../docs/research/RESEARCH_P003_P007_DECISIONS.md) §2 | 反转 ≡ 临时冲击，不与价差/冲击重复计价 | D11 不接线成本 |

### 2.3 职责边界

**本批职责内**：

- 事件级反转统计量的工程契约与实现（`core/impact.py::cross_section_reversal`）；
- 事件样本构造（脚本层）、面板装配（`panels.py`）、结果透传（`runner.py`）；
- `limit_down` 镜像标记（`verify_long_side_research.py`）；
- 证据层读数 / 输出键 / 警告文案 / 测试 / 版本号。

**本批职责外（显式不做）**：

| 不做的事 | 理由 |
|---|---|
| 把 `reversal_bps` 接入 `cost_by_h` / `net` | 用户裁决口径 A（不可推翻） |
| 改滑点/冲击模型、`rho`、`alpha0`、`core/decay.py` | 与本批正交；`core/decay.py` 零改动是硬约束 |
| 改权重构造 / 换手 / 股票池 | 只读 `w`，不改变 `w` |
| P-007 限价取整口径（已并入 P-006） | 不在本批范围 |
| C3 VWAP 主口径 | `amount/volume` 单位未校准（RESEARCH §3.3.2） |
| 重写 v3.9.4 已验证文档 | 只新增本批四件套 |

## 3. 架构设计

### 3.1 整体架构

```
[脚本层 scripts/verify_capacity_impact.py]
  build_panels()
    ├─ adj_price / close                （现有）
    ├─ P['open_adj'] = open × adj       （新增，C2 用）
    └─ P['impl_daily'] = {suspend, st, limit_up, limit_down}  （新增，全量日频）
  build_portfolio_panels(P, cfg)
    └─ portfolio['reversal'] = {rt, rt1, side, weight, month, price_basis}   ← 事件数组（内存）
                  ↓
[装配层 backtest/execution/shell/panels.py]
  build_daily_panels(cfg, daily, portfolio, impact_fit)
    ├─ out['temporary']          = 真实现事件数组（有事件时）/ 旧代理 r1/rev1（回退时）
    ├─ out['temporary_basis']    = 'cross_section_t1' / 'portfolio_ar1_proxy'
    ├─ out['temporary_proxy_ar1']= 旧代理三元组（仅打分对照）
    └─ out['reversal_counts']    = 过滤计数
                  ↓
[计算/透传层 backtest/execution/shell/runner.py]
  ├─ 真实现：core/impact.py::cross_section_reversal(...) → temporary_share + reversal_bps
  └─ 回退：temporary_share(r1, rev1)（现有路径，零改动）
                  ↓
[落盘层]
  result['temporary_share'] / ['temporary_basis'] / ['reversal_bps'] / ['reversal_price_basis']
  attach_panel_meta 白名单不新增事件数组键（数组不落盘）
```

### 3.2 模块划分

| 模块 | 职责 | 输入 | 输出 | 依赖 |
|------|------|------|------|------|
| `verify_long_side_research.load_implementability` | 日频可实施性矩阵 | `market_data/*.pkl` | `{suspend, st, limit_up, limit_down, ind}` | pandas / 现有 |
| `verify_capacity_impact.build_panels` | 日频 → 月频面板；新增 `open_adj` / `impl_daily` | `market_data` | `P` | 上者 |
| `verify_capacity_impact.build_portfolio_panels` | 权重 + 事件样本构造 | `P`、`cfg` | `portfolio['reversal']` 等 | 上者 |
| `impact.cross_section_reversal` | 事件加权统计量 + 聚类 bootstrap | 5 个 1d 数组 | `dict`（§4.1） | numpy + `effect_size.stationary_bootstrap_indices` |
| `panels.build_daily_panels` | 装配 `temporary` 契约 + 兼容回退 | `portfolio` | `out[...]` | 现有 |
| `runner.run_execution_capacity` | 真/旧分支、结果键 | `panels` | `result` | `impact` |

### 3.3 数据流

1. `build_panels` 一次性把**全量日频** `open × adj` 与四个可实施性矩阵挂到 `P`（约 39 月 × 5000 列 × 4，float/bool 稀疏，内存增量远低于分钟层）；
2. `build_portfolio_panels` 以形成日 `w.index` 为锚，取 `t = 形成日`、`t+1 = 下一交易日`（`close.index` 的 `searchsorted` 精确前移，不用自然日）；
3. 逐事件过滤（§4.3 顺序）后，把 `rt/rt1/side/weight/month` 五数组放入 `portfolio['reversal']`；
4. `build_daily_panels` 原样搬到 `out['temporary']`，并计算旧代理三元组（若可从 `excess_d` 得到）放入 `out['temporary_proxy_ar1']`；
5. `runner` 按键存在性选择真实现/回退；真实现另输出 `reversal_bps`。

### 3.4 控制流

- 默认（无 `portfolio['reversal']`）→ 旧代理路径，与今日行为**逐位一致**；
- 校准（39 月）→ 真实现路径；C2 对照由 `price_basis` 切换（U-1 实测时同跑两次）；
- 退化（事件 < 3 或 `Σ a x² = 0`）→ 不抛异常：`share = [0,0,0]`、`reversal_bps` 三值 `NaN`，warning `cross_section_reversal_degraded`。

## 4. 接口定义

### 4.1 `core/impact.py::cross_section_reversal`

```python
def cross_section_reversal(rt, rt1, side, weight, month,
                           n_bootstrap=1000, seed=20261121):
    """事件加权截面 T+1 反转统计量（纯 numpy，无 IO）。

    Args:
        rt:     截面 demean 后 t 日收益（未乘方向），shape (n_events,)
        rt1:    截面 demean 后 t+1 日收益（未乘方向），同 shape
        side:   ±1 交易方向，同 shape
        weight: |Δw| 事件权重，同 shape，非负
        month:  形成月标签（0..T-1 整数），聚类单位，同 shape
        n_bootstrap: 聚类重抽样次数
        seed:   固定随机种子

    Returns:
        {
          'temporary_share': [point, lo, hi],      # clip(-Σa·x·y/Σa·x², 0, 1)
          'reversal_bps': {'point','lo','hi'},      # -(Σa·y/Σa)×1e4
          'buy':  {'point': ..., 'lo': ..., 'hi': ..., 'n': int},
          'sell': {'point': ..., 'lo': ..., 'hi': ..., 'n': int},
          'n': int, 'n_months': int, 'degraded': bool,
        }

    Raises:
        无（输入长度不一致由调用方保证；退化走 degraded 分支）
    """
```

**实现要点**：

- `x = side * rt`、`y = side * rt1`；
- `point` 用全样本充分统计量直接算；
- 分侧：`side=+1` / `side=-1` 子集各自算 `reversal_bps`（权重仍 `a`）；
- bootstrap：先按 `month` 聚合出 `(Σa, Σa·x², Σa·x·y, Σa·y)` 四组长度 `n_months` 的数组（分侧再各四组），再 `stationary_bootstrap_indices(n_months, n_bootstrap=n_bootstrap, block_size=1, seed=seed)` 重抽样月份索引（`block_size=1` 即 cluster 级 iid 重采样）。**签名核对（Step 4 F-1）**：实际签名为 `stationary_bootstrap_indices(n, n_bootstrap=1000, block_size=None, seed=0)`（[backtest/effect_size.py L128-133](file:///f:/Coding/factor_pipeline/backtest/effect_size.py#L128-L133)；由 `impact.py` 内 `from ...effect_size import` 解析），本调用形态兼容，零新增依赖；`n_bootstrap ≥ 100` 约束由默认 1000 满足；
- 每次重抽样由聚合量重建 `share` / `reversal_bps`，取 2.5/97.5 百分位；**端点用 `min(lo, point)` / `max(hi, point)` 夹逼**，与 `temporary_share` L227 的既有语义一致；
- 退化：`n_months < 3` 或 `Σ a x² <= 0` → `temporary_share=[0,0,0]`、`reversal_bps` 三值 `NaN`、`degraded=True`。

### 4.2 `panels.build_daily_panels` 输出契约

```python
out['temporary'] = {          # 真实现（有事件时）
    'rt': [...], 'rt1': [...], 'side': [...],
    'weight': [...], 'month': [...],
    'price_basis': 'adj_close_to_close_cs',   # C1；C2 为 'adj_intraday_open_close'
}
out['temporary_basis'] = 'cross_section_t1'
out['temporary_proxy_ar1'] = [point, lo, hi]          # 旧代理（仅对照）
out['temporary_proxy_basis'] = 'portfolio_ar1_proxy'
out['reversal_counts'] = {
    'n_events', 'n_months', 'n_buy', 'n_sell', 'n_first_period',
    'n_suspended_t', 'n_suspended_t1', 'n_limit_up_t', 'n_limit_down_t',
    'n_limit_t1', 'n_st', 'n_tiny', 'n_extreme', 'n_missing',
    'n_limit_down_unavailable': bool,
}
```

**回退分支**（无 `portfolio['reversal']` 或键不全）：

```python
out['temporary'] = {'r1': [...], 'rev1': [...]}       # 与今日完全一致
out['temporary_basis'] = 'portfolio_ar1_proxy'
# warning 文案与今日逐字一致（Step 4 F-2 补录逐字文案）：
# "temporary_share 为组合日超额 AR(1) 代理，非 T+1 反转，不进入容量"
# （现位于 panels.py L589；回退路径不得改动此字符串）
```

判定函数（私有）：`_has_reversal_events(portfolio) -> bool`，要求五键齐备且 `len(rt) == len(rt1) == len(side) == len(weight) == len(month)`。

### 4.3 事件过滤顺序（脚本层，`build_portfolio_panels`）

| 步骤 | 条件 | 计数键 |
|---|---|---|
| 1 | `\|Δw\| < 1e-8` 剔除 | `n_tiny` |
| 2 | `w_{t-1} < 0`（理论不可能）断言 | — |
| 3 | 首期建仓打标（不剔除） | `n_first_period` |
| 4 | `suspend_t` 剔除 | `n_suspended_t` |
| 5 | `limit_up_t & buy` / `limit_down_t & sell` 剔除（镜像公式见 §11.1 U-2：`raw_ret <= -(thr - 0.3) & close <= low * 1.001`，与涨停 [verify_long_side_research.py L114](file:///f:/Coding/factor_pipeline/scripts/verify_long_side_research.py#L114) 对称） | `n_limit_up_t` / `n_limit_down_t` |
| 6 | `st_t` 剔除 | `n_st` |
| 7 | `suspend_{t+1}` 或 `P_{t+1}` 缺失剔除 | `n_suspended_t1` / `n_missing` |
| 8 | `limit_up/limit_down_{t+1}` 剔除 | `n_limit_t1` |
| 9 | `\|r\| > 0.5` 剔除 | `n_extreme` |

`n_limit_down_unavailable`：若 `stock_low.pkl` 不可读或单位不符，`limit_down` 置空、该键 `True`，并追加 warning `limit_down_unavailable`（不静默通过，对应 U-2 退化披露）。

### 4.4 `runner` 结果键

```python
result['temporary_share']      # 真实现取 cross_section_reversal['temporary_share']；回退取旧三元组
result['temporary_basis']      # 'cross_section_t1' / 'portfolio_ar1_proxy'
result['reversal_bps'] = {     # 仅真实现分支
    'point', 'lo', 'hi',
    'buy':  {'point', 'lo', 'hi', 'n'},
    'sell': {'point', 'lo', 'hi', 'n'},
    'n', 'n_months', 'price_basis',
}
result['reversal_price_basis'] # 'adj_close_to_close_cs' / 'adj_intraday_open_close'
```

**不改**：`cost_by_h`、`net`、`rho`、`alpha0`、`capacity`、`window_capacity`、`decay`。

## 5. 替代方案

### 5.1 方案 A：事件级 + 聚类 bootstrap + 脚本注入（选择）

- 描述：脚本构造事件 → `panels` 装配 → `runner` 调 `core` 纯函数；聚类按形成月。
- 优点：分层清晰；`core` 可单测（纯数组）；事件数组只在内存；39 个 cluster 的重采样成本 `O(1000×39)`。
- 选择理由：与 §3.1 数据可得性匹配；零新增依赖；回退分支天然隔离。

### 5.2 方案 B：事件级 iid bootstrap（否决）

- 否决理由：同一形成日数千只股票高度相关，事件级重采样会把 CI 压窄到失真（RESEARCH §4.1-5）。

### 5.3 方案 C：在 `panels.py` 内直接读 pandas / 数据源（否决）

- 否决理由：违反执行层分层（`panels` 只做装配，不做 IO）；且会把数据依赖带进最小测试面板。

### 5.4 方案 D：删除旧代理、只保留真实现（否决）

- 否决理由：最小测试面板（无 `w`/事件字段）会失去 `temporary_share`，破坏 `test_temporary_basis_flagged` 等既有语义；且损失新旧对照能力。

### 5.5 方案 E：把 `temporary_share` 键改名为 `reversal_bps`（否决）

- 否决理由：下游文档、报告、校准工件、审计记录连锁改动；口径 A 下无收益。

### 5.6 方案 F：接入 `cost_by_h`（否决）

- 否决理由：用户裁决口径 A（不可推翻）；且反转与冲击/价差叠加会重复计价（上游调研 §2）。

### 5.7 方案 G：C3 VWAP 主口径（否决）

- 否决理由：`amount`/`volume` 单位（千元/手）未校准，主口径不可信；保留为后续观测项。

## 6. 数据结构

### 6.1 事件样本（`portfolio['reversal']`）

```python
{
    'rt': np.ndarray,      # float64, 截面 demean 后 t 日收益
    'rt1': np.ndarray,     # float64, 截面 demean 后 t+1 日收益
    'side': np.ndarray,    # int8, ±1
    'weight': np.ndarray,  # float64, |Δw| ≥ 1e-8
    'month': np.ndarray,   # int32, 0..T-1
    'price_basis': str,    # 'adj_close_to_close_cs' / 'adj_intraday_open_close'
}
```

### 6.2 充分统计量（`cross_section_reversal` 内部）

```python
# 每组长度 = n_months；分侧 ×3（all / buy / sell）
s_a   = np.bincount(month, weights=weight)
s_ax2 = np.bincount(month, weights=weight * x * x)
s_axy = np.bincount(month, weights=weight * x * y)
s_ay  = np.bincount(month, weights=weight * y)
```

### 6.3 `reversal_counts`

见 §4.2；只含 `int` / `bool`，可直接落 JSON，体积 < 1 KB。

## 7. 错误处理

| 场景 | 处理 | 用户可见信息 |
|---|---|---|
| 事件数 < 3 或 `Σ a x² = 0` | 退化分支：`share=[0,0,0]`、`reversal_bps=NaN` | warning `cross_section_reversal_degraded` |
| `n_months < 3` | 同上 | 同上 |
| 五键长度不一致 | `_has_reversal_events` 返回 `False` → 回退旧代理 | warning `reversal_events_malformed` |
| 长度不一致到达 `cross_section_reversal` | **不可能**（Step 4 F-5 澄清）：该输入在 panels 层已被 `_has_reversal_events` 拦截并回退，故 §4.1 `Raises: 无` 成立；若未来出现新调用方，由调用方保证五键等长 | — |
| `stock_low.pkl` 缺失 / 单位不符 | `limit_down` 置空 | `n_limit_down_unavailable=True` + warning |
| `t+1` 超出面板末端 | 该事件剔除，计 `n_missing` | 无（计数披露） |
| `temporary` 为空且无 `w` | 保持今日行为（`temporary_share=None`） | 与今日一致 |

## 8. 不变式（Invariants）

1. **INV-1** 默认 `out/capacity_impact.json` SHA `82728CE1…` 逐位不变；
2. **INV-2** `panel_hash` 改前/改后逐位相同；
3. **INV-3** `cost_by_h` / `net(h)` / `rho` / `alpha0` / `alpha0_anchored` / `impact_fit` / `c` / `capacity` 逐位不变；
4. **INV-4** `core/decay.py` 零改动，`__all__` 恒 5 项；
5. **INV-5** `temporary_share` 保持 `[point, lo, hi]` 且 `point ∈ [lo, hi]`；
6. **INV-6** `reversal_bps.point` 与 `temporary_share.point` 来自**同一次**聚类重抽样；
7. **INV-7** 事件数组（`rt/rt1/side/weight/month`）不写入任何落盘工件；
8. **INV-8** 无事件字段时回退旧代理，warning 文案与今日逐字一致；
9. **INV-9** 零新增第三方依赖，Python 3.9 语法；
10. **INV-10** `n_bootstrap` / `seed` 固定时同一输入两次运行逐位一致。

## 9. 幻觉抑制审查（Step 4 Review）

### 9.1 设计基于已验证的调研结论

- [x] 全部 12 条决策可追溯到 RESEARCH §3/§6 锚点（§2.1 表逐行标注）；
- [x] 无未经验证的假设：C1/C2 差异、新读数、bootstrap 稳定性均保留为 U-1/U-3 待实测；
- [x] 无归因扭曲：旧代理「读数不显著」不被解释为「无反转」，只作为样本单位错的证据。

### 9.2 替代方案审查

- [x] 列 6 个被拒方案（B~G），均有明确否决理由；
- [x] 选择方案 A 的理由与 RESEARCH §6.1 推荐表逐条一致。

### 9.3 职责边界审查

- [x] 职责内/外清单分离（§2.3）；
- [x] 不吞并成本建模、不重定义因子（只读 `w`）。

## 10. 对实施的输入

### 10.1 关键工程约束与通过线

1. 白名单文件（Step 5 只允许改这些）：
   - `scripts/verify_capacity_impact.py`
   - `scripts/verify_long_side_research.py`
   - `backtest/execution/core/impact.py`
   - `backtest/execution/shell/panels.py`
   - `backtest/execution/shell/runner.py`
   - `tests/test_minute_panels.py`
   - `tests/test_execution_capacity.py`
   - 版本 **5 处**：代码 3 处（`config_v2.py` L371 / `__init__.py` L58 / `reporting.py` L40）+ 测试断言 2 处（`tests/test_fix3_version_unification.py` L34 / `tests/test_backtest/verify_fix3_manual.py` L21）
2. 通过线：`2065 + N passed / 15 skipped / 0 failed`（N = T3100-1~10 实际新增数）；先红后绿留痕；
3. Step 9 必须产出：C1/C2 双口径 39 月对照表、新旧读数对照表（替换 RESEARCH §3.5「待 E1」）、`limit_down` 计数；
4. 默认 SHA 与 `panel_hash` 必须 before/after 三方核验（同 v3.9.4 做法）。

### 10.2 风险与缓解

| 风险 | 缓解 |
|------|------|
| `build_panels` 新增全量日频矩阵致内存上升 | 只挂 4 个 bool 矩阵 + 1 个 float `open_adj`；39 月规模 < 100 MB；Step 9 记峰值 |
| `t+1` 交易日对齐错位（自然日/停牌） | 用 `close.index` 位置前移，禁用 `DateOffset(days=1)`；T3100-4 覆盖 |
| C1 被隔夜残差主导 | U-1 判据（同号且量级差 ≤50%）；不满足则 Step 9 复议 C2 |
| 旧测试语义漂移 | 回退分支 protected by INV-8；只增不改旧断言 |
| 39 cluster 区间过宽 | 报告 `n_months` 与端点宽度；U-3 检查 seed/重复数 |
| 事件数组误落盘 | INV-7 + `attach_panel_meta` 白名单（§3.1）；Step 9 核对工件大小 |

## 11. 未决项登记（四元块）

**11.1 未决项**

- **U-1 主口径 C1 vs C2**
  - **判据**：39 月 `reversal_bps` / `share` 两口径同号且量级差异 ≤50%，或分歧有书面裁决
  - **触发条件**：Step 9 首次 39 月校准同时产出 `reversal_price_basis` 两种取值
  - **当前倾向**：C1 为主（与登记公式一致），C2 仅稳健性
  - **证据等级**：待核（需 E1）

- **U-2 `limit_down` 镜像标记**
  - **判据**：`n_limit_down_t > 0` 且买卖两侧过滤计数对称；T3100-5 绿
  - **触发条件**：Step 9 实现日频过滤时
  - **当前倾向**：`raw_ret <= -(thr - 0.3) & close <= low * 1.001`（与涨停 L114 对称）
  - **证据等级**：E3（公式可推导，待实测）

- **U-3 聚类 bootstrap 稳定性**
  - **判据**：1000/2000/5000 reps × 3 seeds 下 `share` 端点差 ≤0.01；`point ∈ [lo, hi]`
  - **触发条件**：Step 9 首跑
  - **当前倾向**：1000 reps、seed=20261121、`block_size=1`
  - **证据等级**：待核（需 E1）

- **U-4 买卖不对称**
  - **判据**：`buy` / `sell` 各自有 CI，报告不强行合并
  - **触发条件**：Step 9 首跑产出分侧读数
  - **当前倾向**：分侧报告 + 合并值仅总览
  - **证据等级**：待核（需 E1）

- **U-5 截面基准选择**
  - **判据**：全市场等权 / 可投资域等权 / 事件样本等权三者 `reversal_bps` 差异 ≤10%
  - **触发条件**：Step 9 敏感性表
  - **当前倾向**：全市场等权（与 `daily_portfolio_excess` 一致）
  - **证据等级**：E3

**11.2 决策矩阵**：不启用。本批全部决策为 **Type-2（可逆）**——`core` 新函数与输出键可回退，配置/口径可切回旧代理；无不可逆结构变更。

## 12. 版本号与复审记录

### 12.1 版本号裁决（2026-11-21，用户确认）

**包版本 = 3.9.5（patch）**。理由：

1. v3.9.1~v3.9.4 均为 patch，其中 v3.9.3 同样新增 `DecayCurve` 与新输出键仍走 patch；
2. 本批不改成本/容量口径（口径 A），仅新增证据层读数与键，向后兼容；
3. 批次目录 `spec/v3100-reversal-evidence/` 仅作批次代号，不随版本号改名（RESEARCH front-matter 已预留该说明）。

**版本落点（6 处）**：`config_v2.py` / `__init__.py` / `reporting.py` + 2 处测试断言；另 `scripts/verify_capacity_impact.py` 工件标题若硬编码版本需同步（P-015② 已登记同类问题，本批只改本批触达处）。

### 12.2 Step 4 复审记录（v1.1 增补，2026-11-21）

> **复审方式**：独立上下文只读子代理（GLM-5.3 基座），先通读本文件与 RESEARCH v1.2，再重放 7 组代码锚点 + 五项对齐统计；主会话逐条核实后处置回写。
> **独立性声明（RULE-4/5，D-001）**：撰写者（本文件 v1.0，DeepSeek 基座）与复审者（GLM-5.3 基座）**不同基座**，构成**真异构复审**；子代理独立上下文、只读、不共享撰写推理链。
> **锚点基线**：commit `9b09f8c`（v3.9.4 工作区）。

**结论**：**PASS_WITH_FIXES**（无 P1；3×P2 + 2×P3，处置后全部关闭 → v1.1 verified）。

**门禁 a-d**：

- **(a) 决策可追溯性：过** —— D1-D12 **12/12** 命中 RESEARCH §3/§6 锚点；
- **(b) 可实施性：过** —— §10.1 白名单 8 类文件与 RESEARCH §6.7 一致；`cross_section_reversal` 为纯 numpy，依赖的 `stationary_bootstrap_indices` 实存且签名兼容（主会话实核 [effect_size.py L128-133](file:///f:/Coding/factor_pipeline/backtest/effect_size.py#L128-L133)）；
- **(c) 未决承接：过** —— U-1~U-5 **5/5** 四元块齐备；B-1~B-5 **5/5** 映射到 INV-1~INV-10；T3100-1~10 **10/10** 在 §10.1 通过线与 §4.3 过滤顺序落位；
- **(d) 内部一致：过（处置后）** —— §4.1↔§4.4 键结构统一；§4.3↔§4.2 计数键一一对应；§7↔§4.1 Raises 矛盾澄清；统计量公式与 RESEARCH §3.3.3 逐字一致。

**发现与处置**：

| # | 级别 | 复审发现 | 处置 |
|---|---|---|---|
| F-1 | P2 | `stationary_bootstrap_indices` 调用描述有参数名漂移风险 | **部分采纳**：主会话实核实际签名 `(n, n_bootstrap=1000, block_size=None, seed=0)`（effect_size.py L128-133），DESIGN 调用形态**兼容**（误报部分）；采纳补精确模块路径 `backtest/effect_size.py` + 签名全文 + `n_bootstrap ≥ 100` 约束（§4.1） |
| F-2 | P2 | 回退分支声称 warning「逐字一致」但未给出逐字文案 | **采纳**：§4.2 补录逐字文案 `"temporary_share 为组合日超额 AR(1) 代理，非 T+1 反转，不进入容量"`（主会话此前实读 panels.py L557-558 确认）+「回退路径不得改动此字符串」纪律 |
| F-3 | P2 | `limit_down` 镜像公式在 §4.3 未展开 | **部分误报**：完整公式已在 §11.1 U-2（`raw_ret <= -(thr - 0.3) & close <= low * 1.001`）；采纳在 §4.3 步骤 5 补公式交叉引用 + 涨停锚点 L114 |
| F-4 | P3 | §4.1 `buy/sell` 结构与 §4.4 runner 键不一致（嵌套 vs 扁平） | **采纳**：§4.1 扁平化为 `{'point','lo','hi','n'}`，与 §4.4 完全对齐 |
| F-5 | P3 | §7「五键长度不一致→回退」与 §4.1「Raises: 无」表述有张力 | **采纳**：§7 补一行澄清——长度不一致在 panels 层被 `_has_reversal_events` 拦截，不会进入 `cross_section_reversal`，`Raises: 无` 成立 |

**锚点重放（7 组）**：`temporary_share` 现实现（impact.py L193-227）一致；`stationary_bootstrap_indices` 存在+签名（effect_size.py L128-133）一致；旧代理构造与 warning（panels.py L550-558）一致；`build_daily_panels` 签名（L543-545）一致；`attach_panel_meta` 白名单（verify_capacity_impact.py L271-307）一致；`build_portfolio_panels` 返回 dict（L212-268）一致；`load_implementability` 仅 limit_up + 涨停公式（verify_long_side_research.py L97-120、L114）一致。

**对齐统计**：D1-D12 12/12；U-1~U-5 5/5；B-1~B-5→INV 5/5（映射：B-1→INV-1、B-2→INV-2、B-3→INV-3、B-4→INV-5/6/10、B-5→INV-4/通过线）；T3100-1~10 10/10；影响文件清单 7/7。复审者关于「新增用例数 N 与基线 2065 统计口径需确认」的提示：§10.1 已写「N = T3100-1~10 实际新增数」，实施时以实际收集数为准登记（不预设 N 值，避免编造）。

**v1.1 结论**：复审通过，允许进入 **Step 5（IMPLEMENTATION 起草）**。Step 5 必须遵守：§10.1 白名单、INV-1~INV-10、§4.2 回退分支逐字文案、先红后绿留痕。

### 12.3 v1.2 勘误（Step 5 发现）

| # | 勘误 | 依据 | 处置 |
|---|---|---|---|
| E-1 | §10.1 原写「版本 4 处 + 2 处测试断言」，实际代码落点 **3 处** + 测试断言 **2 处** = **5 处** | 主会话 grep `3\.9\.4` 实核（9 处命中中 4 处为注释/历史标记）；详见 [IMPLEMENTATION.md](./IMPLEMENTATION.md) §11 | 已就地修正 §10.1；Step 8 按 5 处执行 |

### 12.4 v1.3 Step 9-10 回填与审计留痕（2026-11-21）

**E-2（覆盖月数口径）**：本文「39 月」均指**分钟层覆盖**；证据层锚定月频形成日全集，实测 **73 个形成月 / 72 个有效聚类**（`out/v3100_calibration.json`）。不改代码，读数与旧代理同域可比；RESEARCH §3.5 / IMPLEMENTATION §11 / CHECKLIST §2.4 同步登记。

**锚点刷新（Step 9 落码后）**：`panels.py` 回退 warning → **L589**；`cost_by_h` → **L684-689**；`runner.py` 回退分支 → **L524-541**；`impact.py` 新函数 → **L230-337**。

**Step 10 独立审计**：独立上下文只读子代理（同基座运行，按 D-001 同基座降级声明），结论 **PASS_WITH_FIXES**（0×P1、2×P2、6×P3），Phase 0 总分 **4.60/5（A）**。实测复核：默认 SHA `82728CE1…`、`panel_hash dfcc4e1d…`、`impact/decay.__all__` 各 5 项、T3100 子集 11 passed、版本/架构 12 passed。2×P2（INV-6 共享重抽样无独立测试、脚本层 demean 无测试）与 4×P3（T3100_3 恒真断言、T3100_9 半同义反复、counts 15 键缺整体断言、文档锚点）已登记 CHECKLIST §8.2，按「测试有效性补强」批次处理，不影响口径 A 结论。
