# 设计文档：P-020 tradability 小口径收尾 + 台账同步

---
id: p020-tradability-cleanup-and-ledger-DESIGN
type: design
version: 1.1
status: verified
date: 2026-11-23
depends: [p020-tradability-cleanup-and-ledger-RESEARCH]
upstream: null
---

> **Feature**: P-020（A 台账同步 + B 三项小口径收尾）
> **创建日期**: 2026-11-23
> **状态**: verified（Step 3-4 完成）
> **Spec 步骤**: Step 3-4
> **基于调研**: [RESEARCH.md](./RESEARCH.md)
> **批次档位**: **T1**（Layer-1：`backtest/` + `tests/`）

---

## 1. 设计目标

消除 P-006 遗留的三处「同函数内第二套约定」（eps 双源 / 键归一化缺位 / 公开分支零覆盖），并把 `PROJECT_STATUS.md` 台账推进到 v3.9.9。**默认路径零变更**是硬门槛。

## 2. 设计依据

### 2.1 调研结论 → 决策

| 调研发现 | 设计决策 | 引用 |
|---|---|---|
| F-1-3 构建器 meta 用常量 `_EPS`，推进期用 `policy.eps` | **D1** 构建器取 `policy` 的 eps（`policy=None` → 默认 policy 实例） | RESEARCH §3.1 |
| F-2-1/2 `one_word_*` 无取值断言 | **D3** 新增正向计数用例 | RESEARCH §3.2 |
| F-2-3/4/5 `ref=` 直传零覆盖 | **D4** 新增 `ref=` 直传用例 | RESEARCH §3.2 |
| F-3-1/2/3 `list_date` 未归一，`st_overrides` 已归一 | **D2** 抽 `_norm_code`，精确优先 + 归一化回退 | RESEARCH §3.3 |
| F-4-1/2 台账滞后 | **D6** PROJECT_STATUS 两处同步 | RESEARCH §3.4 |

### 2.2 相关 ADR

| ADR | 决策 | 对本设计的影响 |
|---|---|---|
| ADR-0010 | Layer 判定三问 | 本批触及 `backtest/` + `tests/` → T1 |
| ADR-0004（spec 流程） | 四件套 + Review 门禁 | 本批全流程执行 |

### 2.3 职责边界

- **职责内**：`build_tradability_inputs` 的 eps 取源与键匹配；`tests/` 覆盖补强；台账两文件。
- **职责外**：`apply_tradability` 算法、`compute_limits`、取整/板块/除权裁决、`execution/` 容量路径、`TradabilityInputs` 字段集合。

## 3. 架构设计

### 3.1 整体架构

```
list_date ─┐                    ┌─ no_limit 矩阵 ─┐
st_overrides ┴→ _norm_code 归一 ─┤                 ├→ TradabilityInputs ─→ apply_tradability
policy ─────→ eps 单源 ─────────┴→ meta.one_word_*┘        (policy.eps)
```

### 3.2 模块划分

| 模块 | 职责 | 输入 | 输出 | 依赖 |
|---|---|---|---|---|
| `tradability_inputs._norm_code`（新） | 代码键归一（`split(".")[0].zfill(6)`） | 任意标量键 | `str` | 无 |
| `tradability_inputs.build_tradability_inputs` | eps 取源 + 键匹配 | 面板 + policy + list_date | `(inputs, meta)` | `tradability.TradabilityPolicy` |
| `tradability.apply_tradability` | **不动** | — | — | — |

### 3.3 数据流

1. `policy` 为空 → 实例化 `TradabilityPolicy()`；`eps = policy.eps`（D1）。
2. `list_date` 逐 code：**先精确命中** `code in ld.index`；否则用归一化映射回退（D2）。
3. `st_overrides` 复用同一 `_norm_code`（行为等价改写）。

### 3.4 控制流

`build_tradability_inputs` 是纯函数，无 IO；D1/D2 均在其内部，`apply_tradability` 调用图不变。

## 4. 接口定义

### 4.1 `_norm_code`

```python
def _norm_code(code):
    """代码键归一：剥离交易所后缀并补齐 6 位（'600000.SH'→'600000'，1→'000001'）。"""
```

- 回退点：删除该函数并恢复内联表达式，即可回到 v3.9.9 行为。

### 4.2 `build_tradability_inputs`（签名不变）

```python
def build_tradability_inputs(close, high, low, open_, volume, suspend, name,
                             adj, list_date=None, policy=None,
                             st_overrides=None):
```

- 行为增量仅两处：eps 取源、list_date 匹配回退；签名、返回结构、meta 键集合（13 键）不变。
- 回退点：单文件 revert（无跨文件耦合）。

## 5. 设计决策与替代方案

### 5.1 D1 eps 单源（采纳）

- 做法：`policy = policy if policy is not None else TradabilityPolicy()`（**仅用于取 eps**，不回写 `inputs.policy`）。
- 被拒替代 A：`eps = _EPS if policy is None else policy.eps`。拒绝理由：仍是常量第二源，未来默认值变更不会跟随；代价 = 1 行。
- 被拒替代 B：把实例化后的 policy 写入 `TradabilityInputs.policy`。拒绝理由：改变 `inputs.policy is None` 这一既有观察面（引擎虽兜底，但属契约变更）；代价 = 潜在下游行为变化，零收益。

### 5.2 D2 list_date 键归一化（采纳）

- 做法：`norm = {_norm_code(k): v}`（首见优先）+ 精确匹配优先。
- 被拒替代 C：全部改归一化映射（去除精确匹配）。拒绝理由：重复键/非标准键的优先级会变；代价 = 潜在静默改判。
- 被拒替代 D：不改，只加 warning。拒绝理由：`list_date` 缺失当前无 warning 通道，新增通道属门禁类改动，超范围。

### 5.3 D3 正向计数用例（采纳）

- 拆为两个**单事件**用例：T020-1a 只构造一字涨停（`high=low=up`），断言 `one_word_up==1` 且 `one_word_down==0`；T020-1b 只构造一字跌停，断言反向。单事件下方向若翻转必然失败，等价于「不串扰」且可被聚合报告直接断言。
- 被拒替代 E：单用例同时构造涨/跌两个事件再断言 `up==1 & down==1`。拒绝理由：无法区分「方向翻转 + 另一事件补足」的复合错误；且无法定位失败方向。

### 5.4 D4 `ref=` 直传用例（采纳）

- 直接给 `ref` 矩阵（`adj=None`），构造 ref=5.0 的除权日封板，断言 `blocked_buy` 与 `limit_unknown` 读数；与 `test_tp6_6`（经 adj 派生）形成**同结果双路径**对照。
- 被拒替代 F：仅复用 `test_tp6_6`。拒绝理由：该用例走 adj 派生，无法证明直传分支可达。

### 5.5 D5 版本与文档

- 包版本 **3.9.10**（patch）；CHANGELOG 顶部新增条目，**明示 ①③ 改变启用态行为**；PROGRESS P-020 → done。

### 5.6 D6 台账同步（A）

- `PROJECT_STATUS.md` §1：新增 v3.9.9 / v3.9.10 两行 + 指针移到 v3.9.10；§2：`P2 =（无）`、`P3 = P-009 / P-018`（P-020 已 done）。

## 6. 数据结构

不变。`TradabilityInputs` 字段 15 项与 `meta` 13 键均保持（见 P-006 DESIGN §4.6）。

## 7. 错误处理

| 场景 | 处理 | 可见信息 |
|---|---|---|
| `list_date` 键既非精确也不可归一命中 | 维持 `continue`（静默跳过） | 无（与现状一致；新增归一化后命中面增大） |
| `policy` 传入非 `TradabilityPolicy` 对象但具 `eps` | 按鸭子类型取 `policy.eps`（不新增校验） | 无 |
| `adj=None` 但传 `list_date` | 仍抛 `ValueError`（既有守卫） | `build_tradability_inputs 需要 adj（后复权因子）` |

## 8. 不变式（Invariants）

1. **INV-1**：`tradability_inputs=None` 时引擎输出逐位不变（P-006 INV-1 延续；TP6-11 六项基线字面量 + turnover 11 项）。
2. **INV-2**：`build_tradability_inputs(policy=None, 键同形)` 的 `meta` 13 键逐键逐值不变（含 `one_word_*`）。
3. **INV-3**：`meta["one_word_up_cells"]` 与同一 `policy` 下 `apply_tradability` 的 `report["one_word_up"]` 在同输入上口径同源（不再各自取不同 eps）。
4. **INV-4**：`list_date` 精确命中时行为与 v3.9.9 完全一致（归一化只在未命中时生效）。
5. **INV-5**：`apply_tradability` / `compute_limits` / `TradabilityInputs` 零改动。
6. **INV-6**：默认工件 `out/capacity_impact.json` SHA `82728CE1…` 与 `panel_hash dfcc4e1d…` 逐位不变（本批不触碰容量路径，作为护栏）。

## 9. 幻觉抑制审查（Step 4 Review）

### 9.1 设计基于已验证的调研结论

- [x] 每条决策可追溯到 RESEARCH F-/C- 编号
- [x] 无未经验证假设（D1 的行为依赖 `TradabilityPolicy` 默认值 = `_EPS`，已 E1 核实）
- [x] 无归因扭曲：本批**不**声称修复提升任何容量/收益读数

### 9.2 替代方案审查

- [x] 6 个被拒方案（A/B/C/D/E/F），各带拒绝理由与代价

### 9.3 职责边界审查

- [x] 未越界改动 `execution/`、算法层、字段集合

### 9.4 Step 4 独立复审记录

- 复审方式：独立只读子代理（首轮只返回锚点清单、未裁决；第二轮定向追问后给出裁决，见下）。
- 结论：**PASS_WITH_FIXES**（0×P1 / 0×P2 / 3×P3）。
  - 「必须修」四项 = **D1-D4 的落地确认**（非设计变更）：eps 由 policy 取源且不写回 `inputs.policy`；`list_date` 精确命中优先；补一字板正/负向计数；补 `ref=` 直传用例。
  - P3-1（已处置）：`inputs.policy` 不得被改写为实例化对象 → §5.1 已写明「仅用于取 eps」。
  - P3-2（已处置）：`policy` 鸭子类型边界 → §7 增补一行，登记为已知边界。
  - P3-3（如实登记不修，转 U-1）：`meta.one_word_*` 与 `report.one_word_*` 的 `judge` 掩码不同构（前者含 `~no_limit`），故 INV-3 限定为「eps 同源」而非「数值必然相等」。
- 默认路径风险：**无**（D1 不改 `inputs.policy is None`；D2 只在未命中时回退）。

## 10. 对实施的输入

### 10.1 关键工程约束

- 只改 `backtest/tradability_inputs.py`（生产）与 `tests/test_tradability*.py`（测试）+ 台账/版本文件。
- 版本 3.9.10 需覆盖全部既有落点（7 处 + 本批查全）。
- Python 3.9；零新增依赖。

### 10.2 风险与缓解

| 风险 | 缓解 |
|---|---|
| D2 改变异常键行为 | INV-4 精确优先；用例覆盖同形与裸码两个方向 |
| D1 改变 meta 读数 | INV-2 默认路径逐值锁定 |
| 一字跌停用例被 T+1 干扰 | 用例中 `policy.t_plus_1=False` 或只断言报告计数（计数与 T+1 无关） |

## 11. 未决项登记（四元块）与决策矩阵

**11.1 未决项登记**：

- **U-1 构建器 `judge` 掩码与推进期不同构**
  - **判据**：两条路径在同一输入上 `one_word_*` 计数完全相等
  - **触发条件**：出现依赖「meta 与 report 数值相等」的下游消费方
  - **当前倾向**：不修（构建期剔除 `no_limit` 属有意口径：IPO/退市整理日本就不该计入一字板统计）
  - **证据等级**：E1

**11.2 决策矩阵**：不启用（本批决策均可逆，Type-2）。

---

**Review 签字**: Step 4 独立只读复审（PASS_WITH_FIXES，见 §9.4） 日期: 2026-11-23
